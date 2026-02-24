"""
Regression tests for viewport body visibility handling.

Guards against refactor regressions where browser visibility toggles
stopped affecting rendered actors.
"""

from types import SimpleNamespace

import gui.viewport.body_mixin as body_mod
from gui.viewport.body_mixin import BodyRenderingMixin


class _FakeActor:
    def __init__(self):
        self._visible = True

    def SetVisibility(self, visible):
        self._visible = bool(visible)

    def GetVisibility(self):
        return self._visible


def test_set_body_visibility_uses_direct_actor_fallback_when_frustum_disabled(monkeypatch):
    monkeypatch.setattr(body_mod, "request_render", lambda *_args, **_kwargs: None, raising=False)

    mesh_actor = _FakeActor()
    edge_actor = _FakeActor()
    renderer = SimpleNamespace(actors={"mesh_actor": mesh_actor, "edge_actor": edge_actor})

    host = SimpleNamespace(
        _body_actors={"B1": ("mesh_actor", "edge_actor")},
        bodies={"B1": {"requested_visible": True}},
        plotter=SimpleNamespace(renderer=renderer),
        _frustum_culling_enabled=False,
        _apply_frustum_culling=lambda force=False: 0,  # must not block direct fallback
    )
    host.set_body_visibility = BodyRenderingMixin.set_body_visibility.__get__(host, object)

    host.set_body_visibility("B1", False)

    assert host.bodies["B1"]["requested_visible"] is False
    assert mesh_actor.GetVisibility() is False
    assert edge_actor.GetVisibility() is False


def test_set_body_visibility_updates_requested_flag_even_without_registered_actors(monkeypatch):
    monkeypatch.setattr(body_mod, "request_render", lambda *_args, **_kwargs: None, raising=False)

    host = SimpleNamespace(
        _body_actors={},
        bodies={"B2": {"requested_visible": True}},
        plotter=SimpleNamespace(renderer=SimpleNamespace(actors={})),
        _frustum_culling_enabled=False,
    )
    host.set_body_visibility = BodyRenderingMixin.set_body_visibility.__get__(host, object)

    host.set_body_visibility("B2", False)

    assert host.bodies["B2"]["requested_visible"] is False
