"""
Exception classes for use in Viewer
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
class ViewerException(Exception):
    "Base class for all Viewer exceptions"

class InvalidDataset(ViewerException):
    "Dataset was invalid for some reason"

class InvalidParameters(ViewerException):
    "Invalid parameters passed to function"

class InvalidColorTable(ViewerException):
    "A color table was requested but does not exist"

class InvalidStretch(ViewerException):
    "The requested stretch is invalid"

class StatisticsError(ViewerException):
    "Unable to retrieve statistics"

class TypeConversionError(ViewerException):
    "Problem with the type of the dataset"

class AttributeTableTypeError(ViewerException):
    "Problem with the type of attribute"

class UserExpressionError(ViewerException):
    "A problem was encountered in user supplies code"

class UserExpressionSyntaxError(UserExpressionError):
    "Syntax error in user supplied code"

class UserExpressionTypeError(UserExpressionError):
    "The result of user supplied code was the wrong type"
