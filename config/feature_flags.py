"""
MashCad - Feature Flags
=======================

Feature Flags ermöglichen inkrementelle Rollouts und einfaches Rollback.
Neue Features werden mit Flag=False eingeführt und nach Validierung aktiviert.

Nach Validierung werden Features als Standard-Code integriert und Flags entfernt.
Diese Datei enthält nur noch aktive Debug-Flags und experimentelle Features.

Bereits integrierte Features (Flags entfernt):
==============================================
Phase 1-3 (Performance & Boolean):
- optimized_actor_pooling, reuse_hover_markers, picker_pooling
- bbox_early_rejection, export_cache, async_tessellation
- feature_dependency_tracking, feature_solid_caching
- boolean_self_intersection_check, boolean_post_validation
- boolean_argument_analyzer, boolean_tolerance_monitoring
- ocp_glue_auto_detect, adaptive_tessellation

Phase 4 (OCP-First Migration):
- ocp_first_extrude, ocp_brep_cache
- ocp_incremental_rebuild, ocp_brep_persistence

Phase 5 (Core Features):
- assembly_system, batch_fillets, native_ocp_helix

Weitere entfernte Flags:
- parallel_rebuild (OCP/OpenCASCADE ist nicht thread-safe)
- use_solver_constraints, solver_visual_feedback, etc. (nicht implementiert)
"""

from typing import Dict

# Feature Flag Registry
# =====================
# Nur noch Debug-Flags und experimentelle Features.

FEATURE_FLAGS: Dict[str, bool] = {
    # ========================================================================
    # Debug-Modi (für development/troubleshooting)
    # ========================================================================
    "sketch_input_logging": False,  # Detailliertes Sketch-Input Logging
    "tnp_debug_logging": False,  # TNP v4.0 Shape-Tracking Debug (sehr verbose)
    "sketch_debug": False,  # Sketch-editor Debug ([Orientation], [PROFILE])
    "extrude_debug": False,  # Extrude Operation Debug ([EXTRUDE DEBUG])
    "viewport_debug": False,  # Viewport/Mesh Debug (Mesh regeneration)
    "sketch_performance_monitoring": False,  # Performance stats collection
    
    # ========================================================================
    # UX Features
    # ========================================================================
    "sketch_orientation_indicator": False,  # 3D-Orientierung im Sketch-Editor
    
    # ========================================================================
    # Assembly System (Phase 1-6) - Permanent aktiviert
    # ========================================================================
    "mate_system_v1": True,  # AS-002: Mate constraints between components
    "mate_solver": True,  # AS-003: Mate-Solver Base Kernel
    
    # ========================================================================
    # Export Formats (PR-001: 3MF Export)
    # ========================================================================
    "export_3mf": True,  # 3MF Export Implementation
    
    # ========================================================================
    # Export Validation (PR-002)
    # ========================================================================
    "export_free_bounds_check": True,  # Offene-Kanten-Check vor STL Export
    "export_normals_check": False,  # Normalen-Konsistenz-Check (optional)
    "export_auto_repair": True,  # Auto-Repair Integration
    
    # ========================================================================
    # Geometry & Printability
    # ========================================================================
    "geometry_drift_detection": True,  # Early detection of numerical errors
    "printability_trust_gate": True,  # Printability-Validierung vor Export
    "printability_min_score": 60,  # Mindest-Score für Export (0-100)
    "printability_block_on_critical": True,  # Export bei CRITICAL Issues blockieren
    
    # ========================================================================
    # OCP Advanced Features
    # ========================================================================
    "ocp_advanced_flags": True,  # SetFuzzyValue + SetRunParallel
    "wall_thickness_analysis": True,  # BRepExtrema Wandstärken-Analyse
    "self_heal_strict": True,  # Atomischer Rollback bei invalider Geometrie
    "strict_topology_fallback_policy": True,  # Kein Geometric-Selector-Recovery bei TNP-Mismatch
    "mesh_converter_adaptive_tolerance": True,  # Adaptive Sewing-Toleranz
    "loft_sweep_hardening": True,  # SetMaxDegree + MakePipeShell Fallback
    "detailed_boolean_history": True,  # Enhanced Boolean history for TNP
    "helix_fitting_enabled": True,  # Helix parameter fitting via scipy
    
    # ========================================================================
    # Solver Configuration (W35: Stabilization P0-P4)
    # ========================================================================
    "solver_backend": "staged",  # Options: "scipy_lm", "scipy_trf", "staged"
    "solver_pre_validation": True,  # P1: Early contradiction detection
    "solver_smooth_penalties": True,  # P1: Smooth tangent penalties
    "solver_experimental_staged": True,  # P3: Staged solve (experimental)
    
    # ========================================================================
    # Sketch Performance (SU-005: 60 FPS target)
    # ========================================================================
    "sketch_drag_optimization": True,  # Throttled solver updates during drag
    "sketch_solver_throttle_ms": 16,  # Minimum ms between solver calls
    "incremental_solver": True,  # W35 P4: Incremental solver for smooth dragging (60 FPS)

    # ========================================================================
    # Viewport LOD (Phase 1: Foundation Stabilization)
    # ========================================================================
    "viewport_lod_system": True,  # Coarse mesh during camera interaction
    "viewport_frustum_culling": True,  # Hide out-of-frustum bodies during navigation
    "viewport_mesh_instancing": True,  # Share identical mesh datasets between body actors
    
    # ========================================================================
    # QA & Validation
    # ========================================================================
    "performance_regression_gate": True,  # Performance benchmarking
    "rollback_validation": True,  # Rollback state validation
    
    # ========================================================================
    # UX: First-Run Experience
    # ========================================================================
    "first_run_tutorial": True,  # 5-step guided tutorial for new users
    
    # ========================================================================
    # Live Preview System
    # ========================================================================
    "live_preview_textures": True,  # Live texture preview with debouncing
    "live_preview_patterns": True,  # Live pattern preview
    "live_preview_shell": True,  # Live shell thickness preview
    "live_preview_fillet": True,  # Live fillet radius preview
    "live_preview_chamfer": True,  # Live chamfer size preview
    
    # Preview Quality Settings
    "preview_debounce_ms": 150,  # Debounce delay in milliseconds
    "preview_subdivisions_live": 3,  # Mesh subdivisions for live preview
    "preview_subdivisions_final": 5,  # Mesh subdivisions for final apply
    
    # ========================================================================
    # Normal Map Preview (Phase 3 - Advanced, experimental)
    # ========================================================================
    "normal_map_preview": False,  # Normal map visualization
    "normal_map_shader": False,  # Shader-based normal mapping
    
    # ========================================================================
    # Experimental Features
    # ========================================================================
    "cylindrical_face_edit": False,  # Fusion360-style Radius Edit
    "rc_burn_in_mode": False,  # RC burn-in testing mode
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
