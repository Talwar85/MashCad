"""
Helpers for queued main-thread execution of OCP-dependent jobs.

These workers keep the public worker API (`start`, `cancel`, `isRunning`) but
do not move CAD operations to background threads.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QTimer

from modeling.ocp_thread_guard import ensure_ocp_main_thread


class MainThreadWorkerMixin:
    """Mixin that defers work to the next main-thread event loop turn."""

    def _start_queued_task(self, operation: str, callback) -> None:
        ensure_ocp_main_thread(f"schedule {operation}")
        if getattr(self, "_running", False):
            return

        self._running = True
        app = QCoreApplication.instance()
        if app is None:
            callback()
            return

        QTimer.singleShot(0, callback)

    def isRunning(self) -> bool:
        return bool(getattr(self, "_running", False))

    def terminate(self) -> None:
        cancel = getattr(self, "cancel", None)
        if callable(cancel):
            cancel()

    def wait(self, _timeout: int | None = None) -> bool:
        return not self.isRunning()
