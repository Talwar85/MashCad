"""
Incremental Constraint Solver Backend

W35 P4: Incremental solver for smooth dragging performance.

Solves only the affected constraint subset instead of the full system,
enabling 60 FPS during direct edit operations.
"""

import time
import numpy as np
from typing import List, Tuple, Dict, Any
from loguru import logger

try:
    from scipy.optimize import least_squares
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from .solver_interface import ISolverBackend, SolverProblem, SolverResult, SolverOptions
from .solver_scipy import SciPyBackendBase
from .constraints import Constraint, ConstraintStatus, calculate_constraint_errors_batch
from .dependency_graph import IncrementalSolverContext


class IncrementalSolverBackend(ISolverBackend):
    """
    Incremental solver backend for dragging operations.

    Strategy:
    1. Build dependency graph
    2. Identify affected constraints when entity is dragged
    3. Solve only the subset with warm start from previous frame
    4. Use looser tolerance during drag, final precision on release

    Benefits:
    - 10-30x faster during drag (5-20ms vs 100-500ms)
    - Smooth 60 FPS interaction
    - Warm start convergence in 2-5 iterations
    """

    def __init__(self):
        self._context: IncrementalSolverContext = None
        self._full_backend = SciPyBackendBase(method='lm')  # Fallback for full solve
        self._is_dragging = False
        self._drag_entity_id = None

    @property
    def name(self) -> str:
        return "incremental"

    def can_solve(self, problem: SolverProblem) -> Tuple[bool, str]:
        """Can solve any problem SciPy can solve"""
        if not HAS_SCIPY:
            return False, "SciPy not available"
        return True, ""

    def start_drag(self, sketch, entity_id: str) -> IncrementalSolverContext:
        """
        Initialize incremental solve context for dragging.

        Args:
            sketch: The sketch being edited
            entity_id: ID of the entity being dragged

        Returns:
            IncrementalSolverContext for this drag operation
        """
        self._context = IncrementalSolverContext(sketch, entity_id)
        self._is_dragging = True
        self._drag_entity_id = self._context.dragged_entity_id

        logger.debug(f"[IncrementalSolver] Starting drag on {entity_id}")
        return self._context

    def drag_move(self, new_position: Tuple[float, float]) -> SolverResult:
        """Backward-compatible alias for solve_drag()."""
        return self.solve_drag(new_position)

    def solve_drag(self, new_position: Tuple[float, float]) -> SolverResult:
        """
        Solve during drag with incremental approach.

        Args:
            new_position: New (x, y) position of dragged entity

        Returns:
            SolverResult with solution
        """
        if self._context is None:
            return SolverResult(
                success=False,
                iterations=0,
                final_error=float('inf'),
                status=ConstraintStatus.INCONSISTENT,
                message="No active drag context (call start_drag first)",
                backend_used=self.name
            )

        start_time = time.perf_counter()

        # Update dragged entity position
        self._update_dragged_entity_position(new_position)

        # Solve only active subset
        active_constraints = self._context.get_active_constraint_objects()
        active_variables = self._context.get_active_variables_dict()
        result = self._solve_incremental(
            active_constraints,
            active_variables,
            warm_start=self._context.get_warm_start(len(active_variables)),
            tolerance=1e-3,  # Looser during drag
            max_iterations=15  # Fewer iterations during drag
        )

        # Store solution for next frame
        if result.success:
            self._context.save_solution(self._get_solution_vector())

        result.solve_time_ms = (time.perf_counter() - start_time) * 1000
        self._context.solve_count += 1
        self._context.total_time_ms += result.solve_time_ms

        return result

    def end_drag(self) -> SolverResult:
        """
        End drag operation with final precise solve.

        Args:
            sketch: The sketch being edited

        Returns:
            SolverResult with final precise solution
        """
        if self._context is None:
            return SolverResult(
                success=False,
                iterations=0,
                final_error=float('inf'),
                status=ConstraintStatus.INCONSISTENT,
                message="No active drag context",
                backend_used=self.name
            )

        logger.debug(f"[IncrementalSolver] Ending drag (solved {self._context.solve_count} times, "
                    f"avg {self._context.total_time_ms / max(1, self._context.solve_count):.2f}ms)")

        # Do final full solve with tight tolerance
        result = self._full_backend.solve(self._create_full_problem())

        # Clean up
        self._is_dragging = False
        self._drag_entity_id = None
        avg_time = self._context.total_time_ms / max(1, self._context.solve_count)
        logger.info(f"[IncrementalSolver] Drag complete: {self._context.solve_count} solves, "
                   f"avg {avg_time:.2f}ms/solve")
        self._context = None

        return result

    def solve(self, problem: SolverProblem) -> SolverResult:
        """
        Standard solve interface (non-incremental).

        For incremental dragging, use start_drag/solve_drag/end_drag instead.
        This method solves the full problem.
        """
        return self._full_backend.solve(problem)

    def _update_dragged_entity_position(self, new_position: Tuple[float, float]) -> None:
        """Update the dragged entity to its new position"""
        if self._drag_entity_id is None or self._context is None:
            return

        # Find the entity and update its position
        sketch = self._context.sketch

        for p in sketch.points:
            if p.id == self._drag_entity_id and not p.fixed:
                p.x, p.y = new_position
                return

        # Also check lines (if dragging endpoint)
        for line in sketch.lines:
            if hasattr(line.start, 'id') and line.start.id == self._drag_entity_id:
                if not line.start.fixed:
                    line.start.x, line.start.y = new_position
                return
            if hasattr(line.end, 'id') and line.end.id == self._drag_entity_id:
                if not line.end.fixed:
                    line.end.x, line.end.y = new_position
                return

    def _solve_incremental(
        self,
        constraints: List[Constraint],
        variables: Dict[str, Tuple[Any, str]],
        warm_start: List[float],
        tolerance: float = 1e-3,
        max_iterations: int = 15
    ) -> SolverResult:
        """
        Solve subset of constraints with warm start.

        Args:
            constraints: List of active constraints
            variables: Dict mapping var_id -> (obj, attr_name)
            warm_start: Initial values from previous frame
            tolerance: Solve tolerance
            max_iterations: Max solver iterations

        Returns:
            SolverResult
        """
        if not HAS_SCIPY:
            return SolverResult(
                success=False,
                iterations=0,
                final_error=float('inf'),
                status=ConstraintStatus.INCONSISTENT,
                message="SciPy not available",
                backend_used=self.name
            )

        if not constraints:
            return SolverResult(
                success=True,
                iterations=0,
                final_error=0.0,
                status=ConstraintStatus.FULLY_CONSTRAINED,
                message="No active constraints",
                backend_used=self.name
            )

        n_vars = len(variables)
        if n_vars == 0:
            return SolverResult(
                success=True,
                iterations=0,
                final_error=0.0,
                status=ConstraintStatus.FULLY_CONSTRAINED,
                message="No variables to solve",
                backend_used=self.name
            )

        # Prepare variable list and initial values
        var_list = list(variables.items())
        x0 = np.array(warm_start if len(warm_start) == n_vars else self._extract_current_values(var_list))

        def residual_func(x):
            """Compute constraint residuals"""
            # Update geometry
            for i, (var_id, (obj, attr)) in enumerate(var_list):
                setattr(obj, attr, float(x[i]))

            # Calculate errors
            errors = calculate_constraint_errors_batch(constraints)

            # Apply weights
            residuals = []
            for c, error in zip(constraints, errors):
                safe_error = float(error)
                if not np.isfinite(safe_error):
                    safe_error = 1e6
                weight = float(c.get_weight())
                if not np.isfinite(weight) or weight <= 0:
                    weight = 1.0
                residuals.append(safe_error * weight)

            return np.array(residuals, dtype=np.float64)

        try:
            # Solve with Levenberg-Marquardt
            result = least_squares(
                residual_func,
                x0,
                method='lm',
                ftol=tolerance,
                xtol=tolerance,
                gtol=tolerance,
                max_nfev=max_iterations
            )

            # Calculate final error
            final_errors = residual_func(result.x)
            constraint_error = float(np.sum(final_errors**2))

            # Determine status
            n_effective_constraints = self._count_effective_constraints(constraints)
            dof = max(0, n_vars - n_effective_constraints)

            if result.success and constraint_error < tolerance * 10:
                if dof == 0:
                    status = ConstraintStatus.FULLY_CONSTRAINED
                    message = f"Incremental solve: {dof} DOF, error={constraint_error:.2e}"
                else:
                    status = ConstraintStatus.UNDER_CONSTRAINED
                    message = f"Incremental solve: {dof} DOF, error={constraint_error:.2e}"
                success = True
            else:
                status = ConstraintStatus.INCONSISTENT if not result.success else ConstraintStatus.UNDER_CONSTRAINED
                message = f"Incremental solve: {result.message}"
                success = result.success

            return SolverResult(
                success=success,
                iterations=int(result.nfev),
                final_error=constraint_error,
                status=status,
                message=message,
                backend_used=self.name,
                n_variables=n_vars,
                n_constraints=len(constraints),
                dof=dof
            )

        except Exception as e:
            logger.exception(f"[IncrementalSolver] Solve failed: {e}")
            return SolverResult(
                success=False,
                iterations=0,
                final_error=float('inf'),
                status=ConstraintStatus.INCONSISTENT,
                message=f"Incremental solve error: {e}",
                backend_used=self.name
            )

    def _extract_current_values(self, var_list: List[Tuple[str, Tuple[Any, str]]]) -> List[float]:
        """Extract current variable values from geometry"""
        values = []
        for var_id, (obj, attr) in var_list:
            values.append(float(getattr(obj, attr, 0.0)))
        return values

    def _get_solution_vector(self) -> List[float]:
        """Get current solution as vector"""
        if self._context is None:
            return []
        return self._extract_current_values(list(self._context.get_active_variables_dict().items()))

    def _count_effective_constraints(self, constraints: List[Constraint]) -> int:
        """Count constraints weighted by DOF consumption"""
        from .constraints import ConstraintType

        _CONSTRAINT_DOF = {
            ConstraintType.COINCIDENT: 2,
            ConstraintType.CONCENTRIC: 2,
            ConstraintType.COLLINEAR: 2,
            ConstraintType.SYMMETRIC: 2,
            ConstraintType.MIDPOINT: 2,
        }
        return sum(
            _CONSTRAINT_DOF.get(c.type, 1)
            for c in constraints
            if c.type != ConstraintType.FIXED
        )

    def _create_full_problem(self) -> SolverProblem:
        """Create a full SolverProblem from the current sketch context"""
        if self._context is None:
            return None

        sketch = self._context.sketch

        # Find which solver options to use
        options = SolverOptions(
            tolerance=1e-6,  # Tight tolerance for final solve
            max_iterations=100,
            regularization=0.01
        )

        return SolverProblem(
            points=sketch.points,
            lines=sketch.lines,
            circles=sketch.circles,
            arcs=sketch.arcs,
            constraints=sketch.constraints,
            options=options,
            spline_control_points=getattr(sketch, 'spline_control_points', [])
        )


def register_incremental_backend():
    """Register incremental solver in the backend registry"""
    from .solver_interface import SolverBackendRegistry, SolverBackendType

    backend = IncrementalSolverBackend()
    SolverBackendRegistry.register(SolverBackendType.INCREMENTAL, backend)
    logger.info("[Solver] Incremental backend registered")

    return backend
