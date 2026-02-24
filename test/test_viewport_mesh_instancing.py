from types import SimpleNamespace

import gui.viewport.body_mixin as body_mixin_mod


class _FakeMapper:
    def __init__(self):
        self.input_data = None

    def SetInputData(self, data):
        self.input_data = data

    def Modified(self):
        return None

    def SetResolveCoincidentTopologyToPolygonOffset(self):
        return None

    def SetRelativeCoincidentTopologyPolygonOffsetParameters(self, *_args):
        return None


class _FakeProperty:
    def SetRenderLinesAsTubes(self, *_args):
        return None

    def SetLineWidth(self, *_args):
        return None

    def SetColor(self, *_args):
        return None


class _FakeActor:
    def __init__(self):
        self._mapper = _FakeMapper()
        self._property = _FakeProperty()
        self._visible = True

    def GetMapper(self):
        return self._mapper

    def GetProperty(self):
        return self._property

    def SetVisibility(self, value):
        self._visible = bool(value)

    def GetVisibility(self):
        return self._visible


class _FakePlotter:
    def __init__(self):
        self.renderer = SimpleNamespace(actors={})

    def add_mesh(self, mesh, **kwargs):
        name = kwargs["name"]
        actor = _FakeActor()
        actor.GetMapper().SetInputData(mesh)
        self.renderer.actors[name] = actor

    def remove_actor(self, actor_name):
        self.renderer.actors.pop(actor_name, None)


class _FakeMesh:
    def __init__(self, *, n_points=100, n_cells=50, bounds=(0, 1, 0, 1, 0, 1), normals=True):
        self.n_points = int(n_points)
        self.n_cells = int(n_cells)
        self.bounds = tuple(float(v) for v in bounds)
        self.point_data = {"Normals": True} if normals else {}

    def compute_normals(self, **_kwargs):
        self.point_data["Normals"] = True
        return self


class _FakeEdgeMesh:
    def __init__(self, *, n_points=40, n_lines=30, bounds=(0, 1, 0, 1, 0, 1)):
        self.n_points = int(n_points)
        self.n_lines = int(n_lines)
        self.bounds = tuple(float(v) for v in bounds)


def _make_viewport_stub():
    vp = SimpleNamespace(
        plotter=_FakePlotter(),
        _body_actors={},
        bodies={},
        detected_faces=[],
        detector=SimpleNamespace(selection_faces=[]),
        _section_view_enabled=False,
        _pending_body_refs={},
        _lod_applied_quality={},
        _frustum_culled_body_ids=set(),
        _apply_frustum_culling=lambda force=False: 0,
    )
    vp.add_body = body_mixin_mod.BodyRenderingMixin.add_body.__get__(vp, object)
    return vp


def test_mesh_instancing_reuses_canonical_dataset(monkeypatch):
    monkeypatch.setattr(body_mixin_mod, "HAS_PYVISTA", True)
    monkeypatch.setattr(body_mixin_mod, "request_render", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        body_mixin_mod,
        "is_enabled",
        lambda flag: flag == "viewport_mesh_instancing",
    )

    body_mixin_mod.MeshInstanceCache.clear_all()
    body_mixin_mod.ActorPool.clear_all()

    vp = _make_viewport_stub()

    mesh_a = _FakeMesh(n_points=120, n_cells=60)
    edge_a = _FakeEdgeMesh(n_points=60, n_lines=40)
    mesh_b = _FakeMesh(n_points=120, n_cells=60)
    edge_b = _FakeEdgeMesh(n_points=60, n_lines=40)

    vp.add_body("a", "A", mesh_obj=mesh_a, edge_mesh_obj=edge_a, color=(0.7, 0.7, 0.7))
    vp.add_body("b", "B", mesh_obj=mesh_b, edge_mesh_obj=edge_b, color=(0.7, 0.7, 0.7))

    assert vp.bodies["a"]["mesh"] is vp.bodies["b"]["mesh"]
    assert vp.plotter.renderer.actors["body_a_m"].GetMapper().input_data is vp.bodies["a"]["mesh"]
    assert vp.plotter.renderer.actors["body_b_m"].GetMapper().input_data is vp.bodies["a"]["mesh"]


def test_mesh_instancing_disabled_keeps_distinct_objects(monkeypatch):
    monkeypatch.setattr(body_mixin_mod, "HAS_PYVISTA", True)
    monkeypatch.setattr(body_mixin_mod, "request_render", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(body_mixin_mod, "is_enabled", lambda _flag: False)

    body_mixin_mod.MeshInstanceCache.clear_all()
    body_mixin_mod.ActorPool.clear_all()

    vp = _make_viewport_stub()

    mesh_a = _FakeMesh(n_points=120, n_cells=60)
    edge_a = _FakeEdgeMesh(n_points=60, n_lines=40)
    mesh_b = _FakeMesh(n_points=120, n_cells=60)
    edge_b = _FakeEdgeMesh(n_points=60, n_lines=40)

    vp.add_body("a", "A", mesh_obj=mesh_a, edge_mesh_obj=edge_a, color=(0.7, 0.7, 0.7))
    vp.add_body("b", "B", mesh_obj=mesh_b, edge_mesh_obj=edge_b, color=(0.7, 0.7, 0.7))

    assert vp.bodies["a"]["mesh"] is not vp.bodies["b"]["mesh"]
