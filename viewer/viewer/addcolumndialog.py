"""
Contains the AddColumnDialog class
"""

from PyQt4.QtGui import QDialog, QFormLayout, QComboBox, QLineEdit
from PyQt4.QtGui import QPushButton, QHBoxLayout, QVBoxLayout, QMessageBox
from PyQt4.QtCore import QVariant, SIGNAL

from .viewerRAT import NEWCOL_INT, NEWCOL_FLOAT, NEWCOL_STRING

class AddColumnDialog(QDialog):
    """
    Dialog that allows a user to select type of new RAT
    column and enter the name
    """
    def __init__(self, parent):
        QDialog.__init__(self, parent)

        self.typeCombo = QComboBox()
        userdata = QVariant(NEWCOL_INT)
        self.typeCombo.addItem("Integer", userdata)
        userdata = QVariant(NEWCOL_FLOAT)
        self.typeCombo.addItem("Floating Point", userdata)
        userdata = QVariant(NEWCOL_STRING)
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
        if self.nameEdit.text().size() == 0:
            QMessageBox.critical(self, "Viewer", "Must enter column name")
            self.nameEdit.setFocus()
        else:
            self.accept()

    def getColumnType(self):
        index = self.typeCombo.currentIndex()
        userdata = self.typeCombo.itemData(index)
        return userdata.toInt()[0]

    def getColumnName(self):
        return str(self.nameEdit.text())


