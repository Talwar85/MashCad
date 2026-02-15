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
