from shapely.geometry import Polygon

import pytest

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


def _is_non_error(status: str) -> bool:
    return str(status or "").upper() in {"OK", "SUCCESS", "WARNING", "COSMETIC"}


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
        name=f"Ref Push/Pull {step_id}",
    )
    body.add_feature(feat, rebuild=True)
    return feat


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


def _assert_signature_close(a: dict, b: dict, *, context: str):
    assert a["faces"] == b["faces"], f"{context}: face-count mismatch live={a} replay={b}"
    assert a["edges"] == b["edges"], f"{context}: edge-count mismatch live={a} replay={b}"
    assert a["volume"] == pytest.approx(b["volume"], rel=1e-6, abs=1e-6), (
        f"{context}: volume mismatch live={a} replay={b}"
    )
    for i, (av, bv) in enumerate(zip(a["bbox"], b["bbox"])):
        assert av == pytest.approx(bv, rel=1e-6, abs=1e-6), (
            f"{context}: bbox[{i}] mismatch live={a} replay={b}"
        )


@pytest.mark.parametrize("seed", list(range(20)))
def test_parametric_reference_modelset_seed_rebuild_and_roundtrip(seed: int):
    """
    PI-010 Baseline:
    20 deterministische Referenzmodelle mit mehrstufigen Push/Pull-Flows muessen
    Rebuild-idempotent und serialisierungsstabil bleiben.
    """
    doc = Document(f"pi010_doc_{seed}")
    body = Body(f"pi010_body_{seed}", document=doc)
    body.id = f"pi010_body_id_{seed}"
    doc.add_body(body, set_active=True)

    base = PrimitiveFeature(
        primitive_type="box",
        length=20.0 + (seed % 5),
        width=18.0 + ((seed * 2) % 5),
        height=12.0 + ((seed * 3) % 4),
        name=f"Ref Base {seed}",
    )
    body.add_feature(base, rebuild=True)
    assert _is_non_error(base.status)
    assert body._build123d_solid is not None

    for step in range(2):
        direction = _AXIS_DIRECTIONS[(seed + step * 3) % len(_AXIS_DIRECTIONS)]
        distance = 0.8 + 0.2 * ((seed + step) % 5)
        pushpull = _add_pushpull_join(
            doc,
            body,
            step_id=f"pi010_seed_{seed}_step_{step}",
            direction=direction,
            distance=distance,
        )
        assert _is_non_error(pushpull.status)

    # Dritter Schritt fuer edit-intensivere Referenzteile.
    third_direction = _AXIS_DIRECTIONS[(seed + 5) % len(_AXIS_DIRECTIONS)]
    third_distance = 0.6 + 0.1 * (seed % 4)
    pushpull3 = _add_pushpull_join(
        doc,
        body,
        step_id=f"pi010_seed_{seed}_step_2",
        direction=third_direction,
        distance=third_distance,
    )
    assert _is_non_error(pushpull3.status)
    assert body._build123d_solid is not None

    live_sig = _solid_signature(body._build123d_solid)

    # Rebuild-Idempotenz auf demselben Modell.
    body._rebuild()
    replay_sig = _solid_signature(body._build123d_solid)
    _assert_signature_close(live_sig, replay_sig, context=f"seed={seed}: local_rebuild")

    # Persistenz-Roundtrip (in-memory).
    restored_doc = Document.from_dict(doc.to_dict())
    restored_body = restored_doc.find_body_by_id(body.id)
    assert restored_body is not None, f"seed={seed}: restored body missing"
    restored_body._rebuild()
    restored_sig = _solid_signature(restored_body._build123d_solid)
    _assert_signature_close(live_sig, restored_sig, context=f"seed={seed}: roundtrip_rebuild")
