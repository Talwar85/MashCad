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

    def SetResolveCoincidentTopologyToPolygonOffset(self):
        return None

    def SetRelativeCoincidentTopologyPolygonOffsetParameters(self, *_args):
        return None


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

    def GetProperty(self):
        return SimpleNamespace(
            SetRenderLinesAsTubes=lambda *_args: None,
            SetLineWidth=lambda *_args: None,
            SetColor=lambda *_args: None,
        )


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


def test_pending_body_ref_is_applied_when_body_actor_arrives(monkeypatch):
    import gui.viewport.body_mixin as body_mixin_mod

    monkeypatch.setattr(body_mixin_mod, "HAS_PYVISTA", True)
    monkeypatch.setattr(body_mixin_mod, "request_render", lambda *_args, **_kwargs: None)

    class _FakePlotter:
        def __init__(self):
            self.renderer = SimpleNamespace(actors={})

        def add_mesh(self, _mesh, **kwargs):
            name = kwargs["name"]
            self.renderer.actors[name] = _FakeActor(visible=True)

        def remove_actor(self, actor_name):
            self.renderer.actors.pop(actor_name, None)

    class _RenderableMesh:
        def __init__(self):
            self.point_data = {}
            self.n_points = 3200

        def compute_normals(self, **_kwargs):
            return self

    fake_body_ref = object()
    mesh_obj = _RenderableMesh()
    edge_mesh_obj = SimpleNamespace(n_lines=12)

    viewport = SimpleNamespace(
        plotter=_FakePlotter(),
        _body_actors={},
        bodies={},
        detected_faces=[],
        detector=SimpleNamespace(selection_faces=[]),
        _section_view_enabled=False,
        _pending_body_refs={"b1": fake_body_ref},
    )
    viewport.add_body = body_mixin_mod.BodyRenderingMixin.add_body.__get__(viewport, object)

    viewport.add_body(
        bid="b1",
        name="Body 1",
        mesh_obj=mesh_obj,
        edge_mesh_obj=edge_mesh_obj,
        color=(0.7, 0.7, 0.7),
    )

    assert viewport.bodies["b1"]["body_ref"] is fake_body_ref
    assert "b1" not in viewport._pending_body_refs
