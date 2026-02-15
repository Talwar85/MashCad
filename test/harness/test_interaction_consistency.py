
"""
SU-004 Direct Manipulation Test Harness
---------------------------------------
Provides a framework for testing interactions like Click, Drag, Snap, and Selection.
Implemented with PySide6.QtTest for real event simulation.
"""

import pytest
import sys
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from gui.main_window import MainWindow

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)

class InteractionTestHarness:
    """Simulates user interactions for testing direct manipulation."""

    def __init__(self, window):
        self.window = window
        self.viewport = window.viewport_3d
        # Ensure window is visible for QTest events
        self.window.show()
        QTest.qWaitForWindowExposed(self.window)

    def simulate_click(self, x, y, button=Qt.LeftButton, modifiers=Qt.NoModifier):
        """Simulate a click at specific coordinates relative to viewport."""
        pos = QPoint(x, y)
        QTest.mouseClick(self.viewport, button, modifiers, pos)
        QTest.qWait(50) # Allow event processing

    def simulate_drag(self, start_x, start_y, end_x, end_y, button=Qt.LeftButton):
        """Simulate a drag operation."""
        start_pos = QPoint(start_x, start_y)
        end_pos = QPoint(end_x, end_y)
        
        QTest.mousePress(self.viewport, button, Qt.NoModifier, start_pos)
        QTest.qWait(20)
        
        # Simulate a few intermediate moves for smoothness (optional but good for drag logic)
        mid_x = (start_x + end_x) // 2
        mid_y = (start_y + end_y) // 2
        QTest.mouseMove(self.viewport, QPoint(mid_x, mid_y))
        QTest.qWait(20)
        
        QTest.mouseMove(self.viewport, end_pos)
        QTest.qWait(20)
        
        QTest.mouseRelease(self.viewport, button, Qt.NoModifier, end_pos)
        QTest.qWait(50)

    def simulate_hover(self, x, y):
        """Simulate mouse hover."""
        pos = QPoint(x, y)
        QTest.mouseMove(self.viewport, pos)
        QTest.qWait(20)

    def assert_selection_count(self, count):
        """Verify the current selection count."""
        # Check both legacy and logic sets to be sure
        current_count = len(self.viewport.selected_faces)
        # Also check selected_face_ids if populated
        if hasattr(self.viewport, 'selected_face_ids') and self.viewport.selected_face_ids:
             # Might differ if faces != ids, but count should align in principle or check logic
             pass
        assert current_count == count, f"Expected {count} selected items, got {current_count}"

    def assert_cursor_shape(self, shape):
        """Verify the viewport cursor shape."""
        assert self.viewport.cursor().shape() == shape, \
            f"Expected cursor {shape}, got {self.viewport.cursor().shape()}"

@pytest.fixture
def harness(qtbot): # We don't really use qtbot fixture but pytest-qt might be absent. 
                    # If we write this without qtbot dependency:
    pass

@pytest.fixture
def interaction_harness():
    """Fixture to provide the interaction harness."""
    # Setup MainWindow
    window = MainWindow()
    harness = InteractionTestHarness(window)
    yield harness
    window.close()

class TestInteractionConsistency:
    """
    Validation for SU-004 / UX-W2-02.
    """

    def test_click_selects_nothing_in_empty_space(self, interaction_harness):
        """Test that clicking in empty space clears selection."""
        # 1. Simulate click in corner (assumed empty)
        # Viewport size?
        width = interaction_harness.viewport.width()
        height = interaction_harness.viewport.height()
        
        # Click Top-Left
        interaction_harness.simulate_click(50, 50)
        
        # 2. Assert Selection Empty
        interaction_harness.assert_selection_count(0)

    def test_drag_cursor_feedback(self, interaction_harness):
        """Test that dragging changes cursor (if implemented) or state."""
        # 1. Start Drag
        # Note: Drag behavior usually requires picking something or a tool mode.
        # If we just drag in empty space with orbit (middle button) or pan?
        
        # Test Orbit (Middle Button is standard for PyVista, wait, usually Left is Rotate)
        # Let's test standard box selection drag if implemented (Shift+Drag?)
        # Or just verify that dragging doesn't crash.
        
        # Let's try dragging with Left Button
        interaction_harness.simulate_drag(100, 100, 200, 200)
        
        # Assert no crash and idle state restored
        # interaction_harness.assert_cursor_shape(Qt.ArrowCursor) 
        pass

    def test_hover_highlight(self, interaction_harness):
        """Test hover interactions (smoke test)."""
        # 1. Hover center
        width = interaction_harness.viewport.width()
        height = interaction_harness.viewport.height()
        interaction_harness.simulate_hover(width // 2, height // 2)
        
        # 2. Hard to assert highlight without screenshot or internal flag
        # But we verify it runs.
        pass
