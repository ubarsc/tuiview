
"""
Viewer Widget. Allows display of images,
zooming and panning etc.
"""

import numpy
from PyQt4.QtGui import QAbstractScrollArea, QPainter, QImage
from PyQt4.QtCore import Qt
from osgeo import gdal

from . import viewererrors

# constants for specifying how to display an image to open()
# as mode parameter
VIEWER_MODE_COLORTABLE = 1
VIEWER_MODE_GREYSCALE = 2
VIEWER_MODE_RGB = 3

VIEWER_STRETCHMODE_NONE = 0 # color table, or pre stretched data
VIEWER_STRETCHMODE_LINEAR = 1
VIEWER_STRETCHMODE_2STDDEV = 2
VIEWER_STRETCHMODE_HIST = 3


VIEWER_SCROLL_MULTIPLIER = 0.0002 # number of pixels scrolled
                                # is multiplied by this to get fraction
VIEWER_ZOOM_FRACTION = 0.1 # viewport increased/decreased by the fraction 
                            # on zoom out/ zoom in

# raise exceptions rather than returning None
gdal.UseExceptions()

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
    def __init__(self):
        # initially we are looking at the whole image
        self.tlfraction = [0.0, 0.0] # start at top left
        self.viewfraction = [1.0, 1.0] # contain the whole thing
        # this should always be True
        # self.tlfraction  + self.viewfraction <= 1.0

    def moveView(self, xfraction, yfraction):
        """
        Move the view by xfraction and yfraction
        (positive to the right and down)
        """
        # try it and see what happens
        tlfractionx = self.tlfraction[0] + xfraction
        tlfractiony = self.tlfraction[1] + yfraction

        if tlfractionx < 0:
            tlfractionx = 0.0
        elif (tlfractionx + self.viewfraction[0]) > 1.0:
            tlfractionx = 1.0 - self.viewfraction[0]

        if tlfractiony < 0:
            tlfractiony = 0.0
        elif (tlfractiony + self.viewfraction[1]) > 1.0:
            tlfractiony = 1.0 - self.viewfraction[1]

        self.tlfraction = [tlfractionx, tlfractiony]

    def zoomView(self, fraction):
        """
        zoom the view by fraction (positive 
        to zoom in)
        """
        # work out the centre of the window as a fraction
        centrefractionx = self.tlfraction[0] + (self.viewfraction[0] / 2.0)
        centrefractiony = self.tlfraction[1] + (self.viewfraction[1] / 2.0)

        # increase the view fraction by the required amount
        viewfractionx = self.viewfraction[0] * (1.0 + fraction)
        viewfractiony = self.viewfraction[1] * (1.0 + fraction)

        # work out what the tl fraction would be
        tlfractionx = centrefractionx - ( viewfractionx / 2.0 )
        tlfractiony = centrefractiony - ( viewfractiony / 2.0 )

        # bounds check
        if (tlfractionx + viewfractionx) > 1.0:
            tlfractionx = 1.0 - viewfractionx
        if tlfractionx < 0:
            tlfractionx = 0.0

        if (tlfractiony + viewfractiony) > 1.0:
            tlfractiony = 1.0 - viewfractiony
        if tlfractiony < 0:
            tlfractiony = 0.0

        if viewfractionx > 1.0:
            viewfractionx = 1.0
        if viewfractiony > 1.0:
            viewfractiony = 1.0


        self.tlfraction = [tlfractionx, tlfractiony]
        self.viewfraction = [viewfractionx, viewfractiony]


class OverviewInfo(object):
    """
    Stores size and index of an overview
    """
    def __init__(self, xsize, ysize, index):
        self.xsize = xsize
        self.ysize = ysize
        self.index = index

class OverviewManager(object):
    """
    This class contains a list of valid overviews
    and allows the best overview to be retrieved
    """
    def __init__(self):
        self.overviews = None
        self.aspectratio = None

    def loadOverviewInfo(self, ds, bands):
        """
        Load the overviews from the GDAL dataset into a list
        bands should be a list or tuple of band indices. 
        Checks are made that all lists bands contain the 
        same sized overviews
        """
        # i think we can assume that all the bands are the same size
        # add an info for the full res - this should always be location 0
        ovi = OverviewInfo(ds.RasterXSize, ds.RasterYSize, 0)
        self.overviews = [ovi]
        # store the aspect ratio - used elsewhere
        self.aspectratio = float(ovi.xsize) / float(ovi.ysize)

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
                # remember index 0 is full res so all real overviews are +1
                ovi = OverviewInfo(ov.XSize, ov.YSize, index + 1)
                self.overviews.append(ovi)

        # make sure they are sorted by area - biggest first
        self.overviews.sort(key=lambda ov: ov.xsize * ov.ysize, reverse=True)

    def findBestOverview(self, winxsize, winysize, viewfraction):
        """
        Finds the best overview for given window size and viewfraction
        """
        # convert to float so we don't need to do this each
        # time around the loop
        winxsize = float(winxsize)
        winysize = float(winysize)

        # start with the first, then try the others
        # if available
        # work out factor image res/window res
        # this needs to be greater or = 1.0 so there
        # is more image data than window data
        selectedovi = self.overviews[0]
        for ovi in self.overviews[1:]:
                xfactor = (ovi.xsize * viewfraction[0]) / winxsize
                if xfactor < 1.0:
                    break
                yfactor = (ovi.ysize * viewfraction[1]) / winysize
                if yfactor < 1.0:
                    break
                # got here overview must be ok
                selectedovi = ovi

        return selectedovi

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

        self.ds = None
        self.overviews = OverviewManager()
        self.lut = None # stretch is stored as a lookup table (0-255)
                        # 2d lookup array for single band images (BGRA)
                        # list of lut for each band for rgb
        self.bands = None
        self.mode = None
        self.image = None
        self.windowfraction = None

        # when moving the scroll bars
        # events get fired that we wish to ignore
        self.suppressscrollevent = False

    @staticmethod
    def createColorTableLUT(gdalband):
        """
        Creates a LUT for a single band using 
        the color table
        """
        ct = gdalband.GetColorTable()
        if ct is not None and ct.GetPaletteInterpretation() == gdal.GPI_RGB:
            # read in the colour table as lut
            ctcount = ct.GetCount()
            lut = numpy.empty((ctcount, 4), numpy.uint8)
            for i in range(ctcount):
                entry = ct.GetColorEntry(i)
                # entry is RGBA, need to store as BGRA
                lut[i] = (entry[2], entry[1], entry[0], entry[3])
            return lut
        else:
            msg = 'No color table present'
            raise viewererrors.InvalidColorTable(msg)

    @staticmethod
    def createStretchLUT(gdalband, stretchmode):
        """
        Creates a LUT for a single band using the stretch
        method specified
        """
        lutsize = 2 ** gdal.GetDataTypeSize(gdalband.DataType) 

        if stretchmode == VIEWER_STRETCHMODE_NONE:
            # just a linear stretch between 0 and 255
            # for the range of possible values
            lut = numpy.linspace(0, 255, num=lutsize).astype(numpy.uint8)
            return lut

        # following methods need stats
        # need to catch this failing and calc statistics
        # ourselves.
        # not sure what happens on failure. Exception?
        minVal, maxVal, mean, stdDev = gdalband.GetStatistics(0, 0)

        if stretchmode == VIEWER_STRETCHMODE_LINEAR:
            # just a linear stretch between 0 and 255
            # for the range of the data
            lut = numpy.empty(lutsize, numpy.uint8, 'C')
            values = numpy.arange(lutsize)

            minVal = int(minVal)
            maxVal = int(maxVal)
            lut = numpy.where(values < minVal, 0, lut)
            lut = numpy.where(values >= maxVal, 255, lut)
            mask = numpy.logical_and(values > minVal, values < maxVal)
            linstretch = numpy.linspace(0, 255, num=(maxVal-minVal)).astype(numpy.uint8)
            lut[minVal:maxVal] = linstretch
            return lut

        elif stretchmode == VIEWER_STRETCHMODE_2STDDEV:
            # linear stretch 2 std deviations from the mean
            stretchMin = mean - (2.0 * stdDev)
            if stretchMin < minVal:
                stretchMin = minVal
            stretchMax = mean + (2.0 * stdDev)
            if stretchMax > maxVal:
                stretchMax = maxVal

            stretchMin = int(stretchMin)
            stretchMax = int(stretchMax)

            lut = numpy.empty(lutsize, numpy.uint8, 'C')
            values = numpy.arange(lutsize)

            lut = numpy.where(values < stretchMin, 0, lut)
            lut = numpy.where(values >= stretchMax, 255, lut)
            mask = numpy.logical_and(values > stretchMin, values < stretchMax)
            linstretch = numpy.linspace(0, 255, num=(stretchMax-stretchMin)).astype(numpy.uint8)
            lut[stretchMin:stretchMax] = linstretch
            return lut

        elif stretchmode == VIEWER_STRETCHMODE_HIST:
            # must do progress
            numBins = int(numpy.ceil(maxVal - minVal))
            histo = gdalband.GetHistogram(min=minVal, max=maxVal, buckets=numBins, include_out_of_range=0, approx_ok=0)
            sumPxl = sum(histo)

            # Pete: what is this based on?
            bandLower = sumPxl * 0.025
            bandUpper = sumPxl * 0.01

            # calc min and max from histo
            # find bin number that bandLower/Upper fall into 
            # maybe we can do better with numpy?
            sumVals = 0
            for i in range(numBins):
                sumVals = sumVals + histo[i]
                if sumVals > bandLower:
                    stretchMin = minVal + ((maxVal - minVal) * (i / numBins))
                    break
            sumVals = 0
            for i in range(numBins):
                sumVals = sumVals + histo[-i]
                if sumVals > bandUpper:
                    stretchMax = maxVal + ((maxVal - minVal) * ((numBins - i - 1) / numBins))
                    break

            lut = numpy.empty(lutsize, numpy.uint8, 'C')
            values = numpy.arange(lutsize)

            lut = numpy.where(values < stretchMin, 0, lut)
            lut = numpy.where(values >= stretchMax, 255, lut)
            mask = numpy.logical_and(values > stretchMin, values < stretchMax)
            linstretch = numpy.linspace(0, 255, num=(stretchMax-stretchMin)).astype(numpy.uint8)
            lut[stretchMin:stretchMax] = linstretch
            return lut

        else:
            msg = 'unsupported stretch mode'
            raise viewererrors.InvalidParameters(msg)
        

    def open(self, fname, bands, mode, stretchmode=VIEWER_STRETCHMODE_NONE):
        """
        Displays the specified image using bands (a tuple of 1 based indices)
        and a specified mode (one of VIEWER_MODE_*) and a way of performing that mode
        (on of VIEWER_STRETCHMODE_*).
        This should be called after widget first shown to
        avoid unnecessary redraws
        """
        self.ds = gdal.Open(fname)

        # do some checks to see if we can deal with the data
        # currently only support square pixels and non rotated
        transform = self.ds.GetGeoTransform()
        if transform[2] != 0 or transform[4] != 0 or transform[1] != -transform[5]:
            msg = 'Only currently support square pixels and non-rotated images'
            raise viewererrors.InvalidDataset(msg)

        # not sure what floating point means for LUT
        # need to think about it
        dtype = self.ds.GetRasterBand(1).DataType
        if dtype == gdal.GDT_Float32 or dtype == gdal.GDT_Float64:
            msg = 'Only support integer types at present'
            raise viewererrors.InvalidDataset(msg)

        # load the valid overviews
        self.overviews.loadOverviewInfo(self.ds, bands)

        # reset these values
        self.windowfraction = WindowFraction()
        self.bands = bands
        self.mode = mode

        if mode == VIEWER_MODE_COLORTABLE:

            if len(bands) > 1:
                msg = 'specify one band when opening a color table image'
                raise viewererrors.InvalidParameters(msg)

            if stretchmode != VIEWER_STRETCHMODE_NONE:
                msg = 'stretchmode should be set to none for color tables'
                raise viewererrors.InvalidParameters(msg)

            band = bands[0]
            gdalband = self.ds.GetRasterBand(band)

            self.lut = self.createColorTableLUT(gdalband)

        elif mode == VIEWER_MODE_GREYSCALE:
            if len(bands) > 1:
                msg = 'specify one band when opening a greyscale image'
                raise viewererrors.InvalidParameters(msg)
            band = bands[0]
            gdalband = self.ds.GetRasterBand(band)

            lut = self.createStretchLUT( gdalband, stretchmode )
            alpha = numpy.zeros_like(lut) + 255
            # just repeat the lut for each color to make it grey
            # column_stack seems to create Fortran arrays which stuffs up
            # the creation of QImage's from it.
            self.lut = numpy.column_stack((lut, lut, lut, alpha)).copy('C')

        elif mode == VIEWER_MODE_RGB:
            if len(bands) != 3:
                msg = 'must specify 3 bands when opening rgb'
                raise viewererrors.InvalidParameters(msg)

            luts = []
            for band in bands:
                gdalband = self.ds.GetRasterBand(band)
                lut = self.createStretchLUT( gdalband, stretchmode )
                luts.append(lut)
            self.lut = luts
            
        else:
            msg = 'unsupported display mode'
            raise viewererrors.InvalidParameters(msg)

        # now go and retrieve the data for the image
        self.getData()

    
    def getData(self):
        """
        Called when new file opened, or resized,
        pan, zoom etc. Grabs data from the 
        appropriate overview and applies the lut 
        to it.
        """
        # if nothing open, don't bother
        if self.ds is None:
            return

        # the fraction we are displaying
        viewfraction = self.windowfraction.viewfraction
        tlfraction = self.windowfraction.tlfraction

        size = self.viewport().size()
        winxsize = size.width()
        winysize = size.height()


        # grab the best overview for the number of
        # pixels in the window
        selectedovi = self.overviews.findBestOverview(winxsize, winysize, viewfraction)
        print selectedovi.index

        x = int(selectedovi.xsize * tlfraction[0])
        y = int(selectedovi.ysize * tlfraction[1])
        xsize = int(selectedovi.xsize * viewfraction[0])
        ysize = int(selectedovi.ysize * viewfraction[1])

        totalx = x + xsize
        if totalx > selectedovi.xsize:
            x -= (totalx - selectedovi.xsize)
        totaly = y + ysize
        if totaly > selectedovi.ysize:
            y -= (totaly - selectedovi.ysize)

        if self.mode == VIEWER_MODE_RGB:

            # have to read 3 layers in
            # must be more efficient way

            bgra = numpy.empty((winysize, winxsize, 4), numpy.uint8)
            lutindex = 0
            for bandnum in self.bands:
                band = self.ds.GetRasterBand(bandnum)
                if selectedovi.index > 0:
                    band = band.GetOverview(selectedovi.index - 1)

                data = band.ReadAsArray(x, y, xsize, ysize, winxsize, winysize )
                # apply the lut on this band
                bandbgra = self.lut[lutindex][data]
                bgra[...,lutindex] = bandbgra
                lutindex += 1

            bgra[...,3].fill(255)   # alpha for rgb? set to 255

        else:
            # must be single band
            band = self.ds.GetRasterBand(self.bands[0])
            if selectedovi.index > 0:
                band = band.GetOverview(selectedovi.index - 1)

            data = band.ReadAsArray(x, y, xsize, ysize, winxsize, winysize )

            # Qt expects 32bit BGRA data for color images
            # our lut is already set up for this
            bgra = self.lut[data]

        # create QImage from numpy array
        # see http://www.mail-archive.com/pyqt@riverbankcomputing.com/msg17961.html
        self.image = QImage(bgra.data, winxsize, winysize, QImage.Format_RGB32)
        self.image.ndarray = data # hold on to the data in case we
                            # want to change the lut and quickly re-apply it

        # reset the scroll bars for new extent of window
        # need to suppress processing of new scroll bar
        # events otherwise we end up in endless loop
        self.suppressscrollevent = True
        self.horizontalScrollBar().setPageStep(xsize)
        self.verticalScrollBar().setPageStep(ysize)
        self.horizontalScrollBar().setRange(0, selectedovi.xsize - xsize)
        self.verticalScrollBar().setRange(0, selectedovi.ysize - ysize)
        self.horizontalScrollBar().setSliderPosition(x)
        self.verticalScrollBar().setSliderPosition(y)
        self.suppressscrollevent = False

        # force repaint
        self.viewport().update()        
        
    def scrollContentsBy(self, dx, dy):
        """
        Handle the user moving the scroll bars
        """
        if not self.suppressscrollevent:
            xamount = dx * -VIEWER_SCROLL_MULTIPLIER * self.windowfraction.viewfraction[0]
            yamount = dy * -VIEWER_SCROLL_MULTIPLIER * self.windowfraction.viewfraction[1]
            self.windowfraction.moveView(xamount, yamount)

            self.getData()

    def wheelEvent(self, event):
        """
        User has used mouse wheel to zoom in/out
        """
        if event.delta() > 0:
            self.windowfraction.zoomView(-VIEWER_ZOOM_FRACTION)
        elif event.delta() < 0:
            self.windowfraction.zoomView(VIEWER_ZOOM_FRACTION)
        self.getData()

    def resizeEvent(self, event):
        """
        Window has been resized - get new data
        """
        oldsize = event.oldSize()
        newsize = event.size()
        # only bother grabbing more data
        # if the area has got bigger
        # the paint will just ignore the extra data if
        # it is now smaller
        if newsize.width() > oldsize.width() or newsize.height() > oldsize.height():
            self.getData()
                    

    def paintEvent(self, event):
        """
        Viewport needs to be redrawn. Assume that 
        self.image is current (as created by getData())
        we can just draw it with QPainter
        """
        if self.image is not None:
            paint = QPainter(self.viewport())
            paint.drawImage(0,0,self.image)
            paint.end()
