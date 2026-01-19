"""
LiteCAD Sketcher - Geometrie-Primitives
Punkte, Linien, Kreise, Bögen mit parametrischer Unterstützung
"""

from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from enum import Enum, auto
import math
import uuid


class GeometryType(Enum):
    """Geometrie-Typen"""
    POINT = auto()
    LINE = auto()
    CIRCLE = auto()
    ARC = auto()
    SPLINE = auto()


@dataclass
class Point2D:
    """2D-Punkt - Grundbaustein aller Geometrie (Gehärtet)"""
    x: float = 0.0
    y: float = 0.0
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    fixed: bool = False
    construction: bool = False
    standalone: bool = False
    
    def __post_init__(self):
        """
        FIREWALL: Wandelt alles sofort in native Python-Floats um.
        Schützt vor Abstürzen durch Solver-Rückgabewerte (NumPy).
        """
        try:
            # .item() wandelt numpy-skalare extrem schnell in python-types
            if hasattr(self.x, 'item'): self.x = self.x.item()
            else: self.x = float(self.x)
            
            if hasattr(self.y, 'item'): self.y = self.y.item()
            else: self.y = float(self.y)
        except (TypeError, ValueError):
            self.x = 0.0
            self.y = 0.0

    def distance_to(self, other: 'Point2D') -> float:
        return math.hypot(self.x - other.x, self.y - other.y)
    
    def midpoint(self, other: 'Point2D') -> 'Point2D':
        return Point2D((self.x + other.x) / 2, (self.y + other.y) / 2)
    
    def as_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)
    
    def __repr__(self):
        return f"P({self.x:.2f}, {self.y:.2f})"


@dataclass
class Line2D:
    """2D-Linie zwischen zwei Punkten"""
    start: Point2D
    end: Point2D
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    construction: bool = False
    
    @property
    def length(self) -> float:
        """Länge der Linie"""
        return self.start.distance_to(self.end)
    
    @property
    def midpoint(self) -> Point2D:
        """Mittelpunkt der Linie"""
        return self.start.midpoint(self.end)
    
    @property
    def angle(self) -> float:
        """Winkel zur X-Achse in Grad"""
        dx = self.end.x - self.start.x
        dy = self.end.y - self.start.y
        return math.degrees(math.atan2(dy, dx))
    
    @property
    def direction(self) -> Tuple[float, float]:
        """Normierter Richtungsvektor"""
        length = self.length
        if length < 1e-10:
            return (1.0, 0.0)
        dx = self.end.x - self.start.x
        dy = self.end.y - self.start.y
        return (dx / length, dy / length)
    
    def point_at_parameter(self, t: float) -> Point2D:
        """Punkt auf der Linie bei Parameter t (0=start, 1=end)"""
        x = self.start.x + t * (self.end.x - self.start.x)
        y = self.start.y + t * (self.end.y - self.start.y)
        return Point2D(x, y)
    
    def distance_to_point(self, p: Point2D) -> float:
        """Kürzester Abstand zu einem Punkt"""
        # Projektion auf Linie
        dx = self.end.x - self.start.x
        dy = self.end.y - self.start.y
        length_sq = dx*dx + dy*dy
        
        if length_sq < 1e-10:
            return self.start.distance_to(p)
        
        t = max(0, min(1, ((p.x - self.start.x)*dx + (p.y - self.start.y)*dy) / length_sq))
        proj = self.point_at_parameter(t)
        return proj.distance_to(p)
    
    def is_horizontal(self, tolerance: float = 1e-6) -> bool:
        """Prüft ob Linie horizontal ist"""
        return abs(self.end.y - self.start.y) < tolerance
    
    def is_vertical(self, tolerance: float = 1e-6) -> bool:
        """Prüft ob Linie vertikal ist"""
        return abs(self.end.x - self.start.x) < tolerance
    
    def __repr__(self):
        return f"Line({self.start} -> {self.end})"


@dataclass
class Circle2D:
    """2D-Kreis"""
    center: Point2D
    radius: float = 10.0
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    construction: bool = False
    
    @property
    def diameter(self) -> float:
        return self.radius * 2
    
    @property
    def circumference(self) -> float:
        return 2 * math.pi * self.radius
    
    @property
    def area(self) -> float:
        return math.pi * self.radius ** 2
    
    def point_at_angle(self, angle_deg: float) -> Point2D:
        """Punkt auf dem Kreis bei gegebenem Winkel"""
        rad = math.radians(angle_deg)
        x = self.center.x + self.radius * math.cos(rad)
        y = self.center.y + self.radius * math.sin(rad)
        return Point2D(x, y)
    
    def contains_point(self, p: Point2D, tolerance: float = 1e-6) -> bool:
        """Prüft ob Punkt auf dem Kreis liegt"""
        dist = self.center.distance_to(p)
        return abs(dist - self.radius) < tolerance
    
    def __repr__(self):
        return f"Circle(center={self.center}, r={self.radius:.2f})"


@dataclass
class Arc2D:
    """2D-Kreisbogen"""
    center: Point2D
    radius: float = 10.0
    start_angle: float = 0.0    # Startwinkel in Grad
    end_angle: float = 90.0     # Endwinkel in Grad
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    construction: bool = False
    
    @property
    def start_point(self) -> Point2D:
        """Startpunkt des Bogens"""
        rad = math.radians(self.start_angle)
        return Point2D(
            self.center.x + self.radius * math.cos(rad),
            self.center.y + self.radius * math.sin(rad)
        )
    
    @property
    def end_point(self) -> Point2D:
        """Endpunkt des Bogens"""
        rad = math.radians(self.end_angle)
        return Point2D(
            self.center.x + self.radius * math.cos(rad),
            self.center.y + self.radius * math.sin(rad)
        )
    
    @property
    def sweep_angle(self) -> float:
        """Öffnungswinkel in Grad"""
        sweep = self.end_angle - self.start_angle
        while sweep < 0:
            sweep += 360
        return sweep
    
    @property
    def arc_length(self) -> float:
        """Bogenlänge"""
        return self.radius * math.radians(self.sweep_angle)
    
    def point_at_parameter(self, t: float) -> Point2D:
        """Punkt auf dem Bogen bei Parameter t (0=start, 1=end)"""
        angle = self.start_angle + t * self.sweep_angle
        rad = math.radians(angle)
        return Point2D(
            self.center.x + self.radius * math.cos(rad),
            self.center.y + self.radius * math.sin(rad)
        )
    
    def __repr__(self):
        return f"Arc(center={self.center}, r={self.radius:.2f}, {self.start_angle:.1f}°-{self.end_angle:.1f}°)"


@dataclass
class Rectangle2D:
    """2D-Rechteck (Hilfskonstrukt aus 4 Linien)"""
    corner: Point2D  # Untere linke Ecke
    width: float = 20.0
    height: float = 10.0
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    
    def to_lines(self) -> List[Line2D]:
        """Konvertiert zu 4 Linien"""
        p1 = self.corner
        p2 = Point2D(self.corner.x + self.width, self.corner.y)
        p3 = Point2D(self.corner.x + self.width, self.corner.y + self.height)
        p4 = Point2D(self.corner.x, self.corner.y + self.height)
        
        return [
            Line2D(p1, p2),  # Unten
            Line2D(p2, p3),  # Rechts
            Line2D(p3, p4),  # Oben
            Line2D(p4, p1),  # Links
        ]
    
    @property
    def center(self) -> Point2D:
        return Point2D(
            self.corner.x + self.width / 2,
            self.corner.y + self.height / 2
        )
    
    def __repr__(self):
        return f"Rect({self.corner}, {self.width:.2f}x{self.height:.2f})"


# === Utility-Funktionen ===

def line_line_intersection(l1: Line2D, l2: Line2D) -> Optional[Point2D]:
    """Schnittpunkt zweier Linien (oder None)"""
    x1, y1 = l1.start.x, l1.start.y
    x2, y2 = l1.end.x, l1.end.y
    x3, y3 = l2.start.x, l2.start.y
    x4, y4 = l2.end.x, l2.end.y
    
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-10:
        return None  # Parallel
    
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    
    x = x1 + t * (x2 - x1)
    y = y1 + t * (y2 - y1)
    
    return Point2D(x, y)


def circle_line_intersection(circle: Circle2D, line: Line2D) -> List[Point2D]:
    """Schnittpunkte Kreis/Linie"""
    # Linie in parametrischer Form: P = start + t * (end - start)
    dx = line.end.x - line.start.x
    dy = line.end.y - line.start.y
    
    fx = line.start.x - circle.center.x
    fy = line.start.y - circle.center.y
    
    a = dx*dx + dy*dy
    b = 2 * (fx*dx + fy*dy)
    c = fx*fx + fy*fy - circle.radius**2
    
    discriminant = b*b - 4*a*c
    
    if discriminant < 0:
        return []
    
    points = []
    if discriminant == 0:
        t = -b / (2*a)
        points.append(line.point_at_parameter(t))
    else:
        sqrt_disc = math.sqrt(discriminant)
        t1 = (-b - sqrt_disc) / (2*a)
        t2 = (-b + sqrt_disc) / (2*a)
        points.append(line.point_at_parameter(t1))
        points.append(line.point_at_parameter(t2))
    
    return points


def points_are_coincident(p1: Point2D, p2: Point2D, tolerance: float = 1e-6) -> bool:
    """Prüft ob zwei Punkte zusammenfallen"""
    return p1.distance_to(p2) < tolerance


def lines_are_parallel(l1: Line2D, l2: Line2D, tolerance: float = 1e-6) -> bool:
    """Prüft ob zwei Linien parallel sind"""
    d1 = l1.direction
    d2 = l2.direction
    # Kreuzprodukt der Richtungsvektoren
    cross = d1[0] * d2[1] - d1[1] * d2[0]
    return abs(cross) < tolerance


def lines_are_perpendicular(l1: Line2D, l2: Line2D, tolerance: float = 1e-6) -> bool:
    """Prüft ob zwei Linien senkrecht zueinander sind"""
    d1 = l1.direction
    d2 = l2.direction
    # Skalarprodukt der Richtungsvektoren
    dot = d1[0] * d2[0] + d1[1] * d2[1]
    return abs(dot) < tolerance


@dataclass
class SplineControlPoint:
    """Kontrollpunkt für Bézier-Spline mit Tangent-Handles"""
    point: Point2D
    # Handle-Offsets relativ zum Punkt (nicht absolute Positionen)
    handle_in: Tuple[float, float] = (0.0, 0.0)   # Eingehende Tangente
    handle_out: Tuple[float, float] = (0.0, 0.0)  # Ausgehende Tangente
    smooth: bool = True  # Handles gespiegelt (glatter Übergang)
    
    @property
    def handle_in_abs(self) -> Tuple[float, float]:
        """Absolute Position des eingehenden Handles"""
        return (self.point.x + self.handle_in[0], self.point.y + self.handle_in[1])
    
    @property
    def handle_out_abs(self) -> Tuple[float, float]:
        """Absolute Position des ausgehenden Handles"""
        return (self.point.x + self.handle_out[0], self.point.y + self.handle_out[1])
    
    def set_handle_in_abs(self, x: float, y: float):
        """Setzt eingehenden Handle auf absolute Position"""
        self.handle_in = (x - self.point.x, y - self.point.y)
        if self.smooth:
            # Spiegeln für glatten Übergang
            self.handle_out = (-self.handle_in[0], -self.handle_in[1])
    
    def set_handle_out_abs(self, x: float, y: float):
        """Setzt ausgehenden Handle auf absolute Position"""
        self.handle_out = (x - self.point.x, y - self.point.y)
        if self.smooth:
            # Spiegeln für glatten Übergang
            self.handle_in = (-self.handle_out[0], -self.handle_out[1])


@dataclass
class BezierSpline:
    """Kubische Bézier-Spline mit editierbaren Tangent-Handles (Fusion360-Style)"""
    control_points: List[SplineControlPoint] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    construction: bool = False
    closed: bool = False
    _lines: List['Line2D'] = field(default_factory=list)  # Referenz auf generierte Linien
    
    def add_point(self, x: float, y: float) -> SplineControlPoint:
        """Fügt einen neuen Kontrollpunkt hinzu"""
        pt = Point2D(x, y)
        cp = SplineControlPoint(point=pt)
        
        # Auto-Tangenten basierend auf Nachbarpunkten
        if len(self.control_points) >= 1:
            prev = self.control_points[-1]
            # Handle-Richtung = 1/3 der Distanz zum vorherigen Punkt
            dx = (prev.point.x - x) / 3
            dy = (prev.point.y - y) / 3
            cp.handle_in = (dx, dy)
            cp.handle_out = (-dx, -dy)
            
            # Update auch den vorherigen Punkt
            prev.handle_out = (-dx, -dy)
            if prev.smooth:
                prev.handle_in = (dx, dy)
        
        self.control_points.append(cp)
        return cp
    
    def get_curve_points(self, segments_per_span: int = 10) -> List[Tuple[float, float]]:
        """Berechnet Punkte entlang der Kurve für Rendering"""
        if len(self.control_points) < 2:
            return [(cp.point.x, cp.point.y) for cp in self.control_points]
        
        points = []
        
        # Für jedes Segment zwischen zwei Kontrollpunkten
        n = len(self.control_points)
        segments = n if self.closed else n - 1
        
        for i in range(segments):
            p0 = self.control_points[i]
            p1 = self.control_points[(i + 1) % n]
            
            # Kubische Bézier: P0, P0+handle_out, P1+handle_in, P1
            x0, y0 = p0.point.x, p0.point.y
            x1, y1 = p0.handle_out_abs
            x2, y2 = p1.handle_in_abs
            x3, y3 = p1.point.x, p1.point.y
            
            # Punkte auf dem Segment
            for j in range(segments_per_span + 1):
                t = j / segments_per_span
                # Kubische Bézier-Formel
                mt = 1 - t
                x = mt*mt*mt*x0 + 3*mt*mt*t*x1 + 3*mt*t*t*x2 + t*t*t*x3
                y = mt*mt*mt*y0 + 3*mt*mt*t*y1 + 3*mt*t*t*y2 + t*t*t*y3
                
                # Duplikate vermeiden
                if not points or (abs(x - points[-1][0]) > 1e-6 or abs(y - points[-1][1]) > 1e-6):
                    points.append((x, y))
        
        return points
    
    def to_lines(self, segments_per_span: int = 10) -> List[Line2D]:
        """Konvertiert Spline zu Linien-Approximation"""
        pts = self.get_curve_points(segments_per_span)
        lines = []
        for i in range(len(pts) - 1):
            p1 = Point2D(pts[i][0], pts[i][1])
            p2 = Point2D(pts[i+1][0], pts[i+1][1])
            line = Line2D(p1, p2)
            line.construction = self.construction
            lines.append(line)
        return lines
