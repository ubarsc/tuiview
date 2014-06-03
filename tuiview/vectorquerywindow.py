"""
Module that contains the VectorQueryDockWidget
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

from PyQt4.QtGui import QDockWidget, QAction, QIcon, QWidget, QToolBar
from PyQt4.QtGui import QVBoxLayout, QTreeWidget, QTreeWidgetItem
from PyQt4.QtCore import SIGNAL

class VectorQueryDockWidget(QDockWidget):
    """
    Dockable window that is a combined profile and ruler
    """
    def __init__(self, parent):
        QDockWidget.__init__(self, "Vector Query", parent)

        # create a new widget that lives in the dock window
        self.dockWidget = QWidget()
        self.mainLayout = QVBoxLayout()

        self.toolBar = QToolBar(self.dockWidget)
        self.setupActions()
        self.setupToolbar()
        self.mainLayout.addWidget(self.toolBar)

        self.treeWidget = QTreeWidget(self)
        self.treeWidget.setColumnCount(2)
        self.treeWidget.setHeaderLabels(["Field", "Value"])
        self.mainLayout.addWidget(self.treeWidget)

        self.dockWidget.setLayout(self.mainLayout)
        
        # tell the dock window this is the widget to display
        self.setWidget(self.dockWidget)

        self.resize(400, 400)

    def setupActions(self):
        """
        Create the actions to be shown on the toolbar
        """
        self.followAction = QAction(self)
        self.followAction.setText("&Follow Vector Query Tool")
        self.followAction.setStatusTip("Follow Vector Query Tool")
        self.followAction.setIcon(QIcon(":/viewer/images/queryvector.png"))
        self.followAction.setCheckable(True)
        self.followAction.setChecked(True)

    def setupToolbar(self):
        """
        Add the actions to the toolbar
        """
        self.toolBar.addAction(self.followAction)

    def vectorLocationSelected(self, results, layer):
        """
        called in response to vectorLocationSelected signal
        """
        if not self.followAction.isChecked():
            return

        title = "Vector Query: %s" % layer.title
        self.setWindowTitle(title)

        self.treeWidget.clear()
        for result in results:
            item = QTreeWidgetItem(["Feature", ""])
            for key in sorted(result.keys()):
                child = QTreeWidgetItem([key, result[key]])
                item.addChild(child)
            self.treeWidget.addTopLevelItem(item)
            self.treeWidget.expandItem(item)

    def closeEvent(self, event):
        """
        Window is being closed - inform parent window
        """
        self.emit(SIGNAL("queryClosed(PyQt_PyObject)"), self)
