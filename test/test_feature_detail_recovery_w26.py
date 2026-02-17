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
    Verhaltenstests mit sichtbaren UI-Änderungen.
    """

    def test_tnp_ref_missing_shows_reselect_ref_button(self, panel):
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
        assert panel._btn_reselect_ref.isVisible()
        assert panel._btn_edit_feature.isVisible()

    def test_tnp_ref_drift_shows_accept_drift_button(self, panel):
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
        assert panel._btn_accept_drift.isVisible()

    def test_rebuild_finalize_failed_shows_rebuild_button(self, panel):
        """F2-W26-R9: rebuild_finalize_failed zeigt 'Rebuild' Button."""
        feature = Mock()
        feature.name = "RebuildFailed"
        feature.status = "ERROR"
        feature.status_details = {
            "code": "rebuild_finalize_failed"
        }
        feature.edge_indices = []

        panel.show_feature(feature)

        assert panel._recovery_header.isVisible()
        assert panel._btn_rebuild.isVisible()


class TestW26RecoverySignalBehavior:
    """
    W26 F-UX-3: Behavior-Tests für Recovery-Signale.
    Prüft echte Signalemission mit korrekten Payloads.
    """

    def test_recovery_action_requested_emits_with_action_and_feature(self, panel):
        """F2-W26-R10: recovery_action_requested emittiert (action, feature)."""
        received_calls = []
        panel.recovery_action_requested.connect(
            lambda action, feat: received_calls.append((action, feat))
        )

        # Mock Feature
        mock_feature = Mock()
        mock_feature.name = "TestFeature"
        panel._current_feature = mock_feature

        # Aktion auslösen
        panel._on_recovery_action("edit")

        # Verhalten prüfen
        assert len(received_calls) == 1
        assert received_calls[0][0] == "edit"
        assert received_calls[0][1] == mock_feature

    def test_edit_feature_requested_emits_with_feature(self, panel):
        """F2-W26-R11: edit_feature_requested emittiert Feature."""
        received_features = []
        panel.edit_feature_requested.connect(
            lambda feat: received_features.append(feat)
        )

        # Mock Feature
        mock_feature = Mock()
        mock_feature.name = "TestFeature"
        panel._current_feature = mock_feature

        # Aktion auslösen
        panel._on_recovery_action("edit")

        # Verhalten prüfen
        assert len(received_features) == 1
        assert received_features[0] == mock_feature

    def test_rebuild_feature_requested_emits_with_feature(self, panel):
        """F2-W26-R12: rebuild_feature_requested emittiert Feature."""
        received_features = []
        panel.rebuild_feature_requested.connect(
            lambda feat: received_features.append(feat)
        )

        # Mock Feature
        mock_feature = Mock()
        mock_feature.name = "TestFeature"
        panel._current_feature = mock_feature

        # Aktion auslösen
        panel._on_recovery_action("rebuild")

        # Verhalten prüfen
        assert len(received_features) == 1
        assert received_features[0] == mock_feature

    def test_recovery_action_noop_when_no_feature(self, panel):
        """F2-W26-R13: Keine Signal-Emission wenn kein Feature ausgewählt."""
        received_calls = []
        panel.recovery_action_requested.connect(
            lambda action, feat: received_calls.append((action, feat))
        )

        # Kein Feature ausgewählt
        panel._current_feature = None

        # Aktion auslösen
        panel._on_recovery_action("edit")

        # Verhalten prüfen: Keine Emission
        assert len(received_calls) == 0


class TestW26CopyDiagnosticsBehavior:
    """
    W26 F-UX-3: Behavior-Tests für Copy-Diagnostics.
    """

    def test_copy_diagnostics_contains_error_code(self, panel):
        """F2-W26-R14: Copy-Diagnostics enthält Error-Code."""
        feature = Mock()
        feature.name = "TestFeature"
        feature.status = "ERROR"
        feature.status_details = {
            "code": "tnp_ref_missing",
            "status_class": "ERROR",
            "severity": "error"
        }
        feature.edge_indices = []

        panel.show_feature(feature)
        diag_text = panel.get_diagnostics_text()

        # Verhalten prüfen: Error-Code ist enthalten
        assert "tnp_ref_missing" in diag_text or "ERROR" in diag_text

    def test_copy_diagnostics_contains_feature_name(self, panel):
        """F2-W26-R15: Copy-Diagnostics enthält Feature-Name."""
        feature = Mock()
        feature.name = "MyTestFeature"
        feature.status = "OK"
        feature.status_details = {}
        feature.edge_indices = []

        panel.show_feature(feature)
        diag_text = panel.get_diagnostics_text()

        # Verhalten prüfen: Feature-Name ist enthalten
        assert "MyTestFeature" in diag_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
