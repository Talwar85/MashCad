"""
MashCad - Trim Operation (Extrahiert aus sketch_handlers.py)
=============================================================

Testbare Trim-Operation mit klarer Schnittstelle.

Verwendung:
    from sketcher.operations import TrimOperation

    op = TrimOperation(sketch)
    result = op.find_segment(target_entity, click_point)

    if result.success:
        op.execute_trim(result.data)

Phase 13 Enhancement:
- Fuzzy Intersection Fallback für Tangent-Constraint-Fälle
- Behandelt numerische Instabilität bei Near-Miss Intersections
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Any, TYPE_CHECKING
from loguru import logger

from .base import SketchOperation, OperationResult, ResultStatus

if TYPE_CHECKING:
    from sketcher import Sketch, Point2D, Line2D, Circle2D, Arc2D


# === Adaptive Tolerances ===
# Default baseline values are conservative and get scaled by local geometry size.
FUZZY_INTERSECTION_TOLERANCE = 1e-4
FUZZY_INTERSECTION_SCALE_FACTOR = 1e-4
FUZZY_INTERSECTION_TOLERANCE_MAX = 5e-2

TRIM_POINT_MERGE_TOLERANCE = 1e-4
TRIM_POINT_MERGE_SCALE_FACTOR = 5e-5
TRIM_POINT_MERGE_TOLERANCE_MAX = 1e-2


@dataclass
class TrimSegment:
    """Beschreibt ein zu entfernendes Segment."""
    start_point: 'Point2D'
    end_point: 'Point2D'
    segment_index: int
    all_cut_points: List[Tuple[float, 'Point2D']]
    target_entity: Any
    is_full_delete: bool = False  # Für Kreise ohne Schnittpunkte


@dataclass
class TrimResult:
    """Ergebnis einer Trim-Analyse."""
    success: bool
    segment: Optional[TrimSegment] = None
    error: str = ""
    cut_points: List[Tuple[float, 'Point2D']] = field(default_factory=list)

    @classmethod
    def ok(cls, segment: TrimSegment, cut_points: List) -> 'TrimResult':
        return cls(success=True, segment=segment, cut_points=cut_points)

    @classmethod
    def no_target(cls) -> 'TrimResult':
        return cls(success=False, error="Kein Ziel gefunden")

    @classmethod
    def no_segment(cls) -> 'TrimResult':
        return cls(success=False, error="Kein Segment gefunden")

    @classmethod
    def fail(cls, error: str) -> 'TrimResult':
        return cls(success=False, error=error)


class TrimOperation(SketchOperation):
    """
    Extrahierte Trim-Operation.

    Trennt Analyse (find_segment) von Ausführung (execute_trim).
    Das ermöglicht Preview ohne Änderung am Sketch.
    """

    def __init__(self, sketch: 'Sketch'):
        super().__init__(sketch)
        self._geometry = None  # Lazy import
        self._last_trim_result: Optional[TrimResult] = None
        self._active_merge_tolerance = TRIM_POINT_MERGE_TOLERANCE

    def _get_geometry(self):
        """Lazy import des Geometry-Moduls."""
        if self._geometry is None:
            try:
                import sketcher.geometry as geometry
                self._geometry = geometry
            except ImportError:
                import geometry
                self._geometry = geometry
        return self._geometry

    def _get_all_entities(self) -> List:
        """Sammelt alle Entities aus dem Sketch."""
        entities = []
        entities.extend(self.sketch.lines)
        entities.extend(self.sketch.circles)
        if hasattr(self.sketch, 'arcs'):
            entities.extend(self.sketch.arcs)
        return entities

    @staticmethod
    def _points_equal(p1, p2, tol: float = 1e-5) -> bool:
        return abs(p1.x - p2.x) <= tol and abs(p1.y - p2.y) <= tol

    @staticmethod
    def _entity_bounds(entity) -> Optional[Tuple[float, float, float, float]]:
        """
        Returns a conservative 2D AABB for known sketch entities.
        """
        if entity is None:
            return None

        try:
            if hasattr(entity, "start") and hasattr(entity, "end"):
                min_x = min(float(entity.start.x), float(entity.end.x))
                min_y = min(float(entity.start.y), float(entity.end.y))
                max_x = max(float(entity.start.x), float(entity.end.x))
                max_y = max(float(entity.start.y), float(entity.end.y))
                return min_x, min_y, max_x, max_y

            if hasattr(entity, "center") and hasattr(entity, "radius"):
                cx = float(entity.center.x)
                cy = float(entity.center.y)
                r = abs(float(entity.radius))
                return cx - r, cy - r, cx + r, cy + r

            if hasattr(entity, "x") and hasattr(entity, "y"):
                px = float(entity.x)
                py = float(entity.y)
                return px, py, px, py
        except Exception:
            return None

        return None

    def _adaptive_tolerance_from_entities(
        self,
        entities: List[Any],
        base_tolerance: float,
        scale_factor: float,
        max_tolerance: float,
    ) -> float:
        """
        Computes a local tolerance based on combined entity bounds.
        """
        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")
        has_bounds = False

        for entity in entities:
            bounds = self._entity_bounds(entity)
            if bounds is None:
                continue
            bx0, by0, bx1, by1 = bounds
            if not all(math.isfinite(v) for v in (bx0, by0, bx1, by1)):
                continue
            has_bounds = True
            min_x = min(min_x, bx0)
            min_y = min(min_y, by0)
            max_x = max(max_x, bx1)
            max_y = max(max_y, by1)

        if not has_bounds:
            return base_tolerance

        diag = math.hypot(max_x - min_x, max_y - min_y)
        if not math.isfinite(diag) or diag <= 0.0:
            return base_tolerance

        adaptive = diag * scale_factor
        return max(base_tolerance, min(max_tolerance, adaptive))

    def _fuzzy_tolerance_for_pair(self, target, other) -> float:
        return self._adaptive_tolerance_from_entities(
            [target, other],
            base_tolerance=FUZZY_INTERSECTION_TOLERANCE,
            scale_factor=FUZZY_INTERSECTION_SCALE_FACTOR,
            max_tolerance=FUZZY_INTERSECTION_TOLERANCE_MAX,
        )

    def _merge_tolerance_for_target(self, target) -> float:
        return self._adaptive_tolerance_from_entities(
            [target],
            base_tolerance=TRIM_POINT_MERGE_TOLERANCE,
            scale_factor=TRIM_POINT_MERGE_SCALE_FACTOR,
            max_tolerance=TRIM_POINT_MERGE_TOLERANCE_MAX,
        )

    def _collect_transferable_line_constraints(self, target) -> List[Any]:
        """
        Sammelt line-bezogene Constraints, die nach Trim sicher auf ein einzelnes
        verbleibendes Segment migriert werden können.
        """
        from sketcher import Line2D
        from sketcher.constraints import ConstraintType

        if not isinstance(target, Line2D):
            return []

        transferable_types = {
            ConstraintType.HORIZONTAL,
            ConstraintType.VERTICAL,
            ConstraintType.PARALLEL,
            ConstraintType.PERPENDICULAR,
            ConstraintType.COLLINEAR,
            ConstraintType.ANGLE,
        }

        collected = []
        for constraint in getattr(self.sketch, "constraints", []):
            entities = getattr(constraint, "entities", [])
            if target in entities and constraint.type in transferable_types:
                collected.append(constraint)
        return collected

    @staticmethod
    def _clone_constraint_with_entity_replacement(constraint, old_entity, new_entity):
        """Erzeugt ein Constraint-Duplikat mit ersetzter Entity-Referenz."""
        from sketcher.constraints import Constraint

        new_entities = [new_entity if entity is old_entity else entity for entity in constraint.entities]
        return Constraint(
            type=constraint.type,
            entities=new_entities,
            value=constraint.value,
            formula=constraint.formula,
            driving=getattr(constraint, "driving", True),
            priority=getattr(constraint, "priority", None),
            group=getattr(constraint, "group", None),
            enabled=getattr(constraint, "enabled", True),
        )

    def _migrate_trimmed_line_constraints(self, old_line, candidates: List[Any]) -> int:
        """
        Migriert Constraints auf das neue Segment, falls genau ein Segment übrig blieb.
        """
        if not candidates:
            return 0

        created_segments = getattr(self, "_last_created_line_segments", [])
        if len(created_segments) != 1:
            logger.debug(
                f"[TRIM] Constraint-Migration übersprungen: {len(created_segments)} verbleibende Segmente"
            )
            return 0

        new_line = created_segments[0]
        migrated = 0
        for original in candidates:
            cloned = self._clone_constraint_with_entity_replacement(original, old_line, new_line)
            if not cloned.is_valid():
                continue
            if hasattr(self.sketch, "_constraint_exists") and self.sketch._constraint_exists(cloned.type, cloned.entities):
                continue
            self.sketch.constraints.append(cloned)
            migrated += 1

        if migrated:
            logger.info(f"[TRIM] {migrated} Constraints auf neues Segment migriert")
        return migrated

    def _collect_transferable_curve_constraints(self, target) -> List[Any]:
        """
        Sammelt kurvenbezogene Constraints, die sich robust auf genau eine
        verbleibende Kurve migrieren lassen.
        """
        from sketcher import Circle2D, Arc2D
        from sketcher.constraints import ConstraintType

        if not isinstance(target, (Circle2D, Arc2D)):
            return []

        transferable_types = {
            ConstraintType.CONCENTRIC,
            ConstraintType.EQUAL_RADIUS,
            ConstraintType.RADIUS,
            ConstraintType.DIAMETER,
        }

        collected = []
        for constraint in getattr(self.sketch, "constraints", []):
            entities = getattr(constraint, "entities", [])
            if target in entities and constraint.type in transferable_types:
                collected.append(constraint)
        return collected

    @staticmethod
    def _is_curve_constraint_compatible(constraint, new_entity) -> bool:
        """Prüft, ob ein Constraint-Typ zum neuen Kurven-Typ passt."""
        from sketcher.constraints import ConstraintType

        if constraint.type == ConstraintType.RADIUS:
            return hasattr(new_entity, "radius")
        if constraint.type == ConstraintType.DIAMETER:
            return hasattr(new_entity, "diameter")
        return True

    def _migrate_trimmed_curve_constraints(self, old_curve, candidates: List[Any]) -> int:
        """
        Migriert kurvenbezogene Constraints auf die neue Kurve, falls genau
        eine Zielkurve erzeugt wurde.
        """
        if not candidates:
            return 0

        created_curves = getattr(self, "_last_created_curve_entities", [])
        if len(created_curves) != 1:
            logger.debug(
                f"[TRIM] Kurven-Constraint-Migration übersprungen: {len(created_curves)} verbleibende Kurven"
            )
            return 0

        new_curve = created_curves[0]
        migrated = 0
        for original in candidates:
            if not self._is_curve_constraint_compatible(original, new_curve):
                continue
            cloned = self._clone_constraint_with_entity_replacement(original, old_curve, new_curve)
            if not cloned.is_valid():
                continue
            if hasattr(self.sketch, "_constraint_exists") and self.sketch._constraint_exists(cloned.type, cloned.entities):
                continue
            self.sketch.constraints.append(cloned)
            migrated += 1

        if migrated:
            logger.info(f"[TRIM] {migrated} Kurven-Constraints auf neues Segment migriert")
        return migrated

    def _detach_target_entity(self, target) -> None:
        """
        Entfernt die Ziel-Entity ohne sofortiges Topologie-Cleanup.
        Dadurch können Rebuild-Segmente existierende Punkt-Objekte weiterverwenden.
        """
        if target in self.sketch.lines:
            self.sketch.lines.remove(target)
        elif target in self.sketch.circles:
            self.sketch.circles.remove(target)
        elif hasattr(self.sketch, 'arcs') and target in self.sketch.arcs:
            self.sketch.arcs.remove(target)

    def _find_existing_point(self, point: 'Point2D', tolerance: Optional[float] = None):
        """Findet einen existierenden Punkt in Sketch-Geometrie nahe point."""
        if tolerance is None:
            tolerance = self._active_merge_tolerance

        for existing in getattr(self.sketch, "points", []):
            if self._points_equal(existing, point, tolerance):
                return existing

        for line in getattr(self.sketch, "lines", []):
            if self._points_equal(line.start, point, tolerance):
                return line.start
            if self._points_equal(line.end, point, tolerance):
                return line.end

        for circle in getattr(self.sketch, "circles", []):
            if self._points_equal(circle.center, point, tolerance):
                return circle.center

        for arc in getattr(self.sketch, "arcs", []):
            if self._points_equal(arc.center, point, tolerance):
                return arc.center

        return None

    def _resolve_trim_point(self, point: 'Point2D', target) -> 'Point2D':
        """
        Liefert ein stabiles Point-Objekt für Rebuild:
        1) Original-Endpunkte des getrimmten Targets
        2) Existierende Punkte im Sketch (mit kleiner CAD-Toleranz)
        3) Neu erzeugter Punkt
        """
        if hasattr(target, "start") and self._points_equal(point, target.start):
            return target.start
        if hasattr(target, "end") and self._points_equal(point, target.end):
            return target.end

        existing = self._find_existing_point(point)
        if existing is not None:
            return existing

        from sketcher import Point2D
        new_point = Point2D(point.x, point.y)
        self.sketch.points.append(new_point)
        return new_point

    def _arc_param_to_local(self, arc: 'Arc2D', t_abs: float) -> float:
        """
        Wandelt absoluten Winkelparameter (0..2π) in lokalen Arc-Parameter (0..1) um.
        """
        sweep_rad = math.radians(arc.sweep_angle)
        if sweep_rad <= 1e-12:
            return 0.0

        start_rad = math.radians(arc.start_angle % 360.0)
        delta = (t_abs - start_rad) % (2.0 * math.pi)
        return max(0.0, min(1.0, delta / sweep_rad))

    # === Fuzzy Intersection Fallback (Phase 13) ===

    def _get_min_distance_to_line(self, entity, line: 'Line2D') -> Tuple[float, Optional['Point2D'], Optional['Point2D']]:
        """
        Berechnet minimalen Abstand zwischen Entity und Line.

        Returns:
            (distance, point_on_entity, point_on_line)
        """
        from sketcher import Point2D, Arc2D, Circle2D

        best_dist = float('inf')
        best_entity_point = None
        best_line_point = None

        if isinstance(entity, Arc2D):
            # Sample mehrere Punkte auf dem Arc
            for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
                arc_pt = entity.point_at_parameter(t)
                dist = line.distance_to_point(arc_pt)
                if dist < best_dist:
                    best_dist = dist
                    best_entity_point = arc_pt
                    # Projiziere auf Linie für line_point
                    dx = line.end.x - line.start.x
                    dy = line.end.y - line.start.y
                    length_sq = dx*dx + dy*dy
                    if length_sq > 1e-10:
                        t_line = max(0, min(1, ((arc_pt.x - line.start.x)*dx + (arc_pt.y - line.start.y)*dy) / length_sq))
                        best_line_point = line.point_at_parameter(t_line)

            # Auch Arc Start/End prüfen
            for arc_pt in [entity.start_point, entity.end_point]:
                dist = line.distance_to_point(arc_pt)
                if dist < best_dist:
                    best_dist = dist
                    best_entity_point = arc_pt
                    dx = line.end.x - line.start.x
                    dy = line.end.y - line.start.y
                    length_sq = dx*dx + dy*dy
                    if length_sq > 1e-10:
                        t_line = max(0, min(1, ((arc_pt.x - line.start.x)*dx + (arc_pt.y - line.start.y)*dy) / length_sq))
                        best_line_point = line.point_at_parameter(t_line)

        elif isinstance(entity, Circle2D):
            # Nächster Punkt: Projektion des Zentrums auf die Linie
            dx = line.end.x - line.start.x
            dy = line.end.y - line.start.y
            length_sq = dx*dx + dy*dy
            if length_sq > 1e-10:
                t_line = max(0, min(1, ((entity.center.x - line.start.x)*dx + (entity.center.y - line.start.y)*dy) / length_sq))
                proj_point = line.point_at_parameter(t_line)

                # Punkt auf Kreis in Richtung der Projektion
                dir_x = proj_point.x - entity.center.x
                dir_y = proj_point.y - entity.center.y
                dir_len = math.hypot(dir_x, dir_y)

                if dir_len > 1e-10:
                    circle_pt = Point2D(
                        entity.center.x + dir_x / dir_len * entity.radius,
                        entity.center.y + dir_y / dir_len * entity.radius
                    )
                    best_dist = circle_pt.distance_to(proj_point)
                    best_entity_point = circle_pt
                    best_line_point = proj_point

        return best_dist, best_entity_point, best_line_point

    def _try_fuzzy_intersection(self, target, other, tolerance: Optional[float] = None) -> List['Point2D']:
        """
        Fuzzy-Fallback wenn Standard-Intersection 0 Punkte liefert.

        Prüft ob Entities sich "fast" berühren (Abstand < FUZZY_TOLERANCE).
        Wenn ja, wird der nächste Punkt als virtueller Schnittpunkt verwendet.

        Returns:
            Liste von Fuzzy-Schnittpunkten (leer wenn kein Near-Miss)
        """
        from sketcher import Point2D, Line2D, Arc2D, Circle2D

        fuzzy_points = []
        fuzzy_tol = tolerance if tolerance is not None else self._fuzzy_tolerance_for_pair(target, other)

        # Arc + Line Kombination (häufigster Tangent-Fall)
        if isinstance(target, Arc2D) and isinstance(other, Line2D):
            dist, arc_pt, line_pt = self._get_min_distance_to_line(target, other)

            if dist < fuzzy_tol and arc_pt is not None:
                # Prüfe ob der Punkt wirklich auf dem sichtbaren Arc liegt
                if self._point_on_arc(arc_pt, target):
                    logger.warning(
                        f"[TRIM] Fuzzy intersection injected: Arc-Line distance={dist:.6f}mm "
                        f"tol={fuzzy_tol:.6f} at ({arc_pt.x:.2f}, {arc_pt.y:.2f})"
                    )
                    fuzzy_points.append(arc_pt)

        elif isinstance(target, Line2D) and isinstance(other, Arc2D):
            dist, arc_pt, line_pt = self._get_min_distance_to_line(other, target)

            if dist < fuzzy_tol and line_pt is not None:
                # Für Line als Target: Prüfe ob Punkt auf Linie liegt
                t = self._get_geometry().get_param_on_entity(line_pt, target)
                if 0.0 <= t <= 1.0:
                    logger.warning(
                        f"[TRIM] Fuzzy intersection injected: Line-Arc distance={dist:.6f}mm "
                        f"tol={fuzzy_tol:.6f} at ({line_pt.x:.2f}, {line_pt.y:.2f})"
                    )
                    fuzzy_points.append(line_pt)

        # Circle + Line
        elif isinstance(target, Circle2D) and isinstance(other, Line2D):
            dist, circle_pt, line_pt = self._get_min_distance_to_line(target, other)

            if dist < fuzzy_tol and circle_pt is not None:
                logger.warning(
                    f"[TRIM] Fuzzy intersection injected: Circle-Line distance={dist:.6f}mm "
                    f"tol={fuzzy_tol:.6f} at ({circle_pt.x:.2f}, {circle_pt.y:.2f})"
                )
                fuzzy_points.append(circle_pt)

        elif isinstance(target, Line2D) and isinstance(other, Circle2D):
            dist, circle_pt, line_pt = self._get_min_distance_to_line(other, target)

            if dist < fuzzy_tol and line_pt is not None:
                t = self._get_geometry().get_param_on_entity(line_pt, target)
                if 0.0 <= t <= 1.0:
                    logger.warning(
                        f"[TRIM] Fuzzy intersection injected: Line-Circle distance={dist:.6f}mm "
                        f"tol={fuzzy_tol:.6f} at ({line_pt.x:.2f}, {line_pt.y:.2f})"
                    )
                    fuzzy_points.append(line_pt)

        return fuzzy_points

    def _point_on_arc(self, point: 'Point2D', arc: 'Arc2D') -> bool:
        """
        Prüft ob ein Punkt auf dem sichtbaren Arc-Segment liegt.

        Wichtig: Der Arc ist nur ein Teil des vollen Kreises.
        """
        # Berechne Winkel des Punktes relativ zum Zentrum
        dx = point.x - arc.center.x
        dy = point.y - arc.center.y
        angle_rad = math.atan2(dy, dx)
        angle_deg = math.degrees(angle_rad)

        # Normalisiere auf [0, 360)
        while angle_deg < 0:
            angle_deg += 360
        while angle_deg >= 360:
            angle_deg -= 360

        # Normalisiere Arc-Winkel
        start = arc.start_angle % 360
        end = arc.end_angle % 360

        if start < 0:
            start += 360
        if end < 0:
            end += 360

        # Prüfe ob Winkel im Arc-Bereich liegt
        if start <= end:
            return start - 1.0 <= angle_deg <= end + 1.0  # 1° Toleranz
        else:
            # Wrap-around (z.B. 350° bis 10°)
            return angle_deg >= start - 1.0 or angle_deg <= end + 1.0

    def _calculate_intersections(self, target, other_entities) -> List[Tuple[float, 'Point2D']]:
        """
        Berechnet alle Schnittpunkte des Targets mit anderen Entities.

        Returns:
            Liste von (parameter, point) Tupeln, sortiert nach Parameter
        """
        from sketcher import Point2D, Line2D, Circle2D, Arc2D
        geometry = self._get_geometry()

        cut_points = []

        # Start/Ende des Targets selbst
        if isinstance(target, Line2D):
            cut_points.append((0.0, target.start))
            cut_points.append((1.0, target.end))
        elif isinstance(target, Arc2D):
            # Für Arc-Trim müssen Arc-Enden explizit als Schnittgrenzen existieren.
            t_start = geometry.get_param_on_entity(target.start_point, target)
            t_end = geometry.get_param_on_entity(target.end_point, target)
            cut_points.append((t_start, target.start_point))
            cut_points.append((t_end, target.end_point))

        # Schnittpunkte mit anderen Entities
        for other in other_entities:
            if other == target:
                continue

            intersects = []
            try:
                if isinstance(target, Line2D) and isinstance(other, Line2D):
                    pt = geometry.line_line_intersection(target, other)
                    if pt:
                        # WICHTIG: Prüfe ob der Punkt auf BEIDEN Segmenten liegt
                        t_other = geometry.get_param_on_entity(pt, other)
                        if -0.001 <= t_other <= 1.001:  # Toleranz für Endpunkte
                            intersects = [pt]
                elif isinstance(target, Circle2D) and isinstance(other, Circle2D):
                    intersects = geometry.get_circle_circle_intersection(target, other)
                elif isinstance(target, Line2D) and isinstance(other, Circle2D):
                    intersects = geometry.circle_line_intersection(other, target)
                elif isinstance(target, Circle2D) and isinstance(other, Line2D):
                    intersects = geometry.circle_line_intersection(target, other)
                elif isinstance(target, Arc2D) and isinstance(other, Line2D):
                    intersects = geometry.arc_line_intersection(target, other)
                elif isinstance(target, Line2D) and isinstance(other, Arc2D):
                    intersects = geometry.arc_line_intersection(other, target)
                elif isinstance(target, Arc2D) and isinstance(other, Circle2D):
                    intersects = geometry.arc_circle_intersection(target, other)
                elif isinstance(target, Circle2D) and isinstance(other, Arc2D):
                    intersects = geometry.arc_circle_intersection(other, target)

                # === FUZZY FALLBACK (Phase 13) ===
                # Wenn keine exakten Schnittpunkte gefunden wurden,
                # prüfe auf Near-Miss (für Tangent-Constraints etc.)
                if not intersects:
                    fuzzy_tol = self._fuzzy_tolerance_for_pair(target, other)
                    fuzzy_pts = self._try_fuzzy_intersection(target, other, tolerance=fuzzy_tol)
                    if fuzzy_pts:
                        intersects = fuzzy_pts

            except Exception as e:
                logger.debug(f"Intersection error: {e}")
                continue

            # Validierung der Punkte
            for p in intersects:
                t = geometry.get_param_on_entity(p, target)
                if not math.isfinite(t):
                    continue

                if isinstance(target, Line2D):
                    # Toleranz: Nicht exakt auf Start/Ende
                    if 0.001 < t < 0.999:
                        cut_points.append((t, p))
                elif isinstance(target, (Circle2D, Arc2D)):
                    cut_points.append((t, p))

        # Sortieren nach Parameter
        cut_points.sort(key=lambda x: x[0])

        # Deduplizierung: Entferne Punkte die zu nah beieinander liegen
        if len(cut_points) > 1:
            unique_cuts = [cut_points[0]]
            for t, p in cut_points[1:]:
                prev_t, prev_p = unique_cuts[-1]
                # Punkt ist duplikat wenn Parameter oder Position sehr ähnlich
                same_t = abs(t - prev_t) <= 0.001
                same_p = abs(p.x - prev_p.x) <= 1e-4 and abs(p.y - prev_p.y) <= 1e-4
                if not (same_t or same_p):
                    unique_cuts.append((t, p))
            cut_points = unique_cuts

        return cut_points

    def _find_line_segment(self, target: 'Line2D', click_point: 'Point2D',
                           cut_points: List[Tuple[float, 'Point2D']]) -> Optional[TrimSegment]:
        """Findet das Segment auf einer Linie."""
        geometry = self._get_geometry()
        t_mouse = geometry.get_param_on_entity(click_point, target)
        if not math.isfinite(t_mouse):
            t_mouse = 0.5

        for i in range(len(cut_points) - 1):
            t_start, p_start = cut_points[i]
            t_end, p_end = cut_points[i + 1]
            if t_start <= t_mouse <= t_end:
                return TrimSegment(
                    start_point=p_start,
                    end_point=p_end,
                    segment_index=i,
                    all_cut_points=cut_points,
                    target_entity=target
                )

        # Falls der Klick minimal außerhalb liegt (UI-Picking-Toleranz),
        # trimmen wir das nächste Segment statt hard fail.
        if len(cut_points) >= 2:
            best_i = None
            best_dist = float('inf')
            for i in range(len(cut_points) - 1):
                t_start, _ = cut_points[i]
                t_end, _ = cut_points[i + 1]
                t_min = min(t_start, t_end)
                t_max = max(t_start, t_end)
                clamped = min(max(t_mouse, t_min), t_max)
                dist = abs(t_mouse - clamped)
                if dist < best_dist:
                    best_dist = dist
                    best_i = i
            if best_i is not None:
                return TrimSegment(
                    start_point=cut_points[best_i][1],
                    end_point=cut_points[best_i + 1][1],
                    segment_index=best_i,
                    all_cut_points=cut_points,
                    target_entity=target
                )
        return None

    def _find_circle_segment(self, target: 'Circle2D', click_point: 'Point2D',
                             cut_points: List[Tuple[float, 'Point2D']]) -> Optional[TrimSegment]:
        """Findet das Segment auf einem Kreis."""
        geometry = self._get_geometry()

        if not cut_points:
            # Keine Schnittpunkte = ganzer Kreis löschen
            return TrimSegment(
                start_point=None,
                end_point=None,
                segment_index=-1,
                all_cut_points=[],
                target_entity=target,
                is_full_delete=True
            )

        def normalize_angle(t):
            """Normalisiert Winkel auf [0, 2π)"""
            TWO_PI = 2 * math.pi
            while t < 0:
                t += TWO_PI
            while t >= TWO_PI:
                t -= TWO_PI
            return t

        t_mouse = geometry.get_param_on_entity(click_point, target)
        t_mouse_norm = normalize_angle(t_mouse)

        # Sortiere nach normalisiertem Winkel
        sorted_cuts = sorted(cut_points, key=lambda x: normalize_angle(x[0]))
        n = len(sorted_cuts)

        for i in range(n):
            t_s = normalize_angle(sorted_cuts[i][0])
            t_e = normalize_angle(sorted_cuts[(i + 1) % n][0])
            p_s = sorted_cuts[i][1]
            p_e = sorted_cuts[(i + 1) % n][1]

            # Prüfe ob Maus im Segment liegt
            in_segment = False
            if t_s < t_e:
                # Normales Segment
                in_segment = t_s <= t_mouse_norm <= t_e
            else:
                # Wrap-Around Segment
                in_segment = t_mouse_norm >= t_s or t_mouse_norm <= t_e

            if in_segment:
                return TrimSegment(
                    start_point=p_s,
                    end_point=p_e,
                    segment_index=i,
                    all_cut_points=sorted_cuts,
                    target_entity=target
                )

        # Fallback: Letztes Segment
        if sorted_cuts:
            return TrimSegment(
                start_point=sorted_cuts[-1][1],
                end_point=sorted_cuts[0][1],
                segment_index=-1,
                all_cut_points=sorted_cuts,
                target_entity=target
            )

        return None

    def _find_arc_segment(self, target: 'Arc2D', click_point: 'Point2D',
                          cut_points: List[Tuple[float, 'Point2D']]) -> Optional[TrimSegment]:
        """
        Findet das Segment auf einem Arc.
        Anders als beim Kreis gibt es keine Wrap-Around-Logik außerhalb des Arc-Sweeps.
        """
        geometry = self._get_geometry()

        if len(cut_points) < 2:
            return None

        # In lokalen Arc-Parameter 0..1 umrechnen und sortieren
        local_cuts = []
        for t_abs, p in cut_points:
            t_local = self._arc_param_to_local(target, t_abs)
            local_cuts.append((t_local, p))
        local_cuts.sort(key=lambda x: x[0])

        # Deduplizieren nach lokalem Parameter
        dedup = [local_cuts[0]]
        for t, p in local_cuts[1:]:
            if abs(t - dedup[-1][0]) > 1e-6:
                dedup.append((t, p))
        local_cuts = dedup

        t_mouse_abs = geometry.get_param_on_entity(click_point, target)
        t_mouse = self._arc_param_to_local(target, t_mouse_abs)

        for i in range(len(local_cuts) - 1):
            t_start, p_start = local_cuts[i]
            t_end, p_end = local_cuts[i + 1]
            if t_start <= t_mouse <= t_end:
                return TrimSegment(
                    start_point=p_start,
                    end_point=p_end,
                    segment_index=i,
                    all_cut_points=local_cuts,
                    target_entity=target
                )

        # Fallback: nächstes Segment
        if len(local_cuts) >= 2:
            best_i = 0
            best_dist = float('inf')
            for i in range(len(local_cuts) - 1):
                t0 = local_cuts[i][0]
                t1 = local_cuts[i + 1][0]
                mid = 0.5 * (t0 + t1)
                d = abs(mid - t_mouse)
                if d < best_dist:
                    best_dist = d
                    best_i = i
            return TrimSegment(
                start_point=local_cuts[best_i][1],
                end_point=local_cuts[best_i + 1][1],
                segment_index=best_i,
                all_cut_points=local_cuts,
                target_entity=target
            )

        return None

    def find_segment(self, target, click_point: 'Point2D') -> TrimResult:
        """
        Analysiert welches Segment getrimmt werden soll.

        Args:
            target: Ziel-Entity (Line2D, Circle2D, Arc2D)
            click_point: Klick-Position

        Returns:
            TrimResult mit Segment-Info oder Fehler
        """
        from sketcher import Line2D, Circle2D, Arc2D

        if target is None:
            return TrimResult.no_target()

        # Alle Entities sammeln
        other_entities = self._get_all_entities()

        # Schnittpunkte berechnen (inkl. Fuzzy-Fallback)
        cut_points = self._calculate_intersections(target, other_entities)

        # Debug-Logging für Diagnose
        entity_type = type(target).__name__
        # Für Lines: 2 cut_points sind Start/Ende, echte Schnitte sind > 2
        real_cuts = len(cut_points) - 2 if isinstance(target, Line2D) else len(cut_points)
        logger.debug(f"[TRIM] {entity_type}: {len(cut_points)} cut_points ({real_cuts} intersections)")

        # Segment finden je nach Entity-Typ
        segment = None
        if isinstance(target, Line2D):
            segment = self._find_line_segment(target, click_point, cut_points)
        elif isinstance(target, Circle2D):
            segment = self._find_circle_segment(target, click_point, cut_points)
        elif isinstance(target, Arc2D):
            segment = self._find_arc_segment(target, click_point, cut_points)

        if segment is None:
            logger.debug(f"[TRIM] Failed: Kein Segment gefunden (cut_points: {len(cut_points)})")
            return TrimResult.no_segment()

        self._last_trim_result = TrimResult.ok(segment, cut_points)
        return self._last_trim_result

    def execute_trim(self, segment: TrimSegment) -> OperationResult:
        """
        Führt den Trim aus (modifiziert den Sketch).

        Args:
            segment: TrimSegment von find_segment()

        Returns:
            OperationResult
        """
        from sketcher import Line2D, Circle2D, Arc2D
        geometry = self._get_geometry()

        target = segment.target_entity
        self._last_created_line_segments = []
        self._last_created_curve_entities = []
        transferable_line_constraints = self._collect_transferable_line_constraints(target)
        transferable_curve_constraints = self._collect_transferable_curve_constraints(target)

        # Best-effort rollback bei Fehlern (z.B. Exception im Rebuild)
        backup_lines = list(getattr(self.sketch, "lines", []))
        backup_circles = list(getattr(self.sketch, "circles", []))
        backup_arcs = list(getattr(self.sketch, "arcs", []))
        backup_points = list(getattr(self.sketch, "points", []))
        backup_constraints = list(getattr(self.sketch, "constraints", []))

        try:
            # 0. Constraints für diese Entity entfernen BEVOR sie gelöscht wird!
            self._active_merge_tolerance = self._merge_tolerance_for_target(target)
            removed_constraints = 0
            if hasattr(self.sketch, 'remove_constraints_for_entity'):
                removed_constraints = self.sketch.remove_constraints_for_entity(target)
                if removed_constraints > 0:
                    logger.info(f"[TRIM] {removed_constraints} Constraints entfernt für {type(target).__name__}")

            # 1. Target entfernen (ohne sofortiges Cleanup, damit Punkt-IDs stabil bleiben)
            self._detach_target_entity(target)

            # 2. Übrige Teile erstellen
            if isinstance(target, Line2D):
                result = self._recreate_line_segments(segment)
                if result.success:
                    self._migrate_trimmed_line_constraints(target, transferable_line_constraints)
            elif isinstance(target, Circle2D):
                result = self._recreate_circle_arc(segment)
                if result.success:
                    self._migrate_trimmed_curve_constraints(target, transferable_curve_constraints)
            elif isinstance(target, Arc2D):
                result = self._recreate_arc_segments(segment)
                if result.success:
                    self._migrate_trimmed_curve_constraints(target, transferable_curve_constraints)
            else:
                result = OperationResult.ok("Trim erfolgreich")

            # 3. Topologie konsistent halten
            if hasattr(self.sketch, '_cleanup_orphan_points'):
                self.sketch._cleanup_orphan_points()
            if hasattr(self.sketch, 'invalidate_profiles'):
                self.sketch.invalidate_profiles()

            return result

        except Exception as e:
            self.sketch.lines = backup_lines
            self.sketch.circles = backup_circles
            if hasattr(self.sketch, "arcs"):
                self.sketch.arcs = backup_arcs
            self.sketch.points = backup_points
            self.sketch.constraints = backup_constraints
            if hasattr(self.sketch, "invalidate_profiles"):
                self.sketch.invalidate_profiles()
            logger.error(f"Trim failed: {e}")
            return OperationResult.error(f"Trim fehlgeschlagen: {e}")

    def _recreate_line_segments(self, segment: TrimSegment) -> OperationResult:
        """Erstellt die übrigen Linien-Segmente nach dem Trim."""
        cut_points = segment.all_cut_points
        removed_start = segment.start_point
        removed_end = segment.end_point
        created_lines = []

        logger.debug(f"[TRIM] Recreate line segments: {len(cut_points)} cut_points")
        logger.debug(f"[TRIM] Removed segment: ({removed_start.x:.2f}, {removed_start.y:.2f}) → "
                    f"({removed_end.x:.2f}, {removed_end.y:.2f})")

        # Wenn nur 2 cut_points (Start + Ende), keine Schnittpunkte → ganze Linie löschen
        if len(cut_points) <= 2:
            logger.debug("[TRIM] Keine Schnittpunkte, Linie komplett gelöscht")
            return OperationResult.ok("Linie gelöscht (keine Schnittpunkte)")

        created_count = 0
        for i in range(len(cut_points) - 1):
            p_start = cut_points[i][1]
            p_end = cut_points[i + 1][1]

            # Prüfe ob das das gelöschte Segment ist
            same_dir = self._points_equal(p_start, removed_start) and self._points_equal(p_end, removed_end)
            opp_dir = self._points_equal(p_start, removed_end) and self._points_equal(p_end, removed_start)
            is_removed = same_dir or opp_dir

            logger.debug(f"[TRIM] Segment {i}: ({p_start.x:.2f}, {p_start.y:.2f}) → "
                        f"({p_end.x:.2f}, {p_end.y:.2f}), is_removed={is_removed}")

            if not is_removed and p_start.distance_to(p_end) > 1e-3:
                start_pt = self._resolve_trim_point(p_start, segment.target_entity)
                end_pt = self._resolve_trim_point(p_end, segment.target_entity)

                if start_pt is end_pt or start_pt.distance_to(end_pt) <= 1e-6:
                    continue

                if hasattr(self.sketch, "add_line_from_points"):
                    new_line = self.sketch.add_line_from_points(
                        start_pt,
                        end_pt,
                        construction=getattr(segment.target_entity, 'construction', False)
                    )
                else:
                    # Legacy-Fallback mit kleiner Merge-Toleranz
                    new_line = self.sketch.add_line(
                        start_pt.x, start_pt.y, end_pt.x, end_pt.y,
                        construction=getattr(segment.target_entity, 'construction', False),
                        tolerance=self._active_merge_tolerance
                    )
                created_lines.append(new_line)
                created_count += 1
                logger.debug(f"[TRIM] Created segment {created_count}")

        self._last_created_line_segments = created_lines
        return OperationResult.ok(f"{created_count} Segmente erstellt")

    def _recreate_circle_arc(self, segment: TrimSegment) -> OperationResult:
        """Erstellt den Arc nach dem Circle-Trim."""
        self._last_created_curve_entities = []
        if segment.is_full_delete:
            return OperationResult.ok("Kreis gelöscht")

        geometry = self._get_geometry()
        target = segment.target_entity

        p_start_remove = segment.start_point
        p_end_remove = segment.end_point

        # get_param_on_entity gibt Radiant zurück (0 bis 2π)
        # Der BLEIBENDE Arc geht von p_end_remove zu p_start_remove
        # (die andere Seite des Kreises, entgegengesetzt zum entfernten Segment)
        ang_start_rad = geometry.get_param_on_entity(p_end_remove, target)
        ang_end_rad = geometry.get_param_on_entity(p_start_remove, target)

        if ang_end_rad < ang_start_rad:
            ang_end_rad += 2 * math.pi

        # Arc2D erwartet Grad, nicht Radiant!
        ang_start_deg = math.degrees(ang_start_rad)
        ang_end_deg = math.degrees(ang_end_rad)

        logger.debug(f"[TRIM] Arc angles: {ang_start_deg:.1f}° to {ang_end_deg:.1f}°")

        if abs(ang_end_deg - ang_start_deg) > 0.1:  # Mindestens 0.1° Bogen
            new_arc = self.sketch.add_arc(
                target.center.x,
                target.center.y,
                target.radius,
                ang_start_deg,
                ang_end_deg,
                construction=getattr(target, 'construction', False)
            )
            self._last_created_curve_entities = [new_arc]
            return OperationResult.ok("Arc erstellt")

        return OperationResult.warning("Arc zu klein, nicht erstellt")

    def _recreate_arc_segments(self, segment: TrimSegment) -> OperationResult:
        """
        Erstellt verbleibende Arc-Segmente nach Trim eines Arc-Targets.
        """
        self._last_created_curve_entities = []
        target = segment.target_entity
        cut_points = segment.all_cut_points
        if len(cut_points) < 2:
            return OperationResult.ok("Arc gelöscht")

        # cut_points sind hier lokale Arc-Parameter (0..1), siehe _find_arc_segment.
        removed_start = segment.start_point
        removed_end = segment.end_point

        removed_idx = None
        for i in range(len(cut_points) - 1):
            p_s = cut_points[i][1]
            p_e = cut_points[i + 1][1]
            same_dir = self._points_equal(p_s, removed_start) and self._points_equal(p_e, removed_end)
            opp_dir = self._points_equal(p_s, removed_end) and self._points_equal(p_e, removed_start)
            if same_dir or opp_dir:
                removed_idx = i
                break

        if removed_idx is None:
            removed_idx = max(0, min(segment.segment_index, len(cut_points) - 2))

        keep_intervals = []
        for i in range(len(cut_points) - 1):
            if i == removed_idx:
                continue
            t0 = cut_points[i][0]
            t1 = cut_points[i + 1][0]
            if t1 - t0 > 1e-6:
                keep_intervals.append((t0, t1))

        if not keep_intervals:
            return OperationResult.ok("Arc gelöscht")

        sweep_deg = target.sweep_angle
        created = 0
        created_arcs = []
        for t0, t1 in keep_intervals:
            start_deg = target.start_angle + t0 * sweep_deg
            end_deg = target.start_angle + t1 * sweep_deg
            if abs(end_deg - start_deg) <= 0.1:
                continue
            new_arc = self.sketch.add_arc(
                target.center.x,
                target.center.y,
                target.radius,
                start_deg,
                end_deg,
                construction=getattr(target, 'construction', False)
            )
            created_arcs.append(new_arc)
            created += 1

        self._last_created_curve_entities = created_arcs
        if created == 0:
            return OperationResult.warning("Arc zu klein, nicht erstellt")
        return OperationResult.ok(f"{created} Arc-Segment(e) erstellt")

    def execute(self, target, click_point: 'Point2D') -> OperationResult:
        """
        Kombinierte Analyse + Ausführung.

        Args:
            target: Ziel-Entity
            click_point: Klick-Position

        Returns:
            OperationResult
        """
        result = self.find_segment(target, click_point)
        if not result.success:
            return OperationResult.no_target(result.error)

        return self.execute_trim(result.segment)

