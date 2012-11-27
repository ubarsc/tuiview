
"""
Module that contains the StretchLayout, RuleLayout
and StretchDefaultsDialog classes
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

from PyQt4.QtGui import QDialog, QFormLayout, QGridLayout, QVBoxLayout, QIcon
from PyQt4.QtGui import QHBoxLayout, QComboBox, QToolBar, QAction, QLabel
from PyQt4.QtGui import QPushButton, QGroupBox, QDockWidget
from PyQt4.QtGui import QTabWidget, QWidget, QSpinBox, QDoubleSpinBox
from PyQt4.QtGui import QToolButton, QPixmap, QColorDialog, QColor, QMessageBox
from PyQt4.QtCore import QVariant, QSettings, SIGNAL, Qt
import json

from . import viewerstretch
from . import pseudocolor

# strings for the combo boxes and their values
MODE_DATA = (("Color Table", viewerstretch.VIEWER_MODE_COLORTABLE),
                ("Greyscale", viewerstretch.VIEWER_MODE_GREYSCALE),
                ("PseudoColor", viewerstretch.VIEWER_MODE_PSEUDOCOLOR),
                ("RGB", viewerstretch.VIEWER_MODE_RGB))

STRETCH_DATA = (("None", viewerstretch.VIEWER_STRETCHMODE_NONE),
                ("Linear", viewerstretch.VIEWER_STRETCHMODE_LINEAR),
                ("Standard Deviation", viewerstretch.VIEWER_STRETCHMODE_STDDEV),
                ("Histogram", viewerstretch.VIEWER_STRETCHMODE_HIST))

DEFAULT_STRETCH_KEY = 'DefaultStretch'

MAX_BAND_NUMBER = 100 # for spin boxes

class ColorButton(QToolButton):
    """
    Class that is a button with a icon that displays
    the current color. Clicking the button allows user to change color
    """
    def __init__(self, parent, rgbatuple):
        QToolButton.__init__(self, parent)
        color = QColor(rgbatuple[0], rgbatuple[1], 
                        rgbatuple[2], rgbatuple[3])
        self.setColor(color)
        self.setToolTip("Change Color")

    def setColor(self, color):
        """
        Create icon and set color
        """
        # set the alpha channel to be 255 for display
        # by default it is 0 and no color is shown
        iconcolor = QColor(color)
        iconcolor.setAlpha(255)

        pixmap = QPixmap(24, 24)
        pixmap.fill(iconcolor)

        icon = QIcon(pixmap)
        self.setIcon(icon)
        self.color = color

    def getColorAsRGBATuple(self):
        "return the current color"
        r = self.color.red()
        g = self.color.green()
        b = self.color.blue()
        a = self.color.alpha()
        return (r, g, b, a)

    def mouseReleaseEvent(self, event):
        """
        Handle event - show dialog to allow color to be changed
        """
        QToolButton.mouseReleaseEvent(self, event)
        newcolor = QColorDialog.getColor(self.color, self, "Choose Color", 
                            QColorDialog.ShowAlphaChannel)
        if newcolor.isValid():
            self.setColor(newcolor)
        

class StretchLayout(QFormLayout):
    """
    Layout that contains the actual stretch information
    """
    def __init__(self, parent, stretch, gdaldataset=None):
        QFormLayout.__init__(self)

        # the mode
        self.modeCombo = QComboBox(parent)
        index = 0
        for text, code in MODE_DATA:
            self.modeCombo.addItem(text, QVariant(code))
            if code == stretch.mode:
                self.modeCombo.setCurrentIndex(index)
            index += 1

        # callback so we can set the state of other items when changed
        self.connect(self.modeCombo, SIGNAL("currentIndexChanged(int)"), 
                            self.modeChanged)

        self.rampCombo = QComboBox(parent)

        # make sure the pseudocolor has the extra ramps loaded
        try:
            pseudocolor.loadExtraRamps()
        except Exception, e:
            QMessageBox.critical(parent, "Viewer", str(e))

        # populate combo - sort by type
        index = 0
        for (name, display) in pseudocolor.getRampsForDisplay():
            userdata = QVariant(name)
            self.rampCombo.addItem(display, userdata)
            if stretch.rampName is not None and stretch.rampName == name:
                self.rampCombo.setCurrentIndex(index)
            index += 1

        # set ramp state depending on if we are pseudo color or not
        state = stretch.mode == viewerstretch.VIEWER_MODE_PSEUDOCOLOR
        self.rampCombo.setEnabled(state)

        self.modeLayout = QHBoxLayout()
        self.modeLayout.addWidget(self.modeCombo)
        self.modeLayout.addWidget(self.rampCombo)

        self.addRow("Mode", self.modeLayout)

        if gdaldataset is None:
            # we don't have a dateset - is a rule
            # create spin boxes for the bands
            self.createSpinBands(stretch.bands, parent)
        else:
            # we have a dataset. create combo
            # boxes with the band names
            self.createComboBands(stretch.bands, gdaldataset, parent)

        # set the bands depending on if we are RGB or not
        if stretch.mode == viewerstretch.VIEWER_MODE_RGB:
            self.redWidget.setToolTip("Red")
            self.greenWidget.setToolTip("Green")
            self.blueWidget.setToolTip("Blue")
        else:
            self.redWidget.setToolTip("Displayed Band")
            self.greenWidget.setEnabled(False)
            self.blueWidget.setEnabled(False)

        self.addRow("Bands", self.bandLayout)

        # create the combo for the type of stretch
        self.stretchLayout = QHBoxLayout()
        self.stretchCombo = QComboBox(parent)
        index = 0
        for text, code in STRETCH_DATA:
            self.stretchCombo.addItem(text, QVariant(code))
            if code == stretch.stretchmode:
                self.stretchCombo.setCurrentIndex(index)
            index += 1
        # callback so we can set the state of other items when changed
        self.connect(self.stretchCombo, SIGNAL("currentIndexChanged(int)"), 
                        self.stretchChanged)

        self.stretchLayout.addWidget(self.stretchCombo)

        # create the spin boxes for the std devs or hist min and max
        self.stretchParam1 = QDoubleSpinBox(parent)
        self.stretchParam1.setDecimals(3)
        self.stretchParam2 = QDoubleSpinBox(parent)
        self.stretchParam2.setDecimals(3)
        self.stretchLayout.addWidget(self.stretchParam1)
        self.stretchLayout.addWidget(self.stretchParam2)

        if stretch.stretchmode == viewerstretch.VIEWER_STRETCHMODE_STDDEV:
            self.stretchParam2.setEnabled(False)
            self.stretchParam1.setRange(0, 10)
            self.stretchParam1.setSingleStep(0.1)
            self.stretchParam1.setValue(stretch.stretchparam[0])
            self.stretchParam1.setToolTip("Number of Standard Deviations")
        elif stretch.stretchmode == viewerstretch.VIEWER_STRETCHMODE_HIST:
            self.stretchParam1.setRange(0, 1)
            self.stretchParam1.setSingleStep(0.005)
            self.stretchParam1.setValue(stretch.stretchparam[0])
            self.stretchParam1.setToolTip("Minimum Proportion of Histogram")
            self.stretchParam2.setRange(0, 1)
            self.stretchParam2.setSingleStep(0.005)
            self.stretchParam2.setValue(stretch.stretchparam[1])
            self.stretchParam2.setToolTip("Maximum Proportion of Histogram")
        elif stretch.stretchmode == viewerstretch.VIEWER_STRETCHMODE_LINEAR:
            self.stretchParam1.setRange(-1, 65535)
            self.stretchParam1.setSingleStep(1)
            self.stretchParam1.setSpecialValueText("Statistics Min")
            # need to do something cleverer here with the special value
            if stretch.stretchparam[0] is None:
                self.stretchParam1.setValue(-1)
            else:
                self.stretchParam1.setValue(stretch.stretchparam[0])
            self.stretchParam1.setToolTip("Minimum Value")

            self.stretchParam2.setRange(-1, 65535)
            self.stretchParam2.setSingleStep(1)
            self.stretchParam2.setSpecialValueText("Statistics Max")
            if stretch.stretchparam[1] is None:
                self.stretchParam2.setValue(-1)
            else:
                self.stretchParam2.setValue(stretch.stretchparam[1])
            self.stretchParam2.setToolTip("Maximum Value")
        else:
            self.stretchParam1.setEnabled(False)
            self.stretchParam2.setEnabled(False)

        self.addRow("Stretch", self.stretchLayout)
        state = stretch.mode != viewerstretch.VIEWER_MODE_COLORTABLE
        self.stretchCombo.setEnabled(state)

        # now for no data, background and NaN
        self.fixedColorLayout = QHBoxLayout()
        self.nodataLabel = QLabel(parent)
        self.nodataLabel.setText("No Data")
        self.fixedColorLayout.addWidget(self.nodataLabel)
        self.fixedColorLayout.setAlignment(self.nodataLabel, Qt.AlignRight)
        self.nodataButton = ColorButton(parent, stretch.nodata_rgba)
        self.fixedColorLayout.addWidget(self.nodataButton)

        self.backgroundLabel = QLabel(parent)
        self.backgroundLabel.setText("Background")
        self.fixedColorLayout.addWidget(self.backgroundLabel)
        self.fixedColorLayout.setAlignment(self.backgroundLabel, Qt.AlignRight)
        self.backgroundButton = ColorButton(parent, stretch.background_rgba)
        self.fixedColorLayout.addWidget(self.backgroundButton)

        self.NaNLabel = QLabel(parent)
        self.NaNLabel.setText("NaN")
        self.fixedColorLayout.addWidget(self.NaNLabel)
        self.fixedColorLayout.setAlignment(self.NaNLabel, Qt.AlignRight)
        self.NaNButton = ColorButton(parent, stretch.nan_rgba)
        self.fixedColorLayout.addWidget(self.NaNButton)

        self.addRow("Fixed Colors", self.fixedColorLayout)

    def createSpinBands(self, bands, parent):
        """
        For the case where we are creating a rule
        we have no band names so create spin boxes
        """
        # create the 3 band spin boxes
        self.bandLayout = QHBoxLayout()
        self.redWidget = QSpinBox(parent)
        self.redWidget.setRange(1, MAX_BAND_NUMBER)
        self.bandLayout.addWidget(self.redWidget)

        self.greenWidget = QSpinBox(parent)
        self.greenWidget.setRange(1, MAX_BAND_NUMBER)
        self.bandLayout.addWidget(self.greenWidget)

        self.blueWidget = QSpinBox(parent)
        self.blueWidget.setRange(1, MAX_BAND_NUMBER)
        self.bandLayout.addWidget(self.blueWidget)

        # set them depending on if we are RGB or not
        if len(bands) == 3:
            (r, g, b) = bands
            self.redWidget.setValue(r)
            self.greenWidget.setValue(g)
            self.blueWidget.setValue(b)
        else:
            self.redWidget.setValue(bands[0])

    def createComboBands(self, bands, gdaldataset, parent):
        """
        We have a dataset - create combo boxes with the band names
        """
        self.bandLayout = QHBoxLayout()
        self.redWidget = QComboBox(parent)
        self.bandLayout.addWidget(self.redWidget)

        self.greenWidget = QComboBox(parent)
        self.bandLayout.addWidget(self.greenWidget)

        self.blueWidget = QComboBox(parent)
        self.bandLayout.addWidget(self.blueWidget)

        # set them depending on if we are RGB or not
        if len(bands) == 3:
            (r, g, b) = bands
        else:
            (r, g, b) = (bands[0], 1, 1)

        self.populateComboFromDataset(self.redWidget, gdaldataset, r)
        self.populateComboFromDataset(self.greenWidget, gdaldataset, g)
        self.populateComboFromDataset(self.blueWidget, gdaldataset, b)

    def populateComboFromDataset(self, combo, gdaldataset, currentBand=1):
        """
        Go through all the bands in the dataset and add a combo
        item for each one. Set the current index to the currentBand
        """
        for count in range(gdaldataset.RasterCount):
            bandnum = count + 1
            gdalband = gdaldataset.GetRasterBand(bandnum)
            name = gdalband.GetDescription()
            combo.addItem(name, QVariant(bandnum))

        combo.setCurrentIndex(currentBand - 1)

    @staticmethod
    def getBandValue(widget):
        """
        Depending on whether widget it a spinbox
        or a combo box extract the current value for it.
        """
        if isinstance(widget, QSpinBox):
            value = widget.value()
        else:
            index = widget.currentIndex()
            var = widget.itemData(index)
            value = var.toInt()[0]
        return value

    def getStretch(self):
        """
        Return a ViewerStretch object that reflects
        the current state of the GUI
        """
        obj = viewerstretch.ViewerStretch()
        index = self.modeCombo.currentIndex()
        obj.mode = self.modeCombo.itemData(index).toInt()[0]

        bands = []
        value = self.getBandValue(self.redWidget)
        bands.append(value)
        if obj.mode == viewerstretch.VIEWER_MODE_RGB:
            value = self.getBandValue(self.greenWidget)
            bands.append(value)
            value = self.getBandValue(self.blueWidget)
            bands.append(value)
        obj.setBands(tuple(bands))

        if obj.mode == viewerstretch.VIEWER_MODE_PSEUDOCOLOR:
            idx = self.rampCombo.currentIndex()
            rampName = self.rampCombo.itemData(idx)
            rampName = rampName.toString()
            obj.setPseudoColor(str(rampName))

        index = self.stretchCombo.currentIndex()
        obj.stretchmode = self.stretchCombo.itemData(index).toInt()[0]
        if obj.stretchmode == viewerstretch.VIEWER_STRETCHMODE_STDDEV:
            value = self.stretchParam1.value()
            obj.setStdDevStretch(value)
        elif obj.stretchmode == viewerstretch.VIEWER_STRETCHMODE_HIST:
            histmin = self.stretchParam1.value()
            histmax = self.stretchParam2.value()
            obj.setHistStretch(histmin, histmax)
        elif obj.stretchmode == viewerstretch.VIEWER_STRETCHMODE_LINEAR:
            # need to do something cleverer here with the special value
            minVal = self.stretchParam1.value()
            if minVal == -1:
                minVal = None
            maxVal = self.stretchParam2.value()
            if maxVal == -1:
                maxVal = None
            obj.setLinearStretch(minVal, maxVal)

        obj.setNoDataRGBA(self.nodataButton.getColorAsRGBATuple())
        obj.setBackgroundRGBA(self.backgroundButton.getColorAsRGBATuple())
        obj.setNaNRGBA(self.NaNButton.getColorAsRGBATuple())

        return obj

    def modeChanged(self, index):
        """
        Called when user changed the mode. 
        Updates other GUI elements as needed
        """
        mode = self.modeCombo.itemData(index).toInt()[0]
        greenredEnabled = (mode == viewerstretch.VIEWER_MODE_RGB)
        self.greenWidget.setEnabled(greenredEnabled)
        self.blueWidget.setEnabled(greenredEnabled)
        if greenredEnabled:
            self.redWidget.setToolTip("Red")
            self.greenWidget.setToolTip("Green")
            self.blueWidget.setToolTip("Blue")
        else:
            self.redWidget.setToolTip("Displayed Band")
            self.greenWidget.setToolTip("")
            self.blueWidget.setToolTip("")

        if mode == viewerstretch.VIEWER_MODE_COLORTABLE:
            # need to set stretch to none
            self.stretchCombo.setCurrentIndex(0)
        state = mode != viewerstretch.VIEWER_MODE_COLORTABLE
        self.stretchCombo.setEnabled(state)

        state = mode == viewerstretch.VIEWER_MODE_PSEUDOCOLOR
        self.rampCombo.setEnabled(state)

    def stretchChanged(self, index):
        """
        Called when user changed the stretch. 
        Updates other GUI elements as needed
        """
        stretchmode = self.stretchCombo.itemData(index).toInt()[0]
        if stretchmode == viewerstretch.VIEWER_STRETCHMODE_STDDEV:
            self.stretchParam1.setEnabled(True)
            self.stretchParam2.setEnabled(False)
            self.stretchParam1.setRange(0, 10)
            self.stretchParam1.setSingleStep(0.1)
            # always set back to this default
            self.stretchParam1.setValue(viewerstretch.VIEWER_DEFAULT_STDDEV) 
            self.stretchParam1.setToolTip("Number of Standard Deviations")
            self.stretchParam2.setToolTip("")
            self.stretchParam1.setSpecialValueText("")
            self.stretchParam2.setSpecialValueText("")
        elif stretchmode == viewerstretch.VIEWER_STRETCHMODE_HIST:
            self.stretchParam1.setEnabled(True)
            self.stretchParam2.setEnabled(True)
            self.stretchParam1.setRange(0, 1)
            self.stretchParam1.setSingleStep(0.005)
            self.stretchParam1.setToolTip("Minimum Proportion of Histogram")
            self.stretchParam2.setRange(0, 1)
            self.stretchParam2.setSingleStep(0.005)
            self.stretchParam2.setToolTip("Maximum Proportion of Histogram")
            # set back to these defaults
            self.stretchParam1.setValue(viewerstretch.VIEWER_DEFAULT_HISTMIN) 
            self.stretchParam2.setValue(viewerstretch.VIEWER_DEFAULT_HISTMAX)
            self.stretchParam1.setSpecialValueText("")
            self.stretchParam2.setSpecialValueText("")
        elif stretchmode == viewerstretch.VIEWER_STRETCHMODE_LINEAR:
            self.stretchParam1.setEnabled(True)
            self.stretchParam2.setEnabled(True)
            self.stretchParam1.setRange(-1, 65535)
            self.stretchParam1.setSingleStep(1)
            self.stretchParam1.setToolTip("Minimum Value")
            self.stretchParam2.setRange(-1, 65535)
            self.stretchParam2.setSingleStep(1)
            self.stretchParam2.setToolTip("Maximum Value")
            self.stretchParam1.setValue(-1) # set back to these defaults
            self.stretchParam2.setValue(-1)
            # need to do something cleverer here with the special value
            self.stretchParam1.setSpecialValueText("Statistics Min")
            self.stretchParam2.setSpecialValueText("Statistics Max")
        else:
            self.stretchParam1.setEnabled(False)
            self.stretchParam2.setEnabled(False)
            self.stretchParam1.setToolTip("")
            self.stretchParam2.setToolTip("")


RULE_DATA = (("Number of Bands Less than", viewerstretch.VIEWER_COMP_LT),
                ("Number of Bands Greater than", viewerstretch.VIEWER_COMP_GT),
                ("Number of Bands Equal to", viewerstretch.VIEWER_COMP_EQ))

class RuleLayout(QGridLayout):
    """
    Layout that contains the 'rules'. These are 
    the number of bands, the comparison with the
    number of bands and the check for a color table
    """
    def __init__(self, parent, rule):
        QGridLayout.__init__(self)            

        # the comaprison combo
        self.compCombo = QComboBox(parent)
        index = 0
        for text, code in RULE_DATA:
            variant = QVariant(code)
            self.compCombo.addItem(text, variant)
            if code == rule.comp:
                self.compCombo.setCurrentIndex(index)
            index += 1
        self.addWidget(self.compCombo, 0, 0)

        # the number of bands spinbox
        self.numberBox = QSpinBox(parent)
        self.numberBox.setRange(1, 100)
        self.numberBox.setValue(rule.value)
        self.addWidget(self.numberBox, 0, 1)

        # the label for the color table rule
        self.colorTableLabel = QLabel(parent)
        self.colorTableLabel.setText("Color Table in Band")
        self.addWidget(self.colorTableLabel, 1, 0)

        # color table band spinbox
        self.colorTableBox = QSpinBox(parent)
        self.colorTableBox.setRange(0, 100)
        self.colorTableBox.setSpecialValueText('No color table required')
        if rule.ctband is None:
            self.colorTableBox.setValue(0)
        else:
            self.colorTableBox.setValue(rule.ctband)
        self.addWidget(self.colorTableBox, 1, 1)

    def getRule(self):
        """
        Return a StretchRule instance for the current GUI
        settings
        Note: the stretch field will be None
        """
        index = self.compCombo.currentIndex()
        comp = self.compCombo.itemData(index).toInt()[0]
        value = self.numberBox.value()
        ctband = self.colorTableBox.value()
        if ctband == 0:
            ctband = None # no color table required

        obj = viewerstretch.StretchRule(comp, value, ctband, None)
        return obj

class StretchDefaultsDialog(QDialog):
    """
    Dialog that contains a Tabs, each one describing a rule
    and is a combination of RuleLayout and StretchLayout
    """
    def __init__(self, parent):
        QDialog.__init__(self, parent)

        # create a tab widget with its tabs on the left
        self.tabWidget = QTabWidget(self)
        self.tabWidget.setTabPosition(QTabWidget.West)

        # grab the rules from the setting
        # this supplies some default rules if none
        ruleList = self.fromSettings()
        count = 1
        # go through each rule
        for rule in ruleList:
            # create a widget for it
            widget = self.createWidget(rule, rule.stretch)

            # add the widget as a new tab
            name = "Rule %d" % count
            self.tabWidget.addTab(widget, name)
            count += 1

        # now sort out the rest of the dialog
        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.addWidget(self.tabWidget)

        # new and delete buttons
        self.newBeforeButton = QPushButton(self)
        self.newBeforeButton.setText("New Rule Before")
        self.connect(self.newBeforeButton, SIGNAL("clicked()"), 
                            self.onNewBefore)

        self.newAfterButton = QPushButton(self)
        self.newAfterButton.setText("New Rule After")
        self.connect(self.newAfterButton, SIGNAL("clicked()"), self.onNewAfter)

        self.deleteRuleButton = QPushButton(self)
        self.deleteRuleButton.setText("Delete This Rule")
        if len(ruleList) <= 1:
            self.deleteRuleButton.setEnabled(False)
        self.connect(self.deleteRuleButton, SIGNAL("clicked()"), self.onDelete)

        self.newDeleteLayout = QHBoxLayout()
        self.newDeleteLayout.addWidget(self.newBeforeButton)
        self.newDeleteLayout.addWidget(self.newAfterButton)
        self.newDeleteLayout.addWidget(self.deleteRuleButton)

        self.mainLayout.addLayout(self.newDeleteLayout)

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

        self.setWindowTitle("Default Stretch")
        self.setSizeGripEnabled(True)
        self.resize(600, 400)

    def createWidget(self, rule, stretch):
        "create a widget that contains the rule/stretch"
        widget = QWidget()
    
        # create the rule layout and put it into a group box
        widget.ruleLayout = RuleLayout(widget, rule)
        widget.ruleGroup = QGroupBox('Rule')
        widget.ruleGroup.setLayout(widget.ruleLayout)

        # create the stretch layout and put it into a group box
        widget.stretchLayout = StretchLayout(widget, stretch)
        widget.stretchGroup = QGroupBox("Stretch")
        widget.stretchGroup.setLayout(widget.stretchLayout)

        # create a layout for the group boxes
        widget.mainLayout = QVBoxLayout(widget)
        widget.mainLayout.addWidget(widget.ruleGroup)
        widget.mainLayout.addWidget(widget.stretchGroup)

        # set the layout
        widget.setLayout(widget.mainLayout)

        return widget

    @staticmethod
    def fromSettings():
        """
        Read the default stretch rules from the 
        settings and return a list of StretchRules.
        Supplies a default set of rules if none found.
        """
        settings = QSettings()
        settings.beginGroup('Stretch')

        ruleList = []

        defaultRulesJSON = settings.value(DEFAULT_STRETCH_KEY)
        if defaultRulesJSON.isNull():
            # there isn't one, construct some defaults
            stretch = viewerstretch.ViewerStretch()

            # single band with color table
            stretch.setColorTable()
            stretch.setBands((1,))
            # must be one band and band one must have a color table
            rule = viewerstretch.StretchRule(
                        viewerstretch.VIEWER_COMP_EQ, 1, 1, stretch)
            ruleList.append(rule)

            # single band without color table
            stretch.setGreyScale()
            rule = viewerstretch.StretchRule( 
                        viewerstretch.VIEWER_COMP_EQ, 1, None, stretch)
            ruleList.append(rule)

            # 2 bands
            rule = viewerstretch.StretchRule( 
                        viewerstretch.VIEWER_COMP_EQ, 2, None, stretch)
            ruleList.append(rule)
            
            # 3 bands
            stretch.setRGB()
            stretch.setNoStretch()
            stretch.setBands((1, 2, 3))
            rule = viewerstretch.StretchRule(
                        viewerstretch.VIEWER_COMP_EQ, 3, None, stretch)
            ruleList.append(rule)

            # < 6 bands
            stretch.setStdDevStretch()
            stretch.setBands((4, 3, 2))
            rule = viewerstretch.StretchRule(
                        viewerstretch.VIEWER_COMP_LT, 6, None, stretch)
            ruleList.append(rule)

            # > 5 bands
            stretch.setBands((5, 4, 2))
            rule = viewerstretch.StretchRule(
                        viewerstretch.VIEWER_COMP_GT, 5, None, stretch)
            ruleList.append(rule)

        else:
            # is a list of json strings
            defaultRulesJSON = str(defaultRulesJSON.toString())
            for string in json.loads(defaultRulesJSON):
                # go through each one (which is itself a json string)
                # and decode into a StretchRule
                rule = viewerstretch.StretchRule.fromString(string)
                ruleList.append(rule)

        settings.endGroup()
        return ruleList

    def toSettings(self):
        """
        Write the contents of the dialog as the
        default rules to be remembered for next time. 
        """
        settings = QSettings()
        settings.beginGroup('Stretch')

        # go through each tab and turn
        # rules into JSON string and append to list
        defaultRulesList = []
        nwidgets = self.tabWidget.count()
        for index in range(nwidgets):
            widget = self.tabWidget.widget(index)
            stretch = widget.stretchLayout.getStretch()
            rule = widget.ruleLayout.getRule()
            rule.stretch = stretch
            
            string = rule.toString()
            defaultRulesList.append(string)

        # turn list into a json string and write to settings
        JSONstring = json.dumps(defaultRulesList)
        settings.setValue(DEFAULT_STRETCH_KEY, JSONstring)

        settings.endGroup()
        
    def renumberTabs(self):
        """
        A tab has been added or deleted so renumber
        the tabs
        """
        ntabs = self.tabWidget.count()
        for index in range(ntabs):
            name = "Rule %d" % (index + 1)
            self.tabWidget.setTabText(index, name)

    def onOK(self):
        """
        OK button pressed. Save settings
        """
        self.toSettings()
        QDialog.accept(self)

    def onNewBefore(self):
        """
        The 'add new page before' button pressed. 
        Add a new page in with the rule/stretch
        same as current page
        """
        # get the current page and rule/stretch
        currentWidget = self.tabWidget.currentWidget()
        currentIndex = self.tabWidget.currentIndex()
        rule = currentWidget.ruleLayout.getRule()
        stretch = currentWidget.stretchLayout.getStretch()

        # create a new tab
        newWidget = self.createWidget(rule, stretch)
        self.tabWidget.setUpdatesEnabled(False) # reduce flicker
        self.tabWidget.insertTab(currentIndex, newWidget, "new rule")
        self.deleteRuleButton.setEnabled(True)
        self.renumberTabs() # make sure the numbers in order
        self.tabWidget.setUpdatesEnabled(True) # reduce flicker

    def onNewAfter(self):
        """
        The 'add new page after' button pressed. 
        Add a new page in with the rule/stretch
        same as current page
        """
        # get the current page and rule/stretch
        currentWidget = self.tabWidget.currentWidget()
        currentIndex = self.tabWidget.currentIndex()
        rule = currentWidget.ruleLayout.getRule()
        stretch = currentWidget.stretchLayout.getStretch()

        # create a new tab
        newWidget = self.createWidget(rule, stretch)
        self.tabWidget.setUpdatesEnabled(False) # reduce flicker
        self.tabWidget.insertTab(currentIndex + 1, newWidget, "new rule")
        self.deleteRuleButton.setEnabled(True)
        self.renumberTabs() # make sure the numbers in order
        self.tabWidget.setUpdatesEnabled(True) # reduce flicker

    def onDelete(self):
        """
        Delete the current page.
        """
        currentIndex = self.tabWidget.currentIndex()
        self.tabWidget.setUpdatesEnabled(False) # reduce flicker
        self.tabWidget.removeTab(currentIndex)
        
        if self.tabWidget.count() <= 1:
            self.deleteRuleButton.setEnabled(False)
        self.renumberTabs()
        self.tabWidget.setUpdatesEnabled(True) # reduce flicker

class StretchDockWidget(QDockWidget):
    """
    Class that has a StretchLayout as a dockable window
    with apply and save buttons
    """
    def __init__(self, parent, viewwidget, layer):
        QDockWidget.__init__(self, "Stretch", parent)
        # save the view widget
        self.viewwidget = viewwidget
        self.layer = layer
        self.parent = parent

        # create a new widget that lives in the dock window
        self.dockWidget = QWidget()

        # create the toolbar
        self.toolBar = QToolBar(self.dockWidget)
        self.setupActions()
        self.setupToolbar()

        # our stretch layout
        self.stretchLayout = StretchLayout(self.dockWidget, 
                    self.layer.stretch, self.layer.gdalDataset)

        # layout for stretch and buttons
        self.mainLayout = QVBoxLayout()
        self.mainLayout.addWidget(self.toolBar)
        self.mainLayout.addLayout(self.stretchLayout)

        self.dockWidget.setLayout(self.mainLayout)

        # tell the dock window this is the widget to display
        self.setWidget(self.dockWidget)

    def setupActions(self):
        """
        Create the actions to be shown on the toolbar
        """
        self.applyAction = QAction(self)
        self.applyAction.setText("&Apply Stretch")
        self.applyAction.setStatusTip("Apply Stretch")
        self.applyAction.setIcon(QIcon(":/viewer/images/apply.png"))
        self.connect(self.applyAction, SIGNAL("triggered()"), self.onApply)

        self.saveAction = QAction(self)
        self.saveAction.setText("&Save Stretch")
        self.saveAction.setStatusTip("Save Stretch to File")
        self.saveAction.setIcon(QIcon(":/viewer/images/save.png"))
        self.connect(self.saveAction, SIGNAL("triggered()"), self.onSave)

        self.deleteAction = QAction(self)
        self.deleteAction.setText("&Delete Stretch")
        self.deleteAction.setStatusTip("Delete Stretch from File")
        self.deleteAction.setIcon(QIcon(":/viewer/images/deletesaved.png"))
        self.connect(self.deleteAction, SIGNAL("triggered()"), self.onDelete)

        self.localAction = QAction(self)
        self.localAction.setText("&Local Stretch")
        tip = "Calculate approximate local stretch on Apply"
        self.localAction.setStatusTip(tip)
        self.localAction.setIcon(QIcon(":/viewer/images/local.png"))
        self.localAction.setCheckable(True)
        

    def setupToolbar(self):
        """
        Add the actions to the toolbar
        """
        self.toolBar.addAction(self.applyAction)
        self.toolBar.addAction(self.saveAction)
        self.toolBar.addAction(self.deleteAction)
        self.toolBar.addAction(self.localAction)

    def onApply(self):
        """
        Apply the new stretch to the view widget
        """
        stretch = self.stretchLayout.getStretch()
        local = self.localAction.isChecked()
        try:
            self.viewwidget.setNewStretch(stretch, self.layer, local)
        except Exception as e:
            QMessageBox.critical(self, "Viewer", str(e) )

    def onSave(self):
        """
        User wants to save the stretch to the file
        """
        stretch = self.stretchLayout.getStretch()

        try:
            
            self.layer.saveStretchToFile(stretch)
            self.parent.showStatusMessage("Stretch written to file")
        except Exception as e:
            QMessageBox.critical(self, "Viewer", str(e))

    def onDelete(self):
        """
        Delete any stretch/LUT from the file
        """
        try:
            self.layer.deleteStretchFromFile()
            self.parent.showStatusMessage("Stretch deleted from file")
        except Exception as e:
            QMessageBox.critical(self, "Viewer", str(e))

