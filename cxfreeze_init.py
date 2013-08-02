#------------------------------------------------------------------------------
# cxfreeze_init.py. 
# Modified from Console3.py to set $GDAL_DATA
#   Initialization script for cx_Freeze which manipulates the path so that the
# directory in which the executable is found is searched for extensions but
# no other directory is searched. It also sets the attribute sys.frozen so that
# the Win32 extensions behave as expected.
#------------------------------------------------------------------------------

import os
import sys
import zipimport

appDir = os.path.dirname(os.path.abspath(sys.argv[0]))
dataDir = os.path.join(appDir, 'data')

# so we get access to the coordinate info
os.putenv('GDAL_DATA', dataDir)

# often Windows users have %GDAL_DRIVER_PATH% 
# set for some incompatible version for GDAL
# only honour %TUIVIEW_DRIVER_PATH% and unset %GDAL_DRIVER_PATH%
if 'TUIVIEW_DRIVER_PATH' in os.environ:
    tdp = os.environ['TUIVIEW_DRIVER_PATH']
    os.environ['GDAL_DRIVER_PATH'] = tpd
elif 'GDAL_DRIVER_PATH' in os.environ:
    del os.environ['GDAL_DRIVER_PATH']

sys.frozen = True
sys.path = sys.path[:4]

os.environ["TCL_LIBRARY"] = os.path.join(DIR_NAME, "tcl")
os.environ["TK_LIBRARY"] = os.path.join(DIR_NAME, "tk")

m = __import__("__main__")
importer = zipimport.zipimporter(INITSCRIPT_ZIP_FILE_NAME)
if INITSCRIPT_ZIP_FILE_NAME != SHARED_ZIP_FILE_NAME:
    moduleName = m.__name__
else:
    name, ext = os.path.splitext(os.path.basename(os.path.normcase(FILE_NAME)))
    moduleName = "%s__main__" % name
code = importer.get_code(moduleName)
exec(code, m.__dict__)

