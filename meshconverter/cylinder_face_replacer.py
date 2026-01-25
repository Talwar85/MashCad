"""
Cylinder Face Replacer - Ersetzt triangulierte Zylinder-Faces durch analytische.

Strategie (KEIN Boolean!):
1. Mesh → BREP (trianguliert)
2. Erkenne Zylinder-Regionen auf Mesh
3. Finde die entsprechenden BREP-Faces
4. Entferne diese Faces aus der Shell
5. Erstelle analytische Zylinderfläche
6. Nähe alles zusammen

Warum das besser ist als Boolean:
- Kein Hinzufügen/Entfernen von Material
- Nur Oberflächenaustausch
- Erhält die Topologie
"""

import numpy as np
from typing import List, Tuple, Optional, Dict, Set
from dataclasses import dataclass
from loguru import logger

try:
    from OCP.TopoDS import (TopoDS, TopoDS_Shape, TopoDS_Solid, TopoDS_Shell,
                            TopoDS_Face, TopoDS_Edge, TopoDS_Wire, TopoDS_Compound)
    from OCP.TopExp import TopExp_Explorer, TopExp
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_WIRE, TopAbs_SHELL, TopAbs_FORWARD, TopAbs_REVERSED
    from OCP.TopTools import TopTools_IndexedMapOfShape, TopTools_IndexedDataMapOfShapeListOfShape
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax3, gp_Circ, gp_Vec
    from OCP.Geom import Geom_CylindricalSurface
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeEdge, BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Shell, ShapeFix_Solid
    from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    from OCP.GeomAbs import GeomAbs_C0
    HAS_OCP = True
except ImportError:
    HAS_OCP = False

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

from .mesh_primitive_detector import MeshPrimitiveDetector, CylinderFit
from .direct_mesh_converter import DirectMeshConverter
from .mesh_converter_v10 import ConversionResult, ConversionStatus

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from OCP.TopoDS import TopoDS_Shape as TopoDS_Shape_Type
else:
    TopoDS_Shape_Type = object


@dataclass
class FaceReplacementResult:
    """Ergebnis der Face-Ersetzung."""
    solid: Optional['TopoDS_Shape_Type']
    status: str
    stats: Dict
    cylinders_replaced: int = 0


class CylinderFaceReplacer:
    """
    Ersetzt triangulierte Zylinder-Faces durch analytische Zylinderoberflächen.

    Im Gegensatz zu Boolean-Ansätzen wird hier nur die Oberfläche ausgetauscht,
    nicht Material hinzugefügt oder entfernt.
    """

    def __init__(
        self,
        # Zylinder-Erkennung
        angle_threshold: float = 12.0,
        min_cylinder_faces: int = 20,
        cylinder_fit_tolerance: float = 0.3,
        min_inlier_ratio: float = 0.88,
        # Größen-Filter
        min_cylinder_radius: float = 1.0,
        max_cylinder_radius: float = 20.0,
        # Toleranzen
        sewing_tolerance: float = 0.1
    ):
        self.angle_thresh = angle_threshold
        self.min_cyl_faces = min_cylinder_faces
        self.cyl_fit_tol = cylinder_fit_tolerance
        self.min_inlier = min_inlier_ratio
        self.min_radius = min_cylinder_radius
        self.max_radius = max_cylinder_radius
        self.sewing_tol = sewing_tolerance

    def convert(self, mesh: 'pv.PolyData') -> FaceReplacementResult:
        """Konvertiert Mesh mit Face-Replacement für Zylinder."""
        if not HAS_OCP or not HAS_PYVISTA:
            return FaceReplacementResult(None, "FAILED", {"error": "Dependencies missing"})

        stats = {
            'mesh_faces': mesh.n_cells,
            'cylinders_detected': 0,
            'holes_detected': 0,
            'faces_replaced': 0,
            'brep_faces_final': 0
        }

        logger.info("=== Cylinder Face Replacer ===")
        logger.info(f"Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

        # 1. Erkenne Zylinder auf Mesh
        logger.info("Schritt 1: Erkenne Zylinder...")
        detector = MeshPrimitiveDetector(
            angle_threshold=self.angle_thresh,
            min_region_faces=self.min_cyl_faces,
            cylinder_tolerance=self.cyl_fit_tol,
            min_inlier_ratio=self.min_inlier
        )

        cylinders, _ = detector.detect_from_mesh(mesh)
        stats['cylinders_detected'] = len(cylinders)

        # Filtere nach Löchern
        faces = mesh.faces.reshape(-1, 4)[:, 1:4]
        points = mesh.points

        hole_cylinders = []
        for cyl in cylinders:
            if cyl.radius < self.min_radius or cyl.radius > self.max_radius:
                continue
            if self._is_hole(cyl, faces, points):
                hole_cylinders.append(cyl)
                logger.info(f"  Loch: R={cyl.radius:.2f}mm, H={cyl.height:.2f}mm, {len(cyl.face_indices)} Faces")

        stats['holes_detected'] = len(hole_cylinders)
        logger.info(f"  {len(hole_cylinders)} Zylinder-Löcher erkannt")

        # 2. Konvertiere Mesh zu BREP (trianguliert)
        logger.info("Schritt 2: Konvertiere Mesh zu BREP...")
        converter = DirectMeshConverter(
            sewing_tolerance=1e-6,
            unify_faces=False,  # WICHTIG: Nicht unifyen, wir brauchen 1:1 Mapping
            unify_linear_tolerance=0.1,
            unify_angular_tolerance=0.5
        )

        base_result = converter.convert(mesh)
        if base_result.status != ConversionStatus.SUCCESS or base_result.solid is None:
            return FaceReplacementResult(None, "BASE_FAILED", stats)

        # 3. Versuche Face-Replacement
        if hole_cylinders:
            logger.info("Schritt 3: Ersetze Zylinder-Faces...")

            result_shape, replaced = self._replace_cylinder_faces(
                base_result.solid, mesh, hole_cylinders
            )

            if result_shape is not None and replaced > 0:
                stats['faces_replaced'] = replaced
                stats['brep_faces_final'] = self._count_faces(result_shape)
                logger.success(f"Fertig: {replaced} Zylinder ersetzt, {stats['brep_faces_final']} Faces")
                return FaceReplacementResult(result_shape, "SUCCESS", stats, replaced)

        # Fallback: Basis-BREP ohne Replacement
        stats['brep_faces_final'] = self._count_faces(base_result.solid)
        logger.info(f"Kein Face-Replacement, verwende Basis: {stats['brep_faces_final']} Faces")
        return FaceReplacementResult(base_result.solid, "NO_REPLACEMENT", stats, 0)

    def _replace_cylinder_faces(
        self,
        solid,  # TopoDS_Shape
        mesh: 'pv.PolyData',
        hole_cylinders: List[CylinderFit]
    ) -> Tuple[Optional[object], int]:
        """
        Ersetzt triangulierte Zylinder-Faces durch analytische.

        Strategie:
        1. Finde BREP-Faces die zum Mesh-Zylinder gehören
        2. Sammle Boundary-Edges dieser Faces
        3. Erstelle analytische Zylinderfläche
        4. Baue Shell neu auf
        """

        # Sammle alle Faces
        all_faces = []
        face_exp = TopExp_Explorer(solid, TopAbs_FACE)
        while face_exp.More():
            all_faces.append(TopoDS.Face_s(face_exp.Current()))
            face_exp.Next()

        logger.info(f"  BREP hat {len(all_faces)} Faces")

        if len(all_faces) != mesh.n_cells:
            logger.warning(f"  Face-Count mismatch: BREP={len(all_faces)}, Mesh={mesh.n_cells}")
            logger.warning("  Face-Replacement nicht möglich ohne 1:1 Mapping")
            return None, 0

        replaced_count = 0
        faces_to_keep = set(range(len(all_faces)))
        new_cylinder_faces = []

        for cyl_idx, cyl in enumerate(hole_cylinders):
            logger.info(f"  Zylinder {cyl_idx+1}: R={cyl.radius:.2f}mm")

            # Die face_indices aus dem MeshPrimitiveDetector
            cyl_face_indices = set(cyl.face_indices)

            # Entferne diese aus faces_to_keep
            faces_to_keep -= cyl_face_indices

            # Sammle Boundary-Edges
            boundary_edges = self._find_boundary_edges(
                [all_faces[i] for i in cyl_face_indices],
                [all_faces[i] for i in faces_to_keep]
            )

            if not boundary_edges:
                logger.warning(f"    Keine Boundary-Edges gefunden")
                # Faces wieder hinzufügen
                faces_to_keep |= cyl_face_indices
                continue

            logger.info(f"    {len(boundary_edges)} Boundary-Edges gefunden")

            # Erstelle analytische Zylinderfläche
            cyl_face = self._create_cylinder_face(cyl, boundary_edges)

            if cyl_face is not None:
                new_cylinder_faces.append(cyl_face)
                replaced_count += 1
                logger.success(f"    Zylinder-Face erstellt")
            else:
                logger.warning(f"    Zylinder-Face Erstellung fehlgeschlagen")
                # Faces wieder hinzufügen
                faces_to_keep |= cyl_face_indices

        if replaced_count == 0:
            return None, 0

        # Baue Shell neu auf
        logger.info(f"  Baue Shell neu: {len(faces_to_keep)} originale + {len(new_cylinder_faces)} neue Faces")

        sewer = BRepBuilderAPI_Sewing(self.sewing_tol)

        # Originale Faces (ohne Zylinder)
        for idx in faces_to_keep:
            sewer.Add(all_faces[idx])

        # Neue Zylinder-Faces
        for cyl_face in new_cylinder_faces:
            sewer.Add(cyl_face)

        sewer.Perform()
        sewn = sewer.SewedShape()

        if sewn.IsNull():
            logger.warning("  Sewing fehlgeschlagen")
            return None, 0

        # Versuche Solid zu erstellen
        result = self._try_make_solid(sewn)

        return result, replaced_count

    def _find_boundary_edges(
        self,
        cylinder_faces,  # List[TopoDS_Face]
        other_faces  # List[TopoDS_Face]
    ) -> List:
        """
        Findet Edges die zwischen Zylinder-Faces und anderen Faces geteilt werden.
        """
        # Use hash() on the underlying shape pointer
        def edge_id(edge):
            return hash(edge.TShape())

        # Sammle alle Edges der Zylinder-Faces
        cyl_edges = set()
        edge_face_count = {}  # Edge ID -> Anzahl Zylinder-Faces die diese Edge haben
        edge_objects = {}  # Edge ID -> Edge object

        for face in cylinder_faces:
            edge_exp = TopExp_Explorer(face, TopAbs_EDGE)
            while edge_exp.More():
                edge = TopoDS.Edge_s(edge_exp.Current())
                eid = edge_id(edge)
                cyl_edges.add(eid)
                edge_face_count[eid] = edge_face_count.get(eid, 0) + 1
                edge_objects[eid] = edge
                edge_exp.Next()

        # Sammle Edges der anderen Faces
        other_edges = set()
        for face in other_faces:
            edge_exp = TopExp_Explorer(face, TopAbs_EDGE)
            while edge_exp.More():
                edge = TopoDS.Edge_s(edge_exp.Current())
                other_edges.add(edge_id(edge))
                edge_exp.Next()

        # Boundary = Edges die nur 1x in Zylinder vorkommen UND auch in anderen Faces
        boundary_edges = []

        for eid, count in edge_face_count.items():
            if count == 1:  # Edge nur von einer Zylinder-Face
                if eid in other_edges:  # Geteilt mit anderen Faces
                    boundary_edges.append(edge_objects[eid])

        return boundary_edges

    def _create_cylinder_face(
        self,
        cyl: CylinderFit,
        boundary_edges: List[TopoDS_Edge]
    ) -> Optional[TopoDS_Face]:
        """
        Erstellt analytische Zylinderfläche begrenzt durch die Boundary-Edges.
        """
        try:
            # Normalisiere Achse
            axis = np.array(cyl.axis, dtype=float)
            axis_len = np.linalg.norm(axis)
            if axis_len < 1e-10:
                return None
            axis = axis / axis_len

            center = np.array(cyl.center, dtype=float)

            # Koordinatensystem für Zylinder
            gp_origin = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))
            gp_dir = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))

            # Referenz-Richtung (senkrecht zur Achse)
            if abs(axis[2]) < 0.9:
                ref = np.cross(axis, [0, 0, 1])
            else:
                ref = np.cross(axis, [1, 0, 0])
            ref = ref / np.linalg.norm(ref)
            gp_ref = gp_Dir(float(ref[0]), float(ref[1]), float(ref[2]))

            ax3 = gp_Ax3(gp_origin, gp_dir, gp_ref)

            # Zylindrische Oberfläche
            cyl_surface = Geom_CylindricalSurface(ax3, float(cyl.radius))

            # Versuche Wire aus Boundary-Edges zu bauen
            # Wir brauchen typischerweise 2 geschlossene Wires (oben und unten)

            # Einfacher Ansatz: Bounded Face mit U/V Parametern
            # Berechne V-Bereich aus Boundary-Edge-Positionen
            v_min = float('inf')
            v_max = float('-inf')

            for edge in boundary_edges:
                # Hole Vertices der Edge
                v1 = BRep_Tool.Pnt_s(TopExp.FirstVertex_s(edge))
                v2 = BRep_Tool.Pnt_s(TopExp.LastVertex_s(edge))

                for v in [v1, v2]:
                    # Projiziere auf Achse
                    p = np.array([v.X(), v.Y(), v.Z()])
                    proj = np.dot(p - center, axis)
                    v_min = min(v_min, proj)
                    v_max = max(v_max, proj)

            if v_min >= v_max:
                logger.debug("    V-Bereich ungültig")
                return None

            # Erweitere leicht für Überlappung
            margin = 0.01
            v_min -= margin
            v_max += margin

            # U-Bereich = voller Kreis (für Loch)
            u_min = 0.0
            u_max = 2 * np.pi

            logger.debug(f"    U: {u_min:.2f} - {u_max:.2f}, V: {v_min:.2f} - {v_max:.2f}")

            # Erstelle Face
            face_maker = BRepBuilderAPI_MakeFace(cyl_surface, u_min, u_max, v_min, v_max, 1e-6)

            if face_maker.IsDone():
                face = face_maker.Face()
                # Orientierung: Loch = Normale nach innen
                face.Reverse()
                return face

            return None

        except Exception as e:
            logger.debug(f"    Exception: {e}")
            return None

    def _try_make_solid(self, shape: TopoDS_Shape) -> Optional[TopoDS_Shape]:
        """Versucht Shell zu Solid zu machen."""
        try:
            # Erst ShapeFix
            fixer = ShapeFix_Shape(shape)
            fixer.Perform()
            fixed = fixer.Shape()

            # Versuche Shell zu extrahieren
            shell_exp = TopExp_Explorer(fixed, TopAbs_SHELL)
            if shell_exp.More():
                shell = TopoDS.Shell_s(shell_exp.Current())

                # Shell fixen
                shell_fixer = ShapeFix_Shell(shell)
                shell_fixer.Perform()
                shell = shell_fixer.Shell()

                # Solid erstellen
                solid_maker = BRepBuilderAPI_MakeSolid(shell)
                if solid_maker.IsDone():
                    solid = solid_maker.Solid()

                    # Solid fixen
                    solid_fixer = ShapeFix_Solid(solid)
                    solid_fixer.Perform()
                    return solid_fixer.Solid()

            return fixed

        except Exception as e:
            logger.debug(f"    MakeSolid Exception: {e}")
            return shape

    def _is_hole(self, cyl: CylinderFit, faces: np.ndarray, points: np.ndarray) -> bool:
        """Bestimmt ob Zylinder ein Loch ist (Normalen nach innen)."""
        inward = 0
        outward = 0

        for f_idx in cyl.face_indices:
            v0, v1, v2 = faces[f_idx]
            p0, p1, p2 = points[v0], points[v1], points[v2]

            # Normal
            e1 = p1 - p0
            e2 = p2 - p0
            normal = np.cross(e1, e2)
            n_len = np.linalg.norm(normal)
            if n_len < 1e-10:
                continue
            normal /= n_len

            # Radiale Richtung
            centroid = (p0 + p1 + p2) / 3
            to_center = centroid - cyl.center
            proj = np.dot(to_center, cyl.axis) * cyl.axis
            radial = to_center - proj
            r_len = np.linalg.norm(radial)
            if r_len < 1e-10:
                continue
            radial /= r_len

            dot = np.dot(normal, radial)
            if dot > 0.1:
                outward += 1
            elif dot < -0.1:
                inward += 1

        return inward > outward

    def _count_faces(self, shape: TopoDS_Shape) -> int:
        """Zählt Faces."""
        count = 0
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            count += 1
            exp.Next()
        return count
