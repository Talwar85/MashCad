import math

from PySide6.QtCore import QPointF

from gui.sketch_handlers import SketchHandlersMixin
from gui.sketch_snapper import SmartSnapper
from gui.sketch_tools import SketchTool, SnapType
from sketcher import ConstraintType
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


class _ConstraintDummy(SketchHandlersMixin):
    def __init__(self, sketch):
        self.sketch = sketch


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
    assert "Tipp:" in result.diagnostic
    assert "Snap-Radius" in result.diagnostic


def test_snapper_reports_far_virtual_intersection_with_fit_tip():
    sketch = Sketch("virtual_diag_far")
    sketch.add_line(100.0, 0.0, 200.0, 0.0)
    sketch.add_line(150.0, 100.0, 150.0, 200.0)
    editor = _FakeEditor(sketch, snap_radius=5, view_scale=1.0)
    editor.current_tool = SketchTool.LINE
    snapper = SmartSnapper(editor)

    result = snapper.snap(QPointF(150.0, 600.0))

    assert result.type == SnapType.NONE
    assert "zu weit entfernt" in result.diagnostic
    assert "Mit F Ansicht einpassen" in result.diagnostic


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


def test_snapper_infers_perpendicular_for_active_line_tool():
    sketch = Sketch("perpendicular_inference")
    line = sketch.add_line(-20.0, 0.0, 60.0, 0.0)
    editor = _FakeEditor(sketch, snap_radius=8, view_scale=1.0)
    editor.current_tool = SketchTool.LINE
    editor.tool_step = 1
    editor.tool_points = [QPointF(10.0, 25.0)]
    snapper = SmartSnapper(editor)

    result = snapper.snap(QPointF(10.2, 0.1))

    assert result.type == SnapType.PERPENDICULAR
    assert result.target_entity is line
    assert math.isclose(result.point.x(), 10.0, rel_tol=0.0, abs_tol=1e-6)
    assert math.isclose(result.point.y(), 0.0, rel_tol=0.0, abs_tol=1e-6)


def test_snapper_infers_tangent_for_active_line_tool():
    sketch = Sketch("tangent_inference")
    circle = sketch.add_circle(0.0, 0.0, 10.0)
    editor = _FakeEditor(sketch, snap_radius=20, view_scale=1.0)
    editor.current_tool = SketchTool.LINE
    editor.tool_step = 1
    editor.tool_points = [QPointF(20.0, 0.0)]
    snapper = SmartSnapper(editor)

    result = snapper.snap(QPointF(4.9, 8.7))

    assert result.type == SnapType.TANGENT
    assert result.target_entity is circle
    assert math.isclose(result.point.x(), 5.0, rel_tol=0.0, abs_tol=1e-3)
    assert math.isclose(result.point.y(), 8.660254, rel_tol=0.0, abs_tol=1e-3)


def test_snapper_infers_horizontal_for_active_line_tool():
    sketch = Sketch("horizontal_inference")
    editor = _FakeEditor(sketch, snap_radius=5, view_scale=1.0)
    editor.current_tool = SketchTool.LINE
    editor.tool_step = 1
    editor.tool_points = [QPointF(50.0, 50.0)]
    snapper = SmartSnapper(editor)

    result = snapper.snap(QPointF(82.0, 52.0))

    assert result.type == SnapType.HORIZONTAL
    assert math.isclose(result.point.y(), 50.0, rel_tol=0.0, abs_tol=1e-6)


def test_snapper_infers_vertical_for_active_line_tool():
    sketch = Sketch("vertical_inference")
    editor = _FakeEditor(sketch, snap_radius=5, view_scale=1.0)
    editor.current_tool = SketchTool.LINE
    editor.tool_step = 1
    editor.tool_points = [QPointF(50.0, 50.0)]
    snapper = SmartSnapper(editor)

    result = snapper.snap(QPointF(52.0, 86.0))

    assert result.type == SnapType.VERTICAL
    assert math.isclose(result.point.x(), 50.0, rel_tol=0.0, abs_tol=1e-6)


def test_snapper_infers_parallel_for_active_line_tool():
    sketch = Sketch("parallel_inference")
    reference = sketch.add_line(0.0, 0.0, 10.0, 10.0)
    editor = _FakeEditor(sketch, snap_radius=3, view_scale=1.0)
    editor.current_tool = SketchTool.LINE
    editor.tool_step = 1
    editor.tool_points = [QPointF(20.0, 0.0)]
    snapper = SmartSnapper(editor)

    result = snapper.snap(QPointF(30.0, 7.0))

    assert result.type == SnapType.PARALLEL
    assert result.target_entity is reference


def test_line_auto_constraints_add_perpendicular_relation_from_snap_type():
    sketch = Sketch("line_auto_perpendicular")
    reference = sketch.add_line(0.0, 0.0, 40.0, 0.0)
    new_line = sketch.add_line(10.0, 20.0, 10.0, 0.0)
    dummy = _ConstraintDummy(sketch)

    dummy._add_point_constraint(
        point=new_line.end,
        pos=QPointF(10.0, 0.0),
        snap_type=SnapType.PERPENDICULAR,
        snap_entity=reference,
        new_line=new_line,
    )

    has_perp = False
    has_point_on_line = False
    target_ids = {reference.id, new_line.id}
    for c in sketch.constraints:
        ids = {e.id for e in c.entities if hasattr(e, "id")}
        if c.type == ConstraintType.PERPENDICULAR and ids == target_ids:
            has_perp = True
        if c.type == ConstraintType.POINT_ON_LINE:
            if reference.id in ids and new_line.end.id in ids:
                has_point_on_line = True

    assert has_perp
    assert has_point_on_line


def test_line_auto_constraints_add_tangent_relation_from_snap_type():
    sketch = Sketch("line_auto_tangent")
    circle = sketch.add_circle(0.0, 0.0, 10.0)
    new_line = sketch.add_line(20.0, 0.0, 5.0, 8.660254)
    dummy = _ConstraintDummy(sketch)

    dummy._add_point_constraint(
        point=new_line.end,
        pos=QPointF(5.0, 8.660254),
        snap_type=SnapType.TANGENT,
        snap_entity=circle,
        new_line=new_line,
    )

    has_tangent = False
    has_point_on_circle = False
    target_ids = {circle.id, new_line.id}
    for c in sketch.constraints:
        ids = {e.id for e in c.entities if hasattr(e, "id")}
        if c.type == ConstraintType.TANGENT and ids == target_ids:
            has_tangent = True
        if c.type == ConstraintType.POINT_ON_CIRCLE:
            if circle.id in ids and new_line.end.id in ids:
                has_point_on_circle = True

    assert has_tangent
    assert has_point_on_circle


def test_line_auto_constraints_add_horizontal_from_snap_type():
    sketch = Sketch("line_auto_horizontal")
    new_line = sketch.add_line(0.0, 0.0, 25.0, 0.0)
    dummy = _ConstraintDummy(sketch)

    dummy._add_point_constraint(
        point=new_line.end,
        pos=QPointF(25.0, 0.0),
        snap_type=SnapType.HORIZONTAL,
        snap_entity=None,
        new_line=new_line,
    )

    assert any(c.type == ConstraintType.HORIZONTAL and new_line in c.entities for c in sketch.constraints)


def test_line_auto_constraints_add_vertical_from_snap_type():
    sketch = Sketch("line_auto_vertical")
    new_line = sketch.add_line(0.0, 0.0, 0.0, 25.0)
    dummy = _ConstraintDummy(sketch)

    dummy._add_point_constraint(
        point=new_line.end,
        pos=QPointF(0.0, 25.0),
        snap_type=SnapType.VERTICAL,
        snap_entity=None,
        new_line=new_line,
    )

    assert any(c.type == ConstraintType.VERTICAL and new_line in c.entities for c in sketch.constraints)


def test_line_auto_constraints_add_parallel_relation_from_snap_type():
    sketch = Sketch("line_auto_parallel")
    reference = sketch.add_line(0.0, 0.0, 10.0, 10.0)
    new_line = sketch.add_line(20.0, 0.0, 30.0, 10.0)
    dummy = _ConstraintDummy(sketch)

    dummy._add_point_constraint(
        point=new_line.end,
        pos=QPointF(30.0, 10.0),
        snap_type=SnapType.PARALLEL,
        snap_entity=reference,
        new_line=new_line,
    )

    target_ids = {reference.id, new_line.id}
    assert any(
        c.type == ConstraintType.PARALLEL and {e.id for e in c.entities if hasattr(e, "id")} == target_ids
        for c in sketch.constraints
    )


def test_snapper_sticky_lock_keeps_previous_snap_briefly():
    sketch = Sketch("sticky_lock")
    line = sketch.add_line(0.0, 0.0, 100.0, 0.0)
    editor = _FakeEditor(sketch, snap_radius=5, view_scale=1.0)
    editor.current_tool = SketchTool.LINE
    snapper = SmartSnapper(editor)

    first = snapper.snap(QPointF(100.0, 0.0))
    second = snapper.snap(QPointF(106.0, 0.0))  # outside snap radius, inside sticky release

    assert first.type == SnapType.ENDPOINT
    assert second.type == SnapType.ENDPOINT
    assert second.target_entity is line
