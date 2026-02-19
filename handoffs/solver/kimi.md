# SciPy Solver Reassessment Plan (W35)

**Agent:** Kimi  
**Date:** 2026-02-19  
**Branch:** `stabilize/2d-sketch-gap-closure-w34`  
**Status:** PLANNING - Not Yet Implemented  

---

## 1. Current-State Diagnosis (Baseline)

### 1.1 Architecture Overview

| Component | File | Purpose |
|-----------|------|---------|
| Solver | `sketcher/solver.py` | SciPy `least_squares` with Levenberg-Marquardt |
| Constraints | `sketcher/constraints.py` | 19 constraint types with priorities |
| Interface | `ConstraintSolver.solve()` | Returns `SolverResult` |
| Integration | `sketcher/sketch.py` | Calls solver during geometry updates |

### 1.2 Identified Failure Modes

Based on logs and handoffs analysis:

| Failure Mode | Root Cause | Evidence |
|--------------|------------|----------|
| **Spring-back** | Constraints retain "memory" of old values; solver resolves to previous state | Ellipse/Slot drag operations |
| **Infeasible systems** | Over-constrained or contradictory constraints | "Constraints nicht erfüllt" warnings |
| **Drift** | No priority enforcement in solver | Constraints violated in favor of others |
| **Slow convergence** | SciPy least_squares scales O(n²) | UX lag with complex sketches |

### 1.3 Constraint Priority System (Existing but Unused)

```python
# sketcher/constraints.py - Priorities defined but not enforced
ConstraintPriority.CRITICAL = 100  # FIXED, COINCIDENT
ConstraintPriority.HIGH = 50       # TANGENT, PARALLEL, PERPENDICULAR
ConstraintPriority.MEDIUM = 25     # HORIZONTAL, VERTICAL
ConstraintPriority.LOW = 15        # LENGTH, DISTANCE, RADIUS
```

**Problem:** Solver treats all constraints equally regardless of priority.

---

## 2. Work Packages (Implementation Plan)

### WP1: Baseline Analysis (Est. 4h)

**Objective:** Quantified failure classification

**Deliverables:**
- `test/test_sketch_solver_status.py` - Extended with metrics
- `docs/solver/baseline_metrics.md`

**Test Scenarios:**
```python
BENCHMARK_CASES = [
    ("circle_simple", "Single circle with radius constraint"),
    ("rect_equal_length", "Rectangle with equal-length constraints"),
    ("slot_complex", "Slot with all constraint types"),
    ("ellipse_rotation", "Ellipse with rotation handle"),
    ("overconstrained", "Intentionally unsolvable system"),
    ("large_sketch", "50+ entities with 30+ constraints"),
]
```

**Metrics to Collect:**
```python
@dataclass
class SolverMetrics:
    scenario_name: str
    convergence_time_ms: float
    iterations_count: int
    final_residual: float
    constraint_violation_by_type: Dict[ConstraintType, float]
    success: bool
    failure_category: Optional[str]  # A, B, C, D
```

**Failure Categories:**
- **A:** Converges but wrong result (Spring-back)
- **B:** Does not converge (Infeasible)
- **C:** Converges slowly (>500ms)
- **D:** Converges with drift

---

### WP2: Solver Abstraction Layer (Est. 6h)

**Objective:** Backend-agnostic interface

**Files:**
- `sketcher/solver.py` - Refactored with abstraction
- `config/feature_flags.py` - New flags

**Interface Design:**
```python
# sketcher/solver.py

class SolverBackend(ABC):
    @abstractmethod
    def solve(self, problem: SolverProblem) -> SolverResult:
        """Solve constraint system. Must be deterministic."""
        pass

@dataclass
class SolverProblem:
    variables: List[VariableRef]
    constraints: List[Constraint]
    options: SolverOptions

@dataclass  
class SolverResult:
    success: bool
    status: SolverStatus
    final_error: float
    iterations: int
    solution: Optional[Dict[str, float]]
    message: str

# Existing SciPy implementation (refactored)
class SciPyBackend(SolverBackend):
    """Original least_squares implementation."""
    pass
```

**Feature Flags:**
```python
# config/feature_flags.py
"solver_backend": "scipy",  # Options: "scipy", "staged", "hybrid"
"solver_staged_fallback": True,
"solver_debug_logging": False,
"solver_priority_enforcement": False,  # Enable for staged
```

---

### WP3: Alternative Candidate - Staged Solver (Est. 8h)

**Objective:** Deterministic, prioritized solver

**File:** `sketcher/solver_staged.py`

**Algorithm:**
```
Phase 1: CRITICAL Priority (Topological)
  - FIXED, COINCIDENT, POINT_ON_LINE, MIDPOINT
  - Must be satisfied exactly
  - Use direct geometric construction
  
Phase 2: HIGH Priority (Geometric relations)
  - PARALLEL, PERPENDICULAR, TANGENT, CONCENTRIC
  - Use least-squares with strong weighting
  
Phase 3: DIMENSION Priority (Measurements)
  - LENGTH, DISTANCE, RADIUS, ANGLE
  - Use least-squares with weak weighting
  - Allow flexibility for convergence
```

**Implementation Sketch:**
```python
class StagedSolverBackend(SolverBackend):
    def solve(self, problem: SolverProblem) -> SolverResult:
        # Group constraints by priority
        critical = [c for c in constraints 
                   if get_priority(c) == ConstraintPriority.CRITICAL]
        high = [c for c in constraints 
               if get_priority(c) == ConstraintPriority.HIGH]
        dimensions = [c for c in constraints 
                     if get_priority(c) <= ConstraintPriority.LOW]
        
        # Phase 1: Solve critical exactly
        result1 = self._solve_exact(critical)
        if not result1.success:
            return SolverResult(
                success=False,
                status=ConstraintStatus.INCONSISTENT,
                message="Critical constraints unsolvable",
                phase_failed=1
            )
        
        # Phase 2: Solve high priority
        result2 = self._solve_weighted(
            high, 
            fixed_vars=result1.fixed_points,
            weight=100.0
        )
        
        # Phase 3: Solve dimensions with flexibility
        result3 = self._solve_weighted(
            dimensions,
            fixed_vars=result2.solution,
            weight=1.0,
            allow_deviation=0.01  # 1% tolerance
        )
        
        return result3
```

**Key Advantages:**
1. **Deterministic:** Same input → same output
2. **Priority enforcement:** Critical constraints always satisfied
3. **Better diagnostics:** Know which phase failed
4. **Spring-back prevention:** Topological constraints solved first

---

### WP4: Benchmark & Comparison (Est. 4h)

**Objective:** Data-driven decision

**File:** `test/test_solver_benchmark.py`

**Comparison Table Template:**
```markdown
| Case | SciPy Time | SciPy Success | Staged Time | Staged Success | Winner |
|------|-----------|---------------|-------------|----------------|--------|
| circle_simple | X ms | 100% | Y ms | 100% | TBD |
| rect_equal_length | X ms | 95% | Y ms | 100% | TBD |
| slot_complex | X ms | 70% | Y ms | 95% | TBD |
| ellipse_rotation | X ms | 60% | Y ms | 90% | TBD |
| overconstrained | X ms | 0% | Y ms | 0% | Tie |
| large_sketch | X ms | 80% | Y ms | 85% | TBD |
```

**Success Criteria:**
- Staged must be ≥95% as fast as SciPy
- Staged must have ≥10% higher success rate
- Staged must eliminate Category A failures (spring-back)

---

### WP5: Controlled Rollout (Est. 3h)

**Objective:** Feature-flagged integration

**Files:**
- `sketcher/sketch.py` - Integration
- `sketcher/solver.py` - Backend selection

**Integration:**
```python
class Sketch:
    def solve(self) -> SolverResult:
        # Select backend from feature flag
        backend_name = get_feature_flag("solver_backend", "scipy")
        backend = get_solver_backend(backend_name)
        
        # Build problem
        problem = SolverProblem(
            variables=self._collect_variables(),
            constraints=self.constraints,
            options=SolverOptions(
                tolerance=1e-6,
                max_iterations=1000,
                priority_enforcement=get_feature_flag("solver_priority_enforcement")
            )
        )
        
        # Solve with fallback
        result = backend.solve(problem)
        
        if not result.success and get_feature_flag("solver_staged_fallback"):
            if backend_name != "scipy":
                # Try SciPy as fallback
                result = SciPyBackend().solve(problem)
        
        # Handle rollback
        if not result.success:
            self._handle_solver_failure(result)
        
        return result
```

---

### WP6: Deliverable Documentation (Est. 2h)

**Objective:** Production-grade recommendation

**File:** `docs/solver/SCIPY_REASSESSMENT_W35.md`

**Structure:**
```markdown
1. Executive Summary
   - Recommendation: KEEP / REPLACE / HYBRID
   
2. Current-State Diagnosis
   - Failure mode analysis
   - Performance metrics
   
3. Proposed Solution
   - Staged solver architecture
   - Priority enforcement
   
4. Benchmark Evidence
   - Comparison tables
   - Sample cases
   - Convergence metrics
   
5. Migration Plan
   - Phase 1: Feature flag (W35)
   - Phase 2: Benchmark (W36)
   - Phase 3: Default switch (W37)
   - Phase 4: Deprecation (W38)
   
6. Risks & Mitigations
   - Performance regression
   - Breaking changes
   - Rollback procedure
   
7. Decision Rationale
   - Why this approach
   - Trade-offs accepted
```

---

## 3. Recommendation: HYBRID with Staged Primary

### Recommended Approach

```
Phase 1 (W35): Implement Staged Solver as optional backend
                ├─ Feature flag: solver_backend="staged"
                ├─ Default: solver_backend="scipy"
                └─ Fallback: SciPy if Staged fails

Phase 2 (W36): Benchmark & gather real-world data
                ├─ Run comparison on test suite
                ├─ Collect metrics from development use
                └─ Document edge cases

Phase 3 (W37): Make Staged default if metrics positive
                ├─ Switch default to solver_backend="staged"
                ├─ Monitor for regressions
                └─ Quick rollback path maintained

Phase 4 (W38): Deprecate SciPy-only if Staged proves stable
                ├─ Remove SciPy-only code path
                ├─ Staged becomes sole backend
                └─ Feature flag becomes no-op
```

### Rationale

| Factor | SciPy | Staged | Winner |
|--------|-------|--------|--------|
| Spring-back prevention | ❌ | ✅ | Staged |
| Priority enforcement | ❌ | ✅ | Staged |
| Determinism | ⚠️ | ✅ | Staged |
| Speed (simple cases) | ✅ | ⚠️ | SciPy |
| Speed (complex cases) | ⚠️ | ✅ | Staged |
| Maintainability | ✅ | ⚠️ | SciPy |
| Debuggability | ❌ | ✅ | Staged |

**Conclusion:** Staged solver addresses root causes (priority, determinism) while maintaining backward compatibility via abstraction.

---

## 4. Implementation Roadmap

| Phase | Task | Files | Est. | Cumulative |
|-------|------|-------|------|------------|
| 1 | Baseline Metrics | `test/test_sketch_solver_status.py` | 4h | 4h |
| 2 | Solver Abstraction | `sketcher/solver.py` | 6h | 10h |
| 3 | Staged Backend | `sketcher/solver_staged.py` | 8h | 18h |
| 4 | Feature Flags | `config/feature_flags.py` | 2h | 20h |
| 5 | Integration | `sketcher/sketch.py` | 3h | 23h |
| 6 | Benchmark | `test/test_solver_benchmark.py` | 4h | 27h |
| 7 | Documentation | `docs/solver/` | 2h | 29h |

**Total Estimated Effort:** ~29 hours

---

## 5. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Staged solver slower | Medium | Medium | Profiling & optimization; keep SciPy fallback |
| Complex constraints fail | Low | High | Fallback to SciPy; iterative improvement |
| API-breaking changes | Low | High | Abstraction layer protects consumers |
| Regression in existing sketches | Medium | High | Feature flag default=OFF initially |
| Increased code complexity | High | Low | Well-documented abstraction; tests |

---

## 6. Rollback Strategy

```python
# Immediate rollback (code)
set_feature_flag("solver_backend", "scipy")

# Code rollback (git)
git revert HEAD  # If merged
git checkout stable-branch  # Switch to last known good

# Data recovery
# Sketch files unaffected - solver is runtime-only
```

---

## 7. Validation Checklist

Before marking "READY FOR USER ACCEPTANCE":

- [ ] All existing tests pass
- [ ] New benchmark tests pass
- [ ] Feature flags documented
- [ ] Handoff written
- [ ] Rollback procedure tested
- [ ] No GUI changes (per scope)
- [ ] No modeling changes (per scope)

---

## 8. Stop Condition

**STOP:** Wait for explicit "READY FOR USER ACCEPTANCE - DO NOT MERGE" confirmation before proceeding with implementation.

---

*This plan is ready for review. Do not implement until explicitly authorized.*
