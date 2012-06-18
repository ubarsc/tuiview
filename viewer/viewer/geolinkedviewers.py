
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
        # sends new easting, northing and id() of itself. 
        self.connect(newviewer.viewwidget, SIGNAL("geolinkMove(double, double, long)"), self.onMove)

        # open the file if we have one
        if filename is not None:
            newviewer.openFileInternal(filename, stretch)

        self.viewers.append(newviewer)


    def onMove(self, easting, northing, senderid):
        """
        Called when a widget signals it has moved. Move all the
        other widgets. 
        """
        for viewer in self.viewers:
            # we use the id() of the widget to 
            # identify them.
            if id(viewer.viewwidget) != senderid:
                viewer.viewwidget.doGeolinkMove(easting, northing)

