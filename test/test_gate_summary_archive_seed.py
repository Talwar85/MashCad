import json
import subprocess
from pathlib import Path


def _archive_script() -> Path:
    return Path(__file__).parent.parent / "scripts" / "archive_gate_summary.ps1"


def _write_gate_all_summary(path: Path, *, ts: str, status: str, profile: str = "parallel_safe") -> None:
    payload = {
        "metadata": {
            "generated_at": ts,
            "schema": "gate_all_summary_v1",
        },
        "config": {
            "core_profile": profile,
        },
        "gates": [
            {
                "name": "Core-Gate",
                "status": status,
                "profile": profile,
                "pass_rate": 99.0,
                "duration_seconds": 10.0,
            }
        ],
        "overall": {
            "status": status,
            "exit_code": 0 if status == "PASS" else 1,
            "duration_seconds": 11.0,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_archive_gate_summary_writes_index_and_markdown(tmp_path):
    summary = tmp_path / "gate_all_summary.json"
    archive_dir = tmp_path / "archive"
    _write_gate_all_summary(
        summary,
        ts="2026-02-16T12:00:00",
        status="PASS",
        profile="red_flag",
    )

    result = subprocess.run(
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
            "5",
            "-WriteMarkdownIndex",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr

    archived = list(archive_dir.glob("gate_all_summary_*.json"))
    assert len(archived) == 1

    index_json = archive_dir / "index.json"
    index_md = archive_dir / "index.md"
    assert index_json.exists()
    assert index_md.exists()

    payload = json.loads(index_json.read_text(encoding="utf-8-sig"))
    assert payload["metadata"]["schema"] == "gate_summary_archive_index_v1"
    assert payload["metadata"]["max_files"] == 5
    assert payload["latest"]["file"].startswith("gate_all_summary_")
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["overall_status"] == "PASS"
    assert payload["entries"][0]["core_status"] == "PASS"
    assert payload["entries"][0]["core_profile"] == "red_flag"


def test_archive_gate_summary_applies_retention(tmp_path):
    archive_dir = tmp_path / "archive"
    inputs = [
        ("2026-02-16T12:00:00", "PASS"),
        ("2026-02-16T12:01:00", "FAIL"),
        ("2026-02-16T12:02:00", "PASS"),
    ]

    for idx, (ts, status) in enumerate(inputs, start=1):
        summary = tmp_path / f"summary_{idx}.json"
        _write_gate_all_summary(summary, ts=ts, status=status)
        result = subprocess.run(
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
                "2",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + "\n" + result.stderr

    archived = sorted(archive_dir.glob("gate_all_summary_*.json"))
    assert len(archived) == 2
    assert not any("120000" in p.name for p in archived)
    assert any("120100" in p.name for p in archived)
    assert any("120200" in p.name for p in archived)

    payload = json.loads((archive_dir / "index.json").read_text(encoding="utf-8-sig"))
    assert len(payload["entries"]) == 2


def test_archive_gate_summary_rejects_wrong_schema(tmp_path):
    bad_json = tmp_path / "bad_summary.json"
    bad_payload = {
        "metadata": {
            "generated_at": "2026-02-16T12:00:00",
            "schema": "not_gate_all",
        }
    }
    bad_json.write_text(json.dumps(bad_payload), encoding="utf-8")

    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_archive_script()),
            "-InputJson",
            str(bad_json),
            "-ArchiveDir",
            str(tmp_path / "archive"),
            "-MaxFiles",
            "5",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 1
    combined = result.stdout + "\n" + result.stderr
    assert "gate_all_summary_v1" in combined
