from pathlib import Path

import pytest

from config.feature_flags import FEATURE_FLAGS, set_flag


# Global Feature Flag Defaults - Single Source of Truth for Test Isolation
# ========================================================================
# WICHTIG: Jeder Test muss mit sauberen Feature-Flags starten.
# Diese Defaults müssen mit config/feature_flags.py synchron gehalten werden.
FEATURE_FLAG_DEFAULTS = {
    # Debug-Modi
    "sketch_input_logging": False,
    "tnp_debug_logging": False,
    "sketch_debug": False,
    "extrude_debug": False,
    "viewport_debug": False,
    
    # UX Features
    "sketch_orientation_indicator": False,
    
    # Assembly System
    "assembly_system": True,
    
    # Performance Optimizations
    "optimized_actor_pooling": True,
    "reuse_hover_markers": True,
    "picker_pooling": True,
    "bbox_early_rejection": True,
    "export_cache": True,
    "feature_dependency_tracking": True,
    "feature_solid_caching": True,
    "async_tessellation": True,
    "ocp_advanced_flags": True,
    "ocp_glue_auto_detect": True,
    "batch_fillets": True,
    "wall_thickness_analysis": True,
    "self_heal_strict": True,
    
    # W28+ Determinism Core Policy (CRITICAL: must be True for cross-suite isolation)
    "strict_topology_fallback_policy": True,
    
    # Boolean Robustness
    "boolean_self_intersection_check": True,
    "boolean_post_validation": True,
    "boolean_argument_analyzer": True,
    "adaptive_tessellation": True,
    "export_free_bounds_check": True,
    "boolean_tolerance_monitoring": True,
    
    # OCP Feature Audit Tier 3
    "mesh_converter_adaptive_tolerance": True,
    "loft_sweep_hardening": True,
    
    # Thread/Helix
    "native_ocp_helix": True,
    
    # Cylindrical Face Edit
    "cylindrical_face_edit": False,
    
    # OCP-First Migration
    "ocp_first_extrude": True,
    "ocp_brep_cache": True,
    "ocp_incremental_rebuild": True,
    "ocp_brep_persistence": True,
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
