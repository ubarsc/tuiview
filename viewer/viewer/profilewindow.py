"""
Module that contains the ProfileDockWidget
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

from PyQt4.QtGui import QDockWidget, QWidget, QToolBar, QVBoxLayout
from PyQt4.QtGui import QPen, QLabel, QAction, QIcon
from PyQt4.QtCore import Qt, SIGNAL, QLocale
import numpy

# See if we have access to PyQtGraph
HAVE_PYQTGRAPH = True
try:
    import pyqtgraph
except ImportError:
    HAVE_PYQTGRAPH = False

class ProfileDockWidget(QDockWidget):
    """
    Dockable window that is a combined profile and ruler
    """
    def __init__(self, parent, viewwidget):
        QDockWidget.__init__(self, "Profile", parent)
        self.viewwidget = viewwidget

        # create a new widget that lives in the dock window
        self.dockWidget = QWidget()
        self.mainLayout = QVBoxLayout()

        self.toolBar = QToolBar(self.dockWidget)
        self.setupActions()
        self.setupToolbar()
        self.mainLayout.addWidget(self.toolBar)

        if HAVE_PYQTGRAPH:
            self.plotWidget = pyqtgraph.PlotWidget()
            self.mainLayout.addWidget(self.plotWidget)

            self.blackPen = QPen(Qt.black)
            self.redPen = QPen(Qt.red)
            self.greenPen = QPen(Qt.green)
            self.bluePen = QPen(Qt.blue)

            self.oldCurves = [] # so we can detach them for replot

        else:
            self.noPyQtGraphLabel = QLabel()
            self.noPyQtGraphLabel.setText("PyQtGraph needs to be installed for plot")
            self.noPyQtGraphLabel.setAlignment(Qt.AlignCenter)
            self.mainLayout.addWidget(self.noPyQtGraphLabel)

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

        self.savePlotAction = QAction(self)
        self.savePlotAction.setText("&Save Plot")
        self.savePlotAction.setStatusTip("Save Plot")
        self.savePlotAction.setIcon(QIcon(":/viewer/images/saveplot.png"))
        self.connect(self.savePlotAction, SIGNAL("triggered()"), self.savePlot)

        self.plotScalingAction = QAction(self)
        self.plotScalingAction.setText("Set Plot Scaling")
        self.plotScalingAction.setStatusTip("Set Plot Scaling")
        icon = QIcon(":/viewer/images/setplotscale.png")
        self.plotScalingAction.setIcon(icon)
        self.connect(self.plotScalingAction, SIGNAL("triggered()"), 
                        self.onPlotScaling)

    def setupToolbar(self):
        """
        Add the actions to the toolbar
        """
        self.toolBar.addAction(self.followAction)
        if HAVE_PYQTGRAPH:
            self.toolBar.addAction(self.savePlotAction)
            self.toolBar.addAction(self.plotScalingAction)

    def savePlot(self):
        """
        Save the plot as a file. Either .pdf or .ps QPrinter
        chooses format based on extension.
        """
        from PyQt4.QtGui import QPrinter, QPainter, QFileDialog
        if HAVE_PYQTGRAPH:
            fname = QFileDialog.getSaveFileName(self, "Plot File", 
                        filter="PDF (*.pdf);;Postscript (*.ps)")
            if not fname.isEmpty():
                printer = QPrinter()
                printer.setOrientation(QPrinter.Landscape)
                printer.setColorMode(QPrinter.Color)
                printer.setOutputFileName(fname)
                printer.setResolution(96)
                painter = QPainter()
                painter.begin(printer)
                self.plotWidget.render(painter)
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

        lastidx = 0 # start at the beginning of the array
        for idx in changeidx:
            if mask[lastidx]:
                # we are in a run of True's
                xdatasub = xdata[lastidx:idx]
                ydatasub = ydata[lastidx:idx]
                
                curve = self.plotWidget.plot()
                curve.setData(x=xdatasub, y=ydatasub)
                curve.setPen(pen)
            lastidx = idx

    def newLine(self, polyLine):
        """
        Widget has collected a new line
        """
        if not self.followAction.isChecked():
            return

        # get the info we need out of the PolylineToolInfo
        profiledata, profilemask, distance = polyLine.getProfile()
        # set the distance text with commas etc as defined
        # by the system locale
        txt = QLocale.system().toString(distance[-1])
        fmt = "Total Distance: %s" % txt
        self.distanceLabel.setText(fmt)

        if HAVE_PYQTGRAPH:

            # get rid of curves from last time
            self.plotWidget.clear()

            if isinstance(profiledata, list):
                # RGB
                penList = [self.redPen, self.greenPen, self.bluePen]
                minValue = None
                maxValue = None
                for data, pen in zip(profiledata, penList):
                    self.plotProfile(distance, data, profilemask, pen)
        
                    # record the range of the data for scaling
                    masked = numpy.compress(profilemask, data)
                    bandMinValue = masked.min()
                    bandMaxValue = masked.max()
                    if minValue is None or bandMinValue < bandMinValue:
                        minValue = bandMinValue
                    if maxValue is None or bandMaxValue > maxValue:
                        maxValue = bandMaxValue
            else:
                # greyscale
                pen = self.blackPen
                self.plotProfile(distance, profiledata, profilemask, pen)

                # find range of data for scaling
                masked = numpy.compress(profilemask, profiledata)
                minValue = masked.min()
                maxValue = masked.max()

            self.dataRange = (minValue, maxValue)

            # include total distance in case start or end off image
            self.plotWidget.setXRange(0, distance[-1])

            # set scaling if needed
            minScale, maxScale = self.plotScaling
            if minScale is None and maxScale is None:
                # set back to auto
                self.plotWidget.enableAutoRange(pyqtgraph.ViewBox.YAxis)
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
        from .plotscalingdialog import PlotScalingDialog
        if HAVE_PYQTGRAPH:
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
        self.emit(SIGNAL("profileClosed(PyQt_PyObject)"), self)

