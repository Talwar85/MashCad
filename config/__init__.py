"""
MashCad - Configuration Module
==============================

Zentrale Konfiguration für alle globalen Einstellungen.
"""

from .tolerances import Tolerances, kernel_tolerance, mesh_tolerance, sketch_tolerance
from .feature_flags import is_enabled, set_flag, get_all_flags, FEATURE_FLAGS
