
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

import keyword
import numpy
import json
from osgeo import gdal
from PyQt4.QtCore import QObject, SIGNAL

from . import viewererrors

# use TurboGDAL/TurboRAT if available
HAVE_TURBORAT = True
try:
    from turbogdal import turborat
except ImportError:
    HAVE_TURBORAT = False

NEWCOL_INT = 0
NEWCOL_FLOAT = 1
NEWCOL_STRING = 2

DEFAULT_INT_FMT = "%d"
DEFAULT_FLOAT_FMT = "%.2f"
DEFAULT_STRING_FMT = "%s"

VIEWER_COLUMN_ORDER_METADATA_KEY = 'VIEWER_COLUMN_ORDER'
VIEWER_COLUMN_LOOKUP_METADATA_KEY = 'VIEWER_COLUMN_LOOKUP'

def formatException(code):
    """
    Formats an exception for display and returns string
    """
    import sys
    import traceback
  
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
    def __init__(self):
        QObject.__init__(self)
        self.clear()
        self.count = 0 # is incremented each time attributes read into class
                    # so querywindow can tell if it is new data or not

    def hasAttributes(self):
        """
        Returns True if there are actually attributes in this class
        """
        return self.columnNames is not None

    def getColumnNames(self):
        "return the column names"
        return self.columnNames

    def getSaneColumnNames(self):
        """
        Gets column names made sane. This means adding '_'
        to Python keywords and replacing spaces with '_' etc
        """
        sane = []
        for colName in self.columnNames:
            if keyword.iskeyword(colName):
                # append an underscore. 
                colName = colName + '_'
            elif colName.find(' ') != -1:
                colName = colName.replace(' ', '_')
            sane.append(colName)
        return sane

    def getAttribute(self, colName):
        "return the array of attributes for a given column name"
        return self.attributeData[colName]

    def setAttribute(self, colName, data):
        "replace the array of attributes for a given column name"
        self.attributeData[colName] = data

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
        if (self.columnNames is not None and self.attributeData is not None 
            and len(self.columnNames) > 0):
            # assume all same length
            firstCol = self.columnNames[0]
            return self.attributeData[firstCol].size
        else:
            return 0

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
        self.columnNames = None # list
        self.attributeData = None # dict
        self.columnTypes = None # dict
        self.columnUsages = None # dict
        self.columnFormats = None # dict
        self.lookupColName = None # string
        # list of columns in self.columnNames
        # that need to be written to (and possibly created)
        # into a a file.
        self.dirtyColumns = None

    def addColumn(self, colname, coltype):
        """
        Adds a new column with the specified name. Pass one of
        the NEWCOL constants as coltype.
        The new column is added to the 'dirty' list so it
        is written out when writeDirtyColumns() is called.
        """
        if self.columnNames is None:
            msg = 'No valid RAT for this file'
            raise viewererrors.InvalidDataset(msg)

        if colname in self.columnNames:
            msg = 'Already have a column called %s' % colname
            raise viewererrors.InvalidParameters(msg)

        self.columnNames.append(colname)
        self.dirtyColumns.append(colname)
        nrows = self.getNumRows()

        if coltype == NEWCOL_INT:
            col = numpy.zeros(nrows, numpy.int)
            self.columnTypes[colname] = gdal.GFT_Integer
            self.columnFormats[colname] = DEFAULT_INT_FMT
        elif coltype == NEWCOL_FLOAT:
            col = numpy.zeros(nrows, numpy.float)
            self.columnTypes[colname] = gdal.GFT_Real
            self.columnFormats[colname] = DEFAULT_FLOAT_FMT
        elif coltype == NEWCOL_STRING:
            # assume the strings aren't any bigger than 10 chars for now
            stringtype = numpy.dtype('S10')
            col =  numpy.zeros(nrows, dtype=stringtype)
            self.columnTypes[colname] = gdal.GFT_String
            self.columnFormats[colname] = DEFAULT_STRING_FMT
        else:
            msg = 'invalid column type'
            raise viewererrors.InvalidParameters(msg)

        # new cols always this type
        self.columnUsages[colname] = gdal.GFU_Generic 
        
        self.attributeData[colname] = col

    def updateColumn(self, colname, selection, values):
        """
        Update the specified column. selection is a boolean array that
        specifies which rows are to be updated, values are taken
        from values where this is True.
        The column is added to the list of columns that are
        written out when writeDirtyColumns() is called.
        """
        if colname not in self.columnNames:
            msg = "Don't have a column named %s" % colname
            raise viewererrors.InvalidParameters(msg)

        # get the existing values
        oldvalues = self.attributeData[colname]

        # make sure we do something sensible with type
        # hopefully I have this right
        coltype = self.columnTypes[colname]
        try:
            if coltype == gdal.GFT_Integer:
                if numpy.isscalar(values):
                    values = int(values)
                else:
                    values = values.astype(numpy.integer)
            elif coltype == gdal.GFT_Real:
                if numpy.isscalar(values):
                    values = float(values)
                else:
                    values = values.astype(numpy.float)
            else:
                if numpy.isscalar(values):
                    values = str(values)
                    # there is a slight probo here
                    # where doesn't resize the string
                    # arrays automatically so we manually
                    # convert oldvalues to a large enough array
                    # for values
                    lenvalues = len(values)
                    if lenvalues > oldvalues.itemsize:
                        vdtype = numpy.dtype('S%d' % lenvalues)
                        oldvalues = oldvalues.astype(vdtype)
                else:
                    # this converts to a string array
                    # of the right dtype to handle values
                    values = numpy.array(values, dtype=str)
        except ValueError as e:
            msg = str(e)
            raise viewererrors.UserExpressionTypeError(msg)

        # do the masking
        # it is assumed this will do the right thing when 
        # string lengths are different
        newvalues = numpy.where(selection, values, oldvalues)

        # set the new values as our data
        self.attributeData[colname] = newvalues

        # add to list of 'dirty' columns
        if colname not in self.dirtyColumns:
            self.dirtyColumns.append(colname)

    def writeDirtyColumns(self, gdalband):
        """
        Writes out the columns that are marked as 'dirty'
        to the specified gdalband. It is assumed this has been
        opened with GA_Update.
        The list of dirty columns gets reset.
        """
        ncols = len(self.dirtyColumns)
        if ncols > 0:
            self.emit(SIGNAL("newProgress(QString)"), "Writing Attributes...")

            nrows = self.getNumRows()

            # things get a bit weird here as we need different
            # behaviour depending on whether we have an RFC40
            # RAT or not.
            if hasattr(gdal.RasterAttributeTable, "WriteArray"):
                # new behaviour
                rat = gdalband.GetDefaultRAT()
                isFileRAT = True

                # but if it doesn't support dynamic writing
                # we still ahve to call SetDefaultRAT
                if not rat.ChangesAreWrittenToFile():
                    isFileRAT = False

            else:
                # old behaviour
                rat = gdal.RasterAttributeTable()
                isFileRAT = False

            col = rat.GetColumnCount()
            percent_per_col = 100.0 / float(ncols)

            for colname in self.dirtyColumns:
                colData = self.attributeData[colname]
                dtype = self.columnTypes[colname]
                usage = self.columnUsages[colname]
                # preserve usage
                rat.CreateColumn(str(colname), dtype, usage)

                if hasattr(rat, "WriteArray"):
                    # if GDAL > 1.10 has these functions
                    # thanks to RFC40
                    rat.SetRowCount(colData.size)
                    rat.WriteArray(colData, col)

                elif HAVE_TURBORAT:
                    # do it fast way without RFC40
                    turborat.writeColumn(rat, col, colData, colData.size)
                else:
                    # do it slow way checking the type
                    if dtype == gdal.GFT_Integer:
                        for row in range(nrows):
                            val = colData[row]
                            # convert from numpy int to python int
                            val = rat.SetValueAsInt(row, col, int(val))
                    elif dtype == gdal.GFT_Real:
                        for row in range(nrows):
                            val = colData[row]
                            val = rat.SetValueAsDouble(row, col, val)
                    else:
                        for row in range(nrows):
                            val = colData[row]
                            val = rat.SetValueAsString(row, col, val)

                col += 1
                self.emit(SIGNAL("newPercent(int)"), col * percent_per_col)

            if not isFileRAT:
                # assume that existing cols re-written
                # and new cols created in output file.
                # this is correct for HFA and KEA AKAIK
                gdalband.SetDefaultRAT(rat)

            self.dirtyColumns = []
            self.emit(SIGNAL("endProgress()"))

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
        # use RFC40 function if available
        if hasattr(rat, "ReadAsArray"):
            return rat.ReadAsArray(colIndex)

        # use turborat if available
        if HAVE_TURBORAT:
            return turborat.readColumn(rat, colIndex)

        nrows = rat.GetRowCount()
        dtype = rat.GetTypeOfCol(colIndex)
        if dtype == gdal.GFT_Integer:
            colArray = numpy.zeros(nrows, int)
        elif dtype == gdal.GFT_Real:
            colArray = numpy.zeros(nrows, float)
        elif dtype == gdal.GFT_String:
            # for string attributes, create a list
            # convert to array later - don't know the length 
            # of strings yet
            colArray = []
        else:
            msg = "Can't interpret data type of attribute"
            raise viewererrors.AttributeTableTypeError(msg)

        # do it checking the type
        if dtype == gdal.GFT_Integer:
            for row in range(nrows):
                val = rat.GetValueAsInt(row, colIndex)
                colArray[row] = val
        elif dtype == gdal.GFT_Real:
            for row in range(nrows):
                val = rat.GetValueAsDouble(row, colIndex)
                colArray[row] = val
        else:
            for row in range(nrows):
                val = rat.GetValueAsString(row, colIndex)
                colArray.append(val)

        if isinstance(colArray, list):
            # convert to array - numpy can handle this now it 
            # can work out the lengths
            colArray = numpy.array(colArray)
        return colArray

    def readFromGDALBand(self, gdalband, gdaldataset):
        """
        Reads attributes from a GDAL band
        Does nothing if no attribute table
        or file not marked as thematic.
        """
        # reset vars
        self.clear()
        
        # have rat and thematic?
        self.emit(SIGNAL("newProgress(QString)"), "Reading Attributes...")
        rat = gdalband.GetDefaultRAT()
        thematic = gdalband.GetMetadataItem('LAYER_TYPE') == 'thematic'
        if rat is not None and thematic:
            # looks like we have attributes
            self.count += 1
            self.columnNames = []
            self.attributeData = {}
            self.columnTypes = {}
            self.columnUsages = {}
            self.columnFormats = {}
            self.dirtyColumns = []

            # first get the column names
            # we do this so we can preserve the order
            # of the columns in the attribute table
            ncols = rat.GetColumnCount()
            percent_per_col = 100.0 / float(ncols)
            for col in range(ncols):
                colname = rat.GetNameOfCol(col)
                self.columnNames.append(colname)

                # get the attributes as a dictionary
                # keyed on column name and the values
                # being an array of attribute values
                # adapted from rios.rat
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

                # read the column
                colArray = self.readColumnIndex(rat, col)

                self.attributeData[colname] = colArray
                self.emit(SIGNAL("newPercent(int)"), col * percent_per_col)

            # read in a preferred column order (if any)
            prefColOrder, lookup = self.readColumnOrderFromGDAL(gdaldataset)
            if len(prefColOrder) > 0:
                # rearrange our columns given this
                self.arrangeColumnOrder(prefColOrder)

            # remember the lookup column if set (None if not)
            self.lookupColName = lookup

        self.emit(SIGNAL("endProgress()"))

    def arrangeColumnOrder(self, prefColOrder):
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
        
    def getUserExpressionGlobals(self, isselected, queryRow, lastselected=None):
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
        for colName, saneName in (
                zip(self.columnNames, self.getSaneColumnNames())):
            # use sane names so as not to confuse Python
            globaldict[saneName] = self.attributeData[colName]

        # give them access to numpy
        globaldict['numpy'] = numpy
        return globaldict

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
        globaldict = self.getUserExpressionGlobals(isselected, queryRow,
                                                    lastselected)

        try:
            result = eval(expression, globaldict)
        except Exception:
            msg = formatException(expression)
            raise viewererrors.UserExpressionSyntaxError(msg)

        # check type of result
        if not isinstance(result, numpy.ndarray):
            msg = 'must return a numpy array'
            raise viewererrors.UserExpressionTypeError(msg)

        if result.dtype.kind != 'b':
            msg = 'must return a boolean array'
            raise viewererrors.UserExpressionTypeError(msg)

        return result

    def evaluateUserEditExpression(self, expression, isselected, queryRow):
        """
        Evaluate a user expression for editing. 
        Returns a vector or scalar - no checking on result
        is hoped it will work with where() in self.updateColumn
        It is expected that a fragment
        of numpy code will be passed. numpy is provided in the global
        namespace.
        An exception is raised if code is invalid, or does not return
        an array of bools.
        """
        globaldict = self.getUserExpressionGlobals(isselected, queryRow)

        try:
            result = eval(expression, globaldict)
        except Exception:
            msg = formatException(expression)
            raise viewererrors.UserExpressionSyntaxError(msg)

        return result

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
