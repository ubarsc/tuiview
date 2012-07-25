"""
This module contains the CoordManager class, which manages 
the relationship between coordinates for display and coordinates 
in the raster

"""
from __future__ import division
import math

class CoordManager(object):
    """
    Manage the relationship between the coordinate system used
    for display and the other coordinate systems used in the raster 
    file. An instance of this class represents the current relationship
    for a single raster, for a single display. 
    
    Methods are provided for updating the transformation(s), and for 
    transforming between the different coordinate systems. 
    
    Coordinate systems involved are:
        display coords - this notionally corresponds to the screen pixels,
                         although technically it is the units which Qt exposes
                         as its viewport coordinates
        pixel coords   - this is the pixel row/column coordinates in the
                         raster file, using the GDAL conventions
        world coords   - this is the projected coordinate system of the raster 
                         file, using the GDAL coordinates. 
    
    In all cases, coordinate pairs are given with the horizontal coordinate first, 
    i.e. (x, y), even when referring to row/col pairs. Thus, a row/col pair
    will be given as (col, row). 
                         
    """
    def __init__(self):
        # The size of the display window, in display coords
        self.dspWidth = None
        self.dspHeight = None
        # The raster row/col which is to live in the top-left corner of the display
        self.pixTop = None
        self.pixLeft = None
        # And the bottom-right
        self.pixBottom = None
        self.pixRight = None
        # Ratio of raster pixels to display pixels. This defines the zoom level. 
        self.imgPixPerWinPix = None
        # GDAL geotransform array, which defines relationship between
        # pixel and world coords
        self.geotransform = None
    
    def __str__(self):
        """
        For debugging, so I can see what I am set to
        """
        return ("dw:%s dh:%s pt:%s pl:%s pb:%s pr:%s z:%s gt:%s" % (self.dspWidth, self.dspHeight, 
            self.pixTop, self.pixLeft, self.pixBottom, self.pixRight, 
            self.imgPixPerWinPix, self.geotransform))
    
    def setDisplaySize(self, width, height):
        """
        Set display size in units of display coordinate system
        """
        self.dspWidth = width
        self.dspHeight = height
    
    def setTopLeftPixel(self, leftcol, toprow):
        """
        Set row/col of the top/left pixel to display. Args are pixel 
        row/column numbers
        """
        self.pixTop = toprow
        self.pixLeft = leftcol
    
    def setGeoTransform(self, transform):
        """
        Set the GDAL geotransform array
        """
        self.geotransform = transform
    
    def calcZoomFactor(self, right, bottom):
        """
        Calculate the zoom factor, given the currently set top/left
        pixel to display, and the bottom/right pixel desired in display,
        for the currently set display size. 
        
        The zoom factor is calculated to come as close as possible
        to display the given section of  the raster, with the current
        display size, but will correct for any difference in aspect ratio
        between the display window and the desired region of the raster. 
        This means that the given bottom/right values are not always
        actually displayed. One of them, either bottom or right, will 
        be maintained, but the other will be adjusted to match the 
        aspect ratio of the display. For this reason, the bottom/right 
        values are not stored on the object, but instead the calculated 
        zoom factor is stored. The whole of the desired region will be 
        fitted into the display window. 
        
        """
        displayAspectRatio = self.dspWidth / self.dspHeight
        rastWidth = right - self.pixLeft
        rastHeight = bottom - self.pixTop
        rastAspectRatio = rastWidth / rastHeight
        
        if rastAspectRatio < displayAspectRatio:
            rastWidth = int(math.ceil(displayAspectRatio * rastHeight))
            right = self.pixLeft + rastWidth
        elif rastAspectRatio > displayAspectRatio:
            rastHeight = int(math.ceil(rastWidth / displayAspectRatio))
            bottom = self.pixTop + rastHeight
        
        self.imgPixPerWinPix = (right - self.pixLeft + 1) / self.dspWidth
        self.pixBottom = bottom
        self.pixRight = right
    
    def recalcBottomRight(self):
        """
        Called when the window shape has changed. The pixBottom and pixRight
        values are recalculated, based on the new window shape and the existing 
        zoom factor
        
        """
        self.pixRight = self.pixLeft + self.imgPixPerWinPix * self.dspWidth - 1
        self.pixBottom = self.pixTop + self.imgPixPerWinPix * self.dspHeight - 1
    
    def setZoomFactor(self, imgPixPerWinPix):
        """
        Set the zoom to the given value of imgPixPerWinPix. 
        Will then recalcBottomRight(). 
        
        """
        self.imgPixPerWinPix = imgPixPerWinPix
        self.recalcBottomRight()
    
    def display2pixel(self, x, y):
        """
        Convert from display units to raster row/col. Returns
        a tuple (col, row), as floats. 
        """
        col = self.pixLeft + x * self.imgPixPerWinPix
        row = self.pixTop + y * self.imgPixPerWinPix
        return (col, row)
    
    def pixel2display(self, col, row):
        """
        Convert raster row/col to display units. Returns
        a tuple of (x, y). These are int values, as that appears to be
        all Qt will ever deal with. 
        """
        x = int((col - self.pixLeft) / self.imgPixPerWinPix)
        y = int((row - self.pixTop) / self.imgPixPerWinPix)
        return (x, y)
    
    def pixel2world(self, col, row):
        """
        Convert raster row/col to world coordinate system. Returns a
        tuple of floats (x, y)
        """
        gt = self.geotransform
        x = gt[0] + col * gt[1] + row * gt[2]
        y = gt[3] + col * gt[4] + row * gt[5]
        return (x, y)
    
    def world2pixel(self, x, y):
        """
        Convert world x,y coordinates to raster row/col. Returns
        a tuple (col, row), as floats. 
        """
        gt = self.geotransform

        # Classic 2x2 matrix inversion
        det = gt[1] * gt[5] - gt[2] * gt[4]
        col = (gt[5] * (x - gt[0]) - gt[2] * (y - gt[3])) / det
        row = (-gt[4] * (x - gt[0]) + gt[1] * (y - gt[3])) / det
        return (col, row)
        
    def display2world(self, dspX, dspY):
        """
        Convert display (x, y) to world coordinates. Returns
        a tuple of floats (x, y), in the world coordinate system
        """
        (col, row) = self.display2pixel(dspX, dspY)
        (wldX, wldY) = self.pixel2world(col, row)
        return (wldX, wldY)
    
    def world2display(self, wldX, wldY):
        """
        Convert world (x, y) to display coordinates. Returns
        a tuple of int values (x, y) in display coordinate system
        """
        (col, row) = self.world2pixel(wldX, wldY)
        (dspX, dspY) = self.pixel2display(col, row)
        return (dspX, dspY)

