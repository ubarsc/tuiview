"""
Module that contains the PropertiesWindow class
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
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QTextEdit
from PyQt5.QtWidgets import QGroupBox, QLabel, QGridLayout, QTabWidget, QWidget
from PyQt5.QtWidgets import QComboBox

from . import plotwidget

class PropertiesWindow(QDialog):
    def __init__(self, parent, info):
        QDialog.__init__(self, parent)
        self.info = info

        self.mainLayout = QVBoxLayout()

        self.fileLayout = QVBoxLayout()
        self.fileTab = QTabWidget()

        self.fileInfoWidget = QWidget()
        self.fileInfoWidgetLayout = QGridLayout()
        self.fileInfoWidget.setLayout(self.fileInfoWidgetLayout)
        for rowCount, values in enumerate(info.fileInfo):
            name, value = values
            nameLabel = QLabel()
            nameLabel.setText(name)
            self.fileInfoWidgetLayout.addWidget(nameLabel, rowCount, 0)

            valueLabel = QLabel()
            valueLabel.setText(value)
            self.fileInfoWidgetLayout.addWidget(valueLabel, rowCount, 1)

        self.fileTab.addTab(self.fileInfoWidget, "File Information")

        self.fileProjWidget = QWidget()
        self.fileProjWidgetLayout = QGridLayout()
        self.fileProjWidget.setLayout(self.fileProjWidgetLayout)

        coordInfo = [('Projection', info.getProjection()), 
                        ('Datum', info.getDatum()),
                        ('Spheroid', info.getSpheroid()),
                        ('Units', info.getUnits()),
                        ('UTM Zone', info.getUTMZone())]
        for rowCount, values in enumerate(coordInfo):
            name, value = values
            nameLabel = QLabel()
            nameLabel.setText(name)
            self.fileProjWidgetLayout.addWidget(nameLabel, rowCount, 0)

            valueLabel = QLabel()
            if value is not None:
                valueLabel.setText(value)
            else:
                valueLabel.setText("Not Set")
            self.fileProjWidgetLayout.addWidget(valueLabel, rowCount, 1)

        self.fileTab.addTab(self.fileProjWidget, "Coordinate System")

        self.fileLayout.addWidget(self.fileTab)
        
        self.fileGroup = QGroupBox('File')
        self.fileGroup.setLayout(self.fileLayout)
        self.mainLayout.addWidget(self.fileGroup)


        self.layerLayout = QVBoxLayout()
        self.layerTab = QTabWidget()

        self.layerSelLayout = QGridLayout()
        self.layerSelLabel = QLabel()
        self.layerSelLabel.setText("Layer:")
        self.layerSelLayout.addWidget(self.layerSelLabel, 0, 0)
        self.layerSelCombo = QComboBox()
        for idx, name in enumerate(info.bandNames):
            self.layerSelCombo.addItem(name, idx)
        self.layerSelCombo.setEnabled(len(info.bandNames) > 1)

        self.layerSelLayout.addWidget(self.layerSelCombo, 0, 1)
        self.layerSelCombo.currentIndexChanged.connect(self.layerChanged)

        self.layerLayout.addLayout(self.layerSelLayout)
        self.layerLayout.addWidget(self.layerTab)

        self.layerInfoWidget = QWidget()
        self.plotWidget = plotwidget.PlotBarWidget(self)

        self.layerInfoLayout = QGridLayout()
        self.layerValueLabels = {} # so we can just update what we need
        self.layerChanged(0) # fill it in
        self.layerSelCombo.setCurrentIndex(0) # make sure we are at first one
        self.layerInfoWidget.setLayout(self.layerInfoLayout)

        self.layerTab.addTab(self.layerInfoWidget, 'Layer Information')

        self.layerTab.addTab(self.plotWidget, 'Layer Histogram')

        self.layerGroup = QGroupBox('Layer')
        self.layerGroup.setLayout(self.layerLayout)

        self.mainLayout.addWidget(self.layerGroup)


        self.bandInfoLayout = QGridLayout()

        self.mainLayout.addLayout(self.bandInfoLayout)

        self.closeButton = QPushButton()
        self.closeButton.setText("Close")
        self.closeButton.clicked.connect(self.accept)

        self.mainLayout.addWidget(self.closeButton)

        self.setLayout(self.mainLayout)
        self.setSizeGripEnabled(True)
        self.resize(500, 600)
        

    def layerChanged(self, comboIdx):
        """
        Called when the band changed - update GUI
        """
        # get the idx in the info object
        idx = self.layerSelCombo.itemData(comboIdx)

        if len(self.layerValueLabels) == 0:
            for rowCount, values in enumerate(self.info.bandInfo[idx]):
                name, value = values
                nameLabel = QLabel()
                nameLabel.setText(name)
                self.layerInfoLayout.addWidget(nameLabel, rowCount, 0)

                valueLabel = QLabel()
                valueLabel.setText(value)
                self.layerInfoLayout.addWidget(valueLabel, rowCount, 1)
                self.layerValueLabels[name] = valueLabel

        else:
            for name, value in self.info.bandInfo[idx]:
                valueLabel = self.layerValueLabels[name]
                valueLabel.setText(value)

        # update histogram info
        name = self.info.bandNames[idx]
        if name in self.info.histograms:
            minVal, maxVal, histData = self.info.histograms[name]

            plotBar = plotwidget.PlotBars(histData, minVal, maxVal)
            self.plotWidget.setBars(plotBar)
        else:
            # no histo info
            self.plotWidget.setBars(None)

