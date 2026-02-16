"""
W14 Paket C: Crash Containment Regression Contracts
===================================================

Validiert den W14 Stand:
- Drag-Tests sind runnable (kein skip/xfail)
- Subprozess-Isolierung bleibt aktiv
- Isolierte Drag-Suite existiert weiterhin
"""

import os
import pytest


class TestCrashContainmentContract:
    """W14 contracts fuer Interaktions-Crash-Containment."""

    def test_interaction_consistency_drag_tests_are_not_skipped_or_xfailed(self):
        """Drag-Tests im Main-Suite-Entrypoint sind neither skip nor xfail."""
        test_file = "test/harness/test_interaction_consistency.py"
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "@pytest.mark.skip" not in content, "Drag tests must not be skipped"
        assert "@pytest.mark.xfail" not in content, "Drag tests must not be xfailed"

    def test_interaction_consistency_uses_subprocess_isolation(self):
        """Main drag tests must still run isolated via subprocess helper."""
        test_file = "test/harness/test_interaction_consistency.py"
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "run_test_in_subprocess" in content
        assert "crash_containment_helper" in content

    def test_interaction_consistency_hard_fail_contract(self):
        """Main drag tests must assert no crash signature and exit_code==0."""
        test_file = "test/harness/test_interaction_consistency.py"
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "assert crash_sig is None" in content
        assert "assert exit_code == 0" in content

    def test_isolated_drag_test_file_still_exists(self):
        """Isolated drag test file remains available."""
        isolated_file = "test/harness/test_interaction_drag_isolated.py"
        assert os.path.exists(isolated_file), f"Missing {isolated_file}"

        with open(isolated_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "test_circle_move_resize_isolated" in content
        assert "test_rectangle_edge_drag_isolated" in content
        assert "test_line_drag_consistency_isolated" in content

    def test_isolated_tests_not_marked_skip_or_xfail(self):
        """W14 isolated tests are hard runnable tests, no skip/xfail markers."""
        isolated_file = "test/harness/test_interaction_drag_isolated.py"
        with open(isolated_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "@pytest.mark.skip" not in content
        assert "@pytest.mark.xfail" not in content

    def test_crash_signature_dictionary_exists(self):
        """Crash helper keeps canonical blocker signatures."""
        helper_file = "test/harness/crash_containment_helper.py"
        with open(helper_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "BLOCKER_SIGNATURES" in content
        assert "ACCESS_VIOLATION_INTERACTION_DRAG" in content


class TestGateRunnerContractW14:
    """W14 gate/evidence scripts include latest generation markers."""

    def test_gate_ui_has_modern_header(self):
        """Gate UI Script hat W14 Header."""
        gate_file = "scripts/gate_ui.ps1"
        with open(gate_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "W14" in content, "Gate UI Script should have W14 header"

    def test_gate_evidence_has_modern_header(self):
        """Gate Evidence Script hat W14 Header."""
        evidence_file = "scripts/generate_gate_evidence.ps1"
        with open(evidence_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "W14" in content, "Gate Evidence Script should have W14 header"

    def test_gate_evidence_w14_version(self):
        """Gate Evidence hat W14 Version 4.0."""
        evidence_file = "scripts/generate_gate_evidence.ps1"
        with open(evidence_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "evidence_version" in content
        assert '"4.0"' in content or "'4.0'" in content or "4.0" in content


class TestAbortLogicContractW14:
    """W14 contracts fuer SU-006 Abort-State-Machine."""

    def test_abort_logic_tests_include_new_w14_tests(self):
        """Abort-Logic-Tests enthalten W14 Test-Erweiterungen."""
        test_file = "test/test_ui_abort_logic.py"
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        # W14 spezifische Tests
        assert "W14-A-R1" in content or "W14-A-R2" in content
        assert "right_click_empty_clears_dim_input" in content
        assert "test_abort_logic_no_stuck_state_after_sequence" in content

    def test_abort_logic_tests_min_12_new_assertions(self):
        """W14: Mindestens 12 neue Abort-Logic Assertions."""
        test_file = "test/test_ui_abort_logic.py"
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        # W14 Marker und mindestens 12 neue Tests
        w14_a_count = content.count("W14-A-R")
        assert w14_a_count >= 12, f"Expected at least 12 W14-A tests, found {w14_a_count}"


class TestDiscoverabilityContractW14:
    """W14 contracts fuer SU-009 Discoverability ohne Spam."""

    def test_discoverability_tests_include_new_w14_tests(self):
        """Discoverability-Tests enthalten W14 Test-Erweiterungen."""
        test_file = "test/test_discoverability_hints.py"
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        # W14 spezifische Tests
        assert "W14-B-R1" in content or "W14-B-R2" in content
        assert "test_rotation_hint_visible_in_sketch_mode" in content
        assert "test_hint_cooldown_blocks_duplicate_rapid_calls" in content

    def test_discoverability_tests_min_12_new_assertions(self):
        """W14: Mindestens 12 neue Discoverability Assertions."""
        test_file = "test/test_discoverability_hints.py"
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        # W14 Marker und mindestens 12 neue Tests
        w14_b_count = content.count("W14-B-R")
        assert w14_b_count >= 12, f"Expected at least 12 W14-B tests, found {w14_b_count}"


class TestErrorUXContractW14:
    """W14 contracts fuer UX-003 / CH-008 Error UX v2 End-to-End Wiring."""

    def test_error_ux_tests_include_new_w14_tests(self):
        """Error-UX-Tests enthalten W14 Test-Erweiterungen."""
        test_file = "test/test_error_ux_v2_integration.py"
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        # W14 spezifische Tests
        assert "W14-C-R1" in content or "W14-C-R2" in content
        assert "test_feature_edit_failure_shows_warning_recoverable" in content
        assert "test_status_class_overrides_severity_in_status_bar" in content

    def test_error_ux_tests_min_15_new_assertions(self):
        """W14: Mindestens 15 neue Error-UX Assertions."""
        test_file = "test/test_error_ux_v2_integration.py"
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        # W14 Marker und mindestens 15 neue Tests
        w14_c_count = content.count("W14-C-R")
        assert w14_c_count >= 15, f"Expected at least 15 W14-C tests, found {w14_c_count}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
