
"""
Module contains the ViewerApplication class
"""

import sys
import optparse
from PyQt4.QtGui import QApplication

from . import geolinkedviewers
from . import viewerstretch

def optionCallback(option, opt_str, value, parser):
    """
    Called as a callback from optparse so we can process
    the command line arguments and manipulate parser.stretch
    """
    if opt_str == '-c' or opt_str == '--colortable':
        parser.stretch.setColorTable()
        parser.modeSet = True
    elif opt_str == '-g' or opt_str == '--greyscale':
        parser.stretch.setGreyScale()
        parser.modeSet = True
    elif opt_str == '-r' or opt_str == '--rgb':
        parser.stretch.setRGB()
        parser.modeSet = True
    elif opt_str == '-n' or opt_str == '--nostretch':
        parser.stretch.setNoStretch()
        parser.stretchModeSet = True
    elif opt_str == '-l' or opt_str == '--linear':
        (minVal, maxVal) = value
        if minVal == 'stats':
            minVal = None
        else:
            minVal = float(minVal)

        if maxVal == 'stats':
            maxVal = None
        else:
            maxVal = float(maxVal)

        parser.stretch.setLinearStretch(minVal, maxVal)
        parser.stretchModeSet = True
    elif opt_str == '-s' or opt_str == '--stddev':
        parser.stretch.setStdDevStretch()
        parser.stretchModeSet = True
    elif opt_str == '--hist':
        parser.stretch.setHistStretch()
        parser.stretchModeSet = True
    elif opt_str == '-b' or opt_str == '--bands':
        bandlist = [int(x) for x in value.split(',')]
        parser.stretch.setBands(bandlist)
        parser.bandsSet = True
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
        self.parser.modeSet = False
        self.parser.stretchModeSet = False
        self.parser.bandsSet = False

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
                                            type="string", nargs=2, help="do a linear stretch between two values. Pass 'stats' for statistics")
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

        self.viewers = geolinkedviewers.GeolinkedViewers()

        cmdargs = CmdArgs()
        stretch = None
        if cmdargs.parser.modeSet and cmdargs.parser.stretchModeSet and cmdargs.parser.bandsSet:
            # use the stretch they have constructed
            stretch = cmdargs.parser.stretch
        elif cmdargs.parser.modeSet or cmdargs.parser.stretchModeSet or cmdargs.parser.bandsSet:
            msg = 'Stretch incomplete. Must specify one of [-c|-g|-r] and one of [-n|-l|-s|--hist] and -b, or none to use defaults.'
            raise SystemExit(msg)

        if len(cmdargs.args) == 0:
            self.viewers.newViewer()
        else:
            for filename in cmdargs.args:
                self.viewers.newViewer(filename, stretch)

