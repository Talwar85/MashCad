"""
MashCad - Wall Thickness Analyzer (Phase 13)
=============================================

Professionelle Wandstärken-Analyse mittels BRepExtrema/Ray-Casting.

Funktionalität:
- Berechnet minimale Wandstärken an Sample-Punkten
- Identifiziert kritisch dünne Bereiche
- Liefert Daten für Visualisierung (Farbskala)
- Multi-Sample pro Fläche für genauere Analyse

Author: Claude (Phase 13 Performance)
Date: 2026-02
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
from enum import Enum, auto
from loguru import logger
import numpy as np


class ThicknessStatus(Enum):
    """Status der Wandstärke an einem Punkt."""
    OK = auto()           # Wandstärke ausreichend
    WARNING = auto()      # Knapp unter Empfehlung
    CRITICAL = auto()     # Zu dünn für Fertigung
    UNKNOWN = auto()      # Konnte nicht berechnet werden


@dataclass
class ThicknessPoint:
    """Ein Sample-Punkt mit Wandstärken-Information."""
    position: Tuple[float, float, float]
    normal: Tuple[float, float, float]
    thickness: float
    face_index: int = -1
    status: ThicknessStatus = ThicknessStatus.OK


@dataclass
class ThicknessResult:
    """Result of wall thickness analysis."""
    min_thickness: float = 0.0
    max_thickness: float = 0.0
    avg_thickness: float = 0.0
    thin_face_indices: List[int] = field(default_factory=list)
    face_thicknesses: List[float] = field(default_factory=list)
    total_faces: int = 0
    ok: bool = True
    message: str = ""

    # Phase 13: Erweiterte Daten
    sample_points: List[ThicknessPoint] = field(default_factory=list)
    critical_points: List[ThicknessPoint] = field(default_factory=list)
    warning_points: List[ThicknessPoint] = field(default_factory=list)
    analysis_time_ms: float = 0.0

    # Thresholds
    critical_threshold: float = 0.8
    warning_threshold: float = 1.5

    def get_color_for_thickness(self, thickness: float) -> Tuple[float, float, float]:
        """
        Gibt RGB-Farbe für Wandstärke zurück (für Visualisierung).
        Rot = dünn, Gelb = mittel, Grün = dick
        """
        if thickness <= 0:
            return (0.5, 0.5, 0.5)  # Grau für ungültig

        t_min = self.critical_threshold
        t_max = self.warning_threshold * 2

        normalized = (thickness - t_min) / (t_max - t_min) if t_max > t_min else 0
        normalized = max(0.0, min(1.0, normalized))

        if normalized < 0.5:
            r, g, b = 1.0, normalized * 2, 0.0
        else:
            r, g, b = 1.0 - (normalized - 0.5) * 2, 1.0, 0.0

        return (r, g, b)

    def get_heatmap_data(self) -> Dict[str, Any]:
        """Daten für Heatmap-Visualisierung."""
        points, colors, thicknesses = [], [], []
        for sample in self.sample_points:
            if sample.thickness > 0:
                points.append(sample.position)
                colors.append(self.get_color_for_thickness(sample.thickness))
                thicknesses.append(sample.thickness)
        return {
            "points": points,
            "colors": colors,
            "thicknesses": thicknesses,
            "min": self.min_thickness,
            "max": self.max_thickness,
            "avg": self.avg_thickness,
        }


class WallThicknessAnalyzer:
    """
    Analyzes wall thickness by raycasting from face centers inward.

    Strategy: For each face, cast rays from sample points along the inward normal.
    Measure the distance to the opposite wall. If < threshold → thin.

    Phase 13 Enhancements:
    - Multi-sample per face for more accurate analysis
    - Critical/Warning classification
    - Heatmap data generation
    """

    @staticmethod
    def analyze(solid, min_thickness: float = 0.8,
                warning_threshold: float = 1.5,
                samples_per_face: int = 1) -> ThicknessResult:
        """
        Analyze wall thickness of a solid.

        Args:
            solid: Build123d Solid
            min_thickness: Minimum acceptable wall thickness in mm (critical threshold)
            warning_threshold: Threshold for warning classification
            samples_per_face: Number of sample points per face (1 = center only)

        Returns:
            ThicknessResult with per-face thickness info and sample points
        """
        import time
        start_time = time.perf_counter()

        result = ThicknessResult()
        result.critical_threshold = min_thickness
        result.warning_threshold = warning_threshold

        try:
            from OCP.BRepClass3d import BRepClass3d_SolidClassifier
            from OCP.BRepGProp import BRepGProp_Face
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
            from OCP.gp import gp_Pnt, gp_Lin, gp_Dir, gp_Vec
            from OCP.BRepIntCurveSurface import BRepIntCurveSurface_Inter
            from OCP.GProp import GProp_GProps
            from OCP.BRepAdaptor import BRepAdaptor_Surface
            from OCP.BRepLProp import BRepLProp_SLProps
            from OCP.TopoDS import TopoDS

            shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

            # Iterate over all faces
            explorer = TopExp_Explorer(shape, TopAbs_FACE)
            face_idx = 0
            min_found = float('inf')
            max_found = 0.0
            all_thicknesses = []

            while explorer.More():
                face = TopoDS.Face_s(explorer.Current())

                try:
                    # Multi-sample approach
                    face_samples = WallThicknessAnalyzer._sample_face(
                        face, face_idx, samples_per_face
                    )

                    face_min_thickness = float('inf')

                    for sample_pos, sample_normal in face_samples:
                        thickness = WallThicknessAnalyzer._measure_ray(
                            shape, sample_pos, sample_normal
                        )

                        if thickness is not None and thickness > 0:
                            all_thicknesses.append(thickness)

                            if thickness < face_min_thickness:
                                face_min_thickness = thickness

                            # Create sample point
                            status = ThicknessStatus.OK
                            if thickness < min_thickness:
                                status = ThicknessStatus.CRITICAL
                            elif thickness < warning_threshold:
                                status = ThicknessStatus.WARNING

                            point = ThicknessPoint(
                                position=sample_pos,
                                normal=sample_normal,
                                thickness=thickness,
                                face_index=face_idx,
                                status=status
                            )
                            result.sample_points.append(point)

                            if status == ThicknessStatus.CRITICAL:
                                result.critical_points.append(point)
                            elif status == ThicknessStatus.WARNING:
                                result.warning_points.append(point)

                    result.face_thicknesses.append(face_min_thickness)

                    if face_min_thickness < float('inf'):
                        if face_min_thickness < min_found:
                            min_found = face_min_thickness
                        if face_min_thickness > max_found:
                            max_found = face_min_thickness
                        if face_min_thickness < min_thickness:
                            result.thin_face_indices.append(face_idx)

                except Exception as e:
                    logger.debug(f"Face {face_idx} analysis failed: {e}")
                    result.face_thicknesses.append(float('inf'))

                explorer.Next()
                face_idx += 1

            result.total_faces = face_idx
            result.min_thickness = min_found if min_found != float('inf') else 0.0
            result.max_thickness = max_found if max_found > 0 else 0.0
            result.avg_thickness = np.mean(all_thicknesses) if all_thicknesses else 0.0
            result.ok = len(result.thin_face_indices) == 0
            result.analysis_time_ms = (time.perf_counter() - start_time) * 1000

            if result.ok:
                result.message = f"All {face_idx} faces OK (min: {result.min_thickness:.2f}mm)"
            else:
                result.message = (
                    f"{len(result.thin_face_indices)} of {face_idx} faces below "
                    f"{min_thickness}mm (min: {result.min_thickness:.2f}mm)"
                )

            logger.info(f"Wall thickness analysis: {result.message} [{result.analysis_time_ms:.0f}ms]")
            return result

        except ImportError as e:
            result.message = f"OCP modules not available: {e}"
            logger.error(result.message)
            return result
        except Exception as e:
            result.message = f"Analysis failed: {e}"
            logger.error(result.message)
            import traceback
            traceback.print_exc()
            return result

    @staticmethod
    def _sample_face(face, face_idx: int, samples_per_face: int) -> List[Tuple]:
        """
        Generiert Sample-Punkte auf einer Fläche.

        Returns:
            List of (position_tuple, normal_tuple)
        """
        samples = []

        try:
            from OCP.BRepAdaptor import BRepAdaptor_Surface
            from OCP.BRepLProp import BRepLProp_SLProps
            from OCP.TopAbs import TopAbs_REVERSED

            adaptor = BRepAdaptor_Surface(face)

            u_min = adaptor.FirstUParameter()
            u_max = adaptor.LastUParameter()
            v_min = adaptor.FirstVParameter()
            v_max = adaptor.LastVParameter()

            # Grid size
            grid_size = max(1, int(np.sqrt(samples_per_face)))

            for i in range(grid_size):
                for j in range(grid_size):
                    u = u_min + (u_max - u_min) * (i + 0.5) / grid_size
                    v = v_min + (v_max - v_min) * (j + 0.5) / grid_size

                    try:
                        pnt = adaptor.Value(u, v)
                        slprops = BRepLProp_SLProps(adaptor, u, v, 1, 0.01)

                        if slprops.IsNormalDefined():
                            normal = slprops.Normal()

                            # Face orientation
                            if face.Orientation() == TopAbs_REVERSED:
                                normal = normal.Reversed()

                            samples.append((
                                (pnt.X(), pnt.Y(), pnt.Z()),
                                (normal.X(), normal.Y(), normal.Z())
                            ))
                    except Exception:
                        continue

        except Exception as e:
            logger.debug(f"Face sampling error: {e}")

        # Fallback to center if no samples
        if not samples:
            try:
                from OCP.BRepGProp import BRepGProp_Face
                from OCP.gp import gp_Pnt, gp_Vec

                props = BRepGProp_Face(face)
                bounds = [0.0, 0.0, 0.0, 0.0]
                props.Bounds(bounds[0], bounds[1], bounds[2], bounds[3])
                u_mid = (bounds[0] + bounds[1]) / 2.0
                v_mid = (bounds[2] + bounds[3]) / 2.0

                pnt = gp_Pnt()
                normal_vec = gp_Vec()
                props.Normal(u_mid, v_mid, pnt, normal_vec)

                if normal_vec.Magnitude() > 1e-10:
                    normal_vec.Normalize()
                    samples.append((
                        (pnt.X(), pnt.Y(), pnt.Z()),
                        (normal_vec.X(), normal_vec.Y(), normal_vec.Z())
                    ))
            except Exception:
                pass

        return samples

    @staticmethod
    def _measure_ray(shape, position: Tuple, normal: Tuple) -> Optional[float]:
        """
        Misst Wandstärke durch Ray-Casting in Richtung -Normal.

        Returns:
            Thickness in mm or None
        """
        try:
            from OCP.gp import gp_Pnt, gp_Lin, gp_Dir
            from OCP.BRepIntCurveSurface import BRepIntCurveSurface_Inter

            offset = 0.01  # 10µm offset to avoid self-intersection
            start = gp_Pnt(
                position[0] - normal[0] * offset,
                position[1] - normal[1] * offset,
                position[2] - normal[2] * offset
            )

            inward = gp_Dir(-normal[0], -normal[1], -normal[2])
            line = gp_Lin(start, inward)

            inter = BRepIntCurveSurface_Inter()
            inter.Init(shape, line, 1e-6)

            min_distance = float('inf')
            while inter.More():
                w = inter.W()
                if w > offset * 2 and w < 1000.0:  # Valid range
                    if w < min_distance:
                        min_distance = w
                inter.Next()

            return min_distance if min_distance < float('inf') else None

        except Exception as e:
            logger.debug(f"Ray measurement error: {e}")
            return None

    @staticmethod
    def analyze_detailed(solid, min_thickness: float = 0.8,
                         warning_threshold: float = 1.5) -> ThicknessResult:
        """
        Detaillierte Analyse mit mehr Sample-Punkten pro Fläche.

        Für genaue Analyse und Heatmap-Visualisierung.
        """
        return WallThicknessAnalyzer.analyze(
            solid,
            min_thickness=min_thickness,
            warning_threshold=warning_threshold,
            samples_per_face=9  # 3x3 Grid
        )

    @staticmethod
    def quick_check(solid, threshold: float = 1.0) -> Tuple[bool, float]:
        """
        Schnelle Prüfung ob Wandstärken über Threshold.

        Returns:
            (passed, min_thickness)
        """
        result = WallThicknessAnalyzer.analyze(solid, threshold, samples_per_face=1)
        return result.ok, result.min_thickness
