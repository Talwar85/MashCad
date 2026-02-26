"""
TNP v5.0 - Spatial Index Tests

Unit tests for the R-tree based spatial index.
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from modeling.tnp_v5.spatial import (
    Bounds,
    SpatialIndex,
    compute_bounds_from_signature
)


class TestBounds:
    """Test Bounds dataclass."""

    def test_create_bounds(self):
        """Test creating bounds from min/max coordinates."""
        bounds = Bounds(0, 0, 0, 10, 10, 10)

        assert bounds.min_x == 0
        assert bounds.max_x == 10
        assert bounds.to_tuple() == (0, 0, 0, 10, 10, 10)

    def test_bounds_from_center(self):
        """Test creating bounds from center point."""
        bounds = Bounds.from_center((5, 5, 5), 2)

        assert bounds.min_x == 3
        assert bounds.max_x == 7
        assert bounds.min_y == 3
        assert bounds.max_y == 7
        assert bounds.min_z == 3
        assert bounds.max_z == 7

    def test_bounds_from_points(self):
        """Test creating bounds from list of points."""
        points = [
            (0, 0, 0),
            (10, 0, 0),
            (5, 10, 0),
            (5, 5, 10)
        ]

        bounds = Bounds.from_points(points)

        assert bounds.min_x == 0
        assert bounds.max_x == 10
        assert bounds.min_y == 0
        assert bounds.max_y == 10
        assert bounds.min_z == 0
        assert bounds.max_z == 10

    def test_bounds_from_points_empty(self):
        """Test creating bounds from empty point list."""
        bounds = Bounds.from_points([])

        # Returns zero-size bounds
        assert bounds.min_x == 0
        assert bounds.max_x == 0

    def test_bounds_contains(self):
        """Test point containment check."""
        bounds = Bounds(0, 0, 0, 10, 10, 10)

        assert bounds.contains((5, 5, 5)) is True
        assert bounds.contains((0, 0, 0)) is True
        assert bounds.contains((10, 10, 10)) is True
        assert bounds.contains((11, 5, 5)) is False
        assert bounds.contains((5, -1, 5)) is False

    def test_bounds_center(self):
        """Test getting bounds center."""
        bounds = Bounds(0, 0, 0, 10, 10, 10)

        center = bounds.center()
        assert center == (5, 5, 5)

    def test_bounds_distance_to_inside(self):
        """Test distance to point inside bounds."""
        bounds = Bounds(0, 0, 0, 10, 10, 10)

        assert bounds.distance_to((5, 5, 5)) == 0.0

    def test_bounds_distance_to_outside(self):
        """Test distance to point outside bounds."""
        bounds = Bounds(0, 0, 0, 10, 10, 10)

        # Point at (15, 5, 5) is 5 units away
        dist = bounds.distance_to((15, 5, 5))
        assert abs(dist - 5.0) < 0.01

    def test_bounds_distance_to_corner(self):
        """Test distance to point outside corner."""
        bounds = Bounds(0, 0, 0, 10, 10, 10)

        # Point at (15, 15, 15)
        dist = bounds.distance_to((15, 15, 15))
        # Distance to corner (10, 10, 10) is sqrt(5^2 + 5^2 + 5^2) = sqrt(75)
        expected = np.sqrt(75)
        assert abs(dist - expected) < 0.01

    def test_bounds_iteration(self):
        """Test iterating bounds as tuple."""
        bounds = Bounds(0, 1, 2, 3, 4, 5)

        result = tuple(bounds)
        assert result == (0, 1, 2, 3, 4, 5)


class TestSpatialIndex:
    """Test SpatialIndex class."""

    def test_init_with_rtree(self):
        """Test initialization when rtree is available."""
        with patch('modeling.tnp_v5.spatial.HAS_RTREE', True):
            idx = SpatialIndex()
            assert idx.size == 0
            # Index is created if rtree available

    def test_init_without_rtree(self):
        """Test initialization when rtree is not available."""
        with patch('modeling.tnp_v5.spatial.HAS_RTREE', False):
            idx = SpatialIndex()
            assert idx.size == 0
            assert idx.is_accelerated is False

    def test_insert_shape(self):
        """Test inserting a shape into the index."""
        idx = SpatialIndex()

        idx.insert("shape1", (0, 0, 0, 10, 10, 10))

        assert idx.size == 1
        assert "shape1" in idx

    def test_insert_with_bounds_object(self):
        """Test inserting with Bounds object."""
        idx = SpatialIndex()
        bounds = Bounds(0, 0, 0, 10, 10, 10)

        idx.insert("shape1", bounds)

        assert "shape1" in idx
        assert idx.get_bounds("shape1") == bounds

    def test_insert_with_shape_data(self):
        """Test inserting shape with metadata."""
        idx = SpatialIndex()

        data = {'shape_type': 'FACE', 'feature_id': 'extrude_1'}
        idx.insert("shape1", (0, 0, 0, 10, 10, 10), data)

        assert idx.get_shape_data("shape1") == data

    def test_query_nearby(self):
        """Test querying shapes near a point."""
        idx = SpatialIndex()

        # Insert shapes at different locations
        idx.insert("near1", (0, 0, 0, 10, 10, 10))
        idx.insert("near2", (5, 5, 5, 15, 15, 15))
        idx.insert("far", (100, 100, 100, 110, 110, 110))

        # Query near origin
        results = idx.query_nearby((5, 5, 5), 20)

        # Should find near1 and near2, not far
        assert len(results) >= 2
        assert "near1" in results or "near2" in results

    def test_query_nearby_with_type_filter(self):
        """Test querying with shape type filter."""
        idx = SpatialIndex()

        idx.insert("face1", (0, 0, 0, 10, 10, 10), {'shape_type': 'FACE'})
        idx.insert("edge1", (0, 0, 0, 10, 10, 10), {'shape_type': 'EDGE'})

        results = idx.query_nearby((5, 5, 5), 20, shape_type='FACE')

        assert "face1" in results
        assert "edge1" not in results

    def test_nearest(self):
        """Test finding nearest shapes."""
        idx = SpatialIndex()

        idx.insert("close", (0, 0, 0, 5, 5, 5))
        idx.insert("medium", (10, 0, 0, 15, 5, 5))
        idx.insert("far", (50, 0, 0, 55, 5, 5))

        results = idx.nearest((2, 2, 2), max_results=2)

        assert len(results) <= 2
        # Closest should be first
        if results:
            assert results[0] == "close"

    def test_nearest_with_type_filter(self):
        """Test finding nearest with type filter."""
        idx = SpatialIndex()

        idx.insert("face", (0, 0, 0, 10, 10, 10), {'shape_type': 'FACE'})
        idx.insert("edge", (2, 2, 2, 8, 8, 8), {'shape_type': 'EDGE'})

        results = idx.nearest((5, 5, 5), max_results=10, shape_type='FACE')

        assert "face" in results
        assert "edge" not in results

    def test_remove_shape(self):
        """Test removing a shape from the index."""
        idx = SpatialIndex()

        idx.insert("shape1", (0, 0, 0, 10, 10, 10))
        assert "shape1" in idx

        removed = idx.remove("shape1")
        assert removed is True
        assert "shape1" not in idx
        assert idx.size == 0

    def test_remove_nonexistent(self):
        """Test removing a shape that doesn't exist."""
        idx = SpatialIndex()

        removed = idx.remove("nonexistent")
        assert removed is False

    def test_clear(self):
        """Test clearing the index."""
        idx = SpatialIndex()

        idx.insert("shape1", (0, 0, 0, 10, 10, 10))
        idx.insert("shape2", (10, 10, 10, 20, 20, 20))

        assert idx.size == 2

        idx.clear()

        assert idx.size == 0
        assert "shape1" not in idx
        assert "shape2" not in idx

    def test_update_bounds(self):
        """Test updating bounds for existing shape."""
        idx = SpatialIndex()

        idx.insert("shape1", (0, 0, 0, 10, 10, 10))
        old_bounds = idx.get_bounds("shape1")

        idx.update_bounds("shape1", (5, 5, 5, 15, 15, 15))
        new_bounds = idx.get_bounds("shape1")

        assert new_bounds.min_x == 5
        assert old_bounds.min_x == 0

    def test_update_bounds_nonexistent(self):
        """Test updating bounds for nonexistent shape (inserts new)."""
        idx = SpatialIndex()

        idx.update_bounds("shape1", (0, 0, 0, 10, 10, 10))

        assert "shape1" in idx
        assert idx.size == 1

    def test_contains_operator(self):
        """Test using 'in' operator."""
        idx = SpatialIndex()

        idx.insert("shape1", (0, 0, 0, 10, 10, 10))

        assert "shape1" in idx
        assert "shape2" not in idx

    def test_len(self):
        """Test len() function."""
        idx = SpatialIndex()

        assert len(idx) == 0

        idx.insert("shape1", (0, 0, 0, 10, 10, 10))
        assert len(idx) == 1

        idx.insert("shape2", (10, 10, 10, 20, 20, 20))
        assert len(idx) == 2


class TestSpatialIndexLinearFallback:
    """Test SpatialIndex linear search fallback."""

    def test_linear_query_nearby(self):
        """Test linear search for nearby shapes."""
        with patch('modeling.tnp_v5.spatial.HAS_RTREE', False):
            idx = SpatialIndex()

            idx.insert("near1", (0, 0, 0, 10, 10, 10))
            idx.insert("near2", (5, 5, 5, 15, 15, 15))
            idx.insert("far", (100, 100, 100, 110, 110, 110))

            results = idx.query_nearby((5, 5, 5), 20)

            # Should find near shapes
            assert len(results) >= 1
            assert "far" not in results

    def test_linear_nearest(self):
        """Test linear search for nearest shapes."""
        with patch('modeling.tnp_v5.spatial.HAS_RTREE', False):
            idx = SpatialIndex()

            idx.insert("close", (0, 0, 0, 5, 5, 5))
            idx.insert("medium", (10, 0, 0, 15, 5, 5))
            idx.insert("far", (50, 0, 0, 55, 5, 5))

            results = idx.nearest((2, 2, 2))

            assert "close" in results[0]  # Closest should be first


class TestComputeBoundsFromSignature:
    """Test bounds computation from geometric signature."""

    def test_from_signature_with_center(self):
        """Test computing bounds from signature with center."""
        sig = {
            'center': (5, 5, 5)
        }

        bounds = compute_bounds_from_signature(sig)

        assert bounds is not None
        assert bounds.center() == (5, 5, 5)

    def test_from_signature_with_edge_length(self):
        """Test bounds from edge signature uses length."""
        sig = {
            'center': (0, 0, 0),
            'length': 20
        }

        bounds = compute_bounds_from_signature(sig)

        assert bounds is not None
        # Size should be at least half the length
        # Default size 1.0, half length is 10, so size = 10
        assert bounds.max_x - bounds.min_x >= 20

    def test_from_signature_with_face_area(self):
        """Test bounds from face signature uses area."""
        sig = {
            'center': (0, 0, 0),
            'area': 100
        }

        bounds = compute_bounds_from_signature(sig)

        assert bounds is not None
        # Size should be related to sqrt(area) = 10
        # Half of sqrt(100) = 5, but we use full sqrt as size
        # So bounds are from -10 to +10
        assert bounds.max_x - bounds.min_x >= 10

    def test_from_signature_empty(self):
        """Test with empty signature."""
        bounds = compute_bounds_from_signature({})

        assert bounds is None

    def test_from_signature_no_center(self):
        """Test with signature missing center."""
        sig = {'length': 10}

        bounds = compute_bounds_from_signature(sig)

        assert bounds is None


class TestSpatialIndexPerformance:
    """Test performance characteristics of spatial index."""

    def test_query_performance_vs_linear(self):
        """Test that index is faster than linear search for many shapes."""
        # This is more of a regression test
        idx = SpatialIndex()

        # Insert 100 shapes in a grid
        count = 0
        for x in range(0, 100, 10):
            for y in range(0, 100, 10):
                idx.insert(f"shape_{count}", (x, y, 0, x+5, y+5, 5))
                count += 1
                if count >= 100:
                    break
            if count >= 100:
                break

        import time
        start = time.perf_counter()
        results = idx.query_nearby((45, 45, 2), 15)
        duration = (time.perf_counter() - start) * 1000

        # Should complete in reasonable time
        assert duration < 100  # Less than 100ms
        # Should find some shapes
        assert len(results) > 0
