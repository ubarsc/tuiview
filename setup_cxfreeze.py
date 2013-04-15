#!/usr/bin/env python
"""
Setup script for viewer. Use like this for Unix:

$ python setup.py install

For creation of cxfreeze bundle on Windows:
> /c/Python32/python.exe setup.py build
> /c/Python32/python.exe setup.py bdist_msi

"""
# This file is part of 'Viewer' - a simple Raster viewer
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
from datetime import date

# my own command - 'rebase' Rebases all dll's to a unqiue address
# so it loads faster. Uses the editbin utility.
# Needs to have the Visual Studio (vcvars.bat) sourced first.
if len(sys.argv) > 1 and sys.argv[1] == 'rebase':
    # guess at the build dir - can't seem to ask cx_freeze what it should be
    builddir = 'build\exe.%s-%d.%d' % (sys.platform, sys.version_info[0], sys.version_info[1])
    cmd = 'editbin.exe /REBASE %s\*.dll %s\*.pyd' % (builddir, builddir)
    os.system(cmd)
    sys.exit()

# to make a unique name encode todays date
appName = 'Viewer_%s' % date.today().strftime('%Y%m%d')

# NB. Had to hack python scripts in C:\Python32\Lib\site-packages\osgeo
# to 'from . import <blah>' in exception handler, and all over
# also under scipy.sparse.sparsetools...

base = None
include_msvcr = False
initScript = None
include_files = None
if sys.platform == "win32":
    base = "Win32GUI"
    include_msvcr = True
    curDir = os.path.dirname(os.path.abspath(sys.argv[0]))
    initScript = os.path.join(curDir, 'cxfreeze_init.py') # sets the GDAL_DATA path
    keadir = 'c:\\kea\\gdal19'
    hdfdir = 'C:\\Program Files\\HDF Group\\HDF5\\1.8.9\\bin'
    gdaldir = 'c:\\GDAL'
    gdaldatadir = os.path.join(gdaldir, "data")
    gdalpluginsdir = os.path.join(gdaldir, "bin", "gdalplugins")
    keaplugindir = os.path.join(keadir, "gdalplugins")
    hdfcpp = os.path.join(hdfdir, "HDF5_CPPDLL.DLL")
    include_files = [(gdaldatadir, "data"), (keaplugindir, "gdalplugins"), (gdalpluginsdir, "gdalplugins"),
                    ("C:\\kea\\gdal19\\lib\\libkea.dll", ""), (hdfcpp, '')]

# I had to hardcode a lot of scipy stuff for PyQtGraph - dunno why
# also had to import scipy.stats.futil in the main app to get PyQtGraph working
build_exe_options = {'excludes':["pywin", "pywin.debugger", "pydoc",
                    "pywin.debugger.dbgcon", "pywin.dialogs", "pywin.dialogs.list",
                    "Tkconstants","Tkinter","tcl","tk"], "includes" : ["atexit",
                    "osgeo._gdal", "osgeo._osr", "osgeo._gdal_array", "osgeo._ogr",
                    "scipy.sparse.sparsetools._csr", "scipy.sparse.sparsetools._csc",
                    "scipy.sparse.sparsetools._coo", "scipy.sparse.sparsetools._dia",
                    "scipy.sparse.sparsetools._bsr", "scipy.sparse.sparsetools._csgraph",
                    "scipy.stats.futil", "scipy.sparse.csgraph._validation",
                    "scipy.sparse.linalg.dsolve.umfpack", "scipy.integrate.vode",
                    "scipy.integrate.lsoda"],
                    'include_msvcr':include_msvcr, 'include_files':include_files, "init_script":initScript}

viewerexe = Executable("bin/viewer", base=base, shortcutName=appName, 
            shortcutDir="ProgramMenuFolder")
viewerwritetableexe = Executable("bin/viewerwritetable") # console is default

#
setup(name=appName,
      version='1.0',
      description='Simple Raster Viewer',
      author='Sam Gillingham',
      author_email='gillingham.sam@gmail.com',
      options={"build_exe": build_exe_options},
      executables=[viewerexe, viewerwritetableexe])
      
 