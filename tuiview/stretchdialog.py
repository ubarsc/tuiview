
"""
Module that contains the StretchLayout, RuleLayout
and StretchDefaultsDialog classes
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

import os
import json
from PySide6.QtWidgets import QDialog, QFormLayout, QGridLayout, QVBoxLayout
from PySide6.QtWidgets import QHBoxLayout, QComboBox, QToolBar, QLabel
from PySide6.QtWidgets import QPushButton, QGroupBox, QDockWidget, QFileDialog
from PySide6.QtWidgets import QTabWidget, QWidget, QSpinBox, QDoubleSpinBox, QCheckBox
from PySide6.QtWidgets import QToolButton, QColorDialog, QMessageBox
from PySide6.QtGui import QIcon, QPixmap, QColor, QAction
from PySide6.QtCore import QSettings, Qt

from . import viewerstretch
from . import pseudocolor
from .viewerstrings import MESSAGE_TITLE
from . import viewerwindow

# strings for the combo boxes and their values
MODE_DATA = (("Color Table", viewerstretch.VIEWER_MODE_COLORTABLE),
    ("Greyscale", viewerstretch.VIEWER_MODE_GREYSCALE),
    ("PseudoColor", viewerstretch.VIEWER_MODE_PSEUDOCOLOR),
    ("RGB", viewerstretch.VIEWER_MODE_RGB))

STRETCH_DATA = (("None", viewerstretch.VIEWER_STRETCHMODE_NONE),
    ("Linear", viewerstretch.VIEWER_STRETCHMODE_LINEAR),
    ("Linear bands vary", viewerstretch.VIEWER_STRETCHMODE_LINEAR_VAR),
    ("Standard Deviation", viewerstretch.VIEWER_STRETCHMODE_STDDEV),
    ("Standard Deviation bands vary", viewerstretch.VIEWER_STRETCHMODE_STDDEV_VAR),
    ("Histogram", viewerstretch.VIEWER_STRETCHMODE_HIST),
    ("Histogram bands vary", viewerstretch.VIEWER_STRETCHMODE_HIST_VAR))

DEFAULT_STRETCH_KEY = 'DefaultStretch'

MAX_BAND_NUMBER = 100  # for spin boxes

STRETCH_FILTER = ".stretch Files (*.stretch)"


class ColorButton(QToolButton):
    """
    Class that is a button with a icon that displays
    the current color. Clicking the button allows user to change color
    """
    def __init__(self, parent, rgbatuple=None):
        QToolButton.__init__(self, parent)
        if rgbatuple is not None:
            color = QColor(rgbatuple[0], rgbatuple[1], 
                rgbatuple[2], rgbatuple[3])
        else:
            color = QColor(0, 0, 0, 0)
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

    def setColorAsRGBATuple(self, rgbatuple):
        "set the color as RGBA"
        color = QColor(rgbatuple[0], rgbatuple[1], 
            rgbatuple[2], rgbatuple[3])
        self.setColor(color)

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
        for text, code in MODE_DATA:
            self.modeCombo.addItem(text, code)

        # callback so we can set the state of other items when changed
        self.modeCombo.currentIndexChanged.connect(self.modeChanged)

        self.rampCombo = QComboBox(parent)

        # make sure the pseudocolor has the extra ramps loaded
        try:
            pseudocolor.loadExtraRamps()
        except Exception as e:
            QMessageBox.critical(parent, MESSAGE_TITLE, str(e))

        # populate combo - sort by type
        for (name, display) in pseudocolor.getRampsForDisplay():
            self.rampCombo.addItem(display, name)

        self.modeLayout = QHBoxLayout()
        self.modeLayout.addWidget(self.modeCombo)
        self.modeLayout.addWidget(self.rampCombo)

        self.addRow("Mode", self.modeLayout)

        if gdaldataset is None:
            # we don't have a dateset - is a rule
            # create spin boxes for the bands
            self.createSpinBands(parent)
        else:
            # we have a dataset. create combo
            # boxes with the band names
            self.createComboBands(gdaldataset, parent)

        self.addRow("Bands", self.bandLayout)
        
        # the parameters of the stretch
        self.paramsLayout = QHBoxLayout()
        
        self.paramsMinLayout = QVBoxLayout()
        self.paramsMinList = []
        for n in range(4):
            spin_box = QDoubleSpinBox(parent)
            spin_box.setDecimals(3)
            self.paramsMinLayout.addWidget(spin_box)
            stats = QCheckBox(parent)
            stats.setText("Statistics Min")
            stats.stateChanged.connect(self.statsChanged)
            self.paramsMinLayout.addWidget(stats)
            self.paramsMinList.append((spin_box, stats))

        self.paramsMaxLayout = QVBoxLayout()
        self.paramsMaxList = []
        for n in range(4):
            spin_box = QDoubleSpinBox(parent)
            spin_box.setDecimals(3)
            self.paramsMaxLayout.addWidget(spin_box)
            stats = QCheckBox(parent)
            stats.setText("Statistics Max")
            stats.stateChanged.connect(self.statsChanged)
            self.paramsMaxLayout.addWidget(stats)
            self.paramsMaxList.append((spin_box, stats))
            
        self.paramsLayout.addWidget(self.paramsMinLayout)
        self.paramsLayout.addWidget(self.paramsMaxLayout)
        self.addRow("Stretch Params", self.paramsLayout)
        
        # create the combo for the type of stretch
        self.stretchLayout = QHBoxLayout()
        self.stretchCombo = QComboBox(parent)
        for text, code in STRETCH_DATA:
            self.stretchCombo.addItem(text, code)
        # callback so we can set the state of other items when changed
        self.stretchCombo.currentIndexChanged.connect(self.stretchChanged)

        self.stretchLayout.addWidget(self.stretchCombo)

        # now for no data, background and NaN
        self.nodataLabel = QLabel(parent)
        self.nodataLabel.setText("No Data")
        self.fixedColorLayout.addWidget(self.nodataLabel)
        self.fixedColorLayout.setAlignment(self.nodataLabel, Qt.AlignRight)
        self.nodataButton = ColorButton(parent)
        self.stretchLayout.addWidget(self.nodataButton)

        self.backgroundLabel = QLabel(parent)
        self.backgroundLabel.setText("Background")
        self.fixedColorLayout.addWidget(self.backgroundLabel)
        self.fixedColorLayout.setAlignment(self.backgroundLabel, Qt.AlignRight)
        self.backgroundButton = ColorButton(parent)
        self.stretchLayout.addWidget(self.backgroundButton)

        self.NaNLabel = QLabel(parent)
        self.NaNLabel.setText("NaN")
        self.fixedColorLayout.addWidget(self.NaNLabel)
        self.fixedColorLayout.setAlignment(self.NaNLabel, Qt.AlignRight)
        self.NaNButton = ColorButton(parent)
        self.stretchLayout.addWidget(self.NaNButton)

        self.addRow("Stretch", self.stretchLayout)

        # set state of GUI for this stretch
        self.updateStretch(stretch)

    def statsChanged(self, state):
        """
        Called when the 'Statistics Min' or Max box is checked
        """
        for spin_box, stats in self.paramsMinList:
            spin_box.setEnabled(stats.checkState() != Qt.Checked)
        for spin_box, stats in self.paramsMaxList:
            spin_box.setEnabled(stats.checkState() != Qt.Checked)

    def updateStretch(self, stretch):
        """
        Change the state of the GUI to match the given stretch
        """
        # the mode
        idx = self.modeCombo.findData(stretch.mode)
        if idx != -1:
            self.modeCombo.setCurrentIndex(idx)

        # ramp
        if stretch.rampName is not None:
            idx = self.rampCombo.findData(stretch.rampName)
            if idx != -1:
                self.rampCombo.setCurrentIndex(idx)

        # set ramp state depending on if we are pseudo color or not
        state = stretch.mode == viewerstretch.VIEWER_MODE_PSEUDOCOLOR
        self.rampCombo.setEnabled(state)

        # set the bands depending on if we are RGB/RGBA or not
        if stretch.mode == viewerstretch.VIEWER_MODE_RGB:
            self.redWidget.setToolTip("Red")
            self.greenWidget.setToolTip("Green")
            self.blueWidget.setToolTip("Blue")
            (r, g, b) = stretch.bands
            if isinstance(self.redWidget, QSpinBox):
                self.redWidget.setValue(r)
                self.greenWidget.setValue(g)
                self.blueWidget.setValue(b)
            else:
                self.redWidget.setCurrentIndex(r - 1)
                self.greenWidget.setCurrentIndex(g - 1)
                self.blueWidget.setCurrentIndex(b - 1)
            self.alphaWidget.setEnabled(False)
            
        elif stretch.mode == viewerstretch.VIEWER_MODE_RGBA:
            self.redWidget.setToolTip("Red")
            self.greenWidget.setToolTip("Green")
            self.blueWidget.setToolTip("Blue")
            self.alphaWidget.setToolTip("Alpha")
            (r, g, b, a) = stretch.bands
            if isinstance(self.redWidget, QSpinBox):
                self.redWidget.setValue(r)
                self.greenWidget.setValue(g)
                self.blueWidget.setValue(b)
                self.alphaWidget.setValue(a)
            else:
                self.redWidget.setCurrentIndex(r - 1)
                self.greenWidget.setCurrentIndex(g - 1)
                self.blueWidget.setCurrentIndex(b - 1)
                self.alphaWidget.setCurrentIndex(a - 1)
            self.alphaWidget.setEnabled(True)

        else:
            self.redWidget.setToolTip("Displayed Band")
            self.greenWidget.setEnabled(False)
            self.blueWidget.setEnabled(False)
            self.alphaWidget.setEnabled(False)

            if isinstance(self.redWidget, QSpinBox):
                self.redWidget.setValue(stretch.bands[0])
            else:
                self.redWidget.setCurrentIndex(stretch.bands[0] - 1)

        # stretch mode
        idx = self.stretchCombo.findData(stretch.stretchmode)
        if idx != -1:
            self.stretchCombo.setCurrentIndex(idx)

        state = stretch.mode != viewerstretch.VIEWER_MODE_COLORTABLE
        self.stretchCombo.setEnabled(state)

        # Set up GUI
        self.setStretchMode(stretch.stretchmode, stretch.stretchparams)

        # nodata etc
        self.nodataButton.setColorAsRGBATuple(stretch.nodata_rgba)
        self.backgroundButton.setColorAsRGBATuple(stretch.background_rgba)
        self.NaNButton.setColorAsRGBATuple(stretch.nan_rgba)
        
    def setStretchMode(stretchmode, stretchparam=None):
        """
        Used by updateStretch() and stretchChanged() to update the GUI for the stretch
        if stretchparam is None, then the stretch defaults are used
        """
        if stretchmode == viewerstretch.VIEWER_STRETCHMODE_STDDEV:
            spin_box, stats in self.paramsMinList[0]
            spin_box.setRange(0, 10)
            spin_box.setSingleStep(0.1)
            stats.setCheckState(Qt.Unchecked)
            stats.setEnabled(False)
            if stretchparams is not None:
                spin_box.setValue(stretchparam[0])
            else:
                spin_box.setValue(viewerstretch.VIEWER_DEFAULT_STDDEV)
            spin_box.setToolTip("Number of Standard Deviations")
            
            for spin_box, stats in self.paramsMinList[1:]:
                spin_box.setEnabled(False)
                stats.setCheckState(Qt.Unchecked)
                stats.setEnabled(False)

            for spin_box, stats in self.paramsMaxList:
                spin_box.setEnabled(False)
                stats.setCheckState(Qt.Unchecked)
                stats.setEnabled(False)

        if stretchmode == viewerstretch.VIEWER_STRETCHMODE_STDDEV_VAR:
            
            if stretchparam is None:
                stretchparam = [None] * len(self.paramsMinList) 
            for stddev, (spin_box, stats) in zip(stretchparam, self.paramsMinList):
                spin_box.setEnabled(True)
                spin_box.setRange(0, 10)
                spin_box.setSingleStep(0.1)
                spin_box.setToolTip("Number of Standard Deviations")
                stats.setCheckState(Qt.Unchecked)
                stats.setEnabled(False)
                if stddev is not None:
                    spin_box.setValue(stddev)
                else:
                    spin_box.setValue(viewerstretch.VIEWER_DEFAULT_STDDEV)

            for spin_box, stats in self.paramsMaxList:
                spin_box.setEnabled(False)
                state.setCheckState(Qt.Unchecked)
                state.setEnabled(False)

        elif stretch.stretchmode == viewerstretch.VIEWER_STRETCHMODE_HIST:
            spin_box, stats in self.paramsMinList[0]
            spin_box.setEnabled(True)
            spin_box.setRange(0, 1)
            spin_box.setSingleStep(0.005)
            if stretchparam is not None:
                spin_box.setValue(stretchparam[0])
            else:
                spin_box.setValue(viewerstretch.VIEWER_DEFAULT_HISTMIN)
            spin_box.setToolTip("Minimum Proportion of Histograms")
            
            for spin_box, stats in self.paramsMinList[1:]:
                spin_box.setEnabled(False)
                state.setCheckState(Qt.Unchecked)
                state.setEnabled(False)

            spin_box, stats in self.paramsMaxList[0]
            spin_box.setRange(0, 1)
            spin_box.setSingleStep(0.005)
            if stretchparam is not None:
                spin_box.setValue(stretchparam[1])
            else:
                spin_box.setValue(viewerstretch.VIEWER_DEFAULT_HISTMAX)
            spin_box.setToolTip("Maximum Proportion of Histograms")
            
            for spin_box, stats in self.paramsMaxList[1:]:
                spin_box.setEnabled(False)
                state.setCheckState(Qt.Unchecked)
                state.setEnabled(False)

        elif stretch.stretchmode == viewerstretch.VIEWER_STRETCHMODE_HIST_VAR:

            if stretchparam is None:
                stretchparam = [(None, None)] * len(self.paramsMinList) 

            for (minVal, maxVal), (spin_box, stats) in zip(stretchparam, self.paramsMinList):
                spin_box.setEnabled(True)
                spin_box.setRange(0, 10)
                spin_box.setSingleStep(0.1)
                spin_box.setToolTip("Ninimum Proportion of Histograms")
                if minVal is None:
                    state.setCheckState(Qt.Checked)
                else:
                    state.setCheckState(Qt.Unchecked)
                    spin_box.setValue(minVal)

            for (minVal, maxVal), (spin_box, stats) in zip(stretch.stretchparam, self.paramsMaxList):
                spin_box.setEnabled(True)
                spin_box.setRange(0, 10)
                spin_box.setSingleStep(0.1)
                spin_box.setToolTip("Number of Standard Deviations")
                if maxVal is None:
                    state.setCheckState(Qt.Checked)
                else:
                    state.setCheckState(Qt.Unchecked)
                    spin_box.setValue(maxVal)

        elif stretch.stretchmode == viewerstretch.VIEWER_STRETCHMODE_LINEAR:
            self.stretchParam1Stats.setEnabled(True)
            self.stretchParam2Stats.setEnabled(True)
            self.stretchParam1.setRange(-2**32, 2**32)
            self.stretchParam1.setSingleStep(1)

            if stretch.stretchparam[0] is None:
                self.stretchParam1Stats.setCheckState(Qt.Checked)
            else:
                self.stretchParam1.setValue(stretch.stretchparam[0])
                self.stretchParam1Stats.setCheckState(Qt.Unchecked)
            self.stretchParam1.setToolTip("Minimum Value")

            self.stretchParam2.setRange(-2**32, 2**32)
            self.stretchParam2.setSingleStep(1)

            if stretch.stretchparam[1] is None:
                self.stretchParam2Stats.setCheckState(Qt.Checked)
            else:
                self.stretchParam2.setValue(stretch.stretchparam[1])
                self.stretchParam2Stats.setCheckState(Qt.Unchecked)

            self.stretchParam2.setToolTip("Maximum Value")
        else:
            # no stretch
            self.stretchParam1.setEnabled(False)
            self.stretchParam2.setEnabled(False)
            self.stretchParam1Stats.setCheckState(Qt.Unchecked)
            self.stretchParam2Stats.setCheckState(Qt.Unchecked)
            self.stretchParam1Stats.setEnabled(False)
            self.stretchParam2Stats.setEnabled(False)
            self.stretchParam1.setToolTip("")
            self.stretchParam2.setToolTip("")
        

    def createSpinBands(self, parent):
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
        
        self.alphaWidget = QSpinBox(parent)
        self.alphaWidget.setRange(1, MAX_BAND_NUMBER)
        self.bandLayout.addWidget(self.alphaWidget)

    def createComboBands(self, gdaldataset, parent):
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

        self.alphaWidget = QComboBox(parent)
        self.bandLayout.addWidget(self.alphaWidget)

        self.populateComboFromDataset(self.redWidget, gdaldataset)
        self.populateComboFromDataset(self.greenWidget, gdaldataset)
        self.populateComboFromDataset(self.blueWidget, gdaldataset)
        self.populateComboFromDataset(self.alphaWidget, gdaldataset)

    def populateComboFromDataset(self, combo, gdaldataset):
        """
        Go through all the bands in the dataset and add a combo
        item for each one. Set the current index to the currentBand
        """
        for count in range(gdaldataset.RasterCount):
            bandnum = count + 1
            gdalband = gdaldataset.GetRasterBand(bandnum)
            name = gdalband.GetDescription()
            if name == '':
                # make up a name so the user can still choose
                name = 'Band %d' % bandnum
            combo.addItem(name, bandnum)

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
            value = var
        return value

    def getStretch(self):
        """
        Return a ViewerStretch object that reflects
        the current state of the GUI
        """
        obj = viewerstretch.ViewerStretch()
        index = self.modeCombo.currentIndex()
        obj.mode = self.modeCombo.itemData(index)

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
            obj.setPseudoColor(str(rampName))

        index = self.stretchCombo.currentIndex()
        obj.stretchmode = self.stretchCombo.itemData(index)
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
            if self.stretchParam1Stats.checkState() == Qt.Checked:
                minVal = None
            maxVal = self.stretchParam2.value()
            if self.stretchParam2Stats.checkState() == Qt.Checked:
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
        mode = self.modeCombo.itemData(index)
        greenredEnabled = mode == viewerstretch.VIEWER_MODE_RGB
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
        stretchmode = self.stretchCombo.itemData(index)
        if stretchmode == viewerstretch.VIEWER_STRETCHMODE_STDDEV:
            self.stretchParam1.setEnabled(True)
            self.stretchParam2.setEnabled(False)
            self.stretchParam1Stats.setCheckState(Qt.Unchecked)
            self.stretchParam2Stats.setCheckState(Qt.Unchecked)
            self.stretchParam1Stats.setEnabled(False)
            self.stretchParam2Stats.setEnabled(False)
            self.stretchParam1.setRange(0, 10)
            self.stretchParam1.setSingleStep(0.1)
            # always set back to this default
            self.stretchParam1.setValue(viewerstretch.VIEWER_DEFAULT_STDDEV) 
            self.stretchParam1.setToolTip("Number of Standard Deviations")
            self.stretchParam2.setToolTip("")
        elif stretchmode == viewerstretch.VIEWER_STRETCHMODE_HIST:
            self.stretchParam1.setEnabled(True)
            self.stretchParam2.setEnabled(True)
            self.stretchParam1Stats.setCheckState(Qt.Unchecked)
            self.stretchParam2Stats.setCheckState(Qt.Unchecked)
            self.stretchParam1Stats.setEnabled(False)
            self.stretchParam2Stats.setEnabled(False)
            self.stretchParam1.setRange(0, 1)
            self.stretchParam1.setSingleStep(0.005)
            self.stretchParam1.setToolTip("Minimum Proportion of Histogram")
            self.stretchParam2.setRange(0, 1)
            self.stretchParam2.setSingleStep(0.005)
            self.stretchParam2.setToolTip("Maximum Proportion of Histogram")
            # set back to these defaults
            self.stretchParam1.setValue(viewerstretch.VIEWER_DEFAULT_HISTMIN) 
            self.stretchParam2.setValue(viewerstretch.VIEWER_DEFAULT_HISTMAX)
        elif stretchmode == viewerstretch.VIEWER_STRETCHMODE_LINEAR:
            self.stretchParam1.setEnabled(True)
            self.stretchParam2.setEnabled(True)
            self.stretchParam1Stats.setEnabled(True)
            self.stretchParam2Stats.setEnabled(True)
            self.stretchParam1.setRange(-2**32, 2**32)
            self.stretchParam1.setSingleStep(1)
            self.stretchParam1.setToolTip("Minimum Value")
            self.stretchParam2.setRange(-2**32, 2**32)
            self.stretchParam2.setSingleStep(1)
            self.stretchParam2.setToolTip("Maximum Value")
            self.stretchParam1.setValue(0)  # set back to these defaults
            self.stretchParam2.setValue(0)
            self.stretchParam1Stats.setCheckState(Qt.Checked)
            self.stretchParam2Stats.setCheckState(Qt.Checked)
        else:
            self.stretchParam1.setEnabled(False)
            self.stretchParam2.setEnabled(False)
            self.stretchParam1Stats.setCheckState(Qt.Unchecked)
            self.stretchParam2Stats.setCheckState(Qt.Unchecked)
            self.stretchParam1Stats.setEnabled(False)
            self.stretchParam2Stats.setEnabled(False)
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
            self.compCombo.addItem(text, code)
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
        comp = self.compCombo.itemData(index)
        value = self.numberBox.value()
        ctband = self.colorTableBox.value()
        if ctband == 0:
            ctband = None  # no color table required

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
        self.newBeforeButton.clicked.connect(self.onNewBefore)

        self.newAfterButton = QPushButton(self)
        self.newAfterButton.setText("New Rule After")
        self.newAfterButton.clicked.connect(self.onNewAfter)

        self.deleteRuleButton = QPushButton(self)
        self.deleteRuleButton.setText("Delete This Rule")
        if len(ruleList) <= 1:
            self.deleteRuleButton.setEnabled(False)
        self.deleteRuleButton.clicked.connect(self.onDelete)

        self.newDeleteLayout = QHBoxLayout()
        self.newDeleteLayout.addWidget(self.newBeforeButton)
        self.newDeleteLayout.addWidget(self.newAfterButton)
        self.newDeleteLayout.addWidget(self.deleteRuleButton)

        self.mainLayout.addLayout(self.newDeleteLayout)

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

        if defaultRulesJSON is None or defaultRulesJSON == '':
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
            stretch.setStdDevStretch()
            rule = viewerstretch.StretchRule( 
                viewerstretch.VIEWER_COMP_EQ, 1, None, stretch)
            ruleList.append(rule)

            # 2 bands
            rule = viewerstretch.StretchRule( 
                viewerstretch.VIEWER_COMP_EQ, 2, None, stretch)
            ruleList.append(rule)
            
            # 3 bands
            stretch.setRGB()
            stretch.setBands((1, 2, 3))
            rule = viewerstretch.StretchRule(
                viewerstretch.VIEWER_COMP_EQ, 3, None, stretch)
            ruleList.append(rule)

            # < 6 bands
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
        self.tabWidget.setUpdatesEnabled(False)  # reduce flicker
        self.tabWidget.insertTab(currentIndex, newWidget, "new rule")
        self.deleteRuleButton.setEnabled(True)
        self.renumberTabs()  # make sure the numbers in order
        self.tabWidget.setUpdatesEnabled(True)  # reduce flicker

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
        self.tabWidget.setUpdatesEnabled(False)  # reduce flicker
        self.tabWidget.insertTab(currentIndex + 1, newWidget, "new rule")
        self.deleteRuleButton.setEnabled(True)
        self.renumberTabs()  # make sure the numbers in order
        self.tabWidget.setUpdatesEnabled(True)  # reduce flicker

    def onDelete(self):
        """
        Delete the current page.
        """
        currentIndex = self.tabWidget.currentIndex()
        self.tabWidget.setUpdatesEnabled(False)  # reduce flicker
        self.tabWidget.removeTab(currentIndex)
        
        if self.tabWidget.count() <= 1:
            self.deleteRuleButton.setEnabled(False)
        self.renumberTabs()
        self.tabWidget.setUpdatesEnabled(True)  # reduce flicker


class StretchDockWidget(QDockWidget):
    """
    Class that has a StretchLayout as a dockable window
    with apply and save buttons
    """
    def __init__(self, parent, viewwidget, layer):
        title = "Stretch: %s" % layer.title
        QDockWidget.__init__(self, title, parent)
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

        # make sure we get notified if the layers change so
        # we can close if needed
        viewwidget.layers.layersChanged.connect(self.onLayersChanged)

    def onLayersChanged(self):
        """
        Called when the layers have changed. If the one we 'belong' to
        no longer exists then close this window
        """
        if self.layer not in self.viewwidget.layers.layers:
            self.close()

    def setupActions(self):
        """
        Create the actions to be shown on the toolbar
        """
        self.applyAllAction = QAction(self, triggered=self.onApplyAll)
        self.applyAllAction.setText("&Apply Stretch to All Open Files")
        self.applyAllAction.setStatusTip("Apply Stretch to All Open Files")
        self.applyAllAction.setIcon(QIcon(":/viewer/images/applyall.png"))
        
        self.applyAction = QAction(self, triggered=self.onApply)
        self.applyAction.setText("&Apply Stretch")
        self.applyAction.setStatusTip("Apply Stretch")
        self.applyAction.setIcon(QIcon(":/viewer/images/apply.png"))

        self.localAction = QAction(self)
        self.localAction.setText("&Local Stretch")
        self.localAction.setStatusTip(
            "Calculate approximate local stretch on Apply")
        self.localAction.setIcon(QIcon(":/viewer/images/local.png"))
        self.localAction.setCheckable(True)

        self.saveAction = QAction(self, triggered=self.onSave)
        self.saveAction.setText("&Save Stretch and Lookup Table")
        self.saveAction.setStatusTip(
            "Save Stretch and Lookup Table to current File")
        self.saveAction.setIcon(QIcon(":/viewer/images/save.png"))

        self.deleteAction = QAction(self, triggered=self.onDelete)
        self.deleteAction.setText("&Delete Stretch and Lookup Table")
        self.deleteAction.setStatusTip(
            "Delete Stretch and Lookup Table from current File")
        self.deleteAction.setIcon(QIcon(":/viewer/images/deletesaved.png"))

        self.exportToTextAction = QAction(self, triggered=self.exportToText)
        self.exportToTextAction.setText(
            "&Export Stretch and Lookup Table to Text file")    
        self.exportToTextAction.setStatusTip(
            "Export current Stretch and Lookup Table to Text file")
        self.exportToTextAction.setIcon(QIcon(":/viewer/images/savetext.png"))

        self.importFromGDALAction = QAction(self, triggered=self.importFromGDAL)
        self.importFromGDALAction.setText(
            "&Import Stretch and Lookup Table from GDAL file and apply")
        self.importFromGDALAction.setStatusTip(
            "Import Stretch and Lookup Table saved in GDAL file and apply")
        self.importFromGDALAction.setIcon(QIcon(":/viewer/images/open.png"))

        self.importFromTextAction = QAction(self, triggered=self.importFromText)
        self.importFromTextAction.setText(
            "I&mport Stretch and Lookup Table from Text file")
        self.importFromTextAction.setStatusTip(
            "Import Stretch and Lookup Table saved in text file and apply")
        self.importFromTextAction.setIcon(QIcon(":/viewer/images/opentext.png"))

    def setupToolbar(self):
        """
        Add the actions to the toolbar
        """
        self.toolBar.addAction(self.applyAction)
        self.toolBar.addAction(self.applyAllAction)
        self.toolBar.addAction(self.localAction)
        self.toolBar.addSeparator()
        self.toolBar.addAction(self.saveAction)
        self.toolBar.addAction(self.deleteAction)
        self.toolBar.addAction(self.exportToTextAction)
        self.toolBar.addAction(self.importFromGDALAction)
        self.toolBar.addAction(self.importFromTextAction)
        
    def onApplyAll(self):
        """
        The function to be run when the ApplyAll button is clicked (applies
        a stretch to all files open in tuiview.
        """
        stretchvalue = self.stretchLayout.getStretch()
        islocalchecked = self.localAction.isChecked()
        try:
            self.viewwidget.layers.setStretchAllLayers(stretchvalue,
                                                       islocalchecked)
            self.viewwidget.viewport().update()
        except Exception as e:
            QMessageBox.critical(self, MESSAGE_TITLE, str(e))

    def onApply(self):
        """
        Apply the new stretch to the view widget
        """
        stretch = self.stretchLayout.getStretch()
        local = self.localAction.isChecked()
        try:
            self.viewwidget.setNewStretch(stretch, self.layer, local)
        except Exception as e:
            QMessageBox.critical(self, MESSAGE_TITLE, str(e))

    def onSave(self):
        """
        User wants to save the stretch to the file
        """
        stretch = self.stretchLayout.getStretch()

        try:
            
            self.layer.saveStretchToFile(stretch)
            self.parent.showStatusMessage("Stretch written to file")
        except Exception as e:
            QMessageBox.critical(self, MESSAGE_TITLE, str(e))

    def onDelete(self):
        """
        Delete any stretch/LUT from the file
        """
        try:
            self.layer.deleteStretchFromFile()
            self.parent.showStatusMessage("Stretch deleted from file")
        except Exception as e:
            QMessageBox.critical(self, MESSAGE_TITLE, str(e))

    def exportToText(self):
        """
        Export stretch and Lookup Table to JSON text
        """
        fname, _ = QFileDialog.getSaveFileName(self, 
                    "Select file to save stretch and lookup table into",
                    os.getcwd(), STRETCH_FILTER)
        if fname != "":
            try:
                self.layer.exportStretchandLUTToText(fname)
            except Exception as e:
                QMessageBox.critical(self, MESSAGE_TITLE, str(e))

    def importFromGDAL(self):
        """
        Import stretch and lookup table from file where these have already 
        been saved
        """
        viewerwindow.populateFilters()       
        dlg = QFileDialog(self)
        dlg.setNameFilters(viewerwindow.GDAL_FILTERS)
        dlg.setFileMode(QFileDialog.ExistingFile)
        # set last dir
        dirn = os.path.dirname(self.layer.filename)
        dlg.setDirectory(dirn)

        if dlg.exec_() == QDialog.Accepted:
            fname = dlg.selectedFiles()[0]
            fname = str(fname)
            try:
                stretch = viewerstretch.ViewerStretch.fromGDALFileWithLUT(fname)
                if stretch is None:
                    QMessageBox.critical(self, MESSAGE_TITLE, 
                        "Unable to find stretch")
                else:
                    self.viewwidget.setNewStretch(stretch, self.layer)

                    self.stretchLayout.updateStretch(stretch)

            except Exception as e:
                QMessageBox.critical(self, MESSAGE_TITLE, str(e))

    def importFromText(self):
        """
        Import stretch and lookup table from text file saved by exportToText()
        """
        fname, _ = QFileDialog.getOpenFileName(self, 
                    "Select file containing stretch and lookup table",
                    os.getcwd(), STRETCH_FILTER)
        if fname != "":
            try:
                stretch = viewerstretch.ViewerStretch.fromTextFileWithLUT(fname)
                self.viewwidget.setNewStretch(stretch, self.layer)

                self.stretchLayout.updateStretch(stretch)

            except Exception as e:
                QMessageBox.critical(self, MESSAGE_TITLE, str(e))

