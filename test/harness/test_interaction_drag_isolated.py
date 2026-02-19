"""
W14 Paket A: Isolierte Drag-Tests (Subprozess-Ausfuehrung)
==========================================================

Diese Datei enthaelt die isolierten Drag-Regressionen, die aus
`test_interaction_consistency.py` in Child-Prozessen gestartet werden.

W14 Strategie:
- Keine xfail-Marker mehr
- Harte PASS/FAIL Assertions
- Stable direct-edit API drags statt QTest press/move/release
"""

# CRITICAL: QT_OPENGL muss VOR jedem Qt/PyVista Import gesetzt werden
import os
os.environ["QT_OPENGL"] = "software"

import pytest
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from gui.main_window import MainWindow

# Importiere Harness aus dem Haupt-File
sys.path.insert(0, str(Path(__file__).parent))
from test_interaction_consistency import SketchInteractionTestHarness


class TestDragIsolated:
    """Isolierte Drag-Tests fuer subprocess-safe Ausfuehrung."""

    @pytest.fixture(scope="session")
    def qt_app_session(self):
        """Session-weite QApplication Instanz."""
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        yield app
        if app:
            app.quit()

    @pytest.fixture
    def sketch_harness(self, qt_app_session):
        """Sketch harness mit deterministischem Cleanup."""
        import gc

        window = None
        harness = None
        try:
            window = MainWindow()
            harness = SketchInteractionTestHarness(window)
            yield harness
        finally:
            if harness is not None and hasattr(harness, "window"):
                try:
                    if hasattr(harness.window, "viewport_3d") and harness.window.viewport_3d:
                        if hasattr(harness.window.viewport_3d, "plotter"):
                            try:
                                harness.window.viewport_3d.plotter.close()
                            except Exception:
                                pass
                    harness.window.close()
                    harness.window.deleteLater()
                except Exception:
                    pass
            try:
                from gui.viewport.render_queue import RenderQueue
                RenderQueue.flush()
            except Exception:
                pass
            gc.collect()

    def test_circle_move_resize_isolated(self, sketch_harness):
        """Circle center-drag (move) und radius-drag (resize)."""
        editor = sketch_harness.editor
        sketch = editor.sketch

        circle = sketch.add_circle(0, 0, 10.0)
        editor.request_update()
        QApplication.processEvents()
        QTest.qWait(100)

        sketch_harness.direct_edit_drag(
            entity=circle,
            start_world=(0.0, 0.0),
            end_world=(20.0, 0.0),
            expected_mode="center",
        )
        assert abs(circle.center.x - 20.0) < 1.0
        assert abs(circle.radius - 10.0) < 0.1

        sketch_harness.direct_edit_drag(
            entity=circle,
            start_world=(30.0, 0.0),
            end_world=(35.0, 0.0),
            expected_mode="radius",
        )
        assert abs(circle.radius - 15.0) < 1.0
        assert abs(circle.center.x - 20.0) < 0.1

    def test_rectangle_edge_drag_isolated(self, sketch_harness):
        """Rectangle edge-drag (resize)."""
        editor = sketch_harness.editor
        sketch = editor.sketch

        sketch.add_rectangle(-10, -5, 20, 10)
        editor.request_update()
        QApplication.processEvents()
        QTest.qWait(100)

        right_line = None
        for line in sketch.lines:
            if abs(line.start.x - 10) < 0.1 and abs(line.end.x - 10) < 0.1:
                right_line = line
                break

        assert right_line is not None, "Failed to setup rectangle"

        sketch_harness.direct_edit_drag(
            entity=right_line,
            start_world=(10.0, 0.0),
            end_world=(15.0, 0.0),
            expected_mode="line_edge",
        )
        assert abs(right_line.start.x - 15.0) < 1.0
        assert abs(right_line.end.x - 15.0) < 1.0

    def test_line_drag_consistency_isolated(self, sketch_harness):
        """Free line drag (move)."""
        editor = sketch_harness.editor
        sketch = editor.sketch

        line = sketch.add_line(-10, 10, 10, 10)
        editor.request_update()
        QApplication.processEvents()
        QTest.qWait(100)

        # Start at (-5, 10) to avoid hitting the midpoint handle at (0, 10)
        sketch_harness.direct_edit_drag(
            entity=line,
            start_world=(-5.0, 10.0),
            end_world=(-5.0, 20.0),
            expected_mode="line_move",
        )
        assert abs(line.start.y - 20.0) < 1.0
        assert abs(line.end.y - 20.0) < 1.0


def pytest_configure(config):
    """Pytest-Konfiguration fuer isolierte Drag-Tests."""
    config.addinivalue_line(
        "markers",
        "isolated_drag: Markiert Tests, die isoliert im Subprozess laufen"
    )
