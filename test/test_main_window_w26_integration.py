"""
W26 F-UX-1: MainWindow integration tests (lightweight).
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest
from PySide6.QtWidgets import QApplication

os.environ["QT_OPENGL"] = "software"

with patch.dict(
    "sys.modules",
    {
        "PySide6.QtWebEngineWidgets": Mock(),
        "pyvista": Mock(),
        "pyvistaqt": Mock(),
    },
):
    from gui.main_window import MainWindow


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_mainwindow_stub():
    mw = MainWindow.__new__(MainWindow)
    mw.status_bar_mock = Mock()
    mw.statusBar = lambda: mw.status_bar_mock
    mw.notification_manager = Mock()
    mw.browser = Mock()
    mw.browser.refresh = Mock()
    mw.browser.body_visibility = {}
    mw._trigger_viewport_update = Mock()
    mw.feature_detail_panel = Mock()
    mw.feature_detail_dock = Mock()
    mw.log_dock = Mock()
    mw.viewport_3d = Mock()
    mw.body_properties = Mock()
    mw._hide_transform_ui = Mock()
    mw._update_tnp_stats = Mock()
    mw._edit_feature = Mock()
    mw._get_active_body = Mock(return_value=None)
    mw.document = Mock()
    return mw


class TestW26MainWindowBatchIntegration:
    def test_mainwindow_has_batch_handlers(self, qt_app):
        assert hasattr(MainWindow, "_on_batch_retry_rebuild")
        assert hasattr(MainWindow, "_on_batch_open_diagnostics")
        assert hasattr(MainWindow, "_on_batch_isolate_bodies")

    def test_batch_retry_rebuild_noop_when_empty(self, qt_app):
        mw = _make_mainwindow_stub()
        MainWindow._on_batch_retry_rebuild(mw, [])
        mw.status_bar_mock.showMessage.assert_called_once()
        mw.browser.refresh.assert_not_called()

    def test_batch_open_diagnostics_shows_panel(self, qt_app):
        mw = _make_mainwindow_stub()
        feature = Mock(name="feature")
        body = Mock(name="body")
        MainWindow._on_batch_open_diagnostics(mw, [(feature, body)])
        mw.feature_detail_panel.show_feature.assert_called_once_with(feature, body, mw.document)
        mw.feature_detail_dock.show.assert_called_once()
        mw.feature_detail_dock.raise_.assert_called_once()
        mw.log_dock.show.assert_called_once()

    def test_batch_isolate_bodies_updates_visibility(self, qt_app):
        mw = _make_mainwindow_stub()
        b1 = Mock()
        b1.id = "b1"
        b2 = Mock()
        b2.id = "b2"
        b3 = Mock()
        b3.id = "b3"
        mw.document.get_all_bodies = Mock(return_value=[b1, b2, b3])
        MainWindow._on_batch_isolate_bodies(mw, [b1, b2])
        assert mw.browser.body_visibility["b1"] is True
        assert mw.browser.body_visibility["b2"] is True
        assert mw.browser.body_visibility["b3"] is False
        mw.browser.refresh.assert_called_once()


class TestW26MainWindowRecoveryIntegration:
    def test_mainwindow_has_recovery_handlers(self, qt_app):
        assert hasattr(MainWindow, "_on_recovery_action_requested")
        assert hasattr(MainWindow, "_on_edit_feature_requested")
        assert hasattr(MainWindow, "_on_rebuild_feature_requested")
        assert hasattr(MainWindow, "_on_delete_feature_requested")

    def test_recovery_action_noop_for_unknown_action(self, qt_app):
        mw = _make_mainwindow_stub()
        feature = Mock()
        feature.name = "FeatureX"
        MainWindow._on_recovery_action_requested(mw, "unknown_action", feature)


class TestW26MainWindowFeatureDetailPanel:
    def test_feature_selection_shows_feature_detail_panel(self, qt_app):
        mw = _make_mainwindow_stub()
        feature = Mock()
        feature.name = "FeatA"
        body = Mock()
        body.id = "B1"
        MainWindow._on_feature_selected(mw, ("feature", feature, body))
        mw.feature_detail_panel.show_feature.assert_called_once_with(feature, body, mw.document)
        mw.feature_detail_dock.show.assert_called_once()
        mw.feature_detail_dock.raise_.assert_called_once()

    def test_body_selection_hides_feature_detail_panel(self, qt_app):
        mw = _make_mainwindow_stub()
        body = Mock()
        body.id = "B2"
        body.name = "Body2"
        MainWindow._on_feature_selected(mw, ("body", body))
        mw.feature_detail_dock.hide.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
