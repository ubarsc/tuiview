
class ViewerException(Exception):
    "Base class for all Viewer exceptions"

class InvalidDataset(ViewerException):
    "Dataset was invalid for some reason"

class InvalidParameters(ViewerException):
    "Invalid parameters passed to function"

class InvalidColorTable(ViewerException):
    "A color table was requested but does not exist"
