"""
Module that contains the PropertiesWindow class
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

from PyQt4.QtGui import QDialog, QVBoxLayout, QPushButton, QTextEdit
from PyQt4.QtCore import SIGNAL

class PropertiesWindow(QDialog):
    def __init__(self, parent, text):
        QDialog.__init__(self, parent)

        self.mainLayout = QVBoxLayout()
        self.textEdit = QTextEdit()
        self.textEdit.setPlainText(text)
        self.textEdit.setReadOnly(True)

        self.mainLayout.addWidget(self.textEdit)

        self.closeButton = QPushButton()
        self.closeButton.setText("Close")
        self.connect(self.closeButton, SIGNAL("clicked()"), self.accept)

        self.mainLayout.addWidget(self.closeButton)

        self.setLayout(self.mainLayout)
        self.resize(500, 600)
        
