"""
MashCad - Base Classes for Sketch Operations
=============================================

Abstrakte Basisklassen für alle extrahierten Sketch-Operationen.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional, TYPE_CHECKING
from enum import Enum, auto

if TYPE_CHECKING:
    from sketcher import Sketch, Point2D


class ResultStatus(Enum):
    """Status einer Operation."""
    SUCCESS = auto()
    WARNING = auto()  # Erfolgreich, aber mit Einschränkungen
    NO_TARGET = auto()  # Kein Ziel gefunden
    NO_INTERSECTIONS = auto()  # Keine Schnittpunkte
    ERROR = auto()


@dataclass
class OperationResult:
    """
    Strukturiertes Ergebnis einer Sketch-Operation.

    Ermöglicht klare Unterscheidung zwischen Erfolg, Warnung und Fehler.
    """
    status: ResultStatus
    message: str = ""
    data: Any = None

    @property
    def success(self) -> bool:
        return self.status in (ResultStatus.SUCCESS, ResultStatus.WARNING)

    @property
    def is_error(self) -> bool:
        return self.status == ResultStatus.ERROR

    @classmethod
    def ok(cls, message: str = "", data: Any = None) -> 'OperationResult':
        return cls(ResultStatus.SUCCESS, message, data)

    @classmethod
    def warning(cls, message: str, data: Any = None) -> 'OperationResult':
        return cls(ResultStatus.WARNING, message, data)

    @classmethod
    def no_target(cls, message: str = "Kein Ziel gefunden") -> 'OperationResult':
        return cls(ResultStatus.NO_TARGET, message)

    @classmethod
    def no_intersections(cls, message: str = "Keine Schnittpunkte") -> 'OperationResult':
        return cls(ResultStatus.NO_INTERSECTIONS, message)

    @classmethod
    def error(cls, message: str) -> 'OperationResult':
        return cls(ResultStatus.ERROR, message)


class SketchOperation(ABC):
    """
    Abstrakte Basisklasse für Sketch-Operationen.

    Jede Operation hat:
    - Referenz auf den Sketch
    - execute() Methode
    - Strukturiertes Ergebnis
    """

    def __init__(self, sketch: 'Sketch'):
        self.sketch = sketch
        self._last_result: Optional[OperationResult] = None

    @property
    def last_result(self) -> Optional[OperationResult]:
        """Letztes Ergebnis der Operation."""
        return self._last_result

    @abstractmethod
    def execute(self, *args, **kwargs) -> OperationResult:
        """
        Führt die Operation aus.

        Returns:
            OperationResult mit Status und Details
        """
        pass

    def can_execute(self, *args, **kwargs) -> bool:
        """
        Prüft ob die Operation ausgeführt werden kann.
        Override in Subklassen für Validierung.
        """
        return True
