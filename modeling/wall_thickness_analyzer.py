"""
MashCad - Wall Thickness Analyzer
Identifies thin walls by offsetting the solid inward and checking for intersections.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from loguru import logger


@dataclass
class ThicknessResult:
    """Result of wall thickness analysis."""
    min_thickness: float = 0.0
    thin_face_indices: List[int] = field(default_factory=list)
    face_thicknesses: List[float] = field(default_factory=list)
    total_faces: int = 0
    ok: bool = True
    message: str = ""


class WallThicknessAnalyzer:
    """
    Analyzes wall thickness by raycasting from face centers inward.

    Strategy: For each face, cast a ray from the center along the inward normal.
    Measure the distance to the opposite wall. If < threshold → thin.
    """

    @staticmethod
    def analyze(solid, min_thickness: float = 0.8) -> ThicknessResult:
        """
        Analyze wall thickness of a solid.

        Args:
            solid: Build123d Solid
            min_thickness: Minimum acceptable wall thickness in mm

        Returns:
            ThicknessResult with per-face thickness info
        """
        result = ThicknessResult()

        try:
            from OCP.BRepClass3d import BRepClass3d_SolidClassifier
            from OCP.BRepGProp import BRepGProp_Face
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE
            from OCP.gp import gp_Pnt, gp_Lin, gp_Dir, gp_Vec
            from OCP.BRepIntCurveSurface import BRepIntCurveSurface_Inter
            from OCP.GProp import GProp_GProps

            shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

            # Iterate over all faces
            explorer = TopExp_Explorer(shape, TopAbs_FACE)
            face_idx = 0
            min_found = float('inf')

            while explorer.More():
                face = explorer.Current()

                try:
                    # Get face center and normal
                    props = BRepGProp_Face(face)
                    bounds = [0.0, 0.0, 0.0, 0.0]
                    props.Bounds(bounds[0], bounds[1], bounds[2], bounds[3])
                    # Use mid-parameter point
                    u_mid = (bounds[0] + bounds[1]) / 2.0
                    v_mid = (bounds[2] + bounds[3]) / 2.0

                    pnt = gp_Pnt()
                    normal_vec = gp_Vec()
                    props.Normal(u_mid, v_mid, pnt, normal_vec)

                    if normal_vec.Magnitude() < 1e-10:
                        result.face_thicknesses.append(float('inf'))
                        explorer.Next()
                        face_idx += 1
                        continue

                    # Inward normal = -normal
                    inward = gp_Dir(-normal_vec.X(), -normal_vec.Y(), -normal_vec.Z())

                    # Offset start point slightly along inward to avoid self-intersection
                    start = gp_Pnt(
                        pnt.X() + inward.X() * 0.001,
                        pnt.Y() + inward.Y() * 0.001,
                        pnt.Z() + inward.Z() * 0.001
                    )

                    # Ray-cast through the solid
                    line = gp_Lin(start, inward)
                    inter = BRepIntCurveSurface_Inter()
                    inter.Init(shape, line, 1e-6)

                    thickness = float('inf')
                    while inter.More():
                        hit_pnt = inter.Pnt()
                        dist = start.Distance(hit_pnt)
                        if dist > 0.01:  # Skip near-zero hits (same face)
                            thickness = min(thickness, dist)
                            break
                        inter.Next()

                    result.face_thicknesses.append(thickness)
                    if thickness < min_found:
                        min_found = thickness
                    if thickness < min_thickness:
                        result.thin_face_indices.append(face_idx)

                except Exception as e:
                    logger.debug(f"Face {face_idx} analysis failed: {e}")
                    result.face_thicknesses.append(float('inf'))

                explorer.Next()
                face_idx += 1

            result.total_faces = face_idx
            result.min_thickness = min_found if min_found != float('inf') else 0.0
            result.ok = len(result.thin_face_indices) == 0

            if result.ok:
                result.message = f"All {face_idx} faces OK (min: {result.min_thickness:.2f}mm)"
            else:
                result.message = (
                    f"{len(result.thin_face_indices)} of {face_idx} faces below "
                    f"{min_thickness}mm (min: {result.min_thickness:.2f}mm)"
                )

            logger.info(f"Wall thickness analysis: {result.message}")
            return result

        except ImportError as e:
            result.message = f"OCP modules not available: {e}"
            logger.error(result.message)
            return result
        except Exception as e:
            result.message = f"Analysis failed: {e}"
            logger.error(result.message)
            return result
