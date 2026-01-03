"""
LiteCAD Sketcher - Constraint System
Geometrische Constraints für parametrisches Design
"""

from dataclasses import dataclass, field
from typing import Union, List, Optional, Any
from enum import Enum, auto
import math
import uuid

from .geometry import Point2D, Line2D, Circle2D, Arc2D


class ConstraintType(Enum):
    """Verfügbare Constraint-Typen"""
    # Punkt-Constraints
    FIXED = auto()              # Punkt fixiert
    COINCIDENT = auto()         # Zwei Punkte zusammen
    POINT_ON_LINE = auto()      # Punkt auf Linie
    POINT_ON_CIRCLE = auto()    # Punkt auf Kreis
    
    # Linien-Constraints
    HORIZONTAL = auto()         # Linie horizontal
    VERTICAL = auto()           # Linie vertikal
    PARALLEL = auto()           # Zwei Linien parallel
    PERPENDICULAR = auto()      # Zwei Linien senkrecht
    COLLINEAR = auto()          # Zwei Linien kollinear
    EQUAL_LENGTH = auto()       # Zwei Linien gleich lang
    
    # Kreis-Constraints
    CONCENTRIC = auto()         # Kreise konzentrisch
    EQUAL_RADIUS = auto()       # Kreise gleicher Radius
    TANGENT = auto()            # Tangential
    
    # Maß-Constraints (Dimensionen)
    DISTANCE = auto()           # Abstand
    LENGTH = auto()             # Länge einer Linie
    ANGLE = auto()              # Winkel zwischen Linien
    RADIUS = auto()             # Radius eines Kreises
    DIAMETER = auto()           # Durchmesser
    
    # Symmetrie
    SYMMETRIC = auto()          # Symmetrisch zu Linie
    MIDPOINT = auto()           # Punkt auf Mittelpunkt


@dataclass
class Constraint:
    """Basis-Klasse für alle Constraints"""
    type: ConstraintType
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    entities: List[Any] = field(default_factory=list)  # Betroffene Geometrie
    value: Optional[float] = None  # Für Dimension-Constraints
    driving: bool = True  # True = treibend, False = referenz
    satisfied: bool = False
    error: float = 0.0  # Abweichung vom Sollwert
    
    def __repr__(self):
        val_str = f"={self.value}" if self.value is not None else ""
        return f"{self.type.name}{val_str}"


# === Constraint-Factories ===

def make_fixed(point: Point2D) -> Constraint:
    """Punkt fixieren"""
    c = Constraint(
        type=ConstraintType.FIXED,
        entities=[point],
        value=None
    )
    point.fixed = True
    return c


def make_coincident(p1: Point2D, p2: Point2D) -> Constraint:
    """Zwei Punkte zusammenfallen lassen"""
    return Constraint(
        type=ConstraintType.COINCIDENT,
        entities=[p1, p2]
    )


def make_point_on_line(point: Point2D, line: Line2D) -> Constraint:
    """Punkt auf Linie"""
    return Constraint(
        type=ConstraintType.POINT_ON_LINE,
        entities=[point, line]
    )


def make_horizontal(line: Line2D) -> Constraint:
    """Linie horizontal"""
    return Constraint(
        type=ConstraintType.HORIZONTAL,
        entities=[line]
    )


def make_vertical(line: Line2D) -> Constraint:
    """Linie vertikal"""
    return Constraint(
        type=ConstraintType.VERTICAL,
        entities=[line]
    )


def make_parallel(l1: Line2D, l2: Line2D) -> Constraint:
    """Zwei Linien parallel"""
    return Constraint(
        type=ConstraintType.PARALLEL,
        entities=[l1, l2]
    )


def make_perpendicular(l1: Line2D, l2: Line2D) -> Constraint:
    """Zwei Linien senkrecht"""
    return Constraint(
        type=ConstraintType.PERPENDICULAR,
        entities=[l1, l2]
    )


def make_equal_length(l1: Line2D, l2: Line2D) -> Constraint:
    """Zwei Linien gleich lang"""
    return Constraint(
        type=ConstraintType.EQUAL_LENGTH,
        entities=[l1, l2]
    )


def make_concentric(c1: Union[Circle2D, Arc2D], c2: Union[Circle2D, Arc2D]) -> Constraint:
    """Kreise/Bögen konzentrisch"""
    return Constraint(
        type=ConstraintType.CONCENTRIC,
        entities=[c1, c2]
    )


def make_tangent(entity1, entity2) -> Constraint:
    """Tangential-Constraint"""
    return Constraint(
        type=ConstraintType.TANGENT,
        entities=[entity1, entity2]
    )


# === Dimension-Constraints ===

def make_length(line: Line2D, length: float) -> Constraint:
    """Länge einer Linie festlegen"""
    return Constraint(
        type=ConstraintType.LENGTH,
        entities=[line],
        value=length
    )


def make_distance(p1: Point2D, p2: Point2D, distance: float) -> Constraint:
    """Abstand zwischen zwei Punkten"""
    return Constraint(
        type=ConstraintType.DISTANCE,
        entities=[p1, p2],
        value=distance
    )


def make_distance_point_line(point: Point2D, line: Line2D, distance: float) -> Constraint:
    """Abstand Punkt zu Linie"""
    return Constraint(
        type=ConstraintType.DISTANCE,
        entities=[point, line],
        value=distance
    )


def make_angle(l1: Line2D, l2: Line2D, angle_deg: float) -> Constraint:
    """Winkel zwischen zwei Linien"""
    return Constraint(
        type=ConstraintType.ANGLE,
        entities=[l1, l2],
        value=angle_deg
    )


def make_radius(circle: Union[Circle2D, Arc2D], radius: float) -> Constraint:
    """Radius festlegen"""
    return Constraint(
        type=ConstraintType.RADIUS,
        entities=[circle],
        value=radius
    )


def make_diameter(circle: Union[Circle2D, Arc2D], diameter: float) -> Constraint:
    """Durchmesser festlegen"""
    return Constraint(
        type=ConstraintType.DIAMETER,
        entities=[circle],
        value=diameter
    )


def make_symmetric(p1: Point2D, p2: Point2D, axis: Line2D) -> Constraint:
    """Zwei Punkte symmetrisch zu einer Achse"""
    return Constraint(
        type=ConstraintType.SYMMETRIC,
        entities=[p1, p2, axis]
    )


def make_midpoint(point: Point2D, line: Line2D) -> Constraint:
    """Punkt auf Mittelpunkt einer Linie"""
    return Constraint(
        type=ConstraintType.MIDPOINT,
        entities=[point, line]
    )


# === Constraint Error Calculation ===

def calculate_constraint_error(constraint: Constraint) -> float:
    """Berechnet den Fehler eines Constraints (0 = erfüllt)"""
    ct = constraint.type
    entities = constraint.entities
    
    if ct == ConstraintType.COINCIDENT:
        p1, p2 = entities
        return p1.distance_to(p2)
    
    elif ct == ConstraintType.HORIZONTAL:
        line = entities[0]
        return abs(line.end.y - line.start.y)
    
    elif ct == ConstraintType.VERTICAL:
        line = entities[0]
        return abs(line.end.x - line.start.x)
    
    elif ct == ConstraintType.LENGTH:
        line = entities[0]
        target = constraint.value
        return abs(line.length - target)
    
    elif ct == ConstraintType.DISTANCE:
        if len(entities) == 2:
            e1, e2 = entities
            if isinstance(e1, Point2D) and isinstance(e2, Point2D):
                actual = e1.distance_to(e2)
            elif isinstance(e1, Point2D) and isinstance(e2, Line2D):
                actual = e2.distance_to_point(e1)
            else:
                return 0.0
            return abs(actual - constraint.value)
    
    elif ct == ConstraintType.PARALLEL:
        l1, l2 = entities
        d1 = l1.direction
        d2 = l2.direction
        cross = abs(d1[0] * d2[1] - d1[1] * d2[0])
        return cross
    
    elif ct == ConstraintType.PERPENDICULAR:
        l1, l2 = entities
        d1 = l1.direction
        d2 = l2.direction
        dot = abs(d1[0] * d2[0] + d1[1] * d2[1])
        return dot
    
    elif ct == ConstraintType.EQUAL_LENGTH:
        l1, l2 = entities
        return abs(l1.length - l2.length)
    
    elif ct == ConstraintType.POINT_ON_LINE:
        point, line = entities
        return line.distance_to_point(point)
    
    elif ct == ConstraintType.RADIUS:
        circle = entities[0]
        return abs(circle.radius - constraint.value)
    
    elif ct == ConstraintType.DIAMETER:
        circle = entities[0]
        return abs(circle.diameter - constraint.value)
    
    elif ct == ConstraintType.ANGLE:
        l1, l2 = entities
        angle1 = l1.angle
        angle2 = l2.angle
        actual = abs(angle2 - angle1)
        if actual > 180:
            actual = 360 - actual
        return abs(actual - constraint.value)
    
    elif ct == ConstraintType.CONCENTRIC:
        c1, c2 = entities
        return c1.center.distance_to(c2.center)
    
    elif ct == ConstraintType.MIDPOINT:
        point, line = entities
        mid = line.midpoint
        return point.distance_to(mid)
    
    elif ct == ConstraintType.FIXED:
        return 0.0  # Fixed wird durch den Solver behandelt
    
    return 0.0


def is_constraint_satisfied(constraint: Constraint, tolerance: float = 1e-6) -> bool:
    """Prüft ob ein Constraint erfüllt ist"""
    error = calculate_constraint_error(constraint)
    constraint.error = error
    constraint.satisfied = error < tolerance
    return constraint.satisfied


class ConstraintStatus(Enum):
    """Status des Constraint-Systems"""
    UNDER_CONSTRAINED = auto()   # Noch Freiheitsgrade übrig
    FULLY_CONSTRAINED = auto()   # Vollständig bestimmt
    OVER_CONSTRAINED = auto()    # Widersprüchliche Constraints
    INCONSISTENT = auto()        # Nicht lösbar
