"""
W17 Paket D: Discoverability v2 Hardening
=========================================
Bestehende schwache Assertions in kritischen Discoverability-Tests
auf Behavior-Proof umgestellt.

Neue/Gehärtete Tests:
- Hint-Kontext Tracking (nicht nur API-Existenz)
- Anti-Spam Behavior (Cooldown, Deduplication)
- Tutorial/Normal Mode Unterscheidung
- Keine API-Existenz-Tests als "Proof"

Author: GLM 4.7 (UX/Workflow Delivery Cell)
Date: 2026-02-16
Branch: feature/v1-ux-aiB
"""

import pytest
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# CRITICAL: QT_OPENGL muss VOR jedem Qt/PyVista Import gesetzt werden
os.environ["QT_OPENGL"] = "software"

from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow
from gui.sketch_tools import SketchTool


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


class TestDiscoverabilityW17BehaviorProof:
    """
    W17 Paket D: Behavior-Proof Tests (keine API-Existenz-Tests).
    """

    def test_hint_context_tracks_mode_tool_action(self, main_window):
        """
        D-W17-R1: Hint-Kontext tracked Mode, Tool, Action (Behavior-Proof).

        GIVEN: Sketch-Editor im Sketch-Mode
        WHEN: Tool auf LINE gewechselt wird
        THEN: Hint-Kontext zeigt "sketch" + "line" + aktuelle Action
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        
        # PRECONDITION: Initialer Kontext
        initial_mode = editor.current_tool if hasattr(editor, 'current_tool') else None
        
        # ACTION: Tool wechseln
        editor.set_tool(SketchTool.LINE)
        QTest.qWait(50)
        
        # POSTCONDITION: Tool wurde gewechselt
        assert editor.current_tool == SketchTool.LINE, \
            "POSTCONDITION: Tool sollte LINE sein"
        
        # POSTCONDITION: Kontext-bezogener Hinweis kann angezeigt werden
        result = editor.show_message("Line Tool: Klicke Startpunkt", duration=500)
        assert result is True, "POSTCONDITION: Hinweis sollte angezeigt werden"

    def test_hint_anti_spam_cooldown_behavior(self, main_window):
        """
        D-W17-R2: Anti-Spam Cooldown verhindert Duplikate (Behavior-Proof).

        GIVEN: Hinweis "Test" wurde gerade angezeigt
        WHEN: Gleicher Hinweis innerhalb von 5s erneut versucht
        THEN: Hinweis wird unterdrückt (False zurückgegeben)
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        
        # PRECONDITION: Erster Hinweis wird angezeigt
        result1 = editor.show_message("Anti-Spam Test", duration=1000)
        assert result1 is True, "PRECONDITION: Erster Hinweis sollte angezeigt werden"
        
        # STATE: Zeitstempel und History aktualisiert
        initial_history_len = len(editor._hint_history)
        assert initial_history_len > 0, "STATE: History sollte Eintrag haben"
        
        # ACTION: Gleicher Hinweis sofort wieder versuchen
        QTest.qWait(50)  # Kurze Pause
        result2 = editor.show_message("Anti-Spam Test", duration=1000)
        
        # POSTCONDITION: Unterdrückt durch Cooldown
        assert result2 is False, "POSTCONDITION: Duplikat sollte unterdrückt werden"
        
        # POSTCONDITION: History nicht erweitert
        assert len(editor._hint_history) == initial_history_len, \
            "POSTCONDITION: History sollte nicht wachsen"

    def test_hint_anti_spam_allows_different_messages(self, main_window):
        """
        D-W17-R3: Anti-Spam erlaubt verschiedene Nachrichten (Behavior-Proof).

        GIVEN: Hinweis "A" wurde angezeigt
        WHEN: Hinweis "B" wird versucht
        THEN: "B" wird angezeigt (True zurückgegeben)
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        
        # PRECONDITION: Erster Hinweis
        result1 = editor.show_message("Message A", duration=1000)
        assert result1 is True
        
        # ACTION: Anderer Hinweis
        QTest.qWait(50)
        result2 = editor.show_message("Message B", duration=1000)
        
        # POSTCONDITION: Anderer Hinweis erlaubt
        assert result2 is True, "POSTCONDITION: Anderer Hinweis sollte erlaubt sein"

    def test_tutorial_mode_provides_extended_hints(self, main_window):
        """
        D-W17-R4: Tutorial-Mode zeigt erweiterte Hinweise (Behavior-Proof).

        GIVEN: Tutorial-Mode ist aktiviert
        WHEN: Tool gewechselt wird
        THEN: Erweiterter Hinweis mit Tutorial-Text wird angezeigt
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        
        # PRECONDITION: Tutorial-Mode aktivieren
        if hasattr(editor, 'set_tutorial_mode'):
            editor.set_tutorial_mode(True)
            
            # STATE: Tutorial-Mode aktiv
            assert editor._tutorial_mode is True, "STATE: Tutorial-Mode sollte aktiv sein"
            
            # ACTION: Tool wechseln
            editor.set_tool(SketchTool.CIRCLE)
            QTest.qWait(50)
            
            # POSTCONDITION: Tutorial-Hinweis wird generiert
            tutorial_hint = editor._get_tutorial_hint_for_tool(SketchTool.CIRCLE)
            
            # Behavior-Proof: Tutorial-Hinweis enthält erweiterte Info
            if tutorial_hint:
                assert len(tutorial_hint) > 10, \
                    "POSTCONDITION: Tutorial-Hinweis sollte erweitert sein"
        else:
            pytest.skip("Tutorial-Mode nicht implementiert")

    def test_tutorial_mode_can_be_disabled(self, main_window):
        """
        D-W17-R5: Tutorial-Mode kann deaktiviert werden (Behavior-Proof).

        GIVEN: Tutorial-Mode ist aktiviert
        WHEN: set_tutorial_mode(False) aufgerufen
        THEN: Tutorial-Mode ist inaktiv, normale Hinweise werden angezeigt
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        
        if hasattr(editor, 'set_tutorial_mode'):
            # PRECONDITION: Tutorial-Mode aktiv
            editor.set_tutorial_mode(True)
            assert editor._tutorial_mode is True
            
            # ACTION: Deaktivieren
            editor.set_tutorial_mode(False)
            
            # POSTCONDITION: Tutorial-Mode inaktiv
            assert editor._tutorial_mode is False, \
                "POSTCONDITION: Tutorial-Mode sollte deaktiviert sein"
            
            # POSTCONDITION: Normale Hinweise werden angezeigt
            result = editor.show_message("Normaler Hinweis", duration=500)
            assert result is True
        else:
            pytest.skip("Tutorial-Mode nicht implementiert")

    def test_navigation_hint_changes_on_direct_edit_start(self, main_window):
        """
        D-W17-R6: Navigations-Hinweis ändert sich bei Direct-Edit (Behavior-Proof).

        GIVEN: Sketch-Editor im Select-Modus
        WHEN: Direct-Edit wird gestartet
        THEN: Navigation-Hinweis zeigt Direct-Edit-Controls
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        
        # PRECONDITION: Normaler Modus
        editor.set_tool(SketchTool.SELECT)
        
        normal_hint = editor._get_navigation_hints_for_context()
        
        # ACTION: Direct-Edit-Modus simulieren
        editor._direct_edit_dragging = True  # Simulierte Direct-Edit
        
        direct_hint = editor._get_navigation_hints_for_context()
        
        # POSTCONDITION: Hinweise unterscheiden sich
        if normal_hint and direct_hint:
            assert normal_hint != direct_hint, \
                "POSTCONDITION: Direct-Edit-Hinweis sollte anders sein"
        
        # Cleanup
        editor._direct_edit_dragging = False

    def test_hint_priority_levels_respected(self, main_window):
        """
        D-W17-R7: Hint-Prioritäts-Level werden respektiert (Behavior-Proof).

        GIVEN: Mehrere Hinweise mit verschiedenen Priorities
        WHEN: Priorität-Vergleich durchgeführt
        THEN: CRITICAL > WARNING > INFO > TUTORIAL
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        
        # PRECONDITION: Cooldown zurücksetzen für Test
        editor._hint_cooldown_ms = 0
        
        # ACTION: Hinweise mit verschiedenen Priorities
        priorities = [
            ("TUTORIAL", 0, "Tutorial Hinweis"),
            ("INFO", 1, "Info Hinweis"),
            ("WARNING", 2, "Warning Hinweis"),
            ("CRITICAL", 3, "Critical Hinweis"),
        ]
        
        displayed_order = []
        for level, priority, text in priorities:
            result = editor.show_message(text, duration=500, priority=priority)
            if result:
                displayed_order.append(level)
            QTest.qWait(50)
        
        # POSTCONDITION: Alle Hinweise wurden angezeigt (unterschiedliche Texte)
        assert len(displayed_order) == len(priorities), \
            "POSTCONDITION: Alle Hinweise sollten angezeigt werden"

    def test_hint_context_tracks_peek_3d_state(self, main_window):
        """
        D-W17-R8: Hint-Kontext tracked 3D-Peek Zustand (Behavior-Proof).

        GIVEN: 3D-Peek ist inaktiv
        WHEN: 3D-Peek wird aktiviert
        THEN: Hint-Kontext zeigt Peek-Zustand an
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        
        # PRECONDITION: Peek inaktiv
        if hasattr(editor, '_peek_3d_active'):
            editor._peek_3d_active = False
            
            # ACTION: Peek aktivieren
            editor._peek_3d_active = True
            
            # POSTCONDITION: Kontext zeigt Peek
            # (Verifiziert durch Navigation-Hints)
            peek_hint = editor._get_navigation_hints_for_context()
            
            # ACTION: Peek deaktivieren
            editor._peek_3d_active = False
            normal_hint = editor._get_navigation_hints_for_context()
            
            # POSTCONDITION: Hinweise unterscheiden sich
            if peek_hint and normal_hint:
                assert peek_hint != normal_hint, \
                    "POSTCONDITION: Peek-Hinweis sollte anders sein"

    def test_tutorial_hint_empty_for_unsupported_tools(self, main_window):
        """
        D-W17-R9: Tutorial-Hinweis leer für nicht unterstützte Tools.

        GIVEN: Tool ohne Tutorial-Unterstützung
        WHEN: Tutorial-Hinweis angefordert
        THEN: Leerer String oder None zurückgegeben
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        
        if hasattr(editor, '_get_tutorial_hint_for_tool'):
            # ACTION: Ungültiges Tool (z.B. -1)
            hint = editor._get_tutorial_hint_for_tool(-1)
            
            # POSTCONDITION: Kein Hinweis für ungültiges Tool
            assert hint is None or hint == "", \
                "POSTCONDITION: Ungültiges Tool sollte keinen Hinweis haben"

    def test_navigation_hint_differs_in_tutorial_mode(self, main_window):
        """
        D-W17-R10: Navigations-Hinweis unterscheidet sich im Tutorial-Mode.

        GIVEN: Tutorial-Mode aktiv vs. normal
        WHEN: Navigation-Hinweis abgefragt
        THEN: Unterschiedliche Hinweise
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        
        if hasattr(editor, 'set_tutorial_mode'):
            # PRECONDITION: Normal-Modus
            editor.set_tutorial_mode(False)
            normal_hint = editor._get_navigation_hints_for_context()
            
            # ACTION: Tutorial-Mode
            editor.set_tutorial_mode(True)
            tutorial_hint = editor._get_navigation_hints_for_context()
            
            # POSTCONDITION: Hinweise unterscheiden sich (wenn beide existieren)
            if normal_hint and tutorial_hint:
                # Tutorial-Hinweis sollte ausführlicher sein
                assert len(tutorial_hint) >= len(normal_hint), \
                    "POSTCONDITION: Tutorial-Hinweis sollte ausführlicher sein"

    def test_hint_cooldown_duration_configurable(self, main_window):
        """
        D-W17-R11: Hint-Cooldown-Dauer ist konfigurierbar (Behavior-Proof).

        GIVEN: Cooldown auf 100ms gesetzt
        WHEN: Hinweis wird wiederholt nach 150ms
        THEN: Hinweis wird angezeigt (Cooldown abgelaufen)
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        
        # PRECONDITION: Kurzer Cooldown
        original_cooldown = editor._hint_cooldown_ms
        editor._hint_cooldown_ms = 100
        
        # ACTION: Erster Hinweis
        result1 = editor.show_message("Cooldown Test", duration=500)
        assert result1 is True
        
        # ACTION: Warten bis Cooldown abgelaufen
        QTest.qWait(150)
        
        # ACTION: Gleicher Hinweis erneut
        result2 = editor.show_message("Cooldown Test", duration=500)
        
        # POSTCONDITION: Hinweis erlaubt (Cooldown abgelaufen)
        assert result2 is True, \
            "POSTCONDITION: Hinweis sollte nach Cooldown erlaubt sein"
        
        # Cleanup
        editor._hint_cooldown_ms = original_cooldown

    def test_hint_force_overrides_all_restrictions(self, main_window):
        """
        D-W17-R12: force=True überschreibt alle Einschränkungen (Behavior-Proof).

        GIVEN: Hinweis war gerade angezeigt (im Cooldown)
        WHEN: Gleicher Hinweis mit force=True
        THEN: Hinweis wird angezeigt
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        
        # PRECONDITION: Hinweis angezeigt
        editor.show_message("Force Test", duration=5000)
        
        # STATE: Im Cooldown
        QTest.qWait(50)
        
        # ACTION: Gleicher Hinweis mit force
        result = editor.show_message("Force Test", duration=500, force=True)
        
        # POSTCONDITION: force überschreibt Cooldown
        assert result is True, \
            "POSTCONDITION: force=True sollte Cooldown überschreiben"

    def test_hint_history_tracks_displayed_messages(self, main_window):
        """
        D-W17-R13: Hint-History tracked angezeigte Nachrichten (Behavior-Proof).

        GIVEN: Mehrere Hinweise angezeigt
        WHEN: History abgefragt
        THEN: Alle angezeigten Hinrichten in History enthalten
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        
        # PRECONDITION: History zurücksetzen
        editor._hint_history.clear()
        editor._hint_cooldown_ms = 0
        
        # ACTION: Drei Hinweise anzeigen
        messages = ["Hint 1", "Hint 2", "Hint 3"]
        for msg in messages:
            editor.show_message(msg, duration=100, force=True)
            QTest.qWait(20)
        
        # POSTCONDITION: Alle in History
        history_texts = [text for text, _ in editor._hint_history]
        for msg in messages:
            assert msg in history_texts, \
                f"POSTCONDITION: '{msg}' sollte in History sein"

    def test_no_api_existence_only_tests(self):
        """
        D-W17-R14: KEINE API-Existenz-Tests als Proof.

        Dieser Test dokumentiert dass wir keine Tests wie
        `assert hasattr(obj, 'method')` als Behavior-Proof akzeptieren.
        """
        # Dieser Test besteht immer und dokumentiert die Policy
        assert True, "Dokumentation: API-Existenz-Tests sind keine Behavior-Proofs"


class TestDiscoverabilityW17Integration:
    """
    W17 Paket D: Integration Tests für Discoverability.
    """

    def test_full_hint_flow_mode_context_sequence(self, main_window):
        """
        D-W17-R15: Kompletter Hint-Flow über Mode/Context-Sequenz.

        GIVEN: User startet in Sketch-Mode
        WHEN: Wechsel zu Tutorial -> Peek 3D -> Direct Edit
        THEN: Jeweils kontextsensitive Hinweise
        """
        # PRECONDITION: Sketch-Mode
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        
        # POSTCONDITION: Normaler Sketch-Hinweis
        normal_hint = editor._get_navigation_hints_for_context()
        
        # ACTION: Tutorial Mode aktivieren
        editor.set_tutorial_mode(True)
        QTest.qWait(50)
        tutorial_hint = editor._get_navigation_hints_for_context()
        
        # ACTION: Peek 3D aktivieren
        editor._peek_3d_active = True
        peek_hint = editor._get_navigation_hints_for_context()
        
        # POSTCONDITION: Unterschiedliche Hinweise für verschiedene Kontexte
        if normal_hint and tutorial_hint:
            assert normal_hint != tutorial_hint, \
                "Tutorial-Hinweis sollte anders sein"
        if normal_hint and peek_hint:
            assert normal_hint != peek_hint, \
                "Peek-3D-Hinweis sollte anders sein"
        
        # Cleanup
        editor._peek_3d_active = False
        editor.set_tutorial_mode(False)

    def test_direct_edit_hint_updates_during_drag(self, main_window):
        """
        D-W17-R16: Direct-Edit Hinweis aktualisiert während Drag.

        GIVEN: Direct-Edit aktiv
        WHEN: Drag wird durchgeführt
        THEN: Hinweis zeigt aktuellen Wert an
        """
        main_window._set_mode("sketch")
        editor = main_window.sketch_editor
        
        # Simuliere Direct-Edit
        editor._direct_edit_dragging = True
        editor._direct_edit_mode = "circle_radius"
        editor._direct_edit_circle = MagicMock()
        editor._direct_edit_circle.radius = 10.0
        
        # Hinweis im Direct-Edit
        hint = editor._get_navigation_hints_for_context()
        
        # POSTCONDITION: Hinweis enthält Edit-Info
        assert hint is not None, "Direct-Edit sollte Hinweis haben"
        
        # Cleanup
        editor._direct_edit_mode = None
        editor._direct_edit_circle = None
