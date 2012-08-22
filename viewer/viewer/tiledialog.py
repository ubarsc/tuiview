
"""
Contains the TileDialog class
"""

from PyQt4.QtGui import QDialog, QFormLayout, QHBoxLayout, QPushButton
from PyQt4.QtGui import QSpinBox, QPushButton
from PyQt4.QtCore import SIGNAL

class TileDialog(QDialog):
    """
    Dialog that allows user to select how many viewers across and down 
    they want (or auto)
    """
    def __init__(self, parent):
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

        self.connect(self.okButton, SIGNAL("clicked()"), self.accept)
        self.connect(self.cancelButton, SIGNAL("clicked()"), self.reject)

    def getValues(self):
        "Returns the x and y value as a tuple"
        return self.xspin.value(), self.yspin.value()
