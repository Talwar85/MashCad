"""
Tests für Export Validator
==========================

Phase 1: Export Foundation (PR-002)
Testet ExportValidator und ValidationResult.

Run: pytest test/test_export_validator.py -v
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
