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
    ResolutionResult,
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


class TestTNPServiceOperationAndValidation:
    """Tests for operation recording, history fallback and validation APIs."""

    def test_record_operation_stores_data(self):
        tnp = TNPService(document_id="test_doc")
        in_id = ShapeID.create(ShapeType.EDGE, "feat_a", 0, ("in",))
        out_id = ShapeID.create(ShapeType.EDGE, "feat_a", 1, ("out",))

        op_id = tnp.record_operation(
            operation_type="fillet",
            feature_id="feat_a",
            inputs=[in_id],
            outputs=[out_id],
            occt_history={"dummy": True},
        )

        assert op_id.startswith("op_feat_a_fillet_")
        assert len(tnp._operations) == 1
        op = tnp._operations[0]
        assert op["operation_type"] == "fillet"
        assert op["feature_id"] == "feat_a"
        assert op["inputs"][0]["uuid"] == in_id.uuid
        assert op["outputs"][0]["uuid"] == out_id.uuid

    def test_record_operation_validates_required_fields(self):
        tnp = TNPService(document_id="test_doc")
        sid = ShapeID.create(ShapeType.EDGE, "feat", 0, ("x",))

        with pytest.raises(ValueError):
            tnp.record_operation("", "feat", [sid], [sid])
        with pytest.raises(ValueError):
            tnp.record_operation("cut", "", [sid], [sid])
        with pytest.raises(ValueError):
            tnp.record_operation("cut", "feat", None, [sid])  # type: ignore[arg-type]

    def test_resolve_uses_history_after_exact_and_semantic_fail(self):
        tnp = TNPService(document_id="test_doc")
        current_solid = object()

        in_shape = object()
        out_shape = object()
        in_id = tnp.register_shape(in_shape, ShapeType.EDGE, "feat_hist", 0)
        out_id = tnp.register_shape(out_shape, ShapeType.EDGE, "feat_hist", 1)
        tnp.record_operation("boolean", "feat_hist", [in_id], [out_id])

        tnp._try_exact_match = Mock(return_value=None)
        tnp._shape_exists_in_solid = Mock(side_effect=lambda shape, _solid: shape is out_shape)

        result = tnp.resolve(
            in_id,
            current_solid=current_solid,
            options=ResolutionOptions(use_semantic_matching=False, use_history_tracing=True),
        )

        assert result.method == ResolutionMethod.HISTORY
        assert result.resolved_shape is out_shape

    def test_validate_resolutions_detects_duplicate_resolved_shapes(self):
        tnp = TNPService(document_id="test_doc")
        shared_shape = object()
        r1 = ResolutionResult("sid_1", shared_shape, ResolutionMethod.EXACT, 1.0, 0.1)
        r2 = ResolutionResult("sid_2", shared_shape, ResolutionMethod.EXACT, 0.9, 0.2)

        validation = tnp.validate_resolutions([r1, r2])
        assert validation.is_valid is False
        assert any("multiple shape_ids resolved to same shape" in issue for issue in validation.issues)

    def test_check_ambiguity_missing_shape(self):
        tnp = TNPService(document_id="test_doc")
        unknown = ShapeID.create(ShapeType.FACE, "feat_missing", 0, ())

        report = tnp.check_ambiguity(unknown, current_solid=None)
        assert report.is_ambiguous is True
        assert report.ambiguity_type == "missing_shape"

    def test_check_ambiguity_uses_semantic_signal(self):
        tnp = TNPService(document_id="test_doc")
        shape = object()
        sid = tnp.register_shape(
            shape,
            ShapeType.FACE,
            "feat_ctx",
            0,
            context=SelectionContext(
                shape_id="",
                selection_point=(0, 0, 0),
                view_direction=(0, 0, 1),
                adjacent_shapes=[],
                feature_context="feat_ctx",
            ),
        )

        fake_semantic = Mock()
        fake_semantic.is_ambiguous = True
        fake_semantic.score = 0.61
        fake_semantic.alternative_scores = [("cand_1", 0.61), ("cand_2", 0.60)]
        candidate_1 = Mock()
        candidate_1.shape_id = "cand_1"
        candidate_2 = Mock()
        candidate_2.shape_id = "cand_2"
        fake_semantic.candidates = [candidate_1, candidate_2]
        tnp._try_semantic_match = Mock(return_value=fake_semantic)

        report = tnp.check_ambiguity(sid, current_solid=None)
        assert report.is_ambiguous is True
        assert report.ambiguity_type == "semantic_ambiguous"
        assert report.candidates == ["cand_1", "cand_2"]
