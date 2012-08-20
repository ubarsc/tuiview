"""
Module that contains the LayerWindow class
"""

import os
from PyQt4.QtGui import QDockWidget, QListView, QIcon
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
        "Have to override to make it checkable and drag enabled"
        f = QAbstractListModel.flags(self, index)
        return f | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled

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


class LayerWindow(QDockWidget):
    """
    Our dock window that shows the layers. 
    Contains a list view
    """
    def __init__(self, parent, viewwidget):
        QDockWidget.__init__(self, "Layers", parent)
        self.viewwidget = viewwidget

        # create the list view
        self.listView = QListView()
        self.listView.setDragDropMode(QListView.InternalMove)
        self.listView.setDragEnabled(True)

        # set our item model
        model = LayerItemModel(viewwidget, self)
        self.listView.setModel(model)

        self.setWidget(self.listView)

        # connect so we get told when layers added and removed
        self.connect(viewwidget.layers, SIGNAL("layersChanged()"), self.layersChanged)

    def layersChanged(self):
        """
        Called when a layer has been added or removed to/from the LayerManager
        """
        # the only way I can get the whole thing redrawn
        # is to pretend I have a new model. Any suggestions?
        model = LayerItemModel(self.viewwidget, self)
        self.listView.setModel(model)


