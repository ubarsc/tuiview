
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
import argparse
from PySide6.QtWidgets import QApplication, QMessageBox

from . import archivereader
from . import geolinkedviewers
from . import viewerstretch
from .viewerstrings import MESSAGE_TITLE
from .viewerwidget import GeolinkInfo
from .vectoropendialog import PROJ_YES, PROJ_NO

# True if we can't print to stderr etc
# (because we have been started in "GUI" mode on Windows)
GUI_MODE = sys.stderr is None


def showMessageAndExit(msg):
    """
    If in gui mode, show message box with error and exit with 1
    Otherwise raise SystemExit with msg
    """
    if GUI_MODE:
        QMessageBox.critical(None, MESSAGE_TITLE, msg)
        sys.exit(1)
    else:
        raise SystemExit(msg)

        
class TuiViewArgumentParser(argparse.ArgumentParser):
    """
    Same as argparse.ArgumentParser but overrides exit() and error()
    so we can show a message box if required.
    """
    def __init__(self):
        super().__init__(add_help=False)  # we do the help ourselves
        
    def exit(self, status=0, message=None):
        if message is not None:
            if GUI_MODE:
                QMessageBox.critical(None, MESSAGE_TITLE, message)
            else:
                print(message, file=sys.stderr)
        sys.exit(status)
        
    def error(self, message):
        if GUI_MODE:
            QMessageBox.critical(None, MESSAGE_TITLE, message)
        else:
            print(message, file=sys.stderr)
        sys.exit(2)

    
def getCmdargs():
    """
    Get commandline arguments
    """
    p = TuiViewArgumentParser()
    p.add_argument('-b', '--bands', 
        help="comma seperated list of bands to display")
    p.add_argument('-c', '--colortable', action="store_true", default=False,
        help="Apply color table to image")
    p.add_argument('-g', '--greyscale', action="store_true", default=False,
        help="Display image in greyscale")
    p.add_argument('-r', '--rgb', action="store_true", default=False,
        help="use 3 bands to create RGB image")
    p.add_argument('-p', '--pseudocolor', nargs=1, metavar=('name',),
        help="Display image using a pseudocolor ramp")
    p.add_argument('-n', '--nostretch', action="store_true", default=False, 
        help="do no stretch on data")
    p.add_argument('-l', '--linear', nargs=2, metavar=('minVal', 'maxVal'),
        help="do a linear stretch between two values " +
            "(eg '-l 0 10'). Pass 'stats' for statistics")
    p.add_argument('-s', '--stddev', action="store_true", default=False,
        help="do a 2 standard deviation stretch")
    p.add_argument('--hist', action="store_true", default=False,
        help="do a histogram stretch")
    p.add_argument('--stretchfromtext', 
        help="Load stretch and lookup table from text file")
    p.add_argument('--stretchfromgdal', 
        help="Load stretch and lookup table from GDAL file" + 
        " that contains saved stretch and lookup table")
    p.add_argument('--noplugins', action="store_false", default=True, 
        dest='loadplugins', help="Don't load plugins")
    p.add_argument('--separate', action="store_true", default=False,
        help="load multiple files into separate windows")
    p.add_argument('--goto', help="Zoom to a location. Format is:"+
        " 'easting,northing,factor' where factor is meters"+
        " per window pixel.")
    p.add_argument('-v', '--vector', action='append', dest="vectors",
        help="overlay vector file on top of all rasters." +
        " Can be specified multiple times")
    p.add_argument('--vectorlayer', action='append', dest="vectorlayers",
        help="vector layer name(s) to use with --vector. " +
            "Can't be specified if --vectorsql is used. " +
            "Can be specified multiple times - once for each vector")
    p.add_argument('--vectorsql', action='append', dest="vectorsqls",
        help="vector SQL statement(s) to use with --vector. " +
            "Can't be specified if --vectorlayer is used. " +
            "Can be specified multiple times - once for each vector")
    p.add_argument('--vectorlabel', action='append', dest="vectorlabels",
        help="Vector attributes to label. Can be specified multiple times " +
            "- once for each vector")
    p.add_argument('--vectorreproj', action='append', choices=['yes', 'no'],
        dest='vectorreproj', help="whether vector is reprojected to match " +
            "raster. Can be specified multiple times - once for each vector")
    p.add_argument('-t', '--savedstate', 
        help="path to a .tuiview file with saved viewers state")
    # do this ourselves so we can show QMessageBox if GUI_MODE
    p.add_argument('-h', '--help', action="store_true", default=False,
        help="Show this message and exit")
    p.add_argument('filenames', nargs='*')

    cmdargs = p.parse_args()
    
    if cmdargs.help:
        if GUI_MODE:
            msgBox = QMessageBox(QMessageBox.Information, MESSAGE_TITLE, 
                "Get command line information by clicking 'Show Details...'",
                QMessageBox.Ok)
            msgBox.setDetailedText(p.format_help())
            msgBox.exec_()
        else:
            p.print_help()
        sys.exit(1)
    
    # default values for these 'fake' parameters that we
    # then set depending on the flags.
    cmdargs.stretch = viewerstretch.ViewerStretch()
    cmdargs.modeSet = False
    cmdargs.stretchModeSet = False
    cmdargs.bandsSet = False

    if cmdargs.colortable:
        cmdargs.stretch.setColorTable()
        cmdargs.modeSet = True
    if cmdargs.greyscale:
        cmdargs.stretch.setGreyScale()
        cmdargs.modeSet = True
    if cmdargs.rgb:
        cmdargs.stretch.setRGB()
        cmdargs.modeSet = True
    if cmdargs.pseudocolor is not None:
        ramp = cmdargs.pseudocolor[0]
        cmdargs.stretch.setPseudoColor(ramp)
        cmdargs.modeSet = True

    if cmdargs.nostretch:
        cmdargs.stretch.setNoStretch()
        cmdargs.stretchModeSet = True
    if cmdargs.linear is not None:
        (minVal, maxVal) = cmdargs.linear
        try:
            if minVal == 'stats':
                minVal = None
            else:
                minVal = float(minVal)

            if maxVal == 'stats':
                maxVal = None
            else:
                maxVal = float(maxVal)
        except ValueError as e:
            showMessageAndExit(str(e))
        cmdargs.stretch.setLinearStretch(minVal, maxVal)
        cmdargs.stretchModeSet = True
    if cmdargs.stddev:
        cmdargs.stretch.setStdDevStretch()
        cmdargs.stretchModeSet = True
    if cmdargs.hist:
        cmdargs.stretch.setHistStretch()
        cmdargs.stretchModeSet = True
    if cmdargs.bands is not None:
        try:
            bandlist = [int(x) for x in cmdargs.bands.split(',')]
        except ValueError as e:
            showMessageAndExit(str(e))
        cmdargs.stretch.setBands(bandlist)
        cmdargs.bandsSet = True
    if cmdargs.stretchfromtext is not None:
        try:
            cmdargs.stretch = viewerstretch.ViewerStretch.fromTextFileWithLUT(
                cmdargs.stretchfromtext)
            cmdargs.modeSet = True
            cmdargs.stretchModeSet = True
            cmdargs.bandsSet = True
        except Exception as e:
            showMessageAndExit(str(e))
    if cmdargs.stretchfromgdal is not None:
        try:
            cmdargs.stretch = viewerstretch.ViewerStretch.fromGDALFileWithLUT(
                cmdargs.stretchfromgdal)
            cmdargs.modeSet = True
            cmdargs.stretchModeSet = True
            cmdargs.bandsSet = True
        except Exception as e:
            showMessageAndExit(str(e))

    return cmdargs


class ViewerApplication(QApplication):
    """
    Main class for application
    """
    def __init__(self):
        QApplication.__init__(self, sys.argv)
        self.pluginHandlers = []

        # for settings
        self.setApplicationName('tuiview')
        self.setOrganizationName('TuiView')

        cmdargs = getCmdargs()

        loadplugins = cmdargs.loadplugins
        self.viewers = geolinkedviewers.GeolinkedViewers(loadplugins)

        stretch = None
        if (cmdargs.modeSet and cmdargs.stretchModeSet and
                cmdargs.bandsSet):
            # use the stretch they have constructed
            stretch = cmdargs.stretch
        elif (cmdargs.modeSet or cmdargs.stretchModeSet or
                cmdargs.bandsSet):
            msg = ('Stretch incomplete. Must specify one of [-c|-g|-r] and' + 
                ' one of [-n|-l|-s|--hist] and -b, or none to use defaults.')
            showMessageAndExit(msg)
            
        if cmdargs.vectorlayers is not None and cmdargs.vectorsqls is not None:
            msg = 'Specify only one of --vectorlayer and --vectorsql'
            showMessageAndExit(msg)
            
        if (cmdargs.vectors is not None and cmdargs.vectorlayers is not None and
                len(cmdargs.vectors) != len(cmdargs.vectorlayers)):
            msg = 'If specified, you must pass one --vectorlayer per --vector'
            showMessageAndExit(msg)

        if (cmdargs.vectors is not None and cmdargs.vectorsqls is not None and
                len(cmdargs.vectors) != len(cmdargs.vectorsqls)):
            msg = 'If specified, you must pass one --vectorsql per --vector'
            showMessageAndExit(msg)

        if (cmdargs.vectors is not None and cmdargs.vectorlabels is not None and
                len(cmdargs.vectors) != len(cmdargs.vectorlabels)):
            msg = 'If specified, you must pass one --vectorlabel per --vector'
            showMessageAndExit(msg)
            
        if cmdargs.vectorlayers is not None and cmdargs.vectors is None:
            msg = 'When specifying --vectorlayer you must also specify --vector'
            showMessageAndExit(msg)

        if cmdargs.vectorsqls is not None and cmdargs.vectors is None:
            msg = 'When specifying --vectorsql you must also specify --vector'
            showMessageAndExit(msg)

        if cmdargs.vectorlabels is not None and (cmdargs.vectors is None or
                (cmdargs.vectorlayers is None and cmdargs.vectorsqls is None)):
            msg = ('When specifying --vectorlabel you must also specify ' 
                '--vector and one of --vectorlayer or --vectorsql')
            showMessageAndExit(msg)
            
        if (cmdargs.vectors is not None and cmdargs.vectorreproj is not None and
                len(cmdargs.vectors) != len(cmdargs.vectorreproj)):
            msg = 'If specified, you must pass one --vectorreproj per --vector'
            showMessageAndExit(msg)

        if cmdargs.vectorreproj is not None and cmdargs.vectors is None:
            msg = 'When specifying --vectorreproj you must also specify --vector'
            showMessageAndExit(msg)

        if len(cmdargs.filenames) == 0 and cmdargs.savedstate is None:
            self.viewers.newViewer()
        else:
            if cmdargs.separate:
                # need to be in separate windows
                for filename in cmdargs.filenames:
                    self.viewers.newViewer(filename, stretch)
            else:
                # load into one viewer
                viewer = None
                for filename in archivereader.file_list_to_archive_strings(
                        cmdargs.filenames):
                    if viewer is None:
                        viewer = self.viewers.newViewer(filename, stretch)
                    else:
                        viewer.addRasterInternal(filename, stretch)

        # saved state
        if cmdargs.savedstate is not None:
            try:
                fileobj = open(cmdargs.savedstate)
                self.viewers.readViewersState(fileobj)
                fileobj.close()
            except Exception as e:
                showMessageAndExit(str(e))

        # open vectors in all viewer windows
        if cmdargs.vectors is not None:
            layername = None  # reset if cmdargs.vectorsqls/cmdargs.vectorlayer exists
            # otherwise carries the first one selected through to all the viewers
            sql = None  # not used if cmdargs.vectorsqls/cmdargs.vectorlayer exists, otherwise 
            # carries first one through to all the viewers
            userCancel = False
            for viewer in self.viewers.viewers:
                for idx, vector in enumerate(cmdargs.vectors):
                    if cmdargs.vectorlayers is not None:
                        layername = cmdargs.vectorlayers[idx]
                    elif cmdargs.vectorsqls is not None:
                        sql = cmdargs.vectorsqls[idx]
                        
                    label = None
                    if cmdargs.vectorlabels is not None:
                        label = cmdargs.vectorlabels[idx]
                        
                    reproj = PROJ_NO  # keep old behaviour of not reprojecting by default
                    if (cmdargs.vectorreproj is not None and
                            cmdargs.vectorreproj[idx] == 'yes'):
                        reproj = PROJ_YES
                        
                    layername, sql = viewer.addVectorInternal(vector, 
                        layername=layername, sql=sql, label=label, 
                        reproj=reproj)
                    if layername is None and sql is None:
                        # they canceled... break out of loop
                        userCancel = True
                        break
                if userCancel:
                    break

        # goto a location
        if cmdargs.goto is not None:
            arr = cmdargs.goto.split(',')
            if len(arr) != 3:
                msg = "goto usage: 'easting,northing,factor'"
                showMessageAndExit(msg)
            (easting, northing, metresperimgpix) = arr
            easting = float(easting)
            northing = float(northing)
            metresperimgpix = float(metresperimgpix)

            obj = GeolinkInfo(0, easting, northing, metresperimgpix)
            self.viewers.onMove(obj)                

    def savePluginHandler(self, handler):
        """
        Plugins need to be able to save an instance of their signal handling 
        object so it doesn't get cleaned up by Python's garbage collection.
        There are a number of ways to address this, but this seems the cleanest.
        
        Get an instance of this ViewerApplication class in the plugin by using the:
            app = QApplication.instance()
            
        Call.
        """
        self.pluginHandlers.append(handler)


def run():
    """
    Call this function to instantiate an instance of ViewerApplication
    and have the command line parameters inspected etc and app run
    """
    app = ViewerApplication()
    app.exec_()
