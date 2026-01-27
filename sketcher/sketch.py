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
    Point2D, Line2D, Circle2D, Arc2D, Rectangle2D,
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
    """
    
    name: str = "Sketch"
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    
    # Geometrie
    points: List[Point2D] = field(default_factory=list)
    lines: List[Line2D] = field(default_factory=list)
    circles: List[Circle2D] = field(default_factory=list)
    arcs: List[Arc2D] = field(default_factory=list)
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
    _adjacency: dict = field(default_factory=dict, repr=False)  # {(rx,ry): [line, ...]}
    
    # === Geometrie-Erstellung ===
    
    def add_point(self, x: float, y: float, construction: bool = False) -> Point2D:
        """Fügt einen standalone Punkt hinzu"""
        point = Point2D(x, y, construction=construction, standalone=True)
        self.points.append(point)
        return point
    
    def add_line(self, x1: float, y1: float, x2: float, y2: float, 
                 construction: bool = False, tolerance: float = 1.0) -> Line2D:
        """Fügt eine Linie hinzu. Verwendet existierende Punkte wenn möglich."""
        # Prüfe ob es schon Punkte an diesen Positionen gibt
        start = self._find_or_create_point(x1, y1, tolerance)
        end = self._find_or_create_point(x2, y2, tolerance)
        
        line = Line2D(start, end, construction=construction)
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
        """Fügt einen Kreis hinzu"""
        center = Point2D(cx, cy)
        circle = Circle2D(center, radius, construction=construction)
        self.points.append(center)
        self.circles.append(circle)
        return circle
    
    def add_arc(self, cx: float, cy: float, radius: float,
                start_angle: float, end_angle: float,
                construction: bool = False) -> Arc2D:
        """Fügt einen Bogen hinzu"""
        center = Point2D(cx, cy)
        arc = Arc2D(center, radius, start_angle, end_angle, construction=construction)
        self.points.append(center)
        self.arcs.append(arc)
        return arc
    
    def add_rectangle(self, x: float, y: float, width: float, height: float, construction: bool = False) -> List[Line2D]:
        """Fügt ein Rechteck hinzu (4 Linien mit geteilten Eckpunkten)"""
        # 4 Eckpunkte erstellen
        p1 = self.add_point(x, y, construction)               # Unten links
        p2 = self.add_point(x + width, y, construction)       # Unten rechts
        p3 = self.add_point(x + width, y + height, construction) # Oben rechts
        p4 = self.add_point(x, y + height, construction)      # Oben links
        
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

        # 4. Seitenlängen gleichsetzen (Equal Length Constraint)
        # Das sorgt dafür, dass alle Seiten gleich lang bleiben, auch wenn man zieht
        for i in range(len(lines)):
            l1 = lines[i]
            l2 = lines[(i + 1) % len(lines)]
            self.add_equal_length(l1, l2)

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
        Erstellt ein robustes Langloch mit 'Skelett'-Struktur.
        Verhindert das Verzerren beim Rotieren durch interne Konstruktionslinien.
        """
        import math
        
        # 1. Mittellinie (Konstruktion)
        p_start = self.add_point(x1, y1, construction=True)
        p_end = self.add_point(x2, y2, construction=True)
        line_center = self.add_line_from_points(p_start, p_end, construction=True)
        
        # Vektor für Offset berechnen
        dx, dy = x2 - x1, y2 - y1
        len_sq = dx*dx + dy*dy
        if len_sq < 1e-9: dx, dy = 1, 0 # Fallback
        else:
            length = math.sqrt(len_sq)
            dx /= length
            dy /= length
            
        nx, ny = -dy * radius, dx * radius # Normale skalieren
        
        # 2. Die 4 Eckpunkte berechnen
        t1 = self.add_point(x1 + nx, y1 + ny, construction=construction)
        b1 = self.add_point(x1 - nx, y1 - ny, construction=construction)
        t2 = self.add_point(x2 + nx, y2 + ny, construction=construction)
        b2 = self.add_point(x2 - nx, y2 - ny, construction=construction)
        
        # 3. Das "Skelett" bauen (Konstruktionslinien an den Enden)
        # Diese Linien sind entscheidend für die Stabilität beim Rotieren!
        cap1 = self.add_line_from_points(t1, b1, construction=True)
        cap2 = self.add_line_from_points(t2, b2, construction=True)
        
        # 4. Außenlinien verbinden
        line_top = self.add_line_from_points(t1, t2, construction=construction)
        line_bot = self.add_line_from_points(b1, b2, construction=construction)
        
        # 5. Bögen erstellen
        angle_deg = math.degrees(math.atan2(dy, dx))
        arc1 = self.add_arc(x1, y1, radius, angle_deg + 90, angle_deg + 270, construction=construction)
        arc2 = self.add_arc(x2, y2, radius, angle_deg - 90, angle_deg + 90, construction=construction)
        
        # === CONSTRAINTS (Die Magie für die Stabilität) ===
        
        # A. Kappen rechtwinklig zur Mittellinie zwingen (Verhindert Shearing)
        self.add_perpendicular(cap1, line_center)
        self.add_perpendicular(cap2, line_center)
        
        # B. Mittellinie zentriert auf Kappen (Midpoint)
        self.add_midpoint(p_start, cap1)
        self.add_midpoint(p_end, cap2)
        
        # C. Symmetrie/Länge der Kappen
        # Wir setzen den Abstand der Eckpunkte zur Mitte fest (definiert die Breite)
        self.add_distance(p_start, t1, radius)
        self.add_distance(p_start, b1, radius)
        self.add_distance(p_end, t2, radius)
        self.add_distance(p_end, b2, radius)
        
        # D. Bögen mit dem Skelett verbinden
        self.add_coincident(arc1.center, p_start)
        self.add_coincident(arc2.center, p_end)
        
        # WICHTIG: Die Bogen-Enden müssen an den Kappen-Enden kleben
        # Da Arc-Endpunkte berechnet sind, nutzen wir PointOnCircle für die Eckpunkte
        self.add_point_on_circle(t1, arc1)
        self.add_point_on_circle(b1, arc1)
        self.add_point_on_circle(t2, arc2)
        self.add_point_on_circle(b2, arc2)
        
        # E. Optional: Tangenten (für doppelte Sicherheit)
        self.add_tangent(line_top, arc1)
        
        # Speichere Referenzen in den Arcs, damit wir die Winkel später updaten können!
        # Wir fügen dynamisch Attribute hinzu, die wir später auslesen
        arc1._start_marker = t1  # Startet oben (CCW +90)
        arc1._end_marker = b1    # Endet unten
        
        arc2._start_marker = b2  # Startet unten (CCW -90)
        arc2._end_marker = t2    # Endet oben
        
        return line_center, arc1


    def _update_arc_angles(self):
        """
        Aktualisiert die Winkel von Bögen basierend auf ihren Marker-Punkten.
        Muss nach jedem solve() aufgerufen werden.
        """
        for arc in self.arcs:
            # Prüfen ob wir Marker für diesen Bogen gespeichert haben (siehe add_slot)
            p_start = getattr(arc, '_start_marker', None)
            p_end = getattr(arc, '_end_marker', None)
            
            if p_start and p_end:
                # Vektoren vom Zentrum zu den Markern
                dx_s = p_start.x - arc.center.x
                dy_s = p_start.y - arc.center.y
                dx_e = p_end.x - arc.center.x
                dy_e = p_end.y - arc.center.y
                
                # Winkel berechnen
                ang_s = math.degrees(math.atan2(dy_s, dx_s))
                ang_e = math.degrees(math.atan2(dy_e, dx_e))
                
                # Winkel setzen
                arc.start_angle = ang_s
                arc.end_angle = ang_e

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
    
    def solve(self) -> SolverResult:
        """Löst alle Constraints"""
        
        # 1. Versuche C++ Solver (falls vorhanden)
        try:
            from .parametric_solver import ParametricSolver, check_solvespace_available
            if check_solvespace_available():
                res = ParametricSolver(self).solve()
                # Winkel-Update für Arcs ist wichtig nach dem Solve!
                if res.success: 
                    self._update_arc_angles() # (Methode aus vorherigem Schritt)
                    return res
        except ImportError:
            logger.info("py-slvs nicht verfügbar, nutze SciPy-Fallback")

        # 2. Fallback auf Scipy Solver (NEU)
        res = self._solver.solve(
            self.points, self.lines, self.circles, self.arcs, self.constraints
        )
        
        # Auch hier Winkel updaten, falls der Solver Winkel geändert hat
        if res.success:
            self._update_arc_angles()
            self.invalidate_profiles()

        return res
    
    def is_fully_constrained(self) -> bool:
        """Prüft ob der Sketch vollständig bestimmt ist"""
        result = self.solve()
        return result.status == ConstraintStatus.FULLY_CONSTRAINED
    
    def get_constraint_status(self) -> ConstraintStatus:
        """Gibt den aktuellen Constraint-Status zurück"""
        result = self.solve()
        return result.status
    
    def remove_constraint(self, constraint: Constraint):
        """Entfernt einen Constraint"""
        if constraint in self.constraints:
            self.constraints.remove(constraint)
    
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
        for point in self.points:
            valid_ids.add(id(point))
        
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
                    'smooth': cp.smooth
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

        return {
            'name': self.name,
            'id': self.id,
            'points': [(p.x, p.y, p.id, p.fixed) for p in self.points],
            'lines': [(l.start.x, l.start.y, l.end.x, l.end.y, l.id, l.construction)
                      for l in self.lines],
            'circles': [(c.center.x, c.center.y, c.radius, c.id, c.construction)
                        for c in self.circles],
            'arcs': [(a.center.x, a.center.y, a.radius, a.start_angle, a.sweep_angle,
                      a.id, a.construction) for a in self.arcs],
            'splines': splines_data,
            'constraints': constraints_data,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Sketch':
        """Erstellt Sketch aus Dictionary (für Undo)"""
        sketch = cls(name=data.get('name', 'Sketch'))
        sketch.id = data.get('id', sketch.id)

        # Linien wiederherstellen
        for ldata in data.get('lines', []):
            x1, y1, x2, y2 = ldata[0], ldata[1], ldata[2], ldata[3]
            lid = ldata[4] if len(ldata) > 4 else None
            construction = ldata[5] if len(ldata) > 5 else False
            line = sketch.add_line(x1, y1, x2, y2, construction=construction)
            if lid:
                line.id = lid

        # Kreise wiederherstellen
        for cdata in data.get('circles', []):
            cx, cy, r = cdata[0], cdata[1], cdata[2]
            cid = cdata[3] if len(cdata) > 3 else None
            construction = cdata[4] if len(cdata) > 4 else False
            circle = sketch.add_circle(cx, cy, r, construction=construction)
            if cid:
                circle.id = cid

        # Bögen wiederherstellen
        for adata in data.get('arcs', []):
            cx, cy, r, start, sweep = adata[0], adata[1], adata[2], adata[3], adata[4]
            aid = adata[5] if len(adata) > 5 else None
            construction = adata[6] if len(adata) > 6 else False
            arc = sketch.add_arc(cx, cy, r, start, start + sweep, construction=construction)
            if aid:
                arc.id = aid

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
                    smooth=cp_data.get('smooth', True)
                )
                spline.control_points.append(cp)

            sketch.splines.append(spline)

            # Linien für Kompatibilität regenerieren
            if spline.control_points:
                lines = spline.to_lines(segments_per_span=10)
                spline._lines = lines
                for line in lines:
                    sketch.lines.append(line)

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
            except (KeyError, Exception) as e:
                from loguru import logger
                logger.debug(f"Constraint-Wiederherstellung übersprungen: {e}")

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
    print(f"Solver: {result}")
    print(f"Sketch: {sketch}")
    
    # Zeige Koordinaten
    for i, line in enumerate(lines):
        print(f"  Line {i}: {line.start} -> {line.end}")
    
    return sketch


if __name__ == "__main__":
    demo_sketch()
