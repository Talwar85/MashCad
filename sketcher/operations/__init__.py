"""
MashCad - Sketch Operations Module
==================================

Extrahierte Sketch-Operationen für bessere Testbarkeit.
Jede Operation ist eine eigenständige Klasse mit klarer Schnittstelle.

Verwendung:
    from sketcher.operations import TrimOperation

    op = TrimOperation(sketch)
    result = op.execute(target, click_point)

    if result.success:
        # Operation erfolgreich
    else:
        print(result.error)

Feature-Flags:
    Jede Operation kann über Feature-Flags aktiviert/deaktiviert werden.
    Die alten Implementierungen bleiben als Fallback erhalten.
"""

from .trim import TrimOperation, TrimResult
from .base import OperationResult, SketchOperation

__all__ = [
    'TrimOperation',
    'TrimResult',
    'OperationResult',
    'SketchOperation',
]
