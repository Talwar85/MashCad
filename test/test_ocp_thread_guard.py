import queue
import threading

import pytest

from modeling.export_kernel import ExportKernel
from modeling.ocp_thread_guard import ensure_ocp_main_thread, is_ocp_main_thread


def _run_in_background(target):
    results = queue.Queue()

    def _runner():
        try:
            target()
        except Exception as exc:  # expected in negative tests
            results.put(exc)
        else:
            results.put(None)

    thread = threading.Thread(target=_runner, name="ocp-background-test", daemon=True)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    return results.get_nowait()


def test_is_ocp_main_thread_on_test_thread():
    assert is_ocp_main_thread() is True


def test_ensure_ocp_main_thread_raises_in_background_thread():
    exc = _run_in_background(lambda: ensure_ocp_main_thread("unit-test OCP op"))

    assert isinstance(exc, RuntimeError)
    assert "unit-test OCP op" in str(exc)
    assert "main thread" in str(exc)


def test_export_kernel_rejects_background_thread():
    exc = _run_in_background(lambda: ExportKernel.export_bodies([object()], "guard_test.stl"))

    assert isinstance(exc, RuntimeError)
    assert "export CAD bodies" in str(exc)


def test_cad_tessellator_rejects_background_thread():
    from modeling.cad_tessellator import CADTessellator

    exc = _run_in_background(lambda: CADTessellator.tessellate_for_export(object()))

    assert isinstance(exc, RuntimeError)
    assert "tessellate solid for export" in str(exc)
