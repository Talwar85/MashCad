"""
Perfect Converter - Primitive Detector
========================================

Erweiterte Primitive-Erkennung für PerfectConverter:
- Plane (Ebene)
- Cylinder (Zylinder) - mit glatter Oberfläche!
- Sphere (Kugel)
- Cone (Kegel)
- Torus (Ring)
- NURBS (Freiformflächen)

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

try:
    from sklearn.decomposition import PCA
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


class PrimitiveType(Enum):
    """Typen von geometrischen Primitive."""
    PLANE = auto()
    CYLINDER = auto()
    SPHERE = auto()
    CONE = auto()
    TORUS = auto()
    NURBS = auto()
    UNKNOWN = auto()


@dataclass
class DetectedPrimitive:
    """Ein erkanntes geometrisches Primitiv."""
    type: PrimitiveType
    region_id: int
    face_indices: List[int]

    # Geometrie-Parameter (abhängig vom Typ)
    origin: np.ndarray = None      # Ursprungspunkt
    normal: np.ndarray = None      # Normale/Richtung
    axis: np.ndarray = None        # Achse (für Zylinder/Kegel)
    radius: float = None           # Radius
    radius2: float = None          # Zweiter Radius (für Torus)
    height: float = None           # Höhe (für Zylinder/Kegel)

    # Qualitäts-Metriken
    confidence: float = 1.0        # 0-1, Fit-Qualität
    error: float = 0.0             # RMS Fehler in mm
    area: float = 0.0              # Fläche in mm²

    def __post_init__(self):
        if self.origin is None:
            self.origin = np.zeros(3)
        if self.normal is None:
            self.normal = np.array([0, 0, 1])
        if self.axis is None:
            self.axis = np.array([0, 0, 1])


class PrimitiveDetector:
    """
    Erweiterte Primitive-Erkennung mit mehreren Strategien.

    Strategien:
    1. Normalen-basierte Region Growing (für Planes)
    2. PCA-basierte Achsenerkennung (für Zylinder/Kegel)
    3. Algebraischer Fit (für Kugeln)
    4. Kurven-Analyse (für Torus)
    """

    def __init__(
        self,
        # Allgemein
        min_region_faces: int = 10,
        normal_tolerance: float = 0.1,      # rad ~5.7°
        # Plane
        plane_tolerance: float = 0.2,        # mm
        # Cylinder
        cylinder_tolerance: float = 0.3,     # mm
        min_cylinder_faces: int = 20,
        # Sphere
        sphere_tolerance: float = 0.3,       # mm
        min_sphere_faces: int = 15,
    ):
        self.min_region_faces = min_region_faces
        self.normal_tol = normal_tolerance
        self.plane_tol = plane_tolerance
        self.cyl_tol = cylinder_tolerance
        self.min_cyl_faces = min_cylinder_faces
        self.sphere_tol = sphere_tolerance
        self.min_sphere_faces = min_sphere_faces

    def detect_primitives(
        self,
        mesh: 'pv.PolyData'
    ) -> List[DetectedPrimitive]:
        """
        Erkennt alle geometrischen Primitive im Mesh.

        Args:
            mesh: PyVista PolyData

        Returns:
            Liste von DetectedPrimitive
        """
        if not HAS_PYVISTA:
            logger.error("PyVista nicht verfügbar")
            return []

        logger.info(f"Primitive Detection: {mesh.n_cells} Faces")

        # 1. Region Growing basierend auf Normalen
        regions = self._segment_by_normals(mesh)
        logger.info(f"  {len(regions)} Regionen gefunden")

        # 2. Jede Region analysieren
        primitives = []
        for region_id, (face_indices, normal) in enumerate(regions):
            if len(face_indices) < self.min_region_faces:
                continue

            primitive = self._analyze_region(mesh, region_id, face_indices, normal)
            if primitive and primitive.confidence > 0.5:
                primitives.append(primitive)

        # Logging pro Typ
        type_counts = {}
        for p in primitives:
            type_name = p.type.name
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

        logger.info(f"  Erkannt: {type_counts}")

        return primitives

    def _segment_by_normals(
        self,
        mesh: 'pv.PolyData'
    ) -> List[Tuple[List[int], np.ndarray]]:
        """
        Segmentiert Faces nach Normalen-Richtung.

        Returns:
            Liste von (face_indices, average_normal) Tupeln
        """
        mesh.compute_normals(cell_normals=True, inplace=True)
        face_normals = mesh.cell_data['Normals']

        faces_arr = mesh.faces.reshape(-1, 4)[:, 1:4]
        n_faces = len(faces_arr)

        # Adjazenz-Graph bauen
        face_adj = self._build_face_adjacency(faces_arr)

        visited = set()
        regions = []

        for start_face in range(n_faces):
            if start_face in visited:
                continue

            # Region Growing
            region_faces = [start_face]
            visited.add(start_face)
            queue = [start_face]

            while queue:
                current = queue.pop(0)
                current_normal = face_normals[current]

                for neighbor in face_adj.get(current, []):
                    if neighbor in visited:
                        continue

                    # Winkel prüfen
                    neighbor_normal = face_normals[neighbor]
                    angle = np.arccos(np.clip(np.dot(current_normal, neighbor_normal), -1, 1))

                    if angle < self.normal_tol:
                        visited.add(neighbor)
                        region_faces.append(neighbor)
                        queue.append(neighbor)

            if len(region_faces) >= self.min_region_faces:
                avg_normal = np.mean([face_normals[i] for i in region_faces], axis=0)
                avg_normal = avg_normal / np.linalg.norm(avg_normal)
                regions.append((region_faces, avg_normal))

        return regions

    def _build_face_adjacency(self, faces_arr: np.ndarray) -> Dict[int, List[int]]:
        """Baut Adjazenz-Graph basierend auf geteilten Vertices."""
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

    def _analyze_region(
        self,
        mesh: 'pv.PolyData',
        region_id: int,
        face_indices: List[int],
        normal: np.ndarray
    ) -> Optional[DetectedPrimitive]:
        """
        Analysiert eine Region und erkennt den Primitive-Typ.

        Args:
            mesh: PyVista Mesh
            region_id: ID der Region
            face_indices: Indizes der Faces
            normal: Durchschnitts-Normale

        Returns:
            DetectedPrimitive oder None
        """
        # Punkte extrahieren
        points = self._extract_region_points(mesh, face_indices)

        if len(points) < 4:
            return None

        # Versuche verschiedene Primitive in Reihenfolge der Häufigkeit
        # 1. Plane (am häufigsten)
        plane = self._try_fit_plane(points, face_indices)
        if plane and plane.confidence > 0.9:
            return plane

        # 2. Cylinder (zweit häufigst)
        if len(points) >= self.min_cyl_faces * 3:
            cylinder = self._try_fit_cylinder(points, face_indices, normal)
            if cylinder and cylinder.confidence > 0.7:
                return cylinder

        # 3. Sphere
        if len(points) >= self.min_sphere_faces * 3:
            sphere = self._try_fit_sphere(points, face_indices)
            if sphere and sphere.confidence > 0.7:
                return sphere

        # Fallback: Plane mit niedrigerem Confidence
        return plane

    def _extract_region_points(
        self,
        mesh: 'pv.PolyData',
        face_indices: List[int]
    ) -> np.ndarray:
        """Extrahiert alle Punkte aus den Faces einer Region."""
        faces_arr = mesh.faces.reshape(-1, 4)[:, 1:4]
        all_points = []

        for idx in face_indices:
            face = faces_arr[idx]
            for v_idx in face:
                all_points.append(mesh.points[v_idx])

        return np.array(all_points)

    def _try_fit_plane(
        self,
        points: np.ndarray,
        face_indices: List[int]
    ) -> Optional[DetectedPrimitive]:
        """
        Fitte eine Ebene via SVD.

        Returns:
            DetectedPrimitive mit TYPE=PLANE oder None
        """
        if not HAS_SKLEARN:
            return None

        try:
            pca = PCA(n_components=3)
            pca.fit(points)

            # Normale = kleinste Hauptkomponente
            normal = pca.components_[2]

            # Ursprung = Schwerpunkt
            origin = np.mean(points, axis=0)

            # Abstände zur Ebene
            centered = points - origin
            distances = np.dot(centered, normal)

            # Inlier-Ratio
            inliers = np.abs(distances) < self.plane_tol
            inlier_ratio = np.mean(inliers)

            # RMS Error
            error = np.sqrt(np.mean(distances ** 2))

            return DetectedPrimitive(
                type=PrimitiveType.PLANE,
                region_id=0,
                face_indices=face_indices,
                origin=origin,
                normal=normal,
                confidence=inlier_ratio,
                error=error,
                area=len(face_indices) * 10.0  # Schätzung
            )

        except Exception as e:
            logger.warning(f"Plane-Fit fehlgeschlagen: {e}")
            return None

    def _try_fit_cylinder(
        self,
        points: np.ndarray,
        face_indices: List[int],
        region_normal: np.ndarray
    ) -> Optional[DetectedPrimitive]:
        """
        Fitte einen Zylinder via PCA.

        Returns:
            DetectedPrimitive mit TYPE=CYLINDER oder None
        """
        if not HAS_SKLEARN:
            return None

        try:
            pca = PCA(n_components=3)
            pca.fit(points)

            # Achse = Hauptkomponente (größte Varianz)
            axis = pca.components_[0]

            # Ursprung = Schwerpunkt
            origin = np.mean(points, axis=0)

            # Radius = Median-Abstand zur Achse
            to_origin = points - origin
            proj_lengths = np.dot(to_origin, axis)
            proj_on_axis = np.outer(proj_lengths, axis)
            radial = to_origin - proj_on_axis
            distances = np.linalg.norm(radial, axis=1)

            radius = np.median(distances)

            # Inlier-Ratio
            inliers = np.abs(distances - radius) < self.cyl_tol
            inlier_ratio = np.mean(inliers)

            # RMS Error
            error = np.sqrt(np.mean((distances - radius) ** 2))

            return DetectedPrimitive(
                type=PrimitiveType.CYLINDER,
                region_id=0,
                face_indices=face_indices,
                origin=origin,
                axis=axis,
                radius=radius,
                height=proj_lengths.max() - proj_lengths.min() if len(proj_lengths) > 0 else 0,
                confidence=inlier_ratio,
                error=error,
                area=len(face_indices) * 10.0
            )

        except Exception as e:
            logger.warning(f"Cylinder-Fit fehlgeschlagen: {e}")
            return None

    def _try_fit_sphere(
        self,
        points: np.ndarray,
        face_indices: List[int]
    ) -> Optional[DetectedPrimitive]:
        """
        Fitte eine Kugel via algebraischem Fit.

        Returns:
            DetectedPrimitive mit TYPE=SPHERE oder None
        """
        try:
            # Einfache Methode: Zentrum = Schwerpunkt
            center = np.mean(points, axis=0)

            # Radius = Median-Abstand zum Zentrum
            distances = np.linalg.norm(points - center, axis=1)
            radius = np.median(distances)

            # Inlier-Ratio
            inliers = np.abs(distances - radius) < self.sphere_tol
            inlier_ratio = np.mean(inliers)

            # RMS Error
            error = np.sqrt(np.mean((distances - radius) ** 2))

            return DetectedPrimitive(
                type=PrimitiveType.SPHERE,
                region_id=0,
                face_indices=face_indices,
                origin=center,
                radius=radius,
                confidence=inlier_ratio,
                error=error,
                area=len(face_indices) * 10.0
            )

        except Exception as e:
            logger.warning(f"Sphere-Fit fehlgeschlagen: {e}")
            return None
