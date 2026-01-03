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
        self.max_iterations = 500
        self.tolerance = 1e-8
        self.step_size = 0.5
        self.damping = 0.9
        
    def solve(self, 
              points: List[Point2D],
              lines: List[Line2D],
              circles: List[Circle2D],
              arcs: List[Arc2D],
              constraints: List[Constraint]) -> SolverResult:
        """
        Löst das Constraint-System
        
        Args:
            points: Liste aller Punkte
            lines: Liste aller Linien (referenzieren Punkte)
            circles: Liste aller Kreise
            arcs: Liste aller Bögen
            constraints: Liste aller Constraints
        
        Returns:
            SolverResult mit Erfolg/Misserfolg und Details
        """
        if not constraints:
            return SolverResult(
                success=True,
                iterations=0,
                final_error=0.0,
                status=ConstraintStatus.UNDER_CONSTRAINED,
                message="Keine Constraints vorhanden"
            )
        
        # Sammle alle variablen (nicht-fixierten) Punkte
        variable_points = [p for p in points if not p.fixed]
        
        # Füge Punkte aus Linien hinzu
        for line in lines:
            if not line.start.fixed and line.start not in variable_points:
                variable_points.append(line.start)
            if not line.end.fixed and line.end not in variable_points:
                variable_points.append(line.end)
        
        # Füge Kreismittelpunkte hinzu
        for circle in circles:
            if not circle.center.fixed and circle.center not in variable_points:
                variable_points.append(circle.center)
        
        if not variable_points and not circles and not arcs:
            # Alles fixiert - prüfe nur ob Constraints erfüllt
            total_error = sum(calculate_constraint_error(c) for c in constraints)
            if total_error < self.tolerance:
                return SolverResult(
                    success=True,
                    iterations=0,
                    final_error=total_error,
                    status=ConstraintStatus.FULLY_CONSTRAINED,
                    message="Alle Punkte fixiert, Constraints erfüllt"
                )
            else:
                return SolverResult(
                    success=False,
                    iterations=0,
                    final_error=total_error,
                    status=ConstraintStatus.INCONSISTENT,
                    message="Constraints nicht erfüllbar mit fixierten Punkten"
                )
        
        # Iterativer Solver
        for iteration in range(self.max_iterations):
            # Berechne Gesamtfehler
            total_error = 0.0
            for c in constraints:
                error = calculate_constraint_error(c)
                c.error = error
                c.satisfied = error < self.tolerance
                total_error += error ** 2
            
            total_error = math.sqrt(total_error)
            
            # Konvergiert?
            if total_error < self.tolerance:
                return SolverResult(
                    success=True,
                    iterations=iteration + 1,
                    final_error=total_error,
                    status=self._determine_status(constraints, variable_points),
                    message="Konvergiert"
                )
            
            # Berechne und wende Gradienten an
            self._apply_gradients(variable_points, circles, arcs, constraints)
        
        # Maximale Iterationen erreicht
        final_error = sum(calculate_constraint_error(c) ** 2 for c in constraints)
        final_error = math.sqrt(final_error)
        
        return SolverResult(
            success=final_error < self.tolerance * 10,
            iterations=self.max_iterations,
            final_error=final_error,
            status=ConstraintStatus.INCONSISTENT if final_error > 1 else ConstraintStatus.UNDER_CONSTRAINED,
            message="Max Iterationen erreicht"
        )
    
    def _apply_gradients(self,
                         points: List[Point2D],
                         circles: List[Circle2D],
                         arcs: List[Arc2D],
                         constraints: List[Constraint]):
        """Wendet Gradienten-Updates auf alle Variablen an"""
        
        # Punkt-Gradienten
        point_gradients: Dict[str, Tuple[float, float]] = {}
        for p in points:
            point_gradients[p.id] = (0.0, 0.0)
        
        # Radius-Gradienten
        radius_gradients: Dict[str, float] = {}
        for c in circles:
            radius_gradients[c.id] = 0.0
        for a in arcs:
            radius_gradients[a.id] = 0.0
        
        # Berechne Gradienten für jeden Constraint
        for constraint in constraints:
            self._compute_constraint_gradient(
                constraint, point_gradients, radius_gradients
            )
        
        # Wende Gradienten an
        for p in points:
            if p.id in point_gradients:
                gx, gy = point_gradients[p.id]
                magnitude = math.sqrt(gx**2 + gy**2)
                if magnitude > 0.001:
                    # Normalisiere und skaliere
                    scale = min(self.step_size, magnitude) / magnitude
                    p.x -= gx * scale * self.damping
                    p.y -= gy * scale * self.damping
        
        for c in circles:
            if c.id in radius_gradients:
                grad = radius_gradients[c.id]
                c.radius -= grad * self.step_size * self.damping
                c.radius = max(0.001, c.radius)  # Radius muss positiv sein
    
    def _compute_constraint_gradient(self,
                                      constraint: Constraint,
                                      point_grads: Dict[str, Tuple[float, float]],
                                      radius_grads: Dict[str, float]):
        """Berechnet den Gradienten für einen einzelnen Constraint"""
        
        ct = constraint.type
        entities = constraint.entities
        
        if ct == ConstraintType.COINCIDENT:
            p1, p2 = entities
            dx = p1.x - p2.x
            dy = p1.y - p2.y
            
            if not p1.fixed and p1.id in point_grads:
                gx, gy = point_grads[p1.id]
                point_grads[p1.id] = (gx + dx, gy + dy)
            if not p2.fixed and p2.id in point_grads:
                gx, gy = point_grads[p2.id]
                point_grads[p2.id] = (gx - dx, gy - dy)
        
        elif ct == ConstraintType.HORIZONTAL:
            line = entities[0]
            dy = line.end.y - line.start.y
            
            if not line.start.fixed and line.start.id in point_grads:
                gx, gy = point_grads[line.start.id]
                point_grads[line.start.id] = (gx, gy - dy * 0.5)
            if not line.end.fixed and line.end.id in point_grads:
                gx, gy = point_grads[line.end.id]
                point_grads[line.end.id] = (gx, gy + dy * 0.5)
        
        elif ct == ConstraintType.VERTICAL:
            line = entities[0]
            dx = line.end.x - line.start.x
            
            if not line.start.fixed and line.start.id in point_grads:
                gx, gy = point_grads[line.start.id]
                point_grads[line.start.id] = (gx - dx * 0.5, gy)
            if not line.end.fixed and line.end.id in point_grads:
                gx, gy = point_grads[line.end.id]
                point_grads[line.end.id] = (gx + dx * 0.5, gy)
        
        elif ct == ConstraintType.LENGTH:
            line = entities[0]
            target = constraint.value
            current = line.length
            
            if current < 0.001:
                return
            
            error = current - target
            dx = (line.end.x - line.start.x) / current
            dy = (line.end.y - line.start.y) / current
            
            if not line.start.fixed and line.start.id in point_grads:
                gx, gy = point_grads[line.start.id]
                point_grads[line.start.id] = (gx - dx * error, gy - dy * error)
            if not line.end.fixed and line.end.id in point_grads:
                gx, gy = point_grads[line.end.id]
                point_grads[line.end.id] = (gx + dx * error, gy + dy * error)
        
        elif ct == ConstraintType.DISTANCE:
            if len(entities) == 2 and isinstance(entities[0], Point2D) and isinstance(entities[1], Point2D):
                p1, p2 = entities
                target = constraint.value
                current = p1.distance_to(p2)
                
                if current < 0.001:
                    return
                
                error = current - target
                dx = (p1.x - p2.x) / current
                dy = (p1.y - p2.y) / current
                
                if not p1.fixed and p1.id in point_grads:
                    gx, gy = point_grads[p1.id]
                    point_grads[p1.id] = (gx + dx * error, gy + dy * error)
                if not p2.fixed and p2.id in point_grads:
                    gx, gy = point_grads[p2.id]
                    point_grads[p2.id] = (gx - dx * error, gy - dy * error)
        
        elif ct == ConstraintType.PARALLEL:
            l1, l2 = entities
            d1 = l1.direction
            d2 = l2.direction
            
            # Kreuzprodukt = sin(Winkel)
            cross = d1[0] * d2[1] - d1[1] * d2[0]
            
            # Rotiere l2 um den Winkel zu reduzieren
            if abs(cross) > 0.001 and not l2.end.fixed and l2.end.id in point_grads:
                # Vereinfachter Gradient
                gx, gy = point_grads[l2.end.id]
                point_grads[l2.end.id] = (gx - cross * d2[1], gy + cross * d2[0])
        
        elif ct == ConstraintType.PERPENDICULAR:
            l1, l2 = entities
            d1 = l1.direction
            d2 = l2.direction
            
            # Skalarprodukt = cos(Winkel)
            dot = d1[0] * d2[0] + d1[1] * d2[1]
            
            if abs(dot) > 0.001 and not l2.end.fixed and l2.end.id in point_grads:
                gx, gy = point_grads[l2.end.id]
                point_grads[l2.end.id] = (gx + dot * d2[0], gy + dot * d2[1])
        
        elif ct == ConstraintType.EQUAL_LENGTH:
            l1, l2 = entities
            len1 = l1.length
            len2 = l2.length
            error = len2 - len1
            
            if len2 > 0.001:
                dx = (l2.end.x - l2.start.x) / len2
                dy = (l2.end.y - l2.start.y) / len2
                
                if not l2.end.fixed and l2.end.id in point_grads:
                    gx, gy = point_grads[l2.end.id]
                    point_grads[l2.end.id] = (gx + dx * error, gy + dy * error)
        
        elif ct == ConstraintType.POINT_ON_LINE:
            point, line = entities
            
            # Projektion des Punktes auf die Linie
            dx = line.end.x - line.start.x
            dy = line.end.y - line.start.y
            length_sq = dx*dx + dy*dy
            
            if length_sq < 0.001:
                return
            
            t = ((point.x - line.start.x)*dx + (point.y - line.start.y)*dy) / length_sq
            t = max(0, min(1, t))
            
            proj_x = line.start.x + t * dx
            proj_y = line.start.y + t * dy
            
            error_x = point.x - proj_x
            error_y = point.y - proj_y
            
            if not point.fixed and point.id in point_grads:
                gx, gy = point_grads[point.id]
                point_grads[point.id] = (gx + error_x, gy + error_y)
        
        elif ct == ConstraintType.RADIUS:
            circle = entities[0]
            target = constraint.value
            error = circle.radius - target
            
            if circle.id in radius_grads:
                radius_grads[circle.id] += error
        
        elif ct == ConstraintType.DIAMETER:
            circle = entities[0]
            target = constraint.value / 2  # Durchmesser -> Radius
            error = circle.radius - target
            
            if circle.id in radius_grads:
                radius_grads[circle.id] += error
        
        elif ct == ConstraintType.CONCENTRIC:
            c1, c2 = entities
            dx = c2.center.x - c1.center.x
            dy = c2.center.y - c1.center.y
            
            if not c2.center.fixed and c2.center.id in point_grads:
                gx, gy = point_grads[c2.center.id]
                point_grads[c2.center.id] = (gx - dx, gy - dy)
        
        elif ct == ConstraintType.MIDPOINT:
            point, line = entities
            mid = line.midpoint
            
            dx = point.x - mid.x
            dy = point.y - mid.y
            
            if not point.fixed and point.id in point_grads:
                gx, gy = point_grads[point.id]
                point_grads[point.id] = (gx + dx, gy + dy)
    
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
