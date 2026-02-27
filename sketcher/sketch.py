"""
LiteCAD Sketcher - Sketch Object
Fasst Geometrie und Constraints zusammen
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum, auto
import uuid
import math
from loguru import logger

from .geometry import (
    Point2D, Line2D, Circle2D, Arc2D, Ellipse2D, Rectangle2D,
    line_line_intersection, points_are_coincident,
    BezierSpline, SplineControlPoint, Spline2D
)
from .constraints import (
    Constraint, ConstraintType, ConstraintStatus,
    make_fixed, make_coincident, make_horizontal, make_vertical,
    make_parallel, make_perpendicular, make_equal_length,
    make_length, make_distance, make_radius, make_diameter,
    make_angle, make_point_on_line, make_midpoint,
    is_constraint_satisfied
)
from .solver import ConstraintSolver, SolverResult


class SketchState(Enum):
    """Status des Sketches"""
    EDITING = auto()      # Aktiv, wird bearbeitet
    CLOSED = auto()       # Abgeschlossen
    INVALID = auto()      # Ungültig (z.B. offene Konturen)


@dataclass
class Sketch:
    """
    2D-Sketch mit Geometrie und Constraints

    Ein Sketch liegt auf einer Ebene und enthält:
    - 2D-Geometrie (Punkte, Linien, Kreise, Bögen, Splines)
    - Constraints (geometrische Beziehungen)
    - Kann zu einem geschlossenen Profil werden für 3D-Operationen

    TNP v4.1: Jede Geometrie-Komponente hat eine eindeutige shape_uuid
    für persistente Referenzierung über Sketch-Modifikationen hinweg.
    """

    name: str = "Sketch"
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # TNP v4.1: ShapeUUIDs für Sketch-Geometrie (persistent über Sketch-Änderungen)
    _point_shape_uuids: Dict[str, str] = field(default_factory=dict)  # point.id -> shape_uuid
    _line_shape_uuids: Dict[str, str] = field(default_factory=dict)  # line.id -> shape_uuid
    _circle_shape_uuids: Dict[str, str] = field(default_factory=dict)  # circle.id -> shape_uuid
    _arc_shape_uuids: Dict[str, str] = field(default_factory=dict)     # arc.id -> shape_uuid
    _ellipse_shape_uuids: Dict[str, str] = field(default_factory=dict)  # ellipse.id -> shape_uuid
    _spline_shape_uuids: Dict[str, str] = field(default_factory=dict)  # spline.id -> shape_uuid

    # Geometrie
    points: List[Point2D] = field(default_factory=list)
    lines: List[Line2D] = field(default_factory=list)
    circles: List[Circle2D] = field(default_factory=list)
    arcs: List[Arc2D] = field(default_factory=list)
    ellipses: List['Ellipse2D'] = field(default_factory=list)  # Native Ellipsen (TNP v4.1)
    splines: List['BezierSpline'] = field(default_factory=list)  # Bézier-Splines (interaktiv)
    native_splines: List['Spline2D'] = field(default_factory=list)  # B-Splines aus DXF (exakt)

    # Constraints
    constraints: List[Constraint] = field(default_factory=list)

    # Status
    state: SketchState = SketchState.EDITING
    
    # Ebene (später: 3D-Ebene)
    plane_origin: Tuple[float, float, float] = (0, 0, 0)
    plane_normal: Tuple[float, float, float] = (0, 0, 1)  # XY-Ebene
    plane_x_dir: Tuple[float, float, float] = (1, 0, 0)
    plane_y_dir: Tuple[float, float, float] = (0, 1, 0)

    # Solver
    _solver: ConstraintSolver = field(default_factory=ConstraintSolver)

    # Performance: Profil-Cache + Adjacency-Map
    _profiles_valid: bool = field(default=False, repr=False)
    _cached_profiles: list = field(default_factory=list, repr=False)
    _adjacency: dict = field(default_factory=dict, repr=False) # {(rx,ry): [line, ...]}
    _ellipse_bundles: List[dict] = field(default_factory=list, repr=False)

    # === TNP v4.1: Sketch-ShapeUUID Verwaltung ===

    def normalize_plane_basis(self) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
        """
        Normalisiert die Sketch-Ebenenbasis auf ein stabiles orthonormales Frame.
        """
        from modeling.geometry_utils import normalize_plane_axes

        normal, x_dir, y_dir = normalize_plane_axes(
            getattr(self, 'plane_normal', (0, 0, 1)),
            getattr(self, 'plane_x_dir', None),
            getattr(self, 'plane_y_dir', None),
        )
        self.plane_normal = normal
        self.plane_x_dir = x_dir
        self.plane_y_dir = y_dir
        return normal, x_dir, y_dir

    def get_all_shape_uuids(self) -> Dict[str, str]:
        """
        Gibt alle ShapeUUIDs der Sketch-Geometrie zurück.

        Returns:
            Dict mit Komponente-Typ als Key und Liste von UUIDs
        """
        uuids = {
            'points': [sid for sid in self._point_shape_uuids.values()],
            'lines': [sid for sid in self._line_shape_uuids.values()],
            'circles': [sid for sid in self._circle_shape_uuids.values()],
            'arcs': [sid for sid in self._arc_shape_uuids.values()],
            'ellipses': [sid for sid in self._ellipse_shape_uuids.values()],
        }
        return uuids

    def get_shape_uuid_for_element(self, element_type: str, element_id: str) -> Optional[str]:
        """
        Sucht die ShapeUUID für ein spezifisches Sketch-Element.

        Args:
            element_type: 'point', 'line', 'circle', 'arc', 'spline'
            element_id: Die ID des Elements (point.id, line.id, etc.)

        Returns:
            ShapeUUID als String oder None
        """
        type_to_map = {
            'point': self._point_shape_uuids,
            'line': self._line_shape_uuids,
            'circle': self._circle_shape_uuids,
            'arc': self._arc_shape_uuids,
            'ellipse': self._ellipse_shape_uuids,
            'spline': self._spline_shape_uuids,
        }

        uuid_map = type_to_map.get(element_type, {})
        return uuid_map.get(element_id)

    def update_shape_uuid_after_rebuild(self, feature_id: str,
                                  point_uuids: Dict[str, str] = None,
                                  line_uuids: Dict[str, str] = None,
                                  circle_uuids: Dict[str, str] = None,
                                  arc_uuids: Dict[str, str] = None,
                                  ellipse_uuids: Dict[str, str] = None) -> bool:
        """
        Aktualisiert die ShapeUUIDs nach einem Sketch-Rebuild.
        Wird vom Feature/Body aufgerufen wenn sich der Sketch geändert hat.

        Args:
            feature_id: ID des Features das den Sketch verwendet
            point_uuids: Neue UUIDs für Points
            line_uuids: Neue UUIDs für Lines
            circle_uuids: Neue UUIDs für Circles
            arc_uuids: Neue UUIDs für Arcs
            ellipse_uuids: Neue UUIDs für Ellipses (TNP v4.1)

        Returns:
            True wenn mindestens eine UUID aktualisiert wurde
        """
        updated = False

        if point_uuids:
            self._point_shape_uuids.update(point_uuids)
            updated = True
        if line_uuids:
            self._line_shape_uuids.update(line_uuids)
            updated = True
        if circle_uuids:
            self._circle_shape_uuids.update(circle_uuids)
            updated = True
        if arc_uuids:
            self._arc_shape_uuids.update(arc_uuids)
            updated = True
        if ellipse_uuids:
            self._ellipse_shape_uuids.update(ellipse_uuids)
            updated = True

        return updated

    # === Geometrie-Erstellung ===
    
    def add_point(self, x: float, y: float, construction: bool = False) -> Point2D:
        """Fügt einen standalone Punkt hinzu"""
        from modeling.tnp_system import ShapeID, ShapeType
        import uuid

        point = Point2D(x, y, construction=construction, standalone=True)

        # TNP v4.1: ShapeUUID für diesen Punkt generieren
        if not hasattr(self, '_point_shape_uuids'):
            self._point_shape_uuids = {}
        point_shape_id = ShapeID(
            uuid=str(uuid.uuid4())[:8],
            shape_type=ShapeType.VERTEX,
            feature_id=f"{self.id}_point",
            local_index=len(self.points),
            geometry_hash=(x, y)  # 2D-Punkt als Hash
        )
        self._point_shape_uuids[point.id] = point_shape_id.uuid

        self.points.append(point)
        return point
    
    def add_line(self, x1: float, y1: float, x2: float, y2: float,
                 construction: bool = False, tolerance: float = 1.0) -> Line2D:
        """Fügt eine Linie hinzu. Verwendet existierende Punkte wenn möglich."""
        from modeling.tnp_system import ShapeID, ShapeType
        import uuid

        # Prüfe ob es schon Punkte an diesen Positionen gibt
        start = self._find_or_create_point(x1, y1, tolerance)
        end = self._find_or_create_point(x2, y2, tolerance)

        line = Line2D(start, end, construction=construction)

        # TNP v4.1: ShapeUUID für diese Linie generieren
        if not hasattr(self, '_line_shape_uuids'):
            self._line_shape_uuids = {}

        line_shape_id = ShapeID(
            uuid=str(uuid.uuid4())[:8],
            shape_type=ShapeType.EDGE,
            feature_id=f"{self.id}_line",
            local_index=len(self.lines),
            geometry_hash=(x1, y1, x2, y2)  # 4x float für Hash
        )
        self._line_shape_uuids[line.id] = line_shape_id.uuid

        self.lines.append(line)
        self.invalidate_profiles()
        return line
    
    def _find_or_create_point(self, x: float, y: float, tolerance: float = 1.0) -> Point2D:
        """Findet einen existierenden Punkt oder erstellt einen neuen."""
        # Suche in allen Punktquellen
        for point in self.points:
            if abs(point.x - x) < tolerance and abs(point.y - y) < tolerance:
                return point
        
        # Suche auch in Linien-Endpunkten (falls nicht in points)
        for line in self.lines:
            if abs(line.start.x - x) < tolerance and abs(line.start.y - y) < tolerance:
                if line.start not in self.points:
                    self.points.append(line.start)
                return line.start
            if abs(line.end.x - x) < tolerance and abs(line.end.y - y) < tolerance:
                if line.end not in self.points:
                    self.points.append(line.end)
                return line.end
        
        # Neuen Punkt erstellen
        new_point = Point2D(x, y)
        self.points.append(new_point)
        return new_point
    
    def add_line_from_points(self, p1: Point2D, p2: Point2D,
                             construction: bool = False) -> Line2D:
        """Fügt eine Linie zwischen existierenden Punkten hinzu"""
        line = Line2D(p1, p2, construction=construction)
        self.lines.append(line)
        self.invalidate_profiles()
        return line
    
    def add_circle(self, cx: float, cy: float, radius: float,
                   construction: bool = False) -> Circle2D:
        """Fügt einen Kreis hinzu

        TNP v4.1: Speichert native OCP Daten für optimale Extrusion (3 Faces statt 14+).
        """
        from modeling.tnp_system import ShapeID, ShapeType
        import uuid

        self.normalize_plane_basis()

        center = Point2D(cx, cy)
        circle = Circle2D(center, radius, construction=construction)

        # TNP v4.1: Native OCP Daten für optimierte Extrusion speichern
        circle.native_ocp_data = {
            'center': (cx, cy),
            'radius': radius,
            'plane': {
                'origin': self.plane_origin,
                'normal': self.plane_normal,
                'x_dir': self.plane_x_dir,
                'y_dir': self.plane_y_dir,
            }
        }

        # TNP v4.1: ShapeUUID für diesen Kreis generieren
        if not hasattr(self, '_circle_shape_uuids'):
            self._circle_shape_uuids = {}

        circle_shape_id = ShapeID(
            uuid=str(uuid.uuid4())[:8],
            shape_type=ShapeType.EDGE,  # Kreis ist eine geschlossene Edge
            feature_id=f"{self.id}_circle",
            local_index=len(self.circles),
            geometry_hash=(cx, cy, radius)  # Center + Radius als Hash
        )
        self._circle_shape_uuids[circle.id] = circle_shape_id.uuid

        self.points.append(center)
        self.circles.append(circle)
        return circle
    
    def add_arc(self, cx: float, cy: float, radius: float,
                start_angle: float, end_angle: float,
                construction: bool = False) -> Arc2D:
        """Fügt einen Bogen hinzu

        TNP v4.1: Speichert native OCP Daten für optimierte Extrusion.
        Arcs werden direkt als native OCP Arc Faces extrudiert
        statt als Polygon-Approximation.
        """
        from modeling.tnp_system import ShapeID, ShapeType
        import uuid

        self.normalize_plane_basis()

        center = Point2D(cx, cy)
        arc = Arc2D(center, radius, start_angle, end_angle, construction=construction)

        # TNP v4.1: Native OCP Daten für optimierte Extrusion speichern
        arc.native_ocp_data = {
            'center': (cx, cy),
            'radius': radius,
            'start_angle': start_angle,
            'end_angle': end_angle,
            'plane': {
                'origin': self.plane_origin,
                'normal': self.plane_normal,
                'x_dir': self.plane_x_dir,
                'y_dir': self.plane_y_dir,
            }
        }

        # TNP v4.1: ShapeUUID für diesen Bogen generieren
        if not hasattr(self, '_arc_shape_uuids'):
            self._arc_shape_uuids = {}

        arc_shape_id = ShapeID(
            uuid=str(uuid.uuid4())[:8],
            shape_type=ShapeType.EDGE,  # Arc ist eine Edge
            feature_id=f"{self.id}_arc",
            local_index=len(self.arcs),
            geometry_hash=(cx, cy, radius, start_angle, end_angle)  # Vollständige Signatur
        )
        self._arc_shape_uuids[arc.id] = arc_shape_id.uuid

        self.points.append(center)
        self.arcs.append(arc)
        return arc

    def add_ellipse(self, cx: float, cy: float, major_radius: float, minor_radius: float,
                    angle_deg: float = 0.0, construction: bool = False) -> Ellipse2D:
        """
        Fügt eine native Ellipse hinzu (TNP v4.1).
        
        Die Ellipse wird als echtes geometrisches Objekt gespeichert (nicht als
        Liniensegmente). Dies ermöglicht:
        - Glatte Rendering ohne Sichtbare Segmente
        - Native OCP Extrusion mit glatter Fläche
        - Professionelles CAD-Verhalten wie Fusion 360
        
        Args:
            cx, cy: Zentrum der Ellipse
            major_radius: Länge der Hauptachse (Radius)
            minor_radius: Länge der Nebenachse (Radius)
            angle_deg: Rotation der Hauptachse in Grad
            construction: True für Konstruktionsgeometrie
        
        Returns:
            Ellipse2D: Die erstellte native Ellipse
        """
        from modeling.tnp_system import ShapeID, ShapeType
        import uuid
        
        self.normalize_plane_basis()

        major_radius = max(0.01, float(major_radius))
        minor_radius = max(0.01, float(minor_radius))
        angle = float(angle_deg)
        
        # Native Ellipse erstellen
        center = Point2D(cx, cy)
        ellipse = Ellipse2D(
            center=center,
            radius_x=major_radius,
            radius_y=minor_radius,
            rotation=angle,
            construction=construction
        )
        
        # TNP v4.1: Native OCP Daten für optimierte Extrusion
        ellipse.native_ocp_data = {
            'center': (cx, cy),
            'radius_x': major_radius,
            'radius_y': minor_radius,
            'rotation': angle,
            'plane': {
                'origin': self.plane_origin,
                'normal': self.plane_normal,
                'x_dir': self.plane_x_dir,
                'y_dir': self.plane_y_dir,
            }
        }
        
        # TNP v4.1: ShapeUUID für diese Ellipse generieren
        if not hasattr(self, '_ellipse_shape_uuids'):
            self._ellipse_shape_uuids = {}
        
        ellipse_shape_id = ShapeID(
            uuid=str(uuid.uuid4())[:8],
            shape_type=ShapeType.EDGE,  # Ellipse ist eine Edge
            feature_id=f"{self.id}_ellipse",
            local_index=len(self.ellipses),
            geometry_hash=(cx, cy, major_radius, minor_radius, angle)
        )
        self._ellipse_shape_uuids[ellipse.id] = ellipse_shape_id.uuid
        
        # Zur Sketch-Geometrie hinzufügen
        self.ellipses.append(ellipse)
        
        # Konstruktions-Geometrie: Achsenlinien und Center-Point (für UI)
        if not construction:
            # Achsen-Endpunkte berechnen
            angle_rad = math.radians(angle)
            ux = math.cos(angle_rad)
            uy = math.sin(angle_rad)
            vx = -uy
            vy = ux
            
            center_pt = Point2D(cx, cy, construction=True)
            major_pos = Point2D(cx + ux * major_radius, cy + uy * major_radius, construction=True)
            major_neg = Point2D(cx - ux * major_radius, cy - uy * major_radius, construction=True)
            minor_pos = Point2D(cx + vx * minor_radius, cy + vy * minor_radius, construction=True)
            minor_neg = Point2D(cx - vx * minor_radius, cy - vy * minor_radius, construction=True)
            
            # WICHTIG: Markiere Achsen-Endpunkte als "handle" für bessere Selektion
            center_pt._ellipse_handle = "center"
            center_pt._parent_ellipse = ellipse
            major_pos._ellipse_handle = "major_pos"
            major_pos._parent_ellipse = ellipse
            major_neg._ellipse_handle = "major_neg"
            major_neg._parent_ellipse = ellipse
            minor_pos._ellipse_handle = "minor_pos"
            minor_pos._parent_ellipse = ellipse
            minor_neg._ellipse_handle = "minor_neg"
            minor_neg._parent_ellipse = ellipse
            
            self.points.extend([center_pt, major_pos, major_neg, minor_pos, minor_neg])
            
            major_axis = Line2D(major_neg, major_pos, construction=True)
            minor_axis = Line2D(minor_neg, minor_pos, construction=True)
            
            # Achsen mit Ellipse verbinden (Bundle-System für Updates)
            major_axis._ellipse_axis = "major"
            major_axis._ellipse_bundle = ellipse
            minor_axis._ellipse_axis = "minor"
            minor_axis._ellipse_bundle = ellipse
            
            self.lines.extend([major_axis, minor_axis])
            
            # Achsen-Constraints (Fusion-like)
            self.add_midpoint(center_pt, major_axis)
            self.add_midpoint(center_pt, minor_axis)
            self.add_perpendicular(major_axis, minor_axis)
            self.add_length(major_axis, 2.0 * major_radius)
            self.add_length(minor_axis, 2.0 * minor_radius)
            
            # Referenz für späteres Editieren
            ellipse._center_point = center_pt
            ellipse._major_axis = major_axis
            ellipse._minor_axis = minor_axis
            ellipse._major_pos = major_pos
            ellipse._major_neg = major_neg
            ellipse._minor_pos = minor_pos
            ellipse._minor_neg = minor_neg
        
        self.invalidate_profiles()
        return ellipse
    
    def add_rectangle(self, x: float, y: float, width: float, height: float, construction: bool = False) -> List[Line2D]:
        """Fügt ein Rechteck hinzu (4 Linien mit geteilten Eckpunkten)"""
        # 4 Eckpunkte erstellen
        p1 = self.add_point(x, y, construction)               # Unten links
        p2 = self.add_point(x + width, y, construction)       # Unten rechts
        p3 = self.add_point(x + width, y + height, construction) # Oben rechts
        p4 = self.add_point(x, y + height, construction)      # Oben links

        # Rectangle-Eckpunkte gehören zur Geometrie und dürfen beim Löschen
        # nicht als explizite Standalone-Punkte übrig bleiben.
        p1.standalone = False
        p2.standalone = False
        p3.standalone = False
        p4.standalone = False
        
        # 4 Linien verbinden
        l1 = self.add_line_from_points(p1, p2, construction) # Unten
        l2 = self.add_line_from_points(p2, p3, construction) # Rechts
        l3 = self.add_line_from_points(p3, p4, construction) # Oben
        l4 = self.add_line_from_points(p4, p1, construction) # Links
        
        # Constraints: Geometrisch (Form erhalten)
        self.add_horizontal(l1)
        self.add_horizontal(l3)
        self.add_vertical(l2)
        self.add_vertical(l4)
        
        # Coincident ist implizit durch geteilte Punkte (add_line_from_points), 
        # aber Punkte müssen auch logisch verbunden bleiben im Solver.
        # Da wir 'add_line_from_points' nutzen und p1, p2 etc. wiederverwenden,
        # behandelt der Solver (Scipy) die Parameter (x,y) von p1 als geteilt.
        
        return [l1, l2, l3, l4]
    
    def add_polygon(self, points: List[Tuple[float, float]], closed: bool = True, construction: bool = False) -> List[Line2D]:
        """Fügt ein Polygon hinzu"""
        if len(points) < 2:
            return []
        
        point_objs = [Point2D(x, y) for x, y in points]
        self.points.extend(point_objs)
        
        lines = []
        for i in range(len(point_objs) - 1):
            line = Line2D(point_objs[i], point_objs[i + 1])
            line.construction = construction  # Konstruktionsmodus setzen
            lines.append(line)
            self.lines.append(line)
        
        if closed and len(point_objs) > 2:
            closing_line = Line2D(point_objs[-1], point_objs[0])
            closing_line.construction = construction
            lines.append(closing_line)
            self.lines.append(closing_line)
            self.add_coincident(closing_line.end, lines[0].start)
        
        # Ecken verbinden
        for i in range(len(lines) - 1):
            self.add_coincident(lines[i].end, lines[i + 1].start)
        
        return lines
    
    def add_regular_polygon(self, cx: float, cy: float, r: float, sides: int, angle_offset: float = 0, construction: bool = False):
        """
        Erstellt ein parametrisches reguläres Polygon.
        Basiert auf einem (unsichtbaren) Konstruktionskreis.
        """
        import math
        
        # 1. Konstruktionskreis erstellen (dieser steuert das Polygon)
        # construction=True sorgt dafür, dass er gestrichelt dargestellt wird
        circle = self.add_circle(cx, cy, r, construction=True)
        
        points = []
        lines = []
        step = 2 * math.pi / sides
        
        # 2. Punkte erstellen und auf dem Kreis fixieren
        for i in range(sides):
            angle = angle_offset + i * step
            # Startkoordinaten berechnen
            px = cx + r * math.cos(angle)
            py = cy + r * math.sin(angle)
            
            p = self.add_point(px, py, construction=construction)
            points.append(p)
            
            # WICHTIG: Constraint hinzufügen, damit der Punkt am Kreis "klebt"
            self.add_point_on_circle(p, circle)

        # 3. Linien verbinden
        for i in range(sides):
            p1 = points[i]
            p2 = points[(i + 1) % sides] # Modulo verbindet den letzten mit dem ersten

            # Hier nutzen wir add_line_from_points, damit die Punkte geteilt werden
            line = self.add_line_from_points(p1, p2, construction=construction)
            lines.append(line)

        # 4. W33: Keine Equal-Length-Constraints mehr!
        # Die Point-On-Circle-Constraints sorgen bereits dafür, dass alle Punkte
        # auf dem Kreis bleiben, was für ein reguläres Polygon ausreicht.
        # Zusätzliche Equal-Length-Constraints führten zu Überbestimmung und
        # Solver-Fehlern beim Direct-Edit.

        return lines, circle

    # === Constraint-Erstellung ===

    def _constraint_exists(self, c_type: ConstraintType, entities: list) -> bool:
        """
        Prüft ob ein Constraint mit gleichem Typ und gleichen Entities bereits existiert.
        Verhindert doppelte Constraints.
        """
        entity_ids = set(e.id for e in entities if hasattr(e, 'id'))

        for existing in self.constraints:
            if existing.type != c_type:
                continue
            existing_ids = set(e.id for e in existing.entities if hasattr(e, 'id'))
            if entity_ids == existing_ids:
                return True
        return False

    def add_fixed(self, point: Point2D) -> Optional[Constraint]:
        """Fixiert einen Punkt"""
        if self._constraint_exists(ConstraintType.FIXED, [point]):
            return None
        c = make_fixed(point)
        self.constraints.append(c)
        return c

    def add_coincident(self, p1: Point2D, p2: Point2D) -> Optional[Constraint]:
        """Lässt zwei Punkte zusammenfallen"""
        if self._constraint_exists(ConstraintType.COINCIDENT, [p1, p2]):
            return None
        c = make_coincident(p1, p2)
        self.constraints.append(c)
        return c

    def add_horizontal(self, line: Line2D) -> Optional[Constraint]:
        """Macht eine Linie horizontal"""
        if self._constraint_exists(ConstraintType.HORIZONTAL, [line]):
            return None
        c = make_horizontal(line)
        self.constraints.append(c)
        return c

    def add_vertical(self, line: Line2D) -> Optional[Constraint]:
        """Macht eine Linie vertikal"""
        if self._constraint_exists(ConstraintType.VERTICAL, [line]):
            return None
        c = make_vertical(line)
        self.constraints.append(c)
        return c

    def add_parallel(self, l1: Line2D, l2: Line2D) -> Optional[Constraint]:
        """Macht zwei Linien parallel"""
        if self._constraint_exists(ConstraintType.PARALLEL, [l1, l2]):
            return None
        c = make_parallel(l1, l2)
        self.constraints.append(c)
        return c

    def add_perpendicular(self, l1: Line2D, l2: Line2D) -> Optional[Constraint]:
        """Macht zwei Linien senkrecht"""
        if self._constraint_exists(ConstraintType.PERPENDICULAR, [l1, l2]):
            return None
        c = make_perpendicular(l1, l2)
        self.constraints.append(c)
        return c

    def add_equal_length(self, line1: Line2D, line2: Line2D) -> Optional[Constraint]:
        """Zwingt zwei Linien dazu, die gleiche Länge zu haben"""
        if self._constraint_exists(ConstraintType.EQUAL_LENGTH, [line1, line2]):
            return None
        c = Constraint(ConstraintType.EQUAL_LENGTH, [line1, line2])
        self.constraints.append(c)
        return c
    
    def add_length(self, line: Line2D, length: float) -> Optional[Constraint]:
        """Setzt die Länge einer Linie"""
        if self._constraint_exists(ConstraintType.LENGTH, [line]):
            return None
        c = make_length(line, length)
        self.constraints.append(c)
        return c

    def add_distance(self, p1: Point2D, p2: Point2D, distance: float) -> Optional[Constraint]:
        """Setzt den Abstand zwischen zwei Punkten"""
        if self._constraint_exists(ConstraintType.DISTANCE, [p1, p2]):
            return None
        c = make_distance(p1, p2, distance)
        self.constraints.append(c)
        return c

    def add_radius(self, circle: Circle2D, radius: float) -> Optional[Constraint]:
        """Setzt den Radius eines Kreises"""
        if self._constraint_exists(ConstraintType.RADIUS, [circle]):
            return None
        c = make_radius(circle, radius)
        self.constraints.append(c)
        return c

    def add_diameter(self, circle: Circle2D, diameter: float) -> Optional[Constraint]:
        """Setzt den Durchmesser eines Kreises"""
        if self._constraint_exists(ConstraintType.DIAMETER, [circle]):
            return None
        c = make_diameter(circle, diameter)
        self.constraints.append(c)
        return c

    def add_angle(self, l1: Line2D, l2: Line2D, angle: float) -> Optional[Constraint]:
        """Setzt den Winkel zwischen zwei Linien"""
        if self._constraint_exists(ConstraintType.ANGLE, [l1, l2]):
            return None
        c = make_angle(l1, l2, angle)
        self.constraints.append(c)
        return c

    def add_point_on_line(self, point: Point2D, line: Line2D) -> Optional[Constraint]:
        """Legt einen Punkt auf eine Linie"""
        if self._constraint_exists(ConstraintType.POINT_ON_LINE, [point, line]):
            return None
        c = make_point_on_line(point, line)
        self.constraints.append(c)
        return c

    def add_midpoint(self, point: Point2D, line: Line2D) -> Optional[Constraint]:
        """Legt einen Punkt auf den Mittelpunkt einer Linie"""
        if self._constraint_exists(ConstraintType.MIDPOINT, [point, line]):
            return None
        c = make_midpoint(point, line)
        self.constraints.append(c)
        return c

    def add_point_on_circle(self, point: Point2D, circle_or_arc) -> Optional[Constraint]:
        """Zwingt einen Punkt auf die Kreisbahn"""
        if self._constraint_exists(ConstraintType.POINT_ON_CIRCLE, [point, circle_or_arc]):
            return None
        c = Constraint(ConstraintType.POINT_ON_CIRCLE, entities=[point, circle_or_arc])
        self.constraints.append(c)
        return c
    
    def add_slot(self, x1: float, y1: float, x2: float, y2: float, radius: float, construction: bool = False):
        """
        Erstellt ein robustes Langloch mit Skelett-Struktur.
        Verhindert Verzerrung beim Rotieren und Radius-Edit.
        """
        import math

        # 1. Mittellinie (Konstruktion)
        p_start = self.add_point(x1, y1, construction=True)
        p_end = self.add_point(x2, y2, construction=True)
        p_start._slot_center_point = True  # Marker: nicht selektierbar
        p_end._slot_center_point = True    # Marker: nicht selektierbar
        line_center = self.add_line_from_points(p_start, p_end, construction=True)

        # Richtungsvektor fuer Offsets
        dx, dy = x2 - x1, y2 - y1
        len_sq = dx * dx + dy * dy
        if len_sq < 1e-9:
            dx, dy = 1.0, 0.0
        else:
            length = math.sqrt(len_sq)
            dx /= length
            dy /= length

        nx, ny = -dy * radius, dx * radius

        # 2. Eckpunkte
        t1 = self.add_point(x1 + nx, y1 + ny, construction=construction)
        b1 = self.add_point(x1 - nx, y1 - ny, construction=construction)
        t2 = self.add_point(x2 + nx, y2 + ny, construction=construction)
        b2 = self.add_point(x2 - nx, y2 - ny, construction=construction)
        # Marker: Slot-Eckpunkte nicht einzeln selektierbar
        t1._slot_point = True
        b1._slot_point = True
        t2._slot_point = True
        b2._slot_point = True

        # 3. Skelettlinien an den Endkappen
        cap1 = self.add_line_from_points(t1, b1, construction=True)
        cap2 = self.add_line_from_points(t2, b2, construction=True)
        cap1._slot_skeleton_line = True  # Marker: nicht selektierbar
        cap2._slot_skeleton_line = True  # Marker: nicht selektierbar

        # 4. Aussenkontur
        line_top = self.add_line_from_points(t1, t2, construction=construction)
        line_bot = self.add_line_from_points(b1, b2, construction=construction)

        # 5. Endkappen-Boegen
        angle_deg = math.degrees(math.atan2(dy, dx))
        arc1 = self.add_arc(x1, y1, radius, angle_deg + 90, angle_deg + 270, construction=construction)
        arc2 = self.add_arc(x2, y2, radius, angle_deg - 90, angle_deg + 90, construction=construction)

        # Stabilitaets-Constraints
        self.add_perpendicular(cap1, line_center)
        self.add_perpendicular(cap2, line_center)
        self.add_midpoint(p_start, cap1)
        self.add_midpoint(p_end, cap2)

        self.add_distance(p_start, t1, radius)
        self.add_distance(p_start, b1, radius)
        self.add_distance(p_end, t2, radius)
        self.add_distance(p_end, b2, radius)

        self.add_coincident(arc1.center, p_start)
        self.add_coincident(arc2.center, p_end)
        self.add_point_on_circle(t1, arc1)
        self.add_point_on_circle(b1, arc1)
        self.add_point_on_circle(t2, arc2)
        self.add_point_on_circle(b2, arc2)

        # Tangente fuer konturtreuen Uebergang
        self.add_tangent(line_top, arc1)

        # Marker fuer Winkel-Refresh nach Solve
        arc1._start_marker = t1
        arc1._end_marker = b1
        arc2._start_marker = b2
        arc2._end_marker = t2

        # W34: Marker für Slot Direct Edit
        line_center._slot_center_line = True
        line_top._slot_parent_center_line = line_center
        line_bot._slot_parent_center_line = line_center
        arc1._slot_arc = True
        arc2._slot_arc = True

        return line_center, arc1


    def _update_arc_angles(self):
        """
        Aktualisiert die Winkel von Bögen basierend auf ihren Marker-Punkten.
        Muss nach jedem solve() aufgerufen werden.

        WICHTIG: Sweep-Richtung (CCW/CW) muss beibehalten werden!
        atan2 liefert [-180°, 180°], was die Richtung ändern kann.
        """
        for arc in self.arcs:
            # Prüfen ob wir Marker für diesen Bogen gespeichert haben (siehe add_slot)
            p_start = getattr(arc, '_start_marker', None)
            p_end = getattr(arc, '_end_marker', None)

            if p_start and p_end:
                old_start = arc.start_angle
                old_end = arc.end_angle
                old_sweep = old_end - old_start

                # Vektoren vom Zentrum zu den Markern
                dx_s = p_start.x - arc.center.x
                dy_s = p_start.y - arc.center.y
                dx_e = p_end.x - arc.center.x
                dy_e = p_end.y - arc.center.y

                # Winkel berechnen (atan2 liefert [-180°, 180°])
                ang_s = math.degrees(math.atan2(dy_s, dx_s))
                ang_e = math.degrees(math.atan2(dy_e, dx_e))

                # FIX: Sweep-Richtung beibehalten!
                # Wenn ursprünglicher sweep positiv war (CCW), neuen sweep auch positiv machen
                new_sweep = ang_e - ang_s
                if old_sweep > 0 and new_sweep < 0:
                    ang_e += 360
                elif old_sweep < 0 and new_sweep > 0:
                    ang_e -= 360

                # Winkel setzen
                arc.start_angle = ang_s
                arc.end_angle = ang_e

    def _update_ellipse_geometry(self):
        """
        Synchronisiert Ellipsen-Geometrie:
        - Bei Drag: Ellipse-Parameter → Achsen (Live-Update während Drag)
        - Bei Constraint-Änderung: Achsen → Ellipse-Parameter (nach Solve)
        - Aktualisiert native_ocp_data für alle Ellipsen (Lifecycle-Support)
        """
        import math

        for ellipse in getattr(self, 'ellipses', []):
            # === Fall 1: Ellipse mit Achsen-Referenzen (via add_ellipse erstellt) ===
            if hasattr(ellipse, '_major_axis') and hasattr(ellipse, '_minor_axis'):
                # Hole aktuelle Achsen-Punkte
                major_pos = ellipse._major_axis.end
                major_neg = ellipse._major_axis.start
                minor_pos = ellipse._minor_axis.end
                minor_neg = ellipse._minor_axis.start
                center_pt = ellipse._center_point

                prev_center_x = float(ellipse.center.x)
                prev_center_y = float(ellipse.center.y)

                # Center from axis midpoint (default source of truth)
                axis_center_x = (major_pos.x + major_neg.x) / 2
                axis_center_y = (major_pos.y + major_neg.y) / 2

                # If only the center handle moved (direct drag), shift all axis points.
                handle_dx = center_pt.x - prev_center_x
                handle_dy = center_pt.y - prev_center_y
                axis_dx = axis_center_x - prev_center_x
                axis_dy = axis_center_y - prev_center_y
                handle_moved = math.hypot(handle_dx, handle_dy) > 1e-9
                axis_moved = math.hypot(axis_dx, axis_dy) > 1e-9

                if handle_moved and not axis_moved:
                    shift_x = center_pt.x - axis_center_x
                    shift_y = center_pt.y - axis_center_y
                    for pt in (major_pos, major_neg, minor_pos, minor_neg):
                        pt.x += shift_x
                        pt.y += shift_y
                    center_x = center_pt.x
                    center_y = center_pt.y
                else:
                    center_x = axis_center_x
                    center_y = axis_center_y

                # Berechne Radien aus Achsen-Längen
                major_dx = major_pos.x - major_neg.x
                major_dy = major_pos.y - major_neg.y
                major_length = math.hypot(major_dx, major_dy)
                new_rx = major_length / 2

                minor_dx = minor_pos.x - minor_neg.x
                minor_dy = minor_pos.y - minor_neg.y
                minor_length = math.hypot(minor_dx, minor_dy)
                new_ry = minor_length / 2

                # Berechne Rotation aus Major-Achse
                new_rotation = math.degrees(math.atan2(major_dy, major_dx))

                # Update Ellipse-Parameter (aus Achsen berechnet)
                ellipse.center.x = center_x
                ellipse.center.y = center_y
                ellipse.radius_x = max(0.01, new_rx)
                ellipse.radius_y = max(0.01, new_ry)
                ellipse.rotation = new_rotation

                # Keep center handle in sync with computed center
                center_pt.x = center_x
                center_pt.y = center_y

            # === Fall 2: Ellipse ohne Achsen-Referenzen (z.B. nach Deserialisierung) ===
            else:
                # Ellipse-Parameter direkt aktualisieren (nichts zu tun, Werte sind aktuell)
                center_x = ellipse.center.x
                center_y = ellipse.center.y
                new_rx = ellipse.radius_x
                new_ry = ellipse.radius_y
                new_rotation = ellipse.rotation

            # === native_ocp_data für ALLE Ellipsen aktualisieren (Lifecycle-Support) ===
            if ellipse.native_ocp_data:
                ellipse.native_ocp_data['center'] = (center_x, center_y)
                ellipse.native_ocp_data['radius_x'] = new_rx
                ellipse.native_ocp_data['radius_y'] = new_ry
                ellipse.native_ocp_data['rotation'] = new_rotation
            else:
                # Wenn native_ocp_data noch nicht existiert, jetzt erstellen
                ellipse.native_ocp_data = {
                    'center': (center_x, center_y),
                    'radius_x': new_rx,
                    'radius_y': new_ry,
                    'rotation': new_rotation,
                    'plane': {
                        'origin': self.plane_origin,
                        'normal': self.plane_normal,
                        'x_dir': self.plane_x_dir,
                        'y_dir': self.plane_y_dir,
                    }
                }

        # === 2. Legacy Bundles: Ellipse aus Achsen berechnen (altes System) ===
        if not self._ellipse_bundles:
            return

        alive_bundles = []
        for bundle in self._ellipse_bundles:
            center = bundle.get("center")
            major_pos = bundle.get("major_pos")
            major_neg = bundle.get("major_neg")
            minor_pos = bundle.get("minor_pos")
            minor_neg = bundle.get("minor_neg")
            perimeter_points = bundle.get("perimeter_points") or []

            if any(p is None for p in (center, major_pos, major_neg, minor_pos, minor_neg)):
                continue
            if any(p not in self.points for p in (center, major_pos, major_neg, minor_pos, minor_neg)):
                continue

            # Zentrum aus den beiden Achsen-Mittelpunkten stabil bestimmen.
            major_mid_x = (major_pos.x + major_neg.x) * 0.5
            major_mid_y = (major_pos.y + major_neg.y) * 0.5
            minor_mid_x = (minor_pos.x + minor_neg.x) * 0.5
            minor_mid_y = (minor_pos.y + minor_neg.y) * 0.5
            center.x = (major_mid_x + minor_mid_x) * 0.5
            center.y = (major_mid_y + minor_mid_y) * 0.5

            ux = major_pos.x - center.x
            uy = major_pos.y - center.y
            vx = minor_pos.x - center.x
            vy = minor_pos.y - center.y

            rx = math.hypot(ux, uy)
            ry = math.hypot(vx, vy)
            if rx <= 1e-9 or ry <= 1e-9:
                alive_bundles.append(bundle)
                continue

            ux /= rx
            uy /= rx
            vx /= ry
            vy /= ry

            protected_ids = {
                getattr(major_pos, "id", None),
                getattr(major_neg, "id", None),
                getattr(minor_pos, "id", None),
                getattr(minor_neg, "id", None),
            }
            for pt in perimeter_points:
                if getattr(pt, "id", None) in protected_ids:
                    continue
                t = getattr(pt, "_ellipse_param_t", None)
                if t is None:
                    continue
                local_x = rx * math.cos(t)
                local_y = ry * math.sin(t)
                pt.x = center.x + local_x * ux + local_y * vx
                pt.y = center.y + local_x * uy + local_y * vy

            alive_bundles.append(bundle)

        self._ellipse_bundles = alive_bundles

    # Hilfsmethoden für Constraints
    def add_tangent(self, entity1, entity2) -> Optional[Constraint]:
        """Erstellt eine Tangente zwischen Linie und Kreis/Bogen"""
        if self._constraint_exists(ConstraintType.TANGENT, [entity1, entity2]):
            return None
        from .constraints import make_tangent
        c = make_tangent(entity1, entity2)
        self.constraints.append(c)
        return c

    def add_equal_radius(self, c1, c2) -> Optional[Constraint]:
        """Zwingt zwei Kreise/Bögen zum gleichen Radius"""
        if self._constraint_exists(ConstraintType.EQUAL_RADIUS, [c1, c2]):
            return None
        c = Constraint(ConstraintType.EQUAL_RADIUS, entities=[c1, c2])
        self.constraints.append(c)
        return c

    def add_concentric(self, c1, c2) -> Optional[Constraint]:
        """Macht zwei Kreise/Bögen konzentrisch"""
        if self._constraint_exists(ConstraintType.CONCENTRIC, [c1, c2]):
            return None
        from .constraints import Constraint
        c = Constraint(ConstraintType.CONCENTRIC, entities=[c1, c2])
        self.constraints.append(c)
        return c
    
    
    # === Constraint-Solver ===

    def get_spline_control_points(self) -> List['Point2D']:
        """
        W35: Gibt alle Spline-Control-Points zurück für Constraint-Solver.

        Control-Points sind reguläre Point2D Objekte, die vom Solver
        manipuliert werden können. Nach dem Solve müssen die Splines
        ihre Caches invalidieren.

        Returns:
            Liste aller Point2D Objekte aus Spline Control Points
        """
        control_points = []
        for spline in self.splines:
            for cp in spline.control_points:
                control_points.append(cp.point)
        return control_points

    def _invalidate_all_spline_caches(self) -> None:
        """
        W35: Invalidiert alle Spline-Caches nach Solver-Änderungen.

        Muss aufgerufen werden nachdem der Solver Control-Point-Koordinaten
        geändert hat.
        """
        for spline in self.splines:
            if hasattr(spline, 'invalidate_cache'):
                spline.invalidate_cache()
            # Re-generate line segments for rendering
            if hasattr(spline, 'to_lines'):
                spline._lines = spline.to_lines(segments_per_span=10)

    def _sanitize_for_solver(self) -> int:
        """
        Entfernt verwaiste Constraint-Referenzen vor dem Solve.

        Returns:
            Anzahl der entfernten Constraints.
        """
        before = len(self.constraints)
        self._cleanup_orphan_constraints()
        return before - len(self.constraints)

    def _normalize_parametric_result(self, result) -> SolverResult:
        """
        Bringt py-slvs Resultate auf das einheitliche SolverResult-Schema.
        """
        dof = int(getattr(result, "dof", -1))
        message = getattr(result, "message", "")
        raw_enum = getattr(result, "result", None)
        raw_name = getattr(raw_enum, "name", "")

        if getattr(result, "success", False):
            status = ConstraintStatus.FULLY_CONSTRAINED if dof <= 0 else ConstraintStatus.UNDER_CONSTRAINED
            return SolverResult(
                success=True,
                iterations=0,
                final_error=0.0,
                status=status,
                message=message,
                dof=dof,
                error_code="",
            )

        if raw_name == "TOO_MANY_UNKNOWNS":
            return SolverResult(
                success=True,
                iterations=0,
                final_error=0.0,
                status=ConstraintStatus.UNDER_CONSTRAINED,
                message=message or f"Unterbestimmt: {dof} Freiheitsgrade",
                dof=dof,
                error_code="too_many_unknowns",
            )

        if raw_name == "INCONSISTENT":
            status = ConstraintStatus.OVER_CONSTRAINED
        else:
            status = ConstraintStatus.INCONSISTENT

        return SolverResult(
            success=False,
            iterations=0,
            final_error=float("inf"),
            status=status,
            message=message or "py-slvs konnte nicht loesen",
            dof=dof,
            error_code="inconsistent" if raw_name == "INCONSISTENT" else "parametric_failed",
        )

    def _attach_solver_metadata(self, result: SolverResult) -> SolverResult:
        """
        Ergänzt SolverResult um konsistente DOF-/Variablen-Metadaten.
        """
        vars_count, constraint_count, dof = self.calculate_dof()

        try:
            result.n_variables = int(vars_count)
        except (AttributeError, TypeError, ValueError) as exc:
            logger.debug(f"Sketch.solve: n_variables konnte nicht gesetzt werden: {exc}")

        try:
            result.n_constraints = int(constraint_count)
        except (AttributeError, TypeError, ValueError) as exc:
            logger.debug(f"Sketch.solve: n_constraints konnte nicht gesetzt werden: {exc}")

        try:
            result.dof = int(dof)
        except (AttributeError, TypeError, ValueError) as exc:
            logger.debug(f"Sketch.solve: dof konnte nicht gesetzt werden: {exc}")

        try:
            current_code = str(getattr(result, "error_code", "") or "").strip().lower()
            if not current_code:
                msg = str(getattr(result, "message", "") or "").lower()
                status = getattr(result, "status", None)

                inferred = ""
                if "pre-validation failed" in msg:
                    inferred = "pre_validation_failed"
                elif "na" in msg and "inf" in msg:
                    inferred = "nan_residuals"
                elif "ung" in msg and "constraint" in msg:
                    inferred = "invalid_constraints"
                elif status == ConstraintStatus.OVER_CONSTRAINED:
                    inferred = "inconsistent"
                elif status == ConstraintStatus.INCONSISTENT:
                    inferred = "inconsistent"

                result.error_code = inferred
        except Exception as exc:
            logger.debug(f"Sketch.solve: error_code-Inferenz fehlgeschlagen: {exc}")

        try:
            if getattr(result, "status", None) == ConstraintStatus.FULLY_CONSTRAINED and dof > 0:
                result.status = ConstraintStatus.UNDER_CONSTRAINED
        except Exception as exc:
            logger.debug(f"Sketch.solve: Statuskorrektur fehlgeschlagen: {exc}")

        return result

    def solve(self) -> SolverResult:
        """Löst alle Constraints"""
        removed_orphans = self._sanitize_for_solver()
        if removed_orphans > 0:
            logger.debug(f"Sketch.solve: {removed_orphans} verwaiste Constraints entfernt")
        fallback_context = ""
        
        # 1. Versuche C++ Solver (falls vorhanden)
        try:
            from .parametric_solver import ParametricSolver, check_solvespace_available
            if check_solvespace_available():
                param_solver = ParametricSolver(self)
                is_supported, reason = param_solver.supports_current_sketch()
                if is_supported:
                    raw_res = param_solver.solve()
                    res = self._normalize_parametric_result(raw_res)
                    # Winkel-Update für Arcs ist wichtig nach dem Solve!
                    if res.success:
                        self._update_ellipse_geometry()
                        self._update_arc_angles()
                        # W35: Spline-Caches invalidieren nach Control-Point-Änderungen
                        self._invalidate_all_spline_caches()
                        self.invalidate_profiles()
                        return self._attach_solver_metadata(res)
                    raw_result_name = getattr(getattr(raw_res, "result", None), "name", "")
                    # Deterministische py-slvs-Fehler nicht still durch SciPy ueberschreiben.
                    if raw_result_name in {"INCONSISTENT", "TOO_MANY_UNKNOWNS"}:
                        logger.debug(f"py-slvs Ergebnis bleibt aktiv: {res.message}")
                        return self._attach_solver_metadata(res)
                    fallback_context = f"py-slvs fehlgeschlagen: {res.message}"
                    logger.debug(f"py-slvs Solve fehlgeschlagen, fallback auf SciPy: {res.message}")
                else:
                    fallback_context = f"py-slvs übersprungen: {reason}"
                    logger.debug(f"py-slvs übersprungen: {reason}")
        except ImportError:
            fallback_context = "py-slvs nicht verfügbar"
            logger.info("py-slvs nicht verfügbar, nutze SciPy-Fallback")

        # 2. Fallback auf Scipy Solver (NEU)
        # W35: Spline Control Points für Constraints exponieren
        spline_control_points = self.get_spline_control_points()
        res = self._solver.solve(
            self.points, self.lines, self.circles, self.arcs, self.constraints,
            spline_control_points=spline_control_points
        )

        if fallback_context and not res.success:
            base_msg = (res.message or "SciPy-Solver fehlgeschlagen").strip()
            if fallback_context not in base_msg:
                res.message = f"{base_msg} | {fallback_context}"

        # Auch hier Winkel updaten, falls der Solver Winkel geändert hat
        if res.success:
            self._update_ellipse_geometry()
            self._update_arc_angles()
            # W35: Spline-Caches invalidieren nach Control-Point-Änderungen
            self._invalidate_all_spline_caches()
            self.invalidate_profiles()

        return self._attach_solver_metadata(res)
    
    def is_fully_constrained(self) -> bool:
        """Prüft ob der Sketch vollständig bestimmt ist"""
        result = self.solve()
        if hasattr(result, 'status'):
            if getattr(result, 'status', None) != ConstraintStatus.FULLY_CONSTRAINED:
                return False
            dof = getattr(result, 'dof', None)
            if dof is None:
                return True
            return int(dof) <= 0
        if hasattr(result, 'success') and hasattr(result, 'dof'):
            return bool(result.success) and int(result.dof) <= 0
        return False
    
    def get_constraint_status(self) -> ConstraintStatus:
        """Gibt den aktuellen Constraint-Status zurück"""
        result = self.solve()
        if hasattr(result, 'status'):
            status = result.status
            dof = getattr(result, 'dof', None)
            if status == ConstraintStatus.FULLY_CONSTRAINED and dof is not None and int(dof) > 0:
                return ConstraintStatus.UNDER_CONSTRAINED
            return status
        if hasattr(result, 'success') and hasattr(result, 'dof'):
            if not result.success:
                return ConstraintStatus.INCONSISTENT
            return ConstraintStatus.FULLY_CONSTRAINED if int(result.dof) <= 0 else ConstraintStatus.UNDER_CONSTRAINED
        return ConstraintStatus.INCONSISTENT
    
    def calculate_dof(self) -> Tuple[int, int, int]:
        """
        Berechnet die Degrees of Freedom (DOF) des Sketches.
        
        Returns:
            Tuple von (total_variables, effective_constraints, dof)
            - total_variables: Anzahl der beweglichen Variablen (2 pro Punkt, 1 pro Radius, etc.)
            - effective_constraints: Anzahl der effektiven Constraints (ohne FIXED)
            - dof: Verbleibende Freiheitsgrade (max 0)
        """
        try:
            from .constraint_diagnostics import calculate_sketch_dof

            dof, total_variables, effective_constraints, _breakdown = calculate_sketch_dof(
                self.points,
                self.lines,
                self.circles,
                self.arcs,
                self.constraints,
            )
            return int(total_variables), int(effective_constraints), int(dof)
        except Exception:
            # Fallback auf konservative Schätzung
            n_vars = 0
            processed_points = set()
            for p in self.points:
                if not p.fixed and p.id not in processed_points:
                    n_vars += 2
                    processed_points.add(p.id)
            for line in self.lines:
                for p in [line.start, line.end]:
                    if not p.fixed and p.id not in processed_points:
                        n_vars += 2
                        processed_points.add(p.id)
            for circle in self.circles:
                n_vars += 1
                if not circle.center.fixed and circle.center.id not in processed_points:
                    n_vars += 2
                    processed_points.add(circle.center.id)
            for arc in self.arcs:
                n_vars += 3
                if not arc.center.fixed and arc.center.id not in processed_points:
                    n_vars += 2
                    processed_points.add(arc.center.id)

            n_constraints = len([
                c for c in self.constraints
                if c.type != ConstraintType.FIXED and c.is_valid() and getattr(c, 'enabled', True)
            ])
            dof = max(0, n_vars - n_constraints)
            return n_vars, n_constraints, dof
    
    def get_constraint_summary(self) -> dict:
        """
        Gibt eine Zusammenfassung des Constraint-Status zurück.
        
        Returns:
            Dictionary mit:
            - total_constraints: Gesamtanzahl Constraints
            - valid_constraints: Anzahl gültiger Constraints
            - invalid_constraints: Liste ungültiger Constraints
            - dof_info: (vars, constraints, dof) Tuple
            - status: ConstraintStatus (ohne zu lösen)
        """
        total = len(self.constraints)
        valid = [c for c in self.constraints if c.is_valid()]
        invalid = [c for c in self.constraints if not c.is_valid()]
        vars_count, constr_count, dof = self.calculate_dof()
        diagnostics = None
        
        # Schnelle Status-Bestimmung ohne zu lösen
        if invalid:
            status = ConstraintStatus.INCONSISTENT
        else:
            try:
                from .constraint_diagnostics import quick_check
                status, _ = quick_check(self)
            except Exception:
                if dof > 0:
                    status = ConstraintStatus.UNDER_CONSTRAINED
                elif constr_count > vars_count:
                    status = ConstraintStatus.OVER_CONSTRAINED
                else:
                    status = ConstraintStatus.FULLY_CONSTRAINED

        try:
            from .constraint_diagnostics import analyze_constraint_state
            diagnostics = analyze_constraint_state(self)
            if not invalid:
                status = diagnostics.status
        except Exception:
            diagnostics = None

        summary = {
            'total_constraints': total,
            'valid_constraints': len(valid),
            'invalid_constraints': invalid,
            'variables': vars_count,
            'effective_constraints': constr_count,
            'dof': dof,
            'status': status
        }

        if diagnostics is not None:
            summary.update({
                'diagnosis_type': diagnostics.diagnosis_type,
                'redundant_constraints': diagnostics.redundant_constraints,
                'conflicting_constraints': diagnostics.conflicting_constraints,
                'suggested_constraints': diagnostics.suggested_constraints,
                'redundant_count': len(diagnostics.redundant_constraints),
                'conflict_count': len(diagnostics.conflicting_constraints),
                'suggestion_count': len(diagnostics.suggested_constraints),
            })

        return summary
    
    def diagnose_constraints(self, top_n: int = 5) -> List[Tuple[Constraint, float, str]]:
        """
        Diagnostiziert die Constraints und gibt die problematischsten zurück.
        
        Args:
            top_n: Anzahl der zurückgegebenen Constraints (sortiert nach Fehler)
            
        Returns:
            Liste von Tupeln (constraint, error, diagnosis)
            - constraint: Der Constraint
            - error: Der Fehlerwert
            - diagnosis: Menschenlesbare Diagnose
        """
        from .constraints import calculate_constraint_error, ConstraintType
        
        results = []
        
        for c in self.constraints:
            # Prüfe Validität
            if not c.is_valid():
                error_msg = c.validation_error()
                results.append((c, float('inf'), f"Ungültig: {error_msg}"))
                continue
            
            # Berechne Fehler
            try:
                error = calculate_constraint_error(c)
                
                # Erstelle Diagnose
                if error < 1e-6:
                    diagnosis = "✓ Erfüllt"
                elif error < 0.01:
                    diagnosis = f"⚠ Leichte Abweichung ({error:.4f})"
                elif error < 0.1:
                    diagnosis = f"⚠ Mittlere Abweichung ({error:.4f})"
                else:
                    diagnosis = f"✗ Große Abweichung ({error:.4f})"
                
                # Zusätzliche Typ-spezifische Info
                if c.type == ConstraintType.FIXED:
                    diagnosis += " - Punkt sollte nicht bewegt werden"
                elif c.type == ConstraintType.COINCIDENT and error > 0.1:
                    diagnosis += " - Punkte zu weit auseinander"
                elif c.type == ConstraintType.TANGENT and error > 0.1:
                    diagnosis += " - Keine Tangentialität erreicht"
                
                results.append((c, error, diagnosis))
                
            except Exception as e:
                results.append((c, float('inf'), f"Fehler bei Berechnung: {e}"))
        
        # Sortiere nach Fehler (absteigend)
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results[:top_n]
    
    def diagnose_to_string(self) -> str:
        """Gibt eine formatierte Diagnose als String zurück."""
        lines = ["=== Constraint Diagnose ===", ""]
        
        # Zusammenfassung
        summary = self.get_constraint_summary()
        lines.append(f"Gesamt: {summary['total_constraints']} Constraints")
        lines.append(f"Gültig: {summary['valid_constraints']}")
        lines.append(f"Variablen: {summary['variables']}")
        lines.append(f"DOF: {summary['dof']}")
        lines.append(f"Status: {summary['status'].name}")
        lines.append("")
        
        # Ungültige Constraints
        if summary['invalid_constraints']:
            lines.append("Ungültige Constraints:")
            for c in summary['invalid_constraints']:
                lines.append(f"  ✗ {c.type.name}: {c.validation_error()}")
            lines.append("")
        
        # Top Probleme
        problems = self.diagnose_constraints(top_n=5)
        if problems:
            lines.append("Top Probleme:")
            for c, error, diagnosis in problems:
                if error > 1e-6:  # Nur anzeigen wenn es ein Problem gibt
                    lines.append(f"  {diagnosis}: {c.type.name}")
        else:
            lines.append("✓ Alle Constraints erfüllt!")
        
        return "\n".join(lines)
    
    # === Constraint-Gruppen Verwaltung ===
    
    def get_constraints_by_group(self, group: str) -> List[Constraint]:
        """Gibt alle Constraints einer Gruppe zurück."""
        return [c for c in self.constraints if c.group == group]
    
    def get_constraint_groups(self) -> Dict[str, List[Constraint]]:
        """Gibt alle Constraints nach Gruppen gruppiert zurück."""
        groups: Dict[str, List[Constraint]] = {}
        for c in self.constraints:
            g = c.group or "default"
            if g not in groups:
                groups[g] = []
            groups[g].append(c)
        return groups
    
    def set_constraint_group(self, constraint: Constraint, group: str):
        """Setzt die Gruppe eines Constraints."""
        if constraint in self.constraints:
            constraint.group = group
    
    def enable_constraint_group(self, group: str, enabled: bool = True):
        """Aktiviert/Deaktiviert alle Constraints einer Gruppe."""
        for c in self.constraints:
            if c.group == group:
                c.enabled = enabled
    
    def get_constraints_by_priority(self, priority) -> List[Constraint]:
        """Gibt alle Constraints mit einer bestimmten Priorität zurück."""
        from .constraints import ConstraintPriority
        return [c for c in self.constraints if c.get_priority() == priority]
    
    def remove_constraint(self, constraint: Constraint):
        """Entfernt einen Constraint"""
        if constraint in self.constraints:
            self.constraints.remove(constraint)

    def remove_constraints_for_entity(self, entity) -> int:
        """
        Entfernt alle Constraints die diese Entity referenzieren.

        Args:
            entity: Line2D, Circle2D, Arc2D oder Point2D

        Returns:
            Anzahl der entfernten Constraints
        """
        to_remove = []
        for c in self.constraints:
            # Prüfe ob Entity in den Constraint-Entities ist
            if entity in c.entities:
                to_remove.append(c)
            # Prüfe auch Punkte (für Linien: start/end)
            elif hasattr(entity, 'start') and (entity.start in c.entities or entity.end in c.entities):
                # Nur entfernen wenn BEIDE Punkte zur Entity gehören (z.B. LENGTH constraint)
                # NICHT entfernen wenn nur ein Punkt referenziert wird (z.B. COINCIDENT mit anderer Linie)
                if entity.start in c.entities and entity.end in c.entities:
                    to_remove.append(c)
            # Für Kreise: center Punkt
            elif hasattr(entity, 'center') and entity.center in c.entities:
                to_remove.append(c)

        for c in to_remove:
            self.constraints.remove(c)

        return len(to_remove)

    def clear_constraints(self):
        """Entfernt alle Constraints"""
        self.constraints.clear()
        for p in self.points:
            p.fixed = False
    
    # === Geometrie-Operationen ===
    
    def delete_point(self, point: Point2D):
        """Löscht einen Punkt und alle verbundenen Elemente"""
        # Entferne Linien die diesen Punkt verwenden
        self.lines = [l for l in self.lines 
                     if l.start != point and l.end != point]
        
        # Entferne Kreise mit diesem Zentrum
        self.circles = [c for c in self.circles if c.center != point]
        
        # Entferne Bögen mit diesem Zentrum
        self.arcs = [a for a in self.arcs if a.center != point]
        
        # Entferne Constraints die diesen Punkt verwenden
        self.constraints = [c for c in self.constraints 
                          if point not in c.entities]
        
        # Entferne den Punkt
        if point in self.points:
            self.points.remove(point)
    
    def delete_line(self, line: Line2D):
        """Löscht eine Linie und bereinigt verwaiste Punkte"""
        if line in self.lines:
            self.lines.remove(line)
        
        # Entferne Constraints die diese Linie verwenden
        self.constraints = [c for c in self.constraints 
                          if line not in c.entities]
        
        # Bereinige verwaiste Punkte
        self._cleanup_orphan_points()
        self.invalidate_profiles()

    def delete_circle(self, circle: Circle2D):
        """Löscht einen Kreis und bereinigt verwaiste Punkte"""
        if circle in self.circles:
            self.circles.remove(circle)
        
        self.constraints = [c for c in self.constraints 
                          if circle not in c.entities]
        
        # Bereinige verwaiste Punkte
        self._cleanup_orphan_points()
    
    def delete_arc(self, arc: Arc2D):
        """Löscht einen Bogen und bereinigt verwaiste Punkte"""
        if arc in self.arcs:
            self.arcs.remove(arc)
        
        self.constraints = [c for c in self.constraints 
                          if arc not in c.entities]
        
        # Bereinige verwaiste Punkte
        self._cleanup_orphan_points()
    
    def delete_ellipse(self, ellipse: Ellipse2D):
        """Löscht eine Ellipse und bereinigt verwaiste Punkte und Achsen"""
        if ellipse in self.ellipses:
            self.ellipses.remove(ellipse)
        
        self.constraints = [c for c in self.constraints 
                          if ellipse not in c.entities]
        
        # Lösche zugehörige Konstruktionsgeometrie (Achsen)
        if hasattr(ellipse, '_center_point') and ellipse._center_point in self.points:
            self.points.remove(ellipse._center_point)
        if hasattr(ellipse, '_major_axis') and ellipse._major_axis in self.lines:
            self.lines.remove(ellipse._major_axis)
            # Achsen-Endpunkte auch löschen
            if ellipse._major_axis.start in self.points:
                self.points.remove(ellipse._major_axis.start)
            if ellipse._major_axis.end in self.points:
                self.points.remove(ellipse._major_axis.end)
        if hasattr(ellipse, '_minor_axis') and ellipse._minor_axis in self.lines:
            self.lines.remove(ellipse._minor_axis)
            # Achsen-Endpunkte auch löschen
            if ellipse._minor_axis.start in self.points:
                self.points.remove(ellipse._minor_axis.start)
            if ellipse._minor_axis.end in self.points:
                self.points.remove(ellipse._minor_axis.end)
        
        # Bereinige verwaiste Punkte
        self._cleanup_orphan_points()
    
    def _cleanup_orphan_points(self):
        """Entfernt Punkte die nicht mehr von Geometrie verwendet werden
        (außer standalone Punkte die explizit erstellt wurden)"""
        # Sammle alle verwendeten Punkte
        used_points = set()
        
        for line in self.lines:
            used_points.add(id(line.start))
            used_points.add(id(line.end))
        
        for circle in self.circles:
            used_points.add(id(circle.center))
        
        for arc in self.arcs:
            used_points.add(id(arc.center))
        
        # Behalte nur Punkte die:
        # 1. Von Geometrie verwendet werden, ODER
        # 2. Als standalone Punkt explizit erstellt wurden
        new_points = []
        removed_points = set()
        for p in self.points:
            # getattr für Rückwärtskompatibilität mit älteren Point2D Objekten
            is_standalone = getattr(p, 'standalone', False)
            if id(p) in used_points or is_standalone:
                new_points.append(p)
            else:
                removed_points.add(id(p))
        
        self.points = new_points
        
        # Bereinige auch Constraints die auf gelöschte Punkte verweisen
        self._cleanup_orphan_constraints()
    
    def _cleanup_orphan_constraints(self):
        """Entfernt Constraints die auf nicht mehr existierende Geometrie verweisen"""
        # Sammle alle existierenden Entity-IDs
        valid_ids = set()
        for line in self.lines:
            valid_ids.add(id(line))
            valid_ids.add(id(line.start))
            valid_ids.add(id(line.end))
        for circle in self.circles:
            valid_ids.add(id(circle))
            valid_ids.add(id(circle.center))
        for arc in self.arcs:
            valid_ids.add(id(arc))
            valid_ids.add(id(arc.center))
        for ellipse in getattr(self, 'ellipses', []):
            valid_ids.add(id(ellipse))
            valid_ids.add(id(ellipse.center))
        for point in self.points:
            valid_ids.add(id(point))

        # W35: Spline Control Points als gültige Entities eintragen
        for spline in self.splines:
            for cp in spline.control_points:
                valid_ids.add(id(cp.point))

        # Filtere Constraints
        valid_constraints = []
        for c in self.constraints:
            # Prüfe ob alle Entities des Constraints noch existieren
            all_valid = True
            for entity in c.entities:
                if id(entity) not in valid_ids:
                    all_valid = False
                    break
            if all_valid:
                valid_constraints.append(c)

        self.constraints = valid_constraints
    
    def find_point_at(self, x: float, y: float, tolerance: float = 5.0) -> Optional[Point2D]:
        """Findet einen Punkt an einer Position"""
        target = Point2D(x, y)
        for p in self.points:
            if p.distance_to(target) < tolerance:
                return p
        return None
    
    def find_line_at(self, x: float, y: float, tolerance: float = 5.0) -> Optional[Line2D]:
        """Findet eine Linie an einer Position"""
        target = Point2D(x, y)
        for line in self.lines:
            if line.distance_to_point(target) < tolerance:
                return line
        return None
    
    # === Profil-Erkennung (Optimiert: Adjacency-Map + Caching) ===

    @property
    def closed_profiles(self):
        """Gibt geschlossene Profile zurück (lazy + cached)."""
        return self._find_closed_profiles()

    @closed_profiles.setter
    def closed_profiles(self, value):
        """Setter für GUI-Sync. Setzt _cached_profiles direkt."""
        self._cached_profiles = value
        self._profiles_valid = True

    def invalidate_profiles(self):
        """Nach Geometrie-Änderung aufrufen — Profil-Cache wird lazy neu berechnet."""
        self._profiles_valid = False
        self._adjacency.clear()

    def _build_adjacency(self, tolerance: float = 0.5):
        """Baut Punkt→Linien Adjacency-Map für O(1) Nachbar-Lookup."""
        self._adjacency.clear()
        prec = max(1, int(-1 * round(math.log10(tolerance)))) if tolerance > 0 else 1
        for line in self.lines:
            if line.construction:
                continue
            for pt in [line.start, line.end]:
                key = (round(pt.x, prec), round(pt.y, prec))
                self._adjacency.setdefault(key, []).append(line)

    def _find_closed_profiles(self, tolerance: float = 0.5):
        """Findet geschlossene Profile (für Extrude). Cached bis invalidate_profiles()."""
        if self._profiles_valid:
            return self._cached_profiles

        self._build_adjacency(tolerance)

        profiles = []
        used_line_ids = set()
        non_construction_lines = [l for l in self.lines if not l.construction]

        for start_line in non_construction_lines:
            if start_line.id in used_line_ids:
                continue
            profile = self._trace_profile(start_line, used_line_ids, tolerance)
            if profile and len(profile) >= 3:
                profiles.append(profile)

        # === TNP v4.1: Ellipsen als geschlossene Profile erkennen ===
        # Ellipsen sind per Definition geschlossene Kurven und können direkt extrudiert werden
        for ellipse in getattr(self, 'ellipses', []):
            if not ellipse.construction:
                # Erstelle ein Profil-Objekt für die Ellipse (ähnlich wie Kreise)
                # Das Profil-System akzeptiert jetzt auch Ellipse2D-Objekte
                profiles.append({'type': 'ellipse', 'geometry': ellipse})

        # === TNP v4.1: Kreise als geschlossene Profile erkennen ===
        for circle in self.circles:
            if not circle.construction:
                profiles.append({'type': 'circle', 'geometry': circle})
        
        # === W34: Slots als geschlossene Profile erkennen ===
        # Slots bestehen aus 2 Arcs + 2 Linien und sind geschlossene Profile
        # Wir identifizieren Slots über die Center-Line Marker
        processed_slot_centers = set()
        for line in self.lines:
            if getattr(line, '_slot_center_line', False) and line.id not in processed_slot_centers:
                # Finde alle Komponenten dieses Slots
                slot_arcs = []
                slot_lines = []
                
                for arc in self.arcs:
                    if getattr(arc, '_slot_arc', False):
                        slot_arcs.append(arc)
                
                for l in self.lines:
                    if getattr(l, '_slot_parent_center_line', None) is line:
                        slot_lines.append(l)
                
                # Slot ist gültig wenn er 2 Arcs und mindestens 2 Linien hat
                if len(slot_arcs) == 2 and len(slot_lines) >= 2:
                    profiles.append({
                        'type': 'slot',
                        'geometry': {
                            'center_line': line,
                            'arcs': slot_arcs,
                            'lines': slot_lines
                        }
                    })
                    processed_slot_centers.add(line.id)

        self._cached_profiles = profiles
        self._profiles_valid = True
        return profiles

    def get_outer_polygon(self, tolerance: float = 0.5):
        """Gibt das größte geschlossene Profil als 2D-Koordinatenliste zurück.

        Returns:
            List[Tuple[float, float]] oder None wenn kein Profil gefunden.
        """
        profiles = self._find_closed_profiles(tolerance)
        if not profiles:
            return None

        # Wähle das Profil mit der größten Fläche (= Außenprofil)
        best_profile = None
        best_area = 0.0
        for profile_lines in profiles:
            coords = [(l.start.x, l.start.y) for l in profile_lines]
            # Shoelace-Formel für Fläche
            area = 0.0
            n = len(coords)
            for i in range(n):
                x1, y1 = coords[i]
                x2, y2 = coords[(i + 1) % n]
                area += x1 * y2 - x2 * y1
            area = abs(area) / 2.0
            if area > best_area:
                best_area = area
                best_profile = coords

        return best_profile

    def get_all_profiles(self, tolerance: float = 0.5):
        """Gibt alle geschlossenen Profile als 2D-Koordinatenlisten zurück.

        Returns:
            List[List[Tuple[float, float]]] - Alle Profile als Koordinatenlisten.
        """
        profiles = self._find_closed_profiles(tolerance)
        result = []
        for profile_lines in profiles:
            coords = [(l.start.x, l.start.y) for l in profile_lines]
            if len(coords) >= 3:
                result.append(coords)
        return result

    def _adj_key(self, pt, tolerance: float = 0.5):
        """Rundet Punkt auf Adjacency-Key."""
        prec = max(1, int(-1 * round(math.log10(tolerance)))) if tolerance > 0 else 1
        return (round(pt.x, prec), round(pt.y, prec))

    def _trace_profile(self, start_line: Line2D, used_ids: set, tolerance: float = 0.5) -> Optional[List[Line2D]]:
        profile = [start_line]
        used_ids.add(start_line.id)
        current_point = start_line.end

        max_iterations = len(self.lines)

        for _ in range(max_iterations):
            next_line = None
            key = self._adj_key(current_point, tolerance)
            candidates = self._adjacency.get(key, [])

            for line in candidates:
                if line.id in used_ids:
                    continue
                if points_are_coincident(line.start, current_point, tolerance):
                    next_line = line
                    current_point = line.end
                    break
                elif points_are_coincident(line.end, current_point, tolerance):
                    next_line = line
                    current_point = line.start
                    break

            if next_line is None:
                logger.debug(f"Profil-Trace abgebrochen: kein Nachbar für Punkt ({current_point.x:.2f}, {current_point.y:.2f}), {len(profile)} Linien gesammelt")
                return None

            profile.append(next_line)
            used_ids.add(next_line.id)

            if points_are_coincident(current_point, start_line.start, tolerance):
                return profile

        logger.debug(f"Profil-Trace abgebrochen: max_iterations erreicht, {len(profile)} Linien gesammelt")
        return None
    
    # === Serialisierung ===
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary (für Speichern/Undo)"""
        # Splines serialisieren
        splines_data = []
        for spline in self.splines:
            cp_data = []
            for cp in spline.control_points:
                cp_data.append({
                    'point': (cp.point.x, cp.point.y),
                    'handle_in': cp.handle_in,
                    'handle_out': cp.handle_out,
                    'smooth': cp.smooth,
                    'weight': cp.weight  # W35: Weight auch serialisieren
                })
            splines_data.append({
                'id': spline.id,
                'control_points': cp_data,
                'closed': spline.closed,
                'construction': spline.construction
            })

        # Constraints serialisieren
        constraints_data = []
        for c in self.constraints:
            entity_ids = []
            for e in c.entities:
                eid = getattr(e, 'id', None)
                if eid is not None:
                    entity_ids.append(eid)
            cd = {
                'type': c.type.name,
                'id': c.id,
                'entity_ids': entity_ids,
                'value': c.value,
                'driving': c.driving,
            }
            if c.formula:
                cd['formula'] = c.formula
            constraints_data.append(cd)

        # Native Splines (DXF B-Splines) serialisieren
        native_splines_data = []
        for spline in self.native_splines:
            native_splines_data.append(spline.to_dict())

        # Closed Profiles serialisieren (Shapely Polygons → Koordinatenlisten)
        closed_profiles_data = []
        for poly in self.closed_profiles:
            try:
                # Shapely Polygon zu Koordinatenliste
                if hasattr(poly, 'exterior'):
                    coords = list(poly.exterior.coords)
                    # Holes (Interiors) auch speichern
                    holes = [list(interior.coords) for interior in poly.interiors]
                    closed_profiles_data.append({
                        'exterior': coords,
                        'holes': holes
                    })
            except Exception as e:
                logger.debug(f"Profil-Serialisierung übersprungen: {e}")

        # Slot-Marker für Linien sammeln
        line_slot_data = {}
        for l in self.lines:
            if getattr(l, '_slot_center_line', False):
                line_slot_data[l.id] = {'center_line': True}
            elif hasattr(l, '_slot_parent_center_line') and l._slot_parent_center_line is not None:
                line_slot_data[l.id] = {'parent_center_line_id': l._slot_parent_center_line.id}
        
        # Slot-Marker für Arcs sammeln
        arc_slot_data = {}
        for a in self.arcs:
            if getattr(a, '_slot_arc', False):
                arc_slot_data[a.id] = True
        
        return {
            'name': self.name,
            'id': self.id,
            # Phase E1: Plane-Information serialisieren
            'plane_origin': self.plane_origin,
            'plane_normal': self.plane_normal,
            'plane_x_dir': self.plane_x_dir,
            'plane_y_dir': self.plane_y_dir,
            'points': [(p.x, p.y, p.id, p.fixed, p.construction, p.standalone) for p in self.points],
            'lines': [(l.start.x, l.start.y, l.end.x, l.end.y, l.id, l.construction,
                       bool(getattr(l, "_suppress_endpoint_markers", False)), l.start.id, l.end.id)
                      for l in self.lines],
            'line_slot_markers': line_slot_data,  # W34: Slot-Marker persistieren
            'circles': [(c.center.x, c.center.y, c.radius, c.id, c.construction,
                         c.native_ocp_data, c.center.id)
                        for c in self.circles],
            'arcs': [(a.center.x, a.center.y, a.radius, a.start_angle, a.sweep_angle,
                      a.id, a.construction, a.native_ocp_data, a.center.id) for a in self.arcs],
            'arc_slot_markers': arc_slot_data,  # W34: Slot-Arc-Marker persistieren
            'ellipses': [(e.center.x, e.center.y, e.radius_x, e.radius_y, e.rotation,
                         e.id, e.construction, e.native_ocp_data, e.center.id) for e in self.ellipses],
            'splines': splines_data,
            'native_splines': native_splines_data,
            'constraints': constraints_data,
            'closed_profiles': closed_profiles_data,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Sketch':
        """Erstellt Sketch aus Dictionary (für Undo)"""
        sketch = cls(name=data.get('name', 'Sketch'))
        sketch.id = data.get('id', sketch.id)

        # Phase E1: Plane-Information wiederherstellen
        if 'plane_origin' in data:
            sketch.plane_origin = data['plane_origin']
            sketch.plane_normal = data.get('plane_normal', (0, 0, 1))
            sketch.plane_x_dir = data.get('plane_x_dir', (1, 0, 0))
            sketch.plane_y_dir = data.get('plane_y_dir', (0, 1, 0))

        # Standalone-Punkte wiederherstellen
        for pdata in data.get('points', []):
            x, y = pdata[0], pdata[1]
            pid = pdata[2] if len(pdata) > 2 else None
            fixed = pdata[3] if len(pdata) > 3 else False
            construction = pdata[4] if len(pdata) > 4 else False
            standalone = pdata[5] if len(pdata) > 5 else False
            if standalone:
                point = sketch.add_point(x, y, construction=construction)
                point.fixed = fixed
                if pid:
                    point.id = pid

        # Linien wiederherstellen
        line_id_map = {}  # W34: Für Slot-Parent-Referenzen
        for ldata in data.get('lines', []):
            x1, y1, x2, y2 = ldata[0], ldata[1], ldata[2], ldata[3]
            lid = ldata[4] if len(ldata) > 4 else None
            construction = ldata[5] if len(ldata) > 5 else False
            suppress_endpoint_markers = ldata[6] if len(ldata) > 6 else False
            start_id = ldata[7] if len(ldata) > 7 else None
            end_id = ldata[8] if len(ldata) > 8 else None
            line = sketch.add_line(x1, y1, x2, y2, construction=construction)
            if lid:
                line.id = lid
                line_id_map[lid] = line
            if start_id:
                line.start.id = start_id
            if end_id:
                line.end.id = end_id
            if suppress_endpoint_markers:
                line._suppress_endpoint_markers = True
                line._ellipse_segment = True
        
        # W34: Slot-Marker für Linien wiederherstellen
        line_slot_markers = data.get('line_slot_markers', {})
        for line_id, markers in line_slot_markers.items():
            if line_id in line_id_map:
                line = line_id_map[line_id]
                if markers.get('center_line'):
                    line._slot_center_line = True
                parent_id = markers.get('parent_center_line_id')
                if parent_id and parent_id in line_id_map:
                    line._slot_parent_center_line = line_id_map[parent_id]

        # Kreise wiederherstellen
        for cdata in data.get('circles', []):
            cx, cy, r = cdata[0], cdata[1], cdata[2]
            cid = cdata[3] if len(cdata) > 3 else None
            construction = cdata[4] if len(cdata) > 4 else False
            native_ocp_data = cdata[5] if len(cdata) > 5 else None
            center_id = cdata[6] if len(cdata) > 6 else None
            circle = sketch.add_circle(cx, cy, r, construction=construction)
            if cid:
                circle.id = cid
            if native_ocp_data:
                circle.native_ocp_data = native_ocp_data
            if center_id:
                circle.center.id = center_id

        # Bögen wiederherstellen
        arc_id_map = {}  # W34: Für Slot-Arc-Referenzen
        for adata in data.get('arcs', []):
            cx, cy, r, start, sweep = adata[0], adata[1], adata[2], adata[3], adata[4]
            aid = adata[5] if len(adata) > 5 else None
            construction = adata[6] if len(adata) > 6 else False
            native_ocp_data = adata[7] if len(adata) > 7 else None
            center_id = adata[8] if len(adata) > 8 else None
            arc = sketch.add_arc(cx, cy, r, start, start + sweep, construction=construction)
            if aid:
                arc.id = aid
                arc_id_map[aid] = arc
            if native_ocp_data:
                arc.native_ocp_data = native_ocp_data
            if center_id:
                arc.center.id = center_id
        
        # W34: Slot-Marker für Arcs wiederherstellen
        arc_slot_markers = data.get('arc_slot_markers', {})
        for arc_id, is_slot_arc in arc_slot_markers.items():
            if is_slot_arc and arc_id in arc_id_map:
                arc_id_map[arc_id]._slot_arc = True

        # Ellipsen wiederherstellen (TNP v4.1: Native Ellipse2D mit lifecycle support)
        for edata in data.get('ellipses', []):
            cx, cy, rx, ry = edata[0], edata[1], edata[2], edata[3]
            rotation = edata[4] if len(edata) > 4 else 0.0
            eid = edata[5] if len(edata) > 5 else None
            construction = edata[6] if len(edata) > 6 else False
            native_ocp_data = edata[7] if len(edata) > 7 else None
            center_id = edata[8] if len(edata) > 8 else None

            ellipse = sketch.add_ellipse(cx, cy, rx, ry, rotation, construction=construction)
            if eid:
                ellipse.id = eid
            if native_ocp_data:
                ellipse.native_ocp_data = native_ocp_data
            if center_id:
                ellipse.center.id = center_id

        # Splines wiederherstellen
        for sdata in data.get('splines', []):
            spline = BezierSpline()
            spline.id = sdata.get('id', spline.id)
            spline.closed = sdata.get('closed', False)
            spline.construction = sdata.get('construction', False)

            for cp_data in sdata.get('control_points', []):
                px, py = cp_data['point']
                cp = SplineControlPoint(
                    point=Point2D(px, py),
                    handle_in=tuple(cp_data.get('handle_in', (0, 0))),
                    handle_out=tuple(cp_data.get('handle_out', (0, 0))),
                    smooth=cp_data.get('smooth', True),
                    weight=cp_data.get('weight', 1.0)  # W35: Weight auch deserialisieren
                )
                spline.control_points.append(cp)

            # W35: Cache invalidieren nach Deserialisierung
            if hasattr(spline, 'invalidate_cache'):
                spline.invalidate_cache()

            sketch.splines.append(spline)

            # Linien für Kompatibilität regenerieren
            if spline.control_points:
                lines = spline.to_lines(segments_per_span=10)
                spline._lines = lines
                for line in lines:
                    sketch.lines.append(line)

        # Native Splines (B-Splines aus DXF) wiederherstellen
        for nsdata in data.get('native_splines', []):
            try:
                native_spline = Spline2D.from_dict(nsdata)
                sketch.native_splines.append(native_spline)
            except Exception as e:
                logger.debug(f"Native Spline Wiederherstellung übersprungen: {e}")

        # Constraints wiederherstellen
        # Entity-ID → Objekt Map aufbauen
        id_map = {}
        for p in sketch.points:
            id_map[p.id] = p
        for l in sketch.lines:
            id_map[l.id] = l
        for c in sketch.circles:
            id_map[c.id] = c
        for a in sketch.arcs:
            id_map[a.id] = a
        for e in sketch.ellipses:
            id_map[e.id] = e

        from .constraints import Constraint, ConstraintType
        for cdata in data.get('constraints', []):
            try:
                ctype = ConstraintType[cdata['type']]
                entities = [id_map[eid] for eid in cdata.get('entity_ids', []) if eid in id_map]
                if not entities:
                    continue
                constraint = Constraint(
                    type=ctype,
                    id=cdata.get('id', ''),
                    entities=entities,
                    value=cdata.get('value'),
                    formula=cdata.get('formula'),
                    driving=cdata.get('driving', True),
                )
                sketch.constraints.append(constraint)

                # FIX: FIXED-Constraint setzt auch point.fixed = True (wie make_fixed)
                # Das ist wichtig für die Solver-Logik
                if ctype == ConstraintType.FIXED and entities:
                    entity = entities[0]
                    if hasattr(entity, 'fixed'):
                        entity.fixed = True

            except (KeyError, Exception) as e:
                logger.debug(f"Constraint-Wiederherstellung übersprungen: {e}")

        # Closed Profiles wiederherstellen (Koordinatenlisten → Shapely Polygons)
        closed_profiles_data = data.get('closed_profiles', [])
        if closed_profiles_data:
            try:
                from shapely.geometry import Polygon as ShapelyPolygon
                for profile_data in closed_profiles_data:
                    try:
                        exterior = profile_data.get('exterior', [])
                        holes = profile_data.get('holes', [])
                        if exterior:
                            poly = ShapelyPolygon(exterior, holes)
                            if poly.is_valid and poly.area > 0.01:
                                sketch.closed_profiles.append(poly)
                    except Exception as e:
                        logger.debug(f"Profil-Wiederherstellung übersprungen: {e}")
                logger.debug(f"[Sketch.from_dict] {len(sketch.closed_profiles)} Profile wiederhergestellt")
            except ImportError:
                logger.debug("Shapely nicht verfügbar für Profil-Wiederherstellung")

        # FIX: Plane-Daten wiederherstellen (BUG in architecturvision dokumentiert)
        # Plane-Daten MÜSSEN vor closed_profiles wiederhergestellt werden,
        # da normalize_plane_basis() sie benötigt
        if 'plane_origin' in data:
            sketch.plane_origin = tuple(data['plane_origin'])
        if 'plane_normal' in data:
            sketch.plane_normal = tuple(data['plane_normal'])
        if 'plane_x_dir' in data and data['plane_x_dir'] is not None:
            sketch.plane_x_dir = tuple(data['plane_x_dir'])
        if 'plane_y_dir' in data and data['plane_y_dir'] is not None:
            sketch.plane_y_dir = tuple(data['plane_y_dir'])

        # Normalisiere die Plane-Basis um parallele/degeneirierte Achsen zu korrigieren
        sketch.normalize_plane_basis()

        return sketch

    def __repr__(self):
        return (f"Sketch('{self.name}', "
                f"{len(self.points)}pts, {len(self.lines)}lines, "
                f"{len(self.circles)}circles, {len(self.constraints)}constraints)")


# === Demo / Test ===

def demo_sketch():
    """Erstellt einen Demo-Sketch"""
    sketch = Sketch("Demo")
    
    # Rechteck 40x30
    lines = sketch.add_rectangle(0, 0, 40, 30)
    
    # Fixiere untere linke Ecke
    sketch.add_fixed(lines[0].start)
    
    # Setze Maße
    sketch.add_length(lines[0], 40)  # Breite
    sketch.add_length(lines[1], 30)  # Höhe
    
    # Löse
    result = sketch.solve()
    logger.info(f"Solver: {result}")
    logger.info(f"Sketch: {sketch}")
    
    # Zeige Koordinaten
    for i, line in enumerate(lines):
        logger.info(f"  Line {i}: {line.start} -> {line.end}")
    
    return sketch


if __name__ == "__main__":
    demo_sketch()
