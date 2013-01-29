#!/usr/bin/env python
"""
Setup script for viewer. Use like this for Unix:

$ python setup.py install

For creation of py2exe bundle on Windows:
> /c/Python27/python.exe setup.py install
> /c/Python27/python.exe setup.py py2exe

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
from distutils.core import setup
import os
import sys

class OSSpecificOps(object):
    def __init__(self, distdir, action):
        self.distdir = distdir
    def preInstall(self, kwargs, action):
        pass
    def postInstall(self, action):
        pass
        
class Win32SpecificOps(OSSpecificOps):
    def __init__(self, distdir, action):
        OSSpecificOps.__init__(self, distdir, action)
        if action == 'py2exe':
            # can't seem to set this programatically. Sets the GDAL_DATA 
            # environment variable
            sys.argv.append('--custom-boot-script=winbootscript.py')
    def preInstall(self, kwargs, action):
        if action == 'py2exe':
            # to allow creation of an installer for Windows
            # clean up old build
            import py2exe
            from glob import glob
            import shutil
            try:
                shutil.rmtree(self.distdir)
            except:
                pass

            # bundle the runtime and set up other files
            data_files = [("Microsoft.VC90.CRT", glob(r'C:\Program Files\Microsoft Visual Studio 9.0\VC\redist\x86\Microsoft.VC90.CRT\*.*'))]
            kwargs['data_files'] = data_files
            kwargs['windows'] = ['bin/viewer']
            kwargs['console'] = ['bin/viewerwritetable']
            # see http://www.py2exe.org/index.cgi/TkInter, http://www.py2exe.org/index.cgi/Py2exeAndPyQt
            # gone all out on the optimisations - don't need docstrings etc
            options = {'py2exe':{'bundle_files' : 3, 'includes':["sip", "scipy.sparse.csgraph._validation"],
                        'excludes':["pywin", "pywin.debugger", "pywin.debugger.dbgcon", "pywin.dialogs", "pywin.dialogs.list",
                        "Tkconstants","Tkinter","tcl"], 'optimize':2, 'dist_dir' : self.distdir}}
            kwargs['options'] = options
            
    def postInstall(self, action):
        if action == 'py2exe':
            import addkea
            # copy the GDAL projections etc
            addkea.adddata(self.distdir)
            # any plugins we have build (fileGDB/AOI)
            addkea.addplugins(self.distdir)
            # add kea/hdf dlls
            addkea.addkea(self.distdir)
            # don't need this file
            os.remove(os.path.join(self.distdir, 'w9xpopen.exe'))
            
class MacSpecificOps(OSSpecificOps):
    def __init__(self, distdir, action):
        OSSpecificOps.__init__(self, distdir, action)
    def preInstall(self, kwargs, action):
        if action == 'py2app':
            from setuptools import setup
            import shutil
            try:
                shutil.rmtree(self.distdir)
            except:
                pass

            app = ['bin/viewer']
            data_files = []
            options = {'py2app':{'argv_emulation': True, 'dist_dir': self.distdir, 'includes': ['sip']}}

            kwargs['data_files'] = data_files
            kwargs['app'] = app
            kwargs['options'] = options
            kwargs['setup_requires'] = 'py2app'

def doSetup():
    # create the args to setup as a dictionary so we
    # can add extras for Windows/Mac if needed
    kwargs = {'name':'viewer',
      'version':'0.9',
      'description':'Simple Raster Viewer',
      'author':'Sam Gillingham',
      'author_email':'gillingham.sam@gmail.com',
      'scripts':['bin/viewer', 'bin/viewerwritetable'],
      'packages':['viewer'],
      'license':'LICENSE.txt',
      'url':'https://bitbucket.org/chchrsc/viewer'}
      
    action = None
    if len(sys.argv) > 1:
        action = sys.argv[1]
        
    distdir = 'dist'
    if sys.platform == 'win32':
        ops = Win32SpecificOps(distdir, action)
    elif sys.platform == 'darwin':
        ops = MacSpecificOps(distdir, action)
    else:
        # no specific actions
        ops = OSSpecificOps(distdir, action)

    ops.preInstall(kwargs, action)

    # now run setup with the options we have collected
    setup(**kwargs)

    ops.postInstall(action)

if __name__ == '__main__':
    doSetup()
    