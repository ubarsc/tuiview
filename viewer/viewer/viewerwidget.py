
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

VIEWER_STRETCHMODE_NONE = 0
VIEWER_STRETCHMODE_2STDDEV = 1
VIEWER_STRETCHMODE_HIST = 2

# raise exceptions rather than returning None
gdal.UseExceptions()

def inrange(value, minval, maxval):
    if value > maxval:
        value = maxval
    elif value < minval:
        value = minval
    return value

class WindowFraction(object):
    """
    Stores information about wereabouts in the current 
    image the viewport is looking as a fraction
    """
    def __init__(self):
        # initially we are looking at the whole image
        self.tlfraction = [0.0, 0.0] # start at top left
        self.viewfraction = [1.0, 1.0] # contain the whole thing
        # this should always be True
        # self.tlfraction  + self.viewfraction <= 1.0

    def moveView(self, xfraction, yfraction):
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

        # work out the centre of the window as a fraction
        centrefractionx = self.tlfraction[0] + (self.viewfraction[0] / 2.0)
        centrefractiony = self.tlfraction[1] + (self.viewfraction[1] / 2.0)

        # increase the view fraction by the required amount
        viewfractionx = self.viewfraction[0] * (1.0 + fraction)
        viewfractiony = self.viewfraction[1] * (1.0 + fraction)

        # work out what the tl fraction would be
        tlfractionx = centrefractionx - ( viewfractionx / 2.0 )
        tlfractiony = centrefractiony - ( viewfractiony / 2.0 )

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
        # are we trying to match x or y? 
        # we match the biggest
        xismax = winxsize > winysize

        # convert to float so we don't need to do this each
        # time around the loop
        winxsize = float(winxsize)
        winysize = float(winysize)

        # start with the first, then try the others
        # if available
        selectedovi = self.overviews[0]
        for ovi in self.overviews[1:]:
            if xismax:
                factor = (ovi.xsize * viewfraction[0]) / winxsize
            else:
                factor = (ovi.ysize * viewfraction[1]) / winysize
            if factor > 1.0:
                selectedovi = ovi
            else:
                break

        return selectedovi

class ViewerWidget(QAbstractScrollArea):
    def __init__(self, parent):
        QAbstractScrollArea.__init__(self, parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        self.ds = None
        self.overviews = OverviewManager()
        self.lut = None
        self.bands = None
        self.mode = None
        self.image = None
        self.windowfraction = None

        self.suppressscrollevent = False

    def createStretchLUT(self, gdalband, stretchmode):

        if stretchmode == VIEWER_STRETCHMODE_NONE:
            lutsize = 2 ** gdal.GetDataTypeSize(gdalband.DataType) 
            lut = numpy.linspace(0, 255, lutsize)
            return lut

        elif stretchmode == VIEWER_STRETCHMODE_2STDDEV:
            minVal, maxVal, mean, stdDev = gdalband.GetStatistics(0, 0)

            stretchMin = mean - (2.0 * stdDev)
            if stretchMin < minVal:
                stretchMin = minVal
            stretchMax = mean + (2.0 * stdDev)
            if stretchMax > maxVal:
                stretchMax = maxVal

            stretchMin = int(stretchMin)
            stretchMax = int(stretchMax)

            lutsize = 2 ** gdal.GetDataTypeSize(gdalband.DataType) 
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
        self.ds = gdal.Open(fname)
        transform = self.ds.GetGeoTransform()
        if transform[2] != 0 or transform[4] != 0 or transform[1] != -transform[5]:
            msg = 'Only currently support square pixels and non-rotated images'
            raise viewererrors.InvalidDataset(msg)

        dtype = self.ds.GetRasterBand(1).DataType
        if dtype == gdal.GDT_Float32 or dtype == gdal.GDT_Float64:
            msg = 'Only support integer types at present'
            raise viewererrors.InvalidDataset(msg)

        self.overviews.loadOverviewInfo(self.ds, bands)

        self.windowfraction = WindowFraction()
        self.bands = bands
        self.mode = mode

        if mode == VIEWER_MODE_COLORTABLE:

            if len(bands) > 1:
                msg = 'specify one band when opening a color table image'
                raise viewererrors.InvalidParameters(msg)
            band = bands[0]

            ct = self.ds.GetRasterBand(band).GetColorTable()
            if ct is not None and ct.GetPaletteInterpretation() == gdal.GPI_RGB:
                # read in the colour table as lut
                ctcount = ct.GetCount()
                self.lut = numpy.empty((ctcount, 4), numpy.uint8)
                for i in range(ctcount):
                    entry = ct.GetColorEntry(i)
                    # entry is RGBA, need to store as BGRA
                    self.lut[i] = (entry[2], entry[1], entry[0], entry[3])
            else:
                msg = 'No color table present'
                raise viewererrors.InvalidColorTable(msg)
            print self.lut.shape

        elif mode == VIEWER_MODE_GREYSCALE:
            if len(bands) > 1:
                msg = 'specify one band when opening a greyscale image'
                raise viewererrors.InvalidParameters(msg)
            band = bands[0]

            lut = self.createStretchLUT( self.ds.GetRasterBand(band), stretchmode )
            alpha = numpy.zeros_like(lut) + 255
            # column_stack seems to create Fortran arrays which stuffs up
            # the creation of QImage's from it.
            self.lut = numpy.column_stack((lut, lut, lut, alpha)).copy('C')

        elif mode == VIEWER_MODE_RGB:
            if len(bands) != 3:
                msg = 'must specify 3 bands when opening rgb'
                raise viewererrors.InvalidParameters(msg)

            luts = []
            for band in bands:
                lut = self.createStretchLUT( self.ds.GetRasterBand(band), stretchmode )
                luts.append(lut)
            self.lut = luts
            
        else:
            msg = 'unsupported display mode'
            raise viewererrors.InvalidParameters(msg)

        size = self.viewport().size()
        self.getData(size.width(), size.height())
    
    def getData(self, winxsize, winysize):

        if self.ds is None:
            return

        viewfraction = self.windowfraction.viewfraction
        tlfraction = self.windowfraction.tlfraction


        selectedovi = self.overviews.findBestOverview(winxsize, winysize, viewfraction)
        print selectedovi.index
        xismax = winxsize > winysize

        ratio = selectedovi.xsize / float(selectedovi.ysize)
        if xismax:
            winysize = int(winxsize / ratio)
        else:
            winxsize = int(winysize * ratio)

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
            bgras = []
            lutindex = 0
            for bandnum in self.bands:
                band = self.ds.GetRasterBand(bandnum)
                if selectedovi.index > 0:
                    band = band.GetOverview(selectedovi.index - 1)

                data = band.ReadAsArray(x, y, xsize, ysize, winxsize, winysize )
                lut = self.lut[lutindex]
                bgra = lut[data]
                bgras.append(bgra)
                lutindex += 1

            bgra = numpy.empty((winysize, winxsize, 4), numpy.uint8)
            bgra[...,0] = bgras[0]
            bgra[...,1] = bgras[1]
            bgra[...,2] = bgras[2]
            bgra[...,3].fill(255)

        else:
            # must be single band
            band = self.ds.GetRasterBand(self.bands[0])
            if selectedovi.index > 0:
                band = band.GetOverview(selectedovi.index - 1)

            data = band.ReadAsArray(x, y, xsize, ysize, winxsize, winysize )

            # Qt expects 32bit BGRA data for color images
            # our lut is already set up for this
            bgra = self.lut[data]
            print bgra.shape

        self.image = QImage(bgra.data, winxsize, winysize, QImage.Format_RGB32)

        self.suppressscrollevent = True
        self.horizontalScrollBar().setPageStep(xsize)
        self.verticalScrollBar().setPageStep(ysize)
        self.horizontalScrollBar().setRange(0, selectedovi.xsize - xsize)
        self.verticalScrollBar().setRange(0, selectedovi.ysize - ysize)
        self.horizontalScrollBar().setSliderPosition(x)
        self.verticalScrollBar().setSliderPosition(y)
        self.suppressscrollevent = False
        
    def dragMoveEvent(self, event):
        print "dragMoveEvent"

    def dragLeaveEvent(self, event):
        print "dragLeaveEvent"

    def dragEnterEvent(self, event):
        print "dragEnterEvent"

    def scrollContentsBy(self, dx, dy):
        if not self.suppressscrollevent:
            xamount = dx * -0.0002
            yamount = dy * -0.0002
            self.windowfraction.moveView(xamount, yamount)

            size = self.viewport().size()
            self.getData(size.width(), size.height())
            self.viewport().update()        

    def zoom(self, amount):

        self.windowfraction.zoomView(amount)

        size = self.viewport().size()
        self.getData(size.width(), size.height())
        self.viewport().update()        

    def wheelEvent(self, event):
        if event.delta() > 0:
            self.zoom(-0.1)
        elif event.delta() < 0:
            self.zoom(0.1)

    def resizeEvent(self, event):
        oldsize = event.oldSize()
        newsize = event.size()
        # only bother grabbing more data
        # if the area has got bigger
        # the paint will just ignore the extra data if
        # it is now smaller
        if newsize.width() > oldsize.width() or newsize.height() > oldsize.height():
            size = self.viewport().size()
            self.getData(size.width(), size.height())
            self.viewport().update()        
                    

    def paintEvent(self, event):
        if self.image is not None:
            paint = QPainter(self.viewport())
            paint.drawImage(0,0,self.image)
            paint.end()
