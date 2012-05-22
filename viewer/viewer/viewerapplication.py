
"""
Module contains the ViewerApplication class
"""

import sys
import optparse
from PyQt4.QtGui import QApplication

from . import viewerwindow
from . import viewerstretch

def optionCallback(option, opt_str, value, parser):
    """
    Called as a callback from optparse so we can process
    the command line arguments and manipulate parser.stretch
    """
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
    elif opt_str == '-b' or opt_str == '--bands':
        bandlist = [int(x) for x in value.split(',')]
        parser.stretch.setBands(bandlist)
    else:
        raise ValueError("Unknown option %s" % opt_str)

class CmdArgs(object):
    """
    Class for processing command line arguments
    """
    def __init__(self):
        usage = "usage: %prog [options] [filename]"
        self.parser = optparse.OptionParser(usage)
        self.parser.stretch = viewerstretch.ViewerStretch()

        self.parser.add_option('-b', '--bands', action="callback", callback=optionCallback,
                            type="string", nargs=1,  help="comma seperated list of bands to display")
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

        (options, self.args) = self.parser.parse_args()
        self.__dict__.update(options.__dict__)

class ViewerApplication(QApplication):
    """
    Main class for application
    """
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
        if len(cmdargs.args) != 0:
            filename = cmdargs.args[0] # maybe we should support multiple?
            stretch = None
            if cmdargs.parser.stretch.mode != viewerstretch.VIEWER_MODE_DEFAULT and \
                cmdargs.parser.stretch.stretchmode != viewerstretch.VIEWER_STRETCHMODE_DEFAULT and \
                cmdargs.parser.stretch.bands is not None:
                stretch = cmdargs.parser.stretch
            self.mainw.openFileInternal(filename, stretch)

