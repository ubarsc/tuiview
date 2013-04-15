
"""
Main Window of the Viewer application. Contains
the ViewerWidget, menus, toolbars and status bars.
"""
# This file is part of 'Viewer' - a simple Raster viewer
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
from PyQt4.QtGui import QMainWindow, QAction, QIcon, QFileDialog, QDialog
from PyQt4.QtGui import QMessageBox, QProgressBar, QMessageBox, QToolButton
from PyQt4.QtGui import QMenu, QColor
from PyQt4.QtCore import QSettings, QSize, QPoint, SIGNAL, Qt
from PyQt4.QtCore import QCoreApplication, QEventLoop

# different resource file needed on Python3
if sys.version_info[0] == 3:
    from . import viewerresources3
else:
    from . import viewerresources2
from . import viewerwidget

DEFAULT_XSIZE = 400
DEFAULT_YSIZE = 400
DEFAULT_XPOS = 200
DEFAULT_YPOS = 200

MESSAGE_TIMEOUT = 2000
DEFAULT_DRIVER = 'HFA'
MESSAGE_TITLE = 'Viewer'

# Populate this list the first time the
# file open dialog shown.
GDAL_FILTERS = None

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
        # add all files first
        GDAL_FILTERS.append("All files (*)")

        # if we have a default driver do it next
        if not defaultDriver is None:
            driver = gdal.GetDriverByName(defaultDriver)
            qfilter = createFilter(driver)
            GDAL_FILTERS.append(qfilter)

        # just go thru them all and create filters
        for count in range(gdal.GetDriverCount()):
            driver = gdal.GetDriver(count)
            qfilter = createFilter(driver)
            GDAL_FILTERS.append(qfilter)


class ViewerWindow(QMainWindow):
    """
    Main window for viewer application
    """
    def __init__(self):
        QMainWindow.__init__(self)
        self.setWindowTitle('Viewer')
        self.viewwidget = viewerwidget.ViewerWidget(self)

        # connect to the signals emmitted by the LUT/RAT via the LayerManager
        # so we can update our progress bar
        self.connect(self.viewwidget.layers, SIGNAL("newProgress(QString)"), 
                                                self.newProgress)
        self.connect(self.viewwidget.layers, SIGNAL("endProgress()"), 
                                                self.endProgress)
        self.connect(self.viewwidget.layers, SIGNAL("newPercent(int)"), 
                                                self.newPercent)
        # so we can update the window title
        self.connect(self.viewwidget.layers, SIGNAL("topLayerChanged(QString)"),
                                                self.updateWindowTitle)
        # general messages from the widget
        self.connect(self.viewwidget, SIGNAL("showStatusMessage(QString)"),
                                                self.showStatusMessage)
        # the signal that gets sent when active tool changed so we can update
        # gui if querywindow engages a tool
        self.connect(self.viewwidget, 
            SIGNAL("activeToolChanged(PyQt_PyObject)"), self.activeToolChanged)

        self.setCentralWidget(self.viewwidget)

        self.setupActions()
        self.setupMenus()
        self.setupToolbars()
        self.setupStatusBar()

        self.restoreFromSettings()
        # set this value, just read from settings
        self.viewwidget.setMouseScrollWheelAction(self.mouseWheelZoom)
        self.viewwidget.setBackgroundColor(self.backgroundColor)

        self.showStatusMessage("Ready")

        # number of query windows we have open.
        # if zero we need to start a new one when query
        # tool selected
        self.queryWindowCount = 0
        # same, but for profile window
        self.profileWindowCount = 0

        # accept dropping files
        self.setAcceptDrops(True)

        # our layer window so we can toggle it
        self.layerWindow = None

        # so if we are turning on a tool because another tool 
        # in another window has been turned on, we don't undo 
        # that tool being enabled. As oppossed to user unclicking
        # the tool
        self.suppressToolReset = False

    def updateWindowTitle(self, fname):
        """
        called in response to the topLayerChanged(QString) signal
        from the layers to say the top displayed layer has changed
        """
        if fname != '':
            # just display the basename
            title = os.path.basename(str(fname))
            self.setWindowTitle(title)
        else:
            # nothing loaded
            self.setWindowTitle('Viewer')

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

        # qvariant behaviour is different in Python3 so be careful
        defaultsize = QSize(DEFAULT_XSIZE, DEFAULT_YSIZE)
        if sys.version_info[0] == 3:
            self.resize(settings.value("size", defaultsize))
        else:
            self.resize(settings.value("size", defaultsize).toSize())
        defaultpos = QPoint(DEFAULT_XPOS, DEFAULT_YPOS)
        if sys.version_info[0] == 3:
            self.move(settings.value("pos", defaultpos))
        else:
            self.move(settings.value("pos", defaultpos).toPoint())

        settings.endGroup()

        settings.beginGroup('ViewerMouse')
        value = settings.value("mousescroll", True, bool)
        self.mouseWheelZoom = value
        settings.endGroup()

        settings.beginGroup('ViewerBackground')
        value = settings.value("color", QColor(Qt.black), QColor)
        self.backgroundColor = value
        settings.endGroup()

    def setupActions(self):
        """
        Creates all the actions for the Window
        """
        self.toolActions = []

        self.addRasterAct = QAction(self)
        self.addRasterAct.setText("&Add Raster")
        self.addRasterAct.setStatusTip("Open a GDAL supported image")
        self.addRasterAct.setShortcut("CTRL+O")
        self.addRasterAct.setIcon(QIcon(":/viewer/images/addraster.png"))
        self.addRasterAct.setIconVisibleInMenu(True)
        self.connect(self.addRasterAct, SIGNAL("triggered()"), self.addRaster)

        self.addVectorFileAct = QAction(self)
        self.addVectorFileAct.setText("Add Vector &File")
        self.addVectorFileAct.setStatusTip("Open an OGR supported vector file")
        self.addVectorFileAct.setShortcut("CTRL+V")
        self.addVectorFileAct.setIcon(QIcon(":/viewer/images/addvector.png"))
        self.addVectorFileAct.setIconVisibleInMenu(True)
        self.addVectorFileAct.setEnabled(viewerwidget.haveVector())
        self.connect(self.addVectorFileAct, SIGNAL("triggered()"), 
                                                            self.addVectorFile)

        self.addVectorDirAct = QAction(self)
        self.addVectorDirAct.setText("Add Vector &Directory")
        self.addVectorDirAct.setStatusTip("Open an OGR supported vector directory")
        self.addVectorDirAct.setIcon(QIcon(":/viewer/images/addvector.png"))
        self.addVectorDirAct.setIconVisibleInMenu(True)
        self.addVectorDirAct.setEnabled(viewerwidget.haveVector())
        self.connect(self.addVectorDirAct, SIGNAL("triggered()"), 
                                                            self.addVectorDir)

        self.addVectorDBAct = QAction(self)
        self.addVectorDBAct.setText("Add Vector Data&base")
        self.addVectorDBAct.setStatusTip(
                                "Open a layer from an OGR supported database")
        self.addVectorDBAct.setIcon(QIcon(":/viewer/images/addvector.png"))
        self.addVectorDBAct.setIconVisibleInMenu(True)
        self.addVectorDBAct.setEnabled(viewerwidget.haveVector())
        self.connect(self.addVectorDBAct, SIGNAL("triggered()"), 
                                                            self.addVectorDB)

        self.vectorMenu = QMenu()
        self.vectorMenu.setTitle("Add Vector")
        self.vectorMenu.addAction(self.addVectorFileAct)
        self.vectorMenu.addAction(self.addVectorDirAct)
        self.vectorMenu.addAction(self.addVectorDBAct)

        self.removeLayerAct = QAction(self)
        self.removeLayerAct.setText("&Remove Layer")
        self.removeLayerAct.setStatusTip("Remove top layer")
        self.removeLayerAct.setShortcut("CTRL+R")
        self.removeLayerAct.setIcon(QIcon(":/viewer/images/removelayer.png"))
        self.removeLayerAct.setIconVisibleInMenu(True)
        self.connect(self.removeLayerAct, SIGNAL("triggered()"), 
                                                        self.removeLayer)

        self.newWindowAct = QAction(self)
        self.newWindowAct.setText("&New Window")
        self.newWindowAct.setStatusTip("Create a new geo linked window")
        self.newWindowAct.setShortcut("CTRL+N")
        self.newWindowAct.setIcon(QIcon(":/viewer/images/newwindow.png"))
        self.newWindowAct.setIconVisibleInMenu(True)
        self.connect(self.newWindowAct, SIGNAL("triggered()"), self.newWindow)

        self.tileWindowsAct = QAction(self)
        self.tileWindowsAct.setText("&Tile Windows...")
        self.tileWindowsAct.setStatusTip("Tile all open windows")
        self.tileWindowsAct.setShortcut("CTRL+I")
        self.connect(self.tileWindowsAct, SIGNAL("triggered()"), 
                                                        self.tileWindows)

        self.defaultStretchAct = QAction(self)
        self.defaultStretchAct.setText("&Default Stretch...")
        self.defaultStretchAct.setStatusTip("Set default stretches")
        self.defaultStretchAct.setShortcut("CTRL+D")
        self.connect(self.defaultStretchAct, SIGNAL("triggered()"), 
                                                        self.defaultStretch)

        self.stretchAct = QAction(self)
        self.stretchAct.setText("S&tretch")
        self.stretchAct.setStatusTip("Edit current stretch")
        self.stretchAct.setShortcut("CTRL+T")
        self.stretchAct.setEnabled(False) # until a file is opened
        self.connect(self.stretchAct, SIGNAL("triggered()"), self.editStretch)

        self.panAct = QAction(self)
        self.panAct.setText("&Pan")
        self.panAct.setStatusTip("Pan")
        self.panAct.setShortcut("CTRL+P")
        self.panAct.setCheckable(True)
        self.panAct.setIcon(QIcon(":/viewer/images/pan.png"))
        self.panAct.setIconVisibleInMenu(True)
        self.connect(self.panAct, SIGNAL("toggled(bool)"), self.pan)
        self.toolActions.append(self.panAct)

        self.zoomInAct = QAction(self)
        self.zoomInAct.setText("Zoom &In")
        self.zoomInAct.setStatusTip("Zoom In")
        self.zoomInAct.setShortcut("CTRL++")
        self.zoomInAct.setCheckable(True)
        self.zoomInAct.setIcon(QIcon(":/viewer/images/zoomin.png"))
        self.zoomInAct.setIconVisibleInMenu(True)
        self.connect(self.zoomInAct, SIGNAL("toggled(bool)"), self.zoomIn)
        self.toolActions.append(self.zoomInAct)

        self.zoomOutAct = QAction(self)
        self.zoomOutAct.setText("Zoom &Out")
        self.zoomOutAct.setStatusTip("Zoom Out")
        self.zoomOutAct.setShortcut("CTRL+-")
        self.zoomOutAct.setCheckable(True)
        self.zoomOutAct.setIcon(QIcon(":/viewer/images/zoomout.png"))
        self.zoomOutAct.setIconVisibleInMenu(True)
        self.connect(self.zoomOutAct, SIGNAL("toggled(bool)"), self.zoomOut)
        self.toolActions.append(self.zoomOutAct)

        self.zoomNativeAct = QAction(self)
        self.zoomNativeAct.setText("Zoom to &Native")
        self.zoomNativeAct.setStatusTip("Zoom to Native Resolution")
        self.zoomNativeAct.setShortcut("CTRL+1")
        self.zoomNativeAct.setIcon(QIcon(":/viewer/images/zoomnative.png"))
        self.zoomNativeAct.setIconVisibleInMenu(True)
        self.connect(self.zoomNativeAct, SIGNAL("triggered()"), self.zoomNative)

        self.zoomFullExtAct = QAction(self)
        self.zoomFullExtAct.setText("Zoom to &Full Extent")
        self.zoomFullExtAct.setStatusTip("Zoom to Full Extent")
        self.zoomFullExtAct.setShortcut("CTRL+F")
        self.zoomFullExtAct.setIcon(QIcon(":/viewer/images/zoomfullextent.png"))
        self.zoomFullExtAct.setIconVisibleInMenu(True)
        self.connect(self.zoomFullExtAct, SIGNAL("triggered()"), 
                                                           self.zoomFullExtent)

        self.followExtentAct = QAction(self)
        self.followExtentAct.setText("Follow &Extent")
        self.followExtentAct.setStatusTip("Follow geolinked extent")
        self.followExtentAct.setShortcut("CTRL+E")
        self.followExtentAct.setCheckable(True)
        self.followExtentAct.setChecked(True) # by default to match viewerwidget
        self.followExtentAct.setIcon(QIcon(":/viewer/images/followextents.png"))
        self.followExtentAct.setIconVisibleInMenu(True)
        self.connect(self.followExtentAct, SIGNAL("toggled(bool)"), 
                                                            self.followExtent)

        self.queryAct = QAction(self)
        self.queryAct.setText("&Query Tool")
        self.queryAct.setStatusTip("Start Query Tool")
        self.queryAct.setShortcut("CTRL+U")
        self.queryAct.setCheckable(True)
        self.queryAct.setIcon(QIcon(":/viewer/images/query.png"))
        self.queryAct.setIconVisibleInMenu(True)
        self.connect(self.queryAct, SIGNAL("toggled(bool)"), self.query)

        self.newQueryAct = QAction(self)
        self.newQueryAct.setText("New Query &Window")
        self.newQueryAct.setStatusTip("Open New Query Window")
        self.newQueryAct.setShortcut("CTRL+W")
        self.connect(self.newQueryAct, SIGNAL("triggered()"), 
                                                            self.newQueryWindow)

        self.exitAct = QAction(self)
        self.exitAct.setText("&Close")
        self.exitAct.setStatusTip("Close this window")
        self.exitAct.setShortcut("CTRL+Q")
        self.connect(self.exitAct, SIGNAL("triggered()"), self.close)

        self.preferencesAct = QAction(self)
        self.preferencesAct.setText("&Preferences")
        self.preferencesAct.setStatusTip("Edit Preferences")
        self.preferencesAct.setShortcut("CTRL+L")
        self.connect(self.preferencesAct, SIGNAL("triggered()"), 
                                                    self.setPreferences)

        self.flickerAct = QAction(self)
        self.flickerAct.setText("&Flicker")
        self.flickerAct.setStatusTip("Flicker top 2 layers")
        self.flickerAct.setShortcut("CTRL+K")
        self.flickerAct.iconOn = QIcon(":/viewer/images/flickeron.png")
        self.flickerAct.iconOff = QIcon(":/viewer/images/flickeroff.png")
        self.flickerAct.setIcon(self.flickerAct.iconOn)
        self.flickerAct.setIconVisibleInMenu(True)
        self.connect(self.flickerAct, SIGNAL("triggered()"), self.flicker)

        self.layerAct = QAction(self)
        self.layerAct.setText("Arrange La&yers")
        self.layerAct.setStatusTip("Arrange Layers")
        self.layerAct.setShortcut("CTRL+Y")
        self.layerAct.setIcon(QIcon(":/viewer/images/layers.png"))
        self.layerAct.setIconVisibleInMenu(True)
        self.connect(self.layerAct, SIGNAL("triggered()"), self.arrangeLayers)

        self.profileAct = QAction(self)
        self.profileAct.setText("&Profile/Ruler")
        self.profileAct.setStatusTip("Start Profile/Ruler tool")
        self.profileAct.setShortcut("CTRL+A")
        self.profileAct.setCheckable(True)
        self.profileAct.setIcon(QIcon(":/viewer/images/profileruler.png"))
        self.profileAct.setIconVisibleInMenu(True)
        self.connect(self.profileAct, SIGNAL("toggled(bool)"), self.profile)
        self.toolActions.append(self.profileAct)

        self.newProfileAct = QAction(self)
        self.newProfileAct.setText("New P&rofile/Ruler Window")
        self.newProfileAct.setStatusTip("Open New Profile/Ruler Window")
        self.newProfileAct.setShortcut("CTRL+S")
        self.connect(self.newProfileAct, SIGNAL("triggered()"), 
                                                    self.newProfile)

        self.timeseriesForwardAct = QAction(self)
        self.timeseriesForwardAct.setShortcut(".")
        self.timeseriesForwardAct.setText("Timeseries Forward")
        self.timeseriesForwardAct.setStatusTip(
                                "Go forward through timeseries of images")
        self.connect(self.timeseriesForwardAct, SIGNAL("triggered()"),
                                self.viewwidget.timeseriesForward)

        self.timeseriesBackwardAct = QAction(self)
        self.timeseriesBackwardAct.setShortcut(",")
        self.timeseriesBackwardAct.setText("Timeseries Backward")
        self.timeseriesBackwardAct.setStatusTip(
                                "Go backward through timeseries of images")
        self.connect(self.timeseriesBackwardAct, SIGNAL("triggered()"),
                                self.viewwidget.timeseriesBackward)

        self.aboutAct = QAction(self)
        self.aboutAct.setText("&About")
        self.aboutAct.setStatusTip("Show author and version information")
        self.connect(self.aboutAct, SIGNAL("triggered()"), self.about)

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
        fileMenu.addAction(self.tileWindowsAct)
        fileMenu.addAction(self.defaultStretchAct)
        fileMenu.addAction(self.exitAct)
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

        viewToolbar = self.addToolBar("View")
        viewToolbar.addAction(self.panAct)
        viewToolbar.addAction(self.zoomInAct)
        viewToolbar.addAction(self.zoomOutAct)
        viewToolbar.addAction(self.zoomNativeAct)
        viewToolbar.addAction(self.zoomFullExtAct)
        viewToolbar.addAction(self.followExtentAct)

        toolToolbar = self.addToolBar("Tools")
        toolToolbar.addAction(self.queryAct)
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
        self.emit(SIGNAL("newWindow()"))

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
            self.emit(SIGNAL("tileWindows(int, int)"), xnum, ynum)

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
        dlg = QFileDialog(self)
        dlg.setNameFilters(GDAL_FILTERS)
        dlg.setFileMode(QFileDialog.ExistingFiles)
        # set last dir
        layer = self.viewwidget.layers.getTopRasterLayer()
        if layer is not None:
            dir = os.path.dirname(layer.filename)
            dlg.setDirectory(dir)

        if dlg.exec_() == QDialog.Accepted:
            for fname in dlg.selectedFiles():
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
        olddir = ""
        if layer is not None:
            olddir = os.path.dirname(layer.filename)

        dir = QFileDialog.getExistingDirectory(self, "Choose vector directory",
            directory=olddir,
            options=QFileDialog.ShowDirsOnly|QFileDialog.DontResolveSymlinks)
        if dir != "":
            self.addVectorInternal(dir)

    def addVectorDB(self):
        """
        Add a vector from a database - ask user for connection string
        """
        from PyQt4.QtGui import QInputDialog
        (con, ok) = QInputDialog.getText(self, "Viewer", 
                                "Enter OGR connection string (without quotes)")
        if ok and con != "":
            self.addVectorInternal(con)

    def addRasterInternal(self, fname, stretch=None):
        """
        Actually to the file opening. If stretch is None
        is is determined using our automatic scheme.
        """
        fname = str(fname) # was QString
        lut = None
        # first open the dataset
        from osgeo import gdal
        try:
            gdaldataset = gdal.Open(fname)
        except RuntimeError:
            msg = "Unable to open %s" % fname
            QMessageBox.critical(self, MESSAGE_TITLE, msg)
            return

        if stretch is None:
            # first see if it has a stretch saved in the file
            from . import viewerstretch
            stretch = viewerstretch.ViewerStretch.readFromGDAL(gdaldataset)
            if stretch is None:
                # ok was none, read in the default stretches
                from . import stretchdialog
                defaultList = stretchdialog.StretchDefaultsDialog.fromSettings()
                for rule in defaultList:
                    if rule.isMatch(gdaldataset):
                        stretch = rule.stretch
                        break
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
        except Exception as e:
            QMessageBox.critical(self, "Viewer", str(e) )

        # allow the stretch to be edited
        self.stretchAct.setEnabled(True)

    def addVectorInternal(self, path, layername=None):
        """
        Open OGR dataset and layer and tell widget to add it 
        to the list of layers
        """
        from osgeo import ogr
        try:
            ds = ogr.Open(str(path))
            if ds is None:
                msg = 'Unable to open %s' % path
                QMessageBox.critical(self, "Viewer", msg)
                return
                
            if layername is None:
                # ask them
                numLayers = ds.GetLayerCount()
                if numLayers == 0:
                    raise IOError("no valid layers")
                elif numLayers == 1:
                    lyr = ds.GetLayer(0)
                else:
                    from PyQt4.QtGui import QInputDialog
                    layerNames = []
                    for n in range(ds.GetLayerCount()):
                        name = ds.GetLayer(n).GetName()
                        layerNames.append(name)
                    (name, ok) = QInputDialog.getItem(self, "Viewer", 
                        "select layer to open", layerNames, editable=False)
                    if ok:
                        lyr = ds.GetLayerByName(str(name))
                    else:
                        return
            else:
                lyr = ds.GetLayerByName(layername)
                
            self.viewwidget.addVectorLayer(ds, lyr)

        except Exception as e:
            QMessageBox.critical(self, "Viewer", str(e) )

    def removeLayer(self):
        """
        Remove the top most layer
        """
        self.viewwidget.removeLayer()

    def arrangeLayers(self):
        """
        Toggle the LayerWindow
        """
        from . import layerwindow
        if self.layerWindow is None:
            self.layerWindow = layerwindow.LayerWindow(self, self.viewwidget)
            self.addDockWidget(Qt.LeftDockWidgetArea, self.layerWindow)
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
            QMessageBox.critical(self, "Viewer", "No raster layer available" )
        else:
            stretchDock = stretchdialog.StretchDockWidget(self, 
                                self.viewwidget, layer)
            self.addDockWidget(Qt.TopDockWidgetArea, stretchDock)

    def zoomIn(self, checked):
        """
        Zoom in tool selected.
        Tell view widget to operate in zoom mode.
        """
        if checked:
            # disable any other tools
            self.panAct.setChecked(False)
            self.zoomOutAct.setChecked(False)
            self.queryAct.setChecked(False)
            self.profileAct.setChecked(False)
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
            self.panAct.setChecked(False)
            self.zoomInAct.setChecked(False)
            self.queryAct.setChecked(False)
            self.profileAct.setChecked(False)
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
            self.zoomInAct.setChecked(False)
            self.zoomOutAct.setChecked(False)
            self.queryAct.setChecked(False)
            self.profileAct.setChecked(False)
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_PAN, 
                        id(self))
        elif not self.suppressToolReset:
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_NONE, 
                        id(self))

    def zoomNative(self):
        """
        Tell the widget to zoom to native resolution
        """
        try:
            self.viewwidget.zoomNativeResolution()
        except Exception as e:
            QMessageBox.critical(self, "Viewer", str(e) )

    def zoomFullExtent(self):
        """
        Tell the widget to zoom back to the full extent
        """
        try:
            self.viewwidget.zoomFullExtent()
        except Exception as e:
            QMessageBox.critical(self, "Viewer", str(e) )

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
            self.zoomInAct.setChecked(False)
            self.zoomOutAct.setChecked(False)
            self.panAct.setChecked(False)
            self.profileAct.setChecked(False)
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
        self.disconnect(self.viewwidget, 
                            SIGNAL("locationSelected(PyQt_PyObject)"), 
                            queryDock.locationSelected)
        self.queryWindowCount -= 1

    def newQueryWindow(self):
        """
        Create a new QueryDockWidget and connect signals
        and increment our count of these windows
        """
        from . import querywindow
        queryDock = querywindow.QueryDockWidget(self, self.viewwidget)
        self.addDockWidget(Qt.BottomDockWidgetArea, queryDock)
        queryDock.setFloating(True) # detach so it isn't docked by default

        # connect it to signals emitted by the viewerwidget
        self.connect(self.viewwidget, 
                                SIGNAL("locationSelected(PyQt_PyObject)"), 
                                queryDock.locationSelected)

        # grab the signal the queryDock sends when it is closed
        self.connect(queryDock, SIGNAL("queryClosed(PyQt_PyObject)"), 
                                                self.queryClosed)

        # increment our count
        self.queryWindowCount += 1

        # emit the signal back to geolinked viewers so that 
        # any plugins can be informed
        self.emit(SIGNAL("newQueryWindow(PyQt_PyObject)"), queryDock)

    def profile(self, checked):
        """
        Profile tool selected.
        Tell view widget to operate in polyline mode.
        """
        if checked:
            # disable any other tools
            self.zoomInAct.setChecked(False)
            self.zoomOutAct.setChecked(False)
            self.panAct.setChecked(False)
            self.queryAct.setChecked(False)
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
        profileDock.setFloating(True) # detach so it isn't docked by default

        # connect to the signal that provides our new line
        self.connect(self.viewwidget, 
            SIGNAL("polylineCollected(PyQt_PyObject)"), profileDock.newLine)

        # grab the signal the profileDock sends when it is closed
        self.connect(profileDock, SIGNAL("profileClosed(PyQt_PyObject)"), 
                                                self.profileClosed)

        # increment our count
        self.profileWindowCount += 1

    def profileClosed(self, profileDock):
        """
        Profile dock window has been closed. Disconnect from
        polylineCollected signal and decrement our count
        """
        self.disconnect(self.viewwidget, 
                            SIGNAL("polylineCollected(PyQt_PyObject)"), 
                            profileDock.newLine)
        self.profileWindowCount -= 1

    def flicker(self):
        """
        Tell the widget to flicker
        """
        state = self.viewwidget.flicker()
        if state:
            self.flickerAct.setIcon(self.flickerAct.iconOn)
        else:
            self.flickerAct.setIcon(self.flickerAct.iconOff)

    def about(self):
        """
        Show author and version info
        """
        from PyQt4.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
        from osgeo.gdal import __version__ as gdalVersion
        import sys
        from numpy import version as numpyVersion
        scipyVersionString = 'Not Available'
        pyqtgraphVersionString = 'Not Available'
        try:
            from scipy import version as scipyVersion
            scipyVersionString = scipyVersion.version
            from pyqtgraph import __version__ as pyqtgraphVersion
            pyqtgraphVersionString = pyqtgraphVersion
        except ImportError:
            pass

        msg = """ Viewer
By Sam Gillingham, Neil Flood, Pete Bunting, James Shepherd, Pierre Roudier and Tony Gill.

Colours from www.colorbrewer.org by Cynthia A. Brewer, Geography, Pennsylvania State University.

Installed in: %s
GDAL Version: %s
PyQt Version: %s
Qt Version: %s
Python Version: %s
Numpy Version: %s
Scipy Version: %s
PyQtGraph Version: %s
"""
        appDir = os.path.dirname(os.path.abspath(sys.argv[0]))
        pyVer = "%d.%d.%d" % (sys.version_info.major, sys.version_info.minor,
                    sys.version_info.micro)
        msg = msg % (appDir, gdalVersion, PYQT_VERSION_STR, QT_VERSION_STR, 
                pyVer, numpyVersion.version, scipyVersionString, 
                pyqtgraphVersionString)

        # centre each line - doesn't work very well due to font
        msgLines = msg.split('\n')
        maxLine = max([len(line) for line in msgLines])
        centredMsgs = []
        for line in msgLines:
            leftSpaces = int((maxLine - len(line)) / 2.0)
            centred = (' ' * leftSpaces) + line
            centredMsgs.append(centred)

        QMessageBox.about(self, "Viewer", "\n".join(centredMsgs))


    def closeEvent(self, event):
        """
        Window is being closed. Save the position and size.
        Emit signal for GeolinkedViewers.
        """
        settings = QSettings()
        settings.beginGroup('ViewerWindow')
        settings.setValue("size", self.size())
        settings.setValue("pos", self.pos())
        settings.endGroup()

        event.accept()

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
                # things will get tricky when we support vectors
                # try raster then vector?
                self.addRasterInternal(url.toLocalFile())

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

