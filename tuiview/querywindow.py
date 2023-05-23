"""
Module that contains the QueryDockWidget
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
from PyQt5.QtGui import QPixmap, QBrush, QDoubleValidator, QIcon, QPen, QColor
from PyQt5.QtGui import QFontMetrics
from PyQt5.QtWidgets import QDockWidget, QTableView, QColorDialog, QMenu
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QLineEdit, QWidget
from PyQt5.QtWidgets import QToolBar, QAction, QMessageBox, QHeaderView
from PyQt5.QtWidgets import QStyledItemDelegate, QStyle, QTabWidget
from PyQt5.QtCore import pyqtSignal, Qt, QAbstractTableModel
from PyQt5.QtCore import QModelIndex, QItemSelectionModel
import numpy

from .viewerstretch import VIEWER_MODE_RGB, VIEWER_MODE_GREYSCALE
from .viewerstretch import VIEWER_MODE_COLORTABLE
from .viewerwidget import VIEWER_TOOL_POLYGON, VIEWER_TOOL_QUERY
from .viewerwidget import VIEWER_TOOL_POLYLINE
from .userexpressiondialog import UserExpressionDialog
from . import viewererrors
from .viewerstrings import MESSAGE_TITLE
from . import plotwidget
from .viewerRAT import GDAL_COLTYPE_LOOKUP, GDAL_COLUSAGE_LOOKUP

QUERYWIDGET_DEFAULT_CURSORCOLOR = Qt.white
QUERYWIDGET_DEFAULT_CURSORSIZE = 8
QUERYWIDGET_DEFAULT_HIGHLIGHTCOLOR = QColor(Qt.yellow)

RAT_CACHE_CHUNKSIZE = 1000

# Qt seems to have issues with tables bigger than this
MAX_ROW_COUNT = 100000000


def safeCreateColor(r, g, b, a=255):
    """
    Same as QColor constructor but ensures vales
    all between 0 and 255 to avoid annoying warnings from Qt
    """
    if r < 0:
        r = 0
    elif r > 255:
        r = 255

    if g < 0:
        g = 0
    elif g > 255:
        g = 255

    if b < 0:
        b = 0
    elif b > 255:
        b = 255

    if a < 0:
        a = 0
    elif a > 255:
        a = 255

    return QColor(r, g, b, a)


class ThematicTableModel(QAbstractTableModel):
    """
    This class is the 'model' that drives the thematic table.
    QTableView asks it for the data etc
    """
    def __init__(self, attributes, parent):
        QAbstractTableModel.__init__(self, parent)
        self.attributes = attributes
        self.saneColNames = attributes.getSaneColumnNames()
        self.colNames = attributes.getColumnNames()
        # for reading the data
        self.attCache = attributes.getCacheObject(RAT_CACHE_CHUNKSIZE) 
        self.highlightBrush = QBrush(QUERYWIDGET_DEFAULT_HIGHLIGHTCOLOR)
        self.highlightRow = -1
        self.lookupColIcon = QIcon(":/viewer/images/arrowup.png")

    def doUpdate(self, updateHorizHeader=False):
        """
        Called by the parent window when the attributes have changed.
        Emits the appropriate signal.
        """
        topLeft = self.index(0, 0)
        bottomRight = self.index(self.columnCount(None) - 1,
                            self.rowCount(None) - 1)
        self.dataChanged.emit(topLeft, bottomRight)

        # cache will be out of date
        self.attCache = self.attributes.getCacheObject(RAT_CACHE_CHUNKSIZE) 

        if updateHorizHeader:
            self.saneColNames = self.attributes.getSaneColumnNames()
            self.colNames = self.attributes.getColumnNames()
            self.headerDataChanged.emit(Qt.Horizontal, 0, 
                        self.columnCount(None) - 1)

    def setHighlightRow(self, row):
        """
        Called by setupTableThematic to indicate 
        the row that should be highlighted
        """
        if row >= MAX_ROW_COUNT:
            print('Selected row is', row)
            row = MAX_ROW_COUNT - 1
        self.highlightRow = row
        self.headerDataChanged.emit(Qt.Vertical, 0, self.rowCount(None) - 1)

    def rowCount(self, parent):
        "returns the number of rows"
        return min(self.attributes.getNumRows(), MAX_ROW_COUNT)

    def columnCount(self, parent):
        "number of columns"
        ncols = self.attributes.getNumColumns()
        if self.attributes.hasColorTable:
            ncols += 1
        return ncols

    def headerData(self, section, orientation, role):
        """
        returns the header labels for either vertical or
        horizontal
        """
        if orientation == Qt.Horizontal:
            if self.attributes.hasColorTable:
                if role == Qt.DisplayRole and section == 0:
                    return "Color"
                section -= 1  # for below, to ignore the color col

            if role == Qt.DisplayRole:
                name = self.saneColNames[section]
                return name
            elif role == Qt.DecorationRole:
                if section == -1:
                    # color column
                    return None
                name = self.colNames[section]
                if name == self.attributes.getLookupColName():
                    return self.lookupColIcon
                else:
                    return None
            elif role == Qt.ToolTipRole:
                tooltip = ""
                if section != -1:
                    # not the color col, should be some info for it
                    name = self.colNames[section]
                    dtype = self.attributes.getType(name)
                    if dtype in GDAL_COLTYPE_LOOKUP:
                        dtypeStr = GDAL_COLTYPE_LOOKUP[dtype]
                    else:
                        dtypeStr = "Unknown"
                        
                    usage = self.attributes.getUsage(name)
                    if usage in GDAL_COLUSAGE_LOOKUP:
                        usageStr = GDAL_COLUSAGE_LOOKUP[usage]
                    else:
                        usageStr = "Unknown"
                        
                    tooltip = "Type : %s\nUsage : %s\n\n" % (dtypeStr, usageStr)
                
                # always add this right click text even if color menu
                tooltip = tooltip + "Right click for menu"
                return tooltip
            else:
                return None
                
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            # rows just a number
            return "%s" % section
        elif (orientation == Qt.Vertical and role == Qt.BackgroundRole and
                section == self.highlightRow):
            # highlight the header also
            return self.highlightBrush
        else:
            return None

    def createColorIcon(self, row):
        """
        Returns the colour icon for the given row
        """
        self.attCache.autoScrollToIncludeRow(row)

        names = self.attributes.getColumnNames()
        name = names[self.attributes.redColumnIdx]
        redVal = self.attCache.getValueFromCol(name, row)

        name = names[self.attributes.greenColumnIdx]
        greenVal = self.attCache.getValueFromCol(name, row)

        name = names[self.attributes.blueColumnIdx]
        blueVal = self.attCache.getValueFromCol(name, row)

        # ignore alpha as we want to see it
        col = safeCreateColor(redVal, greenVal, blueVal)

        pixmap = QPixmap(64, 24)
        pixmap.fill(col)
        return pixmap

    def data(self, index, role):
        """
        Gets the actual data. A variety of Qt.ItemDataRole's
        are passed, but we only use DisplayRole for the text
        and Qt.BackgroundRole for the highlight role
        """
        if not index.isValid():
            return None

        row = index.row()
        if role == Qt.BackgroundRole and row == self.highlightRow:
            return self.highlightBrush

        if role == Qt.DisplayRole: 
            column = index.column()
            if self.attributes.hasColorTable:
                if column == 0:
                    return None  # no text
                column -= 1  # for below to ignore the color col

            name = self.attributes.getColumnNames()[column]
            # scroll to row
            self.attCache.autoScrollToIncludeRow(row)
            attr_val = self.attCache.getValueFromCol(name, row)

            if isinstance(attr_val, bytes):
                # other wise we get b'...' in Python3 
                attr_val = attr_val.decode()
            fmt = self.attributes.getFormat(name)
            return fmt % attr_val

        elif role == Qt.DecorationRole:
            column = index.column()
            if self.attributes.hasColorTable and column == 0:
                return self.createColorIcon(row)
            else:
                return None

        else:
            return None


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

        # pixmaps for displaying in the 'band' column for RGB
        self.redPixmap = QPixmap(64, 24)
        self.redPixmap.fill(Qt.red)

        self.greenPixmap = QPixmap(64, 24)
        self.greenPixmap.fill(Qt.green)

        self.bluePixmap = QPixmap(64, 24)
        self.bluePixmap.fill(Qt.blue)

        # for greyscale
        self.greyPixmap = QPixmap(64, 24)
        self.greyPixmap.fill(Qt.gray)

    def doUpdate(self, updateHorizHeader=False):
        """
        Called by the parent window when the data has changed.
        Emits the appropriate signal.
        """
        topLeft = self.index(0, 0)
        bottomRight = self.index(self.columnCount(None) - 1, 
                        self.rowCount(None) - 1)
        self.dataChanged.emit(topLeft, bottomRight)

        if updateHorizHeader:
            self.headerDataChanged.emit(Qt.Horizontal, 0, 
                        self.rowCount(None) - 1)

    def rowCount(self, parent):
        "returns the number of rows"
        return len(self.bandNames)

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
            return name
        elif orientation == Qt.Vertical and role == Qt.DisplayRole:
            # rows just a number
            return "%s" % (section + 1)
        else:
            return None

    def data(self, index, role):
        """
        Gets the actual data. A variety of Qt.ItemDataRole's
        are passed, but we only use DisplayRole for the text
        and Qt.BackgroundRole for the highlight role
        """
        if not index.isValid():
            return None

        column = index.column()
        row = index.row()
        if column == 0 and role == Qt.DecorationRole:
            # icon column
            band = row + 1
            if (self.stretch.mode == VIEWER_MODE_RGB and 
                    band in self.stretch.bands):
                if band == self.stretch.bands[0]:
                    return self.redPixmap
                elif band == self.stretch.bands[1]:
                    return self.greenPixmap
                elif band == self.stretch.bands[2]:
                    return self.bluePixmap
                else:
                    return None
            elif (self.stretch.mode == VIEWER_MODE_GREYSCALE and
                    band == self.stretch.bands[0]):
                return self.greyPixmap

            else:
                return None

        elif column == 1 and role == Qt.DisplayRole: 
            # band names column
            return self.bandNames[row]

        elif (column == 2 and role == Qt.DisplayRole and 
                self.banddata is not None):
            # band values column
            return "%s" % self.banddata[row]

        else:
            return None


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
                
        self.parent.storeLastSelection()

        # if we are to clear first, do so
        if (command & QItemSelectionModel.Clear) == QItemSelectionModel.Clear:
            self.parent.selectionArray.fill(False)

        # toggle all the indexes
        for idx in unique_rows:
            self.parent.selectionArray[idx] = (
                not self.parent.selectionArray[idx])

        self.parent.updateToolTip()

        if self.parent.highlightAction.isChecked():
            self.parent.viewwidget.highlightValues(self.parent.highlightColor,
                                self.parent.selectionArray)

        # update the view
        self.parent.tableModel.doUpdate(True)
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
        if (self.parent.selectionArray is not None and
                self.parent.selectionArray[index.row()]):
            option.state |= QStyle.State_Selected
        # shouldn't have to un-select as nothing should be selected
        # according to the model
        QStyledItemDelegate.paint(self, painter, option, index)


MOVE_LEFT = 0
MOVE_RIGHT = 1
MOVE_LEFTMOST = 2
MOVE_RIGHTMOST = 3


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
        self.editColumnAction.setText("&Edit Selected Rows in Column")
        self.editColumnAction.setStatusTip("Edit selected rows in this column")

        self.moveLeftAction = QAction(self)
        self.moveLeftAction.setText("Move &Left")
        self.moveLeftAction.setStatusTip("Move column one left")

        self.moveRightAction = QAction(self)
        self.moveRightAction.setText("Move &Right")
        self.moveRightAction.setStatusTip("Move column one right")
        
        self.moveLeftMostAction = QAction(self)
        self.moveLeftMostAction.setText("&Move Left Most")
        self.moveLeftMostAction.setStatusTip("Move to left most position")

        self.moveRightMostAction = QAction(self)
        self.moveRightMostAction.setText("Move &Right Most")
        self.moveRightMostAction.setStatusTip("Move to right most position")

        self.setDPAction = QAction(self)
        self.setDPAction.setText("&Set number of decimal places")
        self.setDPAction.setStatusTip("Set number of decimal places")

        self.setLookupAction = QAction(self)
        self.setLookupAction.setText("Set column as Color Table L&ookup")
        self.setLookupAction.setStatusTip("Set column as Color Table Lookup")
        self.setLookupAction.setCheckable(True)
        
        self.setKeyboardEditAction = QAction(self)
        self.setKeyboardEditAction.setText(
            "Set column to receive &keyboard edits")
        self.setKeyboardEditAction.setStatusTip(
            "Set column to receive keyboard edits")
        self.setKeyboardEditAction.setCheckable(True)
        
        # don't connect signal - will grab directly below so we can pass
        # on the column that was clicked
        self.popup = QMenu(self)
        self.popup.addAction(self.editColumnAction)
        self.popup.addAction(self.moveLeftAction)
        self.popup.addAction(self.moveRightAction)
        self.popup.addAction(self.moveLeftMostAction)
        self.popup.addAction(self.moveRightMostAction)
        self.popup.addAction(self.setDPAction)  # enabled when float col
        self.popup.addAction(self.setLookupAction)  # enabled when int or float col
        self.popup.addAction(self.setKeyboardEditAction)

        self.setColorAction = QAction(self)
        self.setColorAction.setText("Set &Color of Selected Rows")
        self.setColorAction.setStatusTip("Set Color of Selected Rows")

        # alternate popup for color column
        self.colorPopup = QMenu(self)
        self.colorPopup.addAction(self.setColorAction)

        # Tooltip handled by ThematicTableModel.headerData

    def setThematicMode(self, mode):
        "Set the mode (True or False) for context menu"
        self.thematic = mode

    def contextMenuEvent(self, event):
        "Respond to context menu event"
        if self.thematic:
            from osgeo.gdal import GFT_Real, GFT_String
            col = self.logicalIndexAt(event.pos())
            attributes = self.parent.lastLayer.attributes

            if attributes.hasColorTable:
                if col == 0:
                    # do special handling for color column
                    action = self.colorPopup.exec_(event.globalPos())
                    if action is self.setColorAction:
                        self.parent.editColor()
                    return
                col -= 1  # to ignore color col for below

            # work out whether this is float column
            colName = attributes.getColumnNames()[col]
            colType = attributes.getType(colName)
            self.setDPAction.setEnabled(colType == GFT_Real)
            self.setLookupAction.setEnabled(colType != GFT_String)
            self.setLookupAction.setChecked(colName == attributes.lookupColName)
            colGotKeyboard = self.parent.keyboardEditColumn == colName
            self.setKeyboardEditAction.setChecked(colGotKeyboard)

            action = self.popup.exec_(event.globalPos())
            if action is self.editColumnAction:
                self.parent.editColumn(col)
            elif action is self.moveLeftAction:
                self.parent.moveColumn(col, MOVE_LEFT)
            elif action is self.moveRightAction:
                self.parent.moveColumn(col, MOVE_RIGHT)
            elif action is self.moveLeftMostAction:
                self.parent.moveColumn(col, MOVE_LEFTMOST)
            elif action is self.moveRightMostAction:
                self.parent.moveColumn(col, MOVE_RIGHTMOST)
            elif action is self.setDPAction:
                self.parent.setColumnDecimalPlaces(colName)
            elif action is self.setLookupAction:
                self.parent.setColumnAsLookup(colName)
            elif action is self.setKeyboardEditAction:
                self.parent.setColumnKeyboardEdit(colName)


class QueryTableView(QTableView):
    """
    A hack to ensure all keypresses are redirected to
    the parent window for processing by the keyboard input
    handler rather than the default which tries to do some
    searching thing.
    """
    def __init__(self, parent):
        QTableView.__init__(self, parent)
        self.parent = parent

    def keyPressEvent(self, event):
        self.parent.keyPressEvent(event)
        

class QueryDockWidget(QDockWidget):
    """
    Dock widget that contains the query window. Follows query 
    tool clicks (can be disabled) and can change query point color.
    Image values for point are displayed thanks to locationSelected
    signal from ViewerWidget. 
    """
    # signals
    queryClosed = pyqtSignal(QDockWidget, name='queryClosed')

    def __init__(self, parent, viewwidget):
        QDockWidget.__init__(self, "Query", parent)
        
        # make sure we can get keyboard focus
        self.setFocusPolicy(Qt.StrongFocus)
        
        self.viewwidget = viewwidget
        self.cursorColor = QUERYWIDGET_DEFAULT_CURSORCOLOR
        self.cursorSize = QUERYWIDGET_DEFAULT_CURSORSIZE
        self.highlightColor = QUERYWIDGET_DEFAULT_HIGHLIGHTCOLOR
        self.displayPixelCoords = False  # display pixel or map coordinates.

        # connect to the collected polygon signal - only respond when
        # self.geogSelectAction.isChecked() so don't interfere with
        # other GUI elements that might as for a polygon
        self.viewwidget.polygonCollected.connect(self.newPolyGeogSelect)
        # same for polyline
        self.viewwidget.polylineCollected.connect(self.newLineGeogSelect)

        # connect to the signal we get when tool changed. We can update
        # GUI if main window has selected tool etc
        self.viewwidget.activeToolChanged.connect(self.activeToolChanged)
        
        # connect if the layers have changed and we can close if our layer
        # no longer exists
        self.viewwidget.layers.layersChanged.connect(self.layersChanged)

        # create a new widget that lives in the dock window
        self.dockWidget = QWidget()

        self.toolBar = QToolBar(self.dockWidget)

        self.coordValidator = QDoubleValidator()
        self.eastingEdit = QLineEdit(self.dockWidget)
        self.eastingEdit.setToolTip("Easting")
        self.eastingEdit.setValidator(self.coordValidator)
        self.eastingEdit.returnPressed.connect(self.userNewCoord)

        self.northingEdit = QLineEdit(self.dockWidget)
        self.northingEdit.setToolTip("Northing")
        self.northingEdit.setValidator(self.coordValidator)
        self.northingEdit.returnPressed.connect(self.userNewCoord)

        self.coordLayout = QHBoxLayout()
        self.coordLayout.addWidget(self.eastingEdit)
        self.coordLayout.addWidget(self.northingEdit)

        self.tabWidget = QTabWidget(self.dockWidget)

        self.tableView = QueryTableView(self)
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
        # backup of last selectionArray
        self.lastSelectionArray = None

        # the id() of the last ViewerRAT class so we can 
        # update display only when needed
        self.lastAttributeid = -1
        # the 'count' of files opened by that object
        # so we can tell if the same object has opened another file
        self.lastAttributeCount = -1

        # the reference to the last layer object
        self.lastLayer = None
        
        # column being edited via keyboard
        self.keyboardEditColumn = None
        # text entered via keypad since last return
        self.keyboardData = None

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

        self.plotWidget = plotwidget.PlotLineWidget(self)

        self.tabWidget.addTab(self.tableView, "Table")
        self.tabWidget.addTab(self.plotWidget, "Plot")

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

        # allow plot scaling to be changed by user
        # Min, Max. None means 'auto'.
        self.plotScaling = (None, None)
        
        # so if we are turning on a tool because another tool 
        # in another window has been turned on, we don't undo 
        # that tool being enabled. As oppossed to user unclicking
        # the tool
        self.suppressToolReset = False

        # do these last - some slots are called than need the above
        # variables.
        self.setupActions()
        self.setupToolbar()

        layer = viewwidget.layers.getTopRasterLayer()
        if layer is not None:
            if (len(layer.stretch.bands) == 1 and 
                    layer.attributes.hasAttributes()):
                self.setupTableThematic(None, layer)
            else:
                self.setupTableContinuous(None, layer)

        # now update UI to show unlock state is false
        self.setUIUpdateState(False)

    def storeLastSelection(self):
        "Take a copy of self.selectionArray and store it"
        if self.selectionArray is not None:
            self.lastSelectionArray = self.selectionArray.copy()

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
        self.toolActions = []

        self.followAction = QAction(self)
        self.followAction.setText("&Follow Query Tool")
        self.followAction.setStatusTip("Follow Query Tool")
        self.followAction.setIcon(QIcon(":/viewer/images/query.png"))
        self.followAction.setCheckable(True)
        self.followAction.setChecked(True)

        self.cursorColorAction = QAction(self, triggered=self.changeCursorColor)
        self.cursorColorAction.setText("&Change Cursor Color")
        self.cursorColorAction.setStatusTip("Change Cursor Color")
        icon = self.getColorIcon(self.cursorColor)
        self.cursorColorAction.setIcon(icon)        

        self.increaseCursorSizeAction = QAction(self, 
                        triggered=self.increaseCursorSize)
        self.increaseCursorSizeAction.setText("&Increase Cursor Size")
        self.increaseCursorSizeAction.setStatusTip("Increase Cursor Size")
        icon = QIcon(":/viewer/images/queryincrease.png")
        self.increaseCursorSizeAction.setIcon(icon)

        self.decreaseCursorSizeAction = QAction(self, 
                        triggered=self.decreaseCursorSize)
        self.decreaseCursorSizeAction.setText("&Decrease Cursor Size")
        self.decreaseCursorSizeAction.setStatusTip("Decrease Cursor Size")
        icon = QIcon(":/viewer/images/querydecrease.png")
        self.decreaseCursorSizeAction.setIcon(icon)

        self.labelAction = QAction(self, toggled=self.changeLabel)
        self.labelAction.setText("&Display Plot Labels")
        self.labelAction.setStatusTip("Display Plot Labels")
        self.labelAction.setIcon(QIcon(":/viewer/images/label.png"))
        self.labelAction.setCheckable(True)
        self.labelAction.setChecked(True)

        self.savePlotAction = QAction(self, triggered=self.savePlot)
        self.savePlotAction.setText("&Save Plot")
        self.savePlotAction.setStatusTip("Save Plot")
        self.savePlotAction.setIcon(QIcon(":/viewer/images/saveplot.png"))

        self.highlightAction = QAction(self, toggled=self.highlight)
        self.highlightAction.setText("&Highlight Selection (CTRL+H)")
        self.highlightAction.setStatusTip("Highlight Selection")
        self.highlightAction.setIcon(QIcon(":/viewer/images/highlight.png"))
        self.highlightAction.setCheckable(True)
        self.highlightAction.setChecked(True)
        self.highlightAction.setShortcut("CTRL+H")

        self.highlightColorAction = QAction(self, 
            triggered=self.changeHighlightColor)
        self.highlightColorAction.setText("Ch&ange Highlight Color")
        self.highlightColorAction.setStatusTip("Change Highlight Color")
        icon = self.getColorIcon(self.highlightColor)
        self.highlightColorAction.setIcon(icon)

        self.removeSelectionAction = QAction(self, 
            triggered=self.removeSelection)
        self.removeSelectionAction.setText("&Remove Current Selection")
        self.removeSelectionAction.setStatusTip("Remove Current Selection")
        icon = QIcon(":/viewer/images/removeselection.png")
        self.removeSelectionAction.setIcon(icon)

        self.selectAllAction = QAction(self, triggered=self.selectAll)
        self.selectAllAction.setText("Se&lect All")
        self.selectAllAction.setStatusTip("Select All Rows")
        icon = QIcon(":/viewer/images/selectall.png")
        self.selectAllAction.setIcon(icon)

        self.expressionAction = QAction(self, triggered=self.showUserExpression)
        self.expressionAction.setText("Select using an &Expression")
        self.expressionAction.setStatusTip("Select using an Expression")
        icon = QIcon(":/viewer/images/userexpression.png")
        self.expressionAction.setIcon(icon)

        self.unlockDatasetAction = QAction(self, toggled=self.unlockDataset)
        self.unlockDatasetAction.setText("Toggle &updates to dataset")
        self.unlockDatasetAction.setStatusTip(
            "Toggle whether updates are allowed to dataset")
        icon = QIcon(":/viewer/images/lock.png")
        self.unlockDatasetAction.setIcon(icon)
        self.unlockDatasetAction.setCheckable(True)

        self.addColumnAction = QAction(self, triggered=self.addColumn)
        self.addColumnAction.setText("Add C&olumn")
        self.addColumnAction.setStatusTip("Add Column")
        self.addColumnAction.setIcon(QIcon(":/viewer/images/addcolumn.png"))

        self.saveColOrderAction = QAction(self, triggered=self.saveColOrder)
        self.saveColOrderAction.setText("Sa&ve Column Order")
        self.saveColOrderAction.setStatusTip("Save Column Order to file")
        icon = QIcon(":/viewer/images/savecolumnorder.png")
        self.saveColOrderAction.setIcon(icon)

        self.geogSelectAction = QAction(self, toggled=self.geogSelect)
        self.geogSelectAction.setText(
            "&Geographic Selection by Polygon (ALT+G)")
        self.geogSelectAction.setStatusTip(
            "Select rows by geographic selection")
        icon = QIcon(":/viewer/images/geographicselect.png")
        self.geogSelectAction.setIcon(icon)
        self.geogSelectAction.setCheckable(True)
        self.geogSelectAction.setShortcut("ALT+G")
        self.toolActions.append(self.geogSelectAction)

        self.geogSelectLineAction = QAction(self, 
                    toggled=self.geogLineSelect)
        self.geogSelectLineAction.setText(
            "Geographic Selection by &Line (ALT+L)")
        self.geogSelectLineAction.setStatusTip(
            "Select rows by geographic selection with Line")
        icon = QIcon(":/viewer/images/geographiclineselect.png")
        self.geogSelectLineAction.setIcon(icon)
        self.geogSelectLineAction.setCheckable(True)
        self.geogSelectLineAction.setShortcut("ALT+L")
        self.toolActions.append(self.geogSelectLineAction)

        self.geogSelectPointAction = QAction(self, toggled=self.geogPointSelect)
        self.geogSelectPointAction.setText(
            "Geographic Selection by &Point (ALT+P)")
        self.geogSelectPointAction.setStatusTip(
            "Select rows by geographic selection with Point")
        icon = QIcon(":/viewer/images/geographicpointselect.png")
        self.geogSelectPointAction.setIcon(icon)
        self.geogSelectPointAction.setCheckable(True)
        self.geogSelectPointAction.setShortcut("ALT+P")
        self.toolActions.append(self.geogSelectPointAction)

        self.plotScalingAction = QAction(self, triggered=self.onPlotScaling)
        self.plotScalingAction.setText("Set Plot Scaling")
        self.plotScalingAction.setStatusTip("Set Plot Scaling")
        icon = QIcon(":/viewer/images/setplotscale.png")
        self.plotScalingAction.setIcon(icon)
                        
        self.toggleCoordsAction = QAction(self, toggled=self.toggleCoordsSelect)
        self.toggleCoordsAction.setText("Switch between map and pi&xel coordinates")
        self.toggleCoordsAction.setStatusTip(
            "Switch display between map and pixel coordinates")
        icon = QIcon(":/viewer/images/toggle.png")
        self.toggleCoordsAction.setIcon(icon)
        self.toggleCoordsAction.setCheckable(True)

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
        self.toolBar.addAction(self.unlockDatasetAction)
        self.toolBar.addAction(self.addColumnAction)
        self.toolBar.addAction(self.saveColOrderAction)
        self.toolBar.addAction(self.geogSelectAction)
        self.toolBar.addAction(self.geogSelectLineAction)
        self.toolBar.addAction(self.geogSelectPointAction)
        self.toolBar.addAction(self.toggleCoordsAction)
        self.toolBar.addAction(self.labelAction)
        self.toolBar.addAction(self.savePlotAction)
        self.toolBar.addAction(self.plotScalingAction)

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
                if self.lastqi is not None:
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
            if self.highlightAction.isChecked():
                self.highlight(True)

    def changeLabel(self, checked):
        """
        State of display labels check has been changed. Redisplay plot.
        """
        if self.lastqi is not None:
            self.updatePlot(self.lastqi, self.cursorColor)

    def savePlot(self):
        """
        Save the plot as a file. Either .pdf or .ps QPrinter
        chooses format based on extension.
        """
        from PyQt5.QtGui import QPainter
        from PyQt5.QtPrintSupport import QPrinter
        from PyQt5.QtWidgets import QFileDialog
        fname, filter = QFileDialog.getSaveFileName(self, "Plot File", 
                    filter="PDF (*.pdf);;Postscript (*.ps)")
        if fname != '':
            printer = QPrinter()
            printer.setOrientation(QPrinter.Landscape)
            printer.setColorMode(QPrinter.Color)
            printer.setOutputFileName(fname)
            printer.setResolution(96)
            painter = QPainter()
            painter.begin(printer)
            self.plotWidget.render(painter)
            painter.end()

    def onPlotScaling(self):
        """
        Allows the user to change the Y axis scaling of the plot
        """
        from .plotscalingdialog import PlotScalingDialog
        if self.lastqi is not None:
            data = self.lastqi.data
        else:
            # uint8 default if no data 
            data = numpy.array([0, 1], dtype=numpy.uint8) 

        dlg = PlotScalingDialog(self, self.plotScaling, data)

        if dlg.exec_() == PlotScalingDialog.Accepted:
            self.plotScaling = dlg.getScale()
            if self.lastqi is not None:
                self.updatePlot(self.lastqi, self.cursorColor)

    def highlight(self, state):
        """
        Highlight the currently selected rows on the map
        state contains whether we are enabling this or not
        """
        # tell the widget to update
        try:
            if state:
                self.viewwidget.highlightValues(self.highlightColor, 
                        self.selectionArray)
            else:
                self.viewwidget.highlightValues(self.highlightColor, None)
        except viewererrors.InvalidDataset:
            pass

    def removeSelection(self):
        """
        Remove the current selection from the table widget
        """
        self.storeLastSelection()
        self.selectionArray.fill(False)
        self.updateToolTip()
        
        if self.highlightAction.isChecked():
            self.viewwidget.highlightValues(self.highlightColor,
                                self.selectionArray)
        
        # so we repaint and our itemdelegate gets called
        self.tableModel.doUpdate()

    def selectAll(self):
        """
        Select all the rows in the table
        """
        self.storeLastSelection()
        self.selectionArray.fill(True)
        self.updateToolTip()

        if self.highlightAction.isChecked():
            self.viewwidget.highlightValues(self.highlightColor,
                                self.selectionArray)

        # so we repaint and our itemdelegate gets called
        self.tableModel.doUpdate()

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
Use the special columns:
'row' for the row number and 
'isselected' for the currently selected rows
'queryrow' is the currently queried row and
'lastselected' is the previous selected rows"""
        dlg.setHint(hint)
        dlg.newExpression['QString'].connect(self.newSelectUserExpression)
        dlg.show()

    def unlockDataset(self, state):
        """
        User wants to lock or unlock dataset
        """
        try:
            self.lastLayer.changeUpdateAccess(state)
            self.tableModel.doUpdate(True)
            self.setUIUpdateState(state)
        except IOError:
            msg = """TuiView was unable to re-open the dataset
The file no longer exists or is inaccessible.
The application will now exit."""
            # unfortunaltely we cannot display the messagebox
            # since Qt will still want to redraw the RAT 
            # which we don't have access to. So just exit
            raise SystemExit(msg)
        except Exception as e:
            QMessageBox.critical(self, MESSAGE_TITLE, str(e))
            state = self.lastLayer.updateAccess
            self.unlockDatasetAction.setChecked(state)
            self.setUIUpdateState(state)

    def setUIUpdateState(self, state):
        """
        Update the bits of the UI that change when the 
        update state changes.
        """
        self.addColumnAction.setEnabled(state)
        self.saveColOrderAction.setEnabled(state)
        self.thematicHeader.editColumnAction.setEnabled(state)
        self.thematicHeader.setKeyboardEditAction.setEnabled(state)
        self.thematicHeader.setColorAction.setEnabled(state)

    def scrollToFirstSelected(self):
        "scroll to the first selected row"
        # find the first selected index and scroll to it
        selectedIdx = self.selectionArray.nonzero()[0]  # first axis
        if selectedIdx.size != 0:
            # scroll to the new index - remembering the existing horizontal 
            # scroll value
            horiz_scroll_bar = self.tableView.horizontalScrollBar()
            horiz_pos = horiz_scroll_bar.sliderPosition()
            index = self.tableView.model().index(selectedIdx[0], 0)
            self.tableView.scrollTo(index, QTableView.PositionAtCenter)
            horiz_scroll_bar.setSliderPosition(horiz_pos)

    def userNewCoord(self):
        """
        User has pressed enter on one of the coord boxes
        Tell widget we want to move
        """
        # should have been validated by the time we got here so 
        # should be valid floats
        if self.displayPixelCoords:
            column = float(self.eastingEdit.text())
            row = float(self.northingEdit.text())
            self.viewwidget.newQueryPoint(column=column, row=row)
        else:
            easting = float(self.eastingEdit.text())
            northing = float(self.northingEdit.text())
            self.viewwidget.newQueryPoint(easting=easting, northing=northing)

    def newSelectUserExpression(self, expression):
        """
        Called in reponse to signal from UserExpressionDialog
        for selection
        """
        try:

            # get the numpy array with bools
            attributes = self.lastLayer.attributes
            queryRow = self.tableModel.highlightRow
            result = attributes.evaluateUserSelectExpression(str(expression),
                                                self.selectionArray, queryRow,
                                                self.lastSelectionArray)

            self.storeLastSelection()

            # use it as our selection array
            self.selectionArray = result
            
            # if we are following the hightlight then update that
            if self.highlightAction.isChecked():
                self.viewwidget.highlightValues(self.highlightColor,
                                self.selectionArray)

            self.scrollToFirstSelected()

            self.updateToolTip()
            # so we repaint and our itemdelegate gets called
            self.tableModel.doUpdate()

        except viewererrors.UserExpressionError as e:
            QMessageBox.critical(self, MESSAGE_TITLE, str(e))

    def addColumn(self):
        """
        User wants to add a column
        """
        from .addcolumndialog import AddColumnDialog

        attributes = self.lastLayer.attributes
        dlg = AddColumnDialog(self)
        if dlg.exec_() == AddColumnDialog.Accepted:
            dtype = dlg.getColumnType()
            colname = dlg.getColumnName()
            try:
                attributes.addColumn(colname, dtype)
            except Exception as e:
                QMessageBox.critical(self, MESSAGE_TITLE, str(e))

            self.tableModel.doUpdate(True)

    def editColumn(self, col):
        """
        User has requested to edit a column
        """
        dlg = UserExpressionDialog(self, col=col)
        hint = """Hint: Enter an expression using column names 
(ie 'col_a * 2.1'). Or a scalar (ie '3').

Note: only selected rows are changed.

Any other numpy expressions also valid - columns are represented as 
numpy arrays.
Use the special columns:
'row' for the row number and 
'isselected' for the currently selected rows and
'queryrow' is the currently queried row"""
        dlg.setHint(hint)
        dlg.newExpression['QString', int].connect(self.newEditUserExpression)

        # should be modal?
        dlg.show()

    def editColor(self):
        """
        Change the colour of the selected rows
        """
        if not self.selectionArray.any():
            # if nothing selected, don't even bother
            QMessageBox.warning(self, MESSAGE_TITLE, "No rows selected")
            return

        # get the colour of the first selected one
        selectedIdx = self.selectionArray.nonzero()[0][0]  # first axis first elem
        attributes = self.lastLayer.attributes

        # instantiate our own cache since the first selected might not
        # even be in the model's cache
        # chunksize of one since we will just be reading one row
        cache = attributes.getCacheObject(1)
        cache.setStartRow(selectedIdx)

        names = attributes.getColumnNames()
        redname = names[attributes.redColumnIdx]
        redVal = cache.getValueFromCol(redname, selectedIdx)

        greenname = names[attributes.greenColumnIdx]
        greenVal = cache.getValueFromCol(greenname, selectedIdx)

        bluename = names[attributes.blueColumnIdx]
        blueVal = cache.getValueFromCol(bluename, selectedIdx)

        alphaname = names[attributes.alphaColumnIdx]
        alphaVal = cache.getValueFromCol(alphaname, selectedIdx)

        initial = safeCreateColor(redVal, greenVal, blueVal, alphaVal)
        newcolor = QColorDialog.getColor(initial, self, 
                    "Choose Cursor Color", QColorDialog.ShowAlphaChannel)
        if newcolor.isValid():
            red = newcolor.red()
            attributes.setColumnToConstant(redname, red, self.selectionArray)

            green = newcolor.green()
            attributes.setColumnToConstant(redname, green, self.selectionArray)

            blue = newcolor.blue()
            attributes.setColumnToConstant(redname, blue, self.selectionArray)

            alpha = newcolor.alpha()
            attributes.setColumnToConstant(redname, alpha, self.selectionArray)

            # so we repaint and new values get shown
            self.tableModel.doUpdate()

            self.updateColorTableInWidget()

    def updateColorTableInWidget(self):
        """
        Call this when the color table changed and the LUT
        will be reloaded and redisplayed
        """
        # also need to update the widget
        stretch = self.lastLayer.stretch
        if stretch.mode == VIEWER_MODE_COLORTABLE:
            # causes lut to be updated
            self.viewwidget.setNewStretch(stretch, self.lastLayer)

    def newEditUserExpression(self, expression, col):
        """
        Called in reponse to signal from UserExpressionDialog
        for editing
        """
        if not self.selectionArray.any():
            # if nothing selected, don't even bother
            return

        try:
            # get the rat object to do the work using the cache
            attributes = self.lastLayer.attributes
            queryRow = self.tableModel.highlightRow
            colname = attributes.getColumnNames()[col]
            attributes.evaluateUserEditExpression(colname, 
                    str(expression), self.selectionArray, queryRow)

            # so we repaint and new values get shown
            self.tableModel.doUpdate()

            # was a color table column?
            if (col == attributes.redColumnIdx or 
                    col == attributes.greenColumnIdx or
                    col == attributes.blueColumnIdx or
                    col == attributes.alphaColumnIdx):
                self.updateColorTableInWidget()

            # is this a the lookup column?
            if colname == attributes.getLookupColName():
                # can't just use result because we need selectionArray applied
                col = attributes.getEntireAttribute(colname)
                self.viewwidget.setColorTableLookup(col, colname)

        except viewererrors.UserExpressionError as e:
            QMessageBox.critical(self, MESSAGE_TITLE, str(e))

    def moveColumn(self, col, code):
        """
        Move column left or right in the display
        based on code.
        """
        attributes = self.lastLayer.attributes
        columnNames = attributes.getColumnNames()
        # remove the one we are interested in 
        colName = columnNames.pop(col)

        if code == MOVE_LEFT and col > 0:
            col -= 1
        elif code == MOVE_RIGHT and col < len(columnNames):
            col += 1
        elif code == MOVE_LEFTMOST:
            col = 0
        elif code == MOVE_RIGHTMOST:
            col = len(columnNames)
                
        columnNames.insert(col, colName)
    
        # this should update the color table idxs    
        attributes.findColorTableColumns()

        self.tableModel.doUpdate(True)

    def setColumnDecimalPlaces(self, colName):
        """
        Allows the user to set the number of decimal places for
        float columns
        """
        from PyQt5.QtWidgets import QInputDialog
        attributes = self.lastLayer.attributes
        currFormat = attributes.getFormat(colName)
        currDP = int(currFormat[2:-1])  # dodgy but should be ok
        (newDP, ok) = QInputDialog.getInt(self, MESSAGE_TITLE,
            "Number of Decimal Places", currDP, 0, 100)
        if ok:
            newFormat = "%%.%df" % newDP
            attributes.setFormat(colName, newFormat)
            self.tableModel.doUpdate()

    def setColumnAsLookup(self, colName):
        """
        Allows the user to specify a column to be used
        to lookup the color table
        """
        from .viewerLUT import ViewerLUT
        attributes = self.lastLayer.attributes
        if colName == attributes.getLookupColName():
            # toggle off
            attributes.setLookupColName(None)
            self.viewwidget.setColorTableLookup()
        else:
            col = attributes.getEntireAttribute(colName)

            gdaldataset = self.lastLayer.gdalDataset
            tables = ViewerLUT.readSurrogateColorTables(gdaldataset)
            if len(tables) == 0:
                msg = "File has no surrogate color tables\n"
                msg = msg + "Use viewerwritetable to insert some"
                QMessageBox.critical(self, MESSAGE_TITLE, msg)
                return

            if len(tables) == 1:
                # only one - we can assume they want that
                tablename = list(tables.keys())[0]
            else:
                # need to ask them which one
                from PyQt5.QtWidgets import QInputDialog
                (tablename, ok) = QInputDialog.getItem(self, MESSAGE_TITLE,
                    "Select color table", list(tables.keys()), editable=False)
                if not ok:
                    return
                tablename = str(tablename)

            attributes.setLookupColName(colName)
            self.viewwidget.setColorTableLookup(col, colName, 
                                    tables[tablename], tablename)

        # so header gets updated
        self.tableModel.doUpdate(True)

    def setColumnKeyboardEdit(self, colName):
        """
        set column to receive keyboard events
        if col already sets, toggles off
        """
        if colName == self.keyboardEditColumn:
            self.keyboardEditColumn = None
            self.keyboardData = None
        else:
            self.keyboardEditColumn = colName
            self.keyboardData = ''
            # seem to need to do this otherwise table keeps focus
            self.setFocus()

    def saveColOrder(self):
        """
        Get the layer to save the current order
        of columns into the GDAL metadata
        """
        try:

            self.lastLayer.writeRATColumnOrder()

        except viewererrors.InvalidDataset as e:
            QMessageBox.critical(self, MESSAGE_TITLE, str(e))

    def activeToolChanged(self, obj):
        """
        Called in response to the activeToolChanged signal
        from the widget. If it wasn't called by us, unset our
        tools
        """
        if obj.senderid != id(self):
            self.suppressToolReset = True
            for tool in self.toolActions:
                tool.setChecked(False)
            self.suppressToolReset = False
            
    def layersChanged(self):
        """
        Called in response to layersChanged signal from 
        viewerlayers. We check to see if our lastLayer has been
        removed and if so, close.
        """
        if self.lastLayer is not None:
            if self.lastLayer not in self.viewwidget.layers.layers:
                # closing doesn't actually delete straight away
                # so decref the layer so file can be accessed elsewhere
                self.lastLayer = None
                # this also has a reference to the layer
                self.lastqi = None
                self.close()

    def newPolyGeogSelect(self, polyInfo):
        """
        New polygon just been selected as part of a 
        geographical select
        """
        # if not a signal for us, ignore
        if not self.geogSelectAction.isChecked():
            return

        # polyInfo is a PolygonToolInfo
        # get selection in poly
        selectMask = polyInfo.getDisplaySelectionMask()
        # valid daya
        validMask = polyInfo.getDisplayValidMask()
        # we want both - flatten for compress
        mask = numpy.logical_and(selectMask, validMask).flatten()
        # get the actual data
        data = polyInfo.getDisplayData().flatten()
        # get data where mask==True
        idx = numpy.unique(data.compress(mask))
        
        self.storeLastSelection()
        
        # reset if they havent hit Ctrl
        if int(polyInfo.getInputModifiers() & Qt.ControlModifier) == 0:
            self.selectionArray.fill(False)

        # select rows found in poly
        self.selectionArray[idx] = True

        if self.highlightAction.isChecked():
            self.viewwidget.highlightValues(self.highlightColor,
                                self.selectionArray)

        self.scrollToFirstSelected()
        self.updateToolTip()
        # so we repaint and our itemdelegate gets called
        self.tableModel.doUpdate()

        # so keyboard entry etc works
        self.activateWindow()

    def newLineGeogSelect(self, lineInfo):
        """
        New polyline just been selected as part of a 
        geographical select
        """
        # if not a signal for us, ignore
        if not self.geogSelectLineAction.isChecked():
            return
            
        # lineInfo is an instance of PolylineToolInfo
        data, mask, distance = lineInfo.getProfile()
        # we only interested where mask == True
        idx = numpy.unique(data.compress(mask))

        self.storeLastSelection()

        # reset if they havent hit Ctrl
        if int(lineInfo.getInputModifiers() & Qt.ControlModifier) == 0:
            self.selectionArray.fill(False)

        # select rows found in line
        self.selectionArray[idx] = True

        if self.highlightAction.isChecked():
            self.viewwidget.highlightValues(self.highlightColor,
                                self.selectionArray)

        self.scrollToFirstSelected()
        self.updateToolTip()
        # so we repaint and our itemdelegate gets called
        self.tableModel.doUpdate()

        # so keyboard entry etc works
        self.activateWindow()

    def toggleCoordsSelect(self, checked):
        """
        toggle the displayPixelCoords flag.
        """
        self.displayPixelCoords = checked
        if self.followAction.isChecked() and self.lastqi is not None:
            # set the coords
            if self.displayPixelCoords:
                self.eastingEdit.setText("%.5f" % self.lastqi.column)
                self.northingEdit.setText("%.5f" % self.lastqi.row)
            else:
                self.eastingEdit.setText("%.5f" % self.lastqi.easting)
                self.northingEdit.setText("%.5f" % self.lastqi.northing)

    def geogSelect(self, checked):
        """
        Turn on the polygon tool so we can select the area
        """
        # ask for a polygon to be collected
        if checked:
            self.geogSelectLineAction.setChecked(False)
            self.geogSelectPointAction.setChecked(False)
            self.viewwidget.setActiveTool(VIEWER_TOOL_POLYGON, id(self))
        elif not self.suppressToolReset:
            # reset tool
            self.viewwidget.setActiveTool(VIEWER_TOOL_QUERY, id(self))

    def geogLineSelect(self, checked):
        """
        Turn on the polyline tool so we can select the area
        """
        # ask for a polyline to be collected
        if checked:
            self.geogSelectAction.setChecked(False)
            self.geogSelectPointAction.setChecked(False)
            self.viewwidget.setActiveTool(VIEWER_TOOL_POLYLINE, id(self))
        elif not self.suppressToolReset:
            # reset tool
            self.viewwidget.setActiveTool(VIEWER_TOOL_QUERY, id(self))

    def geogPointSelect(self, checked):
        """
        Turn on the query tool so we can select a point
        """
        # ask for a point to be collected
        if checked:
            self.geogSelectAction.setChecked(False)
            self.geogSelectLineAction.setChecked(False)
        if not self.suppressToolReset:
            self.viewwidget.setActiveTool(VIEWER_TOOL_QUERY, id(self))

    def updateToolTip(self):
        """
        When in thematic mode we set a toolip
        over the attributes that tells the user how many items selected
        """
        # in numpy, False=0 and True=1 so we can do a sum()
        # to find how many selected
        nselected = self.selectionArray.sum()
        self.tableView.setToolTip("%d Selected" % nselected)

    def setToolBarState(self, thematic):
        """
        Set tool bar state to either thematic (True)
        or continuous (False). This enables/disables
        some of the toolbar buttons and the table header contect menu
        """        
        self.highlightAction.setEnabled(thematic)
        self.highlightColorAction.setEnabled(thematic)
        self.expressionAction.setEnabled(thematic)
        self.addColumnAction.setEnabled(thematic)
        self.removeSelectionAction.setEnabled(thematic)
        self.selectAllAction.setEnabled(thematic)
        self.expressionAction.setEnabled(thematic)
        self.unlockDatasetAction.setEnabled(thematic)
        self.addColumnAction.setEnabled(thematic)
        self.saveColOrderAction.setEnabled(thematic)
        self.geogSelectAction.setEnabled(thematic)
        self.geogSelectLineAction.setEnabled(thematic)
        self.geogSelectPointAction.setEnabled(thematic)
        self.thematicHeader.setThematicMode(thematic)

    def setupTableContinuous(self, data, layer):
        """
        setup the table for displaying Continuous
        data. This is a row per band with the pixel values for each band shown
        The current red, green and blue bands have an icon 
        """
        # disable relevant toolbars
        self.setToolBarState(False)

        # any new thematic data after this will have to be reloaded
        self.lastAttributeCount = -1
        self.lastAttributeid = -1
        self.lastLayer = layer

        self.tableModel = ContinuousTableModel(data, layer.bandNames,
                    layer.stretch, self)
        self.tableView.setModel(self.tableModel)

        self.selectionArray = None  # no selections

        self.tableView.setToolTip("")  # disable toolip
        
        # attempt to set the size of the Value colunm to something sensible
        if data is not None:
            largestString = "Value"  # name of column - don't make smaller than this
            largestStringSize = len(largestString)
            for d in data:
                s = "%s" % d
                size = len(s)
                if size > largestStringSize:
                    largestStringSize = size
                    largestString = s
            
            fm = self.tableView.fontMetrics()
            size = fm.size(Qt.TextSingleLine, largestString)
            self.tableView.setColumnWidth(2, size.width() + 20)

    def setupTableThematic(self, data, layer):
        """
        For a single band dataset with attributes. Displays
        the attributes as a table and highlights the current
        value in the table. 
        """
        # enable relevant toolbars
        self.setToolBarState(True)

        # do we need a new table model?
        # do we have a new id() if the attribute obj
        # or a new count of the file opened by that object
        if (id(layer.attributes) != self.lastAttributeid or 
                layer.attributes.count != self.lastAttributeCount):
            self.lastAttributeCount = layer.attributes.count
            self.lastAttributeid = id(layer.attributes)
            self.lastLayer = layer
            
            # display warning so the user knows what is happening
            # have an env var so we can disable this check from eg. plugin
            # (which is why we check it each time)
            if (layer.attributes.getNumRows() > MAX_ROW_COUNT and 
                    os.getenv('TUIVIEW_DISABLE_ROW_WARNING', default='0') != '1'):
                msg = ('The Attribute Table is larger than {} rows. ' +
                    'It will be truncated.').format(MAX_ROW_COUNT)
                QMessageBox.information(self, MESSAGE_TITLE, msg)

            self.tableModel = ThematicTableModel(layer.attributes, self)
            self.tableView.setModel(self.tableModel)

            # create our own selection model so nothing gets selected
            # as far as the model is concerned
            selectionModel = ThematicSelectionModel(self.tableModel, self)
            self.tableView.setSelectionModel(selectionModel)

            # create our selection array to record which items selected
            self.selectionArray = numpy.empty(layer.attributes.getNumRows(),
                bool)
            self.lastSelectionArray = None
            self.selectionArray.fill(False)  # none selected by default

        # set the highlight row if there is data
        if data is not None:
            val = data[0]
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
        self.tableModel.doUpdate(True)
        
    def locationSelected(self, qi):
        """
        The ViewerWidget has told us it has a new coordinate from
        the query tool.
        """
        if self.geogSelectPointAction.isChecked():
            value = qi.data[0]
            
            self.storeLastSelection()
            # reset if they havent hit Ctrl
            if (qi.modifiers is not None and 
                    int(qi.modifiers & Qt.ControlModifier) == 0):
                self.selectionArray.fill(False)

            # select rows found in point
            self.selectionArray[value] = True

            if self.highlightAction.isChecked():
                self.viewwidget.highlightValues(self.highlightColor,
                                self.selectionArray)

            self.scrollToFirstSelected()
            self.updateToolTip()
            # so we repaint and our itemdelegate gets called
            self.tableModel.doUpdate()

            # so keyboard entry etc works
            self.activateWindow()
        
        if self.followAction.isChecked():
            # set the coords
            if self.displayPixelCoords:
                self.eastingEdit.setText("%.5f" % qi.column)
                self.northingEdit.setText("%.5f" % qi.row)
            else:
                self.eastingEdit.setText("%.5f" % qi.easting)
                self.northingEdit.setText("%.5f" % qi.northing)
            nbands = qi.data.shape[0]

            # do the attribute thing if there is only one band
            # and we have attributes
            if nbands == 1 and qi.layer.attributes.hasAttributes():
                self.setupTableThematic(qi.data, qi.layer)
            else:
                # otherwise the multi band table
                self.setupTableContinuous(qi.data, qi.layer)

            # set up the plot
            self.updatePlot(qi, self.cursorColor)

            # window title
            title = "Query: %s" % qi.layer.title
            self.setWindowTitle(title)

            # add/modify this is a query point to the widget
            self.viewwidget.setQueryPoint(id(self), qi.easting, 
                        qi.northing, self.cursorColor, self.cursorSize)
            # remember this qi in case we need to change color
            self.lastqi = qi

    def updatePlot(self, qi, color):
        """
        Updates the plot widget with new data/color
        """
        self.plotWidget.removeCurves()
        self.plotWidget.removeLabels()

        pen = QPen(color)
        nbands = qi.data.shape[0]

        if qi.layer.wavelengths is None:
            # no wavelengths stored with data - just use band number
            xdata = numpy.arange(1, nbands + 1, 1)
        else:
            xdata = numpy.array(qi.layer.wavelengths)

        curve = plotwidget.PlotCurve(xdata, qi.data, pen)
        self.plotWidget.addCurve(curve)
        self.plotWidget.setXRange(xmin=xdata[0])  # just plot the range of the data

        # Calculate the interval for x-axis labels and plot labels
        # so that if there are more than 10 bands not all are labeled.
        # The interval between labels is set to provide ~ 10 labels.
        if len(xdata) > 10:
            label_interval = int(len(xdata) / 10.0)
        else:
            label_interval = 1

        # only do new labels if they have asked for them.
        if self.labelAction.isChecked():
            count = 1
            for x, y, text in zip(xdata[::label_interval], qi.data[::label_interval], qi.layer.bandNames[::label_interval]):
                # align appropriately for first and last
                if count == 1:
                    flags = Qt.AlignLeft | Qt.AlignTop
                else:
                    flags = Qt.AlignRight | Qt.AlignTop

                label = plotwidget.PlotLabel(x, y, text, flags)
                self.plotWidget.addLabel(label)
            
                count += 1

        # set xticks - we want descrete points
        # where there is data, if there are less than 10 bands
        # If there are more than 10, set interval so there are ~ 10 labels
        xticks = [plotwidget.PlotTick(int(x), "%d" % x) for x in xdata[::label_interval]]

        # set the alignment on the rightmost one so it gets displayed, 
        # not chopped
        xticks[-1].flags = Qt.AlignRight | Qt.AlignTop
        self.plotWidget.setXTicks(xticks)

        # set scaling if needed
        minScale, maxScale = self.plotScaling
        if minScale is None and maxScale is None:
            # set back to auto
            self.plotWidget.setYRange()
        else:
            # we need to provide both min and max so
            # derive from data if needed
            if minScale is None:
                minScale = qi.data.min()
            if maxScale is None:
                maxScale = qi.data.max()
            self.plotWidget.setYRange(minScale, maxScale)

    def closeEvent(self, event):
        """
        Window is being closed - inform parent window
        """
        self.viewwidget.removeQueryPoint(id(self))
        self.queryClosed.emit(self)

    def keyPressEvent(self, event):
        """
        User has pressed a key. See if we are recording keystrokes
        and updating attribute columns
        """
        from osgeo.gdal import GFT_Real, GFT_Integer, GFT_String
        if self.keyboardData is not None:
            key = event.key()
            if key == Qt.Key_Enter or key == Qt.Key_Return:
                try:
                    attributes = self.lastLayer.attributes
                    colname = self.keyboardEditColumn
                    data = str(self.keyboardData)
                    attributes.setColumnToConstant(colname, data, 
                                            self.selectionArray)

                    # so we repaint and new values get shown
                    self.tableModel.doUpdate()

                    # is this a the lookup column?
                    if colname == attributes.getLookupColName():
                        # can't just use result because we need selectionArray applied
                        col = attributes.getEntireAttribute(colname)
                        self.viewwidget.setColorTableLookup(col, colname)
                except viewererrors.UserExpressionError as e:
                    QMessageBox.critical(self, MESSAGE_TITLE, str(e))
                self.keyboardData = ''
            else:
                text = str(event.text())
                attributes = self.lastLayer.attributes
                dtype = attributes.getType(self.keyboardEditColumn)
                if dtype == GFT_Real and (text.isdigit() or text == "."):
                    self.keyboardData += text
                elif dtype == GFT_Integer and text.isdigit():        
                    self.keyboardData += text
                elif dtype == GFT_String and text.isalnum():
                    self.keyboardData += text
