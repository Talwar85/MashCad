"""
MashCad - Feature Commands for Undo/Redo
Implements QUndoCommand for undoable feature operations (Extrude, Fillet, etc.)
"""

from PySide6.QtGui import QUndoCommand
from loguru import logger


class AddFeatureCommand(QUndoCommand):
    """
    Undoable command for adding any feature to a body.
    Works with: ExtrudeFeature, FilletFeature, ChamferFeature, etc.
    """

    def __init__(self, body, feature, main_window, description=None, skip_rebuild=False):
        """
        Args:
            body: Body instance to modify
            feature: Feature to add (ExtrudeFeature, FilletFeature, etc.)
            main_window: MainWindow reference for UI updates
            description: Optional description for undo menu
            skip_rebuild: Wenn True, wird kein Rebuild gemacht (z.B. wenn BRepFeat
                          das Solid bereits direkt aktualisiert hat)
        """
        desc = description or f"Add {feature.name}"
        super().__init__(desc)
        self.body = body
        self.feature = feature
        self.main_window = main_window
        self._first_redo = True  # Track if this is first redo (push adds feature)
        self._skip_rebuild = skip_rebuild

    def redo(self):
        """
        Apply feature by adding it to body.
        Called automatically when command is pushed to stack.
        """
        from modeling.cad_tessellator import CADTessellator

        # Feature hinzufügen (nur wenn noch nicht vorhanden)
        if self.feature not in self.body.features:
            # Bei skip_rebuild: Feature nur zur Liste hinzufügen, kein Rebuild
            # (weil das Solid bereits durch BRepFeat o.ä. aktualisiert wurde)
            rebuild = not self._skip_rebuild
            self.body.add_feature(self.feature, rebuild=rebuild)
            logger.debug(f"Redo: Added {self.feature.name} to {self.body.name} (rebuild={rebuild})")

            # TNP v3.0: ShapeReferences registrieren
            self.body._register_feature_shape_refs(self.feature)

        # Rebuild & Update UI
        try:
            CADTessellator.notify_body_changed()
            self.main_window._update_body_from_build123d(
                self.body,
                self.body._build123d_solid
            )
            self.main_window.browser.refresh()
        except Exception as e:
            logger.error(f"Fehler bei UI-Update nach Redo: {e}")

    def undo(self):
        """
        Revert by removing feature from body.
        Called when user presses Ctrl+Z.
        """
        from modeling.cad_tessellator import CADTessellator

        # TNP v3.0: ShapeReferences vor Entfernung aus Registry entfernen
        self.body._unregister_feature_shape_refs(self.feature)

        # Feature entfernen
        if self.feature in self.body.features:
            self.body.features.remove(self.feature)
            logger.debug(f"Undo: Removed {self.feature.name} from {self.body.name}")

            # Rebuild body ohne das Feature
            CADTessellator.notify_body_changed()
            self.body._rebuild()

            # Update UI
            try:
                self.main_window._update_body_from_build123d(
                    self.body,
                    self.body._build123d_solid
                )
                self.main_window.browser.refresh()
            except Exception as e:
                logger.error(f"Fehler bei UI-Update nach Undo: {e}")


class DeleteFeatureCommand(QUndoCommand):
    """
    Undoable command for deleting a feature from a body.
    """

    def __init__(self, body, feature, feature_index, main_window):
        """
        Args:
            body: Body to modify
            feature: Feature to delete
            feature_index: Index of feature in body.features
            main_window: MainWindow reference
        """
        super().__init__(f"Delete {feature.name}")
        self.body = body
        self.feature = feature
        self.feature_index = feature_index
        self.main_window = main_window

    def redo(self):
        """Delete feature."""
        from modeling.cad_tessellator import CADTessellator

        # TNP v3.0: Unregister shape refs
        self.body._unregister_feature_shape_refs(self.feature)

        # Remove feature
        if self.feature in self.body.features:
            self.body.features.remove(self.feature)
            logger.debug(f"Redo: Deleted {self.feature.name}")

            # Rebuild
            CADTessellator.notify_body_changed()
            self.body._rebuild()

            # Update UI
            try:
                self.main_window._update_body_from_build123d(
                    self.body,
                    self.body._build123d_solid
                )
                self.main_window.browser.refresh()
            except Exception as e:
                logger.error(f"Fehler bei UI-Update nach Delete Redo: {e}")

    def undo(self):
        """Restore feature."""
        from modeling.cad_tessellator import CADTessellator

        # Re-insert feature at original index
        self.body.features.insert(self.feature_index, self.feature)
        logger.debug(f"Undo: Restored {self.feature.name}")

        # TNP v3.0: Re-register shape refs
        self.body._register_feature_shape_refs(self.feature)

        # Rebuild
        CADTessellator.notify_body_changed()
        self.body._rebuild()

        # Update UI
        try:
            self.main_window._update_body_from_build123d(
                self.body,
                self.body._build123d_solid
            )
            self.main_window.browser.refresh()
        except Exception as e:
            logger.error(f"Fehler bei UI-Update nach Delete Undo: {e}")


class EditFeatureCommand(QUndoCommand):
    """
    Undoable command for editing feature parameters.
    Supports: Radius, Distance, Angle, etc.
    """

    def __init__(self, body, feature, old_params, new_params, main_window):
        """
        Args:
            body: Body containing the feature
            feature: Feature to edit
            old_params: Dict of old parameter values
            new_params: Dict of new parameter values
            main_window: MainWindow reference
        """
        super().__init__(f"Edit {feature.name}")
        self.body = body
        self.feature = feature
        self.old_params = old_params
        self.new_params = new_params
        self.main_window = main_window

    def _apply_params(self, params):
        """Helper to apply parameters to feature."""
        for key, value in params.items():
            if hasattr(self.feature, key):
                setattr(self.feature, key, value)

    def redo(self):
        """Apply new parameters."""
        from modeling.cad_tessellator import CADTessellator

        self._apply_params(self.new_params)
        logger.debug(f"Redo: Applied new params to {self.feature.name}")

        # Rebuild
        CADTessellator.notify_body_changed()
        self.body._rebuild()

        # Update UI
        try:
            self.main_window._update_body_from_build123d(
                self.body,
                self.body._build123d_solid
            )
            self.main_window.browser.refresh()
        except Exception as e:
            logger.error(f"Fehler bei UI-Update nach Edit Redo: {e}")

    def undo(self):
        """Restore old parameters."""
        from modeling.cad_tessellator import CADTessellator

        self._apply_params(self.old_params)
        logger.debug(f"Undo: Restored old params for {self.feature.name}")

        # Rebuild
        CADTessellator.notify_body_changed()
        self.body._rebuild()

        # Update UI
        try:
            self.main_window._update_body_from_build123d(
                self.body,
                self.body._build123d_solid
            )
            self.main_window.browser.refresh()
        except Exception as e:
            logger.error(f"Fehler bei UI-Update nach Edit Undo: {e}")


class AddBodyCommand(QUndoCommand):
    """
    Undoable command for adding a new body to the document.
    Used for: Sweep (New Body), Loft (New Body), Push/Pull (New Body), etc.
    """

    def __init__(self, document, body, main_window, description=None):
        """
        Args:
            document: Document instance
            body: Body instance to add
            main_window: MainWindow reference for UI updates
            description: Optional description for undo menu
        """
        desc = description or f"Add Body {body.name}"
        super().__init__(desc)
        self.document = document
        self.body = body
        self.main_window = main_window

    def redo(self):
        """Add body to document."""
        from modeling.cad_tessellator import CADTessellator

        if self.body not in self.document.bodies:
            self.document.add_body(self.body, set_active=False)
            logger.debug(f"Redo: Added body {self.body.name}")

        # Update UI
        try:
            CADTessellator.notify_body_changed()
            self.main_window._update_body_from_build123d(
                self.body,
                self.body._build123d_solid
            )
            self.main_window.browser.refresh()
        except Exception as e:
            logger.error(f"Fehler bei UI-Update nach AddBody Redo: {e}")

    def undo(self):
        """Remove body from document."""
        from modeling.cad_tessellator import CADTessellator

        if self.body in self.document.bodies:
            # Remove from viewport first
            try:
                self.main_window.viewport_3d.remove_body(self.body.id)
            except Exception:
                pass

            self.document.bodies.remove(self.body)
            logger.debug(f"Undo: Removed body {self.body.name}")

            # Update UI
            try:
                CADTessellator.notify_body_changed()
                self.main_window.browser.refresh()
            except Exception as e:
                logger.error(f"Fehler bei UI-Update nach AddBody Undo: {e}")


class SplitBodyCommand(QUndoCommand):
    """
    Undo/Redo Command für Body-Split-Operationen.

    Multi-Body Split Architecture (AGENTS.md Phase 4):
    - Tracked: Original Body (vor Split), Body Above, Body Below
    - Redo: Split durchführen via Document.split_body()
    - Undo: Beide Bodies löschen, Original wiederherstellen
    """

    def __init__(self, document, original_body, plane_origin, plane_normal, main_window):
        """
        Args:
            document: Document instance
            original_body: Body vor dem Split
            plane_origin: Tuple (x, y, z) - Ursprung der Split-Ebene
            plane_normal: Tuple (x, y, z) - Normale der Split-Ebene
            main_window: MainWindow reference für UI updates
        """
        super().__init__("Split Body")
        self.document = document
        self.main_window = main_window

        # Plane-Parameter
        self.plane_origin = plane_origin
        self.plane_normal = plane_normal

        # Snapshots
        self.original_body_snapshot = original_body.to_dict()
        self.original_body_id = original_body.id
        self.original_body_name = original_body.name

        # IDs der Split-Bodies (werden beim ersten redo() gesetzt)
        self.body_above_id = None
        self.body_below_id = None

    def redo(self):
        """
        Split durchführen: Original löschen, 2 neue Bodies hinzufügen.
        """
        from modeling.cad_tessellator import CADTessellator
        from modeling import Body

        # Original Body finden oder aus Snapshot wiederherstellen
        original = self.document.find_body_by_id(self.original_body_id)

        if original is None:
            # Redo nach Undo: Original aus Snapshot wiederherstellen
            original = Body.from_dict(self.original_body_snapshot)
            original._document = self.document
            original._rebuild()
            logger.debug(f"SplitBody Redo: Original '{original.name}' aus Snapshot wiederhergestellt")

        # Split durchführen
        try:
            body_above, body_below = self.document.split_body(
                original,
                self.plane_origin,
                self.plane_normal
            )

            # IDs speichern für Undo
            self.body_above_id = body_above.id
            self.body_below_id = body_below.id

            logger.debug(f"SplitBody Redo: '{self.original_body_name}' → '{body_above.name}' + '{body_below.name}'")

            # Update UI
            try:
                CADTessellator.notify_body_changed()
                # Beide Bodies im Viewport darstellen
                self.main_window._update_body_from_build123d(body_above, body_above._build123d_solid)
                self.main_window._update_body_from_build123d(body_below, body_below._build123d_solid)
                self.main_window.browser.refresh()
            except Exception as e:
                logger.error(f"Fehler bei UI-Update nach SplitBody Redo: {e}")

        except Exception as e:
            logger.error(f"SplitBody Redo fehlgeschlagen: {e}")
            # Bei Fehler: Original bleibt erhalten
            return

    def undo(self):
        """
        Split rückgängig: Beide Bodies löschen, Original wiederherstellen.
        """
        from modeling.cad_tessellator import CADTessellator
        from modeling import Body

        # 1. Beide Split-Bodies aus Document entfernen
        body_above = self.document.find_body_by_id(self.body_above_id) if self.body_above_id else None
        body_below = self.document.find_body_by_id(self.body_below_id) if self.body_below_id else None

        if body_above and body_above in self.document.bodies:
            # Remove from viewport
            try:
                self.main_window.viewport_3d.remove_body(body_above.id)
            except Exception:
                pass
            self.document.bodies.remove(body_above)
            logger.debug(f"SplitBody Undo: Removed '{body_above.name}'")

        if body_below and body_below in self.document.bodies:
            # Remove from viewport
            try:
                self.main_window.viewport_3d.remove_body(body_below.id)
            except Exception:
                pass
            self.document.bodies.remove(body_below)
            logger.debug(f"SplitBody Undo: Removed '{body_below.name}'")

        # 2. Original Body wiederherstellen
        original_body = Body.from_dict(self.original_body_snapshot)
        original_body._document = self.document

        # WICHTIG: Split-Feature entfernen (wurde beim Split hinzugefügt)
        from modeling import SplitFeature
        if original_body.features and isinstance(original_body.features[-1], SplitFeature):
            original_body.features.pop()
            logger.debug(f"SplitBody Undo: Split-Feature aus Original entfernt")

        # Rebuild ohne Split-Feature
        try:
            original_body._rebuild()
        except Exception as e:
            logger.warning(f"SplitBody Undo: Rebuild fehlgeschlagen: {e}")

        # 3. Original Body zum Document hinzufügen
        self.document.add_body(original_body, set_active=False)
        logger.info(f"SplitBody Undo: Original '{original_body.name}' wiederhergestellt")

        # Update UI
        try:
            CADTessellator.notify_body_changed()
            self.main_window._update_body_from_build123d(original_body, original_body._build123d_solid)
            self.main_window.browser.refresh()
        except Exception as e:
            logger.error(f"Fehler bei UI-Update nach SplitBody Undo: {e}")
