"""
Selective Mesh Converter - Konvertiert Mesh mit selektiven analytischen Surfaces.

Strategie:
1. Erkenne Zylinder-Regionen auf Mesh
2. Finde Boundary-Vertices jeder Zylinder-Region
3. Fitte Kreise an die Boundaries (oben/unten)
4. Erstelle BREP:
   - Triangulierte Faces für NICHT-Zylinder Regionen
   - Analytische Zylinderfläche für Zylinder-Regionen
5. Nähe zusammen

Der Trick: Wir erstellen die Zylinderfläche VON ANFANG AN analytisch,
statt sie nachträglich zu ersetzen.
"""

import numpy as np
from typing import List, Tuple, Optional, Dict, Set
from dataclasses import dataclass
from loguru import logger
from collections import defaultdict

try:
    from OCP.TopoDS import TopoDS, TopoDS_Shape, TopoDS_Solid, TopoDS_Shell, TopoDS_Face, TopoDS_Edge, TopoDS_Wire, TopoDS_Vertex
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
    from OCP.GC import GC_MakeCircle
    from OCP.GCE2d import GCE2d_MakeCircle
    from OCP.Geom import Geom_Circle
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
class SelectiveResult:
    """Ergebnis der selektiven Konvertierung."""
    solid: Optional[object]  # TopoDS_Shape
    status: str
    stats: Dict
    analytical_cylinders: int = 0


class SelectiveMeshConverter:
    """
    Konvertiert Mesh zu BREP mit analytischen Zylinderflächen für Löcher.

    Im Gegensatz zu anderen Ansätzen werden die Zylinder von Anfang an
    als analytische Flächen erstellt, nicht nachträglich ersetzt.
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
        sewing_tolerance: float = 0.1,
        circle_fit_tolerance: float = 0.5
    ):
        self.angle_thresh = angle_threshold
        self.min_cyl_faces = min_cylinder_faces
        self.cyl_fit_tol = cylinder_fit_tolerance
        self.min_inlier = min_inlier_ratio
        self.min_radius = min_cylinder_radius
        self.max_radius = max_cylinder_radius
        self.sewing_tol = sewing_tolerance
        self.circle_tol = circle_fit_tolerance

    def convert(self, mesh: 'pv.PolyData') -> SelectiveResult:
        """Konvertiert Mesh mit selektiven analytischen Flächen."""
        if not HAS_OCP or not HAS_PYVISTA:
            return SelectiveResult(None, "FAILED", {"error": "Dependencies missing"})

        stats = {
            'mesh_faces': mesh.n_cells,
            'cylinders_detected': 0,
            'holes_detected': 0,
            'analytical_cylinders': 0,
            'triangulated_faces': 0,
            'brep_faces_final': 0
        }

        logger.info("=== Selective Mesh Converter ===")
        logger.info(f"Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

        faces = mesh.faces.reshape(-1, 4)[:, 1:4]
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
            if self._is_hole(cyl, faces, points):
                hole_cylinders.append(cyl)
                cylinder_face_indices.update(cyl.face_indices)
                logger.info(f"  Loch: R={cyl.radius:.2f}mm, H={cyl.height:.2f}mm, {len(cyl.face_indices)} Faces")

        stats['holes_detected'] = len(hole_cylinders)

        # 2. Erstelle Vertex-Pool
        logger.info("Schritt 2: Erstelle Vertex-Pool...")
        vertex_pool = {}
        precision = 4  # Dezimalstellen für Vertex-Matching

        def get_vertex(p):
            key = (round(p[0], precision), round(p[1], precision), round(p[2], precision))
            if key not in vertex_pool:
                vertex_pool[key] = gp_Pnt(float(p[0]), float(p[1]), float(p[2]))
            return vertex_pool[key]

        # 3. Erstelle Edge-Map für NICHT-Zylinder Faces
        logger.info("Schritt 3: Erstelle Edge-Map...")
        edge_map = {}

        def get_edge(p1_key, p2_key, p1, p2):
            key = (min(p1_key, p2_key), max(p1_key, p2_key))
            if key not in edge_map:
                edge_builder = BRepBuilderAPI_MakeEdge(p1, p2)
                if edge_builder.IsDone():
                    edge_map[key] = edge_builder.Edge()
            return edge_map.get(key)

        # 4. Erstelle triangulierte Faces für NICHT-Zylinder
        logger.info("Schritt 4: Erstelle Faces...")
        triangulated_faces = []
        cylinder_boundary_edges = defaultdict(list)  # cyl_idx -> list of (p1_key, p2_key)

        for face_idx in range(len(faces)):
            v0, v1, v2 = faces[face_idx]
            p0, p1, p2 = points[v0], points[v1], points[v2]

            p0_key = (round(p0[0], precision), round(p0[1], precision), round(p0[2], precision))
            p1_key = (round(p1[0], precision), round(p1[1], precision), round(p1[2], precision))
            p2_key = (round(p2[0], precision), round(p2[1], precision), round(p2[2], precision))

            if face_idx in cylinder_face_indices:
                # Diese Face gehört zu einem Zylinder
                # Finde welchem Zylinder
                for cyl_idx, cyl in enumerate(hole_cylinders):
                    if face_idx in cyl.face_indices:
                        # Speichere Edges für Boundary-Detection
                        cylinder_boundary_edges[cyl_idx].append((p0_key, p1_key))
                        cylinder_boundary_edges[cyl_idx].append((p1_key, p2_key))
                        cylinder_boundary_edges[cyl_idx].append((p2_key, p0_key))
                        break
                continue  # Überspringe diese Face

            # Normale Face - trianguliert
            gp_p0 = get_vertex(p0)
            gp_p1 = get_vertex(p1)
            gp_p2 = get_vertex(p2)

            e0 = get_edge(p0_key, p1_key, gp_p0, gp_p1)
            e1 = get_edge(p1_key, p2_key, gp_p1, gp_p2)
            e2 = get_edge(p2_key, p0_key, gp_p2, gp_p0)

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
                        triangulated_faces.append(face_builder.Face())
            except:
                continue

        stats['triangulated_faces'] = len(triangulated_faces)
        logger.info(f"  {len(triangulated_faces)} triangulierte Faces")

        # 5. Erstelle analytische Zylinder-Faces
        logger.info("Schritt 5: Erstelle analytische Zylinder-Faces...")
        analytical_faces = []

        for cyl_idx, cyl in enumerate(hole_cylinders):
            # Finde Boundary-Edges (Edges die nur 1x vorkommen)
            edge_count = defaultdict(int)
            for e in cylinder_boundary_edges[cyl_idx]:
                key = (min(e[0], e[1]), max(e[0], e[1]))
                edge_count[key] += 1

            boundary_edges = [k for k, v in edge_count.items() if v == 1]
            logger.info(f"  Zylinder {cyl_idx+1}: {len(boundary_edges)} Boundary-Edges")

            if len(boundary_edges) < 6:  # Mindestens 2 Kreise mit je 3 Edges
                logger.warning(f"    Zu wenige Boundary-Edges")
                continue

            # Finde die Boundary-Punkte und gruppiere sie in Kreise
            boundary_points = set()
            for e in boundary_edges:
                boundary_points.add(e[0])
                boundary_points.add(e[1])

            boundary_points = list(boundary_points)
            boundary_coords = np.array([list(p) for p in boundary_points])

            # Projiziere auf Zylinder-Achse um oben/unten zu trennen
            axis = np.array(cyl.axis)
            axis = axis / np.linalg.norm(axis)
            center = np.array(cyl.center)

            projections = np.dot(boundary_coords - center, axis)

            # Finde 2 Cluster (oben und unten)
            proj_min, proj_max = projections.min(), projections.max()
            proj_mid = (proj_min + proj_max) / 2

            bottom_mask = projections < proj_mid
            top_mask = ~bottom_mask

            bottom_points = boundary_coords[bottom_mask]
            top_points = boundary_coords[top_mask]

            logger.info(f"    Bottom: {len(bottom_points)} Punkte, Top: {len(top_points)} Punkte")

            if len(bottom_points) < 3 or len(top_points) < 3:
                logger.warning(f"    Nicht genug Punkte für Kreise")
                continue

            # Fitte Kreise
            bottom_circle = self._fit_circle_3d(bottom_points, axis, center)
            top_circle = self._fit_circle_3d(top_points, axis, center)

            if bottom_circle is None or top_circle is None:
                logger.warning(f"    Kreis-Fit fehlgeschlagen")
                continue

            # Erstelle analytische Zylinderfläche
            cyl_face = self._create_cylinder_face_with_circles(
                cyl, bottom_circle, top_circle
            )

            if cyl_face is not None:
                analytical_faces.append(cyl_face)
                stats['analytical_cylinders'] += 1
                logger.success(f"    Analytische Zylinderfläche erstellt")
            else:
                logger.warning(f"    Zylinderflächen-Erstellung fehlgeschlagen")

        # 6. Sewing
        logger.info("Schritt 6: Sewing...")
        sewer = BRepBuilderAPI_Sewing(self.sewing_tol)

        for face in triangulated_faces:
            sewer.Add(face)

        for face in analytical_faces:
            sewer.Add(face)

        sewer.Perform()
        sewn = sewer.SewedShape()

        if sewn.IsNull():
            logger.error("Sewing fehlgeschlagen")
            return SelectiveResult(None, "SEWING_FAILED", stats)

        # 7. Solid erstellen
        logger.info("Schritt 7: Solid erstellen...")
        result = self._try_make_solid(sewn)

        stats['brep_faces_final'] = self._count_faces(result) if result else 0

        if stats['analytical_cylinders'] > 0:
            logger.success(f"Fertig: {stats['analytical_cylinders']} analytische Zylinder, {stats['brep_faces_final']} Faces total")
            return SelectiveResult(result, "SUCCESS", stats, stats['analytical_cylinders'])
        else:
            logger.info(f"Keine analytischen Zylinder, {stats['brep_faces_final']} triangulierte Faces")
            return SelectiveResult(result, "NO_ANALYTICAL", stats, 0)

    def _fit_circle_3d(self, points: np.ndarray, axis: np.ndarray, cyl_center: np.ndarray) -> Optional[Dict]:
        """
        Fittet einen Kreis an 3D Punkte die auf einer Ebene senkrecht zur Achse liegen.
        """
        if len(points) < 3:
            return None

        # Projiziere Punkte auf Ebene senkrecht zur Achse
        # Finde Zentrum der Punkte auf der Achse
        centroid = points.mean(axis=0)
        proj = np.dot(centroid - cyl_center, axis)
        plane_center = cyl_center + proj * axis

        # Projiziere Punkte in 2D (lokales Koordinatensystem)
        # X-Achse: senkrecht zu axis
        if abs(axis[2]) < 0.9:
            x_axis = np.cross(axis, [0, 0, 1])
        else:
            x_axis = np.cross(axis, [1, 0, 0])
        x_axis = x_axis / np.linalg.norm(x_axis)
        y_axis = np.cross(axis, x_axis)

        # Punkte in 2D
        local_2d = []
        for p in points:
            v = p - plane_center
            x = np.dot(v, x_axis)
            y = np.dot(v, y_axis)
            local_2d.append([x, y])
        local_2d = np.array(local_2d)

        # Fitte Kreis in 2D
        # Algebraischer Fit: (x-cx)² + (y-cy)² = r²
        A = np.column_stack([
            2 * local_2d,
            np.ones(len(local_2d))
        ])
        b = np.sum(local_2d**2, axis=1)

        try:
            result, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
            cx, cy, d = result
            radius = np.sqrt(d + cx**2 + cy**2)
        except:
            return None

        # Validiere Fit
        distances = np.sqrt((local_2d[:, 0] - cx)**2 + (local_2d[:, 1] - cy)**2)
        error = np.mean(np.abs(distances - radius))

        if error > self.circle_tol:
            logger.debug(f"    Kreis-Fit Error zu groß: {error:.3f}mm")
            return None

        # Kreis-Zentrum in 3D
        circle_center_3d = plane_center + cx * x_axis + cy * y_axis

        return {
            'center': circle_center_3d,
            'radius': radius,
            'axis': axis,
            'plane_z': proj,  # Position entlang der Zylinder-Achse
            'x_axis': x_axis,
            'y_axis': y_axis
        }

    def _create_cylinder_face_with_circles(
        self,
        cyl: CylinderFit,
        bottom_circle: Dict,
        top_circle: Dict
    ) -> Optional[TopoDS_Face]:
        """
        Erstellt eine zylindrische Face begrenzt durch zwei Kreise.
        """
        try:
            # Mittlere Werte für Zylinder-Parameter
            avg_radius = (bottom_circle['radius'] + top_circle['radius']) / 2
            axis = np.array(cyl.axis)
            axis = axis / np.linalg.norm(axis)

            # Zylinder-Zentrum zwischen den Kreisen
            center = (bottom_circle['center'] + top_circle['center']) / 2

            # Koordinatensystem für Zylinder
            gp_center = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))
            gp_axis = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))

            # Referenz-Richtung
            x_axis = bottom_circle['x_axis']
            gp_x = gp_Dir(float(x_axis[0]), float(x_axis[1]), float(x_axis[2]))

            ax3 = gp_Ax3(gp_center, gp_axis, gp_x)

            # Zylindrische Oberfläche
            cyl_surface = Geom_CylindricalSurface(ax3, float(avg_radius))

            # V-Bereich aus Kreis-Positionen
            v_bottom = float(bottom_circle['plane_z'])
            v_top = float(top_circle['plane_z'])

            if v_bottom > v_top:
                v_bottom, v_top = v_top, v_bottom

            # U-Bereich = voller Kreis
            u_min, u_max = 0.0, 2 * np.pi

            # Kleine Erweiterung für besseres Sewing
            margin = 0.01
            v_min = v_bottom - margin
            v_max = v_top + margin

            logger.debug(f"    Zylinder: R={avg_radius:.3f}, V=[{v_min:.2f}, {v_max:.2f}]")

            # Face erstellen
            face_maker = BRepBuilderAPI_MakeFace(cyl_surface, u_min, u_max, v_min, v_max, 1e-6)

            if face_maker.IsDone():
                face = face_maker.Face()
                # Orientierung für Loch: Normale nach innen
                face.Reverse()
                return face

            return None

        except Exception as e:
            logger.debug(f"    Exception: {e}")
            return None

    def _create_cylinder_face_with_polygon_boundaries(
        self,
        cyl: CylinderFit,
        bottom_points: np.ndarray,
        top_points: np.ndarray,
        vertex_pool: Dict
    ) -> Optional[TopoDS_Face]:
        """
        Erstellt zylindrische Face mit Polygon-Boundaries (aus Mesh-Vertices).

        Die Boundaries sind Polygone aus den tatsächlichen Mesh-Vertices,
        nicht perfekte Kreise. Das ermöglicht sauberes Sewing.
        """
        try:
            # Sortiere Punkte nach Winkel um Achse
            axis = np.array(cyl.axis)
            axis = axis / np.linalg.norm(axis)
            center = np.array(cyl.center)

            # Referenz-Richtung
            if abs(axis[2]) < 0.9:
                x_axis = np.cross(axis, [0, 0, 1])
            else:
                x_axis = np.cross(axis, [1, 0, 0])
            x_axis = x_axis / np.linalg.norm(x_axis)
            y_axis = np.cross(axis, x_axis)

            def sort_by_angle(points):
                angles = []
                for p in points:
                    v = p - center
                    # Projiziere auf Ebene
                    v_proj = v - np.dot(v, axis) * axis
                    angle = np.arctan2(np.dot(v_proj, y_axis), np.dot(v_proj, x_axis))
                    angles.append(angle)
                sorted_indices = np.argsort(angles)
                return points[sorted_indices]

            bottom_sorted = sort_by_angle(bottom_points)
            top_sorted = sort_by_angle(top_points)

            # Berechne Radius
            radius = float(cyl.radius)

            # Zylinder-Achse und Zentrum
            gp_center = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))
            gp_axis = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))
            gp_x = gp_Dir(float(x_axis[0]), float(x_axis[1]), float(x_axis[2]))

            ax3 = gp_Ax3(gp_center, gp_axis, gp_x)

            # Zylindrische Oberfläche
            cyl_surface = Geom_CylindricalSurface(ax3, radius)

            # Erstelle Polygon-Wire für unten
            bottom_wire = self._create_polygon_wire(bottom_sorted, vertex_pool)
            top_wire = self._create_polygon_wire(top_sorted, vertex_pool)

            if bottom_wire is None or top_wire is None:
                logger.debug("    Polygon-Wire Erstellung fehlgeschlagen")
                return None

            # Erstelle Face mit Surface und Wires
            # Dies ist komplexer - wir müssen die Fläche mit Trimming-Wires erstellen
            # Für jetzt: Verwende einfachen parametrischen Ansatz

            # Berechne V-Bereich
            v_bottom = np.dot(bottom_sorted[0] - center, axis)
            v_top = np.dot(top_sorted[0] - center, axis)

            if v_bottom > v_top:
                v_bottom, v_top = v_top, v_bottom

            margin = 0.05
            v_min = v_bottom - margin
            v_max = v_top + margin

            # Face mit parametrischen Grenzen
            face_maker = BRepBuilderAPI_MakeFace(cyl_surface, 0.0, 2*np.pi, v_min, v_max, 1e-6)

            if face_maker.IsDone():
                face = face_maker.Face()
                face.Reverse()  # Loch-Orientierung
                return face

            return None

        except Exception as e:
            logger.debug(f"    Exception bei Polygon-Boundary: {e}")
            return None

    def _create_polygon_wire(self, points: np.ndarray, vertex_pool: Dict) -> Optional[TopoDS_Wire]:
        """Erstellt geschlossenen Polygon-Wire aus geordneten Punkten."""
        if len(points) < 3:
            return None

        try:
            wire_builder = BRepBuilderAPI_MakeWire()
            precision = 4

            for i in range(len(points)):
                p1 = points[i]
                p2 = points[(i + 1) % len(points)]

                # Verwende Vertex-Pool für konsistente Vertices
                key1 = (round(p1[0], precision), round(p1[1], precision), round(p1[2], precision))
                key2 = (round(p2[0], precision), round(p2[1], precision), round(p2[2], precision))

                if key1 == key2:
                    continue

                gp_p1 = vertex_pool.get(key1, gp_Pnt(float(p1[0]), float(p1[1]), float(p1[2])))
                gp_p2 = vertex_pool.get(key2, gp_Pnt(float(p2[0]), float(p2[1]), float(p2[2])))

                edge_builder = BRepBuilderAPI_MakeEdge(gp_p1, gp_p2)
                if edge_builder.IsDone():
                    wire_builder.Add(edge_builder.Edge())

            if wire_builder.IsDone():
                return wire_builder.Wire()

            return None

        except Exception:
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

        except Exception as e:
            logger.debug(f"    MakeSolid Exception: {e}")
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
