"""
MashCad - Feature Flags
=======================

Feature Flags ermöglichen inkrementelle Rollouts und einfaches Rollback.
Neue Features werden mit Flag=False eingeführt und nach Validierung aktiviert.
"""

from typing import Dict

# Feature Flag Registry
FEATURE_FLAGS: Dict[str, bool] = {
    # Phase 1: Kreis-Intersection Fixes
    "use_robust_circle_intersection": True,  # Toleranz-basierte Kreis-Kreis Intersection

    # Phase 1b: Kreis-Überlappung Profile Detection
    "use_circle_overlap_profiles": True,  # Überlappende Kreise als 3 Flächen erkennen

    # Phase 2: Build123d Profile-Detection für Extrude
    "use_build123d_profiles": False,  # DEAKTIVIERT - Shapely+GeometryMapping funktioniert besser

    # Phase 3: DOF-Anzeige
    "use_dof_display": True,  # Zeigt Freiheitsgrade im Sketch-Modus

    # Phase 4: Extrahierte Module (noch nicht implementiert)
    "use_extracted_profile_detector": False,
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
