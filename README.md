Main Page: [tuiview.org](http://tuiview.org/)

TuiView is a lightweight raster GIS with powerful raster attribute table manipulation abilities. Features of TuiView include:

* "Geo-linking" - 2 or more windows linked so they move and zoom together
* Querying and plotting of raster values
* Overlaying and querying of vector layers
* Ability to stretch data for viewing in a number of ways, and ability to set a default stretch for each type of file
* Saving and loading of stretch information into text or image files
* Profile tool
* Display of raster attribute tables and highlighting of rows for queried pixel
* Selection of raster attribute table rows based on a query, or through geographical selection
* Creation of new attribute table columns and updating of columns
* Flicker tool

# Download #
## Binaries ##

Binaries for Windows, Linux and Mac are available through [Conda](http://conda.pydata.org/index.html) on the "osgeo" channel:

1. Download and [install](http://docs.continuum.io/anaconda/install.html) the Python 3.4 installer for your platform from the [Miniconda](http://conda.pydata.org/miniconda.html#miniconda) site
1. Bring up the command line and type "conda install -c osgeo tuiview"
1. Type "tuiview"
1. To upgrade when a new version is released, type "conda update -c osgeo tuiview"

## Source ##

TuiView requires: Python >= 2.6, Numpy, GDAL and PyQt.
Source available from [Download Page](https://bitbucket.org/chchrsc/tuiview/downloads) or through Mercurial.

# Documentation #

Documentation is available in the [TuiView wiki](https://bitbucket.org/chchrsc/tuiview/wiki)