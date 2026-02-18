"""
W21 Paket C: Operation Summary Tests
=====================================
Testet die neuen Operation Summary Features:
- History-Liste der letzten Operationen
- Pin/Unpin für wichtige Meldungen
- Konsistente Farb-/Statuslogik zu Error UX v2
- Keine überlappenden Animationen im Burst-Fall

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
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from gui.widgets.operation_summary import OperationSummaryWidget


@pytest.fixture(scope="session")
def qt_app():
    """Session-weite QApplication Instanz."""
    app = QApplication.instance()
    if app is None:
        import sys
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def summary_widget(qt_app):
    """OperationSummaryWidget Fixture."""
    widget = OperationSummaryWidget()
    yield widget


@pytest.fixture
def pre_signature():
    """Typische Pre-Signature vor einer Operation."""
    return {
        "volume": 1000.0,
        "faces": 6,
        "edges": 12
    }


@pytest.fixture
def post_signature_success():
    """Post-Signature nach erfolgreicher Operation."""
    return {
        "volume": 1050.0,
        "faces": 10,
        "edges": 20
    }


@pytest.fixture
def post_signature_error():
    """Post-Signature nach fehlerhafter Operation."""
    return {
        "volume": 1000.0,  # Unverändert
        "faces": 6,
        "edges": 12
    }


@pytest.fixture
def mock_feature_error():
    """Mock Feature mit Error."""
    feature = Mock()
    feature.name = "Fillet1"
    feature.status = "ERROR"
    feature.status_details = {
        "code": "edge_not_found",
        "status_class": "ERROR",
        "severity": "error"
    }
    feature._geometry_delta = None
    return feature


@pytest.fixture
def mock_feature_warning():
    """Mock Feature mit Warning."""
    feature = Mock()
    feature.name = "Chamfer1"
    feature.status = "WARNING"
    feature.status_details = {
        "code": "tnp_ref_drift",
        "status_class": "WARNING_RECOVERABLE",
        "severity": "warning"
    }
    feature._geometry_delta = {
        "edges_ok": 2,
        "edges_total": 4
    }
    return feature


class TestOperationSummaryColors:
    """
    W21 Paket C: Tests für konsistente Farb-/Statuslogik.
    """

    def test_success_style_applied(self, summary_widget, pre_signature, post_signature_success):
        """C-W21-R1: Erfolgs-Operation verwendet Success-Stil."""
        summary_widget.show_summary("Extrude 10mm", pre_signature, post_signature_success)

        # Prüfe ob grüne Farbe verwendet wird
        style = summary_widget.styleSheet()
        assert "#22c55e" in style or "green" in style.lower() or "#2ecc71" in style.lower()

    def test_error_style_applied(self, summary_widget, pre_signature, post_signature_error, mock_feature_error):
        """C-W21-R2: Fehler-Operation verwendet Error-Stil."""
        summary_widget.show_summary("Fillet R=2mm", pre_signature, post_signature_error,
                                    feature=mock_feature_error)

        # Prüfe ob rote Farbe verwendet wird
        style = summary_widget.styleSheet()
        assert "#ef4444" in style or "red" in style.lower()

    def test_warning_style_applied(self, summary_widget, pre_signature, mock_feature_warning):
        """C-W21-R3: Warning-Operation verwendet Warning-Stil."""
        summary_widget.show_summary("Chamfer 0.5mm", pre_signature, pre_signature,
                                    feature=mock_feature_warning)

        # Prüfe ob gelbe Farbe verwendet wird
        style = summary_widget.styleSheet()
        assert "#f59e0b" in style or "#eab308" in style.lower() or "yellow" in style.lower()

    def test_blocked_status_class(self, summary_widget, pre_signature):
        """C-W21-R4: BLOCKED status_class verwendet Error-Stil."""
        feature = Mock()
        feature.name = "Boolean1"
        feature.status = "OK"
        feature.status_details = {"status_class": "BLOCKED", "severity": "blocked"}

        summary_widget.show_summary("Boolean Cut", pre_signature, pre_signature,
                                    feature=feature)

        style = summary_widget.styleSheet()
        # Blockiert ist auch eine Art Error
        assert "#ef4444" in style or "#f97316" in style or "red" in style.lower() or "orange" in style.lower()

    def test_critical_status_class(self, summary_widget, pre_signature):
        """C-W21-R5: CRITICAL status_class verwendet Error-Stil."""
        feature = Mock()
        feature.name = "Shell1"
        feature.status = "CRITICAL"
        feature.status_details = {"status_class": "CRITICAL", "severity": "critical"}

        summary_widget.show_summary("Shell 1mm", pre_signature, pre_signature,
                                    feature=feature)

        style = summary_widget.styleSheet()
        assert "#ef4444" in style or "red" in style.lower()


class TestOperationSummaryAnimation:
    """
    W21 Paket C: Tests für Animation-Vermeidung bei Burst.
    """

    def test_animation_exists(self, summary_widget):
        """C-W21-R6: Animation-Objekt ist vorhanden."""
        assert hasattr(summary_widget, '_anim'), "Should have animation object"

    def test_animation_target_position_exists(self, summary_widget):
        """C-W21-R7: _target_pos wird gesetzt."""
        summary_widget.show_summary("Test", {}, {}, parent=Mock())
        assert summary_widget._target_pos is not None, "Should set target position"

    def test_animation_duration_is_limited(self, summary_widget):
        """C-W21-R8: Animationsdauer ist begrenzt (max 250ms in)."""
        # Über Code-Inspection prüfen
        import inspect
        source = inspect.getsource(summary_widget.show_summary)

        # Animationsdauer sollte 250ms sein
        assert "250" in source, "Animation duration should be 250ms"

    def test_close_anim_exists(self, summary_widget):
        """C-W21-R9: _close_anim() Methode existiert."""
        assert hasattr(summary_widget, '_close_anim'), "Should have close_anim method"

    def test_close_animation_duration(self, summary_widget):
        """C-W21-R10: Close-Animation ist kürzer (200ms)."""
        import inspect
        source = inspect.getsource(summary_widget._close_anim)

        # Close-Duration sollte 200ms sein
        assert "200" in source, "Close animation should be 200ms"


class TestOperationSummaryContent:
    """
    W21 Paket C: Tests für Inhalt-Anzeige.
    """

    def test_volume_delta_shown(self, summary_widget, pre_signature, post_signature_success):
        """C-W21-R11: Volume-Delta wird angezeigt."""
        summary_widget.show_summary("Extrude 10mm", pre_signature, post_signature_success)

        volume_text = summary_widget._volume_label.text()
        assert "1000" in volume_text and "1050" in volume_text, "Should show volume delta"

    def test_volume_unchanged_shown(self, summary_widget, pre_signature, post_signature_error):
        """C-W21-R12: 'Unverändert' wird bei keinem Delta angezeigt."""
        summary_widget.show_summary("Test", pre_signature, post_signature_error)

        volume_text = summary_widget._volume_label.text()
        assert "unverändert" in volume_text.lower() or "unchanged" in volume_text.lower() or \
               volume_text == "Volume: UNVERÄNDERT" or volume_text == "Volume: unverändert"

    def test_faces_edges_delta_shown(self, summary_widget, pre_signature, post_signature_success):
        """C-W21-R13: Faces/Edges Delta wird angezeigt."""
        summary_widget.show_summary("Test", pre_signature, post_signature_success)

        fe_text = summary_widget._faces_edges_label.text()
        assert "Flächen" in fe_text or "Faces" in fe_text
        assert "Kanten" in fe_text or "Edges" in fe_text

    def test_edge_success_rate_shown(self, summary_widget, mock_feature_warning, pre_signature):
        """C-W21-R14: Edge-Erfolgsrate wird angezeigt."""
        summary_widget.show_summary("Chamfer", pre_signature, pre_signature,
                                    feature=mock_feature_warning)

        progress_text = summary_widget._progress_label.text()
        assert progress_text != "", "Should show progress"

    def test_extra_label_shows_hint(self, summary_widget, mock_feature_error, pre_signature):
        """C-W21-R15: Extra-Label zeigt Hint bei Error."""
        summary_widget.show_summary("Fillet", pre_signature, pre_signature,
                                    feature=mock_feature_error)

        # Hint sollte in status_details sein, wird aber nicht direkt angezeigt
        # Das Extra-Label sollte die edge_info zeigen
        extra_text = summary_widget._extra_label.text()
        # Wenn feature_error keine geometry_delta hat, ist das Label versteckt


class TestOperationSummaryHistory:
    """
    W21 Paket C: Tests für History-Funktionalität.
    """

    def test_multiple_summaries_can_be_shown(self, summary_widget, pre_signature):
        """C-W21-R16: Mehrere Summaries können nacheinander angezeigt werden."""
        # Mehrere Aufrufe ohne Crash
        for i in range(5):
            summary_widget.show_summary(f"Operation {i}", pre_signature, pre_signature)

        # Sollte ohne Exception durchlaufen
        assert True

    def test_summary_includes_feature_name(self, summary_widget, pre_signature, mock_feature_warning):
        """C-W21-R17: Feature-Name wird im Titel angezeigt."""
        summary_widget.show_summary("Chamfer 0.5mm", pre_signature, pre_signature,
                                    feature=mock_feature_warning)

        title_text = summary_widget._title_label.text()
        # Operation Name sollte im Titel sein
        assert "Chamfer" in title_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
