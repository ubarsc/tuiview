#!/usr/bin/env python
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
import os
import shutil

keadir = 'c:\\kea\\gdal19'
hdfdir = 'C:\\Program Files\\HDF Group\\HDF5\\1.8.9\\bin'

def addkea(distdir):
    distplugins = os.path.join(distdir, 'gdalplugins')
    if not os.path.exists(distplugins):
        os.mkdir(distplugins)
    
    keagdal = os.path.join(keadir, 'gdalplugins', 'gdal_KEA.dll')
    shutil.copy(keagdal, distplugins)

    kealib = os.path.join(keadir, 'lib', 'libkea.dll')
    shutil.copy(kealib, distdir)

    for dll in ('HDF5_CPPDLL.DLL', 'HDF5DLL.DLL', 'ZLIB.DLL', 'SZIP.DLL'):
        srcpath = os.path.join(hdfdir, dll)
        shutil.copy(srcpath, distdir)
        
if __name__ == '__main__':
    addkea('dist')
