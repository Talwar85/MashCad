"""
TNP v5.0 - Semantic Matcher Tests

Unit tests for the semantic matching functionality.
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch

from modeling.tnp_v5 import (
    ShapeID,
    ShapeType,
    SelectionContext,
    SemanticMatcher,
    SpatialIndex,
    Bounds,
    MatchCandidate,
    MatchResult
)


class TestMatchCandidate:
    """Test MatchCandidate dataclass."""

    def test_create_candidate(self):
        """Test creating a match candidate."""
        candidate = MatchCandidate(
            shape_id="test-uuid",
            shape=None,
            center=(5, 5, 5),
            normal=(0, 0, 1),
            adjacent=["adj1", "adj2"],
            feature_id="extrude_1",
            shape_type="FACE"
        )

        assert candidate.shape_id == "test-uuid"
        assert candidate.center == (5, 5, 5)
        assert candidate.normal == (0, 0, 1)
        assert len(candidate.adjacent) == 2

    def test_candidate_defaults(self):
        """Test candidate default values."""
        candidate = MatchCandidate(
            shape_id="test",
            shape=None,
            center=(0, 0, 0)
        )

        assert candidate.adjacent == []
        assert candidate.feature_id == ""
        assert candidate.shape_type == ""

    def test_to_dict(self):
        """Test converting candidate to dictionary."""
        candidate = MatchCandidate(
            shape_id="test",
            shape=None,
            center=(1, 2, 3),
            normal=(0, 1, 0),
            adjacent=["a"],
            feature_id="f1",
            shape_type="EDGE"
        )

        result = candidate.to_dict()

        assert result['shape_id'] == "test"
        assert result['center'] == (1, 2, 3)
        assert result['normal'] == (0, 1, 0)


class TestSemanticMatcher:
    """Test SemanticMatcher class."""

    def test_init(self):
        """Test matcher initialization."""
        spatial = Mock(spec=SpatialIndex)
        matcher = SemanticMatcher(spatial)

        assert matcher._spatial == spatial

    def test_score_weights(self):
        """Test scoring weights sum to 1.0."""
        total = (
            SemanticMatcher.WEIGHT_PROXIMITY +
            SemanticMatcher.WEIGHT_VIEW_ALIGNMENT +
            SemanticMatcher.WEIGHT_ADJACENCY +
            SemanticMatcher.WEIGHT_FEATURE
        )

        assert abs(total - 1.0) < 0.001

    def test_score_proximity_exact_match(self):
        """Test proximity scoring with exact location match."""
        matcher = SemanticMatcher(Mock())

        candidate = MatchCandidate(
            shape_id="test",
            shape=None,
            center=(10, 10, 10)  # Same as selection point
        )

        context = SelectionContext(
            shape_id="",
            selection_point=(10, 10, 10),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context=""
        )

        score = matcher._score_proximity(candidate, context)

        # Exact match should score 1.0
        assert abs(score - 1.0) < 0.01

    def test_score_proximity_far_away(self):
        """Test proximity scoring with distant candidate."""
        matcher = SemanticMatcher(Mock())

        candidate = MatchCandidate(
            shape_id="test",
            shape=None,
            center=(100, 100, 100)  # Far from (0,0,0)
        )

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context=""
        )

        score = matcher._score_proximity(candidate, context)

        # Distant candidate should score very low
        assert score < 0.1

    def test_score_proximity_gaussian_decay(self):
        """Test that proximity uses Gaussian decay."""
        matcher = SemanticMatcher(Mock())

        # At sigma = 10mm, score should be ~0.606 (exp(-0.5))
        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context=""
        )

        candidate = MatchCandidate(
            shape_id="test",
            shape=None,
            center=(7.07, 0, 0)  # Distance = ~7.07mm
        )

        score = matcher._score_proximity(candidate, context)

        # At distance sqrt(2)*sigma ≈ 14.14mm, score = exp(-1) ≈ 0.368
        # At distance sigma/sqrt(2) ≈ 7.07mm, score = exp(-0.25) ≈ 0.778
        assert 0.7 < score < 0.85

    def test_score_view_alignment_perfect(self):
        """Test view alignment with perfect alignment."""
        matcher = SemanticMatcher(Mock())

        candidate = MatchCandidate(
            shape_id="test",
            shape=None,
            center=(0, 0, 0),
            normal=(0, 0, 1)  # Pointing toward camera
        )

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),  # Camera looking along -Z
            adjacent_shapes=[],
            feature_context=""
        )

        score = matcher._score_view_alignment(candidate, context)

        # Perfect alignment should score 1.0
        assert abs(score - 1.0) < 0.01

    def test_score_view_alignment_perpendicular(self):
        """Test view alignment with perpendicular normal."""
        matcher = SemanticMatcher(Mock())

        candidate = MatchCandidate(
            shape_id="test",
            shape=None,
            center=(0, 0, 0),
            normal=(1, 0, 0)  # Perpendicular to view
        )

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context=""
        )

        score = matcher._score_view_alignment(candidate, context)

        # Perpendicular should score 0.0
        assert abs(score) < 0.01

    def test_score_view_alignment_no_normal(self):
        """Test view alignment without normal."""
        matcher = SemanticMatcher(Mock())

        candidate = MatchCandidate(
            shape_id="test",
            shape=None,
            center=(0, 0, 0),
            normal=None  # No normal available
        )

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context=""
        )

        score = matcher._score_view_alignment(candidate, context)

        # Should return neutral score
        assert abs(score - 0.5) < 0.01

    def test_score_adjacency_perfect_match(self):
        """Test adjacency scoring with perfect match."""
        matcher = SemanticMatcher(Mock())

        candidate = MatchCandidate(
            shape_id="test",
            shape=None,
            center=(0, 0, 0),
            adjacent=["a", "b", "c"]  # Same as original
        )

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=["a", "b", "c"],
            feature_context=""
        )

        score = matcher._score_adjacency(candidate, context)

        # Perfect match should score 1.0
        assert abs(score - 1.0) < 0.01

    def test_score_adjacency_partial_match(self):
        """Test adjacency scoring with partial match."""
        matcher = SemanticMatcher(Mock())

        candidate = MatchCandidate(
            shape_id="test",
            shape=None,
            center=(0, 0, 0),
            adjacent=["a", "b"]  # Missing "c"
        )

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=["a", "b", "c"],
            feature_context=""
        )

        score = matcher._score_adjacency(candidate, context)

        # Jaccard similarity: 2/3 = 0.667
        assert abs(score - 0.667) < 0.01

    def test_score_adjacency_no_constraint(self):
        """Test adjacency scoring with no original constraint."""
        matcher = SemanticMatcher(Mock())

        candidate = MatchCandidate(
            shape_id="test",
            shape=None,
            center=(0, 0, 0),
            adjacent=[]
        )

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],  # No constraint
            feature_context=""
        )

        score = matcher._score_adjacency(candidate, context)

        # No constraint should score 1.0
        assert abs(score - 1.0) < 0.01

    def test_score_feature_continuity_same_feature(self):
        """Test feature continuity scoring with same feature."""
        matcher = SemanticMatcher(Mock())

        candidate = MatchCandidate(
            shape_id="test",
            shape=None,
            center=(0, 0, 0),
            feature_id="extrude_1"
        )

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context="extrude_1"
        )

        score = matcher._score_feature_continuity(candidate, context)

        # Same feature should score 1.0
        assert score == 1.0

    def test_score_feature_continuity_different_feature(self):
        """Test feature continuity scoring with different feature."""
        matcher = SemanticMatcher(Mock())

        candidate = MatchCandidate(
            shape_id="test",
            shape=None,
            center=(0, 0, 0),
            feature_id="fillet_1"
        )

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context="extrude_1"
        )

        score = matcher._score_feature_continuity(candidate, context)

        # Different feature should score 0.0
        assert score == 0.0

    def test_compute_score_combined(self):
        """Test combined score computation."""
        matcher = SemanticMatcher(Mock())

        candidate = MatchCandidate(
            shape_id="test",
            shape=None,
            center=(10, 10, 10),  # Will match selection point
            normal=(0, 0, 1),     # Will align with view
            adjacent=["a"],       # Will match adjacent
            feature_id="f1"       # Will match feature
        )

        context = SelectionContext(
            shape_id="",
            selection_point=(10, 10, 10),
            view_direction=(0, 0, 1),
            adjacent_shapes=["a"],
            feature_context="f1"
        )

        score = matcher._compute_score(candidate, context)

        # All factors should contribute
        assert score > 0.8  # Should be high

    def test_is_ambiguous_not_enough_candidates(self):
        """Test ambiguity check with insufficient candidates."""
        matcher = SemanticMatcher(Mock())

        scored = [
            (MatchCandidate(shape_id="1", shape=None, center=(0, 0, 0)), 0.9)
        ]

        is_ambig = matcher._is_ambiguous(scored, threshold=0.05)

        # Single candidate should not be ambiguous
        assert is_ambig is False

    def test_is_ambiguous_close_scores(self):
        """Test ambiguity detection with close scores."""
        matcher = SemanticMatcher(Mock())

        scored = [
            (MatchCandidate(shape_id="1", shape=None, center=(0, 0, 0)), 0.90),
            (MatchCandidate(shape_id="2", shape=None, center=(1, 1, 1)), 0.89)
        ]

        is_ambig = matcher._is_ambiguous(scored, threshold=0.05)

        # 1% difference is less than 5% threshold
        assert is_ambig is True

    def test_is_ambiguous_far_scores(self):
        """Test ambiguity detection with far scores."""
        matcher = SemanticMatcher(Mock())

        scored = [
            (MatchCandidate(shape_id="1", shape=None, center=(0, 0, 0)), 0.90),
            (MatchCandidate(shape_id="2", shape=None, center=(1, 1, 1)), 0.70)
        # 20% difference is greater than 5% threshold
        ]

        is_ambig = matcher._is_ambiguous(scored, threshold=0.05)

        assert is_ambig is False

    def test_is_ambiguous_zero_top_score(self):
        """Test ambiguity detection when top score is zero."""
        matcher = SemanticMatcher(Mock())

        scored = [
            (MatchCandidate(shape_id="1", shape=None, center=(0, 0, 0)), 0.0),
            (MatchCandidate(shape_id="2", shape=None, center=(1, 1, 1)), 0.0)
        ]

        is_ambig = matcher._is_ambiguous(scored, threshold=0.05)

        # Zero top score should be ambiguous
        assert is_ambig is True


class TestSemanticMatcherIntegration:
    """Integration tests for SemanticMatcher with SpatialIndex."""

    def test_match_no_candidates(self):
        """Test matching when no candidates available."""
        spatial = SpatialIndex()
        matcher = SemanticMatcher(spatial)

        shape_id = ShapeID.create(ShapeType.FACE, "test", 0, ())
        context = SelectionContext(
            shape_id=shape_id.uuid,
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context=""
        )

        result = matcher.match(shape_id, context, None)

        assert result.matched_shape is None
        assert result.score == 0.0
        assert len(result.candidates) == 0

    def test_match_single_candidate(self):
        """Test matching with single candidate."""
        spatial = SpatialIndex()
        matcher = SemanticMatcher(spatial)

        # Add a candidate
        spatial.insert(
            shape_id="candidate1",
            bounds=Bounds.from_center((10, 10, 10), 5),
            shape_data={'shape_type': 'FACE', 'feature_id': 'f1'}
        )

        shape_id = ShapeID.create(ShapeType.FACE, "test", 0, ())
        context = SelectionContext(
            shape_id=shape_id.uuid,
            selection_point=(10, 10, 10),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context=""
        )

        result = matcher.match(shape_id, context, None)

        # Candidate was found (score is 1.0)
        assert result.score == 1.0
        assert result.is_ambiguous is False
        assert len(result.candidates) == 1
        # Note: matched_shape is None because we didn't provide actual OCP shapes
        # but the candidate was successfully found and scored

    def test_explain_score(self):
        """Test score explanation."""
        spatial = SpatialIndex()
        matcher = SemanticMatcher(spatial)

        candidate = MatchCandidate(
            shape_id="test",
            shape=None,
            center=(10, 10, 10),
            normal=(0, 0, 1),
            adjacent=["a"],
            feature_id="f1"
        )

        context = SelectionContext(
            shape_id="",
            selection_point=(10, 10, 10),
            view_direction=(0, 0, 1),
            adjacent_shapes=["a", "b"],
            feature_context="f1"
        )

        explanation = matcher.explain_score(candidate, context)

        assert 'proximity' in explanation
        assert 'view_alignment' in explanation
        assert 'adjacency' in explanation
        assert 'feature_continuity' in explanation
        assert 'total' in explanation

        # Check individual scores are in valid range
        assert 0 <= explanation['proximity'] <= 1
        assert 0 <= explanation['view_alignment'] <= 1
        assert 0 <= explanation['adjacency'] <= 1
        assert 0 <= explanation['feature_continuity'] <= 1


class TestComputeMatchScore:
    """Test convenience function for score computation."""

    def test_compute_match_score_basic(self):
        """Test basic score computation."""
        from modeling.tnp_v5.semantic_matcher import compute_match_score

        score = compute_match_score(
            candidate_center=(10, 10, 10),
            selection_point=(10, 10, 10),
            candidate_normal=(0, 0, 1),
            view_direction=(0, 0, 1),
            adjacent_match_ratio=0.0,
            same_feature=False
        )

        assert score > 0.8  # Should be high with exact matches

    def test_compute_match_score_with_adjacent(self):
        """Test score computation with adjacency."""
        from modeling.tnp_v5.semantic_matcher import compute_match_score

        score = compute_match_score(
            candidate_center=(10, 10, 10),
            selection_point=(10, 10, 10),
            candidate_normal=(0, 0, 1),
            view_direction=(0, 0, 1),
            adjacent_match_ratio=1.0,  # Perfect adjacency
            same_feature=False
        )

        # With perfect adjacency, should be higher
        assert score > 0.7

    def test_compute_match_score_with_feature(self):
        """Test score computation with same feature."""
        from modeling.tnp_v5.semantic_matcher import compute_match_score

        score = compute_match_score(
            candidate_center=(10, 10, 10),
            selection_point=(10, 10, 10),
            candidate_normal=(0, 0, 1),
            view_direction=(0, 0, 1),
            adjacent_match_ratio=0.0,
            same_feature=True
        )

        # With same feature, should be higher
        assert score > 0.7


class TestMatchResult:
    """Test MatchResult dataclass."""

    def test_create_result(self):
        """Test creating a match result."""
        candidates = [MatchCandidate(shape_id="1", shape=None, center=(0, 0, 0))]

        result = MatchResult(
            matched_shape=None,
            score=0.9,
            candidates=candidates,
            is_ambiguous=False
        )

        assert result.matched_shape is None
        assert result.score == 0.9
        assert result.is_ambiguous is False
        assert len(result.candidates) == 1

    def test_result_alternative_scores_default(self):
        """Test default alternative scores."""
        result = MatchResult(
            matched_shape=None,
            score=0.9,
            candidates=[]
        )

        assert result.alternative_scores == []

    def test_result_with_alternatives(self):
        """Test result with alternative scores."""
        alt_scores = [("id1", 0.9), ("id2", 0.85)]

        result = MatchResult(
            matched_shape=None,
            score=0.9,
            candidates=[],
            alternative_scores=alt_scores
        )

        assert len(result.alternative_scores) == 2
