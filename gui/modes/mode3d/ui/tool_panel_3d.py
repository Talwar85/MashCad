"""
Compatibility wrapper for tool_panel_3d module.

This module re-exports all symbols from the original gui.tool_panel_3d
to maintain backward compatibility during the mode-first restructuring.

Phase-1 scaffolding - compatibility wrapper.
"""

# Re-export all symbols from the original module
import gui.tool_panel_3d as _orig
from gui.tool_panel_3d import *

# Preserve original module's __all__ if defined, otherwise derive from globals
__all__ = getattr(_orig, "__all__", [n for n in globals() if not n.startswith("_")])
