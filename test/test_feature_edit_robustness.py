import pytest
from shapely.geometry import Polygon

from modeling import (
    Body,
    ChamferFeature,
    Document,
    DraftFeature,
    ExtrudeFeature,
    FilletFeature,
    HoleFeature,
    PrimitiveFeature,
    ShellFeature,
    Sketch,
)


def _is_success(feature) -> bool:
    return str(getattr(feature, "status", "")).upper() in {"SUCCESS", "OK"}


def _make_doc_box_body(name: str, *, length: float, width: float, height: float):
    doc = Document(f"{name}_doc")
    body = Body(name, document=doc)
    doc.add_body(body)
    body.add_feature(PrimitiveFeature(primitive_type="box", length=length, width=width, height=height))
    assert body._build123d_solid is not None
    return doc, body


def test_extrude_edit_distance_rebuild_is_stable():
    sketch = Sketch("pi005_extrude")
    sketch.add_rectangle(0.0, 0.0, 20.0, 20.0)
    sketch.closed_profiles = [Polygon([(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0), (0.0, 0.0)])]

    body = Body("pi005_extrude_body")
    feature = ExtrudeFeature(sketch=sketch, distance=10.0, operation="New Body")
    body.add_feature(feature)
    assert _is_success(feature)

    volume_before = float(body._build123d_solid.volume)
    feature.distance = 25.0
    body._rebuild()

    assert _is_success(feature)
    volume_after = float(body._build123d_solid.volume)
    assert volume_after == pytest.approx(volume_before * 2.5, rel=1e-6, abs=1e-6)


def test_fillet_edit_recovers_from_invalid_radius():
    _, body = _make_doc_box_body("pi005_fillet", length=30.0, width=20.0, height=10.0)
    base_volume = float(body._build123d_solid.volume)

    feature = FilletFeature(radius=0.8, edge_indices=[0, 1, 2, 3])
    body.add_feature(feature)
    assert _is_success(feature)
    assert float(body._build123d_solid.volume) < base_volume

    feature.radius = 50.0
    body._rebuild()
    assert str(feature.status).upper() == "ERROR"
    assert float(body._build123d_solid.volume) == pytest.approx(base_volume, rel=1e-6, abs=1e-6)

    feature.radius = 0.4
    body._rebuild()
    assert _is_success(feature)
    assert float(body._build123d_solid.volume) < base_volume


def test_chamfer_edit_recovers_from_invalid_distance():
    _, body = _make_doc_box_body("pi005_chamfer", length=30.0, width=20.0, height=10.0)
    base_volume = float(body._build123d_solid.volume)

    feature = ChamferFeature(distance=0.6, edge_indices=[0, 1, 2, 3])
    body.add_feature(feature)
    assert _is_success(feature)
    assert float(body._build123d_solid.volume) < base_volume

    feature.distance = 20.0
    body._rebuild()
    assert str(feature.status).upper() == "ERROR"
    assert float(body._build123d_solid.volume) == pytest.approx(base_volume, rel=1e-6, abs=1e-6)

    feature.distance = 0.4
    body._rebuild()
    assert _is_success(feature)
    assert float(body._build123d_solid.volume) < base_volume


def test_hole_edit_recovers_from_invalid_diameter():
    _, body = _make_doc_box_body("pi005_hole", length=40.0, width=40.0, height=20.0)
    base_volume = float(body._build123d_solid.volume)

    feature = HoleFeature(
        hole_type="simple",
        diameter=0.0,
        depth=10.0,
        position=(0.0, 0.0, 10.0),
        direction=(0.0, 0.0, -1.0),
        face_indices=[5],
    )
    body.add_feature(feature)
    assert str(feature.status).upper() == "ERROR"
    assert float(body._build123d_solid.volume) == pytest.approx(base_volume, rel=1e-6, abs=1e-6)

    feature.diameter = 6.0
    body._rebuild()
    assert _is_success(feature)
    assert float(body._build123d_solid.volume) < base_volume


def test_draft_edit_recovers_from_invalid_pull_direction():
    _, body = _make_doc_box_body("pi005_draft", length=20.0, width=20.0, height=20.0)
    base_volume = float(body._build123d_solid.volume)

    feature = DraftFeature(
        draft_angle=3.0,
        pull_direction=(0.0, 0.0, 0.0),
        face_indices=[0],
    )
    body.add_feature(feature)
    assert str(feature.status).upper() == "ERROR"
    assert float(body._build123d_solid.volume) == pytest.approx(base_volume, rel=1e-6, abs=1e-6)

    feature.pull_direction = (0.0, 0.0, 1.0)
    body._rebuild()
    assert _is_success(feature)
    assert float(body._build123d_solid.volume) != pytest.approx(base_volume, rel=1e-6, abs=1e-6)


def test_shell_edit_thickness_updates_result_stably():
    _, body = _make_doc_box_body("pi005_shell", length=30.0, width=30.0, height=30.0)

    feature = ShellFeature(thickness=2.0, face_indices=[0])
    body.add_feature(feature)
    assert _is_success(feature)
    volume_thick = float(body._build123d_solid.volume)

    feature.thickness = 1.0
    body._rebuild()
    assert _is_success(feature)
    volume_thin = float(body._build123d_solid.volume)

    assert volume_thin < volume_thick


def test_fillet_edit_cycles_keep_rollback_contract_stable():
    _, body = _make_doc_box_body("pi006_fillet_cycles", length=30.0, width=20.0, height=10.0)
    base_volume = float(body._build123d_solid.volume)

    fillet = FilletFeature(radius=0.8, edge_indices=[0, 1, 2, 3])
    body.add_feature(fillet)
    assert _is_success(fillet)

    for invalid_radius in (50.0, 40.0, 30.0):
        fillet.radius = invalid_radius
        body._rebuild()

        details = fillet.status_details or {}
        rollback = details.get("rollback") or {}
        assert str(fillet.status).upper() == "ERROR"
        assert details.get("code") == "operation_failed"
        assert details.get("status_class") == "ERROR"
        assert details.get("severity") == "error"
        assert rollback.get("from") is not None
        assert rollback.get("to") is not None
        assert float(body._build123d_solid.volume) == pytest.approx(base_volume, rel=1e-6, abs=1e-6)

        fillet.radius = 0.4
        body._rebuild()
        assert _is_success(fillet)
        assert float(body._build123d_solid.volume) < base_volume


def test_chamfer_edit_cycles_keep_rollback_contract_stable():
    _, body = _make_doc_box_body("pi006_chamfer_cycles", length=30.0, width=20.0, height=10.0)
    base_volume = float(body._build123d_solid.volume)

    chamfer = ChamferFeature(distance=0.8, edge_indices=[0, 1, 2, 3])
    body.add_feature(chamfer)
    assert _is_success(chamfer)

    for invalid_distance in (20.0, 15.0, 12.0):
        chamfer.distance = invalid_distance
        body._rebuild()

        details = chamfer.status_details or {}
        rollback = details.get("rollback") or {}
        assert str(chamfer.status).upper() == "ERROR"
        assert details.get("code") == "operation_failed"
        assert details.get("status_class") == "ERROR"
        assert details.get("severity") == "error"
        assert rollback.get("from") is not None
        assert rollback.get("to") is not None
        assert float(body._build123d_solid.volume) == pytest.approx(base_volume, rel=1e-6, abs=1e-6)

        chamfer.distance = 0.4
        body._rebuild()
        assert _is_success(chamfer)
        assert float(body._build123d_solid.volume) < base_volume


def test_downstream_blocked_feature_recovers_after_upstream_fix():
    _, body = _make_doc_box_body("pi006_blocked_recovery", length=30.0, width=20.0, height=10.0)

    fillet = FilletFeature(radius=50.0, edge_indices=[0, 1, 2, 3])
    body.add_feature(fillet)
    assert str(fillet.status).upper() == "ERROR"

    chamfer = ChamferFeature(distance=0.4, edge_indices=[4, 5, 6, 7])
    body.add_feature(chamfer)

    blocked_details = chamfer.status_details or {}
    assert str(chamfer.status).upper() == "ERROR"
    assert blocked_details.get("code") == "blocked_by_upstream_error"
    assert blocked_details.get("status_class") == "BLOCKED"
    assert blocked_details.get("severity") == "blocked"

    fillet.radius = 0.4
    body._rebuild()

    assert _is_success(fillet)
    recovered_details = chamfer.status_details or {}
    assert recovered_details.get("code") != "blocked_by_upstream_error"
    assert recovered_details.get("status_class") != "BLOCKED"
