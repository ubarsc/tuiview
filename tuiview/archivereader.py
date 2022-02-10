"""
Check if file within a zip archive and return apropriate GDAL path if so.

See GDAL documentation on reading files within a zip archive.

http://trac.osgeo.org/gdal/wiki/UserDocs/ReadInZip
"""
# This file is part of 'TuiView' - a simple Raster viewer
# Copyright (C) 2012  Sam Gillingham
#
# archivereader.py written by Terry Cain (2014), Plymouth Marine Laboratory 
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

import zipfile

ALLOWED_FILE_EXTENSIONS = ('.bil', '.bsq', '.bin', '.env', '.dem', '.tif', '.asc', '.img')


def file_list_to_archive_strings(filenames):
    """
    Modifies any archive filenames in the list to allow them to be opened using a GDAL virtual filesystem.

    :param filenames: A list of filenames
    :type filenames: list of str

    :return: The list of filenames passed in, with any supported archive prepended with the appropriate string.
    :rtype: list of str
    """
    output_filename_list = []

    for filename in filenames:
        if filename.endswith('.gz') and filename.find(".tar.gz") == -1:  # can process gz files but opening tar files in python (tarfile) takes ages
            output_filename_list.append(gz_to_file(filename))
        elif filename.endswith('.zip'):
            output_filename_list.extend(zip_to_file(filename))
        else:
            output_filename_list.append(filename)

    return output_filename_list


def gz_to_file(filepath):
    """
    Converts a path ending in .gz so that it can be opened with GDAL

    :param filepath: Filepath ending in .gz
    :type filepath: str

    :return: Filepath prepended with gzip virtual filesystem string
    :rtype: str
    """
    return "/vsigzip/" + filepath


def zip_to_file(filepath):
    """
    Takes in a zip filepath and if the zip contains files that can be opened with GDAL then the filepath will be converted
    so that it can be opened without extraction.

    :param filepath: Filepath ending in .zip
    :type filepath: str

    :return: A list of files prepended with the zip virtual filesystem string
    :rtype: list of str
    """
    zip_file_list = []
    if zipfile.is_zipfile(filepath):
        try:
            zip_file = zipfile.ZipFile(filepath)
            zip_file_contents = ['/vsizip/{0}/{1}'.format(filepath, zip_info_object.filename) for zip_info_object in zip_file.filelist if zip_info_object.filename.endswith(ALLOWED_FILE_EXTENSIONS)]
            zip_file_list.extend(zip_file_contents)
            zip_file.close()
        except zipfile.BadZipfile:
            pass

    return zip_file_list

