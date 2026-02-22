"""
Compatibility wrapper for render_queue module.

This module re-exports all symbols from the original gui.viewport.render_queue
to maintain backward compatibility during the mode-first restructuring.

Phase-1 scaffolding - compatibility wrapper.
"""

# Re-export all symbols from the original module
import gui.viewport.render_queue as _orig
from gui.viewport.render_queue import *

# Preserve original module's __all__ if defined, otherwise derive from globals
__all__ = getattr(_orig, "__all__", [n for n in globals() if not n.startswith("_")])
