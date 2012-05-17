
"""
Viewer Widget. Allows display of images,
zooming and panning etc.
"""

import numpy
from PyQt4.QtGui import QAbstractScrollArea, QPainter
from PyQt4.QtCore import Qt
from osgeo import gdal

from . import viewererrors
from . import viewerLUT


VIEWER_SCROLL_MULTIPLIER = 0.00002 # number of pixels scrolled
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
    def __init__(self, winsize, firstoverview):
        # initially we are looking at the whole image
        # centred on the middle
        self.centrefraction = [0.5, 0.5]

        xperpix = float(firstoverview.xsize) / float(winsize.width())
        yperpix = float(firstoverview.ysize) / float(winsize.height())
        self.imgpixperwinpix = max(xperpix, yperpix)

        

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

    def zoomView(self, fraction):
        """
        zoom the view by fraction (positive 
        to zoom in)
        """
        self.imgpixperwinpix *= (1.0 + fraction)


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

        self.filename = None
        self.ds = None
        self.transform = None
        self.overviews = OverviewManager()
        self.lut = viewerLUT.ViewerLUT()
        self.stretch = None
        self.mode = None
        self.image = None
        self.windowfraction = None

        # when moving the scroll bars
        # events get fired that we wish to ignore
        self.suppressscrollevent = False


    def open(self, fname, stretch):
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

        # read in the LUT
        self.lut.createLUT(self.ds, stretch)

        # now go and retrieve the data for the image
        self.getData()

    def setNewStretch(self, newstretch):
        """
        Change the stretch being applied to the current data
        """
        newbands = self.stretch.bands != newstretch.bands
        if newbands:
            # only need to do this if bands have changed
            self.overviews.loadOverviewInfo(self.ds, newstretch.bands)

        self.lut.createLUT(self.ds, newstretch)

        self.stretch = newstretch
        # note - we need to do this to reapply the stretch
        # but it re-reads the data always.
        # not sure it is a big deal since GDAL caches
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
        centrefraction = self.windowfraction.centrefraction
        imgpixperwinpix = self.windowfraction.imgpixperwinpix

        fullres = self.overviews.getFullRes()

        size = self.viewport().size()
        winxsize = size.width()
        winysize = size.height()


        fullres_winxsize = winxsize * imgpixperwinpix
        fullres_winysize = winysize * imgpixperwinpix
        # adjust if the window is bigger than we need
        if fullres_winxsize > fullres.xsize:
            fullres_winxsize = fullres.xsize
            winxsize = fullres_winxsize / imgpixperwinpix
        if fullres_winysize > fullres.ysize:
            fullres_winysize = fullres.ysize
            winysize = fullres_winysize / imgpixperwinpix

        # what proportion of the full res is that?
        xprop = fullres_winxsize / float(fullres.xsize)
        yprop = fullres_winysize / float(fullres.ysize)

        # grab the best overview for the number of
        # pixels in the window
        selectedovi = self.overviews.findBestOverview(winxsize, winysize, [xprop, yprop])
        print selectedovi.index

        overview_xsize = int(xprop * selectedovi.xsize)
        overview_ysize = int(yprop * selectedovi.ysize)

        # how many overview res pixels from the top left is the centre of the image?
        overview_centrex = centrefraction[0] * selectedovi.xsize
        overview_centrey = centrefraction[1] * selectedovi.ysize

        # then subtract half the height/width
        overview_x = int(overview_centrex - (overview_xsize / 2.0))
        overview_y = int(overview_centrey - (overview_ysize / 2.0))

        if len(self.stretch.bands) == 3:
            # rgb
            datalist = []
            for bandnum in self.stretch.bands:
                band = self.ds.GetRasterBand(bandnum)
                if selectedovi.index > 0:
                    band = band.GetOverview(selectedovi.index - 1)

                data = band.ReadAsArray(overview_x, overview_y, overview_xsize, overview_ysize, winxsize, winysize )
                datalist.append(data)
            
            self.image = self.lut.applyLUTRGB(datalist)

        else:
            # must be single band
            band = self.ds.GetRasterBand(self.stretch.bands[0])
            if selectedovi.index > 0:
                band = band.GetOverview(selectedovi.index - 1)

            data = band.ReadAsArray(overview_x, overview_y, overview_xsize, overview_ysize, winxsize, winysize )

            self.image = self.lut.applyLUTSingle(data)

        # reset the scroll bars for new extent of window
        # need to suppress processing of new scroll bar
        # events otherwise we end up in endless loop
        self.suppressscrollevent = True
        self.horizontalScrollBar().setPageStep(overview_xsize)
        self.verticalScrollBar().setPageStep(overview_ysize)
        self.horizontalScrollBar().setRange(0, selectedovi.xsize - overview_xsize)
        self.verticalScrollBar().setRange(0, selectedovi.ysize - overview_ysize)
        self.horizontalScrollBar().setSliderPosition(overview_x)
        self.verticalScrollBar().setSliderPosition(overview_y)
        self.suppressscrollevent = False

        # force repaint
        self.viewport().update()        
        
    def scrollContentsBy(self, dx, dy):
        """
        Handle the user moving the scroll bars
        """
        if not self.suppressscrollevent:
            xamount = dx * -VIEWER_SCROLL_MULTIPLIER * self.windowfraction.imgpixperwinpix
            yamount = dy * -VIEWER_SCROLL_MULTIPLIER * self.windowfraction.imgpixperwinpix
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
            paint.drawImage(0,0,self.image)
            paint.end()
