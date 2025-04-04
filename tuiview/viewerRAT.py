
"""
Contains the ViewerRAT class
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
import traceback
import json
import keyword
import numpy
from osgeo import gdal
from PySide6.QtCore import QObject, Signal

from . import viewererrors

NEWCOL_INT = 0
NEWCOL_FLOAT = 1
NEWCOL_STRING = 2

DEFAULT_INT_FMT = "%d"
DEFAULT_FLOAT_FMT = "%.2f"
DEFAULT_STRING_FMT = "%s"

VIEWER_COLUMN_ORDER_METADATA_KEY = 'VIEWER_COLUMN_ORDER'
VIEWER_COLUMN_LOOKUP_METADATA_KEY = 'VIEWER_COLUMN_LOOKUP'

DEFAULT_CACHE_SIZE = 500000

GDAL_COLTYPE_LOOKUP = {gdal.GFT_Integer: "Integer", 
        gdal.GFT_Real: "Floating point", gdal.GFT_String: "String"}
GDAL_COLUSAGE_LOOKUP = {gdal.GFU_Generic: "General purpose field",
        gdal.GFU_PixelCount: "Histogram pixel count",
        gdal.GFU_Name: "Class name", gdal.GFU_Min: "Class range minimum",
        gdal.GFU_Max: "Class range maximum", gdal.GFU_MinMax: "Class value",
        gdal.GFU_Red: "Red class color", gdal.GFU_Green: "Green class color",
        gdal.GFU_Blue: "Blue class color", gdal.GFU_Alpha: "Alpha",
        gdal.GFU_RedMin: "Color Range Red Minimum",
        gdal.GFU_GreenMin: "Color Range Green Minimum",
        gdal.GFU_BlueMin: "Color Range Blue Minimum",
        gdal.GFU_AlphaMin: "Color Range Alpha Minimum",
        gdal.GFU_RedMax: "Color Range Red Maximum",
        gdal.GFU_GreenMax: "Color Range Green Maximum",
        gdal.GFU_BlueMax: "Color Range Blue Maximum",
        gdal.GFU_AlphaMax: "Color Range Alpha Maximum"}


def formatException(code):
    """
    Formats an exception for display and returns string
    """
    # extract the current traceback and turn it into a list
    (ttype, value, tb) = sys.exc_info()
    stack = traceback.extract_tb(tb)
  
    # replace all instances of <string> with actual code
    fixedstack = []
    codearr = code.split('\n')
    for (filename, line, function, text) in stack:
        if filename == '<string>' and text is None:
            text = codearr[line - 1]
        fixedstack.append((filename, line, function, text))
  
    trace = '\n'.join(traceback.format_list(fixedstack))
  
    # if a SyntaxError the error won't be part of the trace
    if ttype.__name__ == 'SyntaxError' and value.offset is not None:
        # simulate the offset pointer
        offset = ' ' * value.offset + '^'
        value = str(value) + '\n' + value.text + offset
    
    # add on the actual exceptions
    trace = '%s\n%s: %s' % (trace, ttype.__name__, value)
    return trace


class ViewerRAT(QObject):
    """
    Represents an attribute table in memory. Has method
    to read from GDAL. Also will apply a user expression.
    """
    # signals
    newProgress = Signal('QString', name='newProgress')
    newPercent = Signal(int, name='newPercent')
    endProgress = Signal(name='endProgress')
    columnNames = None  # list
    columnTypes = None  # dict
    columnUsages = None  # dict
    columnFormats = None  # dict
    lookupColName = None  # string
    gdalRAT = None  # object
    redColumnIdx = None  # int
    greenColumnIdx = None  # int
    blueColumnIdx = None  # int
    alphaColumnIdx = None  # int
    hasRATColorTable = False
    hasOldStyleColorTable = False
    attributeData = None

    def __init__(self):
        QObject.__init__(self)
        self.clear()
        self.count = 0  # is incremented each time attributes read into class
        # so querywindow can tell if it is new data or not

    def hasAttributes(self):
        """
        Returns True if there are actually attributes in this class
        """
        return self.columnNames is not None

    def getColumnNames(self):
        "return the column names"
        return self.columnNames

    def getSaneColumnNames(self, colNameList=None):
        """
        Gets column names made sane. This means adding '_'
        to Python keywords and replacing spaces with '_' etc
        """
        sane = []
        if colNameList is None:
            colNameList = self.columnNames
        for colName in colNameList:
            if keyword.iskeyword(colName):
                # append an underscore. 
                colName = colName + '_'
            elif colName.find(' ') != -1:
                colName = colName.replace(' ', '_')

            if colName[0].isdigit():
                colName = '_' + colName
            sane.append(colName)
        return sane

    def getType(self, colName):
        "return the type for a given column name"
        return self.columnTypes[colName]

    def getUsage(self, colName):
        "return the usage for a given column name"
        return self.columnUsages[colName]

    def getFormat(self, colName):
        "return the preferred format string for a given column name"
        return self.columnFormats[colName]

    def setFormat(self, colName, fmt):
        "replace the format string for a given column name"
        self.columnFormats[colName] = fmt

    def getNumColumns(self):
        "get the number of columns"
        if self.columnNames is not None:
            return len(self.columnNames)
        else:
            return 0

    def getNumRows(self):
        "get the number of rows"
        if self.columnNames is not None and len(self.columnNames) > 0:
            return self.gdalRAT.GetRowCount()
        else:
            return 0

    def getCacheObject(self, chunkSize):
        """
        Creates a new cache object to cache chunks of the RAT
        """
        return RATCache(self.gdalRAT, chunkSize)

    def getEntireAttribute(self, colName):
        """
        Reads and entire column (in chunks) and returns a long array
        with all the data - for colour table use
        """
        colIdx = -1
        ncols = self.gdalRAT.GetColumnCount()
        for col in range(ncols):
            name = self.gdalRAT.GetNameOfCol(col)
            if name == colName:
                colIdx = col
                break

        if colIdx == -1:
            msg = 'unable to find column %s' % colName
            raise viewererrors.InvalidParameters(msg)

        return self.gdalRAT.ReadAsArray(colIdx)

    def getLookupColName(self):
        "Return column to be used to lookup color table"
        return self.lookupColName

    def setLookupColName(self, name):
        "Set column to be used to lookup color table"
        self.lookupColName = name

    def clear(self):
        """
        Removes attributes from this class
        """
        self.columnNames = None  # list
        self.columnTypes = None  # dict
        self.columnUsages = None  # dict
        self.columnFormats = None  # dict
        self.lookupColName = None  # string
        self.gdalRAT = None  # object

        self.redColumnIdx = None  # int
        self.greenColumnIdx = None  # int
        self.blueColumnIdx = None  # int
        self.alphaColumnIdx = None  # int
        self.hasRATColorTable = False
        self.hasOldStyleColorTable = False 

    def addColumn(self, colname, coltype):
        """
        Adds a new column with the specified name. Pass one of
        the NEWCOL constants as coltype.
        """
        if self.columnNames is None:
            msg = 'No valid RAT for this file'
            raise viewererrors.InvalidDataset(msg)

        if colname in self.columnNames:
            msg = 'Already have a column called %s' % colname
            raise viewererrors.InvalidParameters(msg)

        self.columnNames.append(colname)

        if coltype == NEWCOL_INT:
            self.columnTypes[colname] = gdal.GFT_Integer
            self.columnFormats[colname] = DEFAULT_INT_FMT
        elif coltype == NEWCOL_FLOAT:
            self.columnTypes[colname] = gdal.GFT_Real
            self.columnFormats[colname] = DEFAULT_FLOAT_FMT
        elif coltype == NEWCOL_STRING:
            self.columnTypes[colname] = gdal.GFT_String
            self.columnFormats[colname] = DEFAULT_STRING_FMT
        else:
            msg = 'invalid column type'
            raise viewererrors.InvalidParameters(msg)

        # new cols always this type
        self.columnUsages[colname] = gdal.GFU_Generic 

        self.gdalRAT.CreateColumn(colname, self.columnTypes[colname], 
                    self.columnUsages[colname])
        
    @staticmethod
    def readColumnName(rat, colName):
        """
        Same as readColumnIndex, but takes a name of
        column. Returns None if not found.
        """
        colArray = None
        ncols = rat.GetColumnCount()
        for col in range(ncols):
            if rat.GetNameOfCol(col) == colName:
                colArray = ViewerRAT.readColumnIndex(rat, col)
                break
        return colArray

    @staticmethod
    def readColumnIndex(rat, colIndex):
        """
        Read a column from the rat at index colIndex
        into a numpy array
        """
        return rat.ReadAsArray(colIndex)

    def readFromGDALBand(self, gdalband, gdaldataset):
        """
        Reads attributes from a GDAL band
        Does nothing if no attribute table
        or file not marked as thematic.
        """
        # reset vars
        self.clear()
        
        # have rat and thematic?
        self.newProgress.emit("Reading Attributes...")
        rat = gdalband.GetDefaultRAT()
        thematic = gdalband.GetMetadataItem('LAYER_TYPE') == 'thematic'
        if rat is not None and rat.GetRowCount() != 0 and thematic:
            # looks like we have attributes
            self.count += 1
            self.columnNames = []
            self.attributeData = {}
            self.columnTypes = {}
            self.columnUsages = {}
            self.columnFormats = {}
            self.gdalRAT = rat

            # first get the column names
            # we do this so we can preserve the order
            # of the columns in the attribute table
            ncols = rat.GetColumnCount()
            percent_per_col = 100.0 / float(ncols)
            for col in range(ncols):
                colname = rat.GetNameOfCol(col)
                self.columnNames.append(colname)

                dtype = rat.GetTypeOfCol(col)
                self.columnTypes[colname] = dtype
                usage = rat.GetUsageOfCol(col)
                self.columnUsages[colname] = usage

                # format depdendent on type
                if dtype == gdal.GFT_Integer:
                    self.columnFormats[colname] = DEFAULT_INT_FMT
                elif dtype == gdal.GFT_Real:
                    self.columnFormats[colname] = DEFAULT_FLOAT_FMT
                else:
                    self.columnFormats[colname] = DEFAULT_STRING_FMT

                self.newPercent.emit(col * percent_per_col)

            # read in a preferred column order (if any)
            prefColOrder, lookup = self.readColumnOrderFromGDAL(gdaldataset)
            if len(prefColOrder) > 0:
                # rearrange our columns given this
                self.arrangeColumnOrder(prefColOrder, gdalband)

            # see if there is a colour table
            self.findColorTableColumns(gdalband)

            # remember the lookup column if set (None if not)
            self.lookupColName = lookup

        self.endProgress.emit()

    def findColorTableColumns(self, gdalband):
        """
        Update the variables that define which are the columns
        in the colour table
        """
        col = 0
        for colname in self.columnNames:
            usage = self.columnUsages[colname]
            if usage == gdal.GFU_Red:
                self.redColumnIdx = col
            elif usage == gdal.GFU_Green:
                self.greenColumnIdx = col
            elif usage == gdal.GFU_Blue:
                self.blueColumnIdx = col
            elif usage == gdal.GFU_Alpha:
                self.alphaColumnIdx = col
            col += 1

        # if we have all the columns, we have a color table
        self.hasRATColorTable = (self.redColumnIdx is not None and 
                self.greenColumnIdx is not None and 
                self.blueColumnIdx is not None and
                self.alphaColumnIdx is not None)
                
        self.hasOldStyleColorTable = False
        if not self.hasRATColorTable:
            ct = gdalband.GetColorTable()
            self.hasOldStyleColorTable = ct is not None
            
    def arrangeColumnOrder(self, prefColOrder, gdalband):
        """
        rearrange self.columnNames given the preferred column
        order that is passed. Any columns not included
        in prefColOrder are tacked onto the end.
        Any columns in prefColOrder that don't exist are ignored.
        """
        newColOrder = []
        for pref in prefColOrder:
            if pref in self.columnNames:
                newColOrder.append(pref)
                self.columnNames.remove(pref)
        # ok all columns in prefColOrder should now have
        # been added to newColOrder. Add the remaining
        # values from  self.columnNames
        newColOrder.extend(self.columnNames)

        # finally clobber the old self.columnNames
        self.columnNames = newColOrder

        # this needs to be updated
        self.findColorTableColumns(gdalband)
        
    def getUserExpressionGlobals(self, cache, isselected, queryRow, 
                            lastselected=None, colNameList=None):
        """
        Get globals for user in user expression
        """
        if not self.hasAttributes():
            msg = 'no attributes to work on'
            raise viewererrors.AttributeTableTypeError(msg)

        globaldict = {}
        # give them access to 'row' which is the row number
        globaldict['row'] = numpy.arange(self.getNumRows())
        # access to 'queryrow' with is the currently queried row
        globaldict['queryrow'] = queryRow
        # give them access to 'isselected' which is the currently
        # selected rows so they can do subselections
        globaldict['isselected'] = isselected
        # lastselected
        if lastselected is not None:
            globaldict['lastselected'] = lastselected
        # insert each column into the global namespace
        # as the array it represents
        if colNameList is None:
            colNameList = self.columnNames
        for colName, saneName in (
                zip(colNameList, self.getSaneColumnNames(colNameList))):
            # use sane names so as not to confuse Python
            globaldict[saneName] = cache.cacheDict[colName]

        # give them access to numpy
        globaldict['numpy'] = numpy
        return globaldict

    @staticmethod
    def findVarNamesUsed(expression):
        """
        Work out what variable names are used in the given expression.
        The variable names are those apart from the special ones provided
        for in getUserExpressionGlobals(), and is intended to be just those
        which might be column names. Returns a list of the variable name
        strings.
        """
        # Just for safety, should never try any where near this many times
        MAX_TRIES = 10000

        numTries = 0
        ok = False
        # Initialize a name space with the special names
        varDict = {'row': 0, 'queryrow': 0, 'isselected': 0, 'lastselected': 0,
                'numpy': numpy}
        specialNames = list(varDict.keys())
        while (not ok and numTries < MAX_TRIES):
            try:
                eval(expression, varDict)
                ok = True
            except NameError as e:
                # Some name in the expression was not found. Find that name,
                # and add it to the dictionary
                msg = str(e)
                varName = msg.split()[1].replace("'", "")
                varDict[varName] = None
            except Exception:
                # Ignore all other exceptions. If we got this far, then we have
                # fixed all the NameError exceptions, and so have all the
                # required names
                ok = True

            numTries += 1

        # The eval() call has added __builtins__, so remove it again.
        # Also remove the special names we started with.
        varNamesUsed = [varName for varName in list(varDict.keys())
            if varName != "__builtins__" and varName not in specialNames]
        return varNamesUsed

    def evaluateUserSelectExpression(self, expression, isselected, queryRow, 
            lastselected):
        """
        Evaluate a user expression for selection. 
        It is expected that a fragment
        of numpy code will be passed. numpy is provided in the global
        namespace.
        An exception is raised if code is invalid, or does not return
        an array of bools.
        """
        self.newProgress.emit("Evaluating User Expression...")
        cache = self.getCacheObject(DEFAULT_CACHE_SIZE)
        nrows = self.getNumRows()
        columnsUsed = self.findVarNamesUsed(expression)

        # create the new selected array the full size of the rat
        # we will fill in each chunk as we go
        result = numpy.empty(nrows, dtype=bool)

        currRow = 0

        while currRow < nrows:
            cache.setStartRow(currRow, colName=columnsUsed)
            length = cache.getLength()

            isselectedSub = isselected[currRow:currRow + length]
            if lastselected is not None:
                lastselectedSub = lastselected[currRow:currRow + length]
            else:
                lastselectedSub = None
            globaldict = self.getUserExpressionGlobals(cache, isselectedSub, 
                                queryRow, lastselectedSub,
                                colNameList=columnsUsed)

            try:
                resultSub = eval(expression, globaldict)
            except Exception as exc:
                msg = formatException(expression)
                raise viewererrors.UserExpressionSyntaxError(msg) from exc

            # check type of result
            if not isinstance(resultSub, numpy.ndarray):
                msg = 'must return a numpy array'
                raise viewererrors.UserExpressionTypeError(msg)

            if resultSub.dtype.kind != 'b':
                msg = 'must return a boolean array'
                raise viewererrors.UserExpressionTypeError(msg)

            result[currRow:currRow + length] = resultSub
            currRow += DEFAULT_CACHE_SIZE
            self.newPercent.emit(int((currRow / nrows) * 100))

        self.endProgress.emit()
        return result

    def evaluateUserEditExpression(self, colName, expression, isselected, 
            queryRow):
        """
        Evaluate a user expression for editing and apply result to rat
        where isselected == True
        It is expected that a fragment
        of numpy code will be passed. numpy is provided in the global
        namespace.
        An exception is raised if code is invalid.
        """
        self.newProgress.emit("Evaluating User Expression...")
        cache = self.getCacheObject(DEFAULT_CACHE_SIZE)
        nrows = self.getNumRows()

        currRow = 0
        done = False
        isScalar = False  # user code returns a scalar - we 
        # can take shortcuts since not all the cols need to be read
        resultSub = None

        while currRow < nrows and not done:

            # guess the length
            isselectedSub = isselected[currRow:currRow + DEFAULT_CACHE_SIZE]
            if isselectedSub.any():

                if isScalar:
                    cache.setStartRow(currRow, colName)
                else:
                    cache.setStartRow(currRow)
                length = cache.getLength()

                # re do with correct length
                isselectedSub = isselected[currRow:currRow + length]
                globaldict = self.getUserExpressionGlobals(cache, isselectedSub, 
                                queryRow)

                if not isScalar:
                    # can re-use the first result if scalar
                    # all calls should be the same
                    try:
                        resultSub = eval(expression, globaldict)
                    except Exception as exc:
                        msg = formatException(expression)
                        raise viewererrors.UserExpressionSyntaxError(msg) from exc

                cache.updateColumn(colName, resultSub, isselected)

                if numpy.isscalar(resultSub):
                    isScalar = True

            currRow += DEFAULT_CACHE_SIZE
            self.newPercent.emit(int((currRow / nrows) * 100))

        self.endProgress.emit()

    def setColumnToConstant(self, colName, value, isselected):
        """
        Sets whole column to be a constant value (where isselected == True)
        for keyboard shortcuts etc
        """
        self.newProgress.emit("Evaluating User Expression...")
        cache = self.getCacheObject(DEFAULT_CACHE_SIZE)
        nrows = self.getNumRows()

        currRow = 0
        done = False

        while currRow < nrows and not done:
            # guess size
            isselectedSub = isselected[currRow:currRow + DEFAULT_CACHE_SIZE]
            if isselectedSub.any():
                cache.setStartRow(currRow, colName)

                cache.updateColumn(colName, value, isselected)

            currRow += DEFAULT_CACHE_SIZE
            self.newPercent.emit(int((currRow / nrows) * 100))

        self.endProgress.emit()

    def writeColumnOrderToGDAL(self, gdaldataset):
        """
        Given a GDAL dataset opened in update mode,
        writes the currently selected column order
        to the file (this can be changed by the querywindow)
        Ideally, this would be the band but writing metadata
        to the band causes problems with some Imagine files
        that have been opened in different versions of Imagine.
        Also writes the lookup column if there is one.
        """
        string = json.dumps(self.columnNames)
        gdaldataset.SetMetadataItem(VIEWER_COLUMN_ORDER_METADATA_KEY, string)
        if self.lookupColName is not None:
            name = str(self.lookupColName)
        else:
            # remove it
            name = ''
        gdaldataset.SetMetadataItem(VIEWER_COLUMN_LOOKUP_METADATA_KEY, name)
        
    @staticmethod
    def readColumnOrderFromGDAL(gdaldataset):
        """
        Reads the column order out of the gdaldataset.
        Returns empty list if none.
        Also returns the lookup column
        """
        string = gdaldataset.GetMetadataItem(VIEWER_COLUMN_ORDER_METADATA_KEY)
        if string is not None and string != '':
            columns = json.loads(string)
        else:
            columns = []
        string = gdaldataset.GetMetadataItem(VIEWER_COLUMN_LOOKUP_METADATA_KEY)
        name = None
        if string is not None and string != '':
            name = string
        return columns, name


class RATCache:
    """
    Class that caches a 'chunk' of the RAT
    """
    def __init__(self, gdalRAT, chunkSize):
        self.gdalRAT = gdalRAT
        self.chunkSize = chunkSize
        self.currStartRow = 0
        self.length = 0
        self.cacheDict = {}

    def getLength(self):
        "Return the length of the current RAT chunk"
        return self.length

    def columnAdded(self, colName):
        """
        Shortcut to be called when a new column added
        saves having to re-read all the data - just
        updates the cache with the new data
        """
        ncols = self.gdalRAT.GetColumnCount()
        for col in range(ncols):
            name = self.gdalRAT.GetNameOfCol(col)
            if name == colName:
                data = self.gdalRAT.ReadAsArray(col, self.currStartRow, self.length)
                self.cacheDict[name] = data
                break

    def updateCache(self, colName=None):
        """
        Internal method, called when self.currStartRow changed
        If colName is None all columns will be updated, if it is a single
        name or a list of names, then just the named one(s) will
        be update.
        """
        rowCount = self.gdalRAT.GetRowCount()
        self.length = self.chunkSize
        if (self.currStartRow + self.length) > rowCount:
            self.length = rowCount - self.currStartRow

        ncols = self.gdalRAT.GetColumnCount()
        for col in range(ncols):
            name = self.gdalRAT.GetNameOfCol(col)
            if colName is None or name == colName or name in colName:
                data = self.gdalRAT.ReadAsArray(col, int(self.currStartRow), 
                            self.length)

                # for some reason, with HFA this can return None
                # fake some zero data
                if data is None:
                    coltype = self.gdalRAT.GetTypeOfCol(col)
                    if coltype == gdal.GFT_Integer:
                        data = numpy.zeros(self.length, dtype=numpy.integer)
                    elif coltype == gdal.GFT_Real:
                        data = numpy.zeros(self.length, dtype=float)
                    else:
                        data = numpy.zeros(self.length, dtype='S10')

                    # write back to file
                    self.gdalRAT.WriteArray(data, col, int(self.currStartRow))

                self.cacheDict[name] = data

    def setStartRow(self, startRow, colName=None):
        """
        Call this to set the cache to contain the new data
        If colName is None all columns will be updated 
        otherwise just the named one
        """
        self.currStartRow = startRow
        self.updateCache(colName)

    def getValueFromCol(self, colName, row):
        """
        Return the actual value given name of col and 
        a row count based on the full rat
        """
        data = self.cacheDict[colName]
        return data[row - self.currStartRow]

    def autoScrollToIncludeRow(self, row):
        """
        For calling from GUI. Qt will ask for a given row
        but we don't want to re-read every time. Most requests will
        be around a location so we only update when we have to.
        """
        if row >= self.currStartRow and row < (self.currStartRow + 
                                self.chunkSize) and len(self.cacheDict) > 0:
            # no need - already have that data
            return

        newStartRow = int(row / self.chunkSize) * self.chunkSize
        self.setStartRow(newStartRow)
        
    def updateColumn(self, colName, data, selectionArray):
        """
        New data for a column. selectionArray is the size of the file's RAT.
        data is just the subset for this cache. 
        Updates only done where selectionArray == True (for the subset we are caching)
        updates cache and data in file
        """
        if not numpy.isscalar(data) and len(data) != self.length:
            msg = 'data wrong length'
            raise viewererrors.AttributeTableTypeError(msg)

        selectionArraySubset = selectionArray[
            self.currStartRow:self.currStartRow + self.length]

        if not selectionArraySubset.any():
            # nothing to be updated
            return

        # need to do some massaging based on coltype
        ncols = self.gdalRAT.GetColumnCount()
        coltype = gdal.GFT_Integer
        colIdx = -1
        for col in range(ncols):
            name = self.gdalRAT.GetNameOfCol(col)
            if name == colName:
                colIdx = col
                coltype = self.gdalRAT.GetTypeOfCol(col)
                break

        if colIdx == -1:
            msg = 'unable to find column %s' % colName
            raise viewererrors.AttributeTableTypeError(msg)

        if not selectionArraySubset.all():
            # some need to be updated
            # keep old where selectionArray == False
            olddata = self.cacheDict[colName] 

            try:
                if coltype == gdal.GFT_Integer:
                    if numpy.isscalar(data):
                        data = int(data)
                    else:
                        data = data.astype(numpy.integer)
                elif coltype == gdal.GFT_Real:
                    if numpy.isscalar(data):
                        data = float(data)
                    else:
                        data = data.astype(float)
                else:
                    if numpy.isscalar(data):
                        data = str(data)
                        # there is a slight probo here
                        # where doesn't resize the string
                        # arrays automatically so we manually
                        # convert olddata to a large enough array
                        # for data
                        lendata = len(data)
                        if lendata > olddata.itemsize:
                            vdtype = numpy.dtype('S%d' % lendata)
                            olddata = olddata.astype(vdtype)
                    else:
                        # this converts to a string array
                        # of the right dtype to handle data
                        data = numpy.array(data, dtype=str)
            except ValueError as e:
                msg = str(e)
                raise viewererrors.UserExpressionTypeError(msg)

            # do the masking
            # it is assumed this will do the right thing when 
            # string lengths are different
            data = numpy.where(selectionArraySubset, data, olddata)

        else:
            # all new data
            if numpy.isscalar(data):
                if coltype == gdal.GFT_Integer:
                    dataarr = numpy.empty(self.length, dtype=numpy.integer)
                    dataarr.fill(data)
                elif coltype == gdal.GFT_Real:
                    dataarr = numpy.empty(self.length, dtype=float)
                    dataarr.fill(data)
                else:
                    lendata = len(data)
                    vdtype = numpy.dtype('S%d' % lendata)
                    dataarr = numpy.empty(self.length, dtype=vdtype)
                    dataarr.fill(data)

                data = dataarr
            # else: already an array

        # update cache
        self.cacheDict[colName] = data
        # write back to file
        self.gdalRAT.WriteArray(data, colIdx, self.currStartRow)
