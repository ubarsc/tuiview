"""
Module that contains the QueryDockWidget
"""

from PyQt4.QtGui import QDockWidget, QTableWidget, QTableWidgetItem, QToolButton, QIcon
from PyQt4.QtGui import QHBoxLayout, QVBoxLayout, QLineEdit, QWidget, QColorDialog, QPixmap
from PyQt4.QtGui import QTabWidget, QLabel, QPen
from PyQt4.QtCore import SIGNAL, Qt

# See if we have access to Qwt
HAVE_QWT = True
try:
    from PyQt4.Qwt5 import QwtPlot, QwtPlotCurve, QwtPlotMarker, QwtText, QwtScaleDiv
except ImportError:
    HAVE_QWT = False

from .viewerstretch import VIEWER_MODE_RGB

QUERYWIDGET_DEFAULT_COLOR = Qt.white

# icons for displaying in the 'band' column for RGB
ICON_PIXMAP = QPixmap(24, 24)

ICON_PIXMAP.fill(Qt.red)
RED_ICON = QIcon(ICON_PIXMAP)

ICON_PIXMAP.fill(Qt.green)
GREEN_ICON = QIcon(ICON_PIXMAP)

ICON_PIXMAP.fill(Qt.blue)
BLUE_ICON = QIcon(ICON_PIXMAP)

class ColorButton(QToolButton):
    """
    QToolButton derived class that contains an icon
    solid with the specified color
    """
    def __init__(self, parent, color):
        QToolButton.__init__(self, parent)
        self.setColor(color)

    def setColor(self, color):
        """
        Just create a solid pixmap and an icon
        from that
        """
        self.color = color
        pixmap = QPixmap(24, 24)
        pixmap.fill(self.color)
        self.icon = QIcon(pixmap)
        self.setIcon(self.icon)

    def getColor(self):
        """
        return the current color
        """
        return self.color


class QueryDockWidget(QDockWidget):
    """
    Dock widget that contains the query window. Follows query 
    tool clicks (can be disabled) and can change query point color.
    Image values for point are displayed thanks to locationSelected
    signal from ViewerWidget. 
    """
    def __init__(self, parent, viewwidget):
        QDockWidget.__init__(self, "Query", parent)
        self.viewwidget = viewwidget

        # create a new widget that lives in the dock window
        self.dockWidget = QWidget()

        self.eastingEdit = QLineEdit(self.dockWidget)
        self.eastingEdit.setReadOnly(True)

        self.northingEdit = QLineEdit(self.dockWidget)
        self.northingEdit.setReadOnly(True)

        self.followButton = QToolButton(self.dockWidget)
        icon = QIcon(":/viewer/images/query.png")
        self.followButton.setIcon(icon)
        self.followButton.setCheckable(True)
        self.followButton.setChecked(True)
        self.followButton.setToolTip("Follow Query Tool")

        self.colorButton = ColorButton(self.dockWidget, QUERYWIDGET_DEFAULT_COLOR)
        self.colorButton.setToolTip("Set cursor color")
        self.connect(self.colorButton, SIGNAL("clicked()"), self.changeColor)

        self.coordLayout = QHBoxLayout()
        self.coordLayout.addWidget(self.eastingEdit)
        self.coordLayout.addWidget(self.northingEdit)
        self.coordLayout.addWidget(self.followButton)
        self.coordLayout.addWidget(self.colorButton)

        self.tabWidget = QTabWidget(self.dockWidget)

        self.tableWidget = QTableWidget()
        if HAVE_QWT:
            self.plotWidget = QwtPlot()
            self.plotCurve = QwtPlotCurve()
            self.plotCurve.attach(self.plotWidget)
            self.oldPlotLabels = [] # so we can detach() them when we want to redisplay
        else:
            self.noQWTLabel = QLabel()
            self.noQWTLabel.setText("PyQwt needs to be installed for plot display")
            self.noQWTLabel.setAlignment(Qt.AlignCenter)

        self.tabWidget.addTab(self.tableWidget, "Table")
        if HAVE_QWT:
            self.tabWidget.addTab(self.plotWidget, "Plot")
        else:
            self.tabWidget.addTab(self.noQWTLabel, "Plot")

        self.mainLayout = QVBoxLayout()
        self.mainLayout.addLayout(self.coordLayout)
        self.mainLayout.addWidget(self.tabWidget)

        self.dockWidget.setLayout(self.mainLayout)
        
        # tell the dock window this is the widget to display
        self.setWidget(self.dockWidget)

        # keep a track of the last QueryInfo in case we need to redisplay
        # when the user changes color
        self.lastqi = None

    def changeColor(self):
        """
        User wishes to change cursor color
        """
        initial = self.colorButton.getColor()
        newcolor = QColorDialog.getColor(initial, self)
        if newcolor.isValid():
            self.colorButton.setColor(newcolor)
    
            # if there is a previous point, redisplay in new color
            if self.lastqi is not None:
                self.viewwidget.setQueryPoint(id(self), self.lastqi.column, self.lastqi.row, newcolor)
                if HAVE_QWT:
                    # to get new color
                    self.updatePlot(self.lastqi, newcolor)


    def locationSelected(self, qi):
        """
        The ViewerWidget has told us it has a new coordinate from
        the query tool.
        """
        if self.followButton.isChecked():
            # set the coords
            self.eastingEdit.setText("%.5f" % qi.easting)
            self.northingEdit.setText("%.5f" % qi.northing)
            nbands = qi.data.shape[0]

            # set up the table
            self.tableWidget.setRowCount(nbands)
            self.tableWidget.setColumnCount(3)

            self.tableWidget.setHorizontalHeaderLabels(["Band", "Name", "Value"])
            vertLabels = ["%s" % (x+1) for x in range(nbands)]
            self.tableWidget.setVerticalHeaderLabels(vertLabels)

            # fill in the table
            count = 0
            for x in qi.data:
                # value
                valitem = QTableWidgetItem("%s" % x)
                valitem.setFlags(Qt.ItemIsEnabled) # disable editing etc
                self.tableWidget.setItem(count, 2, valitem)

                # band name
                nameitem = QTableWidgetItem(qi.bandNames[count])
                nameitem.setFlags(Qt.ItemIsEnabled) # disable editing etc
                self.tableWidget.setItem(count, 1, nameitem)

                # color
                band = count + 1
                if qi.stretch.mode == VIEWER_MODE_RGB and band in qi.stretch.bands:
                    coloritem = QTableWidgetItem()
                    if band == qi.stretch.bands[0]:
                        # red
                        coloritem.setIcon(RED_ICON)
                    elif band == qi.stretch.bands[1]:
                        # green
                        coloritem.setIcon(GREEN_ICON)
                    elif band == qi.stretch.bands[2]:
                        # blue
                        coloritem.setIcon(BLUE_ICON)
                    self.tableWidget.setItem(count, 0, coloritem)

                count += 1

            color = self.colorButton.getColor()

            # set up the plot
            if HAVE_QWT:
                self.updatePlot(qi, color)

            # add/modify this is a query point to the widget
            self.viewwidget.setQueryPoint(id(self), qi.column, qi.row, color)
            # remember this qi in case we need to change color
            self.lastqi = qi

    def updatePlot(self, qi, color):
        """
        Updates the plot widget with new data/color
        """
        pen = QPen(color)
        pen.setWidth(2)
        self.plotCurve.setPen(pen)
        nbands = qi.data.shape[0]
        xdata = range(1, nbands+1, 1)
        self.plotCurve.setData(xdata, qi.data)

        # detach any old ones
        for marker in self.oldPlotLabels:
            marker.detach()
        self.oldPlotLabels = []

        count = 1
        for x, y, text in zip(xdata, qi.data, qi.bandNames):
            marker = QwtPlotMarker()
            text = QwtText(text)
            marker.setLabel(text)
            marker.setValue(x, y)
            
            # align appropriately for first and last
            if count == 1:
                marker.setLabelAlignment(Qt.AlignRight)
            elif count == nbands:
                marker.setLabelAlignment(Qt.AlignLeft)
            
            marker.attach(self.plotWidget)
            self.oldPlotLabels.append(marker)
            count += 1

        # make xaxis labels integer
        div = self.plotWidget.axisScaleDiv(QwtPlot.xBottom)
        div.setInterval(1, nbands)
        div.setTicks(QwtScaleDiv.MajorTick, xdata)
        self.plotWidget.setAxisScaleDiv(QwtPlot.xBottom, div)

        self.plotWidget.replot()
        

    def closeEvent(self, event):
        """
        Window is being closed - inform parent window
        """
        self.viewwidget.removeQueryPoint(id(self))
        self.emit(SIGNAL("queryClosed(PyQt_PyObject)"), self)

