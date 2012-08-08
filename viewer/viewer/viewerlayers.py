
"""
this module contains the LayerManager and related classes
"""

import numpy
from osgeo import gdal

from . import viewerRAT
from . import viewerLUT
from . import coordinatemgr

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

class ViewerLayer(object):
    """
    Base class for a type of layer
    """
    def __init__(self):
        self.image = None
        self.filename = None

class ViewerRasterLayer(ViewerLayer):
    """
    Represents a raster layer
    """
    def __init__(self):
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
        # TODO check WKT matches other layers

        # do some checks to see if we can deal with the data
        # currently only support square pixels and non rotated
        transform = self.gdalDataset.GetGeoTransform()
        if transform[2] != 0 or transform[4] != 0 or transform[1] != -transform[5]:
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
        self.coordmgr.setGeoTransform(transform)
        self.coordmgr.setTopLeftPixel(0, 0)  # This may be changed by the LayerManager if there are other layers
        self.coordmgr.calcZoomFactor(firstoverview.xsize, firstoverview.ysize)

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
        layer.lut.highlightRows(color, selectionArray)
        # re-apply the lut to the data from last time
        self.image = self.lut.applyLUTSingle(self.image.viewerdata, self.image.viewermask)

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

    def getImage(self):
        """
        Refresh the 'image' which is a QImage instance used for rendering.
        Does the selection of overview, choosing of area (based on coordmgr)
        reading, and applying LUT.
        """
        # find the best overview based on imgpixperwinpix
        nf_selectedovi = self.overviews.findBestOverview(self.coordmgr.imgPixPerWinPix)
        
        nf_fullrespixperovpix = nf_selectedovi.fullrespixperpix
        pixTop = max(self.coordmgr.pixTop, 0)
        pixLeft = max(self.coordmgr.pixLeft, 0)
        pixBottom = min(self.coordmgr.pixBottom, self.gdalDataset.RasterYSize-1)
        pixRight = min(self.coordmgr.pixRight, self.gdalDataset.RasterXSize-1)
        nf_ovtop = int(pixTop / nf_fullrespixperovpix)
        nf_ovleft = int(pixLeft / nf_fullrespixperovpix)
        nf_ovbottom = int(pixBottom / nf_fullrespixperovpix)
        nf_ovright = int(pixRight / nf_fullrespixperovpix)
        nf_ovtop = max(nf_ovtop, 0)
        nf_ovleft = max(nf_ovleft, 0)
        nf_ovbottom = min(nf_ovbottom, nf_selectedovi.ysize-1)
        nf_ovright = min(nf_ovright, nf_selectedovi.xsize-1)
        nf_ovxsize = nf_ovright - nf_ovleft + 1
        nf_ovysize = nf_ovbottom - nf_ovtop + 1

        ovPixPerWinPix = self.coordmgr.imgPixPerWinPix / nf_fullrespixperovpix
        print 'ovPixPerWinPix', ovPixPerWinPix, pixTop, pixLeft
        nf_ovbuffxsize = int(numpy.ceil(float(nf_ovxsize) / ovPixPerWinPix))
        nf_ovbuffysize = int(numpy.ceil(float(nf_ovysize) / ovPixPerWinPix))

        # The display coordinates of the top-left corner of the raster data. Often this
        # is (0, 0), but need not be if there is blank area left/above the raster data
        (nf_dspRastLeft, nf_dspRastTop) = self.coordmgr.pixel2display(int(pixLeft), int(pixTop))
        # TODO : don't understand why I have to do this
        if nf_dspRastLeft < 0:
            nf_dspRastLeft = 0
        if nf_dspRastTop <  0:
            nf_dspRastTop = 0
        nf_ovbuffxsize = min(nf_ovbuffxsize, self.coordmgr.dspWidth - nf_dspRastLeft)
        nf_ovbuffysize = min(nf_ovbuffysize, self.coordmgr.dspHeight - nf_dspRastTop)
        print self.coordmgr
        print nf_ovleft, nf_ovtop, nf_ovxsize, nf_ovysize, nf_ovbuffxsize, nf_ovbuffysize, nf_dspRastLeft, nf_dspRastTop

        # only need to do the mask once
        mask = numpy.empty((self.coordmgr.dspHeight, self.coordmgr.dspWidth), dtype=numpy.uint8)
        mask.fill(viewerLUT.MASK_BACKGROUND_VALUE) # set to background
        
        dataslice = (slice(nf_dspRastTop, nf_dspRastTop+nf_ovbuffysize),
            slice(nf_dspRastLeft, nf_dspRastLeft+nf_ovbuffxsize))
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
                data = numpy.zeros((self.coordmgr.dspHeight, self.coordmgr.dspWidth), dtype=numpytype) 

                # get correct overview
                if nf_selectedovi.index > 0:
                    band = band.GetOverview(nf_selectedovi.index - 1)

                # read into correct part of our window array
                #if self.coordmgr.imgPixPerWinPix >= 1.0:
                dataTmp = band.ReadAsArray(nf_ovleft, nf_ovtop, nf_ovxsize, nf_ovysize,
                        nf_ovbuffxsize, nf_ovbuffysize)
                print dataTmp.shape, dataslice
                data[dataslice] = dataTmp
                # TODO
                #else:
                #    dataTmp = band.ReadAsArray(nf_ovleft, nf_ovtop, nf_ovxsize, nf_ovysize)
                #    print 'repl', dataTmp.shape, dataslice
                #    replicateArray(dataTmp, data[dataslice])
                    
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
            band = self.gdalDataset.GetRasterBand(self.stretch.bands[0])

            # create blank array of right size to read in to
            numpytype = GDALTypeToNumpyType(band.DataType)
            data = numpy.zeros((self.coordmgr.dspHeight, self.coordmgr.dspWidth), dtype=numpytype) 

            # get correct overview
            if nf_selectedovi.index > 0:
                band = band.GetOverview(nf_selectedovi.index - 1)

            # read into correct part of our window array
            #if self.coordmgr.imgPixPerWinPix >= 1.0:
            data[dataslice] = band.ReadAsArray(nf_ovleft, nf_ovtop, nf_ovxsize, nf_ovysize,
                    nf_ovbuffxsize, nf_ovbuffysize)
            # TODO
            #else:
            #    dataTmp = band.ReadAsArray(nf_ovleft, nf_ovtop, nf_ovxsize, nf_ovysize)
            #    replicateArray(dataTmp, data[dataslice])

            # do we have no data for this band?
            nodata_value = self.noDataValues[self.stretch.bands[0] - 1]
            if nodata_value is not None:
                inimage_and_nodata = numpy.logical_and(mask == viewerLUT.MASK_IMAGE_VALUE, data == nodata_value)
                mask = numpy.where(inimage_and_nodata, viewerLUT.MASK_NODATA_VALUE, mask)

            # apply LUT
            self.image = self.lut.applyLUTSingle(data, mask)


class ViewerVectorLayer(ViewerLayer):
    """
    A vector layer. I don't do much with this yet...
    """
    def __init__(self):
        ViewerLayer.__init__(self)
        self.ogrDataset = None
        self.coordmgr = coordinatemgr.VectorCoordinateManager()

class LayerManager(object):
    """
    Class that manages a list of layers
    """
    def __init__(self):
        self.layers = []

    def setDisplaySize(self, width, height):
        """
        When window resized this updates all the layers
        """
        for layer in self.layers:
            layer.coordmgr.setDisplaySize(width, height)
            layer.coordmgr.recalcBottomRight()
        self.updateImages()

    def addRasterLayer(self, filename, width, height, stretch, lut=None):
        """
        Add a new raster layer with given display width and height, stretch
        and optional lut.
        """
        # create and open
        layer = ViewerRasterLayer()
        layer.open(filename, width, height, stretch, lut)

        if len(self.layers) > 0:
            # get the existing extent
            extent = self.layers[-1].coordmgr.getWorldExtent()
            layer.coordmgr.setWorldExtent(extent)

        layer.getImage()
        self.layers.append(layer)

    def addVectorLayer(self, filename, color):
        """
        Add a vector layer. Don't do much here yet...
        """
        pass

    def removeTopLayer(self):
        """
        Removes the top layer
        """
        if len(self.layers) > 0:
            self.layers.pop()

    def getTopLayer(self):
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

    def makeLayersConsistant(self, reflayer):
        """
        Make all layers spatially consistant with reflayer
        """
        extent = reflayer.coordmgr.getWorldExtent()        

        for layer in self.layers[:-1]:
            if not reflayer is layer:
                layer.coordmgr.setWorldExtent(extent)

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
            self.makeLayersConsistant(layer)
            self.updateImages()

    def zoomFullExtent(self):
        """
        Zoom to the full extent of the top raster layer
        This might need a re-think for vectors.
        """
        layer = self.getTopRasterLayer()
        if layer is not None:
            layer.coordmgr.setTopLeftPixel(0, 0)
            firstoverview = layer.overviews.getFullRes()
            layer.coordmgr.calcZoomFactor(firstoverview.xsize, firstoverview.ysize)
            self.makeLayersConsistant(layer)
            self.updateImages()


def replicateArray(arr, outarr):
    """
    Replicate the data in the given 2-d array so that it increases
    in size to be (ysize, xsize). 
    
    Replicates each pixel in both directions. 
    
    """
    (ysize, xsize) = outarr.shape
    (nrows, ncols) = arr.shape
    nRptsX = int(numpy.ceil(xsize / ncols))
    nRptsY = int(numpy.ceil(ysize / nrows))
    print 'replicateArray', ysize, xsize, nrows, ncols, nRptsX, nRptsY
    for i in range(nRptsY):
        numYvals = int(numpy.ceil((ysize-i) / nRptsY))
        for j in range(nRptsX):
            numXvals = int(numpy.ceil((xsize-j) / nRptsX))
            outarr[i::nRptsY, j::nRptsX] = arr[:numYvals, :numXvals]





