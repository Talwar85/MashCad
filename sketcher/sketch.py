"""
LiteCAD Sketcher - Sketch Object
Fasst Geometrie und Constraints zusammen
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum, auto
import uuid
import math

from .geometry import (
    Point2D, Line2D, Circle2D, Arc2D, Rectangle2D,
    line_line_intersection, points_are_coincident,
    BezierSpline, SplineControlPoint
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
    splines: List['BezierSpline'] = field(default_factory=list)  # Bézier-Splines
    
    # Constraints
    constraints: List[Constraint] = field(default_factory=list)
    
    # Status
    state: SketchState = SketchState.EDITING
    
    # Ebene (später: 3D-Ebene)
    plane_origin: Tuple[float, float, float] = (0, 0, 0)
    plane_normal: Tuple[float, float, float] = (0, 0, 1)  # XY-Ebene
    
    # Solver
    _solver: ConstraintSolver = field(default_factory=ConstraintSolver)
    
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
        # 4 Eckpunkte erstellen (werden geteilt!)
        p1 = Point2D(x, y)              # Unten links (Ursprung)
        p2 = Point2D(x + width, y)      # Unten rechts
        p3 = Point2D(x + width, y + height)  # Oben rechts
        p4 = Point2D(x, y + height)     # Oben links
        
        # Ersten Punkt fixieren (Ursprungspunkt)
        p1.fixed = True
        
        # Punkte zur Liste hinzufügen
        self.points.extend([p1, p2, p3, p4])
        
        # 4 Linien mit GETEILTEN Punkten
        l1 = Line2D(p1, p2)  # Unten
        l2 = Line2D(p2, p3)  # Rechts
        l3 = Line2D(p3, p4)  # Oben
        l4 = Line2D(p4, p1)  # Links
        
        lines = [l1, l2, l3, l4]
        
        for line in lines:
            line.construction = construction
            self.lines.append(line)
        
        # Constraints: Horizontal/Vertikal
        # KEINE Coincident nötig - Punkte sind bereits geteilt!
        self.add_horizontal(l1)
        self.add_horizontal(l3)
        self.add_vertical(l2)
        self.add_vertical(l4)
        
        return lines
    
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
    
    # === Constraint-Erstellung ===
    
    def add_fixed(self, point: Point2D) -> Constraint:
        """Fixiert einen Punkt"""
        c = make_fixed(point)
        self.constraints.append(c)
        return c
    
    def add_coincident(self, p1: Point2D, p2: Point2D) -> Constraint:
        """Lässt zwei Punkte zusammenfallen"""
        c = make_coincident(p1, p2)
        self.constraints.append(c)
        return c
    
    def add_horizontal(self, line: Line2D) -> Constraint:
        """Macht eine Linie horizontal"""
        c = make_horizontal(line)
        self.constraints.append(c)
        return c
    
    def add_vertical(self, line: Line2D) -> Constraint:
        """Macht eine Linie vertikal"""
        c = make_vertical(line)
        self.constraints.append(c)
        return c
    
    def add_parallel(self, l1: Line2D, l2: Line2D) -> Constraint:
        """Macht zwei Linien parallel"""
        c = make_parallel(l1, l2)
        self.constraints.append(c)
        return c
    
    def add_perpendicular(self, l1: Line2D, l2: Line2D) -> Constraint:
        """Macht zwei Linien senkrecht"""
        c = make_perpendicular(l1, l2)
        self.constraints.append(c)
        return c
    
    def add_equal_length(self, l1: Line2D, l2: Line2D) -> Constraint:
        """Macht zwei Linien gleich lang"""
        c = make_equal_length(l1, l2)
        self.constraints.append(c)
        return c
    
    def add_length(self, line: Line2D, length: float) -> Constraint:
        """Setzt die Länge einer Linie"""
        c = make_length(line, length)
        self.constraints.append(c)
        return c
    
    def add_distance(self, p1: Point2D, p2: Point2D, distance: float) -> Constraint:
        """Setzt den Abstand zwischen zwei Punkten"""
        c = make_distance(p1, p2, distance)
        self.constraints.append(c)
        return c
    
    def add_radius(self, circle: Circle2D, radius: float) -> Constraint:
        """Setzt den Radius eines Kreises"""
        c = make_radius(circle, radius)
        self.constraints.append(c)
        return c
    
    def add_diameter(self, circle: Circle2D, diameter: float) -> Constraint:
        """Setzt den Durchmesser eines Kreises"""
        c = make_diameter(circle, diameter)
        self.constraints.append(c)
        return c
    
    def add_angle(self, l1: Line2D, l2: Line2D, angle: float) -> Constraint:
        """Setzt den Winkel zwischen zwei Linien"""
        c = make_angle(l1, l2, angle)
        self.constraints.append(c)
        return c
    
    def add_point_on_line(self, point: Point2D, line: Line2D) -> Constraint:
        """Legt einen Punkt auf eine Linie"""
        c = make_point_on_line(point, line)
        self.constraints.append(c)
        return c
    
    def add_midpoint(self, point: Point2D, line: Line2D) -> Constraint:
        """Legt einen Punkt auf den Mittelpunkt einer Linie"""
        c = make_midpoint(point, line)
        self.constraints.append(c)
        return c
    
    # === Constraint-Solver ===
    
    def solve(self) -> SolverResult:
        """Löst alle Constraints mit dem ParametricSolver"""
        try:
            from .parametric_solver import ParametricSolver, check_solvespace_available
            
            if check_solvespace_available():
                solver = ParametricSolver(self)
                result = solver.solve()
                return SolverResult(
                    status=ConstraintStatus.FULLY_CONSTRAINED if result.success else ConstraintStatus.UNDER_CONSTRAINED,
                    success=result.success,
                    message=result.message,
                    dof=result.dof
                )
            else:
                # Fallback zum alten Solver wenn python-solvespace nicht verfügbar
                return self._solver.solve(
                    self.points,
                    self.lines,
                    self.circles,
                    self.arcs,
                    self.constraints
                )
        except Exception as e:
            # Bei Fehler: alten Solver verwenden
            return self._solver.solve(
                self.points,
                self.lines,
                self.circles,
                self.arcs,
                self.constraints
            )
    
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
    
    # === Profil-Erkennung ===
    
    def find_closed_profiles(self) -> List[List[Line2D]]:
        """Findet geschlossene Profile (für Extrude)"""
        # Vereinfachte Implementierung - findet verbundene Schleifen
        profiles = []
        used_line_ids = set()
        
        for start_line in self.lines:
            if start_line.id in used_line_ids:
                continue
            
            profile = self._trace_profile(start_line, used_line_ids)
            if profile and len(profile) >= 3:
                profiles.append(profile)
        
        return profiles
    
    def _trace_profile(self, start_line: Line2D, used_ids: set) -> Optional[List[Line2D]]:
        """Verfolgt ein Profil von einer Startlinie aus"""
        profile = [start_line]
        used_ids.add(start_line.id)
        current_point = start_line.end
        
        max_iterations = len(self.lines)
        for _ in range(max_iterations):
            # Finde nächste Linie die an current_point beginnt
            next_line = None
            for line in self.lines:
                if line.id in used_ids:
                    continue
                if points_are_coincident(line.start, current_point, 0.01):
                    next_line = line
                    current_point = line.end
                    break
                elif points_are_coincident(line.end, current_point, 0.01):
                    # Linie umkehren
                    next_line = line
                    current_point = line.start
                    break
            
            if next_line is None:
                return None  # Offenes Profil
            
            profile.append(next_line)
            used_ids.add(next_line.id)
            
            # Geschlossen?
            if points_are_coincident(current_point, start_line.start, 0.01):
                return profile
        
        return None
    
    # === Serialisierung ===
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary (für Speichern/Undo)"""
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
