
import sys
import optparse
from PyQt4.QtGui import QApplication

from . import viewerwindow
from . import viewerLUT

def optionCallback(option, opt_str, value, parser):
    if opt_str == '-c' or opt_str == '--colortable':
        parser.stretch.setColorTable()
    elif opt_str == '-g' or opt_str == '--greyscale':
        parser.stretch.setGreyScale()
    elif opt_str == '-r' or opt_str == '--rgb':
        parser.stretch.setRGB()
    elif opt_str == '-n' or opt_str == '--nostretch':
        parser.stretch.setNoStretch()
    elif opt_str == '-l' or opt_str == '--linear':
        parser.stretch.setLinearStretch()
    elif opt_str == '-s' or opt_str == '--stddev':
        parser.stretch.setStdDevStretch()
    elif opt_str == '--hist':
        parser.stretch.setHistStretch()
    else:
        raise ValueError("Unknown option %s" % opt_str)

class CmdArgs(object):
    def __init__(self):
        self.parser = optparse.OptionParser()
        self.parser.stretch = viewerLUT.ViewerStretch()


        self.parser.add_option('-f', '--filename', dest="filename", help="Image to display")
        self.parser.add_option('-b', '--bands', dest="bands", help="comma seperated list of bands to display")
        self.parser.add_option('-c', '--colortable', action="callback", callback=optionCallback,
                                            help="Apply color table to image")
        self.parser.add_option('-g', '--greyscale', action="callback", callback=optionCallback,
                                            help="Display image in greyscale")
        self.parser.add_option('-r', '--rgb', action="callback", callback=optionCallback,
                                            help="use 3 bands to create RGB image")
        self.parser.add_option('-n', '--nostretch', action="callback", callback=optionCallback,
                                            help="do no stretch on data")
        self.parser.add_option('-l', '--linear', action="callback", callback=optionCallback,
                                            help="do a linear stretch between min and max values")
        self.parser.add_option('-s', '--stddev', action="callback", callback=optionCallback,
                                            help="do a 2 standard deviation stretch")
        self.parser.add_option('--hist', action="callback", callback=optionCallback, 
                                            help="do a histogram stretch")

        (options, args) = self.parser.parse_args()
        self.__dict__.update(options.__dict__)

        if self.filename is None:
            print 'must specify filename'
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
        self.mainw.openFileInternal(cmdargs.filename, cmdargs.bandlist, cmdargs.parser.stretch)

