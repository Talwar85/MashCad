import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from golden_harness_utils import (
    build_reference_model,
    collect_seed_digest_map,
    collect_summary_fingerprint,
    is_feature_hard_error,
    signature_digest,
    solid_signature,
)

_GOLDEN_SEEDS = tuple(range(10))
_ROUNDTRIP_SEEDS = (0, 3, 7, 11, 19)


def test_golden_seed_digests_are_deterministic_across_independent_runs():
    first = collect_seed_digest_map(_GOLDEN_SEEDS)
    second = collect_seed_digest_map(_GOLDEN_SEEDS)
    assert second == first


def test_golden_summary_fingerprint_is_stable_across_runs():
    first = collect_summary_fingerprint(_GOLDEN_SEEDS)
    second = collect_summary_fingerprint(_GOLDEN_SEEDS)
    assert second == first


@pytest.mark.parametrize("seed", list(_ROUNDTRIP_SEEDS))
def test_golden_digest_survives_roundtrip_rebuild(seed: int):
    doc, body = build_reference_model(seed)
    live_digest = signature_digest(solid_signature(body._build123d_solid))

    restored = type(doc).from_dict(doc.to_dict())
    restored_body = restored.find_body_by_id(body.id)
    assert restored_body is not None
    restored_body._rebuild()
    restored_digest = signature_digest(solid_signature(restored_body._build123d_solid))

    assert restored_digest == live_digest


def test_golden_reference_features_do_not_end_in_hard_error_state():
    for seed in _GOLDEN_SEEDS:
        _, body = build_reference_model(seed)
        for feature in body.features:
            assert not is_feature_hard_error(feature), (
                f"seed={seed} feature={feature.name} entered hard error state: "
                f"status={getattr(feature, 'status', '')}, "
                f"details={getattr(feature, 'status_details', {})}"
            )
