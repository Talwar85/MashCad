"""
PushPullFeature Test Suite
=========================

Tests für das neue PushPullFeature mit:
- Feature Creation
- Validation (Push vs Pull)
- Serialization (to_dict/from_dict)
- TNP v4.0 Face-Referenz Tracking

Author: Claude (CAD System Improvement)
Date: 2026-02-10
"""
import pytest
import build123d as bd
from build123d import Solid, Location, Vector

from modeling import (
    Body, Document, PushPullFeature,
    FeatureType
)
from modeling.tnp_system import ShapeID, ShapeType


# ============================================================================
# PushPullFeature Creation Tests
# ============================================================================

class TestPushPullFeatureCreation:
    """Tests für PushPullFeature Erstellung."""

    def test_pushpull_basic_creation(self):
        """PushPullFeature: Basis-Erstellung."""
        feat = PushPullFeature(
            face_index=0,
            distance=5.0
        )

        assert feat.type == FeatureType.PUSHPULL
        assert feat.distance == 5.0
        assert feat.face_index == 0
        assert feat.direction == 1

    def test_pushpull_default_values(self):
        """PushPullFeature: Default-Werte."""
        feat = PushPullFeature()

        assert feat.distance == 10.0
        assert feat.direction == 1
        assert feat.operation == "Join"
        assert feat.face_index is None
        assert feat.face_shape_id is None

    def test_pushpull_with_negative_distance(self):
        """PushPullFeature: Negative Distanz (Push)."""
        feat = PushPullFeature(
            face_index=0,
            distance=-5.0
        )

        assert feat.distance == -5.0
        assert feat.is_push()

    def test_pushpull_with_direction(self):
        """PushPullFeature: Mit Richtung."""
        feat = PushPullFeature(
            face_index=0,
            distance=10.0,
            direction=-1
        )

        assert feat.direction == -1
        assert feat.get_effective_distance() == -10.0
        assert feat.is_push()


# ============================================================================
# PushPullFeature Push/Pull Tests
# ============================================================================

class TestPushPullFeaturePushPull:
    """Tests für Push/Pull Erkennung."""

    def test_is_push_positive_distance(self):
        """is_push: Positive Distanz mit direction=-1."""
        feat = PushPullFeature(
            distance=10.0,
            direction=-1
        )

        assert feat.is_push()
        assert not feat.is_pull()

    def test_is_push_negative_distance(self):
        """is_push: Negative Distanz mit direction=1."""
        feat = PushPullFeature(
            distance=-10.0,
            direction=1
        )

        assert feat.is_push()
        assert not feat.is_pull()

    def test_is_pull_positive_distance(self):
        """is_pull: Positive Distanz mit direction=1."""
        feat = PushPullFeature(
            distance=10.0,
            direction=1
        )

        assert feat.is_pull()
        assert not feat.is_push()

    def test_get_effective_distance(self):
        """get_effective_distance: Korrekte Berechnung."""
        feat1 = PushPullFeature(distance=10.0, direction=1)
        assert feat1.get_effective_distance() == 10.0

        feat2 = PushPullFeature(distance=10.0, direction=-1)
        assert feat2.get_effective_distance() == -10.0

        feat3 = PushPullFeature(distance=-5.0, direction=1)
        assert feat3.get_effective_distance() == -5.0


# ============================================================================
# PushPullFeature Validation Tests
# ============================================================================

class TestPushPullFeatureValidation:
    """Tests für PushPullFeature Validation."""

    def test_validate_valid_with_face_index(self):
        """Validate: Gültig mit face_index."""
        feat = PushPullFeature(
            face_index=0,
            distance=5.0
        )

        is_valid, error = feat.validate()
        assert is_valid
        assert error == ""

    def test_validate_valid_with_face_shape_id(self):
        """Validate: Gültig mit face_shape_id."""
        feat = PushPullFeature(
            face_shape_id=ShapeID.create(
                shape_type=ShapeType.FACE,
                feature_id="feat_1",
                local_index=0,
                geometry_data=("test", 0, "FACE")
            ),
            distance=5.0
        )

        is_valid, error = feat.validate()
        assert is_valid

    def test_validate_no_face_reference(self):
        """Validate: Keine Face-Referenz."""
        feat = PushPullFeature(
            distance=5.0
        )

        is_valid, error = feat.validate()
        assert not is_valid
        assert "face_shape_id, face_index, or face_selector" in error

    def test_validate_zero_distance(self):
        """Validate: Zero-Distanz ist ungültig."""
        feat = PushPullFeature(
            face_index=0,
            distance=0.0
        )

        is_valid, error = feat.validate()
        assert not is_valid
        assert "cannot be zero" in error


# ============================================================================
# PushPullFeature Serialization Tests
# ============================================================================

class TestPushPullFeatureSerialization:
    """Tests für PushPullFeature Serialisierung."""

    def test_to_dict_basic(self):
        """PushPullFeature: to_dict() Basis."""
        feat = PushPullFeature(
            id="feat_123",
            name="Test PushPull",
            face_index=0,
            distance=5.0,
            direction=1
        )

        body = Body("TestBody", document=Document("Test"))
        body.add_feature(feat)

        body_dict = body.to_dict()
        feat_dict = body_dict["features"][0]

        assert feat_dict["feature_class"] == "PushPullFeature"
        assert feat_dict["face_index"] == 0
        assert feat_dict["distance"] == 5.0
        assert feat_dict["direction"] == 1

    def test_from_dict_basic(self):
        """PushPullFeature: from_dict() Basis."""
        data = {
            "name": "TestBody",
            "id": "body_123",
            "features": [{
                "feature_class": "PushPullFeature",
                "id": "feat_456",
                "name": "Test PushPull",
                "face_index": 0,
                "distance": -3.0,
                "direction": 1,
                "operation": "Cut",
                "visible": True,
                "suppressed": False,
                "status": "OK",
            }]
        }

        body = Body.from_dict(data)

        assert len(body.features) == 1
        feat = body.features[0]
        assert isinstance(feat, PushPullFeature)
        assert feat.face_index == 0
        assert feat.distance == -3.0

    def test_serialization_with_face_shape_id(self):
        """PushPullFeature: Serialisierung mit ShapeID."""
        shape_id = ShapeID.create(
            shape_type=ShapeType.FACE,
            feature_id="feat_123",
            local_index=0,
            geometry_data=("test_face", 0, "FACE")
        )

        feat = PushPullFeature(
            face_index=0,
            face_shape_id=shape_id,
            distance=5.0
        )

        body = Body("TestBody", document=Document("Test"))
        body.add_feature(feat)
        body_dict = body.to_dict()
        feat_dict = body_dict["features"][0]

        # Prüfe ShapeID Serialisierung
        assert "face_shape_id" in feat_dict
        sid_data = feat_dict["face_shape_id"]
        assert sid_data["shape_type"] == "FACE"
        assert sid_data["feature_id"] == "feat_123"


# ============================================================================
# PushPullFeature Integration Tests
# ============================================================================

class TestPushPullFeatureIntegration:
    """Integration-Tests für PushPullFeature."""

    def test_pushpull_add_to_body(self):
        """PushPullFeature: Zu Body hinzufügen."""
        doc = Document("PushPull Test")
        body = Body("TestBody", document=doc)
        doc.add_body(body)

        # Erstelle Box
        box = bd.Solid.make_box(10, 10, 10)
        body._build123d_solid = box

        # PushPull Feature
        feat = PushPullFeature(
            face_index=0,  # Oberste Face
            distance=5.0
        )

        body.add_feature(feat)

        assert len(body.features) == 1
        assert isinstance(body.features[0], PushPullFeature)

    def test_pushpull_multiple_features(self):
        """PushPullFeature: Mehrere Features."""
        doc = Document("Multi PushPull Test")
        body = Body("TestBody", document=doc)
        doc.add_body(body)

        box = bd.Solid.make_box(10, 10, 10)
        body._build123d_solid = box

        # Mehrere PushPull Features
        feat1 = PushPullFeature(face_index=0, distance=5.0)
        feat2 = PushPullFeature(face_index=1, distance=3.0)

        body.add_feature(feat1)
        body.add_feature(feat2)

        assert len(body.features) == 2


# ============================================================================
# Test Runner
# ============================================================================

def run_all_pushpull_feature_tests():
    """Führt alle PushPullFeature Tests aus."""
    print("\n" + "="*60)
    print("PUSHPULL FEATURE TEST SUITE")
    print("="*60 + "\n")

    tests = [
        # Creation
        ("PushPullFeature Basic Creation", TestPushPullFeatureCreation().test_pushpull_basic_creation),
        ("PushPullFeature Default Values", TestPushPullFeatureCreation().test_pushpull_default_values),
        ("PushPullFeature Negative Distance", TestPushPullFeatureCreation().test_pushpull_with_negative_distance),
        ("PushPullFeature With Direction", TestPushPullFeatureCreation().test_pushpull_with_direction),

        # Push/Pull
        ("PushPullFeature is_push (+dist, -dir)", TestPushPullFeaturePushPull().test_is_push_positive_distance),
        ("PushPullFeature is_push (-dist)", TestPushPullFeaturePushPull().test_is_push_negative_distance),
        ("PushPullFeature is_pull", TestPushPullFeaturePushPull().test_is_pull_positive_distance),
        ("PushPullFeature effective distance", TestPushPullFeaturePushPull().test_get_effective_distance),

        # Validation
        ("PushPullFeature Validate with face_index", TestPushPullFeatureValidation().test_validate_valid_with_face_index),
        ("PushPullFeature Validate with shape_id", TestPushPullFeatureValidation().test_validate_valid_with_face_shape_id),
        ("PushPullFeature Validate no face ref", TestPushPullFeatureValidation().test_validate_no_face_reference),
        ("PushPullFeature Validate zero distance", TestPushPullFeatureValidation().test_validate_zero_distance),

        # Serialization
        ("PushPullFeature to_dict Basic", TestPushPullFeatureSerialization().test_to_dict_basic),
        ("PushPullFeature from_dict Basic", TestPushPullFeatureSerialization().test_from_dict_basic),
        ("PushPullFeature Serialization with ShapeID", TestPushPullFeatureSerialization().test_serialization_with_face_shape_id),

        # Integration
        ("PushPullFeature Add to Body", TestPushPullFeatureIntegration().test_pushpull_add_to_body),
        ("PushPullFeature Multiple Features", TestPushPullFeatureIntegration().test_pushpull_multiple_features),
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
    success = run_all_pushpull_feature_tests()
    sys.exit(0 if success else 1)
