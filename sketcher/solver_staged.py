"""
W35 P3: Experimental Staged Solver

Multi-phase constraint solver with priority enforcement.
Addresses spring-back by solving topological constraints first.
"""

import time
import numpy as np
from typing import List, Dict, Tuple, Any

from .solver_interface import ISolverBackend, SolverProblem, SolverResult, SolverOptions
from .solver_scipy import SciPyBackendBase
from .constraints import Constraint, ConstraintType, ConstraintStatus, get_constraint_priority, ConstraintPriority


class StagedSolverBackend(ISolverBackend):
    """
    W35 P3: Staged solver with priority-based phases.
    
    Algorithm:
    Phase 1: CRITICAL constraints (FIXED, COINCIDENT)
             - Must be satisfied exactly
             - Solved first to establish topology
    
    Phase 2: HIGH constraints (PARALLEL, PERPENDICULAR, TANGENT, CONCENTRIC)
             - Geometric relationships
             - Solved with strong weighting
    
    Phase 3: DIMENSION constraints (LENGTH, DISTANCE, RADIUS, ANGLE)
             - Measurements
             - Solved with weak weighting (flexible)
    
    Benefits:
    - Deterministic (same input → same output)
    - Priority enforcement
    - Spring-back prevention (topology fixed first)
    - Better diagnostics (know which phase failed)
    """
    
    @property
    def name(self) -> str:
        return "staged"
    
    def can_solve(self, problem: SolverProblem) -> Tuple[bool, str]:
        """Can solve any problem that SciPy can solve"""
        try:
            from scipy.optimize import least_squares
            return True, ""
        except ImportError:
            return False, "SciPy not available"
    
    def _group_constraints_by_priority(self, constraints: List[Constraint]) -> Dict[str, List[Constraint]]:
        """Groups constraints by priority level"""
        groups = {
            'critical': [],  # FIXED, COINCIDENT
            'high': [],      # TANGENT, PARALLEL, PERPENDICULAR, etc.
            'medium': [],    # HORIZONTAL, VERTICAL
            'low': [],       # LENGTH, DISTANCE, RADIUS, etc.
        }
        
        for c in constraints:
            if not getattr(c, 'enabled', True) or not c.is_valid():
                continue
            
            priority = get_constraint_priority(c.type)
            
            if priority == ConstraintPriority.CRITICAL:
                groups['critical'].append(c)
            elif priority == ConstraintPriority.HIGH:
                groups['high'].append(c)
            elif priority == ConstraintPriority.MEDIUM:
                groups['medium'].append(c)
            else:  # LOW or REFERENCE
                groups['low'].append(c)
        
        return groups
    
    def _solve_phase(self, problem: SolverProblem, phase_constraints: List[Constraint],
                     phase_name: str, fixed_values: Dict[Any, float] = None,
                     weight_multiplier: float = 1.0) -> SolverResult:
        """
        Solves a single phase with given constraints.
        
        Args:
            problem: The full problem (for geometry access)
            phase_constraints: Constraints to solve in this phase
            phase_name: Name for diagnostics
            fixed_values: Values from previous phases to keep fixed
            weight_multiplier: Additional weight for this phase
        
        Returns:
            SolverResult
        """
        if not phase_constraints:
            return SolverResult(
                success=True,
                iterations=0,
                final_error=0.0,
                status=ConstraintStatus.FULLY_CONSTRAINED,
                message=f"Phase {phase_name}: No constraints",
                backend_used=self.name
            )
        
        # Create a modified problem with only phase constraints
        phase_problem = SolverProblem(
            points=problem.points,
            lines=problem.lines,
            circles=problem.circles,
            arcs=problem.arcs,
            constraints=phase_constraints,
            options=problem.options,
            # W35: Spline Control Points durchreichen
            spline_control_points=getattr(problem, 'spline_control_points', [])
        )
        
        # Adjust regularization based on phase
        # Phase 1 (critical): Very strong regularization to stay close to start
        # Phase 3 (dimensions): Weak regularization to allow adjustment
        if phase_name == "critical":
            phase_problem.options.regularization = 0.1  # Strong
        elif phase_name == "high":
            phase_problem.options.regularization = 0.01  # Medium
        else:  # dimensions
            phase_problem.options.regularization = 0.001  # Weak (allows spring-back prevention)
        
        # Use SciPy LM backend for each phase
        from .solver_scipy import SciPyLMBackend
        backend = SciPyLMBackend()
        
        # Temporarily adjust constraint weights
        original_weights = {}
        for c in phase_constraints:
            original_weights[id(c)] = getattr(c, '_weight_override', None)
            # Apply phase-specific weight multiplier
            if not hasattr(c, '_original_weight'):
                c._original_weight = c.get_weight()
            c._weight_override = c._original_weight * weight_multiplier
        
        try:
            result = backend.solve(phase_problem)
            result.message = f"[Phase {phase_name}] {result.message}"
            return result
        finally:
            # Restore original weights
            for c in phase_constraints:
                if id(c) in original_weights:
                    c._weight_override = original_weights[id(c)]
    
    def _save_geometry_state(self, problem: SolverProblem) -> Dict:
        """Saves current geometry state for potential rollback"""
        state = {}

        for p in problem.points:
            state[id(p)] = (p.x, p.y)

        for line in problem.lines:
            state[id(line.start)] = (line.start.x, line.start.y)
            state[id(line.end)] = (line.end.x, line.end.y)

        for circle in problem.circles:
            state[id(circle.center)] = (circle.center.x, circle.center.y)
            state[id(circle)] = circle.radius

        for arc in problem.arcs:
            state[id(arc.center)] = (arc.center.x, arc.center.y)
            state[id(arc)] = (arc.radius, arc.start_angle, arc.end_angle)

        # W35: Spline Control Points für State-Save
        spline_control_points = getattr(problem, 'spline_control_points', [])
        for p in spline_control_points:
            state[id(p)] = (p.x, p.y)

        return state
    
    def _solve_fast_path(self, problem: SolverProblem, start_time: float) -> SolverResult:
        """
        Fast path for simple sketches (< 10 constraints).
        Uses single-pass with priority-based weighting instead of multiple phases.
        """
        from .solver_scipy import SciPyLMBackend
        
        # Save initial state
        initial_state = self._save_geometry_state(problem)
        
        try:
            # Apply priority-based weights directly
            for c in problem.constraints:
                if not getattr(c, 'enabled', True) or not c.is_valid():
                    continue
                
                if not hasattr(c, '_original_weight'):
                    c._original_weight = c.get_weight()
                
                priority = get_constraint_priority(c.type)
                # Apply weights in one go
                if priority == ConstraintPriority.CRITICAL:
                    c._weight_override = c._original_weight * 100.0
                elif priority == ConstraintPriority.HIGH:
                    c._weight_override = c._original_weight * 10.0
                elif priority == ConstraintPriority.MEDIUM:
                    c._weight_override = c._original_weight * 5.0
                else:  # LOW
                    c._weight_override = c._original_weight * 1.0
            
            # Single solve with adjusted options
            fast_options = SolverOptions(
                tolerance=problem.options.tolerance,
                max_iterations=problem.options.max_iterations,
                regularization=0.01  # Medium regularization
            )
            
            fast_problem = SolverProblem(
                points=problem.points,
                lines=problem.lines,
                circles=problem.circles,
                arcs=problem.arcs,
                constraints=problem.constraints,
                options=fast_options
            )
            
            backend = SciPyLMBackend()
            result = backend.solve(fast_problem)
            
            # Restore original weights
            for c in problem.constraints:
                if hasattr(c, '_original_weight'):
                    c._weight_override = None
            
            result.backend_used = "staged_fast"
            result.solve_time_ms = (time.perf_counter() - start_time) * 1000
            result.message = f"[Staged Fast] {result.message}"
            return result
            
        except Exception as e:
            self._restore_geometry_state(problem, initial_state)
            return SolverResult(
                success=False,
                iterations=0,
                final_error=float('inf'),
                status=ConstraintStatus.INCONSISTENT,
                message=f"Fast path failed: {e}",
                backend_used="staged_fast",
                solve_time_ms=(time.perf_counter() - start_time) * 1000
            )
    
    def _restore_geometry_state(self, problem: SolverProblem, state: Dict):
        """Restores geometry state from saved values"""
        for p in problem.points:
            if id(p) in state:
                p.x, p.y = state[id(p)]

        for line in problem.lines:
            if id(line.start) in state:
                line.start.x, line.start.y = state[id(line.start)]
            if id(line.end) in state:
                line.end.x, line.end.y = state[id(line.end)]

        for circle in problem.circles:
            if id(circle.center) in state:
                circle.center.x, circle.center.y = state[id(circle.center)]
            if id(circle) in state:
                circle.radius = state[id(circle)]

        for arc in problem.arcs:
            if id(arc.center) in state:
                arc.center.x, arc.center.y = state[id(arc.center)]
            if id(arc) in state:
                arc.radius, arc.start_angle, arc.end_angle = state[id(arc)]

        # W35: Spline Control Points für State-Restore
        spline_control_points = getattr(problem, 'spline_control_points', [])
        for p in spline_control_points:
            if id(p) in state:
                p.x, p.y = state[id(p)]
    
    def solve(self, problem: SolverProblem) -> SolverResult:
        """
        Multi-phase staged solve.
        
        W35 Optimization:
        - Fast path: For simple sketches (< 10 constraints), use single pass
        - Full staged: For complex sketches, use 4 phases
        
        Strategy:
        1. Save initial state
        2. Solve CRITICAL (topology) - weight 100x
        3. If success, solve HIGH (geometry) - weight 10x
        4. If success, solve DIMENSIONS (measurements) - weight 1x
        5. If any phase fails, restore to last good state
        """
        start_time = time.perf_counter()
        
        # OPTIMIZATION: Fast path for simple sketches
        n_constraints = len([c for c in problem.constraints 
                            if getattr(c, 'enabled', True) and c.is_valid()])
        
        if n_constraints < 10:
            # Use single-pass with strong regularization for simple cases
            return self._solve_fast_path(problem, start_time)
        
        # Group constraints by priority
        groups = self._group_constraints_by_priority(problem.constraints)
        
        # Save initial state for rollback
        initial_state = self._save_geometry_state(problem)
        
        # Track phase results
        phase_results = []
        
        # Phase 1: CRITICAL (topology)
        if groups['critical']:
            result1 = self._solve_phase(
                problem, groups['critical'], "critical",
                weight_multiplier=100.0
            )
            phase_results.append(result1)
            
            if not result1.success:
                self._restore_geometry_state(problem, initial_state)
                return SolverResult(
                    success=False,
                    iterations=result1.iterations,
                    final_error=result1.final_error,
                    status=ConstraintStatus.INCONSISTENT,
                    message=f"Phase 1 (CRITICAL) failed: {result1.message}",
                    backend_used=self.name,
                    solve_time_ms=(time.perf_counter() - start_time) * 1000
                )
        
        # Phase 2: HIGH (geometric relationships)
        if groups['high']:
            result2 = self._solve_phase(
                problem, groups['high'], "high",
                weight_multiplier=10.0
            )
            phase_results.append(result2)
            
            if not result2.success:
                # Restore to after phase 1 if it existed
                self._restore_geometry_state(problem, initial_state)
                return SolverResult(
                    success=False,
                    iterations=sum(r.iterations for r in phase_results),
                    final_error=result2.final_error,
                    status=ConstraintStatus.INCONSISTENT,
                    message=f"Phase 2 (HIGH) failed: {result2.message}",
                    backend_used=self.name,
                    solve_time_ms=(time.perf_counter() - start_time) * 1000
                )
        
        # Phase 3: MEDIUM (orientation)
        if groups['medium']:
            result3 = self._solve_phase(
                problem, groups['medium'], "medium",
                weight_multiplier=5.0
            )
            phase_results.append(result3)
            
            if not result3.success:
                self._restore_geometry_state(problem, initial_state)
                return SolverResult(
                    success=False,
                    iterations=sum(r.iterations for r in phase_results),
                    final_error=result3.final_error,
                    status=ConstraintStatus.INCONSISTENT,
                    message=f"Phase 3 (MEDIUM) failed: {result3.message}",
                    backend_used=self.name,
                    solve_time_ms=(time.perf_counter() - start_time) * 1000
                )
        
        # Phase 4: LOW (dimensions) - most flexible
        if groups['low']:
            result4 = self._solve_phase(
                problem, groups['low'], "dimensions",
                weight_multiplier=1.0
            )
            phase_results.append(result4)
            
            if not result4.success:
                self._restore_geometry_state(problem, initial_state)
                return SolverResult(
                    success=False,
                    iterations=sum(r.iterations for r in phase_results),
                    final_error=result4.final_error,
                    status=ConstraintStatus.INCONSISTENT,
                    message=f"Phase 4 (DIMENSIONS) failed: {result4.message}",
                    backend_used=self.name,
                    solve_time_ms=(time.perf_counter() - start_time) * 1000
                )
        
        # All phases successful
        total_iterations = sum(r.iterations for r in phase_results)
        final_error = phase_results[-1].final_error if phase_results else 0.0
        
        # Determine final status
        n_constraints = len(problem.constraints)
        # Rough estimate of variables
        n_vars = len(problem.points) * 2 + len(problem.circles) * 3 + len(problem.arcs) * 4
        
        if n_constraints >= n_vars:
            status = ConstraintStatus.FULLY_CONSTRAINED
        else:
            status = ConstraintStatus.UNDER_CONSTRAINED
        
        return SolverResult(
            success=True,
            iterations=total_iterations,
            final_error=final_error,
            status=status,
            message=f"Staged solve successful: {len(phase_results)} phases",
            backend_used=self.name,
            solve_time_ms=(time.perf_counter() - start_time) * 1000,
            n_variables=n_vars,
            n_constraints=n_constraints
        )
