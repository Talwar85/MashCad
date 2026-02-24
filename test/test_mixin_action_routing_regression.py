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

    def set_pending_transform_mode(self, active):
        self.pending_mode_calls.append(bool(active))

    def setCursor(self, cursor):
        self.cursor_calls.append(cursor)


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
        )
        self._status_bar = _StatusBarStub()

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
        "measure": "_start_measure_mode",
        "section_view": "_toggle_section_view",
        "surface_texture": "_start_texture_mode",
        "lattice": "_start_lattice",
        "nsided_patch": "_nsided_patch_dialog",
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
