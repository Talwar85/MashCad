"""
OpenCASCADE main-thread invariant helpers.

OCP/OpenCASCADE is not thread-safe. Every kernel entry point must enforce
main-thread execution so background worker regressions fail loudly.
"""

from __future__ import annotations

import threading

try:
    from PySide6.QtCore import QCoreApplication, QThread
except ImportError:  # pragma: no cover - Qt-free unit tests
    QCoreApplication = None
    QThread = None


def is_ocp_main_thread() -> bool:
    """Return True when the current execution context is the UI/main thread."""
    if QCoreApplication is not None and QThread is not None:
        app = QCoreApplication.instance()
        if app is not None:
            return QThread.currentThread() == app.thread()

    return threading.current_thread() is threading.main_thread()


def ensure_ocp_main_thread(operation: str) -> None:
    """Raise when OCP/build123d work is attempted off the main thread."""
    if is_ocp_main_thread():
        return

    current = threading.current_thread().name or "unknown"
    raise RuntimeError(
        f"{operation} must run on the main thread because OpenCASCADE is not thread-safe "
        f"(current thread: {current})"
    )
