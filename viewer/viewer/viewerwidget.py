
"""
Viewer Widget. Allows display of images,
zooming and panning etc.
"""

import numpy
from PyQt4.QtGui import QAbstractScrollArea, QPainter, QRubberBand, QCursor, QPixmap, QImage, QPen
from PyQt4.QtCore import Qt, QRect, QSize, QPoint, SIGNAL
from osgeo import gdal

from . import viewererrors
from . import viewerLUT


VIEWER_ZOOM_WHEEL_FRACTION = 0.1 # viewport increased/decreased by the fraction
                            # on zoom out/ zoom in with mouse wheel

QUERY_CURSOR_HALFSIZE = 8 # number of pixels
QUERY_CURSOR_WIDTH = 2 # in pixels

# raise exceptions rather than returning None
gdal.UseExceptions()

# Mappings between numpy datatypes and GDAL datatypes.
# Note that ambiguities are resolved by the order - the first one found
# is the one chosen.
dataTypeMapping = [
    (numpy.uint8,gdal.GDT_Byte),
    (numpy.bool,gdal.GDT_Byte),
    (numpy.int16,gdal.GDT_Int16),
    (numpy.uint16,gdal.GDT_UInt16),
    (numpy.int32,gdal.GDT_Int32),
    (numpy.uint32,gdal.GDT_UInt32),
    (numpy.single,gdal.GDT_Float32),
    (numpy.float,gdal.GDT_Float64)
]

def GDALTypeToNumpyType(gdaltype):
    """
    Given a gdal data type returns the matching
    numpy data type
    """
    for (numpy_type,test_gdal_type) in dataTypeMapping:
        if test_gdal_type == gdaltype:
            return numpy_type
    raise viewererrors.TypeConversionError("Unknown GDAL datatype: %s"%gdaltype)

def NumpyTypeToGDALType(numpytype):
    """
    For a given numpy data type returns the matching
    GDAL data type
    """
    for (test_numpy_type,gdaltype) in dataTypeMapping:
        if test_numpy_type == numpytype:
            return gdaltype
    raise viewererrors.TypeConversionError("Unknown numpy datatype: %s"%numpytype)

class WindowFraction(object):
    """
    Stores information about wereabouts in the current
    image the viewport is looking as a fraction
    of the whole image from:
    1) the top left of the whole image to the top left of the
        currently viewed portion
    2) the fraction of the viewed portion relative
        to the whole thing
    """
    def __init__(self, winsize, firstoverview):
        self.firstoverview = firstoverview
        self.resetToFull(winsize)

    def resetToFull(self, winsize):
        """
        initially we are looking at the whole image
        centred on the middle
        """
        self.centrefraction = [0.5, 0.5]

        xperpix = float(self.firstoverview.xsize) / float(winsize.width())
        yperpix = float(self.firstoverview.ysize) / float(winsize.height())
        self.imgpixperwinpix = max(xperpix, yperpix)

    def moveToCoord(self, easting, northing, metresperwinpix, transform):
        """
        This is used for the geolinking. easting and northing become
        the new centre.
        metresperwinpix is the number of metres per window pixel. This gets divided
        by the pixel size to create imgpixperwinpix. Set to 0 if this widget not 
        following extent.
        """
        centrefractionx = (easting - transform[0]) / (transform[1] * self.firstoverview.xsize)
        centrefractiony = (northing - transform[3]) / (transform[5] * self.firstoverview.ysize)

        if centrefractionx < 0:
            centrefractionx = 0.0
        elif centrefractionx > 1.0:
            centrefractionx = 1.0

        if centrefractiony < 0:
            centrefractiony = 0.0
        elif centrefractiony > 1.0:
            centrefractiony = 1.0

        self.centrefraction = [centrefractionx, centrefractiony]

        if metresperwinpix != 0:
            self.imgpixperwinpix = metresperwinpix / transform[1]

    def getCoordFor(self, x_fromcenter, y_fromcenter, transform):
        """
        For getting between window and world coords
        """
        x_center = self.firstoverview.xsize * self.centrefraction[0]
        y_center = self.firstoverview.ysize * self.centrefraction[1]
        column = x_center + x_fromcenter * self.imgpixperwinpix
        row = y_center + y_fromcenter * self.imgpixperwinpix
        easting = transform[0] + column * transform[1] + row * transform[2]
        northing = transform[3] + column * transform[4] + row * transform[5]
        return easting, northing, column, row

    def getWindowCoordFor(self, col, row, winsize):
        """
        For going from rol/col at full res and current window coord
        """
        imgx_fromcentre = col - (self.firstoverview.xsize * self.centrefraction[0])
        imgy_fromcentre = row - (self.firstoverview.ysize * self.centrefraction[1])
        winx_fromcentre = imgx_fromcentre / self.imgpixperwinpix
        winy_fromcentre = imgy_fromcentre / self.imgpixperwinpix
        winx = winx_fromcentre + (winsize.width() / 2)
        winy = winy_fromcentre + (winsize.height() / 2)
        return int(numpy.round(winx)), int(numpy.round(winy))

    def moveView(self, xfraction, yfraction):
        """
        Move the view by xfraction and yfraction
        (positive to the right and down)
        """
        # try it and see what happens
        centrefractionx = self.centrefraction[0] + xfraction
        centrefractiony = self.centrefraction[1] + yfraction

        if centrefractionx < 0:
            centrefractionx = 0.0
        elif centrefractionx > 1.0:
            centrefractionx = 1.0

        if centrefractiony < 0:
            centrefractiony = 0.0
        elif centrefractiony > 1.0:
            centrefractiony = 1.0

        self.centrefraction = [centrefractionx, centrefractiony]

    def zoomViewCenter(self, x_fromcentre, y_fromcentre, fraction):
        """
        For zooming with zoom tool. x_fromcentre and y_fromcentre
        is the centre of the new box in respect to the current window.
        """
        if x_fromcentre != 0 or y_fromcentre != 0:
            offsetx = (x_fromcentre * self.imgpixperwinpix) / self.firstoverview.xsize
            offsety = (y_fromcentre * self.imgpixperwinpix) / self.firstoverview.ysize
            centrefractionx = self.centrefraction[0] + offsetx
            centrefractiony = self.centrefraction[1] + offsety

            # range check
            if centrefractionx < 0:
                centrefractionx = 0.0
            elif centrefractionx > 1.0:
                centrefractionx = 1.0

            if centrefractiony < 0:
                centrefractiony = 0.0
            elif centrefractiony > 1.0:
                centrefractiony = 1.0

            self.centrefraction = [centrefractionx, centrefractiony]
        self.imgpixperwinpix *= fraction



class OverviewInfo(object):
    """
    Stores size and index of an overview
    """
    def __init__(self, xsize, ysize, fullrespixperpix, index):
        self.xsize = xsize
        self.ysize = ysize
        self.fullrespixperpix = fullrespixperpix
        self.index = index

class OverviewManager(object):
    """
    This class contains a list of valid overviews
    and allows the best overview to be retrieved
    """
    def __init__(self):
        self.overviews = None

    def getFullRes(self):
        return self.overviews[0]

    def loadOverviewInfo(self, ds, bands):
        """
        Load the overviews from the GDAL dataset into a list
        bands should be a list or tuple of band indices.
        Checks are made that all lists bands contain the
        same sized overviews
        """
        # i think we can assume that all the bands are the same size
        # add an info for the full res - this should always be location 0
        ovi = OverviewInfo(ds.RasterXSize, ds.RasterYSize, 1.0, 0)
        self.overviews = [ovi]

        # for the overviews
        # start with the first band and go from there
        band = ds.GetRasterBand(bands[0])

        count = band.GetOverviewCount()
        for index in range(count):
            ov = band.GetOverview(index)

            # do the other bands have the same resolution overview
            # at the same index?
            overviewok = True
            for bandnum in bands[1:]:
                otherband = ds.GetRasterBand(bandnum)
                otherov = otherband.GetOverview(index)
                if otherov.XSize != ov.XSize or otherov.YSize != ov.YSize:
                    overviewok = False
                    break

            if overviewok:
                # calc the conversion to full res pixels
                fullrespixperpix = float(ds.RasterXSize) / float(ov.XSize) # should do both ways?
                # remember index 0 is full res so all real overviews are +1
                ovi = OverviewInfo(ov.XSize, ov.YSize, fullrespixperpix, index + 1)
                self.overviews.append(ovi)

        # make sure they are sorted by area - biggest first
        self.overviews.sort(key=lambda ov: ov.xsize * ov.ysize, reverse=True)

    def findBestOverview(self, imgpixperwinpix):
        """
        Finds the best overview for given imgpixperwinpix
        """
        selectedovi = self.overviews[0]
        for ovi in self.overviews[1:]:
            if ovi.fullrespixperpix > imgpixperwinpix:
                break # gone too far, selectedovi is selected
            else:
                # got here overview must be ok, but keep going
                selectedovi = ovi

        return selectedovi

class QueryInfo(object):
    """
    Container class for the information passed in the locationSelected
    signal.
    """
    def __init__(self, easting, northing, column, row, data, stretch):
        self.easting = easting
        self.northing = northing
        self.column = column
        self.row = row
        self.data = data
        self.stretch = stretch
        # set the following fields manually
        self.bandNames = None
        self.wavelengths = None
        self.columnNames = None
        self.attributeData = None

VIEWER_TOOL_NONE = 0
VIEWER_TOOL_ZOOMIN = 1
VIEWER_TOOL_ZOOMOUT = 2
VIEWER_TOOL_PAN = 3
VIEWER_TOOL_QUERY = 4

class ViewerWidget(QAbstractScrollArea):
    """
    The main ViewerWidget class. Should be embeddable in
    other applications. See the open() function for loading
    images.
    """
    def __init__(self, parent):
        QAbstractScrollArea.__init__(self, parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        self.filename = None
        self.ds = None
        self.transform = None
        self.bandNames = None
        self.wavelengths = None
        self.noDataValues = None
        self.columnNames = None   # for single band imagery
        self.attributeData = None # for single band imagery
        self.queryPoints = None
        self.overviews = OverviewManager()
        self.lut = viewerLUT.ViewerLUT()
        self.stretch = None
        self.image = None
        self.windowfraction = None
        self.paintPoint = QPoint() # normally 0,0 unless we are panning

        # when moving the scroll bars
        # events get fired that we wish to ignore
        self.suppressscrollevent = False

        # set the background color to black so window
        # is black when nothing loaded and when panning
        # new areas are initially black.
        widget = self.viewport()
        palette = widget.palette()
        palette.setColor(widget.backgroundRole(), Qt.black);
        widget.setPalette(palette)

        # to do with tools
        self.rubberBand = None
        self.panCursor = None
        self.panGrabCursor = None
        self.zoomInCursor = None
        self.zoomOutCursor = None
        self.queryCursor = None
        self.activeTool = VIEWER_TOOL_NONE
        self.panOrigin = None

        # Define the scroll wheel behaviour
        self.mouseWheelZoom = True
        # do we follow extent when geolinking?
        self.geolinkFollowExtent = True

    def open(self, fname, stretch, lut=None):
        """
        Displays the specified image using bands (a tuple of 1 based indices)
        and ViewerStretch instance
        This should be called after widget first shown to
        avoid unnecessary redraws
        """
        self.filename = fname
        self.ds = gdal.Open(fname)

        # do some checks to see if we can deal with the data
        # currently only support square pixels and non rotated
        transform = self.ds.GetGeoTransform()
        if transform[2] != 0 or transform[4] != 0 or transform[1] != -transform[5]:
            msg = 'Only currently support square pixels and non-rotated images'
            raise viewererrors.InvalidDataset(msg)
        self.transform = transform

        # store the stretch
        self.stretch = stretch

        # load the valid overviews
        self.overviews.loadOverviewInfo(self.ds, stretch.bands)

        # reset these values
        size = self.viewport().size()
        self.windowfraction = WindowFraction(size, self.overviews.getFullRes())

        # read in the LUT if not specified
        if lut is None:
            self.lut.createLUT(self.ds, stretch)
        else:
            self.lut = lut

        # grab the band names
        self.bandNames = self.getBandNames()

        # grab the wavelengths
        self.wavelengths = self.getWavelengths()

        # the no data values for each band
        self.noDataValues = self.getNoDataValues()

        # if we are single band read attributes if any
        if len(stretch.bands) == 1:
            self.columnNames, self.attributeData = self.getAttributes(stretch.bands[0])
        else:
            self.columnNames = None
            self.attributeData = None

        # start with no query points and go from there
        self.queryPoints = {}

        # now go and retrieve the data for the image
        self.getData()

    def getBandNames(self):
        """
        Return the list of band names
        """
        bandNames = []
        for n in range(self.ds.RasterCount):
            band = self.ds.GetRasterBand(n+1)
            name = band.GetDescription()
            bandNames.append(name)
        return bandNames
        
    def getWavelengths(self):
        """
        Return the list of wavelength if file
        conforms to the metadata provided by the 
        ENVI driver, or None
        """
        wavelengths = []
        ok = True
        # GetMetadataItem seems buggy for ENVI
        # get the lot and go through
        meta = self.ds.GetMetadata()
        # go through each band
        for n in range(self.ds.RasterCount):
            # get the metadata item based on band name
            metaname = "Band_%d" % (n+1)
            if metaname in meta:
                item = meta[metaname]
                # try to convert to float
                try:
                    wl = float(item)
                except ValueError:
                    ok = False
                    break
                # must be ok
                wavelengths.append(wl)
            else:
                ok = False
                break

        # failed
        if not ok:
            wavelengths = None

        return wavelengths
        
    def getNoDataValues(self):
        """
        Return a list of no data values - one for each band
        """
        noData = []
        for n in range(self.ds.RasterCount):
            band = self.ds.GetRasterBand(n+1)
            value = band.GetNoDataValue() # returns None if not set
            noData.append(value)
        return noData

    def getAttributes(self, bandnum):
        """
        Read the attributes
        """
        columnNames = []
        attributeData = {}

        gdalband = self.ds.GetRasterBand(bandnum)
        rat = gdalband.GetDefaultRAT()
        if rat is not None:
            # first get the column names
            # we do this so we can preserve the order
            # of the columns in the attribute table
            ncols = rat.GetColumnCount()
            nrows = rat.GetRowCount()
            for col in range(ncols):
                colname = rat.GetNameOfCol(col)
                columnNames.append(colname)

                # get the attributes as a dictionary
                # keyed on column name and the values
                # being a list of attribute values
                colattr = []
                for row in range(nrows):
                    valstr = rat.GetValueAsString(row, col)
                    colattr.append(valstr)
                attributeData[colname] = colattr

        return columnNames, attributeData

    def setQueryPoint(self, id, col, row, color):
        """
        Query points are overlayed ontop of the map at the given
        row and col (at full res) and with the given color. This
        function adds one based on an 'id' which uniquely identifies
        the QueryDockWindow
        """
        self.queryPoints[id] = (col, row, color)

        # force repaint
        self.viewport().update()

    def removeQueryPoint(self, id):
        """
        Remove given query point given the id.
        """
        del self.queryPoints[id]

        # force repaint
        self.viewport().update()

    def zoomNativeResolution(self):
        """
        Sets the zoom to native resolution wherever
        the current viewport is centered
        """
        if self.windowfraction is not None:
            self.windowfraction.imgpixperwinpix = 1.0
            self.getData()
            # geolink
            self.emitGeolinkMoved()

    def zoomFullExtent(self):
        """
        Resets the zoom to full extent - should be
        the same as when file was opened.
        """
        if self.windowfraction is not None:
            size = self.viewport().size()
            self.windowfraction.resetToFull(size)
            self.getData()
            # geolink
            self.emitGeolinkMoved()

    def setActiveTool(self, tool):
        """
        Set active tool (one of VIEWER_TOOL_*).
        pass VIEWER_TOOL_NONE to disable
        """
        self.activeTool = tool
        if tool == VIEWER_TOOL_ZOOMIN:
            if self.zoomInCursor is None:
                # create if needed.
                self.zoomInCursor = QCursor(QPixmap(["16 16 3 1",
                                  ". c None",
                                  "a c #000000",
                                  "# c #ffffff",
                                  ".....#####......",
                                  "...##aaaaa##....",
                                  "..#.a.....a.#...",
                                  ".#.a...a...a.#..",
                                  ".#a....a....a#..",
                                  "#a.....a.....a#.",
                                  "#a.....a.....a#.",
                                  "#a.aaaa#aaaa.a#.",
                                  "#a.....a.....a#.",
                                  "#a.....a.....a#.",
                                  ".#a....a....a#..",
                                  ".#.a...a...aaa#.",
                                  "..#.a.....a#aaa#",
                                  "...##aaaaa###aa#",
                                  ".....#####...###",
                                  "..............#."]))
            self.viewport().setCursor(self.zoomInCursor)

        elif tool == VIEWER_TOOL_ZOOMOUT:
            if self.zoomOutCursor is None:
                # create if needed
                self.zoomOutCursor = QCursor(QPixmap(["16 16 4 1",
                                  "b c None",
                                  ". c None",
                                  "a c #000000",
                                  "# c #ffffff",
                                  ".....#####......",
                                  "...##aaaaa##....",
                                  "..#.a.....a.#...",
                                  ".#.a.......a.#..",
                                  ".#a.........a#..",
                                  "#a...........a#.",
                                  "#a...........a#.",
                                  "#a.aaaa#aaaa.a#.",
                                  "#a...........a#.",
                                  "#a...........a#.",
                                  ".#a.........a#..",
                                  ".#.a.......aaa#.",
                                  "..#.a.....a#aaa#",
                                  "...##aaaaa###aa#",
                                  ".....#####...###",
                                  "..............#."]))
            self.viewport().setCursor(self.zoomOutCursor)

        elif tool == VIEWER_TOOL_PAN:
            if self.panCursor is None:
                # both these used for pan operations
                self.panCursor = QCursor(Qt.OpenHandCursor)
                self.panGrabCursor = QCursor(Qt.ClosedHandCursor)
            self.viewport().setCursor(self.panCursor)

        elif tool == VIEWER_TOOL_QUERY:
            if self.queryCursor is None:
                self.queryCursor = QCursor(Qt.CrossCursor)
            self.viewport().setCursor(self.queryCursor)

        elif tool == VIEWER_TOOL_NONE:
            # change back
            self.viewport().setCursor(Qt.ArrowCursor)

    def setNewStretch(self, newstretch, local=False):
        """
        Change the stretch being applied to the current data
        """
        newbands = self.stretch.bands != newstretch.bands
        if newbands:
            # only need to do this if bands have changed
            self.overviews.loadOverviewInfo(self.ds, newstretch.bands)

        image = None
        if local and not newbands:
            # we can just grab the stats from the last read
            image = self.image

        self.lut.createLUT(self.ds, newstretch, image)

        self.stretch = newstretch
        # note - we need to do this to reapply the stretch
        # but it re-reads the data always.
        # not sure it is a big deal since GDAL caches
        self.getData()

        if local and newbands:
            # this is a bit of a hack. We needed to do a 
            # getData to get the new bands loaded. Now
            # we can get the stats and apply the stretch locally
            self.lut.createLUT(self.ds, newstretch, self.image)
            self.getData()

    def setMouseScrollWheelAction(self, scrollZoom):
        self.mouseWheelZoom = scrollZoom

    def setGeolinkFollowExtentAction(self, followExtent):
        self.geolinkFollowExtent = followExtent

    def getData(self):
        """
        Called when new file opened, or resized,
        pan, zoom etc. Grabs data from the
        appropriate overview and applies the lut
        to it.
        """
        # if nothing open, just return
        if self.ds is None:
            return

        # the fraction we are displaying
        centrefraction = self.windowfraction.centrefraction
        imgpixperwinpix = self.windowfraction.imgpixperwinpix

        # find the best overview based on imgpixperwinpix
        selectedovi = self.overviews.findBestOverview(imgpixperwinpix)
        print selectedovi.index

        size = self.viewport().size()
        winxsize = size.width()
        winysize = size.height()
        half_winxsize = winxsize / 2
        half_winysize = winysize / 2

        # the centre of the image in overview coords
        ov_centrex = selectedovi.xsize * centrefraction[0]
        ov_centrey = selectedovi.ysize * centrefraction[1]
        # conversion between full res and overview coords
        ov_to_full = imgpixperwinpix / selectedovi.fullrespixperpix
        # size of image in overview units
        ov_xsize = int(winxsize * ov_to_full)
        ov_ysize = int(winysize * ov_to_full)

        # to get from window to overview
        # win * ov_to_full
        # to get from overview to window:
        # ov / ov_to_full
        # subtract half the size to get top left in overview coords
        ov_x = int(ov_centrex - (ov_xsize / 2.0))
        ov_y = int(ov_centrey - (ov_ysize / 2.0))

        # window coords for image we will read in
        win_tlx = 0
        win_tly = 0
        win_brx = winxsize
        win_bry = winysize

        # 1) the requested area won't fit into viewport
        if ov_x < 0:
            # make a black area on the side
            overflow = abs(ov_x)
            win_tlx = int(overflow / ov_to_full)
            ov_xsize -= overflow # adjust size so we are still centred
            ov_x = 0
        if ov_y < 0:
            overflow = abs(ov_y)
            # make a black area on the side
            win_tly = int(overflow / ov_to_full)
            ov_ysize -= overflow # adjust size so we are still centred
            ov_y = 0

        # now do the same to the sizes if we are still too big
        ov_brx = ov_x + ov_xsize
        if ov_brx > selectedovi.xsize:
            overflow = ov_brx - selectedovi.xsize
            win_brx -= int(overflow / ov_to_full)
            ov_xsize -= overflow
        ov_bry = ov_y + ov_ysize
        if ov_bry > selectedovi.ysize:
            overflow = ov_bry - selectedovi.ysize
            win_bry -= int(overflow / ov_to_full)
            ov_ysize -= overflow

        # size of image we will ask GDAL for
        blockxsize = win_brx - win_tlx
        blockysize = win_bry - win_tly

        # only need to do the mask once
        mask = numpy.empty((winysize, winxsize), dtype=numpy.uint8)
        mask.fill(viewerLUT.MASK_BACKGROUND_VALUE) # set to background
        mask[win_tly:win_bry, win_tlx:win_brx] = viewerLUT.MASK_IMAGE_VALUE # 0 where there is data
        nodata_mask = None

        if len(self.stretch.bands) == 3:
            # rgb
            datalist = []
            for bandnum in self.stretch.bands:
                band = self.ds.GetRasterBand(bandnum)

                # create blank array of right size to read in to
                numpytype = GDALTypeToNumpyType(band.DataType)
                data = numpy.zeros((winysize, winxsize), dtype=numpytype) 

                # get correct overview
                if selectedovi.index > 0:
                    band = band.GetOverview(selectedovi.index - 1)

                # read into correct part of our window array
                data[win_tly:win_bry, win_tlx:win_brx] = (
                    band.ReadAsArray(ov_x, ov_y, ov_xsize, ov_ysize, blockxsize, blockysize))

                # do the no data test
                nodata_value = self.noDataValues[bandnum-1]
                if nodata_value is not None:
                    inimage_and_nodata = numpy.logical_and(mask == viewerLUT.MASK_IMAGE_VALUE, data == nodata_value)
                    if nodata_mask is None:
                        nodata_mask = inimage_and_nodata
                    else:
                        # should it be 'or' or 'and' ?
                        nodata_mask = numpy.logical_and(nodata_mask, inimage_and_nodata)

                datalist.append(data)

            # apply the no data
            if nodata_mask is not None:
                mask = numpy.where(nodata_mask, viewerLUT.MASK_NODATA_VALUE, mask)

            # apply LUT
            self.image = self.lut.applyLUTRGB(datalist, mask)

        else:
            # must be single band
            band = self.ds.GetRasterBand(self.stretch.bands[0])

                # create blank array of right size to read in to
            numpytype = GDALTypeToNumpyType(band.DataType)
            data = numpy.zeros((winysize, winxsize), dtype=numpytype) 

            # get correct overview
            if selectedovi.index > 0:
                band = band.GetOverview(selectedovi.index - 1)

            # read into correct part of our window array
            data[win_tly:win_bry, win_tlx:win_brx] = (
                band.ReadAsArray(ov_x, ov_y, ov_xsize, ov_ysize, blockxsize, blockysize))

            # set up the mask - all background to begin with
            mask = numpy.empty((winysize, winxsize), dtype=numpy.uint8) 
            mask.fill(viewerLUT.MASK_BACKGROUND_VALUE)
            mask[win_tly:win_bry, win_tlx:win_brx] = viewerLUT.MASK_IMAGE_VALUE # set where data

            # do we have no data for this band?
            nodata_value = self.noDataValues[self.stretch.bands[0] - 1]
            if nodata_value is not None:
                inimage_and_nodata = numpy.logical_and(mask == viewerLUT.MASK_IMAGE_VALUE, data == nodata_value)
                mask = numpy.where(inimage_and_nodata, viewerLUT.MASK_NODATA_VALUE, mask)

            # apply LUT
            self.image = self.lut.applyLUTSingle(data, mask)

        # reset the scroll bars for new extent of window
        # need to suppress processing of new scroll bar
        # events otherwise we end up in endless loop
        self.suppressscrollevent = True
        self.horizontalScrollBar().setPageStep(ov_xsize / ov_to_full)
        self.verticalScrollBar().setPageStep(ov_ysize / ov_to_full)
        self.horizontalScrollBar().setRange(0, (selectedovi.xsize - ov_xsize) / ov_to_full)
        self.verticalScrollBar().setRange(0, (selectedovi.ysize - ov_ysize) / ov_to_full)
        self.horizontalScrollBar().setSliderPosition(ov_x)
        self.verticalScrollBar().setSliderPosition(ov_y)
        self.suppressscrollevent = False

        # force repaint
        self.viewport().update()

    def scrollContentsBy(self, dx, dy):
        """
        Handle the user moving the scroll bars
        """
        # if nothing open, just return
        if self.ds is None:
            return

        if not self.suppressscrollevent:
            xamount = dx * -(self.windowfraction.imgpixperwinpix / float(self.ds.RasterXSize))
            yamount = dy * -(self.windowfraction.imgpixperwinpix / float(self.ds.RasterYSize))
            self.windowfraction.moveView(xamount, yamount)

            self.getData()
            # geolink
            self.emitGeolinkMoved()

    def wheelEvent(self, event):
        """
        User has used mouse wheel to zoom in/out or pan depending on defined preference
        """
        # if nothing open, just return
        if self.ds is None:
            return

        if self.mouseWheelZoom:
            if event.delta() > 0:
                self.windowfraction.zoomViewCenter(0, 0, 1.0 - VIEWER_ZOOM_WHEEL_FRACTION)
            elif event.delta() < 0:
                self.windowfraction.zoomViewCenter(0, 0, 1.0 + VIEWER_ZOOM_WHEEL_FRACTION)
            self.getData()
        else:
            dx = 0
            dy = 0
            if event.orientation() == Qt.Horizontal:
                dx = event.delta()
            else:
                dy = event.delta()
            self.scrollContentsBy(dx,dy)
        
        # geolink
        self.emitGeolinkMoved()

    def resizeEvent(self, event):
        """
        Window has been resized - get new data
        """
        # should probably do something clever with
        # only getting new data if bigger
        # otherwise moving centre, but all too hard
        self.getData()

    def paintEvent(self, event):
        """
        Viewport needs to be redrawn. Assume that
        self.image is current (as created by getData())
        we can just draw it with QPainter
        """
        if self.image is not None:
            paint = QPainter(self.viewport())
            paint.drawImage(self.paintPoint, self.image)
            self.drawQueryPoints(paint)    # draw any query points on top of image
            paint.end()

    def drawQueryPoints(self, paint):
        """
        Draw query points as part of paint.
        """
        if self.windowfraction is not None:
            size = self.viewport().size()
            pen = QPen()
            pen.setWidth(QUERY_CURSOR_WIDTH)
            for id in self.queryPoints:
                (col, row, color) = self.queryPoints[id]
                cx, cy = self.windowfraction.getWindowCoordFor(col, row, size)
                pen.setColor(color)
                paint.setPen(pen)
                # draw cross hair
                paint.drawLine(cx - QUERY_CURSOR_HALFSIZE, cy, cx + QUERY_CURSOR_HALFSIZE, cy)
                paint.drawLine(cx, cy - QUERY_CURSOR_HALFSIZE, cx, cy + QUERY_CURSOR_HALFSIZE)

    def mousePressEvent(self, event):
        """
        Mouse has been clicked down if we are in zoom/pan
        mode we need to start doing stuff here
        """
        QAbstractScrollArea.mousePressEvent(self, event)
        if self.activeTool == VIEWER_TOOL_ZOOMIN or self.activeTool == VIEWER_TOOL_ZOOMOUT:
            origin = event.pos()
            if self.rubberBand is None:
                self.rubberBand = QRubberBand(QRubberBand.Rectangle, self)
            self.rubberBand.setGeometry(QRect(origin, QSize()))
            self.rubberBand.show()
            self.rubberBand.origin = origin

        elif self.activeTool == VIEWER_TOOL_PAN:
            # remember pos
            self.panOrigin = event.pos()
            # change cursor
            self.viewport().setCursor(self.panGrabCursor)

        elif self.activeTool == VIEWER_TOOL_QUERY:
            if self.windowfraction is not None:
                pos = event.pos()
                geom = self.viewport().geometry()
                geomcenter = geom.center()
                # work out where we are remembering
                # the one pixel offset
                x_fromcenter = pos.x() - geomcenter.x() - geom.x()
                y_fromcenter = pos.y() - geomcenter.y() - geom.y()
                # work out where that is in relation to the whole image
                easting, northing, column, row = (
                     self.windowfraction.getCoordFor(x_fromcenter, y_fromcenter, self.transform))
                # read the data out of the dataset
                if column >= 0 and column < self.ds.RasterXSize and row >= 0 and row < self.ds.RasterYSize:
                    data = self.ds.ReadAsArray(int(numpy.round(column)), int(numpy.round(row)), 1, 1)
                    if data is not None:
                        # we just want the single 'drill down' of data as a 1d array
                        data = data[...,0,0]
                        # if single band GDAL gives us a single value - convert back to array
                        # to make life easier
                        if data.size == 1:
                            data = numpy.array([data])

                        qi = QueryInfo(easting, northing, column, row, data, self.stretch)
                        qi.bandNames = self.bandNames
                        qi.wavelengths = self.wavelengths
                        qi.columnNames = self.columnNames
                        qi.attributeData = self.attributeData
                        # emit the signal - handled by the QueryDockWidget
                        self.emit(SIGNAL("locationSelected(PyQt_PyObject)"), qi)


    def mouseReleaseEvent(self, event):
        """
        Mouse has been released, if we are in zoom/pan
        mode we do stuff here.
        """
        QAbstractScrollArea.mouseReleaseEvent(self, event)
        if self.rubberBand is not None and self.rubberBand.isVisible():
            # get the information about the rect they have drawn
            # note this is on self, rather than viewport()
            selection = self.rubberBand.geometry()
            geom = self.viewport().geometry()

            selectioncenter = selection.center()
            selectionsize = float(selection.width() * selection.height())

            geomcenter = geom.center()
            geomsize = float(geom.width() * geom.height())

            self.rubberBand.hide()

            if self.windowfraction is not None:
                # zoom the appropriate distance from centre
                # and to the appropriate fraction (we used area so conversion needed)
                # adjust also for the fact that the selection is made on this widget
                # rather than the viewport - 1 pixel offset
                newcentrex = selectioncenter.x() - geomcenter.x() - geom.x()
                newcentrey = selectioncenter.y() - geomcenter.y() - geom.y()
                if selectionsize == 0:
                    fraction = 0.5 # they just clicked
                else:
                    fraction = numpy.sqrt(selectionsize / geomsize)

                if self.activeTool == VIEWER_TOOL_ZOOMIN:
                    self.windowfraction.zoomViewCenter(newcentrex, newcentrey, fraction )
                elif self.activeTool == VIEWER_TOOL_ZOOMOUT:
                    # the smaller the area the larger the zoom
                    self.windowfraction.zoomViewCenter(newcentrex, newcentrey, 1.0 / fraction )

                # redraw
                self.getData()
                # geolink
                self.emitGeolinkMoved()

        elif self.activeTool == VIEWER_TOOL_PAN:
            # change cursor back
            self.viewport().setCursor(self.panCursor)
            if self.windowfraction is not None:
                # stop panning and move viewport
                xamount = self.paintPoint.x() * -(self.windowfraction.imgpixperwinpix / float(self.ds.RasterXSize))
                yamount = self.paintPoint.y() * -(self.windowfraction.imgpixperwinpix / float(self.ds.RasterYSize))
                self.windowfraction.moveView(xamount, yamount)
                # reset
                self.paintPoint.setX(0)
                self.paintPoint.setY(0)
                # redraw
                self.getData()
                # geolink
                self.emitGeolinkMoved()


    def mouseMoveEvent(self, event):
        """
        Mouse has been moved while dragging. If in zoom/pan
        mode we need to do something here.
        """
        QAbstractScrollArea.mouseMoveEvent(self, event)
        if self.rubberBand is not None and self.rubberBand.isVisible():
            # must be doing zoom in/out. extend rect
            rect = QRect(self.rubberBand.origin, event.pos()).normalized()
            self.rubberBand.setGeometry(rect)

        elif self.activeTool == VIEWER_TOOL_PAN and self.windowfraction is not None:
            # panning. Work out the offset from where we
            # starting panning and draw the current image
            # at an offset
            pos = event.pos()
            xamount = pos.x() - self.panOrigin.x()
            yamount = pos.y() - self.panOrigin.y()
            self.paintPoint.setX(xamount)
            self.paintPoint.setY(yamount)
            # force repaint - self.paintPoint used by paintEvent()
            self.viewport().update()

    # geolinking routines
    def doGeolinkMove(self, easting, northing, metresperwinpix):
        """
        Call this when widget needs to be moved because
        of geolinking event.
        """
        # if we not moving extent set to 0 will be ignored
        if not self.geolinkFollowExtent:
            metresperwinpix = 0

        self.windowfraction.moveToCoord(easting, northing, metresperwinpix, self.transform)
        self.getData()

    def emitGeolinkMoved(self):
        """
        Call this on each zoom/pan to emit the appropriate signal.
        """
        # get the coords of the current centre
        easting, northing, col, row = self.windowfraction.getCoordFor(0, 0, self.transform)
        metresperwinpix = self.windowfraction.imgpixperwinpix * self.transform[1]

        # emit the signal
        self.emit(SIGNAL("geolinkMove(double, double, double, long)"), easting, northing, metresperwinpix, id(self) )


