"""
MashCad - Unified Result Types for Operation Transparency

Provides structured result types that clearly differentiate between:
- SUCCESS: Operation completed as expected
- WARNING: Operation completed but with fallback or partial results
- EMPTY: Operation completed but returned no results (not an error)
- ERROR: Operation failed and could not complete

Usage:
    from modeling.result_types import OperationResult, ResultStatus

    def my_operation() -> OperationResult:
        try:
            result = do_something()
            if result is None:
                return OperationResult.empty("No geometry found")
            return OperationResult.success(result)
        except SomeRecoverableError as e:
            fallback = try_fallback()
            return OperationResult.warning(fallback, f"Used fallback: {e}")
        except Exception as e:
            return OperationResult.error(f"Operation failed: {e}")
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional, List, Dict
from loguru import logger


class ResultStatus(Enum):
    """
    Clear operation outcome states for logging and test reports.

    SUCCESS  - Operation completed exactly as expected
    WARNING  - Operation completed but used fallback or has partial results
    EMPTY    - Operation completed correctly but returned no results
    ERROR    - Operation failed and could not complete
    """
    SUCCESS = auto()
    WARNING = auto()
    EMPTY = auto()
    ERROR = auto()


@dataclass
class OperationResult:
    """
    Unified result type for CAD operations.

    Attributes:
        status: ResultStatus indicating outcome type
        value: The result value (solid, mesh, list, etc.) - None for ERROR/EMPTY
        message: Human-readable description of what happened
        details: Additional context (fallback used, skipped items, etc.)
        warnings: List of non-fatal issues encountered
        failed_items: List of items that failed (for partial success)
    """
    status: ResultStatus
    value: Any = None
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    failed_items: List[Any] = field(default_factory=list)

    # --- Factory Methods ---

    @classmethod
    def success(cls, value: Any, message: str = "Operation completed successfully") -> "OperationResult":
        """Create a SUCCESS result."""
        return cls(
            status=ResultStatus.SUCCESS,
            value=value,
            message=message
        )

    @classmethod
    def warning(cls, value: Any, message: str, fallback_used: str = None,
                warnings: List[str] = None, failed_items: List[Any] = None) -> "OperationResult":
        """
        Create a WARNING result for partial success or fallback usage.

        Args:
            value: The result (may be partial or from fallback)
            message: Description of what happened
            fallback_used: Name of fallback strategy used
            warnings: List of warning messages
            failed_items: Items that could not be processed
        """
        details = {}
        if fallback_used:
            details["fallback_used"] = fallback_used

        return cls(
            status=ResultStatus.WARNING,
            value=value,
            message=message,
            details=details,
            warnings=warnings or [],
            failed_items=failed_items or []
        )

    @classmethod
    def empty(cls, message: str = "No results found", reason: str = None) -> "OperationResult":
        """
        Create an EMPTY result for valid operations with no output.

        This is NOT an error - the operation executed correctly but found nothing.
        Example: Searching for intersections where none exist.
        """
        details = {}
        if reason:
            details["reason"] = reason

        return cls(
            status=ResultStatus.EMPTY,
            value=None,
            message=message,
            details=details
        )

    @classmethod
    def error(cls, message: str, exception: Exception = None,
              context: Dict[str, Any] = None) -> "OperationResult":
        """
        Create an ERROR result for failed operations.

        Args:
            message: Description of what went wrong
            exception: The exception that caused the failure
            context: Additional context for debugging
        """
        details = context or {}
        if exception:
            details["exception_type"] = type(exception).__name__
            details["exception_message"] = str(exception)

        return cls(
            status=ResultStatus.ERROR,
            value=None,
            message=message,
            details=details
        )

    # --- Properties ---

    @property
    def is_success(self) -> bool:
        """True if operation completed successfully (SUCCESS or WARNING with value)."""
        return self.status == ResultStatus.SUCCESS or (
            self.status == ResultStatus.WARNING and self.value is not None
        )

    @property
    def is_error(self) -> bool:
        """True if operation failed."""
        return self.status == ResultStatus.ERROR

    @property
    def is_empty(self) -> bool:
        """True if operation returned no results."""
        return self.status == ResultStatus.EMPTY

    @property
    def has_warnings(self) -> bool:
        """True if there are warnings to report."""
        return self.status == ResultStatus.WARNING or len(self.warnings) > 0

    @property
    def has_failed_items(self) -> bool:
        """True if some items failed during operation."""
        return len(self.failed_items) > 0

    # --- Logging Integration ---

    def log(self, context: str = "") -> "OperationResult":
        """
        Log the result with appropriate log level.

        Args:
            context: Additional context string for the log message

        Returns:
            self for chaining
        """
        prefix = f"[{context}] " if context else ""

        if self.status == ResultStatus.SUCCESS:
            logger.success(f"{prefix}{self.message}")

        elif self.status == ResultStatus.WARNING:
            logger.warning(f"{prefix}{self.message}")
            for warn in self.warnings:
                logger.warning(f"{prefix}  - {warn}")
            if self.failed_items:
                logger.warning(f"{prefix}  Failed items: {len(self.failed_items)}")

        elif self.status == ResultStatus.EMPTY:
            logger.info(f"{prefix}{self.message}")
            if "reason" in self.details:
                logger.debug(f"{prefix}  Reason: {self.details['reason']}")

        elif self.status == ResultStatus.ERROR:
            logger.error(f"{prefix}{self.message}")
            if "exception_type" in self.details:
                logger.error(f"{prefix}  Exception: {self.details['exception_type']}: {self.details.get('exception_message', '')}")

        return self

    # --- Report Generation ---

    def to_report_dict(self) -> Dict[str, Any]:
        """
        Generate a dictionary suitable for test reports.

        Returns:
            Dict with status, message, and relevant details
        """
        report = {
            "status": self.status.name,
            "message": self.message,
        }

        if self.details:
            report["details"] = self.details

        if self.warnings:
            report["warnings"] = self.warnings

        if self.failed_items:
            report["failed_count"] = len(self.failed_items)

        if self.value is not None:
            # Add type info for debugging
            report["value_type"] = type(self.value).__name__

        return report

    def __repr__(self) -> str:
        parts = [f"OperationResult({self.status.name}"]
        if self.message:
            parts.append(f", message='{self.message[:50]}...'")
        if self.has_warnings:
            parts.append(f", warnings={len(self.warnings)}")
        if self.has_failed_items:
            parts.append(f", failed={len(self.failed_items)}")
        parts.append(")")
        return "".join(parts)


# --- Specialized Result Types ---

@dataclass
class BooleanResult(OperationResult):
    """
    Specialized result for boolean operations (fuse, cut, intersect).

    Additional context for boolean-specific issues.

    Phase 2 TNP (Shape History):
    - history: BRepTools_History object from OCP Boolean operation
    - Tracks wie sich Faces/Edges durch Boolean-Op geändert haben
    - Ermöglicht 95-99% TNP-Robustheit (statt 70-80% mit Geometric Naming)
    """
    operation_type: str = ""  # "fuse", "cut", "intersect"
    history: Any = None  # BRepTools_History (OCP) - für Phase 2 TNP

    @classmethod
    def from_operation(cls, op_type: str, solid: Any,
                       status: ResultStatus = ResultStatus.SUCCESS,
                       message: str = "",
                       history: Any = None) -> "BooleanResult":
        """
        Create from a boolean operation.

        Args:
            op_type: "fuse", "cut", "intersect"
            solid: Result solid
            status: Operation status
            message: Description
            history: BRepTools_History (Phase 2 TNP)
        """
        result = cls(
            status=status,
            value=solid,
            message=message or f"Boolean {op_type} completed",
            operation_type=op_type,
            history=history
        )
        return result


@dataclass
class FilletChamferResult(OperationResult):
    """
    Specialized result for fillet/chamfer operations.

    Tracks which edges succeeded/failed.
    """
    total_edges: int = 0
    successful_edges: int = 0
    failed_edge_indices: List[int] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Percentage of edges successfully processed."""
        if self.total_edges == 0:
            return 0.0
        return (self.successful_edges / self.total_edges) * 100

    def to_report_dict(self) -> Dict[str, Any]:
        report = super().to_report_dict()
        report.update({
            "total_edges": self.total_edges,
            "successful_edges": self.successful_edges,
            "failed_edge_indices": self.failed_edge_indices,
            "success_rate": f"{self.success_rate:.1f}%"
        })
        return report


@dataclass
class ExtrudeResult(OperationResult):
    """
    Specialized result for extrusion operations.
    """
    extrude_height: float = 0.0
    profile_count: int = 0

    def to_report_dict(self) -> Dict[str, Any]:
        report = super().to_report_dict()
        report.update({
            "extrude_height": self.extrude_height,
            "profile_count": self.profile_count
        })
        return report


# --- Helper Functions ---

def combine_results(results: List[OperationResult], context: str = "") -> OperationResult:
    """
    Combine multiple OperationResults into a single summary result.

    Rules:
    - Any ERROR → combined result is ERROR
    - All EMPTY → combined result is EMPTY
    - Any WARNING → combined result is WARNING
    - All SUCCESS → combined result is SUCCESS

    Args:
        results: List of OperationResults to combine
        context: Description of what was being done

    Returns:
        Combined OperationResult
    """
    if not results:
        return OperationResult.empty(f"{context}: No operations performed")

    errors = [r for r in results if r.status == ResultStatus.ERROR]
    warnings = [r for r in results if r.status == ResultStatus.WARNING]
    empties = [r for r in results if r.status == ResultStatus.EMPTY]
    successes = [r for r in results if r.status == ResultStatus.SUCCESS]

    all_warnings = []
    all_failed = []
    values = []

    for r in results:
        all_warnings.extend(r.warnings)
        all_failed.extend(r.failed_items)
        if r.value is not None:
            values.append(r.value)

    if errors:
        return OperationResult.error(
            f"{context}: {len(errors)}/{len(results)} operations failed",
            context={"error_messages": [e.message for e in errors]}
        )

    if len(empties) == len(results):
        return OperationResult.empty(f"{context}: All operations returned empty")

    if warnings:
        return OperationResult.warning(
            values if values else None,
            f"{context}: {len(successes)} succeeded, {len(warnings)} with warnings, {len(empties)} empty",
            warnings=[w.message for w in warnings] + all_warnings,
            failed_items=all_failed
        )

    return OperationResult.success(
        values if values else None,
        f"{context}: All {len(successes)} operations succeeded"
    )
