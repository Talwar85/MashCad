
import pytest
import sys
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from gui.main_window import MainWindow

# Global app instance to prevent segfaults on multiple test runs
app = QApplication.instance() or QApplication(sys.argv)

@pytest.fixture
def main_window():
    """Fixture providing a MainWindow instance."""
    window = MainWindow()
    # We need to show it so it has a window handle and focus context
    window.show()
    yield window
    window.close()

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
        # Focus might be lost if we just send to main_window, so send to panel or app focus
        # But Abort logic is in MainWindow.eventFilter or keyPressEvent.
        # MainWindow installs event filter on app or itself.
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
        # We need a visible input. Transform panel is good.
        main_window.transform_panel.show()
        input_field = main_window.transform_panel.x_input
        input_field.setFocus()
        QTest.qWait(50)
        QApplication.processEvents()

        # In headless/CI OpenGL setups focus assignment can fail nondeterministically.
        if input_field.hasFocus() is False:
            pytest.xfail("Headless focus acquisition is unreliable in this environment")

        # 2. Press Escape
        QTest.keyClick(input_field, Qt.Key_Escape)

        # 3. Verify Focus Lost
        assert input_field.hasFocus() is False
        # Panel should still be visible (Priority 2 is Clear Focus > Close Panel)
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
        
        # Mocking selection state manually
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
        main_window.setFocus() # Ensure focus is on main window so event filter catches it

        # 2. Press Escape ONCE
        QTest.keyClick(main_window, Qt.Key_Escape)

        # 3. Assertion: Panel closed (Priority 2), Selection REMAINS (Priority 4 not reached)
        assert main_window._hole_mode is False
        assert len(viewport.selected_faces) == 1 # Still selected!

        # 4. Press Escape AGAIN
        QTest.keyClick(main_window, Qt.Key_Escape)

        # 5. Assertion: Selection now cleared
        assert len(viewport.selected_faces) == 0
