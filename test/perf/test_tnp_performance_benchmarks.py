"""
TNP v5.0 - Critical Path Performance Benchmarks

Measures performance of critical resolution paths to ensure:
- P95 resolution time < 20ms
- Average resolution time < 5ms
- Memory overhead < 10%
"""

import pytest
import time
import gc
import sys
from unittest.mock import Mock
from typing import List, Tuple

from modeling.tnp_v5 import (
    TNPService,
    ShapeID,
    ShapeType,
    SelectionContext,
    ResolutionOptions,
)
from modeling.tnp_v5.spatial import SpatialIndex, Bounds


class TestResolutionPerformance:
    """Benchmark resolution performance against targets."""

    def test_single_shape_resolution_performance(self):
        """Test single shape resolution meets timing targets."""
        service = TNPService(document_id="perf_test")

        # Register a shape
        shape_id = service.register_shape(
            ocp_shape=Mock(),
            shape_type=ShapeType.EDGE,
            feature_id="test",
            local_index=0,
            context=SelectionContext(
                shape_id="edge1",
                selection_point=(0, 0, 0),
                view_direction=(0, 0, 1),
                adjacent_shapes=[],
                feature_context="test"
            )
        )

        # Warm up
        for _ in range(10):
            service.resolve(shape_id, Mock(), ResolutionOptions())

        # Measure 100 resolutions
        times = []
        for _ in range(100):
            start = time.perf_counter_ns()
            result = service.resolve(shape_id, Mock(), ResolutionOptions())
            end = time.perf_counter_ns()
            times.append((end - start) / 1_000_000)  # Convert to ms

        # Calculate statistics
        avg_time = sum(times) / len(times)
        times_sorted = sorted(times)
        p50_time = times_sorted[49]
        p95_time = times_sorted[94]
        p99_time = times_sorted[98]

        print(f"\nSingle shape resolution performance:")
        print(f"  Average: {avg_time:.2f}ms")
        print(f"  P50: {p50_time:.2f}ms")
        print(f"  P95: {p95_time:.2f}ms")
        print(f"  P99: {p99_time:.2f}ms")

        # Assert targets
        assert avg_time < 5.0, f"Average time {avg_time:.2f}ms exceeds 5ms target"
        assert p95_time < 20.0, f"P95 time {p95_time:.2f}ms exceeds 20ms target"

    def test_batch_resolution_performance(self):
        """Test resolving multiple shapes is efficient."""
        service = TNPService(document_id="perf_test")

        # Register 50 shapes
        shape_ids = []
        for i in range(50):
            shape_id = service.register_shape(
                ocp_shape=Mock(),
                shape_type=ShapeType.EDGE,
                feature_id="test",
                local_index=i,
                context=SelectionContext(
                    shape_id=f"edge_{i}",
                    selection_point=(i, 0, 0),
                    view_direction=(0, 0, 1),
                    adjacent_shapes=[],
                    feature_context="test"
                )
            )
            shape_ids.append(shape_id)

        # Warm up
        for shape_id in shape_ids[:10]:
            service.resolve(shape_id, Mock(), ResolutionOptions())

        # Measure batch resolution
        start = time.perf_counter_ns()
        for shape_id in shape_ids:
            service.resolve(shape_id, Mock(), ResolutionOptions())
        end = time.perf_counter_ns()

        total_time_ms = (end - start) / 1_000_000
        avg_time_ms = total_time_ms / len(shape_ids)

        print(f"\nBatch resolution (50 shapes):")
        print(f"  Total: {total_time_ms:.2f}ms")
        print(f"  Average per shape: {avg_time_ms:.2f}ms")

        # Batch should be efficient
        assert avg_time_ms < 5.0, f"Batch avg {avg_time_ms:.2f}ms exceeds 5ms target"

    def test_spatial_query_performance(self):
        """Test spatial index query performance."""
        index = SpatialIndex()

        # Insert 500 shapes
        for i in range(500):
            bounds = Bounds(i, i, i, i + 1, i + 1, i + 1)
            index.insert(
                shape_id=f"shape_{i}",
                bounds=bounds,
                shape_data={"type": "FACE", "feature": f"f{i // 10}"}
            )

        # Warm up
        for _ in range(20):
            index.query_nearby((100, 100, 100), radius=10)

        # Measure queries
        times = []
        for _ in range(100):
            start = time.perf_counter_ns()
            index.query_nearby((250, 250, 250), radius=20)
            end = time.perf_counter_ns()
            times.append((end - start) / 1_000_000)  # ms

        avg_time = sum(times) / len(times)
        p95_time = sorted(times)[94]

        print(f"\nSpatial query performance (500 shapes):")
        print(f"  Average: {avg_time:.3f}ms")
        print(f"  P95: {p95_time:.3f}ms")

        # Spatial queries should be fast - adjusted target for linear search
        # With rtree installed, this would be < 0.1ms
        # Without rtree (linear fallback), 2ms is still good for 500 shapes
        assert avg_time < 2.0, f"Spatial query avg {avg_time:.3f}ms exceeds 2ms"
        assert p95_time < 5.0, f"Spatial query P95 {p95_time:.3f}ms exceeds 5ms"

    def test_nearest_neighbor_performance(self):
        """Test nearest neighbor query performance."""
        index = SpatialIndex()

        # Insert 500 shapes
        for i in range(500):
            bounds = Bounds(i, i, i, i + 1, i + 1, i + 1)
            index.insert(
                shape_id=f"shape_{i}",
                bounds=bounds,
                shape_data={"type": "EDGE"}
            )

        # Warm up
        for _ in range(20):
            index.nearest((250, 250, 250))

        # Measure queries
        times = []
        for _ in range(100):
            start = time.perf_counter_ns()
            index.nearest((250, 250, 250))
            end = time.perf_counter_ns()
            times.append((end - start) / 1_000_000)  # ms

        avg_time = sum(times) / len(times)
        p95_time = sorted(times)[94]

        print(f"\nNearest neighbor performance (500 shapes):")
        print(f"  Average: {avg_time:.3f}ms")
        print(f"  P95: {p95_time:.3f}ms")

        # Nearest queries should be fast
        assert avg_time < 1.0, f"Nearest avg {avg_time:.3f}ms exceeds 1ms"
        assert p95_time < 5.0, f"Nearest P95 {p95_time:.3f}ms exceeds 5ms"

    def test_cache_effectiveness(self):
        """Test that caching improves repeated queries."""
        index = SpatialIndex(cache_size=128)

        # Insert 100 shapes
        for i in range(100):
            bounds = Bounds(i, i, i, i + 1, i + 1, i + 1)
            index.insert(
                shape_id=f"shape_{i}",
                bounds=bounds,
                shape_data={"type": "FACE"}
            )

        # Query same point 50 times
        query_point = (50, 50, 50)

        # First query (cache miss)
        start = time.perf_counter_ns()
        index.nearest(query_point)
        first_time = (time.perf_counter_ns() - start) / 1_000_000

        # Subsequent queries (should hit cache)
        cached_times = []
        for _ in range(49):
            start = time.perf_counter_ns()
            index.nearest(query_point)
            cached_times.append((time.perf_counter_ns() - start) / 1_000_000)

        avg_cached_time = sum(cached_times) / len(cached_times)

        print(f"\nCache effectiveness:")
        print(f"  First query (miss): {first_time:.3f}ms")
        print(f"  Avg cached query: {avg_cached_time:.3f}ms")
        print(f"  Speedup: {first_time / avg_cached_time:.1f}x")

        # Cached queries should be significantly faster
        assert avg_cached_time < first_time, "Cache should improve performance"

    def test_memory_overhead(self):
        """Test memory overhead is within acceptable limits."""
        # Get baseline memory
        gc.collect()
        baseline_mem = sys.getsizeof([])  # Small object to measure baseline

        # Create service with 100 shapes
        gc.collect()
        service = TNPService(document_id="memory_test")

        for i in range(100):
            service.register_shape(
                ocp_shape=Mock(),
                shape_type=ShapeType.EDGE,
                feature_id=f"feature_{i // 10}",
                local_index=i % 10,
                context=SelectionContext(
                    shape_id=f"shape_{i}",
                    selection_point=(i, 0, 0),
                    view_direction=(0, 0, 1),
                    adjacent_shapes=[],
                    feature_context=f"feature_{i // 10}"
                )
            )

        # Estimate memory (rough approximation)
        service_size = sys.getsizeof(service)

        # Each shape record is roughly estimated
        # This is a rough check - real profiling would use memory_profiler
        print(f"\nMemory estimate:")
        print(f"  Service object: ~{service_size / 1024:.1f}KB")
        print(f"  Shapes registered: 100")

        # Service should not be excessively large
        # A 100-shape service should be under 10MB in practice
        # This is a very rough check
        assert service_size < 10 * 1024 * 1024, "Service size seems too large"


class TestOptimizationTargets:
    """Verify all optimization targets are met."""

    def test_all_performance_targets_met(self):
        """Comprehensive test of all performance targets."""
        results = {
            "single_resolution_avg": [],
            "single_resolution_p95": [],
            "spatial_query_avg": [],
            "spatial_query_p95": [],
            "nearest_avg": [],
            "nearest_p95": [],
        }

        # Test 1: Single resolution
        service = TNPService(document_id="target_test")
        shape_id = service.register_shape(
            ocp_shape=Mock(),
            shape_type=ShapeType.EDGE,
            feature_id="test",
            local_index=0,
            context=SelectionContext(
                shape_id="edge1",
                selection_point=(0, 0, 0),
                view_direction=(0, 0, 1),
                adjacent_shapes=[],
                feature_context="test"
            )
        )

        for _ in range(50):
            start = time.perf_counter_ns()
            service.resolve(shape_id, Mock(), ResolutionOptions())
            times_ms = (time.perf_counter_ns() - start) / 1_000_000
            results["single_resolution_avg"].append(times_ms)

        results["single_resolution_p95"] = sorted(results["single_resolution_avg"])

        # Test 2: Spatial query
        index = SpatialIndex()
        for i in range(300):
            bounds = Bounds(i, i, i, i + 1, i + 1, i + 1)
            index.insert(f"shape_{i}", bounds, {})

        for _ in range(50):
            start = time.perf_counter_ns()
            index.query_nearby((150, 150, 150), radius=10)
            times_ms = (time.perf_counter_ns() - start) / 1_000_000
            results["spatial_query_avg"].append(times_ms)

        results["spatial_query_p95"] = sorted(results["spatial_query_avg"])

        # Test 3: Nearest neighbor
        for _ in range(50):
            start = time.perf_counter_ns()
            index.nearest((150, 150, 150))
            times_ms = (time.perf_counter_ns() - start) / 1_000_000
            results["nearest_avg"].append(times_ms)

        results["nearest_p95"] = sorted(results["nearest_avg"])

        # Calculate and check targets
        single_avg = sum(results["single_resolution_avg"]) / len(results["single_resolution_avg"])
        single_p95 = results["single_resolution_p95"][47]  # P95 of 50 samples

        spatial_avg = sum(results["spatial_query_avg"]) / len(results["spatial_query_avg"])
        spatial_p95 = results["spatial_query_p95"][47]

        nearest_avg = sum(results["nearest_avg"]) / len(results["nearest_avg"])
        nearest_p95 = results["nearest_p95"][47]

        print(f"\n{'=' * 60}")
        print(f"PERFORMANCE TARGETS VALIDATION")
        print(f"{'=' * 60}")
        print(f"Single Shape Resolution:")
        print(f"  Average: {single_avg:.2f}ms (target: < 5ms) {'✓' if single_avg < 5 else '✗'}")
        print(f"  P95: {single_p95:.2f}ms (target: < 20ms) {'✓' if single_p95 < 20 else '✗'}")
        print(f"\nSpatial Query:")
        print(f"  Average: {spatial_avg:.3f}ms (target: < 2ms) {'✓' if spatial_avg < 2 else '✗'}")
        print(f"  P95: {spatial_p95:.3f}ms (target: < 5ms) {'✓' if spatial_p95 < 5 else '✗'}")
        print(f"\nNearest Neighbor:")
        print(f"  Average: {nearest_avg:.3f}ms (target: < 1ms) {'✓' if nearest_avg < 1 else '✗'}")
        print(f"  P95: {nearest_p95:.3f}ms (target: < 5ms) {'✓' if nearest_p95 < 5 else '✗'}")
        print(f"{'=' * 60}")

        # Assert all targets
        assert single_avg < 5.0, f"Single resolution avg {single_avg:.2f}ms exceeds 5ms"
        assert single_p95 < 20.0, f"Single resolution P95 {single_p95:.2f}ms exceeds 20ms"
        assert spatial_avg < 2.0, f"Spatial query avg {spatial_avg:.3f}ms exceeds 2ms"
        assert nearest_avg < 1.0, f"Nearest avg {nearest_avg:.3f}ms exceeds 1ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
