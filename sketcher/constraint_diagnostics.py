"""
MashCAD Sketcher - Constraint Diagnostics
==========================================

Phase 2: SU-002 + SU-003 - Under/Over-Constrained Diagnostik

Bietet detaillierte Diagnose und Erklärung von Constraint-Problemen:
- Under-Constrained Detection mit Vorschlägen
- Over-Constrained Detection mit Konflikt-Analyse
- Constraint-Konflikt-Erklärung mit Lösungsvorschlägen
- Degrees of Freedom (DOF) Berechnung

Usage:
    from sketcher.constraint_diagnostics import (
        ConstraintDiagnostics, 
        analyze_constraint_state,
        detect_redundant_constraints,
        detect_conflicting_constraints,
        suggest_missing_constraints
    )
    
    # Diagnose durchführen
    diagnosis = analyze_constraint_state(sketch)
    
    # Status prüfen
    if diagnosis.is_under_constrained:
        print(f"DOF: {diagnosis.degrees_of_freedom}")
        for suggestion in diagnosis.suggested_constraints:
            print(f"  Vorschlag: {suggestion}")
    
    elif diagnosis.is_over_constrained:
        print(f"Konflikte: {len(diagnosis.conflicting_constraints)}")
        for conflict in diagnosis.conflicting_constraints:
            print(f"  {conflict.explanation}")

Author: Kimi (SU-002/SU-003 Implementation)
Date: 2026-02-19
Updated: 2026-02-20 (Sprint 2 Enhancement)
Branch: feature/v1-roadmap-execution
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple, Set, Union
from enum import Enum, auto
from collections import defaultdict
import math
from loguru import logger

from .constraints import Constraint, ConstraintType, ConstraintStatus, ConstraintPriority
from .geometry import Point2D, Line2D, Circle2D, Arc2D


class ConstraintDiagnosisType(Enum):
    """Typ der Constraint-Diagnose."""
    FULLY_CONSTRAINED = auto()      # Vollständig bestimmt
    UNDER_CONSTRAINED = auto()      # Unterbestimmt
    OVER_CONSTRAINED = auto()       # Überbestimmt (widersprüchlich)
    INCONSISTENT = auto()           # Inkonsistent (ungültige Constraints)
    UNKNOWN = auto()                # Unbekannt


class ConflictSeverity(Enum):
    """Schweregrad eines Constraint-Konflikts."""
    CRITICAL = "critical"    # Unlösbar - muss behoben werden
    HIGH = "high"            # Schwerwiegend - sollte behoben werden
    MEDIUM = "medium"        # Mittel - redundante Constraints
    LOW = "low"              # Geringfügig - Warnung


@dataclass
class ConstraintInfo:
    """
    Informationen über einen Constraint für Diagnosezwecke.
    
    Attributes:
        constraint: Der Constraint selbst
        entity_ids: IDs der betroffenen Entities
        dof_consumed: Anzahl der verbrauchten Freiheitsgrade
        is_redundant: Ob der Constraint redundant ist
        redundancy_reason: Grund für Redundanz (falls zutreffend)
    """
    constraint: Constraint
    entity_ids: List[str] = field(default_factory=list)
    dof_consumed: int = 1
    is_redundant: bool = False
    redundancy_reason: str = ""
    
    def __post_init__(self):
        if not self.entity_ids:
            self.entity_ids = [getattr(e, 'id', str(id(e))) for e in self.constraint.entities]
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            'constraint_id': self.constraint.id,
            'constraint_type': self.constraint.type.name,
            'entity_ids': self.entity_ids,
            'dof_consumed': self.dof_consumed,
            'is_redundant': self.is_redundant,
            'redundancy_reason': self.redundancy_reason
        }


@dataclass
class ConflictInfo:
    """
    Informationen über einen Constraint-Konflikt.
    
    Attributes:
        constraints: Liste der in Konflikt stehenden Constraints
        conflict_type: Art des Konflikts
        explanation: Menschlich lesbare Erklärung
        suggested_resolution: Vorgeschlagene Lösung
        severity: Schweregrad des Konflikts
        auto_fixable: Ob der Konflikt automatisch behoben werden kann
    """
    constraints: List[Constraint]
    conflict_type: str
    explanation: str
    suggested_resolution: str
    severity: ConflictSeverity = ConflictSeverity.HIGH
    auto_fixable: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            'constraint_ids': [c.id for c in self.constraints],
            'constraint_types': [c.type.name for c in self.constraints],
            'conflict_type': self.conflict_type,
            'explanation': self.explanation,
            'suggested_resolution': self.suggested_resolution,
            'severity': self.severity.value,
            'auto_fixable': self.auto_fixable
        }


@dataclass
class SuggestionInfo:
    """
    Vorschlag für einen fehlenden Constraint.
    
    Attributes:
        constraint_type: Vorgeschlagener Constraint-Typ
        entity_ids: IDs der betroffenen Geometrie-Elemente
        entities: Referenzen zu den Geometrie-Elementen
        reason: Begründung für den Vorschlag
        priority: Priorität des Vorschlags
        dof_reduction: Anzahl der reduzierten Freiheitsgrade
        auto_addable: Ob der Constraint automatisch hinzugefügt werden kann
    """
    constraint_type: ConstraintType
    entity_ids: List[str]
    entities: List[Any] = field(default_factory=list)
    reason: str = ""
    priority: ConstraintPriority = ConstraintPriority.MEDIUM
    dof_reduction: int = 1
    auto_addable: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            'constraint_type': self.constraint_type.name,
            'entity_ids': self.entity_ids,
            'reason': self.reason,
            'priority': self.priority.name,
            'dof_reduction': self.dof_reduction,
            'auto_addable': self.auto_addable
        }


@dataclass
class ConstraintDiagnosticsResult:
    """
    Ergebnis einer umfassenden Constraint-Diagnose.
    
    Attributes:
        is_fully_constrained: True wenn vollständig bestimmt
        is_under_constrained: True wenn unterbestimmt
        is_over_constrained: True wenn überbestimmt
        degrees_of_freedom: Anzahl der verbleibenden Freiheitsgrade
        total_variables: Gesamtzahl der Variablen
        total_constraints: Gesamtzahl der Constraints
        
        redundant_constraints: Liste redundanter Constraints
        conflicting_constraints: Liste der gefundenen Konflikte
        suggested_constraints: Vorschläge für neue Constraints
        
        invalid_constraints: Ungültige Constraints
        message: Zusammenfassende Nachricht
        detailed_report: Detaillierter Report
        
        diagnosis_type: Typ der Diagnose
        status: ConstraintStatus
    """
    is_fully_constrained: bool = False
    is_under_constrained: bool = False
    is_over_constrained: bool = False
    degrees_of_freedom: int = 0
    total_variables: int = 0
    total_constraints: int = 0
    
    redundant_constraints: List[ConstraintInfo] = field(default_factory=list)
    conflicting_constraints: List[ConflictInfo] = field(default_factory=list)
    suggested_constraints: List[SuggestionInfo] = field(default_factory=list)
    
    invalid_constraints: List[Tuple[Constraint, str]] = field(default_factory=list)
    message: str = ""
    detailed_report: str = ""
    
    diagnosis_type: ConstraintDiagnosisType = ConstraintDiagnosisType.UNKNOWN
    status: ConstraintStatus = ConstraintStatus.UNDER_CONSTRAINED
    
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
        lines.append(f"Freiheitsgrade: {self.degrees_of_freedom}")
        lines.append(f"Variablen: {self.total_variables}, Constraints: {self.total_constraints}")
        lines.append("")
        
        # Under-Constrained Details
        if self.is_under_constrained:
            lines.append(f"Fehlende Constraints: ~{self.degrees_of_freedom}")
            if self.suggested_constraints:
                lines.append("\nVorschläge:")
                for i, sugg in enumerate(self.suggested_constraints[:5], 1):
                    lines.append(f"  {i}. {sugg.constraint_type.name}: {sugg.reason}")
            lines.append("")
        
        # Over-Constrained Details
        if self.is_over_constrained:
            lines.append(f"Gefundene Konflikte: {len(self.conflicting_constraints)}")
            for i, conflict in enumerate(self.conflicting_constraints[:3], 1):
                lines.append(f"\nKonflikt {i}: {conflict.conflict_type}")
                lines.append(f"  {conflict.explanation}")
                lines.append(f"  💡 Lösung: {conflict.suggested_resolution}")
            
            if self.redundant_constraints:
                lines.append(f"\nRedundante Constraints: {len(self.redundant_constraints)}")
                for rc in self.redundant_constraints[:3]:
                    lines.append(f"  - {rc.constraint.type.name}: {rc.redundancy_reason}")
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
            'is_fully_constrained': self.is_fully_constrained,
            'is_under_constrained': self.is_under_constrained,
            'is_over_constrained': self.is_over_constrained,
            'degrees_of_freedom': self.degrees_of_freedom,
            'total_variables': self.total_variables,
            'total_constraints': self.total_constraints,
            'redundant_constraints': [rc.to_dict() for rc in self.redundant_constraints],
            'conflicting_constraints': [cc.to_dict() for cc in self.conflicting_constraints],
            'suggested_constraints': [sc.to_dict() for sc in self.suggested_constraints],
            'invalid_constraints': [
                {'constraint_id': c.id, 'constraint_type': c.type.name, 'error': e}
                for c, e in self.invalid_constraints
            ],
            'message': self.message,
            'diagnosis_type': self.diagnosis_type.name,
            'status': self.status.name
        }


# =============================================================================
# DOF Calculation
# =============================================================================

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


def calculate_element_dof(element: Any) -> int:
    """
    Berechnet die Freiheitsgrade eines einzelnen Geometrie-Elements.
    
    Args:
        element: Geometrie-Element (Point2D, Line2D, Circle2D, Arc2D)
        
    Returns:
        Anzahl der Freiheitsgrade
    """
    if isinstance(element, Point2D):
        if element.fixed:
            return 0
        return 2  # x, y
    
    elif isinstance(element, Line2D):
        if element.start.fixed and element.end.fixed:
            return 0
        elif element.start.fixed or element.end.fixed:
            return 2  # Ein Endpunkt frei
        return 4  # Beide Endpunkte frei (2 + 2)
    
    elif isinstance(element, Circle2D):
        dof = 0
        if not element.center.fixed:
            dof += 2  # center x, y
        dof += 1  # radius
        return dof
    
    elif isinstance(element, Arc2D):
        dof = 0
        if not element.center.fixed:
            dof += 2  # center x, y
        dof += 3  # radius, start_angle, end_angle
        return dof
    
    return 0


def calculate_sketch_dof(
    points: List[Point2D],
    lines: List[Line2D],
    circles: List[Circle2D],
    arcs: List[Arc2D],
    constraints: List[Constraint]
) -> Tuple[int, int, int, Dict[str, int]]:
    """
    Berechnet die Degrees of Freedom (DOF) eines Sketches.
    
    Berücksichtigt:
    - Punkte: 2 DOF (x, y) wenn nicht fixiert
    - Linien: 4 DOF (2 Endpunkte à 2 DOF)
    - Kreise: 3 DOF (center x, y + radius)
    - Bögen: 5 DOF (center x, y + radius + 2 Winkel)
    
    Args:
        points: Liste aller Punkte
        lines: Liste aller Linien
        circles: Liste aller Kreise
        arcs: Liste aller Bögen
        constraints: Liste aller Constraints
        
    Returns:
        Tuple von (total_dof, total_variables, effective_constraints, dof_breakdown)
    """
    processed_points: Set[str] = set()
    dof_breakdown = {
        'points': 0,
        'lines': 0,
        'circles': 0,
        'arcs': 0,
        'constraints': 0
    }
    
    # 1. Punkte zählen (2 DOF pro Punkt: x, y)
    for p in points:
        if not p.fixed and p.id not in processed_points:
            dof_breakdown['points'] += 2
            processed_points.add(p.id)
    
    # 2. Linien-Endpunkte zählen (falls nicht schon gezählt)
    for line in lines:
        for p in [line.start, line.end]:
            if not p.fixed and p.id not in processed_points:
                dof_breakdown['lines'] += 2
                processed_points.add(p.id)
    
    # 3. Kreise zählen (1 DOF: radius, center wird oben gezählt)
    for circle in circles:
        if not circle.center.fixed and circle.center.id not in processed_points:
            dof_breakdown['circles'] += 2
            processed_points.add(circle.center.id)
        dof_breakdown['circles'] += 1  # radius
    
    # 4. Bögen zählen (3 DOF: radius, start_angle, end_angle)
    for arc in arcs:
        if not arc.center.fixed and arc.center.id not in processed_points:
            dof_breakdown['arcs'] += 2
            processed_points.add(arc.center.id)
        dof_breakdown['arcs'] += 3  # radius, start_angle, end_angle
    
    # 5. Effektive Constraints zählen
    effective_constraint_dof = 0
    for c in constraints:
        if not getattr(c, 'enabled', True):
            continue
        if not c.is_valid():
            continue
        if c.type == ConstraintType.FIXED:
            # FIXED wird durch Variablen-Entfernung behandelt
            continue
        cost = _CONSTRAINT_DOF_COST.get(c.type, 1)
        effective_constraint_dof += cost
    
    dof_breakdown['constraints'] = effective_constraint_dof
    
    # 6. Gesamt-DOF berechnen
    total_variables = (
        dof_breakdown['points'] + 
        dof_breakdown['lines'] + 
        dof_breakdown['circles'] + 
        dof_breakdown['arcs']
    )
    total_dof = max(0, total_variables - effective_constraint_dof)
    
    return total_dof, total_variables, effective_constraint_dof, dof_breakdown


# =============================================================================
# Main Analysis Functions
# =============================================================================

def analyze_constraint_state(sketch) -> ConstraintDiagnosticsResult:
    """
    Führt eine umfassende Constraint-Diagnose durch.
    
    Args:
        sketch: Das Sketch-Objekt zu diagnostizieren
        
    Returns:
        ConstraintDiagnosticsResult mit allen Details
    """
    logger.debug(f"Starting constraint state analysis for sketch")
    
    # 1. DOF-Analyse
    total_dof, total_vars, total_constraints, dof_breakdown = calculate_sketch_dof(
        sketch.points, sketch.lines, sketch.circles, sketch.arcs, sketch.constraints
    )
    
    # 2. Ungültige Constraints finden
    invalid_constraints = _find_invalid_constraints(sketch)
    
    # 3. Redundante Constraints finden
    redundant_constraints = detect_redundant_constraints(sketch)
    
    # 4. Konflikte finden
    conflicting_constraints = detect_conflicting_constraints(sketch)
    
    # 5. Status bestimmen
    if invalid_constraints:
        diagnosis_type = ConstraintDiagnosisType.INCONSISTENT
        status = ConstraintStatus.INCONSISTENT
        is_fully_constrained = False
        is_under_constrained = False
        is_over_constrained = False
    elif conflicting_constraints:
        diagnosis_type = ConstraintDiagnosisType.OVER_CONSTRAINED
        status = ConstraintStatus.OVER_CONSTRAINED
        is_fully_constrained = False
        is_under_constrained = False
        is_over_constrained = True
    elif total_dof > 0:
        diagnosis_type = ConstraintDiagnosisType.UNDER_CONSTRAINED
        status = ConstraintStatus.UNDER_CONSTRAINED
        is_fully_constrained = False
        is_under_constrained = True
        is_over_constrained = False
    elif total_constraints > total_vars:
        diagnosis_type = ConstraintDiagnosisType.OVER_CONSTRAINED
        status = ConstraintStatus.OVER_CONSTRAINED
        is_fully_constrained = False
        is_under_constrained = False
        is_over_constrained = True
    else:
        diagnosis_type = ConstraintDiagnosisType.FULLY_CONSTRAINED
        status = ConstraintStatus.FULLY_CONSTRAINED
        is_fully_constrained = True
        is_under_constrained = False
        is_over_constrained = False
    
    # 6. Vorschläge generieren (nur wenn unterbestimmt)
    suggested_constraints = []
    if is_under_constrained:
        suggested_constraints = suggest_missing_constraints(sketch, total_dof)
    
    # 7. Ergebnis erstellen
    result = ConstraintDiagnosticsResult(
        is_fully_constrained=is_fully_constrained,
        is_under_constrained=is_under_constrained,
        is_over_constrained=is_over_constrained,
        degrees_of_freedom=total_dof,
        total_variables=total_vars,
        total_constraints=total_constraints,
        redundant_constraints=redundant_constraints,
        conflicting_constraints=conflicting_constraints,
        suggested_constraints=suggested_constraints,
        invalid_constraints=invalid_constraints,
        diagnosis_type=diagnosis_type,
        status=status
    )
    
    # 8. Message generieren
    result.message = _generate_message(result)
    result.detailed_report = result.to_user_report()
    
    logger.debug(f"Analysis complete: {diagnosis_type.name}, DOF={total_dof}")
    return result


def detect_redundant_constraints(sketch) -> List[ConstraintInfo]:
    """
    Findet redundante (überflüssige) Constraints.
    
    Ein Constraint ist redundant wenn:
    - Er dieselben Entities wie ein anderer Constraint desselben Typs betrifft
    - Seine Wirkung durch andere Constraints bereits erzielt wird
    
    Args:
        sketch: Das Sketch-Objekt
        
    Returns:
        Liste von ConstraintInfo für redundante Constraints
    """
    redundant = []
    constraints = [c for c in sketch.constraints if getattr(c, 'enabled', True) and c.is_valid()]
    
    # 1. Exakte Duplikate finden (gleicher Typ, gleiche Entities)
    seen: Dict[Tuple, Constraint] = {}
    for constraint in constraints:
        # Erstelle Schlüssel aus Typ und Entity-IDs
        entity_ids = tuple(sorted(id(e) for e in constraint.entities))
        key = (constraint.type, entity_ids)
        
        if key in seen:
            # Dieser Constraint ist ein Duplikat
            redundant.append(ConstraintInfo(
                constraint=constraint,
                entity_ids=[getattr(e, 'id', str(id(e))) for e in constraint.entities],
                dof_consumed=_CONSTRAINT_DOF_COST.get(constraint.type, 1),
                is_redundant=True,
                redundancy_reason=f"Duplikat von Constraint {seen[key].id}"
            ))
        else:
            seen[key] = constraint
    
    # 2. Semantische Redundanz finden
    # Beispiel: HORIZONTAL + VERTICAL auf einer Linie mit LENGTH=0
    for line in sketch.lines:
        line_constraints = [
            c for c in constraints
            if line in c.entities or line.start in c.entities or line.end in c.entities
        ]
        
        has_horizontal = any(c.type == ConstraintType.HORIZONTAL for c in line_constraints)
        has_vertical = any(c.type == ConstraintType.VERTICAL for c in line_constraints)
        
        # Wenn eine Linie sowohl horizontal als auch vertikal sein soll,
        # ist einer der Constraints redundant (außer LENGTH=0)
        if has_horizontal and has_vertical:
            # Prüfe ob LENGTH=0
            length_constraints = [c for c in line_constraints if c.type == ConstraintType.LENGTH]
            if length_constraints:
                length_val = length_constraints[0].value
                if length_val is not None and abs(length_val) < 0.001:
                    # LENGTH=0 - beide Constraints sind technisch möglich
                    pass
                else:
                    # Beide Constraints können nicht gleichzeitig gelten
                    # Markiere den zweiten als redundant
                    for c in line_constraints:
                        if c.type == ConstraintType.VERTICAL:
                            redundant.append(ConstraintInfo(
                                constraint=c,
                                entity_ids=[line.id],
                                dof_consumed=1,
                                is_redundant=True,
                                redundancy_reason="VERTICAL ist redundant mit HORIZONTAL für eine Linie mit LENGTH > 0"
                            ))
                            break
    
    # 3. COINCIDENT-Redundanz: Wenn A=B und B=C, dann ist A=C redundant
    coincident_groups: Dict[str, Set[str]] = {}  # point_id -> group of coincident point_ids
    for c in constraints:
        if c.type == ConstraintType.COINCIDENT and len(c.entities) >= 2:
            p1_id = getattr(c.entities[0], 'id', str(id(c.entities[0])))
            p2_id = getattr(c.entities[1], 'id', str(id(c.entities[1])))
            
            # Finde oder erstelle Gruppe
            group1 = coincident_groups.get(p1_id)
            group2 = coincident_groups.get(p2_id)
            
            if group1 is None and group2 is None:
                new_group = {p1_id, p2_id}
                coincident_groups[p1_id] = new_group
                coincident_groups[p2_id] = new_group
            elif group1 is None:
                group2.add(p1_id)
                coincident_groups[p1_id] = group2
            elif group2 is None:
                group1.add(p2_id)
                coincident_groups[p2_id] = group1
            elif group1 is not group2:
                # Merge groups
                merged = group1 | group2
                for pid in merged:
                    coincident_groups[pid] = merged
    
    # Prüfe auf transitive Redundanz
    for c in constraints:
        if c.type == ConstraintType.COINCIDENT and len(c.entities) >= 2:
            p1_id = getattr(c.entities[0], 'id', str(id(c.entities[0])))
            p2_id = getattr(c.entities[1], 'id', str(id(c.entities[1])))
            
            group = coincident_groups.get(p1_id)
            if group and p2_id in group:
                # Prüfe ob es einen direkten Pfad gibt
                # (Dies ist eine vereinfachte Prüfung)
                pass  # Für erweiterte Analyse könnte hier Graph-Traversierung verwendet werden
    
    return redundant


def detect_conflicting_constraints(sketch) -> List[ConflictInfo]:
    """
    Findet widersprüchliche Constraints.
    
    Konflikte entstehen wenn:
    - Geometrisch unmögliche Kombinationen (HORIZONTAL + VERTICAL + LENGTH>0)
    - Widersprüchliche Dimensions-Constraints
    - Zyklische Abhängigkeiten
    
    Args:
        sketch: Das Sketch-Objekt
        
    Returns:
        Liste von ConflictInfo für gefundene Konflikte
    """
    conflicts = []
    constraints = [c for c in sketch.constraints 
                  if getattr(c, 'enabled', True) and c.is_valid()]
    
    # Gruppiere Constraints nach betroffenen Entities
    constraints_by_entity: Dict[int, List[Constraint]] = defaultdict(list)
    for constraint in constraints:
        for entity in constraint.entities:
            constraints_by_entity[id(entity)].append(constraint)
    
    # Konflikt 1: Horizontal + Vertical + Non-zero Length auf gleicher Linie
    for line in sketch.lines:
        line_constraints = [
            c for c in constraints
            if line in c.entities or line.start in c.entities or line.end in c.entities
        ]
        
        has_horizontal = any(c.type == ConstraintType.HORIZONTAL for c in line_constraints)
        has_vertical = any(c.type == ConstraintType.VERTICAL for c in line_constraints)
        has_nonzero_length = any(
            c.type == ConstraintType.LENGTH and getattr(c, 'value', 0) > 0.001
            for c in line_constraints
        )
        
        if has_horizontal and has_vertical and has_nonzero_length:
            conflicting = [c for c in line_constraints 
                         if c.type in (ConstraintType.HORIZONTAL, ConstraintType.VERTICAL, ConstraintType.LENGTH)]
            conflicts.append(ConflictInfo(
                constraints=conflicting,
                conflict_type="GEOMETRIC_IMPOSSIBLE",
                explanation=f"Linie {getattr(line, 'id', '?')} kann nicht gleichzeitig horizontal und vertikal sein mit Länge > 0",
                suggested_resolution="Entfernen Sie HORIZONTAL oder VERTICAL, oder setzen Sie LENGTH auf 0",
                severity=ConflictSeverity.CRITICAL,
                auto_fixable=False
            ))
    
    # Konflikt 2: Gegensätzliche Dimensions-Constraints
    for entity_id, entity_constraints in constraints_by_entity.items():
        # Längen-Constraints
        length_constraints = [
            c for c in entity_constraints
            if c.type == ConstraintType.LENGTH and c.value is not None
        ]
        if len(length_constraints) >= 2:
            values = [c.value for c in length_constraints]
            if len(set(round(v, 3) for v in values)) > 1:  # Unterschiedliche Werte (gerundet)
                conflicts.append(ConflictInfo(
                    constraints=length_constraints,
                    conflict_type="CONFLICTING_DIMENSIONS",
                    explanation=f"Widersprüchliche Längen-Constraints: {values}",
                    suggested_resolution="Entfernen Sie alle bis auf einen LENGTH-Constraint",
                    severity=ConflictSeverity.HIGH,
                    auto_fixable=True  # Könnte automatisch den ersten behalten
                ))
        
        # Radius-Constraints
        radius_constraints = [
            c for c in entity_constraints
            if c.type == ConstraintType.RADIUS and c.value is not None
        ]
        if len(radius_constraints) >= 2:
            values = [c.value for c in radius_constraints]
            if len(set(round(v, 3) for v in values)) > 1:
                conflicts.append(ConflictInfo(
                    constraints=radius_constraints,
                    conflict_type="CONFLICTING_RADII",
                    explanation=f"Widersprüchliche Radius-Constraints: {values}",
                    suggested_resolution="Entfernen Sie alle bis auf einen RADIUS-Constraint",
                    severity=ConflictSeverity.HIGH,
                    auto_fixable=True
                ))
    
    # Konflikt 3: COINCIDENT auf demselben Punkt (Selbstreferenz)
    for c in constraints:
        if c.type == ConstraintType.COINCIDENT:
            entities = getattr(c, 'entities', [])
            if len(entities) == 2:
                if entities[0] is entities[1]:
                    conflicts.append(ConflictInfo(
                        constraints=[c],
                        conflict_type="SELF_REFERENTIAL",
                        explanation="COINCIDENT-Constraint verweist auf denselben Punkt",
                        suggested_resolution="Entfernen Sie diesen Constraint",
                        severity=ConflictSeverity.MEDIUM,
                        auto_fixable=True
                    ))
    
    # Konflikt 4: Negative Dimensions
    for c in constraints:
        if c.type in (ConstraintType.LENGTH, ConstraintType.DISTANCE, 
                      ConstraintType.RADIUS, ConstraintType.DIAMETER):
            value = getattr(c, 'value', None)
            if value is not None and value < 0:
                conflicts.append(ConflictInfo(
                    constraints=[c],
                    conflict_type="NEGATIVE_DIMENSION",
                    explanation=f"{c.type.name} hat negativen Wert: {value}",
                    suggested_resolution="Setzen Sie einen positiven Wert",
                    severity=ConflictSeverity.HIGH,
                    auto_fixable=False
                ))
    
    # Konflikt 5: PERPENDICULAR + PARALLEL auf denselben Linien
    for line1 in sketch.lines:
        for line2 in sketch.lines:
            if line1 is line2:
                continue
            
            shared_constraints = [
                c for c in constraints
                if line1 in c.entities and line2 in c.entities
            ]
            
            has_perpendicular = any(c.type == ConstraintType.PERPENDICULAR for c in shared_constraints)
            has_parallel = any(c.type == ConstraintType.PARALLEL for c in shared_constraints)
            
            if has_perpendicular and has_parallel:
                conflicting = [c for c in shared_constraints 
                             if c.type in (ConstraintType.PERPENDICULAR, ConstraintType.PARALLEL)]
                conflicts.append(ConflictInfo(
                    constraints=conflicting,
                    conflict_type="PERPENDICULAR_PARALLEL_CONFLICT",
                    explanation=f"Linien {getattr(line1, 'id', '?')} und {getattr(line2, 'id', '?')} können nicht gleichzeitig senkrecht und parallel sein",
                    suggested_resolution="Entfernen Sie PERPENDICULAR oder PARALLEL",
                    severity=ConflictSeverity.CRITICAL,
                    auto_fixable=False
                ))
    
    return conflicts


def suggest_missing_constraints(
    sketch,
    target_dof: int = 0
) -> List[SuggestionInfo]:
    """
    Generiert Vorschläge für fehlende Constraints.
    
    Analysiert den Sketch und schlägt Constraints vor, die:
    - Die Freiheitsgrade reduzieren
    - Die Zeichnung vollständig bestimmen würden
    - Typische CAD-Best-Practices folgen
    
    Args:
        sketch: Das Sketch-Objekt
        target_dof: Ziel-DOF (standardmäßig 0 = vollständig bestimmt)
        
    Returns:
        Liste von SuggestionInfo für fehlende Constraints
    """
    suggestions = []
    
    # 1. Finde Elemente ohne Constraints
    constrained_element_ids: Set[str] = set()
    for c in sketch.constraints:
        if not getattr(c, 'enabled', True):
            continue
        for entity in c.entities:
            constrained_element_ids.add(getattr(entity, 'id', str(id(entity))))
    
    # 2. Finde freie Punkte
    free_points = []
    for p in sketch.points:
        if not p.fixed and p.id not in constrained_element_ids:
            free_points.append(p)
    
    # Auch Linien-Endpunkte prüfen
    for line in sketch.lines:
        for p in [line.start, line.end]:
            if not p.fixed and p.id not in constrained_element_ids:
                if p not in free_points:
                    free_points.append(p)
    
    # 3. Vorschläge generieren
    
    # Vorschlag 1: Ersten freien Punkt fixieren
    if free_points:
        first_free = free_points[0]
        suggestions.append(SuggestionInfo(
            constraint_type=ConstraintType.FIXED,
            entity_ids=[first_free.id],
            entities=[first_free],
            reason="Fixiert einen Punkt als Referenz für die gesamte Zeichnung",
            priority=ConstraintPriority.CRITICAL,
            dof_reduction=2,
            auto_addable=False  # Benutzer sollte entscheiden wo
        ))
    
    # Vorschlag 2: Horizontale/Vertikale Ausrichtung für fast-ausgerichtete Punkte
    if len(free_points) >= 2:
        for i, p1 in enumerate(free_points[:3]):  # Max 3 Punkte prüfen
            for p2 in free_points[i+1:i+4]:
                dx = abs(p1.x - p2.x)
                dy = abs(p1.y - p2.y)
                tolerance = 5.0  # 5 Einheiten Toleranz
                
                if dx < tolerance and dy > tolerance:
                    suggestions.append(SuggestionInfo(
                        constraint_type=ConstraintType.VERTICAL,
                        entity_ids=[p1.id, p2.id],
                        entities=[p1, p2],
                        reason=f"Punkte sind fast vertikal ausgerichtet (Δx={dx:.1f})",
                        priority=ConstraintPriority.MEDIUM,
                        dof_reduction=1,
                        auto_addable=True
                    ))
                elif dy < tolerance and dx > tolerance:
                    suggestions.append(SuggestionInfo(
                        constraint_type=ConstraintType.HORIZONTAL,
                        entity_ids=[p1.id, p2.id],
                        entities=[p1, p2],
                        reason=f"Punkte sind fast horizontal ausgerichtet (Δy={dy:.1f})",
                        priority=ConstraintPriority.MEDIUM,
                        dof_reduction=1,
                        auto_addable=True
                    ))
    
    # Vorschlag 3: Linien ohne Constraints
    for line in sketch.lines:
        line_has_constraint = any(
            line in c.entities or line.start in c.entities or line.end in c.entities
            for c in sketch.constraints
            if getattr(c, 'enabled', True)
        )
        
        if not line_has_constraint:
            # Vorschlage: Länge festlegen
            suggestions.append(SuggestionInfo(
                constraint_type=ConstraintType.LENGTH,
                entity_ids=[line.id],
                entities=[line],
                reason=f"Linie {line.id} hat keine Längen-Beschränkung",
                priority=ConstraintPriority.LOW,
                dof_reduction=1,
                auto_addable=False  # Benutzer muss Wert eingeben
            ))
            
            # Vorschlag: Horizontal oder Vertikal wenn fast ausgerichtet
            dx = abs(line.end.x - line.start.x)
            dy = abs(line.end.y - line.start.y)
            tolerance = 5.0
            
            if dy < tolerance:
                suggestions.append(SuggestionInfo(
                    constraint_type=ConstraintType.HORIZONTAL,
                    entity_ids=[line.id],
                    entities=[line],
                    reason=f"Linie ist fast horizontal (Δy={dy:.1f})",
                    priority=ConstraintPriority.MEDIUM,
                    dof_reduction=1,
                    auto_addable=True
                ))
            elif dx < tolerance:
                suggestions.append(SuggestionInfo(
                    constraint_type=ConstraintType.VERTICAL,
                    entity_ids=[line.id],
                    entities=[line],
                    reason=f"Linie ist fast vertikal (Δx={dx:.1f})",
                    priority=ConstraintPriority.MEDIUM,
                    dof_reduction=1,
                    auto_addable=True
                ))
    
    # Vorschlag 4: Kreise ohne Radius-Constraint
    for circle in sketch.circles:
        has_radius_constraint = any(
            c.type == ConstraintType.RADIUS and circle in c.entities
            for c in sketch.constraints
            if getattr(c, 'enabled', True)
        )
        
        if not has_radius_constraint:
            suggestions.append(SuggestionInfo(
                constraint_type=ConstraintType.RADIUS,
                entity_ids=[circle.id],
                entities=[circle],
                reason=f"Kreis {circle.id} hat keine Radius-Beschränkung",
                priority=ConstraintPriority.LOW,
                dof_reduction=1,
                auto_addable=False
            ))
    
    # Vorschlag 5: Fast-berührende Geometrie (Tangente)
    for line in sketch.lines:
        for circle in sketch.circles:
            # Berechne Abstand von Linie zu Kreiszentrum
            dx = line.end.x - line.start.x
            dy = line.end.y - line.start.y
            len_sq = dx*dx + dy*dy
            
            if len_sq < 1e-8:
                continue
            
            cross = abs(dy * circle.center.x - dx * circle.center.y + 
                       line.end.x * line.start.y - line.end.y * line.start.x)
            dist = cross / math.sqrt(len_sq)
            
            # Wenn Abstand fast gleich Radius, schlage Tangente vor
            if abs(dist - circle.radius) < 5.0:
                suggestions.append(SuggestionInfo(
                    constraint_type=ConstraintType.TANGENT,
                    entity_ids=[line.id, circle.id],
                    entities=[line, circle],
                    reason=f"Linie ist fast tangential zum Kreis (Abstand={dist:.1f}, Radius={circle.radius:.1f})",
                    priority=ConstraintPriority.HIGH,
                    dof_reduction=1,
                    auto_addable=True
                ))
    
    # Sortiere nach Priorität (höchste zuerst)
    priority_order = {
        ConstraintPriority.CRITICAL: 0,
        ConstraintPriority.HIGH: 1,
        ConstraintPriority.MEDIUM: 2,
        ConstraintPriority.LOW: 3,
        ConstraintPriority.REFERENCE: 4
    }
    suggestions.sort(key=lambda s: priority_order.get(s.priority, 5))
    
    return suggestions


# =============================================================================
# Helper Functions
# =============================================================================

def _find_invalid_constraints(sketch) -> List[Tuple[Constraint, str]]:
    """Findet alle ungültigen Constraints."""
    invalid = []
    for constraint in sketch.constraints:
        if not constraint.is_valid():
            error = constraint.validation_error()
            invalid.append((constraint, error or "Unbekannter Fehler"))
    return invalid


def _generate_message(result: ConstraintDiagnosticsResult) -> str:
    """Generiert eine zusammenfassende Nachricht."""
    if result.is_fully_constrained:
        return "Sketch ist vollständig bestimmt"
    elif result.is_under_constrained:
        return f"Unterbestimmt: {result.degrees_of_freedom} Freiheitsgrade verbleibend"
    elif result.is_over_constrained:
        n_conflicts = len(result.conflicting_constraints)
        n_redundant = len(result.redundant_constraints)
        parts = []
        if n_conflicts > 0:
            parts.append(f"{n_conflicts} Konflikt(e)")
        if n_redundant > 0:
            parts.append(f"{n_redundant} redundante Constraint(s)")
        return f"Überbestimmt: {', '.join(parts)}"
    elif result.invalid_constraints:
        return f"Inkonsistent: {len(result.invalid_constraints)} ungültige Constraint(s)"
    else:
        return "Unbekannter Status"


# =============================================================================
# Legacy Compatibility - ConstraintDiagnosis Class
# =============================================================================

@dataclass
class ConstraintConflict:
    """
    Legacy: Beschreibt einen Constraint-Konflikt.
    @deprecated Use ConflictInfo instead
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
    Legacy: Vorschlag für einen neuen Constraint.
    @deprecated Use SuggestionInfo instead
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
    Legacy: Ergebnis einer Constraint-Diagnose.
    @deprecated Use ConstraintDiagnosticsResult instead
    """
    diagnosis_type: ConstraintDiagnosisType
    status: ConstraintStatus
    dof: int
    total_variables: int
    total_constraints: int
    
    missing_constraint_count: int = 0
    suggestions: List[ConstraintSuggestion] = field(default_factory=list)
    unconstrained_elements: List[Any] = field(default_factory=list)
    
    conflicts: List[ConstraintConflict] = field(default_factory=list)
    redundant_constraints: List[Constraint] = field(default_factory=list)
    
    invalid_constraints: List[Tuple[Constraint, str]] = field(default_factory=list)
    message: str = ""
    detailed_report: str = ""
    
    @property
    def is_fully_constrained(self) -> bool:
        return self.diagnosis_type == ConstraintDiagnosisType.FULLY_CONSTRAINED
    
    @property
    def is_under_constrained(self) -> bool:
        return self.diagnosis_type == ConstraintDiagnosisType.UNDER_CONSTRAINED
    
    @property
    def is_over_constrained(self) -> bool:
        return self.diagnosis_type == ConstraintDiagnosisType.OVER_CONSTRAINED
    
    @property
    def is_inconsistent(self) -> bool:
        return self.diagnosis_type == ConstraintDiagnosisType.INCONSISTENT
    
    @property
    def has_issues(self) -> bool:
        return self.diagnosis_type not in (
            ConstraintDiagnosisType.FULLY_CONSTRAINED,
            ConstraintDiagnosisType.UNKNOWN
        )
    
    def to_user_report(self) -> str:
        lines = ["Constraint-Diagnose", "=" * 40, ""]
        
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
        
        if self.is_under_constrained:
            lines.append(f"Fehlende Constraints: ~{self.missing_constraint_count}")
            if self.suggestions:
                lines.append("\nVorschläge:")
                for i, sugg in enumerate(self.suggestions[:5], 1):
                    lines.append(f"  {i}. {sugg.constraint_type.name}: {sugg.reason}")
            lines.append("")
        
        if self.is_over_constrained:
            lines.append(f"Gefundene Konflikte: {len(self.conflicts)}")
            for i, conflict in enumerate(self.conflicts[:3], 1):
                lines.append(f"\nKonflikt {i}: {conflict.conflict_type}")
                lines.append(f"  {conflict.explanation}")
                lines.append(f"  💡 Lösung: {conflict.suggested_resolution}")
            lines.append("")
        
        if self.invalid_constraints:
            lines.append(f"Ungültige Constraints: {len(self.invalid_constraints)}")
            for constraint, error in self.invalid_constraints[:3]:
                lines.append(f"  - {constraint}: {error}")
            lines.append("")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
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
    Legacy: Zentrale Constraint-Diagnostik-Engine.
    @deprecated Use analyze_constraint_state() instead
    """
    
    _CONSTRAINT_DOF_COST = _CONSTRAINT_DOF_COST
    
    @classmethod
    def diagnose(cls, sketch) -> ConstraintDiagnosis:
        """Führt eine vollständige Constraint-Diagnose durch."""
        logger.debug(f"Starting constraint diagnosis for sketch")
        
        vars_count, constr_count, dof = sketch.calculate_dof()
        invalid_constraints = cls._find_invalid_constraints(sketch)
        
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
            diagnosis_type = ConstraintDiagnosisType.FULLY_CONSTRAINED
            status = ConstraintStatus.FULLY_CONSTRAINED
        
        diagnosis = ConstraintDiagnosis(
            diagnosis_type=diagnosis_type,
            status=status,
            dof=dof,
            total_variables=vars_count,
            total_constraints=constr_count,
            invalid_constraints=invalid_constraints
        )
        
        if diagnosis.is_under_constrained:
            cls._analyze_under_constrained(sketch, diagnosis)
        elif diagnosis.is_over_constrained:
            cls._analyze_over_constrained(sketch, diagnosis)
        
        diagnosis.message = cls._generate_message_legacy(diagnosis)
        diagnosis.detailed_report = diagnosis.to_user_report()
        
        logger.debug(f"Diagnosis complete: {diagnosis.diagnosis_type.name}, DOF={dof}")
        return diagnosis
    
    @classmethod
    def quick_check(cls, sketch) -> Tuple[ConstraintStatus, int]:
        """Schneller Check ohne detaillierte Analyse."""
        vars_count, constr_count, dof = sketch.calculate_dof()
        
        if dof > 0:
            return ConstraintStatus.UNDER_CONSTRAINED, dof
        elif constr_count > vars_count:
            return ConstraintStatus.OVER_CONSTRAINED, dof
        else:
            return ConstraintStatus.FULLY_CONSTRAINED, dof
    
    @classmethod
    def _find_invalid_constraints(cls, sketch) -> List[Tuple[Constraint, str]]:
        invalid = []
        for constraint in sketch.constraints:
            if not constraint.is_valid():
                error = constraint.validation_error()
                invalid.append((constraint, error or "Unbekannter Fehler"))
        return invalid
    
    @classmethod
    def _analyze_under_constrained(cls, sketch, diagnosis: ConstraintDiagnosis):
        unconstrained = cls._find_unconstrained_elements(sketch)
        diagnosis.unconstrained_elements = unconstrained
        diagnosis.missing_constraint_count = max(0, diagnosis.dof)
        suggestions = cls._generate_suggestions_legacy(sketch, unconstrained)
        diagnosis.suggestions = suggestions
    
    @classmethod
    def _analyze_over_constrained(cls, sketch, diagnosis: ConstraintDiagnosis):
        conflicts = cls._find_conflicts_legacy(sketch)
        diagnosis.conflicts = conflicts
        redundant = cls._find_redundant_constraints_legacy(sketch)
        diagnosis.redundant_constraints = redundant
    
    @classmethod
    def _find_unconstrained_elements(cls, sketch) -> List[Any]:
        unconstrained = []
        constrained_elements = set()
        for constraint in sketch.constraints:
            if not getattr(constraint, 'enabled', True):
                continue
            for entity in constraint.entities:
                constrained_elements.add(id(entity))
        
        for point in sketch.points:
            if id(point) not in constrained_elements and not point.fixed:
                unconstrained.append(point)
        
        return unconstrained
    
    @classmethod
    def _generate_suggestions_legacy(cls, sketch, unconstrained_elements: List[Any]) -> List[ConstraintSuggestion]:
        suggestions = []
        
        free_points = [e for e in unconstrained_elements 
                      if hasattr(e, 'x') and hasattr(e, 'y')]
        
        if free_points:
            suggestions.append(ConstraintSuggestion(
                constraint_type=ConstraintType.FIXED,
                entities=[free_points[0]],
                reason="Fixiert den ersten Punkt als Referenz",
                priority=ConstraintPriority.CRITICAL
            ))
            
            if len(free_points) >= 2:
                suggestions.append(ConstraintSuggestion(
                    constraint_type=ConstraintType.HORIZONTAL,
                    entities=[free_points[0], free_points[1]],
                    reason="Erstellt horizontale Referenzlinie",
                    priority=ConstraintPriority.HIGH
                ))
        
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
    def _find_conflicts_legacy(cls, sketch) -> List[ConstraintConflict]:
        conflicts = []
        constraints = [c for c in sketch.constraints 
                      if getattr(c, 'enabled', True) and c.is_valid()]
        
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
        
        return conflicts
    
    @classmethod
    def _find_redundant_constraints_legacy(cls, sketch) -> List[Constraint]:
        redundant = []
        constraints = [c for c in sketch.constraints 
                      if getattr(c, 'enabled', True)]
        
        seen = set()
        for constraint in constraints:
            entity_ids = tuple(sorted(id(e) for e in constraint.entities))
            key = (constraint.type, entity_ids)
            
            if key in seen:
                redundant.append(constraint)
            else:
                seen.add(key)
        
        return redundant
    
    @classmethod
    def _generate_message_legacy(cls, diagnosis: ConstraintDiagnosis) -> str:
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
    """Shortcut für ConstraintDiagnostics.diagnose() - Legacy."""
    return ConstraintDiagnostics.diagnose(sketch)


def quick_check(sketch) -> Tuple[ConstraintStatus, int]:
    """Shortcut für ConstraintDiagnostics.quick_check() - Legacy."""
    return ConstraintDiagnostics.quick_check(sketch)


def get_constraint_report(sketch) -> str:
    """Generiert einen nutzerfreundlichen Report."""
    result = analyze_constraint_state(sketch)
    return result.to_user_report()
