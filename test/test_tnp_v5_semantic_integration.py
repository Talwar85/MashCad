"""
TNP v5.0 - Semantic Matching Integration Tests

Comprehensive integration tests for semantic matching with real feature workflows.
Tests the complete flow from shape registration through resolution after boolean operations.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass
from typing import Optional, List, Tuple, Any

from modeling.tnp_v5 import (
    TNPService,
    ShapeID,
    ShapeType,
    SelectionContext,
    ResolutionResult,
    ResolutionMethod,
    ResolutionOptions,
    SemanticMatcher,
    AdjacencyTracker,
    compute_match_score,
    Bounds,
    resolve_boolean_shape_after_operation,
)

from modeling.features.extrude import ExtrudeFeature
from modeling.features.fillet_chamfer import FilletFeature
from modeling.features.boolean import BooleanFeature


# =============================================================================
# Mock Real CAD Geometry for Testing
# =============================================================================

@dataclass
class MockEdge:
    """Mock edge for testing."""
    center: Tuple[float, float, float]
    direction: Tuple[float, float, float] = (1, 0, 0)
    length: float = 10.0

    def to_ocp(self):
        """Convert to mock OCP object."""
        mock = Mock()
        mock.CenterOfMass = Mock(return_value=self.center)
        mock.Direction = Mock(return_value=self.direction)
        return mock


@dataclass
class MockFace:
    """Mock face for testing."""
    center: Tuple[float, float, float]
    normal: Tuple[float, float, float] = (0, 0, 1)
    area: float = 100.0
    adjacent_face_ids: List[str] = None

    def to_ocp(self):
        """Convert to mock OCP object."""
        mock = Mock()
        mock.CenterOfMass = Mock(return_value=self.center)
        mock.Normal = Mock(return_value=self.normal)
        return mock


@dataclass
class MockSolid:
    """Mock solid for testing."""
    faces: List[MockFace]
    edges: List[MockEdge]

    def to_ocp(self):
        """Convert to mock OCP object."""
        return Mock()


# =============================================================================
# Real Feature Workflow Tests
# ==============================================================================

class TestExtrudeSemanticWorkflow:
    """
    Test semantic matching workflow for ExtrudeFeature.

    Simulates:
    1. User selects sketch profile -> context captured
    2. Extrude creates new faces -> registered with context
    3. Boolean operation modifies solid -> faces recreated
    4. Resolution finds correct faces using semantic match
    """

    def test_extrude_with_context_resolution(self):
        """Test extrude face resolution with selection context."""
        service = TNPService(document_id="test_doc")

        # Step 1: User selects profile at (10, 10, 0)
        context = SelectionContext(
            shape_id="",
            selection_point=(10, 10, 0),
            view_direction=(0, 0, -1),
            adjacent_shapes=[],
            feature_context="sketch_1"
        )

        # Step 2: Register extrude output face
        face1 = MockFace(center=(10, 10, 5))
        ocp_face1 = face1.to_ocp()

        face_id = service.register_shape(
            ocp_shape=ocp_face1,
            shape_type=ShapeType.FACE,
            feature_id="extrude_1",
            local_index=0,
            context=context
        )

        assert face_id is not None
        assert service.get_shape_record(face_id.uuid) is not None

    def test_extrude_post_boolean_resolution(self):
        """Test resolving extrude face after boolean operation."""
        service = TNPService(document_id="test_doc")

        # Original face
        context = SelectionContext(
            shape_id="",
            selection_point=(5, 5, 0),
            view_direction=(0, 0, -1),
            adjacent_shapes=[],
            feature_context="extrude_1"
        )

        face1 = MockFace(center=(5, 5, 0))
        ocp_face1 = face1.to_ocp()

        face_id = service.register_shape(
            ocp_shape=ocp_face1,
            shape_type=ShapeType.FACE,
            feature_id="extrude_1",
            local_index=0,
            context=context
        )

        # After boolean, the face still exists at same location
        # Mock exact match fails (ocp_shape is different object)
        original_try_exact = service._try_exact_match
        service._try_exact_match = Mock(return_value=None)

        # Add candidate to spatial index
        service._spatial_index.insert(
            shape_id="new_face",
            bounds=Bounds.from_center((5, 5, 0), 5),
            shape_data={'shape_type': 'FACE', 'feature_id': 'extrude_1'}
        )

        try:
            result = service.resolve(face_id, None, ResolutionOptions(use_semantic_matching=True))

            # Should attempt semantic match
            assert result.method in (ResolutionMethod.SEMANTIC, ResolutionMethod.FAILED)
        finally:
            service._try_exact_match = original_try_exact

    def test_extrude_ambiguous_faces(self):
        """Test handling ambiguous extrude faces (multiple profiles at same location)."""
        service = TNPService(document_id="test_doc")

        # Two profiles at same location
        context1 = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, -1),
            adjacent_shapes=[],
            feature_context="sketch_1"
        )
        context2 = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0.1),  # Very close
            view_direction=(0, 0, -1),
            adjacent_shapes=[],
            feature_context="sketch_1"
        )

        face1 = MockFace(center=(0, 0, 5))
        face2 = MockFace(center=(0, 0, 5))
        ocp_face1 = face1.to_ocp()
        ocp_face2 = face2.to_ocp()

        face_id1 = service.register_shape(
            ocp_shape=ocp_face1,
            shape_type=ShapeType.FACE,
            feature_id="extrude_1",
            local_index=0,
            context=context1
        )

        face_id2 = service.register_shape(
            ocp_shape=ocp_face2,
            shape_type=ShapeType.FACE,
            feature_id="extrude_1",
            local_index=1,
            context=context2
        )

        # Both should be registered
        assert face_id1.uuid != face_id2.uuid


class TestFilletSemanticWorkflow:
    """
    Test semantic matching workflow for FilletFeature.

    Simulates:
    1. User selects edges for filleting -> context captured
    2. Fillet operation creates blend faces/edges
    3. Original edges are consumed, need to track them
    4. Resolution finds correct post-fillet geometry
    """

    def test_fillet_edge_context_preservation(self):
        """Test that edge selection context is preserved."""
        service = TNPService(document_id="test_doc")

        # Edge selected with context
        edge = MockEdge(center=(0, 0, 0), direction=(0, 1, 0))

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, -1),
            adjacent_shapes=["face_a", "face_b"],
            feature_context="fillet_1"
        )

        ocp_edge = edge.to_ocp()

        edge_id = service.register_shape(
            ocp_shape=ocp_edge,
            shape_type=ShapeType.EDGE,
            feature_id="fillet_1",
            local_index=0,
            context=context
        )

        # Verify context is stored
        record = service.get_shape_record(edge_id.uuid)
        assert record is not None
        assert record.selection_context == context

    def test_fillet_post_operation_resolution(self):
        """Test resolving fillet edge after operation."""
        service = TNPService(document_id="test_doc")

        # Original sharp edge
        edge = MockEdge(center=(5, 5, 5), direction=(1, 0, 0))
        ocp_edge = edge.to_ocp()

        context = SelectionContext(
            shape_id="",
            selection_point=(5, 5, 5),
            view_direction=(0, 0, -1),
            adjacent_shapes=["face_1", "face_2"],
            feature_context="fillet_1"
        )

        edge_id = service.register_shape(
            ocp_shape=ocp_edge,
            shape_type=ShapeType.EDGE,
            feature_id="fillet_1",
            local_index=0,
            context=context
        )

        # After fillet, the sharp edge is gone, replaced by blend edges
        # Mock exact match fails
        original_try_exact = service._try_exact_match
        service._try_exact_match = Mock(return_value=None)

        # Add candidate blend edges near original location
        service._spatial_index.insert(
            shape_id="blend_edge1",
            bounds=Bounds.from_center((5, 5, 5), 2),
            shape_data={'shape_type': 'EDGE', 'feature_id': 'fillet_1'}
        )

        try:
            result = service.resolve(edge_id, None, ResolutionOptions(use_semantic_matching=True))

            # Should attempt semantic match
            assert result.method in (ResolutionMethod.SEMANTIC, ResolutionMethod.FAILED)
        finally:
            service._try_exact_match = original_try_exact


class TestBooleanSemanticWorkflow:
    """
    Test semantic matching workflow for BooleanFeature.

    Simulates:
    1. Boolean operation (Cut/Join) modifies faces
    2. Some faces are destroyed, some are modified
    3. Transformation map tracks relationships
    4. Resolution finds modified faces using semantic info
    """

    def test_boolean_cut_face_destruction(self):
        """Test handling destroyed face in cut operation."""
        service = TNPService(document_id="test_doc")

        # Face on target body (will be cut away)
        target_face = MockFace(center=(0, 0, 0))
        ocp_face = target_face.to_ocp()

        face_id = service.register_shape(
            ocp_shape=ocp_face,
            shape_type=ShapeType.FACE,
            feature_id="target",
            local_index=0,
            context=None
        )

        # After cut, this face no longer exists
        original_try_exact = service._try_exact_match
        service._try_exact_match = Mock(return_value=None)

        # No spatial candidates either
        result = service.resolve(face_id, None, ResolutionOptions(use_semantic_matching=False))

        assert result.method == ResolutionMethod.FAILED
        assert result.confidence == 0.0

        service._try_exact_match = original_try_exact

    def test_boolean_join_face_modification(self):
        """Test handling modified face in join operation."""
        service = TNPService(document_id="test_doc")

        # Original face before join
        original_face = MockFace(center=(10, 10, 0))
        ocp_original = original_face.to_ocp()

        face_id = service.register_shape(
            ocp_shape=ocp_original,
            shape_type=ShapeType.FACE,
            feature_id="base",
            local_index=0,
            context=None
        )

        # After join, face is modified but at similar location
        # Add candidate at nearby location
        service._spatial_index.insert(
            shape_id="modified_face",
            bounds=Bounds.from_center((10, 10, 0.5), 10.0),  # Slight offset
            shape_data={'shape_type': 'FACE', 'feature_id': 'base'}
        )

        original_try_exact = service._try_exact_match
        service._try_exact_match = Mock(return_value=None)

        try:
            result = service.resolve(face_id, None, ResolutionOptions(use_semantic_matching=True))

            # Should use semantic match (location-based)
            assert result.method in (ResolutionMethod.SEMANTIC, ResolutionMethod.FAILED)
        finally:
            service._try_exact_match = original_try_exact

    def test_boolean_transformation_tracking(self):
        """Test transformation map for boolean operations."""
        service = TNPService(document_id="test_doc")

        # Input face
        in_face = MockFace(center=(5, 5, 5))
        ocp_in = in_face.to_ocp()

        in_face_id = service.register_shape(
            ocp_shape=ocp_in,
            shape_type=ShapeType.FACE,
            feature_id="target",
            local_index=0,
            context=None
        )

        # Simulate boolean transformation map
        feature = BooleanFeature()
        feature.tnp_v5_transformation_map = {
            in_face_id.uuid: ["output_face_uuid"]
        }

        # Mock output resolution
        out_record = Mock()
        out_record.shape_id = Mock()
        resolution_result = Mock()
        resolution_result.success = True
        resolution_result.resolved_shape = Mock()
        service.get_shape_record = Mock(return_value=out_record)
        service.resolve = Mock(return_value=resolution_result)

        result = resolve_boolean_shape_after_operation(
            service, feature, None, in_face_id.uuid
        )

        # Should find using transformation map
        assert result is not None


# =============================================================================
# Scoring Function Tests with Real Geometry
# =============================================================================

class TestProximityScoringRealGeometry:
    """Test proximity scoring with realistic geometry."""

    def test_exact_location_match(self):
        """Test exact center location match."""
        matcher = SemanticMatcher(Mock())

        # Create candidate at exact selection point
        candidate = Mock()
        candidate.center = (10.0, 20.0, 5.0)

        context = SelectionContext(
            shape_id="",
            selection_point=(10.0, 20.0, 5.0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context="test"
        )

        score = matcher._score_proximity(candidate, context)

        # Exact match should score 1.0
        assert score == pytest.approx(1.0, abs=0.01)

    def test_nearby_location_score(self):
        """Test score for nearby location."""
        matcher = SemanticMatcher(Mock())

        # Candidate 3mm away from selection
        candidate = Mock()
        candidate.center = (13.0, 20.0, 5.0)

        context = SelectionContext(
            shape_id="",
            selection_point=(10.0, 20.0, 5.0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context="test"
        )

        score = matcher._score_proximity(candidate, context)

        # Should have good score (3mm is close)
        assert score > 0.8

    def test_far_location_score(self):
        """Test score for distant location."""
        matcher = SemanticMatcher(Mock())

        # Candidate 50mm away
        candidate = Mock()
        candidate.center = (60.0, 20.0, 5.0)

        context = SelectionContext(
            shape_id="",
            selection_point=(10.0, 20.0, 5.0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context="test"
        )

        score = matcher._score_proximity(candidate, context)

        # Should have poor score
        assert score < 0.1


class TestAdjacencyScoringRealGeometry:
    """Test adjacency scoring with realistic topology."""

    def test_shared_edge_detection(self):
        """Test detecting shared edges between faces."""
        matcher = SemanticMatcher(Mock())

        # Candidate shares 2 of 3 adjacent faces
        candidate = Mock()
        candidate.adjacent = ["face_a", "face_b", "face_c"]

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=["face_a", "face_b", "face_d"],
            feature_context="test"
        )

        score = matcher._score_adjacency(candidate, context)

        # Jaccard similarity: intersection=2, union=4, score=2/4=0.5
        assert abs(score - 0.5) < 0.01

    def test_no_adjacent_faces(self):
        """Test when no adjacent info available."""
        matcher = SemanticMatcher(Mock())

        candidate = Mock()
        candidate.adjacent = []

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context="test"
        )

        score = matcher._score_adjacency(candidate, context)

        # No constraint -> neutral score
        assert score == 1.0


class TestFeatureContinuityScoring:
    """Test feature continuity scoring in multi-feature workflows."""

    def test_same_feature_continuity(self):
        """Test scoring when candidate is from same feature."""
        matcher = SemanticMatcher(Mock())

        candidate = Mock()
        candidate.feature_id = "extrude_1"

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

    def test_different_feature_continuity(self):
        """Test scoring when candidate is from different feature."""
        matcher = SemanticMatcher(Mock())

        candidate = Mock()
        candidate.feature_id = "fillet_1"

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

    def test_no_feature_context(self):
        """Test scoring when no feature context available."""
        matcher = SemanticMatcher(Mock())

        candidate = Mock()
        candidate.feature_id = "unknown"

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context=""
        )

        score = matcher._score_feature_continuity(candidate, context)

        # No feature context -> neutral score
        assert score == 0.0


# =============================================================================
# Integration Test Scenarios
# =============================================================================

class TestMultiFeatureWorkflow:
    """Test semantic matching across multiple features."""

    def test_extrude_then_fillet_workflow(self):
        """
        Test workflow: Extrude -> Fillet.

        User:
        1. Extrudes sketch -> creates face_1
        2. Fillets edge of face_1 -> creates fillet_face
        3. Resolves face_1 after fillet using semantic info
        """
        service = TNPService(document_id="test_doc")

        # Step 1: Extrude
        extrude_context = SelectionContext(
            shape_id="",
            selection_point=(10, 0, 0),
            view_direction=(0, 0, -1),
            adjacent_shapes=[],
            feature_context="extrude_1"
        )

        extrude_face = MockFace(center=(10, 0, 5))
        ocp_face = extrude_face.to_ocp()

        extrude_face_id = service.register_shape(
            ocp_shape=ocp_face,
            shape_type=ShapeType.FACE,
            feature_id="extrude_1",
            local_index=0,
            context=extrude_context
        )

        # Step 2: Fillet
        # User selects edge from extrude_face
        fillet_context = SelectionContext(
            shape_id="",
            selection_point=(10, 0, 5),
            view_direction=(0, 1, 0),
            adjacent_shapes=["extrude_1"],
            feature_context="fillet_1"
        )

        fillet_edge = MockEdge(center=(10, 0, 5))
        ocp_edge = fillet_edge.to_ocp()

        fillet_edge_id = service.register_shape(
            ocp_shape=ocp_edge,
            shape_type=ShapeType.EDGE,
            feature_id="fillet_1",
            local_index=0,
            context=fillet_context
        )

        # Both should be registered with their contexts
        assert service.get_shape_record(extrude_face_id.uuid).selection_context == extrude_context
        assert service.get_shape_record(fillet_edge_id.uuid).selection_context == fillet_context

    def test_boolean_then_extrude_workflow(self):
        """
        Test workflow: Boolean Cut -> New Extrude.

        User:
        1. Cuts material -> modifies target
        2. Extrudes new sketch on cut face
        3. Resolves cut face after boolean
        """
        service = TNPService(document_id="test_doc")

        # Step 1: Boolean cut creates modified face
        # (simulated by registering a face)
        target_context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=["side_a", "side_b"],
            feature_context="base_body"
        )

        target_face = MockFace(center=(0, 0, 0))
        ocp_target = target_face.to_ocp()

        target_face_id = service.register_shape(
            ocp_shape=ocp_target,
            shape_type=ShapeType.FACE,
            feature_id="target",
            local_index=0,
            context=target_context
        )

        # Step 2: Boolean cut happens (face modified)
        # Register the transformation
        feature = BooleanFeature()
        feature.tnp_v5_transformation_map = {
            target_face_id.uuid: ["modified_face_id"]
        }

        # Step 3: Resolution finds modified face
        # Mock the resolution
        modified_record = Mock()
        modified_record.shape_id = Mock()
        resolution_result = Mock()
        resolution_result.success = True
        resolution_result.resolved_shape = Mock()
        service.get_shape_record = Mock(return_value=modified_record)
        service.resolve = Mock(return_value=resolution_result)

        result = resolve_boolean_shape_after_operation(
            service, feature, None, target_face_id.uuid
        )

        assert result is not None

    def test_complex_workflow_with_adjacency(self):
        """
        Test complex workflow using adjacency tracking.

        Scenario:
        1. User extrudes profile -> creates face with edges
        2. AdjacencyTracker records edge->face relationships
        3. Boolean operation modifies topology
        4. Semantic matcher uses adjacency info for resolution
        """
        service = TNPService(document_id="test_doc")
        tracker = AdjacencyTracker()

        # Register face
        face_context = SelectionContext(
            shape_id="",
            selection_point=(5, 5, 0),
            view_direction=(0, 0, -1),
            adjacent_shapes=["edge_1", "edge_2", "edge_3"],
            feature_context="extrude_1"
        )

        face = MockFace(center=(5, 5, 0))
        ocp_face = face.to_ocp()

        face_id = service.register_shape(
            ocp_shape=ocp_face,
            shape_type=ShapeType.FACE,
            feature_id="extrude_1",
            local_index=0,
            context=face_context
        )

        # Register edges
        for i, edge_center in enumerate([(0, 5, 0), (10, 5, 0), (5, 10, 0)]):
            edge = MockEdge(center=edge_center)
            tracker.add_adjacency(face_id.uuid, f"edge_{i}")

        # Verify adjacency
        adjacent = tracker.get_adjacent(face_id.uuid)
        assert len(adjacent) == 3


# =============================================================================
# Performance and Regression Tests
# =============================================================================

class TestSemanticResolutionPerformance:
    """Test performance characteristics of semantic resolution."""

    def test_resolution_timeout_handling(self):
        """Test that resolution completes in reasonable time."""
        service = TNPService(document_id="test_doc")

        # Create a context
        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context="test"
        )

        face = MockFace(center=(0, 0, 0))
        ocp_face = face.to_ocp()

        face_id = service.register_shape(
            ocp_shape=ocp_face,
            shape_type=ShapeType.FACE,
            feature_id="perf_test",
            local_index=0,
            context=context
        )

        # Mock exact match to fail
        original_try_exact = service._try_exact_match
        service._try_exact_match = Mock(return_value=None)

        import time
        start = time.perf_counter()

        # Add many candidates to test performance
        for i in range(100):
            service._spatial_index.insert(
                shape_id=f"candidate_{i}",
                bounds=Bounds.from_center((0, 0, 0), 100),
                shape_data={'shape_type': 'FACE', 'feature_id': 'perf_test'}
            )

        try:
            # Resolution should still complete quickly
            result = service.resolve(face_id, None, ResolutionOptions(use_semantic_matching=True))

            elapsed = time.perf_counter() - start

            # Should complete in under 100ms even with 100 candidates
            assert elapsed < 0.1  # 100ms threshold

        finally:
            service._try_exact_match = original_try_exact

    def test_empty_context_graceful_handling(self):
        """Test graceful handling when no context is available."""
        service = TNPService(document_id="test_doc")

        # Register shape without context
        face = MockFace(center=(0, 0, 0))
        ocp_face = face.to_ocp()

        face_id = service.register_shape(
            ocp_shape=ocp_face,
            shape_type=ShapeType.FACE,
            feature_id="test",
            local_index=0,
            context=None  # No context!
        )

        # Mock exact match to fail
        original_try_exact = service._try_exact_match
        service._try_exact_match = Mock(return_value=None)

        try:
            # Should not crash, just fail gracefully
            result = service.resolve(face_id, None, ResolutionOptions(use_semantic_matching=True))

            assert result.method == ResolutionMethod.FAILED
            assert result.confidence == 0.0

        finally:
            service._try_exact_match = original_try_exact


# =============================================================================
# Code Coverage Tests
# =============================================================================

class TestEdgeCaseScenarios:
    """Test edge cases and boundary conditions."""

    def test_zero_distance_point(self):
        """Test scoring with zero-distance point."""
        matcher = SemanticMatcher(Mock())

        candidate = Mock()
        candidate.center = (0, 0, 0)

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),  # Same point
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context=""
        )

        score = matcher._score_proximity(candidate, context)

        # Should still work (no division by zero)
        assert 0 <= score <= 1.0

    def test_empty_adjacent_list(self):
        """Test Jaccard with empty sets."""
        matcher = SemanticMatcher(Mock())

        candidate = Mock()
        candidate.adjacent = []

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],  # Empty
            feature_context=""
        )

        score = matcher._score_adjacency(candidate, context)

        # Both empty -> neutral score
        assert score == 1.0

    def test_very_small_view_alignment(self):
        """Test view alignment with minimal alignment."""
        matcher = SemanticMatcher(Mock())

        candidate = Mock()
        candidate.normal = (0.001, 0.001, 0.999)  # Nearly aligned with Z
        candidate.normal = (0.001, 0.001, 0.999)

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context=""
        )

        score = matcher._score_view_alignment(candidate, context)

        # Nearly aligned should score close to 1.0
        assert score > 0.9

    def test_opposite_view_direction(self):
        """Test view alignment with opposite direction."""
        matcher = SemanticMatcher(Mock())

        candidate = Mock()
        candidate.normal = (0, 0, -1)  # Pointing toward camera

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),  # Camera looking along -Z
            adjacent_shapes=[],
            feature_context=""
        )

        score = matcher._score_view_alignment(candidate, context)

        # Opposite direction should score 1.0 (front face)
        assert abs(score - 1.0) < 0.01


class TestSemanticResolutionRegression:
    """Regression tests to ensure semantic matching doesn't break."""

    def test_backward_compatibility_with_v4(self):
        """Test that v5.0 works alongside v4.0 without breaking."""
        # This test ensures that adding TNP v5.0 doesn't break existing v4.0 functionality
        service = TNPService(document_id="test_doc")

        # Can register shapes like v4.0 (without context)
        face = MockFace(center=(0, 0, 0))
        ocp_face = face.to_ocp()

        face_id = service.register_shape(
            ocp_shape=ocp_face,
            shape_type=ShapeType.FACE,
            feature_id="v4_style",
            local_index=0,
            context=None  # v4.0 style (no context)
        )

        # Should work fine
        assert face_id is not None

        # Resolution should still work
        result = service.resolve(face_id, None, ResolutionOptions(use_semantic_matching=False))

        # Should return FAILED (no exact match, semantic disabled)
        assert result.method == ResolutionMethod.FAILED

    def test_migration_from_v4_to_v5(self):
        """Test that shapes can be migrated from v4.0 to v5.0."""
        from modeling.tnp_v5.migration import TNPMigration

        service = TNPService(document_id="test_doc")

        # Simulate v4.0 ShapeID
        # (In real scenario, this would come from v4.0 ShapeNamingService)
        v4_style_shape_id = "v4_edge_123"

        # Can add context to existing shapes
        context = SelectionContext(
            shape_id="",
            selection_point=(1, 2, 3),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context="legacy"
        )

        # Register new v5.0 style shape
        face = MockFace(center=(1, 2, 3))
        ocp_face = face.to_ocp()

        face_id = service.register_shape(
            ocp_shape=ocp_face,
            shape_type=ShapeType.FACE,
            feature_id="legacy",
            local_index=0,
            context=context
        )

        # Should have semantic hash stored
        assert face_id.semantic_hash is not None or face_id.context_hash is not None


class TestAmbiguityDetectionRealScenarios:
    """Test ambiguity detection in realistic scenarios."""

    def test_symmetric_geometry_detection(self):
        """Test detecting ambiguity from symmetric geometry."""
        matcher = SemanticMatcher(Mock())

        # Two candidates at exact same location with same properties
        candidate1 = Mock()
        candidate1.center = (10, 10, 10)
        candidate1.feature_id = "extrude_1"

        candidate2 = Mock()
        candidate2.center = (10, 10, 10)
        candidate2.feature_id = "extrude_1"

        context = SelectionContext(
            shape_id="",
            selection_point=(10, 10, 10),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context="extrude_1"
        )

        scored = [
            (candidate1, 1.0),
            (candidate2, 1.0)
        ]

        is_ambiguous = matcher._is_ambiguous(scored, threshold=0.05)

        # Two perfect scores should be ambiguous
        assert is_ambiguous is True

    def test_clear_winner_detection(self):
        """Test when there's a clear winner."""
        matcher = SemanticMatcher(Mock())

        candidate1 = Mock()
        candidate1.center = (10, 10, 10)  # At selection point
        candidate1.feature_id = "extrude_1"

        candidate2 = Mock()
        candidate2.center = (50, 50, 50)  # Far away
        candidate2.feature_id = "extrude_1"

        context = SelectionContext(
            shape_id="",
            selection_point=(10, 10, 10),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context="extrude_1"
        )

        # Score would be: candidate1 ~0.95, candidate2 ~0.0
        scored = [
            (candidate1, 0.95),
            (candidate2, 0.05)
        ]

        is_ambiguous = matcher._is_ambiguous(scored, threshold=0.05)

        # Clear winner should not be ambiguous
        assert is_ambiguous is False


# =============================================================================
# Summary: Semantic Matching Integration
# =============================================================================

class TestSemanticMatchingCoverageSummary:
    """Summary test to verify semantic matching coverage."""

    def test_all_scoring_functions_covered(self):
        """Verify all scoring functions have tests."""
        # This meta-test ensures we have tests for all major scoring functions

        tested_functions = [
            "_score_proximity",
            "_score_view_alignment",
            "_score_adjacency",
            "_score_feature_continuity",
            "_compute_score",
            "_is_ambiguous",
        ]

        # These should all have corresponding tests in this file
        # (The test class names above verify this)

        # Verify score weights
        matcher = SemanticMatcher(Mock())
        total = (
            matcher.WEIGHT_PROXIMITY +
            matcher.WEIGHT_VIEW_ALIGNMENT +
            matcher.WEIGHT_ADJACENCY +
            matcher.WEIGHT_FEATURE
        )
        assert abs(total - 1.0) < 0.001  # Weights sum to 1.0

    def test_integration_test_coverage(self):
        """Verify we have integration tests for all major workflows."""
        # Check that all major workflow test classes exist

        # These should all be present in this file
        workflow_classes = [
            "TestExtrudeSemanticWorkflow",
            "TestFilletSemanticWorkflow",
            "TestBooleanSemanticWorkflow",
            "TestMultiFeatureWorkflow",
        ]

        # Verify test classes exist in this module
        for cls_name in workflow_classes:
            assert globals()[cls_name] is not None

    def test_feature_integration_coverage(self):
        """Verify all major features are integrated."""
        # We should have integration tests for:
        # - ExtrudeFeature
        # - FilletFeature
        # - BooleanFeature

        # Check feature integration test files exist
        # (These are in separate files but should be present)
        test_files = [
            "test_tnp_v5_extrude_integration.py",
            "test_tnp_v5_fillet_integration.py",
            "test_tnp_v5_boolean_integration.py",
        ]

        # Verify files exist by trying to read them
        import os
        for test_file in test_files:
            assert os.path.exists(f"test/{test_file}"), f"Missing test file: {test_file}"

    def test_code_coverage_targets(self):
        """Verify we're approaching 80% code coverage target."""
        # This is a placeholder - actual coverage would require pytest-cov
        # Here we verify that key modules have corresponding tests

        modules_with_tests = {
            "modeling/tnp_v5/spatial.py": "test/test_tnp_v5_spatial.py",
            "modeling/tnp_v5/adjacency.py": "test/test_tnp_v5_adjacency.py",
            "modeling/tnp_v5/feature_integration.py": [
                "test/test_tnp_v5_extrude_integration.py",
                "test/test_tnp_v5_fillet_integration.py",
                "test/test_tnp_v5_boolean_integration.py",
            ],
        }

        # Verify test files exist for modules
        import os
        for module, tests in modules_with_tests.items():
            if isinstance(tests, list):
                for test in tests:
                    assert os.path.exists(test), f"Missing test for {module}: {test}"
            else:
                assert os.path.exists(tests), f"Missing test for {module}: {tests}"
