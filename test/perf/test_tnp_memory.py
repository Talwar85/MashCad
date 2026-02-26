"""
TNP v5.0 - Memory Profiling Tests

Tests for memory efficiency and leak detection:
- Memory profiling for TNPService
- Memory profiling for SpatialIndex
- Memory leak detection
- Memory overhead verification
"""

import pytest
import gc
import sys
import weakref
from unittest.mock import Mock
from typing import List

from modeling.tnp_v5 import (
    TNPService,
    ShapeID,
    ShapeType,
    SelectionContext,
    ResolutionOptions,
)
from modeling.tnp_v5.spatial import SpatialIndex, Bounds, QueryCache
from modeling.tnp_v5.types import ShapeRecord


class TestTNPServiceMemory:
    """Test TNPService memory characteristics."""

    def test_service_initial_memory(self):
        """Test service initialization has minimal memory footprint."""
        # Force garbage collection
        gc.collect()

        # Create service
        service = TNPService(document_id="mem_test")

        # Service object should be relatively small
        service_size = sys.getsizeof(service)
        print(f"\nTNPService base size: {service_size} bytes")

        # Base service should be under 10KB
        assert service_size < 10 * 1024, f"Service too large: {service_size} bytes"

    def test_service_memory_per_shape(self):
        """Test memory per registered shape is reasonable."""
        gc.collect()

        service = TNPService(document_id="mem_test")

        # Register 100 shapes
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

        # Get approximate memory usage
        # Note: This is a rough estimate using __sizeof__
        # Real profiling would use memory_profiler or tracemalloc
        shapes_dict_size = sys.getsizeof(service._shapes)

        print(f"\nMemory for 100 shapes:")
        print(f"  Shapes dict: ~{shapes_dict_size} bytes")
        print(f"  Avg per shape: ~{shapes_dict_size / 100:.1f} bytes")

        # Each shape should be under 1KB average
        avg_per_shape = shapes_dict_size / 100
        assert avg_per_shape < 1024, f"Per-shape memory too high: {avg_per_shape:.1f} bytes"

    def test_service_cleanup(self):
        """Test service is properly garbage collected."""
        gc.collect()

        # Create service with weak reference
        service = TNPService(document_id="cleanup_test")
        weak_ref = weakref.ref(service)

        # Delete service
        del service
        gc.collect()

        # Weak ref should be dead (service was collected)
        assert weak_ref() is None, "Service was not garbage collected"

    def test_shape_records_released(self):
        """Test shape records are released when service is deleted."""
        gc.collect()

        # Create a service and register shapes
        service = TNPService(document_id="leak_test")
        shape_ids = []

        for i in range(50):
            shape_id = service.register_shape(
                ocp_shape=Mock(),
                shape_type=ShapeType.EDGE,
                feature_id="test",
                local_index=i,
                context=SelectionContext(
                    shape_id=f"shape_{i}",
                    selection_point=(i, 0, 0),
                    view_direction=(0, 0, 1),
                    adjacent_shapes=[],
                    feature_context="test"
                )
            )
            shape_ids.append(shape_id)

        # Create weak references to shape records
        record_refs = []
        for sid in list(service._shapes.values()):
            record_refs.append(weakref.ref(sid))

        # Delete service
        del service
        del shape_ids
        gc.collect()

        # Most records should be gone (allow a few due to Python's GC behavior)
        surviving = sum(1 for ref in record_refs if ref() is not None)
        print(f"\nShape records after service deletion: {surviving}/{len(record_refs)}")
        # Allow some survivors due to Python's GC not being immediate
        assert surviving < 5, f"{surviving} shape records were not released"


class TestSpatialIndexMemory:
    """Test SpatialIndex memory characteristics."""

    def test_index_initial_memory(self):
        """Test index initialization has minimal footprint."""
        gc.collect()

        index = SpatialIndex()

        # Index with no entries should be small
        index_size = sys.getsizeof(index)
        print(f"\nSpatialIndex base size: {index_size} bytes")

        assert index_size < 5 * 1024, f"Index too large: {index_size} bytes"

    def test_index_memory_per_entry(self):
        """Test memory per spatial index entry is reasonable."""
        gc.collect()

        index = SpatialIndex()

        # Insert 500 entries
        for i in range(500):
            bounds = Bounds(i, i, i, i + 1, i + 1, i + 1)
            index.insert(
                shape_id=f"shape_{i}",
                bounds=bounds,
                shape_data={"type": "FACE", "feature": f"f{i // 10}"}
            )

        # Estimate memory
        index_dict_size = sys.getsizeof(index._shapes)
        avg_per_entry = index_dict_size / 500

        print(f"\nMemory for 500 spatial index entries:")
        print(f"  Index dict: ~{index_dict_size} bytes")
        print(f"  Avg per entry: ~{avg_per_entry:.1f} bytes")

        # Each entry should be under 500 bytes
        assert avg_per_entry < 500, f"Per-entry memory too high: {avg_per_entry:.1f} bytes"

    def test_cache_memory_bounded(self):
        """Test LRU cache memory stays bounded."""
        gc.collect()

        cache = QueryCache(max_size=100)

        # Fill cache with 200 entries (should evict oldest 100)
        for i in range(200):
            cache.put((i, 0, 0), 10, None, [f"result_{i}"])

        # Cache size should be bounded by max_size
        cache_size = len(cache._cache)
        print(f"\nCache size after 200 inserts with max_size=100: {cache_size}")

        assert cache_size <= 100, f"Cache exceeded max_size: {cache_size}"

    def test_index_cleanup(self):
        """Test index is properly garbage collected."""
        gc.collect()

        index = SpatialIndex()
        weak_ref = weakref.ref(index)

        # Add some entries
        for i in range(50):
            bounds = Bounds(i, i, i, i + 1, i + 1, i + 1)
            index.insert(f"shape_{i}", bounds, {})

        # Delete index
        del index
        gc.collect()

        assert weak_ref() is None, "Index was not garbage collected"


class TestMemoryLeaks:
    """Test for memory leaks in critical operations."""

    def test_no_leak_on_repeated_registration(self):
        """Test repeated registration doesn't leak memory."""
        gc.collect()

        # Get baseline memory
        baseline_objs = len(gc.get_objects())

        # Perform many registrations
        for iteration in range(10):
            service = TNPService(document_id=f"leak_test_{iteration}")

            for i in range(50):
                service.register_shape(
                    ocp_shape=Mock(),
                    shape_type=ShapeType.EDGE,
                    feature_id="test",
                    local_index=i,
                    context=SelectionContext(
                        shape_id=f"shape_{i}",
                        selection_point=(i, 0, 0),
                        view_direction=(0, 0, 1),
                        adjacent_shapes=[],
                        feature_context="test"
                    )
                )

            # Delete service
            del service

        gc.collect()

        # Check object count hasn't grown significantly
        current_objs = len(gc.get_objects())
        growth = current_objs - baseline_objs

        print(f"\nObject growth after 500 registrations: {growth}")

        # Allow some growth but not excessive
        # Growth should be much less than the number of shapes created
        assert growth < 5000, f"Excessive object growth: {growth}"

    def test_no_leak_on_repeated_resolution(self):
        """Test repeated resolution doesn't leak memory."""
        gc.collect()

        service = TNPService(document_id="resolve_leak_test")

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

        # Get baseline
        gc.collect()
        baseline_objs = len(gc.get_objects())

        # Perform many resolutions
        for _ in range(1000):
            service.resolve(shape_id, Mock(), ResolutionOptions())

        gc.collect()
        current_objs = len(gc.get_objects())
        growth = current_objs - baseline_objs

        print(f"\nObject growth after 1000 resolutions: {growth}")

        # Growth should be minimal - allow some overhead for Python's GC behavior
        # Each resolution creates some temporary objects (ResolutionResult, candidates, etc.)
        # With 1000 iterations, some growth is expected
        assert growth < 15000, f"Excessive object growth from resolution: {growth}"

    def test_no_leak_on_spatial_queries(self):
        """Test spatial queries don't leak memory."""
        gc.collect()

        index = SpatialIndex()

        # Insert shapes
        for i in range(200):
            bounds = Bounds(i, i, i, i + 1, i + 1, i + 1)
            index.insert(f"shape_{i}", bounds, {})

        gc.collect()
        baseline_objs = len(gc.get_objects())

        # Perform many queries
        for _ in range(1000):
            index.query_nearby((100, 100, 100), radius=10)
            index.nearest((100, 100, 100))

        gc.collect()
        current_objs = len(gc.get_objects())
        growth = current_objs - baseline_objs

        print(f"\nObject growth after 2000 spatial queries: {growth}")

        assert growth < 100, f"Excessive object growth from spatial queries: {growth}"

    def test_cache_evicts_old_entries(self):
        """Test LRU cache properly evicts old entries."""
        gc.collect()

        cache = QueryCache(max_size=10)

        # Fill cache
        for i in range(10):
            cache.put((i, 0, 0), 10, None, [f"data_{i}"])

        # All should be present
        assert len(cache._cache) == 10

        # Add more entries
        for i in range(10, 20):
            cache.put((i, 0, 0), 10, None, [f"data_{i}"])

        # Size should still be 10 (LRU eviction)
        assert len(cache._cache) == 10

        # Old entries should be evicted
        assert cache.get((0, 0, 0), 10, None) is None
        assert cache.get((5, 0, 0), 10, None) is None
        # Recent entries should be present
        assert cache.get((15, 0, 0), 10, None) is not None


class TestMemoryOverhead:
    """Test memory overhead is within acceptable limits."""

    def test_overhead_vs_baseline(self):
        """Compare TNP v5.0 memory vs simple dictionary baseline."""
        gc.collect()

        # Baseline: Simple dictionary storage
        class SimpleRegistry:
            def __init__(self):
                self._shapes = {}

            def add(self, shape_id, data):
                self._shapes[shape_id] = data

        baseline = SimpleRegistry()
        for i in range(100):
            baseline.add(f"shape_{i}", {"type": "EDGE", "index": i})

        baseline_size = sys.getsizeof(baseline._shapes)

        # TNP v5.0 service
        gc.collect()
        service = TNPService(document_id="overhead_test")

        for i in range(100):
            service.register_shape(
                ocp_shape=Mock(),
                shape_type=ShapeType.EDGE,
                feature_id="test",
                local_index=i,
                context=SelectionContext(
                    shape_id=f"shape_{i}",
                    selection_point=(i, 0, 0),
                    view_direction=(0, 0, 1),
                    adjacent_shapes=[],
                    feature_context="test"
                )
            )

        service_size = sys.getsizeof(service._shapes)

        overhead_ratio = service_size / baseline_size if baseline_size > 0 else 1

        print(f"\nMemory overhead comparison:")
        print(f"  Baseline dict: {baseline_size} bytes")
        print(f"  TNP v5.0 dict: {service_size} bytes")
        print(f"  Overhead ratio: {overhead_ratio:.2f}x")

        # Overhead should be reasonable (< 10x)
        assert overhead_ratio < 10, f"Memory overhead too high: {overhead_ratio:.2f}x"

    def test_spatial_index_overhead(self):
        """Test spatial index overhead vs simple list."""
        gc.collect()

        # Baseline: Simple list
        shape_list = []
        for i in range(200):
            shape_list.append({
                "id": f"shape_{i}",
                "bounds": (i, i, i, i + 1, i + 1, i + 1)
            })

        baseline_size = sys.getsizeof(shape_list)
        for item in shape_list:
            baseline_size += sys.getsizeof(item)

        # Spatial index
        gc.collect()
        index = SpatialIndex()

        for i in range(200):
            bounds = Bounds(i, i, i, i + 1, i + 1, i + 1)
            index.insert(f"shape_{i}", bounds, {})

        # Estimate index size
        index_size = sys.getsizeof(index._shapes)

        overhead_ratio = index_size / baseline_size if baseline_size > 0 else 1

        print(f"\nSpatial index overhead:")
        print(f"  Baseline list: {baseline_size} bytes")
        print(f"  Spatial index: {index_size} bytes")
        print(f"  Overhead ratio: {overhead_ratio:.2f}x")

        # Spatial index should have reasonable overhead
        assert overhead_ratio < 5, f"Spatial index overhead too high: {overhead_ratio:.2f}x"


class TestMemoryStress:
    """Test memory behavior under stress."""

    def test_large_document_handling(self):
        """Test handling a large document doesn't cause issues."""
        gc.collect()

        service = TNPService(document_id="large_doc")

        # Register 1000 shapes (simulating a large document)
        num_shapes = 1000
        shape_uuids = []
        for i in range(num_shapes):
            shape_id = service.register_shape(
                ocp_shape=Mock(),
                shape_type=ShapeType.EDGE,
                feature_id=f"feature_{i // 10}",
                local_index=i % 10,
                context=SelectionContext(
                    shape_id=f"shape_{i}",
                    selection_point=(i % 100, (i // 100) % 100, i // 10000),
                    view_direction=(0, 0, 1),
                    adjacent_shapes=[],
                    feature_context=f"feature_{i // 10}"
                )
            )
            shape_uuids.append(shape_id.uuid)

        # Should be able to retrieve all shapes
        count = 0
        for uuid in shape_uuids:
            record = service.get_shape_record(uuid)
            if record:
                count += 1

        assert count == num_shapes, f"Lost shapes: expected {num_shapes}, got {count}"

    def test_cache_under_pressure(self):
        """Test cache behavior under memory pressure."""
        gc.collect()

        cache = QueryCache(max_size=50)

        # Fill cache
        for i in range(50):
            cache.put((i, 0, 0), 10, None, [f"data_{i}"])

        assert len(cache._cache) == 50

        # Add more entries (should trigger eviction)
        for i in range(50, 150):
            cache.put((i, 0, 0), 10, None, [f"data_{i}"])

        # Size should stay at max
        assert len(cache._cache) == 50

        # Hit rate should be reasonable
        hits = 0
        for i in range(100, 150):  # Recent entries
            if cache.get((i, 0, 0), 10, None) is not None:
                hits += 1

        hit_rate = hits / 50
        print(f"\nCache hit rate for recent entries: {hit_rate:.1%}")
        assert hit_rate > 0.5, f"Cache hit rate too low: {hit_rate:.1%}"


class TestMemoryProfilingSummary:
    """Summary of memory profiling results."""

    def test_memory_profile_summary(self):
        """Generate summary of memory characteristics."""
        gc.collect()

        results = {
            "service_base_size": 0,
            "service_per_shape": 0,
            "index_base_size": 0,
            "index_per_entry": 0,
            "overhead_ratio": 0,
        }

        # Measure service base size
        service = TNPService(document_id="summary_test")
        results["service_base_size"] = sys.getsizeof(service)

        # Measure per-shape memory
        for i in range(100):
            service.register_shape(
                ocp_shape=Mock(),
                shape_type=ShapeType.EDGE,
                feature_id="test",
                local_index=i,
                context=None
            )
        results["service_per_shape"] = sys.getsizeof(service._shapes) / 100

        # Measure index
        gc.collect()
        index = SpatialIndex()
        results["index_base_size"] = sys.getsizeof(index)

        for i in range(200):
            bounds = Bounds(i, i, i, i + 1, i + 1, i + 1)
            index.insert(f"shape_{i}", bounds, {})
        results["index_per_entry"] = sys.getsizeof(index._shapes) / 200

        print(f"\n{'=' * 60}")
        print(f"MEMORY PROFILING SUMMARY")
        print(f"{'=' * 60}")
        print(f"TNPService:")
        print(f"  Base size: {results['service_base_size']} bytes")
        print(f"  Per shape: {results['service_per_shape']:.1f} bytes")
        print(f"\nSpatialIndex:")
        print(f"  Base size: {results['index_base_size']} bytes")
        print(f"  Per entry: {results['index_per_entry']:.1f} bytes")
        print(f"\nMemory Targets:")
        print(f"  Per-shape < 1KB: {'✓' if results['service_per_shape'] < 1024 else '✗'}")
        print(f"  Per-entry < 500B: {'✓' if results['index_per_entry'] < 500 else '✗'}")
        print(f"  Service base < 10KB: {'✓' if results['service_base_size'] < 10240 else '✗'}")
        print(f"{'=' * 60}")

        # Verify targets
        assert results["service_per_shape"] < 1024, "Per-shape memory too high"
        assert results["index_per_entry"] < 500, "Per-entry memory too high"
        assert results["service_base_size"] < 10240, "Service base size too high"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
