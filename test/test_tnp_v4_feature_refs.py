import pytest

from modeling import (
    Body,
    ChamferFeature,
    Document,
    DraftFeature,
    ExtrudeFeature,
    FilletFeature,
    HoleFeature,
    HollowFeature,
    NSidedPatchFeature,
    SurfaceTextureFeature,
    SweepFeature,
    ThreadFeature,
    PrimitiveFeature,
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


def _edge_selector():
    return {
        "center": [0.0, 0.0, 0.0],
        "direction": [1.0, 0.0, 0.0],
        "length": 1.0,
        "curve_type": "line",
        "tolerance": 10.0,
    }


def _feature_dict(body_data: dict, feature_class: str) -> dict:
    for feat in body_data["features"]:
        if feat.get("feature_class") == feature_class:
            return feat
    raise AssertionError(f"Feature {feature_class} not found in serialized body data")


def test_tnp_v4_refs_are_serialized_for_requested_features():
    body = Body("tnp_v4_serialize")

    sweep = SweepFeature(profile_data={}, path_data={"type": "body_edge", "edge_indices": [3]})
    sweep.profile_shape_id = _make_shape_id(ShapeType.FACE, sweep.id, 0)
    sweep.path_shape_id = _make_shape_id(ShapeType.EDGE, sweep.id, 1)
    sweep.profile_face_index = 16

    hole = HoleFeature(face_selectors=[_face_selector()], position=(1.0, 2.0, 3.0), direction=(0.0, 0.0, -1.0))
    hole.face_shape_ids = [_make_shape_id(ShapeType.FACE, hole.id, 0)]
    hole.face_indices = [11]

    draft = DraftFeature(face_selectors=[_face_selector()], pull_direction=(0.0, 0.0, 1.0))
    draft.face_shape_ids = [_make_shape_id(ShapeType.FACE, draft.id, 0)]
    draft.face_indices = [12]

    hollow = HollowFeature(wall_thickness=2.0, opening_face_selectors=[_face_selector()])
    hollow.opening_face_shape_ids = [_make_shape_id(ShapeType.FACE, hollow.id, 0)]
    hollow.opening_face_indices = [13]

    texture = SurfaceTextureFeature(face_selectors=[_face_selector()])
    texture.face_shape_ids = [_make_shape_id(ShapeType.FACE, texture.id, 0)]
    texture.face_indices = [14]

    thread = ThreadFeature(face_selector=_face_selector())
    thread.face_shape_id = _make_shape_id(ShapeType.FACE, thread.id, 0)
    thread.face_index = 15

    nsided = NSidedPatchFeature(edge_indices=[0, 1, 2])
    nsided.edge_shape_ids = [
        _make_shape_id(ShapeType.EDGE, nsided.id, 0),
        _make_shape_id(ShapeType.EDGE, nsided.id, 1),
        _make_shape_id(ShapeType.EDGE, nsided.id, 2),
    ]

    body.features = [sweep, hole, draft, hollow, texture, thread, nsided]
    data = body.to_dict()

    sweep_dict = _feature_dict(data, "SweepFeature")
    for key in ("uuid", "shape_type", "feature_id", "local_index", "geometry_hash", "timestamp"):
        assert key in sweep_dict["profile_shape_id"]
        assert key in sweep_dict["path_shape_id"]
    assert sweep_dict["profile_face_index"] == 16

    hole_dict = _feature_dict(data, "HoleFeature")
    draft_dict = _feature_dict(data, "DraftFeature")
    hollow_dict = _feature_dict(data, "HollowFeature")
    texture_dict = _feature_dict(data, "SurfaceTextureFeature")
    thread_dict = _feature_dict(data, "ThreadFeature")
    nsided_dict = _feature_dict(data, "NSidedPatchFeature")

    for entry in hole_dict["face_shape_ids"]:
        for key in ("uuid", "shape_type", "feature_id", "local_index", "geometry_hash", "timestamp"):
            assert key in entry
    assert hole_dict["face_indices"] == [11]
    for entry in draft_dict["face_shape_ids"]:
        for key in ("uuid", "shape_type", "feature_id", "local_index", "geometry_hash", "timestamp"):
            assert key in entry
    assert draft_dict["face_indices"] == [12]
    for entry in hollow_dict["opening_face_shape_ids"]:
        for key in ("uuid", "shape_type", "feature_id", "local_index", "geometry_hash", "timestamp"):
            assert key in entry
    assert hollow_dict["opening_face_indices"] == [13]
    for entry in texture_dict["face_shape_ids"]:
        for key in ("uuid", "shape_type", "feature_id", "local_index", "geometry_hash", "timestamp"):
            assert key in entry
    assert texture_dict["face_indices"] == [14]
    assert thread_dict["face_index"] == 15
    for key in ("uuid", "shape_type", "feature_id", "local_index", "geometry_hash", "timestamp"):
        assert key in thread_dict["face_shape_id"]
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


def test_tnp_v4_extrude_pushpull_refs_roundtrip():
    body = Body("tnp_v4_extrude_roundtrip")
    extrude = ExtrudeFeature(sketch=None, distance=12.0, operation="Join")
    extrude.face_shape_id = _make_shape_id(ShapeType.FACE, extrude.id, 0)
    extrude.face_index = 6
    extrude.face_selector = _face_selector()
    body.features = [extrude]

    serialized = body.to_dict()
    extrude_dict = _feature_dict(serialized, "ExtrudeFeature")
    assert extrude_dict["face_index"] == 6
    for key in ("uuid", "shape_type", "feature_id", "local_index", "geometry_hash", "timestamp"):
        assert key in extrude_dict["face_shape_id"]

    restored = Body.from_dict(serialized)
    restored_extrude = next(feat for feat in restored.features if isinstance(feat, ExtrudeFeature))
    assert isinstance(restored_extrude.face_shape_id, ShapeID)
    assert restored_extrude.face_index == 6
    assert restored_extrude.face_selector is not None


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

    sweep = SweepFeature(profile_data={}, path_data={"type": "body_edge", "edge_indices": [4]})
    sweep.profile_shape_id = _make_shape_id(ShapeType.FACE, sweep.id, 0)
    sweep.path_shape_id = _make_shape_id(ShapeType.EDGE, sweep.id, 0)
    sweep.profile_face_index = 6

    hole = HoleFeature(face_selectors=[_face_selector()])
    hole.face_shape_ids = [_make_shape_id(ShapeType.FACE, hole.id, 0)]
    hole.face_indices = [7]

    draft = DraftFeature(face_selectors=[_face_selector()])
    draft.face_shape_ids = [_make_shape_id(ShapeType.FACE, draft.id, 0)]
    draft.face_indices = [8]

    hollow = HollowFeature(opening_face_selectors=[_face_selector()])
    hollow.opening_face_shape_ids = [_make_shape_id(ShapeType.FACE, hollow.id, 0)]
    hollow.opening_face_indices = [9]

    texture = SurfaceTextureFeature(face_selectors=[_face_selector()])
    texture.face_shape_ids = [_make_shape_id(ShapeType.FACE, texture.id, 0)]
    texture.face_indices = [10]

    thread = ThreadFeature(face_selector=_face_selector())
    thread.face_shape_id = _make_shape_id(ShapeType.FACE, thread.id, 0)
    thread.face_index = 11

    nsided = NSidedPatchFeature(edge_indices=[7, 8, 9])
    nsided.edge_shape_ids = [_make_shape_id(ShapeType.EDGE, nsided.id, 0)]

    body.features = [sweep, hole, draft, hollow, texture, thread, nsided]
    restored = Body.from_dict(body.to_dict())

    restored_sweep = next(feat for feat in restored.features if isinstance(feat, SweepFeature))
    restored_hole = next(feat for feat in restored.features if isinstance(feat, HoleFeature))
    restored_draft = next(feat for feat in restored.features if isinstance(feat, DraftFeature))
    restored_hollow = next(feat for feat in restored.features if isinstance(feat, HollowFeature))
    restored_texture = next(feat for feat in restored.features if isinstance(feat, SurfaceTextureFeature))
    restored_thread = next(feat for feat in restored.features if isinstance(feat, ThreadFeature))
    restored_nsided = next(feat for feat in restored.features if isinstance(feat, NSidedPatchFeature))

    assert isinstance(restored_sweep.profile_shape_id, ShapeID)
    assert isinstance(restored_sweep.path_shape_id, ShapeID)
    assert restored_sweep.profile_shape_id.uuid
    assert restored_sweep.path_shape_id.uuid
    assert restored_sweep.profile_face_index == 6

    assert restored_hole.face_shape_ids and isinstance(restored_hole.face_shape_ids[0], ShapeID)
    assert restored_draft.face_shape_ids and isinstance(restored_draft.face_shape_ids[0], ShapeID)
    assert restored_hollow.opening_face_shape_ids and isinstance(restored_hollow.opening_face_shape_ids[0], ShapeID)
    assert restored_hole.face_indices == [7]
    assert restored_draft.face_indices == [8]
    assert restored_hollow.opening_face_indices == [9]
    assert restored_texture.face_shape_ids and isinstance(restored_texture.face_shape_ids[0], ShapeID)
    assert restored_texture.face_indices == [10]
    assert isinstance(restored_thread.face_shape_id, ShapeID)
    assert restored_thread.face_index == 11
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
                "face_indices": [2],
                "face_shape_ids": [{"feature_id": "feat_hole", "local_id": 2, "shape_type": "FACE"}],
            },
            {
                "feature_class": "DraftFeature",
                "name": "Draft",
                "face_selectors": [_face_selector()],
                "face_indices": [3],
                "face_shape_ids": [{"feature_id": "feat_draft", "local_id": 3, "shape_type": "FACE"}],
            },
            {
                "feature_class": "SurfaceTextureFeature",
                "name": "Texture",
                "texture_type": "ripple",
                "face_selectors": [_face_selector()],
                "face_indices": [4],
                "face_shape_ids": [{"feature_id": "feat_tex", "local_id": 4, "shape_type": "FACE"}],
            },
            {
                "feature_class": "ThreadFeature",
                "name": "Thread",
                "face_selector": _face_selector(),
                "face_index": 5,
                "face_shape_id": {"feature_id": "feat_thread", "local_id": 5, "shape_type": "FACE"},
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
    texture = next(feat for feat in restored.features if isinstance(feat, SurfaceTextureFeature))
    thread = next(feat for feat in restored.features if isinstance(feat, ThreadFeature))
    nsided = next(feat for feat in restored.features if isinstance(feat, NSidedPatchFeature))

    assert hole.face_shape_ids[0].uuid
    assert hole.face_shape_ids[0].local_index == 2
    assert hole.face_indices == [2]

    assert draft.face_shape_ids[0].uuid
    assert draft.face_shape_ids[0].local_index == 3
    assert draft.face_indices == [3]

    assert texture.face_shape_ids[0].uuid
    assert texture.face_shape_ids[0].local_index == 4
    assert texture.face_indices == [4]

    assert thread.face_shape_id.uuid
    assert thread.face_shape_id.local_index == 5
    assert thread.face_index == 5

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


def test_tnp_v4_sweep_deserialize_drops_profile_selector_when_topological_refs_exist():
    body_data = {
        "name": "legacy_sweep_profile_mixed",
        "features": [
            {
                "feature_class": "SweepFeature",
                "name": "Sweep",
                "profile_data": {},
                "path_data": {"type": "sketch_edge", "geometry_type": "line", "start": [0.0, 0.0], "end": [1.0, 0.0]},
                "profile_face_index": 2,
                "profile_shape_id": {"feature_id": "feat_sweep", "local_id": 2, "shape_type": "FACE"},
                "profile_geometric_selector": _face_selector(),
            }
        ],
    }

    restored = Body.from_dict(body_data)
    sweep = next(feat for feat in restored.features if isinstance(feat, SweepFeature))

    assert sweep.profile_shape_id is not None
    assert sweep.profile_face_index == 2
    assert sweep.profile_geometric_selector is None


def test_tnp_v4_sweep_deserialize_drops_selector_when_topological_path_refs_exist():
    body_data = {
        "name": "legacy_sweep_mixed",
        "features": [
            {
                "feature_class": "SweepFeature",
                "name": "Sweep",
                "profile_data": {},
                "path_data": {
                    "type": "body_edge",
                    "edge_indices": [0],
                },
                "path_shape_id": {"feature_id": "feat_sweep", "local_id": 0, "shape_type": "EDGE"},
                "path_geometric_selector": _edge_selector(),
            }
        ],
    }

    restored = Body.from_dict(body_data)
    sweep = next(feat for feat in restored.features if isinstance(feat, SweepFeature))

    assert sweep.path_shape_id is not None
    assert sweep.path_geometric_selector is None
    assert sweep.path_data.get("edge_indices") == [0]


def test_sweep_resolve_path_prefers_edge_indices_without_selector_fallback(monkeypatch):
    from build123d import Solid
    from modeling.geometric_selector import GeometricEdgeSelector

    body = Body("sweep_edge_index_first")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    sweep = SweepFeature(
        profile_data={},
        path_data={"type": "body_edge", "edge_indices": [0]},
    )
    sweep.path_geometric_selector = _edge_selector()

    def _fail_from_dict(cls, _data):
        raise AssertionError("selector fallback should not run when edge_indices resolve")

    monkeypatch.setattr(GeometricEdgeSelector, "from_dict", classmethod(_fail_from_dict))
    wire = body._resolve_path(sweep.path_data, solid, sweep)

    assert wire is not None


def test_sweep_resolve_path_blocks_legacy_fallback_when_topology_refs_break(monkeypatch):
    from build123d import Solid
    from modeling.geometric_selector import GeometricEdgeSelector

    body = Body("sweep_no_legacy_fallback_on_tnp_break")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    sweep = SweepFeature(
        profile_data={},
        path_data={
            "type": "body_edge",
            "edge_indices": [999],
            "build123d_edges": [list(solid.edges())[0]],
            "path_geometric_selector": _edge_selector(),
        },
    )
    sweep.path_geometric_selector = _edge_selector()

    def _fail_from_dict(cls, _data):
        raise AssertionError("selector fallback must not run when topological path refs exist")

    monkeypatch.setattr(GeometricEdgeSelector, "from_dict", classmethod(_fail_from_dict))
    wire = body._resolve_path(sweep.path_data, solid, sweep)

    assert wire is None


def test_resolve_edges_tnp_prefers_edge_indices_without_selector_fallback(monkeypatch):
    from build123d import Solid
    from modeling.geometric_selector import GeometricEdgeSelector

    body = Body("edge_index_first")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    feature = FilletFeature(
        radius=1.0,
        edge_indices=[0],
        geometric_selectors=[_edge_selector()],
    )

    def _fail_from_dict(cls, _data):
        raise AssertionError("edge selector fallback should not run when edge_indices resolve")

    monkeypatch.setattr(GeometricEdgeSelector, "from_dict", classmethod(_fail_from_dict))
    resolved = body._resolve_edges_tnp(solid, feature)

    assert len(resolved) == 1
    assert feature.edge_indices == [0]


def test_resolve_edges_tnp_blocks_selector_fallback_when_topology_refs_break(monkeypatch):
    from build123d import Solid
    from modeling.geometric_selector import GeometricEdgeSelector

    body = Body("edge_no_legacy_fallback_on_break")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    feature = FilletFeature(
        radius=1.0,
        edge_indices=[999],
        geometric_selectors=[_edge_selector()],
    )
    calls = {"count": 0}

    def _fail_from_dict(cls, _data):
        calls["count"] += 1
        raise AssertionError("edge selector fallback must not run when topological refs exist but break")

    monkeypatch.setattr(GeometricEdgeSelector, "from_dict", classmethod(_fail_from_dict))
    resolved = body._resolve_edges_tnp(solid, feature)

    assert resolved == []
    assert feature.edge_indices == [999]
    assert calls["count"] == 0


def test_resolve_edges_tnp_allows_selector_recovery_when_strict_policy_disabled(monkeypatch):
    from build123d import Solid
    from config.feature_flags import FEATURE_FLAGS
    from modeling.geometric_selector import GeometricEdgeSelector

    body = Body("edge_selector_recovery_policy_disabled")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    feature = FilletFeature(
        radius=1.0,
        edge_indices=[999],
        geometric_selectors=[_edge_selector()],
    )

    class _Selector:
        def find_best_match(self, edges):
            return edges[0] if edges else None

    monkeypatch.setitem(FEATURE_FLAGS, "strict_topology_fallback_policy", False)
    monkeypatch.setattr(GeometricEdgeSelector, "from_dict", classmethod(lambda cls, _data: _Selector()))

    resolved = body._resolve_edges_tnp(solid, feature)

    assert len(resolved) == 1
    assert feature.edge_indices == [0]
    drift_notice = body._consume_tnp_failure(feature)
    assert (drift_notice or {}).get("category") == "drift"
    assert (drift_notice or {}).get("reference_kind") == "edge"
    assert (drift_notice or {}).get("strict") is False


def test_safe_operation_emits_tnp_ref_drift_warning_after_selector_recovery(monkeypatch):
    from build123d import Solid
    from config.feature_flags import FEATURE_FLAGS
    from modeling.geometric_selector import GeometricEdgeSelector

    body = Body("edge_selector_recovery_drift_warning")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    feature = FilletFeature(
        radius=1.0,
        edge_indices=[999],
        geometric_selectors=[_edge_selector()],
    )

    class _Selector:
        def find_best_match(self, edges):
            return edges[0] if edges else None

    monkeypatch.setitem(FEATURE_FLAGS, "strict_topology_fallback_policy", False)
    monkeypatch.setattr(GeometricEdgeSelector, "from_dict", classmethod(lambda cls, _data: _Selector()))

    def _op():
        resolved = body._resolve_edges_tnp(solid, feature)
        assert len(resolved) == 1
        return object()

    result, status = body._safe_operation(
        "EdgeSelectorRecoveryDrift",
        _op,
        feature=feature,
    )

    details = body._last_operation_error_details or {}
    tnp_failure = details.get("tnp_failure") or {}
    assert result is not None
    assert status == "WARNING"
    assert details.get("code") == "tnp_ref_drift"
    assert tnp_failure.get("category") == "drift"
    assert tnp_failure.get("reference_kind") == "edge"


def test_resolve_edges_tnp_shapeid_fallback_is_quiet(monkeypatch):
    from build123d import Solid

    doc = Document()
    body = Body("edge_shapeid_quiet")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    feature = FilletFeature(radius=1.0)
    feature.edge_shape_ids = [_make_shape_id(ShapeType.EDGE, "missing_edge", 0)]
    flags = []

    def _fake_resolve(_shape_id, _solid, *, log_unresolved=True):
        flags.append(log_unresolved)
        return None, "unresolved"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _fake_resolve)
    resolved = body._resolve_edges_tnp(solid, feature)

    assert resolved == []
    assert flags == [False]


def test_resolve_edges_tnp_fillet_requires_shape_index_consistency(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import edge_from_index

    doc = Document()
    body = Body("fillet_edge_shape_index_mismatch")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    feature = FilletFeature(radius=1.0, edge_indices=[0])
    feature.edge_shape_ids = [_make_shape_id(ShapeType.EDGE, "fillet_edge_mismatch", 0)]

    mismatch_edge = edge_from_index(solid, 3)
    assert mismatch_edge is not None

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is False
        return mismatch_edge.wrapped, "direct"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    resolved = body._resolve_edges_tnp(solid, feature)

    assert resolved == []


def test_resolve_edges_tnp_single_ref_pair_geometric_conflict_prefers_index(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import edge_from_index

    doc = Document()
    body = Body("fillet_single_ref_pair_geometric_conflict")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    feature = FilletFeature(radius=1.0, edge_indices=[0], geometric_selectors=[])
    feature.edge_shape_ids = [_make_shape_id(ShapeType.EDGE, "fillet_geo_conflict", 0)]

    mismatch_edge = edge_from_index(solid, 3)
    assert mismatch_edge is not None

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is False
        return mismatch_edge.wrapped, "geometric"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    resolved = body._resolve_edges_tnp(solid, feature)
    drift_notice = body._consume_tnp_failure(feature)

    assert len(resolved) == 1
    assert feature.edge_indices == [0]
    assert (drift_notice or {}).get("category") == "drift"
    assert (drift_notice or {}).get("reference_kind") == "edge"
    assert (drift_notice or {}).get("reason") == "single_ref_pair_geometric_shape_conflict_index_preferred"


def test_safe_operation_emits_drift_warning_for_single_ref_pair_geometric_conflict(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import edge_from_index

    doc = Document()
    body = Body("safe_op_single_ref_pair_geometric_conflict")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    feature = FilletFeature(radius=1.0, edge_indices=[0], geometric_selectors=[])
    feature.edge_shape_ids = [_make_shape_id(ShapeType.EDGE, "fillet_geo_conflict_safe_op", 0)]

    mismatch_edge = edge_from_index(solid, 3)
    assert mismatch_edge is not None

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is False
        return mismatch_edge.wrapped, "geometric"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)

    def _op():
        resolved = body._resolve_edges_tnp(solid, feature)
        assert len(resolved) == 1
        return object()

    result, status = body._safe_operation(
        "SingleRefPairGeometricConflict",
        _op,
        feature=feature,
    )

    details = body._last_operation_error_details or {}
    tnp_failure = details.get("tnp_failure") or {}
    assert result is not None
    assert status == "WARNING"
    assert details.get("code") == "tnp_ref_drift"
    assert tnp_failure.get("category") == "drift"
    assert tnp_failure.get("reason") == "single_ref_pair_geometric_shape_conflict_index_preferred"


def test_rebuild_fillet_invalid_edge_sets_tnp_missing_ref_error_code():
    body = Body("fillet_invalid_edge_tnp_missing_ref")
    base = PrimitiveFeature(primitive_type="box", length=20.0, width=20.0, height=20.0)
    fillet = FilletFeature(radius=1.0, edge_indices=[999], geometric_selectors=[])
    body.features = [base, fillet]

    body._rebuild()

    details = fillet.status_details or {}
    tnp_failure = details.get("tnp_failure") or {}
    assert fillet.status == "ERROR"
    assert details.get("code") == "tnp_ref_missing"
    assert tnp_failure.get("category") == "missing_ref"
    assert tnp_failure.get("reference_kind") == "edge"


def test_rebuild_fillet_invalid_edge_error_is_idempotent_across_cycles():
    body = Body("fillet_invalid_edge_idempotent")
    base = PrimitiveFeature(primitive_type="box", length=20.0, width=20.0, height=20.0)
    fillet = FilletFeature(radius=1.0, edge_indices=[999], geometric_selectors=[])
    body.features = [base, fillet]

    body._rebuild()
    first_details = dict(fillet.status_details or {})

    body._rebuild()
    second_details = dict(fillet.status_details or {})

    assert fillet.status == "ERROR"
    assert first_details.get("code") == "tnp_ref_missing"
    assert second_details.get("code") == "tnp_ref_missing"
    assert (first_details.get("tnp_failure") or {}).get("category") == "missing_ref"
    assert (second_details.get("tnp_failure") or {}).get("category") == "missing_ref"


def test_rebuild_fillet_shape_index_mismatch_sets_tnp_mismatch_error_code(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import edge_from_index

    doc = Document()
    body = Body("fillet_shape_index_mismatch_tnp_code")
    body._build123d_solid = Solid.make_box(10.0, 20.0, 30.0)
    doc.add_body(body)

    base = PrimitiveFeature(primitive_type="box", length=20.0, width=20.0, height=20.0)
    fillet = FilletFeature(radius=1.0, edge_indices=[0], geometric_selectors=[])
    fillet.edge_shape_ids = [_make_shape_id(ShapeType.EDGE, "fillet_status_mismatch", 0)]
    body.features = [base, fillet]

    def _resolve_shape(_shape_id, solid, *, log_unresolved=True):
        assert log_unresolved is False
        mismatch_edge = edge_from_index(solid, 3)
        assert mismatch_edge is not None
        return mismatch_edge.wrapped, "direct"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    body._rebuild()

    details = fillet.status_details or {}
    tnp_failure = details.get("tnp_failure") or {}
    assert fillet.status == "ERROR"
    assert details.get("code") == "tnp_ref_mismatch"
    assert tnp_failure.get("category") == "mismatch"
    assert tnp_failure.get("reference_kind") == "edge"


def test_rebuild_fillet_shape_index_mismatch_error_is_idempotent_across_cycles(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import edge_from_index

    doc = Document()
    body = Body("fillet_shape_index_mismatch_idempotent")
    body._build123d_solid = Solid.make_box(10.0, 20.0, 30.0)
    doc.add_body(body)

    base = PrimitiveFeature(primitive_type="box", length=20.0, width=20.0, height=20.0)
    fillet = FilletFeature(radius=1.0, edge_indices=[0], geometric_selectors=[])
    fillet.edge_shape_ids = [_make_shape_id(ShapeType.EDGE, "fillet_status_mismatch_idempotent", 0)]
    body.features = [base, fillet]

    def _resolve_shape(_shape_id, solid, *, log_unresolved=True):
        mismatch_edge = edge_from_index(solid, 3)
        assert mismatch_edge is not None
        return mismatch_edge.wrapped, "direct"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)

    body._rebuild()
    first_details = dict(fillet.status_details or {})

    body._rebuild()
    second_details = dict(fillet.status_details or {})

    assert fillet.status == "ERROR"
    assert first_details.get("code") == "tnp_ref_mismatch"
    assert second_details.get("code") == "tnp_ref_mismatch"
    assert (first_details.get("tnp_failure") or {}).get("category") == "mismatch"
    assert (second_details.get("tnp_failure") or {}).get("category") == "mismatch"


def test_resolve_edges_tnp_normalizes_index_order_deterministically():
    from build123d import Solid

    body = Body("resolve_edges_order_normalized")
    solid = Solid.make_box(10.0, 20.0, 30.0)

    feature = FilletFeature(radius=1.0, edge_indices=[4, 1, 3, 1])
    resolved_first = body._resolve_edges_tnp(solid, feature)

    assert len(resolved_first) == 3
    assert feature.edge_indices == [1, 3, 4]

    feature.edge_indices = [3, 4, 1]
    resolved_second = body._resolve_edges_tnp(solid, feature)

    assert len(resolved_second) == 3
    assert feature.edge_indices == [1, 3, 4]


def test_rebuild_edge_index_normalization_is_idempotent_across_cycles():
    doc = Document()
    body = Body("edge_index_normalization_idempotent")
    doc.add_body(body)
    base = PrimitiveFeature(primitive_type="box", length=20.0, width=20.0, height=20.0)
    fillet = FilletFeature(radius=0.8, edge_indices=[4, 1, 3, 1])
    body.features = [base, fillet]

    body._rebuild()
    first_indices = list(fillet.edge_indices or [])

    body._rebuild()
    second_indices = list(fillet.edge_indices or [])

    assert fillet.status in ("OK", "SUCCESS")
    assert first_indices == [1, 3, 4]
    assert second_indices == [1, 3, 4]


def test_resolve_edges_tnp_uses_shape_probe_for_single_ref_even_with_legacy_local_index(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import edge_from_index

    doc = Document()
    body = Body("fillet_edge_shape_local_index_stale")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    feature = FilletFeature(radius=1.0, edge_indices=[0])
    feature.edge_shape_ids = [_make_shape_id(ShapeType.EDGE, "fillet_edge_stale_local", 999)]

    calls = {"count": 0}

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        calls["count"] += 1
        assert log_unresolved is False
        target_edge = edge_from_index(solid, 0)
        assert target_edge is not None
        return target_edge.wrapped, "direct"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    resolved = body._resolve_edges_tnp(solid, feature)

    assert len(resolved) == 1
    assert calls["count"] >= 1
    assert feature.edge_indices == [0]


def test_resolve_feature_faces_normalizes_index_order_deterministically():
    from build123d import Solid

    body = Body("resolve_faces_order_normalized")
    solid = Solid.make_box(10.0, 20.0, 30.0)

    feature = SurfaceTextureFeature(face_indices=[4, 1, 3], face_selectors=[_face_selector()] * 3)
    resolved_first = body._resolve_feature_faces(feature, solid)

    assert len(resolved_first) == 3
    assert feature.face_indices == [1, 3, 4]

    feature.face_indices = [3, 4, 1]
    resolved_second = body._resolve_feature_faces(feature, solid)

    assert len(resolved_second) == 3
    assert feature.face_indices == [1, 3, 4]


def test_resolve_feature_faces_uses_indices_when_shapeid_local_index_is_stale(monkeypatch):
    from build123d import Solid

    doc = Document()
    body = Body("hole_face_shape_local_index_stale")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    feature = HoleFeature(face_indices=[0], face_selectors=[_face_selector()])
    feature.face_shape_ids = [_make_shape_id(ShapeType.FACE, "hole_face_stale_local", 999)]

    def _fail_resolve(*_args, **_kwargs):
        raise AssertionError("ShapeID resolution should not run for stale local_index when face_indices are valid")

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _fail_resolve)
    resolved = body._resolve_feature_faces(feature, solid)

    assert len(resolved) == 1
    assert feature.face_indices == [0]


def test_resolve_feature_faces_extrude_blocks_mismatch_even_with_legacy_shape_local_index(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import face_from_index

    doc = Document()
    body = Body("extrude_face_shape_local_index_stale")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    feature = ExtrudeFeature(
        sketch=None,
        distance=5.0,
        operation="Join",
        face_index=0,
        face_selector=_face_selector(),
        precalculated_polys=[object()],
    )
    feature.face_shape_id = _make_shape_id(ShapeType.FACE, "extrude_face_stale_local", 999)
    mismatch_face = face_from_index(solid, 4)
    assert mismatch_face is not None

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is False
        return mismatch_face.wrapped, "direct"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    resolved = body._resolve_feature_faces(feature, solid)

    assert resolved == []
    assert feature.face_index == 0


def test_resolve_feature_faces_single_ref_pair_geometric_conflict_prefers_index(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import face_from_index

    doc = Document()
    body = Body("extrude_face_single_ref_pair_geometric_conflict")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    feature = ExtrudeFeature(
        sketch=None,
        distance=5.0,
        operation="Join",
        face_index=0,
        face_selector=_face_selector(),
        precalculated_polys=[object()],
    )
    feature.face_shape_id = _make_shape_id(ShapeType.FACE, "extrude_face_geo_conflict", 0)

    mismatch_face = face_from_index(solid, 4)
    assert mismatch_face is not None

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is False
        return mismatch_face.wrapped, "geometric"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    resolved = body._resolve_feature_faces(feature, solid)
    drift_notice = body._consume_tnp_failure(feature)

    assert len(resolved) == 1
    assert feature.face_index == 0
    assert (drift_notice or {}).get("category") == "drift"
    assert (drift_notice or {}).get("reference_kind") == "face"
    assert (drift_notice or {}).get("reason") == "single_ref_pair_geometric_shape_conflict_index_preferred"


def test_safe_operation_emits_drift_warning_for_single_ref_pair_geometric_face_conflict(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import face_from_index

    doc = Document()
    body = Body("safe_op_single_ref_pair_geometric_face_conflict")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    feature = ExtrudeFeature(
        sketch=None,
        distance=5.0,
        operation="Join",
        face_index=0,
        face_selector=_face_selector(),
        precalculated_polys=[object()],
    )
    feature.face_shape_id = _make_shape_id(ShapeType.FACE, "extrude_face_geo_conflict_safe_op", 0)

    mismatch_face = face_from_index(solid, 4)
    assert mismatch_face is not None

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is False
        return mismatch_face.wrapped, "geometric"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)

    def _op():
        resolved = body._resolve_feature_faces(feature, solid)
        assert len(resolved) == 1
        return object()

    result, status = body._safe_operation(
        "SingleRefPairGeometricFaceConflict",
        _op,
        feature=feature,
    )

    details = body._last_operation_error_details or {}
    tnp_failure = details.get("tnp_failure") or {}
    assert result is not None
    assert status == "WARNING"
    assert details.get("code") == "tnp_ref_drift"
    assert tnp_failure.get("category") == "drift"
    assert tnp_failure.get("reference_kind") == "face"
    assert tnp_failure.get("reason") == "single_ref_pair_geometric_shape_conflict_index_preferred"


def test_sweep_resolve_path_requires_shape_index_consistency(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import edge_from_index

    doc = Document()
    body = Body("sweep_path_shape_index_mismatch")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    sweep = SweepFeature(
        profile_data={},
        path_data={"type": "body_edge", "edge_indices": [0]},
    )
    sweep.path_shape_id = _make_shape_id(ShapeType.EDGE, "sweep_path_mismatch", 0)

    mismatch_edge = edge_from_index(solid, 4)
    assert mismatch_edge is not None

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is True
        return mismatch_edge.wrapped, "direct"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    wire = body._resolve_path(sweep.path_data, solid, sweep)

    assert wire is None


def test_sweep_resolve_path_single_ref_pair_geometric_conflict_prefers_index(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import edge_from_index, edge_index_of

    doc = Document()
    body = Body("sweep_path_single_ref_pair_geometric_conflict")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    sweep = SweepFeature(
        profile_data={},
        path_data={"type": "body_edge", "edge_indices": [0]},
    )
    sweep.path_shape_id = _make_shape_id(ShapeType.EDGE, "sweep_path_geo_conflict", 0)

    mismatch_edge = edge_from_index(solid, 4)
    assert mismatch_edge is not None

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is True
        return mismatch_edge.wrapped, "geometric"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    wire = body._resolve_path(sweep.path_data, solid, sweep)
    drift_notice = body._consume_tnp_failure(sweep)

    assert wire is not None
    wire_edges = list(wire.edges())
    assert len(wire_edges) == 1
    assert edge_index_of(solid, wire_edges[0]) == 0
    assert sweep.path_shape_id is not None
    assert (drift_notice or {}).get("category") == "drift"
    assert (drift_notice or {}).get("reference_kind") == "edge"
    assert (drift_notice or {}).get("reason") == "single_ref_pair_geometric_shape_conflict_index_preferred"


def test_sweep_resolve_path_single_ref_pair_shape_missing_prefers_index(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import edge_index_of

    doc = Document()
    body = Body("sweep_path_single_ref_pair_shape_missing")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    sweep = SweepFeature(
        profile_data={},
        path_data={"type": "body_edge", "edge_indices": [0]},
    )
    sweep.path_shape_id = _make_shape_id(ShapeType.EDGE, "sweep_path_shape_missing", 0)

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is True
        return None, "unresolved"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    wire = body._resolve_path(sweep.path_data, solid, sweep)
    drift_notice = body._consume_tnp_failure(sweep)

    assert wire is not None
    wire_edges = list(wire.edges())
    assert len(wire_edges) == 1
    assert edge_index_of(solid, wire_edges[0]) == 0
    assert sweep.path_shape_id is not None
    assert drift_notice is None


def test_safe_operation_emits_drift_warning_for_sweep_path_single_ref_pair_geometric_conflict(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import edge_from_index, edge_index_of

    doc = Document()
    body = Body("safe_op_sweep_path_single_ref_pair_geometric_conflict")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    sweep = SweepFeature(
        profile_data={},
        path_data={"type": "body_edge", "edge_indices": [0]},
    )
    sweep.path_shape_id = _make_shape_id(ShapeType.EDGE, "sweep_path_geo_conflict_safe_op", 0)

    mismatch_edge = edge_from_index(solid, 4)
    assert mismatch_edge is not None

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is True
        return mismatch_edge.wrapped, "geometric"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)

    def _op():
        wire = body._resolve_path(sweep.path_data, solid, sweep)
        assert wire is not None
        wire_edges = list(wire.edges())
        assert len(wire_edges) == 1
        assert edge_index_of(solid, wire_edges[0]) == 0
        return object()

    result, status = body._safe_operation(
        "SweepPathSingleRefPairGeometricConflict",
        _op,
        feature=sweep,
    )

    details = body._last_operation_error_details or {}
    tnp_failure = details.get("tnp_failure") or {}
    assert result is not None
    assert status == "WARNING"
    assert details.get("code") == "tnp_ref_drift"
    assert tnp_failure.get("category") == "drift"
    assert tnp_failure.get("reference_kind") == "edge"
    assert tnp_failure.get("reason") == "single_ref_pair_geometric_shape_conflict_index_preferred"


def test_rebuild_sweep_invalid_path_sets_tnp_missing_ref_error_code():
    body = Body("sweep_invalid_path_tnp_missing_ref")
    base = PrimitiveFeature(primitive_type="box", length=20.0, width=20.0, height=20.0)
    sweep = SweepFeature(
        profile_data={"type": "body_face"},
        path_data={"type": "body_edge", "edge_indices": [999]},
    )
    sweep.profile_face_index = 0
    body.features = [base, sweep]

    body._rebuild()

    details = sweep.status_details or {}
    tnp_failure = details.get("tnp_failure") or {}
    assert sweep.status == "ERROR"
    assert details.get("code") == "tnp_ref_missing"
    assert tnp_failure.get("category") == "missing_ref"
    assert tnp_failure.get("reference_kind") == "edge"


def test_rebuild_sweep_path_shape_index_mismatch_sets_tnp_mismatch_code(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import edge_from_index

    doc = Document()
    body = Body("sweep_path_mismatch_tnp_code")
    body._build123d_solid = Solid.make_box(10.0, 20.0, 30.0)
    doc.add_body(body)

    base = PrimitiveFeature(primitive_type="box", length=20.0, width=20.0, height=20.0)
    sweep = SweepFeature(
        profile_data={"type": "body_face"},
        path_data={"type": "body_edge", "edge_indices": [0]},
    )
    sweep.profile_face_index = 0
    sweep.path_shape_id = _make_shape_id(ShapeType.EDGE, "sweep_path_status_mismatch", 0)
    body.features = [base, sweep]

    def _resolve_shape(_shape_id, solid, *, log_unresolved=True):
        mismatch_edge = edge_from_index(solid, 4)
        assert mismatch_edge is not None
        return mismatch_edge.wrapped, "direct"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    body._rebuild()

    details = sweep.status_details or {}
    tnp_failure = details.get("tnp_failure") or {}
    assert sweep.status == "ERROR"
    assert details.get("code") == "tnp_ref_mismatch"
    assert tnp_failure.get("category") == "mismatch"
    assert tnp_failure.get("reference_kind") == "edge"


def test_compute_nsided_patch_blocks_selector_fallback_when_topology_refs_break(monkeypatch):
    from build123d import Solid
    from modeling.geometric_selector import GeometricEdgeSelector

    body = Body("nsided_no_legacy_fallback_on_break")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    feature = NSidedPatchFeature(
        edge_indices=[999, 998, 997],
        geometric_selectors=[_edge_selector(), _edge_selector(), _edge_selector()],
    )

    def _fail_from_dict(cls, _data):
        raise AssertionError("nsided selector fallback must not run when topological refs exist but break")

    monkeypatch.setattr(GeometricEdgeSelector, "from_dict", classmethod(_fail_from_dict))
    with pytest.raises(ValueError, match="Nur 0 von"):
        body._compute_nsided_patch(feature, solid)


@pytest.mark.skip("OCP-First Migration: Test uses monkeypatching incompatible with OCP BRepOffsetAPI_MakePipe. Needs rewrite.")
def test_compute_sweep_prefers_profile_face_index_without_selector_fallback(monkeypatch):
    import build123d
    from build123d import Solid
    from modeling.geometric_selector import GeometricFaceSelector

    class _SweepResult:
        def is_valid(self):
            return True

    body = Body("sweep_profile_index_first")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    feature = SweepFeature(
        profile_data={"type": "body_face"},
        path_data={"type": "body_edge", "edge_indices": [0]},
    )
    feature.profile_face_index = 0
    feature.profile_geometric_selector = _face_selector()

    def _fail_from_dict(cls, _data):
        raise AssertionError("profile selector fallback should not run when profile_face_index resolves")

    monkeypatch.setattr(GeometricFaceSelector, "from_dict", classmethod(_fail_from_dict))
    monkeypatch.setattr(body, "_resolve_path", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(body, "_move_profile_to_path_start", lambda profile_face, *_args, **_kwargs: profile_face)
    monkeypatch.setattr(build123d, "sweep", lambda *_args, **_kwargs: _SweepResult())

    result = body._compute_sweep(feature, solid)

    assert result is not None
    assert feature.profile_face_index == 0


def test_compute_sweep_blocks_profile_legacy_fallback_when_topology_ref_breaks(monkeypatch):
    from build123d import Solid
    from modeling.geometric_selector import GeometricFaceSelector

    body = Body("sweep_profile_no_legacy_fallback")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    feature = SweepFeature(
        profile_data={"type": "sketch_profile"},
        path_data={"type": "body_edge", "edge_indices": [0]},
    )
    feature.profile_face_index = 999
    feature.profile_geometric_selector = _face_selector()

    def _fail_from_dict(cls, _data):
        raise AssertionError("profile selector fallback must not run when topological refs exist")

    def _fail_profile_data_fallback(*_args, **_kwargs):
        raise AssertionError("profile_data fallback must not run when topological refs exist")

    monkeypatch.setattr(GeometricFaceSelector, "from_dict", classmethod(_fail_from_dict))
    monkeypatch.setattr(body, "_profile_data_to_face", _fail_profile_data_fallback)

    with pytest.raises(ValueError, match="Profil-Referenz"):
        body._compute_sweep(feature, solid)


def test_compute_sweep_requires_profile_shape_index_consistency(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import face_from_index

    doc = Document()
    body = Body("sweep_profile_shape_index_mismatch")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    feature = SweepFeature(
        profile_data={"type": "body_face"},
        path_data={"type": "body_edge", "edge_indices": [0]},
    )
    feature.profile_face_index = 0
    feature.profile_shape_id = _make_shape_id(ShapeType.FACE, "sweep_profile_mismatch", 0)

    mismatch_face = face_from_index(solid, 4)
    assert mismatch_face is not None

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is True
        return mismatch_face.wrapped, "direct"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)

    with pytest.raises(ValueError, match="inkonsistent"):
        body._compute_sweep(feature, solid)


def test_compute_sweep_profile_single_ref_pair_geometric_conflict_prefers_index(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import face_from_index

    doc = Document()
    body = Body("sweep_profile_single_ref_pair_geometric_conflict")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    feature = SweepFeature(
        profile_data={"type": "body_face"},
        path_data={"type": "body_edge", "edge_indices": [0]},
    )
    feature.profile_face_index = 0
    feature.profile_shape_id = _make_shape_id(ShapeType.FACE, "sweep_profile_geo_conflict", 0)

    mismatch_face = face_from_index(solid, 4)
    assert mismatch_face is not None

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is True
        return mismatch_face.wrapped, "geometric"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    monkeypatch.setattr(body, "_resolve_path", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        body,
        "_move_profile_to_path_start",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("stop_after_profile_resolution")),
    )

    with pytest.raises(RuntimeError, match="stop_after_profile_resolution"):
        body._compute_sweep(feature, solid)

    drift_notice = body._consume_tnp_failure(feature)
    assert feature.profile_face_index == 0
    assert feature.profile_shape_id is not None
    assert (drift_notice or {}).get("category") == "drift"
    assert (drift_notice or {}).get("reference_kind") == "face"
    assert (drift_notice or {}).get("reason") == "single_ref_pair_geometric_shape_conflict_index_preferred"


def test_compute_sweep_profile_single_ref_pair_shape_missing_prefers_index(monkeypatch):
    from build123d import Solid

    doc = Document()
    body = Body("sweep_profile_single_ref_pair_shape_missing")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    feature = SweepFeature(
        profile_data={"type": "body_face"},
        path_data={"type": "body_edge", "edge_indices": [0]},
    )
    feature.profile_face_index = 0
    feature.profile_shape_id = _make_shape_id(ShapeType.FACE, "sweep_profile_shape_missing", 0)

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is True
        return None, "unresolved"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    monkeypatch.setattr(body, "_resolve_path", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        body,
        "_move_profile_to_path_start",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("stop_after_profile_resolution")),
    )

    with pytest.raises(RuntimeError, match="stop_after_profile_resolution"):
        body._compute_sweep(feature, solid)

    drift_notice = body._consume_tnp_failure(feature)
    assert feature.profile_face_index == 0
    assert feature.profile_shape_id is not None
    assert drift_notice is None


def test_safe_operation_emits_drift_warning_for_sweep_profile_single_ref_pair_geometric_conflict(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import face_from_index

    doc = Document()
    body = Body("safe_op_sweep_profile_single_ref_pair_geometric_conflict")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    feature = SweepFeature(
        profile_data={"type": "body_face"},
        path_data={"type": "body_edge", "edge_indices": [0]},
    )
    feature.profile_face_index = 0
    feature.profile_shape_id = _make_shape_id(ShapeType.FACE, "sweep_profile_geo_conflict_safe_op", 0)

    mismatch_face = face_from_index(solid, 4)
    assert mismatch_face is not None

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is True
        return mismatch_face.wrapped, "geometric"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    monkeypatch.setattr(body, "_resolve_path", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        body,
        "_move_profile_to_path_start",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("stop_after_profile_resolution")),
    )

    def _op():
        try:
            body._compute_sweep(feature, solid)
        except RuntimeError as e:
            assert "stop_after_profile_resolution" in str(e)
            return object()
        return object()

    result, status = body._safe_operation(
        "SweepProfileSingleRefPairGeometricConflict",
        _op,
        feature=feature,
    )

    details = body._last_operation_error_details or {}
    tnp_failure = details.get("tnp_failure") or {}
    assert result is not None
    assert status == "WARNING"
    assert details.get("code") == "tnp_ref_drift"
    assert tnp_failure.get("category") == "drift"
    assert tnp_failure.get("reference_kind") == "face"
    assert tnp_failure.get("reason") == "single_ref_pair_geometric_shape_conflict_index_preferred"


def test_update_face_selectors_uses_tnp_v4_resolver(monkeypatch):
    body = Body("resolver_delegate")
    hole = HoleFeature(face_selectors=[_face_selector()])
    thread = ThreadFeature(face_selector=_face_selector())
    texture = SurfaceTextureFeature(face_selectors=[_face_selector()])

    calls = {"count": 0}

    def fake_resolve(feature, solid):
        calls["count"] += 1
        return []

    def fail_score(*_args, **_kwargs):
        raise AssertionError("_score_face_match should not be used in TNP v4 update path")

    monkeypatch.setattr(body, "_resolve_feature_faces", fake_resolve)
    monkeypatch.setattr(body, "_score_face_match", fail_score)

    body._update_face_selectors_for_feature(hole, solid=object())
    body._update_face_selectors_for_feature(thread, solid=object())
    body._update_face_selectors_for_feature(texture, solid=object())
    assert calls["count"] == 3


def test_resolve_feature_faces_supports_topology_indices():
    from build123d import Solid

    body = Body("face_indices_resolver")
    solid = Solid.make_box(10.0, 20.0, 30.0)

    hole = HoleFeature(face_indices=[0])
    texture = SurfaceTextureFeature(face_indices=[1])
    thread = ThreadFeature(face_index=2)

    resolved = body._resolve_feature_faces(hole, solid)
    resolved_texture = body._resolve_feature_faces(texture, solid)
    resolved_thread = body._resolve_feature_faces(thread, solid)

    assert len(resolved) == 1
    assert len(resolved_texture) == 1
    assert len(resolved_thread) == 1
    assert hole.face_indices == [0]
    assert texture.face_indices == [1]
    assert thread.face_index == 2
    assert thread.face_selector is not None


def test_resolve_feature_faces_does_not_use_selector_recovery_when_indices_resolve(monkeypatch):
    from build123d import Solid
    from modeling.geometric_selector import GeometricFaceSelector

    body = Body("face_index_no_selector_fallback")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    texture = SurfaceTextureFeature(face_indices=[0], face_selectors=[_face_selector()])

    def _fail_from_dict(cls, _data):
        raise AssertionError("selector fallback should not run when face_indices resolve")

    monkeypatch.setattr(GeometricFaceSelector, "from_dict", classmethod(_fail_from_dict))
    resolved = body._resolve_feature_faces(texture, solid)

    assert len(resolved) == 1
    assert texture.face_indices == [0]


def test_resolve_feature_faces_blocks_selector_fallback_when_topology_refs_break(monkeypatch):
    from build123d import Solid
    from modeling.geometric_selector import GeometricFaceSelector

    body = Body("face_index_no_legacy_fallback_on_break")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    texture = SurfaceTextureFeature(face_indices=[999], face_selectors=[_face_selector()])

    def _fail_from_dict(cls, _data):
        raise AssertionError("selector fallback must not run when topological refs exist but break")

    monkeypatch.setattr(GeometricFaceSelector, "from_dict", classmethod(_fail_from_dict))
    resolved = body._resolve_feature_faces(texture, solid)

    assert resolved == []
    assert texture.face_indices == [999]


def test_compute_hole_blocks_selector_fallback_when_topology_refs_break(monkeypatch):
    from build123d import Solid
    from modeling.geometric_selector import GeometricFaceSelector

    body = Body("hole_no_legacy_fallback_on_break")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    feature = HoleFeature(
        diameter=4.0,
        depth=5.0,
        position=(0.0, 0.0, 0.0),
        direction=(0.0, 0.0, -1.0),
        face_indices=[999],
        face_selectors=[_face_selector()],
    )

    def _fail_from_dict(cls, _data):
        raise AssertionError("hole selector fallback must not run when topological refs exist but break")

    monkeypatch.setattr(GeometricFaceSelector, "from_dict", classmethod(_fail_from_dict))
    with pytest.raises(ValueError, match="TNP v4.0"):
        body._compute_hole(feature, solid)


def test_compute_draft_blocks_selector_fallback_when_topology_refs_break(monkeypatch):
    from build123d import Solid
    from modeling.geometric_selector import GeometricFaceSelector

    body = Body("draft_no_legacy_fallback_on_break")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    feature = DraftFeature(
        draft_angle=5.0,
        pull_direction=(0.0, 0.0, 1.0),
        face_indices=[999],
        face_selectors=[_face_selector()],
    )

    def _fail_from_dict(cls, _data):
        raise AssertionError("draft selector fallback must not run when topological refs exist but break")

    monkeypatch.setattr(GeometricFaceSelector, "from_dict", classmethod(_fail_from_dict))
    with pytest.raises(ValueError, match="TNP v4.0"):
        body._compute_draft(feature, solid)


def test_compute_hollow_blocks_selector_fallback_when_topology_refs_break(monkeypatch):
    from build123d import Solid
    from modeling.geometric_selector import GeometricFaceSelector

    body = Body("hollow_no_legacy_fallback_on_break")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    feature = HollowFeature(
        wall_thickness=1.0,
        opening_face_indices=[999],
        opening_face_selectors=[_face_selector()],
    )

    def _fail_from_dict(cls, _data):
        raise AssertionError("hollow selector fallback must not run when topological refs exist but break")

    monkeypatch.setattr(GeometricFaceSelector, "from_dict", classmethod(_fail_from_dict))
    with pytest.raises(ValueError, match="Kein Geometric-Fallback"):
        body._compute_hollow(feature, solid)


def test_resolve_feature_faces_supports_extrude_face_index(monkeypatch):
    from build123d import Solid
    from modeling.geometric_selector import GeometricFaceSelector

    body = Body("extrude_face_index_resolver")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    extrude = ExtrudeFeature(
        sketch=None,
        distance=5.0,
        operation="Join",
        face_index=2,
        face_selector=_face_selector(),
        precalculated_polys=[object()],
    )

    def _fail_from_dict(cls, _data):
        raise AssertionError("selector fallback should not run when face_index resolves")

    monkeypatch.setattr(GeometricFaceSelector, "from_dict", classmethod(_fail_from_dict))
    resolved = body._resolve_feature_faces(extrude, solid)

    assert len(resolved) == 1
    assert extrude.face_index == 2
    assert extrude.face_selector is not None


def test_resolve_feature_faces_extrude_blocks_shape_index_mismatch(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import face_from_index

    doc = Document()
    body = Body("extrude_shape_first_resolver")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    target_face = face_from_index(solid, 3)
    assert target_face is not None
    sid = _make_shape_id(ShapeType.FACE, "extrude_shape_first", 0)

    extrude = ExtrudeFeature(
        sketch=None,
        distance=5.0,
        operation="Join",
        face_index=0,  # absichtlich stale
        face_selector=_face_selector(),
        precalculated_polys=[object()],
    )
    extrude.face_shape_id = sid

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is False
        return target_face.wrapped, "direct"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    resolved = body._resolve_feature_faces(extrude, solid)

    assert resolved == []
    assert extrude.face_index == 0


def test_compute_extrude_part_brepfeat_prefers_face_index_before_selector(monkeypatch):
    from build123d import Solid
    from modeling.geometric_selector import GeometricFaceSelector

    brepfeat_mod = pytest.importorskip("OCP.BRepFeat")

    class _FakePrism:
        def Init(self, shape, *_args):
            self._shape = shape
            self._distance = 0.0

        def Perform(self, distance):
            self._distance = float(distance or 0.0)
            return None

        def IsDone(self):
            return True

        def Shape(self):
            # Liefert absichtlich geänderte Geometrie, damit der No-Op-Guard
            # nicht triggert und nur die Referenz-Auflösung getestet wird.
            from build123d import Solid as _Solid
            delta = 1.0 + max(0.1, abs(self._distance))
            return _Solid.make_box(10.0 + delta, 20.0, 30.0).wrapped

    def _fail_from_dict(cls, _data):
        raise AssertionError("legacy selector matching should not run when face_index resolves")

    body = Body("brepfeat_face_index_first")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    feature = ExtrudeFeature(
        sketch=None,
        distance=3.0,
        operation="Join",
        face_index=0,
        face_selector=_face_selector(),
        precalculated_polys=[object()],
    )

    monkeypatch.setattr(GeometricFaceSelector, "from_dict", classmethod(_fail_from_dict))
    monkeypatch.setattr(body, "_unify_same_domain", lambda shape, _name: shape)
    monkeypatch.setattr(brepfeat_mod, "BRepFeat_MakePrism", _FakePrism)

    result = body._compute_extrude_part_brepfeat(feature, solid)

    assert result is not None
    assert feature.face_index == 0


def test_compute_extrude_part_brepfeat_uses_shape_resolution_even_when_face_index_exists(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import face_from_index

    brepfeat_mod = pytest.importorskip("OCP.BRepFeat")

    class _FakePrism:
        def Init(self, shape, *_args):
            self._shape = shape
            self._distance = 0.0

        def Perform(self, distance):
            self._distance = float(distance or 0.0)
            return None

        def IsDone(self):
            return True

        def Shape(self):
            from build123d import Solid as _Solid
            delta = 1.0 + max(0.1, abs(self._distance))
            return _Solid.make_box(10.0 + delta, 20.0, 30.0).wrapped

    doc = Document()
    body = Body("brepfeat_index_authoritative")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    feature = ExtrudeFeature(
        sketch=None,
        distance=3.0,
        operation="Join",
        face_index=0,
        face_selector=_face_selector(),
        precalculated_polys=[object()],
    )
    feature.face_shape_id = _make_shape_id(ShapeType.FACE, "stale_pushpull_face", 0)

    calls = {"count": 0}

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        calls["count"] += 1
        assert log_unresolved is False
        target = face_from_index(solid, 0)
        assert target is not None
        return target.wrapped, "direct"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    monkeypatch.setattr(body, "_unify_same_domain", lambda shape, _name: shape)
    monkeypatch.setattr(brepfeat_mod, "BRepFeat_MakePrism", _FakePrism)

    result = body._compute_extrude_part_brepfeat(feature, solid)

    assert result is not None
    assert calls["count"] >= 1
    assert feature.face_index == 0
    assert feature.face_shape_id is not None
    assert feature.face_shape_id.shape_type == ShapeType.FACE


def test_compute_extrude_part_brepfeat_prefers_shape_face_and_heals_stale_index(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import face_from_index

    brepfeat_mod = pytest.importorskip("OCP.BRepFeat")

    class _FakePrism:
        def Init(self, shape, face_shape, *_args):
            self._shape = shape
            self._face = face_shape
            self._distance = 0.0

        def Perform(self, distance):
            self._distance = float(distance or 0.0)
            return None

        def IsDone(self):
            return True

        def Shape(self):
            from build123d import Solid as _Solid

            delta = 1.0 + max(0.1, abs(self._distance))
            return _Solid.make_box(10.0 + delta, 20.0, 30.0).wrapped

    doc = Document()
    body = Body("brepfeat_shape_preferred")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    feature = ExtrudeFeature(
        sketch=None,
        distance=3.0,
        operation="Join",
        face_index=0,  # stale index
        face_selector=_face_selector(),
        precalculated_polys=[object()],
    )
    feature.face_shape_id = _make_shape_id(ShapeType.FACE, "shape_preferred", 999)

    target_face = face_from_index(solid, 4)
    assert target_face is not None

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is False
        return target_face.wrapped, "direct"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    monkeypatch.setattr(body, "_unify_same_domain", lambda shape, _name: shape)
    monkeypatch.setattr(brepfeat_mod, "BRepFeat_MakePrism", _FakePrism)

    result = body._compute_extrude_part_brepfeat(feature, solid)

    assert result is not None
    # Stale index must be healed to the resolved shape face.
    assert feature.face_index == 4


def test_rebuild_pushpull_failure_blocks_downstream_and_skips_legacy_fallback(monkeypatch):
    body = Body("pushpull_rebuild_guard")
    base = PrimitiveFeature(primitive_type="box", length=20.0, width=20.0, height=20.0)
    pushpull = ExtrudeFeature(
        sketch=None,
        distance=5.0,
        operation="Join",
        face_index=999,  # absichtlich ungültig
        face_selector=_face_selector(),
        precalculated_polys=[object()],
    )
    pushpull.face_shape_id = _make_shape_id(ShapeType.FACE, pushpull.id, 0)
    downstream = ChamferFeature(distance=1.0, edge_indices=[0])
    body.features = [base, pushpull, downstream]

    legacy_calls = {"count": 0}

    def _legacy_extrude(*_args, **_kwargs):
        legacy_calls["count"] += 1
        return None

    def _fail_brepfeat(*_args, **_kwargs):
        raise ValueError("BRepFeat Push/Pull: Zielfläche nicht gefunden (face_shape_id/face_index prüfen)")

    monkeypatch.setattr(body, "_compute_extrude_part", _legacy_extrude)
    monkeypatch.setattr(body, "_compute_extrude_part_brepfeat", _fail_brepfeat)

    body._rebuild()

    assert pushpull.status == "ERROR"
    assert "Zielfläche nicht gefunden" in (pushpull.status_message or "")
    assert legacy_calls["count"] == 0

    assert downstream.status == "ERROR"
    assert "Nicht ausgeführt: vorheriges Feature" in (downstream.status_message or "")
    assert (downstream.status_details or {}).get("code") == "blocked_by_upstream_error"


def test_safe_operation_strict_blocks_topology_fallback(monkeypatch):
    from config.feature_flags import FEATURE_FLAGS

    body = Body("strict_self_heal_fallback_block")
    feature = ExtrudeFeature(
        sketch=None,
        distance=5.0,
        operation="Join",
        face_index=0,
    )

    monkeypatch.setitem(FEATURE_FLAGS, "self_heal_strict", True)

    result, status = body._safe_operation(
        "StrictFallbackBlock",
        lambda: (_ for _ in ()).throw(ValueError("primary failed")),
        fallback_func=lambda: object(),
        feature=feature,
    )

    assert result is None
    assert status == "ERROR"
    assert (body._last_operation_error_details or {}).get("code") == "fallback_blocked_strict"


def test_safe_operation_policy_blocks_topology_fallback_without_self_heal(monkeypatch):
    from config.feature_flags import FEATURE_FLAGS

    body = Body("strict_topology_policy_fallback_block")
    feature = ExtrudeFeature(
        sketch=None,
        distance=5.0,
        operation="Join",
        face_index=0,
    )

    monkeypatch.setitem(FEATURE_FLAGS, "self_heal_strict", False)
    monkeypatch.setitem(FEATURE_FLAGS, "strict_topology_fallback_policy", True)

    result, status = body._safe_operation(
        "StrictTopologyPolicyBlock",
        lambda: (_ for _ in ()).throw(ValueError("primary failed")),
        fallback_func=lambda: object(),
        feature=feature,
    )

    assert result is None
    assert status == "ERROR"
    assert (body._last_operation_error_details or {}).get("code") == "fallback_blocked_strict"


def test_safe_operation_allows_fallback_when_strict_policies_disabled(monkeypatch):
    from config.feature_flags import FEATURE_FLAGS

    body = Body("fallback_allowed_without_strict_policies")
    feature = ExtrudeFeature(
        sketch=None,
        distance=5.0,
        operation="Join",
        face_index=0,
    )

    monkeypatch.setitem(FEATURE_FLAGS, "self_heal_strict", False)
    monkeypatch.setitem(FEATURE_FLAGS, "strict_topology_fallback_policy", False)

    result, status = body._safe_operation(
        "FallbackAllowed",
        lambda: (_ for _ in ()).throw(ValueError("primary failed")),
        fallback_func=lambda: object(),
        feature=feature,
    )

    assert result is not None
    assert status == "WARNING"
    assert (body._last_operation_error_details or {}).get("code") == "fallback_used"


def test_rebuild_strict_self_heal_rolls_back_invalid_feature_result(monkeypatch):
    from config.feature_flags import FEATURE_FLAGS
    from modeling.geometry_validator import GeometryValidator, ValidationLevel, ValidationResult

    body = Body("strict_self_heal_feature_rollback")
    base = PrimitiveFeature(primitive_type="box", length=10.0, width=10.0, height=10.0, name="base_box")
    invalid = PrimitiveFeature(primitive_type="box", length=20.0, width=20.0, height=20.0, name="invalid_box")
    body.features = [base, invalid]

    monkeypatch.setitem(FEATURE_FLAGS, "self_heal_strict", True)

    def _validate_for_test(solid, level=ValidationLevel.NORMAL):
        volume = float(getattr(solid, "volume", 0.0))
        if volume > 5000.0:
            return ValidationResult.invalid("synthetic invalid solid")
        return ValidationResult.valid("synthetic valid solid")

    monkeypatch.setattr(GeometryValidator, "validate_solid", staticmethod(_validate_for_test))

    body._rebuild()

    assert base.status in ("OK", "SUCCESS")
    assert invalid.status == "ERROR"
    assert (invalid.status_details or {}).get("code") == "self_heal_rollback_invalid_result"
    assert body._build123d_solid is not None
    assert body._build123d_solid.volume == pytest.approx(1000.0, rel=1e-6)


def test_tnp_health_report_extrude_uses_rebuild_status_for_input_refs(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import face_from_index

    doc = Document()
    body = Body("tnp_health_extrude_index_shape_mismatch")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    extrude = ExtrudeFeature(
        sketch=None,
        distance=4.0,
        operation="Join",
        face_index=0,
        precalculated_polys=[object()],
    )
    extrude.face_shape_id = _make_shape_id(ShapeType.FACE, "extrude_health_mismatch", 0)
    body.features = [extrude]

    target_face = face_from_index(solid, 4)
    assert target_face is not None

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is False
        return target_face.wrapped, "direct"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    report = doc._shape_naming_service.get_health_report(body)

    assert report["status"] == "ok"
    feature_report = report["features"][0]
    assert feature_report["status"] == "ok"
    assert feature_report["broken"] == 0
    assert feature_report["ok"] == 1
    assert feature_report["refs"][0]["method"] == "rebuild"


def test_resolve_feature_faces_hole_requires_shape_index_consistency(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import face_from_index

    doc = Document()
    body = Body("hole_face_shape_index_mismatch")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    hole = HoleFeature(face_indices=[0], face_selectors=[_face_selector()])
    hole.face_shape_ids = [_make_shape_id(ShapeType.FACE, "hole_face_mismatch", 0)]

    mismatch_face = face_from_index(solid, 4)
    assert mismatch_face is not None

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is False
        return mismatch_face.wrapped, "direct"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    resolved = body._resolve_feature_faces(hole, solid)

    assert resolved == []


def test_tnp_health_report_hole_marks_index_shape_mismatch_as_broken(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import face_from_index

    doc = Document()
    body = Body("tnp_health_hole_index_shape_mismatch")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    hole = HoleFeature(
        face_indices=[0],
        face_selectors=[_face_selector()],
        position=(0.0, 0.0, 0.0),
        direction=(0.0, 0.0, -1.0),
    )
    hole.face_shape_ids = [_make_shape_id(ShapeType.FACE, "hole_health_mismatch", 0)]
    body.features = [hole]

    mismatch_face = face_from_index(solid, 4)
    assert mismatch_face is not None

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        assert log_unresolved is False
        return mismatch_face.wrapped, "direct"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    report = doc._shape_naming_service.get_health_report(body)

    assert report["status"] == "broken"
    feature_report = report["features"][0]
    assert feature_report["status"] == "broken"
    assert feature_report["broken"] == 1
    assert feature_report["refs"][0]["method"] == "index_mismatch"


def test_pushpull_sequence_with_chamfer_reports_stable_health():
    from modeling.topology_indexing import face_index_of, edge_index_of

    pytest.importorskip("OCP.BRepFeat")

    doc = Document()
    body = Body("pushpull_chamfer_stable_health")
    doc.add_body(body)
    body.add_feature(PrimitiveFeature(primitive_type="box", length=40.0, width=30.0, height=20.0))

    for step in range(5):
        solid = body._build123d_solid
        assert solid is not None
        target_face = max(list(solid.faces()), key=lambda f: f.center().Y)
        target_idx = face_index_of(solid, target_face)
        assert target_idx is not None

        fc = target_face.center()
        sid = doc._shape_naming_service.register_shape(
            ocp_shape=target_face.wrapped,
            shape_type=ShapeType.FACE,
            feature_id=f"pp_seed_{step}",
            local_index=int(target_idx),
            geometry_data=(fc.X, fc.Y, fc.Z, float(target_face.area)),
        )

        pushpull = ExtrudeFeature(
            sketch=None,
            distance=3.0,
            operation="Join",
            face_index=int(target_idx),
            face_shape_id=sid,
            precalculated_polys=[object()],
            name=f"Push/Pull (Join) {step}",
        )
        body.add_feature(pushpull)
        assert pushpull.status in ("OK", "SUCCESS"), pushpull.status_message

    solid = body._build123d_solid
    assert solid is not None and solid.volume > 0.0

    top_face = max(list(solid.faces()), key=lambda f: f.center().Z)
    edge_indices = []
    for edge in top_face.edges():
        edge_idx = edge_index_of(solid, edge)
        if edge_idx is None:
            continue
        idx = int(edge_idx)
        if idx not in edge_indices:
            edge_indices.append(idx)
        if len(edge_indices) >= 4:
            break

    assert edge_indices
    chamfer = ChamferFeature(distance=0.8, edge_indices=edge_indices[:4])
    body.add_feature(chamfer)
    assert chamfer.status in ("OK", "SUCCESS"), chamfer.status_message

    report = doc._shape_naming_service.get_health_report(body)
    pushpull_reports = [f for f in report["features"] if f.get("type") == "Extrude"]
    assert pushpull_reports
    assert all(f.get("broken", 0) == 0 for f in pushpull_reports)
    assert all(f.get("status") == "ok" for f in pushpull_reports)


@pytest.mark.parametrize(
    "directions",
    [
        [(0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (-1.0, 0.0, 0.0)],
        [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0), (-1.0, 0.0, 0.0)],
        [(0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, -1.0)],
    ],
)
def test_pushpull_directional_sequences_keep_tnp_health_stable(directions):
    from modeling.topology_indexing import edge_index_of, face_index_of

    pytest.importorskip("OCP.BRepFeat")

    doc = Document()
    body = Body("pushpull_directional_stable_health")
    doc.add_body(body)
    body.add_feature(PrimitiveFeature(primitive_type="box", length=38.0, width=26.0, height=18.0))

    for step, direction in enumerate(directions):
        solid = body._build123d_solid
        assert solid is not None

        dx, dy, dz = direction
        target_face = max(
            list(solid.faces()),
            key=lambda f: (f.center().X * dx) + (f.center().Y * dy) + (f.center().Z * dz),
        )
        target_idx = face_index_of(solid, target_face)
        assert target_idx is not None

        fc = target_face.center()
        sid = doc._shape_naming_service.register_shape(
            ocp_shape=target_face.wrapped,
            shape_type=ShapeType.FACE,
            feature_id=f"pp_dir_seed_{step}",
            local_index=int(target_idx),
            geometry_data=(fc.X, fc.Y, fc.Z, float(target_face.area)),
        )

        pushpull = ExtrudeFeature(
            sketch=None,
            distance=2.0 + (0.4 * step),
            operation="Join",
            face_index=int(target_idx),
            face_shape_id=sid,
            precalculated_polys=[object()],
            name=f"Push/Pull Dir {step}",
        )
        body.add_feature(pushpull)
        assert pushpull.status in ("OK", "SUCCESS"), pushpull.status_message

    solid = body._build123d_solid
    assert solid is not None and solid.volume > 0.0

    top_face = max(list(solid.faces()), key=lambda f: f.center().Z)
    edge_indices = []
    for edge in top_face.edges():
        edge_idx = edge_index_of(solid, edge)
        if edge_idx is None:
            continue
        idx = int(edge_idx)
        if idx not in edge_indices:
            edge_indices.append(idx)
        if len(edge_indices) >= 4:
            break

    assert len(edge_indices) >= 2
    chamfer = ChamferFeature(distance=0.5, edge_indices=edge_indices[:4])
    body.add_feature(chamfer)
    assert chamfer.status in ("OK", "SUCCESS"), chamfer.status_message

    report = doc._shape_naming_service.get_health_report(body)
    pushpull_reports = [f for f in report["features"] if f.get("type") == "Extrude"]
    assert pushpull_reports
    assert all(f.get("broken", 0) == 0 for f in pushpull_reports)
    assert all(f.get("status") == "ok" for f in pushpull_reports)


def test_rebuild_skips_global_unify_when_topology_refs_exist(monkeypatch):
    shapeupgrade_mod = pytest.importorskip("OCP.ShapeUpgrade")

    def _fail_unify_ctor(*_args, **_kwargs):
        raise AssertionError("global rebuild unify must be skipped when active topology refs exist")

    monkeypatch.setattr(shapeupgrade_mod, "ShapeUpgrade_UnifySameDomain", _fail_unify_ctor)

    body = Body("skip_global_unify_with_tnp_refs")
    body.features = [
        PrimitiveFeature(primitive_type="box", length=20.0, width=20.0, height=20.0),
        SurfaceTextureFeature(face_indices=[0], face_selectors=[_face_selector()]),
    ]

    # Darf nicht crashen; wenn global unify läuft, schlägt der Test fehl.
    body._rebuild()

    assert body._build123d_solid is not None
    assert body.features[0].status in ("OK", "SUCCESS")
    assert body.features[1].status in ("OK", "SUCCESS")


def test_texture_exporter_prefers_face_indices_over_legacy_selector_matching(monkeypatch):
    import modeling.textured_tessellator as textured_tessellator
    import modeling.texture_exporter as texture_exporter
    from modeling.texture_exporter import ResultStatus, apply_textures_to_body

    class _FakeExtracted:
        def __init__(self, n_cells):
            self.n_cells = n_cells

        def extract_surface(self):
            return _FakeMesh(self.n_cells)

    class _FakeMesh:
        def __init__(self, n_cells):
            self.n_cells = n_cells
            self.n_points = max(3, n_cells * 3)

        def extract_cells(self, indices):
            return _FakeExtracted(len(indices))

        def merge(self, other):
            return _FakeMesh(self.n_cells + getattr(other, "n_cells", 0))

        def compute_normals(self, inplace=True):
            return self

    class _Mapping:
        def __init__(self, face_index, triangle_indices):
            self.face_index = face_index
            self.triangle_indices = triangle_indices
            self.center = (0.0, 0.0, 0.0)
            self.normal = (0.0, 0.0, 1.0)
            self.area = 1.0
            self.surface_type = "plane"

    def _fail_selector_match(*_args, **_kwargs):
        raise AssertionError("Legacy selector matching should not run when face_indices are present")

    monkeypatch.setattr(textured_tessellator, "find_matching_mapping", _fail_selector_match)
    monkeypatch.setattr(texture_exporter, "_apply_displacement_to_face", lambda face_mesh, *_args: face_mesh)

    body = Body("texture_idx_first")
    feature = SurfaceTextureFeature(face_indices=[3], face_selectors=[_face_selector()])
    body.features = [feature]

    mesh = _FakeMesh(10)
    mappings = [_Mapping(face_index=3, triangle_indices=[1, 2])]

    final_mesh, results = apply_textures_to_body(mesh, body, mappings)

    assert final_mesh is not None
    assert results
    assert any(r.status == ResultStatus.SUCCESS for r in results)


def test_texture_exporter_resolves_face_shape_ids_before_selector_fallback(monkeypatch):
    import modeling.textured_tessellator as textured_tessellator
    import modeling.texture_exporter as texture_exporter
    from build123d import Solid
    from modeling.texture_exporter import ResultStatus, apply_textures_to_body

    class _FakeExtracted:
        def __init__(self, n_cells):
            self.n_cells = n_cells

        def extract_surface(self):
            return _FakeMesh(self.n_cells)

    class _FakeMesh:
        def __init__(self, n_cells):
            self.n_cells = n_cells
            self.n_points = max(3, n_cells * 3)

        def extract_cells(self, indices):
            return _FakeExtracted(len(indices))

        def merge(self, other):
            return _FakeMesh(self.n_cells + getattr(other, "n_cells", 0))

        def compute_normals(self, inplace=True):
            return self

    class _Mapping:
        def __init__(self, face_index, triangle_indices):
            self.face_index = face_index
            self.triangle_indices = triangle_indices
            self.center = (0.0, 0.0, 0.0)
            self.normal = (0.0, 0.0, 1.0)
            self.area = 1.0
            self.surface_type = "plane"

    def _fail_selector_match(*_args, **_kwargs):
        raise AssertionError("Legacy selector matching should not run when face_shape_ids are present")

    monkeypatch.setattr(textured_tessellator, "find_matching_mapping", _fail_selector_match)
    monkeypatch.setattr(texture_exporter, "_apply_displacement_to_face", lambda face_mesh, *_args: face_mesh)

    doc = Document()
    body = Body("texture_shapeid_first")
    solid = Solid.make_box(10.0, 20.0, 30.0)
    body._build123d_solid = solid
    doc.add_body(body)

    target_idx = 3
    target_face = list(solid.faces())[target_idx]
    fc = target_face.center()
    sid = doc._shape_naming_service.register_shape(
        ocp_shape=target_face.wrapped,
        shape_type=ShapeType.FACE,
        feature_id="feat_tex",
        local_index=target_idx,
        geometry_data=(fc.X, fc.Y, fc.Z, float(target_face.area)),
    )

    feature = SurfaceTextureFeature(face_shape_ids=[sid], face_selectors=[_face_selector()])
    body.features = [feature]

    mesh = _FakeMesh(10)
    mappings = [_Mapping(face_index=target_idx, triangle_indices=[1, 2])]

    final_mesh, results = apply_textures_to_body(mesh, body, mappings)

    assert final_mesh is not None
    assert results
    assert any(r.status == ResultStatus.SUCCESS for r in results)


def test_texture_exporter_does_not_use_selector_recovery_when_tnp_refs_exist(monkeypatch):
    import modeling.textured_tessellator as textured_tessellator
    from modeling.texture_exporter import ResultStatus, apply_textures_to_body

    class _FakeMesh:
        def __init__(self, n_cells):
            self.n_cells = n_cells
            self.n_points = max(3, n_cells * 3)

        def extract_cells(self, indices):
            class _FakeExtracted:
                def __init__(self, n_cells):
                    self.n_cells = n_cells

                def extract_surface(self):
                    return _FakeMesh(self.n_cells)

            return _FakeExtracted(len(indices))

        def merge(self, other):
            return _FakeMesh(self.n_cells + getattr(other, "n_cells", 0))

        def compute_normals(self, inplace=True):
            return self

    class _Mapping:
        def __init__(self, face_index, triangle_indices):
            self.face_index = face_index
            self.triangle_indices = triangle_indices
            self.center = (0.0, 0.0, 0.0)
            self.normal = (0.0, 0.0, 1.0)
            self.area = 1.0
            self.surface_type = "plane"

    def _fail_selector_match(*_args, **_kwargs):
        raise AssertionError("Selector recovery must not run when TNP references exist")

    monkeypatch.setattr(textured_tessellator, "find_matching_mapping", _fail_selector_match)

    body = Body("texture_no_selector_recovery")
    feature = SurfaceTextureFeature(face_indices=[999], face_selectors=[_face_selector()])
    body.features = [feature]

    mesh = _FakeMesh(10)
    mappings = [_Mapping(face_index=3, triangle_indices=[1, 2])]

    final_mesh, results = apply_textures_to_body(mesh, body, mappings)

    assert final_mesh is mesh
    assert results
    assert any(r.status == ResultStatus.WARNING for r in results)
    assert any("TNP-Referenz" in r.message for r in results if r.status == ResultStatus.WARNING)


def test_tnp_health_report_prefers_face_indices_for_surface_texture(monkeypatch):
    from build123d import Solid

    doc = Document()
    body = Body("tnp_health_face_indices")
    body._build123d_solid = Solid.make_box(10.0, 20.0, 30.0)
    doc.add_body(body)

    texture = SurfaceTextureFeature(
        face_indices=[0, 1],
        face_selectors=[_face_selector(), _face_selector()],
    )
    texture.face_shape_ids = [
        _make_shape_id(ShapeType.FACE, "stale_texture", 0),
        _make_shape_id(ShapeType.FACE, "stale_texture", 1),
    ]
    body.features = [texture]

    service = doc._shape_naming_service

    def _fail_resolve(*_args, **_kwargs):
        raise AssertionError("ShapeID resolution should not run when face_indices resolve")

    monkeypatch.setattr(service, "resolve_shape_with_method", _fail_resolve)
    report = service.get_health_report(body)

    assert report["status"] == "ok"
    assert report["ok"] == 2
    assert report["broken"] == 0
    feature_report = report["features"][0]
    assert feature_report["status"] == "ok"
    assert len(feature_report["refs"]) == 2
    assert all(ref["method"] == "index" for ref in feature_report["refs"])


def test_tnp_health_report_prefers_edge_indices_before_shape_ids(monkeypatch):
    from build123d import Solid

    doc = Document()
    body = Body("tnp_health_edge_indices")
    body._build123d_solid = Solid.make_box(10.0, 20.0, 30.0)
    doc.add_body(body)

    patch = NSidedPatchFeature(edge_indices=[0, 1, 2])
    patch.edge_shape_ids = [
        _make_shape_id(ShapeType.EDGE, "stale_patch", 0),
        _make_shape_id(ShapeType.EDGE, "stale_patch", 1),
        _make_shape_id(ShapeType.EDGE, "stale_patch", 2),
    ]
    body.features = [patch]

    service = doc._shape_naming_service

    def _fail_resolve(*_args, **_kwargs):
        raise AssertionError("ShapeID resolution should not run when edge_indices resolve")

    monkeypatch.setattr(service, "resolve_shape_with_method", _fail_resolve)
    report = service.get_health_report(body)

    assert report["status"] == "ok"
    assert report["ok"] == 3
    feature_report = report["features"][0]
    assert feature_report["status"] == "ok"
    assert len(feature_report["refs"]) == 3
    assert all(ref["kind"] == "Edge" for ref in feature_report["refs"])
    assert all(ref["method"] == "index" for ref in feature_report["refs"])


def test_tnp_health_report_prefers_sweep_profile_and_path_indices(monkeypatch):
    from build123d import Solid

    doc = Document()
    body = Body("tnp_health_sweep_indices")
    body._build123d_solid = Solid.make_box(10.0, 20.0, 30.0)
    doc.add_body(body)

    sweep = SweepFeature(
        profile_data={"type": "body_face"},
        path_data={"type": "body_edge", "edge_indices": [0]},
    )
    sweep.profile_face_index = 0
    sweep.profile_shape_id = _make_shape_id(ShapeType.FACE, "stale_sweep_profile", 0)
    sweep.path_shape_id = _make_shape_id(ShapeType.EDGE, "stale_sweep_path", 0)
    body.features = [sweep]

    service = doc._shape_naming_service

    def _fail_resolve(*_args, **_kwargs):
        raise AssertionError("ShapeID resolution should not run when sweep indices resolve")

    monkeypatch.setattr(service, "resolve_shape_with_method", _fail_resolve)
    report = service.get_health_report(body)

    assert report["status"] == "ok"
    assert report["ok"] == 2
    assert report["broken"] == 0
    feature_report = report["features"][0]
    assert feature_report["status"] == "ok"
    assert len(feature_report["refs"]) == 2
    assert {ref["kind"] for ref in feature_report["refs"]} == {"Face", "Edge"}
    assert all(ref["method"] == "index" for ref in feature_report["refs"])


def test_tnp_health_report_shapeid_fallback_is_quiet(monkeypatch):
    from build123d import Solid

    doc = Document()
    body = Body("tnp_health_quiet_shapeid")
    body._build123d_solid = Solid.make_box(10.0, 20.0, 30.0)
    doc.add_body(body)

    texture = SurfaceTextureFeature(face_selectors=[_face_selector()])
    texture.face_shape_ids = [_make_shape_id(ShapeType.FACE, "missing_texture", 0)]
    body.features = [texture]

    service = doc._shape_naming_service
    flags = []

    def _fake_resolve(_shape_id, _solid, *, log_unresolved=True):
        flags.append(log_unresolved)
        return None, "unresolved"

    monkeypatch.setattr(service, "resolve_shape_with_method", _fake_resolve)
    report = service.get_health_report(body)

    assert flags == [False]
    assert report["status"] == "broken"
    feature_report = report["features"][0]
    assert feature_report["broken"] == 1
    assert feature_report["refs"][0]["method"] == "unresolved"


def test_tnp_health_report_uses_status_details_refs_when_topology_fields_missing():
    from build123d import Solid

    doc = Document()
    body = Body("tnp_health_status_details_refs")
    body._build123d_solid = Solid.make_box(10.0, 20.0, 30.0)
    doc.add_body(body)

    texture = SurfaceTextureFeature(face_selectors=[_face_selector()])
    texture.status = "ERROR"
    texture.status_message = "Texture-Referenz nicht gefunden"
    texture.status_details = {
        "code": "operation_failed",
        "hint": "Face neu wählen",
        "refs": {
            "face_indices": [999],
        },
    }
    body.features = [texture]

    report = doc._shape_naming_service.get_health_report(body)

    assert report["status"] == "broken"
    feature_report = report["features"][0]
    assert feature_report["status"] == "broken"
    assert feature_report["broken"] == 1
    assert feature_report["status_message"] == "Texture-Referenz nicht gefunden"
    assert feature_report["status_details"]["code"] == "operation_failed"
    assert feature_report["refs"][0]["method"] == "status_details"
    assert feature_report["refs"][0]["label"] == "face_indices"


def test_tnp_health_report_feature_error_status_overrides_reference_probe():
    from build123d import Solid

    doc = Document()
    body = Body("tnp_health_feature_status_truth")
    body._build123d_solid = Solid.make_box(10.0, 20.0, 30.0)
    doc.add_body(body)

    texture = SurfaceTextureFeature(face_indices=[0], face_selectors=[_face_selector()])
    texture.status = "ERROR"
    texture.status_message = "synthetic rebuild error"
    texture.status_details = {"code": "operation_failed"}
    body.features = [texture]

    report = doc._shape_naming_service.get_health_report(body)

    assert report["status"] == "broken"
    feature_report = report["features"][0]
    assert feature_report["status"] == "broken"
    assert feature_report["broken"] >= 1
    assert any(ref.get("method") == "feature_status" for ref in feature_report.get("refs", []))


def test_tnp_health_report_uses_shape_probe_for_single_ref_even_with_legacy_local_index(monkeypatch):
    from build123d import Solid
    from modeling.topology_indexing import face_from_index

    doc = Document()
    body = Body("tnp_health_face_stale_local_index")
    body._build123d_solid = Solid.make_box(10.0, 20.0, 30.0)
    doc.add_body(body)

    hole = HoleFeature(face_indices=[0], face_selectors=[_face_selector()])
    hole.face_shape_ids = [_make_shape_id(ShapeType.FACE, "hole_health_stale_local", 999)]
    body.features = [hole]

    calls = {"count": 0}

    def _resolve_shape(_shape_id, _solid, *, log_unresolved=True):
        calls["count"] += 1
        assert log_unresolved is False
        target_face = face_from_index(body._build123d_solid, 0)
        assert target_face is not None
        return target_face.wrapped, "direct"

    monkeypatch.setattr(doc._shape_naming_service, "resolve_shape_with_method", _resolve_shape)
    report = doc._shape_naming_service.get_health_report(body)

    assert report["status"] == "ok"
    feature_report = report["features"][0]
    assert feature_report["status"] == "ok"
    assert feature_report["broken"] == 0
    assert feature_report["ok"] == 1
    assert calls["count"] >= 1
    assert feature_report["refs"][0]["method"] == "shape"


def test_migrate_loaded_face_refs_to_shape_ids_repairs_texture_refs_only():
    from build123d import Solid

    doc = Document()
    body = Body("migrate_face_shape_slots")
    body._build123d_solid = Solid.make_box(10.0, 20.0, 30.0)
    doc.add_body(body)

    hole = HoleFeature(face_indices=[0], face_selectors=[_face_selector()])
    hole.face_shape_ids = [_make_shape_id(ShapeType.FACE, "hole_stale_slot", 7)]

    texture = SurfaceTextureFeature(face_indices=[1], face_selectors=[_face_selector()])
    texture.face_shape_ids = [_make_shape_id(ShapeType.FACE, "texture_stale_slot", 9)]

    body.features = [hole, texture]

    migrated = doc._migrate_loaded_face_refs_to_shape_ids()

    assert migrated == 1
    # Consuming features are intentionally not migrated from final BREP.
    assert hole.face_shape_ids[0].feature_id == "hole_stale_slot"
    assert hole.face_shape_ids[0].local_index == 7
    assert isinstance(texture.face_shape_ids[0], ShapeID)
    assert texture.face_shape_ids[0].feature_id == texture.id
    assert texture.face_shape_ids[0].local_index == 0


def test_tnp_health_report_texture_indices_stable_after_undo_redo_cycle():
    doc = Document()
    body = Body("tnp_health_texture_undo_redo")
    doc.add_body(body)

    body.add_feature(PrimitiveFeature(primitive_type="box", length=20.0, width=20.0, height=20.0))

    texture = SurfaceTextureFeature(
        face_indices=[0, 1],
        face_selectors=[_face_selector(), _face_selector()],
    )

    body.add_feature(texture)
    report_after_add = doc._shape_naming_service.get_health_report(body)
    texture_after_add = next(
        feat for feat in report_after_add["features"] if feat.get("name") == texture.name
    )
    assert texture_after_add["broken"] == 0
    assert texture_after_add["ok"] >= 2

    # Undo simulieren (Feature entfernen + Rebuild)
    body.features.remove(texture)
    body._rebuild()

    # Redo simulieren (gleiches Feature wieder hinzufügen + Rebuild)
    body.features.append(texture)
    body._rebuild()

    report_after_redo = doc._shape_naming_service.get_health_report(body)
    texture_after_redo = next(
        feat for feat in report_after_redo["features"] if feat.get("name") == texture.name
    )

    assert texture_after_redo["status"] == "ok"
    assert texture_after_redo["broken"] == 0
    assert texture_after_redo["ok"] >= 2
    assert all(ref.get("method") == "index" for ref in texture_after_redo.get("refs", []))
