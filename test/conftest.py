from pathlib import Path

import pytest

from config.feature_flags import FEATURE_FLAGS, set_flag


# Command-line options for RC burn-in tests
def pytest_addoption(parser):
    """Register custom command-line options for pytest."""
    parser.addoption(
        "--iterations",
        action="store",
        default=100,
        type=int,
        help="Number of iterations for stress tests"
    )
    parser.addoption(
        "--memory-samples",
        action="store",
        default=10,
        type=int,
        help="Number of memory samples to take"
    )


@pytest.fixture
def iterations(request):
    """Get iteration count from command line."""
    return request.config.getoption("--iterations")


@pytest.fixture
def memory_samples(request):
    """Get memory sample count from command line."""
    return request.config.getoption("--memory-samples")


# Global Feature Flag Defaults - Single Source of Truth for Test Isolation
# ========================================================================
# WICHTIG: Jeder Test muss mit sauberen Feature-Flags starten.
# Diese Defaults müssen mit config/feature_flags.py synchron gehalten werden.
#
# Entfernte Flags (Phase 1-5 Cleanup):
# - assembly_system, batch_fillets, native_ocp_helix (permanent aktiviert)
# - optimized_actor_pooling, reuse_hover_markers, picker_pooling (permanent)
# - bbox_early_rejection, export_cache, async_tessellation (permanent)
# - feature_dependency_tracking, feature_solid_caching (permanent)
# - ocp_glue_auto_detect, adaptive_tessellation (permanent)
# - boolean_* flags (permanent aktiviert)
# - ocp_first_extrude, ocp_brep_cache, ocp_incremental_rebuild, ocp_brep_persistence (permanent)
FEATURE_FLAG_DEFAULTS = {
    # Debug-Modi
    "sketch_input_logging": False,
    "tnp_debug_logging": False,
    "sketch_debug": False,
    "extrude_debug": False,
    "viewport_debug": False,
    "sketch_performance_monitoring": False,
    
    # UX Features
    "sketch_orientation_indicator": False,
    
    # Assembly System (mate_system_v1, mate_solver sind noch Flags)
    "mate_system_v1": True,
    "mate_solver": True,
    
    # OCP Advanced (verbleibende Flags)
    "ocp_advanced_flags": True,
    "wall_thickness_analysis": True,
    "self_heal_strict": True,
    
    # W28+ Determinism Core Policy (CRITICAL: must be True for cross-suite isolation)
    "strict_topology_fallback_policy": True,
    
    # Export Validation
    "export_free_bounds_check": True,
    "export_normals_check": False,
    "export_auto_repair": True,
    
    # OCP Feature Audit Tier 3
    "mesh_converter_adaptive_tolerance": True,
    "loft_sweep_hardening": True,
    
    # Cylindrical Face Edit (experimental)
    "cylindrical_face_edit": False,
    
    # UX-001: First-Run Guided Flow
    "first_run_tutorial": True,
    
    # Solver Configuration
    "solver_backend": "staged",
    "solver_pre_validation": True,
    "solver_smooth_penalties": True,
    "solver_experimental_staged": True,
    
    # Sketch Performance
    "sketch_drag_optimization": True,
    "sketch_solver_throttle_ms": 16,
    
    # QA & Validation
    "performance_regression_gate": True,
    "rollback_validation": True,
    
    # Geometry & Printability
    "geometry_drift_detection": True,
    "printability_trust_gate": True,
    "printability_min_score": 60,
    "printability_block_on_critical": True,
    
    # Export
    "export_3mf": True,
    
    # Live Preview
    "live_preview_textures": True,
    "live_preview_patterns": True,
    "live_preview_shell": False,
    "live_preview_fillet": False,
    "live_preview_chamfer": False,
    "preview_debounce_ms": 150,
    "preview_subdivisions_live": 3,
    "preview_subdivisions_final": 5,
    
    # Normal Map Preview
    "normal_map_preview": False,
    "normal_map_shader": False,
    
    # Advanced
    "detailed_boolean_history": True,
    "helix_fitting_enabled": True,
    "rc_burn_in_mode": False,
}


def _is_tnp_suite_test(node: pytest.Item) -> bool:
    """Enable TNP debug logging only for dedicated TNP test modules."""
    try:
        return Path(str(node.fspath)).name.startswith("test_tnp_")
    except Exception:
        return "test_tnp_" in str(getattr(node, "nodeid", ""))


@pytest.fixture(autouse=True)
def _global_feature_flag_isolation():
    """
    W28 Core Regression Fix: Globale Feature-Flag-Isolation.
    
    Stellt sicher, dass jeder Test mit sauberen, deterministischen
    Feature-Flags startet. Verhindert Cross-Suite-Leakage von
    Feature-Flag-Mutationen (z.B. strict_topology_fallback_policy=False).
    
    Dieses Fixture hat Vorrang vor modul-spezifischen Fixtures.
    """
    # Pre-Test: Alle Flags auf Defaults zurücksetzen
    for key, value in FEATURE_FLAG_DEFAULTS.items():
        set_flag(key, value)
    
    yield
    
    # Post-Test: Alle Flags auf Defaults zurücksetzen (cleanup)
    for key, value in FEATURE_FLAG_DEFAULTS.items():
        set_flag(key, value)


@pytest.fixture(autouse=True)
def _tnp_debug_logging_only_for_tnp_suite(request: pytest.FixtureRequest):
    """
    Enable TNP debug logging only for dedicated TNP test modules.
    
    HINWEIS: Dieses Fixture setzt nur tnp_debug_logging, alle anderen
    Flags werden von _global_feature_flag_isolation verwaltet.
    """
    if _is_tnp_suite_test(request.node):
        set_flag("tnp_debug_logging", True)
        yield
        # Cleanup wird von _global_feature_flag_isolation übernommen
    else:
        # Non-TNP Tests: tnp_debug_logging bleibt False (via _global_feature_flag_isolation)
        yield
