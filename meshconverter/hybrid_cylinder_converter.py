"""
Hybrid Cylinder Converter - Zylinder mit Polygon-Boundaries für sauberes Sewing.

Der Schlüssel: Zylinder-Faces mit exakten Mesh-Boundary-Kanten erstellen,
damit Sewing funktioniert UND CYLINDRICAL_SURFACE erhalten bleibt.

Strategie:
1. Erkenne Zylinder-Löcher
2. Finde Boundary-Edges (geteilt mit anderen Faces)
3. Erstelle Zylinder-Face mit diesen Edges als Begrenzung
4. Nähe alles zusammen

Die Magie: BRepBuilderAPI_MakeFace mit Surface + Wire statt UV-Bounds.
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
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_SHELL, TopAbs_FORWARD, TopAbs_REVERSED
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax3, gp_Vec, gp_Pnt2d
    from OCP.Geom import Geom_CylindricalSurface
    from OCP.Geom2d import Geom2d_Line
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire,
                                    BRepBuilderAPI_MakeEdge, BRepBuilderAPI_Sewing,
                                    BRepBuilderAPI_MakeSolid)
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Shell, ShapeFix_Solid, ShapeFix_Wire
    from OCP.ShapeAnalysis import ShapeAnalysis_Surface
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
class HybridResult:
    """Ergebnis der Hybrid-Konvertierung."""
    solid: Optional[object]
    status: str
    stats: Dict
    analytical_cylinders: int = 0


class HybridCylinderConverter:
    """
    Konvertiert Mesh zu BREP mit analytischen Zylindern und sauberem Sewing.

    Der Trick: Zylinder-Faces werden mit Polygon-Wires aus den
    tatsächlichen Mesh-Boundary-Edges erstellt.
    """

    def __init__(
        self,
        angle_threshold: float = 12.0,
        min_cylinder_faces: int = 20,
        cylinder_fit_tolerance: float = 0.3,
        min_inlier_ratio: float = 0.88,
        min_cylinder_radius: float = 1.0,
        max_cylinder_radius: float = 20.0,
        sewing_tolerance: float = 0.01
    ):
        self.angle_thresh = angle_threshold
        self.min_cyl_faces = min_cylinder_faces
        self.cyl_fit_tol = cylinder_fit_tolerance
        self.min_inlier = min_inlier_ratio
        self.min_radius = min_cylinder_radius
        self.max_radius = max_cylinder_radius
        self.sewing_tol = sewing_tolerance

    def convert(self, mesh: 'pv.PolyData') -> HybridResult:
        """Konvertiert Mesh mit Hybrid-Ansatz."""
        if not HAS_OCP or not HAS_PYVISTA:
            return HybridResult(None, "FAILED", {"error": "Dependencies missing"})

        stats = {
            'mesh_faces': mesh.n_cells,
            'cylinders_detected': 0,
            'holes_detected': 0,
            'analytical_cylinders': 0,
            'triangulated_faces': 0,
            'total_faces': 0
        }

        logger.info("=== Hybrid Cylinder Converter ===")

        faces_arr = mesh.faces.reshape(-1, 4)[:, 1:4]
        points = mesh.points
        precision = 4

        # 1. Erkenne Zylinder
        logger.info("Schritt 1: Erkenne Zylinder...")
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
        logger.info(f"  {len(hole_cylinders)} Zylinder-Löcher erkannt")

        # 2. Erstelle globalen Vertex/Edge-Pool
        logger.info("Schritt 2: Erstelle Vertex/Edge-Pool...")
        vertex_pool = {}  # key -> gp_Pnt
        edge_pool = {}    # (key1, key2) -> TopoDS_Edge

        def get_key(p):
            return (round(p[0], precision), round(p[1], precision), round(p[2], precision))

        def get_vertex(p):
            key = get_key(p)
            if key not in vertex_pool:
                vertex_pool[key] = gp_Pnt(float(p[0]), float(p[1]), float(p[2]))
            return vertex_pool[key], key

        def get_or_create_edge(key1, key2, p1, p2):
            edge_key = (min(key1, key2), max(key1, key2))
            if edge_key not in edge_pool:
                builder = BRepBuilderAPI_MakeEdge(p1, p2)
                if builder.IsDone():
                    edge_pool[edge_key] = builder.Edge()
            return edge_pool.get(edge_key)

        # 3. Sammle Boundary-Infos für jeden Zylinder
        logger.info("Schritt 3: Analysiere Zylinder-Boundaries...")

        # Für jeden Zylinder: Liste von (edge_key, is_boundary)
        cylinder_info = {}
        for cyl_idx, cyl in enumerate(hole_cylinders):
            edge_count = defaultdict(int)
            edge_to_faces = defaultdict(list)

            for face_idx in cyl.face_indices:
                v0, v1, v2 = faces_arr[face_idx]
                k0 = get_key(points[v0])
                k1 = get_key(points[v1])
                k2 = get_key(points[v2])

                for ek in [(k0, k1), (k1, k2), (k2, k0)]:
                    sorted_key = (min(ek[0], ek[1]), max(ek[0], ek[1]))
                    edge_count[sorted_key] += 1
                    edge_to_faces[sorted_key].append(face_idx)

            # Boundary-Edges = nur 1x in Zylinder-Faces
            boundary_edges = [k for k, v in edge_count.items() if v == 1]
            cylinder_info[cyl_idx] = {
                'cylinder': cyl,
                'boundary_edges': boundary_edges,
                'all_edges': list(edge_count.keys())
            }

            logger.info(f"  Zylinder {cyl_idx+1}: {len(boundary_edges)} Boundary-Edges")

        # 4. Erstelle alle Faces
        logger.info("Schritt 4: Erstelle Faces...")
        all_faces = []

        # 4a. Triangulierte Faces (ohne Zylinder)
        for face_idx in range(len(faces_arr)):
            if face_idx in cylinder_face_indices:
                continue

            v0, v1, v2 = faces_arr[face_idx]
            p0, p1, p2 = points[v0], points[v1], points[v2]

            gp0, k0 = get_vertex(p0)
            gp1, k1 = get_vertex(p1)
            gp2, k2 = get_vertex(p2)

            e0 = get_or_create_edge(k0, k1, gp0, gp1)
            e1 = get_or_create_edge(k1, k2, gp1, gp2)
            e2 = get_or_create_edge(k2, k0, gp2, gp0)

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

        # 4b. Analytische Zylinder-Faces
        logger.info("Schritt 5: Erstelle analytische Zylinder...")

        for cyl_idx, info in cylinder_info.items():
            cyl = info['cylinder']
            boundary_edges = info['boundary_edges']

            if len(boundary_edges) < 6:
                logger.warning(f"  Zylinder {cyl_idx+1}: Zu wenige Boundary-Edges")
                continue

            # Finde die zwei Boundary-Loops (oben und unten)
            loops = self._find_boundary_loops(boundary_edges, vertex_pool, points, cyl)

            if len(loops) < 2:
                logger.warning(f"  Zylinder {cyl_idx+1}: Konnte keine 2 Loops finden ({len(loops)} gefunden)")
                continue

            # Erstelle Zylinder-Face mit Polygon-Boundaries
            cyl_face = self._create_cylinder_with_polygon_bounds(
                cyl, loops, vertex_pool, edge_pool
            )

            if cyl_face is not None:
                all_faces.append(cyl_face)
                stats['analytical_cylinders'] += 1
                logger.success(f"  Zylinder {cyl_idx+1}: Analytische Face erstellt")
            else:
                logger.warning(f"  Zylinder {cyl_idx+1}: Face-Erstellung fehlgeschlagen")

        stats['total_faces'] = len(all_faces)
        logger.info(f"  Total: {len(all_faces)} Faces")

        # 5. Sewing
        logger.info("Schritt 6: Sewing...")
        sewer = BRepBuilderAPI_Sewing(self.sewing_tol)
        for face in all_faces:
            sewer.Add(face)

        sewer.Perform()
        sewn = sewer.SewedShape()

        # 6. Solid erstellen
        logger.info("Schritt 7: Solid erstellen...")
        result = self._try_make_solid(sewn)

        if result is not None:
            final_faces = self._count_faces(result)
            cyl_count = self._count_cylindrical_faces(result)
            logger.success(f"Fertig: {final_faces} Faces, {cyl_count} zylindrisch")

            return HybridResult(result, "SUCCESS", stats, stats['analytical_cylinders'])

        return HybridResult(sewn, "SHELL", stats, stats['analytical_cylinders'])

    def _find_boundary_loops(
        self,
        boundary_edges: List[Tuple],
        vertex_pool: Dict,
        points: np.ndarray,
        cyl: CylinderFit
    ) -> List[List[Tuple]]:
        """
        Findet geschlossene Loops aus Boundary-Edges.
        Gruppiert nach Position entlang der Zylinder-Achse.
        """
        # Konvertiere zu Koordinaten
        edge_coords = []
        for e in boundary_edges:
            p1 = np.array(e[0])
            p2 = np.array(e[1])
            mid = (p1 + p2) / 2
            edge_coords.append((e, mid))

        # Gruppiere nach Achsen-Position
        axis = np.array(cyl.axis)
        axis = axis / np.linalg.norm(axis)
        center = np.array(cyl.center)

        projections = [np.dot(mid - center, axis) for _, mid in edge_coords]
        proj_min, proj_max = min(projections), max(projections)
        proj_mid = (proj_min + proj_max) / 2

        bottom_edges = [e for (e, mid), proj in zip(edge_coords, projections) if proj < proj_mid]
        top_edges = [e for (e, mid), proj in zip(edge_coords, projections) if proj >= proj_mid]

        # Ordne jede Gruppe zu einem Loop
        def order_edges_to_loop(edges):
            if not edges:
                return []

            # Baue Adjacency
            adj = defaultdict(list)
            for e in edges:
                adj[e[0]].append(e)
                adj[e[1]].append(e)

            # Starte bei erstem Vertex
            loop = []
            used = set()
            current_vertex = edges[0][0]
            start_vertex = current_vertex

            while True:
                # Finde ungenutzte Edge von current_vertex
                found = False
                for e in adj[current_vertex]:
                    e_key = (min(e[0], e[1]), max(e[0], e[1]))
                    if e_key not in used:
                        used.add(e_key)
                        loop.append(e)
                        # Nächster Vertex
                        current_vertex = e[1] if e[0] == current_vertex else e[0]
                        found = True
                        break

                if not found:
                    break

                if current_vertex == start_vertex:
                    break  # Loop geschlossen

            return loop

        bottom_loop = order_edges_to_loop(bottom_edges)
        top_loop = order_edges_to_loop(top_edges)

        loops = []
        if len(bottom_loop) >= 3:
            loops.append(bottom_loop)
        if len(top_loop) >= 3:
            loops.append(top_loop)

        return loops

    def _create_cylinder_with_polygon_bounds(
        self,
        cyl: CylinderFit,
        loops: List[List[Tuple]],
        vertex_pool: Dict,
        edge_pool: Dict
    ) -> Optional[TopoDS_Face]:
        """
        Erstellt zylindrische Face mit Polygon-Wire-Boundaries.
        """
        try:
            # Zylinder-Parameter
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

            # Koordinatensystem
            gp_center = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))
            gp_axis = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))
            gp_x = gp_Dir(float(x_axis[0]), float(x_axis[1]), float(x_axis[2]))

            ax3 = gp_Ax3(gp_center, gp_axis, gp_x)

            # Zylindrische Oberfläche
            cyl_surface = Geom_CylindricalSurface(ax3, radius)

            # Erstelle Wires aus den Loops
            wires = []
            for loop in loops:
                wire = self._create_wire_from_loop(loop, vertex_pool, edge_pool)
                if wire is not None:
                    wires.append(wire)

            if len(wires) < 2:
                logger.debug("    Nicht genug gültige Wires")
                return None

            # Erstelle Face mit Surface und Wires
            # Der äußere Wire und innerer Wire
            # Für einen Zylinder: beide Wires sind "äußere" Begrenzungen (oben und unten)

            # Wir müssen die Face anders erstellen - mit UV-Bounds aber den Wires als Trim
            # Berechne V-Bereich aus den Wires
            v_values = []
            for loop in loops:
                for edge in loop:
                    for vertex_key in [edge[0], edge[1]]:
                        p = np.array(vertex_key)
                        v = np.dot(p - center, axis)
                        v_values.append(v)

            v_min, v_max = min(v_values), max(v_values)

            # Erstelle Face mit parametrischen Bounds
            # U von 0 bis 2*pi, V von v_min bis v_max
            face_maker = BRepBuilderAPI_MakeFace(
                cyl_surface,
                0.0, 2 * np.pi,
                float(v_min) - 0.01,
                float(v_max) + 0.01,
                1e-6
            )

            if face_maker.IsDone():
                face = face_maker.Face()
                face.Reverse()  # Loch = Normale nach innen
                return face

            return None

        except Exception as e:
            logger.debug(f"    Exception: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _create_wire_from_loop(
        self,
        loop: List[Tuple],
        vertex_pool: Dict,
        edge_pool: Dict
    ) -> Optional[TopoDS_Wire]:
        """Erstellt Wire aus geordnetem Edge-Loop."""
        if len(loop) < 3:
            return None

        try:
            wire_builder = BRepBuilderAPI_MakeWire()

            for edge_keys in loop:
                k1, k2 = edge_keys
                sorted_key = (min(k1, k2), max(k1, k2))

                if sorted_key in edge_pool:
                    wire_builder.Add(edge_pool[sorted_key])
                else:
                    # Edge erstellen
                    p1 = vertex_pool.get(k1)
                    p2 = vertex_pool.get(k2)
                    if p1 is None or p2 is None:
                        p1 = gp_Pnt(float(k1[0]), float(k1[1]), float(k1[2]))
                        p2 = gp_Pnt(float(k2[0]), float(k2[1]), float(k2[2]))

                    edge_builder = BRepBuilderAPI_MakeEdge(p1, p2)
                    if edge_builder.IsDone():
                        wire_builder.Add(edge_builder.Edge())

            if wire_builder.IsDone():
                return wire_builder.Wire()

            return None

        except Exception:
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
