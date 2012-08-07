
"""
Viewer Widget. Allows display of images,
zooming and panning etc.
"""

from __future__ import division # ensure we are using Python 3 semantics
import numpy
from PyQt4.QtGui import QAbstractScrollArea, QPainter, QRubberBand, QCursor, QPixmap, QImage, QPen
from PyQt4.QtCore import Qt, QRect, QSize, QPoint, SIGNAL
from osgeo import gdal

from . import viewererrors
from . import viewerlayers

VIEWER_ZOOM_WHEEL_FRACTION = 0.1 # viewport increased/decreased by the fraction
                            # on zoom out/ zoom in with mouse wheel

QUERY_CURSOR_HALFSIZE = 8 # number of pixels
QUERY_CURSOR_WIDTH = 2 # in pixels


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
        self.attributes = None

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

        self.layers = viewerlayers.LayerManager()

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

    def addRasterLayer(self, fname, stretch, lut=None):
        """
        Add the given filename to the stack of images being displayed
        as a raster layer
        """
        size = self.viewport().size()
        self.layers.addRasterLayer(fname, size.width(), size.height(), stretch, lut)
        self.viewport().update()

    def removeLayer(self):
        """
        Removes the top later
        """
        self.layers.removeTopLayer()
        self.viewport().update()

    def highlightValues(self, color, selectionArray=None):
        """
        Applies a QColor to the LUT where selectionArray == True
        to the top layer and redraws. Pass None to reset
        """
        layer = self.layers.getTopRasterLayer()
        if layer is not None:
            if len(layer.stretch.bands) != 1:
                raise viewererrors.InvalidDataset('can only highlight values on single band images')

            # force repaint
            self.viewport().update()


    def zoomNativeResolution(self):
        """
        Sets the zoom to native resolution wherever
        the current viewport is centered
        """
        self.layers.zoomNativeResolution()
        # force repaint
        self.viewport().update()
        # geolink
        self.emitGeolinkMoved()

    def zoomFullExtent(self):
        """
        Resets the zoom to full extent - should be
        the same as when file was opened.
        """
        self.layers.zoomFullExtent()
        # force repaint
        self.viewport().update()
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
        layer = self.layers.getTopRasterLayer()
        if layer is not None:
            layer.setNewStretch(newstretch, local)
            self.viewport().update()

    def setMouseScrollWheelAction(self, scrollZoom):
        self.mouseWheelZoom = scrollZoom

    def setGeolinkFollowExtentAction(self, followExtent):
        self.geolinkFollowExtent = followExtent

    def scrollContentsBy(self, dx, dy):
        """
        Handle the user moving the scroll bars
        """
        # if nothing open, just return
        #if self.ds is None:
        #    return

        #if not self.suppressscrollevent:
        #    xamount = dx * -(self.windowfraction.imgpixperwinpix / float(self.ds.RasterXSize))
        #    yamount = dy * -(self.windowfraction.imgpixperwinpix / float(self.ds.RasterYSize))
        #    self.windowfraction.moveView(xamount, yamount)

        #    self.getData()
        #    # geolink
        #    self.emitGeolinkMoved()

    def wheelEvent(self, event):
        """
        User has used mouse wheel to zoom in/out or pan depending on defined preference
        """
        # if nothing open, just return
        #if self.ds is None:
        #    return

        #if self.mouseWheelZoom:
        #    if event.delta() > 0:
        #        self.windowfraction.zoomViewCenter(0, 0, 1.0 - VIEWER_ZOOM_WHEEL_FRACTION)
        #    elif event.delta() < 0:
        #        self.windowfraction.zoomViewCenter(0, 0, 1.0 + VIEWER_ZOOM_WHEEL_FRACTION)
        #    self.getData()
        #else:
        #    dx = 0
        #    dy = 0
        #    if event.orientation() == Qt.Horizontal:
        #        dx = event.delta()
        #    else:
        #        dy = event.delta()
        #    self.scrollContentsBy(dx,dy)
        
        # geolink
        #self.emitGeolinkMoved()

    def resizeEvent(self, event):
        """
        Window has been resized - get new data
        """
        size = event.size()
        self.layers.setDisplaySize(size.width(), size.height())

    def paintEvent(self, event):
        """
        Viewport needs to be redrawn. Assume that
        self.image is current (as created by getData())
        we can just draw it with QPainter
        """
        paint = QPainter(self.viewport())
        for layer in self.layers.layers:
            paint.drawImage(self.paintPoint, layer.image)
        self.drawQueryPoints(paint)    # draw any query points on top of image
        paint.end()

    def drawQueryPoints(self, paint):
        """
        Draw query points as part of paint.
        """
        #if self.windowfraction is not None:
        #    size = self.viewport().size()
        #    pen = QPen()
        #    pen.setWidth(QUERY_CURSOR_WIDTH)
        #    for id in self.queryPoints:
        #        (col, row, color) = self.queryPoints[id]
        #        cx, cy = self.windowfraction.getWindowCoordFor(col, row, size)
        #        pen.setColor(color)
        #        paint.setPen(pen)
        #        # draw cross hair
        #        paint.drawLine(cx - QUERY_CURSOR_HALFSIZE, cy, cx + QUERY_CURSOR_HALFSIZE, cy)
        #        paint.drawLine(cx, cy - QUERY_CURSOR_HALFSIZE, cx, cy + QUERY_CURSOR_HALFSIZE)

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
            pos = event.pos()
            geom = self.viewport().geometry()

            layer = self.layers.getTopRasterLayer()
            if layer is not None:
                # Display coordinates. Ihave no idea why I need to add 2, but it may be something
                # to do with the geom x,y being equal to (2,2). I don't understand. 
                (dspX, dspY) = (pos.x() + 2, pos.y() + 2)
                # Raster row/column
                (column, row) = layer.coordmgr.display2pixel(dspX, dspY)
                (easting, northing) = layer.coordmgr.pixel2world(column, row)
                print 'mousePressEvent', easting, northing, dspX, dspY
                print layer.coordmgr

                # update the point
                #self.updateQueryPoint(easting, northing, column, row)

                # emit the geolinked query point signal
                self.emit(SIGNAL("geolinkQueryPoint(double, double, long)"), easting, northing, id(self) )


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

            layer = self.layers.getTopRasterLayer()
            if layer is not None:
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
                    dspTop = selection.top() + 2
                    dspLeft = selection.left() + 2
                    dspBottom = selection.bottom() + 2
                    dspRight = selection.right() + 2
                    (rastLeft, rastTop) = layer.coordmgr.display2pixel(dspLeft, dspTop)
                    (rastRight, rastBottom) = layer.coordmgr.display2pixel(dspRight, dspBottom)
                    print 'mouseReleaseEvent', dspTop, dspLeft, dspBottom, dspRight
                    print layer.coordmgr
                    layer.coordmgr.setTopLeftPixel(rastLeft, rastTop)
                    layer.coordmgr.calcZoomFactor(rastRight, rastBottom)
                    print layer.coordmgr


                elif self.activeTool == VIEWER_TOOL_ZOOMOUT:
                    # the smaller the area the larger the zoom
                    layer.coordmgr.setZoomFactor(layer.coordmgr.imgPixPerWinPix / fraction)

                # redraw
                self.layers.makeLayersConsistant(layer)
                self.layers.updateImages()
                self.viewport().update()

                # geolink
                self.emitGeolinkMoved()

        elif self.activeTool == VIEWER_TOOL_PAN:
            # change cursor back
            self.viewport().setCursor(self.panCursor)
            layer = self.layers.getTopRasterLayer()
            if layer is not None:
                # stop panning and move viewport
                dspXmove = -self.paintPoint.x()
                dspYmove = -self.paintPoint.y()
                (pixNewX, pixNewY) = layer.coordmgr.display2pixel(dspXmove, dspYmove)
                print 'panning'
                print layer.coordmgr
                layer.coordmgr.setTopLeftPixel(pixNewX, pixNewY)
                layer.coordmgr.recalcBottomRight()
                print layer.coordmgr
                # reset
                self.paintPoint.setX(0)
                self.paintPoint.setY(0)
                # redraw
                self.layers.makeLayersConsistant(layer)
                self.layers.updateImages()
                self.viewport().update()
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

        elif self.activeTool == VIEWER_TOOL_PAN:
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

    # query point routines
    def updateQueryPoint(self, easting, northing, column, row):
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
                qi.attributes = self.attributes
                # emit the signal - handled by the QueryDockWidget
                self.emit(SIGNAL("locationSelected(PyQt_PyObject)"), qi)

    def doGeolinkQueryPoint(self, easting, northing):
        """
        Call this when the widget query point has been moved
        in another viewer and should be updated in this
        one if the query tool is active.
        """
        if self.activeTool == VIEWER_TOOL_QUERY:
            layer = self.layers.getTopRasterLayer()
            if layer is not None:
                (col, row) = self.coordmgr.world2pixel(easting, northing)
                self.updateQueryPoint(easting, northing, col, row)

    # geolinking routines
    def doGeolinkMove(self, easting, northing, metresperwinpix):
        """
        Call this when widget needs to be moved because
        of geolinking event.
        """
        # if we not moving extent set to 0 will be ignored
        if not self.geolinkFollowExtent:
            metresperwinpix = 0

        if self.windowfraction is not None:
            self.windowfraction.moveToCoord(easting, northing, metresperwinpix, self.transform)
            self.getData()

    def emitGeolinkMoved(self):
        """
        Call this on each zoom/pan to emit the appropriate signal.
        """
        # get the coords of the current centre
        # TODO
        #easting, northing, col, row = self.windowfraction.getCoordFor(0, 0, self.transform)
        #metresperwinpix = self.windowfraction.imgpixperwinpix * self.transform[1]

        # emit the signal
        #self.emit(SIGNAL("geolinkMove(double, double, double, long)"), easting, northing, metresperwinpix, id(self) )


