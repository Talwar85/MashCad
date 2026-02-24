"""
Incremental Solver Integration for Sketch Editor Dragging

W35 P4: Integration module for incremental constraint solving during drag operations.

This module provides functions to integrate the IncrementalSolverBackend with
the SketchEditor's direct edit operations, enabling smooth 60 FPS dragging.

Usage in SketchEditor:
    from gui.incremental_drag_integration import IncrementalDragIntegration

    # In __init__:
    self._incremental_drag = IncrementalDragIntegration(self)

    # On drag start:
    self._incremental_drag.start_drag(entity_id)

    # During drag (mouse move):
    self._incremental_drag.drag_move(new_x, new_y)

    # On drag end:
    result = self._incremental_drag.end_drag()
"""

import time
from typing import Optional, Tuple, Any, Dict
from loguru import logger

try:
    from sketcher.solver_incremental import IncrementalSolverBackend
    HAS_INCREMENTAL = True
except ImportError:
    HAS_INCREMENTAL = False
    IncrementalSolverBackend = None


class IncrementalDragIntegration:
    """
    Integration layer for incremental constraint solving during drag.

    Manages the drag lifecycle:
    1. start_drag() - Initialize incremental context
    2. drag_move() - Solve only affected constraints (fast)
    3. end_drag() - Final precise solve with all constraints

    Performance: 10-30x faster than full solve during drag.
    """

    def __init__(self, sketch_editor):
        """
        Initialize integration with SketchEditor instance.

        Args:
            sketch_editor: The SketchEditor instance
        """
        self.editor = sketch_editor
        self._backend: Optional[IncrementalSolverBackend] = None
        self._context = None
        self._is_active = False
        self._drag_entity_id = None

        # Performance tracking
        self._drag_start_time = 0.0
        self._drag_solve_times = []

        # Check if incremental solver is available
        self._available = HAS_INCREMENTAL
        if self._available:
            try:
                from config.feature_flags import is_enabled
                if not is_enabled("incremental_solver"):
                    self._available = False
                    logger.debug("[IncrementalDrag] Disabled by feature flag")
            except ImportError:
                pass

        if self._available:
            self._backend = IncrementalSolverBackend()
            logger.info("[IncrementalDrag] Integration initialized")

    @property
    def is_available(self) -> bool:
        """Check if incremental solver is available and enabled"""
        return self._available

    @property
    def is_dragging(self) -> bool:
        """Check if currently in drag mode"""
        return self._is_active

    def start_drag(self, entity_id: str) -> bool:
        """
        Start incremental drag for an entity.

        Args:
            entity_id: ID of the point/entity being dragged

        Returns:
            True if incremental mode was activated, False otherwise
        """
        if not self._available:
            return False

        try:
            sketch = self.editor.sketch
            self._context = self._backend.start_drag(sketch, entity_id)
            self._is_active = True
            self._drag_entity_id = entity_id
            self._drag_start_time = time.perf_counter()
            self._drag_solve_times.clear()

            logger.debug(f"[IncrementalDrag] Started drag on {entity_id}")
            return True

        except Exception as e:
            logger.warning(f"[IncrementalDrag] Failed to start: {e}")
            self._is_active = False
            return False

    def drag_move(self, world_x: float, world_y: float) -> Optional[Dict]:
        """
        Perform incremental solve during drag.

        Args:
            world_x: New world X coordinate
            world_y: New world Y coordinate

        Returns:
            Dict with solve result, or None if not in incremental mode
        """
        if not self._is_active or self._backend is None:
            return None

        start_time = time.perf_counter()

        try:
            # Perform incremental solve
            result = self._backend.solve_drag((world_x, world_y))

            solve_time = time.perf_counter() - start_time
            self._drag_solve_times.append(solve_time)

            # Return result dict
            return {
                'success': result.success,
                'iterations': result.iterations,
                'final_error': result.final_error,
                'message': result.message,
                'backend': result.backend_used,
                'solve_time_ms': solve_time * 1000,
                'is_incremental': True
            }

        except Exception as e:
            logger.warning(f"[IncrementalDrag] Solve failed: {e}")
            return {
                'success': False,
                'message': f"Incremental solve error: {e}",
                'is_incremental': True
            }

    def end_drag(self) -> Optional[Dict]:
        """
        End drag with final precise solve.

        Returns:
            Dict with final solve result, or None if not in incremental mode
        """
        if not self._is_active or self._backend is None:
            return None

        start_time = time.perf_counter()

        try:
            # Final precise solve
            result = self._backend.end_drag()

            solve_time = time.perf_counter() - start_time
            total_drag_time = time.perf_counter() - self._drag_start_time

            # Build stats
            avg_drag_time = sum(self._drag_solve_times) / max(1, len(self._drag_solve_times))

            stats = {
                'success': result.success,
                'iterations': result.iterations,
                'final_error': result.final_error,
                'message': result.message,
                'backend': result.backend_used,
                'solve_time_ms': solve_time * 1000,
                'is_incremental': True,
                'stats': {
                    'drag_count': len(self._drag_solve_times),
                    'avg_drag_time_ms': avg_drag_time * 1000,
                    'total_drag_time_ms': total_drag_time * 1000,
                    'final_solve_time_ms': solve_time * 1000
                }
            }

            logger.info(f"[IncrementalDrag] Drag complete: {len(self._drag_solve_times)} solves, "
                       f"avg {avg_drag_time*1000:.2f}ms, final {solve_time*1000:.2f}ms")

            return stats

        except Exception as e:
            logger.warning(f"[IncrementalDrag] End drag failed: {e}")
            return {
                'success': False,
                'message': f"End drag error: {e}",
                'is_incremental': True
            }

        finally:
            self._is_active = False
            self._context = None
            self._drag_entity_id = None

    def cancel_drag(self) -> None:
        """Cancel the current drag operation without solving"""
        if self._is_active:
            logger.debug(f"[IncrementalDrag] Drag cancelled")
            self._is_active = False
            self._context = None
            self._drag_entity_id = None

    def get_stats(self) -> Dict:
        """Get statistics about the current/last drag"""
        return {
            'available': self._available,
            'is_dragging': self._is_active,
            'drag_entity_id': self._drag_entity_id,
            'solve_count': len(self._drag_solve_times),
            'avg_time_ms': sum(self._drag_solve_times) / max(1, len(self._drag_solve_times)) * 1000 if self._drag_solve_times else 0
        }


def patch_sketch_editor_for_incremental_drag(sketch_editor):
    """
    Monkey-patch SketchEditor to use incremental solver for dragging.

    This function modifies the SketchEditor's drag-related methods to use
    incremental solving when available.

    Args:
        sketch_editor: The SketchEditor instance to patch
    """
    if not HAS_INCREMENTAL:
        logger.debug("[IncrementalDrag] Not available, skipping patch")
        return

    try:
        from config.feature_flags import is_enabled
        if not is_enabled("incremental_solver"):
            logger.debug("[IncrementalDrag] Disabled by feature flag, skipping patch")
            return
    except ImportError:
        pass

    # Create integration instance
    integration = IncrementalDragIntegration(sketch_editor)
    if not integration.is_available:
        return

    # Store integration in editor
    sketch_editor._incremental_drag = integration

    # Save original methods
    _original_maybe_live_solve = sketch_editor._maybe_live_solve_during_direct_drag
    _original_start_direct_edit = None
    _original_end_direct_edit = None

    # Find the direct edit start/end methods
    if hasattr(sketch_editor, '_start_direct_edit_mode'):
        _original_start_direct_edit = sketch_editor._start_direct_edit_mode

    # Patch the live solve method
    def _patched_maybe_live_solve():
        """Patched version that uses incremental solver during drag"""
        if integration.is_dragging:
            # Get current mouse position
            world_x = sketch_editor.mouse_world.x()
            world_y = sketch_editor.mouse_world.y()

            # Use incremental solver
            result = integration.drag_move(world_x, world_y)

            if result:
                # Check throttle
                now = time.perf_counter()
                if (now - sketch_editor._direct_edit_last_live_solve_ts) < sketch_editor._direct_edit_live_solve_interval_s:
                    sketch_editor._direct_edit_pending_solve = True
                    return

                sketch_editor._direct_edit_last_live_solve_ts = now

                # Request update
                sketch_editor.request_update()
                return

        # Fallback to original
        return _original_maybe_live_solve()

    # Apply patch
    sketch_editor._maybe_live_solve_during_direct_drag = _patched_maybe_live_solve

    # Store original for potential unpatch
    sketch_editor._original_maybe_live_solve = _original_maybe_live_solve

    logger.info("[IncrementalDrag] SketchEditor patched for incremental drag")


def unpatch_sketch_editor(sketch_editor):
    """Remove incremental drag patches from SketchEditor"""
    if hasattr(sketch_editor, '_original_maybe_live_solve'):
        sketch_editor._maybe_live_solve_during_direct_drag = sketch_editor._original_maybe_live_solve
        delattr(sketch_editor, '_original_maybe_live_solve')

    if hasattr(sketch_editor, '_incremental_drag'):
        delattr(sketch_editor, '_incremental_drag')

    logger.info("[IncrementalDrag] SketchEditor unpatched")
