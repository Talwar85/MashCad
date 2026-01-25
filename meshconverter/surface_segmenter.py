"""
MashCad - Surface Segmenter
===========================

Segmentiert Mesh in homogene Regionen basierend auf Normalen-Ähnlichkeit.
Verwendet hierarchisches Clustering und Connected Components.
"""

import numpy as np
from typing import List, Optional, Dict, Set
from loguru import logger

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

try:
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial import ConvexHull
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    logger.warning("scipy nicht verfügbar - Clustering eingeschränkt")

from meshconverter.mesh_converter_v10 import Region


class SurfaceSegmenter:
    """
    Segmentiert Mesh in homogene Regionen.

    Algorithmus:
    1. Normalen-basiertes Clustering (hierarchisch)
    2. Connected Components pro Cluster
    3. Boundary-Extraktion pro Region
    """

    def __init__(
        self,
        angle_tolerance: float = 5.0,   # Grad
        min_region_faces: int = 1,      # Minimum Faces pro Region (1 für kleine Meshes)
        max_regions: int = 1000         # Maximum Regionen (Performance)
    ):
        """
        Args:
            angle_tolerance: Maximale Winkelabweichung für gleiche Region (Grad)
            min_region_faces: Minimum Faces um als Region zu gelten
            max_regions: Maximum Regionen (verhindert Over-Segmentierung)
        """
        self.angle_tol = np.radians(angle_tolerance)
        self.min_faces = min_region_faces
        self.max_regions = max_regions

    def segment(self, mesh: 'pv.PolyData', merge_coplanar: bool = True) -> List[Region]:
        """
        Segmentiert Mesh in Regionen.

        Args:
            mesh: PyVista PolyData mit Normalen
            merge_coplanar: Koplanare adjazente Regionen mergen

        Returns:
            Liste von Region-Objekten
        """
        if not HAS_PYVISTA:
            logger.error("PyVista nicht verfügbar")
            return []

        # Normalen sicherstellen
        if 'Normals' not in mesh.cell_data:
            mesh.compute_normals(cell_normals=True, point_normals=False, inplace=True)

        normals = mesh.cell_data['Normals']
        n_cells = mesh.n_cells

        logger.debug(f"Segmentiere {n_cells} Faces...")

        # Normalen normalisieren
        norms = np.linalg.norm(normals, axis=1, keepdims=True)
        norms[norms < 1e-10] = 1.0
        normals_normalized = normals / norms

        # Clustering
        if HAS_SCIPY and n_cells >= 10:
            labels = self._cluster_hierarchical(normals_normalized)
        else:
            labels = self._cluster_simple(normals_normalized)

        # Connected Components pro Label
        regions = self._extract_regions(mesh, normals_normalized, labels)

        # Region-Merging: Koplanare adjazente Regionen zusammenfassen
        if merge_coplanar and len(regions) > 6:
            regions = self._merge_coplanar_regions(mesh, regions, normals_normalized)

        # Nach Fläche sortieren (größte zuerst)
        regions.sort(key=lambda r: r.area, reverse=True)

        # Limit auf max_regions
        if len(regions) > self.max_regions:
            logger.warning(f"Zu viele Regionen ({len(regions)}), limitiere auf {self.max_regions}")
            regions = regions[:self.max_regions]

        logger.debug(f"  → {len(regions)} Regionen nach Segmentierung")
        return regions

    def _merge_coplanar_regions(
        self,
        mesh: 'pv.PolyData',
        regions: List[Region],
        normals: np.ndarray
    ) -> List[Region]:
        """
        Merged koplanare adjazente Regionen.

        Strategie:
        1. Baue Region-Adjazenz-Graph
        2. Finde Paare mit ähnlicher Normal (< angle_tol)
        3. Union-Find für Merging
        4. Rekonstruiere Regionen
        """
        if len(regions) <= 1:
            return regions

        logger.debug(f"  Region-Merging: {len(regions)} Regionen...")

        # Adjazenz-Map: cell_id -> region_idx
        cell_to_region = {}
        for idx, region in enumerate(regions):
            for cell_id in region.cell_ids:
                cell_to_region[cell_id] = idx

        # Cell-Adjazenz
        cell_adjacency = self._build_adjacency(mesh)

        # Region-Adjazenz finden
        region_adjacency: Dict[int, Set[int]] = {i: set() for i in range(len(regions))}

        for cell_id, region_idx in cell_to_region.items():
            for neighbor_cell in cell_adjacency.get(cell_id, []):
                neighbor_region = cell_to_region.get(neighbor_cell)
                if neighbor_region is not None and neighbor_region != region_idx:
                    region_adjacency[region_idx].add(neighbor_region)
                    region_adjacency[neighbor_region].add(region_idx)

        # Union-Find für Merging
        parent = list(range(len(regions)))

        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Merge koplanare adjazente Regionen
        # WICHTIG: Nicht nur gleiche Normale, sondern auch GLEICHE EBENE!
        # UND: Nur für planare Regionen (keine gekrümmten Flächen)
        cos_threshold = np.cos(self.angle_tol)  # Strenger: nur bei fast exakt gleicher Normale
        plane_dist_threshold = 0.1  # mm - Sehr streng: nur Flächen auf gleicher Ebene

        # Prüfe ob Region planar ist (alle Normalen ähnlich)
        def is_region_planar(region_idx):
            cell_ids = regions[region_idx].cell_ids
            region_normals = normals[cell_ids]
            # Varianz der Normalen - bei planaren Flächen sehr klein
            normal_variance = np.var(region_normals, axis=0).sum()
            return normal_variance < 0.01  # Sehr niedrige Varianz = planar

        # Berechne Ebenen-Distanz (d in n·p = d) für jede Region
        region_plane_d = []
        region_is_planar = []
        for idx, r in enumerate(regions):
            # d = n · centroid
            d = np.dot(r.normal, r.centroid)
            region_plane_d.append(d)
            region_is_planar.append(is_region_planar(idx))

        merge_count = 0
        for r1_idx in range(len(regions)):
            n1 = regions[r1_idx].normal
            d1 = region_plane_d[r1_idx]

            for r2_idx in region_adjacency[r1_idx]:
                if r2_idx <= r1_idx:
                    continue  # Nur einmal pro Paar

                n2 = regions[r2_idx].normal
                d2 = region_plane_d[r2_idx]

                # Nur mergen wenn BEIDE Regionen planar sind
                if not (region_is_planar[r1_idx] and region_is_planar[r2_idx]):
                    continue

                # Koplanar wenn:
                # 1. Normalen parallel (gleich oder entgegengesetzt)
                cos_angle = abs(np.dot(n1, n2))

                # 2. Auf gleicher Ebene (gleiche Distanz zum Ursprung)
                if cos_angle >= cos_threshold:
                    # Prüfe ob auf gleicher Ebene
                    # Wenn Normalen gleich: d1 ≈ d2
                    # Wenn Normalen entgegengesetzt: d1 ≈ -d2
                    same_direction = np.dot(n1, n2) > 0
                    if same_direction:
                        plane_diff = abs(d1 - d2)
                    else:
                        plane_diff = abs(d1 + d2)

                    if plane_diff < plane_dist_threshold:
                        union(r1_idx, r2_idx)
                        merge_count += 1

        if merge_count == 0:
            logger.debug("    Keine koplanaren Regionen zum Mergen gefunden")
            return regions

        logger.debug(f"    {merge_count} Region-Paare gemerged")

        # Gruppiere nach Union-Find Root
        groups: Dict[int, List[int]] = {}
        for i in range(len(regions)):
            root = find(i)
            if root not in groups:
                groups[root] = []
            groups[root].append(i)

        # Neue Regionen erstellen
        merged_regions = []
        new_region_id = 0

        for root, region_indices in groups.items():
            # Sammle alle Cell-IDs
            all_cell_ids = []
            total_area = 0
            weighted_normal = np.zeros(3)

            for r_idx in region_indices:
                r = regions[r_idx]
                all_cell_ids.extend(r.cell_ids.tolist())
                total_area += r.area
                weighted_normal += r.normal * r.area

            all_cell_ids = np.array(all_cell_ids)

            # Durchschnittliche Normal (gewichtet nach Fläche)
            avg_normal = weighted_normal / (np.linalg.norm(weighted_normal) + 1e-10)

            # Neues Mesh für Region
            region_mesh = mesh.extract_cells(all_cell_ids)
            centroid = np.mean(region_mesh.points, axis=0)

            # Boundary neu extrahieren und auf Original-Mesh-Vertices snappen
            boundary_points = self._extract_boundary(region_mesh, avg_normal)
            if boundary_points is not None:
                boundary_points = self._snap_to_mesh_vertices(boundary_points, mesh.points)

            merged_regions.append(Region(
                region_id=new_region_id,
                cell_ids=all_cell_ids,
                normal=avg_normal,
                centroid=centroid,
                area=total_area,
                boundary_points=boundary_points
            ))
            new_region_id += 1

        logger.debug(f"    → {len(merged_regions)} Regionen nach Merging")
        return merged_regions

    def _cluster_hierarchical(self, normals: np.ndarray) -> np.ndarray:
        """
        Hierarchisches Clustering basierend auf Normalen-Ähnlichkeit.

        Returns:
            Cluster-Labels für jede Cell
        """
        n_cells = len(normals)

        # Sampling für große Meshes (Performance)
        if n_cells > 10000:
            sample_size = 5000
            sample_idx = np.random.choice(n_cells, sample_size, replace=False)
            sample_normals = normals[sample_idx]
        else:
            sample_idx = np.arange(n_cells)
            sample_normals = normals

        try:
            # Hierarchisches Clustering mit Cosinus-Distanz
            # Cosinus-Distanz = 1 - cos(angle) (für Normalen die 180° verschieden sein können)
            Z = linkage(sample_normals, method='average', metric='cosine')

            # Threshold: Bei angle_tol = 5°, cos(5°) ≈ 0.996, dist ≈ 0.004
            # Aber wir müssen bedenken: Cosine distance = 1 - cos(angle)
            # Für angle=5°: dist ≈ 0.004
            # Für angle=90°: dist = 1.0 (orthogonale Normalen)
            threshold = 1 - np.cos(self.angle_tol)
            labels = fcluster(Z, threshold, criterion='distance')

            n_clusters = len(np.unique(labels))
            logger.debug(f"  Hierarchisches Clustering: {n_clusters} Cluster gefunden")

        except Exception as e:
            logger.warning(f"Hierarchisches Clustering fehlgeschlagen: {e}")
            return self._cluster_simple(normals)

        # Labels auf alle Cells übertragen (wenn gesampelt)
        if len(sample_idx) < n_cells:
            all_labels = self._propagate_labels(normals, sample_idx, sample_normals, labels)
        else:
            all_labels = labels

        return all_labels

    def _propagate_labels(
        self,
        all_normals: np.ndarray,
        sample_idx: np.ndarray,
        sample_normals: np.ndarray,
        sample_labels: np.ndarray
    ) -> np.ndarray:
        """
        Propagiert Labels von Samples auf alle Cells.
        """
        n_cells = len(all_normals)
        all_labels = np.zeros(n_cells, dtype=int)

        # Sample-Labels setzen
        all_labels[sample_idx] = sample_labels

        # Cluster-Zentren berechnen
        cluster_centers = {}
        for label in np.unique(sample_labels):
            mask = sample_labels == label
            cluster_centers[label] = np.mean(sample_normals[mask], axis=0)

        # Nicht-Sample-Cells dem nächsten Cluster zuordnen
        non_sample_mask = np.ones(n_cells, dtype=bool)
        non_sample_mask[sample_idx] = False
        non_sample_idx = np.where(non_sample_mask)[0]

        for idx in non_sample_idx:
            normal = all_normals[idx]
            best_label = 1
            best_similarity = -1

            for label, center in cluster_centers.items():
                # Cosinus-Ähnlichkeit (absolute, da Normalen-Richtung egal)
                similarity = abs(np.dot(normal, center))
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_label = label

            all_labels[idx] = best_label

        return all_labels

    def _cluster_simple(self, normals: np.ndarray) -> np.ndarray:
        """
        Einfaches Grid-basiertes Clustering (Fallback ohne scipy).

        Diskretisiert Normalen auf Einheitskugel-Grid.
        """
        n_cells = len(normals)
        grid_size = 20  # 20x20 Grid auf Hemisphäre

        labels = np.zeros(n_cells, dtype=int)
        label_map = {}
        next_label = 1

        for i, n in enumerate(normals):
            # Normalisieren
            n = n / (np.linalg.norm(n) + 1e-10)

            # Zu Kugelkoordinaten
            theta = np.arccos(np.clip(n[2], -1, 1))  # [0, π]
            phi = np.arctan2(n[1], n[0])             # [-π, π]

            # Quantisieren
            theta_bin = int(theta / np.pi * grid_size)
            phi_bin = int((phi + np.pi) / (2 * np.pi) * grid_size)

            key = (theta_bin, phi_bin)

            if key not in label_map:
                label_map[key] = next_label
                next_label += 1

            labels[i] = label_map[key]

        return labels

    def _extract_regions(
        self,
        mesh: 'pv.PolyData',
        normals: np.ndarray,
        labels: np.ndarray
    ) -> List[Region]:
        """
        Extrahiert Region-Objekte aus Cluster-Labels.

        Findet Connected Components pro Label.
        """
        regions = []
        region_id = 0

        # Adjazenz-Liste aufbauen (Cell-zu-Cell Verbindungen)
        adjacency = self._build_adjacency(mesh)

        unique_labels = np.unique(labels)
        logger.debug(f"  Labels: {len(unique_labels)} unique, min={unique_labels.min()}, max={unique_labels.max()}")

        for label in unique_labels:
            if label == 0:
                continue  # Label 0 = unzugeordnet

            cell_ids = np.where(labels == label)[0]
            logger.debug(f"  Label {label}: {len(cell_ids)} cells")

            if len(cell_ids) < self.min_faces:
                logger.debug(f"    → übersprungen (< {self.min_faces} faces)")
                continue

            # Connected Components finden
            components = self._find_connected_components(cell_ids, adjacency)
            logger.debug(f"    → {len(components)} connected components")

            for comp_ids in components:
                if len(comp_ids) < self.min_faces:
                    continue

                comp_ids_array = np.array(list(comp_ids))

                # Region-Properties berechnen
                region_normals = normals[comp_ids_array]
                avg_normal = np.mean(region_normals, axis=0)
                avg_normal = avg_normal / (np.linalg.norm(avg_normal) + 1e-10)

                # Mesh für diese Region
                region_mesh = mesh.extract_cells(comp_ids_array)
                centroid = np.mean(region_mesh.points, axis=0)
                area = region_mesh.area

                # Boundary extrahieren und auf Original-Mesh-Vertices snappen
                boundary_points = self._extract_boundary(region_mesh, avg_normal)
                if boundary_points is not None:
                    boundary_points = self._snap_to_mesh_vertices(boundary_points, mesh.points)

                regions.append(Region(
                    region_id=region_id,
                    cell_ids=comp_ids_array,
                    normal=avg_normal,
                    centroid=centroid,
                    area=area,
                    boundary_points=boundary_points
                ))
                region_id += 1

        return regions

    def _build_adjacency(self, mesh: 'pv.PolyData') -> Dict[int, Set[int]]:
        """
        Baut Adjazenz-Liste für Cells auf.

        Zwei Cells sind adjazent, wenn sie eine gemeinsame Kante haben.
        """
        adjacency: Dict[int, Set[int]] = {i: set() for i in range(mesh.n_cells)}

        # Edge-zu-Cells Mapping
        edge_to_cells: Dict[tuple, List[int]] = {}

        faces = mesh.faces.reshape(-1, 4)[:, 1:4]  # Nur Triangle-Indices

        for cell_id, face in enumerate(faces):
            # Alle 3 Kanten des Dreiecks
            edges = [
                (min(face[0], face[1]), max(face[0], face[1])),
                (min(face[1], face[2]), max(face[1], face[2])),
                (min(face[2], face[0]), max(face[2], face[0])),
            ]

            for edge in edges:
                if edge not in edge_to_cells:
                    edge_to_cells[edge] = []
                edge_to_cells[edge].append(cell_id)

        # Adjazenz aus gemeinsamen Kanten
        for cells in edge_to_cells.values():
            if len(cells) == 2:
                c1, c2 = cells
                adjacency[c1].add(c2)
                adjacency[c2].add(c1)

        return adjacency

    def _find_connected_components(
        self,
        cell_ids: np.ndarray,
        adjacency: Dict[int, Set[int]]
    ) -> List[Set[int]]:
        """
        Findet Connected Components in einer Menge von Cells.
        """
        cell_set = set(cell_ids)
        visited = set()
        components = []

        for start_cell in cell_ids:
            if start_cell in visited:
                continue

            # BFS von start_cell
            component = set()
            queue = [start_cell]

            while queue:
                cell = queue.pop(0)
                if cell in visited:
                    continue
                if cell not in cell_set:
                    continue

                visited.add(cell)
                component.add(cell)

                # Nachbarn hinzufügen
                for neighbor in adjacency.get(cell, []):
                    if neighbor not in visited and neighbor in cell_set:
                        queue.append(neighbor)

            if component:
                components.append(component)

        return components

    def _extract_boundary(
        self,
        region_mesh: 'pv.PolyData',
        normal: np.ndarray
    ) -> Optional[np.ndarray]:
        """
        Extrahiert geordnete Boundary-Punkte einer Region.

        Verwendet die tatsächlichen Mesh-Kanten (boundary edges), nicht ConvexHull.
        """
        try:
            # Boundary Edges extrahieren - das sind die tatsächlichen Außenkanten
            edges = region_mesh.extract_feature_edges(
                boundary_edges=True,
                feature_edges=False,
                manifold_edges=False,
                non_manifold_edges=False
            )

            if edges.n_points < 3:
                # Für sehr kleine Regionen (1-2 Dreiecke):
                # Nimm alle einzigartigen Punkte der Region
                return self._get_unique_boundary_from_faces(region_mesh)

            # Punkte entlang Boundary ordnen
            points = edges.points
            ordered = self._order_boundary_points_by_edges(edges)

            if ordered is not None and len(ordered) >= 3:
                return ordered

            # Fallback auf nearest-neighbor ordering
            return self._order_boundary_points(points)

        except Exception as e:
            logger.debug(f"Boundary-Extraktion fehlgeschlagen: {e}")
            return self._get_unique_boundary_from_faces(region_mesh)

    def _snap_to_mesh_vertices(
        self,
        boundary_points: np.ndarray,
        mesh_vertices: np.ndarray
    ) -> np.ndarray:
        """
        Snappt Boundary-Punkte auf die nächsten Original-Mesh-Vertices.

        Dies stellt sicher, dass benachbarte Regionen exakt dieselben
        Vertex-Koordinaten für geteilte Kanten verwenden.

        Args:
            boundary_points: Zu snappende Boundary-Punkte (N, 3)
            mesh_vertices: Original-Mesh-Vertices (M, 3)

        Returns:
            Gesnappte Boundary-Punkte (N, 3)
        """
        snapped = np.zeros_like(boundary_points)

        for i, pt in enumerate(boundary_points):
            # Finde nächsten Mesh-Vertex
            distances = np.linalg.norm(mesh_vertices - pt, axis=1)
            nearest_idx = np.argmin(distances)
            snapped[i] = mesh_vertices[nearest_idx]

        return snapped

    def _get_unique_boundary_from_faces(self, region_mesh: 'pv.PolyData') -> Optional[np.ndarray]:
        """
        Extrahiert Boundary-Punkte direkt aus den Mesh-Faces.
        Für kleine Regionen (1-2 Dreiecke).
        """
        try:
            if region_mesh.n_cells == 0:
                return None

            # Sammle alle Kanten und zähle wie oft sie vorkommen
            edge_count = {}
            faces = region_mesh.faces.reshape(-1, 4)[:, 1:4]  # Triangle indices

            for face in faces:
                for i in range(3):
                    v1, v2 = face[i], face[(i+1) % 3]
                    edge_key = (min(v1, v2), max(v1, v2))
                    edge_count[edge_key] = edge_count.get(edge_key, 0) + 1

            # Boundary edges sind die, die nur einmal vorkommen
            boundary_edges = [edge for edge, count in edge_count.items() if count == 1]

            if not boundary_edges:
                # Keine Boundary - Region ist geschlossen
                return None

            # Ordne die Boundary-Punkte
            return self._order_edges_to_loop(boundary_edges, region_mesh.points)

        except Exception as e:
            logger.debug(f"Face-basierte Boundary-Extraktion fehlgeschlagen: {e}")
            return None

    def _order_edges_to_loop(self, edges: list, points: np.ndarray) -> Optional[np.ndarray]:
        """
        Ordnet Kanten zu einem geschlossenen Loop.
        """
        if not edges:
            return None

        # Baue Adjazenz-Map
        adjacency = {}
        for v1, v2 in edges:
            if v1 not in adjacency:
                adjacency[v1] = []
            if v2 not in adjacency:
                adjacency[v2] = []
            adjacency[v1].append(v2)
            adjacency[v2].append(v1)

        # Starte beim ersten Vertex
        start = edges[0][0]
        ordered_vertices = [start]
        visited = {start}
        current = start

        while True:
            # Finde nächsten unbesuchten Nachbarn
            next_vertex = None
            for neighbor in adjacency.get(current, []):
                if neighbor not in visited:
                    next_vertex = neighbor
                    break

            if next_vertex is None:
                break

            ordered_vertices.append(next_vertex)
            visited.add(next_vertex)
            current = next_vertex

        if len(ordered_vertices) < 3:
            return None

        return points[ordered_vertices]

    def _order_boundary_points_by_edges(self, edges_mesh: 'pv.PolyData') -> Optional[np.ndarray]:
        """
        Ordnet Boundary-Punkte basierend auf der Edge-Konnektivität.
        """
        try:
            if edges_mesh.n_cells == 0:
                return None

            # Extrahiere Edges als Linien
            lines = edges_mesh.lines
            if lines is None or len(lines) == 0:
                return None

            # Parse line connectivity (Format: [n, p1, p2, n, p3, p4, ...])
            edges = []
            i = 0
            while i < len(lines):
                n = lines[i]
                if n == 2:  # Linie mit 2 Punkten
                    v1, v2 = lines[i+1], lines[i+2]
                    edges.append((v1, v2))
                i += n + 1

            if not edges:
                return None

            return self._order_edges_to_loop(edges, edges_mesh.points)

        except Exception as e:
            logger.debug(f"Edge-basierte Ordering fehlgeschlagen: {e}")
            return None

    def _order_boundary_points(self, points: np.ndarray) -> np.ndarray:
        """
        Ordnet Boundary-Punkte entlang der Kante.

        Verwendet Nearest-Neighbor-Heuristik.
        """
        if len(points) < 3:
            return points

        n = len(points)
        ordered_indices = [0]
        remaining = set(range(1, n))

        while remaining:
            current = ordered_indices[-1]
            current_pt = points[current]

            # Nächsten Punkt finden
            min_dist = float('inf')
            nearest = None

            for idx in remaining:
                dist = np.linalg.norm(points[idx] - current_pt)
                if dist < min_dist:
                    min_dist = dist
                    nearest = idx

            if nearest is not None:
                ordered_indices.append(nearest)
                remaining.remove(nearest)
            else:
                break

        return points[ordered_indices]

    def _boundary_via_convex_hull(
        self,
        points: np.ndarray,
        normal: np.ndarray
    ) -> Optional[np.ndarray]:
        """
        Fallback: 2D ConvexHull in der Ebene als Boundary.
        """
        if not HAS_SCIPY or len(points) < 3:
            return None

        try:
            # Lokales Koordinatensystem auf Ebene
            n = normal / (np.linalg.norm(normal) + 1e-10)

            if abs(n[2]) < 0.9:
                u = np.cross(n, [0, 0, 1])
            else:
                u = np.cross(n, [1, 0, 0])
            u = u / (np.linalg.norm(u) + 1e-10)
            v = np.cross(n, u)

            # Projizieren
            centroid = np.mean(points, axis=0)
            local_pts = points - centroid
            pts_2d = np.column_stack([
                np.dot(local_pts, u),
                np.dot(local_pts, v)
            ])

            # ConvexHull
            hull = ConvexHull(pts_2d)
            hull_points_3d = points[hull.vertices]

            return hull_points_3d

        except Exception as e:
            logger.debug(f"ConvexHull fehlgeschlagen: {e}")
            return None
