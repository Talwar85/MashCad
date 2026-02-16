import json
import subprocess
from pathlib import Path


def _dashboard_script() -> Path:
    return Path(__file__).parent.parent / "scripts" / "generate_core_ops_dashboard.ps1"


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_generate_core_ops_dashboard_combines_matrix_and_trend(tmp_path):
    matrix = {
        "metadata": {"schema": "core_profile_matrix_v1"},
        "profiles": {
            "full": {"suite_count": 16},
            "parallel_safe": {"suite_count": 15},
            "kernel_only": {"suite_count": 13},
            "red_flag": {"suite_count": 6},
        },
        "deltas": {
            "removed_from_full_parallel_safe": ["test/test_feature_commands_atomic.py"],
            "removed_from_full_kernel_only": ["test/test_gate_evidence_contract.py"],
            "removed_from_full_red_flag": ["test/test_feature_flags.py"],
        },
    }
    trend = {
        "metadata": {"schema": "core_gate_trend_v1", "runs_tracked": 2},
        "metrics": {"pass_count": 1, "fail_count": 1, "other_count": 0, "avg_duration_seconds": 55.5},
        "latest": {
            "timestamp": "2026-02-16T12:00:00",
            "status": "PASS",
            "pass_rate": 99.3,
            "duration_seconds": 50.0,
            "profile": "parallel_safe",
            "file": "gate_all_summary_red_flag.json",
        },
    }

    matrix_path = tmp_path / "matrix.json"
    trend_path = tmp_path / "trend.json"
    out_prefix = tmp_path / "core_ops_dashboard"
    _write_json(matrix_path, matrix)
    _write_json(trend_path, trend)

    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_dashboard_script()),
            "-MatrixJson",
            str(matrix_path),
            "-TrendJson",
            str(trend_path),
            "-OutPrefix",
            str(out_prefix),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr

    json_file = Path(str(out_prefix) + ".json")
    md_file = Path(str(out_prefix) + ".md")
    assert json_file.exists()
    assert md_file.exists()

    payload = json.loads(json_file.read_text(encoding="utf-8-sig"))
    assert payload["metadata"]["schema"] == "core_ops_dashboard_v1"
    assert payload["profile_overview"]["full_suite_count"] == 16
    assert payload["profile_overview"]["red_flag_suite_count"] == 6
    assert payload["trend_overview"]["runs_tracked"] == 2
    assert payload["trend_overview"]["pass_rate_percent"] == 50.0
    assert payload["latest_core"]["status"] == "PASS"
