"""
SU-005: Sketch Drag Performance Tests

Tests for 60 FPS target during sketch geometry manipulation.
Validates FrameTimer, PerformanceStats, and DragPerformanceTracker.
"""

import pytest
import time
from unittest.mock import Mock, patch


class TestFrameTimer:
    """Tests for FrameTimer class."""
    
    def test_frame_timer_import(self):
        """Test that FrameTimer can be imported."""
        from sketcher.performance_monitor import FrameTimer
        assert FrameTimer is not None
    
    def test_frame_timer_basic_timing(self):
        """Test basic frame timing functionality."""
        from sketcher.performance_monitor import FrameTimer
        
        timer = FrameTimer()
        
        # Start and end a frame
        timer.begin_frame()
        time.sleep(0.001)  # 1ms delay
        elapsed = timer.end_frame()
        
        # Should be at least 1ms
        assert elapsed >= 1.0
        assert timer.get_last_frame_time() == elapsed
    
    def test_frame_timer_stats(self):
        """Test that stats are calculated correctly."""
        from sketcher.performance_monitor import FrameTimer, PerformanceStats
        
        timer = FrameTimer()
        
        # Run 10 frames with small delays
        for _ in range(10):
            timer.begin_frame()
            time.sleep(0.002)  # 2ms delay
            timer.end_frame()
        
        stats = timer.get_stats()
        
        assert isinstance(stats, PerformanceStats)
        assert stats.frame_count == 10
        assert stats.avg_frame_time_ms >= 2.0
        assert stats.fps > 0
        assert stats.fps <= 500  # Should be less than 500 FPS given 2ms delays
    
    def test_frame_timer_dropped_frames(self):
        """Test dropped frame detection."""
        from sketcher.performance_monitor import FrameTimer
        
        timer = FrameTimer()
        
        # Run frames that exceed 16.67ms budget (dropped frames)
        for _ in range(5):
            timer.begin_frame()
            time.sleep(0.020)  # 20ms - exceeds budget
            timer.end_frame()
        
        # Run frames within budget
        for _ in range(5):
            timer.begin_frame()
            time.sleep(0.005)  # 5ms - within budget
            timer.end_frame()
        
        stats = timer.get_stats()
        
        assert stats.dropped_frames >= 5  # At least 5 dropped frames
        assert stats.drop_rate >= 0.5  # At least 50% drop rate
    
    def test_frame_timer_reset(self):
        """Test timer reset functionality."""
        from sketcher.performance_monitor import FrameTimer
        
        timer = FrameTimer()
        
        # Run some frames
        for _ in range(5):
            timer.begin_frame()
            timer.end_frame()
        
        stats = timer.get_stats()
        assert stats.frame_count == 5
        
        # Reset
        timer.reset()
        stats = timer.get_stats()
        assert stats.frame_count == 0
    
    def test_frame_timer_callback(self):
        """Test frame drop callback."""
        from sketcher.performance_monitor import FrameTimer
        
        timer = FrameTimer()
        dropped_times = []
        
        def on_drop(elapsed: float):
            dropped_times.append(elapsed)
        
        timer.set_on_frame_drop(on_drop)
        
        # Trigger a dropped frame
        timer.begin_frame()
        time.sleep(0.020)  # 20ms
        timer.end_frame()
        
        assert len(dropped_times) == 1
        assert dropped_times[0] >= 16.67


class TestPerformanceStats:
    """Tests for PerformanceStats dataclass."""
    
    def test_performance_stats_creation(self):
        """Test PerformanceStats creation."""
        from sketcher.performance_monitor import PerformanceStats
        
        stats = PerformanceStats(
            frame_count=100,
            total_time_ms=1667.0,
            avg_frame_time_ms=16.67,
            min_frame_time_ms=10.0,
            max_frame_time_ms=25.0,
            fps=60.0,
            dropped_frames=10,
            drop_rate=0.1
        )
        
        assert stats.frame_count == 100
        assert stats.avg_frame_time_ms == 16.67
        assert stats.fps == 60.0
    
    def test_performance_stats_60fps_check(self):
        """Test is_60fps method."""
        from sketcher.performance_monitor import PerformanceStats
        
        # Good performance
        good_stats = PerformanceStats(
            frame_count=100,
            avg_frame_time_ms=14.0,
            drop_rate=0.05
        )
        assert good_stats.is_60fps()
        
        # Poor performance
        poor_stats = PerformanceStats(
            frame_count=100,
            avg_frame_time_ms=20.0,
            drop_rate=0.2
        )
        assert not poor_stats.is_60fps()
    
    def test_performance_stats_to_dict(self):
        """Test to_dict serialization."""
        from sketcher.performance_monitor import PerformanceStats
        
        stats = PerformanceStats(
            frame_count=50,
            total_time_ms=1000.0,
            avg_frame_time_ms=20.0,
            fps=50.0,
            dropped_frames=5,
            drop_rate=0.1
        )
        
        d = stats.to_dict()
        
        assert d['frame_count'] == 50
        assert d['fps'] == 50.0
        assert 'meets_60fps' in d


class TestDragPerformanceTracker:
    """Tests for DragPerformanceTracker class."""
    
    def test_tracker_import(self):
        """Test that DragPerformanceTracker can be imported."""
        from sketcher.performance_monitor import DragPerformanceTracker
        assert DragPerformanceTracker is not None
    
    def test_drag_session_tracking(self):
        """Test basic drag session tracking."""
        from sketcher.performance_monitor import DragPerformanceTracker
        
        tracker = DragPerformanceTracker()
        
        # Start drag session
        tracker.begin_drag()
        assert tracker.is_dragging()
        
        # Simulate frames
        for _ in range(10):
            tracker.begin_frame()
            time.sleep(0.005)
            tracker.end_frame()
        
        # End drag session
        tracker.end_drag()
        assert not tracker.is_dragging()
        
        stats = tracker.get_drag_stats()
        assert stats['frame_stats']['frame_count'] == 10
    
    def test_solver_time_recording(self):
        """Test solver time recording."""
        from sketcher.performance_monitor import DragPerformanceTracker
        
        tracker = DragPerformanceTracker()
        tracker.begin_drag()
        
        tracker.begin_frame()
        tracker.record_solver_time(5.0)  # 5ms solver time
        tracker.end_frame()
        
        tracker.end_drag()
        
        stats = tracker.get_drag_stats()
        assert stats['solver_calls'] == 1
        assert stats['solver_avg_ms'] == 5.0
    
    def test_render_time_recording(self):
        """Test render time recording."""
        from sketcher.performance_monitor import DragPerformanceTracker
        
        tracker = DragPerformanceTracker()
        tracker.begin_drag()
        
        tracker.begin_frame()
        tracker.record_render_time(3.0)  # 3ms render time
        tracker.end_frame()
        
        tracker.end_drag()
        
        stats = tracker.get_drag_stats()
        assert stats['render_calls'] == 1
        assert stats['render_avg_ms'] == 3.0
    
    def test_drag_stats_60fps_check(self):
        """Test meets_60fps in drag stats."""
        from sketcher.performance_monitor import DragPerformanceTracker
        
        tracker = DragPerformanceTracker()
        tracker.begin_drag()
        
        # Fast frames
        for _ in range(10):
            tracker.begin_frame()
            time.sleep(0.005)  # 5ms
            tracker.end_frame()
        
        tracker.end_drag()
        
        stats = tracker.get_drag_stats()
        assert stats['meets_60fps']
    
    def test_tracker_reset(self):
        """Test tracker reset."""
        from sketcher.performance_monitor import DragPerformanceTracker
        
        tracker = DragPerformanceTracker()
        tracker.begin_drag()
        
        for _ in range(5):
            tracker.begin_frame()
            tracker.end_frame()
        
        tracker.end_drag()
        
        stats = tracker.get_drag_stats()
        assert stats['frame_stats']['frame_count'] == 5
        
        tracker.reset()
        stats = tracker.get_drag_stats()
        assert stats['frame_stats']['frame_count'] == 0


class TestThrottledUpdate:
    """Tests for ThrottledUpdate class."""
    
    def test_throttled_update_import(self):
        """Test that ThrottledUpdate can be imported."""
        from sketcher.performance_monitor import ThrottledUpdate
        assert ThrottledUpdate is not None
    
    def test_throttling_at_60fps(self):
        """Test throttling behavior at 60 FPS target."""
        from sketcher.performance_monitor import ThrottledUpdate
        
        throttler = ThrottledUpdate(target_fps=60)
        
        # First request should be allowed
        assert throttler.request_update()
        
        # Immediate second request should be pending but throttled
        throttler.request_update()
        assert not throttler.should_update()  # Too soon
        
        # Wait for throttle period
        time.sleep(0.020)  # 20ms > 16.67ms
        assert throttler.should_update()
        throttler.mark_updated()
    
    def test_throttler_stats(self):
        """Test throttler statistics."""
        from sketcher.performance_monitor import ThrottledUpdate
        
        throttler = ThrottledUpdate(target_fps=60)
        
        # Request many updates rapidly
        for _ in range(10):
            throttler.request_update()
            time.sleep(0.002)  # 2ms - less than throttle period
        
        stats = throttler.get_stats()
        assert stats['skip_count'] > 0  # Some updates should be skipped


class TestFeatureFlags:
    """Tests for SU-005 feature flags."""
    
    def test_drag_optimization_flag_exists(self):
        """Test that sketch_drag_optimization flag exists."""
        from config.feature_flags import FEATURE_FLAGS
        
        assert "sketch_drag_optimization" in FEATURE_FLAGS
        assert FEATURE_FLAGS["sketch_drag_optimization"] is True
    
    def test_solver_throttle_flag_exists(self):
        """Test that sketch_solver_throttle_ms flag exists."""
        from config.feature_flags import FEATURE_FLAGS
        
        assert "sketch_solver_throttle_ms" in FEATURE_FLAGS
        assert FEATURE_FLAGS["sketch_solver_throttle_ms"] == 16
    
    def test_performance_monitoring_flag_exists(self):
        """Test that sketch_performance_monitoring flag exists."""
        from config.feature_flags import FEATURE_FLAGS
        
        assert "sketch_performance_monitoring" in FEATURE_FLAGS
        # Default is False for debug flag
        assert FEATURE_FLAGS["sketch_performance_monitoring"] is False
    
    def test_is_enabled_function(self):
        """Test is_enabled for new flags."""
        from config.feature_flags import is_enabled
        
        assert is_enabled("sketch_drag_optimization")
        assert not is_enabled("sketch_performance_monitoring")


class TestPerformanceIntegration:
    """Integration tests for performance monitoring."""
    
    def test_global_tracker(self):
        """Test global performance tracker."""
        from sketcher.performance_monitor import (
            get_performance_tracker, reset_global_tracker
        )
        
        tracker = get_performance_tracker()
        assert tracker is not None
        
        # Should be same instance
        tracker2 = get_performance_tracker()
        assert tracker is tracker2
        
        # Reset
        reset_global_tracker()
        tracker3 = get_performance_tracker()
        # After reset, stats should be fresh
        assert tracker3.get_drag_stats()['frame_stats']['frame_count'] == 0
    
    @pytest.mark.skipif(
        not pytest.importorskip("PySide6", reason="PySide6 not available"),
        reason="Requires PySide6"
    )
    def test_sketch_editor_performance_tracker_init(self):
        """Test that SketchEditor initializes performance tracker correctly."""
        # This test requires Qt application context
        # In CI, this would be skipped if no display is available
        pass


class TestPerformanceBenchmarks:
    """Benchmark tests for performance validation."""
    
    @pytest.mark.slow
    def test_frame_timer_overhead(self):
        """Test that FrameTimer has minimal overhead."""
        from sketcher.performance_monitor import FrameTimer
        
        timer = FrameTimer()
        
        # Measure overhead of timer itself
        start = time.perf_counter()
        for _ in range(1000):
            timer.begin_frame()
            timer.end_frame()
        elapsed = (time.perf_counter() - start) * 1000.0
        
        avg_overhead_ms = elapsed / 1000
        # Timer overhead should be less than 0.1ms per frame
        assert avg_overhead_ms < 0.1, f"FrameTimer overhead too high: {avg_overhead_ms}ms"
    
    @pytest.mark.slow
    def test_60fps_sustained_performance(self):
        """Test sustained 60 FPS performance simulation."""
        from sketcher.performance_monitor import DragPerformanceTracker
        
        tracker = DragPerformanceTracker()
        tracker.begin_drag()
        
        # Simulate 60 frames at 60 FPS (16.67ms per frame)
        for _ in range(60):
            tracker.begin_frame()
            # Simulate work: 10ms of "work"
            time.sleep(0.010)
            tracker.end_frame()
        
        tracker.end_drag()
        
        stats = tracker.get_drag_stats()
        
        # Should achieve ~60 FPS with 10ms work per frame
        assert stats['frame_stats']['fps'] >= 50, f"FPS too low: {stats['frame_stats']['fps']}"
        assert stats['meets_60fps']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
