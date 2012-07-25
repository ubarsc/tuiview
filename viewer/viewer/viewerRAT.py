
"""
Contains the ViewerRAT class
"""

import numpy
from osgeo import gdal

class ViewerRAT(object):
    def __init__(self):
        self.columnNames = None
        self.attributeData = None

    def hasAttributes(self):
        """
        Returns True if there are actually attributes in this class
        """
        return self.columnNames is not None

    def getColumnNames(self):
        return self.columnNames

    def getAttribute(self, colName):
        return self.attributeData[colName]

    def getNumColumns(self):
        if self.columnNames is not None:
            return len(self.columnNames)
        else:
            return 0

    def getNumRows(self):
        if self.columnNames is not None and self.attributeData is not None and len(self.columnNames) > 0:
            # assume all same length
            firstCol = self.columnNames[0]
            return self.attributeData[firstCol].size
        else:
            return 0

    def readFromGDALBand(self, gdalband):
        """
        Reads attributes from a GDAL band
        Does nothing if no attrbute table
        or file not marked as thematic.
        """
        # reset vars
        self.columnNames = None
        self.attributeData = None
        
        # have rat and thematic?
        rat = gdalband.GetDefaultRAT()
        thematic = gdalband.GetMetadataItem('LAYER_TYPE') == 'thematic'
        if rat is not None and thematic:
            # looks like we have attributes
            self.columnNames = []
            self.attributeData = {}

            # first get the column names
            # we do this so we can preserve the order
            # of the columns in the attribute table
            ncols = rat.GetColumnCount()
            nrows = rat.GetRowCount()
            for col in range(ncols):
                colname = rat.GetNameOfCol(col)
                self.columnNames.append(colname)

                # get the attributes as a dictionary
                # keyed on column name and the values
                # being an array of attribute values
                # adapted from rios.rat
                dtype = rat.GetTypeOfCol(col)

                if dtype == gdal.GFT_Integer:
                    colArray = numpy.zeros(nrows,int)
                elif dtype == gdal.GFT_Real:
                    colArray = numpy.zeros(nrows,float)
                elif dtype == gdal.GFT_String:
                    # for string attributes, create a list
                    # convert to array later - don't know the length of strings yet
                    colArray = []
                else:
                    msg = "Can't interpret data type of attribute"
                    raise viewererrors.AttributeTableTypeError(msg)

                for row in range(nrows):
                    # do it checking the type
                    if dtype == gdal.GFT_Integer:
                        val = rat.GetValueAsInt(row,col)
                        colArray[row] = val
                    elif dtype == gdal.GFT_Real:
                        val = rat.GetValueAsDouble(row,col)
                        colArray[row] = val
                    else:
                        val = rat.GetValueAsString(row,col)
                        colArray.append(val)

                if isinstance(colArray, list):
                    # convert to array - numpy can handle this now it can work out the lengths
                    colArray = numpy.array(colArray)

                self.attributeData[colname] = colArray

