"""
Regression tests for component-scoped mixin behavior.

Focus:
- Extrude operation detection must consider document-wide bodies.
- Parametric sketch rebuild must traverse all document bodies.
- Getting-started overlay must hide for document-wide content.
"""

import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

os.environ["QT_OPENGL"] = "software"

from gui.main_window import MainWindow
from modeling import ExtrudeFeature


class _Centroid:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y


class _Poly:
    def __init__(self, x: float, y: float):
        self.centroid = _Centroid(x, y)


class _Mesh:
    def __init__(self):
        self.points = np.array([[0.0, 0.0, 0.0]], dtype=float)

    def find_closest_point(self, _pt):
        return 0


class _Overlay:
    def __init__(self):
        self._visible = True
        self.hide_calls = 0

    def isVisible(self):
        return self._visible

    def hide(self):
        self._visible = False
        self.hide_calls += 1


def test_detect_extrude_operation_uses_get_all_bodies_when_active_component_empty():
    mw = MainWindow.__new__(MainWindow)
    body = SimpleNamespace(id="B1", name="Body1")
    mesh = _Mesh()

    mw.document = SimpleNamespace(
        bodies=[],
        get_all_bodies=lambda: [body],
    )
    mw.viewport_3d = SimpleNamespace(
        is_body_visible=lambda bid: bid == "B1",
        get_body_mesh=lambda bid: mesh if bid == "B1" else None,
    )

    sketch_face = SimpleNamespace(
        plane_origin=(0.0, 0.0, 0.0),
        plane_normal=(0.0, 0.0, 1.0),
        plane_x=(1.0, 0.0, 0.0),
        plane_y=(0.0, 1.0, 0.0),
        shapely_poly=_Poly(0.0, 0.0),
    )

    result = MainWindow._detect_extrude_operation(mw, sketch_face)

    assert result == "Join"


def test_update_bodies_depending_on_sketch_uses_get_all_bodies_when_active_component_empty():
    mw = MainWindow.__new__(MainWindow)
    sketch = SimpleNamespace(id="S1")
    feature = ExtrudeFeature(sketch=sketch)
    feature._profile_hash = "old_hash"

    body = SimpleNamespace(
        id="B1",
        name="Body1",
        features=[feature],
        _build123d_solid=object(),
        _rebuild=Mock(),
    )

    mw.document = SimpleNamespace(
        bodies=[],
        get_all_bodies=lambda: [body],
    )
    mw._compute_profile_hash = Mock(return_value="new_hash")
    mw._update_body_from_build123d = Mock()

    with patch("modeling.cad_tessellator.CADTessellator.notify_body_changed"):
        MainWindow._update_bodies_depending_on_sketch(mw, sketch)

    body._rebuild.assert_called_once()
    mw._update_body_from_build123d.assert_called_once_with(body, body._build123d_solid)


def test_update_getting_started_hides_overlay_for_document_wide_bodies():
    mw = MainWindow.__new__(MainWindow)
    overlay = _Overlay()

    mw._getting_started_overlay = overlay
    mw.document = SimpleNamespace(
        bodies=[],
        sketches=[],
        get_all_bodies=lambda: [SimpleNamespace(id="B1")],
        get_all_sketches=lambda: [],
    )

    MainWindow._update_getting_started(mw)

    assert overlay.hide_calls == 1
    assert overlay.isVisible() is False


def test_update_getting_started_hides_overlay_for_document_wide_sketches():
    mw = MainWindow.__new__(MainWindow)
    overlay = _Overlay()

    mw._getting_started_overlay = overlay
    mw.document = SimpleNamespace(
        bodies=[],
        sketches=[],
        get_all_bodies=lambda: [],
        get_all_sketches=lambda: [SimpleNamespace(id="S1")],
    )

    MainWindow._update_getting_started(mw)

    assert overlay.hide_calls == 1
    assert overlay.isVisible() is False
