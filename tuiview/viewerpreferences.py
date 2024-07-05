
"""
Module that contains the ViewerPreferences class
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
from PySide6.QtWidgets import QPushButton, QGroupBox, QButtonGroup, QLabel
from PySide6.QtWidgets import QSpinBox, QCheckBox
from PySide6.QtGui import QColor
from PySide6.QtCore import QSettings, Qt
from .stretchdialog import ColorButton
from .plotwidget import DEFAULT_FONT_SIZE


class ViewerPreferencesDialog(QDialog):
    """
    Preferences Dialog for the viewer
    """
    def __init__(self, parent):
        QDialog.__init__(self, parent)
        self.setWindowTitle('TuiView Preferences')

        # get the settings
        self.restoreFromSettings()

        self.mainLayout = QVBoxLayout(self)

        # Scroll Wheel
        self.mouseGroup = QGroupBox("Scroll Wheel Behaviour")
        self.mouseLayout = QHBoxLayout()
        self.mouseButtonGroup = QButtonGroup()  # enforces exclusivity
        
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

        # background color
        self.backgroundColorGroup = QGroupBox("Background")
        self.backgroundColorLayout = QHBoxLayout()
        self.backgroundColorLabel = QLabel()
        self.backgroundColorLabel.setText("Background Canvas Color")

        # this seems a bit backward...
        rgbatuple = (self.settingBackgroundColor.red(), 
                self.settingBackgroundColor.blue(),
                self.settingBackgroundColor.green(),
                self.settingBackgroundColor.alpha())
        self.backgroundColorButton = ColorButton(self, rgbatuple)

        self.backgroundColorLayout.addWidget(self.backgroundColorLabel)
        self.backgroundColorLayout.addWidget(self.backgroundColorButton)
        self.backgroundColorGroup.setLayout(self.backgroundColorLayout)

        self.mainLayout.addWidget(self.backgroundColorGroup)

        # plots
        self.plotGroup = QGroupBox("Plots")
        self.plotLayout = QHBoxLayout()
        
        self.plotFontSizeLabel = QLabel()
        self.plotFontSizeLabel.setText("Font Size")
        self.plotFontSizeSpin = QSpinBox()
        self.plotFontSizeSpin.setMinimum(1)
        self.plotFontSizeSpin.setValue(self.settingPlotFontSize)

        self.plotLayout.addWidget(self.plotFontSizeLabel)
        self.plotLayout.addWidget(self.plotFontSizeSpin)
        self.plotGroup.setLayout(self.plotLayout)

        self.mainLayout.addWidget(self.plotGroup)

        # startup
        self.startupGroup = QGroupBox("Startup State")
        self.startupLayout = QVBoxLayout()

        self.startupQueryCheck = QCheckBox("Query only Displayed Layers")
        if self.settingQueryOnlyDisplayed:
            self.startupQueryCheck.setCheckState(Qt.Checked)
        self.startupArrangeLayersCheck = QCheckBox("Open Arrange Layers Window")
        if self.settingArrangeLayersOpen:
            self.startupArrangeLayersCheck.setCheckState(Qt.Checked)

        self.startupLayout.addWidget(self.startupQueryCheck)
        self.startupLayout.addWidget(self.startupArrangeLayersCheck)
        self.startupGroup.setLayout(self.startupLayout)

        self.mainLayout.addWidget(self.startupGroup)

        # ok and cancel buttons
        self.okButton = QPushButton(self)
        self.okButton.setText("OK")
        self.okButton.setDefault(True)
        self.okButton.clicked.connect(self.onOK)

        self.cancelButton = QPushButton(self)
        self.cancelButton.setText("Cancel")
        self.cancelButton.clicked.connect(self.reject)

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.addWidget(self.okButton)
        self.buttonLayout.addWidget(self.cancelButton)

        self.mainLayout.addLayout(self.buttonLayout)
        self.setLayout(self.mainLayout)

        self.resize(400, 300)

    def restoreFromSettings(self):
        """
        Restore any settings from last time
        n.b. need to rationalize with viewerwindow.
        I've kept this in here for now since there is a slight
        advantage in having the setttings re-read in case another
        window has changed them.
        """
        settings = QSettings()

        settings.beginGroup('ViewerMouse')
        value = settings.value("mousescroll", True, bool)
        self.settingMouseWheelZoom = value
        settings.endGroup()

        settings.beginGroup('ViewerBackground')
        value = settings.value("color", QColor(Qt.black), QColor)
        self.settingBackgroundColor = value
        settings.endGroup()

        settings.beginGroup('Plot')
        value = settings.value('FontSize', DEFAULT_FONT_SIZE, int)
        self.settingPlotFontSize = value
        settings.endGroup()

        settings.beginGroup('StartupState')
        value = settings.value('QueryOnlyDisplayed', False, bool)
        self.settingQueryOnlyDisplayed = value

        value = settings.value('ArrangeLayersOpen', False, bool)
        self.settingArrangeLayersOpen = value
        settings.endGroup()

    def onOK(self):
        """
        Selected OK so save preferences
        """

        self.settingMouseWheelZoom = self.mouseZoom.isChecked()
        self.settingBackgroundColor = self.backgroundColorButton.color
        self.settingPlotFontSize = self.plotFontSizeSpin.value()
        self.settingQueryOnlyDisplayed = (
            self.startupQueryCheck.checkState() == Qt.Checked)
        self.settingArrangeLayersOpen = (
            self.startupArrangeLayersCheck.checkState() == Qt.Checked)

        settings = QSettings()
        settings.beginGroup('ViewerMouse')
        settings.setValue("mousescroll", self.settingMouseWheelZoom)
        settings.endGroup()
        settings.beginGroup('ViewerBackground')
        settings.setValue("color", self.settingBackgroundColor)
        settings.endGroup()
        settings.beginGroup('Plot')
        settings.setValue('FontSize', self.settingPlotFontSize)
        settings.endGroup()
        settings.beginGroup('StartupState')
        settings.setValue('QueryOnlyDisplayed', self.settingQueryOnlyDisplayed)
        settings.setValue('ArrangeLayersOpen', self.settingArrangeLayersOpen)
        settings.endGroup()

        QDialog.accept(self)
