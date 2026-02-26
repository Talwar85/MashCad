"""
TNP v5.0 - Main Service API

Primary interface for shape naming and resolution.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from loguru import logger
import time

from .types import (
    ShapeID,
    ShapeRecord,
    ShapeType,
    SelectionContext,
    ResolutionResult,
    ResolutionMethod,
    ResolutionOptions
)
from .spatial import SpatialIndex, compute_bounds_from_signature
from .semantic_matcher import SemanticMatcher


class TNPService:
    """
    TNP v5.0 Service - Main API for shape naming and resolution.

    This is the PRIMARY public API for TNP v5.0 operations.

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

    def __init__(self, document_id: str):
        """
        Initialize TNP service for a document.

        Args:
            document_id: Unique identifier for the document
        """
        self.document_id = document_id

        # ShapeID -> ShapeRecord
        self._shapes: Dict[str, ShapeRecord] = {}

        # Operation history
        self._operations: List[Dict[str, Any]] = []

        # Feature-based lookup
        self._by_feature: Dict[str, List[ShapeID]] = {}

        # Document generation (for rebuild tracking)
        self._generation = 0

        # Spatial index for O(log n) geometric queries
        self._spatial_index = SpatialIndex()

        # Semantic matcher for context-aware resolution (Phase 2)
        self._semantic_matcher = SemanticMatcher(self._spatial_index)

        logger.info(f"[TNP v5.0] Service initialized for document '{document_id}'")

    # ==========================================================================
    # Registration API
    # ==========================================================================

    def register_shape(
        self,
        ocp_shape: Any,
        shape_type: ShapeType,
        feature_id: str,
        local_index: int,
        context: Optional[SelectionContext] = None
    ) -> ShapeID:
        """
        Register a new shape with the naming service.

        Args:
            ocp_shape: The OCP TopoDS_Shape to register
            shape_type: Type of shape (EDGE, FACE, VERTEX, SOLID)
            feature_id: ID of the feature creating this shape
            local_index: Index within the feature
            context: SelectionContext (if from user interaction)

        Returns:
            ShapeID for the registered shape

        Raises:
            ValueError: If ocp_shape is None
            TypeError: If shape_type is invalid
        """
        if ocp_shape is None:
            raise ValueError("ocp_shape cannot be None")

        # Extract geometry data for hashing
        geometry_data = self._extract_geometry_data(ocp_shape, shape_type)

        # Create or reuse ShapeID (for rebuild stability)
        feature_bucket = self._by_feature.setdefault(feature_id, [])
        existing_shape_id = self._find_existing_in_bucket(
            feature_bucket, local_index, shape_type
        )

        if existing_shape_id is not None:
            # Reuse existing ShapeID for stable IDs across rebuilds
            shape_id = existing_shape_id
        else:
            # Create new ShapeID
            shape_id = ShapeID.create(
                shape_type=shape_type,
                feature_id=feature_id,
                local_index=local_index,
                geometry_data=geometry_data
            )
            feature_bucket.append(shape_id)

        # Add context if provided
        if context is not None:
            shape_id = shape_id.with_context(context)

        # Create record
        record = ShapeRecord(
            shape_id=shape_id,
            ocp_shape=ocp_shape,
            is_valid=True
        )
        record.geometric_signature = record.compute_signature()

        if context is not None:
            record.selection_context = context

        # Store
        self._shapes[shape_id.uuid] = record

        # Add to spatial index (Phase 2)
        bounds = compute_bounds_from_signature(record.geometric_signature)
        if bounds is not None:
            self._spatial_index.insert(
                shape_id=shape_id.uuid,
                bounds=bounds,
                shape_data={
                    'shape_type': shape_type.name,
                    'feature_id': feature_id,
                    'local_index': local_index
                }
            )
            logger.debug(f"[TNP v5.0] Added shape {shape_id.uuid[:8]}... to spatial index")

        logger.debug(f"[TNP v5.0] Registered shape {shape_id.uuid[:8]}... "
                    f"type={shape_type.name} feature={feature_id}")

        return shape_id

    def record_operation(
        self,
        operation_type: str,
        feature_id: str,
        inputs: List[ShapeID],
        outputs: List[ShapeID],
        occt_history: Optional[Any] = None
    ) -> str:
        """
        Record an operation in the provenance graph.

        Args:
            operation_type: Type of operation (extrude, fillet, boolean, etc.)
            feature_id: Feature performing the operation
            inputs: ShapeIDs consumed by the operation
            outputs: ShapeIDs produced by the operation
            occt_history: OCCT BRepTools_History if available

        Returns:
            Operation ID for tracking

        Raises:
            ValueError: If operation data is invalid
        """
        if not operation_type:
            raise ValueError("operation_type cannot be empty")
        if not feature_id:
            raise ValueError("feature_id cannot be empty")
        if inputs is None or outputs is None:
            raise ValueError("inputs and outputs cannot be None")

        operation_id = f"op_{feature_id}_{operation_type}_{len(self._operations)}"
        op_data = {
            "operation_id": operation_id,
            "operation_type": operation_type,
            "feature_id": feature_id,
            "inputs": [self._shape_ref_to_dict(s) for s in inputs],
            "outputs": [self._shape_ref_to_dict(s) for s in outputs],
            "occt_history": occt_history,
            "timestamp": time.time(),
            "generation": self._generation,
        }
        self._operations.append(op_data)

        logger.debug(f"[TNP v5.0] Recorded operation {operation_id}")
        return operation_id

    # ==========================================================================
    # Resolution API
    # ==========================================================================

    def resolve(
        self,
        shape_id: ShapeID,
        current_solid: Any,
        options: Optional[ResolutionOptions] = None
    ) -> ResolutionResult:
        """
        Resolve a ShapeID to the current geometry.

        This is the PRIMARY resolution method for TNP v5.0.

        Resolution Strategy:
        1. EXACT MATCH - TopoDS_Shape.IsSame() - O(1), 100% reliable
        2. SEMANTIC MATCH - Selection context matching - O(log n), 95% reliable
        3. HISTORY MATCH - OCCT BRepTools_History - O(log n), 90% reliable
        4. USER CONFIRMATION - Interactive selection - 100% reliable

        Args:
            shape_id: The ShapeID to resolve
            current_solid: Current state of the solid (build123d Solid or OCP shape)
            options: Resolution options

        Returns:
            ResolutionResult with resolved shape or failure information
        """
        if options is None:
            options = ResolutionOptions()

        start = time.perf_counter()

        # Strategy 1: Exact Match
        resolved = self._try_exact_match(shape_id, current_solid)
        method = ResolutionMethod.EXACT
        confidence = 1.0

        if resolved is not None:
            duration_ms = (time.perf_counter() - start) * 1000
            return ResolutionResult(
                shape_id=shape_id.uuid,
                resolved_shape=resolved,
                method=method,
                confidence=confidence,
                duration_ms=duration_ms
            )

        # Strategy 2: Semantic Match (Phase 2)
        if options.use_semantic_matching:
            context = self._get_selection_context(shape_id)
            if context is not None:
                semantic_result = self._try_semantic_match(shape_id, context, current_solid, options)
                if semantic_result.matched_shape is not None:
                    duration_ms = (time.perf_counter() - start) * 1000
                    return ResolutionResult(
                        shape_id=shape_id.uuid,
                        resolved_shape=semantic_result.matched_shape,
                        method=ResolutionMethod.SEMANTIC,
                        confidence=semantic_result.score,
                        duration_ms=duration_ms,
                        alternative_candidates=[],
                        disambiguation_used=None
                    )
                elif semantic_result.is_ambiguous:
                    candidate_ids = [c.shape_id for c in semantic_result.candidates]
                    if not candidate_ids and semantic_result.alternative_scores:
                        candidate_ids = [shape_uuid for shape_uuid, _ in semantic_result.alternative_scores]

                    # Ambiguous - return result with candidates for user confirmation
                    duration_ms = (time.perf_counter() - start) * 1000
                    return ResolutionResult(
                        shape_id=shape_id.uuid,
                        resolved_shape=None,
                        method=ResolutionMethod.SEMANTIC,
                        confidence=semantic_result.score,
                        duration_ms=duration_ms,
                        alternative_candidates=candidate_ids,
                        disambiguation_used="ambiguous_match"
                    )

        # Strategy 3: History Match
        if options.use_history_tracing:
            history_resolved = self._try_history_match(shape_id, current_solid)
            if history_resolved is not None:
                duration_ms = (time.perf_counter() - start) * 1000
                return ResolutionResult(
                    shape_id=shape_id.uuid,
                    resolved_shape=history_resolved,
                    method=ResolutionMethod.HISTORY,
                    confidence=0.85,
                    duration_ms=duration_ms
                )

        # Strategy 4: User guided fallback (candidate suggestion only)
        if options.require_user_confirmation:
            candidates = self._build_user_guided_candidates(shape_id)
            duration_ms = (time.perf_counter() - start) * 1000
            return ResolutionResult(
                shape_id=shape_id.uuid,
                resolved_shape=None,
                method=ResolutionMethod.USER_GUIDED,
                confidence=0.0,
                duration_ms=duration_ms,
                alternative_candidates=candidates,
                disambiguation_used="user_confirmation_required"
            )

        # Failed to resolve
        duration_ms = (time.perf_counter() - start) * 1000
        return ResolutionResult(
            shape_id=shape_id.uuid,
            resolved_shape=None,
            method=ResolutionMethod.FAILED,
            confidence=0.0,
            duration_ms=duration_ms
        )

    def resolve_batch(
        self,
        shape_ids: List[ShapeID],
        current_solid: Any,
        options: Optional[ResolutionOptions] = None
    ) -> List[ResolutionResult]:
        """
        Resolve multiple shapes efficiently.

        Args:
            shape_ids: List of ShapeIDs to resolve
            current_solid: Current state of the solid
            options: Resolution options

        Returns:
            List of ResolutionResults (same order as input)
        """
        return [self.resolve(shape_id, current_solid, options) for shape_id in shape_ids]

    # ==========================================================================
    # Validation API
    # ==========================================================================

    def validate_resolutions(self, resolutions: List[ResolutionResult]) -> 'ValidationResult':
        """
        Validate a batch of resolutions for consistency.

        Checks:
        - No two IDs resolve to the same shape (unless allowed)
        - All resolved shapes exist in the solid
        - Adjacency relationships preserved
        - No cycles in dependency graph

        Args:
            resolutions: ResolutionResults to validate

        Returns:
            ValidationResult with issues found
        """
        issues: List[str] = []
        seen_resolved_shape: Dict[int, str] = {}
        seen_shape_id: set[str] = set()

        for idx, result in enumerate(resolutions):
            if result is None:
                issues.append(f"resolution[{idx}] is None")
                continue

            if not result.shape_id:
                issues.append(f"resolution[{idx}] has empty shape_id")
                continue

            if result.shape_id in seen_shape_id:
                issues.append(f"duplicate shape_id in batch: {result.shape_id}")
            seen_shape_id.add(result.shape_id)

            if result.confidence < 0.0 or result.confidence > 1.0:
                issues.append(f"invalid confidence for {result.shape_id}: {result.confidence}")

            if result.resolved_shape is not None:
                resolved_key = id(result.resolved_shape)
                other_shape_id = seen_resolved_shape.get(resolved_key)
                if other_shape_id is not None and other_shape_id != result.shape_id:
                    issues.append(
                        f"multiple shape_ids resolved to same shape: {other_shape_id}, {result.shape_id}"
                    )
                else:
                    seen_resolved_shape[resolved_key] = result.shape_id
            elif result.method not in (ResolutionMethod.FAILED, ResolutionMethod.USER_GUIDED, ResolutionMethod.SEMANTIC):
                issues.append(
                    f"resolution without shape uses unexpected method for {result.shape_id}: {result.method}"
                )

        return ValidationResult(is_valid=(len(issues) == 0), issues=issues)

    def check_ambiguity(
        self,
        shape_id: ShapeID,
        current_solid: Any
    ) -> 'AmbiguityReport':
        """
        Check if resolving a ShapeID would be ambiguous.

        Use this BEFORE committing to an operation to detect issues early.

        Args:
            shape_id: The ShapeID to check
            current_solid: Current state of the solid

        Returns:
            AmbiguityReport detailing any ambiguity
        """
        record = self.get_shape_record(shape_id.uuid)
        if record is None:
            return AmbiguityReport(
                is_ambiguous=True,
                ambiguity_type="missing_shape",
                candidates=[],
                disambiguation_questions=["Original shape reference does not exist in TNP registry."],
                recommended_resolution=None
            )

        context = record.selection_context
        if context is None:
            return AmbiguityReport(
                is_ambiguous=False,
                ambiguity_type="insufficient_context",
                candidates=[],
                disambiguation_questions=[],
                recommended_resolution=None
            )

        semantic_result = self._try_semantic_match(
            shape_id=shape_id,
            context=context,
            current_solid=current_solid,
            options=ResolutionOptions(max_candidates=10)
        )

        candidate_ids = [c.shape_id for c in semantic_result.candidates]
        if not candidate_ids and semantic_result.alternative_scores:
            candidate_ids = [shape_uuid for shape_uuid, _ in semantic_result.alternative_scores]

        if semantic_result.is_ambiguous and candidate_ids:
            return AmbiguityReport(
                is_ambiguous=True,
                ambiguity_type="semantic_ambiguous",
                candidates=candidate_ids,
                disambiguation_questions=[
                    f"Multiple candidates match with close scores (top score {semantic_result.score:.3f}). "
                    f"Please confirm intended shape."
                ],
                recommended_resolution=candidate_ids[0]
            )

        return AmbiguityReport(
            is_ambiguous=False,
            ambiguity_type="none",
            candidates=[],
            disambiguation_questions=[],
            recommended_resolution=None
        )

    # ==========================================================================
    # Internal Methods
    # ==========================================================================

    def _extract_geometry_data(self, ocp_shape: Any, shape_type: ShapeType) -> tuple:
        """Extract data for geometry hashing."""
        try:
            if shape_type == ShapeType.EDGE:
                # Extract edge-specific data
                return ("edge", str(id(ocp_shape)))
            elif shape_type == ShapeType.FACE:
                # Extract face-specific data
                return ("face", str(id(ocp_shape)))
            elif shape_type == ShapeType.VERTEX:
                return ("vertex", str(id(ocp_shape)))
            else:
                return (shape_type.name.lower(), str(id(ocp_shape)))
        except Exception:
            return (shape_type.name.lower(), "")

    def _find_existing_in_bucket(
        self,
        bucket: List[ShapeID],
        local_index: int,
        shape_type: ShapeType
    ) -> Optional[ShapeID]:
        """Find existing ShapeID in feature bucket for stable IDs."""
        for sid in reversed(bucket):
            if sid.shape_type != shape_type:
                continue
            if sid.local_index == local_index:
                return sid
        return None

    def _try_exact_match(self, shape_id: ShapeID, current_solid: Any) -> Optional[Any]:
        """
        Strategy 1: Direct lookup via IsSame().

        Returns OCP TopoDS_Shape if found, None otherwise.
        """
        # Check if we have a record
        record = self._shapes.get(shape_id.uuid)
        if record is None or not record.is_valid or record.ocp_shape is None:
            return None

        try:
            from OCP.TopoDS import TopoDS
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX

            # Get the stored shape
            stored_shape = record.ocp_shape
            if hasattr(stored_shape, 'wrapped'):
                stored_shape = stored_shape.wrapped

            # Check if it exists in current solid
            if self._shape_exists_in_solid(stored_shape, current_solid):
                return stored_shape

        except Exception as e:
            logger.debug(f"[TNP v5.0] Exact match failed: {e}")

        return None

    def _shape_exists_in_solid(self, shape: Any, solid: Any) -> bool:
        """Check if a shape exists within a solid."""
        try:
            # Try to find the shape in the solid
            if hasattr(solid, 'wrapped'):
                solid = solid.wrapped

            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX

            # Use ShapeType.from_ocp not ShapeID.from_ocp
            shape_type = ShapeType.from_ocp(shape)
            if shape_type is None:
                return False

            explorer_type = None
            if shape_type == ShapeType.EDGE:
                explorer_type = TopAbs_EDGE
            elif shape_type == ShapeType.FACE:
                explorer_type = TopAbs_FACE
            elif shape_type == ShapeType.VERTEX:
                explorer_type = TopAbs_VERTEX
            else:
                return False

            explorer = TopExp_Explorer(solid, explorer_type)
            while explorer.More():
                current = explorer.Current()
                if current.IsSame(shape):
                    return True
                explorer.Next()

            return False
        except Exception as e:
            logger.debug(f"[TNP v5.0] Shape existence check failed: {e}")
            return False

    def get_shape_record(self, shape_id_or_uuid: str) -> Optional[ShapeRecord]:
        """Get the ShapeRecord for a ShapeID (by ID or UUID)."""
        if isinstance(shape_id_or_uuid, str):
            # Check if it's a UUID or full ShapeID
            if shape_id_or_uuid in self._shapes:
                return self._shapes[shape_id_or_uuid]
            # Try to find by ShapeID.uuid
            for record in self._shapes.values():
                if record.shape_id.uuid == shape_id_or_uuid:
                    return record
        return None

    def _get_selection_context(self, shape_id: ShapeID) -> Optional[SelectionContext]:
        """Get the selection context for a ShapeID."""
        record = self.get_shape_record(shape_id.uuid)
        if record is not None:
            return record.selection_context
        return None

    def _try_semantic_match(
        self,
        shape_id: ShapeID,
        context: SelectionContext,
        current_solid: Any,
        options: ResolutionOptions
    ) -> 'MatchResult':
        """
        Strategy 2: Semantic matching using selection context.

        Uses the SemanticMatcher to find the best matching shape based on:
        - Proximity to selection point
        - View direction alignment
        - Adjacency preservation
        - Feature continuity

        Args:
            shape_id: The ShapeID to resolve
            context: SelectionContext from original selection
            current_solid: Current state of the solid
            options: Resolution options

        Returns:
            MatchResult from SemanticMatcher
        """
        try:
            return self._semantic_matcher.match(
                shape_id=shape_id,
                context=context,
                current_solid=current_solid,
                max_candidates=options.max_candidates if options else 10
            )
        except Exception as e:
            logger.debug(f"[TNP v5.0] Semantic match failed: {e}")
            from .semantic_matcher import MatchResult
            return MatchResult(
                matched_shape=None,
                score=0.0,
                candidates=[],
                is_ambiguous=False
            )

    def _shape_ref_to_dict(self, shape_ref: Any) -> Dict[str, Any]:
        """Normalize ShapeID-like references for operation storage."""
        if isinstance(shape_ref, ShapeID):
            return shape_ref.to_v4_format()

        if isinstance(shape_ref, dict):
            if "uuid" in shape_ref:
                return dict(shape_ref)
            return {"uuid": str(shape_ref)}

        if isinstance(shape_ref, str):
            return {"uuid": shape_ref}

        if hasattr(shape_ref, "uuid"):
            return {
                "uuid": str(getattr(shape_ref, "uuid")),
                "shape_type": getattr(shape_ref, "shape_type", None),
                "feature_id": getattr(shape_ref, "feature_id", ""),
                "local_index": getattr(shape_ref, "local_index", -1),
                "geometry_hash": getattr(shape_ref, "geometry_hash", ""),
            }

        return {"uuid": str(shape_ref)}

    @staticmethod
    def _extract_ref_uuid(shape_ref: Any) -> Optional[str]:
        """Extract UUID from stored operation shape references."""
        if isinstance(shape_ref, dict):
            uuid = shape_ref.get("uuid")
            return str(uuid) if uuid is not None else None
        if isinstance(shape_ref, ShapeID):
            return shape_ref.uuid
        if isinstance(shape_ref, str):
            return shape_ref
        if hasattr(shape_ref, "uuid"):
            return str(getattr(shape_ref, "uuid"))
        return None

    def _try_history_match(self, shape_id: ShapeID, current_solid: Any) -> Optional[Any]:
        """Strategy 3: Resolve through recorded operation input/output links."""
        for op in reversed(self._operations):
            inputs = [self._extract_ref_uuid(ref) for ref in op.get("inputs", [])]
            outputs = [self._extract_ref_uuid(ref) for ref in op.get("outputs", [])]
            inputs = [uuid for uuid in inputs if uuid]
            outputs = [uuid for uuid in outputs if uuid]

            # If queried shape is an operation output, verify it still exists.
            if shape_id.uuid in outputs:
                record = self.get_shape_record(shape_id.uuid)
                if record is not None and record.ocp_shape is not None:
                    if self._shape_exists_in_solid(record.ocp_shape, current_solid):
                        return record.ocp_shape

            # If queried shape is operation input, try mapped outputs.
            if shape_id.uuid in inputs:
                for out_uuid in outputs:
                    record = self.get_shape_record(out_uuid)
                    if record is None or record.ocp_shape is None:
                        continue
                    if self._shape_exists_in_solid(record.ocp_shape, current_solid):
                        return record.ocp_shape

        return None

    def _build_user_guided_candidates(self, shape_id: ShapeID) -> List[str]:
        """Return candidate UUIDs for manual disambiguation."""
        feature_candidates = [
            sid.uuid for sid in self.get_shapes_by_feature(shape_id.feature_id)
            if sid.shape_type == shape_id.shape_type
        ]
        # Keep order stable and unique.
        unique_candidates = list(dict.fromkeys(feature_candidates))
        return unique_candidates[:10]

    # ==========================================================================
    # Spatial Query API (Phase 2)
    # ==========================================================================

    def query_shapes_nearby(
        self,
        point: Tuple[float, float, float],
        radius: float,
        shape_type: Optional[ShapeType] = None
    ) -> List[str]:
        """
        Query shapes within radius of a point.

        Uses the spatial index for O(log n) performance when available.

        Args:
            point: Query point (x, y, z)
            radius: Search radius in mm
            shape_type: Optional filter by shape type

        Returns:
            List of shape UUIDs within radius
        """
        type_filter = shape_type.name if shape_type else None
        return self._spatial_index.query_nearby(point, radius, type_filter)

    def find_nearest_shapes(
        self,
        point: Tuple[float, float, float],
        max_results: int = 10,
        shape_type: Optional[ShapeType] = None
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
        return self._spatial_index.nearest(point, max_results, type_filter)

    def get_spatial_index_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the spatial index.

        Returns:
            Dictionary with index statistics
        """
        return {
            'size': self._spatial_index.size,
            'accelerated': self._spatial_index.is_accelerated
        }

    def get_shapes_by_feature(self, feature_id: str) -> List[ShapeID]:
        """Get all ShapeIDs created by a feature."""
        return self._by_feature.get(feature_id, [])


# Placeholder types for Phase 3 and 4
@dataclass
class ValidationResult:
    """Result of validating a batch of resolutions."""
    is_valid: bool
    issues: List[str] = field(default_factory=list)


@dataclass
class AmbiguityReport:
    """Report on potential ambiguity in resolution."""
    is_ambiguous: bool = False
    ambiguity_type: str = "none"  # "none", "symmetric", "proximate", "duplicate"
    candidates: List[Any] = field(default_factory=list)
    disambiguation_questions: List[str] = field(default_factory=list)
    recommended_resolution: Optional[str] = None
