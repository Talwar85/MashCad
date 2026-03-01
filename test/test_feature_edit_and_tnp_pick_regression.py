from types import SimpleNamespace
from unittest.mock import Mock
import os

from PySide6.QtCore import Qt, QLocale
from PySide6.QtWidgets import QApplication

from gui.dialogs.feature_edit_dialogs import ChamferEditDialog, FilletEditDialog
from gui.design_tokens import parse_decimal
from gui.feature_dialogs import FeatureDialogsMixin
from gui.feature_operations import FeatureMixin
from gui.viewport_pyvista import PyVistaViewport
from modeling.features.advanced import LoftFeature, SweepFeature
from modeling.features.extrude import PushPullFeature


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _FeatureEditHarness(FeatureMixin):
    def __init__(self, bodies):
        self._bodies = list(bodies)
        self.browser = SimpleNamespace(get_selected_bodies=lambda: [])
        self.document = SimpleNamespace(
            get_all_bodies=lambda: list(self._bodies),
            bodies=list(self._bodies),
        )
        self._edit_parametric_feature = Mock()
        self._edit_transform_feature = Mock()
        self._edit_cadquery_feature = Mock()


class _FeatureDialogHarness(FeatureMixin, FeatureDialogsMixin):
    def __init__(self, body):
        self._body = body
        self.browser = SimpleNamespace(
            get_selected_bodies=lambda: [],
            refresh=Mock(),
        )
        self.document = SimpleNamespace(
            find_body_by_id=lambda bid: body if bid == body.id else None,
            get_all_bodies=lambda: [body],
            bodies=[body],
        )
        self.viewport_3d = SimpleNamespace(
            setCursor=Mock(),
            set_pending_transform_mode=Mock(),
        )
        self.tnp_stats_panel = SimpleNamespace(set_picking_active=Mock())
        self._edit_feature = Mock()
        self._update_tnp_stats = Mock()
        self._status_bar = SimpleNamespace(showMessage=Mock())

    def statusBar(self):
        return self._status_bar


class _TNPStatsHarness(FeatureDialogsMixin):
    def __init__(self):
        self.tnp_stats_panel = SimpleNamespace(
            update_stats=Mock(),
            refresh=Mock(),
        )


class _PushPullHarness(FeatureMixin):
    def __init__(self, body):
        self._body = body
        self.browser = SimpleNamespace(
            refresh=Mock(),
            get_selected_bodies=lambda: [],
        )
        self.viewport_3d = SimpleNamespace(get_selection_context=Mock(return_value=None))
        self.document = SimpleNamespace(
            find_body_by_id=lambda bid: body if bid == body.id else None,
            get_all_bodies=lambda: [body],
            _shape_naming_service=SimpleNamespace(find_shape_id_by_shape=Mock(return_value=None)),
        )
        self.undo_stack = SimpleNamespace(push=self._push_command)
        self.pushed_feature = None

    def _push_command(self, cmd):
        self.pushed_feature = cmd.feature
        self._body.features.append(cmd.feature)

    def _find_or_register_face_shape_id(self, *args, **kwargs):
        return "shape-1"


def test_edit_feature_routes_pushpull_loft_and_sweep_when_body_is_not_in_tuple():
    cases = [
        (PushPullFeature(face_index=1, distance=5.0), "pushpull"),
        (LoftFeature(profile_data=[{}]), "loft"),
        (SweepFeature(profile_data={}, path_data={}), "sweep"),
    ]

    for feature, expected_type in cases:
        body = SimpleNamespace(id="B1", name="Body1", features=[feature])
        harness = _FeatureEditHarness([body])

        harness._edit_feature(("feature", feature, None))

        harness._edit_parametric_feature.assert_called_once_with(feature, body, expected_type)


def test_edit_feature_requested_resolves_owner_body_and_dispatches_browser_edit():
    feature = PushPullFeature(face_index=1, distance=4.0)
    body = SimpleNamespace(id="B1", name="Body1", features=[feature])
    harness = _FeatureDialogHarness(body)

    harness._on_edit_feature_requested(feature)

    harness._edit_feature.assert_called_once_with(("feature", feature, body))


def test_tnp_body_pick_arms_viewport_body_pick_mode_and_resets_on_selection():
    feature = PushPullFeature(face_index=1, distance=4.0)
    body = SimpleNamespace(id="B1", name="Body1", features=[feature])
    harness = _FeatureDialogHarness(body)

    harness._on_tnp_body_pick_requested()

    assert harness._pending_tnp_pick_mode is True
    harness.viewport_3d.setCursor.assert_called_with(Qt.CrossCursor)
    harness.viewport_3d.set_pending_transform_mode.assert_called_with(True)
    harness.tnp_stats_panel.set_picking_active.assert_called_with(True)

    harness._on_body_clicked_for_tnp("B1")

    assert harness._pending_tnp_pick_mode is False
    assert harness.viewport_3d.set_pending_transform_mode.call_args_list[-1].args == (False,)
    assert harness.tnp_stats_panel.set_picking_active.call_args_list[-1].args == (False,)
    harness._update_tnp_stats.assert_called_once_with(body)


def test_extrude_body_face_build123d_respects_requested_operation(monkeypatch):
    fake_face = SimpleNamespace()
    body = SimpleNamespace(
        id="B1",
        name="Body1",
        _build123d_solid=object(),
        features=[],
    )
    harness = _PushPullHarness(body)

    class _Selector:
        def to_dict(self):
            return {"center": [0.0, 0.0, 0.0], "normal": [0.0, 0.0, 1.0]}

    class _FakeCommand:
        def __init__(self, body, feature, *_args, **_kwargs):
            self.body = body
            self.feature = feature

    monkeypatch.setattr("modeling.topology_indexing.face_from_index", lambda _solid, idx: fake_face if idx == 4 else None)
    monkeypatch.setattr(
        "modeling.geometric_selector.GeometricFaceSelector.from_face",
        staticmethod(lambda _face: _Selector()),
    )
    monkeypatch.setattr("gui.commands.feature_commands.AddFeatureCommand", _FakeCommand)

    success = harness._extrude_body_face_build123d(
        {
            "body_id": "B1",
            "face_index": 4,
            "normal": (0.0, 0.0, 1.0),
            "center": (1.0, 2.0, 3.0),
            "selection_face_id": 17,
        },
        5.0,
        "Cut",
    )

    assert success is True
    assert harness.pushed_feature is not None
    assert harness.pushed_feature.operation == "Cut"
    assert harness.pushed_feature.direction == -1
    assert harness.pushed_feature.distance == 5.0
    assert harness.pushed_feature.face_shape_id == "shape-1"
    assert harness.browser.refresh.call_count == 1


def test_viewport_initializes_picking_selection_context_storage():
    _qapp()
    viewport = PyVistaViewport()
    try:
        assert hasattr(viewport, "_selection_contexts")
        assert isinstance(viewport._selection_contexts, dict)
    finally:
        viewport.close()


def test_update_tnp_stats_uses_panel_update_stats_api():
    body = SimpleNamespace(name="Body1")
    harness = _TNPStatsHarness()

    harness._update_tnp_stats(body)

    harness.tnp_stats_panel.update_stats.assert_called_once_with(body)
    harness.tnp_stats_panel.refresh.assert_not_called()


def test_feature_edit_dialog_preserves_decimal_text_under_german_locale():
    app = _qapp()
    previous_locale = QLocale()
    QLocale.setDefault(QLocale(QLocale.German, QLocale.Germany))

    dialogs = []
    try:
        cases = [
            (
                FilletEditDialog,
                SimpleNamespace(
                    name="Fillet",
                    radius=2.0,
                    edge_indices=[],
                    edge_shape_ids=[],
                    geometric_selectors=[],
                    _geometry_delta=None,
                ),
                "radius_input",
                "radius",
            ),
            (
                ChamferEditDialog,
                SimpleNamespace(
                    name="Chamfer",
                    distance=2.0,
                    edge_indices=[],
                    edge_shape_ids=[],
                    geometric_selectors=[],
                    _geometry_delta=None,
                ),
                "distance_input",
                "distance",
            ),
        ]

        for dialog_cls, feature, field_name, attr_name in cases:
            dialog = dialog_cls(feature, SimpleNamespace(name="Body1"))
            dialogs.append(dialog)
            field = getattr(dialog, field_name)

            dialog.show()
            field.setFocus()
            app.processEvents()
            field.clearFocus()
            app.processEvents()
            app.processEvents()

            assert "E+" not in field.text(), field.text()
            assert abs(parse_decimal(field.text(), -1.0) - 2.0) < 1e-9, field.text()

            dialog._on_apply()
            assert abs(getattr(feature, attr_name) - 2.0) < 1e-9
    finally:
        for dialog in dialogs:
            dialog.close()
        QLocale.setDefault(previous_locale)
