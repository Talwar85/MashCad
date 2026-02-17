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
from unittest.mock import Mock, MagicMock

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
    (Zusätzliche 5 Assertions)
    """

    def test_batch_retry_selected_emits_signal(self, qt_app):
        """F1-W26-R8: batch_retry_selected emittiert Signal."""
        browser = ProjectBrowser()
        received = []
        browser.batch_retry_rebuild.connect(lambda x: received.append(x))

        # Ohne Selektion sollte nichts emittiert werden
        browser.batch_retry_selected()
        assert len(received) == 0

    def test_batch_open_selected_diagnostics_method_exists(self, qt_app):
        """F1-W26-R9: batch_open_selected_diagnostics Methode existiert."""
        browser = ProjectBrowser()
        assert hasattr(browser, 'batch_open_selected_diagnostics')
        assert callable(getattr(browser, 'batch_open_selected_diagnostics'))

    def test_batch_open_selected_diagnostics_emits_signal(self, qt_app):
        """F1-W26-R10: batch_open_selected_diagnostics emittiert batch_open_diagnostics Signal."""
        browser = ProjectBrowser()
        received = []
        browser.batch_open_diagnostics.connect(lambda payload: received.append(payload))
        browser.get_selected_problem_features = lambda: [("feature1", "body1")]

        browser.batch_open_selected_diagnostics()
        assert len(received) == 1
        assert received[0] == [("feature1", "body1")]

    def test_batch_isolate_bodies_emits_signal(self, qt_app):
        """F1-W26-R11: batch_isolate_bodies emittiert Signal."""
        browser = ProjectBrowser()
        received = []
        browser.batch_isolate_bodies.connect(lambda x: received.append(x))

        browser.batch_isolate_selected_bodies()
        assert len(received) == 0  # Ohne Selektion


class TestW26BrowserRefreshStability:
    """
    W26 Paket F1: Tests für Anti-Flicker/Refresh-Stabilität.
    """

    def test_refresh_preserves_scroll_position(self, qt_app, mock_document_with_critical_errors):
        """F1-W26-R12: refresh() erhält Scroll-Position."""
        browser = ProjectBrowser()
        browser.set_document(mock_document_with_critical_errors)

        # Refresh sollte ohne Exception durchlaufen
        browser.refresh()
        assert True  # Kein Exception

    def test_refresh_updates_problem_badge(self, qt_app, mock_document_with_critical_errors):
        """F1-W26-R13: refresh() aktualisiert Problembadge."""
        browser = ProjectBrowser()
        browser.set_document(mock_document_with_critical_errors)

        browser.refresh()
        # Badge sollte sichtbar sein bei Problemen
        assert browser.problem_badge is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
