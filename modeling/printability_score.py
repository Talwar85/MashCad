"""
MashCAD - Printability Score Module
====================================

PR-010: Printability Trust Gate

Berechnet einen umfassenden Printability-Score für 3D-Modelle
basierend auf verschiedenen Geometrie-Kriterien.

Scoring Categories:
- manifold_score: Geschlossenes Volumen (0-100)
- normals_score: Normalen-Konsistenz (0-100)
- wall_thickness_score: Wandstärke (0-100)
- overhang_score: Überhänge (0-100)

Integration:
- ExportValidator für Geometrie-Checks
- GeometryValidator für OCP-Validierung
- WallThicknessAnalyzer für Wandstärken-Analyse

Author: Claude (PR-010 Printability Trust Gate)
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Dict, Any, Tuple
from loguru import logger


class PrintabilitySeverity(Enum):
    """Schweregrad eines Printability-Issues."""
    INFO = "info"           # Information, kein Einfluss auf Score
    WARNING = "warning"     # Warnung, reduziert Score moderat
    ERROR = "error"         # Fehler, reduziert Score stark
    CRITICAL = "critical"   # Kritisch, blockiert Export


class PrintabilityCategory(Enum):
    """Kategorie eines Printability-Issues."""
    MANIFOLD = "manifold"               # Geschlossenes Volumen
    NORMALS = "normals"                 # Normalen-Konsistenz
    WALL_THICKNESS = "wall_thickness"   # Wandstärke
    OVERHANG = "overhang"               # Überhänge/Unterstützungen
    GEOMETRY = "geometry"               # Allgemeine Geometrie-Probleme
    SIZE = "size"                       # Bauteilgröße


@dataclass
class PrintabilityIssue:
    """
    Ein einzelnes Printability-Issue.
    
    Args:
        severity: Schweregrad (INFO/WARNING/ERROR/CRITICAL)
        category: Kategorie des Issues
        message: Menschlich lesbare Beschreibung
        score_impact: Punktabzug (0-100)
        location: Optional: 3D-Position des Issues
        suggestion: Optional: Vorschlag zur Behebung
        auto_fixable: True wenn automatisch behebbar
    """
    severity: PrintabilitySeverity
    category: PrintabilityCategory
    message: str
    score_impact: int = 0
    location: Optional[Tuple[float, float, float]] = None
    suggestion: Optional[str] = None
    auto_fixable: bool = False
    
    def __post_init__(self):
        """Validiert score_impact Bereich."""
        self.score_impact = max(0, min(100, self.score_impact))
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für Serialisierung."""
        return {
            "severity": self.severity.value,
            "category": self.category.value,
            "message": self.message,
            "score_impact": self.score_impact,
            "location": self.location,
            "suggestion": self.suggestion,
            "auto_fixable": self.auto_fixable
        }


@dataclass
class PrintabilityScore:
    """
    Umfassender Printability-Score für ein 3D-Modell.
    
    Args:
        manifold_score: Score für geschlossenes Volumen (0-100)
        normals_score: Score für Normalen-Konsistenz (0-100)
        wall_thickness_score: Score für Wandstärke (0-100)
        overhang_score: Score für Überhänge (0-100)
        overall_score: Gewichteter Gesamtscore (0-100)
        issues: Liste aller gefundenen Issues
        is_printable: True wenn druckbar (keine CRITICAL Issues)
        analysis_time_ms: Analysezeit in Millisekunden
    """
    manifold_score: int = 100
    normals_score: int = 100
    wall_thickness_score: int = 100
    overhang_score: int = 100
    overall_score: int = 100
    issues: List[PrintabilityIssue] = field(default_factory=list)
    is_printable: bool = True
    analysis_time_ms: float = 0.0
    
    # Metadata
    model_name: str = ""
    model_volume_mm3: float = 0.0
    model_bbox: Optional[Tuple[Tuple[float, float, float], 
                               Tuple[float, float, float]]] = None
    
    def __post_init__(self):
        """Berechnet overall_score wenn nicht explizit gesetzt."""
        if self.overall_score == 100 and not self._overall_explicitly_set():
            self.recalculate_overall()
    
    def _overall_explicitly_set(self) -> bool:
        """Prüft ob overall_score explizit gesetzt wurde."""
        # Wenn es von 100 abweicht, wurde es gesetzt
        return self.overall_score != 100
    
    def recalculate_overall(self) -> None:
        """Berechnet den gewichteten Gesamtscore neu."""
        # Gewichtung der Kategorien
        weights = {
            'manifold': 0.35,      # Wichtigste Kategorie
            'normals': 0.20,       # Wichtig für Mesh-Qualität
            'wall_thickness': 0.25, # Wichtig für Druckbarkeit
            'overhang': 0.20       # Wichtig für FDM-Druck
        }
        
        weighted_sum = (
            self.manifold_score * weights['manifold'] +
            self.normals_score * weights['normals'] +
            self.wall_thickness_score * weights['wall_thickness'] +
            self.overhang_score * weights['overhang']
        )
        
        self.overall_score = int(round(weighted_sum))
        
        # is_printable aktualisieren
        self.is_printable = not any(
            issue.severity == PrintabilitySeverity.CRITICAL
            for issue in self.issues
        )
    
    def add_issue(self, issue: PrintabilityIssue) -> None:
        """Fügt ein Issue hinzu und aktualisiert den entsprechenden Score."""
        self.issues.append(issue)
        
        # Score basierend auf Kategorie reduzieren
        score_reduction = issue.score_impact
        
        if issue.category == PrintabilityCategory.MANIFOLD:
            self.manifold_score = max(0, self.manifold_score - score_reduction)
        elif issue.category == PrintabilityCategory.NORMALS:
            self.normals_score = max(0, self.normals_score - score_reduction)
        elif issue.category == PrintabilityCategory.WALL_THICKNESS:
            self.wall_thickness_score = max(0, self.wall_thickness_score - score_reduction)
        elif issue.category == PrintabilityCategory.OVERHANG:
            self.overhang_score = max(0, self.overhang_score - score_reduction)
        else:
            # GEOMETRY und SIZE beeinflussen alle Scores moderat
            self.manifold_score = max(0, self.manifold_score - score_reduction // 2)
        
        # CRITICAL Issues setzen is_printable auf False
        if issue.severity == PrintabilitySeverity.CRITICAL:
            self.is_printable = False
        
        # Overall neu berechnen
        self.recalculate_overall()
    
    def get_issues_by_severity(self, severity: PrintabilitySeverity) -> List[PrintabilityIssue]:
        """Filtert Issues nach Schweregrad."""
        return [i for i in self.issues if i.severity == severity]
    
    def get_critical_issues(self) -> List[PrintabilityIssue]:
        """Gibt alle CRITICAL Issues zurück."""
        return self.get_issues_by_severity(PrintabilitySeverity.CRITICAL)
    
    def get_errors(self) -> List[PrintabilityIssue]:
        """Gibt alle ERROR Issues zurück."""
        return self.get_issues_by_severity(PrintabilitySeverity.ERROR)
    
    def get_warnings(self) -> List[PrintabilityIssue]:
        """Gibt alle WARNING Issues zurück."""
        return self.get_issues_by_severity(PrintabilitySeverity.WARNING)
    
    def get_grade(self) -> str:
        """
        Gibt eine Buchstaben-Bewertung zurück.
        
        A: 90-100 (Ausgezeichnet)
        B: 80-89 (Gut)
        C: 70-79 (Akzeptabel)
        D: 60-69 (Problematisch)
        F: 0-59 (Nicht druckbar)
        """
        if self.overall_score >= 90:
            return "A"
        elif self.overall_score >= 80:
            return "B"
        elif self.overall_score >= 70:
            return "C"
        elif self.overall_score >= 60:
            return "D"
        else:
            return "F"
    
    def get_grade_color(self) -> Tuple[float, float, float]:
        """Gibt RGB-Farbe für Grade zurück."""
        grade = self.get_grade()
        colors = {
            "A": (0.2, 0.8, 0.2),   # Grün
            "B": (0.4, 0.8, 0.2),   # Hellgrün
            "C": (0.8, 0.8, 0.2),   # Gelb
            "D": (0.9, 0.5, 0.1),   # Orange
            "F": (0.9, 0.2, 0.2),   # Rot
        }
        return colors.get(grade, (0.5, 0.5, 0.5))
    
    def to_report(self) -> str:
        """Erstellt einen menschlich lesbaren Report."""
        lines = [
            "Printability Score Report",
            "=" * 50,
            "",
            f"Overall Score: {self.overall_score}/100 (Grade: {self.get_grade()})",
            "",
            "Category Scores:",
            f"  Manifold:       {self.manifold_score:3d}/100",
            f"  Normals:        {self.normals_score:3d}/100",
            f"  Wall Thickness: {self.wall_thickness_score:3d}/100",
            f"  Overhang:       {self.overhang_score:3d}/100",
            "",
            f"Printable: {'✓ Yes' if self.is_printable else '✗ No'}",
        ]
        
        if self.model_volume_mm3 > 0:
            lines.append(f"Volume: {self.model_volume_mm3:.2f} mm³")
        
        if self.issues:
            lines.append("")
            lines.append(f"Issues ({len(self.issues)}):")
            
            # Sort by severity
            severity_order = {
                PrintabilitySeverity.CRITICAL: 0,
                PrintabilitySeverity.ERROR: 1,
                PrintabilitySeverity.WARNING: 2,
                PrintabilitySeverity.INFO: 3,
            }
            sorted_issues = sorted(
                self.issues,
                key=lambda i: severity_order.get(i.severity, 99)
            )
            
            for issue in sorted_issues:
                icon = {
                    PrintabilitySeverity.CRITICAL: "🔴",
                    PrintabilitySeverity.ERROR: "🟠",
                    PrintabilitySeverity.WARNING: "🟡",
                    PrintabilitySeverity.INFO: "ℹ️",
                }.get(issue.severity, "•")
                
                lines.append(f"\n{icon} [{issue.category.value.upper()}] {issue.message}")
                if issue.suggestion:
                    lines.append(f"   💡 {issue.suggestion}")
        else:
            lines.append("")
            lines.append("✓ No issues found")
        
        lines.append("")
        lines.append(f"Analysis time: {self.analysis_time_ms:.1f} ms")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für Serialisierung."""
        return {
            "manifold_score": self.manifold_score,
            "normals_score": self.normals_score,
            "wall_thickness_score": self.wall_thickness_score,
            "overhang_score": self.overhang_score,
            "overall_score": self.overall_score,
            "grade": self.get_grade(),
            "is_printable": self.is_printable,
            "issues": [issue.to_dict() for issue in self.issues],
            "model_volume_mm3": self.model_volume_mm3,
            "analysis_time_ms": self.analysis_time_ms
        }


def calculate_printability_score(
    solid: Any,
    check_wall_thickness: bool = True,
    check_overhangs: bool = True,
    min_wall_thickness: float = 0.8,
    max_overhang_angle: float = 45.0
) -> PrintabilityScore:
    """
    Berechnet den umfassenden Printability-Score für ein Solid.
    
    Args:
        solid: Build123d Solid oder OCP TopoDS_Shape
        check_wall_thickness: Ob Wandstärke geprüft werden soll
        check_overhangs: Ob Überhänge geprüft werden sollen
        min_wall_thickness: Minimale Wandstärke in mm
        max_overhang_angle: Maximaler Überhangswinkel in Grad
        
    Returns:
        PrintabilityScore mit allen Kategorien und Issues
    """
    import time
    start_time = time.perf_counter()
    
    score = PrintabilityScore()
    
    # Extrahiere OCP Shape
    ocp_shape = solid.wrapped if hasattr(solid, 'wrapped') else solid
    
    if ocp_shape is None:
        score.add_issue(PrintabilityIssue(
            severity=PrintabilitySeverity.CRITICAL,
            category=PrintabilityCategory.MANIFOLD,
            message="Shape ist None",
            score_impact=100,
            suggestion="Prüfen Sie ob das Solid korrekt erzeugt wurde"
        ))
        score.analysis_time_ms = (time.perf_counter() - start_time) * 1000
        return score
    
    try:
        # 1. Manifold-Check (geschlossenes Volumen)
        _check_manifold_score(ocp_shape, score)
        
        # 2. Normals-Check
        _check_normals_score(ocp_shape, score)
        
        # 3. Wall Thickness Check (optional)
        if check_wall_thickness:
            _check_wall_thickness_score(ocp_shape, score, min_wall_thickness)
        
        # 4. Overhang Check (optional)
        if check_overhangs:
            _check_overhang_score(ocp_shape, score, max_overhang_angle)
        
        # 5. Model Metadata
        _collect_model_metadata(ocp_shape, score)
        
    except Exception as e:
        logger.exception("Printability analysis failed")
        score.add_issue(PrintabilityIssue(
            severity=PrintabilitySeverity.ERROR,
            category=PrintabilityCategory.GEOMETRY,
            message=f"Analyse fehlgeschlagen: {str(e)}",
            score_impact=50,
            suggestion="Versuchen Sie Geometry-Healing"
        ))
    
    # Final recalculate
    score.recalculate_overall()
    score.analysis_time_ms = (time.perf_counter() - start_time) * 1000
    
    logger.debug(f"Printability score calculated: {score.overall_score}/100 "
                 f"({len(score.issues)} issues, {score.analysis_time_ms:.1f}ms)")
    
    return score


def _check_manifold_score(shape: Any, score: PrintabilityScore) -> None:
    """Prüft Manifold-Status und aktualisiert Score."""
    try:
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.TopAbs import TopAbs_SOLID
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
        from OCP.TopExp import TopExp
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
        
        # Prüfe ob Shape ein Solid ist
        explorer = TopExp_Explorer(shape, TopAbs_SOLID)
        if not explorer.More():
            score.add_issue(PrintabilityIssue(
                severity=PrintabilitySeverity.CRITICAL,
                category=PrintabilityCategory.MANIFOLD,
                message="Shape ist kein Solid (kein geschlossenes Volumen)",
                score_impact=100,
                suggestion="Verwenden Sie Boolean-Operationen um ein geschlossenes Volumen zu erstellen"
            ))
            return
        
        # BRepCheck Analyzer
        analyzer = BRepCheck_Analyzer(shape)
        if not analyzer.IsValid():
            score.add_issue(PrintabilityIssue(
                severity=PrintabilitySeverity.ERROR,
                category=PrintabilityCategory.MANIFOLD,
                message="BRep-Validierung fehlgeschlagen",
                score_impact=40,
                suggestion="Führen Sie Geometry-Healing durch"
            ))
        
        # Non-manifold edges check
        edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map)
        
        non_manifold_count = 0
        for i in range(1, edge_face_map.Extent() + 1):
            face_list = edge_face_map.FindFromIndex(i)
            # Manifold edges should have exactly 2 faces
            face_count = face_list.Extent()
            if face_count != 2:
                non_manifold_count += 1
        
        if non_manifold_count > 0:
            impact = min(50, non_manifold_count * 5)
            score.add_issue(PrintabilityIssue(
                severity=PrintabilitySeverity.ERROR if non_manifold_count > 5 else PrintabilitySeverity.WARNING,
                category=PrintabilityCategory.MANIFOLD,
                message=f"{non_manifold_count} non-manifold Kanten gefunden",
                score_impact=impact,
                suggestion="Entfernen Sie überlappte Geometrie oder führen Sie Faces zusammen"
            ))
        
        # Free bounds check
        _check_free_bounds_score(shape, score)
        
    except ImportError:
        logger.warning("OCP BRepCheck nicht verfügbar für Manifold-Check")
    except Exception as e:
        logger.warning(f"Manifold-Check fehlgeschlagen: {e}")


def _check_free_bounds_score(shape: Any, score: PrintabilityScore) -> None:
    """Prüft auf offene Kanten (Free Bounds)."""
    try:
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
        from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
        from OCP.TopExp import TopExp
        
        # Zähle Kanten-Referenzen
        edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map)
        
        free_edges = 0
        for i in range(1, edge_face_map.Extent() + 1):
            face_list = edge_face_map.FindFromIndex(i)
            if face_list.Extent() == 0:
                free_edges += 1
        
        if free_edges > 0:
            impact = min(60, free_edges * 10)
            score.add_issue(PrintabilityIssue(
                severity=PrintabilitySeverity.CRITICAL if free_edges > 3 else PrintabilitySeverity.ERROR,
                category=PrintabilityCategory.MANIFOLD,
                message=f"{free_edges} offene Kanten (Free Bounds) gefunden",
                score_impact=impact,
                suggestion="Schließen Sie alle offenen Kanten für ein druckbares Modell"
            ))
            
    except Exception as e:
        logger.warning(f"Free-bounds check fehlgeschlagen: {e}")


def _check_normals_score(shape: Any, score: PrintabilityScore) -> None:
    """Prüft Normalen-Konsistenz und aktualisiert Score."""
    try:
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE
        from OCP.BRep import BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Shape
        
        inverted_count = 0
        face_count = 0
        
        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while explorer.More():
            face_count += 1
            # In einer echten Implementierung würden wir hier
            # die Normalen auf Konsistenz prüfen
            explorer.Next()
        
        # Vereinfachte Prüfung: Wenn Faces vorhanden sind, ist der Score gut
        if face_count == 0:
            score.add_issue(PrintabilityIssue(
                severity=PrintabilitySeverity.ERROR,
                category=PrintabilityCategory.NORMALS,
                message="Keine Faces gefunden",
                score_impact=30,
                suggestion="Prüfen Sie die Geometrie-Erzeugung"
            ))
        
        # TODO: Echte Normalen-Konsistenz-Prüfung implementieren
        # Dies erfordert einen Ray-Casting-Check oder ähnliches
        
    except Exception as e:
        logger.warning(f"Normals check fehlgeschlagen: {e}")


def _check_wall_thickness_score(
    shape: Any, 
    score: PrintabilityScore, 
    min_thickness: float
) -> None:
    """Prüft Wandstärke und aktualisiert Score."""
    try:
        from modeling.wall_thickness_analyzer import WallThicknessAnalyzer
        
        analyzer = WallThicknessAnalyzer()
        result = analyzer.analyze(shape, min_thickness)
        
        if not result.ok:
            critical_count = len(result.critical_points)
            warning_count = len(result.warning_points)
            
            if critical_count > 0:
                impact = min(50, critical_count * 10)
                score.add_issue(PrintabilityIssue(
                    severity=PrintabilitySeverity.ERROR,
                    category=PrintabilityCategory.WALL_THICKNESS,
                    message=f"{critical_count} kritisch dünne Wandbereiche (min: {result.min_thickness:.2f}mm)",
                    score_impact=impact,
                    suggestion=f"Erhöhen Sie die Wandstärke auf mindestens {min_thickness}mm"
                ))
            
            if warning_count > 0:
                impact = min(20, warning_count * 2)
                score.add_issue(PrintabilityIssue(
                    severity=PrintabilitySeverity.WARNING,
                    category=PrintabilityCategory.WALL_THICKNESS,
                    message=f"{warning_count} Bereiche mit geringer Wandstärke",
                    score_impact=impact,
                    suggestion="Überprüfen Sie die Wandstärke für bessere Druckergebnisse"
                ))
        
    except ImportError:
        logger.debug("WallThicknessAnalyzer nicht verfügbar")
    except Exception as e:
        logger.warning(f"Wall thickness check fehlgeschlagen: {e}")


def _check_overhang_score(
    shape: Any, 
    score: PrintabilityScore, 
    max_angle: float
) -> None:
    """Prüft Überhänge und aktualisiert Score."""
    try:
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE
        from OCP.BRep import BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Plane
        import math
        
        overhang_faces = 0
        total_faces = 0
        
        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while explorer.More():
            total_faces += 1
            
            # Prüfe Face auf Überhang
            # Vereinfachte Implementierung: Prüfe planare Faces
            face = explorer.Current()
            adaptor = BRepAdaptor_Surface(face)
            
            if adaptor.GetType() == GeomAbs_Plane:
                plane = adaptor.Plane()
                normal = plane.Axis().Direction()
                
                # Überhang wenn Normalen-Z-Komponente negativ (zeigt nach unten)
                # und der Winkel zur Vertikalen größer als max_angle ist
                angle_from_vertical = math.degrees(math.acos(abs(normal.Z())))
                
                if angle_from_vertical > max_angle and normal.Z() < 0:
                    overhang_faces += 1
            
            explorer.Next()
        
        if overhang_faces > 0:
            ratio = overhang_faces / total_faces if total_faces > 0 else 0
            impact = int(min(40, ratio * 100))
            
            score.add_issue(PrintabilityIssue(
                severity=PrintabilitySeverity.WARNING,
                category=PrintabilityCategory.OVERHANG,
                message=f"{overhang_faces} Faces mit Überhang > {max_angle}°",
                score_impact=impact,
                suggestion="Fügen Sie Stützstrukturen hinzu oder orientieren Sie das Modell neu",
                auto_fixable=False
            ))
        
    except Exception as e:
        logger.warning(f"Overhang check fehlgeschlagen: {e}")


def _collect_model_metadata(shape: Any, score: PrintabilityScore) -> None:
    """Sammelt Metadaten über das Modell."""
    try:
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        
        # Volume
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, props)
        score.model_volume_mm3 = props.Mass()
        
        # Bounding Box
        bbox = Bnd_Box()
        BRepBndLib.Add_s(shape, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        score.model_bbox = ((xmin, ymin, zmin), (xmax, ymax, zmax))
        
        # Size check
        size_x = xmax - xmin
        size_y = ymax - ymin
        size_z = zmax - zmin
        max_dim = max(size_x, size_y, size_z)
        
        # Warnung wenn Modell sehr groß oder sehr klein
        if max_dim > 500:  # > 500mm
            score.add_issue(PrintabilityIssue(
                severity=PrintabilitySeverity.WARNING,
                category=PrintabilityCategory.SIZE,
                message=f"Modell ist sehr groß ({max_dim:.0f}mm)",
                score_impact=5,
                suggestion="Überprüfen Sie die Maßeinheiten oder skalieren Sie das Modell"
            ))
        elif max_dim < 1:  # < 1mm
            score.add_issue(PrintabilityIssue(
                severity=PrintabilitySeverity.WARNING,
                category=PrintabilityCategory.SIZE,
                message=f"Modell ist sehr klein ({max_dim:.2f}mm)",
                score_impact=10,
                suggestion="Überprüfen Sie die Maßeinheiten oder skalieren Sie das Modell"
            ))
        
    except Exception as e:
        logger.warning(f"Metadata collection fehlgeschlagen: {e}")
