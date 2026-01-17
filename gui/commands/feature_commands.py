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

    def __init__(self, body, feature, main_window, description=None):
        """
        Args:
            body: Body instance to modify
            feature: Feature to add (ExtrudeFeature, FilletFeature, etc.)
            main_window: MainWindow reference for UI updates
            description: Optional description for undo menu
        """
        desc = description or f"Add {feature.name}"
        super().__init__(desc)
        self.body = body
        self.feature = feature
        self.main_window = main_window
        self._first_redo = True  # Track if this is first redo (push adds feature)

    def redo(self):
        """
        Apply feature by adding it to body.
        Called automatically when command is pushed to stack.
        """
        from modeling.cad_tessellator import CADTessellator

        # Feature hinzufügen (nur wenn noch nicht vorhanden)
        if self.feature not in self.body.features:
            self.body.add_feature(self.feature)
            logger.debug(f"Redo: Added {self.feature.name} to {self.body.name}")

        # Rebuild & Update UI
        try:
            CADTessellator.clear_cache()
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
            CADTessellator.clear_cache()
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

            CADTessellator.clear_cache()
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

            CADTessellator.clear_cache()
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

        CADTessellator.clear_cache()
        self.body._rebuild()
        self.main_window._update_body_from_build123d(
            self.body, self.body._build123d_solid
        )
        self.main_window.browser.refresh()
