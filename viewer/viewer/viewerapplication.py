
import sys
from PyQt4.QtGui import QApplication

from . import viewerwindow

class ViewerApplication(QApplication):
    def __init__(self):
        QApplication.__init__(self, sys.argv)

        # for settings
        self.setApplicationName('viewer')
        self.setOrganizationName('Viewer')

        self.mainw = viewerwindow.ViewerWindow()
        self.mainw.show()
        if self.argc() > 1:
            # need to do this after show() otherwise
            # window size is wrong for some reason
            self.mainw.openFileInternal(self.argv()[1])

