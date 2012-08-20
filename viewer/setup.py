#!/usr/bin/env python
"""
Setup script for viewer. Use like this for Unix:

$ python setup.py install

For creation of py2exe bundle on Windows:
> /c/Python27/python.exe setup.py install
> /c/Python27/python.exe setup.py py2exe

"""
from distutils.core import setup
import os
import sys

# create the args to setup as a dictionary so we
# can add extras for Windows if needed
kwargs = {'name':'viewer',
      'version':'0.9',
      'description':'Simple Raster Viewer',
      'author':'Sam Gillingham',
      'author_email':'gillingham.sam@gmail.com',
      'scripts':['bin/viewer'],
      'packages':['viewer'],
      'license':'LICENSE.txt',
      'url':'https://bitbucket.org/chchrsc/viewer'}

# are we building in executeable under Windows?
py2exe = sys.platform == 'win32' and sys.argv[1] == 'py2exe'

if py2exe:
    # to allow creation of an installer for Windows
    import py2exe
    from glob import glob
    import shutil
    distdir = 'dist'
    try:
        shutil.rmtree(distdir)
    except:
        pass

    # bundle the runtime
    data_files = [("Microsoft.VC90.CRT", glob(r'C:\Program Files\Microsoft Visual Studio 9.0\VC\redist\x86\Microsoft.VC90.CRT\*.*'))]
    kwargs['data_files'] = data_files
    kwargs['windows'] = ['bin/viewer']
    # see http://www.py2exe.org/index.cgi/TkInter, http://www.py2exe.org/index.cgi/Py2exeAndPyQt
    # gone all out on the optimisations - don't need docstrings etc
    options = {'py2exe':{'bundle_files' : 3, 'includes':["sip"],
                'excludes':["pywin", "pywin.debugger", "pywin.debugger.dbgcon", "pywin.dialogs", "pywin.dialogs.list",
                "Tkconstants","Tkinter","tcl"], 'optimize':2, 'dist_dir' : distdir}}
    kwargs['options'] = options

# are we building in executeable under Mac OSX?
py2appcmd = len(sys.argv) > 1 and sys.platform == 'darwin' and sys.argv[1] == 'py2app'

if py2appcmd:
    from setuptools import setup
    import shutil
    distdir = 'dist'
    try:
        shutil.rmtree(distdir)
    except:
        pass

    app = ['viewer/viewerapplication.py']
    #app = ['bin/viewer']
    data_files = []
    options = {'py2app':{'argv_emulation': True, 'dist_dir': distdir, 'includes': ['sip']}}

    kwargs['data_files'] = data_files
    kwargs['app'] = app
    kwargs['options'] = options
    kwargs['setup_requires'] = 'py2app'



# now run setup with the options we have collected
print kwargs
setup(**kwargs)

if py2exe:
    # don't need this file
    os.remove(os.path.join(distdir, 'w9xpopen.exe'))
