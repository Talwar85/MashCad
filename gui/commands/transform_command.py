"""
MashCad - Transform Command for Undo/Redo
Implements QUndoCommand for undoable transform operations
"""

from PySide6.QtGui import QUndoCommand
from loguru import logger


class TransformCommand(QUndoCommand):
    """
    Undoable transform operation that adds/removes TransformFeature.

    Features:
    - Adds feature on redo()
    - Removes feature on undo()
    - Triggers body rebuild automatically
    - Integrates with Qt's QUndoStack
    """

    def __init__(self, body, feature, main_window):
        """
        Args:
            body: Body instance to transform
            feature: TransformFeature to add/remove
            main_window: MainWindow reference for UI updates
        """
        super().__init__(f"Transform: {feature.mode.capitalize()}")
        self.body = body
        self.feature = feature
        self.main_window = main_window
        self.old_feature_count = len(body.features)

    def _update_gizmo_position(self):
        """Aktualisiert die Gizmo-Position falls es aktiv ist"""
        viewport = self.main_window.viewport_3d
        if hasattr(viewport, 'is_transform_active') and viewport.is_transform_active():
            if hasattr(viewport, 'show_transform_gizmo'):
                viewport.show_transform_gizmo(self.body.id, force_refresh=True)

    def redo(self):
        """
        Apply transform by adding feature to body.
        Called automatically when command is pushed to stack.

        WICHTIG: Transform-Features werden NICHT über _rebuild() angewendet,
        sondern direkt auf das aktuelle Solid. Das verhindert, dass vorherige
        Features (z.B. Extrudes mit precalculated_polys) fehlschlagen.
        """
        from modeling.cad_tessellator import CADTessellator

        logger.info(f"🔧 TransformCommand.redo() CALLED")
        logger.info(f"   Body: {self.body.name}")
        logger.info(f"   Feature: {self.feature.name}")
        logger.info(f"   Mode: {self.feature.mode}")
        logger.info(f"   Data: {self.feature.data}")

        # Only add if not already added
        if len(self.body.features) == self.old_feature_count:
            # Feature zur History hinzufügen (OHNE _rebuild!)
            self.body.features.append(self.feature)
            logger.info(f"   ✅ Feature added to body.features")

            # Transform direkt auf aktuelles Solid anwenden
            try:
                logger.info(f"   🔨 Calling _apply_transform_feature...")
                new_solid = self.body._apply_transform_feature(
                    self.body._build123d_solid,
                    self.feature
                )
                logger.info(f"   Transform result: {new_solid is not None}")

                if new_solid:
                    logger.info(f"   ✅ Transform successful - updating body")
                    self.body._build123d_solid = new_solid
                    if hasattr(new_solid, 'wrapped'):
                        self.body.shape = new_solid.wrapped

                    # ✅ CRITICAL FIX: Clear ENTIRE cache after transform
                    # Transform creates NEW solid which may reuse Python IDs
                    CADTessellator.notify_body_changed()
                    logger.debug(f"🔄 Cache komplett gelöscht nach Transform")
                    # Mesh aktualisieren
                    logger.info(f"   🔄 Updating mesh from solid...")
                    self.body._update_mesh_from_solid(new_solid)
                    self.feature.status = "OK"
                    logger.success(f"✅ Transform direkt angewendet: {self.feature.mode}")
                else:
                    self.feature.status = "ERROR"
                    logger.error("❌ Transform returned None")
            except Exception as e:
                self.feature.status = "ERROR"
                logger.error(f"Transform Error: {e}")

            # UI Update (IMMER ausführen, auch bei Erfolg!)
            logger.info(f"   🖼️  Updating UI (viewport + browser)...")
            self.main_window._update_body_from_build123d(
                self.body,
                self.body._build123d_solid
            )
            self.main_window.browser.refresh()
            logger.info(f"   ✅ UI updated")

            # Gizmo an neue Position verschieben falls aktiv
            self._update_gizmo_position()
            logger.info(f"✅ TransformCommand.redo() FINISHED")

    def undo(self):
        """
        Revert transform by removing feature from body.
        Called when user presses Ctrl+Z.

        WICHTIG: Wendet die INVERSE Transform-Operation an, statt _rebuild().
        Das verhindert Fehler bei vorherigen Extrude-Features.
        """
        from modeling.cad_tessellator import CADTessellator

        # Only remove if it was added
        if len(self.body.features) > self.old_feature_count:
            removed_feature = self.body.features.pop()
            logger.debug(f"Undo: Removed {removed_feature.name} from {self.body.name}")

            # Inverse Transform anwenden statt _rebuild()
            try:
                # Erstelle inverse TransformFeature
                inverse_feature = self._create_inverse_transform(removed_feature)
                if inverse_feature:
                    new_solid = self.body._apply_transform_feature(
                        self.body._build123d_solid,
                        inverse_feature
                    )
                    if new_solid:
                        self.body._build123d_solid = new_solid
                        if hasattr(new_solid, 'wrapped'):
                            self.body.shape = new_solid.wrapped

                        # ✅ CRITICAL FIX: Clear ENTIRE cache after transform
                        CADTessellator.notify_body_changed()
                        logger.debug(f"🔄 Cache komplett gelöscht nach Inverse Transform")

                        self.body._update_mesh_from_solid(new_solid)
                        logger.success(f"Undo: Inverse Transform angewendet")
                    else:
                        # Fallback zu _rebuild() wenn inverse Transform fehlschlägt
                        logger.warning("Inverse Transform failed, using _rebuild()")
                        self.body._rebuild()
                else:
                    # Fallback für unbekannte Transform-Typen
                    self.body._rebuild()
            except Exception as e:
                logger.error(f"Undo Error: {e}, using _rebuild()")
                self.body._rebuild()

            # UI Update (IMMER ausführen!)
            self.main_window._update_body_from_build123d(
                self.body,
                self.body._build123d_solid
            )
            self.main_window.browser.refresh()

            # Gizmo an neue Position verschieben falls aktiv
            self._update_gizmo_position()

    def _create_inverse_transform(self, feature):
        """
        Erstellt ein inverses TransformFeature für Undo.
        """
        from modeling import TransformFeature

        mode = feature.mode
        data = feature.data

        if mode == "move":
            # Inverse: Negative Translation
            trans = data.get("translation", [0, 0, 0])
            return TransformFeature(
                mode="move",
                data={"translation": [-trans[0], -trans[1], -trans[2]]}
            )

        elif mode == "rotate":
            # Inverse: Negative Winkel, gleiche Achse/Center
            return TransformFeature(
                mode="rotate",
                data={
                    "axis": data.get("axis", "Z"),
                    "angle": -data.get("angle", 0),
                    "center": data.get("center", [0, 0, 0])
                }
            )

        elif mode == "scale":
            # Inverse: 1/factor, gleicher Center
            factor = data.get("factor", 1.0)
            if abs(factor) < 1e-6:
                return None  # Division by zero protection
            return TransformFeature(
                mode="scale",
                data={
                    "factor": 1.0 / factor,
                    "center": data.get("center", [0, 0, 0])
                }
            )

        elif mode == "mirror":
            # Mirror ist selbst-invers (mirror mirror = original)
            return TransformFeature(
                mode="mirror",
                data={"plane": data.get("plane", "XY")}
            )

        return None


class DeleteFeatureCommand(QUndoCommand):
    """
    Undoable feature deletion.

    Stores feature index and data for restoration.
    """

    def __init__(self, body, feature, feature_index, main_window):
        super().__init__(f"Delete {feature.name}")
        self.body = body
        self.feature = feature
        self.feature_index = feature_index
        self.main_window = main_window

    def _update_gizmo_position(self):
        """Aktualisiert die Gizmo-Position falls es aktiv ist"""
        viewport = self.main_window.viewport_3d
        if hasattr(viewport, 'is_transform_active') and viewport.is_transform_active():
            if hasattr(viewport, 'show_transform_gizmo'):
                viewport.show_transform_gizmo(self.body.id, force_refresh=True)

    def redo(self):
        """Remove feature"""
        from modeling.cad_tessellator import CADTessellator

        if self.feature in self.body.features:
            self.body.features.remove(self.feature)
            logger.debug(f"Redo: Deleted {self.feature.name}")

            # ✅ CRITICAL FIX: Cache clearing happens inside _rebuild()
            self.body._rebuild()
            self.main_window._update_body_from_build123d(
                self.body,
                self.body._build123d_solid
            )
            self.main_window.browser.refresh()

    def undo(self):
        """Restore feature at original position"""
        from modeling.cad_tessellator import CADTessellator

        if self.feature not in self.body.features:
            # Insert at original index
            self.body.features.insert(self.feature_index, self.feature)
            logger.debug(f"Undo: Restored {self.feature.name}")

            # ✅ CRITICAL FIX: Cache clearing happens inside _rebuild()
            self.body._rebuild()
            self.main_window._update_body_from_build123d(
                self.body,
                self.body._build123d_solid
            )
            self.main_window.browser.refresh()

            # Gizmo an neue Position verschieben falls aktiv
            self._update_gizmo_position()


class EditFeatureCommand(QUndoCommand):
    """
    Undoable feature editing.

    Stores old and new data for feature.
    """

    def __init__(self, body, feature, old_data, new_data, main_window):
        super().__init__(f"Edit {feature.name}")
        self.body = body
        self.feature = feature
        self.old_data = old_data.copy()
        self.new_data = new_data.copy()
        self.main_window = main_window

    def _update_gizmo_position(self):
        """Aktualisiert die Gizmo-Position falls es aktiv ist"""
        viewport = self.main_window.viewport_3d
        if hasattr(viewport, 'is_transform_active') and viewport.is_transform_active():
            if hasattr(viewport, 'show_transform_gizmo'):
                viewport.show_transform_gizmo(self.body.id, force_refresh=True)

    def redo(self):
        """Apply new data"""
        from modeling.cad_tessellator import CADTessellator

        self.feature.data = self.new_data.copy()
        logger.debug(f"Redo: Applied new data to {self.feature.name}")

        # ✅ CRITICAL FIX: Cache clearing happens inside _rebuild()
        self.body._rebuild()
        self.main_window._update_body_from_build123d(
            self.body,
            self.body._build123d_solid
        )
        self.main_window.browser.refresh()

    def undo(self):
        """Restore old data"""
        from modeling.cad_tessellator import CADTessellator

        self.feature.data = self.old_data.copy()
        logger.debug(f"Undo: Restored old data to {self.feature.name}")

        # ✅ CRITICAL FIX: Cache clearing happens inside _rebuild()
        self.body._rebuild()
        self.main_window._update_body_from_build123d(
            self.body,
            self.body._build123d_solid
        )
        self.main_window.browser.refresh()

        # Gizmo an neue Position verschieben falls aktiv
        self._update_gizmo_position()
