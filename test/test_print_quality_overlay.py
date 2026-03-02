from types import SimpleNamespace

import pyvista as pv
from PySide6.QtWidgets import QApplication

from gui.dialogs.print_optimize_dialog import PrintOptimizeDialog
from gui.viewport.print_quality_overlay import PrintQualityOverlay
from modeling.print_orientation_optimizer import OrientationCandidate


def _qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _PlotterStub:
    def __init__(self):
        self.actors = {}
        self.render_calls = 0

    def add_mesh(self, mesh, **kwargs):
        name = kwargs.get("name", f"actor_{len(self.actors)}")
        self.actors[name] = (mesh.copy(deep=True), kwargs)
        return name

    def remove_actor(self, actor, **_kwargs):
        self.actors.pop(actor, None)

    def render(self):
        self.render_calls += 1


class _ViewportStub:
    def __init__(self, mesh, body):
        self.plotter = _PlotterStub()
        self._mesh = mesh
        self.bodies = {body.id: {"opacity": 1.0}}
        self.opacity_calls = []

    def get_body_mesh(self, body_id):
        assert body_id in self.bodies
        return self._mesh.copy(deep=True)

    def set_body_opacity(self, body_id, opacity):
        self.opacity_calls.append((body_id, opacity))
        self.bodies[body_id]["opacity"] = opacity


def test_print_quality_overlay_shows_and_clears_preview():
    _qapp()
    body = SimpleNamespace(id="body1", name="Body1", _build123d_solid=None)
    mesh = pv.Box(bounds=(0, 40, 0, 20, 0, 5)).triangulate()
    viewport = _ViewportStub(mesh, body)
    overlay = PrintQualityOverlay(viewport)
    candidate = OrientationCandidate(axis=(0, 1, 0), angle_deg=45, description="45 deg")

    shown = overlay.show_preview(body, candidate)

    assert shown is True
    assert PrintQualityOverlay.OVERLAY_ACTOR in viewport.plotter.actors
    assert any(call[1] < 1.0 for call in viewport.opacity_calls)

    overlay.clear()

    assert PrintQualityOverlay.OVERLAY_ACTOR not in viewport.plotter.actors
    assert viewport.bodies[body.id]["opacity"] == 1.0


def test_print_quality_overlay_rotates_preview_mesh():
    _qapp()
    body = SimpleNamespace(id="body2", name="Plate", _build123d_solid=None)
    mesh = pv.Box(bounds=(0, 40, 0, 20, 0, 5)).triangulate()
    viewport = _ViewportStub(mesh, body)
    overlay = PrintQualityOverlay(viewport)
    candidate = OrientationCandidate(axis=(0, 1, 0), angle_deg=90, description="Y 90")

    shown = overlay.show_preview(body, candidate)

    assert shown is True
    preview_mesh, _kwargs = viewport.plotter.actors[PrintQualityOverlay.OVERLAY_ACTOR]
    original_height = mesh.bounds[5] - mesh.bounds[4]
    preview_height = preview_mesh.bounds[5] - preview_mesh.bounds[4]
    assert preview_height > original_height


def test_print_optimize_dialog_reject_clears_overlay():
    _qapp()
    body = SimpleNamespace(id="body3", name="Body3")
    document = SimpleNamespace(bodies=[body])
    viewport = SimpleNamespace(get_active_body=lambda: None)
    main_window = SimpleNamespace(document=document, viewport_3d=viewport)

    dialog = PrintOptimizeDialog(main_window)

    cleared = {"count": 0}

    class _OverlayStub:
        def clear(self, render=False):
            cleared["count"] += 1

    dialog._overlay = _OverlayStub()
    dialog.reject()

    assert cleared["count"] == 1
