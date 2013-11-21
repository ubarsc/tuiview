#!/usr/bin/env python
"""
Setup script for TuiView. Use like this for Unix:

$ python setup.py install

For creation of cxfreeze bundle on Windows:
> /c/Python33/python.exe setup.py install
> /c/Python33/python.exe setup_cxfreeze.py bdist_msi

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
from cx_Freeze import setup, Executable
import os
import sys

import tuiview

# NB. Had to hack python scripts in C:\Python33\Lib\site-packages\osgeo
# to 'from . import <blah>' in exception handler, and all over
base = None
include_msvcr = False
initScript = None
include_files = None
if sys.platform == "win32":
    base = "Win32GUI"
    include_msvcr = True
    curDir = os.path.dirname(os.path.abspath(sys.argv[0]))
    initScript = os.path.join(curDir, 'cxfreeze_init.py') # sets the GDAL_DATA path
    #keadir = 'c:\\kea\\gdal110_2010'
    hdfdir = 'C:\\GDALDeps2010\\bin'
    gdaldir = 'c:\\GDAL2010'
    gdaldatadir = os.path.join(gdaldir, "data")
    gdalpluginsdir = os.path.join(gdaldir, "bin", "gdalplugins")
    # using internal version now via KEA inline patch (keaplugindir, "gdalplugins")
    #keaplugindir = os.path.join(keadir, "gdalplugins")
    hdfcpp = os.path.join(hdfdir, "HDF5_CPPDLL.DLL")
    include_files = [(gdaldatadir, "data"), (gdalpluginsdir, "gdalplugins"),
                    ("C:\\kea\\gdal110_2010\\lib\\libkea.dll", ""), (hdfcpp, '')]

build_exe_options = {'excludes':["pywin", "pywin.debugger", "pydoc",
                    "pywin.debugger.dbgcon", "pywin.dialogs", "pywin.dialogs.list",
                    "Tkconstants","Tkinter","tcl","tk"], "includes" : ["atexit", "osgeo._gdal"],
                    'include_msvcr':include_msvcr, 'include_files':include_files, "init_script":initScript,
                    "optimize":'2'}
                    
viewerexe = Executable("bin/tuiview", base=base, shortcutName='TuiView-%s' % tuiview.TUIVIEW_VERSION, 
            shortcutDir="ProgramMenuFolder")
viewerwritetableexe = Executable("bin/tuiviewwritetable") # console is default

#
setup(name='TuiView',
      version=tuiview.TUIVIEW_VERSION,
      description='Simple Raster Viewer',
      author='Sam Gillingham',
      author_email='gillingham.sam@gmail.com',
      options={"build_exe": build_exe_options},
      executables=[viewerexe, viewerwritetableexe])
      
 