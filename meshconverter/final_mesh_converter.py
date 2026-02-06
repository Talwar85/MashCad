"""
Final Mesh Converter - Beste verfügbare Lösung für STL zu STEP mit Zylindern.

ERKENNTNIS: Sewing zerstört CYLINDRICAL_SURFACE Entities IMMER,
weil die Kanten nicht matchen (kreisförmig vs polygonal).

LÖSUNG:
- Compound-Mode: CYLINDRICAL_SURFACE erhalten, kein Solid
- Solid-Mode: Wasserdichtes Solid, aber triangulierte Zylinder

Für STEP Export mit analytischen Zylindern: Compound-Mode verwenden.
"""

import numpy as np
from typing import List, Tuple, Optional, Dict, Set
from dataclasses import dataclass
from loguru import logger
from collections import defaultdict

try:
    from OCP.TopoDS import (TopoDS, TopoDS_Shape, TopoDS_Solid, TopoDS_Shell,
                            TopoDS_Face, TopoDS_Edge, TopoDS_Wire, TopoDS_Compound)
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_SHELL
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax3
    from OCP.Geom import Geom_CylindricalSurface
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire,
                                    BRepBuilderAPI_MakeEdge, BRepBuilderAPI_Sewing,
                                    BRepBuilderAPI_MakeSolid)
    from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Shell, ShapeFix_Solid
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
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
class FinalResult:
    """Ergebnis der finalen Konvertierung."""
    shape: Optional[object]           # TopoDS_Shape (Compound oder Solid)
    status: str
    stats: Dict
    is_solid: bool = False            # True wenn wasserdichtes Solid
    cylindrical_surfaces: int = 0     # Anzahl CYLINDRICAL_SURFACE


class FinalMeshConverter:
    """
    Finaler Mesh-zu-BREP Konverter.

    Modi:
    - preserve_cylinders=True: Compound mit CYLINDRICAL_SURFACE (für STEP)
    - preserve_cylinders=False: Wasserdichtes Solid (trianguliert)
    """

    def __init__(
        self,
        # Modus
        preserve_cylinders: bool = True,
        # Zylinder-Erkennung
        angle_threshold: float = 12.0,
        min_cylinder_faces: int = 20,
        cylinder_fit_tolerance: float = 0.3,
        min_inlier_ratio: float = 0.88,
        min_cylinder_radius: float = 1.0,
        max_cylinder_radius: float = 20.0,
        # Sewing
        sewing_tolerance: float = 0.01
    ):
        self.preserve_cylinders = preserve_cylinders
        self.angle_thresh = angle_threshold
        self.min_cyl_faces = min_cylinder_faces
        self.cyl_fit_tol = cylinder_fit_tolerance
        self.min_inlier = min_inlier_ratio
        self.min_radius = min_cylinder_radius
        self.max_radius = max_cylinder_radius
        self.sewing_tol = sewing_tolerance

    def convert(self, mesh: 'pv.PolyData') -> FinalResult:
        """Konvertiert Mesh zu BREP."""
        if not HAS_OCP or not HAS_PYVISTA:
            return FinalResult(None, "FAILED", {"error": "Dependencies missing"})

        if self.preserve_cylinders:
            return self._convert_with_cylinders(mesh)
        else:
            return self._convert_solid_only(mesh)

    def _convert_with_cylinders(self, mesh: 'pv.PolyData') -> FinalResult:
        """Konvertiert mit analytischen Zylinder-Surfaces (als Compound)."""
        stats = {
            'mesh_faces': mesh.n_cells,
            'cylinders_detected': 0,
            'holes_detected': 0,
            'analytical_cylinders': 0,
            'triangulated_faces': 0,
            'total_faces': 0
        }

        logger.debug("=== Final Mesh Converter (Cylinder Mode) ===")

        faces_arr = mesh.faces.reshape(-1, 4)[:, 1:4]
        points = mesh.points
        precision = 4

        # 1. Erkenne Zylinder
        logger.debug("Schritt 1: Erkenne Zylinder-Löcher...")
        detector = MeshPrimitiveDetector(
            angle_threshold=self.angle_thresh,
            min_region_faces=self.min_cyl_faces,
            cylinder_tolerance=self.cyl_fit_tol,
            min_inlier_ratio=self.min_inlier
        )

        cylinders, _ = detector.detect_from_mesh(mesh)
        stats['cylinders_detected'] = len(cylinders)

        hole_cylinders = []
        cylinder_face_indices = set()

        for cyl in cylinders:
            if cyl.radius < self.min_radius or cyl.radius > self.max_radius:
                continue
            if self._is_hole(cyl, faces_arr, points):
                hole_cylinders.append(cyl)
                cylinder_face_indices.update(cyl.face_indices)

        stats['holes_detected'] = len(hole_cylinders)
        logger.debug(f"  {len(hole_cylinders)} Zylinder-Löcher erkannt")

        # 2. Erstelle Vertex/Edge-Pool
        logger.debug("Schritt 2: Erstelle Geometry...")
        vertex_pool = {}
        edge_pool = {}

        def get_key(p):
            return (round(p[0], precision), round(p[1], precision), round(p[2], precision))

        def get_vertex(p):
            key = get_key(p)
            if key not in vertex_pool:
                vertex_pool[key] = gp_Pnt(float(p[0]), float(p[1]), float(p[2]))
            return vertex_pool[key], key

        def get_edge(key1, key2, p1, p2):
            edge_key = (min(key1, key2), max(key1, key2))
            if edge_key not in edge_pool:
                builder = BRepBuilderAPI_MakeEdge(p1, p2)
                if builder.IsDone():
                    edge_pool[edge_key] = builder.Edge()
            return edge_pool.get(edge_key)

        # 3. Erstelle alle Faces
        logger.debug("Schritt 3: Erstelle Faces...")
        all_faces = []
        cylinder_boundaries = defaultdict(list)

        # Triangulierte Faces (ohne Zylinder)
        for face_idx in range(len(faces_arr)):
            v0, v1, v2 = faces_arr[face_idx]
            p0, p1, p2 = points[v0], points[v1], points[v2]

            gp0, k0 = get_vertex(p0)
            gp1, k1 = get_vertex(p1)
            gp2, k2 = get_vertex(p2)

            if face_idx in cylinder_face_indices:
                # Sammle für Boundary-Detection
                for cyl_idx, cyl in enumerate(hole_cylinders):
                    if face_idx in cyl.face_indices:
                        cylinder_boundaries[cyl_idx].append((k0, k1))
                        cylinder_boundaries[cyl_idx].append((k1, k2))
                        cylinder_boundaries[cyl_idx].append((k2, k0))
                        break
                continue

            e0 = get_edge(k0, k1, gp0, gp1)
            e1 = get_edge(k1, k2, gp1, gp2)
            e2 = get_edge(k2, k0, gp2, gp0)

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
            except Exception as e:
                logger.debug(f"[meshconverter] Fehler: {e}")
                continue

        stats['triangulated_faces'] = len(all_faces)
        logger.debug(f"  {len(all_faces)} triangulierte Faces")

        # 4. Analytische Zylinder
        logger.debug("Schritt 4: Erstelle analytische Zylinder...")

        for cyl_idx, cyl in enumerate(hole_cylinders):
            # Finde Boundary-Punkte für V-Bereich
            edge_count = defaultdict(int)
            for e in cylinder_boundaries[cyl_idx]:
                key = (min(e[0], e[1]), max(e[0], e[1]))
                edge_count[key] += 1

            boundary_edges = [k for k, v in edge_count.items() if v == 1]

            if len(boundary_edges) < 6:
                continue

            boundary_points = set()
            for e in boundary_edges:
                boundary_points.add(e[0])
                boundary_points.add(e[1])

            boundary_coords = np.array([list(p) for p in boundary_points])

            # Berechne V-Bereich
            axis = np.array(cyl.axis)
            axis = axis / np.linalg.norm(axis)
            center = np.array(cyl.center)

            projections = np.dot(boundary_coords - center, axis)
            v_min, v_max = projections.min(), projections.max()

            # Erstelle Zylinder-Face
            cyl_face = self._create_cylinder_face(cyl, v_min, v_max)

            if cyl_face is not None:
                all_faces.append(cyl_face)
                stats['analytical_cylinders'] += 1
                logger.debug(f"  Zylinder {cyl_idx+1}: R={cyl.radius:.2f}mm erstellt")

        stats['total_faces'] = len(all_faces)
        logger.debug(f"  Total: {len(all_faces)} Faces")

        # 5. Compound erstellen (KEIN Sewing!)
        logger.debug("Schritt 5: Erstelle Compound...")
        builder = BRep_Builder()
        compound = TopoDS_Compound()
        builder.MakeCompound(compound)

        for face in all_faces:
            builder.Add(compound, face)

        # Zähle zylindrische Faces
        cyl_count = self._count_cylindrical_faces(compound)

        logger.debug(f"Fertig: {len(all_faces)} Faces, {cyl_count} CYLINDRICAL_SURFACE")

        return FinalResult(
            compound,
            "SUCCESS",
            stats,
            is_solid=False,
            cylindrical_surfaces=cyl_count
        )

    def _convert_solid_only(self, mesh: 'pv.PolyData') -> FinalResult:
        """Konvertiert zu wasserdichtem Solid (ohne analytische Zylinder)."""
        stats = {
            'mesh_faces': mesh.n_cells,
            'brep_faces': 0
        }

        logger.debug("=== Final Mesh Converter (Solid Mode) ===")

        faces_arr = mesh.faces.reshape(-1, 4)[:, 1:4]
        points = mesh.points
        precision = 4

        vertex_pool = {}
        edge_pool = {}

        def get_key(p):
            return (round(p[0], precision), round(p[1], precision), round(p[2], precision))

        def get_vertex(p):
            key = get_key(p)
            if key not in vertex_pool:
                vertex_pool[key] = gp_Pnt(float(p[0]), float(p[1]), float(p[2]))
            return vertex_pool[key], key

        def get_edge(key1, key2, p1, p2):
            edge_key = (min(key1, key2), max(key1, key2))
            if edge_key not in edge_pool:
                builder = BRepBuilderAPI_MakeEdge(p1, p2)
                if builder.IsDone():
                    edge_pool[edge_key] = builder.Edge()
            return edge_pool.get(edge_key)

        # Erstelle alle Faces
        logger.debug("Erstelle Faces...")
        all_faces = []

        for face_idx in range(len(faces_arr)):
            v0, v1, v2 = faces_arr[face_idx]
            p0, p1, p2 = points[v0], points[v1], points[v2]

            gp0, k0 = get_vertex(p0)
            gp1, k1 = get_vertex(p1)
            gp2, k2 = get_vertex(p2)

            e0 = get_edge(k0, k1, gp0, gp1)
            e1 = get_edge(k1, k2, gp1, gp2)
            e2 = get_edge(k2, k0, gp2, gp0)

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
            except Exception as e:
                logger.debug(f"[meshconverter] Fehler: {e}")
                continue

        logger.debug(f"  {len(all_faces)} Faces erstellt")

        # Sewing
        logger.debug("Sewing...")
        sewer = BRepBuilderAPI_Sewing(self.sewing_tol)
        for face in all_faces:
            sewer.Add(face)

        sewer.Perform()
        sewn = sewer.SewedShape()

        # Solid erstellen
        logger.debug("Solid erstellen...")
        result = self._try_make_solid(sewn)

        if result is not None:
            stats['brep_faces'] = self._count_faces(result)
            logger.debug(f"Fertig: {stats['brep_faces']} Faces")

            return FinalResult(result, "SUCCESS", stats, is_solid=True, cylindrical_surfaces=0)

        return FinalResult(sewn, "SHELL", stats, is_solid=False, cylindrical_surfaces=0)

    def _create_cylinder_face(
        self,
        cyl: CylinderFit,
        v_min: float,
        v_max: float
    ) -> Optional[TopoDS_Face]:
        """Erstellt analytische Zylinderfläche."""
        try:
            axis = np.array(cyl.axis)
            axis = axis / np.linalg.norm(axis)
            center = np.array(cyl.center)
            radius = float(cyl.radius)

            # Referenz-Richtung
            if abs(axis[2]) < 0.9:
                x_axis = np.cross(axis, [0, 0, 1])
            else:
                x_axis = np.cross(axis, [1, 0, 0])
            x_axis = x_axis / np.linalg.norm(x_axis)

            gp_center = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))
            gp_axis = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))
            gp_x = gp_Dir(float(x_axis[0]), float(x_axis[1]), float(x_axis[2]))

            ax3 = gp_Ax3(gp_center, gp_axis, gp_x)
            cyl_surface = Geom_CylindricalSurface(ax3, radius)

            # Face mit parametrischen Bounds
            face_maker = BRepBuilderAPI_MakeFace(
                cyl_surface,
                0.0, 2 * np.pi,
                float(v_min),
                float(v_max),
                1e-6
            )

            if face_maker.IsDone():
                face = face_maker.Face()
                face.Reverse()  # Loch = Normale nach innen
                return face

            return None

        except Exception as e:
            logger.debug(f"Exception: {e}")
            return None

    def _try_make_solid(self, shape: TopoDS_Shape) -> Optional[TopoDS_Shape]:
        """Versucht Shell zu Solid zu machen."""
        if shape.IsNull():
            return None

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
        count = 0
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            face = TopoDS.Face_s(exp.Current())
            try:
                adaptor = BRepAdaptor_Surface(face)
                if adaptor.GetType() == GeomAbs_Cylinder:
                    count += 1
            except Exception as e:
                logger.debug(f"[meshconverter] Fehler: {e}")
                pass
            exp.Next()
        return count
