
"""
Module that contains ViewerStretch and StretchRule classes
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

import io
import copy
import json
from osgeo import gdal
from . import viewererrors

gdal.UseExceptions()

# constants for specifying how to display an image 
VIEWER_MODE_DEFAULT = 0
VIEWER_MODE_COLORTABLE = 1
VIEWER_MODE_GREYSCALE = 2
VIEWER_MODE_RGB = 3
VIEWER_MODE_PSEUDOCOLOR = 4
VIEWER_MODE_RGBA = 5

# how to stretch an image
VIEWER_STRETCHMODE_DEFAULT = 0
VIEWER_STRETCHMODE_NONE = 1  # color table, or pre stretched data
VIEWER_STRETCHMODE_LINEAR = 2
VIEWER_STRETCHMODE_STDDEV = 3
VIEWER_STRETCHMODE_HIST = 4
# below only valid with VIEWER_MODE_RGB/VIEWER_MODE_RGBA
VIEWER_STRETCHMODE_LINEAR_VAR = 5  # like VIEWER_STRETCHMODE_LINEAR, but min/max varies between bands
VIEWER_STRETCHMODE_STDDEV_VAR = 6  # like VIEWER_STRETCHMODE_STDDEV, but stddev varies between bands
VIEWER_STRETCHMODE_HIST_VAR = 7  # like VIEWER_STRETCHMODE_HIST, but min/max varies between bands

# for storing a stretch within a file
VIEWER_STRETCH_METADATA_KEY = 'VIEWER_STRETCH'

# default stretchparams
VIEWER_DEFAULT_STDDEV = 2.0
VIEWER_DEFAULT_HISTMIN = 0.1
VIEWER_DEFAULT_HISTMAX = 0.9

VIEWER_DEFAULT_NOCOLOR = (0, 0, 0, 0)


class ViewerStretch:
    """
    Class that represents the stretch. 
    Use the methods here to set the type of
    stretch you want and the bands used
    """
    def __init__(self):
        self.mode = VIEWER_MODE_DEFAULT
        self.stretchmode = VIEWER_STRETCHMODE_DEFAULT
        self.stretchparam = None
        self.bands = None
        self.rampName = None  # from colorbrewer2.org
        self.nodata_rgba = VIEWER_DEFAULT_NOCOLOR
        self.background_rgba = VIEWER_DEFAULT_NOCOLOR
        self.nan_rgba = VIEWER_DEFAULT_NOCOLOR
        self.attributeTableSize = None  # override with size of attribute table 
        # if one exists
        # LUT will then be created with this size
        self.readLUTFromText = None  # if not None, path to text 
        # file to read LUT out of
        self.readLUTFromGDAL = None  # if not None, path to GDAL dataset 
        # to read LUT out of
        self.readLUTFromString = None  # if not None, string with LUT

    def setBands(self, bands):
        "Set the bands to use. bands should be a tuple of 1-based ints"
        self.bands = bands

    def setColorTable(self):
        "Use the color table in the image"
        self.mode = VIEWER_MODE_COLORTABLE
        self.stretchmode = VIEWER_STRETCHMODE_NONE

    def setGreyScale(self):
        "Display a single band in greyscale"
        self.mode = VIEWER_MODE_GREYSCALE

    def setPseudoColor(self, rampName):
        "Display with given color ramp"
        self.mode = VIEWER_MODE_PSEUDOCOLOR
        self.rampName = rampName

    def setRGB(self):
        "Display 3 bands as RGB"
        self.mode = VIEWER_MODE_RGB
        
    def setRGBA(self):
        "Display 4 bands as RGBA"
        self.mode = VIEWER_MODE_RGBA

    def setNoStretch(self):
        "Don't do a stretch - data is already stretched"
        self.stretchmode = VIEWER_STRETCHMODE_NONE

    def setLinearStretch(self, minVal=None, maxVal=None):
        """
        Just stretch linearly between min and max values
        if None, range of the data used. Just for single
        band, or all bands the same
        """
        self.stretchmode = VIEWER_STRETCHMODE_LINEAR
        self.stretchparam = (minVal, maxVal)
        
    def setLinearStretchVar(self, minMaxList):
        """
        Like setLinearStretch, but uses a list of (min, max) tuples
        - one for each band
        """
        if len(minMaxList) != len(self.bands):
            raise viewererrors.InvalidStretch("must pass list the same length as bands")
        if self.mode not in [VIEWER_MODE_RGB, VIEWER_MODE_RGBA]:
            raise viewererrors.InvalidStretch("Var stretch only available for RGB and RGBA")
        self.stretchmode = VIEWER_STRETCHMODE_LINEAR_VAR
        self.stretchparam = minMaxList

    def setStdDevStretch(self, stddev=VIEWER_DEFAULT_STDDEV):
        "Do a standard deviation stretch"
        self.stretchmode = VIEWER_STRETCHMODE_STDDEV
        self.stretchparam = (stddev,)
        
    def setStdDevStretchVar(self, stddevList):
        """
        Like setStdDevStretch, but uses a list of stddevs
        - one for each band
        """
        if len(stddevList) != len(self.bands):
            raise viewererrors.InvalidStretch("must pass list the same length as bands")
        if self.mode not in [VIEWER_MODE_RGB, VIEWER_MODE_RGBA]:
            raise viewererrors.InvalidStretch("Var stretch only available for RGB and RGBA")
        self.stretchmode = VIEWER_STRETCHMODE_STDDEV_VAR
        self.stretchparam = stddevList

    def setHistStretch(self, minVal=VIEWER_DEFAULT_HISTMIN, 
            maxVal=VIEWER_DEFAULT_HISTMAX):
        "Do a histogram stretch"
        self.stretchmode = VIEWER_STRETCHMODE_HIST
        self.stretchparam = (minVal, maxVal)
        
    def setHistStretchVar(self, minMaxList):
        """
        List setHistStretch, but uses a list of (min, max) tuples
        - one for each band
        """
        if len(minMaxList) != len(self.bands):
            raise viewererrors.InvalidStretch("must pass list the same length as bands")
        if self.mode not in [VIEWER_MODE_RGB, VIEWER_MODE_RGBA]:
            raise viewererrors.InvalidStretch("Var stretch only available for RGB and RGBA")
        self.stretchmode = VIEWER_STRETCHMODE_HIST_VAR
        self.stretchparam = minMaxList

    def setNoDataRGBA(self, rgba):
        "Set the RGBA to display No Data values as"
        self.nodata_rgba = rgba

    def setBackgroundRGBA(self, rgba):
        "Set the RGB to display Background areas as"
        self.background_rgba = rgba

    def setNaNRGBA(self, rgba):
        "Set the RGB to display NaN areas as"
        self.nan_rgba = rgba

    def setAttributeTableSize(self, size):
        """
        set with size of attribute table if one exists
        LUT will then be created with this size
        set to None for default behaviour
        """
        self.attributeTableSize = size

    def setLUTFromText(self, fname):
        "Read in the LUT from specified text file"
        self.readLUTFromText = fname

    def setLUTFromGDAL(self, fname):
        "Read LUT from specified GDAL dataset"
        self.readLUTFromGDAL = fname
        
    def setLUTFromString(self, s):
        "Read LUT from string"
        self.readLUTFromString = s

    def toString(self):
        """
        Convert to a JSON encoded string
        """
        rep = {'mode': self.mode, 'stretchmode': self.stretchmode,
            'stretchparam': self.stretchparam, 'bands': self.bands,
            'nodata_rgba': self.nodata_rgba, 'rampname': self.rampName,
            'background_rgba': self.background_rgba, 
            'nan_rgba': self.nan_rgba}
        return json.dumps(rep)

    @staticmethod
    def fromTextFileWithLUT(fname):
        """
        For reading a .stretch file.
        The stretch is read out of the first line and 
        setLUTFromText called with this file also
        since .stretch files contain both
        """
        with open(fname) as fileobj:
            s = fileobj.readline()
        stretch = ViewerStretch.fromString(s)
        stretch.setLUTFromText(fname)
        return stretch

    @staticmethod
    def fromGDALFileWithLUT(fname):
        """
        For reading a GDAL file with stretch and LUT
        saved.
        The stretch is read out and
        setLUTFromGDAL called with this file also
        """
        gdaldataset = gdal.Open(fname)
        stretch = ViewerStretch.readFromGDAL(gdaldataset)
        del gdaldataset
        if stretch is not None:
            stretch.setLUTFromGDAL(fname)
        return stretch
        
    @staticmethod
    def fromStringWithLUT(stretchAndLUT):
        """
        stretchAndLUT contains the stretch and LUT
        """
        with io.StringIO(stretchAndLUT) as fileobj:
            s = fileobj.readline()
        stretch = ViewerStretch.fromString(s)
        stretch.setLUTFromString(stretchAndLUT)
        return stretch
    
    @staticmethod
    def fromString(string):
        """
        Create a ViewerStretch instance from a json encoded
        string created by toString()
        """
        rep = json.loads(str(string))

        obj = ViewerStretch()
        obj.mode = rep['mode']
        obj.stretchmode = rep['stretchmode']
        obj.stretchparam = rep['stretchparam']
        obj.bands = rep['bands']
        if 'nodata_rgba' in rep:
            obj.nodata_rgba = rep['nodata_rgba']
        if 'background_rgba' in rep:
            obj.background_rgba = rep['background_rgba']
        if 'nan_rgba' in rep:
            obj.nan_rgba = rep['nan_rgba']
        if 'rampname' in rep:
            obj.rampName = rep['rampname']
        return obj

    def writeToGDAL(self, gdaldataset):
        """
        Write this stretch into the GDAL file
        assumed the dataset opened with GA_Update
        Good idea to reopen any other handles to dataset
        """
        string = self.toString()
        gdaldataset.SetMetadataItem(VIEWER_STRETCH_METADATA_KEY, string)

    @staticmethod
    def deleteFromGDAL(gdaldataset):
        """
        Remove the stretch entry from this dataset
        assumed the dataset opened with GA_Update
        """
        # can't seem to delete an item so set to empty string
        # we test for this explicity below
        gdaldataset.SetMetadataItem(VIEWER_STRETCH_METADATA_KEY, '')

    @staticmethod
    def readFromGDAL(gdaldataset):
        """
        See if there is an entry in the GDAL metadata,
        and return a ViewerStretch instance, otherwise None
        """
        obj = None
        string = gdaldataset.GetMetadataItem(VIEWER_STRETCH_METADATA_KEY)
        if string is not None and string != '':
            obj = ViewerStretch.fromString(string)
        return obj


# Comparison constants to use in StretchRule
VIEWER_COMP_LT = 0  # Less than
VIEWER_COMP_GT = 1  # greater than
VIEWER_COMP_EQ = 2  # equal


class StretchRule:
    """
    Class that represents a 'rule' and a stretch
    to be applied when that rule matches.
    The rule contains information about number
    of bands in a dataset and how to compare, plus
    if a dataset has a colour table in a particular band
    """
    def __init__(self, comp, value, ctband, stretch):
        self.comp = comp
        self.value = value
        self.ctband = ctband  # or None
        self.stretch = copy.copy(stretch) 
        # can reuse stretch object for something else

    def isMatch(self, gdaldataset):
        """
        Does this rule match the given dataset?
        """
        match = False
        # check band numbers
        if self.comp == VIEWER_COMP_LT:
            match = gdaldataset.RasterCount < self.value
        elif self.comp == VIEWER_COMP_GT:
            match = gdaldataset.RasterCount > self.value
        elif self.comp == VIEWER_COMP_EQ:
            match = gdaldataset.RasterCount == self.value
        else:
            msg = 'invalid value for comparison'
            raise viewererrors.InvalidParameters(msg)

        if (match and self.ctband is not None and
                self.ctband <= gdaldataset.RasterCount):
            # we match the number of bands
            # but we need to check there is a color 
            # table in the specified band. Either via RAT or colour table
            gdalband = gdaldataset.GetRasterBand(self.ctband)
            rat = gdalband.GetDefaultRAT()
            match = False
            # only check if file is thematic anyway
            if rat is not None:
                # we really need to check only that the RAT
                # reports that we have the right columns
                hasRed = False
                hasGreen = False
                hasBlue = False
                hasAlpha = False
                rat = gdalband.GetDefaultRAT()
                if rat is not None:
                    ncols = rat.GetColumnCount()
                    for col in range(ncols):
                        usage = rat.GetUsageOfCol(col)
                        if usage == gdal.GFU_Red:
                            hasRed = True
                        elif usage == gdal.GFU_Green:
                            hasGreen = True
                        elif usage == gdal.GFU_Blue:
                            hasBlue = True
                        elif usage == gdal.GFU_Alpha:
                            hasAlpha = True

                match = hasRed and hasGreen and hasBlue and hasAlpha
            if not match:
                # fall back to use the old style color table if RAT colour columns not present
                colorTable = gdalband.GetColorTable()
                match = colorTable is not None
        
        return match

    def toString(self):
        """
        Convert to a JSON encoded string
        """
        rep = {'comp': self.comp, 
            'value': self.value, 'ctband': self.ctband,
            'stretch': self.stretch.toString()}
        return json.dumps(rep)

    @staticmethod
    def fromString(string):
        """
        Create a StretchRule instance from a json encoded
        string created by toString()
        """
        rep = json.loads(str(string))

        stretch = ViewerStretch.fromString(rep['stretch'])
        obj = StretchRule(rep['comp'], rep['value'], 
                    rep['ctband'], stretch)
        return obj
