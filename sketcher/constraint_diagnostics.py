"""
MashCAD Sketcher - Constraint Diagnostics
==========================================

Phase 2: SU-002 + SU-003 - Under/Over-Constrained Diagnostik

Bietet detaillierte Diagnose und Erklärung von Constraint-Problemen:
- Under-Constrained Detection mit Vorschlägen
- Over-Constrained Detection mit Konflikt-Analyse
- Constraint-Konflikt-Erklärung mit Lösungsvorschlägen

Usage:
    from sketcher.constraint_diagnostics import ConstraintDiagnostics
    
    # Diagnose durchführen
    diagnosis = ConstraintDiagnostics.diagnose(sketch)
    
    # Status prüfen
    if diagnosis.is_under_constrained:
        print(f"Fehlende Constraints: {diagnosis.missing_constraints}")
        for suggestion in diagnosis.suggestions:
            print(f"  Vorschlag: {suggestion}")
    
    elif diagnosis.is_over_constrained:
        print(f"Konflikte: {len(diagnosis.conflicts)}")
        for conflict in diagnosis.conflicts:
            print(f"  {conflict.explanation}")

Author: Kimi (SU-002/SU-003 Implementation)
Date: 2026-02-19
Branch: feature/v1-ux-aiB
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple, Set
from enum import Enum, auto
from collections import defaultdict
import math
from loguru import logger

from .constraints import Constraint, ConstraintType, ConstraintStatus, ConstraintPriority


class ConstraintDiagnosisType(Enum):
    """Typ der Constraint-Diagnose."""
    FULLY_CONSTRAINED = auto()      # Vollständig bestimmt
    UNDER_CONSTRAINED = auto()      # Unterbestimmt
    OVER_CONSTRAINED = auto()       # Überbestimmt (widersprüchlich)
    INCONSISTENT = auto()           # Inkonsistent (ungültige Constraints)
    UNKNOWN = auto()                # Unbekannt


@dataclass
class ConstraintConflict:
    """
    Beschreibt einen Constraint-Konflikt.
    
    Attributes:
        constraints: Liste der in Konflikt stehenden Constraints
        conflict_type: Art des Konflikts
        explanation: Menschlich lesbare Erklärung
        suggested_resolution: Vorgeschlagene Lösung
        severity: Schweregrad des Konflikts
    """
    constraints: List[Constraint]
    conflict_type: str
    explanation: str
    suggested_resolution: str
    severity: ConstraintPriority = ConstraintPriority.HIGH
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            'constraints': [str(c) for c in self.constraints],
            'conflict_type': self.conflict_type,
            'explanation': self.explanation,
            'suggested_resolution': self.suggested_resolution,
            'severity': self.severity.name
        }


@dataclass
class ConstraintSuggestion:
    """
    Vorschlag für einen neuen Constraint.
    
    Attributes:
        constraint_type: Vorgeschlagener Constraint-Typ
        entities: Betroffene Geometrie-Elemente
        reason: Begründung für den Vorschlag
        priority: Priorität des Vorschlags
    """
    constraint_type: ConstraintType
    entities: List[Any]
    reason: str
    priority: ConstraintPriority = ConstraintPriority.MEDIUM
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            'constraint_type': self.constraint_type.name,
            'entities': [str(e) for e in self.entities],
            'reason': self.reason,
            'priority': self.priority.name
        }


@dataclass
class ConstraintDiagnosis:
    """
    Ergebnis einer Constraint-Diagnose.
    
    Attributes:
        diagnosis_type: Typ der Diagnose
        status: ConstraintStatus
        dof: Degrees of Freedom
        total_variables: Gesamtzahl der Variablen
        total_constraints: Gesamtzahl der Constraints
        
        # Under-Constrained
        missing_constraint_count: Geschätzte fehlende Constraints
        suggestions: Vorschläge für neue Constraints
        unconstrained_elements: Elemente ohne Constraints
        
        # Over-Constrained
        conflicts: Liste der gefundenen Konflikte
        redundant_constraints: Liste redundanter Constraints
        
        # Allgemein
        invalid_constraints: Ungültige Constraints
        message: Zusammenfassende Nachricht
        detailed_report: Detaillierter Report
    """
    diagnosis_type: ConstraintDiagnosisType
    status: ConstraintStatus
    dof: int
    total_variables: int
    total_constraints: int
    
    # Under-Constrained
    missing_constraint_count: int = 0
    suggestions: List[ConstraintSuggestion] = field(default_factory=list)
    unconstrained_elements: List[Any] = field(default_factory=list)
    
    # Over-Constrained
    conflicts: List[ConstraintConflict] = field(default_factory=list)
    redundant_constraints: List[Constraint] = field(default_factory=list)
    
    # Allgemein
    invalid_constraints: List[Tuple[Constraint, str]] = field(default_factory=list)
    message: str = ""
    detailed_report: str = ""
    
    @property
    def is_fully_constrained(self) -> bool:
        """True wenn vollständig bestimmt."""
        return self.diagnosis_type == ConstraintDiagnosisType.FULLY_CONSTRAINED
    
    @property
    def is_under_constrained(self) -> bool:
        """True wenn unterbestimmt."""
        return self.diagnosis_type == ConstraintDiagnosisType.UNDER_CONSTRAINED
    
    @property
    def is_over_constrained(self) -> bool:
        """True wenn überbestimmt."""
        return self.diagnosis_type == ConstraintDiagnosisType.OVER_CONSTRAINED
    
    @property
    def is_inconsistent(self) -> bool:
        """True wenn inkonsistent."""
        return self.diagnosis_type == ConstraintDiagnosisType.INCONSISTENT
    
    @property
    def has_issues(self) -> bool:
        """True wenn es Probleme gibt."""
        return self.diagnosis_type not in (
            ConstraintDiagnosisType.FULLY_CONSTRAINED,
            ConstraintDiagnosisType.UNKNOWN
        )
    
    def to_user_report(self) -> str:
        """Erzeugt einen nutzerfreundlichen Report."""
        lines = ["Constraint-Diagnose", "=" * 40, ""]
        
        # Status
        status_names = {
            ConstraintDiagnosisType.FULLY_CONSTRAINED: "✓ Vollständig bestimmt",
            ConstraintDiagnosisType.UNDER_CONSTRAINED: "⚠ Unterbestimmt",
            ConstraintDiagnosisType.OVER_CONSTRAINED: "✗ Überbestimmt (Widersprüche)",
            ConstraintDiagnosisType.INCONSISTENT: "✗ Inkonsistent",
            ConstraintDiagnosisType.UNKNOWN: "? Unbekannt"
        }
        lines.append(f"Status: {status_names.get(self.diagnosis_type, 'Unknown')}")
        lines.append(f"Freiheitsgrade: {self.dof}")
        lines.append(f"Variablen: {self.total_variables}, Constraints: {self.total_constraints}")
        lines.append("")
        
        # Under-Constrained Details
        if self.is_under_constrained:
            lines.append(f"Fehlende Constraints: ~{self.missing_constraint_count}")
            if self.suggestions:
                lines.append("\nVorschläge:")
                for i, sugg in enumerate(self.suggestions[:5], 1):
                    lines.append(f"  {i}. {sugg.constraint_type.name}: {sugg.reason}")
            lines.append("")
        
        # Over-Constrained Details
        if self.is_over_constrained:
            lines.append(f"Gefundene Konflikte: {len(self.conflicts)}")
            for i, conflict in enumerate(self.conflicts[:3], 1):
                lines.append(f"\nKonflikt {i}: {conflict.conflict_type}")
                lines.append(f"  {conflict.explanation}")
                lines.append(f"  💡 Lösung: {conflict.suggested_resolution}")
            lines.append("")
        
        # Invalid Constraints
        if self.invalid_constraints:
            lines.append(f"Ungültige Constraints: {len(self.invalid_constraints)}")
            for constraint, error in self.invalid_constraints[:3]:
                lines.append(f"  - {constraint}: {error}")
            lines.append("")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für Serialisierung."""
        return {
            'diagnosis_type': self.diagnosis_type.name,
            'status': self.status.name,
            'dof': self.dof,
            'total_variables': self.total_variables,
            'total_constraints': self.total_constraints,
            'missing_constraint_count': self.missing_constraint_count,
            'suggestions': [s.to_dict() for s in self.suggestions],
            'conflicts': [c.to_dict() for c in self.conflicts],
            'invalid_constraints': [
                {'constraint': str(c), 'error': e}
                for c, e in self.invalid_constraints
            ],
            'message': self.message
        }


class ConstraintDiagnostics:
    """
    Zentrale Constraint-Diagnostik-Engine.
    
    Bietet:
    - Schnelle DOF-Analyse
    - Konflikt-Erkennung
    - Vorschlags-Generierung
    - Detaillierte Reports
    """
    
    # DOF-Verbrauch pro Constraint-Typ
    _CONSTRAINT_DOF_COST = {
        ConstraintType.FIXED: 2,           # Fixiert 2 Variablen (x, y)
        ConstraintType.COINCIDENT: 2,      # Zwei Punkte werden zu einem (2 DOF)
        ConstraintType.POINT_ON_LINE: 1,   # Punkt auf Linie (1 DOF)
        ConstraintType.POINT_ON_CIRCLE: 1, # Punkt auf Kreis (1 DOF)
        ConstraintType.HORIZONTAL: 1,      # Y-Freiheitsgrad eingeschränkt
        ConstraintType.VERTICAL: 1,        # X-Freiheitsgrad eingeschränkt
        ConstraintType.PARALLEL: 1,        # Winkel eingeschränkt
        ConstraintType.PERPENDICULAR: 1,   # Winkel eingeschränkt
        ConstraintType.COLLINEAR: 2,       # Zwei Linien zu einer
        ConstraintType.EQUAL_LENGTH: 1,    # Längenbeziehung
        ConstraintType.CONCENTRIC: 2,      # Zwei Kreismittelpunkte
        ConstraintType.EQUAL_RADIUS: 1,    # Radien gleich
        ConstraintType.TANGENT: 1,         # Tangential-Bedingung
        ConstraintType.DISTANCE: 1,        # Abstands-Constraint
        ConstraintType.LENGTH: 1,          # Längen-Constraint
        ConstraintType.ANGLE: 1,           # Winkel-Constraint
        ConstraintType.RADIUS: 1,          # Radius-Constraint
        ConstraintType.DIAMETER: 1,        # Durchmesser-Constraint
        ConstraintType.SYMMETRIC: 2,       # Symmetrie-Constraint
        ConstraintType.MIDPOINT: 2,        # Mittelpunkt-Constraint
    }
    
    @classmethod
    def diagnose(cls, sketch) -> ConstraintDiagnosis:
        """
        Führt eine vollständige Constraint-Diagnose durch.
        
        Args:
            sketch: Das Sketch-Objekt zu diagnostizieren
            
        Returns:
            ConstraintDiagnosis mit allen Details
        """
        logger.debug(f"Starting constraint diagnosis for sketch")
        
        # 1. Grundlegende DOF-Analyse
        vars_count, constr_count, dof = sketch.calculate_dof()
        
        # 2. Ungültige Constraints finden
        invalid_constraints = cls._find_invalid_constraints(sketch)
        
        # 3. Status bestimmen
        if invalid_constraints:
            diagnosis_type = ConstraintDiagnosisType.INCONSISTENT
            status = ConstraintStatus.INCONSISTENT
        elif dof > 0:
            diagnosis_type = ConstraintDiagnosisType.UNDER_CONSTRAINED
            status = ConstraintStatus.UNDER_CONSTRAINED
        elif constr_count > vars_count:
            diagnosis_type = ConstraintDiagnosisType.OVER_CONSTRAINED
            status = ConstraintStatus.OVER_CONSTRAINED
        else:
            # Könnte vollständig bestimmt sein
            diagnosis_type = ConstraintDiagnosisType.FULLY_CONSTRAINED
            status = ConstraintStatus.FULLY_CONSTRAINED
        
        # 4. Diagnose-Objekt erstellen
        diagnosis = ConstraintDiagnosis(
            diagnosis_type=diagnosis_type,
            status=status,
            dof=dof,
            total_variables=vars_count,
            total_constraints=constr_count,
            invalid_constraints=invalid_constraints
        )
        
        # 5. Typ-spezifische Analyse
        if diagnosis.is_under_constrained:
            cls._analyze_under_constrained(sketch, diagnosis)
        elif diagnosis.is_over_constrained:
            cls._analyze_over_constrained(sketch, diagnosis)
        
        # 6. Message generieren
        diagnosis.message = cls._generate_message(diagnosis)
        diagnosis.detailed_report = diagnosis.to_user_report()
        
        logger.debug(f"Diagnosis complete: {diagnosis.diagnosis_type.name}, DOF={dof}")
        return diagnosis
    
    @classmethod
    def quick_check(cls, sketch) -> Tuple[ConstraintStatus, int]:
        """
        Schneller Check ohne detaillierte Analyse.
        
        Returns:
            (Status, DOF)
        """
        vars_count, constr_count, dof = sketch.calculate_dof()
        
        if dof > 0:
            return ConstraintStatus.UNDER_CONSTRAINED, dof
        elif constr_count > vars_count:
            return ConstraintStatus.OVER_CONSTRAINED, dof
        else:
            return ConstraintStatus.FULLY_CONSTRAINED, dof
    
    @classmethod
    def _find_invalid_constraints(cls, sketch) -> List[Tuple[Constraint, str]]:
        """Findet alle ungültigen Constraints."""
        invalid = []
        for constraint in sketch.constraints:
            if not constraint.is_valid():
                error = constraint.validation_error()
                invalid.append((constraint, error or "Unbekannter Fehler"))
        return invalid
    
    @classmethod
    def _analyze_under_constrained(cls, sketch, diagnosis: ConstraintDiagnosis):
        """Analysiert einen unterbestimmten Sketch."""
        # 1. Unconstrained Elemente finden
        unconstrained = cls._find_unconstrained_elements(sketch)
        diagnosis.unconstrained_elements = unconstrained
        
        # 2. Geschätzte fehlende Constraints
        diagnosis.missing_constraint_count = max(0, diagnosis.dof)
        
        # 3. Vorschläge generieren
        suggestions = cls._generate_suggestions(sketch, unconstrained)
        diagnosis.suggestions = suggestions
    
    @classmethod
    def _analyze_over_constrained(cls, sketch, diagnosis: ConstraintDiagnosis):
        """Analysiert einen überbestimmten Sketch."""
        # 1. Konflikte finden
        conflicts = cls._find_conflicts(sketch)
        diagnosis.conflicts = conflicts
        
        # 2. Redundante Constraints finden
        redundant = cls._find_redundant_constraints(sketch)
        diagnosis.redundant_constraints = redundant
    
    @classmethod
    def _find_unconstrained_elements(cls, sketch) -> List[Any]:
        """Findet Geometrie-Elemente ohne Constraints."""
        unconstrained = []
        
        # Prüfe welche Elemente Constraints haben
        constrained_elements = set()
        for constraint in sketch.constraints:
            if not getattr(constraint, 'enabled', True):
                continue
            for entity in constraint.entities:
                constrained_elements.add(id(entity))
        
        # Punkte ohne Constraints
        for point in sketch.points:
            if id(point) not in constrained_elements and not point.fixed:
                unconstrained.append(point)
        
        return unconstrained
    
    @classmethod
    def _generate_suggestions(
        cls,
        sketch,
        unconstrained_elements: List[Any]
    ) -> List[ConstraintSuggestion]:
        """Generiert Vorschläge für fehlende Constraints."""
        suggestions = []
        
        # Wenn es freie Punkte gibt
        free_points = [e for e in unconstrained_elements 
                      if hasattr(e, 'x') and hasattr(e, 'y')]
        
        if free_points:
            # Vorschlag 1: Ersten Punkt fixieren
            suggestions.append(ConstraintSuggestion(
                constraint_type=ConstraintType.FIXED,
                entities=[free_points[0]],
                reason="Fixiert den ersten Punkt als Referenz",
                priority=ConstraintPriority.CRITICAL
            ))
            
            # Vorschlag 2: Zweiten Punkt horizontal/vertical ausrichten
            if len(free_points) >= 2:
                suggestions.append(ConstraintSuggestion(
                    constraint_type=ConstraintType.HORIZONTAL,
                    entities=[free_points[0], free_points[1]],
                    reason="Erstellt horizontale Referenzlinie",
                    priority=ConstraintPriority.HIGH
                ))
        
        # Vorschläge basierend auf Geometrie-Typen
        for line in sketch.lines:
            has_constraint = any(
                c for c in sketch.constraints
                if line in c.entities or line.start in c.entities or line.end in c.entities
            )
            if not has_constraint:
                suggestions.append(ConstraintSuggestion(
                    constraint_type=ConstraintType.LENGTH,
                    entities=[line],
                    reason=f"Linie {getattr(line, 'id', '?')} hat keine Constraints",
                    priority=ConstraintPriority.LOW
                ))
        
        return suggestions
    
    @classmethod
    def _find_conflicts(cls, sketch) -> List[ConstraintConflict]:
        """Findet widersprüchliche Constraints."""
        conflicts = []
        constraints = [c for c in sketch.constraints 
                      if getattr(c, 'enabled', True) and c.is_valid()]
        
        # Gruppiere Constraints nach betroffenen Entities
        constraints_by_entity = defaultdict(list)
        for constraint in constraints:
            for entity in constraint.entities:
                constraints_by_entity[id(entity)].append(constraint)
        
        # Prüfe auf spezifische Konflikte
        # Konflikt 1: Horizontal + Vertical an gleicher Linie
        for line in sketch.lines:
            line_constraints = [
                c for c in constraints
                if line in c.entities or line.start in c.entities or line.end in c.entities
            ]
            
            has_horizontal = any(c.type == ConstraintType.HORIZONTAL for c in line_constraints)
            has_vertical = any(c.type == ConstraintType.VERTICAL for c in line_constraints)
            has_length = any(
                c.type == ConstraintType.LENGTH and getattr(c, 'value', 0) > 0.001
                for c in line_constraints
            )
            
            if has_horizontal and has_vertical and has_length:
                conflicting = [c for c in line_constraints 
                             if c.type in (ConstraintType.HORIZONTAL, ConstraintType.VERTICAL)]
                conflicts.append(ConstraintConflict(
                    constraints=conflicting,
                    conflict_type="GEOMETRIC_IMPOSSIBLE",
                    explanation="Eine Linie kann nicht gleichzeitig horizontal und vertikal sein",
                    suggested_resolution="Entfernen Sie entweder HORIZONTAL oder VERTICAL, oder setzen Sie LENGTH auf 0",
                    severity=ConstraintPriority.CRITICAL
                ))
        
        # Konflikt 2: Gegensätzliche Dimensions-Constraints
        for entity_id, entity_constraints in constraints_by_entity.items():
            length_constraints = [
                c for c in entity_constraints
                if c.type == ConstraintType.LENGTH and c.value is not None
            ]
            if len(length_constraints) >= 2:
                values = [c.value for c in length_constraints]
                if len(set(values)) > 1:  # Unterschiedliche Werte
                    conflicts.append(ConstraintConflict(
                        constraints=length_constraints,
                        conflict_type="CONFLICTING_DIMENSIONS",
                        explanation=f"Widersprüchliche Längen-Constraints: {values}",
                        suggested_resolution="Entfernen Sie alle bis auf einen LENGTH-Constraint",
                        severity=ConstraintPriority.HIGH
                    ))
        
        return conflicts
    
    @classmethod
    def _find_redundant_constraints(cls, sketch) -> List[Constraint]:
        """Findet redundante (überflüssige) Constraints."""
        redundant = []
        constraints = [c for c in sketch.constraints 
                      if getattr(c, 'enabled', True)]
        
        # Prüfe auf duplizierte Constraints
        seen = set()
        for constraint in constraints:
            # Erstelle Schlüssel aus Typ und Entities
            entity_ids = tuple(sorted(id(e) for e in constraint.entities))
            key = (constraint.type, entity_ids)
            
            if key in seen:
                redundant.append(constraint)
            else:
                seen.add(key)
        
        return redundant
    
    @classmethod
    def _generate_message(cls, diagnosis: ConstraintDiagnosis) -> str:
        """Generiert eine zusammenfassende Nachricht."""
        if diagnosis.is_fully_constrained:
            return "Sketch ist vollständig bestimmt"
        elif diagnosis.is_under_constrained:
            return f"Unterbestimmt: {diagnosis.dof} Freiheitsgrade fehlen"
        elif diagnosis.is_over_constrained:
            return f"Überbestimmt: {len(diagnosis.conflicts)} Konflikt(e) gefunden"
        elif diagnosis.is_inconsistent:
            return f"Inkonsistent: {len(diagnosis.invalid_constraints)} ungültige Constraint(s)"
        else:
            return "Unbekannter Status"


# =============================================================================
# Convenience Functions
# =============================================================================

def diagnose_sketch(sketch) -> ConstraintDiagnosis:
    """Shortcut für ConstraintDiagnostics.diagnose()."""
    return ConstraintDiagnostics.diagnose(sketch)


def quick_check(sketch) -> Tuple[ConstraintStatus, int]:
    """Shortcut für ConstraintDiagnostics.quick_check()."""
    return ConstraintDiagnostics.quick_check(sketch)


def get_constraint_report(sketch) -> str:
    """Generiert einen nutzerfreundlichen Report."""
    diagnosis = ConstraintDiagnostics.diagnose(sketch)
    return diagnosis.to_user_report()
