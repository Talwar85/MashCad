"""
Tests für Constraint Diagnostics
================================

Phase 2: SU-002 + SU-003 - Under/Over-Constrained Diagnostik

Run: pytest test/test_constraint_diagnostics.py -v
"""

import pytest
from unittest.mock import Mock, MagicMock

# Skip if dependencies not available
try:
    from sketcher.constraint_diagnostics import (
        ConstraintDiagnostics, ConstraintDiagnosis, ConstraintDiagnosisType,
        ConstraintConflict, ConstraintSuggestion, diagnose_sketch, quick_check
    )
    from sketcher.constraints import Constraint, ConstraintType, ConstraintStatus, ConstraintPriority
    DEPENDENCIES_AVAILABLE = True
except ImportError:
    DEPENDENCIES_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not DEPENDENCIES_AVAILABLE,
    reason="ConstraintDiagnostics dependencies not available"
)


class TestConstraintConflict:
    """Tests für ConstraintConflict."""
    
    def test_conflict_creation(self):
        """Test Erstellung eines Konflikts."""
        mock_c1 = Mock()
        mock_c2 = Mock()
        
        conflict = ConstraintConflict(
            constraints=[mock_c1, mock_c2],
            conflict_type="TEST_CONFLICT",
            explanation="Test explanation",
            suggested_resolution="Test resolution",
            severity=ConstraintPriority.HIGH
        )
        
        assert len(conflict.constraints) == 2
        assert conflict.conflict_type == "TEST_CONFLICT"
        assert conflict.severity == ConstraintPriority.HIGH
        
    def test_conflict_to_dict(self):
        """Test Serialisierung."""
        conflict = ConstraintConflict(
            constraints=[Mock()],
            conflict_type="TEST",
            explanation="Test",
            suggested_resolution="Fix it"
        )
        
        d = conflict.to_dict()
        assert d['conflict_type'] == "TEST"
        assert d['explanation'] == "Test"


class TestConstraintSuggestion:
    """Tests für ConstraintSuggestion."""
    
    def test_suggestion_creation(self):
        """Test Erstellung eines Vorschlags."""
        mock_entity = Mock()
        
        suggestion = ConstraintSuggestion(
            constraint_type=ConstraintType.FIXED,
            entities=[mock_entity],
            reason="Test reason",
            priority=ConstraintPriority.CRITICAL
        )
        
        assert suggestion.constraint_type == ConstraintType.FIXED
        assert suggestion.priority == ConstraintPriority.CRITICAL


class TestConstraintDiagnosis:
    """Tests für ConstraintDiagnosis."""
    
    def test_diagnosis_properties(self):
        """Test Diagnose-Properties."""
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
        assert diagnosis.has_issues is False
        
    def test_under_constrained_properties(self):
        """Test Under-Constrained Properties."""
        diagnosis = ConstraintDiagnosis(
            diagnosis_type=ConstraintDiagnosisType.UNDER_CONSTRAINED,
            status=ConstraintStatus.UNDER_CONSTRAINED,
            dof=3,
            total_variables=10,
            total_constraints=7
        )
        
        assert diagnosis.is_fully_constrained is False
        assert diagnosis.is_under_constrained is True
        assert diagnosis.has_issues is True
        
    def test_over_constrained_properties(self):
        """Test Over-Constrained Properties."""
        diagnosis = ConstraintDiagnosis(
            diagnosis_type=ConstraintDiagnosisType.OVER_CONSTRAINED,
            status=ConstraintStatus.OVER_CONSTRAINED,
            dof=0,
            total_variables=10,
            total_constraints=12
        )
        
        assert diagnosis.is_over_constrained is True
        assert diagnosis.has_issues is True
        
    def test_to_user_report(self):
        """Test Report-Generierung."""
        diagnosis = ConstraintDiagnosis(
            diagnosis_type=ConstraintDiagnosisType.UNDER_CONSTRAINED,
            status=ConstraintStatus.UNDER_CONSTRAINED,
            dof=2,
            total_variables=10,
            total_constraints=8,
            missing_constraint_count=2,
            suggestions=[
                ConstraintSuggestion(
                    constraint_type=ConstraintType.FIXED,
                    entities=[Mock()],
                    reason="Fix point"
                )
            ]
        )
        
        report = diagnosis.to_user_report()
        assert "Unterbestimmt" in report or "Under" in report
        assert "2" in report  # DOF count


class TestConstraintDiagnostics:
    """Tests für ConstraintDiagnostics Engine."""
    
    def test_diagnose_fully_constrained(self):
        """Test Diagnose für vollständig bestimmtes Sketch."""
        # Mock Sketch
        mock_sketch = Mock()
        mock_sketch.calculate_dof.return_value = (10, 10, 0)  # vars, constr, dof
        mock_sketch.constraints = []
        mock_sketch.points = []
        mock_sketch.lines = []
        mock_sketch.circles = []
        mock_sketch.arcs = []
        
        diagnosis = ConstraintDiagnostics.diagnose(mock_sketch)
        
        assert diagnosis.diagnosis_type == ConstraintDiagnosisType.FULLY_CONSTRAINED
        assert diagnosis.dof == 0
        
    def test_diagnose_under_constrained(self):
        """Test Diagnose für unterbestimmtes Sketch."""
        mock_sketch = Mock()
        mock_sketch.calculate_dof.return_value = (10, 7, 3)  # 3 DOF missing
        mock_sketch.constraints = []
        mock_sketch.points = []
        mock_sketch.lines = []
        mock_sketch.circles = []
        mock_sketch.arcs = []
        
        diagnosis = ConstraintDiagnostics.diagnose(mock_sketch)
        
        assert diagnosis.diagnosis_type == ConstraintDiagnosisType.UNDER_CONSTRAINED
        assert diagnosis.dof == 3
        assert diagnosis.missing_constraint_count == 3
        
    def test_diagnose_over_constrained(self):
        """Test Diagnose für überbestimmtes Sketch."""
        mock_sketch = Mock()
        mock_sketch.calculate_dof.return_value = (10, 12, 0)  # More constraints than vars
        mock_sketch.constraints = []
        mock_sketch.points = []
        mock_sketch.lines = []
        mock_sketch.circles = []
        mock_sketch.arcs = []
        
        diagnosis = ConstraintDiagnostics.diagnose(mock_sketch)
        
        assert diagnosis.diagnosis_type == ConstraintDiagnosisType.OVER_CONSTRAINED
        
    def test_quick_check(self):
        """Test schneller Check."""
        mock_sketch = Mock()
        mock_sketch.calculate_dof.return_value = (10, 10, 0)
        
        status, dof = ConstraintDiagnostics.quick_check(mock_sketch)
        
        assert status == ConstraintStatus.FULLY_CONSTRAINED
        assert dof == 0
        
    def test_find_invalid_constraints(self):
        """Test Finden ungültiger Constraints."""
        # Gültiger Constraint
        valid_constraint = Mock()
        valid_constraint.is_valid.return_value = True
        
        # Ungültiger Constraint
        invalid_constraint = Mock()
        invalid_constraint.is_valid.return_value = False
        invalid_constraint.validation_error.return_value = "Missing entities"
        
        mock_sketch = Mock()
        mock_sketch.constraints = [valid_constraint, invalid_constraint]
        mock_sketch.calculate_dof.return_value = (10, 10, 0)
        mock_sketch.points = []
        mock_sketch.lines = []
        mock_sketch.circles = []
        mock_sketch.arcs = []
        
        diagnosis = ConstraintDiagnostics.diagnose(mock_sketch)
        
        assert len(diagnosis.invalid_constraints) == 1
        assert diagnosis.invalid_constraints[0][0] == invalid_constraint


class TestConflictDetection:
    """Tests für Konflikt-Erkennung."""
    
    def test_horizontal_vertical_conflict(self):
        """Test Erkennung von Horizontal+Vertical Konflikt."""
        # Erstelle Mock-Linie
        mock_line = Mock()
        
        # Horizontal Constraint
        h_constraint = Mock()
        h_constraint.type = ConstraintType.HORIZONTAL
        h_constraint.entities = [mock_line]
        h_constraint.enabled = True
        
        # Vertical Constraint
        v_constraint = Mock()
        v_constraint.type = ConstraintType.VERTICAL
        v_constraint.entities = [mock_line]
        v_constraint.enabled = True
        
        # Length Constraint mit positivem Wert
        l_constraint = Mock()
        l_constraint.type = ConstraintType.LENGTH
        l_constraint.entities = [mock_line]
        l_constraint.value = 10.0
        l_constraint.enabled = True
        
        mock_sketch = Mock()
        mock_sketch.lines = [mock_line]
        mock_sketch.constraints = [h_constraint, v_constraint, l_constraint]
        mock_sketch.calculate_dof.return_value = (10, 10, 0)
        mock_sketch.points = []
        mock_sketch.circles = []
        mock_sketch.arcs = []
        
        # Prüfe auf Konflikte
        conflicts = ConstraintDiagnostics._find_conflicts(mock_sketch)
        
        # Sollte mindestens einen Konflikt finden
        assert len(conflicts) >= 1
        assert any(c.conflict_type == "GEOMETRIC_IMPOSSIBLE" for c in conflicts)


class TestSuggestionGeneration:
    """Tests für Vorschlags-Generierung."""
    
    def test_suggestions_for_free_points(self):
        """Test Vorschläge für freie Punkte."""
        mock_point = Mock()
        mock_point.x = 0
        mock_point.y = 0
        mock_point.fixed = False
        
        mock_sketch = Mock()
        mock_sketch.points = [mock_point]
        mock_sketch.lines = []
        mock_sketch.constraints = []
        
        unconstrained = [mock_point]
        suggestions = ConstraintDiagnostics._generate_suggestions(mock_sketch, unconstrained)
        
        # Sollte FIX-Vorschlag enthalten
        assert any(s.constraint_type == ConstraintType.FIXED for s in suggestions)


class TestConvenienceFunctions:
    """Tests für Convenience-Funktionen."""
    
    def test_diagnose_sketch(self):
        """Test diagnose_sketch Shortcut."""
        mock_sketch = Mock()
        mock_sketch.calculate_dof.return_value = (10, 10, 0)
        mock_sketch.constraints = []
        mock_sketch.points = []
        mock_sketch.lines = []
        mock_sketch.circles = []
        mock_sketch.arcs = []
        
        diagnosis = diagnose_sketch(mock_sketch)
        
        assert isinstance(diagnosis, ConstraintDiagnosis)
        
    def test_quick_check_function(self):
        """Test quick_check Shortcut."""
        mock_sketch = Mock()
        mock_sketch.calculate_dof.return_value = (10, 8, 2)
        
        status, dof = quick_check(mock_sketch)
        
        assert status == ConstraintStatus.UNDER_CONSTRAINED
        assert dof == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
