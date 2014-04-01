
"""
Module that contains the PlotScalingDialog class
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

from PyQt4.QtGui import QDialog, QFormLayout, QHBoxLayout, QCheckBox
from PyQt4.QtGui import QSpinBox, QDoubleSpinBox, QPushButton, QVBoxLayout
from PyQt4.QtCore import Qt, SIGNAL
import numpy

class PlotScalingDialog(QDialog):
    """
    Dialog that allows the user to set the scale for the X axis
    """
    def __init__(self, parent, currentScale, data):
        QDialog.__init__(self, parent)

        minScale, maxScale = currentScale

        self.setWindowTitle("Plot Scaling")

        self.formLayout = QFormLayout()

        self.minAutoCheck = QCheckBox()
        self.minAutoCheck.setText("Auto")

        floatingPoint = numpy.issubdtype(data.dtype, numpy.floating)
        if floatingPoint:
            info = numpy.finfo(data.dtype)
        else:
            info = numpy.iinfo(data.dtype)

        if floatingPoint:
            self.minValueSpin = QDoubleSpinBox()
            self.minValueSpin.setRange(info.min, info.max)
        else:
            self.minValueSpin = QSpinBox()
            self.minValueSpin.setRange(info.min, info.max)
        self.connect(self.minAutoCheck, SIGNAL("stateChanged(int)"), 
                    self.onMinAuto)

        if minScale is None:
            self.minAutoCheck.setCheckState(Qt.Checked)
            self.minValueSpin.setEnabled(False)
            self.minValueSpin.setValue(data.min())
        else:
            self.minValueSpin.setValue(minScale)

        self.minLayout = QVBoxLayout()
        self.minLayout.addWidget(self.minAutoCheck)
        self.minLayout.addWidget(self.minValueSpin)
        self.formLayout.addRow("Minimum Value:", self.minLayout)

        self.maxAutoCheck = QCheckBox()
        self.maxAutoCheck.setText("Auto")

        if floatingPoint:
            self.maxValueSpin = QDoubleSpinBox()
            self.maxValueSpin.setRange(info.min, info.max)
        else:
            self.maxValueSpin = QSpinBox()
            self.maxValueSpin.setRange(info.min, info.max)
        self.connect(self.maxAutoCheck, SIGNAL("stateChanged(int)"), 
                    self.onMaxAuto)

        if maxScale is None:
            self.maxAutoCheck.setCheckState(Qt.Checked)
            self.maxValueSpin.setEnabled(False)
            self.maxValueSpin.setValue(data.max())
        else:
            self.maxValueSpin.setValue(maxScale)

        self.maxLayout = QVBoxLayout()
        self.maxLayout.addWidget(self.maxAutoCheck)
        self.maxLayout.addWidget(self.maxValueSpin)
        self.formLayout.addRow("Maximum Value:", self.maxLayout)

        self.okButton = QPushButton()
        self.okButton.setText("OK")
        self.connect(self.okButton, SIGNAL("clicked()"), self.accept)

        self.cancelButton = QPushButton()
        self.cancelButton.setText("Cancel")
        self.connect(self.cancelButton, SIGNAL("clicked()"), self.reject)

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.addWidget(self.okButton)
        self.buttonLayout.addWidget(self.cancelButton)

        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.addLayout(self.formLayout)
        self.mainLayout.addLayout(self.buttonLayout)
        self.setLayout(self.mainLayout)

    def onMaxAuto(self, state):
        "Called when auto state changed"
        self.maxValueSpin.setEnabled(state != Qt.Checked)
        
    def onMinAuto(self, state):
        "Called when auto state changed"
        self.minValueSpin.setEnabled(state != Qt.Checked)

    def getScale(self):
        """
        Return the tupe of min, max scaling. None for Auto
        """
        if self.minAutoCheck.isChecked():
            minValue = None
        else:
            minValue = self.minValueSpin.value()

        if self.maxAutoCheck.isChecked():
            maxValue = None
        else:
            maxValue = self.maxValueSpin.value()
        
        return (minValue, maxValue)
