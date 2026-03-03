"""
TNP v5.0 - Lookup Mixin

Shape lookup, health reporting, and statistics methods.
"""

from typing import Dict, List, Optional, Tuple, Any, Set
from loguru import logger
from config.feature_flags import is_enabled
import numpy as np

try:
    from OCP.TopoDS import TopoDS_Shape, TopoDS_Edge, TopoDS_Face
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    HAS_OCP = True
except ImportError:
    HAS_OCP = False

from .types import ShapeID, ShapeRecord, ShapeType


class LookupMixin:
    """Mixin for shape lookup, health reports, and statistics."""

    def _find_exact_shape_id(self, shape: Any, shape_type: ShapeType) -> Optional[ShapeID]:
        """
        Find a ShapeID by exact topological identity (IsSame).

        Robust against symmetric/geometrically similar entities.
        Preferred for interactive selection.
        """
        try:
            target_shape = shape.wrapped if hasattr(shape, "wrapped") else shape
            if target_shape is None:
                return None

            for record in reversed(list(self._shapes.values())):
                sid = record.shape_id
                if sid.shape_type != shape_type:
                    continue
                rec_shape = record.ocp_shape
                if rec_shape is None:
                    continue
                try:
                    if rec_shape.IsSame(target_shape):
                        return sid
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Exact ShapeID lookup failed: {e}")
        return None

    def find_shape_id_by_edge(
        self,
        edge: Any,
        tolerance: float = 0.1,
        *,
        require_exact: bool = False,
    ) -> Optional[ShapeID]:
        """
        Find a ShapeID for a given edge (geometric matching).

        Uses exact topological identity first, then falls back to
        spatial index matching using center position and length.

        Args:
            edge: build123d Edge or OCP TopoDS_Edge
            tolerance: Distance tolerance for geometric matching
            require_exact: If True, only return exact IsSame matches

        Returns:
            ShapeID or None
        """
        try:
            exact = self._find_exact_shape_id(edge, ShapeType.EDGE)
            if exact is not None:
                return exact
            if require_exact:
                return None

            center = edge.center()
            edge_center = np.array([center.X, center.Y, center.Z])
            edge_length = edge.length if hasattr(edge, 'length') else 0

            best_match = None
            best_score = float('inf')

            for pos, shape_id in self._spatial_index[ShapeType.EDGE]:
                dist = np.linalg.norm(edge_center - pos)

                length_score = 0
                record = self._shapes.get(shape_id.uuid)
                if record and 'length' in record.geometric_signature and edge_length > 0:
                    stored_length = record.geometric_signature['length']
                    length_diff = abs(stored_length - edge_length)
                    length_score = length_diff * 0.1

                score = dist + length_score

                if score < best_score and dist < tolerance:
                    best_score = score
                    best_match = shape_id

            if best_match and is_enabled("tnp_debug_logging"):
                logger.debug(f"ShapeID found for Edge: {best_match.uuid[:8]}... (score={best_score:.4f})")

            return best_match

        except Exception as e:
            logger.debug(f"ShapeID lookup for Edge failed: {e}")
            return None

    def find_shape_id_by_face(
        self,
        face: Any,
        tolerance: float = 0.5,
        *,
        require_exact: bool = False,
    ) -> Optional[ShapeID]:
        """
        Find a ShapeID for a given face (geometric matching).

        Args:
            face: build123d Face or OCP TopoDS_Face
            tolerance: Distance tolerance for geometric matching
            require_exact: If True, only return exact IsSame matches

        Returns:
            ShapeID or None
        """
        try:
            exact = self._find_exact_shape_id(face, ShapeType.FACE)
            if exact is not None:
                return exact
            if require_exact:
                return None

            center = face.center()
            face_center = np.array([center.X, center.Y, center.Z])
            face_area = face.area if hasattr(face, 'area') else 0

            best_match = None
            best_score = float('inf')

            for pos, shape_id in self._spatial_index[ShapeType.FACE]:
                dist = np.linalg.norm(face_center - pos)

                area_score = 0
                record = self._shapes.get(shape_id.uuid)
                if record and 'area' in record.geometric_signature and face_area > 0:
                    stored_area = record.geometric_signature['area']
                    area_score = abs(stored_area - face_area) * 0.01

                score = dist + area_score

                if score < best_score and dist < tolerance:
                    best_score = score
                    best_match = shape_id

            if best_match and is_enabled("tnp_debug_logging"):
                logger.debug(f"ShapeID found for Face: {best_match.uuid[:8]}... (score={best_score:.4f})")

            return best_match

        except Exception as e:
            logger.debug(f"ShapeID lookup for Face failed: {e}")
            return None

    def find_shape_id_by_shape(
        self,
        ocp_shape: Any,
        tolerance: float = 0.5,
        *,
        require_exact: bool = False,
    ) -> Optional[ShapeID]:
        """
        Generic method to find a ShapeID for any shape.

        Automatically detects shape type (Edge/Face/Vertex) and
        calls the specialized method.

        Args:
            ocp_shape: OCP Shape (TopoDS_Edge, TopoDS_Face, etc.)
            tolerance: Tolerance for geometric matching
            require_exact: If True, only exact matches

        Returns:
            ShapeID or None
        """
        if not HAS_OCP or ocp_shape is None:
            return None

        try:
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX

            shape_type = ocp_shape.ShapeType()

            if shape_type == TopAbs_EDGE:
                from build123d import Edge
                b123d_edge = Edge(ocp_shape)
                return self.find_shape_id_by_edge(b123d_edge, tolerance=tolerance, require_exact=require_exact)

            elif shape_type == TopAbs_FACE:
                from build123d import Face
                b123d_face = Face(ocp_shape)
                return self.find_shape_id_by_face(b123d_face, tolerance=tolerance, require_exact=require_exact)

            elif shape_type == TopAbs_VERTEX:
                if require_exact:
                    return self._find_exact_shape_id(ocp_shape, ShapeType.VERTEX)
                return None

            else:
                logger.debug(f"[TNP] Unsupported shape type for ShapeID lookup: {shape_type}")
                return None

        except Exception as e:
            logger.debug(f"[TNP] find_shape_id_by_shape failed: {e}")
            return None

    def get_shape_record(self, shape_id_or_uuid: str) -> Optional[ShapeRecord]:
        """
        Get a ShapeRecord by UUID.

        Args:
            shape_id_or_uuid: UUID string

        Returns:
            ShapeRecord or None
        """
        if isinstance(shape_id_or_uuid, str):
            if shape_id_or_uuid in self._shapes:
                return self._shapes[shape_id_or_uuid]
            for record in self._shapes.values():
                if record.shape_id.uuid == shape_id_or_uuid:
                    return record
        return None

    def get_shapes_by_feature(self, feature_id: str) -> List[ShapeID]:
        """Returns all shapes created by a feature."""
        return self._by_feature.get(feature_id, [])

    def get_stats(self) -> Dict[str, int]:
        """
        Statistics for debugging.

        Counts faces/edges from _shapes (source of truth) instead of
        _spatial_index. Ensures correct counts even when compute_signature()
        fails silently.
        """
        faces = sum(1 for r in self._shapes.values() if r.shape_id.shape_type == ShapeType.FACE)
        edges = sum(1 for r in self._shapes.values() if r.shape_id.shape_type == ShapeType.EDGE)
        return {
            'total_shapes': len(self._shapes),
            'operations': len(self._operations),
            'features': len(self._by_feature),
            'edges': edges,
            'faces': faces
        }

    def check_ambiguity(self, shape_id: ShapeID, current_solid: Any):
        """
        Check whether resolving a shape_id would be ambiguous.

        Returns an AmbiguityReport with is_ambiguous flag and candidates.
        """
        from .service import AmbiguityReport
        from .types import ResolutionOptions

        record = self.get_shape_record(shape_id.uuid)
        if record is None:
            return AmbiguityReport(
                is_ambiguous=True,
                ambiguity_type="missing_shape",
                candidates=[],
                disambiguation_questions=["Original shape reference does not exist in TNP registry."],
                recommended_resolution=None,
            )
        context = getattr(record, "selection_context", None)
        if context is None:
            return AmbiguityReport(
                is_ambiguous=False,
                ambiguity_type="insufficient_context",
                candidates=[],
                disambiguation_questions=[],
                recommended_resolution=None,
            )
        semantic_result = self._try_semantic_match(
            shape_id=shape_id,
            context=context,
            current_solid=current_solid,
            options=ResolutionOptions(max_candidates=10),
        )
        candidate_ids = []
        if semantic_result is not None:
            candidate_ids = [c.shape_id for c in getattr(semantic_result, "candidates", [])]
            if getattr(semantic_result, "is_ambiguous", False) and candidate_ids:
                return AmbiguityReport(
                    is_ambiguous=True,
                    ambiguity_type="semantic_ambiguous",
                    candidates=candidate_ids,
                    disambiguation_questions=[
                        f"Multiple candidates match with close scores (top score {getattr(semantic_result, 'score', 0.0):.3f}). Please confirm intended shape."
                    ],
                    recommended_resolution=candidate_ids[0],
                )
        return AmbiguityReport(
            is_ambiguous=False,
            ambiguity_type="none",
            candidates=[],
            disambiguation_questions=[],
            recommended_resolution=None,
        )

    _CONSUMING_FEATURE_TYPES = frozenset([
        'FilletFeature', 'ChamferFeature', 'ExtrudeFeature',
    ])

    def get_health_report(self, body) -> Dict[str, Any]:
        """
        Creates a health report for a Body.

        Checks all features with TNP references (edge_shape_ids, face_shape_ids)
        and tests if ShapeIDs are still resolvable.

        Consuming features (Fillet/Chamfer) destroy their input edges
        intentionally. Their status is taken from the last rebuild
        (feature.status), since references are only valid BEFORE the operation.
        """
        report = {
            'body_name': getattr(body, 'name', 'Body'),
            'status': 'ok',
            'ok': 0, 'fallback': 0, 'broken': 0,
            'features': []
        }

        features = getattr(body, 'features', [])
        current_solid = getattr(body, '_build123d_solid', None)

        ocp_solid = None
        if current_solid is not None:
            ocp_solid = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid

        face_from_index = None
        edge_from_index = None
        try:
            from modeling.topology_indexing import (
                face_from_index as _face_from_index,
                edge_from_index as _edge_from_index,
            )
            face_from_index = _face_from_index
            edge_from_index = _edge_from_index
        except Exception:
            pass

        def _to_list(value: Any) -> List[Any]:
            if value is None:
                return []
            if isinstance(value, (list, tuple)):
                return list(value)
            return [value]

        def _to_index_list(value: Any) -> List[Optional[int]]:
            result = []
            for raw_idx in _to_list(value):
                try:
                    idx = int(raw_idx)
                    result.append(idx if idx >= 0 else None)
                except Exception:
                    result.append(None)
            return result

        def _status_details_dict(feat: Any) -> Dict[str, Any]:
            details = getattr(feat, "status_details", {})
            return details if isinstance(details, dict) else {}

        def _status_diag_level(feat: Any, details: Dict[str, Any]) -> str:
            code = str(details.get("code", "") or "").strip().lower()
            if code in {"fallback_used"}:
                return "fallback"
            if code in {
                "operation_failed", "fallback_failed",
                "no_result_solid", "self_heal_rollback_geometry_drift",
            }:
                return "broken"
            feat_status = str(getattr(feat, "status", "") or "").strip().upper()
            if feat_status == "WARNING":
                return "fallback"
            if feat_status == "ERROR":
                return "broken"
            return "ok"

        def _status_ref_kind(label: str) -> str:
            txt = str(label or "").lower()
            if "edge" in txt:
                return "Edge"
            if "face" in txt:
                return "Face"
            return "Ref"

        def _collect_status_ref_entries(feat: Any) -> List[Dict[str, Any]]:
            details = _status_details_dict(feat)
            refs = details.get("refs")
            if not isinstance(refs, dict):
                return []
            diag_status = _status_diag_level(feat, details)
            entries = []
            for ref_label, raw_value in refs.items():
                values = _to_list(raw_value)
                if not values:
                    continue
                for value in values:
                    if value in (None, "", [], (), {}):
                        continue
                    entries.append({
                        "kind": _status_ref_kind(ref_label),
                        "status": diag_status,
                        "method": "status_details",
                        "label": str(ref_label),
                        "value": value,
                    })
            return entries

        def _enforce_feature_status_truth(feat: Any, feat_report: Dict[str, Any]) -> None:
            details = _status_details_dict(feat)
            diag_status = _status_diag_level(feat, details)
            if diag_status == "ok":
                return
            if diag_status == "broken" and feat_report.get("broken", 0) > 0:
                return
            if diag_status == "fallback" and (
                feat_report.get("fallback", 0) > 0 or feat_report.get("broken", 0) > 0
            ):
                return
            feat_report["refs"].append({
                "kind": "Ref", "status": diag_status,
                "method": "feature_status",
                "label": "feature_status",
                "value": str(getattr(feat, "status", "") or ""),
            })
            if diag_status == "broken":
                feat_report["broken"] = int(feat_report.get("broken", 0)) + 1
                report["broken"] = int(report.get("broken", 0)) + 1
            elif diag_status == "fallback":
                feat_report["fallback"] = int(feat_report.get("fallback", 0)) + 1
                report["fallback"] = int(report.get("fallback", 0)) + 1

        def _collect_ref_groups(feat: Any) -> List[Tuple[str, List[Any], List[Optional[int]]]]:
            groups = []
            edge_shape_ids = _to_list(getattr(feat, "edge_shape_ids", []))
            edge_indices = _to_index_list(getattr(feat, "edge_indices", []))
            if edge_shape_ids or edge_indices:
                groups.append(("Edge", edge_shape_ids, edge_indices))

            face_shape_ids = _to_list(getattr(feat, "face_shape_ids", []))
            face_indices = _to_index_list(getattr(feat, "face_indices", []))
            if face_shape_ids or face_indices:
                groups.append(("Face", face_shape_ids, face_indices))

            opening_face_shape_ids = _to_list(getattr(feat, "opening_face_shape_ids", []))
            opening_face_indices = _to_index_list(getattr(feat, "opening_face_indices", []))
            if opening_face_shape_ids or opening_face_indices:
                groups.append(("Face", opening_face_shape_ids, opening_face_indices))

            single_face_shape_id = getattr(feat, "face_shape_id", None)
            single_face_index = getattr(feat, "face_index", None)
            if single_face_shape_id is not None or single_face_index is not None:
                groups.append(("Face", _to_list(single_face_shape_id), _to_index_list(single_face_index)))

            sweep_profile_shape_id = getattr(feat, "profile_shape_id", None)
            sweep_profile_index = getattr(feat, "profile_face_index", None)
            if sweep_profile_shape_id is not None or sweep_profile_index is not None:
                groups.append(("Face", _to_list(sweep_profile_shape_id), _to_index_list(sweep_profile_index)))

            sweep_path_shape_id = getattr(feat, "path_shape_id", None)
            sweep_path_indices = []
            path_data = getattr(feat, "path_data", {})
            if isinstance(path_data, dict):
                sweep_path_indices = _to_index_list(path_data.get("edge_indices", []))
            if sweep_path_shape_id is not None or sweep_path_indices:
                groups.append(("Edge", _to_list(sweep_path_shape_id), sweep_path_indices))

            return groups

        def _resolve_index_entity(ref_kind: str, topo_index: Optional[int]) -> Optional[Any]:
            if topo_index is None or current_solid is None:
                return None
            try:
                if ref_kind == "Face" and face_from_index is not None:
                    return face_from_index(current_solid, topo_index)
                if ref_kind == "Edge" and edge_from_index is not None:
                    return edge_from_index(current_solid, topo_index)
            except Exception:
                return None
            return None

        def _same_topology_entity(entity_a: Any, entity_b: Any) -> bool:
            if entity_a is None or entity_b is None:
                return False
            try:
                wa = entity_a.wrapped if hasattr(entity_a, "wrapped") else entity_a
                wb = entity_b.wrapped if hasattr(entity_b, "wrapped") else entity_b
                return wa.IsSame(wb)
            except Exception:
                return entity_a is entity_b

        strict_face_feature_types = {
            "ExtrudeFeature", "ThreadFeature", "HoleFeature",
            "DraftFeature", "ShellFeature", "HollowFeature",
        }
        strict_edge_feature_types = {"FilletFeature", "ChamferFeature"}

        for feat in features:
            feat_type_name = type(feat).__name__
            is_consuming = feat_type_name in self._CONSUMING_FEATURE_TYPES
            feat_status_details = _status_details_dict(feat)
            status_ref_entries = _collect_status_ref_entries(feat)

            feat_report = {
                'name': getattr(feat, 'name', 'Feature'),
                'type': feat_type_name.replace('Feature', ''),
                'status': 'no_refs',
                'ok': 0, 'fallback': 0, 'broken': 0,
                'consuming': is_consuming,
                'refs': [],
                'feature_status': str(getattr(feat, "status", "OK") or "OK"),
                'status_message': str(getattr(feat, "status_message", "") or ""),
                'status_details': dict(feat_status_details),
                'status_refs': list(status_ref_entries),
            }

            ref_groups = _collect_ref_groups(feat)
            if not ref_groups:
                if status_ref_entries:
                    for ref in status_ref_entries:
                        ref_status = str(ref.get("status", "broken"))
                        if ref_status == "ok":
                            feat_report['ok'] += 1
                            report['ok'] += 1
                        elif ref_status == "fallback":
                            feat_report['fallback'] += 1
                            report['fallback'] += 1
                        else:
                            feat_report['broken'] += 1
                            report['broken'] += 1
                        feat_report['refs'].append({
                            "kind": ref.get("kind", "Ref"),
                            "status": ref_status,
                            "method": ref.get("method", "status_details"),
                            "label": ref.get("label", ""),
                            "value": ref.get("value"),
                        })
                _enforce_feature_status_truth(feat, feat_report)
                if feat_report['broken'] > 0:
                    feat_report['status'] = 'broken'
                elif feat_report['fallback'] > 0:
                    feat_report['status'] = 'fallback'
                elif feat_report['ok'] > 0:
                    feat_report['status'] = 'ok'
                report['features'].append(feat_report)
                continue

            if is_consuming:
                rebuild_status = getattr(feat, 'status', 'OK')
                for ref_kind, shape_ids, index_refs in ref_groups:
                    ref_count = max(
                        len(shape_ids), len(index_refs),
                        sum(1 for sid in shape_ids if isinstance(sid, ShapeID)),
                        sum(1 for idx in index_refs if idx is not None),
                    )
                    if ref_count <= 0:
                        continue
                    if rebuild_status in ('OK', 'SUCCESS'):
                        feat_report['ok'] += ref_count
                        report['ok'] += ref_count
                        ref_status = 'ok'
                    elif rebuild_status == 'WARNING':
                        feat_report['fallback'] += ref_count
                        report['fallback'] += ref_count
                        ref_status = 'fallback'
                    else:
                        feat_report['broken'] += ref_count
                        report['broken'] += ref_count
                        ref_status = 'broken'
                    for _ in range(ref_count):
                        feat_report['refs'].append({
                            'kind': ref_kind, 'status': ref_status, 'method': 'rebuild'
                        })
            else:
                for ref_kind, shape_ids, index_refs in ref_groups:
                    strict_kind = (
                        (ref_kind == "Face" and feat_type_name in strict_face_feature_types)
                        or (ref_kind == "Edge" and feat_type_name in strict_edge_feature_types)
                    )
                    valid_index_refs = [idx for idx in index_refs if idx is not None]
                    expected_shape_refs = sum(1 for sid in shape_ids if isinstance(sid, ShapeID))
                    single_ref_pair = bool(expected_shape_refs == 1 and len(valid_index_refs) == 1)
                    shape_ids_index_aligned = True
                    if expected_shape_refs > 0 and valid_index_refs and not single_ref_pair:
                        for sid in shape_ids:
                            if not isinstance(sid, ShapeID):
                                continue
                            local_idx = getattr(sid, "local_index", None)
                            if not isinstance(local_idx, int) or not (0 <= local_idx < len(valid_index_refs)):
                                shape_ids_index_aligned = False
                                break
                    strict_group_check = (
                        strict_kind
                        and expected_shape_refs > 0
                        and bool(valid_index_refs)
                        and len(valid_index_refs) == expected_shape_refs
                        and (shape_ids_index_aligned or single_ref_pair)
                    )

                    ref_count = max(len(shape_ids), len(index_refs))
                    for ref_idx in range(ref_count):
                        topo_index = index_refs[ref_idx] if ref_idx < len(index_refs) else None
                        shape_id = shape_ids[ref_idx] if ref_idx < len(shape_ids) else None

                        index_entity = _resolve_index_entity(ref_kind, topo_index)
                        index_ok = index_entity is not None

                        shape_entity = None
                        method = "unresolved"
                        has_shape_ref = isinstance(shape_id, ShapeID)
                        strict_shape_check = has_shape_ref and strict_group_check
                        should_resolve_shape = strict_shape_check or (has_shape_ref and not index_ok)
                        if should_resolve_shape and ocp_solid is not None:
                            shape_entity, method = self.resolve_shape_with_method(
                                shape_id, ocp_solid, log_unresolved=False,
                            )

                        if strict_shape_check and has_shape_ref and topo_index is not None:
                            if shape_entity is not None:
                                if index_ok and not _same_topology_entity(index_entity, shape_entity):
                                    status = "broken"
                                    method = "index_mismatch"
                                elif method in ("direct", "history"):
                                    status = "ok"
                                    method = "shape"
                                elif method in ("brepfeat", "geometric"):
                                    status = "fallback"
                                else:
                                    status = "broken"
                            else:
                                status = "broken"
                                method = "shape_unresolved"
                        elif strict_shape_check and topo_index is None:
                            if shape_entity is not None:
                                if method in ("direct", "history"):
                                    status = "ok"
                                    method = "shape"
                                elif method in ("brepfeat", "geometric"):
                                    status = "fallback"
                                else:
                                    status = "broken"
                            else:
                                status = "broken"
                                method = "shape_unresolved"
                        elif index_ok:
                            status = "ok"
                            method = "index"
                        elif has_shape_ref:
                            if method in ("direct", "history"):
                                status = "ok"
                            elif method in ("brepfeat", "geometric"):
                                status = "fallback"
                            else:
                                status = "broken"
                        elif topo_index is not None:
                            status = "broken"
                            method = "index"
                        else:
                            continue

                        if status == "ok":
                            feat_report['ok'] += 1
                            report['ok'] += 1
                        elif status == "fallback":
                            feat_report['fallback'] += 1
                            report['fallback'] += 1
                        else:
                            feat_report['broken'] += 1
                            report['broken'] += 1

                        feat_report['refs'].append({
                            'kind': ref_kind, 'status': status, 'method': method
                        })

            _enforce_feature_status_truth(feat, feat_report)
            if feat_report['broken'] > 0:
                feat_report['status'] = 'broken'
            elif feat_report['fallback'] > 0:
                feat_report['status'] = 'fallback'
            elif feat_report['ok'] > 0:
                feat_report['status'] = 'ok'

            report['features'].append(feat_report)

        if report['broken'] > 0:
            report['status'] = 'broken'
        elif report['fallback'] > 0:
            report['status'] = 'fallback'

        return report
