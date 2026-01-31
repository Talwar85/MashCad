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
from .extend import ExtendOperation, ExtendResult
from .fillet2d import Fillet2DOperation, FilletResult, CornerData, CornerResult
from .chamfer2d import Chamfer2DOperation, ChamferResult
from .base import OperationResult, SketchOperation

__all__ = [
    # Core
    'OperationResult',
    'SketchOperation',
    # Trim
    'TrimOperation',
    'TrimResult',
    # Extend
    'ExtendOperation',
    'ExtendResult',
    # Fillet 2D
    'Fillet2DOperation',
    'FilletResult',
    'CornerData',
    'CornerResult',
    # Chamfer 2D
    'Chamfer2DOperation',
    'ChamferResult',
]
