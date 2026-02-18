"""
W25 workflow product leaps: fast behavior-proof unit tests.
"""

import os
import sys
import types
from types import SimpleNamespace

os.environ.setdefault("QT_OPENGL", "software")

from gui.browser import ProjectBrowser
from gui.main_window import MainWindow
from gui.viewport_pyvista import PyVistaViewport


def _build_viewport_stub(selection_faces, *, allow_trace=True):
    calls = {"show": [], "clear": 0, "draw": 0}

    stub = SimpleNamespace()
    stub.hover_face_id = -1
    stub.detector = SimpleNamespace(selection_faces=selection_faces)

    def _is_trace_assist_allowed():
        return allow_trace

    def show_trace_hint(face_id):
        calls["show"].append(face_id)

    def clear_trace_hint():
        calls["clear"] += 1

    def _draw_selectable_faces_from_detector():
        calls["draw"] += 1

    stub._is_trace_assist_allowed = _is_trace_assist_allowed
    stub.show_trace_hint = show_trace_hint
    stub.clear_trace_hint = clear_trace_hint
    stub._draw_selectable_faces_from_detector = _draw_selectable_faces_from_detector
    return stub, calls


def test_update_hover_shows_trace_hint_for_body_face_when_allowed():
    face = SimpleNamespace(id=42, domain_type="body_face")
    viewport, calls = _build_viewport_stub([face], allow_trace=True)

    PyVistaViewport._update_hover(viewport, 42)

    assert viewport.hover_face_id == 42
    assert calls["show"] == [42]
    assert calls["draw"] == 1


def test_update_hover_clears_trace_hint_for_non_body_face():
    face = SimpleNamespace(id=7, domain_type="sketch_profile")
    viewport, calls = _build_viewport_stub([face], allow_trace=True)

    PyVistaViewport._update_hover(viewport, 7)

    assert calls["show"] == []
    assert calls["clear"] == 1
    assert calls["draw"] == 1


def test_update_hover_clears_trace_hint_when_trace_assist_disallowed():
    face = SimpleNamespace(id=9, domain_type="body_face")
    viewport, calls = _build_viewport_stub([face], allow_trace=False)

    PyVistaViewport._update_hover(viewport, 9)

    assert calls["show"] == []
    assert calls["clear"] == 1
    assert calls["draw"] == 1


def test_on_create_sketch_requested_cleans_transients_and_starts_sketch():
    face = SimpleNamespace(id=101)
    clear_calls = []
    start_calls = []
    panel_calls = []
    mode_calls = []
    trace_clear_calls = []
    projection_clear_calls = []

    fake_self = SimpleNamespace(
        viewport_3d=SimpleNamespace(
            detector=SimpleNamespace(selection_faces=[face]),
            clear_trace_hint=lambda: trace_clear_calls.append("trace"),
            clear_projection_preview=lambda: projection_clear_calls.append("projection"),
        ),
        sketch_editor=SimpleNamespace(start_sketch=lambda f: start_calls.append(f)),
        tool_panel=SimpleNamespace(show_sketch_tools=lambda: panel_calls.append("shown")),
        _end_current_mode=lambda: mode_calls.append("ended"),
        _clear_transient_previews=lambda reason="", clear_interaction_modes=False: clear_calls.append(
            (reason, clear_interaction_modes)
        ),
    )

    MainWindow._on_create_sketch_requested(fake_self, 101)

    assert clear_calls == [("create_sketch_requested", True)]
    assert trace_clear_calls == ["trace"]
    assert projection_clear_calls == ["projection"]
    assert mode_calls == ["ended"]
    assert start_calls == [face]
    assert panel_calls == ["shown"]


def test_on_component_activated_runs_cleanup_and_pushes_command(monkeypatch):
    pushed_commands = []
    status_messages = []
    clear_calls = []
    trace_clear_calls = []
    projection_clear_calls = []

    class FakeActivateComponentCommand:
        def __init__(self, component, previous_active, main_window):
            self.component = component
            self.previous_active = previous_active
            self.main_window = main_window

    fake_module = types.ModuleType("gui.commands.component_commands")
    fake_module.ActivateComponentCommand = FakeActivateComponentCommand
    monkeypatch.setitem(sys.modules, "gui.commands.component_commands", fake_module)

    previous_component = SimpleNamespace(name="OldComp")
    new_component = SimpleNamespace(name="NewComp")

    fake_self = SimpleNamespace(
        document=SimpleNamespace(_assembly_enabled=True, _active_component=previous_component),
        undo_stack=SimpleNamespace(push=lambda cmd: pushed_commands.append(cmd)),
        statusBar=lambda: SimpleNamespace(showMessage=lambda msg: status_messages.append(msg)),
        _clear_transient_previews=lambda reason="", clear_interaction_modes=False: clear_calls.append(
            (reason, clear_interaction_modes)
        ),
        viewport_3d=SimpleNamespace(
            clear_trace_hint=lambda: trace_clear_calls.append(True),
            clear_projection_preview=lambda: projection_clear_calls.append(True),
        ),
    )

    MainWindow._on_component_activated(fake_self, new_component)

    assert clear_calls == [("component_activated", True)]
    assert trace_clear_calls == [True]
    assert projection_clear_calls == [True]
    assert len(pushed_commands) == 1
    assert pushed_commands[0].component is new_component
    assert pushed_commands[0].previous_active is previous_component
    assert status_messages == ["Aktive Component: NewComp"]


def test_browser_activate_component_delegates_to_safe():
    called = []
    component = SimpleNamespace(name="CompA")
    fake_self = SimpleNamespace(_activate_component_safe=lambda c: called.append(c))

    ProjectBrowser._activate_component(fake_self, component)

    assert called == [component]


def test_browser_activate_component_safe_emits_signal_with_guards():
    emitted = []
    component = SimpleNamespace(name="CompB")
    fake_self = SimpleNamespace(
        _assembly_enabled=True,
        document=SimpleNamespace(name="Doc"),
        component_activated=SimpleNamespace(emit=lambda c: emitted.append(c)),
    )

    result = ProjectBrowser._activate_component_safe(fake_self, component)
    assert result is True
    assert emitted == [component]

    disabled_self = SimpleNamespace(
        _assembly_enabled=False,
        document=SimpleNamespace(name="Doc"),
        component_activated=SimpleNamespace(emit=lambda c: emitted.append(c)),
    )
    assert ProjectBrowser._activate_component_safe(disabled_self, component) is False
