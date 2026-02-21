"""
W35: Solver Baseline & Failure Classification Tests

Dieses Modul sammelt Metriken über den aktuellen SciPy-Solver
und klassifiziert Failure-Modes für die Reassessment-Entscheidung.

Pflicht-Validierung:
    conda run -n cad_env python -m pytest -q test/test_solver_baseline_w35.py
"""

import pytest
import time
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum

# Import sketcher modules
from sketcher.sketch import Sketch
from sketcher.geometry import Point2D, Line2D, Circle2D, Arc2D
from sketcher.constraints import (
    ConstraintType, ConstraintStatus,
    make_coincident, make_horizontal, make_vertical,
    make_parallel, make_perpendicular, make_equal_length,
    make_distance, make_length, make_radius, make_tangent
)
from sketcher.solver import ConstraintSolver


class FailureCategory(Enum):
    """Klassifikation von Solver-Failures"""
    A_SPRING_BACK = "spring_back"  # Converges but wrong result
    B_INFEASIBLE = "infeasible"    # Does not converge
    C_SLOW = "slow"                # Converges slowly (>500ms)
    D_DRIFT = "drift"              # Converges with drift
    E_SUCCESS = "success"          # Normal success


@dataclass
class SolverMetrics:
    """Metriken für einen Solver-Durchlauf"""
    scenario_name: str
    success: bool
    iterations: int
    final_error: float
    max_error: float
    solve_time_ms: float
    n_vars: int
    n_constraints: int
    failure_category: FailureCategory
    message: str = ""
    constraint_errors: Dict[str, float] = field(default_factory=dict)


@dataclass
class BenchmarkScenario:
    """Ein Benchmark-Szenario"""
    name: str
    description: str
    expected_status: ConstraintStatus
    setup_func: callable


# =============================================================================
# BENCHMARK SCENARIOS
# =============================================================================

def setup_simple_rectangle() -> Tuple[Sketch, dict]:
    """
    Einfaches Rechteck mit 4 Linien.
    Constraints: COINCIDENT (Ecken) + HORIZONTAL/VERTICAL
    """
    sketch = Sketch("Rect")
    
    # Punkte
    p1 = sketch.add_point(0, 0)
    p2 = sketch.add_point(100, 0)
    p3 = sketch.add_point(100, 50)
    p4 = sketch.add_point(0, 50)
    
    # Linien
    l1 = sketch.add_line_from_points(p1, p2)  # Bottom
    l2 = sketch.add_line_from_points(p2, p3)  # Right
    l3 = sketch.add_line_from_points(p3, p4)  # Top
    l4 = sketch.add_line_from_points(p4, p1)  # Left
    
    # Constraints
    sketch.constraints.append(make_coincident(l1.end, l2.start))
    sketch.constraints.append(make_coincident(l2.end, l3.start))
    sketch.constraints.append(make_coincident(l3.end, l4.start))
    sketch.constraints.append(make_coincident(l4.end, l1.start))
    
    sketch.constraints.append(make_horizontal(l1))
    sketch.constraints.append(make_horizontal(l3))
    sketch.constraints.append(make_vertical(l2))
    sketch.constraints.append(make_vertical(l4))
    
    return sketch, {"n_points": 4, "n_lines": 4, "n_constraints": 8}


def setup_rectangle_with_dimensions() -> Tuple[Sketch, dict]:
    """
    Rechteck mit exakten Maßen (LENGTH Constraints).
    """
    sketch = Sketch("RectDim")
    
    p1 = sketch.add_point(0, 0)
    p2 = sketch.add_point(100, 0)
    p3 = sketch.add_point(100, 50)
    p4 = sketch.add_point(0, 50)
    
    l1 = sketch.add_line_from_points(p1, p2)
    l2 = sketch.add_line_from_points(p2, p3)
    l3 = sketch.add_line_from_points(p3, p4)
    l4 = sketch.add_line_from_points(p4, p1)
    
    # Topologische Constraints
    sketch.constraints.append(make_coincident(l1.end, l2.start))
    sketch.constraints.append(make_coincident(l2.end, l3.start))
    sketch.constraints.append(make_coincident(l3.end, l4.start))
    sketch.constraints.append(make_coincident(l4.end, l1.start))
    
    # Geometrische Constraints
    sketch.constraints.append(make_horizontal(l1))
    sketch.constraints.append(make_horizontal(l3))
    sketch.constraints.append(make_vertical(l2))
    sketch.constraints.append(make_vertical(l4))
    
    # Dimensionen
    sketch.constraints.append(make_length(l1, 100.0))
    sketch.constraints.append(make_length(l2, 50.0))
    
    return sketch, {"n_points": 4, "n_lines": 4, "n_constraints": 10}


def setup_over_constrained() -> Tuple[Sketch, dict]:
    """
    Bewusst überconstraint: Rechteck + redundante EQUAL_LENGTH.
    """
    sketch = Sketch("OverConstrained")
    
    p1 = sketch.add_point(0, 0)
    p2 = sketch.add_point(100, 0)
    p3 = sketch.add_point(100, 50)
    p4 = sketch.add_point(0, 50)
    
    l1 = sketch.add_line_from_points(p1, p2)
    l2 = sketch.add_line_from_points(p2, p3)
    l3 = sketch.add_line_from_points(p3, p4)
    l4 = sketch.add_line_from_points(p4, p1)
    
    sketch.constraints.append(make_coincident(l1.end, l2.start))
    sketch.constraints.append(make_coincident(l2.end, l3.start))
    sketch.constraints.append(make_coincident(l3.end, l4.start))
    sketch.constraints.append(make_coincident(l4.end, l1.start))
    
    sketch.constraints.append(make_horizontal(l1))
    sketch.constraints.append(make_horizontal(l3))
    sketch.constraints.append(make_vertical(l2))
    sketch.constraints.append(make_vertical(l4))
    
    # Length constraints
    sketch.constraints.append(make_length(l1, 100.0))
    sketch.constraints.append(make_length(l2, 50.0))
    
    # Redundant: Equal length (overconstrained)
    sketch.constraints.append(make_equal_length(l1, l3))
    sketch.constraints.append(make_equal_length(l2, l4))
    
    return sketch, {"n_points": 4, "n_lines": 4, "n_constraints": 12}


def setup_contradictory_hv() -> Tuple[Sketch, dict]:
    """
    Widersprüchlich: Horizontal + Vertical + Length > 0
    """
    sketch = Sketch("Contradictory")
    
    p1 = sketch.add_point(0, 0)
    p2 = sketch.add_point(100, 0)
    
    line = sketch.add_line_from_points(p1, p2)
    
    # Widerspruch: Eine Linie kann nicht gleichzeitig
    # horizontal UND vertical sein (außer Länge = 0)
    sketch.constraints.append(make_horizontal(line))
    sketch.constraints.append(make_vertical(line))
    sketch.constraints.append(make_length(line, 50.0))
    
    return sketch, {"n_points": 2, "n_lines": 1, "n_constraints": 3}


def setup_circle_radius() -> Tuple[Sketch, dict]:
    """
    Einzelner Kreis mit Radius-Constraint.
    """
    sketch = Sketch("Circle")
    
    center = sketch.add_point(50, 50)
    circle = sketch.add_circle(50, 50, 30)
    
    sketch.constraints.append(make_radius(circle, 25.0))
    
    return sketch, {"n_points": 1, "n_circles": 1, "n_constraints": 1}


def setup_tangent_circles() -> Tuple[Sketch, dict]:
    """
    Drei Kreise tangential verbunden.
    """
    sketch = Sketch("TangentCircles")
    
    c1 = sketch.add_circle(30, 50, 20)
    c2 = sketch.add_circle(80, 50, 15)
    c3 = sketch.add_circle(55, 85, 10)
    
    # Tangential constraints - use make_tangent if available
    try:
        from sketcher.constraints import make_tangent
        sketch.constraints.append(make_tangent(c1, c2))
        sketch.constraints.append(make_tangent(c2, c3))
        sketch.constraints.append(make_tangent(c3, c1))
    except ImportError:
        # Fallback: create constraints manually with proper entities
        from sketcher.constraints import Constraint
        t1 = Constraint(ConstraintType.TANGENT, [c1, c2])
        t2 = Constraint(ConstraintType.TANGENT, [c2, c3])
        t3 = Constraint(ConstraintType.TANGENT, [c3, c1])
        sketch.constraints.append(t1)
        sketch.constraints.append(t2)
        sketch.constraints.append(t3)
    
    return sketch, {"n_circles": 3, "n_constraints": 3}


def setup_slot_like() -> Tuple[Sketch, dict]:
    """
    Slot-ähnliche Geometrie (2 parallele Linien + 2 Bögen).
    """
    sketch = Sketch("SlotLike")
    
    import math
    
    # Center line
    p1 = sketch.add_point(20, 50)
    p2 = sketch.add_point(120, 50)
    center_line = sketch.add_line_from_points(p1, p2)
    
    # Arc caps
    arc1 = sketch.add_arc(20, 50, 15, 90, 270)
    arc2 = sketch.add_arc(120, 50, 15, -90, 90)
    
    # Top/Bottom lines
    p3 = sketch.add_point(20, 65)
    p4 = sketch.add_point(120, 65)
    p5 = sketch.add_point(20, 35)
    p6 = sketch.add_point(120, 35)
    
    top_line = sketch.add_line_from_points(p3, p4)
    bottom_line = sketch.add_line_from_points(p5, p6)
    
    # Constraints
    sketch.constraints.append(make_horizontal(center_line))
    sketch.constraints.append(make_parallel(top_line, center_line))
    sketch.constraints.append(make_parallel(bottom_line, center_line))
    sketch.constraints.append(make_distance(top_line.start, p1, 15.0))
    sketch.constraints.append(make_distance(bottom_line.start, p1, 15.0))
    
    return sketch, {"n_points": 6, "n_lines": 3, "n_arcs": 2, "n_constraints": 5}


def setup_complex_mixed() -> Tuple[Sketch, dict]:
    """
    Komplexes System mit >20 Constraints.
    """
    sketch = Sketch("Complex")
    
    # Create a polygon-like shape with constraints
    n_sides = 6
    radius = 50
    points = []
    
    import math
    for i in range(n_sides):
        angle = 2 * math.pi * i / n_sides
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        points.append(sketch.add_point(x, y))
    
    lines = []
    for i in range(n_sides):
        line = sketch.add_line_from_points(points[i], points[(i+1) % n_sides])
        lines.append(line)
    
    # Coincident at corners
    for i in range(n_sides):
        sketch.constraints.append(make_coincident(lines[i].end, lines[(i+1) % n_sides].start))
    
    # Equal length for regular polygon
    for i in range(1, n_sides):
        sketch.constraints.append(make_equal_length(lines[0], lines[i]))
    
    # Fix one point
    points[0].fixed = True
    
    return sketch, {"n_points": n_sides, "n_lines": n_sides, "n_constraints": 2 * n_sides}


# =============================================================================
# BENCHMARK REGISTRY
# =============================================================================

BENCHMARK_SCENARIOS = [
    BenchmarkScenario(
        "simple_rectangle",
        "Einfaches Rechteck mit COINCIDENT + HORIZONTAL/VERTICAL",
        ConstraintStatus.FULLY_CONSTRAINED,
        setup_simple_rectangle
    ),
    BenchmarkScenario(
        "rectangle_with_dimensions",
        "Rechteck mit exakten LENGTH Constraints",
        ConstraintStatus.FULLY_CONSTRAINED,
        setup_rectangle_with_dimensions
    ),
    BenchmarkScenario(
        "over_constrained",
        "Bewusst überconstraint (redundante EQUAL_LENGTH)",
        ConstraintStatus.OVER_CONSTRAINED,
        setup_over_constrained
    ),
    BenchmarkScenario(
        "contradictory_hv",
        "Widersprüchlich: Horizontal + Vertical + Length > 0",
        ConstraintStatus.INCONSISTENT,
        setup_contradictory_hv
    ),
    BenchmarkScenario(
        "circle_radius",
        "Einzelner Kreis mit Radius-Constraint",
        ConstraintStatus.FULLY_CONSTRAINED,
        setup_circle_radius
    ),
    BenchmarkScenario(
        "tangent_circles",
        "Drei tangential verbundene Kreise",
        ConstraintStatus.FULLY_CONSTRAINED,
        setup_tangent_circles
    ),
    BenchmarkScenario(
        "slot_like",
        "Slot-ähnliche Geometrie (Linien + Bögen)",
        ConstraintStatus.FULLY_CONSTRAINED,
        setup_slot_like
    ),
    BenchmarkScenario(
        "complex_mixed",
        "Komplexes System mit >20 Constraints",
        ConstraintStatus.FULLY_CONSTRAINED,
        setup_complex_mixed
    ),
]


# =============================================================================
# METRICS COLLECTION
# =============================================================================

def run_benchmark(scenario: BenchmarkScenario, solver: ConstraintSolver = None) -> SolverMetrics:
    """
    Führt ein Benchmark-Szenario aus und sammelt Metriken.
    """
    if solver is None:
        solver = ConstraintSolver()
    
    # Setup
    sketch, metadata = scenario.setup_func()
    
    # Solve mit Zeitmessung
    start_time = time.perf_counter()
    result = solver.solve(
        sketch.points,
        sketch.lines,
        sketch.circles,
        sketch.arcs,
        sketch.constraints
    )
    solve_time = (time.perf_counter() - start_time) * 1000  # ms
    
    # Failure-Kategorie bestimmen
    category = classify_failure(result, solve_time)
    
    # Constraint-spezifische Fehler sammeln
    constraint_errors = {}
    if hasattr(sketch, 'constraints'):
        from sketcher.constraints import calculate_constraint_errors_batch
        errors = calculate_constraint_errors_batch(sketch.constraints)
        for c, e in zip(sketch.constraints, errors):
            constraint_errors[c.type.name] = float(e)
    
    return SolverMetrics(
        scenario_name=scenario.name,
        success=result.success,
        iterations=result.iterations,
        final_error=result.final_error,
        max_error=max(constraint_errors.values()) if constraint_errors else 0.0,
        solve_time_ms=solve_time,
        n_vars=metadata.get("n_points", 0) * 2 + metadata.get("n_circles", 0),
        n_constraints=metadata.get("n_constraints", 0),
        failure_category=category,
        message=result.message,
        constraint_errors=constraint_errors
    )


def classify_failure(result, solve_time_ms: float) -> FailureCategory:
    """
    Klassifiziert das Ergebnis in eine Failure-Kategorie.
    """
    if result.success:
        if solve_time_ms > 500:
            return FailureCategory.C_SLOW
        return FailureCategory.E_SUCCESS
    
    if solve_time_ms > 500:
        return FailureCategory.C_SLOW
    
    # Prüfe auf bekannte Failure-Muster
    if "nicht erfüllt" in result.message.lower() or "constraints" in result.message.lower():
        return FailureCategory.B_INFEASIBLE
    
    if "konvergiert" in result.message.lower():
        return FailureCategory.B_INFEASIBLE
    
    return FailureCategory.B_INFEASIBLE


# =============================================================================
# TESTS
# =============================================================================

class TestSolverBaseline:
    """
    Baseline-Tests für den SciPy-Solver.
    Sammelt Metriken für das W35 Reassessment.
    """
    
    @pytest.mark.parametrize("scenario", BENCHMARK_SCENARIOS, ids=lambda s: s.name)
    def test_benchmark_scenario(self, scenario: BenchmarkScenario):
        """
        Führt jedes Benchmark-Szenario aus und prüft Erfolg.
        """
        metrics = run_benchmark(scenario)
        
        # Logge Metriken für Analyse
        print(f"\n{'='*60}")
        print(f"Scenario: {metrics.scenario_name}")
        print(f"  Success: {metrics.success}")
        print(f"  Time: {metrics.solve_time_ms:.2f} ms")
        print(f"  Iterations: {metrics.iterations}")
        print(f"  Final Error: {metrics.final_error:.2e}")
        print(f"  Category: {metrics.failure_category.value}")
        print(f"  Message: {metrics.message}")
        print(f"{'='*60}")
        
        # Speichere Metriken für spätere Analyse
        self._last_metrics = metrics
        
        # Für überconstraint/widersprüchliche Systeme ist Failure OK
        if scenario.expected_status in (ConstraintStatus.OVER_CONSTRAINED, 
                                        ConstraintStatus.INCONSISTENT):
            # Wir erwarten hier keinen Erfolg
            pass
        else:
            # Für normale Systeme sollte der Solver konvergieren
            assert metrics.success, f"Solver failed: {metrics.message}"
    
    def test_performance_regression_simple(self):
        """
        Prüft, dass einfache Szenarien schnell sind (<100ms).
        """
        scenario = BenchmarkScenario(
            "perf_test", "", ConstraintStatus.FULLY_CONSTRAINED, setup_simple_rectangle
        )
        
        for _ in range(5):  # Mehrere Durchläufe
            metrics = run_benchmark(scenario)
            assert metrics.solve_time_ms < 100, \
                f"Performance regression: {metrics.solve_time_ms:.2f}ms > 100ms"
    
    def test_spring_back_detection(self):
        """
        Testet auf Spring-Back (Solver konvergiert, aber Geometrie nicht korrekt).
        """
        sketch = Sketch("SpringBackTest")
        
        # Erstelle ein System, das anfällig für Spring-Back ist
        p1 = sketch.add_point(0, 0)
        p2 = sketch.add_point(100, 0)
        line = sketch.add_line_from_points(p1, p2)
        
        sketch.constraints.append(make_horizontal(line))
        sketch.constraints.append(make_length(line, 50.0))
        
        # Ändere die Geometrie (simuliere Drag)
        p2.x = 200  # Weit weg vom Constraint
        
        solver = ConstraintSolver()
        result = solver.solve(
            sketch.points, sketch.lines, sketch.circles, sketch.arcs,
            sketch.constraints
        )
        
        if result.success:
            # Prüfe, ob das Ergebnis korrekt ist
            actual_length = line.length
            error = abs(actual_length - 50.0)
            
            if error > 1.0:  # Mehr als 1% Abweichung
                print(f"\n⚠️  SPRING-BACK DETECTED!")
                print(f"   Expected length: 50.0")
                print(f"   Actual length: {actual_length:.2f}")
                print(f"   Error: {error:.2f}")
    
    def test_collect_all_metrics(self):
        """
        Sammelt alle Metriken und erzeugt Zusammenfassung.
        """
        print("\n" + "="*80)
        print("SOLVER BASELINE METRICS SUMMARY (W35)")
        print("="*80)
        
        all_metrics = []
        for scenario in BENCHMARK_SCENARIOS:
            metrics = run_benchmark(scenario)
            all_metrics.append(metrics)
        
        # Tabelle ausgeben
        print(f"\n{'Scenario':<25} {'Success':<8} {'Time(ms)':<10} {'Iter':<6} {'Category':<15}")
        print("-"*80)
        
        for m in all_metrics:
            print(f"{m.scenario_name:<25} {str(m.success):<8} {m.solve_time_ms:<10.2f} {m.iterations:<6} {m.failure_category.value:<15}")
        
        # Zusammenfassung
        success_count = sum(1 for m in all_metrics if m.success)
        total = len(all_metrics)
        
        print(f"\nSummary:")
        print(f"  Success Rate: {success_count}/{total} ({100*success_count/total:.1f}%)")
        print(f"  Avg Time: {np.mean([m.solve_time_ms for m in all_metrics]):.2f} ms")
        print(f"  Max Time: {max([m.solve_time_ms for m in all_metrics]):.2f} ms")
        
        # Kategorie-Statistiken
        from collections import Counter
        cat_counts = Counter(m.failure_category.value for m in all_metrics)
        print(f"\nFailure Categories:")
        for cat, count in cat_counts.items():
            print(f"  {cat}: {count}")
        
        print("="*80)


# =============================================================================
# MAIN (für direkte Ausführung)
# =============================================================================

if __name__ == "__main__":
    """
    Direkte Ausführung für schnelle Metrik-Sammlung.
    """
    print("Solver Baseline Metrics Collector (W35)")
    print("="*80)
    
    test = TestSolverBaseline()
    test.test_collect_all_metrics()
