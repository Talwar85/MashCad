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
        BRepPrimAPI_MakeCone
    )
    from OCP.TopoDS import TopoDS_Face, TopoDS_Shape
    from OCP.ShapeFix import ShapeFix_Shape
    from OCP.BRepCheck import BRepCheck_Analyzer
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
                    PrimitiveType.CONE
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
        """
        if prim.radius is None or prim.radius <= 0:
            return None

        # Achse
        origin = gp_Pnt(prim.origin[0], prim.origin[1], prim.origin[2])
        direction = gp_Dir(prim.axis[0], prim.axis[1], prim.axis[2])
        axis = gp_Ax1(origin, direction)

        # Zylinder
        height = prim.height if prim.height else 10.0
        make_cyl = BRepPrimAPI_MakeCylinder(
            axis,
            prim.radius,
            height / 2  # Halbe Höhe nach oben und unten
        )

        if make_cyl.IsDone():
            shape = make_cyl.Shape()
            # Extrahiere Faces
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE
            explorer = TopExp_Explorer(shape, TopAbs_FACE)

            # Gib das erste Face zurück (der curved surface)
            # In einer vollständigen Implementierung würden wir hier
            # alle Faces verarbeiten
            return None  # TODO: Implementieren

        return None

    def _build_sphere_face(self, prim: DetectedPrimitive) -> Optional[TopoDS_Face]:
        """Erstellt eine Kugel-Surface."""
        if prim.radius is None or prim.radius <= 0:
            return None

        center = gp_Pnt(prim.origin[0], prim.origin[1], prim.origin[2])

        make_sphere = BRepPrimAPI_MakeSphere(center, prim.radius)

        if make_sphere.IsDone():
            # TODO: Faces extrahieren
            return None

        return None

    def _build_cone_face(self, prim: DetectedPrimitive) -> Optional[TopoDS_Face]:
        """Erstellt eine Kegel-Surface."""
        # TODO: Implementieren
        return None

    def _build_fallback_face(
        self,
        prim: DetectedPrimitive,
        mesh
    ) -> Optional[TopoDS_Face]:
        """Fallback: Triangulierte Faces aus Mesh."""
        # Extrahiere die Faces des Meshes für diese Primitive
        # und erstelle planare BREP Faces
        # TODO: Implementieren
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
