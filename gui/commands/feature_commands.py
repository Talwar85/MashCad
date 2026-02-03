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
            body: Body instance
            feature: Feature to delete
            feature_index: Original index in features list
            main_window: MainWindow reference
        """
        super().__init__(f"Delete {feature.name}")
        self.body = body
        self.feature = feature
        self.feature_index = feature_index
        self.main_window = main_window

    def redo(self):
        """Delete the feature."""
        from modeling.cad_tessellator import CADTessellator

        if self.feature in self.body.features:
            self.body.features.remove(self.feature)
            logger.debug(f"Redo Delete: Removed {self.feature.name}")

            CADTessellator.notify_body_changed()
            self.body._rebuild()
            self.main_window._update_body_from_build123d(
                self.body, self.body._build123d_solid
            )
            self.main_window.browser.refresh()

    def undo(self):
        """Restore the feature."""
        from modeling.cad_tessellator import CADTessellator

        # Feature an ursprünglicher Position einfügen
        if self.feature not in self.body.features:
            idx = min(self.feature_index, len(self.body.features))
            self.body.features.insert(idx, self.feature)
            logger.debug(f"Undo Delete: Restored {self.feature.name} at index {idx}")

            CADTessellator.notify_body_changed()
            self.body._rebuild()
            self.main_window._update_body_from_build123d(
                self.body, self.body._build123d_solid
            )
            self.main_window.browser.refresh()


class EditFeatureCommand(QUndoCommand):
    """
    Undoable command for editing feature parameters.
    """

    def __init__(self, body, feature, old_data, new_data, main_window):
        """
        Args:
            body: Body instance
            feature: Feature being edited
            old_data: Dict with original parameter values
            new_data: Dict with new parameter values
            main_window: MainWindow reference
        """
        super().__init__(f"Edit {feature.name}")
        self.body = body
        self.feature = feature
        self.old_data = old_data
        self.new_data = new_data
        self.main_window = main_window

    def redo(self):
        """Apply new values."""
        self._apply_data(self.new_data)

    def undo(self):
        """Restore old values."""
        self._apply_data(self.old_data)

    def _apply_data(self, data):
        """Apply parameter dict to feature."""
        from modeling.cad_tessellator import CADTessellator

        for key, value in data.items():
            if hasattr(self.feature, key):
                setattr(self.feature, key, value)

        CADTessellator.notify_body_changed()

        # Phase 7: Inkrementeller Rebuild mit changed_feature_id
        self.body._rebuild(changed_feature_id=self.feature.id)

        self.main_window._update_body_from_build123d(
            self.body, self.body._build123d_solid
        )
        self.main_window.browser.refresh()


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
            self.document.bodies.append(self.body)
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
