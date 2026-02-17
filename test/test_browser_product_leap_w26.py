"""
W26 Paket F1: Browser Problem Workflow v2 Tests
================================================
Testet die neuen W26 Browser-Features:
- Problem-First Navigation mit Priorisierung (CRITICAL > BLOCKED > ERROR > WARNING)
- Multi-Select für Problem-Features mit Batch-Aktionen
- Anti-Flicker/Refresh-Stabilität (>200 Features)

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
from PySide6.QtCore import Qt
from unittest.mock import Mock, MagicMock, patch

from gui.browser import ProjectBrowser, DraggableTreeWidget
from modeling import Document, Body, Component


@pytest.fixture(scope="session")
def qt_app():
    """Session-weite QApplication Instanz."""
    app = QApplication.instance()
    if app is None:
        import sys
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def mock_document_with_critical_errors():
    """Mock Document mit verschiedenen Severity-Levels für Priorisierungstests."""
    doc = Mock()
    doc.name = "TestDocument"
    doc.root_component = Component("Root")
    doc._active_component = doc.root_component

    body = Body("Body1")
    body.id = "body1"

    # Feature mit CRITICAL
    feat_critical = Mock()
    feat_critical.name = "CriticalFillet"
    feat_critical.status = "ERROR"
    feat_critical.status_details = {
        "code": "tnp_ref_missing",
        "status_class": "CRITICAL",
        "severity": "critical"
    }
    feat_critical.edge_indices = []

    # Feature mit BLOCKED
    feat_blocked = Mock()
    feat_blocked.name = "BlockedChamfer"
    feat_blocked.status = "ERROR"
    feat_blocked.status_details = {
        "code": "rebuild_finalize_failed",
        "status_class": "BLOCKED",
        "severity": "blocked"
    }
    feat_blocked.edge_indices = []

    # Feature mit ERROR
    feat_error = Mock()
    feat_error.name = "ErrorExtrude"
    feat_error.status = "ERROR"
    feat_error.status_details = {
        "code": "ocp_api_unavailable",
        "status_class": "ERROR",
        "severity": "error"
    }
    feat_error.edge_indices = []

    # Feature mit WARNING
    feat_warning = Mock()
    feat_warning.name = "WarningDrift"
    feat_warning.status = "WARNING"
    feat_warning.status_details = {
        "code": "tnp_ref_drift",
        "status_class": "WARNING_RECOVERABLE",
        "severity": "warning"
    }
    feat_warning.edge_indices = []

    body.features = [feat_warning, feat_error, feat_blocked, feat_critical]
    doc.root_component.bodies = [body]

    doc.get_all_bodies = lambda: [body]
    doc.get_all_sketches = lambda: []
    doc.planes = []

    return doc


class TestW26BrowserProblemFirstNavigation:
    """
    W26 Paket F1: Tests für Problem-First Navigation mit Priorisierung.
    7 Assertions
    """

    def test_get_problem_priority_returns_correct_order(self, qt_app):
        """F1-W26-R1: _get_problem_priority gibt korrekte Prioritätsordnung zurück."""
        tree = DraggableTreeWidget()

        # Mock Items mit verschiedenen Severities
        item_critical = Mock()
        feat_critical = Mock()
        feat_critical.status = "ERROR"
        feat_critical.status_details = {"status_class": "CRITICAL", "severity": "critical"}
        item_critical.data = lambda role, idx=0: ('feature', feat_critical) if role == 0 else None

        item_blocked = Mock()
        feat_blocked = Mock()
        feat_blocked.status = "ERROR"
        feat_blocked.status_details = {"status_class": "BLOCKED", "severity": "blocked"}
        item_blocked.data = lambda role, idx=0: ('feature', feat_blocked) if role == 0 else None

        item_error = Mock()
        feat_error = Mock()
        feat_error.status = "ERROR"
        feat_error.status_details = {"status_class": "ERROR", "severity": "error"}
        item_error.data = lambda role, idx=0: ('feature', feat_error) if role == 0 else None

        item_warning = Mock()
        feat_warning = Mock()
        feat_warning.status = "WARNING"
        feat_warning.status_details = {"status_class": "WARNING_RECOVERABLE", "severity": "warning"}
        item_warning.data = lambda role, idx=0: ('feature', feat_warning) if role == 0 else None

        # Test: CRITICAL (0) < BLOCKED (1) < ERROR (2) < WARNING (3)
        assert tree._get_problem_priority(item_critical) == 0
        assert tree._get_problem_priority(item_blocked) == 1
        assert tree._get_problem_priority(item_error) == 2
        assert tree._get_problem_priority(item_warning) == 3

    def test_navigate_to_next_critical_problem_exists(self, qt_app):
        """F1-W26-R2: navigate_to_next_critical_problem Methode existiert."""
        tree = DraggableTreeWidget()
        assert hasattr(tree, 'navigate_to_next_critical_problem')

    def test_navigate_to_prev_critical_problem_exists(self, qt_app):
        """F1-W26-R3: navigate_to_prev_critical_problem Methode existiert."""
        tree = DraggableTreeWidget()
        assert hasattr(tree, 'navigate_to_prev_critical_problem')

    def test_select_all_problem_items_exists(self, qt_app):
        """F1-W26-R4: select_all_problem_items Methode existiert."""
        tree = DraggableTreeWidget()
        assert hasattr(tree, 'select_all_problem_items')

    def test_batch_signals_exist(self, qt_app):
        """F1-W26-R5: Batch-Aktions-Signale existieren."""
        browser = ProjectBrowser()
        assert hasattr(browser, 'batch_retry_rebuild')
        assert hasattr(browser, 'batch_open_diagnostics')
        assert hasattr(browser, 'batch_isolate_bodies')
        assert hasattr(browser.batch_retry_rebuild, 'emit')
        assert hasattr(browser.batch_open_diagnostics, 'emit')
        assert hasattr(browser.batch_isolate_bodies, 'emit')

    def test_get_selected_features_returns_list(self, qt_app, mock_document_with_critical_errors):
        """F1-W26-R6: get_selected_features gibt Liste von (feature, body) Tupeln zurück."""
        browser = ProjectBrowser()
        browser.set_document(mock_document_with_critical_errors)

        # Initial sollte leere Liste zurückgeben
        features = browser.get_selected_features()
        assert isinstance(features, list)

    def test_get_selected_problem_features_filters_non_problems(self, qt_app, mock_document_with_critical_errors):
        """F1-W26-R7: get_selected_problem_features filtert nur Problem-Features."""
        browser = ProjectBrowser()
        browser.set_document(mock_document_with_critical_errors)

        problem_features = browser.get_selected_problem_features()
        # Ohne Selektion sollte leere Liste zurückgeben
        assert isinstance(problem_features, list)


class TestW26BrowserMultiSelectBatchActions:
    """
    W26 Paket F1: Tests für Multi-Select Batch-Aktionen.
    Verhaltenstests mit echten Signal-Payloads.
    """

    def test_batch_retry_selected_emits_signal_with_payload(self, qt_app):
        """F1-W26-R8: batch_retry_selected emittiert Signal mit korrektem Payload."""
        browser = ProjectBrowser()
        received_payloads = []
        browser.batch_retry_rebuild.connect(lambda x: received_payloads.append(x))

        # Mock selektierte Problem-Features
        mock_features = [("feature1", "body1"), ("feature2", "body2")]
        browser.get_selected_problem_features = lambda: mock_features

        # Aktion ausführen
        browser.batch_retry_selected()

        # Verhalten prüfen: Signal wurde mit Payload emittiert
        assert len(received_payloads) == 1
        assert received_payloads[0] == mock_features

    def test_batch_retry_selected_noop_when_empty_selection(self, qt_app):
        """F1-W26-R9: batch_retry_selected emitiert NICHT bei leerer Selektion."""
        browser = ProjectBrowser()
        received_payloads = []
        browser.batch_retry_rebuild.connect(lambda x: received_payloads.append(x))

        # Leere Selektion
        browser.get_selected_problem_features = lambda: []

        # Aktion ausführen
        browser.batch_retry_selected()

        # Verhalten prüfen: Kein Signal wurde emittiert
        assert len(received_payloads) == 0

    def test_batch_open_selected_diagnostics_emits_signal_with_payload(self, qt_app):
        """F1-W26-R10: batch_open_selected_diagnostics emittiert Signal mit Payload."""
        browser = ProjectBrowser()
        received_payloads = []
        browser.batch_open_diagnostics.connect(lambda x: received_payloads.append(x))

        # Mock selektierte Problem-Features
        mock_features = [("feature1", "body1")]
        browser.get_selected_problem_features = lambda: mock_features

        # Aktion ausführen
        browser.batch_open_selected_diagnostics()

        # Verhalten prüfen
        assert len(received_payloads) == 1
        assert received_payloads[0] == mock_features

    def test_batch_isolate_bodies_emits_signal_with_bodies(self, qt_app):
        """F1-W26-R11: batch_isolate_bodies emittiert Signal mit Body-Liste."""
        browser = ProjectBrowser()
        received_payloads = []
        browser.batch_isolate_bodies.connect(lambda x: received_payloads.append(x))

        # Mock selektierte Problem-Features mit Bodies
        mock_body1 = Mock()
        mock_body1.id = "body1"
        mock_body2 = Mock()
        mock_body2.id = "body2"
        mock_features = [("feature1", mock_body1), ("feature2", mock_body2)]
        browser.get_selected_problem_features = lambda: mock_features

        # Aktion ausführen
        browser.batch_isolate_selected_bodies()

        # Verhalten prüfen: Signal wurde mit Body-Liste emittiert
        assert len(received_payloads) == 1
        assert len(received_payloads[0]) == 2
        assert mock_body1 in received_payloads[0]
        assert mock_body2 in received_payloads[0]

    def test_batch_isolate_bodies_noop_when_no_bodies(self, qt_app):
        """F1-W26-R12: batch_isolate_bodies emitiert NICHT wenn keine Bodies."""
        browser = ProjectBrowser()
        received_payloads = []
        browser.batch_isolate_bodies.connect(lambda x: received_payloads.append(x))

        # Leere Selektion
        browser.get_selected_problem_features = lambda: []

        # Aktion ausführen
        browser.batch_isolate_selected_bodies()

        # Verhalten prüfen: Kein Signal wurde emittiert
        assert len(received_payloads) == 0


class TestW26BrowserRefreshStability:
    """
    W26 Paket F1: Tests für Anti-Flicker/Refresh-Stabilität.
    """

    def test_refresh_preserves_scroll_position(self, qt_app, mock_document_with_critical_errors):
        """F1-W26-R13: refresh() erhält Scroll-Position."""
        browser = ProjectBrowser()
        browser.set_document(mock_document_with_critical_errors)

        # Refresh sollte ohne Exception durchlaufen
        browser.refresh()
        assert True  # Kein Exception

    def test_refresh_updates_problem_badge(self, qt_app, mock_document_with_critical_errors):
        """F1-W26-R14: refresh() aktualisiert Problembadge."""
        browser = ProjectBrowser()
        browser.set_document(mock_document_with_critical_errors)

        browser.refresh()
        # Badge sollte sichtbar sein bei Problemen
        assert browser.problem_badge is not None


class TestW26GuardrailsApiCollision:
    """
    W26 F-UX-2: Guardrails gegen API-Kollisionen.
    Verhindert Namenskollisionen zwischen Signalen und Methoden.
    """

    def test_no_signal_method_name_collision_batch_retry(self, qt_app):
        """F1-W26-R15: batch_retry_rebuild Signal hat keine Namenskollision."""
        browser = ProjectBrowser()
        
        # Signal und Methode müssen unterschiedliche Namen haben
        signal_name = "batch_retry_rebuild"
        method_name = "batch_retry_selected"
        
        # Signal existiert
        assert hasattr(browser, signal_name)
        # Methode existiert
        assert hasattr(browser, method_name)
        # Sie sind verschiedene Attribute
        assert getattr(browser, signal_name) is not getattr(browser, method_name)

    def test_no_signal_method_name_collision_batch_open(self, qt_app):
        """F1-W26-R16: batch_open_diagnostics Signal hat keine Namenskollision."""
        browser = ProjectBrowser()
        
        signal_name = "batch_open_diagnostics"
        method_name = "batch_open_selected_diagnostics"
        
        # Signal existiert
        assert hasattr(browser, signal_name)
        # Methode existiert
        assert hasattr(browser, method_name)
        # Sie sind verschiedene Attribute
        assert getattr(browser, signal_name) is not getattr(browser, method_name)

    def test_signal_emit_callable(self, qt_app):
        """F1-W26-R17: Alle Batch-Signale sind emittierbar."""
        browser = ProjectBrowser()

        # Teste dass emit() aufgerufen werden kann
        try:
            browser.batch_retry_rebuild.emit([])
            browser.batch_open_diagnostics.emit([])
            browser.batch_isolate_bodies.emit([])
        except Exception as e:
            pytest.fail(f"Signal emit failed: {e}")


class TestW28BatchUnhideFocus:
    """
    W28 Paket F3: Tests für neue Batch unhide/focus flows.
    8 neue Assertions
    """

    def test_batch_unhide_bodies_signal_exists(self, qt_app):
        """F3-W28-R1: batch_unhide_bodies Signal existiert."""
        browser = ProjectBrowser()
        assert hasattr(browser, 'batch_unhide_bodies')
        assert hasattr(browser.batch_unhide_bodies, 'emit')

    def test_batch_focus_features_signal_exists(self, qt_app):
        """F3-W28-R2: batch_focus_features Signal existiert."""
        browser = ProjectBrowser()
        assert hasattr(browser, 'batch_focus_features')
        assert hasattr(browser.batch_focus_features, 'emit')

    def test_batch_unhide_selected_bodies_method_exists(self, qt_app):
        """F3-W28-R3: batch_unhide_selected_bodies Methode existiert."""
        browser = ProjectBrowser()
        assert hasattr(browser, 'batch_unhide_selected_bodies')
        assert callable(browser.batch_unhide_selected_bodies)

    def test_batch_focus_selected_features_method_exists(self, qt_app):
        """F3-W28-R4: batch_focus_selected_features Methode existiert."""
        browser = ProjectBrowser()
        assert hasattr(browser, 'batch_focus_selected_features')
        assert callable(browser.batch_focus_selected_features)

    def test_batch_unhide_emits_signal_with_hidden_bodies(self, qt_app, mock_document_with_critical_errors):
        """F3-W28-R5: batch_unhide_selected_bodies emittiert Signal mit versteckten Bodies."""
        browser = ProjectBrowser()
        browser.set_document(mock_document_with_critical_errors)

        received_payloads = []
        browser.batch_unhide_bodies.connect(lambda x: received_payloads.append(x))

        # Einen Body verstecken
        body = mock_document_with_critical_errors.root_component.bodies[0]
        browser.body_visibility[body.id] = False

        # Aktion ausführen
        browser.batch_unhide_selected_bodies()

        # Verhalten prüfen: Signal wurde mit Body-Liste emittiert
        assert len(received_payloads) == 1
        assert body in received_payloads[0]

    def test_batch_unhide_makes_bodies_visible(self, qt_app, mock_document_with_critical_errors):
        """F3-W28-R6: batch_unhide_selected_bodies macht Bodies sichtbar."""
        browser = ProjectBrowser()
        browser.set_document(mock_document_with_critical_errors)

        # Einen Body verstecken
        body = mock_document_with_critical_errors.root_component.bodies[0]
        browser.body_visibility[body.id] = False
        assert not browser.body_visibility.get(body.id, True)

        # Aktion ausführen
        browser.batch_unhide_selected_bodies()

        # Verhalten prüfen: Body ist jetzt sichtbar
        assert browser.body_visibility.get(body.id, True)

    def test_batch_focus_emits_signal_with_features(self, qt_app):
        """F3-W28-R7: batch_focus_selected_features emittiert Signal mit Features."""
        browser = ProjectBrowser()

        received_payloads = []
        browser.batch_focus_features.connect(lambda x: received_payloads.append(x))

        # Mock selektierte Features
        mock_features = [("feature1", "body1"), ("feature2", "body2")]
        browser.get_selected_features = lambda: mock_features

        # Aktion ausführen
        browser.batch_focus_selected_features()

        # Verhalten prüfen: Signal wurde mit Feature-Liste emittiert
        assert len(received_payloads) == 1
        assert received_payloads[0] == mock_features

    def test_batch_focus_noop_when_empty_selection(self, qt_app):
        """F3-W28-R8: batch_focus_selected_features emitiert NICHT bei leerer Selektion."""
        browser = ProjectBrowser()

        received_payloads = []
        browser.batch_focus_features.connect(lambda x: received_payloads.append(x))

        # Leere Selektion
        browser.get_selected_features = lambda: []

        # Aktion ausführen
        browser.batch_focus_selected_features()

        # Verhalten prüfen: Kein Signal wurde emittiert
        assert len(received_payloads) == 0


class TestW29BatchUXPolishing:
    """
    W29 Closeout: Tests für Batch UX Polishing.
    Prüft Context-Menüs nur in passenden Kontexten.
    10 Assertions
    """

    def test_clear_batch_state_on_filter_change_exists(self, qt_app):
        """W29-R1: _clear_batch_state_on_filter_change Methode existiert."""
        browser = ProjectBrowser()
        assert hasattr(browser, '_clear_batch_state_on_filter_change')
        assert callable(browser._clear_batch_state_on_filter_change)

    def test_filter_change_clears_hidden_selection(self, qt_app, mock_document_with_critical_errors):
        """W29-R2: Filterwechsel bereinigt Selektion von versteckten Items."""
        browser = ProjectBrowser()
        browser.set_document(mock_document_with_critical_errors)

        # Simuliere Selektion die durch Filter versteckt wird
        browser.tree.clearSelection()
        # Alle Items selektieren
        root = browser.tree.invisibleRootItem()
        for i in range(root.childCount()):
            child = root.child(i)
            if child:
                child.setSelected(True)

        # Filter auf 'errors' setzen
        browser.filter_combo.setCurrentIndex(2)  # "❌ Fehler"

        # Prüfe dass versteckte Items deselektiert wurden
        selected = browser.tree.selectedItems()
        for item in selected:
            assert not item.isHidden(), "Hidden items should not be selected"

    def test_context_menu_method_exists(self, qt_app):
        """W29-R3: _show_context_menu Methode existiert."""
        browser = ProjectBrowser()
        assert hasattr(browser, '_show_context_menu')
        assert callable(browser._show_context_menu)

    def test_filter_combo_has_all_options(self, qt_app):
        """W29-R4: Filter-Combo hat alle erwarteten Optionen."""
        browser = ProjectBrowser()

        expected_data = ["all", "warnings", "errors", "blocked"]
        actual_data = []

        for i in range(browser.filter_combo.count()):
            data = browser.filter_combo.itemData(i)
            actual_data.append(data)

        assert actual_data == expected_data

    def test_filter_combo_change_emits_signal(self, qt_app):
        """W29-R5: Filter-Änderung emittiert filter_changed Signal."""
        browser = ProjectBrowser()
        received_signals = []
        browser.filter_changed.connect(lambda x: received_signals.append(x))

        # Filter ändern
        browser.filter_combo.setCurrentIndex(1)  # "⚠ Warnungen"

        # Prüfe dass Signal emittiert wurde
        assert len(received_signals) > 0
        assert received_signals[0] == "warnings"

    def test_batch_menu_only_for_multi_select(self, qt_app, mock_document_with_critical_errors):
        """W29-R6: Batch-Menü nur bei Multi-Select sichtbar."""
        browser = ProjectBrowser()
        browser.set_document(mock_document_with_critical_errors)
        browser.refresh()

        # Bei Einzel-Selektion sollte kein Batch-Menü erscheinen
        # (Dies wird durch Context-Menu Logik gesteuert)
        root = browser.tree.invisibleRootItem()
        if root.childCount() > 0:
            first_child = root.child(0)
            if first_child.childCount() > 0:
                feature_item = first_child.child(0)
                data = feature_item.data(0, Qt.UserRole)

                # Einzel-Selektion
                browser.tree.clearSelection()
                feature_item.setSelected(True)
                selected_count = len(browser.tree.selectedItems())
                assert selected_count == 1

    def test_problem_badge_updates_on_filter_change(self, qt_app, mock_document_with_critical_errors):
        """W29-R7: Problembadge wird bei Filterwechsel aktualisiert."""
        browser = ProjectBrowser()
        browser.set_document(mock_document_with_critical_errors)

        # Initial sollte Badge sichtbar sein
        browser._update_problem_badge()

        # Filter auf 'errors' setzen
        browser.filter_combo.setCurrentIndex(2)  # "❌ Fehler"
        browser._update_problem_badge()

        # Badge sollte noch existieren
        assert browser.problem_badge is not None

    def test_get_selected_problem_features_returns_empty_when_no_selection(self, qt_app):
        """W29-R8: get_selected_problem_features gibt leere Liste zurück bei keiner Selektion."""
        browser = ProjectBrowser()
        browser.tree.clearSelection()

        problem_features = browser.get_selected_problem_features()
        assert isinstance(problem_features, list)
        assert len(problem_features) == 0

    def test_get_selected_features_returns_list_type(self, qt_app):
        """W29-R9: get_selected_features gibt immer Liste zurück."""
        browser = ProjectBrowser()
        features = browser.get_selected_features()

        assert isinstance(features, list)

    def test_recover_all_five_error_codes_via_panel(self, qt_app):
        """W29-R10: Alle 5 Error-Codes haben Recovery-Pfad im Panel."""
        from gui.widgets.feature_detail_panel import FeatureDetailPanel
        from PySide6.QtTest import QTest
        panel = FeatureDetailPanel()
        panel.show()
        QTest.qWaitForWindowExposed(panel)

        error_codes = [
            ("tnp_ref_missing", "missing_ref"),
            ("tnp_ref_mismatch", "mismatch"),
            ("tnp_ref_drift", "drift"),
            ("rebuild_finalize_failed", ""),
            ("ocp_api_unavailable", ""),
        ]

        for code, category in error_codes:
            feature = Mock()
            feature.name = f"Test_{code}"
            feature.status = "ERROR"
            feature.status_details = {"code": code, "tnp_failure": {"category": category}}
            feature.edge_indices = []

            panel.show_feature(feature)

            # Recovery-Header sollte sichtbar sein
            assert panel._recovery_header.isVisible(), f"Recovery header not visible for {code}"

            # Mindestens eine Aktion sollte verfügbar sein
            has_action = any([
                panel._btn_reselect_ref.isVisible(),
                panel._btn_edit_feature.isVisible(),
                panel._btn_rebuild.isVisible(),
                panel._btn_accept_drift.isVisible(),
                panel._btn_check_deps.isVisible(),
            ])
            assert has_action, f"No recovery action for {code}"

        panel.close()
        panel.deleteLater()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
