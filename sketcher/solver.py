"""
LiteCAD Sketcher - Constraint Solver
Numerischer Solver für geometrische Constraints mit SciPy least_squares

W35 P2: Dieses Modul enthält jetzt die Unified-Solver-Architektur.
Für Rückwärtskompatibilität ist ConstraintSolver ein Alias für
UnifiedConstraintSolver mit SciPy LM Backend.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import inspect
import numpy as np

from .geometry import Point2D, Line2D, Circle2D, Arc2D

try:
    from scipy.optimize import least_squares
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from .constraints import (
    Constraint, ConstraintType, ConstraintStatus,
    calculate_constraint_errors_batch
)

# W35 P2: Import neue Solver-Architektur
from .solver_interface import (
    ISolverBackend, SolverProblem, SolverOptions,
    SolverBackendType, SolverBackendRegistry
)


@dataclass
class SolverResult:
    """Ergebnis des Constraint-Solvers (W35: Erweitert um backend_used)"""
    success: bool
    iterations: int
    final_error: float
    status: ConstraintStatus
    message: str = ""
    backend_used: str = ""  # W35 P2: Zusätzliches Feld


class ConstraintSolver:
    """
    Numerischer Constraint-Solver mit SciPy least_squares.

    Verwendet Levenberg-Marquardt mit Regularisierung, um das Problem
    "mehr Residuen als Variablen" zu lösen.
    """

    def __init__(self, regularization: float = None):
        self.tolerance = 1e-6
        # W35 P1: Controllable regularization via parameter or feature flag
        if regularization is not None:
            self.regularization = regularization
        else:
            # Try to get from feature flags
            try:
                from config.feature_flags import is_enabled
                import os
                env_reg = os.environ.get('SOLVER_REGULARIZATION')
                if env_reg:
                    self.regularization = float(env_reg)
                else:
                    self.regularization = 0.01  # Default
            except Exception:
                self.regularization = 0.01  # Dämpfungsfaktor für Regularisierung
        
        self.progress_callback = None  # Callback für Live-Updates
        self.callback_interval = 10    # Alle N Iterationen

    def _validate_pre_solve(self, lines, constraints) -> Tuple[bool, List[str]]:
        """
        W35 P1: Pre-solve validation to detect contradictory constraints early.
        
        Returns:
            (is_valid, list_of_issues)
        """
        from .constraints import ConstraintType
        
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
        for c in constraints:
            if c.type == ConstraintType.COINCIDENT:
                entities = getattr(c, 'entities', [])
                if len(entities) == 2:
                    if entities[0] is entities[1]:
                        issues.append(f"Constraint {getattr(c, 'id', '?')}: COINCIDENT on same point")
        
        # Check 3: Distance constraint with negative value
        for c in constraints:
            if c.type in (ConstraintType.DISTANCE, ConstraintType.LENGTH, ConstraintType.RADIUS):
                value = getattr(c, 'value', None)
                if value is not None and value < 0:
                    issues.append(f"Constraint {getattr(c, 'id', '?')}: {c.type.name} with negative value ({value})")
        
        return len(issues) == 0, issues

    def solve(self, points, lines, circles, arcs, constraints,
              spline_control_points=None,
              progress_callback=None, callback_interval=10) -> SolverResult:
        """
        Löst das Constraint-System.

        W35 P2: Verwendet jetzt die neue Solver-Architektur mit Backend-Auswahl.
        Für Rückwärtskompatibilität wird standardmäßig SciPy LM verwendet.

        W35: Spline Control Points werden für Constraints unterstützt.

        Args:
            points: Liste aller Punkte
            lines: Liste aller Linien
            circles: Liste aller Kreise
            arcs: Liste aller Bögen
            constraints: Liste aller Constraints
            spline_control_points: Liste der Spline-Control-Punkte (optional)

        Returns:
            SolverResult mit Erfolg/Misserfolg und Details
        """
        if spline_control_points is None:
            spline_control_points = []

        # W35 P2: Versuche neues Unified Solver Interface
        try:
            # Erstelle Problem
            options = SolverOptions(
                regularization=self.regularization,
                tolerance=self.tolerance
            )

            # Lese P1 Feature-Flags
            try:
                from config.feature_flags import is_enabled
                options.pre_validation = is_enabled("solver_pre_validation")
                options.smooth_penalties = is_enabled("solver_smooth_penalties")
            except Exception:
                pass

            problem = SolverProblem(
                points=points,
                lines=lines,
                circles=circles,
                arcs=arcs,
                constraints=constraints,
                options=options,
                # W35: Spline Control Points für Constraints
                spline_control_points=spline_control_points
            )

            # Verwende neues Unified Solver
            from .solver_interface import UnifiedConstraintSolver
            unified = UnifiedConstraintSolver()
            result = unified.solve(
                points, lines, circles, arcs, constraints,
                spline_control_points=spline_control_points,
                progress_callback=progress_callback,
                callback_interval=callback_interval
            )
            
            # Konvertiere in altes SolverResult Format (ohne backend_used)
            return SolverResult(
                success=result.success,
                iterations=result.iterations,
                final_error=result.final_error,
                status=result.status,
                message=result.message,
                backend_used=result.backend_used  # W35: Neues Feld
            )
            
        except Exception as e:
            # Fallback auf direkte Implementierung wenn neues Interface fehlschlägt
            return self._solve_legacy(points, lines, circles, arcs, constraints,
                                      progress_callback, callback_interval)
    
    def _solve_legacy(self, points, lines, circles, arcs, constraints, 
                      progress_callback=None, callback_interval=10) -> SolverResult:
        """Legacy implementation als Fallback"""
        if not constraints:
            return SolverResult(True, 0, 0.0, ConstraintStatus.UNDER_CONSTRAINED, "Keine Constraints")

        # Nur aktive und valide Constraints für die numerische Lösung verwenden.
        active_constraints = [c for c in constraints if getattr(c, 'enabled', True) and c.is_valid()]
        invalid_enabled = [c for c in constraints if getattr(c, 'enabled', True) and not c.is_valid()]

        if invalid_enabled:
            return SolverResult(
                False,
                0,
                float('inf'),
                ConstraintStatus.INCONSISTENT,
                f"Ungültige Constraints: {len(invalid_enabled)}"
            )

        if not active_constraints:
            return SolverResult(True, 0, 0.0, ConstraintStatus.UNDER_CONSTRAINED, "Keine aktiven Constraints")

        if not HAS_SCIPY:
            return SolverResult(False, 0, 0.0, ConstraintStatus.INCONSISTENT, "SciPy nicht installiert!")
        
        # W35 P1: Pre-solve validation (if enabled via feature flag)
        try:
            from config.feature_flags import is_enabled
            pre_validation_enabled = is_enabled("solver_pre_validation")
        except Exception:
            pre_validation_enabled = False
        
        if pre_validation_enabled:
            is_valid, validation_issues = self._validate_pre_solve(lines, active_constraints)
            if not is_valid:
                return SolverResult(
                    False,
                    0,
                    float('inf'),
                    ConstraintStatus.INCONSISTENT,
                    f"Pre-validation failed: {'; '.join(validation_issues)}"
                )

        # 1. Variablen sammeln (Referenzen auf bewegliche Teile)
        refs = []  # Liste von (Objekt, AttributName)
        x0_vals = []  # Startwerte
        processed_ids = set()

        def add_point(p):
            """Fügt Punkt-Koordinaten als Variablen hinzu"""
            if p.id in processed_ids or p.fixed:
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

        # Zähle Constraints gewichtet nach DOF-Verbrauch
        # Manche Constraints binden mehr als 1 Freiheitsgrad
        _CONSTRAINT_DOF = {
            ConstraintType.COINCIDENT: 2,      # x + y
            ConstraintType.CONCENTRIC: 2,      # x + y
            ConstraintType.COLLINEAR: 2,       # parallel + punkt-auf-linie
            ConstraintType.SYMMETRIC: 2,       # mittelpunkt + senkrecht
            ConstraintType.MIDPOINT: 2,        # x + y
        }
        n_effective_constraints = sum(
            _CONSTRAINT_DOF.get(c.type, 1)
            for c in active_constraints
            if c.type != ConstraintType.FIXED
        )
        
        if not x0_vals:
            # Keine beweglichen Teile - prüfen ob Constraints erfüllt
            # Performance Optimization 2.2: Batch-Berechnung
            errors = calculate_constraint_errors_batch(active_constraints)
            total_error = sum(errors)
            if total_error < self.tolerance:
                return SolverResult(True, 0, total_error, ConstraintStatus.FULLY_CONSTRAINED, "Statisch bestimmt")
            else:
                return SolverResult(False, 0, total_error, ConstraintStatus.INCONSISTENT, "Keine Variablen, aber Fehler")

        x0 = np.array(x0_vals, dtype=np.float64)
        n_vars = len(x0)

        def restore_initial_values() -> None:
            """Stellt Geometrie auf den Solver-Eingangszustand zurück."""
            for i, (obj, attr) in enumerate(refs):
                try:
                    setattr(obj, attr, float(x0[i]))
                except Exception:
                    setattr(obj, attr, x0[i])

        if not np.all(np.isfinite(x0)):
            return SolverResult(
                False,
                0,
                float('inf'),
                ConstraintStatus.INCONSISTENT,
                "Ungültige Startwerte (NaN/Inf)"
            )
        
        # Nur als Heuristik/Status-Metadatum nutzen. Harte Abbrüche erzeugen
        # bei abhängigen Constraints unnötige False-Negatives.
        overconstrained_hint = n_effective_constraints > n_vars

        # 2. Fehlerfunktion mit Regularisierung
        def error_function(x):
            """
            Berechnet Residuen für least_squares.
            Enthält Constraint-Fehler + Regularisierung.
            """
            # A. Werte in Objekte zurückschreiben
            for i, (obj, attr) in enumerate(refs):
                setattr(obj, attr, x[i])

            # B. Constraint-Fehler berechnen (Performance Optimization 2.2: Batch-Berechnung!)
            residuals = []

            # Batch-Berechnung aller Errors (70-85% schneller!)
            errors = calculate_constraint_errors_batch(active_constraints)

            if len(errors) != len(active_constraints):
                raise ValueError("Constraint-Fehlerliste hat falsche Länge")

            # Gewichtung anwenden (basiert auf Constraint-Priorität)
            # Topologische Constraints (Müssen zuerst gelten - höchste Priorität)
            # Geometrische Constraints (Wichtig für Form)
            # Dimensions-Constraints (Können etwas flexibler sein)
            # Gewichtung basierend auf Constraint-Priorität
            for c, error in zip(active_constraints, errors):
                # Verwende Constraint's eigene Gewichtung
                safe_error = float(error)
                if not np.isfinite(safe_error):
                    safe_error = 1e6

                weight = float(c.get_weight())
                if not np.isfinite(weight) or weight <= 0.0:
                    weight = 1.0

                residuals.append(safe_error * weight)

            # C. Regularisierung: Verhindere zu starke Abweichung von Startwerten
            # Dies löst auch das Problem "mehr Residuen als Variablen" für 'lm'
            for i in range(n_vars):
                regularization_term = (x[i] - x0[i]) * self.regularization
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

        # 3. Lösen mit Levenberg-Marquardt
        self.progress_callback = progress_callback
        self.callback_interval = callback_interval
        self._iteration_count = 0
        
        try:
            # Callback für least_squares (wird pro Iteration aufgerufen)
            def iteration_callback(x):
                self._iteration_count += 1
                if self.progress_callback and self._iteration_count % self.callback_interval == 0:
                    # Werte temporär zurückschreiben für Callback
                    for i, (obj, attr) in enumerate(refs):
                        setattr(obj, attr, x[i])
                    # Fehler berechnen
                    errors = np.asarray(
                        calculate_constraint_errors_batch(active_constraints),
                        dtype=np.float64,
                    )
                    errors = np.nan_to_num(errors, nan=1e6, posinf=1e6, neginf=1e6)
                    total_error = float(errors.sum())
                    # Callback aufrufen
                    self.progress_callback(self._iteration_count, total_error)
            
            lsq_kwargs = dict(
                method='lm',  # Levenberg-Marquardt
                ftol=1e-8,
                xtol=1e-8,
                gtol=1e-8,
                max_nfev=1000,
            )
            if progress_callback:
                try:
                    if 'callback' in inspect.signature(least_squares).parameters:
                        lsq_kwargs['callback'] = iteration_callback
                except Exception:
                    # Ältere SciPy-Version ohne Signature/Callback-Support.
                    pass

            result = least_squares(
                error_function,
                x0,
                **lsq_kwargs,
            )

            if not np.all(np.isfinite(result.x)):
                restore_initial_values()
                return SolverResult(
                    False,
                    int(result.nfev),
                    float('inf'),
                    ConstraintStatus.INCONSISTENT,
                    "Solver lieferte ungültige Werte (NaN/Inf)"
                )

            # Finale Werte übernehmen
            for i, (obj, attr) in enumerate(refs):
                # .item() konvertiert numpy.float64 -> float
                val = result.x[i].item()
                setattr(obj, attr, val)

            # Erfolg prüfen mit verbesserten Konvergenzkriterien
            # Performance Optimization 2.2: Batch-Berechnung
            final_errors = np.asarray(
                calculate_constraint_errors_batch(active_constraints),
                dtype=np.float64,
            )
            if final_errors.size != len(active_constraints):
                restore_initial_values()
                return SolverResult(
                    False,
                    int(result.nfev),
                    float('inf'),
                    ConstraintStatus.INCONSISTENT,
                    "Ungültige Residuen (Längenfehler)"
                )
            if not np.all(np.isfinite(final_errors)):
                restore_initial_values()
                return SolverResult(
                    False,
                    int(result.nfev),
                    float('inf'),
                    ConstraintStatus.INCONSISTENT,
                    "Ungültige Residuen (NaN/Inf)"
                )

            constraint_error = float(final_errors.sum())
            
            # Maximaler Einzelfehler (wichtig für geometrische Genauigkeit)
            max_error = float(final_errors.max()) if final_errors.size else 0.0
            
            # Konvergenzkriterien:
            # 1. Der Solver muss konvergiert sein
            # 2. Der Gesamtfehler muss klein sein (< 1e-3)
            # 3. Der maximale Einzelfehler muss klein sein (< 1e-2)
            solver_converged = result.success
            total_error_small = constraint_error < 1e-3
            max_error_small = max_error < 1e-2
            
            # Detaillierte Status-Bestimmung
            if solver_converged and total_error_small and max_error_small:
                success = True
                # Prüfe auf vollständige Bestimmung (DOF = 0)
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
                # Solver konvergiert aber Fehler zu groß
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
                success=bool(success),           # numpy.bool_ -> bool
                iterations=int(result.nfev),     # numpy.int32 -> int
                final_error=float(constraint_error), # numpy.float64 -> float
                status=status,
                message=message
            )

        except Exception as e:
            restore_initial_values()
            return SolverResult(False, 0, 0.0, ConstraintStatus.INCONSISTENT, f"Solver-Fehler: {e}")


# === Utility-Funktionen ===

def auto_constrain_horizontal(line: Line2D, tolerance: float = 5.0) -> Optional[Constraint]:
    """Automatisch Horizontal-Constraint wenn Linie fast horizontal"""
    if abs(line.end.y - line.start.y) < tolerance:
        from .constraints import make_horizontal
        return make_horizontal(line)
    return None


def auto_constrain_vertical(line: Line2D, tolerance: float = 5.0) -> Optional[Constraint]:
    """Automatisch Vertikal-Constraint wenn Linie fast vertikal"""
    if abs(line.end.x - line.start.x) < tolerance:
        from .constraints import make_vertical
        return make_vertical(line)
    return None


def auto_constrain_coincident(points: List[Point2D], tolerance: float = 5.0) -> List[Constraint]:
    """Findet und erstellt Coincident-Constraints für nahe Punkte"""
    from .constraints import make_coincident

    constraints = []
    for i, p1 in enumerate(points):
        for p2 in points[i+1:]:
            if p1.distance_to(p2) < tolerance:
                constraints.append(make_coincident(p1, p2))
    return constraints
