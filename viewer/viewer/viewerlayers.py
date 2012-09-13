
"""
this module contains the LayerManager and related classes
"""

import numpy
from osgeo import gdal
from osgeo import osr
from PyQt4.QtGui import QImage, QPainter, QPen
from PyQt4.QtCore import QObject, SIGNAL

from . import viewerRAT
from . import viewerLUT
from . import viewerstretch
from . import coordinatemgr
from . import viewererrors

QUERY_CURSOR_HALFSIZE = 8 # number of pixels
QUERY_CURSOR_WIDTH = 1 # in pixels

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
    for (numpy_type, test_gdal_type) in dataTypeMapping:
        if test_gdal_type == gdaltype:
            return numpy_type
    raise viewererrors.TypeConversionError("Unknown GDAL datatype: %s"%gdaltype)

def NumpyTypeToGDALType(numpytype):
    """
    For a given numpy data type returns the matching
    GDAL data type
    """
    for (test_numpy_type, gdaltype) in dataTypeMapping:
        if test_numpy_type == numpytype:
            return gdaltype
    msg = "Unknown numpy datatype: %s" % numpytype
    raise viewererrors.TypeConversionError(msg)

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
        "Get the full res overview - ie the non overview image"
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
                fullrespixperpix = float(ds.RasterXSize) / float(ov.XSize) 
                # should do both ways?
                # remember index 0 is full res so all real overviews are +1
                ovi = OverviewInfo(ov.XSize, ov.YSize, fullrespixperpix, 
                                            index + 1)
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

class ViewerLayer(object):
    """
    Base class for a type of layer
    """
    def __init__(self):
        self.image = None
        self.filename = None
        self.displayed = True

    def getImage(self):
        "return a QImage with the data in it"
        raise NotImplementedError("Must implement in derived class")

    def getPropertiesString(self):
        "Return the properties as a string we can show the user"
        raise NotImplementedError("Must implement in derived class")

class ViewerRasterLayer(ViewerLayer):
    """
    Represents a raster layer
    """
    def __init__(self, layermanager):
        ViewerLayer.__init__(self)
        self.coordmgr = coordinatemgr.RasterCoordManager()
        self.gdalDataset = None
        self.transform = None
        self.bandNames = None
        self.wavelengths = None
        self.noDataValues = None
        self.attributes = viewerRAT.ViewerRAT()
        self.overviews = OverviewManager()
        self.lut = viewerLUT.ViewerLUT()
        self.stretch = None

        # connect the signals from the RAT and LUT back to the layermanager
        layermanager.connect(self.lut, SIGNAL("newProgress(QString)"), 
                                                    layermanager.newProgress)
        layermanager.connect(self.lut, SIGNAL("endProgress()"), 
                                                    layermanager.endProgress)
        layermanager.connect(self.lut, SIGNAL("newPercent(int)"), 
                                                    layermanager.newPercent)

        layermanager.connect(self.attributes, SIGNAL("newProgress(QString)"), 
                                                    layermanager.newProgress)
        layermanager.connect(self.attributes, SIGNAL("endProgress()"), 
                                                    layermanager.endProgress)
        layermanager.connect(self.attributes, SIGNAL("newPercent(int)"), 
                                                    layermanager.newPercent)


    def open(self, filename, width, height, stretch, lut=None):
        """
        Open a filename as a raster layer. width and height is the
        display size. stretch is the ViewerStretch instance to use.
        if specified, the lut is used to display the data, otherwise
        calculated from the stretch
        """
        # open the file
        self.filename = filename
        self.gdalDataset = gdal.Open(filename)

        # do some checks to see if we can deal with the data
        # currently only support square pixels and non rotated
        transform = self.gdalDataset.GetGeoTransform()
        if (transform[2] != 0 or transform[4] != 0 or 
                            transform[1] != -transform[5]):
            msg = 'Only currently support square pixels and non-rotated images'
            raise viewererrors.InvalidDataset(msg)
        self.transform = transform

        # store the stretch
        self.stretch = stretch

        # load the valid overviews
        self.overviews.loadOverviewInfo(self.gdalDataset, stretch.bands)

        # reset these values
        firstoverview = self.overviews.getFullRes()
        self.coordmgr.setDisplaySize(width, height)
        self.coordmgr.setGeoTransformAndSize(transform, firstoverview.xsize, 
                                                firstoverview.ysize)
        # This may be changed by the LayerManager if there are other layers
        self.coordmgr.setTopLeftPixel(0, 0)  
        self.coordmgr.calcZoomFactor(firstoverview.xsize, firstoverview.ysize)

        # if we are single band read attributes if any
        if len(stretch.bands) == 1:
            gdalband = self.gdalDataset.GetRasterBand(stretch.bands[0])
            self.attributes.readFromGDALBand(gdalband)
            if self.attributes.hasAttributes():
                # tell stretch to create same size as attribute table
                self.stretch.setAttributeTableSize(self.attributes.getNumRows())
        else:
            # keep blank
            self.attributes.clear()

        # read in the LUT if not specified
        if lut is None:
            self.lut.createLUT(self.gdalDataset, stretch)
        else:
            self.lut = lut

        # grab the band names
        self.bandNames = self.getBandNames()

        # grab the wavelengths
        self.wavelengths = self.getWavelengths()

        # the no data values for each band
        self.noDataValues = self.getNoDataValues()

    def getBandNames(self):
        """
        Return the list of band names
        """
        bandNames = []
        for n in range(self.gdalDataset.RasterCount):
            band = self.gdalDataset.GetRasterBand(n+1)
            name = band.GetDescription()
            bandNames.append(name)
        return bandNames
        
    def getWavelengths(self):
        """
        Return the list of wavelength if file
        conforms to the metadata provided by the 
        ENVI driver, or None.
        Other formats will be added in future.
        """
        wavelengths = []
        ok = False

        drivername = self.gdalDataset.GetDriver().ShortName
        if drivername == 'ENVI':
            ok = True
            # GetMetadataItem seems buggy for ENVI
            # get the lot and go through
            meta = self.gdalDataset.GetMetadata()
            # go through each band
            for n in range(self.gdalDataset.RasterCount):
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
        for n in range(self.gdalDataset.RasterCount):
            band = self.gdalDataset.GetRasterBand(n+1)
            value = band.GetNoDataValue() # returns None if not set
            noData.append(value)
        return noData

    def highlightRows(self, color, selectionArray=None):
        """
        Highlight selected rows in the LUT
        """
        self.lut.highlightRows(color, selectionArray)
        # re-apply the lut to the data from last time
        self.image = self.lut.applyLUTSingle(self.image.viewerdata, 
                                                self.image.viewermask)

    def setNewStretch(self, newstretch, local=False):
        """
        Set the new stretch
        """
        newbands = self.stretch.bands != newstretch.bands
        if newbands:
            # only need to do this if bands have changed
            self.overviews.loadOverviewInfo(self.gdalDataset, newstretch.bands)

        image = None
        if local and not newbands:
            # we can just grab the stats from the last read
            image = self.image

        # if we have an attribute table create stretch same size
        if self.attributes.hasAttributes():
            newstretch.setAttributeTableSize(self.attributes.getNumRows())

        self.lut.createLUT(self.gdalDataset, newstretch, image)

        self.stretch = newstretch
        # note - we need to do this to reapply the stretch
        # but it re-reads the data always.
        # not sure it is a big deal since GDAL caches
        self.getImage()

        if local and newbands:
            # this is a bit of a hack. We needed to do a 
            # getData to get the new bands loaded. Now
            # we can get the stats and apply the stretch locally
            self.lut.createLUT(self.gdalDataset, newstretch, self.image)
            self.getImage()

    def saveStretchToFile(self, stretch):
        """
        Saves the given stretch and current LUT to the file
        """
        # ok we need to close the current file handle and re-open in write mode
        del self.gdalDataset
        try:
            # now open as writeable
            dataset = gdal.Open(self.filename, gdal.GA_Update)

            # write the stretch
            stretch.writeToGDAL(dataset)

            # write the LUT
            self.lut.writeToGDAL(dataset)

            # close this (writeable) file handle
            del dataset
        except RuntimeError:
            raise viewererrors.InvalidDataset('Unable to save stretch to file')
        finally:
            # attempt to open the file readonly again
            self.gdalDataset = gdal.Open(self.filename)

    def deleteStretchFromFile(self):
        """
        deletes the stretch and current LUT from the file
        """
        # ok we need to close the current file handle and re-open in write mode
        del self.gdalDataset
        try:
            # now open as writeable
            dataset = gdal.Open(self.filename, gdal.GA_Update)

            # delete the stretch
            viewerstretch.ViewerStretch.deleteFromGDAL(dataset)

            # delete the LUT
            viewerLUT.ViewerLUT.deleteFromGDAL(dataset)

            # close this (writeable) file handle
            del dataset
        except RuntimeError:
            msg = 'Unable to delete stretch from file'
            raise viewererrors.InvalidDataset(msg)
        finally:
            # attempt to open the file readonly again
            self.gdalDataset = gdal.Open(self.filename)

    def writeDirtyRATColumns(self):
        """
        calls self.attributes.writeDirtyColumns on the band opening
        the file in update mode first.
        """
        # close the current file handle and re-open in write mode
        del self.gdalDataset
        try:
            # now open as writeable
            dataset = gdal.Open(self.filename, gdal.GA_Update)

            gdalband = dataset.GetRasterBand(self.stretch.bands[0])
            self.attributes.writeDirtyColumns(gdalband)
            # close this (writeable) file handle
            del dataset
        except RuntimeError:
            msg = 'Unable to save columns'
            raise viewererrors.InvalidDataset(msg)
        finally:
            # attempt to open the file readonly again
            self.gdalDataset = gdal.Open(self.filename)


    def writeRATColumnOrder(self):
        """
        calls self.attributes.writeColumnOrderToGDAL on the band opening
        the file in update mode first.
        """
        # close the current file handle and re-open in write mode
        del self.gdalDataset
        try:
            # now open as writeable
            dataset = gdal.Open(self.filename, gdal.GA_Update)

            gdalband = dataset.GetRasterBand(self.stretch.bands[0])
            self.attributes.writeColumnOrderToGDAL(gdalband)
            # close this (writeable) file handle
            del dataset
        except RuntimeError:
            msg = 'Unable to save column order'
            raise viewererrors.InvalidDataset(msg)
        finally:
            # attempt to open the file readonly again
            self.gdalDataset = gdal.Open(self.filename)

    def getImage(self):
        """
        Refresh the 'image' which is a QImage instance used for rendering.
        Does the selection of overview, choosing of area (based on coordmgr)
        reading, and applying LUT.
        """
        # find the best overview based on imgpixperwinpix
        imgpix = self.coordmgr.imgPixPerWinPix
        nf_selectedovi = self.overviews.findBestOverview(imgpix)
        print nf_selectedovi.index

        # if this layer isn't anywhere near where we currently are
        # don't even bother reading - just create a empty QImage
        # and nothing will be rendered
        if self.coordmgr.pixTop < 0 and self.coordmgr.pixBottom < 0:
            self.image = QImage()
            return 
        elif self.coordmgr.pixLeft < 0 and self.coordmgr.pixRight < 0:
            self.image = QImage()
            return
        elif (self.coordmgr.pixLeft > self.gdalDataset.RasterXSize and 
                    self.coordmgr.pixRight > self.gdalDataset.RasterXSize):
            self.image = QImage()
            return
        elif (self.coordmgr.pixTop > self.gdalDataset.RasterYSize and 
                    self.coordmgr.pixBottom > self.gdalDataset.RasterYSize):
            self.image = QImage()
            return
        
        nf_fullrespixperovpix = nf_selectedovi.fullrespixperpix
        pixTop = max(self.coordmgr.pixTop, 0)
        pixLeft = max(self.coordmgr.pixLeft, 0)
        #print 'pixTop', pixTop, pixLeft, pixTop / nf_fullrespixperovpix
        pixBottom = min(self.coordmgr.pixBottom, self.gdalDataset.RasterYSize-1)
        pixRight = min(self.coordmgr.pixRight, self.gdalDataset.RasterXSize-1)
        nf_ovtop = int(pixTop / nf_fullrespixperovpix)
        nf_ovleft = int(pixLeft / nf_fullrespixperovpix)
        nf_ovbottom = int(numpy.ceil(pixBottom / nf_fullrespixperovpix))
        nf_ovright = int(numpy.ceil(pixRight / nf_fullrespixperovpix))
        nf_ovtop = max(nf_ovtop, 0)
        nf_ovleft = max(nf_ovleft, 0)
        nf_ovbottom = min(nf_ovbottom, nf_selectedovi.ysize-1)
        nf_ovright = min(nf_ovright, nf_selectedovi.xsize-1)
        nf_ovxsize = nf_ovright - nf_ovleft + 1
        nf_ovysize = nf_ovbottom - nf_ovtop + 1

        #ovPixPerWinPix = self.coordmgr.imgPixPerWinPix / nf_fullrespixperovpix
        #print 'ovPixPerWinPix', ovPixPerWinPix, pixTop, pixLeft
        #nf_ovbuffxsize = int(numpy.ceil(float(nf_ovxsize) / ovPixPerWinPix))
        #nf_ovbuffysize = int(numpy.ceil(float(nf_ovysize) / ovPixPerWinPix))

        # The display coordinates of the top-left corner of the raster data.
        #  Often this
        # is (0, 0), but need not be if there is blank area left/above the 
        # raster data
        (nf_dspRastLeft, nf_dspRastTop) = self.coordmgr.pixel2display(
                                                        pixLeft, pixTop)
        (nf_dspRastRight, nf_dspRastBottom) = self.coordmgr.pixel2display(
                                                        pixRight, pixBottom)
        nf_dspRastXSize = nf_dspRastRight - nf_dspRastLeft 
        nf_dspRastYSize = nf_dspRastBottom - nf_dspRastTop 

        if self.coordmgr.imgPixPerWinPix < 1:
            # need to calc 'extra' around the edge as we have partial pixels
            # GDAL reads in full pixels
            (nf_dspRastAbsLeft, nf_dspRastAbsTop) = self.coordmgr.pixel2display(
                                    numpy.floor(pixLeft), numpy.floor(pixTop))
            (nf_dspRastAbsRight, nf_dspRastAbsBottom) = (
                    self.coordmgr.pixel2display(
                    numpy.ceil(pixRight), numpy.ceil(pixBottom)))
            nf_dspLeftExtra = ((nf_dspRastLeft - nf_dspRastAbsLeft) 
                                    / nf_fullrespixperovpix)
            nf_dspTopExtra = ((nf_dspRastTop - nf_dspRastAbsTop) 
                                    / nf_fullrespixperovpix)
            nf_dspRightExtra = ((nf_dspRastAbsRight - nf_dspRastRight) 
                                    / nf_fullrespixperovpix)
            nf_dspBottomExtra = ((nf_dspRastAbsBottom - nf_dspRastBottom) 
                                    / nf_fullrespixperovpix)


        # only need to do the mask once
        mask = numpy.empty((self.coordmgr.dspHeight, self.coordmgr.dspWidth), 
                                    dtype=numpy.uint8)
        mask.fill(viewerLUT.MASK_BACKGROUND_VALUE) # set to background
        
        dataslice = (slice(nf_dspRastTop, nf_dspRastTop+nf_dspRastYSize),
            slice(nf_dspRastLeft, nf_dspRastLeft+nf_dspRastXSize))
        mask[dataslice] = viewerLUT.MASK_IMAGE_VALUE # 0 where there is data
        nodata_mask = None

        if len(self.stretch.bands) == 3:
            # rgb
            datalist = []
            for bandnum in self.stretch.bands:
                band = self.gdalDataset.GetRasterBand(bandnum)

                # create blank array of right size to read in to. This data
                # array represents the window pixels, one-for-one
                numpytype = GDALTypeToNumpyType(band.DataType)
                shape = (self.coordmgr.dspHeight, self.coordmgr.dspWidth)
                data = numpy.zeros(shape, dtype=numpytype) 

                # get correct overview
                if nf_selectedovi.index > 0:
                    band = band.GetOverview(nf_selectedovi.index - 1)

                # read into correct part of our window array
                if self.coordmgr.imgPixPerWinPix >= 1.0:
                    dataTmp = band.ReadAsArray(nf_ovleft, nf_ovtop, 
                        nf_ovxsize, nf_ovysize,
                        nf_dspRastXSize, nf_dspRastYSize)
                    #print dataTmp.shape, dataslice
                    data[dataslice] = dataTmp
                else:
                    dataTmp = band.ReadAsArray(nf_ovleft, nf_ovtop, 
                                    nf_ovxsize, nf_ovysize)
                    #print 'repl', dataTmp.shape, dataslice
                    data[dataslice] = replicateArray(dataTmp, data[dataslice], 
                        nf_dspLeftExtra, nf_dspTopExtra, nf_dspRightExtra, 
                            nf_dspBottomExtra)
                    
                # do the no data test
                nodata_value = self.noDataValues[bandnum-1]
                if nodata_value is not None:
                    inimage_and_nodata = numpy.logical_and(
                            mask == viewerLUT.MASK_IMAGE_VALUE, 
                            data == nodata_value)
                    if nodata_mask is None:
                        nodata_mask = inimage_and_nodata
                    else:
                        # should it be 'or' or 'and' ?
                        nodata_mask = numpy.logical_and(nodata_mask, 
                                        inimage_and_nodata)

                datalist.append(data)

            # apply the no data
            if nodata_mask is not None:
                mask = numpy.where(nodata_mask, viewerLUT.MASK_NODATA_VALUE, 
                                        mask)

            # apply LUT
            self.image = self.lut.applyLUTRGB(datalist, mask)

        else:
            # must be single band
            band = self.gdalDataset.GetRasterBand(self.stretch.bands[0])

            # create blank array of right size to read in to
            numpytype = GDALTypeToNumpyType(band.DataType)
            shape = (self.coordmgr.dspHeight, self.coordmgr.dspWidth)
            data = numpy.zeros(shape, dtype=numpytype) 

            # get correct overview
            if nf_selectedovi.index > 0:
                band = band.GetOverview(nf_selectedovi.index - 1)

            # read into correct part of our window array
            if self.coordmgr.imgPixPerWinPix >= 1.0:
                data[dataslice] = band.ReadAsArray(nf_ovleft, nf_ovtop, 
                    nf_ovxsize, nf_ovysize,
                    nf_dspRastXSize, nf_dspRastYSize)
            else:
                dataTmp = band.ReadAsArray(nf_ovleft, nf_ovtop, 
                        nf_ovxsize, nf_ovysize)
                data[dataslice] = replicateArray(dataTmp, data[dataslice], 
                    nf_dspLeftExtra, nf_dspTopExtra, nf_dspRightExtra,
                         nf_dspBottomExtra)

            # do we have no data for this band?
            nodata_value = self.noDataValues[self.stretch.bands[0] - 1]
            if nodata_value is not None:
                inimage_and_nodata = numpy.logical_and(
                        mask == viewerLUT.MASK_IMAGE_VALUE, 
                        data == nodata_value)
                mask = numpy.where(inimage_and_nodata, 
                        viewerLUT.MASK_NODATA_VALUE, 
                        mask)

            # apply LUT
            self.image = self.lut.applyLUTSingle(data, mask)

    def getPropertiesString(self):
        """
        Get the properties of the file as a string for presentation to user.
        Do something similar to gdalinfo.
        """
        fmt = """Driver: %s
Files: %s
Size is %d, %d
Number of Bands: %d
Coordinate System is:\n%s
Origin = (%f,%f)
Pixel Size = (%f,%f)
Corner Coordinates:
Upper Left  ( %f, %f)
Lower Left  ( %f, %f)
Upper Right ( %f, %f)
Lower Right ( %f, %f)
Center      ( %f, %f)
"""
        driver = self.gdalDataset.GetDriver()
        driverString = "%s/%s" % (driver.ShortName, driver.LongName)
        fileString = " ".join(self.gdalDataset.GetFileList())
        proj = self.gdalDataset.GetProjection()
        sr = osr.SpatialReference(proj)
        coordString = sr.ExportToPrettyWkt()

        (ulx, uly) = self.coordmgr.pixel2world(0, 0)
        (llx, lly) = self.coordmgr.pixel2world(0, self.gdalDataset.RasterYSize)
        (urx, ury) = self.coordmgr.pixel2world(self.gdalDataset.RasterYSize, 0)
        (lrx, lry) = self.coordmgr.pixel2world(self.gdalDataset.RasterYSize, 
                                                self.gdalDataset.RasterYSize)
        (cx, cy) = self.coordmgr.pixel2world(
                                        self.gdalDataset.RasterYSize / 2.0, 
                                        self.gdalDataset.RasterYSize / 2.0)
        
        propstr = fmt % (driverString, fileString, 
                        self.gdalDataset.RasterXSize, 
                        self.gdalDataset.RasterYSize,
                    self.gdalDataset.RasterCount, coordString, 
                    self.transform[0], self.transform[3],
                    self.transform[1], self.transform[5], 
                    ulx, uly, llx, lly, urx, ury, lrx, lry, cx, cy)
        return propstr

class ViewerQueryPointLayer(ViewerLayer):
    """
    Class for display of query points.
    """
    def __init__(self):
        ViewerLayer.__init__(self)
        self.coordmgr = coordinatemgr.VectorCoordManager()
        self.queryPoints = {}
        self.image = None

    def setQueryPoint(self, senderid, easting, northing, color,
                            size=QUERY_CURSOR_HALFSIZE):
        """
        Add/replace a query point based on the id() of the requesting object
        """
        self.queryPoints[senderid] = (easting, northing, color, size)

    def removeQueryPoint(self, senderid):
        """
        remove a query point based on the id() of the requesting object
        """
        del self.queryPoints[senderid]

    def getImage(self):
        """
        Update self.image
        """
        if self.coordmgr.dspWidth is None:
            self.image = QImage()
        else:
            self.image = QImage(self.coordmgr.dspWidth, 
                    self.coordmgr.dspHeight, QImage.Format_ARGB32)
            self.image.fill(0)
            pen = QPen()
            pen.setWidth(QUERY_CURSOR_WIDTH)
            paint = QPainter(self.image)
            for senderid in self.queryPoints:
                (easting, northing, color, size) = self.queryPoints[senderid]
                display = self.coordmgr.world2display(easting, northing)
                if display is not None:
                    (dspX, dspY) = display
                    dspX = int(dspX)
                    dspY = int(dspY)
                    pen.setColor(color)
                    paint.setPen(pen)
                    paint.drawLine(dspX - size, dspY, dspX + size, dspY)
                    paint.drawLine(dspX, dspY - size, dspX, dspY + size)
            paint.end()
                
                

class ViewerVectorLayer(ViewerLayer):
    """
    A vector layer. I don't do much with this yet...
    """
    def __init__(self):
        ViewerLayer.__init__(self)
        self.ogrDataset = None
        self.coordmgr = coordinatemgr.VectorCoordManager()

class LayerManager(QObject):
    """
    Class that manages a list of layers
    """
    def __init__(self):
        QObject.__init__(self)
        self.layers = []
        self.fullextent = None
        self.queryPointLayer = ViewerQueryPointLayer()

    def getFullExtent(self):
        """
        Return the full extent for all the open layers
        """
        return self.fullextent

    def recalcFullExtent(self):
        """
        Internal method. Recalculates the full extent of all
        the layers. Called when dataset added or removed.
        """
        self.fullextent = None
        for layer in self.layers:
            extent = layer.coordmgr.getFullWorldExtent()
            if extent is not None:
                if self.fullextent is None:
                    self.fullextent = extent
                else:
                    (left, top, right, bottom) = self.fullextent
                    (newleft, newtop, newright, newbottom) = extent
                    if newleft < left:
                        left = newleft
                    if newtop > top:
                        top = newtop
                    if newright > right:
                        right = newright
                    if newbottom < bottom:
                        bottom = newbottom
                    self.fullextent = (left, top, right, bottom)

    def setDisplaySize(self, width, height):
        """
        When window resized this updates all the layers
        """
        for layer in self.layers:
            layer.coordmgr.setDisplaySize(width, height)
            layer.coordmgr.recalcBottomRight()
        self.queryPointLayer.coordmgr.setDisplaySize(width, height)
        self.updateImages()

    @staticmethod
    def isSameRasterProjection(layer1, layer2):
        """
        Checks to see if 2 raster layers have the same projection
        """
        proj1 = layer1.gdalDataset.GetProjection()
        proj2 = layer2.gdalDataset.GetProjection()
        sr1 = osr.SpatialReference(proj1)
        sr2 = osr.SpatialReference(proj2)
        return bool(sr1.IsSame(sr2))

    def addRasterLayer(self, filename, width, height, stretch, lut=None):
        """
        Add a new raster layer with given display width and height, stretch
        and optional lut.
        """
        # create and open
        layer = ViewerRasterLayer(self)
        layer.open(filename, width, height, stretch, lut)

        if len(self.layers) > 0:
            # get the existing extent
            extent = self.layers[-1].coordmgr.getWorldExtent()
            layer.coordmgr.setWorldExtent(extent)

        # if there is an existing raster layer, check we have an equivalent
        # projection. Perhaps we should do similar if there is a vector layer. 
        # Not sure.
        existinglayer = self.getTopRasterLayer()
        if existinglayer is not None:
            if not self.isSameRasterProjection(layer, existinglayer):
                raise viewererrors.InvalidDataset('projections do not match')
        
        # ensure the query points have the correct extent
        extent = layer.coordmgr.getWorldExtent()
        self.queryPointLayer.coordmgr.setWorldExtent(extent)

        layer.getImage()
        self.layers.append(layer)
        self.recalcFullExtent()
        self.emit(SIGNAL("layersChanged()"))

    def addVectorLayer(self, filename, color):
        """
        Add a vector layer. Don't do much here yet...
        """
        self.recalcFullExtent()
        self.emit(SIGNAL("layersChanged()"))

    def removeTopLayer(self):
        """
        Removes the top layer
        """
        if len(self.layers) > 0:
            self.layers.pop()
            self.recalcFullExtent()
            self.emit(SIGNAL("layersChanged()"))

    def removeLayer(self, layer):
        """
        Remove the specified layer
        """
        self.layers.remove(layer)
        self.recalcFullExtent()
        self.emit(SIGNAL("layersChanged()"))

    def moveLayerUp(self, layer):
        """
        Move the specified layer 'up' - ie
        render it later which is actually down the list
        """
        index = self.layers.index(layer)
        if index < len(self.layers) - 1:
            self.layers.pop(index)
            self.layers.insert(index + 1, layer)
            self.emit(SIGNAL("layersChanged()"))

    def moveLayerDown(self, layer):
        """
        Move the specified layer 'down' - ie
        render it later which is actually up the list
        """
        index = self.layers.index(layer)
        if index > 0:
            self.layers.pop(index)
            self.layers.insert(index - 1, layer)
            self.emit(SIGNAL("layersChanged()"))

    def getTopLayer(self):
        "Returns the very top layer which may be raster or vector"
        layer = None
        if len(self.layers) > 0:
            layer = self.layers[-1]
        return layer

    def getTopRasterLayer(self):
        """
        Returns the top most raster layer
        (if there is one) otherwise None
        """
        rasterLayer = None
        for layer in reversed(self.layers):
            if isinstance(layer, ViewerRasterLayer):
                rasterLayer = layer
                break
        return rasterLayer

    def getTopVectorLayer(self):
        """
        Returns the top most vector layer
        (if there is one) otherwise None
        """
        vectorLayer = None
        for layer in reversed(self.layers):
            if isinstance(layer, ViewerVectorLayer):
                vectorLayer = layer
                break
        return vectorLayer

    def updateImages(self):
        """
        Tell each of the layers to get a new
        'image' for rendering. This is called
        when extents have changed etc.
        """
        for layer in self.layers:
            layer.getImage()
        self.queryPointLayer.getImage()

    def makeLayersConsistent(self, reflayer):
        """
        Make all layers spatially consistent with reflayer
        """
        extent = reflayer.coordmgr.getWorldExtent()        

        for layer in self.layers:
            if not reflayer is layer:
                layer.coordmgr.setWorldExtent(extent)
        self.queryPointLayer.coordmgr.setWorldExtent(extent)

    def zoomNativeResolution(self):
        """
        Zoom to the native resolution of the top
        raster later
        """
        layer = self.getTopRasterLayer()
        if layer is not None:
            # take care to preserve the center
            (wldX, wldY) = layer.coordmgr.getWorldCenter()
            layer.coordmgr.setZoomFactor(1.0)
            layer.coordmgr.setWorldCenter(wldX, wldY)
            self.makeLayersConsistent(layer)
            self.updateImages()

    def zoomFullExtent(self):
        """
        Zoom to the full extent of all the layers
        This might need a re-think for vectors.
        """
        layer = self.getTopLayer()
        if layer is not None and self.fullextent is not None:
            layer.coordmgr.setWorldExtent(self.fullextent)
            self.makeLayersConsistent(layer)
            self.updateImages()

    # the following functions are needed as this class
    # acts as a 'proxy' between the RAT and LUT's inside
    # the individual layers and anything wanting to listen
    # to the progress (the window in this case)
    def newProgress(self, string):
        """
        Called when we are about to start a new progress
        """
        self.emit(SIGNAL("newProgress(QString)"), string)

    def endProgress(self):
        """
        Called when a progress run has finished
        """
        self.emit(SIGNAL("endProgress()"))

    def newPercent(self, percent):
        """
        New progress value
        """
        self.emit(SIGNAL("newPercent(int)"), percent)


def replicateArray(arr, outarr, dspLeftExtra, dspTopExtra, dspRightExtra, 
                            dspBottomExtra):
    """
    Replicate the data in the given 2-d array so that it increases
    in size to be (ysize, xsize). 
    
    Replicates each pixel in both directions. 
    
    xfract and yfract is the fracton of the first pixel that needs to 
    be removed
    because GDAL always reads in first pixel. This is taken out of the 
    repeated values of the first pixel.
    """
    (ysize, xsize) = outarr.shape
    (nrows, ncols) = arr.shape
    nRptsX = float(xsize + dspLeftExtra + dspRightExtra) / float(ncols)
    nRptsY = float(ysize + dspTopExtra + dspBottomExtra) / float(nrows)
    #print 'replicateArray', ysize, xsize, nrows, ncols, nRptsX, nRptsY

    rowCount = int(numpy.ceil(nrows * nRptsY)) * 1j
    colCount = int(numpy.ceil(ncols * nRptsX)) * 1j
    
    # create the lookup table (up to nrows/ncols-1)
    (row, col) = (
       numpy.mgrid[0:nrows-1:rowCount, 0:ncols-1:colCount].astype(numpy.int32))
    # do the lookup
    outarr = arr[row, col]

    # chop out the extra pixels
    outarr = (
       outarr[dspTopExtra:dspTopExtra+ysize, dspLeftExtra:dspLeftExtra+xsize])

    return outarr





