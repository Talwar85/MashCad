import json
import subprocess
from pathlib import Path


def _validator_script() -> Path:
    return Path(__file__).parent.parent / "scripts" / "validate_gate_evidence.ps1"


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _run_validator(evidence_path: Path, *, fail_on_warning: bool = False) -> subprocess.CompletedProcess:
    cmd = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(_validator_script()),
        "-EvidencePath",
        str(evidence_path),
    ]
    if fail_on_warning:
        cmd.append("-FailOnWarning")
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _valid_payload() -> dict:
    return {
        "metadata": {
            "date": "2026-02-16",
            "time": "23:59:00",
            "branch": "feature/v1-ux-aiB",
        },
        "delivery_metrics": {
            "delivery_completion_ratio": 0.95,
            "validation_runtime_seconds": 120.0,
            "blocker_type": None,
            "failed_suite_count": 0,
            "error_suite_count": 0,
            "total_tests": 132,
            "total_passed": 125,
        },
        "summary": {
            "core_gate": {
                "status": "PASS",
                "passed": 100,
                "failed": 0,
                "skipped": 0,
                "errors": 0,
                "duration_seconds": 10.0,
            },
            "ui_gate": {
                "status": "PASS",
                "passed": 20,
                "failed": 0,
                "skipped": 0,
                "errors": 0,
                "duration_seconds": 5.0,
            },
            "pi010_gate": {
                "status": "PASS",
                "passed": 12,
                "failed": 0,
                "skipped": 0,
                "errors": 0,
                "duration_seconds": 3.5,
            },
            "hygiene_gate": {
                "status": "CLEAN",
                "violations_count": 0,
                "duration_seconds": 1.0,
            },
        },
    }


def test_validate_gate_evidence_passes_on_valid_schema(tmp_path):
    evidence = tmp_path / "QA_EVIDENCE_WX.json"
    _write_json(evidence, _valid_payload())

    result = _run_validator(evidence)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "[PASS]" in result.stdout


def test_validate_gate_evidence_fails_on_core_status_semantic_mismatch(tmp_path):
    payload = _valid_payload()
    payload["summary"]["core_gate"]["failed"] = 2
    payload["summary"]["core_gate"]["status"] = "PASS"

    evidence = tmp_path / "QA_EVIDENCE_BAD.json"
    _write_json(evidence, payload)

    result = _run_validator(evidence)
    assert result.returncode == 1
    assert "gate_semantics_invalid" in result.stdout


def test_validate_gate_evidence_warning_exit_policy(tmp_path):
    payload = _valid_payload()
    payload["summary"]["ui_gate"]["status"] = "BLOCKED"
    payload["summary"]["ui_gate"].pop("blocker", None)
    payload["summary"]["ui_gate"].pop("blocker_type", None)

    evidence = tmp_path / "QA_EVIDENCE_WARN.json"
    _write_json(evidence, payload)

    relaxed = _run_validator(evidence, fail_on_warning=False)
    strict = _run_validator(evidence, fail_on_warning=True)

    assert relaxed.returncode == 0, relaxed.stdout + "\n" + relaxed.stderr
    assert strict.returncode == 1, strict.stdout + "\n" + strict.stderr
