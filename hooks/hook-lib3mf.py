"""PyInstaller runtime hook: patch lib3mf library discovery for bundled app."""
import os
import sys
import ctypes.util

_original_find_library = ctypes.util.find_library

def _patched_find_library(name):
    if name == "3mf" or name == "lib3mf":
        # In PyInstaller bundle, check _MEIPASS (internal dir)
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            # Primary location: lib3mf subdirectory
            candidates = [
                os.path.join(meipass, 'lib3mf', 'lib3mf.dll'),  # Windows
                os.path.join(meipass, 'lib3mf', 'lib3mf.so'),   # Linux
                os.path.join(meipass, 'Library', 'bin', 'lib3mf.dll'),  # Windows alt
                os.path.join(meipass, 'lib', 'lib3mf.so'),      # Linux alt
                os.path.join(meipass, 'lib3mf.dll'),            # Root Windows
                os.path.join(meipass, 'lib3mf.so'),             # Root Linux
            ]
            for candidate in candidates:
                if os.path.isfile(candidate):
                    return candidate
    return _original_find_library(name)

ctypes.util.find_library = _patched_find_library

# Also patch the lib3mf module's DLL path directly if possible
try:
    import lib3mf
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass and hasattr(lib3mf, '_lib3mf_path'):
        dll_path = os.path.join(meipass, 'lib3mf', 'lib3mf.dll')
        if os.path.isfile(dll_path):
            lib3mf._lib3mf_path = dll_path
except ImportError:
    pass
