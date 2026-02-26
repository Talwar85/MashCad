"""
TNP v5.0 - ExtrudeFeature Integration Tests

Integration tests for TNP v5.0 with ExtrudeFeature.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from modeling.tnp_v5 import (
    TNPService,
    ShapeID,
    ShapeType,
    SelectionContext,
    get_tnp_v5_service,
    capture_sketch_selection_context,
    register_extrude_output_faces,
    register_extrude_output_edges,
    store_tnp_v5_data_in_feature,
    get_tnp_v5_face_ids_from_feature,
    resolve_extrude_face_after_boolean,
)

from modeling.features.extrude import ExtrudeFeature, PushPullFeature


class TestGetTNPV5Service:
    """Test getting TNP v5.0 service from document."""

    def test_get_service_none_document(self):
        """Test with None document."""
        service = get_tnp_v5_service(None)
        assert service is None

    def test_get_service_creates_new(self):
        """Test creating new service."""
        doc = Mock()
        doc.name = "test_doc"
        doc._tnp_v5_service = None

        # Mock feature flag
        with patch('config.feature_flags.is_enabled', return_value=True):
            service = get_tnp_v5_service(doc)

        assert service is not None
        assert doc._tnp_v5_service == service
        assert service.document_id == "test_doc"

    def test_get_service_returns_existing(self):
        """Test returning existing service."""
        doc = Mock()
        existing_service = Mock()
        doc._tnp_v5_service = existing_service

        service = get_tnp_v5_service(doc)

        assert service == existing_service

    def test_get_service_disabled(self):
        """Test when feature flag is disabled."""
        doc = Mock()
        doc._tnp_v5_service = None

        with patch('config.feature_flags.is_enabled', return_value=False):
            service = get_tnp_v5_service(doc)

        assert service is None


class TestCaptureSketchSelectionContext:
    """Test capturing selection context from sketch."""

    def test_capture_none_sketch(self):
        """Test with None sketch."""
        context = capture_sketch_selection_context(None, 0)
        assert context is None

    def test_capture_basic_context(self):
        """Test basic context capture."""
        sketch = Mock()
        profile = Mock()
        profile.centroid = Mock()
        profile.centroid.x = 5.0
        profile.centroid.y = 10.0

        sketch.closed_profiles = [profile]
        sketch.name = "test_sketch"
        # Mock plane to return actual values
        sketch.plane = Mock()
        sketch.plane.to_local_coords = Mock(return_value=(5.0, 10.0, 0.0))

        context = capture_sketch_selection_context(sketch, 0)

        assert context is not None
        # Check coordinates are numeric
        assert len(context.selection_point) == 3
        assert context.feature_context == "test_sketch"

    def test_capture_with_viewport(self):
        """Test with viewport for view direction."""
        sketch = Mock()
        profile = Mock()
        profile.centroid = Mock(x=0, y=0)

        sketch.closed_profiles = [profile]

        viewport = Mock()
        camera = Mock()
        camera.direction = (0, 1, 0)
        viewport.camera = camera

        context = capture_sketch_selection_context(sketch, 0, viewport)

        assert context is not None
        assert context.view_direction == (0, 1, 0)

    def test_capture_invalid_profile_index(self):
        """Test with invalid profile index."""
        sketch = Mock()
        sketch.closed_profiles = []

        context = capture_sketch_selection_context(sketch, 0)

        assert context is None


class TestRegisterExtrudeOutputFaces:
    """Test registering extrude output faces."""

    def test_register_none_solid(self):
        """Test with None solid."""
        service = Mock(spec=TNPService)
        service.register_shape = Mock(return_value=Mock(uuid="test"))

        ids = register_extrude_output_faces(service, None, "test_feature")

        assert ids == []

    def test_register_faces_success(self):
        """Test successful face registration."""
        service = Mock(spec=TNPService)
        service.register_shape = Mock(return_value=Mock(uuid="test_uuid"))

        # Mock solid with faces
        solid = Mock()
        face1 = Mock()
        face1.wrapped = Mock()
        face2 = Mock()
        face2.wrapped = Mock()
        solid.faces = Mock(return_value=[face1, face2])

        ids = register_extrude_output_faces(service, solid, "extrude_1")

        assert len(ids) == 2
        assert service.register_shape.call_count == 2

    def test_register_with_selection_contexts(self):
        """Test with selection contexts."""
        service = Mock(spec=TNPService)
        service.register_shape = Mock(return_value=Mock(uuid="test_uuid"))

        solid = Mock()
        face = Mock()
        face.wrapped = Mock()
        solid.faces = Mock(return_value=[face])

        context = SelectionContext(
            shape_id="",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context="sketch_1"
        )

        ids = register_extrude_output_faces(
            service, solid, "extrude_1", [context]
        )

        assert len(ids) == 1
        # Check context was passed
        call_kwargs = service.register_shape.call_args[1]
        assert call_kwargs['context'] == context


class TestRegisterExtrudeOutputEdges:
    """Test registering extrude output edges."""

    def test_register_none_solid(self):
        """Test with None solid."""
        service = Mock(spec=TNPService)

        ids = register_extrude_output_edges(service, None, "test_feature")

        assert ids == []

    def test_register_edges_success(self):
        """Test successful edge registration."""
        service = Mock(spec=TNPService)
        service.register_shape = Mock(return_value=Mock(uuid="test_uuid"))

        solid = Mock()
        edge = Mock()
        edge.wrapped = Mock()
        solid.edges = Mock(return_value=[edge, edge])

        ids = register_extrude_output_edges(service, solid, "extrude_1")

        assert len(ids) == 2
        assert service.register_shape.call_count == 2


class TestStoreTNPV5DataInFeature:
    """Test storing TNP v5.0 data in feature."""

    def test_store_face_ids(self):
        """Test storing face IDs."""
        feature = ExtrudeFeature()
        face_ids = [Mock(uuid="uuid1"), Mock(uuid="uuid2")]

        store_tnp_v5_data_in_feature(feature, face_ids)

        assert feature.tnp_v5_face_ids == ["uuid1", "uuid2"]

    def test_store_with_edge_ids(self):
        """Test storing with edge IDs."""
        feature = ExtrudeFeature()
        face_ids = [Mock(uuid="uuid1")]
        edge_ids = [Mock(uuid="edge1")]

        store_tnp_v5_data_in_feature(feature, face_ids, edge_ids)

        assert feature.tnp_v5_face_ids == ["uuid1"]
        assert feature.tnp_v5_edge_ids == ["edge1"]

    def test_store_replaces_existing(self):
        """Test that existing data is replaced."""
        feature = ExtrudeFeature()
        feature.tnp_v5_face_ids = ["old"]

        face_ids = [Mock(uuid="new")]
        store_tnp_v5_data_in_feature(feature, face_ids)

        assert feature.tnp_v5_face_ids == ["new"]


class TestGetTNPV5FaceIdsFromFeature:
    """Test getting stored face IDs."""

    def test_get_from_extrude_feature(self):
        """Test getting from ExtrudeFeature."""
        feature = ExtrudeFeature()
        feature.tnp_v5_face_ids = ["uuid1", "uuid2"]

        ids = get_tnp_v5_face_ids_from_feature(feature)

        assert ids == ["uuid1", "uuid2"]

    def test_get_from_pushpull_feature(self):
        """Test getting from PushPullFeature."""
        feature = PushPullFeature()
        feature.tnp_v5_face_ids = ["uuid3"]

        ids = get_tnp_v5_face_ids_from_feature(feature)

        assert ids == ["uuid3"]

    def test_get_empty_when_missing(self):
        """Test when feature has no stored IDs."""
        feature = ExtrudeFeature()
        # Don't set tnp_v5_face_ids

        ids = get_tnp_v5_face_ids_from_feature(feature)

        assert ids == []


class TestResolveExtrudeFaceAfterBoolean:
    """Test resolving extrude face after boolean operations."""

    def test_resolve_no_stored_ids(self):
        """Test with no stored face IDs."""
        service = Mock(spec=TNPService)
        feature = ExtrudeFeature()
        current_solid = Mock()

        result = resolve_extrude_face_after_boolean(service, feature, current_solid, 0)

        assert result is None

    def test_resolve_index_out_of_range(self):
        """Test with index out of range."""
        service = Mock(spec=TNPService)
        feature = ExtrudeFeature()
        feature.tnp_v5_face_ids = ["uuid1"]

        current_solid = Mock()

        result = resolve_extrude_face_after_boolean(service, feature, current_solid, 5)

        assert result is None

    def test_resolve_no_record_found(self):
        """Test when record is not found."""
        service = Mock(spec=TNPService)
        service.get_shape_record = Mock(return_value=None)

        feature = ExtrudeFeature()
        feature.tnp_v5_face_ids = ["uuid1"]

        current_solid = Mock()

        result = resolve_extrude_face_after_boolean(service, feature, current_solid, 0)

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

        feature = ExtrudeFeature()
        feature.tnp_v5_face_ids = ["uuid1"]

        current_solid = Mock()

        result = resolve_extrude_face_after_boolean(service, feature, current_solid, 0)

        assert result is not None
        assert result == resolution_result.resolved_shape

    def test_resolve_failure(self):
        """Test failed resolution."""
        service = Mock(spec=TNPService)

        # Mock record
        record = Mock()
        record.shape_id = Mock()
        service.get_shape_record = Mock(return_value=record)

        # Mock resolution result - failed
        resolution_result = Mock()
        resolution_result.success = False
        service.resolve = Mock(return_value=resolution_result)

        feature = ExtrudeFeature()
        feature.tnp_v5_face_ids = ["uuid1"]

        current_solid = Mock()

        result = resolve_extrude_face_after_boolean(service, feature, current_solid, 0)

        assert result is None


class TestExtrudeFeatureV5Fields:
    """Test TNP v5.0 fields in ExtrudeFeature."""

    def test_extrude_has_tnp_v5_fields(self):
        """Test that ExtrudeFeature has v5.0 fields."""
        feature = ExtrudeFeature()

        assert hasattr(feature, 'tnp_v5_face_ids')
        assert hasattr(feature, 'tnp_v5_edge_ids')
        assert hasattr(feature, 'tnp_v5_selection_contexts')

    def test_extrude_default_values(self):
        """Test default values for v5.0 fields."""
        feature = ExtrudeFeature()

        assert feature.tnp_v5_face_ids == []
        assert feature.tnp_v5_edge_ids == []
        assert feature.tnp_v5_selection_contexts == []

    def test_pushpull_has_tnp_v5_fields(self):
        """Test that PushPullFeature has v5.0 fields."""
        feature = PushPullFeature()

        assert hasattr(feature, 'tnp_v5_face_ids')
        assert hasattr(feature, 'tnp_v5_edge_ids')
        assert hasattr(feature, 'tnp_v5_selection_context')

    def test_pushpull_default_values(self):
        """Test default values for PushPullFeature."""
        feature = PushPullFeature()

        assert feature.tnp_v5_face_ids == []
        assert feature.tnp_v5_edge_ids == []
        assert feature.tnp_v5_selection_context is None


class TestExtrudeIntegrationWorkflow:
    """Test complete extrude workflow with TNP v5.0."""

    def test_full_registration_workflow(self):
        """Test the full registration workflow."""
        # Create service
        service = TNPService(document_id="test_doc")

        # Mock solid
        solid = Mock()
        face = Mock()
        face.wrapped = Mock()
        solid.faces = Mock(return_value=[face])

        # Register faces
        face_ids = register_extrude_output_faces(service, solid, "extrude_1")

        assert len(face_ids) == 1
        assert face_ids[0].uuid is not None

        # Store in feature
        feature = ExtrudeFeature()
        store_tnp_v5_data_in_feature(feature, face_ids)

        assert feature.tnp_v5_face_ids == [face_ids[0].uuid]

        # Retrieve
        retrieved = get_tnp_v5_face_ids_from_feature(feature)
        assert retrieved == [face_ids[0].uuid]

    def test_resolution_workflow(self):
        """Test the resolution workflow."""
        service = TNPService(document_id="test_doc")

        # Create and register a face
        solid = Mock()
        face = Mock()
        face.wrapped = Mock()
        solid.faces = Mock(return_value=[face])

        # Capture context
        context = SelectionContext(
            shape_id="",
            selection_point=(10, 10, 10),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context="sketch_1"
        )

        face_ids = register_extrude_output_faces(
            service, solid, "extrude_1", [context]
        )

        # Store in feature
        feature = ExtrudeFeature()
        store_tnp_v5_data_in_feature(feature, face_ids)

        # Mock exact match failure
        original_try_exact = service._try_exact_match
        service._try_exact_match = Mock(return_value=None)

        try:
            # Resolve (should use semantic)
            from modeling.tnp_v5.types import ResolutionOptions, ResolutionMethod
            result = service.resolve(face_ids[0], solid, ResolutionOptions(use_semantic_matching=True))

            # Should have attempted semantic match
            assert result.method in (ResolutionMethod.SEMANTIC, ResolutionMethod.FAILED)
        finally:
            service._try_exact_match = original_try_exact
