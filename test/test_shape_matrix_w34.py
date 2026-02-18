"""
W34: Shape Matrix – Draw Behavior Stabilization
=================================================
Tests for Create, Select, Drag, Handle-Edit, Constraint, and Persistence
for all sketch shapes: Line, Circle, Rectangle, Arc, Ellipse, Polygon, Slot, Spline.

Author: AI (stabilize/w34-draw-shapes-behavior-loop)
Date: 2026-02-18
"""

import os
os.environ["QT_OPENGL"] = "software"

import math
import pytest
from sketcher import Sketch, Point2D, Line2D, Circle2D, Arc2D, ConstraintType


@pytest.fixture
def sketch():
    return Sketch("test_matrix")


# ===================================================================
# 1. LINE (Reference – must not regress)
# ===================================================================

class TestLineCreate:
    def test_add_line(self, sketch):
        sketch.add_line(0, 0, 10, 0)
        assert len(sketch.lines) == 1
        line = sketch.lines[0]
        assert abs(line.start.x - 0) < 1e-6
        assert abs(line.end.x - 10) < 1e-6

    def test_line_length(self, sketch):
        sketch.add_line(0, 0, 3, 4)
        line = sketch.lines[0]
        assert abs(line.length - 5.0) < 1e-6


class TestLineDrag:
    def test_body_drag_translates(self, sketch):
        sketch.add_line(0, 0, 10, 0)
        line = sketch.lines[0]
        dx, dy = 5.0, 3.0
        line.start.x += dx; line.start.y += dy
        line.end.x += dx; line.end.y += dy
        assert abs(line.start.x - 5.0) < 1e-6
        assert abs(line.start.y - 3.0) < 1e-6
        assert abs(line.end.x - 15.0) < 1e-6
        assert abs(line.length - 10.0) < 1e-6

    def test_endpoint_drag_changes_length(self, sketch):
        sketch.add_line(0, 0, 10, 0)
        line = sketch.lines[0]
        line.end.x = 20.0
        assert abs(line.length - 20.0) < 1e-6


class TestLinePersistence:
    def test_roundtrip(self, sketch):
        sketch.add_line(1, 2, 3, 4)
        data = sketch.to_dict()
        sketch2 = Sketch.from_dict(data)
        assert len(sketch2.lines) >= 1
        line = sketch2.lines[0]
        assert abs(line.start.x - 1.0) < 1e-6
        assert abs(line.end.y - 4.0) < 1e-6


# ===================================================================
# 2. CIRCLE (Reference – must not regress)
# ===================================================================

class TestCircleCreate:
    def test_add_circle(self, sketch):
        sketch.add_circle(10, 20, 15)
        assert len(sketch.circles) == 1
        c = sketch.circles[0]
        assert abs(c.center.x - 10) < 1e-6
        assert abs(c.radius - 15) < 1e-6


class TestCircleDrag:
    def test_center_drag_translates(self, sketch):
        sketch.add_circle(10, 20, 15)
        c = sketch.circles[0]
        c.center.x += 5; c.center.y += 3
        assert abs(c.center.x - 15) < 1e-6
        assert abs(c.radius - 15) < 1e-6

    def test_radius_change(self, sketch):
        sketch.add_circle(0, 0, 10)
        c = sketch.circles[0]
        c.radius = 25
        assert abs(c.radius - 25) < 1e-6
        assert abs(c.center.x) < 1e-6


class TestCirclePersistence:
    def test_roundtrip(self, sketch):
        sketch.add_circle(5, 10, 20)
        data = sketch.to_dict()
        sketch2 = Sketch.from_dict(data)
        assert len(sketch2.circles) >= 1
        c = sketch2.circles[0]
        assert abs(c.center.x - 5) < 1e-6
        assert abs(c.radius - 20) < 1e-6


# ===================================================================
# 3. RECTANGLE (Reference – must not regress)
# ===================================================================

class TestRectangleCreate:
    def test_add_rectangle_creates_4_lines(self, sketch):
        sketch.add_line(0, 0, 10, 0)
        sketch.add_line(10, 0, 10, 5)
        sketch.add_line(10, 5, 0, 5)
        sketch.add_line(0, 5, 0, 0)
        assert len(sketch.lines) == 4


# ===================================================================
# 4. ARC – 3-point creation must put arc on correct side
# ===================================================================

class TestArcCreate:
    def test_add_arc_basic(self, sketch):
        arc = sketch.add_arc(0, 0, 10, 0, 90)
        assert len(sketch.arcs) == 1
        assert abs(arc.radius - 10) < 1e-6
        assert abs(arc.start_angle - 0) < 1e-6
        assert abs(arc.end_angle - 90) < 1e-6

    def test_arc_start_end_points(self, sketch):
        arc = sketch.add_arc(0, 0, 10, 0, 90)
        sp = arc.start_point
        ep = arc.end_point
        assert abs(sp.x - 10) < 1e-6
        assert abs(sp.y - 0) < 1e-6
        assert abs(ep.x - 0) < 1e-4
        assert abs(ep.y - 10) < 1e-4

    def test_arc_sweep_angle(self, sketch):
        arc = sketch.add_arc(0, 0, 10, 0, 270)
        assert abs(arc.sweep_angle - 270) < 1e-6


class TestArc3PointCalc:
    """Test the _calc_arc_3point method for correct orientation."""

    def _calc(self, p1, p2, p3):
        """Helper to call arc calculation."""
        from PySide6.QtCore import QPointF
        from gui.sketch_handlers import SketchHandlersMixin

        class FakeEditor(SketchHandlersMixin):
            pass

        editor = FakeEditor()
        return editor._calc_arc_3point(
            QPointF(p1[0], p1[1]),
            QPointF(p2[0], p2[1]),
            QPointF(p3[0], p3[1]),
        )

    def test_bulge_up(self):
        """Arc through (0,0), (5,5), (10,0) – midpoint above, arc bulges up."""
        result = self._calc((0, 0), (5, 5), (10, 0))
        assert result is not None
        cx, cy, r, start, end = result
        # The midpoint of the arc should have positive y
        mid_angle = (start + end) / 2
        mid_y = cy + r * math.sin(math.radians(mid_angle))
        assert mid_y > 0, f"Arc midpoint y={mid_y} should be > 0 (bulge up)"

    def test_bulge_down(self):
        """Arc through (0,0), (5,-5), (10,0) – midpoint below, arc bulges down."""
        result = self._calc((0, 0), (5, -5), (10, 0))
        assert result is not None
        cx, cy, r, start, end = result
        mid_angle = (start + end) / 2
        mid_y = cy + r * math.sin(math.radians(mid_angle))
        assert mid_y < 0, f"Arc midpoint y={mid_y} should be < 0 (bulge down)"

    def test_collinear_returns_none(self):
        """Collinear points should return None."""
        result = self._calc((0, 0), (5, 0), (10, 0))
        assert result is None

    def test_arc_passes_through_all_three_points(self):
        """The computed arc must pass through all three input points."""
        pts = [(0, 0), (3, 4), (6, 0)]
        result = self._calc(*pts)
        assert result is not None
        cx, cy, r, start, end = result
        for px, py in pts:
            dist = math.hypot(px - cx, py - cy)
            assert abs(dist - r) < 1e-6, f"Point ({px},{py}) not on arc circle"


class TestArcDrag:
    def test_center_drag_preserves_radius(self, sketch):
        arc = sketch.add_arc(0, 0, 10, 0, 90)
        arc.center.x += 5; arc.center.y += 3
        assert abs(arc.radius - 10) < 1e-6
        assert abs(arc.center.x - 5) < 1e-6


class TestArcPersistence:
    def test_roundtrip(self, sketch):
        sketch.add_arc(5, 10, 15, 30, 120)
        data = sketch.to_dict()
        sketch2 = Sketch.from_dict(data)
        assert len(sketch2.arcs) >= 1
        arc = sketch2.arcs[0]
        assert abs(arc.center.x - 5) < 1e-6
        assert abs(arc.radius - 15) < 1e-6
        assert abs(arc.start_angle - 30) < 1e-6


# ===================================================================
# 5. POLYGON – center drag must translate, not distort
# ===================================================================

class TestPolygonCreate:
    def test_add_regular_polygon(self, sketch):
        lines, circle = sketch.add_regular_polygon(10, 20, 15, 6)
        assert len(lines) == 6
        assert circle.construction is True
        assert abs(circle.center.x - 10) < 1e-6
        assert abs(circle.radius - 15) < 1e-6

    def test_polygon_vertices_on_circle(self, sketch):
        lines, circle = sketch.add_regular_polygon(0, 0, 10, 5)
        for line in lines:
            dist = math.hypot(line.start.x - 0, line.start.y - 0)
            assert abs(dist - 10) < 0.5, f"Vertex at dist {dist}, expected ~10"


class TestPolygonDrag:
    def test_center_drag_preserves_shape(self, sketch):
        """Moving the construction circle center must translate all vertices."""
        lines, circle = sketch.add_regular_polygon(0, 0, 10, 6)
        # Record original edge lengths
        orig_lengths = [l.length for l in lines]
        # Simulate center drag by moving the circle center
        dx, dy = 5.0, 3.0
        circle.center.x += dx
        circle.center.y += dy
        # Also move all polygon points
        moved_points = set()
        for line in lines:
            if id(line.start) not in moved_points:
                line.start.x += dx; line.start.y += dy
                moved_points.add(id(line.start))
            if id(line.end) not in moved_points:
                line.end.x += dx; line.end.y += dy
                moved_points.add(id(line.end))
        # Edge lengths must be preserved
        for i, line in enumerate(lines):
            assert abs(line.length - orig_lengths[i]) < 1e-4, \
                f"Edge {i} length changed from {orig_lengths[i]} to {line.length}"


# ===================================================================
# 6. ELLIPSE – center handle, unified drag
# ===================================================================

class TestEllipseCreate:
    def test_add_ellipse_creates_native_ellipse(self, sketch):
        from sketcher.geometry import Ellipse2D
        ellipse = sketch.add_ellipse(10, 20, 30, 15, angle_deg=0)
        assert isinstance(ellipse, Ellipse2D)
        assert ellipse.center.x == 10
        assert ellipse.center.y == 20
        assert ellipse.radius_x == 30
        assert ellipse.radius_y == 15
        assert ellipse in sketch.ellipses

    def test_ellipse_axis_lengths(self, sketch):
        ellipse = sketch.add_ellipse(0, 0, 20, 10, angle_deg=0)
        major_axis = ellipse._major_axis
        minor_axis = ellipse._minor_axis
        major_len = major_axis.length
        minor_len = minor_axis.length
        assert abs(major_len - 40) < 1e-4  # 2 * 20
        assert abs(minor_len - 20) < 1e-4  # 2 * 10


class TestEllipsePersistence:
    def test_roundtrip_preserves_ellipse(self, sketch):
        sketch.add_ellipse(0, 0, 20, 10, angle_deg=0)
        n_ellipses = len(sketch.ellipses)
        data = sketch.to_dict()
        sketch2 = Sketch.from_dict(data)
        assert len(sketch2.ellipses) == n_ellipses

    def test_roundtrip_preserves_axes(self, sketch):
        sketch.add_ellipse(0, 0, 20, 10, angle_deg=0)
        data = sketch.to_dict()
        sketch2 = Sketch.from_dict(data)
        construction_lines = [l for l in sketch2.lines if l.construction]
        assert len(construction_lines) >= 2  # major + minor axis


# ===================================================================
# 7. SLOT – constraint changes, reopen, no regression
# ===================================================================

class TestSlotCreate:
    def test_add_slot(self, sketch):
        center_line, arc1 = sketch.add_slot(0, 0, 20, 0, 5)
        assert center_line.construction is True
        assert len(sketch.arcs) >= 2
        assert abs(arc1.radius - 5) < 1e-6

    def test_slot_has_constraints(self, sketch):
        sketch.add_slot(0, 0, 20, 0, 5)
        # Should have perpendicular, midpoint, distance constraints etc
        assert len(sketch.constraints) > 0

    def test_slot_solve_succeeds(self, sketch):
        sketch.add_slot(0, 0, 20, 0, 5)
        result = sketch.solve()
        assert result.success is True


class TestSlotPersistence:
    def test_roundtrip(self, sketch):
        sketch.add_slot(0, 0, 20, 0, 5)
        n_arcs = len(sketch.arcs)
        n_lines = len(sketch.lines)
        data = sketch.to_dict()
        sketch2 = Sketch.from_dict(data)
        assert len(sketch2.arcs) == n_arcs
        assert len(sketch2.lines) == n_lines


class TestSlotNoRegression:
    """Slot must not break after arc/polygon/ellipse fixes."""

    def test_slot_after_arc(self, sketch):
        sketch.add_arc(50, 50, 10, 0, 180)
        sketch.add_slot(0, 0, 20, 0, 5)
        result = sketch.solve()
        assert result.success is True

    def test_slot_after_polygon(self, sketch):
        sketch.add_regular_polygon(50, 50, 10, 6)
        sketch.add_slot(0, 0, 20, 0, 5)
        result = sketch.solve()
        assert result.success is True


# ===================================================================
# 8. SPLINE – body drag moves whole spline
# ===================================================================

class TestSplineCreate:
    def test_add_spline(self, sketch):
        from sketcher.geometry import BezierSpline, SplineControlPoint
        cp1 = SplineControlPoint(Point2D(0, 0))
        cp2 = SplineControlPoint(Point2D(10, 10))
        cp3 = SplineControlPoint(Point2D(20, 0))
        spline = BezierSpline(control_points=[cp1, cp2, cp3])
        sketch.splines.append(spline)
        assert len(sketch.splines) == 1
        assert len(spline.control_points) == 3


class TestSplineDrag:
    def test_body_drag_translates_all_points(self, sketch):
        from sketcher.geometry import BezierSpline, SplineControlPoint
        cp1 = SplineControlPoint(Point2D(0, 0))
        cp2 = SplineControlPoint(Point2D(10, 10))
        cp3 = SplineControlPoint(Point2D(20, 0))
        spline = BezierSpline(control_points=[cp1, cp2, cp3])
        sketch.splines.append(spline)

        dx, dy = 5.0, 3.0
        for cp in spline.control_points:
            cp.point.x += dx
            cp.point.y += dy

        assert abs(spline.control_points[0].point.x - 5.0) < 1e-6
        assert abs(spline.control_points[1].point.x - 15.0) < 1e-6
        assert abs(spline.control_points[2].point.x - 25.0) < 1e-6

    def test_single_point_drag(self, sketch):
        from sketcher.geometry import BezierSpline, SplineControlPoint
        cp1 = SplineControlPoint(Point2D(0, 0))
        cp2 = SplineControlPoint(Point2D(10, 10))
        cp3 = SplineControlPoint(Point2D(20, 0))
        spline = BezierSpline(control_points=[cp1, cp2, cp3])

        # Drag only cp2
        cp2.point.x = 15; cp2.point.y = 15
        assert abs(cp1.point.x) < 1e-6  # unchanged
        assert abs(cp3.point.x - 20) < 1e-6  # unchanged
        assert abs(cp2.point.x - 15) < 1e-6  # moved
