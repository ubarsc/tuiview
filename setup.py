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
from distutils.core import setup

import tuiview

setup(name='TuiView', 
    version=tuiview.TUIVIEW_VERSION, 
    description='Simple Raster Viewer',
    author='Sam Gillingham',
    author_email='gillingham.sam@gmail.com',
    scripts=['bin/tuiview', 'bin/tuiviewwritetable'],
    packages=['tuiview'],
    license='LICENSE.txt',
    install_requires=['numpy', 'PyQt4'],
    url='https://bitbucket.org/chchrsc/tuiview',
    classifiers=['Intended Audience :: Developers',
          'Operating System :: OS Independent',
          'Programming Language :: Python :: 2',
          'Programming Language :: Python :: 2.7',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.2',
          'Programming Language :: Python :: 3.3'])
