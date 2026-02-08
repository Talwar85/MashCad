import pytest
from shapely.geometry import Polygon

from modeling import Body, ChamferFeature, Document, ExtrudeFeature, PrimitiveFeature
from modeling.topology_indexing import edge_index_of, face_index_of
from modeling.tnp_system import ShapeType


def _is_success_status(status: str) -> bool:
    return str(status or "").upper() in {"OK", "SUCCESS"}


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


def _add_pushpull_join(doc: Document, body: Body, step: int, direction, distance: float) -> ExtrudeFeature:
    solid = body._build123d_solid
    assert solid is not None

    face = _pick_face_by_direction(solid, direction)
    face_idx = face_index_of(solid, face)
    assert face_idx is not None
    face_idx = int(face_idx)

    shape_id = _register_face_shape_id(doc, face, f"trust_seed_{step}", face_idx)
    # Realistic payload: GUI stores projected polygons as WKT-serializable shapely polygons.
    poly = Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
    feat = ExtrudeFeature(
        sketch=None,
        distance=float(distance),
        operation="Join",
        face_index=face_idx,
        face_shape_id=shape_id,
        precalculated_polys=[poly],
        name=f"Push/Pull (Join) {step}",
    )
    body.add_feature(feat, rebuild=True)
    return feat


def _top_edge_indices(solid, limit: int = 4):
    top_face = max(list(solid.faces()), key=lambda f: float(f.center().Z))
    indices = []
    for edge in top_face.edges():
        edge_idx = edge_index_of(solid, edge)
        if edge_idx is None:
            continue
        idx = int(edge_idx)
        if idx not in indices:
            indices.append(idx)
        if len(indices) >= limit:
            break
    return indices


def _assert_no_broken_feature_refs(report: dict, include_types: set[str]):
    features = [f for f in report.get("features", []) if f.get("type") in include_types]
    assert features, f"Expected feature types missing: {include_types}"
    for feat in features:
        assert feat.get("status") != "broken", f"Broken feature report: {feat}"
        assert int(feat.get("broken", 0)) == 0, f"Broken refs for feature: {feat}"


def test_trust_gate_rect_pushpull_chamfer_undo_redo_save_load_and_continue(tmp_path):
    pytest.importorskip("OCP.BRepFeat")

    doc = Document("trust_gate_rect")
    body = Body("BodyTrust", document=doc)
    doc.add_body(body, set_active=True)

    base = PrimitiveFeature(primitive_type="box", length=40.0, width=28.0, height=18.0, name="Base Box")
    body.add_feature(base, rebuild=True)
    assert _is_success_status(base.status), base.status_message
    assert body._build123d_solid is not None

    directions = [
        (0.0, 1.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        (-1.0, 0.0, 0.0),
        (0.0, -1.0, 0.0),
    ]
    for step, direction in enumerate(directions):
        pushpull = _add_pushpull_join(doc, body, step, direction, distance=2.0 + (0.25 * step))
        assert _is_success_status(pushpull.status), pushpull.status_message

    solid = body._build123d_solid
    assert solid is not None and float(solid.volume) > 0.0

    edge_indices = _top_edge_indices(solid, limit=4)
    assert edge_indices
    chamfer = ChamferFeature(distance=0.8, edge_indices=edge_indices)
    body.add_feature(chamfer, rebuild=True)
    assert _is_success_status(chamfer.status), chamfer.status_message

    report = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report, {"Extrude", "Chamfer"})

    # Undo (simulate command effect): remove chamfer and rebuild.
    removed = body.features.pop()
    assert removed is chamfer
    body._rebuild()
    assert body._build123d_solid is not None
    assert all(
        _is_success_status(feat.status) for feat in body.features if isinstance(feat, (PrimitiveFeature, ExtrudeFeature))
    )

    # Redo (simulate command effect): re-add same chamfer and rebuild.
    body.features.append(chamfer)
    body._rebuild()
    assert _is_success_status(chamfer.status), chamfer.status_message

    report_after_redo = doc._shape_naming_service.get_health_report(body)
    _assert_no_broken_feature_refs(report_after_redo, {"Extrude", "Chamfer"})

    save_path = tmp_path / "trust_gate_rect_pushpull_chamfer.mshcad"
    assert doc.save_project(str(save_path)) is True
    loaded = Document.load_project(str(save_path))
    assert loaded is not None

    loaded_body = loaded.find_body_by_id(body.id)
    assert loaded_body is not None
    loaded_report = loaded._shape_naming_service.get_health_report(loaded_body)
    _assert_no_broken_feature_refs(loaded_report, {"Extrude", "Chamfer"})

    # Continue modeling after load: one more Push/Pull must work without missing ref errors.
    post_load_pushpull = _add_pushpull_join(loaded, loaded_body, 99, (0.0, 1.0, 0.0), distance=1.4)
    assert _is_success_status(post_load_pushpull.status), post_load_pushpull.status_message
    assert "referenz" not in (post_load_pushpull.status_message or "").lower()

    post_load_report = loaded._shape_naming_service.get_health_report(loaded_body)
    _assert_no_broken_feature_refs(post_load_report, {"Extrude", "Chamfer"})
