"""
Regression tests for robust plane basis normalization.
"""

import math

from modeling.geometry_utils import normalize_plane_axes
from modeling.shape_builders import get_plane_from_sketch
from modeling.component import Component
from sketcher import Sketch


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def test_normalize_plane_axes_repairs_parallel_x_dir():
    normal, x_dir, y_dir = normalize_plane_axes((0.0, 0.0, 1.0), (0.0, 0.0, 1.0), (0.0, 0.0, 0.0))

    assert _length(normal) > 0.999
    assert _length(x_dir) > 0.999
    assert _length(y_dir) > 0.999
    assert abs(_dot(normal, x_dir)) < 1e-8
    assert abs(_dot(normal, y_dir)) < 1e-8
    assert abs(_dot(x_dir, y_dir)) < 1e-8


def test_normalize_plane_axes_uses_y_hint_when_x_missing():
    normal, x_dir, y_dir = normalize_plane_axes((0.0, 1.0, 0.0), None, (1.0, 0.0, 0.0))

    assert _length(normal) > 0.999
    assert _length(x_dir) > 0.999
    assert _length(y_dir) > 0.999
    assert abs(_dot(normal, x_dir)) < 1e-8
    assert abs(_dot(normal, y_dir)) < 1e-8
    assert abs(_dot(x_dir, y_dir)) < 1e-8


def test_get_plane_from_sketch_normalizes_invalid_sketch_axes():
    sketch = Sketch(name="PlaneNormalizationSketch")
    sketch.plane_origin = (0.0, 0.0, 0.0)
    sketch.plane_normal = (0.0, 0.0, 1.0)
    sketch.plane_x_dir = (0.0, 0.0, 1.0)  # invalid: parallel to normal
    sketch.plane_y_dir = (0.0, 0.0, 0.0)  # invalid: zero vector

    plane = get_plane_from_sketch(sketch)

    x_dir = (float(plane.x_dir.X), float(plane.x_dir.Y), float(plane.x_dir.Z))
    z_dir = (float(plane.z_dir.X), float(plane.z_dir.Y), float(plane.z_dir.Z))
    assert _length(x_dir) > 0.999
    assert _length(z_dir) > 0.999
    assert abs(_dot(x_dir, z_dir)) < 1e-8


def test_component_from_dict_normalizes_sketch_plane_basis():
    comp_data = {
        "id": "cmp_001",
        "name": "Comp",
        "bodies": [],
        "sketches": [
            {
                "name": "S1",
                "id": "sk_001",
                "points": [],
                "lines": [],
                "line_slot_markers": {},
                "circles": [],
                "arcs": [],
                "arc_slot_markers": {},
                "ellipses": [],
                "splines": [],
                "native_splines": [],
                "constraints": [],
                "closed_profiles": [],
                "plane_origin": [0.0, 0.0, 0.0],
                "plane_normal": [0.0, 0.0, 1.0],
                "plane_x_dir": [0.0, 0.0, 1.0],  # invalid
                "plane_y_dir": [0.0, 0.0, 0.0],  # invalid
            }
        ],
        "planes": [],
        "sub_components": [],
    }

    comp = Component.from_dict(comp_data)
    sketch = comp.sketches[0]

    assert _length(sketch.plane_normal) > 0.999
    assert _length(sketch.plane_x_dir) > 0.999
    assert _length(sketch.plane_y_dir) > 0.999
    assert abs(_dot(sketch.plane_normal, sketch.plane_x_dir)) < 1e-8
    assert abs(_dot(sketch.plane_normal, sketch.plane_y_dir)) < 1e-8
    assert abs(_dot(sketch.plane_x_dir, sketch.plane_y_dir)) < 1e-8
