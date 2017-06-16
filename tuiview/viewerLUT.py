
"""
Module that contains the ViewerLUT class
amongst other things
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

import sys
import numpy
import json
from PyQt4.QtGui import QImage
from PyQt4.QtCore import QObject, SIGNAL
from osgeo import gdal
from . import viewererrors
from . import viewerstretch

gdal.UseExceptions()

# are we big endian or not?
BIG_ENDIAN = sys.byteorder == 'big'

DEFAULT_LUTSIZE = 256 # if not 8bit

# Qt expects the colours in BGRA order packed into
# a 32bit int. We do this by inserting stuff into
# a 8 bit numpy array, but this is endian specific
if BIG_ENDIAN:
    CODE_TO_LUTINDEX = {'blue' : 3, 'green' : 2, 'red' : 1, 'alpha' : 0}
else:
    CODE_TO_LUTINDEX = {'blue' : 0, 'green' : 1, 'red' : 2, 'alpha' : 3}

# for indexing into RGB triplets
CODE_TO_RGBINDEX = {'red' : 0, 'green' : 1, 'blue' : 2, 'alpha' : 3}

# to save creating this tuple all the time
RGB_CODES = ('red', 'green', 'blue')
RGBA_CODES = ('red', 'green', 'blue', 'alpha')

# for the apply functions
MASK_IMAGE_VALUE = 0
MASK_NODATA_VALUE = 1
MASK_BACKGROUND_VALUE = 2

# metadata
VIEWER_BANDINFO_METADATA_KEY = 'VIEWER_BAND_INFO'
VIEWER_LUT_METADATA_KEY = 'VIEWER_LUT'
VIEWER_LUT_SURROGATE_KEY = 'VIEWER_LUT_SURROGATE'
VIEWER_SURROGATE_CT_KEY = 'VIEWER_SURROGATE_CT'

# number of 'extra' lut entries required.
# currently for background, no data and NaN
VIEWER_LUT_EXTRA = 3

def GDALProgressFunc(value, string, lutobject):
    """
    Callback function called by GDAL when calculating
    stats or histogram.
    """
    percent = int(value * 100)
    lutobject.emit(SIGNAL("newPercent(int)"), percent)

class BandLUTInfo(object):
    """
    Class that holds information about a band's LUT
    """
    def __init__(self, scale, offset, lutsize, minval, maxval,
                    nodata_index=0, background_index=0, nan_index=0):
        self.scale = scale
        self.offset = offset
        self.lutsize = lutsize
        self.min = minval
        self.max = maxval
        # indices into the LUT
        self.nodata_index = nodata_index
        self.background_index = background_index
        self.nan_index = nan_index

    def toString(self):
        "Converts to a JSON string"
        rep = {'scale' : self.scale, 'offset' : self.offset, 
                    'lutsize' : self.lutsize, 'min' : self.min, 
                    'max' : self.max, 'nodata_index' : self.nodata_index,
                    'background_index' : self.background_index,
                    'nan_index' : self.nan_index}
        return json.dumps(rep)

    @staticmethod
    def fromString(string):
        "Returns an instance of this class from a JSON string"
        rep = json.loads(string)
        bi = BandLUTInfo(rep['scale'], rep['offset'], 
                rep['lutsize'], rep['min'], rep['max'],
                rep['nodata_index'], rep['background_index'] )
        if 'nan_index' in rep:
            bi.nan_index = rep['nan_index']
        return bi


class ViewerLUT(QObject):
    """
    Class that handles the Lookup Table
    used for transformation between raw
    data and stretched data
    """
    def __init__(self):
        QObject.__init__(self) # so we can emit signal
        # array shape [lutsize,4] for color table and greyscale
        # shape [4, lutsize] for RGB
        self.lut = None
        # 'backup' lut. Used for holding the original for highlight etc
        self.backuplut = None
        # surrogateLookupArray - if not None used to lookup image values
        # in surrogateLUT
        self.surrogateLookupArray = None
        self.surrogateLookupArrayName = None # the name gets saved to the file
        # surrogateLUT - if not None used to lookup image values
        # specified by surrogateLookupArray
        self.surrogateLUT = None
        self.surrogateLUTName = None # name of column gets saved to file
        # a single BandLUTInfo instance for single band
        # dictionary keyed on code for RGB
        self.bandinfo = None

    def highlightRows(self, color, selectionArray=None):
        """
        Highlights the specified where selectionArray == True
        Saves the existing LUT in self.backuplut if not already
        Assumes selectionArray is the same length as the LUT
        """
        if self.lut is None:
            raise viewererrors.InvalidColorTable('stretch not loaded yet')

        if self.lut.shape[1] != 4:
            msg = 'Can only highlight thematic data'
            raise viewererrors.InvalidColorTable(msg)

        if self.backuplut is None:
            # first time this has been done - save copy
            self.backuplut = self.lut.copy()
        else:
            # this has happened before. 
            # restore the old one so no rows highlighted
            # then highlight the ones we want
            self.lut = self.backuplut.copy()
            
        if selectionArray is not None:
            # make selectionArray the same size by adding space for 
            # no data and ignore+nan
            # (which aren't used here)
            selectionArray = numpy.append(selectionArray, 
                                                [False, False, False])

            entry = [color.red(), color.green(), color.blue(), color.alpha()]
            for (value, code) in zip(entry, RGBA_CODES):
                lutindex = CODE_TO_LUTINDEX[code]
                self.lut[..., lutindex] = (
                    numpy.where(selectionArray, value, self.lut[..., lutindex]))

    def setColorTableLookup(self, lookupArray, colName, 
                                    surrogateLUT, surrogateName):
        """
        Uses lookupArray to index into surrogateLUT where 
        values != 0. Pass None to reset.
        Need to pass colName and surrogateName so we can save as part of LUT
        """
        if self.lut is None:
            raise viewererrors.InvalidColorTable('stretch not loaded yet')

        if self.lut.shape[1] != 4:
            msg = 'Can only lookup thematic data'
            raise viewererrors.InvalidColorTable(msg)

        if lookupArray is not None:
            if numpy.issubdtype(lookupArray.dtype, numpy.floating):
                msg = 'lookup must be integer'
                raise viewererrors.InvalidColorTable(msg)

        self.surrogateLookupArray = lookupArray
        self.surrogateLookupArrayName = colName
        if lookupArray is not None and surrogateLUT is not None:
            # assume they want to keep surrogateLUT otherwise
            self.surrogateLUT = surrogateLUT
            self.surrogateLUTName = surrogateName

    def saveToFile(self, fileobj):
        """
        Save current stretch to a text file
        so it can be stored and manipulated
        """
        if self.lut.shape[1] == 4:
            rep = {'nbands' : 1}
            fileobj.write('%s\n' % json.dumps(rep))

            # color table - just one bandinfo - write it out
            bi = self.bandinfo
            fileobj.write('%s\n' % bi.toString())
            for code in RGBA_CODES:
                lutindex = CODE_TO_LUTINDEX[code]
                lut = self.lut[..., lutindex]
                rep = {'code' : code, 'data' : lut.tolist()}
                fileobj.write('%s\n' % json.dumps(rep))
        else:
            # rgb
            rep = {'nbands' : 3}
            fileobj.write('%s\n' % json.dumps(rep))
            for code in RGB_CODES:
                lutindex = CODE_TO_LUTINDEX[code]
                bi = self.bandinfo[code]

                fileobj.write('%s\n' % bi.toString())

                lut = self.lut[lutindex]
                rep = {'code' : code, 'data' : lut.tolist()}
                fileobj.write('%s\n' % json.dumps(rep))

    def writeToGDAL(self, gdaldataset):
        """
        Writes the LUT and BandInfo into the given dataset
        assumed the dataset opened with GA_Update
        Good idea to reopen any other handles to dataset
        to the file as part of this call
        """
        if self.lut.shape[1] == 4:
            # single band - NB writing into band metadata results in corruption 
            # use dataset instead
            string = self.bandinfo.toString()
            gdaldataset.SetMetadataItem(VIEWER_BANDINFO_METADATA_KEY, string)

            # have to deal with the lut being in memory in an 
            # endian specific format
            for code in RGBA_CODES:
                lutindex = CODE_TO_LUTINDEX[code]
                string = json.dumps(self.lut[..., lutindex].tolist())
                key = VIEWER_LUT_METADATA_KEY + '_' + code
                gdaldataset.SetMetadataItem(key, string)

            # surrogate only applicable for single band
            if (self.surrogateLookupArrayName is not None and
                    self.surrogateLUTName is not None):
                surrogateInfo = {'colname' : self.surrogateLookupArrayName,
                        'tablename' : self.surrogateLUTName}
                string = json.dumps(surrogateInfo)
                gdaldataset.SetMetadataItem(VIEWER_LUT_SURROGATE_KEY, string)

        else:
            # rgb - NB writing into band metadata results in corruption 
            # use dataset instead
            for code in RGB_CODES:
                string = self.bandinfo[code].toString()
                key = VIEWER_BANDINFO_METADATA_KEY + '_' + code
                gdaldataset.SetMetadataItem(key, string)

                lutindex = CODE_TO_LUTINDEX[code]
                string = json.dumps(self.lut[lutindex].tolist())
                key = VIEWER_LUT_METADATA_KEY + '_' + code
                gdaldataset.SetMetadataItem(key, string)

            # do alpha seperately as there is no bandinfo
            code = 'alpha'
            lutindex = CODE_TO_LUTINDEX[code]
            string = json.dumps(self.lut[lutindex].tolist())
            key = VIEWER_LUT_METADATA_KEY + '_' + code
            gdaldataset.SetMetadataItem(key, string)

    @staticmethod
    def deleteFromGDAL(gdaldataset):
        """
        Remove all LUT entries from this dataset
        assumed the dataset opened with GA_Update
        """
        # can't seem to delete an item so set to empty string
        # we test for this explicity below
        meta = gdaldataset.GetMetadata()
        if VIEWER_BANDINFO_METADATA_KEY in meta:
            gdaldataset.SetMetadataItem(VIEWER_BANDINFO_METADATA_KEY, '')

        for code in RGBA_CODES:
            key = VIEWER_BANDINFO_METADATA_KEY + '_' + code
            if key in meta:
                gdaldataset.SetMetadataItem(key, '')
            key = VIEWER_LUT_METADATA_KEY + '_' + code
            if key in meta:
                gdaldataset.SetMetadataItem(key, '')
    
    @staticmethod
    def createFromFile(fileobj, stretch):
        """
        Read a text file created by saveToFile and 
        create an instance of this class
        """
        lutobj = ViewerLUT()
        s = fileobj.readline()
        rep = json.loads(s)
        nbands = rep['nbands']
        if nbands == 1:
            # color table
            s = fileobj.readline()
            bi = BandLUTInfo.fromString(s)
            lutobj.bandinfo = bi
            lutobj.lut = numpy.empty((bi.lutsize+VIEWER_LUT_EXTRA, 4), 
                                        numpy.uint8, 'C')
            for n in range(len(RGBA_CODES)):
                s = fileobj.readline()
                rep = json.loads(s)
                code = rep['code']
                lut = numpy.fromiter(rep['data'], numpy.uint8)
                lutindex = CODE_TO_LUTINDEX[code]
                lutobj.lut[..., lutindex] = lut
        else:
            # rgb
            lutobj.bandinfo = {}
            for n in range(len(RGB_CODES)):
                s = fileobj.readline()
                bi = BandLUTInfo.fromString(s)
                s = fileobj.readline()
                rep = json.loads(s)
                code = rep['code']
                lutobj.bandinfo[code] = bi
                lutindex = CODE_TO_LUTINDEX[code]

                if lutobj.lut is None:
                    lutobj.lut = (
                        numpy.empty((4, bi.lutsize+VIEWER_LUT_EXTRA), 
                                numpy.uint8, 'C'))

                lut = numpy.fromiter(rep['data'], numpy.uint8)
                lutobj.lut[lutindex] = lut

            # now do alpha seperately - 255 for all except 
            # no data and background
            # (this isn't stored in the file)
            alphaindex = CODE_TO_LUTINDEX['alpha']
            lutobj.lut[alphaindex].fill(255)
            rgbindex = CODE_TO_RGBINDEX['alpha']
            bandinfo = lutobj.bandinfo['red'] # just to get the index for nan, nodata etc
            nodata_value = stretch.nodata_rgba[rgbindex]
            background_value = stretch.background_rgba[rgbindex]
            nan_value = stretch.nan_rgba[rgbindex]
            lutobj.lut[alphaindex, bandinfo.nodata_index] = nodata_value
            lutobj.lut[alphaindex, bandinfo.background_index] = background_value
            lutobj.lut[alphaindex, bandinfo.nan_index] = nan_value

        return lutobj

    @staticmethod
    def createFromGDAL(gdaldataset, stretch):
        """
        Creates a ViewerLUT object from the metadata saved
        to a GDAL dataset. stretch needed to find what type
        of stretch.
        """
        obj = None

        if len(stretch.bands) == 1:
            # single band
            bistring = gdaldataset.GetMetadataItem(VIEWER_BANDINFO_METADATA_KEY)
            if bistring is not None and bistring != '':
                lutstrings = []
                for code in RGBA_CODES:
                    lutindex = CODE_TO_LUTINDEX[code]
                    key = VIEWER_LUT_METADATA_KEY + '_' + code
                    lutstring = gdaldataset.GetMetadataItem(key)
                    if lutstring is not None and lutstring != '':
                        lutstrings.append(lutstring)

                if len(lutstrings) == 4:
                    # ok we got all the data
                    obj = ViewerLUT()
                    obj.bandinfo = BandLUTInfo.fromString(bistring)
                    size = obj.bandinfo.lutsize + VIEWER_LUT_EXTRA
                    obj.lut = numpy.empty((size, 4), numpy.uint8, 'C')
                    for (lutstring, code) in zip(lutstrings, RGBA_CODES):
                        lutindex = CODE_TO_LUTINDEX[code]
                        lut = numpy.fromiter(json.loads(lutstring), numpy.uint8)
                        obj.lut[..., lutindex] = lut

                # only applicable for single band
                surrogateString = (
                        gdaldataset.GetMetadataItem(VIEWER_LUT_SURROGATE_KEY))
                if (obj is not None and surrogateString is not None and 
                                                        surrogateString != ''):
                    from .viewerRAT import ViewerRAT
                    surrogateInfo = json.loads(surrogateString)
                    name = surrogateInfo['colname']
                    gdalband = gdaldataset.GetRasterBand(stretch.bands[0])
                    rat = gdalband.GetDefaultRAT()
                    if rat is not None:
                        colArray = ViewerRAT.readColumnName(rat, name)
                        if colArray is not None:
                            obj.surrogateLookupArray = colArray
                            obj.surrogateLookupArrayName = name
                        # show error?

                    # read that color table in
                    obj.surrogateLUTName = surrogateInfo['tablename']
                    tables = ViewerLUT.readSurrogateColorTables(gdaldataset)
                    if (obj.surrogateLUTName in tables and 
                                    obj.surrogateLookupArray is not None):
                        obj.surrogateLUT = tables[obj.surrogateLUTName]
                    else:
                        obj.surrogateLUTName = None # show error?

        else:
            # rgb
            infos = []
            for code in RGB_CODES:
                key = VIEWER_BANDINFO_METADATA_KEY + '_' + code
                bistring = gdaldataset.GetMetadataItem(key)
                if bistring is not None and bistring != '':
                    key = VIEWER_LUT_METADATA_KEY + '_' + code
                    lutstring = gdaldataset.GetMetadataItem(key)
                    if lutstring is not None and lutstring != '':
                        infos.append((bistring, lutstring))
            # do alpha separately as there is no band info
            code = 'alpha'
            key = VIEWER_LUT_METADATA_KEY + '_' + code
            alphalutstring = gdaldataset.GetMetadataItem(key)

            if (len(infos) == 3 and alphalutstring is not None 
                    and alphalutstring != ''):
                # ok we got all the data
                obj = ViewerLUT()
                obj.bandinfo = {}
                for (info, code) in zip(infos, RGB_CODES):
                    lutindex = CODE_TO_LUTINDEX[code]
                    (bistring, lutstring) = info
                    obj.bandinfo[code] = BandLUTInfo.fromString(bistring)

                    if obj.lut is None:
                        size = obj.bandinfo[code].lutsize + VIEWER_LUT_EXTRA
                        obj.lut = numpy.empty((4, size), numpy.uint8, 'C')
                    lut = numpy.fromiter(json.loads(lutstring), numpy.uint8)
                    obj.lut[lutindex] = lut
                # now alpha
                code = 'alpha'
                lutindex = CODE_TO_LUTINDEX[code]
                lut = numpy.fromiter(json.loads(alphalutstring), numpy.uint8)
                obj.lut[lutindex] = lut

        return obj

    @staticmethod
    def readSurrogateColorTables(gdaldataset):
        """
        Read the surrogate color tables stored in the file's
        metadata into a dictionary keyed on the name.
        """
        surrogatetables = {}
        surrogatestring = gdaldataset.GetMetadataItem(VIEWER_SURROGATE_CT_KEY)
        if surrogatestring is not None and surrogatestring != '':
            jsondict = json.loads(surrogatestring)
            # go through each named table
            for name in jsondict:
                rgbadict = jsondict[name]
                alllut = None
                # each rgba
                for code in rgbadict:
                    lutstring = rgbadict[code]
                    lut = numpy.fromiter(json.loads(lutstring), numpy.uint8)
                    if alllut is None:
                        # first one - all should be same size
                        alllut = numpy.empty((lut.size, 4), numpy.uint8, 'C')

                    lutindex = CODE_TO_LUTINDEX[code]
                    alllut[..., lutindex] = lut
                surrogatetables[name] = alllut

        return surrogatetables

    @staticmethod
    def writeSurrogateColorTables(gdaldataset, tables):
        """
        Write a dictionary of surrogate color tables to the file's
        metadata.
        """
        # need to convert everything to json combatibale format
        jsondict = {}
        for name in tables:
            rgbadict = {}
            alllut = tables[name]
            for code in RGBA_CODES:
                lutindex = CODE_TO_LUTINDEX[code]
                jsonlutstring = alllut[..., lutindex].tolist()
                lutstring = json.dumps(jsonlutstring)
                rgbadict[code] = lutstring
            jsondict[name] = rgbadict
        jsonstring = json.dumps(jsondict)
        gdaldataset.SetMetadataItem(VIEWER_SURROGATE_CT_KEY, jsonstring)

    def loadColorTable(self, rat, nodata_rgba, background_rgba, nan_rgba):
        """
        Creates a LUT for a single band using 
        the RAT
        """
        if rat.hasColorTable:

            # read in the colour table as lut
            ctcount = rat.getNumRows()

            # LUT is shape [lutsize,4] so we can index from a single 
            # band and get the brga (native order)
            # add for no data and background/nan
            lut = numpy.empty((ctcount + VIEWER_LUT_EXTRA, 4), 
                                    numpy.uint8, 'C')

            # copy in from RAT
            names = rat.getColumnNames()
            self.emit(SIGNAL("newProgress(QString)"), 
                    "Reading Colors...")

            redCol = rat.getEntireAttribute(names[rat.redColumnIdx])
            self.emit(SIGNAL("newPercent(int)"), 25)

            greenCol = rat.getEntireAttribute(names[rat.greenColumnIdx])
            self.emit(SIGNAL("newPercent(int)"), 50)

            blueCol = rat.getEntireAttribute(names[rat.blueColumnIdx])
            self.emit(SIGNAL("newPercent(int)"), 75)

            alphaCol = rat.getEntireAttribute(names[rat.alphaColumnIdx])
            self.emit(SIGNAL("endProgress()"))

            cols = [redCol, greenCol, blueCol, alphaCol]
            for (col, code) in zip(cols, RGBA_CODES):
                lutindex = CODE_TO_LUTINDEX[code]
                lut[:-3, lutindex] = col

            # fill in the background and no data
            nodata_index = ctcount
            background_index = ctcount + 1
            nan_index = ctcount + 2
            data = zip(nodata_rgba, background_rgba, nan_rgba, RGBA_CODES)
            for (nodatavalue, backgroundvalue, nanvalue, code) in data:
                lutindex = CODE_TO_LUTINDEX[code]
                lut[nodata_index, lutindex] = nodatavalue
                lut[background_index, lutindex] = backgroundvalue
                lut[nan_index, lutindex] = nanvalue

        else:
            msg = 'No color table present or file not thematic'
            raise viewererrors.InvalidColorTable(msg)

        bandinfo = BandLUTInfo(1.0, 0.0, ctcount, 0, ctcount-1, 
                                nodata_index, background_index)

        return lut, bandinfo


    def createStretchLUT(self, gdalband, stretch, lutsize, localdata=None):
        """
        Creates a LUT for a single band using the stretch
        method specified and returns it.
        If localdata is not None then it should be an array to calculate
        the stats from (ignore values should be already removed)
        Otherwise these will be calculated from the whole image using GDAL if needed.
        """

        if stretch.stretchmode == viewerstretch.VIEWER_STRETCHMODE_NONE:
            # just a linear stretch between 0 and 255
            # for the range of possible values
            lut = numpy.linspace(0, 255, num=lutsize).astype(numpy.uint8)
            bandinfo = BandLUTInfo(1.0, 0.0, lutsize, 0, 255)
            return lut, bandinfo

        # other methods below require statistics
        minVal, maxVal, mean, stdDev = (
                self.getStatisticsWithProgress(gdalband, localdata))

        # code below sets stretchMin and stretchMax

        if stretch.stretchmode == viewerstretch.VIEWER_STRETCHMODE_LINEAR:
            # stretch between reported min and max if they
            # have given us None as the range, otherwise use
            # the specified range
            (reqMin, reqMax) = stretch.stretchparam
            if reqMin is None:
                stretchMin = minVal
            else:
                stretchMin = reqMin

            if reqMax is None:
                stretchMax = maxVal
            else:
                stretchMax = reqMax
                
        elif stretch.stretchmode == viewerstretch.VIEWER_STRETCHMODE_STDDEV:
            # linear stretch n std deviations from the mean
            nstddev = stretch.stretchparam[0]

            stretchMin = mean - (nstddev * stdDev)
            if stretchMin < minVal:
                stretchMin = minVal
            stretchMax = mean + (nstddev * stdDev)
            if stretchMax > maxVal:
                stretchMax = maxVal

        elif stretch.stretchmode == viewerstretch.VIEWER_STRETCHMODE_HIST:

            histo = (
             self.getHistogramWithProgress(gdalband, minVal, maxVal, localdata))

            sumPxl = sum(histo)
            histmin, histmax = stretch.stretchparam
            numBins = len(histo)

            bandLower = sumPxl * histmin
            bandUpper = sumPxl * histmax

            # calc min and max from histo
            # find bin number that bandLower/Upper fall into 
            # maybe we can do better with numpy?
            stretchMin = minVal
            stretchMax = maxVal
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
                    stretchMax = maxVal + (
                        (maxVal - minVal) * ((numBins - i - 1) / numBins))
                    break

        else:
            msg = 'unsupported stretch mode'
            raise viewererrors.InvalidParameters(msg)

        if stretch.attributeTableSize is None:
            # default behaviour - a LUT for the range of the data
            lut = numpy.linspace(0, 255, num=lutsize).astype(numpy.uint8)

            if stretchMin == stretchMax:
                # hack for invalid data
                stretchMax = stretchMin + 1

            # make it lutsize-1 so we keep the indices less than lutsize
            scale = float(stretchMax - stretchMin) / (lutsize-1)
            offset = -stretchMin

        else:
            # custom LUT size - have an attribute table we must match
            lut = numpy.empty(lutsize, numpy.uint8)
            # assume ints - we just create ramp 0-255 in data range
            stretchMin = int(stretchMin)
            stretchMax = int(stretchMax)
            if stretchMin == stretchMax:
                # hack for invalid data
                stretchMax = stretchMin + 1
            stretchRange = stretchMax - stretchMin
            lut[stretchMin:stretchMax] = numpy.linspace(0, 255, 
                                                num=stretchRange)
            # 0 and 255 outside this range
            lut[0:stretchMin] = 0
            lut[stretchMax:] = 255
            # this must be true
            scale = 1
            offset = 0

        bandinfo = BandLUTInfo(scale, offset, lutsize, stretchMin, stretchMax)

        return lut, bandinfo

    def getStatisticsWithProgress(self, gdalband, localdata=None):
        """
        Helper method. Just quickly returns the stats if
        they are easily available from GDAL. Calculates them using
        the supplied progress if not.
        If localdata is not None, statistics are calulated using 
        the data in this numpy array.
        """
        if localdata is None:
            # calculate stats for whole image
            gdal.ErrorReset()
            stats = gdalband.GetStatistics(0, 0)
            if stats == [0, 0, 0, -1] or gdal.GetLastErrorNo() != gdal.CE_None:
                # need to actually calculate them
                gdal.ErrorReset()
                self.emit(SIGNAL("newProgress(QString)"), 
                        "Calculating Statistics...")
                # TODO: find a way of ignoring NaNs

                # A workaround for broken progress support in GDAL 2.2.0
                # see https://trac.osgeo.org/gdal/ticket/6927
                if gdal.__version__ == '2.2.0':
                    stats = gdalband.ComputeStatistics(False)
                else:
                    stats = gdalband.ComputeStatistics(False, GDALProgressFunc, self)

                self.emit(SIGNAL("endProgress()"))

                if (stats == [0, 0, 0, -1] or 
                        gdal.GetLastErrorNo() != gdal.CE_None):
                    msg = 'unable to calculate statistics'
                    raise viewererrors.StatisticsError(msg)

        else:
            # local - using numpy - make sure float not 1-d array for json
            # ignore NANs
            minval = float(numpy.nanmin(localdata))
            maxval = float(numpy.nanmax(localdata))
            mean = float(numpy.nanmean(localdata))
            stddev = float(numpy.nanstd(localdata))
            stats = [minval, maxval, mean, stddev]


        # inf and NaNs really stuff things up
        # must be a better way, but GDAL doesn't seem to have
        # an option to ignore NaNs and numpy still returns Infs. 
        # Make some numbers up.
        if not numpy.isfinite(stats[0]):
            stats[0] = 0.0
        if not numpy.isfinite(stats[1]):
            stats[1] = 10.0
        if not numpy.isfinite(stats[2]):
            stats[2] = 5.0
        if not numpy.isfinite(stats[3]):
            stats[3] = 1.0

        return stats

    def getHistogramWithProgress(self, gdalband, minVal, maxVal, 
                                localdata=None):
        """
        Helper method. Calculates histogram using GDAL.
        If localdata is not None, histogram calulated using 
        the data in this numpy array.
        """
        numBins = int(numpy.ceil(maxVal - minVal))
        if numBins < 1:
            # float data?
            numBins = 255

        if localdata is None:
            # global stats - first check if there is a histo saved
            # needs to share the same min and max that we have calculated
            histo = None
            # careful with comparisons since they are saved as 
            # strings in the file
            histomin = gdalband.GetMetadataItem('STATISTICS_HISTOMIN')
            histomax = gdalband.GetMetadataItem('STATISTICS_HISTOMAX')
            # attempt to read out of the RAT
            histoIdx = None
            histostr = None
            rat = gdalband.GetDefaultRAT()
            if rat is not None:
                for col in range(rat.GetColumnCount()):
                    if rat.GetUsageOfCol(col) == gdal.GFU_PixelCount:
                        histoIdx = col
                        break
            else:
                # drop back to metadata
                histostr = gdalband.GetMetadataItem('STATISTICS_HISTOBINVALUES')

            if (histomin is not None and histomax is not None 
                        and (histoIdx is not None or histostr is not None)):
                # try and convert to float
                try:
                    histomin = float(histomin)
                    histomax = float(histomax)
                    if histomin == minVal and histomax == maxVal:
                        if histoIdx is not None:
                            histo = rat.ReadAsArray(histoIdx)
                        else:
                            # drop back to metadata
                            histolist = histostr.split('|')
                            # sometimes there seems to be a trailing '|'
                            if histolist[-1] == '':
                                histolist.pop()
                            histo = [int(x) for x in histolist]

                except ValueError:
                    pass

            if histo is None:
                # no suitable histo - call GDAL and do progress
                self.emit(SIGNAL("newProgress(QString)"), 
                            "Calculating Histogram...")

                histo = gdalband.GetHistogram(min=minVal, max=maxVal, 
                        buckets=numBins, 
                        include_out_of_range=0, approx_ok=0, 
                        callback=GDALProgressFunc, 
                        callback_data=self)

                self.emit(SIGNAL("endProgress()"))
        else:
            # local stats - use numpy on localdata
            histo, bins = numpy.histogram(localdata, numBins)

        return histo

    def createLUT(self, dataset, stretch, rat, image=None):
        """
        Main function.
        dataset is a GDAL dataset to use.
        stetch is a ViewerStretch instance that describes the stretch.
        rat is an instance of ViewerRAT - for reading color table
        if image is not None it should be a QImage returned by the apply
        functions and a local stretch will be calculated using this.
        """
        # clobber the backup lut - any hightlights happen afresh
        self.backuplut = None

        if (stretch.mode == viewerstretch.VIEWER_MODE_DEFAULT or 
            stretch.stretchmode == viewerstretch.VIEWER_STRETCHMODE_DEFAULT):
            msg = 'must set mode and stretchmode'
            raise viewererrors.InvalidStretch(msg)

        if image is not None:
            # if we are doing a local stretch do some masking first
            flatmask = image.viewermask.flatten() == MASK_IMAGE_VALUE
            if isinstance(image.viewerdata, list):
                # rgb - create data for 3 bands
                localdatalist = []
                for localdata in image.viewerdata:
                    flatdata = localdata.flatten()
                    data = flatdata.compress(flatmask)
                    localdatalist.append(data)
            else:
                # single band
                flatdata = image.viewerdata.flatten()
                localdata = flatdata.compress(flatmask)
        else:
            # global stretch
            localdata = None
            localdatalist = (None, None, None)

        # are we loading the LUT from an external file instead?
        if stretch.readLUTFromText is not None:
            # first line describes the stretch - ignore
            fileobj = open(stretch.readLUTFromText)
            fileobj.readline()
            lut = self.createFromFile(fileobj, stretch)
            fileobj.close()
            if lut is None:
                msg = 'No stretch and lookup table in this file'
                raise viewererrors.InvalidDataset(msg)
            self.lut = lut.lut
            self.bandinfo = lut.bandinfo
            return
        elif stretch.readLUTFromGDAL is not None:
            gdaldataset = gdal.Open(stretch.readLUTFromGDAL)
            lut = self.createFromGDAL(gdaldataset, stretch)
            del gdaldataset
            if lut is None:
                msg = 'No stretch and lookup table in this file'
                raise viewererrors.InvalidDataset(msg)
            self.lut = lut.lut
            self.bandinfo = lut.bandinfo
            return

        # decide what to do based on the code
        if stretch.mode == viewerstretch.VIEWER_MODE_COLORTABLE:

            if len(stretch.bands) > 1:
                msg = 'specify one band when opening a color table image'
                raise viewererrors.InvalidParameters(msg)

            if stretch.stretchmode != viewerstretch.VIEWER_STRETCHMODE_NONE:
                msg = 'stretchmode should be set to none for color tables'
                raise viewererrors.InvalidParameters(msg)

            band = stretch.bands[0]
            gdalband = dataset.GetRasterBand(band)

            # load the color table
            self.lut, self.bandinfo = self.loadColorTable(rat, 
                                                stretch.nodata_rgba, 
                                                stretch.background_rgba,
                                                stretch.nan_rgba)

        elif stretch.mode == viewerstretch.VIEWER_MODE_GREYSCALE:
            if len(stretch.bands) > 1:
                msg = 'specify one band when opening a greyscale image'
                raise viewererrors.InvalidParameters(msg)

            band = stretch.bands[0]
            gdalband = dataset.GetRasterBand(band)

            if gdalband.DataType == gdal.GDT_Byte:
                lutsize = 256
            elif stretch.attributeTableSize is not None:
                # override if there is an attribute table
                lutsize = stretch.attributeTableSize
            else:
                lutsize = DEFAULT_LUTSIZE

            # LUT is shape [lutsize,4] so we can index from a single 
            # band and get the brga (native order)
            # plus 2 for no data and background
            self.lut = numpy.empty((lutsize + VIEWER_LUT_EXTRA, 4), 
                                        numpy.uint8, 'C')

            lut, self.bandinfo = self.createStretchLUT(gdalband, 
                        stretch, lutsize, localdata)

            # make space for nodata and background + nan
            lut = numpy.append(lut, [0, 0, 0])
            self.bandinfo.nodata_index = lutsize
            self.bandinfo.background_index = lutsize + 1

            # copy to all bands
            for code in RGB_CODES:
                lutindex = CODE_TO_LUTINDEX[code]
                # append the nodata and background while we are at it
                rgbindex = CODE_TO_RGBINDEX[code]
                nodata_value = stretch.nodata_rgba[rgbindex]
                background_value = stretch.background_rgba[rgbindex]
                nan_value = stretch.nan_rgba[rgbindex]
                lut[self.bandinfo.nodata_index] = nodata_value
                lut[self.bandinfo.background_index] = background_value
                lut[self.bandinfo.nan_index] = nan_value

                self.lut[..., lutindex] = lut

            # now do alpha seperately - 255 for all except 
            # no data and background
            lutindex = CODE_TO_LUTINDEX['alpha']
            self.lut[..., lutindex].fill(255)
            rgbindex = CODE_TO_RGBINDEX['alpha']
            nodata_value = stretch.nodata_rgba[rgbindex]
            background_value = stretch.background_rgba[rgbindex]
            self.lut[self.bandinfo.nodata_index, lutindex] = nodata_value
            self.lut[self.bandinfo.background_index, lutindex] = (
                                                background_value)

        elif stretch.mode == viewerstretch.VIEWER_MODE_PSEUDOCOLOR:
            from . import pseudocolor
            # make sure we have any other ramps loaded
            pseudocolor.loadExtraRamps()

            if len(stretch.bands) > 1:
                msg = 'specify one band when opening a pseudocolor image'
                raise viewererrors.InvalidParameters(msg)

            band = stretch.bands[0]
            gdalband = dataset.GetRasterBand(band)

            if gdalband.DataType == gdal.GDT_Byte:
                lutsize = 256
            elif stretch.attributeTableSize is not None:
                # override if there is an attribute table
                lutsize = stretch.attributeTableSize
            else:
                lutsize = DEFAULT_LUTSIZE

            # LUT is shape [lutsize,4] so we can index from a single 
            # band and get the brga (native order)
            # plus 2 for no data and background
            self.lut = numpy.empty((lutsize + VIEWER_LUT_EXTRA, 4), 
                                    numpy.uint8, 'C')

            # we get the LUT from createStretchLUT but we are really
            # only interested in the bandinfo that records the stretchmin, max
            lut, self.bandinfo = self.createStretchLUT(gdalband, 
                        stretch, lutsize, localdata)

            # we will make space for thses
            self.bandinfo.nodata_index = lutsize
            self.bandinfo.background_index = lutsize + 1

            # now obtain for each band and copy
            for code in RGB_CODES:
                lutindex = CODE_TO_LUTINDEX[code]

                lut = pseudocolor.getLUTForRamp(code, stretch.rampName, 
                                                lutsize)
                # make space for nodata and background+nan
                lut = numpy.append(lut, [0, 0, 0])

                # append the nodata and background while we are at it
                rgbindex = CODE_TO_RGBINDEX[code]
                nodata_value = stretch.nodata_rgba[rgbindex]
                background_value = stretch.background_rgba[rgbindex]
                nan_value = stretch.nan_rgba[rgbindex]
                lut[self.bandinfo.nodata_index] = nodata_value
                lut[self.bandinfo.background_index] = background_value
                lut[self.bandinfo.nan_index] = nan_value

                self.lut[..., lutindex] = lut

            # now do alpha seperately - 255 for all except 
            # no data and background
            lutindex = CODE_TO_LUTINDEX['alpha']
            self.lut[..., lutindex].fill(255)
            rgbindex = CODE_TO_RGBINDEX['alpha']
            nodata_value = stretch.nodata_rgba[rgbindex]
            background_value = stretch.background_rgba[rgbindex]
            nan_value = stretch.nan_rgba[rgbindex]
            self.lut[self.bandinfo.nodata_index, lutindex] = nodata_value
            self.lut[self.bandinfo.background_index, lutindex] = (
                                                background_value)
            self.lut[self.bandinfo.nan_index, lutindex] = nan_value

        elif stretch.mode == viewerstretch.VIEWER_MODE_RGB:
            if len(stretch.bands) != 3:
                msg = 'must specify 3 bands when opening rgb'
                raise viewererrors.InvalidParameters(msg)


            self.bandinfo = {}
            self.lut = None

            # user supplies RGB
            zipdata = zip(stretch.bands, RGB_CODES, localdatalist)
            for (band, code, localdata) in zipdata:
                gdalband = dataset.GetRasterBand(band)

                if gdalband.DataType == gdal.GDT_Byte:
                    lutsize = 256
                else:
                    lutsize = DEFAULT_LUTSIZE

                if self.lut is None:
                    # LUT is shape [4,lutsize]. We apply the stretch seperately
                    # to each band. Order is RGBA 
                    # (native order to make things easier)
                    # plus 2 for no data and background
                    self.lut = numpy.empty((4, lutsize + VIEWER_LUT_EXTRA), 
                                                    numpy.uint8, 'C')

                lutindex = CODE_TO_LUTINDEX[code]
                # create stretch for each band
                lut, bandinfo = self.createStretchLUT(gdalband, stretch, 
                                    lutsize, localdata)

                # append the nodata and background+nan while we are at it
                rgbindex = CODE_TO_RGBINDEX[code]
                nodata_value = stretch.nodata_rgba[rgbindex]
                background_value = stretch.background_rgba[rgbindex]
                nan_value = stretch.nan_rgba[rgbindex]
                lut = numpy.append(lut, [nodata_value, background_value, 
                                                    nan_value])

                bandinfo.nodata_index = lutsize
                bandinfo.background_index = lutsize + 1
                bandinfo.nan_index = lutsize + 2

                self.bandinfo[code] = bandinfo

                self.lut[lutindex] = lut

            # now do alpha seperately - 255 for all except 
            # no data and background
            lutindex = CODE_TO_LUTINDEX['alpha']
            self.lut[lutindex].fill(255)
            rgbindex = CODE_TO_RGBINDEX['alpha']
            nodata_value = stretch.nodata_rgba[rgbindex]
            background_value = stretch.background_rgba[rgbindex]
            nan_value = stretch.nan_rgba[rgbindex]
            # just use blue since alpha has no bandinfo and 
            # they should all be the same anyway
            nodata_index = self.bandinfo['blue'].nodata_index
            background_index = self.bandinfo['blue'].background_index
            nan_index = self.bandinfo['blue'].nan_index

            self.lut[lutindex, nodata_index] = nodata_value
            self.lut[lutindex, background_index] = background_value
            self.lut[lutindex, nan_index] = nan_value
            
        else:
            msg = 'unsupported display mode'
            raise viewererrors.InvalidParameters(msg)

    def applyLUTSingle(self, data, mask):
        """
        Apply the LUT to a single band (color table
        or greyscale image) and return the result as
        a QImage
        """
        # hang on the 'old' data so we can save that back to the image
        olddata = data            

        # work out where the NaN's are if float
        if numpy.issubdtype(data.dtype, numpy.floating):
            nanmask = numpy.isnan(data)
        else:
            nanmask = None

        # convert to float for maths below
        data = data.astype(numpy.floating)

        # in case data outside range of stretch
        numpy.clip(data, self.bandinfo.min, self.bandinfo.max, out=data)

        # apply scaling
        numpy.add(data, self.bandinfo.offset, out=data)
        numpy.divide(data, self.bandinfo.scale, out=data)
        
        # can only do lookups with integer data
        data = data.astype(numpy.integer)

        if nanmask is not None:
            # set NaN values back to LUT=nan if originally float
            data[nanmask] = self.bandinfo.nan_index

        # mask no data and background
        data[mask == MASK_NODATA_VALUE] = self.bandinfo.nodata_index
        data[mask == MASK_BACKGROUND_VALUE] = self.bandinfo.background_index

        # do the lookup
        bgra = self.lut[data]
        winysize, winxsize = data.shape

        if (self.surrogateLookupArray is not None and 
                    self.surrogateLUT is not None):
            # clip the data to the range
            surrogatedata = olddata.clip(0, self.surrogateLookupArray.size - 1)
            # do the lookup
            lookup = self.surrogateLookupArray[surrogatedata]
            # create the bgra for the surrogate
            surrogatebgra = self.surrogateLUT[lookup]
            # only apply when != and not no data, background etc
            surrogatemask = ((lookup != 0) & (mask != MASK_NODATA_VALUE) & 
                                    (mask != MASK_BACKGROUND_VALUE))
            # mask sure mask has same number of axis
            surrogatemask = numpy.expand_dims(surrogatemask, axis=2)
            # swap where needed - can't do direct mask index as different shape
            bgra = numpy.where(surrogatemask, surrogatebgra, bgra)
        
        # create QImage from numpy array
        # see 
        # http://www.mail-archive.com/pyqt@riverbankcomputing.com/msg17961.html
        # TODO there is a note in the docs saying Format_ARGB32_Premultiplied
        # is faster. Not sure what this means
        image = QImage(bgra.data, winxsize, winysize, QImage.Format_ARGB32)
        image.viewerdata = olddata # hold on to the data in case we
                            # want to change the lut and quickly re-apply it
                            # or calculate local stats
        image.viewermask = mask 
        return image

    def applyLUTRGB(self, datalist, mask):
        """
        Apply LUT to 3 bands of imagery
        passed as a list of arrays.
        Return a QImage
        """
        winysize, winxsize = datalist[0].shape

        # create blank array to stretch into
        bgra = numpy.empty((winysize, winxsize, 4), numpy.uint8, 'C')
        for (data, code) in zip(datalist, RGB_CODES):
            lutindex = CODE_TO_LUTINDEX[code]
            bandinfo = self.bandinfo[code]

            # work out where the NaN's are if float
            if numpy.issubdtype(data.dtype, numpy.floating):
                nanmask = numpy.isnan(data)
            else:
                nanmask = None

            # convert to float for maths below
            data = data.astype(numpy.floating)
            # in case data outside range of stretch
            numpy.clip(data, bandinfo.min, bandinfo.max, out=data)
            
            # apply scaling in place
            numpy.add(data, bandinfo.offset, out=data)
            numpy.divide(data, bandinfo.scale, out=data)

            # can only do lookups with integer data
            data = data.astype(numpy.integer)

            # set NaN values back to LUT=nandata if data originally float
            if nanmask is not None:
                data[nanmask] = bandinfo.nan_index

            # mask no data and background
            data[mask == MASK_NODATA_VALUE] = bandinfo.nodata_index
            data[mask == MASK_BACKGROUND_VALUE] = bandinfo.background_index

            # do the lookup
            bgra[..., lutindex] = self.lut[lutindex][data]
        
        # now alpha - all 255 apart from nodata and background
        lutindex = CODE_TO_LUTINDEX['alpha']

        # just use blue since alpha has no bandinfo and 
        # they should all be the same anyway
        nodata_index = self.bandinfo['blue'].nodata_index
        background_index = self.bandinfo['blue'].background_index
        nan_index = self.bandinfo['blue'].nan_index
        nodata_value = self.lut[lutindex, nodata_index]
        background_value = self.lut[lutindex, background_index]
        nan_value = self.lut[lutindex, nan_index]

        # create the alpha array (do separately so we not always doing strides)
        alpha = numpy.empty((winysize, winxsize), numpy.uint8)
        alpha.fill(255)
        alpha[mask == MASK_NODATA_VALUE] = nodata_value
        if nanmask is not None:
            alpha[nanmask] = nan_value
        alpha[mask == MASK_BACKGROUND_VALUE] = background_value
        bgra[..., lutindex] = alpha

        # turn into QImage
        # TODO there is a note in the docs saying Format_ARGB32_Premultiplied
        # is faster. Not sure what this means
        image = QImage(bgra.data, winxsize, winysize, QImage.Format_ARGB32)
        image.viewerdata = datalist 
        # so we have the data if we want to calculate stats etc
        image.viewermask = mask
        return image


