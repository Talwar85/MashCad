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
# - ShapeUpgrade_UnifySameDomain (Phase 14) - aktiv in Rebuild-Pipeline
#
# Nicht umsetzbar (entfernt):
# - parallel_rebuild (Phase 15) - OCP/OpenCASCADE ist nicht thread-safe
#
# Die Flags unten sind für aktives Debugging oder experimentelle Features.

FEATURE_FLAGS: Dict[str, bool] = {
    # Debug-Modi
    "sketch_input_logging": False,  # Detailliertes Sketch-Input Logging
    "tnp_debug_logging": False,  # TNP v4.0 Shape-Tracking Debug (sehr verbose!)
    "sketch_debug": False,  # Sketch-Editor Debug ([Orientation], [PROFILE], [Auto-Align])
    "extrude_debug": False,  # Extrude Operation Debug ([EXTRUDE DEBUG], [SELECTOR])
    "viewport_debug": False,  # Viewport/Mesh Debug (Mesh regeneration, Actors)

    # UX Features
    "sketch_orientation_indicator": False,  # Zeigt 3D-Orientierung im Sketch-Editor (deaktiviert - Auto-Align löst das Problem)

    # Assembly System (Phase 1-6)
    "assembly_system": True,  # Hierarchische Component-Struktur wie CAD

    # Performance Optimizations (2026 Performance Plan)
    "optimized_actor_pooling": True,  # Phase 2: VTK Actor Pooling Optimierung
    "reuse_hover_markers": True,  # Phase 3: Hover-Marker wiederverwenden
    "picker_pooling": True,  # Phase 4: Picker-Pool statt neu erstellen
    "bbox_early_rejection": True,  # Phase 5: BBox Check vor Boolean-Ops (PERMANENT)
    "export_cache": True,  # Phase 6: Tessellation-Cache für STL Export
    "feature_dependency_tracking": True,  # Phase 7: Feature Dependency Graph
    "feature_solid_caching": True,  # Phase 8: In Phase 7 integriert (_solid_checkpoints)
    "async_tessellation": False,  # Phase 9: Background Mesh Generation (TODO)
    # Phase 10: BooleanEngineV4 ist jetzt STANDARD - kein Flag mehr nötig
    "ocp_advanced_flags": True,  # Phase 11: SetFuzzyValue + SetRunParallel (AKTIV)
    "ocp_glue_mode": False,  # Phase 11: SetGlue() - VERBOTEN (erzeugt kaputte Topologie, TNP kann nicht reparieren)
    "batch_fillets": False,  # Phase 12: BOPAlgo_Builder für Batch-Fillets (TODO - bei vielen Fillets)
    "wall_thickness_analysis": True,  # Phase 13: BRepExtrema Wandstärken-Analyse (AKTIV)

    # Boolean Robustness (OCP Feature Audit 2026)
    "boolean_self_intersection_check": True,  # Pre-Check: BOPAlgo_CheckerSI vor Booleans
    "boolean_post_validation": True,  # Post-Check: BRepCheck_Analyzer + ShapeFix nach Booleans
    "boolean_argument_analyzer": True,  # Pre-Check: BOPAlgo_ArgumentAnalyzer Input-Validierung
    "adaptive_tessellation": True,  # Deflection proportional zur Modellgröße
    "export_free_bounds_check": True,  # Offene-Kanten-Check vor STL Export
    "boolean_tolerance_monitoring": True,  # Post-Check: ShapeAnalysis_ShapeTolerance nach Booleans
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
