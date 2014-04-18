#!/usr/bin/env python
"""
Setup script for TuiView. Use like this for Unix:

$ python setup.py install

For creation of cx freeze installer on Windows
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
from numpy.distutils.core import setup, Extension
from distutils.version import LooseVersion
import os
import sys

try:
    from osgeo import gdal
except ImportError:
    raise SystemExit("GDAL with Python bindings must be installed first")

import tuiview

def getGDALFlags():
    """
    Return the flags needed to link in GDAL as a dictionary
    """
    extraargs = {}
    if sys.platform == 'win32':
        # Windows - rely on $GDAL_HOME being set and set 
        # paths appropriately
        gdalhome = os.getenv('GDAL_HOME')
        if gdalhome is None:
            raise SystemExit("need to define $GDAL_HOME")
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

    if gdalVersion is None or LooseVersion(gdalVersion) < LooseVersion('1.11.0'):
        raise SystemExit("This version of TuiView")



# check the version
checkGDALVersion()

# get the flags for GDAL
gdalargs = getGDALFlags()

# create our vector extension
vecextkwargs = {'name':'vectorrasterizer', 'sources':['src/vectorrasterizer.c']}
# add gdalargs
vecextkwargs.update(gdalargs)

vecmodule = Extension(**vecextkwargs)

setup(name='TuiView', 
    version=tuiview.TUIVIEW_VERSION, 
    description='Simple Raster Viewer',
    author='Sam Gillingham',
    author_email='gillingham.sam@gmail.com',
    scripts=['bin/tuiview', 'bin/tuiviewwritetable'],
    packages=['tuiview'],
    ext_package = 'tuiview',
    ext_modules = [vecmodule],
    license='LICENSE.txt',
    url='https://bitbucket.org/chchrsc/tuiview',
    classifiers=['Intended Audience :: Developers',
          'Operating System :: OS Independent',
          'Programming Language :: Python :: 2',
          'Programming Language :: Python :: 2.7',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.2',
          'Programming Language :: Python :: 3.3'])
