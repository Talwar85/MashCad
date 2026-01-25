"""
MashCad - BREP Face Factory
===========================

Erstellt OCP TopoDS_Face Objekte aus DetectedPrimitive.
Verwendet moderne OCP API (KEIN deprecated GetHandle()).
"""

import numpy as np
from typing import Optional, List
from loguru import logger

try:
    from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax2, gp_Ax3, gp_Pln
    from OCP.Geom import Geom_CylindricalSurface, Geom_SphericalSurface, Geom_ConicalSurface
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeWire,
        BRepBuilderAPI_MakeFace
    )
    from OCP.TopoDS import TopoDS_Face, TopoDS_Wire
    HAS_OCP = True
except ImportError:
    HAS_OCP = False
    logger.warning("OCP nicht verfügbar")

from meshconverter.mesh_converter_v10 import DetectedPrimitive


class BRepFaceFactory:
    """
    Factory für BREP Face-Erstellung aus Primitiven.

    Unterstützte Typen:
    - plane → gp_Pln + Polygon-Wire
    - cylinder → Geom_CylindricalSurface + UV-Bounds
    - sphere → Geom_SphericalSurface + UV-Bounds
    - cone → Geom_ConicalSurface + UV-Bounds
    - bspline → Geom_BSplineSurface (via NURBSFitter)
    """

    def __init__(self, tolerance: float = 1e-6):
        """
        Args:
            tolerance: Geometrische Toleranz für Face-Erstellung
        """
        self.tolerance = tolerance

    def create_face(self, primitive: DetectedPrimitive) -> Optional['TopoDS_Face']:
        """
        Erstellt TopoDS_Face aus DetectedPrimitive.

        Args:
            primitive: Erkanntes Primitiv

        Returns:
            TopoDS_Face oder None bei Fehler
        """
        if not HAS_OCP:
            logger.error("OCP nicht verfügbar")
            return None

        try:
            if primitive.type == "plane":
                return self._create_planar_face(primitive)
            elif primitive.type == "cylinder":
                return self._create_cylindrical_face(primitive)
            elif primitive.type == "sphere":
                return self._create_spherical_face(primitive)
            elif primitive.type == "cone":
                return self._create_conical_face(primitive)
            elif primitive.type == "bspline":
                return self._create_bspline_face(primitive)
            else:
                logger.warning(f"Unbekannter Primitiv-Typ: {primitive.type}")
                return None

        except Exception as e:
            logger.error(f"Face-Erstellung fehlgeschlagen ({primitive.type}): {e}")
            import traceback
            traceback.print_exc()
            return None

    # =========================================================================
    # Planar Face
    # =========================================================================

    def _create_planar_face(self, prim: DetectedPrimitive) -> Optional['TopoDS_Face']:
        """
        Erstellt planare Face mit Boundary-Wire.
        """
        origin = np.array(prim.params['origin'])
        normal = np.array(prim.params['normal'])
        boundary = prim.boundary_points

        if boundary is None or len(boundary) < 3:
            logger.warning("Keine Boundary-Punkte für planare Face")
            return None

        # Normal normalisieren
        normal = normal / (np.linalg.norm(normal) + 1e-10)

        # gp_Pln erstellen
        gp_origin = gp_Pnt(float(origin[0]), float(origin[1]), float(origin[2]))
        gp_normal = gp_Dir(float(normal[0]), float(normal[1]), float(normal[2]))
        plane = gp_Pln(gp_origin, gp_normal)

        # Boundary-Wire erstellen
        wire = self._create_wire_from_points(boundary)
        if wire is None:
            return None

        # Face aus Plane und Wire
        try:
            face_builder = BRepBuilderAPI_MakeFace(plane, wire)
            if face_builder.IsDone():
                return face_builder.Face()
            else:
                logger.warning("BRepBuilderAPI_MakeFace (plane) fehlgeschlagen")
                return None
        except Exception as e:
            logger.warning(f"Planare Face Erstellung fehlgeschlagen: {e}")
            return None

    # =========================================================================
    # Cylindrical Face
    # =========================================================================

    def _create_cylindrical_face(self, prim: DetectedPrimitive) -> Optional['TopoDS_Face']:
        """
        Erstellt zylindrische Face.
        """
        center = np.array(prim.params['center'])
        axis = np.array(prim.params['axis'])
        radius = float(prim.params['radius'])
        height = float(prim.params['height'])

        if radius <= 0 or height <= 0:
            return None

        # Achse normalisieren
        axis = axis / (np.linalg.norm(axis) + 1e-10)

        # Koordinatensystem erstellen
        gp_center = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))
        gp_axis = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))

        # X-Richtung für Ax3 (beliebig, aber senkrecht zu axis)
        if abs(axis[2]) < 0.9:
            x_dir = np.cross(axis, [0, 0, 1])
        else:
            x_dir = np.cross(axis, [1, 0, 0])
        x_dir = x_dir / (np.linalg.norm(x_dir) + 1e-10)
        gp_x_dir = gp_Dir(float(x_dir[0]), float(x_dir[1]), float(x_dir[2]))

        ax3 = gp_Ax3(gp_center, gp_axis, gp_x_dir)

        # Zylindrische Oberfläche erstellen
        cylinder_surface = Geom_CylindricalSurface(ax3, radius)

        # Face mit U/V Bounds
        # U: 0 bis 2*pi (voller Umfang)
        # V: -height/2 bis +height/2
        u_min, u_max = 0.0, 2 * np.pi
        v_min, v_max = -height / 2, height / 2

        try:
            face_builder = BRepBuilderAPI_MakeFace(
                cylinder_surface,
                u_min, u_max,
                v_min, v_max,
                self.tolerance
            )
            if face_builder.IsDone():
                return face_builder.Face()
            else:
                logger.warning("BRepBuilderAPI_MakeFace (cylinder) fehlgeschlagen")
                return None
        except Exception as e:
            logger.warning(f"Zylindrische Face Erstellung fehlgeschlagen: {e}")
            return None

    # =========================================================================
    # Spherical Face
    # =========================================================================

    def _create_spherical_face(self, prim: DetectedPrimitive) -> Optional['TopoDS_Face']:
        """
        Erstellt sphärische Face.
        """
        center = np.array(prim.params['center'])
        radius = float(prim.params['radius'])

        if radius <= 0:
            return None

        # Koordinatensystem (Z-Achse nach oben)
        gp_center = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))
        gp_axis = gp_Dir(0, 0, 1)
        gp_x_dir = gp_Dir(1, 0, 0)

        ax3 = gp_Ax3(gp_center, gp_axis, gp_x_dir)

        # Sphärische Oberfläche
        sphere_surface = Geom_SphericalSurface(ax3, radius)

        # Face mit U/V Bounds
        # U: 0 bis 2*pi (Longitude)
        # V: -pi/2 bis +pi/2 (Latitude, -90° bis +90°)
        # Für Teil-Kugel müsste V eingeschränkt werden
        u_min, u_max = 0.0, 2 * np.pi
        v_min, v_max = -np.pi / 2, np.pi / 2

        try:
            face_builder = BRepBuilderAPI_MakeFace(
                sphere_surface,
                u_min, u_max,
                v_min, v_max,
                self.tolerance
            )
            if face_builder.IsDone():
                return face_builder.Face()
            else:
                logger.warning("BRepBuilderAPI_MakeFace (sphere) fehlgeschlagen")
                return None
        except Exception as e:
            logger.warning(f"Sphärische Face Erstellung fehlgeschlagen: {e}")
            return None

    # =========================================================================
    # Conical Face
    # =========================================================================

    def _create_conical_face(self, prim: DetectedPrimitive) -> Optional['TopoDS_Face']:
        """
        Erstellt konische Face.
        """
        apex = np.array(prim.params['apex'])
        axis = np.array(prim.params['axis'])
        half_angle = float(prim.params['half_angle'])
        height = float(prim.params['height'])

        if half_angle <= 0 or half_angle >= np.pi / 2 or height <= 0:
            return None

        # Achse normalisieren
        axis = axis / (np.linalg.norm(axis) + 1e-10)

        # Koordinatensystem am Apex
        gp_apex = gp_Pnt(float(apex[0]), float(apex[1]), float(apex[2]))
        gp_axis = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))

        # X-Richtung
        if abs(axis[2]) < 0.9:
            x_dir = np.cross(axis, [0, 0, 1])
        else:
            x_dir = np.cross(axis, [1, 0, 0])
        x_dir = x_dir / (np.linalg.norm(x_dir) + 1e-10)
        gp_x_dir = gp_Dir(float(x_dir[0]), float(x_dir[1]), float(x_dir[2]))

        ax3 = gp_Ax3(gp_apex, gp_axis, gp_x_dir)

        # Konische Oberfläche
        # Geom_ConicalSurface(Ax3, half_angle, reference_radius)
        # reference_radius ist der Radius bei V=0 (am Apex wäre das 0)
        reference_radius = 0.0  # Am Apex
        cone_surface = Geom_ConicalSurface(ax3, half_angle, reference_radius)

        # Face mit U/V Bounds
        # U: 0 bis 2*pi
        # V: 0 bis height (Abstand vom Apex entlang der Achse)
        u_min, u_max = 0.0, 2 * np.pi
        v_min, v_max = 0.0, height

        try:
            face_builder = BRepBuilderAPI_MakeFace(
                cone_surface,
                u_min, u_max,
                v_min, v_max,
                self.tolerance
            )
            if face_builder.IsDone():
                return face_builder.Face()
            else:
                logger.warning("BRepBuilderAPI_MakeFace (cone) fehlgeschlagen")
                return None
        except Exception as e:
            logger.warning(f"Konische Face Erstellung fehlgeschlagen: {e}")
            return None

    # =========================================================================
    # B-Spline Face
    # =========================================================================

    def _create_bspline_face(self, prim: DetectedPrimitive) -> Optional['TopoDS_Face']:
        """
        Erstellt B-Spline Face aus vorher gefitteter Surface.
        """
        if 'surface' not in prim.params:
            logger.warning("Keine B-Spline Surface in Primitiv")
            return None

        surface = prim.params['surface']

        try:
            # Surface ist bereits ein Geom_BSplineSurface
            # Hole U/V Bounds
            u_min = surface.FirstUParameter()
            u_max = surface.LastUParameter()
            v_min = surface.FirstVParameter()
            v_max = surface.LastVParameter()

            face_builder = BRepBuilderAPI_MakeFace(
                surface,
                u_min, u_max,
                v_min, v_max,
                self.tolerance
            )

            if face_builder.IsDone():
                return face_builder.Face()
            else:
                logger.warning("BRepBuilderAPI_MakeFace (bspline) fehlgeschlagen")
                return None

        except Exception as e:
            logger.warning(f"B-Spline Face Erstellung fehlgeschlagen: {e}")
            return None

    # =========================================================================
    # Helper: Wire aus Punkten
    # =========================================================================

    def _create_wire_from_points(self, points: np.ndarray) -> Optional['TopoDS_Wire']:
        """
        Erstellt geschlossenen Wire aus geordneten Punkten.

        Rundet Koordinaten auf 0.001mm für konsistentes Edge-Matching beim Sewing.
        """
        if len(points) < 3:
            return None

        try:
            wire_builder = BRepBuilderAPI_MakeWire()

            # Runde Punkte auf 0.01mm Präzision für konsistentes Matching
            # (gröbere Rundung hilft bei leichten Koordinaten-Unterschieden)
            precision = 2  # 2 Dezimalstellen = 0.01mm
            rounded_points = np.round(points, precision)

            for i in range(len(rounded_points)):
                p1 = rounded_points[i]
                p2 = rounded_points[(i + 1) % len(rounded_points)]

                # Überprüfe ob Punkte verschieden sind
                if np.linalg.norm(p2 - p1) < 1e-6:
                    continue

                gp_p1 = gp_Pnt(float(p1[0]), float(p1[1]), float(p1[2]))
                gp_p2 = gp_Pnt(float(p2[0]), float(p2[1]), float(p2[2]))

                edge_builder = BRepBuilderAPI_MakeEdge(gp_p1, gp_p2)
                if edge_builder.IsDone():
                    wire_builder.Add(edge_builder.Edge())

            if wire_builder.IsDone():
                return wire_builder.Wire()
            else:
                logger.warning("Wire-Erstellung fehlgeschlagen")
                return None

        except Exception as e:
            logger.warning(f"Wire-Erstellung fehlgeschlagen: {e}")
            return None
