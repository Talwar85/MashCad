"""
TNP v5.0 - Feature Ambiguity Resolution Helper

Provides helper functions for integrating ambiguity checking
into feature operations (Fillet, Chamfer, Boolean).

This module is called by workflow/command systems before executing
features that may have ambiguous shape selections.
"""

from typing import Optional, List, Dict, Any
from loguru import logger

from modeling.tnp_v5.ambiguity import (
    AmbiguityDetector,
    AmbiguityReport,
    CandidateInfo,
    AmbiguityType,
    detect_ambiguity,
)
from modeling.tnp_v5 import TNPService, ShapeID


class FeatureAmbiguityChecker:
    """
    Helper class for checking and resolving ambiguity in feature operations.

    Called by workflows before executing features like Fillet, Chamfer, Boolean.
    """

    def __init__(self, tnp_service: TNPService):
        """
        Initialize the ambiguity checker.

        Args:
            tnp_service: TNP v5.0 service for shape resolution
        """
        self._tnp_service = tnp_service
        self._detector = AmbiguityDetector()

    def check_fillet_edges(
        self,
        edge_ids: List[str],
        feature_id: str
    ) -> Optional[AmbiguityReport]:
        """
        Check if selected edges for fillet are ambiguous.

        Args:
            edge_ids: List of selected edge shape IDs
            feature_id: Feature that will use these edges

        Returns:
            AmbiguityReport if ambiguous, None otherwise
        """
        if len(edge_ids) < 2:
            return None

        # Build candidate info list
        candidates = []
        for edge_id in edge_ids:
            record = self._tnp_service.get_shape_record(edge_id)
            if record:
                # Use geometric_signature not signature
                geo_sig = record.geometric_signature if record.geometric_signature else {}
                candidates.append(CandidateInfo(
                    shape_id=edge_id,
                    score=0.8,  # Default score (edges selected by user)
                    distance=0.0,
                    shape_type=str(record.shape_id.shape_type.value),
                    feature_id=feature_id,
                    geometry_hash=geo_sig.get('geometry_hash') if geo_sig else None,
                    center=geo_sig.get('center') if geo_sig else None
                ))

        if not candidates:
            return None

        return self._detector.detect(candidates)

    def check_chamfer_edges(
        self,
        edge_ids: List[str],
        feature_id: str
    ) -> Optional[AmbiguityReport]:
        """
        Check if selected edges for chamfer are ambiguous.

        Args:
            edge_ids: List of selected edge shape IDs
            feature_id: Feature that will use these edges

        Returns:
            AmbiguityReport if ambiguous, None otherwise
        """
        # Same logic as fillet
        return self.check_fillet_edges(edge_ids, feature_id)

    def check_boolean_tool(
        self,
        target_body_id: str,
        tool_body_id: str,
        operation: str
    ) -> Optional[AmbiguityReport]:
        """
        Check if boolean operation has ambiguity (e.g., symmetric target selection).

        Args:
            target_body_id: Target body ID
            tool_body_id: Tool body ID
            operation: Boolean operation type

        Returns:
            AmbiguityReport if ambiguous, None otherwise
        """
        # For boolean, ambiguity typically means:
        # 1. Multiple possible target bodies with similar positions
        # 2. Symmetric tool placement

        # Get body positions from service
        target_record = self._tnp_service.get_shape_record(target_body_id)
        tool_record = self._tnp_service.get_shape_record(tool_body_id)

        if not target_record or not tool_record:
            return None

        # Use geometric_signature not signature
        target_sig = target_record.geometric_signature if target_record.geometric_signature else {}
        tool_sig = tool_record.geometric_signature if tool_record.geometric_signature else {}

        # Check for symmetric position (simple check)
        target_center = target_sig.get('center', (0, 0, 0))
        tool_center = tool_sig.get('center', (0, 0, 0))

        # Check if positions are symmetric
        if self._are_positions_symmetric(target_center, tool_center):
            return AmbiguityReport(
                ambiguity_type=AmbiguityType.SYMMETRIC,
                question=f"Boolean {operation}: Tool and target are in symmetric positions. Which should be used?",
                candidates=[target_body_id, tool_body_id],
                candidate_descriptions=[
                    f"Target at {target_center}",
                    f"Tool at {tool_center}"
                ],
                metadata={"operation": operation}
            )

        return None

    def _are_positions_symmetric(
        self,
        pos1: tuple,
        pos2: tuple,
        threshold: float = 0.1
    ) -> bool:
        """Check if two positions are symmetric."""
        x1, y1, z1 = pos1
        x2, y2, z2 = pos2

        # Mirror across one of the planes
        if abs(x1 + x2) < threshold and abs(y1 - y2) < threshold and abs(z1 - z2) < threshold:
            return True
        if abs(x1 - x2) < threshold and abs(y1 + y2) < threshold and abs(z1 - z2) < threshold:
            return True
        if abs(x1 - x2) < threshold and abs(y1 - y2) < threshold and abs(z1 + z2) < threshold:
            return True

        return False


def resolve_feature_ambiguity(
    report: AmbiguityReport,
    parent_widget=None
) -> Optional[str]:
    """
    Resolve feature ambiguity by showing dialog to user.

    Args:
        report: AmbiguityReport with candidates
        parent_widget: Parent widget for dialog

    Returns:
        Selected candidate ID or None if cancelled
    """
    try:
        from gui.dialogs.ambiguity_dialog import resolve_ambiguity_dialog

        return resolve_ambiguity_dialog(report, parent=parent_widget)

    except ImportError:
        logger.warning("[FeatureAmbiguity] Dialog module not available")
        return None
    except Exception as e:
        logger.error(f"[FeatureAmbiguity] Error showing dialog: {e}")
        return None


def check_and_resolve_fillet_ambiguity(
    edge_ids: List[str],
    feature_id: str,
    tnp_service: TNPService,
    parent_widget=None
) -> List[str]:
    """
    Check for ambiguity in fillet edge selection and resolve if needed.

    Args:
        edge_ids: List of selected edge IDs
        feature_id: Feature being created
        tnp_service: TNP v5.0 service
        parent_widget: Parent widget for dialog

    Returns:
        List of edge IDs to use (may be filtered by user selection)
    """
    checker = FeatureAmbiguityChecker(tnp_service)
    report = checker.check_fillet_edges(edge_ids, feature_id)

    if report is None:
        return edge_ids  # No ambiguity

    # Resolve with user
    selected_id = resolve_feature_ambiguity(report, parent_widget)

    if selected_id is None:
        return []  # User cancelled

    # User selected one, return only that
    return [selected_id]


def check_and_resolve_chamfer_ambiguity(
    edge_ids: List[str],
    feature_id: str,
    tnp_service: TNPService,
    parent_widget=None
) -> List[str]:
    """
    Check for ambiguity in chamfer edge selection and resolve if needed.

    Args:
        edge_ids: List of selected edge IDs
        feature_id: Feature being created
        tnp_service: TNP v5.0 service
        parent_widget: Parent widget for dialog

    Returns:
        List of edge IDs to use (may be filtered by user selection)
    """
    checker = FeatureAmbiguityChecker(tnp_service)
    report = checker.check_chamfer_edges(edge_ids, feature_id)

    if report is None:
        return edge_ids

    selected_id = resolve_feature_ambiguity(report, parent_widget)

    if selected_id is None:
        return []

    return [selected_id]


def check_and_resolve_boolean_ambiguity(
    target_body_id: str,
    tool_body_id: str,
    operation: str,
    tnp_service: TNPService,
    parent_widget=None
) -> bool:
    """
    Check for ambiguity in boolean operation and resolve if needed.

    Args:
        target_body_id: Target body ID
        tool_body_id: Tool body ID
        operation: Boolean operation type
        tnp_service: TNP v5.0 service
        parent_widget: Parent widget for dialog

    Returns:
        True to proceed with operation, False if cancelled
    """
    checker = FeatureAmbiguityChecker(tnp_service)
    report = checker.check_boolean_tool(target_body_id, tool_body_id, operation)

    if report is None:
        return True  # No ambiguity, proceed

    # For boolean, ambiguity typically means user needs to confirm
    selected_id = resolve_feature_ambiguity(report, parent_widget)

    return selected_id is not None


# Convenience functions for features
def fillet_requires_disambiguation(edge_ids: List[str]) -> bool:
    """
    Quick check if fillet might need user disambiguation.

    Args:
        edge_ids: List of selected edge IDs

    Returns:
        True if multiple edges selected (potential ambiguity)
    """
    return len(edge_ids) > 1


def chamfer_requires_disambiguation(edge_ids: List[str]) -> bool:
    """
    Quick check if chamfer might need user disambiguation.

    Args:
        edge_ids: List of selected edge IDs

    Returns:
        True if multiple edges selected (potential ambiguity)
    """
    return len(edge_ids) > 1


def boolean_requires_disambiguation(
    target_center: tuple,
    tool_center: tuple
) -> bool:
    """
    Quick check if boolean might need user disambiguation.

    Args:
        target_center: Target body center
        tool_center: Tool body center

    Returns:
        True if positions appear symmetric
    """
    checker = FeatureAmbiguityChecker(None)  # No service needed for quick check
    return checker._are_positions_symmetric(target_center, tool_center)
