"""
Module that contains the QueryDockWidget
"""

from PyQt4.QtGui import QDockWidget, QTableView, QIcon, QFileDialog
from PyQt4.QtGui import QColorDialog, QPixmap, QBrush, QMenu
from PyQt4.QtGui import QHBoxLayout, QVBoxLayout, QLineEdit, QWidget
from PyQt4.QtGui import QTabWidget, QLabel, QPen, QToolBar, QAction, QPrinter
from PyQt4.QtGui import QFontMetrics, QColor, QMessageBox, QHeaderView
from PyQt4.QtGui import QStyledItemDelegate, QStyle, QItemSelectionModel
from PyQt4.QtCore import SIGNAL, Qt, QVariant, QAbstractTableModel 
from PyQt4.QtCore import QModelIndex
import numpy

# See if we have access to Qwt
HAVE_QWT = True
try:
    from PyQt4.Qwt5 import QwtPlot, QwtPlotCurve, QwtPlotMarker, QwtText
    from PyQt4.Qwt5 import QwtScaleDiv
except ImportError:
    HAVE_QWT = False

from .viewerstretch import VIEWER_MODE_RGB, VIEWER_MODE_GREYSCALE
from .userexpressiondialog import UserExpressionDialog
from . import viewererrors

QUERYWIDGET_DEFAULT_CURSORCOLOR = Qt.white
QUERYWIDGET_DEFAULT_CURSORSIZE = 8
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
    def __init__(self, banddata, bandNames, stretch, parent):
        QAbstractTableModel.__init__(self, parent)
        self.banddata = banddata
        self.bandNames = bandNames
        self.stretch = stretch
        self.colNames = ["Band", "Name", "Value"]

    def rowCount(self, parent):
        "returns the number of rows"
        return self.banddata.shape[0]

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
            if (self.stretch.mode == VIEWER_MODE_RGB and 
                            band in self.stretch.bands):
                if band == self.stretch.bands[0]:
                    return RED_ICON
                elif band == self.stretch.bands[1]:
                    return GREEN_ICON
                elif band == self.stretch.bands[2]:
                    return BLUE_ICON
                else:
                    return QVariant()
            elif (self.stretch.mode == VIEWER_MODE_GREYSCALE 
                    and band == self.stretch.bands[0]):
                return GREY_ICON

            else:
                return QVariant()

        elif column == 1 and role == Qt.DisplayRole: 
            # band names column
            return QVariant(self.bandNames[row])

        elif column == 2 and role == Qt.DisplayRole:
            # band values column
            return QVariant("%s" % self.banddata[row])

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
            self.parent.selectionArray[idx] = (
                    not self.parent.selectionArray[idx])

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
        "Paint method - paint as selected if needed"
        if (self.parent.selectionArray is not None 
                and self.parent.selectionArray[index.row()]):
            option.state |= QStyle.State_Selected
        # shouldn't have to un-select as nothing should be selected
        # according to the model
        QStyledItemDelegate.paint(self, painter, option, index)

class ThematicHorizontalHeader(QHeaderView):
    """
    Same as a horizontal QHeaderView but responds to context
    menu requests when setThematicMode(True)
    """
    def __init__(self, parent):
        QHeaderView.__init__(self, Qt.Horizontal, parent)
        self.thematic = True
        self.parent = parent

        self.editColumnAction = QAction(self)
        self.editColumnAction.setText("&Edit Column")
        self.editColumnAction.setStatusTip("Edit selected rows in this column")
        # don't connect signal - will grab directly below so we can pass
        # on the column that was clicked
        self.popup = QMenu(self)
        self.popup.addAction(self.editColumnAction)

        self.setToolTip("Right click for menu")

    def setThematicMode(self, mode):
        "Set the mode (True or False) for context menu"
        self.thematic = mode

    def contextMenuEvent(self, event):
        "Respond to context menu event"
        if self.thematic:
            col = self.logicalIndexAt(event.pos())
            action = self.popup.exec_(event.globalPos())
            if action is self.editColumnAction:
                self.parent.editColumn(col)


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
        self.cursorSize = QUERYWIDGET_DEFAULT_CURSORSIZE
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
        # our own horizontal header that can do context menus
        self.thematicHeader = ThematicHorizontalHeader(self)
        self.tableView.setHorizontalHeader(self.thematicHeader)

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
        # add 3 pixels as some platforms (Windows, Solaris) need a few more
        # as the vertical header has a 'box' around it and font 
        # ends up squashed otherwise
        height = fm.height() + 3
        # default height actually controlled by headers
        # don't worry about QItemDelegate etc
        self.tableView.verticalHeader().setDefaultSectionSize(height)

        if HAVE_QWT:
            self.plotWidget = QwtPlot()
            self.plotWidget.setMinimumSize(100, 100)
            self.plotCurve = QwtPlotCurve()
            self.plotCurve.attach(self.plotWidget)
            self.oldPlotLabels = [] # so we can detach() them when 
                                    # we want to redisplay
        else:
            self.noQWTLabel = QLabel()
            self.noQWTLabel.setText("PyQwt needs to be installed for plot")
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
        self.connect(self.cursorColorAction, SIGNAL("triggered()"), 
                        self.changeCursorColor)

        self.increaseCursorSizeAction = QAction(self)
        self.increaseCursorSizeAction.setText("&Increase Cursor Size")
        self.increaseCursorSizeAction.setStatusTip("Increase Cursor Size")
        icon = QIcon(":/viewer/images/queryincrease.png")
        self.increaseCursorSizeAction.setIcon(icon)
        self.connect(self.increaseCursorSizeAction, SIGNAL("triggered()"), 
                        self.increaseCursorSize)

        self.decreaseCursorSizeAction = QAction(self)
        self.decreaseCursorSizeAction.setText("&Decrease Cursor Size")
        self.decreaseCursorSizeAction.setStatusTip("Decrease Cursor Size")
        icon = QIcon(":/viewer/images/querydecrease.png")
        self.decreaseCursorSizeAction.setIcon(icon)
        self.connect(self.decreaseCursorSizeAction, SIGNAL("triggered()"), 
                        self.decreaseCursorSize)

        self.labelAction = QAction(self)
        self.labelAction.setText("&Display Plot Labels")
        self.labelAction.setStatusTip("Display Plot Labels")
        self.labelAction.setIcon(QIcon(":/viewer/images/label.png"))
        self.labelAction.setCheckable(True)
        self.labelAction.setChecked(True)
        self.connect(self.labelAction, SIGNAL("toggled(bool)"), 
                        self.changeLabel)

        self.savePlotAction = QAction(self)
        self.savePlotAction.setText("&Save Plot")
        self.savePlotAction.setStatusTip("Save Plot")
        self.savePlotAction.setIcon(QIcon(":/viewer/images/saveplot.png"))
        self.connect(self.savePlotAction, SIGNAL("triggered()"), self.savePlot)

        self.highlightAction = QAction(self)
        self.highlightAction.setText("&Highlight Selection")
        self.highlightAction.setStatusTip("Highlight Selection")
        self.highlightAction.setIcon(QIcon(":/viewer/images/highlight.png"))
        self.connect(self.highlightAction, SIGNAL("triggered()"), 
                        self.highlight)

        self.highlightColorAction = QAction(self)
        self.highlightColorAction.setText("Ch&ange Highlight Color")
        self.highlightColorAction.setStatusTip("Change Highlight Color")
        icon = self.getColorIcon(self.highlightColor)
        self.highlightColorAction.setIcon(icon)
        self.connect(self.highlightColorAction, SIGNAL("triggered()"), 
                        self.changeHighlightColor)

        self.removeSelectionAction = QAction(self)
        self.removeSelectionAction.setText("&Remove Current Selection")
        self.removeSelectionAction.setStatusTip("Remove Current Selection")
        icon = QIcon(":/viewer/images/removeselection.png")
        self.removeSelectionAction.setIcon(icon)
        self.connect(self.removeSelectionAction, SIGNAL("triggered()"), 
                        self.removeSelection)

        self.selectAllAction = QAction(self)
        self.selectAllAction.setText("Se&lect All")
        self.selectAllAction.setStatusTip("Select All Rows")
        icon = QIcon(":/viewer/images/selectall.png")
        self.selectAllAction.setIcon(icon)
        self.connect(self.selectAllAction, SIGNAL("triggered()"), 
                        self.selectAll)

        self.expressionAction = QAction(self)
        self.expressionAction.setText("Select using an &Expression")
        self.expressionAction.setStatusTip("Select using an Expression")
        icon = QIcon(":/viewer/images/userexpression.png")
        self.expressionAction.setIcon(icon)
        self.connect(self.expressionAction, SIGNAL("triggered()"), 
                        self.showUserExpression)

        self.addColumnAction = QAction(self)
        self.addColumnAction.setText("Add C&olumn")
        self.addColumnAction.setStatusTip("Add Column")
        self.addColumnAction.setIcon(QIcon(":/viewer/images/addcolumn.png"))
        self.connect(self.addColumnAction, SIGNAL("triggered()"), 
                        self.addColumn)

        self.saveAttrAction = QAction(self)
        self.saveAttrAction.setText("Save Edited Columns")
        self.saveAttrAction.setStatusTip("Save Edited Columns")
        icon = QIcon(":/viewer/images/saveattributes.png")
        self.saveAttrAction.setIcon(icon)
        self.connect(self.saveAttrAction, SIGNAL("triggered()"),
                        self.saveAttributes)

    def setupToolbar(self):
        """
        Add the actions to the toolbar
        """
        self.toolBar.addAction(self.followAction)
        self.toolBar.addAction(self.cursorColorAction)
        self.toolBar.addAction(self.increaseCursorSizeAction)
        self.toolBar.addAction(self.decreaseCursorSizeAction)
        self.toolBar.addAction(self.highlightAction)
        self.toolBar.addAction(self.highlightColorAction)
        self.toolBar.addAction(self.removeSelectionAction)
        self.toolBar.addAction(self.selectAllAction)
        self.toolBar.addAction(self.expressionAction)
        self.toolBar.addAction(self.addColumnAction)
        self.toolBar.addAction(self.saveAttrAction)
        if HAVE_QWT:
            self.toolBar.addAction(self.labelAction)
            self.toolBar.addAction(self.savePlotAction)


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
                self.viewwidget.setQueryPoint(id(self), self.lastqi.easting,
                         self.lastqi.northing, newcolor, self.cursorSize)
                if HAVE_QWT and self.lastqi is not None:
                    # to get new color
                    self.updatePlot(self.lastqi, newcolor)

    def increaseCursorSize(self):
        """
        increase the cursor size
        """
        if self.lastqi is not None:
            self.cursorSize += QUERYWIDGET_DEFAULT_CURSORSIZE
            self.viewwidget.setQueryPoint(id(self), self.lastqi.easting, 
                    self.lastqi.northing, self.cursorColor, self.cursorSize)

    def decreaseCursorSize(self):
        """
        increase the cursor size
        """
        if (self.lastqi is not None and 
                self.cursorSize > QUERYWIDGET_DEFAULT_CURSORSIZE):
            self.cursorSize -= QUERYWIDGET_DEFAULT_CURSORSIZE
            self.viewwidget.setQueryPoint(id(self), self.lastqi.easting, 
                self.lastqi.northing, self.cursorColor, self.cursorSize)

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
            fname = QFileDialog.getSaveFileName(self, "Plot File", 
                        filter="PDF (*.pdf);;Postscript (*.ps)")
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
            self.viewwidget.highlightValues(self.highlightColor, 
                        self.selectionArray)
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

    def selectAll(self):
        """
        Select all the rows in the table
        """
        self.selectionArray.fill(True)
        self.updateToolTip()
        # so we repaint and our itemdelegate gets called
        self.tableView.viewport().update()

    def showUserExpression(self):
        """
        Allow user to enter expression to select rows
        """
        dlg = UserExpressionDialog(self)
        hint = """Hint: Enter an expression using column names 
(ie 'col_a < 10'). Combine more complicated expressions with '&' and '|'.
For example '(a < 10) & (b > 1)'\n
Any other numpy expressions also valid - columns are represented as 
numpy arrays.
Use the special column 'row' for the row number."""
        dlg.setHint(hint)
        self.connect(dlg, SIGNAL("newExpression(QString)"), 
                        self.newSelectUserExpression)
        dlg.show()

    def newSelectUserExpression(self, expression):
        """
        Called in reponse to signal from UserExpressionDialog
        for selection
        """
        try:
            # get the numpy array with bools
            attributes = self.lastqi.attributes
            result = attributes.evaluateUserSelectExpression(str(expression))


            # use it as our selection array
            self.selectionArray = result

            self.updateToolTip()
            # so we repaint and our itemdelegate gets called
            self.tableView.viewport().update()

        except viewererrors.UserExpressionError, e:
            QMessageBox.critical(self, "Viewer", str(e))

    def addColumn(self):
        """
        User wants to add a column
        """
        from .addcolumndialog import AddColumnDialog

        attributes = self.lastqi.attributes
        dlg = AddColumnDialog(self)
        if dlg.exec_() == AddColumnDialog.Accepted:
            dtype = dlg.getColumnType()
            colname = dlg.getColumnName()
            try:
                attributes.addColumn(colname, dtype)
            except Exception, e:
                QMessageBox.critical(self, "Viewer", str(e))

            self.updateThematicTableModel(attributes)

    def editColumn(self, col):
        """
        User has requested to edit a column
        """
        dlg = UserExpressionDialog(self, col)
        hint = """Hint: Enter an expression using column names 
(ie 'col_a * 2.1'). Or a scalar (ie '3').

Note: only selected rows are changed.

Any other numpy expressions also valid - columns are represented as 
numpy arrays.
Use the special column 'row' for the row number."""
        dlg.setHint(hint)
        self.connect(dlg, SIGNAL("newExpression(QString,int)"), 
                        self.newEditUserExpression)
        # should be modal?
        dlg.show()

    def newEditUserExpression(self, expression, col):
        """
        Called in reponse to signal from UserExpressionDialog
        for editing
        """
        try:
            # get the numpy array or scalar from user
            attributes = self.lastqi.attributes
            result = attributes.evaluateUserEditExpression(str(expression))

            # use it to update the column
            colname = attributes.getColumnNames()[col]
            attributes.updateColumn(colname, self.selectionArray, result)

            # so we repaint and new values get shown
            self.tableView.viewport().update()

        except viewererrors.UserExpressionError, e:
            QMessageBox.critical(self, "Viewer", str(e))

    def saveAttributes(self):
        """
        Get the layer to save the 'dirty' columns
        ie ones that have been added or edited.
        """
        try:

            self.lastqi.layer.writeDirtyRATColumns()

        except viewererrors.InvalidDataset, e:
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
        self.addColumnAction.setEnabled(False)
        self.thematicHeader.setThematicMode(False)

        # any new thematic data after this will have to be reloaded
        self.lastAttributeCount = -1
        self.lastAttributeid = -1

        self.tableModel = ContinuousTableModel(qi.data, qi.bandNames, 
                    qi.stretch, self)
        self.tableView.setModel(self.tableModel)

        self.selectionArray = None # no selections

        self.tableView.setToolTip("") # disable toolip

    def updateThematicTableModel(self, attributes):
        """
        Install our own table model that shows the contents of
        attributes. Call whenever data is updated.
        """
        self.tableModel = ThematicTableModel(attributes, self)
        self.tableView.setModel(self.tableModel)

        # create our own selection model so nothing gets selected
        # as far as the model is concerned
        selectionModel = ThematicSelectionModel(self.tableModel, self)
        self.tableView.setSelectionModel(selectionModel)


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
        self.addColumnAction.setEnabled(True)
        self.thematicHeader.setThematicMode(True)

        val = qi.data[0]

        # do we need a new table model?
        # do we have a new id() if the attribute obj
        # or a new count of the file opened by that object
        if (id(qi.attributes) != self.lastAttributeid or 
                qi.attributes.count != self.lastAttributeCount):
            self.lastAttributeCount = qi.attributes.count
            self.lastAttributeid = id(qi.attributes)

            self.updateThematicTableModel(qi.attributes)

            # create our selection array to record which items selected
            self.selectionArray = numpy.empty(qi.attributes.getNumRows(), 
                                    numpy.bool)
            self.selectionArray.fill(False) # none selected by default

        # set the highlight row
        self.tableModel.setHighlightRow(val)

        # scroll to the new index - remembering the existing horizontal 
        # scroll value
        horiz_scroll_bar = self.tableView.horizontalScrollBar()
        horiz_pos = horiz_scroll_bar.sliderPosition()
        index = self.tableView.model().index(val, 0)
        self.tableView.scrollTo(index, QTableView.PositionAtCenter)
        horiz_scroll_bar.setSliderPosition(horiz_pos)

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
            self.viewwidget.setQueryPoint(id(self), qi.easting, 
                        qi.northing, self.cursorColor, self.cursorSize)
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

