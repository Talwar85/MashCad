"""
MeshConverter Base Classes
===========================

Async-enabled base classes for mesh-to-BREP conversion with progress reporting.

Author: Claude (MeshConverter Architecture)
Date: 2026-02-10
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Any
from abc import ABC, abstractmethod
from loguru import logger


class ConversionPhase(Enum):
    """Phasen der Mesh-Konvertierung"""
    LOADING = "Laden"
    REPAIRING = "Reparieren"
    SEGMENTING = "Segmentierung"
    DETECTING = "Primitive Detection"
    BUILDING = "BREP Construction"
    SEWING = "Sewing"
    OPTIMIZING = "Optimierung"
    VALIDATING = "Validierung"
    COMPLETE = "Fertig"


@dataclass
class ProgressUpdate:
    """
    Progress Update für asynchrone Konvertierung.

    Args:
        phase: Aktuelle Phase
        progress: Fortschritt 0.0 - 1.0
        message: Status-Nachricht für Anwender
        detail: Optionales Detail (z.B. "15/20 regions")
    """
    phase: ConversionPhase
    progress: float  # 0.0 - 1.0
    message: str
    detail: Optional[str] = None

    def __post_init__(self):
        """Validiert Progress-Wert."""
        if not 0.0 <= self.progress <= 1.0:
            raise ValueError(f"Progress must be 0.0-1.0, got {self.progress}")


ProgressCallback = Callable[[ProgressUpdate], None]


@dataclass
class ConversionResult:
    """
    Ergebnis der Mesh-Konvertierung.

    Args:
        success: Ob die Konvertierung erfolgreich war
        solid: Der resultierende build123d Solid (oder None)
        status: Status-Enum für detailliertes Ergebnis
        message: Menschlich lesbare Nachricht
        face_count: Anzahl der Faces im resultierenden Solid
        warnings: Liste von Warnungen
        error: Exception bei Fehlschlag
    """
    success: bool
    solid: Optional[Any] = None  # build123d Solid
    status: 'ConversionStatus' = None
    message: str = ""
    face_count: int = 0
    warnings: list = field(default_factory=list)
    error: Optional[Exception] = None


class ConversionStatus(Enum):
    """Detaillierter Status der Konvertierung"""
    SUCCESS = "Erfolg"
    PARTIAL = "Teilweise erfolgreich"
    SHELL_ONLY = "Nur Shell (kein Solid)"
    FAILED = "Fehlgeschlagen"


class AsyncMeshConverter(ABC):
    """
    Base Klasse für asynchrone Mesh-to-BREP Converter.

    Alle Converter müssen von dieser Klasse erben und die
    convert_async() Methode implementieren.

    Usage:
        def on_progress(update: ProgressUpdate):
            progress_bar.setValue(int(update.progress * 100))
            status_label.setText(update.message)

        result = converter.convert_async(mesh, on_progress)
    """

    def __init__(self, name: str = "MeshConverter"):
        self.name = name

    @abstractmethod
    def convert_async(
        self,
        mesh: Any,
        progress_callback: Optional[ProgressCallback] = None
    ) -> ConversionResult:
        """
        Asynchrone Konvertierung mit Progress Updates.

        Args:
            mesh: PyVista PolyData oder ähnliches Mesh-Objekt
            progress_callback: Optionale Callback-Funktion für Progress Updates

        Returns:
            ConversionResult mit dem erstellten BREP Solid
        """
        pass

    def _emit_progress(
        self,
        phase: ConversionPhase,
        progress: float,
        message: str,
        detail: Optional[str] = None,
        callback: Optional[ProgressCallback] = None
    ):
        """Emittet ein Progress-Update an den Callback."""
        if callback is not None:
            update = ProgressUpdate(
                phase=phase,
                progress=progress,
                message=message,
                detail=detail
            )
            try:
                callback(update)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

    def _validate_mesh(self, mesh: Any) -> bool:
        """
        Validiert das Input-Mesh.

        Returns:
            True wenn Mesh gültig, False sonst
        """
        if mesh is None:
            return False

        # Prüfe ob Mesh Punkte hat
        try:
            n_points = mesh.n_points if hasattr(mesh, 'n_points') else 0
            n_cells = mesh.n_cells if hasattr(mesh, 'n_cells') else 0
            return n_points > 0 and n_cells > 0
        except Exception:
            return False


def _test_progress():
    """Test der Progress-Klassen."""
    from PySide6.QtCore import QObject, Signal

    class TestEmitter(QObject):
        progress_signal = Signal(object)

        def __init__(self):
            super().__init__()

        def on_progress(self, update: ProgressUpdate):
            self.progress_signal.emit(update)
            print(f"[{update.phase.value}] {update.progress*100:.0f}% - {update.message}")
            if update.detail:
                print(f"  Detail: {update.detail}")

    # Test
    emitter = TestEmitter()

    # Simuliere Progress
    phases = [
        (ConversionPhase.LOADING, 0.1, "Laden...", None),
        (ConversionPhase.REPAIRING, 0.2, "Repariere Mesh...", None),
        (ConversionPhase.SEGMENTING, 0.5, "Segmentiere...", "15/20 regions"),
        (ConversionPhase.DETECTING, 0.7, "Erkenne Primitive...", None),
        (ConversionPhase.BUILDING, 0.9, "Erstelle BREP...", None),
        (ConversionPhase.COMPLETE, 1.0, "Fertig!", None),
    ]

    for phase, progress, message, detail in phases:
        emitter.on_progress(ProgressUpdate(phase, progress, message, detail))


if __name__ == "__main__":
    _test_progress()
