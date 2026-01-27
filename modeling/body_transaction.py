"""
MashCAD - Body Transaction System
==================================

Professional transaction-based state management for CAD bodies.
Ensures atomic Boolean operations with automatic rollback on failure.

Problem solved:
- No more "body is corrupt" states
- Failed Boolean operations automatically rollback
- User can always continue working after errors

Author: Claude (Architecture Refactoring Phase 1)
Date: 2026-01-22
"""

import copy
from typing import Optional, Any, Dict
from dataclasses import dataclass
from loguru import logger


class BooleanOperationError(Exception):
    """Raised when Boolean operation fails and should trigger rollback"""
    pass


@dataclass
class BodySnapshot:
    """Immutable snapshot of Body state for rollback"""

    solid: Any                    # build123d Solid (CAD kernel)
    features: list                # Feature history (deep copy)
    metadata: Dict[str, Any]      # Name, color, visibility, etc.

    # Optional cached visualization (not critical for rollback)
    vtk_mesh: Optional[Any] = None
    vtk_edges: Optional[Any] = None
    vtk_normals: Optional[Any] = None

    def __post_init__(self):
        """Ensure features are deep copied"""
        if self.features is not None:
            self.features = copy.deepcopy(self.features)


class BodyTransaction:
    """
    Context manager for atomic Body modifications with rollback.

    Usage:
        with BodyTransaction(body, "Boolean Cut") as txn:
            result = body.execute_boolean_operation(...)

            if result.is_error:
                raise BooleanOperationError(result.message)

            # Update body state
            body._build123d_solid = result.value
            body.invalidate_cache()

            # Mark as successful (prevents rollback)
            txn.commit()

    On exception or missing commit():
        - Body state is restored to snapshot
        - Exception is logged but suppressed
        - User can continue working
    """

    def __init__(self, body: 'Body', operation_name: str = "Operation"):
        """
        Initialize transaction.

        Args:
            body: The Body to protect
            operation_name: Human-readable operation description for logging
        """
        self._body = body
        self._operation_name = operation_name
        self._snapshot: Optional[BodySnapshot] = None
        self._committed = False
        self._entered = False

    def __enter__(self) -> 'BodyTransaction':
        """
        Enter transaction - create snapshot.
        """
        if self._entered:
            raise RuntimeError("Transaction already entered")

        self._entered = True

        # Create immutable snapshot of ALL critical state
        self._snapshot = BodySnapshot(
            solid=self._body._build123d_solid,
            features=self._body.features,
            metadata=copy.deepcopy(self._body.metadata),
            vtk_mesh=getattr(self._body, 'vtk_mesh', None),
            vtk_edges=getattr(self._body, 'vtk_edges', None),
            vtk_normals=getattr(self._body, 'vtk_normals', None)
        )

        logger.debug(f"📸 Transaction started: {self._operation_name}")
        return self

    def commit(self):
        """
        Mark transaction as successful.

        Call this ONLY if operation succeeded.
        If not called, __exit__ will trigger rollback.
        """
        if not self._entered:
            raise RuntimeError("Cannot commit - transaction not entered")

        self._committed = True
        logger.success(f"✅ Transaction committed: {self._operation_name}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit transaction - rollback if not committed or on exception.

        Args:
            exc_type: Exception type (or None)
            exc_val: Exception value (or None)
            exc_tb: Exception traceback (or None)

        Returns:
            True to suppress exception, False to propagate
        """
        if not self._entered:
            return False

        # Determine if rollback is needed
        needs_rollback = not self._committed or exc_type is not None

        if needs_rollback:
            self._rollback(exc_type, exc_val)

            # Suppress BooleanOperationError (expected failure)
            # Propagate other exceptions (programming errors)
            if exc_type is BooleanOperationError:
                return True  # Suppress exception - user can continue

            return False  # Propagate unexpected exceptions

        return False

    def _rollback(self, exc_type, exc_val):
        """
        Restore body to snapshot state.

        Args:
            exc_type: Exception type that triggered rollback
            exc_val: Exception value
        """
        if self._snapshot is None:
            logger.error("❌ Cannot rollback - no snapshot available!")
            return

        try:
            # Restore CAD kernel state (CRITICAL)
            self._body._build123d_solid = self._snapshot.solid

            # Restore feature history
            self._body.features = self._snapshot.features

            # Restore metadata
            self._body.metadata = self._snapshot.metadata

            # Invalidate mesh cache — lazy regeneration from restored solid
            if hasattr(self._body, 'invalidate_mesh'):
                self._body.invalidate_mesh()
            else:
                self._body._mesh_cache = None
                self._body._edges_cache = None
                self._body._mesh_cache_valid = False

            # Log rollback reason
            if exc_type is BooleanOperationError:
                logger.warning(f"⏪ Transaction rolled back: {self._operation_name}")
                logger.warning(f"   Reason: {exc_val}")
            elif exc_type is not None:
                logger.error(f"⏪ Transaction rolled back due to exception: {exc_type.__name__}")
                logger.error(f"   Message: {exc_val}")
            else:
                logger.warning(f"⏪ Transaction rolled back: {self._operation_name} (not committed)")

            logger.info(f"✓ Body state restored to pre-operation snapshot")

        except Exception as rollback_error:
            # Critical: Rollback itself failed!
            logger.critical(f"❌❌❌ ROLLBACK FAILED: {rollback_error}")
            logger.critical(f"Body '{self._body.name}' may be in corrupt state!")
            # Don't suppress this - it's a critical error
            raise


class BatchTransaction:
    """
    Transaction for multiple bodies (e.g., multi-body Boolean).

    Usage:
        with BatchTransaction([body1, body2], "Multi-body Join") as txn:
            # Modify both bodies
            body1._build123d_solid = new_solid1
            body2._build123d_solid = new_solid2

            txn.commit()  # Commit all or rollback all
    """

    def __init__(self, bodies: list, operation_name: str = "Batch Operation"):
        """
        Initialize batch transaction.

        Args:
            bodies: List of Bodies to protect
            operation_name: Operation description
        """
        self._bodies = bodies
        self._operation_name = operation_name
        self._transactions = []
        self._committed = False

    def __enter__(self) -> 'BatchTransaction':
        """Create individual transactions for each body"""
        for body in self._bodies:
            txn = BodyTransaction(body, self._operation_name)
            txn.__enter__()
            self._transactions.append(txn)

        logger.debug(f"📸 Batch transaction started: {self._operation_name} ({len(self._bodies)} bodies)")
        return self

    def commit(self):
        """Commit all transactions"""
        self._committed = True
        for txn in self._transactions:
            txn.commit()

        logger.success(f"✅ Batch transaction committed: {self._operation_name}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit all transactions (rollback if not committed)"""
        # Exit all transactions in reverse order
        for txn in reversed(self._transactions):
            txn.__exit__(exc_type, exc_val, exc_tb)

        if not self._committed and exc_type is not None:
            logger.warning(f"⏪ Batch transaction rolled back: {self._operation_name}")

        # Suppress BooleanOperationError
        return exc_type is BooleanOperationError
