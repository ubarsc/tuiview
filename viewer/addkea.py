#!/usr/bin/env python

import os
import shutil

distdir = 'dist'
keadir = 'c:\\kea\\gdal19'
hdfdir = 'C:\\Program Files\\HDF Group\\HDF5\\1.8.9\\bin'

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
