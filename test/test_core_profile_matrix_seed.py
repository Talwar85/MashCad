import json
import subprocess
from pathlib import Path


def _matrix_script() -> Path:
    return Path(__file__).parent.parent / "scripts" / "generate_core_profile_matrix.ps1"


def test_generate_core_profile_matrix_outputs_json_and_md(tmp_path):
    out_prefix = tmp_path / "core_profile_matrix"
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_matrix_script()),
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
    assert payload["metadata"]["schema"] == "core_profile_matrix_v1"

    full_count = payload["profiles"]["full"]["suite_count"]
    parallel_count = payload["profiles"]["parallel_safe"]["suite_count"]
    kernel_count = payload["profiles"]["kernel_only"]["suite_count"]
    red_flag_count = payload["profiles"]["red_flag"]["suite_count"]
    assert full_count >= parallel_count >= kernel_count >= red_flag_count

    removed_parallel = payload["deltas"]["removed_from_full_parallel_safe"]
    removed_kernel = payload["deltas"]["removed_from_full_kernel_only"]
    removed_red_flag = payload["deltas"]["removed_from_full_red_flag"]
    assert "test/test_feature_commands_atomic.py" in removed_parallel
    assert "test/test_gate_evidence_contract.py" in removed_kernel
    assert "test/test_stability_dashboard_seed.py" in removed_kernel
    assert "test/test_showstopper_red_flag_pack.py" not in removed_red_flag
