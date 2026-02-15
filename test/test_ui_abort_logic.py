"""
UI-Abort Logic Tests (UX-W2-01: SU-006)
=========================================

Validiert die Abort State Machine Priority Stack:
Drag > Dialog > Tool > Selection > Idle

Update W5 (Paket A: UI-Gate Hardening):
- Zentrale UI-Test-Infrastruktur in test/ui/conftest.py
- QT_OPENGL=software wird VOR Qt-Import gesetzt
- Deterministische Cleanup-Strategie

Author: GLM 4.7 (UX/WORKFLOW + QA Integration Cell)
Date: 2026-02-16
Branch: feature/v1-ux-aiB
"""

# CRITICAL: QT_OPENGL muss VOR jedem Qt/PyVista Import gesetzt werden
import os
os.environ["QT_OPENGL"] = "software"

import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from gui.main_window import MainWindow

# Session-weite QApplication (verhindert Segfaults bei mehreren Läufen)
@pytest.fixture(scope="session")
def qt_app():
    """Session-weite QApplication Instanz."""
    app = QApplication.instance()
    if app is None:
        import sys
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def main_window(qt_app):
    """
    MainWindow Fixture mit deterministischem Cleanup (Paket A).

    Verwendet Cleanup-Strategie aus UI-Gate Hardening.
    """
    import gc

    window = None
    try:
        window = MainWindow()
        window.show()
        QTest.qWaitForWindowExposed(window)
        yield window
    finally:
        # Deterministischer Cleanup (Paket A)
        if window is not None:
            try:
                if hasattr(window, 'viewport_3d') and window.viewport_3d:
                    if hasattr(window.viewport_3d, 'plotter'):
                        try:
                            window.viewport_3d.plotter.close()
                        except Exception:
                            pass
                window.close()
                window.deleteLater()
            except Exception:
                pass

        # RenderQueue flush falls vorhanden
        try:
            from gui.viewport.render_queue import RenderQueue
            RenderQueue.flush()
        except Exception:
            pass

        # Python Garbage Collection
        gc.collect()

class TestAbortLogic:
    """
    UX-W2-01: SU-006 Abort State Machine Regression Tests.
    Validates the priority stack: Drag > Dialog > Tool > Selection > Idle.
    Uses QTest instead of pytest-qt for robust, dependency-free testing.
    """

    def test_priority_1_drag_cancellation(self, main_window):
        """Test that Escape cancels an active drag operation (Priority 1)."""
        # 1. Simulate Drag State
        viewport = main_window.viewport_3d
        viewport.is_dragging = True
        
        # Verify state before
        assert viewport.is_dragging is True

        # 2. Press Escape
        QTest.keyClick(main_window, Qt.Key_Escape)

        # 3. Verify Drag is cancelled
        assert viewport.is_dragging is False

    def test_priority_2_modal_dialog_cancellation(self, main_window):
        """Test that Escape closes active panels/dialogs (Priority 2)."""
        # 1. Open Hole Panel
        main_window._hole_mode = True
        main_window.hole_panel.show()
        QTest.qWaitForWindowExposed(main_window.hole_panel)

        # 2. Press Escape
        QTest.keyClick(main_window, Qt.Key_Escape)

        # 3. Verify Panel Closed and Mode Reset
        assert main_window.hole_panel.isVisible() is False
        assert main_window._hole_mode is False

        # Repeat for Revolve
        main_window.viewport_3d.revolve_mode = True
        main_window.revolve_panel.show()
        QTest.keyClick(main_window, Qt.Key_Escape)
        assert main_window.revolve_panel.isVisible() is False
        assert main_window.viewport_3d.revolve_mode is False

    def test_priority_2_input_focus_clear(self, main_window):
        """Test that Escape clears focus from input fields (Priority 2b)."""
        # 1. Focus an input field
        main_window.transform_panel.show()
        input_field = main_window.transform_panel.x_input
        input_field.setFocus()
        QTest.qWait(50)
        QApplication.processEvents()

        if input_field.hasFocus() is False:
            pytest.xfail("Headless focus acquisition is unreliable in this environment")

        # 2. Press Escape
        QTest.keyClick(input_field, Qt.Key_Escape)

        # 3. Verify Focus Lost
        assert input_field.hasFocus() is False
        # Panel should still be visible
        assert main_window.transform_panel.isVisible() is True

    def test_priority_3_sketch_tool_cancellation(self, main_window):
        """Test that Escape cancels the active sketch tool (Priority 3)."""
        # 1. Enter Sketch Mode
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        editor.setFocus()
        
        # 2. Select Line Tool
        from gui.sketch_editor import SketchTool
        editor.set_tool(SketchTool.LINE)
        assert editor.current_tool == SketchTool.LINE

        # 3. Press Escape
        QTest.keyClick(editor, Qt.Key_Escape)

        # 4. Verify Tool is now SELECT
        assert editor.current_tool == SketchTool.SELECT

    def test_priority_4_selection_clearing(self, main_window):
        """Test that Escape clears current selection (Priority 4)."""
        # 1. Setup Selection
        main_window._set_mode("3d")
        viewport = main_window.viewport_3d
        
        viewport.selected_faces = ["face_1"]
        viewport.selected_edges = []

        # 2. Press Escape
        QTest.keyClick(main_window, Qt.Key_Escape)

        # 3. Verify Selection Cleared
        assert len(viewport.selected_faces) == 0

    def test_priority_stack_order(self, main_window):
        """
        Validates that higher priority states block lower priority cancellations.
        Scenario: Panel Open AND Selection Active.
        """
        # 1. Setup Conflict
        main_window._set_mode("3d")
        viewport = main_window.viewport_3d
        viewport.selected_faces = ["face_1"]

        # Setup Panel Open (Medium Priority)
        main_window._hole_mode = True
        main_window.hole_panel.show()
        main_window.setFocus()
        QTest.qWait(50)

        # 2. Press Escape ONCE
        QTest.keyClick(main_window, Qt.Key_Escape)

        # 3. Assertion: Panel closed (Priority 2), Selection REMAINS (Priority 4 not reached)
        assert main_window._hole_mode is False
        assert len(viewport.selected_faces) == 1

        # 4. Press Escape AGAIN
        QTest.keyClick(main_window, Qt.Key_Escape)

        # 5. Assertion: Selection now cleared
        assert len(viewport.selected_faces) == 0

    def test_right_click_cancels_drag(self, main_window):
        """Test that Right-Click (Press) cancels an active drag (Priority 1)."""
        viewport = main_window.viewport_3d
        viewport.is_dragging = True
        
        # Simulate Right Button Press on Viewport
        center = viewport.rect().center()
        QTest.mousePress(viewport, Qt.RightButton, Qt.NoModifier, center)
        
        assert viewport.is_dragging is False

    def test_right_click_background_clears_selection(self, main_window, monkeypatch):
        """Test that Right-Click (Click) on empty space clears selection (Priority 4)."""
        viewport = main_window.viewport_3d
        viewport.selected_faces = ["face_1"]
        
        # Mock pick to return -1 (Background)
        monkeypatch.setattr(viewport, 'pick', lambda x, y, selection_filter=None: -1)
        
        # Simulate Right Click (Press + Release short duration)
        center = viewport.rect().center()
        QTest.mousePress(viewport, Qt.RightButton, Qt.NoModifier, center)
        QTest.qWait(50) # Short wait < 300ms
        QTest.mouseRelease(viewport, Qt.RightButton, Qt.NoModifier, center)
        
        assert len(viewport.selected_faces) == 0

    def test_combined_drag_and_panel(self, main_window):
        """
        Test combined state: Dragging while Panel is open.
        Escape should cancel Drag first, then Panel.
        """
        viewport = main_window.viewport_3d
        viewport.is_dragging = True
        
        main_window._hole_mode = True
        main_window.hole_panel.show()
        main_window.setFocus()
        QTest.qWait(50)
        
        # 1. Escape -> Cancel Drag
        QTest.keyClick(main_window, Qt.Key_Escape)
        assert viewport.is_dragging is False
        assert main_window._hole_mode is True
        assert main_window.hole_panel.isVisible() is True
        
        # 2. Escape -> Close Panel
        QTest.keyClick(main_window, Qt.Key_Escape)
        assert main_window._hole_mode is False
        assert main_window.hole_panel.isVisible() is False

    def test_repeated_escape_to_idle(self, main_window):
        """
        Test repeated escape sequence from deep state to idle.
        Tool > Selection > Idle
        """
        # Setup: Extrude Mode Active AND Selection existing
        main_window._set_mode("3d")
        viewport = main_window.viewport_3d
        viewport.selected_faces = ["face_1"]
        
        # Activate Extrude Panel (Priority 2)
        viewport.extrude_mode = True
        main_window.setFocus()
        QTest.qWait(50)
        
        # 1. Escape -> Cancel Extrude
        QTest.keyClick(main_window, Qt.Key_Escape)
        assert viewport.extrude_mode is False
        assert len(viewport.selected_faces) == 1
        
        # 2. Escape -> Clear Selection
        QTest.keyClick(main_window, Qt.Key_Escape)
        assert len(viewport.selected_faces) == 0
        
        # 3. Escape -> Idle (No Op, No Crash)
        QTest.keyClick(main_window, Qt.Key_Escape)
        assert True # Survived
