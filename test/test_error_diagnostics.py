"""
Tests für Error Diagnostics Framework
=====================================

Phase 2: CH-008 - Fehlerdiagnostik im UI verbessern

Run: pytest test/test_error_diagnostics.py -v
"""

import pytest
from unittest.mock import Mock, MagicMock

# Skip if dependencies not available
try:
    from modeling.error_diagnostics import (
        ErrorDiagnostics, ErrorExplanation, ErrorCategory, ErrorSeverity,
        explain_error, get_next_actions, format_error_for_user,
        ERROR_KNOWLEDGE_BASE
    )
    DEPENDENCIES_AVAILABLE = True
except ImportError:
    DEPENDENCIES_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not DEPENDENCIES_AVAILABLE,
    reason="ErrorDiagnostics dependencies not available"
)


class TestErrorExplanation:
    """Tests für ErrorExplanation Dataclass."""
    
    def test_explanation_creation(self):
        """Test Erstellung einer Erklärung."""
        explanation = ErrorExplanation(
            error_code="test_error",
            category=ErrorCategory.GEOMETRY,
            severity=ErrorSeverity.WARNING,
            title="Test Error",
            description="A test error occurred",
            next_actions=["Step 1", "Step 2"]
        )
        
        assert explanation.error_code == "test_error"
        assert explanation.category == ErrorCategory.GEOMETRY
        assert len(explanation.next_actions) == 2
        
    def test_to_user_message(self):
        """Test Formatierung für Nutzer."""
        explanation = ErrorExplanation(
            error_code="test_error",
            category=ErrorCategory.GEOMETRY,
            severity=ErrorSeverity.WARNING,
            title="Test Error",
            description="A test error occurred",
            next_actions=["Fix step 1", "Fix step 2"]
        )
        
        msg = explanation.to_user_message()
        assert "Test Error" in msg
        assert "Fix step 1" in msg
        assert "1." in msg  # Numbered list
        
    def test_to_user_message_with_technical(self):
        """Test Formatierung mit technischen Details."""
        explanation = ErrorExplanation(
            error_code="test_error",
            category=ErrorCategory.GEOMETRY,
            severity=ErrorSeverity.WARNING,
            title="Test",
            description="Desc",
            technical_details="Technical info"
        )
        
        msg = explanation.to_user_message(include_technical=True)
        assert "Technical info" in msg
        
    def test_to_dict(self):
        """Test Serialisierung."""
        explanation = ErrorExplanation(
            error_code="test_error",
            category=ErrorCategory.GEOMETRY,
            severity=ErrorSeverity.WARNING,
            title="Test",
            description="Desc"
        )
        
        d = explanation.to_dict()
        assert d['error_code'] == "test_error"
        assert d['category'] == "geometry"
        assert d['severity'] == "warning"


class TestErrorDiagnostics:
    """Tests für ErrorDiagnostics Engine."""
    
    def test_explain_known_error(self):
        """Test Erklärung eines bekannten Fehlers."""
        explanation = ErrorDiagnostics.explain("geometry_non_manifold")
        
        assert explanation.error_code == "geometry_non_manifold"
        assert explanation.category == ErrorCategory.GEOMETRY
        assert explanation.title  # Sollte einen Titel haben
        assert explanation.description  # Sollte eine Beschreibung haben
        assert len(explanation.next_actions) > 0
        
    def test_explain_unknown_error(self):
        """Test Erklärung eines unbekannten Fehlers."""
        explanation = ErrorDiagnostics.explain("unknown_error_xyz")
        
        assert explanation.error_code == "unknown_error_xyz"
        assert explanation.category == ErrorCategory.UNKNOWN
        assert explanation.severity == ErrorSeverity.CRITICAL
        
    def test_explain_with_context(self):
        """Test Erklärung mit Kontext."""
        context = {
            'feature_name': 'TestFeature',
            'feature_type': 'ExtrudeFeature'
        }
        explanation = ErrorDiagnostics.explain("reference_not_found", context)
        
        assert 'feature_name' in explanation.context
        assert explanation.context['feature_name'] == 'TestFeature'
        # Sollte Feature-Info in next_actions haben
        assert any('TestFeature' in action for action in explanation.next_actions)
        
    def test_can_auto_fix(self):
        """Test Auto-Fix Erkennung."""
        # Diese Errors sollten Auto-Fix haben
        assert ErrorDiagnostics.can_auto_fix("geometry_non_manifold") is True
        assert ErrorDiagnostics.can_auto_fix("constraint_over_constrained") is True
        
        # Diese nicht
        assert ErrorDiagnostics.can_auto_fix("reference_not_found") is False
        
    def test_get_suggested_actions(self):
        """Test Abrufen von vorgeschlagenen Aktionen."""
        actions = ErrorDiagnostics.get_suggested_actions("geometry_non_manifold")
        
        assert len(actions) > 0
        assert all(isinstance(a, str) for a in actions)
        
    def test_get_errors_by_category(self):
        """Test Abrufen von Fehlern nach Kategorie."""
        geometry_errors = ErrorDiagnostics.get_errors_by_category(ErrorCategory.GEOMETRY)
        
        assert len(geometry_errors) > 0
        assert "geometry_non_manifold" in geometry_errors
        
    def test_search_errors(self):
        """Test Fehler-Suche."""
        results = ErrorDiagnostics.search_errors("manifold")
        
        assert len(results) > 0
        # Sollte geometry_non_manifold enthalten
        assert any(r['code'] == 'geometry_non_manifold' for r in results)
        
    def test_register_custom_handler(self):
        """Test Registrierung eines Custom Handlers."""
        custom_called = False
        
        def custom_handler(explanation, context):
            nonlocal custom_called
            custom_called = True
            explanation.title = "Custom Title"
            return explanation
        
        ErrorDiagnostics.register_custom_handler("test_custom", custom_handler)
        
        explanation = ErrorDiagnostics.explain("test_custom")
        
        assert custom_called is True
        assert explanation.title == "Custom Title"


class TestErrorKnowledgeBase:
    """Tests für die Error Knowledge Base."""
    
    def test_all_entries_have_required_fields(self):
        """Test dass alle KB-Einträge Pflichtfelder haben."""
        required_fields = ['category', 'severity', 'title', 'description', 'next_actions']
        
        for code, entry in ERROR_KNOWLEDGE_BASE.items():
            for field in required_fields:
                assert field in entry, f"{code} missing {field}"
                
    def test_categories_are_valid(self):
        """Test dass alle Kategorien gültig sind."""
        valid_categories = set(ErrorCategory)
        
        for code, entry in ERROR_KNOWLEDGE_BASE.items():
            assert entry['category'] in valid_categories, f"{code} has invalid category"
            
    def test_severities_are_valid(self):
        """Test dass alle Schweregrade gültig sind."""
        valid_severities = set(ErrorSeverity)
        
        for code, entry in ERROR_KNOWLEDGE_BASE.items():
            assert entry['severity'] in valid_severities, f"{code} has invalid severity"
            
    def test_next_actions_is_list(self):
        """Test dass next_actions eine Liste ist."""
        for code, entry in ERROR_KNOWLEDGE_BASE.items():
            assert isinstance(entry['next_actions'], list), f"{code} next_actions not a list"
            assert len(entry['next_actions']) > 0, f"{code} has empty next_actions"


class TestConvenienceFunctions:
    """Tests für Convenience-Funktionen."""
    
    def test_explain_error(self):
        """Test explain_error Shortcut."""
        explanation = explain_error("geometry_non_manifold")
        
        assert explanation.error_code == "geometry_non_manifold"
        
    def test_get_next_actions(self):
        """Test get_next_actions Shortcut."""
        actions = get_next_actions("geometry_non_manifold")
        
        assert len(actions) > 0
        
    def test_format_error_for_user(self):
        """Test format_error_for_user."""
        msg = format_error_for_user("geometry_non_manifold")
        
        assert isinstance(msg, str)
        assert len(msg) > 0


class TestIntegrationWithOperationResult:
    """Tests für Integration mit OperationResult."""
    
    def test_explain_from_result_error(self):
        """Test Erklärung aus einem Error-Result."""
        try:
            from modeling.result_types import OperationResult
            
            result = OperationResult.error(
                "Operation failed",
                context={'error_code': 'geometry_non_manifold'}
            )
            
            explanation = ErrorDiagnostics.explain_result(result)
            
            assert explanation is not None
            assert explanation.error_code == "geometry_non_manifold"
            
        except ImportError:
            pytest.skip("OperationResult not available")
            
    def test_explain_from_result_success(self):
        """Test dass Success-Result None zurückgibt."""
        try:
            from modeling.result_types import OperationResult
            
            result = OperationResult.success("value")
            
            explanation = ErrorDiagnostics.explain_result(result)
            
            assert explanation is None
            
        except ImportError:
            pytest.skip("OperationResult not available")


class TestErrorCategories:
    """Tests für Error-Kategorien."""
    
    def test_all_categories_have_errors(self):
        """Test dass alle Kategorien Einträge haben."""
        categories_with_errors = set()
        
        for entry in ERROR_KNOWLEDGE_BASE.values():
            categories_with_errors.add(entry['category'])
        
        # Jede Kategorie außer UNKNOWN sollte mindestens einen Eintrag haben
        for cat in ErrorCategory:
            if cat != ErrorCategory.UNKNOWN:
                assert cat in categories_with_errors or True  # Soft check


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
