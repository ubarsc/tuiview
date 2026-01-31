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

Binaries for Windows, Linux and Mac are available through [Conda](http://conda.pydata.org/index.html) on the "conda-forge" channel:

1. Download and [install](http://docs.continuum.io/anaconda/install.html) the Python 3.5 installer for your platform from the [Miniconda](http://conda.pydata.org/miniconda.html#miniconda) site and type the following commands on the command line.
1. conda config --add channels conda-forge
1. conda create -n myenv tuiview
1. source activate myenv # omit 'source' on Windows

## Source ##

TuiView requires: Python >= 3.6, Numpy, GDAL and PySide.
Source available from [Download Page](https://github.com/ubarsc/tuiview/releases) or through git.

# Documentation #

Blog Posts are being made about aspects of using TuiView:
- [Opening files and Tiling viewers with TuiView](https://ubarsc.github.io/tutorial/2026/01/07/tuiview-intro.html)
- [Querying Continuous Raster Layers and Vectors with TuiView](https://ubarsc.github.io/tutorial/2026/01/16/tuiview-query.html)
- [Querying Raster Layers with Raster Attribute Tables](https://ubarsc.github.io/tutorial/2026/01/21/tuiview-ratquery.html)
- [Exploring TuiView plugins and developing your own](https://ubarsc.github.io/tutorial/2026/01/26/tuiview-plugins.html)

Further documentation is available in the [TuiView wiki](https://github.com/ubarsc/tuiview/wiki)
