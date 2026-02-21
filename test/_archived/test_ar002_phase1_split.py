"""
Test for AR-002: modeling/__init__.py Phase1 Split

Tests verify:
- New modules can be imported
- Backward compatibility maintained
- Functions work correctly
"""

import pytest


class TestGeometryUtils:
    """Tests for modeling/geometry_utils.py"""

    def test_import_geometry_utils(self):
        """Test that geometry_utils can be imported directly."""
        from modeling.geometry_utils import (
            solid_metrics,
            canonicalize_indices,
            get_face_center,
            get_face_area,
            validate_plane_normal,
            format_index_refs_for_error,
            format_shape_refs_for_error,
            collect_feature_reference_diagnostics,
            collect_feature_reference_payload,
        )
        assert callable(solid_metrics)
        assert callable(canonicalize_indices)
        assert callable(get_face_center)
        assert callable(get_face_area)

    def test_canonicalize_indices_empty(self):
        """Test canonicalize_indices with empty input."""
        from modeling.geometry_utils import canonicalize_indices
        assert canonicalize_indices([]) == []
        assert canonicalize_indices(None) == []

    def test_canonicalize_indices_dedup(self):
        """Test canonicalize_indices removes duplicates."""
        from modeling.geometry_utils import canonicalize_indices
        result = canonicalize_indices([3, 1, 2, 2, 1])
        assert result == [1, 2, 3]

    def test_canonicalize_indices_negative(self):
        """Test canonicalize_indices filters negative values."""
        from modeling.geometry_utils import canonicalize_indices
        result = canonicalize_indices([3, -1, 2, -5])
        assert result == [2, 3]

    def test_canonicalize_indices_invalid(self):
        """Test canonicalize_indices handles invalid values."""
        from modeling.geometry_utils import canonicalize_indices
        result = canonicalize_indices([3, 'a', 2, None, 1.5])
        assert result == [1, 2, 3]  # 1.5 -> int(1.5) = 1, 'a' and None skipped

    def test_validate_plane_normal_zero(self):
        """Test validate_plane_normal with zero vector."""
        from modeling.geometry_utils import validate_plane_normal
        result = validate_plane_normal((0, 0, 0))
        assert result == (0, 0, 1)  # Default fallback

    def test_validate_plane_normal_normalizes(self):
        """Test validate_plane_normal normalizes vectors."""
        from modeling.geometry_utils import validate_plane_normal
        result = validate_plane_normal((2, 0, 0))
        assert result == (1.0, 0.0, 0.0)

    def test_format_index_refs_for_error_none(self):
        """Test format_index_refs_for_error with None."""
        from modeling.geometry_utils import format_index_refs_for_error
        assert format_index_refs_for_error("test", None) == ""

    def test_format_index_refs_for_error_single(self):
        """Test format_index_refs_for_error with single value."""
        from modeling.geometry_utils import format_index_refs_for_error
        result = format_index_refs_for_error("face", 5)
        assert "5" in result
        assert "face" in result

    def test_format_index_refs_for_error_list(self):
        """Test format_index_refs_for_error with list."""
        from modeling.geometry_utils import format_index_refs_for_error
        result = format_index_refs_for_error("edge", [1, 2, 3])
        assert "1" in result
        assert "2" in result
        assert "3" in result


class TestShapeBuilders:
    """Tests for modeling/shape_builders.py"""

    def test_import_shape_builders(self):
        """Test that shape_builders can be imported directly."""
        from modeling.shape_builders import (
            convert_legacy_nsided_edge_selectors,
            convert_legacy_edge_selectors,
            convert_line_profiles_to_polygons,
            filter_profiles_by_selector,
            get_plane_from_sketch,
            lookup_geometry_for_polygon,
        )
        assert callable(convert_legacy_nsided_edge_selectors)
        assert callable(convert_legacy_edge_selectors)
        assert callable(convert_line_profiles_to_polygons)
        assert callable(filter_profiles_by_selector)

    def test_convert_legacy_edge_selectors_empty(self):
        """Test convert_legacy_edge_selectors with empty input."""
        from modeling.shape_builders import convert_legacy_edge_selectors
        assert convert_legacy_edge_selectors([]) == []
        assert convert_legacy_edge_selectors(None) == []

    def test_convert_legacy_edge_selectors_valid(self):
        """Test convert_legacy_edge_selectors with valid input."""
        from modeling.shape_builders import convert_legacy_edge_selectors
        result = convert_legacy_edge_selectors([(1.0, 2.0, 3.0)])
        assert len(result) == 1
        assert result[0]["center"] == [1.0, 2.0, 3.0]
        assert "direction" in result[0]

    def test_filter_profiles_by_selector_empty(self):
        """Test filter_profiles_by_selector with empty inputs."""
        from modeling.shape_builders import filter_profiles_by_selector
        assert filter_profiles_by_selector([], []) == []
        assert filter_profiles_by_selector(None, []) == []

    def test_filter_profiles_by_selector_no_selector(self):
        """Test filter_profiles_by_selector returns all when no selector."""
        from modeling.shape_builders import filter_profiles_by_selector
        
        # Create mock profiles
        class MockProfile:
            def __init__(self, x, y):
                self._x = x
                self._y = y
            @property
            def centroid(self):
                class C:
                    x = self._x
                    y = self._y
                return C()
        
        profiles = [MockProfile(0, 0), MockProfile(10, 10)]
        # When selector is empty, return all profiles
        result = filter_profiles_by_selector(profiles, [])
        assert len(result) == 2


class TestBackwardCompatibility:
    """Tests for backward compatibility with legacy imports."""

    def test_legacy_aliases_exist_geometry_utils(self):
        """Test that legacy aliases exist in geometry_utils."""
        from modeling.geometry_utils import (
            _solid_metrics,
            _canonicalize_indices,
            _get_face_center,
            _get_face_area,
            _format_index_refs_for_error,
            _format_shape_refs_for_error,
            _collect_feature_reference_diagnostics,
            _collect_feature_reference_payload,
        )
        # All aliases should be callable
        assert callable(_solid_metrics)
        assert callable(_canonicalize_indices)
        assert callable(_get_face_center)
        assert callable(_get_face_area)

    def test_legacy_aliases_exist_shape_builders(self):
        """Test that legacy aliases exist in shape_builders."""
        from modeling.shape_builders import (
            _convert_legacy_nsided_edge_selectors,
            _convert_legacy_edge_selectors,
            _convert_line_profiles_to_polygons,
            _filter_profiles_by_selector,
            _get_plane_from_sketch,
            _lookup_geometry_for_polygon,
        )
        # All aliases should be callable
        assert callable(_convert_legacy_nsided_edge_selectors)
        assert callable(_convert_legacy_edge_selectors)
        assert callable(_convert_line_profiles_to_polygons)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
