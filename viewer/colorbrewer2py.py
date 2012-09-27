#!/usr/bin/env python

"""
Script for converting spreadsheet downloaded from
colorbrewer2.org to the Python variables that for
the basis of pseudocolor.py
"""

import sys

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
            print "RAMP['%s'] = {'type' : '%s'}" % (name, type)
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
            print "RAMP['%s']['r'] = '%s'" % (name, redstr)
            print "RAMP['%s']['g'] = '%s'" % (name, greenstr)
            print "RAMP['%s']['b'] = '%s'" % (name, bluestr)

if __name__ == '__main__':
    info = readData(sys.argv[1])
    maxinfo = findMaxColors(info)
    emitPythonCode(maxinfo)