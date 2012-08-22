
"""
Contains the ViewerRAT class
"""

import keyword
import numpy
from osgeo import gdal
from PyQt4.QtCore import QObject, SIGNAL

from . import viewererrors

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

    def clear(self):
        """
        Removes attributes from this class
        """
        self.columnNames = None
        self.attributeData = None

    def readFromGDALBand(self, gdalband):
        """
        Reads attributes from a GDAL band
        Does nothing if no attrbute table
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

            # first get the column names
            # we do this so we can preserve the order
            # of the columns in the attribute table
            ncols = rat.GetColumnCount()
            nrows = rat.GetRowCount()
            percent_per_col = 100.0 / float(ncols)
            for col in range(ncols):
                colname = rat.GetNameOfCol(col)
                self.columnNames.append(colname)

                # get the attributes as a dictionary
                # keyed on column name and the values
                # being an array of attribute values
                # adapted from rios.rat
                dtype = rat.GetTypeOfCol(col)

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
                        val = rat.GetValueAsInt(row, col)
                        colArray[row] = val
                elif dtype == gdal.GFT_Real:
                    for row in range(nrows):
                        val = rat.GetValueAsDouble(row, col)
                        colArray[row] = val
                else:
                    for row in range(nrows):
                        val = rat.GetValueAsString(row, col)
                        colArray.append(val)

                if isinstance(colArray, list):
                    # convert to array - numpy can handle this now it 
                    # can work out the lengths
                    colArray = numpy.array(colArray)

                self.attributeData[colname] = colArray
                self.emit(SIGNAL("newPercent(int)"), col * percent_per_col)


        self.emit(SIGNAL("endProgress()"))


    def evaluateUserExpression(self, expression):
        """
        Evaluate a user expression. It is expected that a fragment
        of numpy code will be passed. numpy is provided in the global
        namespace.
        An exception is raised if code is invalid, or does not return
        an array of bools.
        """
        if not self.hasAttributes():
            msg = 'no attributes to work on'
            raise viewererrors.AttributeTableTypeError(msg)

        globaldict = {}
        # give them access to 'row' which is the row number
        globaldict['row'] = numpy.arange(self.getNumRows())
        # insert each column into the global namespace
        # as the array it represents
        for colName, saneName in (
                zip(self.columnNames, self.getSaneColumnNames())):
            # use sane names so as not to confuse Python
            globaldict[saneName] = self.attributeData[colName]

        # give them access to numpy
        globaldict['numpy'] = numpy

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


