"""
MashCAD - Async Tessellation Worker
===================================

Background thread worker and priority manager for non-blocking tessellation.
"""

from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from loguru import logger
from PySide6.QtCore import QMutex, QMutexLocker, QThread, Signal


class TessellationWorker(QThread):
    """Background worker that tessellates one solid."""

    mesh_ready = Signal(str, object, object, object)  # body_id, mesh, edges, face_info
    error = Signal(str, str)  # body_id, error_message

    def __init__(self, body_id: str, solid: Any, parent=None):
        super().__init__(parent)
        self.body_id = body_id
        self.solid = solid
        self._cancelled = False

    def cancel(self):
        """Cancel this tessellation request."""
        self._cancelled = True

    def run(self):
        """Execute tessellation in the worker thread."""
        try:
            if self._cancelled:
                return

            from modeling.cad_tessellator import CADTessellator

            mesh, edges, face_info = CADTessellator.tessellate_with_face_ids(self.solid)

            if self._cancelled:
                return

            self.mesh_ready.emit(self.body_id, mesh, edges, face_info)

        except Exception as exc:
            if not self._cancelled:
                logger.warning(f"Async tessellation failed for {self.body_id}: {exc}")
                self.error.emit(self.body_id, str(exc))


class TessellationManager:
    """
    Manages tessellation workers with per-body supersede and priority scheduling.

    - At most one active worker per body.
    - New request for same body cancels old active/pending request.
    - Higher priority requests are started first.
    - max_concurrent controls global concurrency (default 1 for kernel safety).
    """

    def __init__(self, max_concurrent: int = 1):
        self._workers: Dict[str, TessellationWorker] = {}
        self._pending: List[Tuple[int, int, str]] = []  # (priority, sequence, body_id)
        self._active_body_ids: Set[str] = set()
        self._request_seq = 0
        self._max_concurrent = max(1, int(max_concurrent))
        self._mutex = QMutex()

    def request_tessellation(
        self,
        body_id: str,
        solid: Any,
        on_ready: Callable,
        on_error: Optional[Callable] = None,
        priority: int = 0,
    ) -> TessellationWorker:
        """Queue/start tessellation for a body."""
        with QMutexLocker(self._mutex):
            # Supersede old request for this body.
            if body_id in self._workers:
                old_worker = self._workers[body_id]
                old_worker.cancel()
                self._active_body_ids.discard(body_id)
                self._remove_pending_locked(body_id)
                logger.debug(f"Tessellation superseded for {body_id}")

            worker = TessellationWorker(body_id, solid)
            worker.mesh_ready.connect(on_ready)
            if on_error:
                worker.error.connect(on_error)
            worker.finished.connect(lambda bid=body_id: self._cleanup_worker(bid))

            self._workers[body_id] = worker
            self._request_seq += 1
            self._pending.append((int(priority), self._request_seq, body_id))
            self._schedule_locked()
            return worker

    def _remove_pending_locked(self, body_id: str):
        self._pending = [item for item in self._pending if item[2] != body_id]

    def _pop_next_pending_body_locked(self) -> Optional[str]:
        if not self._pending:
            return None

        best_idx = 0
        best_priority, best_seq, _ = self._pending[0]
        for idx in range(1, len(self._pending)):
            prio, seq, _bid = self._pending[idx]
            if prio > best_priority or (prio == best_priority and seq < best_seq):
                best_idx = idx
                best_priority, best_seq = prio, seq

        _prio, _seq, body_id = self._pending.pop(best_idx)
        return body_id

    def _schedule_locked(self):
        while len(self._active_body_ids) < self._max_concurrent:
            next_body_id = self._pop_next_pending_body_locked()
            if next_body_id is None:
                return

            worker = self._workers.get(next_body_id)
            if worker is None:
                continue

            if worker.isRunning():
                self._active_body_ids.add(next_body_id)
                continue

            self._active_body_ids.add(next_body_id)
            worker.start()
            logger.debug(
                f"Tessellation started for {next_body_id} "
                f"(active={len(self._active_body_ids)}, pending={len(self._pending)})"
            )

    def _cleanup_worker(self, body_id: str):
        """Called when a worker finishes."""
        with QMutexLocker(self._mutex):
            self._active_body_ids.discard(body_id)
            self._remove_pending_locked(body_id)

            worker = self._workers.get(body_id)
            if worker is not None and not worker.isRunning():
                del self._workers[body_id]

            self._schedule_locked()

    def cancel_all(self):
        """Cancel all active and pending requests."""
        with QMutexLocker(self._mutex):
            for worker in self._workers.values():
                worker.cancel()
            self._workers.clear()
            self._pending.clear()
            self._active_body_ids.clear()

    def is_tessellating(self, body_id: str) -> bool:
        """True when body is active or pending in scheduler."""
        with QMutexLocker(self._mutex):
            if body_id in self._workers:
                if self._workers[body_id].isRunning():
                    return True
                if body_id in self._active_body_ids:
                    return True
                if any(item[2] == body_id for item in self._pending):
                    return True
            return False

    @property
    def active_count(self) -> int:
        """Number of currently running workers."""
        with QMutexLocker(self._mutex):
            return sum(1 for worker in self._workers.values() if worker.isRunning())
