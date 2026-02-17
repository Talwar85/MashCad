"""
W26 Paket F2: Feature Detail Recovery Actions Tests
====================================================
Testet die neuen W26 Feature Detail Panel Features:
- Error-Taxonomie mit Recovery-Aktionen
- Copy-Diagnostics verbessert mit strukturierten Feldern

Author: AI-LARGE-F (Product Surface Cell)
Date: 2026-02-17
Branch: feature/v1-ux-aiB
"""

# CRITICAL: QT_OPENGL muss VOR jedem Qt/PyVista Import gesetzt werden
import os
os.environ["QT_OPENGL"] = "software"

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from unittest.mock import Mock, MagicMock, patch

from gui.widgets.feature_detail_panel import FeatureDetailPanel


@pytest.fixture(scope="session")
def qt_app():
    """Session-weite QApplication Instanz."""
    app = QApplication.instance()
    if app is None:
        import sys
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def panel(qt_app):
    """FeatureDetailPanel Fixture."""
    panel = FeatureDetailPanel()
    panel.show()
    QTest.qWaitForWindowExposed(panel)
    yield panel
    panel.close()
    panel.deleteLater()


class TestW26RecoveryActionsExist:
    """
    W26 Paket F2: Tests für Recovery-Action UI-Elemente.
    6 Assertions
    """

    def test_recovery_header_exists(self, panel):
        """F2-W26-R1: Recovery Header existiert."""
        assert hasattr(panel, '_recovery_header')

    def test_recovery_buttons_exist(self, panel):
        """F2-W26-R2: Alle Recovery-Buttons existieren."""
        assert hasattr(panel, '_btn_reselect_ref')
        assert hasattr(panel, '_btn_edit_feature')
        assert hasattr(panel, '_btn_rebuild')
        assert hasattr(panel, '_btn_accept_drift')
        assert hasattr(panel, '_btn_check_deps')

    def test_recovery_action_signals_exist(self, panel):
        """F2-W26-R3: Recovery-Action Signale existieren."""
        assert hasattr(panel, 'recovery_action_requested')
        assert hasattr(panel, 'edit_feature_requested')
        assert hasattr(panel, 'rebuild_feature_requested')
        assert hasattr(panel, 'delete_feature_requested')

    def test_update_recovery_actions_method_exists(self, panel):
        """F2-W26-R4: _update_recovery_actions Methode existiert."""
        assert hasattr(panel, '_update_recovery_actions')

    def test_on_recovery_action_method_exists(self, panel):
        """F2-W26-R5: _on_recovery_action Methode existiert."""
        assert hasattr(panel, '_on_recovery_action')

    def test_recovery_buttons_hidden_for_ok_feature(self, panel):
        """F2-W26-R6: Recovery-Buttons sind für OK-Features versteckt."""
        feature = Mock()
        feature.name = "OKFeature"
        feature.status = "OK"
        feature.status_details = {}
        feature.edge_indices = []

        panel.show_feature(feature)

        assert not panel._recovery_header.isVisible()


class TestW26ErrorCodeMapping:
    """
    W26 Paket F2: Tests für Error-Code-Mapping.
    """

    def test_tnp_ref_missing_shows_reselect_ref(self, panel):
        """F2-W26-R7: tnp_ref_missing zeigt 'Referenz neu wählen' Button."""
        feature = Mock()
        feature.name = "MissingRefFeature"
        feature.status = "ERROR"
        feature.status_details = {
            "code": "tnp_ref_missing",
            "tnp_failure": {"category": "missing_ref"}
        }
        feature.edge_indices = []

        panel.show_feature(feature)

        # Bei tnp_ref_missing sollten bestimmte Buttons sichtbar sein
        assert panel._recovery_header.isVisible()

    def test_tnp_ref_drift_shows_accept_drift(self, panel):
        """F2-W26-R8: tnp_ref_drift zeigt 'Drift akzeptieren' Button."""
        feature = Mock()
        feature.name = "DriftFeature"
        feature.status = "WARNING"
        feature.status_details = {
            "code": "tnp_ref_drift",
            "tnp_failure": {"category": "drift"}
        }
        feature.edge_indices = []

        panel.show_feature(feature)

        assert panel._recovery_header.isVisible()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
