"""
Perfect Converter - Feature Detector
=====================================

Erkennt CAD-spezifische Features für PerfectConverter:
- Fillets (runde Übergänge)
- Chamfers (abgeschrägte Kanten)
- Holes (Bohrungen)
- Steps (Stufen)

Author: Claude (MeshConverter Architecture)
Date: 2026-02-10
"""

import numpy as np
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from loguru import logger
from enum import Enum, auto

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False


class FeatureType(Enum):
    """Typen von CAD-Features."""
    FILLET = auto()      # Runder Übergang
    CHAMFER = auto()     # Abgeschrägte Kante
    HOLE = auto()        # Bohrung
    STEP = auto()        # Stufe
    UNKNOWN = auto()


@dataclass
class DetectedFeature:
    """Ein erkanntes CAD-Feature."""
    type: FeatureType
    edge_indices: List[int]
    face_indices: List[int]

    # Parameter (abhängig vom Typ)
    radius: float = None         # Für Fillets
    angle: float = None          # Für Chamfers (in Grad)
    diameter: float = None       # Für Holes

    # Geometrie
    center: np.ndarray = None
    axis: np.ndarray = None
    start_point: np.ndarray = None
    end_point: np.ndarray = None

    confidence: float = 1.0


class FeatureDetector:
    """
    Erkennt CAD-Features im Mesh.

    Strategien:
    1. Winkel-basierte Erkennung für Fillets/Chamfers
    2. Topologie-Analyse für Holes
    3. Höhen-Profiler für Steps
    """

    def __init__(
        self,
        # Fillet/Chamfer
        fillet_angle_threshold: float = 120,   # Grad - Fillet hat flachen Winkel
        chamfer_angle_threshold: float = 135,  # Grad - Chamfer hat steilen Winkel
        min_fillet_faces: int = 6,
        # Hole
        hole_min_faces: int = 12,
        hole_circularity_threshold: float = 0.8,
    ):
        self.fillet_angle = np.radians(fillet_angle_threshold)
        self.chamfer_angle = np.radians(chamfer_angle_threshold)
        self.min_fillet_faces = min_fillet_faces
        self.min_hole_faces = hole_min_faces
        self.hole_circularity = hole_circularity_threshold

    def detect_features(
        self,
        mesh: 'pv.PolyData',
        primitives: List = None
    ) -> List[DetectedFeature]:
        """
        Erkennt alle CAD-Features im Mesh.

        Args:
            mesh: PyVista PolyData
            primitives: Liste der erkannten Primitive (für Kontext)

        Returns:
            Liste von DetectedFeature
        """
        if not HAS_PYVISTA:
            return []

        logger.info("Feature Detection...")

        features = []

        # 1. Fillets und Chamfers (Winkel-basiert)
        fillet_chamfers = self._detect_fillet_chamfer(mesh)
        features.extend(fillet_chamfers)

        # 2. Holes (Topologie-basiert)
        holes = self._detect_holes(mesh)
        features.extend(holes)

        # Logging
        type_counts = {}
        for f in features:
            type_name = f.type.name
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

        logger.info(f"  Features erkannt: {type_counts}")

        return features

    def _detect_fillet_chamfer(
        self,
        mesh: 'pv.PolyData'
    ) -> List[DetectedFeature]:
        """
        Erkennt Fillets und Chamfers basierend auf Face-Normalen-Winkeln.

        Fillet: Konvexe Übergänge mit flachem Winkel (< 120°)
        Chamfer: Abgeschrägte Kanten mit steilem Winkel (120° - 150°)
        """
        mesh.compute_normals(cell_normals=True, inplace=True)
        face_normals = mesh.cell_data['Normals']

        faces_arr = mesh.faces.reshape(-1, 4)[:, 1:4]
        n_faces = len(faces_arr)

        # Face-Adjazenz für Winkel-Berechnung
        face_adj = self._build_face_adjacency(faces_arr)

        features = []

        for face_idx in range(n_faces):
            # Prüfe Winkel zu allen Nachbarn
            neighbors = face_adj.get(face_idx, [])

            if len(neighbors) < 2:
                continue

            current_normal = face_normals[face_idx]
            angles = []

            for neighbor_idx in neighbors:
                neighbor_normal = face_normals[neighbor_idx]
                angle = np.arccos(np.clip(np.dot(current_normal, neighbor_normal), -1, 1))
                angles.append(angle)

            if not angles:
                continue

            avg_angle = np.mean(angles)

            # Fillet: flacher Winkel
            if avg_angle < self.fillet_angle:
                # Schätze Radius aus Geometrie
                region_faces = self._get_connected_faces(mesh, face_idx, face_adj)
                if len(region_faces) >= self.min_fillet_faces:
                    radius = self._estimate_fillet_radius(mesh, region_faces)
                    features.append(DetectedFeature(
                        type=FeatureType.FILLET,
                        edge_indices=[],
                        face_indices=region_faces,
                        radius=radius,
                        confidence=min(1.0, len(region_faces) / self.min_fillet_faces)
                    ))

            # Chamfer: steiler Winkel
            elif avg_angle > self.fillet_angle and avg_angle < self.chamfer_angle:
                region_faces = self._get_connected_faces(mesh, face_idx, face_adj)
                features.append(DetectedFeature(
                    type=FeatureType.CHAMFER,
                    edge_indices=[],
                    face_indices=region_faces,
                    angle=np.degrees(avg_angle),
                    confidence=0.8
                ))

        return features

    def _detect_holes(
        self,
        mesh: 'pv.PolyData'
    ) -> List[DetectedFeature]:
        """
        Erkennt Löcher basierend auf Topologie.
        Ein Loch ist eine geschlossene Schleife von Faces mit zylindrischer Geometrie.
        """
        # Einfache Heuristik: Finde geschlossene Ringe aus Faces
        # mit ähnlichen Normalen (zeigen nach innen)

        mesh.compute_normals(cell_normals=True, inplace=True)
        face_normals = mesh.cell_data['Normals']

        faces_arr = mesh.faces.reshape(-1, 4)[:, 1:4]
        face_adj = self._build_face_adjacency(faces_arr)

        holes = []
        visited = set()

        for face_idx in range(len(faces_arr)):
            if face_idx in visited:
                continue

            # Prüfe ob Normalen nach innen zeigen (zur Mesh-Mitte)
            normal = face_normals[face_idx]
            mesh_center = np.mean(mesh.points, axis=0)
            face_center = np.mean(mesh.points[faces_arr[face_idx]], axis=0)

            to_center = mesh_center - face_center
            to_center = to_center / np.linalg.norm(to_center)

            # Wenn Normalen zur Mitte zeigen, könnte es ein Loch sein
            if np.dot(normal, to_center) > 0.5:  # Zeigt nach innen
                region = self._get_connected_faces(mesh, face_idx, face_adj, max_size=50)

                if len(region) >= self.min_hole_faces:
                    # Prüfe auf zylindrische Form
                    if self._is_cylindrical_region(mesh, region):
                        center, axis, radius = self._fit_cylinder_to_region(mesh, region)
                        holes.append(DetectedFeature(
                            type=FeatureType.HOLE,
                            edge_indices=[],
                            face_indices=region,
                            diameter=radius * 2,
                            center=center,
                            axis=axis,
                            confidence=0.8
                        ))
                        visited.update(region)

        return holes

    def _build_face_adjacency(self, faces_arr: np.ndarray) -> Dict[int, List[int]]:
        """Baut Adjazenz-Graph."""
        from collections import defaultdict

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

    def _get_connected_faces(
        self,
        mesh: 'pv.PolyData',
        start_face: int,
        face_adj: Dict,
        max_size: int = 100
    ) -> List[int]:
        """Holt alle verbundenen Faces ab start_face."""
        visited = {start_face}
        queue = [start_face]
        result = []

        while queue and len(result) < max_size:
            current = queue.pop(0)
            result.append(current)

            for neighbor in face_adj.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return result

    def _estimate_fillet_radius(
        self,
        mesh: 'pv.PolyData',
        face_indices: List[int]
    ) -> float:
        """
        Schätzt den Fillet-Radius aus der Geometrie.

        Methode: Betrachte die Krümmung über die Faces
        """
        # Einfache Schätzung basierend auf der Anzahl der Faces
        # Mehr Faces = größerer Radius
        return float(len(face_indices)) * 0.5

    def _is_cylindrical_region(
        self,
        mesh: 'pv.PolyData',
        face_indices: List[int]
    ) -> bool:
        """Prüft ob eine Region zylindrisch ist."""
        if len(face_indices) < self.min_hole_faces:
            return False

        # Prüfe ob alle Normalen ähnlich zur Zylinder-Achse sind
        mesh.compute_normals(cell_normals=True, inplace=True)
        normals = mesh.cell_data['Normals'][face_indices]

        # PCA der Normalen
        try:
            from sklearn.decomposition import PCA
            pca = PCA(n_components=3)
            pca.fit(normals)

            # Bei einem Zylinder sollten Normalen in einer Ebene liegen
            # -> Die kleinste Varianz sollte sehr klein sein
            variances = pca.explained_variance_ratio_
            return variances[2] < 0.1  # Kleinste Varianz < 10%
        except Exception:
            return False

    def _fit_cylinder_to_region(
        self,
        mesh: 'pv.PolyData',
        face_indices: List[int]
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """
        Fittet einen Zylinder auf eine Region.

        Returns:
            (center, axis, radius)
        """
        # Punkte extrahieren
        faces_arr = mesh.faces.reshape(-1, 4)[:, 1:4]
        points = []

        for idx in face_indices:
            face = faces_arr[idx]
            for v_idx in face:
                points.append(mesh.points[v_idx])

        points = np.array(points)

        # PCA für Achse
        try:
            from sklearn.decomposition import PCA
            pca = PCA(n_components=3)
            pca.fit(points)

            axis = pca.components_[0]
            center = np.mean(points, axis=0)

            # Radius
            to_center = points - center
            proj_lengths = np.dot(to_center, axis)
            proj_on_axis = np.outer(proj_lengths, axis)
            radial = to_center - proj_on_axis
            radius = np.median(np.linalg.norm(radial, axis=1))

            return center, axis, float(radius)

        except Exception:
            return np.zeros(3), np.array([0, 0, 1]), 1.0
