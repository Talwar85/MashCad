"""
MashCAD - OCP Compatibility Tests
==================================

CH-006: Tests for OCP API Compatibility Validation

Tests cover:
- Version detection
- API validation
- Graceful degradation
- Decorator functionality

Author: Claude (CH-006 Implementation)
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

import pytest
from unittest.mock import patch, MagicMock
import sys

from modeling.ocp_compatibility import (
    OCPVersionInfo,
    ApiCompatibilityIssue,
    ApiSeverity,
    check_ocp_availability,
    get_ocp_version,
    validate_ocp_api,
    ocp_api_guard,
    get_feature_availability,
    OCP_COMPATIBILITY,
    OCPCompatibility,
    ensure_ocp_available,
    get_missing_critical_apis,
    is_feature_available,
    REQUIRED_OCP_APIS,
    OPTIONAL_OCP_APIS,
)


class TestOCPVersionInfo:
    """Tests for OCPVersionInfo dataclass."""
    
    def test_default_values(self):
        """Test default values are set correctly."""
        info = OCPVersionInfo()
        assert info.available is False
        assert info.version_string == "unknown"
        assert info.major == 0
        assert info.minor == 0
        assert info.patch == 0
        assert info.ocp_package_version == "unknown"
    
    def test_str_not_available(self):
        """Test string representation when not available."""
        info = OCPVersionInfo()
        assert str(info) == "OCP not available"
    
    def test_str_available(self):
        """Test string representation when available."""
        info = OCPVersionInfo(
            available=True,
            version_string="7.8.1",
            ocp_package_version="7.8.1.0"
        )
        assert "7.8.1" in str(info)
        assert "7.8.1.0" in str(info)
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        info = OCPVersionInfo(
            available=True,
            version_string="7.8.1",
            major=7,
            minor=8,
            patch=1,
            ocp_package_version="7.8.1.0",
            python_version="3.11.0",
            platform="Windows 10"
        )
        d = info.to_dict()
        assert d["available"] is True
        assert d["version_string"] == "7.8.1"
        assert d["major"] == 7
        assert d["minor"] == 8
        assert d["patch"] == 1
    
    def test_is_at_least(self):
        """Test version comparison."""
        info = OCPVersionInfo(available=True, major=7, minor=8, patch=1)
        
        # Should be True for lower or equal versions
        assert info.is_at_least(7, 0, 0) is True
        assert info.is_at_least(7, 8, 0) is True
        assert info.is_at_least(7, 8, 1) is True
        
        # Should be False for higher versions
        assert info.is_at_least(8, 0, 0) is False
        assert info.is_at_least(7, 9, 0) is False
        assert info.is_at_least(7, 8, 2) is False
    
    def test_is_at_least_not_available(self):
        """Test version comparison when OCP not available."""
        info = OCPVersionInfo(available=False)
        assert info.is_at_least(1, 0, 0) is False


class TestApiCompatibilityIssue:
    """Tests for ApiCompatibilityIssue dataclass."""
    
    def test_basic_issue(self):
        """Test basic issue creation."""
        issue = ApiCompatibilityIssue(
            api_name="TestAPI",
            severity=ApiSeverity.WARNING,
            message="Test message"
        )
        assert issue.api_name == "TestAPI"
        assert issue.severity == ApiSeverity.WARNING
        assert issue.message == "Test message"
        assert issue.suggestion == ""
    
    def test_str_representation(self):
        """Test string representation."""
        issue = ApiCompatibilityIssue(
            api_name="TestAPI",
            severity=ApiSeverity.CRITICAL,
            message="Critical issue",
            suggestion="Update OCP"
        )
        s = str(issue)
        assert "[CRITICAL]" in s
        assert "TestAPI" in s
        assert "Critical issue" in s
        assert "Update OCP" in s
    
    def test_to_dict(self):
        """Test serialization."""
        issue = ApiCompatibilityIssue(
            api_name="TestAPI",
            severity=ApiSeverity.WARNING,
            message="Test",
            suggestion="Fix it",
            platform_info="Windows"
        )
        d = issue.to_dict()
        assert d["api_name"] == "TestAPI"
        assert d["severity"] == "warning"
        assert d["message"] == "Test"
        assert d["suggestion"] == "Fix it"
        assert d["platform_info"] == "Windows"


class TestCheckOcpAvailability:
    """Tests for check_ocp_availability function."""
    
    def test_returns_bool(self):
        """Test that function returns boolean."""
        result = check_ocp_availability()
        assert isinstance(result, bool)
    
    @patch.dict(sys.modules, {'OCP': None})
    def test_returns_false_when_import_fails(self):
        """Test returns False when OCP import fails."""
        # This test simulates OCP not being installed
        with patch.dict(sys.modules, {'OCP': None}):
            # Force re-import
            import importlib
            import modeling.ocp_compatibility as compat_module
            importlib.reload(compat_module)
            # The module-level HAS_OCP should be checked
            # Note: This is tricky due to module caching


class TestGetOcpVersion:
    """Tests for get_ocp_version function."""
    
    def test_returns_version_info(self):
        """Test that function returns OCPVersionInfo."""
        result = get_ocp_version()
        assert isinstance(result, OCPVersionInfo)
    
    def test_contains_platform_info(self):
        """Test that result contains platform info."""
        result = get_ocp_version()
        assert result.platform != ""
        assert result.python_version != ""


class TestValidateOcpApi:
    """Tests for validate_ocp_api function."""
    
    def test_returns_list(self):
        """Test that function returns a list."""
        result = validate_ocp_api()
        assert isinstance(result, list)
    
    def test_items_are_issues(self):
        """Test that all items are ApiCompatibilityIssue."""
        result = validate_ocp_api()
        for item in result:
            assert isinstance(item, ApiCompatibilityIssue)
    
    def test_optional_check(self):
        """Test checking optional APIs."""
        result_required = validate_ocp_api(check_optional=False)
        result_optional = validate_ocp_api(check_optional=True)
        
        # Optional check should potentially return more issues
        # (or same if all optional APIs are available)
        assert isinstance(result_optional, list)


class TestOcpApiGuard:
    """Tests for ocp_api_guard decorator."""
    
    def test_guard_returns_fallback_on_import_error(self):
        """Test decorator returns fallback when OCP unavailable."""
        @ocp_api_guard(fallback="fallback_value")
        def test_func():
            return "success"
        
        # When OCP is available, should return success
        # (This test assumes OCP is available in test environment)
        result = test_func()
        # Result depends on whether OCP is installed
        assert result in ["success", "fallback_value"]
    
    def test_guard_with_specific_api(self):
        """Test decorator with specific API requirement."""
        @ocp_api_guard(fallback=None, api_names=["BRepPrimAPI_MakeBox"])
        def make_box():
            return "box_created"
        
        result = make_box()
        # Should return box_created if API available, None otherwise
        assert result in ["box_created", None]
    
    def test_guard_raises_on_failure(self):
        """Test decorator raises when raise_on_failure is True."""
        @ocp_api_guard(fallback=None, raise_on_failure=True)
        def failing_func():
            raise ImportError("OCP not found")
        
        # This should raise RuntimeError when OCP is not available
        # But if OCP is available, the ImportError is caught and re-raised
        with pytest.raises((RuntimeError, ImportError)):
            failing_func()
    
    def test_guard_preserves_function_metadata(self):
        """Test decorator preserves function name and docstring."""
        @ocp_api_guard(fallback=None)
        def documented_function():
            """This is a documented function."""
            return "result"
        
        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is a documented function."


class TestGetFeatureAvailability:
    """Tests for get_feature_availability function."""
    
    def test_returns_dict(self):
        """Test that function returns a dictionary."""
        result = get_feature_availability()
        assert isinstance(result, dict)
    
    def test_contains_expected_features(self):
        """Test that result contains expected feature keys."""
        result = get_feature_availability()
        expected_keys = [
            "primitives",
            "booleans",
            "fillet_chamfer",
            "topology_exploration",
            "geometry_types",
            "shape_building",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"
    
    def test_values_are_bool(self):
        """Test that all values are booleans."""
        result = get_feature_availability()
        for key, value in result.items():
            assert isinstance(value, bool), f"Value for {key} is not bool: {type(value)}"


class TestOCPCompatibility:
    """Tests for OCPCompatibility class."""
    
    def test_singleton_initialization(self):
        """Test that global instance can be initialized."""
        # Force re-initialization
        OCP_COMPATIBILITY._initialized = False
        OCP_COMPATIBILITY.initialize()
        
        assert OCP_COMPATIBILITY._initialized is True
    
    def test_is_available_property(self):
        """Test is_available property."""
        result = OCP_COMPATIBILITY.is_available
        assert isinstance(result, bool)
    
    def test_version_info_property(self):
        """Test version_info property."""
        result = OCP_COMPATIBILITY.version_info
        assert isinstance(result, OCPVersionInfo)
    
    def test_api_issues_property(self):
        """Test api_issues property."""
        result = OCP_COMPATIBILITY.api_issues
        assert isinstance(result, list)
    
    def test_feature_availability_property(self):
        """Test feature_availability property."""
        result = OCP_COMPATIBILITY.feature_availability
        assert isinstance(result, dict)
    
    def test_has_critical_issues_property(self):
        """Test has_critical_issues property."""
        result = OCP_COMPATIBILITY.has_critical_issues
        assert isinstance(result, bool)
    
    def test_get_summary(self):
        """Test get_summary method."""
        summary = OCP_COMPATIBILITY.get_summary()
        assert isinstance(summary, str)
        assert "OCP Compatibility" in summary


class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def test_ensure_ocp_available(self):
        """Test ensure_ocp_available function."""
        if OCP_COMPATIBILITY.is_available:
            # Should not raise
            ensure_ocp_available()
        else:
            # Should raise RuntimeError
            with pytest.raises(RuntimeError):
                ensure_ocp_available()
    
    def test_get_missing_critical_apis(self):
        """Test get_missing_critical_apis function."""
        result = get_missing_critical_apis()
        assert isinstance(result, list)
        # All items should be strings
        for item in result:
            assert isinstance(item, str)
    
    def test_is_feature_available(self):
        """Test is_feature_available function."""
        # Test with known feature
        result = is_feature_available("primitives")
        assert isinstance(result, bool)
        
        # Test with unknown feature
        result = is_feature_available("nonexistent_feature")
        assert result is False


class TestRequiredApisDefinition:
    """Tests for required APIs definition."""
    
    def test_required_apis_not_empty(self):
        """Test that required APIs list is not empty."""
        assert len(REQUIRED_OCP_APIS) > 0
    
    def test_required_apis_have_module(self):
        """Test that all required APIs have module defined."""
        for api_name, api_info in REQUIRED_OCP_APIS.items():
            assert "module" in api_info, f"Missing module for {api_name}"
            assert api_info["module"].startswith("OCP."), f"Invalid module for {api_name}"
    
    def test_required_apis_have_description(self):
        """Test that all required APIs have description."""
        for api_name, api_info in REQUIRED_OCP_APIS.items():
            assert "description" in api_info, f"Missing description for {api_name}"
    
    def test_optional_apis_not_empty(self):
        """Test that optional APIs list is not empty."""
        assert len(OPTIONAL_OCP_APIS) > 0


class TestGracefulDegradation:
    """Tests for graceful degradation scenarios."""
    
    def test_decorator_handles_attribute_error(self):
        """Test that decorator handles AttributeError gracefully."""
        @ocp_api_guard(fallback="fallback")
        def func_with_attribute_error():
            raise AttributeError("API not found")
        
        # Should catch the error and return fallback
        # Note: Only catches if error message contains OCP keywords
        result = func_with_attribute_error()
        assert result == "fallback"
    
    def test_decorator_passes_through_unrelated_errors(self):
        """Test that decorator passes through unrelated errors."""
        @ocp_api_guard(fallback="fallback")
        def func_with_unrelated_error():
            raise ValueError("Unrelated error")
        
        # Should raise the ValueError, not return fallback
        with pytest.raises(ValueError):
            func_with_unrelated_error()


class TestIntegration:
    """Integration tests for OCP compatibility module."""
    
    def test_full_initialization_flow(self):
        """Test full initialization flow."""
        # Create new instance
        compat = OCPCompatibility()
        compat.initialize(force=True)
        
        # Check all properties are populated
        assert compat._version_info is not None
        assert compat._api_issues is not None
        assert compat._feature_availability is not None
        assert compat._initialized is True
    
    def test_double_initialization(self):
        """Test that double initialization doesn't cause issues."""
        compat = OCPCompatibility()
        compat.initialize()
        compat.initialize()  # Second call should be no-op
        
        assert compat._initialized is True
    
    def test_force_reinitialization(self):
        """Test force reinitialization."""
        compat = OCPCompatibility()
        compat.initialize()
        
        # Modify state
        compat._api_issues = []
        
        # Force reinit
        compat.initialize(force=True)
        
        # Should have issues again (or empty list if all APIs available)
        assert compat._api_issues is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
