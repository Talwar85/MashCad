"""
TNP v5.0 - Semantic Matcher

Context-aware shape matching using selection context.

Scoring:
1. Proximity to selection point (40%)
2. View direction alignment (20%)
3. Adjacency preservation (30%)
4. Feature continuity (10%)
"""

import numpy as np
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from loguru import logger

from .types import ShapeID, SelectionContext, ShapeType
from .spatial import SpatialIndex


@dataclass
class MatchCandidate:
    """
    A candidate shape for semantic matching.

    Attributes:
        shape_id: UUID of the candidate shape
        shape: The OCP TopoDS_Shape (or None)
        center: Geometric center point
        normal: Surface normal (for faces)
        adjacent: List of adjacent shape IDs
        feature_id: Creating feature ID
        shape_type: Type of shape
    """
    shape_id: str
    shape: Any
    center: Tuple[float, float, float]
    normal: Optional[Tuple[float, float, float]] = None
    adjacent: List[str] = None
    feature_id: str = ""
    shape_type: str = ""

    def __post_init__(self):
        if self.adjacent is None:
            self.adjacent = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for scoring."""
        return {
            'shape_id': self.shape_id,
            'shape': self.shape,
            'center': self.center,
            'normal': self.normal,
            'adjacent': self.adjacent,
            'feature_id': self.feature_id,
            'shape_type': self.shape_type
        }


@dataclass
class MatchResult:
    """
    Result of semantic matching.

    Attributes:
        matched_shape: The best matching shape (or None if ambiguous/failed)
        score: The confidence score (0.0 - 1.0)
        method: ResolutionMethod used
        candidates: All candidates considered
        is_ambiguous: Whether the match was ambiguous
        alternative_scores: Scores of top candidates
    """
    matched_shape: Optional[Any]
    score: float
    candidates: List[MatchCandidate]
    is_ambiguous: bool = False
    alternative_scores: List[Tuple[str, float]] = None

    def __post_init__(self):
        if self.alternative_scores is None:
            self.alternative_scores = []


class SemanticMatcher:
    """
    Context-aware shape matching using selection context.

    Uses multi-factor scoring to find the best matching shape when
    exact matching fails.
    """

    # Scoring weights
    WEIGHT_PROXIMITY = 0.40
    WEIGHT_VIEW_ALIGNMENT = 0.20
    WEIGHT_ADJACENCY = 0.30
    WEIGHT_FEATURE = 0.10

    # Proximity scoring parameters
    PROXIMITY_SIGMA = 10.0  # mm - Gaussian decay parameter

    # Ambiguity threshold
    AMBIGUITY_THRESHOLD = 0.05  # 5% relative difference

    def __init__(self, spatial_index: SpatialIndex):
        """
        Initialize the semantic matcher.

        Args:
            spatial_index: The SpatialIndex for proximity queries
        """
        self._spatial = spatial_index

    def match(
        self,
        shape_id: ShapeID,
        context: SelectionContext,
        current_solid: Any,
        max_candidates: int = 10
    ) -> MatchResult:
        """
        Find the best matching shape using semantic criteria.

        Args:
            shape_id: The original ShapeID to resolve
            context: SelectionContext from when shape was selected
            current_solid: Current state of the solid
            max_candidates: Maximum candidates to consider

        Returns:
            MatchResult with best match or None if ambiguous/failed
        """
        import time
        start = time.perf_counter()

        # Get candidates from spatial index
        candidates = self._get_candidates(shape_id, context, current_solid, max_candidates)

        if not candidates:
            logger.debug(f"[SemanticMatcher] No candidates found for {shape_id.uuid[:8]}")
            return MatchResult(
                matched_shape=None,
                score=0.0,
                candidates=[],
                is_ambiguous=False
            )

        # Single candidate - return immediately
        if len(candidates) == 1:
            duration = (time.perf_counter() - start) * 1000
            logger.debug(f"[SemanticMatcher] Single candidate found in {duration:.2f}ms")
            return MatchResult(
                matched_shape=candidates[0].shape,
                score=1.0,
                candidates=candidates,
                is_ambiguous=False
            )

        # Score each candidate
        scored = []
        for candidate in candidates:
            score = self._compute_score(candidate, context)
            scored.append((candidate, score))

        # Sort by score (highest first)
        scored.sort(key=lambda x: x[1], reverse=True)

        # Check for ambiguity
        is_ambiguous = self._is_ambiguous(scored, self.AMBIGUITY_THRESHOLD)

        if is_ambiguous:
            logger.debug(f"[SemanticMatcher] Ambiguous match - top scores too close")
            # Create alternative scores list
            alt_scores = [(c.shape_id, s) for c, s in scored[:3]]
            return MatchResult(
                matched_shape=None,
                score=scored[0][1] if scored else 0.0,
                candidates=candidates,
                is_ambiguous=True,
                alternative_scores=alt_scores
            )

        # Return best match
        best_candidate, best_score = scored[0]
        duration = (time.perf_counter() - start) * 1000

        logger.debug(f"[SemanticMatcher] Matched {best_candidate.shape_id[:8]}... "
                    f"with score {best_score:.3f} in {duration:.2f}ms")

        return MatchResult(
            matched_shape=best_candidate.shape,
            score=best_score,
            candidates=candidates,
            is_ambiguous=False
        )

    def _get_candidates(
        self,
        shape_id: ShapeID,
        context: SelectionContext,
        current_solid: Any,
        max_candidates: int
    ) -> List[MatchCandidate]:
        """
        Get candidate shapes from the current solid.

        Args:
            shape_id: Original ShapeID
            context: SelectionContext
            current_solid: Current solid geometry
            max_candidates: Maximum number of candidates

        Returns:
            List of MatchCandidate objects
        """
        candidates = []

        # Use spatial index to find nearby shapes
        selection_point = context.selection_point

        # Start with reasonable search radius (50mm)
        search_radius = 50.0

        nearby_uuids = self._spatial.query_nearby(
            selection_point,
            search_radius,
            shape_type=shape_id.shape_type.name
        )

        # If not enough results, expand search
        if len(nearby_uuids) < 3:
            search_radius = 200.0
            nearby_uuids = self._spatial.query_nearby(
                selection_point,
                search_radius,
                shape_type=shape_id.shape_type.name
            )

        # Convert to MatchCandidate objects
        for uuid in nearby_uuids[:max_candidates]:
            # Get candidate data from spatial index
            shape_data = self._spatial.get_shape_data(uuid)
            bounds = self._spatial.get_bounds(uuid)

            if bounds is None:
                continue

            # Build candidate
            center = bounds.center()
            candidates.append(MatchCandidate(
                shape_id=uuid,
                shape=None,  # Will be filled by caller if needed
                center=center,
                normal=None,  # TODO: Extract from geometry
                adjacent=[],
                feature_id=shape_data.get('feature_id', ''),
                shape_type=shape_data.get('shape_type', '')
            ))

        return candidates

    def _compute_score(self, candidate: MatchCandidate, context: SelectionContext) -> float:
        """
        Compute semantic match score for a candidate.

        Combines four scoring factors with their weights.

        Args:
            candidate: The candidate to score
            context: Original selection context

        Returns:
            Score from 0.0 to 1.0
        """
        proximity = self._score_proximity(candidate, context) * self.WEIGHT_PROXIMITY
        view_align = self._score_view_alignment(candidate, context) * self.WEIGHT_VIEW_ALIGNMENT
        adjacency = self._score_adjacency(candidate, context) * self.WEIGHT_ADJACENCY
        feature = self._score_feature_continuity(candidate, context) * self.WEIGHT_FEATURE

        total_score = proximity + view_align + adjacency + feature

        # Clamp to [0, 1]
        return max(0.0, min(1.0, total_score))

    def _score_proximity(self, candidate: MatchCandidate, context: SelectionContext) -> float:
        """
        Score based on distance from selection point.

        Uses Gaussian decay: score = exp(-distance^2 / 2*sigma^2)
        with sigma = 10mm.

        Args:
            candidate: Candidate to score
            context: Selection context with original point

        Returns:
            Proximity score from 0.0 to 1.0
        """
        candidate_center = np.array(candidate.center)
        selection_point = np.array(context.selection_point)

        distance = np.linalg.norm(candidate_center - selection_point)

        # Gaussian decay: 1.0 at distance=0, ~0.5 at distance=~7mm
        sigma = self.PROXIMITY_SIGMA
        score = np.exp(-(distance ** 2) / (2 * sigma ** 2))

        return float(score)

    def _score_view_alignment(self, candidate: MatchCandidate, context: SelectionContext) -> float:
        """
        Score based on view direction alignment.

        Front-facing surfaces (normal pointing toward camera) score higher.

        Args:
            candidate: Candidate to score
            context: Selection context with view direction

        Returns:
            View alignment score from 0.0 to 1.0
        """
        # If no normal available, return neutral score
        if candidate.normal is None:
            return 0.5

        normal = np.array(candidate.normal)
        view_dir = np.array(context.view_direction)

        # Normalize vectors
        normal_norm = np.linalg.norm(normal)
        view_norm = np.linalg.norm(view_dir)

        if normal_norm == 0 or view_norm == 0:
            return 0.5

        normal = normal / normal_norm
        view_dir = view_dir / view_norm

        # Dot product: 1.0 = facing camera, 0.0 = perpendicular
        alignment = abs(np.dot(normal, view_dir))

        return float(alignment)

    def _score_adjacency(self, candidate: MatchCandidate, context: SelectionContext) -> float:
        """
        Score based on preserved adjacency relationships.

        Higher score if adjacent shapes match original configuration.

        Args:
            candidate: Candidate to score
            context: Selection context with original adjacent shapes

        Returns:
            Adjacency score from 0.0 to 1.0
        """
        original_adjacent = set(context.adjacent_shapes)
        candidate_adjacent = set(candidate.adjacent)

        # No adjacency constraint - give full score
        if not original_adjacent:
            return 1.0

        # Jaccard similarity: intersection / union
        intersection = len(original_adjacent & candidate_adjacent)
        union = len(original_adjacent | candidate_adjacent)

        if union == 0:
            return 0.0

        return intersection / union

    def _score_feature_continuity(self, candidate: MatchCandidate, context: SelectionContext) -> float:
        """
        Score based on feature continuity.

        Prefer shapes from the same feature.

        Args:
            candidate: Candidate to score
            context: Selection context with feature info

        Returns:
            Feature continuity score (0.0 or 1.0)
        """
        candidate_feature = candidate.feature_id
        context_feature = context.feature_context

        return 1.0 if candidate_feature == context_feature else 0.0

    def _is_ambiguous(self, scored: List[Tuple[MatchCandidate, float]], threshold: float) -> bool:
        """
        Check if top two candidates are too close in score.

        Args:
            scored: List of (candidate, score) tuples, sorted by score
            threshold: Relative difference threshold (e.g., 0.05 = 5%)

        Returns:
            True if ambiguous (top scores too close)
        """
        if len(scored) < 2:
            return False

        top_score = scored[0][1]
        second_score = scored[1][1]

        if top_score == 0:
            return True

        relative_diff = abs(top_score - second_score) / top_score
        return relative_diff < threshold

    def explain_score(self, candidate: MatchCandidate, context: SelectionContext) -> Dict[str, float]:
        """
        Explain the scoring breakdown for a candidate.

        Useful for debugging and user feedback.

        Args:
            candidate: Candidate to analyze
            context: Selection context

        Returns:
            Dictionary with individual scores and total
        """
        proximity = self._score_proximity(candidate, context)
        view_align = self._score_view_alignment(candidate, context)
        adjacency = self._score_adjacency(candidate, context)
        feature = self._score_feature_continuity(candidate, context)

        weighted_proximity = proximity * self.WEIGHT_PROXIMITY
        weighted_view = view_align * self.WEIGHT_VIEW_ALIGNMENT
        weighted_adjacency = adjacency * self.WEIGHT_ADJACENCY
        weighted_feature = feature * self.WEIGHT_FEATURE

        return {
            'proximity': proximity,
            'view_alignment': view_align,
            'adjacency': adjacency,
            'feature_continuity': feature,
            'weighted_proximity': weighted_proximity,
            'weighted_view': weighted_view,
            'weighted_adjacency': weighted_adjacency,
            'weighted_feature': weighted_feature,
            'total': weighted_proximity + weighted_view + weighted_adjacency + weighted_feature
        }


def compute_match_score(
    candidate_center: Tuple[float, float, float],
    selection_point: Tuple[float, float, float],
    candidate_normal: Optional[Tuple[float, float, float]],
    view_direction: Tuple[float, float, float],
    adjacent_match_ratio: float = 0.0,
    same_feature: bool = False
) -> float:
    """
    Convenience function to compute semantic match score.

    Args:
        candidate_center: Center of candidate shape
        selection_point: Original selection point
        candidate_normal: Surface normal (optional)
        view_direction: Camera view direction
        adjacent_match_ratio: Ratio of matching adjacent shapes (0-1)
        same_feature: Whether from same feature

    Returns:
        Total score from 0.0 to 1.0
    """
    # Create temporary objects for scoring
    matcher = SemanticMatcher(spatial_index=None)  # type: ignore

    candidate = MatchCandidate(
        shape_id="temp",
        shape=None,
        center=candidate_center,
        normal=candidate_normal
    )

    context = SelectionContext(
        shape_id="temp",
        selection_point=selection_point,
        view_direction=view_direction,
        adjacent_shapes=[],
        feature_context=""
    )

    # Compute base score
    score = matcher._compute_score(candidate, context)

    # Override adjacency and feature if provided
    if adjacent_match_ratio > 0:
        score = score - (SemanticMatcher.WEIGHT_ADJACENCY) + (adjacent_match_ratio * SemanticMatcher.WEIGHT_ADJACENCY)

    if same_feature:
        score = score - (SemanticMatcher.WEIGHT_FEATURE) + (1.0 * SemanticMatcher.WEIGHT_FEATURE)

    return max(0.0, min(1.0, score))
