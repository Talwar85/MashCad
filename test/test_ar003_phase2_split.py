"""
AR-003 Phase 2 Split Tests

Tests for the extracted modules:
- modeling/feature_operations.py
- modeling/body_state.py

Verifies:
- New module functions work correctly
- Backward compatibility maintained
- Import paths work correctly
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestFeatureOperationsModule:
    """Tests for modeling/feature_operations.py"""

    def test_import_feature_operations_module(self):
        """Test that the feature_operations module can be imported."""
        from modeling import feature_operations
        assert feature_operations is not None

    def test_import_from_feature_operations(self):
        """Test importing specific functions from feature_operations."""
        from modeling.feature_operations import (
            record_tnp_failure,
            consume_tnp_failure,
            classify_error_code,
            default_next_action_for_code,
            build_operation_error_details,
            normalize_status_details_for_load,
            safe_operation,
        )
        assert callable(record_tnp_failure)
        assert callable(consume_tnp_failure)
        assert callable(classify_error_code)
        assert callable(default_next_action_for_code)
        assert callable(build_operation_error_details)
        assert callable(normalize_status_details_for_load)
        assert callable(safe_operation)

    def test_classify_error_code_critical(self):
        """Test error code classification for critical errors."""
        from modeling.feature_operations import classify_error_code
        
        status_class, severity = classify_error_code("rebuild_finalize_failed")
        assert status_class == "CRITICAL"
        assert severity == "critical"

    def test_classify_error_code_warning(self):
        """Test error code classification for warnings."""
        from modeling.feature_operations import classify_error_code
        
        status_class, severity = classify_error_code("fallback_used")
        assert status_class == "WARNING_RECOVERABLE"
        assert severity == "warning"
        
        status_class, severity = classify_error_code("tnp_ref_drift")
        assert status_class == "WARNING_RECOVERABLE"
        assert severity == "warning"

    def test_classify_error_code_blocked(self):
        """Test error code classification for blocked errors."""
        from modeling.feature_operations import classify_error_code
        
        status_class, severity = classify_error_code("blocked_by_upstream_error")
        assert status_class == "BLOCKED"
        assert severity == "blocked"
        
        status_class, severity = classify_error_code("fallback_blocked_strict")
        assert status_class == "BLOCKED"
        assert severity == "blocked"

    def test_classify_error_code_generic_error(self):
        """Test error code classification for generic errors."""
        from modeling.feature_operations import classify_error_code
        
        status_class, severity = classify_error_code("operation_failed")
        assert status_class == "ERROR"
        assert severity == "error"
        
        # Unknown error code
        status_class, severity = classify_error_code("unknown_error_code_xyz")
        assert status_class == "ERROR"
        assert severity == "error"

    def test_default_next_action_for_code(self):
        """Test default next action retrieval."""
        from modeling.feature_operations import default_next_action_for_code
        
        action = default_next_action_for_code("operation_failed")
        assert isinstance(action, str)
        assert len(action) > 0
        
        # Unknown code returns generic action
        action = default_next_action_for_code("unknown_code")
        assert isinstance(action, str)
        assert len(action) > 0

    def test_record_tnp_failure_basic(self):
        """Test TNP failure recording."""
        from modeling.feature_operations import record_tnp_failure
        
        feature = Mock()
        feature.id = "feat123"
        feature.name = "TestFeature"
        feature.__class__.__name__ = "MockFeature"
        
        result = record_tnp_failure(
            None,
            feature=feature,
            category="missing_ref",
            reference_kind="face",
            reason="Test reason",
        )
        
        assert result is not None
        assert result["category"] == "missing_ref"
        assert result["reference_kind"] == "face"
        assert result["reason"] == "Test reason"
        assert result["feature_id"] == "feat123"

    def test_record_tnp_failure_none_feature(self):
        """Test TNP failure recording with None feature."""
        from modeling.feature_operations import record_tnp_failure
        
        result = record_tnp_failure(
            None,
            feature=None,
            category="missing_ref",
            reference_kind="face",
            reason="Test reason",
        )
        
        assert result is None

    def test_record_tnp_failure_category_normalization(self):
        """Test TNP failure category normalization."""
        from modeling.feature_operations import record_tnp_failure
        
        feature = Mock()
        feature.id = "feat123"
        feature.name = "TestFeature"
        feature.__class__.__name__ = "MockFeature"
        
        # Invalid category should default to "missing_ref"
        result = record_tnp_failure(
            None,
            feature=feature,
            category="invalid_category",
            reference_kind="edge",
            reason="Test",
        )
        
        assert result["category"] == "missing_ref"

    def test_consume_tnp_failure_basic(self):
        """Test TNP failure consumption."""
        from modeling.feature_operations import consume_tnp_failure
        
        pending = {
            "category": "drift",
            "feature_id": "feat123",
            "reason": "Test",
        }
        
        consumed, updated = consume_tnp_failure(pending, feature=None)
        
        assert consumed is not None
        assert consumed["category"] == "drift"
        assert updated is None

    def test_consume_tnp_failure_feature_match(self):
        """Test TNP failure consumption with matching feature."""
        from modeling.feature_operations import consume_tnp_failure
        
        pending = {
            "category": "drift",
            "feature_id": "feat123",
            "reason": "Test",
        }
        
        feature = Mock()
        feature.id = "feat123"
        
        consumed, updated = consume_tnp_failure(pending, feature=feature)
        
        assert consumed is not None
        assert consumed["category"] == "drift"

    def test_consume_tnp_failure_feature_mismatch(self):
        """Test TNP failure consumption with non-matching feature."""
        from modeling.feature_operations import consume_tnp_failure
        
        pending = {
            "category": "drift",
            "feature_id": "feat123",
            "reason": "Test",
        }
        
        feature = Mock()
        feature.id = "different_id"
        
        consumed, updated = consume_tnp_failure(pending, feature=feature)
        
        assert consumed is None
        assert updated == pending

    def test_build_operation_error_details_basic(self):
        """Test building operation error details."""
        from modeling.feature_operations import build_operation_error_details
        
        details = build_operation_error_details(
            op_name="test_op",
            code="operation_failed",
            message="Test error message",
        )
        
        assert details["schema"] == "error_envelope_v1"
        assert details["code"] == "operation_failed"
        assert details["operation"] == "test_op"
        assert details["message"] == "Test error message"
        assert "status_class" in details
        assert "severity" in details
        assert "hint" in details
        assert "next_action" in details

    def test_build_operation_error_details_with_feature(self):
        """Test building operation error details with feature."""
        from modeling.feature_operations import build_operation_error_details
        
        feature = Mock()
        feature.id = "feat123"
        feature.name = "TestFeature"
        feature.__class__.__name__ = "MockFeature"
        
        details = build_operation_error_details(
            op_name="test_op",
            code="operation_failed",
            message="Test error",
            feature=feature,
        )
        
        assert "feature" in details
        assert details["feature"]["id"] == "feat123"
        assert details["feature"]["name"] == "TestFeature"

    def test_normalize_status_details_for_load_empty(self):
        """Test normalizing empty status details."""
        from modeling.feature_operations import normalize_status_details_for_load
        
        result = normalize_status_details_for_load(None)
        assert result == {}
        
        result = normalize_status_details_for_load("not a dict")
        assert result == {}

    def test_normalize_status_details_for_load_with_code(self):
        """Test normalizing status details with error code."""
        from modeling.feature_operations import normalize_status_details_for_load
        
        details = {"code": "operation_failed"}
        result = normalize_status_details_for_load(details)
        
        assert result["schema"] == "error_envelope_v1"
        assert result["status_class"] == "ERROR"
        assert result["severity"] == "error"
        assert "hint" in result
        assert "next_action" in result

    def test_safe_operation_success(self):
        """Test safe operation wrapper with successful operation."""
        from modeling.feature_operations import safe_operation
        
        def successful_op():
            return "success"
        
        result, status, error, error_details, updated_pending = safe_operation(
            "test_op",
            successful_op,
        )
        
        assert result == "success"
        assert status == "SUCCESS"
        assert error == ""

    def test_safe_operation_failure(self):
        """Test safe operation wrapper with failed operation."""
        from modeling.feature_operations import safe_operation
        
        def failing_op():
            raise ValueError("Test error")
        
        result, status, error, error_details, updated_pending = safe_operation(
            "test_op",
            failing_op,
        )
        
        assert result is None
        assert status == "ERROR"
        assert "Test error" in error

    def test_safe_operation_with_fallback(self):
        """Test safe operation wrapper with fallback."""
        from modeling.feature_operations import safe_operation
        
        def failing_op():
            raise ValueError("Primary error")
        
        def fallback_op():
            return "fallback_success"
        
        result, status, error, error_details, updated_pending = safe_operation(
            "test_op",
            failing_op,
            fallback_func=fallback_op,
        )
        
        assert result == "fallback_success"
        assert status == "WARNING"
        assert "Fallback" in error

    def test_safe_operation_none_result(self):
        """Test safe operation wrapper with None result."""
        from modeling.feature_operations import safe_operation
        
        def none_op():
            return None
        
        result, status, error, error_details, updated_pending = safe_operation(
            "test_op",
            none_op,
        )
        
        assert result is None
        assert status == "ERROR"


class TestBodyStateModule:
    """Tests for modeling/body_state.py"""

    def test_import_body_state_module(self):
        """Test that the body_state module can be imported."""
        from modeling import body_state
        assert body_state is not None

    def test_import_from_body_state(self):
        """Test importing specific functions from body_state."""
        from modeling.body_state import (
            serialize_shape_id,
            deserialize_shape_id,
            serialize_shape_ids,
            deserialize_shape_ids,
            serialize_feature,
            serialize_feature_base,
            compare_body_states,
            body_state_summary,
            serialize_brep,
            deserialize_brep,
        )
        assert callable(serialize_shape_id)
        assert callable(deserialize_shape_id)
        assert callable(serialize_shape_ids)
        assert callable(deserialize_shape_ids)
        assert callable(serialize_feature)
        assert callable(serialize_feature_base)
        assert callable(compare_body_states)
        assert callable(body_state_summary)
        assert callable(serialize_brep)
        assert callable(deserialize_brep)

    def test_serialize_shape_id_none(self):
        """Test serializing None ShapeID."""
        from modeling.body_state import serialize_shape_id
        
        result = serialize_shape_id(None)
        assert result is None

    def test_serialize_shape_id_with_uuid(self):
        """Test serializing ShapeID with uuid."""
        from modeling.body_state import serialize_shape_id
        from modeling.tnp_system import ShapeID, ShapeType
        
        sid = Mock(spec=ShapeID)
        sid.uuid = "test-uuid-123"
        sid.shape_type = ShapeType.FACE
        sid.feature_id = "feat123"
        sid.local_index = 5
        sid.geometry_hash = "hash123"
        sid.timestamp = 12345.0
        
        result = serialize_shape_id(sid)
        
        assert result["uuid"] == "test-uuid-123"
        assert result["shape_type"] == "FACE"
        assert result["feature_id"] == "feat123"
        assert result["local_index"] == 5
        assert result["geometry_hash"] == "hash123"
        assert result["timestamp"] == 12345.0

    def test_serialize_shape_ids_list(self):
        """Test serializing list of ShapeIDs."""
        from modeling.body_state import serialize_shape_ids
        from modeling.tnp_system import ShapeID, ShapeType
        
        sid1 = Mock(spec=ShapeID)
        sid1.uuid = "uuid1"
        sid1.shape_type = ShapeType.EDGE
        sid1.feature_id = "feat1"
        sid1.local_index = 0
        sid1.geometry_hash = "hash1"
        sid1.timestamp = 1.0
        
        sid2 = Mock(spec=ShapeID)
        sid2.uuid = "uuid2"
        sid2.shape_type = ShapeType.EDGE
        sid2.feature_id = "feat2"
        sid2.local_index = 1
        sid2.geometry_hash = "hash2"
        sid2.timestamp = 2.0
        
        result = serialize_shape_ids([sid1, sid2])
        
        assert len(result) == 2
        assert result[0]["uuid"] == "uuid1"
        assert result[1]["uuid"] == "uuid2"

    def test_serialize_feature_base(self):
        """Test serializing base feature properties."""
        from modeling.body_state import serialize_feature_base
        from modeling.features.base import Feature, FeatureType
        
        feature = Mock(spec=Feature)
        feature.type = FeatureType.EXTRUDE
        feature.name = "TestFeature"
        feature.id = "feat123"
        feature.visible = True
        feature.suppressed = False
        feature.status = "OK"
        feature.status_message = ""
        feature.status_details = {}
        
        result = serialize_feature_base(feature)
        
        assert result["type"] == "EXTRUDE"
        assert result["name"] == "TestFeature"
        assert result["id"] == "feat123"
        assert result["visible"] is True
        assert result["suppressed"] is False
        assert result["status"] == "OK"

    def test_compare_body_states_identical(self):
        """Test comparing identical body states."""
        from modeling.body_state import compare_body_states
        
        state = {
            "name": "Body1",
            "id": "body123",
            "features": [
                {"id": "feat1", "type": "EXTRUDE"},
            ],
            "source_body_id": None,
            "split_index": None,
            "split_side": None,
        }
        
        result = compare_body_states(state, state.copy())
        
        assert result["name_changed"] is False
        assert result["id_changed"] is False
        assert result["feature_count_changed"] is False
        assert result["features_added"] == []
        assert result["features_removed"] == []
        assert result["features_modified"] == []

    def test_compare_body_states_different(self):
        """Test comparing different body states."""
        from modeling.body_state import compare_body_states
        
        state1 = {
            "name": "Body1",
            "id": "body123",
            "features": [
                {"id": "feat1", "type": "EXTRUDE"},
            ],
            "source_body_id": None,
            "split_index": None,
            "split_side": None,
        }
        
        state2 = {
            "name": "Body2",
            "id": "body456",
            "features": [
                {"id": "feat2", "type": "FILLET"},
            ],
            "source_body_id": "original",
            "split_index": 0,
            "split_side": "above",
        }
        
        result = compare_body_states(state1, state2)
        
        assert result["name_changed"] is True
        assert result["id_changed"] is True
        assert result["feature_count_changed"] is False
        assert "feat1" in result["features_removed"]
        assert "feat2" in result["features_added"]

    def test_body_state_summary(self):
        """Test body state summary generation."""
        from modeling.body_state import body_state_summary
        
        state = {
            "name": "TestBody",
            "version": "9.1",
            "features": [
                {"id": "feat1", "feature_class": "ExtrudeFeature"},
                {"id": "feat2", "feature_class": "FilletFeature"},
                {"id": "feat3", "feature_class": "ExtrudeFeature"},
            ],
            "brep": "some brep data",
        }
        
        summary = body_state_summary(state)
        
        assert "TestBody" in summary
        assert "9.1" in summary
        assert "3 features" in summary
        assert "BREP: True" in summary


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing imports."""

    def test_import_from_init_feature_operations(self):
        """Test that feature_operations functions can be imported from __init__."""
        from modeling import (
            record_tnp_failure,
            consume_tnp_failure,
            classify_error_code,
            default_next_action_for_code,
            build_operation_error_details,
            normalize_status_details_for_load,
            safe_operation,
        )
        assert callable(record_tnp_failure)
        assert callable(consume_tnp_failure)
        assert callable(classify_error_code)
        assert callable(default_next_action_for_code)
        assert callable(build_operation_error_details)
        assert callable(normalize_status_details_for_load)
        assert callable(safe_operation)

    def test_import_from_init_body_state(self):
        """Test that body_state functions can be imported from __init__."""
        from modeling import (
            serialize_shape_id,
            deserialize_shape_id,
            serialize_shape_ids,
            deserialize_shape_ids,
            serialize_feature,
            serialize_feature_base,
            compare_body_states,
            body_state_summary,
            serialize_brep,
            deserialize_brep,
        )
        assert callable(serialize_shape_id)
        assert callable(deserialize_shape_id)
        assert callable(serialize_shape_ids)
        assert callable(deserialize_shape_ids)
        assert callable(serialize_feature)
        assert callable(serialize_feature_base)
        assert callable(compare_body_states)
        assert callable(body_state_summary)
        assert callable(serialize_brep)
        assert callable(deserialize_brep)

    def test_legacy_aliases_feature_operations(self):
        """Test that legacy aliases work for feature_operations."""
        from modeling import (
            _record_tnp_failure,
            _consume_tnp_failure,
            _classify_error_code,
            _default_next_action_for_code,
            _build_operation_error_details,
            _normalize_status_details_for_load,
            _safe_operation,
        )
        # These should be the same functions as the non-underscore versions
        from modeling import (
            record_tnp_failure,
            consume_tnp_failure,
            classify_error_code,
            default_next_action_for_code,
            build_operation_error_details,
            normalize_status_details_for_load,
            safe_operation,
        )
        assert _record_tnp_failure is record_tnp_failure
        assert _consume_tnp_failure is consume_tnp_failure
        assert _classify_error_code is classify_error_code
        assert _default_next_action_for_code is default_next_action_for_code
        assert _build_operation_error_details is build_operation_error_details
        assert _normalize_status_details_for_load is normalize_status_details_for_load
        assert _safe_operation is safe_operation

    def test_legacy_aliases_body_state(self):
        """Test that legacy aliases work for body_state."""
        from modeling import (
            _serialize_shape_id,
            _deserialize_shape_id,
            _serialize_shape_ids,
            _deserialize_shape_ids,
            _serialize_feature,
            _serialize_feature_base,
            _compare_body_states,
            _body_state_summary,
            _serialize_brep,
            _deserialize_brep,
        )
        # These should be the same functions as the non-underscore versions
        from modeling import (
            serialize_shape_id,
            deserialize_shape_id,
            serialize_shape_ids,
            deserialize_shape_ids,
            serialize_feature,
            serialize_feature_base,
            compare_body_states,
            body_state_summary,
            serialize_brep,
            deserialize_brep,
        )
        assert _serialize_shape_id is serialize_shape_id
        assert _deserialize_shape_id is deserialize_shape_id
        assert _serialize_shape_ids is serialize_shape_ids
        assert _deserialize_shape_ids is deserialize_shape_ids
        assert _serialize_feature is serialize_feature
        assert _serialize_feature_base is serialize_feature_base
        assert _compare_body_states is compare_body_states
        assert _body_state_summary is body_state_summary
        assert _serialize_brep is serialize_brep
        assert _deserialize_brep is deserialize_brep


class TestModuleIntegration:
    """Integration tests for the new modules."""

    def test_feature_operations_with_body_state(self):
        """Test feature_operations and body_state working together."""
        from modeling.feature_operations import build_operation_error_details
        from modeling.body_state import normalize_status_details_for_load
        
        # Build error details
        details = build_operation_error_details(
            op_name="test",
            code="operation_failed",
            message="Test error",
        )
        
        # Normalize them (simulating load from file)
        normalized = normalize_status_details_for_load(details)
        
        assert normalized["code"] == "operation_failed"
        assert "hint" in normalized

    def test_error_flow_simulation(self):
        """Simulate a typical error flow using the new modules."""
        from modeling.feature_operations import (
            record_tnp_failure,
            consume_tnp_failure,
            classify_error_code,
            build_operation_error_details,
        )
        
        # 1. Record a TNP failure
        feature = Mock()
        feature.id = "feat123"
        feature.name = "TestFeature"
        feature.__class__.__name__ = "MockFeature"
        
        pending = record_tnp_failure(
            None,
            feature=feature,
            category="missing_ref",
            reference_kind="face",
            reason="Face reference not found",
            expected=1,
            resolved=0,
        )
        
        assert pending is not None
        assert pending["category"] == "missing_ref"
        
        # 2. Consume the failure
        consumed, updated = consume_tnp_failure(pending, feature=feature)
        
        assert consumed is not None
        
        # 3. Build error details
        details = build_operation_error_details(
            op_name="fillet",
            code="tnp_ref_missing",
            message="Face reference not found",
            feature=feature,
            hint=consumed.get("next_action", ""),
        )
        
        assert details["code"] == "tnp_ref_missing"
        assert "feature" in details


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
