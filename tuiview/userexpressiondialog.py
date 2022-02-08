
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

from PyQt5.QtWidgets import QTextEdit
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt5.QtGui import QPalette
from PyQt5.QtCore import pyqtSignal, Qt


class UserExpressionDialog(QDialog):
    """
    Allows user to enter a expression and have it applied.
    Sends a signal with the expresson on Apply
    """
    # signals
    newExpression = pyqtSignal(['QString'], ['QString', int], 
                        name='newExpression')
    # not used?
    undoEdit = pyqtSignal('QObject', int, name='undoEdit')

    def __init__(self, parent, col=None, undoObject=None):
        QDialog.__init__(self, parent)
        # if this is not none col included in signal
        self.col = col 
        # if this is not none an undo button will be created
        # and an undo signal sent
        self.undoObject = undoObject

        self.setWindowTitle("Enter Expression")

        self.exprEdit = QTextEdit(self)
        self.exprEdit.setAcceptRichText(False)

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

        self.applyButton = QPushButton(self)
        self.applyButton.setText("Apply")

        self.closeButton = QPushButton(self)
        self.closeButton.setText("Close")

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.addWidget(self.applyButton)
        
        # if we have something to undo add a button
        if undoObject is not None:
            self.undoButton = QPushButton(self)
            self.undoButton.setText("Undo")
            self.buttonLayout.addWidget(self.undoButton)
            self.undoButton.clicked.connect(self.undo)

        self.buttonLayout.addWidget(self.closeButton)

        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.addWidget(self.exprEdit)
        self.mainLayout.addWidget(self.hintEdit)
        self.mainLayout.addLayout(self.buttonLayout)
        self.setLayout(self.mainLayout)

        self.closeButton.clicked.connect(self.close)
        self.applyButton.clicked.connect(self.applyExpression)

    def setHint(self, hint):
        "set the hint displayed"
        self.hintEdit.setText(hint)

    def applyExpression(self):
        "Sends a signal with the expression"
        expression = self.exprEdit.toPlainText()
        if self.col is None:
            self.newExpression['QString'].emit(expression)
        else:
            # include column
            self.newExpression['QString', int].emit(expression, self.col)

    def undo(self):
        "sends a signal with the undo object"
        self.undoEdit.emit(self.undoObject, self.col)
