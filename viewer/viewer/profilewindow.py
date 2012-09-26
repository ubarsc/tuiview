"""
Module that contains the ProfileDockWidget
"""

from PyQt4.QtGui import QDockWidget, QWidget, QToolBar, QVBoxLayout, QPen
from PyQt4.QtCore import Qt, SIGNAL
import numpy

# See if we have access to Qwt
HAVE_QWT = True
try:
    from PyQt4.Qwt5 import QwtPlot, QwtPlotCurve
except ImportError:
    HAVE_QWT = False

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
        self.mainLayout.addWidget(self.toolBar)

        if HAVE_QWT:
            self.plotWidget = QwtPlot()
            self.plotWidget.setMinimumSize(300, 100)
            self.plotCurve = QwtPlotCurve()
            self.plotCurve.attach(self.plotWidget)
            self.mainLayout.addWidget(self.plotWidget)
        else:
            self.noQWTLabel = QLabel()
            self.noQWTLabel.setText("PyQwt needs to be installed for plot")
            self.noQWTLabel.setAlignment(Qt.AlignCenter)
            self.mainLayout.addWidget(self.noQWTLabel)

        self.rulerWidget = QWidget() # for now
        self.mainLayout.addWidget(self.rulerWidget)

        self.dockWidget.setLayout(self.mainLayout)
        
        # tell the dock window this is the widget to display
        self.setWidget(self.dockWidget)

    def newLine(self, polyLine):
        """
        Widget has collected a new line
        """
        if HAVE_QWT:
            profiledata, profilemask = polyLine.getProfile()

            if isinstance(profiledata, list):
                colList = [Qt.red, Qt.green, Qt.blue]
                for data, col in zip(profiledata, colList):
                    pen = QPen(col)
                    pen.setWidth(1)
                    self.plotCurve.setPen(pen)

                size = data.size
                print data.shape
                xdata = numpy.linspace(0, size-1, size)
                self.plotCurve.setData(xdata, data)
            else:
                pen = QPen(Qt.black)
                pen.setWidth(1)
                self.plotCurve.setPen(pen)

                size = profiledata.size
                xdata = numpy.linspace(0, size-1, size)
                self.plotCurve.setData(xdata, profiledata)
                

            self.plotWidget.replot()

        

    def closeEvent(self, event):
        """
        Window is being closed - inform parent window
        """
        self.emit(SIGNAL("profileClosed(PyQt_PyObject)"), self)
