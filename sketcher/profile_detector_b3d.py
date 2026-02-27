"""
Build123d-basierte Profile-Detection
=====================================

Exakte Profile-Detection mit Build123d/OpenCASCADE statt Shapely-Approximation.

Vorteile:
- Kreise bleiben echte Kreise (keine 64-Eck Polygone)
- Konsistenz zwischen 2D-Preview und 3D-Extrusion
- OpenCASCADE macht Boolean/Intersection automatisch korrekt

Verwendung:
    detector = Build123dProfileDetector()
    faces = detector.detect_profiles(sketch)
    # faces ist eine Liste von Build123d Face-Objekten
"""

from typing import List, Optional, Tuple, TYPE_CHECKING
from loguru import logger
import math

if TYPE_CHECKING:
    from sketcher import Sketch

# Build123d imports (lazy, da nicht immer verfügbar)
try:
    from build123d import (
        BuildSketch, BuildLine, BuildPart,
        Line as B3DLine, Circle as B3DCircle,
        CenterArc, Polyline, Wire, Face, Edge,
        Plane, Locations, make_face, Sketch as B3DSketch
    )
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace
    from OCP.TopoDS import TopoDS_Wire, TopoDS_Face, TopoDS_Edge
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_WIRE, TopAbs_EDGE
    from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
    from OCP.TopTools import TopTools_HSequenceOfShape
    from OCP.gp import gp_Pln, gp_Ax3, gp_Pnt, gp_Dir
    HAS_BUILD123D = True
except ImportError as e:
    logger.debug(f"Build123d imports fehlgeschlagen: {e}")
    HAS_BUILD123D = False


class Build123dProfileDetector:
    """
    Exakte Profile-Detection mit Build123d/OpenCASCADE.

    Im Gegensatz zur Shapely-basierten Detection:
    - Kreise bleiben analytische Kurven
    - Überlappungen werden exakt berechnet (keine Polygonisierung)
    - Ergebnis ist direkt für Build123d extrude() nutzbar
    """

    def __init__(self, tolerance: float = 1e-4):
        """
        Args:
            tolerance: Toleranz für Punkt-Verschweißung (mm)
        """
        self.tolerance = tolerance
        self._last_error: Optional[str] = None

    @property
    def last_error(self) -> Optional[str]:
        """Letzte Fehlermeldung (für Debugging)"""
        return self._last_error

    def detect_profiles(self, sketch: 'Sketch', plane: Optional['Plane'] = None) -> List['Face']:
        """
        Konvertiert Sketch-Geometrie zu Build123d und findet alle geschlossenen Faces.

        Args:
            sketch: MashCAD Sketch-Objekt
            plane: Build123d Plane (default: XY)

        Returns:
            Liste von Build123d Face-Objekten, bereit für extrude()
        """
        if not HAS_BUILD123D:
            self._last_error = "Build123d nicht verfügbar"
            logger.warning(self._last_error)
            return []

        self._last_error = None

        if plane is None:
            plane = Plane.XY

        # Sammle alle nicht-construction Geometrie
        lines = [l for l in sketch.lines if not l.construction]
        circles = [c for c in sketch.circles if not c.construction]
        arcs = [a for a in sketch.arcs if not a.construction]

        if not lines and not circles and not arcs:
            self._last_error = "Keine Geometrie im Sketch"
            return []

        logger.debug(f"Profile-Detection: {len(lines)} Linien, {len(circles)} Kreise, {len(arcs)} Arcs")

        try:
            # Methode 1: Direkte Edge-basierte Face-Erkennung mit OCP
            faces = self._detect_faces_ocp(lines, circles, arcs, plane)

            if faces:
                logger.info(f"Build123d Profile-Detection: {len(faces)} Faces gefunden")
                return faces

            # Fallback: BuildSketch mit make_face()
            return self._detect_faces_buildsketch(lines, circles, arcs, plane)

        except Exception as e:
            self._last_error = f"Profile-Detection fehlgeschlagen: {e}"
            logger.error(self._last_error)
            import traceback
            traceback.print_exc()
            return []

    def _detect_faces_ocp(self, lines, circles, arcs, plane) -> List['Face']:
        """
        Nutzt OCP/OpenCASCADE direkt für Face-Detection.

        ShapeAnalysis_FreeBounds findet automatisch geschlossene Konturen
        aus einer Menge von Edges.
        """
        try:
            # 1. Alle Edges in OCP-Format konvertieren
            ocp_edges = []

            # Linien zu OCP Edges
            for line in lines:
                try:
                    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
                    from OCP.gp import gp_Pnt

                    p1 = gp_Pnt(line.start.x, line.start.y, 0)
                    p2 = gp_Pnt(line.end.x, line.end.y, 0)

                    # Degenerierte Edges überspringen
                    if p1.Distance(p2) < self.tolerance:
                        continue

                    edge = BRepBuilderAPI_MakeEdge(p1, p2).Edge()
                    ocp_edges.append(edge)
                except Exception as e:
                    logger.debug(f"Linie konnte nicht konvertiert werden: {e}")

            # Kreise zu OCP Edges (geschlossene Kurven)
            for circle in circles:
                try:
                    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
                    from OCP.gp import gp_Circ, gp_Ax2, gp_Pnt, gp_Dir

                    center = gp_Pnt(circle.center.x, circle.center.y, 0)
                    axis = gp_Ax2(center, gp_Dir(0, 0, 1))
                    ocp_circle = gp_Circ(axis, circle.radius)

                    edge = BRepBuilderAPI_MakeEdge(ocp_circle).Edge()
                    ocp_edges.append(edge)
                except Exception as e:
                    logger.debug(f"Kreis konnte nicht konvertiert werden: {e}")

            # Arcs zu OCP Edges
            for arc in arcs:
                try:
                    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
                    from OCP.GC import GC_MakeArcOfCircle
                    from OCP.gp import gp_Pnt

                    # Start- und Endpunkt des Arcs
                    start_rad = math.radians(arc.start_angle)
                    end_rad = math.radians(arc.end_angle)

                    # Sweep berechnen - Richtung BEIBEHALTEN!
                    sweep = arc.end_angle - arc.start_angle
                    # Normalisiere auf [-360, 360] aber behalte das Vorzeichen
                    while sweep > 360:
                        sweep -= 360
                    while sweep < -360:
                        sweep += 360

                    # Für Fillet-Arcs (< 180°) den KURZEN Bogen nehmen
                    # Wenn sweep > 180, nimm den kurzen Weg (negativer sweep)
                    # Wenn sweep < -180, nimm den kurzen Weg (positiver sweep)
                    if sweep > 180:
                        sweep -= 360
                    elif sweep < -180:
                        sweep += 360

                    # Mittelpunkt auf dem Arc
                    mid_angle = math.radians(arc.start_angle + sweep / 2)

                    p1 = gp_Pnt(
                        arc.center.x + arc.radius * math.cos(start_rad),
                        arc.center.y + arc.radius * math.sin(start_rad),
                        0
                    )
                    p2 = gp_Pnt(
                        arc.center.x + arc.radius * math.cos(end_rad),
                        arc.center.y + arc.radius * math.sin(end_rad),
                        0
                    )
                    p_mid = gp_Pnt(
                        arc.center.x + arc.radius * math.cos(mid_angle),
                        arc.center.y + arc.radius * math.sin(mid_angle),
                        0
                    )

                    # Arc durch 3 Punkte
                    arc_maker = GC_MakeArcOfCircle(p1, p_mid, p2)
                    if arc_maker.IsDone():
                        edge = BRepBuilderAPI_MakeEdge(arc_maker.Value()).Edge()
                        ocp_edges.append(edge)
                except Exception as e:
                    logger.debug(f"Arc konnte nicht konvertiert werden: {e}")

            if not ocp_edges:
                return []

            logger.debug(f"Build123d Profile-Detection: {len(lines)} Linien, {len(arcs)} Arcs → {len(ocp_edges)} OCP Edges")

            # 2. ShapeAnalysis_FreeBounds für Wire-Erkennung
            edge_sequence = TopTools_HSequenceOfShape()
            for edge in ocp_edges:
                edge_sequence.Append(edge)

            wire_sequence = TopTools_HSequenceOfShape()

            # FreeBounds findet geschlossene Wires aus Edges
            ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(
                edge_sequence,
                self.tolerance,  # tolerance
                False,  # shared edges
                wire_sequence
            )

            logger.debug(f"Build123d: {wire_sequence.Length()} Wires gefunden")

            # 3. Wires zu Faces konvertieren
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
            from OCP.gp import gp_Pln, gp_Ax3, gp_Pnt, gp_Dir
            from OCP.TopoDS import TopoDS
            from OCP.TopAbs import TopAbs_WIRE

            faces = []
            gp_plane = gp_Pln(gp_Ax3(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)))

            for i in range(1, wire_sequence.Length() + 1):
                wire_shape = wire_sequence.Value(i)
                # FIX: TopoDS.Wire() statt TopoDS_Wire(wire_shape)
                wire = TopoDS.Wire_s(wire_shape)

                try:
                    is_closed = wire.Closed()
                    if not is_closed:
                        continue

                    # Face aus Wire erstellen
                    face_maker = BRepBuilderAPI_MakeFace(gp_plane, wire)
                    if face_maker.IsDone():
                        ocp_face = face_maker.Face()

                        # Zu Build123d Face konvertieren
                        from build123d import Face as B3DFace
                        b3d_face = B3DFace(ocp_face)
                        faces.append(b3d_face)
                except Exception as e:
                    logger.debug(f"Wire zu Face fehlgeschlagen: {e}")

            return faces

        except Exception as e:
            logger.debug(f"OCP Face-Detection fehlgeschlagen: {e}")
            return []

    def _detect_faces_buildsketch(self, lines, circles, arcs, plane) -> List['Face']:
        """
        Fallback: Nutzt BuildSketch mit make_face().

        Dies ist weniger robust als die direkte OCP-Methode,
        aber funktioniert wenn alle Edges einen geschlossenen Kontur bilden.
        """
        try:
            with BuildSketch(plane) as sketch:
                edges_created = False

                # Linien
                for line in lines:
                    try:
                        with BuildLine():
                            B3DLine(
                                (line.start.x, line.start.y),
                                (line.end.x, line.end.y)
                            )
                        edges_created = True
                    except Exception as e:
                        logger.debug(f"Linie zu BuildSketch fehlgeschlagen: {e}")

                # Kreise (geschlossene Kurven = automatisch Faces)
                for circle in circles:
                    try:
                        # FIX: Kreise direkt als Faces erstellen (Build123d Circle erzeugt automatisch Face)
                        with Locations([(circle.center.x, circle.center.y)]):
                            circle_face = B3DCircle(radius=circle.radius)
                        # B3DCircle in BuildSketch erzeugt automatisch ein Face
                        edges_created = True
                    except Exception as e:
                        logger.debug(f"Kreis zu Face fehlgeschlagen: {e}")

                # Arcs
                for arc in arcs:
                    try:
                        sweep = arc.end_angle - arc.start_angle
                        if sweep < 0:
                            sweep += 360

                        with BuildLine():
                            CenterArc(
                                center=(arc.center.x, arc.center.y),
                                radius=arc.radius,
                                start_angle=arc.start_angle,
                                arc_size=sweep
                            )
                        edges_created = True
                    except Exception as e:
                        logger.debug(f"Arc zu BuildSketch fehlgeschlagen: {e}")

                if edges_created:
                    # make_face() findet alle geschlossenen Konturen
                    make_face()

            # Faces aus dem Sketch extrahieren
            if sketch.faces():
                return list(sketch.faces())

            return []

        except Exception as e:
            logger.debug(f"BuildSketch Face-Detection fehlgeschlagen: {e}")
            return []

    def get_profiles_for_extrude(self, sketch: 'Sketch', plane: Optional['Plane'] = None) -> Tuple[List['Face'], Optional[str]]:
        """
        High-level Methode für Extrude-Integration.

        Args:
            sketch: MashCAD Sketch-Objekt
            plane: Build123d Plane

        Returns:
            Tuple von (faces, error_message)
            - faces: Liste von Face-Objekten
            - error_message: None bei Erfolg, sonst Fehlerbeschreibung
        """
        faces = self.detect_profiles(sketch, plane)

        if not faces:
            return [], self._last_error or "Keine geschlossenen Profile gefunden"

        return faces, None


def is_available() -> bool:
    """Prüft ob Build123d verfügbar ist."""
    return HAS_BUILD123D
