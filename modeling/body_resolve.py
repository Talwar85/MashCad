"""
Body Resolve Mixin - Extracted from body.py

Contains _resolve_* methods for TNP (Topology Naming Protocol) resolution.
This mixin is designed to be inherited by the Body class.
"""

from typing import List, Optional, Dict
from loguru import logger

from config.feature_flags import is_enabled
from modeling.tnp_system import ShapeType

from modeling.features.extrude import ExtrudeFeature
from modeling.features.advanced import (
    ThreadFeature, HoleFeature, DraftFeature, ShellFeature, HollowFeature
)


class BodyResolveMixin:
    """
    Mixin class containing TNP resolution methods for Body.
    
    These methods handle the resolution of topological references (faces, edges)
    using the TNP (Topology Naming Protocol) system.
    """

    def _resolve_path(self, path_data: dict, current_solid, feature: Optional['SweepFeature'] = None):
        """
        LÃ¶st Pfad-Daten zu Build123d Wire auf.

        Args:
            path_data: Dict mit edge_indices, sketch_id, etc.
            current_solid: Aktueller Solid fÃ¼r Body-Edge-AuflÃ¶sung

        Returns:
            Build123d Wire oder None
        """
        if not path_data:
            return None

        try:
            path_type = path_data.get('type', 'body_edge')

            if path_type == 'sketch_edge':
                # Sketch-Edge zu Wire konvertieren
                return self._sketch_edge_to_wire(path_data)

            elif path_type == 'body_edge':
                from build123d import Wire, Edge

                source_solid = current_solid
                source_body_id = path_data.get("body_id")
                if source_body_id and self._document and hasattr(self._document, "find_body_by_id"):
                    ref_body = self._document.find_body_by_id(source_body_id)
                    if ref_body is not None and getattr(ref_body, "_build123d_solid", None) is not None:
                        source_solid = ref_body._build123d_solid

                all_edges = list(source_solid.edges()) if source_solid and hasattr(source_solid, 'edges') else []
                edge_indices = list(path_data.get("edge_indices") or [])
                has_topological_path_refs = bool(edge_indices)
                if feature and getattr(feature, "path_shape_id", None) is not None:
                    has_topological_path_refs = True
                shape_service = None
                if self._document and hasattr(self._document, '_shape_naming_service'):
                    shape_service = self._document._shape_naming_service

                def _persist_path_shape_id(edge_obj) -> None:
                    if not feature or not shape_service or feature.path_shape_id is not None:
                        return
                    try:
                        shape_id = shape_service.find_shape_id_by_edge(edge_obj)
                        if shape_id is None and hasattr(edge_obj, 'wrapped'):
                            ec = edge_obj.center()
                            edge_len = edge_obj.length if hasattr(edge_obj, 'length') else 0.0
                            shape_id = shape_service.register_shape(
                                ocp_shape=edge_obj.wrapped,
                                shape_type=ShapeType.EDGE,
                                feature_id=feature.id,
                                local_index=0,
                                geometry_data=(ec.X, ec.Y, ec.Z, edge_len)
                            )
                        if shape_id is not None:
                            feature.path_shape_id = shape_id
                    except Exception as e:
                        logger.debug(f"Sweep: Konnte Path-ShapeID nicht persistieren: {e}")

                resolved_index_edges = []
                if edge_indices and all_edges:
                    try:
                        from modeling.topology_indexing import edge_from_index
                        for edge_idx in edge_indices:
                            resolved = edge_from_index(source_solid, int(edge_idx))
                            if resolved is not None:
                                resolved_index_edges.append(resolved)
                    except Exception as e:
                        logger.debug(f"Sweep: Topology-Index-PfadauflÃ¶sung fehlgeschlagen: {e}")

                resolved_shape_edge = None
                path_shape_resolution_method = ""
                if feature and feature.path_shape_id and shape_service:
                    try:
                        resolved_ocp, method = shape_service.resolve_shape_with_method(
                            feature.path_shape_id, source_solid
                        )
                        path_shape_resolution_method = str(method or "").strip().lower()
                        if resolved_ocp is not None:
                            if all_edges:
                                resolved_shape_edge = self._find_matching_edge_in_solid(
                                    resolved_ocp, all_edges, tolerance=0.1
                                )
                            if resolved_shape_edge is None:
                                resolved_shape_edge = Edge(resolved_ocp)
                            if is_enabled("tnp_debug_logging"):
                                logger.debug(f"Sweep: Path via ShapeID aufgelÃ¶st (method={method})")
                    except Exception as e:
                        logger.debug(f"Sweep: Path-ShapeID AuflÃ¶sung fehlgeschlagen: {e}")

                strict_path_mismatch = False
                single_path_ref_pair = bool(
                    feature
                    and getattr(feature, "path_shape_id", None) is not None
                    and len(edge_indices) == 1
                )
                if edge_indices and feature and getattr(feature, "path_shape_id", None) is not None:
                    if not resolved_index_edges or resolved_shape_edge is None:
                        strict_path_mismatch = True
                    else:
                        strict_path_mismatch = not any(
                            self._is_same_edge(idx_edge, resolved_shape_edge)
                            for idx_edge in resolved_index_edges
                        )

                if strict_path_mismatch and single_path_ref_pair:
                    index_resolved = bool(resolved_index_edges)
                    shape_resolved = resolved_shape_edge is not None
                    pair_conflict = False
                    if index_resolved and shape_resolved:
                        pair_conflict = not any(
                            self._is_same_edge(idx_edge, resolved_shape_edge)
                            for idx_edge in resolved_index_edges
                        )
                    weak_shape_resolution = path_shape_resolution_method in {"geometric", "geometry_hash"}

                    if index_resolved and (not shape_resolved):
                        strict_path_mismatch = False
                        if feature is not None:
                            feature.path_shape_id = None
                        if is_enabled("tnp_debug_logging"):
                            logger.warning(
                                "Sweep: single_ref_pair path ShapeID nicht aufloesbar -> "
                                "verwende index-basierten Pfad."
                            )
                    elif index_resolved and shape_resolved and pair_conflict and weak_shape_resolution:
                        strict_path_mismatch = False
                        if feature is not None:
                            feature.path_shape_id = None
                        self._record_tnp_failure(
                            feature=feature,
                            category="drift",
                            reference_kind="edge",
                            reason="single_ref_pair_geometric_shape_conflict_index_preferred",
                            expected=max(1, len(edge_indices)),
                            resolved=1,
                            strict=False,
                        )
                        if is_enabled("tnp_debug_logging"):
                            logger.warning(
                                "Sweep: single_ref_pair Path Shape/Index-Konflikt mit schwacher "
                                "Shape-Aufloesung (geometric/hash) -> index-basierten Pfad bevorzugt."
                            )

                if strict_path_mismatch:
                    logger.warning(
                        "Sweep: TNP-Pfadreferenz ist inkonsistent "
                        "(path_shape_id != path_data.edge_indices). Kein Geometric-Fallback."
                    )
                    self._record_tnp_failure(
                        feature=feature,
                        category="mismatch",
                        reference_kind="edge",
                        reason="sweep_path_shape_index_mismatch",
                        expected=max(1, len(edge_indices)),
                        resolved=int(bool(resolved_shape_edge)) + int(bool(resolved_index_edges)),
                        strict=True,
                    )
                    return None

                if resolved_index_edges:
                    _persist_path_shape_id(resolved_index_edges[0])
                    return Wire(resolved_index_edges)

                if resolved_shape_edge is not None:
                    return Wire([resolved_shape_edge])

                # Wenn explizite TNP-Referenzen vorhanden sind, kein stilles Recovery Ã¼ber Legacy/Session-Pfade.
                if has_topological_path_refs:
                    logger.warning(
                        "Sweep: TNP-Pfadreferenz konnte nicht aufgelÃ¶st werden "
                        "(ShapeID/edge_indices). Kein Geometric-Fallback."
                    )
                    self._record_tnp_failure(
                        feature=feature,
                        category="missing_ref",
                        reference_kind="edge",
                        reason="sweep_path_unresolved_topology_reference",
                        expected=max(1, len(edge_indices)),
                        resolved=0,
                        strict=True,
                    )
                    return None

                # TNP v4.0 Fallback: GeometricEdgeSelector (Feature-Feld oder path_data)
                path_geo_selector = getattr(feature, 'path_geometric_selector', None) if feature else None
                if path_geo_selector is None:
                    path_geo_selector = path_data.get('path_geometric_selector')
                if path_geo_selector and all_edges:
                    try:
                        from modeling.geometric_selector import GeometricEdgeSelector
                        if isinstance(path_geo_selector, dict):
                            geo_sel = GeometricEdgeSelector.from_dict(path_geo_selector)
                        else:
                            geo_sel = path_geo_selector

                        best_edge = geo_sel.find_best_match(all_edges)
                        if best_edge is not None:
                            _persist_path_shape_id(best_edge)
                            return Wire([best_edge])
                    except Exception as e:
                        logger.debug(f"Sweep: GeometricEdgeSelector Fallback fehlgeschlagen: {e}")

                # SekundÃ¤r: Direkte Build123d Edges (Session-basiert)
                build123d_edges = path_data.get('build123d_edges', [])
                if build123d_edges:
                    _persist_path_shape_id(build123d_edges[0])
                    logger.debug(f"Sweep: Verwende {len(build123d_edges)} direkte Build123d Edge(s)")
                    return Wire(build123d_edges)

                # SekundÃ¤r: Direkte Einzel-Edge (Session-basiert)
                direct_edge = path_data.get('edge')
                if direct_edge is not None:
                    _persist_path_shape_id(direct_edge)
                    return Wire([direct_edge])

                if path_data.get("edge_selector") is not None:
                    logger.warning(
                        "Sweep: Legacy path_data.edge_selector wird nicht mehr aufgelÃ¶st. "
                        "Bitte Pfad neu auswÃ¤hlen (TNP v4: edge_indices/ShapeID)."
                    )

            return None

        except Exception as e:
            logger.debug(f"Pfad-AuflÃ¶sung fehlgeschlagen: {e}")
            return None

    def _sketch_edge_to_wire(self, path_data: dict):
        """
        Konvertiert Sketch-Edge zu Build123d Wire.

        UnterstÃ¼tzte Typen:
        - arc: Bogen mit center, radius, start_angle, end_angle
        - line: Linie mit start, end
        - spline: Spline mit control_points
        - polyline: Polylinie mit points

        Args:
            path_data: Dict mit geometry_type und entsprechenden Parametern

        Returns:
            Build123d Wire oder None
        """
        try:
            from build123d import Wire, Edge, Vector, Plane
            import numpy as np

            geom_type = path_data.get('geometry_type', 'line')
            plane_origin = path_data.get('plane_origin', (0, 0, 0))
            plane_normal = path_data.get('plane_normal', (0, 0, 1))
            plane_x = path_data.get('plane_x', (1, 0, 0))
            plane_y = path_data.get('plane_y', (0, 1, 0))

            def to_3d(x, y):
                """Konvertiert 2D Sketch-Koordinaten zu 3D"""
                o = np.array(plane_origin)
                px = np.array(plane_x)
                py = np.array(plane_y)
                return tuple(o + x * px + y * py)

            if geom_type == 'arc':
                # Bogen
                center_2d = path_data.get('center', (0, 0))
                radius = path_data.get('radius', 10.0)
                start_angle = path_data.get('start_angle', 0.0)
                end_angle = path_data.get('end_angle', 90.0)

                center_3d = to_3d(center_2d[0], center_2d[1])

                # Build123d Arc erstellen
                from build123d import ThreePointArc
                import math

                # Start- und Endpunkt berechnen
                start_rad = math.radians(start_angle)
                mid_rad = math.radians((start_angle + end_angle) / 2)
                end_rad = math.radians(end_angle)

                start_2d = (center_2d[0] + radius * math.cos(start_rad),
                           center_2d[1] + radius * math.sin(start_rad))
                mid_2d = (center_2d[0] + radius * math.cos(mid_rad),
                         center_2d[1] + radius * math.sin(mid_rad))
                end_2d = (center_2d[0] + radius * math.cos(end_rad),
                         center_2d[1] + radius * math.sin(end_rad))

                start_3d = to_3d(*start_2d)
                mid_3d = to_3d(*mid_2d)
                end_3d = to_3d(*end_2d)

                arc = ThreePointArc(Vector(*start_3d), Vector(*mid_3d), Vector(*end_3d))
                return Wire([arc])

            elif geom_type == 'line':
                # Linie
                start_2d = path_data.get('start', (0, 0))
                end_2d = path_data.get('end', (10, 0))

                start_3d = to_3d(*start_2d)
                end_3d = to_3d(*end_2d)

                from build123d import Line
                line = Line(Vector(*start_3d), Vector(*end_3d))
                return Wire([line])

            elif geom_type == 'spline':
                # Spline
                control_points = path_data.get('control_points', [])
                if len(control_points) < 2:
                    return None

                points_3d = [Vector(*to_3d(p[0], p[1])) for p in control_points]

                from build123d import Spline
                spline = Spline(*points_3d)
                return Wire([spline])

            elif geom_type == 'polyline':
                # Polylinie (mehrere verbundene Linien)
                points = path_data.get('points', [])
                if len(points) < 2:
                    return None

                from build123d import Line
                edges = []
                for i in range(len(points) - 1):
                    start_3d = to_3d(*points[i])
                    end_3d = to_3d(*points[i + 1])
                    edges.append(Line(Vector(*start_3d), Vector(*end_3d)))

                return Wire(edges)

            logger.warning(f"Unbekannter Sketch-Edge-Typ: {geom_type}")
            return None

        except Exception as e:
            logger.error(f"Sketch-Edge zu Wire Konvertierung fehlgeschlagen: {e}")
            return None

    def _score_face_match(self, face, geo_selector) -> float:
        """
        Berechnet Match-Score (0-1) zwischen Face und GeometricFaceSelector.
        TNP-robustes Face-Matching basierend auf mehreren Kriterien.
        
        Args:
            face: Build123d Face
            geo_selector: GeometricFaceSelector mit center, normal, area, surface_type
            
        Returns:
            Score zwischen 0 (kein Match) und 1 (perfektes Match)
        """
        try:
            import numpy as np
            
            # Center-Distanz (wichtigstes Kriterium)
            fc = face.center()
            face_center = np.array([fc.X, fc.Y, fc.Z])
            selector_center = np.array(geo_selector.center)
            dist = np.linalg.norm(face_center - selector_center)
            
            # Normalisierter Distanz-Score (1.0 = gleich, 0.0 = auÃŸerhalb Toleranz)
            tolerance = getattr(geo_selector, 'tolerance', 10.0)
            center_score = max(0.0, 1.0 - (dist / tolerance))
            
            # Normalen-Ã„hnlichkeit
            try:
                fn = face.normal_at(fc)
                face_normal = np.array([fn.X, fn.Y, fn.Z])
                selector_normal = np.array(geo_selector.normal)
                
                # Normalisieren
                face_normal = face_normal / (np.linalg.norm(face_normal) + 1e-10)
                selector_normal = selector_normal / (np.linalg.norm(selector_normal) + 1e-10)
                
                # Dot-Product (1.0 = gleiche Richtung, -1.0 = entgegengesetzt)
                dot = abs(np.dot(face_normal, selector_normal))  # Abs fÃ¼r beide Richtungen
                normal_score = dot
            except Exception as e:
                logger.debug(f"[__init__.py] Fehler: {e}")
                normal_score = 0.5  # Neutral wenn Normal nicht berechenbar
            
            # Area-Ã„hnlichkeit (20% Toleranz)
            try:
                face_area = face.area
                selector_area = geo_selector.area
                if selector_area > 0:
                    area_ratio = min(face_area, selector_area) / max(face_area, selector_area)
                    area_score = area_ratio
                else:
                    area_score = 0.5
            except Exception as e:
                logger.debug(f"[__init__.py] Fehler: {e}")
                area_score = 0.5
            
            # Gewichteter Gesamt-Score
            # Center ist wichtigster, dann Normal, dann Area
            total_score = (0.5 * center_score + 
                          0.3 * normal_score + 
                          0.2 * area_score)
            
            return total_score
            
        except Exception as e:
            logger.debug(f"Face-Scoring fehlgeschlagen: {e}")
            return 0.0

    def _resolve_feature_faces(self, feature, solid):
        """
        TNP v4.0: LÃ¶st Face-Referenzen eines Features auf und migriert Legacy-Daten.

        Reihenfolge:
        1. ShapeIDs via ShapeNamingService
        2. Topologie-Indizes via topology_indexing.face_from_index
        3. GeometricFaceSelector-Fallback nur ohne Topologie-Referenzen.
        """
        if solid is None or not hasattr(solid, 'faces'):
            return []

        all_faces = list(solid.faces())
        if not all_faces:
            return []

        from modeling.geometric_selector import GeometricFaceSelector

        # Feature-spezifische Felder bestimmen
        single_shape_attr = None
        single_index_attr = None
        single_selector_attr = None
        if isinstance(feature, HollowFeature):
            shape_attr = "opening_face_shape_ids"
            index_attr = "opening_face_indices"
            selector_attr = "opening_face_selectors"
        elif isinstance(feature, ShellFeature):
            shape_attr = "face_shape_ids"
            index_attr = "face_indices"
            selector_attr = "opening_face_selectors"
        elif isinstance(feature, (ThreadFeature, ExtrudeFeature)):
            # Thread/Push-Pull nutzen singulÃ¤re Face-Referenzen.
            shape_attr = None
            index_attr = None
            selector_attr = None
            single_shape_attr = "face_shape_id"
            single_index_attr = "face_index"
            single_selector_attr = "face_selector"
        else:
            shape_attr = "face_shape_ids"
            index_attr = "face_indices"
            selector_attr = "face_selectors"

        if single_shape_attr:
            single_shape = getattr(feature, single_shape_attr, None)
            single_index = getattr(feature, single_index_attr, None)
            single_selector = getattr(feature, single_selector_attr, None)

            shape_ids = [single_shape] if single_shape is not None else []
            face_indices = [single_index] if single_index is not None else []
            selectors = [single_selector] if single_selector else []
        else:
            shape_ids = list(getattr(feature, shape_attr, []) or [])
            face_indices = list(getattr(feature, index_attr, []) or [])
            selectors = list(getattr(feature, selector_attr, []) or [])
        if not shape_ids and not face_indices and not selectors:
            return []

        service = None
        if self._document and hasattr(self._document, '_shape_naming_service'):
            service = self._document._shape_naming_service

        resolved_faces = []
        resolved_shape_ids = []
        resolved_selector_indices = set()
        resolved_face_indices = []
        resolved_faces_from_shape = []
        resolved_faces_from_index = []
        shape_resolution_methods = {}

        strict_face_feature = isinstance(
            feature,
            (
                ExtrudeFeature,
                ThreadFeature,
                HoleFeature,
                DraftFeature,
                ShellFeature,
                HollowFeature,
            ),
        )
        single_ref_pair_index_preferred = False

        def _same_face(face_a, face_b) -> bool:
            try:
                wa = face_a.wrapped if hasattr(face_a, 'wrapped') else face_a
                wb = face_b.wrapped if hasattr(face_b, 'wrapped') else face_b
                return wa.IsSame(wb)
            except Exception:
                return face_a is face_b

        def _face_index(face_obj):
            for face_idx, candidate in enumerate(all_faces):
                if _same_face(candidate, face_obj):
                    return face_idx
            return None

        def _append_source_face(collection, face_obj) -> None:
            for existing in collection:
                if _same_face(existing, face_obj):
                    return
            collection.append(face_obj)

        def _append_face(face_obj, shape_id=None, selector_index=None, topo_index=None, source=None) -> None:
            if face_obj is None:
                return
            for existing in resolved_faces:
                if _same_face(existing, face_obj):
                    if source == "shape":
                        _append_source_face(resolved_faces_from_shape, existing)
                    elif source == "index":
                        _append_source_face(resolved_faces_from_index, existing)
                    return
            resolved_faces.append(face_obj)
            if source == "shape":
                _append_source_face(resolved_faces_from_shape, face_obj)
            elif source == "index":
                _append_source_face(resolved_faces_from_index, face_obj)
            if shape_id is not None:
                resolved_shape_ids.append(shape_id)
            if selector_index is not None:
                resolved_selector_indices.add(selector_index)
            if topo_index is None:
                topo_index = _face_index(face_obj)
            if topo_index is not None:
                try:
                    topo_index = int(topo_index)
                    if topo_index >= 0 and topo_index not in resolved_face_indices:
                        resolved_face_indices.append(topo_index)
                except Exception:
                    pass

        valid_face_indices = []
        for raw_idx in face_indices:
            try:
                face_idx = int(raw_idx)
            except Exception:
                continue
            if face_idx >= 0 and face_idx not in valid_face_indices:
                valid_face_indices.append(face_idx)

        def _resolve_by_indices() -> None:
            if not valid_face_indices:
                return
            try:
                from modeling.topology_indexing import face_from_index

                for face_idx in valid_face_indices:
                    resolved_face = face_from_index(solid, face_idx)
                    _append_face(resolved_face, topo_index=face_idx, source="index")
            except Exception as e:
                logger.debug(f"{feature.name}: Face-Index AuflÃ¶sung fehlgeschlagen: {e}")

        def _resolve_by_shape_ids() -> None:
            if not service:
                return
            for idx, shape_id in enumerate(shape_ids):
                if not hasattr(shape_id, 'uuid'):
                    continue
                try:
                    resolved_ocp, method = service.resolve_shape_with_method(
                        shape_id,
                        solid,
                        log_unresolved=False,
                    )
                    shape_resolution_methods[str(getattr(shape_id, "uuid", "") or "")] = (
                        str(method or "").strip().lower()
                    )
                    if resolved_ocp is None:
                        continue
                    from build123d import Face
                    resolved_face = Face(resolved_ocp)
                    _append_face(
                        resolved_face,
                        shape_id=shape_id,
                        selector_index=idx,
                        source="shape",
                    )
                    if is_enabled("tnp_debug_logging"):
                        logger.debug(
                            f"{feature.name}: Face via ShapeID aufgelÃ¶st "
                            f"(method={method})"
                        )
                except Exception as e:
                    logger.debug(f"{feature.name}: Face-ShapeID AuflÃ¶sung fehlgeschlagen: {e}")

        expected_shape_refs = sum(1 for sid in shape_ids if hasattr(sid, "uuid"))
        single_ref_pair = bool(
            single_shape_attr
            and expected_shape_refs == 1
            and len(valid_face_indices) == 1
        )
        shape_ids_index_aligned = True
        if expected_shape_refs > 0 and valid_face_indices and not single_ref_pair:
            for sid in shape_ids:
                if not hasattr(sid, "uuid"):
                    continue
                local_idx = getattr(sid, "local_index", None)
                if not isinstance(local_idx, int) or not (0 <= int(local_idx) < len(valid_face_indices)):
                    shape_ids_index_aligned = False
                    break
        strict_dual_face_refs = (
            strict_face_feature
            and expected_shape_refs > 0
            and bool(valid_face_indices)
            and len(valid_face_indices) == expected_shape_refs
            and (shape_ids_index_aligned or single_ref_pair)
        )
        prefer_shape_first = bool(
            single_shape_attr
            and expected_shape_refs > 0
            and (not valid_face_indices or shape_ids_index_aligned or single_ref_pair)
        )

        # TNP v4.0:
        # - Extrude/Thread (single-face): shape-first fÃ¼r semantische StabilitÃ¤t.
        # - Alle anderen: index-first, um Topologie-Indizes als PrimÃ¤rreferenz zu nutzen.
        if prefer_shape_first:
            _resolve_by_shape_ids()
            if strict_dual_face_refs or (len(resolved_shape_ids) < expected_shape_refs and valid_face_indices):
                _resolve_by_indices()
        elif valid_face_indices:
            _resolve_by_indices()
            indices_complete = len(resolved_face_indices) >= len(valid_face_indices)
            if strict_dual_face_refs or not indices_complete:
                _resolve_by_shape_ids()
        else:
            _resolve_by_shape_ids()
            _resolve_by_indices()

        strict_topology_mismatch = False
        if strict_dual_face_refs:
            if (
                len(resolved_faces_from_index) < len(valid_face_indices)
                or len(resolved_faces_from_shape) < expected_shape_refs
            ):
                strict_topology_mismatch = True
            else:
                for idx_face in resolved_faces_from_index:
                    if not any(_same_face(idx_face, shape_face) for shape_face in resolved_faces_from_shape):
                        strict_topology_mismatch = True
                        break
                if not strict_topology_mismatch:
                    for shape_face in resolved_faces_from_shape:
                        if not any(_same_face(shape_face, idx_face) for idx_face in resolved_faces_from_index):
                            strict_topology_mismatch = True
                            break
        if strict_dual_face_refs and strict_topology_mismatch and single_ref_pair:
            shape_resolved = bool(resolved_faces_from_shape)
            index_resolved = bool(resolved_faces_from_index)
            pair_conflict = False
            if shape_resolved and index_resolved:
                pair_conflict = not any(
                    _same_face(resolved_faces_from_shape[0], idx_face)
                    for idx_face in resolved_faces_from_index
                )

            weak_shape_resolution = False
            if shape_resolved and expected_shape_refs == 1:
                for sid in shape_ids:
                    sid_uuid = str(getattr(sid, "uuid", "") or "")
                    if not sid_uuid:
                        continue
                    method = shape_resolution_methods.get(sid_uuid, "")
                    weak_shape_resolution = method in {"geometric", "geometry_hash"}
                    break

            if index_resolved and (not shape_resolved):
                resolved_faces = list(resolved_faces_from_index)
                resolved_shape_ids = []
                strict_topology_mismatch = False
                single_ref_pair_index_preferred = True
                if is_enabled("tnp_debug_logging"):
                    logger.warning(
                        f"{feature.name}: single_ref_pair Face-ShapeID nicht aufloesbar -> "
                        "verwende index-basierte Face-Aufloesung."
                    )
            elif index_resolved and shape_resolved and pair_conflict and weak_shape_resolution:
                resolved_faces = list(resolved_faces_from_index)
                resolved_shape_ids = []
                strict_topology_mismatch = False
                single_ref_pair_index_preferred = True
                self._record_tnp_failure(
                    feature=feature,
                    category="drift",
                    reference_kind="face",
                    reason="single_ref_pair_geometric_shape_conflict_index_preferred",
                    expected=max(len(valid_face_indices), expected_shape_refs),
                    resolved=len(resolved_faces),
                    strict=False,
                )
                if is_enabled("tnp_debug_logging"):
                    logger.warning(
                        f"{feature.name}: single_ref_pair Shape/Index-Konflikt mit schwacher "
                        "Face-Shape-Aufloesung (geometric/hash) -> index-basierte Face-Aufloesung bevorzugt."
                    )
            else:
                if is_enabled("tnp_debug_logging"):
                    reason = "Shape/Index-Konflikt" if pair_conflict else "strict single_ref_pair mismatch"
                    logger.warning(f"{feature.name}: {reason} -> Abbruch ohne Fallback.")
                self._record_tnp_failure(
                    feature=feature,
                    category="mismatch",
                    reference_kind="face",
                    reason="single_ref_pair_conflict" if pair_conflict else "strict_single_ref_pair_mismatch",
                    expected=max(len(valid_face_indices), expected_shape_refs),
                    resolved=max(len(resolved_face_indices), len(resolved_shape_ids)),
                    strict=bool(strict_face_feature),
                )
                return []

        has_topological_refs = bool(valid_face_indices or expected_shape_refs > 0)
        unresolved_topology_refs = (
            (valid_face_indices and len(resolved_face_indices) < len(valid_face_indices))
            or (
                expected_shape_refs > 0
                and not valid_face_indices
                and len(resolved_shape_ids) < expected_shape_refs
            )
        )
        if strict_dual_face_refs and strict_topology_mismatch:
            unresolved_topology_refs = True
        # Strict fÃ¼r single-face Referenzen: wenn ShapeID vorhanden aber nicht
        # auflÃ¶sbar, nicht still auf potentiell falschen Index degradieren.
        if (
            prefer_shape_first
            and expected_shape_refs > 0
            and len(resolved_shape_ids) < expected_shape_refs
            and not single_ref_pair_index_preferred
        ):
            unresolved_topology_refs = True

        if has_topological_refs and unresolved_topology_refs:
            mismatch_hint = " (ShapeID/Index-Mismatch)" if strict_topology_mismatch else ""
            logger.warning(
                f"{feature.name}: Face-Referenz ist ungÃ¼ltig (ShapeID/face_indices). "
                f"Kein Geometric-Fallback.{mismatch_hint}"
            )
            self._record_tnp_failure(
                feature=feature,
                category="mismatch" if strict_topology_mismatch else "missing_ref",
                reference_kind="face",
                reason="shape_index_mismatch" if strict_topology_mismatch else "unresolved_topology_reference",
                expected=max(len(valid_face_indices), expected_shape_refs),
                resolved=max(len(resolved_face_indices), len(resolved_shape_ids)),
                strict=bool(strict_face_feature),
            )
            return []

        need_selector_recovery = (not has_topological_refs) and (not resolved_faces)

        # 3) Geometric selector fallback (nur Recovery)
        if need_selector_recovery:
            for idx, selector_data in enumerate(selectors):
                if idx in resolved_selector_indices:
                    continue

                try:
                    if isinstance(selector_data, dict):
                        geo_sel = GeometricFaceSelector.from_dict(selector_data)
                    elif hasattr(selector_data, 'find_best_match'):
                        geo_sel = selector_data
                    else:
                        continue
                except Exception:
                    continue

                best_face = geo_sel.find_best_match(all_faces)
                if best_face is None:
                    continue

                shape_id = None
                if service:
                    try:
                        shape_id = service.find_shape_id_by_face(best_face)
                        if shape_id is None and hasattr(best_face, 'wrapped'):
                            fc = best_face.center()
                            area = best_face.area if hasattr(best_face, 'area') else 0.0
                            shape_id = service.register_shape(
                                ocp_shape=best_face.wrapped,
                                shape_type=ShapeType.FACE,
                                feature_id=feature.id,
                                local_index=idx,
                                geometry_data=(fc.X, fc.Y, fc.Z, area)
                            )
                    except Exception as e:
                        logger.debug(f"{feature.name}: Face-ShapeID Registrierung fehlgeschlagen: {e}")

                _append_face(best_face, shape_id=shape_id, selector_index=idx)

        if not resolved_faces:
            return []

        def _face_sort_key(face_obj):
            face_idx = _face_index(face_obj)
            if face_idx is not None:
                return (0, int(face_idx))
            try:
                center = face_obj.center()
                area = float(face_obj.area if hasattr(face_obj, "area") else 0.0)
                return (
                    1,
                    round(float(center.X), 6),
                    round(float(center.Y), 6),
                    round(float(center.Z), 6),
                    round(area, 6),
                )
            except Exception:
                return (2, str(face_obj))

        resolved_faces = sorted(resolved_faces, key=_face_sort_key)
        resolved_face_indices = sorted(
            {
                int(idx)
                for idx in resolved_face_indices
                if isinstance(idx, int) and int(idx) >= 0
            }
        )

        # PI-002: ShapeIDs in derselben stabilen Reihenfolge wie Face-Indizes persistieren.
        if service is not None and resolved_faces:
            canonical_shape_ids = []
            for local_idx, face_obj in enumerate(resolved_faces):
                shape_id = None
                try:
                    shape_id = service.find_shape_id_by_face(face_obj, require_exact=True)
                except Exception:
                    shape_id = None
                if shape_id is None:
                    try:
                        shape_id = service.find_shape_id_by_face(face_obj)
                    except Exception:
                        shape_id = None
                if shape_id is None and hasattr(face_obj, "wrapped"):
                    try:
                        fc = face_obj.center()
                        area = face_obj.area if hasattr(face_obj, "area") else 0.0
                        shape_id = service.register_shape(
                            ocp_shape=face_obj.wrapped,
                            shape_type=ShapeType.FACE,
                            feature_id=feature.id,
                            local_index=local_idx,
                            geometry_data=(fc.X, fc.Y, fc.Z, area),
                        )
                    except Exception:
                        shape_id = None
                if shape_id is not None:
                    canonical_shape_ids.append(shape_id)
            if canonical_shape_ids:
                resolved_shape_ids = canonical_shape_ids

        # Persistiere aktualisierte Referenzen zurÃ¼ck ins Feature
        try:
            updated_selectors = [
                GeometricFaceSelector.from_face(face).to_dict()
                for face in resolved_faces
            ]
            # Nicht-topologische Zusatzdaten (z. B. cell_ids fÃ¼rs Overlay) beibehalten.
            for idx, updated in enumerate(updated_selectors):
                if idx >= len(selectors):
                    continue
                original = selectors[idx]
                if not isinstance(original, dict):
                    continue
                for key, value in original.items():
                    if key not in updated:
                        updated[key] = value
            if single_selector_attr:
                setattr(feature, single_selector_attr, updated_selectors[0] if updated_selectors else None)
            else:
                setattr(feature, selector_attr, updated_selectors)
        except Exception as e:
            logger.debug(f"{feature.name}: Selector-Update fehlgeschlagen: {e}")

        if single_shape_attr:
            if resolved_shape_ids:
                setattr(feature, single_shape_attr, resolved_shape_ids[0])
        elif resolved_shape_ids:
            setattr(feature, shape_attr, resolved_shape_ids)

        if single_index_attr:
            if resolved_face_indices:
                setattr(feature, single_index_attr, resolved_face_indices[0])
        elif resolved_face_indices:
            setattr(feature, index_attr, resolved_face_indices)

        return resolved_faces

    def _resolve_faces_for_shell(self, solid, face_selectors: List[dict],
                                feature: 'ShellFeature' = None):
        """
        LÃ¶st Face-Selektoren fÃ¼r Shell-Operation auf.
        
        Verwendet TNP v4.0 wenn ShapeNamingService verfÃ¼gbar.
        """
        if solid is None or not face_selectors:
            return []

        all_faces = list(solid.faces()) if hasattr(solid, 'faces') else []
        if not all_faces:
            return []

        resolved_faces = []
        
        for selector in face_selectors:
            # Try ShapeID first
            shape_id = selector.get('shape_id')
            if shape_id and self._document and hasattr(self._document, '_shape_naming_service'):
                try:
                    service = self._document._shape_naming_service
                    resolved_ocp, method = service.resolve_shape_with_method(shape_id, solid)
                    if resolved_ocp is not None:
                        from build123d import Face
                        resolved_face = Face(resolved_ocp)
                        # Find matching face in solid
                        for face in all_faces:
                            if self._is_same_face(face, resolved_face):
                                resolved_faces.append(face)
                                break
                        continue
                except Exception as e:
                    logger.debug(f"Shell Face ShapeID resolution failed: {e}")
            
            # Try index
            face_index = selector.get('face_index')
            if face_index is not None:
                try:
                    from modeling.topology_indexing import face_from_index
                    resolved_face = face_from_index(solid, int(face_index))
                    if resolved_face is not None:
                        resolved_faces.append(resolved_face)
                        continue
                except Exception as e:
                    logger.debug(f"Shell Face index resolution failed: {e}")
            
            # Try geometric selector
            geo_selector = selector.get('geometric_selector')
            if geo_selector and isinstance(geo_selector, dict):
                try:
                    from modeling.geometric_selector import GeometricFaceSelector
                    geo_sel = GeometricFaceSelector.from_dict(geo_selector)
                    best_face = geo_sel.find_best_match(all_faces)
                    if best_face is not None:
                        resolved_faces.append(best_face)
                except Exception as e:
                    logger.debug(f"Shell Face geometric resolution failed: {e}")

        return resolved_faces

    def _resolve_edges_tnp(self, solid, feature) -> List:
        """
        TNP v4.1 Edge-AuflÃ¶sung mit History-First Strategie.

        Reihenfolge (STRICT):
        1. OperationRecord-Mappings (History-basiert)
        2. edge_shape_ids mit direkter AuflÃ¶sung
        3. edge_indices (Topology-Index)
        4. geometric_selectors (NUR LETZTE OPTION)

        WICHTIG: Wenn History-First versagt und keine andere Methode funktioniert,
        soll das Feature fehlschlagen statt auf Geometric-Fallback zurÃ¼ckzufallen.
        """
        # Import here to avoid circular imports
        from modeling.features.fillet_chamfer import FilletFeature, ChamferFeature
        
        all_edges = list(solid.edges()) if hasattr(solid, 'edges') else []
        if not all_edges:
            if is_enabled("tnp_debug_logging"):
                logger.warning("TNP v4.0: Keine Edges im Solid gefunden")
            return []

        feature_name = getattr(feature, 'name', 'Unknown')
        edge_shape_ids = list(getattr(feature, 'edge_shape_ids', []) or [])
        edge_indices_raw = list(getattr(feature, 'edge_indices', []) or [])
        geometric_selectors = list(getattr(feature, 'geometric_selectors', []) or [])

        valid_edge_indices = []
        for raw_idx in edge_indices_raw:
            try:
                idx = int(raw_idx)
            except Exception:
                continue
            if idx >= 0 and idx not in valid_edge_indices:
                valid_edge_indices.append(idx)

        if is_enabled("tnp_debug_logging"):
            logger.info(
                f"TNP v4.0: Resolving edges for {feature_name} "
                f"(shape_ids={len(edge_shape_ids)}, indices={len(valid_edge_indices)}, "
                f"selectors={len(geometric_selectors)}, solid_edges={len(all_edges)})"
            )

        service = None
        if self._document and hasattr(self._document, '_shape_naming_service'):
            service = self._document._shape_naming_service

        resolved_edges = []
        unresolved_shape_ids = []  # FÃ¼r Debug-Visualisierung
        resolved_shape_ids = []
        resolved_edge_indices = []
        resolved_edges_from_shape = []
        resolved_edges_from_index = []
        shape_resolution_methods: Dict[str, str] = {}

        strict_edge_feature = isinstance(feature, (FilletFeature, ChamferFeature))

        def _edge_index_of(edge_obj):
            for edge_idx, candidate in enumerate(all_edges):
                if self._is_same_edge(candidate, edge_obj):
                    return edge_idx
            return None

        def _append_source_edge(collection, edge_obj) -> None:
            for existing in collection:
                if self._is_same_edge(existing, edge_obj):
                    return
            collection.append(edge_obj)

        def _append_unique(edge_obj, shape_id=None, topo_index=None, source=None) -> None:
            if edge_obj is None:
                return
            for existing in resolved_edges:
                if self._is_same_edge(existing, edge_obj):
                    if source == "shape":
                        _append_source_edge(resolved_edges_from_shape, existing)
                    elif source == "index":
                        _append_source_edge(resolved_edges_from_index, existing)
                    return
            resolved_edges.append(edge_obj)
            if source == "shape":
                _append_source_edge(resolved_edges_from_shape, edge_obj)
            elif source == "index":
                _append_source_edge(resolved_edges_from_index, edge_obj)
            if shape_id is not None:
                resolved_shape_ids.append(shape_id)
            if topo_index is None:
                topo_index = _edge_index_of(edge_obj)
            if topo_index is not None:
                try:
                    topo_index = int(topo_index)
                    if topo_index >= 0 and topo_index not in resolved_edge_indices:
                        resolved_edge_indices.append(topo_index)
                except Exception:
                    pass

        def _resolve_by_operation_records() -> int:
            """TNP v4.1: Zuerst OperationRecords nach Mappings durchsuchen."""
            if not service or not edge_shape_ids:
                return 0

            resolved_count = 0
            for op in service._operations:
                if op.manual_mappings and op.feature_id == getattr(feature, 'id', ''):
                    # PrÃ¼fe ob ShapeIDs in den Mappings vorhanden sind
                    for input_uuid, output_uuids in op.manual_mappings.items():
                        # Input-ShapeID finden
                        for shape_id in edge_shape_ids:
                            if hasattr(shape_id, 'uuid') and shape_id.uuid == input_uuid:
                                # Output-ShapeIDs finden
                                for output_uuid in output_uuids:
                                    if output_uuid in service._shapes:
                                        output_record = service._shapes[output_uuid]
                                        if output_record.ocp_shape:
                                            matching_edge = self._find_matching_edge_in_solid(
                                                output_record.ocp_shape, all_edges
                                            )
                                            if matching_edge is not None:
                                                _append_unique(matching_edge, shape_id=shape_id, source="shape")
                                                resolved_count += 1
                                                if is_enabled("tnp_debug_logging"):
                                                    logger.debug(
                                                        f"TNP v4.1: Edge via OperationRecord-Mapping aufgelÃ¶st: "
                                                        f"{input_uuid[:8]} â†’ {output_uuid[:8]}"
                                                    )
            return resolved_count

        def _resolve_by_shape_ids() -> None:
            if not edge_shape_ids or service is None:
                return
            for i, shape_id in enumerate(edge_shape_ids):
                if not hasattr(shape_id, "uuid"):
                    continue
                try:
                    resolved_ocp, method = service.resolve_shape_with_method(
                        shape_id,
                        solid,
                        log_unresolved=False,
                    )
                    shape_resolution_methods[str(getattr(shape_id, "uuid", "") or "")] = str(method or "").strip().lower()
                    if resolved_ocp is None:
                        unresolved_shape_ids.append(shape_id)
                        if is_enabled("tnp_debug_logging"):
                            logger.warning(f"TNP v4.0: Edge {i} konnte via ShapeID nicht aufgelÃ¶st werden")
                        continue

                    matching_edge = self._find_matching_edge_in_solid(resolved_ocp, all_edges)
                    if matching_edge is not None:
                        _append_unique(matching_edge, shape_id=shape_id, source="shape")
                        if is_enabled("tnp_debug_logging"):
                            logger.debug(f"TNP v4.0: Edge {i} via ShapeID aufgelÃ¶st (method={method})")
                    else:
                        unresolved_shape_ids.append(shape_id)
                        if is_enabled("tnp_debug_logging"):
                            logger.warning(f"TNP v4.0: Keine passende Solid-Edge fÃ¼r ShapeID-Edge {i}")
                except Exception as e:
                    unresolved_shape_ids.append(shape_id)
                    if is_enabled("tnp_debug_logging"):
                        logger.warning(f"TNP v4.0: Edge {i} ShapeID-AuflÃ¶sung fehlgeschlagen: {e}")

        def _resolve_by_indices() -> None:
            if not valid_edge_indices:
                return
            try:
                from modeling.topology_indexing import edge_from_index

                for edge_idx in valid_edge_indices:
                    resolved = edge_from_index(solid, int(edge_idx))
                    _append_unique(resolved, topo_index=edge_idx, source="index")
            except Exception as e:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP v4.0: Index-AuflÃ¶sung fehlgeschlagen: {e}")

        # Main resolution logic
        expected_shape_refs = sum(1 for sid in edge_shape_ids if hasattr(sid, "uuid"))
        
        # TNP v4.1: History-First Strategie
        op_resolved = _resolve_by_operation_records()
        if op_resolved > 0 and is_enabled("tnp_debug_logging"):
            logger.debug(f"TNP v4.1: {op_resolved} Edges via OperationRecords aufgelÃ¶st")

        # Then ShapeIDs
        if op_resolved < len(edge_shape_ids):
            _resolve_by_shape_ids()

        # Then Index-based
        if len(resolved_edges) < len(edge_shape_ids) or valid_edge_indices:
            _resolve_by_indices()

        # Geometric selector fallback
        # TNP v4.1: Block selector fallback when topological refs were provided but failed
        has_topo_refs = bool(edge_shape_ids) or bool(valid_edge_indices)
        topo_refs_failed = has_topo_refs and not resolved_edges
        strict_policy = is_enabled("strict_topology_fallback_policy")
        allow_selector_fallback = geometric_selectors and not resolved_edges and not (topo_refs_failed and strict_policy)

        selector_recovery_used = False
        if allow_selector_fallback:
            try:
                from modeling.geometric_selector import GeometricEdgeSelector

                for selector_data in geometric_selectors:
                    if isinstance(selector_data, dict):
                        geo_sel = GeometricEdgeSelector.from_dict(selector_data)
                    elif hasattr(selector_data, 'find_best_match'):
                        geo_sel = selector_data
                    else:
                        continue
                    matched = geo_sel.find_best_match(all_edges)
                    if matched is not None:
                        _append_unique(matched)
                        selector_recovery_used = True
            except Exception as e:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP v4.0: GeometricEdgeSelector-AuflÃ¶sung fehlgeschlagen: {e}")

            # Record drift when selector recovery was used
            if selector_recovery_used and not strict_policy:
                self._record_tnp_failure(
                    feature=feature,
                    category="drift",
                    reference_kind="edge",
                    reason="selector_recovery_used",
                    strict=False,
                )

        # Update feature references
        if resolved_edge_indices:
            feature.edge_indices = sorted({int(idx) for idx in resolved_edge_indices if int(idx) >= 0})

        if service is not None and resolved_edges:
            new_shape_ids = []
            for idx, edge in enumerate(resolved_edges):
                try:
                    shape_id = service.find_shape_id_by_edge(edge)
                    if shape_id is None and hasattr(edge, 'wrapped'):
                        ec = edge.center()
                        edge_len = edge.length if hasattr(edge, 'length') else 0.0
                        shape_id = service.register_shape(
                            ocp_shape=edge.wrapped,
                            shape_type=ShapeType.EDGE,
                            feature_id=feature.id,
                            local_index=idx,
                            geometry_data=(ec.X, ec.Y, ec.Z, edge_len),
                        )
                    if shape_id is not None:
                        new_shape_ids.append(shape_id)
                except Exception:
                    continue
            if new_shape_ids:
                feature.edge_shape_ids = new_shape_ids

        total_refs = max(len(edge_shape_ids), len(valid_edge_indices), len(geometric_selectors))
        found = len(resolved_edges)

        # TNP v4.2: Record missing_ref failure when refs were provided but nothing resolved
        if total_refs > 0 and found == 0 and strict_edge_feature:
            self._record_tnp_failure(
                feature=feature,
                category="missing_ref",
                reference_kind="edge",
                reason="no_edges_resolved_from_refs",
                expected=total_refs,
                resolved=0,
                strict=True,
            )
            if is_enabled("tnp_debug_logging"):
                logger.warning(f"TNP v4.2: No edges resolved for {feature_name} with {total_refs} refs")

        if is_enabled("tnp_debug_logging"):
            if total_refs == 0:
                logger.warning("TNP v4.0: Feature hat keine Edge-Referenzen")
            elif found >= total_refs:
                logger.debug(f"TNP v4.0: {found}/{total_refs} Edges aufgelÃ¶st")
            else:
                logger.warning(f"TNP v4.0: Nur {found}/{total_refs} Edges aufgelÃ¶st")
        
        # Debug visualization data
        self._last_tnp_debug_data = {
            'resolved': resolved_edges,
            'unresolved': unresolved_shape_ids,
            'body_id': self.id
        }
        
        # Callback fÃ¼r GUI-Visualisierung (wenn registriert)
        if hasattr(self._document, '_tnp_debug_callback') and self._document._tnp_debug_callback:
            try:
                self._document._tnp_debug_callback(resolved_edges, unresolved_shape_ids, self.id)
            except Exception as e:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP Debug Callback fehlgeschlagen: {e}")

        return resolved_edges
    
    def _validate_edge_in_solid(self, edge, all_edges, tolerance=0.01) -> bool:
        """Validiert ob eine Edge im Solid existiert (geometrischer Vergleich)"""
        try:
            import numpy as np
            
            edge_center = np.array([edge.center().X, edge.center().Y, edge.center().Z])
            
            for solid_edge in all_edges:
                solid_center = np.array([solid_edge.center().X, solid_edge.center().Y, solid_edge.center().Z])
                dist = np.linalg.norm(edge_center - solid_center)
                
                if dist < tolerance:
                    return True
                    
        except Exception:
            pass
            
        return False
    
    def _find_matching_edge_in_solid(self, resolved_ocp_edge, all_edges, tolerance=0.01):
        """
        Findet die passende Edge vom aktuellen Solid.
        
        OCP erwartet Edges die tatsÃ¤chlich im aktuellen Solid's BRep-Graph existieren,
        nicht Edges aus einem anderen Kontext (auch wenn sie geometrisch identisch sind).
        
        Args:
            resolved_ocp_edge: Die aufgelÃ¶ste OCP Edge (aus ShapeNamingService)
            all_edges: Liste aller Edges vom aktuellen Solid
            tolerance: Toleranz fÃ¼r geometrischen Vergleich
            
        Returns:
            Die passende Edge aus all_edges, oder None
        """
        try:
            import numpy as np
            from build123d import Edge
            wrapped = resolved_ocp_edge.wrapped if hasattr(resolved_ocp_edge, "wrapped") else resolved_ocp_edge

            # Nur Edge-Shapes gegen Edge-Listen matchen.
            try:
                from OCP.TopAbs import TopAbs_EDGE
                if hasattr(wrapped, "ShapeType") and wrapped.ShapeType() != TopAbs_EDGE:
                    return None
            except Exception as shape_type_err:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(
                        f"_find_matching_edge_in_solid: ShapeType-Pruefung uebersprungen ({shape_type_err})"
                    )
            
            # Center der aufgelÃ¶sten Edge
            resolved_b3d = Edge(wrapped)
            resolved_center = np.array([
                resolved_b3d.center().X, 
                resolved_b3d.center().Y, 
                resolved_b3d.center().Z
            ])
            
            # Finde die Edge im aktuellen Solid mit dem gleichen Center
            best_match = None
            best_dist = float('inf')
            
            for solid_edge in all_edges:
                solid_center = np.array([
                    solid_edge.center().X, 
                    solid_edge.center().Y, 
                    solid_edge.center().Z
                ])
                dist = np.linalg.norm(resolved_center - solid_center)
                
                if dist < tolerance and dist < best_dist:
                    best_dist = dist
                    best_match = solid_edge
            
            return best_match
            
        except Exception as e:
            logger.debug(f"_find_matching_edge_in_solid fehlgeschlagen: {e}")
            return None

    @staticmethod
    def _is_same_edge(edge_a, edge_b) -> bool:
        """
        Robuster Edge-Vergleich fÃ¼r TNP-Pfade.

        Bevorzugt OCP IsSame (Topologie-identisch), fÃ¤llt auf eine leichte
        Geometrie-PrÃ¼fung und zuletzt ObjektidentitÃ¤t zurÃ¼ck.
        """
        if edge_a is None or edge_b is None:
            return False
        try:
            wrapped_a = edge_a.wrapped if hasattr(edge_a, "wrapped") else edge_a
            wrapped_b = edge_b.wrapped if hasattr(edge_b, "wrapped") else edge_b
            if hasattr(wrapped_a, "IsSame") and wrapped_a.IsSame(wrapped_b):
                return True
        except Exception:
            pass
        try:
            center_a = edge_a.center()
            center_b = edge_b.center()
            dx = float(center_a.X) - float(center_b.X)
            dy = float(center_a.Y) - float(center_b.Y)
            dz = float(center_a.Z) - float(center_b.Z)
            if (dx * dx + dy * dy + dz * dz) <= 1e-12:
                len_a = float(getattr(edge_a, "length", 0.0) or 0.0)
                len_b = float(getattr(edge_b, "length", 0.0) or 0.0)
                if abs(len_a - len_b) <= 1e-9:
                    return True
        except Exception:
            pass
        return edge_a is edge_b


__all__ = ['BodyResolveMixin']
