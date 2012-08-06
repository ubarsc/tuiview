
from . import viewerRAT


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
    def __init__(self):
        self.image = None
        self.filename = None

class ViewerRasterLayer(ViewerLayer):
    def __init__(self):
        ViewerLayer.__init__(self)
        self.coordmgr = coordinatemgr.RasterCoordinateManager()
        self.gdalDataset = None
        self.bandNames = None
        self.wavelengths = None
        self.noDataValues = None
        self.attributes = viewerRAT.ViewerRAT()
        self.overviews = OverviewManager()
        self.lut = viewerLUT.ViewerLUT()
        self.stretch = None

    def open(self, filename, stretch, lut=None):
        self.filename = fname
        self.ds = gdal.Open(fname)
        # TODO check WKT

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
        firstoverview = self.overviews.getFullRes()
        self.coordmgr.setDisplaySize(size.width(), size.height())
        self.coordmgr.setGeoTransform(transform)
        self.coordmgr.setTopLeftPixel(0, 0)  # This may be overridden by the LayerManager if there are other layers
        self.coordmgr.calcZoomFactor(firstoverview.xsize, firstoverview.ysize)

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
        ENVI driver, or None.
        Other formats will be added in future.
        """
        wavelengths = []
        ok = False

        drivername = self.ds.GetDriver().ShortName
        if drivername == 'ENVI':
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

    def getImage(self):

        # find the best overview based on imgpixperwinpix
        nf_selectedovi = self.overviews.findBestOverview(self.coordmgr.imgPixPerWinPix)
        
        size = self.viewport().size()
        winxsize = size.width()
        winysize = size.height()

        nf_fullrespixperovpix = nf_selectedovi.fullrespixperpix
        pixTop = max(self.coordmgr.pixTop, 0)
        pixLeft = max(self.coordmgr.pixLeft, 0)
        pixBottom = min(self.coordmgr.pixBottom, self.ds.RasterYSize-1)
        pixRight = min(self.coordmgr.pixRight, self.ds.RasterXSize-1)
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
        nf_ovbuffxsize = int(numpy.ceil(nf_ovxsize / ovPixPerWinPix))
        nf_ovbuffysize = int(numpy.ceil(nf_ovysize / ovPixPerWinPix))

        # The display coordinates of the top-left corner of the raster data. Often this
        # is (0, 0), but need not be if there is blank area left/above the raster data
        (nf_dspRastLeft, nf_dspRastTop) = self.coordmgr.pixel2display(int(pixLeft), int(pixTop))
        nf_ovbuffxsize = min(nf_ovbuffxsize, winxsize - nf_dspRastLeft)
        nf_ovbuffysize = min(nf_ovbuffysize, winysize - nf_dspRastTop)
        print self.coordmgr
        print nf_ovxsize, nf_ovysize, nf_ovbuffxsize, nf_ovbuffysize, nf_dspRastLeft, nf_dspRastTop

        # only need to do the mask once
        mask = numpy.empty((winysize, winxsize), dtype=numpy.uint8)
        mask.fill(viewerLUT.MASK_BACKGROUND_VALUE) # set to background
        
        dataslice = (slice(nf_dspRastTop, nf_dspRastTop+nf_ovbuffysize),
            slice(nf_dspRastLeft, nf_dspRastLeft+nf_ovbuffxsize))
        mask[dataslice] = viewerLUT.MASK_IMAGE_VALUE # 0 where there is data
        nodata_mask = None

        if len(self.stretch.bands) == 3:
            # rgb
            datalist = []
            for bandnum in self.stretch.bands:
                band = self.ds.GetRasterBand(bandnum)

                # create blank array of right size to read in to. This data
                # array represents the window pixels, one-for-one
                numpytype = GDALTypeToNumpyType(band.DataType)
                data = numpy.zeros((winysize, winxsize), dtype=numpytype) 

                # get correct overview
                if nf_selectedovi.index > 0:
                    band = band.GetOverview(nf_selectedovi.index - 1)

                # read into correct part of our window array
                if self.coordmgr.imgPixPerWinPix >= 1.0:
                    dataTmp = band.ReadAsArray(nf_ovleft, nf_ovtop, nf_ovxsize, nf_ovysize,
                        nf_ovbuffxsize, nf_ovbuffysize)
                    print dataTmp.shape, dataslice
                    data[dataslice] = dataTmp
                else:
                    dataTmp = band.ReadAsArray(nf_ovleft, nf_ovtop, nf_ovxsize, nf_ovysize)
                    print 'repl', dataTmp.shape, dataslice
                    replicateArray(dataTmp, data[dataslice])
                    
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
            if nf_selectedovi.index > 0:
                band = band.GetOverview(nf_selectedovi.index - 1)

            # read into correct part of our window array
            if self.coordmgr.imgPixPerWinPix >= 1.0:
                data[dataslice] = band.ReadAsArray(nf_ovleft, nf_ovtop, nf_ovxsize, nf_ovysize,
                    nf_ovbuffxsize, nf_ovbuffysize)
            else:
                dataTmp = band.ReadAsArray(nf_ovleft, nf_ovtop, nf_ovxsize, nf_ovysize)
                replicateArray(dataTmp, data[dataslice])

            # do we have no data for this band?
            nodata_value = self.noDataValues[self.stretch.bands[0] - 1]
            if nodata_value is not None:
                inimage_and_nodata = numpy.logical_and(mask == viewerLUT.MASK_IMAGE_VALUE, data == nodata_value)
                mask = numpy.where(inimage_and_nodata, viewerLUT.MASK_NODATA_VALUE, mask)

            # apply LUT
            self.image = self.lut.applyLUTSingle(data, mask)


class ViewerVectorLayer(ViewerLayer):
    def __init__(self):
        ViewerLayer.__init__(self)
        self.ogrDataset = None
        self.coordmgr = coordinatemgr.VectorCoordinateManager()

class LayerManager(object):
    def __init__(self):
        self.layers = []

    def addRasterLayer(self, filename, stretch, lut=None):
        layer = ViewerRasterLayer()
        layer.open(filename, stretch, lut)

        if len(self.layers) > 0:
            # get the existing extent
            extent = self.layers[-1].coordmgr.getWorldExtent()
            layer.setWorldExtent(extent)

        layer.getImage()
        layers.append(layer)

    def addVectorLayer(self, filename, color):
        pass

    def removeTopLayer(self):
        if len(self.layers) > 0:
            self.layers.pop()

    def updateImages(self):
        for layer in self.layers:
            layer.getImage()

    def makeLayersConsistantWithTop(self):
        toplayer = self.layers[-1]
        extent = toplayer.coordmgr.getWorldExtent()        

        for layer in self.layers[:-1]:
            layer.coordmgr.setWorldExtent(extent)

    def zoomNativeResolution(self):
        if len(self.layers) > 0:
            toplayer = self.layers[-1]
            toplayer.coordmgr.setZoomFactor(1.0)
            self.makeLayersConsistantWithTop()
            self.updateImages()

    def zoomFullExtent(self):
        if len(self.layers) > 0:
            toplayer = self.layers[-1]
            toplayer.coordmgr.setTopLeftPixel(0, 0)
            firstoverview = toplayer.overviews.getFullRes()
            toplayer.coordmgr.calcZoomFactor(firstoverview.xsize, firstoverview.ysize)
            self.makeLayersConsistantWithTop()
            self.updateImages()









