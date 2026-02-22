"""
MashCAD - Rollback Consistency Validator
========================================

PI-006: Ensures rollback operations restore consistent geometric and parametric state
without leaving orphaned or inconsistent data.

Author: Claude (Sprint 2 - PI-006)
Date: 2026-02-20
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from enum import Enum
import hashlib
import json
from loguru import logger


class OrphanType(Enum):
    """Types of orphaned data that can be detected."""
    TNP_SHAPE = "tnp_shape"  # Orphaned TNP shape record
    TNP_OPERATION = "tnp_operation"  # Orphaned TNP operation record
    FEATURE_REFERENCE = "feature_reference"  # Feature references non-existent shape
    CONSTRAINT_REFERENCE = "constraint_reference"  # Constraint references missing geometry
    CACHE_ENTRY = "cache_entry"  # Orphaned cache entry
    DEPENDENCY_EDGE = "dependency_edge"  # Dependency graph edge points to nothing


@dataclass
class OrphanInfo:
    """Information about detected orphaned data."""
    orphan_type: OrphanType
    identifier: str
    description: str
    severity: str  # "low", "medium", "high", "critical"
    parent_reference: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RollbackState:
    """
    Immutable snapshot of system state for rollback validation.
    
    Captures all critical state that must be consistent after rollback.
    """
    # Geometry state
    geometry_hash: str  # Hash of all body geometries
    feature_count: int  # Total number of features across all bodies
    body_count: int  # Number of bodies
    
    # Constraint state (sketch mode)
    constraint_count: int  # Total constraints in active sketch
    
    # TNP state
    tnp_shape_count: int  # Number of TNP shape records
    tnp_operation_count: int  # Number of TNP operation records
    
    # Cache state
    cache_entry_count: int  # Number of cached entries
    
    # Dependency graph state
    dependency_node_count: int  # Number of dependency nodes
    dependency_edge_count: int  # Number of dependency edges
    
    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    operation_name: str = ""
    body_name: Optional[str] = None
    
    # Detailed hashes for granular validation
    body_hashes: Dict[str, str] = field(default_factory=dict)  # body_name -> geometry hash
    feature_hashes: Dict[str, List[str]] = field(default_factory=dict)  # body_name -> [feature hashes]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize state to dictionary for logging/debugging."""
        return {
            "geometry_hash": self.geometry_hash,
            "feature_count": self.feature_count,
            "body_count": self.body_count,
            "constraint_count": self.constraint_count,
            "tnp_shape_count": self.tnp_shape_count,
            "tnp_operation_count": self.tnp_operation_count,
            "cache_entry_count": self.cache_entry_count,
            "dependency_node_count": self.dependency_node_count,
            "dependency_edge_count": self.dependency_edge_count,
            "timestamp": self.timestamp.isoformat(),
            "operation_name": self.operation_name,
            "body_name": self.body_name,
            "body_hashes": self.body_hashes,
            "feature_hashes": self.feature_hashes,
        }


@dataclass
class ValidationResult:
    """Result of rollback validation."""
    is_valid: bool
    geometry_consistent: bool
    features_consistent: bool
    constraints_consistent: bool
    tnp_consistent: bool
    cache_consistent: bool
    dependencies_consistent: bool
    orphans_detected: int
    orphan_details: List[OrphanInfo] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize result to dictionary."""
        return {
            "is_valid": self.is_valid,
            "geometry_consistent": self.geometry_consistent,
            "features_consistent": self.features_consistent,
            "constraints_consistent": self.constraints_consistent,
            "tnp_consistent": self.tnp_consistent,
            "cache_consistent": self.cache_consistent,
            "dependencies_consistent": self.dependencies_consistent,
            "orphans_detected": self.orphans_detected,
            "orphan_details": [
                {
                    "type": o.orphan_type.value,
                    "identifier": o.identifier,
                    "description": o.description,
                    "severity": o.severity,
                }
                for o in self.orphan_details
            ],
            "warnings": self.warnings,
            "errors": self.errors,
        }


class RollbackValidator:
    """
    Validates rollback consistency and detects orphaned data.
    
    Usage:
        validator = RollbackValidator(document)
        
        # Before operation
        state_before = validator.capture_state("Boolean Cut")
        
        # ... perform operation, potentially rollback ...
        
        # After rollback
        state_after = validator.capture_state("After Rollback")
        result = validator.validate_rollback(state_before, state_after)
        
        if not result.is_valid:
            orphans = validator.detect_orphans()
            validator.cleanup_orphans(orphans)
    """
    
    def __init__(self, document: Any = None, main_window: Any = None):
        """
        Initialize validator.
        
        Args:
            document: The Document to validate
            main_window: Optional MainWindow for sketch state access
        """
        self._document = document
        self._main_window = main_window
        self._state_history: List[RollbackState] = []
        self._max_history = 10
    
    def set_document(self, document: Any) -> None:
        """Set the document to validate."""
        self._document = document
    
    def set_main_window(self, main_window: Any) -> None:
        """Set main window for sketch state access."""
        self._main_window = main_window
    
    def capture_state(self, operation_name: str = "", body_name: Optional[str] = None) -> RollbackState:
        """
        Capture current system state for later validation.
        
        Args:
            operation_name: Name of the operation being performed
            body_name: Optional specific body being modified
            
        Returns:
            RollbackState snapshot
        """
        state = RollbackState(
            geometry_hash=self._compute_geometry_hash(),
            feature_count=self._count_features(),
            body_count=self._count_bodies(),
            constraint_count=self._count_constraints(),
            tnp_shape_count=self._count_tnp_shapes(),
            tnp_operation_count=self._count_tnp_operations(),
            cache_entry_count=self._count_cache_entries(),
            dependency_node_count=self._count_dependency_nodes(),
            dependency_edge_count=self._count_dependency_edges(),
            operation_name=operation_name,
            body_name=body_name,
            body_hashes=self._compute_body_hashes(),
            feature_hashes=self._compute_feature_hashes(),
        )
        
        # Store in history
        self._state_history.append(state)
        if len(self._state_history) > self._max_history:
            self._state_history.pop(0)
        
        logger.debug(f"[RollbackValidator] State captured: {operation_name}")
        logger.debug(f"  geometry_hash={state.geometry_hash[:16]}...")
        logger.debug(f"  features={state.feature_count}, bodies={state.body_count}")
        
        return state
    
    def validate_rollback(self, before: RollbackState, after: RollbackState) -> ValidationResult:
        """
        Validate that rollback restored consistent state.
        
        Args:
            before: State before the operation
            after: State after rollback
            
        Returns:
            ValidationResult with consistency details
        """
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
        
        # Check geometry consistency
        if before.geometry_hash != after.geometry_hash:
            result.geometry_consistent = False
            result.warnings.append(
                f"Geometry hash mismatch: {before.geometry_hash[:16]}... != {after.geometry_hash[:16]}..."
            )
            # This might be expected for some operations, so just warn
        
        # Check feature count consistency
        if before.feature_count != after.feature_count:
            result.features_consistent = False
            if before.feature_count > after.feature_count:
                result.warnings.append(
                    f"Feature count decreased: {before.feature_count} -> {after.feature_count}"
                )
            else:
                result.errors.append(
                    f"Feature count increased after rollback: {before.feature_count} -> {after.feature_count}"
                )
                result.is_valid = False
        
        # Check body count consistency
        if before.body_count != after.body_count:
            result.warnings.append(
                f"Body count changed: {before.body_count} -> {after.body_count}"
            )
        
        # Check constraint consistency (sketch mode)
        if before.constraint_count != after.constraint_count:
            result.constraints_consistent = False
            result.warnings.append(
                f"Constraint count mismatch: {before.constraint_count} -> {after.constraint_count}"
            )
        
        # Check TNP consistency
        if before.tnp_shape_count != after.tnp_shape_count:
            result.tnp_consistent = False
            result.warnings.append(
                f"TNP shape count mismatch: {before.tnp_shape_count} -> {after.tnp_shape_count}"
            )
        
        if before.tnp_operation_count != after.tnp_operation_count:
            result.tnp_consistent = False
            result.warnings.append(
                f"TNP operation count mismatch: {before.tnp_operation_count} -> {after.tnp_operation_count}"
            )
        
        # Check cache consistency
        if before.cache_entry_count != after.cache_entry_count:
            result.cache_consistent = False
            result.warnings.append(
                f"Cache entry count mismatch: {before.cache_entry_count} -> {after.cache_entry_count}"
            )
        
        # Check dependency graph consistency
        if before.dependency_node_count != after.dependency_node_count:
            result.dependencies_consistent = False
            result.warnings.append(
                f"Dependency node count mismatch: {before.dependency_node_count} -> {after.dependency_node_count}"
            )
        
        # Detect orphans
        orphans = self.detect_orphans()
        result.orphans_detected = len(orphans)
        result.orphan_details = orphans
        
        if orphans:
            critical_orphans = [o for o in orphans if o.severity == "critical"]
            high_orphans = [o for o in orphans if o.severity == "high"]
            
            if critical_orphans:
                result.is_valid = False
                result.errors.append(f"Critical orphans detected: {len(critical_orphans)}")
            
            if high_orphans:
                result.warnings.append(f"High severity orphans detected: {len(high_orphans)}")
        
        # Log result
        if result.is_valid:
            logger.debug(f"[RollbackValidator] Validation PASSED for '{before.operation_name}'")
        else:
            logger.warning(f"[RollbackValidator] Validation FAILED for '{before.operation_name}'")
            for error in result.errors:
                logger.warning(f"  ERROR: {error}")
            for warning in result.warnings:
                logger.debug(f"  WARNING: {warning}")
        
        return result
    
    def detect_orphans(self) -> List[OrphanInfo]:
        """
        Detect all types of orphaned data in the system.
        
        Returns:
            List of OrphanInfo for all detected orphans
        """
        orphans: List[OrphanInfo] = []
        
        orphans.extend(self._detect_tnp_orphans())
        orphans.extend(self._detect_feature_reference_orphans())
        orphans.extend(self._detect_cache_orphans())
        orphans.extend(self._detect_dependency_orphans())
        
        if orphans:
            logger.debug(f"[RollbackValidator] Detected {len(orphans)} orphaned items")
        
        return orphans
    
    def cleanup_orphans(self, orphans: Optional[List[OrphanInfo]] = None) -> int:
        """
        Remove orphaned data from the system.
        
        Args:
            orphans: List of orphans to clean up, or None to detect automatically
            
        Returns:
            Number of orphaned items removed
        """
        if orphans is None:
            orphans = self.detect_orphans()
        
        cleaned = 0
        
        for orphan in orphans:
            try:
                if orphan.orphan_type == OrphanType.TNP_SHAPE:
                    if self._cleanup_tnp_shape(orphan):
                        cleaned += 1
                
                elif orphan.orphan_type == OrphanType.TNP_OPERATION:
                    if self._cleanup_tnp_operation(orphan):
                        cleaned += 1
                
                elif orphan.orphan_type == OrphanType.CACHE_ENTRY:
                    if self._cleanup_cache_entry(orphan):
                        cleaned += 1
                
                elif orphan.orphan_type == OrphanType.DEPENDENCY_EDGE:
                    if self._cleanup_dependency_edge(orphan):
                        cleaned += 1
                
            except Exception as e:
                logger.warning(f"[RollbackValidator] Failed to cleanup orphan {orphan.identifier}: {e}")
        
        if cleaned > 0:
            logger.info(f"[RollbackValidator] Cleaned up {cleaned} orphaned items")
        
        return cleaned
    
    # === State Capture Helpers ===
    
    def _compute_geometry_hash(self) -> str:
        """Compute hash of all body geometries."""
        if not self._document:
            return ""
        
        hash_input = ""
        
        for body in getattr(self._document, 'bodies', []):
            if hasattr(body, '_build123d_solid') and body._build123d_solid:
                # Use BREP representation for hash
                try:
                    from OCP.BRepTools import BRepTools
                    from OCP.TopoDS import TopoDS_Shape
                    import io
                    
                    shape = body._build123d_solid.wrapped
                    stream = io.BytesIO()
                    BRepTools.Write_s(shape, stream)
                    brep_bytes = stream.getvalue()
                    hash_input += f"{body.name}:{hashlib.md5(brep_bytes).hexdigest()}:"
                except Exception:
                    # Fallback to string representation
                    hash_input += f"{body.name}:{str(body._build123d_solid)}:"
        
        return hashlib.sha256(hash_input.encode()).hexdigest()
    
    def _compute_body_hashes(self) -> Dict[str, str]:
        """Compute per-body geometry hashes."""
        hashes = {}
        
        if not self._document:
            return hashes
        
        for body in getattr(self._document, 'bodies', []):
            if hasattr(body, '_build123d_solid') and body._build123d_solid:
                try:
                    from OCP.BRepTools import BRepTools
                    from OCP.TopoDS import TopoDS_Shape
                    import io
                    
                    shape = body._build123d_solid.wrapped
                    stream = io.BytesIO()
                    BRepTools.Write_s(shape, stream)
                    brep_bytes = stream.getvalue()
                    hashes[body.name] = hashlib.md5(brep_bytes).hexdigest()
                except Exception:
                    hashes[body.name] = hashlib.md5(str(body._build123d_solid).encode()).hexdigest()
        
        return hashes
    
    def _compute_feature_hashes(self) -> Dict[str, List[str]]:
        """Compute per-body feature hashes."""
        hashes = {}
        
        if not self._document:
            return hashes
        
        for body in getattr(self._document, 'bodies', []):
            if hasattr(body, 'features') and body.features:
                body_hashes = []
                for feature in body.features:
                    feat_str = f"{feature.name}:{feature.type}:{getattr(feature, 'status', '')}"
                    body_hashes.append(hashlib.md5(feat_str.encode()).hexdigest())
                hashes[body.name] = body_hashes
        
        return hashes
    
    def _count_features(self) -> int:
        """Count total features across all bodies."""
        if not self._document:
            return 0
        
        count = 0
        for body in getattr(self._document, 'bodies', []):
            if hasattr(body, 'features'):
                count += len(body.features)
        
        return count
    
    def _count_bodies(self) -> int:
        """Count bodies in document."""
        if not self._document:
            return 0
        
        return len(getattr(self._document, 'bodies', []))
    
    def _count_constraints(self) -> int:
        """Count constraints in active sketch."""
        if not self._main_window:
            return 0
        
        sketch_editor = getattr(self._main_window, 'sketch_editor', None)
        if sketch_editor:
            sketch = getattr(sketch_editor, 'sketch', None)
            if sketch:
                return len(getattr(sketch, 'constraints', []))
        
        return 0
    
    def _count_tnp_shapes(self) -> int:
        """Count TNP shape records."""
        if not self._document:
            return 0
        
        service = getattr(self._document, '_shape_naming_service', None)
        if service:
            return len(getattr(service, '_shapes', {}))
        
        return 0
    
    def _count_tnp_operations(self) -> int:
        """Count TNP operation records."""
        if not self._document:
            return 0
        
        service = getattr(self._document, '_shape_naming_service', None)
        if service:
            return len(getattr(service, '_operations', []))
        
        return 0
    
    def _count_cache_entries(self) -> int:
        """Count cache entries."""
        if not self._document:
            return 0
        
        count = 0
        for body in getattr(self._document, 'bodies', []):
            if hasattr(body, '_mesh_cache') and body._mesh_cache:
                count += 1
            if hasattr(body, '_edges_cache') and body._edges_cache:
                count += 1
        
        # Count BREP cache
        try:
            from modeling.brep_cache import BRepCache
            cache = BRepCache()
            count += cache.size()
        except Exception:
            pass
        
        return count
    
    def _count_dependency_nodes(self) -> int:
        """Count dependency graph nodes."""
        if not self._document:
            return 0
        
        count = 0
        for body in getattr(self._document, 'bodies', []):
            if hasattr(body, '_dependency_graph'):
                graph = body._dependency_graph
                if graph:
                    count += len(getattr(graph, '_nodes', {}))
        
        return count
    
    def _count_dependency_edges(self) -> int:
        """Count dependency graph edges."""
        if not self._document:
            return 0
        
        count = 0
        for body in getattr(self._document, 'bodies', []):
            if hasattr(body, '_dependency_graph'):
                graph = body._dependency_graph
                if graph:
                    count += len(getattr(graph, '_edges', []))
        
        return count
    
    # === Orphan Detection Helpers ===
    
    def _detect_tnp_orphans(self) -> List[OrphanInfo]:
        """Detect orphaned TNP records."""
        orphans = []
        
        if not self._document:
            return orphans
        
        service = getattr(self._document, '_shape_naming_service', None)
        if not service:
            return orphans
        
        # Get all valid feature IDs
        valid_feature_ids: Set[str] = set()
        for body in getattr(self._document, 'bodies', []):
            if hasattr(body, 'features'):
                for feature in body.features:
                    if hasattr(feature, 'id'):
                        valid_feature_ids.add(feature.id)
        
        # Check TNP shapes for orphaned feature references
        shapes = getattr(service, '_shapes', {})
        by_feature = getattr(service, '_by_feature', {})
        
        for feature_id in by_feature.keys():
            if feature_id not in valid_feature_ids:
                orphans.append(OrphanInfo(
                    orphan_type=OrphanType.TNP_SHAPE,
                    identifier=feature_id,
                    description=f"TNP shapes reference non-existent feature: {feature_id}",
                    severity="medium",
                    parent_reference=feature_id,
                ))
        
        # Check for shapes with invalid geometry
        for uuid, record in shapes.items():
            if hasattr(record, 'is_valid') and not record.is_valid:
                orphans.append(OrphanInfo(
                    orphan_type=OrphanType.TNP_SHAPE,
                    identifier=uuid,
                    description=f"Invalid TNP shape record: {uuid}",
                    severity="low",
                    metadata={"shape_type": str(getattr(record.shape_id, 'shape_type', 'unknown'))},
                ))
        
        return orphans
    
    def _detect_feature_reference_orphans(self) -> List[OrphanInfo]:
        """Detect features referencing non-existent shapes."""
        orphans = []
        
        if not self._document:
            return orphans
        
        service = getattr(self._document, '_shape_naming_service', None)
        valid_shape_ids: Set[str] = set()
        
        if service:
            shapes = getattr(service, '_shapes', {})
            valid_shape_ids = set(shapes.keys())
        
        for body in getattr(self._document, 'bodies', []):
            if not hasattr(body, 'features'):
                continue
            
            for feature in body.features:
                # Check for shape references in feature
                if hasattr(feature, 'shape_references'):
                    for ref in feature.shape_references:
                        if hasattr(ref, 'uuid') and ref.uuid not in valid_shape_ids:
                            orphans.append(OrphanInfo(
                                orphan_type=OrphanType.FEATURE_REFERENCE,
                                identifier=f"{feature.id}:{ref.uuid}",
                                description=f"Feature '{feature.name}' references missing shape: {ref.uuid}",
                                severity="high",
                                parent_reference=feature.id,
                            ))
        
        return orphans
    
    def _detect_cache_orphans(self) -> List[OrphanInfo]:
        """Detect orphaned cache entries."""
        orphans = []
        
        if not self._document:
            return orphans
        
        valid_body_names: Set[str] = {b.name for b in getattr(self._document, 'bodies', [])}
        
        # Check BREP cache for orphaned entries
        try:
            from modeling.brep_cache import BRepCache
            cache = BRepCache()
            
            # This would require cache to expose entry metadata
            # For now, we just count entries
            pass
        except Exception:
            pass
        
        return orphans
    
    def _detect_dependency_orphans(self) -> List[OrphanInfo]:
        """Detect orphaned dependency graph edges."""
        orphans = []
        
        if not self._document:
            return orphans
        
        for body in getattr(self._document, 'bodies', []):
            if not hasattr(body, '_dependency_graph') or not body._dependency_graph:
                continue
            
            graph = body._dependency_graph
            nodes = getattr(graph, '_nodes', {})
            edges = getattr(graph, '_edges', [])
            
            valid_node_ids: Set[str] = set(nodes.keys())
            
            for edge in edges:
                # Check if source and target nodes exist
                source = getattr(edge, 'source', None)
                target = getattr(edge, 'target', None)
                
                if source and source not in valid_node_ids:
                    orphans.append(OrphanInfo(
                        orphan_type=OrphanType.DEPENDENCY_EDGE,
                        identifier=f"{body.name}:{source}",
                        description=f"Dependency edge references missing source node: {source}",
                        severity="medium",
                        parent_reference=body.name,
                    ))
                
                if target and target not in valid_node_ids:
                    orphans.append(OrphanInfo(
                        orphan_type=OrphanType.DEPENDENCY_EDGE,
                        identifier=f"{body.name}:{target}",
                        description=f"Dependency edge references missing target node: {target}",
                        severity="medium",
                        parent_reference=body.name,
                    ))
        
        return orphans
    
    # === Cleanup Helpers ===
    
    def _cleanup_tnp_shape(self, orphan: OrphanInfo) -> bool:
        """Remove orphaned TNP shape."""
        if not self._document:
            return False
        
        service = getattr(self._document, '_shape_naming_service', None)
        if not service:
            return False
        
        feature_id = orphan.parent_reference
        if feature_id and hasattr(service, '_by_feature'):
            if feature_id in service._by_feature:
                del service._by_feature[feature_id]
                logger.debug(f"[RollbackValidator] Removed TNP shapes for feature: {feature_id}")
                return True
        
        return False
    
    def _cleanup_tnp_operation(self, orphan: OrphanInfo) -> bool:
        """Remove orphaned TNP operation."""
        if not self._document:
            return False
        
        service = getattr(self._document, '_shape_naming_service', None)
        if not service:
            return False
        
        operations = getattr(service, '_operations', [])
        op_id = orphan.identifier
        
        # Remove operations with matching ID
        original_count = len(operations)
        service._operations = [op for op in operations if getattr(op, 'operation_id', None) != op_id]
        
        if len(service._operations) < original_count:
            logger.debug(f"[RollbackValidator] Removed TNP operation: {op_id}")
            return True
        
        return False
    
    def _cleanup_cache_entry(self, orphan: OrphanInfo) -> bool:
        """Remove orphaned cache entry."""
        # Cache cleanup would require cache to support removal by key
        # For now, invalidate all caches on the affected body
        if not self._document:
            return False
        
        body_name = orphan.parent_reference
        if body_name:
            for body in getattr(self._document, 'bodies', []):
                if body.name == body_name:
                    if hasattr(body, 'invalidate_mesh'):
                        body.invalidate_mesh()
                        logger.debug(f"[RollbackValidator] Invalidated cache for body: {body_name}")
                        return True
        
        return False
    
    def _cleanup_dependency_edge(self, orphan: OrphanInfo) -> bool:
        """Remove orphaned dependency edge."""
        if not self._document:
            return False
        
        body_name = orphan.parent_reference
        if body_name:
            for body in getattr(self._document, 'bodies', []):
                if body.name == body_name and hasattr(body, '_dependency_graph'):
                    graph = body._dependency_graph
                    if graph and hasattr(graph, '_edges'):
                        original_count = len(graph._edges)
                        # Remove edges with missing nodes
                        valid_nodes = set(getattr(graph, '_nodes', {}).keys())
                        graph._edges = [
                            e for e in graph._edges
                            if getattr(e, 'source', None) in valid_nodes
                            and getattr(e, 'target', None) in valid_nodes
                        ]
                        
                        if len(graph._edges) < original_count:
                            logger.debug(f"[RollbackValidator] Cleaned dependency edges for: {body_name}")
                            return True
        
        return False


# === Integration Helpers ===

def create_validator_from_body(body: Any) -> RollbackValidator:
    """Create a validator for a specific body."""
    document = getattr(body, '_document', None)
    return RollbackValidator(document=document)


def validate_body_rollback(body: Any, operation_name: str) -> Tuple[RollbackState, RollbackValidator]:
    """
    Capture state for body rollback validation.
    
    Usage:
        state_before, validator = validate_body_rollback(body, "Boolean Cut")
        # ... perform operation ...
        # After rollback:
        state_after = validator.capture_state("After Rollback")
        result = validator.validate_rollback(state_before, state_after)
    """
    validator = create_validator_from_body(body)
    state = validator.capture_state(operation_name, body.name)
    return state, validator
