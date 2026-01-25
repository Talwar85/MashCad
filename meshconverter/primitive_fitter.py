"""
MashCad - Primitive Fitter
==========================

Fittet geometrische Primitive (Plane, Cylinder, Sphere, Cone) auf Mesh-Regionen.
Eigene Implementation OHNE pyransac3d für Stabilität.
"""

import numpy as np
from typing import Optional, Tuple
from loguru import logger

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
    logger.warning("sklearn nicht verfügbar - Cylinder-Fitting eingeschränkt")

from meshconverter.mesh_converter_v10 import Region, DetectedPrimitive


class PrimitiveFitter:
    """
    Fittet geometrische Primitive auf Mesh-Regionen.

    Unterstützte Primitive:
    - Plane (SVD-basiert)
    - Cylinder (PCA + Median)
    - Sphere (Algebraischer Fit)
    - Cone (Apex-Detection)
    - B-Spline (via NURBSFitter)
    """

    def __init__(
        self,
        tolerance: float = 0.5,     # mm - Fitting-Toleranz
        min_confidence: float = 0.7, # Minimum Confidence für akzeptiertes Primitiv
        enable_nurbs: bool = True    # NURBS-Fallback aktivieren
    ):
        """
        Args:
            tolerance: Maximaler Fitting-Fehler in mm
            min_confidence: Minimum Confidence (inlier_ratio) für Akzeptanz
            enable_nurbs: NURBS-Fitting als Fallback
        """
        self.tolerance = tolerance
        self.min_confidence = min_confidence
        self.enable_nurbs = enable_nurbs

    def fit_region(self, mesh: 'pv.PolyData', region: Region) -> Optional[DetectedPrimitive]:
        """
        Fittet das beste Primitiv auf eine Region.

        Args:
            mesh: Vollständiges Mesh
            region: Region-Objekt mit cell_ids

        Returns:
            DetectedPrimitive oder None
        """
        # Punkte der Region extrahieren
        region_mesh = mesh.extract_cells(region.cell_ids)
        points = region_mesh.points

        if len(points) < 4:
            return None

        # Normalen der Region
        if 'Normals' in region_mesh.point_data:
            normals = region_mesh.point_data['Normals']
        elif 'Normals' in region_mesh.cell_data:
            # Cell-Normals zu Point-Normals konvertieren (Durchschnitt)
            normals = self._cell_to_point_normals(region_mesh)
        else:
            region_mesh.compute_normals(point_normals=True, inplace=True)
            normals = region_mesh.point_data['Normals']

        # Versuche Primitive in Reihenfolge (schnellste/häufigste zuerst)
        best_primitive = None
        best_confidence = 0.0

        # 1. Plane Fitting (immer versuchen - sehr häufig)
        plane_result = self._fit_plane(points, normals, region)
        if plane_result and plane_result.confidence > best_confidence:
            best_primitive = plane_result
            best_confidence = plane_result.confidence

        # 2. Cylinder (nur wenn Plane nicht gut genug)
        if best_confidence < 0.95 and HAS_SKLEARN:
            cyl_result = self._fit_cylinder(points, normals, region)
            if cyl_result and cyl_result.confidence > best_confidence:
                best_primitive = cyl_result
                best_confidence = cyl_result.confidence

        # 3. Sphere
        if best_confidence < 0.95:
            sphere_result = self._fit_sphere(points, region)
            if sphere_result and sphere_result.confidence > best_confidence:
                best_primitive = sphere_result
                best_confidence = sphere_result.confidence

        # 4. Cone (komplexer, nur wenn andere fehlschlagen)
        if best_confidence < 0.9:
            cone_result = self._fit_cone(points, normals, region)
            if cone_result and cone_result.confidence > best_confidence:
                best_primitive = cone_result
                best_confidence = cone_result.confidence

        # 5. NURBS Fallback (wenn aktiviert und andere nicht gut genug)
        if best_confidence < self.min_confidence and self.enable_nurbs:
            try:
                from meshconverter.nurbs_fitter import NURBSFitter
                nurbs_fitter = NURBSFitter()
                nurbs_result = nurbs_fitter.fit(points, normals, region)
                if nurbs_result and nurbs_result.confidence > best_confidence:
                    best_primitive = nurbs_result
                    best_confidence = nurbs_result.confidence
            except ImportError:
                pass  # NURBS-Modul nicht verfügbar

        # Nur zurückgeben wenn Confidence > Threshold
        if best_primitive and best_primitive.confidence >= self.min_confidence:
            return best_primitive

        return None

    def _cell_to_point_normals(self, mesh: 'pv.PolyData') -> np.ndarray:
        """Konvertiert Cell-Normals zu Point-Normals."""
        cell_normals = mesh.cell_data['Normals']
        point_normals = np.zeros((mesh.n_points, 3))
        point_counts = np.zeros(mesh.n_points)

        faces = mesh.faces.reshape(-1, 4)[:, 1:4]
        for cell_id, face in enumerate(faces):
            for pt_id in face:
                point_normals[pt_id] += cell_normals[cell_id]
                point_counts[pt_id] += 1

        # Normalisieren
        point_counts[point_counts == 0] = 1
        point_normals = point_normals / point_counts[:, np.newaxis]
        norms = np.linalg.norm(point_normals, axis=1, keepdims=True)
        norms[norms < 1e-10] = 1
        return point_normals / norms

    # =========================================================================
    # Plane Fitting (SVD)
    # =========================================================================

    def _fit_plane(
        self,
        points: np.ndarray,
        normals: np.ndarray,
        region: Region
    ) -> Optional[DetectedPrimitive]:
        """
        Fittet Ebene via SVD.

        Methode:
        1. Centroid berechnen
        2. Punkte zentrieren
        3. SVD → kleinster Singulärwert gibt Normal
        """
        if len(points) < 3:
            return None

        try:
            centroid = np.mean(points, axis=0)
            centered = points - centroid

            # SVD: V[-1] ist die Richtung mit minimaler Varianz = Normal
            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            normal = Vt[-1]

            # Normal-Richtung an Region-Normal angleichen
            if np.dot(normal, region.normal) < 0:
                normal = -normal

            # Distanzen zur Ebene
            distances = np.abs(np.dot(centered, normal))
            error = np.mean(distances)
            inlier_ratio = np.mean(distances < self.tolerance)

            # Confidence basierend auf Fehler und Inlier-Ratio
            confidence = inlier_ratio * (1.0 - min(error / self.tolerance, 1.0))

            return DetectedPrimitive(
                type="plane",
                region_id=region.region_id,
                params={
                    'origin': centroid.tolist(),
                    'normal': normal.tolist()
                },
                boundary_points=region.boundary_points if region.boundary_points is not None else points,
                area=region.area,
                confidence=confidence,
                error=error
            )

        except Exception as e:
            logger.debug(f"Plane fitting fehlgeschlagen: {e}")
            return None

    # =========================================================================
    # Cylinder Fitting (PCA + Median)
    # =========================================================================

    def _fit_cylinder(
        self,
        points: np.ndarray,
        normals: np.ndarray,
        region: Region
    ) -> Optional[DetectedPrimitive]:
        """
        Fittet Zylinder via PCA auf Normalen + Median-Radius.

        Methode:
        1. PCA auf Normalen → Achse ist Richtung mit größter Varianz
        2. Punkte auf Achse projizieren
        3. Radius = Median der Abstände zur Achse
        """
        if len(points) < 10 or not HAS_SKLEARN:
            return None

        try:
            # Normalen normalisieren
            norm_lengths = np.linalg.norm(normals, axis=1, keepdims=True)
            norm_lengths[norm_lengths < 1e-10] = 1
            normals_normalized = normals / norm_lengths

            # PCA auf Normalen → Achse ist orthogonal zu allen Normalen
            # Bei Zylinder zeigen alle Normalen von der Achse weg
            # Die Achse ist die Richtung mit minimaler Varianz in den Normalen
            pca = PCA(n_components=3)
            pca.fit(normals_normalized)

            # Die letzte Komponente (kleinste Varianz) ist die Achsen-Richtung
            axis = pca.components_[-1]

            # Alternativ: Die Achse ist senkrecht zu den meisten Normalen
            # → Nimm die Richtung mit minimaler durchschnittlicher |dot| mit Normalen
            dots = np.abs(np.dot(normals_normalized, axis))
            if np.mean(dots) > 0.3:
                # Probiere andere Komponenten
                for i in range(3):
                    test_axis = pca.components_[i]
                    test_dots = np.abs(np.dot(normals_normalized, test_axis))
                    if np.mean(test_dots) < np.mean(dots):
                        axis = test_axis
                        dots = test_dots

            # Centroid als Punkt auf Achse
            centroid = np.mean(points, axis=0)

            # Abstände zur Achse
            # Projektion auf Achse
            proj_lengths = np.dot(points - centroid, axis)
            proj_points = centroid + proj_lengths[:, np.newaxis] * axis
            perpendicular = points - proj_points
            distances_to_axis = np.linalg.norm(perpendicular, axis=1)

            # Radius = Median (robust gegen Outliers)
            radius = np.median(distances_to_axis)

            if radius < 0.1:  # Zu klein
                return None

            # Fehler = Abweichung vom Radius
            radial_errors = np.abs(distances_to_axis - radius)
            error = np.mean(radial_errors)
            inlier_ratio = np.mean(radial_errors < self.tolerance)

            # Height aus Projektion
            height = np.max(proj_lengths) - np.min(proj_lengths)

            if height < 0.1:  # Zu flach
                return None

            # Center auf Achsen-Mitte verschieben
            center = centroid + (np.min(proj_lengths) + np.max(proj_lengths)) / 2 * axis

            confidence = inlier_ratio * (1.0 - min(error / self.tolerance, 1.0))

            # Nur akzeptieren wenn deutlich besser als Plane wäre
            if confidence < 0.5:
                return None

            return DetectedPrimitive(
                type="cylinder",
                region_id=region.region_id,
                params={
                    'center': center.tolist(),
                    'axis': axis.tolist(),
                    'radius': float(radius),
                    'height': float(height)
                },
                boundary_points=region.boundary_points if region.boundary_points is not None else points,
                area=region.area,
                confidence=confidence,
                error=error
            )

        except Exception as e:
            logger.debug(f"Cylinder fitting fehlgeschlagen: {e}")
            return None

    # =========================================================================
    # Sphere Fitting (Algebraisch)
    # =========================================================================

    def _fit_sphere(
        self,
        points: np.ndarray,
        region: Region
    ) -> Optional[DetectedPrimitive]:
        """
        Fittet Kugel via algebraischem Fit.

        Gleichung: (x-cx)² + (y-cy)² + (z-cz)² = r²
        Umgeformt: x² + y² + z² = 2*cx*x + 2*cy*y + 2*cz*z + (r² - cx² - cy² - cz²)
        """
        if len(points) < 4:
            return None

        try:
            # Least Squares Setup
            # A * [cx, cy, cz, d]^T = b
            # wobei d = r² - cx² - cy² - cz²
            A = np.column_stack([
                2 * points,
                np.ones(len(points))
            ])
            b = np.sum(points**2, axis=1)

            # Least Squares Lösung
            result, residuals, rank, s = np.linalg.lstsq(A, b, rcond=None)
            cx, cy, cz, d = result

            center = np.array([cx, cy, cz])
            radius_sq = d + cx**2 + cy**2 + cz**2

            if radius_sq <= 0:
                return None

            radius = np.sqrt(radius_sq)

            if radius < 0.1 or radius > 10000:  # Unrealistisch
                return None

            # Fehler berechnen
            distances = np.linalg.norm(points - center, axis=1)
            radial_errors = np.abs(distances - radius)
            error = np.mean(radial_errors)
            inlier_ratio = np.mean(radial_errors < self.tolerance)

            confidence = inlier_ratio * (1.0 - min(error / self.tolerance, 1.0))

            # Nur akzeptieren wenn Fehler klein genug
            if confidence < 0.5:
                return None

            return DetectedPrimitive(
                type="sphere",
                region_id=region.region_id,
                params={
                    'center': center.tolist(),
                    'radius': float(radius)
                },
                boundary_points=region.boundary_points if region.boundary_points is not None else points,
                area=region.area,
                confidence=confidence,
                error=error
            )

        except Exception as e:
            logger.debug(f"Sphere fitting fehlgeschlagen: {e}")
            return None

    # =========================================================================
    # Cone Fitting (Iterativ)
    # =========================================================================

    def _fit_cone(
        self,
        points: np.ndarray,
        normals: np.ndarray,
        region: Region
    ) -> Optional[DetectedPrimitive]:
        """
        Fittet Kegel via iterativer Apex-Suche.

        Methode:
        1. Initiale Achse aus Normalen-Verteilung
        2. Apex als Schnittpunkt der Normalen-Linien
        3. Iterative Verfeinerung
        """
        if len(points) < 10:
            return None

        try:
            # Normalen normalisieren
            norm_lengths = np.linalg.norm(normals, axis=1, keepdims=True)
            norm_lengths[norm_lengths < 1e-10] = 1
            normals_normalized = normals / norm_lengths

            centroid = np.mean(points, axis=0)

            # Initiale Achse: Durchschnittliche Richtung vom Centroid zu Punkten
            directions = points - centroid
            dir_lengths = np.linalg.norm(directions, axis=1, keepdims=True)
            dir_lengths[dir_lengths < 1e-10] = 1
            directions_normalized = directions / dir_lengths

            # PCA auf Richtungen → Hauptachse
            if HAS_SKLEARN:
                pca = PCA(n_components=1)
                pca.fit(directions_normalized)
                axis = pca.components_[0]
            else:
                # Fallback: Durchschnitt
                axis = np.mean(directions_normalized, axis=0)
                axis = axis / (np.linalg.norm(axis) + 1e-10)

            # Apex-Schätzung: Normalen-Linien schneiden
            # Für jeden Punkt: Linie = point + t * normal
            # Suche t wo Linien sich am nächsten kommen

            # Vereinfacht: Projiziere auf Achse und finde Apex
            proj_lengths = np.dot(points - centroid, axis)

            # Bei Kegel: Radius proportional zu Projektion
            # Berechne lokalen Radius
            proj_points = centroid + proj_lengths[:, np.newaxis] * axis
            perpendicular = points - proj_points
            local_radii = np.linalg.norm(perpendicular, axis=1)

            # Lineare Regression: radius = slope * proj_length + intercept
            # Bei Kegel mit Apex: intercept ≈ 0 am Apex
            if len(np.unique(proj_lengths)) < 2:
                return None

            # Least Squares für Kegel-Parameter
            A = np.column_stack([proj_lengths, np.ones(len(proj_lengths))])
            slope_intercept, _, _, _ = np.linalg.lstsq(A, local_radii, rcond=None)
            slope, intercept = slope_intercept

            if abs(slope) < 0.01:  # Fast kein Kegel (eher Zylinder)
                return None

            # Apex: wo radius = 0 → proj_length = -intercept / slope
            apex_proj = -intercept / slope
            apex = centroid + apex_proj * axis

            # Halber Öffnungswinkel
            half_angle = np.arctan(abs(slope))

            if half_angle < np.radians(1) or half_angle > np.radians(89):
                return None  # Unrealistisch

            # Fehler berechnen
            expected_radii = np.abs(slope * proj_lengths + intercept)
            radial_errors = np.abs(local_radii - expected_radii)
            error = np.mean(radial_errors)
            inlier_ratio = np.mean(radial_errors < self.tolerance)

            confidence = inlier_ratio * (1.0 - min(error / self.tolerance, 1.0))

            if confidence < 0.5:
                return None

            # Height
            height = np.max(proj_lengths) - np.min(proj_lengths)

            return DetectedPrimitive(
                type="cone",
                region_id=region.region_id,
                params={
                    'apex': apex.tolist(),
                    'axis': axis.tolist(),
                    'half_angle': float(half_angle),
                    'height': float(height)
                },
                boundary_points=region.boundary_points if region.boundary_points is not None else points,
                area=region.area,
                confidence=confidence,
                error=error
            )

        except Exception as e:
            logger.debug(f"Cone fitting fehlgeschlagen: {e}")
            return None
