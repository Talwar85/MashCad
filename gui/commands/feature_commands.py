"""
MashCad - Feature Commands for Undo/Redo
Implements QUndoCommand for undoable feature operations (Extrude, Fillet, etc.)
"""

import copy

from PySide6.QtGui import QUndoCommand
from loguru import logger


def _solid_signature_safe(body) -> dict:
    """Geometry-Fingerprint (volume, faces, edges) oder None."""
    try:
        solid = getattr(body, "_build123d_solid", None)
        if solid is None:
            return None
        return {
            "volume": float(solid.volume),
            "faces": len(list(solid.faces())),
            "edges": len(list(solid.edges())),
        }
    except Exception:
        return None


def _collect_error_feature_ids(body) -> set:
    """Collect all feature IDs currently marked as ERROR."""
    return {
        feat.id
        for feat in getattr(body, "features", [])
        if getattr(feat, "status", "") == "ERROR"
    }


def _is_solid_invalid(body) -> bool:
    """Validate current body solid. Empty body is considered valid."""
    solid = getattr(body, "_build123d_solid", None)
    if solid is None:
        return False
    try:
        from modeling.geometry_validator import GeometryValidator, ValidationLevel

        return GeometryValidator.validate_solid(solid, ValidationLevel.NORMAL).is_error
    except Exception:
        # If validation itself crashes, treat as invalid to stay fail-safe.
        return True


def _capture_body_state(body) -> dict:
    """Capture state for transactional rollback."""
    feature_status = {}
    for feat in getattr(body, "features", []):
        feature_status[feat.id] = (
            getattr(feat, "status", "OK"),
            getattr(feat, "status_message", ""),
            copy.deepcopy(getattr(feat, "status_details", {})),
        )

    return {
        "features": list(getattr(body, "features", [])),
        "feature_status": feature_status,
        "solid": getattr(body, "_build123d_solid", None),
        "shape": getattr(body, "shape", None),
        "rollback_index": getattr(body, "rollback_index", None),
        "last_error": getattr(body, "_last_operation_error", ""),
        "last_error_details": copy.deepcopy(getattr(body, "_last_operation_error_details", {})),
        "solid_checkpoints": dict(getattr(body, "_solid_checkpoints", {})),
        "solid_generation": getattr(body, "_solid_generation", 0),
        "last_boolean_feature_index": getattr(body, "_last_boolean_feature_index", -1),
        "error_ids": _collect_error_feature_ids(body),
        "solid_invalid": _is_solid_invalid(body),
        "had_solid": getattr(body, "_build123d_solid", None) is not None,
    }


def _restore_body_state(body, state: dict) -> None:
    """Restore a previously captured body state."""
    body.features = list(state.get("features", []))

    feature_status = state.get("feature_status", {})
    for feat in body.features:
        status_pack = feature_status.get(feat.id)
        if status_pack is None:
            continue
        feat.status = status_pack[0]
        feat.status_message = status_pack[1]
        feat.status_details = copy.deepcopy(status_pack[2])

    body.rollback_index = state.get("rollback_index")
    body._build123d_solid = state.get("solid")
    body.shape = state.get("shape")
    body._last_operation_error = state.get("last_error", "")
    body._last_operation_error_details = copy.deepcopy(state.get("last_error_details", {}))
    body._solid_checkpoints = dict(state.get("solid_checkpoints", {}))
    body._solid_generation = state.get("solid_generation", 0)
    body._last_boolean_feature_index = state.get("last_boolean_feature_index", -1)

    try:
        body.invalidate_mesh()
    except Exception:
        pass

    if body._build123d_solid is not None:
        try:
            body._update_mesh_from_solid(body._build123d_solid)
        except Exception:
            pass
    else:
        body._mesh_cache = None
        body._edges_cache = None
        body._mesh_cache_valid = True
        body._mesh_vertices = []
        body._mesh_triangles = []


def _has_transaction_regression(body, state: dict) -> tuple:
    """
    Check if operation degraded body health compared to the snapshot.

    Returns:
        (regression: bool, reason: str)
    """
    before_errors = set(state.get("error_ids", set()))
    after_errors = _collect_error_feature_ids(body)
    new_errors = sorted(after_errors - before_errors)
    if new_errors:
        return True, f"new feature errors: {', '.join(new_errors)}"

    if state.get("had_solid", False) and getattr(body, "_build123d_solid", None) is None:
        return True, "body solid disappeared"

    after_invalid = _is_solid_invalid(body)
    if after_invalid and not state.get("solid_invalid", False):
        return True, "body solid became invalid"

    return False, ""


def _update_body_ui(main_window, body) -> None:
    """Centralized UI refresh for one body."""
    try:
        main_window._update_body_from_build123d(body, body._build123d_solid)
        main_window.browser.refresh()
    except Exception as e:
        logger.error(f"UI update failed: {e}")


def _remove_body_from_viewport(main_window, body_id: str) -> None:
    try:
        viewport = getattr(main_window, "viewport_3d", None)
        if viewport is not None:
            viewport.remove_body(body_id)
    except Exception:
        pass


def _capture_document_state(document) -> dict:
    """Capture bodies + active body for atomic split command rollback."""
    return {
        "bodies": list(document.bodies),
        "active_body": document.active_body,
    }


def _restore_document_state(document, state: dict) -> None:
    """Restore captured document body state."""
    restored_bodies = list(state.get("bodies", []))
    document.bodies = restored_bodies
    for body in restored_bodies:
        try:
            body._document = document
        except Exception:
            pass

    active = state.get("active_body")
    if active in restored_bodies:
        document.active_body = active
    elif restored_bodies:
        document.active_body = restored_bodies[0]
    else:
        document.active_body = None


def _update_document_ui(main_window, document) -> None:
    """Refresh browser + body visuals for all bodies in current document."""
    try:
        for body in document.bodies:
            main_window._update_body_from_build123d(body, body._build123d_solid)
        main_window.browser.refresh()
    except Exception as e:
        logger.error(f"Document UI update failed: {e}")


class AddFeatureCommand(QUndoCommand):
    """
    Undoable command for adding any feature to a body.
    Works with: ExtrudeFeature, FilletFeature, ChamferFeature, etc.
    """

    def __init__(self, body, feature, main_window, description=None, skip_rebuild=False):
        desc = description or f"Add {feature.name}"
        super().__init__(desc)
        self.body = body
        self.feature = feature
        self.main_window = main_window
        self._skip_rebuild = skip_rebuild

    def redo(self):
        from modeling.cad_tessellator import CADTessellator

        tx_state = _capture_body_state(self.body)

        # Geometry-Snapshot VOR Operation (für Operation Summary)
        pre_sig = _solid_signature_safe(self.body)

        try:
            # TNP v4.0: Vorherige ShapeIDs für dieses Feature invalidieren
            # Falls ein Redo nach Undo erfolgt, müssen alte ShapeIDs entfernt werden
            try:
                if hasattr(self.body, '_document') and self.body._document:
                    if hasattr(self.body._document, '_shape_naming_service'):
                        service = self.body._document._shape_naming_service
                        if service and hasattr(self.feature, 'id'):
                            service.invalidate_feature(self.feature.id)
                            logger.debug(f"[TNP] Feature {self.feature.id} invalidiert vor Redo")
            except Exception as e:
                logger.debug(f"[TNP] Invalidierung fehlgeschlagen: {e}")

            if self.feature not in self.body.features:
                rebuild = not self._skip_rebuild
                self.body.add_feature(self.feature, rebuild=rebuild)
                logger.debug(f"Redo: Added {self.feature.name} to {self.body.name} (rebuild={rebuild})")

            regressed, reason = _has_transaction_regression(self.body, tx_state)
            if regressed:
                logger.error(f"Redo rollback ({self.feature.name}): {reason}")
                _restore_body_state(self.body, tx_state)

            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, self.body)

            # Operation Summary anzeigen (wenn MainWindow das Widget hat)
            post_sig = _solid_signature_safe(self.body)
            if pre_sig and post_sig and hasattr(self.main_window, 'operation_summary'):
                try:
                    self.main_window.operation_summary.show_summary(
                        self.feature.name, pre_sig, post_sig, self.feature, self.main_window
                    )
                except Exception:
                    pass  # Summary ist nice-to-have, nie blockierend
        except Exception as e:
            logger.error(f"Redo failed ({self.feature.name}): {e}")
            _restore_body_state(self.body, tx_state)
            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, self.body)

    def undo(self):
        from modeling.cad_tessellator import CADTessellator

        tx_state = _capture_body_state(self.body)
        try:
            if self.feature in self.body.features:
                # TNP v4.0: Feature-ShapeIDs sauber aus dem Service entfernen
                # statt einfach zu leeren
                try:
                    if hasattr(self.body, '_document') and self.body._document:
                        if hasattr(self.body._document, '_shape_naming_service'):
                            service = self.body._document._shape_naming_service
                            if service and hasattr(self.feature, 'id'):
                                service.invalidate_feature(self.feature.id)
                                logger.debug(f"[TNP] Feature {self.feature.id} bei Undo entfernt")
                except Exception as e:
                    logger.debug(f"[TNP] Feature-Entfernung fehlgeschlagen: {e}")

                # Legacy: ShapeIDs leeren für Features die TNP nicht nutzen
                try:
                    from modeling import ChamferFeature, FilletFeature

                    if isinstance(self.feature, (FilletFeature, ChamferFeature)):
                        if getattr(self.feature, "edge_shape_ids", None):
                            self.feature.edge_shape_ids = []
                except Exception:
                    pass

                self.body.features.remove(self.feature)
                logger.debug(f"Undo: Removed {self.feature.name} from {self.body.name}")
                CADTessellator.notify_body_changed()
                self.body._rebuild()

            regressed, reason = _has_transaction_regression(self.body, tx_state)
            if regressed:
                logger.error(f"Undo rollback ({self.feature.name}): {reason}")
                _restore_body_state(self.body, tx_state)

            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, self.body)
        except Exception as e:
            logger.error(f"Undo failed ({self.feature.name}): {e}")
            _restore_body_state(self.body, tx_state)
            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, self.body)


class DeleteFeatureCommand(QUndoCommand):
    """Undoable command for deleting a feature from a body."""

    def __init__(self, body, feature, feature_index, main_window):
        super().__init__(f"Delete {feature.name}")
        self.body = body
        self.feature = feature
        self.feature_index = feature_index
        self.main_window = main_window

    def redo(self):
        from modeling.cad_tessellator import CADTessellator

        tx_state = _capture_body_state(self.body)
        try:
            if self.feature in self.body.features:
                self.body.features.remove(self.feature)
                logger.debug(f"Redo: Deleted {self.feature.name}")
                CADTessellator.notify_body_changed()
                self.body._rebuild()

            regressed, reason = _has_transaction_regression(self.body, tx_state)
            if regressed:
                logger.error(f"Delete redo rollback ({self.feature.name}): {reason}")
                _restore_body_state(self.body, tx_state)

            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, self.body)
        except Exception as e:
            logger.error(f"Delete redo failed ({self.feature.name}): {e}")
            _restore_body_state(self.body, tx_state)
            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, self.body)

    def undo(self):
        from modeling.cad_tessellator import CADTessellator

        tx_state = _capture_body_state(self.body)
        try:
            if self.feature not in self.body.features:
                insert_at = max(0, min(self.feature_index, len(self.body.features)))
                self.body.features.insert(insert_at, self.feature)
                logger.debug(f"Undo: Restored {self.feature.name}")
                CADTessellator.notify_body_changed()
                self.body._rebuild()

            regressed, reason = _has_transaction_regression(self.body, tx_state)
            if regressed:
                logger.error(f"Delete undo rollback ({self.feature.name}): {reason}")
                _restore_body_state(self.body, tx_state)

            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, self.body)
        except Exception as e:
            logger.error(f"Delete undo failed ({self.feature.name}): {e}")
            _restore_body_state(self.body, tx_state)
            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, self.body)


class EditFeatureCommand(QUndoCommand):
    """Undoable command for editing feature parameters."""

    def __init__(self, body, feature, old_params, new_params, main_window):
        super().__init__(f"Edit {feature.name}")
        self.body = body
        self.feature = feature
        self.old_params = old_params
        self.new_params = new_params
        self.main_window = main_window

    def _apply_params(self, params):
        for key, value in params.items():
            if hasattr(self.feature, key):
                setattr(self.feature, key, value)

    def redo(self):
        from modeling.cad_tessellator import CADTessellator

        tx_state = _capture_body_state(self.body)
        try:
            self._apply_params(self.new_params)
            logger.debug(f"Redo: Applied new params to {self.feature.name}")
            CADTessellator.notify_body_changed()
            self.body._rebuild()

            regressed, reason = _has_transaction_regression(self.body, tx_state)
            if regressed:
                logger.error(f"Edit redo rollback ({self.feature.name}): {reason}")
                self._apply_params(self.old_params)
                _restore_body_state(self.body, tx_state)

            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, self.body)
        except Exception as e:
            logger.error(f"Edit redo failed ({self.feature.name}): {e}")
            self._apply_params(self.old_params)
            _restore_body_state(self.body, tx_state)
            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, self.body)

    def undo(self):
        from modeling.cad_tessellator import CADTessellator

        tx_state = _capture_body_state(self.body)
        try:
            self._apply_params(self.old_params)
            logger.debug(f"Undo: Restored old params for {self.feature.name}")
            CADTessellator.notify_body_changed()
            self.body._rebuild()

            regressed, reason = _has_transaction_regression(self.body, tx_state)
            if regressed:
                logger.error(f"Edit undo rollback ({self.feature.name}): {reason}")
                self._apply_params(self.new_params)
                _restore_body_state(self.body, tx_state)

            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, self.body)
        except Exception as e:
            logger.error(f"Edit undo failed ({self.feature.name}): {e}")
            self._apply_params(self.new_params)
            _restore_body_state(self.body, tx_state)
            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, self.body)


class AddBodyCommand(QUndoCommand):
    """Undoable command for adding a new body to the document."""

    def __init__(self, document, body, main_window, description=None):
        desc = description or f"Add Body {body.name}"
        super().__init__(desc)
        self.document = document
        self.body = body
        self.main_window = main_window

    def redo(self):
        from modeling.cad_tessellator import CADTessellator

        doc_state = _capture_document_state(self.document)
        try:
            if self.body not in self.document.bodies:
                self.document.add_body(self.body, set_active=False)
                logger.debug(f"Redo: Added body {self.body.name}")

            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, self.body)
        except Exception as e:
            logger.error(f"AddBody redo failed ({self.body.name}): {e}")
            _restore_document_state(self.document, doc_state)
            CADTessellator.notify_body_changed()
            _update_document_ui(self.main_window, self.document)

    def undo(self):
        from modeling.cad_tessellator import CADTessellator

        doc_state = _capture_document_state(self.document)
        try:
            if self.body in self.document.bodies:
                _remove_body_from_viewport(self.main_window, self.body.id)
                self.document.bodies.remove(self.body)
                logger.debug(f"Undo: Removed body {self.body.name}")

            CADTessellator.notify_body_changed()
            self.main_window.browser.refresh()
        except Exception as e:
            logger.error(f"AddBody undo failed ({self.body.name}): {e}")
            _restore_document_state(self.document, doc_state)
            CADTessellator.notify_body_changed()
            _update_document_ui(self.main_window, self.document)


class SplitBodyCommand(QUndoCommand):
    """
    Undo/Redo command for body split operations.
    Tracks original body and both split result bodies.
    """

    def __init__(self, document, original_body, plane_origin, plane_normal, main_window):
        super().__init__("Split Body")
        self.document = document
        self.main_window = main_window

        self.plane_origin = plane_origin
        self.plane_normal = plane_normal

        self.original_body_snapshot = original_body.to_dict()
        self.original_body_id = original_body.id
        self.original_body_name = original_body.name

        self.body_above_id = None
        self.body_below_id = None

    def redo(self):
        from modeling.cad_tessellator import CADTessellator
        from modeling import Body

        doc_state = _capture_document_state(self.document)
        try:
            original = self.document.find_body_by_id(self.original_body_id)
            if original is None:
                original = Body.from_dict(self.original_body_snapshot)
                original._document = self.document
                original._rebuild()
                logger.debug(
                    f"SplitBody redo: restored original snapshot '{original.name}' before splitting"
                )

            body_above, body_below = self.document.split_body(
                original,
                self.plane_origin,
                self.plane_normal,
            )
            if body_above is None or body_below is None:
                raise ValueError("split_body returned empty result")
            if body_above._build123d_solid is None or body_below._build123d_solid is None:
                raise ValueError("split result body has no valid solid")

            self.body_above_id = body_above.id
            self.body_below_id = body_below.id
            logger.debug(
                f"SplitBody redo: '{self.original_body_name}' -> '{body_above.name}' + '{body_below.name}'"
            )

            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, body_above)
            _update_body_ui(self.main_window, body_below)
        except Exception as e:
            logger.error(f"SplitBody redo failed: {e}")
            _restore_document_state(self.document, doc_state)
            CADTessellator.notify_body_changed()
            _update_document_ui(self.main_window, self.document)

    def undo(self):
        from modeling.cad_tessellator import CADTessellator
        from modeling import Body, SplitFeature

        doc_state = _capture_document_state(self.document)
        try:
            body_above = self.document.find_body_by_id(self.body_above_id) if self.body_above_id else None
            body_below = self.document.find_body_by_id(self.body_below_id) if self.body_below_id else None

            if body_above and body_above in self.document.bodies:
                _remove_body_from_viewport(self.main_window, body_above.id)
                self.document.bodies.remove(body_above)
                logger.debug(f"SplitBody undo: removed '{body_above.name}'")

            if body_below and body_below in self.document.bodies:
                _remove_body_from_viewport(self.main_window, body_below.id)
                self.document.bodies.remove(body_below)
                logger.debug(f"SplitBody undo: removed '{body_below.name}'")

            original_body = Body.from_dict(self.original_body_snapshot)
            original_body._document = self.document

            if original_body.features and isinstance(original_body.features[-1], SplitFeature):
                original_body.features.pop()
                logger.debug("SplitBody undo: removed split feature from restored original")

            original_body._rebuild()
            if original_body.features and original_body._build123d_solid is None:
                raise ValueError("restored original body has no valid solid after rebuild")

            self.document.add_body(original_body, set_active=False)
            self.document.active_body = original_body
            logger.info(f"SplitBody undo: restored original '{original_body.name}'")

            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, original_body)
        except Exception as e:
            logger.error(f"SplitBody undo failed: {e}")
            _restore_document_state(self.document, doc_state)
            CADTessellator.notify_body_changed()
            _update_document_ui(self.main_window, self.document)
