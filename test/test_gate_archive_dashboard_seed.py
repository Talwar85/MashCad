import json
import subprocess
from pathlib import Path


def _archive_script() -> Path:
    return Path(__file__).parent.parent / "scripts" / "archive_gate_summary.ps1"


def _validator_script() -> Path:
    return Path(__file__).parent.parent / "scripts" / "validate_gate_summary_archive.ps1"


def _dashboard_script() -> Path:
    return Path(__file__).parent.parent / "scripts" / "generate_gate_archive_dashboard.ps1"


def _write_gate_all_summary(path: Path, *, ts: str, status: str, profile: str) -> None:
    payload = {
        "metadata": {"generated_at": ts, "schema": "gate_all_summary_v1"},
        "gates": [
            {
                "name": "Core-Gate",
                "status": status,
                "profile": profile,
                "pass_rate": 99.1,
                "duration_seconds": 12.0,
            }
        ],
        "overall": {"status": status, "exit_code": 0 if status == "PASS" else 1, "duration_seconds": 13.0},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _run_archive(summary: Path, archive_dir: Path, max_files: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_archive_script()),
            "-InputJson",
            str(summary),
            "-ArchiveDir",
            str(archive_dir),
            "-MaxFiles",
            str(max_files),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_validate_archive_passes_and_writes_json(tmp_path):
    archive_dir = tmp_path / "archive"
    s1 = tmp_path / "s1.json"
    s2 = tmp_path / "s2.json"
    _write_gate_all_summary(s1, ts="2026-02-16T12:00:00", status="PASS", profile="red_flag")
    _write_gate_all_summary(s2, ts="2026-02-16T12:01:00", status="FAIL", profile="parallel_safe")
    assert _run_archive(s1, archive_dir, max_files=5).returncode == 0
    assert _run_archive(s2, archive_dir, max_files=5).returncode == 0

    validation_json = tmp_path / "validation.json"
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_validator_script()),
            "-ArchiveDir",
            str(archive_dir),
            "-JsonOut",
            str(validation_json),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    payload = json.loads(validation_json.read_text(encoding="utf-8-sig"))
    assert payload["metadata"]["schema"] == "gate_summary_archive_validation_v1"
    assert payload["summary"]["entries_checked"] == 2
    assert payload["summary"]["violation_count"] == 0


def test_validate_archive_fails_when_archive_file_missing(tmp_path):
    archive_dir = tmp_path / "archive"
    s1 = tmp_path / "s1.json"
    _write_gate_all_summary(s1, ts="2026-02-16T12:00:00", status="PASS", profile="full")
    assert _run_archive(s1, archive_dir, max_files=5).returncode == 0

    archived = list(archive_dir.glob("gate_all_summary_*.json"))
    assert len(archived) == 1
    archived[0].unlink()

    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_validator_script()),
            "-ArchiveDir",
            str(archive_dir),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 1
    combined = result.stdout + "\n" + result.stderr
    assert "Missing archive file" in combined


def test_generate_archive_dashboard_outputs_json_and_md(tmp_path):
    archive_dir = tmp_path / "archive"
    s1 = tmp_path / "s1.json"
    s2 = tmp_path / "s2.json"
    _write_gate_all_summary(s1, ts="2026-02-16T12:00:00", status="PASS", profile="red_flag")
    _write_gate_all_summary(s2, ts="2026-02-16T12:01:00", status="FAIL", profile="parallel_safe")
    assert _run_archive(s1, archive_dir, max_files=5).returncode == 0
    assert _run_archive(s2, archive_dir, max_files=5).returncode == 0

    out_prefix = tmp_path / "archive_dashboard"
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_dashboard_script()),
            "-ArchiveDir",
            str(archive_dir),
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
    assert payload["metadata"]["schema"] == "gate_summary_archive_dashboard_v1"
    assert payload["capacity"]["entries_total"] == 2
    assert payload["counts"]["overall_status"]["PASS"] == 1
    assert payload["counts"]["overall_status"]["FAIL"] == 1
