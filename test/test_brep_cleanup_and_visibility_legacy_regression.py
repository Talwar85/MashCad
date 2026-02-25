"""
Regression guards for restored BREP cleanup callbacks and legacy visibility toggle.
"""

from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from gui.feature_dialogs import FeatureDialogsMixin
from gui.feature_operations import FeatureMixin


class _DialogHarness(FeatureDialogsMixin):
    def __init__(self):
        self._pending_brep_cleanup_mode = False
        self._brep_cleanup_body = None
        self.viewport_3d = SimpleNamespace(
            setCursor=Mock(),
            set_pending_transform_mode=Mock(),
            select_feature_by_index=Mock(),
        )
        self.browser = SimpleNamespace(
            get_selected_bodies=lambda: [],
            refresh=Mock(),
        )
        self.document = SimpleNamespace(find_body_by_id=lambda _bid: None)
        self.show_notification = Mock()
        self._trigger_viewport_update = Mock()
        self._active_body = None

    def _get_active_body(self):
        return self._active_body

    def statusBar(self):
        return SimpleNamespace(showMessage=Mock())


class _FeatureHarness(FeatureMixin):
    def __init__(self):
        self._on_bodies_visibility_state_changed = Mock()


def test_brep_feature_selected_delegates_to_viewport():
    host = _DialogHarness()

    host._on_brep_cleanup_feature_selected(3, additive=True)

    host.viewport_3d.select_feature_by_index.assert_called_once_with(3, True)


def test_brep_merge_all_fallback_uses_transaction_and_refreshes_ui():
    host = _DialogHarness()
    body = SimpleNamespace(id="B1", name="Body1", _build123d_solid=object())
    host._brep_cleanup_body = body

    fake_merger_module = ModuleType("modeling.brep_face_merger")
    merge_mock = Mock(return_value=SimpleNamespace(message="merged"))
    fake_merger_module.merge_with_transaction = merge_mock

    with patch.dict("sys.modules", {"modeling.brep_face_merger": fake_merger_module}):
        host._on_brep_cleanup_merge_all()

    merge_mock.assert_called_once_with(body)
    host._trigger_viewport_update.assert_called_once()
    host.browser.refresh.assert_called_once()
    host.show_notification.assert_called_once()


def test_toggle_brep_cleanup_activates_directly_when_body_already_selected():
    body = SimpleNamespace(id="B2", name="Body2", _build123d_solid=object())
    host = _DialogHarness()
    host.browser = SimpleNamespace(get_selected_bodies=lambda: [body], refresh=Mock())
    host._activate_brep_cleanup_for_body = Mock()

    host._toggle_brep_cleanup()

    host._activate_brep_cleanup_for_body.assert_called_once_with(body)
    assert host._pending_brep_cleanup_mode is False
    host.viewport_3d.set_pending_transform_mode.assert_called_once_with(False)


def test_legacy_visibility_toggle_routes_to_state_handler():
    host = _FeatureHarness()

    host._on_toggle_bodies_visibility(True)
    host._on_toggle_bodies_visibility(False)

    assert host._on_bodies_visibility_state_changed.call_args_list[0].args == (2,)
    assert host._on_bodies_visibility_state_changed.call_args_list[1].args == (0,)
