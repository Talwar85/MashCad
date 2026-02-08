"""
MashCad - Transform Command for Undo/Redo
Implements QUndoCommand for undoable transform operations.
"""

from copy import deepcopy

from PySide6.QtGui import QUndoCommand
from loguru import logger

from .feature_commands import (
    _capture_body_state,
    _has_transaction_regression,
    _restore_body_state,
    _update_body_ui,
)


class TransformCommand(QUndoCommand):
    """Undoable transform operation that adds/removes TransformFeature atomically."""

    def __init__(self, body, feature, main_window):
        super().__init__(f"Transform: {feature.mode.capitalize()}")
        self.body = body
        self.feature = feature
        self.main_window = main_window

    def _update_gizmo_position(self):
        viewport = getattr(self.main_window, "viewport_3d", None)
        if viewport is None:
            return
        try:
            if hasattr(viewport, "is_transform_active") and viewport.is_transform_active():
                if hasattr(viewport, "show_transform_gizmo"):
                    viewport.show_transform_gizmo(self.body.id, force_refresh=True)
        except Exception:
            # Gizmo update must not break command consistency.
            pass

    def _apply_new_solid(self, new_solid):
        self.body._build123d_solid = new_solid
        if hasattr(new_solid, "wrapped"):
            self.body.shape = new_solid.wrapped
        try:
            self.body.invalidate_mesh()
        except Exception:
            pass
        self.body._update_mesh_from_solid(new_solid)

    def _set_feature_ok(self):
        self.feature.status = "OK"
        self.feature.status_message = ""
        self.feature.status_details = {}

    def _set_feature_error(self, message, details=None):
        self.feature.status = "ERROR"
        self.feature.status_message = message
        self.feature.status_details = details or {"code": "operation_failed"}

    def redo(self):
        """
        Apply transform by adding feature and transforming current solid.

        Transform is applied incrementally (without full rebuild) to avoid
        re-evaluating unrelated feature chain steps for simple move/rotate/scale.
        """
        from modeling.cad_tessellator import CADTessellator

        tx_state = _capture_body_state(self.body)
        changed = False
        try:
            if self.feature not in self.body.features:
                self.body.features.append(self.feature)
                changed = True

            if changed:
                current = getattr(self.body, "_build123d_solid", None)
                if current is None:
                    raise ValueError("Transform redo failed: body has no solid")

                new_solid = self.body._apply_transform_feature(current, self.feature)
                if new_solid is None:
                    raise ValueError("Transform redo failed: _apply_transform_feature returned None")

                self._apply_new_solid(new_solid)
                self._set_feature_ok()

                regressed, reason = _has_transaction_regression(self.body, tx_state)
                if regressed:
                    raise ValueError(f"Transform redo regression: {reason}")

            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, self.body)
            self._update_gizmo_position()
            logger.debug(f"Redo: Transform {self.feature.mode} on {self.body.name}")
        except Exception as e:
            logger.error(f"Transform redo failed ({self.feature.mode}): {e}")
            self._set_feature_error(str(e))
            _restore_body_state(self.body, tx_state)
            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, self.body)
            self._update_gizmo_position()

    def undo(self):
        """Revert transform by removing feature and applying inverse transform."""
        from modeling.cad_tessellator import CADTessellator

        tx_state = _capture_body_state(self.body)
        changed = False
        try:
            if self.feature in self.body.features:
                self.body.features.remove(self.feature)
                changed = True

            if changed:
                current = getattr(self.body, "_build123d_solid", None)
                if current is None:
                    raise ValueError("Transform undo failed: body has no solid")

                inverse_feature = self._create_inverse_transform(self.feature)
                if inverse_feature is not None:
                    new_solid = self.body._apply_transform_feature(current, inverse_feature)
                    if new_solid is None:
                        raise ValueError("Transform undo failed: inverse transform returned None")
                    self._apply_new_solid(new_solid)
                else:
                    # Fallback only for non-invertible transforms.
                    self.body._rebuild()

                regressed, reason = _has_transaction_regression(self.body, tx_state)
                if regressed:
                    raise ValueError(f"Transform undo regression: {reason}")

            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, self.body)
            self._update_gizmo_position()
            logger.debug(f"Undo: Transform {self.feature.mode} on {self.body.name}")
        except Exception as e:
            logger.error(f"Transform undo failed ({self.feature.mode}): {e}")
            _restore_body_state(self.body, tx_state)
            CADTessellator.notify_body_changed()
            _update_body_ui(self.main_window, self.body)
            self._update_gizmo_position()

    @staticmethod
    def _create_inverse_transform(feature):
        """Build inverse TransformFeature for undo."""
        from modeling import TransformFeature

        mode = getattr(feature, "mode", "")
        data = deepcopy(getattr(feature, "data", {})) or {}

        if mode == "move":
            trans = list(data.get("translation", [0.0, 0.0, 0.0]))
            while len(trans) < 3:
                trans.append(0.0)
            return TransformFeature(
                mode="move",
                data={"translation": [-float(trans[0]), -float(trans[1]), -float(trans[2])]},
            )

        if mode == "rotate":
            return TransformFeature(
                mode="rotate",
                data={
                    "axis": data.get("axis", "Z"),
                    "angle": -float(data.get("angle", 0.0)),
                    "center": list(data.get("center", [0.0, 0.0, 0.0])),
                },
            )

        if mode == "scale":
            factor = float(data.get("factor", 1.0))
            if abs(factor) < 1e-12:
                return None
            return TransformFeature(
                mode="scale",
                data={
                    "factor": 1.0 / factor,
                    "center": list(data.get("center", [0.0, 0.0, 0.0])),
                },
            )

        if mode == "mirror":
            return TransformFeature(
                mode="mirror",
                data={"plane": data.get("plane", "XY")},
            )

        return None

