"""
MashCad - Configuration Module
==============================

Zentrale Konfiguration für alle globalen Einstellungen.
"""

from .tolerances import Tolerances, kernel_tolerance, mesh_tolerance, sketch_tolerance
from .feature_flags import (
    is_enabled,
    get_setting,
    set_flag,
    set_setting,
    get_all_flags,
    get_all_settings,
    FEATURE_FLAGS,
    FEATURE_SETTINGS,
)
