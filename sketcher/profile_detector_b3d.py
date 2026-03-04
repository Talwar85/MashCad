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

    def _point_key(self, x: float, y: float) -> Tuple[int, int]:
        scale = max(self.tolerance, 1e-9)
        return (round(x / scale), round(y / scale))

    def _has_open_contours(self, lines, arcs, bezier_splines=None, native_splines=None) -> bool:
        """Reject sketches with unmatched open endpoints before OCP face creation."""
        endpoint_degree = {}

        def add_endpoint(x: float, y: float) -> None:
            key = self._point_key(x, y)
            endpoint_degree[key] = endpoint_degree.get(key, 0) + 1

        for line in lines:
            add_endpoint(line.start.x, line.start.y)
            add_endpoint(line.end.x, line.end.y)

        for arc in arcs:
            start_rad = math.radians(arc.start_angle)
            end_rad = math.radians(arc.end_angle)
            start_x = arc.center.x + arc.radius * math.cos(start_rad)
            start_y = arc.center.y + arc.radius * math.sin(start_rad)
            end_x = arc.center.x + arc.radius * math.cos(end_rad)
            end_y = arc.center.y + arc.radius * math.sin(end_rad)
            add_endpoint(start_x, start_y)
            add_endpoint(end_x, end_y)

        for spline in (bezier_splines or []):
            if not spline.closed and len(spline.control_points) >= 2:
                p0 = spline.control_points[0].point
                pn = spline.control_points[-1].point
                add_endpoint(p0.x, p0.y)
                add_endpoint(pn.x, pn.y)

        for spline in (native_splines or []):
            sp = spline.start_point
            ep = spline.end_point
            add_endpoint(sp.x, sp.y)
            add_endpoint(ep.x, ep.y)

        return any(degree % 2 != 0 for degree in endpoint_degree.values())

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
        ellipses = [e for e in getattr(sketch, 'ellipses', []) if not e.construction]
        bezier_splines = [s for s in getattr(sketch, 'splines', []) if not s.construction]
        native_splines = [s for s in getattr(sketch, 'native_splines', []) if not s.construction]

        if not lines and not circles and not arcs and not ellipses and not bezier_splines and not native_splines:
            self._last_error = "Keine Geometrie im Sketch"
            return []

        logger.debug(f"Profile-Detection: {len(lines)} Linien, {len(circles)} Kreise, {len(arcs)} Arcs, "
                     f"{len(ellipses)} Ellipsen, {len(bezier_splines)} BezierSplines, {len(native_splines)} NativeSplines")

        if self._has_open_contours(lines, arcs, bezier_splines, native_splines):
            self._last_error = "Offene Konturen im Sketch"
            logger.debug(self._last_error)
            return []

        try:
            # Methode 1: Direkte Edge-basierte Face-Erkennung mit OCP
            faces = self._detect_faces_ocp(lines, circles, arcs, plane, ellipses, bezier_splines, native_splines)

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

    def _detect_faces_ocp(self, lines, circles, arcs, plane, ellipses=None, bezier_splines=None, native_splines=None) -> List['Face']:
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

            # Ellipsen zu OCP Edges (geschlossene Kurven)
            for ellipse in (ellipses or []):
                try:
                    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
                    from OCP.GC import GC_MakeEllipse
                    from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir

                    cx, cy = ellipse.center.x, ellipse.center.y
                    rx, ry = ellipse.radius_x, ellipse.radius_y
                    rotation = getattr(ellipse, 'rotation', 0.0)

                    center = gp_Pnt(cx, cy, 0)
                    rot_rad = math.radians(rotation)
                    major_dir = gp_Dir(math.cos(rot_rad), math.sin(rot_rad), 0)
                    axis = gp_Ax2(center, gp_Dir(0, 0, 1), major_dir)

                    ellipse_maker = GC_MakeEllipse(axis, rx, ry)
                    if ellipse_maker.IsDone():
                        edge = BRepBuilderAPI_MakeEdge(ellipse_maker.Value()).Edge()
                        ocp_edges.append(edge)
                except Exception as e:
                    logger.debug(f"Ellipse konnte nicht konvertiert werden: {e}")

            # BezierSplines zu OCP Edges (kubische Bézier-Segmente)
            for spline in (bezier_splines or []):
                try:
                    from OCP.Geom import Geom_BezierCurve
                    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
                    from OCP.TColgp import TColgp_Array1OfPnt
                    from OCP.gp import gp_Pnt

                    cps = spline.control_points
                    n_segments = len(cps) if spline.closed else len(cps) - 1

                    for i in range(n_segments):
                        p0 = cps[i]
                        p1 = cps[(i + 1) % len(cps)]

                        # Kubische Bézier: 4 Kontrollpunkte (P0, handle_out, handle_in, P1)
                        poles = TColgp_Array1OfPnt(1, 4)
                        poles.SetValue(1, gp_Pnt(p0.point.x, p0.point.y, 0))
                        poles.SetValue(2, gp_Pnt(*p0.handle_out_abs, 0))
                        poles.SetValue(3, gp_Pnt(*p1.handle_in_abs, 0))
                        poles.SetValue(4, gp_Pnt(p1.point.x, p1.point.y, 0))

                        bezier = Geom_BezierCurve(poles)
                        edge = BRepBuilderAPI_MakeEdge(bezier).Edge()
                        ocp_edges.append(edge)
                except Exception as e:
                    logger.debug(f"BezierSpline konnte nicht konvertiert werden: {e}")

            # Native Splines (B-Spline/NURBS aus DXF) zu OCP Edges
            for spline in (native_splines or []):
                try:
                    from OCP.Geom import Geom_BSplineCurve
                    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
                    from OCP.TColgp import TColgp_Array1OfPnt
                    from OCP.TColStd import TColStd_Array1OfReal, TColStd_Array1OfInteger
                    from OCP.gp import gp_Pnt

                    n = len(spline.control_points)
                    if n < 2:
                        continue

                    poles = TColgp_Array1OfPnt(1, n)
                    for i, (x, y) in enumerate(spline.control_points):
                        poles.SetValue(i + 1, gp_Pnt(x, y, 0))

                    weights = TColStd_Array1OfReal(1, n)
                    for i, w in enumerate(spline.weights):
                        weights.SetValue(i + 1, w)

                    unique_knots = sorted(set(spline.knots))
                    multiplicities = [spline.knots.count(k) for k in unique_knots]

                    knots_arr = TColStd_Array1OfReal(1, len(unique_knots))
                    mults_arr = TColStd_Array1OfInteger(1, len(unique_knots))
                    for i, (k, m) in enumerate(zip(unique_knots, multiplicities)):
                        knots_arr.SetValue(i + 1, k)
                        mults_arr.SetValue(i + 1, m)

                    curve = Geom_BSplineCurve(poles, weights, knots_arr, mults_arr, spline.degree)
                    edge = BRepBuilderAPI_MakeEdge(curve).Edge()
                    ocp_edges.append(edge)
                except Exception as e:
                    logger.debug(f"Native Spline konnte nicht konvertiert werden: {e}")

            if not ocp_edges:
                return []

            logger.debug(f"Build123d Profile-Detection: {len(lines)} Linien, {len(arcs)} Arcs, "
                        f"{len(ellipses or [])} Ellipsen, {len(bezier_splines or [])} BezierSplines, "
                        f"{len(native_splines or [])} NativeSplines → {len(ocp_edges)} OCP Edges")

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
