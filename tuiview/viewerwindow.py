
"""
Main Window of the TuiView application. Contains
the ViewerWidget, menus, toolbars and status bars.
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

import os
import sys
import glob
import traceback
from PyQt5.QtWidgets import QMainWindow, QAction, QFileDialog, QDialog
from PyQt5.QtWidgets import QMessageBox, QProgressBar, QToolButton
from PyQt5.QtWidgets import QMenu, QLineEdit, QPushButton
from PyQt5.QtGui import QIcon, QColor
from PyQt5.QtCore import QSettings, QSize, QPoint, pyqtSignal, Qt
from PyQt5.QtCore import QCoreApplication, QEventLoop, QTimer

from . import viewerresources  # noqa
from . import archivereader
from . import viewerwidget
from . import viewererrors
from . import querywindow
from .viewerstrings import MESSAGE_TITLE

# set to True to see traceback when file open fails
SHOW_TRACEBACK = (os.getenv('TUIVIEW_SHOW_TRACEBACK', '0') == '1')

DEFAULT_XSIZE = 400
DEFAULT_YSIZE = 400
DEFAULT_XPOS = 200
DEFAULT_YPOS = 200

MESSAGE_TIMEOUT = 2000
DEFAULT_DRIVER = os.getenv('TUIVIEW_DFLT_DRIVER')

# Populate this list the first time the
# file open dialog shown.
GDAL_FILTERS = None

# Set up a dictionary of filters not in GDAL (ENVI files with various extensions)
NON_GDAL_FILTERS = {'BIL': 'ENVI BIL (*.bil)',
                    'BSQ': 'ENVI BSQ (*.bsq)',
                    'DEM': 'ENVI DEM (*.dem)',
                    'RAW': 'ENVI RAW (*.raw)'}


def createFilter(driver):
    """
    Given a GDAL driver, creates the Qt QFileDialog
    compatible filter for the file type
    """
    from osgeo.gdal import DMD_LONGNAME, DMD_EXTENSION
    drivermeta = driver.GetMetadata()
    name = 'Image Files'
    if DMD_LONGNAME in drivermeta:
        name = drivermeta[DMD_LONGNAME]
        # get rid of any stuff in brackets - seems to
        # confuse Qt 4.x
        firstbracket = name.find('(')
        if firstbracket != -1:
            name = name[:firstbracket]
    qfilter = '*'
    if DMD_EXTENSION in drivermeta:
        qfilter = drivermeta[DMD_EXTENSION]
    return "%s (*.%s)" % (name, qfilter)


def populateFilters(defaultDriver=DEFAULT_DRIVER):
    """
    Create a list of file filters for QFileDialog for
    all the GDAL supported files.
    If a default driver is specified it goes first on the list
    """
    from osgeo import gdal
    global GDAL_FILTERS
    # only bother if it hasn't been populated already
    if GDAL_FILTERS is None:
        GDAL_FILTERS = []

        # if we have a default driver do it first
        if defaultDriver is not None:
            driver = gdal.GetDriverByName(defaultDriver)
            if driver is not None:
                qfilter = createFilter(driver)
                GDAL_FILTERS.append(qfilter)
            else:
                # If there is no GDAL driver try non-GDAL drivers dict
                try:
                    qfilter = NON_GDAL_FILTERS[defaultDriver]
                    GDAL_FILTERS.append(qfilter)
                except KeyError:
                    pass

        # add all files next
        GDAL_FILTERS.append("All files (*)")

        # just go thru them all and create filters
        for count in range(gdal.GetDriverCount()):
            driver = gdal.GetDriver(count)
            # we have already done the default driver
            # and it looks a bit silly if it is in there again
            if defaultDriver is None or driver.ShortName != defaultDriver:
                qfilter = createFilter(driver)
                GDAL_FILTERS.append(qfilter)

        # Now add non-GDAL filters
        for qfilter in NON_GDAL_FILTERS.values():
            GDAL_FILTERS.append(qfilter)


class WildcardFileDialog(QFileDialog):
    """
    Our version of the Qt Filedialog thathas an "Expand Wildcards" button.
    """
    def __init__(self, parent):
        QFileDialog.__init__(self, parent)
        # On Windows etc, ensure that the Qt dialog is used 
        # so our logic for working with widgets works...
        self.setOption(QFileDialog.DontUseNativeDialog)
        
        # create our button
        self.expandButton = QPushButton("&Expand Wildcards", self)
        self.expandButton.clicked.connect(self.expandWildcards)
        
        # add another row with the button in it on the right hand side
        layout = self.layout()
        layout.addWidget(self.expandButton, layout.rowCount(), 
                        layout.columnCount() - 1)

        # search for the line edit widgets for the filenames
        # For some reason, selectFile() doesn't work when called 
        # from a keyboard shortcut
        self.fnameTextWidget = None
        for row in range(layout.rowCount()):
            for col in range(layout.columnCount()):
                item = layout.itemAtPosition(row, col)
                if item is not None:
                    widget = item.widget()
                    if isinstance(widget, QLineEdit):
                        self.fnameTextWidget = widget
        
    def expandWildcards(self):
        """
        Expand Wildcard button has been clicked. 
        """
        fileList = self.selectedFiles()
        expandedList = []
        for fname in fileList:
            expanded = sorted(glob.iglob(fname))
            # quote every string
            expanded = ['"' + os.path.basename(e) + '"' for e in expanded]
            expandedList.extend(expanded)
         
        # for some reason, selectFile() doesn't work when called 
        # from a keyboard shortcut so set the 
        if self.fnameTextWidget is not None:
            self.fnameTextWidget.setText(' '.join(expandedList))


class ViewerWindow(QMainWindow):
    """
    Main window for viewer application. The ViewerWidget is 
    contained in the 'viewwidget' attribute.
    """
    # signals
    newWindowSig = pyqtSignal(name='newWindow')
    tileWindowsSig = pyqtSignal(int, int, name='tileWindows')
    newQueryWindowSig = pyqtSignal(querywindow.QueryDockWidget,
                            name='newQueryWindow')
    closeAllWindowsSig = pyqtSignal(name='closeAllWindows')
    # Don't know how to specify file objects...
    writeViewersState = pyqtSignal(object, name='writeViewersState')
    readViewersState = pyqtSignal(object, name='readViewersState')

    def __init__(self):
        QMainWindow.__init__(self)
        self.setWindowTitle(MESSAGE_TITLE)
        self.viewwidget = viewerwidget.ViewerWidget(self)

        # connect to the signals emmitted by the LUT/RAT via the LayerManager
        # so we can update our progress bar
        self.viewwidget.layers.newProgressSig.connect(self.newProgress)
        self.viewwidget.layers.endProgressSig.connect(self.endProgress)
        self.viewwidget.layers.newPercentSig.connect(self.newPercent)
        # so we can update the window title
        self.viewwidget.layers.topLayerChanged.connect(self.updateWindowTitle)
        # general messages from the widget
        self.viewwidget.showStatusMessage.connect(self.showStatusMessage)
        # the signal that gets sent when active tool changed so we can update
        # gui if querywindow engages a tool
        self.viewwidget.activeToolChanged.connect(self.activeToolChanged)

        self.setCentralWidget(self.viewwidget)

        self.setupActions()
        self.setupMenus()
        self.setupToolbars()
        self.setupStatusBar()

        # our layer window so we can toggle it
        self.layerWindow = None

        self.restoreFromSettings()
        # set these values, just read from settings
        self.viewwidget.setMouseScrollWheelAction(self.mouseWheelZoom)
        self.viewwidget.setBackgroundColor(self.backgroundColor)
        if self.settingQueryOnlyDisplayed:
            self.queryOnlyDisplayedAct.setChecked(True)
        if self.settingArrangeLayersOpen:
            self.arrangeLayers()

        self.showStatusMessage("Ready")

        # number of query windows we have open.
        # if zero we need to start a new one when query
        # tool selected
        self.queryWindowCount = 0
        # same, but for profile window
        self.profileWindowCount = 0
        # same, but for vector query window
        self.vectorQueryWindowCount = 0

        # accept dropping files
        self.setAcceptDrops(True)

        # so if we are turning on a tool because another tool 
        # in another window has been turned on, we don't undo 
        # that tool being enabled. As oppossed to user unclicking
        # the tool
        self.suppressToolReset = False

    def resizeForWidgetSize(self, xsize, ysize):
        """
        Resizes this window so that the widget is the given size
        Takes into account the border etc
        """
        viewerSize = self.size()
        widgetSize = self.viewwidget.viewport().size()
        borderWidth = viewerSize.width() - widgetSize.width()
        borderHeight = viewerSize.height() - widgetSize.height()

        # resize it to desired size
        self.resize(xsize + borderWidth, ysize + borderHeight)
        
    def updateWindowTitle(self, layer):
        """
        called in response to the topLayerChanged(PyQt_PyObject) signal
        from the layers to say the top displayed layer has changed
        """
        if layer is not None:
            # just display the layer title
            self.setWindowTitle(layer.title)
        else:
            # nothing loaded
            self.setWindowTitle(MESSAGE_TITLE)

    def newProgress(self, string):
        """
        Called when we are about to start a new progress
        """
        self.statusBar().showMessage(string)
        self.progressWidget.setValue(0)
        self.progressWidget.setVisible(True)
        self.setCursor(Qt.WaitCursor)  # look like we are busy
        # process any events show gets shown while busy
        QCoreApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

    def endProgress(self):
        """
        Called when a progress run has finished
        """
        self.statusBar().clearMessage()
        self.progressWidget.setVisible(False)
        self.setCursor(Qt.ArrowCursor)  # look like we are finished
        # process any events show gets shown while busy
        QCoreApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

    def newPercent(self, percent):
        """
        New progress value
        """
        self.progressWidget.setValue(percent)
        # process any events show gets shown while busy
        QCoreApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

    def showStatusMessage(self, message):
        """
        Helper method to show a message for a short period of time
        """
        self.statusBar().showMessage(message, MESSAGE_TIMEOUT)

    def activeToolChanged(self, obj):
        """
        Called when the active tool changed. If we didn't cause it
        then show our tools as disabled
        """
        if obj.senderid != id(self):
            self.suppressToolReset = True
            for tool in self.toolActions:
                tool.setChecked(False)
            self.suppressToolReset = False

    def restoreFromSettings(self):
        """
        Restore any settings from last time
        n.b. need to rationalize with preferences window
        """
        settings = QSettings()
        settings.beginGroup('ViewerWindow')

        defaultsize = QSize(DEFAULT_XSIZE, DEFAULT_YSIZE)
        self.resize(settings.value("size", defaultsize))

        defaultpos = QPoint(DEFAULT_XPOS, DEFAULT_YPOS)
        self.move(settings.value("pos", defaultpos))

        settings.endGroup()

        settings.beginGroup('ViewerMouse')
        value = settings.value("mousescroll", True, bool)
        self.mouseWheelZoom = value
        settings.endGroup()

        settings.beginGroup('ViewerBackground')
        value = settings.value("color", QColor(Qt.black), QColor)
        self.backgroundColor = value
        settings.endGroup()

        settings.beginGroup('StartupState')
        value = settings.value('QueryOnlyDisplayed', False, bool)
        self.settingQueryOnlyDisplayed = value

        value = settings.value('ArrangeLayersOpen', False, bool)
        self.settingArrangeLayersOpen = value
        settings.endGroup()

    def setupActions(self):
        """
        Creates all the actions for the Window
        """
        self.toolActions = []

        self.addRasterAct = QAction(self, triggered=self.addRaster)
        self.addRasterAct.setText("&Add Raster")
        self.addRasterAct.setStatusTip("Open a GDAL supported image")
        self.addRasterAct.setShortcut("CTRL+O")
        self.addRasterAct.setIcon(QIcon(":/viewer/images/addraster.png"))
        self.addRasterAct.setIconVisibleInMenu(True)

        self.addVectorFileAct = QAction(self, triggered=self.addVectorFile)
        self.addVectorFileAct.setText("Add Vector &File")
        self.addVectorFileAct.setStatusTip("Open an OGR supported vector file")
        self.addVectorFileAct.setShortcut("CTRL+V")
        self.addVectorFileAct.setIcon(QIcon(":/viewer/images/addvector.png"))
        self.addVectorFileAct.setIconVisibleInMenu(True)

        self.addVectorDirAct = QAction(self, triggered=self.addVectorDir)
        self.addVectorDirAct.setText("Add Vector &Directory")
        self.addVectorDirAct.setStatusTip("Open an OGR supported vector directory")
        self.addVectorDirAct.setIcon(QIcon(":/viewer/images/addvector.png"))
        self.addVectorDirAct.setIconVisibleInMenu(True)

        self.addVectorDBAct = QAction(self, triggered=self.addVectorDB)
        self.addVectorDBAct.setText("Add Vector Data&base")
        self.addVectorDBAct.setStatusTip(
            "Open a layer from an OGR supported database")
        self.addVectorDBAct.setIcon(QIcon(":/viewer/images/addvector.png"))
        self.addVectorDBAct.setIconVisibleInMenu(True)

        self.vectorMenu = QMenu()
        self.vectorMenu.setTitle("Add Vector")
        self.vectorMenu.addAction(self.addVectorFileAct)
        self.vectorMenu.addAction(self.addVectorDirAct)
        self.vectorMenu.addAction(self.addVectorDBAct)

        self.removeLayerAct = QAction(self, triggered=self.removeLayer)
        self.removeLayerAct.setText("&Remove Layer")
        self.removeLayerAct.setStatusTip("Remove top layer")
        self.removeLayerAct.setShortcut("CTRL+R")
        self.removeLayerAct.setIcon(QIcon(":/viewer/images/removelayer.png"))
        self.removeLayerAct.setIconVisibleInMenu(True)

        self.newWindowAct = QAction(self, triggered=self.newWindow)
        self.newWindowAct.setText("&New Window")
        self.newWindowAct.setStatusTip("Create a new geo linked window")
        self.newWindowAct.setShortcut("CTRL+N")
        self.newWindowAct.setIcon(QIcon(":/viewer/images/newwindow.png"))
        self.newWindowAct.setIconVisibleInMenu(True)

        self.tileWindowsAct = QAction(self, triggered=self.tileWindows)
        self.tileWindowsAct.setText("&Tile Windows...")
        self.tileWindowsAct.setStatusTip("Tile all open windows")
        self.tileWindowsAct.setShortcut("CTRL+I")

        self.defaultStretchAct = QAction(self, triggered=self.defaultStretch)
        self.defaultStretchAct.setText("&Default Stretch...")
        self.defaultStretchAct.setStatusTip("Set default stretches")
        self.defaultStretchAct.setShortcut("CTRL+D")

        self.stretchAct = QAction(self, triggered=self.editStretch)
        self.stretchAct.setText("S&tretch")
        self.stretchAct.setStatusTip("Edit current stretch")
        self.stretchAct.setShortcut("CTRL+T")
        self.stretchAct.setEnabled(False)  # until a file is opened

        self.panAct = QAction(self, toggled=self.pan)
        self.panAct.setText("&Pan")
        self.panAct.setStatusTip("Pan")
        self.panAct.setShortcut("CTRL+P")
        self.panAct.setCheckable(True)
        self.panAct.setIcon(QIcon(":/viewer/images/pan.png"))
        self.panAct.setIconVisibleInMenu(True)
        self.toolActions.append(self.panAct)

        self.zoomInAct = QAction(self, toggled=self.zoomIn)
        self.zoomInAct.setText("Zoom &In")
        self.zoomInAct.setStatusTip("Zoom In")
        self.zoomInAct.setShortcut("CTRL++")
        self.zoomInAct.setCheckable(True)
        self.zoomInAct.setIcon(QIcon(":/viewer/images/zoomin.png"))
        self.zoomInAct.setIconVisibleInMenu(True)
        self.toolActions.append(self.zoomInAct)

        self.zoomOutAct = QAction(self, toggled=self.zoomOut)
        self.zoomOutAct.setText("Zoom &Out")
        self.zoomOutAct.setStatusTip("Zoom Out")
        self.zoomOutAct.setShortcut("CTRL+-")
        self.zoomOutAct.setCheckable(True)
        self.zoomOutAct.setIcon(QIcon(":/viewer/images/zoomout.png"))
        self.zoomOutAct.setIconVisibleInMenu(True)
        self.toolActions.append(self.zoomOutAct)

        self.zoomNativeAct = QAction(self, triggered=self.zoomNative)
        self.zoomNativeAct.setText("Zoom to &Native")
        self.zoomNativeAct.setStatusTip("Zoom to Native Resolution")
        self.zoomNativeAct.setShortcut("CTRL+1")
        self.zoomNativeAct.setIcon(QIcon(":/viewer/images/zoomnative.png"))
        self.zoomNativeAct.setIconVisibleInMenu(True)

        self.zoomFullExtAct = QAction(self, triggered=self.zoomFullExtent)
        self.zoomFullExtAct.setText("Zoom to &Full Extent")
        self.zoomFullExtAct.setStatusTip("Zoom to Full Extent")
        self.zoomFullExtAct.setShortcut("CTRL+F")
        self.zoomFullExtAct.setIcon(QIcon(":/viewer/images/zoomfullextent.png"))
        self.zoomFullExtAct.setIconVisibleInMenu(True)

        self.followExtentAct = QAction(self, toggled=self.followExtent)
        self.followExtentAct.setText("Follow &Extent")
        self.followExtentAct.setStatusTip("Follow geolinked extent")
        self.followExtentAct.setShortcut("CTRL+E")
        self.followExtentAct.setCheckable(True)
        self.followExtentAct.setChecked(True)  # by default to match viewerwidget
        self.followExtentAct.setIcon(QIcon(":/viewer/images/followextents.png"))
        self.followExtentAct.setIconVisibleInMenu(True)

        self.queryAct = QAction(self, toggled=self.query)
        self.queryAct.setText("&Query Tool")
        self.queryAct.setStatusTip("Start Query Tool")
        self.queryAct.setShortcut("CTRL+U")
        self.queryAct.setCheckable(True)
        self.queryAct.setIcon(QIcon(":/viewer/images/query.png"))
        self.queryAct.setIconVisibleInMenu(True)

        self.newQueryAct = QAction(self, triggered=self.newQueryWindow)
        self.newQueryAct.setText("New Query &Window")
        self.newQueryAct.setStatusTip("Open New Query Window")
        self.newQueryAct.setShortcut("CTRL+W")

        self.vectorQueryAct = QAction(self, toggled=self.vectorQuery)
        self.vectorQueryAct.setText("&Vector Query Tool")
        self.vectorQueryAct.setStatusTip("Start Vector Query Tool")
        self.vectorQueryAct.setShortcut("CTRL+C")
        self.vectorQueryAct.setCheckable(True)
        self.vectorQueryAct.setIcon(QIcon(":/viewer/images/queryvector.png"))
        self.vectorQueryAct.setIconVisibleInMenu(True)

        self.newVectorQueryAct = QAction(self, 
                                        triggered=self.newVectorQueryWindow)
        self.newVectorQueryAct.setText("New Vector Query &Window")
        self.newVectorQueryAct.setStatusTip("Open New Vector Query Window")

        self.queryOnlyDisplayedAct = QAction(self, 
                                        toggled=self.queryOnlyDisplayed)
        self.queryOnlyDisplayedAct.setText("&Query Only Displayed Layers")
        self.queryOnlyDisplayedAct.setCheckable(True)
        self.queryOnlyDisplayedAct.setShortcut("CTRL+B")
        self.queryOnlyDisplayedAct.setStatusTip(
            "Query Only Displayed Layers with Query Window")

        self.exitAct = QAction(self, triggered=self.close)
        self.exitAct.setText("&Close")
        self.exitAct.setStatusTip("Close this window")
        self.exitAct.setShortcut("CTRL+Q")

        self.closeAllWindows = QAction(self, triggered=self.closeAll)
        self.closeAllWindows.setText("C&lose All")
        self.closeAllWindows.setStatusTip("Close all windows")
        self.closeAllWindows.setShortcut("SHIFT+CTRL+Q")

        self.preferencesAct = QAction(self, triggered=self.setPreferences)
        self.preferencesAct.setText("&Preferences")
        self.preferencesAct.setStatusTip("Edit Preferences")
        self.preferencesAct.setShortcut("CTRL+L")

        self.flickerAct = QAction(self, triggered=self.flicker)
        self.flickerAct.setText("&Flicker")
        self.flickerAct.setStatusTip("Flicker top 2 layers")
        self.flickerAct.setShortcut("CTRL+K")
        self.flickerAct.iconOn = QIcon(":/viewer/images/flickeron.png")
        self.flickerAct.iconOff = QIcon(":/viewer/images/flickeroff.png")
        self.flickerAct.setIcon(self.flickerAct.iconOn)
        self.flickerAct.setIconVisibleInMenu(True)

        self.layerAct = QAction(self, triggered=self.arrangeLayers)
        self.layerAct.setText("Arrange La&yers")
        self.layerAct.setStatusTip("Arrange Layers")
        self.layerAct.setShortcut("CTRL+Y")
        self.layerAct.setIcon(QIcon(":/viewer/images/layers.png"))
        self.layerAct.setIconVisibleInMenu(True)

        self.profileAct = QAction(self, toggled=self.profile)
        self.profileAct.setText("&Profile/Ruler")
        self.profileAct.setStatusTip("Start Profile/Ruler tool")
        self.profileAct.setShortcut("CTRL+A")
        self.profileAct.setCheckable(True)
        self.profileAct.setIcon(QIcon(":/viewer/images/profileruler.png"))
        self.profileAct.setIconVisibleInMenu(True)
        self.toolActions.append(self.profileAct)

        self.newProfileAct = QAction(self, triggered=self.newProfile)
        self.newProfileAct.setText("New P&rofile/Ruler Window")
        self.newProfileAct.setStatusTip("Open New Profile/Ruler Window")
        self.newProfileAct.setShortcut("CTRL+S")

        self.propertiesAct = QAction(self, triggered=self.properties)
        self.propertiesAct.setText("Properties")
        self.propertiesAct.setStatusTip("Show Properties of top layer")
        self.propertiesAct.setShortcut("CTRL+X")
        self.propertiesAct.setIcon(QIcon(":/viewer/images/properties.png"))
        self.propertiesAct.setIconVisibleInMenu(True)

        self.timeseriesForwardAct = QAction(self, 
                        triggered=self.viewwidget.timeseriesForward)
        self.timeseriesForwardAct.setShortcut(".")
        self.timeseriesForwardAct.setText("Timeseries Forward")
        self.timeseriesForwardAct.setStatusTip(
            "Go forward through timeseries of images")

        self.timeseriesBackwardAct = QAction(self, 
                        triggered=self.viewwidget.timeseriesBackward)
        self.timeseriesBackwardAct.setShortcut(",")
        self.timeseriesBackwardAct.setText("Timeseries Backward")
        self.timeseriesBackwardAct.setStatusTip(
            "Go backward through timeseries of images")

        self.saveCurrentViewAct = QAction(self, triggered=self.saveCurrentView)
        self.saveCurrentViewAct.setText("Save Current Display")
        self.saveCurrentViewAct.setStatusTip(
            "Save the contents of the current display as an image file")

        self.saveCurrentViewersState = QAction(self, 
                            triggered=self.saveViewersState)
        self.saveCurrentViewersState.setText("Save State of All Viewers")
        self.saveCurrentViewersState.setStatusTip(
            "Save state of Viewers to a file so they can be restored")

        self.loadCurrentViewersState = QAction(self, 
                            triggered=self.loadViewersState)
        self.loadCurrentViewersState.setText("Load State of Viewers")
        self.loadCurrentViewersState.setStatusTip(
            "Restore state of viewers previously saved")

        self.aboutAct = QAction(self, triggered=self.about)
        self.aboutAct.setText("&About")
        self.aboutAct.setStatusTip("Show author and version information")

        # Actions just for keyboard shortcuts

        self.moveUpAct = QAction(self, triggered=self.moveUp)
        self.moveUpAct.setShortcut(Qt.CTRL + Qt.Key_Up)

        self.moveDownAct = QAction(self, triggered=self.moveDown)
        self.moveDownAct.setShortcut(Qt.CTRL + Qt.Key_Down)

        self.moveLeftAct = QAction(self, triggered=self.moveLeft)
        self.moveLeftAct.setShortcut(Qt.CTRL + Qt.Key_Left)

        self.moveRightAct = QAction(self, triggered=self.moveRight)
        self.moveRightAct.setShortcut(Qt.CTRL + Qt.Key_Right)

        self.addAction(self.moveUpAct)
        self.addAction(self.moveDownAct)
        self.addAction(self.moveLeftAct)
        self.addAction(self.moveRightAct)

    def setupMenus(self):
        """
        Creates the menus and adds the actions to them
        """
        fileMenu = self.menuBar().addMenu("&File")
        fileMenu.addAction(self.addRasterAct)
        fileMenu.addMenu(self.vectorMenu)
        fileMenu.addAction(self.removeLayerAct)
        fileMenu.addAction(self.layerAct)
        fileMenu.addAction(self.newWindowAct)
        fileMenu.addAction(self.queryOnlyDisplayedAct)
        fileMenu.addAction(self.tileWindowsAct)
        fileMenu.addAction(self.defaultStretchAct)
        fileMenu.addAction(self.saveCurrentViewAct)
        fileMenu.addAction(self.saveCurrentViewersState)
        fileMenu.addAction(self.loadCurrentViewersState)
        fileMenu.addAction(self.propertiesAct)
        fileMenu.addAction(self.exitAct)
        fileMenu.addAction(self.closeAllWindows)
        fileMenu.insertSeparator(self.exitAct)

        editMenu = self.menuBar().addMenu("&Edit")
        editMenu.addAction(self.stretchAct)
        editMenu.addAction(self.preferencesAct)

        viewMenu = self.menuBar().addMenu("&View")
        viewMenu.addAction(self.panAct)
        viewMenu.addAction(self.zoomInAct)
        viewMenu.addAction(self.zoomOutAct)
        viewMenu.addAction(self.zoomNativeAct)
        viewMenu.addAction(self.zoomFullExtAct)
        viewMenu.addAction(self.followExtentAct)
        viewMenu.addAction(self.timeseriesForwardAct)
        viewMenu.addAction(self.timeseriesBackwardAct)

        toolMenu = self.menuBar().addMenu("&Tools")
        toolMenu.addAction(self.queryAct)
        toolMenu.addAction(self.newQueryAct)
        toolMenu.addAction(self.vectorQueryAct)
        toolMenu.addAction(self.newVectorQueryAct)
        toolMenu.addAction(self.profileAct)
        toolMenu.addAction(self.newProfileAct)
        toolMenu.addAction(self.flickerAct)

        helpMenu = self.menuBar().addMenu("&Help")
        helpMenu.addAction(self.aboutAct)

    def setupToolbars(self):
        """
        Creates the toolbars and adds the actions to them
        """
        fileToolbar = self.addToolBar("File")
        fileToolbar.addAction(self.addRasterAct)
        vectorToolButton = QToolButton()
        vectorToolButton.setMenu(self.vectorMenu)
        vectorToolButton.setPopupMode(QToolButton.MenuButtonPopup)
        vectorToolButton.setIcon(QIcon(":/viewer/images/addvector.png"))
        vectorToolButton.setDefaultAction(self.addVectorFileAct)
        fileToolbar.addWidget(vectorToolButton)

        fileToolbar.addAction(self.removeLayerAct)
        fileToolbar.addAction(self.layerAct)
        fileToolbar.addAction(self.newWindowAct)
        fileToolbar.addAction(self.propertiesAct)

        viewToolbar = self.addToolBar("View")
        viewToolbar.addAction(self.panAct)
        viewToolbar.addAction(self.zoomInAct)
        viewToolbar.addAction(self.zoomOutAct)
        viewToolbar.addAction(self.zoomNativeAct)
        viewToolbar.addAction(self.zoomFullExtAct)
        viewToolbar.addAction(self.followExtentAct)

        toolToolbar = self.addToolBar("Tools")
        toolToolbar.addAction(self.queryAct)
        toolToolbar.addAction(self.vectorQueryAct)
        toolToolbar.addAction(self.profileAct)
        toolToolbar.addAction(self.flickerAct)

    def setupStatusBar(self):
        """
        Sets up the status bar
        """
        statusbar = self.statusBar()
        statusbar.setSizeGripEnabled(True)
        self.progressWidget = QProgressBar(statusbar)
        self.progressWidget.setMinimum(0)
        self.progressWidget.setMaximum(100)
        self.progressWidget.setVisible(False)
        statusbar.addPermanentWidget(self.progressWidget)

    def newWindow(self):
        """
        Triggered when user wants a new window. Send signal
        to GeolinkedViewers class (if there is one!)
        """
        self.newWindowSig.emit()

    def tileWindows(self):
        """
        Triggered when user wants to tile windows. Display
        dialog to allow number to be selected, then send signal
        to GeolinkedViewers class (if there is one!)
        """
        from .tiledialog import TileDialog
        dlg = TileDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            xnum, ynum = dlg.getValues()
            self.tileWindowsSig.emit(xnum, ynum)

    def defaultStretch(self):
        """
        Show the default stretch dialog
        """
        from . import stretchdialog
        dlg = stretchdialog.StretchDefaultsDialog(self)
        dlg.exec_()

    def addRaster(self):
        """
        User has asked to open a file. Show file
        dialog and open file
        """
        populateFilters()
        # Note: use our modified dialog with wildcard support
        dlg = WildcardFileDialog(self)
        dlg.setNameFilters(GDAL_FILTERS)
        dlg.setFileMode(QFileDialog.ExistingFiles)
        # set last dir
        layer = self.viewwidget.layers.getTopRasterLayer()
        if layer is not None:
            dir = os.path.dirname(layer.filename)
            if dir == '':
                dir = os.getcwd()
        else:
            # or cwd
            dir = os.getcwd()

        dlg.setDirectory(dir)

        if dlg.exec_() == QDialog.Accepted:
            file_list = dlg.selectedFiles()
            for fname in archivereader.file_list_to_archive_strings(file_list):
                self.addRasterInternal(fname)

    def addVectorFile(self):
        """
        User wants to add a vector layer. OGR seems to have no
        way to determine extensions...
        From a file.
        """
        dlg = QFileDialog(self)
        dlg.setNameFilter("OGR Files (*)")
        dlg.setFileMode(QFileDialog.ExistingFile)
        # set last dir
        layer = self.viewwidget.layers.getTopVectorLayer()
        if layer is not None:
            dir = os.path.dirname(layer.filename)
            if dir == '':
                dir = os.getcwd()
        else:
            # or cwd
            dir = os.getcwd()

        dlg.setDirectory(dir)

        if dlg.exec_() == QDialog.Accepted:
            fname = dlg.selectedFiles()[0]
            self.addVectorInternal(fname)

    def addVectorDir(self):
        """
        Add a vector from a directory (filegdb/covereage)
        """
        # set last dir
        layer = self.viewwidget.layers.getTopVectorLayer()
        if layer is not None:
            olddir = os.path.dirname(layer.filename)
            if olddir == '':
                olddir = os.getcwd()
        else:
            # or cwd
            olddir = os.getcwd()

        dir = QFileDialog.getExistingDirectory(self, "Choose vector directory",
            directory=olddir,
            options=QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks)
        if dir != "":
            self.addVectorInternal(dir)

    def addVectorDB(self):
        """
        Add a vector from a database - ask user for connection string
        """
        from PyQt5.QtWidgets import QInputDialog
        (con, ok) = QInputDialog.getText(self, MESSAGE_TITLE, 
                                "Enter OGR connection string (without quotes)")
        if ok and con != "":
            self.addVectorInternal(con)

    @staticmethod
    def findDefaultStretchForDataset(gdaldataset):
        """
        Attempts to find the default stretch that matches the
        given gdal dataset. Returns None on failure.
        """
        from . import stretchdialog
        stretch = None
        defaultList = stretchdialog.StretchDefaultsDialog.fromSettings()
        for rule in defaultList:
            if rule.isMatch(gdaldataset):
                stretch = rule.stretch
                break
        return stretch

    def addRasterInternal(self, fname, stretch=None, showError=True):
        """
        Actually to the file opening. If stretch is None
        is is determined using our automatic scheme.
        if showError is True a message box will be displayed with any error
        if false an exception will be raised.
        """
        lut = None
        # first open the dataset
        from osgeo import gdal
        try:
            gdal.PushErrorHandler('CPLQuietErrorHandler')
            gdaldataset = gdal.Open(fname)
        except RuntimeError as err:
            if SHOW_TRACEBACK:
                traceback.print_exc()
            if showError:
                msg = "Unable to open %s\n%s" % (fname, err)
                QMessageBox.critical(self, MESSAGE_TITLE, msg)
                return
            else:
                raise

        if stretch is None:
            # first see if it has a stretch saved in the file
            from . import viewerstretch
            stretch = viewerstretch.ViewerStretch.readFromGDAL(gdaldataset)
            if stretch is None:
                # ok was none, read in the default stretches
                stretch = self.findDefaultStretchForDataset(gdaldataset)
            else:
                # if there was a stretch, see if we can read a LUT also
                from . import viewerLUT
                lut = viewerLUT.ViewerLUT.createFromGDAL(gdaldataset, stretch)

            # couldn't find anything. Tell user and
            # open default stretch dialog
            if stretch is None:
                del gdaldataset
                msg = ("File has no stretch saved and none of the default " + 
                "stretches match\nThe default stretch dialog will now open.")
                QMessageBox.warning(self, MESSAGE_TITLE, msg)
                self.defaultStretch()
                return

        # now open it for real
        try:
            self.viewwidget.addRasterLayer(gdaldataset, stretch, lut)
        except viewererrors.ProjectionMismatch:
            # as the user if they really want to go ahead
            btn = QMessageBox.question(self, MESSAGE_TITLE, 
                """Projection is different to existing file(s). 
Results may be incorrect. Do you wish to go ahead anyway?""", 
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if btn == QMessageBox.Yes:
                # try again with the flag
                try:
                    self.viewwidget.addRasterLayer(gdaldataset, stretch, lut,
                            ignoreProjectionMismatch=True)
                except Exception as e:
                    if SHOW_TRACEBACK:
                        traceback.print_exc()
                    if showError:
                        QMessageBox.critical(self, MESSAGE_TITLE, str(e))
                    else:
                        raise
        except viewererrors.InvalidStretch:
            # probably band referred to in stretch no longer exists
            # display error and fall back on default stretch
            QMessageBox.information(self, MESSAGE_TITLE,
                """Saved stretch refers to invalid band(s).
File will now be opened using default stretch""")

            stretch = self.findDefaultStretchForDataset(gdaldataset)
            if stretch is None:
                del gdaldataset
                msg = ("File has no stretch saved and none of the default " + 
                "stretches match\nThe default stretch dialog will now open.")
                QMessageBox.warning(self, MESSAGE_TITLE, msg)
                self.defaultStretch()
                return

            # now call this function again with default stretch
            del gdaldataset
            self.addRasterInternal(fname, stretch=stretch)

        except Exception as e:
            if SHOW_TRACEBACK:
                traceback.print_exc()
            if showError:
                QMessageBox.critical(self, MESSAGE_TITLE, str(e))
            else:
                raise

        # allow the stretch to be edited
        self.stretchAct.setEnabled(True)

    def addVectorInternal(self, path, layername=None, sql=None):
        """
        Open OGR dataset and layer and tell widget to add it 
        to the list of layers
        """
        from osgeo import ogr
        isResultSet = False
        try:
            ds = ogr.Open(str(path))
            if ds is None:
                msg = 'Unable to open %s' % path
                QMessageBox.critical(self, MESSAGE_TITLE, msg)
                return
                
            if layername is not None:
                lyr = ds.GetLayerByName(layername)
            elif sql is not None:
                lyr = ds.ExecuteSQL(sql)
            else:
                # ask them
                numLayers = ds.GetLayerCount()
                if numLayers == 0:
                    raise IOError("no valid layers")
                else:
                    from . import vectoropendialog
                    layerNames = []
                    for n in range(ds.GetLayerCount()):
                        name = ds.GetLayer(n).GetName()
                        layerNames.append(name)

                    dlg = vectoropendialog.VectorOpenDialog(self, layerNames)
                    if dlg.exec_() == QDialog.Accepted:
                        if dlg.isNamedLayer():
                            layername = dlg.getSelectedLayer()
                            lyr = ds.GetLayerByName(layername)
                        else:
                            sql = dlg.getSQL()
                            lyr = ds.ExecuteSQL(sql)
                            if lyr is None:
                                raise IOError("Invalid SQL")                                
                            isResultSet = True
                    else:
                        return None, None
                
            self.viewwidget.addVectorLayer(ds, lyr, resultSet=isResultSet,
                                        origSQL=sql)

        except Exception as e:
            if SHOW_TRACEBACK:
                traceback.print_exc()
            QMessageBox.critical(self, MESSAGE_TITLE, str(e))
            layername = None
            sql = None
            
        # return layername and sql so viewerapplication can use this for all 
        # viewers if needed
        return layername, sql

    def addLayersFromJSONFile(self, fileobj, nlayers):
        """
        Gets the widget to read layer definitions from fileobj and add them
        """
        try:
            self.viewwidget.addLayersFromJSONFile(fileobj, nlayers)
        except Exception as e:
            QMessageBox.critical(self, MESSAGE_TITLE, str(e))
        self.stretchAct.setEnabled(True)

    def removeLayer(self):
        """
        Remove the top most layer
        """
        self.viewwidget.removeLayer()

    def layerWindowClosed(self, window):
        """
        Reset state so we know we need to open another
        """
        self.layerWindow = None

    def arrangeLayers(self):
        """
        Toggle the LayerWindow
        """
        from . import layerwindow
        if self.layerWindow is None:
            self.layerWindow = layerwindow.LayerWindow(self, self.viewwidget)
            self.addDockWidget(Qt.LeftDockWidgetArea, self.layerWindow)
            # this works to prevent it trying to dock when dragging
            # but double click still works
            self.layerWindow.setAllowedAreas(Qt.NoDockWidgetArea) 
            self.layerWindow.layerWindowClosed.connect(self.layerWindowClosed)
        else:
            # remove
            self.removeDockWidget(self.layerWindow)
            self.layerWindow = None

    def editStretch(self):
        """
        Show the edit stretch dock window
        """
        from . import stretchdialog
        # should it just be visible layers?
        layer = self.viewwidget.layers.getTopRasterLayer()
        if layer is None:
            QMessageBox.critical(self, MESSAGE_TITLE, "No raster layer available")
        else:
            stretchDock = stretchdialog.StretchDockWidget(self, 
                                self.viewwidget, layer)
            self.addDockWidget(Qt.TopDockWidgetArea, stretchDock)
            # this works to prevent it trying to dock when dragging
            # but double click still works
            stretchDock.setAllowedAreas(Qt.NoDockWidgetArea) 

    def disableTools(self, ignoreTool=None):
        """
        Disable all tool actions apart from ignoreTool
        """
        tools = (self.panAct, self.zoomInAct, self.zoomOutAct, 
            self.queryAct, self.profileAct, self.vectorQueryAct)
        for tool in tools:
            if tool is not ignoreTool:
                tool.setChecked(False)

    def zoomIn(self, checked):
        """
        Zoom in tool selected.
        Tell view widget to operate in zoom mode.
        """
        if checked:
            # disable any other tools
            self.disableTools(self.zoomInAct)
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_ZOOMIN, 
                        id(self))
        elif not self.suppressToolReset:
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_NONE, 
                        id(self))

    def zoomOut(self, checked):
        """
        Zoom in tool selected.
        Tell view widget to operate in zoom mode.
        """
        if checked:
            # disable any other tools
            self.disableTools(self.zoomOutAct)
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_ZOOMOUT, 
                        id(self))
        elif not self.suppressToolReset:
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_NONE, 
                        id(self))

    def pan(self, checked):
        """
        Pan tool selected.
        Tell view widget to operate in pan mode.
        """
        if checked:
            # disable any other tools
            self.disableTools(self.panAct)
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_PAN, 
                        id(self))
        elif not self.suppressToolReset:
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_NONE, 
                        id(self))

    def moveFixedDist(self, xdist, ydist):
        layer = self.viewwidget.layers.getTopRasterLayer()
        if layer is not None:
            # stop panning and move viewport
            (pixNewX, pixNewY) = layer.coordmgr.display2pixel(xdist, 
                                                            ydist)
            # print 'panning'
            # print layer.coordmgr
            layer.coordmgr.setTopLeftPixel(pixNewX, pixNewY)
            layer.coordmgr.recalcBottomRight()
            # print layer.coordmgr
            # reset
            self.viewwidget.paintPoint.setX(0)
            self.viewwidget.paintPoint.setY(0)
            # redraw
            self.viewwidget.layers.makeLayersConsistent(layer)
            self.viewwidget.layers.updateImages()
            self.viewwidget.viewport().update()
            self.viewwidget.updateScrollBars()
            # geolink
            self.viewwidget.emitGeolinkMoved()

    def moveUp(self):
        self.moveFixedDist(0, -1 * self.viewwidget.size().height())

    def moveDown(self):
        self.moveFixedDist(0, self.viewwidget.size().height())

    def moveLeft(self):
        self.moveFixedDist(-1 * self.viewwidget.size().width(), 0)

    def moveRight(self):
        self.moveFixedDist(self.viewwidget.size().width(), 0)

    def zoomNative(self):
        """
        Tell the widget to zoom to native resolution
        """
        try:
            self.viewwidget.zoomNativeResolution()
        except Exception as e:
            QMessageBox.critical(self, MESSAGE_TITLE, str(e))

    def zoomFullExtent(self):
        """
        Tell the widget to zoom back to the full extent
        """
        try:
            self.viewwidget.zoomFullExtent()
        except Exception as e:
            QMessageBox.critical(self, MESSAGE_TITLE, str(e))

    def followExtent(self, state):
        """
        Called when user toggles the follow extent button.
        Tell the widget
        """
        self.viewwidget.setGeolinkFollowExtentAction(state)

    def query(self, checked):
        """
        Query tool selected.
        Tell view widget to operate in query mode.
        """
        if checked:
            # disable any other tools
            self.disableTools(self.queryAct)
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_QUERY, 
                    id(self))

            # if there is no query window currently open start one
            if self.queryWindowCount <= 0:
                self.newQueryWindow()
        else:
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_NONE, 
                    id(self))

    def queryClosed(self, queryDock):
        """
        Query dock window has been closed. Disconnect from
        locationSelected signal and decrement our count
        """
        if self.queryWindowCount > 0:
            self.viewwidget.locationSelected.disconnect(queryDock.locationSelected)
            self.queryWindowCount -= 1

    def newQueryWindow(self):
        """
        Create a new QueryDockWidget and connect signals
        and increment our count of these windows
        """
        queryDock = querywindow.QueryDockWidget(self, self.viewwidget)
        # can't pass Qt.NoDockWidgetArea in here
        self.addDockWidget(Qt.BottomDockWidgetArea, queryDock)
        queryDock.setFloating(True)  # detach so it isn't docked by default
        # this works to prevent it trying to dock when dragging
        # but double click still works
        queryDock.setAllowedAreas(Qt.NoDockWidgetArea) 
        
        # start over this window
        thispos = self.pos()
        x = thispos.x() + 100
        y = thispos.y() + 100
        queryDock.move(x, y)

        # connect it to signals emitted by the viewerwidget
        self.viewwidget.locationSelected.connect(queryDock.locationSelected)

        # grab the signal the queryDock sends when it is closed
        queryDock.queryClosed.connect(self.queryClosed)

        # increment our count
        self.queryWindowCount += 1

        # emit the signal back to geolinked viewers so that 
        # any plugins can be informed
        self.newQueryWindowSig.emit(queryDock)

    def vectorQuery(self, checked):
        """
        Vector Query tool selected
        Tell view widget to operate in query mode
        """
        if checked:
            self.disableTools(self.vectorQueryAct)
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_VECTORQUERY,
                    id(self))

            # if no window, start one
            if self.vectorQueryWindowCount <= 0:
                self.newVectorQueryWindow()
        else:
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_NONE, 
                        id(self))

    def newVectorQueryWindow(self):
        """
        Create a new VectorQueryDockWidget and connect signals
        and increment our count of these windows
        """
        from . import vectorquerywindow
        queryDock = vectorquerywindow.VectorQueryDockWidget(self)
        self.addDockWidget(Qt.BottomDockWidgetArea, queryDock)
        queryDock.setFloating(True)  # detach so it isn't docked by default
        # this works to prevent it trying to dock when dragging
        # but double click still works
        queryDock.setAllowedAreas(Qt.NoDockWidgetArea) 

        # start over this window
        thispos = self.pos()
        x = thispos.x() + 100
        y = thispos.y() + 100
        queryDock.move(x, y)

        # connect it to signals emitted by the viewerwidget
        self.viewwidget.vectorLocationSelected.connect(
            queryDock.vectorLocationSelected)

        # grab the signal the queryDock sends when it is closed
        queryDock.queryClosed.connect(self.vectorQueryClosed)

        # increment our count
        self.vectorQueryWindowCount += 1

        # emit the signal back to geolinked viewers so that 
        # any plugins can be informed
        self.newQueryWindowSig.emit(queryDock)

    def vectorQueryClosed(self, queryDock):
        """
        Query dock window has been closed. Disconnect from
        vectorLocationSelected signal and decrement our count
        """
        if self.vectorQueryWindowCount > 0:
            self.viewwidget.vectorLocationSelected.disconnect(
                queryDock.vectorLocationSelected)
            self.vectorQueryWindowCount -= 1

    def profile(self, checked):
        """
        Profile tool selected.
        Tell view widget to operate in polyline mode.
        """
        if checked:
            # disable any other tools
            self.disableTools(self.profileAct)
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_POLYLINE, 
                        id(self))

            # if there is no query window currently open start one
            if self.profileWindowCount <= 0:
                self.newProfile()
        else:
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_NONE, 
                        id(self))

    def newProfile(self):
        from . import profilewindow
        profileDock = profilewindow.ProfileDockWidget(self, self.viewwidget)
        self.addDockWidget(Qt.TopDockWidgetArea, profileDock)
        profileDock.setFloating(True)  # detach so it isn't docked by default
        # this works to prevent it trying to dock when dragging
        # but double click still works
        profileDock.setAllowedAreas(Qt.NoDockWidgetArea) 

        # start over this window
        thispos = self.pos()
        x = thispos.x() + 100
        y = thispos.y() + 100
        profileDock.move(x, y)

        # connect to the signal that provides our new line
        self.viewwidget.polylineCollected.connect(profileDock.newLine)

        # grab the signal the profileDock sends when it is closed
        profileDock.profileClosed.connect(self.profileClosed)

        # increment our count
        self.profileWindowCount += 1

    def profileClosed(self, profileDock):
        """
        Profile dock window has been closed. Disconnect from
        polylineCollected signal and decrement our count
        """
        if self.profileWindowCount > 0:
            self.viewwidget.polylineCollected.disconnect(profileDock.newLine)
            self.profileWindowCount -= 1

    def properties(self):
        """
        Show the properties dialog
        """
        from . import propertieswindow
        layer = self.viewwidget.layers.getTopLayer()
        if layer is not None:
            info = layer.getPropertiesInfo()
            dlg = propertieswindow.PropertiesWindow(self, info)
            dlg.setWindowTitle(layer.title)
            dlg.show()

    def flicker(self):
        """
        Tell the widget to flicker
        """
        state = self.viewwidget.flicker()
        if state:
            self.flickerAct.setIcon(self.flickerAct.iconOn)
        else:
            self.flickerAct.setIcon(self.flickerAct.iconOff)

    def saveCurrentView(self):
        """
        Saves the current view as an image file
        """
        # now get a filename
        fname, filter = QFileDialog.getSaveFileName(self, "Image File", 
                        filter="Images (*.png *.xpm *.jpg *.tif)")
        if fname != '':
            self.saveCurrentViewInternal(fname)

    def saveCurrentViewInternal(self, fname):
        """
        Saves the current view as an image file as the file given
        """
        # first grab it out of the widget
        from PyQt5.QtGui import QImage
        img = QImage(self.viewwidget.viewport().size(), QImage.Format_RGB32)
        self.viewwidget.viewport().render(img)

        if not img.save(fname):
            QMessageBox.critical(self, MESSAGE_TITLE, 
                "Unable to save file")
        else:
            # save a world file while we are at it
            # see http://en.wikipedia.org/wiki/World_file
            worldfname = fname + 'w'
            worldfObj = None
            try:
                layer = self.viewwidget.layers.getTopRasterLayer()
                if layer is not None:
                    metresperwinpix = (layer.coordmgr.imgPixPerWinPix * 
                        layer.coordmgr.geotransform[1])
                    (left, top, right, bottom) = (
                        layer.coordmgr.getWorldExtent())

                    worldfObj = open(worldfname, 'w')
                    worldfObj.write("%f\n" % metresperwinpix)
                    worldfObj.write("0.0\n0.0\n")
                    worldfObj.write("%f\n" % -metresperwinpix)
                    worldfObj.write("%f\n" % (left + (metresperwinpix / 2.0)))
                    worldfObj.write("%f\n" % (top + (metresperwinpix / 2.0)))
            except IOError:
                QMessageBox.critical(self, MESSAGE_TITLE,
                    "Unable to save world file: %s" % worldfname)
            finally:
                if worldfObj is not None:
                    worldfObj.close()

    def about(self):
        """
        Show author and version info
        """
        from . import TUIVIEW_VERSION
        from PyQt5.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
        from osgeo.gdal import __version__ as gdalVersion
        from numpy import version as numpyVersion

        msg = """<p align='center'>TuiView<br><br>
By Sam Gillingham, Neil Flood, Pete Bunting, James Shepherd, <br>
Pierre Roudier, Tony Gill, Robin Wilson, Dan Clewley, Dale Peters,<br>
Terry Cain and Ben Jolly<br><br>

Development funded by Landcare Research NZ Ltd.<br><br>

Colours from www.colorbrewer.org by Cynthia A. Brewer, Geography,<br>
Pennsylvania State University.<br><br>

Version: %s<br>
Installed in: %s<br>
GDAL Version: %s<br>
PyQt Version: %s<br>
Qt Version: %s<br>
Python Version: %s<br>
Numpy Version: %s<br></p>
"""
        appDir = os.path.dirname(os.path.abspath(sys.argv[0]))
        pyVer = "%d.%d.%d" % (sys.version_info.major, sys.version_info.minor,
                    sys.version_info.micro)
        msg = msg % (TUIVIEW_VERSION, appDir, gdalVersion, PYQT_VERSION_STR, 
                QT_VERSION_STR, 
                pyVer, numpyVersion.version)

        # centre each line - doesn't work very well due to font
        msgLines = msg.split('\n')
        maxLine = max([len(line) for line in msgLines])
        centredMsgs = []
        for line in msgLines:
            leftSpaces = int((maxLine - len(line)) / 2.0)
            centred = (' ' * leftSpaces) + line
            centredMsgs.append(centred)

        QMessageBox.about(self, MESSAGE_TITLE, "\n".join(centredMsgs))

    def closeEvent(self, event):
        """
        Window is being closed. Save the position and size.
        Check that any of the query windows don't have unsaved data
        """
        settings = QSettings()
        settings.beginGroup('ViewerWindow')
        settings.setValue("size", self.size())
        settings.setValue("pos", self.pos())
        settings.endGroup()

        event.accept()

    def closeAllOnTimer(self):
        """
        See closeAll() below. Does the actual work when
        called by the single shot timer.
        """
        self.closeAllWindowsSig.emit()

    def closeAll(self):
        """
        Send a signal to geolinked viewers close all windows.
        For some reason, doing this right now causes a crash.
        Seems safest to wait until GUI is idle (using a single 
        shot timer with a timeout of 0) then call closeAllOnTimer()
        to do the actual work.
        """
        QTimer.singleShot(0, self.closeAllOnTimer)

    def dragEnterEvent(self, event):
        """
        Called when user about to drop some data on the window
        accept it if it has urls (which are usually just files)
        """
        mimeData = event.mimeData()
        if mimeData.hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """
        Called when the user attempts to drop some data onto the window
        We only respond to files being dropped
        """
        mimeData = event.mimeData()
        if mimeData.hasUrls():
            for url in mimeData.urls():
                fname = url.toLocalFile()
                try:
                    # try raster first
                    self.addRasterInternal(fname, showError=False)
                except Exception:
                    # then vector 
                    self.addVectorInternal(fname)

    def setPreferences(self):
        """
        Display the preferences dialog
        """
        from . import viewerpreferences
        viewPref = viewerpreferences.ViewerPreferencesDialog(self)
        if viewPref.exec_() == QDialog.Accepted:

            # extract the mouse wheel setting
            self.mouseWheelZoom = viewPref.settingMouseWheelZoom
            self.viewwidget.setMouseScrollWheelAction(self.mouseWheelZoom)
            # the color
            self.backgroundColor = viewPref.settingBackgroundColor
            self.viewwidget.setBackgroundColor(self.backgroundColor)
            # setting have already been set back to disc

    def queryOnlyDisplayed(self, state):
        "Change the state of the querying behaviour"
        self.viewwidget.setQueryOnlyDisplayed(state)

    def saveViewersState(self):
        """
        Get the geolinked viewers class to save the state as a file
        """
        # set last dir
        layer = self.viewwidget.layers.getTopLayer()
        if layer is not None:
            dir = os.path.dirname(layer.filename)
            if dir == '':
                dir = os.getcwd()
        else:
            # or cwd
            dir = os.getcwd()
        fname, filter= QFileDialog.getSaveFileName(self, 
                    "Select file to save state into",
                    dir, "TuiView State .tuiview (*.tuiview)")

        if fname != "":
            fileobj = open(fname, 'w')
            self.writeViewersState.emit(fileobj)
            fileobj.close()

    def loadViewersState(self):
        """
        Get the geolinked viewers class to open previously saved state file
        """
        # set last dir
        layer = self.viewwidget.layers.getTopLayer()
        if layer is not None:
            dir = os.path.dirname(layer.filename)
            if dir == '':
                dir = os.getcwd()
        else:
            # or cwd
            dir = os.getcwd()
        fname, filter = QFileDialog.getOpenFileName(self, "Select file to restore state from",
                    dir, "TuiView State .tuiview (*.tuiview)")

        if fname != "":
            fileobj = open(fname)
            self.readViewersState.emit(fileobj)
            fileobj.close()

