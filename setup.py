#!/usr/bin/env python
"""
Setup script for TuiView. 

Installation
------------

Use like this:

$ python setup.py install

GDAL devel files need to be installed along with a C compiler.
numpy and pyqt also required.

export TUIVIEW_NOCMDLINE=1

First to prevent the command line scripts from being installed which
is useful when using Python entry points instead.

Creating Source Packages
------------------------

Use like this:

$ python setup.py sdist --formats=gztar,zip

The packages will be created in the 'dist' subdirectory.

export INCLUDE_WINDOWS_BAT=1

First to include the .bat files needed for Windows installation.
(these aren't included in packages created on non-Windows platforms
by default).

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

# If we fail to import the numpy version of setup, still try to proceed, as it is possibly
# because we are being run by ReadTheDocs, and so we just need to be able to generate documentation. 
try:
    from numpy.distutils.core import setup, Extension
    withExtensions = True
except ImportError:
    from distutils.core import setup
    withExtensions = False
    
from distutils.version import LooseVersion
import os
import sys

try:
    from osgeo import gdal
except ImportError:
    if withExtensions:
        raise SystemExit("GDAL with Python bindings must be installed first")

import tuiview
MIN_GDAL_VERSION = '1.11.0'

# Are we installing the command line scripts?
# this is an experimental option for users who are
# using the Python entry point feature of setuptools and Conda instead
NO_INSTALL_CMDLINE = int(os.getenv('TUIVIEW_NOCMDLINE', '0')) > 0

# When building the sdist on Linux we want the extra .bat
# files that are need for the Windows install. 
INCLUDE_WINDOWS_BAT = int(os.getenv('TUIVIEW_INCLUDEBAT', '0')) > 0

def getGDALFlags():
    """
    Return the flags needed to link in GDAL as a dictionary
    """
    extraargs = {}
    # don't use the deprecated numpy api
    extraargs['define_macros'] = [('NPY_NO_DEPRECATED_API', 'NPY_1_7_API_VERSION')]

    if sys.platform == 'win32':
        # Windows - rely on %GDAL_HOME% being set and set 
        # paths appropriately
        gdalhome = os.getenv('GDAL_HOME')
        if gdalhome is None:
            raise SystemExit("need to define %GDAL_HOME%")
        extraargs['include_dirs'] = [os.path.join(gdalhome, 'include')]
        extraargs['library_dirs'] = [os.path.join(gdalhome, 'lib')]
        extraargs['libraries'] = ['gdal_i']
    else:
        # Unix - can do better with actual flags using gdal-config
        import subprocess
        try:
            cflags = subprocess.check_output(['gdal-config', '--cflags'])
            if sys.version_info[0] >= 3:
                cflags = cflags.decode()
            extraargs['extra_compile_args'] = cflags.strip().split()

            ldflags = subprocess.check_output(['gdal-config', '--libs'])
            if sys.version_info[0] >= 3:
                ldflags = ldflags.decode()
            extraargs['extra_link_args'] = ldflags.strip().split()
        except OSError:
            raise SystemExit("can't find gdal-config - GDAL development files need to be installed")
    return extraargs

def checkGDALVersion():
    """
    Checks the installed GDAL version (via the Python bindings) 
    and exits with message if it is too old.
    """
    gdalVersion = None
    if hasattr(gdal, '__version__'):
        gdalVersion = gdal.__version__

    if gdalVersion is None or LooseVersion(gdalVersion) < LooseVersion(MIN_GDAL_VERSION):
        msg = "This version of TuiView requires GDAL Version %s or later" % MIN_GDAL_VERSION
        raise SystemExit(msg)

if withExtensions:
    # check the version
    checkGDALVersion()

    # get the flags for GDAL
    gdalargs = getGDALFlags()

    # create our vector extension
    vecextkwargs = {'name':'vectorrasterizer', 'sources':['src/vectorrasterizer.c']}
    # add gdalargs
    vecextkwargs.update(gdalargs)

    vecmodule = Extension(**vecextkwargs)
    ext_modules = [vecmodule]
else:
    ext_modules = []

if NO_INSTALL_CMDLINE:
    scripts_list = None
else:
    # For windows also copy bat files, to run python scripts
    if sys.platform == 'win32' or INCLUDE_WINDOWS_BAT:
        scripts_list = ['bin/tuiview','bin/tuiview.bat',
                     'bin/tuiviewwritetable','bin/tuiviewwritetable.bat']
    else:
        scripts_list = ['bin/tuiview',
                     'bin/tuiviewwritetable']

setup(name='TuiView', 
    version=tuiview.TUIVIEW_VERSION, 
    description='Simple Raster Viewer',
    author='Sam Gillingham',
    author_email='gillingham.sam@gmail.com',
    scripts=scripts_list,
    packages=['tuiview'],
    ext_package = 'tuiview',
    ext_modules = ext_modules,
    license='LICENSE.txt',
    url='https://bitbucket.org/chchrsc/tuiview',
    classifiers=['Intended Audience :: Developers',
          'Operating System :: OS Independent',
          'Programming Language :: Python :: 2',
          'Programming Language :: Python :: 2.7',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.4',
          'Programming Language :: Python :: 3.5',
          'Programming Language :: Python :: 3.6'])


