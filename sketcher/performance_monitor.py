"""
Performance Monitoring for Sketch Drag Operations.

This module provides tools for measuring and monitoring frame timing
during sketch drag operations to achieve 60 FPS target.

SU-005: Drag Performance Optimization
"""

from dataclasses import dataclass, field
from typing import Optional, List, Callable
from collections import deque
import time


@dataclass
class PerformanceStats:
    """Statistics for frame timing and performance monitoring.
    
    Attributes:
        frame_count: Total number of frames recorded
        total_time_ms: Total elapsed time in milliseconds
        avg_frame_time_ms: Average frame time in milliseconds
        min_frame_time_ms: Minimum frame time in milliseconds
        max_frame_time_ms: Maximum frame time in milliseconds
        fps: Current frames per second
        dropped_frames: Number of frames exceeding 16.67ms budget
        drop_rate: Percentage of dropped frames
    """
    frame_count: int = 0
    total_time_ms: float = 0.0
    avg_frame_time_ms: float = 0.0
    min_frame_time_ms: float = float('inf')
    max_frame_time_ms: float = 0.0
    fps: float = 0.0
    dropped_frames: int = 0
    drop_rate: float = 0.0
    
    # Target frame budget for 60 FPS
    TARGET_FRAME_MS: float = 16.67
    
    def is_60fps(self) -> bool:
        """Check if performance meets 60 FPS target."""
        return self.avg_frame_time_ms <= self.TARGET_FRAME_MS and self.drop_rate < 0.1
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging/serialization."""
        return {
            'frame_count': self.frame_count,
            'total_time_ms': round(self.total_time_ms, 2),
            'avg_frame_time_ms': round(self.avg_frame_time_ms, 2),
            'min_frame_time_ms': round(self.min_frame_time_ms, 2) if self.min_frame_time_ms != float('inf') else 0,
            'max_frame_time_ms': round(self.max_frame_time_ms, 2),
            'fps': round(self.fps, 1),
            'dropped_frames': self.dropped_frames,
            'drop_rate': round(self.drop_rate * 100, 1),
            'meets_60fps': self.is_60fps()
        }


class FrameTimer:
    """High-precision frame timer for performance monitoring.
    
    Usage:
        timer = FrameTimer()
        
        # Start frame
        timer.begin_frame()
        
        # ... do work ...
        
        # End frame and get elapsed time
        elapsed_ms = timer.end_frame()
        
        # Get current stats
        stats = timer.get_stats()
    """
    
    def __init__(self, history_size: int = 60):
        """Initialize frame timer.
        
        Args:
            history_size: Number of frames to keep for rolling average
        """
        self._history_size = history_size
        self._frame_times: deque = deque(maxlen=history_size)
        self._frame_start: Optional[float] = None
        self._total_frames: int = 0
        self._dropped_frames: int = 0
        self._total_time: float = 0.0
        self._min_frame: float = float('inf')
        self._max_frame: float = 0.0
        self._last_frame_time: float = 0.0
        
        # Callbacks for frame events
        self._on_frame_drop: Optional[Callable[[float], None]] = None
        self._on_stats_update: Optional[Callable[[PerformanceStats], None]] = None
    
    def begin_frame(self) -> None:
        """Mark the beginning of a new frame."""
        self._frame_start = time.perf_counter()
    
    def end_frame(self) -> float:
        """Mark the end of the current frame and return elapsed time in ms.
        
        Returns:
            Elapsed frame time in milliseconds, or 0 if begin_frame wasn't called
        """
        if self._frame_start is None:
            return 0.0
        
        frame_end = time.perf_counter()
        elapsed_ms = (frame_end - self._frame_start) * 1000.0
        self._frame_start = None
        
        # Update statistics
        self._last_frame_time = elapsed_ms
        self._frame_times.append(elapsed_ms)
        self._total_frames += 1
        self._total_time += elapsed_ms
        self._min_frame = min(self._min_frame, elapsed_ms)
        self._max_frame = max(self._max_frame, elapsed_ms)
        
        # Check for dropped frame (exceeds 16.67ms budget)
        if elapsed_ms > PerformanceStats.TARGET_FRAME_MS:
            self._dropped_frames += 1
            if self._on_frame_drop:
                self._on_frame_drop(elapsed_ms)
        
        return elapsed_ms
    
    def get_last_frame_time(self) -> float:
        """Get the last frame time in milliseconds."""
        return self._last_frame_time
    
    def get_stats(self) -> PerformanceStats:
        """Calculate and return current performance statistics."""
        if not self._frame_times:
            return PerformanceStats()
        
        avg_time = sum(self._frame_times) / len(self._frame_times)
        drop_rate = self._dropped_frames / self._total_frames if self._total_frames > 0 else 0.0
        
        stats = PerformanceStats(
            frame_count=self._total_frames,
            total_time_ms=self._total_time,
            avg_frame_time_ms=avg_time,
            min_frame_time_ms=self._min_frame if self._min_frame != float('inf') else 0.0,
            max_frame_time_ms=self._max_frame,
            fps=1000.0 / avg_time if avg_time > 0 else 0.0,
            dropped_frames=self._dropped_frames,
            drop_rate=drop_rate
        )
        
        if self._on_stats_update:
            self._on_stats_update(stats)
        
        return stats
    
    def reset(self) -> None:
        """Reset all statistics."""
        self._frame_times.clear()
        self._frame_start = None
        self._total_frames = 0
        self._dropped_frames = 0
        self._total_time = 0.0
        self._min_frame = float('inf')
        self._max_frame = 0.0
        self._last_frame_time = 0.0
    
    def set_on_frame_drop(self, callback: Callable[[float], None]) -> None:
        """Set callback for frame drop events.
        
        Args:
            callback: Function called with elapsed time when frame exceeds budget
        """
        self._on_frame_drop = callback
    
    def set_on_stats_update(self, callback: Callable[[PerformanceStats], None]) -> None:
        """Set callback for stats update events.
        
        Args:
            callback: Function called with updated stats after each frame
        """
        self._on_stats_update = callback


class DragPerformanceTracker:
    """Tracks performance during drag operations.
    
    Provides detailed tracking of drag sessions including:
    - Total drag duration
    - Frame timing during drag
    - Solver call timing
    - Render timing
    
    Usage:
        tracker = DragPerformanceTracker()
        
        tracker.begin_drag()
        while dragging:
            tracker.begin_frame()
            # ... handle drag ...
            tracker.end_frame()
        tracker.end_drag()
        
        stats = tracker.get_drag_stats()
    """
    
    def __init__(self):
        """Initialize drag performance tracker."""
        self._frame_timer = FrameTimer(history_size=120)  # 2 seconds at 60 FPS
        self._drag_start_time: Optional[float] = None
        self._drag_end_time: Optional[float] = None
        self._solver_times: List[float] = []
        self._render_times: List[float] = []
        self._in_drag: bool = False
        self._current_frame_solver_time: float = 0.0
        self._current_frame_render_time: float = 0.0
    
    def begin_drag(self) -> None:
        """Start a new drag session."""
        self._frame_timer.reset()
        self._drag_start_time = time.perf_counter()
        self._drag_end_time = None
        self._solver_times.clear()
        self._render_times.clear()
        self._in_drag = True
    
    def end_drag(self) -> None:
        """End the current drag session."""
        self._drag_end_time = time.perf_counter()
        self._in_drag = False
    
    def begin_frame(self) -> None:
        """Mark the beginning of a frame during drag."""
        self._current_frame_solver_time = 0.0
        self._current_frame_render_time = 0.0
        self._frame_timer.begin_frame()
    
    def end_frame(self) -> float:
        """Mark the end of a frame during drag.
        
        Returns:
            Elapsed frame time in milliseconds
        """
        elapsed = self._frame_timer.end_frame()
        
        # Track component times
        if self._current_frame_solver_time > 0:
            self._solver_times.append(self._current_frame_solver_time)
        if self._current_frame_render_time > 0:
            self._render_times.append(self._current_frame_render_time)
        
        return elapsed
    
    def record_solver_time(self, time_ms: float) -> None:
        """Record time spent in solver for current frame.
        
        Args:
            time_ms: Solver execution time in milliseconds
        """
        self._current_frame_solver_time += time_ms
    
    def record_render_time(self, time_ms: float) -> None:
        """Record time spent rendering for current frame.
        
        Args:
            time_ms: Render time in milliseconds
        """
        self._current_frame_render_time += time_ms
    
    def is_dragging(self) -> bool:
        """Check if currently in a drag session."""
        return self._in_drag
    
    def get_drag_stats(self) -> dict:
        """Get comprehensive drag performance statistics.
        
        Returns:
            Dictionary with frame stats, solver stats, and render stats
        """
        frame_stats = self._frame_timer.get_stats()
        
        drag_duration_ms = 0.0
        if self._drag_start_time is not None:
            end = self._drag_end_time or time.perf_counter()
            drag_duration_ms = (end - self._drag_start_time) * 1000.0
        
        solver_avg = sum(self._solver_times) / len(self._solver_times) if self._solver_times else 0.0
        render_avg = sum(self._render_times) / len(self._render_times) if self._render_times else 0.0
        
        return {
            'drag_duration_ms': round(drag_duration_ms, 2),
            'frame_stats': frame_stats.to_dict(),
            'solver_calls': len(self._solver_times),
            'solver_avg_ms': round(solver_avg, 2),
            'solver_total_ms': round(sum(self._solver_times), 2),
            'render_calls': len(self._render_times),
            'render_avg_ms': round(render_avg, 2),
            'render_total_ms': round(sum(self._render_times), 2),
            'meets_60fps': frame_stats.is_60fps()
        }
    
    def reset(self) -> None:
        """Reset all tracking data."""
        self._frame_timer.reset()
        self._drag_start_time = None
        self._drag_end_time = None
        self._solver_times.clear()
        self._render_times.clear()
        self._in_drag = False


class ThrottledUpdate:
    """Throttled update manager for achieving consistent frame rates.
    
    Provides intelligent throttling that:
    - Skips updates if called too frequently
    - Accumulates pending updates and applies latest
    - Supports priority-based updates
    
    Usage:
        throttler = ThrottledUpdate(target_fps=60)
        
        def on_update():
            throttler.request_update()
        
        # In main loop:
        if throttler.should_update():
            do_update()
            throttler.mark_updated()
    """
    
    def __init__(self, target_fps: int = 60):
        """Initialize throttled update manager.
        
        Args:
            target_fps: Target frames per second (default 60)
        """
        self._target_fps = target_fps
        self._min_frame_ms = 1000.0 / target_fps
        self._last_update_time: float = 0.0
        self._pending: bool = False
        self._update_count: int = 0
        self._skip_count: int = 0
    
    def request_update(self) -> bool:
        """Request an update.
        
        Returns:
            True if update should be processed immediately, False if throttled
        """
        now = time.perf_counter()
        elapsed_ms = (now - self._last_update_time) * 1000.0
        
        if elapsed_ms >= self._min_frame_ms:
            self._pending = True
            return True
        else:
            self._pending = True
            self._skip_count += 1
            return False
    
    def should_update(self) -> bool:
        """Check if an update should be processed now.
        
        Returns:
            True if enough time has elapsed since last update
        """
        if not self._pending:
            return False
        
        now = time.perf_counter()
        elapsed_ms = (now - self._last_update_time) * 1000.0
        
        return elapsed_ms >= self._min_frame_ms
    
    def mark_updated(self) -> None:
        """Mark that an update has been completed."""
        self._last_update_time = time.perf_counter()
        self._pending = False
        self._update_count += 1
    
    def get_stats(self) -> dict:
        """Get throttling statistics.
        
        Returns:
            Dictionary with update and skip counts
        """
        total = self._update_count + self._skip_count
        return {
            'update_count': self._update_count,
            'skip_count': self._skip_count,
            'efficiency': self._update_count / total if total > 0 else 1.0
        }
    
    def reset(self) -> None:
        """Reset throttling state."""
        self._last_update_time = 0.0
        self._pending = False
        self._update_count = 0
        self._skip_count = 0


# Global performance tracker instance for convenience
_global_tracker: Optional[DragPerformanceTracker] = None


def get_performance_tracker() -> DragPerformanceTracker:
    """Get the global drag performance tracker instance.
    
    Returns:
        Global DragPerformanceTracker instance
    """
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = DragPerformanceTracker()
    return _global_tracker


def reset_global_tracker() -> None:
    """Reset the global performance tracker."""
    global _global_tracker
    if _global_tracker is not None:
        _global_tracker.reset()
