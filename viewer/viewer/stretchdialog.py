
from PyQt4.QtGui import QDialog, QFormLayout, QGridLayout, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton, QGroupBox, QTabWidget, QWidget
from PyQt4.QtCore import QVariant, QSettings, SIGNAL

from . import viewerLUT

MODE_DATA = (("Color Table", viewerLUT.VIEWER_MODE_COLORTABLE),
                ("Greyscale", viewerLUT.VIEWER_MODE_GREYSCALE),
                ("RGB", viewerLUT.VIEWER_MODE_RGB))

STRETCH_DATA = (("None", viewerLUT.VIEWER_STRETCHMODE_NONE),
                ("Linear", viewerLUT.VIEWER_STRETCHMODE_LINEAR),
                ("Standard Deviation", viewerLUT.VIEWER_STRETCHMODE_STDDEV),
                ("Histogram", viewerLUT.VIEWER_STRETCHMODE_HIST))

class StretchLayout(QFormLayout):
    def __init__(self, parent, nbands, stretch):
        QFormLayout.__init__(self)
        self.modeCombo = QComboBox(parent)
        index = 0
        for text, code in MODE_DATA:
            self.modeCombo.addItem(text, QVariant(code))
            if code == stretch.mode:
                self.modeCombo.setCurrentIndex(index)
            index += 1

        self.connect(self.modeCombo, SIGNAL("currentIndexChanged(int)"), self.modeChanged)

        self.addRow("Mode", self.modeCombo)

        self.bandLayout = QHBoxLayout()
        self.redCombo = QComboBox(parent)
        self.bandLayout.addWidget(self.redCombo)

        self.greenCombo = QComboBox(parent)
        self.bandLayout.addWidget(self.greenCombo)

        self.blueCombo = QComboBox(parent)
        self.bandLayout.addWidget(self.blueCombo)

        for n in range(nbands):
            band = n + 1
            text = "%s" % band
            variant = QVariant(band)
            self.redCombo.addItem(text, variant)
            self.greenCombo.addItem(text, variant)
            self.blueCombo.addItem(text, variant)

        if stretch.mode == viewerLUT.VIEWER_MODE_RGB:
            (r, g, b) = stretch.bands
            self.redCombo.setCurrentIndex(r - 1)
            self.greenCombo.setCurrentIndex(g - 1)
            self.blueCombo.setCurrentIndex(b - 1)
        else:
            self.redCombo.setCurrentIndex(stretch.bands[0] - 1)
            self.greenCombo.setEnabled(False)
            self.blueCombo.setEnabled(False)

        self.addRow("Bands", self.bandLayout)

        self.stretchCombo = QComboBox(parent)
        index = 0
        for text, code in STRETCH_DATA:
            self.stretchCombo.addItem(text, QVariant(code))
            if code == stretch.stretchmode:
                self.stretchCombo.setCurrentIndex(index)
            index += 1

        self.addRow("Stretch", self.stretchCombo)
        self.stretchCombo.setEnabled(stretch.mode != viewerLUT.VIEWER_MODE_COLORTABLE)

        self.stretch = stretch

    def getStretch(self):
        index = self.modeCombo.currentIndex()
        self.stretch.mode = self.modeCombo.itemData(index).toInt()[0]

        bands = []
        index = self.redCombo.currentIndex()
        band = self.redCombo.itemData(index).toInt()[0]
        bands.append(band)
        if self.stretch.mode == viewerLUT.VIEWER_MODE_RGB:
            index = self.greenCombo.currentIndex()
            band = self.greenCombo.itemData(index).toInt()[0]
            bands.append(band)
            index = self.blueCombo.currentIndex()
            band = self.blueCombo.itemData(index).toInt()[0]
            bands.append(band)
        self.stretch.bands = bands

        index = self.stretchCombo.currentIndex()
        self.stretch.stretchmode = self.stretchCombo.itemData(index).toInt()[0]
        return self.stretch

    def modeChanged(self, index):
        mode = self.modeCombo.itemData(index).toInt()[0]
        greenredEnabled = (mode == viewerLUT.VIEWER_MODE_RGB)
        self.greenCombo.setEnabled(greenredEnabled)
        self.blueCombo.setEnabled(greenredEnabled)

        if mode == viewerLUT.VIEWER_MODE_COLORTABLE:
            # need to set stretch to none
            self.stretchCombo.setCurrentIndex(0)
        self.stretchCombo.setEnabled(mode != viewerLUT.VIEWER_MODE_COLORTABLE)
            

class StretchDefaultsDialog(QDialog):
    def __init__(self, parent):
        QDialog.__init__(self, parent)

        self.tabWidget = QTabWidget(self)
        self.defaultList = self.fromSettings()
        self.widgetList = []
        for stretch in self.defaultList:
            widget = QWidget()
            widget.layout = StretchLayout(widget, stretch.nbands, stretch)
            widget.setLayout(widget.layout)
            self.tabWidget.addTab(widget, stretch.name)
            self.widgetList.append(widget)

        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.addWidget(self.tabWidget)

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

        self.setWindowTitle("Default Stretch")
        self.setSizeGripEnabled(True)
        self.resize(600,400)

    @staticmethod
    def getDefaultStretch(settings, code, name, bands, nbands, ct, default):
        defaultstr = default.toString(bands=bands, name=name)
        str = settings.value(code, defaultstr).toString()
        obj = viewerLUT.ViewerStretch.fromString(str)
        obj.nbands = nbands
        obj.ct = ct
        obj.code = code
        return obj

    @staticmethod
    def fromSettings():

        settings = QSettings()
        settings.beginGroup('DefaultStretch')

        defaultList = []

        # single band with color table
        default = viewerLUT.ViewerStretch()
        default.setColorTable()
        obj = StretchDefaultsDialog.getDefaultStretch(settings, "1 ct", 
                            "1 Band with Color Table", (1,), 1, True, default)
        defaultList.append(obj)

        # single band without color table
        default.setGreyScale()
        obj = StretchDefaultsDialog.getDefaultStretch(settings, 
                            "1", "1 Band", (1,), 1, False, default)
        defaultList.append(obj)

        # 2 bands
        obj = StretchDefaultsDialog.getDefaultStretch(settings, 
                            "2", "2 Bands", (1,), 2, False, default)
        defaultList.append(obj)

        # 3 bands
        default.setRGB()
        default.setNoStretch()
        obj = StretchDefaultsDialog.getDefaultStretch(settings, 
                            "3", "3 Bands", (3,2,1), 3, False, default)
        defaultList.append(obj)

        # 4 bands
        default.setRGB()
        default.setStdDevStretch()
        obj = StretchDefaultsDialog.getDefaultStretch(settings, 
                            "4", "4 Bands", (4,3,2), 4, False, default)
        defaultList.append(obj)

        # 5 bands
        obj = StretchDefaultsDialog.getDefaultStretch(settings, 
                            "5", "5 Bands", (4,3,2), 5, False, default)
        defaultList.append(obj)

        # 6 bands
        obj = StretchDefaultsDialog.getDefaultStretch(settings, 
                            "6", "6 Bands", (5,4,2), 6, False, default)
        defaultList.append(obj)

        # >6 bands
        obj = StretchDefaultsDialog.getDefaultStretch(settings, 
                            ">6", ">6 Bands", (5,4,2), 6, False, default)
        defaultList.append(obj)

        settings.endGroup()
        return defaultList

    def toSettings(self):
        settings = QSettings()
        settings.beginGroup('DefaultStretch')

        for widget in self.widgetList:
            layout = widget.layout
            stretch = layout.getStretch()
            string = stretch.toString(bands=stretch.bands, name=stretch.name)
            settings.setValue(stretch.code, string)

        settings.endGroup()
        

    def onOK(self):
        self.toSettings()
        QDialog.accept(self)


