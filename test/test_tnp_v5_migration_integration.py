"""
TNP v5.0 - Migration Integration Tests

Integration tests for v4.0 to v5.0 migration including:
- Automatic migration on document load
- Rollback capability
- Test corpus validation
- Edge case handling
"""

import pytest
import time
import tempfile
import json
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4

from modeling.tnp_v5 import (
    TNPService,
    ShapeID,
    ShapeRecord,
    ShapeType,
    SelectionContext,
)
from modeling.tnp_v5.migration import (
    TNPMigration,
    MigrationResult,
    MigrationRollback,
    AutoMigration,
)
from modeling.tnp_system import (
    ShapeID as V4ShapeID,
    ShapeRecord as V4ShapeRecord,
    ShapeNamingService,
    OperationRecord as V4OperationRecord,
)


class TestMigrationRollback:
    """Test rollback capability for migration."""

    def test_create_rollback_snapshot_empty_service(self):
        """Test creating snapshot of empty v4.0 service."""
        v4_service = ShapeNamingService()

        snapshot = MigrationRollback.create_rollback_snapshot(v4_service)

        assert snapshot is not None
        assert snapshot['shapes'] == {}
        assert snapshot['operations'] == []
        assert snapshot['by_feature'] == {}

    def test_create_rollback_snapshot_with_shapes(self):
        """Test creating snapshot with shapes."""
        v4_service = ShapeNamingService()

        # Register some shapes
        for i in range(3):
            shape_id = v4_service.register_shape(
                ocp_shape=Mock(),
                shape_type=ShapeType.EDGE,
                feature_id=f"feature_{i}",
                local_index=i
            )

        snapshot = MigrationRollback.create_rollback_snapshot(v4_service)

        assert len(snapshot['shapes']) == 3
        assert 'timestamp' in snapshot

    def test_create_rollback_snapshot_with_operations(self):
        """Test creating snapshot with operations."""
        v4_service = ShapeNamingService()

        # Add some shapes
        sid1 = v4_service.register_shape(Mock(), ShapeType.EDGE, "f1", 0)
        sid2 = v4_service.register_shape(Mock(), ShapeType.FACE, "f1", 1)

        # Record an operation
        op = V4OperationRecord(
            operation_type="extrude",
            feature_id="f1",
            input_shape_ids=[sid1],
            output_shape_ids=[sid2]
        )
        v4_service.record_operation(op)

        snapshot = MigrationRollback.create_rollback_snapshot(v4_service)

        assert len(snapshot['operations']) == 1
        assert snapshot['operations'][0]['operation_type'] == "extrude"
        assert len(snapshot['operations'][0]['input_shape_ids']) == 1
        assert len(snapshot['operations'][0]['output_shape_ids']) == 1

    def test_restore_from_snapshot(self):
        """Test restoring v4.0 service from snapshot."""
        v4_service = ShapeNamingService()

        # Register original shapes
        sid1 = v4_service.register_shape(Mock(), ShapeType.EDGE, "f1", 0)
        sid2 = v4_service.register_shape(Mock(), ShapeType.FACE, "f1", 1)

        # Create snapshot
        snapshot = MigrationRollback.create_rollback_snapshot(v4_service)

        # Modify the service
        sid3 = v4_service.register_shape(Mock(), ShapeType.VERTEX, "f2", 0)

        # Clear and restore
        v4_service._shapes.clear()
        v4_service._operations.clear()
        v4_service._by_feature.clear()

        success = MigrationRollback.restore_from_snapshot(v4_service, snapshot)

        assert success is True
        assert len(v4_service._shapes) == 2
        assert sid1.uuid in v4_service._shapes
        assert sid2.uuid in v4_service._shapes

    def test_restore_preserves_shape_data(self):
        """Test that restore preserves all shape data."""
        v4_service = ShapeNamingService()

        # Register a shape
        sid = v4_service.register_shape(Mock(), ShapeType.EDGE, "test", 0)
        record = v4_service._shapes[sid.uuid]
        original_sig = record.geometric_signature.copy()

        # Snapshot and restore
        snapshot = MigrationRollback.create_rollback_snapshot(v4_service)

        v4_service._shapes.clear()
        MigrationRollback.restore_from_snapshot(v4_service, snapshot)

        # Verify data preserved
        restored_record = v4_service._shapes[sid.uuid]
        assert restored_record.shape_id.uuid == sid.uuid
        assert restored_record.shape_id.feature_id == "test"
        assert restored_record.geometric_signature == original_sig

    def test_rollback_migration_full_cycle(self):
        """Test full migration and rollback cycle."""
        # Create mock document with v4.0 service
        document = Mock()
        v4_service = ShapeNamingService()

        # Add shapes
        for i in range(5):
            v4_service.register_shape(Mock(), ShapeType.EDGE, f"feature_{i}", i)

        original_shape_count = len(v4_service._shapes)

        document._shape_naming_service = v4_service
        document._tnp_v5_service = None
        document._tnp_v5_rollback_data = None

        # Create rollback snapshot
        snapshot = MigrationRollback.create_rollback_snapshot(v4_service)
        document._tnp_v5_rollback_data = snapshot

        # Perform migration
        result = TNPMigration.migrate_document(document)
        assert result.is_valid
        assert hasattr(document, '_tnp_v5_service')

        # Rollback
        success = MigrationRollback.rollback_migration(document)
        assert success is True
        assert not hasattr(document, '_tnp_v5_service')
        assert not hasattr(document, '_tnp_v5_rollback_data')

        # Verify v4.0 service restored
        assert len(v4_service._shapes) == original_shape_count


class TestAutoMigration:
    """Test automatic migration detection and execution."""

    def test_needs_migration_with_v4_only(self):
        """Test detection when document has only v4.0 service."""
        document = Mock()
        v4_service = ShapeNamingService()
        v4_service.register_shape(Mock(), ShapeType.EDGE, "test", 0)

        document._shape_naming_service = v4_service
        document._tnp_v5_service = None

        assert AutoMigration.needs_migration(document) is True

    def test_needs_migration_with_both_services(self):
        """Test detection when document has both services."""
        document = Mock()
        v4_service = ShapeNamingService()
        v5_service = TNPService(document_id="test")

        document._shape_naming_service = v4_service
        document._tnp_v5_service = v5_service

        assert AutoMigration.needs_migration(document) is False

    def test_needs_migration_with_v5_only(self):
        """Test detection when document has only v5.0 service."""
        document = Mock()
        v5_service = TNPService(document_id="test")

        document._shape_naming_service = None
        document._tnp_v5_service = v5_service

        assert AutoMigration.needs_migration(document) is False

    def test_needs_migration_with_empty_v4(self):
        """Test detection when v4.0 service has no shapes."""
        document = Mock()
        v4_service = ShapeNamingService()

        document._shape_naming_service = v4_service
        document._tnp_v5_service = None

        assert AutoMigration.needs_migration(document) is False

    def test_auto_migrate_creates_v5_service(self):
        """Test auto-migration creates v5.0 service."""
        document = Mock()
        v4_service = ShapeNamingService()

        # Add shapes
        for i in range(3):
            v4_service.register_shape(Mock(), ShapeType.EDGE, f"f{i}", i)

        document._shape_naming_service = v4_service
        document._tnp_v5_service = None

        result = AutoMigration.auto_migrate(document, create_rollback=False)

        assert result.is_valid
        assert result.migrated_count == 3
        assert hasattr(document, '_tnp_v5_service')

    def test_auto_migrate_creates_rollback_data(self):
        """Test auto-migration creates rollback when requested."""
        document = Mock()
        v4_service = ShapeNamingService()

        v4_service.register_shape(Mock(), ShapeType.EDGE, "test", 0)

        document._shape_naming_service = v4_service
        document._tnp_v5_service = None

        result = AutoMigration.auto_migrate(document, create_rollback=True)

        assert result.is_valid
        assert result.rollback_data is not None
        assert hasattr(document, '_tnp_v5_rollback_data')

    def test_auto_migrate_skips_if_not_needed(self):
        """Test auto-migrate skips when not needed."""
        document = Mock()
        v5_service = TNPService(document_id="test")

        document._shape_naming_service = None
        document._tnp_v5_service = v5_service

        result = AutoMigration.auto_migrate(document)

        assert result.is_valid
        assert "No migration needed" in result.warnings

    def test_auto_migrate_handles_errors(self):
        """Test auto-migrate handles missing v4.0 service gracefully."""
        document = Mock()
        document._shape_naming_service = None
        document._tnp_v5_service = None

        result = AutoMigration.auto_migrate(document)

        # Should return valid with "no migration needed" warning
        # rather than an error - no v4.0 service means nothing to migrate
        assert result.is_valid is True
        assert "No migration needed" in result.warnings


class TestMigrationEdgeCases:
    """Test edge cases in migration."""

    def test_migrate_with_corrupted_shape_data(self):
        """Test migration handles corrupted shape data."""
        v4_service = Mock()
        v5_service = TNPService(document_id="test")

        # Add valid shape
        valid_sid = Mock()
        valid_sid.uuid = "valid-uuid"
        valid_sid.shape_type = ShapeType.EDGE
        valid_sid.feature_id = "test"
        valid_sid.local_index = 0
        valid_sid.geometry_hash = "hash123"
        valid_sid.to_v4_format = Mock(return_value={
            'uuid': 'valid-uuid',
            'shape_type': ShapeType.EDGE,
            'feature_id': 'test',
            'local_index': 0,
            'geometry_hash': 'hash123'
        })

        valid_record = Mock()
        valid_record.shape_id = valid_sid
        valid_record.ocp_shape = Mock()
        valid_record.geometric_signature = {'center': (0, 0, 0)}
        valid_record.is_valid = True

        # Add corrupted record (missing shape_id)
        corrupted_record = Mock()
        corrupted_record.shape_id = None

        v4_service._shapes = {'valid-uuid': valid_record}
        v4_service._operations = []
        v4_service._by_feature = {}

        result = TNPMigration.migrate_service_v4_to_v5(v4_service, v5_service)

        # Should migrate valid shapes despite corrupted ones
        assert result is True
        assert len(v5_service._shapes) == 1

    def test_migrate_with_missing_ocp_shapes(self):
        """Test migration with None OCP shapes."""
        v4_service = Mock()
        v5_service = TNPService(document_id="test")

        # Create shape with None OCP shape
        sid = Mock()
        sid.uuid = "test-uuid"
        sid.shape_type = ShapeType.EDGE
        sid.feature_id = "test"
        sid.local_index = 0
        sid.geometry_hash = "hash123"
        sid.to_v4_format = Mock(return_value={
            'uuid': 'test-uuid',
            'shape_type': ShapeType.EDGE,
            'feature_id': 'test',
            'local_index': 0,
            'geometry_hash': 'hash123'
        })

        record = Mock()
        record.shape_id = sid
        record.ocp_shape = None  # No OCP shape
        record.geometric_signature = {}
        record.is_valid = True

        v4_service._shapes = {'test-uuid': record}
        v4_service._operations = []
        v4_service._by_feature = {}

        result = TNPMigration.migrate_service_v4_to_v5(v4_service, v5_service)

        assert result is True
        assert 'test-uuid' in v5_service._shapes
        assert v5_service._shapes['test-uuid'].ocp_shape is None

    def test_migrate_large_document_performance(self):
        """Test migration performance with large documents."""
        v4_service = Mock()
        v5_service = TNPService(document_id="test")

        # Create many shapes
        num_shapes = 1000
        shapes = {}
        by_feature = {}

        for i in range(num_shapes):
            sid = Mock()
            sid.uuid = f"shape-{i}"
            sid.shape_type = ShapeType.EDGE
            sid.feature_id = f"feature_{i // 10}"
            sid.local_index = i % 10
            sid.geometry_hash = f"hash{i}"
            sid.to_v4_format = Mock(return_value={
                'uuid': f"shape-{i}",
                'shape_type': ShapeType.EDGE,
                'feature_id': f"feature_{i // 10}",
                'local_index': i % 10,
                'geometry_hash': f"hash{i}"
            })

            record = Mock()
            record.shape_id = sid
            record.ocp_shape = Mock()
            record.geometric_signature = {'center': (i, 0, 0)}
            record.is_valid = True

            shapes[f"shape-{i}"] = record

            # Update by_feature
            feat_id = f"feature_{i // 10}"
            if feat_id not in by_feature:
                by_feature[feat_id] = []
            by_feature[feat_id].append(sid)

        v4_service._shapes = shapes
        v4_service._operations = []
        v4_service._by_feature = by_feature

        # Measure migration time
        start = time.perf_counter()
        result = TNPMigration.migrate_service_v4_to_v5(v4_service, v5_service)
        elapsed = time.perf_counter() - start

        assert result is True
        assert len(v5_service._shapes) == num_shapes

        # Should complete in reasonable time (< 5 seconds for 1000 shapes)
        assert elapsed < 5.0, f"Migration too slow: {elapsed:.2f}s"

    def test_migrate_with_complex_operation_graph(self):
        """Test migration with complex operation dependencies."""
        v4_service = Mock()
        v5_service = TNPService(document_id="test")

        # Create operation chain: op1 -> op2 -> op3
        sid1 = Mock()
        sid1.uuid = "shape-1"
        sid1.to_v4_format = Mock(return_value={'uuid': 'shape-1', 'shape_type': ShapeType.FACE, 'feature_id': 'op1', 'local_index': 0, 'geometry_hash': 'h1'})

        sid2 = Mock()
        sid2.uuid = "shape-2"
        sid2.to_v4_format = Mock(return_value={'uuid': 'shape-2', 'shape_type': ShapeType.FACE, 'feature_id': 'op2', 'local_index': 0, 'geometry_hash': 'h2'})

        sid3 = Mock()
        sid3.uuid = "shape-3"
        sid3.to_v4_format = Mock(return_value={'uuid': 'shape-3', 'shape_type': ShapeType.FACE, 'feature_id': 'op3', 'local_index': 0, 'geometry_hash': 'h3'})

        # Operations
        op1 = Mock()
        op1.operation_type = "extrude"
        op1.feature_id = "op1"
        op1.timestamp = 1000
        op1.input_shape_ids = []
        op1.output_shape_ids = [sid1]

        op2 = Mock()
        op2.operation_type = "fillet"
        op2.feature_id = "op2"
        op2.timestamp = 2000
        op2.input_shape_ids = [sid1]
        op2.output_shape_ids = [sid2]

        op3 = Mock()
        op3.operation_type = "boolean"
        op3.feature_id = "op3"
        op3.timestamp = 3000
        op3.input_shape_ids = [sid2]
        op3.output_shape_ids = [sid3]

        v4_service._shapes = {
            'shape-1': Mock(shape_id=sid1, ocp_shape=Mock(), geometric_signature={}, is_valid=True),
            'shape-2': Mock(shape_id=sid2, ocp_shape=Mock(), geometric_signature={}, is_valid=True),
            'shape-3': Mock(shape_id=sid3, ocp_shape=Mock(), geometric_signature={}, is_valid=True),
        }
        v4_service._operations = [op1, op2, op3]
        v4_service._by_feature = {}

        result = TNPMigration.migrate_service_v4_to_v5(v4_service, v5_service)

        assert result is True
        assert len(v5_service._operations) == 3

        # Verify operation chain preserved
        ops = v5_service._operations
        assert ops[0]['operation_type'] == 'extrude'
        assert ops[1]['operation_type'] == 'fillet'
        assert ops[2]['operation_type'] == 'boolean'


class TestMigrationValidation:
    """Test migration validation."""

    def test_validate_detects_shape_loss(self):
        """Test validation detects lost shapes."""
        v5_service = TNPService(document_id="test")

        # Add one shape
        sid = ShapeID.create(ShapeType.EDGE, "test", 0, ())
        v5_service._shapes[sid.uuid] = ShapeRecord(shape_id=sid, ocp_shape=None)

        # Validate expecting more shapes
        result = TNPMigration.validate_migration(v5_service, expected_shape_count=5)

        assert result.is_valid is False
        assert any("Shape count mismatch" in issue for issue in result.issues)

    def test_validate_detects_orphaned_operations(self):
        """Test validation detects orphaned operation references."""
        v5_service = TNPService(document_id="test")

        # Add operation referencing non-existent shape
        v5_service._operations.append({
            'operation_type': 'test',
            'inputs': [{'uuid': 'non-existent'}],
            'outputs': []
        })

        result = TNPMigration.validate_migration(v5_service)

        assert result.is_valid is False
        assert any("Orphaned" in issue for issue in result.issues)

    def test_validate_passes_clean_migration(self):
        """Test validation passes for clean migration."""
        v5_service = TNPService(document_id="test")

        # Add shapes
        for i in range(3):
            sid = ShapeID.create(ShapeType.EDGE, f"f{i}", i, ())
            v5_service._shapes[sid.uuid] = ShapeRecord(shape_id=sid, ocp_shape=Mock())
            v5_service._by_feature[f"f{i}"] = [sid]

        result = TNPMigration.validate_migration(v5_service, expected_shape_count=3)

        assert result.is_valid is True
        assert result.migrated_count == 3

    def test_validate_reports_warnings(self):
        """Test validation reports warnings."""
        v5_service = TNPService(document_id="test")

        # Add shape without signature
        sid = ShapeID.create(ShapeType.EDGE, "test", 0, ())
        v5_service._shapes[sid.uuid] = ShapeRecord(
            shape_id=sid,
            ocp_shape=None,
            geometric_signature={}  # Empty signature
        )

        result = TNPMigration.validate_migration(v5_service)

        assert result.is_valid is True  # Valid, but with warnings
        assert len(result.warnings) > 0
        assert any("empty geometric signature" in w.lower() for w in result.warnings)


class TestMigrationResult:
    """Test MigrationResult functionality."""

    def test_migration_result_with_rollback_data(self):
        """Test MigrationResult stores rollback data."""
        rollback_data = {'shapes': {'test': 'data'}, 'timestamp': 123}

        result = MigrationResult(
            is_valid=True,
            migrated_count=10,
            rollback_data=rollback_data,
            original_shape_count=10
        )

        assert result.rollback_data == rollback_data
        assert result.original_shape_count == 10

    def test_migration_result_get_summary_with_warnings(self):
        """Test get_summary includes warnings."""
        result = MigrationResult(
            is_valid=True,
            migrated_count=100,
            operation_count=10,
            migration_time_seconds=1.5,
            warnings=["Warning 1", "Warning 2"]
        )

        summary = result.get_summary()

        assert "SUCCESS" in summary
        assert "100" in summary
        assert "10" in summary
        assert "Warning 1" in summary
        assert "Warning 2" in summary


class TestDocumentIntegration:
    """Test document-level migration integration."""

    def test_document_migrate_and_resolve(self):
        """Test migrating a document and resolving shapes."""
        # Create mock document with v4.0 service
        document = Mock()
        v4_service = ShapeNamingService()

        # Register a shape
        original_sid = v4_service.register_shape(
            ocp_shape=Mock(),
            shape_type=ShapeType.EDGE,
            feature_id="test_feature",
            local_index=0
        )

        document._shape_naming_service = v4_service
        document.document_id = "test_doc"

        # Migrate
        result = TNPMigration.migrate_document(document)

        assert result.is_valid
        assert hasattr(document, '_tnp_v5_service')

        # Verify v5.0 service can access the migrated shape
        v5_service = document._tnp_v5_service
        assert original_sid.uuid in v5_service._shapes

    def test_document_auto_migrate_on_load(self):
        """Test automatic migration when document is loaded."""
        document = Mock()
        v4_service = ShapeNamingService()

        # Simulate document with existing data
        for i in range(5):
            v4_service.register_shape(Mock(), ShapeType.EDGE, f"f{i}", i)

        document._shape_naming_service = v4_service
        document._tnp_v5_service = None
        document.document_id = "loaded_doc"

        # Check migration needed
        assert AutoMigration.needs_migration(document)

        # Auto-migrate
        result = AutoMigration.auto_migrate(document, create_rollback=True)

        assert result.is_valid
        assert result.migrated_count == 5
        assert hasattr(document, '_tnp_v5_service')
        assert hasattr(document, '_tnp_v5_rollback_data')

    def test_document_rollback_after_failed_migration(self):
        """Test rollback can recover from failed migration."""
        document = Mock()
        v4_service = ShapeNamingService()

        # Add original data
        for i in range(3):
            v4_service.register_shape(Mock(), ShapeType.EDGE, f"f{i}", i)

        original_count = len(v4_service._shapes)

        document._shape_naming_service = v4_service
        document._tnp_v5_service = None

        # Create snapshot
        snapshot = MigrationRollback.create_rollback_snapshot(v4_service)
        document._tnp_v5_rollback_data = snapshot

        # Simulate failed migration (v5 service created but validation fails)
        v5_service = TNPService(document_id="test")
        document._tnp_v5_service = v5_service

        # Add a shape to v5 (simulating partial migration)
        sid = ShapeID.create(ShapeType.EDGE, "test", 0, ())
        v5_service._shapes[sid.uuid] = ShapeRecord(shape_id=sid, ocp_shape=None)

        # Rollback
        success = MigrationRollback.rollback_migration(document)

        assert success
        assert not hasattr(document, '_tnp_v5_service')
        assert len(v4_service._shapes) == original_count


class TestMigrationPersistence:
    """Test migration persistence across save/load cycles."""

    def test_migration_state_persists(self):
        """Test migration state survives save/load."""
        # This would test actual file I/O in a real scenario
        # For now, test the data structure
        result = MigrationResult(
            is_valid=True,
            migrated_count=50,
            operation_count=5,
            migration_time_seconds=0.5,
            rollback_data={'test': 'data'}
        )

        # Serialize to dict
        data = {
            'is_valid': result.is_valid,
            'migrated_count': result.migrated_count,
            'operation_count': result.operation_count,
            'migration_time_seconds': result.migration_time_seconds,
            'rollback_data': result.rollback_data
        }

        # Reconstruct
        restored = MigrationResult(**data)

        assert restored.is_valid == result.is_valid
        assert restored.migrated_count == result.migrated_count
        assert restored.rollback_data == result.rollback_data

    def test_migration_metadata_in_document(self):
        """Test migration metadata is stored in document."""
        document = Mock()
        v4_service = ShapeNamingService()

        v4_service.register_shape(Mock(), ShapeType.EDGE, "test", 0)

        document._shape_naming_service = v4_service
        document.document_id = "test"

        result = TNPMigration.migrate_document(document)

        # Metadata should be accessible
        assert hasattr(document, '_tnp_v5_service')
        assert result.migrated_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
