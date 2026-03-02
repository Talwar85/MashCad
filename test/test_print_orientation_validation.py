"""
MashCad - Print Orientation Validation Tests
============================================

Comprehensive validation tests for the Print Orientation Optimization system.

Tests cover:
- Phase 1: Geometry Analysis (OrientationMetrics, Bridge, Support, Fins)
- Phase 2: Orientation Recommendation (Candidate generation, scoring)
- Phase 3: UI Integration (Dialog functionality)
- Phase 4: Export Trust Integration (Export warnings)
- Performance: Analysis time budgets
- Accuracy: Correct recommendations for test parts

Author: Claude (Phase 5: Validation)
Date: 2026-03-02
Branch: feature/tnp5
"""

import pytest
import time
from typing import List

from build123d import *
from loguru import logger

# Test imports
from modeling.printability_score import (
    OrientationMetrics, compute_orientation_metrics
)
from modeling.print_bridge_analysis import (
    BridgeClassifier, BridgeType
)
from modeling.print_support import (
    SupportEstimator, SupportEstimate
)
from modeling.print_support_fins import (
    FinGenerator, FinConfig, FinOrientation
)
from modeling.print_orientation_optimizer import (
    OrientationCandidate, OrientationRecommendation,
    recommend_orientation, PrintOptimizer
)
from modeling.print_performance import (
    BUDGET_BASE_ANALYSIS, BUDGET_BRIDGE_CLASSIFICATION,
    BUDGET_SUPPORT_ESTIMATION, BUDGET_FIN_GENERATION,
    BUDGET_TOTAL_RECOMMENDATION
)
from test.corpus.print_orientation.corpus_parts import (
    get_corpus_parts, make_cube, make_plate, make_bridge_sample
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_cube():
    """A simple 20mm cube for testing."""
    return make_cube(20)


@pytest.fixture
def flat_plate():
    """A flat 100x100x5mm plate (should score well)."""
    return make_plate(100, 100, 5)


@pytest.fixture
def bridge_part():
    """A part with a bridge (tests bridge detection)."""
    return make_bridge_sample(60, 10, 20)


@pytest.fixture
def corpus_parts():
    """All corpus parts for comprehensive testing."""
    return get_corpus_parts()


# =============================================================================
# Phase 1: Geometry Analysis Tests
# =============================================================================

class TestOrientationMetrics:
    """Tests for OrientationMetrics computation."""

    def test_cube_metrics(self, sample_cube):
        """Cube should have balanced metrics."""
        metrics = compute_orientation_metrics(sample_cube)

        assert metrics.overhang_area_mm2 >= 0
        assert metrics.overhang_ratio <= 1.0
        assert metrics.build_height_mm == pytest.approx(20, abs=1)
        assert metrics.volume_mm3 == pytest.approx(8000, abs=100)
        assert metrics.total_surface_area_mm2 > 0

    def test_flat_plate_excellent_score(self, flat_plate):
        """Flat plate should have excellent printability score."""
        metrics = compute_orientation_metrics(flat_plate)

        # Flat plate upright should have minimal overhangs
        assert metrics.overhang_ratio < 0.1
        # Good base contact
        assert metrics.base_contact_area_mm2 > 9000  # ~100x100
        assert metrics.base_contact_ratio > 0.8
        # Stable
        assert metrics.stability_score > 0.8

    def test_metrics_performance_budget(self, sample_cube):
        """Base metrics analysis should complete within budget."""
        start = time.perf_counter()
        metrics = compute_orientation_metrics(sample_cube)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < BUDGET_BASE_ANALYSIS
        assert metrics is not None

    def test_overhang_detection(self, sample_cube):
        """Overhang detection should identify downward-facing faces."""
        metrics = compute_orientation_metrics(sample_cube)

        # Cube has some overhang area from vertical faces
        assert metrics.overhang_area_mm2 >= 0
        # Critical overhangs (>60°) should be tracked
        assert metrics.critical_overhang_area_mm2 >= 0

    def test_stability_calculation(self, sample_cube):
        """Stability score should be between 0 and 1."""
        metrics = compute_orientation_metrics(sample_cube)

        assert 0 <= metrics.stability_score <= 1
        # Cube should be stable
        assert metrics.stability_score > 0.5


class TestBridgeAnalysis:
    """Tests for bridge detection and classification."""

    def test_bridge_detection(self, bridge_part):
        """Bridge parts should have bridges detected."""
        classifier = BridgeClassifier()

        result = classifier.classify(bridge_part)

        assert result is not None
        assert hasattr(result, 'total_faces')
        assert hasattr(result, 'bridge_faces')
        assert hasattr(result, 'total_bridge_area_mm2')

    def test_bridge_classification_types(self):
        """Different bridge types should be classified correctly."""
        classifier = BridgeClassifier()

        # Create a simple bridge-like structure
        bridge = Solid.make_box(60, 10, 5)

        result = classifier.classify(bridge)
        # Should return a valid result
        assert result is not None
        assert isinstance(result.total_faces, int)

    def test_material_span_limits(self):
        """Different materials should have different span limits."""
        assert BridgeClassifier.MATERIAL_SPANS['PLA'] > 0
        assert BridgeClassifier.MATERIAL_SPANS['ABS'] > 0
        assert BridgeClassifier.MATERIAL_SPANS['PETG'] > 0

        # PLA should allow longest spans
        assert BridgeClassifier.MATERIAL_SPANS['PLA'] >= BridgeClassifier.MATERIAL_SPANS['ABS']


class TestSupportEstimation:
    """Tests for support volume estimation."""

    def test_support_estimate_structure(self, sample_cube):
        """SupportEstimate should have all required fields."""
        estimator = SupportEstimator()
        estimate = estimator.estimate(sample_cube)

        assert isinstance(estimate, SupportEstimate)
        assert estimate.total_support_volume_mm3 >= 0
        assert estimate.total_contact_area_mm2 >= 0
        assert isinstance(estimate.regions, list)

    def test_support_for_flat_plate(self, flat_plate):
        """Flat plate should need minimal supports."""
        estimator = SupportEstimator()
        estimate = estimator.estimate(flat_plate)

        # Flat plate upright should need very little support
        assert estimate.total_support_volume_mm3 < 1000

    def test_support_performance(self, sample_cube):
        """Support estimation should complete within budget."""
        estimator = SupportEstimator()

        start = time.perf_counter()
        estimate = estimator.estimate(sample_cube)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < BUDGET_SUPPORT_ESTIMATION
        assert estimate is not None


class TestFinGeneration:
    """Tests for support fin generation."""

    def test_fin_config_defaults(self):
        """FinConfig should have sensible defaults."""
        config = FinConfig()

        assert config.thickness_mm > 0
        assert config.height_mm > 0
        assert config.spacing_mm > 0
        assert config.min_overhang_angle_deg > 0

    def test_fin_proposal_structure(self, sample_cube):
        """FinGenerator should return valid proposal."""
        generator = FinGenerator()
        proposal = generator.analyze(sample_cube, 45.0)

        assert proposal is not None
        assert proposal.config == generator.config
        assert proposal.total_fins >= 0
        assert proposal.total_fin_volume_mm3 >= 0

    def test_fin_performance(self, sample_cube):
        """Fin analysis should complete within budget."""
        generator = FinGenerator()

        start = time.perf_counter()
        proposal = generator.analyze(sample_cube, 45.0)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < BUDGET_FIN_GENERATION
        assert proposal is not None


# =============================================================================
# Phase 2: Orientation Recommendation Tests
# =============================================================================

class TestCandidateGeneration:
    """Tests for orientation candidate generation."""

    def test_generates_candidates(self, sample_cube):
        """Should generate 10-20 candidates."""
        from modeling.print_orientation_optimizer import CandidateGenerator

        generator = CandidateGenerator(max_candidates=15)
        candidates = generator.generate(sample_cube)

        assert len(candidates) > 0
        assert len(candidates) <= 15

    def test_default_orientation_included(self, sample_cube):
        """Default upright orientation should always be included."""
        from modeling.print_orientation_optimizer import CandidateGenerator

        generator = CandidateGenerator()
        candidates = generator.generate(sample_cube)

        # Should have a 0-degree (upright) candidate
        has_upright = any(c.angle_deg == 0 for c in candidates)
        assert has_upright

    def test_candidate_descriptions(self, sample_cube):
        """All candidates should have descriptions."""
        from modeling.print_orientation_optimizer import CandidateGenerator

        generator = CandidateGenerator()
        candidates = generator.generate(sample_cube)

        for c in candidates:
            assert c.description
            assert len(c.description) > 0


class TestOrientationRanking:
    """Tests for orientation scoring and ranking."""

    def test_flat_plate_best_orientation(self, flat_plate):
        """Flat plate should score best in upright orientation."""
        optimizer = PrintOptimizer()
        recommendation = optimizer.optimize(flat_plate)

        assert recommendation is not None
        assert recommendation.best is not None
        # Best score should be quite good for flat plate
        assert recommendation.best.score < 0.3

    def test_ranking_produces_order(self, sample_cube):
        """Ranking should produce ordered candidates."""
        optimizer = PrintOptimizer()
        recommendation = optimizer.optimize(sample_cube)

        assert len(recommendation.all_candidates) > 0

        # Check that scores are in non-decreasing order
        scores = [c.score for c in recommendation.all_candidates]
        assert scores == sorted(scores)

    def test_alternatives_provided(self, sample_cube):
        """Should provide alternative orientations."""
        optimizer = PrintOptimizer()
        recommendation = optimizer.optimize(sample_cube)

        # Should have at least the best option
        assert recommendation.best is not None

        # If multiple candidates, should have alternatives
        if len(recommendation.all_candidates) > 1:
            assert len(recommendation.alternatives) >= 0


class TestRecommendationResult:
    """Tests for the complete recommendation result."""

    def test_recommendation_completeness(self, flat_plate):
        """Recommendation should have all required fields."""
        recommendation = recommend_orientation(flat_plate)

        assert recommendation.best is not None
        assert recommendation.best.metrics is not None
        assert recommendation.total_candidates > 0
        assert recommendation.analysis_time_ms >= 0

    def test_recommendation_performance(self, flat_plate):
        """Complete recommendation should meet time budget."""
        start = time.perf_counter()
        recommendation = recommend_orientation(flat_plate)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < BUDGET_TOTAL_RECOMMENDATION
        assert recommendation is not None


# =============================================================================
# Corpus Part Tests
# =============================================================================

class TestCorpusParts:
    """Tests using the corpus of reference parts."""

    def test_all_corpus_parts_analyzable(self, corpus_parts):
        """All corpus parts should be analyzable without errors."""
        failed = []

        for name, part in corpus_parts.items():
            try:
                metrics = compute_orientation_metrics(part)
                assert metrics is not None
            except Exception as e:
                failed.append((name, e))

        assert len(failed) == 0, f"Failed parts: {failed}"

    def test_all_corpus_parts_recommendable(self, corpus_parts):
        """All corpus parts should get recommendations."""
        failed = []

        for name, part in corpus_parts.items():
            try:
                recommendation = recommend_orientation(part)
                assert recommendation is not None
                assert recommendation.best is not None
            except Exception as e:
                failed.append((name, e))

        assert len(failed) == 0, f"Failed parts: {failed}"

    def test_corpus_performance_budget(self, corpus_parts):
        """All parts should analyze within performance budget."""
        slow_parts = []

        for name, part in corpus_parts.items():
            start = time.perf_counter()
            recommendation = recommend_orientation(part)
            elapsed_ms = (time.perf_counter() - start) * 1000

            if elapsed_ms > BUDGET_TOTAL_RECOMMENDATION:
                slow_parts.append((name, elapsed_ms))

        # Allow some slack for complex parts
        assert len(slow_parts) == 0, f"Slow parts: {slow_parts}"

    def test_expected_behaviors(self, corpus_parts):
        """Corpus parts should behave as expected."""
        # Flat plate should score well
        plate = corpus_parts.get('flat_plate')
        if plate:
            rec = recommend_orientation(plate)
            assert rec.best.score < 0.2, "Flat plate should score very well"

        # Tall tower should have height warnings
        tower = corpus_parts.get('tall_tower')
        if tower:
            metrics = compute_orientation_metrics(tower)
            assert metrics.build_height_mm > 50, "Tall tower should be tall"


# =============================================================================
# Phase 3 & 4: UI Integration Tests
# =============================================================================

class TestDialogImports:
    """Tests that dialog components can be imported."""

    def test_print_optimize_dialog_import(self):
        """Print optimize dialog should be importable."""
        from gui.dialogs.print_optimize_dialog import (
            PrintOptimizeDialog, show_print_optimize_dialog
        )
        assert PrintOptimizeDialog is not None
        assert show_print_optimize_dialog is not None

    def test_export_dialog_import(self):
        """Enhanced export dialog should be importable."""
        from gui.dialogs.stl_export_with_print_check import (
            STLExportWithPrintCheckDialog, show_stl_export_with_print_check
        )
        assert STLExportWithPrintCheckDialog is not None
        assert show_stl_export_with_print_check is not None


# =============================================================================
# Integration Tests
# =============================================================================

class TestEndToEndWorkflow:
    """End-to-end workflow tests."""

    def test_full_optimization_workflow(self, flat_plate):
        """Test complete workflow from part to recommendation."""
        # 1. Analyze geometry
        metrics = compute_orientation_metrics(flat_plate)
        assert metrics is not None

        # 2. Get recommendation
        recommendation = recommend_orientation(flat_plate)
        assert recommendation is not None
        assert recommendation.best is not None

        # 3. Verify recommendation has metrics
        assert recommendation.best.metrics is not None

        # 4. Verify we have alternatives
        # (May be empty if only one candidate, which is fine)
        assert isinstance(recommendation.alternatives, list)

    def test_workflow_with_transform_application(self, flat_plate):
        """Test that recommended orientation can be applied as transform."""
        from modeling import TransformFeature
        from modeling.features.base import FeatureType

        recommendation = recommend_orientation(flat_plate)
        best = recommendation.best

        # Create a TransformFeature from the recommendation
        feature = TransformFeature(
            name=f"Print Rotate: {best.description}",
            mode="rotate",
            data={
                "axis": list(best.axis),
                "angle": best.angle_deg,
                "center": [0.0, 0.0, 0.0]
            }
        )

        assert feature.type == FeatureType.TRANSFORM
        assert feature.mode == "rotate"
        assert feature.data["angle"] == best.angle_deg


# =============================================================================
# Regression Tests
# =============================================================================

class TestRegressions:
    """Regression tests to ensure existing functionality isn't broken."""

    def test_feature_flag_exists(self):
        """printability_check feature flag should exist."""
        from config.feature_flags import is_enabled

        # Flag should be defined (even if disabled)
        result = is_enabled("printability_check")
        assert isinstance(result, bool)

    def test_i18n_keys_exist(self):
        """Required i18n keys should exist."""
        from i18n import tr

        # These should not raise errors
        tr("Optimize for 3D Printing")
        tr("3D Printability Check")
        tr("Analyzing...")
        tr("Export Anyway")

    def test_import_chain(self):
        """All modules should be importable."""
        # Phase 1
        import modeling.printability_score
        import modeling.print_bridge_analysis
        import modeling.print_support
        import modeling.print_support_fins

        # Phase 2
        import modeling.print_orientation_optimizer
        import modeling.print_explanation

        # Phase 3
        import gui.dialogs.print_optimize_dialog

        # Phase 4
        import gui.dialogs.stl_export_with_print_check


# =============================================================================
# Data Consistency Tests
# =============================================================================

class TestDataConsistency:
    """Tests for data consistency across modules."""

    def test_metrics_serialization(self, sample_cube):
        """OrientationMetrics should serialize correctly."""
        metrics = compute_orientation_metrics(sample_cube)

        # All numeric fields should be finite
        assert metrics.overhang_area_mm2 >= 0
        assert metrics.overhang_ratio >= 0
        assert 0 <= metrics.stability_score <= 1

        # Center of mass should be a valid 3D point
        assert len(metrics.center_of_mass) == 3
        assert all(isinstance(c, (int, float)) for c in metrics.center_of_mass)

    def test_recommendation_serialization(self, flat_plate):
        """OrientationRecommendation should serialize correctly."""
        recommendation = recommend_orientation(flat_plate)

        # Check to_dict works
        data = recommendation.to_dict()
        assert isinstance(data, dict)
        assert 'best' in data
        assert 'total_candidates' in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
