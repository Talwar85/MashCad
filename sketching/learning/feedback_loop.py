"""
Feedback Loop - Sammelt Feedback und lernt daraus

Adaptive Strategien:
- Erfolgreiche Parameter werden bevorzugt
- Fehlerhafte Parameter werden vermieden
- Langsame Operationen werden optimiert

Author: Claude (Sketch Agent)
Date: 2026-02-11
"""

import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict
from loguru import logger


@dataclass
class OperationRecord:
    """Einzelner Eintrag im Feedback-Log."""
    operation: str
    parameters: Dict[str, Any]
    success: bool
    duration_ms: float
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dict für Serialisierung."""
        return {
            "operation": self.operation,
            "parameters": self.parameters,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OperationRecord':
        """Erstellt aus Dict."""
        return cls(
            operation=data["operation"],
            parameters=data["parameters"],
            success=data["success"],
            duration_ms=data["duration_ms"],
            error=data.get("error"),
            timestamp=data["timestamp"]
        )


class FeedbackLoop:
    """
    Sammelt Feedback und lernt daraus.

    Adaptive Strategien:
    - Erfolgreiche Parameter werden bevorzugt
    - Fehlerhafte Parameter werden vermieden
    - Langsame Operationen werden optimiert
    """

    def __init__(self, storage_path: str = "sketching/learning/feedback_db.json"):
        """
        Args:
            storage_path: Pfad zur JSON-Datei für Persistenz
        """
        self.storage_path = storage_path
        self.records: List[OperationRecord] = []
        self.stats: Dict[str, Dict] = defaultdict(lambda: {
            "total": 0,
            "success": 0,
            "failures": 0,
            "avg_duration_ms": 0,
            "total_duration_ms": 0
        })

        # Lade gespeicherte Daten
        self._load()

    def record(
        self,
        operation: str,
        params: Dict[str, Any],
        success: bool,
        duration_ms: float,
        error: Optional[str] = None
    ):
        """
        Zeichnet Operation auf.

        Args:
            operation: Operations-Typ (z.B. "extrude", "fillet")
            params: Verwendete Parameter
            success: Ob Operation erfolgreich war
            duration_ms: Dauer in ms
            error: Fehlermeldung (falls fehlgeschlagen)
        """
        record = OperationRecord(
            operation=operation,
            parameters=params,
            success=success,
            duration_ms=duration_ms,
            error=error
        )
        self.records.append(record)
        self._update_stats(record)

        # Speichere periodisch
        if len(self.records) % 10 == 0:
            self.save()

    def get_success_rate(self, operation: str) -> float:
        """
        Gibt Erfolgsrate für Operation zurück.

        Args:
            operation: Operations-Typ

        Returns:
            Erfolgsrate (0-1)
        """
        if operation not in self.stats:
            return 0.5

        stats = self.stats[operation]
        if stats["total"] == 0:
            return 0.5
        return stats["success"] / stats["total"]

    def suggest_parameters(
        self,
        operation: str,
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Schlägt erfolgreiche Parameter vor.

        Adaptive:
        - Wenn operation oft fehlschlägt → konservativere Parameter
        - Wenn operation oft succeedet → optimierte Parameter

        Args:
            operation: Operations-Typ
            context: Zusätzlicher Kontext (z.B. sketch_area)

        Returns:
            Vorgeschlagene Parameter
        """
        # Standard-Parameter
        default_params = self._get_default_params(operation, context)

        # Wenn keine Statistiken vorhanden, gib Default zurück
        if operation not in self.stats:
            return default_params

        stats = self.stats[operation]
        success_rate = stats["success"] / stats["total"] if stats["total"] > 0 else 0.5

        # Adaptive Anpassung
        if success_rate < 0.5:
            # Niedrige Erfolgsrate → konservativer
            return self._make_conservative(operation, default_params)
        elif success_rate > 0.8:
            # Hohe Erfolgsrate → optimiert
            return self._make_optimized(operation, default_params)

        return default_params

    def analyze_errors(self) -> Dict[str, int]:
        """
        Analysiert häufige Fehler.

        Returns:
            Dict mit Fehler-Typ → Anzahl
        """
        error_counts = defaultdict(int)
        for record in self.records:
            if record.error:
                error_counts[record.error] += 1
        return dict(error_counts)

    def get_slow_operations(self, threshold_ms: float = 100) -> List[OperationRecord]:
        """
        Gibt langsame Operationen zurück.

        Args:
            threshold_ms: Schwellenwert in ms

        Returns:
            Liste der langsamen Operationen
        """
        return [
            r for r in self.records
            if r.duration_ms > threshold_ms
        ]

    def _update_stats(self, record: OperationRecord):
        """Aktualisiert Statistiken nach neuem Record."""
        stats = self.stats[record.operation]

        stats["total"] += 1
        stats["total_duration_ms"] += record.duration_ms

        if record.success:
            stats["success"] += 1
        else:
            stats["failures"] += 1

        # Durchschnitt neu berechnen
        stats["avg_duration_ms"] = stats["total_duration_ms"] / stats["total"]

    def _get_default_params(
        self,
        operation: str,
        context: Optional[Dict]
    ) -> Dict[str, Any]:
        """Standard-Parameter für Operation."""
        defaults = {
            "extrude": {"distance": 20, "operation": "New Body"},
            "fillet": {"radius": 2, "edges": None},
            "chamfer": {"distance": 1, "edges": None},
            "revolve": {"angle": 360},
            "shell": {"thickness": 2, "faces": None}
        }
        return defaults.get(operation, {})

    def _make_conservative(
        self,
        operation: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Macht Parameter konservativer (weniger aggressiv)."""
        result = dict(params)

        if operation == "extrude":
            # Geringere Distanz
            result["distance"] = params.get("distance", 20) * 0.5
        elif operation == "fillet":
            # Kleinerer Radius
            result["radius"] = params.get("radius", 2) * 0.5
        elif operation == "shell":
            # Dicke Wandstärke
            result["thickness"] = params.get("thickness", 2) * 1.5

        return result

    def _make_optimized(
        self,
        operation: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Optimiert Parameter für bessere Performance."""
        result = dict(params)

        if operation == "extrude":
            # Optimale Distanz beibehalten
            pass
        elif operation == "fillet":
            # Grösserer Radius für sichtbarere Ergebnisse
            result["radius"] = params.get("radius", 2) * 1.5

        return result

    def save(self):
        """Speichert Feedback-DB in JSON-Datei."""
        try:
            import os
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)

            data = {
                "records": [r.to_dict() for r in self.records],
                "stats": dict(self.stats)
            }

            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)

            logger.debug(f"[FeedbackLoop] Gespeichert: {len(self.records)} Records")

        except Exception as e:
            logger.error(f"[FeedbackLoop] Speichern fehlgeschlagen: {e}")

    def _load(self):
        """Lädt Feedback-DB aus JSON-Datei."""
        try:
            import os
            if not os.path.exists(self.storage_path):
                return

            with open(self.storage_path, 'r') as f:
                data = json.load(f)

            self.records = [
                OperationRecord.from_dict(r) for r in data.get("records", [])
            ]
            self.stats = defaultdict(lambda: {
                "total": 0,
                "success": 0,
                "failures": 0,
                "avg_duration_ms": 0,
                "total_duration_ms": 0
            })
            self.stats.update(data.get("stats", {}))

            logger.debug(f"[FeedbackLoop] Geladen: {len(self.records)} Records")

        except Exception as e:
            logger.warning(f"[FeedbackLoop] Laden fehlgeschlagen: {e}")

    def get_summary(self) -> Dict[str, Any]:
        """Zusammenfassung der Feedback-Daten."""
        return {
            "total_records": len(self.records),
            "operations": list(self.stats.keys()),
            "error_analysis": self.analyze_errors(),
            "slow_operations": len(self.get_slow_operations())
        }


# Factory für kompatible Creation
def create_feedback_loop(
    storage_path: str = "sketching/learning/feedback_db.json"
) -> FeedbackLoop:
    """
    Factory-Funktion zum Erstellen eines FeedbackLoop.

    Args:
        storage_path: Pfad zur JSON-Datei

    Returns:
        FeedbackLoop Instanz
    """
    return FeedbackLoop(storage_path=storage_path)
