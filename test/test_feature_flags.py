"""Tests for the feature flag registry."""

import pytest

from config.feature_flags import (
    FEATURE_FLAGS,
    FEATURE_SETTINGS,
    get_all_flags,
    get_all_settings,
    get_setting,
    is_enabled,
    set_flag,
)


class TestFeatureFlagsBasic:
    def test_is_enabled_existing_flag_true(self):
        assert is_enabled("geometry_drift_detection") is True

    def test_is_enabled_existing_flag_false(self):
        assert is_enabled("normal_map_preview") is False

    def test_is_enabled_nonexistent_flag(self):
        assert is_enabled("nonexistent_flag_xyz123") is False

    def test_get_all_flags_returns_dict_copy(self):
        flags1 = get_all_flags()
        flags2 = get_all_flags()

        assert isinstance(flags1, dict)
        assert len(flags1) > 0
        assert flags1 is not FEATURE_FLAGS
        assert flags2 is not FEATURE_FLAGS

        flags1["new_flag"] = True
        assert "new_flag" not in FEATURE_FLAGS

    def test_get_all_settings_returns_dict_copy(self):
        settings1 = get_all_settings()
        settings2 = get_all_settings()

        assert isinstance(settings1, dict)
        assert len(settings1) > 0
        assert settings1 is not FEATURE_SETTINGS
        assert settings2 is not FEATURE_SETTINGS

        settings1["new_setting"] = 123
        assert "new_setting" not in FEATURE_SETTINGS

    def test_set_flag_runtime(self):
        set_flag("runtime_test_flag", True)
        assert is_enabled("runtime_test_flag") is True

        set_flag("runtime_test_flag", False)
        assert is_enabled("runtime_test_flag") is False

        del FEATURE_FLAGS["runtime_test_flag"]


class TestRemovedIntegratedFlags:
    def test_ocp_first_flags_are_removed(self):
        removed_flags = [
            "ocp_first_extrude",
            "ocp_brep_cache",
            "ocp_incremental_rebuild",
            "ocp_brep_persistence",
            "ocp_first_fillet",
            "ocp_first_chamfer",
            "ocp_first_revolve",
            "ocp_first_loft",
            "ocp_first_sweep",
            "ocp_first_shell",
            "ocp_first_hollow",
        ]

        flags = get_all_flags()
        for flag in removed_flags:
            assert flag not in flags
            assert is_enabled(flag) is False

    def test_dead_flags_are_removed(self):
        removed_flags = [
            "mate_system_v1",
            "mate_solver",
            "export_3mf",
            "export_normals_check",
            "export_auto_repair",
            "ocp_advanced_flags",
            "wall_thickness_analysis",
            "loft_sweep_hardening",
            "solver_experimental_staged",
            "live_preview_textures",
            "live_preview_patterns",
            "live_preview_shell",
            "live_preview_fillet",
            "live_preview_chamfer",
            "preview_subdivisions_live",
            "preview_subdivisions_final",
            "cylindrical_face_edit",
            "rc_burn_in_mode",
            "assembly_system",
            "native_ocp_helix",
            "performance_regression_gate",
        ]

        flags = get_all_flags()
        for flag in removed_flags:
            assert flag not in flags
            assert is_enabled(flag) is False


class TestActiveRuntimePolicies:
    def test_core_runtime_flags_default_true(self):
        flags = [
            "geometry_drift_detection",
            "export_free_bounds_check",
            "self_heal_strict",
            "strict_topology_fallback_policy",
            "mesh_converter_adaptive_tolerance",
            "detailed_boolean_history",
            "helix_fitting_enabled",
            "rollback_validation",
            "first_run_tutorial",
            "incremental_solver",
            "viewport_lod_system",
            "viewport_frustum_culling",
            "viewport_mesh_instancing",
        ]

        for flag in flags:
            assert is_enabled(flag) is True, f"{flag} should default to True"

    def test_printability_settings_exist(self):
        flags = get_all_flags()
        assert flags["printability_trust_gate"] is True
        assert flags["printability_block_on_critical"] is True

        settings = get_all_settings()
        assert settings["printability_min_score"] == 60

    def test_solver_settings_exist(self):
        flags = get_all_flags()
        settings = get_all_settings()
        assert settings["solver_backend"] == "staged"
        assert flags["solver_pre_validation"] is True
        assert flags["solver_smooth_penalties"] is True
        assert settings["sketch_solver_throttle_ms"] == 16
        assert settings["preview_debounce_ms"] == 150

    def test_get_setting_returns_defaults(self):
        assert get_setting("preview_debounce_ms") == 150
        assert get_setting("missing_runtime_setting", "fallback") == "fallback"


class TestDebugFeatureFlags:
    def test_debug_flags_can_be_toggled(self):
        debug_flags = [
            "sketch_input_logging",
            "tnp_debug_logging",
            "sketch_debug",
            "extrude_debug",
            "viewport_debug",
        ]

        original_values = {flag: FEATURE_FLAGS[flag] for flag in debug_flags}
        try:
            for flag in debug_flags:
                set_flag(flag, True)
                assert is_enabled(flag) is True

            for flag in debug_flags:
                set_flag(flag, False)
                assert is_enabled(flag) is False
        finally:
            for flag, value in original_values.items():
                set_flag(flag, value)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
