"""
Unit tests for modeling/features/ module.

Tests cover:
- Feature base class (instantiation, serialization)
- ExtrudeFeature (creation, validation, sketch handling)
- FilletFeature/ChamferFeature (edge references, validation)
- BooleanFeature (operation types, validation)
- PushPullFeature (validation, push/pull detection)
"""
import pytest
from dataclasses import asdict, fields
from unittest.mock import MagicMock, patch

from modeling.features.base import Feature, FeatureType
from modeling.features.extrude import ExtrudeFeature, PushPullFeature
from modeling.features.fillet_chamfer import (
    FilletFeature,
    ChamferFeature,
    _canonicalize_indices,
)
from modeling.features.boolean import BooleanFeature


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def basic_feature():
    """Create a basic Feature instance for testing."""
    return Feature(
        type=FeatureType.SKETCH,
        name="TestFeature",
        visible=True,
        suppressed=False,
        status="OK",
        status_message="",
    )


@pytest.fixture
def extrude_feature():
    """Create a basic ExtrudeFeature instance for testing."""
    return ExtrudeFeature(
        distance=20.0,
        direction=1,
        operation="New Body",
    )


@pytest.fixture
def fillet_feature():
    """Create a basic FilletFeature instance for testing."""
    return FilletFeature(
        radius=5.0,
        edge_indices=[0, 1, 2],
    )


@pytest.fixture
def chamfer_feature():
    """Create a basic ChamferFeature instance for testing."""
    return ChamferFeature(
        distance=3.0,
        edge_indices=[0, 1],
    )


@pytest.fixture
def boolean_feature():
    """Create a basic BooleanFeature instance for testing."""
    return BooleanFeature(
        operation="Cut",
        tool_body_id="tool_123",
    )


# =============================================================================
# Test FeatureType Enum
# =============================================================================

class TestFeatureType:
    """Tests for the FeatureType enum."""

    def test_feature_type_values(self):
        """Test that all expected feature types exist."""
        expected_types = [
            "SKETCH", "EXTRUDE", "REVOLVE", "FILLET", "CHAMFER",
            "TRANSFORM", "BOOLEAN", "PUSHPULL", "PATTERN", "LOFT",
            "SWEEP", "SHELL", "SURFACE_TEXTURE", "HOLE", "DRAFT",
            "SPLIT", "THREAD", "HOLLOW", "LATTICE", "NSIDED_PATCH",
            "PRIMITIVE", "IMPORT",
        ]
        for type_name in expected_types:
            assert hasattr(FeatureType, type_name), f"Missing FeatureType.{type_name}"

    def test_feature_type_auto_values(self):
        """Test that FeatureType auto values are unique."""
        values = [ft.value for ft in FeatureType]
        assert len(values) == len(set(values)), "FeatureType values should be unique"


# =============================================================================
# Test Feature Base Class
# =============================================================================

class TestFeatureBase:
    """Tests for the Feature base class."""

    def test_feature_instantiation_default_values(self):
        """Test Feature instantiation with default values."""
        feature = Feature()
        
        assert feature.type is None
        assert feature.name == "Feature"
        assert feature.visible is True
        assert feature.suppressed is False
        assert feature.status == "OK"
        assert feature.status_message == ""
        assert feature.status_details == {}
        assert len(feature.id) == 8  # UUID truncated to 8 chars

    def test_feature_instantiation_custom_values(self):
        """Test Feature instantiation with custom values."""
        feature = Feature(
            type=FeatureType.EXTRUDE,
            name="CustomFeature",
            visible=False,
            suppressed=True,
            status="ERROR",
            status_message="Test error",
            status_details={"code": "E001"},
        )
        
        assert feature.type == FeatureType.EXTRUDE
        assert feature.name == "CustomFeature"
        assert feature.visible is False
        assert feature.suppressed is True
        assert feature.status == "ERROR"
        assert feature.status_message == "Test error"
        assert feature.status_details == {"code": "E001"}

    def test_feature_unique_ids(self):
        """Test that each Feature instance gets a unique ID."""
        feature1 = Feature()
        feature2 = Feature()
        
        assert feature1.id != feature2.id

    def test_feature_id_format(self):
        """Test that Feature ID is a valid hex string."""
        feature = Feature()
        
        # Should be 8 character hex string from UUID
        assert len(feature.id) == 8
        assert all(c in "0123456789abcdef" for c in feature.id)

    def test_feature_to_dict_via_dataclass(self):
        """Test Feature serialization via dataclasses.asdict()."""
        feature = Feature(
            type=FeatureType.EXTRUDE,
            name="TestFeature",
            visible=True,
        )
        
        data = asdict(feature)
        
        assert data["type"] == FeatureType.EXTRUDE
        assert data["name"] == "TestFeature"
        assert data["visible"] is True
        assert "id" in data

    def test_feature_from_dict_via_kwargs(self):
        """Test Feature deserialization from dict via **kwargs."""
        data = {
            "type": FeatureType.EXTRUDE,
            "name": "RestoredFeature",
            "visible": False,
            "suppressed": True,
            "status": "WARNING",
            "status_message": "Test warning",
            "status_details": {"hint": "check input"},
        }
        
        feature = Feature(**data)
        
        assert feature.type == FeatureType.EXTRUDE
        assert feature.name == "RestoredFeature"
        assert feature.visible is False
        assert feature.suppressed is True
        assert feature.status == "WARNING"
        assert feature.status_message == "Test warning"
        assert feature.status_details == {"hint": "check input"}

    def test_feature_field_count(self):
        """Test that Feature has expected number of fields."""
        field_names = [f.name for f in fields(Feature)]
        
        expected_fields = ["type", "name", "id", "visible", "suppressed", 
                          "status", "status_message", "status_details"]
        
        for expected in expected_fields:
            assert expected in field_names, f"Missing field: {expected}"


# =============================================================================
# Test ExtrudeFeature
# =============================================================================

class TestExtrudeFeature:
    """Tests for the ExtrudeFeature class."""

    def test_extrude_creation_default_values(self):
        """Test ExtrudeFeature creation with default values."""
        feature = ExtrudeFeature()
        
        assert feature.type == FeatureType.EXTRUDE
        assert feature.name == "Extrude"
        assert feature.distance == 10.0
        assert feature.direction == 1
        assert feature.operation == "New Body"
        assert feature.sketch is None
        assert feature.profile_selector == []
        assert feature.precalculated_polys == []

    def test_extrude_creation_custom_values(self):
        """Test ExtrudeFeature creation with custom values."""
        feature = ExtrudeFeature(
            distance=50.0,
            distance_formula="width * 2",
            direction=-1,
            operation="Join",
            profile_selector=[(10.0, 20.0), (30.0, 40.0)],
        )
        
        assert feature.distance == 50.0
        assert feature.distance_formula == "width * 2"
        assert feature.direction == -1
        assert feature.operation == "Join"
        assert feature.profile_selector == [(10.0, 20.0), (30.0, 40.0)]

    def test_extrude_post_init_sets_type(self):
        """Test that __post_init__ sets correct type."""
        feature = ExtrudeFeature()
        
        assert feature.type == FeatureType.EXTRUDE

    def test_extrude_post_init_sets_name(self):
        """Test that __post_init__ sets default name."""
        feature = ExtrudeFeature()
        
        assert feature.name == "Extrude"

    def test_extrude_custom_name_preserved(self):
        """Test that custom name is preserved."""
        feature = ExtrudeFeature(name="CustomExtrude")
        
        assert feature.name == "CustomExtrude"

    def test_extrude_face_index_conversion(self):
        """Test that face_index is converted to int."""
        feature = ExtrudeFeature(face_index="5")
        
        assert feature.face_index == 5
        assert isinstance(feature.face_index, int)

    def test_extrude_face_index_invalid_conversion(self):
        """Test that invalid face_index is set to None."""
        feature = ExtrudeFeature(face_index="invalid")
        
        assert feature.face_index is None

    def test_extrude_plane_defaults(self):
        """Test default plane values."""
        feature = ExtrudeFeature()
        
        assert feature.plane_origin == (0, 0, 0)
        assert feature.plane_normal == (0, 0, 1)

    def test_extrude_serialization(self):
        """Test ExtrudeFeature serialization via asdict()."""
        feature = ExtrudeFeature(
            distance=25.0,
            direction=1,
            profile_selector=[(5.0, 10.0)],
        )
        
        data = asdict(feature)
        
        assert data["distance"] == 25.0
        assert data["direction"] == 1
        assert data["profile_selector"] == [(5.0, 10.0)]
        assert data["type"] == FeatureType.EXTRUDE

    def test_extrude_with_sketch_reference(self):
        """Test ExtrudeFeature with sketch reference."""
        mock_sketch = MagicMock()
        mock_sketch.name = "Sketch1"
        
        feature = ExtrudeFeature(
            sketch=mock_sketch,
            distance=15.0,
        )
        
        assert feature.sketch is mock_sketch
        assert feature.distance == 15.0


# =============================================================================
# Test PushPullFeature
# =============================================================================

class TestPushPullFeature:
    """Tests for the PushPullFeature class."""

    def test_pushpull_creation_default_values(self):
        """Test PushPullFeature creation with default values."""
        feature = PushPullFeature()
        
        assert feature.type == FeatureType.PUSHPULL
        assert feature.distance == 10.0
        assert feature.direction == 1
        assert feature.operation == "Join"

    def test_pushpull_is_pull_detection(self):
        """Test is_pull() method for pull operations."""
        feature = PushPullFeature(distance=10.0, direction=1)
        
        assert feature.is_pull() is True
        assert feature.is_push() is False

    def test_pushpull_is_push_detection(self):
        """Test is_push() method for push operations."""
        feature = PushPullFeature(distance=10.0, direction=-1)
        
        assert feature.is_push() is True
        assert feature.is_pull() is False

    def test_pushpull_get_effective_distance(self):
        """Test get_effective_distance() calculation."""
        feature = PushPullFeature(distance=10.0, direction=1)
        assert feature.get_effective_distance() == 10.0
        
        feature = PushPullFeature(distance=10.0, direction=-1)
        assert feature.get_effective_distance() == -10.0

    def test_pushpull_validate_success(self):
        """Test validate() with valid parameters."""
        feature = PushPullFeature(face_index=0, distance=10.0)
        
        is_valid, error = feature.validate()
        
        assert is_valid is True
        assert error == ""

    def test_pushpull_validate_no_face_reference(self):
        """Test validate() without face reference."""
        feature = PushPullFeature(distance=10.0)
        
        is_valid, error = feature.validate()
        
        assert is_valid is False
        assert "face_shape_id" in error or "face_index" in error or "face_selector" in error

    def test_pushpull_validate_zero_distance(self):
        """Test validate() with zero distance."""
        feature = PushPullFeature(face_index=0, distance=0)
        
        is_valid, error = feature.validate()
        
        assert is_valid is False
        assert "zero" in error.lower()

    def test_pushpull_name_based_on_direction(self):
        """Test that name is set based on direction."""
        feature_pull = PushPullFeature(distance=10.0)
        assert "Pull" in feature_pull.name
        
        feature_push = PushPullFeature(distance=-10.0)
        assert "Push" in feature_push.name


# =============================================================================
# Test FilletFeature
# =============================================================================

class TestFilletFeature:
    """Tests for the FilletFeature class."""

    def test_fillet_creation_default_values(self):
        """Test FilletFeature creation with default values."""
        feature = FilletFeature()
        
        assert feature.type == FeatureType.FILLET
        assert feature.name == "Fillet"
        assert feature.radius == 2.0
        assert feature.edge_shape_ids == []
        assert feature.edge_indices == []
        assert feature.geometric_selectors == []

    def test_fillet_creation_custom_values(self):
        """Test FilletFeature creation with custom values."""
        feature = FilletFeature(
            radius=5.0,
            radius_formula="thickness / 4",
            edge_indices=[0, 2, 4],
            edge_shape_ids=["shape_1", "shape_2"],
        )
        
        assert feature.radius == 5.0
        assert feature.radius_formula == "thickness / 4"
        assert feature.edge_indices == [0, 2, 4]
        assert feature.edge_shape_ids == ["shape_1", "shape_2"]

    def test_fillet_post_init_sets_type(self):
        """Test that __post_init__ sets correct type."""
        feature = FilletFeature()
        
        assert feature.type == FeatureType.FILLET

    def test_fillet_custom_name_preserved(self):
        """Test that custom name is preserved."""
        feature = FilletFeature(name="EdgeFillet")
        
        assert feature.name == "EdgeFillet"

    def test_fillet_edge_indices_canonicalized(self):
        """Test that edge_indices are canonicalized (sorted, unique)."""
        feature = FilletFeature(edge_indices=[5, 2, 3, 2, 1])
        
        assert feature.edge_indices == [1, 2, 3, 5]

    def test_fillet_negative_indices_filtered(self):
        """Test that negative indices are filtered out."""
        feature = FilletFeature(edge_indices=[1, -1, 2, -5, 3])
        
        assert feature.edge_indices == [1, 2, 3]

    def test_fillet_depends_on_feature_id(self):
        """Test depends_on_feature_id field."""
        feature = FilletFeature(
            radius=3.0,
            depends_on_feature_id="extrude_123",
        )
        
        assert feature.depends_on_feature_id == "extrude_123"

    def test_fillet_serialization(self):
        """Test FilletFeature serialization via asdict()."""
        feature = FilletFeature(
            radius=4.0,
            edge_indices=[1, 2, 3],
        )
        
        data = asdict(feature)
        
        assert data["radius"] == 4.0
        assert data["edge_indices"] == [1, 2, 3]
        assert data["type"] == FeatureType.FILLET


# =============================================================================
# Test ChamferFeature
# =============================================================================

class TestChamferFeature:
    """Tests for the ChamferFeature class."""

    def test_chamfer_creation_default_values(self):
        """Test ChamferFeature creation with default values."""
        feature = ChamferFeature()
        
        assert feature.type == FeatureType.CHAMFER
        assert feature.name == "Chamfer"
        assert feature.distance == 2.0
        assert feature.edge_shape_ids == []
        assert feature.edge_indices == []
        assert feature.geometric_selectors == []

    def test_chamfer_creation_custom_values(self):
        """Test ChamferFeature creation with custom values."""
        feature = ChamferFeature(
            distance=4.0,
            distance_formula="width / 2",
            edge_indices=[1, 3, 5],
            edge_shape_ids=["shape_a", "shape_b"],
        )
        
        assert feature.distance == 4.0
        assert feature.distance_formula == "width / 2"
        assert feature.edge_indices == [1, 3, 5]
        assert feature.edge_shape_ids == ["shape_a", "shape_b"]

    def test_chamfer_post_init_sets_type(self):
        """Test that __post_init__ sets correct type."""
        feature = ChamferFeature()
        
        assert feature.type == FeatureType.CHAMFER

    def test_chamfer_custom_name_preserved(self):
        """Test that custom name is preserved."""
        feature = ChamferFeature(name="EdgeChamfer")
        
        assert feature.name == "EdgeChamfer"

    def test_chamfer_edge_indices_canonicalized(self):
        """Test that edge_indices are canonicalized (sorted, unique)."""
        feature = ChamferFeature(edge_indices=[4, 1, 2, 1, 0])
        
        assert feature.edge_indices == [0, 1, 2, 4]

    def test_chamfer_depends_on_feature_id(self):
        """Test depends_on_feature_id field."""
        feature = ChamferFeature(
            distance=2.5,
            depends_on_feature_id="extrude_456",
        )
        
        assert feature.depends_on_feature_id == "extrude_456"

    def test_chamfer_serialization(self):
        """Test ChamferFeature serialization via asdict()."""
        feature = ChamferFeature(
            distance=3.5,
            edge_indices=[0, 1],
        )
        
        data = asdict(feature)
        
        assert data["distance"] == 3.5
        assert data["edge_indices"] == [0, 1]
        assert data["type"] == FeatureType.CHAMFER


# =============================================================================
# Test _canonicalize_indices Helper
# =============================================================================

class TestCanonicalizeIndices:
    """Tests for the _canonicalize_indices helper function."""

    def test_empty_list(self):
        """Test with empty list."""
        result = _canonicalize_indices([])
        assert result == []

    def test_none_input(self):
        """Test with None input."""
        result = _canonicalize_indices(None)
        assert result == []

    def test_sorts_indices(self):
        """Test that indices are sorted."""
        result = _canonicalize_indices([3, 1, 2])
        assert result == [1, 2, 3]

    def test_removes_duplicates(self):
        """Test that duplicates are removed."""
        result = _canonicalize_indices([1, 2, 2, 3, 3, 3])
        assert result == [1, 2, 3]

    def test_filters_negative(self):
        """Test that negative indices are filtered."""
        result = _canonicalize_indices([1, -1, 2, -5])
        assert result == [1, 2]

    def test_converts_floats(self):
        """Test that floats are converted to ints."""
        result = _canonicalize_indices([1.0, 2.5, 3.9])
        assert result == [1, 2, 3]

    def test_handles_strings(self):
        """Test that numeric strings are converted."""
        result = _canonicalize_indices(["1", "2", "3"])
        assert result == [1, 2, 3]

    def test_ignores_invalid_strings(self):
        """Test that invalid strings are ignored."""
        result = _canonicalize_indices([1, "invalid", 2, None, 3])
        assert result == [1, 2, 3]


# =============================================================================
# Test BooleanFeature
# =============================================================================

class TestBooleanFeature:
    """Tests for the BooleanFeature class."""

    def test_boolean_creation_default_values(self):
        """Test BooleanFeature creation with default values."""
        feature = BooleanFeature()
        
        assert feature.type == FeatureType.BOOLEAN
        assert feature.operation == "Cut"
        assert feature.tool_body_id is None
        assert feature.tool_solid_data is None
        assert feature.modified_shape_ids == []

    def test_boolean_creation_custom_values(self):
        """Test BooleanFeature creation with custom values."""
        feature = BooleanFeature(
            operation="Join",
            tool_body_id="body_abc123",
            fuzzy_tolerance=0.001,
        )
        
        assert feature.operation == "Join"
        assert feature.tool_body_id == "body_abc123"
        assert feature.fuzzy_tolerance == 0.001

    def test_boolean_post_init_sets_type(self):
        """Test that __post_init__ sets correct type."""
        feature = BooleanFeature()
        
        assert feature.type == FeatureType.BOOLEAN

    def test_boolean_name_includes_operation(self):
        """Test that name includes operation type."""
        feature = BooleanFeature(operation="Cut")
        assert "Cut" in feature.name
        
        feature = BooleanFeature(operation="Join")
        assert "Join" in feature.name

    def test_boolean_custom_name_preserved(self):
        """Test that custom name is preserved."""
        feature = BooleanFeature(name="CustomBoolean", operation="Cut")
        
        assert feature.name == "CustomBoolean"

    def test_get_operation_type_join_aliases(self):
        """Test get_operation_type() for Join aliases."""
        for alias in ["Union", "Fuse", "Add", "Join"]:
            feature = BooleanFeature(operation=alias)
            assert feature.get_operation_type() == "Join"

    def test_get_operation_type_cut_aliases(self):
        """Test get_operation_type() for Cut aliases."""
        for alias in ["Subtract", "Difference", "Cut"]:
            feature = BooleanFeature(operation=alias)
            assert feature.get_operation_type() == "Cut"

    def test_get_operation_type_common_aliases(self):
        """Test get_operation_type() for Common aliases."""
        for alias in ["Intersect", "Intersection", "Common"]:
            feature = BooleanFeature(operation=alias)
            assert feature.get_operation_type() == "Common"

    def test_get_operation_type_unknown_returns_original(self):
        """Test get_operation_type() returns original for unknown."""
        feature = BooleanFeature(operation="UnknownOp")
        assert feature.get_operation_type() == "UnknownOp"

    def test_validate_success_with_tool_body_id(self):
        """Test validate() with tool_body_id."""
        feature = BooleanFeature(
            operation="Cut",
            tool_body_id="tool_123",
        )
        
        is_valid, error = feature.validate()
        
        assert is_valid is True
        assert error == ""

    def test_validate_success_with_tool_solid_data(self):
        """Test validate() with tool_solid_data."""
        feature = BooleanFeature(
            operation="Join",
            tool_solid_data="BREP_DATA_HERE",
        )
        
        is_valid, error = feature.validate()
        
        assert is_valid is True
        assert error == ""

    def test_validate_invalid_operation(self):
        """Test validate() with invalid operation."""
        feature = BooleanFeature(
            operation="InvalidOp",
            tool_body_id="tool_123",
        )
        
        is_valid, error = feature.validate()
        
        assert is_valid is False
        assert "Unknown operation" in error

    def test_validate_no_tool_reference(self):
        """Test validate() without tool reference."""
        feature = BooleanFeature(operation="Cut")
        
        is_valid, error = feature.validate()
        
        assert is_valid is False
        assert "tool_body_id" in error or "tool_solid_data" in error

    def test_boolean_serialization(self):
        """Test BooleanFeature serialization via asdict()."""
        feature = BooleanFeature(
            operation="Cut",
            tool_body_id="body_xyz",
            fuzzy_tolerance=0.0005,
        )
        
        data = asdict(feature)
        
        assert data["operation"] == "Cut"
        assert data["tool_body_id"] == "body_xyz"
        assert data["fuzzy_tolerance"] == 0.0005
        assert data["type"] == FeatureType.BOOLEAN


# =============================================================================
# Test Feature Type Consistency
# =============================================================================

class TestFeatureTypeConsistency:
    """Tests for feature type consistency across classes."""

    def test_all_features_have_unique_types(self):
        """Test that different feature classes have different types."""
        features = [
            ExtrudeFeature(),
            FilletFeature(),
            ChamferFeature(),
            BooleanFeature(),
            PushPullFeature(),
        ]
        
        types = [f.type for f in features]
        
        # All should be different
        assert len(types) == len(set(types))

    def test_all_features_inherit_from_base(self):
        """Test that all feature classes inherit from Feature."""
        feature_classes = [
            ExtrudeFeature,
            FilletFeature,
            ChamferFeature,
            BooleanFeature,
            PushPullFeature,
        ]
        
        for cls in feature_classes:
            assert issubclass(cls, Feature), f"{cls.__name__} should inherit from Feature"

    def test_all_features_have_id_field(self):
        """Test that all feature instances have an id field."""
        features = [
            Feature(),
            ExtrudeFeature(),
            FilletFeature(),
            ChamferFeature(),
            BooleanFeature(),
            PushPullFeature(),
        ]
        
        for feature in features:
            assert hasattr(feature, "id")
            assert feature.id is not None
            assert len(feature.id) == 8


# =============================================================================
# Test Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_extrude_zero_distance(self):
        """Test ExtrudeFeature with zero distance (valid for dataclass)."""
        feature = ExtrudeFeature(distance=0.0)
        assert feature.distance == 0.0

    def test_extrude_negative_distance(self):
        """Test ExtrudeFeature with negative distance."""
        feature = ExtrudeFeature(distance=-10.0)
        assert feature.distance == -10.0

    def test_fillet_zero_radius(self):
        """Test FilletFeature with zero radius (valid for dataclass)."""
        feature = FilletFeature(radius=0.0)
        assert feature.radius == 0.0

    def test_fillet_negative_radius(self):
        """Test FilletFeature with negative radius."""
        feature = FilletFeature(radius=-5.0)
        assert feature.radius == -5.0

    def test_chamfer_zero_distance(self):
        """Test ChamferFeature with zero distance."""
        feature = ChamferFeature(distance=0.0)
        assert feature.distance == 0.0

    def test_boolean_expected_volume_change(self):
        """Test BooleanFeature with expected volume change."""
        feature = BooleanFeature(
            operation="Cut",
            tool_body_id="tool_123",
            expected_volume_change=-500.0,
        )
        assert feature.expected_volume_change == -500.0

    def test_feature_status_variations(self):
        """Test Feature with different status values."""
        for status in ["OK", "WARNING", "ERROR", "PENDING"]:
            feature = Feature(status=status)
            assert feature.status == status

    def test_extrude_with_face_brep(self):
        """Test ExtrudeFeature with face_brep for non-planar faces."""
        feature = ExtrudeFeature(
            distance=10.0,
            face_brep="SERIALIZED_BREP_DATA",
            face_type="cylinder",
        )
        
        assert feature.face_brep == "SERIALIZED_BREP_DATA"
        assert feature.face_type == "cylinder"

    def test_fillet_with_ocp_edge_shapes(self):
        """Test FilletFeature with OCP edge shapes."""
        mock_shape = MagicMock()
        feature = FilletFeature(
            radius=3.0,
            ocp_edge_shapes=[mock_shape],
        )
        
        assert feature.ocp_edge_shapes == [mock_shape]

    def test_boolean_with_modified_shape_ids(self):
        """Test BooleanFeature with modified shape IDs."""
        feature = BooleanFeature(
            operation="Join",
            tool_body_id="tool_123",
            modified_shape_ids=["shape_1", "shape_2", "shape_3"],
        )
        
        assert len(feature.modified_shape_ids) == 3


# =============================================================================
# Test Feature Status Details
# =============================================================================

class TestFeatureStatusDetails:
    """Tests for feature status_details field."""

    def test_status_details_default_empty(self):
        """Test that status_details defaults to empty dict."""
        feature = Feature()
        assert feature.status_details == {}

    def test_status_details_with_content(self):
        """Test status_details with content."""
        details = {
            "code": "E001",
            "refs": ["edge_1", "edge_2"],
            "hints": ["Check edge selection"],
        }
        feature = Feature(status_details=details)
        
        assert feature.status_details == details

    def test_status_details_serialization(self):
        """Test that status_details is included in serialization."""
        feature = Feature(
            status="ERROR",
            status_message="Validation failed",
            status_details={"code": "E001"},
        )
        
        data = asdict(feature)
        
        assert data["status_details"] == {"code": "E001"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
