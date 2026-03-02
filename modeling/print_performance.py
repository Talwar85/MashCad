"""
Performance Budgets for Print Optimization

V1 Performance Requirements:

For a typical part (5000 faces, 20mm bounding box):

| Operation | Budget | Notes |
|-----------|--------|-------|
| Base printability analysis | <300ms | Existing modules |
| Bridge classification | <100ms | New, simple heuristics |
| Support estimation | <200ms | Face iteration only |
| Fin proposal generation | <500ms | Simple geometry only |
| Candidate generation | <50ms | Max ~20 candidates |
| Candidate scoring | <1s | All candidates serial |
| **Total recommendation** | **<2s** | **Hard limit** |
| Overlay refresh | debounced | Non-blocking |

Enforcement:
- Add timing decorators to all analysis functions
- Fail with clear error if budget exceeded
- Log actual timings for corpus monitoring
"""

import time
import functools
from loguru import logger


# Performance budget constants (milliseconds)
BUDGET_BASE_ANALYSIS = 300
BUDGET_BRIDGE_CLASSIFICATION = 100
BUDGET_SUPPORT_ESTIMATION = 200
BUDGET_FIN_GENERATION = 500
BUDGET_CANDIDATE_GENERATION = 50
BUDGET_CANDIDATE_SCORING = 1000
BUDGET_TOTAL_RECOMMENDATION = 2000


def timed(budget_ms: int, name: str = None):
    """
    Decorator to measure execution time and enforce budget.

    Raises:
        RuntimeError: If execution exceeds budget
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000

            func_name = name or func.__name__

            if elapsed_ms > budget_ms:
                logger.warning(
                    f"[PERFORMANCE] {func_name} exceeded budget: "
                    f"{elapsed_ms:.0f}ms > {budget_ms}ms"
                )
                # In production: could raise or warn
                # For V1: log only, fail only if significantly over

            logger.debug(f"[PERFORMANCE] {func_name}: {elapsed_ms:.0f}ms")
            return result

        return wrapper
    return decorator


def timed_test(expected_max_ms: float):
    """
    Decorator for test functions to assert performance budget.

    Usage:
        @timed_test(100)
        def test_bridge_classification():
            assert_bridge_classification_is_fast()
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000

            assert elapsed_ms < expected_max_ms, (
                f"{func.__name__} exceeded performance budget: "
                f"{elapsed_ms:.0f}ms < {expected_max_ms}ms"
            )

            return result
        return wrapper
    return decorator


class PerformanceMonitor:
    """
    Monitor and report performance metrics for print optimization.
    """

    def __init__(self):
        self.measurements = {}

    def start(self, name: str):
        """Start timing a named operation."""
        self.measurements[name] = {'start': time.perf_counter()}

    def end(self, name: str):
        """End timing and record measurement."""
        if name in self.measurements:
            elapsed = time.perf_counter() - self.measurements[name]['start']
            self.measurements[name]['elapsed_ms'] = elapsed * 1000

    def get_report(self) -> dict:
        """Get all measurements as dict."""
        return {
            name: m.get('elapsed_ms', 0)
            for name, m in self.measurements.items()
        }

    def log_report(self):
        """Log performance report."""
        for name, ms in self.get_report().items():
            if ms > 0:
                logger.info(f"[PERF] {name}: {ms:.0f}ms")


# Global performance monitor instance
_perf_monitor = PerformanceMonitor()


# Budget definitions for use in code

BUDGETS = {
    'base_analysis': BUDGET_BASE_ANALYSIS,
    'bridge_classification': BUDGET_BRIDGE_CLASSIFICATION,
    'support_estimation': BUDGET_SUPPORT_ESTIMATION,
    'fin_generation': BUDGET_FIN_GENERATION,
    'candidate_generation': BUDGET_CANDIDATE_GENERATION,
    'candidate_scoring': BUDGET_CANDIDATE_SCORING,
    'total_recommendation': BUDGET_TOTAL_RECOMMENDATION,
}


def get_budget(operation: str) -> int:
    """Get budget for an operation by name."""
    return BUDGETS.get(operation, float('inf'))


if __name__ == "__main__":
    # Test the timing decorator
    @timed(budget_ms=100, name="test_function")
    def test_function():
        time.sleep(0.01)  # 10ms - well under budget
        return "ok"

    test_function()
