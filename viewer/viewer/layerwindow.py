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
from PyQt4.QtGui import QDockWidget, QListView, QIcon, QMenu, QAction
from PyQt4.QtGui import QMessageBox
from PyQt4.QtCore import QAbstractListModel, QVariant, Qt, SIGNAL

class LayerItemModel(QAbstractListModel):
    """
    This class provides the data to the list view by 
    reading the list of layers provided by the LayerManager
    """
    def __init__(self, viewwidget, parent):
        QAbstractListModel.__init__(self, parent)
        self.viewwidget = viewwidget
        self.rasterIcon = QIcon(":/viewer/images/rasterlayer.png")

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
            return QVariant()

        layer = self.getLayer(index)

        if role == Qt.DisplayRole:
            # name 
            fname = os.path.basename(layer.filename)
            return QVariant(fname)
        elif role == Qt.DecorationRole:
            # icon
            return QVariant(self.rasterIcon)
        elif role == Qt.CheckStateRole:
            # whether displayed or not
            if layer.displayed:
                return QVariant(Qt.Checked)
            else:
                return QVariant(Qt.Unchecked)
        else:
            return QVariant()

    def setData(self, index, value, role):
        """
        Set the data back. Only bother with CheckStateRole
        """
        if role == Qt.CheckStateRole:
            state = value.toInt()[0]
            layer = self.getLayer(index)
            layer.displayed = state == Qt.Checked

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

        self.propertiesAct = QAction(self)
        self.propertiesAct.setText("&Properties")
        self.propertiesAct.setStatusTip("Show properties of file")
        self.connect(self.propertiesAct, SIGNAL("triggered()"), self.properties)

    def setupMenu(self):
        "Create the popup menu"
        self.popupMenu = QMenu(self)
        self.popupMenu.addAction(self.layerExtentAct)
        self.popupMenu.addAction(self.removeLayerAct)
        self.popupMenu.addAction(self.moveUpAct)
        self.popupMenu.addAction(self.moveDownAct)
        self.popupMenu.addSeparator()
        self.popupMenu.addAction(self.propertiesAct)

    def contextMenuEvent(self, e):
        "Show our popup menu"
        self.popupMenu.popup(e.globalPos())

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

        # create the list view
        self.listView = LayerListView()

        # set our item model
        model = LayerItemModel(viewwidget, self)
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
        model = LayerItemModel(self.viewwidget, self)
        self.listView.setModel(model)


