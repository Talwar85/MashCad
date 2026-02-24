"""
Regression tests for pending body-pick workflows and copy feature history.

Focus:
- Pending tool modes must activate correctly after viewport body click.
- Body copy path must clone feature history (not lose features).
"""

from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtCore import Qt

from gui.dialog_operations import DialogMixin
from gui.feature_dialogs import FeatureDialogsMixin
from gui.tool_operations import ToolMixin


class _StatusBarStub:
    def __init__(self):
        self.messages = []
        self.clear_calls = 0

    def showMessage(self, message, _timeout=0):
        self.messages.append(str(message))

    def clearMessage(self):
        self.clear_calls += 1


class _ViewportStub:
    def __init__(self):
        self.cursor_calls = []
        self.pending_transform_mode_calls = []
        self.set_extrude_mode_calls = []
        self.set_shell_mode_calls = []
        self.start_texture_face_mode_calls = []
        self.start_edge_selection_mode_calls = []
        self.edge_selection_callbacks = []
        self.hide_transform_gizmo_calls = 0

    def setCursor(self, cursor):
        self.cursor_calls.append(cursor)

    def set_pending_transform_mode(self, active):
        self.pending_transform_mode_calls.append(bool(active))

    def set_extrude_mode(self, enabled, enable_preview=True):
        self.set_extrude_mode_calls.append((bool(enabled), bool(enable_preview)))

    def set_shell_mode(self, enabled):
        self.set_shell_mode_calls.append(bool(enabled))

    def start_texture_face_mode(self, body_id):
        self.start_texture_face_mode_calls.append(body_id)

    def set_edge_selection_callbacks(self, **kwargs):
        self.edge_selection_callbacks.append(kwargs)

    def start_edge_selection_mode(self, body_id):
        self.start_edge_selection_mode_calls.append(body_id)

    def hide_transform_gizmo(self):
        self.hide_transform_gizmo_calls += 1


class _PanelStub:
    def __init__(self):
        self.reset_calls = 0
        self.show_at_calls = []
        self.hide_calls = 0
        self.set_target_body_calls = []
        self.set_body_calls = []
        self.clear_opening_faces_calls = 0

    def reset(self):
        self.reset_calls += 1

    def show_at(self, viewport):
        self.show_at_calls.append(viewport)

    def hide(self):
        self.hide_calls += 1

    def set_target_body(self, body):
        self.set_target_body_calls.append(body)

    def set_body(self, body):
        self.set_body_calls.append(body)

    def clear_opening_faces(self):
        self.clear_opening_faces_calls += 1


class _Harness(FeatureDialogsMixin, DialogMixin, ToolMixin):
    def __init__(self, body):
        self._body = body
        self.viewport_3d = _ViewportStub()
        self.browser = SimpleNamespace(
            get_selected_bodies=lambda: [],
            refresh=Mock(),
        )
        self.document = SimpleNamespace(
            bodies=[body],
            find_body_by_id=lambda bid: body if bid == body.id else None,
            add_body=Mock(),
        )
        self.pattern_panel = _PanelStub()
        self.shell_panel = _PanelStub()
        self.texture_panel = _PanelStub()
        self.lattice_panel = _PanelStub()
        self.nsided_patch_panel = _PanelStub()

        self._status_bar = _StatusBarStub()

        self._update_detector = Mock()
        self._update_viewport_all = Mock()

        # pending flags
        self._pending_transform_mode = None
        self._pending_split_mode = False
        self._pending_fillet_mode = False
        self._pending_chamfer_mode = False
        self._pending_thread_mode = False
        self._pending_brep_cleanup_mode = False
        self._pending_shell_mode = False
        self._pending_texture_mode = False
        self._pending_mesh_convert_mode = False
        self._pending_pattern_mode = False
        self._pending_lattice_mode = False
        self._pending_nsided_patch_mode = False
        self._pending_wall_thickness_mode = False
        self._pending_tnp_pick_mode = False

    def statusBar(self):
        return self._status_bar

    def __getattr__(self, name):
        if name.startswith("_"):
            return lambda *args, **kwargs: None
        raise AttributeError(name)


def _make_body():
    return SimpleNamespace(id="B1", name="Body1", _build123d_solid=object(), features=[])


def test_texture_pending_body_pick_activates_texture_panel():
    h = _Harness(_make_body())

    h._start_texture_mode()
    assert h._pending_texture_mode is True
    assert h.viewport_3d.cursor_calls[-1] == Qt.CrossCursor

    h._on_viewport_body_clicked("B1")
    assert h._pending_texture_mode is False
    assert h._texture_mode is True
    assert h._texture_target_body.id == "B1"
    assert h.texture_panel.reset_calls == 1
    assert h.texture_panel.show_at_calls == [h.viewport_3d]
    assert h.viewport_3d.start_texture_face_mode_calls == ["B1"]
    assert h.viewport_3d.pending_transform_mode_calls[-1] is False


def test_pattern_pending_body_pick_activates_pattern_panel():
    h = _Harness(_make_body())

    h._start_pattern()
    assert h._pending_pattern_mode is True
    assert h.viewport_3d.cursor_calls[-1] == Qt.CrossCursor

    h._on_viewport_body_clicked("B1")
    assert h._pending_pattern_mode is False
    assert h._pattern_mode is True
    assert h._pattern_target_body.id == "B1"
    assert h.pattern_panel.reset_calls == 1
    assert h.pattern_panel.show_at_calls == [h.viewport_3d]
    assert h.viewport_3d.pending_transform_mode_calls[-1] is False


def test_shell_pending_body_pick_activates_shell_panel_and_mode():
    h = _Harness(_make_body())

    h._start_shell()
    assert h._pending_shell_mode is True
    assert h.viewport_3d.cursor_calls[-1] == Qt.CrossCursor

    h._on_viewport_body_clicked("B1")
    assert h._pending_shell_mode is False
    assert h._shell_mode is True
    assert h._shell_target_body.id == "B1"
    assert h.shell_panel.reset_calls == 1
    assert h.shell_panel.show_at_calls == [h.viewport_3d]
    assert h.viewport_3d.set_shell_mode_calls[-1] is True
    assert h.viewport_3d.pending_transform_mode_calls[-1] is False


def test_lattice_pending_body_pick_activates_lattice_panel():
    h = _Harness(_make_body())

    h._start_lattice()
    assert h._pending_lattice_mode is True
    assert h.viewport_3d.cursor_calls[-1] == Qt.CrossCursor

    h._on_viewport_body_clicked("B1")
    assert h._pending_lattice_mode is False
    assert h._lattice_mode is True
    assert h._lattice_target_body.id == "B1"
    assert h.lattice_panel.reset_calls == 1
    assert h.lattice_panel.show_at_calls == [h.viewport_3d]
    assert h.viewport_3d.pending_transform_mode_calls[-1] is False


def test_nsided_patch_pending_body_pick_activates_panel_and_edge_mode():
    h = _Harness(_make_body())

    h._nsided_patch_dialog()
    assert h._pending_nsided_patch_mode is True
    assert h.viewport_3d.cursor_calls[-1] == Qt.CrossCursor

    h._on_viewport_body_clicked("B1")
    assert h._pending_nsided_patch_mode is False
    assert h._nsided_patch_mode is True
    assert h._nsided_patch_target_body.id == "B1"
    assert h.nsided_patch_panel.reset_calls == 1
    assert h.nsided_patch_panel.show_at_calls == [h.viewport_3d]
    assert h.viewport_3d.start_edge_selection_mode_calls == ["B1"]
    assert h.viewport_3d.pending_transform_mode_calls[-1] is False


def test_wall_thickness_pending_body_pick_routes_to_open_dialog():
    h = _Harness(_make_body())
    h._open_wall_thickness_for_body = Mock()

    h._wall_thickness_dialog()
    assert h._pending_wall_thickness_mode is True
    assert h.viewport_3d.cursor_calls[-1] == Qt.CrossCursor

    h._on_viewport_body_clicked("B1")
    assert h._pending_wall_thickness_mode is False
    h._open_wall_thickness_for_body.assert_called_once()
    assert h.viewport_3d.pending_transform_mode_calls[-1] is False


class _CopyHarness(FeatureDialogsMixin):
    def __init__(self):
        self.document = SimpleNamespace(add_body=Mock())
        self.browser = SimpleNamespace(get_selected_bodies=lambda: [], refresh=Mock())
        self._update_viewport_all = Mock()


def test_clone_body_feature_history_copies_features_and_remaps_dependencies():
    source = SimpleNamespace(
        id="src",
        features=[
            SimpleNamespace(
                id="f1",
                status="ERROR",
                status_message="bad",
                status_details={"code": "X"},
                depends_on_feature_id=None,
                face_shape_ids=[object()],
                edge_shape_id=object(),
            ),
            SimpleNamespace(
                id="f2",
                status="OK",
                status_message="",
                status_details={},
                depends_on_feature_id="f1",
                edge_shape_ids=[object(), object()],
            ),
        ],
    )

    added = []

    class _Target:
        def add_feature(self, feature, rebuild=False):
            added.append((feature, rebuild))

    h = _CopyHarness()
    count = h._clone_body_feature_history(source, _Target())

    assert count == 2
    assert len(added) == 2
    f1 = added[0][0]
    f2 = added[1][0]

    assert added[0][1] is False
    assert added[1][1] is False

    # IDs must be fresh and dependencies remapped.
    assert f1.id != "f1"
    assert f2.id != "f2"
    assert f2.depends_on_feature_id == f1.id

    # Status reset + shape refs cleared.
    assert f1.status == "OK"
    assert f1.status_message == ""
    assert f1.status_details == {}
    assert f1.face_shape_ids == []
    assert f1.edge_shape_id is None
    assert f2.edge_shape_ids == []
