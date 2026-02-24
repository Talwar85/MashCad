"""
Regression tests for component-aware body add/remove undo commands.
"""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from gui.commands.feature_commands import AddBodyCommand
from modeling.document import Document


def _install_fake_tessellator():
    fake_tess = ModuleType("modeling.cad_tessellator")
    fake_tess.CADTessellator = SimpleNamespace(notify_body_changed=Mock())
    return {"modeling.cad_tessellator": fake_tess}


def _main_window_stub():
    return SimpleNamespace(
        _update_body_from_build123d=Mock(),
        browser=SimpleNamespace(refresh=Mock()),
        viewport_3d=SimpleNamespace(remove_body=Mock()),
    )


def test_add_body_command_redo_does_not_duplicate_body_in_inactive_component():
    doc = Document("CmdDocRedo")
    inactive = doc.new_component("Inactive")
    doc.set_active_component(doc.root_component)

    body = SimpleNamespace(id="B1", name="Body1", _build123d_solid=None)
    doc.add_body(body, component=inactive, set_active=False)
    doc.add_body = Mock(wraps=doc.add_body)

    mw = _main_window_stub()
    cmd = AddBodyCommand(doc, body, mw)

    with patch.dict(sys.modules, _install_fake_tessellator()):
        cmd.redo()

    assert doc.add_body.call_count == 0
    assert inactive.bodies.count(body) == 1


def test_add_body_command_undo_removes_body_from_owning_component():
    doc = Document("CmdDocUndo")
    inactive = doc.new_component("Inactive")
    doc.set_active_component(doc.root_component)

    body = SimpleNamespace(id="B1", name="Body1", _build123d_solid=None)
    doc.add_body(body, component=inactive, set_active=False)

    mw = _main_window_stub()
    cmd = AddBodyCommand(doc, body, mw)

    with patch.dict(sys.modules, _install_fake_tessellator()):
        cmd.undo()

    assert body not in inactive.bodies
    mw.viewport_3d.remove_body.assert_called_once_with("B1")
    mw.browser.refresh.assert_called_once()
