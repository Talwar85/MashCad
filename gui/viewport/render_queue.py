"""
MashCad - Render Queue
======================

Phase 4.1: Performance-Optimierung durch Render-Batching

Problem: 44x plotter.render() Aufrufe verteilt über die Codebase
- Jeder Aufruf ist ~10-50ms (abhängig von Mesh-Komplexität)
- Bei Mouse-Move können 60+ Events/Sekunde auftreten
- Ergebnis: Frame-Drops, Lag, CPU-Spikes

Lösung: Zentralisierte Render-Queue mit Debouncing
- Sammelt alle Render-Requests
- Führt max. 1 Render pro 16ms aus (60 FPS cap)
- Immediate-Mode für kritische Updates (z.B. nach Boolean)

Verwendung:
    # VORHER
    self.plotter.render()

    # NACHHER
    from gui.viewport.render_queue import RenderQueue
    RenderQueue.request_render(self.plotter)

    # Für sofortiges Render (z.B. nach Boolean-Operation)
    RenderQueue.request_render(self.plotter, immediate=True)

Author: Claude (Phase 4 Performance)
Date: 2026-01-23
"""

from typing import Optional, Set
from loguru import logger

try:
    from PySide6.QtCore import QTimer, QObject
    HAS_QT = True
except ImportError:
    HAS_QT = False


class RenderQueue(QObject):
    """
    Singleton Render-Queue für debounced Viewport-Rendering.

    Verhindert Performance-Probleme durch zu häufiges Rendering.
    Max. 60 FPS (16ms Intervall) für normale Updates.
    """

    _instance: Optional['RenderQueue'] = None
    _plotters: Set = None  # Pending plotters to render
    _timer: Optional[QTimer] = None
    _initialized: bool = False

    # Performance-Tuning
    DEBOUNCE_MS = 16       # ~60 FPS max
    IMMEDIATE_MS = 0       # Sofort (nächster Event-Loop)

    # Statistiken (für Debugging)
    _stats_requested = 0
    _stats_rendered = 0
    _stats_skipped = 0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if RenderQueue._initialized:
            return

        if HAS_QT:
            super().__init__()

        RenderQueue._plotters = set()
        RenderQueue._timer = None
        RenderQueue._initialized = True

        logger.debug("RenderQueue initialisiert")

    @classmethod
    def request_render(cls, plotter, immediate: bool = False):
        """
        Fordert Render für einen Plotter an.

        Args:
            plotter: PyVista QtInteractor
            immediate: True für sofortiges Render (nach Boolean, etc.)
        """
        if not HAS_QT:
            # Fallback: Direktes Render ohne Qt
            plotter.render()
            return

        # Singleton initialisieren falls nötig
        instance = cls()

        cls._stats_requested += 1

        # Plotter zur Queue hinzufügen
        cls._plotters.add(plotter)

        # Timer starten falls nicht bereits aktiv
        if cls._timer is None:
            cls._timer = QTimer()
            cls._timer.setSingleShot(True)
            cls._timer.timeout.connect(cls._execute_render)

        if not cls._timer.isActive():
            delay = cls.IMMEDIATE_MS if immediate else cls.DEBOUNCE_MS
            cls._timer.start(delay)
        elif immediate and cls._timer.remainingTime() > cls.IMMEDIATE_MS:
            # Immediate überschreibt längeren Timer
            cls._timer.stop()
            cls._timer.start(cls.IMMEDIATE_MS)
        else:
            # Timer läuft bereits, Request wird gebatched
            cls._stats_skipped += 1

    @classmethod
    def _execute_render(cls):
        """Führt gebatchtes Render für alle pending Plotters aus."""
        if not cls._plotters:
            return

        # Kopie erstellen und Queue leeren
        plotters_to_render = list(cls._plotters)
        cls._plotters.clear()

        # Alle Plotters rendern
        for plotter in plotters_to_render:
            try:
                plotter.render()
                cls._stats_rendered += 1
            except Exception as e:
                logger.warning(f"Render fehlgeschlagen: {e}")

        # Debug-Logging (nur bei signifikanter Aktivität)
        if cls._stats_requested > 0 and cls._stats_requested % 100 == 0:
            skip_rate = (cls._stats_skipped / cls._stats_requested) * 100 if cls._stats_requested > 0 else 0
            logger.debug(
                f"RenderQueue Stats: {cls._stats_requested} requested, "
                f"{cls._stats_rendered} rendered, {cls._stats_skipped} skipped "
                f"({skip_rate:.1f}% savings)"
            )

    @classmethod
    def force_render(cls, plotter):
        """
        Erzwingt sofortiges Render (synchron, ohne Queue).

        Nur für kritische Situationen verwenden:
        - Screenshot
        - Export
        - Shutdown
        """
        plotter.render()
        cls._stats_rendered += 1

    @classmethod
    def flush(cls):
        """Führt alle pending Renders sofort aus."""
        if cls._timer and cls._timer.isActive():
            cls._timer.stop()
        cls._execute_render()

    @classmethod
    def get_stats(cls) -> dict:
        """Gibt Performance-Statistiken zurück."""
        return {
            "requested": cls._stats_requested,
            "rendered": cls._stats_rendered,
            "skipped": cls._stats_skipped,
            "savings_percent": (cls._stats_skipped / cls._stats_requested * 100)
                               if cls._stats_requested > 0 else 0
        }

    @classmethod
    def reset_stats(cls):
        """Setzt Statistiken zurück."""
        cls._stats_requested = 0
        cls._stats_rendered = 0
        cls._stats_skipped = 0


# Convenience-Funktion für einfachen Import
def request_render(plotter, immediate: bool = False):
    """
    Shortcut für RenderQueue.request_render()

    Usage:
        from gui.viewport.render_queue import request_render
        request_render(self.plotter)
    """
    RenderQueue.request_render(plotter, immediate)
