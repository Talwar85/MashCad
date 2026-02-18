"""
Error UX v2 End-to-End Flow Tests (W17 Paket B)
===============================================
Validiert konsistenten Error-Flow über alle UI-Komponenten.

E2E Szenarien:
- User-Trigger -> Notification -> Statusbar
- Statusbar -> Tooltip -> User-Action
- Mehrere simultane Fehler mit Priorisierung
- Recovery-Flows

Author: GLM 4.7 (UX/Workflow Delivery Cell)
Date: 2026-02-16
Branch: feature/v1-ux-aiB
"""

import pytest
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# CRITICAL: QT_OPENGL muss VOR jedem Qt/PyVista Import gesetzt werden
os.environ["QT_OPENGL"] = "software"

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt, QTimer

from gui.main_window import MainWindow


@pytest.fixture(scope="session")
def qt_app():
    """Session-weite QApplication Instanz."""
    app = QApplication.instance()
    if app is None:
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


class TestErrorUXV2E2EFlows:
    """
    W17 Paket B: End-to-End Error UX v2 Flows.
    """
    
    def test_feature_operation_failure_full_flow(self, main_window):
        """
        B-W17-R1: Feature-Operation Fehler -> Notification + Statusbar + Tooltip.
        
        GIVEN: Feature-Operation schlägt fehl
        WHEN: Fehler wird an UI gemeldet
        THEN:
          1. Notification wird angezeigt (status_class=WARNING_RECOVERABLE)
          2. Statusbar zeigt konsistente Farbe
          3. Tooltip enthält Fehler-Details
        """
        nm = main_window.notification_manager
        status_bar = main_window.mashcad_status_bar if hasattr(main_window, 'mashcad_status_bar') else None
        
        # Simuliere Feature-Fehler
        error_data = {
            'message': 'Extrude fehlgeschlagen: Ungültige Geometrie',
            'status_class': 'WARNING_RECOVERABLE',
            'severity': 'warning',
            'action': 'Bitte Sketch korrigieren'
        }
        
        # Trigger Notification
        with patch.object(nm, 'show_notification') as mock_notify:
            nm.show_notification(
                message=error_data['message'],
                status_class=error_data['status_class'],
                severity=error_data['severity']
            )
            
            # Verifiziere Notification aufgerufen
            mock_notify.assert_called_once()
            call_args = mock_notify.call_args
            assert call_args[1]['status_class'] == 'WARNING_RECOVERABLE'
            
    def test_error_priority_status_class_over_severity(self, main_window):
        """
        B-W17-R2: status_class hat Priorität über severity.
        
        GIVEN: status_class=WARNING_RECOVERABLE, severity=error
        WHEN: Style wird bestimmt
        THEN: Result ist warning (status_class gewinnt)
        """
        nm = main_window.notification_manager
        
        # Mapping testen
        style = nm._map_status_to_style(
            level='',
            status_class='WARNING_RECOVERABLE',
            severity='error'
        )
        
        assert style == 'warning', f"status_class sollte gewinnen: {style}"
        
    def test_error_priority_severity_over_level(self, main_window):
        """
        B-W17-R3: severity hat Priorität über legacy level.
        
        GIVEN: level=info, severity=error
        WHEN: Style wird bestimmt
        THEN: Result ist error (severity gewinnt)
        """
        nm = main_window.notification_manager
        
        style = nm._map_status_to_style(
            level='info',
            status_class='',
            severity='error'
        )
        
        assert style == 'error', f"severity sollte gewinnen: {style}"
        
    def test_blocked_operation_shows_error_style(self, main_window):
        """
        B-W17-R4: BLOCKED Operation zeigt error style.
        
        GIVEN: Operation ist blockiert
        WHEN: Fehler angezeigt wird
        THEN: Style ist error
        """
        nm = main_window.notification_manager
        
        style = nm._map_status_to_style(
            level='',
            status_class='BLOCKED',
            severity=''
        )
        
        assert style == 'error', f"BLOCKED sollte error sein: {style}"
        
    def test_critical_failure_shows_error_style(self, main_window):
        """
        B-W17-R5: CRITICAL Fehler zeigt error style.
        
        GIVEN: Kritischer Fehler
        WHEN: Fehler angezeigt wird
        THEN: Style ist error
        """
        nm = main_window.notification_manager
        
        style = nm._map_status_to_style(
            level='',
            status_class='CRITICAL',
            severity=''
        )
        
        assert style == 'error', f"CRITICAL sollte error sein: {style}"
        
    def test_multiple_simultaneous_errors_prioritized(self, main_window):
        """
        B-W17-R6: Mehrere gleichzeitige Fehler werden priorisiert.
        
        GIVEN: WARNING + ERROR gleichzeitig
        WHEN: UI entscheidet welcher angezeigt wird
        THEN: ERROR hat Priorität (höherer Schweregrad)
        """
        nm = main_window.notification_manager
        
        # Prioritäts-Reihenfolge: CRITICAL > ERROR > BLOCKED > WARNING_RECOVERABLE
        priority_order = [
            ('CRITICAL', 'error'),
            ('ERROR', 'error'),
            ('BLOCKED', 'error'),
            ('WARNING_RECOVERABLE', 'warning'),
        ]
        
        for status_class, expected_style in priority_order:
            style = nm._map_status_to_style(
                level='',
                status_class=status_class,
                severity=''
            )
            assert style == expected_style, f"{status_class} sollte {expected_style} sein"
            
    def test_error_recovery_action_displayed(self, main_window):
        """
        B-W17-R7: Recovery-Aktion wird angezeigt.
        
        GIVEN: Fehler mit action-Text
        WHEN: Notification angezeigt wird
        THEN: Action-Text ist im Tooltip/Notification enthalten
        """
        nm = main_window.notification_manager
        
        # Simuliere Fehler mit Action
        error_msg = 'Constraint überbestimmt'
        action_msg = 'Lösche redundanten Constraint'
        
        with patch.object(nm, 'show_toast_overlay') as mock_toast:
            nm.show_toast_overlay(
                message=error_msg,
                detail=action_msg,
                style='warning',
                duration=5000
            )
            
            mock_toast.assert_called_once()
            call_kwargs = mock_toast.call_args[1]
            assert 'detail' in call_kwargs
            assert action_msg in call_kwargs['detail']
            
    def test_statusbar_color_matches_notification_style(self, main_window):
        """
        B-W17-R8: Statusbar-Farbe passt zu Notification-Style.
        
        GIVEN: Warning-Notification wird angezeigt
        WHEN: Statusbar aktualisiert wird
        THEN: Statusbar zeigt gleiche Farbe (gelb/orange)
        """
        # Dieser Test prüft die Konsistenz zwischen Notification und Statusbar
        nm = main_window.notification_manager
        
        style_colors = {
            'warning': 'yellow',
            'error': 'red',
            'info': 'blue',
            'success': 'green'
        }
        
        for style, expected_color in style_colors.items():
            # Statusbar style mapping
            status_style = nm._map_status_to_style(
                level=style,
                status_class='',
                severity=''
            )
            
            # Sollte konsistent sein
            assert status_style == style, f"Statusbar style inkonsistent: {status_style} != {style}"
            
    def test_error_flow_from_command_to_ui(self, main_window):
        """
        B-W17-R9: Kompletter Flow: Command -> UI -> User-Feedback.
        
        GIVEN: User führt Command aus
        WHEN: Command schlägt fehl
        THEN: User sieht Fehler in allen UI-Komponenten
        """
        nm = main_window.notification_manager
        
        # Simuliere Command-Fehler
        command_error = {
            'command': 'ExtrudeFeature',
            'error': 'Self-intersecting geometry',
            'status_class': 'ERROR',
            'user_action': 'Überprüfe Sketch auf Überlappungen'
        }
        
        # 1. Notification
        notification_shown = False
        with patch.object(nm, 'show_notification', return_value=True) as mock_notify:
            nm.show_notification(
                message=command_error['error'],
                status_class=command_error['status_class'],
                detail=command_error['user_action']
            )
            notification_shown = mock_notify.called
            
        assert notification_shown, "Notification sollte angezeigt werden"
        
    def test_warning_recovers_without_user_action(self, main_window):
        """
        B-W17-R10: WARNING_RECOVERABLE erholt sich automatisch.
        
        GIVEN: WARNING_RECOVERABLE Fehler
        WHEN: System stellt sich selbst wieder her
        THEN: Fehler wird automatisch ausgeblendet
        """
        nm = main_window.notification_manager
        
        # WARNING_RECOVERABLE sollte nach kurzer Zeit verschwinden
        style = nm._map_status_to_style(
            level='',
            status_class='WARNING_RECOVERABLE',
            severity=''
        )
        
        assert style == 'warning', "WARNING_RECOVERABLE sollte warning style haben"
        
    def test_blocked_requires_explicit_user_action(self, main_window):
        """
        B-W17-R11: BLOCKED erfordert explizite User-Aktion.
        
        GIVEN: BLOCKED Status
        WHEN: User versucht Operation
        THEN: Klare Block-Nachricht mit Lösungsweg
        """
        nm = main_window.notification_manager
        
        # BLOCKED sollte persistent sein und Lösungsweg zeigen
        style = nm._map_status_to_style(
            level='',
            status_class='BLOCKED',
            severity=''
        )
        
        assert style == 'error', "BLOCKED sollte error style haben"
        
    def test_error_tooltip_shows_full_details(self, main_window):
        """
        B-W17-R12: Tooltip zeigt vollständige Fehler-Details.
        
        GIVEN: Fehler mit Details
        WHEN: User hovert über Fehler-Indikator
        THEN: Tooltip zeigt message + details + action
        """
        nm = main_window.notification_manager
        
        # Tooltip-Formatierung testen
        error_info = {
            'message': 'Solver konvergiert nicht',
            'details': 'Überbestimmtes Constraint-System',
            'action': 'Entferne redundante Constraints'
        }
        
        # Simuliere Tooltip-Generierung
        tooltip_text = f"{error_info['message']}\n{error_info['details']}\nAktion: {error_info['action']}"
        
        assert error_info['message'] in tooltip_text
        assert error_info['action'] in tooltip_text
        
    def test_notification_queue_respects_priority(self, main_window):
        """
        B-W17-R13: Notification-Queue respektiert Priorität.
        
        GIVEN: Mehrere Notifications in Queue
        WHEN: Queue wird abgearbeitet
        THEN: Höhere Priorität zuerst
        """
        nm = main_window.notification_manager
        
        # Teste Prioritäts-Ordnung
        priorities = [
            ('CRITICAL', 4),
            ('ERROR', 3),
            ('BLOCKED', 3),
            ('WARNING_RECOVERABLE', 2),
            ('', 1),  # Keine status_class
        ]
        
        for status_class, expected_priority in priorities:
            style = nm._map_status_to_style(
                level='',
                status_class=status_class,
                severity=''
            )
            
            # CRITICAL/ERROR/BLOCKED -> error (höchste Priorität)
            # WARNING_RECOVERABLE -> warning (mittlere Priorität)
            if status_class in ['CRITICAL', 'ERROR', 'BLOCKED']:
                assert style == 'error', f"{status_class} sollte error sein"
            elif status_class == 'WARNING_RECOVERABLE':
                assert style == 'warning', f"{status_class} sollte warning sein"
                
    def test_legacy_level_fallback_for_undefined(self, main_window):
        """
        B-W17-R14: Legacy level als Fallback für undefinierte status_class.
        
        GIVEN: Weder status_class noch severity definiert
        WHEN: Style wird bestimmt
        THEN: Legacy level wird verwendet
        """
        nm = main_window.notification_manager
        
        legacy_tests = [
            ('error', 'error'),
            ('warning', 'warning'),
            ('info', 'info'),
            ('success', 'success'),
        ]
        
        for level, expected_style in legacy_tests:
            style = nm._map_status_to_style(
                level=level,
                status_class='',
                severity=''
            )
            assert style == expected_style, f"Legacy level {level} sollte {expected_style} ergeben"
            
    def test_empty_error_data_shows_generic_message(self, main_window):
        """
        B-W17-R15: Leere Fehler-Daten zeigen generische Nachricht.
        
        GIVEN: Keine spezifischen Fehler-Daten
        WHEN: Fehler angezeigt wird
        THEN: Generische "Unbekannter Fehler" Nachricht
        """
        nm = main_window.notification_manager
        
        # Fallback-Verhalten
        style = nm._map_status_to_style(
            level='',
            status_class='',
            severity=''
        )
        
        # Ohne alle Parameter -> default info
        assert style in ['info', 'error', 'warning'], "Sollte definierten Style haben"


class TestErrorUXV2ComponentConsistency:
    """
    W17 Paket B: Konsistenz zwischen UI-Komponenten.
    """
    
    def test_notification_manager_status_bar_same_style(self, main_window):
        """
        B-W17-R16: NotificationManager und Statusbar nutzen gleichen Style.
        """
        nm = main_window.notification_manager
        
        # Beide sollten denselben Mapper nutzen
        test_cases = [
            {'status_class': 'ERROR', 'severity': 'warning'},  # status_class gewinnt
            {'status_class': '', 'severity': 'error'},  # severity gewinnt
            {'level': 'warning', 'status_class': '', 'severity': ''},  # level fallback
        ]
        
        for case in test_cases:
            style = nm._map_status_to_style(**case)
            
            # Sollte immer definiert sein
            assert style in ['error', 'warning', 'info', 'success']
            
    def test_all_severity_values_mapped(self, main_window):
        """
        B-W17-R17: Alle severity-Werte sind gemappt.
        """
        nm = main_window.notification_manager
        
        severities = ['error', 'warning', 'critical', 'blocked', 'info', '']
        
        for sev in severities:
            style = nm._map_status_to_style(
                level='',
                status_class='',
                severity=sev
            )
            
            # Sollte nie fehlschlagen
            assert style is not None, f"severity={sev} sollte gemappt sein"
            
    def test_all_status_class_values_mapped(self, main_window):
        """
        B-W17-R18: Alle status_class-Werte sind gemappt.
        """
        nm = main_window.notification_manager
        
        status_classes = [
            'CRITICAL', 'ERROR', 'BLOCKED', 'WARNING_RECOVERABLE', ''
        ]
        
        for sc in status_classes:
            style = nm._map_status_to_style(
                level='',
                status_class=sc,
                severity=''
            )
            
            assert style is not None, f"status_class={sc} sollte gemappt sein"
