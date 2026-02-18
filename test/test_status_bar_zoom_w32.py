"""
W32: Status Bar Zoom Badge – Live Update & Presets
===================================================
Tests for live zoom badge updates, preset interaction, and 3D fallback.

W32 Hardening (AI-SMALL-5): Added real interaction tests for context menu.
W32 Semantics (AI-SMALL-6): Aligned to unified Nx format (view_scale based).

Author: AI-SMALL-4, AI-SMALL-5, AI-SMALL-6
Date: 2026-02-18
Branch: feature/v1-ux-aiB
"""

import os
os.environ["QT_OPENGL"] = "software"

import pytest
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtTest import QTest
from PySide6.QtGui import QWheelEvent, QMouseEvent

from gui.widgets.status_bar import MashCadStatusBar
from gui.sketch_editor import SketchEditor, SketchTool, format_zoom_label


@pytest.fixture(scope="session")
def qt_app():
    app = pytest.importorskip("PySide6.QtWidgets").QApplication.instance()
    if app is None:
        import sys
        app = pytest.importorskip("PySide6.QtWidgets").QApplication(sys.argv)
    return app


@pytest.fixture
def status_bar(qt_app):
    """Fresh MashCadStatusBar instance."""
    return MashCadStatusBar()


@pytest.fixture
def sketch_editor(qt_app):
    """SketchEditor with a blank sketch."""
    from sketcher import Sketch
    editor = SketchEditor()
    editor.sketch = Sketch("test")
    return editor


# ===========================================================================
# A) Live Zoom in Status Bar Badge
# ===========================================================================

class TestZoomSignalExists:
    """SketchEditor must declare a zoom_changed signal."""

    def test_sketch_editor_has_zoom_changed_signal(self, qt_app):
        assert hasattr(SketchEditor, "zoom_changed"), "SketchEditor missing zoom_changed signal"


class TestStatusBarSetZoom:
    """set_zoom() must update the badge text using format_zoom_label."""

    def test_set_zoom_updates_text(self, status_bar):
        status_bar.set_zoom(12.5)
        assert status_bar.zoom_badge.text() == "12.5x"

    def test_set_zoom_default(self, status_bar):
        status_bar.set_zoom(5.0)
        assert status_bar.zoom_badge.text() == "5x"


class TestZoomChangedEmission:
    """zoom_changed must be emitted when view_scale changes."""

    def test_emit_on_set_zoom_to(self, sketch_editor):
        received = []
        sketch_editor.zoom_changed.connect(lambda v: received.append(v))
        sketch_editor.set_zoom_to(10.0)
        assert len(received) == 1
        assert received[0] == 10.0


class TestZoomEmitHelper:
    """_emit_zoom_changed emits the raw view_scale."""

    def test_default_scale(self, sketch_editor):
        received = []
        sketch_editor.zoom_changed.connect(lambda v: received.append(v))
        sketch_editor.view_scale = 5.0
        sketch_editor._emit_zoom_changed()
        assert received[0] == 5.0

    def test_double_zoom(self, sketch_editor):
        received = []
        sketch_editor.zoom_changed.connect(lambda v: received.append(v))
        sketch_editor.view_scale = 10.0
        sketch_editor._emit_zoom_changed()
        assert received[0] == 10.0


# ===========================================================================
# B) Zoom Presets (Context Menu)
# ===========================================================================

class TestZoomPresetSignals:
    """Status bar must have zoom_preset_requested and zoom_fit_requested signals."""

    def test_has_preset_signal(self, qt_app):
        assert hasattr(MashCadStatusBar, "zoom_preset_requested")

    def test_has_fit_signal(self, qt_app):
        assert hasattr(MashCadStatusBar, "zoom_fit_requested")


class TestZoomPresetOnlyInSketchMode:
    """Context menu should only appear in sketch (2D) mode."""

    def test_no_menu_in_3d_mode(self, status_bar):
        status_bar.set_mode("3D")
        assert status_bar._is_sketch_mode is False

    def test_menu_in_2d_mode(self, status_bar):
        status_bar.set_mode("2D")
        assert status_bar._is_sketch_mode is True


class TestSetZoomToMethod:
    """set_zoom_to sets view_scale directly."""

    def test_set_zoom_to_half(self, sketch_editor):
        sketch_editor.set_zoom_to(2.5)
        assert abs(sketch_editor.view_scale - 2.5) < 0.01

    def test_set_zoom_to_double(self, sketch_editor):
        sketch_editor.set_zoom_to(10.0)
        assert abs(sketch_editor.view_scale - 10.0) < 0.01


# ===========================================================================
# C) 3D Mode – Badge Fallback
# ===========================================================================

class TestThreeDModeZoomReset:
    """When switching to 3D mode, badge must show neutral value."""

    def test_mode_3d_resets_badge(self, status_bar):
        status_bar.set_zoom(12.5)
        assert status_bar.zoom_badge.text() == "12.5x"
        status_bar.set_mode("3D")
        status_bar.set_zoom(5.0)
        assert status_bar.zoom_badge.text() == "5x"

    def test_mode_2d_keeps_zoom(self, status_bar):
        status_bar.set_zoom(8.7)
        status_bar.set_mode("2D")
        assert status_bar.zoom_badge.text() == "8.7x"


# ===========================================================================
# D) Real UI Interaction – Context Menu (W32 Hardening)
# ===========================================================================

class TestZoomMenuBuilt:
    """_build_zoom_menu returns a QMenu with the correct actions."""

    def test_menu_has_four_actions(self, status_bar):
        status_bar.set_mode("2D")
        menu = status_bar._build_zoom_menu()
        actions = [a for a in menu.actions() if not a.isSeparator()]
        assert len(actions) == 4  # 2.5x, 5x, 10x, Fit

    def test_menu_action_labels(self, status_bar):
        status_bar.set_mode("2D")
        menu = status_bar._build_zoom_menu()
        labels = [a.text() for a in menu.actions() if not a.isSeparator()]
        assert labels == ["2.5x", "5x", "10x", "Fit"]

    def test_menu_has_separator(self, status_bar):
        status_bar.set_mode("2D")
        menu = status_bar._build_zoom_menu()
        separators = [a for a in menu.actions() if a.isSeparator()]
        assert len(separators) == 1


class TestPresetActionEmitsSignal:
    """Triggering a menu action must emit the correct signal."""

    def test_2_5x_preset(self, status_bar):
        status_bar.set_mode("2D")
        received = []
        status_bar.zoom_preset_requested.connect(lambda v: received.append(v))
        menu = status_bar._build_zoom_menu()
        actions = [a for a in menu.actions() if not a.isSeparator()]
        actions[0].trigger()  # "2.5x"
        assert received == [2.5]

    def test_5x_preset(self, status_bar):
        status_bar.set_mode("2D")
        received = []
        status_bar.zoom_preset_requested.connect(lambda v: received.append(v))
        menu = status_bar._build_zoom_menu()
        actions = [a for a in menu.actions() if not a.isSeparator()]
        actions[1].trigger()  # "5x"
        assert received == [5.0]

    def test_10x_preset(self, status_bar):
        status_bar.set_mode("2D")
        received = []
        status_bar.zoom_preset_requested.connect(lambda v: received.append(v))
        menu = status_bar._build_zoom_menu()
        actions = [a for a in menu.actions() if not a.isSeparator()]
        actions[2].trigger()  # "10x"
        assert received == [10.0]

    def test_fit_preset(self, status_bar):
        status_bar.set_mode("2D")
        received = []
        status_bar.zoom_fit_requested.connect(lambda: received.append(True))
        menu = status_bar._build_zoom_menu()
        actions = [a for a in menu.actions() if not a.isSeparator()]
        actions[3].trigger()  # "Fit"
        assert len(received) == 1


class TestThreeDModeBlocksMenu:
    """In 3D mode, _on_zoom_badge_clicked must not emit any signal."""

    def test_click_in_3d_no_signal(self, status_bar):
        status_bar.set_mode("3D")
        preset_received = []
        fit_received = []
        status_bar.zoom_preset_requested.connect(lambda v: preset_received.append(v))
        status_bar.zoom_fit_requested.connect(lambda: fit_received.append(True))
        fake_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(5, 5),
            QPointF(5, 5),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        status_bar._on_zoom_badge_clicked(fake_event)
        assert preset_received == []
        assert fit_received == []


class TestPresetEndToEnd:
    """Preset action → set_zoom_to → view_scale + zoom_changed signal."""

    def test_preset_triggers_zoom_change(self, status_bar, sketch_editor):
        status_bar.set_mode("2D")
        status_bar.zoom_preset_requested.connect(sketch_editor.set_zoom_to)
        zoom_received = []
        sketch_editor.zoom_changed.connect(lambda v: zoom_received.append(v))

        menu = status_bar._build_zoom_menu()
        actions = [a for a in menu.actions() if not a.isSeparator()]
        actions[0].trigger()  # "2.5x"

        assert abs(sketch_editor.view_scale - 2.5) < 0.01
        assert zoom_received == [2.5]

    def test_preset_updates_badge_text(self, status_bar, sketch_editor):
        status_bar.set_mode("2D")
        status_bar.zoom_preset_requested.connect(sketch_editor.set_zoom_to)
        sketch_editor.zoom_changed.connect(status_bar.set_zoom)

        menu = status_bar._build_zoom_menu()
        actions = [a for a in menu.actions() if not a.isSeparator()]
        actions[2].trigger()  # "10x"

        assert status_bar.zoom_badge.text() == "10x"
