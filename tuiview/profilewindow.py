"""
Module that contains the ProfileDockWidget
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

from PySide6.QtGui import QPen, QIcon
from PySide6.QtWidgets import QDockWidget, QWidget, QToolBar, QVBoxLayout, QLabel
from PySide6.QtWidgets import QFileDialog
from PySide6.QtGui import QAction, QPainter, QPageLayout
from PySide6.QtCore import Qt, Signal, QLocale, QPoint
from PySide6.QtPrintSupport import QPrinter
import numpy

from . import plotwidget
from .plotscalingdialog import PlotScalingDialog


class ProfileDockWidget(QDockWidget):
    """
    Dockable window that is a combined profile and ruler
    """
    # signals
    profileClosed = Signal(QDockWidget, name='profileClosed')
    "emitted when Window closed"

    def __init__(self, parent, viewwidget):
        QDockWidget.__init__(self, "Profile", parent)
        self.viewwidget = viewwidget
        self.plugins = []

        # create a new widget that lives in the dock window
        self.dockWidget = QWidget()
        self.mainLayout = QVBoxLayout()

        self.toolBar = QToolBar(self.dockWidget)
        self.setupActions()
        self.setupToolbar()
        self.mainLayout.addWidget(self.toolBar)

        self.plotWidget = plotwidget.PlotLineWidget(self)
        self.mainLayout.addWidget(self.plotWidget)

        self.whitePen = QPen(Qt.white)
        self.whitePen.setWidth(1)
        self.redPen = QPen(Qt.red)
        self.redPen.setWidth(1)
        self.greenPen = QPen(Qt.green)
        self.greenPen.setWidth(1)
        self.bluePen = QPen(Qt.blue)
        self.bluePen.setWidth(1)

        self.distanceLabel = QLabel()
        self.mainLayout.addWidget(self.distanceLabel)

        self.dockWidget.setLayout(self.mainLayout)
        
        # tell the dock window this is the widget to display
        self.setWidget(self.dockWidget)

        self.resize(400, 200)

        # allow plot scaling to be changed by user
        # Min, Max. None means 'auto'.
        self.plotScaling = (None, None)
        # store the range of the data so we can init plot scale dlg
        self.dataRange = None
        # last polyLine so we can quickly resraw if plot scale changes
        self.lastPolyLine = None

        # connect if the layers have changed and we can close if our layer
        # no longer exists
        self.viewwidget.layers.layersChanged.connect(self.layersChanged)

    def setupActions(self):
        """
        Create the actions to be shown on the toolbar
        """
        self.followAction = QAction(self)
        self.followAction.setText("&Follow Query Tool")
        self.followAction.setStatusTip("Follow Query Tool")
        self.followAction.setIcon(QIcon(":/viewer/images/profileruler.png"))
        self.followAction.setCheckable(True)
        self.followAction.setChecked(True)

        self.savePlotAction = QAction(self, triggered=self.savePlot)
        self.savePlotAction.setText("&Save Plot")
        self.savePlotAction.setStatusTip("Save Plot")
        self.savePlotAction.setIcon(QIcon(":/viewer/images/saveplot.png"))

        self.plotScalingAction = QAction(self, triggered=self.onPlotScaling)
        self.plotScalingAction.setText("Set Plot Scaling")
        self.plotScalingAction.setStatusTip("Set Plot Scaling")
        icon = QIcon(":/viewer/images/setplotscale.png")
        self.plotScalingAction.setIcon(icon)

    def setupToolbar(self):
        """
        Add the actions to the toolbar
        """
        self.toolBar.addAction(self.followAction)
        self.toolBar.addAction(self.savePlotAction)
        self.toolBar.addAction(self.plotScalingAction)

    def savePlot(self):
        """
        Save the plot as a file. Either .pdf or .ps QPrinter
        chooses format based on extension.
        """
        fname, _ = QFileDialog.getSaveFileName(self, "Plot File", 
                    filter="PDF (*.pdf);;Postscript (*.ps)")
        if fname != '':
            printer = QPrinter()
            printer.setPageOrientation(QPageLayout.Landscape)
            printer.setColorMode(QPrinter.Color)
            printer.setOutputFileName(fname)
            printer.setResolution(96)
            painter = QPainter()
            painter.begin(printer)
            self.plotWidget.render(painter, QPoint())
            painter.end()

    def plotProfile(self, xdata, ydata, mask, pen):
        """
        Plot the xdata vs ydata. Use the mask
        to split the plot up so values only plotted
        where mask = True
        """
        # get all the indices where the mask
        # changes from True to False and vice versa
        changeidx = numpy.diff(mask).nonzero()[0]
        # because diff() starts from the second element
        # we actually want the indices relative to the start
        changeidx = changeidx + 1
        # go all the way to the end
        changeidx = numpy.append(changeidx, mask.size)

        lastidx = 0  # start at the beginning of the array
        for idx in changeidx:
            if mask[lastidx]:
                # we are in a run of True's
                xdatasub = xdata[lastidx:idx]
                ydatasub = ydata[lastidx:idx]
                
                curve = plotwidget.PlotCurve(xdatasub, ydatasub, pen)
                self.plotWidget.addCurve(curve)
            lastidx = idx

    def newLine(self, polyLine):
        """
        Widget has collected a new line
        """
        if not self.followAction.isChecked():
            return

        title = "Profile: %s" % polyLine.layer.title
        self.setWindowTitle(title)

        # get the info we need out of the PolylineToolInfo
        profiledata, profilemask, distance = polyLine.getProfile()
        # set the distance text with commas etc as defined
        # by the system locale
        txt = QLocale.system().toString(distance[-1])
        fmt = "Total Distance: %s" % txt
        self.distanceLabel.setText(fmt)

        # get rid of curves from last time
        self.plotWidget.removeCurves()

        if isinstance(profiledata, list):
            # RGB
            penList = [self.redPen, self.greenPen, self.bluePen]
            minValue = None
            maxValue = None
            for data, pen in zip(profiledata, penList):
                # record the range of the data for scaling
                masked = numpy.compress(profilemask, data)
                if masked.size == 0:
                    # can't do anything if no valid data
                    continue
                bandMinValue = masked.min()
                bandMaxValue = masked.max()

                self.plotProfile(distance, data, profilemask, pen)
        
                if minValue is None or minValue < bandMinValue:
                    minValue = bandMinValue
                if maxValue is None or maxValue > bandMaxValue:
                    maxValue = bandMaxValue
        else:
            # greyscale
            # find range of data for scaling
            masked = numpy.compress(profilemask, profiledata)
            if masked.size == 0:
                # can't do anything if no valid data
                return
            minValue = masked.min()
            maxValue = masked.max()

            pen = self.whitePen
            self.plotProfile(distance, profiledata, profilemask, pen)

        self.dataRange = (minValue, maxValue)

        # include total distance in case start or end off image
        self.plotWidget.setXRange(0, distance[-1])

        # set scaling if needed
        minScale, maxScale = self.plotScaling
        if minScale is None and maxScale is None:
            # set back to auto
            self.plotWidget.setYRange()
        else:
            # we need to provide both min and max so
            # derive from data if needed
            if minScale is None:
                minScale = minValue
            if maxScale is None:
                maxScale = maxValue
            self.plotWidget.setYRange(minScale, maxScale)

        self.lastPolyLine = polyLine

    def onPlotScaling(self):
        """
        Allows the user to change the Y axis scaling of the plot
        """
        if self.dataRange is not None:
            minValue, maxValue = self.dataRange
            # should inherit type of minValue etc
            # which should be the same as the data array
            data = numpy.array([minValue, maxValue])
        else:
            # uint8 default if no data 
            data = numpy.array([0, 1], dtype=numpy.uint8) 

        dlg = PlotScalingDialog(self, self.plotScaling, data)

        if dlg.exec_() == PlotScalingDialog.Accepted:
            self.plotScaling = dlg.getScale()
            if self.lastPolyLine is not None:
                self.newLine(self.lastPolyLine)

    def closeEvent(self, event):
        """
        Window is being closed - inform parent window
        """
        self.profileClosed.emit(self)
        
    def layersChanged(self):
        """
        Layers have changed - if polyLine.layer no
        longer in our list of layers then close this
        window. 
        """
        if self.lastPolyLine is not None:
            if self.lastPolyLine.layer not in self.viewwidget.layers.layers:
                # remove reference
                self.lastPolyLine = None
                # close window
                self.close()
