"""PyInstaller runtime hook: patch lib3mf library discovery for bundled app."""
import os
import sys
import ctypes.util

_original_find_library = ctypes.util.find_library

def _patched_find_library(name):
    if name == "3mf":
        # In PyInstaller bundle, check _MEIPASS (internal dir)
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            candidate = os.path.join(meipass, 'Library', 'bin', 'lib3mf.dll')
            if os.path.isfile(candidate):
                return candidate
    return _original_find_library(name)

ctypes.util.find_library = _patched_find_library
