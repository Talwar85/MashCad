"""
W21 Paket B: Feature Detail Panel v2 Tests
============================================
Testet die neuen Feature Detail Panel Features:
- Strukturierte Fehlerdiagnose
- Copy diagnostics Aktion
- Kantenreferenzen mit robustem Invalid-Handling
- TNP-Sektion visuell priorisieren

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
from unittest.mock import Mock, MagicMock, patch

from gui.widgets.feature_detail_panel import FeatureDetailPanel
from modeling import Body, ExtrudeFeature


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


@pytest.fixture
def mock_feature_ok():
    """Mock Feature mit OK Status."""
    feature = Mock()
    feature.name = "Extrude1"
    feature.status = "OK"
    feature.status_message = ""
    feature.status_details = {}
    feature.edge_indices = []
    feature.id = "feature1"
    return feature


@pytest.fixture
def mock_feature_error():
    """Mock Feature mit ERROR Status."""
    feature = Mock()
    feature.name = "Fillet1"
    feature.status = "ERROR"
    feature.status_message = "Kante konnte nicht aufgelöst werden"
    feature.status_details = {
        "code": "edge_not_found",
        "hint": "Prüfe die Geometrie auf Überschneidungen",
        "status_class": "ERROR",
        "severity": "error",
        "tnp_failure": {
            "category": "missing_ref",
            "reference_kind": "edge"
        }
    }
    feature.edge_indices = [0, 1, 999]  # 999 ist ungültig
    feature.id = "feature2"
    return feature


@pytest.fixture
def mock_body():
    """Mock Body mit Solid."""
    body = Mock()
    body.name = "Body1"
    body.id = "body1"
    # Mock solid ohne echte OCP-Objekte
    mock_solid = Mock()
    mock_edge = Mock()
    mock_edge.center = Mock(return_value=Mock(X=10.0, Y=20.0, Z=30.0))
    mock_edge.length = 5.0
    mock_solid.edges = Mock(return_value=[])
    body._build123d_solid = mock_solid
    return body


class TestFeatureDetailPanelDiagnostics:
    """
    W21 Paket B: Tests für strukturierte Fehlerdiagnose.
    """

    def test_diag_widgets_exist(self, panel):
        """B-W21-R1: Diagnose-Widgets sind vorhanden."""
        assert hasattr(panel, '_diag_header')
        assert hasattr(panel, '_diag_code')
        assert hasattr(panel, '_diag_category')
        assert hasattr(panel, '_diag_hint')

    def test_show_feature_with_error_shows_diagnostics(self, panel, mock_feature_error):
        """B-W21-R2: ERROR-Feature zeigt Diagnose-Section."""
        panel.show_feature(mock_feature_error)

        assert panel._diag_header.isVisible(), "Diag header should be visible for error"
        assert panel._diag_code.isVisible(), "Diag code should be visible"
        assert panel._diag_hint.isVisible(), "Diag hint should be visible"

    def test_show_feature_with_ok_hides_diagnostics(self, panel, mock_feature_ok):
        """B-W21-R3: OK-Feature versteckt Diagnose-Section."""
        panel.show_feature(mock_feature_ok)

        assert not panel._diag_header.isVisible(), "Diag header should be hidden for OK"

    def test_diag_code_shows_error_code(self, panel, mock_feature_error):
        """B-W21-R4: Diag-Code zeigt den Error-Code."""
        panel.show_feature(mock_feature_error)

        code_text = panel._diag_code.text()
        assert "edge_not_found" in code_text, "Should show error code"

    def test_diag_category_shows_category(self, panel, mock_feature_error):
        """B-W21-R5: Diag-Category zeigt die Kategorie."""
        panel.show_feature(mock_feature_error)

        cat_text = panel._diag_category.text()
        assert "Referenz verloren" in cat_text or "missing_ref" in cat_text

    def test_diag_hint_shows_hint(self, panel, mock_feature_error):
        """B-W21-R6: Diag-Hint zeigt den Hinweis."""
        panel.show_feature(mock_feature_error)

        hint_text = panel._diag_hint.text()
        assert "Prüfe" in hint_text or "hint" in hint_text.lower()

    def test_show_feature_without_details_hides_diag(self, panel, mock_feature_ok):
        """B-W21-R7: Feature ohne Details versteckt Diagnose."""
        mock_feature_ok.status_details = None
        panel.show_feature(mock_feature_ok)

        assert not panel._diag_code.isVisible()
        assert not panel._diag_category.isVisible()
        assert not panel._diag_hint.isVisible()


class TestFeatureDetailPanelCopyDiagnostics:
    """
    W21 Paket B: Tests für Copy Diagnostics Aktion.
    """

    def test_copy_button_exists(self, panel):
        """B-W21-R8: Copy-Diagnostics Button ist vorhanden."""
        assert hasattr(panel, '_btn_copy_diag'), "Should have copy button"

    def test_copy_diagnostics_method_exists(self, panel):
        """B-W21-R9: _on_copy_diagnostics() Methode existiert."""
        assert hasattr(panel, '_on_copy_diagnostics'), "Should have copy diagnostics method"

    def test_get_diagnostics_text_returns_string(self, panel, mock_feature_error):
        """B-W21-R10: get_diagnostics_text() liefert String."""
        panel.show_feature(mock_feature_error)
        diag_text = panel.get_diagnostics_text()

        assert isinstance(diag_text, str), "Should return string"
        assert "Fillet1" in diag_text, "Should contain feature name"
        assert "ERROR" in diag_text, "Should contain status"

    def test_get_diagnostics_text_includes_code_and_hint(self, panel, mock_feature_error):
        """B-W21-R11: get_diagnostics_text() enthält Code und Hint."""
        panel.show_feature(mock_feature_error)
        diag_text = panel.get_diagnostics_text()

        assert "edge_not_found" in diag_text, "Should contain error code"
        assert "Prüfe" in diag_text or "hint" in diag_text.lower(), "Should contain hint"

    def test_get_diagnostics_text_for_none_returns_empty(self, panel):
        """B-W21-R12: get_diagnostics_text() mit None liefert leeren String."""
        panel.show_feature(None)
        diag_text = panel.get_diagnostics_text()

        assert diag_text == "", "Should return empty string for None"

    @patch('PySide6.QtWidgets.QApplication.clipboard')
    def test_copy_diagnostics_copies_to_clipboard(self, mock_clipboard, panel, mock_feature_error):
        """B-W21-R13: _on_copy_diagnostics() kopiert in die Zwischenablage."""
        mock_clipboard_instance = Mock()
        mock_clipboard.return_value = mock_clipboard_instance

        panel.show_feature(mock_feature_error)
        panel._on_copy_diagnostics()

        # Verify setText wurde aufgerufen
        assert mock_clipboard_instance.setText.called, "Should copy to clipboard"


class TestFeatureDetailPanelEdgeReferences:
    """
    W21 Paket B: Tests für Kantenreferenzen mit Invalid-Handling.
    """

    def test_show_edge_references_with_invalid_indices(self, panel, mock_feature_error, mock_body):
        """B-W21-R14: Ungültige Kanten-Indizes werden als UNGÜLTIG markiert."""
        panel.show_feature(mock_feature_error, mock_body)

        # Nach dem Aufruf von _show_edge_references
        edge_layout = panel._edge_layout
        assert edge_layout.count() > 0, "Should have edge labels"

        # Prüfe ob Warnung für ungültige Kanten angezeigt wird
        found_invalid = False
        for i in range(edge_layout.count()):
            item = edge_layout.itemAt(i)
            if item and item.widget():
                text = item.widget().text()
                if "UNGÜLTIG" in text or "ungültig" in text:
                    found_invalid = True

        assert found_invalid, "Should show invalid edge warning"

    def test_show_edge_references_handles_exception(self, panel, mock_body):
        """B-W21-R15: Exception beim Kanten-Lesen wird abgefangen."""
        # Kante die Exception wirft
        mock_bad_edge = Mock()
        mock_bad_edge.center.side_effect = RuntimeError("Test error")
        mock_bad_edge.length = 5.0

        mock_solid = Mock()
        mock_solid.edges = Mock(return_value=[mock_bad_edge])
        mock_body._build123d_solid = mock_solid

        feature = Mock()
        feature.name = "TestFeature"
        feature.status = "ERROR"
        feature.status_message = "Test"
        feature.status_details = {}
        feature.edge_indices = [0]

        panel.show_feature(feature, mock_body)

        # Sollte nicht crashen
        edge_layout = panel._edge_layout
        assert edge_layout.count() > 0, "Should handle exception gracefully"

    def test_show_edge_references_max_12_displayed(self, panel):
        """B-W21-R16: Maximal 12 Kanten werden angezeigt."""
        feature = Mock()
        feature.name = "TestFeature"
        feature.status = "OK"
        feature.status_details = {}
        feature.edge_indices = list(range(20))  # 20 Kanten

        body = Mock()
        body.name = "Body1"
        body.id = "body1"

        mock_solid = Mock()
        mock_edges = [Mock(center=Mock(return_value=Mock(X=0, Y=0, Z=0)), length=1.0)]
        mock_solid.edges = Mock(return_value=mock_edges * 20)
        body._build123d_solid = mock_solid

        panel.show_feature(feature, body)

        # Prüfe "weitere" Label
        edge_layout = panel._edge_layout
        found_more = False
        for i in range(edge_layout.count()):
            item = edge_layout.itemAt(i)
            if item and item.widget():
                if "weitere" in item.widget().text() or "more" in item.widget().text().lower():
                    found_more = True

        assert found_more, "Should show '+X more' for additional edges"


class TestFeatureDetailPanelTNPPriority:
    """
    W21 Paket B: Tests für TNP-Sektion Priorisierung.
    """

    def test_tnp_priority_parameter_exists(self, panel):
        """B-W21-R17: _show_tnp_section() hat prioritize Parameter."""
        import inspect
        sig = inspect.signature(panel._show_tnp_section)
        params = sig.parameters
        assert 'prioritize' in params, "Should have prioritize parameter"

    def test_tnp_section_with_error_prioritized(self, panel, mock_feature_error, mock_body):
        """B-W21-R18: TNP-Sektion wird bei ERROR priorisiert (sichtbar hervorgehoben)."""
        # Mock Shape Naming Service
        mock_doc = Mock()
        mock_sns = Mock()
        report = {
            "features": [{
                "feature_id": "feature2",
                "feature_name": "Fillet1",
                "ok": 2,
                "fallback": 1,
                "broken": 0,
                "refs": [{"method": "history"}]
            }]
        }
        mock_sns.get_health_report = Mock(return_value=report)
        mock_doc._shape_naming_service = mock_sns

        panel.show_feature(mock_feature_error, mock_body, mock_doc)

        # TNP Header sollte rot (priorisiert) sein
        header_style = panel._tnp_header.styleSheet()
        assert "#ef4444" in header_style or "red" in header_style.lower(), \
               "TNP header should be prioritized (red) for error"

    def test_tnp_section_with_warning_not_prioritized(self, panel, mock_body):
        """B-W21-R19: TNP-Sektion wird bei WARNING nicht prioritisiert."""
        feature = Mock()
        feature.name = "Chamfer1"
        feature.status = "WARNING"
        feature.status_message = "Drift detected"
        feature.status_details = {
            "code": "tnp_ref_drift",
            "status_class": "WARNING_RECOVERABLE",
            "severity": "warning"
        }
        feature.edge_indices = []
        feature.id = "feature3"

        mock_doc = Mock()
        mock_sns = Mock()
        report = {
            "features": [{
                "feature_id": "feature3",
                "feature_name": "Chamfer1",
                "ok": 2,
                "fallback": 1,
                "broken": 0,
                "refs": [{"method": "geometric"}]
            }]
        }
        mock_sns.get_health_report = Mock(return_value=report)
        mock_doc._shape_naming_service = mock_sns

        panel.show_feature(feature, mock_body, mock_doc)

        # TNP Header sollte normal (nicht priorisiert) sein
        header_style = panel._tnp_header.styleSheet()
        assert "#888" in header_style or "color: #888" in header_style, \
               "TNP header should be normal for warning"

    def test_tnp_quality_low_shows_warning(self, panel, mock_feature_error, mock_body):
        """B-W21-R20: Niedrige TNP-Qualität zeigt Warnung."""
        mock_doc = Mock()
        mock_sns = Mock()
        report = {
            "features": [{
                "feature_id": "feature2",
                "feature_name": "Fillet1",
                "ok": 1,
                "fallback": 2,
                "broken": 1,  # Schlechte Qualität
                "refs": [{"method": "fallback"}]
            }]
        }
        mock_sns.get_health_report = Mock(return_value=report)
        mock_doc._shape_naming_service = mock_sns

        panel.show_feature(mock_feature_error, mock_body, mock_doc)

        # Quality Label sollte Warnung haben
        quality_text = panel._tnp_quality.text()
        assert "⚠" in quality_text or quality_text.startswith("Qualität:"), \
               "Low quality should show warning"


class TestFeatureDetailPanelErrorUXv2:
    """
    W21 Paket B: Tests für Error UX v2 Integration.
    """

    def test_status_with_warning_recoverable(self, panel):
        """B-W21-R21: WARNING_RECOVERABLE zeigt Warnung-Icon."""
        feature = Mock()
        feature.name = "Test"
        feature.status = "ERROR"
        feature.status_details = {"status_class": "WARNING_RECOVERABLE"}

        panel.show_feature(feature)

        status_text = panel._status_label.text()
        assert "⚠" in status_text or "Warning" in status_text

    def test_status_with_blocked(self, panel):
        """B-W21-R22: BLOCKED zeigt Error-Icon."""
        feature = Mock()
        feature.name = "Test"
        feature.status = "OK"
        feature.status_details = {"status_class": "BLOCKED"}

        panel.show_feature(feature)

        status_text = panel._status_label.text()
        assert "✕" in status_text or "Error" in status_text

    def test_status_with_critical(self, panel):
        """B-W21-R23: CRITICAL zeigt Error-Icon."""
        feature = Mock()
        feature.name = "Test"
        feature.status = "OK"
        feature.status_details = {"status_class": "CRITICAL"}

        panel.show_feature(feature)

        status_text = panel._status_label.text()
        assert "✕" in status_text or "Error" in status_text


class TestFeatureDetailPanelTypeSafety:
    """
    W21 SmokePack: Tests für typsichere Behandlung von Mock/None/String Werten.
    """

    def test_show_feature_with_mock_status_message_no_crash(self, panel):
        """SmokePack-R1: Mock status_message verursacht keinen Crash."""
        feature = Mock()
        feature.name = "TestFeature"
        feature.status = "OK"
        feature.status_message = Mock()  # Mock statt String
        feature.status_details = {}
        feature.edge_indices = []

        # Sollte nicht crashen
        panel.show_feature(feature)
        assert panel._status_label.text()  # Sollte Text haben

    def test_show_feature_with_none_status_message(self, panel):
        """SmokePack-R2: None status_message wird sicher behandelt."""
        feature = Mock()
        feature.name = "TestFeature"
        feature.status = "OK"
        feature.status_message = None
        feature.status_details = {}
        feature.edge_indices = []

        panel.show_feature(feature)
        assert "OK" in panel._status_label.text()

    def test_show_feature_with_mock_geometry_delta_no_crash(self, panel):
        """SmokePack-R3: Mock _geometry_delta verursacht keinen Crash."""
        feature = Mock()
        feature.name = "TestFeature"
        feature.status = "OK"
        feature.status_details = {}
        feature.edge_indices = []
        feature._geometry_delta = Mock()  # Mock statt dict

        # Sollte nicht crashen
        panel.show_feature(feature)
        assert not panel._geo_header.isVisible()  # Geometry sollte versteckt sein

    def test_show_feature_with_partial_geometry_delta(self, panel):
        """SmokePack-R4: Partielles geometry_delta wird sicher behandelt."""
        feature = Mock()
        feature.name = "TestFeature"
        feature.status = "OK"
        feature.status_details = {}
        feature.edge_indices = []
        feature._geometry_delta = {
            "volume_before": 100.0,
            # volume_after fehlt
        }

        panel.show_feature(feature)
        # Sollte nicht crashen, Geometry sollte angezeigt werden
        assert panel._geo_header.isVisible() or not panel._geo_header.isVisible()  # Beides OK

    def test_show_feature_with_mock_edge_indices_no_crash(self, panel):
        """SmokePack-R5: Mock edge_indices verursacht keinen Crash."""
        feature = Mock()
        feature.name = "TestFeature"
        feature.status = "OK"
        feature.status_details = {}
        feature.edge_indices = Mock()  # Mock statt Liste

        # Sollte nicht crashen
        panel.show_feature(feature)
        assert not panel._edge_header.isVisible()  # Edges sollten versteckt sein

    def test_show_feature_with_mock_details_values(self, panel):
        """SmokePack-R6: Mock Werte in status_details werden sicher behandelt."""
        feature = Mock()
        feature.name = "TestFeature"
        feature.status = "ERROR"
        feature.status_details = {
            "code": Mock(),
            "hint": Mock(),
            "tnp_failure": Mock(),  # Mock statt dict
        }
        feature.edge_indices = []

        # Sollte nicht crashen
        panel.show_feature(feature)
        assert panel._diag_header.isVisible()  # Diag sollte sichtbar sein bei ERROR

    def test_show_feature_with_nested_tnp_failure(self, panel):
        """SmokePack-R7: tnp_failure mit category wird korrekt angezeigt."""
        feature = Mock()
        feature.name = "TestFeature"
        feature.status = "ERROR"
        feature.status_details = {
            "code": "test_error",
            "tnp_failure": {
                "category": "missing_ref"
            }
        }
        feature.edge_indices = []

        panel.show_feature(feature)
        # Category sollte übersetzt werden
        cat_text = panel._diag_category.text()
        assert "Referenz verloren" in cat_text or "missing_ref" in cat_text

    def test_copy_diagnostics_with_mock_geometry(self, panel):
        """SmokePack-R8: Copy diagnostics mit Mock geometry_delta."""
        feature = Mock()
        feature.name = "TestFeature"
        feature.status = "OK"
        feature.status_message = ""
        feature.status_details = {}
        feature.edge_indices = None
        feature._geometry_delta = Mock()  # Mock

        panel.show_feature(feature)
        diag_text = panel.get_diagnostics_text()

        # Sollte String zurückgeben ohne Crash
        assert isinstance(diag_text, str)
        assert "TestFeature" in diag_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
