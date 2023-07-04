#!/usr/bin/env python

# This file is part of 'TuiView' - a simple Raster viewer
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
import argparse
from PyQt5.QtWidgets import QApplication, QFontDialog
from PyQt5.QtGui import QImage, QPainter, QColor, QFontMetrics, QPen, QFont
from PyQt5.QtCore import Qt

MIN_ASCII = 33
MAX_ASCII = 126
N_ASCII = (126 - 33) + 1
IN_FONT = '2'
OUT_FONT = '0'
DFLT_OUTPATH = 'src/tuifont.h'
DFLT_THRESHOLD = 100

def getCmdArgs():
    """
    Get the command line params
    """
    parser = argparse.ArgumentParser(
            description='Generate find bitmaps for TuiView',
            epilog="Run with no args to use Font chooser dialog")
    parser.add_argument('--family', help="Font family name")
    parser.add_argument('--pointsize', type=int, help="Font size")
    parser.add_argument('--weight', type=int, help="Font weight")
    parser.add_argument('--italic', default=False, action="store_true",
            help="Specify if font is Italic")
    parser.add_argument('--outpath', default=DFLT_OUTPATH,
            help="output file to write (default=%(default)s)")
    parser.add_argument('--threshold', default=DFLT_THRESHOLD, type=int, 
            help="threshold to use when removing anti " +
                "aliasing (default=%(default)s)")
            
    cmdargs = parser.parse_args()
    fontargs = [cmdargs.family, cmdargs.pointsize, cmdargs.weight]
    fontargsSet = [x is not None for x in fontargs]
    if any(fontargsSet) and not all(fontargsSet):
        raise SystemExit('If one of --family/--pointsize/--weight ' +
                'set, all must be specified')
    return cmdargs
    

def main(cmdargs):
    """
    Main function
    """
    app = QApplication(sys.argv)
    
    if cmdargs.family is None:
        font, ok = QFontDialog.getFont()
        if not ok:
            return
    else:
        font = QFont(cmdargs.family, cmdargs.pointsize, cmdargs.weight, 
                cmdargs.italic)
        
    fm = QFontMetrics(font)
    height = fm.height()
    ascent = fm.ascent()
    descent = fm.descent()
    
    black = QColor(Qt.black)
    white = QColor(Qt.white)
    
    painter = QPainter()
    pen = QPen(black)
    
    with open(cmdargs.outpath, 'wt') as f:
        f.write('#ifndef TUIFONT_H\n')
        f.write('#define TUIFONT_H\n\n')
        f.write('#define FONT_FAMILY "{}"\n'.format(font.family()))
        f.write('#define FONT_POINTSIZE {}\n'.format(font.pointSize()))
        f.write('#define FONT_WEIGHT {}\n'.format(font.weight()))
        f.write('#define FONT_ITALIC {}\n'.format(1 if font.italic() else 0))
        f.write('#define FONT_THRESHOLD {}\n'.format(cmdargs.threshold))
        f.write('#define FONT_SPACE_ADVANCE {}\n'.format(fm.horizontalAdvance(' ')))
        f.write('#define FONT_HEIGHT {}\n'.format(height))
        f.write('#define FONT_ASCENT {}\n'.format(ascent))
        f.write('#define FONT_DESCENT {}\n'.format(descent))
        f.write('#define FONT_MIN_ASCII {}\n'.format(MIN_ASCII))
        f.write('#define FONT_MAX_ASCII {}\n\n'.format(MAX_ASCII))
        
        f.write('struct TuiFontInfo {uint8_t left; uint8_t adv; uint8_t right;};\n')
        f.write('struct TuiFontInfo fontInfo[] = {\n')
        # loop through to get maximums
        maxLeftBearing = 0
        maxRightBearing = 0
        maxAdvance = 0
        for n in range(N_ASCII):
            val = chr(n + MIN_ASCII)
            leftBearing = fm.leftBearing(val)
            # only interested in negative values - they extend outside of horizontalAdvance
            if leftBearing < 0:
                leftBearing = abs(leftBearing)
                if leftBearing > maxLeftBearing:
                    maxLeftBearing = leftBearing
                
            rightBearing = fm.rightBearing(val)
            if rightBearing < 0:
                rightBearing = abs(rightBearing)
                if rightBearing > maxRightBearing:
                    maxRightBearing = rightBearing
                
            advance = fm.horizontalAdvance(val)
            if advance > maxAdvance:
                maxAdvance = advance
            f.write('{{ {}, {}, {} }} /* {} */'.format(leftBearing, 
                    advance, rightBearing, val))
            if n != (N_ASCII - 1):
                f.write(',')
            f.write('\n')
        f.write('};\n')
            
        # fm.width() seems to return a very high number
        width = maxLeftBearing + maxAdvance + maxRightBearing

        f.write('#define FONT_WIDTH {}\n'.format(width))
        f.write('#define FONT_MAX_LEFT_BEARING {}\n\n'.format(maxLeftBearing))

        img = QImage(width, height, QImage.Format_RGB32)
        
        f.write('uint8_t fontData[{}][FONT_HEIGHT][FONT_WIDTH] = {{\n'.format(N_ASCII))
        for n in range(N_ASCII):
            val = chr(n + MIN_ASCII)
            print(val, end='\r')
            img.fill(white)
            painter.begin(img)
            painter.setFont(font)
            painter.setPen(pen)
            painter.drawText(maxLeftBearing, ascent, val)
            painter.end()
            
            f.write('{')
            for y in range(height):
                f.write('{')
                for x in range(width):
                    rgb = img.pixelColor(x, y)
                    if rgb.black() > cmdargs.threshold:
                        f.write(IN_FONT)
                    else:
                        f.write(OUT_FONT)
                        
                    if x != (width - 1):
                        f.write(',')
                f.write('}')
                if y != (height - 1):
                    f.write(',')
                if y == 0:
                    f.write('  /* {} */'.format(val))
                    
                f.write('\n')
                        
            f.write('}')
            if n != (N_ASCII - 1):
                f.write(',')
            f.write('\n')
        
        f.write('};\n')
        f.write('#endif\n')
    
if __name__ == '__main__':
    cmdargs = getCmdArgs()
    main(cmdargs)

