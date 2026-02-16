import json
import subprocess
from pathlib import Path


def _write_evidence(path: Path, *, date: str, time: str, core_status: str, core_duration: float, ui_status: str, blocker_type: str | None):
    payload = {
        "metadata": {
            "date": date,
            "time": time,
            "toolchain": {"platform": "win32"},
        },
        "summary": {
            "core_gate": {
                "status_class": core_status,
                "duration_seconds": core_duration,
                "passed": 100,
                "failed": 0,
                "skipped": 0,
                "errors": 0,
            },
            "ui_gate": {
                "status_class": ui_status,
                "duration_seconds": 12.0,
                "passed": 10,
                "failed": 0,
                "skipped": 0,
                "errors": 0,
                "blocker_type": blocker_type,
            },
            "pi010_gate": {"status_class": "PASS", "duration_seconds": 3.0},
            "hygiene_gate": {"status_class": "WARNING", "duration_seconds": 1.0},
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_generate_stability_dashboard_outputs_json_and_md(tmp_path):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    _write_evidence(
        evidence_dir / "QA_EVIDENCE_W3_20260216_101500.json",
        date="2026-02-16",
        time="10:15:00",
        core_status="PASS",
        core_duration=84.0,
        ui_status="BLOCKED_INFRA",
        blocker_type="OPENGL_CONTEXT",
    )
    _write_evidence(
        evidence_dir / "QA_EVIDENCE_W3_20260216_111500.json",
        date="2026-02-16",
        time="11:15:00",
        core_status="PASS",
        core_duration=82.0,
        ui_status="PASS",
        blocker_type=None,
    )

    out_prefix = tmp_path / "dashboard_seed"
    script = Path(__file__).parent.parent / "scripts" / "generate_stability_dashboard.ps1"
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-EvidenceDir",
            str(evidence_dir),
            "-Pattern",
            "QA_EVIDENCE_W*.json",
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

    data = json.loads(json_file.read_text(encoding="utf-8-sig"))
    assert data["metadata"]["schema"] == "stability_dashboard_seed_v1"
    assert data["metadata"]["runs_tracked"] == 2
    assert data["metrics"]["core_pass_count"] == 2
    assert data["metrics"]["ui_blocked_infra_count"] == 1
    assert data["latest"]["ui_gate"]["status"] == "PASS"


def test_generate_stability_dashboard_fails_without_input(tmp_path):
    evidence_dir = tmp_path / "empty"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    out_prefix = tmp_path / "dashboard_empty"
    script = Path(__file__).parent.parent / "scripts" / "generate_stability_dashboard.ps1"

    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-EvidenceDir",
            str(evidence_dir),
            "-Pattern",
            "QA_EVIDENCE_W*.json",
            "-OutPrefix",
            str(out_prefix),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1
