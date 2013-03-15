"""
Module that contains the LayerWindow class
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
from PyQt4.QtGui import QDockWidget, QListView, QIcon, QMenu, QAction
from PyQt4.QtGui import QMessageBox
from PyQt4.QtCore import QAbstractListModel, Qt, SIGNAL

from . import viewerlayers

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
            fname = os.path.basename(layer.filename)
            return fname
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
            if sys.version_info[0] >= 3:
                state = value
            else:
                state = value.toInt()[0]
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
        self.setupActions()
        self.setupMenu()

    def setupActions(self):
        "Set up the actions for the popup menu"
        self.layerExtentAct = QAction(self)
        self.layerExtentAct.setText("&Zoom to Layer Extent")
        self.layerExtentAct.setStatusTip("Zoom to Layer Extent")
        self.layerExtentAct.setIcon(QIcon(":/viewer/images/zoomlayer.png"))
        self.layerExtentAct.setIconVisibleInMenu(True)
        self.connect(self.layerExtentAct, SIGNAL("triggered()"), self.zoomLayer)

        self.removeLayerAct = QAction(self)
        self.removeLayerAct.setText("&Remove Layer")
        self.removeLayerAct.setStatusTip("Remove selected layer")
        self.removeLayerAct.setIcon(QIcon(":/viewer/images/removelayer.png"))
        self.removeLayerAct.setIconVisibleInMenu(True)
        self.connect(self.removeLayerAct, SIGNAL("triggered()"), 
                                                        self.removeLayer)

        self.moveUpAct = QAction(self)
        self.moveUpAct.setText("Move &Up")
        self.moveUpAct.setStatusTip("Move selected layer up in list")
        self.moveUpAct.setIcon(QIcon(":/viewer/images/arrowup.png"))
        self.moveUpAct.setIconVisibleInMenu(True)
        self.connect(self.moveUpAct, SIGNAL("triggered()"), self.moveUp)

        self.moveDownAct = QAction(self)
        self.moveDownAct.setText("Move &Down")
        self.moveDownAct.setStatusTip("Move selected layer down in list")
        self.moveDownAct.setIcon(QIcon(":/viewer/images/arrowdown.png"))
        self.moveDownAct.setIconVisibleInMenu(True)
        self.connect(self.moveDownAct, SIGNAL("triggered()"), self.moveDown)

        self.moveToTopAct = QAction(self)
        self.moveToTopAct.setText("Move To &Top")
        self.moveToTopAct.setStatusTip("Move selected layer top top")
        self.connect(self.moveToTopAct, SIGNAL("triggered()"), self.moveToTop)
        
        self.changeColorAct = QAction(self)
        self.changeColorAct.setText("Change &Color")
        self.changeColorAct.setStatusTip("Change color of vector layer")
        self.connect(self.changeColorAct,  SIGNAL("triggered()"), 
                                                            self.changeColor)
                                                            
        self.setSQLAct = QAction(self)
        self.setSQLAct.setText("Set &attribute filter")
        self.setSQLAct.setStatusTip("Set attribute filter via SQL")
        self.connect(self.setSQLAct, SIGNAL("triggered()"), self.setSQL)

        self.editStretchAct = QAction(self)
        self.editStretchAct.setText("&Edit Stretch")
        self.editStretchAct.setStatusTip("Edit Stretch of raster layer")
        self.connect(self.editStretchAct, SIGNAL("triggered()"), 
                                                    self.editStretch)

        self.propertiesAct = QAction(self)
        self.propertiesAct.setText("&Properties")
        self.propertiesAct.setStatusTip("Show properties of file")
        self.connect(self.propertiesAct, SIGNAL("triggered()"), self.properties)

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

    def removeLayer(self):
        "remove the selected layer"
        selected = self.selectedIndexes()
        if len(selected) > 0:
            index = selected[0]

            model = self.model()
            layer = model.getLayer(index)
            model.viewwidget.layers.removeLayer(layer)
            model.viewwidget.viewport().update()

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
        from PyQt4.QtGui import QColorDialog, QColor
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
        from PyQt4.QtGui import QInputDialog
        selected = self.selectedIndexes()
        if len(selected) > 0:
            index = selected[0]

            model = self.model()
            layer = model.getLayer(index)
            
            oldsql = ""
            if layer.hasSQL():
                oldsql = layer.getSQL()
                
            sql, ok = QInputDialog.getText(self, "Viewer", 
                "Enter SQL attribute filter", text=oldsql)
            if ok:
                if sql == "":
                    sql = None
                else:
                    sql = str(sql)
                layer.setSQL(sql)
                layer.getImage()
                model.viewwidget.viewport().update()

    def editStretch(self):
        "Edit the stretch for the layer"
        from . import stretchdialog
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
            propstring = layer.getPropertiesString()
            QMessageBox.information(self, "Viewer", propstring)

class LayerWindow(QDockWidget):
    """
    Our dock window that shows the layers. 
    Contains a list view
    """
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
        self.connect(viewwidget.layers, SIGNAL("layersChanged()"), 
                                        self.layersChanged)

    def layersChanged(self):
        """
        Called when a layer has been added or removed to/from the LayerManager
        """
        # the only way I can get the whole thing redrawn
        # is to pretend I have a new model. Any suggestions?
        model = LayerItemModel(self.viewwidget, self.parent, self)
        self.listView.setModel(model)


