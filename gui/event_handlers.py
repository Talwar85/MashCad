"""
MashCAD Event Handlers Module
=============================

Extracted from main_window.py (AR-004: Phase 1 Split).

This module contains event handling methods as a mixin class.
Maintains backward compatibility by being imported into MainWindow.

Usage:
    class MainWindow(EventHandlersMixin, QMainWindow):
        pass
"""

from typing import TYPE_CHECKING
from loguru import logger

from PySide6.QtCore import Qt, QEvent, QObject
from PySide6.QtWidgets import QApplication

if TYPE_CHECKING:
    from gui.main_window import MainWindow


class EventHandlersMixin:
    """
    Mixin class containing event handlers for MainWindow.
    
    This class provides:
    - Global keyboard event handling (eventFilter)
    - Mode-specific keyboard shortcuts
    - Escape key abort logic
    - Resize event handling
    
    All methods assume they are called within a MainWindow context
    and access MainWindow attributes via `self`.
    """
    
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """
        Global event filter for MainWindow.
        
        Handles:
        - Viewport resize
        - 3D-Peek Space key release
        - Escape key abort logic (priority stack)
        - Mode-specific shortcuts
        - Transform shortcuts
        
        Args:
            obj: The object that generated the event
            event: The event to filter
            
        Returns:
            True if event was handled, False to pass to next filter
        """
        # Merged Logic from shadowed eventFilter (global shortcuts, resize, peek)
        if obj is self.viewport_3d and event.type() == QEvent.Resize:
            self._position_transform_toolbar()

        # Backup for 3D-Peek Space-Release
        if getattr(self, '_peek_3d_active', False):
            if event.type() == QEvent.KeyRelease and event.key() == Qt.Key_Space:
                if not event.isAutoRepeat():
                    self._on_peek_3d(False)
                    return True

        if event.type() == QEvent.KeyPress:
            return self._handle_key_press(event)
        
        return False
    
    def _handle_key_press(self, event) -> bool:
        """
        Handle key press events with priority-based dispatch.
        
        Priority Stack:
        1. Escape - Abort operations (drag, modal, tool, selection)
        2. Mode-specific shortcuts
        3. Global shortcuts
        
        Args:
            event: QKeyEvent
            
        Returns:
            True if event was handled
        """
        # SU-006: Centralized Abort Logic (Priority Stack)
        if event.key() == Qt.Key_Escape:
            return self._handle_escape_key(event)
        
        # Block shortcuts when dialog is open or text field has focus
        focus_widget = QApplication.focusWidget()
        if self._should_block_shortcuts(focus_widget):
            return False
        
        k = event.key()
        
        # Sketch navigation shortcuts
        if self.mode == "sketch":
            if k == Qt.Key_Home:
                if hasattr(self, "sketch_editor") and self.sketch_editor:
                    self.sketch_editor._reset_view_to_origin()
                    return True
            if k == Qt.Key_0 and not (event.modifiers() & Qt.ControlModifier):
                if hasattr(self, "sketch_editor") and self.sketch_editor:
                    self.sketch_editor._reset_view_to_origin()
                    return True
        
        # Tab - Focus input fields
        if k == Qt.Key_Tab:
            return self._handle_tab_key(event)
        
        # Mode-specific shortcuts
        if self.viewport_3d.revolve_mode:
            handled = self._handle_revolve_shortcuts(k)
            if handled:
                return handled
        
        # E - Extrude
        if k == Qt.Key_E:
            if not self.viewport_3d.extrude_mode:
                self._extrude_dialog()
            return True
        
        # 3D Mode shortcuts
        if self.mode == "3d":
            handled = self._handle_3d_mode_shortcuts(k, event)
            if handled:
                return handled
        
        # Hole mode shortcuts
        if self._hole_mode:
            if k == Qt.Key_Tab:
                self.hole_panel.diameter_input.setFocus()
                self.hole_panel.diameter_input.selectAll()
                return True
        
        # Draft mode shortcuts
        if self._draft_mode:
            handled = self._handle_draft_shortcuts(k)
            if handled:
                return handled
        
        # Confirmation for Revolve / Extrude / Offset Plane / Hole / Draft
        if k in (Qt.Key_Return, Qt.Key_Enter):
            return self._handle_confirm_key()
        
        # Plane Selection Shortcuts
        if self.viewport_3d.plane_select_mode:
            handled = self._handle_plane_selection_shortcuts(k)
            if handled:
                return handled
        
        # 3D Mode Shortcuts (when not in extrude mode)
        if self.mode == "3d" and not self.viewport_3d.extrude_mode:
            handled = self._handle_3d_global_shortcuts(k)
            if handled:
                return handled
        
        return False
    
    def _handle_escape_key(self, event) -> bool:
        """
        Handle Escape key with priority-based abort logic.
        
        Priority:
        1. Drag operations (highest)
        2. Modal dialogs / panels / input focus
        3. Active tool (sketch)
        4. Selection clearing (lowest)
        
        Returns:
            True if event was handled
        """
        # 1. Drag Operations (Highest Priority)
        if self.viewport_3d.is_dragging or self.viewport_3d._offset_plane_dragging or self.viewport_3d._split_dragging:
            if hasattr(self.viewport_3d, 'cancel_drag'):
                self.viewport_3d.cancel_drag()
            elif hasattr(self.viewport_3d, 'handle_offset_plane_mouse_release'):
                self.viewport_3d.handle_offset_plane_mouse_release()
            return True
        
        # 2. Modal Dialogs / Panels / Input Focus
        focus_widget = QApplication.focusWidget()
        
        # If focus is on an input field, remove focus (don't close panel yet)
        from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox
        if isinstance(focus_widget, (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox)):
            focus_widget.clearFocus()
            return True
        
        # Close specific panels if they are open/active modes
        if self._hole_mode:
            self._on_hole_cancelled()
            return True
        if self._draft_mode:
            self._on_draft_cancelled()
            return True
        if self.viewport_3d.revolve_mode:
            self._on_revolve_cancelled()
            return True
        if self.viewport_3d.offset_plane_mode:
            self._on_offset_plane_cancelled()
            return True
        if self.viewport_3d.extrude_mode:
            self._on_extrude_cancelled()
            return True
        if self.viewport_3d.point_to_point_mode:
            self._cancel_point_to_point_move()
            return True
        
        # Close transforms
        if hasattr(self.transform_panel, 'isVisible') and self.transform_panel.isVisible():
            self._on_transform_panel_cancelled()
            return True
        
        # 3. Active Tool (Sketch) is handled by SketchEditor's own keyPressEvent if it has focus.
        if self.mode == "sketch":
            self.sketch_editor._handle_escape_logic()
            return True
        
        # 4. Selection (Lowest Priority)
        if self.mode == "3d":
            has_selection = False
            if hasattr(self.viewport_3d, 'selected_faces') and self.viewport_3d.selected_faces:
                has_selection = True
            if hasattr(self.viewport_3d, 'selected_edges') and self.viewport_3d.selected_edges:
                has_selection = True
            
            if has_selection:
                if hasattr(self.viewport_3d, 'clear_selection'):
                    self.viewport_3d.clear_selection()
                return True
        
        # 5. Idle - No Op
        return False
    
    def _should_block_shortcuts(self, focus_widget) -> bool:
        """Check if shortcuts should be blocked due to input focus."""
        from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox
        
        if isinstance(focus_widget, (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox)):
            # Allow standard keys (Backspace, Delete, etc.)
            return True
        if isinstance(focus_widget, QComboBox) and focus_widget.isEditable():
            return True
        
        active_modal = QApplication.activeModalWidget()
        if active_modal and active_modal is not self:
            return True
        
        return False
    
    def _handle_tab_key(self, event) -> bool:
        """Handle Tab key for focus navigation."""
        if self.mode == "sketch":
            self.sketch_editor.keyPressEvent(event)
            return True
        if self.viewport_3d.extrude_mode:
            self.extrude_panel.height_input.setFocus()
            self.extrude_panel.height_input.selectAll()
            return True
        return False
    
    def _handle_revolve_shortcuts(self, key) -> bool:
        """Handle revolve mode shortcuts."""
        if key == Qt.Key_X:
            self.revolve_panel.set_axis('X')
            return True
        if key == Qt.Key_Y:
            self.revolve_panel.set_axis('Y')
            return True
        if key == Qt.Key_Z:
            self.revolve_panel.set_axis('Z')
            return True
        if key == Qt.Key_F:
            self.revolve_panel._flip_direction()
            return True
        if key == Qt.Key_Tab:
            self.revolve_panel.angle_input.setFocus()
            self.revolve_panel.angle_input.selectAll()
            return True
        return False
    
    def _handle_draft_shortcuts(self, key) -> bool:
        """Handle draft mode shortcuts."""
        if key == Qt.Key_X:
            self.draft_panel._set_axis('X')
            return True
        if key == Qt.Key_Y:
            self.draft_panel._set_axis('Y')
            return True
        if key == Qt.Key_Z:
            self.draft_panel._set_axis('Z')
            return True
        if key == Qt.Key_Tab:
            self.draft_panel.angle_input.setFocus()
            self.draft_panel.angle_input.selectAll()
            return True
        return False
    
    def _handle_3d_mode_shortcuts(self, key, event) -> bool:
        """Handle 3D mode specific shortcuts."""
        # F - Flip direction in extrude mode
        if key == Qt.Key_F and self.viewport_3d.extrude_mode:
            self.extrude_panel._flip_direction()
            return True
        
        # Selection mode shortcuts
        if key == Qt.Key_U:
            self.viewport_3d.set_selection_mode("face")
            logger.success("Modus: Flächen")
            return True
        elif key == Qt.Key_I:
            self.viewport_3d.set_selection_mode("hole")
            logger.success("Modus: Löcher")
            return True
        elif key == Qt.Key_O:
            self.viewport_3d.set_selection_mode("sketch")
            logger.success("Modus: Skizze")
            return True
        
        return False
    
    def _handle_3d_global_shortcuts(self, key) -> bool:
        """Handle 3D mode global shortcuts."""
        if key == Qt.Key_E:
            self._extrude_dialog()
            return True
        if key == Qt.Key_N:
            self._new_sketch()
            return True
        
        # G/R/S/M - Transform Shortcuts (only when gizmo visible)
        if key == Qt.Key_G:
            if self.viewport_3d.handle_transform_key('g'):
                return True
        if key == Qt.Key_R:
            if self.viewport_3d.handle_transform_key('r'):
                return True
        if key == Qt.Key_M:
            if self.viewport_3d.handle_transform_key('m'):
                return True
        
        # H - Hide/Show selected bodies
        if key == Qt.Key_H:
            selected = self.browser.get_selected_bodies()
            if selected:
                for body in selected:
                    vis = self.browser.body_visibility.get(body.id, True)
                    self.browser.body_visibility[body.id] = not vis
                    self.browser.body_vis_changed.emit(body.id, not vis)
                self.browser.refresh()
                self.browser.visibility_changed.emit()
                return True
        
        # Delete - Delete selected body
        if key == Qt.Key_Delete:
            selected = self.browser.get_selected_bodies()
            if selected:
                for body in selected:
                    self.browser._del_body(body)
                return True
        
        return False
    
    def _handle_confirm_key(self) -> bool:
        """Handle Enter/Return key for confirmation."""
        if self._draft_mode:
            self._on_draft_confirmed()
            return True
        if self._hole_mode:
            self._on_hole_confirmed()
            return True
        if self.viewport_3d.revolve_mode:
            self._on_revolve_confirmed()
            return True
        if self.viewport_3d.offset_plane_mode:
            self._on_offset_plane_confirmed()
            return True
        if self.viewport_3d.extrude_mode:
            self._on_extrude_confirmed()
            return True
        return False
    
    def _handle_plane_selection_shortcuts(self, key) -> bool:
        """Handle plane selection mode shortcuts."""
        if key in [Qt.Key_1, Qt.Key_T]:
            self._on_plane_selected('xy')
            return True
        if key in [Qt.Key_2, Qt.Key_F]:
            self._on_plane_selected('xz')
            return True
        if key in [Qt.Key_3, Qt.Key_R]:
            self._on_plane_selected('yz')
            return True
        return False
    
    def resizeEvent(self, event):
        """Handle window resize events."""
        super().resizeEvent(event)
        
        # Position transform toolbar if needed
        if hasattr(self, '_position_transform_toolbar'):
            self._position_transform_toolbar()
    
    def _on_opt_change(self, option, value):
        """Handle option changes from tool panel."""
        pass  # Placeholder for subclass implementation


# =============================================================================
# Backward Compatibility Exports
# =============================================================================

__all__ = [
    'EventHandlersMixin',
]
