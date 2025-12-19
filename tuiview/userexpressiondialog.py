
"""
Contains the UserExpressionDialog class
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

from PySide6.QtWidgets import QTextEdit, QLabel, QSplitter, QWidget
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton
from PySide6.QtGui import QPalette
from PySide6.QtCore import Signal, Qt


class UserExpressionDialog(QDialog):
    """
    Allows user to enter a expression and have it applied.
    Sends a signal with the expresson on Apply
    """
    # signals
    newExpression = Signal((str, str), (str, str, int), 
                        name='newExpression')
    "emitted when a new expression is entered"

    def __init__(self, parent, col=None):
        QDialog.__init__(self, parent)
        # if this is not none col included in signal
        self.col = col 

        self.setWindowTitle("Enter Expression")

        self.splitter = QSplitter(self)
        self.splitter.setOrientation(Qt.Vertical)
        
        self.importWidget = QWidget()
        self.importLayout = QVBoxLayout()
        self.importWidget.setLayout(self.importLayout)
        
        self.importLabel = QLabel()
        self.importLabel.setText("Enter Imports")
        self.importLayout.addWidget(self.importLabel)
        
        self.importEdit = QTextEdit()
        self.importEdit.setAcceptRichText(False)
        self.importLayout.addWidget(self.importEdit)

        self.splitter.addWidget(self.importWidget)
        
        self.exprWidget = QWidget()
        self.exprLayout = QVBoxLayout()
        self.exprWidget.setLayout(self.exprLayout)
        
        self.exprLabel = QLabel()
        self.exprLabel.setText("Enter Expression")
        self.exprLayout.addWidget(self.exprLabel)

        self.exprEdit = QTextEdit()
        self.exprEdit.setAcceptRichText(False)
        self.exprLayout.addWidget(self.exprEdit)

        self.splitter.addWidget(self.exprWidget)
        
        self.hintWidget = QWidget()
        self.hintLayout = QVBoxLayout()
        self.hintWidget.setLayout(self.hintLayout)

        self.hintEdit = QTextEdit(self)
        self.hintEdit.setText("""
Hint: Enter an expression using column names (ie 'col_a < 10'). 
Combine more complicated expressions with '&' and '|'.
For example '(a < 10) & (b > 1)'\n
Any other numpy expressions also valid - columns are represented as 
numpy arrays.
Use the special column 'row' for the row number.""")

        self.hintEdit.setReadOnly(True)
        # make background gray
        palette = self.hintEdit.palette()
        palette.setColor(QPalette.Base, Qt.lightGray)
        self.hintEdit.setPalette(palette)
        
        self.hintLayout.addWidget(self.hintEdit)

        self.splitter.addWidget(self.hintWidget)
        
        self.splitter.setSizes([1500, 3000, 3000])

        self.applyButton = QPushButton(self)
        self.applyButton.setText("Apply")

        self.closeButton = QPushButton(self)
        self.closeButton.setText("Close")

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.addWidget(self.applyButton)
        self.buttonLayout.addWidget(self.closeButton)

        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.addWidget(self.splitter)
        self.mainLayout.addLayout(self.buttonLayout)
        self.setLayout(self.mainLayout)

        self.closeButton.clicked.connect(self.close)
        self.applyButton.clicked.connect(self.applyExpression)

    def setHint(self, hint):
        "set the hint displayed"
        self.hintEdit.setText(hint)

    def applyExpression(self):
        "Sends a signal with the expression"
        imports = self.importEdit.toPlainText()
        expression = self.exprEdit.toPlainText()
        if self.col is None:
            self.newExpression[str, str].emit(imports, expression)
        else:
            # include column
            self.newExpression[str, str, int].emit(imports, expression, self.col)
