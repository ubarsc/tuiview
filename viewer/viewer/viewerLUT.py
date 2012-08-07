
"""
Module that contains the ViewerLUT class
amongst other things
"""

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
    CODE_TO_LUTINDEX = {'b' : 3, 'g' : 2, 'r' : 1, 'a' : 0}
else:
    CODE_TO_LUTINDEX = {'b' : 0, 'g' : 1, 'r' : 2, 'a' : 3}

# for indexing into RGB triplets
CODE_TO_RGBINDEX = {'r' : 0, 'g' : 1, 'b' : 2, 'a' : 3}

# to save creating this tuple all the time
RGB_CODES = ('r', 'g', 'b')
RGBA_CODES = ('r', 'g', 'b', 'a')

# for the apply functions
MASK_IMAGE_VALUE = 0
MASK_NODATA_VALUE = 1
MASK_BACKGROUND_VALUE = 2

# metadata
VIEWER_BANDINFO_METADATA_KEY = 'VIEWER_BAND_INFO'
VIEWER_LUT_METADATA_KEY = 'VIEWER_LUT'

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
    def __init__(self, scale, offset, lutsize, min, max,
                    nodata_index=0, background_index=0):
        self.scale = scale
        self.offset = offset
        self.lutsize = lutsize
        self.min = min
        self.max = max
        # indices into the LUT
        self.nodata_index = nodata_index
        self.background_index = background_index

    def toString(self):
        rep = {'scale' : self.scale, 'offset' : self.offset, 
                    'lutsize' : self.lutsize, 'min' : self.min, 
                    'max' : self.max, 'nodata_index' : self.nodata_index,
                    'background_index' : self.background_index}
        return json.dumps(rep)

    @staticmethod
    def fromString(string):
        rep = json.loads(string)
        bi = BandLUTInfo(rep['scale'], rep['offset'], 
                rep['lutsize'], rep['min'], rep['max'],
                rep['nodata_index'], rep['background_index'] )
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
        # a single BandLUTInfo instance for single band
        # dictionary keyed on code for RGB
        self.bandinfo = None

    def highlightRows(self, color, selectionArray=None):
        """
        Highlights the specified where selectionArray == True
        (or remove if 'rows' is None).
        Saves the existing LUT in self.backuplut if not already
        Assumes selectionArray is the same length as the LUT
        """
        if self.lut is None:
            raise viewererrors.InvalidColorTable('stretch not loaded yet')

        if self.lut.shape[1] != 4:
            raise viewererrors.InvalidColorTable('Can only highlight thematic data')

        if self.backuplut is None:
            # first time this has been done - save copy
            self.backuplut = self.lut.copy()
        else:
            # this has happened before. 
            # restore the old one so no rows highlighted
            # then highlight the ones we want
            self.lut = self.backuplut.copy()

        # make selectionArray the same size by adding space for no data and ignore
        # (which aren't used here)
        selectionArray = numpy.append(selectionArray, [False, False])

        entry = [color.red(), color.green(), color.blue(), color.alpha()]
        for (value, code) in zip(entry, RGBA_CODES):
            lutindex = CODE_TO_LUTINDEX[code]
            self.lut[...,lutindex] = numpy.where(selectionArray, value, self.lut[...,lutindex])

    def saveToFile(self, fname):
        """
        Save current stretch to a text file
        so it can be stored and manipulated
        """
        fileobj = open(fname, 'w')

        if self.lut.shape[1] == 4:
            rep = {'nbands' : 1}
            fileobj.write('%s\n' % json.dumps(rep))

            # color table - just one bandinfo - write it out
            bi = self.bandinfo
            fileobj.write('%s\n' % bi.toString())
            for code in RGB_CODES:
                lutindex = CODE_TO_LUTINDEX[code]
                lut = self.lut[...,lutindex]
                rep = {'code' : code, 'data' : lut.tolist()}
                fileobj.write('%s\n' % json.dumps(rep))
        else:
            # rgb
            rep = {'nbands' : 3}
            fileobj.write('%s\n' % json.dumps(rep))
            for code in RGB_CODES:
                lutindex = CODE_TO_LUTINDEX[code]
                bi = self.bandinfo[code]

                fileobj.write('%s\n' % bo.toString())

                lut = self.lut[lutindex]
                fileobj.write('%s\n' % json.dumps(lut.tolist()))

        fileobj.close()

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

            # have to deal with the lut being in memory in an endian specific format
            for code in RGBA_CODES:
                lutindex = CODE_TO_LUTINDEX[code]
                string = json.dumps(self.lut[...,lutindex].tolist())
                key = VIEWER_LUT_METADATA_KEY + '_' + code
                gdaldataset.SetMetadataItem(key, string)
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
            code = 'a'
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
    def createFromFile(fname):

        lutobj = ViewerLUT()
        fileobj = open(fname)
        s = fileobj.readline()
        rep = json.loads(s)
        nbands = rep['nbands']
        if nbands == 1:
            # color table
            s = fileobj.readline()
            bi = BandLUTInfo.fromString(s)
            lutobj.bandinfo = bi
            lutobj.lut = numpy.empty((bi.lutsize+2, 4), numpy.uint8, 'C')
            for n in range(len(RGB_CODES)):
                s = fileobj.readline()
                rep = json.loads(s)
                code = rep['code']
                lut = numpy.fromiter(rep['data'], numpy.uint8)
                lutindex = CODE_TO_LUTINDEX[code]
                lutobj.lut[...,lutindex] = lut
        else:
            # rgb
            lutobj.bandinfo = {}
            for n in range(len(RGB_CODES)):
                s = fileobj.readline()
                bi = BandLUTInfo.fromString(s)
                code = rep['code']
                lutobj.bandinfo[code] = bi
                lutindex = CODE_TO_LUTINDEX[code]

                if lutobj.lut is None:
                    lutobj.lut = numpy.empty((4, bi.lutsize+2), numpy.uint8, 'C')
        
                s = fileobj.readline()
                rep = json.loads(s)
                lut = numpy.fromiter(rep, numpy.uint8)
                lutobj.lut[lutindex] = lut

        fileobj.close()
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
                    obj.lut = numpy.empty((obj.bandinfo.lutsize+2, 4), numpy.uint8, 'C')
                    for (lutstring, code) in zip(lutstrings, RGBA_CODES):
                        lutindex = CODE_TO_LUTINDEX[code]
                        lut = numpy.fromiter(json.loads(lutstring), numpy.uint8)
                        obj.lut[...,lutindex] = lut

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
            code = 'a'
            key = VIEWER_LUT_METADATA_KEY + '_' + code
            alphalutstring = gdaldataset.GetMetadataItem(key)

            if len(infos) == 3 and alphalutstring is not None and alphalutstring != '':
                # ok we got all the data
                obj = ViewerLUT()
                obj.bandinfo = {}
                for (info, code) in zip(infos, RGB_CODES):
                    lutindex = CODE_TO_LUTINDEX[code]
                    (bistring, lutstring) = info
                    obj.bandinfo[code] = BandLUTInfo.fromString(bistring)

                    if obj.lut is None:
                        obj.lut = numpy.empty((4, obj.bandinfo[code].lutsize+2), numpy.uint8, 'C')
                    lut = numpy.fromiter(json.loads(lutstring), numpy.uint8)
                    obj.lut[lutindex] = lut
                # now alpha
                code = 'a'
                lutindex = CODE_TO_LUTINDEX[code]
                lut = numpy.fromiter(json.loads(alphalutstring), numpy.uint8)
                obj.lut[lutindex] = lut

        return obj

    def loadColorTable(self, gdalband, nodata_rgba, background_rgba):
        """
        Creates a LUT for a single band using 
        the color table
        """
        ct = gdalband.GetColorTable()
        if ct is not None:

            if ct.GetPaletteInterpretation() != gdal.GPI_RGB:
                msg = 'only handle RGB color tables'
                raise viewererrors.InvalidColorTable(msg)

            # read in the colour table as lut
            ctcount = ct.GetCount()

            # LUT is shape [lutsize,4] so we can index from a single 
            # band and get the brga (native order)
            # add 2 for no data and background
            lut = numpy.empty((ctcount + 2, 4), numpy.uint8, 'C')

            for i in range(ctcount):
                entry = ct.GetColorEntry(i)
                # entry is RGBA, need to store as BGRA - always ignore alpha for now
                for (value, code) in zip(entry, RGBA_CODES):
                    lutindex = CODE_TO_LUTINDEX[code]
                    lut[i,lutindex] = value

            # fill in the background and no data
            nodata_index = ctcount
            background_index = ctcount + 1
            for (nodatavalue, backgroundvalue, code) in zip(nodata_rgba, background_rgba, RGBA_CODES):
                lutindex = CODE_TO_LUTINDEX[code]
                lut[nodata_index,lutindex] = nodatavalue
                lut[background_index,lutindex] = backgroundvalue

        else:
            msg = 'No color table present'
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
        minVal, maxVal, mean, stdDev = self.getStatisticsWithProgress(gdalband, localdata)

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

            histo = self.getHistogramWithProgress(gdalband, minVal, maxVal, localdata)

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
                    stretchMax = maxVal + ((maxVal - minVal) * ((numBins - i - 1) / numBins))
                    break

        else:
            msg = 'unsupported stretch mode'
            raise viewererrors.InvalidParameters(msg)

        if stretch.attributeTableSize is None:
            # default behaviour - a LUT for the range of the data
            lut = numpy.linspace(0, 255, num=lutsize).astype(numpy.uint8)

            # make it lutsize-1 so we keep the indices less than lutsize
            scale = float(stretchMax - stretchMin) / (lutsize-1)
            offset = -stretchMin

        else:
            # custom LUT size - have an attribute table we must match
            lut = numpy.empty(lutsize, numpy.uint8)
            # assume ints - we just create ramp 0-255 in data range
            stretchMin = int(stretchMin)
            stretchMax = int(stretchMax)
            stretchRange = stretchMax - stretchMin
            lut[stretchMin:stretchMax] = numpy.linspace(0, 255, num=stretchRange)
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
                self.emit(SIGNAL("newProgress(QString)"), "Calculating Statistics...")
                stats = gdalband.ComputeStatistics(0, GDALProgressFunc, self)
                self.emit(SIGNAL("endProgress()"))

                if stats == [0, 0, 0, -1] or gdal.GetLastErrorNo() != gdal.CE_None:
                    msg = 'unable to calculate statistics'
                    raise viewererrors.StatisticsError(msg)

        else:
            # local - using numpy - make sure float not 1-d array for json
            min = float(localdata.min())
            max = float(localdata.max())
            mean = float(localdata.mean())
            stddev = float(localdata.std())
            stats = (min, max, mean, stddev)

        return stats

    def getHistogramWithProgress(self, gdalband, minVal, maxVal, localdata=None):
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
            # careful with comparisons since they are saved as strings in the file
            histomin = gdalband.GetMetadataItem('STATISTICS_HISTOMIN')
            histomax = gdalband.GetMetadataItem('STATISTICS_HISTOMAX')
            histostr = gdalband.GetMetadataItem('STATISTICS_HISTOBINVALUES')
            if histomin is not None and histomax is not None and histostr is not None:
                # try and convert to float
                try:
                    histomin = float(histomin)
                    histomax = float(histomax)
                    if histomin == minVal and histomax == maxVal:
                        histolist = histostr.split('|')
                        # sometimes there seems to be a trailing '|'
                        if histolist[-1] == '':
                            histolist.pop()
                        histo = [int(x) for x in histolist]

                except ValueError:
                    pass

            if histo is None:
                # no suitable histo - call GDAL and do progress
                self.emit(SIGNAL("newProgress(QString)"), "Calculating Histogram...")

                histo = gdalband.GetHistogram(min=minVal, max=maxVal, buckets=numBins, 
                        include_out_of_range=0, approx_ok=0, callback=GDALProgressFunc, 
                        callback_data=self)

                self.emit(SIGNAL("endProgress()"))
        else:
            # local stats - use numpy on localdata
            histo, bins = numpy.histogram(localdata, numBins)

        return histo

    def createLUT(self, dataset, stretch, image=None):
        """
        Main function.
        dataset is a GDAL dataset to use.
        stetch is a ViewerStretch instance that describes the stretch.
        if image is not None it should be a QImage returned by the apply
            functions and a local stretch will be calculated using this.
        """
        # clobber the backup lut - any hightlights happen afresh
        self.backuplut = None

        if stretch.mode == viewerstretch.VIEWER_MODE_DEFAULT or \
                stretch.stretchmode == viewerstretch.VIEWER_STRETCHMODE_DEFAULT:
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
            self.lut, self.bandinfo = self.loadColorTable(gdalband, stretch.nodata_rgba, 
                                                                stretch.background_rgba)

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
            self.lut = numpy.empty((lutsize + 2, 4), numpy.uint8, 'C')

            lut, self.bandinfo = self.createStretchLUT(gdalband, stretch, lutsize, localdata)

            # make space for nodata and background
            lut = numpy.append(lut, [0, 0])
            self.bandinfo.nodata_index = lutsize
            self.bandinfo.background_index = lutsize + 1

            # copy to all bands
            for code in RGB_CODES:
                lutindex = CODE_TO_LUTINDEX[code]
                # append the nodata and background while we are at it
                rgbindex = CODE_TO_RGBINDEX[code]
                nodata_value = stretch.nodata_rgba[rgbindex]
                background_value = stretch.background_rgba[rgbindex]
                lut[self.bandinfo.nodata_index] = nodata_value
                lut[self.bandinfo.background_index] = background_value

                self.lut[...,lutindex] = lut

            # now do alpha seperately - 255 for all except no data and background
            lutindex = CODE_TO_LUTINDEX['a']
            self.lut[...,lutindex].fill(255)
            rgbindex = CODE_TO_RGBINDEX['a']
            nodata_value = stretch.nodata_rgba[rgbindex]
            background_value = stretch.background_rgba[rgbindex]
            self.lut[self.bandinfo.nodata_index,lutindex] = nodata_value
            self.lut[self.bandinfo.background_index,lutindex] = background_value


        elif stretch.mode == viewerstretch.VIEWER_MODE_RGB:
            if len(stretch.bands) != 3:
                msg = 'must specify 3 bands when opening rgb'
                raise viewererrors.InvalidParameters(msg)


            self.bandinfo = {}
            self.lut = None

            # user supplies RGB
            for (band, code, localdata) in zip(stretch.bands, RGB_CODES, localdatalist):
                gdalband = dataset.GetRasterBand(band)

                if gdalband.DataType == gdal.GDT_Byte:
                    lutsize = 256
                else:
                    lutsize = DEFAULT_LUTSIZE

                if self.lut == None:
                    # LUT is shape [4,lutsize]. We apply the stretch seperately
                    # to each band. Order is RGBA (native order to make things easier)
                    # plus 2 for no data and background
                    self.lut = numpy.empty((4, lutsize + 2), numpy.uint8, 'C')

                lutindex = CODE_TO_LUTINDEX[code]
                # create stretch for each band
                lut, bandinfo = self.createStretchLUT(gdalband, stretch, lutsize, localdata)

                # append the nodata and background while we are at it
                rgbindex = CODE_TO_RGBINDEX[code]
                nodata_value = stretch.nodata_rgba[rgbindex]
                background_value = stretch.background_rgba[rgbindex]
                lut = numpy.append(lut, [nodata_value, background_value])

                bandinfo.nodata_index = lutsize
                bandinfo.background_index = lutsize + 1

                self.bandinfo[code] = bandinfo

                self.lut[lutindex] = lut

            # now do alpha seperately - 255 for all except no data and background
            lutindex = CODE_TO_LUTINDEX['a']
            self.lut[lutindex].fill(255)
            rgbindex = CODE_TO_RGBINDEX['a']
            nodata_value = stretch.nodata_rgba[rgbindex]
            background_value = stretch.background_rgba[rgbindex]
            # just use blue since alpha has no bandinfo and 
            # they should all be the same anyway
            nodata_index = self.bandinfo['b'].nodata_index
            background_index = self.bandinfo['b'].background_index

            self.lut[lutindex, nodata_index] = nodata_value
            self.lut[lutindex, background_index] = background_value
            
        else:
            msg = 'unsupported display mode'
            raise viewererrors.InvalidParameters(msg)

    def applyLUTSingle(self, data, mask):
        """
        Apply the LUT to a single band (color table
        or greyscale image) and return the result as
        a QImage
        """
        # work out where the NaN's are if float
        if numpy.issubdtype(data.dtype, numpy.floating):
            nanmask = numpy.isnan(data)
        else:
            nanmask = None

        # in case data outside range of stretch
        # don't use the in place version because if either min or max are
        # float we need the type to change
        data = numpy.clip(data, self.bandinfo.min, self.bandinfo.max)

        # apply scaling
        data = (data + self.bandinfo.offset) / self.bandinfo.scale

        # can only do lookups with integer data
        if numpy.issubdtype(data.dtype, numpy.floating):
            data = data.astype(numpy.integer)

        if nanmask is not None:
            # set NaN values back to LUT=0 if originally float
            data = numpy.where(nanmask, 0, data)

        # mask no data and background
        data = numpy.where(mask == MASK_NODATA_VALUE, self.bandinfo.nodata_index, data)
        data = numpy.where(mask == MASK_BACKGROUND_VALUE, self.bandinfo.background_index, data)

        # do the lookup
        bgra = self.lut[data]
        winysize, winxsize = data.shape
        
        # create QImage from numpy array
        # see http://www.mail-archive.com/pyqt@riverbankcomputing.com/msg17961.html
        # TODO there is a note in the docs saying Format_ARGB32_Premultiplied
        # is faster. Not sure what this means
        image = QImage(bgra.data, winxsize, winysize, QImage.Format_ARGB32)
        image.viewerdata = data # hold on to the data in case we
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

            # in case data outside range of stretch
            # don't use the in place version because if either min or max are
            # float we need the type to change
            data = numpy.clip(data, bandinfo.min, bandinfo.max)
            
            # apply scaling
            data = (data + bandinfo.offset) / bandinfo.scale

            # can only do lookups with integer data
            if numpy.issubdtype(data.dtype, numpy.floating):
                data = data.astype(numpy.integer)

            # set NaN values back to LUT=0 if data originally float
            if nanmask is not None:
                data = numpy.where(nanmask, 0, data)

            # mask no data and background
            data = numpy.where(mask == MASK_NODATA_VALUE, bandinfo.nodata_index, data)
            data = numpy.where(mask == MASK_BACKGROUND_VALUE, bandinfo.background_index, data)

            # do the lookup
            bgra[...,lutindex] = self.lut[lutindex][data]
        
        # now alpha - all 255 apart from nodata and background
        lutindex = CODE_TO_LUTINDEX['a']
        bgra[...,lutindex].fill(255)
        # just use blue since alpha has no bandinfo and 
        # they should all be the same anyway
        nodata_index = self.bandinfo['b'].nodata_index
        background_index = self.bandinfo['b'].background_index

        nodata_value = self.lut[lutindex, nodata_index]
        background_value = self.lut[lutindex, background_index]
        bgra[nodata_index, lutindex] = nodata_value
        bgra[background_index, lutindex] = background_value
        # turn into QImage
        # TODO there is a note in the docs saying Format_ARGB32_Premultiplied
        # is faster. Not sure what this means
        image = QImage(bgra.data, winxsize, winysize, QImage.Format_ARGB32)
        image.viewerdata = datalist # so we have the data if we want to calculate stats etc
        image.viewermask = mask
        return image


