
"""
Contains the GeolinkedViewers class.
"""
import math
from PyQt4.QtCore import QObject, QTimer, SIGNAL, Qt
from PyQt4.QtGui import QApplication

from . import viewerwindow

class GeolinkedViewers(QObject):
    """
    Class that manages a collection of ViewerWindows
    that have their widgets geolinked.
    """
    def __init__(self):
        QObject.__init__(self)
        # need to keep a reference to keep the python objects alive
        # otherwise they are deleted before they are shown
        self.viewers = []
        # set up a timer so we can periodically remove viewer
        # instances when they are no longer open to save memory
        # Usually, in PyQt you don't have such a 'dynamic' 
        # number of sub windows. 
        self.timer = QTimer(self)
        self.connect(self.timer, SIGNAL("timeout()"), self.cleanUp)
        self.timer.start(10000) # 10 secs

    @staticmethod
    def getViewerList():
        """
        Gets the list of current viewer windows from Qt
        """
        viewers = []
        for viewer in QApplication.topLevelWidgets():
            if (isinstance(viewer, viewerwindow.ViewerWindow) 
                    and viewer.isVisible()):
                viewers.append(viewer)
        return viewers

    def cleanUp(self):
        "remove any viewers that are no longer in the activelist"
        activeviewers = self.getViewerList()

        # remove any viewers that are no longer in the activelist
        # (they must have been closed)
        # they should now be cleaned up by Python and memory released
        self.viewers = [viewer for viewer in self.viewers 
                                if viewer in activeviewers]

    def closeAll(self):
        """
        Call this to close all geonlinked viewers
        """
        for viewer in self.viewers:
            viewer.close()
        self.viewers = []

    def setActiveToolAll(self, tool):
        """
        sets the specified tool as active on 
        all the viewers
        """
        for viewer in self.viewers:
            viewer.viewwidget.setActiveTool(tool)

    def setQueryPointAll(self, senderid, easting, northing, color, 
                                    size=None, cursor=None):
        """
        Calls setQueryPoint on all the widgets
        """
        for viewer in self.viewers:
            viewer.viewwidget.setQueryPoint(senderid, easting, northing, color,
                                                    size, cursor)

    def newViewer(self, filename=None, stretch=None):
        """
        Call this to create a new geolinked viewer
        """
        newviewer = viewerwindow.ViewerWindow()
        newviewer.show()

        # connect signals
        self.connectSignals(newviewer)

        # open the file if we have one
        if filename is not None:
            newviewer.addRasterInternal(filename, stretch)

        self.viewers.append(newviewer)

        # emit a signal so that application can do any customisation
        self.emit(SIGNAL("newViewerCreated(PyQt_PyObject)"), newviewer)

    def connectSignals(self, newviewer):
        """
        Connects the appropriate signals for the new viewer
        """
        # connect to the signal the widget sends when moved
        # sends new easting, northing and id() of the widget. 
        self.connect(newviewer.viewwidget, 
                    SIGNAL("geolinkMove(PyQt_PyObject)"), self.onMove)
        # the signal when a new query point is chosen
        # on a widget. Sends easting, northing and id() of the widget
        self.connect(newviewer.viewwidget, 
                    SIGNAL("geolinkQueryPoint(PyQt_PyObject)"), self.onQuery)
        # signal for request for new window
        self.connect(newviewer, SIGNAL("newWindow()"), self.onNewWindow)
        # signal for request for windows to be tiled
        self.connect(newviewer, SIGNAL("tileWindows(int, int)"), 
                    self.onTileWindows)

    def onNewWindow(self):
        """
        Called when the user requests a new window
        """
        newviewer = viewerwindow.ViewerWindow()
        newviewer.show()

        # connect signals
        self.connectSignals(newviewer)

        self.viewers.append(newviewer)

        # emit a signal so that application can do any customisation
        self.emit(SIGNAL("newViewerCreated(PyQt_PyObject)"), newviewer)

    def getDesktopSize(self):
        """
        Called at the start of the tiling operation.
        Default implementation just gets the size of the desktop.
        if overridden, return a QRect
        """
        return QApplication.desktop().availableGeometry()

    def onTileWindows(self, nxside, nyside):
        """
        Called when the user wants the windows to be tiled
        """
        # get the dimensions of the desktop
        desktop = self.getDesktopSize()

        # do they want full auto?
        if nxside == 0 and nyside == 0:
            # find the number of viewers along each side
            nxside = math.sqrt(len(self.viewers))
            # round up - we may end up with gaps
            nxside = int(math.ceil(nxside))
            
            nyside = int(math.ceil(len(self.viewers) / float(nxside)))
        elif nxside == 0 and nyside != 0:
            # guess nxside
            nxside = int(math.ceil(len(self.viewers) / float(nyside)))
        elif nxside != 0 and nyside == 0:
            # guess yxside
            nyside = int(math.ceil(len(self.viewers) / float(nxside)))

        # size of each viewer window
        viewerwidth = int(desktop.width() / nxside)
        viewerheight = int(desktop.height() / nyside)

        # there is a problem where resize() doesn't include the frame
        # area so we have to calculate it ourselves. This is the best
        # I could come up with
        geom = self.viewers[0].geometry()
        framegeom = self.viewers[0].frameGeometry()
        framewidth = framegeom.width() - geom.width()
        frameheight = framegeom.height() - geom.height()

        # now resize and move the viewers
        xcount = 0
        ycount = 0
        for viewer in self.getViewerList():
            # remove any maximised states - window manager will not let
            # use resize
            state = viewer.windowState()
            if (state & Qt.WindowMaximized) == Qt.WindowMaximized:
                viewer.setWindowState(state ^ Qt.WindowMaximized)
            # resize takes the area without the frame so we correct for that
            viewer.resize(viewerwidth - framewidth, viewerheight - frameheight)
            # remember that taskbar etc mean that we might not want 
            # to start at 0,0
            viewer.move(desktop.x() + viewerwidth * xcount, 
                            desktop.y() + viewerheight * ycount)

            xcount += 1
            if xcount >= nxside:
                xcount = 0
                ycount += 1

    def onMove(self, obj):
        """
        Called when a widget signals it has moved. Move all the
        other widgets. A GeolinkInfo object is passed.
        Sends the id() of the widget and uses this to not move the original widget
        """
        for viewer in self.getViewerList():
            # we use the id() of the widget to 
            # identify them.
            if id(viewer.viewwidget) != obj.senderid:
                viewer.viewwidget.doGeolinkMove(obj.easting, obj.northing, 
                                    obj.metresperwinpix)

    def onQuery(self, obj):
        """
        Called when a widget signals the query point has moved.
        Notify the other widgets. A GeolinkInfo object is passed.
        Sends the id() of the widget and uses this not to notify the original widget
        """
        for viewer in self.getViewerList():
            # we use the id() of the widget to 
            # identify them.
            if id(viewer.viewwidget) != obj.senderid:
                viewer.viewwidget.doGeolinkQueryPoint(obj.easting, obj.northing)
