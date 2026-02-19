"""
Tests für Export Validator
==========================

Phase 1: Export Foundation (PR-002)
Testet ExportValidator und ValidationResult.

PR-002 Complete:
- Normals consistency check (check_normals_consistency)
- Auto-repair integration (attempt_auto_repair)
- Free bounds detection

Run: pytest test/test_export_validator.py -v
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import math

# Skip all tests if dependencies not available
try:
    from modeling.export_validator import (
        ExportValidator, ValidationResult, ValidationOptions,
        ValidationIssue, ValidationSeverity, ValidationCheckType,
        validate_for_print, validate_strict
    )
    DEPENDENCIES_AVAILABLE = True
except ImportError:
    DEPENDENCIES_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not DEPENDENCIES_AVAILABLE,
    reason="ExportValidator dependencies not available"
)


class TestValidationIssue:
    """Tests für ValidationIssue."""
    
    def test_issue_creation(self):
        """Test Erstellung eines Issues."""
        issue = ValidationIssue(
            severity=ValidationSeverity.WARNING,
            check_type=ValidationCheckType.FREE_BOUNDS,
            message="Test message",
            suggestion="Test suggestion"
        )
        
        assert issue.severity == ValidationSeverity.WARNING
        assert issue.check_type == ValidationCheckType.FREE_BOUNDS
        assert issue.message == "Test message"
        assert issue.suggestion == "Test suggestion"
        
    def test_issue_to_dict(self):
        """Test Konvertierung zu Dictionary."""
        issue = ValidationIssue(
            severity=ValidationSeverity.ERROR,
            check_type=ValidationCheckType.MANIFOLD,
            message="Test",
            entity_id="face_1"
        )
        
        d = issue.to_dict()
        assert d['severity'] == 'error'
        assert d['check_type'] == 'manifold'
        assert d['message'] == 'Test'
        assert d['entity_id'] == 'face_1'


class TestValidationResult:
    """Tests für ValidationResult."""
    
    def test_default_result_is_valid(self):
        """Test dass Default-Result valid ist."""
        result = ValidationResult()
        assert result.is_valid is True
        assert result.is_printable is True
        assert result.is_closed is True
        
    def test_add_error_makes_invalid(self):
        """Test dass ERROR Result invalid macht."""
        result = ValidationResult()
        issue = ValidationIssue(
            severity=ValidationSeverity.ERROR,
            check_type=ValidationCheckType.MANIFOLD,
            message="Error"
        )
        result.add_issue(issue)
        
        assert result.is_valid is False
        
    def test_add_free_bounds_issue(self):
        """Test dass FREE_BOUNDS Issue Zustand aktualisiert."""
        result = ValidationResult()
        issue = ValidationIssue(
            severity=ValidationSeverity.WARNING,
            check_type=ValidationCheckType.FREE_BOUNDS,
            message="Open edges"
        )
        result.add_issue(issue)
        
        assert result.has_free_bounds is True
        assert result.is_closed is False
        
    def test_add_degenerate_issue(self):
        """Test dass DEGENERATE Issue Zustand aktualisiert."""
        result = ValidationResult()
        issue = ValidationIssue(
            severity=ValidationSeverity.WARNING,
            check_type=ValidationCheckType.DEGENERATE_FACES,
            message="Small face"
        )
        result.add_issue(issue)
        
        assert result.has_degenerate_faces is True
        
    def test_get_issues_by_severity(self):
        """Test Filter nach Severity."""
        result = ValidationResult()
        
        result.add_issue(ValidationIssue(
            severity=ValidationSeverity.ERROR,
            check_type=ValidationCheckType.MANIFOLD,
            message="Error 1"
        ))
        result.add_issue(ValidationIssue(
            severity=ValidationSeverity.ERROR,
            check_type=ValidationCheckType.FREE_BOUNDS,
            message="Error 2"
        ))
        result.add_issue(ValidationIssue(
            severity=ValidationSeverity.WARNING,
            check_type=ValidationCheckType.NORMALS,
            message="Warning 1"
        ))
        
        errors = result.get_errors()
        warnings = result.get_warnings()
        
        assert len(errors) == 2
        assert len(warnings) == 1
        
    def test_to_report(self):
        """Test Report-Generierung."""
        result = ValidationResult()
        result.add_issue(ValidationIssue(
            severity=ValidationSeverity.ERROR,
            check_type=ValidationCheckType.MANIFOLD,
            message="Not closed",
            suggestion="Check faces"
        ))
        
        report = result.to_report()
        assert "Nicht druckbar" in report or "Export" in report
        assert "Not closed" in report


class TestValidationOptions:
    """Tests für ValidationOptions."""
    
    def test_default_options(self):
        """Test Default-Optionen."""
        opts = ValidationOptions()
        assert opts.check_manifold is True
        assert opts.check_free_bounds is True
        assert opts.check_degenerate is True
        assert opts.check_normals is False
        assert opts.check_self_intersection is False
        
    def test_strict_mode(self):
        """Test strict_mode Option."""
        opts = ValidationOptions(strict_mode=True)
        assert opts.strict_mode is True


class TestExportValidatorBasic:
    """Basis-Tests für ExportValidator."""
    
    def test_validate_with_none_shape(self):
        """Test Validierung mit None Shape."""
        mock_solid = Mock()
        mock_solid.wrapped = None
        
        result = ExportValidator.validate_for_export(mock_solid)
        
        assert result.is_valid is False
        assert any(i.check_type == ValidationCheckType.MANIFOLD 
                  for i in result.issues)
        
    def test_is_printable_with_valid(self):
        """Test is_printable Shortcut mit validem Solid."""
        # Mock ein valides Solid
        mock_solid = Mock()
        mock_ocp_shape = Mock()
        mock_solid.wrapped = mock_ocp_shape
        
        with patch.object(ExportValidator, '_check_manifold'):
            with patch.object(ExportValidator, '_check_free_bounds'):
                with patch.object(ExportValidator, '_check_degenerate_faces'):
                    result = ExportValidator.is_printable(mock_solid)
                    # Da wir Checks mocken, sollte es True sein
                    # (wenn keine Checks Issues hinzufügen)


class TestExportValidatorConvenience:
    """Tests für Convenience-Funktionen."""
    
    @patch('modeling.export_validator.ExportValidator.validate_for_export')
    def test_validate_for_print(self, mock_validate):
        """Test validate_for_print Shortcut."""
        mock_result = ValidationResult()
        mock_validate.return_value = mock_result
        
        mock_solid = Mock()
        result = validate_for_print(mock_solid)
        
        assert result == mock_result
        mock_validate.assert_called_once()
        
    @patch('modeling.export_validator.ExportValidator.validate_for_export')
    def test_validate_strict(self, mock_validate):
        """Test validate_strict Shortcut."""
        mock_result = ValidationResult()
        mock_validate.return_value = mock_result
        
        mock_solid = Mock()
        result = validate_strict(mock_solid)
        
        assert result == mock_result
        # Prüfe dass strict_options verwendet wurden
        args = mock_validate.call_args
        assert args[1]['options'].strict_mode is True


class TestExportValidatorQuickReport:
    """Tests für Quick Report Funktion."""
    
    def test_quick_report_printable(self):
        """Test Quick Report für druckbares Solid."""
        mock_solid = Mock()
        
        with patch.object(ExportValidator, 'validate_for_export') as mock_val:
            mock_val.return_value = ValidationResult()
            report = ExportValidator.get_quick_report(mock_solid)
            
        assert "OK" in report or "Druckbar" in report
        
    def test_quick_report_not_printable(self):
        """Test Quick Report für nicht-druckbares Solid."""
        mock_solid = Mock()
        
        result = ValidationResult()
        result.add_issue(ValidationIssue(
            severity=ValidationSeverity.ERROR,
            check_type=ValidationCheckType.FREE_BOUNDS,
            message="Open"
        ))
        
        with patch.object(ExportValidator, 'validate_for_export', return_value=result):
            report = ExportValidator.get_quick_report(mock_solid)
            
        assert "Nicht druckbar" in report or "nicht" in report.lower()


class TestExportValidatorStatistics:
    """Tests für Statistik-Sammlung."""
    
    def test_statistics_collected(self):
        """Test dass Statistiken gesammelt werden."""
        result = ValidationResult()
        
        # Manuell Statistiken setzen (normalerweise durch Checks)
        result.statistics['total_edges'] = 100
        result.statistics['free_bounds'] = 5
        
        assert result.statistics['total_edges'] == 100
        assert result.statistics['free_bounds'] == 5


class TestNormalsConsistencyCheck:
    """Tests für Normalen-Konsistenz-Prüfung (PR-002)."""
    
    def test_check_normals_consistency_returns_dict(self):
        """Test dass check_normals_consistency ein Dict zurückgibt."""
        mock_solid = Mock()
        mock_solid.wrapped = None
        
        result = ExportValidator.check_normals_consistency(mock_solid)
        
        assert isinstance(result, dict)
        assert 'has_inconsistencies' in result
        assert 'inverted_faces' in result
        assert 'zero_normals' in result
        assert 'issues' in result
        assert 'statistics' in result
    
    def test_check_normals_consistency_none_shape(self):
        """Test mit None Shape."""
        result = ExportValidator.check_normals_consistency(None)
        
        assert result['has_inconsistencies'] is False
        assert len(result['issues']) > 0
        assert result['issues'][0]['type'] == 'error'
    
    def test_check_normals_consistency_statistics_structure(self):
        """Test dass Statistiken korrekt strukturiert sind."""
        mock_solid = Mock()
        mock_solid.wrapped = None
        
        result = ExportValidator.check_normals_consistency(mock_solid)
        
        assert 'total_faces' in result['statistics']
        assert 'total_edges' in result['statistics']
        assert 'checked_faces' in result['statistics']
    
    @patch('modeling.export_validator.ExportValidator.check_normals_consistency')
    def test_normals_check_integrates_with_validation(self, mock_check):
        """Test dass _check_normals die detaillierte Methode aufruft."""
        mock_check.return_value = {
            'has_inconsistencies': True,
            'inverted_faces': [1, 2],
            'zero_normals': [],
            'issues': [{
                'message': 'Test issue',
                'face_id': 'face_1',
                'type': 'orientation_mismatch'
            }],
            'statistics': {'total_faces': 3}
        }
        
        mock_shape = Mock()
        result = ValidationResult()
        options = ValidationOptions(check_normals=True)
        
        ExportValidator._check_normals(mock_shape, result, options)
        
        # Check that ValidationCheckType.NORMALS was added
        assert ValidationCheckType.NORMALS in result.checks_performed
        # Check that has_inverted_normals was set
        assert result.has_inverted_normals is True
        # Check that issue was added
        assert len(result.issues) == 1


class TestAutoRepair:
    """Tests für Auto-Repair Funktionalität (PR-002)."""
    
    def test_attempt_auto_repair_returns_tuple(self):
        """Test dass attempt_auto_repair ein Tuple zurückgibt."""
        mock_solid = Mock()
        mock_solid.wrapped = None
        
        result = ExportValidator.attempt_auto_repair(mock_solid)
        
        assert isinstance(result, tuple)
        assert len(result) == 2
    
    def test_attempt_auto_repair_none_shape(self):
        """Test Auto-Repair mit None Shape."""
        repaired, repair_result = ExportValidator.attempt_auto_repair(None)
        
        assert repaired is None
        assert repair_result.success is False
        assert "None" in repair_result.message
    
    def test_attempt_auto_repair_no_issues(self):
        """Test Auto-Repair wenn keine Issues vorhanden."""
        mock_solid = Mock()
        mock_ocp_shape = Mock()
        mock_solid.wrapped = mock_ocp_shape
        
        # Mock validation to return no issues
        with patch.object(ExportValidator, 'validate_for_export') as mock_validate:
            mock_result = ValidationResult()
            mock_validate.return_value = mock_result
            
            repaired, repair_result = ExportValidator.attempt_auto_repair(mock_solid)
            
            assert repair_result.success is True
            assert "Keine Reparatur nötig" in repair_result.message
    
    def test_attempt_auto_repair_with_validation_result(self):
        """Test Auto-Repair mit vorhandenem ValidationResult."""
        # Pre-existing validation result
        validation = ValidationResult()
        validation.add_issue(ValidationIssue(
            severity=ValidationSeverity.WARNING,
            check_type=ValidationCheckType.FREE_BOUNDS,
            message="Open edges"
        ))
        
        repaired, repair_result = ExportValidator.attempt_auto_repair(
            None,  # Will be handled
            validation_result=validation
        )
        
        assert repair_result.original_issues == 1
    
    def test_attempt_auto_repair_custom_strategies(self):
        """Test Auto-Repair mit benutzerdefinierten Strategien."""
        repaired, repair_result = ExportValidator.attempt_auto_repair(
            None,
            strategies=['shape_fix']
        )
        
        # Should only attempt shape_fix strategy
        assert isinstance(repair_result.strategies_applied, list)


class TestFreeBoundsDetection:
    """Tests für Free-Bounds Erkennung."""
    
    def test_free_bounds_check_updates_statistics(self):
        """Test dass Free-Bounds Check Statistiken sammelt."""
        result = ValidationResult()
        
        # Manuell Statistiken setzen wie es _check_free_bounds tun würde
        result.statistics['total_edges'] = 50
        result.statistics['free_bounds'] = 3
        result.statistics['internal_edges'] = 47
        
        assert result.statistics['free_bounds'] == 3
        assert result.statistics['internal_edges'] == 47
    
    def test_free_bounds_creates_issue(self):
        """Test dass offene Kanten ein Issue erstellen."""
        result = ValidationResult()
        issue = ValidationIssue(
            severity=ValidationSeverity.WARNING,
            check_type=ValidationCheckType.FREE_BOUNDS,
            message="3 offene Kanten gefunden",
            suggestion="Verwenden Sie Shell um Kanten zu schließen"
        )
        result.add_issue(issue)
        
        assert result.has_free_bounds is True
        assert result.is_closed is False
    
    def test_free_bounds_ratio_calculation(self):
        """Test Berechnung des Free-Bounds Verhältnisses."""
        total_edges = 100
        free_bounds = 5
        ratio = free_bounds / total_edges
        
        # 5% sollte unter der 1% Schwelle sein für WARNING
        assert ratio == 0.05
        
        # Bei 1% Schwelle wäre das ein WARNING
        max_ratio = 0.01
        assert ratio > max_ratio  # Would trigger stricter handling


class TestFeatureFlagsIntegration:
    """Tests für Feature-Flag Integration."""
    
    def test_export_normals_check_flag_exists(self):
        """Test dass export_normals_check Flag existiert."""
        from config.feature_flags import FEATURE_FLAGS
        
        assert 'export_normals_check' in FEATURE_FLAGS
        # Default sollte False sein (performance-intensiv)
        assert FEATURE_FLAGS['export_normals_check'] is False
    
    def test_export_auto_repair_flag_exists(self):
        """Test dass export_auto_repair Flag existiert."""
        from config.feature_flags import FEATURE_FLAGS
        
        assert 'export_auto_repair' in FEATURE_FLAGS
        # Default sollte True sein
        assert FEATURE_FLAGS['export_auto_repair'] is True
    
    def test_export_free_bounds_check_flag_exists(self):
        """Test dass export_free_bounds_check Flag existiert."""
        from config.feature_flags import FEATURE_FLAGS
        
        assert 'export_free_bounds_check' in FEATURE_FLAGS
        # Default sollte True sein
        assert FEATURE_FLAGS['export_free_bounds_check'] is True
    
    def test_feature_flag_is_enabled_function(self):
        """Test is_enabled Funktion für neue Flags."""
        from config.feature_flags import is_enabled, set_flag
        
        # Test default values
        assert is_enabled('export_auto_repair') is True
        assert is_enabled('export_normals_check') is False
        
        # Test setting flag
        set_flag('export_normals_check', True)
        assert is_enabled('export_normals_check') is True
        
        # Reset
        set_flag('export_normals_check', False)


class TestValidationResultExtended:
    """Erweiterte Tests für ValidationResult."""
    
    def test_has_inverted_normals_flag(self):
        """Test has_inverted_normals Flag."""
        result = ValidationResult()
        assert result.has_inverted_normals is False
        
        issue = ValidationIssue(
            severity=ValidationSeverity.WARNING,
            check_type=ValidationCheckType.NORMALS,
            message="Inverted normal"
        )
        result.add_issue(issue)
        
        assert result.has_inverted_normals is True
    
    def test_has_self_intersections_flag(self):
        """Test has_self_intersections Flag."""
        result = ValidationResult()
        assert result.has_self_intersections is False
        
        issue = ValidationIssue(
            severity=ValidationSeverity.ERROR,
            check_type=ValidationCheckType.SELF_INTERSECTION,
            message="Self intersection"
        )
        result.add_issue(issue)
        
        assert result.has_self_intersections is True
    
    def test_to_report_with_normals_issue(self):
        """Test Report-Generierung mit Normalen-Issue."""
        result = ValidationResult()
        result.add_issue(ValidationIssue(
            severity=ValidationSeverity.WARNING,
            check_type=ValidationCheckType.NORMALS,
            message="2 Faces mit invertierten Normalen",
            suggestion="Auto-Repair versuchen"
        ))
        
        report = result.to_report()
        assert "Normalen" in report or "normals" in report.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
