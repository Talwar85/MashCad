"""
MashCad - Component Commands for Undo/Redo (Assembly-System Phase 5)
=====================================================================

Implements QUndoCommand for undoable component operations:
- CreateComponentCommand: Neue Sub-Component erstellen
- DeleteComponentCommand: Component löschen (mit Inhalt)
- MoveBodyToComponentCommand: Body zwischen Components verschieben
- RenameComponentCommand: Component umbenennen
- ActivateComponentCommand: Component aktivieren
"""

from PySide6.QtGui import QUndoCommand
from loguru import logger


class CreateComponentCommand(QUndoCommand):
    """
    Undoable: Neue Sub-Component in einer Parent-Component erstellen.
    """

    def __init__(self, parent_component, component_name, main_window):
        """
        Args:
            parent_component: Die Parent-Component
            component_name: Name der neuen Component
            main_window: MainWindow für UI-Updates
        """
        super().__init__(f"Create Component '{component_name}'")
        self.parent_component = parent_component
        self.component_name = component_name
        self.main_window = main_window
        self.created_component = None

    def redo(self):
        """Component erstellen."""
        from modeling import Component

        if self.created_component is None:
            # Erste Ausführung: Neue Component erstellen
            self.created_component = Component(name=self.component_name)
            self.created_component.parent = self.parent_component

        # Zur Parent hinzufügen
        if self.created_component not in self.parent_component.sub_components:
            self.parent_component.sub_components.append(self.created_component)
            logger.info(f"[ASSEMBLY] Component erstellt: {self.component_name} in {self.parent_component.name}")

        # UI aktualisieren
        self.main_window.browser.refresh()
        self.main_window._update_viewport_all_impl()

    def undo(self):
        """Component entfernen."""
        if self.created_component in self.parent_component.sub_components:
            self.parent_component.sub_components.remove(self.created_component)
            logger.info(f"[ASSEMBLY] Component entfernt (Undo): {self.component_name}")

        # UI aktualisieren
        self.main_window.browser.refresh()
        self.main_window._update_viewport_all_impl()


class DeleteComponentCommand(QUndoCommand):
    """
    Undoable: Component löschen (mit allen Bodies, Sketches, Sub-Components).
    """

    def __init__(self, component, main_window):
        """
        Args:
            component: Die zu löschende Component
            main_window: MainWindow für UI-Updates
        """
        super().__init__(f"Delete Component '{component.name}'")
        self.component = component
        self.parent_component = component.parent
        self.main_window = main_window
        # Index merken für korrekte Wiederherstellung
        self.original_index = None
        if self.parent_component:
            try:
                self.original_index = self.parent_component.sub_components.index(component)
            except ValueError:
                self.original_index = len(self.parent_component.sub_components)

    def redo(self):
        """Component löschen."""
        if self.parent_component and self.component in self.parent_component.sub_components:
            self.parent_component.sub_components.remove(self.component)
            logger.info(f"[ASSEMBLY] Component gelöscht: {self.component.name}")

            # Falls gelöschte Component aktiv war, zur Parent wechseln
            if self.main_window.document._active_component == self.component:
                self.main_window.document._active_component = self.parent_component
                self.parent_component.is_active = True
                self.component.is_active = False

        # UI aktualisieren
        self.main_window.browser.refresh()
        self.main_window._update_viewport_all_impl()

    def undo(self):
        """Component wiederherstellen."""
        if self.parent_component and self.component not in self.parent_component.sub_components:
            # An ursprünglicher Position einfügen
            idx = self.original_index if self.original_index is not None else len(self.parent_component.sub_components)
            idx = min(idx, len(self.parent_component.sub_components))
            self.parent_component.sub_components.insert(idx, self.component)
            self.component.parent = self.parent_component
            logger.info(f"[ASSEMBLY] Component wiederhergestellt (Undo): {self.component.name}")

        # UI aktualisieren
        self.main_window.browser.refresh()
        self.main_window._update_viewport_all_impl()


class MoveBodyToComponentCommand(QUndoCommand):
    """
    Undoable: Body von einer Component zu einer anderen verschieben.
    """

    def __init__(self, body, source_component, target_component, main_window):
        """
        Args:
            body: Der zu verschiebende Body
            source_component: Quell-Component
            target_component: Ziel-Component
            main_window: MainWindow für UI-Updates
        """
        super().__init__(f"Move '{body.name}' to '{target_component.name}'")
        self.body = body
        self.source_component = source_component
        self.target_component = target_component
        self.main_window = main_window
        # Original-Index für korrekte Wiederherstellung
        try:
            self.source_index = source_component.bodies.index(body)
        except ValueError:
            self.source_index = 0

    def redo(self):
        """Body verschieben."""
        # Aus Quell-Component entfernen
        if self.body in self.source_component.bodies:
            self.source_component.bodies.remove(self.body)

        # Zu Ziel-Component hinzufügen
        if self.body not in self.target_component.bodies:
            self.target_component.bodies.append(self.body)

        logger.info(f"[ASSEMBLY] Body '{self.body.name}' verschoben: {self.source_component.name} → {self.target_component.name}")

        # UI aktualisieren
        self.main_window.browser.refresh()
        self.main_window._update_viewport_all_impl()

    def undo(self):
        """Body zurück verschieben."""
        # Aus Ziel-Component entfernen
        if self.body in self.target_component.bodies:
            self.target_component.bodies.remove(self.body)

        # Zu Quell-Component hinzufügen (an ursprünglicher Position)
        if self.body not in self.source_component.bodies:
            idx = min(self.source_index, len(self.source_component.bodies))
            self.source_component.bodies.insert(idx, self.body)

        logger.info(f"[ASSEMBLY] Body '{self.body.name}' zurück verschoben (Undo): {self.target_component.name} → {self.source_component.name}")

        # UI aktualisieren
        self.main_window.browser.refresh()
        self.main_window._update_viewport_all_impl()


class MoveSketchToComponentCommand(QUndoCommand):
    """
    Undoable: Sketch von einer Component zu einer anderen verschieben.
    """

    def __init__(self, sketch, source_component, target_component, main_window):
        """
        Args:
            sketch: Der zu verschiebende Sketch
            source_component: Quell-Component
            target_component: Ziel-Component
            main_window: MainWindow für UI-Updates
        """
        super().__init__(f"Move Sketch '{sketch.name}' to '{target_component.name}'")
        self.sketch = sketch
        self.source_component = source_component
        self.target_component = target_component
        self.main_window = main_window
        # Original-Index für korrekte Wiederherstellung
        try:
            self.source_index = source_component.sketches.index(sketch)
        except ValueError:
            self.source_index = 0

    def redo(self):
        """Sketch verschieben."""
        if self.sketch in self.source_component.sketches:
            self.source_component.sketches.remove(self.sketch)

        if self.sketch not in self.target_component.sketches:
            self.target_component.sketches.append(self.sketch)

        logger.info(f"[ASSEMBLY] Sketch '{self.sketch.name}' verschoben: {self.source_component.name} → {self.target_component.name}")

        self.main_window.browser.refresh()
        self.main_window._update_viewport_all_impl()

    def undo(self):
        """Sketch zurück verschieben."""
        if self.sketch in self.target_component.sketches:
            self.target_component.sketches.remove(self.sketch)

        if self.sketch not in self.source_component.sketches:
            idx = min(self.source_index, len(self.source_component.sketches))
            self.source_component.sketches.insert(idx, self.sketch)

        logger.info(f"[ASSEMBLY] Sketch '{self.sketch.name}' zurück verschoben (Undo)")

        self.main_window.browser.refresh()
        self.main_window._update_viewport_all_impl()


class RenameComponentCommand(QUndoCommand):
    """
    Undoable: Component umbenennen.
    """

    def __init__(self, component, old_name, new_name, main_window):
        """
        Args:
            component: Die Component
            old_name: Alter Name
            new_name: Neuer Name
            main_window: MainWindow für UI-Updates
        """
        super().__init__(f"Rename '{old_name}' to '{new_name}'")
        self.component = component
        self.old_name = old_name
        self.new_name = new_name
        self.main_window = main_window

    def redo(self):
        """Umbenennen."""
        self.component.name = self.new_name
        logger.info(f"[ASSEMBLY] Component umbenannt: {self.old_name} → {self.new_name}")
        self.main_window.browser.refresh()

    def undo(self):
        """Zurück umbenennen."""
        self.component.name = self.old_name
        logger.info(f"[ASSEMBLY] Component umbenannt (Undo): {self.new_name} → {self.old_name}")
        self.main_window.browser.refresh()


class ActivateComponentCommand(QUndoCommand):
    """
    Undoable: Component aktivieren (= als aktiven Arbeitskontext setzen).
    """

    def __init__(self, component, previous_active, main_window):
        """
        Args:
            component: Die zu aktivierende Component
            previous_active: Die zuvor aktive Component
            main_window: MainWindow für UI-Updates
        """
        super().__init__(f"Activate '{component.name}'")
        self.component = component
        self.previous_active = previous_active
        self.main_window = main_window

    def redo(self):
        """Component aktivieren."""
        # Alte deaktivieren
        if self.previous_active:
            self.previous_active.is_active = False

        # Neue aktivieren
        self.component.is_active = True
        self.main_window.document._active_component = self.component

        logger.info(f"[ASSEMBLY] Component aktiviert: {self.component.name}")

        # UI aktualisieren
        self.main_window.browser.refresh()
        self.main_window._update_viewport_all_impl()

    def undo(self):
        """Zur vorherigen Component zurückkehren."""
        # Aktuelle deaktivieren
        self.component.is_active = False

        # Vorherige aktivieren
        if self.previous_active:
            self.previous_active.is_active = True
            self.main_window.document._active_component = self.previous_active
            logger.info(f"[ASSEMBLY] Component aktiviert (Undo): {self.previous_active.name}")
        else:
            # Fallback: Root-Component
            root = self.main_window.document.root_component
            root.is_active = True
            self.main_window.document._active_component = root
            logger.info(f"[ASSEMBLY] Root-Component aktiviert (Undo)")

        # UI aktualisieren
        self.main_window.browser.refresh()
        self.main_window._update_viewport_all_impl()
