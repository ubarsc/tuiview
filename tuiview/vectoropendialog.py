"""
Module that contains the VectorOpenDialog class
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
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QRadioButton
from PySide6.QtWidgets import QButtonGroup, QComboBox, QTextEdit, QPushButton
from PySide6.QtGui import QFontMetrics

NUM_SQL_ROWS = 4


class VectorOpenDialog(QDialog):
    """
    Allows user to select which layer
    """
    def __init__(self, parent, layerList):
        QDialog.__init__(self, parent)
        self.setWindowTitle('Open Vector Layer')
        self.layerList = layerList

        self.layerTypeButtonGroup = QButtonGroup()  # enforces exclusivity
        self.layerNameRadio = QRadioButton("Layer Name")
        self.layerSQLRadio = QRadioButton("SQL")
        self.layerTypeButtonGroup.addButton(self.layerNameRadio)
        self.layerTypeButtonGroup.addButton(self.layerSQLRadio)
        self.layerNameRadio.setChecked(True)  # the default

        self.mainLayout = QVBoxLayout()

        self.nameLayout = QHBoxLayout()
        self.nameLayout.addWidget(self.layerNameRadio)

        self.nameCombo = QComboBox()
        for layerName in layerList:
            self.nameCombo.addItem(layerName)
        self.nameLayout.addWidget(self.nameCombo)

        self.mainLayout.addLayout(self.nameLayout)

        self.sqlLayout = QHBoxLayout()
        self.sqlLayout.addWidget(self.layerSQLRadio)
        self.sqlText = QTextEdit()
        self.sqlText.setReadOnly(True)
        fm = QFontMetrics(self.sqlText.font())
        self.sqlText.setFixedHeight(NUM_SQL_ROWS * fm.lineSpacing())
        
        self.layerNameRadio.toggled.connect(self.typeToggled)
        self.sqlLayout.addWidget(self.sqlText)

        self.mainLayout.addLayout(self.sqlLayout)

        # ok and cancel buttons
        self.okButton = QPushButton(self)
        self.okButton.setText("OK")
        self.okButton.setDefault(True)
        self.okButton.clicked.connect(self.accept)

        self.cancelButton = QPushButton(self)
        self.cancelButton.setText("Cancel")
        self.cancelButton.clicked.connect(self.reject)

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.addWidget(self.okButton)
        self.buttonLayout.addWidget(self.cancelButton)
        self.mainLayout.addLayout(self.buttonLayout)

        self.setLayout(self.mainLayout)

    def typeToggled(self, checked):
        "signal handler for change of state"
        self.sqlText.setReadOnly(checked)

    def isNamedLayer(self):
        "Return if the user has selected a named layer rather than SQL"
        return self.layerNameRadio.isChecked()

    def getSelectedLayer(self):
        "Get the name of the selected layer"
        return self.nameCombo.currentText()

    def getSQL(self):
        "return the SQL text entered"
        return self.sqlText.toPlainText()

