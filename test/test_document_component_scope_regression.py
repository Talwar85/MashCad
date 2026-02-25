"""
Regression tests for document-wide component handling in Document methods.
"""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from modeling.document import Document, SplitResult


class _FakeBody:
    _counter = 0

    def __init__(self, name, document=None):
        type(self)._counter += 1
        self.id = f"{name}_{type(self)._counter}"
        self.name = name
        self._document = document
        self.features = []
        self._build123d_solid = None
        self._invalidate_calls = 0

    def invalidate_mesh(self):
        self._invalidate_calls += 1


def test_split_body_uses_owning_component_not_active_component():
    doc = Document("SplitScopeDoc")
    inactive_comp = doc.new_component("InactiveComp")
    doc.set_active_component(doc.root_component)

    source = _FakeBody("SourceBody", document=doc)
    source.id = "SRC1"
    source._build123d_solid = object()
    source.features = []
    source._compute_split = lambda _feat, _solid: SplitResult(
        body_above=object(),
        body_below=object(),
        split_plane={},
    )

    doc.add_body(source, component=inactive_comp, set_active=False)
    doc.active_body = source

    fake_build123d = ModuleType("build123d")
    fake_build123d.Solid = object

    with patch.dict(sys.modules, {"build123d": fake_build123d}), patch("modeling.document.Body", _FakeBody):
        body_above, body_below = doc.split_body(source, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))

    assert source not in inactive_comp.bodies
    assert body_above in inactive_comp.bodies
    assert body_below in inactive_comp.bodies
    assert doc.active_body is body_above
    assert body_above._invalidate_calls == 1
    assert body_below._invalidate_calls == 1


def test_export_step_uses_document_wide_bodies_not_only_active_component():
    doc = Document("ExportScopeDoc")
    inactive_comp = doc.new_component("InactiveComp")
    doc.set_active_component(doc.root_component)

    body = SimpleNamespace(id="B_INACTIVE", _build123d_solid=object())
    doc.add_body(body, component=inactive_comp, set_active=False)

    writer = SimpleNamespace(
        export_solid=Mock(return_value=SimpleNamespace(success=True, message="")),
        export_assembly=Mock(return_value=SimpleNamespace(success=True, message="")),
    )
    schema = SimpleNamespace(AP214="AP214", AP242="AP242")

    fake_step_io = ModuleType("modeling.step_io")
    fake_step_io.STEPWriter = writer
    fake_step_io.STEPSchema = schema

    with patch.dict(sys.modules, {"modeling.step_io": fake_step_io}):
        result = doc.export_step("dummy.step", schema="AP214")

    assert result is True
    writer.export_solid.assert_called_once()
    writer.export_assembly.assert_not_called()
