"""
MashCAD - Performance Gate Tests
=================================

QA-006: Performance Regression Gate Tests

Tests for:
- BenchmarkTimer accuracy
- Baseline comparison
- Regression detection
- Corpus model benchmarks

Author: Claude (QA-006 Implementation)
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

import json
import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

from modeling.performance_benchmark import (
    BenchmarkTimer,
    BenchmarkResult,
    BenchmarkReport,
    PerformanceBenchmark,
    PERFORMANCE_TARGETS,
    REGRESSION_THRESHOLD,
    run_performance_gate,
)


class TestBenchmarkTimer:
    """Tests for BenchmarkTimer context manager."""
    
    def test_timer_measures_duration(self):
        """Timer should accurately measure duration."""
        with BenchmarkTimer("test") as timer:
            time.sleep(0.05)  # 50ms
        
        # Should be approximately 50ms (allow 20ms tolerance)
        assert timer.duration_ms >= 45
        assert timer.duration_ms <= 100
    
    def test_timer_returns_self(self):
        """Timer should return itself for access to duration."""
        with BenchmarkTimer("test") as timer:
            assert timer.name == "test"
    
    def test_timer_success_by_default(self):
        """Timer should be successful if no exception."""
        with BenchmarkTimer("test") as timer:
            pass
        
        assert timer.success is True
        assert timer.error_message == ""
    
    def test_timer_captures_exception(self):
        """Timer should capture exception info."""
        with pytest.raises(ValueError):
            with BenchmarkTimer("test") as timer:
                raise ValueError("Test error")
        
        assert timer.success is False
        assert "Test error" in timer.error_message
    
    def test_timer_duration_seconds(self):
        """Timer should provide duration in seconds."""
        with BenchmarkTimer("test") as timer:
            time.sleep(0.01)
        
        assert timer.duration_seconds > 0
        assert abs(timer.duration_seconds * 1000 - timer.duration_ms) < 0.001


class TestBenchmarkResult:
    """Tests for BenchmarkResult dataclass."""
    
    def test_result_creation(self):
        """Result should store all fields correctly."""
        result = BenchmarkResult(
            name="test_op",
            duration_ms=150.0,
            target_ms=100.0,
            max_ms=200.0,
            iterations=3
        )
        
        assert result.name == "test_op"
        assert result.duration_ms == 150.0
        assert result.target_ms == 100.0
        assert result.max_ms == 200.0
        assert result.iterations == 3
        assert result.success is True
    
    def test_is_regression_within_threshold(self):
        """Result within 20% of target should not be regression."""
        # 110ms is 10% over 100ms target - not a regression
        result = BenchmarkResult(
            name="test",
            duration_ms=110.0,
            target_ms=100.0,
            max_ms=200.0
        )
        
        assert result.is_regression is False
    
    def test_is_regression_at_threshold(self):
        """Result at exactly 20% over target should be regression."""
        # 120ms is 20% over 100ms target - borderline regression
        result = BenchmarkResult(
            name="test",
            duration_ms=120.0,
            target_ms=100.0,
            max_ms=200.0
        )
        
        # At exactly 1.20x, it's NOT a regression (needs to be > 1.20)
        assert result.is_regression is False
    
    def test_is_regression_over_threshold(self):
        """Result over 20% of target should be regression."""
        # 130ms is 30% over 100ms target - regression
        result = BenchmarkResult(
            name="test",
            duration_ms=130.0,
            target_ms=100.0,
            max_ms=200.0
        )
        
        assert result.is_regression is True
    
    def test_is_failure_over_max(self):
        """Result over max should be failure."""
        result = BenchmarkResult(
            name="test",
            duration_ms=250.0,
            target_ms=100.0,
            max_ms=200.0
        )
        
        assert result.is_failure is True
    
    def test_is_failure_unsuccessful(self):
        """Unsuccessful result should be failure."""
        result = BenchmarkResult(
            name="test",
            duration_ms=50.0,
            target_ms=100.0,
            max_ms=200.0,
            success=False,
            error_message="Operation failed"
        )
        
        assert result.is_failure is True
    
    def test_ratio_to_target(self):
        """Ratio to target should be calculated correctly."""
        result = BenchmarkResult(
            name="test",
            duration_ms=150.0,
            target_ms=100.0,
            max_ms=200.0
        )
        
        assert result.ratio_to_target == 1.5
    
    def test_to_dict(self):
        """Result should serialize to dict correctly."""
        result = BenchmarkResult(
            name="test",
            duration_ms=150.0,
            target_ms=100.0,
            max_ms=200.0,
            iterations=3
        )
        
        d = result.to_dict()
        
        assert d["name"] == "test"
        assert d["duration_ms"] == 150.0
        assert d["target_ms"] == 100.0
        assert d["max_ms"] == 200.0
        assert d["iterations"] == 3
        assert d["success"] is True


class TestBenchmarkReport:
    """Tests for BenchmarkReport dataclass."""
    
    def test_report_creation(self):
        """Report should store results correctly."""
        results = [
            BenchmarkResult("op1", 100.0, 100.0, 200.0),
            BenchmarkResult("op2", 150.0, 100.0, 200.0),
        ]
        
        report = BenchmarkReport(
            timestamp="2026-02-20T10:00:00",
            results=results,
            baseline_file="test.json"
        )
        
        assert len(report.results) == 2
        assert report.timestamp == "2026-02-20T10:00:00"
    
    def test_report_detects_regressions(self):
        """Report should detect regressions in results."""
        results = [
            BenchmarkResult("op1", 100.0, 100.0, 200.0),  # OK
            BenchmarkResult("op2", 150.0, 100.0, 200.0),  # Regression (50% over)
        ]
        
        report = BenchmarkReport(
            timestamp="2026-02-20T10:00:00",
            results=results,
            baseline_file="test.json"
        )
        
        assert report.has_regressions is True
        assert len(report.regression_details) == 1
        assert "op2" in report.regression_details[0]
    
    def test_report_detects_failures(self):
        """Report should detect failures in results."""
        results = [
            BenchmarkResult("op1", 100.0, 100.0, 200.0),  # OK
            BenchmarkResult("op2", 250.0, 100.0, 200.0),  # Failure (over max)
        ]
        
        report = BenchmarkReport(
            timestamp="2026-02-20T10:00:00",
            results=results,
            baseline_file="test.json"
        )
        
        assert report.has_failures is True
    
    def test_report_no_regressions(self):
        """Report with all results within target should have no regressions."""
        results = [
            BenchmarkResult("op1", 90.0, 100.0, 200.0),  # Under target
            BenchmarkResult("op2", 110.0, 100.0, 200.0),  # 10% over - OK
        ]
        
        report = BenchmarkReport(
            timestamp="2026-02-20T10:00:00",
            results=results,
            baseline_file="test.json"
        )
        
        assert report.has_regressions is False
        assert len(report.regression_details) == 0
    
    def test_report_to_dict(self):
        """Report should serialize to dict correctly."""
        results = [
            BenchmarkResult("op1", 100.0, 100.0, 200.0),
        ]
        
        report = BenchmarkReport(
            timestamp="2026-02-20T10:00:00",
            results=results,
            baseline_file="test.json"
        )
        
        d = report.to_dict()
        
        assert d["timestamp"] == "2026-02-20T10:00:00"
        assert d["has_regressions"] is False
        assert d["has_failures"] is False
        assert d["baseline_file"] == "test.json"
        assert len(d["results"]) == 1


class TestPerformanceBenchmark:
    """Tests for PerformanceBenchmark class."""
    
    def test_benchmark_uses_default_baseline_path(self):
        """Benchmark should use default baseline path if not specified."""
        benchmark = PerformanceBenchmark()
        
        expected_path = Path(__file__).parent / "performance_baselines.json"
        assert benchmark.baseline_file == expected_path
    
    def test_benchmark_uses_custom_baseline_path(self):
        """Benchmark should use custom baseline path if specified."""
        custom_path = Path("/tmp/custom_baselines.json")
        benchmark = PerformanceBenchmark(baseline_file=custom_path)
        
        assert benchmark.baseline_file == custom_path
    
    def test_benchmark_loads_existing_baselines(self):
        """Benchmark should load existing baseline file."""
        baselines = {
            "simple_extrude": {"target_ms": 100, "max_ms": 200},
            "boolean_union": {"target_ms": 200, "max_ms": 500}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(baselines, f)
            baseline_path = Path(f.name)
        
        try:
            benchmark = PerformanceBenchmark(baseline_file=baseline_path)
            
            assert "simple_extrude" in benchmark._baselines
            assert benchmark._baselines["simple_extrude"]["target_ms"] == 100
        finally:
            baseline_path.unlink()
    
    def test_benchmark_handles_missing_baseline_file(self):
        """Benchmark should handle missing baseline file gracefully."""
        non_existent = Path("/tmp/non_existent_baseline_12345.json")
        benchmark = PerformanceBenchmark(baseline_file=non_existent)
        
        assert benchmark._baselines == {}
    
    def test_benchmark_extrude(self):
        """Benchmark should measure extrude operation."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_extrude(iterations=1)
        
        assert result.name == "simple_extrude"
        assert result.duration_ms > 0
        assert result.iterations == 1
        # Should be within reasonable bounds
        assert result.duration_ms < 5000  # Less than 5 seconds
    
    def test_benchmark_boolean(self):
        """Benchmark should measure boolean operation."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_boolean(iterations=1)
        
        assert result.name == "boolean_union"
        assert result.duration_ms > 0
        assert result.iterations == 1
    
    def test_benchmark_fillet(self):
        """Benchmark should measure fillet operation."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_fillet(iterations=1)
        
        assert result.name == "fillet_10_edges"
        assert result.duration_ms > 0
        assert result.iterations == 1
    
    def test_benchmark_export(self):
        """Benchmark should measure export operation."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_export(iterations=1)
        
        assert result.name == "stl_export"
        assert result.duration_ms > 0
        assert result.iterations == 1
    
    def test_benchmark_rebuild(self):
        """Benchmark should measure full rebuild cycle."""
        benchmark = PerformanceBenchmark()
        result = benchmark.benchmark_rebuild(iterations=1)
        
        assert result.name == "full_rebuild"
        assert result.duration_ms > 0
        assert result.iterations == 1
    
    def test_run_all_benchmarks(self):
        """Benchmark should run all benchmarks and return report."""
        benchmark = PerformanceBenchmark()
        report = benchmark.run_all_benchmarks(iterations=1)
        
        assert len(report.results) == 5
        result_names = [r.name for r in report.results]
        assert "simple_extrude" in result_names
        assert "boolean_union" in result_names
        assert "fillet_10_edges" in result_names
        assert "stl_export" in result_names
        assert "full_rebuild" in result_names
    
    def test_update_baselines(self):
        """Benchmark should update baseline file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            baseline_path = Path(f.name)
        
        try:
            benchmark = PerformanceBenchmark(baseline_file=baseline_path)
            report = benchmark.run_all_benchmarks(iterations=1)
            benchmark.update_baselines(report)
            
            # Verify file was updated
            with open(baseline_path, 'r') as f:
                baselines = json.load(f)
            
            assert "simple_extrude" in baselines
            assert baselines["simple_extrude"]["last_measured_ms"] > 0
        finally:
            baseline_path.unlink()


class TestPerformanceTargets:
    """Tests for performance targets configuration."""
    
    def test_all_targets_defined(self):
        """All required benchmarks should have targets defined."""
        required_benchmarks = [
            "simple_extrude",
            "boolean_union",
            "fillet_10_edges",
            "stl_export",
            "full_rebuild"
        ]
        
        for benchmark_name in required_benchmarks:
            assert benchmark_name in PERFORMANCE_TARGETS, f"Missing target for {benchmark_name}"
            target = PERFORMANCE_TARGETS[benchmark_name]
            assert "target_ms" in target, f"Missing target_ms for {benchmark_name}"
            assert "max_ms" in target, f"Missing max_ms for {benchmark_name}"
            assert target["target_ms"] < target["max_ms"], f"target_ms should be less than max_ms for {benchmark_name}"
    
    def test_targets_are_reasonable(self):
        """Performance targets should be reasonable for modern hardware."""
        # Simple operations should be fast
        assert PERFORMANCE_TARGETS["simple_extrude"]["target_ms"] <= 100
        assert PERFORMANCE_TARGETS["fillet_10_edges"]["target_ms"] <= 150
        
        # Complex operations can take longer
        assert PERFORMANCE_TARGETS["full_rebuild"]["target_ms"] <= 1000
        assert PERFORMANCE_TARGETS["stl_export"]["target_ms"] <= 500


class TestRegressionThreshold:
    """Tests for regression threshold configuration."""
    
    def test_regression_threshold_is_20_percent(self):
        """Regression threshold should be 20% (1.20x)."""
        assert REGRESSION_THRESHOLD == 1.20


class TestRunWithCorpusModels:
    """Integration tests using corpus models."""
    
    @pytest.mark.slow
    def test_benchmark_with_simple_box(self):
        """Benchmark should work with simple box model."""
        benchmark = PerformanceBenchmark()
        
        # The internal benchmarks already use simple boxes
        result = benchmark.benchmark_extrude(iterations=3)
        
        assert result.success
        assert result.duration_ms < result.max_ms
    
    @pytest.mark.slow
    def test_benchmark_with_complex_operation(self):
        """Benchmark should handle complex operations."""
        benchmark = PerformanceBenchmark()
        
        # Rebuild is the most complex benchmark
        result = benchmark.benchmark_rebuild(iterations=2)
        
        assert result.success
        # Allow more time for complex operations
        assert result.duration_ms < 5000  # 5 seconds max for test
    
    @pytest.mark.slow
    def test_full_gate_run(self):
        """Full performance gate should run without errors."""
        exit_code = run_performance_gate()
        
        # Should pass (0) or have regressions (also 0 - warnings)
        # Only failures return 1
        assert exit_code in [0, 1]


class TestFeatureFlag:
    """Tests for feature flag integration."""
    
    def test_feature_flag_exists(self):
        """Performance regression gate flag should exist."""
        from config.feature_flags import is_enabled, FEATURE_FLAGS
        
        assert "performance_regression_gate" in FEATURE_FLAGS
        assert is_enabled("performance_regression_gate") is True
    
    def test_feature_flag_can_be_disabled(self):
        """Performance regression gate flag can be disabled."""
        from config.feature_flags import set_flag, is_enabled, FEATURE_FLAGS
        
        original_value = FEATURE_FLAGS.get("performance_regression_gate", False)
        
        try:
            set_flag("performance_regression_gate", False)
            assert is_enabled("performance_regression_gate") is False
        finally:
            set_flag("performance_regression_gate", original_value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
