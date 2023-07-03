#!/usr/bin/env python

import sys
from PyQt5.QtWidgets import QApplication, QFontDialog
from PyQt5.QtGui import QImage, QPainter, QColor, QFontMetrics, QPen
from PyQt5.QtCore import Qt

MIN_ASCII = 33
MAX_ASCII = 126
N_ASCII = (126 - 33) + 1
IN_FONT = '2'
OUT_FONT = '0'

app = QApplication(sys.argv)
dlg = QFontDialog()
dlg.show()

app.exec_()

font = dlg.currentFont()
print(font.family())
print(font.pointSize())
print(font.weight())
fm = QFontMetrics(font)
width = fm.maxWidth()
height = fm.height()
ascent = fm.ascent()
descent = fm.descent()

img = QImage(width, height, QImage.Format_RGB32)

black = QColor(Qt.black)
white = QColor(Qt.white)

painter = QPainter()
pen = QPen(black)

with open('tuifont.h', 'wt') as f:
    f.write('#define FONT_WIDTH {}\n'.format(width))
    f.write('#define FONT_HEIGHT {}\n'.format(height))
    f.write('#define FONT_ASCENT {}\n'.format(ascent))
    f.write('#define FONT_DESCENT {}\n'.format(descent))
    f.write('#define FONT_MIN_ASCII {}\n'.format(MIN_ASCII))
    f.write('#define FONT_MAX_ASCII {}\n\n'.format(MAX_ASCII))
    f.write('uint_8 fontData[{}][FONT_HEIGHT][FONT_WIDTH] = {{\n'.format(N_ASCII))
    for n in range(N_ASCII):
        val = chr(n + MIN_ASCII)
        print(val, end='\r')
        img.fill(white)
        painter.begin(img)
        painter.setFont(font)
        painter.setPen(pen)
        lbear = fm.leftBearing(val)
        painter.drawText(lbear, ascent, val)
        painter.end()
        
        f.write('{')
        for y in range(height):
            f.write('{')
            for x in range(width):
                rgb = img.pixelColor(x, y)
                if rgb.black() > 0:
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
    

