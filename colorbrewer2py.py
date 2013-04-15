#!/usr/bin/env python

"""
Script for converting spreadsheet downloaded from
colorbrewer2.org to the Python variables that for
the basis of pseudocolor.py
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
import sys

# Fixed metadata for the ColorBrewer color ramps
author = 'Cynthia Brewer'
comments = 'Colours from www.colorbrewer.org by Cynthia A. Brewer, Geography, Pennsylvania State University.'

def readData(fname):
    """
    Reads the data out of the CSV and makes it into
    a dictionary key on name, numcolours and type.
    data is r,g,b tuple
    """
    count = 0
    lastName = None
    lastNumColors = None
    lastType = None
    infoDict = {}

    for line in open(fname):
        if count != 0:
            arr = line.strip().split(',')
            if ''.join(arr) == '':
                break # end of data
            (name, numColors, ua, ub, uc, ud, r, g, b, type) = arr

            if name != '':
                lastName = name
            if numColors != '':
                lastNumColors = numColors
            if type != '':
                lastType = type

            key = '_'.join([lastName, lastNumColors, lastType])
            if key in infoDict:
                infoDict[key].append((r,g,b))
            else:
                infoDict[key] = [(r,g,b)]

        count += 1
    return infoDict

def findMaxColors(infoDict):
    """
    Return same as readData() but only return the entry
    with the maximum number of colours
    """
    maxDict = {}
    for key in infoDict.keys():
        (name, colors, type) = key.split('_')
        colors = int(colors)
        maxKey = '_'.join((name, type))
        if maxKey in maxDict:
            if colors > maxDict[maxKey]:
                maxDict[maxKey] = colors
        else:
            maxDict[maxKey] = colors

    retDict = {}
    for key in maxDict:
        (name, type) = key.split('_')
        colors = maxDict[key]
        infoKey = '_'.join([name, str(colors), type])
        data = infoDict[infoKey]
        retDict[key] = data

    return retDict

def emitPythonCode(infoDict):
    # ones we use , so far
    wantList = ['Blues','Reds','Greys','YlGnBu','YlOrRd',
            'Spectral','RdYlGn','RdYlBu','RdBu']

    for key in sorted(infoDict.keys()):
        (name, type) = key.split('_')
        if name in wantList:
            print "RAMP['%s'] = {'author' : '%s', 'comments' : '%s', 'type' : '%s'}" % (name, author, comments, type)
            # turn r,g,b tuples into list
            redList = []
            greenList = []
            blueList = []
            for (r,g,b) in infoDict[key]:
                redList.append(r)
                greenList.append(g)
                blueList.append(b)
            redstr = ' '.join(redList)
            greenstr = ' '.join(greenList)
            bluestr = ' '.join(blueList)
            print "RAMP['%s']['description'] = {}" % name
            print "RAMP['%s']['description']['red'] = '%s'" % (name, redstr)
            print "RAMP['%s']['description']['green'] = '%s'" % (name, greenstr)
            print "RAMP['%s']['description']['blue'] = '%s'" % (name, bluestr)

if __name__ == '__main__':
    info = readData(sys.argv[1])
    maxinfo = findMaxColors(info)
    emitPythonCode(maxinfo)
