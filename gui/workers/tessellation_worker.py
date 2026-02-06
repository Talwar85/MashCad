"""
MashCAD - Async Tessellation Worker
====================================

PERFORMANCE (Phase 9): Background thread für Mesh-Generierung.

Problem: CADTessellator.tessellate_with_face_ids() blockiert UI bei komplexen Modellen.
Lösung: QThread-basierter Worker - Tessellation läuft im Hintergrund,
        Viewport wird aktualisiert sobald das Mesh fertig ist.

Features:
- Non-blocking Tessellation (UI bleibt responsiv)
- Cancel-Support bei Body-Wechsel
- Automatische Mesh-Übernahme via Signal
- Supersedes vorherige Anfragen für denselben Body

Autor: Claude (Performance Optimization Phase 9)
Datum: 2026-02-06
"""

from typing import Any, Optional, Dict
from loguru import logger

from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker


class TessellationWorker(QThread):
    """
    Background Worker für Mesh-Generierung aus CAD-Solids.

    Signals:
        mesh_ready: (body_id, mesh, edges, face_info) - Tessellation fertig
        error: (body_id, error_message) - Fehler bei Tessellation

    Usage:
        worker = TessellationWorker(body_id, solid)
        worker.mesh_ready.connect(on_mesh_ready)
        worker.error.connect(on_tessellation_error)
        worker.start()
    """

    mesh_ready = Signal(str, object, object, object)  # body_id, mesh, edges, face_info
    error = Signal(str, str)  # body_id, error_message

    def __init__(self, body_id: str, solid: Any, parent=None):
        """
        Args:
            body_id: Eindeutige Body-ID für Zuordnung
            solid: Build123d Solid (OCP Shapes sind immutable → thread-safe)
        """
        super().__init__(parent)
        self.body_id = body_id
        self.solid = solid
        self._cancelled = False

    def cancel(self):
        """Bricht die Tessellation ab (z.B. bei erneutem Rebuild)."""
        self._cancelled = True

    def run(self):
        """Tessellation im Background-Thread."""
        try:
            if self._cancelled:
                return

            from modeling.cad_tessellator import CADTessellator

            mesh, edges, face_info = CADTessellator.tessellate_with_face_ids(self.solid)

            if self._cancelled:
                return

            self.mesh_ready.emit(self.body_id, mesh, edges, face_info)

        except Exception as e:
            if not self._cancelled:
                logger.warning(f"Async Tessellation fehlgeschlagen für {self.body_id}: {e}")
                self.error.emit(self.body_id, str(e))


class TessellationManager:
    """
    Verwaltet async Tessellation-Worker für mehrere Bodies.

    - Pro Body maximal ein Worker aktiv
    - Neuer Request → alter Worker wird gecancelled
    - Thread-safe via QMutex
    """

    def __init__(self):
        self._workers: Dict[str, TessellationWorker] = {}
        self._mutex = QMutex()

    def request_tessellation(
        self,
        body_id: str,
        solid: Any,
        on_ready: callable,
        on_error: Optional[callable] = None
    ) -> TessellationWorker:
        """
        Startet async Tessellation für einen Body.

        Wenn bereits ein Worker für diesen Body läuft, wird er gecancelled.

        Args:
            body_id: Body-ID
            solid: Build123d Solid
            on_ready: Callback(body_id, mesh, edges, face_info)
            on_error: Optional Callback(body_id, error_message)

        Returns:
            Der gestartete Worker
        """
        with QMutexLocker(self._mutex):
            # Cancel laufenden Worker für diesen Body
            if body_id in self._workers:
                old_worker = self._workers[body_id]
                if old_worker.isRunning():
                    old_worker.cancel()
                    logger.debug(f"Tessellation gecancelled für {body_id} (neuer Request)")

            # Neuen Worker starten
            worker = TessellationWorker(body_id, solid)
            worker.mesh_ready.connect(on_ready)
            if on_error:
                worker.error.connect(on_error)

            # Cleanup nach Fertigstellung
            worker.finished.connect(lambda: self._cleanup_worker(body_id))

            self._workers[body_id] = worker
            worker.start()

            return worker

    def _cleanup_worker(self, body_id: str):
        """Entfernt Worker nach Fertigstellung."""
        with QMutexLocker(self._mutex):
            if body_id in self._workers:
                worker = self._workers[body_id]
                if not worker.isRunning():
                    del self._workers[body_id]

    def cancel_all(self):
        """Cancelt alle laufenden Workers."""
        with QMutexLocker(self._mutex):
            for body_id, worker in self._workers.items():
                if worker.isRunning():
                    worker.cancel()
            self._workers.clear()

    def is_tessellating(self, body_id: str) -> bool:
        """Prüft ob Tessellation für einen Body läuft."""
        with QMutexLocker(self._mutex):
            if body_id in self._workers:
                return self._workers[body_id].isRunning()
            return False

    @property
    def active_count(self) -> int:
        """Anzahl aktiver Tessellation-Worker."""
        with QMutexLocker(self._mutex):
            return sum(1 for w in self._workers.values() if w.isRunning())
