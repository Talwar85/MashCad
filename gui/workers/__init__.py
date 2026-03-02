"""
MashCAD - Background Workers
============================

Queued main-thread worker für OCP-abhängige Langläufer.

PERFORMANCE (Phase 6): UI bleibt responsiv soweit Progress-Callbacks yielden.
PERFORMANCE (Phase 9): Deferred tessellation für flüssigere UI ohne OCP-Threads.
"""

from gui.workers.export_worker import STLExportWorker, STEPExportWorker
from gui.workers.tessellation_worker import TessellationWorker, TessellationManager

__all__ = ['STLExportWorker', 'STEPExportWorker', 'TessellationWorker', 'TessellationManager']
