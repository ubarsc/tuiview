"""
Contains the AddColumnDialog class
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

from PyQt4.QtGui import QDialog, QFormLayout, QComboBox, QLineEdit
from PyQt4.QtGui import QPushButton, QHBoxLayout, QVBoxLayout, QMessageBox
from PyQt4.QtCore import SIGNAL
import sys

from .viewerRAT import NEWCOL_INT, NEWCOL_FLOAT, NEWCOL_STRING

class AddColumnDialog(QDialog):
    """
    Dialog that allows a user to select type of new RAT
    column and enter the name
    """
    def __init__(self, parent):
        QDialog.__init__(self, parent)

        self.typeCombo = QComboBox()
        userdata = NEWCOL_INT
        self.typeCombo.addItem("Integer", userdata)
        userdata = NEWCOL_FLOAT
        self.typeCombo.addItem("Floating Point", userdata)
        userdata = NEWCOL_STRING
        self.typeCombo.addItem("String", userdata)

        self.nameEdit = QLineEdit()

        self.formLayout = QFormLayout()
        self.formLayout.addRow("Column Type", self.typeCombo)
        self.formLayout.addRow("Column Name", self.nameEdit)

        self.okButton = QPushButton()
        self.okButton.setText("OK")
        self.connect(self.okButton, SIGNAL("clicked()"), self.onOK)

        self.cancelButton = QPushButton()
        self.cancelButton.setText("Cancel")
        self.connect(self.cancelButton, SIGNAL("clicked()"), self.reject)

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.addWidget(self.okButton)
        self.buttonLayout.addWidget(self.cancelButton)

        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.addLayout(self.formLayout)
        self.mainLayout.addLayout(self.buttonLayout)
        self.nameEdit.setFocus()

    def onOK(self):
        if len(self.nameEdit.text()) == 0:
            QMessageBox.critical(self, "Viewer", "Must enter column name")
            self.nameEdit.setFocus()
        else:
            self.accept()

    def getColumnType(self):
        index = self.typeCombo.currentIndex()
        userdata = self.typeCombo.itemData(index)
        if sys.version_info[0] >= 3:
            return int(userdata)
        else:
            return userdata.toInt()[0]

    def getColumnName(self):
        return str(self.nameEdit.text())


