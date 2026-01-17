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

    def redo(self):
        """
        Apply transform by adding feature to body.
        Called automatically when command is pushed to stack.
        """
        from modeling.cad_tessellator import CADTessellator

        # Only add if not already added
        if len(self.body.features) == self.old_feature_count:
            self.body.add_feature(self.feature)
            logger.debug(f"Redo: Added {self.feature.name} to {self.body.name}")

            # Rebuild & Update UI
            with CADTessellator.invalidate_cache():
                self.main_window._update_body_from_build123d(
                    self.body,
                    self.body._build123d_solid
                )
                self.main_window.browser.refresh()

    def undo(self):
        """
        Revert transform by removing feature from body.
        Called when user presses Ctrl+Z.
        """
        from modeling.cad_tessellator import CADTessellator

        # Only remove if it was added
        if len(self.body.features) > self.old_feature_count:
            removed_feature = self.body.features.pop()
            logger.debug(f"Undo: Removed {removed_feature.name} from {self.body.name}")

            # Rebuild without this feature
            with CADTessellator.invalidate_cache():
                self.body._rebuild()
                self.main_window._update_body_from_build123d(
                    self.body,
                    self.body._build123d_solid
                )
                self.main_window.browser.refresh()


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

    def redo(self):
        """Remove feature"""
        from modeling.cad_tessellator import CADTessellator

        if self.feature in self.body.features:
            self.body.features.remove(self.feature)
            logger.debug(f"Redo: Deleted {self.feature.name}")

            with CADTessellator.invalidate_cache():
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

            with CADTessellator.invalidate_cache():
                self.body._rebuild()
                self.main_window._update_body_from_build123d(
                    self.body,
                    self.body._build123d_solid
                )
                self.main_window.browser.refresh()


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

    def redo(self):
        """Apply new data"""
        from modeling.cad_tessellator import CADTessellator

        self.feature.data = self.new_data.copy()
        logger.debug(f"Redo: Applied new data to {self.feature.name}")

        with CADTessellator.invalidate_cache():
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

        with CADTessellator.invalidate_cache():
            self.body._rebuild()
            self.main_window._update_body_from_build123d(
                self.body,
                self.body._build123d_solid
            )
            self.main_window.browser.refresh()
