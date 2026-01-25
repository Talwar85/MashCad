"""
Mesh-basierte Primitiv-Erkennung ohne vorherige Curvature-Klassifizierung.

Ansatz:
1. Segmentiere Mesh in Regionen basierend auf Normalen-Ähnlichkeit
2. Für jede Region: Teste verschiedene Primitiv-Typen
3. Wähle bestes Fit mit niedrigstem Fehler

Dieser Ansatz ist robuster als Curvature-basierte Klassifizierung,
da er direkt auf der Geometrie arbeitet.
"""

import numpy as np
from typing import List, Tuple, Optional, Dict, Set
from dataclasses import dataclass
from loguru import logger
from collections import deque
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial import ConvexHull

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False


@dataclass
class CylinderFit:
    """Erkannter Zylinder."""
    face_indices: List[int]
    center: np.ndarray
    axis: np.ndarray
    radius: float
    height: float
    error: float
    confidence: float


@dataclass
class SphereFit:
    """Erkannte Kugel."""
    face_indices: List[int]
    center: np.ndarray
    radius: float
    error: float
    confidence: float


@dataclass
class PlaneFit:
    """Erkannte Ebene."""
    face_indices: List[int]
    origin: np.ndarray
    normal: np.ndarray
    error: float


class MeshPrimitiveDetector:
    """
    Erkennt Primitive direkt aus Mesh-Geometrie.

    Unterschied zum CurvatureDetector:
    - Keine Vorselektion durch Krümmungsberechnung
    - Arbeitet direkt mit Region Growing auf dem Mesh
    - Testet alle Primitiv-Typen pro Region
    """

    def __init__(
        self,
        angle_threshold: float = 15.0,      # Grad für Normalen-Clustering
        min_region_faces: int = 12,          # Min Faces pro Region
        cylinder_tolerance: float = 0.5,     # mm für Zylinder-Fit
        sphere_tolerance: float = 0.5,       # mm für Kugel-Fit
        min_inlier_ratio: float = 0.85       # Min 85% Punkte müssen passen
    ):
        self.angle_thresh = np.radians(angle_threshold)
        self.min_faces = min_region_faces
        self.cyl_tol = cylinder_tolerance
        self.sphere_tol = sphere_tolerance
        self.min_inlier = min_inlier_ratio

    def detect_from_mesh(
        self,
        mesh: 'pv.PolyData'
    ) -> Tuple[List[CylinderFit], List[SphereFit]]:
        """
        Erkennt Zylinder und Kugeln aus PyVista Mesh.

        Returns:
            Tuple von (Zylinder-Liste, Kugel-Liste)
        """
        if not HAS_PYVISTA:
            return [], []

        cylinders = []
        spheres = []

        # 1. Berechne Face-Normalen und Zentroids
        logger.info("Berechne Face-Normalen...")
        mesh.compute_normals(cell_normals=True, point_normals=False, inplace=True)

        faces = mesh.faces.reshape(-1, 4)[:, 1:4]
        n_faces = len(faces)
        points = mesh.points

        face_normals = mesh.cell_data['Normals']
        face_centers = np.zeros((n_faces, 3))

        for i, face in enumerate(faces):
            face_centers[i] = points[face].mean(axis=0)

        # 2. Baue Face-Adjacency
        logger.info("Baue Adjacency-Graph...")
        adjacency = self._build_adjacency(faces, n_faces)

        # 3. Region Growing basierend auf Normalen-Kontinuität
        logger.info("Segmentiere in Regionen...")
        regions = self._segment_by_normals(
            faces, face_normals, face_centers, adjacency
        )
        logger.info(f"  {len(regions)} Regionen gefunden")

        # Statistik
        region_sizes = [len(r) for r in regions]
        if region_sizes:
            logger.info(f"  Größen: Min={min(region_sizes)}, Max={max(region_sizes)}, "
                       f"Median={np.median(region_sizes):.0f}")

        # 4. Für jede Region: Finde bestes Primitiv
        logger.info("Fitte Primitive auf Regionen...")

        for region_faces in regions:
            if len(region_faces) < self.min_faces:
                continue

            # Sammle Punkte der Region
            vertex_set = set()
            for f_idx in region_faces:
                for v in faces[f_idx]:
                    vertex_set.add(v)

            region_points = points[list(vertex_set)]
            region_normals = face_normals[region_faces]

            if len(region_points) < 10:
                continue

            # Teste Primitiv-Typen
            best_fit = None
            best_type = None
            best_error = float('inf')

            # Teste Zylinder
            cyl = self._fit_cylinder(region_points, region_normals)
            if cyl is not None and cyl['error'] < best_error:
                best_fit = cyl
                best_type = 'cylinder'
                best_error = cyl['error']

            # Teste Kugel
            sphere = self._fit_sphere(region_points)
            if sphere is not None and sphere['error'] < best_error:
                best_fit = sphere
                best_type = 'sphere'
                best_error = sphere['error']

            # Erstelle Ergebnis
            if best_fit is not None:
                if best_type == 'cylinder':
                    # Zusätzliche Validierung für Zylinder
                    if best_fit['inlier_ratio'] >= self.min_inlier:
                        cyl_fit = CylinderFit(
                            face_indices=region_faces,
                            center=best_fit['center'],
                            axis=best_fit['axis'],
                            radius=best_fit['radius'],
                            height=best_fit['height'],
                            error=best_fit['error'],
                            confidence=best_fit['inlier_ratio']
                        )
                        cylinders.append(cyl_fit)
                        logger.info(f"    Zylinder: R={cyl_fit.radius:.2f}mm, "
                                   f"H={cyl_fit.height:.2f}mm, {len(region_faces)} Faces")

                elif best_type == 'sphere':
                    if best_fit['inlier_ratio'] >= self.min_inlier:
                        sphere_fit = SphereFit(
                            face_indices=region_faces,
                            center=best_fit['center'],
                            radius=best_fit['radius'],
                            error=best_fit['error'],
                            confidence=best_fit['inlier_ratio']
                        )
                        spheres.append(sphere_fit)
                        logger.info(f"    Kugel: R={sphere_fit.radius:.2f}mm, "
                                   f"{len(region_faces)} Faces")

        logger.info(f"Gefunden: {len(cylinders)} Zylinder, {len(spheres)} Kugeln")
        return cylinders, spheres

    def _build_adjacency(self, faces: np.ndarray, n_faces: int) -> Dict[int, Set[int]]:
        """Baut Face-Adjacency-Graph basierend auf gemeinsamen Edges."""
        edge_to_faces = {}

        for f_idx, face in enumerate(faces):
            for i in range(3):
                edge = tuple(sorted([face[i], face[(i+1) % 3]]))
                if edge not in edge_to_faces:
                    edge_to_faces[edge] = []
                edge_to_faces[edge].append(f_idx)

        adjacency = {i: set() for i in range(n_faces)}
        for edge, adj_faces in edge_to_faces.items():
            if len(adj_faces) == 2:
                f1, f2 = adj_faces
                adjacency[f1].add(f2)
                adjacency[f2].add(f1)

        return adjacency

    def _segment_by_normals(
        self,
        faces: np.ndarray,
        normals: np.ndarray,
        centers: np.ndarray,
        adjacency: Dict[int, Set[int]]
    ) -> List[List[int]]:
        """
        Segmentiert Mesh in Regionen basierend auf Normalen-Kontinuität.

        Verwendet Region Growing mit adaptivem Schwellwert:
        - Für Ebenen: Strikte Normalen-Übereinstimmung
        - Für gekrümmte Flächen: Erlaubt graduelle Änderung
        """
        n_faces = len(faces)
        visited = np.zeros(n_faces, dtype=bool)
        regions = []

        # Sortiere Faces nach "Flachheit" (Variation mit Nachbarn)
        # Starte bei den flachsten Regionen
        flatness_scores = []
        for i in range(n_faces):
            if len(adjacency[i]) == 0:
                flatness_scores.append((i, 0.0))
                continue

            neighbor_normals = normals[list(adjacency[i])]
            dots = np.dot(neighbor_normals, normals[i])
            # Höherer Score = flacher (mehr ähnliche Nachbarn)
            flatness_scores.append((i, np.mean(dots)))

        # Sortiere absteigend (flachste zuerst)
        flatness_scores.sort(key=lambda x: -x[1])

        for seed, _ in flatness_scores:
            if visited[seed]:
                continue

            # Region Growing mit adaptivem Threshold
            region = self._grow_region(
                seed, normals, centers, adjacency, visited
            )

            if len(region) >= 3:  # Min 3 Faces
                regions.append(region)

        return regions

    def _grow_region(
        self,
        seed: int,
        normals: np.ndarray,
        centers: np.ndarray,
        adjacency: Dict[int, Set[int]],
        visited: np.ndarray
    ) -> List[int]:
        """Wächst Region von Seed-Face."""
        region = [seed]
        visited[seed] = True

        queue = deque(adjacency[seed])
        region_normal = normals[seed].copy()

        # Dynamischer Threshold basierend auf lokaler Krümmung
        local_threshold = self.angle_thresh

        while queue:
            candidate = queue.popleft()

            if visited[candidate]:
                continue

            # Prüfe Normalen-Ähnlichkeit
            dot = np.dot(normals[candidate], region_normal)
            angle = np.arccos(np.clip(dot, -1, 1))

            # Für gekrümmte Flächen: Erlaube graduelle Änderung
            # Prüfe auch Ähnlichkeit zum nächsten Nachbarn in der Region
            neighbor_in_region = [n for n in adjacency[candidate] if n in region]

            if neighbor_in_region:
                # Direkter Nachbar-Check (strenger)
                neighbor_dots = [np.dot(normals[candidate], normals[n])
                                for n in neighbor_in_region]
                max_neighbor_dot = max(neighbor_dots)
                neighbor_angle = np.arccos(np.clip(max_neighbor_dot, -1, 1))

                # Akzeptiere wenn Nachbar-Winkel klein ist (graduelle Krümmung)
                if neighbor_angle < self.angle_thresh * 0.7:  # Strenger als global
                    visited[candidate] = True
                    region.append(candidate)

                    # Update Region-Normal (gewichteter Durchschnitt)
                    n = len(region)
                    region_normal = ((n-1) * region_normal + normals[candidate]) / n
                    region_normal = region_normal / np.linalg.norm(region_normal)

                    # Füge Nachbarn zur Queue
                    for neighbor in adjacency[candidate]:
                        if not visited[neighbor]:
                            queue.append(neighbor)

            elif angle < local_threshold:
                # Fallback: Global Threshold
                visited[candidate] = True
                region.append(candidate)

                n = len(region)
                region_normal = ((n-1) * region_normal + normals[candidate]) / n
                region_normal = region_normal / np.linalg.norm(region_normal)

                for neighbor in adjacency[candidate]:
                    if not visited[neighbor]:
                        queue.append(neighbor)

        return region

    def _fit_cylinder(
        self,
        points: np.ndarray,
        normals: np.ndarray
    ) -> Optional[Dict]:
        """
        Fittet Zylinder auf Punktwolke.

        Strategie:
        1. PCA auf Punkte für Achsenschätzung
        2. Berechne Radius als Median-Abstand zur Achse
        3. Validiere Fit-Qualität
        """
        if len(points) < 10:
            return None

        try:
            # Zentroid und PCA
            centroid = np.mean(points, axis=0)
            centered = points - centroid

            cov = np.cov(centered.T)
            eigenvalues, eigenvectors = np.linalg.eigh(cov)

            # Sortiere absteigend
            idx = np.argsort(eigenvalues)[::-1]
            eigenvalues = eigenvalues[idx]
            eigenvectors = eigenvectors[:, idx]

            # Achse = Richtung größter Varianz
            axis = eigenvectors[:, 0]
            axis = axis / np.linalg.norm(axis)

            # Prüfe Elongation
            if eigenvalues[1] < 1e-10:
                return None
            elongation = eigenvalues[0] / eigenvalues[1]

            if elongation < 1.5:  # Nicht elongiert genug
                return None

            # Radius: Abstand zur Achse
            proj_lengths = np.dot(centered, axis)
            proj_on_axis = np.outer(proj_lengths, axis)
            radial = centered - proj_on_axis
            distances = np.linalg.norm(radial, axis=1)

            radius = np.median(distances)

            if radius < 0.5 or radius > 100:
                return None

            # Fehler
            errors = np.abs(distances - radius)
            rms_error = np.sqrt(np.mean(errors**2))
            inlier_ratio = np.mean(errors < self.cyl_tol)

            if inlier_ratio < 0.7:  # Lockerer initial
                return None

            # Höhe
            height = proj_lengths.max() - proj_lengths.min()

            if height < 1.0:
                return None

            # Verhältnis prüfen
            if height < radius * 0.2:  # Zu flach
                return None

            return {
                'center': centroid,
                'axis': axis,
                'radius': radius,
                'height': height,
                'error': rms_error,
                'inlier_ratio': inlier_ratio
            }

        except Exception:
            return None

    def _fit_sphere(self, points: np.ndarray) -> Optional[Dict]:
        """
        Fittet Kugel auf Punktwolke via algebraischem Fit.
        """
        if len(points) < 10:
            return None

        try:
            # Least Squares
            A = np.column_stack([
                2 * points,
                np.ones(len(points))
            ])
            b = np.sum(points**2, axis=1)

            result, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
            cx, cy, cz, d = result

            center = np.array([cx, cy, cz])
            radius_sq = d + cx**2 + cy**2 + cz**2

            if radius_sq <= 0:
                return None

            radius = np.sqrt(radius_sq)

            if radius < 0.5 or radius > 200:
                return None

            # Fehler
            distances = np.linalg.norm(points - center, axis=1)
            errors = np.abs(distances - radius)
            rms_error = np.sqrt(np.mean(errors**2))
            inlier_ratio = np.mean(errors < self.sphere_tol)

            if inlier_ratio < 0.7:
                return None

            # Zusätzliche Validierung: Punkte sollten räumlich verteilt sein
            # (nicht alle auf einer Seite der Kugel)
            normalized = (points - center) / (distances[:, np.newaxis] + 1e-10)
            centroid_direction = np.mean(normalized, axis=0)

            # Wenn Punkte stark auf einer Seite: wahrscheinlich kein voller Kugelausschnitt
            if np.linalg.norm(centroid_direction) > 0.7:
                # Könnte Teil eines Zylinders sein - reduziere Confidence
                inlier_ratio *= 0.8

            return {
                'center': center,
                'radius': radius,
                'error': rms_error,
                'inlier_ratio': inlier_ratio
            }

        except Exception:
            return None


def detect_primitives_from_mesh(
    mesh: 'pv.PolyData'
) -> Tuple[List[CylinderFit], List[SphereFit]]:
    """Convenience-Funktion für Primitiv-Erkennung."""
    detector = MeshPrimitiveDetector()
    return detector.detect_from_mesh(mesh)
