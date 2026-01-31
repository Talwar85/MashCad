"""
MashCad - Chamfer 2D Operation (Extrahiert aus sketch_handlers.py)
==================================================================

Testbare 2D-Chamfer-Operation mit klarer Schnittstelle.

Verwendung:
    from sketcher.operations import Chamfer2DOperation

    op = Chamfer2DOperation(sketch)
    result = op.find_corner(click_x, click_y, snap_radius)

    if result.success:
        chamfer = op.calculate_chamfer(result.data, distance=5.0)
        if chamfer.success:
            op.execute_chamfer(chamfer.data)

Feature-Flag: "use_extracted_chamfer_2d"
"""

import math
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING
from loguru import logger

from .base import SketchOperation, OperationResult
from .fillet2d import CornerData, CornerResult  # Reuse corner detection

if TYPE_CHECKING:
    from sketcher import Sketch, Point2D, Line2D


@dataclass
class ChamferData:
    """Beschreibt ein berechnetes Chamfer."""
    corner: CornerData
    distance: float
    chamfer1_x: float  # Erster Endpunkt der Fase
    chamfer1_y: float
    chamfer2_x: float  # Zweiter Endpunkt der Fase
    chamfer2_y: float
    chamfer_length: float  # Länge der Fasenlinie


@dataclass
class ChamferResult:
    """Ergebnis einer Chamfer-Berechnung."""
    success: bool
    data: Optional[ChamferData] = None
    error: str = ""

    @classmethod
    def ok(cls, data: ChamferData) -> 'ChamferResult':
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str) -> 'ChamferResult':
        return cls(success=False, error=error)


class Chamfer2DOperation(SketchOperation):
    """
    Extrahierte 2D-Chamfer-Operation.

    Trennt Suche (find_corner), Berechnung (calculate_chamfer) und
    Ausführung (execute_chamfer) für bessere Testbarkeit.
    """

    def __init__(self, sketch: 'Sketch'):
        super().__init__(sketch)

    def find_corner(self, click_x: float, click_y: float, snap_radius: float) -> CornerResult:
        """
        Findet eine Ecke (wo zwei Linien sich treffen) nahe der Klick-Position.

        Delegiert an Fillet2DOperation.find_corner() - gleiche Logik.
        """
        lines = self.sketch.lines

        for i, l1 in enumerate(lines):
            for l2 in lines[i + 1:]:
                corners = [
                    (l1.start, l1.end, l2.start, l2.end, 'start', 'start'),
                    (l1.start, l1.end, l2.end, l2.start, 'start', 'end'),
                    (l1.end, l1.start, l2.start, l2.end, 'end', 'start'),
                    (l1.end, l1.start, l2.end, l2.start, 'end', 'end'),
                ]

                for corner1, other1, corner2, other2, attr1, attr2 in corners:
                    is_same = corner1 is corner2
                    is_close = math.hypot(corner1.x - corner2.x, corner1.y - corner2.y) < 1.0

                    if is_same or is_close:
                        dist = math.hypot(corner1.x - click_x, corner1.y - click_y)
                        if dist < snap_radius:
                            return CornerResult.ok(CornerData(
                                line1=l1,
                                line2=l2,
                                corner_point=corner1,
                                other_point1=other1,
                                other_point2=other2,
                                attr1=attr1,
                                attr2=attr2
                            ))

        return CornerResult.not_found()

    def calculate_chamfer(self, corner: CornerData, distance: float) -> ChamferResult:
        """
        Berechnet die Chamfer-Geometrie für eine Ecke.

        Args:
            corner: CornerData von find_corner()
            distance: Chamfer-Abstand auf jedem Schenkel

        Returns:
            ChamferResult mit Geometrie-Daten oder Fehler
        """
        corner_pt = corner.corner_point
        other1 = corner.other_point1
        other2 = corner.other_point2

        # Richtungsvektoren VON der Ecke WEG
        d1 = (other1.x - corner_pt.x, other1.y - corner_pt.y)
        d2 = (other2.x - corner_pt.x, other2.y - corner_pt.y)

        len1 = math.hypot(d1[0], d1[1])
        len2 = math.hypot(d2[0], d2[1])

        if len1 < 0.01 or len2 < 0.01:
            return ChamferResult.fail("Linien zu kurz")

        # Normalisieren
        d1 = (d1[0] / len1, d1[1] / len1)
        d2 = (d2[0] / len2, d2[1] / len2)

        # Prüfe ob Abstand passt
        if distance > len1 * 0.9 or distance > len2 * 0.9:
            return ChamferResult.fail("Fase zu groß")

        # Neue Endpunkte auf den Linien
        c1_x = corner_pt.x + d1[0] * distance
        c1_y = corner_pt.y + d1[1] * distance
        c2_x = corner_pt.x + d2[0] * distance
        c2_y = corner_pt.y + d2[1] * distance

        # Länge der Fasenlinie
        chamfer_length = math.hypot(c2_x - c1_x, c2_y - c1_y)

        return ChamferResult.ok(ChamferData(
            corner=corner,
            distance=distance,
            chamfer1_x=c1_x,
            chamfer1_y=c1_y,
            chamfer2_x=c2_x,
            chamfer2_y=c2_y,
            chamfer_length=chamfer_length
        ))

    def execute_chamfer(self, chamfer: ChamferData) -> OperationResult:
        """
        Führt das Chamfer aus (modifiziert den Sketch).

        Args:
            chamfer: ChamferData von calculate_chamfer()

        Returns:
            OperationResult
        """
        from sketcher import Point2D

        try:
            corner = chamfer.corner
            l1 = corner.line1
            l2 = corner.line2

            # Neue Punkte erstellen
            new_pt1 = Point2D(chamfer.chamfer1_x, chamfer.chamfer1_y)
            new_pt2 = Point2D(chamfer.chamfer2_x, chamfer.chamfer2_y)
            self.sketch.points.append(new_pt1)
            self.sketch.points.append(new_pt2)

            # Linien anpassen
            if corner.attr1 == 'start':
                l1.start = new_pt1
            else:
                l1.end = new_pt1

            if corner.attr2 == 'start':
                l2.start = new_pt2
            else:
                l2.end = new_pt2

            # Fase-Linie hinzufügen
            chamfer_line = self.sketch.add_line(
                chamfer.chamfer1_x, chamfer.chamfer1_y,
                chamfer.chamfer2_x, chamfer.chamfer2_y
            )

            # Längen-Constraint hinzufügen
            self.sketch.add_length(chamfer_line, chamfer.chamfer_length)

            logger.debug(f"[CHAMFER] Created D={chamfer.distance:.1f}mm, "
                        f"L={chamfer.chamfer_length:.2f}mm")

            return OperationResult.ok(f"Fase D={chamfer.distance:.1f}mm erstellt")

        except Exception as e:
            logger.error(f"Chamfer failed: {e}")
            return OperationResult.error(f"Fase fehlgeschlagen: {e}")

    def execute(self, click_x: float, click_y: float, snap_radius: float, distance: float) -> OperationResult:
        """
        Kombinierte Suche + Berechnung + Ausführung.

        Args:
            click_x, click_y: Klick-Position
            snap_radius: Such-Radius für Ecken
            distance: Chamfer-Abstand

        Returns:
            OperationResult
        """
        corner_result = self.find_corner(click_x, click_y, snap_radius)
        if not corner_result.success:
            return OperationResult.no_target(corner_result.error)

        chamfer_result = self.calculate_chamfer(corner_result.data, distance)
        if not chamfer_result.success:
            return OperationResult.error(chamfer_result.error)

        return self.execute_chamfer(chamfer_result.data)
