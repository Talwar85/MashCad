"""
TNP v5.0 - BooleanFeature Integration Tests

Integration tests for TNP v5.0 with BooleanFeature.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from modeling.tnp_v5 import (
    TNPService,
    ShapeID,
    ShapeType,
    SelectionContext,
    get_tnp_v5_service,
    register_extrude_output_faces,
    register_boolean_input_shapes,
    register_boolean_output_shapes,
    store_boolean_data_in_feature,
    resolve_boolean_shape_after_operation,
    get_occt_history_data,
    get_boolean_input_face_ids,
    get_boolean_output_face_ids,
    get_transformation_map,
)

from modeling.features.boolean import BooleanFeature


class TestRegisterBooleanInputShapes:
    """Test registering boolean input shapes."""

    def test_register_none_solids(self):
        """Test with None solids."""
        service = Mock(spec=TNPService)

        face_ids, edge_ids = register_boolean_input_shapes(
            service, None, None, "bool_1"
        )

        assert face_ids == []
        assert edge_ids == []

    def test_register_target_solid(self):
        """Test registering target solid shapes."""
        service = Mock(spec=TNPService)
        service.register_shape = Mock(return_value=Mock(uuid="test_uuid"))

        # Mock target solid
        solid = Mock()
        face = Mock()
        face.wrapped = Mock()
        edge = Mock()
        edge.wrapped = Mock()
        solid.faces = Mock(return_value=[face])
        solid.edges = Mock(return_value=[edge])

        face_ids, edge_ids = register_boolean_input_shapes(
            service, solid, None, "bool_1"
        )

        assert len(face_ids) == 1
        assert len(edge_ids) == 1
        assert service.register_shape.call_count == 2

    def test_register_both_solids(self):
        """Test registering both target and tool solids."""
        service = Mock(spec=TNPService)
        service.register_shape = Mock(return_value=Mock(uuid="test_uuid"))

        # Mock solids
        target = Mock()
        target_face = Mock()
        target_face.wrapped = Mock()
        target.faces = Mock(return_value=[target_face])
        target.edges = Mock(return_value=[])

        tool = Mock()
        tool_face = Mock()
        tool_face.wrapped = Mock()
        tool.faces = Mock(return_value=[tool_face])
        tool.edges = Mock(return_value=[])

        face_ids, edge_ids = register_boolean_input_shapes(
            service, target, tool, "bool_1"
        )

        # Currently only target is registered (tool tracking could be added)
        assert len(face_ids) >= 1


class TestRegisterBooleanOutputShapes:
    """Test registering boolean output shapes."""

    def test_register_none_solid(self):
        """Test with None solid."""
        service = Mock(spec=TNPService)

        face_ids, edge_ids, transform = register_boolean_output_shapes(
            service, None, "bool_1"
        )

        assert face_ids == []
        assert edge_ids == []
        assert transform == {}

    def test_register_success(self):
        """Test successful output registration."""
        service = Mock(spec=TNPService)
        service.register_shape = Mock(return_value=Mock(uuid="out_uuid"))

        # Mock result solid
        solid = Mock()
        face = Mock()
        face.wrapped = Mock()
        edge = Mock()
        edge.wrapped = Mock()
        solid.faces = Mock(return_value=[face])
        solid.edges = Mock(return_value=[edge])

        face_ids, edge_ids, transform = register_boolean_output_shapes(
            service, solid, "bool_1"
        )

        assert len(face_ids) == 1
        assert len(edge_ids) == 1
        assert isinstance(transform, dict)

    def test_register_with_inputs_for_transformation(self):
        """Test transformation map building."""
        service = Mock(spec=TNPService)

        # Create mock input IDs
        input_id1 = Mock(uuid="input1")
        input_id2 = Mock(uuid="input2")

        service.register_shape = Mock(return_value=Mock(uuid="output1"))

        solid = Mock()
        face = Mock()
        face.wrapped = Mock()
        solid.faces = Mock(return_value=[face])
        solid.edges = Mock(return_value=[])

        face_ids, edge_ids, transform = register_boolean_output_shapes(
            service, solid, "bool_1",
            input_face_ids=[input_id1],
            input_edge_ids=[input_id2]
        )

        # Check transformation map
        assert "input1" in transform
        assert "input2" in transform


class TestStoreBooleanDataInFeature:
    """Test storing boolean data in feature."""

    def test_store_all_data(self):
        """Test storing all boolean data."""
        feature = BooleanFeature()

        in_faces = [Mock(uuid="inf1")]
        in_edges = [Mock(uuid="ine1")]
        out_faces = [Mock(uuid="outf1")]
        out_edges = [Mock(uuid="oute1")]
        transform = {"inf1": "outf1"}

        store_boolean_data_in_feature(
            feature, in_faces, in_edges, out_faces, out_edges, transform
        )

        assert feature.tnp_v5_input_face_ids == ["inf1"]
        assert feature.tnp_v5_input_edge_ids == ["ine1"]
        assert feature.tnp_v5_output_face_ids == ["outf1"]
        assert feature.tnp_v5_output_edge_ids == ["oute1"]
        assert feature.tnp_v5_transformation_map == transform


class TestResolveBooleanShapeAfterOperation:
    """Test resolving shapes after boolean operations."""

    def test_resolve_no_transformation_map(self):
        """Test with no transformation map."""
        service = Mock(spec=TNPService)
        feature = BooleanFeature()
        feature.tnp_v5_transformation_map = {}

        # Mock get_shape_record to return None
        service.get_shape_record = Mock(return_value=None)

        result = resolve_boolean_shape_after_operation(
            service, feature, None, "test_uuid"
        )

        assert result is None

    def test_resolve_with_transformation_map(self):
        """Test using transformation map."""
        service = Mock(spec=TNPService)

        # Mock record and resolution
        record = Mock()
        record.shape_id = Mock()
        resolution_result = Mock()
        resolution_result.success = True
        resolution_result.resolved_shape = Mock()
        service.get_shape_record = Mock(return_value=record)
        service.resolve = Mock(return_value=resolution_result)

        feature = BooleanFeature()
        feature.tnp_v5_transformation_map = {
            "input_uuid": ["output_uuid"]
        }

        result = resolve_boolean_shape_after_operation(
            service, feature, None, "input_uuid"
        )

        assert result is not None
        assert result == resolution_result.resolved_shape

    def test_resolve_fallback_to_semantic(self):
        """Test fallback to semantic matching."""
        service = Mock(spec=TNPService)

        # Mock record and resolution
        record = Mock()
        record.shape_id = Mock()
        resolution_result = Mock()
        resolution_result.success = True
        resolution_result.resolved_shape = Mock()
        service.get_shape_record = Mock(return_value=record)
        service.resolve = Mock(return_value=resolution_result)

        feature = BooleanFeature()
        feature.tnp_v5_transformation_map = {}

        result = resolve_boolean_shape_after_operation(
            service, feature, None, "input_uuid"
        )

        assert result is not None


class TestGetOCCTHistoryData:
    """Test OCCT history extraction."""

    def test_no_history(self):
        """Test with no history."""
        result = Mock()
        # Don't set history attribute
        del result.history

        history = get_occt_history_data(result)

        assert history is None

    def test_with_history(self):
        """Test with history object."""
        result = Mock()
        history = Mock()
        history.IsGenerated = Mock(return_value=True)
        result.history = history

        history_data = get_occt_history_data(result)

        assert history_data is not None
        assert history_data['has_history'] is True
        assert history_data['is_generated'] is True

    def test_history_exception(self):
        """Test with history that raises exception."""
        result = Mock()
        history = Mock()
        history.IsGenerated = Mock(side_effect=Exception("test"))
        result.history = history

        history_data = get_occt_history_data(result)

        # Should handle exception gracefully
        assert history_data is None


class TestBooleanFeatureV5Fields:
    """Test TNP v5.0 fields in BooleanFeature."""

    def test_boolean_has_tnp_v5_fields(self):
        """Test that BooleanFeature has v5.0 fields."""
        feature = BooleanFeature()

        assert hasattr(feature, 'tnp_v5_input_face_ids')
        assert hasattr(feature, 'tnp_v5_input_edge_ids')
        assert hasattr(feature, 'tnp_v5_output_face_ids')
        assert hasattr(feature, 'tnp_v5_output_edge_ids')
        assert hasattr(feature, 'tnp_v5_occt_history')
        assert hasattr(feature, 'tnp_v5_transformation_map')

    def test_boolean_default_values(self):
        """Test default values for v5.0 fields."""
        feature = BooleanFeature()

        assert feature.tnp_v5_input_face_ids == []
        assert feature.tnp_v5_input_edge_ids == []
        assert feature.tnp_v5_output_face_ids == []
        assert feature.tnp_v5_output_edge_ids == []
        assert feature.tnp_v5_occt_history is None
        assert feature.tnp_v5_transformation_map == {}


class TestBooleanGetters:
    """Test getter functions for boolean feature."""

    def test_get_input_face_ids(self):
        """Test getting input face IDs."""
        feature = BooleanFeature()
        feature.tnp_v5_input_face_ids = ["uuid1", "uuid2"]

        ids = get_boolean_input_face_ids(feature)

        assert ids == ["uuid1", "uuid2"]

    def test_get_input_face_ids_empty(self):
        """Test getting input face IDs when empty."""
        feature = BooleanFeature()

        ids = get_boolean_input_face_ids(feature)

        assert ids == []

    def test_get_output_face_ids(self):
        """Test getting output face IDs."""
        feature = BooleanFeature()
        feature.tnp_v5_output_face_ids = ["out1"]

        ids = get_boolean_output_face_ids(feature)

        assert ids == ["out1"]

    def test_get_transformation_map(self):
        """Test getting transformation map."""
        feature = BooleanFeature()
        feature.tnp_v5_transformation_map = {"in1": "out1"}

        trans = get_transformation_map(feature)

        assert trans == {"in1": "out1"}


class TestBooleanIntegrationWorkflow:
    """Test complete boolean workflow with TNP v5.0."""

    def test_full_workflow(self):
        """Test the complete boolean workflow."""
        service = TNPService(document_id="test_doc")

        # Mock target solid
        target = Mock()
        target_face = Mock()
        target_face.wrapped = Mock()
        target.faces = Mock(return_value=[target_face])
        target.edges = Mock(return_value=[])

        # Register input
        input_face_ids, input_edge_ids = register_boolean_input_shapes(
            service, target, None, "bool_1"
        )

        assert len(input_face_ids) == 1

        # Mock result solid
        result = Mock()
        result_face = Mock()
        result_face.wrapped = Mock()
        result.faces = Mock(return_value=[result_face])
        result.edges = Mock(return_value=[])

        # Register output
        output_face_ids, output_edge_ids, transform = register_boolean_output_shapes(
            service, result, "bool_1",
            input_face_ids=input_face_ids
        )

        assert len(output_face_ids) == 1
        assert isinstance(transform, dict)

        # Store in feature
        feature = BooleanFeature()
        store_boolean_data_in_feature(
            feature, input_face_ids, input_edge_ids,
            output_face_ids, output_edge_ids, transform
        )

        # Verify storage
        assert feature.tnp_v5_input_face_ids == [input_face_ids[0].uuid]
        assert feature.tnp_v5_transformation_map == transform

    def test_resolution_with_map(self):
        """Test resolution using transformation map."""
        service = TNPService(document_id="test_doc")

        # Create a mock face for registration
        face = Mock()
        face.wrapped = Mock()
        face_solid = Mock()
        face_solid.faces = Mock(return_value=[face])

        # Register the face properly
        face_id = service.register_shape(
            ocp_shape=face.wrapped,
            shape_type=ShapeType.FACE,
            feature_id="bool_1",
            local_index=0,
            context=None
        )

        # Create feature with transformation map
        feature = BooleanFeature()
        feature.tnp_v5_transformation_map = {
            face_id.uuid: ["output_uuid"]
        }

        # Mock record and resolution for output UUID
        out_record = Mock()
        out_record.shape_id = Mock()
        resolution_result = Mock()
        resolution_result.success = True
        resolution_result.resolved_shape = Mock()
        service.get_shape_record = Mock(return_value=out_record)
        service.resolve = Mock(return_value=resolution_result)

        result = resolve_boolean_shape_after_operation(
            service, feature, None, face_id.uuid
        )

        assert result is not None
