"""
Integration Tests für Export Foundation + Error Diagnostics
===========================================================

Testet die Integration zwischen:
- ExportKernel
- ExportValidator
- ErrorDiagnostics

Run: pytest test/test_integration_export_diagnostics.py -v
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import tempfile
import os


class TestExportWithValidation:
    """Integration: Export mit Validierung."""
    
    def test_export_with_validation_shows_errors(self):
        """Test dass Export mit Validierung Fehler erkennt."""
        try:
            from modeling.export_kernel import ExportKernel, ExportOptions, ExportFormat
            from modeling.export_validator import ExportValidator, ValidationSeverity
        except ImportError:
            pytest.skip("Dependencies not available")
        
        # Mock Body mit ungültiger Geometrie
        mock_body = Mock()
        mock_body.visible = True
        mock_body.name = "TestBody"
        
        # Mock Solid das nicht-manifold ist
        mock_solid = Mock()
        mock_body._build123d_solid = mock_solid
        
        # Mock Validation um Fehler zu simulieren
        with patch.object(ExportValidator, '_check_manifold') as mock_check:
            # Erstelle ValidationResult mit Fehler
            from modeling.export_validator import ValidationResult, ValidationIssue, ValidationCheckType
            
            result = ValidationResult()
            result.add_issue(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                check_type=ValidationCheckType.MANIFOLD,
                message="Not closed"
            ))
            
            mock_check.side_effect = lambda shape, r, o: r.add_issue(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    check_type=ValidationCheckType.MANIFOLD,
                    message="Not closed"
                )
            )
            
            # Export mit Validierung
            options = ExportOptions(format=ExportFormat.STL)
            export_result = ExportKernel.export_with_validation(
                [mock_body], 
                "/tmp/test.stl",
                options,
                validation_options={'block_on_error': True}
            )
            
            # Sollte blockiert sein
            assert export_result.success is False
            assert export_result.error_code == "VALIDATION_FAILED"


class TestErrorDiagnosticsWithExport:
    """Integration: Error Diagnostics mit Export-Fehlern."""
    
    def test_export_error_explained(self):
        """Test dass Export-Fehler erklärt werden."""
        try:
            from modeling.export_kernel import ExportResult, ExportFormat
            from modeling.error_diagnostics import ErrorDiagnostics, ErrorCategory
        except ImportError:
            pytest.skip("Dependencies not available")
        
        # Erstelle einen Export-Fehler
        export_result = ExportResult(
            success=False,
            error_code="NO_VALID_BODIES",
            error_message="Keine gültigen Bodies",
            format=ExportFormat.STL
        )
        
        # Sollte erklärt werden können
        # (Auch wenn NO_VALID_BODIES nicht in KB ist, sollte es UNKNOWN behandeln)
        explanation = ErrorDiagnostics.explain("export_no_valid_geometry")
        
        assert explanation.error_code == "export_no_valid_geometry"
        assert explanation.category == ErrorCategory.IMPORT_EXPORT
        assert len(explanation.next_actions) > 0


class TestErrorInExportContext:
    """Integration: Fehler-Kontext in Export-Operationen."""
    
    def test_error_context_contains_feature_info(self):
        """Test dass Fehler-Kontext Feature-Info enthält."""
        try:
            from modeling.error_diagnostics import ErrorDiagnostics
        except ImportError:
            pytest.skip("Dependencies not available")
        
        # Simuliere Fehler mit Feature-Kontext
        mock_feature = Mock()
        mock_feature.name = "TestExtrude"
        mock_feature.__class__.__name__ = "ExtrudeFeature"
        
        context = {
            'feature': mock_feature,
            'feature_name': 'TestExtrude',
            'feature_type': 'ExtrudeFeature',
            'parameter': 10.0
        }
        
        explanation = ErrorDiagnostics.explain("reference_not_found", context)
        
        # Sollte Feature-Info enthalten
        assert 'feature_name' in explanation.context
        assert explanation.context['feature_name'] == 'TestExtrude'
        
        # Sollte in Next-Actions erwähnt werden
        actions_text = ' '.join(explanation.next_actions)
        assert 'TestExtrude' in actions_text or 'Feature' in actions_text


class TestValidationCategories:
    """Test Validation Categories mit Error Diagnostics."""
    
    def test_geometry_errors_mapped_correctly(self):
        """Test dass Geometrie-Fehler korrekt zugeordnet werden."""
        try:
            from modeling.error_diagnostics import (
                ErrorDiagnostics, ErrorCategory, ERROR_KNOWLEDGE_BASE
            )
            from modeling.export_validator import ValidationCheckType
        except ImportError:
            pytest.skip("Dependencies not available")
        
        # Prüfe dass Geometry-Fehler existieren
        geometry_errors = ErrorDiagnostics.get_errors_by_category(
            ErrorCategory.GEOMETRY
        )
        
        assert len(geometry_errors) > 0
        
        # Wichtige Geometrie-Fehler sollten existieren
        important_errors = [
            'geometry_non_manifold',
            'geometry_self_intersection',
            'geometry_degenerate'
        ]
        
        for error_code in important_errors:
            assert error_code in ERROR_KNOWLEDGE_BASE, f"{error_code} missing"


class TestErrorExplanationStructure:
    """Test Struktur von Error Explanations."""
    
    def test_all_explanations_have_required_fields(self):
        """Test dass alle Erklärungen Pflichtfelder haben."""
        try:
            from modeling.error_diagnostics import (
                ErrorDiagnostics, ERROR_KNOWLEDGE_BASE
            )
        except ImportError:
            pytest.skip("Dependencies not available")
        
        required_fields = ['title', 'description', 'next_actions']
        
        for error_code in ERROR_KNOWLEDGE_BASE.keys():
            explanation = ErrorDiagnostics.explain(error_code)
            
            assert explanation.title, f"{error_code} missing title"
            assert explanation.description, f"{error_code} missing description"
            assert len(explanation.next_actions) > 0, f"{error_code} missing next_actions"
            
            # Severity und Category sollten gesetzt sein
            assert explanation.severity is not None
            assert explanation.category is not None


class TestAutoFixDetection:
    """Test Auto-Fix Erkennung."""
    
    def test_can_auto_fix_for_valid_errors(self):
        """Test Auto-Fix Erkennung für bekannte Fehler."""
        try:
            from modeling.error_diagnostics import ErrorDiagnostics
        except ImportError:
            pytest.skip("Dependencies not available")
        
        # Diese sollten Auto-Fix haben
        auto_fix_errors = [
            'geometry_non_manifold',
            'constraint_over_constrained'
        ]
        
        for error_code in auto_fix_errors:
            explanation = ErrorDiagnostics.explain(error_code)
            assert explanation.can_auto_fix is True, f"{error_code} should have auto_fix"
            assert explanation.auto_fix_action, f"{error_code} missing auto_fix_action"


class TestIntegrationWithBody:
    """Test Integration mit Body-Objekten."""
    
    def test_body_validation_pipeline(self):
        """Test komplette Validation-Pipeline für Body."""
        try:
            from modeling.export_validator import ExportValidator
            from modeling.export_kernel import ExportKernel, ExportOptions
        except ImportError:
            pytest.skip("Dependencies not available")
        
        # Mock Body
        mock_body = Mock()
        mock_body.visible = True
        mock_body.name = "TestBody"
        mock_body.id = "body_123"
        
        # Mock Solid
        mock_solid = Mock()
        mock_body._build123d_solid = mock_solid
        mock_body._mesh = None
        
        # Prepare candidates
        candidates = ExportKernel._prepare_candidates([mock_body])
        
        assert len(candidates) == 1
        assert candidates[0].name == "TestBody"
        assert candidates[0].id == "body_123"
        
        # Solid extraction
        solid = candidates[0].get_solid()
        assert solid == mock_solid


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
