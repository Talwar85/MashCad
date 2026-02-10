"""
PatternFeature Test Suite
========================

Tests für das neue PatternFeature mit:
- Linear Pattern (Rechteckiges Muster)
- Circular Pattern (Zirkuläres Muster)
- Mirror Pattern (Spiegelung)
- Validation
- Serialization (to_dict/from_dict)

Author: Claude (CAD System Improvement)
Date: 2026-02-10
"""
import pytest
import build123d as bd
from build123d import Solid, Location, Vector

from modeling import (
    Body, Document, PatternFeature,
    FeatureType
)


# ============================================================================
# PatternFeature Creation Tests
# ============================================================================

class TestPatternFeatureCreation:
    """Tests für PatternFeature Erstellung."""

    def test_pattern_basic_creation(self):
        """PatternFeature: Basis-Erstellung."""
        feat = PatternFeature(
            pattern_type="Linear"
        )

        assert feat.type == FeatureType.PATTERN
        assert feat.pattern_type == "Linear"
        assert feat.name == "Pattern: Linear"

    def test_pattern_linear_creation(self):
        """PatternFeature: Linear Pattern."""
        feat = PatternFeature(
            pattern_type="Linear",
            count=5,
            spacing=20.0
        )

        assert feat.pattern_type == "Linear"
        assert feat.count == 5
        assert feat.spacing == 20.0

    def test_pattern_circular_creation(self):
        """PatternFeature: Circular Pattern."""
        feat = PatternFeature(
            pattern_type="Circular",
            count=8,
            axis_direction=(0, 0, 1)
        )

        assert feat.pattern_type == "Circular"
        assert feat.count == 8

    def test_pattern_mirror_creation(self):
        """PatternFeature: Mirror Pattern."""
        feat = PatternFeature(
            pattern_type="Mirror",
            mirror_plane="XY"
        )

        assert feat.pattern_type == "Mirror"
        assert feat.mirror_plane == "XY"


# ============================================================================
# PatternFeature Validation Tests
# ============================================================================

class TestPatternFeatureValidation:
    """Tests für PatternFeature Validation."""

    def test_validate_linear_valid(self):
        """Validate: Gültiges Linear Pattern."""
        feat = PatternFeature(
            pattern_type="Linear",
            count=3,
            spacing=10.0
        )

        is_valid, error = feat.validate()
        assert is_valid

    def test_validate_linear_count_too_small(self):
        """Validate: Linear count < 2."""
        feat = PatternFeature(
            pattern_type="Linear",
            count=1,
            spacing=10.0
        )

        is_valid, error = feat.validate()
        assert not is_valid
        assert "at least 2" in error

    def test_validate_linear_negative_spacing(self):
        """Validate: Negative Spacing."""
        feat = PatternFeature(
            pattern_type="Linear",
            count=3,
            spacing=-5.0
        )

        is_valid, error = feat.validate()
        assert not is_valid
        assert "positive" in error

    def test_validate_circular_valid(self):
        """Validate: Gültiges Circular Pattern."""
        feat = PatternFeature(
            pattern_type="Circular",
            count=6
        )

        is_valid, error = feat.validate()
        assert is_valid

    def test_validate_circular_count_too_small(self):
        """Validate: Circular count < 2."""
        feat = PatternFeature(
            pattern_type="Circular",
            count=1
        )

        is_valid, error = feat.validate()
        assert not is_valid

    def test_validate_mirror_valid(self):
        """Validate: Gültiges Mirror Pattern."""
        feat = PatternFeature(
            pattern_type="Mirror",
            mirror_plane="XY"
        )

        is_valid, error = feat.validate()
        assert is_valid

    def test_validate_mirror_no_plane(self):
        """Validate: Mirror ohne Plane."""
        feat = PatternFeature(
            pattern_type="Mirror"
        )

        is_valid, error = feat.validate()
        assert not is_valid
        assert "mirror_plane" in error

    def test_validate_unknown_type(self):
        """Validate: Unbekannter Pattern-Typ."""
        feat = PatternFeature(
            pattern_type="Unknown"
        )

        is_valid, error = feat.validate()
        assert not is_valid
        assert "Unknown pattern_type" in error


# ============================================================================
# PatternFeature get_total_instances Tests
# ============================================================================

class TestPatternFeatureInstances:
    """Tests für get_total_instances() Methode."""

    def test_total_instances_linear_1d(self):
        """get_total_instances: Linear 1D."""
        feat = PatternFeature(
            pattern_type="Linear",
            count=5,
            spacing=10.0
        )

        assert feat.get_total_instances() == 5

    def test_total_instances_linear_2d(self):
        """get_total_instances: Linear 2D."""
        feat = PatternFeature(
            pattern_type="Linear",
            count=4,
            count_2=3
        )

        assert feat.get_total_instances() == 12  # 4 * 3

    def test_total_instances_circular(self):
        """get_total_instances: Circular."""
        feat = PatternFeature(
            pattern_type="Circular",
            count=8
        )

        assert feat.get_total_instances() == 8

    def test_total_instances_mirror(self):
        """get_total_instances: Mirror."""
        feat = PatternFeature(
            pattern_type="Mirror",
            mirror_plane="XY"
        )

        assert feat.get_total_instances() == 2  # Original + Spiegel


# ============================================================================
# PatternFeature Serialization Tests
# ============================================================================

class TestPatternFeatureSerialization:
    """Tests für PatternFeature Serialisierung."""

    def test_to_dict_linear(self):
        """PatternFeature: to_dict() Linear."""
        feat = PatternFeature(
            id="feat_123",
            name="Linear Pattern",
            pattern_type="Linear",
            count=4,
            spacing=20.0,
            count_2=3
        )

        body = Body("TestBody", document=Document("Test"))
        body.add_feature(feat)

        body_dict = body.to_dict()
        feat_dict = body_dict["features"][0]

        assert feat_dict["feature_class"] == "PatternFeature"
        assert feat_dict["pattern_type"] == "Linear"
        assert feat_dict["count"] == 4
        assert feat_dict["count_2"] == 3

    def test_from_dict_linear(self):
        """PatternFeature: from_dict() Linear."""
        data = {
            "name": "TestBody",
            "id": "body_123",
            "features": [{
                "feature_class": "PatternFeature",
                "id": "feat_456",
                "name": "Linear Pattern",
                "pattern_type": "Linear",
                "count": 5,
                "spacing": 15.0,
                "direction_1": [1, 0, 0],
                "direction_2": [0, 1, 0],
                "count_2": 2,
                "visible": True,
                "suppressed": False,
                "status": "OK",
            }]
        }

        body = Body.from_dict(data)

        assert len(body.features) == 1
        feat = body.features[0]
        assert isinstance(feat, PatternFeature)
        assert feat.pattern_type == "Linear"
        assert feat.count == 5
        assert feat.spacing == 15.0
        assert feat.count_2 == 2

    def test_serialization_circular(self):
        """PatternFeature: Circular Serialisierung."""
        feat = PatternFeature(
            pattern_type="Circular",
            count=6,
            axis_origin=[10, 10, 0],
            axis_direction=[0, 0, 1]
        )

        body = Body("TestBody", document=Document("Test"))
        body.add_feature(feat)
        body_dict = body.to_dict()
        feat_dict = body_dict["features"][0]

        assert feat_dict["pattern_type"] == "Circular"
        assert feat_dict["count"] == 6
        assert feat_dict["axis_origin"] == [10, 10, 0]

    def test_serialization_mirror(self):
        """PatternFeature: Mirror Serialisierung."""
        feat = PatternFeature(
            pattern_type="Mirror",
            mirror_plane="YZ",
            mirror_origin=[5, 0, 0]
        )

        body = Body("TestBody", document=Document("Test"))
        body.add_feature(feat)
        body_dict = body.to_dict()
        feat_dict = body_dict["features"][0]

        assert feat_dict["pattern_type"] == "Mirror"
        assert feat_dict["mirror_plane"] == "YZ"


# ============================================================================
# PatternFeature Integration Tests
# ============================================================================

class TestPatternFeatureIntegration:
    """Integration-Tests für PatternFeature."""

    def test_pattern_add_to_body(self):
        """PatternFeature: Zu Body hinzufügen."""
        doc = Document("Pattern Test")
        body = Body("TestBody", document=doc)
        doc.add_body(body)

        feat = PatternFeature(
            pattern_type="Linear",
            count=3
        )

        body.add_feature(feat)

        assert len(body.features) == 1
        assert isinstance(body.features[0], PatternFeature)

    def test_pattern_multiple_features(self):
        """PatternFeature: Mehrere Pattern-Features."""
        doc = Document("Multi Pattern Test")
        body = Body("TestBody", document=doc)
        doc.add_body(body)

        feat1 = PatternFeature(pattern_type="Linear", count=3)
        feat2 = PatternFeature(pattern_type="Circular", count=6)

        body.add_feature(feat1)
        body.add_feature(feat2)

        assert len(body.features) == 2


# ============================================================================
# Test Runner
# ============================================================================

def run_all_pattern_feature_tests():
    """Führt alle PatternFeature Tests aus."""
    print("\n" + "="*60)
    print("PATTERN FEATURE TEST SUITE")
    print("="*60 + "\n")

    tests = [
        # Creation
        ("PatternFeature Basic Creation", TestPatternFeatureCreation().test_pattern_basic_creation),
        ("PatternFeature Linear Creation", TestPatternFeatureCreation().test_pattern_linear_creation),
        ("PatternFeature Circular Creation", TestPatternFeatureCreation().test_pattern_circular_creation),
        ("PatternFeature Mirror Creation", TestPatternFeatureCreation().test_pattern_mirror_creation),

        # Validation
        ("PatternFeature Validate Linear", TestPatternFeatureValidation().test_validate_linear_valid),
        ("PatternFeature Validate Linear count < 2", TestPatternFeatureValidation().test_validate_linear_count_too_small),
        ("PatternFeature Validate negative spacing", TestPatternFeatureValidation().test_validate_linear_negative_spacing),
        ("PatternFeature Validate Circular", TestPatternFeatureValidation().test_validate_circular_valid),
        ("PatternFeature Validate Circular < 2", TestPatternFeatureValidation().test_validate_circular_count_too_small),
        ("PatternFeature Validate Mirror", TestPatternFeatureValidation().test_validate_mirror_valid),
        ("PatternFeature Validate Mirror no plane", TestPatternFeatureValidation().test_validate_mirror_no_plane),
        ("PatternFeature Validate unknown type", TestPatternFeatureValidation().test_validate_unknown_type),

        # Total Instances
        ("PatternFeature Total Instances Linear 1D", TestPatternFeatureInstances().test_total_instances_linear_1d),
        ("PatternFeature Total Instances Linear 2D", TestPatternFeatureInstances().test_total_instances_linear_2d),
        ("PatternFeature Total Instances Circular", TestPatternFeatureInstances().test_total_instances_circular),
        ("PatternFeature Total Instances Mirror", TestPatternFeatureInstances().test_total_instances_mirror),

        # Serialization
        ("PatternFeature to_dict Linear", TestPatternFeatureSerialization().test_to_dict_linear),
        ("PatternFeature from_dict Linear", TestPatternFeatureSerialization().test_from_dict_linear),
        ("PatternFeature Serialization Circular", TestPatternFeatureSerialization().test_serialization_circular),
        ("PatternFeature Serialization Mirror", TestPatternFeatureSerialization().test_serialization_mirror),

        # Integration
        ("PatternFeature Add to Body", TestPatternFeatureIntegration().test_pattern_add_to_body),
        ("PatternFeature Multiple Features", TestPatternFeatureIntegration().test_pattern_multiple_features),
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
    success = run_all_pattern_feature_tests()
    sys.exit(0 if success else 1)
