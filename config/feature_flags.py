"""
MashCad - Feature Flags
=======================

Feature Flags ermöglichen inkrementelle Rollouts und einfaches Rollback.
Neue Features werden mit Flag=False eingeführt und nach Validierung aktiviert.

Nach Validierung werden Features als Standard-Code integriert und Flags entfernt.
Diese Datei enthält nur noch aktive Debug-Flags und experimentelle Features.
"""

from typing import Dict

# Feature Flag Registry
# =====================
# HINWEIS: Die meisten Feature-Flags wurden nach erfolgreicher Validierung
# entfernt (Januar 2026). Die entsprechenden Features sind jetzt Standard:
#
# - Kreis-Intersection Fixes (Phase 1)
# - Kreis-Überlappung Profile Detection (Phase 1b)
# - Build123d Profile-Detection (Phase 2)
# - DOF-Anzeige (Phase 3)
# - Extrahierte Trim/Extend/Fillet/Chamfer Operationen (Phase 4)
# - TNP Face-Selection mit Hash (Phase 7)
# - Smart Dimension Entry UX (Phase 8)
#
# Die Flags unten sind für aktives Debugging oder experimentelle Features.

FEATURE_FLAGS: Dict[str, bool] = {
    # Debug-Modi
    "sketch_input_logging": False,  # Detailliertes Sketch-Input Logging

    # UX Features
    "sketch_orientation_indicator": False,  # Zeigt 3D-Orientierung im Sketch-Editor (deaktiviert - Auto-Align löst das Problem)

    # Assembly System (Phase 1-6)
    "assembly_system": True,  # Hierarchische Component-Struktur wie Fusion 360
}


def is_enabled(flag: str) -> bool:
    """
    Prüft ob ein Feature-Flag aktiviert ist.

    Args:
        flag: Name des Feature-Flags

    Returns:
        True wenn aktiviert, False wenn nicht aktiviert oder unbekannt
    """
    return FEATURE_FLAGS.get(flag, False)


def set_flag(flag: str, value: bool) -> None:
    """
    Setzt ein Feature-Flag zur Laufzeit.
    Nützlich für Tests und Debugging.

    Args:
        flag: Name des Feature-Flags
        value: Neuer Wert
    """
    FEATURE_FLAGS[flag] = value


def get_all_flags() -> Dict[str, bool]:
    """Gibt alle Feature-Flags zurück."""
    return FEATURE_FLAGS.copy()
