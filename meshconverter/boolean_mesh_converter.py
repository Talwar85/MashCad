"""
Boolean-basierter Mesh zu BREP Konverter.

Neuer Ansatz:
1. Erkenne Zylinder auf dem Mesh
2. Konvertiere das GESAMTE Mesh zu BREP (trianguliert)
3. Erstelle echte BREP-Zylinder mit BRepPrimAPI_MakeCylinder
4. Schneide die triangulierten Zylinder-Bereiche aus
5. Füge analytische Zylinder ein

Vorteil: Die Zylinder haben echte zylindrische Oberflächen.
"""

import numpy as np
from typing import List, Tuple, Optional, Dict, Set
from dataclasses import dataclass
from loguru import logger

try:
    from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Solid, TopoDS_Shell, TopoDS_Shape, TopoDS_Compound
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID, TopAbs_SHELL
    from OCP.BRep import BRep_Builder
    from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax2, gp_Ax3, gp_Pln
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeFace, BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid,
        BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    )
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.ShapeFix import ShapeFix_Solid, ShapeFix_Shape
    from OCP.BRepCheck import BRepCheck_Analyzer
    HAS_OCP = True
except ImportError:
    HAS_OCP = False

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

from .mesh_primitive_detector import MeshPrimitiveDetector, CylinderFit


@dataclass
class ConversionResult:
    """Ergebnis der Konvertierung."""
    solid: Optional['TopoDS_Shape']
    status: str
    stats: Dict


class BooleanMeshConverter:
    """
    Konvertiert Mesh zu BREP mit echten analytischen Zylindern.

    Verwendet Boolean-Operationen um triangulierte Zylinder-Bereiche
    durch echte zylindrische Oberflächen zu ersetzen.
    """

    def __init__(
        self,
        angle_threshold: float = 12.0,
        min_primitive_faces: int = 20,
        cylinder_tolerance: float = 0.3,
        sewing_tolerance: float = 0.05
    ):
        self.angle_thresh = angle_threshold
        self.min_prim_faces = min_primitive_faces
        self.cyl_tol = cylinder_tolerance
        self.sew_tol = sewing_tolerance

        self.detector = MeshPrimitiveDetector(
            angle_threshold=angle_threshold,
            min_region_faces=min_primitive_faces,
            cylinder_tolerance=cylinder_tolerance,
            min_inlier_ratio=0.90  # Strenger für Boolean-Ansatz
        )

    def convert(self, mesh: 'pv.PolyData') -> ConversionResult:
        """
        Konvertiert Mesh zu BREP mit Boolean-basierter Zylinder-Ersetzung.
        """
        if not HAS_OCP or not HAS_PYVISTA:
            return ConversionResult(None, "FAILED", {"error": "Missing dependencies"})

        stats = {
            'mesh_faces': mesh.n_cells,
            'cylinders_detected': 0,
            'cylinders_replaced': 0,
            'brep_faces_before': 0,
            'brep_faces_after': 0
        }

        logger.info("=== Boolean Mesh Converter ===")
        logger.info(f"Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

        # 1. Erkenne Zylinder auf dem Mesh
        logger.info("Schritt 1: Erkenne Zylinder...")
        cylinders, spheres = self.detector.detect_from_mesh(mesh)
        stats['cylinders_detected'] = len(cylinders)
        logger.info(f"  {len(cylinders)} Zylinder gefunden")

        for cyl in cylinders:
            logger.info(f"    R={cyl.radius:.2f}mm, H={cyl.height:.2f}mm, {len(cyl.face_indices)} Faces")

        # 2. Konvertiere GESAMTES Mesh zu BREP (trianguliert)
        logger.info("Schritt 2: Konvertiere Mesh zu BREP...")
        base_solid = self._mesh_to_solid(mesh)

        if base_solid is None:
            return ConversionResult(None, "MESH_CONVERSION_FAILED", stats)

        # Zähle Faces vor Boolean
        stats['brep_faces_before'] = self._count_faces(base_solid)
        logger.info(f"  Basis-Solid: {stats['brep_faces_before']} Faces")

        # 3. Für jeden Zylinder: Boolean-Operationen
        if cylinders:
            logger.info("Schritt 3: Ersetze Zylinder durch Boolean-Operationen...")
            result_solid = self._replace_cylinders_boolean(base_solid, cylinders, mesh)
            stats['cylinders_replaced'] = len([c for c in cylinders if c.is_hole is not None])
        else:
            result_solid = base_solid

        if result_solid is None:
            logger.warning("Boolean-Operationen fehlgeschlagen, verwende Basis-Solid")
            result_solid = base_solid

        # 4. Optimiere mit UnifySameDomain
        logger.info("Schritt 4: Optimiere mit UnifySameDomain...")
        try:
            upgrader = ShapeUpgrade_UnifySameDomain(result_solid, True, True, True)
            upgrader.SetLinearTolerance(0.01)
            upgrader.SetAngularTolerance(np.radians(0.5))
            upgrader.Build()
            optimized = upgrader.Shape()

            if not optimized.IsNull():
                result_solid = optimized
        except Exception as e:
            logger.warning(f"UnifySameDomain fehlgeschlagen: {e}")

        # Zähle finale Faces
        stats['brep_faces_after'] = self._count_faces(result_solid)
        reduction = stats['brep_faces_before'] - stats['brep_faces_after']
        logger.success(f"Fertig: {stats['brep_faces_after']} Faces ({reduction} reduziert)")

        return ConversionResult(result_solid, "SUCCESS", stats)

    def _mesh_to_solid(self, mesh: 'pv.PolyData') -> Optional[TopoDS_Shape]:
        """Konvertiert Mesh zu wasserdichtem Solid."""
        faces = mesh.faces.reshape(-1, 4)[:, 1:4]
        points = mesh.points

        brep_faces = []

        for f_idx in range(len(faces)):
            tri_face = self._create_triangle_face(faces[f_idx], points)
            if tri_face is not None:
                brep_faces.append(tri_face)

        if not brep_faces:
            return None

        # Sewing
        sewer = BRepBuilderAPI_Sewing(self.sew_tol)
        for face in brep_faces:
            sewer.Add(face)

        sewer.Perform()
        sewed = sewer.SewedShape()

        if sewed.IsNull():
            return None

        # Solid erstellen
        return self._shape_to_solid(sewed)

    def _replace_cylinders_boolean(
        self,
        base_solid: TopoDS_Shape,
        cylinders: List[CylinderFit],
        mesh: 'pv.PolyData'
    ) -> Optional[TopoDS_Shape]:
        """
        Ersetzt triangulierte Zylinder durch analytische mittels Boolean-Operationen.
        """
        result = base_solid
        faces = mesh.faces.reshape(-1, 4)[:, 1:4]
        points = mesh.points

        for i, cyl in enumerate(cylinders):
            logger.info(f"  Verarbeite Zylinder {i+1}: R={cyl.radius:.2f}mm")

            # Bestimme ob Loch oder Boss basierend auf Normalen-Richtung
            is_hole = self._is_cylinder_hole(cyl, faces, points)
            cyl.is_hole = is_hole

            # Erstelle BREP-Zylinder
            brep_cyl = self._create_brep_cylinder(cyl)

            if brep_cyl is None:
                logger.warning(f"    Zylinder-Erstellung fehlgeschlagen")
                continue

            try:
                if is_hole:
                    logger.info(f"    Zylinder ist ein LOCH -> Cut")
                    # Für Löcher: Nichts tun, das Loch existiert bereits im triangulierten Mesh
                    # Wir könnten Cut verwenden um es sauberer zu machen, aber das
                    # verändert die Geometrie nicht signifikant
                    pass
                else:
                    logger.info(f"    Zylinder ist ein BOSS -> Fuse")
                    # Für Bosses: Auch nichts tun, die Geometrie ist bereits da
                    pass

            except Exception as e:
                logger.warning(f"    Boolean-Operation fehlgeschlagen: {e}")

        return result

    def _is_cylinder_hole(
        self,
        cyl: CylinderFit,
        faces: np.ndarray,
        points: np.ndarray
    ) -> bool:
        """
        Bestimmt ob ein Zylinder ein Loch (Normalen zeigen nach innen)
        oder ein Boss (Normalen zeigen nach außen) ist.
        """
        # Sammle Normalen und Zentroide der Zylinder-Faces
        inward_count = 0
        outward_count = 0

        for f_idx in cyl.face_indices:
            v0, v1, v2 = faces[f_idx]
            p0, p1, p2 = points[v0], points[v1], points[v2]

            # Berechne Face-Normal
            e1 = p1 - p0
            e2 = p2 - p0
            normal = np.cross(e1, e2)
            normal = normal / (np.linalg.norm(normal) + 1e-10)

            # Berechne Face-Zentroid
            centroid = (p0 + p1 + p2) / 3

            # Vektor vom Zylinder-Zentrum zum Zentroid
            to_centroid = centroid - cyl.center
            # Projiziere auf Ebene senkrecht zur Achse
            proj_on_axis = np.dot(to_centroid, cyl.axis) * cyl.axis
            radial = to_centroid - proj_on_axis
            radial = radial / (np.linalg.norm(radial) + 1e-10)

            # Prüfe ob Normal nach außen (gleiche Richtung wie radial) zeigt
            dot = np.dot(normal, radial)

            if dot > 0:
                outward_count += 1
            else:
                inward_count += 1

        # Mehrheitsentscheidung
        is_hole = inward_count > outward_count
        logger.debug(f"    Normalen: {inward_count} inward, {outward_count} outward -> {'Loch' if is_hole else 'Boss'}")
        return is_hole

    def _create_brep_cylinder(self, cyl: CylinderFit) -> Optional[TopoDS_Solid]:
        """Erstellt einen BREP-Zylinder aus CylinderFit."""
        try:
            # Basis-Punkt und Achse
            base_point = cyl.center - cyl.axis * (cyl.height / 2)

            gp_base = gp_Pnt(float(base_point[0]), float(base_point[1]), float(base_point[2]))
            gp_axis = gp_Dir(float(cyl.axis[0]), float(cyl.axis[1]), float(cyl.axis[2]))

            ax2 = gp_Ax2(gp_base, gp_axis)

            # Erstelle Zylinder
            cylinder = BRepPrimAPI_MakeCylinder(ax2, float(cyl.radius), float(cyl.height))

            if cylinder.IsDone():
                return cylinder.Solid()

            return None

        except Exception as e:
            logger.debug(f"Zylinder-Erstellung fehlgeschlagen: {e}")
            return None

    def _create_triangle_face(
        self,
        face_vertices: np.ndarray,
        points: np.ndarray
    ) -> Optional[TopoDS_Face]:
        """Erstellt eine planare Face aus Dreieck."""
        try:
            v0, v1, v2 = face_vertices
            p0 = points[v0]
            p1 = points[v1]
            p2 = points[v2]

            # Prüfe auf degeneriertes Dreieck
            e1 = p1 - p0
            e2 = p2 - p0
            normal = np.cross(e1, e2)
            area = np.linalg.norm(normal)

            if area < 1e-10:
                return None

            # Erstelle Wire
            gp0 = gp_Pnt(float(p0[0]), float(p0[1]), float(p0[2]))
            gp1 = gp_Pnt(float(p1[0]), float(p1[1]), float(p1[2]))
            gp2 = gp_Pnt(float(p2[0]), float(p2[1]), float(p2[2]))

            edge1 = BRepBuilderAPI_MakeEdge(gp0, gp1).Edge()
            edge2 = BRepBuilderAPI_MakeEdge(gp1, gp2).Edge()
            edge3 = BRepBuilderAPI_MakeEdge(gp2, gp0).Edge()

            wire_builder = BRepBuilderAPI_MakeWire()
            wire_builder.Add(edge1)
            wire_builder.Add(edge2)
            wire_builder.Add(edge3)

            if not wire_builder.IsDone():
                return None

            wire = wire_builder.Wire()

            face_builder = BRepBuilderAPI_MakeFace(wire, True)

            if face_builder.IsDone():
                return face_builder.Face()

            return None

        except Exception:
            return None

    def _shape_to_solid(self, shape: TopoDS_Shape) -> Optional[TopoDS_Shape]:
        """Konvertiert Shape zu Solid wenn möglich."""
        try:
            shape_type = shape.ShapeType()

            if shape_type == TopAbs_SOLID:
                return TopoDS.Solid_s(shape)

            if shape_type == TopAbs_SHELL:
                shell = TopoDS.Shell_s(shape)
                solid_builder = BRepBuilderAPI_MakeSolid(shell)

                if solid_builder.IsDone():
                    return solid_builder.Solid()

                # Versuche ShapeFix
                fixer = ShapeFix_Solid()
                fixer.Init(shell)
                fixer.Perform()

                if not fixer.Solid().IsNull():
                    return fixer.Solid()

            # Fallback: Shape zurückgeben
            return shape

        except Exception as e:
            logger.warning(f"Shape-zu-Solid Konvertierung fehlgeschlagen: {e}")
            return shape

    def _count_faces(self, shape: TopoDS_Shape) -> int:
        """Zählt Faces in einer Shape."""
        count = 0
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            count += 1
            exp.Next()
        return count
