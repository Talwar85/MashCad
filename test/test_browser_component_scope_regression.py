"""
Regression tests for component-aware browser body/sketch handling.
"""

import os
import sys
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from gui.browser import ProjectBrowser
from modeling.component import Component

os.environ["QT_OPENGL"] = "software"


def _qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_get_visible_bodies_legacy_branch_uses_get_all_bodies_without_private_list():
    _qt_app()
    browser = ProjectBrowser()
    browser._assembly_enabled = False

    body = SimpleNamespace(id="B1")
    browser.document = SimpleNamespace(
        get_all_bodies=lambda: [body],
        bodies=[body],
    )

    visible = browser.get_visible_bodies()

    assert len(visible) == 1
    assert visible[0][0] is body
    assert visible[0][1] is True
    assert visible[0][2] is False


def test_del_body_removes_from_owning_component_and_emits_signal():
    _qt_app()
    browser = ProjectBrowser()
    browser._assembly_enabled = True

    root = Component(name="Root")
    child = Component(name="Child", parent=root)
    root.sub_components.append(child)

    body = SimpleNamespace(id="B1", name="Body1")
    child.bodies.append(body)

    browser.document = SimpleNamespace(
        root_component=root,
        bodies=[],
    )
    browser.refresh = lambda: None

    deleted_ids = []
    browser.body_deleted.connect(lambda bid: deleted_ids.append(bid))

    browser._del_body(body)

    assert body not in child.bodies
    assert deleted_ids == ["B1"]


def test_del_sketch_removes_from_owning_component():
    _qt_app()
    browser = ProjectBrowser()
    browser._assembly_enabled = True

    root = Component(name="Root")
    child = Component(name="Child", parent=root)
    root.sub_components.append(child)

    sketch = SimpleNamespace(id="S1", name="Sketch1")
    child.sketches.append(sketch)

    browser.document = SimpleNamespace(
        root_component=root,
        sketches=[],
    )
    browser.refresh = lambda: None

    browser._del_sketch(sketch)

    assert sketch not in child.sketches
