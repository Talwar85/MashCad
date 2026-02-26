"""
TNP v5.0 - Core Type Tests

Unit tests for TNP v5.0 data structures.
"""

import pytest
import math
from dataclasses import FrozenInstanceError

# Mock OCP imports for testing (we'll test without actual OCP when possible)
try:
    from OCP.TopoDS import TopoDS_Shape
    HAS_OCP = True
except ImportError:
    HAS_OCP = False

from modeling.tnp_v5 import (
    ShapeID,
    ShapeType,
    SelectionContext,
    ResolutionResult,
    ResolutionMethod,
    ResolutionOptions
)


class TestShapeType:
    """Test ShapeType enum."""

    def test_shape_type_values(self):
        """ShapeType has correct values."""
        assert ShapeType.EDGE.name == "EDGE"
        assert ShapeType.FACE.name == "FACE"
        assert ShapeType.VERTEX.name == "VERTEX"
        assert ShapeType.SOLID.name == "SOLID"

    def test_shape_type_from_ocp_skipped_without_ocp(self):
        """from_ocp() returns None when OCP not available."""
        # This test passes regardless of OCP availability
        result = ShapeType.from_ocp(None)
        assert result is None


class TestShapeID:
    """Test ShapeID creation and operations."""

    def test_create_generates_unique_uuids(self):
        """Creating ShapeIDs generates unique UUIDs."""
        id1 = ShapeID.create(ShapeType.EDGE, "feature_1", 0, ())
        id2 = ShapeID.create(ShapeType.EDGE, "feature_1", 0, ())

        assert id1.uuid != id2.uuid
        assert id1.feature_id == id2.feature_id
        assert id1.local_index == id2.local_index
        assert id1.geometry_hash == id2.geometry_hash

    def test_create_different_features(self):
        """ShapeIDs from different features are distinct."""
        id1 = ShapeID.create(ShapeType.EDGE, "feature_1", 0, ())
        id2 = ShapeID.create(ShapeType.EDGE, "feature_2", 0, ())

        assert id1.uuid != id2.uuid
        assert id1.feature_id != id2.feature_id

    def test_create_different_types(self):
        """ShapeIDs of different types are distinct."""
        id1 = ShapeID.create(ShapeType.EDGE, "feature_1", 0, ())
        id2 = ShapeID.create(ShapeType.FACE, "feature_1", 0, ())

        assert id1.uuid != id2.uuid
        assert id1.shape_type == ShapeType.EDGE
        assert id2.shape_type == ShapeType.FACE

    def test_with_context_adds_semantic_hash(self):
        """with_context() adds semantic hash."""
        id1 = ShapeID.create(ShapeType.EDGE, "f1", 0, ())

        context = SelectionContext(
            shape_id=id1.uuid,
            selection_point=(1.0, 2.0, 3.0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context="f1"
        )

        id2 = id1.with_context(context)

        assert id2.semantic_hash != ""
        assert id2.uuid == id1.uuid  # Immutable except specified fields
        assert id2.feature_id == id1.feature_id
        assert id2.local_index == id1.local_index

    def test_with_context_none_returns_same(self):
        """with_context(None) returns unchanged ShapeID."""
        id1 = ShapeID.create(ShapeType.EDGE, "f1", 0, ())
        id2 = id1.with_context(None)

        assert id2 == id1

    def test_with_parent_adds_parent(self):
        """with_parent() adds parent reference."""
        id1 = ShapeID.create(ShapeType.EDGE, "f1", 0, ())
        parent_uuid = "parent-123"

        id2 = id1.with_parent(parent_uuid)

        assert id2.parent_uuid == parent_uuid
        assert id2.uuid == id1.uuid

    def test_with_tag_adds_tag(self):
        """with_tag() adds a tag."""
        id1 = ShapeID.create(ShapeType.EDGE, "f1", 0, ())
        id2 = id1.with_tag("important")

        assert "important" in id2.tags
        assert id2.uuid == id1.uuid

    def test_with_tag_multiple(self):
        """Multiple tags can be added."""
        id1 = ShapeID.create(ShapeType.EDGE, "f1", 0, ())
        id2 = id1.with_tag("tag1")
        id3 = id2.with_tag("tag2")

        assert "tag1" in id3.tags
        assert "tag2" in id3.tags

    def test_frozen_immutable(self):
        """ShapeID is frozen - fields cannot be modified."""
        id1 = ShapeID.create(ShapeType.EDGE, "f1", 0, ())

        with pytest.raises(FrozenInstanceError):
            id1.feature_id = "other"  # Should raise

    def test_to_v4_format(self):
        """to_v4_format() produces correct dictionary."""
        id1 = ShapeID.create(ShapeType.EDGE, "f1", 0, ())

        v4_dict = id1.to_v4_format()

        assert 'uuid' in v4_dict
        assert 'shape_type' in v4_dict
        assert 'feature_id' in v4_dict
        assert 'local_index' in v4_dict
        assert 'geometry_hash' in v4_dict
        assert v4_dict['shape_type'] == ShapeType.EDGE
        assert v4_dict['feature_id'] == "f1"
        assert v4_dict['local_index'] == 0

    def test_from_v4_format_roundtrip(self):
        """from_v4_format() and to_v4_format() are inverses."""
        id1 = ShapeID.create(ShapeType.FACE, "f1", 5, ())

        v4_dict = id1.to_v4_format()
        id2 = ShapeID.from_v4_format(v4_dict)

        assert id2.uuid == id1.uuid
        assert id2.shape_type == id1.shape_type
        assert id2.feature_id == id1.feature_id
        assert id2.local_index == id1.local_index
        assert id2.geometry_hash == id1.geometry_hash


class TestSelectionContext:
    """Test SelectionContext operations."""

    def test_creation(self):
        """SelectionContext can be created with all fields."""
        ctx = SelectionContext(
            shape_id="test-id",
            selection_point=(1.0, 2.0, 3.0),
            view_direction=(0, 0, 1),
            adjacent_shapes=["a", "b", "c"],
            feature_context="test_feature",
            semantic_tags={"tag1", "tag2"},
            screen_position=(100, 200),
            zoom_level=1.5,
            viewport_id="viewport_1"
        )

        assert ctx.shape_id == "test-id"
        assert ctx.selection_point == (1.0, 2.0, 3.0)
        assert ctx.view_direction == (0, 0, 1)
        assert ctx.adjacent_shapes == ["a", "b", "c"]
        assert ctx.feature_context == "test_feature"
        assert "tag1" in ctx.semantic_tags
        assert "tag2" in ctx.semantic_tags
        assert ctx.screen_position == (100, 200)
        assert ctx.zoom_level == 1.5
        assert ctx.viewport_id == "viewport_1"

    def test_default_values(self):
        """SelectionContext has sensible defaults."""
        ctx = SelectionContext(
            shape_id="test-id",
            selection_point=(0, 0, 0),
            view_direction=(0, 0, 1),
            adjacent_shapes=[],
            feature_context=""
        )

        assert ctx.semantic_tags == set()
        assert ctx.screen_position is None
        assert ctx.zoom_level is None
        assert ctx.viewport_id is None

    def test_serialization_roundtrip(self):
        """SelectionContext serializes and deserializes correctly."""
        ctx1 = SelectionContext(
            shape_id="test-id",
            selection_point=(1.5, 2.5, 3.5),
            view_direction=(0.1, 0.2, 0.3),
            adjacent_shapes=["adj1", "adj2"],
            feature_context="my_feature",
            semantic_tags={"important"}
        )

        # Serialize
        data = ctx1.to_dict()

        # Deserialize
        ctx2 = SelectionContext.from_dict(data)

        assert ctx2.shape_id == ctx1.shape_id
        assert ctx2.selection_point == ctx1.selection_point
        assert ctx2.view_direction == ctx1.view_direction
        assert ctx2.adjacent_shapes == ctx1.adjacent_shapes
        assert ctx2.feature_context == ctx1.feature_context
        assert ctx2.semantic_tags == ctx1.semantic_tags


class TestResolutionResult:
    """Test ResolutionResult dataclass."""

    def test_creation_success(self):
        """ResolutionResult can be created for successful resolution."""
        result = ResolutionResult(
            shape_id="test-uuid",
            resolved_shape="mock_shape",
            method=ResolutionMethod.EXACT,
            confidence=1.0,
            duration_ms=5.0
        )

        assert result.success is True
        assert result.method == ResolutionMethod.EXACT
        assert result.confidence == 1.0
        assert result.duration_ms == 5.0
        assert not result.is_ambiguous

    def test_creation_failure(self):
        """ResolutionResult can be created for failed resolution."""
        result = ResolutionResult(
            shape_id="test-uuid",
            resolved_shape=None,
            method=ResolutionMethod.FAILED,
            confidence=0.0,
            duration_ms=10.0
        )

        assert result.success is False
        assert result.method == ResolutionMethod.FAILED
        assert result.confidence == 0.0
        assert not result.is_ambiguous

    def test_ambiguous_with_candidates(self):
        """ResolutionResult can indicate ambiguity with alternatives."""
        result = ResolutionResult(
            shape_id="test-uuid",
            resolved_shape="candidate1",
            method=ResolutionMethod.SEMANTIC,
            confidence=0.6,
            duration_ms=8.0,
            alternative_candidates=["candidate2", "candidate3"]
        )

        assert result.success is True
        assert result.is_ambiguous is True
        assert len(result.alternative_candidates) == 2


class TestResolutionOptions:
    """Test ResolutionOptions dataclass."""

    def test_default_values(self):
        """ResolutionOptions has sensible defaults."""
        options = ResolutionOptions()

        assert options.use_semantic_matching is True
        assert options.use_history_tracing is True
        assert options.require_user_confirmation is False
        assert options.position_tolerance == 0.01
        assert options.angle_tolerance == 0.1
        assert options.enable_spatial_index is True
        assert options.max_candidates == 10
        assert options.on_failure == "prompt"

    def test_custom_values(self):
        """ResolutionOptions accepts custom values."""
        options = ResolutionOptions(
            use_semantic_matching=False,
            require_user_confirmation=True,
            max_candidates=20
        )

        assert options.use_semantic_matching is False
        assert options.require_user_confirmation is True
        assert options.max_candidates == 20


class TestResolutionMethod:
    """Test ResolutionMethod enum."""

    def test_values(self):
        """ResolutionMethod has correct values."""
        assert ResolutionMethod.EXACT.value == "exact"
        assert ResolutionMethod.SEMANTIC.value == "semantic"
        assert ResolutionMethod.HISTORY.value == "history"
        assert ResolutionMethod.USER_GUIDED.value == "user"
        assert ResolutionMethod.FAILED.value == "failed"
