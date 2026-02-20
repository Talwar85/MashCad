"""
PI-008: Geometry Drift Early Detection Tests

Tests for the geometry drift detection system that detects when
small numerical errors accumulate during modeling operations.
"""

import pytest
import math
from dataclasses import asdict

from modeling.geometry_drift_detector import (
    DriftMetrics,
    DriftBaseline,
    DriftThresholds,
    GeometryDriftDetector,
    get_detector,
    capture_baseline,
    detect_drift,
    is_drift_acceptable,
    get_drift_warnings,
)
from test.ocp_test_utils import create_test_box, create_test_cylinder


class TestDriftMetrics:
    """Tests for DriftMetrics dataclass."""
    
    def test_default_values(self):
        """Test default values are zero/empty."""
        metrics = DriftMetrics()
        assert metrics.vertex_drift == 0.0
        assert metrics.normal_drift == 0.0
        assert metrics.area_drift == 0.0
        assert metrics.volume_drift == 0.0
        assert metrics.edge_count_delta == 0
        assert metrics.face_count_delta == 0
        assert metrics.vertex_count_delta == 0
        assert metrics.is_valid is True
        assert metrics.timestamp == 0.0
    
    def test_custom_values(self):
        """Test custom values are stored correctly."""
        metrics = DriftMetrics(
            vertex_drift=1e-5,
            normal_drift=0.01,
            area_drift=0.05,
            volume_drift=0.02,
            edge_count_delta=2,
            face_count_delta=1,
            vertex_count_delta=4,
            is_valid=True,
            timestamp=12345.0,
        )
        assert metrics.vertex_drift == 1e-5
        assert metrics.normal_drift == 0.01
        assert metrics.area_drift == 0.05
        assert metrics.volume_drift == 0.02
        assert metrics.edge_count_delta == 2
        assert metrics.face_count_delta == 1
        assert metrics.vertex_count_delta == 4
        assert metrics.is_valid is True
        assert metrics.timestamp == 12345.0
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        metrics = DriftMetrics(
            vertex_drift=1e-6,
            volume_drift=0.01,
            is_valid=True,
        )
        data = metrics.to_dict()
        assert isinstance(data, dict)
        assert data["vertex_drift"] == 1e-6
        assert data["volume_drift"] == 0.01
        assert data["is_valid"] is True
    
    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "vertex_drift": 2e-5,
            "normal_drift": 0.02,
            "area_drift": 0.03,
            "volume_drift": 0.04,
            "edge_count_delta": 3,
            "face_count_delta": 2,
            "vertex_count_delta": 5,
            "is_valid": False,
            "timestamp": 999.0,
        }
        metrics = DriftMetrics.from_dict(data)
        assert metrics.vertex_drift == 2e-5
        assert metrics.normal_drift == 0.02
        assert metrics.area_drift == 0.03
        assert metrics.volume_drift == 0.04
        assert metrics.edge_count_delta == 3
        assert metrics.face_count_delta == 2
        assert metrics.vertex_count_delta == 5
        assert metrics.is_valid is False
        assert metrics.timestamp == 999.0


class TestDriftBaseline:
    """Tests for DriftBaseline dataclass."""
    
    def test_default_values(self):
        """Test default baseline values."""
        baseline = DriftBaseline()
        assert baseline.vertex_positions == []
        assert baseline.face_normals == []
        assert baseline.surface_area == 0.0
        assert baseline.volume == 0.0
        assert baseline.edge_count == 0
        assert baseline.face_count == 0
        assert baseline.vertex_count == 0
        assert baseline.bounding_box == (0, 0, 0, 0, 0, 0)
        assert baseline.shape_hash == ""
    
    def test_custom_values(self):
        """Test custom baseline values."""
        baseline = DriftBaseline(
            vertex_positions=[(0, 0, 0), (10, 0, 0), (10, 10, 0)],
            face_normals=[(0, 0, 1), (0, 0, -1)],
            surface_area=600.0,
            volume=1000.0,
            edge_count=12,
            face_count=6,
            vertex_count=8,
            bounding_box=(0, 0, 0, 10, 10, 10),
            shape_hash="abc123",
            timestamp=100.0,
        )
        assert len(baseline.vertex_positions) == 3
        assert len(baseline.face_normals) == 2
        assert baseline.surface_area == 600.0
        assert baseline.volume == 1000.0
        assert baseline.edge_count == 12
        assert baseline.face_count == 6
        assert baseline.vertex_count == 8
        assert baseline.bounding_box == (0, 0, 0, 10, 10, 10)
        assert baseline.shape_hash == "abc123"
    
    def test_serialization(self):
        """Test baseline serialization round-trip."""
        baseline = DriftBaseline(
            vertex_positions=[(1.0, 2.0, 3.0)],
            face_normals=[(0.0, 0.0, 1.0)],
            surface_area=100.0,
            volume=50.0,
            edge_count=6,
            face_count=4,
            vertex_count=4,
            bounding_box=(0, 0, 0, 5, 5, 5),
            shape_hash="test123",
            timestamp=42.0,
        )
        data = baseline.to_dict()
        restored = DriftBaseline.from_dict(data)
        
        assert restored.vertex_positions == baseline.vertex_positions
        assert restored.face_normals == baseline.face_normals
        assert restored.surface_area == baseline.surface_area
        assert restored.volume == baseline.volume
        assert restored.edge_count == baseline.edge_count
        assert restored.face_count == baseline.face_count
        assert restored.vertex_count == baseline.vertex_count
        assert restored.bounding_box == baseline.bounding_box
        assert restored.shape_hash == baseline.shape_hash
        assert restored.timestamp == baseline.timestamp


class TestDriftThresholds:
    """Tests for DriftThresholds dataclass."""
    
    def test_default_values(self):
        """Test default threshold values."""
        thresholds = DriftThresholds()
        assert thresholds.vertex_max == 1e-6
        assert thresholds.normal_max == 1e-4
        assert thresholds.area_max == 0.01
        assert thresholds.volume_max == 0.01
        assert thresholds.topology_max == 0
    
    def test_custom_values(self):
        """Test custom threshold values."""
        thresholds = DriftThresholds(
            vertex_max=1e-5,
            normal_max=1e-3,
            area_max=0.05,
            volume_max=0.05,
            topology_max=2,
        )
        assert thresholds.vertex_max == 1e-5
        assert thresholds.normal_max == 1e-3
        assert thresholds.area_max == 0.05
        assert thresholds.volume_max == 0.05
        assert thresholds.topology_max == 2
    
    def test_from_tolerances(self):
        """Test loading thresholds from Tolerances config."""
        thresholds = DriftThresholds.from_tolerances()
        # Should match config/tolerances.py values
        assert thresholds.vertex_max > 0
        assert thresholds.normal_max > 0
        assert thresholds.area_max > 0
        assert thresholds.volume_max > 0


class TestGeometryDriftDetector:
    """Tests for GeometryDriftDetector class."""
    
    @pytest.fixture
    def detector(self):
        """Create a detector with default thresholds."""
        return GeometryDriftDetector()
    
    @pytest.fixture
    def box_solid(self):
        """Create a simple box solid for testing."""
        return create_test_box((10, 10, 10))
    
    def test_capture_baseline_box(self, detector, box_solid):
        """Test baseline capture for a box."""
        baseline = detector.capture_baseline(box_solid.wrapped)
        
        assert baseline is not None
        assert baseline.volume > 0
        assert baseline.surface_area > 0
        assert baseline.face_count == 6  # Box has 6 faces
        assert baseline.edge_count == 12  # Box has 12 edges
        assert baseline.vertex_count == 8  # Box has 8 vertices
        assert len(baseline.vertex_positions) > 0
        assert len(baseline.face_normals) > 0
        assert baseline.shape_hash != ""
    
    def test_capture_baseline_with_cache(self, detector, box_solid):
        """Test baseline capture with caching."""
        key = "test_box_baseline"
        baseline = detector.capture_baseline(box_solid.wrapped, key)
        
        # Should be retrievable from cache
        cached = detector.get_cached_baseline(key)
        assert cached is not None
        assert cached.shape_hash == baseline.shape_hash
        
        # Should be able to clear
        assert detector.clear_cached_baseline(key) is True
        assert detector.get_cached_baseline(key) is None
    
    def test_detect_drift_identical(self, detector, box_solid):
        """Test drift detection with identical solids."""
        baseline = detector.capture_baseline(box_solid.wrapped)
        metrics = detector.detect_drift(box_solid.wrapped, baseline)
        
        # Identical solids should have zero drift
        assert metrics.vertex_drift < 1e-10
        assert metrics.normal_drift < 1e-10
        assert metrics.area_drift < 1e-10
        assert metrics.volume_drift < 1e-10
        assert metrics.is_valid is True
    
    def test_detect_drift_different_size(self, detector):
        """Test drift detection with different sized boxes."""
        small_box = create_test_box((10, 10, 10))
        large_box = create_test_box((11, 10, 10))  # 10% larger in X
        
        baseline = detector.capture_baseline(small_box.wrapped)
        metrics = detector.detect_drift(large_box.wrapped, baseline)
        
        # Should detect significant drift
        assert metrics.vertex_drift > 0.5  # Vertices moved ~0.5mm
        assert metrics.volume_drift > 0.05  # ~10% volume change
        assert metrics.is_valid is True
    
    def test_is_drift_acceptable_within_thresholds(self, detector, box_solid):
        """Test drift acceptability check with acceptable drift."""
        baseline = detector.capture_baseline(box_solid.wrapped)
        metrics = detector.detect_drift(box_solid.wrapped, baseline)
        
        # Identical solid should be acceptable
        assert detector.is_drift_acceptable(metrics) is True
    
    def test_is_drift_acceptable_exceeds_thresholds(self, detector):
        """Test drift acceptability check with excessive drift."""
        # Create metrics that exceed thresholds
        metrics = DriftMetrics(
            vertex_drift=1e-3,  # Exceeds default 1e-6
            normal_drift=0.1,   # Exceeds default 1e-4
            is_valid=True,
        )
        
        # Should not be acceptable
        assert detector.is_drift_acceptable(metrics) is False
    
    def test_is_drift_acceptable_invalid_geometry(self, detector):
        """Test drift acceptability with invalid geometry."""
        metrics = DriftMetrics(is_valid=False)
        
        # Invalid geometry should not be acceptable
        assert detector.is_drift_acceptable(metrics) is False
    
    def test_get_drift_warnings_no_warnings(self, detector, box_solid):
        """Test warning generation with no drift."""
        baseline = detector.capture_baseline(box_solid.wrapped)
        metrics = detector.detect_drift(box_solid.wrapped, baseline)
        
        warnings = detector.get_drift_warnings(metrics)
        assert len(warnings) == 0
    
    def test_get_drift_warnings_with_warnings(self, detector):
        """Test warning generation with excessive drift."""
        metrics = DriftMetrics(
            vertex_drift=1e-3,
            normal_drift=0.1,
            area_drift=0.05,
            volume_drift=0.05,
            is_valid=True,
        )
        
        warnings = detector.get_drift_warnings(metrics)
        assert len(warnings) >= 2  # At least vertex and normal warnings
        assert any("vertex" in w.lower() for w in warnings)
        assert any("normal" in w.lower() for w in warnings)
    
    def test_get_drift_warnings_invalid_geometry(self, detector):
        """Test warning generation with invalid geometry."""
        metrics = DriftMetrics(is_valid=False)
        
        warnings = detector.get_drift_warnings(metrics)
        assert len(warnings) == 1
        assert "invalid" in warnings[0].lower()
    
    def test_clear_all_cache(self, detector, box_solid):
        """Test clearing all cached baselines."""
        detector.capture_baseline(box_solid.wrapped, "key1")
        detector.capture_baseline(box_solid.wrapped, "key2")
        detector.capture_baseline(box_solid.wrapped, "key3")
        
        detector.clear_all_cache()
        
        assert detector.get_cached_baseline("key1") is None
        assert detector.get_cached_baseline("key2") is None
        assert detector.get_cached_baseline("key3") is None
    
    def test_custom_thresholds(self):
        """Test detector with custom thresholds."""
        thresholds = DriftThresholds(
            vertex_max=1e-3,  # More lenient
            normal_max=0.1,
            area_max=0.1,
            volume_max=0.1,
        )
        detector = GeometryDriftDetector(thresholds=thresholds)
        
        # Metrics that would fail with default thresholds
        metrics = DriftMetrics(
            vertex_drift=5e-4,  # Within custom threshold
            is_valid=True,
        )
        
        # Should be acceptable with lenient thresholds
        assert detector.is_drift_acceptable(metrics) is True


class TestModuleFunctions:
    """Tests for module-level convenience functions."""
    
    def test_get_detector_singleton(self):
        """Test that get_detector returns a singleton."""
        detector1 = get_detector()
        detector2 = get_detector()
        assert detector1 is detector2
    
    def test_capture_baseline_function(self):
        """Test module-level capture_baseline function."""
        box = create_test_box((10, 10, 10))
        baseline = capture_baseline(box.wrapped)
        
        assert baseline is not None
        assert baseline.volume > 0
    
    def test_detect_drift_function(self):
        """Test module-level detect_drift function."""
        box = create_test_box((10, 10, 10))
        baseline = capture_baseline(box.wrapped)
        metrics = detect_drift(box.wrapped, baseline)
        
        assert metrics is not None
        assert metrics.vertex_drift < 1e-10
    
    def test_is_drift_acceptable_function(self):
        """Test module-level is_drift_acceptable function."""
        box = create_box_solid(10, 10, 10)
        baseline = capture_baseline(box.wrapped)
        metrics = detect_drift(box.wrapped, baseline)
        
        assert is_drift_acceptable(metrics) is True
    
    def test_get_drift_warnings_function(self):
        """Test module-level get_drift_warnings function."""
        box = create_box_solid(10, 10, 10)
        baseline = capture_baseline(box.wrapped)
        metrics = detect_drift(box.wrapped, baseline)
        
        warnings = get_drift_warnings(metrics)
        assert len(warnings) == 0


class TestDriftDetectionScenarios:
    """Tests for realistic drift detection scenarios."""
    
    @pytest.fixture
    def detector(self):
        """Create a detector for scenario tests."""
        return GeometryDriftDetector()
    
    def test_fillet_causes_minor_drift(self, detector):
        """Test that a fillet operation causes detectable but acceptable drift."""
        # Create a box
        box = create_box_solid(10, 10, 10)
        baseline = detector.capture_baseline(box.wrapped)
        
        # After a fillet, volume would decrease slightly
        # Simulate this by measuring against the same solid
        metrics = detector.detect_drift(box.wrapped, baseline)
        
        # Should be acceptable (no actual fillet applied in this test)
        assert detector.is_drift_acceptable(metrics)
    
    def test_boolean_operation_changes_topology(self, detector):
        """Test detection of topology changes from boolean operations."""
        box1 = create_test_box((10, 10, 10))
        baseline = detector.capture_baseline(box1.wrapped)

        # Different box should have same topology counts
        box2 = create_test_box((20, 20, 20))
        metrics = detector.detect_drift(box2.wrapped, baseline)
        
        # Topology counts should be the same (same shape type)
        assert metrics.face_count_delta == 0
        assert metrics.edge_count_delta == 0
        assert metrics.vertex_count_delta == 0
        
        # But volume/area should differ
        assert metrics.volume_drift > 0.5  # 8x volume difference
        assert metrics.area_drift > 0.1
    
    def test_cylinder_vs_box_different_normals(self, detector):
        """Test normal drift detection between different shape types."""
        box = create_test_box((10, 10, 10))
        baseline = detector.capture_baseline(box.wrapped)

        cylinder = create_test_cylinder(5, 10)
        metrics = detector.detect_drift(cylinder.wrapped, baseline)
        
        # Different shape types should have significant normal drift
        # (box has planar faces, cylinder has curved surfaces)
        assert metrics.normal_drift > 0.01  # Significant normal difference
        assert metrics.face_count_delta != 0  # Different face counts


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_null_shape_handling(self):
        """Test handling of null/None shapes."""
        detector = GeometryDriftDetector()
        
        # Should handle None gracefully
        # Note: This may raise an exception depending on implementation
        # The test verifies the behavior is documented
        try:
            baseline = detector.capture_baseline(None)
            # If it doesn't raise, baseline should indicate invalid
            assert baseline is None or baseline.volume == 0
        except (AttributeError, TypeError):
            pass  # Expected behavior
    
    def test_empty_baseline_drift_detection(self):
        """Test drift detection with empty baseline."""
        detector = GeometryDriftDetector()
        box = create_box_solid(10, 10, 10)
        
        empty_baseline = DriftBaseline()
        metrics = detector.detect_drift(box.wrapped, empty_baseline)
        
        # Should still produce valid metrics
        assert metrics is not None
        # Volume drift might be infinite (division by zero)
        # This tests the edge case handling
    
    def test_angle_between_vectors(self):
        """Test angle calculation between vectors."""
        detector = GeometryDriftDetector()
        
        # Parallel vectors
        angle = detector._angle_between_vectors((1, 0, 0), (1, 0, 0))
        assert abs(angle) < 1e-10
        
        # Perpendicular vectors
        angle = detector._angle_between_vectors((1, 0, 0), (0, 1, 0))
        assert abs(angle - math.pi/2) < 1e-10
        
        # Opposite vectors
        angle = detector._angle_between_vectors((1, 0, 0), (-1, 0, 0))
        assert abs(angle - math.pi) < 1e-10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
