import json
import subprocess
from pathlib import Path


def _trend_script() -> Path:
    return Path(__file__).parent.parent / "scripts" / "generate_core_gate_trend.ps1"


def _write_gate_all_summary(path: Path, *, ts: str, status: str, pass_rate: float, duration: float, profile: str) -> None:
    payload = {
        "metadata": {
            "generated_at": ts,
            "schema": "gate_all_summary_v1",
        },
        "gates": [
            {
                "name": "Core-Gate",
                "status": status,
                "pass_rate": pass_rate,
                "duration_seconds": duration,
                "profile": profile,
            }
        ],
        "overall": {"status": "PASS", "exit_code": 0, "duration_seconds": duration + 1.0},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_generate_core_gate_trend_outputs_json_and_md(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)

    _write_gate_all_summary(
        evidence / "gate_all_summary_1.json",
        ts="2026-02-16T10:00:00",
        status="PASS",
        pass_rate=99.3,
        duration=100.0,
        profile="parallel_safe",
    )
    _write_gate_all_summary(
        evidence / "gate_all_summary_2.json",
        ts="2026-02-16T11:00:00",
        status="FAIL",
        pass_rate=97.2,
        duration=120.0,
        profile="full",
    )

    out_prefix = tmp_path / "core_gate_trend"
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_trend_script()),
            "-EvidenceDir",
            str(evidence),
            "-Pattern",
            "gate_all_summary*.json",
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
    assert payload["metadata"]["schema"] == "core_gate_trend_v1"
    assert payload["metadata"]["runs_tracked"] == 2
    assert payload["metrics"]["pass_count"] == 1
    assert payload["metrics"]["fail_count"] == 1
    assert payload["latest"]["status"] == "FAIL"
    assert payload["latest"]["profile"] == "full"
