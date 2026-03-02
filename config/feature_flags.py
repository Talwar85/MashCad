"""
MashCad - Feature Flags
=======================

Feature flags in this repo are limited to debug controls and a small set of
real runtime policies. Integrated features run directly in production code and
are no longer gated here.

Already integrated features (flags removed):
===========================================
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
- mate_system_v1, mate_solver

Further removed flags:
- parallel_rebuild (OCP/OpenCASCADE is not thread-safe)
- use_solver_constraints, solver_visual_feedback, etc.
- export_normals_check, export_auto_repair
- ocp_advanced_flags, wall_thickness_analysis, loft_sweep_hardening
- solver_experimental_staged
- live_preview_textures, live_preview_patterns
- preview_subdivisions_live, preview_subdivisions_final
- cylindrical_face_edit, rc_burn_in_mode
"""

from typing import Any

# Feature Flag Registry
# =====================
# FEATURE_FLAGS contains boolean gates and runtime policies only.
# FEATURE_SETTINGS contains non-boolean runtime configuration values.

FEATURE_FLAGS: dict[str, bool] = {
    # ========================================================================
    # Debug Modes
    # ========================================================================
    "sketch_input_logging": False,
    "tnp_debug_logging": True,
    "sketch_debug": False,
    "extrude_debug": True,
    "viewport_debug": False,
    "sketch_performance_monitoring": False,

    # ========================================================================
    # UX Features
    # ========================================================================
    "sketch_orientation_indicator": False,

    # ========================================================================
    # Export Formats
    # ========================================================================
    "export_3mf": True,

    # ========================================================================
    # Export Validation
    # ========================================================================
    "export_free_bounds_check": True,

    # ========================================================================
    # Geometry & Printability
    # ========================================================================
    "geometry_drift_detection": True,
    "printability_trust_gate": True,
    "printability_block_on_critical": True,

    # ========================================================================
    # OCP Runtime Policies
    # ========================================================================
    "self_heal_strict": True,
    "strict_topology_fallback_policy": True,
    "mesh_converter_adaptive_tolerance": True,
    "detailed_boolean_history": True,
    "helix_fitting_enabled": True,

    # ========================================================================
    # Solver Configuration
    # ========================================================================
    "solver_pre_validation": True,
    "solver_smooth_penalties": True,

    # ========================================================================
    # Sketch Performance
    # ========================================================================
    "sketch_drag_optimization": True,
    "incremental_solver": True,

    # ========================================================================
    # Viewport LOD
    # ========================================================================
    "viewport_lod_system": True,
    "viewport_frustum_culling": True,
    "viewport_mesh_instancing": True,

    # ========================================================================
    # QA & Validation
    # ========================================================================
    "performance_regression_gate": True,
    "rollback_validation": True,

    # ========================================================================
    # UX: First-Run Experience
    # ========================================================================
    "first_run_tutorial": True,

    # ========================================================================
    # Live Preview System
    # ========================================================================
    "live_preview_shell": True,
    "live_preview_fillet": True,
    "live_preview_chamfer": True,

    # ========================================================================
    # Normal Map Preview
    # ========================================================================
    "normal_map_preview": False,
}

FEATURE_SETTINGS: dict[str, Any] = {
    "printability_min_score": 60,
    "solver_backend": "staged",
    "sketch_solver_throttle_ms": 16,
    "preview_debounce_ms": 150,
}


def is_enabled(flag: str) -> bool:
    """
    Return whether a boolean feature flag is enabled.

    Unknown flags default to False.
    """
    return bool(FEATURE_FLAGS.get(flag, False))


def get_setting(name: str, default: Any = None) -> Any:
    """Return a non-boolean runtime setting."""
    return FEATURE_SETTINGS.get(name, default)



def set_flag(flag: str, value: Any) -> None:
    """
    Set a feature flag at runtime.

    Useful for tests and debugging.
    """
    if flag in FEATURE_SETTINGS:
        FEATURE_SETTINGS[flag] = value
        return
    FEATURE_FLAGS[flag] = bool(value) if isinstance(value, bool) else value


# Alias for set_flag (CH-006 compatibility)
def set_enabled(flag: str, value: Any) -> None:
    """Alias for set_flag."""
    set_flag(flag, value)


def set_setting(name: str, value: Any) -> None:
    """Set a non-boolean runtime setting."""
    FEATURE_SETTINGS[name] = value



def get_all_flags() -> dict[str, Any]:
    """Return a copy of all feature flags."""
    return FEATURE_FLAGS.copy()


def get_all_settings() -> dict[str, Any]:
    """Return a copy of all runtime settings."""
    return FEATURE_SETTINGS.copy()
