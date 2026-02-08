"""
Centralized user-facing feedback text for sketch solver and trim operations.
"""

from typing import Any


def _status_name(status: Any) -> str:
    if status is None:
        return ""
    name = getattr(status, "name", None)
    if isinstance(name, str):
        return name.upper()
    if isinstance(status, str):
        return status.upper()
    return ""


def format_solver_failure_message(status: Any, message: str, dof: float | int | None = None, context: str = "Solver") -> str:
    """
    Builds a consistent, actionable message for solver failures.
    """
    status_name = _status_name(status)
    base = (message or "").strip() or "Unbekannter Solver-Fehler"
    lower = base.lower()

    if status_name == "OVER_CONSTRAINED":
        hint = "Widerspruechliche Constraints. Entferne oder entspanne mindestens ein Constraint."
    elif status_name == "UNDER_CONSTRAINED":
        dof_txt = ""
        if dof is not None:
            try:
                dof_txt = f" ({int(dof)} DOF)"
            except Exception:
                dof_txt = ""
        hint = f"Skizze ist unterbestimmt{dof_txt}. Fuege fehlende Constraints hinzu."
    elif "nan" in lower or "inf" in lower:
        hint = "Numerische Instabilitaet erkannt. Pruefe ungueltige Masse oder degenerierte Geometrie."
    elif "ungueltig" in lower or "entities" in lower:
        hint = "Mindestens ein Constraint ist ungueltig oder verweist auf geloeschte Geometrie."
    else:
        hint = "Skizze und Constraints sind in diesem Zustand nicht loesbar."

    return f"{context}: {base} | {hint}"


def format_trim_failure_message(error: str, target_type: str = "") -> str:
    """
    Builds a consistent, actionable message for trim failures.
    """
    raw = (error or "").strip() or "Trim fehlgeschlagen"
    target = f" ({target_type})" if target_type else ""
    lower = raw.lower()

    if "kein ziel" in lower:
        return f"Trim{target}: Keine Geometrie unter dem Cursor. Naeher zoomen oder Snapping nutzen."
    if "kein segment" in lower:
        return f"Trim{target}: Kein trennbares Segment gefunden. Schnittpunkt erzeugen oder naeher klicken."
    if "fehlgeschlagen" in lower:
        return f"Trim{target}: {raw}. Aenderung wurde zurueckgesetzt."
    return f"Trim{target}: {raw}"

