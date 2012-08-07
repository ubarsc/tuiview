
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
    drivermeta = driver.GetMetadata()
    name = 'Image Files'
    if drivermeta.has_key("DMD_LONGNAME"):
        name = drivermeta["DMD_LONGNAME"]
        # get rid of any stuff in brackets - seems to
        # confuse Qt 4.x
        firstbracket = name.find('(')
        if firstbracket != -1:
            name = name[:firstbracket]
    filter = '*'
    if drivermeta.has_key("DMD_EXTENSION"):
        filter = drivermeta["DMD_EXTENSION"]
    return "%s (*.%s)" % (name,filter)

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
            filter = createFilter(driver)
            GDAL_FILTERS.append(filter)

        # just go thru them all and create filters
        for count in range(gdal.GetDriverCount()):
            driver = gdal.GetDriver(count)
            filter = createFilter(driver)
            GDAL_FILTERS.append(filter)


class ViewerWindow(QMainWindow):
    """
    Main window for viewer application
    """
    def __init__(self):
        QMainWindow.__init__(self)
        self.setWindowTitle('Viewer')
        self.viewwidget = viewerwidget.ViewerWidget(self)

        # connect to the signals emmitted by the LUT
        # so we can update our progress bar
        # TODO
        #self.connect(self.viewwidget.lut, SIGNAL("newProgress(QString)"), self.newProgress)
        #self.connect(self.viewwidget.lut, SIGNAL("endProgress()"), self.endProgress)
        #self.connect(self.viewwidget.lut, SIGNAL("newPercent(int)"), self.newPercent)

        # same with the RAT for reading in attributes
        #self.connect(self.viewwidget.attributes, SIGNAL("newProgress(QString)"), self.newProgress)
        #self.connect(self.viewwidget.attributes, SIGNAL("endProgress()"), self.endProgress)
        #self.connect(self.viewwidget.attributes, SIGNAL("newPercent(int)"), self.newPercent)

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
        self.mouseWheelZoom = settings.value("mousescroll", self.mouseWheelZoom).toBool()
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
        self.connect(self.addRasterAct, SIGNAL("triggered()"), self.addRaster)

        self.removeLayerAct = QAction(self)
        self.removeLayerAct.setText("&Remove Layer")
        self.removeLayerAct.setStatusTip("Remove top layer")
        self.removeLayerAct.setShortcut("CTRL+R")
        self.removeLayerAct.setIcon(QIcon(":/viewer/images/removelayer.png"))
        self.connect(self.removeLayerAct, SIGNAL("triggered()"), self.removeLayer)

        self.newWindowAct = QAction(self)
        self.newWindowAct.setText("&New Window")
        self.newWindowAct.setStatusTip("Create a new geo linked window")
        self.newWindowAct.setShortcut("CTRL+N")
        self.newWindowAct.setIcon(QIcon(":/viewer/images/newwindow.png"))
        self.connect(self.newWindowAct, SIGNAL("triggered()"), self.newWindow)

        self.tileWindowsAct = QAction(self)
        self.tileWindowsAct.setText("&Tile Windows...")
        self.tileWindowsAct.setStatusTip("Tile all open windows")
        self.tileWindowsAct.setShortcut("CTRL+I")
        self.connect(self.tileWindowsAct, SIGNAL("triggered()"), self.tileWindows)

        self.defaultStretchAct = QAction(self)
        self.defaultStretchAct.setText("&Default Stretch...")
        self.defaultStretchAct.setStatusTip("Set default stretches")
        self.defaultStretchAct.setShortcut("CTRL+D")
        self.connect(self.defaultStretchAct, SIGNAL("triggered()"), self.defaultStretch)

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
        self.connect(self.panAct, SIGNAL("toggled(bool)"), self.pan)

        self.zoomInAct = QAction(self)
        self.zoomInAct.setText("Zoom &In")
        self.zoomInAct.setStatusTip("Zoom In")
        self.zoomInAct.setShortcut("CTRL++")
        self.zoomInAct.setCheckable(True)
        self.zoomInAct.setIcon(QIcon(":/viewer/images/zoomin.png"))
        self.connect(self.zoomInAct, SIGNAL("toggled(bool)"), self.zoomIn)

        self.zoomOutAct = QAction(self)
        self.zoomOutAct.setText("Zoom &Out")
        self.zoomOutAct.setStatusTip("Zoom Out")
        self.zoomOutAct.setShortcut("CTRL+-")
        self.zoomOutAct.setCheckable(True)
        self.zoomOutAct.setIcon(QIcon(":/viewer/images/zoomout.png"))
        self.connect(self.zoomOutAct, SIGNAL("toggled(bool)"), self.zoomOut)

        self.zoomNativeAct = QAction(self)
        self.zoomNativeAct.setText("Zoom to &Native")
        self.zoomNativeAct.setStatusTip("Zoom to Native Resolution")
        self.zoomNativeAct.setShortcut("CTRL+1")
        self.zoomNativeAct.setIcon(QIcon(":/viewer/images/zoomnative.png"))
        self.connect(self.zoomNativeAct, SIGNAL("triggered()"), self.zoomNative)

        self.zoomFullExtAct = QAction(self)
        self.zoomFullExtAct.setText("Zoom to &Full Extent")
        self.zoomFullExtAct.setStatusTip("Zoom to Full Extent")
        self.zoomFullExtAct.setShortcut("CTRL+F")
        self.zoomFullExtAct.setIcon(QIcon(":/viewer/images/zoomfullextent.png"))
        self.connect(self.zoomFullExtAct, SIGNAL("triggered()"), self.zoomFullExtent)

        self.followExtentAct = QAction(self)
        self.followExtentAct.setText("Follow &Extent")
        self.followExtentAct.setStatusTip("Follow geolinked extent")
        self.followExtentAct.setShortcut("CTRL+E")
        self.followExtentAct.setCheckable(True)
        self.followExtentAct.setChecked(True) # by default to match viewerwidget
        self.followExtentAct.setIcon(QIcon(":/viewer/images/followextents.png"))
        self.connect(self.followExtentAct, SIGNAL("toggled(bool)"), self.followExtent)

        self.queryAct = QAction(self)
        self.queryAct.setText("&Query Tool")
        self.queryAct.setStatusTip("Start Query Tool")
        self.queryAct.setShortcut("CTRL+U")
        self.queryAct.setCheckable(True)
        self.queryAct.setIcon(QIcon(":/viewer/images/query.png"))
        self.connect(self.queryAct, SIGNAL("toggled(bool)"), self.query)

        self.newQueryAct = QAction(self)
        self.newQueryAct.setText("New Query &Window")
        self.newQueryAct.setStatusTip("Open New Query Window")
        self.newQueryAct.setShortcut("CTRL+W")
        self.connect(self.newQueryAct, SIGNAL("triggered()"), self.newQueryWindow)

        self.exitAct = QAction(self)
        self.exitAct.setText("&Close")
        self.exitAct.setStatusTip("Close this window")
        self.exitAct.setShortcut("CTRL+Q")
        self.connect(self.exitAct, SIGNAL("triggered()"), self.close)

        self.preferencesAct = QAction(self)
        self.preferencesAct.setText("&Preferences")
        self.preferencesAct.setStatusTip("Edit Preferences")
        self.preferencesAct.setShortcut("CTRL+L")
        self.connect(self.preferencesAct, SIGNAL("triggered()"), self.setPreferences)

    def setupMenus(self):
        """
        Creates the menus and adds the actions to them
        """
        self.fileMenu = self.menuBar().addMenu("&File")
        self.fileMenu.addAction(self.addRasterAct)
        self.fileMenu.addAction(self.removeLayerAct)
        self.fileMenu.addAction(self.newWindowAct)
        self.fileMenu.addAction(self.tileWindowsAct)
        self.fileMenu.addAction(self.defaultStretchAct)
        self.fileMenu.addAction(self.exitAct)
        self.fileMenu.insertSeparator(self.exitAct)

        self.editMenu = self.menuBar().addMenu("&Edit")
        self.editMenu.addAction(self.stretchAct)
        self.editMenu.addAction(self.preferencesAct);

        self.viewMenu = self.menuBar().addMenu("&View")
        self.viewMenu.addAction(self.panAct)
        self.viewMenu.addAction(self.zoomInAct)
        self.viewMenu.addAction(self.zoomOutAct)
        self.viewMenu.addAction(self.zoomNativeAct)
        self.viewMenu.addAction(self.zoomFullExtAct)
        self.viewMenu.addAction(self.followExtentAct)
        self.viewMenu.addAction(self.queryAct)
        self.viewMenu.addAction(self.newQueryAct)

    def setupToolbars(self):
        """
        Creates the toolbars and adds the actions to them
        """
        self.fileToolbar = self.addToolBar("File")
        self.fileToolbar.addAction(self.addRasterAct)
        self.fileToolbar.addAction(self.removeLayerAct)
        self.fileToolbar.addAction(self.newWindowAct)

        self.viewToolbar = self.addToolBar("View")
        self.viewToolbar.addAction(self.panAct)
        self.viewToolbar.addAction(self.zoomInAct)
        self.viewToolbar.addAction(self.zoomOutAct)
        self.viewToolbar.addAction(self.zoomNativeAct)
        self.viewToolbar.addAction(self.zoomFullExtAct)
        self.viewToolbar.addAction(self.followExtentAct)
        self.viewToolbar.addAction(self.queryAct)

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
        from osgeo import gdal
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
                QMessageBox.critical(self, MESSAGE_TITLE, "Unable to open %s" % fname)
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
                msg = "File has no stretch saved and none of the default stretches match\n\
The default stretch dialog will now open."
                QMessageBox.warning(self, MESSAGE_TITLE, msg)
                self.defaultStretch()
                return

            # close dataset before we open it again
            # (may well be a better way)
            del gdaldataset

        # now open it for real
        #try:
        # TODO
        self.viewwidget.addRasterLayer(fname, stretch, lut)
        self.viewwidget.setMouseScrollWheelAction(self.mouseWheelZoom)
        #except Exception as e:
        #    QMessageBox.critical(self, "Viewer", str(e) )

        # set the window title
        self.setWindowTitle(os.path.basename(fname))
        # allow the stretch to be edited
        self.stretchAct.setEnabled(True)

    def removeLayer(self):
        """
        Remove the top most layer
        """
        self.viewwidget.removeLayer()

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
        #try:
        # TODO
        self.viewwidget.zoomNativeResolution()
        #except Exception as e:
        #    QMessageBox.critical(self, "Viewer", str(e) )

    def zoomFullExtent(self):
        """
        Tell the widget to zoom back to the full extent
        """
        #try:
        # TODO
        self.viewwidget.zoomFullExtent()
        #except Exception as e:
        #    QMessageBox.critical(self, "Viewer", str(e) )

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
        self.disconnect(self.viewwidget, SIGNAL("locationSelected(PyQt_PyObject)"), queryDock.locationSelected)
        self.queryWindowCount -= 1

    def newQueryWindow(self):
        """
        Create a new QueryDockWidget and connect signals
        and increment our count of these windows
        """
        from . import querywindow
        queryDock = querywindow.QueryDockWidget(self, self.viewwidget)
        self.addDockWidget(Qt.BottomDockWidgetArea, queryDock)

        # connect it to signals emitted by the viewerwidget
        self.connect(self.viewwidget, SIGNAL("locationSelected(PyQt_PyObject)"), queryDock.locationSelected)

        # grab the signal with queryDock sends when it is closed
        self.connect(queryDock, SIGNAL("queryClosed(PyQt_PyObject)"), self.queryClosed)

        # increment our count
        self.queryWindowCount += 1

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
        self.mouseWheelZoom = settings.value("mousescroll", self.mouseWheelZoom).toBool()
        settings.endGroup()

        self.viewwidget.setMouseScrollWheelAction(self.mouseWheelZoom)


