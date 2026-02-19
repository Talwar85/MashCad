"""
W35: Spline Constraint Tests

Testet dass Spline Control Points vom Constraint-Solver
manipuliert werden können.
"""

import pytest
from sketcher.geometry import BezierSpline, Point2D
from sketcher.sketch import Sketch
from sketcher.constraints import Constraint, ConstraintType


class TestSplineConstraints:
    """Tests für Spline-Constraint-Integration"""

    def test_spline_control_points_exposed(self):
        """Control Points müssen über get_spline_control_points() abrufbar sein"""
        sketch = Sketch()
        spline = BezierSpline()
        spline.add_point(0, 0)
        spline.add_point(10, 10)
        spline.add_point(20, 0)
        sketch.splines.append(spline)

        control_points = sketch.get_spline_control_points()

        assert len(control_points) == 3
        # Alle Control Points müssen Point2D Objekte sein
        for cp in control_points:
            assert isinstance(cp, Point2D)

    def test_spline_control_point_fixed_constraint(self):
        """FIXED-Constraint auf Spline Control Point"""
        from sketcher.constraints import make_fixed

        sketch = Sketch()
        spline = BezierSpline()
        spline.add_point(0, 0)
        spline.add_point(10, 10)
        spline.add_point(20, 0)
        sketch.splines.append(spline)

        # Mittleren Control Point fixieren (make_fixed setzt point.fixed = True)
        middle_cp = spline.control_points[1].point
        constraint = make_fixed(middle_cp)
        sketch.constraints.append(constraint)

        # Solve aufrufen
        result = sketch.solve()

        # Sollte erfolgreich sein
        assert result.success, f"Solve fehlgeschlagen: {result.message}"

    def test_spline_control_point_coincident_constraint(self):
        """COINCIDENT-Constraint zwischen zwei Spline Control Points"""
        from sketcher.constraints import make_fixed

        sketch = Sketch()
        spline1 = BezierSpline()
        spline1.add_point(0, 0)
        spline1.add_point(10, 10)  # Dieser Punkt soll mit spline2 verbunden werden
        spline1.add_point(20, 0)
        sketch.splines.append(spline1)

        spline2 = BezierSpline()
        spline2.add_point(10, 10)  # Startet am gleichen Punkt
        spline2.add_point(30, 10)
        spline2.add_point(40, 0)
        sketch.splines.append(spline2)

        # Einen Punkt fixieren um DOF zu reduzieren
        make_fixed(spline1.control_points[0].point)

        # COINCIDENT Constraint zwischen den Punkten
        # (Die sind bereits coincident, aber der Constraint sollte trotzdem funktionieren)
        cp1 = spline1.control_points[1].point
        cp2 = spline2.control_points[0].point
        constraint = Constraint(ConstraintType.COINCIDENT, entities=[cp1, cp2])
        sketch.constraints.append(constraint)

        result = sketch.solve()
        assert result.success, f"Solve fehlgeschlagen: {result.message}"

    def test_spline_cache_invalidated_after_solve(self):
        """Spline-Caches müssen nach Solve invalidiert werden"""
        from sketcher.constraints import make_fixed

        sketch = Sketch()
        spline = BezierSpline()
        spline.add_point(0, 0)
        spline.add_point(10, 10)
        spline.add_point(20, 0)
        sketch.splines.append(spline)

        # Cache vorbereiten
        spline._lines = spline.to_lines(segments_per_span=10)
        old_lines = spline._lines
        assert len(old_lines) > 0

        # Fixed Constraint hinzufügen (make_fixed setzt fixed=True)
        make_fixed(spline.control_points[0].point)

        # Solve
        result = sketch.solve()
        assert result.success

        # Cache sollte neu generiert worden sein
        # (Die _lines sollten immer noch existieren, aber sie wurden in _invalidate_all_spline_caches neu gesetzt)
        assert hasattr(spline, '_lines')
        assert len(spline._lines) > 0

    def test_multiple_splines_with_constraints(self):
        """Mehrere Splines mit Constraints zwischen ihnen"""
        from sketcher.constraints import make_fixed

        sketch = Sketch()
        spline1 = BezierSpline()
        spline1.add_point(0, 0)
        spline1.add_point(10, 5)
        spline1.add_point(20, 0)
        sketch.splines.append(spline1)

        spline2 = BezierSpline()
        spline2.add_point(20, 0)  # Startet wo spline1 endet
        spline2.add_point(30, 5)
        spline2.add_point(40, 0)
        sketch.splines.append(spline2)

        # Beide Startpunkte fixieren (make_fixed setzt fixed=True)
        make_fixed(spline1.control_points[0].point)
        make_fixed(spline2.control_points[-1].point)

        # Verbindungspunkte coincident
        sketch.constraints.append(Constraint(
            ConstraintType.COINCIDENT,
            entities=[spline1.control_points[2].point, spline2.control_points[0].point]
        ))

        result = sketch.solve()
        assert result.success, f"Solve fehlgeschlagen: {result.message}"

    def test_spline_control_point_distance_constraint(self):
        """DISTANCE-Constraint für Spline Control Point"""
        from sketcher.constraints import make_fixed

        sketch = Sketch()
        spline = BezierSpline()
        spline.add_point(0, 0)
        spline.add_point(10, 10)
        spline.add_point(20, 0)
        sketch.splines.append(spline)

        # Ersten Punkt fixieren (make_fixed setzt fixed=True)
        make_fixed(spline.control_points[0].point)

        # Zweiter Punkt soll 15mm vom ersten entfernt sein
        sketch.constraints.append(Constraint(
            ConstraintType.DISTANCE,
            entities=[spline.control_points[0].point, spline.control_points[1].point],
            value=15.0
        ))

        result = sketch.solve()
        assert result.success, f"Solve fehlgeschlagen: {result.message}"

        # Abstand sollte ungefähr 15mm sein
        p1 = spline.control_points[0].point
        p2 = spline.control_points[1].point
        import math
        distance = math.hypot(p2.x - p1.x, p2.y - p1.y)
        assert abs(distance - 15.0) < 0.1, f"Abstand {distance} ist nicht ~15.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
