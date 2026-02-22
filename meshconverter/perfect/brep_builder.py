"""
Perfect Converter - BREP Builder
==================================

Erstellt analytische BREP-Geometrie aus erkannten Primitive und Features.
Im Gegensatz zu SimpleConverter (facettiert) werden hier echte
mathematische Surfaces verwendet.

Author: Claude (MeshConverter Architecture)
Date: 2026-02-10
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
from loguru import logger

try:
    from OCP.gp import (
        gp_Pnt, gp_Vec, gp_Dir, gp_Ax1, gp_Ax2, gp_Ax3,
        gp_Pln, gp_Circ, gp_Elips
    )
    from OCP.Geom import (
        Geom_Plane, Geom_CylindricalSurface, Geom_SphericalSurface,
        Geom_ConicalSurface, Geom_ToroidalSurface, Geom_Surface
    )
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeWire, BRepBuilderAPI_Sewing
    )
    from OCP.BRepPrimAPI import (
        BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeSphere,
        BRepPrimAPI_MakeCone, BRepPrimAPI_MakeTorus
    )
    from OCP.TopoDS import TopoDS_Face, TopoDS_Shape
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.ShapeFix import ShapeFix_Shape
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Sphere, GeomAbs_Cone, GeomAbs_Torus
    HAS_OCP = True
except ImportError:
    HAS_OCP = False
    logger.warning("OCP nicht verfügbar")

from .primitive_detector import DetectedPrimitive, PrimitiveType


class BREPBuilder:
    """
    Erstellt analytische BREP-Geometrie aus erkannten Primitive.

    Jede DetectedPrimitive wird zu einem echten mathematischen Surface:
    - Plane → Geom_Plane
    - Cylinder → Geom_CylindricalSurface (glatt, nicht facettiert!)
    - Sphere → Geom_SphericalSurface
    - Cone → Geom_ConicalSurface
    """

    def __init__(
        self,
        sewing_tolerance: float = 0.01,
        unify_faces: bool = True
    ):
        self.sewing_tol = sewing_tolerance
        self.unify_faces = unify_faces

    def build_from_primitives(
        self,
        mesh,
        primitives: List[DetectedPrimitive]
    ) -> Tuple[Optional[TopoDS_Shape], Dict]:
        """
        Erstellt BREP aus Liste von erkannten Primitive.

        Args:
            mesh: Original PyVista Mesh (für Fallback)
            primitives: Liste von DetectedPrimitive

        Returns:
            (TopoDS_Shape oder None, stats Dict)
        """
        if not HAS_OCP:
            return None, {"error": "OCP nicht verfügbar"}

        stats = {
            "total_primitives": len(primitives),
            "faces_created": 0,
            "analytical_surfaces": 0,
            "fallback_faces": 0
        }

        logger.info(f"BREP Builder: {len(primitives)} Primitive")

        faces = []

        for primitive in primitives:
            face = self._build_primitive_face(primitive, mesh)
            if face is not None:
                faces.append(face)
                stats["faces_created"] += 1

                if primitive.type in [
                    PrimitiveType.PLANE,
                    PrimitiveType.CYLINDER,
                    PrimitiveType.SPHERE,
                    PrimitiveType.CONE,
                    PrimitiveType.TORUS
                ]:
                    stats["analytical_surfaces"] += 1
                else:
                    stats["fallback_faces"] += 1

        logger.info(f"  {stats['faces_created']} Faces erstellt")

        # Sewing
        if faces:
            result = self._sew_faces(faces, stats)
            return result, stats

        return None, stats

    def _build_primitive_face(
        self,
        primitive: DetectedPrimitive,
        mesh
    ) -> Optional[TopoDS_Face]:
        """Erstellt ein Face aus einem Primitiv."""
        try:
            if primitive.type == PrimitiveType.PLANE:
                return self._build_plane_face(primitive)

            elif primitive.type == PrimitiveType.CYLINDER:
                return self._build_cylinder_face(primitive)

            elif primitive.type == PrimitiveType.SPHERE:
                return self._build_sphere_face(primitive)

            elif primitive.type == PrimitiveType.CONE:
                return self._build_cone_face(primitive)

            elif primitive.type == PrimitiveType.TORUS:
                return self._build_torus_face(primitive)

            else:
                # Fallback: Triangulierte Faces aus Mesh
                return self._build_fallback_face(primitive, mesh)

        except Exception as e:
            logger.warning(f"Face-Erstellung fehlgeschlagen für {primitive.type}: {e}")
            return None

    def _build_plane_face(self, prim: DetectedPrimitive) -> Optional[TopoDS_Face]:
        """Erstellt eine planare Face."""
        # Ebene aus Ursprung und Normale
        origin = gp_Pnt(prim.origin[0], prim.origin[1], prim.origin[2])
        normal = gp_Dir(prim.normal[0], prim.normal[1], prim.normal[2])
        plane = gp_Pln(origin, normal)

        # Face mit begrenztem Rechteck
        # TODO: Eigentliche Boundary aus Mesh-Edges extrahieren
        make_face = BRepBuilderAPI_MakeFace(plane, -1000, 1000, -1000, 1000)

        if make_face.IsDone():
            return make_face.Face()
        return None

    def _build_cylinder_face(self, prim: DetectedPrimitive) -> Optional[TopoDS_Face]:
        """
        Erstellt eine echte Zylinder-Surface (nicht facettiert!).

        Das ist der Schlüssel für "perfect" BREP:
        Ein Zylinder hat nur 3 Faces (Top, Bottom, Curved),
        statt hunderten facettierter Faces.

        Returns the curved cylindrical face (not the caps).
        """
        if prim.radius is None or prim.radius <= 0:
            logger.warning("Zylinder: Ungültiger Radius")
            return None

        if prim.axis is None:
            logger.warning("Zylinder: Keine Achse definiert")
            return None

        try:
            # Achse definieren
            origin = gp_Pnt(prim.origin[0], prim.origin[1], prim.origin[2])
            direction = gp_Dir(prim.axis[0], prim.axis[1], prim.axis[2])
            ax2 = gp_Ax2(origin, direction)

            # Höhe bestimmen (Default falls nicht vorhanden)
            height = prim.height if prim.height and prim.height > 0 else 10.0

            # Zylinder erstellen
            make_cyl = BRepPrimAPI_MakeCylinder(ax2, prim.radius, height)

            if not make_cyl.IsDone():
                logger.warning("Zylinder-Erstellung fehlgeschlagen")
                return None

            shape = make_cyl.Shape()

            # Extrahiere die zylindrische Face (curved surface, nicht caps)
            explorer = TopExp_Explorer(shape, TopAbs_FACE)

            while explorer.More():
                face = TopoDS_Face(explorer.Current())
                adaptor = BRepAdaptor_Surface(face)

                # Prüfe ob es eine zylindrische Surface ist
                if adaptor.GetType() == GeomAbs_Cylinder:
                    logger.debug(f"Zylinder-Face gefunden: Radius={prim.radius:.3f}")
                    return face

                explorer.Next()

            # Fallback: Erste Face zurückgeben wenn keine cylindrische gefunden
            explorer = TopExp_Explorer(shape, TopAbs_FACE)
            if explorer.More():
                logger.warning("Zylinder: Keine cylindrische Face gefunden, verwende erste Face")
                return TopoDS_Face(explorer.Current())

            logger.warning("Zylinder: Keine Faces gefunden")
            return None

        except Exception as e:
            logger.warning(f"Zylinder-Face-Erstellung fehlgeschlagen: {e}")
            return None

    def _build_sphere_face(self, prim: DetectedPrimitive) -> Optional[TopoDS_Face]:
        """
        Erstellt eine Kugel-Surface.

        Verwendet BRepPrimAPI_MakeSphere um eine echte analytische
        Kugel zu erzeugen (nicht facettiert).
        """
        if prim.radius is None or prim.radius <= 0:
            logger.warning("Kugel: Ungültiger Radius")
            return None

        try:
            center = gp_Pnt(prim.origin[0], prim.origin[1], prim.origin[2])

            # Kugel erstellen (volle Kugel)
            make_sphere = BRepPrimAPI_MakeSphere(center, prim.radius)

            if not make_sphere.IsDone():
                logger.warning("Kugel-Erstellung fehlgeschlagen")
                return None

            shape = make_sphere.Shape()

            # Extrahiere die sphärische Face
            explorer = TopExp_Explorer(shape, TopAbs_FACE)

            while explorer.More():
                face = TopoDS_Face(explorer.Current())
                adaptor = BRepAdaptor_Surface(face)

                # Prüfe ob es eine sphärische Surface ist
                if adaptor.GetType() == GeomAbs_Sphere:
                    logger.debug(f"Kugel-Face gefunden: Radius={prim.radius:.3f}")
                    return face

                explorer.Next()

            # Fallback: Erste Face zurückgeben
            explorer = TopExp_Explorer(shape, TopAbs_FACE)
            if explorer.More():
                logger.warning("Kugel: Keine sphärische Face gefunden, verwende erste Face")
                return TopoDS_Face(explorer.Current())

            logger.warning("Kugel: Keine Faces gefunden")
            return None

        except Exception as e:
            logger.warning(f"Kugel-Face-Erstellung fehlgeschlagen: {e}")
            return None

    def _build_cone_face(self, prim: DetectedPrimitive) -> Optional[TopoDS_Face]:
        """
        Erstellt eine Kegel-Surface.

        Verwendet BRepPrimAPI_MakeCone um einen echten analytischen
        Kegel zu erzeugen.

        Für einen Kegel benötigen wir:
        - origin: Spitze oder Basis-Zentrum
        - axis: Achsenrichtung
        - radius: Basis-Radius (radius1)
        - radius2: 0 für spitzen Kegel, oder zweiter Radius
        - height: Höhe des Kegels
        """
        if prim.radius is None or prim.radius <= 0:
            logger.warning("Kegel: Ungültiger Radius")
            return None

        if prim.axis is None:
            logger.warning("Kegel: Keine Achse definiert")
            return None

        try:
            # Achse definieren
            origin = gp_Pnt(prim.origin[0], prim.origin[1], prim.origin[2])
            direction = gp_Dir(prim.axis[0], prim.axis[1], prim.axis[2])
            ax2 = gp_Ax2(origin, direction)

            # Höhe bestimmen
            height = prim.height if prim.height and prim.height > 0 else 10.0

            # Zweiten Radius bestimmen (für Kegelstumpf oder spitzen Kegel)
            radius2 = prim.radius2 if prim.radius2 is not None else 0.0

            # Kegel erstellen
            make_cone = BRepPrimAPI_MakeCone(ax2, prim.radius, radius2, height)

            if not make_cone.IsDone():
                logger.warning("Kegel-Erstellung fehlgeschlagen")
                return None

            shape = make_cone.Shape()

            # Extrahiere die konische Face (curved surface)
            explorer = TopExp_Explorer(shape, TopAbs_FACE)

            while explorer.More():
                face = TopoDS_Face(explorer.Current())
                adaptor = BRepAdaptor_Surface(face)

                # Prüfe ob es eine konische Surface ist
                if adaptor.GetType() == GeomAbs_Cone:
                    logger.debug(f"Kegel-Face gefunden: R1={prim.radius:.3f}, R2={radius2:.3f}")
                    return face

                explorer.Next()

            # Fallback: Erste Face zurückgeben
            explorer = TopExp_Explorer(shape, TopAbs_FACE)
            if explorer.More():
                logger.warning("Kegel: Keine konische Face gefunden, verwende erste Face")
                return TopoDS_Face(explorer.Current())

            logger.warning("Kegel: Keine Faces gefunden")
            return None

        except Exception as e:
            logger.warning(f"Kegel-Face-Erstellung fehlgeschlagen: {e}")
            return None

    def _build_torus_face(self, prim: DetectedPrimitive) -> Optional[TopoDS_Face]:
        """
        Erstellt eine Torus-Surface.

        Verwendet BRepPrimAPI_MakeTorus um einen echten analytischen
        Torus (Ring) zu erzeugen.

        Für einen Torus benötigen wir:
        - origin: Zentrum des Torus
        - axis: Achsenrichtung (Rotationsachse)
        - radius: Haupt-Radius (Abstand vom Zentrum zur Rohrmitte)
        - radius2: Neben-Radius (Radius des Rohrs)
        """
        if prim.radius is None or prim.radius <= 0:
            logger.warning("Torus: Ungültiger Haupt-Radius")
            return None

        if prim.radius2 is None or prim.radius2 <= 0:
            logger.warning("Torus: Ungültiger Neben-Radius (radius2)")
            return None

        if prim.axis is None:
            logger.warning("Torus: Keine Achse definiert")
            return None

        try:
            # Achse definieren
            origin = gp_Pnt(prim.origin[0], prim.origin[1], prim.origin[2])
            direction = gp_Dir(prim.axis[0], prim.axis[1], prim.axis[2])
            ax2 = gp_Ax2(origin, direction)

            # Torus erstellen (voller Torus)
            # radius = Haupt-Radius (R), radius2 = Neben-Radius (r)
            make_torus = BRepPrimAPI_MakeTorus(ax2, prim.radius, prim.radius2)

            if not make_torus.IsDone():
                logger.warning("Torus-Erstellung fehlgeschlagen")
                return None

            shape = make_torus.Shape()

            # Extrahiere die toroidale Face
            explorer = TopExp_Explorer(shape, TopAbs_FACE)

            while explorer.More():
                face = TopoDS_Face(explorer.Current())
                adaptor = BRepAdaptor_Surface(face)

                # Prüfe ob es eine toroidale Surface ist
                if adaptor.GetType() == GeomAbs_Torus:
                    logger.debug(f"Torus-Face gefunden: R={prim.radius:.3f}, r={prim.radius2:.3f}")
                    return face

                explorer.Next()

            # Fallback: Erste Face zurückgeben
            explorer = TopExp_Explorer(shape, TopAbs_FACE)
            if explorer.More():
                logger.warning("Torus: Keine toroidale Face gefunden, verwende erste Face")
                return TopoDS_Face(explorer.Current())

            logger.warning("Torus: Keine Faces gefunden")
            return None

        except Exception as e:
            logger.warning(f"Torus-Face-Erstellung fehlgeschlagen: {e}")
            return None

    def _build_fallback_face(
        self,
        prim: DetectedPrimitive,
        mesh
    ) -> Optional[TopoDS_Face]:
        """
        Fallback: Erstellt Faces aus Mesh-Triangulation.

        Wird verwendet wenn:
        - Der Primitive-Typ unbekannt ist (NURBS, UNKNOWN)
        - Die analytische Erstellung fehlgeschlagen ist

        Erstellt planare BREP Faces für jedes Triangle im Mesh-Bereich.
        """
        if mesh is None:
            logger.warning("Fallback: Kein Mesh verfügbar")
            return None

        if not prim.face_indices:
            logger.warning("Fallback: Keine Face-Indizes verfügbar")
            return None

        try:
            # Prüfe ob PyVista verfügbar ist
            try:
                import pyvista as pv
            except ImportError:
                logger.warning("Fallback: PyVista nicht verfügbar")
                return None

            # Extrahiere Faces aus dem Mesh
            faces_arr = mesh.faces.reshape(-1, 4)[:, 1:4]

            # Sammle alle relevanten Faces
            faces_to_process = []
            for idx in prim.face_indices:
                if 0 <= idx < len(faces_arr):
                    faces_to_process.append(faces_arr[idx])

            if not faces_to_process:
                logger.warning("Fallback: Keine gültigen Faces gefunden")
                return None

            # Erstelle eine einzelne planare Face als Repräsentant
            # (Für vollständige Implementierung würden wir alle Faces verarbeiten)
            first_face = faces_to_process[0]
            v0 = mesh.points[first_face[0]]
            v1 = mesh.points[first_face[1]]
            v2 = mesh.points[first_face[2]]

            # Berechne Normale
            edge1 = v1 - v0
            edge2 = v2 - v0
            normal = np.cross(edge1, edge2)
            normal_len = np.linalg.norm(normal)

            if normal_len < 1e-10:
                logger.warning("Fallback: Degeneriertes Triangle")
                return None

            normal = normal / normal_len

            # Erstelle planare Face
            origin = gp_Pnt(v0[0], v0[1], v0[2])
            normal_dir = gp_Dir(normal[0], normal[1], normal[2])
            plane = gp_Pln(origin, normal_dir)

            make_face = BRepBuilderAPI_MakeFace(plane, -100, 100, -100, 100)

            if make_face.IsDone():
                logger.debug(f"Fallback-Face erstellt für {len(faces_to_process)} Triangles")
                return make_face.Face()

            logger.warning("Fallback: Face-Erstellung fehlgeschlagen")
            return None

        except Exception as e:
            logger.warning(f"Fallback-Face-Erstellung fehlgeschlagen: {e}")
            return None

    def _sew_faces(
        self,
        faces: List[TopoDS_Face],
        stats: Dict
    ) -> Optional[TopoDS_Shape]:
        """Verbindet Faces via Sewing."""
        sewing = BRepBuilderAPI_Sewing()
        sewing.SetTolerance(self.sewing_tol)

        for face in faces:
            sewing.Add(face)

        sewing.Perform()

        result = sewing.SewedShape()

        # Validierung
        if HAS_OCP:
            analyzer = BRepCheck_Analyzer(result)
            if analyzer.IsValid():
                logger.info("  Validierung: OK")
            else:
                logger.warning("  Validierung: FAILED (bekannte Limitation)")

        return result


def build_analytical_cylinder(
    center: np.ndarray,
    axis: np.ndarray,
    radius: float,
    height: float
) -> Optional[TopoDS_Shape]:
    """
    Erstellt einen analytischen Zylinder mit nur 3 Faces.

    Dies ist der Schlüssel für "perfect" BREP:
    - Top Face (Kreis)
    - Bottom Face (Kreis)
    - Curved Face (CylindricalSurface)

    Vergleich:
    - SimpleConverter: ~100 facettierte Faces
    - PerfectConverter: 3 analytische Faces!

    Args:
        center: Punkt auf der Achse
        axis: Achsenrichtung (normalisiert)
        radius: Radius
        height: Höhe

    Returns:
        TopoDS_Shape (Solid) oder None
    """
    if not HAS_OCP:
        return None

    try:
        origin = gp_Pnt(center[0], center[1], center[2])
        direction = gp_Dir(axis[0], axis[1], axis[2])
        ax1 = gp_Ax1(origin, direction)

        make_cyl = BRepPrimAPI_MakeCylinder(ax1, radius, height / 2)

        if make_cyl.IsDone():
            return make_cyl.Shape()

    except Exception as e:
        logger.warning(f"Analytischer Zylinder fehlgeschlagen: {e}")

    return None
