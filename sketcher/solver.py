"""
LiteCAD Sketcher - Constraint Solver
Numerischer Solver für geometrische Constraints
Verwendet Gradientenabstieg und Newton-Raphson
"""

from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Optional
import math
import numpy as np

from .geometry import Point2D, Line2D, Circle2D, Arc2D
from scipy.optimize import least_squares
from .constraints import (
    Constraint, ConstraintType, ConstraintStatus,
    calculate_constraint_error, is_constraint_satisfied
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
    Numerischer Constraint-Solver
    
    Verwendet einen iterativen Ansatz:
    1. Sammle alle variablen Punkte
    2. Berechne Fehler aller Constraints
    3. Berechne Gradienten
    4. Update Punkte
    5. Wiederhole bis konvergiert
    """
    
    def __init__(self):
        self.tolerance = 1e-6
        
    def solve(self, 
              points: List[Point2D],
              lines: List[Line2D],
              circles: List[Circle2D],
              arcs: List[Arc2D],
              constraints: List[Constraint]) -> SolverResult:
        
        if not constraints:
            return SolverResult(True, 0, 0.0, ConstraintStatus.UNDER_CONSTRAINED, "Keine Constraints")

        # 1. Identifiziere variable (nicht fixierte) Parameter
        # Wir sammeln alle x, y Koordinaten von nicht-fixierten Punkten
        # und Radien von Kreisen/Bögen in einem flachen Array 'x0'
        
        variable_refs = [] # Liste von Objekten und Attributen: (obj, 'x') oder (obj, 'y') oder (obj, 'radius')
        initial_values = []

        # Punkte sammeln (auch die von Linien etc.)
        processed_points = set()
        
        # Hilfsfunktion zum Sammeln
        def add_point_vars(p):
            if p.id in processed_points or p.fixed: return
            variable_refs.append((p, 'x'))
            initial_values.append(p.x)
            variable_refs.append((p, 'y'))
            initial_values.append(p.y)
            processed_points.add(p.id)

        # Alle Punkte durchgehen
        for p in points: add_point_vars(p)
        for l in lines: add_point_vars(l.start); add_point_vars(l.end)
        for c in circles: 
            add_point_vars(c.center)
            # Radius ist auch eine Variable!
            variable_refs.append((c, 'radius'))
            initial_values.append(c.radius)
            
        for a in arcs: add_point_vars(a.center) # Radius bei Arcs ggf. auch

        if not variable_refs:
            # Nichts zu bewegen, prüfe nur Fehler
            err = sum(calculate_constraint_error(c)**2 for c in constraints)
            return SolverResult(err < self.tolerance, 0, err, ConstraintStatus.FULLY_CONSTRAINED, "Statisch geprüft")

        x0 = np.array(initial_values)

        # 2. Definiere die Fehlerfunktion für Scipy
        # Diese Funktion schreibt die Werte aus dem Solver zurück in die Objekte
        # und berechnet dann, wie weit die Constraints verletzt sind.
        def error_function(x_new):
            # A. Werte zurückschreiben
            for i, (obj, attr) in enumerate(variable_refs):
                setattr(obj, attr, x_new[i])
            
            # B. Fehler berechnen (Residuen)
            residuals = []
            for c in constraints:
                # Gewichtung: Coincident Constraints sind wichtiger als Längen
                weight = 1.0
                if c.type == ConstraintType.COINCIDENT: weight = 10.0
                
                err = calculate_constraint_error(c)
                residuals.append(err * weight)
            return residuals

        # 3. Lösen mit Levenberg-Marquardt (oder TRF)
        try:
            res = least_squares(error_function, x0, method='trf', ftol=self.tolerance, xtol=self.tolerance, verbose=0)
            
            success = res.success and (np.mean(np.abs(res.fun)) < 1e-3)
            status = ConstraintStatus.FULLY_CONSTRAINED if success else ConstraintStatus.INCONSISTENT
            
            # Finales Zurückschreiben ist durch den letzten Aufruf von error_function implizit passiert,
            # aber sicherheitshalber schreiben wir das Ergebnis 'res.x' nochmal rein.
            for i, (obj, attr) in enumerate(variable_refs):
                setattr(obj, attr, res.x[i])
                
            return SolverResult(
                success=success,
                iterations=res.nfev,
                final_error=np.sum(np.abs(res.fun)),
                status=status,
                message=f"Scipy: {res.message}"
            )
            
        except Exception as e:
            return SolverResult(False, 0, 0.0, ConstraintStatus.INCONSISTENT, f"Solver Error: {e}")
    
    
    
    def _determine_status(self, 
                          constraints: List[Constraint],
                          variable_points: List[Point2D]) -> ConstraintStatus:
        """Bestimmt den Status des Constraint-Systems"""
        
        # Freiheitsgrade: 2 pro Punkt (x, y)
        dof = len(variable_points) * 2
        
        # Jeder Constraint reduziert Freiheitsgrade
        constraint_dof = 0
        for c in constraints:
            if c.type in [ConstraintType.HORIZONTAL, ConstraintType.VERTICAL,
                         ConstraintType.LENGTH, ConstraintType.RADIUS,
                         ConstraintType.DIAMETER]:
                constraint_dof += 1
            elif c.type in [ConstraintType.COINCIDENT, ConstraintType.DISTANCE,
                           ConstraintType.CONCENTRIC]:
                constraint_dof += 2
            elif c.type == ConstraintType.FIXED:
                constraint_dof += 2
            else:
                constraint_dof += 1
        
        if constraint_dof < dof:
            return ConstraintStatus.UNDER_CONSTRAINED
        elif constraint_dof == dof:
            return ConstraintStatus.FULLY_CONSTRAINED
        else:
            return ConstraintStatus.OVER_CONSTRAINED


# === Utility-Funktionen ===

def auto_constrain_horizontal(line: Line2D, tolerance: float = 5.0) -> Optional[Constraint]:
    """Automatisch Horizontal-Constraint wenn fast horizontal"""
    if abs(line.end.y - line.start.y) < tolerance:
        from .constraints import make_horizontal
        return make_horizontal(line)
    return None


def auto_constrain_vertical(line: Line2D, tolerance: float = 5.0) -> Optional[Constraint]:
    """Automatisch Vertikal-Constraint wenn fast vertikal"""
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
