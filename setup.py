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

$ python -m build

The tar.gz source package and a binary distribution wheel file,
will be created in the 'dist' subdirectory.

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


# I need this so that the tuiview package can be imported, in order for
# pyproject.toml to access to the version number
sys.path.append('.')

# don't build extensions if we are in readthedocs
withExtensions = os.getenv('READTHEDOCS', default='False') != 'True'


def getGDALFlags():
    """
    Return the flags needed to link in GDAL as a dictionary
    """
    from numpy import get_include as numpy_get_include  # pylint: disable=C0415;
    extraargs = {}
    # don't use the deprecated numpy api
    extraargs['define_macros'] = [('NPY_NO_DEPRECATED_API', 'NPY_2_0_API_VERSION')]

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
        import subprocess  # pylint: disable=C0415;
        try:
            cflags = subprocess.check_output(['gdal-config', '--cflags'])
            cflags = cflags.decode()
            extraargs['extra_compile_args'] = cflags.strip().split()

            ldflags = subprocess.check_output(['gdal-config', '--libs'])
            ldflags = ldflags.decode()
            extraargs['extra_link_args'] = ldflags.strip().split()
        except (OSError, FileNotFoundError) as exc:
            raise SystemExit("can't find gdal-config - GDAL development files need to be installed") from exc
    return extraargs


if withExtensions:
    # get the flags for GDAL
    gdalargs = getGDALFlags()

    # create our vector extension
    vecextkwargs = {'name': 'tuiview.vectorrasterizer',
        'sources': ['c_src/vectorrasterizer.c']}
    # add gdalargs
    vecextkwargs.update(gdalargs)

    vecmodule = Extension(**vecextkwargs)
    ext_modules = [vecmodule]
else:
    ext_modules = []

setup(ext_modules=ext_modules)


