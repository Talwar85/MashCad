"""
Curvature-basierte Primitiv-Erkennung für Mesh-Daten.

Mathematische Grundlage:
- Zylinder: Gauß-Krümmung K=0, Mittlere Krümmung H=1/(2R)
- Kugel: K=1/R², H=1/R
- Ebene: K=0, H=0

Verwendet diskrete Krümmungsberechnung basierend auf Mesh-Geometrie.
"""

import numpy as np
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from loguru import logger

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False


@dataclass
class CylinderRegion:
    """Erkannte zylindrische Region."""
    face_indices: List[int]
    center: np.ndarray
    axis: np.ndarray
    radius: float
    height: float
    mean_curvature: float
    confidence: float


@dataclass
class SphereRegion:
    """Erkannte sphärische Region."""
    face_indices: List[int]
    center: np.ndarray
    radius: float
    confidence: float


class CurvatureDetector:
    """
    Erkennt Primitive basierend auf diskreter Krümmungsanalyse.

    Algorithmus:
    1. Berechne Krümmung an jedem Vertex
    2. Propagiere zu Faces (Mittelwert der Vertices)
    3. Klassifiziere Faces nach Krümmungs-Signatur
    4. Gruppiere connected Faces gleicher Klasse
    5. Fitte Primitive auf Gruppen
    """

    def __init__(
        self,
        curvature_threshold: float = 0.01,  # Min Krümmung für gekrümmte Fläche
        plane_threshold: float = 0.005,      # Max Krümmung für Ebene
        min_region_faces: int = 10,          # Min Faces pro Region
        radius_tolerance: float = 0.2        # 20% Radius-Variation erlaubt
    ):
        self.curv_thresh = curvature_threshold
        self.plane_thresh = plane_threshold
        self.min_faces = min_region_faces
        self.radius_tol = radius_tolerance

    def detect_from_mesh(
        self,
        mesh: 'pv.PolyData'
    ) -> Tuple[List[CylinderRegion], List[SphereRegion]]:
        """
        Erkennt Zylinder und Kugeln in einem PyVista Mesh.

        Returns:
            Tuple von (Zylinder-Regionen, Kugel-Regionen)
        """
        if not HAS_PYVISTA:
            return [], []

        cylinders = []
        spheres = []

        # 1. Berechne Krümmungen
        logger.info("Berechne diskrete Krümmung...")
        mean_curv, gauss_curv = self._compute_curvatures(mesh)

        if mean_curv is None:
            return [], []

        # 2. Klassifiziere Faces
        logger.info("Klassifiziere Faces nach Krümmung...")
        face_classes = self._classify_faces(mesh, mean_curv, gauss_curv)

        # Statistik
        class_counts = {}
        for c in face_classes:
            class_counts[c] = class_counts.get(c, 0) + 1
        logger.info(f"  Face-Klassen: {class_counts}")

        # 3. Finde connected Regionen pro Klasse
        logger.info("Finde zusammenhängende Regionen...")

        # Zylinder-Kandidaten (K≈0, H≠0)
        cylinder_faces = [i for i, c in enumerate(face_classes) if c == 'cylinder']
        cylinder_regions = self._find_connected_regions(mesh, cylinder_faces)
        logger.info(f"  {len(cylinder_regions)} Zylinder-Regionen gefunden")

        # Kugel-Kandidaten (K>0, H>0)
        sphere_faces = [i for i, c in enumerate(face_classes) if c == 'sphere']
        sphere_regions = self._find_connected_regions(mesh, sphere_faces)
        logger.info(f"  {len(sphere_regions)} Kugel-Regionen gefunden")

        # 4. Fitte Primitive auf Regionen
        logger.info(f"Fitte Zylinder auf {len(cylinder_regions)} Regionen...")
        fit_attempts = 0
        for region_faces in cylinder_regions:
            if len(region_faces) < self.min_faces:
                continue

            fit_attempts += 1
            cyl = self._fit_cylinder(mesh, region_faces, mean_curv)
            if cyl is not None:
                cylinders.append(cyl)
                logger.info(f"    Zylinder: R={cyl.radius:.2f}mm, H={cyl.height:.2f}mm, "
                           f"{len(cyl.face_indices)} Faces, Conf={cyl.confidence:.2f}")

        logger.info(f"  {len(cylinders)}/{fit_attempts} Zylinder-Fits erfolgreich")

        for region_faces in sphere_regions:
            if len(region_faces) < self.min_faces:
                continue

            sph = self._fit_sphere(mesh, region_faces)
            if sph is not None:
                spheres.append(sph)
                logger.info(f"    Kugel: R={sph.radius:.2f}mm, {len(sph.face_indices)} Faces")

        return cylinders, spheres

    def _compute_curvatures(
        self,
        mesh: 'pv.PolyData'
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Berechnet diskrete Krümmung für jeden Vertex.

        Verwendet:
        - Mittlere Krümmung: Laplace-Beltrami Operator
        - Gauß-Krümmung: Winkeldefekt-Methode
        """
        try:
            points = mesh.points
            n_points = len(points)

            # Initialisiere
            mean_curvature = np.zeros(n_points)
            gauss_curvature = np.zeros(n_points)
            vertex_areas = np.zeros(n_points)

            # Sammle Nachbarschafts-Informationen
            # Für jeden Vertex: Liste der anliegenden Faces
            vertex_faces = [[] for _ in range(n_points)]

            faces = mesh.faces.reshape(-1, 4)[:, 1:4]  # Annahme: Triangles

            for face_idx, face in enumerate(faces):
                for v_idx in face:
                    vertex_faces[v_idx].append(face_idx)

            # Berechne Krümmung pro Vertex
            for v_idx in range(n_points):
                adj_faces = vertex_faces[v_idx]
                if len(adj_faces) < 3:
                    continue

                # Sammle Nachbar-Vertices
                neighbors = set()
                for f_idx in adj_faces:
                    for v in faces[f_idx]:
                        if v != v_idx:
                            neighbors.add(v)

                neighbors = list(neighbors)
                if len(neighbors) < 3:
                    continue

                p = points[v_idx]

                # Gauß-Krümmung via Winkeldefekt
                angle_sum = 0.0
                area_sum = 0.0

                for f_idx in adj_faces:
                    face = faces[f_idx]
                    # Finde Position von v_idx im Face
                    local_idx = np.where(face == v_idx)[0][0]

                    # Die anderen zwei Vertices
                    v1 = face[(local_idx + 1) % 3]
                    v2 = face[(local_idx + 2) % 3]

                    p1 = points[v1]
                    p2 = points[v2]

                    # Winkel bei v_idx
                    e1 = p1 - p
                    e2 = p2 - p
                    e1_norm = np.linalg.norm(e1)
                    e2_norm = np.linalg.norm(e2)

                    if e1_norm > 1e-10 and e2_norm > 1e-10:
                        cos_angle = np.dot(e1, e2) / (e1_norm * e2_norm)
                        cos_angle = np.clip(cos_angle, -1, 1)
                        angle = np.arccos(cos_angle)
                        angle_sum += angle

                    # Fläche (Dreieck)
                    area = 0.5 * np.linalg.norm(np.cross(e1, e2))
                    area_sum += area / 3  # Vertex bekommt 1/3 der Fläche

                # Gauß-Krümmung = (2π - Winkelsumme) / Fläche
                if area_sum > 1e-10:
                    gauss_curvature[v_idx] = (2 * np.pi - angle_sum) / area_sum
                    vertex_areas[v_idx] = area_sum

                # Mittlere Krümmung via Laplace-Beltrami (vereinfacht)
                # H = |Δp| / (4 * A) wobei Δp der diskrete Laplacian ist
                laplacian = np.zeros(3)
                weight_sum = 0.0

                for n_idx in neighbors:
                    pn = points[n_idx]
                    edge = pn - p
                    weight = 1.0 / (np.linalg.norm(edge) + 1e-10)
                    laplacian += weight * edge
                    weight_sum += weight

                if weight_sum > 1e-10:
                    laplacian /= weight_sum
                    mean_curvature[v_idx] = np.linalg.norm(laplacian) / (4 * max(area_sum, 1e-10))

            return mean_curvature, gauss_curvature

        except Exception as e:
            logger.error(f"Krümmungsberechnung fehlgeschlagen: {e}")
            return None, None

    def _classify_faces(
        self,
        mesh: 'pv.PolyData',
        mean_curv: np.ndarray,
        gauss_curv: np.ndarray
    ) -> List[str]:
        """
        Klassifiziert Faces basierend auf Krümmungs-Signatur.

        Klassen:
        - 'plane': K≈0, H≈0
        - 'cylinder': K≈0, H≠0
        - 'sphere': K>0, H>0
        - 'saddle': K<0 (hyperbolisch)
        - 'other': Unbestimmt
        """
        faces = mesh.faces.reshape(-1, 4)[:, 1:4]
        n_faces = len(faces)

        classifications = []

        for face in faces:
            # Mittlere Krümmung der Vertices
            H = np.mean([mean_curv[v] for v in face])
            K = np.mean([gauss_curv[v] for v in face])

            # Klassifikation
            if abs(K) < self.plane_thresh and abs(H) < self.plane_thresh:
                classifications.append('plane')
            elif abs(K) < self.curv_thresh and abs(H) > self.curv_thresh:
                classifications.append('cylinder')
            elif K > self.curv_thresh and H > self.curv_thresh:
                classifications.append('sphere')
            elif K < -self.curv_thresh:
                classifications.append('saddle')
            else:
                classifications.append('other')

        return classifications

    def _find_connected_regions(
        self,
        mesh: 'pv.PolyData',
        face_indices: List[int]
    ) -> List[List[int]]:
        """Findet zusammenhängende Regionen aus Face-Indices."""
        if not face_indices:
            return []

        # Baue Face-Nachbarschaft
        faces = mesh.faces.reshape(-1, 4)[:, 1:4]

        # Edge -> Faces Map
        edge_faces = {}
        for f_idx in face_indices:
            face = faces[f_idx]
            for i in range(3):
                edge = tuple(sorted([face[i], face[(i+1) % 3]]))
                if edge not in edge_faces:
                    edge_faces[edge] = []
                edge_faces[edge].append(f_idx)

        # Face -> Nachbar-Faces
        face_neighbors = {f: set() for f in face_indices}
        for edge, adj_faces in edge_faces.items():
            if len(adj_faces) == 2:
                f1, f2 = adj_faces
                face_neighbors[f1].add(f2)
                face_neighbors[f2].add(f1)

        # BFS für connected components
        regions = []
        visited = set()

        for start_face in face_indices:
            if start_face in visited:
                continue

            region = []
            queue = [start_face]

            while queue:
                f = queue.pop(0)
                if f in visited:
                    continue

                visited.add(f)
                region.append(f)

                for neighbor in face_neighbors.get(f, []):
                    if neighbor not in visited:
                        queue.append(neighbor)

            if region:
                regions.append(region)

        return regions

    def _fit_cylinder(
        self,
        mesh: 'pv.PolyData',
        face_indices: List[int],
        mean_curv: np.ndarray
    ) -> Optional[CylinderRegion]:
        """Fittet Zylinder auf Region."""
        try:
            faces = mesh.faces.reshape(-1, 4)[:, 1:4]
            points = mesh.points

            # Sammle Punkte
            vertex_set = set()
            for f_idx in face_indices:
                for v in faces[f_idx]:
                    vertex_set.add(v)

            vertices = list(vertex_set)
            region_points = points[vertices]

            if len(region_points) < 10:
                logger.debug(f"    Zylinder-Fit: Zu wenige Punkte ({len(region_points)} < 10)")
                return None

            # PCA für Achsenrichtung (OHNE Krümmungsschätzung - die ist für Mesh-Daten unzuverlässig)
            centroid = np.mean(region_points, axis=0)
            centered = region_points - centroid

            cov = np.cov(centered.T)
            eigenvalues, eigenvectors = np.linalg.eigh(cov)

            # Sortiere nach Eigenvalues (absteigend)
            idx_sorted = np.argsort(eigenvalues)[::-1]
            eigenvalues = eigenvalues[idx_sorted]
            eigenvectors = eigenvectors[:, idx_sorted]

            # Größte Varianz = Achsenrichtung
            axis = eigenvectors[:, 0]
            axis = axis / np.linalg.norm(axis)

            # Prüfe ob elongiert genug für Zylinder
            # Verhältnis zwischen größter und zweitgrößter Varianz
            if eigenvalues[0] < 1e-10:
                return None
            elongation_ratio = eigenvalues[0] / (eigenvalues[1] + 1e-10)

            # Zylinder sollte elongiert sein (Varianz entlang Achse >> radiale Varianz)
            # Aber nicht zu extrem (dann wäre es eine Linie)
            if elongation_ratio < 1.2:  # Nicht elongiert genug
                logger.debug(f"    Zylinder-Fit: Nicht elongiert ({elongation_ratio:.2f} < 1.2)")
                return None

            # Verfeinere Radius: Abstand zur Achse
            proj = np.outer(np.dot(centered, axis), axis)
            radial = centered - proj
            distances = np.linalg.norm(radial, axis=1)

            radius = np.median(distances)
            radius_std = np.std(distances)

            # Relative Streuung
            if radius < 1e-6:
                return None
            relative_std = radius_std / radius

            # Lockere Toleranz für Mesh-Daten (30% statt 20%)
            if relative_std > 0.35:
                logger.debug(f"    Zylinder-Fit: Hohe Radius-Streuung ({relative_std:.1%} > 35%)")
                return None

            if radius < 0.3 or radius > 100:  # Erweiterte Grenzen
                logger.debug(f"    Zylinder-Fit: Unrealistischer Radius ({radius:.2f}mm)")
                return None

            # Höhe
            projections = np.dot(centered, axis)
            height = projections.max() - projections.min()

            if height < 0.5:  # Lockerer (0.5mm statt 1.0mm)
                logger.debug(f"    Zylinder-Fit: Zu niedrig ({height:.2f}mm < 0.5mm)")
                return None

            # Verhältnis Höhe/Radius - Zylinder sollten nicht extrem flach sein
            if height < radius * 0.1:
                logger.debug(f"    Zylinder-Fit: Zu flach (H/R={height/radius:.2f} < 0.1)")
                return None

            # Mittlere Krümmung für Info (optional)
            curv_values = [mean_curv[v] for v in vertices if mean_curv[v] > 0.001]
            avg_H = np.mean(curv_values) if curv_values else 0.0

            # Confidence basierend auf Fit-Qualität
            confidence = 1.0 - relative_std

            return CylinderRegion(
                face_indices=face_indices,
                center=centroid,
                axis=axis,
                radius=radius,
                height=height,
                mean_curvature=avg_H,
                confidence=confidence
            )

        except Exception as e:
            logger.debug(f"Zylinder-Fit fehlgeschlagen: {e}")
            return None

    def _fit_sphere(
        self,
        mesh: 'pv.PolyData',
        face_indices: List[int]
    ) -> Optional[SphereRegion]:
        """Fittet Kugel auf Region."""
        try:
            faces = mesh.faces.reshape(-1, 4)[:, 1:4]
            points = mesh.points

            # Sammle Punkte
            vertex_set = set()
            for f_idx in face_indices:
                for v in faces[f_idx]:
                    vertex_set.add(v)

            vertices = list(vertex_set)
            region_points = points[vertices]

            if len(region_points) < 10:
                return None

            # Algebraischer Kugel-Fit
            # x² + y² + z² = 2*cx*x + 2*cy*y + 2*cz*z + (r² - cx² - cy² - cz²)
            A = np.column_stack([
                2 * region_points,
                np.ones(len(region_points))
            ])
            b = np.sum(region_points**2, axis=1)

            result, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
            cx, cy, cz, d = result

            center = np.array([cx, cy, cz])
            radius_sq = d + cx**2 + cy**2 + cz**2

            if radius_sq <= 0:
                return None

            radius = np.sqrt(radius_sq)

            # Validierung
            distances = np.linalg.norm(region_points - center, axis=1)
            errors = np.abs(distances - radius)

            if np.mean(errors) > radius * 0.15:
                return None

            if radius < 0.5 or radius > 100:
                return None

            confidence = 1.0 - np.mean(errors) / radius

            return SphereRegion(
                face_indices=face_indices,
                center=center,
                radius=radius,
                confidence=confidence
            )

        except Exception:
            return None


def detect_primitives_curvature(mesh: 'pv.PolyData') -> Tuple[List[CylinderRegion], List[SphereRegion]]:
    """
    Convenience-Funktion für Curvature-basierte Primitiv-Erkennung.
    """
    detector = CurvatureDetector()
    return detector.detect_from_mesh(mesh)
