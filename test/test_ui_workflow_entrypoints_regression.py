"""
UI workflow entrypoint regression tests.

Focus:
- Hole / Draft / Split dialog entrypoints
- Measure / Section mode entrypoints
- MainWindow signal wiring for double-click + face workflow callbacks
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


os.environ["QT_OPENGL"] = "software"

with patch.dict(
    "sys.modules",
    {
        "PySide6.QtWebEngineWidgets": Mock(),
        "pyvista": Mock(),
        "pyvistaqt": Mock(),
    },
):
    from gui.main_window import MainWindow


def _qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _statusbar_stub():
    sb = Mock()
    sb.showMessage = Mock()
    sb.clearMessage = Mock()
    return sb


def _body_with_solid():
    return SimpleNamespace(id="B1", name="Body1", _build123d_solid=object())


def _make_stub():
    mw = MainWindow.__new__(MainWindow)
    sb = _statusbar_stub()
    mw.statusBar = lambda: sb
    return mw, sb


def test_hole_dialog_enters_mode_and_opens_panel():
    _qt_app()
    mw, sb = _make_stub()
    mw.document = SimpleNamespace(bodies=[_body_with_solid()])
    mw._hide_transform_ui = Mock()
    mw.viewport_3d = SimpleNamespace(set_hole_mode=Mock())
    mw.hole_panel = SimpleNamespace(reset=Mock(), show_at=Mock(), hide=Mock())

    MainWindow._hole_dialog(mw)

    assert mw._hole_mode is True
    assert mw._hole_target_body is None
    assert mw._hole_face_selector is None
    assert mw._hole_face_shape_id is None
    assert mw._hole_face_index is None
    mw._hide_transform_ui.assert_called_once()
    mw.viewport_3d.set_hole_mode.assert_called_once_with(True)
    mw.hole_panel.reset.assert_called_once()
    mw.hole_panel.show_at.assert_called_once_with(mw.viewport_3d)
    assert sb.showMessage.call_count >= 1


def test_draft_dialog_enters_mode_detects_faces_and_opens_panel():
    _qt_app()
    mw, sb = _make_stub()
    mw.document = SimpleNamespace(bodies=[_body_with_solid()])
    mw._hide_transform_ui = Mock()
    mw.viewport_3d = SimpleNamespace(
        detected_faces=[],
        _detect_body_faces=Mock(),
        set_draft_mode=Mock(),
    )
    mw.draft_panel = SimpleNamespace(reset=Mock(), show_at=Mock(), hide=Mock())

    MainWindow._draft_dialog(mw)

    assert mw._draft_mode is True
    assert mw._draft_target_body is None
    mw._hide_transform_ui.assert_called_once()
    mw.viewport_3d._detect_body_faces.assert_called_once()
    mw.viewport_3d.set_draft_mode.assert_called_once_with(True)
    mw.draft_panel.reset.assert_called_once()
    mw.draft_panel.show_at.assert_called_once_with(mw.viewport_3d)
    assert sb.showMessage.call_count >= 1


def test_split_dialog_enters_pending_body_pick_and_opens_panel():
    _qt_app()
    mw, sb = _make_stub()
    mw.document = SimpleNamespace(bodies=[_body_with_solid()])
    mw._hide_transform_ui = Mock()
    mw.viewport_3d = SimpleNamespace(
        setCursor=Mock(),
        set_pending_transform_mode=Mock(),
    )
    mw.split_panel = SimpleNamespace(reset=Mock(), show_at=Mock(), hide=Mock())

    MainWindow._split_body_dialog(mw)

    assert mw._split_mode is True
    assert mw._pending_split_mode is True
    assert mw._split_target_body is None
    mw._hide_transform_ui.assert_called_once()
    mw.split_panel.reset.assert_called_once()
    mw.split_panel.show_at.assert_called_once_with(mw.viewport_3d)
    mw.viewport_3d.setCursor.assert_called_once_with(Qt.CrossCursor)
    mw.viewport_3d.set_pending_transform_mode.assert_called_once_with(True)
    assert sb.showMessage.call_count >= 1


def test_measure_mode_starts_and_opens_panel():
    _qt_app()
    mw, sb = _make_stub()
    mw.viewport_3d = SimpleNamespace(set_measure_mode=Mock())
    mw.measure_panel = SimpleNamespace(reset=Mock(), show_at=Mock(), hide=Mock())

    MainWindow._start_measure_mode(mw)

    assert mw._measure_mode is True
    assert mw._measure_points == [None, None]
    mw.measure_panel.reset.assert_called_once()
    mw.measure_panel.show_at.assert_called_once_with(mw.viewport_3d)
    mw.viewport_3d.set_measure_mode.assert_called_once_with(True)
    assert sb.showMessage.call_count >= 1


def test_section_view_toggle_enables_then_disables():
    _qt_app()
    mw, _sb = _make_stub()
    mw.viewport_3d = SimpleNamespace(
        enable_section_view=Mock(),
        disable_section_view=Mock(),
    )

    class _SectionPanel:
        def __init__(self):
            self.visible = False

        def isVisible(self):
            return self.visible

        def show_at(self, _vp):
            self.visible = True

        def hide(self):
            self.visible = False

    mw.section_panel = _SectionPanel()

    MainWindow._toggle_section_view(mw)
    assert mw.section_panel.isVisible() is True
    mw.viewport_3d.enable_section_view.assert_called_once_with("XY", 0.0)

    MainWindow._toggle_section_view(mw)
    assert mw.section_panel.isVisible() is False
    mw.viewport_3d.disable_section_view.assert_called_once()


class _Signal:
    def __init__(self):
        self.connected = []

    def connect(self, callback):
        self.connected.append(callback)


class _SignalContainer:
    def __init__(self):
        self._signals = {}

    def __getattr__(self, name):
        sig = self._signals.get(name)
        if sig is None:
            sig = _Signal()
            self._signals[name] = sig
        return sig


def test_connect_signals_wires_doubleclick_and_face_workflows():
    _qt_app()
    mw, _sb = _make_stub()

    mw.tool_panel = _SignalContainer()
    mw.tool_panel_3d = _SignalContainer()
    mw.sketch_editor = _SignalContainer()
    mw.browser = _SignalContainer()
    mw.feature_detail_panel = _SignalContainer()
    mw.viewport_3d = _SignalContainer()
    mw.transform_state = object()

    MainWindow._connect_signals(mw)

    assert mw._edit_feature in mw.browser.feature_double_clicked.connected
    assert mw._on_viewport_body_clicked in mw.viewport_3d.body_clicked.connected
    assert mw._on_body_face_clicked_for_hole in mw.viewport_3d.hole_face_clicked.connected
    assert mw._on_body_face_clicked_for_draft in mw.viewport_3d.draft_face_clicked.connected
    assert mw._on_split_body_clicked in mw.viewport_3d.split_body_clicked.connected
    assert mw._on_measure_point_picked in mw.viewport_3d.measure_point_picked.connected
