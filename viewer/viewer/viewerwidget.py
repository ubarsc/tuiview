
import numpy
from PyQt4.QtGui import QAbstractScrollArea, QPainter, QImage
from PyQt4.QtCore import Qt
from osgeo import gdal

# raise exceptions rather than returning None
gdal.UseExceptions()

def inrange(value, minval, maxval):
    if value > maxval:
        value = maxval
    elif value < minval:
        value = minval
    return value

class OverviewInfo(object):
    def __init__(self, xsize, ysize):
        self.xsize = xsize
        self.ysize = ysize

class ViewerWidget(QAbstractScrollArea):
    def __init__(self, parent):
        QAbstractScrollArea.__init__(self, parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        self.ds = None
        self.overviews = None
        self.lut = None
        self.image = None

        self.tlfraction = [0.0, 0.0]
        self.viewfraction = [1.0, 1.0]

        self.suppressscrollevent = False

    def open(self, fname):
        self.ds = gdal.Open(fname)
        self.overviews = []
        ovi = OverviewInfo(self.ds.RasterXSize, self.ds.RasterYSize)
        self.overviews.append(ovi)
        
        # just grab the overview info for the first band
        # probably should be more rigurous
        band = self.ds.GetRasterBand(1)
        count = band.GetOverviewCount()
        for i in range(count):
            ov = band.GetOverview(i)
            ovi = OverviewInfo(ov.XSize, ov.YSize)
            self.overviews.append(ovi)

        # make sure they are sorted by area - biggest first
        self.overviews.sort(key=lambda ov: ov.xsize * ov.ysize, reverse=True)

        ct = band.GetColorTable()
        if ct is not None and ct.GetPaletteInterpretation() == gdal.GPI_RGB:
            # read in the colour table as lut
            ctcount = ct.GetCount()
            self.lut = numpy.empty((ctcount, 4), numpy.uint8)
            for i in range(ctcount):
                entry = ct.GetColorEntry(i)
                # entry is RGBA, need to store as BGRA
                self.lut[i] = (entry[2], entry[1], entry[0], entry[3])

        size = self.viewport().size()
        self.getData(size.width(), size.height())
    
    def getData(self, winxsize, winysize):
        # calculate the factor between the win size and each overview
        xismin = winxsize < winysize

        selectedoviidx = 0
        selectedovi = self.overviews[0]
        count = 1
        while count < len(self.overviews):
            ovi = self.overviews[count]
            if xismin:
                factor = (ovi.xsize * self.viewfraction[0]) / float(winxsize)
            else:
                factor = (ovi.ysize * self.viewfraction[1]) / float(winysize)
            if factor > 1.0:
                selectedoviidx = count
                selectedovi = ovi
            else:
                break
            count += 1

        print selectedoviidx

        ratio = selectedovi.xsize / float(selectedovi.ysize)
        if xismin:
            winysize = int(winxsize / ratio)
        else:
            winxsize = int(winysize * ratio)

        band = self.ds.GetRasterBand(1)
        if selectedoviidx > 0:
            band = band.GetOverview(selectedoviidx - 1)

        x = int(selectedovi.xsize * self.tlfraction[0])
        y = int(selectedovi.ysize * self.tlfraction[1])
        xsize = int(selectedovi.xsize * self.viewfraction[0])
        ysize = int(selectedovi.ysize * self.viewfraction[1])

        totalx = x + xsize
        if totalx > selectedovi.xsize:
            x -= (totalx - selectedovi.xsize)
        totaly = y + ysize
        if totaly > selectedovi.ysize:
            y -= (totaly - selectedovi.ysize)

        data = band.ReadAsArray(x, y, xsize, ysize, winxsize, winysize )

        # Qt expects 32bit BGRA data for color images
        # our lut is already set up for this
        bgra = self.lut[data]

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
            self.tlfraction[0] = inrange(self.tlfraction[0] + xamount, 0.0, 1.0 - self.viewfraction[0])
            self.tlfraction[1] = inrange(self.tlfraction[1] + yamount, 0.0, 1.0 - self.viewfraction[1])
            size = self.viewport().size()
            self.getData(size.width(), size.height())
            self.viewport().update()        

    def zoom(self, amount):
        tlamount = amount / 2.0
        self.tlfraction[0] = inrange(self.tlfraction[0] + tlamount, 0.0, 0.9)
        self.tlfraction[1] = inrange(self.tlfraction[1] + tlamount, 0.0, 0.9)
        self.viewfraction[0] = inrange(self.viewfraction[0] - amount, 0.05, 1.0)
        self.viewfraction[1] = inrange(self.viewfraction[1] - amount, 0.05, 1.0)
        size = self.viewport().size()
        self.getData(size.width(), size.height())
        self.viewport().update()        

    def wheelEvent(self, event):
        if event.delta() > 0:
            self.zoom(0.05)
        elif event.delta() < 0:
            self.zoom(-0.05)
            

    def paintEvent(self, event):
        if self.image is not None:
            paint = QPainter(self.viewport())
            paint.drawImage(0,0,self.image)
            paint.end()
