
"""
Module that contains the ViewerLUT class
amongst other things
"""

import sys
import numpy
from PyQt4.QtGui import QImage
from osgeo import gdal
from . import viewererrors


# constants for specifying how to display an image 
VIEWER_MODE_DEFAULT = 0
VIEWER_MODE_COLORTABLE = 1
VIEWER_MODE_GREYSCALE = 2
VIEWER_MODE_RGB = 3

# how to stretch an image
VIEWER_STRETCHMODE_DEFAULT = 0
VIEWER_STRETCHMODE_NONE = 1 # color table, or pre stretched data
VIEWER_STRETCHMODE_LINEAR = 2
VIEWER_STRETCHMODE_STDDEV = 3
VIEWER_STRETCHMODE_HIST = 4

# are we big endian or not?
BIG_ENDIAN = sys.byteorder == 'big'

# scale, offset, size, min, max
INTEGER_SCALEOFFSETS = {gdal.GDT_Byte : (1, 0, 256, 0, 255),
                        gdal.GDT_UInt16 : (1, 0, 65536, 0, 65535),
                        gdal.GDT_Int16 : (1, -32768, 65536, -32768, 32767) }
DEFAULT_LUTSIZE = 1024 # if not one of the types above

# Qt expects the colours in BGRA order packed into
# a 32bit int. We do this by inserting stuff into
# a 8 bit numpy array, but this is endian specific
if BIG_ENDIAN:
    CODE_TO_LUTINDEX = {'b' : 3, 'g' : 2, 'r' : 1, 'a' : 0}
else:
    CODE_TO_LUTINDEX = {'b' : 0, 'g' : 1, 'r' : 2, 'a' : 3}

# to save creating this tuple all the time
RGB_CODES = ('r', 'g', 'b')

class ViewerStretch(object):
    """
    Class that represents the stretch. 
    Use the methods here to set the type of
    stretch you want.
    """
    def __init__(self):
        self.mode = VIEWER_MODE_DEFAULT
        self.stretchmode = VIEWER_STRETCHMODE_DEFAULT
        self.stretchparam = None

    def setColorTable(self):
        "Use the color table in the image"
        self.mode = VIEWER_MODE_COLORTABLE
        self.stretchmode = VIEWER_STRETCHMODE_NONE

    def setGreyScale(self):
        "Display a single band in greyscale"
        self.mode = VIEWER_MODE_GREYSCALE

    def setRGB(self):
        "Display 3 bands as RGB"
        self.mode = VIEWER_MODE_RGB

    def setNoStretch(self):
        "Don't do a stretch - data is already stretched"
        self.stretchmode = VIEWER_STRETCHMODE_NONE

    def setLinearStretch(self):
        "Just stretch linearly between min and max values"
        self.stretchmode = VIEWER_STRETCHMODE_LINEAR

    def setStdDevStretch(self, stddev=2.0):
        "Do a standard deviation stretch"
        self.stretchmode = VIEWER_STRETCHMODE_STDDEV
        self.stretchparam = stddev

    def setHistStretch(self, min=0.025, max=0.01):
        "Do a histogram stretch"
        self.stretchmode = VIEWER_STRETCHMODE_HIST
        self.stretchparam = (min, max)

    @staticmethod
    def createForFile(filename):
        """
        See if there is an entry in the GDAL metadata,
        otherwise construct using standard rules
        """
        return None


class BandLUTInfo(object):
    """
    Class that holds information about a band's LUT
    """
    def __init__(self, scale, offset, lutsize, min, max):
        self.scale = scale
        self.offset = offset
        self.lutsize = lutsize
        self.min = min
        self.max = max


class ViewerLUT(object):
    """
    Class that handles the Lookup Table
    used for transformation between raw
    data and stretched data
    """
    def __init__(self):
        # array shape [lutsize,4] for color table and greyscale
        # shape [3, lutsize] for RGB
        self.lut = None
        # a single BandLUTInfo instance for single band
        # dictionary keyed on code for RGB
        self.bandinfo = None

    def saveToFile(self, fname):
        """
        Save current stretch to a text file
        so it can be stored and manipulated
        """
        # must to scales, offsets, mins and maxs also
        numpy.savetxt(fname, self.lut, fmt='%6.3f')

    def loadColorTable(self, gdalband):
        """
        Creates a LUT for a single band using 
        the color table
        """
        ct = gdalband.GetColorTable()
        if ct is not None:

            if ct.GetPaletteInterpretation() != gdal.GPI_RGB:
                msg = 'only handle RGB color tables'
                raise viewererrors.InvalidColorTable(msg)

            codes = ('r', 'g', 'b', 'a')
            # read in the colour table as lut
            ctcount = ct.GetCount()
            for i in range(ctcount):
                entry = ct.GetColorEntry(i)
                # entry is RGBA, need to store as BGRA - always ignore alpha for now
                for (value, code) in zip(entry, codes):
                    lutindex = CODE_TO_LUTINDEX[code]
                    self.lut[i,lutindex] = value
        else:
            msg = 'No color table present'
            raise viewererrors.InvalidColorTable(msg)


    def createStretchLUT(self, gdalband, stretch, bandinfo):
        """
        Creates a LUT for a single band using the stretch
        method specified and returns it
        """

        if stretch.stretchmode == VIEWER_STRETCHMODE_NONE:
            # just a linear stretch between 0 and 255
            # for the range of possible values
            lut = numpy.linspace(0, 255, num=bandinfo.lutsize).astype(numpy.uint8)
            return lut

        # other methods below require statistics
        minVal, maxVal, mean, stdDev = self.getStatisticsWithProgress(gdalband)

        # code below sets stretchMin and stretchMax

        if stretch.stretchmode == VIEWER_STRETCHMODE_LINEAR:
            # stretch between reported min and max
            stretchMin = minVal
            stretchMax = maxVal

        elif stretch.stretchmode == VIEWER_STRETCHMODE_STDDEV:
            # linear stretch n std deviations from the mean
            nstddev = stretch.stretchparam

            stretchMin = mean - (nstddev * stdDev)
            if stretchMin < minVal:
                stretchMin = minVal
            stretchMax = mean + (nstddev * stdDev)
            if stretchMax > maxVal:
                stretchMax = maxVal

        elif stretch.stretchmode == VIEWER_STRETCHMODE_HIST:
            # must do progress
            numBins = int(numpy.ceil(maxVal - minVal))
            histo = gdalband.GetHistogram(min=minVal, max=maxVal, buckets=numBins, include_out_of_range=0, approx_ok=0)
            sumPxl = sum(histo)

            histmin, histmax = stretch.stretchparam

            # Pete: what is this based on?
            bandLower = sumPxl * histmin
            bandUpper = sumPxl * histmax

            # calc min and max from histo
            # find bin number that bandLower/Upper fall into 
            # maybe we can do better with numpy?
            sumVals = 0
            for i in range(numBins):
                sumVals = sumVals + histo[i]
                if sumVals > bandLower:
                    stretchMin = minVal + ((maxVal - minVal) * (i / numBins))
                    break
            sumVals = 0
            for i in range(numBins):
                sumVals = sumVals + histo[-i]
                if sumVals > bandUpper:
                    stretchMax = maxVal + ((maxVal - minVal) * ((numBins - i - 1) / numBins))
                    break

        else:
            msg = 'unsupported stretch mode'
            raise viewererrors.InvalidParameters(msg)

        # create an array with the actual values so we can index/max
        values = numpy.linspace(bandinfo.min, bandinfo.max, bandinfo.lutsize)
        
        # the location of the min/max values in the LUT
        minLoc = int((stretchMin + bandinfo.offset) * bandinfo.scale)
        maxLoc = int((stretchMax + bandinfo.offset) * bandinfo.scale)

        # create the LUT
        lut = numpy.empty(bandinfo.lutsize, numpy.uint8, 'C')

        # set values outside to 0/255
        lut = numpy.where(values < stretchMin, 0, lut)
        lut = numpy.where(values >= stretchMax, 255, lut)

        # create the stretch between stretchMin/Max ind insert into LUT 
        # at right place
        linstretch = numpy.linspace(0, 255, num=(maxLoc - minLoc)).astype(numpy.uint8)
        lut[minLoc:maxLoc] = linstretch

        return lut

    def getStatisticsWithProgress(self, gdalband):
        """
        Helper method. Just quickly returns the stats if
        they are easily available. Calculates them using
        the supplied progress if not.
        """
        gdal.ErrorReset()
        minVal, maxVal, mean, stdDev = gdalband.GetStatistics(0, 0)
        if gdal.GetLastErrorNo() != gdal.CE_None:
            # need to actually calculate them
            # must do progress callback
            print 'falling back on calculating stats...'
            gdal.ErrorReset()
            minVal, maxVal, mean, stdDev = gdalband.ComputeStatistics(0)

            if gdal.GetLastErrorNo() != gdal.CE_None:
                msg = 'unable to calculate statistics'
                raise viewererrors.StatisticsError(msg)

        return minVal, maxVal, mean, stdDev

    def getInfoForBand(self, gdalband):
        """
        Using either standard numbers, or based
        upon the range of numbers in the image, 
        return the BandLUTInfo instance
        to be used in the LUT for this image
        """
        dtype = gdalband.DataType
        if dtype in INTEGER_SCALEOFFSETS:
            (scale, offset, lutsize, min, max) = INTEGER_SCALEOFFSETS[dtype]
        else:
            # must be float or 32bit int
            # scale to the range of the data
            minVal, maxVal, mean, stdDev = self.getStatisticsWithProgress(gdalband)
            scale = -minVal
            offset = (maxVal - minVal) / DEFAULT_LUTSIZE
            lutsize = DEFAULT_LUTSIZE
            min = minVal
            max = maxVal

        info = BandLUTInfo(scale, offset, lutsize, min, max)
        return info

    def createLUT(self, dataset, bands, stretch):
        """
        Main function
        """
        if stretch.mode == VIEWER_MODE_DEFAULT or stretch.stretchmode == VIEWER_STRETCHMODE_DEFAULT:
            msg = 'must set mode and stretchmode'
            raise viewererrors.InvalidStretch(msg)

        # decide what to do based on the ode
        if stretch.mode == VIEWER_MODE_COLORTABLE:

            if len(bands) > 1:
                msg = 'specify one band when opening a color table image'
                raise viewererrors.InvalidParameters(msg)

            if stretch.stretchmode != VIEWER_STRETCHMODE_NONE:
                msg = 'stretchmode should be set to none for color tables'
                raise viewererrors.InvalidParameters(msg)

            band = bands[0]
            gdalband = dataset.GetRasterBand(band)

            self.bandinfo = self.getInfoForBand(gdalband)

            # LUT is shape [lutsize,4] so we can index from a single 
            # band and get the brga (native order)
            self.lut = numpy.empty((self.bandinfo.lutsize, 4), numpy.uint8, 'C')

            if self.bandinfo.scale != 1:
                msg = 'Can only apply colour table to images with 1:1 scale on LUT'
                raise viewererrors.InvalidColorTable(msg)

            # load the color table
            self.loadColorTable(gdalband)

        elif stretch.mode == VIEWER_MODE_GREYSCALE:
            if len(bands) > 1:
                msg = 'specify one band when opening a greyscale image'
                raise viewererrors.InvalidParameters(msg)

            band = bands[0]
            gdalband = dataset.GetRasterBand(band)

            self.bandinfo = self.getInfoForBand(gdalband)

            # LUT is shape [lutsize,4] so we can index from a single 
            # band and get the brga (native order)
            self.lut = numpy.empty((self.bandinfo.lutsize, 4), numpy.uint8, 'C')

            lut = self.createStretchLUT( gdalband, stretch, self.bandinfo )

            # copy to all bands
            for code in RGB_CODES:
                lutindex = CODE_TO_LUTINDEX[code]
                self.lut[...,lutindex] = lut

        elif stretch.mode == VIEWER_MODE_RGB:
            if len(bands) != 3:
                msg = 'must specify 3 bands when opening rgb'
                raise viewererrors.InvalidParameters(msg)


            self.bandinfo = {}
            self.lut = None

            # user supplies RGB
            for (band, code) in zip(bands, RGB_CODES):
                gdalband = dataset.GetRasterBand(band)

                bandinfo = self.getInfoForBand(gdalband)

                if self.lut == None:
                    # LUT is shape [3,lutsize]. We apply the stretch seperately
                    # to each band. Order is RGB (native order to make things easier)
                    self.lut = numpy.empty((3, bandinfo.lutsize), numpy.uint8, 'C')
                elif self.lut.shape[1] != bandinfo.lutsize:
                    msg = 'cannot handle bands with different LUT sizes'
                    raise viewererrors.InvalidStretch(msg)

                self.bandinfo[code] = bandinfo

                lutindex = CODE_TO_LUTINDEX[code]
                # create stretch for each band
                lut = self.createStretchLUT( gdalband, stretch, bandinfo )

                self.lut[lutindex] = lut
            
        else:
            msg = 'unsupported display mode'
            raise viewererrors.InvalidParameters(msg)

    def applyLUTSingle(self, data):
        """
        Apply the LUT to a single band (color table
        or greyscale image) and return the result as
        a QImage
        """
        # apply scaling
        data = (data + self.bandinfo.offset) * self.bandinfo.scale

        # do the lookup
        bgra = self.lut[data]
        winysize, winxsize = data.shape
        
        # create QImage from numpy array
        # see http://www.mail-archive.com/pyqt@riverbankcomputing.com/msg17961.html
        image = QImage(bgra.data, winxsize, winysize, QImage.Format_RGB32)
        image.ndarray = data # hold on to the data in case we
                            # want to change the lut and quickly re-apply it
        return image

    def applyLUTRGB(self, datalist):
        """
        Apply LUT to 3 bands of imagery
        passed as a lit of arrays.
        Return a QImage
        """
        winysize, winxsize = datalist[0].shape

        # create blank array to stretch into
        bgra = numpy.empty((winysize, winxsize, 4), numpy.uint8, 'C')
        for (data, code) in zip(datalist, RGB_CODES):
            lutindex = CODE_TO_LUTINDEX[code]
            bandinfo = self.bandinfo[code]
            
            # apply scaling
            data = (data + bandinfo.offset) * bandinfo.scale
            # do the lookup
            bgra[...,lutindex] = self.lut[lutindex][data]
        
        # turn into QImage
        image = QImage(bgra.data, winxsize, winysize, QImage.Format_RGB32)
        return image


