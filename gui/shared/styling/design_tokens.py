"""
Compatibility wrapper for design_tokens module.

This module re-exports all symbols from the original gui.design_tokens
to maintain backward compatibility during the mode-first restructuring.

Phase-1 scaffolding - compatibility wrapper.
"""

# Re-export all symbols from the original module
import gui.design_tokens as _orig
from gui.design_tokens import *

# Preserve original module's __all__ if defined, otherwise derive from globals
__all__ = getattr(_orig, "__all__", [n for n in globals() if not n.startswith("_")])
