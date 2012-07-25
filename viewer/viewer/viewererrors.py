
class ViewerException(Exception):
    "Base class for all Viewer exceptions"

class InvalidDataset(ViewerException):
    "Dataset was invalid for some reason"

class InvalidParameters(ViewerException):
    "Invalid parameters passed to function"

class InvalidColorTable(ViewerException):
    "A color table was requested but does not exist"

class InvalidStretch(ViewerException):
    "The requested stretch is invalid"

class StatisticsError(ViewerException):
    "Unable to retrieve statistics"

class TypeConversionError(ViewerException):
    "Problem with the type of the dataset"

class AttributeTableTypeError(ViewerException):
    "Problem with the type of attribute"
