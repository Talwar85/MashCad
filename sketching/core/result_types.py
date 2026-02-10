"""
Result Types für Sketch Agent

Dataclasses für alle Rückgabewerte der Agent-Operationen.

Author: Claude (Sketch Agent)
Date: 2026-02-10
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class PartResult:
    """Ergebnis einer Part-Generierung."""

    success: bool
    solid: Optional[Any]  # build123d.Solid
    operations: List[str]
    duration_ms: float
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.metadata:
            self.metadata = {}

    @property
    def volume(self) -> float:
        """Volumen des generierten Solids."""
        if self.solid is None:
            return 0.0
        try:
            return self.solid.volume
        except:
            return 0.0

    @property
    def face_count(self) -> int:
        """Anzahl der Faces im Solid."""
        if self.solid is None:
            return 0
        try:
            return len(list(self.solid.faces()))
        except:
            return 0


@dataclass
class AssemblyResult:
    """Ergebnis einer Assembly-Generierung."""

    success: bool
    parts: List[PartResult]
    constraints: List[Dict[str, Any]]
    duration_ms: float
    error: Optional[str] = None

    @property
    def part_count(self) -> int:
        """Anzahl der Parts."""
        return len(self.parts)

    @property
    def successful_parts(self) -> int:
        """Anzahl der erfolgreich generierten Parts."""
        return sum(1 for p in self.parts if p.success)


@dataclass
class BatchResult:
    """Ergebnis eines Batch-Tests."""

    results: List[PartResult]
    duration_ms: float
    started_at: datetime
    finished_at: datetime

    @property
    def total_count(self) -> int:
        """Gesamtanzahl der Parts."""
        return len(self.results)

    @property
    def success_count(self) -> int:
        """Anzahl der erfolgreichen Parts."""
        return sum(1 for r in self.results if r.success)

    @property
    def success_rate(self) -> float:
        """Erfolgsrate (0-1)."""
        if self.total_count == 0:
            return 0.0
        return self.success_count / self.total_count

    @property
    def avg_duration_ms(self) -> float:
        """Durchschnittliche Dauer pro Part."""
        if not self.results:
            return 0.0
        return sum(r.duration_ms for r in self.results) / len(self.results)


@dataclass
class MeshAnalysis:
    """Ergebnis einer Mesh-Analyse."""

    primitives: List[Dict[str, Any]]
    features: List[Dict[str, Any]]
    suggested_steps: List[Dict[str, Any]]
    mesh_info: Dict[str, Any]
    duration_ms: float

    @property
    def primitive_count(self) -> int:
        """Anzahl der erkannten Primitives."""
        return len(self.primitives)

    @property
    def feature_count(self) -> int:
        """Anzahl der erkannten Features."""
        return len(self.features)

    @property
    def step_count(self) -> int:
        """Anzahl der vorgeschlagenen Schritte."""
        return len(self.suggested_steps)


@dataclass
class ReconstructionResult:
    """Ergebnis einer Mesh-to-CAD Rekonstruktion."""

    success: bool
    solid: Optional[Any]  # build123d.Solid
    analysis: MeshAnalysis
    executed_steps: List[Dict[str, Any]]
    duration_ms: float
    error: Optional[str] = None

    @property
    def completed_steps(self) -> int:
        """Anzahl der ausgeführten Schritte."""
        return len(self.executed_steps)


@dataclass
class StressTestResult:
    """Ergebnis eines Stresstests."""

    batch: BatchResult
    success_rate: float
    avg_duration_ms: float
    error_analysis: Dict[str, int]
    memory_mb: float


@dataclass
class PatternInfo:
    """Info über ein erkanntes Design-Pattern."""

    name: str
    confidence: float  # 0-1
    parameters: Dict[str, Any]
    matched_features: List[str]


@dataclass
class PrimitiveInfo:
    """Info über ein erkanntes Primitive."""

    primitive_type: str  # "plane", "cylinder", "sphere", "cone"
    center: tuple
    parameters: Dict[str, Any]
    confidence: float


@dataclass
class FeatureInfo:
    """Info über ein erkanntes CAD-Feature."""

    feature_type: str  # "fillet", "chamfer", "hole", "pocket"
    parameters: Dict[str, Any]
    location: tuple
    confidence: float
