
"""
Contains the GeolinkedViewers class.
"""

from PyQt4.QtCore import QObject, SIGNAL

from . import viewerwindow

class GeolinkedViewers(QObject):
    """
    Class that manages a collection of ViewerWindows
    that have their widgets geolinked.
    """
    def __init__(self):
        QObject.__init__(self)
        self.viewers = []

    def newViewer(self, filename=None, stretch=None):
        """
        Call this to create a new geolinked viewer
        """
        newviewer = viewerwindow.ViewerWindow()
        newviewer.show()

        # connect to the signal the widget sends when moved
        # sends new easting, northing and id() of the widget. 
        self.connect(newviewer.viewwidget, SIGNAL("geolinkMove(double, double, long)"), self.onMove)
        # the signal when a viewer instance is closed
        # sends the id() of the window
        self.connect(newviewer, SIGNAL("viewerClosed(long)"), self.onClose)
        # signal for request for new window
        self.connect(newviewer, SIGNAL("newWindow()"), self.onNewWindow)

        # open the file if we have one
        if filename is not None:
            newviewer.openFileInternal(filename, stretch)

        self.viewers.append(newviewer)

    def onNewWindow(self):
        """
        Called when the user requests a new window
        """
        newviewer = viewerwindow.ViewerWindow()
        newviewer.show()
        self.viewers.append(newviewer)

    def onClose(self, senderid):
        """
        Called when a viewerwindow closed. Sends the
        id() of the window. Remove from our list.
        """
        index = -1
        count = 0
        for viewer in self.viewers:
            if id(viewer) == senderid:
                index = count
                break
            count += 1

        if index != -1:
            del self.viewers[index]

    def onMove(self, easting, northing, senderid):
        """
        Called when a widget signals it has moved. Move all the
        other widgets. Sends the id() of the widget.
        """
        for viewer in self.viewers:
            # we use the id() of the widget to 
            # identify them.
            if id(viewer.viewwidget) != senderid:
                viewer.viewwidget.doGeolinkMove(easting, northing)

