from sketcher.constraints import Constraint, ConstraintType
import sketcher.constraints as constraints_module
import sketcher.parametric_solver as parametric_solver_module
import sketcher.solver as solver_module
import sketcher.solver_scipy as solver_scipy_module
from sketcher.sketch import ConstraintStatus, Sketch
from types import SimpleNamespace
import random


class _LegacyLikeResult:
    """Simuliert ein SolverResult ohne .status (z.B. alternative Solver-Backends)."""

    def __init__(self, success: bool, dof: int):
        self.success = success
        self.dof = dof


def test_calculate_dof_ignores_disabled_constraints():
    sketch = Sketch("dof_disabled")
    line = sketch.add_line(0.0, 0.0, 10.0, 0.0)
    horizontal = sketch.add_horizontal(line)
    assert horizontal is not None

    horizontal.enabled = False
    vars_count, constraint_count, dof = sketch.calculate_dof()

    assert constraint_count == 0
    assert dof == vars_count


def test_solver_fails_on_invalid_enabled_constraint():
    sketch = Sketch("invalid_enabled")
    sketch.add_line(0.0, 0.0, 10.0, 0.0)

    invalid = Constraint(type=ConstraintType.LENGTH, entities=[], value=10.0)
    sketch.constraints.append(invalid)

    result = sketch.solve()

    assert result.success is False
    assert result.status == ConstraintStatus.INCONSISTENT
    assert "Ungültig" in result.message


def test_solver_ignores_invalid_disabled_constraint():
    sketch = Sketch("invalid_disabled")
    sketch.add_line(0.0, 0.0, 10.0, 0.0)

    invalid = Constraint(type=ConstraintType.LENGTH, entities=[], value=10.0, enabled=False)
    sketch.constraints.append(invalid)

    result = sketch.solve()

    assert result.success is True
    assert result.status == ConstraintStatus.UNDER_CONSTRAINED


def test_get_constraint_status_supports_legacy_like_result(monkeypatch):
    sketch = Sketch("legacy_status")

    monkeypatch.setattr(sketch, "solve", lambda: _LegacyLikeResult(True, 0))
    assert sketch.get_constraint_status() == ConstraintStatus.FULLY_CONSTRAINED

    monkeypatch.setattr(sketch, "solve", lambda: _LegacyLikeResult(True, 2))
    assert sketch.get_constraint_status() == ConstraintStatus.UNDER_CONSTRAINED

    monkeypatch.setattr(sketch, "solve", lambda: _LegacyLikeResult(False, 2))
    assert sketch.get_constraint_status() == ConstraintStatus.INCONSISTENT


def test_is_fully_constrained_supports_legacy_like_result(monkeypatch):
    sketch = Sketch("legacy_fully")

    monkeypatch.setattr(sketch, "solve", lambda: _LegacyLikeResult(True, 0))
    assert sketch.is_fully_constrained() is True

    monkeypatch.setattr(sketch, "solve", lambda: _LegacyLikeResult(True, 1))
    assert sketch.is_fully_constrained() is False

    monkeypatch.setattr(sketch, "solve", lambda: _LegacyLikeResult(False, 0))
    assert sketch.is_fully_constrained() is False


def test_solve_removes_orphan_constraints_before_solving():
    sketch = Sketch("orphan_cleanup")
    line = sketch.add_line(0.0, 0.0, 10.0, 0.0)
    horizontal = sketch.add_horizontal(line)
    assert horizontal is not None
    assert len(sketch.constraints) == 1

    sketch.lines.clear()  # simuliert stale Topology-Referenz
    result = sketch.solve()

    assert result.success is True
    assert result.status == ConstraintStatus.UNDER_CONSTRAINED
    assert len(sketch.constraints) == 0


def test_delete_rectangle_cleans_corner_points():
    sketch = Sketch("rect_cleanup")
    lines = sketch.add_rectangle(0.0, 0.0, 20.0, 10.0)

    assert len(lines) == 4
    assert len(sketch.points) == 4
    assert all(not p.standalone for p in sketch.points)

    for line in lines:
        sketch.delete_line(line)

    assert len(sketch.lines) == 0
    assert len(sketch.points) == 0


def test_solver_reports_non_finite_residuals(monkeypatch):
    sketch = Sketch("nan_residuals")
    line = sketch.add_line(0.0, 0.0, 10.0, 0.0)
    sketch.add_length(line, 10.0)

    # W35: Patch both modules since solver_scipy imports the function
    monkeypatch.setattr(
        constraints_module,
        "calculate_constraint_errors_batch",
        lambda constraints: [float("nan")] * len(constraints),
    )
    # Also patch in solver_scipy since it imports the function directly
    monkeypatch.setattr(
        solver_scipy_module,
        "calculate_constraint_errors_batch",
        lambda constraints: [float("nan")] * len(constraints),
    )

    result = sketch._solver.solve(
        sketch.points,
        sketch.lines,
        sketch.circles,
        sketch.arcs,
        sketch.constraints,
    )

    assert result.success is False
    assert result.status == ConstraintStatus.INCONSISTENT
    assert "NaN/Inf" in result.message


def test_parametric_too_many_unknowns_is_reported_as_under_constrained(monkeypatch):
    class _FakeParamResult:
        success = False
        result = parametric_solver_module.SolveResult.TOO_MANY_UNKNOWNS
        dof = 3
        message = "Unterbestimmt: 3 Freiheitsgrade"

    class _FakeParamSolver:
        def __init__(self, _sketch):
            pass

        def supports_current_sketch(self):
            return True, ""

        def solve(self):
            return _FakeParamResult()

    sketch = Sketch("parametric_under")
    sketch.add_line(0.0, 0.0, 10.0, 0.0)

    monkeypatch.setattr(parametric_solver_module, "check_solvespace_available", lambda: True)
    monkeypatch.setattr(parametric_solver_module, "ParametricSolver", _FakeParamSolver)
    monkeypatch.setattr(
        sketch._solver,
        "solve",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("SciPy fallback must not run")),
    )

    result = sketch.solve()

    assert result.success is True
    assert result.status == ConstraintStatus.UNDER_CONSTRAINED
    assert "Unterbestimmt" in result.message


def test_parametric_inconsistent_is_not_silently_overridden_by_scipy(monkeypatch):
    class _FakeParamResult:
        success = False
        result = parametric_solver_module.SolveResult.INCONSISTENT
        dof = -1
        message = "Widerspruechliche Constraints"

    class _FakeParamSolver:
        def __init__(self, _sketch):
            pass

        def supports_current_sketch(self):
            return True, ""

        def solve(self):
            return _FakeParamResult()

    sketch = Sketch("parametric_inconsistent")
    sketch.add_line(0.0, 0.0, 10.0, 0.0)

    monkeypatch.setattr(parametric_solver_module, "check_solvespace_available", lambda: True)
    monkeypatch.setattr(parametric_solver_module, "ParametricSolver", _FakeParamSolver)
    monkeypatch.setattr(
        sketch._solver,
        "solve",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("SciPy fallback must not run")),
    )

    result = sketch.solve()

    assert result.success is False
    assert result.status == ConstraintStatus.OVER_CONSTRAINED
    assert "Widerspruechlich" in result.message or "Constraints" in result.message


def test_scipy_failure_reports_parametric_skip_reason(monkeypatch):
    sketch = Sketch("fallback_reason")
    sketch.add_arc(0.0, 0.0, 5.0, 0.0, 90.0)

    monkeypatch.setattr(parametric_solver_module, "check_solvespace_available", lambda: True)
    monkeypatch.setattr(
        sketch._solver,
        "solve",
        lambda *args, **kwargs: solver_module.SolverResult(
            success=False,
            iterations=3,
            final_error=1.0,
            status=ConstraintStatus.INCONSISTENT,
            message="SciPy fehlgeschlagen",
        ),
    )

    result = sketch.solve()

    assert result.success is False
    assert "SciPy fehlgeschlagen" in result.message
    assert "py-slvs übersprungen" in result.message
    assert "Arc" in result.message or "Arcs" in result.message


def test_scipy_non_convergence_restores_original_geometry(monkeypatch):
    sketch = Sketch("scipy_restore_non_converged")
    line = sketch.add_line(0.0, 0.0, 10.0, 0.0)
    sketch.add_length(line, 10.0)

    original = (line.start.x, line.start.y, line.end.x, line.end.y)

    def _fake_least_squares(fun, x0, **_kwargs):
        mutated = x0.copy()
        mutated[:] = mutated + 1.234
        fun(mutated)  # simulates internal solver iterations mutating refs
        return SimpleNamespace(x=mutated, nfev=5, success=False, status=5)

    monkeypatch.setattr(solver_scipy_module, "least_squares", _fake_least_squares)

    result = sketch._solver.solve(
        sketch.points,
        sketch.lines,
        sketch.circles,
        sketch.arcs,
        sketch.constraints,
    )

    assert result.success is False
    assert (line.start.x, line.start.y, line.end.x, line.end.y) == original


def test_scipy_exception_restores_original_geometry(monkeypatch):
    sketch = Sketch("scipy_restore_exception")
    line = sketch.add_line(0.0, 0.0, 10.0, 0.0)
    sketch.add_length(line, 10.0)

    original = (line.start.x, line.start.y, line.end.x, line.end.y)

    def _raising_least_squares(fun, x0, **_kwargs):
        mutated = x0.copy()
        mutated[0] += 42.0
        mutated[1] -= 17.0
        fun(mutated)  # simulates mutation before backend crash
        raise RuntimeError("forced backend failure")

    monkeypatch.setattr(solver_scipy_module, "least_squares", _raising_least_squares)

    result = sketch._solver.solve(
        sketch.points,
        sketch.lines,
        sketch.circles,
        sketch.arcs,
        sketch.constraints,
    )

    assert result.success is False
    assert "forced backend failure" in result.message
    assert (line.start.x, line.start.y, line.end.x, line.end.y) == original


def test_scipy_inconsistent_random_cases_do_not_drift_geometry():
    rng = random.Random(20260209)

    for idx in range(25):
        sketch = Sketch(f"scipy_restore_random_{idx}")

        x0 = rng.uniform(-120.0, 120.0)
        y0 = rng.uniform(-120.0, 120.0)
        dx = rng.uniform(15.0, 80.0) * (1.0 if rng.random() > 0.5 else -1.0)
        dy = rng.uniform(15.0, 80.0) * (1.0 if rng.random() > 0.5 else -1.0)
        line = sketch.add_line(x0, y0, x0 + dx, y0 + dy)

        original = (line.start.x, line.start.y, line.end.x, line.end.y)
        original_length = line.length

        sketch.add_fixed(line.start)
        sketch.add_length(line, original_length)
        sketch.add_horizontal(line)
        sketch.add_vertical(line)  # impossible in combination with non-zero length

        result = sketch._solver.solve(
            sketch.points,
            sketch.lines,
            sketch.circles,
            sketch.arcs,
            sketch.constraints,
        )

        assert result.success is False
        assert (line.start.x, line.start.y, line.end.x, line.end.y) == original
