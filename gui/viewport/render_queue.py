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

import time
from typing import Optional, Set, Callable, List
from collections import deque
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

    # FPS Tracking
    _frame_times: deque = None       # Timestamps der letzten Frames
    _fps: float = 0.0                # Aktueller FPS-Wert
    _fps_callbacks: List[Callable] = None  # Listener für FPS-Updates
    _fps_update_timer: Optional[QTimer] = None
    FPS_WINDOW_SIZE = 60             # Frames für gleitenden Durchschnitt

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
        RenderQueue._frame_times = deque(maxlen=RenderQueue.FPS_WINDOW_SIZE)
        RenderQueue._fps_callbacks = []
        RenderQueue._initialized = True

        # FPS-Update Timer (alle 500ms den FPS-Wert berechnen und broadcasten)
        if HAS_QT:
            RenderQueue._fps_update_timer = QTimer()
            RenderQueue._fps_update_timer.setInterval(500)
            RenderQueue._fps_update_timer.timeout.connect(RenderQueue._broadcast_fps)
            RenderQueue._fps_update_timer.start()

        logger.debug("RenderQueue initialisiert (mit FPS-Tracking)")

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

    # ── FPS Counter ──────────────────────────────────────────

    @classmethod
    def record_frame(cls):
        """Zeichnet einen gerenderten Frame auf (von VTK-Observer aufgerufen)."""
        if cls._frame_times is not None:
            cls._frame_times.append(time.perf_counter())

    @classmethod
    def attach_fps_observer(cls, plotter):
        """
        Hängt einen VTK EndRenderEvent-Observer an den Plotter,
        damit ALLE Renders gezählt werden (nicht nur Queue-Renders).
        """
        try:
            rw = None
            if hasattr(plotter, 'render_window') and plotter.render_window:
                rw = plotter.render_window
            elif hasattr(plotter, 'ren_win') and plotter.ren_win:
                rw = plotter.ren_win

            if rw is not None:
                rw.AddObserver('EndEvent', lambda obj, evt: cls.record_frame())
                logger.debug("FPS-Observer an RenderWindow angehängt")
            else:
                logger.debug("FPS-Observer: kein RenderWindow gefunden")
        except Exception as e:
            logger.debug(f"FPS-Observer konnte nicht angehängt werden: {e}")

    @classmethod
    def get_fps(cls) -> float:
        """Gibt aktuellen FPS-Wert zurück (gleitender Durchschnitt)."""
        if cls._frame_times is None or len(cls._frame_times) < 2:
            return 0.0
        now = time.perf_counter()
        # Nur Frames der letzten 2 Sekunden berücksichtigen
        cutoff = now - 2.0
        while cls._frame_times and cls._frame_times[0] < cutoff:
            cls._frame_times.popleft()
        if len(cls._frame_times) < 2:
            return 0.0
        elapsed = cls._frame_times[-1] - cls._frame_times[0]
        if elapsed <= 0:
            return 0.0
        return (len(cls._frame_times) - 1) / elapsed

    @classmethod
    def register_fps_callback(cls, callback: Callable[[float], None]):
        """Registriert Callback der bei FPS-Update aufgerufen wird."""
        instance = cls()
        if cls._fps_callbacks is None:
            cls._fps_callbacks = []
        cls._fps_callbacks.append(callback)

    @classmethod
    def unregister_fps_callback(cls, callback: Callable[[float], None]):
        """Entfernt FPS-Callback."""
        if cls._fps_callbacks:
            try:
                cls._fps_callbacks.remove(callback)
            except ValueError:
                pass

    @classmethod
    def _broadcast_fps(cls):
        """Berechnet FPS und benachrichtigt alle Listener."""
        cls._fps = cls.get_fps()
        if cls._fps_callbacks:
            for cb in cls._fps_callbacks:
                try:
                    cb(cls._fps)
                except Exception:
                    pass


# Convenience-Funktion für einfachen Import
def request_render(plotter, immediate: bool = False):
    """
    Shortcut für RenderQueue.request_render()

    Usage:
        from gui.viewport.render_queue import request_render
        request_render(self.plotter)
    """
    RenderQueue.request_render(plotter, immediate)
