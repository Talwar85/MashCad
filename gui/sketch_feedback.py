"""
Centralized user-facing feedback text for sketch solver and trim operations.

W33 EPIC AA2: Enhanced solver feedback with actionable next steps.
"""

from typing import Any, List, Tuple


def _status_name(status: Any) -> str:
    if status is None:
        return ""
    name = getattr(status, "name", None)
    if isinstance(name, str):
        return name.upper()
    if isinstance(status, str):
        return status.upper()
    return ""


def _extract_constraint_suggestions(message: str, status_name: str) -> List[str]:
    """
    Extrahiert konkrete Handlungsempfehlungen aus Solver-Meldungen.
    """
    suggestions = []
    lower = message.lower()

    if status_name == "OVER_CONSTRAINED":
        suggestions.append("Entferne das letzte Constraint")
        suggestions.append("Pruefe auf doppelte Constraints")
        suggestions.append("Reduziere Dimensions-Constraints")
    elif status_name == "UNDER_CONSTRAINED":
        suggestions.append("Fuege fehlende Abstaende/Winkel hinzu")
        suggestions.append("Fixiere Punkte auf Referenzgeometrie")
    elif "fixed" in lower and ("cannot" in lower or "nicht" in lower):
        suggestions.append("Entferne Fixed-Constraint oder ziehe andere Geometrie")
    elif "conflicting" in lower or "widerspr" in lower:
        suggestions.append("Entferne einen der konfliktierenden Constraints")
        suggestions.append("Aendere Dimensionswerte")
    elif "coincident" in lower or "koinzid" in lower:
        suggestions.append("Pruefe ob Punkte auf gleicher Position liegen")
        suggestions.append("Entferne ueberfluessige Coincident-Constraints")
    elif "tangent" in lower or "tangent" in lower:
        suggestions.append("Pruefe ob Geometrie tangieren kann")
        suggestions.append("Aendere Radius oder Position")
    elif "radius" in lower or "diameter" in lower:
        suggestions.append("Pruefe Radius/Diameter-Constraints")
        suggestions.append("Radius muss groesser 0 sein")

    return suggestions


def format_solver_failure_message(
    status: Any,
    message: str,
    dof: float | int | None = None,
    context: str = "Solver",
    include_next_actions: bool = True,
) -> str:
    """
    Builds a consistent, actionable message for solver failures.

    Args:
        status: Solver result status object or string
        message: Error message from solver
        dof: Degrees of freedom (if available)
        context: Operation context (e.g., "Direct edit", "Fillet")
        include_next_actions: Whether to include actionable next steps

    Returns:
        Formatted error message with hints
    """
    status_name = _status_name(status)
    base = (message or "").strip() or "Unbekannter Solver-Fehler"
    lower = base.lower()

    # Status-spezifische Hinweise
    if status_name == "OVER_CONSTRAINED":
        hint = "Zu viele Constraints fuer verfuegbare Geometrie."
    elif status_name == "UNDER_CONSTRAINED":
        dof_txt = ""
        if dof is not None:
            try:
                dof_val = int(dof) if dof >= 1 else "0"
                dof_txt = f" ({dof_val} DOF)"
            except Exception:
                dof_txt = ""
        hint = f"Skizze ist unterbestimmt{dof_txt}."
    elif "nan" in lower or "inf" in lower:
        hint = "Numerische Instabilitaet erkannt."
    elif "ungueltig" in lower or "entities" in lower or "invalid" in lower:
        hint = "Mindestens ein Constraint verweist auf ungueltige Geometrie."
    elif "fixed" in lower and ("cannot" in lower or "nicht" in lower):
        hint = "Fixierte Geometrie kann nicht verschoben werden."
    elif "conflicting" in lower or "widerspr" in lower or "conflict" in lower:
        hint = "Widerspruechliche Constraints erkannt."
    else:
        hint = "Skizze und Constraints sind in diesem Zustand nicht loesbar."

    # Naechste Aktionen (optional)
    next_action = ""
    if include_next_actions:
        suggestions = _extract_constraint_suggestions(base, status_name)
        if suggestions:
            # Nur die erste relevante Empfehlung anzeigen
            next_action = f" → {suggestions[0]}"

    return f"{context}: {base} | {hint}{next_action}"


def format_direct_edit_solver_message(
    mode: str,
    status: Any,
    message: str,
    dof: float | int | None = None,
) -> str:
    """
    Spezialisierte Fehlermeldung fuer Direct-Edit-Operationen.

    Args:
        mode: Direct-Edit-Modus (radius, center, vertex, etc.)
        status: Solver result status
        message: Error message
        dof: Degrees of freedom

    Returns:
        Kontext-spezifische Fehlermeldung
    """
    mode_display = {
        "radius": "Radius",
        "center": "Verschieben",
        "endpoint_start": "Endpunkt",
        "endpoint_end": "Endpunkt",
        "midpoint": "Linie verschieben",
        "vertex": "Punkt verschieben",
        "radius_x": "X-Radius",
        "radius_y": "Y-Radius",
        "line_edge": "Kante",
        "line_move": "Linie",
    }.get(mode, "Geometrie")

    return format_solver_failure_message(
        status,
        message,
        dof=dof,
        context=f"{mode_display}-Bearbeitung",
        include_next_actions=True,
    )


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


def format_trim_warning_message(message: str, target_type: str = "") -> str:
    """
    Builds a consistent, actionable message for trim warnings.
    """
    raw = (message or "").strip() or "Trim mit Einschraenkung abgeschlossen"
    target = f" ({target_type})" if target_type else ""
    lower = raw.lower()

    if "zu klein" in lower:
        return f"Trim{target}: Restsegment unter Toleranz und nicht erstellt."
    return f"Trim{target}: {raw}"
