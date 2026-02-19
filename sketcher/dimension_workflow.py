"""
MashCAD Sketcher - Dimension Workflow Helper
=============================================

Phase 2: SU-008 - Dimensions-Workflow für Einsteiger

Bietet einen geführten Workflow für das Bemaßen von Sketches:
- Automatische Vorschlag von sinnvollen Dimensionen
- Visuelle Hilfe zur Auswahl der richtigen Bemaßungsstrategie
- Auto-Dimension für vollständige Bemaßung
- Echtzeit-Validierung der Dimensionierung

Usage:
    from sketcher.dimension_workflow import DimensionWorkflow, DimensionGuide
    
    # Workflow erstellen
    workflow = DimensionWorkflow(sketch)
    
    # Vorschläge erhalten
    suggestions = workflow.get_dimension_suggestions()
    
    # Auto-Dimension anwenden
    workflow.auto_dimension(strategy="minimal")  # oder "full"
    
    # Guide für Einsteiger
    guide = DimensionGuide(sketch)
    next_step = guide.get_next_recommended_step()
    print(f"Empfohlener Schritt: {next_step.description}")

Author: Kimi (SU-008 Implementation)
Date: 2026-02-19
Branch: feature/v1-ux-aiB
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple, Set
from enum import Enum, auto
from collections import defaultdict
import math
from loguru import logger

from .constraints import (
    Constraint, ConstraintType, make_length, make_distance, 
    make_angle, make_radius, make_diameter, make_horizontal,
    make_vertical
)
from .geometry import Point2D, Line2D, Circle2D, Arc2D


class DimensionType(Enum):
    """Arten von Dimensionen."""
    LENGTH = auto()         # Linienlänge
    DISTANCE = auto()       # Punkt-zu-Punkt oder Punkt-zu-Linie
    ANGLE = auto()          # Winkel zwischen Linien
    RADIUS = auto()         # Kreis/Radius-Radius
    DIAMETER = auto()       # Kreis-Durchmesser
    HORIZONTAL = auto()     # Horizontale Position
    VERTICAL = auto()       # Vertikale Position


class DimensionStrategy(Enum):
    """Strategien für Auto-Dimension."""
    MINIMAL = "minimal"         # Minimale notwendige Dimensionen
    FULL = "full"               # Vollständige Bemaßung
    REFERENCE = "reference"     # Nur Referenz-Dimensionen
    SYMMETRIC = "symmetric"     # Symmetriebasierte Bemaßung


@dataclass
class DimensionSuggestion:
    """
    Vorschlag für eine Dimension.
    
    Attributes:
        dimension_type: Art der Dimension
        entities: Zu bemaßende Elemente
        suggested_value: Vorgeschlagener Wert
        reason: Begründung für den Vorschlag
        priority: Priorität (1-10, höher = wichtiger)
        confidence: Konfidenz (0.0-1.0)
    """
    dimension_type: DimensionType
    entities: List[Any]
    suggested_value: Optional[float]
    reason: str
    priority: int = 5
    confidence: float = 0.8
    
    def to_constraint(self) -> Optional[Constraint]:
        """Konvertiert den Vorschlag zu einem Constraint."""
        try:
            if self.dimension_type == DimensionType.LENGTH:
                if len(self.entities) == 1 and isinstance(self.entities[0], Line2D):
                    return make_length(self.entities[0], self.suggested_value or 10.0)
                    
            elif self.dimension_type == DimensionType.DISTANCE:
                if len(self.entities) == 2:
                    return make_distance(self.entities[0], self.entities[1], 
                                       self.suggested_value or 10.0)
                    
            elif self.dimension_type == DimensionType.ANGLE:
                if len(self.entities) == 2:
                    return make_angle(self.entities[0], self.entities[1],
                                    self.suggested_value or 90.0)
                    
            elif self.dimension_type == DimensionType.RADIUS:
                if len(self.entities) == 1 and isinstance(self.entities[0], Circle2D):
                    return make_radius(self.entities[0], self.suggested_value or 5.0)
                    
            elif self.dimension_type == DimensionType.DIAMETER:
                if len(self.entities) == 1 and isinstance(self.entities[0], Circle2D):
                    return make_diameter(self.entities[0], 
                                       (self.suggested_value or 10.0) * 2)
                    
            elif self.dimension_type == DimensionType.HORIZONTAL:
                if len(self.entities) == 1 and isinstance(self.entities[0], Line2D):
                    return make_horizontal(self.entities[0])
                    
            elif self.dimension_type == DimensionType.VERTICAL:
                if len(self.entities) == 1 and isinstance(self.entities[0], Line2D):
                    return make_vertical(self.entities[0])
                    
        except Exception as e:
            logger.warning(f"Failed to create constraint from suggestion: {e}")
            
        return None


@dataclass
class DimensionGuideStep:
    """
    Ein Schritt im Dimension-Guide.
    
    Attributes:
        step_number: Schritt-Nummer
        title: Kurze Überschrift
        description: Detaillierte Beschreibung
        action: Durchzuführende Aktion
        is_completed: Ob der Schritt erledigt ist
        suggestions: Zugehörige Vorschläge
    """
    step_number: int
    title: str
    description: str
    action: str
    is_completed: bool = False
    suggestions: List[DimensionSuggestion] = field(default_factory=list)


@dataclass
class DimensionStatus:
    """
    Status der Dimensionierung eines Sketches.
    
    Attributes:
        total_elements: Gesamtzahl der bemaßbaren Elemente
        dimensioned_count: Anzahl bereits bemaßter Elemente
        missing_count: Fehlende Dimensionen
        is_fully_dimensioned: Ob vollständig bemaßt
        coverage_percentage: Abdeckung in Prozent
        weak_areas: Bereiche mit wenig Bemaßung
    """
    total_elements: int
    dimensioned_count: int
    missing_count: int
    is_fully_dimensioned: bool
    coverage_percentage: float
    weak_areas: List[str] = field(default_factory=list)


class DimensionWorkflow:
    """
    Workflow-Helper für das Bemaßen von Sketches.
    
    Bietet:
    - Intelligente Vorschlags-Generierung
    - Auto-Dimension mit verschiedenen Strategien
    - Status-Überwachung
    - Validierung
    """
    
    def __init__(self, sketch):
        """
        Args:
            sketch: Das Sketch-Objekt
        """
        self.sketch = sketch
        self._analysis_cache = None
        
    def analyze(self) -> Dict[str, Any]:
        """
        Analysiert das Sketch und gibt Informationen zur Dimensionierung.
        
        Returns:
            Dictionary mit Analyse-Ergebnissen
        """
        if self._analysis_cache is not None:
            return self._analysis_cache
            
        analysis = {
            'lines_without_length': [],
            'circles_without_radius': [],
            'arcs_without_radius': [],
            'angles_available': [],
            'distances_available': [],
            'horizontal_candidates': [],
            'vertical_candidates': [],
            'already_dimensioned': []
        }
        
        # Sammle bereits bemaßte Elemente
        dimensioned_elements = set()
        for constraint in self.sketch.constraints:
            if not getattr(constraint, 'enabled', True):
                continue
                
            if constraint.type in (ConstraintType.LENGTH, ConstraintType.HORIZONTAL, 
                                  ConstraintType.VERTICAL):
                for entity in constraint.entities:
                    if isinstance(entity, Line2D):
                        dimensioned_elements.add(id(entity))
                        analysis['already_dimensioned'].append(entity)
                        
            elif constraint.type in (ConstraintType.RADIUS, ConstraintType.DIAMETER):
                for entity in constraint.entities:
                    if isinstance(entity, (Circle2D, Arc2D)):
                        dimensioned_elements.add(id(entity))
                        
            elif constraint.type == ConstraintType.ANGLE:
                if len(constraint.entities) >= 2:
                    key = tuple(sorted([id(e) for e in constraint.entities[:2]]))
                    analysis['already_dimensioned'].append(key)
        
        # Finde Linien ohne Längen-Bemaßung
        for line in self.sketch.lines:
            if id(line) not in dimensioned_elements:
                analysis['lines_without_length'].append(line)
                
        # Finde Kreise ohne Radius
        for circle in self.sketch.circles:
            if id(circle) not in dimensioned_elements:
                analysis['circles_without_radius'].append(circle)
                
        # Finde mögliche Winkel
        for i, line1 in enumerate(self.sketch.lines):
            for line2 in self.sketch.lines[i+1:]:
                # Prüfe ob Linien einen gemeinsamen Punkt haben
                if (line1.start in (line2.start, line2.end) or 
                    line1.end in (line2.start, line2.end)):
                    angle_key = tuple(sorted([id(line1), id(line2)]))
                    if angle_key not in analysis['already_dimensioned']:
                        analysis['angles_available'].append((line1, line2))
        
        # Finde horizontale/vertikale Kandidaten
        for line in self.sketch.lines:
            if id(line) in dimensioned_elements:
                continue
                
            dx = abs(line.end.x - line.start.x)
            dy = abs(line.end.y - line.start.y)
            length = math.sqrt(dx*dx + dy*dy)
            
            if length > 0.001:
                if dy / length < 0.1:  # Fast horizontal
                    analysis['horizontal_candidates'].append(line)
                elif dx / length < 0.1:  # Fast vertical
                    analysis['vertical_candidates'].append(line)
        
        self._analysis_cache = analysis
        return analysis
        
    def get_dimension_suggestions(self, max_suggestions: int = 10) -> List[DimensionSuggestion]:
        """
        Generiert Vorschläge für sinnvolle Dimensionen.
        
        Args:
            max_suggestions: Maximale Anzahl der Vorschläge
            
        Returns:
            Liste von DimensionSuggestion
        """
        analysis = self.analyze()
        suggestions = []
        
        # 1. Horizontale/Vertikale Constraints (hohe Priorität)
        for line in analysis['horizontal_candidates'][:2]:
            suggestions.append(DimensionSuggestion(
                dimension_type=DimensionType.HORIZONTAL,
                entities=[line],
                suggested_value=None,
                reason="Linie ist fast horizontal - HORIZONTAL Constraint empfohlen",
                priority=9,
                confidence=0.95
            ))
            
        for line in analysis['vertical_candidates'][:2]:
            suggestions.append(DimensionSuggestion(
                dimension_type=DimensionType.VERTICAL,
                entities=[line],
                suggested_value=None,
                reason="Linie ist fast vertikal - VERTICAL Constraint empfohlen",
                priority=9,
                confidence=0.95
            ))
        
        # 2. Fixiere ersten Punkt (höchste Priorität für Anfänger)
        if self.sketch.points and not any(
            c.type == ConstraintType.FIXED for c in self.sketch.constraints
        ):
            first_point = self.sketch.points[0]
            suggestions.append(DimensionSuggestion(
                dimension_type=DimensionType.DISTANCE,
                entities=[first_point, first_point],  # Self-reference = FIX
                suggested_value=0,
                reason="Erster Punkt sollte fixiert werden als Referenz",
                priority=10,
                confidence=1.0
            ))
        
        # 3. Längen für unbemaßte Linien
        for line in analysis['lines_without_length'][:5]:
            length = line.length()
            if length > 0.001:
                suggestions.append(DimensionSuggestion(
                    dimension_type=DimensionType.LENGTH,
                    entities=[line],
                    suggested_value=round(length, 2),
                    reason=f"Linie hat aktuelle Länge {length:.2f}",
                    priority=7,
                    confidence=0.9
                ))
        
        # 4. Radien für Kreise
        for circle in analysis['circles_without_radius'][:3]:
            radius = circle.radius
            suggestions.append(DimensionSuggestion(
                dimension_type=DimensionType.RADIUS,
                entities=[circle],
                suggested_value=round(radius, 2),
                reason=f"Kreis hat aktuellen Radius {radius:.2f}",
                priority=7,
                confidence=0.9
            ))
        
        # 5. Winkel für verbundene Linien
        for line1, line2 in analysis['angles_available'][:3]:
            # Berechne aktuellen Winkel
            angle = self._calculate_angle(line1, line2)
            if angle is not None:
                suggestions.append(DimensionSuggestion(
                    dimension_type=DimensionType.ANGLE,
                    entities=[line1, line2],
                    suggested_value=round(angle, 1),
                    reason=f"Aktueller Winkel beträgt {angle:.1f}°",
                    priority=6,
                    confidence=0.8
                ))
        
        # Sortiere nach Priorität
        suggestions.sort(key=lambda s: s.priority, reverse=True)
        
        return suggestions[:max_suggestions]
        
    def auto_dimension(self, strategy: DimensionStrategy = DimensionStrategy.MINIMAL) -> List[Constraint]:
        """
        Wendet Auto-Dimensionierung basierend auf Strategie an.
        
        Args:
            strategy: Zu verwendende Strategie
            
        Returns:
            Liste der erstellten Constraints
        """
        suggestions = self.get_dimension_suggestions(max_suggestions=100)
        created_constraints = []
        
        if strategy == DimensionStrategy.MINIMAL:
            # Nur höchste Prioritäten
            for suggestion in suggestions:
                if suggestion.priority >= 8:
                    constraint = suggestion.to_constraint()
                    if constraint:
                        self.sketch.constraints.append(constraint)
                        created_constraints.append(constraint)
                        
        elif strategy == DimensionStrategy.FULL:
            # Alle sinnvollen Dimensionen
            for suggestion in suggestions:
                if suggestion.priority >= 5:
                    constraint = suggestion.to_constraint()
                    if constraint:
                        self.sketch.constraints.append(constraint)
                        created_constraints.append(constraint)
                        
        elif strategy == DimensionStrategy.REFERENCE:
            # Nur Referenz-Dimensionen (keine treibenden)
            for suggestion in suggestions:
                constraint = suggestion.to_constraint()
                if constraint:
                    constraint.driving = False
                    self.sketch.constraints.append(constraint)
                    created_constraints.append(constraint)
        
        logger.info(f"Auto-dimension created {len(created_constraints)} constraints "
                   f"using {strategy.value} strategy")
        return created_constraints
        
    def get_dimension_status(self) -> DimensionStatus:
        """
        Gibt den aktuellen Status der Dimensionierung zurück.
        
        Returns:
            DimensionStatus
        """
        analysis = self.analyze()
        
        total = (len(self.sketch.lines) + len(self.sketch.circles) + 
                len(self.sketch.arcs))
                
        dimensioned = len(analysis['already_dimensioned'])
        
        # Berechne Abdeckung
        if total > 0:
            coverage = (dimensioned / total) * 100
        else:
            coverage = 100.0
            
        # Identifiziere schwache Bereiche
        weak_areas = []
        if len(analysis['lines_without_length']) > 2:
            weak_areas.append(f"{len(analysis['lines_without_length'])} Linien ohne Länge")
        if len(analysis['circles_without_radius']) > 0:
            weak_areas.append(f"{len(analysis['circles_without_radius'])} Kreise ohne Radius")
        
        return DimensionStatus(
            total_elements=total,
            dimensioned_count=dimensioned,
            missing_count=total - dimensioned,
            is_fully_dimensioned=(total - dimensioned) == 0,
            coverage_percentage=coverage,
            weak_areas=weak_areas
        )
        
    def validate_dimension(self, dimension_type: DimensionType, 
                          entities: List[Any], value: float) -> Tuple[bool, str]:
        """
        Validiert eine geplante Dimension.
        
        Returns:
            (is_valid, message)
        """
        if not entities:
            return False, "Keine Elemente ausgewählt"
            
        if dimension_type == DimensionType.LENGTH:
            if len(entities) != 1 or not isinstance(entities[0], Line2D):
                return False, "LENGTH benötigt genau eine Linie"
            if value <= 0:
                return False, "Länge muss positiv sein"
                
        elif dimension_type == DimensionType.RADIUS:
            if len(entities) != 1 or not isinstance(entities[0], (Circle2D, Arc2D)):
                return False, "RADIUS benötigt einen Kreis oder Bogen"
            if value <= 0:
                return False, "Radius muss positiv sein"
                
        elif dimension_type == DimensionType.ANGLE:
            if len(entities) != 2:
                return False, "ANGLE benötigt zwei Linien"
            if not (0 <= value <= 360):
                return False, "Winkel muss zwischen 0° und 360° liegen"
        
        return True, "Valid"
        
    def _calculate_angle(self, line1: Line2D, line2: Line2D) -> Optional[float]:
        """Berechnet den Winkel zwischen zwei Linien in Grad."""
        try:
            # Richtungsvektoren
            v1 = (line1.end.x - line1.start.x, line1.end.y - line1.start.y)
            v2 = (line2.end.x - line2.start.x, line2.end.y - line2.start.y)
            
            # Längen
            len1 = math.sqrt(v1[0]**2 + v1[1]**2)
            len2 = math.sqrt(v2[0]**2 + v2[1]**2)
            
            if len1 < 0.001 or len2 < 0.001:
                return None
            
            # Normalisiere
            v1 = (v1[0]/len1, v1[1]/len1)
            v2 = (v2[0]/len2, v2[1]/len2)
            
            # Winkel
            dot = v1[0]*v2[0] + v1[1]*v2[1]
            dot = max(-1, min(1, dot))  # Clamp
            angle_rad = math.acos(dot)
            angle_deg = math.degrees(angle_rad)
            
            return angle_deg
        except Exception:
            return None


class DimensionGuide:
    """
    Interaktiver Guide für Einsteiger zum Bemaßen.
    
    Bietet:
    - Schritt-für-Schritt Anleitung
    - Kontext-sensitive Hilfe
    - Fortschritts-Tracking
    """
    
    def __init__(self, sketch):
        """
        Args:
            sketch: Das Sketch-Objekt
        """
        self.sketch = sketch
        self.workflow = DimensionWorkflow(sketch)
        self._completed_steps = set()
        
    def get_all_steps(self) -> List[DimensionGuideStep]:
        """
        Gibt alle Schritte des Guides zurück.
        
        Returns:
            Liste von DimensionGuideStep
        """
        steps = []
        
        # Schritt 1: Referenz fixieren
        has_fixed = any(c.type == ConstraintType.FIXED for c in self.sketch.constraints)
        steps.append(DimensionGuideStep(
            step_number=1,
            title="Referenzpunkt fixieren",
            description="Fixieren Sie einen Punkt als Ausgangspunkt für das Sketch.",
            action="Wählen Sie einen Punkt und wenden Sie FIX an",
            is_completed=has_fixed
        ))
        
        # Schritt 2: Horizontale/Vertikale ausrichten
        analysis = self.workflow.analyze()
        has_orientation = any(
            c.type in (ConstraintType.HORIZONTAL, ConstraintType.VERTICAL)
            for c in self.sketch.constraints
        )
        steps.append(DimensionGuideStep(
            step_number=2,
            title="Grundausrichtung definieren",
            description="Definieren Sie horizontale oder vertikale Linien.",
            action="Wählen Sie nahezu horizontale/vertikale Linien",
            is_completed=has_orientation or len(analysis['horizontal_candidates']) == 0
        ))
        
        # Schritt 3: Basis-Längen
        status = self.workflow.get_dimension_status()
        steps.append(DimensionGuideStep(
            step_number=3,
            title="Basis-Längen bemaßen",
            description="Bemaßen Sie die wichtigsten Linienlängen.",
            action=f"Es fehlen noch {len(analysis['lines_without_length'])} Längen",
            is_completed=len(analysis['lines_without_length']) == 0,
            suggestions=[
                s for s in self.workflow.get_dimension_suggestions() 
                if s.dimension_type == DimensionType.LENGTH
            ][:3]
        ))
        
        # Schritt 4: Winkel
        has_angles = any(c.type == ConstraintType.ANGLE for c in self.sketch.constraints)
        steps.append(DimensionGuideStep(
            step_number=4,
            title="Winkel definieren",
            description="Definieren Sie wichtige Winkel zwischen Linien.",
            action="Wählen Sie zwei verbundene Linien",
            is_completed=has_angles or len(analysis['angles_available']) == 0
        ))
        
        # Schritt 5: Kreise
        has_circle_dims = any(
            c.type in (ConstraintType.RADIUS, ConstraintType.DIAMETER)
            for c in self.sketch.constraints
        )
        steps.append(DimensionGuideStep(
            step_number=5,
            title="Kreis-Abmessungen",
            description="Bemaßen Sie Radien oder Durchmesser von Kreisen.",
            action=f"Es fehlen noch {len(analysis['circles_without_radius'])} Kreis-Dimensionen",
            is_completed=len(analysis['circles_without_radius']) == 0 or has_circle_dims
        ))
        
        # Schritt 6: Vollständigkeit prüfen
        steps.append(DimensionGuideStep(
            step_number=6,
            title="Vollständigkeit prüfen",
            description="Stellen Sie sicher, dass das Sketch vollständig bestimmt ist.",
            action="Prüfen Sie den Constraint-Status",
            is_completed=status.is_fully_dimensioned
        ))
        
        return steps
        
    def get_next_recommended_step(self) -> Optional[DimensionGuideStep]:
        """
        Gibt den nächsten empfohlenen Schritt zurück.
        
        Returns:
            Nächster Schritt oder None wenn alle erledigt
        """
        steps = self.get_all_steps()
        for step in steps:
            if not step.is_completed:
                return step
        return None
        
    def get_progress_percentage(self) -> float:
        """
        Gibt den Fortschritt in Prozent zurück.
        
        Returns:
            Fortschritt 0.0 - 100.0
        """
        steps = self.get_all_steps()
        if not steps:
            return 100.0
            
        completed = sum(1 for s in steps if s.is_completed)
        return (completed / len(steps)) * 100
        
    def mark_step_completed(self, step_number: int):
        """Markiert einen Schritt als erledigt."""
        self._completed_steps.add(step_number)


# =============================================================================
# Convenience Functions
# =============================================================================

def suggest_dimensions(sketch, max_suggestions: int = 10) -> List[DimensionSuggestion]:
    """Shortcut für DimensionWorkflow.get_dimension_suggestions()."""
    workflow = DimensionWorkflow(sketch)
    return workflow.get_dimension_suggestions(max_suggestions)


def auto_dimension_sketch(sketch, strategy: str = "minimal") -> List[Constraint]:
    """Shortcut für DimensionWorkflow.auto_dimension()."""
    workflow = DimensionWorkflow(sketch)
    strategy_enum = DimensionStrategy(strategy)
    return workflow.auto_dimension(strategy_enum)


def get_dimension_guide(sketch) -> DimensionGuide:
    """Shortcut für DimensionGuide Erstellung."""
    return DimensionGuide(sketch)


def is_fully_dimensioned(sketch) -> bool:
    """Prüft ob ein Sketch vollständig bemaßt ist."""
    workflow = DimensionWorkflow(sketch)
    status = workflow.get_dimension_status()
    return status.is_fully_dimensioned
