import hashlib
import json

import pytest
from shapely.geometry import Polygon

from modeling import Body, Document, ExtrudeFeature, PrimitiveFeature
from modeling.topology_indexing import face_index_of
from modeling.tnp_system import ShapeType

_AXIS_DIRECTIONS = (
    (1.0, 0.0, 0.0),
    (-1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, -1.0, 0.0),
    (0.0, 0.0, 1.0),
    (0.0, 0.0, -1.0),
)

_GOLDEN_SEEDS = tuple(range(10))
_ROUNDTRIP_SEEDS = (0, 3, 7, 11, 19)


def _solid_signature(solid):
    assert solid is not None
    bb = solid.bounding_box()
    return {
        "volume": float(solid.volume),
        "faces": len(list(solid.faces())),
        "edges": len(list(solid.edges())),
        "bbox": (
            float(bb.min.X),
            float(bb.min.Y),
            float(bb.min.Z),
            float(bb.max.X),
            float(bb.max.Y),
            float(bb.max.Z),
        ),
    }


def _signature_digest(sig: dict) -> str:
    payload = {
        "volume": round(float(sig["volume"]), 6),
        "faces": int(sig["faces"]),
        "edges": int(sig["edges"]),
        "bbox": [round(float(v), 6) for v in sig["bbox"]],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_feature_hard_error(feature) -> bool:
    status = str(getattr(feature, "status", "") or "").strip().upper()
    details = getattr(feature, "status_details", {}) or {}
    if not isinstance(details, dict):
        details = {}
    status_class = str(details.get("status_class", "") or "").strip().upper()
    severity = str(details.get("severity", "") or "").strip().lower()
    code = str(details.get("code", "") or "").strip().lower()

    if status_class in {"ERROR", "CRITICAL", "BLOCKED"}:
        return True
    if severity in {"error", "critical", "blocked"}:
        return True
    if status == "ERROR" and code not in {"tnp_ref_drift", "fallback_used"}:
        return True
    return False


def _pick_face_by_direction(solid, direction):
    dx, dy, dz = direction
    return max(
        list(solid.faces()),
        key=lambda f: (float(f.center().X) * dx)
        + (float(f.center().Y) * dy)
        + (float(f.center().Z) * dz),
    )


def _register_face_shape_id(doc: Document, face, feature_seed: str, local_index: int):
    fc = face.center()
    return doc._shape_naming_service.register_shape(
        ocp_shape=face.wrapped,
        shape_type=ShapeType.FACE,
        feature_id=feature_seed,
        local_index=int(local_index),
        geometry_data=(float(fc.X), float(fc.Y), float(fc.Z), float(face.area)),
    )


def _add_pushpull_join(doc: Document, body: Body, step_id: str, direction, distance: float) -> ExtrudeFeature:
    solid = body._build123d_solid
    assert solid is not None

    face = _pick_face_by_direction(solid, direction)
    face_idx = face_index_of(solid, face)
    assert face_idx is not None
    face_idx = int(face_idx)

    shape_id = _register_face_shape_id(doc, face, step_id, face_idx)
    profile = Polygon([(0.0, 0.0), (1.2, 0.0), (1.2, 1.2), (0.0, 1.2)])
    feat = ExtrudeFeature(
        sketch=None,
        distance=float(distance),
        operation="Join",
        face_index=face_idx,
        face_shape_id=shape_id,
        precalculated_polys=[profile],
        name=f"Golden Push/Pull {step_id}",
    )
    body.add_feature(feat, rebuild=True)
    return feat


def _build_reference_model(seed: int) -> tuple[Document, Body]:
    doc = Document(f"golden_doc_{seed}")
    body = Body(f"golden_body_{seed}", document=doc)
    body.id = f"golden_body_id_{seed}"
    doc.add_body(body, set_active=True)

    base = PrimitiveFeature(
        primitive_type="box",
        length=20.0 + (seed % 5),
        width=18.0 + ((seed * 2) % 5),
        height=12.0 + ((seed * 3) % 4),
        name=f"Golden Base {seed}",
    )
    body.add_feature(base, rebuild=True)

    for step in range(2):
        direction = _AXIS_DIRECTIONS[(seed + step * 3) % len(_AXIS_DIRECTIONS)]
        distance = 0.8 + 0.2 * ((seed + step) % 5)
        _add_pushpull_join(
            doc,
            body,
            step_id=f"golden_seed_{seed}_step_{step}",
            direction=direction,
            distance=distance,
        )

    direction = _AXIS_DIRECTIONS[(seed + 5) % len(_AXIS_DIRECTIONS)]
    distance = 0.6 + 0.1 * (seed % 4)
    _add_pushpull_join(
        doc,
        body,
        step_id=f"golden_seed_{seed}_step_2",
        direction=direction,
        distance=distance,
    )
    assert body._build123d_solid is not None
    return doc, body


def _collect_seed_digest_map(seeds) -> dict[int, str]:
    digests = {}
    for seed in seeds:
        _, body = _build_reference_model(seed)
        sig = _solid_signature(body._build123d_solid)
        digests[int(seed)] = _signature_digest(sig)
    return digests


def _collect_summary_fingerprint(seeds) -> str:
    aggregate = {
        "faces_total": 0,
        "edges_total": 0,
        "volume_total": 0.0,
        "bbox_sum": [0.0] * 6,
        "digests": [],
    }
    for seed in seeds:
        _, body = _build_reference_model(seed)
        sig = _solid_signature(body._build123d_solid)
        aggregate["faces_total"] += int(sig["faces"])
        aggregate["edges_total"] += int(sig["edges"])
        aggregate["volume_total"] += float(sig["volume"])
        aggregate["digests"].append(_signature_digest(sig))
        for i, v in enumerate(sig["bbox"]):
            aggregate["bbox_sum"][i] += float(v)

    payload = {
        "faces_total": aggregate["faces_total"],
        "edges_total": aggregate["edges_total"],
        "volume_total": round(aggregate["volume_total"], 6),
        "bbox_sum": [round(v, 6) for v in aggregate["bbox_sum"]],
        "digests": aggregate["digests"],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_golden_seed_digests_are_deterministic_across_independent_runs():
    first = _collect_seed_digest_map(_GOLDEN_SEEDS)
    second = _collect_seed_digest_map(_GOLDEN_SEEDS)
    assert second == first


def test_golden_summary_fingerprint_is_stable_across_runs():
    first = _collect_summary_fingerprint(_GOLDEN_SEEDS)
    second = _collect_summary_fingerprint(_GOLDEN_SEEDS)
    assert second == first


@pytest.mark.parametrize("seed", list(_ROUNDTRIP_SEEDS))
def test_golden_digest_survives_roundtrip_rebuild(seed: int):
    doc, body = _build_reference_model(seed)
    live_digest = _signature_digest(_solid_signature(body._build123d_solid))

    restored = Document.from_dict(doc.to_dict())
    restored_body = restored.find_body_by_id(body.id)
    assert restored_body is not None
    restored_body._rebuild()
    restored_digest = _signature_digest(_solid_signature(restored_body._build123d_solid))

    assert restored_digest == live_digest


def test_golden_reference_features_do_not_end_in_hard_error_state():
    for seed in _GOLDEN_SEEDS:
        _, body = _build_reference_model(seed)
        for feature in body.features:
            assert not _is_feature_hard_error(feature), (
                f"seed={seed} feature={feature.name} entered hard error state: "
                f"status={getattr(feature, 'status', '')}, "
                f"details={getattr(feature, 'status_details', {})}"
            )
