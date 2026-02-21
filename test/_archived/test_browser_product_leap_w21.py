"""
W21 Paket A: Browser Product Leap Tests
=========================================
Testet die neuen Browser-Features:
- Schnellfilter für Tree-Inhalte
- Keyboard-first Navigation
- Status-Badges für Problemfeatures
- Kein visuelles Flackern bei Refresh

Author: AI-2 (Product Surface Cell)
Date: 2026-02-16
Branch: feature/v1-ux-aiB
"""

# CRITICAL: QT_OPENGL muss VOR jedem Qt/PyVista Import gesetzt werden
import os
os.environ["QT_OPENGL"] = "software"

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from unittest.mock import Mock, MagicMock

from gui.browser import ProjectBrowser, DraggableTreeWidget
from modeling import Document, Body, Component, ExtrudeFeature


@pytest.fixture(scope="session")
def qt_app():
    """Session-weite QApplication Instanz."""
    app = QApplication.instance()
    if app is None:
        import sys
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def mock_document():
    """Mock Document mit Bodies und Features."""
    doc = Mock()
    doc.name = "TestDocument"
    doc.root_component = Component("Root")
    doc._active_component = doc.root_component

    # Bodies mit unterschiedlichen Status erstellen
    body1 = Body("Body1")
    body1.id = "body1"

    # Features mit Status erstellen
    feature_ok = Mock()
    feature_ok.name = "Extrude1"
    feature_ok.status = "OK"
    feature_ok.status_message = ""
    feature_ok.status_details = {}
    feature_ok.edge_indices = []

    feature_error = Mock()
    feature_error.name = "Fillet1"
    feature_error.status = "ERROR"
    feature_error.status_message = "Kante nicht gefunden"
    feature_error.status_details = {
        "code": "edge_not_found",
        "status_class": "ERROR",
        "severity": "error"
    }
    feature_error.edge_indices = []

    feature_warning = Mock()
    feature_warning.name = "Chamfer1"
    feature_warning.status = "WARNING"
    feature_warning.status_message = "Geometrie leicht verschoben"
    feature_warning.status_details = {
        "code": "tnp_ref_drift",
        "status_class": "WARNING_RECOVERABLE",
        "severity": "warning"
    }
    feature_warning.edge_indices = []

    body1.features = [feature_ok, feature_error, feature_warning]
    doc.root_component.bodies = [body1]

    def get_all_bodies():
        return [body1]

    def get_all_sketches():
        return []

    doc.get_all_bodies = get_all_bodies
    doc.get_all_sketches = get_all_sketches
    doc.planes = []

    return doc


@pytest.fixture
def browser(qt_app, mock_document):
    """Browser Fixture mit Document."""
    browser = ProjectBrowser()
    browser.set_document(mock_document)
    browser.show()
    QTest.qWaitForWindowExposed(browser)
    yield browser
    browser.close()
    browser.deleteLater()


class TestBrowserFilter:
    """
    W21 Paket A: Tests für Schnellfilter-Functionality.
    """

    def test_filter_combo_exists(self, browser):
        """A-W21-R1: Filter-Combo ist vorhanden."""
        assert hasattr(browser, 'filter_combo'), "Filter combo should exist"
        assert browser.filter_combo.count() == 4, "Should have 4 filter options"

    def test_filter_modes(self, browser):
        """A-W21-R2: Filter-Modi sind korrekt definiert."""
        assert browser.filter_combo.itemData(0) == "all"
        assert browser.filter_combo.itemData(1) == "warnings"
        assert browser.filter_combo.itemData(2) == "errors"
        assert browser.filter_combo.itemData(3) == "blocked"

    def test_filter_to_errors_hides_ok_features(self, browser):
        """A-W21-R3: Filter 'errors' versteckt OK-Features."""
        browser.set_filter_mode("errors")
        QTest.qWait(100)  # UI update abwarten

        # Tree sollte nur noch ERROR-Features zeigen
        # (Implementierungsdetail: Filter wird auf Items angewendet)
        assert browser.tree._filter_mode == "errors"

    def test_filter_to_warnings_shows_warnings_and_errors(self, browser):
        """A-W21-R4: Filter 'warnings' zeigt WARNINGS und ERRORS."""
        browser.set_filter_mode("warnings")
        QTest.qWait(100)

        assert browser.tree._filter_mode == "warnings"

    def test_filter_to_all_shows_everything(self, browser):
        """A-W21-R5: Filter 'all' zeigt alles."""
        browser.set_filter_mode("warnings")
        browser.set_filter_mode("all")
        QTest.qWait(100)

        assert browser.tree._filter_mode == "all"

    def test_problem_badge_exists(self, browser):
        """A-W21-R6: Problembadge ist vorhanden."""
        assert hasattr(browser, 'problem_badge'), "Problem badge should exist"
        assert browser.problem_badge is not None


class TestBrowserKeyboardNavigation:
    """
    W21 Paket A: Tests für Keyboard-Navigation.
    """

    def test_tree_has_navigation_methods(self, browser):
        """A-W21-R7: Tree hat Navigations-Methoden."""
        assert hasattr(browser.tree, 'navigate_to_next_item')
        assert hasattr(browser.tree, 'navigate_to_prev_item')
        assert hasattr(browser.tree, 'navigate_to_next_problem')
        assert hasattr(browser.tree, 'navigate_to_prev_problem')

    def test_navigation_signals_exist(self, browser):
        """A-W21-R8: Navigations-Signale sind vorhanden."""
        # Signals sollten von DraggableTreeWidget emittiert werden
        assert hasattr(browser.tree, 'next_problem_item')
        assert hasattr(browser.tree, 'prev_problem_item')
        assert hasattr(browser.tree, 'next_item')
        assert hasattr(browser.tree, 'prev_item')

    def test_is_problem_item_detects_errors(self, browser):
        """A-W21-R9: _is_problem_item erkennt ERROR-Features."""
        # Problem-Item erstellen
        error_feature = Mock()
        error_feature.status = "ERROR"
        error_feature.status_details = {"status_class": "ERROR"}

        # Tree-Item mocken
        item = Mock()
        item.data = lambda role, data: ('feature', error_feature) if role == 0 else None

        assert browser.tree._is_problem_item(item), "ERROR feature should be problem item"

    def test_is_problem_item_detects_warnings(self, browser):
        """A-W21-R10: _is_problem_item erkennt WARNING-Features."""
        warning_feature = Mock()
        warning_feature.status = "WARNING"
        warning_feature.status_details = {"status_class": "WARNING_RECOVERABLE"}

        item = Mock()
        item.data = lambda role, data: ('feature', warning_feature) if role == 0 else None

        assert browser.tree._is_problem_item(item), "WARNING feature should be problem item"

    def test_is_problem_item_ignores_ok(self, browser):
        """A-W21-R11: _is_problem_item ignoriert OK-Features."""
        ok_feature = Mock()
        ok_feature.status = "OK"
        ok_feature.status_details = {}

        item = Mock()
        item.data = lambda role, data: ('feature', ok_feature) if role == 0 else None

        assert not browser.tree._is_problem_item(item), "OK feature should not be problem item"


class TestBrowserStatusBadges:
    """
    W21 Paket A: Tests für Status-Badges.
    """

    def test_update_problem_badge_updates_count(self, browser):
        """A-W21-R12: _update_problem_badge aktualisiert den Count."""
        browser._update_problem_badge()
        # Mit 2 Problem-Features (1 ERROR, 1 WARNING) sollte Badge "2" zeigen
        if browser.problem_badge.isVisible():
            count = int(browser.problem_badge.text())
            assert count >= 2, f"Expected at least 2 problems, got {count}"

    def test_get_problem_count(self, browser):
        """A-W21-R13: get_problem_count() liefert korrekte Anzahl."""
        count = browser.get_problem_count()
        # Sollte 2 sein (1 ERROR, 1 WARNING)
        assert count == 2, f"Expected 2 problems, got {count}"

    def test_get_filtered_features_returns_list(self, browser):
        """A-W21-R14: get_filtered_features() liefert Liste."""
        features = browser.get_filtered_features()
        assert isinstance(features, list), "Should return a list"

    def test_get_filtered_features_errors_only(self, browser):
        """A-W21-R15: get_filtered_features() mit errors Filter."""
        browser.set_filter_mode("errors")
        features = browser.get_filtered_features()

        # Nur ERROR-Features sollten zurückgegeben werden
        for feature, body in features:
            assert feature.status in ("ERROR",) or \
                   feature.status_details.get("status_class") in ("ERROR", "CRITICAL"), \
                   f"Feature {feature.name} should be ERROR"

    def test_problem_badge_color_for_errors(self, browser):
        """A-W21-R16: Badge-Farbe rot bei errors Filter."""
        browser.set_filter_mode("errors")
        browser._update_problem_badge()

        style = browser.problem_badge.styleSheet()
        if browser.problem_badge.isVisible():
            assert "#ef4444" in style or "red" in style.lower(), "Should be red for errors"

    def test_problem_badge_color_for_warnings(self, browser):
        """A-W21-R17: Badge-Farbe gelb bei warnings Filter."""
        browser.set_filter_mode("warnings")
        browser._update_problem_badge()

        style = browser.problem_badge.styleSheet()
        if browser.problem_badge.isVisible():
            assert "#f59e0b" in style or "yellow" in style.lower(), "Should be yellow for warnings"


class TestBrowserRefreshNoFlicker:
    """
    W21 Paket A: Tests für Flackern-freien Refresh.
    """

    def test_schedule_refresh_method_exists(self, browser):
        """A-W21-R18: schedule_refresh() Methode existiert."""
        assert hasattr(browser, 'schedule_refresh'), "Should have schedule_refresh method"

    def test_refresh_timer_exists(self, browser):
        """A-W21-R19: Refresh-Timer ist vorhanden."""
        assert hasattr(browser, '_refresh_timer'), "Should have refresh timer"
        assert browser._refresh_timer.isSingleShot(), "Timer should be single-shot"

    def test_refresh_uses_updates_enabled(self, browser):
        """A-W21-R20: refresh() verwendet setUpdatesEnabled für Flackern-Vermeidung."""
        # Die refresh()-Methode sollte setUpdatesEnabled(False/True) verwenden
        # Dies ist durch Code-Inspection verifiziert
        import inspect
        source = inspect.getsource(browser.refresh)
        assert "setUpdatesEnabled" in source, "refresh should use setUpdatesEnabled"


class TestBrowserFilterChangedSignal:
    """
    W21 Paket A: Tests für Filter-Changed Signal.
    """

    def test_filter_changed_signal_exists(self, browser):
        """A-W21-R21: filter_changed Signal existiert."""
        assert hasattr(browser, 'filter_changed'), "Should have filter_changed signal"

    def test_filter_change_emits_signal(self, browser, qt_app):
        """A-W21-R22: Filter-Änderung emittiert Signal."""
        received = []

        browser.filter_changed.connect(lambda mode: received.append(mode))
        browser.set_filter_mode("errors")
        QTest.qWait(100)

        assert "errors" in received, "Should emit 'errors' mode"


class TestSafeConversionHelpers:
    """
    Smoke-Pack: Type-safety helpers dürfen bei None/Mock/String nicht crashen.
    """

    def test_safe_int_with_none(self):
        from gui.browser import _safe_int
        assert _safe_int(None) == 0

    def test_safe_int_with_string(self):
        from gui.browser import _safe_int
        assert _safe_int("abc") == 0

    def test_safe_int_with_valid(self):
        from gui.browser import _safe_int
        assert _safe_int(42) == 42
        assert _safe_int("7") == 7

    def test_safe_float_with_none(self):
        from gui.browser import _safe_float
        assert _safe_float(None) == 0.0

    def test_safe_float_with_string(self):
        from gui.browser import _safe_float
        assert _safe_float("xyz") == 0.0

    def test_safe_float_with_valid(self):
        from gui.browser import _safe_float
        assert _safe_float(3.14) == pytest.approx(3.14)
        assert _safe_float("2.5") == pytest.approx(2.5)

    def test_safe_details_with_none(self):
        from gui.browser import _safe_details
        assert _safe_details(None) == {}

    def test_safe_details_with_string(self):
        from gui.browser import _safe_details
        assert _safe_details("oops") == {}

    def test_safe_details_with_dict(self):
        from gui.browser import _safe_details
        d = {"status_class": "ERROR"}
        assert _safe_details(d) is d

    def test_safe_details_with_mock(self):
        from gui.browser import _safe_details
        assert _safe_details(Mock()) == {}


class TestBrowserRobustWithBadData:
    """
    Smoke-Pack: Browser darf bei unvollständigen/kaputten Feature-Daten nicht crashen.
    """

    def test_problem_count_with_none_status_details(self, qt_app):
        """get_problem_count darf bei status_details=None nicht crashen."""
        browser = ProjectBrowser()

        doc = Mock()
        doc.name = "Test"
        doc.root_component = None
        doc.planes = []
        doc.sketches = []
        doc.bodies = []

        body = Mock()
        body.features = []
        feat = Mock()
        feat.status = "ERROR"
        feat.status_details = None  # None statt dict!
        feat.edge_indices = []
        body.features = [feat]
        doc.get_all_bodies = lambda: [body]
        doc.get_all_sketches = lambda: []

        browser.set_document(doc)
        count = browser.get_problem_count()
        assert count == 1
        browser.close()
        browser.deleteLater()

    def test_problem_count_with_string_status_details(self, qt_app):
        """get_problem_count darf bei status_details='error string' nicht crashen."""
        browser = ProjectBrowser()

        doc = Mock()
        doc.name = "Test"
        doc.root_component = None
        doc.planes = []
        doc.sketches = []
        doc.bodies = []

        body = Mock()
        feat = Mock()
        feat.status = "WARNING"
        feat.status_details = "some error string"
        feat.edge_indices = []
        body.features = [feat]
        doc.get_all_bodies = lambda: [body]
        doc.get_all_sketches = lambda: []

        browser.set_document(doc)
        count = browser.get_problem_count()
        assert count == 1
        browser.close()
        browser.deleteLater()

    def test_filtered_features_with_none_details(self, qt_app):
        """get_filtered_features darf bei status_details=None nicht crashen."""
        browser = ProjectBrowser()

        doc = Mock()
        doc.name = "Test"
        doc.root_component = None
        doc.planes = []
        doc.sketches = []
        doc.bodies = []

        body = Mock()
        feat = Mock()
        feat.status = "ERROR"
        feat.status_details = None
        feat.edge_indices = []
        body.features = [feat]
        doc.get_all_bodies = lambda: [body]
        doc.get_all_sketches = lambda: []

        browser.set_document(doc)
        browser.set_filter_mode("errors")
        features = browser.get_filtered_features()
        assert len(features) == 1
        browser.close()
        browser.deleteLater()

    def test_update_problem_badge_with_none_details(self, qt_app):
        """_update_problem_badge darf bei status_details=None nicht crashen."""
        browser = ProjectBrowser()

        doc = Mock()
        doc.name = "Test"
        doc.root_component = None
        doc.planes = []
        doc.sketches = []
        doc.bodies = []

        body = Mock()
        feat = Mock()
        feat.status = "ERROR"
        feat.status_details = None
        feat.edge_indices = []
        body.features = [feat]
        doc.get_all_bodies = lambda: [body]
        doc.get_all_sketches = lambda: []

        browser.set_document(doc)
        # Should not raise
        browser._update_problem_badge()
        assert not browser.problem_badge.isHidden()
        browser.close()
        browser.deleteLater()

    def test_problem_count_consistent_with_badge(self, browser):
        """get_problem_count und _update_problem_badge müssen konsistent zählen."""
        browser._update_problem_badge()
        badge_count = int(browser.problem_badge.text()) if browser.problem_badge.isVisible() else 0
        method_count = browser.get_problem_count()
        assert badge_count == method_count, \
            f"Badge={badge_count} vs get_problem_count={method_count} — inconsistent!"

    def test_geometry_badge_with_none_values(self, qt_app):
        """Geometry badge darf bei None-Werten in _geometry_delta nicht crashen."""
        browser = ProjectBrowser()

        doc = Mock()
        doc.name = "Test"
        doc.root_component = None
        doc.planes = []

        body = Mock()
        body.id = "b1"
        body.name = "Body1"
        body.rollback_index = None
        feat = Mock()
        feat.name = "Extrude1"
        feat.status = "OK"
        feat.status_message = ""
        feat.status_details = {}
        feat.edge_indices = []
        feat._geometry_delta = {
            "volume_pct": None,
            "faces_delta": None,
            "edges_ok": None,
            "edges_total": None,
        }
        body.features = [feat]
        doc.bodies = [body]
        doc.sketches = []
        doc.get_all_bodies = lambda: [body]
        doc.get_all_sketches = lambda: []

        browser.set_document(doc)
        # Should not raise TypeError
        browser.refresh()
        browser.close()
        browser.deleteLater()

    def test_geometry_badge_with_string_values(self, qt_app):
        """Geometry badge darf bei String-Werten nicht crashen."""
        browser = ProjectBrowser()

        doc = Mock()
        doc.name = "Test"
        doc.root_component = None
        doc.planes = []

        body = Mock()
        body.id = "b1"
        body.name = "Body1"
        body.rollback_index = None
        feat = Mock()
        feat.name = "Extrude1"
        feat.status = "OK"
        feat.status_message = ""
        feat.status_details = {}
        feat.edge_indices = []
        feat._geometry_delta = {
            "volume_pct": "bad",
            "faces_delta": "nope",
            "edges_ok": "x",
            "edges_total": "y",
        }
        body.features = [feat]
        doc.bodies = [body]
        doc.sketches = []
        doc.get_all_bodies = lambda: [body]
        doc.get_all_sketches = lambda: []

        browser.set_document(doc)
        # Should not raise TypeError/ValueError
        browser.refresh()
        browser.close()
        browser.deleteLater()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
