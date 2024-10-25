
"""
Contains the TileDialog class
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

from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QPushButton
from PySide6.QtWidgets import QSpinBox, QLabel


class TileDialog(QDialog):
    """
    Dialog that allows user to select how many viewers across and down 
    they want (or auto)
    """
    def __init__(self, parent, name):
        QDialog.__init__(self, parent)
        
        self.xspin = QSpinBox()
        self.xspin.setRange(0, 100)
        self.xspin.setSpecialValueText("Auto")
        self.xspin.setValue(0)

        self.yspin = QSpinBox()
        self.yspin.setRange(0, 100)
        self.yspin.setSpecialValueText("Auto")
        self.yspin.setValue(0)

        self.formLayout = QFormLayout(self)
        if name is not None:
            # add a row to display the current screen name
            self.screenLabel = QLabel(name)
            self.screenLabel.setToolTip(
                "To tile windows on another screen, use a viewer on that screen")
            self.formLayout.addRow("Tile Windows On Screen", self.screenLabel)
        
        self.formLayout.addRow("Viewers Across", self.xspin)
        self.formLayout.addRow("Viewers Down", self.yspin)

        self.okButton = QPushButton()
        self.okButton.setText("OK")

        self.cancelButton = QPushButton()
        self.cancelButton.setText("Cancel")

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.addWidget(self.okButton)
        self.buttonLayout.addWidget(self.cancelButton)
        self.formLayout.addRow(self.buttonLayout)

        self.okButton.clicked.connect(self.accept)
        self.cancelButton.clicked.connect(self.reject)
        self.setLayout(self.formLayout)

    def getValues(self):
        "Returns the x and y value as a tuple"
        return self.xspin.value(), self.yspin.value()
