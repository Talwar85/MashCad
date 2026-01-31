"""
MashCad - Extend Operation (Extrahiert aus sketch_handlers.py)
==============================================================

Testbare Extend-Operation mit klarer Schnittstelle.

Verwendung:
    from sketcher.operations import ExtendOperation

    op = ExtendOperation(sketch)
    result = op.find_extension(target_line, click_point)

    if result.success:
        op.execute_extend(result.data)

Feature-Flag: "use_extracted_extend"
"""

import math
from dataclasses import dataclass
from typing import Optional, List, TYPE_CHECKING
from loguru import logger

from .base import SketchOperation, OperationResult

if TYPE_CHECKING:
    from sketcher import Sketch, Point2D, Line2D


@dataclass
class ExtendData:
    """Beschreibt eine geplante Linien-Verlängerung."""
    line: 'Line2D'
    extend_start: bool  # True = Start-Punkt verlängern, False = End-Punkt
    new_point: 'Point2D'
    intersection_t: float  # Parameter auf der Linie


@dataclass
class ExtendResult:
    """Ergebnis einer Extend-Analyse."""
    success: bool
    data: Optional[ExtendData] = None
    error: str = ""

    @classmethod
    def ok(cls, data: ExtendData) -> 'ExtendResult':
        return cls(success=True, data=data)

    @classmethod
    def no_line(cls) -> 'ExtendResult':
        return cls(success=False, error="Keine Linie gefunden")

    @classmethod
    def no_extension(cls) -> 'ExtendResult':
        return cls(success=False, error="Keine Verlängerung möglich")


class ExtendOperation(SketchOperation):
    """
    Extrahierte Extend-Operation.

    Trennt Analyse (find_extension) von Ausführung (execute_extend).
    Das ermöglicht Preview ohne Änderung am Sketch.
    """

    def __init__(self, sketch: 'Sketch'):
        super().__init__(sketch)
        self._last_result: Optional[ExtendResult] = None

    def _point_on_line_t(self, line: 'Line2D', px: float, py: float) -> float:
        """
        Berechnet den Parameter t für einen Punkt auf/bei einer Linie.

        t=0 → Start, t=1 → Ende, t<0 oder t>1 → außerhalb
        """
        dx = line.end.x - line.start.x
        dy = line.end.y - line.start.y
        length_sq = dx * dx + dy * dy

        if length_sq < 1e-10:
            return 0.0

        return ((px - line.start.x) * dx + (py - line.start.y) * dy) / length_sq

    def _line_intersection_extended(self, l1: 'Line2D', l2: 'Line2D') -> Optional[tuple]:
        """
        Berechnet Schnittpunkt von l1 (verlängert) mit l2 (nur im Segment).

        Returns:
            (x, y, t) oder None
            t ist der Parameter auf l1
        """
        x1, y1 = l1.start.x, l1.start.y
        x2, y2 = l1.end.x, l1.end.y
        x3, y3 = l2.start.x, l2.start.y
        x4, y4 = l2.end.x, l2.end.y

        d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)

        if abs(d) < 1e-10:
            return None  # Parallel

        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
        s = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / d

        # s muss im Segment [0,1] von l2 liegen
        if 0 <= s <= 1:
            px = x1 + t * (x2 - x1)
            py = y1 + t * (y2 - y1)
            return (px, py, t)

        return None

    def find_extension(self, line: 'Line2D', click_x: float, click_y: float) -> ExtendResult:
        """
        Analysiert welche Verlängerung möglich ist.

        Args:
            line: Ziel-Linie zum Verlängern
            click_x, click_y: Klick-Position

        Returns:
            ExtendResult mit Verlängerungs-Info oder Fehler
        """
        from sketcher import Point2D

        if line is None:
            return ExtendResult.no_line()

        # Bestimme ob Start oder Ende verlängert wird
        click_t = self._point_on_line_t(line, click_x, click_y)
        extend_start = click_t < 0.5

        # Suche beste Intersection
        best_inter = None
        best_t = float('-inf') if extend_start else float('inf')

        for other in self.sketch.lines:
            if other == line:
                continue

            inter = self._line_intersection_extended(line, other)
            if inter:
                px, py, t = inter

                if extend_start:
                    # Suche Schnittpunkt mit t < 0 (vor Start), größtes t
                    if t < 0 and t > best_t:
                        best_t = t
                        best_inter = (px, py)
                else:
                    # Suche Schnittpunkt mit t > 1 (nach Ende), kleinstes t
                    if t > 1 and t < best_t:
                        best_t = t
                        best_inter = (px, py)

        if best_inter is None:
            return ExtendResult.no_extension()

        data = ExtendData(
            line=line,
            extend_start=extend_start,
            new_point=Point2D(best_inter[0], best_inter[1]),
            intersection_t=best_t
        )

        self._last_result = ExtendResult.ok(data)
        return self._last_result

    def execute_extend(self, data: ExtendData) -> OperationResult:
        """
        Führt die Verlängerung aus (modifiziert den Sketch).

        Args:
            data: ExtendData von find_extension()

        Returns:
            OperationResult
        """
        try:
            line = data.line
            new_point = data.new_point

            if data.extend_start:
                old_x, old_y = line.start.x, line.start.y
                line.start.x = new_point.x
                line.start.y = new_point.y
                logger.debug(f"[EXTEND] Start ({old_x:.2f}, {old_y:.2f}) → ({new_point.x:.2f}, {new_point.y:.2f})")
            else:
                old_x, old_y = line.end.x, line.end.y
                line.end.x = new_point.x
                line.end.y = new_point.y
                logger.debug(f"[EXTEND] End ({old_x:.2f}, {old_y:.2f}) → ({new_point.x:.2f}, {new_point.y:.2f})")

            return OperationResult.ok("Linie verlängert")

        except Exception as e:
            logger.error(f"Extend failed: {e}")
            return OperationResult.error(f"Extend fehlgeschlagen: {e}")

    def execute(self, line: 'Line2D', click_x: float, click_y: float) -> OperationResult:
        """
        Kombinierte Analyse + Ausführung.

        Args:
            line: Ziel-Linie
            click_x, click_y: Klick-Position

        Returns:
            OperationResult
        """
        result = self.find_extension(line, click_x, click_y)

        if not result.success:
            return OperationResult.no_target(result.error)

        return self.execute_extend(result.data)
