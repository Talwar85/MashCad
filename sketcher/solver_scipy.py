"""
W35 P2: SciPy Backend Implementations

Refactored aus dem ursprünglichen ConstraintSolver.
"""

import numpy as np
import inspect
from typing import List, Any

try:
    from scipy.optimize import least_squares
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from .solver_interface import ISolverBackend, SolverProblem, SolverResult, SolverOptions
from .constraints import Constraint, ConstraintType, ConstraintStatus, calculate_constraint_errors_batch


class SciPyBackendBase(ISolverBackend):
    """Basis-Klasse für SciPy-basierte Backends"""
    
    def __init__(self, method: str = 'lm'):
        self.method = method
        self._iteration_count = 0
        self._progress_callback = None
        self._callback_interval = 10
    
    @property
    def name(self) -> str:
        return f"scipy_{self.method}"
    
    def _validate_pre_solve(self, lines, constraints) -> tuple:
        """
        W35 P1: Pre-solve validation to detect contradictory constraints early.
        """
        issues = []
        
        # Collect constraints by type for quick lookup
        constraints_by_type = {}
        for c in constraints:
            if not getattr(c, 'enabled', True) or not c.is_valid():
                continue
            c_type = c.type
            if c_type not in constraints_by_type:
                constraints_by_type[c_type] = []
            constraints_by_type[c_type].append(c)
        
        # Check 1: Horizontal + Vertical + Non-zero length on same line
        for line in lines:
            line_constraints = []
            for c in constraints:
                if not getattr(c, 'enabled', True) or not c.is_valid():
                    continue
                if line in c.entities or line.start in c.entities or line.end in c.entities:
                    line_constraints.append(c)
            
            has_horizontal = any(c.type == ConstraintType.HORIZONTAL for c in line_constraints)
            has_vertical = any(c.type == ConstraintType.VERTICAL for c in line_constraints)
            has_nonzero_length = any(
                c.type == ConstraintType.LENGTH and getattr(c, 'value', 0) > 0.001
                for c in line_constraints
            )
            
            if has_horizontal and has_vertical and has_nonzero_length:
                issues.append(f"Line {getattr(line, 'id', '?')}: Horizontal + Vertical + Length>0 is geometrically impossible")
        
        # Check 2: Coincident constraint on same point (self-reference)
        # DISABLED: This check produces false positives for connected geometry
        # where line1.end and line2.start reference the same Point object (which is correct)
        # for c in constraints:
        #     if c.type == ConstraintType.COINCIDENT:
        #         entities = getattr(c, 'entities', [])
        #         if len(entities) == 2:
        #             if entities[0] is entities[1]:
        #                 issues.append(f"Constraint {getattr(c, 'id', '?')}: COINCIDENT on same point")
        
        # Check 3: Distance constraint with negative value
        for c in constraints:
            if c.type in (ConstraintType.DISTANCE, ConstraintType.LENGTH, ConstraintType.RADIUS):
                value = getattr(c, 'value', None)
                if value is not None and value < 0:
                    issues.append(f"Constraint {getattr(c, 'id', '?')}: {c.type.name} with negative value ({value})")
        
        return len(issues) == 0, issues
    
    def _collect_variables(self, points, lines, circles, arcs, spline_control_points=None):
        """
        Sammelt Variablen aus der Geometrie

        W35: Spline Control Points werden ebenfalls als Variablen aufgenommen.
        """
        if spline_control_points is None:
            spline_control_points = []

        refs = []  # Liste von (Objekt, AttributName)
        x0_vals = []  # Startwerte
        processed_ids = set()

        def add_point(p):
            """Fügt Punkt-Koordinaten als Variablen hinzu"""
            if p.id in processed_ids or getattr(p, 'fixed', False):
                return
            refs.append((p, 'x'))
            x0_vals.append(p.x)
            refs.append((p, 'y'))
            x0_vals.append(p.y)
            processed_ids.add(p.id)

        # Punkte aus allen Quellen sammeln
        for p in points:
            add_point(p)

        for line in lines:
            add_point(line.start)
            add_point(line.end)

        for circle in circles:
            add_point(circle.center)
            # Radius als Variable
            refs.append((circle, 'radius'))
            x0_vals.append(circle.radius)

        for arc in arcs:
            add_point(arc.center)
            # Radius und Winkel als Variablen
            refs.append((arc, 'radius'))
            x0_vals.append(arc.radius)
            refs.append((arc, 'start_angle'))
            x0_vals.append(arc.start_angle)
            refs.append((arc, 'end_angle'))
            x0_vals.append(arc.end_angle)

        # W35: Spline Control Points als Variablen aufnehmen
        for p in spline_control_points:
            add_point(p)

        return refs, x0_vals
    
    def _count_effective_constraints(self, constraints):
        """Zählt Constraints gewichtet nach DOF-Verbrauch"""
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
    
    def solve(self, problem: SolverProblem) -> SolverResult:
        """Implementierung des SciPy Solvers"""
        if not HAS_SCIPY:
            return SolverResult(
                False, 0, float('inf'),
                ConstraintStatus.INCONSISTENT,
                "SciPy nicht installiert!",
                backend_used=self.name,
                n_variables=total_n_vars,
                n_constraints=len(active_constraints),
                dof=dof_estimate,
            )

        points = problem.points
        lines = problem.lines
        circles = problem.circles
        arcs = problem.arcs
        constraints = problem.constraints
        options = problem.options
        # W35: Spline Control Points aus Problem extrahieren
        spline_control_points = getattr(problem, 'spline_control_points', [])
        refs_all, x0_all = self._collect_variables(points, lines, circles, arcs, spline_control_points)
        total_n_vars = len(x0_all)

        if not constraints:
            return SolverResult(
                True, 0, 0.0,
                ConstraintStatus.UNDER_CONSTRAINED,
                "Keine Constraints",
                backend_used=self.name,
                n_variables=total_n_vars,
                n_constraints=0,
                dof=total_n_vars,
                error_code="no_constraints",
            )

        # Nur aktive und valide Constraints
        active_constraints = [c for c in constraints if getattr(c, 'enabled', True) and c.is_valid()]
        invalid_enabled = [c for c in constraints if getattr(c, 'enabled', True) and not c.is_valid()]
        n_effective_constraints = self._count_effective_constraints(active_constraints)
        dof_estimate = max(0, total_n_vars - n_effective_constraints)

        if invalid_enabled:
            return SolverResult(
                False, 0, float('inf'),
                ConstraintStatus.INCONSISTENT,
                f"Ungültige Constraints: {len(invalid_enabled)}",
                backend_used=self.name
            )

        if not active_constraints:
            return SolverResult(
                True, 0, 0.0,
                ConstraintStatus.UNDER_CONSTRAINED,
                "Keine aktiven Constraints",
                backend_used=self.name,
                n_variables=total_n_vars,
                n_constraints=0,
                dof=total_n_vars,
                error_code="no_active_constraints",
            )

        # P1: Pre-validation
        if options.pre_validation:
            is_valid, issues = self._validate_pre_solve(lines, active_constraints)
            if not is_valid:
                return SolverResult(
                    False, 0, float('inf'),
                    ConstraintStatus.INCONSISTENT,
                    f"Pre-validation failed: {'; '.join(issues)}",
                    backend_used=self.name,
                    n_variables=total_n_vars,
                    n_constraints=len(active_constraints),
                    dof=dof_estimate,
                    error_code="pre_validation_failed",
                )

        # Variablen sammeln
        refs, x0_vals = self._collect_variables(points, lines, circles, arcs, spline_control_points)
        
        if not x0_vals:
            # Keine beweglichen Teile
            errors = calculate_constraint_errors_batch(active_constraints)
            total_error = sum(errors)
            if total_error < options.tolerance:
                return SolverResult(
                    True, 0, total_error,
                    ConstraintStatus.FULLY_CONSTRAINED,
                    "Statisch bestimmt",
                    backend_used=self.name,
                    n_variables=0,
                    n_constraints=len(active_constraints),
                    dof=0,
                    error_code="",
                )
            else:
                return SolverResult(
                    False, 0, total_error,
                    ConstraintStatus.INCONSISTENT,
                    "Keine Variablen, aber Fehler",
                    backend_used=self.name,
                    n_variables=0,
                    n_constraints=len(active_constraints),
                    dof=0,
                    error_code="inconsistent",
                )
        
        x0 = np.array(x0_vals, dtype=np.float64)
        n_vars = len(x0)
        
        def restore_initial_values():
            """Stellt Geometrie auf den Solver-Eingangszustand zurück."""
            for i, (obj, attr) in enumerate(refs):
                try:
                    setattr(obj, attr, float(x0[i]))
                except Exception:
                    setattr(obj, attr, x0[i])
        
        if not np.all(np.isfinite(x0)):
            return SolverResult(
                False, 0, float('inf'),
                ConstraintStatus.INCONSISTENT,
                "Ungültige Startwerte (NaN/Inf)",
                backend_used=self.name
            )
        
        overconstrained_hint = n_effective_constraints > n_vars
        
        # Fehlerfunktion
        def error_function(x):
            """Berechnet Residuen für least_squares."""
            # A. Werte in Objekte zurückschreiben
            for i, (obj, attr) in enumerate(refs):
                setattr(obj, attr, x[i])
            
            # B. Constraint-Fehler berechnen
            residuals = []
            errors = calculate_constraint_errors_batch(active_constraints)
            
            if len(errors) != len(active_constraints):
                raise ValueError("Constraint-Fehlerliste hat falsche Länge")
            
            # Gewichtung anwenden
            for c, error in zip(active_constraints, errors):
                safe_error = float(error)
                if not np.isfinite(safe_error):
                    safe_error = 1e6
                
                weight = float(c.get_weight())
                if not np.isfinite(weight) or weight <= 0.0:
                    weight = 1.0
                
                residuals.append(safe_error * weight)
            
            # C. Regularisierung
            for i in range(n_vars):
                regularization_term = (x[i] - x0[i]) * options.regularization
                residuals.append(regularization_term)
            
            residual_array = np.asarray(residuals, dtype=np.float64)
            if not np.all(np.isfinite(residual_array)):
                residual_array = np.nan_to_num(
                    residual_array,
                    nan=1e6,
                    posinf=1e6,
                    neginf=-1e6,
                )
            return residual_array
        
        # Lösen
        try:
            lsq_kwargs = dict(
                method=self.method,
                ftol=options.tolerance,
                xtol=options.tolerance,
                gtol=options.tolerance,
                max_nfev=options.max_iterations,
            )
            
            result = least_squares(
                error_function,
                x0,
                **lsq_kwargs
            )
            
            if not np.all(np.isfinite(result.x)):
                restore_initial_values()
                return SolverResult(
                    False,
                    int(result.nfev),
                    float('inf'),
                    ConstraintStatus.INCONSISTENT,
                    "Solver lieferte ungültige Werte (NaN/Inf)",
                    backend_used=self.name
                )
            
            # Finale Werte übernehmen
            for i, (obj, attr) in enumerate(refs):
                val = result.x[i].item()
                setattr(obj, attr, val)
            
            # Erfolg prüfen
            final_errors = np.asarray(
                calculate_constraint_errors_batch(active_constraints),
                dtype=np.float64,
            )
            
            # W35: Check for NaN/Inf in final errors
            if not np.all(np.isfinite(final_errors)):
                restore_initial_values()
                return SolverResult(
                    False,
                    int(result.nfev),
                    float('inf'),
                    ConstraintStatus.INCONSISTENT,
                    "Ungültige Residuen (NaN/Inf)",
                    backend_used=self.name
                )
            
            constraint_error = float(final_errors.sum())
            max_error = float(final_errors.max()) if final_errors.size else 0.0
            
            solver_converged = result.success
            total_error_small = constraint_error < 1e-3
            max_error_small = max_error < 1e-2
            
            if solver_converged and total_error_small and max_error_small:
                success = True
                if n_effective_constraints >= n_vars:
                    status = ConstraintStatus.FULLY_CONSTRAINED
                    message = f"Vollständig bestimmt (Fehler: {constraint_error:.2e})"
                else:
                    status = ConstraintStatus.UNDER_CONSTRAINED
                    dof = n_vars - n_effective_constraints
                    message = f"Unterbestimmt ({dof} Freiheitsgrade)"
            elif not solver_converged:
                success = False
                status = ConstraintStatus.OVER_CONSTRAINED if overconstrained_hint else ConstraintStatus.INCONSISTENT
                message = f"Solver nicht konvergiert (Status: {result.status})"
            else:
                success = False
                status = ConstraintStatus.OVER_CONSTRAINED if overconstrained_hint else ConstraintStatus.INCONSISTENT
                if not total_error_small and not max_error_small:
                    message = f"Constraints nicht erfüllt (Gesamt: {constraint_error:.2e}, Max: {max_error:.2e})"
                elif not total_error_small:
                    message = f"Gesamtfehler zu groß ({constraint_error:.2e})"
                else:
                    message = f"Maximaler Einzelfehler zu groß ({max_error:.2e})"
            
            if not success:
                restore_initial_values()
            
            return SolverResult(
                success=bool(success),
                iterations=int(result.nfev),
                final_error=float(constraint_error),
                status=status,
                message=message,
                backend_used=self.name,
                n_variables=n_vars,
                n_constraints=len(active_constraints),
                dof=max(0, n_vars - n_effective_constraints),
                error_code="" if success else ("non_converged" if not solver_converged else "inconsistent"),
            )
            
        except Exception as e:
            restore_initial_values()
            return SolverResult(
                False, 0, 0.0,
                ConstraintStatus.INCONSISTENT,
                f"Solver-Fehler: {e}",
                backend_used=self.name,
                error_code="backend_exception",
            )


class SciPyLMBackend(SciPyBackendBase):
    """SciPy Levenberg-Marquardt Backend (default)"""
    
    def __init__(self):
        super().__init__(method='lm')
    
    @property
    def name(self) -> str:
        return "scipy_lm"


class SciPyTRFBackend(SciPyBackendBase):
    """SciPy Trust Region Reflective Backend (fallback)"""
    
    def __init__(self):
        super().__init__(method='trf')
    
    @property
    def name(self) -> str:
        return "scipy_trf"
