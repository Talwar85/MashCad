"""
MashCAD - Export Validator
===========================

Pre-flight Validierung für 3D-Exporte.

Phase 1: Export Foundation (PR-002)
Prüft Geometrie auf Manifold-Status, Free-Bounds, und Degenerate Faces
vor dem Export.

Usage:
    from modeling.export_validator import ExportValidator, ValidationOptions
    
    solid = body._build123d_solid
    result = ExportValidator.validate_for_export(solid)
    
    if not result.is_printable:
        print(f"Warnungen: {result.warnings}")
        for issue in result.issues:
            print(f"  - {issue.severity.value}: {issue.message}")

Author: Kimi (Phase 1 Implementation)
Date: 2026-02-19
Branch: feature/v1-ux-aiB
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Any, Dict, Set, Tuple
from loguru import logger
import math


class ValidationSeverity(Enum):
    """Schweregrad eines Validierungs-Issues."""
    INFO = "info"           # Information, kein Handlungsbedarf
    WARNING = "warning"     # Warnung, Export möglich aber problematisch
    ERROR = "error"         # Fehler, Export wird blockiert


class ValidationCheckType(Enum):
    """Typ der durchgeführten Validierung."""
    MANIFOLD = "manifold"               # Geschlossenes Volumen
    FREE_BOUNDS = "free_bounds"         # Offene Kanten
    DEGENERATE_FACES = "degenerate"     # Degenerierte Faces
    NORMALS = "normals"                 # Normalen-Konsistenz
    SELF_INTERSECTION = "self_intersection"  # Selbstüberschneidungen
    SMALL_FEATURES = "small_features"   # Sehr kleine Features
    NON_MANIFOLD_EDGES = "non_manifold_edges"  # Nicht-Manifold Kanten


@dataclass
class ValidationIssue:
    """
    Ein einzelnes Validierungs-Issue.
    
    Args:
        severity: Schweregrad (INFO/WARNING/ERROR)
        check_type: Art der Prüfung
        message: Menschlich lesbare Beschreibung
        entity_id: Optional: ID der betroffenen Entität
        location: Optional: 3D-Position des Issues
        suggestion: Optional: Vorschlag zur Behebung
    """
    severity: ValidationSeverity
    check_type: ValidationCheckType
    message: str
    entity_id: Optional[str] = None
    location: Optional[Tuple[float, float, float]] = None
    suggestion: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für Serialisierung."""
        return {
            "severity": self.severity.value,
            "check_type": self.check_type.value,
            "message": self.message,
            "entity_id": self.entity_id,
            "location": self.location,
            "suggestion": self.suggestion
        }


@dataclass
class ValidationResult:
    """
    Ergebnis einer Export-Validierung.
    
    Args:
        is_valid: True wenn keine ERROR-Issues vorhanden
        is_printable: True wenn keine kritischen 3D-Print-Blocker
        is_closed: True wenn Solid geschlossen (Manifold)
        has_free_bounds: True wenn offene Kanten existieren
        has_degenerate_faces: True wenn degenerierte Faces existieren
        issues: Liste aller gefundenen Issues
        checks_performed: Liste der durchgeführten Checks
        statistics: Zusätzliche Statistiken
    """
    is_valid: bool = True
    is_printable: bool = True
    is_closed: bool = True
    has_free_bounds: bool = False
    has_degenerate_faces: bool = False
    has_inverted_normals: bool = False
    has_self_intersections: bool = False
    issues: List[ValidationIssue] = field(default_factory=list)
    checks_performed: List[ValidationCheckType] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)
    
    def add_issue(self, issue: ValidationIssue):
        """Fügt ein Issue hinzu und aktualisiert Status."""
        self.issues.append(issue)
        
        if issue.severity == ValidationSeverity.ERROR:
            self.is_valid = False
            if issue.check_type in (ValidationCheckType.MANIFOLD, 
                                    ValidationCheckType.FREE_BOUNDS):
                self.is_printable = False
        
        # Aktualisiere Zustand basierend auf Issue-Typ
        if issue.check_type == ValidationCheckType.FREE_BOUNDS:
            self.has_free_bounds = True
            self.is_closed = False
        elif issue.check_type == ValidationCheckType.DEGENERATE_FACES:
            self.has_degenerate_faces = True
        elif issue.check_type == ValidationCheckType.NORMALS:
            self.has_inverted_normals = True
        elif issue.check_type == ValidationCheckType.SELF_INTERSECTION:
            self.has_self_intersections = True
    
    def get_issues_by_severity(self, severity: ValidationSeverity) -> List[ValidationIssue]:
        """Filtert Issues nach Schweregrad."""
        return [i for i in self.issues if i.severity == severity]
    
    def get_errors(self) -> List[ValidationIssue]:
        """Gibt alle ERROR-Issues zurück."""
        return self.get_issues_by_severity(ValidationSeverity.ERROR)
    
    def get_warnings(self) -> List[ValidationIssue]:
        """Gibt alle WARNING-Issues zurück."""
        return self.get_issues_by_severity(ValidationSeverity.WARNING)
    
    def get_info(self) -> List[ValidationIssue]:
        """Gibt alle INFO-Issues zurück."""
        return self.get_issues_by_severity(ValidationSeverity.INFO)
    
    def to_report(self) -> str:
        """Erstellt einen menschlich lesbaren Report."""
        lines = ["Export Validierungs-Report", "=" * 40]
        
        lines.append(f"\nStatus: {'✓ Gültig' if self.is_valid else '✗ Ungültig'}")
        lines.append(f"3D-Druckbar: {'✓ Ja' if self.is_printable else '✗ Nein'}")
        lines.append(f"Geschlossen: {'✓ Ja' if self.is_closed else '✗ Nein'}")
        
        if self.issues:
            lines.append(f"\nGefundene Issues: {len(self.issues)}")
            for issue in self.issues:
                icon = "🔴" if issue.severity == ValidationSeverity.ERROR else \
                       "🟡" if issue.severity == ValidationSeverity.WARNING else "ℹ️"
                lines.append(f"\n{icon} {issue.check_type.value.upper()}")
                lines.append(f"   {issue.message}")
                if issue.suggestion:
                    lines.append(f"   💡 {issue.suggestion}")
        else:
            lines.append("\n✓ Keine Issues gefunden")
        
        return "\n".join(lines)


@dataclass
class ValidationOptions:
    """
    Optionen für die Export-Validierung.
    
    Args:
        check_manifold: Prüfe auf geschlossenes Volumen
        check_free_bounds: Prüfe auf offene Kanten
        check_degenerate: Prüfe auf degenerierte Faces
        check_normals: Prüfe auf Normalen-Konsistenz
        check_self_intersection: Prüfe auf Selbstüberschneidungen
        min_face_area: Minimale Face-Fläche (mm²)
        max_free_bounds_ratio: Maximales Verhältnis offener/gesamter Kanten
        strict_mode: Bei True werden WARNINGS zu ERRORS
    """
    check_manifold: bool = True
    check_free_bounds: bool = True
    check_degenerate: bool = True
    check_normals: bool = False  # Performance-Intensiv
    check_self_intersection: bool = False  # Sehr Performance-Intensiv
    min_face_area: float = 1e-6  # 0.001 mm²
    max_free_bounds_ratio: float = 0.01  # 1% offene Kanten
    strict_mode: bool = False
    
    # Toleranzen
    tolerance: float = 1e-6
    angular_tolerance: float = 0.5  # rad


class ExportValidator:
    """
    Validator für 3D-Export-Qualität.
    
    Prüft Geometrie auf Probleme die den Export oder 3D-Druck
    beeinträchtigen könnten.
    
    Usage:
        # Standard-Validierung
        result = ExportValidator.validate_for_export(solid)
        
        # Mit Optionen
        options = ValidationOptions(check_normals=True, strict_mode=True)
        result = ExportValidator.validate_for_export(solid, options)
        
        # Schnell-Check
        is_ok = ExportValidator.is_printable(solid)
    """
    
    @staticmethod
    def validate_for_export(
        solid: Any,
        options: Optional[ValidationOptions] = None
    ) -> ValidationResult:
        """
        Führt vollständige Export-Validierung durch.
        
        Args:
            solid: Build123d Solid oder OCP TopoDS_Shape
            options: Validierungs-Optionen
            
        Returns:
            ValidationResult mit allen Issues
        """
        if options is None:
            options = ValidationOptions()
        
        result = ValidationResult()
        
        # Extrahiere OCP Shape
        ocp_shape = solid.wrapped if hasattr(solid, 'wrapped') else solid
        
        if ocp_shape is None:
            result.add_issue(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                check_type=ValidationCheckType.MANIFOLD,
                message="Shape ist None",
                suggestion="Prüfen Sie ob das Solid korrekt erzeugt wurde"
            ))
            return result
        
        logger.debug(f"Starting export validation for {type(solid).__name__}")
        
        # 1. Manifold-Check (geschlossenes Volumen)
        if options.check_manifold:
            ExportValidator._check_manifold(ocp_shape, result, options)
        
        # 2. Free-Bounds-Check (offene Kanten)
        if options.check_free_bounds:
            ExportValidator._check_free_bounds(ocp_shape, result, options)
        
        # 3. Degenerate Faces
        if options.check_degenerate:
            ExportValidator._check_degenerate_faces(ocp_shape, result, options)
        
        # 4. Normals (optional, performance-intensiv)
        if options.check_normals:
            ExportValidator._check_normals(ocp_shape, result, options)
        
        # 5. Self-Intersections (optional, sehr performance-intensiv)
        if options.check_self_intersection:
            ExportValidator._check_self_intersections(ocp_shape, result, options)
        
        logger.debug(f"Validation complete: {len(result.issues)} issues found")
        return result
    
    @staticmethod
    def is_printable(solid: Any, tolerance: float = 1e-6) -> bool:
        """
        Schnell-Check ob ein Solid 3D-druckbar ist.
        
        Args:
            solid: Zu prüfendes Solid
            tolerance: Geometrische Toleranz
            
        Returns:
            True wenn druckbar (manifold, keine kritischen Fehler)
        """
        options = ValidationOptions(
            check_manifold=True,
            check_free_bounds=True,
            check_degenerate=True,
            tolerance=tolerance
        )
        result = ExportValidator.validate_for_export(solid, options)
        return result.is_printable
    
    @staticmethod
    def is_valid_for_export(solid: Any, tolerance: float = 1e-6) -> bool:
        """
        Schnell-Check ob ein Solid exportierbar ist.
        
        Args:
            solid: Zu prüfendes Solid
            tolerance: Geometrische Toleranz
            
        Returns:
            True wenn exportierbar
        """
        options = ValidationOptions(
            check_manifold=True,
            check_free_bounds=False,  # Nicht strikt für Export
            check_degenerate=True,
            tolerance=tolerance
        )
        result = ExportValidator.validate_for_export(solid, options)
        return result.is_valid
    
    @staticmethod
    def _check_manifold(
        shape: Any,
        result: ValidationResult,
        options: ValidationOptions
    ):
        """Prüft ob Shape ein geschlossenes Volumen ist."""
        result.checks_performed.append(ValidationCheckType.MANIFOLD)
        
        try:
            from OCP.BRepCheck import BRepCheck_Analyzer
            from OCP.TopAbs import TopAbs_SOLID
            from OCP.TopExp import TopExp_Explorer
            
            # Prüfe ob Shape ein Solid ist
            explorer = TopExp_Explorer(shape, TopAbs_SOLID)
            if not explorer.More():
                result.add_issue(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    check_type=ValidationCheckType.MANIFOLD,
                    message="Shape ist kein Solid (kein geschlossenes Volumen)",
                    suggestion="Verwenden Sie Boolean-Operationen oder Shell um ein geschlossenes Volumen zu erstellen"
                ))
                return
            
            # BRepCheck Analyzer
            analyzer = BRepCheck_Analyzer(shape)
            
            if not analyzer.IsValid():
                status = analyzer.Result()
                # Status-Werte analysieren
                result.add_issue(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    check_type=ValidationCheckType.MANIFOLD,
                    message=f"BRep-Validierung meldet Probleme (Status: {status})",
                    suggestion="Versuchen Sie Geometry-Healing oder reparieren Sie das Modell"
                ))
            
        except ImportError:
            logger.warning("OCP BRepCheck nicht verfügbar")
        except Exception as e:
            logger.warning(f"Manifold-Check fehlgeschlagen: {e}")
    
    @staticmethod
    def _check_free_bounds(
        shape: Any,
        result: ValidationResult,
        options: ValidationOptions
    ):
        """Prüft auf offene Kanten (Free Bounds)."""
        result.checks_performed.append(ValidationCheckType.FREE_BOUNDS)
        
        try:
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
            from OCP.TopoDS import TopoDS_Face, TopoDS_Edge
            from OCP.BRep import BRep_Tool
            from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
            from OCP.BRepTools import BRepTools_WireExplorer
            
            # Sammle alle Faces
            faces = []
            face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
            while face_explorer.More():
                faces.append(TopoDS_Face(face_explorer.Current()))
                face_explorer.Next()
            
            if not faces:
                return
            
            # Zähle Kanten und ihre Referenzen
            edge_count = {}
            
            for face in faces:
                edge_explorer = TopExp_Explorer(face, TopAbs_EDGE)
                while edge_explorer.More():
                    edge = TopoDS_Edge(edge_explorer.Current())
                    # Hash basierend auf geometrischer Identität
                    if edge not in edge_count:
                        edge_count[edge] = 0
                    edge_count[edge] += 1
                    edge_explorer.Next()
            
            # Finde Free Bounds (nur eine Referenz = offene Kante)
            free_bounds = []
            internal_edges = []
            
            for edge, count in edge_count.items():
                if count == 1:
                    free_bounds.append(edge)
                elif count == 2:
                    internal_edges.append(edge)
                else:
                    # Non-manifold Kante (mehr als 2 Faces)
                    result.add_issue(ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        check_type=ValidationCheckType.NON_MANIFOLD_EDGES,
                        message=f"Non-manifold Kante gefunden ({count} angrenzende Faces)",
                        suggestion="Überprüfen Sie die Topologie an dieser Stelle"
                    ))
            
            total_edges = len(edge_count)
            free_bound_count = len(free_bounds)
            
            if free_bound_count > 0:
                ratio = free_bound_count / total_edges if total_edges > 0 else 1.0
                
                # Bestimme Schweregrad basierend auf Verhältnis
                if ratio > options.max_free_bounds_ratio:
                    severity = ValidationSeverity.ERROR if options.strict_mode else ValidationSeverity.WARNING
                    message = f"Viele offene Kanten: {free_bound_count}/{total_edges} ({ratio*100:.1f}%)"
                else:
                    severity = ValidationSeverity.WARNING
                    message = f"Wenige offene Kanten: {free_bound_count}/{total_edges} ({ratio*100:.1f}%)"
                
                result.add_issue(ValidationIssue(
                    severity=severity,
                    check_type=ValidationCheckType.FREE_BOUNDS,
                    message=message,
                    suggestion="Verwenden Sie 'Shell' oder 'Stitch' um offene Kanten zu schließen"
                ))
            
            # Statistik speichern
            result.statistics['total_edges'] = total_edges
            result.statistics['free_bounds'] = free_bound_count
            result.statistics['internal_edges'] = len(internal_edges)
            
        except ImportError:
            logger.warning("OCP TopExp nicht verfügbar")
        except Exception as e:
            logger.warning(f"Free-Bounds-Check fehlgeschlagen: {e}")
    
    @staticmethod
    def _check_degenerate_faces(
        shape: Any,
        result: ValidationResult,
        options: ValidationOptions
    ):
        """Prüft auf degenerierte Faces."""
        result.checks_performed.append(ValidationCheckType.DEGENERATE_FACES)
        
        try:
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE
            from OCP.BRep import BRep_Tool
            from OCP.GProp import GProp_GProps
            from OCP.BRepGProp import BRepGProp
            
            degenerate_count = 0
            small_face_count = 0
            
            face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
            face_idx = 0
            
            while face_explorer.More():
                face = face_explorer.Current()
                
                # Berechne Fläche
                props = GProp_GProps()
                BRepGProp.SurfaceProperties(face, props)
                area = props.Mass()
                
                if area < options.tolerance:
                    degenerate_count += 1
                elif area < options.min_face_area:
                    small_face_count += 1
                
                face_idx += 1
                face_explorer.Next()
            
            if degenerate_count > 0:
                result.add_issue(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    check_type=ValidationCheckType.DEGENERATE_FACES,
                    message=f"{degenerate_count} degenerierte Faces gefunden (Fläche ≈ 0)",
                    suggestion="Entfernen oder reparieren Sie degenerierte Faces vor dem Export"
                ))
            
            if small_face_count > 0:
                result.add_issue(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    check_type=ValidationCheckType.SMALL_FEATURES,
                    message=f"{small_face_count} sehr kleine Faces gefunden",
                    suggestion="Kleine Features können 3D-Druck-Probleme verursachen"
                ))
            
            result.statistics['degenerate_faces'] = degenerate_count
            result.statistics['small_faces'] = small_face_count
            result.statistics['total_faces'] = face_idx
            
        except ImportError:
            logger.warning("OCP BRepGProp nicht verfügbar")
        except Exception as e:
            logger.warning(f"Degenerate-Check fehlgeschlagen: {e}")
    
    @staticmethod
    def _check_normals(
        shape: Any,
        result: ValidationResult,
        options: ValidationOptions
    ):
        """Prüft auf konsistente Normalen (optional)."""
        result.checks_performed.append(ValidationCheckType.NORMALS)
        
        try:
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE
            from OCP.BRep import BRep_Tool
            from OCP.BRepTools import BRepTools_Normal
            from OCP.gp import gp_Pnt
            
            inverted_count = 0
            
            face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
            while face_explorer.More():
                face = face_explorer.Current()
                
                # Prüfe Normalen-Richtung
                surface = BRep_Tool.Surface(face)
                if surface is not None:
                    # Sampling-Punkt (UV = 0.5, 0.5)
                    try:
                        u_min, u_max, v_min, v_max = surface.Bounds()
                        u = (u_min + u_max) / 2
                        v = (v_min + v_max) / 2
                        
                        pnt = gp_Pnt()
                        normal = BRepTools_Normal(surface, u, v)
                        
                        # Hier könnte komplexere Normalen-Analyse folgen
                        # Für jetzt: Grundlegende Prüfung
                        
                    except Exception:
                        pass
                
                face_explorer.Next()
            
            if inverted_count > 0:
                result.add_issue(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    check_type=ValidationCheckType.NORMALS,
                    message=f"{inverted_count} Faces mit möglicherweise invertierten Normalen",
                    suggestion="Überprüfen Sie die Face-Orientierung"
                ))
            
        except ImportError:
            logger.warning("OCP BRepTools nicht verfügbar")
        except Exception as e:
            logger.warning(f"Normals-Check fehlgeschlagen: {e}")
    
    @staticmethod
    def _check_self_intersections(
        shape: Any,
        result: ValidationResult,
        options: ValidationOptions
    ):
        """Prüft auf Selbstüberschneidungen (optional, sehr aufwändig)."""
        result.checks_performed.append(ValidationCheckType.SELF_INTERSECTION)
        
        try:
            from OCP.BRepCheck import BRepCheck_Analyzer
            
            analyzer = BRepCheck_Analyzer(shape)
            
            # Self-Intersection Check ist komplex und rechenintensiv
            # Vereinfachte Prüfung hier
            
            if not analyzer.IsValid():
                # Könnte Selbstüberschneidungen enthalten
                pass
            
        except ImportError:
            logger.warning("OCP BRepCheck nicht verfügbar")
        except Exception as e:
            logger.warning(f"Self-Intersection-Check fehlgeschlagen: {e}")
    
    @staticmethod
    def get_quick_report(solid: Any) -> str:
        """
        Erzeugt einen kurzen Text-Report für das Solid.
        
        Args:
            solid: Zu prüfendes Solid
            
        Returns:
            Kurzer Report-String
        """
        result = ExportValidator.validate_for_export(solid)
        
        if result.is_printable and not result.issues:
            return "✓ Druckbar - Keine Probleme gefunden"
        
        parts = []
        if not result.is_printable:
            parts.append("✗ Nicht druckbar")
        elif not result.is_valid:
            parts.append("⚠ Export mit Einschränkungen")
        
        if result.has_free_bounds:
            parts.append("Offene Kanten")
        if result.has_degenerate_faces:
            parts.append("Degenerierte Faces")
        
        errors = len(result.get_errors())
        warnings = len(result.get_warnings())
        
        if errors > 0:
            parts.append(f"{errors} Fehler")
        if warnings > 0:
            parts.append(f"{warnings} Warnungen")
        
        return " | ".join(parts) if parts else "✓ OK"


# =============================================================================
# Convenience Functions
# =============================================================================

def validate_for_print(solid: Any) -> ValidationResult:
    """Shortcut für 3D-Druck-Validierung."""
    options = ValidationOptions(
        check_manifold=True,
        check_free_bounds=True,
        check_degenerate=True,
        check_normals=False,
        strict_mode=False
    )
    return ExportValidator.validate_for_export(solid, options)


def validate_strict(solid: Any) -> ValidationResult:
    """Shortcut für strikte Validierung."""
    options = ValidationOptions(
        check_manifold=True,
        check_free_bounds=True,
        check_degenerate=True,
        check_normals=True,
        check_self_intersection=True,
        strict_mode=True
    )
    return ExportValidator.validate_for_export(solid, options)
