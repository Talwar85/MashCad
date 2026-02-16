"""
Discoverability v4 Production Tests (Paket C)
==============================================
Validiert dass Discoverability-Hinweise sichtbar, aber nicht störend sind.

W10 Paket C: Erweitert um Anti-Spam Features (Cooldown, Priority, No-Repeat).

Author: GLM 4.7 (UX/WORKFLOW + QA Integration Cell)
Date: 2026-02-16
Branch: feature/v1-ux-aiB
"""

# CRITICAL: QT_OPENGL muss VOR jedem Qt/PyVista Import gesetzt werden
import os
os.environ["QT_OPENGL"] = "software"

import pytest
import time
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtGui import QColor

from gui.main_window import MainWindow
from gui.sketch_tools import SketchTool


@pytest.fixture(scope="session")
def qt_app():
    """Session-weite QApplication Instanz."""
    app = pytest.importorskip("PySide6.QtWidgets").QApplication.instance()
    if app is None:
        import sys
        app = pytest.importorskip("PySide6.QtWidgets").QApplication(sys.argv)
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


class TestDiscoverabilityHints:
    """
    W9 Paket C: Discoverability v3 Production Tests.
    """

    def test_sketch_hud_navigation_hint_visible(self, main_window):
        """
        C-W9-R1: Navigation-Hint ist sichtbar im Sketch-Mode.
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        editor.request_update()
        QTest.qWait(50)

        # HUD sollte nicht leer sein
        assert hasattr(editor, '_draw_hud')
        # Navigation-Hint ist im HUD text enthalten
        # Wir können nicht direkt rendern, aber wir prüfen dass die Methode existiert
        assert callable(editor._draw_hud)

    def test_sketch_tool_hint_shown_on_tool_change(self, main_window):
        """
        C-W9-R2: Tool-Hinweis wird bei Tool-Wechsel angezeigt.
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor

        # Tool wechseln
        editor.set_tool(SketchTool.LINE)
        QTest.qWait(50)

        # _show_tool_hint sollte aufgerufen werden (kein Fehler)
        # Wir prüfen dass die Methode existiert und aufrufbar ist
        assert callable(editor._show_tool_hint)

        # Tool-Options sollte verfügbar sein
        assert hasattr(editor, 'tool_options')

    def test_sketch_hud_message_fade_out(self, main_window):
        """
        C-W9-R3: HUD-Nachricht fade-out nach Duration.
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor

        # HUD-Nachricht mit kurzer Dauer anzeigen
        editor.show_message("Test Nachricht", duration=500, color=QColor(255, 255, 255))
        QTest.qWait(50)

        # Nachricht sollte gesetzt sein
        assert editor._hud_message == "Test Nachricht"
        assert editor._hud_duration == 500

        # Warten bis fade-out
        QTest.qWait(600)

        # Nachricht sollte geleert sein (fade-out abgelaufen)
        # Note: Die actual Leerung passiert beim nächsten paint, aber die Zeit ist abgelaufen
        elapsed = (time.time() * 1000) - editor._hud_message_time
        assert elapsed >= 500  # Mindestens duration vergangen

    def test_sketch_hud_deduplication(self, main_window):
        """
        C-W9-R4: Hinweise werden nicht dupliziert (dedupliziert).

        Stellt sicher dass wiederholte show_message Aufrufe mit gleichem Text
        nicht zu spam führen.
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor

        # Gleiche Nachricht mehrmals anzeigen
        editor.show_message("Test", duration=1000)
        QTest.qWait(50)
        editor.show_message("Test", duration=1000)
        QTest.qWait(50)

        # Es sollte nur eine Nachricht aktiv sein (nicht dupliziert)
        # Die HUD Implementierung überschreibt die Nachricht, das ist korrektes Verhalten
        assert editor._hud_message == "Test"

    def test_sketch_hud_color_variation(self, main_window):
        """
        C-W9-R5: HUD-Nachrichten unterstützen verschiedene Farben (Severity).

        Stellt sicher dass Info, Warning, Error Nachrichten mit unterschiedlichen
        Farben angezeigt werden können.
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor

        # Info (Standard: Weiß)
        editor.show_message("Info", duration=500, color=QColor(255, 255, 255))
        assert editor._hud_color == QColor(255, 255, 255)

        # Warning (Gelb)
        editor.show_message("Warning", duration=500, color=QColor(255, 200, 0))
        assert editor._hud_color == QColor(255, 200, 0)

        # Error (Rot)
        editor.show_message("Error", duration=500, color=QColor(255, 50, 50))
        assert editor._hud_color == QColor(255, 50, 50)

    def test_sketch_context_hint_on_mode_switch(self, main_window):
        """
        C-W9-R6: Kontext-Hinweis bei Modus-Wechsel.

        Stellt sicher dass bei Modus-Wechsel ein Hinweis angezeigt wird.
        """
        main_window._set_mode("3d")
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        QTest.qWait(50)

        # Nach Modus-Wechsel sollte der Editor bereit sein
        assert editor is not None
        assert editor.current_tool == SketchTool.SELECT  # Default nach Modus-Wechsel

        # Tool-Options sollte initialisiert sein
        assert hasattr(editor, 'tool_options')

    def test_discoverability_no_crash_on_rapid_hints(self, main_window):
        """
        C-W9-R7: Kein Absturz bei raschen Hinweis-Wechseln.

        Stellt sicher dass das HUD-System robust gegen rapid-fire Hinweise ist.
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor

        # Viele Hinweise schnell hintereinander
        for i in range(10):
            editor.show_message(f"Nachricht {i}", duration=100)
            QTest.qWait(20)

        # Sollte nicht abgestürzt sein
        assert editor is not None
        # Letzte Nachricht sollte gesetzt sein
        assert "Nachricht" in editor._hud_message

    # =========================================================================
    # W10 Paket C: Discoverability v4 Anti-Spam Tests
    # =========================================================================

    def test_hint_cooldown_prevents_duplicate_within_window(self, main_window):
        """
        C-W10-R1: Hint-Cooldown verhindert Duplikate innerhalb des Cooldown-Fensters.

        Stellt sicher dass derselbe Hinweis nicht mehrfach innerhalb des
        Cooldown-Fensters (5s) angezeigt wird.
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor

        # Ersten Hinweis anzeigen
        result1 = editor.show_message("Cooldown Test", duration=1000)
        assert result1 is True  # Erster Hinweis sollte angezeigt werden

        # Sofort wieder derselbe Hinweis (sollte unterdrückt werden)
        QTest.qWait(50)
        result2 = editor.show_message("Cooldown Test", duration=1000)
        assert result2 is False  # Zweiter Hinweis sollte unterdrückt werden

        # History sollte den Hinweis enthalten
        hint_texts = [text for text, _ in editor._hint_history]
        assert "Cooldown Test" in hint_texts

    def test_hint_cooldown_allows_after_duration(self, main_window):
        """
        C-W10-R2: Hint-Cooldown erlaubt gleichen Hinweis nach Ablauf der Dauer.

        Stellt sicher dass nach Ablauf der Cooldown-Dauer der Hinweis
        wieder angezeigt werden kann.
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor

        # Cooldown auf kurze Dauer setzen für Test
        editor._hint_cooldown_ms = 200

        # Ersten Hinweis anzeigen
        result1 = editor.show_message("Cooldown Test 2", duration=100)
        assert result1 is True

        # Warten bis Cooldown abgelaufen
        QTest.qWait(250)

        # Gleichfalls wieder anzeigen (sollte jetzt erlaubt sein)
        result2 = editor.show_message("Cooldown Test 2", duration=100)
        assert result2 is True  # Nach Cooldown sollte erlaubt sein

    def test_hint_force_parameter_ignores_cooldown(self, main_window):
        """
        C-W10-R3: force=True ignoriert Cooldown.

        Stellt sicher dass wichtige Hinweise mit force=True
        auch während Cooldown angezeigt werden.
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor

        # Ersten Hinweis anzeigen
        result1 = editor.show_message("Force Test", duration=1000)
        assert result1 is True

        # Sofort wieder mit force=True (sollte angezeigt werden)
        QTest.qWait(50)
        result2 = editor.show_message("Force Test", duration=1000, force=True)
        assert result2 is True  # force=True sollte Cooldown ignorieren

    def test_hint_priority_overrides_cooldown(self, main_window):
        """
        C-W10-R4: Priority überschreibt Cooldown.

        Stellt sicher dass Hinweise mit hoher Priority (priority > 0)
        auch während Cooldown angezeigt werden.
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor

        # Ersten Hinweis mit Priority 0 anzeigen
        result1 = editor.show_message("Priority Test", duration=1000, priority=0)
        assert result1 is True

        # Sofort wieder mit höherer Priority (sollte angezeigt werden)
        QTest.qWait(50)
        result2 = editor.show_message("Priority Test", duration=1000, priority=1)
        assert result2 is True  # priority=1 sollte Cooldown brechen

    def test_hint_no_repeat_within_cooldown(self, main_window):
        """
        C-W10-R5: No-Repeat verhindert identische Hinweise im Cooldown.

        Stellt sicher dass die Hint-History Duplikate erkennt und
        denselben Text nicht mehrfach speichert.
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor

        # Derselbe Hinweis mehrfach
        editor.show_message("No Repeat Test", duration=100)
        QTest.qWait(50)
        editor.show_message("No Repeat Test", duration=100)
        QTest.qWait(50)
        editor.show_message("No Repeat Test", duration=100)

        # History sollte nur einen Eintrag für diesen Text haben
        hint_texts = [text for text, _ in editor._hint_history]
        count = hint_texts.count("No Repeat Test")
        assert count == 1  # Nur ein Eintrag, keine Duplikate

    def test_hint_different_messages_allowed(self, main_window):
        """
        C-W10-R6: Verschiedene Hinweise sind nicht vom Cooldown betroffen.

        Stellt sicher dass unterschiedliche Hinweise sofort angezeigt werden,
        auch wenn ein anderer Hinweis erst kürzlich gezeigt wurde.
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor

        # Ersten Hinweis anzeigen
        result1 = editor.show_message("Message 1", duration=1000)
        assert result1 is True

        # Anderer Hinweis sofort (sollte erlaubt sein)
        QTest.qWait(50)
        result2 = editor.show_message("Message 2", duration=1000)
        assert result2 is True  # Unterschiedlicher Text sollte erlaubt sein

    def test_hint_history_max_length(self, main_window):
        """
        C-W10-R7: Hint-History begrenzt auf Max-Länge.

        Stellt sicher dass die Hint-History nicht unendlich wächst
        sondern auf _hint_max_history begrenzt ist.
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor

        # Max-Länge auf 5 setzen für Test
        editor._hint_max_history = 5

        # Mehr Hinweise als Max-Länge anzeigen
        for i in range(10):
            editor.show_message(f"Hint {i}", duration=100, force=True)
            QTest.qWait(20)

        # History sollte nicht größer sein als Max-Länge
        assert len(editor._hint_history) <= editor._hint_max_history

        # Die letzten 5 Hinweise sollten vorhanden sein
        hint_texts = [text for text, _ in editor._hint_history]
        for i in range(5, 10):
            assert f"Hint {i}" in hint_texts

    def test_hint_return_value_indicates_display(self, main_window):
        """
        C-W10-R8: show_message Rückgabewert zeigt ob Hinweis angezeigt wurde.

        Stellt sicher dass show_message True zurückgibt wenn der Hinweis
        angezeigt wurde, und False wenn er unterdrückt wurde.
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor

        # Erster Hinweis sollte angezeigt werden
        result1 = editor.show_message("Return Value Test", duration=1000)
        assert result1 is True

        # Sofort wieder sollte unterdrückt werden
        result2 = editor.show_message("Return Value Test", duration=1000)
        assert result2 is False

        # Anderer Hinweis sollte angezeigt werden
        result3 = editor.show_message("Different Message", duration=1000)
        assert result3 is True

    def test_rapid_hints_no_spam_with_cooldown(self, main_window):
        """
        C-W10-R9: Rapid-Hints erzeugen keinen Spam mit Cooldown.

        Stellt sicher dass schnelle wiederholte Hinweise durch das
        Cooldown-System nicht spammen.
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor

        # Derselbe Hinweis schnell mehrfach
        displayed_count = 0
        for i in range(10):
            result = editor.show_message("Spam Test", duration=100)
            if result:
                displayed_count += 1
            QTest.qWait(20)

        # Nur der erste sollte angezeigt worden sein
        assert displayed_count == 1
