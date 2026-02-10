"""
BooleanFeature Test Suite
=========================

Tests für das neue BooleanFeature mit:
- Feature Creation
- Validation
- Serialization (to_dict/from_dict)
- BooleanEngineV4 Integration
- TNP v4.0 ShapeID Tracking

Author: Claude (CAD System Improvement)
Date: 2026-02-10
"""
# pytest not required for basic tests
import build123d as bd
from build123d import Solid, Location, Vector

from modeling import (
    Body, Document, BooleanFeature,
    FeatureType
)
from modeling.boolean_engine_v4 import BooleanEngineV4, VolumeCache
from modeling.result_types import ResultStatus, BooleanResult
from modeling.tnp_system import ShapeID, ShapeType


# ============================================================================
# BooleanFeature Creation Tests
# ============================================================================

class TestBooleanFeatureCreation:
    """Tests für BooleanFeature Erstellung."""

    def test_boolean_feature_basic_creation(self):
        """BooleanFeature: Basis-Erstellung."""
        feat = BooleanFeature(
            operation="Cut",
            tool_body_id="tool_body_123"
        )

        assert feat.type == FeatureType.BOOLEAN
        assert feat.operation == "Cut"
        assert feat.tool_body_id == "tool_body_123"
        assert feat.name == "Boolean: Cut"

    def test_boolean_feature_all_operations(self):
        """BooleanFeature: Alle Operation-Typen."""
        for op in ["Join", "Cut", "Common"]:
            feat = BooleanFeature(operation=op)
            assert feat.operation == op
            assert feat.name == f"Boolean: {op}"

    def test_boolean_feature_with_tolerance(self):
        """BooleanFeature: Mit custom Tolerance."""
        feat = BooleanFeature(
            operation="Cut",
            fuzzy_tolerance=0.00005
        )

        assert feat.fuzzy_tolerance == 0.00005

    def test_boolean_feature_with_volume_change(self):
        """BooleanFeature: Mit erwarteter Volumenänderung."""
        feat = BooleanFeature(
            operation="Cut",
            expected_volume_change=-100.0
        )

        assert feat.expected_volume_change == -100.0

    def test_boolean_feature_default_values(self):
        """BooleanFeature: Default-Werte."""
        feat = BooleanFeature()

        assert feat.operation == "Cut"
        assert feat.tool_body_id is None
        assert feat.tool_solid_data is None
        assert feat.fuzzy_tolerance is None
        assert feat.modified_shape_ids == []


# ============================================================================
# BooleanFeature Validation Tests
# ============================================================================

class TestBooleanFeatureValidation:
    """Tests für BooleanFeature Validation."""

    def test_validate_valid_cut(self):
        """BooleanFeature Validation: Gültiges Cut."""
        feat = BooleanFeature(
            operation="Cut",
            tool_body_id="tool_123"
        )

        is_valid, error = feat.validate()
        assert is_valid
        assert error == ""

    def test_validate_valid_join(self):
        """BooleanFeature Validation: Gültiges Join."""
        feat = BooleanFeature(
            operation="Join",
            tool_body_id="tool_123"
        )

        is_valid, error = feat.validate()
        assert is_valid

    def test_validate_valid_common(self):
        """BooleanFeature Validation: Gültiges Common."""
        feat = BooleanFeature(
            operation="Common",
            tool_body_id="tool_123"
        )

        is_valid, error = feat.validate()
        assert is_valid

    def test_validate_unknown_operation(self):
        """BooleanFeature Validation: Unbekannte Operation."""
        feat = BooleanFeature(
            operation="InvalidOp",
            tool_body_id="tool_123"
        )

        is_valid, error = feat.validate()
        assert not is_valid
        assert "Unknown operation" in error

    def test_validate_no_tool(self):
        """BooleanFeature Validation: Kein Tool."""
        feat = BooleanFeature(
            operation="Cut"
        )

        is_valid, error = feat.validate()
        assert not is_valid
        assert "tool_body_id or tool_solid_data" in error


# ============================================================================
# BooleanFeature get_operation_type Tests
# ============================================================================

class TestBooleanFeatureOperationType:
    """Tests für get_operation_type() Methode."""

    def test_operation_type_standardization(self):
        """BooleanFeature: Operation-Typ Standardisierung."""
        test_cases = [
            ("Join", "Join"),
            ("Union", "Join"),
            ("Fuse", "Join"),
            ("Add", "Join"),
            ("Cut", "Cut"),
            ("Subtract", "Cut"),
            ("Difference", "Cut"),
            ("Common", "Common"),
            ("Intersect", "Common"),
            ("Intersection", "Common"),
        ]

        for input_op, expected_op in test_cases:
            feat = BooleanFeature(operation=input_op)
            assert feat.get_operation_type() == expected_op


# ============================================================================
# BooleanFeature Serialization Tests
# ============================================================================

class TestBooleanFeatureSerialization:
    """Tests für BooleanFeature Serialisierung."""

    def test_to_dict_basic(self):
        """BooleanFeature: to_dict() Basis."""
        feat = BooleanFeature(
            id="feat_123",
            name="Test Boolean",
            operation="Cut",
            tool_body_id="tool_456",
            fuzzy_tolerance=0.0001
        )

        # to_dict wird über Body.to_dict() aufgerufen
        body = Body("TestBody", document=Document("Test"))
        body.add_feature(feat)

        body_dict = body.to_dict()
        feat_dict = body_dict["features"][0]

        assert feat_dict["feature_class"] == "BooleanFeature"
        assert feat_dict["operation"] == "Cut"
        assert feat_dict["tool_body_id"] == "tool_456"
        assert feat_dict["fuzzy_tolerance"] == 0.0001

    def test_from_dict_basic(self):
        """BooleanFeature: from_dict() Basis."""
        data = {
            "name": "TestBody",
            "id": "body_123",
            "features": [{
                "feature_class": "BooleanFeature",
                "id": "feat_456",
                "name": "Test Boolean",
                "operation": "Join",
                "tool_body_id": "tool_789",
                "fuzzy_tolerance": 0.0002,
                "visible": True,
                "suppressed": False,
                "status": "OK",
                "status_message": "",
                "status_details": {},
            }]
        }

        body = Body.from_dict(data)

        assert len(body.features) == 1
        feat = body.features[0]
        assert isinstance(feat, BooleanFeature)
        assert feat.operation == "Join"
        assert feat.tool_body_id == "tool_789"
        assert feat.fuzzy_tolerance == 0.0002

    def test_serialization_with_modified_shape_ids(self):
        """BooleanFeature: Serialisierung mit ShapeIDs."""
        # ShapeID für Test erstellen
        shape_id = ShapeID.create(
            shape_type=ShapeType.FACE,
            feature_id="feat_123",
            local_index=0,
            geometry_data=("test_face", 0, "FACE")
        )

        feat = BooleanFeature(
            operation="Cut",
            tool_body_id="tool_123",
            modified_shape_ids=[shape_id]
        )

        # Serialisieren via Body
        body = Body("TestBody", document=Document("Test"))
        body.add_feature(feat)
        body_dict = body.to_dict()
        feat_dict = body_dict["features"][0]

        # Prüfe dass ShapeID serialisiert wurde
        assert "modified_shape_ids" in feat_dict
        assert len(feat_dict["modified_shape_ids"]) == 1
        sid_data = feat_dict["modified_shape_ids"][0]
        assert sid_data["shape_type"] == "FACE"
        assert sid_data["feature_id"] == "feat_123"
        assert sid_data["local_index"] == 0

    def test_deserialization_with_modified_shape_ids(self):
        """BooleanFeature: Deserialisierung mit ShapeIDs."""
        data = {
            "name": "TestBody",
            "id": "body_123",
            "features": [{
                "feature_class": "BooleanFeature",
                "operation": "Cut",
                "tool_body_id": "tool_123",
                "modified_shape_ids": [{
                    "uuid": "test-uuid",
                    "shape_type": "FACE",
                    "feature_id": "feat_123",
                    "local_index": 0,
                    "geometry_hash": "hash123",
                    "timestamp": 1234567890.0
                }],
                "visible": True,
                "suppressed": False,
                "status": "OK",
            }]
        }

        body = Body.from_dict(data)
        feat = body.features[0]

        assert len(feat.modified_shape_ids) == 1
        sid = feat.modified_shape_ids[0]
        assert sid.shape_type == ShapeType.FACE
        assert sid.feature_id == "feat_123"
        assert sid.local_index == 0


# ============================================================================
# BooleanFeature Integration Tests
# ============================================================================

class TestBooleanFeatureIntegration:
    """Integration-Tests für BooleanFeature mit BooleanEngineV4."""

    def test_boolean_cut_with_feature(self):
        """BooleanFeature: Cut-Operation mit BooleanEngineV4."""
        doc = Document("Boolean Feature Integration Test")
        body = Body("TargetBody", document=doc)
        doc.add_body(body)

        # Target Solid
        target = bd.Solid.make_box(20, 20, 10)
        body._build123d_solid = target

        # Tool Solid
        tool = bd.Solid.make_cylinder(3.0, 15).located(Location(Vector(10, 10, 0)))

        # Boolean-Operation ausführen
        result = BooleanEngineV4.execute_boolean(
            body, tool, "Cut"
        )

        assert result.status == ResultStatus.SUCCESS
        assert body._build123d_solid.volume < target.volume

    def test_boolean_join_with_feature(self):
        """BooleanFeature: Join-Operation mit BooleanEngineV4."""
        doc = Document("Boolean Join Integration Test")
        body = Body("JoinBody", document=doc)
        doc.add_body(body)

        # Zwei Boxes zusammenfügen
        box1 = bd.Solid.make_box(10, 10, 10).located(Location(Vector(0, 0, 0)))
        box2 = bd.Solid.make_box(10, 10, 10).located(Location(Vector(10, 0, 0)))

        body._build123d_solid = box1

        result = BooleanEngineV4.execute_boolean(
            body, box2, "Join"
        )

        assert result.status == ResultStatus.SUCCESS
        assert body._build123d_solid.volume > box1.volume

    def test_boolean_common_with_feature(self):
        """BooleanFeature: Common-Operation mit BooleanEngineV4."""
        doc = Document("Boolean Common Integration Test")
        body = Body("CommonBody", document=doc)
        doc.add_body(body)

        # Zwei überlappende Boxes
        box1 = bd.Solid.make_box(20, 20, 20)
        box2 = bd.Solid.make_box(20, 20, 20).located(Location(Vector(10, 10, 10)))

        body._build123d_solid = box1

        result = BooleanEngineV4.execute_boolean(
            body, box2, "Intersect"  # BooleanEngineV4 nutzt "Intersect" nicht "Common"
        )

        assert result.status == ResultStatus.SUCCESS
        assert body._build123d_solid.volume < box1.volume


# ============================================================================
# BooleanFeature Workflow Tests
# ============================================================================

class TestBooleanFeatureWorkflow:
    """Workflow-Tests für BooleanFeature."""

    def test_feature_add_to_body(self):
        """BooleanFeature: Feature zu Body hinzufügen."""
        doc = Document("Feature Add Test")
        body = Body("TestBody", document=doc)
        doc.add_body(body)

        feat = BooleanFeature(
            operation="Cut",
            tool_body_id="tool_123"
        )

        body.add_feature(feat)

        assert len(body.features) == 1
        assert body.features[0] is feat
        # Feature wurde zur Liste hinzugefügt, aber nicht ausgeführt
        # (BooleanFeature arbeitet mit execute_boolean für Ausführung)

    def test_feature_multiple_booleans(self):
        """BooleanFeature: Mehrere Boolean-Operationen."""
        doc = Document("Multi Boolean Test")
        body = Body("MultiBooleanBody", document=doc)
        doc.add_body(body)

        # Erstelle Box
        box = bd.Solid.make_box(30, 30, 10)
        body._build123d_solid = box

        # Füge zwei Boolean-Features hinzu
        feat1 = BooleanFeature(
            operation="Cut",
            tool_body_id="cutter1",
            expected_volume_change=-50.0
        )

        feat2 = BooleanFeature(
            operation="Cut",
            tool_body_id="cutter2",
            expected_volume_change=-30.0
        )

        body.add_feature(feat1)
        body.add_feature(feat2)

        assert len(body.features) == 2
        assert body.features[0].operation == "Cut"
        assert body.features[1].operation == "Cut"


# ============================================================================
# Test Runner
# ============================================================================

def run_all_boolean_feature_tests():
    """Führt alle BooleanFeature Tests aus."""
    print("\n" + "="*60)
    print("BOOLEAN FEATURE TEST SUITE")
    print("="*60 + "\n")

    tests = [
        # Creation
        ("BooleanFeature Basic Creation", TestBooleanFeatureCreation().test_boolean_feature_basic_creation),
        ("BooleanFeature All Operations", TestBooleanFeatureCreation().test_boolean_feature_all_operations),
        ("BooleanFeature With Tolerance", TestBooleanFeatureCreation().test_boolean_feature_with_tolerance),
        ("BooleanFeature With Volume Change", TestBooleanFeatureCreation().test_boolean_feature_with_volume_change),
        ("BooleanFeature Default Values", TestBooleanFeatureCreation().test_boolean_feature_default_values),

        # Validation
        ("BooleanFeature Validate Valid Cut", TestBooleanFeatureValidation().test_validate_valid_cut),
        ("BooleanFeature Validate Valid Join", TestBooleanFeatureValidation().test_validate_valid_join),
        ("BooleanFeature Validate Valid Common", TestBooleanFeatureValidation().test_validate_valid_common),
        ("BooleanFeature Validate Unknown Op", TestBooleanFeatureValidation().test_validate_unknown_operation),
        ("BooleanFeature Validate No Tool", TestBooleanFeatureValidation().test_validate_no_tool),

        # Operation Type
        ("BooleanFeature Operation Type Standardization", TestBooleanFeatureOperationType().test_operation_type_standardization),

        # Serialization
        ("BooleanFeature to_dict Basic", TestBooleanFeatureSerialization().test_to_dict_basic),
        ("BooleanFeature from_dict Basic", TestBooleanFeatureSerialization().test_from_dict_basic),
        ("BooleanFeature Serialization with ShapeIDs", TestBooleanFeatureSerialization().test_serialization_with_modified_shape_ids),
        ("BooleanFeature Deserialization with ShapeIDs", TestBooleanFeatureSerialization().test_deserialization_with_modified_shape_ids),

        # Integration
        ("BooleanFeature Cut Integration", TestBooleanFeatureIntegration().test_boolean_cut_with_feature),
        ("BooleanFeature Join Integration", TestBooleanFeatureIntegration().test_boolean_join_with_feature),
        ("BooleanFeature Common Integration", TestBooleanFeatureIntegration().test_boolean_common_with_feature),

        # Workflow
        ("BooleanFeature Add to Body", TestBooleanFeatureWorkflow().test_feature_add_to_body),
        ("BooleanFeature Multiple Booleans", TestBooleanFeatureWorkflow().test_feature_multiple_booleans),
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
    success = run_all_boolean_feature_tests()
    sys.exit(0 if success else 1)
