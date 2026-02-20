"""
MashCAD - Error Diagnostics Framework
======================================

Phase 2: CH-008 - Fehlerdiagnostik im UI verbessern

Bietet kontext-sensitive Fehlererklärungen und "Next Action" Vorschläge
für alle CAD-Operationen. Baut auf bestehendem Error Envelope auf.

Usage:
    from modeling.error_diagnostics import ErrorDiagnostics, ErrorExplanation
    
    # Nach einem Fehler
    result = some_operation()
    if result.is_error:
        explanation = ErrorDiagnostics.explain(result)
        print(explanation.title)           # Kurze Überschrift
        print(explanation.description)      # Detaillierte Erklärung
        print(explanation.next_actions)     # Liste von Lösungsschritten

Author: Kimi (CH-008 Implementation)
Date: 2026-02-19
Branch: feature/v1-ux-aiB
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Dict, Any, Callable
from pathlib import Path
from loguru import logger


class ErrorCategory(Enum):
    """Kategorien für Fehler-Klassifizierung."""
    GEOMETRY = "geometry"           # Geometrie-bezogene Fehler
    TOPOLOGY = "topology"           # Topologie-Probleme
    CONSTRAINT = "constraint"       # Sketch-Constraint Fehler
    REFERENCE = "reference"         # Referenz-Auflösung
    PARAMETER = "parameter"         # Parameter-Validierung
    OPERATION = "operation"         # Operation-spezifisch
    DEPENDENCY = "dependency"       # Fehlende Abhängigkeiten
    IMPORT_EXPORT = "import_export" # Import/Export Fehler
    SYSTEM = "system"               # System/interne Fehler
    UNKNOWN = "unknown"             # Unbekannt


class ErrorSeverity(Enum):
    """Schweregrad für Fehler."""
    INFO = "info"           # Information, kein Handlungsbedarf
    WARNING = "warning"     # Warnung, Operation möglich
    RECOVERABLE = "recoverable"  # Fehler, aber Recovery möglich
    CRITICAL = "critical"   # Kritischer Fehler, Blockierung


class ErrorActionType(Enum):
    """Typen von Aktionen die bei Fehlern ausgeführt werden können."""
    SELECT_REFERENCE = "select_reference"    # Referenz neu auswählen
    EDIT_FEATURE = "edit_feature"            # Feature bearbeiten
    UNDO = "undo"                            # Rückgängig machen
    VALIDATE_GEOMETRY = "validate_geometry"  # Geometrie validieren
    OPEN_SETTINGS = "open_settings"          # Einstellungen öffnen
    SHOW_DOCS = "show_docs"                  # Dokumentation anzeigen
    REPAIR_GEOMETRY = "repair_geometry"      # Geometrie reparieren
    RETRY = "retry"                          # Operation wiederholen
    CUSTOM = "custom"                        # Benutzerdefinierte Aktion


@dataclass
class ErrorExplanation:
    """
    Strukturierte Fehlererklärung für UI-Anzeige.
    
    Attributes:
        error_code: Maschinenlesbarer Error-Code
        category: Fehler-Kategorie
        severity: Schweregrad
        title: Kurze Überschrift (1 Zeile)
        description: Detaillierte Erklärung (1-2 Sätze)
        technical_details: Technische Details für erfahrene Nutzer
        next_actions: Liste konkreter Lösungsschritte
        related_docs: Links zu Dokumentation
        can_auto_fix: Ob automatische Behebung möglich
        auto_fix_action: Beschreibung der Auto-Fix Aktion
        action_type: Typ der empfohlenen Aktion (für UI-Buttons)
        action_callback: Optionaler Callback für die Aktion
    """
    error_code: str
    category: ErrorCategory
    severity: ErrorSeverity
    title: str
    description: str
    technical_details: str = ""
    next_actions: List[str] = field(default_factory=list)
    related_docs: List[str] = field(default_factory=list)
    can_auto_fix: bool = False
    auto_fix_action: str = ""
    action_type: Optional[ErrorActionType] = None
    action_callback: Optional[Callable] = None
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_user_message(self, include_technical: bool = False) -> str:
        """Formatiert für Nutzer-Anzeige."""
        lines = [f"**{self.title}**", ""]
        lines.append(self.description)
        
        if self.next_actions:
            lines.append("\n**Nächste Schritte:**")
            for i, action in enumerate(self.next_actions, 1):
                lines.append(f"{i}. {action}")
        
        if include_technical and self.technical_details:
            lines.append(f"\n_Technisch: {self.technical_details}_")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialisierung für Persistence/Logging."""
        return {
            "error_code": self.error_code,
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "technical_details": self.technical_details,
            "next_actions": self.next_actions,
            "can_auto_fix": self.can_auto_fix,
            "auto_fix_action": self.auto_fix_action,
            "action_type": self.action_type.value if self.action_type else None,
        }
    
    def get_action_button_text(self) -> str:
        """Gibt den Text für den Aktions-Button zurück."""
        if self.auto_fix_action:
            return self.auto_fix_action
        
        # Fallback basierend auf action_type
        action_texts = {
            ErrorActionType.SELECT_REFERENCE: "Referenz auswählen",
            ErrorActionType.EDIT_FEATURE: "Feature bearbeiten",
            ErrorActionType.UNDO: "Rückgängig",
            ErrorActionType.VALIDATE_GEOMETRY: "Geometrie prüfen",
            ErrorActionType.OPEN_SETTINGS: "Einstellungen",
            ErrorActionType.SHOW_DOCS: "Hilfe anzeigen",
            ErrorActionType.REPAIR_GEOMETRY: "Reparieren",
            ErrorActionType.RETRY: "Erneut versuchen",
        }
        return action_texts.get(self.action_type, "Aktion ausführen")


# =============================================================================
# Error Knowledge Base
# =============================================================================

ERROR_KNOWLEDGE_BASE: Dict[str, Dict[str, Any]] = {
    # === Geometry Errors ===
    "geometry_non_manifold": {
        "category": ErrorCategory.GEOMETRY,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Nicht-manifold Geometrie",
        "description": "Die Geometrie enthält Kanten, die von mehr als zwei Faces geteilt werden, oder offene Flächen.",
        "technical_details": "Non-manifold topology detected in BRep structure",
        "next_actions": [
            "Prüfen Sie das Modell auf überlappende oder sich schneidende Faces",
            "Verwenden Sie 'Heilung' um kleine Lücken zu schließen",
            "Überprüfen Sie Boolean-Operationen auf Fehler",
            "Reduzieren Sie Feature-Größen und versuchen Sie es erneut"
        ],
        "can_auto_fix": True,
        "auto_fix_action": "Automatische Heilung mit BRep-Repair",
    },
    "geometry_self_intersection": {
        "category": ErrorCategory.GEOMETRY,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Selbstüberschneidende Geometrie",
        "description": "Das Modell schneidet sich selbst, was zu ungültiger Topologie führt.",
        "technical_details": "Self-intersecting geometry in solid",
        "next_actions": [
            "Verkleinern Sie den Radius bei Fillet/Chamfer",
            "Überprüfen Sie Sweep-Pfade auf Kollisionen",
            "Vereinfachen Sie das Profil",
            "Verwenden Sie kleinere Extrusions-Werte"
        ],
    },
    "geometry_degenerate": {
        "category": ErrorCategory.GEOMETRY,
        "severity": ErrorSeverity.WARNING,
        "title": "Degenerierte Geometrie",
        "description": "Das Modell enthält Faces oder Edges mit verschwindend kleiner Größe.",
        "technical_details": "Degenerate faces (zero area) detected",
        "next_actions": [
            "Entfernen Sie sehr kleine Features",
            "Erhöhen Sie die Toleranz für die Operation",
            "Prüfen Sie das Sketch-Profil auf doppelte Punkte"
        ],
    },
    
    # === Topology Errors ===
    "topology_build_error": {
        "category": ErrorCategory.TOPOLOGY,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Topologie konnte nicht aufgebaut werden",
        "description": "Die geometrische Operation konnte die Topologie des Ergebnisses nicht korrekt erstellen.",
        "technical_details": "BRep builder failed to create valid topology",
        "next_actions": [
            "Vereinfachen Sie die Eingabe-Geometrie",
            "Reduzieren Sie die Anzahl der gleichzeitigen Operationen",
            "Prüfen Sie die Eingabe auf gültige Solids"
        ],
    },
    
    # === Constraint Errors ===
    "constraint_over_constrained": {
        "category": ErrorCategory.CONSTRAINT,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Überbestimmtes Sketch",
        "description": "Das Sketch enthält widersprüchliche oder redundante Constraints.",
        "technical_details": "Sketch solver detected over-constrained system",
        "next_actions": [
            "Löschen Sie redundanten Constraints (markiert in rot)",
            "Konvertieren Sie Dimensions-Constraints zu Referenzen",
            "Verwenden Sie 'Auto-Lösen' zur Konflikt-Erkennung",
            "Entfernen Sie kürzlich hinzugefügte Constraints"
        ],
        "can_auto_fix": True,
        "auto_fix_action": "Redundante Constraints entfernen",
    },
    "constraint_under_constrained": {
        "category": ErrorCategory.CONSTRAINT,
        "severity": ErrorSeverity.WARNING,
        "title": "Unterbestimmtes Sketch",
        "description": "Das Sketch hat nicht genug Constraints für eine eindeutige Lösung.",
        "technical_details": "Sketch solver detected under-constrained system",
        "next_actions": [
            "Fügen Sie weitere Dimensions- oder Relations-Constraints hinzu",
            "Fixieren Sie Punkte mit Fix-Constraint",
            "Verwenden Sie 'Vollständig bestimmen' für Vorschläge"
        ],
    },
    "constraint_solver_failed": {
        "category": ErrorCategory.CONSTRAINT,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Constraint-Löser fehlgeschlagen",
        "description": "Der Solver konnte das Constraint-System nicht lösen.",
        "technical_details": "Constraint solver convergence failed",
        "next_actions": [
            "Vereinfachen Sie das Constraint-System",
            "Entfernen Sie kürzlich hinzugefügte Constraints",
            "Prüfen Sie auf widersprüchliche Werte",
            "Erhöhen Sie die Solver-Toleranz"
        ],
    },
    
    # === Reference Errors ===
    "reference_not_found": {
        "category": ErrorCategory.REFERENCE,
        "severity": ErrorSeverity.CRITICAL,
        "title": "Referenz nicht gefunden",
        "description": "Eine referenzierte Geometrie (Face, Edge, Punkt) konnte nicht gefunden werden.",
        "technical_details": "TNP reference resolution failed - shape not found",
        "next_actions": [
            "Wählen Sie die Referenz neu aus",
            "Prüfen Sie ob das referenzierte Feature unterdrückt ist",
            "Aktualisieren Sie die Referenz über 'Referenz ändern'",
            "Erstellen Sie das Feature neu falls die Geometrie sich geändert hat"
        ],
    },
    "reference_ambiguous": {
        "category": ErrorCategory.REFERENCE,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Mehrdeutige Referenz",
        "description": "Die Referenz konnte nicht eindeutig aufgelöst werden.",
        "technical_details": "Multiple candidate shapes for reference",
        "next_actions": [
            "Wählen Sie die Referenz erneut aus",
            "Verwenden Sie spezifischere Auswahlkriterien",
            "Prüfen Sie ob mehrere ähnliche Geometrien existieren"
        ],
    },
    
    # === Parameter Errors ===
    "parameter_invalid": {
        "category": ErrorCategory.PARAMETER,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Ungültiger Parameter",
        "description": "Ein Parameter-Wert liegt außerhalb des gültigen Bereichs.",
        "technical_details": "Parameter validation failed",
        "next_actions": [
            "Überprüfen Sie die Parameter-Grenzen",
            "Verwenden Sie positive Werte für Abstände",
            "Stellen Sie sicher dass Winkel zwischen 0° und 360° liegen",
            "Reduzieren Sie Werte die zu Selbstüberschneidung führen"
        ],
    },
    "parameter_dimension_too_large": {
        "category": ErrorCategory.PARAMETER,
        "severity": ErrorSeverity.WARNING,
        "title": "Dimension zu groß",
        "description": "Eine Dimension überschreitet die empfohlene Modell-Größe.",
        "technical_details": "Dimension exceeds recommended model bounds",
        "next_actions": [
            "Verwenden Sie kleinere Einheiten (mm statt m)",
            "Skalieren Sie das gesamte Modell",
            "Prüfen Sie ob die Einheit korrekt ist"
        ],
    },
    
    # === Operation Errors ===
    "operation_boolean_failed": {
        "category": ErrorCategory.OPERATION,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Boolean-Operation fehlgeschlagen",
        "description": "Die Schnitt-, Vereinigungs- oder Differenz-Operation konnte nicht ausgeführt werden.",
        "technical_details": "OCC Boolean operation failed",
        "next_actions": [
            "Stellen Sie sicher dass sich die Bodies überlappen",
            "Vereinfachen Sie die Geometrie der beteiligten Bodies",
            "Erhöhen Sie die Toleranz für die Operation",
            "Versuchen Sie die Operation in umgekehrter Reihenfolge"
        ],
    },
    "operation_fillet_failed": {
        "category": ErrorCategory.OPERATION,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Fillet fehlgeschlagen",
        "description": "Die Rundung konnte nicht an allen gewählten Kanten erstellt werden.",
        "technical_details": "Fillet operation failed on one or more edges",
        "next_actions": [
            "Verringern Sie den Fillet-Radius",
            "Wählen Sie weniger Kanten aus",
            "Vermeiden Sie Kanten mit sehr kleinen Winkeln",
            "Verwenden Sie Face-Fillet statt Edge-Fillet"
        ],
    },
    "operation_extrude_failed": {
        "category": ErrorCategory.OPERATION,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Extrusion fehlgeschlagen",
        "description": "Das Profil konnte nicht extrudiert werden.",
        "technical_details": "Extrude operation failed",
        "next_actions": [
            "Prüfen Sie ob das Profil geschlossen ist",
            "Vermeiden Sie sich selbst überschneidende Profiles",
            "Reduzieren Sie die Extrusions-Tiefe",
            "Prüfen Sie auf degenerierte Profilelemente"
        ],
    },
    
    # === Dependency Errors ===
    "dependency_ocp_unavailable": {
        "category": ErrorCategory.DEPENDENCY,
        "severity": ErrorSeverity.CRITICAL,
        "title": "OCP Bibliothek nicht verfügbar",
        "description": "Die OpenCASCADE Python-Bindings (OCP) konnten nicht geladen werden.",
        "technical_details": "OCP module import failed",
        "next_actions": [
            "Installieren Sie OCP: pip install ocp",
            "Überprüfen Sie Ihre Python-Umgebung",
            "Starten Sie die Anwendung neu",
            "Kontaktieren Sie den Support falls das Problem besteht"
        ],
    },
    # CH-006: OCP API Compatibility Errors
    "ocp_api_unavailable": {
        "category": ErrorCategory.DEPENDENCY,
        "severity": ErrorSeverity.CRITICAL,
        "title": "OCP API nicht verfügbar",
        "description": "Eine erforderliche OCP API-Klasse oder -Methode ist in der installierten Version nicht verfügbar.",
        "technical_details": "OCP API class/method not found - version mismatch or missing feature",
        "next_actions": [
            "Aktualisieren Sie OCP auf die neueste Version: pip install --upgrade ocp",
            "Prüfen Sie die OCP-Version mit: python -c \"import OCP; print(OCP.__version__)\"",
            "Konsultieren Sie die Dokumentation für kompatible Versionen",
            "Verwenden Sie eine alternative Operation falls verfügbar"
        ],
    },
    "ocp_api_version_mismatch": {
        "category": ErrorCategory.DEPENDENCY,
        "severity": ErrorSeverity.WARNING,
        "title": "OCP Version inkompatibel",
        "description": "Die installierte OCP-Version unterscheidet sich von der erwarteten Version. Einige Funktionen sind möglicherweise eingeschränkt.",
        "technical_details": "OCP version mismatch - some APIs may be unavailable or behave differently",
        "next_actions": [
            "Prüfen Sie die aktuelle OCP-Version",
            "Vergleichen Sie mit der empfohlenen Version (7.8.x)",
            "Führen Sie ein Upgrade durch falls nötig",
            "Einige erweiterte Funktionen sind möglicherweise nicht verfügbar"
        ],
    },
    "ocp_feature_degraded": {
        "category": ErrorCategory.DEPENDENCY,
        "severity": ErrorSeverity.INFO,
        "title": "OCP Feature eingeschränkt",
        "description": "Eine optionale OCP-Funktion ist nicht verfügbar. Die Anwendung funktioniert weiterhin, aber mit eingeschränkten Funktionen.",
        "technical_details": "Optional OCP API not available - feature degraded",
        "next_actions": [
            "Grundlegende Funktionen bleiben verfügbar",
            "Für volle Funktionalität OCP aktualisieren",
            "Siehe Protokoll für Details zu fehlenden APIs"
        ],
    },
    "dependency_build123d_unavailable": {
        "category": ErrorCategory.DEPENDENCY,
        "severity": ErrorSeverity.CRITICAL,
        "title": "Build123d nicht verfügbar",
        "description": "Die Build123d Bibliothek konnte nicht geladen werden.",
        "technical_details": "Build123d module import failed",
        "next_actions": [
            "Installieren Sie Build123d: pip install build123d",
            "Überprüfen Sie Ihre Python-Umgebung",
            "Starten Sie die Anwendung neu"
        ],
    },
    
    # === Import/Export Errors ===
    "import_file_not_found": {
        "category": ErrorCategory.IMPORT_EXPORT,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Datei nicht gefunden",
        "description": "Die zu importierende Datei existiert nicht oder ist nicht lesbar.",
        "technical_details": "File not found or not accessible",
        "next_actions": [
            "Überprüfen Sie den Dateipfad",
            "Stellen Sie sicher dass die Datei existiert",
            "Prüfen Sie die Leseberechtigungen"
        ],
    },
    "import_format_unsupported": {
        "category": ErrorCategory.IMPORT_EXPORT,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Nicht unterstütztes Dateiformat",
        "description": "Das Dateiformat wird nicht unterstützt oder konnte nicht erkannt werden.",
        "technical_details": "File format not supported",
        "next_actions": [
            "Verwenden Sie ein unterstütztes Format (STEP, STL, OBJ)",
            "Überprüfen Sie die Dateiendung",
            "Konvertieren Sie die Datei in ein unterstütztes Format"
        ],
    },
    "export_no_valid_geometry": {
        "category": ErrorCategory.IMPORT_EXPORT,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Keine gültige Geometrie zum Exportieren",
        "description": "Es wurde keine exportierbare Geometrie gefunden.",
        "technical_details": "No valid solids or meshes for export",
        "next_actions": [
            "Stellen Sie sicher dass mindestens ein Body sichtbar ist",
            "Prüfen Sie ob die Bodies gültige Solids enthalten",
            "Erstellen Sie Geometrie bevor Sie exportieren"
        ],
    },
    
    # === TNP (Topology Naming Protocol) Errors ===
    "tnp_ref_missing": {
        "category": ErrorCategory.REFERENCE,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Referenz fehlt",
        "description": "Die referenzierte Kante oder Fläche existiert nicht mehr. Die Topologie hat sich geändert.",
        "technical_details": "TNP reference missing - shape no longer exists in updated topology",
        "next_actions": [
            "Wählen Sie eine neue Referenz-Kante oder-Fläche aus",
            "Öffnen Sie das Feature und aktualisieren Sie die Referenz",
            "Prüfen Sie ob vorangegangene Operationen die Geometrie verändert haben"
        ],
        "can_auto_fix": True,
        "auto_fix_action": "Neue Referenz auswählen",
        "action_type": "select_reference",
    },
    "tnp_ref_mismatch": {
        "category": ErrorCategory.REFERENCE,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Referenz-Typ stimmt nicht überein",
        "description": "Die Referenz entspricht nicht dem erwarteten Typ (Kante statt Fläche oder umgekehrt).",
        "technical_details": "TNP reference type mismatch - expected different shape type",
        "next_actions": [
            "Bearbeiten Sie das Feature um die Referenzen zu aktualisieren",
            "Wählen Sie eine Referenz des korrekten Typs",
            "Prüfen Sie die Feature-Parameter auf Konsistenz"
        ],
        "can_auto_fix": True,
        "auto_fix_action": "Feature bearbeiten",
        "action_type": "edit_feature",
    },
    "tnp_ref_ambiguous": {
        "category": ErrorCategory.REFERENCE,
        "severity": ErrorSeverity.WARNING,
        "title": "Mehrdeutige Topologie-Referenz",
        "description": "Die Referenz konnte nicht eindeutig zugeordnet werden. Mehrere ähnliche Geometrien gefunden.",
        "technical_details": "TNP ambiguous reference - multiple candidates match the reference criteria",
        "next_actions": [
            "Wählen Sie die gewünschte Geometrie explizit aus",
            "Verwenden Sie spezifischere Auswahlkriterien",
            "Benennen Sie Geometrien zur besseren Unterscheidung"
        ],
    },
    
    # === Rebuild Errors ===
    "rebuild_failed": {
        "category": ErrorCategory.OPERATION,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Neuberechnung fehlgeschlagen",
        "description": "Das Feature konnte nach Parameter-Änderung nicht neu berechnet werden.",
        "technical_details": "Feature rebuild failed - dependency graph evaluation error",
        "next_actions": [
            "Machen Sie die letzte Operation rückgängig und versuchen Sie andere Parameter",
            "Prüfen Sie abhängige Features auf Fehler",
            "Vereinfachen Sie die Feature-Hierarchie"
        ],
        "can_auto_fix": True,
        "auto_fix_action": "Rückgängig machen",
        "action_type": "undo",
    },
    "rebuild_circular_dependency": {
        "category": ErrorCategory.DEPENDENCY,
        "severity": ErrorSeverity.CRITICAL,
        "title": "Zirkuläre Abhängigkeit",
        "description": "Es wurde eine zirkuläre Abhängigkeit zwischen Features erkannt.",
        "technical_details": "Circular dependency detected in feature graph",
        "next_actions": [
            "Überprüfen Sie die Feature-Reihenfolge",
            "Entfernen Sie sich gegenseitig referenzierende Features",
            "Strukturieren Sie das Modell neu"
        ],
    },
    "rebuild_missing_input": {
        "category": ErrorCategory.DEPENDENCY,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Fehlendes Eingabe-Feature",
        "description": "Ein für die Berechnung benötigtes Feature fehlt oder ist unterdrückt.",
        "technical_details": "Missing input feature in dependency chain",
        "next_actions": [
            "Aktivieren Sie unterdrückte Features",
            "Stellen Sie gelöschte Features wieder her",
            "Überprüfen Sie die Feature-Abhängigkeiten"
        ],
    },
    
    # === Export Errors ===
    "export_failed": {
        "category": ErrorCategory.IMPORT_EXPORT,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Export fehlgeschlagen",
        "description": "Die Geometrie konnte nicht exportiert werden. Möglicherweise sind ungültige Solids vorhanden.",
        "technical_details": "Export operation failed - geometry validation error",
        "next_actions": [
            "Überprüfen Sie die Geometrie mit dem Validierungs-Werkzeug",
            "Stellen Sie sicher dass alle Bodies gültige Solids sind",
            "Reparieren Sie nicht-manifold Geometrie vor dem Export"
        ],
        "can_auto_fix": True,
        "auto_fix_action": "Geometrie validieren",
        "action_type": "validate_geometry",
    },
    "export_empty_scene": {
        "category": ErrorCategory.IMPORT_EXPORT,
        "severity": ErrorSeverity.WARNING,
        "title": "Leere Szene",
        "description": "Es gibt keine sichtbare Geometrie zum Exportieren.",
        "technical_details": "No visible geometry in scene for export",
        "next_actions": [
            "Erstellen Sie Geometrie bevor Sie exportieren",
            "Blenden Sie ausgeblendete Bodies ein",
            "Stellen Sie sicher dass mindestens ein Body sichtbar ist"
        ],
    },
    "export_invalid_mesh": {
        "category": ErrorCategory.IMPORT_EXPORT,
        "severity": ErrorSeverity.RECOVERABLE,
        "title": "Ungültiges Mesh",
        "description": "Das generierte Mesh enthält Fehler (z.B. nicht-dreieckige Faces, degenerierte Vertices).",
        "technical_details": "Mesh generation produced invalid triangles or degenerate vertices",
        "next_actions": [
            "Erhöhen Sie die Mesh-Auflösung",
            "Reparieren Sie die Quellgeometrie",
            "Verwenden Sie ein anderes Export-Format"
        ],
    },
    
    # === System Errors ===
    "system_memory": {
        "category": ErrorCategory.SYSTEM,
        "severity": ErrorSeverity.CRITICAL,
        "title": "Speicherfehler",
        "description": "Die Operation konnte wegen unzureichendem Speicher nicht abgeschlossen werden.",
        "technical_details": "Memory allocation failed",
        "next_actions": [
            "Schließen Sie andere Anwendungen",
            "Speichern Sie Ihr Projekt und starten Sie neu",
            "Reduzieren Sie die Komplexität des Modells",
            "Verwenden Sie ein System mit mehr RAM"
        ],
    },
    "system_unknown": {
        "category": ErrorCategory.SYSTEM,
        "severity": ErrorSeverity.CRITICAL,
        "title": "Unbekannter Fehler",
        "description": "Ein unerwarteter Fehler ist aufgetreten.",
        "technical_details": "Unexpected exception",
        "next_actions": [
            "Speichern Sie Ihr Projekt",
            "Starten Sie die Anwendung neu",
            "Kontaktieren Sie den Support mit der Fehlermeldung"
        ],
    },
}


# =============================================================================
# Error Diagnostics Engine
# =============================================================================

class ErrorDiagnostics:
    """
    Zentrale Fehler-Diagnostik Engine.
    
    Bietet:
    - Erklärungen für alle bekannten Error-Codes
    - Kontext-sensitive Next-Action Vorschläge
    - Auto-Fix Detection
    - Error-Logging mit strukturierten Details
    """
    
    # Registry für custom error handlers
    _custom_handlers: Dict[str, Callable] = {}
    
    @classmethod
    def explain(
        cls,
        error_code: str,
        context: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ) -> ErrorExplanation:
        """
        Erzeugt eine erklärte Fehlermeldung für den Nutzer.
        
        Args:
            error_code: Der Error-Code (z.B. "geometry_non_manifold")
            context: Zusätzlicher Kontext (Feature, Parameter, etc.)
            original_exception: Originale Exception falls vorhanden
            
        Returns:
            ErrorExplanation mit allen Details für die UI
        """
        context = context or {}
        
        # Suche in Knowledge Base
        kb_entry = ERROR_KNOWLEDGE_BASE.get(error_code)
        
        if kb_entry:
            # Parse action_type if present
            action_type = None
            if "action_type" in kb_entry:
                try:
                    action_type = ErrorActionType(kb_entry["action_type"])
                except ValueError:
                    pass
            
            explanation = ErrorExplanation(
                error_code=error_code,
                category=kb_entry["category"],
                severity=kb_entry["severity"],
                title=kb_entry["title"],
                description=kb_entry["description"],
                technical_details=kb_entry.get("technical_details", ""),
                next_actions=list(kb_entry.get("next_actions", [])),
                can_auto_fix=kb_entry.get("can_auto_fix", False),
                auto_fix_action=kb_entry.get("auto_fix_action", ""),
                action_type=action_type,
                context=context
            )
        else:
            # Unbekannter Fehler
            explanation = cls._create_unknown_explanation(
                error_code, context, original_exception
            )
        
        # Custom Handler falls registriert
        if error_code in cls._custom_handlers:
            explanation = cls._custom_handlers[error_code](explanation, context)
        
        # Kontext-spezifische Anpassungen
        explanation = cls._enrich_with_context(explanation, context)
        
        return explanation
    
    @classmethod
    def explain_result(
        cls,
        result: Any,  # OperationResult or similar
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[ErrorExplanation]:
        """
        Erzeugt Erklärung aus einem OperationResult.
        
        Args:
            result: OperationResult mit Error-Status
            context: Zusätzlicher Kontext
            
        Returns:
            ErrorExplanation oder None wenn kein Fehler
        """
        # Prüfe ob Result ein Error ist
        is_error = getattr(result, 'is_error', False)
        if not is_error:
            return None
        
        # Extrahiere Error-Code
        details = getattr(result, 'details', {})
        error_code = details.get('error_code', 'system_unknown')
        
        # Kontext erweitern
        full_context = {
            'result': result,
            'message': getattr(result, 'message', ''),
            **(context or {})
        }
        
        return cls.explain(error_code, full_context)
    
    @classmethod
    def register_custom_handler(
        cls,
        error_code: str,
        handler: Callable[[ErrorExplanation, Dict], ErrorExplanation]
    ):
        """
        Registriert einen Custom Handler für einen Error-Code.
        
        Args:
            error_code: Der zu handhabende Error-Code
            handler: Funktion(enplanation, context) -> explanation
        """
        cls._custom_handlers[error_code] = handler
        logger.debug(f"Registered custom error handler for {error_code}")
    
    @classmethod
    def can_auto_fix(cls, error_code: str) -> bool:
        """Prüft ob automatische Behebung verfügbar ist."""
        kb_entry = ERROR_KNOWLEDGE_BASE.get(error_code)
        return kb_entry.get("can_auto_fix", False) if kb_entry else False
    
    @classmethod
    def get_suggested_actions(cls, error_code: str) -> List[str]:
        """Gibt vorgeschlagene Aktionen für einen Error-Code zurück."""
        kb_entry = ERROR_KNOWLEDGE_BASE.get(error_code)
        return list(kb_entry.get("next_actions", [])) if kb_entry else []
    
    @classmethod
    def get_errors_by_category(cls, category: ErrorCategory) -> List[str]:
        """Gibt alle Error-Codes einer Kategorie zurück."""
        return [
            code for code, entry in ERROR_KNOWLEDGE_BASE.items()
            if entry["category"] == category
        ]
    
    @classmethod
    def search_errors(cls, query: str) -> List[Dict[str, str]]:
        """
        Durchsucht Error-Knowledge-Base.
        
        Args:
            query: Suchbegriff
            
        Returns:
            Liste von Matches mit code, title, description
        """
        query_lower = query.lower()
        matches = []
        
        for code, entry in ERROR_KNOWLEDGE_BASE.items():
            if (query_lower in code.lower() or
                query_lower in entry["title"].lower() or
                query_lower in entry["description"].lower()):
                matches.append({
                    "code": code,
                    "title": entry["title"],
                    "description": entry["description"][:100] + "..."
                })
        
        return matches
    
    @classmethod
    def _create_unknown_explanation(
        cls,
        error_code: str,
        context: Dict[str, Any],
        exception: Optional[Exception]
    ) -> ErrorExplanation:
        """Erzeugt Erklärung für unbekannten Fehler."""
        tech_details = f"Unknown error code: {error_code}"
        if exception:
            tech_details += f" | Exception: {type(exception).__name__}: {str(exception)}"
        
        return ErrorExplanation(
            error_code=error_code,
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.CRITICAL,
            title="Unbekannter Fehler",
            description=f"Ein unerwarteter Fehler ist aufgetreten (Code: {error_code}).",
            technical_details=tech_details,
            next_actions=[
                "Speichern Sie Ihr Projekt",
                "Notieren Sie die Schritte die zum Fehler geführt haben",
                "Kontaktieren Sie den Support"
            ],
            context=context
        )
    
    @classmethod
    def _enrich_with_context(
        cls,
        explanation: ErrorExplanation,
        context: Dict[str, Any]
    ) -> ErrorExplanation:
        """Reichert Erklärung mit kontext-spezifischen Details an."""
        # Feature-spezifische Anpassungen
        feature = context.get('feature')
        if feature:
            feature_name = getattr(feature, 'name', 'Unbekannt')
            feature_class = feature.__class__.__name__
            
            # Füge Feature-Info zu Kontext hinzu
            explanation.context['feature_name'] = feature_name
            explanation.context['feature_type'] = feature_class
            
            # Passe Next-Actions an
            if explanation.error_code == "reference_not_found":
                explanation.next_actions.insert(
                    0, f"Prüfen Sie das Feature '{feature_name}' auf veraltete Referenzen"
                )
        
        # Parameter-spezifische Anpassungen
        parameter = context.get('parameter')
        if parameter and explanation.error_code.startswith("parameter"):
            explanation.next_actions.append(
                f"Aktueller Wert: {parameter}. Überprüfen Sie die gültigen Grenzen."
            )
        
        return explanation


# =============================================================================
# Convenience Functions
# =============================================================================

def explain_error(
    error_code: str,
    context: Optional[Dict[str, Any]] = None
) -> ErrorExplanation:
    """Shortcut für ErrorDiagnostics.explain()."""
    return ErrorDiagnostics.explain(error_code, context)


def get_next_actions(error_code: str) -> List[str]:
    """Shortcut für ErrorDiagnostics.get_suggested_actions()."""
    return ErrorDiagnostics.get_suggested_actions(error_code)


def format_error_for_user(
    error_code: str,
    include_technical: bool = False
) -> str:
    """Formatiert Fehler direkt als User-String."""
    explanation = ErrorDiagnostics.explain(error_code)
    return explanation.to_user_message(include_technical)
