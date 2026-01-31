"""
MashCad - Fillet 2D Operation (Extrahiert aus sketch_handlers.py)
=================================================================

Testbare 2D-Fillet-Operation mit klarer Schnittstelle.

Verwendung:
    from sketcher.operations import Fillet2DOperation

    op = Fillet2DOperation(sketch)
    result = op.find_corner(click_x, click_y, snap_radius)

    if result.success:
        fillet = op.calculate_fillet(result.data, radius=5.0)
        if fillet.success:
            op.execute_fillet(fillet.data)

Feature-Flag: "use_extracted_fillet_2d"
"""

import math
from dataclasses import dataclass
from typing import Optional, List, Tuple, TYPE_CHECKING
from loguru import logger

from .base import SketchOperation, OperationResult

if TYPE_CHECKING:
    from sketcher import Sketch, Point2D, Line2D, Arc2D


@dataclass
class CornerData:
    """Beschreibt eine gefundene Ecke zwischen zwei Linien."""
    line1: 'Line2D'
    line2: 'Line2D'
    corner_point: 'Point2D'
    other_point1: 'Point2D'  # Der andere Punkt von line1
    other_point2: 'Point2D'  # Der andere Punkt von line2
    attr1: str  # 'start' oder 'end' - welcher Punkt von line1 ist die Ecke
    attr2: str  # 'start' oder 'end' - welcher Punkt von line2 ist die Ecke


@dataclass
class FilletData:
    """Beschreibt ein berechnetes Fillet."""
    corner: CornerData
    radius: float
    center_x: float
    center_y: float
    tangent1_x: float
    tangent1_y: float
    tangent2_x: float
    tangent2_y: float
    start_angle: float  # In Grad
    end_angle: float    # In Grad


@dataclass
class CornerResult:
    """Ergebnis einer Ecken-Suche."""
    success: bool
    data: Optional[CornerData] = None
    error: str = ""

    @classmethod
    def ok(cls, data: CornerData) -> 'CornerResult':
        return cls(success=True, data=data)

    @classmethod
    def not_found(cls) -> 'CornerResult':
        return cls(success=False, error="Keine Ecke gefunden")


@dataclass
class FilletResult:
    """Ergebnis einer Fillet-Berechnung."""
    success: bool
    data: Optional[FilletData] = None
    error: str = ""

    @classmethod
    def ok(cls, data: FilletData) -> 'FilletResult':
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str) -> 'FilletResult':
        return cls(success=False, error=error)


class Fillet2DOperation(SketchOperation):
    """
    Extrahierte 2D-Fillet-Operation.

    Trennt Suche (find_corner), Berechnung (calculate_fillet) und
    Ausführung (execute_fillet) für bessere Testbarkeit.
    """

    def __init__(self, sketch: 'Sketch'):
        super().__init__(sketch)

    def find_corner(self, click_x: float, click_y: float, snap_radius: float) -> CornerResult:
        """
        Findet eine Ecke (wo zwei Linien sich treffen) nahe der Klick-Position.

        Args:
            click_x, click_y: Klick-Position
            snap_radius: Such-Radius

        Returns:
            CornerResult mit Ecken-Info oder Fehler
        """
        lines = self.sketch.lines

        for i, l1 in enumerate(lines):
            for l2 in lines[i + 1:]:
                # Prüfe alle Punkt-Kombinationen
                corners = [
                    (l1.start, l1.end, l2.start, l2.end, 'start', 'start'),
                    (l1.start, l1.end, l2.end, l2.start, 'start', 'end'),
                    (l1.end, l1.start, l2.start, l2.end, 'end', 'start'),
                    (l1.end, l1.start, l2.end, l2.start, 'end', 'end'),
                ]

                for corner1, other1, corner2, other2, attr1, attr2 in corners:
                    # Sind die Eckpunkte zusammen (gleich oder sehr nah)?
                    is_same = corner1 is corner2
                    is_close = math.hypot(corner1.x - corner2.x, corner1.y - corner2.y) < 1.0

                    if is_same or is_close:
                        # Ist der Klick nah an dieser Ecke?
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

    def calculate_fillet(self, corner: CornerData, radius: float) -> FilletResult:
        """
        Berechnet die Fillet-Geometrie für eine Ecke.

        Args:
            corner: CornerData von find_corner()
            radius: Fillet-Radius

        Returns:
            FilletResult mit Geometrie-Daten oder Fehler
        """
        corner_pt = corner.corner_point
        other1 = corner.other_point1
        other2 = corner.other_point2

        # Richtungsvektoren VON der Ecke WEG entlang der Linien
        d1 = (other1.x - corner_pt.x, other1.y - corner_pt.y)
        d2 = (other2.x - corner_pt.x, other2.y - corner_pt.y)

        # Normalisieren
        len1 = math.hypot(d1[0], d1[1])
        len2 = math.hypot(d2[0], d2[1])

        if len1 < 0.01 or len2 < 0.01:
            return FilletResult.fail("Linien zu kurz")

        d1 = (d1[0] / len1, d1[1] / len1)
        d2 = (d2[0] / len2, d2[1] / len2)

        # Winkel zwischen den Linien (immer der kleinere Winkel, 0 bis π)
        dot = d1[0] * d2[0] + d1[1] * d2[1]
        dot = max(-1, min(1, dot))
        angle_between = math.acos(dot)

        # Geometrie-Check
        if angle_between < 0.01 or angle_between > math.pi - 0.01:
            return FilletResult.fail("Linien zu parallel")

        half_angle = angle_between / 2

        # Abstand vom Corner zu den Tangentenpunkten
        tan_dist = radius / math.tan(half_angle)

        if tan_dist > len1 * 0.99 or tan_dist > len2 * 0.99:
            return FilletResult.fail("Radius zu groß")

        # Tangentenpunkte auf den Linien
        t1_x = corner_pt.x + d1[0] * tan_dist
        t1_y = corner_pt.y + d1[1] * tan_dist
        t2_x = corner_pt.x + d2[0] * tan_dist
        t2_y = corner_pt.y + d2[1] * tan_dist

        # Winkelhalbierender Vektor (d1 + d2)
        bisect_x = d1[0] + d2[0]
        bisect_y = d1[1] + d2[1]
        bisect_len = math.hypot(bisect_x, bisect_y)

        if bisect_len < 0.001:
            return FilletResult.fail("Ungültige Ecken-Geometrie")

        bisect_x /= bisect_len
        bisect_y /= bisect_len

        # Abstand vom Corner zum Arc-Zentrum
        center_dist = radius / math.sin(half_angle)

        # Arc-Zentrum (auf der INNENSEITE der Ecke)
        center_x = corner_pt.x + bisect_x * center_dist
        center_y = corner_pt.y + bisect_y * center_dist

        # Arc-Winkel berechnen (vom Zentrum aus gesehen)
        angle1 = math.degrees(math.atan2(t1_y - center_y, t1_x - center_x))
        angle2 = math.degrees(math.atan2(t2_y - center_y, t2_x - center_x))

        # Berechne den Sweep von angle1 zu angle2
        sweep = angle2 - angle1
        # Normalisiere auf [-180, 180] um den kurzen Weg zu finden
        while sweep > 180:
            sweep -= 360
        while sweep < -180:
            sweep += 360

        # Wähle Start/End so dass der Sweep positiv ist (CCW)
        if sweep >= 0:
            start_angle = angle1
            end_angle = angle2
        else:
            # Negativer sweep → tausche für positiven Sweep
            start_angle = angle2
            end_angle = angle1

        # Stelle sicher dass end > start (für positiven Sweep im Renderer)
        if end_angle < start_angle:
            end_angle += 360

        return FilletResult.ok(FilletData(
            corner=corner,
            radius=radius,
            center_x=center_x,
            center_y=center_y,
            tangent1_x=t1_x,
            tangent1_y=t1_y,
            tangent2_x=t2_x,
            tangent2_y=t2_y,
            start_angle=start_angle,
            end_angle=end_angle
        ))

    def execute_fillet(self, fillet: FilletData) -> OperationResult:
        """
        Führt das Fillet aus (modifiziert den Sketch).

        Args:
            fillet: FilletData von calculate_fillet()

        Returns:
            OperationResult
        """
        from sketcher import Point2D

        try:
            corner = fillet.corner
            l1 = corner.line1
            l2 = corner.line2

            # Neue Punkte erstellen
            new_pt1 = Point2D(fillet.tangent1_x, fillet.tangent1_y)
            new_pt2 = Point2D(fillet.tangent2_x, fillet.tangent2_y)
            self.sketch.points.append(new_pt1)
            self.sketch.points.append(new_pt2)

            # Linien verkürzen
            if corner.attr1 == 'start':
                l1.start = new_pt1
            else:
                l1.end = new_pt1

            if corner.attr2 == 'start':
                l2.start = new_pt2
            else:
                l2.end = new_pt2

            # Arc hinzufügen
            arc = self.sketch.add_arc(
                fillet.center_x,
                fillet.center_y,
                fillet.radius,
                fillet.start_angle,
                fillet.end_angle
            )

            # Radius-Constraint hinzufügen
            self.sketch.add_radius(arc, fillet.radius)

            logger.debug(f"[FILLET] Created R={fillet.radius:.1f}mm at "
                        f"({fillet.center_x:.2f}, {fillet.center_y:.2f})")

            return OperationResult.ok(f"Fillet R={fillet.radius:.1f}mm erstellt")

        except Exception as e:
            logger.error(f"Fillet failed: {e}")
            return OperationResult.error(f"Fillet fehlgeschlagen: {e}")

    def execute(self, click_x: float, click_y: float, snap_radius: float, radius: float) -> OperationResult:
        """
        Kombinierte Suche + Berechnung + Ausführung.

        Args:
            click_x, click_y: Klick-Position
            snap_radius: Such-Radius für Ecken
            radius: Fillet-Radius

        Returns:
            OperationResult
        """
        corner_result = self.find_corner(click_x, click_y, snap_radius)
        if not corner_result.success:
            return OperationResult.no_target(corner_result.error)

        fillet_result = self.calculate_fillet(corner_result.data, radius)
        if not fillet_result.success:
            return OperationResult.error(fillet_result.error)

        return self.execute_fillet(fillet_result.data)
