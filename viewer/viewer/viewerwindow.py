
"""
Main Window of the Viewer application. Contains
the ViewerWidget, menus, toolbars and status bars.
"""

import os
from PyQt4.QtGui import QMainWindow, QAction, QIcon, QFileDialog, QDialog
from PyQt4.QtGui import QMessageBox, QProgressBar, QMessageBox
from PyQt4.QtCore import QSettings, QSize, QPoint, SIGNAL, QStringList, Qt
from PyQt4.QtCore import QCoreApplication, QEventLoop

from . import viewerresources
from . import viewerwidget

DEFAULT_XSIZE = 400
DEFAULT_YSIZE = 400
DEFAULT_XPOS = 200
DEFAULT_YPOS = 200

MESSAGE_TIMEOUT = 2000
DEFAULT_DRIVER = 'HFA'
MESSAGE_TITLE = 'Viewer'

# Populate this QStringList the first time the
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
    if drivermeta.has_key(DMD_LONGNAME):
        name = drivermeta[DMD_LONGNAME]
        # get rid of any stuff in brackets - seems to
        # confuse Qt 4.x
        firstbracket = name.find('(')
        if firstbracket != -1:
            name = name[:firstbracket]
    qfilter = '*'
    if drivermeta.has_key(DMD_EXTENSION):
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
        GDAL_FILTERS = QStringList()
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

        self.setCentralWidget(self.viewwidget)

        self.setupActions()
        self.setupMenus()
        self.setupToolbars()
        self.setupStatusBar()

        self.restoreFromSettings()

        self.showStatusMessage("Ready")

        # number of query windows we have open.
        # if zero we need to start a new one when query
        # tool selected
        self.queryWindowCount = 0

        # accept dropping files
        self.setAcceptDrops(True)

        self.mouseWheelZoom = True

    def newProgress(self, string):
        """
        Called when we are about to start a new progress
        """
        self.statusBar().showMessage(string)
        self.progressWidget.setValue(0)
        self.progressWidget.setVisible(True)
        # process any events show gets shown while busy
        QCoreApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

    def endProgress(self):
        """
        Called when a progress run has finished
        """
        self.statusBar().clearMessage()
        self.progressWidget.setVisible(False)
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

    def restoreFromSettings(self):
        """
        Restore any settings from last time
        """
        settings = QSettings()
        settings.beginGroup('ViewerWindow')

        defaultsize = QSize(DEFAULT_XSIZE, DEFAULT_YSIZE)
        self.resize(settings.value("size", defaultsize).toSize())
        defaultpos = QPoint(DEFAULT_XPOS, DEFAULT_YPOS)
        self.move(settings.value("pos", defaultpos).toPoint())

        settings.endGroup()

        settings.beginGroup('ViewerMouse')
        self.mouseWheelZoom = True
        value = settings.value("mousescroll", self.mouseWheelZoom)
        self.mouseWheelZoom = value.toBool()
        settings.endGroup()

    def setupActions(self):
        """
        Creates all the actions for the Window
        """
        self.addRasterAct = QAction(self)
        self.addRasterAct.setText("&Add Raster")
        self.addRasterAct.setStatusTip("Open a GDAL supported image")
        self.addRasterAct.setShortcut("CTRL+O")
        self.addRasterAct.setIcon(QIcon(":/viewer/images/addraster.png"))
        self.addRasterAct.setIconVisibleInMenu(True)
        self.connect(self.addRasterAct, SIGNAL("triggered()"), self.addRaster)

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

        self.zoomInAct = QAction(self)
        self.zoomInAct.setText("Zoom &In")
        self.zoomInAct.setStatusTip("Zoom In")
        self.zoomInAct.setShortcut("CTRL++")
        self.zoomInAct.setCheckable(True)
        self.zoomInAct.setIcon(QIcon(":/viewer/images/zoomin.png"))
        self.zoomInAct.setIconVisibleInMenu(True)
        self.connect(self.zoomInAct, SIGNAL("toggled(bool)"), self.zoomIn)

        self.zoomOutAct = QAction(self)
        self.zoomOutAct.setText("Zoom &Out")
        self.zoomOutAct.setStatusTip("Zoom Out")
        self.zoomOutAct.setShortcut("CTRL+-")
        self.zoomOutAct.setCheckable(True)
        self.zoomOutAct.setIcon(QIcon(":/viewer/images/zoomout.png"))
        self.zoomOutAct.setIconVisibleInMenu(True)
        self.connect(self.zoomOutAct, SIGNAL("toggled(bool)"), self.zoomOut)

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
        self.flickerAct.setText("F&licker")
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

    def setupMenus(self):
        """
        Creates the menus and adds the actions to them
        """
        fileMenu = self.menuBar().addMenu("&File")
        fileMenu.addAction(self.addRasterAct)
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
        viewMenu.addAction(self.queryAct)
        viewMenu.addAction(self.newQueryAct)
        viewMenu.addAction(self.flickerAct)

    def setupToolbars(self):
        """
        Creates the toolbars and adds the actions to them
        """
        fileToolbar = self.addToolBar("File")
        fileToolbar.addAction(self.addRasterAct)
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
        viewToolbar.addAction(self.queryAct)
        viewToolbar.addAction(self.flickerAct)

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
        dlg.setFileMode(QFileDialog.ExistingFile)
        if dlg.exec_() == QDialog.Accepted:
            fname = dlg.selectedFiles()[0]
            self.addRasterInternal(fname)

    def addRasterInternal(self, fname, stretch=None):
        """
        Actually to the file opening. If stretch is None
        is is determined using our automatic scheme.
        """
        fname = str(fname) # was QString
        lut = None
        if stretch is None:
            # first see if it has a stretch saved in the file
            from osgeo import gdal
            try:
                gdaldataset = gdal.Open(fname)
            except RuntimeError:
                msg = "Unable to open %s" % fname
                QMessageBox.critical(self, MESSAGE_TITLE, msg)
                return

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

            # close dataset before we open it again
            # (may well be a better way)
            del gdaldataset

        # now open it for real
        try:
            self.viewwidget.addRasterLayer(fname, stretch, lut)
            self.viewwidget.setMouseScrollWheelAction(self.mouseWheelZoom)
        except Exception as e:
            QMessageBox.critical(self, "Viewer", str(e) )

        # set the window title
        self.setWindowTitle(os.path.basename(fname))
        # allow the stretch to be edited
        self.stretchAct.setEnabled(True)

    def removeLayer(self):
        """
        Remove the top most layer
        """
        self.viewwidget.removeLayer()

    def arrangeLayers(self):
        """
        Bring up the LayerWindow
        """
        from . import layerwindow
        layerWindow = layerwindow.LayerWindow(self, self.viewwidget)
        self.addDockWidget(Qt.LeftDockWidgetArea, layerWindow)

    def editStretch(self):
        """
        Show the edit stretch dock window
        """
        from . import stretchdialog
        stretchDock = stretchdialog.StretchDockWidget(self, self.viewwidget)
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
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_ZOOMIN)
        else:
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_NONE)

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
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_ZOOMOUT)
        else:
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_NONE)

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
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_PAN)
        else:
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_NONE)

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
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_QUERY)

            # if there is no query window currently open start one
            if self.queryWindowCount <= 0:
                self.newQueryWindow()
        else:
            self.viewwidget.setActiveTool(viewerwidget.VIEWER_TOOL_NONE)

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

        # grab the signal with queryDock sends when it is closed
        self.connect(queryDock, SIGNAL("queryClosed(PyQt_PyObject)"), 
                                                self.queryClosed)

        # increment our count
        self.queryWindowCount += 1

    def flicker(self):
        """
        Tell the widget to flicker
        """
        state = self.viewwidget.flicker()
        if state:
            self.flickerAct.setIcon(self.flickerAct.iconOn)
        else:
            self.flickerAct.setIcon(self.flickerAct.iconOff)

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

        settings.beginGroup('ViewerMouse')
        settings.setValue("mousescroll", self.mouseWheelZoom)
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
                self.addRasterInternal(url.path())

    def setPreferences(self):
        """
        Display the preferences dialog
        """
        from . import viewerpreferences
        viewPref = viewerpreferences.ViewerPreferencesDialog(self)
        viewPref.exec_()

        # extract the mouse wheel setting
        settings = QSettings()
        settings.beginGroup('ViewerMouse')
        self.mouseWheelZoom = True
        value = settings.value("mousescroll", self.mouseWheelZoom)
        self.mouseWheelZoom = value.toBool()
        settings.endGroup()

        self.viewwidget.setMouseScrollWheelAction(self.mouseWheelZoom)


