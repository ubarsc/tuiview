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

from __future__ import division  # ensure we are using Python 3 semantics
import numpy
from PyQt5.QtGui import QPainter, QPainterPath, QPen, QFontMetrics
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QSize, QSettings

DEFAULT_FONT_SIZE = 6
try:
    DEFAULT_YTICK_FLAGS = Qt.AlignRight | Qt.AlignVCenter | Qt.TextDontClip
    DEFAULT_XTICK_FLAGS = Qt.AlignHCenter | Qt.AlignTop | Qt.TextDontClip
    DEFAULT_LABEL_FLAGS = Qt.AlignLeft | Qt.AlignTop
except TypeError:
    # if building from sphinx these values will be type Mock()
    # which cannot be Or'd. So we fack it.
    DEFAULT_YTICK_FLAGS = 0
    DEFAULT_XTICK_FLAGS = 0
    DEFAULT_LABEL_FLAGS = 0
TICK_SIZE = 2  # pixels


class PlotCurve(object):
    """
    Pass instances of these to PlotLineWidget.addCurve()
    xdata and ydata should be numpy arrays
    If pen not given will be white, 1 pixel wide
    """
    def __init__(self, xdata, ydata, pen=None):
        self.xdata = xdata
        self.ydata = ydata
        if xdata.size == 0 or ydata.size != xdata.size:
            raise ValueError('invalid data')
        self.pen = pen
        if self.pen is None:
            self.pen = QPen()
            self.pen.setWidth(1)
            self.pen.setColor(Qt.white)


class PlotBars(object):
    """
    Pass an instance of this to PlotBarWidget.setBars()
    data should be a numpy array containing the counts. minVal and maxVal
    describe the range of the data
    """
    def __init__(self, data, minVal, maxVal, pen=None, fillColor=Qt.white):
        self.data = data
        self.minVal = minVal
        self.maxVal = maxVal
        if data.size == 0:
            raise ValueError('inavlid data')
        self.pen = pen
        if self.pen is None:
            self.pen = QPen()
            self.pen.setWidth(1)
            self.pen.setColor(Qt.white)
        self.fillColor = fillColor


class PlotLabel(object):
    """
    Pass instances of these to PlotWidget.addLabel()
    xloc and yloc are in data units
    txt is text to display
    flags are those accepted by QPainter.drawText
    If pen not given will be white, 1 pixel wide
    """
    def __init__(self, xloc, yloc, txt, flags=DEFAULT_LABEL_FLAGS, 
            pen=None):
        self.xloc = xloc
        self.yloc = yloc
        self.txt = txt
        self.flags = flags
        self.pen = pen
        if self.pen is None:
            self.pen = QPen()
            self.pen.setWidth(1)
            self.pen.setColor(Qt.white)


class PlotTick(object):
    """
    Pass lists of these to PlotWidget.setXTicks and PlotWidget.setYTicks
    if flags is None either DEFAULT_YTICK_FLAGS or DEFAULT_XTICK_FLAGS
    will be used depending on the direction
    if pen is None the default axes pen will be used
    """
    def __init__(self, loc, txt, flags=None, pen=None):
        self.loc = loc
        self.txt = txt
        self.flags = flags
        self.pen = pen


class PlotWidget(QWidget):
    """
    Lightweight plot widget base class
    Don't instantiate directly - use one of the base classes.
    """
    def __init__(self, parent):
        QWidget.__init__(self, parent)
        # always draw background as black
        self.setBackgroundColor(Qt.black)
        self.setAutoFillBackground(True)

        # pen to draw the axes
        self.axesPen = QPen(Qt.gray)
        self.axesPen.setWidth(1)

        # font 
        fontSize = self.getSettingsFontSize()
        self.setFontSize(fontSize)

        # xticks. Lists of PlotTicks
        self.xticks = None
        # yticks
        self.yticks = None

        #  text labels list of PlotTexts
        self.labels = []

        #  fontmetrics
        self.fontMetrics = QFontMetrics(self.font())

    def haveData(self):
        """
        Returns True if data has been set 
        """
        raise NotImplementedError('haveData() must be implemented')

    def getSettingsFontSize(self):
        "Get the default font size from settings"
        settings = QSettings()
        settings.beginGroup('Plot')

        fontSize = settings.value('FontSize', DEFAULT_FONT_SIZE, int)

        settings.endGroup()
        return fontSize

    def setFontSize(self, size):
        "Set the font point size"
        font = self.font()
        font.setPointSize(size)
        self.setFont(font)
        self.update()

    def setYRange(self, ymin=None, ymax=None):
        """
        Set the Y range. Pass None for autoscale
        for either or both
        """
        self.yrange = (ymin, ymax)
        self.update()

    def setXRange(self, xmin=None, xmax=None):
        """
        Set the X range. Pass None for autoscale
        for either or both
        """
        self.xrange = (xmin, xmax)
        self.update()

    def setXTicks(self, xticks=None):
        """
        Pass a list of PlotTicks. None to reset.
        """
        self.xticks = xticks
        self.update()

    def setYTicks(self, yticks=None):
        """
        Pass a list of PlotTicks. None to reset.
        """
        self.yticks = yticks
        self.update()

    def setBackgroundColor(self, color):
        "Sets the background color for the widget"
        palette = self.palette()
        palette.setColor(self.backgroundRole(), color)
        self.setPalette(palette)
        self.update()

    def addLabel(self, label):
        "Add a PlotLabel to be drawn"
        self.labels.append(label)
        self.update()

    def removeLabels(self):
        "remove all labels"
        self.labels = []
        self.update()

    def getYDataRange(self):
        """
        Get the range of the Y data to be plotted.
        """
        return self.yrange

    def getXDataRange(self):
        """
        Get the range of the X data to be plotted.
        """
        return self.xrange

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

    def drawText(self, paint, xloc, yloc, txt, flags):
        """
        Helper method to draw text in given device coords
        For some reason Qt doesn't come with a method like
        this that moves the text around for given flags.
        """
        # the position we are after is relative to the left bottom of the rect
        txtrect = self.fontMetrics.boundingRect(txt)

        if flags & Qt.AlignRight:
            xloc -= txtrect.width()
        if flags & Qt.AlignHCenter:
            xloc -= txtrect.width() / 2
        if flags & Qt.AlignTop:
            yloc += txtrect.height()
        if flags & Qt.AlignVCenter:
            yloc += txtrect.height() / 2

        if flags & Qt.TextDontClip:
            # remember: y is baseline
            txtrect.setRect(xloc, yloc - txtrect.height(), 
                    txtrect.width(), txtrect.height())

            winrect = self.rect()
            if not winrect.contains(txtrect):
                return

        paint.drawText(xloc, yloc, txt)

    @staticmethod
    def formatInterval(interval, ndp):
        if ndp == 0:
            txt = "%d" % interval
        else:
            txt = "%.*f" % (ndp, interval)
        return txt

    def findLargestIntervalLabel(self, intervals, ndp):
        maxwidth = 0
        for interval in intervals:
            txt = self.formatInterval(interval, ndp)
            textrect = self.fontMetrics.boundingRect(txt)
            txtwidth = textrect.width()
            if txtwidth > maxwidth:
                maxwidth = txtwidth
        return maxwidth

    def drawYTicks(self, paint, minYData, maxYData, yoffset, yscale, height):
        """
        Draw the Y-ticks. Returns the size needed for the text
        """
        paint.setPen(self.axesPen)
        flags = DEFAULT_YTICK_FLAGS

        if self.yticks is None:
            # create our own
            nIntervals = int(height / 20)

            intervals, ndp = self.makeIntervals(minYData, maxYData, nIntervals)

            # find width of largest interval and use that for width param
            txtwidth = self.findLargestIntervalLabel(intervals, ndp)

            for interval in intervals:

                if interval < minYData:
                    continue

                txt = self.formatInterval(interval, ndp)

                yloc = (interval - minYData) * yscale + yoffset

                self.drawText(paint, txtwidth, yloc, txt, flags)
                # draw tick
                paint.drawLine(txtwidth, yloc, txtwidth + TICK_SIZE, yloc)
        else:
            # user supplied

            lastTick = self.xticks[-1]
            textrect = self.fontMetrics.boundingRect(lastTick.txt)
            txtwidth = textrect.width()
            for tick in self.xticks:
                yloc = (tick.loc - minYData) * yscale + yoffset

                if tick.pen is not None:
                    oldPen = paint.pen()  # save it
                    paint.setPen(tick.pen)

                flags = DEFAULT_YTICK_FLAGS
                if tick.flags is not None:
                    flags = tick.flags

                self.drawText(paint, txtwidth, yloc, tick.txt, flags)

                if tick.pen is not None:
                    paint.setPen(oldPen)  # restore

                # draw tick
                paint.drawLine(txtwidth, yloc, txtwidth + TICK_SIZE, yloc)
    
        return txtwidth + TICK_SIZE

    def drawXTicks(self, paint, minXData, maxXData, xoffset, xscale, width, height):
        """
        Draw the X-ticks
        """
        paint.setPen(self.axesPen)
        flags = DEFAULT_XTICK_FLAGS

        if self.xticks is None:
            # we have to create our own

            # do a guess and refine it until it fits
            txtwidth = 20
            finished = False
            nIntervals = int(width / txtwidth)
            while not finished:

                intervals, ndp = self.makeIntervals(minXData, maxXData, nIntervals)
                txtwidth = self.findLargestIntervalLabel(intervals, ndp)

                nIntervals = int(width / txtwidth)
                # had to make it nIntervals+1 otherwise ended up
                # with infinite loop for long labels for some reason...
                finished = len(intervals) <= (nIntervals + 1)
                
            for interval in intervals:
                if interval < minXData:
                    continue

                txt = self.formatInterval(interval, ndp)

                xloc = (interval - minXData) * xscale + xoffset

                self.drawText(paint, xloc, height, txt, flags)

                # draw tick
                paint.drawLine(xloc, height, xloc, 
                    height + TICK_SIZE)
        else:
            # user supplied ticks
            for tick in self.xticks:
                xloc = (tick.loc - minXData) * xscale + xoffset

                if tick.pen is not None:
                    oldPen = paint.pen()  # save it
                    paint.setPen(tick.pen)

                flags = DEFAULT_XTICK_FLAGS
                if tick.flags is not None:
                    flags = tick.flags

                self.drawText(paint, xloc, height, tick.txt, flags)

                if tick.pen is not None:
                    paint.setPen(oldPen)  # restore
                # draw tick
                paint.drawLine(xloc, height, xloc, 
                    height + TICK_SIZE)

    def drawLabels(self, paint, minXData, minYData, xoffset, xscale, yoffset, yscale):
        """
        Draw the user supplied labels onto the plot
        """
        for label in self.labels:
            xloc = (label.xloc - minXData) * xscale + xoffset
            yloc = (label.yloc - minYData) * yscale + yoffset
            paint.setPen(label.pen)
            self.drawText(paint, xloc, yloc, label.txt, label.flags)

    def paintEvent(self, event):
        """
        This is the main part - calculation and drawing happen here.
        In theory the calculation should happen separately on resize etc 
        and paint should be simpler, but can't be bothered right now
        Delegates to paintData() in sublass to do actuall work
        """
        paint = QPainter(self)

        # allow enough size under the x-axes for text and tick
        axes_ysize = self.fontMetrics.height() + TICK_SIZE

        size = self.size()
        plotheight = size.height() - axes_ysize

        yoffset = size.height() - axes_ysize
        axes_xsize = axes_ysize  # in case there no data, we still have axes drawn ok

        # do we have data?
        if self.haveData():
            minYData, maxYData = self.getYDataRange()
            minXData, maxXData = self.getXDataRange()
            xrange = (maxXData - minXData)
            yrange = (maxYData - minYData)

            # check we can draw lines 
            # - might still be a problem if range set by user
            if xrange > 0 and yrange > 0:

                # NB: Qt works from top left, plots from bottom left
                yscale = -plotheight / yrange

                # axes labels
                axes_xsize = self.drawYTicks(paint, minYData, maxYData, yoffset, 
                                    yscale, plotheight)

                # now we now the width of the axes_xsize calc the other parts
                plotwidth = size.width() - axes_xsize
                xoffset = axes_xsize
                xscale = plotwidth / xrange

                self.drawXTicks(paint, minXData, maxXData, xoffset, 
                    xscale, plotwidth, plotheight)

                # delegate to sublass
                self.paintData(paint, minXData, minYData, xoffset, xscale, yoffset, yscale)

                # labels
                self.drawLabels(paint, minXData, minYData, xoffset, xscale, yoffset, yscale)

        # axes
        paint.setPen(self.axesPen)
        paint.drawLine(axes_xsize, 0, axes_xsize, size.height() - axes_ysize)
        paint.drawLine(axes_xsize, size.height() - axes_ysize, size.width(), 
            size.height() - axes_ysize)

        paint.end()

    def paintData(self, paint):
        """
        To be implemented in sublass
        """
        return NotImplementedError('must implement paintData')

    def sizeHint(self):
        """
        This has to be implemented otherwise plot is very small!
        """
        return QSize(400, 400)


class PlotLineWidget(PlotWidget):
    """
    Widget for making line plots
    """
    def __init__(self, parent):
        PlotWidget.__init__(self, parent)

        # default ranges - y autoscale
        self.setYRange()
        # x left =0, right autoscale
        self.setXRange(xmin=0)

        # list of PlotCurves to draw
        self.curves = []

    def haveData(self):
        """
        Returns True if data has been set 
        """
        return len(self.curves) != 0

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
        (minYData, maxYData) = PlotWidget.getYDataRange(self)
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

        if (maxYData - minYData) == 0:
            # make range +/- 20%
            minYData = maxYData - (maxYData * 0.2)
            maxYData = maxYData + (maxYData * 0.2)

        return minYData, maxYData

    def getXDataRange(self):
        """
        Get the range of the X data to be plotted.
        If value(s) have been set with SetXRange these
        are returned
        """
        (minXData, maxXData) = PlotWidget.getXDataRange(self)
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

        if (maxXData - minXData) == 0:
            # make range +/- 20%
            minXData = maxXData - (maxXData * 0.2)
            maxXData = maxXData + (maxXData * 0.2)

        return minXData, maxXData

    def paintData(self, paint, minXData, minYData, xoffset, xscale, yoffset, yscale):
        """
        Paints the curves - called from paintEvent in the baseclass
        """
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


class PlotBarWidget(PlotWidget):
    """
    Widget for making bar plots
    """
    def __init__(self, parent):
        PlotWidget.__init__(self, parent)

        # default ranges - y min = 0
        self.setYRange(ymin=0)
        # x  autoscale
        self.setXRange()

        # out one PlotBars object
        # maybe we should support more than one?
        self.bars = None

    def haveData(self):
        """
        Returns True if data has been set 
        """
        return self.bars is not None

    def setBars(self, bars):
        "Set the bars object to use"
        self.bars = bars
        self.update()

    def getYDataRange(self):
        """
        Get the range of the Y data to be plotted.
        If value(s) have been set with SetYRange these
        are returned
        """
        (minYData, maxYData) = PlotWidget.getYDataRange(self)
        if minYData is None:
            minYData = self.bars.data.min()
        if maxYData is None:
            maxYData = self.bars.data.max()

        if (maxYData - minYData) == 0:
            # make range +/- 20%
            minYData = maxYData - (maxYData * 0.2)
            maxYData = maxYData + (maxYData * 0.2)

        return minYData, maxYData

    def getXDataRange(self):
        """
        Get the range of the X data to be plotted.
        If value(s) have been set with SetXRange these
        are returned
        """
        (minXData, maxXData) = PlotWidget.getXDataRange(self)
        if minXData is None:
            minXData = self.bars.minVal
        if maxXData is None:
            maxXData = self.bars.maxVal

        if (maxXData - minXData) == 0:
            # make range +/- 20%
            minXData = maxXData - (maxXData * 0.2)
            maxXData = maxXData + (maxXData * 0.2)

        return minXData, maxXData

    def paintData(self, paint, minXData, minYData, xoffset, xscale, yoffset, yscale):
        """
        Paints the bars - called from paintEvent in the baseclass
        """
        paint.setPen(self.bars.pen)
        heights = (self.bars.data - minYData) * yscale + yoffset
        tlxs = numpy.linspace(self.bars.minVal, self.bars.maxVal, self.bars.data.size)
        tlxs = (tlxs - minXData) * xscale + xoffset
        tlxs += 1  # otherwise left most bar gets clobbered by axis
        width = int(tlxs[1] - tlxs[0])
        if width < 1:
            width = 1

        for height, tlx in zip(heights, tlxs):
            paint.fillRect(tlx, height, width, yoffset - height, self.bars.fillColor)
