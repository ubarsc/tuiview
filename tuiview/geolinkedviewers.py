
"""
Contains the GeolinkedViewers class.
"""
# This file is part of 'TuiView' - a simple Raster viewer
# Copyright (C) 2012  Sam Gillingham
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

import math
import json
from PyQt5.QtCore import QObject, QTimer, Qt, QEventLoop, pyqtSignal
from PyQt5.QtWidgets import QApplication

from . import viewerwindow
from . import pluginmanager


class GeolinkedViewers(QObject):
    """
    Class that manages a collection of ViewerWindows
    that have their widgets geolinked.
    """
    # signals
    newViewerCreated = pyqtSignal(viewerwindow.ViewerWindow, 
                        name='newViewerCreated')

    def __init__(self, loadPlugins=True):
        QObject.__init__(self)
        # need to keep a reference to keep the python objects alive
        # otherwise they are deleted before they are shown
        self.viewers = []

        # load plugins if asked
        if loadPlugins:
            self.pluginmanager = pluginmanager.PluginManager()
            self.pluginmanager.loadPlugins()
            # do the init action
            self.pluginmanager.callAction(pluginmanager.PLUGIN_ACTION_INIT, 
                self)
        else:
            self.pluginmanager = None

        # set up a timer so we can periodically remove viewer
        # instances when they are no longer open to save memory
        # Usually, in PyQt you don't have such a 'dynamic' 
        # number of sub windows. 
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.cleanUp)
        self.timer.start(10000)  # 10 secs

    @staticmethod
    def getViewerList(screen=None):
        """
        Gets the list of current viewer windows from Qt.
        Pass in a screen to restrict to the viewers on
        that screen
        """
        viewers = []
        for viewer in QApplication.topLevelWidgets():
            if (isinstance(viewer, viewerwindow.ViewerWindow) and
                    viewer.isVisible()):
                if screen is not None:
                    screen2 = viewer.screen()
                    if screen2 is not None and screen.name() != screen2.name():
                        continue
                    
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
        Call this to close all geolinked viewers
        """
        for viewer in self.viewers:
            viewer.close()
        self.viewers = []

    def setActiveToolAll(self, tool, senderid):
        """
        sets the specified tool as active on 
        all the viewers
        """
        for viewer in self.viewers:
            viewer.viewwidget.setActiveTool(tool, senderid)

    def setQueryPointAll(self, senderid, easting, northing, color, 
            size=None, cursor=None):
        """
        Calls setQueryPoint on all the widgets
        """
        for viewer in self.viewers:
            viewer.viewwidget.setQueryPoint(senderid, easting, northing, color,
                size, cursor)

    def removeQueryPointAll(self, senderid):
        """
        Calls removeQueryPoint on all the widgets
        """
        for viewer in self.viewers:
            viewer.viewwidget.removeQueryPoint(senderid)

    def newViewer(self, filename=None, stretch=None):
        """
        Call this to create a new geolinked viewer.
        Returns the created ViewerWindow instance.
        """
        newviewer = viewerwindow.ViewerWindow()
        newviewer.show()

        # connect signals
        self.connectSignals(newviewer)

        # open the file if we have one
        if filename is not None:
            newviewer.addRasterInternal(filename, stretch)

        self.viewers.append(newviewer)

        # call any plugins
        if self.pluginmanager is not None:
            self.pluginmanager.callAction(
                pluginmanager.PLUGIN_ACTION_NEWVIEWER, newviewer)

        # emit a signal so that application can do any customisation
        self.newViewerCreated.emit(newviewer)

        # return it
        return newviewer

    def connectSignals(self, newviewer):
        """
        Connects the appropriate signals for the new viewer
        """
        # connect to the signal the widget sends when moved
        # sends new easting, northing and id() of the widget. 
        newviewer.viewwidget.geolinkMove.connect(self.onMove)
        # the signal when a new query point is chosen
        # on a widget. Sends easting, northing and id() of the widget
        newviewer.viewwidget.geolinkQueryPoint.connect(self.onQuery)
        # signal for request for new window
        newviewer.newWindowSig.connect(self.onNewWindow)
        # signal for request for windows to be tiled
        newviewer.tileWindowsSig.connect(self.onTileWindows)
        # signal for new query window been opened
        newviewer.newQueryWindowSig.connect(self.onNewQueryWindow)
        # signal for closing all windows
        newviewer.closeAllWindowsSig.connect(self.closeAll)
        # signal for request to write viewers state to a file
        newviewer.writeViewersState.connect(self.writeViewersState)
        # signal for request to read viewers state from file
        newviewer.readViewersState.connect(self.readViewersState)

    def onNewWindow(self):
        """
        Called when the user requests a new window
        """
        newviewer = viewerwindow.ViewerWindow()
        newviewer.show()

        # connect signals
        self.connectSignals(newviewer)

        self.viewers.append(newviewer)

        # call any plugins
        if self.pluginmanager is not None:
            self.pluginmanager.callAction(
                pluginmanager.PLUGIN_ACTION_NEWVIEWER, newviewer)

        # emit a signal so that application can do any customisation
        self.newViewerCreated.emit(newviewer)

        return newviewer

    def onNewQueryWindow(self, querywindow):
        """
        Called when the viewer starts a new query window
        """
        # call any plugins
        if self.pluginmanager is not None:
            self.pluginmanager.callAction(
                pluginmanager.PLUGIN_ACTION_NEWQUERY, querywindow)

    def getDesktopSize(self, screen):
        """
        Called at the start of the tiling operation.
        Default implementation just gets the size of the desktop.
        if overridden, return a QRect
        """
        if screen is None:
            return QApplication.desktop().availableGeometry()
        else:
            return screen.availableGeometry()

    def onTileWindows(self, nxside, nyside, screen):
        """
        Called when the user wants the windows to be tiled
        """
        # get the dimensions of the desktop
        desktop = self.getDesktopSize(screen)
        # getViewerList returns a temporary list so we can stuff around with it
        viewerList = self.getViewerList(screen)

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
        while len(viewerList) > 0:
            # work out the location we will use and find the viewer closest
            xloc = desktop.x() + viewerwidth * xcount
            yloc = desktop.y() + viewerheight * ycount

            def viewerKey(a):
                xdist = abs(a.x() - xloc)
                ydist = abs(a.y() - yloc)
                return math.sqrt(xdist * xdist + ydist * ydist)

            # sort by distance from this location
            viewerList = sorted(viewerList, key=viewerKey)
            # closest
            viewer = viewerList.pop(0)

            # remove any maximised states - window manager will not let
            # use resize
            state = viewer.windowState()
            if (state & Qt.WindowMaximized) == Qt.WindowMaximized:
                viewer.setWindowState(state ^ Qt.WindowMaximized)
            # resize takes the area without the frame so we correct for that
            viewer.resize(viewerwidth - framewidth, viewerheight - frameheight)
            # remember that taskbar etc mean that we might not want 
            # to start at 0,0
            viewer.move(xloc, yloc)

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
        # paint any windows that are ready
        QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)
        for viewer in self.getViewerList():
            # we use the id() of the widget to 
            # identify them.
            if id(viewer.viewwidget) != obj.senderid:
                viewer.viewwidget.doGeolinkMove(obj.easting, obj.northing, 
                                    obj.metresperwinpix)

            # paint any windows that are ready
            QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

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

    def writeViewersState(self, fileobj):
        """
        Gets the state of all the viewers (location, layers etc) as a json encoded
        string and write it to fileobj
        """
        from .viewerlayers import ViewerQueryPointLayer, ViewerFeatureVectorLayer
        viewers = self.getViewerList()

        # see if we can get a GeolinkInfo
        # should all be the same since geolinked
        geolinkStr = 'None'
        for viewer in viewers:
            info = viewer.viewwidget.getGeolinkInfo()
            if info is not None:
                geolinkStr = info.toString()
                break
        
        s = json.dumps({'name': 'tuiview', 'nviewers': len(viewers), 
                        'geolink': geolinkStr}) + '\n'
        fileobj.write(s)
        for viewer in viewers:
            pos = viewer.pos()
            # we have to be careful since not all layer types
            # are saved. Must be a better way...
            nlayers = 0
            for layer in viewer.viewwidget.layers.layers:
                if (not isinstance(layer, ViewerQueryPointLayer) and 
                        not isinstance(layer, ViewerFeatureVectorLayer)):
                    nlayers += 1

            viewerDict = {'nlayers': nlayers, 'x': pos.x(), 'y': pos.y(), 
                'width': viewer.width(), 'height': viewer.height()}
            winHandle = viewer.windowHandle()
            if hasattr(winHandle, 'screen'):
                # save which screen this is on if available
                screen = winHandle.screen()
                if screen is not None:
                    viewerDict['screen'] = screen.name()
                
            s = json.dumps(viewerDict) + '\n'
            fileobj.write(s)

            # now get the layers to write themselves out
            viewer.viewwidget.layers.toFile(fileobj)

    def readViewersState(self, fileobj):
        """
        Reads viewer state from the fileobj and restores viewers 
        """
        from . import viewerwidget
        headerDict = json.loads(fileobj.readline())
        if 'name' not in headerDict or headerDict['name'] != 'tuiview':
            raise ValueError('File not written by tuiview')

        geolinkStr = headerDict['geolink']
        if geolinkStr != 'None':
            geolink = viewerwidget.GeolinkInfo.fromString(geolinkStr)
        else:
            geolink = None
            
        # get all the screens connected
        screenDict = {}
        if hasattr(QApplication, 'screens'):
            screens = QApplication.screens()
            for screen in screens:
                screenDict[screen.name()] = screen

        for n in range(headerDict['nviewers']):
            viewer = self.onNewWindow()
            viewerDict = json.loads(fileobj.readline())
            viewer.move(viewerDict['x'], viewerDict['y'])
            viewer.resize(viewerDict['width'], viewerDict['height'])

            viewer.addLayersFromJSONFile(fileobj, viewerDict['nlayers'])
            
            if 'screen' in viewerDict:
                winHandle = viewer.windowHandle()
                if hasattr(winHandle, 'setScreen'):
                    screenName = viewerDict['screen']
                    if screenName in screenDict:
                        screen = screenDict[screenName]
                        winHandle.setScreen(screen)
                
        # set the location if any
        if geolink is not None:
            self.onMove(geolink)
