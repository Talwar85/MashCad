"""
MashCad - Hybrid Mesh to BREP Converter
========================================

Kombiniert Primitive-Erkennung (Zylinder, Kegel) mit DirectMesh für optimale Ergebnisse.

Strategie:
1. Erkennt zylindrische Flächen im gesamten Mesh
2. Erstellt echte Geom_CylindricalSurface für Zylinder
3. Konvertiert restliche Dreiecke mit DirectMesh-Ansatz
4. Vereinigt alles zu einem wasserdichten Solid
"""

import numpy as np
from typing import Optional, List, Dict, Tuple, Set
from loguru import logger

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

try:
    from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax3, gp_Pln
    from OCP.Geom import Geom_CylindricalSurface
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeWire,
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_Sewing,
        BRepBuilderAPI_MakeSolid
    )
    from OCP.TopoDS import TopoDS_Edge, TopoDS_Wire, TopoDS_Face, TopoDS, TopoDS_Shell, TopoDS_Solid
    from OCP.ShapeFix import ShapeFix_Solid, ShapeFix_Shell
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.TopAbs import TopAbs_REVERSED, TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    HAS_OCP = True
except ImportError:
    HAS_OCP = False
    logger.warning("OCP nicht verfügbar")

try:
    from sklearn.decomposition import PCA
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

from meshconverter.mesh_converter_v10 import ConversionResult, ConversionStatus


class HybridMeshConverter:
    """
    Hybrid Konverter: Primitive-Erkennung + DirectMesh.

    Erkennt Zylinder, Kegel und andere Primitive und erstellt echte
    analytische Surfaces. Restliche Geometrie wird als planare Faces
    konvertiert.
    """

    def __init__(
        self,
        cylinder_tolerance: float = 0.3,      # mm - max Abweichung für Zylinder
        cylinder_min_angle: float = 30.0,     # Grad - min Krümmung für Zylinder-Region
        cylinder_min_cells: int = 12,         # Min Dreiecke für Zylinder
        sewing_tolerance: float = 0.5,        # mm - höher für Cylinder/Plane Verbindung
        unify_linear_tolerance: float = 0.5,  # mm
        unify_angular_tolerance: float = 1.0  # Grad - streng um Geometriefehler zu vermeiden
    ):
        self.cyl_tol = cylinder_tolerance
        self.cyl_min_angle = np.radians(cylinder_min_angle)
        self.cyl_min_cells = cylinder_min_cells
        self.sewing_tol = sewing_tolerance
        self.unify_linear_tol = unify_linear_tolerance
        self.unify_angular_tol = np.radians(unify_angular_tolerance)

    def convert(self, mesh: 'pv.PolyData') -> ConversionResult:
        """
        Konvertiert Mesh zu BREP mit Primitive-Erkennung.
        """
        if not HAS_OCP or not HAS_PYVISTA:
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message="OCP oder PyVista nicht verfügbar"
            )

        logger.info("=== Hybrid Mesh Converter ===")
        logger.info(f"Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

        stats = {
            'input_points': mesh.n_points,
            'input_faces': mesh.n_cells,
            'cylinders_detected': 0,
            'cylinder_cells': 0
        }

        try:
            # 1. Normalen berechnen
            if 'Normals' not in mesh.cell_data:
                mesh.compute_normals(cell_normals=True, inplace=True)

            # 2. Zylinder erkennen
            logger.info("Erkenne Zylinder...")
            cylinders = self._detect_cylinders(mesh)
            stats['cylinders_detected'] = len(cylinders)

            if cylinders:
                logger.info(f"  → {len(cylinders)} Zylinder erkannt")
                for i, cyl in enumerate(cylinders):
                    logger.debug(f"    Zylinder {i+1}: r={cyl['radius']:.2f}mm, "
                                f"h={cyl['height']:.2f}mm, {len(cyl['cell_ids'])} Cells")
                    stats['cylinder_cells'] += len(cyl['cell_ids'])

            # 3. Sammle alle Zylinder-Cell-IDs
            cylinder_cells: Set[int] = set()
            for cyl in cylinders:
                cylinder_cells.update(cyl['cell_ids'])

            logger.info(f"  → {len(cylinder_cells)} Cells in Zylindern, "
                       f"{mesh.n_cells - len(cylinder_cells)} restliche")

            # 4. Vertex-Pool erstellen
            vertices = self._create_vertex_pool(mesh)

            # 5. Edge-Map erstellen (für alle Dreiecke)
            edge_map = self._create_edge_map(mesh, vertices)
            logger.debug(f"  → {len(edge_map)} unique Edges")

            # 6. Erstelle Faces
            all_faces: List[TopoDS_Face] = []

            # 6a. Zylinder-Faces (mit Mesh-Boundary für korrekte Verbindung)
            # Mindestradius für echte Zylinder-Surfaces (kleinere bleiben als Dreiecke)
            MIN_CYLINDER_RADIUS = 1.0  # mm

            for i, cyl in enumerate(cylinders):
                cyl_face = None

                # Nur für größere Zylinder die Boundary-Methode verwenden
                if cyl['radius'] >= MIN_CYLINDER_RADIUS:
                    cyl_face = self._create_cylinder_face_with_boundary(
                        cyl, mesh, vertices, edge_map
                    )

                if cyl_face is not None:
                    all_faces.append(cyl_face)
                    logger.debug(f"  → Zylinder {i+1} Face erstellt (r={cyl['radius']:.2f}mm)")
                else:
                    # Kleine Zylinder oder Fehler: als Dreiecke behalten
                    if cyl['radius'] < MIN_CYLINDER_RADIUS:
                        logger.debug(f"  → Zylinder {i+1} zu klein (r={cyl['radius']:.2f}mm < {MIN_CYLINDER_RADIUS}mm), nutze Dreiecke")
                    else:
                        logger.warning(f"  → Zylinder {i+1} Face fehlgeschlagen, nutze Dreiecke")
                    for cell_id in cyl['cell_ids']:
                        cylinder_cells.discard(cell_id)

            # 6b. Planare Faces für nicht-Zylinder Dreiecke
            logger.info("Erstelle planare Faces...")
            planar_faces = self._create_planar_faces(
                mesh, vertices, edge_map, cylinder_cells
            )
            all_faces.extend(planar_faces)

            logger.info(f"  → {len(all_faces)} Faces total "
                       f"({len(cylinders)} Zylinder, {len(planar_faces)} planar)")
            stats['faces_created'] = len(all_faces)

            # 7. Sewing
            logger.info("Sewing...")
            result = self._sew_and_make_solid(all_faces, stats)

            logger.info(f"=== Ergebnis: {result.status.name} ===")
            return result

        except Exception as e:
            logger.error(f"Hybrid Konvertierung fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message=f"Fehler: {e}",
                stats=stats
            )

    def _detect_cylinders(self, mesh: 'pv.PolyData') -> List[dict]:
        """
        Erkennt zylindrische Regionen im Mesh.

        Strategie:
        1. Finde gekrümmte Regionen (Normalen divergieren)
        2. Für jede Region: Prüfe ob Zylinder-Fit möglich
        """
        if not HAS_SKLEARN:
            return []

        normals = mesh.cell_data['Normals']
        n_cells = mesh.n_cells

        # Adjacency Map bauen
        adjacency = self._build_adjacency(mesh)

        # Regionen mit divergierenden Normalen finden
        curved_regions = self._find_curved_regions(mesh, normals, adjacency)
        logger.debug(f"  → {len(curved_regions)} gekrümmte Regionen gefunden")

        # Zylinder-Fit für jede Region versuchen
        cylinders = []
        for region_cells in curved_regions:
            if len(region_cells) < self.cyl_min_cells:
                continue

            cyl = self._fit_cylinder(mesh, np.array(region_cells))
            if cyl is not None:
                cylinders.append(cyl)

        return cylinders

    def _find_curved_regions(
        self,
        mesh: 'pv.PolyData',
        normals: np.ndarray,
        adjacency: Dict[int, List[int]]
    ) -> List[List[int]]:
        """
        Findet zusammenhängende Regionen mit divergierenden Normalen.
        """
        n_cells = mesh.n_cells
        visited = set()
        curved_regions = []

        # Threshold für "gleiche" Normale (cos von Winkel)
        planar_threshold = np.cos(self.cyl_min_angle)

        for start_cell in range(n_cells):
            if start_cell in visited:
                continue

            # BFS um zusammenhängende nicht-planare Region zu finden
            region_cells = []
            queue = [start_cell]
            has_curvature = False

            while queue:
                cell_id = queue.pop(0)
                if cell_id in visited:
                    continue

                visited.add(cell_id)
                region_cells.append(cell_id)

                # Prüfe Nachbarn
                for neighbor_id in adjacency.get(cell_id, []):
                    if neighbor_id in visited:
                        continue

                    # Normalen-Unterschied
                    n1 = normals[cell_id]
                    n2 = normals[neighbor_id]
                    dot = np.clip(np.dot(n1, n2), -1.0, 1.0)

                    if dot < planar_threshold:
                        # Signifikanter Normalen-Unterschied = Krümmung
                        has_curvature = True

                    # Füge zu Region hinzu wenn nicht zu unterschiedlich
                    # (bei Zylinder sind benachbarte Dreiecke ähnlich)
                    if dot > 0.5:  # Max 60° Unterschied zwischen Nachbarn
                        queue.append(neighbor_id)

            if has_curvature and len(region_cells) >= self.cyl_min_cells:
                curved_regions.append(region_cells)

        return curved_regions

    def _fit_cylinder(
        self,
        mesh: 'pv.PolyData',
        cell_ids: np.ndarray
    ) -> Optional[dict]:
        """
        Fittet Zylinder auf eine Region.

        Methode:
        1. PCA auf Normalen → Achse (kleinste Varianz)
        2. Punkte auf Achse projizieren → Height
        3. Senkrechte Abstände → Radius
        """
        try:
            # Punkte und Normalen sammeln
            faces = mesh.faces.reshape(-1, 4)[:, 1:4]
            normals_data = mesh.cell_data['Normals']

            points_list = []
            normals_list = []

            for cell_id in cell_ids:
                tri = faces[cell_id]
                for v_idx in tri:
                    points_list.append(mesh.points[v_idx])
                normals_list.append(normals_data[cell_id])

            points = np.array(points_list)
            normals = np.array(normals_list)

            if len(points) < 10:
                return None

            # 1. Achsenrichtung via PCA auf Normalen
            pca = PCA(n_components=3)
            pca.fit(normals)

            # Die Achse ist die Richtung mit KLEINSTER Varianz in den Normalen
            # (bei einem Zylinder sind alle Normalen senkrecht zur Achse)
            axis = pca.components_[-1]
            axis = axis / (np.linalg.norm(axis) + 1e-10)

            # Prüfe ob Normalen wirklich senkrecht zur Achse sind
            dots = np.abs(np.dot(normals, axis))
            mean_dot = np.mean(dots)

            if mean_dot > 0.3:  # Normalen sollten fast senkrecht sein
                # Probiere andere Komponenten
                for i in range(3):
                    test_axis = pca.components_[i]
                    test_dots = np.abs(np.dot(normals, test_axis))
                    if np.mean(test_dots) < mean_dot:
                        axis = test_axis
                        mean_dot = np.mean(test_dots)

            if mean_dot > 0.3:
                return None  # Kein guter Zylinder-Fit

            axis = axis / (np.linalg.norm(axis) + 1e-10)

            # 2. Projektion auf Achse
            centroid = np.mean(points, axis=0)
            proj = np.dot(points - centroid, axis)
            v_min, v_max = proj.min(), proj.max()
            height = v_max - v_min

            if height < 0.1:
                return None  # Zu flach

            # 3. Radius aus senkrechten Abständen
            perp = points - centroid - np.outer(proj, axis)
            distances = np.linalg.norm(perp, axis=1)
            radius = np.median(distances)

            if radius < 0.1 or radius > 10000:
                return None  # Unrealistisch

            # 4. Fitting-Fehler
            errors = np.abs(distances - radius)
            mean_error = np.mean(errors)

            if mean_error > self.cyl_tol:
                return None  # Fit nicht gut genug

            # Center auf Achsen-Mitte
            center = centroid + (v_min + v_max) / 2 * axis

            logger.debug(f"    Zylinder: r={radius:.2f}mm, h={height:.2f}mm, "
                        f"error={mean_error:.3f}mm, axis_dot={mean_dot:.3f}")

            return {
                'cell_ids': cell_ids.tolist(),
                'center': center,
                'axis': axis,
                'radius': radius,
                'height': height,
                'v_min': v_min,
                'v_max': v_max,
                'error': mean_error
            }

        except Exception as e:
            logger.debug(f"Zylinder-Fit fehlgeschlagen: {e}")
            return None

    def _create_cylinder_face_with_boundary(
        self,
        cyl: dict,
        mesh: 'pv.PolyData',
        vertices: List['gp_Pnt'],
        edge_map: Dict[Tuple[int, int], 'TopoDS_Edge']
    ) -> Optional[TopoDS_Face]:
        """
        Erstellt BREP Face für erkannten Zylinder MIT Mesh-Boundary-Kanten.

        Verwendet die tatsächlichen Mesh-Kanten als Boundary, damit
        die Zylinder-Face korrekt mit den benachbarten Faces verbunden wird.
        """
        try:
            center = cyl['center']
            axis = cyl['axis']
            radius = cyl['radius']
            cell_ids = cyl['cell_ids']

            # 1. Finde Boundary-Edges der Zylinder-Region
            boundary_edges = self._find_region_boundary_edges(mesh, cell_ids)

            if len(boundary_edges) < 3:
                logger.debug("Nicht genug Boundary-Edges für Zylinder")
                return None

            # 2. Sortiere Boundary-Edges zu geschlossenen Loops
            edge_loops = self._sort_edges_to_loops(boundary_edges)

            if not edge_loops:
                logger.debug("Keine geschlossenen Edge-Loops gefunden")
                return None

            # 3. Erstelle Wires aus den Edge-Loops
            wires = []
            for loop in edge_loops:
                wire = self._create_wire_from_edge_loop(loop, vertices, edge_map)
                if wire is not None:
                    wires.append(wire)

            if not wires:
                logger.debug("Keine Wires erstellt")
                return None

            # 4. Erstelle zylindrische Surface
            gp_center = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))
            gp_axis = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))

            if abs(axis[2]) < 0.9:
                x_dir = np.cross(axis, [0, 0, 1])
            else:
                x_dir = np.cross(axis, [1, 0, 0])
            x_dir = x_dir / (np.linalg.norm(x_dir) + 1e-10)
            gp_x_dir = gp_Dir(float(x_dir[0]), float(x_dir[1]), float(x_dir[2]))

            ax3 = gp_Ax3(gp_center, gp_axis, gp_x_dir)
            cyl_surface = Geom_CylindricalSurface(ax3, radius)

            # 5. Erstelle Face mit dem ersten Wire (Außen-Boundary)
            face_builder = BRepBuilderAPI_MakeFace(cyl_surface, wires[0], True)

            if not face_builder.IsDone():
                logger.debug("MakeFace mit Wire fehlgeschlagen")
                return None

            face = face_builder.Face()

            # Weitere Wires als Löcher hinzufügen
            for inner_wire in wires[1:]:
                face_builder = BRepBuilderAPI_MakeFace(face, inner_wire)
                if face_builder.IsDone():
                    face = face_builder.Face()

            return face

        except Exception as e:
            logger.warning(f"Zylinder-Face mit Boundary fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _find_region_boundary_edges(
        self,
        mesh: 'pv.PolyData',
        cell_ids: List[int]
    ) -> List[Tuple[int, int]]:
        """
        Findet die Boundary-Kanten einer Region.

        Eine Kante ist Boundary wenn sie nur von EINEM Cell in der Region verwendet wird.
        """
        cell_ids_set = set(cell_ids)
        edge_count: Dict[Tuple[int, int], int] = {}

        faces = mesh.faces.reshape(-1, 4)[:, 1:4]

        for cell_id in cell_ids:
            tri = faces[cell_id]
            for i in range(3):
                v1, v2 = int(tri[i]), int(tri[(i + 1) % 3])
                edge_key = (min(v1, v2), max(v1, v2))

                if edge_key not in edge_count:
                    edge_count[edge_key] = 0
                edge_count[edge_key] += 1

        # Boundary-Edges sind die mit count == 1
        boundary = [edge for edge, count in edge_count.items() if count == 1]
        return boundary

    def _sort_edges_to_loops(
        self,
        edges: List[Tuple[int, int]]
    ) -> List[List[Tuple[int, int, int, int]]]:
        """
        Sortiert Edges zu geschlossenen Loops.

        Returns Liste von Loops, wobei jeder Loop eine Liste von
        (v_from, v_to, edge_key_0, edge_key_1) ist.
        """
        if not edges:
            return []

        # Baue Adjazenzliste
        adj: Dict[int, List[Tuple[int, int, int]]] = {}
        for edge in edges:
            v1, v2 = edge
            if v1 not in adj:
                adj[v1] = []
            if v2 not in adj:
                adj[v2] = []
            adj[v1].append((v2, edge[0], edge[1]))
            adj[v2].append((v1, edge[0], edge[1]))

        loops = []
        used_edges = set()

        for start_edge in edges:
            if start_edge in used_edges:
                continue

            # Starte neuen Loop
            loop = []
            current_v = start_edge[0]
            prev_v = None

            max_iter = len(edges) + 10
            iterations = 0

            while iterations < max_iter:
                iterations += 1

                # Finde nächste Kante
                found = False
                for next_v, ek0, ek1 in adj.get(current_v, []):
                    edge_key = (ek0, ek1)
                    if edge_key in used_edges:
                        continue
                    if next_v == prev_v:
                        continue

                    # Kante gefunden
                    loop.append((current_v, next_v, ek0, ek1))
                    used_edges.add(edge_key)
                    prev_v = current_v
                    current_v = next_v
                    found = True
                    break

                if not found:
                    break

                # Prüfe ob Loop geschlossen
                if loop and current_v == loop[0][0]:
                    break

            if len(loop) >= 3:
                loops.append(loop)

        return loops

    def _create_wire_from_edge_loop(
        self,
        loop: List[Tuple[int, int, int, int]],
        vertices: List['gp_Pnt'],
        edge_map: Dict[Tuple[int, int], 'TopoDS_Edge']
    ) -> Optional['TopoDS_Wire']:
        """Erstellt Wire aus einem Edge-Loop."""
        try:
            wire_builder = BRepBuilderAPI_MakeWire()

            for v_from, v_to, ek0, ek1 in loop:
                edge_key = (ek0, ek1)

                if edge_key not in edge_map:
                    # Erstelle Edge falls nicht vorhanden
                    p1, p2 = vertices[ek0], vertices[ek1]
                    edge_builder = BRepBuilderAPI_MakeEdge(p1, p2)
                    if not edge_builder.IsDone():
                        continue
                    edge = edge_builder.Edge()
                else:
                    edge = edge_map[edge_key]

                # Orientierung prüfen
                if v_from == ek0:
                    wire_builder.Add(edge)
                else:
                    wire_builder.Add(TopoDS.Edge_s(edge.Reversed()))

            if wire_builder.IsDone():
                return wire_builder.Wire()
            return None

        except Exception as e:
            logger.debug(f"Wire-Erstellung fehlgeschlagen: {e}")
            return None

    def _create_cylinder_face(self, cyl: dict) -> Optional[TopoDS_Face]:
        """
        Erstellt BREP Face für erkannten Zylinder (ohne Mesh-Boundary).
        Fallback wenn Boundary-Methode nicht funktioniert.
        """
        try:
            center = cyl['center']
            axis = cyl['axis']
            radius = cyl['radius']
            v_min = cyl['v_min']
            v_max = cyl['v_max']

            gp_center = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))
            gp_axis = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))

            if abs(axis[2]) < 0.9:
                x_dir = np.cross(axis, [0, 0, 1])
            else:
                x_dir = np.cross(axis, [1, 0, 0])
            x_dir = x_dir / (np.linalg.norm(x_dir) + 1e-10)
            gp_x_dir = gp_Dir(float(x_dir[0]), float(x_dir[1]), float(x_dir[2]))

            ax3 = gp_Ax3(gp_center, gp_axis, gp_x_dir)
            cyl_surface = Geom_CylindricalSurface(ax3, radius)

            u_min, u_max = 0.0, 2 * np.pi

            face_builder = BRepBuilderAPI_MakeFace(
                cyl_surface,
                u_min, u_max,
                v_min, v_max,
                1e-6
            )

            if face_builder.IsDone():
                return face_builder.Face()
            return None

        except Exception as e:
            logger.warning(f"Zylinder-Face Fehler: {e}")
            return None

    def _build_adjacency(self, mesh: 'pv.PolyData') -> Dict[int, List[int]]:
        """Baut Cell-Adjacency-Map."""
        adjacency: Dict[int, List[int]] = {}
        edge_to_cells: Dict[Tuple[int, int], List[int]] = {}

        faces = mesh.faces.reshape(-1, 4)[:, 1:4]

        for cell_id, face in enumerate(faces):
            for i in range(3):
                v1, v2 = int(face[i]), int(face[(i + 1) % 3])
                edge_key = (min(v1, v2), max(v1, v2))

                if edge_key not in edge_to_cells:
                    edge_to_cells[edge_key] = []
                edge_to_cells[edge_key].append(cell_id)

        for cells in edge_to_cells.values():
            if len(cells) == 2:
                c1, c2 = cells
                if c1 not in adjacency:
                    adjacency[c1] = []
                if c2 not in adjacency:
                    adjacency[c2] = []
                adjacency[c1].append(c2)
                adjacency[c2].append(c1)

        return adjacency

    def _create_vertex_pool(self, mesh: 'pv.PolyData') -> List['gp_Pnt']:
        """Erstellt Liste von gp_Pnt aus Mesh-Vertices."""
        return [gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2]))
                for pt in mesh.points]

    def _create_edge_map(
        self,
        mesh: 'pv.PolyData',
        vertices: List['gp_Pnt']
    ) -> Dict[Tuple[int, int], 'TopoDS_Edge']:
        """Erstellt globale Edge-Map mit Sharing."""
        edge_map: Dict[Tuple[int, int], TopoDS_Edge] = {}
        faces_array = mesh.faces.reshape(-1, 4)[:, 1:4]

        for face in faces_array:
            for i in range(3):
                v1, v2 = int(face[i]), int(face[(i + 1) % 3])
                edge_key = (min(v1, v2), max(v1, v2))

                if edge_key not in edge_map:
                    p1, p2 = vertices[edge_key[0]], vertices[edge_key[1]]
                    dist = p1.Distance(p2)
                    if dist > 1e-9:
                        edge_builder = BRepBuilderAPI_MakeEdge(p1, p2)
                        if edge_builder.IsDone():
                            edge_map[edge_key] = edge_builder.Edge()

        return edge_map

    def _create_planar_faces(
        self,
        mesh: 'pv.PolyData',
        vertices: List['gp_Pnt'],
        edge_map: Dict[Tuple[int, int], 'TopoDS_Edge'],
        exclude_cells: Set[int]
    ) -> List['TopoDS_Face']:
        """
        Erstellt planare BREP Faces für alle Dreiecke außer den ausgeschlossenen.
        """
        faces = []
        faces_array = mesh.faces.reshape(-1, 4)[:, 1:4]
        normals = mesh.cell_data['Normals']

        for cell_id, tri in enumerate(faces_array):
            if cell_id in exclude_cells:
                continue  # Dieser Cell gehört zu einem Zylinder

            v0, v1, v2 = int(tri[0]), int(tri[1]), int(tri[2])
            normal = normals[cell_id]

            face = self._create_single_triangle_face(
                v0, v1, v2, vertices, edge_map, normal
            )

            if face is not None:
                faces.append(face)

        return faces

    def _create_single_triangle_face(
        self,
        v0: int, v1: int, v2: int,
        vertices: List['gp_Pnt'],
        edge_map: Dict[Tuple[int, int], 'TopoDS_Edge'],
        normal: np.ndarray
    ) -> Optional['TopoDS_Face']:
        """Erstellt einzelnes dreieckiges BREP Face."""
        try:
            edges = []
            vertex_sequence = [(v0, v1), (v1, v2), (v2, v0)]

            for v_from, v_to in vertex_sequence:
                edge_key = (min(v_from, v_to), max(v_from, v_to))

                if edge_key not in edge_map:
                    return None

                edge = edge_map[edge_key]

                if v_from == edge_key[0]:
                    edges.append(edge)
                else:
                    edges.append(TopoDS.Edge_s(edge.Reversed()))

            wire_builder = BRepBuilderAPI_MakeWire()
            for edge in edges:
                wire_builder.Add(edge)

            if not wire_builder.IsDone():
                return None

            wire = wire_builder.Wire()

            p0, p1, p2 = vertices[v0], vertices[v1], vertices[v2]
            cx = (p0.X() + p1.X() + p2.X()) / 3.0
            cy = (p0.Y() + p1.Y() + p2.Y()) / 3.0
            cz = (p0.Z() + p1.Z() + p2.Z()) / 3.0
            origin = gp_Pnt(cx, cy, cz)

            norm_len = np.linalg.norm(normal)
            if norm_len < 1e-10:
                vec1 = np.array([p1.X() - p0.X(), p1.Y() - p0.Y(), p1.Z() - p0.Z()])
                vec2 = np.array([p2.X() - p0.X(), p2.Y() - p0.Y(), p2.Z() - p0.Z()])
                normal = np.cross(vec1, vec2)
                norm_len = np.linalg.norm(normal)
                if norm_len < 1e-10:
                    return None

            normal = normal / norm_len
            direction = gp_Dir(float(normal[0]), float(normal[1]), float(normal[2]))
            plane = gp_Pln(origin, direction)

            face_builder = BRepBuilderAPI_MakeFace(plane, wire)
            if face_builder.IsDone():
                return face_builder.Face()
            return None

        except Exception:
            return None

    def _sew_and_make_solid(
        self,
        faces: List['TopoDS_Face'],
        stats: dict
    ) -> ConversionResult:
        """Näht Faces zusammen und erstellt Solid."""
        from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Face

        sewer = BRepBuilderAPI_Sewing(self.sewing_tol)
        sewer.SetNonManifoldMode(False)

        for face in faces:
            if face and not face.IsNull():
                sewer.Add(face)

        sewer.Perform()

        free_edges = sewer.NbFreeEdges()
        stats['free_edges'] = free_edges

        logger.debug(f"  Sewing: {free_edges} free edges")

        sewed_shape = sewer.SewedShape()

        if sewed_shape.IsNull():
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message="Sewing fehlgeschlagen",
                stats=stats
            )

        # Repariere das Shape vor der Solid-Erstellung
        shape_fixer = ShapeFix_Shape(sewed_shape)
        shape_fixer.SetPrecision(self.sewing_tol)
        shape_fixer.Perform()
        fixed_shape = shape_fixer.Shape()

        if fixed_shape.IsNull():
            fixed_shape = sewed_shape

        # Shell zu Solid
        try:
            shape_type = fixed_shape.ShapeType()

            if shape_type.name == 'TopAbs_SHELL':
                shell = TopoDS.Shell_s(fixed_shape)
            elif shape_type.name == 'TopAbs_SOLID':
                # Schon ein Solid
                solid = TopoDS.Solid_s(fixed_shape)
                stats['is_valid'] = True

                # UnifySameDomain
                unified_solid = self._unify_faces(solid)
                if unified_solid is not None:
                    solid = unified_solid
                    n_faces = self._count_faces(solid)
                    stats['faces_after_unify'] = n_faces
                    logger.info(f"  Face-Merging: → {n_faces} Faces")

                logger.success("Solid erfolgreich erstellt")
                return ConversionResult(
                    status=ConversionStatus.SUCCESS,
                    solid=solid,
                    stats=stats
                )
            elif shape_type.name == 'TopAbs_COMPOUND':
                from OCP.TopAbs import TopAbs_SHELL
                exp = TopExp_Explorer(fixed_shape, TopAbs_SHELL)
                if exp.More():
                    shell = TopoDS.Shell_s(exp.Current())
                else:
                    return ConversionResult(
                        status=ConversionStatus.PARTIAL,
                        message="Kein Shell in Compound",
                        stats=stats
                    )
            else:
                return ConversionResult(
                    status=ConversionStatus.PARTIAL,
                    message=f"Unerwarteter Shape-Typ: {shape_type}",
                    stats=stats
                )

            # Shell reparieren und orientieren
            shell_fixer = ShapeFix_Shell(shell)
            shell_fixer.SetPrecision(self.sewing_tol)
            shell_fixer.FixFaceOrientation(shell)  # Orientierung reparieren
            shell_fixer.Perform()
            fixed_shell = shell_fixer.Shell()

            # Solid erstellen
            solid_builder = BRepBuilderAPI_MakeSolid(fixed_shell)

            if solid_builder.IsDone():
                solid = solid_builder.Solid()

                # Solid reparieren
                solid_fixer = ShapeFix_Solid(solid)
                solid_fixer.SetPrecision(self.sewing_tol)
                solid_fixer.Perform()
                fixed_solid = solid_fixer.Solid()

                if not fixed_solid.IsNull():
                    solid = fixed_solid

                analyzer = BRepCheck_Analyzer(solid)
                is_valid = analyzer.IsValid()
                stats['is_valid'] = is_valid

                if is_valid:
                    # UnifySameDomain für planare Faces
                    unified_solid = self._unify_faces(solid)
                    if unified_solid is not None:
                        solid = unified_solid
                        n_faces = self._count_faces(solid)
                        stats['faces_after_unify'] = n_faces
                        logger.info(f"  Face-Merging: → {n_faces} Faces")

                    logger.success("Solid erfolgreich erstellt")
                    return ConversionResult(
                        status=ConversionStatus.SUCCESS,
                        solid=solid,
                        stats=stats
                    )
                else:
                    # Trotzdem weitermachen - oft funktioniert das Solid trotz Warnung
                    unified_solid = self._unify_faces(solid)
                    if unified_solid is not None:
                        solid = unified_solid
                        n_faces = self._count_faces(solid)
                        stats['faces_after_unify'] = n_faces

                        # Nochmal prüfen
                        analyzer2 = BRepCheck_Analyzer(solid)
                        if analyzer2.IsValid():
                            stats['is_valid'] = True
                            logger.success("Solid nach UnifySameDomain valide")
                            return ConversionResult(
                                status=ConversionStatus.SUCCESS,
                                solid=solid,
                                stats=stats
                            )

                    logger.warning("Solid erstellt aber nicht valide - wird trotzdem zurückgegeben")
                    return ConversionResult(
                        status=ConversionStatus.PARTIAL,
                        solid=solid,
                        message="Validierung fehlgeschlagen",
                        stats=stats
                    )
            else:
                return ConversionResult(
                    status=ConversionStatus.SHELL_ONLY,
                    message="MakeSolid fehlgeschlagen",
                    stats=stats
                )

        except Exception as e:
            logger.error(f"Solid-Erstellung Fehler: {e}")
            import traceback
            traceback.print_exc()
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message=f"Solid-Erstellung: {e}",
                stats=stats
            )

    def _unify_faces(self, solid) -> Optional['TopoDS_Solid']:
        """Vereinigt koplanare Faces."""
        try:
            upgrader = ShapeUpgrade_UnifySameDomain(solid, True, True, True)
            upgrader.SetLinearTolerance(self.unify_linear_tol)
            upgrader.SetAngularTolerance(self.unify_angular_tol)
            upgrader.Build()

            unified = upgrader.Shape()

            if unified.IsNull():
                return None

            from OCP.TopAbs import TopAbs_SOLID
            if unified.ShapeType() == TopAbs_SOLID:
                return TopoDS.Solid_s(unified)
            return None

        except Exception as e:
            logger.warning(f"UnifySameDomain fehlgeschlagen: {e}")
            return None

    def _count_faces(self, shape) -> int:
        """Zählt Faces in einem Shape."""
        count = 0
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            count += 1
            exp.Next()
        return count


def convert_hybrid_mesh(filepath: str, **kwargs) -> ConversionResult:
    """
    Convenience-Funktion für Hybrid Mesh Konvertierung.
    """
    from meshconverter.mesh_converter_v10 import MeshLoader, LoadStatus

    load_result = MeshLoader.load(filepath, repair=True)
    if load_result.status == LoadStatus.FAILED:
        return ConversionResult(
            status=ConversionStatus.FAILED,
            message=f"Laden fehlgeschlagen: {load_result.message}"
        )

    converter = HybridMeshConverter(**kwargs)
    return converter.convert(load_result.mesh)
