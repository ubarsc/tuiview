"""
This module contains the CoordManager class, which manages 
the relationship between coordinates for display and coordinates 
in the raster

"""
from __future__ import division

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
        # Ratio of raster pixels to display pixels. This defines the zoom level. 
        self.imgPixPerWinPix = None
        # GDAL geotransform array, which defines relationship between
        # pixel and world coords
        self.geotransform = None
    
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
    
    def setZoomFactor(self, imgPixPerWinPix):
        """
        Set the zoom factor, as ratio of number of raster 
        pixels per display pixel. This is a float value. 
        """
        self.imgPixPerWinPix = imgPixPerWinPix
    
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

