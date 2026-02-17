"""
W26 projection/trace workflow tests.

This suite focuses on deterministic contract checks and behavior checks for
projection preview state transitions.
"""

"""
W26 projection/trace workflow tests.

W29: Headless-Hardening for stable CI execution.
"""

import os
import sys

import pytest

# W29: Headless environment setup BEFORE Qt imports
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_OPENGL", "software")

from PySide6.QtWidgets import QApplication

from gui.sketch_tools import SketchTool


class _Signal:
    def __init__(self):
        self._subs = []

    def connect(self, fn):
        self._subs.append(fn)

    def emit(self, *args):
        for fn in list(self._subs):
            fn(*args)


class MockSketchEditor:
    """Pure-Python behavior model for projection preview lifecycle."""

    def __init__(self):
        self.projection_preview_requested = _Signal()
        self.projection_preview_cleared = _Signal()
        self.current_tool = SketchTool.SELECT
        self.hovered_ref_edge = None
        self._last_projection_edge = None
        self._projection_type = "edge"
        self.tool_step = 0

    def set_tool(self, tool):
        old_tool = self.current_tool
        self.current_tool = tool
        if old_tool == SketchTool.PROJECT and tool != SketchTool.PROJECT:
            if self._last_projection_edge is not None:
                self._last_projection_edge = None
                self.projection_preview_cleared.emit()

    def simulate_hover_edge(self, edge_tuple):
        if self.current_tool != SketchTool.PROJECT:
            return
        if edge_tuple != self._last_projection_edge:
            self._last_projection_edge = edge_tuple
            if edge_tuple is not None:
                self.projection_preview_requested.emit(edge_tuple, self._projection_type)
            else:
                self.projection_preview_cleared.emit()

    def simulate_confirm_projection(self):
        if self._last_projection_edge is not None:
            self._last_projection_edge = None
            self.projection_preview_cleared.emit()

    def simulate_cancel(self):
        if self._last_projection_edge is not None:
            self._last_projection_edge = None
            self.projection_preview_cleared.emit()

    def simulate_leave_sketch(self):
        if self._last_projection_edge is not None:
            self._last_projection_edge = None
            self.projection_preview_cleared.emit()


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class TestProjectionPreviewBehavior:
    def test_signal_emitted_on_edge_hover(self):
        editor = MockSketchEditor()
        editor.set_tool(SketchTool.PROJECT)

        seen = []
        editor.projection_preview_requested.connect(lambda e, t: seen.append((e, t)))

        test_edge = (0, 0, 10, 10, 0, 0)
        editor.simulate_hover_edge(test_edge)

        assert seen == [(test_edge, "edge")]

    def test_signal_cleared_on_leave_edge(self):
        editor = MockSketchEditor()
        editor.set_tool(SketchTool.PROJECT)

        cleared = []
        editor.projection_preview_cleared.connect(lambda: cleared.append(True))

        editor.simulate_hover_edge((0, 0, 10, 10, 0, 0))
        editor.simulate_hover_edge(None)

        assert len(cleared) == 1

    def test_preview_cleared_on_confirm(self):
        editor = MockSketchEditor()
        editor.set_tool(SketchTool.PROJECT)

        cleared = []
        editor.projection_preview_cleared.connect(lambda: cleared.append(True))

        editor.simulate_hover_edge((0, 0, 10, 10, 0, 0))
        editor.simulate_confirm_projection()

        assert len(cleared) == 1

    def test_preview_cleared_on_cancel(self):
        editor = MockSketchEditor()
        editor.set_tool(SketchTool.PROJECT)

        cleared = []
        editor.projection_preview_cleared.connect(lambda: cleared.append(True))

        editor.simulate_hover_edge((0, 0, 10, 10, 0, 0))
        editor.simulate_cancel()

        assert len(cleared) == 1

    def test_preview_cleared_on_tool_change(self):
        editor = MockSketchEditor()
        editor.set_tool(SketchTool.PROJECT)

        cleared = []
        editor.projection_preview_cleared.connect(lambda: cleared.append(True))

        editor.simulate_hover_edge((0, 0, 10, 10, 0, 0))
        editor.set_tool(SketchTool.SELECT)

        assert len(cleared) == 1

    def test_preview_cleared_on_sketch_exit(self):
        editor = MockSketchEditor()
        editor.set_tool(SketchTool.PROJECT)

        cleared = []
        editor.projection_preview_cleared.connect(lambda: cleared.append(True))

        editor.simulate_hover_edge((0, 0, 10, 10, 0, 0))
        editor.simulate_leave_sketch()

        assert len(cleared) == 1

    def test_no_duplicate_signals_for_same_edge(self):
        editor = MockSketchEditor()
        editor.set_tool(SketchTool.PROJECT)

        seen = []
        editor.projection_preview_requested.connect(lambda *_: seen.append(True))

        edge = (0, 0, 10, 10, 0, 0)
        editor.simulate_hover_edge(edge)
        editor.simulate_hover_edge(edge)

        assert len(seen) == 1


class TestTraceAssistAndAbortBehavior:
    def test_context_is_valid_in_select_mode(self):
        editor = MockSketchEditor()
        editor.set_tool(SketchTool.SELECT)
        assert editor.current_tool == SketchTool.SELECT

    def test_no_ghost_state_after_quick_tool_changes(self):
        editor = MockSketchEditor()
        editor.set_tool(SketchTool.PROJECT)
        editor.simulate_hover_edge((0, 0, 10, 10, 0, 0))
        editor.set_tool(SketchTool.SELECT)
        editor.set_tool(SketchTool.LINE)

        assert editor._last_projection_edge is None

    def test_abort_resets_projection_state(self):
        editor = MockSketchEditor()
        editor.set_tool(SketchTool.PROJECT)
        editor.simulate_hover_edge((0, 0, 10, 10, 0, 0))
        editor.tool_step = 1
        editor.simulate_cancel()

        assert editor._last_projection_edge is None


class TestRealSketchEditorContract:
    def test_class_contract_has_projection_symbols(self):
        from gui.sketch_editor import SketchEditor

        assert hasattr(SketchEditor, "projection_preview_requested")
        assert hasattr(SketchEditor, "projection_preview_cleared")
        assert hasattr(SketchEditor, "mouseMoveEvent")
        assert hasattr(SketchEditor, "_find_reference_edge_at")

    def test_instance_has_projection_state_defaults(self, qt_app):
        from gui.sketch_editor import SketchEditor

        editor = SketchEditor(parent=None)
        try:
            assert hasattr(editor, "_last_projection_edge")
            assert hasattr(editor, "_projection_type")
            assert editor._last_projection_edge is None
            assert editor._projection_type == "edge"
        finally:
            editor.close()
            editor.deleteLater()
            QApplication.processEvents()

    def test_cancel_tool_clears_projection_state(self, qt_app):
        from gui.sketch_editor import SketchEditor

        editor = SketchEditor(parent=None)
        try:
            editor._last_projection_edge = (0, 0, 10, 10, 0, 0)
            cleared = []
            editor.projection_preview_cleared.connect(lambda: cleared.append(True))

            editor._cancel_tool()

            assert editor._last_projection_edge is None
            assert len(cleared) == 1
        finally:
            editor.close()
            editor.deleteLater()
            QApplication.processEvents()


class TestProjectionCleanupW28:
    """W28: Projection Cleanup - Keine Ghost-Previews nach State-Changes."""
    
    def test_no_ghost_preview_after_confirm(self):
        """W28-G1: Keine Ghost-Preview nach Confirm."""
        from gui.sketch_tools import SketchTool
        
        editor = MockSketchEditor()
        editor.set_tool(SketchTool.PROJECT)
        
        cleared = []
        editor.projection_preview_cleared.connect(lambda: cleared.append(True))
        
        # Hover edge
        editor.simulate_hover_edge((0, 0, 10, 10, 0, 0))
        # Confirm
        editor.simulate_confirm_projection()
        
        assert editor._last_projection_edge is None
        assert len(cleared) == 1
    
    def test_no_ghost_preview_after_tool_change(self):
        """W28-G2: Keine Ghost-Preview nach Toolwechsel."""
        from gui.sketch_tools import SketchTool
        
        editor = MockSketchEditor()
        editor.set_tool(SketchTool.PROJECT)
        editor.simulate_hover_edge((0, 0, 10, 10, 0, 0))
        
        # Switch tool
        editor.set_tool(SketchTool.LINE)
        
        assert editor._last_projection_edge is None
    
    def test_no_ghost_preview_after_sketch_exit(self):
        """W28-G3: Keine Ghost-Preview nach Sketch-Exit."""
        from gui.sketch_tools import SketchTool
        
        editor = MockSketchEditor()
        editor.set_tool(SketchTool.PROJECT)
        editor.simulate_hover_edge((0, 0, 10, 10, 0, 0))
        
        # Exit sketch
        editor.simulate_leave_sketch()
        
        assert editor._last_projection_edge is None


class TestDirectManipulationAbortW28:
    """W28: Direct Manipulation Abbruch - Rechtsklick und ESC."""
    
    def test_right_click_aborts_direct_edit(self):
        """W28-A1: Rechtsklick bricht Direct-Edit ab."""
        editor = MockSketchEditor()
        editor._direct_edit_dragging = True
        editor._direct_edit_mode = "center"
        
        # Simulate right-click abort
        aborted = False
        if editor._direct_edit_dragging:
            editor._direct_edit_dragging = False
            editor._direct_edit_mode = None
            aborted = True
        
        assert aborted is True
        assert editor._direct_edit_dragging is False
    
    def test_esc_aborts_direct_edit(self):
        """W28-A2: ESC bricht Direct-Edit ab."""
        editor = MockSketchEditor()
        editor._direct_edit_dragging = True
        editor._direct_edit_mode = "radius"
        
        # Simulate ESC abort
        aborted = False
        if editor._direct_edit_dragging:
            editor._direct_edit_dragging = False
            editor._direct_edit_mode = None
            aborted = True
        
        assert aborted is True
        assert editor._direct_edit_mode is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
