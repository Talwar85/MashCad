"""
W26 signal integration tests.

These tests intentionally avoid global import monkeypatching so they stay
compatible with the real runtime modules.
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def editor(qt_app):
    from gui.sketch_editor import SketchEditor

    instance = SketchEditor(parent=None)
    yield instance
    try:
        instance.close()
        instance.deleteLater()
        QApplication.processEvents()
    except Exception:
        pass


def test_projection_signals_exist_on_class():
    from gui.sketch_editor import SketchEditor

    assert hasattr(SketchEditor, "projection_preview_requested")
    assert hasattr(SketchEditor, "projection_preview_cleared")


def test_cancel_tool_clears_projection_preview(editor):
    editor._last_projection_edge = (0.0, 0.0, 10.0, 10.0, 0.0, 0.0)
    cleared = []
    editor.projection_preview_cleared.connect(lambda: cleared.append(True))

    editor._cancel_tool()

    assert editor._last_projection_edge is None
    assert len(cleared) == 1


def test_set_tool_clears_projection_preview_when_leaving_project(editor):
    from gui.sketch_tools import SketchTool

    editor.current_tool = SketchTool.PROJECT
    editor._last_projection_edge = (0.0, 0.0, 10.0, 10.0, 0.0, 0.0)
    cleared = []
    editor.projection_preview_cleared.connect(lambda: cleared.append(True))

    editor.set_tool(SketchTool.LINE)

    assert editor.current_tool == SketchTool.LINE
    assert editor._last_projection_edge is None
    assert len(cleared) >= 1


def test_mainwindow_projection_adapter_converts_edge_tuple():
    from gui.main_window import MainWindow

    viewport = MagicMock()
    host = SimpleNamespace(viewport_3d=viewport)

    edge_tuple = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    MainWindow._on_projection_preview_requested(host, edge_tuple, "edge")

    viewport.show_projection_preview.assert_called_once_with(
        [((1.0, 2.0, 0), (3.0, 4.0, 0))],
        "edge",
    )


def test_mainwindow_projection_adapter_ignores_invalid_tuple():
    from gui.main_window import MainWindow

    viewport = MagicMock()
    host = SimpleNamespace(viewport_3d=viewport)

    MainWindow._on_projection_preview_requested(host, None, "edge")
    MainWindow._on_projection_preview_requested(host, (1.0, 2.0, 3.0), "edge")

    viewport.show_projection_preview.assert_not_called()


def test_mainwindow_projection_clear_calls_viewport():
    from gui.main_window import MainWindow

    viewport = MagicMock()
    host = SimpleNamespace(viewport_3d=viewport)

    MainWindow._on_projection_preview_cleared(host)

    viewport.clear_projection_preview.assert_called_once()
