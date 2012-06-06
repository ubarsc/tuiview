
"""
Module that contains the ViewerPreferences class
"""

from PyQt4.QtGui import QDialog, QVBoxLayout, QHBoxLayout, QRadioButton, QFormLayout
from PyQt4.QtGui import QLabel, QPushButton, QCheckBox, QGroupBox, QButtonGroup
from PyQt4.QtGui import QToolButton, QPixmap, QIcon, QColorDialog, QColor
from PyQt4.QtCore import QVariant, QSettings, SIGNAL, Qt

class ColorButton(QToolButton):
    """
    Class that is a button with a icon that displays
    the current color. Clicking the button allows user to change color
    """
    def __init__(self, parent, color):
        QToolButton.__init__(self, parent)
        self.setColor(color)
        self.setToolTip("Change Color")

    def setColor(self, color):
        """
        Create icon and set color
        """
        pixmap = QPixmap(24, 24)
        pixmap.fill(color)
        icon = QIcon(pixmap)
        self.setIcon(icon)
        self.color = color

    def getColor(self):
        "return the current color"
        return self.color

    def mouseReleaseEvent(self, event):
        """
        Handle event - show dialog to allow color to be changed
        """
        QToolButton.mouseReleaseEvent(self, event)
        newcolor = QColorDialog.getColor(self.color, self)
        if newcolor.isValid():
            self.setColor(newcolor)
        

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

        # color settings
        self.colorGroup = QGroupBox("Color Settings")
        self.colorLayout = QFormLayout()
        self.colorNoDataColor = ColorButton(self, self.settingNoDataValue)
        self.colorLayout.addRow("No Data Color", self.colorNoDataColor)
        self.colorBackgroundColor = ColorButton(self, self.settingBackgroundValue)
        self.colorLayout.addRow("Background Color", self.colorBackgroundColor)

        self.colorGroup.setLayout(self.colorLayout)

        self.mainLayout.addWidget(self.colorGroup)

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
        self.settingMouseWheelZoom = settings.value("mousescroll", True).toBool()
        settings.endGroup()

        settings.beginGroup('ViewerColors')
        # this is how to get a QColor out of a QVariant
        self.settingNoDataValue = QColor(settings.value("no data", Qt.black))
        self.settingBackgroundValue = QColor(settings.value("background", Qt.black))
        settings.endGroup()

    def onOK(self):
        """
        Selected OK so save preferences
        """

        self.settingMouseWheelZoom = self.mouseZoom.isChecked()
        self.settingNoDataValue = self.colorNoDataColor.getColor()
        self.settingBackgroundValue = self.colorBackgroundColor.getColor()

        settings = QSettings()
        settings.beginGroup('ViewerMouse')
        settings.setValue("mousescroll", self.settingMouseWheelZoom)
        settings.endGroup()

        settings.beginGroup('ViewerColors')
        settings.setValue("no data", self.settingNoDataValue)
        settings.setValue("background", self.settingBackgroundValue)
        settings.endGroup()

        QDialog.accept(self)
