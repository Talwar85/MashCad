"""
LiteCAD - Parametric Constraint Solver
Basierend auf py-slvs (FreeCAD-Standard) für echtes parametrisches CAD

Verwendung:
    from sketcher.parametric_solver import ParametricSolver
    
    solver = ParametricSolver(sketch)
    result = solver.solve()
    
    if result.success:
        # Geometrie wurde aktualisiert
        pass

Installation:
    pip install py-slvs
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum, auto

# py-slvs Import (FreeCAD-Standard)
try:
    from py_slvs import slvs
    HAS_SOLVESPACE = True
except ImportError:
    HAS_SOLVESPACE = False
    slvs = None


class SolveResult(Enum):
    """Ergebnis des Constraint-Solvers"""
    OK = auto()                    # Alle Constraints erfüllt
    INCONSISTENT = auto()          # Widersprüchliche Constraints
    DIDNT_CONVERGE = auto()        # Solver konnte nicht konvergieren
    TOO_MANY_UNKNOWNS = auto()     # Zu viele Freiheitsgrade
    NO_SOLVER = auto()             # py-slvs nicht installiert


@dataclass
class SolverResult:
    """Detailliertes Solver-Ergebnis"""
    success: bool
    result: SolveResult
    dof: int  # Degrees of Freedom
    message: str
    failed_constraints: List[str] = field(default_factory=list)


def check_solvespace_available() -> bool:
    """Prüft ob py-slvs verfügbar ist"""
    return HAS_SOLVESPACE


class ParametricSolver:
    """
    Constraint Solver für LiteCAD Sketches basierend auf py-slvs.
    
    py-slvs ist der bewährte SWIG-Wrapper für SolveSpace,
    der auch in FreeCAD verwendet wird.
    """
    
    def __init__(self, sketch):
        """
        Args:
            sketch: LiteCAD Sketch-Objekt mit Geometrie und Constraints
        """
        self.sketch = sketch
        self.sys = None
        
        # Handle-Counter für Entities
        self._handle = 1
        
        # Gruppen
        self._group_wp = 1      # Workplane group
        self._group_sketch = 2  # Sketch group
        
        # Workplane handle
        self._wp_handle = 0
        
        # Mappings: LiteCAD ID -> (entity_handle, param_handles)
        self._point_map: Dict[str, Tuple[int, int, int]] = {}  # id -> (entity_h, px_h, py_h)
        self._line_map: Dict[str, int] = {}                     # id -> entity_h
        self._circle_map: Dict[str, Tuple[int, int]] = {}       # id -> (entity_h, radius_param_h)
        self._arc_map: Dict[str, int] = {}                      # id -> entity_h
        
        # Fixierte Punkte
        self._fixed_points: set = set()
    
    def _next_handle(self) -> int:
        """Gibt nächsten Handle zurück und inkrementiert"""
        h = self._handle
        self._handle += 1
        return h
    
    def _setup_workplane(self):
        """Erstellt die 2D-Arbeitsebene (XY-Ebene)"""
        g = self._group_wp
        
        # Origin (0, 0, 0) - 3 Parameter
        for v in [0.0, 0.0, 0.0]:
            self.sys.addParam(slvs.makeParam(self._next_handle(), g, v))
        
        # Point3d für Origin (referenziert params 1, 2, 3)
        origin = slvs.makePoint3d(self._next_handle(), g, 1, 2, 3)
        self.sys.addEntity(origin)
        
        # Quaternion für Normal (Z-up: 1, 0, 0, 0) - 4 Parameter
        for v in [1.0, 0.0, 0.0, 0.0]:
            self.sys.addParam(slvs.makeParam(self._next_handle(), g, v))
        
        # Normal3d (referenziert params 5, 6, 7, 8)
        normal = slvs.makeNormal3d(self._next_handle(), g, 5, 6, 7, 8)
        self.sys.addEntity(normal)
        
        # Workplane
        wp = slvs.makeWorkplane(self._next_handle(), g, origin.h, normal.h)
        self.sys.addEntity(wp)
        self._wp_handle = wp.h
    
    def _add_point(self, point_id: str, x: float, y: float) -> int:
        """Fügt einen 2D-Punkt hinzu"""
        g = self._group_sketch
        wp = self._wp_handle
        
        # Parameter für x und y
        px = slvs.makeParam(self._next_handle(), g, x)
        self.sys.addParam(px)
        py = slvs.makeParam(self._next_handle(), g, y)
        self.sys.addParam(py)
        
        # Point2d Entity
        pt = slvs.makePoint2d(self._next_handle(), g, wp, px.h, py.h)
        self.sys.addEntity(pt)
        
        # Mapping speichern
        self._point_map[point_id] = (pt.h, px.h, py.h)
        
        return pt.h
    
    def _add_line(self, line_id: str, start_id: str, end_id: str) -> int:
        """Fügt eine Linie hinzu"""
        g = self._group_sketch
        wp = self._wp_handle
        
        p1_data = self._point_map.get(start_id)
        p2_data = self._point_map.get(end_id)
        
        if not p1_data or not p2_data:
            return 0
        
        p1_h = p1_data[0]
        p2_h = p2_data[0]
        
        line = slvs.makeLineSegment(self._next_handle(), g, wp, p1_h, p2_h)
        self.sys.addEntity(line)
        
        self._line_map[line_id] = line.h
        return line.h
    
    def _add_circle(self, circle_id: str, center_id: str, radius: float) -> int:
        """Fügt einen Kreis hinzu"""
        g = self._group_sketch
        wp = self._wp_handle
        
        center_data = self._point_map.get(center_id)
        if not center_data:
            return 0
        
        center_h = center_data[0]
        
        # Radius als Distance-Entity
        r_param = slvs.makeParam(self._next_handle(), g, radius)
        self.sys.addParam(r_param)
        
        dist = slvs.makeDistance(self._next_handle(), g, wp, r_param.h)
        self.sys.addEntity(dist)
        
        # Normal für den Kreis (gleiche Orientierung wie Workplane)
        for v in [1.0, 0.0, 0.0, 0.0]:
            self.sys.addParam(slvs.makeParam(self._next_handle(), g, v))
        qw_h = self._handle - 4
        normal = slvs.makeNormal3d(self._next_handle(), g, qw_h, qw_h+1, qw_h+2, qw_h+3)
        self.sys.addEntity(normal)
        
        # Kreis
        circle = slvs.makeCircle(self._next_handle(), g, wp, center_h, normal.h, dist.h)
        self.sys.addEntity(circle)
        
        self._circle_map[circle_id] = (circle.h, r_param.h)
        return circle.h
    
    def _add_constraint_fixed(self, point_id: str):
        """Fixiert einen Punkt (WHERE_DRAGGED)"""
        g = self._group_sketch
        wp = self._wp_handle
        
        point_data = self._point_map.get(point_id)
        if not point_data:
            return
        
        pt_h = point_data[0]
        c = slvs.makeConstraint(
            self._next_handle(), g, slvs.SLVS_C_WHERE_DRAGGED,
            wp, 0.0, pt_h, 0, 0, 0
        )
        self.sys.addConstraint(c)
        self._fixed_points.add(point_id)
    
    def _add_constraint_horizontal(self, line_id: str):
        """Linie horizontal"""
        g = self._group_sketch
        wp = self._wp_handle
        
        line_h = self._line_map.get(line_id)
        if not line_h:
            return
        
        c = slvs.makeConstraint(
            self._next_handle(), g, slvs.SLVS_C_HORIZONTAL,
            wp, 0.0, 0, 0, line_h, 0
        )
        self.sys.addConstraint(c)
    
    def _add_constraint_vertical(self, line_id: str):
        """Linie vertikal"""
        g = self._group_sketch
        wp = self._wp_handle
        
        line_h = self._line_map.get(line_id)
        if not line_h:
            return
        
        c = slvs.makeConstraint(
            self._next_handle(), g, slvs.SLVS_C_VERTICAL,
            wp, 0.0, 0, 0, line_h, 0
        )
        self.sys.addConstraint(c)
    
    def _add_constraint_parallel(self, line1_id: str, line2_id: str):
        """Linien parallel"""
        g = self._group_sketch
        wp = self._wp_handle
        
        l1_h = self._line_map.get(line1_id)
        l2_h = self._line_map.get(line2_id)
        
        if not l1_h or not l2_h:
            return
        
        c = slvs.makeConstraint(
            self._next_handle(), g, slvs.SLVS_C_PARALLEL,
            wp, 0.0, 0, 0, l1_h, l2_h
        )
        self.sys.addConstraint(c)
    
    def _add_constraint_perpendicular(self, line1_id: str, line2_id: str):
        """Linien senkrecht"""
        g = self._group_sketch
        wp = self._wp_handle
        
        l1_h = self._line_map.get(line1_id)
        l2_h = self._line_map.get(line2_id)
        
        if not l1_h or not l2_h:
            return
        
        c = slvs.makeConstraint(
            self._next_handle(), g, slvs.SLVS_C_PERPENDICULAR,
            wp, 0.0, 0, 0, l1_h, l2_h
        )
        self.sys.addConstraint(c)
    
    def _add_constraint_equal_length(self, line1_id: str, line2_id: str):
        """Gleiche Länge"""
        g = self._group_sketch
        wp = self._wp_handle
        
        l1_h = self._line_map.get(line1_id)
        l2_h = self._line_map.get(line2_id)
        
        if not l1_h or not l2_h:
            return
        
        c = slvs.makeConstraint(
            self._next_handle(), g, slvs.SLVS_C_EQUAL_LENGTH_LINES,
            wp, 0.0, 0, 0, l1_h, l2_h
        )
        self.sys.addConstraint(c)
    
    def _add_constraint_coincident(self, point1_id: str, point2_id: str):
        """Punkte zusammen"""
        g = self._group_sketch
        wp = self._wp_handle
        
        p1_data = self._point_map.get(point1_id)
        p2_data = self._point_map.get(point2_id)
        
        if not p1_data or not p2_data:
            return
        
        c = slvs.makeConstraint(
            self._next_handle(), g, slvs.SLVS_C_POINTS_COINCIDENT,
            wp, 0.0, p1_data[0], p2_data[0], 0, 0
        )
        self.sys.addConstraint(c)
    
    def _add_constraint_distance(self, point1_id: str, point2_id: str, distance: float):
        """Abstand zwischen Punkten"""
        g = self._group_sketch
        wp = self._wp_handle
        
        p1_data = self._point_map.get(point1_id)
        p2_data = self._point_map.get(point2_id)
        
        if not p1_data or not p2_data:
            return
        
        c = slvs.makeConstraint(
            self._next_handle(), g, slvs.SLVS_C_PT_PT_DISTANCE,
            wp, distance, p1_data[0], p2_data[0], 0, 0
        )
        self.sys.addConstraint(c)
    
    def _add_constraint_length(self, line_id: str, length: float):
        """Linienlänge - über Punkt-Punkt-Distanz"""
        # Finde die Endpunkte der Linie
        for line in self.sketch.lines:
            if line.id == line_id:
                self._add_constraint_distance(line.start.id, line.end.id, length)
                return
    
    def _add_constraint_angle(self, line1_id: str, line2_id: str, angle_deg: float):
        """Winkel zwischen Linien"""
        g = self._group_sketch
        wp = self._wp_handle
        
        l1_h = self._line_map.get(line1_id)
        l2_h = self._line_map.get(line2_id)
        
        if not l1_h or not l2_h:
            return
        
        c = slvs.makeConstraint(
            self._next_handle(), g, slvs.SLVS_C_ANGLE,
            wp, angle_deg, 0, 0, l1_h, l2_h
        )
        self.sys.addConstraint(c)
    
    def _add_constraint_radius(self, circle_id: str, radius: float):
        """Kreisradius (als Diameter)"""
        g = self._group_sketch
        wp = self._wp_handle
        
        circle_data = self._circle_map.get(circle_id)
        if not circle_data:
            return
        
        circle_h = circle_data[0]
        
        c = slvs.makeConstraint(
            self._next_handle(), g, slvs.SLVS_C_DIAMETER,
            wp, radius * 2, 0, 0, circle_h, 0
        )
        self.sys.addConstraint(c)
    
    def _add_constraint_equal_radius(self, circle1_id: str, circle2_id: str):
        """Gleicher Radius"""
        g = self._group_sketch
        wp = self._wp_handle
        
        c1_data = self._circle_map.get(circle1_id)
        c2_data = self._circle_map.get(circle2_id)
        
        if not c1_data or not c2_data:
            return
        
        c = slvs.makeConstraint(
            self._next_handle(), g, slvs.SLVS_C_EQUAL_RADIUS,
            wp, 0.0, 0, 0, c1_data[0], c2_data[0]
        )
        self.sys.addConstraint(c)
    
    def _add_constraint_point_on_line(self, point_id: str, line_id: str):
        """Punkt auf Linie"""
        g = self._group_sketch
        wp = self._wp_handle
        
        pt_data = self._point_map.get(point_id)
        line_h = self._line_map.get(line_id)
        
        if not pt_data or not line_h:
            return
        
        c = slvs.makeConstraint(
            self._next_handle(), g, slvs.SLVS_C_PT_ON_LINE,
            wp, 0.0, pt_data[0], 0, line_h, 0
        )
        self.sys.addConstraint(c)
    
    def _add_constraint_point_on_circle(self, point_id: str, circle_id: str):
        """Punkt auf Kreis"""
        g = self._group_sketch
        wp = self._wp_handle
        
        pt_data = self._point_map.get(point_id)
        circle_data = self._circle_map.get(circle_id)
        
        if not pt_data or not circle_data:
            return
        
        c = slvs.makeConstraint(
            self._next_handle(), g, slvs.SLVS_C_PT_ON_CIRCLE,
            wp, 0.0, pt_data[0], 0, circle_data[0], 0
        )
        self.sys.addConstraint(c)
    
    def _add_constraint_tangent(self, line_id: str, circle_id: str):
        """Linie tangential zu Kreis"""
        g = self._group_sketch
        wp = self._wp_handle
        
        line_h = self._line_map.get(line_id)
        circle_data = self._circle_map.get(circle_id)
        
        if not line_h or not circle_data:
            return
        
        c = slvs.makeConstraint(
            self._next_handle(), g, slvs.SLVS_C_ARC_LINE_TANGENT,
            wp, 0.0, 0, 0, circle_data[0], line_h
        )
        self.sys.addConstraint(c)
    
    def _add_constraint_symmetric(self, point1_id: str, point2_id: str, line_id: str):
        """Punkte symmetrisch zu Linie"""
        g = self._group_sketch
        wp = self._wp_handle
        
        p1_data = self._point_map.get(point1_id)
        p2_data = self._point_map.get(point2_id)
        line_h = self._line_map.get(line_id)
        
        if not p1_data or not p2_data or not line_h:
            return
        
        c = slvs.makeConstraint(
            self._next_handle(), g, slvs.SLVS_C_SYMMETRIC_LINE,
            wp, 0.0, p1_data[0], p2_data[0], line_h, 0
        )
        self.sys.addConstraint(c)
    
    def _add_constraint_midpoint(self, point_id: str, line_id: str):
        """Punkt auf Mittelpunkt der Linie"""
        g = self._group_sketch
        wp = self._wp_handle
        
        pt_data = self._point_map.get(point_id)
        line_h = self._line_map.get(line_id)
        
        if not pt_data or not line_h:
            return
        
        c = slvs.makeConstraint(
            self._next_handle(), g, slvs.SLVS_C_AT_MIDPOINT,
            wp, 0.0, pt_data[0], 0, line_h, 0
        )
        self.sys.addConstraint(c)
    
    def _convert_geometry(self):
        """Konvertiert alle LiteCAD-Geometrie zu py-slvs"""
        # Alle Punkte sammeln (eindeutig nach ID)
        point_ids_added = set()
        
        # Punkte aus Linien
        for line in self.sketch.lines:
            if line.start.id not in point_ids_added:
                self._add_point(line.start.id, line.start.x, line.start.y)
                point_ids_added.add(line.start.id)
                if line.start.fixed:
                    self._add_constraint_fixed(line.start.id)
            
            if line.end.id not in point_ids_added:
                self._add_point(line.end.id, line.end.x, line.end.y)
                point_ids_added.add(line.end.id)
                if line.end.fixed:
                    self._add_constraint_fixed(line.end.id)
        
        # Punkte aus Kreisen
        for circle in self.sketch.circles:
            if circle.center.id not in point_ids_added:
                self._add_point(circle.center.id, circle.center.x, circle.center.y)
                point_ids_added.add(circle.center.id)
                if circle.center.fixed:
                    self._add_constraint_fixed(circle.center.id)
        
        # Punkte aus Bögen
        for arc in self.sketch.arcs:
            if arc.center.id not in point_ids_added:
                self._add_point(arc.center.id, arc.center.x, arc.center.y)
                point_ids_added.add(arc.center.id)
                if arc.center.fixed:
                    self._add_constraint_fixed(arc.center.id)
        
        # Standalone Punkte
        for point in self.sketch.points:
            if point.id not in point_ids_added:
                self._add_point(point.id, point.x, point.y)
                point_ids_added.add(point.id)
                if point.fixed:
                    self._add_constraint_fixed(point.id)
        
        # Linien
        for line in self.sketch.lines:
            self._add_line(line.id, line.start.id, line.end.id)
        
        # Kreise
        for circle in self.sketch.circles:
            self._add_circle(circle.id, circle.center.id, circle.radius)
    
    def _convert_constraints(self):
        """Konvertiert alle LiteCAD-Constraints zu py-slvs"""
        from .constraints import ConstraintType
        
        for constraint in self.sketch.constraints:
            try:
                ct = constraint.type
                entities = constraint.entities
                value = constraint.value
                
                if ct == ConstraintType.HORIZONTAL:
                    if entities and hasattr(entities[0], 'id'):
                        self._add_constraint_horizontal(entities[0].id)
                
                elif ct == ConstraintType.VERTICAL:
                    if entities and hasattr(entities[0], 'id'):
                        self._add_constraint_vertical(entities[0].id)
                
                elif ct == ConstraintType.PARALLEL:
                    if len(entities) >= 2:
                        self._add_constraint_parallel(entities[0].id, entities[1].id)
                
                elif ct == ConstraintType.PERPENDICULAR:
                    if len(entities) >= 2:
                        self._add_constraint_perpendicular(entities[0].id, entities[1].id)
                
                elif ct == ConstraintType.EQUAL_LENGTH:
                    if len(entities) >= 2:
                        self._add_constraint_equal_length(entities[0].id, entities[1].id)
                
                elif ct == ConstraintType.COINCIDENT:
                    if len(entities) >= 2:
                        self._add_constraint_coincident(entities[0].id, entities[1].id)
                
                elif ct == ConstraintType.LENGTH:
                    if entities:
                        self._add_constraint_length(entities[0].id, value)
                
                elif ct == ConstraintType.DISTANCE:
                    if len(entities) >= 2:
                        self._add_constraint_distance(entities[0].id, entities[1].id, value)
                
                elif ct == ConstraintType.ANGLE:
                    if len(entities) >= 2:
                        self._add_constraint_angle(entities[0].id, entities[1].id, value)
                
                elif ct == ConstraintType.RADIUS:
                    if entities:
                        self._add_constraint_radius(entities[0].id, value)
                
                elif ct == ConstraintType.DIAMETER:
                    if entities:
                        self._add_constraint_radius(entities[0].id, value / 2)
                
                elif ct == ConstraintType.POINT_ON_LINE:
                    if len(entities) >= 2:
                        self._add_constraint_point_on_line(entities[0].id, entities[1].id)
                
                elif ct == ConstraintType.MIDPOINT:
                    if len(entities) >= 2:
                        self._add_constraint_midpoint(entities[0].id, entities[1].id)
                
                elif ct == ConstraintType.TANGENT:
                    if len(entities) >= 2:
                        self._add_constraint_tangent(entities[0].id, entities[1].id)
                
                elif ct == ConstraintType.CONCENTRIC:
                    if len(entities) >= 2:
                        # Konzentrisch = gleiche Mittelpunkte
                        c1, c2 = entities[0], entities[1]
                        if hasattr(c1, 'center') and hasattr(c2, 'center'):
                            self._add_constraint_coincident(c1.center.id, c2.center.id)
                
            except Exception as e:
                from loguru import logger
                logger.warning(f"Constraint-Konvertierung übersprungen ({c.type.name}): {e}")
    
    def _ensure_fixed_point(self):
        """Stellt sicher dass mindestens ein Punkt fixiert ist.
        Fixiert den Punkt am nächsten zum Ursprung (0,0) für intuitiveres Verhalten."""
        if self._fixed_points:
            return  # Bereits fixierte Punkte vorhanden
        
        if not self._point_map:
            return
        
        # Finde den Punkt am nächsten zum Ursprung
        best_id = None
        best_dist = float('inf')
        
        for point_id, (_, px_h, py_h) in self._point_map.items():
            x = self.sys.getParam(px_h).val
            y = self.sys.getParam(py_h).val
            dist = x * x + y * y  # Quadrierte Distanz für Effizienz
            if dist < best_dist:
                best_dist = dist
                best_id = point_id
        
        if best_id:
            self._add_constraint_fixed(best_id)
    
    def _apply_solution(self):
        """Wendet die Solver-Ergebnisse auf die LiteCAD-Geometrie an"""
        # Punkte aktualisieren
        for line in self.sketch.lines:
            # Start
            start_data = self._point_map.get(line.start.id)
            if start_data:
                _, px_h, py_h = start_data
                line.start.x = self.sys.getParam(px_h).val
                line.start.y = self.sys.getParam(py_h).val
            
            # End
            end_data = self._point_map.get(line.end.id)
            if end_data:
                _, px_h, py_h = end_data
                line.end.x = self.sys.getParam(px_h).val
                line.end.y = self.sys.getParam(py_h).val
        
        # Kreise aktualisieren
        for circle in self.sketch.circles:
            center_data = self._point_map.get(circle.center.id)
            if center_data:
                _, px_h, py_h = center_data
                circle.center.x = self.sys.getParam(px_h).val
                circle.center.y = self.sys.getParam(py_h).val
            
            circle_data = self._circle_map.get(circle.id)
            if circle_data:
                _, r_h = circle_data
                circle.radius = self.sys.getParam(r_h).val
        
        # Bögen aktualisieren
        for arc in self.sketch.arcs:
            center_data = self._point_map.get(arc.center.id)
            if center_data:
                _, px_h, py_h = center_data
                arc.center.x = self.sys.getParam(px_h).val
                arc.center.y = self.sys.getParam(py_h).val
        
        # Standalone Punkte aktualisieren
        for point in self.sketch.points:
            point_data = self._point_map.get(point.id)
            if point_data:
                _, px_h, py_h = point_data
                point.x = self.sys.getParam(px_h).val
                point.y = self.sys.getParam(py_h).val
    
    def solve(self) -> SolverResult:
        """
        Löst alle Constraints und aktualisiert die Geometrie.
        
        Returns:
            SolverResult mit Erfolg/Fehler-Info
        """
        if not HAS_SOLVESPACE:
            return SolverResult(
                success=False,
                result=SolveResult.NO_SOLVER,
                dof=-1,
                message="py-slvs nicht installiert. Bitte installieren: pip install py-slvs"
            )
        
        try:
            # Neues System erstellen
            self.sys = slvs.System()
            self._handle = 1
            self._point_map.clear()
            self._line_map.clear()
            self._circle_map.clear()
            self._arc_map.clear()
            self._fixed_points.clear()
            
            # Workplane erstellen
            self._setup_workplane()
            
            # Geometrie konvertieren
            self._convert_geometry()
            
            # Constraints konvertieren
            self._convert_constraints()
            
            # Mindestens einen Punkt fixieren
            self._ensure_fixed_point()
            
            # Lösen
            result_code = self.sys.solve(self._group_sketch)
            dof = self.sys.Dof
            
            # Ergebnis interpretieren
            if result_code == 0:  # OK
                self._apply_solution()
                return SolverResult(
                    success=True,
                    result=SolveResult.OK,
                    dof=dof,
                    message=f"Gelöst. DOF: {dof}"
                )
            elif result_code == 1:  # DIDNT_CONVERGE
                return SolverResult(
                    success=False,
                    result=SolveResult.DIDNT_CONVERGE,
                    dof=dof,
                    message="Solver konnte nicht konvergieren"
                )
            elif result_code == 2:  # INCONSISTENT
                return SolverResult(
                    success=False,
                    result=SolveResult.INCONSISTENT,
                    dof=dof,
                    message="Widersprüchliche Constraints"
                )
            elif result_code == 3:  # TOO_MANY_UNKNOWNS
                return SolverResult(
                    success=False,
                    result=SolveResult.TOO_MANY_UNKNOWNS,
                    dof=dof,
                    message=f"Unterbestimmt: {dof} Freiheitsgrade"
                )
            else:
                return SolverResult(
                    success=False,
                    result=SolveResult.DIDNT_CONVERGE,
                    dof=dof,
                    message=f"Unbekannter Fehler: {result_code}"
                )
        
        except Exception as e:
            return SolverResult(
                success=False,
                result=SolveResult.DIDNT_CONVERGE,
                dof=-1,
                message=f"Solver-Fehler: {str(e)}"
            )


# Export
__all__ = [
    'ParametricSolver',
    'SolverResult',
    'SolveResult',
    'check_solvespace_available',
    'HAS_SOLVESPACE'
]
