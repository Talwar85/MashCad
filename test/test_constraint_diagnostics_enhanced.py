"""
Tests für Enhanced Constraint Diagnostics (Sprint 2)
====================================================

SU-002: Under/Over-Constrained Diagnostics

Testet die neue API mit:
- ConstraintDiagnosticsResult
- ConstraintInfo
- ConflictInfo
- SuggestionInfo
- DOF Calculation
- Redundant Constraint Detection
- Conflict Detection
- Suggestion Generation

Run: pytest test/test_constraint_diagnostics_enhanced.py -v

Author: Kimi (Sprint 2 Implementation)
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass
from typing import List, Tuple

# Skip if dependencies not available
try:
    from sketcher.constraint_diagnostics import (
        # Neue API (Sprint 2)
        analyze_constraint_state,
        detect_redundant_constraints,
        detect_conflicting_constraints,
        suggest_missing_constraints,
        calculate_sketch_dof,
        calculate_element_dof,
        ConstraintDiagnosticsResult,
        ConstraintInfo,
        ConflictInfo,
        SuggestionInfo,
        ConflictSeverity,
        ConstraintDiagnosisType,
        # Legacy API
        ConstraintDiagnostics,
        ConstraintDiagnosis,
        ConstraintConflict,
        ConstraintSuggestion,
        diagnose_sketch,
        quick_check
    )
    from sketcher.constraints import (
        Constraint, ConstraintType, ConstraintStatus, ConstraintPriority,
        make_fixed, make_horizontal, make_vertical, make_length,
        make_coincident, make_parallel, make_perpendicular
    )
    from sketcher.geometry import Point2D, Line2D, Circle2D, Arc2D
    DEPENDENCIES_AVAILABLE = True
except ImportError as e:
    print(f"Import error: {e}")
    DEPENDENCIES_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not DEPENDENCIES_AVAILABLE,
    reason="ConstraintDiagnostics dependencies not available"
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def simple_point():
    """Erstellt einen einfachen Punkt."""
    return Point2D(0, 0)


@pytest.fixture
def simple_line():
    """Erstellt eine einfache Linie."""
    start = Point2D(0, 0)
    end = Point2D(100, 0)
    return Line2D(start, end)


@pytest.fixture
def simple_circle():
    """Erstellt einen einfachen Kreis."""
    center = Point2D(50, 50)
    return Circle2D(center, 25)


@pytest.fixture
def simple_arc():
    """Erstellt einen einfachen Bogen."""
    center = Point2D(50, 50)
    return Arc2D(center, 25, 0, 90)


@pytest.fixture
def empty_sketch():
    """Erstellt ein leeres Mock-Sketch."""
    sketch = Mock()
    sketch.points = []
    sketch.lines = []
    sketch.circles = []
    sketch.arcs = []
    sketch.constraints = []
    sketch.calculate_dof.return_value = (0, 0, 0)
    return sketch


@pytest.fixture
def sketch_with_line(simple_line):
    """Erstellt ein Sketch mit einer Linie."""
    sketch = Mock()
    sketch.points = [simple_line.start, simple_line.end]
    sketch.lines = [simple_line]
    sketch.circles = []
    sketch.arcs = []
    sketch.constraints = []
    sketch.calculate_dof.return_value = (4, 0, 4)  # 4 DOF für 2 Punkte
    return sketch


@pytest.fixture
def fully_constrained_sketch(simple_line):
    """Erstellt ein vollständig bestimmtes Sketch."""
    sketch = Mock()
    sketch.points = [simple_line.start, simple_line.end]
    sketch.lines = [simple_line]
    sketch.circles = []
    sketch.arcs = []
    
    # Constraints erstellen
    fixed_constraint = make_fixed(simple_line.start)
    length_constraint = make_length(simple_line, 100)
    horizontal_constraint = make_horizontal(simple_line)
    
    sketch.constraints = [fixed_constraint, length_constraint, horizontal_constraint]
    sketch.calculate_dof.return_value = (4, 3, 1)  # 1 DOF remaining (end point y)
    return sketch


# =============================================================================
# DOF Calculation Tests
# =============================================================================

class TestDOFCalculation:
    """Tests für Degrees of Freedom Berechnung."""
    
    def test_calculate_element_dof_free_point(self, simple_point):
        """Test DOF für freien Punkt."""
        simple_point.fixed = False
        dof = calculate_element_dof(simple_point)
        assert dof == 2  # x, y
    
    def test_calculate_element_dof_fixed_point(self, simple_point):
        """Test DOF für fixierten Punkt."""
        simple_point.fixed = True
        dof = calculate_element_dof(simple_point)
        assert dof == 0
    
    def test_calculate_element_dof_free_line(self, simple_line):
        """Test DOF für freie Linie."""
        simple_line.start.fixed = False
        simple_line.end.fixed = False
        dof = calculate_element_dof(simple_line)
        assert dof == 4  # 2 Punkte à 2 DOF
    
    def test_calculate_element_dof_half_fixed_line(self, simple_line):
        """Test DOF für teilweise fixierte Linie."""
        simple_line.start.fixed = True
        simple_line.end.fixed = False
        dof = calculate_element_dof(simple_line)
        assert dof == 2  # Nur Endpunkt frei
    
    def test_calculate_element_dof_fully_fixed_line(self, simple_line):
        """Test DOF für vollständig fixierte Linie."""
        simple_line.start.fixed = True
        simple_line.end.fixed = True
        dof = calculate_element_dof(simple_line)
        assert dof == 0
    
    def test_calculate_element_dof_circle(self, simple_circle):
        """Test DOF für Kreis."""
        simple_circle.center.fixed = False
        dof = calculate_element_dof(simple_circle)
        assert dof == 3  # center x, y + radius
    
    def test_calculate_element_dof_fixed_center_circle(self, simple_circle):
        """Test DOF für Kreis mit fixiertem Zentrum."""
        simple_circle.center.fixed = True
        dof = calculate_element_dof(simple_circle)
        assert dof == 1  # Nur radius
    
    def test_calculate_element_dof_arc(self, simple_arc):
        """Test DOF für Bogen."""
        simple_arc.center.fixed = False
        dof = calculate_element_dof(simple_arc)
        assert dof == 5  # center x, y + radius + 2 angles
    
    def test_calculate_sketch_dof_empty(self):
        """Test DOF für leeres Sketch."""
        dof, vars, constr, breakdown = calculate_sketch_dof([], [], [], [], [])
        assert dof == 0
        assert vars == 0
        assert constr == 0
    
    def test_calculate_sketch_dof_with_points(self):
        """Test DOF für Sketch mit Punkten."""
        p1 = Point2D(0, 0)
        p2 = Point2D(100, 100)
        points = [p1, p2]
        
        dof, vars, constr, breakdown = calculate_sketch_dof(points, [], [], [], [])
        
        assert dof == 4  # 2 Punkte à 2 DOF
        assert vars == 4
        assert breakdown['points'] == 4
    
    def test_calculate_sketch_dof_with_line(self):
        """Test DOF für Sketch mit Linie."""
        start = Point2D(0, 0)
        end = Point2D(100, 0)
        line = Line2D(start, end)
        
        dof, vars, constr, breakdown = calculate_sketch_dof([], [line], [], [], [])
        
        assert dof == 4  # 2 Endpunkte à 2 DOF
        assert vars == 4
    
    def test_calculate_sketch_dof_with_constraints(self):
        """Test DOF für Sketch mit Constraints."""
        start = Point2D(0, 0)
        end = Point2D(100, 0)
        line = Line2D(start, end)
        
        # Horizontal constraint
        h_constraint = Constraint(
            type=ConstraintType.HORIZONTAL,
            entities=[line]
        )
        
        dof, vars, constr, breakdown = calculate_sketch_dof(
            [], [line], [], [], [h_constraint]
        )
        
        assert dof == 3  # 4 DOF - 1 constraint
        assert constr == 1
    
    def test_calculate_sketch_dof_fully_constrained(self):
        """Test DOF für vollständig bestimmtes Sketch."""
        start = Point2D(0, 0)
        end = Point2D(100, 0)
        line = Line2D(start, end)
        
        constraints = [
            Constraint(type=ConstraintType.FIXED, entities=[start]),
            Constraint(type=ConstraintType.HORIZONTAL, entities=[line]),
            Constraint(type=ConstraintType.LENGTH, entities=[line], value=100),
        ]
        
        # FIXED wird durch Variablen-Entfernung behandelt
        dof, vars, constr, breakdown = calculate_sketch_dof(
            [], [line], [], [], constraints
        )
        
        # start ist fixed, also 2 vars (end) - 2 constraints (horizontal, length)
        # = 0 DOF
        assert constr == 2  # FIXED zählt nicht


# =============================================================================
# ConstraintInfo Tests
# =============================================================================

class TestConstraintInfo:
    """Tests für ConstraintInfo Dataclass."""
    
    def test_constraint_info_creation(self):
        """Test Erstellung von ConstraintInfo."""
        mock_constraint = Mock()
        mock_constraint.id = "test_123"
        mock_constraint.type = ConstraintType.HORIZONTAL
        mock_entity = Mock()
        mock_entity.id = "entity_456"
        mock_constraint.entities = [mock_entity]
        
        info = ConstraintInfo(
            constraint=mock_constraint,
            dof_consumed=1
        )
        
        assert info.constraint == mock_constraint
        assert info.dof_consumed == 1
        assert info.is_redundant is False
        assert len(info.entity_ids) == 1
    
    def test_constraint_info_redundant(self):
        """Test redundanten ConstraintInfo."""
        mock_constraint = Mock()
        mock_constraint.id = "test_123"
        mock_constraint.type = ConstraintType.HORIZONTAL
        mock_constraint.entities = []
        
        info = ConstraintInfo(
            constraint=mock_constraint,
            is_redundant=True,
            redundancy_reason="Duplicate constraint"
        )
        
        assert info.is_redundant is True
        assert info.redundancy_reason == "Duplicate constraint"
    
    def test_constraint_info_to_dict(self):
        """Test Serialisierung."""
        mock_constraint = Mock()
        mock_constraint.id = "c_123"
        mock_constraint.type = ConstraintType.LENGTH
        mock_constraint.entities = []
        
        info = ConstraintInfo(
            constraint=mock_constraint,
            dof_consumed=1,
            is_redundant=True,
            redundancy_reason="Test"
        )
        
        d = info.to_dict()
        assert d['constraint_id'] == "c_123"
        assert d['constraint_type'] == "LENGTH"
        assert d['is_redundant'] is True


# =============================================================================
# ConflictInfo Tests
# =============================================================================

class TestConflictInfo:
    """Tests für ConflictInfo Dataclass."""
    
    def test_conflict_info_creation(self):
        """Test Erstellung von ConflictInfo."""
        mock_c1 = Mock()
        mock_c2 = Mock()
        
        conflict = ConflictInfo(
            constraints=[mock_c1, mock_c2],
            conflict_type="TEST_CONFLICT",
            explanation="Test explanation",
            suggested_resolution="Test resolution",
            severity=ConflictSeverity.HIGH,
            auto_fixable=True
        )
        
        assert len(conflict.constraints) == 2
        assert conflict.conflict_type == "TEST_CONFLICT"
        assert conflict.severity == ConflictSeverity.HIGH
        assert conflict.auto_fixable is True
    
    def test_conflict_info_default_severity(self):
        """Test Default-Severity."""
        conflict = ConflictInfo(
            constraints=[Mock()],
            conflict_type="TEST",
            explanation="Test",
            suggested_resolution="Fix"
        )
        
        assert conflict.severity == ConflictSeverity.HIGH
        assert conflict.auto_fixable is False
    
    def test_conflict_info_to_dict(self):
        """Test Serialisierung."""
        mock_c = Mock()
        mock_c.id = "c_1"
        mock_c.type = ConstraintType.HORIZONTAL
        
        conflict = ConflictInfo(
            constraints=[mock_c],
            conflict_type="TEST",
            explanation="Test explanation",
            suggested_resolution="Fix it",
            severity=ConflictSeverity.CRITICAL
        )
        
        d = conflict.to_dict()
        assert d['conflict_type'] == "TEST"
        assert d['severity'] == "critical"
        assert 'constraint_ids' in d


# =============================================================================
# SuggestionInfo Tests
# =============================================================================

class TestSuggestionInfo:
    """Tests für SuggestionInfo Dataclass."""
    
    def test_suggestion_info_creation(self):
        """Test Erstellung von SuggestionInfo."""
        mock_entity = Mock()
        mock_entity.id = "e_1"
        
        suggestion = SuggestionInfo(
            constraint_type=ConstraintType.FIXED,
            entity_ids=["e_1"],
            entities=[mock_entity],
            reason="Fix point as reference",
            priority=ConstraintPriority.CRITICAL,
            dof_reduction=2,
            auto_addable=False
        )
        
        assert suggestion.constraint_type == ConstraintType.FIXED
        assert suggestion.priority == ConstraintPriority.CRITICAL
        assert suggestion.dof_reduction == 2
    
    def test_suggestion_info_to_dict(self):
        """Test Serialisierung."""
        suggestion = SuggestionInfo(
            constraint_type=ConstraintType.HORIZONTAL,
            entity_ids=["e_1", "e_2"],
            reason="Align horizontally",
            priority=ConstraintPriority.MEDIUM,
            dof_reduction=1,
            auto_addable=True
        )
        
        d = suggestion.to_dict()
        assert d['constraint_type'] == "HORIZONTAL"
        assert d['dof_reduction'] == 1
        assert d['auto_addable'] is True


# =============================================================================
# ConstraintDiagnosticsResult Tests
# =============================================================================

class TestConstraintDiagnosticsResult:
    """Tests für ConstraintDiagnosticsResult."""
    
    def test_result_properties_fully_constrained(self):
        """Test Properties für vollständig bestimmtes Ergebnis."""
        result = ConstraintDiagnosticsResult(
            is_fully_constrained=True,
            degrees_of_freedom=0,
            total_variables=10,
            total_constraints=10,
            diagnosis_type=ConstraintDiagnosisType.FULLY_CONSTRAINED,
            status=ConstraintStatus.FULLY_CONSTRAINED
        )
        
        assert result.is_fully_constrained is True
        assert result.is_under_constrained is False
        assert result.is_over_constrained is False
    
    def test_result_properties_under_constrained(self):
        """Test Properties für unterbestimmtes Ergebnis."""
        result = ConstraintDiagnosticsResult(
            is_under_constrained=True,
            degrees_of_freedom=3,
            total_variables=10,
            total_constraints=7,
            diagnosis_type=ConstraintDiagnosisType.UNDER_CONSTRAINED,
            status=ConstraintStatus.UNDER_CONSTRAINED
        )
        
        assert result.is_fully_constrained is False
        assert result.is_under_constrained is True
        assert result.degrees_of_freedom == 3
    
    def test_result_properties_over_constrained(self):
        """Test Properties für überbestimmtes Ergebnis."""
        result = ConstraintDiagnosticsResult(
            is_over_constrained=True,
            degrees_of_freedom=0,
            total_variables=10,
            total_constraints=12,
            diagnosis_type=ConstraintDiagnosisType.OVER_CONSTRAINED,
            status=ConstraintStatus.OVER_CONSTRAINED,
            conflicting_constraints=[
                ConflictInfo(
                    constraints=[Mock()],
                    conflict_type="TEST",
                    explanation="Test",
                    suggested_resolution="Fix"
                )
            ]
        )
        
        assert result.is_over_constrained is True
        assert len(result.conflicting_constraints) == 1
    
    def test_result_to_user_report(self):
        """Test Report-Generierung."""
        result = ConstraintDiagnosticsResult(
            is_under_constrained=True,
            degrees_of_freedom=2,
            total_variables=10,
            total_constraints=8,
            diagnosis_type=ConstraintDiagnosisType.UNDER_CONSTRAINED,
            status=ConstraintStatus.UNDER_CONSTRAINED,
            suggested_constraints=[
                SuggestionInfo(
                    constraint_type=ConstraintType.FIXED,
                    entity_ids=["p1"],
                    reason="Fix point"
                )
            ]
        )
        
        report = result.to_user_report()
        assert "Freiheitsgrade" in report or "DOF" in report or "2" in report
    
    def test_result_to_dict(self):
        """Test Serialisierung."""
        result = ConstraintDiagnosticsResult(
            is_fully_constrained=True,
            degrees_of_freedom=0,
            total_variables=10,
            total_constraints=10,
            diagnosis_type=ConstraintDiagnosisType.FULLY_CONSTRAINED,
            status=ConstraintStatus.FULLY_CONSTRAINED
        )
        
        d = result.to_dict()
        assert d['is_fully_constrained'] is True
        assert d['degrees_of_freedom'] == 0
        assert d['diagnosis_type'] == "FULLY_CONSTRAINED"


# =============================================================================
# Redundant Constraint Detection Tests
# =============================================================================

class TestRedundantConstraintDetection:
    """Tests für Erkennung redundanter Constraints."""
    
    def test_detect_exact_duplicates(self, sketch_with_line):
        """Test Erkennung von exakten Duplikaten."""
        line = sketch_with_line.lines[0]
        
        # Zwei identische Constraints
        c1 = Constraint(type=ConstraintType.HORIZONTAL, entities=[line])
        c2 = Constraint(type=ConstraintType.HORIZONTAL, entities=[line])
        
        sketch_with_line.constraints = [c1, c2]
        
        redundant = detect_redundant_constraints(sketch_with_line)
        
        assert len(redundant) >= 1
        assert any(r.constraint.type == ConstraintType.HORIZONTAL for r in redundant)
    
    def test_detect_no_redundant(self, sketch_with_line):
        """Test dass keine falschen Redundanzen erkannt werden."""
        line = sketch_with_line.lines[0]
        
        # Verschiedene Constraints
        c1 = Constraint(type=ConstraintType.HORIZONTAL, entities=[line])
        c2 = Constraint(type=ConstraintType.LENGTH, entities=[line], value=100)
        
        sketch_with_line.constraints = [c1, c2]
        
        redundant = detect_redundant_constraints(sketch_with_line)
        
        assert len(redundant) == 0


# =============================================================================
# Conflict Detection Tests
# =============================================================================

class TestConflictDetection:
    """Tests für Konflikt-Erkennung."""
    
    def test_detect_horizontal_vertical_conflict(self, sketch_with_line):
        """Test Erkennung von Horizontal+Vertical+Length Konflikt."""
        line = sketch_with_line.lines[0]
        
        # Unmögliche Kombination
        h_constraint = Constraint(type=ConstraintType.HORIZONTAL, entities=[line])
        v_constraint = Constraint(type=ConstraintType.VERTICAL, entities=[line])
        l_constraint = Constraint(type=ConstraintType.LENGTH, entities=[line], value=100)
        
        sketch_with_line.constraints = [h_constraint, v_constraint, l_constraint]
        
        conflicts = detect_conflicting_constraints(sketch_with_line)
        
        assert len(conflicts) >= 1
        assert any(c.conflict_type == "GEOMETRIC_IMPOSSIBLE" for c in conflicts)
    
    def test_detect_perpendicular_parallel_conflict(self, sketch_with_line):
        """Test Erkennung von Perpendicular+Parallel Konflikt."""
        line1 = sketch_with_line.lines[0]
        start = Point2D(0, 100)
        end = Point2D(100, 100)
        line2 = Line2D(start, end)
        sketch_with_line.lines = [line1, line2]
        
        # Unmögliche Kombination
        p_constraint = Constraint(type=ConstraintType.PERPENDICULAR, entities=[line1, line2])
        pa_constraint = Constraint(type=ConstraintType.PARALLEL, entities=[line1, line2])
        
        sketch_with_line.constraints = [p_constraint, pa_constraint]
        
        conflicts = detect_conflicting_constraints(sketch_with_line)
        
        assert len(conflicts) >= 1
        assert any("PERPENDICULAR_PARALLEL" in c.conflict_type for c in conflicts)
    
    def test_detect_negative_dimension(self, sketch_with_line):
        """Test Erkennung von negativen Dimensionen."""
        line = sketch_with_line.lines[0]
        
        # Negativer Wert
        l_constraint = Constraint(
            type=ConstraintType.LENGTH,
            entities=[line],
            value=-10.0
        )
        
        sketch_with_line.constraints = [l_constraint]
        
        conflicts = detect_conflicting_constraints(sketch_with_line)
        
        assert len(conflicts) >= 1
        assert any(c.conflict_type == "NEGATIVE_DIMENSION" for c in conflicts)
    
    def test_detect_self_referential_coincident(self, sketch_with_line):
        """Test Erkennung von selbst-referentiellem Coincident."""
        point = sketch_with_line.points[0]
        
        # Selbst-referentiell
        c_constraint = Constraint(
            type=ConstraintType.COINCIDENT,
            entities=[point, point]
        )
        
        sketch_with_line.constraints = [c_constraint]
        
        conflicts = detect_conflicting_constraints(sketch_with_line)
        
        assert len(conflicts) >= 1
        assert any(c.conflict_type == "SELF_REFERENTIAL" for c in conflicts)
    
    def test_no_conflict_valid_constraints(self, sketch_with_line):
        """Test dass gültige Constraints keine Konflikte erzeugen."""
        line = sketch_with_line.lines[0]
        
        # Gültige Constraints
        h_constraint = Constraint(type=ConstraintType.HORIZONTAL, entities=[line])
        l_constraint = Constraint(type=ConstraintType.LENGTH, entities=[line], value=100)
        
        sketch_with_line.constraints = [h_constraint, l_constraint]
        
        conflicts = detect_conflicting_constraints(sketch_with_line)
        
        assert len(conflicts) == 0


# =============================================================================
# Suggestion Generation Tests
# =============================================================================

class TestSuggestionGeneration:
    """Tests für Vorschlags-Generierung."""
    
    def test_suggest_for_free_point(self, empty_sketch, simple_point):
        """Test Vorschläge für freien Punkt."""
        empty_sketch.points = [simple_point]
        
        suggestions = suggest_missing_constraints(empty_sketch)
        
        # Sollte FIXED vorschlagen
        assert any(s.constraint_type == ConstraintType.FIXED for s in suggestions)
    
    def test_suggest_for_unconstrained_line(self, empty_sketch, simple_line):
        """Test Vorschläge für unbeschränkte Linie."""
        empty_sketch.lines = [simple_line]
        empty_sketch.points = [simple_line.start, simple_line.end]
        
        suggestions = suggest_missing_constraints(empty_sketch)
        
        # Sollte LENGTH vorschlagen
        assert any(s.constraint_type == ConstraintType.LENGTH for s in suggestions)
    
    def test_suggest_horizontal_for_almost_horizontal(self, empty_sketch):
        """Test Horizontal-Vorschlag für fast horizontale Linie."""
        # Fast horizontale Linie (dy < 5)
        start = Point2D(0, 0)
        end = Point2D(100, 2)  # dy = 2
        line = Line2D(start, end)
        
        empty_sketch.lines = [line]
        empty_sketch.points = [start, end]
        
        suggestions = suggest_missing_constraints(empty_sketch)
        
        # Sollte HORIZONTAL vorschlagen
        horizontal_suggestions = [s for s in suggestions if s.constraint_type == ConstraintType.HORIZONTAL]
        assert len(horizontal_suggestions) >= 1
        assert horizontal_suggestions[0].auto_addable is True
    
    def test_suggest_vertical_for_almost_vertical(self, empty_sketch):
        """Test Vertical-Vorschlag für fast vertikale Linie."""
        # Fast vertikale Linie (dx < 5)
        start = Point2D(0, 0)
        end = Point2D(2, 100)  # dx = 2
        line = Line2D(start, end)
        
        empty_sketch.lines = [line]
        empty_sketch.points = [start, end]
        
        suggestions = suggest_missing_constraints(empty_sketch)
        
        # Sollte VERTICAL vorschlagen
        vertical_suggestions = [s for s in suggestions if s.constraint_type == ConstraintType.VERTICAL]
        assert len(vertical_suggestions) >= 1
    
    def test_suggest_radius_for_circle(self, empty_sketch, simple_circle):
        """Test Radius-Vorschlag für Kreis ohne Radius-Constraint."""
        empty_sketch.circles = [simple_circle]
        empty_sketch.points = [simple_circle.center]
        
        suggestions = suggest_missing_constraints(empty_sketch)
        
        # Sollte RADIUS vorschlagen
        assert any(s.constraint_type == ConstraintType.RADIUS for s in suggestions)
    
    def test_suggestions_sorted_by_priority(self, empty_sketch):
        """Test dass Vorschläge nach Priorität sortiert sind."""
        # Mehrere freie Punkte
        points = [Point2D(i * 10, i * 10) for i in range(5)]
        empty_sketch.points = points
        
        suggestions = suggest_missing_constraints(empty_sketch)
        
        # Prüfe Sortierung
        priority_order = {
            ConstraintPriority.CRITICAL: 0,
            ConstraintPriority.HIGH: 1,
            ConstraintPriority.MEDIUM: 2,
            ConstraintPriority.LOW: 3,
        }
        
        for i in range(len(suggestions) - 1):
            p1 = priority_order.get(suggestions[i].priority, 5)
            p2 = priority_order.get(suggestions[i + 1].priority, 5)
            assert p1 <= p2


# =============================================================================
# Full Analysis Tests
# =============================================================================

class TestAnalyzeConstraintState:
    """Tests für die vollständige Analyse."""
    
    def test_analyze_empty_sketch(self, empty_sketch):
        """Test Analyse eines leeren Sketches."""
        result = analyze_constraint_state(empty_sketch)
        
        assert isinstance(result, ConstraintDiagnosticsResult)
        assert result.degrees_of_freedom == 0
        assert result.total_variables == 0
        assert result.total_constraints == 0
    
    def test_analyze_under_constrained_sketch(self, sketch_with_line):
        """Test Analyse eines unterbestimmten Sketches."""
        result = analyze_constraint_state(sketch_with_line)
        
        assert result.is_under_constrained is True
        assert result.degrees_of_freedom > 0
        assert len(result.suggested_constraints) > 0
    
    def test_analyze_over_constrained_sketch(self, sketch_with_line):
        """Test Analyse eines überbestimmten Sketches."""
        line = sketch_with_line.lines[0]
        
        # Erzeuge Konflikt
        h_constraint = Constraint(type=ConstraintType.HORIZONTAL, entities=[line])
        v_constraint = Constraint(type=ConstraintType.VERTICAL, entities=[line])
        l_constraint = Constraint(type=ConstraintType.LENGTH, entities=[line], value=100)
        
        sketch_with_line.constraints = [h_constraint, v_constraint, l_constraint]
        
        result = analyze_constraint_state(sketch_with_line)
        
        assert result.is_over_constrained is True
        assert len(result.conflicting_constraints) > 0
    
    def test_analyze_sketch_with_redundant(self, sketch_with_line):
        """Test Analyse mit redundanten Constraints."""
        line = sketch_with_line.lines[0]
        
        # Duplikat
        c1 = Constraint(type=ConstraintType.HORIZONTAL, entities=[line])
        c2 = Constraint(type=ConstraintType.HORIZONTAL, entities=[line])
        
        sketch_with_line.constraints = [c1, c2]
        
        result = analyze_constraint_state(sketch_with_line)
        
        assert len(result.redundant_constraints) >= 1


# =============================================================================
# Legacy Compatibility Tests
# =============================================================================

class TestLegacyCompatibility:
    """Tests für Rückwärtskompatibilität mit alter API."""
    
    def test_legacy_diagnose_sketch(self, empty_sketch):
        """Test legacy diagnose_sketch Funktion."""
        diagnosis = diagnose_sketch(empty_sketch)
        
        assert isinstance(diagnosis, ConstraintDiagnosis)
    
    def test_legacy_quick_check(self, empty_sketch):
        """Test legacy quick_check Funktion."""
        status, dof = quick_check(empty_sketch)
        
        assert isinstance(status, ConstraintStatus)
        assert isinstance(dof, int)
    
    def test_legacy_constraint_diagnosis_properties(self):
        """Test legacy ConstraintDiagnosis Properties."""
        diagnosis = ConstraintDiagnosis(
            diagnosis_type=ConstraintDiagnosisType.FULLY_CONSTRAINED,
            status=ConstraintStatus.FULLY_CONSTRAINED,
            dof=0,
            total_variables=10,
            total_constraints=10
        )
        
        assert diagnosis.is_fully_constrained is True
        assert diagnosis.is_under_constrained is False
        assert diagnosis.is_over_constrained is False
        assert diagnosis.is_inconsistent is False
        assert diagnosis.has_issues is False
    
    def test_legacy_constraint_conflict(self):
        """Test legacy ConstraintConflict."""
        conflict = ConstraintConflict(
            constraints=[Mock()],
            conflict_type="TEST",
            explanation="Test",
            suggested_resolution="Fix"
        )
        
        d = conflict.to_dict()
        assert 'conflict_type' in d
    
    def test_legacy_constraint_suggestion(self):
        """Test legacy ConstraintSuggestion."""
        suggestion = ConstraintSuggestion(
            constraint_type=ConstraintType.FIXED,
            entities=[Mock()],
            reason="Test"
        )
        
        d = suggestion.to_dict()
        assert 'constraint_type' in d


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration Tests mit echten Geometrie-Objekten."""
    
    def test_full_workflow_with_line(self):
        """Test vollständiger Workflow mit einer Linie."""
        # Erstelle Sketch
        start = Point2D(0, 0)
        end = Point2D(100, 0)
        line = Line2D(start, end)
        
        sketch = Mock()
        sketch.points = [start, end]
        sketch.lines = [line]
        sketch.circles = []
        sketch.arcs = []
        sketch.constraints = []
        
        # 1. DOF berechnen
        dof, vars, constr, breakdown = calculate_sketch_dof(
            sketch.points, sketch.lines, sketch.circles, sketch.arcs, sketch.constraints
        )
        assert dof == 4
        
        # 2. Analyse durchführen
        result = analyze_constraint_state(sketch)
        assert result.is_under_constrained is True
        
        # 3. Vorschläge holen
        suggestions = result.suggested_constraints
        assert len(suggestions) > 0
        
        # 4. Constraint hinzufügen
        h_constraint = make_horizontal(line)
        sketch.constraints.append(h_constraint)
        
        # 5. Neu analysieren
        result = analyze_constraint_state(sketch)
        assert result.degrees_of_freedom < 4  # Weniger DOF nach Constraint
    
    def test_conflict_resolution_workflow(self):
        """Test Konflikt-Lösungs-Workflow."""
        # Erstelle Sketch mit Konflikt
        start = Point2D(0, 0)
        end = Point2D(100, 0)
        line = Line2D(start, end)
        
        sketch = Mock()
        sketch.points = [start, end]
        sketch.lines = [line]
        sketch.circles = []
        sketch.arcs = []
        
        # Konflikt erzeugen
        h = make_horizontal(line)
        v = make_vertical(line)
        l = make_length(line, 100)
        sketch.constraints = [h, v, l]
        
        # Konflikte erkennen
        conflicts = detect_conflicting_constraints(sketch)
        assert len(conflicts) > 0
        
        # Konflikt lösen (entferne Vertical)
        sketch.constraints.remove(v)
        
        # Prüfen dass Konflikt gelöst
        conflicts = detect_conflicting_constraints(sketch)
        assert len(conflicts) == 0


# =============================================================================
# SU-003: Enhanced Conflict Explanation Tests
# =============================================================================

@pytest.mark.skipif(
    not DEPENDENCIES_AVAILABLE,
    reason="ConstraintDiagnostics dependencies not available"
)
class TestSU003ConflictExplanations:
    """SU-003: Tests für erweiterte Konflikt-Erklärungen."""
    
    def test_conflict_info_has_resolution_steps(self):
        """Test dass ConflictInfo resolution_steps enthält."""
        from sketcher.constraint_diagnostics import ConflictInfo, ConflictSeverity
        
        conflict = ConflictInfo(
            constraints=[Mock()],
            conflict_type="GEOMETRIC_IMPOSSIBLE",
            explanation="Test explanation",
            suggested_resolution="Test resolution",
            severity=ConflictSeverity.CRITICAL,
            auto_fixable=False,
            resolution_steps=["Schritt 1", "Schritt 2"],
            affected_geometry=["line_1"],
            visual_hint="highlight_line"
        )
        
        assert conflict.resolution_steps == ["Schritt 1", "Schritt 2"]
        assert conflict.affected_geometry == ["line_1"]
        assert conflict.visual_hint == "highlight_line"
    
    def test_conflict_info_to_dict_includes_new_fields(self):
        """Test dass to_dict() die neuen SU-003 Felder enthält."""
        from sketcher.constraint_diagnostics import ConflictInfo, ConflictSeverity
        
        conflict = ConflictInfo(
            constraints=[Mock()],
            conflict_type="TEST_CONFLICT",
            explanation="Test",
            suggested_resolution="Fix",
            severity=ConflictSeverity.HIGH,
            auto_fixable=True,
            resolution_steps=["Step 1", "Step 2"],
            affected_geometry=["geo_1", "geo_2"],
            visual_hint="highlight_elements"
        )
        
        d = conflict.to_dict()
        
        assert 'resolution_steps' in d
        assert d['resolution_steps'] == ["Step 1", "Step 2"]
        assert 'affected_geometry' in d
        assert d['affected_geometry'] == ["geo_1", "geo_2"]
        assert 'visual_hint' in d
        assert d['visual_hint'] == "highlight_elements"
    
    def test_get_conflict_explanation_geometric_impossible(self):
        """Test Template für GEOMETRIC_IMPOSSIBLE."""
        from sketcher.constraint_diagnostics import get_conflict_explanation
        
        template = get_conflict_explanation("GEOMETRIC_IMPOSSIBLE")
        
        assert 'explanation' in template
        assert 'resolution_steps' in template
        assert 'visual_hint' in template
        assert "horizontal" in template['explanation'].lower()
        assert "vertikal" in template['explanation'].lower()
        assert len(template['resolution_steps']) >= 2
    
    def test_get_conflict_explanation_perpendicular_parallel(self):
        """Test Template für PERPENDICULAR_PARALLEL_CONFLICT."""
        from sketcher.constraint_diagnostics import get_conflict_explanation
        
        template = get_conflict_explanation("PERPENDICULAR_PARALLEL_CONFLICT")
        
        assert 'explanation' in template
        assert "rechtwinklig" in template['explanation'].lower() or "90°" in template['explanation']
        assert "parallel" in template['explanation'].lower()
        assert len(template['resolution_steps']) >= 2
    
    def test_get_conflict_explanation_negative_dimension(self):
        """Test Template für NEGATIVE_DIMENSION."""
        from sketcher.constraint_diagnostics import get_conflict_explanation
        
        template = get_conflict_explanation("NEGATIVE_DIMENSION")
        
        assert 'explanation' in template
        assert "positiv" in template['explanation'].lower()
        assert len(template['resolution_steps']) >= 1
    
    def test_get_conflict_explanation_self_referential(self):
        """Test Template für SELF_REFERENTIAL."""
        from sketcher.constraint_diagnostics import get_conflict_explanation
        
        template = get_conflict_explanation("SELF_REFERENTIAL")
        
        assert 'explanation' in template
        assert "COINCIDENT" in template['explanation'] or "koinzident" in template['explanation'].lower()
        assert len(template['resolution_steps']) >= 1
    
    def test_get_conflict_explanation_conflicting_dimensions(self):
        """Test Template für CONFLICTING_DIMENSIONS."""
        from sketcher.constraint_diagnostics import get_conflict_explanation
        
        template = get_conflict_explanation("CONFLICTING_DIMENSIONS")
        
        assert 'explanation' in template
        assert "widersprüchlich" in template['explanation'].lower() or "unterschiedlich" in template['explanation'].lower()
        assert len(template['resolution_steps']) >= 2
    
    def test_get_conflict_explanation_unknown_type(self):
        """Test Fallback für unbekannten Konflikt-Typ."""
        from sketcher.constraint_diagnostics import get_conflict_explanation
        
        template = get_conflict_explanation("UNKNOWN_CONFLICT_TYPE")
        
        assert 'explanation' in template
        assert 'resolution_steps' in template
        assert "Unbekannt" in template['explanation'] or "unbekannt" in template['explanation'].lower()
    
    def test_format_conflict_explanation_with_entities(self):
        """Test format_conflict_explanation mit Entity-Namen."""
        from sketcher.constraint_diagnostics import format_conflict_explanation
        
        explanation = format_conflict_explanation(
            "GEOMETRIC_IMPOSSIBLE",
            entity_names=["Line_1", "Line_2"],
            values=[100, 50]
        )
        
        assert "Line_1" in explanation
        assert "Line_2" in explanation
        assert "100" in explanation
        assert "50" in explanation
    
    def test_conflict_detection_includes_resolution_steps(self):
        """Test dass detect_conflicting_constraints resolution_steps setzt."""
        start = Point2D(0, 0)
        end = Point2D(100, 0)
        line = Line2D(start, end)
        
        sketch = Mock()
        sketch.points = [start, end]
        sketch.lines = [line]
        sketch.circles = []
        sketch.arcs = []
        
        # Konflikt erzeugen: HORIZONTAL + VERTICAL + LENGTH
        h = make_horizontal(line)
        v = make_vertical(line)
        l = make_length(line, 100)
        sketch.constraints = [h, v, l]
        
        conflicts = detect_conflicting_constraints(sketch)
        
        assert len(conflicts) > 0
        conflict = conflicts[0]
        
        # SU-003: Prüfe neue Felder
        assert hasattr(conflict, 'resolution_steps')
        assert len(conflict.resolution_steps) >= 2
        assert hasattr(conflict, 'affected_geometry')
        assert len(conflict.affected_geometry) > 0
        assert hasattr(conflict, 'visual_hint')
    
    def test_conflict_detection_self_referential_includes_resolution(self):
        """Test dass SELF_REFERENTIAL Konflikt resolution_steps enthält."""
        point = Point2D(50, 50)
        
        sketch = Mock()
        sketch.points = [point]
        sketch.lines = []
        sketch.circles = []
        sketch.arcs = []
        
        # Selbstreferenziellen COINCIDENT Constraint erzeugen
        c = make_coincident(point, point)
        sketch.constraints = [c]
        
        conflicts = detect_conflicting_constraints(sketch)
        
        assert len(conflicts) > 0
        conflict = conflicts[0]
        
        assert conflict.conflict_type == "SELF_REFERENTIAL"
        assert hasattr(conflict, 'resolution_steps')
        assert len(conflict.resolution_steps) >= 1
    
    def test_conflict_detection_negative_dimension_includes_resolution(self):
        """Test dass NEGATIVE_DIMENSION Konflikt resolution_steps enthält."""
        start = Point2D(0, 0)
        end = Point2D(100, 0)
        line = Line2D(start, end)
        
        sketch = Mock()
        sketch.points = [start, end]
        sketch.lines = [line]
        sketch.circles = []
        sketch.arcs = []
        
        # Negativen LENGTH Constraint erzeugen
        l = make_length(line, -50)
        sketch.constraints = [l]
        
        conflicts = detect_conflicting_constraints(sketch)
        
        assert len(conflicts) > 0
        conflict = conflicts[0]
        
        assert conflict.conflict_type == "NEGATIVE_DIMENSION"
        assert hasattr(conflict, 'resolution_steps')
        assert len(conflict.resolution_steps) >= 1
    
    def test_conflict_detection_perpendicular_parallel_includes_resolution(self):
        """Test dass PERPENDICULAR_PARALLEL_CONFLICT resolution_steps enthält."""
        start1 = Point2D(0, 0)
        end1 = Point2D(100, 0)
        line1 = Line2D(start1, end1)
        
        start2 = Point2D(0, 0)
        end2 = Point2D(0, 100)
        line2 = Line2D(start2, end2)
        
        sketch = Mock()
        sketch.points = [start1, end1, start2, end2]
        sketch.lines = [line1, line2]
        sketch.circles = []
        sketch.arcs = []
        
        # PERPENDICULAR und PARALLEL auf dieselben Linien
        perp = make_perpendicular(line1, line2)
        par = make_parallel(line1, line2)
        sketch.constraints = [perp, par]
        
        conflicts = detect_conflicting_constraints(sketch)
        
        assert len(conflicts) > 0
        conflict = conflicts[0]
        
        assert conflict.conflict_type == "PERPENDICULAR_PARALLEL_CONFLICT"
        assert hasattr(conflict, 'resolution_steps')
        assert len(conflict.resolution_steps) >= 2
        assert hasattr(conflict, 'affected_geometry')
        assert len(conflict.affected_geometry) == 2


@pytest.mark.skipif(
    not DEPENDENCIES_AVAILABLE,
    reason="ConstraintDiagnostics dependencies not available"
)
class TestConflictExplanationTemplates:
    """SU-003: Tests für ConflictExplanationTemplates Klasse."""
    
    def test_all_templates_have_required_fields(self):
        """Test dass alle Templates die erforderlichen Felder haben."""
        from sketcher.constraint_diagnostics import ConflictExplanationTemplates
        
        template_names = [
            'GEOMETRIC_IMPOSSIBLE',
            'PERPENDICULAR_PARALLEL_CONFLICT',
            'NEGATIVE_DIMENSION',
            'SELF_REFERENTIAL',
            'CONFLICTING_DIMENSIONS',
            'CONFLICTING_RADII',
            'ZERO_LENGTH_LINE',
            'INVALID_ANGLE',
            'OVER_CONSTRAINED_POINT',
            'TANGENT_IMPOSSIBLE'
        ]
        
        for name in template_names:
            template = getattr(ConflictExplanationTemplates, name, None)
            assert template is not None, f"Template {name} nicht gefunden"
            assert 'explanation' in template, f"Template {name} hat kein 'explanation' Feld"
            assert 'resolution_steps' in template, f"Template {name} hat kein 'resolution_steps' Feld"
            assert 'visual_hint' in template, f"Template {name} hat kein 'visual_hint' Feld"
    
    def test_templates_are_german(self):
        """Test dass alle Erklärungen auf Deutsch sind."""
        from sketcher.constraint_diagnostics import ConflictExplanationTemplates
        
        # Deutsche Schlüsselwörter die in den Erklärungen vorkommen sollten
        german_keywords = [
            "kann nicht", "müssen", "entfernen", "hinzufügen",
            "positiv", "negativ", "Wert", "Constraint", "Linie",
            "Punkt", "Winkel", "parallel", "senkrecht"
        ]
        
        template_names = [
            'GEOMETRIC_IMPOSSIBLE',
            'PERPENDICULAR_PARALLEL_CONFLICT',
            'NEGATIVE_DIMENSION',
            'SELF_REFERENTIAL',
            'CONFLICTING_DIMENSIONS'
        ]
        
        for name in template_names:
            template = getattr(ConflictExplanationTemplates, name)
            explanation = template['explanation']
            
            # Mindestens ein deutsches Schlüsselwort sollte vorhanden sein
            has_german = any(kw.lower() in explanation.lower() for kw in german_keywords)
            assert has_german, f"Template {name} scheint nicht auf Deutsch zu sein"
    
    def test_resolution_steps_are_actionable(self):
        """Test dass Resolution Steps aktionsorientiert sind."""
        from sketcher.constraint_diagnostics import ConflictExplanationTemplates
        
        action_keywords = ["Entferne", "ODER", "setze", "prüfe", "ändere", "verschiebe", "Ändere", "Prüfe"]
        
        template_names = [
            'GEOMETRIC_IMPOSSIBLE',
            'PERPENDICULAR_PARALLEL_CONFLICT',
            'NEGATIVE_DIMENSION',
            'SELF_REFERENTIAL',
            'CONFLICTING_DIMENSIONS'
        ]
        
        for name in template_names:
            template = getattr(ConflictExplanationTemplates, name)
            steps = template['resolution_steps']
            
            assert len(steps) >= 1, f"Template {name} hat keine Resolution Steps"
            
            # Mindestens ein Step sollte ein Aktions-Keyword enthalten
            has_action = any(
                any(kw in step for kw in action_keywords)
                for step in steps
            )
            assert has_action, f"Template {name} Steps sind nicht aktionsorientiert"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
