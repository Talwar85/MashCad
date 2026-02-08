import math

from sketcher import Point2D
from sketcher.constraints import Constraint, ConstraintType, calculate_constraint_error
from sketcher.geometry import (
    Arc2D,
    Circle2D,
    Line2D,
    Point2D as GeoPoint2D,
    circle_line_intersection,
    get_param_on_entity,
)
from sketcher.operations.trim import TrimOperation
from sketcher.parametric_solver import ParametricSolver
from sketcher.sketch import Sketch


def _line_endpoints(line):
    return (
        round(line.start.x, 6),
        round(line.start.y, 6),
        round(line.end.x, 6),
        round(line.end.y, 6),
    )


def test_get_param_on_entity_supports_arc_angle():
    arc = Arc2D(center=GeoPoint2D(0.0, 0.0), radius=10.0, start_angle=0.0, end_angle=180.0)
    pt = GeoPoint2D(0.0, 10.0)

    t = get_param_on_entity(pt, arc)

    assert 0.0 <= t <= 2.0 * math.pi
    assert math.isclose(t, math.pi / 2.0, rel_tol=1e-6)


def test_circle_line_intersection_handles_near_tangent_numeric_noise():
    circle = Circle2D(center=GeoPoint2D(0.0, 0.0), radius=5.0)
    line = Line2D(start=GeoPoint2D(-10.0, 5.0 + 1e-10), end=GeoPoint2D(10.0, 5.0 + 1e-10))

    intersections = circle_line_intersection(circle, line, segment_only=True)

    assert len(intersections) == 1
    assert abs(intersections[0].x) < 1e-3
    assert abs(intersections[0].y - 5.0) < 1e-3


def test_trim_line_keeps_opposite_segment():
    sketch = Sketch("trim_line")
    target = sketch.add_line(0.0, 0.0, 10.0, 0.0)
    sketch.add_line(5.0, -5.0, 5.0, 5.0)

    op = TrimOperation(sketch)
    find_result = op.find_segment(target, Point2D(2.0, 0.0))
    assert find_result.success

    exec_result = op.execute_trim(find_result.segment)
    assert exec_result.success

    # Erwartung: Cutter + verbleibendes Teilstück auf der rechten Seite
    assert len(sketch.lines) == 2
    horizontal = [l for l in sketch.lines if abs(l.start.y - l.end.y) < 1e-9]
    assert len(horizontal) == 1
    endpoints = _line_endpoints(horizontal[0])
    assert endpoints in (
        (5.0, 0.0, 10.0, 0.0),
        (10.0, 0.0, 5.0, 0.0),
    )


def test_trim_line_does_not_snap_to_nearby_unrelated_point():
    sketch = Sketch("trim_precision")
    target = sketch.add_line(0.0, 0.0, 10.0, 0.0)
    sketch.add_line(5.0, -5.0, 5.0, 5.0)
    sketch.add_point(5.5, 0.0)  # nahe am echten Schnittpunkt, aber nicht identisch

    op = TrimOperation(sketch)
    find_result = op.find_segment(target, Point2D(2.0, 0.0))
    assert find_result.success

    exec_result = op.execute_trim(find_result.segment)
    assert exec_result.success

    horizontal = [l for l in sketch.lines if abs(l.start.y - l.end.y) < 1e-9]
    assert len(horizontal) == 1
    x_values = sorted([round(horizontal[0].start.x, 6), round(horizontal[0].end.x, 6)])
    assert x_values == [5.0, 10.0]


def test_trim_line_reuses_shared_endpoint_object():
    sketch = Sketch("trim_shared_endpoint")
    target = sketch.add_line(0.0, 0.0, 10.0, 0.0)
    sketch.add_line(5.0, -5.0, 5.0, 5.0)
    branch = sketch.add_line(10.0, 0.0, 10.0, 8.0)
    shared_point = branch.start

    op = TrimOperation(sketch)
    find_result = op.find_segment(target, Point2D(2.0, 0.0))
    assert find_result.success

    exec_result = op.execute_trim(find_result.segment)
    assert exec_result.success

    horizontal = [l for l in sketch.lines if abs(l.start.y - l.end.y) < 1e-9]
    assert len(horizontal) == 1
    remaining = horizontal[0]
    assert remaining.start is shared_point or remaining.end is shared_point


def test_trim_adaptive_fuzzy_intersection_for_large_scale_near_miss():
    sketch = Sketch("trim_large_fuzzy")
    target_arc = sketch.add_arc(0.0, 0.0, 5000.0, 0.0, 180.0)
    near_line = sketch.add_line(-6000.0, 5000.02, 6000.0, 5000.02)

    op = TrimOperation(sketch)
    cuts = op._calculate_intersections(target_arc, [near_line])

    assert len(cuts) >= 3  # Arc start/end + injected fuzzy cut
    assert any(abs(p.y - 5000.0) < 0.05 for _, p in cuts)


def test_trim_adaptive_merge_tolerance_reuses_near_point_on_large_model():
    sketch = Sketch("trim_large_merge_tolerance")
    target = sketch.add_line(0.0, 0.0, 10000.0, 0.0)
    sketch.add_line(5000.0, -200.0, 5000.0, 200.0)
    nearby_branch = sketch.add_line(5000.002, 0.0, 5000.002, 50.0)
    nearby_point = nearby_branch.start

    op = TrimOperation(sketch)
    find_result = op.find_segment(target, Point2D(2000.0, 0.0))
    assert find_result.success

    exec_result = op.execute_trim(find_result.segment)
    assert exec_result.success

    horizontal = [l for l in sketch.lines if abs(l.start.y - l.end.y) < 1e-9]
    assert len(horizontal) == 1
    remaining = horizontal[0]
    assert remaining.start is nearby_point or remaining.end is nearby_point


def test_trim_line_accepts_click_slightly_outside_segment_range():
    sketch = Sketch("trim_outside_click_range")
    target = sketch.add_line(0.0, 0.0, 10.0, 0.0)
    sketch.add_line(5.0, -5.0, 5.0, 5.0)

    op = TrimOperation(sketch)
    find_result = op.find_segment(target, Point2D(-0.05, 0.0))
    assert find_result.success

    exec_result = op.execute_trim(find_result.segment)
    assert exec_result.success

    horizontal = [l for l in sketch.lines if abs(l.start.y - l.end.y) < 1e-9]
    assert len(horizontal) == 1
    x_values = sorted([round(horizontal[0].start.x, 6), round(horizontal[0].end.x, 6)])
    assert x_values == [5.0, 10.0]


def test_trim_line_migrates_horizontal_constraint_to_remaining_segment():
    sketch = Sketch("trim_constraint_migration")
    target = sketch.add_line(0.0, 0.0, 10.0, 0.0)
    sketch.add_horizontal(target)
    sketch.add_line(5.0, -5.0, 5.0, 5.0)

    op = TrimOperation(sketch)
    find_result = op.find_segment(target, Point2D(2.0, 0.0))
    assert find_result.success

    exec_result = op.execute_trim(find_result.segment)
    assert exec_result.success

    horizontal_lines = [l for l in sketch.lines if abs(l.start.y - l.end.y) < 1e-9]
    assert len(horizontal_lines) == 1
    remaining_line = horizontal_lines[0]

    horizontal_constraints = [c for c in sketch.constraints if c.type == ConstraintType.HORIZONTAL]
    assert len(horizontal_constraints) == 1
    assert horizontal_constraints[0].entities[0] is remaining_line


def test_trim_line_does_not_migrate_length_constraint():
    sketch = Sketch("trim_length_removed")
    target = sketch.add_line(0.0, 0.0, 10.0, 0.0)
    sketch.add_length(target, 10.0)
    sketch.add_line(5.0, -5.0, 5.0, 5.0)

    op = TrimOperation(sketch)
    find_result = op.find_segment(target, Point2D(2.0, 0.0))
    assert find_result.success

    exec_result = op.execute_trim(find_result.segment)
    assert exec_result.success

    length_constraints = [c for c in sketch.constraints if c.type == ConstraintType.LENGTH]
    assert len(length_constraints) == 0


def test_trim_rolls_back_geometry_on_exception(monkeypatch):
    sketch = Sketch("trim_rollback")
    target = sketch.add_line(0.0, 0.0, 10.0, 0.0)
    cutter = sketch.add_line(5.0, -5.0, 5.0, 5.0)
    sketch.add_horizontal(target)

    op = TrimOperation(sketch)
    find_result = op.find_segment(target, Point2D(2.0, 0.0))
    assert find_result.success

    before_line_ids = {id(line) for line in sketch.lines}
    before_constraint_count = len(sketch.constraints)

    def _boom(_segment):
        raise RuntimeError("forced trim failure")

    monkeypatch.setattr(op, "_recreate_line_segments", _boom)

    exec_result = op.execute_trim(find_result.segment)
    assert exec_result.success is False

    after_line_ids = {id(line) for line in sketch.lines}
    assert before_line_ids == after_line_ids
    assert target in sketch.lines
    assert cutter in sketch.lines
    assert len(sketch.constraints) == before_constraint_count


def test_trim_circle_migrates_radius_constraint_to_created_arc():
    sketch = Sketch("trim_circle_radius_migration")
    target_circle = sketch.add_circle(0.0, 0.0, 10.0)
    sketch.add_radius(target_circle, 10.0)
    sketch.add_line(0.0, -20.0, 0.0, 20.0)

    op = TrimOperation(sketch)
    find_result = op.find_segment(target_circle, Point2D(10.0, 0.0))
    assert find_result.success

    exec_result = op.execute_trim(find_result.segment)
    assert exec_result.success
    assert len(sketch.circles) == 0
    assert len(sketch.arcs) == 1

    radius_constraints = [c for c in sketch.constraints if c.type == ConstraintType.RADIUS]
    assert len(radius_constraints) == 1
    assert radius_constraints[0].entities[0] is sketch.arcs[0]


def test_trim_circle_does_not_migrate_diameter_constraint_to_arc():
    sketch = Sketch("trim_circle_no_diameter_migration")
    target_circle = sketch.add_circle(0.0, 0.0, 10.0)
    sketch.add_diameter(target_circle, 20.0)
    sketch.add_line(0.0, -20.0, 0.0, 20.0)

    op = TrimOperation(sketch)
    find_result = op.find_segment(target_circle, Point2D(10.0, 0.0))
    assert find_result.success

    exec_result = op.execute_trim(find_result.segment)
    assert exec_result.success
    assert len(sketch.arcs) == 1

    diameter_constraints = [c for c in sketch.constraints if c.type == ConstraintType.DIAMETER]
    assert len(diameter_constraints) == 0


def test_trim_arc_migrates_concentric_constraint_when_single_segment_remains():
    sketch = Sketch("trim_arc_concentric_migration")
    target_arc = sketch.add_arc(0.0, 0.0, 10.0, 0.0, 180.0)
    ref_circle = sketch.add_circle(0.0, 0.0, 4.0)
    sketch.add_concentric(target_arc, ref_circle)
    sketch.add_line(0.0, -20.0, 0.0, 20.0)

    op = TrimOperation(sketch)
    find_result = op.find_segment(target_arc, Point2D(8.0, 5.0))
    assert find_result.success

    exec_result = op.execute_trim(find_result.segment)
    assert exec_result.success
    assert len(sketch.arcs) == 1

    concentric_constraints = [c for c in sketch.constraints if c.type == ConstraintType.CONCENTRIC]
    assert len(concentric_constraints) == 1
    assert sketch.arcs[0] in concentric_constraints[0].entities
    assert ref_circle in concentric_constraints[0].entities


def test_trim_arc_skips_radius_migration_when_multiple_segments_remain():
    sketch = Sketch("trim_arc_multi_segment_no_migration")
    target_arc = sketch.add_arc(0.0, 0.0, 10.0, 0.0, 180.0)
    sketch.add_radius(target_arc, 10.0)
    sketch.add_line(-5.0, -20.0, -5.0, 20.0)
    sketch.add_line(5.0, -20.0, 5.0, 20.0)

    op = TrimOperation(sketch)
    find_result = op.find_segment(target_arc, Point2D(0.0, 10.0))
    assert find_result.success

    exec_result = op.execute_trim(find_result.segment)
    assert exec_result.success
    assert len(sketch.arcs) == 2

    radius_constraints = [c for c in sketch.constraints if c.type == ConstraintType.RADIUS]
    assert len(radius_constraints) == 0


def test_trim_arc_recreates_remaining_arc_segment():
    sketch = Sketch("trim_arc")
    target_arc = sketch.add_arc(0.0, 0.0, 10.0, 0.0, 180.0)
    sketch.add_line(0.0, -20.0, 0.0, 20.0)

    op = TrimOperation(sketch)
    find_result = op.find_segment(target_arc, Point2D(7.0, 7.0))
    assert find_result.success

    exec_result = op.execute_trim(find_result.segment)
    assert exec_result.success

    # Erwartung: ein verbleibender Arc plus die Cutter-Linie
    assert len(sketch.arcs) == 1
    remaining = sketch.arcs[0]
    assert remaining.radius == 10.0
    assert 1.0 < remaining.sweep_angle < 180.0


def test_solver_handles_redundant_but_consistent_constraints():
    sketch = Sketch("redundant")
    line = sketch.add_line(0.0, 0.0, 10.0, 0.0)

    sketch.add_fixed(line.start)
    sketch.add_horizontal(line)
    sketch.add_length(line, 10.0)
    sketch.add_distance(line.start, line.end, 10.0)  # redundant, aber konsistent

    result = sketch.solve()
    assert result.success


def test_invalid_constraint_error_is_not_silently_zero():
    line = Line2D(start=GeoPoint2D(0.0, 0.0), end=GeoPoint2D(3.0, 4.0))
    invalid = Constraint(type=ConstraintType.LENGTH, entities=[], value=5.0)

    err = calculate_constraint_error(invalid)

    assert err >= 1e5


def test_dimension_constraint_with_none_value_is_finite():
    line = Line2D(start=GeoPoint2D(0.0, 0.0), end=GeoPoint2D(3.0, 4.0))
    c = Constraint(type=ConstraintType.LENGTH, entities=[line], value=None)

    err = calculate_constraint_error(c)

    assert math.isfinite(err)
    assert err >= 0.0


def test_parametric_solver_support_gate_for_arc_sketch():
    sketch = Sketch("arc_support")
    sketch.add_arc(0.0, 0.0, 5.0, 0.0, 90.0)

    supported, reason = ParametricSolver(sketch).supports_current_sketch()

    assert supported is False
    assert "Arc" in reason or "Arcs" in reason
