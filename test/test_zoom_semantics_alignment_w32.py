"""
W32: Zoom Semantics Alignment Tests
====================================
Validates that overlay HUD and status bar badge show identical zoom values
from the same format_zoom_label source.

Author: AI-SMALL-6
Date: 2026-02-18
Branch: feature/v1-ux-aiB
"""

import os
os.environ["QT_OPENGL"] = "software"

import pytest
from gui.sketch_editor import format_zoom_label, SketchEditor
from gui.widgets.status_bar import MashCadStatusBar


@pytest.fixture(scope="session")
def qt_app():
    app = pytest.importorskip("PySide6.QtWidgets").QApplication.instance()
    if app is None:
        import sys
        app = pytest.importorskip("PySide6.QtWidgets").QApplication(sys.argv)
    return app


@pytest.fixture
def status_bar(qt_app):
    return MashCadStatusBar()


@pytest.fixture
def sketch_editor(qt_app):
    from sketcher import Sketch
    editor = SketchEditor()
    editor.sketch = Sketch("test")
    return editor


# ===========================================================================
# A) format_zoom_label – Single Source of Truth
# ===========================================================================

class TestFormatZoomLabel:
    """format_zoom_label must produce consistent Nx output."""

    def test_integer_scale(self):
        assert format_zoom_label(5.0) == "5x"

    def test_integer_scale_10(self):
        assert format_zoom_label(10.0) == "10x"

    def test_integer_scale_1(self):
        assert format_zoom_label(1.0) == "1x"

    def test_fractional_scale(self):
        assert format_zoom_label(2.5) == "2.5x"

    def test_fractional_scale_high(self):
        assert format_zoom_label(8.7) == "8.7x"

    def test_small_fractional(self):
        assert format_zoom_label(0.5) == "0.5x"

    def test_large_scale(self):
        assert format_zoom_label(50.0) == "50x"


# ===========================================================================
# B) Overlay and Status Bar consistency
# ===========================================================================

class TestOverlayAndBadgeSync:
    """Status bar badge must show the same label as format_zoom_label for any view_scale."""

    def test_default_scale_sync(self, status_bar):
        status_bar.set_zoom(5.0)
        assert status_bar.zoom_badge.text() == format_zoom_label(5.0)

    def test_fractional_scale_sync(self, status_bar):
        status_bar.set_zoom(8.7)
        assert status_bar.zoom_badge.text() == format_zoom_label(8.7)

    def test_half_scale_sync(self, status_bar):
        status_bar.set_zoom(2.5)
        assert status_bar.zoom_badge.text() == format_zoom_label(2.5)

    def test_double_scale_sync(self, status_bar):
        status_bar.set_zoom(10.0)
        assert status_bar.zoom_badge.text() == format_zoom_label(10.0)


# ===========================================================================
# C) Wheel zoom → both displays synchron
# ===========================================================================

class TestWheelZoomSync:
    """After set_zoom_to, emitted value matches format_zoom_label."""

    def test_wheel_zoom_signal_matches_label(self, sketch_editor, status_bar):
        status_bar.set_mode("2D")
        sketch_editor.zoom_changed.connect(status_bar.set_zoom)

        sketch_editor.set_zoom_to(7.3)

        expected = format_zoom_label(sketch_editor.view_scale)
        assert status_bar.zoom_badge.text() == expected


# ===========================================================================
# D) Fit view → both displays synchron
# ===========================================================================

class TestFitViewSync:
    """After _fit_view, badge matches format_zoom_label(view_scale)."""

    def test_fit_view_updates_badge(self, sketch_editor, status_bar):
        status_bar.set_mode("2D")
        sketch_editor.zoom_changed.connect(status_bar.set_zoom)

        # Add geometry so _fit_view has something to fit
        sketch_editor.sketch.add_line(0, 0, 100, 0)
        sketch_editor.sketch.add_line(0, 0, 0, 100)
        sketch_editor.resize(800, 600)
        sketch_editor._fit_view()

        expected = format_zoom_label(sketch_editor.view_scale)
        assert status_bar.zoom_badge.text() == expected


# ===========================================================================
# E) Preset click → both displays synchron
# ===========================================================================

class TestPresetSync:
    """Preset → set_zoom_to → badge shows matching format_zoom_label."""

    def test_preset_5x_sync(self, status_bar, sketch_editor):
        status_bar.set_mode("2D")
        status_bar.zoom_preset_requested.connect(sketch_editor.set_zoom_to)
        sketch_editor.zoom_changed.connect(status_bar.set_zoom)

        menu = status_bar._build_zoom_menu()
        actions = [a for a in menu.actions() if not a.isSeparator()]
        actions[1].trigger()  # 5x

        assert status_bar.zoom_badge.text() == "5x"
        assert status_bar.zoom_badge.text() == format_zoom_label(sketch_editor.view_scale)

    def test_preset_2_5x_sync(self, status_bar, sketch_editor):
        status_bar.set_mode("2D")
        status_bar.zoom_preset_requested.connect(sketch_editor.set_zoom_to)
        sketch_editor.zoom_changed.connect(status_bar.set_zoom)

        menu = status_bar._build_zoom_menu()
        actions = [a for a in menu.actions() if not a.isSeparator()]
        actions[0].trigger()  # 2.5x

        assert status_bar.zoom_badge.text() == "2.5x"
        assert status_bar.zoom_badge.text() == format_zoom_label(sketch_editor.view_scale)

    def test_preset_10x_sync(self, status_bar, sketch_editor):
        status_bar.set_mode("2D")
        status_bar.zoom_preset_requested.connect(sketch_editor.set_zoom_to)
        sketch_editor.zoom_changed.connect(status_bar.set_zoom)

        menu = status_bar._build_zoom_menu()
        actions = [a for a in menu.actions() if not a.isSeparator()]
        actions[2].trigger()  # 10x

        assert status_bar.zoom_badge.text() == "10x"
        assert status_bar.zoom_badge.text() == format_zoom_label(sketch_editor.view_scale)
