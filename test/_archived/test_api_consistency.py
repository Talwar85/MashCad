"""
API Consistency Test Suite
==========================

Tests für API-Konsistenz zwischen Loft, Sweep, Revolve und Extrude Features.
Stellt sicher dass alle Features das gleiche Pattern für Parameter-Namen und
TNP v4.0 ShapeID-Tracking verwenden.

Author: Claude (CAD System Improvement)
Date: 2026-02-10
"""
import pytest
import build123d as bd
from build123d import Solid, Location, Vector

from modeling import (
    Body, Document, ExtrudeFeature, LoftFeature,
    SweepFeature, RevolveFeature, FeatureType
)
from modeling.tnp_system import ShapeID, ShapeType


# ============================================================================
# API Parameter Naming Consistency Tests
# ============================================================================

class TestAPIParameterConsistency:
    """Tests für konsistente Parameter-Namen über alle Features."""

    def test_operation_values_consistent(self):
        """Operation-Values sind konsistent über alle Features."""
        # Alle Features sollten die gleichen Operations-Values verwenden
        expected_ops = ["New Body", "Join", "Cut", "Intersect"]

        # ExtrudeFeature
        feat_extrude = ExtrudeFeature(operation="New Body")
        assert feat_extrude.operation in expected_ops

        # RevolveFeature
        feat_revolve = RevolveFeature(operation="New Body")
        assert feat_revolve.operation in expected_ops

        # LoftFeature
        feat_loft = LoftFeature(operation="Join")
        assert feat_loft.operation in expected_ops

        # SweepFeature
        feat_sweep = SweepFeature(operation="Cut")
        assert feat_sweep.operation in expected_ops

    def test_distance_angle_units_consistent(self):
        """Distance/Angle sind immer float in mm/Grad."""
        # Extrude: Distance in mm
        feat_extrude = ExtrudeFeature(distance=10.5)
        assert isinstance(feat_extrude.distance, float)
        assert feat_extrude.distance == 10.5

        # Revolve: Angle in Grad
        feat_revolve = RevolveFeature(angle=180.0)
        assert isinstance(feat_revolve.angle, float)
        assert feat_revolve.angle == 180.0

        # Pattern: Spacing in mm
        from modeling import PatternFeature
        feat_pattern = PatternFeature(spacing=15.5)
        assert isinstance(feat_pattern.spacing, float)

    def test_axis_direction_consistent(self):
        """Axis/Direction ist immer tuple(x, y, z)."""
        # Revolve: Axis
        feat_revolve = RevolveFeature(axis=(0, 1, 0))
        assert isinstance(feat_revolve.axis, tuple)
        assert len(feat_revolve.axis) == 3

        # Pattern: direction_1, direction_2
        from modeling import PatternFeature
        feat_pattern = PatternFeature(direction_1=(1, 0, 0))
        assert isinstance(feat_pattern.direction_1, tuple)
        assert len(feat_pattern.direction_1) == 3

    def test_plane_parameters_consistent(self):
        """Plane-Parameter sind konsistent (origin, normal, x_dir, y_dir)."""
        # ExtrudeFeature
        feat_extrude = ExtrudeFeature(
            plane_origin=(0, 0, 0),
            plane_normal=(0, 0, 1),
            plane_x_dir=(1, 0, 0),
            plane_y_dir=(0, 1, 0)
        )
        assert feat_extrude.plane_origin == (0, 0, 0)
        assert feat_extrude.plane_normal == (0, 0, 1)

        # PushPullFeature sollte gleiche Parameter haben
        from modeling import PushPullFeature
        feat_pushpull = PushPullFeature(
            plane_origin=(5, 0, 0),
            plane_normal=(0, 1, 0)
        )
        assert feat_pushpull.plane_origin == (5, 0, 0)


# ============================================================================
# TNP v4.0 ShapeID Consistency Tests
# ============================================================================

class TestTNPShapeIDConsistency:
    """Tests für konsistentes ShapeID-Tracking über alle Features."""

    def test_extrude_has_face_shape_id(self):
        """ExtrudeFeature hat face_shape_id für TNP v4.0."""
        feat = ExtrudeFeature()
        assert hasattr(feat, "face_shape_id")
        assert hasattr(feat, "face_index")
        assert hasattr(feat, "face_selector")

    def test_pushpull_has_face_shape_id(self):
        """PushPullFeature hat face_shape_id für TNP v4.0."""
        from modeling import PushPullFeature
        feat = PushPullFeature()
        assert hasattr(feat, "face_shape_id")
        assert hasattr(feat, "face_index")
        assert hasattr(feat, "face_selector")

    def test_revolve_has_face_shape_id(self):
        """RevolveFeature hat face_shape_id für TNP v4.0."""
        feat = RevolveFeature()
        # TNP v4.0 Support (Phase 3)
        assert hasattr(feat, "face_shape_id")
        assert hasattr(feat, "face_index")
        assert hasattr(feat, "face_selector")

    def test_loft_has_profile_shape_ids(self):
        """LoftFeature hat profile_shape_ids (plural) für multiple Profile."""
        feat = LoftFeature()
        assert hasattr(feat, "profile_shape_ids")
        assert hasattr(feat, "profile_geometric_selectors")
        # Loft hat multiple Profiles → plural
        assert isinstance(feat.profile_shape_ids, list)

    def test_sweep_has_profile_path_shape_ids(self):
        """SweepFeature hat profile_shape_id und path_shape_id."""
        feat = SweepFeature()
        # Singular weil Sweep nur ein Profil hat
        assert hasattr(feat, "profile_shape_id")
        assert hasattr(feat, "path_shape_id")
        assert hasattr(feat, "profile_geometric_selector")
        assert hasattr(feat, "path_geometric_selector")

    def test_boolean_has_modified_shape_ids(self):
        """BooleanFeature hat modified_shape_ids."""
        from modeling import BooleanFeature
        feat = BooleanFeature()
        assert hasattr(feat, "modified_shape_ids")
        assert isinstance(feat.modified_shape_ids, list)


# ============================================================================
# Feature Creation Consistency Tests
# ============================================================================

class TestFeatureCreationConsistency:
    """Tests für konsistente Feature-Erstellung."""

    def test_all_features_have_type(self):
        """Alle Features setzen ihren Type korrekt in __post_init__."""
        feat_extrude = ExtrudeFeature()
        assert feat_extrude.type == FeatureType.EXTRUDE

        feat_revolve = RevolveFeature()
        assert feat_revolve.type == FeatureType.REVOLVE

        feat_loft = LoftFeature()
        assert feat_loft.type == FeatureType.LOFT

        feat_sweep = SweepFeature()
        assert feat_sweep.type == FeatureType.SWEEP

        from modeling import BooleanFeature, PushPullFeature, PatternFeature
        feat_boolean = BooleanFeature()
        assert feat_boolean.type == FeatureType.BOOLEAN

        feat_pushpull = PushPullFeature()
        assert feat_pushpull.type == FeatureType.PUSHPULL

        feat_pattern = PatternFeature()
        assert feat_pattern.type == FeatureType.PATTERN

    def test_all_features_have_default_name(self):
        """Alle Features haben einen Default-Namen."""
        feat_extrude = ExtrudeFeature()
        assert feat_extrude.name == "Extrude"

        feat_revolve = RevolveFeature()
        assert feat_revolve.name == "Revolve"

        feat_loft = LoftFeature()
        assert feat_loft.name == "Loft"

        feat_sweep = SweepFeature()
        assert feat_sweep.name == "Sweep"


# ============================================================================
# Serialization Consistency Tests
# ============================================================================

class TestSerializationConsistency:
    """Tests für konsistente Serialisierung."""

    def test_revolve_serialization_with_shape_id(self):
        """RevolveFeature: Serialisierung mit ShapeID."""
        shape_id = ShapeID.create(
            shape_type=ShapeType.FACE,
            feature_id="feat_123",
            local_index=0,
            geometry_data=("test_face", 0, "FACE")
        )

        feat = RevolveFeature(
            angle=180.0,
            axis=(0, 1, 0),
            face_shape_id=shape_id,
            face_index=0
        )

        body = Body("TestBody", document=Document("Test"))
        body.add_feature(feat)
        body_dict = body.to_dict()
        feat_dict = body_dict["features"][0]

        # Prüfe Serialisierung
        assert feat_dict["feature_class"] == "RevolveFeature"
        assert feat_dict["angle"] == 180.0
        assert "face_shape_id" in feat_dict
        sid_data = feat_dict["face_shape_id"]
        assert sid_data["shape_type"] == "FACE"
        assert sid_data["feature_id"] == "feat_123"

    def test_revolve_deserialization_with_shape_id(self):
        """RevolveFeature: Deserialisierung mit ShapeID."""
        data = {
            "name": "TestBody",
            "id": "body_123",
            "features": [{
                "feature_class": "RevolveFeature",
                "id": "feat_456",
                "name": "Test Revolve",
                "angle": 270.0,
                "axis": [0, 1, 0],
                "axis_origin": [0, 0, 0],
                "operation": "New Body",
                "face_shape_id": {
                    "uuid": "test-uuid",
                    "shape_type": "FACE",
                    "feature_id": "feat_123",
                    "local_index": 0,
                    "geometry_hash": "hash123",
                    "timestamp": 1234567890.0
                },
                "face_index": 0,
                "visible": True,
                "suppressed": False,
                "status": "OK",
            }]
        }

        body = Body.from_dict(data)

        assert len(body.features) == 1
        feat = body.features[0]
        assert isinstance(feat, RevolveFeature)
        assert feat.angle == 270.0
        assert feat.face_index == 0
        assert feat.face_shape_id is not None
        assert feat.face_shape_id.shape_type == ShapeType.FACE


# ============================================================================
# Test Runner
# ============================================================================

def run_all_api_consistency_tests():
    """Führt alle API-Konsistenz Tests aus."""
    print("\n" + "="*60)
    print("API CONSISTENCY TEST SUITE")
    print("="*60 + "\n")

    tests = [
        # Parameter Consistency
        ("Operation Values Consistent", TestAPIParameterConsistency().test_operation_values_consistent),
        ("Distance/Angle Units Consistent", TestAPIParameterConsistency().test_distance_angle_units_consistent),
        ("Axis Direction Consistent", TestAPIParameterConsistency().test_axis_direction_consistent),
        ("Plane Parameters Consistent", TestAPIParameterConsistency().test_plane_parameters_consistent),

        # TNP v4.0 Consistency
        ("Extrude has face_shape_id", TestTNPShapeIDConsistency().test_extrude_has_face_shape_id),
        ("PushPull has face_shape_id", TestTNPShapeIDConsistency().test_pushpull_has_face_shape_id),
        ("Revolve has face_shape_id", TestTNPShapeIDConsistency().test_revolve_has_face_shape_id),
        ("Loft has profile_shape_ids", TestTNPShapeIDConsistency().test_loft_has_profile_shape_ids),
        ("Sweep has profile_path_shape_ids", TestTNPShapeIDConsistency().test_sweep_has_profile_path_shape_ids),
        ("Boolean has modified_shape_ids", TestTNPShapeIDConsistency().test_boolean_has_modified_shape_ids),

        # Feature Creation Consistency
        ("All Features have type", TestFeatureCreationConsistency().test_all_features_have_type),
        ("All Features have default name", TestFeatureCreationConsistency().test_all_features_have_default_name),

        # Serialization Consistency
        ("Revolve Serialize with ShapeID", TestSerializationConsistency().test_revolve_serialization_with_shape_id),
        ("Revolve Deserialize with ShapeID", TestSerializationConsistency().test_revolve_deserialization_with_shape_id),
    ]

    passed = 0
    failed = 0
    errors = []

    for name, test_func in tests:
        try:
            print(f"Running: {name}...", end=" ")
            test_func()
            print("✓ PASS")
            passed += 1
        except AssertionError as e:
            print(f"✗ FAIL: {e}")
            failed += 1
            errors.append((name, str(e)[:100]))
        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed += 1
            errors.append((name, str(e)[:100]))

    print("\n" + "="*60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*60)

    if errors:
        print("\nFailed Tests:")
        for name, error in errors:
            print(f"  - {name}: {error}")

    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_all_api_consistency_tests()
    sys.exit(0 if success else 1)
