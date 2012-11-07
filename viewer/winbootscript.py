"""
Custom boot stript for py2exe
Sets the GDAL_DATA variable to point to the 'data' subdirectory
of where we are running
"""
import os
import sys
appDir = os.path.dirname(os.path.abspath(sys.argv[0]))
dataDir = os.path.join(appDir, 'data')

os.putenv('GDAL_DATA', dataDir)
