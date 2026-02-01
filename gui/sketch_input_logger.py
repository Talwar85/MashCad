"""
MashCad - Sketch Input Logger
==============================

Strukturiertes Logging für Sketch Dimension Input.
Ermöglicht Debugging der Smart Entry und Value-Locking Funktionalität.

Verwendung:
    from gui.sketch_input_logger import sketch_logger

    # Debug aktivieren
    sketch_logger.enable_debug()

    # Nach Session
    print(sketch_logger.get_session_stats())
    sketch_logger.export_session("sketch_session.json")
"""

from loguru import logger
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
import json
import time


@dataclass
class DimensionInputEvent:
    """Einzelnes Dimension-Input Ereignis."""

    timestamp: float
    action: str            # "show", "hide", "edit", "lock", "unlock", "commit", "validate", "forward"
    tool: str              # SketchTool Name
    field: Optional[str]   # Feldname (length, width, angle, etc.)
    value: Optional[float] # Wert
    source: str            # "auto", "user", "forward", "reset", "system"
    valid: bool            # Validierung bestanden?
    error: Optional[str]   # Fehlermeldung

    def to_dict(self) -> dict:
        return {
            "ts": round(self.timestamp, 3),
            "action": self.action,
            "tool": self.tool,
            "field": self.field,
            "value": round(self.value, 4) if self.value is not None else None,
            "source": self.source,
            "valid": self.valid,
            "error": self.error,
        }


class SketchInputLogger:
    """
    Strukturiertes Logging für Sketch Dimension Input.

    Features:
    - Loggt Panel show/hide Events
    - Trackt Feld-Edits und Locks
    - Loggt Validierungsergebnisse
    - Berechnet Session-Statistiken
    """

    def __init__(self):
        self.events: List[DimensionInputEvent] = []
        self.debug_mode = False
        self._session_start: Optional[float] = None
        self._last_validation_error: Optional[str] = None

    def enable_debug(self):
        """Aktiviert detailliertes Logging."""
        self.debug_mode = True
        self._session_start = time.time()
        self.events.clear()
        logger.info("[SketchInput] Debug mode ENABLED")

    def disable_debug(self):
        """Deaktiviert Logging."""
        self.debug_mode = False
        logger.info("[SketchInput] Debug mode DISABLED")

    def log_show(self, tool: str, fields: List[str], source: str = "auto"):
        """
        Panel wird angezeigt.

        Args:
            tool: Name des aktuellen Tools
            fields: Liste der angezeigten Felder
            source: "auto" (Smart Entry) oder "tab" (manuell)
        """
        if not self.debug_mode:
            return

        logger.debug(f"[SketchInput] SHOW panel tool={tool} fields={fields} source={source}")
        self._add_event("show", tool, None, None, source, True, None)

    def log_hide(self, tool: str, reason: str = "unknown"):
        """
        Panel wird versteckt.

        Args:
            tool: Name des aktuellen Tools
            reason: Grund (esc, click_outside, confirm, tool_change)
        """
        if not self.debug_mode:
            return

        logger.debug(f"[SketchInput] HIDE panel tool={tool} reason={reason}")
        self._add_event("hide", tool, None, None, reason, True, None)

    def log_edit(self, tool: str, field: str, value: float, source: str):
        """
        Feld wurde editiert.

        Args:
            tool: Name des aktuellen Tools
            field: Feldname
            value: Neuer Wert
            source: "user" (manuell) oder "auto" (Maus-basiert)
        """
        if not self.debug_mode:
            return

        logger.debug(f"[SketchInput] EDIT {field}={value:.2f} tool={tool} source={source}")
        self._add_event("edit", tool, field, value, source, True, None)

    def log_lock(self, tool: str, field: str, value: float):
        """
        Feld wurde gelockt (User-Eingabe).

        Args:
            tool: Name des aktuellen Tools
            field: Feldname
            value: Gelockter Wert
        """
        if not self.debug_mode:
            return

        logger.debug(f"[SketchInput] 🔒 LOCK {field}={value:.2f} tool={tool}")
        self._add_event("lock", tool, field, value, "user", True, None)

    def log_unlock(self, tool: str, field: str):
        """
        Feld wurde entsperrt (Doppelklick).

        Args:
            tool: Name des aktuellen Tools
            field: Feldname
        """
        if not self.debug_mode:
            return

        logger.debug(f"[SketchInput] 🔓 UNLOCK {field} tool={tool}")
        self._add_event("unlock", tool, field, None, "reset", True, None)

    def log_validate(self, tool: str, field: str, value: float,
                     valid: bool, error: str = None):
        """
        Validierung durchgeführt.

        Args:
            tool: Name des aktuellen Tools
            field: Feldname
            value: Validierter Wert
            valid: Validierung bestanden?
            error: Fehlermeldung (wenn nicht valid)
        """
        if not self.debug_mode:
            return

        self._last_validation_error = error

        status = "✓" if valid else "✗"
        msg = f"[SketchInput] {status} VALIDATE {field}={value:.2f} valid={valid}"
        if error:
            msg += f" error=\"{error}\""

        if valid:
            logger.debug(msg)
        else:
            logger.warning(msg)

        self._add_event("validate", tool, field, value, "system", valid, error)

    def log_commit(self, tool: str, field: str, value: float):
        """
        Feld wurde committed (Enter).

        Args:
            tool: Name des aktuellen Tools
            field: Feldname
            value: Committeter Wert
        """
        if not self.debug_mode:
            return

        logger.info(f"[SketchInput] ✓ COMMIT {field}={value:.2f} tool={tool}")
        self._add_event("commit", tool, field, value, "user", True, None)

    def log_forward(self, tool: str, field: str, char: str):
        """
        Tastendruck wurde an Feld weitergeleitet.

        Args:
            tool: Name des aktuellen Tools
            field: Zielfeld
            char: Weitergeleitetes Zeichen
        """
        if not self.debug_mode:
            return

        logger.trace(f"[SketchInput] FORWARD '{char}' → {field} tool={tool}")
        self._add_event("forward", tool, field, None, "forward", True, None)

    def _add_event(self, action: str, tool: str, field: Optional[str],
                   value: Optional[float], source: str, valid: bool, error: Optional[str]):
        """Fügt Event zur Liste hinzu."""
        event = DimensionInputEvent(
            timestamp=time.time(),
            action=action,
            tool=tool,
            field=field,
            value=value,
            source=source,
            valid=valid,
            error=error,
        )
        self.events.append(event)

    def get_session_stats(self) -> dict:
        """
        Gibt Statistiken der aktuellen Session zurück.

        Returns:
            Dict mit Gesamtzahl, Actions, Validierungsrate, Dauer
        """
        if not self.events:
            return {"total": 0}

        # Action-Statistiken
        actions = {}
        for e in self.events:
            actions[e.action] = actions.get(e.action, 0) + 1

        # Validierungs-Erfolgsrate
        validation_events = [e for e in self.events if e.action == "validate"]
        valid_count = sum(1 for e in validation_events if e.valid)
        validation_rate = valid_count / len(validation_events) if validation_events else 1.0

        # Tool-Verteilung
        tools = {}
        for e in self.events:
            tools[e.tool] = tools.get(e.tool, 0) + 1

        # Dauer
        duration = time.time() - self._session_start if self._session_start else 0

        return {
            "total": len(self.events),
            "actions": actions,
            "tools": tools,
            "validation_success_rate": round(validation_rate, 3),
            "duration_sec": round(duration, 1),
        }

    def export_session(self, filepath: str):
        """
        Exportiert Session-Log.

        Args:
            filepath: Pfad zur JSON-Datei
        """
        data = {
            "stats": self.get_session_stats(),
            "events": [e.to_dict() for e in self.events],
        }

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logger.info(f"[SketchInput] Exported {len(self.events)} events to {filepath}")
        except Exception as e:
            logger.error(f"[SketchInput] Export failed: {e}")

    def clear(self):
        """Löscht alle Events."""
        self.events.clear()
        self._session_start = time.time()
        logger.debug("[SketchInput] Events cleared")

    def print_summary(self):
        """Gibt Zusammenfassung in Console aus."""
        stats = self.get_session_stats()

        print("\n" + "=" * 50)
        print("Sketch Input Summary")
        print("=" * 50)
        print(f"Total Events:      {stats['total']}")
        print(f"Validation Rate:   {stats.get('validation_success_rate', 1.0):.1%}")
        print(f"Session Duration:  {stats.get('duration_sec', 0):.1f}s")

        if 'actions' in stats:
            print("\nActions:")
            for action, count in sorted(stats['actions'].items()):
                print(f"  {action}: {count}")

        if 'tools' in stats:
            print("\nTools:")
            for tool, count in sorted(stats['tools'].items(), key=lambda x: -x[1]):
                print(f"  {tool}: {count}")

        print("=" * 50 + "\n")


# Globale Instanz
sketch_logger = SketchInputLogger()
