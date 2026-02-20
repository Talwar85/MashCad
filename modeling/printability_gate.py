"""
MashCAD - Printability Trust Gate
==================================

PR-010: Printability Trust Gate Enforcement

Der Trust Gate validiert Modelle vor dem Export und blockiert
nicht-druckbare Modelle basierend auf konfigurierbaren Schwellwerten.

Funktionalität:
- PASS/WARN/FAIL Status basierend auf Printability-Score
- Konfigurierbare Schwellwerte pro Kategorie
- Blocking bei CRITICAL Issues
- Override-Möglichkeit für fortgeschrittene Benutzer

Usage:
    from modeling.printability_gate import PrintabilityGate, GateResult
    
    gate = PrintabilityGate()
    result = gate.check(solid)
    
    if result.status == GateStatus.PASS:
        # Export erlaubt
        export_stl(solid)
    elif result.status == GateStatus.WARN:
        # Warnung anzeigen, Export möglich
        if user_confirms():
            export_stl(solid)
    else:  # FAIL
        # Export blockiert
        show_errors(result.issues)

Author: Claude (PR-010 Printability Trust Gate)
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Dict, Any, Callable
from loguru import logger

from modeling.printability_score import (
    PrintabilityScore,
    PrintabilityIssue,
    PrintabilitySeverity,
    PrintabilityCategory,
    calculate_printability_score
)


class GateStatus(Enum):
    """Status des Trust Gate Checks."""
    PASS = "pass"       # Alle Checks bestanden, Export erlaubt
    WARN = "warn"       # Warnungen vorhanden, Export mit Bestätigung möglich
    FAIL = "fail"       # Kritische Probleme, Export blockiert
    ERROR = "error"     # Unerwarteter Fehler während des Checks


@dataclass
class GateThresholds:
    """
    Konfigurierbare Schwellwerte für den Trust Gate.
    
    Args:
        min_overall_score: Minimaler Gesamtscore (0-100)
        min_manifold_score: Minimaler Manifold-Score (0-100)
        min_normals_score: Minimaler Normalen-Score (0-100)
        min_wall_thickness_score: Minimaler Wandstärken-Score (0-100)
        min_overhang_score: Minimaler Überhang-Score (0-100)
        block_on_critical: Export bei CRITICAL Issues blockieren
        block_on_error: Export bei ERROR Issues blockieren
        warn_on_warning: Warnung bei WARNING Issues anzeigen
    """
    min_overall_score: int = 60
    min_manifold_score: int = 50
    min_normals_score: int = 40
    min_wall_thickness_score: int = 40
    min_overhang_score: int = 30
    block_on_critical: bool = True
    block_on_error: bool = False
    warn_on_warning: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "min_overall_score": self.min_overall_score,
            "min_manifold_score": self.min_manifold_score,
            "min_normals_score": self.min_normals_score,
            "min_wall_thickness_score": self.min_wall_thickness_score,
            "min_overhang_score": self.min_overhang_score,
            "block_on_critical": self.block_on_critical,
            "block_on_error": self.block_on_error,
            "warn_on_warning": self.warn_on_warning
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GateThresholds':
        """Erstellt Thresholds aus Dictionary."""
        return cls(
            min_overall_score=data.get("min_overall_score", 60),
            min_manifold_score=data.get("min_manifold_score", 50),
            min_normals_score=data.get("min_normals_score", 40),
            min_wall_thickness_score=data.get("min_wall_thickness_score", 40),
            min_overhang_score=data.get("min_overhang_score", 30),
            block_on_critical=data.get("block_on_critical", True),
            block_on_error=data.get("block_on_error", False),
            warn_on_warning=data.get("warn_on_warning", True)
        )
    
    @classmethod
    def strict(cls) -> 'GateThresholds':
        """Strikte Thresholds für produktive Exporte."""
        return cls(
            min_overall_score=80,
            min_manifold_score=70,
            min_normals_score=60,
            min_wall_thickness_score=60,
            min_overhang_score=50,
            block_on_critical=True,
            block_on_error=True,
            warn_on_warning=True
        )
    
    @classmethod
    def lenient(cls) -> 'GateThresholds':
        """Lockere Thresholds für Test/Entwicklung."""
        return cls(
            min_overall_score=40,
            min_manifold_score=30,
            min_normals_score=20,
            min_wall_thickness_score=20,
            min_overhang_score=10,
            block_on_critical=True,
            block_on_error=False,
            warn_on_warning=True
        )


@dataclass
class GateResult:
    """
    Ergebnis eines Trust Gate Checks.
    
    Args:
        status: GateStatus (PASS/WARN/FAIL/ERROR)
        score: Der berechnete PrintabilityScore
        blocking_issues: Issues die den Export blockieren
        warning_issues: Issues die eine Warnung erzeugen
        thresholds: Die verwendeten Schwellwerte
        can_override: True wenn der Benutzer den Gate überschreiben kann
        message: Zusammenfassende Nachricht
    """
    status: GateStatus
    score: PrintabilityScore
    blocking_issues: List[PrintabilityIssue] = field(default_factory=list)
    warning_issues: List[PrintabilityIssue] = field(default_factory=list)
    thresholds: GateThresholds = field(default_factory=GateThresholds)
    can_override: bool = False
    message: str = ""
    
    @property
    def passed(self) -> bool:
        """True wenn der Gate bestanden wurde (PASS oder WARN)."""
        return self.status in (GateStatus.PASS, GateStatus.WARN)
    
    @property
    def blocked(self) -> bool:
        """True wenn der Export blockiert ist (FAIL)."""
        return self.status == GateStatus.FAIL
    
    @property
    def has_warnings(self) -> bool:
        """True wenn Warnungen vorhanden sind."""
        return len(self.warning_issues) > 0 or self.status == GateStatus.WARN
    
    def get_summary(self) -> str:
        """Gibt eine Zusammenfassung zurück."""
        if self.status == GateStatus.PASS:
            return f"✓ Printability Check bestanden (Score: {self.score.overall_score}/100)"
        elif self.status == GateStatus.WARN:
            return f"⚠ Printability Warnungen (Score: {self.score.overall_score}/100)"
        elif self.status == GateStatus.FAIL:
            return f"✗ Printability Check fehlgeschlagen (Score: {self.score.overall_score}/100)"
        else:
            return f"⚠ Printability Check Fehler: {self.message}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für Serialisierung."""
        return {
            "status": self.status.value,
            "score": self.score.to_dict(),
            "blocking_issues": [issue.to_dict() for issue in self.blocking_issues],
            "warning_issues": [issue.to_dict() for issue in self.warning_issues],
            "thresholds": self.thresholds.to_dict(),
            "can_override": self.can_override,
            "message": self.message,
            "summary": self.get_summary()
        }


class PrintabilityGate:
    """
    Trust Gate für Printability-Validierung vor Export.
    
    Der Gate prüft Modelle gegen konfigurierbare Schwellwerte
    und entscheidet ob ein Export erlaubt, mit Warnung oder
    blockiert ist.
    
    Usage:
        # Standard-Konfiguration
        gate = PrintabilityGate()
        result = gate.check(solid)
        
        # Strikte Konfiguration
        gate = PrintabilityGate(thresholds=GateThresholds.strict())
        result = gate.check(solid)
        
        # Custom Thresholds
        thresholds = GateThresholds(min_overall_score=75)
        gate = PrintabilityGate(thresholds=thresholds)
    """
    
    def __init__(
        self,
        thresholds: Optional[GateThresholds] = None,
        check_wall_thickness: bool = True,
        check_overhangs: bool = True,
        min_wall_thickness: float = 0.8,
        max_overhang_angle: float = 45.0
    ):
        """
        Initialisiert den Printability Gate.
        
        Args:
            thresholds: Konfigurierbare Schwellwerte (None = Default)
            check_wall_thickness: Ob Wandstärke geprüft werden soll
            check_overhangs: Ob Überhänge geprüft werden sollen
            min_wall_thickness: Minimale Wandstärke in mm
            max_overhang_angle: Maximaler Überhangswinkel in Grad
        """
        self.thresholds = thresholds or GateThresholds()
        self.check_wall_thickness = check_wall_thickness
        self.check_overhangs = check_overhangs
        self.min_wall_thickness = min_wall_thickness
        self.max_overhang_angle = max_overhang_angle
        
        # Feature Flag Integration
        self._load_feature_flags()
    
    def _load_feature_flags(self) -> None:
        """Lädt Konfiguration aus Feature Flags."""
        try:
            from config.feature_flags import is_enabled, FEATURE_FLAGS
            
            # Gate aktiviert?
            self.enabled = is_enabled("printability_trust_gate")
            
            # Min Score aus Feature Flags (falls vorhanden)
            if "printability_min_score" in FEATURE_FLAGS:
                self.thresholds.min_overall_score = FEATURE_FLAGS["printability_min_score"]
            
            # Block on Critical aus Feature Flags
            if "printability_block_on_critical" in FEATURE_FLAGS:
                self.thresholds.block_on_critical = FEATURE_FLAGS["printability_block_on_critical"]
                
        except ImportError:
            self.enabled = True  # Default: aktiviert
    
    def check(self, solid: Any) -> GateResult:
        """
        Führt den Printability Check durch.
        
        Args:
            solid: Zu prüfendes Solid (Build123d oder OCP)
            
        Returns:
            GateResult mit Status und Details
        """
        if not self.enabled:
            # Gate deaktiviert - immer PASS
            return GateResult(
                status=GateStatus.PASS,
                score=PrintabilityScore(),
                message="Trust Gate deaktiviert"
            )
        
        try:
            # Berechne Printability Score
            score = calculate_printability_score(
                solid,
                check_wall_thickness=self.check_wall_thickness,
                check_overhangs=self.check_overhangs,
                min_wall_thickness=self.min_wall_thickness,
                max_overhang_angle=self.max_overhang_angle
            )
            
            # Analysiere Issues
            blocking_issues = []
            warning_issues = []
            
            for issue in score.issues:
                if issue.severity == PrintabilitySeverity.CRITICAL:
                    if self.thresholds.block_on_critical:
                        blocking_issues.append(issue)
                    else:
                        warning_issues.append(issue)
                elif issue.severity == PrintabilitySeverity.ERROR:
                    if self.thresholds.block_on_error:
                        blocking_issues.append(issue)
                    else:
                        warning_issues.append(issue)
                elif issue.severity == PrintabilitySeverity.WARNING:
                    if self.thresholds.warn_on_warning:
                        warning_issues.append(issue)
            
            # Prüfe Score-Thresholds
            score_failures = []
            
            if score.overall_score < self.thresholds.min_overall_score:
                score_failures.append(
                    PrintabilityIssue(
                        severity=PrintabilitySeverity.ERROR,
                        category=PrintabilityCategory.GEOMETRY,
                        message=f"Gesamtscore {score.overall_score} unter Minimum {self.thresholds.min_overall_score}",
                        score_impact=0
                    )
                )
            
            if score.manifold_score < self.thresholds.min_manifold_score:
                score_failures.append(
                    PrintabilityIssue(
                        severity=PrintabilitySeverity.ERROR,
                        category=PrintabilityCategory.MANIFOLD,
                        message=f"Manifold-Score {score.manifold_score} unter Minimum {self.thresholds.min_manifold_score}",
                        score_impact=0
                    )
                )
            
            if score.normals_score < self.thresholds.min_normals_score:
                score_failures.append(
                    PrintabilityIssue(
                        severity=PrintabilitySeverity.WARNING,
                        category=PrintabilityCategory.NORMALS,
                        message=f"Normalen-Score {score.normals_score} unter Minimum {self.thresholds.min_normals_score}",
                        score_impact=0
                    )
                )
            
            if score.wall_thickness_score < self.thresholds.min_wall_thickness_score:
                score_failures.append(
                    PrintabilityIssue(
                        severity=PrintabilitySeverity.WARNING,
                        category=PrintabilityCategory.WALL_THICKNESS,
                        message=f"Wandstärken-Score {score.wall_thickness_score} unter Minimum {self.thresholds.min_wall_thickness_score}",
                        score_impact=0
                    )
                )
            
            if score.overhang_score < self.thresholds.min_overhang_score:
                score_failures.append(
                    PrintabilityIssue(
                        severity=PrintabilitySeverity.WARNING,
                        category=PrintabilityCategory.OVERHANG,
                        message=f"Überhang-Score {score.overhang_score} unter Minimum {self.thresholds.min_overhang_score}",
                        score_impact=0
                    )
                )
            
            # Score-Failures zu Issues hinzufügen
            for failure in score_failures:
                if failure.severity == PrintabilitySeverity.ERROR:
                    blocking_issues.append(failure)
                else:
                    warning_issues.append(failure)
            
            # Bestimme Gate Status
            if blocking_issues:
                status = GateStatus.FAIL
                can_override = False
                message = f"Export blockiert: {len(blocking_issues)} kritische Probleme"
            elif warning_issues:
                status = GateStatus.WARN
                can_override = True
                message = f"Warnungen: {len(warning_issues)} Probleme gefunden"
            else:
                status = GateStatus.PASS
                can_override = False
                message = "Alle Checks bestanden"
            
            return GateResult(
                status=status,
                score=score,
                blocking_issues=blocking_issues,
                warning_issues=warning_issues,
                thresholds=self.thresholds,
                can_override=can_override,
                message=message
            )
            
        except Exception as e:
            logger.exception("Printability Gate Check fehlgeschlagen")
            return GateResult(
                status=GateStatus.ERROR,
                score=PrintabilityScore(),
                message=f"Gate Check Fehler: {str(e)}"
            )
    
    def quick_check(self, solid: Any) -> bool:
        """
        Schneller Check ob ein Solid den Gate passiert.
        
        Args:
            solid: Zu prüfendes Solid
            
        Returns:
            True wenn bestanden (PASS oder WARN)
        """
        result = self.check(solid)
        return result.passed
    
    def is_printable(self, solid: Any) -> bool:
        """
        Prüft ob ein Solid druckbar ist (PASS Status).
        
        Args:
            solid: Zu prüfendes Solid
            
        Returns:
            True wenn druckbar ohne Warnungen
        """
        result = self.check(solid)
        return result.status == GateStatus.PASS


# Singleton-Instanz für einfache Verwendung
_default_gate: Optional[PrintabilityGate] = None


def get_default_gate() -> PrintabilityGate:
    """
    Gibt die Standard-Gate-Instanz zurück.
    
    Die Instanz wird beim ersten Aufruf erstellt und
    mit den Feature-Flag-Einstellungen konfiguriert.
    """
    global _default_gate
    if _default_gate is None:
        _default_gate = PrintabilityGate()
    return _default_gate


def check_printability(solid: Any) -> GateResult:
    """
    Convenience-Funktion für Printability Check.
    
    Verwendet die Standard-Gate-Instanz.
    
    Args:
        solid: Zu prüfendes Solid
        
    Returns:
        GateResult mit Status und Details
    """
    return get_default_gate().check(solid)


def is_printable(solid: Any) -> bool:
    """
    Convenience-Funktion für schnellen Printability Check.
    
    Args:
        solid: Zu prüfendes Solid
        
    Returns:
        True wenn das Modell den Gate passiert
    """
    return get_default_gate().quick_check(solid)
