"""
MashCad - NURBS Fitter
======================

Fittet B-Spline Surfaces auf organische Regionen, die nicht zu
geometrischen Primitiven passen.
"""

import numpy as np
from typing import Optional, Tuple
from loguru import logger

try:
    from sklearn.decomposition import PCA
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

try:
    from OCP.gp import gp_Pnt
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
    from OCP.GeomAbs import GeomAbs_C0, GeomAbs_C1, GeomAbs_C2, GeomAbs_C3
    from OCP.Geom import Geom_BSplineSurface
    HAS_OCP = True
except ImportError:
    HAS_OCP = False
    logger.warning("OCP nicht verfügbar für NURBS Fitting")

from meshconverter.mesh_converter_v10 import Region, DetectedPrimitive


class NURBSFitter:
    """
    Fittet B-Spline Surfaces auf organische Mesh-Regionen.

    Verwendet GeomAPI_PointsToBSplineSurface für das Fitting.
    """

    def __init__(
        self,
        min_degree: int = 3,        # Minimum B-Spline Grad
        max_degree: int = 8,        # Maximum B-Spline Grad
        continuity: str = "C2",     # Kontinuität (C0, C1, C2, C3)
        tolerance: float = 0.1      # Fitting-Toleranz in mm
    ):
        """
        Args:
            min_degree: Minimum Polynomgrad
            max_degree: Maximum Polynomgrad
            continuity: Gewünschte Kontinuität
            tolerance: Fitting-Toleranz
        """
        self.min_degree = min_degree
        self.max_degree = max_degree
        self.continuity = continuity
        self.tolerance = tolerance

    def fit(
        self,
        points: np.ndarray,
        normals: np.ndarray,
        region: Region
    ) -> Optional[DetectedPrimitive]:
        """
        Fittet B-Spline Surface auf Punktwolke.

        Args:
            points: 3D Punkte (N, 3)
            normals: Punkt-Normalen (N, 3)
            region: Region-Objekt

        Returns:
            DetectedPrimitive mit B-Spline Surface oder None
        """
        if not HAS_OCP:
            logger.warning("OCP nicht verfügbar für NURBS Fitting")
            return None

        if not HAS_SKLEARN:
            logger.warning("sklearn nicht verfügbar für NURBS Fitting")
            return None

        if len(points) < 9:  # Minimum für 3x3 Grid
            return None

        try:
            # 1. Punkte auf reguläres Grid projizieren
            grid_size = self._compute_grid_size(len(points))
            grid_points = self._project_to_grid(points, normals, grid_size)

            if grid_points is None:
                return None

            # 2. TColgp_Array2OfPnt erstellen
            pnt_array = self._create_point_array(grid_points, grid_size)

            if pnt_array is None:
                return None

            # 3. B-Spline fitten
            surface = self._fit_bspline(pnt_array)

            if surface is None:
                return None

            # 4. Fehler berechnen
            error = self._compute_fitting_error(points, surface)
            confidence = max(0.0, 1.0 - error / self.tolerance)

            logger.debug(f"NURBS Fit: error={error:.3f}mm, confidence={confidence:.2f}")

            return DetectedPrimitive(
                type="bspline",
                region_id=region.region_id,
                params={
                    'surface': surface,
                    'grid_size': grid_size
                },
                boundary_points=region.boundary_points if region.boundary_points is not None else points,
                area=region.area,
                confidence=confidence,
                error=error
            )

        except Exception as e:
            logger.debug(f"NURBS Fitting fehlgeschlagen: {e}")
            return None

    def _compute_grid_size(self, n_points: int) -> int:
        """
        Berechnet optimale Grid-Größe basierend auf Punktanzahl.
        """
        # Ziel: Grid mit ähnlich vielen Punkten wie Original
        # grid_size² ≈ n_points
        grid_size = int(np.sqrt(n_points))

        # Minimum 3, Maximum 50
        grid_size = max(3, min(grid_size, 50))

        return grid_size

    def _project_to_grid(
        self,
        points: np.ndarray,
        normals: np.ndarray,
        grid_size: int
    ) -> Optional[np.ndarray]:
        """
        Projiziert unstrukturierte Punkte auf reguläres Grid.

        Verwendet PCA für lokales Koordinatensystem.
        """
        if len(points) < grid_size * grid_size:
            # Nicht genug Punkte - reduziere Grid
            grid_size = int(np.sqrt(len(points)))
            if grid_size < 3:
                return None

        try:
            # PCA für 2D Parametrisierung
            pca = PCA(n_components=2)
            uv = pca.fit_transform(points)

            # UV-Bounds
            u_min, u_max = uv[:, 0].min(), uv[:, 0].max()
            v_min, v_max = uv[:, 1].min(), uv[:, 1].max()

            # Verhindere Division durch Null
            u_range = u_max - u_min
            v_range = v_max - v_min

            if u_range < 1e-10 or v_range < 1e-10:
                return None

            # Grid erstellen
            grid = np.zeros((grid_size, grid_size, 3))

            for i in range(grid_size):
                for j in range(grid_size):
                    # Ziel-UV
                    u = u_min + u_range * i / (grid_size - 1)
                    v = v_min + v_range * j / (grid_size - 1)

                    # Nächsten Punkt finden (gewichteter Durchschnitt)
                    distances = np.sqrt((uv[:, 0] - u)**2 + (uv[:, 1] - v)**2)

                    # IDW (Inverse Distance Weighting) für glatteres Ergebnis
                    weights = 1.0 / (distances + 1e-10)**2

                    # Top-k Nachbarn für Performance
                    k = min(10, len(points))
                    top_k_idx = np.argpartition(distances, k)[:k]

                    weighted_point = np.average(
                        points[top_k_idx],
                        weights=weights[top_k_idx],
                        axis=0
                    )

                    grid[i, j] = weighted_point

            return grid

        except Exception as e:
            logger.debug(f"Grid-Projektion fehlgeschlagen: {e}")
            return None

    def _create_point_array(
        self,
        grid: np.ndarray,
        grid_size: int
    ) -> Optional['TColgp_Array2OfPnt']:
        """
        Erstellt TColgp_Array2OfPnt aus Grid.
        """
        try:
            # OCP Arrays sind 1-basiert
            pnt_array = TColgp_Array2OfPnt(1, grid_size, 1, grid_size)

            for i in range(grid_size):
                for j in range(grid_size):
                    pt = grid[i, j]
                    pnt_array.SetValue(
                        i + 1, j + 1,
                        gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2]))
                    )

            return pnt_array

        except Exception as e:
            logger.debug(f"Point Array Erstellung fehlgeschlagen: {e}")
            return None

    def _fit_bspline(
        self,
        pnt_array: 'TColgp_Array2OfPnt'
    ) -> Optional['Geom_BSplineSurface']:
        """
        Fittet B-Spline Surface auf Punktarray.
        """
        try:
            # Kontinuität - muss OCP Enum sein, nicht Integer!
            continuity_map = {
                "C0": GeomAbs_C0,
                "C1": GeomAbs_C1,
                "C2": GeomAbs_C2,
                "C3": GeomAbs_C3
            }
            cont = continuity_map.get(self.continuity, GeomAbs_C2)

            # B-Spline Fitting
            fitter = GeomAPI_PointsToBSplineSurface(
                pnt_array,
                self.min_degree,
                self.max_degree,
                cont,
                self.tolerance
            )

            if fitter.IsDone():
                return fitter.Surface()
            else:
                logger.debug("GeomAPI_PointsToBSplineSurface nicht erfolgreich")
                return None

        except Exception as e:
            logger.debug(f"B-Spline Fitting fehlgeschlagen: {e}")
            return None

    def _compute_fitting_error(
        self,
        points: np.ndarray,
        surface: 'Geom_BSplineSurface'
    ) -> float:
        """
        Berechnet durchschnittlichen Abstand der Punkte zur Surface.
        """
        try:
            from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf

            errors = []
            # Sample für Performance
            sample_size = min(100, len(points))
            sample_idx = np.random.choice(len(points), sample_size, replace=False)

            for idx in sample_idx:
                pt = points[idx]
                gp_pt = gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2]))

                projector = GeomAPI_ProjectPointOnSurf(gp_pt, surface)

                if projector.NbPoints() > 0:
                    nearest = projector.NearestPoint()
                    dist = gp_pt.Distance(nearest)
                    errors.append(dist)

            if errors:
                return np.mean(errors)
            else:
                return float('inf')

        except Exception as e:
            logger.debug(f"Fehlerberechnung fehlgeschlagen: {e}")
            return float('inf')
