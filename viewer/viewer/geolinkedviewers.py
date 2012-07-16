
"""
Contains the GeolinkedViewers class.
"""
import math
from PyQt4.QtCore import QObject, QTimer, SIGNAL
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
            if isinstance(viewer, viewerwindow.ViewerWindow) and viewer.isVisible():
                viewers.append(viewer)
        return viewers

    def cleanUp(self):
        activeviewers = self.getViewerList()

        # remove any viewers that are no longer in the activelist
        # (they must have been closed)
        # they should now be cleaned up by Python and memory released
        self.viewers = [viewer for viewer in self.viewers if viewer in activeviewers]

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

    def setQueryPointNEAll(self, id, easting, northing, color):
        """
        Calls setQueryPointNE on all the widgets
        """
        for viewer in self.viewers:
            viewer.viewwidget.setQueryPointNE(id, easting, northing, color)

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
            newviewer.openFileInternal(filename, stretch)

        self.viewers.append(newviewer)

        # emit a signal so that application can do any customisation
        self.emit(SIGNAL("newViewerCreated(PyQt_PyObject)"), newviewer)

    def connectSignals(self, newviewer):
        """
        Connects the appropriate signals for the new viewer
        """
        # connect to the signal the widget sends when moved
        # sends new easting, northing and id() of the widget. 
        self.connect(newviewer.viewwidget, SIGNAL("geolinkMove(double, double, double, long)"), self.onMove)
        # the signal when a new query point is chosen
        # on a widget. Sends easting, northing and id() of the widget
        self.connect(newviewer.viewwidget, SIGNAL("geolinkQueryPoint(double, double, long)"), self.onQuery)
        # signal for request for new window
        self.connect(newviewer, SIGNAL("newWindow()"), self.onNewWindow)
        # signal for request for windows to be tiled
        self.connect(newviewer, SIGNAL("tileWindows()"), self.onTileWindows)

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

    def onTileWindows(self):
        """
        Called when the user wants the windows to be tiled
        """
        # get the dimensions of the desktop
        desktop = QApplication.desktop().availableGeometry()

        # find the number of viewers along each side
        nxside = math.sqrt(len(self.viewers))
        # round up - we may end up with gaps
        nxside = int(math.ceil(nxside))
        
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
            # resize takes the area without the frame so we correct for that
            viewer.resize(viewerwidth - framewidth, viewerheight - frameheight)
            # remember that taskbar etc mean that we might not want to start at 0,0
            viewer.move(desktop.x() + viewerwidth * xcount, desktop.y() + viewerheight * ycount)

            xcount += 1
            if xcount >= nxside:
                xcount = 0
                ycount += 1

    def onMove(self, easting, northing, metresperwinpix, senderid):
        """
        Called when a widget signals it has moved. Move all the
        other widgets. Sends the id() of the widget.
        """
        for viewer in self.getViewerList():
            # we use the id() of the widget to 
            # identify them.
            if id(viewer.viewwidget) != senderid:
                viewer.viewwidget.doGeolinkMove(easting, northing, metresperwinpix)

    def onQuery(self, easting, northing, senderid):
        """
        Called when a widget signals the query point has moved.
        Notify the other widgets. Sends the id() of the widget.
        """
        for viewer in self.getViewerList():
            # we use the id() of the widget to 
            # identify them.
            if id(viewer.viewwidget) != senderid:
                viewer.viewwidget.doGeolinkQueryPoint(easting, northing)
