"""
Module that contains the LayerWindow class
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

from PyQt5.QtGui import QIcon, QColor
from PyQt5.QtWidgets import QDockWidget, QListView, QMenu, QAbstractItemView
from PyQt5.QtWidgets import QAction, QInputDialog, QColorDialog
from PyQt5.QtCore import QAbstractListModel, Qt, pyqtSignal

from . import viewerlayers
from . import stretchdialog
from . import propertieswindow
from .viewerstrings import MESSAGE_TITLE


class LayerItemModel(QAbstractListModel):
    """
    This class provides the data to the list view by 
    reading the list of layers provided by the LayerManager
    """
    def __init__(self, viewwidget, viewwindow, parent):
        QAbstractListModel.__init__(self, parent)
        self.viewwidget = viewwidget
        self.viewwindow = viewwindow
        self.rasterIcon = QIcon(":/viewer/images/rasterlayer.png")
        self.vectorIcon = QIcon(":/viewer/images/vectorlayer.png")

    def rowCount(self, parent):
        "Just the number of layers"
        return len(self.viewwidget.layers.layers)

    def flags(self, index):
        "Have to override to make it checkable"
        f = QAbstractListModel.flags(self, index)
        return f | Qt.ItemIsUserCheckable

    def getLayer(self, index):
        """
        Because we are showing the layers in the opposite
        order (last layer is top) we have a helper function
        to get the right layer
        """
        row = index.row()
        layerNum = len(self.viewwidget.layers.layers) - row - 1
        return self.viewwidget.layers.layers[layerNum]

    def data(self, index, role):
        """
        Get the data associated with an item
        """
        if not index.isValid():
            return None

        layer = self.getLayer(index)

        if role == Qt.DisplayRole:
            # name 
            return layer.title
        elif role == Qt.DecorationRole:
            # icon
            layer = self.getLayer(index)
            if isinstance(layer, viewerlayers.ViewerRasterLayer):
                return self.rasterIcon
            else:
                return self.vectorIcon
        elif role == Qt.CheckStateRole:
            # whether displayed or not
            if layer.displayed:
                return Qt.Checked
            else:
                return Qt.Unchecked
        else:
            return None

    def setData(self, index, value, role):
        """
        Set the data back. Only bother with CheckStateRole
        """
        if role == Qt.CheckStateRole:
            state = value
            layer = self.getLayer(index)
            state = state == Qt.Checked
            self.viewwidget.layers.setDisplayedState(layer, state)

            # redraw
            self.viewwidget.viewport().update()

            return True
        return False


class LayerListView(QListView):
    """
    Our own QListView derived class so we can handle the context menu event
    """
    def __init__(self):
        QListView.__init__(self)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setupActions()
        self.setupMenu()

    def setupActions(self):
        "Set up the actions for the popup menu"
        self.layerExtentAct = QAction(self, triggered=self.zoomLayer)
        self.layerExtentAct.setText("&Zoom to Layer Extent")
        self.layerExtentAct.setStatusTip("Zoom to Layer Extent")
        self.layerExtentAct.setIcon(QIcon(":/viewer/images/zoomlayer.png"))
        self.layerExtentAct.setIconVisibleInMenu(True)

        self.removeLayerAct = QAction(self, triggered=self.removeLayers)
        self.removeLayerAct.setText("&Remove Selected Layer(s)")
        self.removeLayerAct.setStatusTip("Remove selected layer(s)")
        self.removeLayerAct.setIcon(QIcon(":/viewer/images/removelayer.png"))
        self.removeLayerAct.setIconVisibleInMenu(True)

        self.moveUpAct = QAction(self, triggered=self.moveUp)
        self.moveUpAct.setText("Move &Up")
        self.moveUpAct.setStatusTip("Move selected layer up in list")
        self.moveUpAct.setIcon(QIcon(":/viewer/images/arrowup.png"))
        self.moveUpAct.setIconVisibleInMenu(True)

        self.moveDownAct = QAction(self, triggered=self.moveDown)
        self.moveDownAct.setText("Move &Down")
        self.moveDownAct.setStatusTip("Move selected layer down in list")
        self.moveDownAct.setIcon(QIcon(":/viewer/images/arrowdown.png"))
        self.moveDownAct.setIconVisibleInMenu(True)

        self.moveToTopAct = QAction(self, triggered=self.moveToTop)
        self.moveToTopAct.setText("Move To &Top")
        self.moveToTopAct.setStatusTip("Move selected layer top top")
        
        self.changeColorAct = QAction(self, triggered=self.changeColor)
        self.changeColorAct.setText("Change &Color")
        self.changeColorAct.setStatusTip("Change color of vector layer")

        self.setSQLAct = QAction(self, triggered=self.setSQL)
        self.setSQLAct.setText("Set &attribute filter")
        self.setSQLAct.setStatusTip("Set attribute filter via SQL")

        self.setLineWidthAct = QAction(self, triggered=self.setLineWidth)
        self.setLineWidthAct.setText("Set &Line width")
        self.setLineWidthAct.setStatusTip("Set line width of rendered features")

        self.setPointCrossSizeAct = QAction(self, triggered=self.setPointCrossSize)
        self.setPointCrossSizeAct.setText("Set P&oint cross size")
        self.setPointCrossSizeAct.setStatusTip("Set the size of the point crosshair")

        self.setFillAct = QAction(self, toggled=self.toggleFill)
        self.setFillAct.setText("Fill Polygons")
        self.setFillAct.setStatusTip("Toggle the fill status of polygons")
        self.setFillAct.setCheckable(True)
        
        self.setLabelAct = QAction(self, triggered=self.setLabel)
        self.setLabelAct.setText("Set Label")
        self.setLabelAct.setStatusTip("Set the attribute to show as a label")
        
        self.setLabelColorAct = QAction(self, triggered=self.setLabelColor)
        self.setLabelColorAct.setText("Set Label Color")
        self.setLabelColorAct.setStatusTip("Set the color of the labels")

        self.editStretchAct = QAction(self, triggered=self.editStretch)
        self.editStretchAct.setText("&Edit Stretch")
        self.editStretchAct.setStatusTip("Edit Stretch of raster layer")

        self.propertiesAct = QAction(self, triggered=self.properties)
        self.propertiesAct.setText("&Properties")
        self.propertiesAct.setStatusTip("Show properties of file")
        self.propertiesAct.setIcon(QIcon(":/viewer/images/properties.png"))
        self.propertiesAct.setIconVisibleInMenu(True)

    def setupMenu(self):
        "Create the popup menus"
        self.rasterPopupMenu = QMenu(self)
        self.rasterPopupMenu.addAction(self.layerExtentAct)
        self.rasterPopupMenu.addAction(self.removeLayerAct)
        self.rasterPopupMenu.addAction(self.moveUpAct)
        self.rasterPopupMenu.addAction(self.moveDownAct)
        self.rasterPopupMenu.addAction(self.moveToTopAct)
        self.rasterPopupMenu.addSeparator()
        self.rasterPopupMenu.addAction(self.editStretchAct)
        self.rasterPopupMenu.addAction(self.propertiesAct)
        
        self.vectorPopupMenu = QMenu(self)
        self.vectorPopupMenu.addAction(self.layerExtentAct)
        self.vectorPopupMenu.addAction(self.removeLayerAct)
        self.vectorPopupMenu.addAction(self.moveUpAct)
        self.vectorPopupMenu.addAction(self.moveDownAct)
        self.vectorPopupMenu.addAction(self.moveToTopAct)
        self.vectorPopupMenu.addSeparator()
        self.vectorPopupMenu.addAction(self.changeColorAct)
        self.vectorPopupMenu.addAction(self.setSQLAct)
        self.vectorPopupMenu.addAction(self.setLineWidthAct)
        self.vectorPopupMenu.addAction(self.setPointCrossSizeAct)
        self.vectorPopupMenu.addAction(self.setFillAct)
        self.vectorPopupMenu.addSeparator()
        self.vectorPopupMenu.addAction(self.setLabelAct)
        self.vectorPopupMenu.addAction(self.setLabelColorAct)
        self.vectorPopupMenu.addSeparator()
        self.vectorPopupMenu.addAction(self.propertiesAct)

    def contextMenuEvent(self, e):
        "Show our popup menu"
        selected = self.selectedIndexes()
        if len(selected) > 0:
            index = selected[0]

            model = self.model()
            layer = model.getLayer(index)
            if isinstance(layer, viewerlayers.ViewerVectorLayer):
                # sql gets enabled only if it is a full vector layer
                # - not a single feature layer
                allowSQL = not isinstance(layer, 
                            viewerlayers.ViewerFeatureVectorLayer)
                self.setSQLAct.setEnabled(allowSQL)

                # get the existing state of the fill
                bFill = layer.getFill()
                self.setFillAct.setChecked(bFill)

                self.vectorPopupMenu.popup(e.globalPos())
            else:
                self.rasterPopupMenu.popup(e.globalPos())

    def zoomLayer(self):
        "zoom to the extents of the selected layer"
        selected = self.selectedIndexes()
        if len(selected) > 0:
            index = selected[0]

            model = self.model()
            layer = model.getLayer(index)
            extent = layer.coordmgr.getFullWorldExtent()
            layer.coordmgr.setWorldExtent(extent)
            model.viewwidget.layers.makeLayersConsistent(layer)
            model.viewwidget.layers.updateImages()
            model.viewwidget.viewport().update()

    def removeLayers(self):
        "remove the selected layer"
        try:
            selected = self.selectedIndexes()
        except AttributeError:
            # Layer windows is not open
            selected = []

        if len(selected) > 0:
            model = self.model()
            layers = [model.getLayer(layer) for layer in selected]

            model.viewwidget.removeLayers(layers)

    def moveUp(self):
        "Move the selected layer up in order"
        selected = self.selectedIndexes()
        if len(selected) > 0:
            index = selected[0]

            model = self.model()
            layer = model.getLayer(index)
            model.viewwidget.layers.moveLayerUp(layer)
            model.viewwidget.viewport().update()

    def moveDown(self):
        "Move the selected layer down in order"
        selected = self.selectedIndexes()
        if len(selected) > 0:
            index = selected[0]

            model = self.model()
            layer = model.getLayer(index)
            model.viewwidget.layers.moveLayerDown(layer)
            model.viewwidget.viewport().update()

    def moveToTop(self):
        "Move the selected layer to the top"
        selected = self.selectedIndexes()
        if len(selected) > 0:
            index = selected[0]

            model = self.model()
            layer = model.getLayer(index)
            model.viewwidget.layers.moveLayerToTop(layer)
            model.viewwidget.viewport().update()
            
    def changeColor(self):
        "Change the color of the vector layer"
        selected = self.selectedIndexes()
        if len(selected) > 0:
            index = selected[0]

            model = self.model()
            layer = model.getLayer(index)
            
            rgba = layer.getColorAsRGBATuple()
            init = QColor(rgba[0], rgba[1], rgba[2], rgba[3])
            newCol = QColorDialog.getColor(init, self, "Choose Layer Color",
                            QColorDialog.ShowAlphaChannel)
            if newCol.isValid():
                rgba = (newCol.red(), newCol.green(), newCol.blue(), 
                    newCol.alpha())
                layer.updateColor(rgba)
                model.viewwidget.viewport().update()
                
    def setSQL(self):
        "Set the attribute filter for vector layers"
        selected = self.selectedIndexes()
        if len(selected) > 0:
            index = selected[0]

            model = self.model()
            layer = model.getLayer(index)
            
            oldsql = ""
            if layer.hasSQL():
                oldsql = layer.getSQL()
                
            sql, ok = QInputDialog.getText(self, MESSAGE_TITLE, 
                "Enter SQL attribute filter", text=oldsql)
            if ok:
                if sql == "":
                    sql = None
                else:
                    sql = str(sql)
                layer.setSQL(sql)
                layer.getImage()
                model.viewwidget.viewport().update()

    def setLineWidth(self):
        "Set the line width for vector layers"
        selected = self.selectedIndexes()
        if len(selected) > 0:
            index = selected[0]

            model = self.model()
            layer = model.getLayer(index)

            linewidth = layer.getLineWidth()            
                
            linewidth, ok = QInputDialog.getInt(self, MESSAGE_TITLE, 
                "Enter line width", value=linewidth, min=0, max=100)
            if ok:
                layer.setLineWidth(linewidth)
                layer.getImage()
                model.viewwidget.viewport().update()
                
    def setPointCrossSize(self):
        "Set the cross hair size for points"
        selected = self.selectedIndexes()
        if len(selected) > 0:
            index = selected[0]

            model = self.model()
            layer = model.getLayer(index)

            crossHairSize = layer.getHalfCrossSize()
                
            crossHairSize, ok = QInputDialog.getInt(self, MESSAGE_TITLE, 
                "Enter half crosshair size", value=crossHairSize, min=0, max=100)
            if ok:
                layer.setHalfCrossSize(crossHairSize)
                layer.getImage()
                model.viewwidget.viewport().update()

    def toggleFill(self, state):
        "toggle the fill state"
        selected = self.selectedIndexes()
        if len(selected) > 0:
            index = selected[0]

            model = self.model()
            layer = model.getLayer(index)
            layer.setFill(state)
            layer.getImage()
            model.viewwidget.viewport().update()
            
    def setLabel(self):
        "Set the label"
        selected = self.selectedIndexes()
        if len(selected) > 0:
            index = selected[0]

            model = self.model()
            layer = model.getLayer(index)
            all_attributes = layer.getAvailableAttributes()
            attribute_list = ["<None>"]
            attribute_list.extend(all_attributes)
            idx = 0
            field = layer.getFieldToLabel()
            if field is not None:
                idx = attribute_list.index(field)
            att, ok = QInputDialog.getItem(self, MESSAGE_TITLE, 
                "Select Attribute", attribute_list, idx, False)
            if ok:
                if att == "<None>":
                    att = None
                layer.setFieldToLabel(att)
                layer.getImage()  # need to redraw whole thing so old labels aren't seen
                model.viewwidget.viewport().update()
                
    def setLabelColor(self):
        "Color for label"
        selected = self.selectedIndexes()
        if len(selected) > 0:
            index = selected[0]

            model = self.model()
            layer = model.getLayer(index)
            color = layer.getLabelColor()
            init = QColor(color[0], color[1], color[2], color[3])
            newCol = QColorDialog.getColor(init, self, "Choose Label Color",
                            QColorDialog.ShowAlphaChannel)
            if newCol.isValid():
                rgba = (newCol.red(), newCol.green(), newCol.blue(), 
                    newCol.alpha())
                layer.updateLabelColor(rgba)
                model.viewwidget.viewport().update()

    def editStretch(self):
        "Edit the stretch for the layer"
        selected = self.selectedIndexes()
        if len(selected) > 0:
            index = selected[0]

            model = self.model()
            layer = model.getLayer(index)

            stretchDock = stretchdialog.StretchDockWidget(self, 
                                model.viewwidget, layer)
            model.viewwindow.addDockWidget(Qt.TopDockWidgetArea, stretchDock)

    def properties(self):
        "Show the properties for the layer"
        selected = self.selectedIndexes()
        if len(selected) > 0:
            index = selected[0]

            model = self.model()
            layer = model.getLayer(index)
            info = layer.getPropertiesInfo()
            dlg = propertieswindow.PropertiesWindow(self, info)
            dlg.setWindowTitle(layer.title)
            dlg.show()


class LayerWindow(QDockWidget):
    """
    Our dock window that shows the layers. 
    Contains a list view
    """
    # signals
    layerWindowClosed = pyqtSignal('QDockWidget', name='layerWindowClosed')

    def __init__(self, parent, viewwidget):
        QDockWidget.__init__(self, "Layers", parent)
        self.viewwidget = viewwidget
        self.parent = parent

        # create the list view
        self.listView = LayerListView()

        # set our item model
        model = LayerItemModel(viewwidget, parent, self)
        self.listView.setModel(model)

        self.setWidget(self.listView)

        # connect so we get told when layers added and removed
        viewwidget.layers.layersChanged.connect(self.layersChanged)

    def layersChanged(self):
        """
        Called when a layer has been added or removed to/from the LayerManager
        """
        # the only way I can get the whole thing redrawn
        # is to pretend I have a new model. Any suggestions?
        model = LayerItemModel(self.viewwidget, self.parent, self)
        self.listView.setModel(model)

    def closeEvent(self, event):
        """
        Window is being closed - inform parent window
        """
        self.layerWindowClosed.emit(self)
