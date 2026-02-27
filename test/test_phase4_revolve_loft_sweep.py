"""
Current-body integration tests for revolve, loft, and sweep.

These cover the production OCP paths in Body._compute_revolve(),
Body._compute_loft(), and Body._compute_sweep() instead of the removed
legacy helper classes.
"""

from shapely.geometry import Polygon

from modeling import Body, Document, LoftFeature, RevolveFeature, SweepFeature
from sketcher import Sketch


def _make_doc_body(name: str) -> tuple[Document, Body]:
    doc = Document(f"{name}_doc")
    body = Body(name, document=doc)
    doc.add_body(body)
    return doc, body


def _make_revolve_sketch() -> Sketch:
    sketch = Sketch(name="revolve_profile")
    sketch.closed_profiles = [Polygon([(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)])]
    return sketch


def test_revolve_uses_current_body_kernel_path():
    _doc, body = _make_doc_body("phase4_revolve")
    feature = RevolveFeature(
        sketch=_make_revolve_sketch(),
        angle=180.0,
        axis=(0.0, 1.0, 0.0),
        axis_origin=(0.0, 0.0, 0.0),
        operation="New Body",
        name="Revolve Rect 180",
    )

    solid = body._compute_revolve(feature)

    assert solid is not None
    assert solid.is_valid()
    assert float(solid.volume) > 0.0


def test_loft_uses_current_body_kernel_path():
    _doc, body = _make_doc_body("phase4_loft")
    feature = LoftFeature(
        profile_data=[
            {
                "type": "polygon",
                "coords": [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
                "plane_origin": (0.0, 0.0, 0.0),
                "plane_normal": (0.0, 0.0, 1.0),
            },
            {
                "type": "polygon",
                "coords": [(0.0, 0.0), (6.0, 0.0), (6.0, 3.0), (0.0, 3.0)],
                "plane_origin": (0.0, 0.0, 12.0),
                "plane_normal": (0.0, 0.0, 1.0),
            },
        ],
        ruled=False,
        operation="New Body",
        name="Loft Two Sections",
    )

    solid = body._compute_loft(feature)

    assert solid is not None
    assert solid.is_valid()
    assert float(solid.volume) > 0.0


def test_sweep_uses_current_body_kernel_path():
    _doc, body = _make_doc_body("phase4_sweep")
    feature = SweepFeature(
        profile_data={
            "type": "polygon",
            "coords": [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)],
            "plane_origin": (0.0, 0.0, 0.0),
            "plane_normal": (0.0, 0.0, 1.0),
        },
        path_data={
            "type": "sketch_edge",
            "geometry_type": "line",
            "start": (0.0, 0.0),
            "end": (0.0, 20.0),
            "plane_origin": (0.0, 0.0, 0.0),
            "plane_normal": (0.0, 1.0, 0.0),
            "plane_x": (1.0, 0.0, 0.0),
            "plane_y": (0.0, 0.0, 1.0),
        },
        operation="New Body",
        name="Sweep Line Path",
    )

    solid = body._compute_sweep(feature, None)

    assert solid is not None
    assert solid.is_valid()
    assert float(solid.volume) > 0.0
