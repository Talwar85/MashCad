"""
Regression tests for MainWindow mixin action routing.

These tests lock down the dispatch chain that broke during the mixin split:
- Tool action -> handler method
- pending body-click mode -> correct callback
"""

from types import SimpleNamespace
from unittest.mock import Mock

from gui.feature_dialogs import FeatureDialogsMixin
from gui.tool_operations import ToolMixin


class _StatusBarStub:
    def __init__(self):
        self.last_message = None

    def showMessage(self, message, _timeout=0):
        self.last_message = message

    def clearMessage(self):
        self.last_message = None


class _ViewportStub:
    def __init__(self):
        self.pending_mode_calls = []
        self.cursor_calls = []
        self.edge_selection_callback_kwargs = []
        self.edge_selection_mode_calls = []
        self.sweep_mode_calls = []
        self.loft_mode_calls = []
        self.extrude_mode_calls = []

    def set_pending_transform_mode(self, active):
        self.pending_mode_calls.append(bool(active))

    def setCursor(self, cursor):
        self.cursor_calls.append(cursor)

    def set_edge_selection_callbacks(self, **kwargs):
        self.edge_selection_callback_kwargs.append(kwargs)

    def start_edge_selection_mode(self, body_id, selection_mode):
        self.edge_selection_mode_calls.append((body_id, selection_mode))

    def set_sweep_mode(self, enabled):
        self.sweep_mode_calls.append(bool(enabled))

    def set_loft_mode(self, enabled):
        self.loft_mode_calls.append(bool(enabled))

    def set_extrude_mode(self, enabled, enable_preview=True):
        self.extrude_mode_calls.append((bool(enabled), bool(enable_preview)))


class _Harness(FeatureDialogsMixin, ToolMixin):
    """Lightweight test harness for mixin methods."""

    def __init__(self):
        self.viewport_3d = _ViewportStub()
        self.browser = SimpleNamespace(get_selected_bodies=lambda: [])
        self.document = SimpleNamespace(
            find_body_by_id=lambda _bid: SimpleNamespace(id="B1", name="Body1")
        )
        self.fillet_panel = SimpleNamespace(
            set_target_body=lambda _b: None,
            set_mode=lambda _m: None,
            reset=lambda: None,
            update_edge_count=lambda _n: None,
            show_at=lambda _vp: None,
            isVisible=lambda: False,
        )
        self.sweep_panel = SimpleNamespace(
            reset=Mock(),
            show_at=Mock(),
        )
        self.loft_panel = SimpleNamespace(
            reset=Mock(),
            show_at=Mock(),
        )
        self.transform_panel = SimpleNamespace(
            set_mode=Mock(),
            set_body_name=Mock(),
            set_body=Mock(),
            setToolTip=Mock(),
            show=Mock(),
        )
        self.nsided_patch_panel = SimpleNamespace(
            update_edge_count=Mock(),
            set_edge_count=Mock(),
        )
        self._status_bar = _StatusBarStub()
        self._update_detector = Mock()
        self._position_transform_panel = Mock()

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
        # _on_3d_action builds a full dispatch table eagerly and touches many
        # handlers. For this routing-focused test harness we provide no-op
        # fallbacks for unneeded methods.
        if name.startswith("_"):
            return lambda *args, **kwargs: None
        raise AttributeError(name)


def test_3d_action_dispatches_critical_handlers():
    """Critical 3D actions must still dispatch to their handlers."""
    h = _Harness()

    dispatch_map = {
        "fillet": "_start_fillet",
        "chamfer": "_start_chamfer",
        "hole": "_hole_dialog",
        "draft": "_draft_dialog",
        "split_body": "_split_body_dialog",
        "shell": "_start_shell",
        "sweep": "_start_sweep",
        "loft": "_start_loft",
        "pattern": "_start_pattern",
        "measure": "_start_measure_mode",
        "wall_thickness": "_wall_thickness_dialog",
        "section_view": "_toggle_section_view",
        "surface_texture": "_start_texture_mode",
        "lattice": "_start_lattice",
        "nsided_patch": "_nsided_patch_dialog",
        "point_to_point": "_start_point_to_point_move",
        "point_to_point_move": "_start_point_to_point_move",
    }

    for action, method_name in dispatch_map.items():
        method_mock = Mock()
        setattr(h, method_name, method_mock)
        h._on_3d_action(action)
        method_mock.assert_called_once()


def test_start_fillet_without_selected_body_enters_pending_pick_mode():
    """If no body is selected, fillet enters pending body-pick mode."""
    h = _Harness()

    h._start_fillet()

    assert h._pending_fillet_mode == "fillet"
    assert h._pending_chamfer_mode is False
    assert h.viewport_3d.pending_mode_calls[-1] is True
    assert h._status_bar.last_message is not None


def test_pending_fillet_body_click_routes_to_activation():
    """Body-click while fillet is pending must activate fillet mode."""
    h = _Harness()
    h._pending_fillet_mode = "fillet"
    h._pending_chamfer_mode = False
    h.document = SimpleNamespace(
        find_body_by_id=lambda bid: SimpleNamespace(id=bid, name="BodyFromPick")
    )
    activate_mock = Mock()
    h._activate_fillet_chamfer_for_body = activate_mock

    h._on_viewport_body_clicked("B42")

    activate_mock.assert_called_once()
    args, _kwargs = activate_mock.call_args
    assert args[0].id == "B42"
    assert args[1] == "fillet"
    assert h._pending_fillet_mode is False
    assert h._pending_chamfer_mode is False
    assert h.viewport_3d.pending_mode_calls[-1] is False


def test_activate_fillet_enables_edge_selection_with_all_filter():
    """
    Regression guard: fillet/chamfer must expose all edges for selection.
    """
    h = _Harness()
    body = SimpleNamespace(id="B17", name="Body17", _build123d_solid=object())

    h._activate_fillet_chamfer_for_body(body, "fillet")

    assert h._fillet_mode == "fillet"
    assert h._fillet_target_body is body
    assert h.viewport_3d.edge_selection_mode_calls[-1] == ("B17", "all")
    assert h.viewport_3d.edge_selection_callback_kwargs
    assert callable(h.viewport_3d.edge_selection_callback_kwargs[-1]["get_body_by_id"])


def test_show_transform_ui_falls_back_to_set_body_when_set_body_name_missing():
    h = _Harness()
    h.transform_panel = SimpleNamespace(
        set_mode=Mock(),
        set_body=Mock(),
        setToolTip=Mock(),
        show=Mock(),
    )
    h.viewport_3d.show_transform_gizmo = Mock()

    h._show_transform_ui("B1", "Body1", "move")

    h.transform_panel.set_mode.assert_called_once_with("move")
    h.transform_panel.set_body.assert_called_once_with("Body1")
    h.transform_panel.show.assert_called_once()
    h.viewport_3d.show_transform_gizmo.assert_called_once_with("B1", "move")


def test_transform_live_update_syncs_visible_panel_values():
    h = _Harness()
    h.transform_panel = SimpleNamespace(
        isVisible=lambda: True,
        set_values=Mock(),
    )

    h._on_transform_values_live_update(1.0, 2.0, 3.0)

    h.transform_panel.set_values.assert_called_once_with(1.0, 2.0, 3.0)


def test_start_sweep_enables_face_picking_and_shows_panel():
    h = _Harness()

    h._start_sweep()

    assert h._sweep_mode is True
    assert h._sweep_phase == "profile"
    assert h.viewport_3d.sweep_mode_calls[-1] is True
    assert h.viewport_3d.extrude_mode_calls[-1] == (True, False)
    h.sweep_panel.reset.assert_called_once()
    h.sweep_panel.show_at.assert_called_once_with(h.viewport_3d)
    h._update_detector.assert_called_once()
    assert h._status_bar.last_message is not None


def test_start_loft_enables_face_picking_and_shows_panel():
    h = _Harness()

    h._start_loft()

    assert h._loft_mode is True
    assert h._loft_profiles == []
    assert h.viewport_3d.loft_mode_calls[-1] is True
    assert h.viewport_3d.extrude_mode_calls[-1] == (True, False)
    h.loft_panel.reset.assert_called_once()
    h.loft_panel.show_at.assert_called_once_with(h.viewport_3d)
    h._update_detector.assert_called_once()
    assert h._status_bar.last_message is not None


def test_edge_selection_changed_routes_sweep_path_edges():
    h = _Harness()
    h._sweep_mode = True
    h._sweep_phase = "path"
    h._on_edge_selected_for_sweep = Mock()
    h.viewport_3d.get_selected_edges = lambda: ["e1", "e2"]

    h._on_edge_selection_changed(2)

    h._on_edge_selected_for_sweep.assert_called_once_with(["e1", "e2"])


def test_edge_selection_changed_updates_nsided_patch_panel_count():
    h = _Harness()
    h._nsided_patch_mode = True

    h._on_edge_selection_changed(3)

    h.nsided_patch_panel.update_edge_count.assert_called_once_with(3)


def test_pending_body_click_dispatch_table_covers_all_modes():
    """
    Regression guard: each pending flag must route to its callback.
    """
    h = _Harness()

    routes = [
        ("_pending_split_mode", "_on_split_body_clicked"),
        ("_pending_fillet_mode", "_on_body_clicked_for_fillet"),
        ("_pending_thread_mode", "_on_body_clicked_for_thread"),
        ("_pending_brep_cleanup_mode", "_on_body_clicked_for_brep_cleanup"),
        ("_pending_shell_mode", "_on_body_clicked_for_shell"),
        ("_pending_texture_mode", "_on_body_clicked_for_texture"),
        ("_pending_mesh_convert_mode", "_on_body_clicked_for_mesh_convert"),
        ("_pending_pattern_mode", "_on_body_clicked_for_pattern"),
        ("_pending_lattice_mode", "_on_body_clicked_for_lattice"),
        ("_pending_nsided_patch_mode", "_on_body_clicked_for_nsided_patch"),
        ("_pending_wall_thickness_mode", "_on_body_clicked_for_wall_thickness"),
        ("_pending_tnp_pick_mode", "_on_body_clicked_for_tnp"),
    ]

    for flag_name, callback_name in routes:
        h = _Harness()
        setattr(h, callback_name, Mock())
        setattr(h, flag_name, "fillet" if flag_name == "_pending_fillet_mode" else True)

        h._on_viewport_body_clicked("B99")

        callback = getattr(h, callback_name)
        callback.assert_called_once_with("B99")
