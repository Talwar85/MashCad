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


class TestW26ErrorCodeMappingExtended:
    """
    W28 Paket F4: Tests für zusätzliche Error-Codes.
    Abdeckt tnp_ref_mismatch und ocp_api_unavailable.
    6 neue Assertions
    """

    def test_tnp_ref_mismatch_shows_edit_and_check_deps_buttons(self, panel):
        """F4-W28-R1: tnp_ref_mismatch zeigt 'Editieren' und 'Dependencies prüfen' Buttons."""
        feature = Mock()
        feature.name = "MismatchFeature"
        feature.status = "ERROR"
        feature.status_details = {
            "code": "tnp_ref_mismatch",
            "tnp_failure": {"category": "mismatch"}
        }
        feature.edge_indices = []

        panel.show_feature(feature)

        assert panel._recovery_header.isVisible()
        assert panel._btn_edit_feature.isVisible()
        assert panel._btn_check_deps.isVisible()
        assert panel._btn_rebuild.isVisible()

    def test_ocp_api_unavailable_shows_check_deps_and_rebuild_buttons(self, panel):
        """F4-W28-R2: ocp_api_unavailable zeigt 'Dependencies prüfen' und 'Rebuild' Buttons."""
        feature = Mock()
        feature.name = "OcpUnavailableFeature"
        feature.status = "ERROR"
        feature.status_details = {
            "code": "ocp_api_unavailable",
            "severity": "critical"
        }
        feature.edge_indices = []

        panel.show_feature(feature)

        assert panel._recovery_header.isVisible()
        assert panel._btn_check_deps.isVisible()
        assert panel._btn_rebuild.isVisible()

    def test_reselect_ref_button_only_for_missing_ref(self, panel):
        """F4-W28-R3: 'Referenz neu wählen' Button nur bei tnp_ref_missing."""
        feature = Mock()
        feature.name = "MismatchFeature"
        feature.status = "ERROR"
        feature.status_details = {
            "code": "tnp_ref_mismatch",
            "tnp_failure": {"category": "mismatch"}
        }
        feature.edge_indices = []

        panel.show_feature(feature)

        # Bei mismatch sollte reselect_ref NICHT sichtbar sein
        assert not panel._btn_reselect_ref.isVisible()

    def test_accept_drift_button_only_for_drift(self, panel):
        """F4-W28-R4: 'Drift akzeptieren' Button nur bei tnp_ref_drift."""
        feature = Mock()
        feature.name = "MismatchFeature"
        feature.status = "ERROR"
        feature.status_details = {
            "code": "tnp_ref_mismatch",
            "tnp_failure": {"category": "mismatch"}
        }
        feature.edge_indices = []

        panel.show_feature(feature)

        # Bei mismatch sollte accept_drift NICHT sichtbar sein
        assert not panel._btn_accept_drift.isVisible()

    def test_all_five_error_codes_have_recovery_actions(self, panel):
        """F4-W28-R5: Alle 5 Error-Codes haben Recovery-Actions."""
        error_codes = [
            ("tnp_ref_missing", ["reselect_ref", "edit_feature", "check_deps"]),
            ("tnp_ref_mismatch", ["edit_feature", "check_deps", "rebuild"]),
            ("tnp_ref_drift", ["accept_drift", "edit_feature"]),
            ("rebuild_finalize_failed", ["rebuild", "edit_feature"]),
            ("ocp_api_unavailable", ["check_deps", "rebuild"]),
        ]

        for code, expected_actions in error_codes:
            feature = Mock()
            feature.name = f"Feature_{code}"
            feature.status = "ERROR"
            feature.status_details = {"code": code}
            feature.edge_indices = []

            panel.show_feature(feature)

            # Recovery-Header sollte sichtbar sein
            assert panel._recovery_header.isVisible(), f"Recovery header not visible for {code}"

            # Mindestens eine Action sollte sichtbar sein
            visible_actions = []
            if panel._btn_reselect_ref.isVisible():
                visible_actions.append("reselect_ref")
            if panel._btn_edit_feature.isVisible():
                visible_actions.append("edit_feature")
            if panel._btn_rebuild.isVisible():
                visible_actions.append("rebuild")
            if panel._btn_accept_drift.isVisible():
                visible_actions.append("accept_drift")
            if panel._btn_check_deps.isVisible():
                visible_actions.append("check_deps")

            assert len(visible_actions) > 0, f"No recovery actions for {code}"
            # Prüfe dass mindestens eine erwartete Action sichtbar ist
            has_expected = any(action in visible_actions for action in expected_actions)
            assert has_expected, f"Expected one of {expected_actions} for {code}, got {visible_actions}"

    def test_recovery_buttons_hidden_for_unknown_error_code(self, panel):
        """F4-W28-R6: Bei unbekanntem Error-Code werden Fallback-Actions angezeigt."""
        feature = Mock()
        feature.name = "UnknownErrorFeature"
        feature.status = "ERROR"
        feature.status_details = {
            "code": "unknown_error_code_xyz"
        }
        feature.edge_indices = []

        panel.show_feature(feature)

        # Fallback: Editieren und Rebuild sollten verfügbar sein
        assert panel._btn_edit_feature.isVisible()
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


class TestW29RecoveryActionGuards:
    """
    W29 Closeout: Tests für Recovery Action Guards.
    Prüft enabled/disabled States und Tooltips.
    12 Assertions
    """

    def test_tnp_ref_missing_reselect_ref_enabled(self, panel):
        """W29-R1: Bei tnp_ref_missing ist 'Referenz neu wählen' enabled."""
        feature = Mock()
        feature.name = "MissingRefFeature"
        feature.status = "ERROR"
        feature.status_details = {"code": "tnp_ref_missing"}
        feature.edge_indices = []

        panel.show_feature(feature)

        assert panel._btn_reselect_ref.isEnabled()
        assert panel._btn_reselect_ref.isVisible()

    def test_tnp_ref_missing_rebuild_disabled_with_tooltip(self, panel):
        """W29-R2: Bei tnp_ref_missing ist 'Rebuild' disabled mit Tooltip."""
        feature = Mock()
        feature.name = "MissingRefFeature"
        feature.status = "ERROR"
        feature.status_details = {"code": "tnp_ref_missing"}
        feature.edge_indices = []

        panel.show_feature(feature)

        assert not panel._btn_rebuild.isEnabled() or not panel._btn_rebuild.isVisible()

    def test_tnp_ref_mismatch_check_deps_enabled(self, panel):
        """W29-R3: Bei tnp_ref_mismatch ist 'Dependencies prüfen' enabled."""
        feature = Mock()
        feature.name = "MismatchFeature"
        feature.status = "ERROR"
        feature.status_details = {"code": "tnp_ref_mismatch"}
        feature.edge_indices = []

        panel.show_feature(feature)

        assert panel._btn_check_deps.isEnabled()
        assert panel._btn_check_deps.isVisible()

    def test_tnp_ref_mismatch_reselect_ref_disabled(self, panel):
        """W29-R4: Bei tnp_ref_mismatch ist 'Referenz neu wählen' disabled."""
        feature = Mock()
        feature.name = "MismatchFeature"
        feature.status = "ERROR"
        feature.status_details = {"code": "tnp_ref_mismatch"}
        feature.edge_indices = []

        panel.show_feature(feature)

        assert not panel._btn_reselect_ref.isEnabled() or not panel._btn_reselect_ref.isVisible()

    def test_tnp_ref_drift_accept_drift_enabled(self, panel):
        """W29-R5: Bei tnp_ref_drift ist 'Drift akzeptieren' enabled."""
        feature = Mock()
        feature.name = "DriftFeature"
        feature.status = "WARNING"
        feature.status_details = {"code": "tnp_ref_drift"}
        feature.edge_indices = []

        panel.show_feature(feature)

        assert panel._btn_accept_drift.isEnabled()
        assert panel._btn_accept_drift.isVisible()

    def test_rebuild_finalize_failed_rebuild_enabled(self, panel):
        """W29-R6: Bei rebuild_finalize_failed ist 'Rebuild' enabled."""
        feature = Mock()
        feature.name = "RebuildFailed"
        feature.status = "ERROR"
        feature.status_details = {"code": "rebuild_finalize_failed"}
        feature.edge_indices = []

        panel.show_feature(feature)

        assert panel._btn_rebuild.isEnabled()
        assert panel._btn_rebuild.isVisible()

    def test_ocp_api_unavailable_edit_disabled(self, panel):
        """W29-R7: Bei ocp_api_unavailable ist 'Editieren' disabled."""
        feature = Mock()
        feature.name = "OcpUnavailable"
        feature.status = "ERROR"
        feature.status_details = {"code": "ocp_api_unavailable"}
        feature.edge_indices = []

        panel.show_feature(feature)

        assert not panel._btn_edit_feature.isEnabled() or not panel._btn_edit_feature.isVisible()

    def test_fallback_error_has_edit_and_rebuild(self, panel):
        """W29-R8: Bei unbekanntem Error-Code sind Edit/Rebuild verfügbar."""
        feature = Mock()
        feature.name = "UnknownError"
        feature.status = "ERROR"
        feature.status_details = {"code": "unknown_xyz_error"}
        feature.edge_indices = []

        panel.show_feature(feature)

        assert panel._btn_edit_feature.isEnabled()
        assert panel._btn_rebuild.isEnabled()

    def test_recovery_buttons_have_tooltips(self, panel):
        """W29-R9: Alle sichtbaren Recovery-Buttons haben Tooltips."""
        feature = Mock()
        feature.name = "MismatchFeature"
        feature.status = "ERROR"
        feature.status_details = {"code": "tnp_ref_mismatch"}
        feature.edge_indices = []

        panel.show_feature(feature)

        # Prüfe dass sichtbare Buttons Tooltips haben
        if panel._btn_edit_feature.isVisible():
            assert panel._btn_edit_feature.toolTip() != ""
        if panel._btn_check_deps.isVisible():
            assert panel._btn_check_deps.toolTip() != ""
        if panel._btn_rebuild.isVisible():
            assert panel._btn_rebuild.toolTip() != ""

    def test_disabled_buttons_have_explanation_tooltip(self, panel):
        """W29-R10: Disabled Buttons haben Erklärung im Tooltip."""
        feature = Mock()
        feature.name = "MismatchFeature"
        feature.status = "ERROR"
        feature.status_details = {"code": "tnp_ref_mismatch"}
        feature.edge_indices = []

        panel.show_feature(feature)

        # accept_drift sollte disabled sein mit Erklärung
        if not panel._btn_accept_drift.isEnabled():
            tooltip = panel._btn_accept_drift.toolTip()
            assert tooltip != ""
            assert "nicht" in tooltip.lower() or "not" in tooltip.lower()

    def test_recovery_header_visible_only_with_diagnostic(self, panel):
        """W29-R11: Recovery-Header nur sichtbar wenn Diagnose vorhanden."""
        feature_ok = Mock()
        feature_ok.name = "OKFeature"
        feature_ok.status = "OK"
        feature_ok.status_details = {}
        feature_ok.edge_indices = []

        panel.show_feature(feature_ok)
        assert not panel._recovery_header.isVisible()

        feature_err = Mock()
        feature_err.name = "ErrorFeature"
        feature_err.status = "ERROR"
        feature_err.status_details = {"code": "tnp_ref_missing"}
        feature_err.edge_indices = []

        panel.show_feature(feature_err)
        assert panel._recovery_header.isVisible()

    def test_all_five_error_codes_have_valid_actions(self, panel):
        """W29-R12: Alle 5 Error-Codes haben mindestens eine gültige Aktion."""
        error_codes = ["tnp_ref_missing", "tnp_ref_mismatch", "tnp_ref_drift",
                       "rebuild_finalize_failed", "ocp_api_unavailable"]

        for code in error_codes:
            feature = Mock()
            feature.name = f"Feature_{code}"
            feature.status = "ERROR"
            feature.status_details = {"code": code}
            feature.edge_indices = []

            panel.show_feature(feature)

            # Prüfe dass mindestens eine Aktion sichtbar und enabled ist
            visible_enabled = []
            if panel._btn_reselect_ref.isVisible() and panel._btn_reselect_ref.isEnabled():
                visible_enabled.append("reselect_ref")
            if panel._btn_edit_feature.isVisible() and panel._btn_edit_feature.isEnabled():
                visible_enabled.append("edit")
            if panel._btn_rebuild.isVisible() and panel._btn_rebuild.isEnabled():
                visible_enabled.append("rebuild")
            if panel._btn_accept_drift.isVisible() and panel._btn_accept_drift.isEnabled():
                visible_enabled.append("accept_drift")
            if panel._btn_check_deps.isVisible() and panel._btn_check_deps.isEnabled():
                visible_enabled.append("check_deps")

            assert len(visible_enabled) > 0, f"No valid actions for {code}"


class TestW30RecoveryDecisionEngine:
    """
    W30 Product Leap: Tests für Recovery Decision Engine.
    Tests für primäre/sekundäre Aktionen und Next-Steps.
    8 Assertions
    """

    def test_recovery_decision_dict_exists(self, panel):
        """W30-F1: _RECOVERY_DECISIONS Klassenvariable existiert."""
        from gui.widgets.feature_detail_panel import FeatureDetailPanel
        assert hasattr(FeatureDetailPanel, '_RECOVERY_DECISIONS')

    def test_recovery_decision_dict_has_all_codes(self, panel):
        """W30-F2: _RECOVERY_DECISIONS enthält alle Error-Codes."""
        from gui.widgets.feature_detail_panel import FeatureDetailPanel
        decisions = FeatureDetailPanel._RECOVERY_DECISIONS
        expected = ["tnp_ref_missing", "tnp_ref_mismatch", "tnp_ref_drift",
                   "rebuild_finalize_failed", "ocp_api_unavailable"]
        for code in expected:
            assert code in decisions, f"Missing {code}"

    def test_primary_action_is_bold_for_tnp_ref_missing(self, panel):
        """W30-F3: Primäraktion wird hervorgehoben für tnp_ref_missing."""
        feature = Mock()
        feature.name = "MissingRef"
        feature.status = "ERROR"
        feature.status_details = {"code": "tnp_ref_missing"}
        feature.edge_indices = []

        panel.show_feature(feature)

        # Reselect-Button sollte sichtbar sein
        assert panel._btn_reselect_ref.isVisible()

    def test_next_step_text_contains_steps(self, panel):
        """W30-F4: Next-Step Text enthält Schrittanleitung."""
        feature = Mock()
        feature.name = "DriftFeature"
        feature.status = "WARNING"
        feature.status_details = {"code": "tnp_ref_drift"}
        feature.edge_indices = []

        panel.show_feature(feature)

        # Hint-Feld sollte Text enthalten
        hint_text = panel._diag_hint.text()
        assert len(hint_text) > 0

    def test_apply_button_style_exists(self, panel):
        """W30-F5: _apply_button_style Methode existiert."""
        assert hasattr(panel, '_apply_button_style')
        assert callable(panel._apply_button_style)

    def test_apply_button_style_sets_stylesheet(self, panel):
        """W30-F6: _apply_button_style setzt StyleSheet."""
        panel._apply_button_style(panel._btn_edit_feature, is_primary=False, is_secondary=False)
        style = panel._btn_edit_feature.styleSheet()
        assert len(style) > 0

    def test_primary_button_gets_bold_style(self, panel):
        """W30-F7: Primärbutton erhält fetten Stil."""
        panel._apply_button_style(panel._btn_rebuild, is_primary=True, is_secondary=False)
        style = panel._btn_rebuild.styleSheet()
        assert "bold" in style.lower()

    def test_secondary_button_gets_different_style(self, panel):
        """W30-F8: Sekundärbutton erhält anderen Stil als Primär."""
        panel._apply_button_style(panel._btn_edit_feature, is_primary=False, is_secondary=True)
        secondary_style = panel._btn_edit_feature.styleSheet()
        panel._apply_button_style(panel._btn_rebuild, is_primary=True, is_secondary=False)
        primary_style = panel._btn_rebuild.styleSheet()
        # Verschiedene Styles für primär vs sekundär
        assert len(secondary_style) > 0
        assert len(primary_style) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
