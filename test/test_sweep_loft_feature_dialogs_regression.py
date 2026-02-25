"""
Regression tests for Sweep/Loft dialog workflows.

Covers regressions introduced during mixin refactor:
- panel API mismatch (set_profile/set_path/add_profile)
- wrong dataclass constructor kwargs (profile_data/path_data)
"""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

from gui.feature_dialogs import FeatureDialogsMixin


class _StatusBarStub:
    def __init__(self):
        self.messages = []

    def showMessage(self, message, _timeout=0):
        self.messages.append(str(message))

    def clearMessage(self):
        self.messages.append("")


class _UndoStackStub:
    def __init__(self):
        self.pushed = []
        self.undo_calls = 0

    def push(self, cmd):
        self.pushed.append(cmd)

    def undo(self):
        self.undo_calls += 1


class _Harness(FeatureDialogsMixin):
    def __init__(self):
        self._status = _StatusBarStub()
        self.undo_stack = _UndoStackStub()
        self.browser = SimpleNamespace(refresh=Mock())
        self._update_viewport_all = Mock()
        self._update_body_from_build123d = Mock()
        self._update_detector = Mock()

        self.viewport_3d = SimpleNamespace(
            detector=SimpleNamespace(selection_faces=[]),
            start_sketch_path_mode=Mock(),
            stop_sketch_path_mode=Mock(),
            set_extrude_mode=Mock(),
            set_edge_selection_callbacks=Mock(),
            start_edge_selection_mode=Mock(),
            stop_edge_selection_mode=Mock(),
            set_sweep_mode=Mock(),
            set_loft_mode=Mock(),
            get_selected_edges=lambda: [],
            get_selected_edge_topology_indices=lambda: [],
            _edge_selection_body_id=None,
        )

        self.sweep_panel = SimpleNamespace(
            set_profile=Mock(),
            set_path=Mock(),
            clear_profile=Mock(),
            clear_path=Mock(),
            get_operation=lambda: "Join",
            is_frenet=lambda: False,
            get_twist_angle=lambda: 0.0,
            get_scale_start=lambda: 1.0,
            get_scale_end=lambda: 1.0,
            hide=Mock(),
        )

        self.loft_panel = SimpleNamespace(
            add_profile=Mock(),
            get_profiles=lambda: [],
            get_operation=lambda: "Join",
            is_ruled=lambda: False,
            hide=Mock(),
        )

        self._sweep_mode = False
        self._sweep_phase = None
        self._sweep_profile_data = None
        self._sweep_path_data = None
        self._sweep_profile_shape_id = None
        self._sweep_profile_face_index = None
        self._sweep_profile_geometric_selector = None
        self._loft_mode = False
        self._loft_profiles = []

        self._active_body = SimpleNamespace(id="B1", _build123d_solid=object(), features=[])
        self.document = SimpleNamespace(
            bodies=[self._active_body],
            find_body_by_id=lambda bid: self._active_body if bid == "B1" else None,
            get_all_sketches=lambda: [],
        )

    def statusBar(self):
        return self._status

    def _get_active_body(self):
        return self._active_body


def _make_face(face_id=7, domain_type="sketch_face", owner_id="S1"):
    return SimpleNamespace(
        id=face_id,
        domain_type=domain_type,
        owner_id=owner_id,
        plane_origin=(0.0, 0.0, 0.0),
        plane_normal=(0.0, 0.0, 1.0),
        plane_x=(1.0, 0.0, 0.0),
        plane_y=(0.0, 1.0, 0.0),
        shapely_poly=None,
        ocp_face_id=0,
    )


def test_on_face_selected_for_sweep_sets_profile_and_switches_to_path_phase():
    h = _Harness()
    h._sweep_mode = True
    h._sweep_phase = "profile"
    h.viewport_3d.detector.selection_faces = [_make_face()]

    h._on_face_selected_for_sweep(7)

    assert h._sweep_profile_data["face_id"] == 7
    assert h._sweep_phase == "path"
    h.sweep_panel.set_profile.assert_called_once()
    h.viewport_3d.start_sketch_path_mode.assert_called_once()
    h.viewport_3d.set_extrude_mode.assert_called_with(True, enable_preview=False)


def test_on_face_selected_for_loft_adds_profile_via_panel_api():
    h = _Harness()
    h._loft_mode = True
    h.viewport_3d.detector.selection_faces = [_make_face()]

    h._on_face_selected_for_loft(7)

    assert len(h._loft_profiles) == 1
    h.loft_panel.add_profile.assert_called_once()


def test_sweep_confirmed_builds_feature_with_profile_data_and_path_data(monkeypatch):
    h = _Harness()
    h._sweep_profile_data = {"type": "sketch_face", "face_id": 7}
    h._sweep_path_data = {"type": "body_edge", "edge_indices": [0], "build123d_edges": []}
    expected_profile = dict(h._sweep_profile_data)
    expected_path = dict(h._sweep_path_data)

    captured = {}

    class _FakeSweepFeature:
        def __init__(
            self,
            *,
            profile_data,
            path_data,
            is_frenet,
            operation,
            twist_angle,
            scale_start,
            scale_end,
        ):
            captured["profile_data"] = profile_data
            captured["path_data"] = path_data
            captured["operation"] = operation
            self.profile_shape_id = None
            self.profile_face_index = None
            self.profile_geometric_selector = None
            self.path_geometric_selector = None

    fake_modeling = ModuleType("modeling")
    fake_modeling.__path__ = []
    fake_modeling.SweepFeature = _FakeSweepFeature
    fake_modeling.Body = object
    fake_tess_module = ModuleType("modeling.cad_tessellator")
    fake_tess_module.CADTessellator = SimpleNamespace(notify_body_changed=Mock())
    with monkeypatch.context() as m:
        m.setitem(sys.modules, "modeling", fake_modeling)
        m.setitem(sys.modules, "modeling.cad_tessellator", fake_tess_module)
        m.setattr(
            "gui.commands.feature_commands.AddFeatureCommand",
            lambda body, feature, *_args, **_kwargs: SimpleNamespace(body=body, feature=feature),
            raising=False,
        )
        h._on_sweep_confirmed()

    assert captured["profile_data"] == expected_profile
    assert captured["path_data"] == expected_path
    assert captured["operation"] == "Join"
    assert len(h.undo_stack.pushed) == 1


def test_loft_confirmed_builds_feature_with_profile_data(monkeypatch):
    h = _Harness()
    h._loft_profiles = [
        {"face_id": 1, "plane_origin": (0, 0, 10)},
        {"face_id": 2, "plane_origin": (0, 0, 0)},
    ]
    h.loft_panel.get_profiles = lambda: list(h._loft_profiles)

    captured = {}

    class _FakeLoftFeature:
        def __init__(self, *, profile_data, operation, ruled):
            captured["profile_data"] = profile_data
            captured["operation"] = operation
            captured["ruled"] = ruled

    fake_modeling = ModuleType("modeling")
    fake_modeling.__path__ = []
    fake_modeling.LoftFeature = _FakeLoftFeature
    fake_modeling.Body = object
    fake_tess_module = ModuleType("modeling.cad_tessellator")
    fake_tess_module.CADTessellator = SimpleNamespace(notify_body_changed=Mock())
    with monkeypatch.context() as m:
        m.setitem(sys.modules, "modeling", fake_modeling)
        m.setitem(sys.modules, "modeling.cad_tessellator", fake_tess_module)
        m.setattr(
            "gui.commands.feature_commands.AddFeatureCommand",
            lambda body, feature, *_args, **_kwargs: SimpleNamespace(body=body, feature=feature),
            raising=False,
        )
        h._on_loft_confirmed()

    assert captured["operation"] == "Join"
    assert captured["ruled"] is False
    assert [p["face_id"] for p in captured["profile_data"]] == [2, 1]
    assert len(h.undo_stack.pushed) == 1
