
"""
Utility module to insert 'surrogate' color tables
from a specified file into the metadata of the
destination file.

Can also print info on existing 'surrogate' color tables
and delete specified tables.
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

from __future__ import print_function
import sys
import optparse
from osgeo import gdal
from tuiview.viewerLUT import ViewerLUT
from tuiview.viewerRAT import ViewerRAT

class CmdArgs(object):
    """
    Class for processing command line arguments
    """
    def __init__(self):
        usage = "usage: %prog [options]"
        self.parser = optparse.OptionParser(usage)
        self.parser.add_option("-s", "--source", dest="source",
            help="File to read color table from")
        self.parser.add_option("-n", "--name", dest="name",
            help="name to save the color table under")
        self.parser.add_option("-d", "--dest", dest="dest",
            help="destination file to write color table into")
        self.parser.add_option("-p", "--print", dest="printct",
            help="print out available color tables")
        self.parser.add_option("-r", "--remove", dest="remove", 
            help="remove table from specified file (must specify --name also)")

        (options, args) = self.parser.parse_args()
        writeArgs = [options.source, options.name, options.dest]
        writeValid = [x is not None for x in writeArgs]
        if (options.printct is None and options.remove is None and
			any(writeValid) and not all(writeValid)):
            msg = "Must specify all of --source, --name and --dest for writing"
            raise SystemExit(msg)

        if options.printct is not None and options.remove is not None:
            msg = "can't specify both --print and --remove"
            raise SystemExit(msg)

        if options.remove is not None and options.name is None:
            msg = "Must specify --name for --remove"
            raise SystemExit(msg)

        if options.printct is not None and any(writeValid):
            msg = "can't specify --name, --source or --dest with --print"
            raise SystemExit(msg)

        if not options.printct and not any(writeValid):
                self.parser.print_help()
                sys.exit(0)

        self.__dict__.update(options.__dict__)

def printTables(fname):
    """
    Print report on existing surrogate color tables
    """
    ds = gdal.Open(fname)
    if ds is None:
        msg = "Cannot open %s" % fname
        raise SystemExit(msg)

    tables = ViewerLUT.readSurrogateColorTables(ds)
    if len(tables) == 0:
        print("No tables found")
    else:
        print("Name\tSize")
        print("------------------------")

        for name in tables:
            (size, bands) = tables[name].shape
            print("%s\t%s" % (name, size))

    del ds

def addTable(source, name, dest):
    """
    Insert color table from source as a surrogate
    color table into dest, naming it name
    """
    sourceds = gdal.Open(source)
    if sourceds is None:
        msg = "Cannot open %s" % source
        raise SystemExit(msg)

    # always band 1?
    sourceband = sourceds.GetRasterBand(1)
    rat = ViewerRAT()
    rat.readFromGDALBand(sourceband, sourceds)

    # should we allow this to be set?
    nodata_rgba = (0, 0, 0, 0)
    nan_rgba = (0, 0, 0, 0)
    lutobj = ViewerLUT()
    lut, bi = lutobj.loadColorTable(rat, nodata_rgba, nodata_rgba, nan_rgba)

    destds = gdal.Open(dest, gdal.GA_Update)
    if destds is None:
        msg = "Cannot open %s for writing" % dest
        raise SystemExit(msg)

    # read in existing tables (if any)
    tables = ViewerLUT.readSurrogateColorTables(destds)

    # what to do if already exists? Dunno.
    tables[name] = lut[:-2] # strip off the nodata and background

    # write out
    ViewerLUT.writeSurrogateColorTables(destds, tables)

    del sourceds
    del destds

def removeTable(fname, tablename):

    destds = gdal.Open(fname, gdal.GA_Update)
    if destds is None:
        msg = "Cannot open %s for writing" % fname
        raise SystemExit(msg)

    # read in existing tables (if any)
    tables = ViewerLUT.readSurrogateColorTables(destds)

    if tablename not in tables:
        msg = "Can't find table %s in %s" % (tablename, fname)
        raise SystemExit(msg)

    del tables[tablename]

    # write out
    ViewerLUT.writeSurrogateColorTables(destds, tables)

    del destds


def run():
    """
    Call this to have command line parameters interpreted
    and the appropriate function called.
    """
    # main program
    cmdargs = CmdArgs()
    
    if cmdargs.printct is not None:
        printTables(cmdargs.printct)
    elif cmdargs.remove is not None:
        removeTable(cmdargs.remove, cmdargs.name)
    else:
        addTable(cmdargs.source, cmdargs.name, cmdargs.dest)

