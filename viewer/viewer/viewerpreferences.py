
"""
Module that contains the ViewerPreferences class
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

from PyQt4.QtGui import QDialog, QVBoxLayout, QHBoxLayout, QRadioButton
from PyQt4.QtGui import QPushButton, QGroupBox, QButtonGroup
from PyQt4.QtCore import QSettings, SIGNAL

class ViewerPreferencesDialog(QDialog):
    """
    Preferences Dialog for the viewer
    """
    def __init__(self, parent):
        QDialog.__init__(self, parent)
        self.setWindowTitle('Viewer Preferences')

        # get the settings
        self.restoreFromSettings()

        self.mainLayout = QVBoxLayout(self)

        # Scroll Wheel
        self.mouseGroup = QGroupBox("Scroll Wheel Behaviour")
        self.mouseLayout = QHBoxLayout()
        self.mouseButtonGroup = QButtonGroup() # enforces exclusivity
        
        self.mouseZoom = QRadioButton("Zooms")
        self.mousePan = QRadioButton("Pans")
        self.mouseButtonGroup.addButton(self.mouseZoom)
        self.mouseButtonGroup.addButton(self.mousePan)

        self.mouseLayout.addWidget(self.mouseZoom)
        self.mouseLayout.addWidget(self.mousePan)
        self.mouseGroup.setLayout(self.mouseLayout)
        
        self.mainLayout.addWidget(self.mouseGroup)

        # from settings
        if self.settingMouseWheelZoom:
            self.mouseZoom.setChecked(True)
        else:
            self.mousePan.setChecked(True)

        # ok and cancel buttons
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

        self.resize(400, 300)

    def restoreFromSettings(self):
        """
        Restore any settings from last time
        """
        settings = QSettings()

        settings.beginGroup('ViewerMouse')
        value = settings.value("mousescroll", True)
        self.settingMouseWheelZoom = value.toBool()
        settings.endGroup()

    def onOK(self):
        """
        Selected OK so save preferences
        """

        self.settingMouseWheelZoom = self.mouseZoom.isChecked()

        settings = QSettings()
        settings.beginGroup('ViewerMouse')
        settings.setValue("mousescroll", self.settingMouseWheelZoom)
        settings.endGroup()

        QDialog.accept(self)
