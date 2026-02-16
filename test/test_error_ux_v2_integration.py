"""
Error UX v2 End-to-End Integration Tests (Paket B)
==================================================
Validiert dass status_class/severity über alle UI-Komponenten hinweg
konsistent genutzt wird.

W10 Paket B: Testet Error UX v2 Integration in:
- NotificationManager (show_notification, show_toast_overlay)
- MainWindow (show_notification)
- Status-Bar (set_status)

Author: GLM 4.7 (UX/WORKFLOW + QA Integration Cell)
Date: 2026-02-16
Branch: feature/v1-ux-aiB
"""

# CRITICAL: QT_OPENGL muss VOR jedem Qt/PyVista Import gesetzt werden
import os
os.environ["QT_OPENGL"] = "software"

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from gui.main_window import MainWindow
from gui.managers.notification_manager import NotificationManager


@pytest.fixture(scope="session")
def qt_app():
    """Session-weite QApplication Instanz."""
    app = QApplication.instance()
    if app is None:
        import sys
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def main_window(qt_app):
    """MainWindow Fixture mit deterministischem Cleanup."""
    import gc

    window = None
    try:
        window = MainWindow()
        window.show()
        QTest.qWaitForWindowExposed(window)
        yield window
    finally:
        if window is not None:
            try:
                if hasattr(window, 'viewport_3d') and window.viewport_3d:
                    if hasattr(window.viewport_3d, 'plotter'):
                        try:
                            window.viewport_3d.plotter.close()
                        except Exception:
                            pass
                window.close()
                window.deleteLater()
            except Exception:
                pass
        try:
            from gui.viewport.render_queue import RenderQueue
            RenderQueue.flush()
        except Exception:
            pass
        gc.collect()


class TestErrorUXV2NotificationManager:
    """
    W10 Paket B: Error UX v2 Notification Manager Tests.
    """

    def test_notification_manager_status_class_warning_recoverable(self, main_window):
        """
        B-W10-R1: NotificationManager mappt WARNING_RECOVERABLE zu warning style.
        """
        nm = main_window.notification_manager

        # status_class=WARNING_RECOVERABLE sollte warning style ergeben
        style = nm._map_status_to_style(level="", status_class="WARNING_RECOVERABLE", severity="")
        assert style == "warning"

    def test_notification_manager_status_class_blocked(self, main_window):
        """
        B-W10-R2: NotificationManager mappt BLOCKED zu error style.
        """
        nm = main_window.notification_manager

        style = nm._map_status_to_style(level="", status_class="BLOCKED", severity="")
        assert style == "error"

    def test_notification_manager_status_class_critical(self, main_window):
        """
        B-W10-R3: NotificationManager mappt CRITICAL zu error style.
        """
        nm = main_window.notification_manager

        style = nm._map_status_to_style(level="", status_class="CRITICAL", severity="")
        assert style == "error"

    def test_notification_manager_status_class_error(self, main_window):
        """
        B-W10-R4: NotificationManager mappt ERROR zu error style.
        """
        nm = main_window.notification_manager

        style = nm._map_status_to_style(level="", status_class="ERROR", severity="")
        assert style == "error"

    def test_notification_manager_severity_warning(self, main_window):
        """
        B-W10-R5: NotificationManager mappt severity=warning zu warning style.
        """
        nm = main_window.notification_manager

        style = nm._map_status_to_style(level="", status_class="", severity="warning")
        assert style == "warning"

    def test_notification_manager_severity_blocked(self, main_window):
        """
        B-W10-R6: NotificationManager mappt severity=blocked zu error style.
        """
        nm = main_window.notification_manager

        style = nm._map_status_to_style(level="", status_class="", severity="blocked")
        assert style == "error"

    def test_notification_manager_severity_critical(self, main_window):
        """
        B-W10-R7: NotificationManager mappt severity=critical zu error style.
        """
        nm = main_window.notification_manager

        style = nm._map_status_to_style(level="", status_class="", severity="critical")
        assert style == "error"

    def test_notification_manager_severity_error(self, main_window):
        """
        B-W10-R8: NotificationManager mappt severity=error zu error style.
        """
        nm = main_window.notification_manager

        style = nm._map_status_to_style(level="", status_class="", severity="error")
        assert style == "error"

    def test_notification_manager_priority_status_over_severity(self, main_window):
        """
        B-W10-R9: NotificationManager priorisiert status_class über severity.

        Korrigiert: Wenn status_class=WARNING_RECOVERABLE (warning) und severity=error,
        dann gewinnt status_class → warning. Das ist korrektes Verhalten.
        """
        nm = main_window.notification_manager

        # status_class sollte Vorrang vor severity haben
        # WARNING_RECOVERABLE mappt zu "warning"
        style = nm._map_status_to_style(level="", status_class="WARNING_RECOVERABLE", severity="error")
        assert style == "warning"  # status_class WARNING_RECOVERABLE wins (maps to warning)

        # ERROR (status_class) gewinnt über warning (severity)
        style = nm._map_status_to_style(level="", status_class="ERROR", severity="warning")
        assert style == "error"  # status_class ERROR wins

        # Wenn kein status_class, dann severity gewinnt
        style = nm._map_status_to_style(level="info", status_class="", severity="error")
        assert style == "error"  # severity wins when no status_class

    def test_notification_manager_priority_severity_over_level(self, main_window):
        """
        B-W10-R10: NotificationManager priorisiert severity über legacy level.
        """
        nm = main_window.notification_manager

        # severity sollte Vorrang vor legacy level haben
        style = nm._map_status_to_style(level="info", status_class="", severity="warning")
        assert style == "warning"  # severity wins

        style = nm._map_status_to_style(level="info", status_class="", severity="error")
        assert style == "error"  # severity wins

    def test_notification_manager_legacy_level_fallback(self, main_window):
        """
        B-W10-R11: NotificationManager nutzt legacy level wenn kein status_class/severity.
        """
        nm = main_window.notification_manager

        # Legacy level sollte funktionieren wenn keine Error UX v2 Felder
        style = nm._map_status_to_style(level="error", status_class="", severity="")
        assert style == "error"

        style = nm._map_status_to_style(level="warning", status_class="", severity="")
        assert style == "warning"

        style = nm._map_status_to_style(level="success", status_class="", severity="")
        assert style == "success"

        style = nm._map_status_to_style(level="info", status_class="", severity="")
        assert style == "info"


class TestErrorUXV2MainWindow:
    """
    W10 Paket B: Error UX v2 MainWindow Integration Tests.
    """

    def test_main_window_show_notification_with_status_class(self, main_window):
        """
        B-W10-R12: MainWindow.show_notification akzeptiert status_class Parameter.
        """
        # Sollte kein Fehler werfen
        main_window.show_notification(
            "Test Title",
            "Test Message",
            level="info",
            status_class="WARNING_RECOVERABLE",
            severity="warning"
        )

        # Verify notification wurde erstellt
        assert len(main_window.notification_manager.notifications) > 0

        # Cleanup
        for notif in main_window.notification_manager.notifications[:]:
            main_window.notification_manager.cleanup_notification(notif)

    def test_main_window_show_notification_with_severity(self, main_window):
        """
        B-W10-R13: MainWindow.show_notification akzeptiert severity Parameter.
        """
        # Sollte kein Fehler werfen
        main_window.show_notification(
            "Error Title",
            "Error Message",
            level="error",
            status_class="",
            severity="error"
        )

        # Verify notification wurde erstellt
        assert len(main_window.notification_manager.notifications) > 0

        # Cleanup
        for notif in main_window.notification_manager.notifications[:]:
            main_window.notification_manager.cleanup_notification(notif)

    def test_main_window_show_notification_legacy_compatible(self, main_window):
        """
        B-W10-R14: MainWindow.show_notification bleibt rückwärtskompatibel.
        """
        # Legacy Aufruf ohne status_class/severity sollte noch funktionieren
        main_window.show_notification(
            "Legacy Title",
            "Legacy Message",
            level="warning"
        )

        # Verify notification wurde erstellt
        assert len(main_window.notification_manager.notifications) > 0

        # Cleanup
        for notif in main_window.notification_manager.notifications[:]:
            main_window.notification_manager.cleanup_notification(notif)


class TestErrorUXV2StatusBar:
    """
    W10 Paket B: Error UX v2 Status-Bar Integration Tests.
    """

    def test_status_bar_set_status_with_status_class_warning_recoverable(self, main_window):
        """
        B-W10-R15: Status-Bar set_status mit WARNING_RECOVERABLE zeigt gelben Dot.
        """
        status_bar = main_window.mashcad_status_bar

        status_bar.set_status("Warning message", is_error=False, status_class="WARNING_RECOVERABLE", severity="warning")

        # Dot sollte gelb sein (check stylesheet)
        dot_style = status_bar.status_dot.styleSheet()
        assert "#eab308" in dot_style or "yellow" in dot_style.lower()

    def test_status_bar_set_status_with_status_class_blocked(self, main_window):
        """
        B-W10-R16: Status-Bar set_status mit BLOCKED zeigt orangen Dot.
        """
        status_bar = main_window.mashcad_status_bar

        status_bar.set_status("Blocked message", is_error=False, status_class="BLOCKED", severity="blocked")

        # Dot sollte orange sein
        dot_style = status_bar.status_dot.styleSheet()
        assert "#f97316" in dot_style or "orange" in dot_style.lower()

    def test_status_bar_set_status_with_status_class_critical(self, main_window):
        """
        B-W10-R17: Status-Bar set_status mit CRITICAL zeigt roten Dot.
        """
        status_bar = main_window.mashcad_status_bar

        status_bar.set_status("Critical message", is_error=False, status_class="CRITICAL", severity="critical")

        # Dot sollte rot sein (Hex-Code #ef4444 für rot)
        dot_style = status_bar.status_dot.styleSheet()
        assert "#ef4444" in dot_style or "red" in dot_style.lower() or "#ff" in dot_style.lower()

    def test_status_bar_set_status_with_status_class_error(self, main_window):
        """
        B-W10-R18: Status-Bar set_status mit ERROR zeigt roten Dot.
        """
        status_bar = main_window.mashcad_status_bar

        status_bar.set_status("Error message", is_error=False, status_class="ERROR", severity="error")

        # Dot sollte rot sein (Hex-Code #ef4444 für rot)
        dot_style = status_bar.status_dot.styleSheet()
        assert "#ef4444" in dot_style or "red" in dot_style.lower()

    def test_status_bar_set_status_legacy_compatible(self, main_window):
        """
        B-W10-R19: Status-Bar set_status bleibt rückwärtskompatibel.
        """
        status_bar = main_window.mashcad_status_bar

        # Legacy Aufruf mit is_error sollte noch funktionieren
        status_bar.set_status("Legacy error", is_error=True)

        # Dot sollte rot sein (Hex-Code #ef4444 für rot)
        dot_style = status_bar.status_dot.styleSheet()
        assert "#ef4444" in dot_style or "red" in dot_style.lower()

    def test_status_bar_set_status_success_green(self, main_window):
        """
        B-W10-R20: Status-Bar set_status ohne Fehler zeigt grünen Dot.
        """
        status_bar = main_window.mashcad_status_bar

        status_bar.set_status("Success message", is_error=False)

        # Dot sollte grün sein (Hex-Code #22c55e für grün)
        dot_style = status_bar.status_dot.styleSheet()
        assert "#22c55e" in dot_style or "green" in dot_style.lower()


class TestErrorUXV2Integration:
    """
    W10 Paket B: End-to-End Error UX v2 Integration Tests.
    """

    def test_error_ux_v2_consistent_across_ui_components(self, main_window):
        """
        B-W10-R21: Error UX v2 status_class wird konsistent über alle UI-Komponenten genutzt.

        Dieser Test validiert dass derselbe Fehler (status_class=ERROR)
        in Notification, Status-Bar und Tooltip konsistent dargestellt wird.
        """
        from gui.browser import _format_feature_status_tooltip

        error_msg = "Boolean: Operation fehlgeschlagen"
        error_details = {
            "code": "boolean_failed",
            "status_class": "ERROR",
            "severity": "error",
            "hint": "Prüfe die Geometrie auf Überschneidungen"
        }

        # 1. Tooltip sollte Error anzeigen
        tooltip = _format_feature_status_tooltip(error_msg, status="ERROR", status_details=error_details)
        assert "Error" in tooltip

        # 2. Status-Bar sollte Error anzeigen
        status_bar = main_window.mashcad_status_bar
        status_bar.set_status(error_msg, is_error=False, status_class="ERROR", severity="error")
        dot_style = status_bar.status_dot.styleSheet()
        assert "#ef4444" in dot_style or "red" in dot_style.lower()

        # 3. Notification sollte Error anzeigen
        main_window.show_notification("Boolean Error", error_msg, level="error",
                                     status_class="ERROR", severity="error")
        assert len(main_window.notification_manager.notifications) > 0

        # Cleanup
        for notif in main_window.notification_manager.notifications[:]:
            main_window.notification_manager.cleanup_notification(notif)

    def test_error_ux_v2_warning_recoverable_consistent(self, main_window):
        """
        B-W10-R22: WARNING_RECOVERABLE wird konsistent über alle UI-Komponenten genutzt.
        """
        from gui.browser import _format_feature_status_tooltip

        warning_msg = "Fillet: Geometrie leicht verschoben"
        warning_details = {
            "code": "tnp_ref_drift",
            "status_class": "WARNING_RECOVERABLE",
            "severity": "warning",
            "hint": "Fillet-Parameter anpassen"
        }

        # 1. Tooltip sollte Warning (Recoverable) anzeigen
        tooltip = _format_feature_status_tooltip(warning_msg, status="ERROR", status_details=warning_details)
        assert "Warning (Recoverable)" in tooltip

        # 2. Status-Bar sollte Warning (gelb) anzeigen
        status_bar = main_window.mashcad_status_bar
        status_bar.set_status(warning_msg, is_error=False, status_class="WARNING_RECOVERABLE", severity="warning")
        dot_style = status_bar.status_dot.styleSheet()
        assert "#eab308" in dot_style or "yellow" in dot_style.lower()

        # 3. Notification sollte Warning anzeigen
        main_window.show_notification("Fillet Warning", warning_msg, level="warning",
                                     status_class="WARNING_RECOVERABLE", severity="warning")
        assert len(main_window.notification_manager.notifications) > 0

        # Cleanup
        for notif in main_window.notification_manager.notifications[:]:
            main_window.notification_manager.cleanup_notification(notif)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
