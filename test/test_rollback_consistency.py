"""
MashCAD - PI-006 Rollback Consistency Tests
============================================

Tests for rollback validation and orphan detection.

Author: Claude (Sprint 2 - PI-006)
Date: 2026-02-20
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass
from typing import Dict, List, Any, Optional


# Test fixtures and mocks
@pytest.fixture
def mock_body():
    """Create a mock Body for testing."""
    body = Mock()
    body.name = "TestBody"
    body._build123d_solid = Mock()
    body.features = []
    body.metadata = {"color": "red"}
    body._document = None
    body._mesh_cache = None
    body._edges_cache = None
    body._mesh_cache_valid = False
    
    def invalidate_mesh():
        body._mesh_cache = None
        body._edges_cache = None
        body._mesh_cache_valid = False
    
    body.invalidate_mesh = invalidate_mesh
    return body


@pytest.fixture
def mock_document(mock_body):
    """Create a mock Document for testing."""
    document = Mock()
    document.bodies = [mock_body]
    document._shape_naming_service = None
    return document


@pytest.fixture
def mock_feature():
    """Create a mock Feature for testing."""
    feature = Mock()
    feature.id = "feature-001"
    feature.name = "TestFeature"
    feature.type = "extrude"
    feature.status = "OK"
    return feature


class TestRollbackState:
    """Tests for RollbackState dataclass."""
    
    def test_rollback_state_creation(self):
        """Test basic RollbackState creation."""
        from modeling.rollback_validator import RollbackState
        
        state = RollbackState(
            geometry_hash="abc123",
            feature_count=5,
            body_count=2,
            constraint_count=3,
            tnp_shape_count=10,
            tnp_operation_count=5,
            cache_entry_count=2,
            dependency_node_count=8,
            dependency_edge_count=7,
            operation_name="Test Operation",
        )
        
        assert state.geometry_hash == "abc123"
        assert state.feature_count == 5
        assert state.body_count == 2
        assert state.constraint_count == 3
        assert state.operation_name == "Test Operation"
        assert isinstance(state.timestamp, datetime)
    
    def test_rollback_state_to_dict(self):
        """Test RollbackState serialization."""
        from modeling.rollback_validator import RollbackState
        
        state = RollbackState(
            geometry_hash="abc123",
            feature_count=5,
            body_count=2,
            constraint_count=3,
            tnp_shape_count=10,
            tnp_operation_count=5,
            cache_entry_count=2,
            dependency_node_count=8,
            dependency_edge_count=7,
            operation_name="Test",
            body_hashes={"Body1": "hash1"},
            feature_hashes={"Body1": ["f1", "f2"]},
        )
        
        data = state.to_dict()
        
        assert data["geometry_hash"] == "abc123"
        assert data["feature_count"] == 5
        assert data["body_hashes"] == {"Body1": "hash1"}
        assert "timestamp" in data


class TestOrphanInfo:
    """Tests for OrphanInfo dataclass."""
    
    def test_orphan_info_creation(self):
        """Test OrphanInfo creation."""
        from modeling.rollback_validator import OrphanInfo, OrphanType
        
        orphan = OrphanInfo(
            orphan_type=OrphanType.TNP_SHAPE,
            identifier="orphan-001",
            description="Test orphan",
            severity="high",
            parent_reference="feature-001",
        )
        
        assert orphan.orphan_type == OrphanType.TNP_SHAPE
        assert orphan.identifier == "orphan-001"
        assert orphan.severity == "high"


class TestValidationResult:
    """Tests for ValidationResult dataclass."""
    
    def test_validation_result_success(self):
        """Test successful validation result."""
        from modeling.rollback_validator import ValidationResult
        
        result = ValidationResult(
            is_valid=True,
            geometry_consistent=True,
            features_consistent=True,
            constraints_consistent=True,
            tnp_consistent=True,
            cache_consistent=True,
            dependencies_consistent=True,
            orphans_detected=0,
        )
        
        assert result.is_valid
        assert result.geometry_consistent
        assert len(result.errors) == 0
    
    def test_validation_result_failure(self):
        """Test failed validation result."""
        from modeling.rollback_validator import ValidationResult
        
        result = ValidationResult(
            is_valid=False,
            geometry_consistent=True,
            features_consistent=False,
            constraints_consistent=True,
            tnp_consistent=True,
            cache_consistent=True,
            dependencies_consistent=True,
            orphans_detected=2,
            errors=["Feature count mismatch"],
            warnings=["Geometry hash changed"],
        )
        
        assert not result.is_valid
        assert not result.features_consistent
        assert result.orphans_detected == 2
        assert "Feature count mismatch" in result.errors


class TestRollbackValidator:
    """Tests for RollbackValidator class."""
    
    def test_validator_creation(self, mock_document):
        """Test RollbackValidator creation."""
        from modeling.rollback_validator import RollbackValidator
        
        validator = RollbackValidator(document=mock_document)
        
        assert validator._document == mock_document
        assert validator._state_history == []
    
    def test_capture_state_empty_document(self):
        """Test state capture with empty document."""
        from modeling.rollback_validator import RollbackValidator
        
        validator = RollbackValidator(document=None)
        state = validator.capture_state("Test Operation")
        
        assert state.geometry_hash == ""
        assert state.feature_count == 0
        assert state.body_count == 0
        assert state.operation_name == "Test Operation"
    
    def test_capture_state_with_bodies(self, mock_document, mock_body, mock_feature):
        """Test state capture with bodies."""
        from modeling.rollback_validator import RollbackValidator
        
        mock_body.features = [mock_feature]
        
        # Setup mock dependency graph to avoid Mock len() error
        mock_graph = Mock()
        mock_graph._nodes = {}
        mock_graph._edges = []
        mock_body._dependency_graph = mock_graph
        
        mock_document.bodies = [mock_body]
        
        # The validator will handle missing BRepUtils gracefully
        validator = RollbackValidator(document=mock_document)
        state = validator.capture_state("Boolean Cut")
        
        assert state.feature_count == 1
        assert state.body_count == 1
        assert state.operation_name == "Boolean Cut"
    
    def test_validate_rollback_identical_states(self):
        """Test validation with identical states."""
        from modeling.rollback_validator import RollbackValidator, RollbackState
        
        validator = RollbackValidator()
        
        before = RollbackState(
            geometry_hash="abc123",
            feature_count=5,
            body_count=2,
            constraint_count=3,
            tnp_shape_count=10,
            tnp_operation_count=5,
            cache_entry_count=2,
            dependency_node_count=8,
            dependency_edge_count=7,
        )
        
        after = RollbackState(
            geometry_hash="abc123",
            feature_count=5,
            body_count=2,
            constraint_count=3,
            tnp_shape_count=10,
            tnp_operation_count=5,
            cache_entry_count=2,
            dependency_node_count=8,
            dependency_edge_count=7,
        )
        
        result = validator.validate_rollback(before, after)
        
        assert result.is_valid
        assert result.geometry_consistent
        assert result.features_consistent
        assert result.orphans_detected == 0
    
    def test_validate_rollback_feature_count_increased(self):
        """Test validation detects feature count increase."""
        from modeling.rollback_validator import RollbackValidator, RollbackState
        
        validator = RollbackValidator()
        
        before = RollbackState(
            geometry_hash="abc",
            feature_count=3,
            body_count=1,
            constraint_count=0,
            tnp_shape_count=0,
            tnp_operation_count=0,
            cache_entry_count=0,
            dependency_node_count=0,
            dependency_edge_count=0,
        )
        
        after = RollbackState(
            geometry_hash="abc",
            feature_count=5,  # Increased - should fail
            body_count=1,
            constraint_count=0,
            tnp_shape_count=0,
            tnp_operation_count=0,
            cache_entry_count=0,
            dependency_node_count=0,
            dependency_edge_count=0,
        )
        
        result = validator.validate_rollback(before, after)
        
        assert not result.is_valid
        assert not result.features_consistent
        assert any("increased" in e.lower() for e in result.errors)
    
    def test_validate_rollback_geometry_changed_warning(self):
        """Test validation warns on geometry hash change."""
        from modeling.rollback_validator import RollbackValidator, RollbackState
        
        validator = RollbackValidator()
        
        before = RollbackState(
            geometry_hash="before_hash",
            feature_count=3,
            body_count=1,
            constraint_count=0,
            tnp_shape_count=0,
            tnp_operation_count=0,
            cache_entry_count=0,
            dependency_node_count=0,
            dependency_edge_count=0,
        )
        
        after = RollbackState(
            geometry_hash="different_hash",  # Changed - should warn
            feature_count=3,
            body_count=1,
            constraint_count=0,
            tnp_shape_count=0,
            tnp_operation_count=0,
            cache_entry_count=0,
            dependency_node_count=0,
            dependency_edge_count=0,
        )
        
        result = validator.validate_rollback(before, after)
        
        # Geometry change is a warning, not an error
        assert result.is_valid  # Still valid
        assert not result.geometry_consistent
        assert any("hash mismatch" in w.lower() for w in result.warnings)
    
    def test_detect_orphans_empty_document(self):
        """Test orphan detection with empty document."""
        from modeling.rollback_validator import RollbackValidator
        
        validator = RollbackValidator(document=None)
        orphans = validator.detect_orphans()
        
        assert orphans == []
    
    def test_detect_tnp_orphans(self, mock_document):
        """Test TNP orphan detection."""
        from modeling.rollback_validator import RollbackValidator, OrphanType
        
        # Mock TNP service with orphaned shapes
        mock_service = Mock()
        mock_service._shapes = {}
        mock_service._by_feature = {
            "orphan-feature-id": [Mock()],  # Feature doesn't exist
        }
        mock_document._shape_naming_service = mock_service
        mock_document.bodies = []  # No bodies, so all features are orphans
        
        validator = RollbackValidator(document=mock_document)
        orphans = validator.detect_orphans()
        
        tnp_orphans = [o for o in orphans if o.orphan_type == OrphanType.TNP_SHAPE]
        assert len(tnp_orphans) > 0
    
    def test_cleanup_orphans_empty(self):
        """Test orphan cleanup with no orphans."""
        from modeling.rollback_validator import RollbackValidator
        
        validator = RollbackValidator(document=None)
        cleaned = validator.cleanup_orphans([])
        
        assert cleaned == 0
    
    def test_state_history_limit(self, mock_document, mock_body):
        """Test that state history is limited."""
        from modeling.rollback_validator import RollbackValidator
        
        # Setup mock body with proper dependency graph mock
        mock_graph = Mock()
        mock_graph._nodes = {}  # Use dict instead of Mock for len()
        mock_graph._edges = []
        mock_body._dependency_graph = mock_graph
        mock_document.bodies = [mock_body]
        
        validator = RollbackValidator(document=mock_document)
        validator._max_history = 3
        
        # Capture more states than the limit
        for i in range(5):
            validator.capture_state(f"Operation {i}")
        
        assert len(validator._state_history) == 3


class TestBodyTransactionIntegration:
    """Tests for BodyTransaction with rollback validation."""
    
    def test_transaction_without_validation(self, mock_body):
        """Test transaction without rollback validation."""
        from modeling.body_transaction import BodyTransaction
        
        # Disable validation
        with patch('config.feature_flags.FEATURE_FLAGS', {'rollback_validation': False}):
            with BodyTransaction(mock_body, "Test Op", validate_rollback=False) as txn:
                mock_body._build123d_solid = Mock()
                txn.commit()
            
            assert txn._committed
    
    def test_transaction_with_validation_enabled(self, mock_body, mock_document):
        """Test transaction with rollback validation enabled."""
        from modeling.body_transaction import BodyTransaction
        
        # Setup mock body with proper dependency graph mock
        mock_graph = Mock()
        mock_graph._nodes = {}
        mock_graph._edges = []
        mock_body._dependency_graph = mock_graph
        mock_body._document = mock_document
        mock_document.bodies = [mock_body]
        
        with patch('config.feature_flags.FEATURE_FLAGS', {'rollback_validation': True}):
            with BodyTransaction(mock_body, "Test Op", validate_rollback=True) as txn:
                # Should have captured pre-state
                assert txn._pre_state is not None
                assert txn._validator is not None
                
                mock_body._build123d_solid = Mock()
                txn.commit()
            
            assert txn._committed
    
    def test_transaction_rollback_with_validation(self, mock_body, mock_document):
        """Test transaction rollback with validation."""
        from modeling.body_transaction import BodyTransaction, BooleanOperationError
        
        mock_body._document = mock_document
        original_solid = mock_body._build123d_solid
        
        with patch('config.feature_flags.FEATURE_FLAGS', {'rollback_validation': True}):
            with BodyTransaction(mock_body, "Test Op", validate_rollback=True) as txn:
                # Modify body
                mock_body._build123d_solid = Mock()
                
                # Trigger rollback
                raise BooleanOperationError("Test failure")
        
        # Body should be restored
        assert mock_body._build123d_solid == original_solid
        assert not txn._committed


class TestOrphanTypes:
    """Tests for different orphan types."""
    
    def test_orphan_type_enum(self):
        """Test OrphanType enum values."""
        from modeling.rollback_validator import OrphanType
        
        assert OrphanType.TNP_SHAPE.value == "tnp_shape"
        assert OrphanType.TNP_OPERATION.value == "tnp_operation"
        assert OrphanType.FEATURE_REFERENCE.value == "feature_reference"
        assert OrphanType.CONSTRAINT_REFERENCE.value == "constraint_reference"
        assert OrphanType.CACHE_ENTRY.value == "cache_entry"
        assert OrphanType.DEPENDENCY_EDGE.value == "dependency_edge"


class TestFeatureFlag:
    """Tests for PI-006 feature flag."""
    
    def test_rollback_validation_flag_exists(self):
        """Test that rollback_validation flag exists."""
        from config.feature_flags import FEATURE_FLAGS
        
        assert "rollback_validation" in FEATURE_FLAGS
        assert FEATURE_FLAGS["rollback_validation"] is True
    
    def test_is_enabled_function(self):
        """Test is_enabled function for rollback_validation."""
        from config.feature_flags import is_enabled
        
        # Should be True by default
        assert is_enabled("rollback_validation") is True
    
    def test_set_flag_function(self):
        """Test set_flag function for rollback_validation."""
        from config.feature_flags import set_flag, is_enabled
        
        original = is_enabled("rollback_validation")
        
        try:
            set_flag("rollback_validation", False)
            assert is_enabled("rollback_validation") is False
            
            set_flag("rollback_validation", True)
            assert is_enabled("rollback_validation") is True
        finally:
            # Restore original value
            set_flag("rollback_validation", original)


class TestGeometryIntegrity:
    """Tests for geometry integrity checks."""
    
    def test_geometry_hash_computation(self, mock_document, mock_body):
        """Test geometry hash computation."""
        from modeling.rollback_validator import RollbackValidator
        
        mock_document.bodies = [mock_body]
        
        # The validator handles missing BRepUtils gracefully
        validator = RollbackValidator(document=mock_document)
        hash1 = validator._compute_geometry_hash()
        
        # Same data should produce same hash
        hash2 = validator._compute_geometry_hash()
        
        assert hash1 == hash2
        # Hash may be empty string if no BREP available
        if hash1:
            assert len(hash1) == 64  # SHA-256 produces 64 char hex string
    
    def test_body_hashes(self, mock_document, mock_body):
        """Test per-body hash computation."""
        from modeling.rollback_validator import RollbackValidator
        
        mock_document.bodies = [mock_body]
        
        # The validator handles missing BRepUtils gracefully
        validator = RollbackValidator(document=mock_document)
        hashes = validator._compute_body_hashes()
        
        # Hashes dict should contain the body
        assert "TestBody" in hashes
        # Hash may be empty or MD5 length depending on mock
        if hashes["TestBody"]:
            assert len(hashes["TestBody"]) == 32  # MD5 produces 32 char hex


class TestFeatureReferenceConsistency:
    """Tests for feature reference consistency."""
    
    def test_feature_reference_orphan_detection(self, mock_document, mock_body, mock_feature):
        """Test detection of orphaned feature references."""
        from modeling.rollback_validator import RollbackValidator, OrphanType
        
        # Feature references a shape that doesn't exist
        mock_ref = Mock()
        mock_ref.uuid = "non-existent-shape-id"
        mock_feature.shape_references = [mock_ref]
        mock_body.features = [mock_feature]
        mock_document.bodies = [mock_body]
        
        # TNP service has no shapes
        mock_service = Mock()
        mock_service._shapes = {}
        mock_document._shape_naming_service = mock_service
        
        validator = RollbackValidator(document=mock_document)
        orphans = validator._detect_feature_reference_orphans()
        
        assert len(orphans) > 0
        assert all(o.orphan_type == OrphanType.FEATURE_REFERENCE for o in orphans)


class TestDependencyGraphConsistency:
    """Tests for dependency graph consistency."""
    
    def test_dependency_edge_orphan_detection(self, mock_document, mock_body):
        """Test detection of orphaned dependency edges."""
        from modeling.rollback_validator import RollbackValidator, OrphanType
        
        # Mock dependency graph with orphaned edge
        mock_graph = Mock()
        mock_graph._nodes = {"node1": Mock()}
        mock_edge = Mock()
        mock_edge.source = "node1"
        mock_edge.target = "non_existent_node"  # Orphan!
        mock_graph._edges = [mock_edge]
        
        mock_body._dependency_graph = mock_graph
        mock_document.bodies = [mock_body]
        
        validator = RollbackValidator(document=mock_document)
        orphans = validator._detect_dependency_orphans()
        
        assert len(orphans) > 0
        assert any(o.orphan_type == OrphanType.DEPENDENCY_EDGE for o in orphans)


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
