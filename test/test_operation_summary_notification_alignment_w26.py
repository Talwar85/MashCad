"""
W26 Paket F3: Operation Summary + Notification Alignment Tests
================================================================
Testet die konsistente Severity-Darstellung zwischen:
- Operation Summary Widget
- Notification Manager
- Browser Badge

Author: AI-LARGE-F (Product Surface Cell)
Date: 2026-02-17
Branch: feature/v1-ux-aiB
"""

# CRITICAL: QT_OPENGL muss VOR jedem Qt/PyVista Import gesetzt werden
import os
os.environ["QT_OPENGL"] = "software"

import pytest
from PySide6.QtWidgets import QApplication
from unittest.mock import Mock

from gui.widgets.operation_summary import (
    SeverityLevel, map_to_severity, _SEVERITY_CONFIG
)
from gui.managers.notification_manager import NotificationManager


@pytest.fixture(scope="session")
def qt_app():
    """Session-weite QApplication Instanz."""
    app = QApplication.instance()
    if app is None:
        import sys
        app = QApplication(sys.argv)
    return app


class TestW26SeverityMapping:
    """
    W26 Paket F3: Tests für konsistentes Severity-Mapping.
    5 Assertions
    """

    def test_map_to_severity_critical(self):
        """F3-W26-R1: map_to_severity erkennt CRITICAL korrekt."""
        result = map_to_severity("OK", "CRITICAL", "")
        assert result == SeverityLevel.CRITICAL

        result = map_to_severity("OK", "", "critical")
        assert result == SeverityLevel.CRITICAL

    def test_map_to_severity_blocked(self):
        """F3-W26-R2: map_to_severity erkennt BLOCKED korrekt."""
        result = map_to_severity("OK", "BLOCKED", "")
        assert result == SeverityLevel.BLOCKED

        result = map_to_severity("OK", "", "blocked")
        assert result == SeverityLevel.BLOCKED

    def test_map_to_severity_warning_recoverable(self):
        """F3-W26-R3: map_to_severity erkennt WARNING_RECOVERABLE."""
        result = map_to_severity("ERROR", "WARNING_RECOVERABLE", "")
        assert result == SeverityLevel.WARNING

    def test_severity_config_has_all_levels(self):
        """F3-W26-R4: _SEVERITY_CONFIG enthält alle Severity-Levels."""
        assert SeverityLevel.CRITICAL in _SEVERITY_CONFIG
        assert SeverityLevel.BLOCKED in _SEVERITY_CONFIG
        assert SeverityLevel.ERROR in _SEVERITY_CONFIG
        assert SeverityLevel.WARNING in _SEVERITY_CONFIG
        assert SeverityLevel.SUCCESS in _SEVERITY_CONFIG
        assert SeverityLevel.INFO in _SEVERITY_CONFIG

    def test_severity_config_has_required_fields(self):
        """F3-W26-R5: _SEVERITY_CONFIG Einträge haben alle erforderlichen Felder."""
        for level, config in _SEVERITY_CONFIG.items():
            assert "color" in config
            assert "icon" in config
            assert "accent" in config
            assert "duration_ms" in config
            assert "recoverable" in config


class TestW26NotificationManagerAlignment:
    """
    W26 Paket F3: Tests für Notification Manager Alignment.
    """

    def test_notification_manager_maps_blocked(self, qt_app):
        """F3-W26-R6: NotificationManager mappt BLOCKED korrekt."""
        from PySide6.QtWidgets import QWidget
        parent = QWidget()
        nm = NotificationManager(parent)

        style = nm._map_status_to_style("", "BLOCKED", "")
        assert style == "error"  # BLOCKED wird auf "error" gemappt

    def test_notification_manager_maps_critical(self, qt_app):
        """F3-W26-R7: NotificationManager mappt CRITICAL korrekt."""
        from PySide6.QtWidgets import QWidget
        parent = QWidget()
        nm = NotificationManager(parent)

        style = nm._map_status_to_style("", "CRITICAL", "")
        assert style == "error"  # CRITICAL wird auf "error" gemappt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
