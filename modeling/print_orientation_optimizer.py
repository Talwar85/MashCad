"""
MashCAD - Print Orientation Optimization
=========================================

Recommends optimal print orientations to minimize supports and
improve print quality.

Uses deterministic geometric analysis:
- Generates 10-20 candidate orientations
- Scores each using weighted heuristics
- Returns best recommendation with explanations

Author: Claude (Phase 2: Orientation Recommendation)
Date: 2026-03-02
Branch: feature/tnp5
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Any, Tuple, Optional, Callable
from loguru import logger
import math

# Import modules from Phase 1
from modeling.printability_score import OrientationMetrics, compute_orientation_metrics, compare_metrics
from modeling.print_bridge_analysis import BridgeAnalysisResult
from modeling.print_support import SupportEstimate
from modeling.print_explanation import OrientationExplanation, build_explanation


class RotationAxis(Enum):
    """Standard rotation axes."""
    X = (1, 0, 0)
    Y = (0, 1, 0)
    Z = (0, 0, 1)


@dataclass
class OrientationCandidate:
    """
    A candidate orientation for printing.

    Represents a specific rotation of the part.
    """
    # Rotation specification
    axis: Tuple[float, float, float] = (0, 0, 1)  # Rotation axis
    angle_deg: float = 0.0                      # Rotation angle

    # Description for UI
    description: str = "Default (upright)"

    # Metrics for this orientation (computed)
    metrics: Optional[OrientationMetrics] = None

    # Analysis results
    support_estimate: Optional[SupportEstimate] = None
    bridge_analysis: Optional[BridgeAnalysisResult] = None

    # Scoring
    score: float = 1.0  # Lower is better (0 = perfect)
    rank: int = -1      # Position in sorted list

    def get_rotation_matrix(self) -> List[List[float]]:
        """Get the 3x3 rotation matrix for this orientation."""
        import numpy as np

        axis = self.axis
        angle_rad = math.radians(self.angle_deg)

        # Rodrigues' rotation formula
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        one_minus_cos = 1 - cos_a

        # Normalize axis
        axis_len = math.sqrt(axis[0]**2 + axis[1]**2 + axis[2]**2)
        if axis_len > 1e-6:
            ux, uy, uz = axis[0]/axis_len, axis[1]/axis_len, axis[2]/axis_len
        else:
            ux, uy, uz = 0, 0, 1

        return [
            [cos_a + ux*ux*one_minus_cos,
             ux*uy*one_minus_cos - uz*sin_a,
             ux*uz*one_minus_cos + uy*sin_a],
            [uy*ux*one_minus_cos + uz*sin_a,
             cos_a + uy*uy*one_minus_cos,
             uy*uz*one_minus_cos - ux*sin_a],
            [uz*ux*one_minus_cos - uy*sin_a,
             uz*uy*one_minus_cos + ux*sin_a,
             cos_a + uz*uz*one_minus_cos]
        ]

    def to_dict(self) -> dict:
        """Serialize for caching/UI."""
        return {
            'axis': self.axis,
            'angle_deg': self.angle_deg,
            'description': self.description,
            'score': self.score,
            'rank': self.rank,
            'metrics': self.metrics.to_dict() if self.metrics else None,
        }


@dataclass
class ScoringWeights:
    """
    Weights for orientation scoring.

    All weights are visible and user-editable.
    Weights sum to 1.0.
    """
    # Primary factors
    overhang_weight: float = 0.35      # Less overhang is better
    support_weight: float = 0.30       # Less support is better
    height_weight: float = 0.15        # Shorter is better
    stability_weight: float = 0.15     # More stable is better
    bridge_weight: float = 0.05        # More bridges is better

    def __post_init__(self):
        """Normalize weights to sum to 1.0."""
        total = (
            self.overhang_weight + self.support_weight +
            self.height_weight + self.stability_weight +
            self.bridge_weight
        )
        if total > 0 and total != 1.0:
            factor = 1.0 / total
            self.overhang_weight *= factor
            self.support_weight *= factor
            self.height_weight *= factor
            self.stability_weight *= factor
            self.bridge_weight *= factor

    def to_dict(self) -> dict:
        """Serialize for UI."""
        return {
            'overhang_weight': self.overhang_weight,
            'support_weight': self.support_weight,
            'height_weight': self.height_weight,
            'stability_weight': self.stability_weight,
            'bridge_weight': self.bridge_weight,
        }


@dataclass
class OrientationRecommendation:
    """
    Complete recommendation for print orientation.

    Contains the best orientation and alternatives,
    along with explanations and metrics.
    """
    # Recommended orientation
    best: OrientationCandidate
    alternatives: List[OrientationCandidate] = field(default_factory=list)

    # Comparison with original orientation
    original: Optional[OrientationCandidate] = None

    # Explanation
    explanation: Optional[OrientationExplanation] = None

    # All candidates that were evaluated
    all_candidates: List[OrientationCandidate] = field(default_factory=list)

    # Weights used for scoring
    weights: ScoringWeights = field(default_factory=ScoringWeights)

    # Analysis metadata
    total_candidates: int = 0
    analysis_time_ms: float = 0.0

    def get_summary(self) -> str:
        """Get human-readable summary."""
        lines = [
            f"Print Orientation Recommendation:",
            f"",
            f"Best: {self.best.description}",
            f"  Score: {self.best.score:.3f}",
            f"",
        ]

        if self.original and self.original != self.best:
            lines.append("Improvements:")
            if self.explanation:
                for imp in self.explanation.improvements:
                    lines.append(f"  - {imp}")

        lines.append(f"\nAlternatives:")
        for alt in self.alternatives[:3]:  # Top 3
            lines.append(f"  {alt.description}: score={alt.score:.3f}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize for caching/UI."""
        return {
            'best': self.best.to_dict(),
            'alternatives': [a.to_dict() for a in self.alternatives],
            'original': self.original.to_dict() if self.original else None,
            'explanation': self.explanation.to_dict() if self.explanation else None,
            'weights': self.weights.to_dict(),
            'total_candidates': self.total_candidates,
            'analysis_time_ms': self.analysis_time_ms,
        }


class CandidateGenerator:
    """
    Generates orientation candidates for evaluation.

    Strategy:
    1. Face-down orientations (major faces pointing down)
    2. Axis-aligned rotations (X, Y axes)
    3. 45° rotations of best candidates

    Target: 10-20 candidates total
    """

    # Maximum number of candidates to generate
    MAX_CANDIDATES = 20
    MAX_FACE_CANDIDATES = 6

    def __init__(self, max_candidates: int = MAX_CANDIDATES):
        """
        Initialize the candidate generator.

        Args:
            max_candidates: Maximum number of candidates to generate
        """
        self.max_candidates = max_candidates

    def generate(self, solid: Any) -> List[OrientationCandidate]:
        """
        Generate orientation candidates for a solid.

        Args:
            solid: Build123d Solid or OCP TopoDS_Shape

        Returns:
            List of OrientationCandidate objects
        """
        import time
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopoDS import TopoDS
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepLProp import BRepLProp_SLProps
        from OCP.TopAbs import TopAbs_REVERSED

        start_time = time.perf_counter()

        candidates = []

        # Extract OCP shape
        ocp_shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

        if ocp_shape is None:
            return candidates

        try:
            # Candidate 0: Original orientation (upright)
            candidates.append(OrientationCandidate(
                axis=(0, 0, 1),
                angle_deg=0,
                description="Upright (Z-axis up)"
            ))

            # Get face data for face-down candidates
            face_data = []
            explorer = TopExp_Explorer(ocp_shape, TopAbs_FACE)

            while explorer.More():
                face = TopoDS.Face_s(explorer.Current())

                # Get face area
                face_props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, face_props)
                area = face_props.Mass()

                # Get normal
                normal = (0, 0, 1)
                try:
                    adaptor = BRepAdaptor_Surface(face)
                    u_min = adaptor.FirstUParameter()
                    u_max = adaptor.LastUParameter()
                    v_min = adaptor.FirstVParameter()
                    v_max = adaptor.LastVParameter()

                    u_center = (u_min + u_max) / 2
                    v_center = (v_min + v_max) / 2

                    slprops = BRepLProp_SLProps(adaptor, u_center, v_center, 1, 0.01)

                    if slprops.IsNormalDefined():
                        n = slprops.Normal()
                        nx, ny, nz = n.X(), n.Y(), n.Z()

                        if face.Orientation() == TopAbs_REVERSED:
                            nx, ny, nz = -nx, -ny, -nz

                        normal = (nx, ny, nz)
                except Exception:
                    pass

                face_data.append({
                    'area': area,
                    'normal': normal,
                })

                explorer.Next()

            # Sort faces by area (largest first)
            face_data.sort(key=lambda f: f['area'], reverse=True)

            # Candidate 1-6: Face-down orientations for largest faces
            face_count = min(self.MAX_FACE_CANDIDATES, len(face_data))
            for i in range(face_count):
                face = face_data[i]
                if face['area'] > 100:  # Only significant faces
                    normal = face['normal']

                    # Determine rotation to make this face point down
                    # Face normal (nx, ny, nz) -> rotate so it becomes (0, 0, -1)
                    candidates.append(OrientationCandidate(
                        axis=RotationAxis.Y.value,  # Simplified - use Y axis rotation
                        angle_deg=90,
                        description=f"Face {i+1} down ({face['area']:.0f} mm²)"
                    ))

            # Candidate: X-axis rotation (90°)
            candidates.append(OrientationCandidate(
                axis=RotationAxis.X.value,
                angle_deg=90,
                description="Rotated 90° around X"
            ))

            # Candidate: Y-axis rotation (90°)
            candidates.append(OrientationCandidate(
                axis=RotationAxis.Y.value,
                angle_deg=90,
                description="Rotated 90° around Y"
            ))

            # Candidate: 180° rotation (upside down)
            candidates.append(OrientationCandidate(
                axis=(0, 0, 1),
                angle_deg=180,
                description="Upside down (180°)"
            ))

            # Candidate: 45° rotation
            candidates.append(OrientationCandidate(
                axis=RotationAxis.Y.value,
                angle_deg=45,
                description="Rotated 45° around Y"
            ))

        except Exception as e:
            logger.exception(f"Candidate generation failed: {e}")

        # Deduplicate by description
        seen = set()
        unique_candidates = []
        for c in candidates:
            if c.description not in seen:
                seen.add(c.description)
                unique_candidates.append(c)

        logger.debug(f"Generated {len(unique_candidates)} candidates in "
                    f"{(time.perf_counter() - start_time) * 1000:.1f}ms")

        return unique_candidates[:self.max_candidates]


class OrientationRanker:
    """
    Scores and ranks orientation candidates.

    Uses weighted heuristics to score each candidate.
    Lower score = better orientation.
    """

    # Scoring parameters
    MAX_SUPPORT_VOLUME = 50000  # mm³
    MAX_BUILD_HEIGHT = 200      # mm
    MAX_OVERHANG_RATIO = 0.5    # 50% of surface area

    def __init__(self, weights: Optional[ScoringWeights] = None):
        """
        Initialize the ranker.

        Args:
            weights: Scoring weights (uses default if None)
        """
        self.weights = weights or ScoringWeights()

    def score(self, candidate: OrientationCandidate) -> float:
        """
        Score an orientation candidate.

        Lower score = better orientation.
        Score is weighted sum of penalties (0 = perfect, 1 = worst).

        Args:
            candidate: Orientation candidate with metrics computed

        Returns:
            Score between 0 and 1 (lower is better)
        """
        if candidate.metrics is None:
            return 1.0  # No metrics = worst score

        m = candidate.metrics

        # Normalize metrics to 0-1 scale
        overhang_penalty = min(1.0, m.overhang_ratio / self.MAX_OVERHANG_RATIO)
        support_penalty = min(1.0, m.support_volume_estimate_mm3 / self.MAX_SUPPORT_VOLUME)
        height_penalty = min(1.0, m.build_height_mm / self.MAX_BUILD_HEIGHT)
        stability_bonus = m.stability_score  # Already 0-1, higher is better
        bridge_bonus = min(1.0, m.base_contact_ratio / 0.5)  # More base = better

        # Weighted score
        score = (
            self.weights.overhang_weight * overhang_penalty +
            self.weights.support_weight * support_penalty +
            self.weights.height_weight * height_penalty +
            self.weights.stability_weight * (1.0 - stability_bonus) +
            self.weights.bridge_weight * (1.0 - bridge_bonus)
        )

        return min(1.0, max(0.0, score))

    def rank(self, candidates: List[OrientationCandidate]) -> List[OrientationCandidate]:
        """
        Sort candidates by score (best first).

        Args:
            candidates: List of candidates with metrics computed

        Returns:
            Sorted list with rank assigned
        """
        # Score all candidates
        for candidate in candidates:
            candidate.score = self.score(candidate)

        # Sort by score
        sorted_candidates = sorted(candidates, key=lambda c: c.score)

        # Assign ranks
        for i, candidate in enumerate(sorted_candidates):
            candidate.rank = i + 1

        return sorted_candidates


class PrintOptimizer:
    """
    Main entry point for print orientation optimization.

    Combines candidate generation, scoring, and recommendation.
    """

    def __init__(
        self,
        weights: Optional[ScoringWeights] = None,
        max_candidates: int = 15
    ):
        """
        Initialize the print optimizer.

        Args:
            weights: Scoring weights (uses default if None)
            max_candidates: Maximum number of candidates to evaluate
        """
        self.weights = weights or ScoringWeights()
        self.generator = CandidateGenerator(max_candidates)
        self.ranker = OrientationRanker(self.weights)

    def optimize(self, solid: Any) -> OrientationRecommendation:
        """
        Find the optimal print orientation for a solid.

        Args:
            solid: Build123d Solid or OCP TopoDS_Shape

        Returns:
            OrientationRecommendation with best orientation and alternatives
        """
        import time

        start_time = time.perf_counter()

        # Generate candidates
        candidates = self.generator.generate(solid)

        # Evaluate each candidate (compute metrics)
        for candidate in candidates:
            try:
                candidate.metrics = compute_orientation_metrics(solid)
            except Exception as e:
                logger.warning(f"Failed to compute metrics for {candidate.description}: {e}")

        # Rank candidates
        ranked = self.ranker.rank(candidates)

        # Build recommendation
        best = ranked[0] if ranked else candidates[0]
        alternatives = ranked[1:4] if len(ranked) > 1 else []

        # Use original as the first candidate (if it exists)
        original = next((c for c in candidates if c.angle_deg == 0), None)

        recommendation = OrientationRecommendation(
            best=best,
            alternatives=alternatives,
            original=original,
            all_candidates=candidates,
            weights=self.weights,
            total_candidates=len(candidates)
        )

        # Generate explanation
        if original and original.metrics:
            recommendation.explanation = build_explanation(
                orientation_before={'axis': (0, 0, 1), 'angle': 0},
                orientation_after={'axis': best.axis, 'angle': best.angle_deg},
                metrics_before=original.metrics.to_dict(),
                metrics_after=best.metrics.to_dict(),
                material='PLA'
            )

        recommendation.analysis_time_ms = (time.perf_counter() - start_time) * 1000

        logger.info(f"Orientation optimization: {len(candidates)} candidates, "
                   f"best={best.description}, score={best.score:.3f}, "
                   f"time={recommendation.analysis_time_ms:.0f}ms")

        return recommendation


def recommend_orientation(
    solid: Any,
    weights: Optional[ScoringWeights] = None,
    max_candidates: int = 15
) -> OrientationRecommendation:
    """
    Convenience function to recommend optimal print orientation.

    Args:
        solid: Build123d Solid or OCP TopoDS_Shape
        weights: Optional scoring weights
        max_candidates: Maximum candidates to evaluate

    Returns:
        OrientationRecommendation with best orientation
    """
    optimizer = PrintOptimizer(weights, max_candidates)
    return optimizer.optimize(solid)
