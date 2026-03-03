"""
TNP v5.0 - Resolution Mixin

Provides shape resolution strategies for the ShapeNamingService.
Handles resolving ShapeIDs to current OCP geometry through multiple
fallback strategies: direct lookup, semantic matching, history tracing,
BRepFeat mapping, and geometric matching.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any, Set
from loguru import logger
from config.feature_flags import is_enabled
import time
import numpy as np

try:
    from OCP.TopoDS import TopoDS_Shape
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from OCP.TopExp import TopExp
    HAS_OCP = True
except ImportError:
    HAS_OCP = False

from .types import (
    ShapeID, ShapeRecord, ShapeType, SelectionContext,
    ResolutionResult, ResolutionMethod, ResolutionOptions,
)


@dataclass
class ValidationResult:
    """Result of batch resolution validation."""
    is_valid: bool
    issues: List[str]


class ResolutionMixin:
    """Mixin for shape resolution strategies."""

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    def resolve_shape(
        self,
        shape_id: ShapeID,
        current_solid,
        *,
        log_unresolved: bool = True,
    ) -> Optional[Any]:
        """
        Resolve a ShapeID to current geometry.

        Delegates to resolve_shape_with_method and returns only the shape,
        discarding the method string.

        Args:
            shape_id: The ShapeID to resolve.
            current_solid: The current OCP solid to resolve against.
            log_unresolved: Whether to log a warning when resolution fails.

        Returns:
            The resolved OCP TopoDS_Shape, or None if unresolved.
        """
        resolved, _method = self.resolve_shape_with_method(
            shape_id, current_solid, log_unresolved=log_unresolved,
        )
        return resolved

    def resolve_shape_with_method(
        self,
        shape_id: ShapeID,
        current_solid,
        *,
        log_unresolved: bool = True,
        resolution_options: Optional[ResolutionOptions] = None,
    ) -> Tuple[Optional[Any], str]:
        """
        Full resolution with method tracking (v5.0).

        Resolution order:
        1. Direct lookup (IsSame)
        2. Semantic matching via SelectionContext (v5.0)
        3. History tracing (BRepTools_History)
        4. BRepFeat mapping
        5. Geometric matching (center / length / area / curve_type)

        If the UUID is not in the registry, a geometry_hash fallback
        is attempted before giving up.

        Args:
            shape_id: The ShapeID to resolve.
            current_solid: The current OCP solid.
            log_unresolved: Whether to log warnings on failure.
            resolution_options: Optional ResolutionOptions overrides.

        Returns:
            Tuple of (resolved_shape_or_None, method_string).
            method_string is one of: "direct", "semantic", "geometry_hash",
            "history", "brepfeat", "geometric", "unresolved".
        """
        options = resolution_options or ResolutionOptions()

        # --- UUID not in registry: try geometry_hash fallback ---------- #
        if shape_id.uuid not in self._shapes:
            ghash = getattr(shape_id, "geometry_hash", None)
            stype = getattr(shape_id, "shape_type", None)
            if ghash and stype is not None:
                for uuid, rec in self._shapes.items():
                    sid = rec.shape_id
                    if sid.geometry_hash == ghash and sid.shape_type == stype:
                        if (
                            rec.is_valid
                            and rec.ocp_shape is not None
                            and self._shape_exists_in_solid(rec.ocp_shape, current_solid)
                        ):
                            if is_enabled("tnp_debug_logging"):
                                logger.debug(
                                    f"[TNP v5.0] Shape {shape_id.uuid[:8]} resolved "
                                    f"via geometry_hash ({ghash[:8]}) -> {uuid[:8]}"
                                )
                            return rec.ocp_shape, "geometry_hash"

            if log_unresolved:
                logger.warning(f"[TNP v5.0] Unknown ShapeID: {shape_id.uuid}")
            return None, "unresolved"

        record: ShapeRecord = self._shapes[shape_id.uuid]

        # Strategy 1: Direct lookup
        if record.is_valid and record.ocp_shape is not None:
            if self._shape_exists_in_solid(record.ocp_shape, current_solid):
                return record.ocp_shape, "direct"

        # Strategy 2: Semantic matching (v5.0)
        if (
            options.use_semantic_matching
            and getattr(record, "selection_context", None) is not None
        ):
            semantic_result = self._try_semantic_match(
                shape_id, record.selection_context, current_solid, options,
            )
            if (
                semantic_result is not None
                and getattr(semantic_result, "matched_shape", None) is not None
            ):
                return semantic_result.matched_shape, "geometric"

        # Strategy 3: History tracing
        resolved = self._trace_via_history(shape_id, current_solid)
        if resolved:
            return resolved, "history"

        # Strategy 4: BRepFeat mapping
        resolved = self._lookup_brepfeat_mapping(shape_id, current_solid)
        if resolved:
            return resolved, "brepfeat"

        # Strategy 5: Geometric matching
        resolved = self._match_geometrically(shape_id, current_solid)
        if resolved:
            return resolved, "geometric"

        if log_unresolved:
            logger.warning(
                f"[TNP v5.0] Shape {shape_id.uuid[:8]} could not be resolved"
            )
        return None, "unresolved"

    def resolve(
        self,
        shape_id: ShapeID,
        current_solid,
        options: Optional[ResolutionOptions] = None,
    ) -> ResolutionResult:
        """
        v5.0 resolution returning a ResolutionResult with confidence,
        method, and candidate information.

        Args:
            shape_id: The ShapeID to resolve.
            current_solid: The current OCP solid.
            options: Optional ResolutionOptions.

        Returns:
            ResolutionResult with resolved shape, method, and confidence.
        """
        options = options or ResolutionOptions()
        start = time.perf_counter()

        record = self.get_shape_record(shape_id.uuid)
        if (
            record is not None
            and record.ocp_shape is not None
            and self._shape_exists_in_solid(record.ocp_shape, current_solid)
        ):
            return ResolutionResult(
                shape_id=shape_id.uuid,
                resolved_shape=record.ocp_shape,
                method=ResolutionMethod.EXACT,
                confidence=1.0,
                duration_ms=(time.perf_counter() - start) * 1000,
            )

        # Try semantic matching first
        if (
            options.use_semantic_matching
            and record is not None
            and getattr(record, "selection_context", None) is not None
        ):
            semantic_result = self._try_semantic_match(
                shape_id, record.selection_context, current_solid, options,
            )
            if semantic_result is not None:
                if getattr(semantic_result, "matched_shape", None) is not None:
                    return ResolutionResult(
                        shape_id=shape_id.uuid,
                        resolved_shape=semantic_result.matched_shape,
                        method=ResolutionMethod.SEMANTIC,
                        confidence=float(getattr(semantic_result, "score", 0.0)),
                        duration_ms=(time.perf_counter() - start) * 1000,
                    )
                if getattr(semantic_result, "is_ambiguous", False):
                    candidate_ids = [
                        c.shape_id
                        for c in getattr(semantic_result, "candidates", [])
                    ]
                    return ResolutionResult(
                        shape_id=shape_id.uuid,
                        resolved_shape=None,
                        method=ResolutionMethod.SEMANTIC,
                        confidence=float(getattr(semantic_result, "score", 0.0)),
                        duration_ms=(time.perf_counter() - start) * 1000,
                        alternative_candidates=candidate_ids,
                        disambiguation_used="ambiguous_match",
                    )

        # Fallback to legacy resolution (without semantic to avoid infinite loop)
        fallback_options = ResolutionOptions(
            use_semantic_matching=False,
            use_history_tracing=options.use_history_tracing,
            require_user_confirmation=options.require_user_confirmation,
            position_tolerance=options.position_tolerance,
            angle_tolerance=options.angle_tolerance,
            enable_spatial_index=options.enable_spatial_index,
            max_candidates=options.max_candidates,
            on_failure=options.on_failure,
        )
        resolved, method = self.resolve_shape_with_method(
            shape_id,
            current_solid,
            log_unresolved=False,
            resolution_options=fallback_options,
        )

        method_map = {
            "direct": ResolutionMethod.EXACT,
            "history": ResolutionMethod.HISTORY,
            "brepfeat": ResolutionMethod.HISTORY,
            "geometric": ResolutionMethod.SEMANTIC,
            "geometry_hash": ResolutionMethod.HISTORY,
            "unresolved": ResolutionMethod.FAILED,
        }
        confidence_map = {
            "direct": 1.0,
            "history": 0.85,
            "brepfeat": 0.75,
            "geometric": 0.65,
            "geometry_hash": 0.8,
            "unresolved": 0.0,
        }

        return ResolutionResult(
            shape_id=shape_id.uuid,
            resolved_shape=resolved,
            method=method_map.get(method, ResolutionMethod.FAILED),
            confidence=confidence_map.get(method, 0.0),
            duration_ms=(time.perf_counter() - start) * 1000,
        )

    def resolve_batch(
        self,
        shape_ids: List[ShapeID],
        current_solid,
        options: Optional[ResolutionOptions] = None,
    ) -> List[ResolutionResult]:
        """
        Resolve a batch of ShapeIDs against the current solid.

        Args:
            shape_ids: List of ShapeIDs to resolve.
            current_solid: The current OCP solid.
            options: Optional ResolutionOptions.

        Returns:
            List of ResolutionResult, one per input ShapeID (same order).
        """
        results: List[ResolutionResult] = []
        for sid in shape_ids:
            results.append(self.resolve(sid, current_solid, options))
        return results

    def validate_resolutions(
        self, resolutions: List[ResolutionResult],
    ) -> ValidationResult:
        """
        Validate a batch of resolution results.

        Checks for:
        - Duplicate resolved shapes (two ShapeIDs pointing at the same geometry)
        - Confidence values outside [0.0, 1.0]
        - Failed resolutions

        Args:
            resolutions: List of ResolutionResult to validate.

        Returns:
            ValidationResult with is_valid flag and list of issue descriptions.
        """
        issues: List[str] = []

        # Duplicate detection: track resolved shape identities
        seen_shapes: Dict[int, str] = {}  # id(shape) -> first shape_id
        for res in resolutions:
            # Confidence range check
            if not (0.0 <= res.confidence <= 1.0):
                issues.append(
                    f"Shape {res.shape_id}: confidence {res.confidence} "
                    f"out of range [0.0, 1.0]"
                )

            if res.resolved_shape is None:
                if res.method != ResolutionMethod.FAILED:
                    issues.append(
                        f"Shape {res.shape_id}: resolved_shape is None but "
                        f"method is {res.method.value} (expected FAILED)"
                    )
                continue

            shape_identity = id(res.resolved_shape)
            if shape_identity in seen_shapes:
                first_id = seen_shapes[shape_identity]
                issues.append(
                    f"Duplicate: shapes {first_id} and {res.shape_id} "
                    f"resolved to the same geometry"
                )
            else:
                seen_shapes[shape_identity] = res.shape_id

        return ValidationResult(
            is_valid=len(issues) == 0,
            issues=issues,
        )

    def resolve_shape_id(
        self,
        shape_uuid: str,
        current_solid,
        *,
        log_unresolved: bool = True,
    ) -> Optional[Any]:
        """
        Convenience method for UUID-based resolution.

        Looks up the ShapeRecord by UUID, constructs the ShapeID,
        and delegates to resolve_shape.

        Args:
            shape_uuid: UUID string of the shape to resolve.
            current_solid: The current OCP solid.
            log_unresolved: Whether to log warnings on failure.

        Returns:
            The resolved OCP TopoDS_Shape, or None.
        """
        record = self.get_shape_record(shape_uuid)
        if record is None:
            if log_unresolved:
                logger.warning(f"[TNP v5.0] No record for UUID: {shape_uuid}")
            return None

        return self.resolve_shape(
            record.shape_id, current_solid, log_unresolved=log_unresolved,
        )

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _shape_exists_in_solid(self, ocp_shape, current_solid) -> bool:
        """
        Check whether *ocp_shape* is present in *current_solid* using
        an IndexedMap for correct TShape identity comparison.

        Args:
            ocp_shape: An OCP TopoDS_Shape (edge, face, etc.).
            current_solid: The solid to search in (build123d or raw OCP).

        Returns:
            True if the shape is found in the solid.
        """
        if not HAS_OCP:
            return False

        try:
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX

            # Unwrap build123d objects
            solid_shape = current_solid
            if hasattr(current_solid, "wrapped"):
                solid_shape = current_solid.wrapped

            check_shape = ocp_shape
            if hasattr(ocp_shape, "wrapped"):
                check_shape = ocp_shape.wrapped

            if solid_shape is None or check_shape is None:
                return False

            # Determine which sub-shape type to enumerate
            shape_type = check_shape.ShapeType()

            imap = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(solid_shape, shape_type, imap)

            return imap.Contains(check_shape)

        except Exception as e:
            logger.debug(f"[TNP v5.0] _shape_exists_in_solid error: {e}")
            return False

    def _match_geometrically(
        self, shape_id: ShapeID, current_solid,
    ) -> Optional[Any]:
        """
        Level 4 fallback: geometric signature matching.

        Scores candidate shapes by comparing center distance, length/area,
        and curve type against the stored geometric signature.

        Weighting:
        - center distance:  40 %
        - length / area:    30 %
        - curve_type match: 20 %
        - reserved:         10 %

        Args:
            shape_id: The ShapeID whose stored signature to match against.
            current_solid: The current OCP solid to search.

        Returns:
            Best-matching OCP shape, or None if no match exceeds threshold.
        """
        if not HAS_OCP:
            return None

        record = self._shapes.get(shape_id.uuid)
        if record is None:
            return None

        sig = record.geometric_signature
        if not sig:
            # Try to compute from the record itself
            sig = record.compute_signature()
            if not sig:
                return None

        ref_center = sig.get("center")
        if ref_center is None:
            return None

        ref_center = np.array(ref_center, dtype=np.float64)
        ref_length = sig.get("length")
        ref_area = sig.get("area")
        ref_curve_type = sig.get("curve_type")

        try:
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
            from OCP.BRepAdaptor import BRepAdaptor_Curve
            from OCP.GProp import GProp_GProps
            from OCP.BRepGProp import BRepGProp

            # Unwrap build123d
            solid_shape = current_solid
            if hasattr(current_solid, "wrapped"):
                solid_shape = current_solid.wrapped
            if solid_shape is None:
                return None

            is_edge = shape_id.shape_type == ShapeType.EDGE
            is_face = shape_id.shape_type == ShapeType.FACE

            if is_edge:
                target_type = TopAbs_EDGE
            elif is_face:
                target_type = TopAbs_FACE
            else:
                return None

            imap = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(solid_shape, target_type, imap)

            best_shape = None
            best_score = -1.0
            threshold = 0.6

            for idx in range(1, imap.Size() + 1):
                candidate = imap.FindKey(idx)
                score = self._score_candidate(
                    candidate,
                    is_edge,
                    ref_center,
                    ref_length,
                    ref_area,
                    ref_curve_type,
                )
                if score > best_score:
                    best_score = score
                    best_shape = candidate

            if best_score >= threshold:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(
                        f"[TNP v5.0] Geometric match for {shape_id.uuid[:8]} "
                        f"score={best_score:.3f}"
                    )
                return best_shape

        except Exception as e:
            logger.debug(f"[TNP v5.0] _match_geometrically error: {e}")

        return None

    def _score_candidate(
        self,
        candidate,
        is_edge: bool,
        ref_center: np.ndarray,
        ref_length: Optional[float],
        ref_area: Optional[float],
        ref_curve_type: Optional[str],
    ) -> float:
        """
        Score a candidate shape against reference geometric properties.

        Args:
            candidate: OCP TopoDS_Shape to score.
            is_edge: True if comparing edges, False if faces.
            ref_center: Reference center point as numpy array.
            ref_length: Reference edge length (edges only).
            ref_area: Reference face area (faces only).
            ref_curve_type: Reference curve type string (edges only).

        Returns:
            Score in [0.0, 1.0].
        """
        try:
            from OCP.BRepAdaptor import BRepAdaptor_Curve
            from OCP.GProp import GProp_GProps
            from OCP.BRepGProp import BRepGProp

            score = 0.0

            if is_edge:
                adaptor = BRepAdaptor_Curve(candidate)

                # Center (40%)
                u_mid = (adaptor.FirstParameter() + adaptor.LastParameter()) / 2
                pnt = adaptor.Value(u_mid)
                cand_center = np.array([pnt.X(), pnt.Y(), pnt.Z()])
                dist = np.linalg.norm(cand_center - ref_center)
                center_score = max(0.0, 1.0 - dist / 10.0)
                score += 0.4 * center_score

                # Length (30%)
                if ref_length is not None and ref_length > 1e-9:
                    props = GProp_GProps()
                    BRepGProp.LinearProperties_s(candidate, props)
                    cand_length = props.Mass()
                    length_ratio = min(cand_length, ref_length) / max(cand_length, ref_length) if max(cand_length, ref_length) > 1e-9 else 0.0
                    score += 0.3 * length_ratio
                else:
                    score += 0.3  # No ref length; give benefit of doubt

                # Curve type (20%)
                if ref_curve_type is not None:
                    cand_curve_type = str(adaptor.GetType())
                    if cand_curve_type == ref_curve_type:
                        score += 0.2

                # Reserved (10%) - always granted
                score += 0.1

            else:
                # Face
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(candidate, props)
                cand_cm = props.CentreOfMass()
                cand_center = np.array([cand_cm.X(), cand_cm.Y(), cand_cm.Z()])

                # Center (40%)
                dist = np.linalg.norm(cand_center - ref_center)
                center_score = max(0.0, 1.0 - dist / 10.0)
                score += 0.4 * center_score

                # Area (30%)
                if ref_area is not None and ref_area > 1e-9:
                    cand_area = props.Mass()
                    area_ratio = min(cand_area, ref_area) / max(cand_area, ref_area) if max(cand_area, ref_area) > 1e-9 else 0.0
                    score += 0.3 * area_ratio
                else:
                    score += 0.3

                # No curve_type for faces; grant those 20% + 10% reserved
                score += 0.3

            return score

        except Exception:
            return 0.0

    def _try_semantic_match(
        self,
        shape_id: ShapeID,
        context: SelectionContext,
        current_solid,
        options: ResolutionOptions,
    ) -> Optional[Any]:
        """
        Attempt semantic matching via the SemanticMatcher.

        Uses selection context (position, adjacent shapes, feature context)
        to find the best matching shape in the current solid.

        Args:
            shape_id: The ShapeID to resolve.
            context: The original SelectionContext.
            current_solid: The current OCP solid.
            options: ResolutionOptions controlling tolerance etc.

        Returns:
            Semantic match result (with .matched_shape and .score attributes),
            or None if no matcher is available or matching failed.
        """
        matcher = getattr(self, "_semantic_matcher", None)
        if matcher is None:
            return None

        try:
            result = matcher.match(
                shape_id=shape_id,
                context=context,
                current_solid=current_solid,
                options=options,
            )
            return result
        except Exception as e:
            logger.debug(f"[TNP v5.0] Semantic matching failed: {e}")
            return None
