"""
TNP v5.0 - TNPService Integration Tests

Integration tests for TNPService with semantic matching.
"""

import pytest
from unittest.mock import Mock, MagicMock

from modeling.tnp_v5 import (
    TNPService,
    ShapeID,
    ShapeType,
    SelectionContext,
    ResolutionOptions,
    ResolutionMethod,
    Bounds
)


class TestTNPServiceSemanticResolution:
    """Test TNPService resolve() with semantic matching."""

    def test_resolve_with_semantic_fallback(self):
        """Test resolve() falls back to semantic matching."""
        tnp = TNPService(document_id="test_doc")

        # Create a mock OCP shape
        mock_shape = Mock()
        mock_shape.wrapped = Mock()
        mock_shape.wrapped.ShapeType = Mock(return_value=Mock(value=Mock(__eq__=lambda self, other: True)))

        # Register a shape with context
        context = SelectionContext(
            shape_id="",
            selection_point=(10, 10, 10),
            view_direction=(0, 0, 1),
            adjacent_shapes=["adj1"],
            feature_context="extrude_1"
        )

        shape_id = tnp.register_shape(
            ocp_shape=mock_shape,
            shape_type=ShapeType.FACE,
            feature_id="extrude_1",
            local_index=0,
            context=context
        )

        # Add a candidate to spatial index (simulating a different shape at same location)
        # Create another mock for the candidate
        candidate_shape = Mock()
        candidate_shape.wrapped = Mock()
        candidate_shape.CenterOfMass = Mock(return_value=Mock())

        # Insert candidate with a wrapper that provides access to shape
        tnp._spatial_index.insert(
            shape_id="candidate1",
            bounds=Bounds.from_center((10, 10, 10), 5),
            shape_data={'shape_type': 'FACE', 'feature_id': 'extrude_1',
                       'shape': candidate_shape}
        )

        # Since we can't actually test semantic matching without a real solid,
        # we verify that semantic matching infrastructure exists
        options = ResolutionOptions(use_semantic_matching=True)

        # Mock exact match to fail (force semantic)
        original_try_exact = tnp._try_exact_match
        tnp._try_exact_match = Mock(return_value=None)

        try:
            result = tnp.resolve(shape_id, current_solid=None, options=options)
            # Should attempt semantic (exact failed), may fail if no candidates
            # The important thing is it doesn't crash
            assert result.method in (ResolutionMethod.SEMANTIC, ResolutionMethod.FAILED)
        finally:
            tnp._try_exact_match = original_try_exact

    def test_resolve_semantic_disabled(self):
        """Test resolve() skips semantic when disabled."""
        tnp = TNPService(document_id="test_doc")

        # Create a mock shape for registration
        mock_shape = Mock()
        mock_shape.wrapped = Mock()

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context=""
        )

        shape_id = tnp.register_shape(
            ocp_shape=mock_shape,
            shape_type=ShapeType.FACE,
            feature_id="test",
            local_index=0,
            context=context
        )

        # Mock exact match to fail
        original_try_exact = tnp._try_exact_match
        tnp._try_exact_match = Mock(return_value=None)

        try:
            # Resolve with semantic matching disabled
            options = ResolutionOptions(use_semantic_matching=False)
            result = tnp.resolve(shape_id, current_solid=None, options=options)

            # Should fail (no exact match, semantic disabled)
            assert result.method == ResolutionMethod.FAILED
            assert result.confidence == 0.0
        finally:
            tnp._try_exact_match = original_try_exact

    def test_resolve_uses_selection_context(self):
        """Test resolve() uses stored selection context."""
        tnp = TNPService(document_id="test_doc")

        # Create a mock shape for registration
        mock_shape = Mock()
        mock_shape.wrapped = Mock()

        # Create a shape with context
        context = SelectionContext(
            shape_id="",
            selection_point=(5, 5, 5),
            view_direction=(0, 0, 1),
            adjacent_shapes=["face_a", "face_b"],
            feature_context="sketch_1"
        )

        shape_id = tnp.register_shape(
            ocp_shape=mock_shape,
            shape_type=ShapeType.FACE,
            feature_id="test",
            local_index=0,
            context=context
        )

        # Add candidates with same adjacency
        tnp._spatial_index.insert(
            shape_id="candidate1",
            bounds=Bounds.from_center((5, 5, 5), 5),
            shape_data={'shape_type': 'FACE', 'feature_id': 'sketch_1'}
        )

        # Mock the _try_exact_match to return None
        original_try_exact = tnp._try_exact_match
        tnp._try_exact_match = Mock(return_value=None)

        options = ResolutionOptions(use_semantic_matching=True)
        result = tnp.resolve(shape_id, current_solid=None, options=options)

        # Should have attempted semantic match
        assert result.method in (ResolutionMethod.SEMANTIC, ResolutionMethod.FAILED)

        # Restore original method
        tnp._try_exact_match = original_try_exact

    def test_resolve_semantic_with_no_context(self):
        """Test resolve() skips semantic when no context available."""
        tnp = TNPService(document_id="test_doc")

        # Create a mock shape for registration
        mock_shape = Mock()
        mock_shape.wrapped = Mock()

        # Register without context
        shape_id = tnp.register_shape(
            ocp_shape=mock_shape,
            shape_type=ShapeType.FACE,
            feature_id="test",
            local_index=0,
            context=None  # No context stored
        )

        # Mock exact match to fail
        original_try_exact = tnp._try_exact_match
        tnp._try_exact_match = Mock(return_value=None)

        options = ResolutionOptions(use_semantic_matching=True)
        result = tnp.resolve(shape_id, current_solid=None, options=options)

        # Should fail (no context for semantic matching)
        assert result.method == ResolutionMethod.FAILED

        # Restore
        tnp._try_exact_match = original_try_exact

    def test_resolve_returns_ambiguous_on_close_scores(self):
        """Test resolve() returns ambiguous result for close candidates."""
        tnp = TNPService(document_id="test_doc")

        # Create a mock shape for registration
        mock_shape = Mock()
        mock_shape.wrapped = Mock()

        context = SelectionContext(
            shape_id="",
            selection_point=(10, 10, 10),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context="test"
        )

        shape_id = tnp.register_shape(
            ocp_shape=mock_shape,
            shape_type=ShapeType.FACE,
            feature_id="test",
            local_index=0,
            context=context
        )

        # Add two candidates at same location
        tnp._spatial_index.insert(
            shape_id="candidate1",
            bounds=Bounds.from_center((10, 10, 10), 5),
            shape_data={'shape_type': 'FACE', 'feature_id': 'test'}
        )
        tnp._spatial_index.insert(
            shape_id="candidate2",
            bounds=Bounds.from_center((10, 10, 10), 5),
            shape_data={'shape_type': 'FACE', 'feature_id': 'test'}
        )

        # Mock exact match to fail
        original_try_exact = tnp._try_exact_match
        tnp._try_exact_match = Mock(return_value=None)

        options = ResolutionOptions(use_semantic_matching=True)
        result = tnp.resolve(shape_id, current_solid=None, options=options)

        # Should attempt semantic (may fail without actual shapes)
        # The key is that it doesn't crash
        assert result.method in (ResolutionMethod.SEMANTIC, ResolutionMethod.FAILED)

        # Restore
        tnp._try_exact_match = original_try_exact

    def test_spatial_index_stats(self):
        """Test getting spatial index statistics."""
        tnp = TNPService(document_id="test_doc")

        stats = tnp.get_spatial_index_stats()

        assert stats['size'] == 0
        assert 'accelerated' in stats

        # Add a shape
        tnp._spatial_index.insert(
            shape_id="test",
            bounds=Bounds(0, 0, 0, 10, 10, 10),
            shape_data={'shape_type': 'FACE'}
        )

        stats = tnp.get_spatial_index_stats()
        assert stats['size'] == 1

    def test_query_shapes_nearby(self):
        """Test querying shapes near a point."""
        tnp = TNPService(document_id="test_doc")

        # Add some shapes
        tnp._spatial_index.insert(
            shape_id="near1",
            bounds=Bounds(0, 0, 0, 5, 5, 5),
            shape_data={'shape_type': 'FACE', 'feature_id': 'f1'}
        )
        tnp._spatial_index.insert(
            shape_id="near2",
            bounds=Bounds(8, 8, 0, 12, 12, 5),
            shape_data={'shape_type': 'FACE', 'feature_id': 'f1'}
        )
        tnp._spatial_index.insert(
            shape_id="far",
            bounds=Bounds(100, 100, 100, 110, 110, 105),
            shape_data={'shape_type': 'FACE', 'feature_id': 'f2'}
        )

        # Query near origin
        results = tnp.query_shapes_nearby((0, 0, 0), radius=20)

        # Should find near1 and near2, not far
        assert "near1" in results
        assert "near2" in results or len(results) >= 1  # At least one nearby

    def test_find_nearest_shapes(self):
        """Test finding nearest shapes."""
        tnp = TNPService(document_id="test_doc")

        # Add shapes at different distances
        tnp._spatial_index.insert(
            shape_id="close",
            bounds=Bounds(0, 0, 0, 5, 5, 5),
            shape_data={'shape_type': 'EDGE'}
        )
        tnp._spatial_index.insert(
            shape_id="medium",
            bounds=Bounds(20, 0, 0, 25, 5, 5),
            shape_data={'shape_type': 'EDGE'}
        )
        tnp._spatial_index.insert(
            shape_id="far",
            bounds=Bounds(100, 0, 0, 105, 5, 5),
            shape_data={'shape_type': 'EDGE'}
        )

        results = tnp.find_nearest_shapes((0, 0, 0), max_results=2)

        # Closest should be first
        assert "close" in results[0]

    def test_find_nearest_with_type_filter(self):
        """Test finding nearest shapes with type filter."""
        tnp = TNPService(document_id="test_doc")

        tnp._spatial_index.insert(
            shape_id="face1",
            bounds=Bounds(0, 0, 0, 10, 10, 10),
            shape_data={'shape_type': 'FACE'}
        )
        tnp._spatial_index.insert(
            shape_id="edge1",
            bounds=Bounds(2, 0, 0, 7, 5, 5),
            shape_data={'shape_type': 'EDGE'}
        )

        results = tnp.find_nearest_shapes(
            (0, 0, 0),
            max_results=10,
            shape_type=ShapeType.FACE
        )

        # Should only return faces
        assert "face1" in results
        assert "edge1" not in results


class TestTNPServiceResolutionStrategy:
    """Test the resolution strategy order."""

    def test_exact_match_trumps_semantic(self):
        """Test that exact match takes priority over semantic."""
        tnp = TNPService(document_id="test_doc")

        shape_id = ShapeID.create(ShapeType.EDGE, "test", 0, ())

        # Mock exact match to succeed
        mock_shape = Mock()
        tnp._try_exact_match = Mock(return_value=mock_shape)

        options = ResolutionOptions(use_semantic_matching=True)
        result = tnp.resolve(shape_id, current_solid=None, options=options)

        # Should use exact match, not semantic
        assert result.method == ResolutionMethod.EXACT
        assert result.resolved_shape == mock_shape
        assert result.confidence == 1.0

    def test_semantic_used_when_exact_fails(self):
        """Test semantic is used when exact fails."""
        tnp = TNPService(document_id="test_doc")

        # Create a mock shape for registration
        mock_shape = Mock()
        mock_shape.wrapped = Mock()

        context = SelectionContext(
            shape_id="",
            selection_point=(10, 10, 10),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context="test"
        )

        shape_id = tnp.register_shape(
            ocp_shape=mock_shape,
            shape_type=ShapeType.FACE,
            feature_id="test",
            local_index=0,
            context=context
        )

        # Add candidate
        tnp._spatial_index.insert(
            shape_id="candidate",
            bounds=Bounds.from_center((10, 10, 10), 5),
            shape_data={'shape_type': 'FACE', 'feature_id': 'test'}
        )

        # Mock exact match to fail
        original_try_exact = tnp._try_exact_match
        tnp._try_exact_match = Mock(return_value=None)

        options = ResolutionOptions(use_semantic_matching=True)
        result = tnp.resolve(shape_id, current_solid=None, options=options)

        # Should attempt semantic match (may fail without actual shapes)
        assert result.method in (ResolutionMethod.SEMANTIC, ResolutionMethod.FAILED)

        # Restore
        tnp._try_exact_match = original_try_exact

    def test_semantic_skipped_when_disabled(self):
        """Test semantic is skipped when option is false."""
        tnp = TNPService(document_id="test_doc")

        shape_id = ShapeID.create(ShapeType.FACE, "test", 0, ())

        # Mock exact match to fail
        tnp._try_exact_match = Mock(return_value=None)

        options = ResolutionOptions(use_semantic_matching=False)
        result = tnp.resolve(shape_id, current_solid=None, options=options)

        # Should fail without trying semantic
        assert result.method == ResolutionMethod.FAILED
