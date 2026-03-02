"""
TNP v5.0 - FilletFeature Integration Tests

Integration tests for TNP v5.0 with FilletFeature and ChamferFeature.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from modeling.tnp_v5 import (
    TNPService,
    ShapeID,
    ShapeType,
    SelectionContext,
    get_tnp_v5_service,
    register_fillet_input_edges,
    register_fillet_output_edges,
    register_fillet_output_faces,
    store_fillet_data_in_feature,
    get_tnp_v5_input_edge_ids,
    resolve_fillet_edge_after_boolean,
    capture_edge_selection_context,
)

from modeling.features.fillet_chamfer import FilletFeature, ChamferFeature


class TestRegisterFilletInputEdges:
    """Test registering fillet input edges."""

    def test_register_none_edges(self):
        """Test with None edge list."""
        service = Mock(spec=TNPService)

        ids = register_fillet_input_edges(service, None, "fillet_1")

        assert ids == []

    def test_register_empty_list(self):
        """Test with empty edge list."""
        service = Mock(spec=TNPService)

        ids = register_fillet_input_edges(service, [], "fillet_1")

        assert ids == []

    def test_register_edges_success(self):
        """Test successful edge registration."""
        service = Mock(spec=TNPService)
        service.register_shape = Mock(return_value=Mock(uuid="test_uuid"))

        # Mock edges
        edge1 = Mock()
        edge1.wrapped = Mock()
        edge2 = Mock()
        edge2.wrapped = Mock()

        ids = register_fillet_input_edges(service, [edge1, edge2], "fillet_1")

        assert len(ids) == 2
        assert service.register_shape.call_count == 2

        # Verify first call was for EDGE type
        call1_kwargs = service.register_shape.call_args[1]
        assert call1_kwargs['shape_type'] == ShapeType.EDGE
        assert call1_kwargs['feature_id'] == "fillet_1"

    def test_register_with_selection_contexts(self):
        """Test with selection contexts."""
        service = Mock(spec=TNPService)
        service.register_shape = Mock(return_value=Mock(uuid="test_uuid"))

        edge = Mock()
        edge.wrapped = Mock()

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context="edge_1"
        )

        ids = register_fillet_input_edges(
            service, [edge], "fillet_1", [context]
        )

        assert len(ids) == 1
        call_kwargs = service.register_shape.call_args[1]
        assert call_kwargs['context'] == context


class TestRegisterFilletOutputEdges:
    """Test registering fillet output edges."""

    def test_register_none_solid(self):
        """Test with None solid."""
        service = Mock(spec=TNPService)

        ids = register_fillet_output_edges(service, None, "fillet_1")

        assert ids == []

    def test_register_edges_success(self):
        """Test successful output edge registration."""
        service = Mock(spec=TNPService)
        service.register_shape = Mock(return_value=Mock(uuid="test_uuid"))

        solid = Mock()
        edge = Mock()
        edge.wrapped = Mock()
        solid.edges = Mock(return_value=[edge, edge])

        ids = register_fillet_output_edges(service, solid, "fillet_1")

        assert len(ids) == 2
        assert service.register_shape.call_count == 2


class TestRegisterFilletOutputFaces:
    """Test registering fillet output faces."""

    def test_register_none_solid(self):
        """Test with None solid."""
        service = Mock(spec=TNPService)

        ids = register_fillet_output_faces(service, None, "fillet_1")

        assert ids == []

    def test_register_faces_success(self):
        """Test successful face registration."""
        service = Mock(spec=TNPService)
        service.register_shape = Mock(return_value=Mock(uuid="test_uuid"))

        solid = Mock()
        face = Mock()
        face.wrapped = Mock()
        solid.faces = Mock(return_value=[face])

        ids = register_fillet_output_faces(service, solid, "fillet_1")

        assert len(ids) == 1
        call_kwargs = service.register_shape.call_args[1]
        assert call_kwargs['shape_type'] == ShapeType.FACE


class TestStoreFilletDataInFeature:
    """Test storing fillet data in feature."""

    def test_store_input_edges(self):
        """Test storing input edge IDs."""
        feature = FilletFeature()
        edge_ids = [Mock(uuid="uuid1"), Mock(uuid="uuid2")]

        store_fillet_data_in_feature(feature, edge_ids)

        assert feature.tnp_v5_input_edge_ids == ["uuid1", "uuid2"]

    def test_store_with_output(self):
        """Test storing with output edges and faces."""
        feature = FilletFeature()
        input_ids = [Mock(uuid="in1")]
        output_edge_ids = [Mock(uuid="out1")]
        output_face_ids = [Mock(uuid="face1")]

        store_fillet_data_in_feature(
            feature, input_ids, output_edge_ids, output_face_ids
        )

        assert feature.tnp_v5_input_edge_ids == ["in1"]
        assert feature.tnp_v5_output_edge_ids == ["out1"]
        assert feature.tnp_v5_output_face_ids == ["face1"]

    def test_store_chamfer_feature(self):
        """Test storing in ChamferFeature."""
        feature = ChamferFeature()
        edge_ids = [Mock(uuid="uuid1")]

        store_fillet_data_in_feature(feature, edge_ids)

        assert feature.tnp_v5_input_edge_ids == ["uuid1"]


class TestGetTNPV5InputEdgeIds:
    """Test getting stored input edge IDs."""

    def test_get_from_fillet_feature(self):
        """Test getting from FilletFeature."""
        feature = FilletFeature()
        feature.tnp_v5_input_edge_ids = ["uuid1", "uuid2"]

        ids = get_tnp_v5_input_edge_ids(feature)

        assert ids == ["uuid1", "uuid2"]

    def test_get_from_chamfer_feature(self):
        """Test getting from ChamferFeature."""
        feature = ChamferFeature()
        feature.tnp_v5_input_edge_ids = ["uuid3"]

        ids = get_tnp_v5_input_edge_ids(feature)

        assert ids == ["uuid3"]

    def test_get_empty_when_missing(self):
        """Test when feature has no stored IDs."""
        feature = FilletFeature()

        ids = get_tnp_v5_input_edge_ids(feature)

        assert ids == []


class TestResolveFilletEdgeAfterBoolean:
    """Test resolving fillet edge after boolean operations."""

    def test_resolve_no_stored_ids(self):
        """Test with no stored edge IDs."""
        service = Mock(spec=TNPService)
        feature = FilletFeature()
        current_solid = Mock()

        result = resolve_fillet_edge_after_boolean(service, feature, current_solid, 0)

        assert result is None

    def test_resolve_index_out_of_range(self):
        """Test with index out of range."""
        service = Mock(spec=TNPService)
        feature = FilletFeature()
        feature.tnp_v5_input_edge_ids = ["uuid1"]

        current_solid = Mock()

        result = resolve_fillet_edge_after_boolean(service, feature, current_solid, 5)

        assert result is None

    def test_resolve_no_record_found(self):
        """Test when record is not found."""
        service = Mock(spec=TNPService)
        service.get_shape_record = Mock(return_value=None)

        feature = FilletFeature()
        feature.tnp_v5_input_edge_ids = ["uuid1"]

        current_solid = Mock()

        result = resolve_fillet_edge_after_boolean(service, feature, current_solid, 0)

        assert result is None

    def test_resolve_success(self):
        """Test successful resolution."""
        service = Mock(spec=TNPService)

        # Mock record
        record = Mock()
        record.shape_id = Mock()
        service.get_shape_record = Mock(return_value=record)

        # Mock resolution result
        resolution_result = Mock()
        resolution_result.success = True
        resolution_result.resolved_shape = Mock()
        service.resolve = Mock(return_value=resolution_result)

        feature = FilletFeature()
        feature.tnp_v5_input_edge_ids = ["uuid1"]

        current_solid = Mock()

        result = resolve_fillet_edge_after_boolean(service, feature, current_solid, 0)

        assert result is not None
        assert result == resolution_result.resolved_shape


class TestCaptureEdgeSelectionContext:
    """Test capturing edge selection context."""

    def test_capture_none_edge(self):
        """Test with None edge."""
        context = capture_edge_selection_context(None)
        assert context is None

    def test_capture_basic_context(self):
        """Test basic context capture."""
        edge = Mock()
        center = Mock()
        center.X = 1.0
        center.Y = 2.0
        center.Z = 3.0
        edge.center = Mock(return_value=center)

        context = capture_edge_selection_context(edge)

        assert context is not None
        assert context.selection_point == (1.0, 2.0, 3.0)
        assert context.feature_context == "edge_selection"

    def test_capture_with_adjacent_faces(self):
        """Test with adjacent faces."""
        edge = Mock()
        center = Mock(X=0, Y=0, Z=0)
        edge.center = Mock(return_value=center)

        face1 = Mock()
        face2 = Mock()

        context = capture_edge_selection_context(edge, adjacent_faces=[face1, face2])

        assert context is not None
        assert "face_0" in context.adjacent_shapes
        assert "face_1" in context.adjacent_shapes

    def test_capture_with_viewport(self):
        """Test with viewport."""
        edge = Mock()
        center = Mock(X=0, Y=0, Z=0)
        edge.center = Mock(return_value=center)

        viewport = Mock()
        camera = Mock()
        camera.direction = (0, 1, 0)
        viewport.camera = camera

        context = capture_edge_selection_context(edge, viewport=viewport)

        assert context is not None
        assert context.view_direction == (0, 1, 0)


class TestFilletFeatureV5Fields:
    """Test TNP v5.0 fields in FilletFeature."""

    def test_fillet_has_tnp_v5_fields(self):
        """Test that FilletFeature has v5.0 fields."""
        feature = FilletFeature()

        assert hasattr(feature, 'tnp_v5_input_edge_ids')
        assert hasattr(feature, 'tnp_v5_output_edge_ids')
        assert hasattr(feature, 'tnp_v5_output_face_ids')
        assert hasattr(feature, 'tnp_v5_selection_contexts')

    def test_fillet_default_values(self):
        """Test default values for v5.0 fields."""
        feature = FilletFeature()

        assert feature.tnp_v5_input_edge_ids == []
        assert feature.tnp_v5_output_edge_ids == []
        assert feature.tnp_v5_output_face_ids == []
        assert feature.tnp_v5_selection_contexts == []

    def test_chamfer_has_tnp_v5_fields(self):
        """Test that ChamferFeature has v5.0 fields."""
        feature = ChamferFeature()

        assert hasattr(feature, 'tnp_v5_input_edge_ids')
        assert hasattr(feature, 'tnp_v5_output_edge_ids')
        assert hasattr(feature, 'tnp_v5_output_face_ids')
        assert hasattr(feature, 'tnp_v5_selection_contexts')

    def test_chamfer_default_values(self):
        """Test default values for ChamferFeature."""
        feature = ChamferFeature()

        assert feature.tnp_v5_input_edge_ids == []
        assert feature.tnp_v5_output_edge_ids == []
        assert feature.tnp_v5_output_face_ids == []
        assert feature.tnp_v5_selection_contexts == []


class TestFilletIntegrationWorkflow:
    """Test complete fillet workflow with TNP v5.0."""

    def test_full_registration_workflow(self):
        """Test the full registration workflow."""
        service = TNPService(document_id="test_doc")

        # Mock edges
        edge1 = Mock()
        edge1.wrapped = Mock()
        edge2 = Mock()
        edge2.wrapped = Mock()

        # Register input edges
        input_ids = register_fillet_input_edges(service, [edge1, edge2], "fillet_1")

        assert len(input_ids) == 2

        # Store in feature
        feature = FilletFeature()
        store_fillet_data_in_feature(feature, input_ids)

        assert feature.tnp_v5_input_edge_ids == [input_ids[0].uuid, input_ids[1].uuid]

        # Retrieve
        retrieved = get_tnp_v5_input_edge_ids(feature)
        assert len(retrieved) == 2

    def test_resolution_workflow(self):
        """Test the resolution workflow."""
        service = TNPService(document_id="test_doc")

        # Create and register an edge
        edge = Mock()
        edge.wrapped = Mock()
        edge.center = Mock(return_value=Mock(X=0, Y=0, Z=0))

        # Capture context
        context = capture_edge_selection_context(edge)

        edge_ids = register_fillet_input_edges(service, [edge], "fillet_1", [context])

        # Store in feature
        feature = FilletFeature()
        store_fillet_data_in_feature(feature, edge_ids)

        # Mock exact match failure
        original_try_exact = service._try_exact_match
        service._try_exact_match = Mock(return_value=None)

        try:
            # Resolve (should use semantic)
            from modeling.tnp_v5.types import ResolutionOptions, ResolutionMethod
            result = service.resolve(edge_ids[0], None, ResolutionOptions(use_semantic_matching=True))

            # Should have attempted semantic match
            assert result.method in (ResolutionMethod.SEMANTIC, ResolutionMethod.FAILED)
        finally:
            service._try_exact_match = original_try_exact
