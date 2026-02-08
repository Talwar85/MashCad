from sketcher.constraints import Constraint, ConstraintType
import sketcher.parametric_solver as parametric_solver_module
import sketcher.solver as solver_module
from sketcher.sketch import ConstraintStatus, Sketch


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


def test_solver_reports_non_finite_residuals(monkeypatch):
    sketch = Sketch("nan_residuals")
    line = sketch.add_line(0.0, 0.0, 10.0, 0.0)
    sketch.add_length(line, 10.0)

    monkeypatch.setattr(
        solver_module,
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
