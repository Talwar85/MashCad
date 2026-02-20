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
    "tnp_debug_logging": False,  # TNP v4.0 Shape-Tracking Debug (sehr verbose, nur in Tests aktivieren)
    "sketch_debug": False,  # Sketch-Editor Debug ([Orientation], [PROFILE], [Auto-Align])
    "extrude_debug": False,  # Extrude Operation Debug ([EXTRUDE DEBUG], [SELECTOR])
    "viewport_debug": False,  # Viewport/Mesh Debug (Mesh regeneration, Actors)

    # UX Features
    "sketch_orientation_indicator": False,  # Zeigt 3D-Orientierung im Sketch-Editor (deaktiviert - Auto-Align löst das Problem)

    # Assembly System (Phase 1-6)
    "assembly_system": True,  # Hierarchische Component-Struktur wie CAD
    "mate_system_v1": True,  # AS-002: Mate constraints between components
    "mate_solver": True,  # AS-003: Mate-Solver Base Kernel for assembly constraint solving

    # Performance Optimizations (2026 Performance Plan)
    "optimized_actor_pooling": True,  # Phase 2: VTK Actor Pooling Optimierung
    "reuse_hover_markers": True,  # Phase 3: Hover-Marker wiederverwenden
    "picker_pooling": True,  # Phase 4: Picker-Pool statt neu erstellen
    "bbox_early_rejection": True,  # Phase 5: BBox Check vor Boolean-Ops (PERMANENT)
    "export_cache": True,  # Phase 6: Tessellation-Cache für STL Export
    "feature_dependency_tracking": True,  # Phase 7: Feature Dependency Graph
    "feature_solid_caching": True,  # Phase 8: In Phase 7 integriert (_solid_checkpoints)
    "async_tessellation": True,  # Phase 9: Background Mesh Generation
    # Phase 10: BooleanEngineV4 ist jetzt STANDARD - kein Flag mehr nötig
    "ocp_advanced_flags": True,  # Phase 11: SetFuzzyValue + SetRunParallel (AKTIV)
    "ocp_glue_auto_detect": True,  # Auto-Erkennung von coinciding Faces → GlueShift für ~90% Speedup
    "batch_fillets": True,  # Phase 12: Fillet/Chamfer History-Extraction für TNP
    "wall_thickness_analysis": True,  # Phase 13: BRepExtrema Wandstärken-Analyse (AKTIV)
    "self_heal_strict": True,  # Strict: atomischer Rollback bei invalider Geometrie statt stiller Weiterverarbeitung
    # PI-003: Wenn Topologie-Referenzen vorhanden sind, kein Geometric-Selector-Recovery.
    # Verhindert stilles "falsches" Recovery bei TNP-Mismatch.
    "strict_topology_fallback_policy": True,

    # Boolean Robustness (OCP Feature Audit 2026)
    "boolean_self_intersection_check": True,  # Pre-Check: BOPAlgo_CheckerSI vor Booleans
    "boolean_post_validation": True,  # Post-Check: BRepCheck_Analyzer + ShapeFix nach Booleans
    "boolean_argument_analyzer": True,  # Pre-Check: BOPAlgo_ArgumentAnalyzer Input-Validierung
    "adaptive_tessellation": True,  # Deflection proportional zur Modellgröße
    
    # Export Formats (PR-001: 3MF Export)
    "export_3mf": True,  # 3MF Export Implementation
    
    # Export Validation (PR-002: Manifold/Free-Bounds Pflichtcheck)
    "export_free_bounds_check": True,  # Offene-Kanten-Check vor STL Export (G4 Printability)
    "export_normals_check": False,  # Normalen-Konsistenz-Check (optional, performance-intensiv)
    "export_auto_repair": True,  # Auto-Repair Integration mit GeometryHealer
    
    # PR-010: Printability Trust Gate
    "printability_trust_gate": True,  # Printability-Validierung vor Export
    "printability_min_score": 60,  # Mindest-Score für Export (0-100)
    "printability_block_on_critical": True,  # Export bei CRITICAL Issues blockieren
    
    "boolean_tolerance_monitoring": True,  # Post-Check: ShapeAnalysis_ShapeTolerance nach Booleans

    # OCP Feature Audit Tier 3
    "mesh_converter_adaptive_tolerance": True,  # Adaptive Sewing-Toleranz + Post-Sewing Validation
    "loft_sweep_hardening": True,  # SetMaxDegree + MakePipeShell Fallback für Loft/Sweep

    # Thread/Helix (Native OCP)
    "native_ocp_helix": True,  # Native Geom_CylindricalSurface Helix statt build123d BSpline-Approximation

    # Cylindrical Face Edit (Fusion360-style Radius Edit)
    "cylindrical_face_edit": False,  # Phase 1: Zylindrische Faces radius-modifizieren (Hole/Pocket/Solid)

    # OCP-First Migration (2026 CAD Kernel Nearness Plan)
    # ======================================================
    # Phase A-E (Feb 2026): OCP-First komplett abgeschlossen
    # - Revolve: Direktes OCP BRepPrimAPI_MakeRevol (Phase C)
    # - Loft: Direktes OCP BRepOffsetAPI_ThruSections (Phase D)
    # - Sweep: Direktes OCP BRepOffsetAPI_MakePipe/MakePipeShell (Phase E)
    # - Shell/Hollow: Direktes OCP BRepOffsetAPI_MakeThickSolid (Phase F)
    # - Fillet, Chamfer: OCP-First Helper ohne Fallback-Kaskade (Phase B)
    # - ocp_first_revolve, loft, sweep, shell, hollow entfernt (Phase A)
    # - ocp_first_fillet, chamfer entfernt (Phase B)
    #
    # Verbleibendes Flag:
    # - ocp_first_extrude: OCPExtrudeHelper (mit TNP)
    #
    # Nach Abschluss aller Phasen wird auch ocp_first_extrude entfernt.

    # Phase 2-3: Extrude (OCP-First mit Helper-Klasse)
    "ocp_first_extrude": True,

    # Phase 7: BREP Caching
    "ocp_brep_cache": True,

    # Phase 8: Incremental Rebuild
    "ocp_incremental_rebuild": True,

    # Phase 9: BREP Persistence
    "ocp_brep_persistence": True,
    
    # W35: Solver Stabilization (P0-P4)
    "solver_backend": "staged",  # Options: "scipy_lm", "scipy_trf", "staged"
    "solver_pre_validation": True,  # P1: Early contradiction detection
    "solver_smooth_penalties": True,  # P1: Smooth tangent penalties
    "solver_experimental_staged": True,  # P3: Staged solve (experimental)
    
    # SU-005: Sketch Drag Performance Optimization (60 FPS target)
    "sketch_drag_optimization": True,  # Enable throttled solver updates during drag
    "sketch_solver_throttle_ms": 16,  # Minimum ms between solver calls (60 FPS = 16ms)
    "sketch_performance_monitoring": False,  # Enable performance stats collection (debug)
    
    # QA-006: Performance Regression Gate
    "performance_regression_gate": True,  # Enable performance benchmarking and regression detection
    
    # PI-006: Rollback Consistency Validation
    "rollback_validation": True,  # Enable rollback state validation and orphan detection
    
    # UX-001: First-Run Guided Flow
    "first_run_tutorial": True,  # Enable5-step guided tutorial for new users
}


def is_enabled(flag: str) -> bool:
    """
    Prüft ob ein Feature-Flag aktiviert ist.
    
    WICHTIG: Für OCP-First Flags:
    - Default = False (alter Build123d Code)
    - Nach Validierung = True (neuer OCP Code)
    - Kein dauerhafter Fallback! Flags werden nach Validierung entfernt.
    - TNP Integration ist in beiden Pfaden obligatorisch!
    
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


# Alias for set_flag (CH-006 compatibility)
def set_enabled(flag: str, value: bool) -> None:
    """
    Alias for set_flag - sets a feature flag at runtime.
    
    Args:
        flag: Name of the feature flag
        value: New value
    """
    set_flag(flag, value)


def get_all_flags() -> Dict[str, bool]:
    """Gibt alle Feature-Flags zurück."""
    return FEATURE_FLAGS.copy()
