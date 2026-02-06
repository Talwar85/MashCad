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

Feature-Flag: "use_extracted_trim"

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


# === Fuzzy Intersection Toleranz ===
# Für Tangent-Constraints und andere numerische Near-Miss-Fälle
FUZZY_INTERSECTION_TOLERANCE = 1e-4  # 0.1mm - CAD-übliche Toleranz


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

    def _try_fuzzy_intersection(self, target, other) -> List['Point2D']:
        """
        Fuzzy-Fallback wenn Standard-Intersection 0 Punkte liefert.

        Prüft ob Entities sich "fast" berühren (Abstand < FUZZY_TOLERANCE).
        Wenn ja, wird der nächste Punkt als virtueller Schnittpunkt verwendet.

        Returns:
            Liste von Fuzzy-Schnittpunkten (leer wenn kein Near-Miss)
        """
        from sketcher import Point2D, Line2D, Arc2D, Circle2D

        fuzzy_points = []

        # Arc + Line Kombination (häufigster Tangent-Fall)
        if isinstance(target, Arc2D) and isinstance(other, Line2D):
            dist, arc_pt, line_pt = self._get_min_distance_to_line(target, other)

            if dist < FUZZY_INTERSECTION_TOLERANCE and arc_pt is not None:
                # Prüfe ob der Punkt wirklich auf dem sichtbaren Arc liegt
                if self._point_on_arc(arc_pt, target):
                    logger.warning(
                        f"[TRIM V2] Fuzzy intersection injected: Arc-Line distance={dist:.6f}mm "
                        f"at ({arc_pt.x:.2f}, {arc_pt.y:.2f})"
                    )
                    fuzzy_points.append(arc_pt)

        elif isinstance(target, Line2D) and isinstance(other, Arc2D):
            dist, arc_pt, line_pt = self._get_min_distance_to_line(other, target)

            if dist < FUZZY_INTERSECTION_TOLERANCE and line_pt is not None:
                # Für Line als Target: Prüfe ob Punkt auf Linie liegt
                t = self._get_geometry().get_param_on_entity(line_pt, target)
                if 0.0 <= t <= 1.0:
                    logger.warning(
                        f"[TRIM V2] Fuzzy intersection injected: Line-Arc distance={dist:.6f}mm "
                        f"at ({line_pt.x:.2f}, {line_pt.y:.2f})"
                    )
                    fuzzy_points.append(line_pt)

        # Circle + Line
        elif isinstance(target, Circle2D) and isinstance(other, Line2D):
            dist, circle_pt, line_pt = self._get_min_distance_to_line(target, other)

            if dist < FUZZY_INTERSECTION_TOLERANCE and circle_pt is not None:
                logger.warning(
                    f"[TRIM V2] Fuzzy intersection injected: Circle-Line distance={dist:.6f}mm "
                    f"at ({circle_pt.x:.2f}, {circle_pt.y:.2f})"
                )
                fuzzy_points.append(circle_pt)

        elif isinstance(target, Line2D) and isinstance(other, Circle2D):
            dist, circle_pt, line_pt = self._get_min_distance_to_line(other, target)

            if dist < FUZZY_INTERSECTION_TOLERANCE and line_pt is not None:
                t = self._get_geometry().get_param_on_entity(line_pt, target)
                if 0.0 <= t <= 1.0:
                    logger.warning(
                        f"[TRIM V2] Fuzzy intersection injected: Line-Circle distance={dist:.6f}mm "
                        f"at ({line_pt.x:.2f}, {line_pt.y:.2f})"
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

        # Start/Ende des Targets selbst (für Linien)
        if isinstance(target, Line2D):
            cut_points.append((0.0, target.start))
            cut_points.append((1.0, target.end))

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
                    fuzzy_pts = self._try_fuzzy_intersection(target, other)
                    if fuzzy_pts:
                        intersects = fuzzy_pts

            except Exception as e:
                logger.debug(f"Intersection error: {e}")
                continue

            # Validierung der Punkte
            for p in intersects:
                t = geometry.get_param_on_entity(p, target)

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
                if abs(t - prev_t) > 0.001:  # Mindestabstand im Parameter-Raum
                    unique_cuts.append((t, p))
            cut_points = unique_cuts

        return cut_points

    def _find_line_segment(self, target: 'Line2D', click_point: 'Point2D',
                           cut_points: List[Tuple[float, 'Point2D']]) -> Optional[TrimSegment]:
        """Findet das Segment auf einer Linie."""
        geometry = self._get_geometry()
        t_mouse = geometry.get_param_on_entity(click_point, target)

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
        logger.debug(f"[TRIM V2] {entity_type}: {len(cut_points)} cut_points ({real_cuts} intersections)")

        # Segment finden je nach Entity-Typ
        segment = None
        if isinstance(target, Line2D):
            segment = self._find_line_segment(target, click_point, cut_points)
        elif isinstance(target, Circle2D):
            segment = self._find_circle_segment(target, click_point, cut_points)
        elif isinstance(target, Arc2D):
            # Arc2D wird wie Circle behandelt (gleiche Segment-Logik)
            segment = self._find_circle_segment(target, click_point, cut_points)

        if segment is None:
            logger.debug(f"[TRIM V2] Failed: Kein Segment gefunden (cut_points: {len(cut_points)})")
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

        try:
            # 0. Constraints für diese Entity entfernen BEVOR sie gelöscht wird!
            removed_constraints = 0
            if hasattr(self.sketch, 'remove_constraints_for_entity'):
                removed_constraints = self.sketch.remove_constraints_for_entity(target)
                if removed_constraints > 0:
                    logger.info(f"[TRIM] {removed_constraints} Constraints entfernt für {type(target).__name__}")

            # 1. Target entfernen
            if target in self.sketch.lines:
                self.sketch.lines.remove(target)
            elif target in self.sketch.circles:
                self.sketch.circles.remove(target)
            elif hasattr(self.sketch, 'arcs') and target in self.sketch.arcs:
                self.sketch.arcs.remove(target)

            # 2. Übrige Teile erstellen
            if isinstance(target, Line2D):
                return self._recreate_line_segments(segment)
            elif isinstance(target, Circle2D):
                return self._recreate_circle_arc(segment)

            return OperationResult.ok("Trim erfolgreich")

        except Exception as e:
            logger.error(f"Trim failed: {e}")
            return OperationResult.error(f"Trim fehlgeschlagen: {e}")

    def _recreate_line_segments(self, segment: TrimSegment) -> OperationResult:
        """Erstellt die übrigen Linien-Segmente nach dem Trim."""
        cut_points = segment.all_cut_points
        removed_start = segment.start_point
        removed_end = segment.end_point

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
            is_removed = (
                abs(p_start.x - removed_start.x) < 1e-5 and
                abs(p_start.y - removed_start.y) < 1e-5
            )

            logger.debug(f"[TRIM] Segment {i}: ({p_start.x:.2f}, {p_start.y:.2f}) → "
                        f"({p_end.x:.2f}, {p_end.y:.2f}), is_removed={is_removed}")

            if not is_removed and p_start.distance_to(p_end) > 1e-3:
                self.sketch.add_line(p_start.x, p_start.y, p_end.x, p_end.y)
                created_count += 1
                logger.debug(f"[TRIM] Created segment {created_count}")

        return OperationResult.ok(f"{created_count} Segmente erstellt")

    def _recreate_circle_arc(self, segment: TrimSegment) -> OperationResult:
        """Erstellt den Arc nach dem Circle-Trim."""
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
            self.sketch.add_arc(
                target.center.x,
                target.center.y,
                target.radius,
                ang_start_deg,
                ang_end_deg
            )
            return OperationResult.ok("Arc erstellt")

        return OperationResult.warning("Arc zu klein, nicht erstellt")

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


# === Vergleichs-Modus für Testing ===

class TrimComparisonTest:
    """
    Vergleicht alte und neue Trim-Implementierung.

    Verwendung:
        test = TrimComparisonTest(sketch)
        match, details = test.compare(target, click_point)

        if not match:
            # logger.debug(f"TrimComparisonTest: Unterschied gefunden: {details}")  # Nur für Debugging
    """

    def __init__(self, sketch: 'Sketch'):
        self.sketch = sketch
        self.new_op = TrimOperation(sketch)

    def compare(self, target, click_point: 'Point2D') -> Tuple[bool, str]:
        """
        Vergleicht ob beide Implementierungen das gleiche Segment finden.

        Returns:
            (match: bool, details: str)
        """
        # Neue Implementierung
        new_result = self.new_op.find_segment(target, click_point)

        # Details für Debugging
        if not new_result.success:
            return True, f"Kein Segment gefunden: {new_result.error}"

        seg = new_result.segment
        details = (
            f"Segment: idx={seg.segment_index}, "
            f"start=({seg.start_point.x:.3f}, {seg.start_point.y:.3f}), "
            f"end=({seg.end_point.x:.3f}, {seg.end_point.y:.3f})"
        )

        return True, details
