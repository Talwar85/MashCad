import json
import subprocess
from pathlib import Path


def _gate_core_script() -> Path:
    return Path(__file__).parent.parent / "scripts" / "gate_core.ps1"


def _run_gate_core(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    cmd = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(_gate_core_script()),
        *args,
    ]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_gate_core_dry_run_full_includes_feature_commands_atomic():
    result = _run_gate_core("-Profile", "full", "-DryRun")
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "Profile: full" in result.stdout
    assert "test/test_feature_commands_atomic.py" in result.stdout


def test_gate_core_dry_run_parallel_safe_excludes_feature_commands_atomic():
    result = _run_gate_core("-Profile", "parallel_safe", "-DryRun")
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "Profile: parallel_safe" in result.stdout
    assert "test/test_feature_commands_atomic.py" not in result.stdout


def test_gate_core_dry_run_kernel_only_excludes_non_kernel_contract_suites():
    result = _run_gate_core("-Profile", "kernel_only", "-DryRun")
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "Profile: kernel_only" in result.stdout
    assert "test/test_feature_commands_atomic.py" not in result.stdout
    assert "test/test_gate_evidence_contract.py" not in result.stdout
    assert "test/test_stability_dashboard_seed.py" not in result.stdout


def test_gate_core_dry_run_json_manifest(tmp_path):
    out = tmp_path / "core_gate_manifest.json"
    result = _run_gate_core("-Profile", "parallel_safe", "-DryRun", "-JsonOut", str(out))
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert out.exists()

    payload = json.loads(out.read_text(encoding="utf-8-sig"))
    assert payload["profile"] == "parallel_safe"
    assert payload["dry_run"] is True
    assert payload["status"] == "DRY_RUN"
    assert "test/test_feature_commands_atomic.py" not in payload["suites"]


def test_gate_core_dry_run_red_flag_profile_contains_showstopper_pack():
    result = _run_gate_core("-Profile", "red_flag", "-DryRun")
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "Profile: red_flag" in result.stdout
    assert "test/test_showstopper_red_flag_pack.py" in result.stdout
    assert "test/test_feature_error_status.py" in result.stdout
    assert "test/test_feature_commands_atomic.py" not in result.stdout
