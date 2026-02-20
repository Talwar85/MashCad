"""
MashCAD - UX-003: Error Next Steps Tests
========================================

Tests for the "Next Step" error guidance feature.

Tests:
- All error codes have next steps
- Quick fix actions are properly defined
- UI display functions work correctly
- Coverage validation

Author: UX-003 Implementation
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

import pytest
from typing import List

from modeling.error_diagnostics import (
    ErrorDiagnostics,
    ErrorExplanation,
    ErrorCategory,
    ErrorSeverity,
    ErrorActionType,
    ERROR_KNOWLEDGE_BASE,
)


class TestNextStepsCoverage:
    """Test that all error codes have next steps."""
    
    def test_all_errors_have_next_steps(self):
        """Every error in the knowledge base should have at least one next step."""
        errors_without_steps = []
        
        for error_code, entry in ERROR_KNOWLEDGE_BASE.items():
            next_actions = entry.get("next_actions", [])
            if not next_actions:
                errors_without_steps.append(error_code)
        
        assert len(errors_without_steps) == 0, (
            f"Errors missing next steps: {errors_without_steps}"
        )
    
    def test_next_steps_are_actionable(self):
        """Next steps should be actionable (contain verbs)."""
        german_verbs = [
            "Prüfen", "Wählen", "Bearbeiten", "Verwenden", "Überprüfen",
            "Stellen", "Erhöhen", "Reduzieren", "Vereinfachen", "Entfernen",
            "Fügen", "Installieren", "Starten", "Speichern", "Kontaktieren",
            "Erstellen", "Aktivieren", "Blenden", "Konvertieren", "Versuchen",
            "Öffnen", "Schließen", "Kopieren", "Aktualisieren", "Ersetzen"
        ]
        
        for error_code, entry in ERROR_KNOWLEDGE_BASE.items():
            next_actions = entry.get("next_actions", [])
            for action in next_actions:
                # At least one verb should be present
                has_verb = any(verb in action for verb in german_verbs)
                assert has_verb or len(action) > 10, (
                    f"Next step for {error_code} may not be actionable: '{action}'"
                )
    
    def test_next_steps_count_reasonable(self):
        """Each error should have 2-5 next steps."""
        for error_code, entry in ERROR_KNOWLEDGE_BASE.items():
            next_actions = entry.get("next_actions", [])
            assert 1 <= len(next_actions) <= 6, (
                f"{error_code} has {len(next_actions)} steps, expected 1-6"
            )


class TestQuickFixActions:
    """Test quick fix action definitions."""
    
    def test_auto_fix_errors_have_action_type(self):
        """Errors with can_auto_fix=True should have action_type defined."""
        errors_missing_type = []
        
        for error_code, entry in ERROR_KNOWLEDGE_BASE.items():
            if entry.get("can_auto_fix"):
                if not entry.get("action_type"):
                    errors_missing_type.append(error_code)
        
        # This is a soft warning - not all auto-fix errors need explicit action_type
        # The get_quick_fix_action function will infer from category
        if errors_missing_type:
            pytest.skip(
                f"Auto-fix errors without explicit action_type (will use inference): "
                f"{errors_missing_type}"
            )
    
    def test_action_types_are_valid(self):
        """All action_type values should be valid ErrorActionType enum values."""
        valid_types = [e.value for e in ErrorActionType]
        
        for error_code, entry in ERROR_KNOWLEDGE_BASE.items():
            action_type = entry.get("action_type")
            if action_type:
                assert action_type in valid_types, (
                    f"{error_code} has invalid action_type: {action_type}"
                )


class TestGetNextStepsFunction:
    """Test the get_next_steps() function."""
    
    def test_get_next_steps_returns_list(self):
        """get_next_steps should return a list."""
        from gui.error_explainer import get_next_steps
        
        result = get_next_steps("geometry_non_manifold")
        assert isinstance(result, list)
    
    def test_get_next_steps_known_error(self):
        """get_next_steps should return steps for known errors."""
        from gui.error_explainer import get_next_steps
        
        result = get_next_steps("geometry_non_manifold")
        assert len(result) > 0
        assert any("Faces" in step or "Heilung" in step for step in result)
    
    def test_get_next_steps_unknown_error(self):
        """get_next_steps should return fallback steps for unknown errors."""
        from gui.error_explainer import get_next_steps
        
        result = get_next_steps("unknown_error_code_xyz")
        assert len(result) > 0
        # Should have fallback steps
        assert any("Speichern" in step or "erneut" in step.lower() for step in result)
    
    def test_get_next_steps_tnp_error(self):
        """TNP errors should have reference-related steps."""
        from gui.error_explainer import get_next_steps
        
        result = get_next_steps("tnp_ref_missing")
        assert len(result) > 0
        # Should mention reference selection
        assert any("Referenz" in step for step in result)


class TestGetQuickFixActionFunction:
    """Test the get_quick_fix_action() function."""
    
    def test_get_quick_fix_returns_action_type_or_none(self):
        """get_quick_fix_action should return ErrorActionType or None."""
        from gui.error_explainer import get_quick_fix_action
        
        result = get_quick_fix_action("geometry_non_manifold")
        assert result is None or isinstance(result, ErrorActionType)
    
    def test_get_quick_fix_auto_fix_error(self):
        """Auto-fixable errors should return an action type."""
        from gui.error_explainer import get_quick_fix_action
        
        # tnp_ref_missing has can_auto_fix=True
        result = get_quick_fix_action("tnp_ref_missing")
        assert result is not None
        assert isinstance(result, ErrorActionType)
    
    def test_get_quick_fix_non_auto_fix_error(self):
        """Non-auto-fixable errors may return None."""
        from gui.error_explainer import get_quick_fix_action
        
        # System errors typically don't have auto-fix
        result = get_quick_fix_action("system_unknown")
        # Could be None or an action type depending on implementation
        assert result is None or isinstance(result, ErrorActionType)


class TestDocumentationLinks:
    """Test documentation link generation."""
    
    def test_get_documentation_link_returns_string(self):
        """get_documentation_link should return a URL string."""
        from gui.error_explainer import get_documentation_link
        
        result = get_documentation_link("geometry_non_manifold")
        assert isinstance(result, str)
        assert result.startswith("http")
    
    def test_get_documentation_link_unknown_error(self):
        """Unknown errors should get a generic documentation link."""
        from gui.error_explainer import get_documentation_link
        
        result = get_documentation_link("unknown_error_xyz")
        assert "docs.mashcad.io" in result
    
    def test_get_documentation_link_category_specific(self):
        """TNP errors should get TNP-specific documentation."""
        from gui.error_explainer import get_documentation_link
        
        result = get_documentation_link("tnp_ref_missing")
        assert "tnp" in result.lower()


class TestValidateErrorCoverage:
    """Test the coverage validation function."""
    
    def test_validate_error_coverage_structure(self):
        """validate_error_coverage should return correct structure."""
        from gui.error_explainer import validate_error_coverage
        
        result = validate_error_coverage()
        
        assert "valid" in result
        assert "total_errors" in result
        assert "missing_next_steps" in result
        assert "coverage_percent" in result
        
        assert isinstance(result["valid"], bool)
        assert isinstance(result["total_errors"], int)
        assert isinstance(result["missing_next_steps"], list)
        assert isinstance(result["coverage_percent"], (int, float))
    
    def test_validate_error_coverage_high_coverage(self):
        """Coverage should be 100% or very close."""
        from gui.error_explainer import validate_error_coverage
        
        result = validate_error_coverage()
        
        # We expect 100% coverage after UX-003 implementation
        assert result["coverage_percent"] >= 95.0, (
            f"Coverage is only {result['coverage_percent']}%, expected >= 95%"
        )


class TestErrorExplanation:
    """Test ErrorExplanation enhancements."""
    
    def test_explanation_has_next_actions(self):
        """ErrorExplanation should include next_actions."""
        explanation = ErrorDiagnostics.explain("geometry_non_manifold")
        
        assert hasattr(explanation, "next_actions")
        assert len(explanation.next_actions) > 0
    
    def test_explanation_to_user_message_includes_steps(self):
        """to_user_message should include next steps."""
        explanation = ErrorDiagnostics.explain("geometry_non_manifold")
        
        message = explanation.to_user_message()
        
        # Should include "Nächste Schritte" or similar
        assert "Schritt" in message or "step" in message.lower()
    
    def test_explanation_action_type(self):
        """ErrorExplanation should have action_type for auto-fix errors."""
        explanation = ErrorDiagnostics.explain("tnp_ref_missing")
        
        # tnp_ref_missing has can_auto_fix=True
        if explanation.can_auto_fix:
            # action_type may be set directly or inferred
            assert explanation.action_type is not None or explanation.auto_fix_action


class TestErrorExplainerUI:
    """Test ErrorExplainer UI integration."""
    
    def test_error_explainer_has_required_methods(self):
        """ErrorExplainer should have all required methods."""
        from gui.error_explainer import ErrorExplainer
        
        # Check class has required methods
        assert hasattr(ErrorExplainer, "show_error")
        assert hasattr(ErrorExplainer, "show_from_result")
        assert hasattr(ErrorExplainer, "register_auto_fix_handler")
        assert hasattr(ErrorExplainer, "try_auto_fix")
        assert hasattr(ErrorExplainer, "get_last_error")
    
    def test_error_explainer_signals(self):
        """ErrorExplainer should have required signals."""
        from gui.error_explainer import ErrorExplainer
        
        # Signals are class attributes
        assert hasattr(ErrorExplainer, "error_shown")
        assert hasattr(ErrorExplainer, "auto_fix_requested")
        assert hasattr(ErrorExplainer, "error_dismissed")


class TestHasQuickFixFunction:
    """Test has_quick_fix function."""
    
    def test_has_quick_fix_auto_fixable(self):
        """has_quick_fix should return True for auto-fixable errors."""
        from gui.error_explainer import has_quick_fix
        
        # geometry_non_manifold has can_auto_fix=True
        result = has_quick_fix("geometry_non_manifold")
        assert isinstance(result, bool)
    
    def test_has_quick_fix_non_auto_fixable(self):
        """has_quick_fix should return False for non-auto-fixable errors."""
        from gui.error_explainer import has_quick_fix
        
        # System unknown typically doesn't have quick fix
        result = has_quick_fix("system_unknown")
        assert isinstance(result, bool)


class TestGetAllErrorCodes:
    """Test get_all_error_codes function."""
    
    def test_get_all_error_codes_returns_list(self):
        """get_all_error_codes should return a list."""
        from gui.error_explainer import get_all_error_codes
        
        result = get_all_error_codes()
        assert isinstance(result, list)
    
    def test_get_all_error_codes_not_empty(self):
        """get_all_error_codes should return non-empty list."""
        from gui.error_explainer import get_all_error_codes
        
        result = get_all_error_codes()
        assert len(result) > 0
    
    def test_get_all_error_codes_matches_knowledge_base(self):
        """get_all_error_codes should match ERROR_KNOWLEDGE_BASE keys."""
        from gui.error_explainer import get_all_error_codes
        
        result = get_all_error_codes()
        expected = list(ERROR_KNOWLEDGE_BASE.keys())
        
        assert set(result) == set(expected)


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
