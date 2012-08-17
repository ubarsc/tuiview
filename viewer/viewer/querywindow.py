"""
Module that contains the QueryDockWidget
"""

from PyQt4.QtGui import QDockWidget, QTableView, QIcon, QFileDialog, QItemDelegate
from PyQt4.QtGui import QHBoxLayout, QVBoxLayout, QLineEdit, QWidget, QColorDialog, QPixmap
from PyQt4.QtGui import QTabWidget, QLabel, QPen, QToolBar, QAction, QPrinter, QBrush
from PyQt4.QtGui import QFontMetrics, QColor, QMessageBox
from PyQt4.QtGui import QStyledItemDelegate, QStyle, QItemSelectionModel
from PyQt4.QtCore import SIGNAL, Qt, QVariant, QAbstractTableModel, QSize, QModelIndex
import numpy

# See if we have access to Qwt
HAVE_QWT = True
try:
    from PyQt4.Qwt5 import QwtPlot, QwtPlotCurve, QwtPlotMarker, QwtText, QwtScaleDiv
except ImportError:
    HAVE_QWT = False

from .viewerstretch import VIEWER_MODE_RGB, VIEWER_MODE_GREYSCALE
from .userexpressiondialog import UserExpressionDialog
from .viewerRAT import ViewerRAT
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


class ThematicTableModel(QAbstractTableModel):
    """
    This class is the 'model' that drives the thematic table.
    QTableView asks it for the data etc
    """
    def __init__(self, attributes, parent):
        QAbstractTableModel.__init__(self, parent)
        self.attributes = attributes
        self.saneColNames = attributes.getSaneColumnNames()
        self.highlightBrush = QBrush(QUERYWIDGET_DEFAULT_HIGHLIGHTCOLOR)
        self.highlightRow = -1

    def setHighlightRow(self, row):
        """
        Called by setupTableThematic to indicate 
        the row that should be highlighted
        """
        self.highlightRow = row

    def rowCount(self, parent):
        "returns the number of rows"
        return self.attributes.getNumRows()

    def columnCount(self, parent):
        "number of columns"
        return self.attributes.getNumColumns()

    def headerData(self, section, orientation, role):
        """
        returns the header labels for either vertical or
        horizontal
        """
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            name = self.saneColNames[section]
            return QVariant(name)
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            # rows just a number
            return QVariant("%s" % section)
        else:
            return QVariant()

    def data(self, index, role):
        """
        Gets the actual data. A variety of Qt.ItemDataRole's
        are passed, but we only use DisplayRole for the text
        and Qt.BackgroundRole for the highlight role
        """
        if not index.isValid():
            return QVariant()

        row = index.row()
        if role == Qt.BackgroundRole and row == self.highlightRow:
            return self.highlightBrush

        if role == Qt.DisplayRole: 
            column = index.column()
            name = self.attributes.getColumnNames()[column]
            attr = self.attributes.getAttribute(name)
            return QVariant("%s" % attr[row]) 
        else:
            QVariant()

class ContinuousTableModel(QAbstractTableModel):
    """
    This class is the 'model' that drives the continuous table.
    QTableView asks it for the data etc
    """
    def __init__(self, data, bandNames, stretch, parent):
        QAbstractTableModel.__init__(self, parent)
        self.data = data
        self.bandNames = bandNames
        self.stretch = stretch
        self.colNames = ["Band", "Name", "Value"]

    def rowCount(self, parent):
        "returns the number of rows"
        return self.data.shape[0]

    def columnCount(self, parent):
        "number of columns"
        return 3

    def headerData(self, section, orientation, role):
        """
        returns the header labels for either vertical or
        horizontal
        """
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            name = self.colNames[section]
            return QVariant(name)
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            # rows just a number
            return QVariant("%s" % (section + 1))
        else:
            return QVariant()

    def data(self, index, role):
        """
        Gets the actual data. A variety of Qt.ItemDataRole's
        are passed, but we only use DisplayRole for the text
        and Qt.BackgroundRole for the highlight role
        """
        if not index.isValid():
            return QVariant()

        column = index.column()
        row = index.row()
        if column == 0 and role == Qt.DecorationRole:
            # icon column
            band = row + 1
            if self.stretch.mode == VIEWER_MODE_RGB and band in self.stretch.bands:
                if band == self.stretch.bands[0]:
                    return RED_ICON
                elif band == self.stretch.bands[1]:
                    return GREEN_ICON
                elif band == self.stretch.bands[2]:
                    return BLUE_ICON
                else:
                    return QVariant()
            elif self.stretch.mode == VIEWER_MODE_GREYSCALE and band == self.stretch.bands[0]:
                return GREY_ICON

            else:
                return QVariant()

        elif column == 1 and role == Qt.DisplayRole: 
            # band names column
            return QVariant(self.bandNames[row])

        elif column == 2 and role == Qt.DisplayRole:
            # band values column
            return QVariant("%s" % self.data[row])

        else:
            QVariant()

class ThematicSelectionModel(QItemSelectionModel):
    """
    Selection model for the thematic table. We override the 
    default because we don't want the selection model
    to record any selections to make life easier for us.
    Ideally we would override the isSelected method but
    this is not declared virtual so we have to do this and
    paint the selections via the ItemDelegate.
    """
    def __init__(self, model, parent):
        QItemSelectionModel.__init__(self, model)
        self.parent = parent

    def select(self, index, command):
        """
        Override and don't call base class so nothing
        selected as far as selection model concerned
        """
        # seems that the rows can be repeated
        # so just operate on unique values
        # because we toggling
        unique_rows = {}
        if isinstance(index, QModelIndex):
            unique_rows[index.row()] = 1
        else:
            # QItemSelection
            for idx in index.indexes():
                unique_rows[idx.row()] = 1

        # if we are to clear first, do so
        if (command & QItemSelectionModel.Clear) == QItemSelectionModel.Clear:
            self.parent.selectionArray.fill(False)

        # toggle all the indexes
        for idx in unique_rows:
            self.parent.selectionArray[idx] = not self.parent.selectionArray[idx]

        self.parent.updateToolTip()

        # update the view
        self.parent.tableView.viewport().update()
        # note: the behaviour still not right....

class ThematicItemDelegate(QStyledItemDelegate):
    """
    Because we can't override the isSelected method of the modelselection
    we draw the selected state via the item delegate paint method as needed
    """
    def __init__(self, parent):
        QStyledItemDelegate.__init__(self, parent)
        self.parent = parent

    def paint(self, painter, option, index):
        if self.parent.selectionArray is not None and self.parent.selectionArray[index.row()]:
            option.state |= QStyle.State_Selected
        # shouldn't have to un-select as nothing should be selected
        # according to the model
        QStyledItemDelegate.paint(self, painter, option, index)

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

        self.tableView = QTableView()
        # can only select rows - not individual items
        self.tableView.setSelectionBehavior(QTableView.SelectRows)

        # the model - this is None by default - changed if 
        # it is a thematic view
        self.tableModel = None

        # the delegate - this renders the rows with optional selection
        # style. Ideally we would overried the selection model but
        # QItemSelectionModel.isSelected not virtual...
        self.tableDelegate = ThematicItemDelegate(self)
        self.tableView.setItemDelegate(self.tableDelegate)

        # our numpy array that contains the selections
        # None by default and for Continuous
        self.selectionArray = None

        # the id() of the last ViewerRAT class so we can 
        # update display only when needed
        self.lastAttributeid = -1
        # the 'count' of files opened by that object
        # so we can tell if the same object has opened another file
        self.lastAttributeCount = -1

        # now make sure the size of the rows matches the font we are using
        font = self.tableView.viewOptions().font
        fm = QFontMetrics(font)
        height = fm.height()
        # default height actually controlled by headers
        # don't worry about QItemDelegate etc
        self.tableView.verticalHeader().setDefaultSectionSize(height)

        if HAVE_QWT:
            self.plotWidget = QwtPlot()
            self.plotWidget.setMinimumSize(100, 100)
            self.plotCurve = QwtPlotCurve()
            self.plotCurve.attach(self.plotWidget)
            self.oldPlotLabels = [] # so we can detach() them when we want to redisplay
        else:
            self.noQWTLabel = QLabel()
            self.noQWTLabel.setText("PyQwt needs to be installed for plot display")
            self.noQWTLabel.setAlignment(Qt.AlignCenter)

        self.tabWidget.addTab(self.tableView, "Table")
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

        # these stay disabled until thematic selected
        self.highlightAction.setEnabled(False)
        self.highlightColorAction.setEnabled(False)
        self.expressionAction.setEnabled(False)

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

        self.removeSelectionAction = QAction(self)
        self.removeSelectionAction.setText("&Remove Current Selection")
        self.removeSelectionAction.setStatusTip("Remove Current Selection")
        self.removeSelectionAction.setIcon(QIcon(":/viewer/images/removeselection.png"))
        self.connect(self.removeSelectionAction, SIGNAL("triggered()"), self.removeSelection)

        self.expressionAction = QAction(self)
        self.expressionAction.setText("Select using an &Expression")
        self.expressionAction.setStatusTip("Select using an Expression")
        self.expressionAction.setIcon(QIcon(":/viewer/images/userexpression.png"))
        self.connect(self.expressionAction, SIGNAL("triggered()"), self.showUserExpression)

    def setupToolbar(self):
        """
        Add the actions to the toolbar
        """
        self.toolBar.addAction(self.followAction)
        self.toolBar.addAction(self.cursorColorAction)
        self.toolBar.addAction(self.highlightAction)
        self.toolBar.addAction(self.highlightColorAction)
        self.toolBar.addAction(self.removeSelectionAction)
        self.toolBar.addAction(self.expressionAction)
        if HAVE_QWT:
            self.toolBar.addAction(self.labelAction)
            self.toolBar.addAction(self.saveAction)


    def changeCursorColor(self):
        """
        User wishes to change cursor color
        """
        initial = self.cursorColor
        newcolor = QColorDialog.getColor(initial, self, 
                    "Choose Cursor Color", QColorDialog.ShowAlphaChannel)
        if newcolor.isValid():
            # change the toolbar icon
            self.cursorColor = newcolor
            icon = self.getColorIcon(self.cursorColor)
            self.cursorColorAction.setIcon(icon)        
    
            # if there is a previous point, redisplay in new color
            if self.lastqi is not None:
                self.viewwidget.setQueryPoint(id(self), self.lastqi.easting, self.lastqi.northing, newcolor)
                if HAVE_QWT and self.lastqi is not None:
                    # to get new color
                    self.updatePlot(self.lastqi, newcolor)

    def changeHighlightColor(self):
        """
        User wishes to change highlight color
        """
        initial = self.highlightColor
        newcolor = QColorDialog.getColor(initial, self, 
                "Choose Highlight Color", QColorDialog.ShowAlphaChannel)
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
        # tell the widget to update
        try:
            self.viewwidget.highlightValues(self.highlightColor, self.selectionArray)
        except viewererrors.InvalidDataset:
            pass

    def removeSelection(self):
        """
        Remove the current selection from the table widget
        """
        self.selectionArray.fill(False)
        self.updateToolTip()
        # so we repaint and our itemdelegate gets called
        self.tableView.viewport().update()

    def showUserExpression(self):
        """
        Allow user to enter expression to select rows
        """
        dlg = UserExpressionDialog(self)
        self.connect(dlg, SIGNAL("newExpression(QString)"), self.newUserExpression)
        dlg.show()

    def newUserExpression(self, expression):
        """
        Called in reponse to signal from UserExpressionDialog
        """
        try:
            # get the numpy array with bools
            result = self.lastqi.attributes.evaluateUserExpression(str(expression))

            # use it as our selection array
            self.selectionArray = result

            self.updateToolTip()
            # so we repaint and our itemdelegate gets called
            self.tableView.viewport().update()

        except viewererrors.UserExpressionError, e:
            QMessageBox.critical(self, "Viewer", str(e))

    def updateToolTip(self):
        """
        When in thematic mode we set a toolip
        over the attributes that tells the user how many items selected
        """
        # in numpy, False=0 and True=1 so we can do a sum()
        # to find how many selected
        nselected = self.selectionArray.sum()
        self.tableView.setToolTip("%d Selected" % nselected)
        

    def setupTableContinuous(self, qi):
        """
        setup the table for displaying Continuous
        data. This is a row per band with the pixel values for each band shown
        The current red, green and blue bands have an icon 
        """
        # can't highlight continuous
        self.highlightAction.setEnabled(False)
        self.highlightColorAction.setEnabled(False)
        self.expressionAction.setEnabled(False)

        self.tableModel = ContinuousTableModel(qi.data, qi.bandNames, qi.stretch, self)
        self.tableView.setModel(self.tableModel)

        self.selectionArray = None # no selections

        self.tableView.setToolTip("") # disable toolip

    def setupTableThematic(self, qi):
        """
        For a single band dataset with attributes. Displays
        the attributes as a table and highlights the current
        value in the table. 
        """
        # we can highlight thematic
        self.highlightAction.setEnabled(True)
        self.highlightColorAction.setEnabled(True)
        self.expressionAction.setEnabled(True)

        val = qi.data[0]

        # do we need a new table model?
        # do we have a new id() if the attribute obj
        # or a new count of the file opened by that object
        if id(qi.attributes) != self.lastAttributeid or qi.attributes.count != self.lastAttributeCount:
            self.lastAttributeCount = qi.attributes.count
            self.lastAttributeid = id(qi.attributes)

            self.tableModel = ThematicTableModel(qi.attributes, self)
            self.tableView.setModel(self.tableModel)

            # create our own selection model so nothing gets selected
            # as far as the model is concerned
            selectionModel = ThematicSelectionModel(self.tableModel, self)
            self.tableView.setSelectionModel(selectionModel)

            # create our selection array to record which items selected
            self.selectionArray = numpy.empty(qi.attributes.getNumRows(), numpy.bool)
            self.selectionArray.fill(False) # none selected by default

        # set the highlight row
        self.tableModel.setHighlightRow(val)

        # scroll to the new index
        index = self.tableView.model().index(val, 0)
        self.tableView.scrollTo(index, QTableView.PositionAtCenter)

        self.updateToolTip()

        # so the items get redrawn and old highlight areas get removed
        self.tableView.viewport().update()
        

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
            if nbands == 1 and qi.attributes.hasAttributes():
                self.setupTableThematic(qi)
            else:
                # otherwise the multi band table
                self.setupTableContinuous(qi)

            # set up the plot
            if HAVE_QWT:
                self.updatePlot(qi, self.cursorColor)

            # add/modify this is a query point to the widget
            self.viewwidget.setQueryPoint(id(self), qi.easting, qi.northing, self.cursorColor)
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

