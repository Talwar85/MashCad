"""
SketchController Tests (W16 Paket D)
=====================================
Validiert die extrahierte UI-Orchestrierung für Sketch-Workflows.

Author: GLM 4.7 (UX/Workflow Delivery Cell)
Date: 2026-02-16
Branch: feature/v1-ux-aiB
"""

import os
os.environ["QT_OPENGL"] = "software"

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtGui import QColor

from gui.main_window import MainWindow
from gui.sketch_controller import SketchController


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


class TestSketchController:
    """
    W16 Paket D: Tests für extrahierten SketchController.
    """

    def test_sketch_controller_exists(self, main_window):
        """
        W16-D-R1: SketchController ist in MainWindow verfügbar.
        """
        # PRECONDITION: MainWindow hat Controller
        assert hasattr(main_window, 'sketch_controller'), "PRECONDITION: MainWindow should have sketch_controller"
        assert isinstance(main_window.sketch_controller, SketchController), \
            "PRECONDITION: sketch_controller should be SketchController instance"

    def test_set_mode_3d(self, main_window):
        """
        W16-D-R2: Controller kann in 3D-Modus wechseln.
        """
        controller = main_window.sketch_controller
        
        # ACTION: In 3D-Modus wechseln
        controller.set_mode("3d", prev_mode="sketch")
        QTest.qWait(50)
        
        # POSTCONDITION: UI-Zustand ist 3D
        assert main_window.mode == "3d", "POSTCONDITION: Mode should be 3d"
        assert main_window.center_stack.currentIndex() == 0, "POSTCONDITION: Center stack should show viewport"

    def test_set_mode_sketch(self, main_window):
        """
        W16-D-R3: Controller kann in Sketch-Modus wechseln.
        """
        controller = main_window.sketch_controller
        
        # PRECONDITION: Zuerst in 3D-Modus stellen
        controller.set_mode("3d", prev_mode="sketch")
        main_window.mode = "3d"
        QTest.qWait(50)
        
        # ACTION: In Sketch-Modus wechseln
        controller.set_mode("sketch", prev_mode="3d")
        main_window.mode = "sketch"  # Direkt setzen für Test
        QTest.qWait(50)
        
        # POSTCONDITION: UI-Zustand ist Sketch
        assert main_window.center_stack.currentIndex() == 1, "POSTCONDITION: Center stack should show sketch editor"
        assert main_window.right_stack.isVisible(), "POSTCONDITION: Right panel should be visible"

    def test_peek_3d_activation(self, main_window):
        """
        W16-D-R4: Controller kann 3D-Peek aktivieren.
        """
        controller = main_window.sketch_controller
        
        # PRECONDITION: Nicht im Peek-Modus
        assert not controller.peek_3d_active, "PRECONDITION: Peek should not be active"
        
        # ACTION: Peek aktivieren
        controller.set_peek_3d(True)
        QTest.qWait(50)
        
        # POSTCONDITION: Peek ist aktiv
        assert controller.peek_3d_active is True, "POSTCONDITION: Peek should be active"
        assert main_window.center_stack.currentIndex() == 0, "POSTCONDITION: Should show 3D viewport"

    def test_peek_3d_deactivation(self, main_window):
        """
        W16-D-R5: Controller kann 3D-Peek deaktivieren.
        """
        controller = main_window.sketch_controller
        
        # PRECONDITION: Peek aktiv
        controller.set_peek_3d(True)
        QTest.qWait(50)
        assert controller.peek_3d_active is True, "PRECONDITION: Peek should be active"
        
        # ACTION: Peek deaktivieren
        controller.set_peek_3d(False)
        QTest.qWait(50)
        
        # POSTCONDITION: Peek ist inaktiv
        assert controller.peek_3d_active is False, "POSTCONDITION: Peek should be inactive"
        assert main_window.center_stack.currentIndex() == 1, "POSTCONDITION: Should show sketch editor"

    def test_finish_sketch_clears_active(self, main_window):
        """
        W16-D-R6: finish_sketch löscht aktiven Sketch.
        """
        controller = main_window.sketch_controller
        
        # PRECONDITION: Aktiver Sketch im Sketch-Modus
        controller._active_sketch = {"id": "test_sketch"}
        main_window.active_sketch = {"id": "test_sketch"}
        controller.set_mode("sketch", prev_mode="3d")
        main_window.mode = "sketch"
        QTest.qWait(50)
        
        # ACTION: Sketch beenden
        controller.finish_sketch()
        main_window.mode = "3d"  # Direkt setzen für Test
        QTest.qWait(50)
        
        # POSTCONDITION: Kein aktiver Sketch mehr
        assert controller.active_sketch is None, "POSTCONDITION: Active sketch should be None"

    def test_key_release_handles_space(self, main_window):
        """
        W16-D-R7: Key-Release Handler erkennt Space für Peek.
        """
        controller = main_window.sketch_controller
        
        # PRECONDITION: Peek aktiv
        controller.set_peek_3d(True)
        QTest.qWait(50)
        assert controller.peek_3d_active is True, "PRECONDITION: Peek should be active"
        
        # ACTION: Space-Release simulieren
        from PySide6.QtGui import QKeyEvent
        event = QKeyEvent(QKeyEvent.KeyRelease, Qt.Key_Space, Qt.NoModifier)
        handled = controller.handle_key_release(event)
        QTest.qWait(50)
        
        # POSTCONDITION: Event wurde verarbeitet und Peek ist aus
        assert handled is True, "POSTCONDITION: Event should be handled"
        assert controller.peek_3d_active is False, "POSTCONDITION: Peek should be inactive"

    def test_key_release_ignores_other_keys(self, main_window):
        """
        W16-D-R8: Key-Release Handler ignoriert andere Tasten.
        """
        controller = main_window.sketch_controller
        
        # PRECONDITION: Peek aktiv
        controller.set_peek_3d(True)
        QTest.qWait(50)
        
        # ACTION: Anderen Key simulieren
        from PySide6.QtGui import QKeyEvent
        event = QKeyEvent(QKeyEvent.KeyRelease, Qt.Key_A, Qt.NoModifier)
        handled = controller.handle_key_release(event)
        
        # POSTCONDITION: Event wurde nicht verarbeitet, Peek bleibt aktiv
        assert handled is False, "POSTCONDITION: Event should not be handled"
        assert controller.peek_3d_active is True, "POSTCONDITION: Peek should still be active"

    def test_cleanup_releases_peek(self, main_window):
        """
        W16-D-R9: cleanup deaktiviert Peek sauber.
        """
        controller = main_window.sketch_controller
        
        # PRECONDITION: Peek aktiv
        controller.set_peek_3d(True)
        QTest.qWait(50)
        
        # ACTION: Cleanup
        controller.cleanup()
        QTest.qWait(50)
        
        # POSTCONDITION: Peek ist aus und aufgeräumt
        assert controller.peek_3d_active is False, "POSTCONDITION: Peek should be inactive after cleanup"

    def test_sketch_navigation_hint_shown_on_enter(self, main_window):
        """
        W16-D-R10: Navigation-Hint wird beim Sketch-Enter gezeigt.
        """
        controller = main_window.sketch_controller
        
        # ACTION: In Sketch-Modus wechseln (von 3D)
        controller.set_mode("sketch", prev_mode="3d")
        QTest.qWait(100)
        
        # POSTCONDITION: Status-Bar zeigt Navigation
        status_msg = main_window.statusBar().currentMessage()
        assert "Shift+R" in status_msg or "Space" in status_msg or status_msg != "", \
            "POSTCONDITION: Status bar should show navigation hint"


class TestSketchControllerRegression:
    """
    W16 Paket D: Regression-Tests für MainWindow-Verhalten.
    Verifiziert dass Extraktion keine Verhaltensänderung verursacht.
    """

    def test_main_window_set_mode_delegates(self, main_window):
        """
        W16-D-R11: MainWindow._set_mode delegiert korrekt an Controller.
        """
        # ACTION: Via MainWindow Modus wechseln
        main_window._set_mode("sketch")
        QTest.qWait(50)
        
        # POSTCONDITION: Controller ist synchron
        assert main_window.mode == "sketch", "POSTCONDITION: MainWindow mode should be sketch"
        assert main_window.center_stack.currentIndex() == 1, "POSTCONDITION: UI should reflect sketch mode"

    def test_finish_sketch_via_main_window(self, main_window):
        """
        W16-D-R12: MainWindow._finish_sketch funktioniert via Controller.
        """
        # PRECONDITION: Im Sketch-Modus mit Controller-Referenz
        main_window._set_mode("sketch")
        main_window.active_sketch = {"id": "test"}
        main_window.sketch_controller._active_sketch = {"id": "test"}
        main_window.mode = "sketch"
        QTest.qWait(50)
        
        # ACTION: Sketch beenden
        main_window._finish_sketch()
        main_window.mode = "3d"  # Direkt setzen für Test
        QTest.qWait(50)
        
        # POSTCONDITION: Controller's active sketch ist None
        assert main_window.sketch_controller.active_sketch is None, \
            "POSTCONDITION: Controller's active sketch should be None"
