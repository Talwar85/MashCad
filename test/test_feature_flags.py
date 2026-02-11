"""
Feature Flags Tests - Tests für das Feature Flag System

Author: Claude (OCP-First Migration Phase 1)
Date: 2026-02-10
"""

import pytest
from config.feature_flags import (
    is_enabled,
    set_flag,
    get_all_flags,
    FEATURE_FLAGS
)


class TestFeatureFlagsBasic:
    """Tests für grundlegende Feature Flag Funktionalität."""
    
    def test_is_enabled_existing_flag_true(self):
        """Test: Existierendes Flag mit Wert True."""
        # assembly_system ist auf True gesetzt
        assert is_enabled("assembly_system") is True
    
    def test_is_enabled_existing_flag_false(self):
        """Test: Existierendes Flag mit Wert False."""
        # cylindrical_face_edit ist auf False gesetzt
        assert is_enabled("cylindrical_face_edit") is False
    
    def test_is_enabled_nonexistent_flag(self):
        """Test: Nicht existierendes Flag gibt False zurück."""
        assert is_enabled("nonexistent_flag_xyz123") is False
    
    def test_get_all_flags_returns_dict(self):
        """Test: get_all_flags gibt ein Dict zurück."""
        flags = get_all_flags()
        assert isinstance(flags, dict)
        assert len(flags) > 0
    
    def test_get_all_flags_returns_copy(self):
        """Test: get_all_flags gibt eine Kopie zurück."""
        flags1 = get_all_flags()
        flags2 = get_all_flags()
        
        # Modifiziere eine Kopie
        flags1["new_flag"] = True
        
        # Original sollte nicht verändert sein
        assert "new_flag" not in FEATURE_FLAGS
    
    def test_set_flag_runtime(self):
        """Test: Set Flag zur Laufzeit."""
        # Neues Flag setzen
        set_flag("runtime_test_flag", True)
        assert is_enabled("runtime_test_flag") is True
        
        # Flag ändern
        set_flag("runtime_test_flag", False)
        assert is_enabled("runtime_test_flag") is False
        
        # Cleanup
        del FEATURE_FLAGS["runtime_test_flag"]


class TestOCPFirstFeatureFlags:
    """Tests für OCP-First Migration Feature Flags.

    Nach Phase A-F (Feb 2026) sind die meisten OCP-First Flags entfernt,
    da die Operationen jetzt direkt OCP verwenden (kein Fallback mehr nötig).
    """

    def test_ocp_first_extrude_enabled(self):
        """Test: ocp_first_extrude ist nach Migration aktiviert."""
        assert is_enabled("ocp_first_extrude") is True

    def test_ocp_first_revolve_removed(self):
        """Test: ocp_first_revolve wurde nach OCP-First Migration entfernt."""
        # Flag wurde entfernt - Revolve verwendet jetzt direkt OCP
        assert is_enabled("ocp_first_revolve") is False

    def test_ocp_first_loft_removed(self):
        """Test: ocp_first_loft wurde nach OCP-First Migration entfernt."""
        # Flag wurde entfernt - Loft verwendet jetzt direkt OCP
        assert is_enabled("ocp_first_loft") is False

    def test_ocp_first_sweep_removed(self):
        """Test: ocp_first_sweep wurde nach OCP-First Migration entfernt."""
        # Flag wurde entfernt - Sweep verwendet jetzt direkt OCP
        assert is_enabled("ocp_first_sweep") is False

    def test_ocp_first_shell_removed(self):
        """Test: ocp_first_shell wurde nach OCP-First Migration entfernt."""
        # Flag wurde entfernt - Shell verwendet jetzt direkt OCP
        assert is_enabled("ocp_first_shell") is False

    def test_ocp_first_hollow_removed(self):
        """Test: ocp_first_hollow wurde nach OCP-First Migration entfernt."""
        # Flag wurde entfernt - Hollow verwendet jetzt direkt OCP
        assert is_enabled("ocp_first_hollow") is False

    def test_ocp_first_fillet_removed(self):
        """Test: ocp_first_fillet wurde nach OCP-First Migration entfernt."""
        # Flag wurde entfernt - Fillet verwendet jetzt direkt OCP
        assert is_enabled("ocp_first_fillet") is False

    def test_ocp_first_chamfer_removed(self):
        """Test: ocp_first_chamfer wurde nach OCP-First Migration entfernt."""
        # Flag wurde entfernt - Chamfer verwendet jetzt direkt OCP
        assert is_enabled("ocp_first_chamfer") is False

    def test_ocp_brep_cache_enabled(self):
        """Test: ocp_brep_cache ist nach Migration aktiviert."""
        assert is_enabled("ocp_brep_cache") is True

    def test_ocp_incremental_rebuild_enabled(self):
        """Test: ocp_incremental_rebuild ist nach Migration aktiviert."""
        assert is_enabled("ocp_incremental_rebuild") is True

    def test_ocp_brep_persistence_enabled(self):
        """Test: ocp_brep_persistence ist nach Migration aktiviert."""
        assert is_enabled("ocp_brep_persistence") is True

    def test_all_ocp_first_flags_exist(self):
        """Test: Alle OCP-First Flags existieren oder entfernt wurden."""
        # Nach Phase A-F (Feb 2026): Nur ocp_first_extrude bleibt
        remaining_flags = [
            "ocp_first_extrude",
            "ocp_brep_cache",
            "ocp_incremental_rebuild",
            "ocp_brep_persistence"
        ]

        removed_flags = [
            "ocp_first_fillet",
            "ocp_first_chamfer",
            "ocp_first_revolve",
            "ocp_first_loft",
            "ocp_first_sweep",
            "ocp_first_shell",
            "ocp_first_hollow"
        ]

        flags = get_all_flags()

        # Verbleibende Flags sollten existieren
        for flag in remaining_flags:
            assert flag in flags, f"OCP-First Flag {flag} fehlt"

        # Entfernte Flags sollten NICHT mehr existieren
        for flag in removed_flags:
            assert flag not in flags, f"OCP-First Flag {flag} wurde entfernt, sollte nicht mehr existieren"


class TestPerformanceFeatureFlags:
    """Tests für Performance Optimierung Feature Flags."""
    
    def test_performance_flags_default_true(self):
        """Test: Performance Flags sind standardmäßig True."""
        performance_flags = [
            "optimized_actor_pooling",
            "reuse_hover_markers",
            "picker_pooling",
            "bbox_early_rejection",
            "export_cache",
            "feature_dependency_tracking",
            "feature_solid_caching",
            "async_tessellation",
            "ocp_advanced_flags",
            "ocp_glue_auto_detect",
            "batch_fillets",
            "wall_thickness_analysis"
        ]
        
        for flag in performance_flags:
            assert is_enabled(flag) is True, f"Performance Flag {flag} sollte True sein"
    
    def test_self_heal_strict_default_true(self):
        """Test: self_heal_strict ist standardmäßig True."""
        assert is_enabled("self_heal_strict") is True


class TestBooleanRobustnessFeatureFlags:
    """Tests für Boolean Robustness Feature Flags."""
    
    def test_boolean_robustness_flags_default_true(self):
        """Test: Boolean Robustness Flags sind standardmäßig True."""
        boolean_flags = [
            "boolean_self_intersection_check",
            "boolean_post_validation",
            "boolean_argument_analyzer",
            "adaptive_tessellation",
            "export_free_bounds_check",
            "boolean_tolerance_monitoring"
        ]
        
        for flag in boolean_flags:
            assert is_enabled(flag) is True, f"Boolean Flag {flag} sollte True sein"


class TestOCPFeatureAuditFlags:
    """Tests für OCP Feature Audit Feature Flags."""
    
    def test_ocp_audit_flags_default_true(self):
        """Test: OCP Audit Flags sind standardmäßig True."""
        audit_flags = [
            "mesh_converter_adaptive_tolerance",
            "loft_sweep_hardening"
        ]
        
        for flag in audit_flags:
            assert is_enabled(flag) is True, f"OCP Audit Flag {flag} sollte True sein"


class TestDebugFeatureFlags:
    """Tests für Debug Feature Flags."""
    
    def test_debug_flags_default_false(self):
        """Test: Debug Flags sind standardmäßig False."""
        debug_flags = [
            "sketch_input_logging",
            "tnp_debug_logging",
            "sketch_debug",
            "extrude_debug",
            "viewport_debug"
        ]
        
        for flag in debug_flags:
            assert is_enabled(flag) is False, f"Debug Flag {flag} sollte False sein"


class TestNativeOCPHelixFlag:
    """Tests für native_ocp_helix Flag."""
    
    def test_native_ocp_helix_default_true(self):
        """Test: native_ocp_helix ist standardmäßig True."""
        assert is_enabled("native_ocp_helix") is True


class TestAssemblySystemFlag:
    """Tests für assembly_system Flag."""
    
    def test_assembly_system_default_true(self):
        """Test: assembly_system ist standardmäßig True."""
        assert is_enabled("assembly_system") is True


class TestFeatureFlagRuntimeModification:
    """Tests für Laufzeit-Modifikation von Feature Flags."""
    
    def test_set_flag_to_true(self):
        """Test: Flag auf True setzen."""
        # cylindrical_face_edit ist standardmäßig False
        assert is_enabled("cylindrical_face_edit") is False
        
        # Auf True setzen
        set_flag("cylindrical_face_edit", True)
        assert is_enabled("cylindrical_face_edit") is True
        
        # Wieder zurück auf False
        set_flag("cylindrical_face_edit", False)
        assert is_enabled("cylindrical_face_edit") is False
    
    def test_ocp_first_flags_can_be_enabled(self):
        """Test: OCP-First Flags können aktiviert werden."""
        # Alle OCP-First Flags testweise aktivieren
        ocp_flags = [
            "ocp_first_extrude",
            "ocp_first_fillet",
            "ocp_first_chamfer",
            "ocp_first_revolve"
        ]
        
        for flag in ocp_flags:
            set_flag(flag, True)
            assert is_enabled(flag) is True
        
        # Wieder deaktivieren
        for flag in ocp_flags:
            set_flag(flag, False)
            assert is_enabled(flag) is False
    
    def test_debug_flags_can_be_enabled(self):
        """Test: Debug Flags können aktiviert werden."""
        # Debug Flags testweise aktivieren
        debug_flags = [
            "tnp_debug_logging",
            "sketch_debug"
        ]
        
        for flag in debug_flags:
            set_flag(flag, True)
            assert is_enabled(flag) is True
        
        # Wieder deaktivieren
        for flag in debug_flags:
            set_flag(flag, False)
            assert is_enabled(flag) is False


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])