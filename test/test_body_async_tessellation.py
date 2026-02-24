from types import SimpleNamespace

from modeling.body import Body


class _FakeManager:
    def __init__(self):
        self.requests = []

    def request_tessellation(self, body_id, solid, on_ready, on_error=None):
        self.requests.append(
            {
                "body_id": body_id,
                "solid": solid,
                "on_ready": on_ready,
                "on_error": on_error,
            }
        )
        return SimpleNamespace()


def test_request_async_tessellation_updates_cache_and_forwards_callback(monkeypatch):
    body = Body("AsyncTest")
    body._build123d_solid = object()

    fake_manager = _FakeManager()
    monkeypatch.setattr(Body, "_shared_tessellation_manager", fake_manager)

    received = []

    def _user_on_ready(body_id, mesh, edges, face_info):
        received.append((body_id, mesh, edges, face_info))

    worker = body.request_async_tessellation(on_ready=_user_on_ready)

    assert worker is not None
    assert len(fake_manager.requests) == 1
    req = fake_manager.requests[0]
    assert req["body_id"] == body.id
    assert req["solid"] is body._build123d_solid

    mesh = SimpleNamespace(n_points=42)
    edges = SimpleNamespace(n_lines=7)
    face_info = {"0": {"normal": (0, 0, 1)}}
    req["on_ready"](body.id, mesh, edges, face_info)

    assert body._mesh_cache is mesh
    assert body._edges_cache is edges
    assert body._face_info_cache == face_info
    assert body._mesh_cache_valid is True
    assert received == [(body.id, mesh, edges, face_info)]


def test_request_async_tessellation_ignores_stale_callback(monkeypatch):
    body = Body("AsyncGeneration")
    body._build123d_solid = object()

    fake_manager = _FakeManager()
    monkeypatch.setattr(Body, "_shared_tessellation_manager", fake_manager)

    callback_hits = []
    body.request_async_tessellation(
        on_ready=lambda *_args: callback_hits.append("first")
    )
    body.request_async_tessellation(
        on_ready=lambda *_args: callback_hits.append("second")
    )

    assert len(fake_manager.requests) == 2
    first_req = fake_manager.requests[0]
    second_req = fake_manager.requests[1]

    mesh_new = SimpleNamespace(n_points=100)
    mesh_old = SimpleNamespace(n_points=10)
    edges = SimpleNamespace(n_lines=1)

    second_req["on_ready"](body.id, mesh_new, edges, {})
    first_req["on_ready"](body.id, mesh_old, edges, {})

    assert body._mesh_cache is mesh_new
    assert callback_hits == ["second"]
