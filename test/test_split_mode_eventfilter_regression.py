from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt

import gui.viewport_pyvista as viewport_mod
from gui.viewport_pyvista import PyVistaViewport


class _Emitter:
    def __init__(self):
        self.calls = []

    def emit(self, *args):
        self.calls.append(args)


class _MouseEvent:
    def __init__(
        self,
        event_type,
        x=0,
        y=0,
        button=Qt.NoButton,
        buttons=Qt.NoButton,
        modifiers=Qt.NoModifier,
    ):
        self._event_type = event_type
        self._x = x
        self._y = y
        self._button = button
        self._buttons = buttons
        self._modifiers = modifiers

    def type(self):
        return self._event_type

    def button(self):
        return self._button

    def buttons(self):
        return self._buttons

    def modifiers(self):
        return self._modifiers

    def position(self):
        return QPointF(float(self._x), float(self._y))

    def pos(self):
        return QPoint(int(self._x), int(self._y))


def _make_host(monkeypatch):
    monkeypatch.setattr(viewport_mod, "HAS_PYVISTA", True, raising=False)

    host = SimpleNamespace()
    host.mapToGlobal = lambda p: p

    host._trace_hint_face_id = None
    host._is_trace_assist_allowed = lambda: False
    host.clear_trace_hint = Mock()
    host.create_sketch_requested = _Emitter()

    host._last_mouse_move_time = 0.0
    host._mouse_move_interval = 0.0

    host.is_dragging = False
    host._offset_plane_dragging = False
    host._split_dragging = False
    host.cancel_drag = Mock()

    host.extrude_mode = False
    host.extrude_cancelled = _Emitter()
    host.point_to_point_mode = False
    host.cancel_point_to_point_mode = Mock()

    host._right_click_start_pos = None
    host._right_click_start_global_pos = None
    host._right_click_start_time = 0.0
    host.plotter = SimpleNamespace(interactor=SimpleNamespace(mapFromGlobal=lambda p: p))
    host.pick = Mock(return_value=-1)
    host.active_selection_filter = set()
    host.clear_selection = Mock()
    host.background_clicked = _Emitter()
    host._show_context_menu = Mock()

    host.offset_plane_mode = False
    host.handle_offset_plane_mouse_press = Mock(return_value=False)
    host.handle_offset_plane_mouse_move = Mock(return_value=False)
    host.handle_offset_plane_mouse_release = Mock(return_value=False)
    host._update_offsetplane_hover_cursor = Mock(return_value=False)

    host.split_mode = True
    host._split_body_id = None
    host._split_position = 0.0
    host.split_drag_changed = _Emitter()
    host._draw_split_plane = Mock()
    host.handle_split_mouse_press = Mock(return_value=True)
    host.handle_split_mouse_move = Mock(return_value=True)
    host.handle_split_mouse_release = Mock(return_value=True)
    host._hover_body_face = Mock()

    host.is_transform_active = Mock(return_value=False)
    host.transform_state = None
    host.handle_transform_mouse_press = Mock(return_value=False)
    host.handle_transform_mouse_move = Mock(return_value=False)
    host.handle_transform_mouse_release = Mock(return_value=False)
    host.hide_transform_gizmo = Mock()

    host.texture_face_mode = False
    host._brep_cleanup_mode = False
    host.edge_select_mode = False
    host.hole_mode = False
    host.thread_mode = False
    host.draft_mode = False
    host.point_to_point_mode = False

    return host


def test_split_mode_mouse_press_routes_even_without_transform_gizmo(monkeypatch):
    host = _make_host(monkeypatch)
    event = _MouseEvent(
        QEvent.MouseButtonPress,
        x=10,
        y=20,
        button=Qt.LeftButton,
        buttons=Qt.LeftButton,
    )

    result = PyVistaViewport.eventFilter(host, host, event)

    assert result is True
    host.handle_split_mouse_press.assert_called_once_with(10, 20)


def test_split_mode_mouse_move_updates_hover_during_pending_body_pick(monkeypatch):
    host = _make_host(monkeypatch)
    event = _MouseEvent(QEvent.MouseMove, x=15, y=25, buttons=Qt.NoButton)

    result = PyVistaViewport.eventFilter(host, host, event)

    assert result is False
    host._hover_body_face.assert_called_once_with(15, 25)
    host.handle_split_mouse_move.assert_not_called()


def test_split_mode_mouse_move_routes_drag_without_transform_gizmo(monkeypatch):
    host = _make_host(monkeypatch)
    host._split_body_id = "B1"
    host._split_dragging = True
    event = _MouseEvent(QEvent.MouseMove, x=7, y=9, buttons=Qt.LeftButton)

    result = PyVistaViewport.eventFilter(host, host, event)

    assert result is True
    host.handle_split_mouse_move.assert_called_once_with(7, 9)
    host._hover_body_face.assert_not_called()


def test_hole_mode_mouse_press_refreshes_hover_before_click(monkeypatch):
    host = _make_host(monkeypatch)
    host.split_mode = False
    host.hole_mode = True
    host.hovered_body_face = None

    def _hover(x, y):
        host.hovered_body_face = ("B1", 7, (0.0, 0.0, 1.0), (1.0, 2.0, 3.0))

    host._hover_body_face = Mock(side_effect=_hover)
    host._click_body_face = Mock()

    event = _MouseEvent(
        QEvent.MouseButtonPress,
        x=11,
        y=13,
        button=Qt.LeftButton,
        buttons=Qt.LeftButton,
    )

    result = PyVistaViewport.eventFilter(host, host, event)

    assert result is True
    host._hover_body_face.assert_called_once_with(11, 13)
    host._click_body_face.assert_called_once()


def test_hole_mode_mouse_move_updates_preview_from_cursor_after_face_selection(monkeypatch):
    host = _make_host(monkeypatch)
    host.split_mode = False
    host.hole_mode = True
    host._hole_body_id = "B1"
    host._hole_plane_origin = (1.0, 2.0, 3.0)
    host._hole_normal = (0.0, 0.0, 1.0)
    host._update_hole_preview_from_cursor = Mock()
    host._hover_body_face = Mock()

    event = _MouseEvent(QEvent.MouseMove, x=17, y=19, buttons=Qt.NoButton)

    result = PyVistaViewport.eventFilter(host, host, event)

    assert result is False
    host._update_hole_preview_from_cursor.assert_called_once_with(17, 19)
    host._hover_body_face.assert_not_called()


def test_click_body_face_in_hole_mode_uses_full_face_highlight():
    host = SimpleNamespace(
        hovered_body_face=("B1", 9, (0.0, 0.0, 1.0), (1.0, 2.0, 3.0)),
        hole_mode=True,
        thread_mode=False,
        draft_mode=False,
        texture_face_mode=False,
        hole_face_clicked=_Emitter(),
        thread_face_clicked=_Emitter(),
        clear_trace_hint=Mock(),
        _draw_full_face_hover=Mock(),
        _draw_body_face_selection=Mock(),
        _detect_cylindrical_face=Mock(return_value=None),
    )

    PyVistaViewport._click_body_face(host)

    assert host.hole_face_clicked.calls == [("B1", 9, (0.0, 0.0, 1.0), (1.0, 2.0, 3.0))]
    assert host._hole_body_id == "B1"
    assert host._hole_plane_origin == (1.0, 2.0, 3.0)
    host._draw_full_face_hover.assert_called_once_with("B1", (0.0, 0.0, 1.0), (0.0, 0.0, 1.0), cell_id=9)
    host._draw_body_face_selection.assert_not_called()
