#!/usr/bin/env python
"""
Setup script for TuiView. 

Installation
------------

Use like this:

$ pip install .

See INSTALL.txt for more information.

Creating Source Packages
------------------------

Use like this:

$ python setup.py sdist --formats=gztar,zip

The packages will be created in the 'dist' subdirectory.

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

import os
import sys
from setuptools import setup, Extension
import tuiview

# don't build extensions if we are in readthedocs
withExtensions = os.getenv('READTHEDOCS', default='False') != 'True'
# there seems to be no 'standard' cross compilation env var, so just using
# the conda one as that is what I'm really interested in
crossCompiling = os.getenv('CONDA_BUILD_CROSS_COMPILATION', default='0') == '1'

try:
    from osgeo import gdal, ogr  # noqa
except ImportError:
    if withExtensions and not crossCompiling:
        raise SystemExit("GDAL with Python bindings must be installed first")


def have_geos():
    """
    Check that GDAL is built with GEOS support
    """
    geos_flag = True  # assume all ok if we can't test
    if withExtensions and not crossCompiling:
        pnt1 = ogr.CreateGeometryFromWkt('POINT(10 20)')
        pnt2 = ogr.CreateGeometryFromWkt('POINT(30 20)')
        gdal.PushErrorHandler('CPLQuietErrorHandler')
        geos_flag = pnt1.Union(pnt2) is not None
        gdal.PopErrorHandler()
    return geos_flag


def getGDALFlags():
    """
    Return the flags needed to link in GDAL as a dictionary
    """
    if not have_geos():
        raise SystemExit("GDAL not built with GEOS support")
    
    from numpy import get_include as numpy_get_include
    extraargs = {}
    # don't use the deprecated numpy api
    extraargs['define_macros'] = [('NPY_NO_DEPRECATED_API', 'NPY_1_7_API_VERSION')]

    if sys.platform == 'win32':
        # Windows - rely on %GDAL_HOME% being set and set 
        # paths appropriately
        gdalhome = os.getenv('GDAL_HOME')
        if gdalhome is None:
            raise SystemExit("need to define %GDAL_HOME%")
        extraargs['include_dirs'] = [os.path.join(gdalhome, 'include'), numpy_get_include()]
        extraargs['library_dirs'] = [os.path.join(gdalhome, 'lib')]
        # nmake builds of gdal created the import lib as gdal_i.lib
        # new cmake builds create it as gdal.lib. Handle both
        for name in ('gdal_i', 'gdal'):
            lib = os.path.join(gdalhome, 'lib', name + '.lib')
            if os.path.exists(lib):
                extraargs['libraries'] = [name]
                break
                
        if 'libraries' not in extraargs:
            raise SystemExit('Unable to find gdal import lib')
    else:
        # Unix - can do better with actual flags using gdal-config
        extraargs['include_dirs'] = [numpy_get_include()]
        import subprocess
        try:
            cflags = subprocess.check_output(['gdal-config', '--cflags'])
            cflags = cflags.decode()
            extraargs['extra_compile_args'] = cflags.strip().split()

            ldflags = subprocess.check_output(['gdal-config', '--libs'])
            ldflags = ldflags.decode()
            extraargs['extra_link_args'] = ldflags.strip().split()
        except OSError:
            raise SystemExit("can't find gdal-config - GDAL development files need to be installed")
    return extraargs


if withExtensions:
        
    # get the flags for GDAL
    gdalargs = getGDALFlags()

    # create our vector extension
    vecextkwargs = {'name': 'vectorrasterizer', 
        'sources': ['src/vectorrasterizer.c']}
    # add gdalargs
    vecextkwargs.update(gdalargs)

    vecmodule = Extension(**vecextkwargs)
    ext_modules = [vecmodule]
else:
    ext_modules = []

setup(name='TuiView', 
    version=tuiview.TUIVIEW_VERSION, 
    description='Simple Raster Viewer',
    author='Sam Gillingham',
    author_email='gillingham.sam@gmail.com',
    entry_points={
        'console_scripts': [
            'tuiviewwritetable = tuiview:writetableapplication.run'
        ],
        'gui_scripts': [
            'tuiview = tuiview:viewerapplication.run'
        ]
    },
    packages=['tuiview'],
    ext_package='tuiview',
    ext_modules=ext_modules,
    license='LICENSE.txt',
    url='http://tuiview.org/',
    classifiers=['Intended Audience :: Developers',
          'Operating System :: OS Independent',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
          'Programming Language :: Python :: 3.8',
          'Programming Language :: Python :: 3.9',
          'Programming Language :: Python :: 3.10'])


