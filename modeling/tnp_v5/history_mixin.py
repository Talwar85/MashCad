"""
TNP v5.0 - History Mixin

Operation tracking and history-based shape tracing.
Extracted from the monolithic ShapeNamingService (v4.0) as part of
the TNP v4.0 -> v5.0 migration.
"""

from typing import Dict, List, Optional, Tuple, Any, Set
from uuid import uuid4
from loguru import logger
from config.feature_flags import is_enabled
import time
import numpy as np

try:
    from OCP.TopoDS import TopoDS_Shape, TopoDS_Edge, TopoDS_Face
    from OCP.BRepTools import BRepTools_History
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer, TopExp
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape
    HAS_OCP = True
except ImportError:
    HAS_OCP = False

from .types import ShapeID, ShapeRecord, ShapeType


class OperationRecord:
    """
    A recorded operation in the provenance graph with input/output shapes.

    Tracks what happened during a modeling operation (boolean, extrude,
    fillet, etc.) including OCCT history and manual shape mappings.
    """

    def __init__(self, operation_type: str = "", feature_id: str = "",
                 input_shape_ids: List[ShapeID] = None,
                 output_shape_ids: List[ShapeID] = None,
                 occt_history: Optional[Any] = None,
                 manual_mappings: Dict[str, List[str]] = None,
                 metadata: Dict[str, Any] = None,
                 operation_id: str = None):
        self.operation_id = operation_id or str(uuid4())[:8]
        self.operation_type = operation_type
        self.feature_id = feature_id
        self.input_shape_ids = input_shape_ids or []
        self.output_shape_ids = output_shape_ids or []
        self.occt_history = occt_history
        self.manual_mappings = manual_mappings or {}
        self.metadata = metadata or {}
        self.timestamp = time.time()


class HistoryMixin:
    """Mixin for operation tracking and history-based shape tracing.

    Provides methods for:
    - Recording operations in the provenance graph
    - Tracing shapes through operation history (Level 2 resolution)
    - BRepFeat manual mapping lookup (Level 3 resolution)
    - Batch updating ShapeIDs from OCCT History
    - Tracking BRepFeat, fillet, chamfer, draft, and sketch extrude operations

    Accesses from the composing class:
    - self._shapes: Dict[str, ShapeRecord]
    - self._operations: List[OperationRecord]
    - self._spatial_index
    - self._by_feature: Dict[str, List[ShapeID]]
    - self.register_shape()
    - self._shape_exists_in_solid()
    - self.find_shape_id_by_edge()
    - self.find_shape_id_by_face()
    """

    # ==========================================================================
    # Operation Recording
    # ==========================================================================

    def record_operation(self, operation: OperationRecord) -> None:
        """
        Store an operation in the provenance graph.

        Deduplicates by (feature_id, operation_type): rebuilds execute the
        same feature multiple times, so we keep only the latest record for
        each combination.

        Args:
            operation: The OperationRecord to store.
        """
        self._operations = [
            op for op in self._operations
            if not (
                op.feature_id == operation.feature_id
                and op.operation_type == operation.operation_type
            )
        ]
        self._operations.append(operation)
        if is_enabled("tnp_debug_logging"):
            logger.debug(
                f"Operation recorded: {operation.operation_type} "
                f"({len(operation.input_shape_ids)} in -> "
                f"{len(operation.output_shape_ids)} out)"
            )

    def get_last_operation(self) -> Optional[OperationRecord]:
        """Return the most recently recorded operation, or None."""
        return self._operations[-1] if self._operations else None

    # ==========================================================================
    # History Tracing (Level 2 Resolution)
    # ==========================================================================

    def _trace_via_history(self, shape_id: ShapeID,
                           current_solid: Any) -> Optional[Any]:
        """
        Level 2 resolution: trace a shape through the operation graph.

        Follows the chain via manual_mappings and occt_history in
        chronological order. Self-healing: updates the ShapeRecord when
        the resolved shape is found in the current solid.

        Args:
            shape_id: The ShapeID to resolve.
            current_solid: The current state of the solid.

        Returns:
            The resolved OCP TopoDS_Shape, or None if tracing fails.
        """
        if not self._operations or shape_id.uuid not in self._shapes:
            return None

        try:
            base_record = self._shapes.get(shape_id.uuid)
            candidate_shape = base_record.ocp_shape if base_record is not None else None
            candidate_uuid = shape_id.uuid

            if candidate_shape is None:
                return None

            # Walk chronologically: follow the same evolution direction
            # as the feature history.
            for op in self._operations:
                had_mapping = False
                next_shape = None
                next_uuid = None

                # --- Check manual_mappings first ---
                if op.manual_mappings and candidate_uuid in op.manual_mappings:
                    had_mapping = True
                    mapped_uuids = op.manual_mappings.get(candidate_uuid, [])

                    # Pass 1: Prefer same-type mappings (Edge->Edge, Face->Face).
                    # BRepFeat stores both FACE and EDGE in manual_mappings for
                    # a source Edge. We must prefer Edge matches to avoid
                    # returning a Face when the caller expects an Edge.
                    for mapped_uuid in mapped_uuids:
                        mapped_record = self._shapes.get(mapped_uuid)
                        if mapped_record is None or mapped_record.ocp_shape is None:
                            continue
                        if mapped_record.shape_id.shape_type != shape_id.shape_type:
                            continue  # Skip cross-type in first pass
                        mapped_shape = mapped_record.ocp_shape
                        if self._shape_exists_in_solid(mapped_shape, current_solid):
                            return mapped_shape
                        if next_shape is None:
                            next_shape = mapped_shape
                            next_uuid = mapped_uuid

                    # Pass 2: Accept cross-type mappings as fallback.
                    for mapped_uuid in mapped_uuids:
                        mapped_record = self._shapes.get(mapped_uuid)
                        if mapped_record is None or mapped_record.ocp_shape is None:
                            continue
                        if mapped_record.shape_id.shape_type == shape_id.shape_type:
                            continue  # Already checked in pass 1
                        mapped_shape = mapped_record.ocp_shape
                        if self._shape_exists_in_solid(mapped_shape, current_solid):
                            return mapped_shape
                        if next_shape is None:
                            next_shape = mapped_shape
                            next_uuid = mapped_uuid

                # --- Check OCCT history ---
                if op.occt_history is not None and HAS_OCP and candidate_shape is not None:
                    history_outputs = self._history_outputs_for_shape(
                        op.occt_history, candidate_shape
                    )
                    if history_outputs:
                        had_mapping = True
                        for mapped_shape in history_outputs:
                            if self._shape_exists_in_solid(mapped_shape, current_solid):
                                # Self-healing: update record to the last
                                # successfully resolved geometry.
                                if base_record is not None:
                                    base_record.ocp_shape = mapped_shape
                                    base_record.is_valid = True
                                    base_record.geometric_signature = (
                                        base_record.compute_signature()
                                    )
                                return mapped_shape
                        if next_shape is None:
                            next_shape = history_outputs[0]

                # Advance the candidate for the next iteration.
                if had_mapping and next_shape is not None:
                    candidate_shape = next_shape
                    if next_uuid is not None:
                        candidate_uuid = next_uuid

        except Exception as e:
            logger.debug(f"History tracing failed: {e}")

        return None

    # ==========================================================================
    # BRepFeat Mapping Lookup (Level 3 Resolution)
    # ==========================================================================

    def _lookup_brepfeat_mapping(self, shape_id: ShapeID,
                                  current_solid: Any) -> Optional[Any]:
        """
        Level 3 resolution: search BRepFeat manual_mappings.

        For Push/Pull operations: find which new edge corresponds to the
        old one by matching geometric signatures against the current solid.

        Args:
            shape_id: The ShapeID to resolve.
            current_solid: The current state of the solid.

        Returns:
            The resolved OCP TopoDS_Shape, or None.
        """
        try:
            # Search all operations (most recent first) for BRepFeat mappings.
            for op in reversed(self._operations):
                if op.operation_type == "BREPFEAT_PRISM" and op.manual_mappings:
                    # Check if our ShapeID was an input in this operation.
                    if shape_id.uuid in op.manual_mappings:
                        mapped_uuids = op.manual_mappings[shape_id.uuid]

                        # Find the mapped shapes in the current solid.
                        for mapped_uuid in mapped_uuids:
                            mapped_record = self._shapes.get(mapped_uuid)
                            if (
                                mapped_record
                                and "center" in mapped_record.geometric_signature
                            ):
                                target_center = np.array(
                                    mapped_record.geometric_signature["center"]
                                )
                                target_length = mapped_record.geometric_signature.get(
                                    "length", 0
                                )

                                for edge in current_solid.edges():
                                    center = edge.center()
                                    edge_center = np.array(
                                        [center.X, center.Y, center.Z]
                                    )
                                    dist = np.linalg.norm(target_center - edge_center)

                                    # Also check length.
                                    length_ok = True
                                    if target_length > 0 and hasattr(edge, "length"):
                                        length_diff = abs(edge.length - target_length)
                                        length_ok = length_diff < 0.5  # 0.5mm tolerance

                                    if dist < 0.5 and length_ok:  # 0.5mm tolerance
                                        return edge.wrapped

        except Exception as e:
            logger.debug(f"BRepFeat mapping lookup failed: {e}")

        return None

    # ==========================================================================
    # OCCT History Helpers
    # ==========================================================================

    def _iter_history_shapes(self, shape_list_obj: Any) -> List[Any]:
        """
        Convert an OCCT ListOfShape to a Python list.

        Tries direct iteration first, then falls back to manual
        Iterator protocol for older OCP versions.

        Args:
            shape_list_obj: OCCT TopTools_ListOfShape or similar.

        Returns:
            Python list of TopoDS_Shape objects.
        """
        if shape_list_obj is None:
            return []
        try:
            return [s for s in shape_list_obj]
        except Exception:
            pass

        try:
            it = shape_list_obj.Iterator()
            out = []
            while it.More():
                out.append(it.Value())
                it.Next()
            return out
        except Exception:
            return []

    def _history_outputs_for_shape(
        self, occt_history: Any, source_shape: Any
    ) -> List[Any]:
        """
        Get Modified/Generated outputs from OCCT history for a source shape.

        Prefers Modified over Generated. Falls back to checking the
        Reversed variant of the source shape when no mappings are found
        (BRepFeat history building is orientation-dependent).

        Args:
            occt_history: BRepTools_History object.
            source_shape: The source OCP TopoDS_Shape.

        Returns:
            List of output TopoDS_Shape objects (deduplicated by IsSame).
        """
        if occt_history is None or source_shape is None:
            return []

        outputs: List[Any] = []
        seen: List[Any] = []

        for query_name in ("Modified", "Generated"):
            try:
                query_fn = getattr(occt_history, query_name, None)
                if query_fn is None:
                    continue
                mapped = self._iter_history_shapes(query_fn(source_shape))

                # BRepFeat fix: also check Reversed variant if no mappings found
                # (BRepFeat/History-building is orientation-dependent).
                if not mapped and hasattr(source_shape, "Reversed"):
                    try:
                        rev_mapped = self._iter_history_shapes(
                            query_fn(source_shape.Reversed())
                        )
                        if rev_mapped:
                            mapped = rev_mapped
                    except Exception:
                        pass
            except Exception:
                mapped = []

            for mapped_shape in mapped:
                if mapped_shape is None:
                    continue
                duplicate = False
                for known in seen:
                    try:
                        if known.IsSame(mapped_shape):
                            duplicate = True
                            break
                    except Exception:
                        continue
                if duplicate:
                    continue
                seen.append(mapped_shape)
                outputs.append(mapped_shape)

        return outputs

    # ==========================================================================
    # ShapeID Update Methods
    # ==========================================================================

    def update_shape_id_after_operation(
        self,
        old_shape: Any,
        new_shape: Any,
        feature_id: str,
        operation_type: str = "unknown",
    ) -> bool:
        """
        Update a ShapeID with new geometry after an operation.

        This is the CORE METHOD for history-based TNP. Instead of falling
        back to geometric matching, ShapeIDs are updated directly with the
        new geometry while preserving their UUID.

        Args:
            old_shape: The OCP shape BEFORE the operation.
            new_shape: The OCP shape AFTER the operation.
            feature_id: ID of the feature performing the operation.
            operation_type: Type of operation (for logging).

        Returns:
            True if a ShapeID was found and updated, False otherwise.
        """
        if not HAS_OCP:
            return False

        try:
            # Find the old ShapeID.
            old_shape_id = self._find_exact_shape_id_by_ocp_shape(old_shape)
            if old_shape_id is None:
                if is_enabled("tnp_debug_logging"):
                    logger.debug("TNP: Old shape not found for update")
                return False

            # Compute new geometry data.
            geo_data = self._extract_geometry_data(new_shape, old_shape_id.shape_type)
            if not geo_data:  # Empty tuple means failure
                logger.debug(
                    f"TNP: Could not compute geometry data for "
                    f"{old_shape_id.uuid[:8]} (expected for consumed edges)"
                )
                return False

            # Update ShapeID: new geometry, same UUID.
            updated_shape_id = ShapeID(
                uuid=old_shape_id.uuid,
                shape_type=old_shape_id.shape_type,
                feature_id=feature_id,
                local_index=old_shape_id.local_index,
                geometry_hash=geo_data,
                timestamp=time.time(),
            )

            # Update ShapeRecord.
            new_record = ShapeRecord(
                shape_id=updated_shape_id,
                ocp_shape=new_shape,
                is_valid=True,
            )
            new_record.geometric_signature = new_record.compute_signature()

            # Replace old record.
            self._shapes[old_shape_id.uuid] = new_record

            # Update spatial index.
            center = self._get_shape_center(new_shape)
            if center is not None:
                shape_type_key = updated_shape_id.shape_type.name
                if isinstance(self._spatial_index, dict) and shape_type_key in self._spatial_index:
                    # v4-style dict spatial index
                    self._spatial_index[shape_type_key] = [
                        (pos, sid)
                        for pos, sid in self._spatial_index[shape_type_key]
                        if sid.uuid != old_shape_id.uuid
                    ]
                    self._spatial_index[shape_type_key].append(
                        (center, updated_shape_id)
                    )

            if is_enabled("tnp_debug_logging"):
                logger.success(
                    f"TNP: ShapeID {old_shape_id.uuid[:8]} updated "
                    f"after {operation_type}"
                )
            return True

        except Exception as e:
            logger.warning(f"TNP: update_shape_id_after_operation failed: {e}")
            return False

    def update_shape_ids_from_history(
        self,
        source_solid: Any,
        result_solid: Any,
        occt_history: Any,
        feature_id: str,
        operation_type: str = "unknown",
    ) -> int:
        """
        Batch update ALL ShapeIDs based on OCCT History.

        This is the preferred method for updating ShapeIDs after boolean,
        extrude, and similar operations.

        Args:
            source_solid: Solid BEFORE the operation.
            result_solid: Solid AFTER the operation.
            occt_history: BRepTools_History object.
            feature_id: ID of the feature.
            operation_type: Type of operation.

        Returns:
            Number of updated ShapeIDs.
        """
        if not HAS_OCP or occt_history is None:
            return 0

        try:
            updated_count = 0

            # Iterate all shapes in the source solid.
            for shape_type in (TopAbs_EDGE, TopAbs_FACE):
                source_map = TopTools_IndexedMapOfShape()
                TopExp.MapShapes_s(source_solid, shape_type, source_map)

                for i in range(1, source_map.Extent() + 1):
                    old_shape = source_map.FindKey(i)

                    # Check if this shape has a ShapeID.
                    old_shape_id = self._find_exact_shape_id_by_ocp_shape(old_shape)
                    if old_shape_id is None:
                        continue

                    # Query history: what became of this shape?
                    modified = self._history_outputs_for_shape(
                        occt_history, old_shape
                    )
                    if not modified:
                        # Shape was not modified (still exists).
                        continue

                    # Consider all modified shapes (1:N possible for booleans).
                    for new_shape in modified:
                        if self.update_shape_id_after_operation(
                            old_shape,
                            new_shape,
                            feature_id,
                            f"{operation_type}_history",
                        ):
                            updated_count += 1
                            break  # First successful match wins.

            if is_enabled("tnp_debug_logging") and updated_count > 0:
                logger.success(
                    f"TNP: {updated_count} ShapeIDs updated after "
                    f"{operation_type} via history"
                )

            return updated_count

        except Exception as e:
            logger.warning(f"TNP: update_shape_ids_from_history failed: {e}")
            import traceback
            traceback.print_exc()
            return 0

    # ==========================================================================
    # Exact Shape Lookup
    # ==========================================================================

    def _find_exact_shape_id_by_ocp_shape(
        self, ocp_shape: Any
    ) -> Optional[ShapeID]:
        """
        Find a ShapeID by exact OCP topology identity (IsSame).

        Helper for history-tracking deduplication. Iterates records in
        reverse order to prefer newer entries.

        Args:
            ocp_shape: The OCP TopoDS_Shape to look up.

        Returns:
            The matching ShapeID, or None.
        """
        try:
            for record in reversed(list(self._shapes.values())):
                if record.ocp_shape is None:
                    continue
                try:
                    if record.ocp_shape.IsSame(ocp_shape):
                        return record.shape_id
                except Exception:
                    continue
        except Exception:
            pass
        return None

    # ==========================================================================
    # Spatial Helpers
    # ==========================================================================

    def _get_shape_center(
        self, shape: Any
    ) -> Optional[Tuple[float, float, float]]:
        """
        Compute the center of mass of a shape for the spatial index.

        Args:
            shape: OCP TopoDS_Shape.

        Returns:
            (x, y, z) center tuple, or None on failure.
        """
        if not HAS_OCP or shape is None:
            return None
        try:
            from OCP.GProp import GProp_GProps
            from OCP.BRepGProp import BRepGProp

            props = GProp_GProps()
            BRepGProp.LinearProperties_s(shape, props)
            p = props.CentreOfMass()
            return (p.X(), p.Y(), p.Z())
        except Exception:
            return None

    # ==========================================================================
    # BRepFeat Operation Tracking
    # ==========================================================================

    def track_brepfeat_operation(
        self,
        feature_id: str,
        source_solid: Any,
        result_solid: Any,
        modified_face: Any,
        direction: Tuple[float, float, float],
        distance: float,
        occt_history: Optional[Any] = None,
    ) -> Optional[OperationRecord]:
        """
        Track a BRepFeat_MakePrism operation.

        BRepFeat changes the topology of the solid: faces are shifted and
        new edges are created. This method creates mappings from old to new
        ShapeIDs.

        Two paths:
        1. Kernel-first (if OCCT history available): build mappings from
           real Source->Result via OCCT history.
        2. Heuristic fallback: match edges geometrically using centers,
           expected shift direction, and lengths.

        Args:
            feature_id: ID of the Push/Pull feature.
            source_solid: Solid before the operation.
            result_solid: Solid after the operation.
            modified_face: The face that was pushed/pulled.
            direction: Extrusion direction (x, y, z).
            distance: Extrusion distance.
            occt_history: Optional BRepTools_History from BRepFeat_MakePrism.

        Returns:
            OperationRecord with mappings, or None on failure.
        """
        if not HAS_OCP:
            return None

        try:
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_EDGE
            from OCP.TopoDS import TopoDS

            if is_enabled("tnp_debug_logging"):
                logger.info(
                    f"TNP: Tracking BRepFeat operation '{feature_id}'"
                )

            # ------------------------------------------------------------------
            # Kernel-first path: use OCCT history for real mappings.
            # ------------------------------------------------------------------
            if occt_history is not None:
                source_items = self._collect_brepfeat_history_inputs(
                    source_solid, modified_face
                )
                if source_items:
                    manual_mappings, new_shape_ids = (
                        self._build_brepfeat_history_mappings(
                            feature_id=feature_id,
                            source_items=source_items,
                            result_solid=result_solid,
                            occt_history=occt_history,
                            start_local_index=0,
                        )
                    )

                    if manual_mappings:
                        edge_output_ids = [
                            sid
                            for sid in new_shape_ids
                            if sid.shape_type == ShapeType.EDGE
                        ]
                        max_edge_local_index = max(
                            (int(sid.local_index) for sid in edge_output_ids),
                            default=-1,
                        )

                        mappings_for_unmapped = []
                        for new_shape_id in edge_output_ids:
                            mappings_for_unmapped.append(
                                type(
                                    "Mapping",
                                    (),
                                    {"new_shape_uuid": new_shape_id.uuid},
                                )()
                            )

                        new_edge_count = self._register_unmapped_edges(
                            result_solid=result_solid,
                            feature_id=feature_id,
                            existing_mappings=mappings_for_unmapped,
                            start_local_index=max_edge_local_index + 1,
                        )

                        input_shape_ids = [sid for sid, _shape in source_items]
                        op_record = OperationRecord(
                            operation_type="BREPFEAT_PRISM",
                            feature_id=feature_id,
                            input_shape_ids=input_shape_ids,
                            output_shape_ids=new_shape_ids,
                            occt_history=occt_history,
                            manual_mappings=manual_mappings,
                            metadata={
                                "direction": direction,
                                "distance": distance,
                                "mappings_count": len(manual_mappings),
                                "new_edges_registered": int(new_edge_count),
                                "mapping_mode": "history",
                            },
                        )
                        self.record_operation(op_record)

                        if is_enabled("tnp_debug_logging"):
                            logger.success(
                                "TNP: BRepFeat kernel-history tracked - "
                                f"{len(manual_mappings)} mappings + "
                                f"{new_edge_count} new edges"
                            )
                        return op_record

                    if is_enabled("tnp_debug_logging"):
                        logger.warning(
                            "TNP: BRepFeat history had source inputs but "
                            "0 mappings. Falling back to heuristic."
                        )
                if is_enabled("tnp_debug_logging"):
                    logger.debug(
                        "TNP: BRepFeat kernel-history without source inputs, "
                        "falling back to heuristic"
                    )

            # ------------------------------------------------------------------
            # Heuristic fallback path.
            # ------------------------------------------------------------------

            # 1. Find all edges of modified_face before the operation.
            mod_face_shape = (
                modified_face.wrapped
                if hasattr(modified_face, "wrapped")
                else modified_face
            )

            # Extract centers of all edges of modified_face.
            modified_face_centers = []
            face_edge_exp = TopExp_Explorer(mod_face_shape, TopAbs_EDGE)
            while face_edge_exp.More():
                edge = TopoDS.Edge_s(face_edge_exp.Current())
                try:
                    from OCP.BRepAdaptor import BRepAdaptor_Curve
                    from OCP.GProp import GProp_GProps
                    from OCP.BRepGProp import BRepGProp

                    adaptor = BRepAdaptor_Curve(edge)
                    u_mid = (
                        adaptor.FirstParameter() + adaptor.LastParameter()
                    ) / 2
                    pnt = adaptor.Value(u_mid)

                    props = GProp_GProps()
                    BRepGProp.LinearProperties_s(edge, props)
                    length = props.Mass()

                    modified_face_centers.append(
                        (np.array([pnt.X(), pnt.Y(), pnt.Z()]), length)
                    )
                except Exception:
                    pass
                face_edge_exp.Next()

            # 2. Find ShapeIDs that belong to these positions, deduplicating.
            affected_shape_ids = []
            source_edge_shapes: List[Any] = []

            for _shape_uuid, record in self._shapes.items():
                if record.shape_id.shape_type != ShapeType.EDGE:
                    continue
                if "center" not in record.geometric_signature:
                    continue

                # Only consider edges actually in the source solid.
                if not record.ocp_shape or not self._shape_exists_in_solid(
                    record.ocp_shape, source_solid
                ):
                    continue

                # Dedupe: same source edge (multiple stale ShapeIDs).
                already_seen = False
                for seen_shape in source_edge_shapes:
                    try:
                        if seen_shape.IsSame(record.ocp_shape):
                            already_seen = True
                            break
                    except Exception:
                        continue
                if already_seen:
                    continue
                source_edge_shapes.append(record.ocp_shape)

                record_center = np.array(record.geometric_signature["center"])

                for face_center, _face_length in modified_face_centers:
                    dist = np.linalg.norm(record_center - face_center)
                    if dist < 0.1:  # 0.1mm CAD standard
                        affected_shape_ids.append(record.shape_id)
                        break

            if is_enabled("tnp_debug_logging"):
                logger.debug(
                    f"TNP BRepFeat: {len(affected_shape_ids)}/"
                    f"{len(modified_face_centers)} affected edges found"
                )

            # 3. Extract all edges from the new solid (OCP-native).
            from OCP.BRepAdaptor import BRepAdaptor_Curve
            from OCP.GProp import GProp_GProps
            from OCP.BRepGProp import BRepGProp

            result_shape = (
                result_solid.wrapped
                if hasattr(result_solid, "wrapped")
                else result_solid
            )
            new_edges = []  # list of (ocp_edge, center_array, length)
            edge_exp = TopExp_Explorer(result_shape, TopAbs_EDGE)
            while edge_exp.More():
                ocp_edge = TopoDS.Edge_s(edge_exp.Current())
                try:
                    adaptor = BRepAdaptor_Curve(ocp_edge)
                    u_mid = (
                        adaptor.FirstParameter() + adaptor.LastParameter()
                    ) / 2
                    pnt = adaptor.Value(u_mid)
                    props = GProp_GProps()
                    BRepGProp.LinearProperties_s(ocp_edge, props)
                    edge_length = props.Mass()
                    edge_center = np.array([pnt.X(), pnt.Y(), pnt.Z()])
                    new_edges.append((ocp_edge, edge_center, edge_length))
                except Exception:
                    new_edges.append((ocp_edge, np.zeros(3), 0.0))
                edge_exp.Next()

            # 4. Create mappings: old edge -> new edge.
            manual_mappings: Dict[str, List[str]] = {}
            new_shape_ids: List[ShapeID] = []
            used_new_edge_indices: Set[int] = set()

            dir_vec = np.array(direction)

            for old_shape_id in affected_shape_ids:
                old_record = self._shapes.get(old_shape_id.uuid)
                if (
                    not old_record
                    or "center" not in old_record.geometric_signature
                ):
                    continue

                old_center = np.array(old_record.geometric_signature["center"])
                old_length = old_record.geometric_signature.get("length", 0)

                best_match = None
                best_score = float("inf")

                for i, (ocp_edge, new_center, new_length) in enumerate(
                    new_edges
                ):
                    if i in used_new_edge_indices:
                        continue

                    expected_shift = dir_vec * distance
                    expected_center = old_center + expected_shift

                    dist_to_expected = np.linalg.norm(
                        new_center - expected_center
                    )
                    dist_to_old = np.linalg.norm(new_center - old_center)
                    dist = min(dist_to_expected, dist_to_old)

                    length_diff = abs(new_length - old_length)
                    length_score = length_diff * 0.1

                    score = dist + length_score

                    if score < best_score and dist < 1.0:  # 1mm tolerance
                        best_score = score
                        best_match = (i, ocp_edge)

                if best_match:
                    idx, matched_ocp_edge = best_match
                    used_new_edge_indices.add(idx)

                    new_shape_id = self.register_shape(
                        ocp_shape=matched_ocp_edge,
                        shape_type=ShapeType.EDGE,
                        feature_id=feature_id,
                        local_index=len(new_shape_ids),
                    )
                    new_shape_ids.append(new_shape_id)

                    if old_shape_id.uuid not in manual_mappings:
                        manual_mappings[old_shape_id.uuid] = []
                    manual_mappings[old_shape_id.uuid].append(
                        new_shape_id.uuid
                    )

                    if is_enabled("tnp_debug_logging"):
                        logger.debug(
                            f"TNP BRepFeat: Mapped {old_shape_id.uuid[:8]} -> "
                            f"{new_shape_id.uuid[:8]} (score={best_score:.3f})"
                        )

            # 5. Register all unmapped new edges (e.g. side edges).
            mappings_for_unmapped = []
            if manual_mappings:
                for _old_uuid, new_uuid_list in manual_mappings.items():
                    for new_uuid in new_uuid_list:
                        mappings_for_unmapped.append(
                            type(
                                "Mapping",
                                (),
                                {"new_shape_uuid": new_uuid},
                            )()
                        )

            new_edge_count = self._register_unmapped_edges(
                result_solid=result_solid,
                feature_id=feature_id,
                existing_mappings=mappings_for_unmapped,
                start_local_index=len(new_shape_ids),
            )

            if is_enabled("tnp_debug_logging"):
                logger.info(
                    f"TNP BRepFeat: {len(manual_mappings)} mappings + "
                    f"{new_edge_count} new edges registered"
                )

            # 6. Create OperationRecord.
            if manual_mappings:
                op_record = OperationRecord(
                    operation_type="BREPFEAT_PRISM",
                    feature_id=feature_id,
                    input_shape_ids=affected_shape_ids,
                    output_shape_ids=new_shape_ids,
                    manual_mappings=manual_mappings,
                    metadata={
                        "direction": direction,
                        "distance": distance,
                        "mappings_count": len(manual_mappings),
                        "mapping_mode": "heuristic",
                    },
                )
                self.record_operation(op_record)

                mapped_unique = len({sid.uuid for sid in new_shape_ids})
                total_refs = mapped_unique + new_edge_count
                if is_enabled("tnp_debug_logging"):
                    logger.success(
                        "TNP: BRepFeat operation tracked - "
                        f"{len(manual_mappings)} mappings "
                        f"({mapped_unique} unique) + "
                        f"{new_edge_count} new edges = {total_refs} unique refs"
                    )
                return op_record
            else:
                if is_enabled("tnp_debug_logging"):
                    logger.warning("TNP: No BRepFeat mappings created")
                return None

        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.error(f"TNP: BRepFeat tracking failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ==========================================================================
    # BRepFeat History Helpers
    # ==========================================================================

    def _collect_brepfeat_history_inputs(
        self,
        source_solid: Any,
        modified_face: Any,
    ) -> List[Tuple[ShapeID, Any]]:
        """
        Collect source ShapeIDs (face + boundary edges) for kernel-first
        BRepFeat mapping.

        Args:
            source_solid: The solid before the operation.
            modified_face: The face being pushed/pulled.

        Returns:
            List of (ShapeID, ocp_shape) tuples for all input shapes.
        """
        if not HAS_OCP or modified_face is None:
            return []

        inputs: List[Tuple[ShapeID, Any]] = []
        seen_uuids: Set[str] = set()

        def _append_candidate(
            shape_id: Optional[ShapeID], shape_obj: Any
        ) -> None:
            if shape_id is None or shape_obj is None:
                return
            if shape_id.uuid in seen_uuids:
                return

            # Use shape_obj (from current operation context) rather than
            # record.ocp_shape. The BRepFeat history was built using
            # shape_obj; using the registry cache might point to a
            # topologically equivalent but different TShape instance,
            # causing History Lookup (pointer identity) to fail.
            candidate_shape = shape_obj
            if candidate_shape is None:
                return

            seen_uuids.add(shape_id.uuid)
            inputs.append((shape_id, candidate_shape))

        face_shape = (
            modified_face.wrapped
            if hasattr(modified_face, "wrapped")
            else modified_face
        )
        face_shape_id = self.find_shape_id_by_face(
            face_shape, require_exact=True
        )
        _append_candidate(face_shape_id, face_shape)

        edge_exp = TopExp_Explorer(face_shape, TopAbs_EDGE)
        while edge_exp.More():
            edge_shape = TopoDS.Edge_s(edge_exp.Current())
            edge_shape_id = self.find_shape_id_by_edge(
                edge_shape, require_exact=True
            )
            _append_candidate(edge_shape_id, edge_shape)
            edge_exp.Next()

        return inputs

    def _build_brepfeat_history_mappings(
        self,
        feature_id: str,
        source_items: List[Tuple[ShapeID, Any]],
        result_solid: Any,
        occt_history: Any,
        *,
        start_local_index: int = 0,
    ) -> Tuple[Dict[str, List[str]], List[ShapeID]]:
        """
        Create Input->Output mappings per OCCT History for BRepFeat.

        BRepFeat-specific: Generated(Edge) yields a FACE (side surface),
        NOT another Edge. We extract child edges from the generated face
        to create correct Edge->Edge mappings.

        For Faces: IsDeleted(Face) can be True (the pushed face is deleted
        and recreated at the new position).

        Args:
            feature_id: Feature ID for newly registered shapes.
            source_items: List of (ShapeID, ocp_shape) from
                _collect_brepfeat_history_inputs.
            result_solid: Solid after the operation.
            occt_history: BRepTools_History object.
            start_local_index: Starting local_index for new registrations.

        Returns:
            Tuple of (manual_mappings dict, list of new ShapeIDs).
        """
        local_index = max(0, int(start_local_index or 0))
        manual_mappings: Dict[str, List[str]] = {}
        new_shape_ids: List[ShapeID] = []
        registered_outputs: List[Tuple[Any, ShapeID]] = []

        def _find_or_register(ocp_shape: Any, shape_type: ShapeType) -> ShapeID:
            """Find existing registered output or register new."""
            nonlocal local_index
            for known_shape, known_shape_id in registered_outputs:
                try:
                    if known_shape.IsSame(ocp_shape):
                        return known_shape_id
                except Exception:
                    continue
            shape_id = self.register_shape(
                ocp_shape=ocp_shape,
                shape_type=shape_type,
                feature_id=feature_id,
                local_index=local_index,
            )
            registered_outputs.append((ocp_shape, shape_id))
            new_shape_ids.append(shape_id)
            local_index += 1
            return shape_id

        for source_shape_id, source_shape in source_items:
            history_outputs = self._history_outputs_for_shape(
                occt_history, source_shape
            )
            if not history_outputs:
                continue

            for mapped_shape in history_outputs:
                if mapped_shape is None:
                    continue

                mapped_type = None
                try:
                    mapped_type = mapped_shape.ShapeType()
                except Exception:
                    continue

                # --- BRepFeat-specific: Edge -> Face (generated side surface) ---
                if (
                    source_shape_id.shape_type == ShapeType.EDGE
                    and mapped_type == TopAbs_FACE
                ):
                    if not self._shape_exists_in_solid(
                        mapped_shape, result_solid
                    ):
                        continue

                    # Register the generated side face.
                    face_shape_id = _find_or_register(
                        mapped_shape, ShapeType.FACE
                    )
                    bucket = manual_mappings.setdefault(
                        source_shape_id.uuid, []
                    )
                    if face_shape_id.uuid not in bucket:
                        bucket.append(face_shape_id.uuid)

                    # Extract child edges of the generated face and register
                    # them as edge mappings.
                    child_edge_exp = TopExp_Explorer(mapped_shape, TopAbs_EDGE)
                    while child_edge_exp.More():
                        child_edge = TopoDS.Edge_s(child_edge_exp.Current())
                        if self._shape_exists_in_solid(
                            child_edge, result_solid
                        ):
                            edge_shape_id = _find_or_register(
                                child_edge, ShapeType.EDGE
                            )
                            if edge_shape_id.uuid not in bucket:
                                bucket.append(edge_shape_id.uuid)
                        child_edge_exp.Next()
                    continue

                # --- Standard: Same-Type Mapping (Edge->Edge, Face->Face) ---
                expected_topabs = {
                    ShapeType.EDGE: TopAbs_EDGE,
                    ShapeType.FACE: TopAbs_FACE,
                    ShapeType.VERTEX: TopAbs_VERTEX,
                }.get(source_shape_id.shape_type)

                if expected_topabs is not None and mapped_type != expected_topabs:
                    continue
                if not self._shape_exists_in_solid(mapped_shape, result_solid):
                    continue

                mapped_shape_id = _find_or_register(
                    mapped_shape, source_shape_id.shape_type
                )
                bucket = manual_mappings.setdefault(source_shape_id.uuid, [])
                if mapped_shape_id.uuid not in bucket:
                    bucket.append(mapped_shape_id.uuid)

        return manual_mappings, new_shape_ids

    def _register_unmapped_edges(
        self,
        result_solid: Any,
        feature_id: str,
        existing_mappings: List,
        start_local_index: int = 0,
    ) -> int:
        """
        Register all edges in the result solid that have no mapping yet.

        Uses OCCT-native TopTools_IndexedMapOfShape for correct shape
        identity (TShape pointer equality) instead of fragile hash
        comparisons.

        Args:
            result_solid: The solid after the operation.
            feature_id: Feature ID for newly registered shapes.
            existing_mappings: List of objects with .new_shape_uuid attr.
            start_local_index: Starting local_index for new registrations.

        Returns:
            Number of newly registered edges.
        """
        if not HAS_OCP:
            return 0

        try:
            result_shape = (
                result_solid.wrapped
                if hasattr(result_solid, "wrapped")
                else result_solid
            )

            # 1. Build map of ALL already-known edges (from registry).
            known_edges_map = TopTools_IndexedMapOfShape()
            for record in self._shapes.values():
                if (
                    record.shape_id.shape_type == ShapeType.EDGE
                    and record.ocp_shape
                ):
                    known_edges_map.Add(record.ocp_shape)

            # Add explicitly already-mapped output edges (defensive:
            # prevents double-registration with partial registry states).
            for mapping in existing_mappings or []:
                new_uuid = getattr(mapping, "new_shape_uuid", None)
                if not new_uuid:
                    continue
                record = self._shapes.get(str(new_uuid))
                if (
                    not record
                    or record.shape_id.shape_type != ShapeType.EDGE
                    or not record.ocp_shape
                ):
                    continue
                try:
                    known_edges_map.Add(record.ocp_shape)
                except Exception:
                    continue

            if is_enabled("tnp_debug_logging"):
                result_edge_map = TopTools_IndexedMapOfShape()
                TopExp.MapShapes_s(result_shape, TopAbs_EDGE, result_edge_map)
                logger.debug(
                    f"[TNP] _register_unmapped_edges: "
                    f"{result_edge_map.Extent()} unique edges in result, "
                    f"{known_edges_map.Extent()} already known"
                )

            # 2. Iterate result solid edges using IndexedMap for dedup.
            explorer = TopExp_Explorer(result_shape, TopAbs_EDGE)
            new_count = 0
            local_index = max(0, int(start_local_index or 0))

            while explorer.More():
                edge = TopoDS.Edge_s(explorer.Current())

                if not known_edges_map.Contains(edge):
                    # Truly new edge -> register.
                    shape_id = self.register_shape(
                        ocp_shape=edge,
                        shape_type=ShapeType.EDGE,
                        feature_id=feature_id,
                        local_index=local_index,
                    )
                    known_edges_map.Add(edge)  # prevent double-registration
                    new_count += 1
                    local_index += 1

                    if is_enabled("tnp_debug_logging"):
                        logger.debug(
                            f"[TNP] New edge registered: {shape_id.uuid[:8]}"
                        )

                explorer.Next()

            if is_enabled("tnp_debug_logging"):
                logger.info(
                    f"[TNP] _register_unmapped_edges: "
                    f"{new_count} new edges registered"
                )
            return new_count

        except Exception as e:
            logger.warning(f"_register_unmapped_edges failed: {e}")
            return 0

    # ==========================================================================
    # Stub: Fillet Operation Tracking
    # ==========================================================================

    def _track_fillet_or_chamfer_operation(
        self,
        operation_type: str,
        feature_id: str,
        source_solid: Any,
        result_solid: Any,
        occt_history: Optional[Any] = None,
        edge_shapes: Optional[List[Any]] = None,
        param_value: float = 0.0,
    ) -> Optional[OperationRecord]:
        """
        Shared implementation for Fillet and Chamfer tracking.

        Both operations modify edges into new faces. The OCCT History tracks
        which edges were modified and which new faces/edges were created.
        """
        if not HAS_OCP:
            return None

        try:
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
            from OCP.TopTools import TopTools_IndexedMapOfShape
            from OCP.TopExp import TopExp

            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP v5.0: Tracking {operation_type} operation '{feature_id}'")

            # Kernel-first: OCCT History
            if occt_history is not None:
                manual_mappings: Dict[str, List[str]] = {}
                new_shape_ids: List[ShapeID] = []

                source_edge_map = TopTools_IndexedMapOfShape()
                TopExp.MapShapes_s(source_solid, TopAbs_EDGE, source_edge_map)

                for uuid, record in list(self._shapes.items()):
                    if record.shape_id.shape_type != ShapeType.EDGE:
                        continue
                    if record.ocp_shape is None:
                        continue
                    if not self._shape_exists_in_solid(record.ocp_shape, source_solid):
                        continue

                    modified_shapes = self._history_outputs_for_shape(occt_history, record.ocp_shape)
                    if modified_shapes:
                        input_shape_id = record.shape_id
                        output_uuids = []

                        for modified_shape in modified_shapes:
                            existing_id = self._find_exact_shape_id_by_ocp_shape(modified_shape)
                            if existing_id:
                                output_uuids.append(existing_id.uuid)
                                if existing_id not in new_shape_ids:
                                    new_shape_ids.append(existing_id)
                            else:
                                if self.update_shape_id_after_operation(
                                    old_shape=record.ocp_shape,
                                    new_shape=modified_shape,
                                    feature_id=feature_id,
                                    operation_type=f"{operation_type.lower()}_{feature_id}"
                                ):
                                    output_uuids.append(record.shape_id.uuid)
                                    if record.shape_id not in new_shape_ids:
                                        new_shape_ids.append(record.shape_id)
                                else:
                                    shape_type = ShapeType.FACE if modified_shape.ShapeType() == TopAbs_FACE else ShapeType.EDGE
                                    new_id = self.register_shape(
                                        ocp_shape=modified_shape,
                                        shape_type=shape_type,
                                        feature_id=feature_id,
                                        local_index=len(new_shape_ids)
                                    )
                                    new_shape_ids.append(new_id)
                                    output_uuids.append(new_id.uuid)

                        if output_uuids:
                            manual_mappings[input_shape_id.uuid] = output_uuids

                if manual_mappings or new_shape_ids:
                    op_record = OperationRecord(
                        operation_type=operation_type,
                        feature_id=feature_id,
                        input_shape_ids=[sid for sid in self._shapes.values()
                                        if sid.shape_id.uuid in manual_mappings],
                        output_shape_ids=new_shape_ids,
                        occt_history=occt_history,
                        manual_mappings=manual_mappings,
                        metadata={
                            "param_value": param_value,
                            "mappings_count": len(manual_mappings),
                            "new_shapes": len(new_shape_ids),
                        }
                    )
                    self.record_operation(op_record)
                    if is_enabled("tnp_debug_logging"):
                        logger.success(
                            f"TNP v5.0: {operation_type} History tracked - "
                            f"{len(manual_mappings)} mappings, {len(new_shape_ids)} new shapes"
                        )
                    return op_record

            # Fallback: Register all new edges
            new_edge_count = self._register_unmapped_edges(
                result_solid=result_solid,
                feature_id=feature_id,
                existing_mappings=[],
                start_local_index=0,
            )

            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP {operation_type} Fallback: {new_edge_count} new edges registered")

            op_record = OperationRecord(
                operation_type=operation_type,
                feature_id=feature_id,
                input_shape_ids=[],
                output_shape_ids=[],
                occt_history=occt_history,
                manual_mappings={},
                metadata={
                    "param_value": param_value,
                    "fallback_mode": True,
                    "new_edges": new_edge_count,
                }
            )
            self.record_operation(op_record)
            return op_record

        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.error(f"TNP v5.0: {operation_type} Tracking failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def track_fillet_operation(
        self,
        feature_id: str,
        source_solid: Any,
        result_solid: Any,
        occt_history: Optional[Any] = None,
        edge_shapes: Optional[List[Any]] = None,
        radius: float = 0.0,
    ) -> Optional[OperationRecord]:
        """
        Track a BRepFilletAPI_MakeFillet operation.

        Args:
            feature_id: ID of the fillet feature
            source_solid: Solid before operation
            result_solid: Solid after operation
            occt_history: BRepTools_History from BRepFilletAPI_MakeFillet
            edge_shapes: The filleted edge shapes (for fallback)
            radius: Fillet radius (for metadata)
        """
        return self._track_fillet_or_chamfer_operation(
            "FILLET", feature_id, source_solid, result_solid,
            occt_history, edge_shapes, radius,
        )

    def track_chamfer_operation(
        self,
        feature_id: str,
        source_solid: Any,
        result_solid: Any,
        occt_history: Optional[Any] = None,
        edge_shapes: Optional[List[Any]] = None,
        distance: float = 0.0,
    ) -> Optional[OperationRecord]:
        """
        Track a BRepFilletAPI_MakeChamfer operation.

        Args:
            feature_id: ID of the chamfer feature
            source_solid: Solid before operation
            result_solid: Solid after operation
            occt_history: BRepTools_History from MakeChamfer
            edge_shapes: The chamfered edge shapes (for fallback)
            distance: Chamfer distance (for metadata)
        """
        return self._track_fillet_or_chamfer_operation(
            "CHAMFER", feature_id, source_solid, result_solid,
            occt_history, edge_shapes, distance,
        )

    def track_draft_operation(
        self,
        feature_id: str,
        source_solid: Any,
        result_solid: Any,
        occt_history: Optional[Any] = None,
        angle: float = 0.0,
    ) -> Optional[OperationRecord]:
        """
        Track a BRepOffsetAPI_DraftAngle operation.

        Draft modifies faces. We track Modified() and Generated().
        """
        if not HAS_OCP:
            return None

        try:
            from OCP.TopAbs import TopAbs_FACE

            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP v5.0: Tracking Draft operation '{feature_id}'")

            manual_mappings: Dict[str, List[str]] = {}
            new_shape_ids: List[ShapeID] = []

            if occt_history is not None:
                for uuid, record in list(self._shapes.items()):
                    if record.shape_id.shape_type != ShapeType.FACE:
                        continue
                    if record.ocp_shape is None:
                        continue
                    if not self._shape_exists_in_solid(record.ocp_shape, source_solid):
                        continue

                    modified_shapes = self._history_outputs_for_shape(occt_history, record.ocp_shape)
                    if modified_shapes:
                        input_shape_id = record.shape_id
                        output_uuids = []
                        for mod_shape in modified_shapes:
                            existing_id = self._find_exact_shape_id_by_ocp_shape(mod_shape)
                            if existing_id:
                                output_uuids.append(existing_id.uuid)
                                if existing_id not in new_shape_ids:
                                    new_shape_ids.append(existing_id)
                            else:
                                if self.update_shape_id_after_operation(
                                    old_shape=record.ocp_shape,
                                    new_shape=mod_shape,
                                    feature_id=feature_id,
                                    operation_type=f"draft_{feature_id}"
                                ):
                                    output_uuids.append(record.shape_id.uuid)
                                    if record.shape_id not in new_shape_ids:
                                        new_shape_ids.append(record.shape_id)
                                else:
                                    new_id = self.register_shape(
                                        ocp_shape=mod_shape,
                                        shape_type=ShapeType.FACE,
                                        feature_id=feature_id,
                                        local_index=len(new_shape_ids)
                                    )
                                    new_shape_ids.append(new_id)
                                    output_uuids.append(new_id.uuid)
                        if output_uuids:
                            manual_mappings[input_shape_id.uuid] = output_uuids

            op_record = OperationRecord(
                operation_type="DRAFT",
                feature_id=feature_id,
                input_shape_ids=[sid for sid in self._shapes.values() if sid.shape_id.uuid in manual_mappings],
                output_shape_ids=new_shape_ids,
                occt_history=occt_history,
                manual_mappings=manual_mappings,
                metadata={"angle": angle}
            )
            self.record_operation(op_record)

            self._register_unmapped_edges(result_solid, feature_id, existing_mappings=[])

            return op_record

        except Exception as e:
            logger.error(f"TNP Draft Tracking failed: {e}")
            return None

    def track_sketch_extrude(
        self,
        feature_id: str,
        sketch: Any,
        result_solid: Any,
        distance: float,
        direction: Tuple[float, float, float] = (0, 0, 1),
        plane_origin: Tuple[float, float, float] = (0, 0, 0),
        plane_normal: Tuple[float, float, float] = (0, 0, 1),
    ) -> Optional[OperationRecord]:
        """
        Track a sketch extrusion and create mappings from sketch elements
        to the generated 3D edges.

        Args:
            feature_id: ID of the ExtrudeFeature
            sketch: The sketch that was extruded
            result_solid: The resulting solid
            distance: Extrusion distance
            direction: Extrusion direction vector
            plane_origin: Origin of the sketch plane
            plane_normal: Normal of the sketch plane
        """
        if not HAS_OCP:
            return None

        try:
            from OCP.TopAbs import TopAbs_EDGE

            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP v5.0: Tracking sketch extrusion '{feature_id}'")

            sketch_edge_mappings: Dict[str, str] = {}
            new_shape_ids: List[ShapeID] = []

            # Collect all edges in result solid
            result_shape = result_solid.wrapped if hasattr(result_solid, 'wrapped') else result_solid
            try:
                from OCP.TopTools import TopTools_IndexedMapOfShape
                e_map = TopTools_IndexedMapOfShape()
                TopExp.MapShapes_s(result_shape, TopAbs_EDGE, e_map)
                edge_list = []
                for i in range(e_map.Extent()):
                    edge = e_map.FindKey(i + 1)
                    edge_list.append(edge)
            except Exception:
                edge_list = [edge.wrapped for edge in result_solid.edges()]

            # For each sketch element, find matching 3D edge
            element_types = ['line', 'circle', 'arc']
            for elem_type in element_types:
                uuids_attr = f'_{elem_type}_shape_uuids'
                if not hasattr(sketch, uuids_attr):
                    continue

                element_uuids = getattr(sketch, uuids_attr, {})
                if not element_uuids:
                    continue

                for elem_id, elem_uuid in element_uuids.items():
                    best_match_edge = None
                    best_score = float('inf')

                    for ocp_edge in edge_list:
                        try:
                            from build123d import Edge as B123Edge
                            b123_edge = B123Edge(ocp_edge)
                            center = b123_edge.center()
                            edge_center = np.array([center.X, center.Y, center.Z])

                            expected_tip = np.array(plane_origin) + np.array(direction) * distance
                            dist_to_tip = np.linalg.norm(edge_center - expected_tip)

                            if dist_to_tip < best_score:
                                best_score = dist_to_tip
                                best_match_edge = ocp_edge
                        except Exception:
                            continue

                    if best_match_edge is not None:
                        edge_shape_id = self.register_shape(
                            ocp_shape=best_match_edge,
                            shape_type=ShapeType.EDGE,
                            feature_id=feature_id,
                            local_index=len(new_shape_ids),
                        )
                        new_shape_ids.append(edge_shape_id)
                        sketch_edge_mappings[elem_id] = edge_shape_id.uuid

            op_record = OperationRecord(
                operation_type="SKETCH_EXTRUDE",
                feature_id=feature_id,
                input_shape_ids=[],
                output_shape_ids=new_shape_ids,
                occt_history=None,
                manual_mappings={},
                metadata={
                    "distance": distance,
                    "direction": direction,
                    "plane_origin": plane_origin,
                    "plane_normal": plane_normal,
                    "sketch_elements_mapped": len(sketch_edge_mappings),
                    "mapping_mode": "sketch_to_3d",
                }
            )
            self.record_operation(op_record)

            if is_enabled("tnp_debug_logging"):
                logger.success(
                    f"TNP v5.0: Sketch extrusion tracked - "
                    f"{len(sketch_edge_mappings)} elements -> 3D edges"
                )
            return op_record

        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.error(f"TNP v5.0: Sketch extrusion tracking failed: {e}")
            import traceback
            traceback.print_exc()
            return None
