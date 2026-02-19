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
        def _coerce_scalar(value, fallback=0.0):
            try:
                # Falls versehentlich eine gebundene Methode uebergeben wurde (z.B. QPointF.y)
                if callable(value):
                    value = value()

                # NumPy-Skalare: .item() nur nutzen, wenn wirklich aufrufbar
                item_attr = getattr(value, "item", None)
                if callable(item_attr):
                    value = item_attr()

                # Manche Wrapper liefern erneut callables
                if callable(value):
                    value = value()

                return float(value)
            except (TypeError, ValueError):
                return fallback

        try:
            self.x = _coerce_scalar(self.x, 0.0)
            self.y = _coerce_scalar(self.y, 0.0)
        except (TypeError, ValueError):
            self.x = 0.0
            self.y = 0.0

    def distance_to(self, other: 'Point2D') -> float:
        return math.hypot(self.x - other.x, self.y - other.y)
    
    def midpoint(self, other: 'Point2D') -> 'Point2D':
        return Point2D((self.x + other.x) / 2, (self.y + other.y) / 2)
    
    def as_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)

    def to_dict(self) -> dict:
        """Serialisiert zu Dictionary für JSON."""
        return {
            "type": "Point2D",
            "x": self.x,
            "y": self.y,
            "id": self.id,
            "fixed": self.fixed,
            "construction": self.construction,
        }

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

    def to_dict(self) -> dict:
        """Serialisiert zu Dictionary für JSON."""
        return {
            "type": "Line2D",
            "start_x": self.start.x,
            "start_y": self.start.y,
            "end_x": self.end.x,
            "end_y": self.end.y,
            "id": self.id,
            "construction": self.construction,
        }

    def __repr__(self):
        return f"Line({self.start} -> {self.end})"


@dataclass
class Circle2D:
    """2D-Kreis

    TNP v4.1: Native OCP Daten für optimale Extrusion.
    Wenn native_ocp_data gesetzt ist, wird der Circle direkt als
    nativer OCP Circle extrudiert (3 Faces statt 14+).
    """
    center: Point2D
    radius: float = 10.0
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    construction: bool = False
    # TNP v4.1: Native OCP Daten für optimierte Extrusion
    native_ocp_data: Optional[dict] = None  # {center, radius, plane}

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

    def to_dict(self) -> dict:
        """Serialisiert zu Dictionary für JSON."""
        return {
            "type": "Circle2D",
            "center_x": self.center.x,
            "center_y": self.center.y,
            "radius": self.radius,
            "id": self.id,
            "construction": self.construction,
            "native_ocp_data": self.native_ocp_data,
        }

    def __repr__(self):
        return f"Circle(center={self.center}, r={self.radius:.2f})"


@dataclass
class Arc2D:
    """2D-Kreisbogen

    TNP v4.1: Native OCP Daten für optimale Extrusion.
    Wenn native_ocp_data gesetzt ist, wird der Arc direkt als
    nativer OCP Arc extrudiert (wenige Faces statt Polygon-Approximation).
    """
    center: Point2D
    radius: float = 10.0
    start_angle: float = 0.0    # Startwinkel in Grad
    end_angle: float = 90.0     # Endwinkel in Grad
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    construction: bool = False
    # TNP v4.1: Native OCP Daten für optimierte Extrusion
    native_ocp_data: Optional[dict] = None  # {center, radius, start_angle, end_angle, plane}
    
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

    def to_dict(self) -> dict:
        """Serialisiert zu Dictionary für JSON."""
        return {
            "type": "Arc2D",
            "center_x": self.center.x,
            "center_y": self.center.y,
            "radius": self.radius,
            "start_angle": self.start_angle,
            "end_angle": self.end_angle,
            "id": self.id,
            "construction": self.construction,
            "native_ocp_data": self.native_ocp_data,
        }

    def __repr__(self):
        return f"Arc(center={self.center}, r={self.radius:.2f}, {self.start_angle:.1f}°-{self.end_angle:.1f}°)"


@dataclass
class Ellipse2D:
    """2D-Ellipse mit separaten Achsen und Rotation in Grad.
    
    TNP v4.1: Native OCP Daten für optimale Extrusion.
    Wenn native_ocp_data gesetzt ist, wird die Ellipse direkt als
    nativer OCP Ellipse extrudiert (glatte Fläche statt Polygon-Approximation).
    """
    center: Point2D
    radius_x: float = 10.0  # Major radius
    radius_y: float = 5.0   # Minor radius
    rotation: float = 0.0   # Rotation in Grad
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    construction: bool = False
    # TNP v4.1: Native OCP Daten für optimierte Extrusion
    native_ocp_data: Optional[dict] = None  # {center, radius_x, radius_y, rotation, plane}

    def point_at_angle(self, angle_deg: float) -> Point2D:
        """Punkt auf der Ellipse bei gegebenem Winkel (parametrisch)."""
        rad = math.radians(angle_deg)
        # Lokale Koordinaten (ungerotiert)
        local_x = self.radius_x * math.cos(rad)
        local_y = self.radius_y * math.sin(rad)
        # Rotation anwenden
        rot_rad = math.radians(self.rotation)
        cos_rot = math.cos(rot_rad)
        sin_rot = math.sin(rot_rad)
        x = self.center.x + local_x * cos_rot - local_y * sin_rot
        y = self.center.y + local_x * sin_rot + local_y * cos_rot
        return Point2D(x, y)

    def point_on_major_axis(self) -> Point2D:
        """Endpunkt der Major-Achse."""
        return self.point_at_angle(0)

    def point_on_minor_axis(self) -> Point2D:
        """Endpunkt der Minor-Achse (90°)."""
        return self.point_at_angle(90)

    def get_curve_points(self, segments: int = 64) -> List[Tuple[float, float]]:
        """Berechnet Punkte entlang der Ellipse für Rendering.
        
        Args:
            segments: Anzahl der Segmente (default: 64 für glatte Kurve)
        
        Returns:
            Liste von (x, y) Tupeln
        """
        points = []
        for i in range(segments + 1):
            angle = (360.0 * i) / segments
            pt = self.point_at_angle(angle)
            points.append((pt.x, pt.y))
        return points

    def to_dict(self) -> dict:
        """Serialisiert zu Dictionary für JSON."""
        return {
            "type": "Ellipse2D",
            "center_x": self.center.x,
            "center_y": self.center.y,
            "radius_x": self.radius_x,
            "radius_y": self.radius_y,
            "rotation": self.rotation,
            "id": self.id,
            "construction": self.construction,
            "native_ocp_data": self.native_ocp_data,
        }

    def __repr__(self):
        return f"Ellipse(center={self.center}, rx={self.radius_x:.2f}, ry={self.radius_y:.2f}, rot={self.rotation:.1f}°)"


@dataclass
class Polygon2D:
    """2D-Polygon als Punktliste."""
    points: List[Point2D] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    construction: bool = False
    closed: bool = True

    def vertex_count(self) -> int:
        return len(self.points)

    def centroid(self) -> Point2D:
        if not self.points:
            return Point2D(0.0, 0.0)
        sx = sum(p.x for p in self.points)
        sy = sum(p.y for p in self.points)
        n = len(self.points)
        return Point2D(sx / n, sy / n)


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


def circle_line_intersection(circle: Circle2D, line: Line2D, segment_only: bool = True) -> List[Point2D]:
    """
    Schnittpunkte Kreis/Linie.

    Args:
        circle: Der Kreis
        line: Die Linie
        segment_only: Wenn True (default), nur Punkte auf dem SEGMENT [0,1] zurückgeben.
                      Wenn False, auch Punkte auf der unendlichen Linie zurückgeben.

    Returns:
        Liste der Schnittpunkte
    """
    # Linie in parametrischer Form: P = start + t * (end - start)
    dx = line.end.x - line.start.x
    dy = line.end.y - line.start.y

    fx = line.start.x - circle.center.x
    fy = line.start.y - circle.center.y

    a = dx*dx + dy*dy

    # Schutz vor Division durch Null (Linie hat keine Länge)
    if a < 1e-12:
        # Prüfen ob der Punkt auf dem Kreis liegt
        dist = math.hypot(fx, fy)
        if abs(dist - circle.radius) < 1e-6:
            return [Point2D(line.start.x, line.start.y)]
        return []

    b = 2 * (fx*dx + fy*dy)
    c = fx*fx + fy*fy - circle.radius**2

    discriminant = b*b - 4*a*c
    # Relative tolerance keeps near-tangent cases numerically stable.
    disc_tol = 1e-9 * (abs(b * b) + abs(4.0 * a * c) + 1.0)
    if discriminant < -disc_tol:
        return []
    if abs(discriminant) <= disc_tol:
        discriminant = 0.0

    points = []
    # Kleine Toleranz für Segment-Grenzen (um numerische Ungenauigkeiten zu behandeln)
    SEGMENT_TOLERANCE = 1e-6

    if discriminant == 0.0:
        t = -b / (2*a)
        # Nur hinzufügen wenn auf dem Segment (oder segment_only=False)
        if not segment_only or (-SEGMENT_TOLERANCE <= t <= 1 + SEGMENT_TOLERANCE):
            t_eval = max(0.0, min(1.0, t)) if segment_only else t
            points.append(line.point_at_parameter(t_eval))
    else:
        sqrt_disc = math.sqrt(discriminant)
        t1 = (-b - sqrt_disc) / (2*a)
        t2 = (-b + sqrt_disc) / (2*a)

        # Nur Punkte hinzufügen die auf dem Segment liegen (oder segment_only=False)
        if not segment_only or (-SEGMENT_TOLERANCE <= t1 <= 1 + SEGMENT_TOLERANCE):
            t1_eval = max(0.0, min(1.0, t1)) if segment_only else t1
            points.append(line.point_at_parameter(t1_eval))
        if not segment_only or (-SEGMENT_TOLERANCE <= t2 <= 1 + SEGMENT_TOLERANCE):
            t2_eval = max(0.0, min(1.0, t2)) if segment_only else t2
            points.append(line.point_at_parameter(t2_eval))

    return points


def circle_circle_intersection(c1: 'Circle2D', c2: 'Circle2D',
                                   tolerance: float = 1e-6) -> List['Point2D']:
    """
    Robuste Kreis-Kreis Intersection mit Tangent-Handling.

    Fixes gegenüber V1:
    - Toleranz für Tangent-Fälle (d ≈ r1+r2 oder d ≈ |r1-r2|)
    - Numerisch stabil bei fast-konzentrischen Kreisen
    - Gibt genau 1 Punkt bei Tangenz zurück

    Args:
        c1: Erster Kreis
        c2: Zweiter Kreis
        tolerance: Toleranz für Tangent-Detection (Standard: 1e-6)

    Returns:
        Liste von Schnittpunkten (0, 1, oder 2 Punkte)
    """
    dx = c2.center.x - c1.center.x
    dy = c2.center.y - c1.center.y
    d = math.hypot(dx, dy)
    r1, r2 = c1.radius, c2.radius

    # Konzentrisch (mit Toleranz) - keine Schnittpunkte
    if d < tolerance:
        return []

    # Extern tangent: d ≈ r1 + r2
    if abs(d - (r1 + r2)) < tolerance:
        t = r1 / d
        return [Point2D(c1.center.x + t * dx, c1.center.y + t * dy)]

    # Intern tangent: d ≈ |r1 - r2|
    if abs(d - abs(r1 - r2)) < tolerance:
        # Punkt liegt auf der Verbindungslinie, in Richtung des größeren Kreises
        if r1 >= r2:
            t = r1 / d
        else:
            t = -r1 / d
        return [Point2D(c1.center.x + t * dx, c1.center.y + t * dy)]

    # Disjunkt (außen)
    if d > r1 + r2:
        return []

    # Einer im anderen (kein Schnitt)
    if d < abs(r1 - r2):
        return []

    # Standard 2-Punkt Lösung (Radical Axis Methode)
    a = (r1**2 - r2**2 + d**2) / (2 * d)
    h_sq = r1**2 - a**2

    if h_sq < 0:
        return []

    h = math.sqrt(h_sq)

    # Punkt auf der Verbindungslinie
    px = c1.center.x + a * dx / d
    py = c1.center.y + a * dy / d

    # Zwei Schnittpunkte senkrecht zur Verbindungslinie
    return [
        Point2D(px + h * dy / d, py - h * dx / d),
        Point2D(px - h * dy / d, py + h * dx / d)
    ]


def get_circle_circle_intersection(c1: 'Circle2D', c2: 'Circle2D') -> List['Point2D']:
    """
    Kreis-Kreis Intersection mit robustem Tangent-Handling.

    Wrapper für circle_circle_intersection() für Abwärtskompatibilität.
    """
    return circle_circle_intersection(c1, c2)


def is_point_on_arc(point: 'Point2D', arc: 'Arc2D', tolerance: float = 1e-4) -> bool:
    """Prüft, ob ein Punkt winkeltechnisch auf dem Bogen liegt."""
    import math

    # 1. Radius-Check (Grobfilter)
    if abs(point.distance_to(arc.center) - arc.radius) > tolerance:
        return False

    # 2. Winkel berechnen (in Grad, da Arc2D Winkel in Grad speichert)
    angle = math.degrees(math.atan2(point.y - arc.center.y, point.x - arc.center.x))
    if angle < 0: angle += 360.0

    start = arc.start_angle % 360.0
    end = arc.end_angle % 360.0

    # Winkel-Toleranz in Grad
    angle_tol = math.degrees(tolerance) if tolerance < 1.0 else tolerance

    # 3. Bereichsprüfung (Handling für 0°-Übergang)
    if start <= end:
        return start - angle_tol <= angle <= end + angle_tol
    else:
        # Bogen geht über 0° hinweg (z.B. 350° bis 10°)
        return angle >= start - angle_tol or angle <= end + angle_tol

def arc_line_intersection(arc: 'Arc2D', line: 'Line2D') -> List['Point2D']:
    """Schnitt Arc-Linie: Berechnet Kreis-Schnitt und filtert via Winkel."""
    full_circle = Circle2D(arc.center, arc.radius)
    candidates = circle_line_intersection(full_circle, line)
    return [p for p in candidates if is_point_on_arc(p, arc)]

def arc_circle_intersection(arc: 'Arc2D', circle: 'Circle2D') -> List['Point2D']:
    """Schnitt Arc-Kreis."""
    full_circle_arc = Circle2D(arc.center, arc.radius)
    candidates = get_circle_circle_intersection(full_circle_arc, circle)
    return [p for p in candidates if is_point_on_arc(p, arc)]


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
    weight: float = 1.0  # NURBS Gewichtung (1.0 = Standard)
    
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

    def to_dict(self) -> dict:
        """Serialisiert zu Dictionary für JSON-Persistenz."""
        return {
            "type": "SplineControlPoint",
            "point": self.point.to_dict(),
            "handle_in": self.handle_in,
            "handle_out": self.handle_out,
            "smooth": self.smooth,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'SplineControlPoint':
        """Deserialisiert von Dictionary."""
        point_data = data.get("point", {})
        point = Point2D(
            x=point_data.get("x", 0.0),
            y=point_data.get("y", 0.0),
            id=point_data.get("id", ""),
            fixed=point_data.get("fixed", False),
            construction=point_data.get("construction", False),
        )
        return cls(
            point=point,
            handle_in=tuple(data.get("handle_in", (0.0, 0.0))),
            handle_out=tuple(data.get("handle_out", (0.0, 0.0))),
            smooth=data.get("smooth", True),
            weight=data.get("weight", 1.0),
        )


@dataclass
class BezierSpline:
    """Kubische Bézier-Spline mit editierbaren Tangent-Handles (Fusion360-Style)"""
    control_points: List[SplineControlPoint] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    construction: bool = False
    closed: bool = False
    _lines: List['Line2D'] = field(default_factory=list)  # Referenz auf generierte Linien

    # Performance Optimization 2.1: Spline-Kurven Caching (80-90% Reduktion!)
    _cached_lines: List['Line2D'] = field(default_factory=list, init=False, repr=False)
    _cache_hash: int = field(default=0, init=False, repr=False)
    
    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        if not isinstance(other, BezierSpline):
            return False
        return self.id == other.id
    
    def invalidate_cache(self):
        """
        Performance Optimization 2.1: Invalidiert to_lines() Cache.
        Aufruf bei Control-Point-Änderungen (Drag, Edit).
        """
        self._cache_hash = 0
        self._cached_lines = []

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

        # Performance Optimization 2.1: Invalidiere Cache
        self.invalidate_cache()

        return cp
    
    def insert_point(self, index: int, x: float, y: float) -> SplineControlPoint:
        """Fügt einen neuen Kontrollpunkt an einem bestimmten Index ein"""
        pt = Point2D(x, y)
        cp = SplineControlPoint(point=pt)
        
        # Auto-Tangenten basierend auf Nachbarpunkten
        if 0 < index < len(self.control_points):
            prev = self.control_points[index-1]
            next_cp = self.control_points[index]
            
            # Punkt liegt wsl. zwischen prev und next
            # Tangenten: 1/3 der Strecke zum Nachbarn
            dx_prev = (x - prev.point.x) / 3
            dy_prev = (y - prev.point.y) / 3
            cp.handle_in = (-dx_prev, -dy_prev)
            
            dx_next = (next_cp.point.x - x) / 3
            dy_next = (next_cp.point.y - y) / 3
            cp.handle_out = (dx_next, dy_next)
        
        elif index > 0:
            # Am Ende einfügen -> analog add_point
            prev = self.control_points[index-1]
            dx = (prev.point.x - x) / 3
            dy = (prev.point.y - y) / 3
            cp.handle_in = (dx, dy)
            cp.handle_out = (-dx, -dy)
            
        elif index == 0 and len(self.control_points) > 0:
             # Am Anfang einfügen
             next_cp = self.control_points[0]
             dx = (next_cp.point.x - x) / 3
             dy = (next_cp.point.y - y) / 3
             cp.handle_out = (dx, dy)
             cp.handle_in = (-dx, -dy)

        self.control_points.insert(index, cp)
        self.invalidate_cache()
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
            
            # Rational Bezier (NURBS-like) Weights
            w0 = p0.weight
            w3 = p1.weight
            # Tangenten-Gewichte: Üblicherweise 1.0 oder gemittelt, wir nehmen hier einfach 1.0 für smooth
            # Für "echte" NURBS bräuchten wir Gewichte für innere Kontrollpunkte.
            # Bei kubischen Beziers sind P1, P2 aber nur Handles.
            # Wir interpolieren die Gewichte linear für die Handles, damit der Übergang weich ist.
            w1 = (2*w0 + w3) / 3
            w2 = (w0 + 2*w3) / 3

            # Punkte auf dem Segment
            for j in range(segments_per_span + 1):
                t = j / segments_per_span
                mt = 1 - t
                
                # Basis-Funktionen
                b0 = mt*mt*mt
                b1 = 3*mt*mt*t
                b2 = 3*mt*t*t
                b3 = t*t*t
                
                # Zähler (Weighted Points)
                num_x = b0*w0*x0 + b1*w1*x1 + b2*w2*x2 + b3*w3*x3
                num_y = b0*w0*y0 + b1*w1*y1 + b2*w2*y2 + b3*w3*y3
                
                # Nenner (Weights)
                den = b0*w0 + b1*w1 + b2*w2 + b3*w3
                
                if abs(den) < 1e-9:
                    x, y = x0, y0
                else:
                    x = num_x / den
                    y = num_y / den
                
                # Duplikate vermeiden
                if not points or (abs(x - points[-1][0]) > 1e-6 or abs(y - points[-1][1]) > 1e-6):
                    points.append((x, y))
        
        return points
    
    def to_lines(self, segments_per_span: int = 10) -> List[Line2D]:
        """
        Konvertiert Spline zu Linien-Approximation.

        Performance Optimization 2.1: Cached mit Hash der Control-Points (80-90% Reduktion!)
        """
        # Hash der Control-Points berechnen (Positionen + Handles)
        hash_components = []
        for cp in self.control_points:
            hash_components.extend([cp.point.x, cp.point.y, *cp.handle_in, *cp.handle_out])
        hash_components.append(segments_per_span)
        hash_components.append(self.closed)

        current_hash = hash(tuple(hash_components))

        # Cache-Hit?
        if self._cache_hash == current_hash and self._cached_lines:
            return self._cached_lines

        # Cache-Miss: Neu berechnen
        pts = self.get_curve_points(segments_per_span)
        lines = []
        for i in range(len(pts) - 1):
            p1 = Point2D(pts[i][0], pts[i][1])
            p2 = Point2D(pts[i+1][0], pts[i+1][1])
            line = Line2D(p1, p2)
            line.construction = self.construction
            lines.append(line)

        # Cache speichern
        self._cached_lines = lines
        self._cache_hash = current_hash

        return lines

    def get_curvature_comb(self, num_samples: int = 100, scale: float = 1.0) -> List[Tuple[Point2D, Point2D, float]]:
        """
        Berechnet Daten für Curvature Comb Visualisierung.
        """
        # Wir nutzen die existierende Tesselierung
        # Ungefähr num_samples erreichen
        spans = max(1, len(self.control_points) - 1)
        segs = max(5, int(num_samples / spans))
        points = self.get_curve_points(segments_per_span=segs)
        
        if len(points) < 3:
            return []
            
        comb_data = []
        
        for i in range(len(points)):
            p = points[i] # tuple (x, y)
            
            # Neighbors
            prev_p = points[max(0, i-1)]
            next_p = points[min(len(points)-1, i+1)]
            
            # Boundary conditions (forward/backward diff)
            if i == 0:
                p0, p1, p2 = p, next_p, points[min(len(points)-1, i+2)]
            elif i == len(points) - 1:
                p0, p1, p2 = points[max(0, i-2)], prev_p, p
            else:
                p0, p1, p2 = prev_p, p, next_p
                
            x0, y0 = p0
            x1, y1 = p1
            x2, y2 = p2
            
            # Centered first derivative at p1
            dx = (x2 - x0) / 2
            dy = (y2 - y0) / 2
            
            # Second derivative at p1
            ddx = x2 - 2*x1 + x0
            ddy = y2 - 2*y1 + y0
            
            denom = math.pow(dx*dx + dy*dy, 1.5)
            if denom < 1e-9:
                k = 0
            else:
                k = (dx * ddy - dy * ddx) / denom
                
            # Normal vector
            len_n = math.hypot(dx, dy)
            if len_n < 1e-9:
                nx, ny = 0, 1
            else:
                nx = -dy / len_n
                ny = dx / len_n
                
            px, py = points[i]
            
            vis_len = k * scale * 1000 
            
            end_x = px + nx * vis_len
            end_y = py + ny * vis_len
            
            comb_data.append((Point2D(px, py), Point2D(end_x, end_y), k))
            
        return comb_data

    def to_dict(self) -> dict:
        """
        Serialisiert zu Dictionary für JSON-Persistenz.
        Speichert alle Control Points mit Handles und Einstellungen.
        """
        return {
            "type": "BezierSpline",
            "id": self.id,
            "construction": self.construction,
            "closed": self.closed,
            "control_points": [cp.to_dict() for cp in self.control_points],
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'BezierSpline':
        """
        Deserialisiert von Dictionary für JSON-Persistenz.
        Stellt alle Control Points mit Handles wieder her.
        """
        control_points = []
        for cp_data in data.get("control_points", []):
            control_points.append(SplineControlPoint.from_dict(cp_data))

        spline = cls(
            control_points=control_points,
            id=data.get("id", ""),
            construction=data.get("construction", False),
            closed=data.get("closed", False),
        )

        # Cache invalidieren nach Deserialisierung
        spline.invalidate_cache()

        return spline


@dataclass
class Spline2D:
    """
    Native B-Spline/NURBS Kurve für DXF-Import und saubere Extrusion.

    Im Gegensatz zu BezierSpline (interaktiv mit Handles) speichert diese Klasse
    die mathematisch exakte B-Spline Definition aus DXF-Dateien:
    - Kontrollpunkte
    - Knotenvektor
    - Grad
    - Gewichte (optional, für NURBS)

    Beim Extrudieren wird diese direkt zu Build123d Edge.make_spline() konvertiert,
    was eine einzelne glatte Fläche erzeugt (statt vieler kleiner Polygone).
    """
    control_points: List[Tuple[float, float]] = field(default_factory=list)
    knots: List[float] = field(default_factory=list)
    degree: int = 3
    weights: List[float] = field(default_factory=list)  # Leer = nicht-rational (B-Spline)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    construction: bool = False

    # Gecachte Endpunkte für schnelles Profil-Matching
    _start_point: Optional[Point2D] = field(default=None, init=False, repr=False)
    _end_point: Optional[Point2D] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """Validiert und berechnet Endpunkte."""
        if len(self.control_points) < 2:
            return

        # Default Gewichte (alle 1.0 = B-Spline)
        if not self.weights:
            self.weights = [1.0] * len(self.control_points)

        # Grad auf max. n-1 begrenzen
        n = len(self.control_points)
        if self.degree >= n:
            self.degree = n - 1

        # Default Knotenvektor (clamped uniform)
        if not self.knots:
            self.knots = self._create_clamped_uniform_knots()

        # Endpunkte berechnen
        self._compute_endpoints()

    def _create_clamped_uniform_knots(self) -> List[float]:
        """Erstellt clamped uniform Knotenvektor."""
        n = len(self.control_points)
        p = self.degree
        m = n + p + 1
        knots = []

        for i in range(m):
            if i <= p:
                knots.append(0.0)
            elif i >= m - p - 1:
                knots.append(1.0)
            else:
                knots.append((i - p) / (n - p))

        return knots

    def _compute_endpoints(self):
        """Berechnet Start- und Endpunkt durch Spline-Evaluation."""
        if len(self.control_points) < 2:
            return

        try:
            start = self.evaluate(0.0)
            end = self.evaluate(1.0)
            self._start_point = Point2D(start[0], start[1])
            self._end_point = Point2D(end[0], end[1])
        except Exception:
            # Fallback: Erster/letzter Kontrollpunkt
            self._start_point = Point2D(self.control_points[0][0], self.control_points[0][1])
            self._end_point = Point2D(self.control_points[-1][0], self.control_points[-1][1])

    @property
    def start_point(self) -> Point2D:
        """Startpunkt der Kurve."""
        if self._start_point is None:
            self._compute_endpoints()
        return self._start_point or Point2D(0, 0)

    @property
    def end_point(self) -> Point2D:
        """Endpunkt der Kurve."""
        if self._end_point is None:
            self._compute_endpoints()
        return self._end_point or Point2D(0, 0)

    def _basis_function(self, i: int, p: int, u: float) -> float:
        """Cox-de Boor Rekursion für B-Spline Basisfunktion."""
        if p == 0:
            if self.knots[i] <= u < self.knots[i + 1]:
                return 1.0
            elif u == self.knots[i + 1] == 1.0 and self.knots[i] < 1.0:
                return 1.0
            return 0.0

        result = 0.0
        denom1 = self.knots[i + p] - self.knots[i]
        if denom1 != 0:
            result += (u - self.knots[i]) / denom1 * self._basis_function(i, p - 1, u)

        denom2 = self.knots[i + p + 1] - self.knots[i + 1]
        if denom2 != 0:
            result += (self.knots[i + p + 1] - u) / denom2 * self._basis_function(i + 1, p - 1, u)

        return result

    def evaluate(self, u: float) -> Tuple[float, float]:
        """
        Evaluiert Kurve an Parameter u ∈ [0, 1].

        Args:
            u: Parameter (0.0 = Start, 1.0 = Ende)

        Returns:
            Punkt (x, y) auf der Kurve
        """
        u = max(0.0, min(1.0, u))
        n = len(self.control_points)

        if n < 2:
            return self.control_points[0] if self.control_points else (0.0, 0.0)

        # Basisfunktionen berechnen
        N = [self._basis_function(i, self.degree, u) for i in range(n)]

        # Gewichtete Summe (NURBS Formel)
        num_x, num_y = 0.0, 0.0
        denom = 0.0

        for i in range(n):
            w = self.weights[i] if i < len(self.weights) else 1.0
            num_x += N[i] * w * self.control_points[i][0]
            num_y += N[i] * w * self.control_points[i][1]
            denom += N[i] * w

        if abs(denom) < 1e-10:
            return self.control_points[n // 2]

        return (num_x / denom, num_y / denom)

    def evaluate_points(self, num_points: int = 50) -> List[Tuple[float, float]]:
        """Evaluiert Kurve an gleichmäßig verteilten Parametern."""
        points = []
        for i in range(num_points):
            u = i / (num_points - 1) if num_points > 1 else 0.0
            points.append(self.evaluate(u))
        return points

    def to_polyline_points(self, tolerance: float = 0.01) -> List[Tuple[float, float]]:
        """
        Konvertiert zu Polyline mit adaptiver Auflösung.
        Mehr Punkte in stark gekrümmten Bereichen.
        """
        # Einfache Version: Gleichmäßige Verteilung basierend auf Grad und Kontrollpunkten
        num_points = max(50, len(self.control_points) * 10)
        return self.evaluate_points(num_points)

    def to_build123d_edge(self, plane=None):
        """
        Konvertiert zu Build123d Edge für saubere Extrusion.

        Args:
            plane: Build123d Plane für 3D-Konvertierung (optional)

        Returns:
            Build123d Edge Objekt
        """
        try:
            from OCP.Geom import Geom_BSplineCurve
            from OCP.TColgp import TColgp_Array1OfPnt
            from OCP.TColStd import TColStd_Array1OfReal, TColStd_Array1OfInteger
            from OCP.gp import gp_Pnt
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
            from build123d import Edge

            n = len(self.control_points)

            # Poles (Kontrollpunkte) - Z=0 für 2D
            poles = TColgp_Array1OfPnt(1, n)
            for i, (x, y) in enumerate(self.control_points):
                if plane:
                    pt_3d = plane.from_local_coords((x, y))
                    poles.SetValue(i + 1, gp_Pnt(pt_3d.X, pt_3d.Y, pt_3d.Z))
                else:
                    poles.SetValue(i + 1, gp_Pnt(x, y, 0))

            # Weights
            weights = TColStd_Array1OfReal(1, n)
            for i, w in enumerate(self.weights):
                weights.SetValue(i + 1, w)

            # Knots + Multiplicities
            unique_knots = sorted(set(self.knots))
            multiplicities = [self.knots.count(k) for k in unique_knots]

            knots_arr = TColStd_Array1OfReal(1, len(unique_knots))
            mults_arr = TColStd_Array1OfInteger(1, len(unique_knots))

            for i, (k, m) in enumerate(zip(unique_knots, multiplicities)):
                knots_arr.SetValue(i + 1, k)
                mults_arr.SetValue(i + 1, m)

            # BSpline Kurve erstellen
            curve = Geom_BSplineCurve(poles, weights, knots_arr, mults_arr, self.degree)
            return Edge.make_edge(curve)

        except ImportError:
            # Fallback: Polyline
            pts = self.to_polyline_points(tolerance=0.01)
            return Edge.make_polyline([
                (p[0], p[1], 0) for p in pts
            ])



    def to_lines(self, segments: int = 50) -> List[Line2D]:
        """
        Fallback: Konvertiert zu Linien-Approximation.
        Nur verwenden wenn native Spline-Extrusion nicht möglich.
        """
        pts = self.evaluate_points(segments)
        lines = []
        for i in range(len(pts) - 1):
            p1 = Point2D(pts[i][0], pts[i][1])
            p2 = Point2D(pts[i + 1][0], pts[i + 1][1])
            if p1.distance_to(p2) > 1e-6:
                line = Line2D(p1, p2)
                line.construction = self.construction
                lines.append(line)
        return lines

    def to_dict(self) -> dict:
        """Serialisiert zu Dictionary für JSON."""
        return {
            "type": "Spline2D",
            "control_points": list(self.control_points),
            "knots": list(self.knots),
            "degree": self.degree,
            "weights": list(self.weights),
            "id": self.id,
            "construction": self.construction,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Spline2D':
        """Deserialisiert von Dictionary."""
        return cls(
            control_points=[tuple(p) for p in data.get("control_points", [])],
            knots=data.get("knots", []),
            degree=data.get("degree", 3),
            weights=data.get("weights", []),
            id=data.get("id", ""),
            construction=data.get("construction", False),
        )

    def __repr__(self):
        return f"Spline2D({len(self.control_points)} pts, deg={self.degree})"


def get_param_on_entity(point: 'Point2D', entity) -> float:
    """
    Gibt einen Sortier-Parameter zurück:
    - Linie: 0.0 (Start) bis 1.0 (Ende)
    - Kreis: 0.0 bis 2*PI (Winkel)
    - Bogen: 0.0 bis 2*PI (absoluter Winkel)
    """
    import math
    
    if isinstance(entity, Line2D):
        # Projeziere Punkt auf Linie und berechne t (0..1)
        dx = entity.end.x - entity.start.x
        dy = entity.end.y - entity.start.y
        if dx == 0 and dy == 0: return 0.0
        
        # Vektor Start->Punkt
        vkx = point.x - entity.start.x
        vky = point.y - entity.start.y
        
        # Skalarprodukt für Projektion
        t = (vkx * dx + vky * dy) / (dx*dx + dy*dy)
        return t

    elif isinstance(entity, Circle2D):
        # Winkel berechnen
        angle = math.atan2(point.y - entity.center.y, point.x - entity.center.x)
        if angle < 0: angle += 2 * math.pi
        return angle

    elif isinstance(entity, Arc2D):
        # Arc nutzt denselben Winkelparameter wie Circle.
        # Die Arc-Begrenzung wird separat in Arc-Logik geprüft.
        angle = math.atan2(point.y - entity.center.y, point.x - entity.center.x)
        if angle < 0:
            angle += 2 * math.pi
        return angle
        
    return 0.0
