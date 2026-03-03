"""
TNP v5.0 - Main Service API

Mixin-based TNPService combining:
- RegistryMixin: shape registration, seeding, spatial index management
- ResolutionMixin: multi-strategy shape resolution
- HistoryMixin: operation tracking, history-based tracing
- LookupMixin: shape lookup, health reports, statistics
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from loguru import logger
from config.feature_flags import is_enabled
import numpy as np

from .types import (
    ShapeID,
    ShapeRecord,
    ShapeType,
    SelectionContext,
    ResolutionResult,
    ResolutionMethod,
    ResolutionOptions,
)
from .spatial import SpatialIndex
from .semantic_matcher import SemanticMatcher

from .registry_mixin import RegistryMixin
from .resolution_mixin import ResolutionMixin, ValidationResult
from .history_mixin import HistoryMixin, OperationRecord
from .lookup_mixin import LookupMixin


class TNPService(RegistryMixin, ResolutionMixin, HistoryMixin, LookupMixin):
    """
    TNP v5.0 Service - Single Source of Truth for shape naming.

    Combines all TNP functionality via mixins:
    - RegistryMixin: register_shape, seed_shape, invalidate_feature, compact
    - ResolutionMixin: resolve, resolve_shape, resolve_batch, validate_resolutions
    - HistoryMixin: record_operation, track_brepfeat_operation, track_fillet_operation, ...
    - LookupMixin: find_shape_id_by_edge/face, get_shape_record, check_ambiguity, get_health_report

    Usage:
        tnp = TNPService(document_id="my_document")

        # Register a shape
        shape_id = tnp.register_shape(
            ocp_shape=edge.wrapped,
            shape_type=ShapeType.EDGE,
            feature_id="fillet_1",
            local_index=0,
            context=selection_context
        )

        # Resolve later
        result = tnp.resolve(shape_id, current_solid)
    """

    def __init__(self, document_id: str = ""):
        """
        Initialize TNP service for a document.

        Args:
            document_id: Unique identifier for the document
        """
        self.document_id = str(document_id or "")

        # ShapeID.uuid -> ShapeRecord
        self._shapes: Dict[str, ShapeRecord] = {}

        # Operation history (OperationRecord instances)
        self._operations: List[OperationRecord] = []

        # Feature-based lookup: feature_id -> [ShapeID]
        self._by_feature: Dict[str, List[ShapeID]] = {}

        # Document generation counter (for rebuild tracking)
        self._generation: int = 0

        # Legacy spatial index: ShapeType -> [(center_array, ShapeID)]
        self._spatial_index: Dict[ShapeType, List[Tuple[np.ndarray, ShapeID]]] = {
            ShapeType.EDGE: [],
            ShapeType.FACE: [],
            ShapeType.VERTEX: [],
        }

        # Semantic spatial index (R-tree based)
        self._semantic_spatial_index = SpatialIndex()

        # Semantic matcher for context-aware resolution
        self._semantic_matcher = SemanticMatcher(self._semantic_spatial_index)

        if is_enabled("tnp_debug_logging"):
            logger.info(
                f"[TNP v5.0] Service initialized for document '{self.document_id}'"
            )

    # ======================================================================
    # Spatial Query Convenience API
    # ======================================================================

    def query_shapes_nearby(
        self,
        point: Tuple[float, float, float],
        radius: float,
        shape_type: Optional[ShapeType] = None,
    ) -> List[str]:
        """
        Query shapes within radius of a point using the semantic spatial index.

        Args:
            point: Query point (x, y, z)
            radius: Search radius in mm
            shape_type: Optional filter by shape type

        Returns:
            List of shape UUIDs within radius
        """
        type_filter = shape_type.name if shape_type else None
        return self._semantic_spatial_index.query_nearby(point, radius, type_filter)

    def find_nearest_shapes(
        self,
        point: Tuple[float, float, float],
        max_results: int = 10,
        shape_type: Optional[ShapeType] = None,
    ) -> List[str]:
        """
        Find nearest shapes to a point.

        Args:
            point: Query point (x, y, z)
            max_results: Maximum number of results
            shape_type: Optional filter by shape type

        Returns:
            List of shape UUIDs, sorted by distance
        """
        type_filter = shape_type.name if shape_type else None
        return self._semantic_spatial_index.nearest(point, max_results, type_filter)

    def get_spatial_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the semantic spatial index."""
        return {
            "size": self._semantic_spatial_index.size,
            "accelerated": self._semantic_spatial_index.is_accelerated,
        }


# Backward-compatibility alias
ShapeNamingService = TNPService


@dataclass
class AmbiguityReport:
    """Report on potential ambiguity in resolution."""

    is_ambiguous: bool = False
    ambiguity_type: str = "none"
    candidates: List[Any] = field(default_factory=list)
    disambiguation_questions: List[str] = field(default_factory=list)
    recommended_resolution: Optional[str] = None
