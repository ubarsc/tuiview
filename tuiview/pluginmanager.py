
"""
Contains the PluginManager class.
"""
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

from __future__ import print_function
import os
import sys
import imp

PLUGINS_ENV = 'TUIVIEW_PLUGINS_PATH'
PLUGINS_SUBDIR = 'plugins'

PLUGIN_NAME_FN = 'name'
PLUGIN_ACTION_FN = 'action'
PLUGIN_AUTHOR_FN = 'author'

PLUGIN_REQUIRED_FNS = (PLUGIN_NAME_FN, PLUGIN_ACTION_FN, PLUGIN_AUTHOR_FN)

PLUGIN_ACTION_INIT = 0
PLUGIN_ACTION_NEWVIEWER = 1
PLUGIN_ACTION_NEWQUERY = 2

class PluginManager(object):
    def __init__(self):
        self.plugins = {}
        self.pysuffixes = self.getSuffixes()
        self.pluginNameIndex = 1

    def callAction(self, actioncode, param):
        """
        Calls PLUGIN_ACTION_FN on each of the loaded plugins
        with the supplit PLUGIN_ACTION_* constant and a parameter
        """
        for name in self.plugins.keys():
            mod = self.plugins[name]
            try:
                action = getattr(mod, PLUGIN_ACTION_FN)
                action(actioncode, param)
            except Exception as e:
                self.printTraceback(mod)

    @staticmethod
    def printTraceback(name):
        import traceback
        print('Exception raised when calling plugin %s:' % name)
        (ttype, value, tb) = sys.exc_info()
        stack = traceback.extract_tb(tb)
        trace = '\n'.join(traceback.format_list(stack))
        print(trace, ttype.__name__, ':', value)

    @staticmethod
    def getSuffixes():
        suffixes = None
        for (suffix, mode, type) in imp.get_suffixes():
            if type == imp.PY_SOURCE:
                suffixes = (suffix, mode, type)
                break

        if suffixes is None:
            raise ValueError('Unable to find suffix for Python source')
        return suffixes

    def loadPlugins(self):
        """
        Order is:
        1. If there is a plugins directory under where we are running
        2. Any directories listed in os.getenv(PLUGINS_ENV)
        3. Under ~/.tuiview/plugins
        Reads any Python file that has the required entries
        """
        # check where we are running
        appDir = os.path.dirname(os.path.abspath(sys.argv[0]))
        subdir = os.path.join(appDir, PLUGINS_SUBDIR)
        if os.path.isdir(subdir):
            self.loadPluginsFromDir(subdir)

        # now do the environment variable
        pluginPath = os.getenv(PLUGINS_ENV)
        if pluginPath is not None:
            for subdir in pluginPath.split(os.pathsep):
                if os.path.isdir(subdir):
                    self.loadPluginsFromDir(subdir)

        # now home directory
        homeDir = os.path.expanduser('~')
        subdir = os.path.join(homeDir, '.tuiview', PLUGINS_SUBDIR)
        if os.path.isdir(subdir):
            self.loadPluginsFromDir(subdir)

    def loadPluginsFromDir(self, directory):
        """
        Attempt to load all the files in the given 
        directory that match the Python suffix (.py)
        """
        for fname in os.listdir(directory):
            if fname.endswith(self.pysuffixes[0]):
                path = os.path.join(directory, fname)
                self.loadPluginFromPath(path)

    def loadPluginFromPath(self, path):
        """
        Try loading a plugin given a path to it. Module
        put into self.plugins with the key being the name
        the module describes itself as
        """
        try:
            fileobj = open(path, self.pysuffixes[1])

            # make up a name to keep Python happy
            name = 'tuiview.plugin%d' % self.pluginNameIndex
            self.pluginNameIndex += 1

            try:
                mod = imp.load_module(name, fileobj, path, self.pysuffixes)
                # all required fns?
                for fn in PLUGIN_REQUIRED_FNS:
                    if not hasattr(mod, fn):
                        msg = 'Plugin %s does not have required functions'
                        print(msg % path)
                        return

                # must be ok. Get name and save it
                try:
                    name = getattr(mod, PLUGIN_NAME_FN)
                    modname = name()
                except Exception as e:
                    self.printTraceback(modname)
                    return
                self.plugins[modname] = mod
                print('loaded plugin %s' % modname)
            except ImportError:
                print('Unable to import %s' % path)
            finally:
                fileobj.close()

        except IOError:
            print('Unable to read %s' % path)



