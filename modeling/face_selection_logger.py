"""
MashCad - Face Selection Logger
================================

Strukturiertes Logging für Face-Selection mit Vergleichsmodus.
Ermöglicht Debugging und Validierung der neuen Hash-basierten Selektion.

Verwendung:
    from modeling.face_selection_logger import face_logger

    # Comparison Mode aktivieren
    face_logger.enable_comparison_mode("debug.jsonl")

    # Nach Tests
    print(face_logger.get_mismatch_stats())
    face_logger.export_mismatches("mismatches.json")
"""

from loguru import logger
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
import json
import time


@dataclass
class FaceSelectionEvent:
    """Einzelnes Face-Selection Ereignis für Logging/Vergleich."""

    timestamp: float
    action: str                    # "pick", "hover", "resolve", "hash"
    body_id: str

    # Alte Methode (Heuristik)
    old_face_id: Optional[int] = None
    old_method: str = "heuristic"  # "heuristic", "ocp_id", "none"
    old_score: float = 0.0

    # Neue Methode (Hash-basiert)
    new_face_hash: Optional[str] = None
    new_method: str = "hash"       # "hash", "fallback", "none"
    new_score: float = 0.0

    # Ergebnis
    match: bool = False            # Alte == Neue?
    resolved_face_id: Optional[int] = None

    # Zusätzliche Infos
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ts": self.timestamp,
            "action": self.action,
            "body": self.body_id,
            "old": {
                "id": self.old_face_id,
                "method": self.old_method,
                "score": round(self.old_score, 3)
            },
            "new": {
                "hash": self.new_face_hash,
                "method": self.new_method,
                "score": round(self.new_score, 3)
            },
            "match": self.match,
            "resolved": self.resolved_face_id,
            "extra": self.extra if self.extra else None,
        }


class FaceSelectionLogger:
    """
    Strukturiertes Logging für Face-Selection mit Vergleichsmodus.

    Features:
    - Vergleicht alte (Heuristik) vs. neue (Hash) Selektion
    - Loggt alle Pick/Hover Events
    - Berechnet Match-Statistiken
    - Exportiert Mismatches für Analyse
    """

    def __init__(self):
        self.events: List[FaceSelectionEvent] = []
        self.comparison_mode = False
        self.log_to_file = False
        self._log_file = None
        self._session_start: Optional[float] = None

    def enable_comparison_mode(self, log_file: str = None):
        """
        Aktiviert Vergleichsmodus: Beide Methoden werden ausgeführt und verglichen.

        Args:
            log_file: Optional Pfad für JSON-Log (z.B. "face_selection_debug.jsonl")
        """
        self.comparison_mode = True
        self._session_start = time.time()

        if log_file:
            self.log_to_file = True
            try:
                self._log_file = open(log_file, 'a', encoding='utf-8')
                logger.info(f"[FaceSelection] Comparison mode ENABLED (log={log_file})")
            except Exception as e:
                logger.error(f"[FaceSelection] Failed to open log file: {e}")
                self._log_file = None
        else:
            logger.info("[FaceSelection] Comparison mode ENABLED (no file)")

    def disable_comparison_mode(self):
        """Deaktiviert Vergleichsmodus."""
        self.comparison_mode = False

        if self._log_file:
            try:
                self._log_file.close()
            except Exception as e:
                logger.debug(f"[face_selection_logger.py] Fehler: {e}")
                pass
            self._log_file = None

        logger.info("[FaceSelection] Comparison mode DISABLED")

    def log_pick(self, body_id: str,
                 old_face_id: Optional[int], old_method: str, old_score: float,
                 new_hash: Optional[str], new_method: str, new_score: float,
                 resolved_id: Optional[int],
                 extra: Dict[str, Any] = None):
        """
        Loggt Pick-Ereignis mit Vergleich.

        Args:
            body_id: ID des Bodies
            old_face_id: Face-ID aus alter Methode
            old_method: Methode der alten Selektion
            old_score: Score der alten Selektion
            new_hash: Face-Hash aus neuer Methode
            new_method: Methode der neuen Selektion
            new_score: Score der neuen Selektion
            resolved_id: Final aufgelöste Face-ID
            extra: Zusätzliche Debug-Infos
        """
        match = (old_face_id == resolved_id) if old_face_id is not None else False

        event = FaceSelectionEvent(
            timestamp=time.time(),
            action="pick",
            body_id=body_id,
            old_face_id=old_face_id,
            old_method=old_method,
            old_score=old_score,
            new_face_hash=new_hash,
            new_method=new_method,
            new_score=new_score,
            match=match,
            resolved_face_id=resolved_id,
            extra=extra or {},
        )

        self.events.append(event)
        self._log_event(event)

    def log_hover(self, body_id: str, face_id: Optional[int],
                  face_hash: Optional[str] = None,
                  method: str = "unknown"):
        """Loggt Hover-Ereignis."""
        event = FaceSelectionEvent(
            timestamp=time.time(),
            action="hover",
            body_id=body_id,
            old_face_id=face_id,
            new_face_hash=face_hash,
            new_method=method,
            resolved_face_id=face_id,
            match=True,  # Hover hat immer nur eine Methode
        )

        self.events.append(event)
        # Hover nicht in Datei loggen (zu viele Events)

    def log_hash_computation(self, face_id: int, face_hash: str,
                             surface_type: str, area: float, center: tuple):
        """Loggt Hash-Berechnung für Debugging."""
        logger.trace(f"[FaceHash] face={face_id} hash={face_hash} "
                    f"type={surface_type} area={area:.4f} center={center}")

    def log_resolution(self, ref_hash: str, resolved_id: Optional[int],
                       method: str, score: float, candidates: int):
        """Loggt Referenz-Auflösung."""
        if resolved_id is not None:
            logger.debug(f"[FaceResolve] ✓ hash={ref_hash[:8] if ref_hash else '???'} → face={resolved_id} "
                        f"method={method} score={score:.2f} candidates={candidates}")
        else:
            logger.warning(f"[FaceResolve] ✗ FAILED hash={ref_hash[:8] if ref_hash else '???'} "
                          f"method={method} candidates={candidates}")

    def _log_event(self, event: FaceSelectionEvent):
        """Internes Logging eines Events."""
        hash_short = event.new_face_hash[:8] if event.new_face_hash else 'None'

        if event.match:
            logger.debug(f"[FaceSelection] ✓ MATCH body={event.body_id} "
                        f"face={event.resolved_face_id} hash={hash_short}")
        else:
            logger.warning(f"[FaceSelection] ✗ MISMATCH body={event.body_id} "
                          f"old={event.old_face_id}({event.old_method}) "
                          f"vs new={event.resolved_face_id}({event.new_method}) "
                          f"hash={hash_short}")

        # File Logging
        if self.log_to_file and self._log_file:
            try:
                self._log_file.write(json.dumps(event.to_dict()) + "\n")
                self._log_file.flush()
            except Exception as e:
                logger.error(f"[FaceSelection] Log write failed: {e}")

    def get_mismatch_stats(self) -> dict:
        """
        Gibt Statistiken über Mismatches zurück.

        Returns:
            Dict mit total, matches, mismatches, match_rate
        """
        total = len(self.events)
        if total == 0:
            return {
                "total": 0,
                "matches": 0,
                "mismatches": 0,
                "match_rate": 1.0,
                "session_duration_sec": 0,
            }

        matches = sum(1 for e in self.events if e.match)
        mismatches = total - matches

        duration = time.time() - self._session_start if self._session_start else 0

        return {
            "total": total,
            "matches": matches,
            "mismatches": mismatches,
            "match_rate": matches / total,
            "session_duration_sec": round(duration, 1),
        }

    def export_mismatches(self, filepath: str):
        """
        Exportiert nur Mismatches für Analyse.

        Args:
            filepath: Pfad zur JSON-Datei
        """
        mismatches = [e.to_dict() for e in self.events if not e.match]

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(mismatches, f, indent=2)
            logger.info(f"[FaceSelection] Exported {len(mismatches)} mismatches to {filepath}")
        except Exception as e:
            logger.error(f"[FaceSelection] Export failed: {e}")

    def export_all(self, filepath: str):
        """
        Exportiert alle Events.

        Args:
            filepath: Pfad zur JSON-Datei
        """
        data = {
            "stats": self.get_mismatch_stats(),
            "events": [e.to_dict() for e in self.events],
        }

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logger.info(f"[FaceSelection] Exported {len(self.events)} events to {filepath}")
        except Exception as e:
            logger.error(f"[FaceSelection] Export failed: {e}")

    def clear(self):
        """Löscht alle Events."""
        self.events.clear()
        self._session_start = time.time()
        logger.debug("[FaceSelection] Events cleared")

    def print_summary(self):
        """Gibt Zusammenfassung in Console aus."""
        stats = self.get_mismatch_stats()

        print("\n" + "=" * 50)
        print("Face Selection Summary")
        print("=" * 50)
        print(f"Total Events:     {stats['total']}")
        print(f"Matches:          {stats['matches']}")
        print(f"Mismatches:       {stats['mismatches']}")
        print(f"Match Rate:       {stats['match_rate']:.1%}")
        print(f"Session Duration: {stats['session_duration_sec']:.1f}s")
        print("=" * 50 + "\n")


# Globale Instanz
face_logger = FaceSelectionLogger()
