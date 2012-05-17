
"""
Main Window of the Viewer application. Contains
the ViewerWidget, menus, toolbars and status bars.
"""

import os
from PyQt4.QtGui import QMainWindow, QAction, QIcon, QFileDialog, QDialog, QMessageBox, QProgressBar
from PyQt4.QtCore import QSettings, QSize, QPoint, SIGNAL, QStringList, Qt

from . import viewerresources
from . import viewerwidget
from . import stretchdialog

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

        # if we have a default driver do it first
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
        self.connect(self.viewwidget.lut, SIGNAL("newProgress(QString)"), self.newProgress)
        self.connect(self.viewwidget.lut, SIGNAL("endProgress()"), self.endProgress)
        self.connect(self.viewwidget.lut, SIGNAL("newPercent(int)"), self.newPercent)

        self.setCentralWidget(self.viewwidget)

        self.setupActions()
        self.setupMenus()
        self.setupToolbars()
        self.setupStatusBar()

        self.restoreFromSettings()

        self.showStatusMessage("Ready")

    def newProgress(self, string):
        """
        Called when we are about to start a new progress
        """
        self.statusBar().showMessage(string)
        self.progressWidget.setValue(0)
        self.progressWidget.setVisible(True)

    def endProgress(self):
        self.statusBar().clearMessage()
        self.progressWidget.setVisible(False)

    def newPercent(self, percent):
        self.progressWidget.setValue(percent)

    def showStatusMessage(self, message):
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

    def setupActions(self):
        """
        Creates all the actions for the Window
        """
        self.openAct = QAction(self)
        self.openAct.setText("&Open")
        self.openAct.setStatusTip("Open a GDAL supported image")
        self.openAct.setShortcut("CTRL+O")
        self.openAct.setIcon(QIcon(":/viewer/images/open.png"))
        self.connect(self.openAct, SIGNAL("activated()"), self.openFile)

        self.defaultStretchAct = QAction(self)
        self.defaultStretchAct.setText("&Default Stretch...")
        self.defaultStretchAct.setStatusTip("Set default stretches")
        self.defaultStretchAct.setShortcut("CTRL+D")
        self.connect(self.defaultStretchAct, SIGNAL("activated()"), self.defaultStretch)

        self.stretchAct = QAction(self)
        self.stretchAct.setText("S&tretch")
        self.stretchAct.setStatusTip("Edit current stretch")
        self.stretchAct.setShortcut("CTRL+T")
        self.stretchAct.setEnabled(False) # until a file is opened
        self.connect(self.stretchAct, SIGNAL("activated()"), self.editStretch)

        self.exitAct = QAction(self)
        self.exitAct.setText("&Close")
        self.exitAct.setStatusTip("Close this window")
        self.exitAct.setShortcut("CTRL+Q")
        self.connect(self.exitAct, SIGNAL("activated()"), self.close)

    def setupMenus(self):
        """
        Creates the menus and adds the actions to them
        """
        self.fileMenu = self.menuBar().addMenu("&File")
        self.fileMenu.addAction(self.openAct)
        self.fileMenu.addAction(self.defaultStretchAct)
        self.fileMenu.addAction(self.exitAct)
        self.fileMenu.insertSeparator(self.exitAct)

        self.editMenu = self.menuBar().addMenu("&Edit")
        self.editMenu.addAction(self.stretchAct)

    def setupToolbars(self):
        """
        Creates the toolbars and adds the actions to them
        """
        self.fileToolbar = self.addToolBar("File")
        self.fileToolbar.addAction(self.openAct)

    def setupStatusBar(self):
        """
        Sets up the status bar
        """
        statusbar = self.statusBar()
        statusbar.setSizeGripEnabled(True)
        self.progressWidget = QProgressBar(self)
        self.progressWidget.setMinimum(0)
        self.progressWidget.setMaximum(100)
        self.progressWidget.setVisible(False)
        self.statusBar().addPermanentWidget(self.progressWidget)

    def defaultStretch(self):
        """
        Show the default stretch dialog
        """
        dlg = stretchdialog.StretchDefaultsDialog(self)
        dlg.exec_()

    def openFile(self):
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
            self.openFileInternal(fname)


    def openFileInternal(self, fname, stretch=None):
        fname = str(fname) # was QString
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
                defaultList = stretchdialog.StretchDefaultsDialog.fromSettings()
                for rule in defaultList:
                    if rule.isMatch(gdaldataset):
                        stretch = rule.stretch
                        break

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
        self.viewwidget.open(fname, stretch)
        # set the window title
        self.setWindowTitle(os.path.basename(fname))
        # allow the stretch to be edited
        self.stretchAct.setEnabled(True)

    def editStretch(self):
        """
        Show the edit stretch dock window
        """
        stretchDock = stretchdialog.StretchDockWidget(self, self.viewwidget)
        self.addDockWidget(Qt.TopDockWidgetArea, stretchDock)

    def closeEvent(self, event):
        """
        Window is being closed. Save the position and size.
        """
        settings = QSettings()
        settings.beginGroup('ViewerWindow')
        settings.setValue("size", self.size())
        settings.setValue("pos", self.pos())
        settings.endGroup()
        event.accept()

