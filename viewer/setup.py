#!/usr/bin/env python
"""
"""
from distutils.core import setup

setup(name='viewer',
      version='0.1',
      description='Simple Raster Viewer',
      author='Sam Gillingham',
      author_email='gillingham.sam@gmail.com',
      scripts=['bin/viewer'],
      packages=['viewer'],
      license='LICENSE.txt', 
      url='https://bitbucket.org/chchrsc/viewer'
     )
