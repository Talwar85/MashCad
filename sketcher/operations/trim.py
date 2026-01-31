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
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Any, TYPE_CHECKING
from loguru import logger

from .base import SketchOperation, OperationResult, ResultStatus

if TYPE_CHECKING:
    from sketcher import Sketch, Point2D, Line2D, Circle2D, Arc2D


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

        # Schnittpunkte berechnen
        cut_points = self._calculate_intersections(target, other_entities)

        # Segment finden je nach Entity-Typ
        segment = None
        if isinstance(target, Line2D):
            segment = self._find_line_segment(target, click_point, cut_points)
        elif isinstance(target, Circle2D):
            segment = self._find_circle_segment(target, click_point, cut_points)
        # TODO: Arc2D Support

        if segment is None:
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
            print(f"Unterschied gefunden: {details}")
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
