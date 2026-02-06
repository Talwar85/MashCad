"""
LiteCAD Sketcher - Constraint Solver
Numerischer Solver für geometrische Constraints mit SciPy least_squares
"""

from dataclasses import dataclass
from typing import List, Optional
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


@dataclass
class SolverResult:
    """Ergebnis des Constraint-Solvers"""
    success: bool
    iterations: int
    final_error: float
    status: ConstraintStatus
    message: str = ""


class ConstraintSolver:
    """
    Numerischer Constraint-Solver mit SciPy least_squares.

    Verwendet Levenberg-Marquardt mit Regularisierung, um das Problem
    "mehr Residuen als Variablen" zu lösen.
    """

    def __init__(self):
        self.tolerance = 1e-6
        self.regularization = 0.01  # Dämpfungsfaktor für Regularisierung

    def solve(self, points, lines, circles, arcs, constraints) -> SolverResult:
        """
        Löst das Constraint-System.

        Args:
            points: Liste aller Punkte
            lines: Liste aller Linien
            circles: Liste aller Kreise
            arcs: Liste aller Bögen
            constraints: Liste aller Constraints

        Returns:
            SolverResult mit Erfolg/Misserfolg und Details
        """
        if not constraints:
            return SolverResult(True, 0, 0.0, ConstraintStatus.UNDER_CONSTRAINED, "Keine Constraints")

        if not HAS_SCIPY:
            return SolverResult(False, 0, 0.0, ConstraintStatus.INCONSISTENT, "SciPy nicht installiert!")

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

        # Zähle Constraints (FIXED zählt nicht als "echter" Constraint)
        n_effective_constraints = len([c for c in constraints 
                                       if c.type != ConstraintType.FIXED])
        
        if not x0_vals:
            # Keine beweglichen Teile - prüfen ob Constraints erfüllt
            # Performance Optimization 2.2: Batch-Berechnung
            errors = calculate_constraint_errors_batch(constraints)
            total_error = sum(errors)
            if total_error < self.tolerance:
                return SolverResult(True, 0, total_error, ConstraintStatus.FULLY_CONSTRAINED, "Statisch bestimmt")
            else:
                return SolverResult(False, 0, total_error, ConstraintStatus.INCONSISTENT, "Keine Variablen, aber Fehler")

        x0 = np.array(x0_vals, dtype=np.float64)
        n_vars = len(x0)
        
        # === OVER_CONSTRAINED Check ===
        if n_effective_constraints > n_vars:
            return SolverResult(
                success=False,
                iterations=0,
                final_error=float('inf'),
                status=ConstraintStatus.OVER_CONSTRAINED,
                message=f"Überbestimmt: {n_effective_constraints} Constraints > {n_vars} Variablen"
            )

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
            errors = calculate_constraint_errors_batch(constraints)

            # Gewichtung anwenden (basiert auf Constraint-Priorität)
            # Topologische Constraints (Müssen zuerst gelten - höchste Priorität)
            # Geometrische Constraints (Wichtig für Form)
            # Dimensions-Constraints (Können etwas flexibler sein)
            WEIGHTS = {
                # Topologisch - höchste Priorität
                ConstraintType.FIXED: 100.0,           # Fixierte Punkte dürfen sich nicht bewegen
                ConstraintType.COINCIDENT: 50.0,       # Punkte müssen zusammenfallen
                ConstraintType.POINT_ON_LINE: 40.0,    # Punkt muss auf Linie bleiben
                ConstraintType.POINT_ON_CIRCLE: 40.0,  # Punkt muss auf Kreis bleiben
                ConstraintType.MIDPOINT: 40.0,         # Punkt muss Mittelpunkt sein
                
                # Geometrisch - mittlere Priorität
                ConstraintType.TANGENT: 30.0,          # Tangential ist wichtig für Übergänge
                ConstraintType.PARALLEL: 25.0,         # Parallelität
                ConstraintType.PERPENDICULAR: 25.0,    # Rechtwinkligkeit
                ConstraintType.CONCENTRIC: 25.0,       # Konzentrisch
                ConstraintType.COLLINEAR: 25.0,        # Kollinear
                ConstraintType.HORIZONTAL: 20.0,       # Horizontal
                ConstraintType.VERTICAL: 20.0,         # Vertikal
                
                # Dimensions-Constraints - können etwas flexibler sein
                ConstraintType.LENGTH: 15.0,           # Länge
                ConstraintType.DISTANCE: 15.0,         # Abstand
                ConstraintType.RADIUS: 15.0,           # Radius
                ConstraintType.DIAMETER: 15.0,         # Durchmesser
                ConstraintType.ANGLE: 15.0,            # Winkel
                
                # Gleichheits-Constraints
                ConstraintType.EQUAL_LENGTH: 20.0,     # Gleiche Länge
                ConstraintType.EQUAL_RADIUS: 20.0,     # Gleicher Radius
                
                # Symmetrie
                ConstraintType.SYMMETRIC: 25.0,        # Symmetrisch
            }
            
            for c, error in zip(constraints, errors):
                weight = WEIGHTS.get(c.type, 10.0)  # Default: 10.0
                residuals.append(error * weight)

            # C. Regularisierung: Verhindere zu starke Abweichung von Startwerten
            # Dies löst auch das Problem "mehr Residuen als Variablen" für 'lm'
            for i in range(n_vars):
                regularization_term = (x[i] - x0[i]) * self.regularization
                residuals.append(regularization_term)

            return residuals

        # 3. Lösen mit Levenberg-Marquardt
        try:
            result = least_squares(
                error_function,
                x0,
                method='lm',  # Levenberg-Marquardt
                ftol=1e-8,
                xtol=1e-8,
                gtol=1e-8,
                max_nfev=1000
            )

            # Finale Werte übernehmen
            for i, (obj, attr) in enumerate(refs):
                # .item() konvertiert numpy.float64 -> float
                val = result.x[i].item()
                setattr(obj, attr, val)

            # Erfolg prüfen mit verbesserten Konvergenzkriterien
            # Performance Optimization 2.2: Batch-Berechnung
            final_errors = calculate_constraint_errors_batch(constraints)
            constraint_error = sum(final_errors)
            
            # Maximaler Einzelfehler (wichtig für geometrische Genauigkeit)
            max_error = max(final_errors) if final_errors else 0.0
            
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
                status = ConstraintStatus.INCONSISTENT
                message = f"Solver nicht konvergiert (Status: {result.status})"
            else:
                # Solver konvergiert aber Fehler zu groß
                success = False
                status = ConstraintStatus.INCONSISTENT
                if not total_error_small and not max_error_small:
                    message = f"Constraints nicht erfüllt (Gesamt: {constraint_error:.2e}, Max: {max_error:.2e})"
                elif not total_error_small:
                    message = f"Gesamtfehler zu groß ({constraint_error:.2e})"
                else:
                    message = f"Maximaler Einzelfehler zu groß ({max_error:.2e})"

            return SolverResult(
                success=bool(success),           # numpy.bool_ -> bool
                iterations=int(result.nfev),     # numpy.int32 -> int
                final_error=float(constraint_error), # numpy.float64 -> float
                status=status,
                message=message
            )

        except Exception as e:
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
