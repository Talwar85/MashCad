"""
Body Rebuild Mixin - Extracted from body.py

Contains the _rebuild() method and related rebuild logic.
This mixin is designed to be inherited by the Body class.
"""

from typing import Optional
from loguru import logger

from config.feature_flags import is_enabled


class BodyRebuildMixin:
    """
    Mixin class containing the rebuild logic for Body.
    
    This handles the history-based rebuild process that applies
    all features sequentially to construct the final solid.
    """

    def _rebuild(self, rebuild_up_to=None, changed_feature_id: str = None, progress_callback=None):
        """
        Robuster Rebuild-Prozess (History-basiert).

        Args:
            rebuild_up_to: Optional int - nur Features bis zu diesem Index (exklusiv) anwenden.
                           None = alle Features. Wird fuer Rollback-Bar verwendet.
            changed_feature_id: Optional str - ID des geÃ¤nderten Features fÃ¼r inkrementellen Rebuild.
                                Phase 7: Nutzt Checkpoints fÃ¼r schnelleren Restart.
        """
        # Import here to avoid circular imports
        from modeling.features import (
            ChamferFeature, FilletFeature, PrimitiveFeature, ImportFeature,
            ExtrudeFeature, PushPullFeature, TransformFeature, RevolveFeature,
            LoftFeature, SweepFeature, ShellFeature, HollowFeature,
            LatticeFeature, NSidedPatchFeature, HoleFeature, DraftFeature,
            SplitFeature, ThreadFeature, SurfaceTextureFeature
        )
        from modeling.boolean_engine_v4 import BooleanEngineV4
        from modeling.ocp_helpers import OCPFilletHelper, OCPChamferHelper
        from modeling.geometry_validator import GeometryValidator, ValidationLevel
        from modeling.geometry_healer import GeometryHealer

        max_index = rebuild_up_to if rebuild_up_to is not None else len(self.features)
        strict_self_heal = is_enabled("self_heal_strict")

        def _solid_metrics(solid_obj) -> dict:
            if solid_obj is None:
                return {
                    "volume": None,
                    "faces": 0,
                    "edges": 0,
                    "bbox_lengths": None,
                    "bbox_center": None,
                    "bbox_diag": None,
                }
            try:
                volume = float(getattr(solid_obj, "volume", 0.0))
            except Exception:
                volume = None
            try:
                faces = len(list(solid_obj.faces()))
            except Exception:
                faces = 0
            try:
                edges = len(list(solid_obj.edges()))
            except Exception:
                edges = 0
            bbox_lengths = None
            bbox_center = None
            bbox_diag = None
            try:
                bb = solid_obj.bounding_box()
                min_x = float(bb.min.X)
                min_y = float(bb.min.Y)
                min_z = float(bb.min.Z)
                max_x = float(bb.max.X)
                max_y = float(bb.max.Y)
                max_z = float(bb.max.Z)
                lx = max_x - min_x
                ly = max_y - min_y
                lz = max_z - min_z
                bbox_lengths = (lx, ly, lz)
                bbox_center = (
                    0.5 * (min_x + max_x),
                    0.5 * (min_y + max_y),
                    0.5 * (min_z + max_z),
                )
                bbox_diag = float((lx * lx + ly * ly + lz * lz) ** 0.5)
            except Exception:
                pass
            return {
                "volume": volume,
                "faces": faces,
                "edges": edges,
                "bbox_lengths": bbox_lengths,
                "bbox_center": bbox_center,
                "bbox_diag": bbox_diag,
            }

        def _format_metrics(metrics: dict) -> str:
            volume = metrics.get("volume")
            if volume is None:
                vol_text = "n/a"
            else:
                vol_text = f"{volume:.3f}"
            diag = metrics.get("bbox_diag")
            diag_text = "n/a" if diag is None else f"{float(diag):.3f}"
            return (
                f"vol={vol_text}mmÂ³, "
                f"faces={metrics.get('faces', 0)}, "
                f"edges={metrics.get('edges', 0)}, "
                f"diag={diag_text}mm"
            )

        def _ensure_rollback_details(details: dict, rollback_from, rollback_to) -> dict:
            payload = dict(details or {})
            if "rollback" not in payload:
                payload["rollback"] = {
                    "from": rollback_from,
                    "to": rollback_to,
                }
            return payload

        def _is_local_modifier_feature(feat) -> bool:
            return isinstance(feat, (ChamferFeature, FilletFeature))

        def _local_modifier_drift_details(feat, before_metrics: dict, after_metrics: dict) -> Optional[dict]:
            if before_metrics is None or after_metrics is None:
                return None

            before_lengths = before_metrics.get("bbox_lengths")
            after_lengths = after_metrics.get("bbox_lengths")
            before_center = before_metrics.get("bbox_center")
            after_center = after_metrics.get("bbox_center")
            before_diag = before_metrics.get("bbox_diag")
            after_diag = after_metrics.get("bbox_diag")
            if (
                before_lengths is None or after_lengths is None
                or before_center is None or after_center is None
                or before_diag is None or after_diag is None
            ):
                return None

            if isinstance(feat, ChamferFeature):
                magnitude = abs(float(getattr(feat, "distance", 0.0) or 0.0))
                op_label = "Chamfer"
            else:
                magnitude = abs(float(getattr(feat, "radius", 0.0) or 0.0))
                op_label = "Fillet"

            max_axis_grow = max(0.25, 0.60 * magnitude)
            max_axis_shrink = max(1.60, 6.50 * magnitude)
            max_diag_grow = max(0.35, 0.95 * magnitude)
            max_diag_shrink = max(2.20, 8.00 * magnitude)
            max_center_shift = max(1.50, 6.00 * magnitude)

            drift_reasons = []
            max_axis_grow_seen = 0.0
            max_axis_shrink_seen = 0.0
            for axis_idx, (before_len, after_len) in enumerate(zip(before_lengths, after_lengths)):
                grow = float(after_len - before_len)
                shrink = float(before_len - after_len)
                max_axis_grow_seen = max(max_axis_grow_seen, grow)
                max_axis_shrink_seen = max(max_axis_shrink_seen, shrink)
                if grow > max_axis_grow:
                    drift_reasons.append(f"axis{axis_idx}_grow={grow:.3f}mm")
                if shrink > max_axis_shrink:
                    drift_reasons.append(f"axis{axis_idx}_shrink={shrink:.3f}mm")

            diag_grow = float(after_diag - before_diag)
            diag_shrink = float(before_diag - after_diag)
            if diag_grow > max_diag_grow:
                drift_reasons.append(f"diag_grow={diag_grow:.3f}mm")
            if diag_shrink > max_diag_shrink:
                drift_reasons.append(f"diag_shrink={diag_shrink:.3f}mm")

            center_shift = float(
                (
                    (after_center[0] - before_center[0]) ** 2
                    + (after_center[1] - before_center[1]) ** 2
                    + (after_center[2] - before_center[2]) ** 2
                ) ** 0.5
            )
            if center_shift > max_center_shift:
                drift_reasons.append(f"center_shift={center_shift:.3f}mm")

            if not drift_reasons:
                return None

            return {
                "feature": op_label,
                "magnitude": magnitude,
                "before": before_metrics,
                "after": after_metrics,
                "limits": {
                    "max_axis_grow": max_axis_grow,
                    "max_axis_shrink": max_axis_shrink,
                    "max_diag_grow": max_diag_grow,
                    "max_diag_shrink": max_diag_shrink,
                    "max_center_shift": max_center_shift,
                },
                "observed": {
                    "max_axis_grow": max_axis_grow_seen,
                    "max_axis_shrink": max_axis_shrink_seen,
                    "diag_grow": diag_grow,
                    "diag_shrink": diag_shrink,
                    "center_shift": center_shift,
                },
                "reasons": drift_reasons,
            }

        # === PHASE 7: Inkrementeller Rebuild mit Checkpoints ===
        start_index = 0
        current_solid = None
        use_incremental = is_enabled("feature_dependency_tracking") and changed_feature_id is not None

        if use_incremental:
            # Dependency Graph aktualisieren
            self._dependency_graph.rebuild_feature_index(self.features)

            # Finde optimalen Start-Punkt
            start_index = self._dependency_graph.get_rebuild_start_index(changed_feature_id)

            # Lade Checkpoint-Solid falls vorhanden
            if start_index > 0 and (start_index - 1) in self._solid_checkpoints:
                current_solid = self._solid_checkpoints[start_index - 1]
                logger.info(f"Phase 7: Inkrementeller Rebuild ab Feature {start_index} (Checkpoint genutzt)")
            else:
                start_index = 0  # Kein Checkpoint, starte von 0

        last_valid_solid = current_solid
        last_valid_feature_index = start_index - 1 if current_solid is not None else -1

        logger.info(f"Rebuilding Body '{self.name}' (Features {start_index}-{max_index-1}/{len(self.features)})...")

        # Reset Cache (Phase 2: Lazy-Loading)
        self.invalidate_mesh()
        self._mesh_vertices.clear()
        self._mesh_triangles.clear()

        # Setze Status fÃ¼r Features VOR start_index (bereits computed)
        for i in range(start_index):
            if i < len(self.features) and not self.features[i].suppressed:
                self.features[i].status = "OK"  # Aus Checkpoint
                self.features[i].status_message = ""
                self.features[i].status_details = {}

        blocked_by_feature_error = False
        blocked_by_feature_name = ""
        blocked_by_feature_index = -1

        for i, feature in enumerate(self.features):
            solid_before_feature = current_solid
            if progress_callback:
                try:
                    progress_callback(i, len(self.features), feature.name)
                except Exception:
                    pass
            if i >= max_index:
                feature.status = "ROLLED_BACK"
                feature.status_message = ""
                feature.status_details = {}
                continue
            if feature.suppressed:
                feature.status = "SUPPRESSED"
                feature.status_message = ""
                feature.status_details = {}
                continue

            # === PHASE 7: Ãœberspringe Features vor start_index (aus Checkpoint) ===
            if use_incremental and i < start_index:
                continue  # Status bereits gesetzt

            if blocked_by_feature_error:
                blocked_msg = (
                    f"Nicht ausgefÃ¼hrt: vorheriges Feature "
                    f"'{blocked_by_feature_name}' (Index {blocked_by_feature_index}) fehlgeschlagen."
                )
                feature.status = "ERROR"
                feature.status_message = blocked_msg
                blocked_details = self._build_operation_error_details(
                    op_name=f"Blocked_{i}",
                    code="blocked_by_upstream_error",
                    message=blocked_msg,
                    feature=feature,
                )
                rollback_metrics = _solid_metrics(current_solid)
                feature.status_details = _ensure_rollback_details(
                    blocked_details,
                    rollback_metrics,
                    rollback_metrics,
                )
                continue

            new_solid = None
            status = "OK"
            self._last_operation_error = ""
            self._last_operation_error_details = {}

            # ================= PRIMITIVE (Base Feature) =================
            if isinstance(feature, PrimitiveFeature):
                base_solid = feature.create_solid()
                if base_solid is not None:
                    new_solid = base_solid
                    logger.info(f"PrimitiveFeature: {feature.primitive_type} erstellt")
                    if current_solid is None:
                        self._register_base_feature_shapes(feature, new_solid)
                else:
                    status = "ERROR"
                    logger.error(f"PrimitiveFeature: Erstellung fehlgeschlagen")

            # ================= IMPORT (Base Feature) =================
            elif isinstance(feature, ImportFeature):
                # ImportFeature enthÃ¤lt die Basis-Geometrie (z.B. konvertiertes Mesh)
                base_solid = feature.get_solid()
                if base_solid is not None:
                    new_solid = base_solid
                    logger.info(f"ImportFeature: Basis-Geometrie geladen ({base_solid.volume:.2f}mmÂ³)")
                    if current_solid is None:
                        self._register_base_feature_shapes(feature, new_solid)
                else:
                    status = "ERROR"
                    logger.error(f"ImportFeature: Konnte BREP nicht laden")

            # ================= EXTRUDE =================
            elif isinstance(feature, ExtrudeFeature):
                # Push/Pull auf Body-Face: BRepFeat fÃ¼r Join/Cut verwenden.
                has_polys = hasattr(feature, 'precalculated_polys') and feature.precalculated_polys

                if has_polys and current_solid is not None and feature.operation in ("Join", "Cut"):
                    # === PUSH/PULL auf Body-Face: Verwende BRepFeat fÃ¼r TNP-Robustheit ===
                    
                    def op_brepfeat():
                        return self._compute_extrude_part_brepfeat(feature, current_solid)
                    
                    brepfeat_result, status = self._safe_operation(
                        f"Extrude_BRepFeat_{i}",
                        op_brepfeat,
                        feature=feature,
                    )
                    
                    if brepfeat_result and status == "SUCCESS":
                        new_solid = brepfeat_result
                        if is_enabled("tnp_debug_logging"):
                            logger.debug(f"TNP BRepFeat: Push/Pull erfolgreich via BRepFeat_MakePrism")
                        
                        if is_enabled("extrude_debug"):
                            logger.debug(f"TNP DEBUG: Starte _update_edge_selectors_after_operation")
                        self._update_edge_selectors_after_operation(new_solid, current_feature_index=i)
                    else:
                        # TNP v4 strict: Bei vorhandenen PrimÃ¤rreferenzen (ShapeID/Index)
                        # KEIN Fallback auf polygon-basiertes Extrude+Boolean, da das
                        # semantisch eine andere Operation ergeben kann.
                        has_primary_face_ref = (
                            getattr(feature, "face_shape_id", None) is not None
                            or getattr(feature, "face_index", None) is not None
                        )
                        if has_primary_face_ref:
                            status = "ERROR"
                            new_solid = current_solid
                            logger.error(
                                "Push/Pull: BRepFeat fehlgeschlagen bei vorhandenen "
                                "TNP-PrimÃ¤rreferenzen (face_shape_id/face_index). "
                                "Kein Boolean-Fallback."
                            )
                        else:
                            # Legacy-Fallback nur ohne TNP-PrimÃ¤rreferenz.
                            has_polys = False
                
                if not has_polys or current_solid is None:
                    # === Normales Extrude (mit Sketch) oder New Body ===
                    def op_extrude():
                        return self._compute_extrude_part(feature)
                    
                    part_geometry, status = self._safe_operation(
                        f"Extrude_{i}",
                        op_extrude,
                        feature=feature,
                    )

                    if part_geometry:
                        if current_solid is None or feature.operation == "New Body":
                            new_solid = part_geometry
                            if is_enabled("extrude_debug"):
                                logger.debug(f"TNP DEBUG: Extrude New Body - kein Boolean")
                            
                            # === TNP v4.0: Shape-Registrierung fÃ¼r Extrude ===
                            if self._document and hasattr(self._document, '_shape_naming_service'):
                                try:
                                    self._register_extrude_shapes(feature, new_solid)
                                except Exception as tnp_e:
                                    if is_enabled("tnp_debug_logging"):
                                        logger.debug(f"TNP v4.0: Shape-Registrierung fehlgeschlagen: {tnp_e}")
                        else:
                            # Boolean Operation Ã¼ber BooleanEngineV4
                            if is_enabled("extrude_debug"):
                                logger.debug(f"TNP DEBUG: Extrude {feature.operation} startet...")
                            bool_result = BooleanEngineV4.execute_boolean_on_shapes(
                                current_solid, part_geometry, feature.operation
                            )

                            if bool_result.is_success:
                                new_solid = bool_result.value
                                if is_enabled("extrude_debug"):
                                    logger.debug(f"TNP DEBUG: Boolean {feature.operation} erfolgreich")

                                # TNP v4.0: History an ShapeNamingService durchreichen
                                self._register_boolean_history(bool_result, feature, operation_name=feature.operation)

                                # Nach Boolean-Operation: Edge-Selektoren fÃ¼r nachfolgende Features aktualisieren
                                if new_solid is not None:
                                    if is_enabled("extrude_debug"):
                                        logger.debug(f"TNP DEBUG: Starte _update_edge_selectors_after_operation")
                                    self._update_edge_selectors_after_operation(new_solid, current_feature_index=i)
                            else:
                                logger.warning(f"âš ï¸ {feature.operation} fehlgeschlagen: {bool_result.message}")
                                status = "ERROR"
                                # Behalte current_solid (keine Ã„nderung)
                                continue

            # ================= PUSHPULL =================
            elif isinstance(feature, PushPullFeature):
                # Push/Pull nutzt exakt dieselbe Logik wie Extrude (Join/Cut) auf Body-Face.
                # Wir delegieren an _compute_extrude_part_brepfeat.
                
                def op_pushpull():
                    return self._compute_extrude_part_brepfeat(feature, current_solid)

                pushpull_result, status = self._safe_operation(
                    f"PushPull_{i}",
                    op_pushpull,
                    feature=feature,
                )

                if pushpull_result and status == "SUCCESS":
                    new_solid = pushpull_result
                    if is_enabled("tnp_debug_logging"):
                        logger.debug(f"PushPullFeature: Erfolgreich ausgefÃ¼hrt ({feature.operation}, d={feature.distance})")
                    
                    self._update_edge_selectors_after_operation(new_solid, current_feature_index=i)
                else:
                    status = "ERROR"
                    logger.error(f"PushPullFeature fehlgeschlagen: {self._last_operation_error}")
                    new_solid = current_solid

            # ================= FILLET =================
            elif isinstance(feature, FilletFeature):
                if current_solid:
                    # TNP-CRITICAL: Aktualisiere Edge-Selektoren BEVOR Fillet ausgefÃ¼hrt wird
                    # Weil vorherige Features (Extrude, Boolean) das Solid verÃ¤ndert haben
                    self._update_edge_selectors_for_feature(feature, current_solid)

                    # Feature-ID sicherstellen
                    if not hasattr(feature, 'id') or feature.id is None:
                        import uuid
                        feature.id = str(uuid.uuid4())[:8]
                        logger.debug(f"[FILLET] Generated ID for FilletFeature: {feature.id}")

                    def op_fillet(rad=feature.radius):
                        # OCP-First Fillet mit TNP Integration (Phase B)
                        edges_to_fillet = self._resolve_edges_tnp(current_solid, feature)
                        if not edges_to_fillet:
                            raise ValueError("Fillet: Keine Kanten selektiert (TNP resolution failed)")

                        naming_service = None
                        if self._document and hasattr(self._document, '_shape_naming_service'):
                            naming_service = self._document._shape_naming_service

                        if naming_service is None:
                            raise ValueError(
                                "Fillet: TNP ShapeNamingService nicht verfÃ¼gbar. "
                                "Bitte Document mit TNP Service verwenden."
                            )

                        # EINZIGER PFAD - OCPFilletHelper (kein Fallback!)
                        result = OCPFilletHelper.fillet(
                            solid=current_solid,
                            edges=[e.wrapped if hasattr(e, 'wrapped') else e for e in edges_to_fillet],
                            radius=rad,
                            naming_service=naming_service,
                            feature_id=feature.id
                        )
                        return result

                    # Fail-Fast: Kein Fallback mit reduziertem Radius
                    new_solid, status = self._safe_operation(
                        f"Fillet_{i}",
                        op_fillet,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"
                        logger.error(f"Fillet R={feature.radius}mm fehlgeschlagen. Radius evtl. zu gross fuer die gewaehlten Kanten.")
                    # TNP History wird automatisch vom OCPFilletHelper registriert

            # ================= CHAMFER =================
            elif isinstance(feature, ChamferFeature):
                if current_solid:
                    # TNP-CRITICAL: Aktualisiere Edge-Selektoren BEVOR Chamfer ausgefÃ¼hrt wird
                    # Weil vorherige Features (Extrude, Boolean) das Solid verÃ¤ndert haben
                    self._update_edge_selectors_for_feature(feature, current_solid)

                    # Feature-ID sicherstellen
                    if not hasattr(feature, 'id') or feature.id is None:
                        import uuid
                        feature.id = str(uuid.uuid4())[:8]
                        logger.debug(f"[CHAMFER] Generated ID for ChamferFeature: {feature.id}")

                    def op_chamfer(dist=feature.distance):
                        # OCP-First Chamfer mit TNP Integration (Phase B)
                        edges = self._resolve_edges_tnp(current_solid, feature)
                        if not edges:
                            raise ValueError("Chamfer: Keine Kanten selektiert (TNP resolution failed)")

                        naming_service = None
                        if self._document and hasattr(self._document, '_shape_naming_service'):
                            naming_service = self._document._shape_naming_service

                        if naming_service is None:
                            raise ValueError(
                                "Chamfer: TNP ShapeNamingService nicht verfÃ¼gbar. "
                                "Bitte Document mit TNP Service verwenden."
                            )

                        # EINZIGER PFAD - OCPChamferHelper (kein Fallback!)
                        result = OCPChamferHelper.chamfer(
                            solid=current_solid,
                            edges=[e.wrapped if hasattr(e, 'wrapped') else e for e in edges],
                            distance=dist,
                            naming_service=naming_service,
                            feature_id=feature.id
                        )
                        return result

                    # Fail-Fast: Kein Fallback mit reduzierter Distance
                    new_solid, status = self._safe_operation(
                        f"Chamfer_{i}",
                        op_chamfer,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"
                        logger.error(f"Chamfer D={feature.distance}mm fehlgeschlagen. Distance evtl. zu gross fuer die gewaehlten Kanten.")
                    # TNP History wird automatisch vom OCPChamferHelper registriert

            # ================= TRANSFORM =================
            elif isinstance(feature, TransformFeature):
                if current_solid:
                    def op_transform():
                        return self._apply_transform_feature(current_solid, feature)

                    new_solid, status = self._safe_operation(
                        f"Transform_{i}",
                        op_transform,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= REVOLVE =================
            elif isinstance(feature, RevolveFeature):
                def op_revolve():
                    return self._compute_revolve(feature)

                part_geometry, status = self._safe_operation(
                    f"Revolve_{i}",
                    op_revolve,
                    feature=feature,
                )

                if part_geometry:
                    if current_solid is None or feature.operation == "New Body":
                        new_solid = part_geometry
                        if current_solid is None:
                            self._register_base_feature_shapes(feature, new_solid)
                    else:
                        bool_result = BooleanEngineV4.execute_boolean_on_shapes(
                            current_solid, part_geometry, feature.operation
                        )
                        if bool_result.is_success:
                            new_solid = bool_result.value
                            self._register_boolean_history(bool_result, feature, operation_name=feature.operation)
                        else:
                            logger.warning(f"Revolve Boolean fehlgeschlagen: {bool_result.message}")
                            status = "ERROR"
                            continue

            # ================= LOFT (Phase 6) =================
            elif isinstance(feature, LoftFeature):
                def op_loft():
                    return self._compute_loft(feature)

                part_geometry, status = self._safe_operation(
                    f"Loft_{i}",
                    op_loft,
                    feature=feature,
                )

                if part_geometry:
                    if current_solid is None or feature.operation == "New Body":
                        new_solid = part_geometry
                        if current_solid is None:
                            self._register_base_feature_shapes(feature, new_solid)
                    else:
                        bool_result = BooleanEngineV4.execute_boolean_on_shapes(
                            current_solid, part_geometry, feature.operation
                        )
                        if bool_result.is_success:
                            new_solid = bool_result.value
                            self._register_boolean_history(bool_result, feature, operation_name=feature.operation)
                        else:
                            logger.warning(f"Loft Boolean fehlgeschlagen: {bool_result.message}")
                            status = "ERROR"
                            continue

            # ================= SWEEP (Phase 6) =================
            elif isinstance(feature, SweepFeature):
                def op_sweep():
                    return self._compute_sweep(feature, current_solid)

                part_geometry, status = self._safe_operation(
                    f"Sweep_{i}",
                    op_sweep,
                    feature=feature,
                )

                if part_geometry:
                    if current_solid is None or feature.operation == "New Body":
                        new_solid = part_geometry
                        if current_solid is None:
                            self._register_base_feature_shapes(feature, new_solid)
                    else:
                        bool_result = BooleanEngineV4.execute_boolean_on_shapes(
                            current_solid, part_geometry, feature.operation
                        )
                        if bool_result.is_success:
                            new_solid = bool_result.value
                            self._register_boolean_history(bool_result, feature, operation_name=feature.operation)
                        else:
                            logger.warning(f"Sweep Boolean fehlgeschlagen: {bool_result.message}")
                            status = "ERROR"
                            continue

            # ================= SHELL (Phase 6) =================
            elif isinstance(feature, ShellFeature):
                if current_solid:
                    # TNP-CRITICAL: Aktualisiere Face-Selektoren BEVOR Shell ausgefÃ¼hrt wird
                    self._update_face_selectors_for_feature(feature, current_solid)
                    
                    def op_shell():
                        return self._compute_shell(feature, current_solid)

                    new_solid, status = self._safe_operation(
                        f"Shell_{i}",
                        op_shell,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= HOLLOW (3D-Druck) =================
            elif isinstance(feature, HollowFeature):
                if current_solid:
                    # TNP v4.0: Opening-Faces vor Hollow aktualisieren
                    self._update_face_selectors_for_feature(feature, current_solid)

                    def op_hollow():
                        return self._compute_hollow(feature, current_solid)

                    new_solid, status = self._safe_operation(
                        f"Hollow_{i}",
                        op_hollow,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= LATTICE (3D-Druck) =================
            elif isinstance(feature, LatticeFeature):
                if current_solid:
                    def op_lattice():
                        from modeling.lattice_generator import LatticeGenerator
                        return LatticeGenerator.generate(
                            current_solid,
                            cell_type=feature.cell_type,
                            cell_size=feature.cell_size,
                            beam_radius=feature.beam_radius,
                            shell_thickness=feature.shell_thickness,
                        )

                    new_solid, status = self._safe_operation(
                        f"Lattice_{i}",
                        op_lattice,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= N-SIDED PATCH =================
            elif isinstance(feature, NSidedPatchFeature):
                if current_solid:
                    def op_nsided():
                        return self._compute_nsided_patch(feature, current_solid)

                    new_solid, status = self._safe_operation(
                        f"NSidedPatch_{i}",
                        op_nsided,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= HOLE =================
            elif isinstance(feature, HoleFeature):
                if current_solid:
                    # TNP-CRITICAL: Aktualisiere Face-Selektoren BEVOR Hole ausgefÃ¼hrt wird
                    self._update_face_selectors_for_feature(feature, current_solid)
                    
                    def op_hole():
                        return self._compute_hole(feature, current_solid)

                    new_solid, status = self._safe_operation(
                        f"Hole_{i}",
                        op_hole,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"
                        if not self._last_operation_error:
                            self._last_operation_error = "Hole-Operation lieferte kein Ergebnis-Solid"
                            self._last_operation_error_details = self._build_operation_error_details(
                                op_name=f"Hole_{i}",
                                code="no_result_solid",
                                message=self._last_operation_error,
                                feature=feature,
                            )

            # ================= DRAFT =================
            elif isinstance(feature, DraftFeature):
                if current_solid:
                    # TNP-CRITICAL: Aktualisiere Face-Selektoren BEVOR Draft ausgefÃ¼hrt wird
                    self._update_face_selectors_for_feature(feature, current_solid)
                    
                    def op_draft():
                        return self._compute_draft(feature, current_solid)

                    new_solid, status = self._safe_operation(
                        f"Draft_{i}",
                        op_draft,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"
                        if not self._last_operation_error:
                            self._last_operation_error = "Draft-Operation lieferte kein Ergebnis-Solid"
                            self._last_operation_error_details = self._build_operation_error_details(
                                op_name=f"Draft_{i}",
                                code="no_result_solid",
                                message=self._last_operation_error,
                                feature=feature,
                            )

            # ================= SPLIT =================
            elif isinstance(feature, SplitFeature):
                if current_solid:
                    def op_split():
                        # Multi-Body Architecture (AGENTS.md Phase 2):
                        # WÃ¤hrend Rebuild: Wenn dieser Body ein split_side hat, berechne nur diese Seite
                        if self.split_side and i == self.split_index:
                            # Rebuild-Modus: Nur unsere Seite berechnen
                            # TemporÃ¤r keep_side Ã¼berschreiben fÃ¼r diesen Rebuild
                            original_keep_side = feature.keep_side
                            feature.keep_side = self.split_side
                            result = self._compute_split(feature, current_solid)
                            feature.keep_side = original_keep_side  # Restore
                            return result  # Solid (legacy mode)
                        else:
                            # Normaler Split oder keep_side != "both"
                            result = self._compute_split(feature, current_solid)
                            # Falls SplitResult zurÃ¼ckkommt (keep_side == "both"):
                            # Das sollte nur beim ersten Split passieren, nicht wÃ¤hrend Rebuild
                            if isinstance(result, SplitResult):
                                # WÃ¤hrend Rebuild sollte das nicht passieren - Warnung!
                                logger.warning("Split returned SplitResult during rebuild - using body_above as fallback")
                                return result.body_above
                            return result

                    new_solid, status = self._safe_operation(
                        f"Split_{i}",
                        op_split,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= THREAD =================
            elif isinstance(feature, ThreadFeature):
                if current_solid:
                    self._update_face_selectors_for_feature(feature, current_solid)
                if feature.cosmetic and is_enabled("cosmetic_threads"):
                    # Kosmetisch: kein BREP-Update, nur Helix-Linien im Viewport
                    status = "COSMETIC"
                    logger.debug(f"Thread '{feature.name}' â€” cosmetic, kein BREP-Update")
                elif current_solid:
                    def op_thread():
                        return self._compute_thread(feature, current_solid)

                    new_solid, status = self._safe_operation(
                        f"Thread_{i}",
                        op_thread,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= SURFACE TEXTURE =================
            elif isinstance(feature, SurfaceTextureFeature):
                if current_solid:
                    self._update_face_selectors_for_feature(feature, current_solid)
                # Texturen modifizieren NICHT das BREP â€” nur Metadaten-Layer.
                # Displacement wird erst beim STL-Export angewendet.
                status = "OK"
                logger.debug(f"SurfaceTexture '{feature.name}' â€” Metadaten-only, kein BREP-Update")

            if strict_self_heal and status == "WARNING" and self._feature_has_topological_references(feature):
                rollback_from = _solid_metrics(new_solid) if new_solid is not None else _solid_metrics(current_solid)
                rollback_to = _solid_metrics(solid_before_feature)
                status = "ERROR"
                new_solid = solid_before_feature
                self._last_operation_error = (
                    f"Strict Self-Heal: Warning/Fallback bei Topologie-Referenzen blockiert "
                    f"(Feature '{feature.name}')."
                )
                self._last_operation_error_details = self._build_operation_error_details(
                    op_name=f"StrictSelfHeal_{i}",
                    code="self_heal_blocked_topology_warning",
                    message=self._last_operation_error,
                    feature=feature,
                    hint="Feature-Referenzen neu auswÃ¤hlen oder Parameter reduzieren.",
                )
                self._last_operation_error_details["rollback"] = {
                    "from": rollback_from,
                    "to": rollback_to,
                }
                logger.error(self._last_operation_error)
                logger.error(
                    f"Strict Self-Heal Rollback ({feature.name}): "
                    f"{_format_metrics(rollback_from)} -> {_format_metrics(rollback_to)}"
                )

            if strict_self_heal and new_solid is not None and status != "ERROR":
                step_validation = GeometryValidator.validate_solid(new_solid, ValidationLevel.NORMAL)
                if step_validation.is_error:
                    rollback_from = _solid_metrics(new_solid)
                    rollback_to = _solid_metrics(solid_before_feature)
                    status = "ERROR"
                    new_solid = solid_before_feature
                    self._last_operation_error = (
                        f"Strict Self-Heal: Feature '{feature.name}' erzeugte ungÃ¼ltige Geometrie "
                        f"({step_validation.message}) â€“ Rollback auf letzten validen Stand."
                    )
                    self._last_operation_error_details = self._build_operation_error_details(
                        op_name=f"StrictSelfHeal_{i}",
                        code="self_heal_rollback_invalid_result",
                        message=self._last_operation_error,
                        feature=feature,
                        hint=step_validation.message,
                    )
                    self._last_operation_error_details["rollback"] = {
                        "from": rollback_from,
                        "to": rollback_to,
                    }
                    logger.error(self._last_operation_error)
                    logger.error(
                        f"Strict Self-Heal Rollback ({feature.name}): "
                        f"{_format_metrics(rollback_from)} -> {_format_metrics(rollback_to)}"
                    )

            if (
                strict_self_heal
                and new_solid is not None
                and status != "ERROR"
                and solid_before_feature is not None
                and _is_local_modifier_feature(feature)
            ):
                before_metrics = _solid_metrics(solid_before_feature)
                after_metrics = _solid_metrics(new_solid)
                drift_details = _local_modifier_drift_details(feature, before_metrics, after_metrics)
                if drift_details is not None:
                    status = "ERROR"
                    new_solid = solid_before_feature
                    self._last_operation_error = (
                        f"Strict Self-Heal: Feature '{feature.name}' verworfen "
                        f"(unerwartete globale Geometrie-Drift bei lokalem Modifier)."
                    )
                    self._last_operation_error_details = self._build_operation_error_details(
                        op_name=f"StrictSelfHeal_{i}",
                        code="self_heal_rollback_geometry_drift",
                        message=self._last_operation_error,
                        feature=feature,
                        hint="Chamfer/Fillet hat den Body global verÃ¤ndert. Auswahl/Parameter prÃ¼fen.",
                    )
                    self._last_operation_error_details["rollback"] = {
                        "from": after_metrics,
                        "to": before_metrics,
                    }
                    self._last_operation_error_details["geometry_drift"] = drift_details
                    logger.error(self._last_operation_error)
                    logger.error(
                        f"Strict Self-Heal Rollback ({feature.name}, drift): "
                        f"{_format_metrics(after_metrics)} -> {_format_metrics(before_metrics)} | "
                        f"reasons={', '.join(drift_details.get('reasons', []))}"
                    )

            feature.status = status
            if status in ("ERROR", "WARNING"):
                feature.status_message = self._last_operation_error or feature.status_message
                feature.status_details = dict(self._last_operation_error_details or {})
            else:
                feature.status_message = ""
                feature.status_details = {}

            if status == "ERROR":
                rollback_from = _solid_metrics(new_solid if new_solid is not None else current_solid)
                rollback_to = _solid_metrics(solid_before_feature)
                feature.status_details = _ensure_rollback_details(
                    feature.status_details,
                    rollback_from,
                    rollback_to,
                )
                self._last_operation_error_details = _ensure_rollback_details(
                    self._last_operation_error_details,
                    rollback_from,
                    rollback_to,
                )

            # === Geometry Delta (Transparenz fÃ¼r Endanwender) ===
            # Berechnet den Geometrie-Unterschied vor/nach jeder Feature-Anwendung.
            # Transient (_geometry_delta wird NICHT gespeichert, nur zur Laufzeit).
            effective_solid = new_solid if (new_solid is not None and status != "ERROR") else current_solid
            before_m = _solid_metrics(solid_before_feature) if solid_before_feature is not None else None
            after_m = _solid_metrics(effective_solid) if effective_solid is not None else None
            if before_m is not None and after_m is not None and before_m["volume"] is not None and after_m["volume"] is not None:
                pre_vol = before_m["volume"]
                post_vol = after_m["volume"]
                vol_pct = ((post_vol - pre_vol) / pre_vol * 100.0) if pre_vol > 1e-12 else 0.0
                feature._geometry_delta = {
                    "volume_before": round(pre_vol, 2),
                    "volume_after": round(post_vol, 2),
                    "volume_pct": round(vol_pct, 1),
                    "faces_before": before_m["faces"],
                    "faces_after": after_m["faces"],
                    "faces_delta": after_m["faces"] - before_m["faces"],
                    "edges_before": before_m["edges"],
                    "edges_after": after_m["edges"],
                    "edges_delta": after_m["edges"] - before_m["edges"],
                }
            elif after_m is not None and after_m["volume"] is not None:
                # Erstes Feature (kein solid_before_feature)
                feature._geometry_delta = {
                    "volume_before": 0.0,
                    "volume_after": round(after_m["volume"], 2),
                    "volume_pct": 0.0,
                    "faces_before": 0,
                    "faces_after": after_m["faces"],
                    "faces_delta": after_m["faces"],
                    "edges_before": 0,
                    "edges_after": after_m["edges"],
                    "edges_delta": after_m["edges"],
                }
            else:
                feature._geometry_delta = None

            if status == "ERROR":
                blocked_by_feature_error = True
                blocked_by_feature_name = feature.name
                blocked_by_feature_index = i

            if new_solid is not None and status != "ERROR":
                current_solid = new_solid
                last_valid_solid = current_solid
                last_valid_feature_index = i

                # === PHASE 7: Checkpoint erstellen (alle N Features) ===
                if use_incremental and self._dependency_graph.should_create_checkpoint(i):
                    self._solid_checkpoints[i] = current_solid
                    self._dependency_graph.create_checkpoint(i, feature.id, current_solid)
                    logger.debug(f"Phase 7: Checkpoint nach Feature {i} ('{feature.name}')")

        # === PHASE 7: Dependency Graph aufrÃ¤umen ===
        if use_incremental:
            self._dependency_graph.clear_dirty()

        pre_finalize_snapshot = {
            "solid": self._build123d_solid,
            "shape": self.shape,
            "mesh_cache": self._mesh_cache,
            "edges_cache": self._edges_cache,
            "mesh_cache_valid": self._mesh_cache_valid,
            "mesh_vertices": list(self._mesh_vertices or []),
            "mesh_triangles": list(self._mesh_triangles or []),
            "last_error": self._last_operation_error,
            "last_error_details": dict(self._last_operation_error_details or {}),
        }

        if current_solid:
            # Phase 7: Validierung nach Rebuild
            validation = GeometryValidator.validate_solid(current_solid, ValidationLevel.NORMAL)

            if validation.is_error:
                logger.warning(f"âš ï¸ Geometrie-Validierung fehlgeschlagen: {validation.message}")
                before_heal_metrics = _solid_metrics(current_solid)
                healed, heal_result = GeometryHealer.heal_solid(current_solid)
                heal_applied = False

                if heal_result.success and healed is not None:
                    healed_validation = GeometryValidator.validate_solid(healed, ValidationLevel.NORMAL)
                    healed_metrics = _solid_metrics(healed)
                    topology_changed = (
                        before_heal_metrics["faces"] != healed_metrics["faces"]
                        or before_heal_metrics["edges"] != healed_metrics["edges"]
                    )
                    active_topology_refs = self._has_active_topological_references(max_index=max_index)

                    if strict_self_heal and active_topology_refs and topology_changed:
                        logger.error(
                            "Strict Self-Heal: Healing-Ergebnis verworfen "
                            "(Topologie geÃ¤ndert bei aktiven TNP-Referenzen)."
                        )
                    elif healed_validation.is_error:
                        logger.warning(
                            f"âš ï¸ Auto-Healing Ergebnis weiterhin ungÃ¼ltig: {healed_validation.message}"
                        )
                    else:
                        current_solid = healed
                        validation = healed_validation
                        heal_applied = True
                        if heal_result.changes_made:
                            logger.info(f"ðŸ”§ Auto-Healing: {', '.join(heal_result.changes_made)}")
                        logger.info(
                            f"Self-Heal Delta: {_format_metrics(before_heal_metrics)} -> "
                            f"{_format_metrics(healed_metrics)}"
                        )
                elif not heal_result.success:
                    logger.warning(f"âš ï¸ Auto-Healing fehlgeschlagen: {heal_result.message}")

                if strict_self_heal and not heal_applied and last_valid_solid is not None and last_valid_feature_index >= 0:
                    rollback_from = _solid_metrics(current_solid)
                    rollback_to = _solid_metrics(last_valid_solid)
                    logger.error(
                        f"Strict Self-Heal: Rollback auf letzten validen Checkpoint "
                        f"(Feature Index {last_valid_feature_index})."
                    )
                    logger.error(
                        f"Strict Self-Heal Rollback (final): "
                        f"{_format_metrics(rollback_from)} -> {_format_metrics(rollback_to)}"
                    )
                    current_solid = last_valid_solid
                    validation = GeometryValidator.validate_solid(current_solid, ValidationLevel.NORMAL)

            # Phase 9:
            # Globales UnifySameDomain nur ohne aktive TNP-Referenzen.
            # Sonst kann ein "post-history" Topologie-Merge ShapeIDs/Indices
            # nachtrÃ¤glich ungÃ¼ltig machen.
            if self._has_active_topological_references(max_index=max_index):
                if is_enabled("tnp_debug_logging"):
                    logger.debug("UnifySameDomain (Rebuild) Ã¼bersprungen: aktive TNP-Referenzen vorhanden")
            else:
                try:
                    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
                    from build123d import Solid

                    ocp_shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid
                    n_faces_before = len(current_solid.faces()) if hasattr(current_solid, 'faces') else 0

                    upgrader = ShapeUpgrade_UnifySameDomain(ocp_shape, True, True, True)
                    # ErhÃ¶hte Toleranzen fÃ¼r besseres Zylinder-Merging
                    upgrader.SetLinearTolerance(0.1)   # 0.1mm - groÃŸzÃ¼giger
                    upgrader.SetAngularTolerance(0.1)  # ~5.7Â° - fÃ¼r zylindrische FlÃ¤chen
                    upgrader.Build()
                    unified_shape = upgrader.Shape()

                    if unified_shape and not unified_shape.IsNull():
                        unified_solid = Solid.make_solid(unified_shape) if hasattr(Solid, 'make_solid') else Solid(unified_shape)
                        n_faces_after = len(unified_solid.faces()) if hasattr(unified_solid, 'faces') else 0

                        if n_faces_after < n_faces_before:
                            logger.debug(f"UnifySameDomain (Rebuild): {n_faces_before} â†’ {n_faces_after} Faces")
                            current_solid = unified_solid
                except Exception as e:
                    logger.debug(f"UnifySameDomain Ã¼bersprungen: {e}")

            try:
                self._build123d_solid = current_solid
                if hasattr(current_solid, 'wrapped'):
                    self.shape = current_solid.wrapped

                # UPDATE MESH via Helper
                self._update_mesh_from_solid(current_solid)

                # B-Rep Faces zÃ¤hlen (echte CAD-Faces, nicht Tessellations-Dreiecke)
                from modeling.cad_tessellator import CADTessellator
                n_faces = CADTessellator.count_brep_faces(current_solid)
                if n_faces == 0:
                    # Fallback
                    n_faces = len(current_solid.faces()) if hasattr(current_solid, 'faces') else 0

                # Phase 7: Validierungs-Status loggen
                if validation.is_valid:
                    logger.debug(f"âœ“ {self.name}: BREP Valid ({n_faces} Faces)")
                else:
                    logger.warning(f"âš ï¸ {self.name}: BREP mit Warnungen ({n_faces} Faces) - {validation.message}")

                # PI-008: Geometry Drift Detection
                if is_enabled("geometry_drift_detection"):
                    try:
                        from modeling.geometry_drift_detector import GeometryDriftDetector, DriftThresholds
                        
                        detector = GeometryDriftDetector()
                        
                        # Check if we have a cached baseline for this body
                        baseline_key = f"body_{self.id}_baseline"
                        baseline = detector.get_cached_baseline(baseline_key)
                        
                        if baseline is not None:
                            # Detect drift against the baseline
                            ocp_shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid
                            metrics = detector.detect_drift(ocp_shape, baseline)
                            
                            if not detector.is_drift_acceptable(metrics):
                                warnings = detector.get_drift_warnings(metrics)
                                for warning in warnings:
                                    logger.warning(f"Geometry Drift: {warning}")
                                # Store drift info for UI/debugging
                                self._last_drift_metrics = metrics
                            else:
                                logger.debug(f"Geometry Drift Check: OK (vertex={metrics.vertex_drift:.2e}, volume={metrics.volume_drift:.4%})")
                                self._last_drift_metrics = None
                        else:
                            # Capture baseline on first rebuild
                            ocp_shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid
                            detector.capture_baseline(ocp_shape, baseline_key)
                            logger.debug(f"Geometry Drift: Baseline captured for '{self.name}'")
                            self._last_drift_metrics = None
                    except Exception as drift_error:
                        logger.debug(f"Geometry Drift Detection skipped: {drift_error}")

                # Phase 8.2: Automatische Referenz-Migration nach Rebuild
                self._migrate_tnp_references(current_solid)
            except Exception as finalize_error:
                rollback_from = _solid_metrics(current_solid)
                rollback_to = _solid_metrics(pre_finalize_snapshot.get("solid"))

                self._build123d_solid = pre_finalize_snapshot.get("solid")
                self.shape = pre_finalize_snapshot.get("shape")
                self._mesh_cache = pre_finalize_snapshot.get("mesh_cache")
                self._edges_cache = pre_finalize_snapshot.get("edges_cache")
                self._mesh_cache_valid = bool(pre_finalize_snapshot.get("mesh_cache_valid"))
                self._mesh_vertices = list(pre_finalize_snapshot.get("mesh_vertices") or [])
                self._mesh_triangles = list(pre_finalize_snapshot.get("mesh_triangles") or [])

                self._last_operation_error = (
                    f"Rebuild-Finalisierung fehlgeschlagen: {finalize_error}"
                )
                self._last_operation_error_details = self._build_operation_error_details(
                    op_name="RebuildFinalize",
                    code="rebuild_finalize_failed",
                    message=self._last_operation_error,
                )
                self._last_operation_error_details["rollback"] = {
                    "from": rollback_from,
                    "to": rollback_to,
                }

                logger.error(self._last_operation_error)
                logger.error(
                    f"Rebuild-Failsafe Rollback: "
                    f"{_format_metrics(rollback_from)} -> {_format_metrics(rollback_to)}"
                )
                raise
        else:
            logger.warning(f"Body '{self.name}' is empty after rebuild.")
            # Fix: Solid und Mesh auch bei leerem Rebuild aktualisieren
            self._build123d_solid = None
            self.shape = None
            self.invalidate_mesh()
            self._mesh_cache = None
            self._edges_cache = None
            self._mesh_cache_valid = True  # Valid but empty
            self._mesh_vertices = []
            self._mesh_triangles = []

    def _migrate_tnp_references(self, new_solid):
        """
        KompatibilitÃ¤ts-Hook nach Rebuild.

        Das alte TNP-v3 Registry-System wurde entfernt; TNP v4 wird Ã¼ber den
        ShapeNamingService im Document gepflegt.
        """
        return

    def _feature_has_topological_references(self, feature) -> bool:
        """PrÃ¼ft, ob ein Feature aktive Topologie-Referenzen trÃ¤gt."""
        if feature is None:
            return False

        list_ref_attrs = (
            "edge_indices",
            "edge_shape_ids",
            "face_indices",
            "face_shape_ids",
            "opening_face_indices",
            "opening_face_shape_ids",
        )
        single_ref_attrs = (
            "face_index",
            "face_shape_id",
            "profile_face_index",
            "profile_shape_id",
            "path_shape_id",
        )

        for attr in list_ref_attrs:
            val = getattr(feature, attr, None)
            if val is not None and len(val) > 0:
                return True

        for attr in single_ref_attrs:
            val = getattr(feature, attr, None)
            if val is not None:
                return True

        return False

    def _has_active_topological_references(self, max_index: Optional[int] = None) -> bool:
        """True wenn mindestens ein aktives Feature bis max_index Topo-Refs besitzt."""
        end = max_index if max_index is not None else len(self.features)
        for i, feat in enumerate(self.features[:end]):
            if getattr(feat, "suppressed", False):
                continue
            if self._feature_has_topological_references(feat):
                return True
        return False


__all__ = ['BodyRebuildMixin']
