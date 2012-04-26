
class ViewerException(Exception):
    "Base class for all Viewer exceptions"

class InvalidDataset(ViewerException):
    "Dataset was invalid for some reason"
