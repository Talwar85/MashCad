import hashlib
import json
import sys
from pathlib import Path

import pytest

from modeling import Body

sys.path.insert(0, str(Path(__file__).resolve().parent))
import golden_harness_utils as gh


_CROSS_PLATFORM_SEEDS = (0, 3, 7)

# Win32 baseline captured on 2026-02-16 (feature/v1-ux-aiB).
_PLATFORM_BASELINES = {
    "win32": {
        "faces_total": 18,
        "edges_total": 36,
        "volume_total": 19426.14,
        "bbox_sum": (-1.2, -2.4, -0.6, 68.3, 59.9, 39.4),
        "digests": (
            "aea8df7126d3c430b7f222ff690cec18322698e95b78cde88df97220f2e5f452",
            "d5e8a82041d2b85efb734bfd3583d369d5f8e5cce0d5de5822520ffba43650f2",
            "7a92c84159e477d265f1b63a89127e5d5d75eec3878d8b02fe853311f6993978",
        ),
        "summary_digest": "2a4a6bfe819a5ec7b63a331c5eaf353953db8a38275cdd253f88ad7941fe8a3e",
    },
}


def _platform_key() -> str:
    if sys.platform.startswith("win"):
        return "win32"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform.startswith("darwin"):
        return "darwin"
    return sys.platform


def _collect_platform_snapshot() -> dict:
    acc = {"faces_total": 0, "edges_total": 0, "volume_total": 0.0, "bbox_sum": [0.0] * 6, "digests": []}
    for seed in _CROSS_PLATFORM_SEEDS:
        _, body = gh.build_reference_model(seed)
        sig = gh.solid_signature(body._build123d_solid)
        acc["faces_total"] += int(sig["faces"])
        acc["edges_total"] += int(sig["edges"])
        acc["volume_total"] += float(sig["volume"])
        acc["digests"].append(gh.signature_digest(sig))
        for i, v in enumerate(sig["bbox"]):
            acc["bbox_sum"][i] += float(v)

    payload = {
        "platform": _platform_key(),
        "seeds": list(_CROSS_PLATFORM_SEEDS),
        "faces_total": int(acc["faces_total"]),
        "edges_total": int(acc["edges_total"]),
        "volume_total": round(float(acc["volume_total"]), 6),
        "bbox_sum": tuple(round(float(v), 6) for v in acc["bbox_sum"]),
        "digests": tuple(acc["digests"]),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["summary_digest"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def test_cross_platform_error_code_classification_contract_matrix():
    expected = {
        "tnp_ref_missing": ("ERROR", "error"),
        "tnp_ref_mismatch": ("ERROR", "error"),
        "tnp_ref_drift": ("WARNING_RECOVERABLE", "warning"),
        "fallback_used": ("WARNING_RECOVERABLE", "warning"),
        "blocked_by_upstream_error": ("BLOCKED", "blocked"),
        "fallback_blocked_strict": ("BLOCKED", "blocked"),
        "rebuild_finalize_failed": ("CRITICAL", "critical"),
        "ocp_api_unavailable": ("ERROR", "error"),
        "operation_failed": ("ERROR", "error"),
    }
    for code, pair in expected.items():
        assert Body._classify_error_code(code) == pair


def test_cross_platform_status_details_migration_contract():
    legacy = {"schema": "error_envelope_v1", "code": "blocked_by_upstream_error", "message": "legacy"}
    migrated = Body._normalize_status_details_for_load(legacy)
    assert migrated.get("code") == "blocked_by_upstream_error"
    assert migrated.get("status_class") == "BLOCKED"
    assert migrated.get("severity") == "blocked"


def test_cross_platform_reference_snapshot_contract():
    snap = _collect_platform_snapshot()
    platform = _platform_key()
    expected = _PLATFORM_BASELINES.get(platform)

    if expected is None:
        # Unknown platform in this repository baseline: enforce generic invariants only.
        assert snap["faces_total"] > 0
        assert snap["edges_total"] > 0
        assert snap["volume_total"] > 0
        assert len(snap["digests"]) == len(_CROSS_PLATFORM_SEEDS)
        return

    assert snap["faces_total"] == expected["faces_total"]
    assert snap["edges_total"] == expected["edges_total"]
    assert snap["volume_total"] == pytest.approx(expected["volume_total"], rel=1e-9, abs=1e-9)
    assert snap["bbox_sum"] == expected["bbox_sum"]
    assert snap["digests"] == expected["digests"]
    assert snap["summary_digest"] == expected["summary_digest"]
