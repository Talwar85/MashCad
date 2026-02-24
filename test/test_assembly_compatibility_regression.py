"""
Regression tests for assembly compatibility flags and component lookup.
"""

from types import SimpleNamespace

from gui.viewport_operations import ViewportMixin
from modeling.document import Document


class _Harness(ViewportMixin):
    pass


def _make_component(name, bodies=None, parent=None):
    return SimpleNamespace(
        name=name,
        bodies=list(bodies or []),
        sub_components=[],
        parent=parent,
    )


def test_document_sets_assembly_enabled_compatibility_flag():
    doc = Document("CompatDoc")
    assert hasattr(doc, "_assembly_enabled")
    assert doc._assembly_enabled is True


def test_find_component_for_body_traverses_sub_components():
    body = SimpleNamespace(id="B1")
    root = _make_component("Root")
    child = _make_component("Child", bodies=[body], parent=root)
    root.sub_components.append(child)

    h = _Harness()
    h.document = SimpleNamespace(
        _assembly_enabled=True,
        root_component=root,
    )

    found = h._find_component_for_body(body)
    assert found is child


def test_is_body_in_inactive_component_respects_active_component_ancestry():
    body_active = SimpleNamespace(id="A")
    body_inactive = SimpleNamespace(id="B")

    root = _make_component("Root")
    active = _make_component("Active", bodies=[body_active], parent=root)
    inactive = _make_component("Inactive", bodies=[body_inactive], parent=root)
    root.sub_components.extend([active, inactive])

    h = _Harness()
    h.document = SimpleNamespace(
        _assembly_enabled=True,
        root_component=root,
        _active_component=active,
    )

    assert h._is_body_in_inactive_component(body_active) is False
    assert h._is_body_in_inactive_component(body_inactive) is True
