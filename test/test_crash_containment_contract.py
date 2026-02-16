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
        gate_file = "scripts/gate_ui.ps1"
        with open(gate_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert ("W14" in content or "W13" in content or "W12" in content)

    def test_gate_evidence_has_modern_header(self):
        evidence_file = "scripts/generate_gate_evidence.ps1"
        with open(evidence_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert ("W14" in content or "W13" in content or "W12" in content)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
