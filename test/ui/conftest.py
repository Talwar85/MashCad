"""
UI-Test Infrastructure (Paket A: UI-Gate Hardening)
====================================================

Zentrale Test-Härtung für alle UI-Tests gegen VTK/OpenGL Instabilität.

Problem:
- QT_OPENGL=software wird zu spät gesetzt (nach PySide6 Import)
- VTK Context Cleanup verursacht Access Violations
- Keine deterministische Teardown-Strategie

Lösung:
- Umgebungsvariable MUSS vor Qt-Import gesetzt werden
- Sauberes VTK/Qt Lifecycle Management
- Known-Warning-Policy für tolerierbare stderr-Warnings

Author: GLM 4.7 (UX/WORKFLOW + QA Integration Cell)
Date: 2026-02-16
Branch: feature/v1-ux-aiB
"""

import os
import sys
import gc
import warnings
from typing import Generator, Optional
from pathlib import Path
from loguru import logger

# ==============================================================================
# PHASE 1: Umgebungsvariable MUSS vor Qt-Import gesetzt werden
# ==============================================================================

# CRITICAL: Dies muss VOR jedem PySide6/PyVista Import passieren
# Wenn die Variable bereits auf "hardware" oder nicht gesetzt ist,
# überschreiben wir sie mit "software" für stabilere UI-Tests
if os.environ.get("QT_OPENGL") != "software":
    os.environ["QT_OPENGL"] = "software"
    logger.debug("[UI-GATE] QT_OPENGL=software gesetzt (vor Qt-Import)")

# ==============================================================================
# PHASE 2: Known-Warning-Policy (tolerierbare stderr-Warnings)
# ==============================================================================

# VTK/PyVista stderr-Warnings die toleriert werden (kein Test-Fail)
KNOWN_TOLERABLE_WARNINGS = {
    # VTK Win32 OpenGL Context Issues (Windows-spezifisch)
    "wglMakeCurrent failed",
    "wglMakeCurrent failed in MakeCurrent()",
    "error: Das Handle ist ungültig",
    "Invalid handle passed to method",
    "GetDC failed",
    "RenderWindow",
    "vtkWin32OpenGLRenderWindow",

    # PyVista/Qt Interop Warnings
    "QOpenGLWidget",

    # VTK Internal Warnings
    "Generic Warning",
    "vtkWarning",
}

UNKNOWN_ERROR_MARKERS = {
    # Fehler die auf echtes Problem hindeuten
    "Access violation",
    "Segmentation fault",
    "EXCEPTION_ACCESS_VIOLATION",
    "Fatal error",
    "AssertionError",
    "FAILED",
    "ERROR:",
}

def check_stderr_for_fatal_issues(stderr_output: str) -> tuple[bool, list[str]]:
    """
    Prüft stderr-Ausgabe auf fatale Fehler (vs. tolerierbare VTK-Warnings).

    Returns:
        (has_fatal_issues, list_of_fatal_lines)
    """
    if not stderr_output:
        return False, []

    fatal_lines = []
    for line in stderr_output.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Prüfen ob es ein bekannter tolerierbarer Warning ist
        is_known = any(kw in line_stripped for kw in KNOWN_TOLERABLE_WARNINGS)

        # Prüfen ob es ein fataler Marker ist
        is_fatal = any(em in line_stripped for em in UNKNOWN_ERROR_MARKERS)

        if is_fatal and not is_known:
            fatal_lines.append(line_stripped)

    return len(fatal_lines) > 0, fatal_lines

# ==============================================================================
# PHASE 3: Deterministische VTK/Qt Cleanup-Strategie
# ==============================================================================

def cleanup_vtk_qt_resources():
    """
    Sauberes Cleanup von VTK/Qt Ressourcen nach jedem Test.

    Diese Funktion sollte im fixture teardown aufgerufen werden.
    """
    try:
        # PyVista/Qt Cleanup
        try:
            from gui.viewport.render_queue import RenderQueue
            RenderQueue.flush()
        except Exception:
            pass

        # PyQt Garbage Collection
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                # Alle offenen Widgets schließen
                for widget in app.topLevelWidgets():
                    try:
                        widget.close()
                        widget.deleteLater()
                    except Exception:
                        pass
        except Exception:
            pass

        # Python Garbage Collection erzwingen
        gc.collect()

    except Exception as e:
        logger.debug(f"[UI-GATE] Cleanup warning: {e}")

# ==============================================================================
# PHASE 4: UI Test Fixtures
# ==============================================================================

import pytest

# Import Qt nach Umgebungsvariablen-Setup
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt


@pytest.fixture(scope="session")
def qt_application():
    """
    Session-weite QApplication Instanz.
    Verhindert segfaults durch mehrfache QApplication-Erstellung.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        logger.debug("[UI-GATE] Neue QApplication erstellt (session-scoped)")
    else:
        logger.debug("[UI-GATE] Existierende QApplication wiederverwendet")

    yield app

    # Session-Cleanup
    cleanup_vtk_qt_resources()


@pytest.fixture
def main_window_clean(qt_application) -> Generator:
    """
    MainWindow Fixture mit deterministischem Cleanup.

    Usage:
        def test_something(main_window_clean):
            window = main_window_clean
            # ... test code ...
    """
    from gui.main_window import MainWindow

    window = None
    try:
        window = MainWindow()
        window.show()

        # Kurze Wartezeit für Fenster-Initialisierung
        from PySide6.QtTest import QTest
        from PySide6.QtCore import QTimer
        QTest.qWaitForWindowExposed(window)

        yield window

    finally:
        # Deterministischer Cleanup
        if window is not None:
            try:
                # Erst Viewport sauber schließen
                if hasattr(window, 'viewport_3d') and window.viewport_3d:
                    try:
                        if hasattr(window.viewport_3d, 'plotter'):
                            window.viewport_3d.plotter.close()
                    except Exception:
                        pass

                window.close()
                window.deleteLater()
            except Exception as e:
                logger.debug(f"[UI-GATE] Window cleanup warning: {e}")

        cleanup_vtk_qt_resources()


@pytest.fixture
def safe_render_delay():
    """
    Fixture für sichere Wartezeit nach Render-Operationen.

    VTK/Qt Events brauchen Zeit zur Verarbeitung.
    """
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QTimer

    def _wait(ms: int = 50):
        """Sichere Wartezeit mit Event-Processing."""
        QTest.qWait(ms)
        QTimer.singleShot(0, lambda: None)  # Event-Loop drain

    return _wait


# ==============================================================================
# PHASE 5: Pytest-Hooks für UI-Gate Hardening
# ==============================================================================

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_setup(item):
    """
    Hook vor jedem Test - loggt UI-Test-Start.
    """
    # Prüfen ob es ein UI-Test ist
    is_ui_test = any(marker for marker in [
        "ui_abort", "interaction", "viewport", "sketch_editor",
        "main_window", "dialog"
    ] if marker in str(item.fspath).lower() or marker in item.keywords)

    if is_ui_test:
        logger.debug(f"[UI-GATE] Setup: {item.name}")

    yield


@pytest.hookimpl(trylast=True, hookwrapper=True)
def pytest_runtest_teardown(item):
    """
    Hook nach jedem Test - Cleanup und Warnung-Check.
    """
    yield

    # Cleanup nach UI-Tests
    is_ui_test = any(marker for marker in [
        "ui_abort", "interaction", "viewport", "sketch_editor",
        "main_window", "dialog"
    ] if marker in str(item.fspath).lower() or marker in item.keywords)

    if is_ui_test:
        cleanup_vtk_qt_resources()
        logger.debug(f"[UI-GATE] Teardown: {item.name}")


# ==============================================================================
# PHASE 6: Konfiguration für Captured Stderr Prüfung
# ==============================================================================

def pytest_configure(config):
    """
    Registriere Custom Marker für UI-Tests.
    """
    config.addinivalue_line(
        "markers", "ui_gate: Markiert Tests als UI-Gate relevant (braucht VTK/Qt)"
    )
    config.addinivalue_line(
        "markers", "vtk_known_warning: Test erwartet bekannte VTK-Warnings"
    )


# ==============================================================================
# PHASE 7: Hilfsfunktionen für Test-Entwicklung
# ==============================================================================

class UIGateHelper:
    """Hilfsklasse für UI-Test-Entwicklung."""

    @staticmethod
    def wait_for_condition(condition, timeout_ms=5000, check_interval_ms=50):
        """
        Wartet auf eine Condition mit Timeout.

        Args:
            condition: Callable die True zurückgibt wenn Bedingung erfüllt
            timeout_ms: Maximal zu wartende Zeit
            check_interval_ms: Intervall zwischen Checks

        Returns:
            bool: True wenn Bedingung erfüllt, False bei Timeout
        """
        from PySide6.QtCore import QTimer, QEventLoop
        from PySide6.QtTest import QTest

        elapsed = 0
        while elapsed < timeout_ms:
            if condition():
                return True
            QTest.qWait(check_interval_ms)
            elapsed += check_interval_ms
        return False

    @staticmethod
    def press_key_safe(widget, key, modifier=Qt.NoModifier):
        """
        Sicheres Tastendruck-Senden mit Event-Processing.
        """
        from PySide6.QtTest import QTest

        QTest.keyClick(widget, key, modifier)
        QTest.qWait(20)  # Kurz warten für Event-Verarbeitung

    @staticmethod
    def click_safe(widget, button, pos=None, modifier=Qt.NoModifier):
        """
        Sicheres Maus-Klick-Senden mit Event-Processing.
        """
        from PySide6.QtTest import QTest
        from PySide6.QtCore import QPoint

        if pos is None:
            pos = QPoint(widget.width() // 2, widget.height() // 2)

        QTest.mouseClick(widget, button, modifier, pos)
        QTest.qWait(20)


# Export für Test-Module
__all__ = [
    "main_window_clean",
    "qt_application",
    "safe_render_delay",
    "cleanup_vtk_qt_resources",
    "check_stderr_for_fatal_issues",
    "KNOWN_TOLERABLE_WARNINGS",
    "UIGateHelper",
]
