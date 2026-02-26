"""
TNP v5.0 - Migration Utilities

Utilities for migrating from TNP v4.0 to v5.0.
"""

from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from loguru import logger
import time
from uuid import uuid4

from .types import ShapeID, ShapeRecord, ShapeType
from .service import TNPService


class TNPMigration:
    """
    Utilities for migrating from v4.0 to v5.0.

    Allows smooth transition without data loss.
    """

    @staticmethod
    def migrate_shape_id_v4_to_v5(v4_shape_id_dict: Dict) -> ShapeID:
        """
        Migrate a v4.0 ShapeID dictionary to v5.0 ShapeID.

        Args:
            v4_shape_id_dict: Dictionary with v4.0 ShapeID data

        Returns:
            New v5.0 ShapeID

        Raises:
            KeyError: If required fields are missing
            TypeError: If data types are incorrect
        """
        required_fields = ['uuid', 'shape_type', 'feature_id', 'local_index', 'geometry_hash']
        for field in required_fields:
            if field not in v4_shape_id_dict:
                raise KeyError(f"Missing required field: {field}")

        return ShapeID.from_v4_format(v4_shape_id_dict)

    @staticmethod
    def migrate_service_v4_to_v5(v4_service: Any, v5_service: 'TNPService') -> bool:
        """
        Migrate a v4.0 ShapeNamingService to v5.0 TNPService.

        Converts all registered shapes and operations from v4 to v5.0 format.

        Args:
            v4_service: The v4.0 ShapeNamingService instance
            v5_service: The v5.0 TNPService instance to populate

        Returns:
            True if migration succeeded, False otherwise

        Raises:
            ValueError: If either service is invalid
        """
        try:
            if v4_service is None:
                logger.warning("[TNP Migration] v4 service is None")
                return False

            if v5_service is None:
                logger.warning("[TNP Migration] v5 service is None")
                return False

            # Migrate all shapes
            migrated_count = 0
            shape_map = {}  # Maps old UUID to new ShapeID

            # Access v4.0 internal structures
            v4_shapes = getattr(v4_service, '_shapes', {})
            v4_by_feature = getattr(v4_service, '_by_feature', {})

            for uuid, v4_record in v4_shapes.items():
                try:
                    # Convert ShapeID
                    v4_shape_id_dict = v4_record.shape_id.to_v4_format() if hasattr(v4_record.shape_id, 'to_v4_format') else {
                        'uuid': uuid,
                        'shape_type': v4_record.shape_id.shape_type,
                        'feature_id': v4_record.shape_id.feature_id,
                        'local_index': v4_record.shape_id.local_index,
                        'geometry_hash': v4_record.shape_id.geometry_hash,
                    }

                    v5_shape_id = ShapeID.from_v4_format(v4_shape_id_dict)

                    # Create v5.0 record
                    v5_record = ShapeRecord(
                        shape_id=v5_shape_id,
                        ocp_shape=v4_record.ocp_shape,
                        geometric_signature=v4_record.geometric_signature.copy(),
                        is_valid=v4_record.is_valid,
                        selection_context=None,  # No context in v4.0
                        adjacency={},  # TODO: Migrate adjacency if available
                        validation_history=[],
                        resolution_history=[]
                    )

                    # Store in v5 service
                    v5_service._shapes[v5_shape_id.uuid] = v5_record

                    # Update feature bucket
                    feature_id = v5_shape_id.feature_id
                    if feature_id not in v5_service._by_feature:
                        v5_service._by_feature[feature_id] = []
                    v5_service._by_feature[feature_id].append(v5_shape_id)

                    # Map for operation migration
                    shape_map[uuid] = v5_shape_id.uuid

                    migrated_count += 1

                except Exception as e:
                    logger.warning(f"[TNP Migration] Failed to migrate shape {uuid}: {e}")

            # Migrate operations
            v4_operations = getattr(v4_service, '_operations', [])
            for op in v4_operations:
                try:
                    # Convert operation
                    op_data = {
                        'operation_type': getattr(op, 'operation_type', ''),
                        'feature_id': getattr(op, 'feature_id', ''),
                        'timestamp': getattr(op, 'timestamp', 0)
                    }

                    # Convert inputs/outputs
                    inputs = []
                    for inp in getattr(op, 'input_shape_ids', []):
                        if hasattr(inp, 'to_v4_format'):
                            inp_dict = inp.to_v4_format()
                        else:
                            inp_dict = {'uuid': str(inp)}
                        inputs.append(inp_dict)

                    outputs = []
                    for out in getattr(op, 'output_shape_ids', []):
                        if hasattr(out, 'to_v4_format'):
                            out_dict = out.to_v4_format()
                        else:
                            out_dict = {'uuid': str(out)}
                        outputs.append(out_dict)

                    op_data['inputs'] = inputs
                    op_data['outputs'] = outputs

                    # Store in v5 service (placeholder)
                    v5_service._operations.append(op_data)

                except Exception as e:
                    logger.warning(f"[TNP Migration] Failed to migrate operation: {e}")

            logger.info(f"[TNP Migration] Migrated {migrated_count} shapes, "
                       f"{len(v4_operations)} operations")

            return True

        except Exception as e:
            logger.error(f"[TNP Migration] Migration failed: {e}")
            return False

    @staticmethod
    def validate_migration(v5_service: TNPService, expected_shape_count: int = None) -> 'MigrationResult':
        """
        Validate that migration was successful.

        Checks:
        - All shapes migrated
        - No data loss
        - Records are consistent
        - No orphaned references

        Args:
            v5_service: The v5.0 TNPService to validate
            expected_shape_count: Optional expected number of shapes

        Returns:
            MigrationResult with validation status
        """
        issues = []
        warnings = []
        migrated_count = 0
        operation_count = 0

        try:
            # Count shapes
            migrated_count = len(v5_service._shapes)
            operation_count = len(v5_service._operations)

            # Check expected count
            if expected_shape_count is not None and migrated_count != expected_shape_count:
                issues.append(
                    f"Shape count mismatch: expected {expected_shape_count}, "
                    f"got {migrated_count}"
                )

            # Check for orphaned references (shapes referenced in operations but not in _shapes)
            shape_uuids = set(v5_service._shapes.keys())

            for op in v5_service._operations:
                if isinstance(op, dict):
                    # Check inputs
                    for inp in op.get('inputs', []):
                        if isinstance(inp, dict):
                            inp_uuid = inp.get('uuid')
                            if inp_uuid and inp_uuid not in shape_uuids:
                                issues.append(f"Orphaned input reference: {inp_uuid}")

                    # Check outputs
                    for out in op.get('outputs', []):
                        if isinstance(out, dict):
                            out_uuid = out.get('uuid')
                            if out_uuid and out_uuid not in shape_uuids:
                                issues.append(f"Orphaned output reference: {out_uuid}")

            # Check feature buckets consistency
            for feature_id, shape_ids in v5_service._by_feature.items():
                for sid in shape_ids:
                    if sid.uuid not in shape_uuids:
                        issues.append(
                            f"Feature bucket {feature_id} references missing shape: {sid.uuid}"
                        )

            # Check all ShapeRecords have required fields
            for uuid, record in v5_service._shapes.items():
                if record.shape_id is None:
                    issues.append(f"Shape {uuid} has None shape_id")
                if record.shape_id.uuid != uuid:
                    issues.append(
                        f"Shape {uuid} has mismatched shape_id.uuid: {record.shape_id.uuid}"
                    )

            # Check geometric signatures (warnings only)
            empty_sigs = sum(1 for r in v5_service._shapes.values() if not r.geometric_signature)
            if empty_sigs > 0:
                warnings.append(
                    f"{empty_sigs} shapes have empty geometric signatures "
                )

            logger.info(
                f"[TNP Migration] Validation complete: "
                f"{migrated_count} shapes, {operation_count} operations, "
                f"{len(issues)} issues"
            )

        except Exception as e:
            issues.append(f"Validation error: {e}")
            logger.error(f"[TNP Migration] Validation failed: {e}")

        return MigrationResult(
            is_valid=len(issues) == 0,
            issues=issues,
            migrated_count=migrated_count,
            operation_count=operation_count,
            warnings=warnings
        )

    @staticmethod
    def rebuild_spatial_index(v5_service: TNPService) -> bool:
        """
        Rebuild the spatial index for a v5.0 service.

        This is useful after migration to enable fast geometric queries.

        Args:
            v5_service: The v5.0 TNPService to rebuild index for

        Returns:
            True if rebuild succeeded, False otherwise
        """
        try:
            from .spatial import Bounds, compute_bounds_from_signature

            # Clear existing spatial index
            v5_service._spatial_index._bounds.clear()
            v5_service._spatial_index._shapes.clear()
            v5_service._spatial_index._count = 0

            inserted = 0

            for uuid, record in v5_service._shapes.items():
                if record.ocp_shape is None:
                    continue

                # Get geometric signature for bounding box
                sig = record.geometric_signature
                if not sig:
                    continue

                # Compute bounds from signature
                bounds = compute_bounds_from_signature(sig)
                if bounds is None:
                    continue

                # Insert using SpatialIndex.insert() API
                v5_service._spatial_index.insert(
                    shape_id=uuid,
                    bounds=bounds,
                    shape_data={
                        'shape_type': record.shape_id.shape_type.name,
                        'feature_id': record.shape_id.feature_id,
                        'local_index': record.shape_id.local_index
                    }
                )
                inserted += 1

            logger.info(f"[TNP Migration] Rebuilt spatial index with {inserted} shapes")
            return True

        except Exception as e:
            logger.error(f"[TNP Migration] Failed to rebuild spatial index: {e}")
            return False

    @staticmethod
    def migrate_document(document: Any, create_v5_service=True) -> 'MigrationResult':
        """
        Migrate an entire document from v4.0 to v5.0.

        This is a high-level convenience method that:
        1. Finds the v4.0 ShapeNamingService in the document
        2. Creates a new v5.0 TNPService
        3. Migrates all shapes and operations
        4. Validates the migration
        5. Optionally replaces the v4.0 service with v5.0

        Args:
            document: The document object (must have _shape_naming_service attribute)
            create_v5_service: If True, creates new v5.0 service

        Returns:
            MigrationResult with status and details
        """
        issues = []

        try:
            # Get v4.0 service
            v4_service = getattr(document, '_shape_naming_service', None)
            if v4_service is None:
                issues.append("Document has no _shape_naming_service attribute")
                return MigrationResult(is_valid=False, issues=issues)

            # Count expected shapes
            expected_count = len(getattr(v4_service, '_shapes', {}))

            # Create v5.0 service
            if create_v5_service:
                document_id = getattr(document, 'document_id', 'migrated_doc')
                v5_service = TNPService(document_id=document_id)
            else:
                v5_service = getattr(document, '_tnp_v5_service', None)
                if v5_service is None:
                    issues.append("v5.0 service not found in document")
                    return MigrationResult(is_valid=False, issues=issues)

            # Perform migration
            start_time = time.time()
            success = TNPMigration.migrate_service_v4_to_v5(v4_service, v5_service)
            duration = time.time() - start_time

            if not success:
                issues.append("Migration failed during service_v4_to_v5")
                return MigrationResult(is_valid=False, issues=issues)

            # Rebuild spatial index
            TNPMigration.rebuild_spatial_index(v5_service)

            # Validate
            result = TNPMigration.validate_migration(v5_service, expected_count)

            # Store v5.0 service in document
            if create_v5_service:
                document._tnp_v5_service = v5_service

            # Add timing info
            result.migration_time_seconds = duration

            logger.info(
                f"[TNP Migration] Document migration complete in {duration:.2f}s: "
                f"{result.migrated_count} shapes"
            )

            return result

        except Exception as e:
            issues.append(f"Document migration failed: {e}")
            logger.error(f"[TNP Migration] Document migration error: {e}")
            return MigrationResult(is_valid=False, issues=issues)


@dataclass
class MigrationResult:
    """Result of a v4.0 to v5.0 migration."""
    is_valid: bool
    issues: List[str] = field(default_factory=list)
    migrated_count: int = 0
    operation_count: int = 0
    migration_time_seconds: float = 0.0
    warnings: List[str] = field(default_factory=list)
    rollback_data: Optional[Dict[str, Any]] = None  # For rollback capability
    original_shape_count: int = 0

    def get_summary(self) -> str:
        """Get a human-readable summary of the migration result."""
        if self.is_valid:
            status = "SUCCESS"
        else:
            status = "FAILED"

        lines = [
            f"TNP v4.0 → v5.0 Migration: {status}",
            f"  Shapes migrated: {self.migrated_count}",
            f"  Operations migrated: {self.operation_count}",
            f"  Time: {self.migration_time_seconds:.2f}s"
        ]

        if self.issues:
            lines.append(f"  Issues: {len(self.issues)}")
            for issue in self.issues[:5]:  # Show first 5
                lines.append(f"    - {issue}")
            if len(self.issues) > 5:
                lines.append(f"    ... and {len(self.issues) - 5} more")

        if self.warnings:
            lines.append(f"  Warnings: {len(self.warnings)}")
            for warning in self.warnings[:3]:
                lines.append(f"    - {warning}")

        return "\n".join(lines)


class MigrationRollback:
    """
    Rollback capability for v4.0 to v5.0 migration.

    Allows reverting a migration if issues are detected.
    """

    @staticmethod
    def create_rollback_snapshot(v4_service: Any) -> Dict[str, Any]:
        """
        Create a snapshot of v4.0 service for potential rollback.

        Args:
            v4_service: The v4.0 ShapeNamingService to snapshot

        Returns:
            Dictionary containing all data needed for rollback
        """
        import copy

        snapshot = {
            'shapes': {},
            'operations': [],
            'by_feature': {},
            'spatial_index': {},
            'timestamp': time.time()
        }

        try:
            # Snapshot shapes
            v4_shapes = getattr(v4_service, '_shapes', {})
            for uuid, record in v4_shapes.items():
                snapshot['shapes'][uuid] = {
                    'shape_id_data': {
                        'uuid': record.shape_id.uuid,
                        'shape_type': record.shape_id.shape_type,
                        'feature_id': record.shape_id.feature_id,
                        'local_index': record.shape_id.local_index,
                        'geometry_hash': record.shape_id.geometry_hash,
                        'timestamp': getattr(record.shape_id, 'timestamp', 0)
                    },
                    'ocp_shape': record.ocp_shape,  # Reference, not deep copy
                    'geometric_signature': record.geometric_signature.copy(),
                    'is_valid': record.is_valid
                }

            # Snapshot operations
            v4_operations = getattr(v4_service, '_operations', [])
            for op in v4_operations:
                snapshot['operations'].append({
                    'operation_id': getattr(op, 'operation_id', str(uuid4())),
                    'operation_type': op.operation_type,
                    'feature_id': op.feature_id,
                    'input_shape_ids': [
                        {
                            'uuid': sid.uuid,
                            'shape_type': sid.shape_type,
                            'feature_id': sid.feature_id,
                            'local_index': sid.local_index,
                            'geometry_hash': sid.geometry_hash
                        }
                        for sid in op.input_shape_ids
                    ],
                    'output_shape_ids': [
                        {
                            'uuid': sid.uuid,
                            'shape_type': sid.shape_type,
                            'feature_id': sid.feature_id,
                            'local_index': sid.local_index,
                            'geometry_hash': sid.geometry_hash
                        }
                        for sid in op.output_shape_ids
                    ],
                    'timestamp': op.timestamp
                })

            # Snapshot by_feature
            v4_by_feature = getattr(v4_service, '_by_feature', {})
            for feature_id, shape_ids in v4_by_feature.items():
                snapshot['by_feature'][feature_id] = [
                    {
                        'uuid': sid.uuid,
                        'shape_type': sid.shape_type,
                        'feature_id': sid.feature_id,
                        'local_index': sid.local_index,
                        'geometry_hash': sid.geometry_hash
                    }
                    for sid in shape_ids
                ]

            # Snapshot spatial index
            v4_spatial = getattr(v4_service, '_spatial_index', {})
            for shape_type, entries in v4_spatial.items():
                snapshot['spatial_index'][str(shape_type)] = [
                    (pos.tolist() if hasattr(pos, 'tolist') else pos,
                     {
                         'uuid': sid.uuid,
                         'shape_type': sid.shape_type,
                         'feature_id': sid.feature_id,
                         'local_index': sid.local_index,
                         'geometry_hash': sid.geometry_hash
                     })
                    for pos, sid in entries
                ]

            logger.info(f"[TNP Migration] Created rollback snapshot: "
                       f"{len(snapshot['shapes'])} shapes, {len(snapshot['operations'])} ops")

        except Exception as e:
            logger.error(f"[TNP Migration] Failed to create rollback snapshot: {e}")
            snapshot['_error'] = str(e)

        return snapshot

    @staticmethod
    def restore_from_snapshot(v4_service: Any, snapshot: Dict[str, Any]) -> bool:
        """
        Restore v4.0 service from a rollback snapshot.

        Args:
            v4_service: The v4.0 ShapeNamingService to restore
            snapshot: The snapshot data from create_rollback_snapshot

        Returns:
            True if restore succeeded, False otherwise
        """
        try:
            if '_error' in snapshot:
                logger.error(f"[TNP Migration] Snapshot has error: {snapshot['_error']}")
                return False

            # Import v4.0 types
            from modeling.tnp_system import ShapeID as V4ShapeID, ShapeRecord as V4ShapeRecord
            from modeling.tnp_system import OperationRecord as V4OperationRecord, ShapeType as V4ShapeType

            # Clear existing data
            v4_service._shapes.clear()
            v4_service._operations.clear()
            v4_service._by_feature.clear()
            for shape_type in v4_service._spatial_index:
                v4_service._spatial_index[shape_type].clear()

            # Restore shapes
            for uuid, shape_data in snapshot['shapes'].items():
                sid_data = shape_data['shape_id_data']
                v4_shape_id = V4ShapeID(
                    uuid=sid_data['uuid'],
                    shape_type=sid_data['shape_type'],
                    feature_id=sid_data['feature_id'],
                    local_index=sid_data['local_index'],
                    geometry_hash=sid_data['geometry_hash'],
                    timestamp=sid_data.get('timestamp', 0)
                )

                v4_record = V4ShapeRecord(
                    shape_id=v4_shape_id,
                    ocp_shape=shape_data['ocp_shape']
                )
                v4_record.geometric_signature = shape_data['geometric_signature']
                v4_record.is_valid = shape_data['is_valid']

                v4_service._shapes[uuid] = v4_record

            # Restore operations
            for op_data in snapshot['operations']:
                input_ids = [
                    V4ShapeID(
                        uuid=d['uuid'],
                        shape_type=d['shape_type'],
                        feature_id=d['feature_id'],
                        local_index=d['local_index'],
                        geometry_hash=d['geometry_hash']
                    )
                    for d in op_data['input_shape_ids']
                ]
                output_ids = [
                    V4ShapeID(
                        uuid=d['uuid'],
                        shape_type=d['shape_type'],
                        feature_id=d['feature_id'],
                        local_index=d['local_index'],
                        geometry_hash=d['geometry_hash']
                    )
                    for d in op_data['output_shape_ids']
                ]

                v4_op = V4OperationRecord(
                    operation_type=op_data['operation_type'],
                    feature_id=op_data['feature_id'],
                    input_shape_ids=input_ids,
                    output_shape_ids=output_ids,
                    operation_id=op_data.get('operation_id')
                )
                v4_op.timestamp = op_data['timestamp']

                v4_service._operations.append(v4_op)

            # Restore by_feature
            import numpy as np
            for feature_id, shape_ids_data in snapshot['by_feature'].items():
                v4_service._by_feature[feature_id] = []
                for sid_data in shape_ids_data:
                    v4_shape_id = V4ShapeID(
                        uuid=sid_data['uuid'],
                        shape_type=sid_data['shape_type'],
                        feature_id=sid_data['feature_id'],
                        local_index=sid_data['local_index'],
                        geometry_hash=sid_data['geometry_hash']
                    )
                    v4_service._by_feature[feature_id].append(v4_shape_id)

            # Restore spatial index
            for shape_type_str, entries in snapshot['spatial_index'].items():
                # Parse shape type from string
                for st in V4ShapeType:
                    if str(st) == shape_type_str:
                        shape_type = st
                        break
                else:
                    continue

                for pos, sid_data in entries:
                    pos_array = np.array(pos) if isinstance(pos, list) else pos
                    v4_shape_id = V4ShapeID(
                        uuid=sid_data['uuid'],
                        shape_type=sid_data['shape_type'],
                        feature_id=sid_data['feature_id'],
                        local_index=sid_data['local_index'],
                        geometry_hash=sid_data['geometry_hash']
                    )
                    v4_service._spatial_index[shape_type].append((pos_array, v4_shape_id))

            logger.info(f"[TNP Migration] Restored from snapshot: "
                       f"{len(v4_service._shapes)} shapes, {len(v4_service._operations)} ops")

            return True

        except Exception as e:
            logger.error(f"[TNP Migration] Failed to restore from snapshot: {e}")
            return False

    @staticmethod
    def rollback_migration(document: Any) -> bool:
        """
        Rollback a migration by restoring v4.0 service and removing v5.0 service.

        Args:
            document: The document with migration to rollback

        Returns:
            True if rollback succeeded, False otherwise
        """
        try:
            # Check if rollback data exists
            rollback_data = getattr(document, '_tnp_v5_rollback_data', None)
            if rollback_data is None:
                logger.warning("[TNP Migration] No rollback data found")
                return False

            # Get v4.0 service
            v4_service = getattr(document, '_shape_naming_service', None)
            if v4_service is None:
                logger.error("[TNP Migration] v4.0 service not found for rollback")
                return False

            # Restore v4.0 service
            success = MigrationRollback.restore_from_snapshot(v4_service, rollback_data)
            if not success:
                return False

            # Remove v5.0 service
            if hasattr(document, '_tnp_v5_service'):
                delattr(document, '_tnp_v5_service')

            # Clear rollback data
            if hasattr(document, '_tnp_v5_rollback_data'):
                delattr(document, '_tnp_v5_rollback_data')

            logger.info("[TNP Migration] Rollback complete")
            return True

        except Exception as e:
            logger.error(f"[TNP Migration] Rollback failed: {e}")
            return False


class AutoMigration:
    """
    Automatic migration detection and execution for documents.

    Detects when a document uses v4.0 TNP and automatically migrates to v5.0.
    """

    @staticmethod
    def needs_migration(document: Any) -> bool:
        """
        Check if a document needs v4.0 to v5.0 migration.

        Args:
            document: The document to check

        Returns:
            True if migration is needed, False otherwise
        """
        # Has v4.0 service
        has_v4 = hasattr(document, '_shape_naming_service') and document._shape_naming_service is not None

        # Does not have v5.0 service
        has_v5 = hasattr(document, '_tnp_v5_service') and document._tnp_v5_service is not None

        # Has v4.0 shapes to migrate
        has_shapes = False
        if has_v4:
            v4_shapes = getattr(document._shape_naming_service, '_shapes', {})
            has_shapes = len(v4_shapes) > 0

        return has_v4 and not has_v5 and has_shapes

    @staticmethod
    def auto_migrate(document: Any, create_rollback: bool = True) -> MigrationResult:
        """
        Automatically migrate a document from v4.0 to v5.0.

        Args:
            document: The document to migrate
            create_rollback: If True, creates rollback snapshot

        Returns:
            MigrationResult with status
        """
        if not AutoMigration.needs_migration(document):
            return MigrationResult(
                is_valid=True,
                issues=[],
                migrated_count=0,
                operation_count=0,
                warnings=["No migration needed"]
            )

        try:
            # Create rollback snapshot if requested
            rollback_data = None
            if create_rollback:
                rollback_data = MigrationRollback.create_rollback_snapshot(
                    document._shape_naming_service
                )
                document._tnp_v5_rollback_data = rollback_data

            # Perform migration
            result = TNPMigration.migrate_document(document, create_v5_service=True)

            # Store rollback data in result
            if rollback_data:
                result.rollback_data = rollback_data

            # Log result
            if result.is_valid:
                logger.info(f"[TNP AutoMigration] Successfully migrated document: "
                           f"{result.migrated_count} shapes")
            else:
                logger.warning(f"[TNP AutoMigration] Migration failed: {result.issues}")

            return result

        except Exception as e:
            logger.error(f"[TNP AutoMigration] Auto-migration failed: {e}")
            return MigrationResult(
                is_valid=False,
                issues=[f"Auto-migration failed: {e}"],
                migrated_count=0,
                operation_count=0
            )
