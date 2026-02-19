# W35 Plan: SciPy Solver Reassessment for 2D Sketch Constraints

**Branch:** `stabilize/2d-sketch-gap-closure-w34`
**Date:** 2026-02-19
**Status:** READY FOR REVIEW
**Handoff to:** glm47

---

## Executive Summary

This plan assesses whether SciPy `least_squares` is the right long-term solver for 2D sketch constraints in LiteCAD. After analyzing the current implementation and failure modes, the recommendation is to **keep SciPy as primary solver** with specific improvements, while **expanding py-slvs support** for supported geometries.

**Key Finding:** SciPy is adequate for most cases but needs better fallback strategies and improved diagnostic feedback.

---

## Current State Analysis

### Architecture (from `sketcher/solver.py`, `sketcher/sketch.py`, `sketcher/parametric_solver.py`)

```
┌─────────────────────────────────────────────────────────┐
│              SOLVER SELECTION FLOW                       │
├─────────────────────────────────────────────────────────┤
│ 1. Try py-slvs (ParametricSolver)                       │
│    └─ If available AND sketch supported (no arcs)       │
│ 2. Fallback to SciPy (ConstraintSolver)                 │
│    └─ least_squares(method='lm') with regularization    │
└─────────────────────────────────────────────────────────┘
```

### SciPy Solver Current Implementation

**File:** `sketcher/solver.py` (ConstraintSolver class)

| Parameter | Value | Notes |
|-----------|-------|-------|
| Method | `lm` (Levenberg-Marquardt) | Requires square Jacobian |
| Tolerance | 1e-6 | ftol, xtol, gtol |
| Regularization | 0.01 | Damping for "more residuals than variables" |
| Max Iterations | 1000 | nfev limit |
| Constraint Weights | 15-100 | Priority-based weighting |

**Key Features:**
- Batch error calculation (70-85% faster via NumPy)
- Rollback on failure (`restore_initial_values()`)
- Progress callback support for live solve
- Weighted residuals (CRITICAL > HIGH > MEDIUM > LOW)

### py-slvs Parametric Solver

**File:** `sketcher/parametric_solver.py`

| Aspect | Status |
|--------|--------|
| Lines | ✅ Supported |
| Circles | ✅ Supported |
| Arcs | ❌ Not supported (fallback to SciPy) |
| Splines | ❌ Not supported (fallback to SciPy) |
| Ellipses | ❌ Not supported (fallback to SciPy) |
| Constraint Types | 17/19 supported (COLLINEAR, SYMMETRIC missing) |

---

## Identified Failure Modes

### 1. Spring-Back (Geometrie "federt" zurück)

**Cause:** Regularization term `0.01 * (x - x0)` pulls geometry toward initial values.

**Impact:** After drag operation, geometry partially reverts.

**Current Mitigation:** None (regularization always active)

### 2. Infeasible Systems Not Detected Early

**Cause:** Solver attempts solve even when constraints are geometrically impossible (e.g., horizontal + vertical non-zero length line).

**Impact:** Wasted computation, unclear error messages.

**Current Mitigation:** Post-solve validation with generic error messages.

### 3. Drift During Iterative Solving

**Cause:** Each drag operation triggers multiple solves; errors accumulate.

**Current Mitigation:** Rollback on failure (`restore_initial_values()`).

### 4. Over-Constrained Detection Weak

**Cause:** `overconstrained_hint = n_effective_constraints > n_vars` is only used for message, not prevention.

**Impact:** Solver tries impossible systems anyway.

---

## Solver Options Comparison

| Strategy | Pros | Cons | Deterministic | CAD-Grade |
|----------|------|------|---------------|-----------|
| **SciPy LM (current)** | Mature library, good convergence | "More residuals than variables" issue, regularization causes drift | ✅ Yes | ⚠️ Medium |
| **SciPy Trust Region Reflective** | Handles over-determined well | Slower, may not converge on small residuals | ✅ Yes | ⚠️ Medium |
| **Damped Gauss-Newton (custom)** | No regularization, geometrically pure | Implementation effort, no adaptive damping | ✅ Yes | ✅ High |
| **py-slvs (SolveSpace)** | Deterministic, DOF aware, CAD-grade | Limited geometry support (no arcs/splines) | ✅ Yes | ✅ High |
| **Hybrid (py-slvs + SciPy)** | Best of both, feature-flagged | Complexity, two codebases | ✅ Yes | ✅ High |

---

## Recommended Approach: Hybrid with Improvements

### Phase 1: Solver Abstraction Layer

Create `sketcher/solver_interface.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

class SolverBackend(Enum):
    SCIPY_LM = "scipy_lm"
    SCIPY_TRF = "scipy_trf"
    PY_SLVS = "py_slvs"
    GAUSS_NEWTON = "gauss_newton"

@dataclass
class UnifiedSolverResult:
    success: bool
    backend: SolverBackend
    iterations: int
    final_error: float
    dof: int  # Degrees of Freedom (-1 = unknown)
    status: ConstraintStatus
    message: str
    failed_constraints: List[str] = field(default_factory=list)

class ISolverBackend(ABC):
    @abstractmethod
    def can_solve(self, sketch) -> Tuple[bool, str]:
        """Check if this backend supports the sketch geometry"""
        pass

    @abstractmethod
    def solve(self, sketch) -> UnifiedSolverResult:
        """Execute the solve"""
        pass
```

### Phase 2: Feature-Flagged Backend Selection

Create `config/solver_config.py`:

```python
from dataclasses import dataclass
from sketcher.solver_interface import SolverBackend

@dataclass
class SolverConfig:
    # Primary backend preference
    preferred_backend: SolverBackend = SolverBackend.PY_SLVS

    # Fallback chain
    fallback_chain: List[SolverBackend] = (
        SolverBackend.SCIPY_LM,
        SolverBackend.SCIPY_TRF,
    )

    # Solver parameters
    scipy_tolerance: float = 1e-6
    scipy_max_iterations: int = 1000
    scipy_regularization: float = 0.001  # Reduced from 0.01

    # Feature flags
    enable_gauss_newton: bool = False  # Experimental
    enable_pre_solve_validation: bool = True
```

### Phase 3: Pre-Solve Validation

Add `sketcher/solver_validator.py`:

```python
class PreSolveValidator:
    """
    Validates constraint system BEFORE attempting solve.
    Prevents wasted computation on impossible systems.
    """

    def validate(self, sketch) -> Tuple[bool, List[str]]:
        """
        Returns:
            (is_valid, list_of_issues)
        """
        issues = []

        # Check 1: Contradictory geometric constraints
        for line in sketch.lines:
            has_horizontal = any(c.type == ConstraintType.HORIZONTAL
                                 for c in self._line_constraints(line))
            has_vertical = any(c.type == ConstraintType.VERTICAL
                               for c in self._line_constraints(line))
            has_nonzero_length = any(c.type == ConstraintType.LENGTH
                                     and c.value > 0.001
                                     for c in self._line_constraints(line))

            if has_horizontal and has_vertical and has_nonzero_length:
                issues.append(f"Line {line.id}: Horizontal + Vertical + Length > 0 is impossible")

        # Check 2: Over-constrained by DOF
        n_vars, n_constraints, dof = sketch.calculate_dof()
        if n_constraints > n_vars + 2:  # +2 tolerance for coincident duplicates
            issues.append(f"Over-constrained: {n_constraints} constraints > {n_vars} variables")

        return len(issues) == 0, issues
```

### Phase 4: Improved SciPy Fallback

Modify `sketcher/solver.py`:

```python
class ImprovedConstraintSolver(ConstraintSolver):
    def __init__(self, config: SolverConfig):
        self.config = config
        self.tolerance = config.scipy_tolerance
        self.regularization = config.scipy_regularization  # 0.001 instead of 0.01

    def solve(self, points, lines, circles, arcs, constraints, **kwargs):
        # 1. Pre-validation (if enabled)
        if self.config.enable_pre_solve_validation:
            validator = PreSolveValidator()
            is_valid, issues = validator.validate_from_lists(...)
            if not is_valid:
                return SolverResult(
                    False, 0, float('inf'),
                    ConstraintStatus.OVER_CONSTRAINED,
                    "; ".join(issues)
                )

        # 2. Try primary method
        result = self._solve_scipy_lm(...)

        # 3. Fallback to TRF if LM failed with specific error
        if not result.success and result.message.startswith("lm"):
            result = self._solve_scipy_trf(...)

        return result
```

---

## Implementation Plan

### Step 1: Create Solver Interface (1 day)
- [ ] Create `sketcher/solver_interface.py`
- [ ] Define `ISolverBackend` ABC
- [ ] Define `UnifiedSolverResult`
- [ ] Define `SolverBackend` enum

### Step 2: Create Solver Configuration (0.5 day)
- [ ] Create `config/solver_config.py` (or use existing `config/feature_flag.py`)
- [ ] Add feature flags for backend selection
- [ ] Add solver parameters (tolerance, regularization, etc.)

### Step 3: Implement Pre-Solve Validator (1 day)
- [ ] Create `sketcher/solver_validator.py`
- [ ] Implement geometric contradiction detection
- [ ] Implement DOF-based over-constraint detection
- [ ] Add unit tests

### Step 4: Refactor SciPy Solver (1 day)
- [ ] Modify `ConstraintSolver` to use config
- [ ] Reduce regularization from 0.01 to 0.001
- [ ] Add TRF fallback option
- [ ] Improve error messages with validator output

### Step 5: Update Sketch Integration (0.5 day)
- [ ] Modify `sketcher/sketch.py` `solve()` method to use new interface
- [ ] Ensure py-slvs fallback chain still works
- [ ] Update `normalize_result()` for `UnifiedSolverResult`

### Step 6: Testing & Validation (1 day)
- [ ] Run existing test suite
- [ ] Add new tests for pre-solve validation
- [ ] Add tests for feature flag switching
- [ ] Manual testing with complex sketches

---

## Critical Files to Modify

| File | Changes | Lines (est.) |
|------|---------|--------------|
| `sketcher/solver_interface.py` | NEW | ~150 |
| `sketcher/solver_validator.py` | NEW | ~200 |
| `sketcher/solver.py` | Refactor + config integration | ~50 |
| `sketcher/sketch.py` | Update solve() method | ~30 |
| `config/feature_flag.py` | Add solver flags | ~20 |
| `test/test_sketch_solver_status.py` | Add validation tests | ~100 |

---

## Validation Commands

```powershell
# Compilation
conda run -n cad_env python -m py_compile sketcher/solver.py sketcher/constraints.py sketcher/sketch.py sketcher/solver_interface.py sketcher/solver_validator.py

# Existing tests
conda run -n cad_env python -m pytest -q test/test_sketch_solver_status.py

# New tests (to be created)
conda run -n cad_env python -m pytest -q test/test_solver_validation_w35.py
```

---

## Benchmark Requirements

Create `benchmarks/solver_comparison_w35.py`:

```python
"""
Benchmark: Compare solver backends on representative scenarios.
"""

SCENARIOS = [
    # Name, (n_points, n_lines, n_constraints), Expected Status
    ("simple_rectangle", (4, 4, 6), ConstraintStatus.FULLY_CONSTRAINED),
    ("over_constrained", (4, 4, 10), ConstraintStatus.OVER_CONSTRAINED),
    ("under_constrained", (4, 4, 3), ConstraintStatus.UNDER_CONSTRAINED),
    ("contradictory_hv", (2, 1, 3), ConstraintStatus.INCONSISTENT),
    ("complex_50_constraints", (20, 20, 50), ConstraintStatus.FULLY_CONSTRAINED),
]

METRICS = [
    "success_rate",
    "iterations",
    "final_error",
    "solve_time_ms",
    "rollback_rate",
]
```

**Required Output:** Table showing all metrics for each backend (SciPy-LM, SciPy-TRF, py-slvs if available).

---

## Risk Analysis

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Regression in existing sketches | Medium | High | Extensive testing, feature flag default to current behavior |
| Performance degradation | Low | Medium | Benchmark before/after, optimize hot paths |
| py-slvs installation issues | High | Low | Clear documentation, graceful fallback |

---

## Deliverable Documentation

Create `docs/solver/SCIPY_REASSESSMENT_W35.md` with:

1. **Current-State Diagnosis**
   - Failure mode classification
   - Performance metrics on representative scenarios
   - Comparison table of backends

2. **Interface and Implementation Changes**
   - `ISolverBackend` interface documentation
   - Feature flag documentation
   - Migration guide for existing code

3. **Benchmark Evidence**
   - Command lines used
   - Sample cases
   - Convergence/failure metrics
   - Decision rationale

4. **Recommendation and Migration Plan**
   - Keep SciPy as primary (with improvements)
   - Expand py-slvs support (add arc mapping)
   - Long-term: consider custom Gauss-Newton

5. **Risks and Rollback Strategy**
   - Feature flags allow instant revert
   - Old behavior always available via config

---

## Rollback Strategy

All changes are feature-flagged. To rollback:

1. Set `preferred_backend = SolverBackend.SCIPY_LM`
2. Set `scipy_regularization = 0.01` (original value)
3. Set `enable_pre_solve_validation = False`

Or simply revert to commit before W35 changes.

---

## Final Recommendation

**Keep SciPy** as the primary solver with the following improvements:

1. **Reduce regularization** from 0.01 to 0.001 (less spring-back)
2. **Add pre-solve validation** (catch impossible systems early)
3. **Add TRF fallback** (handle over-determined cases better)
4. **Feature-flag backend selection** (controlled rollout)
5. **Expand py-slvs support** for arc geometries (future work)

**NOT recommended:** Full replacement with custom solver (high risk, unclear benefit).

---

## STOP CONDITION

This plan is **READY FOR USER ACCEPTANCE**.

**DO NOT MERGE** until:
- [ ] All validation commands pass
- [ ] Manual testing confirms no regression
- [ ] User explicitly approves with `ABNAHME: OK`
