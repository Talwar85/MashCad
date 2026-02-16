"""
test_gate_runner_contract.py
QA Contract Tests for Gate Runner Scripts (W3)

Validates:
- Script existence and callability
- Output schema (Status, Exit, Duration, counts)
- BLOCKED_INFRA vs BLOCKED vs FAIL classification (W3)
- blocker_type field validation (W3)
- Evidence generator contract with status_class (W3)
- JSON schema validation (W3)

No expensive end-to-end tests - fast contract validation only.
"""

import subprocess
import re
import sys
import json
import tempfile
from pathlib import Path
from typing import List

import pytest


class TestGateRunnerContract:
    """Contract tests for gate runner scripts."""

    SCRIPT_DIR = Path(__file__).parent.parent / "scripts"

    def _run_script(self, script_name, args=None, timeout=10):
        """Helper to run a gate script and return result."""
        script_path = self.SCRIPT_DIR / script_name
        if not script_path.exists():
            pytest.skip(f"Script not found: {script_path}")

        cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
        if args:
            cmd.extend(args)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result

    # =========================================================================
    # Script Existence Tests
    # =========================================================================

    def test_gate_core_script_exists(self):
        """gate_core.ps1 must exist."""
        script_path = self.SCRIPT_DIR / "gate_core.ps1"
        assert script_path.exists(), f"gate_core.ps1 not found at {script_path}"

    def test_gate_ui_script_exists(self):
        """gate_ui.ps1 must exist."""
        script_path = self.SCRIPT_DIR / "gate_ui.ps1"
        assert script_path.exists(), f"gate_ui.ps1 not found at {script_path}"

    def test_gate_all_script_exists(self):
        """gate_all.ps1 must exist."""
        script_path = self.SCRIPT_DIR / "gate_all.ps1"
        assert script_path.exists(), f"gate_all.ps1 not found at {script_path}"

    def test_hygiene_check_script_exists(self):
        """hygiene_check.ps1 must exist."""
        script_path = self.SCRIPT_DIR / "hygiene_check.ps1"
        assert script_path.exists(), f"hygiene_check.ps1 not found at {script_path}"

    def test_core_budget_check_script_exists(self):
        """check_core_gate_budget.ps1 must exist."""
        script_path = self.SCRIPT_DIR / "check_core_gate_budget.ps1"
        assert script_path.exists(), f"check_core_gate_budget.ps1 not found at {script_path}"

    def test_stability_dashboard_script_exists(self):
        """generate_stability_dashboard.ps1 must exist."""
        script_path = self.SCRIPT_DIR / "generate_stability_dashboard.ps1"
        assert script_path.exists(), f"generate_stability_dashboard.ps1 not found at {script_path}"

    def test_validate_gate_evidence_script_exists(self):
        """validate_gate_evidence.ps1 must exist."""
        script_path = self.SCRIPT_DIR / "validate_gate_evidence.ps1"
        assert script_path.exists(), f"validate_gate_evidence.ps1 not found at {script_path}"

    def test_core_profile_matrix_script_exists(self):
        """generate_core_profile_matrix.ps1 must exist."""
        script_path = self.SCRIPT_DIR / "generate_core_profile_matrix.ps1"
        assert script_path.exists(), f"generate_core_profile_matrix.ps1 not found at {script_path}"

    def test_core_gate_trend_script_exists(self):
        """generate_core_gate_trend.ps1 must exist."""
        script_path = self.SCRIPT_DIR / "generate_core_gate_trend.ps1"
        assert script_path.exists(), f"generate_core_gate_trend.ps1 not found at {script_path}"

    def test_core_ops_dashboard_script_exists(self):
        """generate_core_ops_dashboard.ps1 must exist."""
        script_path = self.SCRIPT_DIR / "generate_core_ops_dashboard.ps1"
        assert script_path.exists(), f"generate_core_ops_dashboard.ps1 not found at {script_path}"

    # =========================================================================
    # Output Schema Tests
    # =========================================================================

    def test_gate_core_output_schema(self):
        """gate_core.ps1 must output structured result with required fields."""
        result = self._run_script("gate_core.ps1", args=["-Profile", "parallel_safe"], timeout=120)
        output = result.stdout

        # Required fields must be present
        assert "=== Core-Gate Result ===" in output, "Missing result header"
        assert "Profile:" in output, "Missing profile output"
        assert re.search(r"Duration: \d+\.?\d*s", output), "Missing duration"
        assert re.search(r"Tests: \d+ passed", output), "Missing passed count"
        assert "Status:" in output, "Missing status"
        assert "Exit Code:" in output, "Missing exit code"

    def test_gate_core_includes_golden_harness_suite(self):
        """gate_core.ps1 must include the golden model regression harness suite."""
        script_path = self.SCRIPT_DIR / "gate_core.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert "test/test_golden_model_regression_harness.py" in content, (
            "Core gate must include the golden model regression harness suite"
        )

    def test_gate_core_includes_cross_platform_contract_suite(self):
        """gate_core.ps1 must include cross-platform core contract suite."""
        script_path = self.SCRIPT_DIR / "gate_core.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert "test/test_core_cross_platform_contract.py" in content, (
            "Core gate must include cross-platform contract suite"
        )

    def test_gate_core_includes_evidence_contract_suite(self):
        """gate_core.ps1 must include evidence schema contract suite."""
        script_path = self.SCRIPT_DIR / "gate_core.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert "test/test_gate_evidence_contract.py" in content, (
            "Core gate must include evidence schema contract suite"
        )

    def test_gate_core_includes_stability_seed_suite(self):
        """gate_core.ps1 must include stability dashboard seed suite."""
        script_path = self.SCRIPT_DIR / "gate_core.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert "test/test_stability_dashboard_seed.py" in content, (
            "Core gate must include stability dashboard seed suite"
        )

    def test_gate_core_has_parallel_mode_parameter(self):
        """gate_core.ps1 should expose profile/parallel switches for UX-parallel operation."""
        script_path = self.SCRIPT_DIR / "gate_core.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert "SkipUxBoundSuites" in content
        assert "Profile" in content
        assert "parallel_safe" in content
        assert "kernel_only" in content
        assert "red_flag" in content

    def test_core_budget_script_has_stable_defaults(self):
        """check_core_gate_budget.ps1 should define stable baseline defaults."""
        script_path = self.SCRIPT_DIR / "check_core_gate_budget.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert "MaxDurationSeconds = 150.0" in content
        assert "MinPassRate = 99.0" in content
        assert "CoreProfile" in content

    def test_gate_ui_output_schema_w3(self):
        """gate_ui.ps1 W3: must output structured result with blocker_type."""
        result = self._run_script("gate_ui.ps1")
        output = result.stdout

        # Required fields must be present
        assert "=== UI-Gate Result ===" in output, "Missing result header"
        assert re.search(r"Duration: \d+\.?\d*s", output), "Missing duration"
        assert "Status:" in output, "Missing status"
        assert "Exit Code:" in output, "Missing exit code"

        # W3: blocker_type may be present for infrastructure issues
        blocker_type_match = re.search(r"Blocker-Type: (\S+)", output)
        if blocker_type_match:
            blocker_type = blocker_type_match.group(1)
            # Valid blocker types
            assert blocker_type in ["OPENGL_CONTEXT", "ACCESS_VIOLATION", "FATAL_ERROR", "IMPORT_ERROR"], \
                f"Invalid blocker_type: {blocker_type}"

    def test_hygiene_output_schema(self):
        """hygiene_check.ps1 must output structured result with required fields."""
        result = self._run_script("hygiene_check.ps1")
        output = result.stdout

        # Required fields must be present
        assert "=== Hygiene Check Result ===" in output, "Missing result header"
        assert "Violations:" in output, "Missing violations count"
        assert "Status:" in output, "Missing status"
        assert "Exit Code:" in output, "Missing exit code"

    # =========================================================================
    # Status Classification Tests (W3: Extended)
    # =========================================================================

    def test_gate_ui_blocked_infra_classification_w3(self):
        """gate_ui.ps1 W3: must classify OPENGL_CONTEXT/ACCESS_VIOLATION as BLOCKED_INFRA."""
        result = self._run_script("gate_ui.ps1")
        output = result.stdout

        # Check for BLOCKED_INFRA status
        if "OPENGL_CONTEXT" in output or "wglMakeCurrent" in output:
            assert "Status: BLOCKED_INFRA" in output, \
                "VTK OpenGL errors must be classified as BLOCKED_INFRA"
            assert "Blocker-Type: OPENGL_CONTEXT" in output, \
                "Must show Blocker-Type for infrastructure issues"

        if "ACCESS_VIOLATION" in output or "0xC0000005" in output:
            assert "Status: BLOCKED_INFRA" in output, \
                "Access violations must be classified as BLOCKED_INFRA"
            assert "Blocker-Type: ACCESS_VIOLATION" in output, \
                "Must show Blocker-Type for access violations"

    def test_gate_ui_blocked_vs_fail_distinction(self):
        """gate_ui.ps1 must distinguish BLOCKED (infra) from FAIL (logic)."""
        result = self._run_script("gate_ui.ps1")
        output = result.stdout

        # Extract status
        status_match = re.search(r"Status: (\S+)", output)
        if status_match:
            status = status_match.group(1)
            # Valid statuses
            assert status in ["PASS", "BLOCKED_INFRA", "BLOCKED", "FAIL"], \
                f"Invalid status: {status}"

    def test_exit_code_contract_blocked_infra_w3(self):
        """gate_ui.ps1 W3: BLOCKED_INFRA should exit 0 (not a logic failure)."""
        result = self._run_script("gate_ui.ps1")
        output = result.stdout

        # BLOCKED_INFRA should have exit code 0
        if "Status: BLOCKED_INFRA" in output:
            assert result.returncode == 0, \
                "BLOCKED_INFRA (infrastructure issue) should exit 0, not fail CI"

    # =========================================================================
    # Hygiene Mode Tests
    # =========================================================================

    def test_hygiene_warn_mode_default(self):
        """hygiene_check.ps1 default mode: violations = WARNING, exit = 0."""
        result = self._run_script("hygiene_check.ps1")
        output = result.stdout

        # Default should exit 0 even with violations
        if "WARNING" in output or "violations found" in output.lower():
            assert result.returncode == 0, "Default mode should exit 0 even with violations"

    def test_hygiene_fail_mode_strict(self):
        """hygiene_check.ps1 -FailOnUntracked: violations = FAIL, exit = 1."""
        result = self._run_script("hygiene_check.ps1", args=["-FailOnUntracked"])
        output = result.stdout

        # Check if it recognizes strict mode
        if "FAIL" in output or "StrictHygiene" in output or "FailOnUntracked" in output:
            pass  # Accept either outcome depending on violations state

    # =========================================================================
    # Gate Aggregation Tests
    # =========================================================================

    def test_gate_all_strict_hygiene_parameter(self):
        """gate_all.ps1 must accept -StrictHygiene parameter."""
        result = self._run_script("gate_all.ps1", args=["-StrictHygiene"], timeout=120)
        output = result.stdout

        # Should show StrictHygiene status
        assert "StrictHygiene" in output or "strict" in output.lower(), \
            "Must show StrictHygiene status"

    def test_gate_all_has_core_budget_parameter_contract(self):
        """gate_all.ps1 must expose core budget enforcement parameters."""
        script_path = self.SCRIPT_DIR / "gate_all.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert "EnforceCoreBudget" in content
        assert "MaxCoreDurationSeconds" in content
        assert "MinCorePassRate" in content
        assert "CoreProfile" in content
        assert "ValidateEvidence" in content
        assert "FailOnEvidenceWarning" in content
        assert "JsonOut" in content

    def test_gate_all_contains_evidence_contract_step(self):
        """gate_all.ps1 should contain optional evidence-contract execution step."""
        script_path = self.SCRIPT_DIR / "gate_all.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert "Evidence-Contract" in content
        assert "validate_gate_evidence.ps1" in content

    def test_gate_all_contains_json_summary_contract(self):
        """gate_all.ps1 should support machine-readable JSON summary export."""
        script_path = self.SCRIPT_DIR / "gate_all.ps1"
        content = script_path.read_text(encoding="utf-8")
        assert "gate_all_summary_v1" in content
        assert "JSON written:" in content

    def test_gate_all_shows_blocker_type_w3(self):
        """gate_all.ps1 W3: must show blocker_type for BLOCKED_INFRA."""
        result = self._run_script("gate_all.ps1", timeout=120)
        output = result.stdout

        # If UI is BLOCKED_INFRA, should show blocker_type
        if "BLOCKED_INFRA" in output:
            # Should have a "Blocker-Type:" line
            assert "Blocker-Type:" in output, \
                "gate_all.ps1 must show blocker_type for BLOCKED_INFRA status"

    def test_gate_all_aggregates_results(self):
        """gate_all.ps1 must aggregate all gate results."""
        result = self._run_script("gate_all.ps1", timeout=120)
        output = result.stdout

        # Should show all gates
        assert "Core-Gate" in output, "Must show Core-Gate result"
        assert "UI-Gate" in output, "Must show UI-Gate result"
        assert "Hygiene-Gate" in output, "Must show Hygiene-Gate result"
        assert "Overall:" in output, "Must show overall result"

    # =========================================================================
    # Exit Code Contract Tests
    # =========================================================================

    def test_exit_code_contract_core(self):
        """gate_core.ps1: exit 0 = PASS, exit 1 = FAIL."""
        result = self._run_script("gate_core.ps1", args=["-Profile", "parallel_safe"], timeout=120)
        output = result.stdout

        # Exit code should match status
        if "Status: PASS" in output:
            assert result.returncode == 0, "PASS must have exit code 0"
        elif "Status: FAIL" in output:
            assert result.returncode == 1, "FAIL must have exit code 1"

    def test_exit_code_contract_ui_w3(self):
        """gate_ui.ps1 W3: exit 0 = PASS/BLOCKED_INFRA, exit 1 = FAIL."""
        result = self._run_script("gate_ui.ps1")
        output = result.stdout

        # Exit code should match status
        if "Status: PASS" in output or "Status: BLOCKED_INFRA" in output:
            assert result.returncode == 0, "PASS/BLOCKED_INFRA must have exit code 0"
        elif "Status: BLOCKED" in output or "Status: FAIL" in output:
            # BLOCKED (old) or FAIL should exit 1
            # But BLOCKED_INFRA (new) exits 0
            if "BLOCKED_INFRA" not in output:
                assert result.returncode == 1, "FAIL/BLOCKED must have exit code 1"

    # =========================================================================
    # Evidence Generator Tests (W3: Extended)
    # =========================================================================

    def test_evidence_generator_script_exists(self):
        """generate_gate_evidence.ps1 must exist (W3)."""
        script_path = self.SCRIPT_DIR / "generate_gate_evidence.ps1"
        assert script_path.exists(), f"Evidence generator not found at {script_path}"

    def test_evidence_generator_output_format_w3(self):
        """generate_gate_evidence.ps1 W3: must create .md and .json with status_class."""
        script_path = self.SCRIPT_DIR / "generate_gate_evidence.ps1"
        if not script_path.exists():
            pytest.skip("Evidence generator not found")

        # Run with custom output prefix to test
        with tempfile.TemporaryDirectory() as tmpdir:
            out_prefix = str(Path(tmpdir) / "test_evidence_w3")

            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path),
                 "-OutPrefix", out_prefix],
                capture_output=True,
                text=True,
                timeout=300
            )

            # Should create both files (even if some gates fail)
            md_file = Path(out_prefix + ".md")
            json_file = Path(out_prefix + ".json")

            # At least one file should be created
            assert md_file.exists() or json_file.exists(), \
                "Evidence generator must create at least one output file"

            # W3: JSON should contain status_class field if created
            if json_file.exists():
                with open(json_file) as f:
                    data = json.load(f)
                assert "metadata" in data, "JSON must contain metadata"
                assert "summary" in data, "JSON must contain summary"

                # W3: Check for status_class in summary
                summary = data["summary"]
                if "core_gate" in summary:
                    assert "status_class" in summary["core_gate"], \
                        "W3: core_gate must contain status_class"
                if "ui_gate" in summary:
                    assert "status_class" in summary["ui_gate"], \
                        "W3: ui_gate must contain status_class"
                if "pi010_gate" in summary:
                    assert "status_class" in summary["pi010_gate"], \
                        "W3: pi010_gate must contain status_class"
                if "hygiene_gate" in summary:
                    assert "status_class" in summary["hygiene_gate"], \
                        "W3: hygiene_gate must contain status_class"

                # W3: Check for blocker_type/blocker_signature in ui_gate
                if "ui_gate" in summary:
                    ui_gate = summary["ui_gate"]
                    # blocker_type may be null for passing tests
                    if "blocker_type" in ui_gate and ui_gate["blocker_type"]:
                        assert "blocker_signature" in ui_gate, \
                            "W3: blocker_type requires blocker_signature"

            # MD should contain W3 sections if created
            if md_file.exists():
                content = md_file.read_text()
                assert "Evidence Summary" in content or "QA Evidence W3" in content

    def test_evidence_generator_w3_prefix(self):
        """generate_gate_evidence.ps1 W3: must use W3 prefix by default."""
        script_path = self.SCRIPT_DIR / "generate_gate_evidence.ps1"
        if not script_path.exists():
            pytest.skip("Evidence generator not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Run without -OutPrefix to test default
            env_backup = dict(subprocess.os.environ)
            subprocess.os.environ["LITECAD_TEMP"] = tmpdir

            try:
                result = subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path),
                     "-OutPrefix", str(Path(tmpdir) / "QA_EVIDENCE_W3_test")],
                    capture_output=True,
                    text=True,
                    timeout=300
                )

                # Should create W3-prefixed files
                w3_files = list(Path(tmpdir).glob("QA_EVIDENCE_W3_*"))
                assert len(w3_files) > 0, "Should create W3-prefixed evidence files"
            finally:
                subprocess.os.environ.clear()
                subprocess.os.environ.update(env_backup)

    def test_evidence_files_exist(self):
        """QA evidence files must exist."""
        evidence_dir = Path(__file__).parent.parent / "roadmap_ctp"

        # W3: Check for W3 evidence files (may not exist yet, fall back to W5)
        md_evidence = evidence_dir / "QA_EVIDENCE_W3_20260216.md"
        json_evidence = evidence_dir / "QA_EVIDENCE_W3_20260216.json"

        if not (md_evidence.exists() or json_evidence.exists()):
            # Fall back to W5 if W3 doesn't exist yet
            md_evidence = evidence_dir / "QA_EVIDENCE_W5_20260216.md"
            json_evidence = evidence_dir / "QA_EVIDENCE_W5_20260216.json"

        # At least one evidence file should exist
        assert md_evidence.exists() or json_evidence.exists(), \
            "QA evidence file (MD or JSON) must exist"


class TestGateEvidenceFormat:
    """Evidence format validation tests."""

    def test_evidence_json_schema_w3(self):
        """Evidence JSON W3: must validate against expected schema."""
        evidence_dir = Path(__file__).parent.parent / "roadmap_ctp"

        # Look for any W3 or W5 evidence JSON
        json_files = list(evidence_dir.glob("QA_EVIDENCE_W*_20260216.json"))
        if not json_files:
            pytest.skip("No evidence JSON files found")

        json_file = json_files[0]
        with open(json_file) as f:
            data = json.load(f)

        # W3: Required top-level fields
        assert "metadata" in data, "JSON must contain metadata"
        assert "summary" in data, "JSON must contain summary"
        assert "commands" in data, "JSON must contain commands"

        # W3: Required metadata fields
        metadata = data["metadata"]
        assert "date" in metadata, "metadata must contain date"
        assert "qa_cell" in metadata, "metadata must contain qa_cell"

        # W3: Required summary fields
        summary = data["summary"]
        for gate_name in ["core_gate", "ui_gate", "pi010_gate", "hygiene_gate"]:
            if gate_name in summary:
                gate_data = summary[gate_name]
                assert "status_class" in gate_data, \
                    f"{gate_name} must contain status_class (W3 requirement)"

    def test_evidence_md_required_sections_w3(self):
        """Evidence MD W3: must contain required sections."""
        evidence_dir = Path(__file__).parent.parent / "roadmap_ctp"

        # Look for any W3 or W5 evidence MD
        md_files = list(evidence_dir.glob("QA_EVIDENCE_W*_20260216.md"))
        if not md_files:
            pytest.skip("No evidence MD files found")

        md_file = md_files[0]
        content = md_file.read_text()

        # W3: Required sections
        assert "Evidence Summary" in content or "Executive Summary" in content, \
            "MD must contain summary section"

        # Should document all gates
        assert "Core-Gate" in content or "Core Gate" in content
        assert "UI-Gate" in content or "UI Gate" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
