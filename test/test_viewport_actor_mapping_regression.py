from types import SimpleNamespace

import numpy as np

from gui.viewport.picking_mixin import PickingMixin
from gui.viewport_pyvista import PyVistaViewport
import gui.viewport.picking_mixin as picking_mod


class _FakeActor:
    def __init__(self, addr: str):
        self._addr = addr

    def GetAddressAsString(self, _prefix: str):
        return self._addr


class _FakePicker:
    def __init__(self, actor, cell_id=0, pos=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0)):
        self._actor = actor
        self._cell_id = cell_id
        self._pos = pos
        self._normal = normal

    def SetTolerance(self, _tol):
        return None

    def Pick(self, *_args):
        return 1

    def GetActor(self):
        return self._actor

    def GetCellId(self):
        return self._cell_id

    def GetPickPosition(self):
        return self._pos

    def GetPickNormal(self):
        return self._normal


def test_select_body_at_resolves_raw_actor_by_vtk_address():
    wrapped_actor = _FakeActor("Actor(0xA1)")
    raw_actor = _FakeActor("Actor(0xA1)")
    picker = _FakePicker(raw_actor)

    vp = SimpleNamespace(
        _body_actors={"B1": ("body_B1_m",)},
        plotter=SimpleNamespace(
            interactor=SimpleNamespace(height=lambda: 600),
            renderer=SimpleNamespace(actors={"body_B1_m": wrapped_actor}),
        ),
    )
    vp._get_picker = lambda _name: picker
    vp._get_body_id_for_actor = PyVistaViewport._get_body_id_for_actor.__get__(vp, object)
    vp.select_body_at = PyVistaViewport.select_body_at.__get__(vp, object)

    assert vp.select_body_at(120, 240) == "B1"


def test_picking_mixin_exact_face_lookup_works_with_raw_wrapped_actor_mismatch(monkeypatch):
    wrapped_actor = _FakeActor("Actor(0xB2)")
    raw_actor = _FakeActor("Actor(0xB2)")
    picker = _FakePicker(raw_actor, cell_id=0, pos=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0))

    monkeypatch.setattr(picking_mod, "HAS_VTK", True, raising=False)
    monkeypatch.setattr(
        picking_mod,
        "vtk",
        SimpleNamespace(vtkCellPicker=lambda: picker),
        raising=False,
    )

    face = SimpleNamespace(
        id=42,
        domain_type="body_face",
        owner_id="B1",
        ocp_face_id=2,
        _np_origin=np.array([100.0, 100.0, 100.0]),  # fallback heuristic should not match
        _np_normal=np.array([1.0, 0.0, 0.0]),
    )

    host = SimpleNamespace(
        detector=SimpleNamespace(selection_faces=[face]),
        _body_actors={"B1": ("body_B1_m",)},
        bodies={"B1": {"mesh": SimpleNamespace(cell_data={"face_id": [2]})}},
        plotter=SimpleNamespace(
            interactor=SimpleNamespace(height=lambda: 600),
            renderer=SimpleNamespace(actors={"body_B1_m": wrapped_actor}),
        ),
        is_body_visible=lambda _bid: True,
    )

    host._resolve_body_id_for_actor = PickingMixin._resolve_body_id_for_actor.__get__(host, object)
    host.pick = PickingMixin.pick.__get__(host, object)

    assert host.pick(10, 10, selection_filter={"body_face"}) == 42
