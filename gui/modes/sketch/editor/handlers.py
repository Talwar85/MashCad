"""
Compatibility wrapper for sketch_handlers module.

This module re-exports all symbols from the original gui.sketch_handlers
to maintain backward compatibility during the mode-first restructuring.

Phase-1 scaffolding - compatibility wrapper.
"""

# Re-export all symbols from the original module
import gui.sketch_handlers as _orig
from gui.sketch_handlers import *

# Preserve original module's __all__ if defined, otherwise derive from globals
__all__ = getattr(_orig, "__all__", [n for n in globals() if not n.startswith("_")])
