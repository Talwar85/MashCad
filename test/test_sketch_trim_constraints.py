import math

from sketcher import Point2D
from sketcher.constraints import Constraint, ConstraintType, calculate_constraint_error
from sketcher.geometry import Arc2D, Line2D, Point2D as GeoPoint2D, get_param_on_entity
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
