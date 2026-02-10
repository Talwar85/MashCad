"""
MashCad - Mesh Primitive Detector
==================================

Erkennt geometrische Primitive (Zylinder) direkt aus Mesh-Daten.
Wird von FinalMeshConverter für Zylinder-erhaltende Konvertierung verwendet.

Author: Claude (MeshConverter Architecture)
Date: 2026-02-10
"""

import numpy as np
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from loguru import logger
from collections import defaultdict

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

try:
    from sklearn.decomposition import PCA
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    logger.warning("sklearn nicht verfügbar - Zylinder-Erkennung eingeschränkt")


@dataclass
class CylinderFit:
    """Ergebnis eines Zylinder-Fits aus Mesh-Daten."""
    center: np.ndarray      # Punkt auf der Achse
    axis: np.ndarray        # Achsenrichtung (normalisiert)
    radius: float           # Radius
    height: float           # Höhe entlang Achse
    error: float            # RMS Fehler
    inlier_ratio: float     # Anteil der Punkte innerhalb Toleranz
    face_indices: List[int] = None  # Indizes der Mesh-Faces

    def __post_init__(self):
        if self.face_indices is None:
            self.face_indices = []


class MeshPrimitiveDetector:
    """
    Erkennt Zylinder-Primitive direkt aus Mesh-Daten.

    Verwendung durch FinalMeshConverter für analytische Zylinder-Surfaces.
    """

    def __init__(
        self,
        angle_threshold: float = 12.0,
        min_region_faces: int = 20,
        cylinder_tolerance: float = 0.3,
        min_inlier_ratio: float = 0.88
    ):
        """
        Args:
            angle_threshold: Max Winkelabweichung in Grad für Region-Bildung
            min_region_faces: Min Faces pro Region
            cylinder_tolerance: Max Abweichung für Zylinder-Fit in mm
            min_inlier_ratio: Min Inlier-Ratio für gültigen Zylinder
        """
        self.angle_thresh = np.radians(angle_threshold)
        self.min_region_faces = min_region_faces
        self.cyl_tol = cylinder_tolerance
        self.min_inlier = min_inlier_ratio

    def detect_from_mesh(self, mesh: 'pv.PolyData') -> Tuple[List[CylinderFit], Dict]:
        """
        Erkennt alle Zylinder im Mesh.

        Args:
            mesh: PyVista PolyData

        Returns:
            (Liste von CylinderFit, Stats-Dict)
        """
        if not HAS_SKLEARN:
            logger.warning("sklearn nicht verfügbar - keine Zylinder-Erkennung")
            return {}, {}

        stats = {
            'total_faces': mesh.n_cells,
            'regions_detected': 0,
            'cylinders_detected': 0
        }

        # 1. Berechne Face-Normalen
        mesh.compute_normals(cell_normals=True, inplace=True)
        face_normals = mesh.cell_data['Normals']

        # 2. Segmentiere nach Normalen-Richtung
        regions = self._segment_by_normals(mesh, face_normals)
        stats['regions_detected'] = len(regions)

        # 3. Fitte Zylinder auf jede Region
        cylinders = []
        for region_faces, normal in regions:
            if len(region_faces) < self.min_region_faces:
                continue

            cylinder = self._try_fit_cylinder(mesh, region_faces, normal)
            if cylinder and cylinder.inlier_ratio >= self.min_inlier:
                cylinders.append(cylinder)
                stats['cylinders_detected'] += 1

        logger.debug(f"Zylinder-Erkennung: {stats['cylinders_detected']} Zylinder aus {stats['regions_detected']} Regionen")

        return cylinders, stats

    def _segment_by_normals(
        self,
        mesh: 'pv.PolyData',
        face_normals: np.ndarray
    ) -> List[Tuple[List[int], np.ndarray]]:
        """
        Segmentiert Faces nach Normalen-Richtung.

        Returns:
            Liste von (face_indices, average_normal) Tupeln
        """
        # Region Growing basierend auf Normalen-Winkel
        visited = set()
        regions = []

        # Faces array: [n_verts, v0, v1, v2, ...]
        faces_arr = mesh.faces.reshape(-1, 4)[:, 1:4]
        n_faces = len(faces_arr)

        # Adjazenz: Faces die Vertices teilen
        face_adj = self._build_face_adjacency(faces_arr)

        for start_face in range(n_faces):
            if start_face in visited:
                continue

            # Neue Region starten
            region_faces = [start_face]
            region_normal = face_normals[start_face].copy()
            visited.add(start_face)
            queue = [start_face]

            while queue:
                current = queue.pop(0)
                current_normal = face_normals[current]

                # Prüfe Nachbarn
                for neighbor in face_adj.get(current, []):
                    if neighbor in visited:
                        continue

                    # Winkel prüfen
                    neighbor_normal = face_normals[neighbor]
                    angle = np.arccos(np.clip(np.dot(current_normal, neighbor_normal), -1, 1))

                    if angle < self.angle_thresh:
                        visited.add(neighbor)
                        region_faces.append(neighbor)
                        queue.append(neighbor)

            if len(region_faces) >= self.min_region_faces:
                # Durchschnitts-Normale berechnen
                avg_normal = np.mean([face_normals[i] for i in region_faces], axis=0)
                avg_normal = avg_normal / np.linalg.norm(avg_normal)
                regions.append((region_faces, avg_normal))

        return regions

    def _build_face_adjacency(self, faces_arr: np.ndarray) -> Dict[int, List[int]]:
        """Baut Adjazenz-Graph basierend auf geteilten Vertices."""
        vertex_to_faces = defaultdict(list)
        for i, face in enumerate(faces_arr):
            for v in face:
                vertex_to_faces[v].append(i)

        adj = defaultdict(set)
        for face_list in vertex_to_faces.values():
            for i in range(len(face_list)):
                for j in range(i + 1, len(face_list)):
                    adj[face_list[i]].add(face_list[j])
                    adj[face_list[j]].add(face_list[i])

        return {k: list(v) for k, v in adj.items()}

    def _try_fit_cylinder(
        self,
        mesh: 'pv.PolyData',
        face_indices: List[int],
        region_normal: np.ndarray
    ) -> Optional[CylinderFit]:
        """
        Versucht Zylinder-Fit auf Face-Region.

        Args:
            mesh: PyVista Mesh
            face_indices: Indizes der Faces in der Region
            region_normal: Durchschnitts-Normale der Region

        Returns:
            CylinderFit oder None
        """
        # Punkte extrahieren
        all_points = []
        faces_arr = mesh.faces.reshape(-1, 4)[:, 1:4]

        for idx in face_indices:
            face = faces_arr[idx]
            for v_idx in face:
                all_points.append(mesh.points[v_idx])

        points = np.array(all_points)

        if len(points) < 10:
            return None

        # PCA für Achsen-Finding
        try:
            pca = PCA(n_components=3)
            pca.fit(points)

            # Hauptkomponente = mögliche Achse
            axis = pca.components_[0]

            # Zylinder-Normalen sollten um Achse rotieren
            # Die Achse ist senkrecht zur Region-Normalen (bei geradem Zylinder)
            axis = axis / np.linalg.norm(axis)

            # Radius als Median-Abstand zur Achse
            centroid = np.mean(points, axis=0)
            to_centroid = points - centroid
            proj_lengths = np.dot(to_centroid, axis)
            proj_on_axis = np.outer(proj_lengths, axis)
            radial = to_centroid - proj_on_axis
            distances = np.linalg.norm(radial, axis=1)

            radius = np.median(distances)

            # Inlier prüfen
            inliers = np.abs(distances - radius) < self.cyl_tol
            inlier_ratio = np.mean(inliers)

            # Höhe
            if proj_lengths.size > 0:
                height = proj_lengths.max() - proj_lengths.min()
            else:
                height = 0.0

            # RMS Error
            error = np.sqrt(np.mean((distances - radius) ** 2))

            return CylinderFit(
                center=centroid,
                axis=axis,
                radius=radius,
                height=height,
                error=error,
                inlier_ratio=inlier_ratio,
                face_indices=face_indices
            )

        except Exception as e:
            logger.warning(f"Zylinder-Fit fehlgeschlagen: {e}")
            return None
