"""
TNP v5.0 - Ambiguity Detection Tests

Tests for the AmbiguityDetector class and ambiguity detection logic.
"""

import pytest
from modeling.tnp_v5.ambiguity import (
    AmbiguityDetector,
    AmbiguityReport,
    AmbiguityType,
    CandidateInfo,
    detect_ambiguity,
)


class TestAmbiguityType:
    """Test AmbiguityType enum."""

    def test_values(self):
        """Test enum values exist."""
        assert AmbiguityType.SYMMETRIC.value == "symmetric"
        assert AmbiguityType.PROXIMATE.value == "proximate"
        assert AmbiguityType.DUPLICATE.value == "duplicate"
        assert AmbiguityType.INSUFFICIENT_CONTEXT.value == "insufficient_context"
        assert AmbiguityType.MULTIPLE_FEATURES.value == "multiple_features"


class TestAmbiguityReport:
    """Test AmbiguityReport dataclass."""

    def test_creation(self):
        """Test creating an ambiguity report."""
        report = AmbiguityReport(
            ambiguity_type=AmbiguityType.SYMMETRIC,
            question="Which shape?",
            candidates=["shape1", "shape2"]
        )

        assert report.ambiguity_type == AmbiguityType.SYMMETRIC
        assert report.question == "Which shape?"
        assert report.candidates == ["shape1", "shape2"]
        assert report.candidate_descriptions == ["Candidate 1", "Candidate 2"]

    def test_with_descriptions(self):
        """Test report with custom descriptions."""
        report = AmbiguityReport(
            ambiguity_type=AmbiguityType.DUPLICATE,
            question="Select one",
            candidates=["a", "b"],
            candidate_descriptions=["Face A", "Face B"]
        )

        assert report.candidate_descriptions == ["Face A", "Face B"]

    def test_with_metadata(self):
        """Test report with metadata."""
        report = AmbiguityReport(
            ambiguity_type=AmbiguityType.PROXIMATE,
            question="Select",
            candidates=["x"],
            metadata={"threshold": 0.1}
        )

        assert report.metadata == {"threshold": 0.1}


class TestCandidateInfo:
    """Test CandidateInfo dataclass."""

    def test_minimal(self):
        """Test creating minimal candidate info."""
        info = CandidateInfo(
            shape_id="test",
            score=0.5,
            distance=1.0,
            shape_type="FACE"
        )

        assert info.shape_id == "test"
        assert info.score == 0.5
        assert info.distance == 1.0
        assert info.shape_type == "FACE"
        assert info.feature_id is None
        assert info.geometry_hash is None
        assert info.center is None

    def test_complete(self):
        """Test creating complete candidate info."""
        info = CandidateInfo(
            shape_id="test",
            score=0.8,
            distance=0.5,
            shape_type="EDGE",
            feature_id="extrude1",
            geometry_hash="abc123",
            center=(1.0, 2.0, 3.0)
        )

        assert info.feature_id == "extrude1"
        assert info.geometry_hash == "abc123"
        assert info.center == (1.0, 2.0, 3.0)


class TestAmbiguityDetectorInit:
    """Test AmbiguityDetector initialization."""

    def test_default_thresholds(self):
        """Test default threshold values."""
        detector = AmbiguityDetector()

        assert detector._symmetry_threshold == 0.01
        assert detector._proximity_threshold == 0.1
        assert detector._score_threshold == 0.05

    def test_custom_thresholds(self):
        """Test custom threshold values."""
        detector = AmbiguityDetector(
            symmetry_threshold=0.1,
            proximity_threshold=1.0,
            score_difference_threshold=0.1
        )

        assert detector._symmetry_threshold == 0.1
        assert detector._proximity_threshold == 1.0
        assert detector._score_threshold == 0.1


class TestDetectNoAmbiguity:
    """Test detect() with non-ambiguous cases."""

    def test_empty_candidates(self):
        """Test with empty candidate list."""
        detector = AmbiguityDetector()

        result = detector.detect([])

        assert result is None

    def test_single_candidate(self):
        """Test with single candidate (no ambiguity)."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(shape_id="shape1", score=0.9, distance=1.0, shape_type="FACE")
        ]

        result = detector.detect(candidates)

        assert result is None

    def test_clear_winner(self):
        """Test with clear winner (large score difference)."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(shape_id="shape1", score=0.9, distance=1.0, shape_type="FACE"),
            CandidateInfo(shape_id="shape2", score=0.3, distance=10.0, shape_type="FACE")
        ]

        result = detector.detect(candidates)

        assert result is None

    def test_distinct_positions(self):
        """Test with candidates at distinct positions."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(
                shape_id="shape1", score=0.8, distance=1.0, shape_type="FACE",
                center=(0, 0, 0), feature_id="feat1"
            ),
            CandidateInfo(
                shape_id="shape2", score=0.6, distance=5.0, shape_type="FACE",
                center=(100, 100, 100), feature_id="feat1"
            )
        ]

        result = detector.detect(candidates)

        assert result is None


class TestDetectDuplicateScores:
    """Test duplicate score detection."""

    def test_identical_scores(self):
        """Test detection of identical scores."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(shape_id="shape1", score=0.8, distance=1.0, shape_type="FACE"),
            CandidateInfo(shape_id="shape2", score=0.8, distance=2.0, shape_type="FACE")
        ]

        result = detector.detect(candidates)

        assert result is not None
        assert result.ambiguity_type == AmbiguityType.DUPLICATE
        assert len(result.candidates) == 2
        assert "shape1" in result.candidates
        assert "shape2" in result.candidates

    def test_very_close_scores(self):
        """Test detection of very close scores."""
        detector = AmbiguityDetector(score_difference_threshold=0.05)

        candidates = [
            CandidateInfo(shape_id="shape1", score=0.80, distance=1.0, shape_type="FACE"),
            CandidateInfo(shape_id="shape2", score=0.82, distance=2.0, shape_type="FACE")
        ]

        result = detector.detect(candidates)

        assert result is not None
        assert result.ambiguity_type == AmbiguityType.DUPLICATE

    def test_outside_threshold(self):
        """Test scores outside threshold are not ambiguous."""
        detector = AmbiguityDetector(score_difference_threshold=0.05)

        candidates = [
            CandidateInfo(
                shape_id="shape1", score=0.90, distance=1.0, shape_type="FACE",
                center=(0, 0, 0), feature_id="feat1"
            ),
            CandidateInfo(
                shape_id="shape2", score=0.80, distance=2.0, shape_type="FACE",
                center=(100, 0, 0), feature_id="feat1"
            )
        ]

        result = detector.detect(candidates)

        # Large score difference, different positions - no ambiguity
        assert result is None


class TestDetectSymmetricPositions:
    """Test symmetric position detection."""

    def test_mirror_across_z_plane(self):
        """Test detection of mirror across Z=0 plane."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(
                shape_id="shape1", score=0.8, distance=1.0, shape_type="FACE",
                center=(10, 20, 5)
            ),
            CandidateInfo(
                shape_id="shape2", score=0.8, distance=1.0, shape_type="FACE",
                center=(10, 20, -5)
            )
        ]

        result = detector.detect(candidates)

        assert result is not None
        assert result.ambiguity_type == AmbiguityType.SYMMETRIC

    def test_mirror_across_y_plane(self):
        """Test detection of mirror across Y=0 plane."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(
                shape_id="shape1", score=0.8, distance=1.0, shape_type="FACE",
                center=(10, 5, 20)
            ),
            CandidateInfo(
                shape_id="shape2", score=0.8, distance=1.0, shape_type="FACE",
                center=(10, -5, 20)
            )
        ]

        result = detector.detect(candidates)

        assert result is not None
        assert result.ambiguity_type == AmbiguityType.SYMMETRIC

    def test_mirror_across_x_plane(self):
        """Test detection of mirror across X=0 plane."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(
                shape_id="shape1", score=0.8, distance=1.0, shape_type="FACE",
                center=(5, 10, 20)
            ),
            CandidateInfo(
                shape_id="shape2", score=0.8, distance=1.0, shape_type="FACE",
                center=(-5, 10, 20)
            )
        ]

        result = detector.detect(candidates)

        assert result is not None
        assert result.ambiguity_type == AmbiguityType.SYMMETRIC

    def test_not_symmetric(self):
        """Test positions that are not symmetric."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(
                shape_id="shape1", score=0.9, distance=1.0, shape_type="FACE",
                center=(0, 0, 0)
            ),
            CandidateInfo(
                shape_id="shape2", score=0.7, distance=2.0, shape_type="FACE",
                center=(10, 20, 30)
            )
        ]

        result = detector.detect(candidates)

        # Not symmetric, not close scores
        assert result is None

    def test_no_center_no_symmetry_detection(self):
        """Test that candidates without centers skip symmetry check."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(shape_id="shape1", score=0.8, distance=1.0, shape_type="FACE"),
            CandidateInfo(shape_id="shape2", score=0.8, distance=1.0, shape_type="FACE")
        ]

        result = detector.detect(candidates)

        # Should still detect duplicate scores
        assert result is not None
        assert result.ambiguity_type == AmbiguityType.DUPLICATE


class TestDetectProximatePositions:
    """Test proximate position detection."""

    def test_proximate_candidates(self):
        """Test detection of very close candidates."""
        detector = AmbiguityDetector(proximity_threshold=1.0)

        candidates = [
            CandidateInfo(
                shape_id="shape1", score=0.8, distance=1.0, shape_type="FACE",
                center=(0, 0, 0)
            ),
            CandidateInfo(
                shape_id="shape2", score=0.75, distance=1.5, shape_type="FACE",
                center=(0.5, 0, 0)
            )
        ]

        result = detector.detect(candidates)

        assert result is not None
        assert result.ambiguity_type == AmbiguityType.PROXIMATE

    def test_not_proximate(self):
        """Test candidates that are far apart."""
        detector = AmbiguityDetector(proximity_threshold=1.0)

        candidates = [
            CandidateInfo(
                shape_id="shape1", score=0.9, distance=1.0, shape_type="FACE",
                center=(0, 0, 0)
            ),
            CandidateInfo(
                shape_id="shape2", score=0.7, distance=2.0, shape_type="FACE",
                center=(100, 100, 100)
            )
        ]

        result = detector.detect(candidates)

        # Far apart, different scores - no ambiguity
        assert result is None


class TestDetectMultipleFeatures:
    """Test cross-feature ambiguity detection."""

    def test_different_features_close_scores(self):
        """Test detection of candidates from different features."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(
                shape_id="shape1", score=0.8, distance=1.0, shape_type="FACE",
                feature_id="extrude1"
            ),
            CandidateInfo(
                shape_id="shape2", score=0.78, distance=1.5, shape_type="FACE",
                feature_id="fillet1"
            )
        ]

        result = detector.detect(candidates)

        assert result is not None
        assert result.ambiguity_type == AmbiguityType.MULTIPLE_FEATURES

    def test_same_feature_no_cross_ambiguity(self):
        """Test that same-feature candidates don't trigger this."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(
                shape_id="shape1", score=0.9, distance=1.0, shape_type="FACE",
                feature_id="extrude1"
            ),
            CandidateInfo(
                shape_id="shape2", score=0.7, distance=2.0, shape_type="FACE",
                feature_id="extrude1"
            )
        ]

        result = detector.detect(candidates)

        # Same feature, distinct scores - no ambiguity
        assert result is None

    def test_no_feature_id(self):
        """Test handling of missing feature IDs."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(
                shape_id="shape1", score=0.8, distance=1.0, shape_type="FACE",
                feature_id=None
            ),
            CandidateInfo(
                shape_id="shape2", score=0.7, distance=2.0, shape_type="FACE",
                feature_id=None
            )
        ]

        result = detector.detect(candidates)

        # No feature info - no cross-feature ambiguity
        assert result is None


class TestCloseScoresDetection:
    """Test close scores ambiguity detection."""

    def test_top_two_close(self):
        """Test detection when top two scores are close."""
        detector = AmbiguityDetector(score_difference_threshold=0.1)

        candidates = [
            CandidateInfo(
                shape_id="shape1", score=0.80, distance=1.0, shape_type="FACE",
                center=(0, 0, 0)
            ),
            CandidateInfo(
                shape_id="shape2", score=0.75, distance=2.0, shape_type="FACE",
                center=(100, 0, 0)
            ),
            CandidateInfo(
                shape_id="shape3", score=0.50, distance=5.0, shape_type="FACE"
            )
        ]

        result = detector.detect(candidates)

        assert result is not None
        assert "shape1" in result.candidates or "shape2" in result.candidates


class TestQuestionGeneration:
    """Test user-friendly question generation."""

    def test_duplicate_question(self):
        """Test question for duplicate scores."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(
                shape_id="shape1", score=0.8, distance=1.0, shape_type="FACE",
                feature_id="feat1", center=(0, 0, 0)
            ),
            CandidateInfo(
                shape_id="shape2", score=0.8, distance=2.0, shape_type="FACE",
                feature_id="feat1", center=(10, 0, 0)  # Same feature to avoid cross-feature detection
            )
        ]

        result = detector.detect(candidates)

        assert result is not None
        assert "identical match scores" in result.question.lower()
        assert "which" in result.question.lower()

    def test_symmetric_question(self):
        """Test question for symmetric positions."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(
                shape_id="shape1", score=0.8, distance=1.0, shape_type="FACE",
                center=(0, 0, 5)
            ),
            CandidateInfo(
                shape_id="shape2", score=0.8, distance=1.0, shape_type="FACE",
                center=(0, 0, -5)
            )
        ]

        result = detector.detect(candidates)

        assert result is not None
        assert "symmetric" in result.question.lower()

    def test_proximate_question(self):
        """Test question for proximate candidates."""
        detector = AmbiguityDetector(proximity_threshold=1.0)

        candidates = [
            CandidateInfo(
                shape_id="shape1", score=0.8, distance=0.5, shape_type="FACE",
                center=(0, 0, 0)
            ),
            CandidateInfo(
                shape_id="shape2", score=0.75, distance=0.6, shape_type="FACE",
                center=(0.5, 0, 0)
            )
        ]

        result = detector.detect(candidates)

        assert result is not None
        assert "close" in result.question.lower()

    def test_multiple_features_question(self):
        """Test question for multiple features."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(
                shape_id="shape1", score=0.8, distance=1.0, shape_type="FACE",
                feature_id="extrude1"
            ),
            CandidateInfo(
                shape_id="shape2", score=0.78, distance=1.5, shape_type="FACE",
                feature_id="fillet1"
            )
        ]

        result = detector.detect(candidates)

        assert result is not None
        assert "different features" in result.question.lower()

    def test_candidate_descriptions(self):
        """Test that candidate descriptions are generated."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(
                shape_id="face1", score=0.8, distance=1.0, shape_type="FACE",
                center=(10, 20, 30)
            ),
            CandidateInfo(
                shape_id="edge1", score=0.8, distance=2.0, shape_type="EDGE",
                center=(40, 50, 60)
            )
        ]

        result = detector.detect(candidates)

        assert result is not None
        assert len(result.candidate_descriptions) == 2
        assert any("FACE" in desc for desc in result.candidate_descriptions)
        assert any("EDGE" in desc for desc in result.candidate_descriptions)


class TestDetectAmbiguityConvenience:
    """Test the detect_ambiguity convenience function."""

    def test_with_dict_candidates(self):
        """Test detect_ambiguity with dict candidates."""
        candidates = [
            {"shape_id": "shape1", "score": 0.8, "distance": 1.0, "shape_type": "FACE"},
            {"shape_id": "shape2", "score": 0.8, "distance": 2.0, "shape_type": "FACE"}
        ]

        result = detect_ambiguity(candidates)

        assert result is not None
        assert result.ambiguity_type == AmbiguityType.DUPLICATE

    def test_with_empty_list(self):
        """Test detect_ambiguity with empty list."""
        result = detect_ambiguity([])

        assert result is None

    def test_with_single_candidate(self):
        """Test detect_ambiguity with single candidate."""
        candidates = [
            {"shape_id": "shape1", "score": 0.8, "distance": 1.0, "shape_type": "FACE"}
        ]

        result = detect_ambiguity(candidates)

        assert result is None

    def test_custom_threshold(self):
        """Test detect_ambiguity with custom threshold."""
        candidates = [
            {"shape_id": "shape1", "score": 0.80, "distance": 1.0, "shape_type": "FACE"},
            {"shape_id": "shape2", "score": 0.85, "distance": 2.0, "shape_type": "FACE"}
        ]

        # With threshold 0.1, should detect ambiguity
        result = detect_ambiguity(candidates, threshold=0.1)

        assert result is not None

        # With threshold 0.01, should not detect ambiguity
        result = detect_ambiguity(candidates, threshold=0.01)

        assert result is None


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_three_way_symmetry(self):
        """Test three-way symmetric positions."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(shape_id="s1", score=0.8, distance=1.0, shape_type="FACE", center=(5, 0, 0)),
            CandidateInfo(shape_id="s2", score=0.8, distance=1.0, shape_type="FACE", center=(-5, 0, 0)),
            CandidateInfo(shape_id="s3", score=0.8, distance=1.0, shape_type="FACE", center=(0, 5, 0))
        ]

        result = detector.detect(candidates)

        # Should detect some form of ambiguity
        assert result is not None

    def test_many_candidates(self):
        """Test with many candidates."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(
                shape_id=f"shape{i}", score=0.8 - i * 0.05, distance=i * 1.0,
                shape_type="FACE", center=(i * 10, 0, 0)
            )
            for i in range(10)
        ]

        result = detector.detect(candidates)

        # Should have clear winner (first candidate)
        assert result is None

    def test_missing_optional_fields(self):
        """Test candidates with missing optional fields."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(shape_id="s1", score=0.8, distance=1.0, shape_type="FACE"),
            CandidateInfo(shape_id="s2", score=0.8, distance=1.0, shape_type="FACE")
        ]

        result = detector.detect(candidates)

        # Should still detect duplicate scores
        assert result is not None


class TestReportMetadata:
    """Test metadata in ambiguity reports."""

    def test_duplicate_metadata(self):
        """Test metadata in duplicate report."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(shape_id="s1", score=0.8, distance=1.0, shape_type="FACE"),
            CandidateInfo(shape_id="s2", score=0.8, distance=1.0, shape_type="FACE")
        ]

        result = detector.detect(candidates)

        assert result is not None
        assert "score" in result.metadata
        assert result.metadata["score"] == 0.8

    def test_proximate_metadata(self):
        """Test metadata in proximate report."""
        detector = AmbiguityDetector(proximity_threshold=2.5)

        candidates = [
            CandidateInfo(shape_id="s1", score=0.8, distance=1.0, shape_type="FACE", center=(0, 0, 0)),
            CandidateInfo(shape_id="s2", score=0.75, distance=1.5, shape_type="FACE", center=(1, 0, 0))
        ]

        result = detector.detect(candidates)

        assert result is not None
        assert "proximity_threshold" in result.metadata

    def test_multiple_features_metadata(self):
        """Test metadata in multiple features report."""
        detector = AmbiguityDetector()

        candidates = [
            CandidateInfo(shape_id="s1", score=0.8, distance=1.0, shape_type="FACE", feature_id="feat1"),
            CandidateInfo(shape_id="s2", score=0.78, distance=1.5, shape_type="FACE", feature_id="feat2")
        ]

        result = detector.detect(candidates)

        assert result is not None
        assert "features" in result.metadata
        assert "feat1" in result.metadata["features"]
        assert "feat2" in result.metadata["features"]
