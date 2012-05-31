
"""
Module that contains the ViewerPreferences class
"""

from PyQt4.QtGui import QDialog, QVBoxLayout, QHBoxLayout
from PyQt4.QtGui import QLabel, QPushButton, QCheckBox
from PyQt4.QtCore import QVariant, QSettings, SIGNAL


class ViewerPreferencesDialog(QDialog):
    """
    Preferences Dialog for the viewer
    """
    def __init__(self, parent):
        QDialog.__init__(self, parent)
        self.setWindowTitle('Viewer Preferences')

        self.mouseWheelZoom = True
        self.restoreFromSettings()

        self.mainLayout = QVBoxLayout(self)

        self.mouseScrollCheckBox = QCheckBox("Scroll wheel Zooms (or Pans)", self)
        self.mouseScrollCheckBox.setChecked(True)
        self.mainLayout.addWidget(self.mouseScrollCheckBox)

        self.okButton = QPushButton(self)
        self.okButton.setText("OK")
        self.okButton.setDefault(True)
        self.connect(self.okButton, SIGNAL("clicked()"), self.onOK)

        self.cancelButton = QPushButton(self)
        self.cancelButton.setText("Cancel")
        self.connect(self.cancelButton, SIGNAL("clicked()"), self.reject)

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.addWidget(self.okButton)
        self.buttonLayout.addWidget(self.cancelButton)

        self.mainLayout.addLayout(self.buttonLayout)

    def restoreFromSettings(self):
        """
        Restore any settings from last time
        """
        settings = QSettings()

        settings.beginGroup('ViewerMouse')
        self.mouseWheelZoom = True
        self.mouseWheelZoom = settings.value("mousescroll", self.mouseWheelZoom)
        settings.endGroup()

    def onOK(self):
        """
        Selected OK so save preferences
        """

        self.mouseWheelZoom = self.mouseScrollCheckBox.isChecked()

        print "mouse scroll: ", self.mouseWheelZoom

        settings = QSettings()
        settings.beginGroup('ViewerMouse')
        settings.setValue("mousescroll", self.mouseWheelZoom)
        settings.endGroup()

        QDialog.accept(self)
