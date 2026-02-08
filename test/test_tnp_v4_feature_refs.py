from modeling import (
    Body,
    DraftFeature,
    HoleFeature,
    HollowFeature,
    NSidedPatchFeature,
    SweepFeature,
)
from modeling.tnp_system import ShapeID, ShapeType


def _make_shape_id(shape_type: ShapeType, feature_id: str, local_index: int) -> ShapeID:
    return ShapeID.create(
        shape_type=shape_type,
        feature_id=feature_id,
        local_index=local_index,
        geometry_data=(feature_id, local_index, shape_type.name),
    )


def _face_selector():
    return {
        "center": [0.0, 0.0, 0.0],
        "normal": [0.0, 0.0, 1.0],
        "area": 1.0,
        "surface_type": "plane",
        "tolerance": 5.0,
    }


def _feature_dict(body_data: dict, feature_class: str) -> dict:
    for feat in body_data["features"]:
        if feat.get("feature_class") == feature_class:
            return feat
    raise AssertionError(f"Feature {feature_class} not found in serialized body data")


def test_tnp_v4_refs_are_serialized_for_requested_features():
    body = Body("tnp_v4_serialize")

    sweep = SweepFeature(profile_data={}, path_data={})
    sweep.profile_shape_id = _make_shape_id(ShapeType.FACE, sweep.id, 0)
    sweep.path_shape_id = _make_shape_id(ShapeType.EDGE, sweep.id, 1)

    hole = HoleFeature(face_selectors=[_face_selector()], position=(1.0, 2.0, 3.0), direction=(0.0, 0.0, -1.0))
    hole.face_shape_ids = [_make_shape_id(ShapeType.FACE, hole.id, 0)]

    draft = DraftFeature(face_selectors=[_face_selector()], pull_direction=(0.0, 0.0, 1.0))
    draft.face_shape_ids = [_make_shape_id(ShapeType.FACE, draft.id, 0)]

    hollow = HollowFeature(wall_thickness=2.0, opening_face_selectors=[_face_selector()])
    hollow.opening_face_shape_ids = [_make_shape_id(ShapeType.FACE, hollow.id, 0)]

    nsided = NSidedPatchFeature(edge_selectors=[(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0)])
    nsided.edge_shape_ids = [
        _make_shape_id(ShapeType.EDGE, nsided.id, 0),
        _make_shape_id(ShapeType.EDGE, nsided.id, 1),
        _make_shape_id(ShapeType.EDGE, nsided.id, 2),
    ]

    body.features = [sweep, hole, draft, hollow, nsided]
    data = body.to_dict()

    sweep_dict = _feature_dict(data, "SweepFeature")
    for key in ("uuid", "shape_type", "feature_id", "local_index", "geometry_hash", "timestamp"):
        assert key in sweep_dict["profile_shape_id"]
        assert key in sweep_dict["path_shape_id"]

    hole_dict = _feature_dict(data, "HoleFeature")
    draft_dict = _feature_dict(data, "DraftFeature")
    hollow_dict = _feature_dict(data, "HollowFeature")
    nsided_dict = _feature_dict(data, "NSidedPatchFeature")

    for entry in hole_dict["face_shape_ids"]:
        for key in ("uuid", "shape_type", "feature_id", "local_index", "geometry_hash", "timestamp"):
            assert key in entry
    for entry in draft_dict["face_shape_ids"]:
        for key in ("uuid", "shape_type", "feature_id", "local_index", "geometry_hash", "timestamp"):
            assert key in entry
    for entry in hollow_dict["opening_face_shape_ids"]:
        for key in ("uuid", "shape_type", "feature_id", "local_index", "geometry_hash", "timestamp"):
            assert key in entry
    for entry in nsided_dict["edge_shape_ids"]:
        for key in ("uuid", "shape_type", "feature_id", "local_index", "geometry_hash", "timestamp"):
            assert key in entry


def test_tnp_v4_refs_roundtrip_for_requested_features():
    body = Body("tnp_v4_roundtrip")

    sweep = SweepFeature(profile_data={}, path_data={})
    sweep.profile_shape_id = _make_shape_id(ShapeType.FACE, sweep.id, 0)
    sweep.path_shape_id = _make_shape_id(ShapeType.EDGE, sweep.id, 0)

    hole = HoleFeature(face_selectors=[_face_selector()])
    hole.face_shape_ids = [_make_shape_id(ShapeType.FACE, hole.id, 0)]

    draft = DraftFeature(face_selectors=[_face_selector()])
    draft.face_shape_ids = [_make_shape_id(ShapeType.FACE, draft.id, 0)]

    hollow = HollowFeature(opening_face_selectors=[_face_selector()])
    hollow.opening_face_shape_ids = [_make_shape_id(ShapeType.FACE, hollow.id, 0)]

    nsided = NSidedPatchFeature(edge_selectors=[(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0)])
    nsided.edge_shape_ids = [_make_shape_id(ShapeType.EDGE, nsided.id, 0)]

    body.features = [sweep, hole, draft, hollow, nsided]
    restored = Body.from_dict(body.to_dict())

    restored_sweep = next(feat for feat in restored.features if isinstance(feat, SweepFeature))
    restored_hole = next(feat for feat in restored.features if isinstance(feat, HoleFeature))
    restored_draft = next(feat for feat in restored.features if isinstance(feat, DraftFeature))
    restored_hollow = next(feat for feat in restored.features if isinstance(feat, HollowFeature))
    restored_nsided = next(feat for feat in restored.features if isinstance(feat, NSidedPatchFeature))

    assert isinstance(restored_sweep.profile_shape_id, ShapeID)
    assert isinstance(restored_sweep.path_shape_id, ShapeID)
    assert restored_sweep.profile_shape_id.uuid
    assert restored_sweep.path_shape_id.uuid

    assert restored_hole.face_shape_ids and isinstance(restored_hole.face_shape_ids[0], ShapeID)
    assert restored_draft.face_shape_ids and isinstance(restored_draft.face_shape_ids[0], ShapeID)
    assert restored_hollow.opening_face_shape_ids and isinstance(restored_hollow.opening_face_shape_ids[0], ShapeID)
    assert restored_nsided.edge_shape_ids and isinstance(restored_nsided.edge_shape_ids[0], ShapeID)


def test_tnp_v4_legacy_shape_id_fallback_for_requested_features():
    body_data = {
        "name": "legacy",
        "features": [
            {
                "feature_class": "HoleFeature",
                "name": "Hole",
                "face_selectors": [_face_selector()],
                "face_shape_ids": [{"feature_id": "feat_hole", "local_id": 2, "shape_type": "FACE"}],
            },
            {
                "feature_class": "DraftFeature",
                "name": "Draft",
                "face_selectors": [_face_selector()],
                "face_shape_ids": [{"feature_id": "feat_draft", "local_id": 3, "shape_type": "FACE"}],
            },
            {
                "feature_class": "NSidedPatchFeature",
                "name": "Patch",
                "edge_selectors": [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0)],
                "edge_shape_ids": [{"feature_id": "feat_patch", "local_id": 4, "shape_type": "EDGE"}],
            },
        ],
    }

    restored = Body.from_dict(body_data)
    hole = next(feat for feat in restored.features if isinstance(feat, HoleFeature))
    draft = next(feat for feat in restored.features if isinstance(feat, DraftFeature))
    nsided = next(feat for feat in restored.features if isinstance(feat, NSidedPatchFeature))

    assert hole.face_shape_ids[0].uuid
    assert hole.face_shape_ids[0].local_index == 2

    assert draft.face_shape_ids[0].uuid
    assert draft.face_shape_ids[0].local_index == 3

    assert nsided.edge_shape_ids[0].uuid
    assert nsided.edge_shape_ids[0].local_index == 4


def test_update_face_selectors_uses_tnp_v4_resolver(monkeypatch):
    body = Body("resolver_delegate")
    hole = HoleFeature(face_selectors=[_face_selector()])

    calls = {"count": 0}

    def fake_resolve(feature, solid):
        calls["count"] += 1
        return []

    def fail_score(*_args, **_kwargs):
        raise AssertionError("_score_face_match should not be used in TNP v4 update path")

    monkeypatch.setattr(body, "_resolve_feature_faces", fake_resolve)
    monkeypatch.setattr(body, "_score_face_match", fail_score)

    body._update_face_selectors_for_feature(hole, solid=object())
    assert calls["count"] == 1

