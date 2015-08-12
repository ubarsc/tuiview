
"""
this module contains the LayerManager and related classes
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

from __future__ import print_function
import os
import sys
import json
import numpy
from osgeo import gdal
from osgeo import osr
from osgeo import ogr
from PyQt4.QtGui import QImage, QPainter, QPen
from PyQt4.QtCore import QObject, SIGNAL
import threading
if sys.version_info[0] < 3:
   import Queue as queue
else:
   import queue

from . import viewerRAT
from . import viewerLUT
from . import viewerstretch
from . import coordinatemgr
from . import viewererrors

# number of threads to call layer.getImage on - only raster layers supported
NUM_GETIMAGE_THREADS = os.getenv('TUIVIEW_GETIMAGE_THREADS','1')
# convert to int with care
try:
    NUM_GETIMAGE_THREADS = int(NUM_GETIMAGE_THREADS)
except ValueError:
    NUM_GETIMAGE_THREADS = 1

# Check if data without geospatial information is allowed
ALLOW_NOGEO = os.getenv('TUIVIEW_ALLOW_NOGEO','NO')
if ALLOW_NOGEO.upper() == 'YES':
    ALLOW_NOGEO = True
else:
    ALLOW_NOGEO = False

# raise exceptions rather than returning None
gdal.UseExceptions()

# Mappings between numpy datatypes and GDAL datatypes.
# Note that ambiguities are resolved by the order - the first one found
# is the one chosen.
dataTypeMapping = [
    (numpy.uint8,gdal.GDT_Byte),
    (numpy.bool,gdal.GDT_Byte),
    (numpy.int16,gdal.GDT_Int16),
    (numpy.uint16,gdal.GDT_UInt16),
    (numpy.int32,gdal.GDT_Int32),
    (numpy.uint32,gdal.GDT_UInt32),
    (numpy.single,gdal.GDT_Float32),
    (numpy.float,gdal.GDT_Float64)
]

def GDALTypeToNumpyType(gdaltype):
    """
    Given a gdal data type returns the matching
    numpy data type
    """
    for (numpy_type, test_gdal_type) in dataTypeMapping:
        if test_gdal_type == gdaltype:
            return numpy_type
    raise viewererrors.TypeConversionError("Unknown GDAL datatype: %s"%gdaltype)

def NumpyTypeToGDALType(numpytype):
    """
    For a given numpy data type returns the matching
    GDAL data type
    """
    for (test_numpy_type, gdaltype) in dataTypeMapping:
        if test_numpy_type == numpytype:
            return gdaltype
    msg = "Unknown numpy datatype: %s" % numpytype
    raise viewererrors.TypeConversionError(msg)

def _callGetImage(q):
    """
    Calls getImage on each layer in the queue.
    Passed to a thread
    """
    while True:
        layer = q.get()
        layer.getImage()
        q.task_done()

    return None

class OverviewInfo(object):
    """
    Stores size and index of an overview
    """
    def __init__(self, xsize, ysize, fullrespixperpix, index):
        self.xsize = xsize
        self.ysize = ysize
        self.fullrespixperpix = fullrespixperpix
        self.index = index

class OverviewManager(object):
    """
    This class contains a list of valid overviews
    and allows the best overview to be retrieved
    """
    def __init__(self):
        self.overviews = None

    def getFullRes(self):
        "Get the full res overview - ie the non overview image"
        return self.overviews[0]

    def loadOverviewInfo(self, ds, bands):
        """
        Load the overviews from the GDAL dataset into a list
        bands should be a list or tuple of band indices.
        Checks are made that all lists bands contain the
        same sized overviews
        """
        # i think we can assume that all the bands are the same size
        # add an info for the full res - this should always be location 0
        ovi = OverviewInfo(ds.RasterXSize, ds.RasterYSize, 1.0, 0)
        self.overviews = [ovi]

        # for the overviews
        # start with the first band and go from there
        try:
            band = ds.GetRasterBand(bands[0])
        except RuntimeError as e:
            # when the stretch refers to a band that does not exist
            # this is the first bit of code that fails
            # raise a proper exceptions
            raise viewererrors.InvalidStretch(str(e))

        count = band.GetOverviewCount()
        for index in range(count):
            ov = band.GetOverview(index)

            # do the other bands have the same resolution overview
            # at the same index?
            overviewok = True
            for bandnum in bands[1:]:
                otherband = ds.GetRasterBand(bandnum)
                otherov = otherband.GetOverview(index)
                if otherov.XSize != ov.XSize or otherov.YSize != ov.YSize:
                    overviewok = False
                    break

            if overviewok:
                # calc the conversion to full res pixels
                fullrespixperpix = float(ds.RasterXSize) / float(ov.XSize) 
                # should do both ways?
                # remember index 0 is full res so all real overviews are +1
                ovi = OverviewInfo(ov.XSize, ov.YSize, fullrespixperpix, 
                                            index + 1)
                self.overviews.append(ovi)

        # make sure they are sorted by area - biggest first
        self.overviews.sort(key=lambda ov: ov.xsize * ov.ysize, reverse=True)

    def findBestOverview(self, imgpixperwinpix):
        """
        Finds the best overview for given imgpixperwinpix
        """
        selectedovi = self.overviews[0]
        for ovi in self.overviews[1:]:
            if ovi.fullrespixperpix > imgpixperwinpix:
                break # gone too far, selectedovi is selected
            else:
                # got here overview must be ok, but keep going
                selectedovi = ovi

        return selectedovi

NOTSET_STRING = 'Not Set'

class PropertyInfo(object):
    """
    Container for Info for proerties window
    """
    def __init__(self):
        self.fileInfo = []  # list of tuples
        self.sr = None # SpatialReference
        self.bandInfo = [] # list of lists of tuples
        self.bandNames = [] # list of strings
        self.histograms = {} # dictionary of min, max, data tuples
                            # keyed on bandName

    def addFileInfo(self, name, value):
        "Add a file info"
        self.fileInfo.append((name, value))

    def setSR(self, sr):
        "set spatial reference"
        self.sr = sr

    def getUTMZone(self):
        utmZone = NOTSET_STRING
        if self.sr is not None:
            zone = self.sr.GetUTMZone()
            if zone != 0:
                utmZone = str(zone)
        return utmZone

    def getProjection(self):
        proj = NOTSET_STRING
        if self.sr is not None:
            proj = self.sr.GetAttrValue('PROJECTION')
        return proj

    def getDatum(self):
        datum = NOTSET_STRING
        if self.sr is not None:
            datum = self.sr.GetAttrValue('DATUM')
        return datum

    def getSpheroid(self):
        spheroid = NOTSET_STRING
        if self.sr is not None:
            spheroid = self.sr.GetAttrValue('SPHEROID')
        return spheroid

    def getUnits(self):
        units = NOTSET_STRING
        if self.sr is not None:
            units = self.sr.GetLinearUnitsName()
        return units

    def getWKT(self):
        wkt = NOTSET_STRING
        if self.sr is not None:
            wkt = self.sr.ExportToPrettyWkt()
        return wkt

    def addBandInfo(self, bandName, infoList):
        "sets info for a band"
        self.bandInfo.append(infoList)
        self.bandNames.append(bandName)

    def addHistogramInfo(self, bandName, histInfo):
        """
        sets histogram info for a band. Should be a tuple
        of min, max, data
        """
        self.histograms[bandName] = histInfo

class ViewerLayer(object):
    """
    Base class for a type of layer
    """
    def __init__(self):
        self.image = None
        self.filename = None
        self.title = None # basename of filename
        self.displayed = True # use LayerManager.setDisplayedState
        self.quiet = False # not displayed in title bar. Set when calling add*()

    def getImage(self):
        "return a QImage with the data in it"
        raise NotImplementedError("Must implement in derived class")

    def getPropertiesInfo(self):
        "Return the properties as a PropertyInfo instance we can show the user"
        raise NotImplementedError("Must implement in derived class")

    def toFile(self, fileobj):
        "write information to re-create layer as JSON"
        raise NotImplementedError("Must implement in derived class")

    def fromFile(self, fileobj, width, height):
        """
        Initialise this instance of the class with information from json in fileobj
        """
        raise NotImplementedError("Must implement in derived class")

VIEWER_NONSQUARE_PIXEL_THRESHOLD = 0.001 # 0.1%

class ViewerRasterLayer(ViewerLayer):
    """
    Represents a raster layer
    """
    def __init__(self, layermanager):
        ViewerLayer.__init__(self)
        self.coordmgr = coordinatemgr.RasterCoordManager()
        self.gdalDataset = None
        self.updateAccess = False
        self.transform = None
        self.bandNames = None
        self.wavelengths = None
        self.noDataValues = None
        self.attributes = viewerRAT.ViewerRAT()
        self.overviews = OverviewManager()
        self.lut = viewerLUT.ViewerLUT()
        self.stretch = None
        self.image = None

        # connect the signals from the RAT and LUT back to the layermanager
        layermanager.connect(self.lut, SIGNAL("newProgress(QString)"), 
                                                    layermanager.newProgress)
        layermanager.connect(self.lut, SIGNAL("endProgress()"), 
                                                    layermanager.endProgress)
        layermanager.connect(self.lut, SIGNAL("newPercent(int)"), 
                                                    layermanager.newPercent)

        layermanager.connect(self.attributes, SIGNAL("newProgress(QString)"), 
                                                    layermanager.newProgress)
        layermanager.connect(self.attributes, SIGNAL("endProgress()"), 
                                                    layermanager.endProgress)
        layermanager.connect(self.attributes, SIGNAL("newPercent(int)"), 
                                                    layermanager.newPercent)

    def toFile(self, fileobj):
        """
        Write all the information needed to re-open this layer
        """
        dict = {'type' : 'raster'}
        fileobj.write(json.dumps(dict) + '\n')

        dict = {'filename' : self.filename, 'update' : self.updateAccess,
            'stretch' : self.stretch.toString(), 'displayed' : self.displayed,
            'quiet' : self.quiet}
        fileobj.write(json.dumps(dict) + '\n')
        self.lut.saveToFile(fileobj)

    def fromFile(self, fileobj, width, height):
        """
        Reads information (written by toFile) and builds a layer
        assumes that the 'type' line has already been read.
        """
        line = fileobj.readline()
        dict = json.loads(line)

        filename = dict['filename']
        self.quiet = dict['quiet']
        self.displayed = dict['displayed']

        ds = gdal.Open(filename, gdal.GA_Update)

        stretch = viewerstretch.ViewerStretch.fromString(dict['stretch'])
        lut = viewerLUT.ViewerLUT.createFromFile(fileobj, stretch)

        self.open(ds, width, height, stretch, lut)
        self.changeUpdateAccess(dict['update']) # won't do anything if already ro

    def open(self, gdalDataset, width, height, stretch, lut=None):
        """
        Open a filename as a raster layer. width and height is the
        display size. stretch is the ViewerStretch instance to use.
        if specified, the lut is used to display the data, otherwise
        calculated from the stretch
        Keeps a reference to gdalDataset
        Assumes gdalDataset opened in read only mode.
        """
        # open the file
        self.filename = gdalDataset.GetDescription()
        self.title = os.path.basename(self.filename)
        self.gdalDataset = gdalDataset
        self.updateAccess = False

        # do some checks to see if we can deal with the data
        # currently only support square pixels and non rotated
        transform = self.gdalDataset.GetGeoTransform()
        if transform[1] < 0 or transform[5] > 0:
            if ALLOW_NOGEO:
                # If image isn't north up, and unmapped data is allowed
                # flip the pixel resolution to trick TuiView into 
                # handling it as north up data.
                # Enables opening data with no spatial reference (e.g., 
                # level1 / level1b).
                transform = (transform[0],
                             transform[1],
                             transform[2],
                             transform[3],
                             transform[4],
                             transform[5]*-1)
            else:
                msg = 'Only north-up images allowed. ' \
                     'To disable this check set:\n"TUIVIEW_ALLOW_NOGEO=YES"'
                raise viewererrors.InvalidDataset(msg)

        if transform[2] != 0 or transform[4] != 0:
            msg = 'Only non-rotated images supported'
            raise viewererrors.InvalidDataset(msg)

        # ideally transform[1] == -transform[5] but might not due to rounding
        if (((transform[1] + transform[5]) / transform[1]) > 
                VIEWER_NONSQUARE_PIXEL_THRESHOLD):
            msg = 'Only square pixels supported'
            raise viewererrors.InvalidDataset(msg)

        self.transform = transform

        # store the stretch
        self.stretch = stretch

        # load the valid overviews
        self.overviews.loadOverviewInfo(self.gdalDataset, stretch.bands)

        # reset these values
        firstoverview = self.overviews.getFullRes()
        self.coordmgr.setDisplaySize(width, height)
        self.coordmgr.setGeoTransformAndSize(transform, firstoverview.xsize, 
                                                firstoverview.ysize)
        # This may be changed by the LayerManager if there are other layers
        self.coordmgr.setTopLeftPixel(0, 0)  
        self.coordmgr.calcZoomFactor(firstoverview.xsize, firstoverview.ysize)

        # if we are single band read attributes if any
        if len(stretch.bands) == 1:
            gdalband = self.gdalDataset.GetRasterBand(stretch.bands[0])
            self.attributes.readFromGDALBand(gdalband, self.gdalDataset)
            if self.attributes.hasAttributes():
                # tell stretch to create same size as attribute table
                self.stretch.setAttributeTableSize(self.attributes.getNumRows())
        else:
            # keep blank
            self.attributes.clear()

        # read in the LUT if not specified
        if lut is None:
            self.lut.createLUT(self.gdalDataset, stretch, self.attributes)
        else:
            self.lut = lut

        # grab the band names
        self.bandNames = self.getBandNames()

        # grab the wavelengths
        self.wavelengths = self.getWavelengths()

        # the no data values for each band
        self.noDataValues = self.getNoDataValues()

    def getBandNames(self):
        """
        Return the list of band names
        """
        bandNames = []
        for n in range(self.gdalDataset.RasterCount):
            band = self.gdalDataset.GetRasterBand(n+1)
            name = band.GetDescription()
            if name == '':
                # in case the name is missing
                name = 'Band %d' % (n+1)
            bandNames.append(name)
        return bandNames
        
    def getWavelengths(self):
        """
        Return the list of wavelength if file
        conforms to the metadata provided by the 
        ENVI driver, or None.
        Other formats will be added in future.
        """

        # Wavelength units to strip off metadata
        wavelength_units = ['nm','um']

        wavelengths = []
        ok = False

        drivername = self.gdalDataset.GetDriver().ShortName
        if drivername == 'ENVI':
            ok = True
            # GetMetadataItem seems buggy for ENVI
            # get the lot and go through
            meta = self.gdalDataset.GetMetadata()
            # go through each band
            for n in range(self.gdalDataset.RasterCount):
                # get the metadata item based on band name
                metaname = "Band_%d" % (n+1)
                if metaname in meta:
                    item = meta[metaname]
                    # Try to replace wavelength units
                    # Do this rather than stripping off letters
                    # as metadata might not be a wavelength
                    for wl_unit in wavelength_units:
                        item = item.replace(wl_unit,'')
                    # If wavelengths are stored as:
                    #    951.20 (951.20)
                    # subset to before bracket
                    item = item[0:item.find('(')]
                    # try to convert to float
                    try:
                        wl = float(item)
                    except ValueError:
                        ok = False
                        break
                    # must be ok
                    wavelengths.append(wl)
                else:
                    ok = False
                    break
        # failed
        if not ok:
            wavelengths = None

        return wavelengths
        
    def getNoDataValues(self):
        """
        Return a list of no data values - one for each band
        """
        noData = []
        for n in range(self.gdalDataset.RasterCount):
            band = self.gdalDataset.GetRasterBand(n+1)
            value = band.GetNoDataValue() # returns None if not set
            noData.append(value)
        return noData

    def highlightRows(self, color, selectionArray=None):
        """
        Highlight selected rows in the LUT
        """
        self.lut.highlightRows(color, selectionArray)
        # re-apply the lut to the data from last time
        self.image = self.lut.applyLUTSingle(self.image.viewerdata, 
                                                self.image.viewermask)

    def setColorTableLookup(self, lookupArray=None, colName=None, 
                                surrogateLUT=None, surrogateName=None):
        """
        Use array as a lookup to color table
        """
        self.lut.setColorTableLookup(lookupArray, colName, surrogateLUT, 
                                                    surrogateName)
        # re-apply the lut to the data from last time
        self.image = self.lut.applyLUTSingle(self.image.viewerdata, 
                                                self.image.viewermask)

    def setNewStretch(self, newstretch, local=False):
        """
        Set the new stretch
        """
        newbands = self.stretch.bands != newstretch.bands
        if newbands:
            # only need to do this if bands have changed
            self.overviews.loadOverviewInfo(self.gdalDataset, newstretch.bands)

        image = None
        if local and not newbands:
            # we can just grab the stats from the last read
            image = self.image

        # if we have an attribute table create stretch same size
        if self.attributes.hasAttributes():
            newstretch.setAttributeTableSize(self.attributes.getNumRows())

        self.lut.createLUT(self.gdalDataset, newstretch, self.attributes, image)

        self.stretch = newstretch
        # note - we need to do this to reapply the stretch
        # but it re-reads the data always.
        # not sure it is a big deal since GDAL caches
        self.getImage()

        if local and newbands:
            # this is a bit of a hack. We needed to do a 
            # getData to get the new bands loaded. Now
            # we can get the stats and apply the stretch locally
            self.lut.createLUT(self.gdalDataset, newstretch, self.attributes, 
                                                                self.image)
            self.getImage()

    def saveStretchToFile(self, stretch):
        """
        Saves the given stretch and current LUT to the file
        """
        if self.updateAccess:
            # write the stretch
            stretch.writeToGDAL(self.gdalDataset)

            # write the LUT
            self.lut.writeToGDAL(self.gdalDataset)
        else:
            # ok we need to close the current file handle and re-open in write mode
            del self.gdalDataset
            try:
                # now open as writeable
                dataset = gdal.Open(self.filename, gdal.GA_Update)

                # write the stretch
                stretch.writeToGDAL(dataset)

                # write the LUT
                self.lut.writeToGDAL(dataset)

                # close this (writeable) file handle
                del dataset
            except RuntimeError:
                raise viewererrors.InvalidDataset('Unable to save stretch to file')
            finally:
                # attempt to open the file readonly again
                self.gdalDataset = gdal.Open(self.filename)

    def deleteStretchFromFile(self):
        """
        deletes the stretch and current LUT from the file
        """
        if self.updateAccess:
            # delete the stretch
            viewerstretch.ViewerStretch.deleteFromGDAL(self.gdalDataset)

            # delete the LUT
            viewerLUT.ViewerLUT.deleteFromGDAL(self.gdalDataset)
        else:
            # ok we need to close the current file handle and re-open in write mode
            del self.gdalDataset
            try:
                # now open as writeable
                dataset = gdal.Open(self.filename, gdal.GA_Update)

                # delete the stretch
                viewerstretch.ViewerStretch.deleteFromGDAL(dataset)

                # delete the LUT
                viewerLUT.ViewerLUT.deleteFromGDAL(dataset)

                # close this (writeable) file handle
                del dataset
            except RuntimeError:
                msg = 'Unable to delete stretch from file'
                raise viewererrors.InvalidDataset(msg)
            finally:
                # attempt to open the file readonly again
                self.gdalDataset = gdal.Open(self.filename)

    def exportStretchandLUTToText(self, fname):
        """
        Exports the current stretch and lookup table to a 
        JSON formatted text file
        """
        fileobj = open(fname, 'w')

        stretchstr = self.stretch.toString()
        fileobj.write("%s\n" % stretchstr)

        self.lut.saveToFile(fileobj)

        fileobj.close()

    def changeUpdateAccess(self, update):
        """
        Re-opens the GDAL dataset in the new update mode (True
        for update False for readonly)
        """
        if self.updateAccess == update:
            # already in this mode - multiple query windows may be out of date
            # with each other
            return

        # close the current file handle and re-open in new mode
        self.gdalDataset.FlushCache()
        del self.gdalDataset
        del self.attributes.gdalRAT
        try:
            if update:
                self.gdalDataset = gdal.Open(self.filename, gdal.GA_Update)
            else:
                self.gdalDataset = gdal.Open(self.filename)

            self.updateAccess = update
        except RuntimeError:
            if update:
                # wanted to make updateable, but failed
                # retry as read-only
                try:
                    self.gdalDataset = gdal.Open(self.filename)
                    self.updateAccess = False
                except RuntimeError:
                    msg = "Can't open dataset readonly" 
                    raise IOError(msg)

                # attributes handle will be stale...
                if len(self.stretch.bands) == 1:
                    gdalband = self.gdalDataset.GetRasterBand(self.stretch.bands[0])
                    self.attributes.readFromGDALBand(gdalband, self.gdalDataset)

                # successfully reopened readonly
                msg = 'Unable to change mode of dataset'
                raise viewererrors.InvalidDataset(msg)

            else:
                # wanted to open readonly, but that failed
                # file can't exist any more
                # app needs to exit since we don't have a dataset
                self.gdalDataset = None
                msg = "Can't open dataset readonly" 
                raise IOError(msg)

        # attributes handle will be stale...
        if len(self.stretch.bands) == 1:
            gdalband = self.gdalDataset.GetRasterBand(self.stretch.bands[0])
            self.attributes.readFromGDALBand(gdalband, self.gdalDataset)

    def writeRATColumnOrder(self):
        """
        calls self.attributes.writeColumnOrderToGDAL. Assumes file upen in 
        update mode - raises exception otherwise
        """
        if not self.updateAccess:
            msg = 'file needs to be open in update mode'
            raise viewererrors.InvalidDataset(msg)

        self.attributes.writeColumnOrderToGDAL(self.gdalDataset)

    def getImage(self):
        """
        Refresh the 'image' which is a QImage instance used for rendering.
        Does the selection of overview, choosing of area (based on coordmgr)
        reading, and applying LUT.
        """
        # find the best overview based on imgpixperwinpix
        imgpix = self.coordmgr.imgPixPerWinPix
        selectedovi = self.overviews.findBestOverview(imgpix)
        #print(selectedovi.index)

        # if this layer isn't anywhere near where we currently are
        # don't even bother reading - just create a empty QImage
        # and nothing will be rendered
        if self.coordmgr.pixTop < 0 and self.coordmgr.pixBottom < 0:
            self.image = QImage()
            return 
        elif self.coordmgr.pixLeft < 0 and self.coordmgr.pixRight < 0:
            self.image = QImage()
            return
        elif (self.coordmgr.pixLeft > self.gdalDataset.RasterXSize and 
                    self.coordmgr.pixRight > self.gdalDataset.RasterXSize):
            self.image = QImage()
            return
        elif (self.coordmgr.pixTop > self.gdalDataset.RasterYSize and 
                    self.coordmgr.pixBottom > self.gdalDataset.RasterYSize):
            self.image = QImage()
            return
        
        fullrespixperovpix = selectedovi.fullrespixperpix
        pixTop = max(self.coordmgr.pixTop, 0)
        pixLeft = max(self.coordmgr.pixLeft, 0)
        pixBottom = min(self.coordmgr.pixBottom, self.gdalDataset.RasterYSize)
        pixRight = min(self.coordmgr.pixRight, self.gdalDataset.RasterXSize)
        ovtop = int(pixTop / fullrespixperovpix)
        ovleft = int(pixLeft / fullrespixperovpix)
        ovbottom = int(numpy.ceil(pixBottom / fullrespixperovpix))
        ovright = int(numpy.ceil(pixRight / fullrespixperovpix))
        ovtop = max(ovtop, 0)
        ovleft = max(ovleft, 0)
        ovbottom = min(ovbottom, selectedovi.ysize)
        ovright = min(ovright, selectedovi.xsize)
        ovxsize = ovright - ovleft
        ovysize = ovbottom - ovtop

        # The display coordinates of the top-left corner of the raster data.
        #  Often this
        # is (0, 0), but need not be if there is blank area left/above the 
        # raster data
        # because we have the display in ints, other metrics floats,
        # we need to do the size calculations as floats, convert
        # to int at last. Otherwise black lines appear around side
        (dspRastLeft, dspRastTop) = self.coordmgr.pixel2displayF(
                                                        pixLeft, pixTop)
        (dspRastRight, dspRastBottom) = self.coordmgr.pixel2displayF(
                                                        pixRight, pixBottom)
        dspRastXSize = int(numpy.round(dspRastRight - dspRastLeft))
        dspRastYSize = int(numpy.round(dspRastBottom - dspRastTop))
        dspRastLeft = int(dspRastLeft)
        dspRastTop = int(dspRastTop)
        dspRastRight = dspRastLeft + dspRastXSize
        dspRastBottom = dspRastTop + dspRastYSize

        if self.coordmgr.imgPixPerWinPix < 1:
            # need to calc 'extra' around the edge as we have partial pixels
            # GDAL reads in full pixels
            (dspRastAbsLeft, dspRastAbsTop) = self.coordmgr.pixel2display(
                                    numpy.floor(pixLeft), numpy.floor(pixTop))
            (dspRastAbsRight, dspRastAbsBottom) = (
                    self.coordmgr.pixel2display(
                    numpy.ceil(pixRight), numpy.ceil(pixBottom)))
            dspLeftExtra = ((dspRastLeft - dspRastAbsLeft) 
                                    / fullrespixperovpix)
            dspTopExtra = ((dspRastTop - dspRastAbsTop) 
                                    / fullrespixperovpix)
            dspRightExtra = ((dspRastAbsRight - dspRastRight) 
                                    / fullrespixperovpix)
            dspBottomExtra = ((dspRastAbsBottom - dspRastBottom) 
                                    / fullrespixperovpix)
            # be aware rounding errors
            dspRightExtra = max(dspRightExtra, 0)
            dspBottomExtra = max(dspBottomExtra, 0)


        # only need to do the mask once
        mask = numpy.empty((self.coordmgr.dspHeight, self.coordmgr.dspWidth), dtype=numpy.uint8)
        mask.fill(viewerLUT.MASK_BACKGROUND_VALUE) # set to background
        
        dataslice = (slice(dspRastTop, dspRastTop+dspRastYSize),
            slice(dspRastLeft, dspRastLeft+dspRastXSize))
        mask[dataslice] = viewerLUT.MASK_IMAGE_VALUE # 0 where there is data
        nodata_mask = None

        if len(self.stretch.bands) == 3:
            # rgb
            datalist = []
            for bandnum in self.stretch.bands:
                band = self.gdalDataset.GetRasterBand(bandnum)

                # create blank array of right size to read in to. This data
                # array represents the window pixels, one-for-one
                numpytype = GDALTypeToNumpyType(band.DataType)
                shape = (self.coordmgr.dspHeight, self.coordmgr.dspWidth)
                data = numpy.zeros(shape, dtype=numpytype) 

                # get correct overview
                if selectedovi.index > 0:
                    band = band.GetOverview(selectedovi.index - 1)

                # read into correct part of our window array
                if self.coordmgr.imgPixPerWinPix >= 1.0:
                    dataTmp = band.ReadAsArray(ovleft, ovtop, 
                        ovxsize, ovysize,
                        dspRastXSize, dspRastYSize)
                    data[dataslice] = dataTmp
                else:
                    dataTmp = band.ReadAsArray(ovleft, ovtop, 
                                    ovxsize, ovysize)
                    data[dataslice] = replicateArray(dataTmp, data[dataslice], 
                        dspLeftExtra, dspTopExtra, dspRightExtra, 
                            dspBottomExtra)
                    
                # do the no data test
                nodata_value = self.noDataValues[bandnum-1]
                if nodata_value is not None:
                    inimage_and_nodata = numpy.logical_and(
                            mask == viewerLUT.MASK_IMAGE_VALUE, 
                            data == nodata_value)
                    if nodata_mask is None:
                        nodata_mask = inimage_and_nodata
                    else:
                        # should it be 'or' or 'and' ?
                        nodata_mask = numpy.logical_and(nodata_mask, 
                                        inimage_and_nodata)

                datalist.append(data)

            # apply the no data
            if nodata_mask is not None:
                mask = numpy.where(nodata_mask, viewerLUT.MASK_NODATA_VALUE, 
                                        mask)

            # apply LUT
            self.image = self.lut.applyLUTRGB(datalist, mask)

        else:
            # must be single band
            band = self.gdalDataset.GetRasterBand(self.stretch.bands[0])

            # create blank array of right size to read in to
            numpytype = GDALTypeToNumpyType(band.DataType)
            shape = (self.coordmgr.dspHeight, self.coordmgr.dspWidth)
            data = numpy.zeros(shape, dtype=numpytype) 

            # get correct overview
            if selectedovi.index > 0:
                band = band.GetOverview(selectedovi.index - 1)

            # read into correct part of our window array
            if self.coordmgr.imgPixPerWinPix >= 1.0:
                data[dataslice] = band.ReadAsArray(ovleft, ovtop, 
                    ovxsize, ovysize,
                    dspRastXSize, dspRastYSize)
            else:
                dataTmp = band.ReadAsArray(ovleft, ovtop, 
                        ovxsize, ovysize)
                data[dataslice] = replicateArray(dataTmp, data[dataslice], 
                    dspLeftExtra, dspTopExtra, dspRightExtra,
                         dspBottomExtra)

            # do we have no data for this band?
            nodata_value = self.noDataValues[self.stretch.bands[0] - 1]
            if nodata_value is not None:
            
                inimage_and_nodata = numpy.logical_and(
                        mask == viewerLUT.MASK_IMAGE_VALUE, 
                        data == nodata_value)
                mask = numpy.where(inimage_and_nodata, 
                        viewerLUT.MASK_NODATA_VALUE, 
                        mask)
                        
            # apply LUT
            self.image = self.lut.applyLUTSingle(data, mask)

    def getPropertiesInfo(self):
        """
        Get the properties of the file as a PropertyInfo for presentation to user.
        Do something similar to gdalinfo.
        """
        info = PropertyInfo()
        proj = self.gdalDataset.GetProjection()
        sr = osr.SpatialReference(proj)
        info.setSR(sr)

        driver = self.gdalDataset.GetDriver()
        driverString = "%s/%s" % (driver.ShortName, driver.LongName)
        info.addFileInfo('Driver:', driverString)

        fileString = " ".join(self.gdalDataset.GetFileList())
        info.addFileInfo('Files:', fileString)

        info.addFileInfo('Number of Bands:', '%d' % self.gdalDataset.RasterCount)

        if len(self.overviews.overviews) > 1:
            overviewString = "Present"
        else:
            overviewString = "Absent"
        info.addFileInfo('Overviews:', overviewString)

        sizeString = '%d, %d' % (self.gdalDataset.RasterXSize, 
                                    self.gdalDataset.RasterYSize)
        info.addFileInfo('Size:', sizeString)

        pixelSizeString = '%f, %f' % (self.transform[1], self.transform[5])
        info.addFileInfo('Pixel Size:', pixelSizeString)

        (ulx, uly) = self.coordmgr.pixel2world(0, 0)
        info.addFileInfo('Upper Left', '%f, %f' % (ulx, uly))
        (llx, lly) = self.coordmgr.pixel2world(0, self.gdalDataset.RasterYSize)
        info.addFileInfo('Lower Left', '%f, %f' % (llx, lly))
        (urx, ury) = self.coordmgr.pixel2world(self.gdalDataset.RasterXSize, 0)
        info.addFileInfo('Upper Right', '%f, %f' % (urx, ury))
        (lrx, lry) = self.coordmgr.pixel2world(self.gdalDataset.RasterXSize, 
                                                self.gdalDataset.RasterYSize)
        info.addFileInfo('Lower Right', '%f, %f' % (lrx, lry))
        (cx, cy) = self.coordmgr.pixel2world(
                                        self.gdalDataset.RasterXSize / 2.0, 
                                        self.gdalDataset.RasterYSize / 2.0)
        info.addFileInfo('Center', '%f, %f' % (cx, cy))

        for nband in range(self.gdalDataset.RasterCount):
            bandInfo = []
            band = self.gdalDataset.GetRasterBand(nband+1)
            metadata = band.GetMetadata()

            if 'LAYER_TYPE' in metadata:
                layerType = metadata['LAYER_TYPE']
            else:
                layerType = NOTSET_STRING
            bandInfo.append(('Layer Type:', layerType))

            nodata = band.GetNoDataValue()
            if nodata is None:
                nodataString = NOTSET_STRING
            else:
                nodataString = '%f' % nodata
            bandInfo.append(('No Data Value:', nodataString))

            if 'STATISTICS_MAXIMUM' in metadata:
                statsMax = metadata['STATISTICS_MAXIMUM']
            else:
                statsMax = NOTSET_STRING
            bandInfo.append(('Maximum:', statsMax))

            if 'STATISTICS_MEAN' in metadata:
                statsMean = metadata['STATISTICS_MEAN']
            else:
                statsMean = NOTSET_STRING
            bandInfo.append(('Mean', statsMean))

            if 'STATISTICS_MEDIAN' in metadata:
                statsMedian = metadata['STATISTICS_MEDIAN']
            else:
                statsMedian = NOTSET_STRING
            bandInfo.append(('Median', statsMedian))

            if 'STATISTICS_MINIMUM' in metadata:
                statsMin = metadata['STATISTICS_MINIMUM']
            else:
                statsMin = NOTSET_STRING
            bandInfo.append(('Minimum', statsMin))

            if 'STATISTICS_MODE' in metadata:
                statsMode = metadata['STATISTICS_MODE']
            else:
                statsMode = NOTSET_STRING
            bandInfo.append(('Mode:', statsMode))

            if 'STATISTICS_STDDEV' in metadata:
                statsStd = metadata['STATISTICS_STDDEV']
            else:
                statsStd = NOTSET_STRING
            bandInfo.append(('Standard Deviation:', statsStd))

            if ('STATISTICS_SKIPFACTORX' in metadata and 
                    'STATISTICS_SKIPFACTORY' in metadata):
                skipX = metadata['STATISTICS_SKIPFACTORX']
                skipY = metadata['STATISTICS_SKIPFACTORY']
                statsSkip = '%s, %s' % (skipX, skipY)
            else:
                statsSkip = NOTSET_STRING
            bandInfo.append(('Skip Factor:', statsSkip))

            dataTypeName = gdal.GetDataTypeName(band.DataType)
            bandInfo.append(('Data Type:', dataTypeName))

            bandName = band.GetDescription()
            info.addBandInfo(bandName, bandInfo)

            # check the histo info - from RAT if available
            histoIdx = None
            rat = band.GetDefaultRAT()
            if rat is not None:
                for col in range(rat.GetColumnCount()):
                    if rat.GetUsageOfCol(col) == gdal.GFU_PixelCount:
                        histoIdx = col
                        break

            if ('STATISTICS_HISTOMIN' in metadata and
                    'STATISTICS_HISTOMAX' in metadata and
                    (histoIdx is not None or 'STATISTICS_HISTOBINVALUES' in metadata)):
                histMin = float(metadata['STATISTICS_HISTOMIN'])
                histMax = float(metadata['STATISTICS_HISTOMAX'])
                if histoIdx is not None:
                    histData = rat.ReadAsArray(histoIdx)
                else:
                    histDataString = metadata['STATISTICS_HISTOBINVALUES']
                    histData = [float(x) for x in histDataString.split('|') if x != '']
                    histData = numpy.array(histData)
                    
                info.addHistogramInfo(bandName, (histMin, histMax, histData))

        return info

QUERY_CURSOR_HALFSIZE = 8 # number of pixels
QUERY_CURSOR_WIDTH = 1 # in pixels

# types of cursor
CURSOR_CROSS = 0
CURSOR_CROSSHAIR = 1

class ViewerQueryPointLayer(ViewerLayer):
    """
    Class for display of query points.
    """
    def __init__(self):
        ViewerLayer.__init__(self)
        self.coordmgr = coordinatemgr.VectorCoordManager()
        self.queryPoints = {}
        self.image = None

    def setQueryPoint(self, senderid, easting, northing, color,
                            size=None, cursor=None):
        """
        Add/replace a query point based on the id() of the requesting object
        """
        if size is None:
            size = QUERY_CURSOR_HALFSIZE
        if cursor is None:
            cursor = CURSOR_CROSS
        self.queryPoints[senderid] = (easting, northing, color, size, cursor)

    def removeQueryPoint(self, senderid):
        """
        remove a query point based on the id() of the requesting object
        """
        if senderid in self.queryPoints:
            del self.queryPoints[senderid]

    def getImage(self):
        """
        Update self.image
        """
        if self.coordmgr.dspWidth is None:
            self.image = QImage()
        else:
            self.image = QImage(self.coordmgr.dspWidth, 
                    self.coordmgr.dspHeight, QImage.Format_ARGB32)
            self.image.fill(0)
            pen = QPen()
            pen.setWidth(QUERY_CURSOR_WIDTH)
            paint = QPainter(self.image)
            for senderid in self.queryPoints:
                (easting, northing, color, size, cursor) = (
                                                self.queryPoints[senderid])
                display = self.coordmgr.world2display(easting, northing)
                if display is not None:
                    (dspX, dspY) = display
                    dspX = int(dspX)
                    dspY = int(dspY)
                    pen.setColor(color)
                    paint.setPen(pen)
                    if cursor == CURSOR_CROSS:
                        paint.drawLine(dspX - size, dspY, dspX + size, dspY)
                        paint.drawLine(dspX, dspY - size, dspX, dspY + size)
                    else:
                        # CURSOR_CROSSHAIR
                        paint.drawLine(dspX - size, dspY, dspX - 2, dspY)
                        paint.drawLine(dspX + 2, dspY, dspX + size, dspY)
                        paint.drawLine(dspX, dspY - size, dspX, dspY - 2)
                        paint.drawLine(dspX, dspY + 2, dspX, dspY + size)
                        paint.drawArc(dspX - size, dspY - size, 
                                        size * 2, size * 2, 0, 16 * 360)
            paint.end()
                
DEFAULT_VECTOR_COLOR = (255, 255, 0, 255)

class ViewerVectorLayer(ViewerLayer):
    """
    A vector layer. Uses vectorrasterizer
    to burn in the outlines
    """
    def __init__(self):
        ViewerLayer.__init__(self)
        self.ogrDataSource = None
        self.ogrLayer = None # must have both dataset and lyr for ref counts
        self.coordmgr = coordinatemgr.VectorCoordManager()
        # we use a mini LUT to convert the 1's and zeros to colours
        # we leave the first index blank to it is black/invisible
        self.lut = numpy.zeros((2, 4), numpy.uint8)
        self.image = None
        self.filename = None
        self.origSQL = None # if query, not layer name (isResultSet = True)
        self.sql = None
        self.linewidth = 1
        self.isResultSet = False

    def __del__(self):
        # unfortunately this isn't called when the viewer
        # is closed and there are still layers existing...
        # but is when the user removes the layer
        # perhaps we can do something better here
        if (self.isResultSet and self.ogrDataSource is not None and 
                    self.ogrLayer is not None):
            self.ogrDataSource.ReleaseResultSet(self.ogrLayer)

    def toFile(self, fileobj):
        "write information to re-create layer as JSON"
        dict = {'type' : 'vector'}
        fileobj.write(json.dumps(dict) + '\n')

        dict = {'filename' : self.filename, 'displayed' : self.displayed,
            'quiet' : self.quiet, 'filterSQL': self.sql, 
            'linewidth':self.linewidth,}
        # the values out of getColorAsRGBATuple are numpy.uint8's
        # which confuses json. Convert to ints
        dict['color'] = [int(x) for x in self.getColorAsRGBATuple()]

        if self.isResultSet:
            dict['origSQL'] = self.origSQL
        else:
            dict['layerName'] = self.ogrLayer.GetName()

        fileobj.write(json.dumps(dict) + '\n')

    def fromFile(self, fileobj, width, height):
        """
        Initialise this instance of the class with information from json in fileobj
        """
        line = fileobj.readline()
        dict = json.loads(line)
        filename = dict['filename']
        self.quiet = dict['quiet']
        self.displayed = dict['displayed']

        ds = ogr.Open(filename)

        if 'origSQL' in dict:
            # result of a query
            origSQL = dict['origSQL']
            lyr = ds.ExecuteSQL(origSQL)
            isResultSet = True
        else:
            # a normal layer
            lyr = ds.GetLayerByName(dict['layerName'])
            origSQL = None
            isResultSet = False

        colour = dict['color']

        self.open(ds, lyr, width, height, color=colour, resultSet=isResultSet,
                    origSQL=origSQL)

        sql = dict['filterSQL']
        if sql is not None:
            self.setSQL(sql)

        self.setLineWidth(dict['linewidth'])
        
    def setSQL(self, sql=None):
        "sets the sql attribute filter"
        self.sql = sql
        
    def getSQL(self):
        return self.sql
        
    def hasSQL(self):
        "returns True if there is an attribute filter in place"
        return self.sql is not None

    def setLineWidth(self, linewidth):
        "sets the line width"
        self.linewidth = linewidth

    def getLineWidth(self):
        return self.linewidth
        
    def getColorAsRGBATuple(self):
        rgba = []
        for code in viewerLUT.RGBA_CODES:
            lutindex = viewerLUT.CODE_TO_LUTINDEX[code]
            value = self.lut[1,lutindex]
            rgba.append(value)
        return tuple(rgba)

    def setColor(self, color):
        """
        Sets up the LUT to use the specified color
        """
        for value, code in zip(color, viewerLUT.RGBA_CODES):
            lutindex = viewerLUT.CODE_TO_LUTINDEX[code]
            self.lut[1,lutindex] = value

    def open(self, ogrDataSource, ogrLayer, width, height, extent=None,
                    color=DEFAULT_VECTOR_COLOR, resultSet=False, origSQL=None):
        """
        Use the supplied datasource and layer for accessing vector data
        keeps a reference to the datasource and layer
        If resultSet is True then ogrDataSource.ReleaseResultSet is called
        on destruction. If resultSet is True then origSQL should be passed so
        layer can be recreated if saved as json
        """
        self.filename = ogrDataSource.GetName()
        self.title = os.path.basename(self.filename)
        self.ogrDataSource = ogrDataSource
        self.ogrLayer = ogrLayer
        self.setColor(color)
        self.isResultSet = resultSet
        self.origSQL = origSQL

        self.coordmgr.setDisplaySize(width, height)
        bbox = ogrLayer.GetExtent()
        fullExtent = (bbox[0], bbox[3], bbox[1], bbox[2])
        self.coordmgr.setFullWorldExtent(fullExtent)

        if extent is None:
            # if not given, get full extent of layer
            extent = fullExtent

        self.coordmgr.setWorldExtent(extent)

    def updateColor(self, color):
        """
        Like setColor, but also updates the stored self.image
        to be in the new color
        """
        self.setColor(color)
        if self.image is not None:
            data = self.image.viewerdata
            bgra = self.lut[data]
            (ysize, xsize) = data.shape
            self.image = QImage(bgra.data, xsize, ysize, QImage.Format_ARGB32)
            self.image.viewerdata = data

    def getImage(self):
        """
        Updates self.image with the outlines of the
        vector in the current color
        """
        from . import vectorrasterizer
        extent = self.coordmgr.getWorldExtent()
        (xsize, ysize) = (self.coordmgr.dspWidth, self.coordmgr.dspHeight)

        # rasterizeOutlines burns in 1 for outline, 0 otherwise
        data = vectorrasterizer.rasterizeOutlines(self.ogrLayer, extent, 
                    xsize, ysize, self.linewidth, self.sql)

        # do our lookup
        bgra = self.lut[data]
        self.image = QImage(bgra.data, xsize, ysize, QImage.Format_ARGB32)
        self.image.viewerdata = data

    def getAttributesAtPoint(self, easting, northing, tolerance=0):
        """
        Returns a list of attributes for the point centred on 
        (easting, northing). If tolerance is specified a box will 
        will be drawn centred at (easting, northing) and size tolerance.
        Each item in the list contains a dictionary keyed on the attribute
        name and the value will be the attribute value as a string.
        """
        # set the spatial filter
        halftolerance = tolerance / 2
        self.ogrLayer.SetSpatialFilterRect(easting - halftolerance, 
            northing + halftolerance, easting + halftolerance, 
            northing - halftolerance)

        # get the field names
        feat_defn = self.ogrLayer.GetLayerDefn()
        fieldNames = []
        for field_idx in range(feat_defn.GetFieldCount()):
            field_defn = feat_defn.GetFieldDefn(field_idx)
            field_name = field_defn.GetName()
            fieldNames.append(field_name)

        # read through
        results = []
        self.ogrLayer.ResetReading()
        feat = self.ogrLayer.GetNextFeature()
        while feat is not None:

            thisresult = {}
            field_idx = 0
            for field_name in fieldNames:
                field_value = feat.GetFieldAsString(field_idx)
                thisresult[field_name] = field_value
                field_idx += 1

            results.append(thisresult)
            feat = self.ogrLayer.GetNextFeature()

        # reset 
        self.ogrLayer.SetSpatialFilter(None)

        return results

    def getPropertiesInfo(self):
        "Return the properties as a PropertyInfo we can show the user"
        from osgeo import ogr
        info = PropertyInfo()

        sr = self.ogrLayer.GetSpatialRef()
        info.setSR(sr)

        driverString = self.ogrDataSource.GetDriver().GetName()
        info.addFileInfo('Driver:', driverString)

        info.addFileInfo('Files:', self.filename)

        layerInfo = []
        geomTypes = {ogr.wkbUnknown:'Unknown', ogr.wkbPoint:'Point',
            ogr.wkbLineString:'Line String', ogr.wkbPolygon:'Polygon',
            ogr.wkbMultiPoint:'Multi Point', 
            ogr.wkbMultiLineString:'Multi Line String',
            ogr.wkbMultiPolygon:'Polygon', 
            ogr.wkbGeometryCollection:'Geometry Collection'}
        geomCode = self.ogrLayer.GetGeomType()
        geomType = geomTypes[geomCode]
        layerInfo.append(('Layer Type:', geomType))

        layerName = self.ogrLayer.GetName()
        info.addBandInfo(layerName, layerInfo)

        return info

class ViewerFeatureVectorLayer(ViewerVectorLayer):
    """
    A vector Feature layer. Same as ViewerVectorLayer but
    works with a single feature provided by the driving program.
    """
    def __init__(self):
        ViewerVectorLayer.__init__(self)
        self.ogrFeature = None

    def setFeature(self, ogrFeature):
        "Update feature to draw"
        self.ogrFeature = ogrFeature

    def toFile(self, fileobj):
        """
        This doesn't make sense since the ogrDataSource etc
        is owned by the driving program so we can't recreate it
        """
        raise NotImplementedError()

    def open(self, ogrDataSource, ogrLayer, ogrFeature, width, height, 
                    extent=None, color=DEFAULT_VECTOR_COLOR):
        "Set Data source, plus first feature to rasterize"
        ViewerVectorLayer.open(self, ogrDataSource, ogrLayer, width, height, 
                                extent, color)
        self.ogrFeature = ogrFeature

    def getImage(self):
        """
        Updates self.image with the outlines of the
        vector feature in the current color
        """
        from . import vectorrasterizer
        extent = self.coordmgr.getWorldExtent()
        (xsize, ysize) = (self.coordmgr.dspWidth, self.coordmgr.dspHeight)

        # rasterizeOutlinesFeature burns in 1 for outline, 0 otherwise
        data = vectorrasterizer.rasterizeOutlinesFeature(self.ogrFeature, extent, 
                    xsize, ysize, self.linewidth)

        # do our lookup
        bgra = self.lut[data]
        self.image = QImage(bgra.data, xsize, ysize, QImage.Format_ARGB32)
        self.image.viewerdata = data

    def setSQL(self, sql=None):
        "unlike the base class we don't support SQL"
        msg = "ViewerFeatureVectorLayer doesn't support SQL"
        raise NotImplementedError(msg)
        
    def getSQL(self):
        msg = "ViewerFeatureVectorLayer doesn't support SQL"
        raise NotImplementedError(msg)
        
    def hasSQL(self):
        msg = "ViewerFeatureVectorLayer doesn't support SQL"
        raise NotImplementedError(msg)
        

class LayerManager(QObject):
    """
    Class that manages a list of layers
    """
    def __init__(self):
        QObject.__init__(self)
        self.layers = []
        self.fullextent = None
        self.queryPointLayer = ViewerQueryPointLayer()
        self.topLayer = None

        if NUM_GETIMAGE_THREADS > 1:
            # thread of the jobs
            self.queue = queue.Queue()
            # start the threads
            for i in range(NUM_GETIMAGE_THREADS):
                t = threading.Thread(target=_callGetImage,
                                            args=(self.queue, ))
                t.daemon = True # so program exits even when threads running
                t.start()
        else:
            self.queue = None

    def updateTopFilename(self):
        """
        Call this when the top displayed layer may 
        have changed and the correct signal will be emitted
        """
        newTopLayer = None
        for layer in self.layers:
            if layer.displayed and not layer.quiet:
                newTopLayer = layer
                # don't break since we want the last layer
                # - top one is displayed

        if not newTopLayer is self.topLayer:
            self.topLayer = newTopLayer
            self.emit(SIGNAL("topLayerChanged(PyQt_PyObject)"), self.topLayer)

    def getFullExtent(self):
        """
        Return the full extent for all the open layers
        """
        return self.fullextent

    def recalcFullExtent(self):
        """
        Internal method. Recalculates the full extent of all
        the layers. Called when dataset added or removed.
        """
        self.fullextent = None
        for layer in self.layers:
            extent = layer.coordmgr.getFullWorldExtent()
            if extent is not None:
                if self.fullextent is None:
                    self.fullextent = extent
                else:
                    (left, top, right, bottom) = self.fullextent
                    (newleft, newtop, newright, newbottom) = extent
                    if newleft < left:
                        left = newleft
                    if newtop > top:
                        top = newtop
                    if newright > right:
                        right = newright
                    if newbottom < bottom:
                        bottom = newbottom
                    self.fullextent = (left, top, right, bottom)

    def setDisplaySize(self, width, height):
        """
        When window resized this updates all the layers
        """
        for layer in self.layers:
            layer.coordmgr.setDisplaySize(width, height)
            layer.coordmgr.recalcBottomRight()
        self.queryPointLayer.coordmgr.setDisplaySize(width, height)
        self.updateImages()

    @staticmethod
    def isSameRasterProjection(layer1, layer2):
        """
        Checks to see if 2 raster layers have the same projection
        """
        proj1 = layer1.gdalDataset.GetProjection()
        proj2 = layer2.gdalDataset.GetProjection()
        sr1 = osr.SpatialReference(proj1)
        sr2 = osr.SpatialReference(proj2)
        return bool(sr1.IsSame(sr2))

    def addRasterLayer(self, gdalDataset, width, height, stretch, lut=None,
                        ignoreProjectionMismatch=False, quiet=False):
        """
        Add a new raster layer with given display width and height, stretch
        and optional lut.
        """
        # create and open
        layer = ViewerRasterLayer(self)
        layer.quiet = quiet
        layer.open(gdalDataset, width, height, stretch, lut)

        if len(self.layers) > 0:
            # get the existing extent
            extent = self.layers[-1].coordmgr.getWorldExtent()
            layer.coordmgr.setWorldExtent(extent)

        # if there is an existing raster layer, check we have an equivalent
        # projection. Perhaps we should do similar if there is a vector layer. 
        # Not sure.
        existinglayer = self.getTopRasterLayer()
        if existinglayer is not None:
            if (not ignoreProjectionMismatch and 
                    not self.isSameRasterProjection(layer, existinglayer)):
                raise viewererrors.ProjectionMismatch('projections do not match')
        
        # ensure the query points have the correct extent
        extent = layer.coordmgr.getWorldExtent()
        self.queryPointLayer.coordmgr.setWorldExtent(extent)

        layer.getImage()
        self.layers.append(layer)
        self.recalcFullExtent()
        self.emit(SIGNAL("layersChanged()"))
        self.updateTopFilename()

    def addVectorLayer(self, ogrDataSource, ogrLayer, width, height, 
                                color=DEFAULT_VECTOR_COLOR, resultSet=False,
                                origSQL=None, quiet=False):
        """
        Add a vector layer. See ViewerVectorLayer.open for more info on params
        """
        # copy the current extent, if available
        extent = None
        topLayer = self.getTopLayer()
        if topLayer is not None:
            extent = topLayer.coordmgr.getWorldExtent()

        layer = ViewerVectorLayer()
        layer.quiet = quiet
        layer.open(ogrDataSource, ogrLayer, width, height, extent, color, 
                                resultSet, origSQL)

        layer.getImage()
        self.layers.append(layer)

        self.recalcFullExtent()
        self.emit(SIGNAL("layersChanged()"))
        self.updateTopFilename()

    def addVectorFeatureLayer(self, ogrDataSource, ogrLayer, ogrFeature, 
                                width, height, color=DEFAULT_VECTOR_COLOR,
                                quiet=False):
        """
        Add a vector feature layer
        """
        extent = None
        topLayer = self.getTopLayer()
        if topLayer is not None:
            extent = topLayer.coordmgr.getWorldExtent()

        layer = ViewerFeatureVectorLayer()
        layer.quiet = quiet
        layer.open(ogrDataSource, ogrLayer, ogrFeature, width, 
                            height, extent, color)

        layer.getImage()
        self.layers.append(layer)

        self.recalcFullExtent()
        self.emit(SIGNAL("layersChanged()"))
        self.updateTopFilename()

    def removeTopLayer(self):
        """
        Removes the top layer
        """
        if len(self.layers) > 0:
            self.layers.pop()
            self.recalcFullExtent()
            self.emit(SIGNAL("layersChanged()"))
        self.updateTopFilename()

    def removeLayer(self, layer):
        """
        Remove the specified layer
        """
        self.layers.remove(layer)
        self.recalcFullExtent()
        self.emit(SIGNAL("layersChanged()"))
        self.updateTopFilename()

    def moveLayerUp(self, layer):
        """
        Move the specified layer 'up' - ie
        render it later which is actually down the list
        """
        index = self.layers.index(layer)
        if index < len(self.layers) - 1:
            self.layers.pop(index)
            self.layers.insert(index + 1, layer)
            self.emit(SIGNAL("layersChanged()"))
        self.updateTopFilename()

    def moveLayerDown(self, layer):
        """
        Move the specified layer 'down' - ie
        render it later which is actually up the list
        """
        index = self.layers.index(layer)
        if index > 0:
            self.layers.pop(index)
            self.layers.insert(index - 1, layer)
            self.emit(SIGNAL("layersChanged()"))
        self.updateTopFilename()

    def moveLayerToTop(self, layer):
        """
        Move layer to the end of the list so it is
        rendererd last.
        """
        index = self.layers.index(layer)
        if index < len(self.layers) - 1:
            self.layers.pop(index)
            self.layers.append(layer)
            self.emit(SIGNAL("layersChanged()"))
        self.updateTopFilename()

    def setDisplayedState(self, layer, state):
        """
        Sets the displayed state for a layer
        use this rather than setting layer.displayed
        directly as title bar will be updated this way
        """
        layer.displayed = state
        self.updateTopFilename()
        self.emit(SIGNAL("layersChanged()"))

    def timeseriesForward(self):
        """
        Assume images are a stacked timeseries oldest
        to newest. Turn off the current topmost displayed
        """
        for layer in reversed(self.layers):
            if layer.displayed:
                self.setDisplayedState(layer, False)
                self.emit(SIGNAL("layersChanged()"))
                break

    def timeseriesBackward(self):
        """
        Assume images are a stacked timeseries oldest
        to newest. Turn on the previous one to the current
        topmost displayed
        """
        prevLayer = None
        for layer in reversed(self.layers):
            if layer.displayed:
                break
            prevLayer = layer
        if prevLayer is not None:
            self.setDisplayedState(prevLayer, True)
            self.emit(SIGNAL("layersChanged()"))
                    
    def getTopLayer(self):
        "Returns the very top layer which may be raster or vector"
        layer = None
        if len(self.layers) > 0:
            layer = self.layers[-1]
        return layer

    def getTopRasterLayer(self):
        """
        Returns the top most raster layer
        (if there is one) otherwise None
        """
        rasterLayer = None
        for layer in reversed(self.layers):
            if isinstance(layer, ViewerRasterLayer):
                rasterLayer = layer
                break
        return rasterLayer

    def getTopDisplayedRasterLayer(self):
        """
        Returns the top most raster layer
        (if there is one) otherwise None
        """
        rasterLayer = None
        for layer in reversed(self.layers):
            if isinstance(layer, ViewerRasterLayer) and layer.displayed:
                rasterLayer = layer
                break
        return rasterLayer
        
    def setStretchAllLayers(self, stretch, local=False):
        """
        Sets the stretch for all layers contained
        by the LayerManager.
        """
        for layer in self.layers:
            if isinstance(layer, ViewerRasterLayer):
               layer.setNewStretch(local=local, newstretch=stretch)

    def getTopVectorLayer(self):
        """
        Returns the top most vector layer
        (if there is one) otherwise None
        """
        vectorLayer = None
        for layer in reversed(self.layers):
            if isinstance(layer, ViewerVectorLayer):
                vectorLayer = layer
                break
        return vectorLayer

    def getTopDisplayedVectorLayer(self):
        """
        Returns the top most vector layer
        (if there is one) otherwise None
        """
        vectorLayer = None
        for layer in reversed(self.layers):
            if isinstance(layer, ViewerVectorLayer) and layer.displayed:
                vectorLayer = layer
                break
        return vectorLayer

    def updateImages(self):
        """
        Tell each of the layers to get a new
        'image' for rendering. This is called
        when extents have changed etc.
        """
        if NUM_GETIMAGE_THREADS <= 1:
            # do it the old single thread way
            for layer in self.layers:
                layer.getImage()
        else:
            # put all the layer getImage requests in the Queue
            for layer in self.layers:
                self.queue.put(layer)
            self.queue.join()    # block until all tasks are completed

        self.queryPointLayer.getImage()

    def makeLayersConsistent(self, reflayer):
        """
        Make all layers spatially consistent with reflayer
        """
        extent = reflayer.coordmgr.getWorldExtent()        

        for layer in self.layers:
            if not reflayer is layer:
                layer.coordmgr.setWorldExtent(extent)
        self.queryPointLayer.coordmgr.setWorldExtent(extent)

    def zoomNativeResolution(self):
        """
        Zoom to the native resolution of the top
        raster later
        """
        layer = self.getTopRasterLayer()
        if layer is not None:
            # take care to preserve the center
            (wldX, wldY) = layer.coordmgr.getWorldCenter()
            layer.coordmgr.setZoomFactor(1.0)
            layer.coordmgr.setWorldCenter(wldX, wldY)
            self.makeLayersConsistent(layer)
            self.updateImages()

    def zoomFullExtent(self):
        """
        Zoom to the full extent of all the layers
        This might need a re-think for vectors.
        """
        layer = self.getTopRasterLayer()
        if layer is not None and self.fullextent is not None:
            layer.coordmgr.setWorldExtent(self.fullextent)
            self.makeLayersConsistent(layer)
            self.updateImages()

    def toFile(self, fileobj):
        """
        Save all the layers and info needed to re-create them 
        to the fileobj as JSON.
        """
        for layer in self.layers:
            try:
                layer.toFile(fileobj)
            except NotImplementedError:
                # ignore for now
                pass

    def fromFile(self, fileobj, nlayers, width, height):
        """
        Tries to read the json out of fileobj and reconstruct
        all the layers
        """
        for n in range(nlayers):
            line = fileobj.readline()
            dict = json.loads(line)
            # find the type of the layer
            ltype = dict['type']
            if ltype == 'raster':
                layer = ViewerRasterLayer(self)
                layer.fromFile(fileobj, width, height)
        
                if len(self.layers) > 0:
                    # get the existing extent
                    extent = self.layers[-1].coordmgr.getWorldExtent()
                    layer.coordmgr.setWorldExtent(extent)

                # don't do projection check, but maybe should?
        
                # ensure the query points have the correct extent
                extent = layer.coordmgr.getWorldExtent()
                self.queryPointLayer.coordmgr.setWorldExtent(extent)

                layer.getImage()
                self.layers.append(layer)
                self.recalcFullExtent()
            elif ltype == 'vector':

                layer = ViewerVectorLayer()
                layer.fromFile(fileobj, width, height)

                layer.getImage()
                self.layers.append(layer)

                self.recalcFullExtent()
            else:
                raise ValueError('unsupported layer type')

        self.emit(SIGNAL("layersChanged()"))
        self.updateTopFilename()


    # the following functions are needed as this class
    # acts as a 'proxy' between the RAT and LUT's inside
    # the individual layers and anything wanting to listen
    # to the progress (the window in this case)
    def newProgress(self, string):
        """
        Called when we are about to start a new progress
        """
        self.emit(SIGNAL("newProgress(QString)"), string)

    def endProgress(self):
        """
        Called when a progress run has finished
        """
        self.emit(SIGNAL("endProgress()"))

    def newPercent(self, percent):
        """
        New progress value
        """
        self.emit(SIGNAL("newPercent(int)"), percent)


def replicateArray(arr, outarr, dspLeftExtra, dspTopExtra, dspRightExtra, 
                            dspBottomExtra):
    """
    Replicate the data in the given 2-d array so that it increases
    in size to be (ysize, xsize). 
    
    Replicates each pixel in both directions. 
    
    dspLeftExtra, dspTopExtra are the number of pixels to be shaved off the
    top and left. dspRightExtra, dspBottomExtra are the number of pixels
    to be shaved off the bottom and right of the result. This allows us
    to display fractional pixels.
    """
    (ysize, xsize) = outarr.shape
    (nrows, ncols) = arr.shape
    nRptsX = float(xsize + dspLeftExtra + dspRightExtra) / float(ncols)
    nRptsY = float(ysize + dspTopExtra + dspBottomExtra) / float(nrows)

    rowCount = int(numpy.ceil(nrows * nRptsY))
    colCount = int(numpy.ceil(ncols * nRptsX))
    
    # create the lookup table (up to nrows/ncols-1)
    # using the complex number stuff in numpy.mgrid
    # doesn't work too well since you end up with unevenly
    # spaced divisions...
    row, col = numpy.mgrid[dspTopExtra:rowCount-dspBottomExtra, 
                        dspLeftExtra:colCount-dspRightExtra]
    # try to be a little frugal with memory
    numpy.multiply(row, nrows / float(rowCount), out=row)
    numpy.multiply(col, ncols / float(colCount), out=col)
    # need to index with ints
    row = row.astype(numpy.int32)
    col = col.astype(numpy.int32)

    # do the lookup
    outarr = arr[row, col]

    # chop out the extra pixels (if any)
    outarr = outarr[0:ysize, 0:xsize]

    return outarr





