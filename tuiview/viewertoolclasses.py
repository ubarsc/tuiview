
"""
Supporting classes for tools in the ViewerWidget
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

from PySide6.QtGui import QPolygon, QPolygonF
from PySide6.QtCore import Qt, QPoint, QPointF
import numpy
from osgeo import ogr

from .viewerLUT import MASK_IMAGE_VALUE
from . import vectorrasterizer


class ToolInfo(QPolygon):
    """
    Class derived from QPolygon that contains the poly
    that the user selected, but has some other methods
    """
    def __init__(self, pointList, layer, modifiers):
        QPolygon.__init__(self, pointList)
        self.layer = layer  # topmost raster
        self.modifiers = modifiers  # input modifiers

    def getInputModifiers(self):
        return self.modifiers

    def getWorldPolygon(self):
        """
        Return a polygon of world coords
        """
        wldList = []
        for pt in self:
            wldx, wldy = self.layer.coordmgr.display2world(pt.x(), pt.y())
            wldList.append(QPointF(wldx, wldy))

        return QPolygonF(wldList)

    def getOGRGeometry(self):
        """
        Return a ogr.Geometry instance. Derived classes to implement
        """
        raise NotImplementedError()

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


class PolygonToolInfo(ToolInfo):
    """
    Class derived from ToolInfo that contains the poly etc
    but has a getDisplaySelectionMask() mask to create a 
    mask inside poly
    """
    def __init__(self, pointList, layer, modifiers):
        ToolInfo.__init__(self, pointList, layer, modifiers)

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
        # copy all the vertices so they can be used to fill in poly
        size = len(self)
        xDsp = numpy.empty((size,), dtype=float)
        yDsp = numpy.empty((size,), dtype=float)
        for idx, p in enumerate(self):
            xDsp[idx] = p.x()
            yDsp[idx] = p.y()
            
        xWld, yWld = self.layer.coordmgr.display2world(xDsp, yDsp)
        minY = yWld.min()
        maxY = yWld.max()

        extent = self.layer.coordmgr.getWorldExtent()
        (xsize, ysize) = (self.layer.coordmgr.dspWidth, 
                    self.layer.coordmgr.dspHeight)
                
        mask = vectorrasterizer.fillVertices(xWld, yWld, extent, 
                        xsize, ysize, minY, maxY)
        mask = mask == 1

        return mask

    def getOGRGeometry(self):
        """
        Return a ogr.Geometry instance
        """
        # Create ring
        ring = ogr.Geometry(ogr.wkbLinearRing)
        for pt in self:
            wldx, wldy = self.layer.coordmgr.display2world(pt.x(), pt.y())
            ring.AddPoint(wldx, wldy)

        poly = ogr.Geometry(ogr.wkbPolygon)
        poly.AddGeometry(ring)

        return poly
        

class PolylineToolInfo(ToolInfo):
    """
    Class derived from ToolInfo that contains the polyline etc
    has method for getting profile
    """
    def __init__(self, pointList, layer, modifiers):
        ToolInfo.__init__(self, pointList, layer, modifiers)

    def getProfile(self):
        lastPoint = self[0]
        # bresenhamline does not include the very first point
        profile = numpy.array([[lastPoint.x(), lastPoint.y()]])
        distance = numpy.array([0.0])
        for pt in self[1:]:
            # need to be 2-d arrays for some reason
            start = numpy.array([[lastPoint.x(), lastPoint.y()]])
            end = numpy.array([[pt.x(), pt.y()]])
            # do the bresenham
            newprofile = bresenhamline(start, end, max_iter=-1)
            # add to our array of points
            profile = numpy.append(profile, newprofile, axis=0)

            # now work out distance
            # make relative to first point
            tmpx = newprofile[..., 0] - lastPoint.x()
            tmpy = newprofile[..., 1] - lastPoint.y()
            # work out diag distance and make it cumulative
            newdist = numpy.sqrt(tmpx**2 + tmpy**2) + distance[-1]
            distance = numpy.append(distance, newdist)

            lastPoint = pt

        # see http://docs.scipy.org/doc/numpy/user/basics.indexing.html
        # #indexing-multi-dimensional-arrays
        profiley = profile[..., 1]
        profilex = profile[..., 0]

        # index these points in the data
        data = self.getDisplayData()
        if isinstance(data, list):
            # RGB
            profiledata = []
            for banddata in data:
                pdata = banddata[profiley, profilex]
                profiledata.append(pdata)
        else:
            # single band
            profiledata = data[profiley, profilex]
        
        # and the mask
        mask = self.getDisplayValidMask()
        profilemask = mask[profiley, profilex]

        # convert distance to metres
        coordmgr = self.layer.coordmgr
        if (coordmgr.imgPixPerWinPix is not None and 
                coordmgr.geotransform is not None):
            profiledistance = distance * (coordmgr.imgPixPerWinPix * 
                                    coordmgr.geotransform[1])
        else:
            profiledistance = distance

        return profiledata, profilemask, profiledistance

    def getOGRGeometry(self):
        """
        Return a ogr.Geometry instance
        """
        geom = ogr.Geometry(ogr.wkbLineString)
        for pt in self:
            wldx, wldy = self.layer.coordmgr.display2world(pt.x(), pt.y())
            geom.AddPoint(wldx, wldy)
        return geom


# the following stolen from 
# http://code.activestate.com/recipes/578112-bresenhams-line-algorithm-in-n-dimensions/
def _bresenhamline_nslope(slope):
    """
    Normalize slope for Bresenham's line algorithm.

    >>> s = np.array([[-2, -2, -2, 0]])
    >>> _bresenhamline_nslope(s)
    array([[-1., -1., -1.,  0.]])

    >>> s = np.array([[0, 0, 0, 0]])
    >>> _bresenhamline_nslope(s)
    array([[ 0.,  0.,  0.,  0.]])

    >>> s = np.array([[0, 0, 9, 0]])
    >>> _bresenhamline_nslope(s)
    array([[ 0.,  0.,  1.,  0.]])
    """
    scale = numpy.amax(numpy.abs(slope), axis=1).reshape(-1, 1)
    zeroslope = (scale == 0).all(1)
    scale[zeroslope] = numpy.ones(1)
    normalizedslope = numpy.array(slope, dtype=numpy.double) / scale
    normalizedslope[zeroslope] = numpy.zeros(slope[0].shape)
    return normalizedslope


def _bresenhamlines(start, end, max_iter):
    """
    Returns npts lines of length max_iter each. (npts x max_iter x dimension)::

        >>> s = np.array([[3, 1, 9, 0],[0, 0, 3, 0]])
        >>> _bresenhamlines(s, np.zeros(s.shape[1]), max_iter=-1)
        array([[[ 3,  1,  8,  0],
                [ 2,  1,  7,  0],
                [ 2,  1,  6,  0],
                [ 2,  1,  5,  0],
                [ 1,  0,  4,  0],
                [ 1,  0,  3,  0],
                [ 1,  0,  2,  0],
                [ 0,  0,  1,  0],
                [ 0,  0,  0,  0]],
        <BLANKLINE>
               [[ 0,  0,  2,  0],
                [ 0,  0,  1,  0],
                [ 0,  0,  0,  0],
                [ 0,  0, -1,  0],
                [ 0,  0, -2,  0],
                [ 0,  0, -3,  0],
                [ 0,  0, -4,  0],
                [ 0,  0, -5,  0],
                [ 0,  0, -6,  0]]])
    """
    if max_iter == -1:
        max_iter = numpy.amax(numpy.amax(numpy.abs(end - start), axis=1))
    _, dim = start.shape
    nslope = _bresenhamline_nslope(end - start)

    # steps to iterate on
    stepseq = numpy.arange(1, max_iter + 1)
    stepmat = numpy.tile(stepseq, (dim, 1)).T

    # some hacks for broadcasting properly
    bline = start[:, numpy.newaxis, :] + nslope[:, numpy.newaxis, :] * stepmat

    # Approximate to nearest int
    return numpy.array(numpy.rint(bline), dtype=start.dtype)


def bresenhamline(start, end, max_iter=5):
    """
    Returns a list of points from (start, end] by ray tracing a line b/w the
    points.
    Parameters:
    * start: An array of start points (number of points x dimension)
    * end:   An end points (1 x dimension) or An array of end point corresponding to each start point (number of points x dimension)
    * max_iter: Max points to traverse. if -1, maximum number of required points are traversed

    Returns:
    * linevox (n x dimension) A cumulative array of all points traversed by all the lines so far.

    ::

        >>> s = np.array([[3, 1, 9, 0],[0, 0, 3, 0]])
        >>> bresenhamline(s, np.zeros(s.shape[1]), max_iter=-1)
        array([[ 3,  1,  8,  0],
               [ 2,  1,  7,  0],
               [ 2,  1,  6,  0],
               [ 2,  1,  5,  0],
               [ 1,  0,  4,  0],
               [ 1,  0,  3,  0],
               [ 1,  0,  2,  0],
               [ 0,  0,  1,  0],
               [ 0,  0,  0,  0],
               [ 0,  0,  2,  0],
               [ 0,  0,  1,  0],
               [ 0,  0,  0,  0],
               [ 0,  0, -1,  0],
               [ 0,  0, -2,  0],
               [ 0,  0, -3,  0],
               [ 0,  0, -4,  0],
               [ 0,  0, -5,  0],
               [ 0,  0, -6,  0]])
    """
    # Return the points as a single array
    return _bresenhamlines(start, end, max_iter).reshape(-1, start.shape[-1])

