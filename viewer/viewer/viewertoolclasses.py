
"""
Supporting classes for tools in the ViewerWidget
"""

from PyQt4.QtGui import QPolygon, QPolygonF
from PyQt4.QtCore import Qt, QPoint, QPointF
import numpy

from .viewerLUT import MASK_IMAGE_VALUE

class PolyonToolInfo(QPolygon):
    """
    Class derived from QPolygon that contains the poly
    that the user selected, but has some other methods
    to create masks etc
    """
    def __init__(self, pointList, layer, modifiers):
        QPolygonF.__init__(self, pointList)
        self.layer = layer # topmost raster
        self.modifiers = modifiers # input modifiers

    def getInputModifiers(self):
        return self.modifiers

    def getWorldPolygon(self):
        """
        Return a polygon of world coords
        """
        wldList = []
        for pt in self:
            wldx, wldy = self.layer.coordmgr.display2world(py.x(), pt.y())
            wldList.append(QPointF(wldx, wldy))

        return QPolygonF(wldList)

    def getDisplayData(self):
        """
        Return the numpy array of the display data
        a list for RGB
        """
        return self.layer.image.viewerdata

    def getDisplayValidMask(self):
        """
        Return bool numpy array where valid data
        (not no data and not background)
        """
        mask = self.layer.image.viewermask
        return mask == MASK_IMAGE_VALUE

    @staticmethod
    def maskFunc(x, y, cls):
        """
        Function to be called via numpy.vectorize
        Returns whether x,y are within polygon
        """
        pt = QPoint(x, y)
        return cls.poly.containsPoint(pt, Qt.OddEvenFill)

    def getDisplaySelectionMask(self):
        """
        Get a bool mask in display coords that can then be used to mask
        the data (would probably pay to apply getDisplayValidMask
        to the result)
        """
        # create the output mask - just do polygon checks
        # within the bounding box
        selectMask = numpy.empty_like(self.layer.image.viewermask, 
                                    dtype=numpy.bool)
        selectMask.fill(False)

        # now create a mgrid of x and y values within the bounding box
        bbox = self.boundingRect()
        tlx = bbox.left()
        tly = bbox.top()
        brx = bbox.right()
        bry = bbox.bottom()

        # create a grid of x and y values same size as the data
        dispGridY, dispGridX = numpy.mgrid[tly:bry, tlx:brx]

        # normally would pass self to numpy.vectorize to give access to
        # containsPoint(),  but we are iteratable which causes all
        # sorts of problems. Work around is to create a new class
        # which is not iteratable, but has a reference to self
        class NonIter(object):
            pass
        noniter = NonIter()
        noniter.poly = self

        # vectorize the function which creates a mask of values
        # inside the poly for the bbox area
        vfunc = numpy.vectorize(self.maskFunc, otypes=[numpy.bool])
        bboxmask = vfunc(dispGridX, dispGridY, noniter)

        # insert the bbox mask back into the selectMask
        selectMask[tly:bry, tlx:brx] = bboxmask
        return selectMask
