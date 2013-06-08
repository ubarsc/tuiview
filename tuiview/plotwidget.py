"""
Plot widget
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

from __future__ import division # ensure we are using Python 3 semantics
import numpy
from PyQt4.QtGui import QWidget, QPainter, QPainterPath, QPen, QFontMetrics
from PyQt4.QtCore import Qt, QSize

class PlotCurve(object):
    """
    Pass instances of these to PlotWidget.addCurve()
    xdata and ydata should be numpy arrays
    If pen not given will be white, 1 pixel wide
    """
    def __init__(self, xdata, ydata, pen=None):
        self.xdata = xdata
        self.ydata = ydata
        if xdata.size == 0 or ydata.size != xdata.size:
            raise ValueError('inavlid data')
        self.pen = pen
        if self.pen is None:
            self.pen = QPen()
            self.pen.setWidth(1)
            self.pen.setColor(Qt.white)

AXES_YSIZE = 18 # pixels
TICK_SIZE = 2  # pixels

class PlotWidget(QWidget):
    """
    Lightweight plot widget
    """
    def __init__(self, parent):
        QWidget.__init__(self, parent)
        # always draw background as black
        self.setBackgroundColor(Qt.black)
        self.setAutoFillBackground(True)

        # list of PlotCurves to draw
        self.curves = []

        # pen to draw the axes
        self.axesPen = QPen(Qt.gray)
        self.axesPen.setWidth(1)

        # default ranges - y autoscale
        self.setYRange()
        # x left =0, right autoscale
        self.setXRange(xmin=0)

        # font - default, but small
        font = self.font()
        font.setPointSize(6)
        self.setFont(font)

    def setYRange(self, ymin=None, ymax=None):
        """
        Set the Y range. Pass None for autoscale
        for either or both
        """
        self.yrange = (ymin, ymax)

    def setXRange(self, xmin=None, xmax=None):
        """
        Set the X range. Pass None for autoscale
        for either or both
        """
        self.xrange = (xmin, xmax)

    def setBackgroundColor(self, color):
        "Sets the background color for the widget"
        palette = self.palette()
        palette.setColor(self.backgroundRole(), color)
        self.setPalette(palette)
        self.update()

    def addCurve(self, curve):
        """
        Add an instance of PlotCurve to the list of curves
        to be plotted
        """
        self.curves.append(curve)
        self.update()

    def removeCurves(self):
        "Remove all the curves"
        self.curves = []
        self.update()

    def getYDataRange(self):
        """
        Get the range of the Y data to be plotted.
        If value(s) have been set with SetYRange these
        are returned
        """
        (minYData, maxYData) = self.yrange
        if minYData is None:
            minYData = self.curves[0].ydata.min()
            for curve in self.curves[1:]:
                my = curve.ydata.min()
                if my < minYData:
                    minYData = my
        if maxYData is None:
            maxYData = self.curves[0].ydata.max()
            for curve in self.curves[1:]:
                my = curve.ydata.max()
                if my > maxYData:
                    maxYData = my
        return minYData, maxYData

    def getXDataRange(self):
        """
        Get the range of the X data to be plotted.
        If value(s) have been set with SetXRange these
        are returned
        """
        (minXData, maxXData) = self.xrange
        if minXData is None:
            minXData = self.curves[0].xdata.min()
            for curve in self.curves[1:]:
                mx = curve.xdata.min()
                if mx < minXData:
                    minXData = mx
        if maxXData is None:
            maxXData = self.curves[0].xdata.max()
            for curve in self.curves[1:]:
                mx = curve.xdata.max()
                if mx > maxXData:
                    maxXData = mx
        return minXData, maxXData

    @staticmethod
    def makeIntervals(start, end, nIntervals):
        """
        Make a 'pretty' list of intervals. 
        This was the hardest part.
        also returns number of decimals to display
        This is non-zero if floating point data
        """
        interval = (end - start) / nIntervals

        ndecimals = 0
        test = interval
        if interval >= 1:
            while test > 10:
                test /= 10
                ndecimals += 1
        else:
            while test < 10:
                test *= 10
                ndecimals += 1
            ndecimals = -ndecimals

        newinterval = numpy.ceil(test) * 10**ndecimals
        mininterval = int(start / newinterval) * newinterval

        tmp = mininterval
        intervals = [tmp]
        for n in range(nIntervals):
            tmp += newinterval
            intervals.append(tmp)

        if ndecimals < 0:
            npd = abs(ndecimals)
        else:
            npd = 0

        return intervals, npd

    @staticmethod
    def formatInterval(interval, ndp):
        if ndp == 0:
            txt = "%d" % interval
        else:
            txt = "%.*f" % (ndp, interval)
        return txt

    def drawYLabels(self, paint, minYData, maxYData, yoffset, yscale, height):
        """
        Draw the Y-labels. Returns the size needed for the text
        """
        paint.setPen(self.axesPen)

        nIntervals = int(height / 20)

        intervals, ndp = self.makeIntervals(minYData, maxYData, nIntervals)
        # find with of largest interval (last?) and use that for width param
        txt = self.formatInterval(intervals[-1], ndp)
        fm = QFontMetrics(self.font())
        textrect = fm.boundingRect(txt)
        txtwidth = textrect.width()
        txtheight = textrect.height()
        for interval in intervals:
            txt = self.formatInterval(interval, ndp)

            yloc = interval * yscale + yoffset
            paint.drawText(0, yloc, txtwidth, txtheight, 
                            Qt.AlignRight | Qt.AlignVCenter, txt)
            # draw tick
            paint.drawLine(txtwidth, yloc, txtwidth + TICK_SIZE, yloc)

        return txtwidth + TICK_SIZE

    def drawXLabels(self, paint, minXData, maxXData, xoffset, xscale, width, height):
        """
        Draw the Y-labels
        """
        paint.setPen(self.axesPen)

        nIntervals = int(width / 100)

        intervals, ndp = self.makeIntervals(minXData, maxXData, nIntervals)
        # find with of largest interval (last?) and use that for width param
        txt = self.formatInterval(intervals[-1], ndp)
        fm = QFontMetrics(self.font())
        txtwidth = fm.boundingRect(txt).width()
        halftxtwidth = txtwidth / 2
        for interval in intervals:
            txt = self.formatInterval(interval, ndp)

            xloc = interval * xscale + xoffset
            paint.drawText(xloc - halftxtwidth, height, 
                            txtwidth, AXES_YSIZE - TICK_SIZE, 
                            Qt.AlignHCenter | Qt.AlignBottom, txt)
            # draw tick
            paint.drawLine(xloc, height, xloc, 
                            height + TICK_SIZE)

    def paintEvent(self, event):
        """
        This is the main part - calculation and drawing happen here.
        In theory the calculation should happen separately on resize etc 
        and paint should be simpler, but can't be bothered right now
        """
        paint = QPainter(self)

        size = self.size()
        plotheight = size.height() - AXES_YSIZE - 1

        yoffset = size.height() - AXES_YSIZE
        axes_xsize = AXES_YSIZE # in case there no data, we still have axes drawn ok

        # do we have data?
        if len(self.curves) != 0:
            minYData, maxYData = self.getYDataRange()
            minXData, maxXData = self.getXDataRange()
            xrange = (maxXData - minXData)
            yrange = (maxYData - minYData)

            # check we can draw lines
            if xrange != 0 and yrange != 0:

                # NB: Qt works from top left, plots from bottom left
                yscale = -plotheight / yrange

                # axes labels
                axes_xsize = self.drawYLabels(paint, minYData, maxYData, yoffset, 
                                    yscale, plotheight)

                # now we now the width of the axes_xsize calc the other parts
                plotwidth = size.width() - axes_xsize - 1
                xoffset = axes_xsize
                xscale = plotwidth / xrange

                self.drawXLabels(paint, minXData, maxXData, xoffset, 
                                    xscale, plotwidth, plotheight)

                # each curve
                for curve in self.curves:
                    paint.setPen(curve.pen)

                    xpoints = (curve.xdata - minXData) * xscale + xoffset
                    ypoints = (curve.ydata - minYData) * yscale + yoffset
                    xpoints = xpoints.astype(int)
                    ypoints = ypoints.astype(int)

                    # doesn't seem to be a faster array way, but this
                    # seems plenty fast enough
                    path = QPainterPath()
                    path.moveTo(xpoints[0], ypoints[0])
                    for x, y in zip(xpoints[1:], ypoints[1:]):
                        path.lineTo(x, y)
                    paint.drawPath(path)

        # axes
        paint.setPen(self.axesPen)
        paint.drawLine(axes_xsize, 0, axes_xsize, size.height() - AXES_YSIZE)
        paint.drawLine(axes_xsize, size.height() - AXES_YSIZE, size.width(), 
                        size.height() - AXES_YSIZE)

        paint.end()

    def sizeHint(self):
        """
        This has to be implemented otherwise plot is very small!
        """
        return QSize(400, 400)
