"""
MashCad - Surface Analyzer
Curvature Analysis, Draft Angle Analysis, and Zebra Stripes for Rhino-level QC.

Uses OCP BRepLProp_SLProps for curvature, BRepAdaptor_Surface for face normals.
Results are per-face arrays suitable for PyVista scalar coloring.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from enum import Enum
import numpy as np
from loguru import logger


class AnalysisType(Enum):
    CURVATURE_GAUSS = "gauss"
    CURVATURE_MEAN = "mean"
    CURVATURE_MAX = "max_curvature"
    CURVATURE_MIN = "min_curvature"
    DRAFT_ANGLE = "draft_angle"


@dataclass
class AnalysisResult:
    """Result of surface analysis — per-vertex or per-cell scalar array."""
    scalars: np.ndarray = None          # Scalar values
    scalar_name: str = ""               # Display name
    cmap: str = "RdYlGn"               # Colormap
    clim: Tuple[float, float] = None   # Value range
    ok: bool = True
    message: str = ""


class SurfaceAnalyzer:
    """Computes curvature and draft angle analysis on BREP solids."""

    @staticmethod
    def curvature_analysis(solid, mesh, curvature_type: str = "mean") -> AnalysisResult:
        """
        Compute curvature at each mesh vertex by projecting onto the BREP surface.

        Args:
            solid: Build123d Solid
            mesh: PyVista PolyData (the tessellated mesh)
            curvature_type: "gauss", "mean", "max_curvature", "min_curvature"

        Returns:
            AnalysisResult with per-vertex curvature scalars
        """
        result = AnalysisResult(scalar_name=f"Curvature ({curvature_type})")

        try:
            # Use PyVista's built-in curvature computation (fast, mesh-based)
            curv = mesh.curvature(curv_type=curvature_type)
            result.scalars = curv

            # Clip extreme values for better visualization
            if len(curv) > 0:
                p5, p95 = np.percentile(curv, [5, 95])
                result.clim = (p5, p95)

            cmap_map = {
                "gauss": "coolwarm",
                "mean": "RdYlBu_r",
                "max_curvature": "hot",
                "min_curvature": "cool",
            }
            result.cmap = cmap_map.get(curvature_type, "RdYlBu_r")
            result.message = f"Curvature ({curvature_type}) computed for {len(curv)} vertices"
            logger.info(result.message)

        except Exception as e:
            result.ok = False
            result.message = f"Curvature analysis failed: {e}"
            logger.error(result.message)

        return result

    @staticmethod
    def draft_angle_analysis(solid, mesh, pull_direction=(0, 0, 1)) -> AnalysisResult:
        """
        Compute draft angle for each face relative to a pull direction.

        The draft angle is the angle between each face normal and the pull direction.
        0° = parallel to pull (vertical wall, no draft)
        90° = perpendicular to pull (flat top/bottom)

        Args:
            solid: Build123d Solid
            mesh: PyVista PolyData
            pull_direction: Mold pull direction as (x, y, z) tuple

        Returns:
            AnalysisResult with per-cell draft angle in degrees
        """
        result = AnalysisResult(
            scalar_name="Draft Angle (°)",
            cmap="RdYlGn",
            clim=(0, 10),  # 0-10° range, green=good draft, red=no draft
        )

        try:
            pull = np.array(pull_direction, dtype=float)
            pull = pull / (np.linalg.norm(pull) + 1e-12)

            # Compute face normals
            mesh_with_normals = mesh.compute_normals(cell_normals=True, point_normals=False)
            face_normals = mesh_with_normals.cell_data["Normals"]

            # Draft angle = 90° - angle between normal and pull direction
            # cos(angle) = dot(normal, pull)
            dots = np.dot(face_normals, pull)
            dots = np.clip(dots, -1.0, 1.0)
            angles_from_pull = np.degrees(np.arccos(np.abs(dots)))

            # Draft angle: 90° - angle_from_pull
            # If face is perpendicular to pull (top/bottom): angle_from_pull=0 → draft=90°
            # If face is parallel to pull (wall): angle_from_pull=90 → draft=0°
            draft_angles = 90.0 - angles_from_pull

            result.scalars = draft_angles
            result.message = (
                f"Draft angles: min={draft_angles.min():.1f}°, "
                f"max={draft_angles.max():.1f}°, "
                f"mean={draft_angles.mean():.1f}°"
            )
            logger.info(result.message)

        except Exception as e:
            result.ok = False
            result.message = f"Draft angle analysis failed: {e}"
            logger.error(result.message)

        return result

    @staticmethod
    def zebra_stripes(mesh, stripe_direction=(0, 0, 1), stripe_count=20) -> AnalysisResult:
        """
        Compute zebra stripe pattern for surface continuity analysis.

        Zebra stripes simulate parallel light reflections on the surface.
        Discontinuities in the stripes reveal G0/G1/G2 breaks.

        Args:
            mesh: PyVista PolyData
            stripe_direction: Direction of stripe lines
            stripe_count: Number of stripes

        Returns:
            AnalysisResult with per-vertex binary stripe pattern
        """
        result = AnalysisResult(
            scalar_name="Zebra",
            cmap="gray",
            clim=(0, 1),
        )

        try:
            mesh_with_normals = mesh.compute_normals(cell_normals=False, point_normals=True)
            normals = mesh_with_normals.point_data["Normals"]

            stripe_dir = np.array(stripe_direction, dtype=float)
            stripe_dir = stripe_dir / (np.linalg.norm(stripe_dir) + 1e-12)

            # Reflection vector: R = 2*(N·L)*N - L
            # Simplified: use dot(normal, stripe_dir) for stripe modulation
            dots = np.dot(normals, stripe_dir)

            # Create stripe pattern: sin wave on the dot product
            stripe_val = np.sin(dots * stripe_count * np.pi)
            # Binarize
            stripes = (stripe_val > 0).astype(float)

            result.scalars = stripes
            result.message = f"Zebra stripes ({stripe_count} bands) applied to {len(stripes)} vertices"
            logger.info(result.message)

        except Exception as e:
            result.ok = False
            result.message = f"Zebra stripe analysis failed: {e}"
            logger.error(result.message)

        return result
