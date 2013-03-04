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

# NB. Had to hack python scripts in C:\Python32\Lib\site-packages\osgeo
# to 'from . import <blah>' in exception handler, and all over
# also under scipy.sparse.sparsetools...

base = None
include_msvcr = False
initScript = None
if sys.platform == "win32":
    base = "Win32GUI"
    include_msvcr = True
    curDir = os.path.dirname(os.path.abspath(sys.argv[0]))
    initScript = os.path.join(curDir, 'cxfreeze_init.py')

build_exe_options = {'excludes':["pywin", "pywin.debugger", "pydoc",
                    "pywin.debugger.dbgcon", "pywin.dialogs", "pywin.dialogs.list",
                    "Tkconstants","Tkinter","tcl","tk"], "includes" : ["atexit",                    
                    "osgeo._gdal", "osgeo._osr", "osgeo._gdal_array", "osgeo._ogr",
                    "scipy.sparse.sparsetools._csr", "scipy.sparse.sparsetools._csc",
                    "scipy.sparse.sparsetools._coo", "scipy.sparse.sparsetools._dia",
                    "scipy.sparse.sparsetools._bsr", "scipy.sparse.sparsetools._csgraph"],
                    'include_msvcr':include_msvcr}

viewerexe = Executable("bin/viewer", base=base, shortcutName='Viewer', initScript=initScript)
viewerwritetableexe = Executable("bin/viewerwritetable", initScript=initScript) # console is default

#
setup(name='Viewer_%s' % date.today().strftime('%Y%m%d'),
      version='1.0',
      description='Simple Raster Viewer',
      author='Sam Gillingham',
      author_email='gillingham.sam@gmail.com',
      options={"build_exe": build_exe_options},
      executables=[viewerexe, viewerwritetableexe])
      
 