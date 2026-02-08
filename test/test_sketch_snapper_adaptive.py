import math

from PySide6.QtCore import QPointF

from gui.sketch_handlers import SketchHandlersMixin
from gui.sketch_snapper import SmartSnapper
from gui.sketch_tools import SketchTool, SnapType
from sketcher.sketch import Sketch


class _FakeEditor:
    def __init__(self, sketch, snap_radius=15, view_scale=1.0):
        self.sketch = sketch
        self.snap_radius = snap_radius
        self.view_scale = view_scale
        self.current_tool = SketchTool.SELECT
        self.grid_snap = False
        self.grid_size = 1.0
        self.spatial_index = None

    def screen_to_world(self, p: QPointF) -> QPointF:
        # Identity mapping is enough for these unit tests.
        return QPointF(p.x(), p.y())


def test_snapper_honors_editor_snap_radius_setting():
    sketch = Sketch("snapper_radius")
    line = sketch.add_line(0.0, 0.0, 100.0, 0.0)
    editor = _FakeEditor(sketch, snap_radius=30, view_scale=1.0)
    snapper = SmartSnapper(editor)

    result = snapper.snap(QPointF(120.0, 0.0))

    assert result.type == SnapType.ENDPOINT
    assert result.target_entity is line


def test_snapper_world_radius_is_clamped_for_zoom_out():
    sketch = Sketch("snapper_zoom_out")
    sketch.add_line(0.0, 0.0, 100.0, 0.0)
    editor = _FakeEditor(sketch, snap_radius=30, view_scale=0.01)
    snapper = SmartSnapper(editor)

    radius = snapper._compute_snap_radius_world()

    assert radius <= 30.0 + 1e-9
    assert radius >= 1e-4


def test_snapper_world_radius_has_min_floor_for_zoom_in():
    sketch = Sketch("snapper_zoom_in")
    sketch.add_line(0.0, 0.0, 100.0, 0.0)
    editor = _FakeEditor(sketch, snap_radius=30, view_scale=1e6)
    snapper = SmartSnapper(editor)

    radius = snapper._compute_snap_radius_world()

    assert math.isclose(radius, 1e-4, rel_tol=0.0, abs_tol=1e-8)


def test_handlers_adaptive_world_tolerance_is_bounded():
    class _Dummy(SketchHandlersMixin):
        pass

    dummy = _Dummy()
    dummy.snap_radius = 200
    dummy.view_scale = 0.01
    high = dummy._adaptive_world_tolerance(scale=0.4, min_world=0.05, max_world=1.5)
    assert math.isclose(high, 1.5, rel_tol=0.0, abs_tol=1e-9)

    dummy.snap_radius = 6
    dummy.view_scale = 1e6
    low = dummy._adaptive_world_tolerance(scale=0.4, min_world=0.05, max_world=1.5)
    assert math.isclose(low, 0.05, rel_tol=0.0, abs_tol=1e-9)


def test_snapper_classifies_virtual_line_intersection():
    sketch = Sketch("virtual_intersection")
    # Real intersection point is on line 1 segment but outside line 2 segment.
    sketch.add_line(100.0, 0.0, 200.0, 0.0)
    sketch.add_line(150.0, 100.0, 150.0, 200.0)
    editor = _FakeEditor(sketch, snap_radius=20, view_scale=1.0)
    editor.current_tool = SketchTool.LINE
    snapper = SmartSnapper(editor)

    result = snapper.snap(QPointF(150.1, 0.1))

    assert result.type == SnapType.VIRTUAL_INTERSECTION
    assert isinstance(result.target_entity, dict)
    assert result.target_entity.get("virtual") is True


def test_snapper_classifies_real_line_intersection():
    sketch = Sketch("real_intersection")
    sketch.add_line(100.0, 0.0, 200.0, 0.0)
    sketch.add_line(150.0, -50.0, 150.0, 50.0)
    editor = _FakeEditor(sketch, snap_radius=20, view_scale=1.0)
    snapper = SmartSnapper(editor)

    result = snapper.snap(QPointF(150.05, 0.05))

    assert result.type == SnapType.INTERSECTION


def test_virtual_intersection_priority_boost_in_drawing_mode():
    sketch = Sketch("virtual_priority")
    editor = _FakeEditor(sketch, snap_radius=20, view_scale=1.0)
    snapper = SmartSnapper(editor)

    editor.current_tool = SketchTool.SELECT
    p_select = snapper._priority_for_snap_type(SnapType.VIRTUAL_INTERSECTION)
    editor.current_tool = SketchTool.LINE
    p_draw = snapper._priority_for_snap_type(SnapType.VIRTUAL_INTERSECTION)

    assert p_draw > p_select


def test_snapper_reports_virtual_intersection_near_miss_diagnostic():
    sketch = Sketch("virtual_diag")
    sketch.add_line(100.0, 0.0, 200.0, 0.0)
    sketch.add_line(150.0, 100.0, 150.0, 200.0)
    editor = _FakeEditor(sketch, snap_radius=5, view_scale=1.0)
    editor.current_tool = SketchTool.LINE
    snapper = SmartSnapper(editor)

    result = snapper.snap(QPointF(150.0, 12.0))

    assert result.type == SnapType.NONE
    assert "Virtueller Schnittpunkt" in result.diagnostic


def test_snapper_no_diagnostic_in_non_drawing_mode():
    sketch = Sketch("virtual_diag_select")
    sketch.add_line(100.0, 0.0, 200.0, 0.0)
    sketch.add_line(150.0, 100.0, 150.0, 200.0)
    editor = _FakeEditor(sketch, snap_radius=5, view_scale=1.0)
    editor.current_tool = SketchTool.SELECT
    snapper = SmartSnapper(editor)

    result = snapper.snap(QPointF(150.0, 12.0))

    assert result.type == SnapType.NONE
    assert result.diagnostic == ""
