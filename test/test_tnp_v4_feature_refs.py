from modeling import (
    Body,
    ChamferFeature,
    Document,
    DraftFeature,
    FilletFeature,
    HoleFeature,
    HollowFeature,
    NSidedPatchFeature,
    SweepFeature,
)
from modeling.geometric_selector import GeometricEdgeSelector
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

    nsided = NSidedPatchFeature(edge_indices=[0, 1, 2])
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
    assert nsided_dict["edge_indices"] == [0, 1, 2]
    assert "edge_selectors" not in nsided_dict


def test_tnp_v4_fillet_chamfer_serialization_omits_legacy_edge_selectors():
    body = Body("tnp_v4_fillet_chamfer_serialize")

    fillet = FilletFeature(radius=1.5, edge_indices=[1, 3, 5])
    fillet.edge_shape_ids = [
        _make_shape_id(ShapeType.EDGE, fillet.id, 0),
        _make_shape_id(ShapeType.EDGE, fillet.id, 1),
    ]
    fillet.geometric_selectors = [
        {
            "center": [0.0, 0.0, 0.0],
            "direction": [1.0, 0.0, 0.0],
            "length": 10.0,
            "curve_type": "line",
            "tolerance": 10.0,
        }
    ]

    chamfer = ChamferFeature(distance=0.8, edge_indices=[2, 4])
    chamfer.edge_shape_ids = [_make_shape_id(ShapeType.EDGE, chamfer.id, 0)]
    chamfer.geometric_selectors = [
        {
            "center": [1.0, 1.0, 1.0],
            "direction": [0.0, 1.0, 0.0],
            "length": 8.0,
            "curve_type": "line",
            "tolerance": 10.0,
        }
    ]

    body.features = [fillet, chamfer]
    data = body.to_dict()

    fillet_dict = _feature_dict(data, "FilletFeature")
    chamfer_dict = _feature_dict(data, "ChamferFeature")

    assert fillet_dict["edge_indices"] == [1, 3, 5]
    assert chamfer_dict["edge_indices"] == [2, 4]
    assert "edge_selectors" not in fillet_dict
    assert "edge_selectors" not in chamfer_dict


def test_tnp_v4_fillet_chamfer_deserialize_migrates_legacy_edge_selectors():
    body_data = {
        "name": "legacy_fillet_chamfer",
        "features": [
            {
                "feature_class": "FilletFeature",
                "name": "Fillet",
                "radius": 2.0,
                "edge_selectors": [
                    (0.0, 0.0, 0.0),
                    ((10.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
                ],
            },
            {
                "feature_class": "ChamferFeature",
                "name": "Chamfer",
                "distance": 1.0,
                "edge_selectors": [
                    (5.0, 5.0, 0.0),
                ],
            },
        ],
    }

    restored = Body.from_dict(body_data)
    fillet = next(feat for feat in restored.features if isinstance(feat, FilletFeature))
    chamfer = next(feat for feat in restored.features if isinstance(feat, ChamferFeature))

    assert fillet.geometric_selectors
    assert chamfer.geometric_selectors
    assert fillet.edge_indices == []
    assert chamfer.edge_indices == []
    assert not hasattr(fillet, "edge_selectors")
    assert not hasattr(chamfer, "edge_selectors")


def test_tnp_v4_sweep_serialization_omits_transient_legacy_path_fields():
    body = Body("tnp_v4_sweep_path_sanitize")
    sweep = SweepFeature(
        profile_data={},
        path_data={
            "type": "body_edge",
            "edge": object(),
            "build123d_edges": [object()],
            "edge_selector": [(1.0, 2.0, 3.0)],
            "path_geometric_selector": {
                "center": [1.0, 2.0, 3.0],
                "direction": [1.0, 0.0, 0.0],
                "length": 5.0,
                "curve_type": "line",
                "tolerance": 10.0,
            },
            "edge_indices": [2, 4],
            "body_id": "body_a",
        },
    )
    body.features = [sweep]

    data = body.to_dict()
    sweep_dict = _feature_dict(data, "SweepFeature")

    assert "edge" not in sweep_dict["path_data"]
    assert "build123d_edges" not in sweep_dict["path_data"]
    assert "edge_selector" not in sweep_dict["path_data"]
    assert "path_geometric_selector" not in sweep_dict["path_data"]
    assert sweep_dict["path_data"]["edge_indices"] == [2, 4]
    assert sweep_dict["path_data"]["body_id"] == "body_a"


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

    nsided = NSidedPatchFeature(edge_indices=[7, 8, 9])
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
    assert restored_nsided.edge_indices == [7, 8, 9]


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
    assert nsided.geometric_selectors
    assert not hasattr(nsided, "edge_selectors")


def test_document_payload_migration_converts_legacy_nsided_edge_selectors():
    payload = {
        "name": "legacy_payload",
        "root_component": {
            "id": "root",
            "name": "Root",
            "bodies": [
                {
                    "id": "b1",
                    "name": "Body1",
                    "features": [
                        {
                            "feature_class": "NSidedPatchFeature",
                            "name": "Patch",
                            "edge_selectors": [
                                (0.0, 0.0, 0.0),
                                ((10.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
                                (0.0, 10.0, 0.0),
                            ],
                        }
                    ],
                }
            ],
            "sketches": [],
            "planes": [],
            "sub_components": [],
        },
    }

    stripped, converted = Document._migrate_legacy_nsided_payload(payload)
    feat = payload["root_component"]["bodies"][0]["features"][0]

    assert stripped == 1
    assert converted == 1
    assert "edge_selectors" not in feat
    assert len(feat.get("geometric_selectors", [])) == 3


def test_document_runtime_migrates_nsided_selectors_to_indices_and_shape_ids():
    from build123d import Solid

    doc = Document("runtime_nsided_migration")
    body = Body("BodyRuntime", document=doc)
    body._build123d_solid = Solid.make_box(10.0, 20.0, 30.0)

    all_edges = list(body._build123d_solid.edges())
    selectors = [GeometricEdgeSelector.from_edge(edge).to_dict() for edge in all_edges[:3]]
    patch = NSidedPatchFeature(geometric_selectors=selectors)
    body.features = [patch]
    doc.add_body(body, set_active=True)

    migrated = doc._migrate_loaded_nsided_features_to_indices()

    assert migrated == 1
    assert len(patch.edge_indices) >= 3
    assert len(patch.edge_shape_ids) >= 3


def test_tnp_v4_sweep_deserialize_moves_path_geometric_selector_out_of_path_data():
    body_data = {
        "name": "legacy_sweep",
        "features": [
            {
                "feature_class": "SweepFeature",
                "name": "Sweep",
                "profile_data": {},
                "path_data": {
                    "type": "body_edge",
                    "path_geometric_selector": {
                        "center": [0.0, 0.0, 0.0],
                        "direction": [1.0, 0.0, 0.0],
                        "length": 10.0,
                        "curve_type": "line",
                        "tolerance": 10.0,
                    },
                    "edge_selector": [(1.0, 2.0, 3.0)],
                },
            }
        ],
    }

    restored = Body.from_dict(body_data)
    sweep = next(feat for feat in restored.features if isinstance(feat, SweepFeature))

    assert sweep.path_geometric_selector is not None
    assert "path_geometric_selector" not in sweep.path_data
    assert "edge_selector" not in sweep.path_data


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
