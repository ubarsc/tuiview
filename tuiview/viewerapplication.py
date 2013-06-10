
"""
Module contains the ViewerApplication class
"""
# This file is part of 'TuiView' - a simple Raster viewer
# Copyright (C) 2012  Sam Gillingham
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

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
    elif opt_str == '--stretchfromtext':
        fileobj = open(value)
        s = fileobj.readline()
        fileobj.close()
        parser.stretch = viewerstretch.ViewerStretch.fromString(s)
        parser.stretch.setLUTFromText(value)
        parser.modeSet = True
        parser.stretchModeSet = True
        parser.bandsSet = True
    elif opt_str == '--stretchfromgdal':
        from osgeo import gdal
        ds = gdal.Open(value)
        parser.stretch = viewerstretch.ViewerStretch.readFromGDAL(ds)
        del ds
        parser.stretch.setLUTFromGDAL(value)
        parser.modeSet = True
        parser.stretchModeSet = True
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

        self.parser.add_option('-b', '--bands', action="callback", 
                            callback=optionCallback,
                            type="string", nargs=1,  
                            help="comma seperated list of bands to display")
        self.parser.add_option('-c', '--colortable', action="callback", 
                            callback=optionCallback,
                            help="Apply color table to image")
        self.parser.add_option('-g', '--greyscale', action="callback", 
                            callback=optionCallback,
                            help="Display image in greyscale")
        self.parser.add_option('-r', '--rgb', action="callback", 
                            callback=optionCallback,
                            help="use 3 bands to create RGB image")
        self.parser.add_option('-n', '--nostretch', action="callback", 
                            callback=optionCallback,
                            help="do no stretch on data")
        self.parser.add_option('-l', '--linear', action="callback", 
                            callback=optionCallback,
                            type="string", nargs=2, 
                            help="do a linear stretch between two values. " +
                                    "Pass 'stats' for statistics")
        self.parser.add_option('-s', '--stddev', action="callback", 
                            callback=optionCallback,
                            help="do a 2 standard deviation stretch")
        self.parser.add_option('--hist', action="callback", 
                            callback=optionCallback, 
                            help="do a histogram stretch")
        self.parser.add_option('--stretchfromtext', action="callback", 
                            callback=optionCallback, nargs=1, type="string", 
                        help="Load stretch and lookup table from text file")
        self.parser.add_option('--stretchfromgdal', action="callback", 
                            callback=optionCallback, nargs=1, type="string", 
                        help="Load stretch and lookup table from GDAL file" + 
                            " that contains saved stretch and lookup table")
        self.parser.add_option('--noplugins', action="store_false", 
                            default=True, dest='loadplugins', 
                            help="Don't load plugins")
        self.parser.add_option('--separate', action="store_true", 
                            default=False, dest='separate',
                            help="load multiple files into separate windows")
        self.parser.add_option('--goto', dest='goto', 
                            help="Zoom to a location. Format is:"+
                            " 'easting,northing,factor' where factor is meters"+
                            " per window pixel.")

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

        cmdargs = CmdArgs()

        loadplugins = cmdargs.loadplugins
        self.viewers = geolinkedviewers.GeolinkedViewers(loadplugins)

        stretch = None
        if (cmdargs.parser.modeSet and cmdargs.parser.stretchModeSet 
                    and cmdargs.parser.bandsSet):
            # use the stretch they have constructed
            stretch = cmdargs.parser.stretch
        elif (cmdargs.parser.modeSet or cmdargs.parser.stretchModeSet 
                        or cmdargs.parser.bandsSet):
            msg = ('Stretch incomplete. Must specify one of [-c|-g|-r] and' + 
                ' one of [-n|-l|-s|--hist] and -b, or none to use defaults.')
            raise SystemExit(msg)

        if len(cmdargs.args) == 0:
            self.viewers.newViewer()
        else:
            if cmdargs.separate:
                # need to be in separate windows
                for filename in cmdargs.args:
                    self.viewers.newViewer(filename, stretch)
            else:
                # load into one viewer
                viewer = None
                for filename in cmdargs.args:
                    if viewer is None:
                        viewer = self.viewers.newViewer(filename, stretch)
                    else:
                        viewer.addRasterInternal(filename, stretch)

        # goto a location
        if cmdargs.goto is not None:
            from tuiview.viewerwidget import GeolinkInfo
            arr = cmdargs.goto.split(',')
            if len(arr) != 3:
                msg = "goto usage: 'easting,northing,factor'"
                raise SystemExit(msg)
            (easting, northing, metresperimgpix) = arr
            easting = float(easting)
            northing = float(northing)
            metresperimgpix = float(metresperimgpix)

            obj = GeolinkInfo(0, easting, northing, metresperimgpix)
            self.viewers.onMove(obj)                

