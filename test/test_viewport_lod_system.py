from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import gui.viewport_pyvista as viewport_mod
from gui.viewport_pyvista import PyVistaViewport


class _FakeMapper:
    def __init__(self):
        self.input_data = None
        self.modified_calls = 0

    def SetInputData(self, data):
        self.input_data = data

    def Modified(self):
        self.modified_calls += 1


class _FakeActor:
    def __init__(self, visible=True):
        self._visible = visible
        self._mapper = _FakeMapper()

    def GetMapper(self):
        return self._mapper

    def GetVisibility(self):
        return self._visible

    def SetVisibility(self, value):
        self._visible = bool(value)


class _FakeMesh:
    def __init__(self, n_points=5000):
        self.n_points = n_points
        self.bounds = (0.0, 1.0, 0.0, 1.0, 0.0, 1.0)


def _make_dummy_viewport():
    renderer = SimpleNamespace(
        actors={
            "body_b1_m": _FakeActor(visible=True),
            "body_b1_e": _FakeActor(visible=True),
        }
    )
    plotter = SimpleNamespace(renderer=renderer)

    vp = SimpleNamespace()
    vp.plotter = plotter
    vp._lod_enabled = True
    vp._lod_quality_high = 0.01
    vp._lod_quality_interaction = 0.05
    vp._lod_min_points = 2500
    vp._lod_applied_quality = {}
    vp._section_view_enabled = False
    vp._section_plane = "XY"
    vp._section_position = 0.0
    vp._section_invert = False
    vp._body_actors = {"b1": ("body_b1_m", "body_b1_e")}
    vp.bodies = {
        "b1": {
            "mesh": _FakeMesh(n_points=4000),
            "body_ref": SimpleNamespace(_build123d_solid=object()),
        }
    }

    vp._is_body_actor_visible = PyVistaViewport._is_body_actor_visible.__get__(vp, object)
    vp._apply_lod_mesh_to_actor = PyVistaViewport._apply_lod_mesh_to_actor.__get__(vp, object)
    vp._apply_lod_to_visible_bodies = PyVistaViewport._apply_lod_to_visible_bodies.__get__(vp, object)
    vp._on_camera_interaction_start = PyVistaViewport._on_camera_interaction_start.__get__(vp, object)
    vp._on_camera_interaction_end = PyVistaViewport._on_camera_interaction_end.__get__(vp, object)

    return vp


def test_lod_switches_interaction_and_restore_quality(monkeypatch):
    vp = _make_dummy_viewport()
    monkeypatch.setattr(viewport_mod, "HAS_PYVISTA", True)

    quality_calls = []

    def _fake_tessellate_with_face_ids(_solid, quality=None):
        quality_calls.append(quality)
        mesh = _FakeMesh(n_points=1500 if quality >= 0.05 else 6500)
        return mesh, _FakeMesh(n_points=300), {}

    from modeling.cad_tessellator import CADTessellator

    monkeypatch.setattr(CADTessellator, "tessellate_with_face_ids", staticmethod(_fake_tessellate_with_face_ids))
    monkeypatch.setattr(viewport_mod, "request_render", lambda *_args, **_kwargs: None)

    vp._apply_lod_to_visible_bodies(interaction_active=True)
    vp._apply_lod_to_visible_bodies(interaction_active=False)

    assert quality_calls == [0.05, 0.01]
    assert vp._lod_applied_quality["b1"] == 0.01
    assert vp.bodies["b1"]["mesh"].n_points == 6500


def test_lod_camera_end_emits_view_and_starts_restore_timer():
    vp = _make_dummy_viewport()
    vp.view_changed = Mock()
    vp._lod_restore_timer = Mock()

    vp._on_camera_interaction_end()

    vp.view_changed.emit.assert_called_once()
    vp._lod_restore_timer.start.assert_called_once()


def test_lod_camera_start_stops_timer_and_applies_interaction_lod():
    vp = _make_dummy_viewport()
    vp._lod_restore_timer = Mock()
    vp._lod_restore_timer.isActive.return_value = True
    vp._apply_lod_to_visible_bodies = Mock()

    vp._on_camera_interaction_start()

    vp._lod_restore_timer.stop.assert_called_once()
    vp._apply_lod_to_visible_bodies.assert_called_once_with(interaction_active=True)
