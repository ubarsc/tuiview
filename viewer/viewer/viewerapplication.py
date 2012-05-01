
import sys
import optparse
from PyQt4.QtGui import QApplication

from . import viewerwindow

from .viewerwidget import VIEWER_MODE_COLORTABLE, VIEWER_MODE_GREYSCALE, VIEWER_MODE_RGB
from .viewerwidget import VIEWER_STRETCHMODE_NONE, VIEWER_STRETCHMODE_LINEAR, VIEWER_STRETCHMODE_2STDDEV, VIEWER_STRETCHMODE_HIST

class CmdArgs(object):
    def __init__(self):
        self.parser = optparse.OptionParser()
        self.parser.add_option('-f', '--filename', dest="filename", help="Image to display")
        self.parser.add_option('-b', '--bands', dest="bands", help="comma seperated list of bands to display")
        self.parser.add_option('-c', '--colortable', action="store_const", const=VIEWER_MODE_COLORTABLE, 
                dest="mode", default=0, help="Apply color table to image")
        self.parser.add_option('-g', '--greyscale', action="store_const", const=VIEWER_MODE_GREYSCALE, 
                dest="mode", default=0, help="Display image in greyscale")
        self.parser.add_option('-r', '--rgb', action="store_const", const=VIEWER_MODE_RGB, 
                dest="mode", default=0, help="use 3 bands to create RGB image")
        self.parser.add_option('-n', '--nostretch', action="store_const", const=VIEWER_STRETCHMODE_NONE, 
                dest="stretchmode", default=VIEWER_STRETCHMODE_NONE, help="do no stretch on data")
        self.parser.add_option('-l', '--linear', action="store_const", const=VIEWER_STRETCHMODE_LINEAR, 
                dest="stretchmode", default=VIEWER_STRETCHMODE_NONE, help="do a linear stretch between min and max values")
        self.parser.add_option('-s', '--stddev', action="store_const", const=VIEWER_STRETCHMODE_2STDDEV, 
                dest="stretchmode", default=VIEWER_STRETCHMODE_NONE, help="do a 2 standard deviation stretch")
        self.parser.add_option('--hist', action="store_const", const=VIEWER_STRETCHMODE_HIST, 
                dest="stretchmode", default=VIEWER_STRETCHMODE_NONE, help="do a histogram stretch")

        (options, args) = self.parser.parse_args()
        self.__dict__.update(options.__dict__)

        if self.filename is None:
            print 'must specify filename'
            self.parser.print_help()
            sys.exit()
        elif self.mode == 0:
            print 'must specify one of -c, -g or -r'
            self.parser.print_help()
            sys.exit()
        elif self.bands is None:
            print 'must specify bands to display'
            self.parser.print_help()
            sys.exit()

        self.bandlist = [int(x) for x in self.bands.split(',')]

class ViewerApplication(QApplication):
    def __init__(self):
        QApplication.__init__(self, sys.argv)

        # for settings
        self.setApplicationName('viewer')
        self.setOrganizationName('Viewer')

        self.mainw = viewerwindow.ViewerWindow()
        self.mainw.show()

        cmdargs = CmdArgs()

        # need to do this after show() otherwise
        # window size is wrong for some reason
        self.mainw.openFileInternal(cmdargs.filename, cmdargs.bandlist, cmdargs.mode, cmdargs.stretchmode)

