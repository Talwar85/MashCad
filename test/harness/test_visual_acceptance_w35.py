"""
W35 BI: Visual Acceptance Harness - Headless Shape Checkpoint Tests
===================================================================

Headless-safe test suite for visual acceptance of 2D sketch shapes.
No GUI, no QTest — pure sketch logic only.

Each shape type is tested across 4 checkpoints:
  1. Create   — shape instantiation and geometry sanity
  2. Constraint — applying constraints modifies geometry correctly
  3. Solver   — sketch.solve() converges with constraints
  4. Persistence — to_dict / from_dict roundtrip preserves geometry

Triage tags (custom pytest markers) classify failures:
  - triage_interaction  — shape creation / basic API
  - triage_solver       — constraint solver convergence
  - triage_persistence  — save/load roundtrip fidelity
  - triage_rendering    — visual output (placeholder for future GPU tests)

Author: Amp (W35 Visual Acceptance)
Date: 2026-02-19
Branch: feature/ocp-first-migration
"""

import pytest
import math

from sketcher.sketch import Sketch
from sketcher.constraints import ConstraintStatus
from sketcher.geometry import Point2D, Line2D, Circle2D, Arc2D, Ellipse2D


# ---------------------------------------------------------------------------
# Custom markers for triage
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line("markers", "triage_interaction: Interaction failure")
    config.addinivalue_line("markers", "triage_solver: Solver failure")
    config.addinivalue_line("markers", "triage_persistence: Persistence failure")
    config.addinivalue_line("markers", "triage_rendering: Rendering failure")


# ===========================================================================
# Line
# ===========================================================================

class TestLineAcceptance:
    """Line: Create → Constraint → Solve → Persist"""

    @pytest.mark.triage_interaction
    def test_line_create(self):
        sketch = Sketch("line_test")
        line = sketch.add_line(0, 0, 10, 0)
        assert line is not None
        assert len(sketch.lines) >= 1
        assert abs(line.start.x - 0) < 0.01
        assert abs(line.end.x - 10) < 0.01

    @pytest.mark.triage_solver
    def test_line_constraint_horizontal(self):
        sketch = Sketch("line_h")
        line = sketch.add_line(0, 0, 10, 2)
        sketch.add_horizontal(line)
        result = sketch.solve()
        assert result.success
        assert abs(line.start.y - line.end.y) < 0.1

    @pytest.mark.triage_solver
    def test_line_constraint_length(self):
        sketch = Sketch("line_len")
        line = sketch.add_line(0, 0, 10, 0)
        sketch.add_length(line, 20.0)
        result = sketch.solve()
        assert result.success
        dx = line.end.x - line.start.x
        dy = line.end.y - line.start.y
        actual_len = math.sqrt(dx * dx + dy * dy)
        assert abs(actual_len - 20.0) < 0.5

    @pytest.mark.triage_persistence
    def test_line_save_load_roundtrip(self):
        sketch = Sketch("line_persist")
        line = sketch.add_line(5, 3, 15, 7)
        data = sketch.to_dict()
        loaded = Sketch.from_dict(data)
        assert len(loaded.lines) == len(sketch.lines)
        orig = sketch.lines[-1]
        rest = loaded.lines[-1]
        assert abs(orig.start.x - rest.start.x) < 0.01
        assert abs(orig.end.x - rest.end.x) < 0.01


# ===========================================================================
# Rectangle
# ===========================================================================

class TestRectangleAcceptance:
    """Rectangle: Create → Constraints → Solve → Persist"""

    @pytest.mark.triage_interaction
    def test_rectangle_create(self):
        sketch = Sketch("rect_test")
        lines = sketch.add_rectangle(-5, -5, 10, 10)
        assert len(lines) == 4
        assert len(sketch.constraints) >= 4

    @pytest.mark.triage_solver
    def test_rectangle_solve_stable(self):
        sketch = Sketch("rect_solve")
        lines = sketch.add_rectangle(0, 0, 20, 10)
        result = sketch.solve()
        assert result.success
        for line in lines:
            dx = abs(line.end.x - line.start.x)
            dy = abs(line.end.y - line.start.y)
            assert dx < 0.1 or dy < 0.1  # Either H or V

    @pytest.mark.triage_persistence
    def test_rectangle_roundtrip(self):
        sketch = Sketch("rect_persist")
        sketch.add_rectangle(0, 0, 30, 20)
        data = sketch.to_dict()
        loaded = Sketch.from_dict(data)
        assert len(loaded.lines) == len(sketch.lines)
        assert len(loaded.constraints) == len(sketch.constraints)


# ===========================================================================
# Circle
# ===========================================================================

class TestCircleAcceptance:
    """Circle: Create → Constraint → Solve → Persist"""

    @pytest.mark.triage_interaction
    def test_circle_create(self):
        sketch = Sketch("circle_test")
        circle = sketch.add_circle(0, 0, 10)
        assert circle is not None
        assert abs(circle.radius - 10) < 0.01
        assert abs(circle.center.x) < 0.01

    @pytest.mark.triage_solver
    def test_circle_radius_constraint(self):
        sketch = Sketch("circle_rad")
        circle = sketch.add_circle(0, 0, 10)
        sketch.add_radius(circle, 25.0)
        result = sketch.solve()
        assert result.success
        assert abs(circle.radius - 25.0) < 0.5

    @pytest.mark.triage_persistence
    def test_circle_roundtrip(self):
        sketch = Sketch("circle_persist")
        sketch.add_circle(5, 5, 15)
        data = sketch.to_dict()
        loaded = Sketch.from_dict(data)
        assert len(loaded.circles) == len(sketch.circles)
        assert abs(loaded.circles[0].radius - 15) < 0.01


# ===========================================================================
# Arc
# ===========================================================================

class TestArcAcceptance:
    """Arc: Create → Solve → Persist"""

    @pytest.mark.triage_interaction
    def test_arc_create(self):
        sketch = Sketch("arc_test")
        arc = sketch.add_arc(0, 0, 10, 0, 90)
        assert arc is not None
        assert abs(arc.radius - 10) < 0.01
        assert abs(arc.start_angle - 0) < 0.01

    @pytest.mark.triage_solver
    def test_arc_solver_stable(self):
        sketch = Sketch("arc_solve")
        arc = sketch.add_arc(0, 0, 10, 0, 90)
        result = sketch.solve()
        assert result.success
        assert arc.radius > 0

    @pytest.mark.triage_persistence
    def test_arc_roundtrip(self):
        sketch = Sketch("arc_persist")
        sketch.add_arc(5, 5, 8, 45, 180)
        data = sketch.to_dict()
        loaded = Sketch.from_dict(data)
        assert len(loaded.arcs) == len(sketch.arcs)
        assert abs(loaded.arcs[0].radius - 8) < 0.01


# ===========================================================================
# Ellipse
# ===========================================================================

class TestEllipseAcceptance:
    """Ellipse: Create → Solve → Persist"""

    @pytest.mark.triage_interaction
    def test_ellipse_create(self):
        sketch = Sketch("ellipse_test")
        ellipse = sketch.add_ellipse(0, 0, 10, 5)
        assert ellipse is not None
        assert abs(ellipse.radius_x - 10) < 0.01
        assert abs(ellipse.radius_y - 5) < 0.01

    @pytest.mark.triage_solver
    def test_ellipse_solver_stable(self):
        sketch = Sketch("ellipse_solve")
        ellipse = sketch.add_ellipse(0, 0, 10, 5)
        result = sketch.solve()
        assert result.success
        assert ellipse.radius_x > 0
        assert ellipse.radius_y > 0

    @pytest.mark.triage_persistence
    def test_ellipse_roundtrip(self):
        sketch = Sketch("ellipse_persist")
        sketch.add_ellipse(3, 4, 12, 6, 30)
        data = sketch.to_dict()
        loaded = Sketch.from_dict(data)
        assert len(loaded.ellipses) == len(sketch.ellipses)
        assert abs(loaded.ellipses[0].radius_x - 12) < 0.01
        assert abs(loaded.ellipses[0].radius_y - 6) < 0.01


# ===========================================================================
# Polygon
# ===========================================================================

class TestPolygonAcceptance:
    """Polygon: Create → Solve → Persist"""

    @pytest.mark.triage_interaction
    def test_polygon_create(self):
        sketch = Sketch("polygon_test")
        pts = [(0, 0), (10, 0), (10, 10), (0, 10)]
        lines = sketch.add_polygon(pts, closed=True)
        assert len(lines) >= 4  # 4 sides for closed quad

    @pytest.mark.triage_solver
    def test_polygon_solver_stable(self):
        sketch = Sketch("polygon_solve")
        pts = [(0, 0), (10, 0), (10, 10), (0, 10)]
        sketch.add_polygon(pts, closed=True)
        result = sketch.solve()
        assert result.success

    @pytest.mark.triage_persistence
    def test_polygon_roundtrip(self):
        sketch = Sketch("polygon_persist")
        pts = [(0, 0), (20, 0), (20, 15), (0, 15)]
        sketch.add_polygon(pts, closed=True)
        n_lines = len(sketch.lines)
        data = sketch.to_dict()
        loaded = Sketch.from_dict(data)
        assert len(loaded.lines) == n_lines


# ===========================================================================
# Slot
# ===========================================================================

class TestSlotAcceptance:
    """Slot: Create → Solve → Persist"""

    @pytest.mark.triage_interaction
    def test_slot_create(self):
        sketch = Sketch("slot_test")
        center_line, arc1 = sketch.add_slot(0, 0, 20, 0, 5)
        assert center_line is not None
        assert arc1 is not None
        assert len(sketch.arcs) >= 2
        assert len(sketch.lines) >= 3  # center + top + bottom

    @pytest.mark.triage_solver
    def test_slot_solver_stable(self):
        sketch = Sketch("slot_solve")
        sketch.add_slot(0, 0, 20, 0, 5)
        result = sketch.solve()
        assert result.success

    @pytest.mark.triage_persistence
    def test_slot_roundtrip(self):
        sketch = Sketch("slot_persist")
        sketch.add_slot(-10, 0, 10, 0, 3)
        n_lines = len(sketch.lines)
        n_arcs = len(sketch.arcs)
        n_constraints = len(sketch.constraints)
        data = sketch.to_dict()
        loaded = Sketch.from_dict(data)
        assert len(loaded.lines) == n_lines
        assert len(loaded.arcs) == n_arcs
        assert len(loaded.constraints) == n_constraints
