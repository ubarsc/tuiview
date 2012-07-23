"""
Module that contains the QueryDockWidget
"""

from PyQt4.QtGui import QDockWidget, QTableWidget, QTableWidgetItem, QIcon, QFileDialog
from PyQt4.QtGui import QHBoxLayout, QVBoxLayout, QLineEdit, QWidget, QColorDialog, QPixmap
from PyQt4.QtGui import QTabWidget, QLabel, QPen, QToolBar, QAction, QPrinter, QBrush
from PyQt4.QtGui import QFontMetrics, QColor
from PyQt4.QtCore import SIGNAL, Qt

# See if we have access to Qwt
HAVE_QWT = True
try:
    from PyQt4.Qwt5 import QwtPlot, QwtPlotCurve, QwtPlotMarker, QwtText, QwtScaleDiv
except ImportError:
    HAVE_QWT = False

from .viewerstretch import VIEWER_MODE_RGB, VIEWER_MODE_GREYSCALE
from . import viewererrors

QUERYWIDGET_DEFAULT_CURSORCOLOR = Qt.white
QUERYWIDGET_DEFAULT_HIGHLIGHTCOLOR = QColor(Qt.yellow)

# icons for displaying in the 'band' column for RGB
ICON_PIXMAP = QPixmap(24, 24)

ICON_PIXMAP.fill(Qt.red)
RED_ICON = QIcon(ICON_PIXMAP)

ICON_PIXMAP.fill(Qt.green)
GREEN_ICON = QIcon(ICON_PIXMAP)

ICON_PIXMAP.fill(Qt.blue)
BLUE_ICON = QIcon(ICON_PIXMAP)

# for greyscale
ICON_PIXMAP.fill(Qt.gray)
GREY_ICON = QIcon(ICON_PIXMAP)

class QueryDockWidget(QDockWidget):
    """
    Dock widget that contains the query window. Follows query 
    tool clicks (can be disabled) and can change query point color.
    Image values for point are displayed thanks to locationSelected
    signal from ViewerWidget. 
    """
    def __init__(self, parent, viewwidget):
        QDockWidget.__init__(self, "Query", parent)
        self.viewwidget = viewwidget
        self.cursorColor = QUERYWIDGET_DEFAULT_CURSORCOLOR
        self.highlightColor = QUERYWIDGET_DEFAULT_HIGHLIGHTCOLOR

        # create a new widget that lives in the dock window
        self.dockWidget = QWidget()

        self.toolBar = QToolBar(self.dockWidget)
        self.setupActions()
        self.setupToolbar()

        self.eastingEdit = QLineEdit(self.dockWidget)
        self.eastingEdit.setReadOnly(True)
        self.eastingEdit.setToolTip("Easting")

        self.northingEdit = QLineEdit(self.dockWidget)
        self.northingEdit.setReadOnly(True)
        self.northingEdit.setToolTip("Northing")

        self.coordLayout = QHBoxLayout()
        self.coordLayout.addWidget(self.eastingEdit)
        self.coordLayout.addWidget(self.northingEdit)

        self.tabWidget = QTabWidget(self.dockWidget)

        self.tableWidget = QTableWidget()
        # can only select rows - not individual items
        self.tableWidget.setSelectionBehavior(QTableWidget.SelectRows)

        if HAVE_QWT:
            self.plotWidget = QwtPlot()
            self.plotCurve = QwtPlotCurve()
            self.plotCurve.attach(self.plotWidget)
            self.oldPlotLabels = [] # so we can detach() them when we want to redisplay
        else:
            self.noQWTLabel = QLabel()
            self.noQWTLabel.setText("PyQwt needs to be installed for plot display")
            self.noQWTLabel.setAlignment(Qt.AlignCenter)

        self.tabWidget.addTab(self.tableWidget, "Table")
        if HAVE_QWT:
            self.tabWidget.addTab(self.plotWidget, "Plot")
        else:
            self.tabWidget.addTab(self.noQWTLabel, "Plot")

        self.mainLayout = QVBoxLayout()
        self.mainLayout.addWidget(self.toolBar)
        self.mainLayout.addLayout(self.coordLayout)
        self.mainLayout.addWidget(self.tabWidget)

        self.dockWidget.setLayout(self.mainLayout)
        
        # tell the dock window this is the widget to display
        self.setWidget(self.dockWidget)

        # keep a track of the last QueryInfo in case we need to redisplay
        # when the user changes color
        self.lastqi = None

    def getColorIcon(self, color):
        """
        Returns the icon for the change color tool
        which is based on the current color
        """
        pixmap = QPixmap(24, 24)
        pixmap.fill(color)
        return QIcon(pixmap)

    def setupActions(self):
        """
        Create the actions to be shown on the toolbar
        """
        self.followAction = QAction(self)
        self.followAction.setText("&Follow Query Tool")
        self.followAction.setStatusTip("Follow Query Tool")
        self.followAction.setIcon(QIcon(":/viewer/images/query.png"))
        self.followAction.setCheckable(True)
        self.followAction.setChecked(True)

        self.cursorColorAction = QAction(self)
        self.cursorColorAction.setText("&Change Cursor Color")
        self.cursorColorAction.setStatusTip("Change Cursor Color")
        icon = self.getColorIcon(self.cursorColor)
        self.cursorColorAction.setIcon(icon)        
        self.connect(self.cursorColorAction, SIGNAL("triggered()"), self.changeCursorColor)

        self.labelAction = QAction(self)
        self.labelAction.setText("&Display Plot Labels")
        self.labelAction.setStatusTip("Display Plot Labels")
        self.labelAction.setIcon(QIcon(":/viewer/images/label.png"))
        self.labelAction.setCheckable(True)
        self.labelAction.setChecked(True)
        self.connect(self.labelAction, SIGNAL("toggled(bool)"), self.changeLabel)

        self.saveAction = QAction(self)
        self.saveAction.setText("&Save Plot")
        self.saveAction.setStatusTip("Save Plot")
        self.saveAction.setIcon(QIcon(":/viewer/images/save.png"))
        self.connect(self.saveAction, SIGNAL("triggered()"), self.savePlot)

        self.highlightAction = QAction(self)
        self.highlightAction.setText("&Highlight Selection")
        self.highlightAction.setStatusTip("Highlight Selection")
        self.highlightAction.setIcon(QIcon(":/viewer/images/highlight.png"))
        self.connect(self.highlightAction, SIGNAL("triggered()"), self.highlight)

        self.highlightColorAction = QAction(self)
        self.highlightColorAction.setText("Ch&ange Highlight Color")
        self.highlightColorAction.setStatusTip("Change Highlight Color")
        icon = self.getColorIcon(self.highlightColor)
        self.highlightColorAction.setIcon(icon)
        self.connect(self.highlightColorAction, SIGNAL("triggered()"), self.changeHighlightColor)

    def setupToolbar(self):
        """
        Add the actions to the toolbar
        """
        self.toolBar.addAction(self.followAction)
        self.toolBar.addAction(self.cursorColorAction)
        self.toolBar.addAction(self.highlightAction)
        self.toolBar.addAction(self.highlightColorAction)
        if HAVE_QWT:
            self.toolBar.addAction(self.labelAction)
            self.toolBar.addAction(self.saveAction)


    def changeCursorColor(self):
        """
        User wishes to change cursor color
        """
        initial = self.cursorColor
        newcolor = QColorDialog.getColor(initial, self)
        if newcolor.isValid():
            # change the toolbar icon
            self.cursorColor = newcolor
            icon = self.getColorIcon(self.cursorColor)
            self.cursorColorAction.setIcon(icon)        
    
            # if there is a previous point, redisplay in new color
            if self.lastqi is not None:
                self.viewwidget.setQueryPoint(id(self), self.lastqi.column, self.lastqi.row, newcolor)
                if HAVE_QWT and self.lastqi is not None:
                    # to get new color
                    self.updatePlot(self.lastqi, newcolor)

    def changeHighlightColor(self):
        """
        User wishes to change highlight color
        """
        initial = self.highlightColor
        newcolor = QColorDialog.getColor(initial, self)
        if newcolor.isValid():
            # change the toolbar icon
            self.highlightColor = newcolor
            icon = self.getColorIcon(self.highlightColor)
            self.highlightColorAction.setIcon(icon)

            # re-highlight the selected rows
            self.highlight()

    def changeLabel(self, checked):
        """
        State of display labels check has been changed. Redisplay plot.
        """
        if HAVE_QWT and self.lastqi is not None:
            self.updatePlot(self.lastqi, self.cursorColor)

    def savePlot(self):
        """
        Save the plot as a file. Either .pdf or .ps QPrinter
        chooses format based on extension.
        """
        if HAVE_QWT:
            fname = QFileDialog.getSaveFileName(self, "Plot File", filter="PDF (*.pdf);;Postscript (*.ps)")
            if not fname.isEmpty():
                printer = QPrinter()
                printer.setOrientation(QPrinter.Landscape)
                printer.setColorMode(QPrinter.Color)
                printer.setOutputFileName(fname)
                printer.setResolution(96)
                self.plotWidget.print_(printer)

    def highlight(self):
        """
        Highlight the currently selected rows on the map
        """
        # convert the ranges into a list of rows
        selectedRanges = self.tableWidget.selectedRanges()
        rows = []
        for sel in selectedRanges:
            for row in range(sel.topRow(), sel.bottomRow() + 1):
                rows.append(row)
        
        # tell the widget to update
        try:
            self.viewwidget.highlightValues(self.highlightColor, rows)
        except viewererrors.InvalidDataset:
            pass

    def setupTableContinuous(self, qi):
        """
        setup the table for displaying Continuous
        data. This is a row per band with the pixel values for each band shown
        The current red, green and blue bands have an icon 
        """
        # can't highlight continuous
        self.highlightAction.setEnabled(False)
        self.highlightColorAction.setEnabled(False)

        nbands = qi.data.shape[0]
        # set up the table
        self.tableWidget.setRowCount(nbands)
        self.tableWidget.setColumnCount(3)

        self.tableWidget.setHorizontalHeaderLabels(["Band", "Name", "Value"])
        vertLabels = ["%s" % (x+1) for x in range(nbands)]
        self.tableWidget.setVerticalHeaderLabels(vertLabels)

        # fill in the table
        count = 0
        for x in qi.data:
            # value
            valitem = QTableWidgetItem("%s" % x)
            valitem.setFlags(Qt.ItemIsEnabled) # disable editing etc
            self.tableWidget.setItem(count, 2, valitem)

            # band name
            nameitem = QTableWidgetItem(qi.bandNames[count])
            nameitem.setFlags(Qt.ItemIsEnabled) # disable editing etc
            self.tableWidget.setItem(count, 1, nameitem)

            # color
            band = count + 1
            if qi.stretch.mode == VIEWER_MODE_RGB and band in qi.stretch.bands:
                coloritem = QTableWidgetItem()
                if band == qi.stretch.bands[0]:
                    # red
                    coloritem.setIcon(RED_ICON)
                elif band == qi.stretch.bands[1]:
                    # green
                    coloritem.setIcon(GREEN_ICON)
                elif band == qi.stretch.bands[2]:
                    # blue
                    coloritem.setIcon(BLUE_ICON)
                self.tableWidget.setItem(count, 0, coloritem)
            elif qi.stretch.mode == VIEWER_MODE_GREYSCALE and band == qi.stretch.bands[0]:
                greyitem = QTableWidgetItem()
                greyitem.setIcon(GREY_ICON)
                self.tableWidget.setItem(count, 0, greyitem)
            else:
                # blank item - might be stuff still there from attributes
                item = QTableWidgetItem()
                self.tableWidget.setItem(count, 0, item)

            count += 1

    def setupTableThematic(self, qi):
        """
        For a single band dataset with attributes. Displays
        the attributes as a table and highlights the current
        value in the table. 
        """
        # we can highlight thematic
        self.highlightAction.setEnabled(True)
        self.highlightColorAction.setEnabled(True)

        val = qi.data[0]
        ncols = len(qi.columnNames)
        # should all be the same length
        nrows = len(qi.attributeData[qi.columnNames[0]])

        self.tableWidget.setRowCount(nrows)
        self.tableWidget.setColumnCount(ncols)

        self.tableWidget.setHorizontalHeaderLabels(qi.columnNames)
        vertLabels = ["%s" % x for x in range(nrows)]
        self.tableWidget.setVerticalHeaderLabels(vertLabels)

        highlightBrush = QBrush(Qt.yellow)
        for col in range(ncols):
            colattr = qi.attributeData[qi.columnNames[col]]
            for row in range(nrows):
                highlight = row == val
                item = QTableWidgetItem(colattr[row])
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable) # disable editing etc, but allow selection
                self.tableWidget.setItem(row, col, item)
                if highlight:
                    item.setBackground(highlightBrush)

        # return the value to scroll to
        return val 

    def locationSelected(self, qi):
        """
        The ViewerWidget has told us it has a new coordinate from
        the query tool.
        """
        if self.followAction.isChecked():
            # set the coords
            self.eastingEdit.setText("%.5f" % qi.easting)
            self.northingEdit.setText("%.5f" % qi.northing)
            nbands = qi.data.shape[0]

            # do the attribute thing if there is only one band
            # and we have attributes
            scrollRow = None
            if nbands == 1 and qi.columnNames is not None and len(qi.columnNames) != 0:
                scrollRow = self.setupTableThematic(qi)
            else:
                # otherwise the multi band table
                self.setupTableContinuous(qi)

            # hack to ensure that the rows in the table are only 
            # as high as they need to be - by default they are very 
            # high wasting a lot of screen space
            item = self.tableWidget.item(0, 0)  # get the top left item 
            fm = QFontMetrics(item.font())      # get info about its font
            height = fm.height()                # get the height
            nrows = self.tableWidget.rowCount()
            for row in range(nrows):
                # set all rows to the necessary height
                self.tableWidget.setRowHeight(row, height)
            # not sure how to resize the header...

            # set up the plot
            if HAVE_QWT:
                self.updatePlot(qi, self.cursorColor)

            # after we have finished rejigging the UI
            # scroll to the selected row (only used for thematic ATM)
            if scrollRow is not None:
                item = self.tableWidget.item(scrollRow, 0)
                if item is not None:
                    self.tableWidget.scrollToItem(item, QTableWidget.PositionAtCenter)


            # add/modify this is a query point to the widget
            self.viewwidget.setQueryPoint(id(self), qi.column, qi.row, self.cursorColor)
            # remember this qi in case we need to change color
            self.lastqi = qi

    def updatePlot(self, qi, color):
        """
        Updates the plot widget with new data/color
        """
        pen = QPen(color)
        pen.setWidth(2)
        self.plotCurve.setPen(pen)
        nbands = qi.data.shape[0]

        if qi.wavelengths is None:
            # no wavelengths stored with data - just use band number
            xdata = range(1, nbands+1, 1)
        else:
            xdata = qi.wavelengths

        self.plotCurve.setData(xdata, qi.data)

        # detach any old ones
        for marker in self.oldPlotLabels:
            marker.detach()
        self.oldPlotLabels = []

        # only do new labels if they have asked for them.
        if self.labelAction.isChecked():
            count = 1
            for x, y, text in zip(xdata, qi.data, qi.bandNames):
                marker = QwtPlotMarker()
                text = QwtText(text)
                marker.setLabel(text)
                marker.setValue(x, y)
            
                # align appropriately for first and last
                if count == 1:
                    marker.setLabelAlignment(Qt.AlignRight)
                elif count == nbands:
                    marker.setLabelAlignment(Qt.AlignLeft)
            
                marker.attach(self.plotWidget)
                self.oldPlotLabels.append(marker)
                count += 1

        # make xaxis labels integer if no wavelengths
        if qi.wavelengths is None:
            div = self.plotWidget.axisScaleDiv(QwtPlot.xBottom)
            div.setInterval(1, nbands)
            div.setTicks(QwtScaleDiv.MajorTick, xdata)
            self.plotWidget.setAxisScaleDiv(QwtPlot.xBottom, div)

        self.plotWidget.replot()
        

    def closeEvent(self, event):
        """
        Window is being closed - inform parent window
        """
        self.viewwidget.removeQueryPoint(id(self))
        self.emit(SIGNAL("queryClosed(PyQt_PyObject)"), self)

