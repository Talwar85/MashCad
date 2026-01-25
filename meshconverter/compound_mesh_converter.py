"""
Compound Mesh Converter - Erstellt Compound aus Faces OHNE Sewing.

Das Problem: Sewing zerstört die CYLINDRICAL_SURFACE Entities.
Lösung: Faces als Compound zusammenfassen, kein Sewing.

Das Ergebnis ist kein wasserdichtes Solid, aber enthält echte
CYLINDRICAL_SURFACE Entities im STEP Export.
"""

import numpy as np
from typing import List, Tuple, Optional, Dict, Set
from dataclasses import dataclass
from loguru import logger
from collections import defaultdict

try:
    from OCP.TopoDS import TopoDS, TopoDS_Shape, TopoDS_Solid, TopoDS_Shell, TopoDS_Face, TopoDS_Edge, TopoDS_Wire, TopoDS_Compound
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_SHELL
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax3, gp_Circ, gp_Vec, gp_Ax2
    from OCP.Geom import Geom_CylindricalSurface
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire,
                                    BRepBuilderAPI_MakeEdge, BRepBuilderAPI_Sewing,
                                    BRepBuilderAPI_MakeSolid)
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Shell, ShapeFix_Solid
    HAS_OCP = True
except ImportError:
    HAS_OCP = False

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

from .mesh_primitive_detector import MeshPrimitiveDetector, CylinderFit
from .mesh_converter_v10 import ConversionResult, ConversionStatus


@dataclass
class CompoundResult:
    """Ergebnis der Compound-Konvertierung."""
    shape: Optional[object]  # TopoDS_Compound oder TopoDS_Solid
    status: str
    stats: Dict
    analytical_cylinders: int = 0
    is_solid: bool = False


class CompoundMeshConverter:
    """
    Konvertiert Mesh zu BREP Compound mit analytischen Zylinderflächen.

    Im Gegensatz zum Selective Converter wird hier KEIN Sewing gemacht,
    um die CYLINDRICAL_SURFACE Entities zu erhalten.

    Das Ergebnis kann ein:
    - Compound (alle Faces lose)
    - Shell (wenn Faces zusammenhängen)
    - Solid (wenn wasserdicht)
    sein.
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
        # Sewing (optional, mit kleiner Toleranz)
        sewing_tolerance: float = 0.001,  # Sehr klein!
        try_sewing: bool = True
    ):
        self.angle_thresh = angle_threshold
        self.min_cyl_faces = min_cylinder_faces
        self.cyl_fit_tol = cylinder_fit_tolerance
        self.min_inlier = min_inlier_ratio
        self.min_radius = min_cylinder_radius
        self.max_radius = max_cylinder_radius
        self.sewing_tol = sewing_tolerance
        self.try_sewing = try_sewing

    def convert(self, mesh: 'pv.PolyData') -> CompoundResult:
        """Konvertiert Mesh zu Compound mit analytischen Flächen."""
        if not HAS_OCP or not HAS_PYVISTA:
            return CompoundResult(None, "FAILED", {"error": "Dependencies missing"})

        stats = {
            'mesh_faces': mesh.n_cells,
            'cylinders_detected': 0,
            'holes_detected': 0,
            'analytical_cylinders': 0,
            'triangulated_faces': 0,
            'total_faces': 0
        }

        logger.info("=== Compound Mesh Converter ===")
        logger.info(f"Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

        faces_arr = mesh.faces.reshape(-1, 4)[:, 1:4]
        points = mesh.points

        # 1. Erkenne Zylinder
        logger.info("Schritt 1: Erkenne Zylinder-Löcher...")
        detector = MeshPrimitiveDetector(
            angle_threshold=self.angle_thresh,
            min_region_faces=self.min_cyl_faces,
            cylinder_tolerance=self.cyl_fit_tol,
            min_inlier_ratio=self.min_inlier
        )

        cylinders, _ = detector.detect_from_mesh(mesh)
        stats['cylinders_detected'] = len(cylinders)

        # Filtere nach Löchern
        hole_cylinders = []
        cylinder_face_indices = set()

        for cyl in cylinders:
            if cyl.radius < self.min_radius or cyl.radius > self.max_radius:
                continue
            if self._is_hole(cyl, faces_arr, points):
                hole_cylinders.append(cyl)
                cylinder_face_indices.update(cyl.face_indices)
                logger.info(f"  Loch: R={cyl.radius:.2f}mm, H={cyl.height:.2f}mm")

        stats['holes_detected'] = len(hole_cylinders)

        # 2. Erstelle Vertex-Pool und Edge-Map
        logger.info("Schritt 2: Erstelle Vertex/Edge-Pool...")
        vertex_pool = {}
        edge_map = {}
        precision = 4

        def get_vertex(p):
            key = (round(p[0], precision), round(p[1], precision), round(p[2], precision))
            if key not in vertex_pool:
                vertex_pool[key] = gp_Pnt(float(p[0]), float(p[1]), float(p[2]))
            return vertex_pool[key], key

        def get_edge(p1_key, p2_key, p1, p2):
            key = (min(p1_key, p2_key), max(p1_key, p2_key))
            if key not in edge_map:
                edge_builder = BRepBuilderAPI_MakeEdge(p1, p2)
                if edge_builder.IsDone():
                    edge_map[key] = edge_builder.Edge()
            return edge_map.get(key)

        # 3. Erstelle triangulierte Faces und sammle Boundary-Info
        logger.info("Schritt 3: Erstelle Faces...")
        all_faces = []
        cylinder_boundaries = defaultdict(lambda: {'edges': [], 'points_bottom': [], 'points_top': []})

        for face_idx in range(len(faces_arr)):
            v0, v1, v2 = faces_arr[face_idx]
            p0, p1, p2 = points[v0], points[v1], points[v2]

            gp_p0, key0 = get_vertex(p0)
            gp_p1, key1 = get_vertex(p1)
            gp_p2, key2 = get_vertex(p2)

            if face_idx in cylinder_face_indices:
                # Sammle für später, aber erstelle keine Face
                for cyl_idx, cyl in enumerate(hole_cylinders):
                    if face_idx in cyl.face_indices:
                        # Speichere Punkte für Boundary-Detection
                        cylinder_boundaries[cyl_idx]['edges'].append((key0, key1))
                        cylinder_boundaries[cyl_idx]['edges'].append((key1, key2))
                        cylinder_boundaries[cyl_idx]['edges'].append((key2, key0))
                        break
                continue

            # Normale Face
            e0 = get_edge(key0, key1, gp_p0, gp_p1)
            e1 = get_edge(key1, key2, gp_p1, gp_p2)
            e2 = get_edge(key2, key0, gp_p2, gp_p0)

            if e0 is None or e1 is None or e2 is None:
                continue

            try:
                wire_builder = BRepBuilderAPI_MakeWire()
                wire_builder.Add(e0)
                wire_builder.Add(e1)
                wire_builder.Add(e2)

                if wire_builder.IsDone():
                    face_builder = BRepBuilderAPI_MakeFace(wire_builder.Wire())
                    if face_builder.IsDone():
                        all_faces.append(face_builder.Face())
            except:
                continue

        stats['triangulated_faces'] = len(all_faces)
        logger.info(f"  {len(all_faces)} triangulierte Faces")

        # 4. Erstelle analytische Zylinder-Faces
        logger.info("Schritt 4: Erstelle analytische Zylinder...")

        for cyl_idx, cyl in enumerate(hole_cylinders):
            # Finde Boundary-Punkte
            edge_count = defaultdict(int)
            for e in cylinder_boundaries[cyl_idx]['edges']:
                key = (min(e[0], e[1]), max(e[0], e[1]))
                edge_count[key] += 1

            boundary_edges = [k for k, v in edge_count.items() if v == 1]

            if len(boundary_edges) < 6:
                logger.warning(f"  Zylinder {cyl_idx+1}: Zu wenige Boundary-Edges")
                continue

            # Sammle Boundary-Punkte
            boundary_points = set()
            for e in boundary_edges:
                boundary_points.add(e[0])
                boundary_points.add(e[1])

            boundary_coords = np.array([list(p) for p in boundary_points])

            # Separiere oben/unten
            axis = np.array(cyl.axis)
            axis = axis / np.linalg.norm(axis)
            center = np.array(cyl.center)

            projections = np.dot(boundary_coords - center, axis)
            proj_mid = (projections.min() + projections.max()) / 2

            bottom_mask = projections < proj_mid
            bottom_points = boundary_coords[bottom_mask]
            top_points = boundary_coords[~bottom_mask]

            if len(bottom_points) < 3 or len(top_points) < 3:
                logger.warning(f"  Zylinder {cyl_idx+1}: Nicht genug Boundary-Punkte")
                continue

            # Erstelle Zylinder-Face
            cyl_face = self._create_cylinder_face(cyl, bottom_points, top_points)

            if cyl_face is not None:
                all_faces.append(cyl_face)
                stats['analytical_cylinders'] += 1
                logger.success(f"  Zylinder {cyl_idx+1}: Analytische Face erstellt")
            else:
                logger.warning(f"  Zylinder {cyl_idx+1}: Face-Erstellung fehlgeschlagen")

        stats['total_faces'] = len(all_faces)
        logger.info(f"  Total: {len(all_faces)} Faces")

        # 5. Erstelle Compound
        logger.info("Schritt 5: Erstelle Compound...")
        builder = BRep_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)

        for face in all_faces:
            builder.Add(compound, face)

        # 6. Optionales Sewing
        if self.try_sewing and len(all_faces) > 0:
            logger.info("Schritt 6: Versuche Sewing...")

            sewer = BRepBuilderAPI_Sewing(self.sewing_tol)
            for face in all_faces:
                sewer.Add(face)

            sewer.Perform()
            sewn = sewer.SewedShape()

            if not sewn.IsNull():
                # Prüfe ob Solid möglich
                result = self._try_make_solid(sewn)
                if result is not None:
                    final_faces = self._count_faces(result)
                    logger.success(f"  Sewing erfolgreich: {final_faces} Faces")

                    # Prüfe ob CYLINDRICAL_SURFACE erhalten
                    cyl_count = self._count_cylindrical_faces(result)
                    logger.info(f"  Zylindrische Faces nach Sewing: {cyl_count}")

                    if cyl_count > 0:
                        return CompoundResult(result, "SUCCESS", stats, stats['analytical_cylinders'], True)
                    else:
                        logger.warning("  CYLINDRICAL_SURFACE verloren durch Sewing!")

        # Fallback: Compound ohne Sewing
        logger.info("Verwende Compound ohne Sewing")
        return CompoundResult(compound, "COMPOUND", stats, stats['analytical_cylinders'], False)

    def _create_cylinder_face(
        self,
        cyl: CylinderFit,
        bottom_points: np.ndarray,
        top_points: np.ndarray
    ) -> Optional[TopoDS_Face]:
        """Erstellt analytische Zylinderfläche."""
        try:
            axis = np.array(cyl.axis)
            axis = axis / np.linalg.norm(axis)
            center = np.array(cyl.center)

            # Referenz-Richtung
            if abs(axis[2]) < 0.9:
                x_axis = np.cross(axis, [0, 0, 1])
            else:
                x_axis = np.cross(axis, [1, 0, 0])
            x_axis = x_axis / np.linalg.norm(x_axis)

            # Koordinatensystem
            gp_center = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))
            gp_axis = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))
            gp_x = gp_Dir(float(x_axis[0]), float(x_axis[1]), float(x_axis[2]))

            ax3 = gp_Ax3(gp_center, gp_axis, gp_x)

            # Radius
            radius = float(cyl.radius)

            # Zylindrische Oberfläche
            cyl_surface = Geom_CylindricalSurface(ax3, radius)

            # V-Bereich aus Boundary-Punkten
            v_bottom = np.dot(bottom_points.mean(axis=0) - center, axis)
            v_top = np.dot(top_points.mean(axis=0) - center, axis)

            if v_bottom > v_top:
                v_bottom, v_top = v_top, v_bottom

            # Kleine Erweiterung
            margin = 0.02
            v_min = v_bottom - margin
            v_max = v_top + margin

            # U = voller Kreis
            u_min, u_max = 0.0, 2 * np.pi

            # Face erstellen
            face_maker = BRepBuilderAPI_MakeFace(cyl_surface, u_min, u_max, v_min, v_max, 1e-6)

            if face_maker.IsDone():
                face = face_maker.Face()
                face.Reverse()  # Loch = nach innen
                return face

            return None

        except Exception as e:
            logger.debug(f"    Exception: {e}")
            return None

    def _try_make_solid(self, shape: TopoDS_Shape) -> Optional[TopoDS_Shape]:
        """Versucht Shell zu Solid zu machen."""
        try:
            fixer = ShapeFix_Shape(shape)
            fixer.Perform()
            fixed = fixer.Shape()

            shell_exp = TopExp_Explorer(fixed, TopAbs_SHELL)
            if shell_exp.More():
                shell = TopoDS.Shell_s(shell_exp.Current())

                shell_fixer = ShapeFix_Shell(shell)
                shell_fixer.Perform()
                shell = shell_fixer.Shell()

                solid_maker = BRepBuilderAPI_MakeSolid(shell)
                if solid_maker.IsDone():
                    solid = solid_maker.Solid()
                    solid_fixer = ShapeFix_Solid(solid)
                    solid_fixer.Perform()
                    return solid_fixer.Solid()

            return fixed

        except Exception:
            return shape

    def _is_hole(self, cyl: CylinderFit, faces: np.ndarray, points: np.ndarray) -> bool:
        """Bestimmt ob Zylinder ein Loch ist."""
        inward = 0
        outward = 0

        for f_idx in cyl.face_indices:
            v0, v1, v2 = faces[f_idx]
            p0, p1, p2 = points[v0], points[v1], points[v2]

            e1 = p1 - p0
            e2 = p2 - p0
            normal = np.cross(e1, e2)
            n_len = np.linalg.norm(normal)
            if n_len < 1e-10:
                continue
            normal /= n_len

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

    def _count_cylindrical_faces(self, shape: TopoDS_Shape) -> int:
        """Zählt zylindrische Faces."""
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cylinder

        count = 0
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            face = TopoDS.Face_s(exp.Current())
            try:
                adaptor = BRepAdaptor_Surface(face)
                if adaptor.GetType() == GeomAbs_Cylinder:
                    count += 1
            except:
                pass
            exp.Next()
        return count
