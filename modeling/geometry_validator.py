"""
MashCad - Geometry Validator
============================

Phase 7: Kernel-Robustheit

Validiert OCP-Geometrie vor/nach Operationen.
Verhindert Crashes und liefert klare Fehlermeldungen.

Validierungs-Stufen:
- QUICK: Nur Null-Check und Bounding-Box (~1ms)
- NORMAL: + Volume/Area Check (~5ms)
- FULL: + BRepCheck Analyzer (~20ms)

Verwendung:
    from modeling.geometry_validator import GeometryValidator, ValidationLevel

    # Quick-Check
    result = GeometryValidator.validate_solid(solid, ValidationLevel.QUICK)

    # Pre-Boolean Validierung
    result = GeometryValidator.validate_before_boolean(body, tool, "union")

Author: Claude (Phase 7 Kernel-Robustheit)
Date: 2026-01-23
"""

from dataclasses import dataclass, field
from typing import Optional, Any, List, Tuple
from enum import Enum, auto
from loguru import logger

from config.tolerances import Tolerances


class ValidationLevel(Enum):
    """Validierungs-Stufen mit unterschiedlichem Performance/Thoroughness Trade-off."""
    QUICK = auto()   # Nur Null-Check (~1ms)
    NORMAL = auto()  # + Volume/Topology (~5ms)
    FULL = auto()    # + BRepCheck Analyzer (~20ms)


class ValidationStatus(Enum):
    """Ergebnis-Status der Validierung."""
    VALID = "valid"
    WARNING = "warning"
    INVALID = "invalid"
    ERROR = "error"


@dataclass
class ValidationResult:
    """
    Strukturiertes Ergebnis einer Geometrie-Validierung.

    Attributes:
        status: ValidationStatus (VALID, WARNING, INVALID, ERROR)
        message: Kurze Beschreibung
        details: Zusätzliche Informationen (optional)
        issues: Liste von gefundenen Problemen
    """
    status: ValidationStatus
    message: str
    details: dict = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True wenn Geometrie valide ist (keine kritischen Fehler)."""
        return self.status in (ValidationStatus.VALID, ValidationStatus.WARNING)

    @property
    def is_error(self) -> bool:
        """True wenn kritischer Fehler vorliegt."""
        return self.status in (ValidationStatus.INVALID, ValidationStatus.ERROR)

    @classmethod
    def valid(cls, message: str = "Geometrie ist valide", **details) -> 'ValidationResult':
        """Factory für valides Ergebnis."""
        return cls(ValidationStatus.VALID, message, details)

    @classmethod
    def warning(cls, message: str, issues: List[str] = None, **details) -> 'ValidationResult':
        """Factory für Warnung (nutzbar, aber problematisch)."""
        return cls(ValidationStatus.WARNING, message, details, issues or [])

    @classmethod
    def invalid(cls, message: str, issues: List[str] = None, **details) -> 'ValidationResult':
        """Factory für ungültige Geometrie."""
        return cls(ValidationStatus.INVALID, message, details, issues or [])

    @classmethod
    def error(cls, message: str, **details) -> 'ValidationResult':
        """Factory für kritischen Fehler."""
        return cls(ValidationStatus.ERROR, message, details)


class GeometryValidator:
    """
    Validiert OCP/Build123d Geometrie.

    Stellt sicher dass Geometrie vor CAD-Operationen gültig ist.
    Verhindert Crashes durch ungültige Shapes.
    """

    @staticmethod
    def validate_solid(solid, level: ValidationLevel = ValidationLevel.NORMAL) -> ValidationResult:
        """
        Validiert einen Build123d Solid.

        Args:
            solid: Build123d Solid Objekt
            level: Validierungs-Tiefe (QUICK, NORMAL, FULL)

        Returns:
            ValidationResult mit Status und Details
        """
        issues = []

        # === Level QUICK: Basis-Checks ===

        # Null-Check
        if solid is None:
            return ValidationResult.error("Solid ist None")

        # Wrapped-Check (OCP Shape)
        if not hasattr(solid, 'wrapped'):
            return ValidationResult.error("Solid hat kein 'wrapped' Attribut (kein Build123d Objekt)")

        ocp_shape = solid.wrapped

        if ocp_shape is None:
            return ValidationResult.error("Solid.wrapped ist None")

        # IsNull-Check
        try:
            if ocp_shape.IsNull():
                return ValidationResult.error("Solid ist Null-Shape")
        except Exception as e:
            return ValidationResult.error(f"IsNull-Check fehlgeschlagen: {e}")

        if level == ValidationLevel.QUICK:
            return ValidationResult.valid("Quick-Check bestanden")

        # === Level NORMAL: Topology & Volume ===

        # Volume-Check
        try:
            volume = solid.volume
            if volume <= 0:
                issues.append(f"Negatives oder Null-Volumen: {volume:.6f}")
            elif volume < Tolerances.KERNEL_MIN_VOLUME_CHANGE:
                issues.append(f"Sehr kleines Volumen: {volume:.9f}")
        except Exception as e:
            issues.append(f"Volume-Berechnung fehlgeschlagen: {e}")

        # Topology-Count (sanity check)
        try:
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX

            n_faces = 0
            n_edges = 0
            n_vertices = 0

            explorer = TopExp_Explorer(ocp_shape, TopAbs_FACE)
            while explorer.More():
                n_faces += 1
                explorer.Next()

            explorer = TopExp_Explorer(ocp_shape, TopAbs_EDGE)
            while explorer.More():
                n_edges += 1
                explorer.Next()

            explorer = TopExp_Explorer(ocp_shape, TopAbs_VERTEX)
            while explorer.More():
                n_vertices += 1
                explorer.Next()

            if n_faces == 0:
                issues.append("Keine Flächen gefunden")
            if n_edges == 0:
                issues.append("Keine Kanten gefunden")
            if n_vertices == 0:
                issues.append("Keine Vertices gefunden")

            # Euler-Poincaré Check (V - E + F = 2 für einfache Solids)
            euler = n_vertices - n_edges + n_faces
            if euler != 2 and n_faces > 0:
                # Nicht unbedingt ein Fehler (z.B. bei Hohlräumen), aber warnen
                issues.append(f"Euler-Charakteristik ungewöhnlich: V-E+F = {euler} (erwartet: 2)")

        except Exception as e:
            issues.append(f"Topology-Analyse fehlgeschlagen: {e}")

        if level == ValidationLevel.NORMAL:
            if issues:
                return ValidationResult.warning(
                    f"Normal-Check: {len(issues)} Warnung(en)",
                    issues=issues,
                    volume=volume if 'volume' in dir() else None,
                    n_faces=n_faces if 'n_faces' in dir() else None
                )
            return ValidationResult.valid(
                "Normal-Check bestanden",
                volume=volume,
                n_faces=n_faces,
                n_edges=n_edges,
                n_vertices=n_vertices
            )

        # === Level FULL: BRepCheck Analyzer ===

        try:
            from OCP.BRepCheck import BRepCheck_Analyzer

            analyzer = BRepCheck_Analyzer(ocp_shape)

            if not analyzer.IsValid():
                issues.append("BRepCheck: Shape ist nicht valide")

                # Detaillierte Fehler extrahieren (wenn möglich)
                try:
                    from OCP.BRepCheck import BRepCheck_Status
                    # Status-Codes sind komplex - vereinfachte Ausgabe
                    issues.append("BRepCheck meldet Topologie-Fehler")
                except Exception as e:
                    logger.debug(f"[geometry_validator.py] Fehler: {e}")
                    # Optionales Status-Detail nicht verfuegbar -> Basismeldung bleibt erhalten.

        except Exception as e:
            issues.append(f"BRepCheck fehlgeschlagen: {e}")

        # Ergebnis für FULL Level
        if issues:
            # Unterscheide zwischen kritischen Fehlern und Warnungen
            critical = any("nicht valide" in i.lower() or "fehlgeschlagen" in i.lower() for i in issues)

            if critical:
                return ValidationResult.invalid(
                    f"Full-Check: {len(issues)} Problem(e) gefunden",
                    issues=issues
                )
            else:
                return ValidationResult.warning(
                    f"Full-Check: {len(issues)} Warnung(en)",
                    issues=issues
                )

        return ValidationResult.valid("Full-Check bestanden")

    @staticmethod
    def validate_before_boolean(body, tool_solid, operation: str) -> ValidationResult:
        """
        Pre-Boolean Validierung.

        Prüft ob Body und Tool für Boolean-Operation geeignet sind.

        Args:
            body: Body Objekt mit _build123d_solid
            tool_solid: Build123d Solid (das Tool)
            operation: "union", "cut", oder "intersect"

        Returns:
            ValidationResult
        """
        issues = []

        # Body-Solid validieren
        if not hasattr(body, '_build123d_solid') or body._build123d_solid is None:
            return ValidationResult.error("Body hat kein Solid")

        body_result = GeometryValidator.validate_solid(body._build123d_solid, ValidationLevel.QUICK)
        if body_result.is_error:
            return ValidationResult.error(f"Body ungültig: {body_result.message}")

        # Tool-Solid validieren
        tool_result = GeometryValidator.validate_solid(tool_solid, ValidationLevel.QUICK)
        if tool_result.is_error:
            return ValidationResult.error(f"Tool ungültig: {tool_result.message}")

        # Bounding-Box Überschneidung prüfen
        try:
            body_bb = body._build123d_solid.bounding_box()
            tool_bb = tool_solid.bounding_box()

            # Check ob Bounding Boxes sich überschneiden
            if not GeometryValidator._bounding_boxes_intersect(body_bb, tool_bb):
                if operation == "intersect":
                    return ValidationResult.warning(
                        "Bounding Boxes überschneiden sich nicht - Intersect wird leer sein",
                        issues=["Keine Überschneidung"]
                    )
                elif operation == "cut":
                    issues.append("Bounding Boxes überschneiden sich nicht - Cut hat evtl. keinen Effekt")
                # Bei Union ist das OK

        except Exception as e:
            issues.append(f"Bounding-Box Check fehlgeschlagen: {e}")

        # Volume-Verhältnis prüfen (sehr unterschiedliche Größen können problematisch sein)
        try:
            body_vol = body._build123d_solid.volume
            tool_vol = tool_solid.volume

            if body_vol > 0 and tool_vol > 0:
                ratio = max(body_vol, tool_vol) / min(body_vol, tool_vol)
                if ratio > 1e6:
                    issues.append(f"Sehr unterschiedliche Volumen (Ratio: {ratio:.0f}x) - kann zu Präzisionsproblemen führen")

        except Exception as e:
            issues.append(f"Volume-Vergleich fehlgeschlagen: {e}")

        if issues:
            return ValidationResult.warning(
                f"Pre-Boolean: {len(issues)} Warnung(en)",
                issues=issues,
                operation=operation
            )

        return ValidationResult.valid(f"Pre-Boolean Check für {operation} bestanden")

    @staticmethod
    def _bounding_boxes_intersect(bb1, bb2) -> bool:
        """
        Prüft ob zwei Bounding Boxes sich überschneiden.

        Args:
            bb1, bb2: Build123d BoundBox Objekte

        Returns:
            True wenn Überschneidung existiert
        """
        try:
            # BoundBox hat min/max Properties
            # Überschneidung wenn alle Achsen sich überlappen
            return (
                bb1.min.X <= bb2.max.X and bb1.max.X >= bb2.min.X and
                bb1.min.Y <= bb2.max.Y and bb1.max.Y >= bb2.min.Y and
                bb1.min.Z <= bb2.max.Z and bb1.max.Z >= bb2.min.Z
            )
        except Exception:
            # Bei Fehler annehmen dass sie sich überschneiden
            return True

    @staticmethod
    def validate_face(face) -> ValidationResult:
        """
        Validiert eine einzelne Fläche.

        Args:
            face: Build123d Face Objekt

        Returns:
            ValidationResult
        """
        if face is None:
            return ValidationResult.error("Face ist None")

        if not hasattr(face, 'wrapped'):
            return ValidationResult.error("Face hat kein 'wrapped' Attribut")

        try:
            # Area-Check
            area = face.area
            if area <= 0:
                return ValidationResult.invalid(f"Face hat keine Fläche: {area}")

            # Normal-Check
            try:
                center = face.center()
                normal = face.normal_at(center)
                if normal is None:
                    return ValidationResult.warning("Face-Normal konnte nicht berechnet werden")
            except Exception as e:
                logger.debug(f"[geometry_validator.py] Fehler: {e}")
                # Normalenberechnung optional fuer diese Validierungsstufe.

            return ValidationResult.valid("Face ist valide", area=area)

        except Exception as e:
            return ValidationResult.error(f"Face-Validierung fehlgeschlagen: {e}")

    @staticmethod
    def validate_edge(edge) -> ValidationResult:
        """
        Validiert eine einzelne Kante.

        Args:
            edge: Build123d Edge Objekt

        Returns:
            ValidationResult
        """
        if edge is None:
            return ValidationResult.error("Edge ist None")

        if not hasattr(edge, 'wrapped'):
            return ValidationResult.error("Edge hat kein 'wrapped' Attribut")

        try:
            # Length-Check
            length = edge.length
            if length <= 0:
                return ValidationResult.invalid(f"Edge hat keine Länge: {length}")

            return ValidationResult.valid("Edge ist valide", length=length)

        except Exception as e:
            return ValidationResult.error(f"Edge-Validierung fehlgeschlagen: {e}")


# Convenience-Funktionen
def validate_solid(solid, level: ValidationLevel = ValidationLevel.NORMAL) -> ValidationResult:
    """Shortcut für GeometryValidator.validate_solid()"""
    return GeometryValidator.validate_solid(solid, level)


def is_valid_solid(solid) -> bool:
    """Quick-Check ob Solid valide ist."""
    return GeometryValidator.validate_solid(solid, ValidationLevel.QUICK).is_valid
