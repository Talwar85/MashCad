"""
TNP v5.0 - Shape Preview Mixin

Provides shape preview and highlighting functionality for ambiguity resolution.
Highlights candidate shapes in the viewport to help users make selections.
"""

import numpy as np
from loguru import logger
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

from gui.viewport.render_queue import request_render


@dataclass
class PreviewState:
    """State of a shape preview."""
    shape_id: str
    actor: Any  # pyvista.Actor
    original_color: Tuple[float, float, float]
    original_opacity: float


class PreviewMixin:
    """
    Mixin for PyVistaViewport providing shape preview and highlighting.

    Features:
    - preview_shape(): Highlight a single shape
    - preview_shapes(): Highlight multiple shapes for comparison
    - clear_preview(): Remove all highlights
    - Multi-candidate highlighting with distinct colors
    - Pulsing animation for attention
    """

    # Default colors for preview
    PREVIEW_COLOR = (1.0, 0.5, 0.0)  # Orange
    HIGHLIGHT_COLOR = (0.0, 0.8, 1.0)  # Cyan
    SELECTED_COLOR = (0.2, 1.0, 0.2)  # Green

    # Distinct colors for multiple candidates
    CANDIDATE_COLORS = [
        (1.0, 0.5, 0.0),  # Orange
        (0.0, 0.8, 1.0),  # Cyan
        (1.0, 0.0, 0.5),  # Magenta
        (1.0, 1.0, 0.0),  # Yellow
        (0.5, 0.0, 1.0),  # Purple
        (0.0, 1.0, 0.5),  # Teal
        (1.0, 0.0, 0.0),  # Red
        (0.0, 1.0, 1.0),  # Aqua
    ]

    def _init_preview_mixin(self):
        """Initialize preview state."""
        self._preview_states: Dict[str, PreviewState] = {}
        self._preview_actors: List[Any] = []  # Temporary overlay actors
        self._preview_active = False
        self._pulse_timer = None
        self._pulse_direction = 1

    # ========================================================================
    # Single Shape Preview
    # ========================================================================

    def preview_shape(
        self,
        shape_id: str,
        shape_mesh: Optional[Any] = None,
        color: Optional[Tuple[float, float, float]] = None,
        opacity: float = 0.8,
        pulse: bool = True
    ) -> bool:
        """
        Preview/highlight a single shape in the viewport.

        Args:
            shape_id: Unique identifier for the shape
            shape_mesh: PyVista mesh of the shape (if None, tries to find from viewport)
            color: RGB color tuple (default: PREVIEW_COLOR)
            opacity: Opacity 0-1 (default: 0.8)
            pulse: Enable pulsing animation (default: True)

        Returns:
            True if preview was created successfully
        """
        if not HAS_PYVISTA:
            logger.warning("PyVista not available for preview")
            return False

        if color is None:
            color = self.PREVIEW_COLOR

        try:
            # Clear existing preview
            self.clear_preview()

            # Find or create actor for the shape
            actor = self._find_or_create_shape_actor(shape_id, shape_mesh)
            if actor is None:
                return False

            # Store original state
            original_color = actor.prop.color
            original_opacity = actor.prop.opacity

            self._preview_states[shape_id] = PreviewState(
                shape_id=shape_id,
                actor=actor,
                original_color=original_color,
                original_opacity=original_opacity
            )

            # Apply preview style
            actor.prop.color = color
            actor.prop.opacity = opacity
            actor.prop.show_edges = True
            actor.prop.line_width = 2

            self._preview_active = True

            if pulse:
                self._start_pulse_animation()

            request_render(self.plotter)
            logger.debug(f"[Preview] Previewing shape: {shape_id}")
            return True

        except Exception as e:
            logger.error(f"[Preview] Error previewing shape {shape_id}: {e}")
            return False

    def _find_or_create_shape_actor(
        self,
        shape_id: str,
        shape_mesh: Optional[Any]
    ) -> Optional[Any]:
        """
        Find existing actor for shape or create new one.

        Args:
            shape_id: Shape identifier
            shape_mesh: PyVista mesh if creating new actor

        Returns:
            Actor or None
        """
        # First try to find existing actor in viewport
        actor = self._find_actor_by_shape_id(shape_id)
        if actor is not None:
            return actor

        # If mesh provided, create new actor
        if shape_mesh is not None:
            return self._add_preview_actor(shape_id, shape_mesh)

        logger.warning(f"[Preview] Could not find actor for shape: {shape_id}")
        return None

    def _find_actor_by_shape_id(self, shape_id: str) -> Optional[Any]:
        """Find existing actor by shape ID."""
        # Check bodies
        if hasattr(self, '_body_actors'):
            for body_id, actor in self._body_actors.items():
                if shape_id in body_id or body_id in shape_id:
                    return actor

        # Check all actors in plotter
        if hasattr(self, 'plotter') and self.plotter:
            for actor in self.plotter.renderer.actors.values():
                if hasattr(actor, 'user_matrix') and actor.user_matrix is not None:
                    # This is likely a body actor
                    if shape_id in str(actor.name):
                        return actor

        return None

    def _add_preview_actor(self, shape_id: str, mesh: Any) -> Optional[Any]:
        """Add a temporary preview actor to the scene."""
        if not hasattr(self, 'plotter') or self.plotter is None:
            return None

        try:
            actor = self.plotter.add_mesh(
                mesh,
                color=self.PREVIEW_COLOR,
                opacity=0.8,
                show_edges=True,
                line_width=2,
                name=f"preview_{shape_id}",
                pickable=False
            )
            self._preview_actors.append(actor)
            return actor
        except Exception as e:
            logger.error(f"[Preview] Error adding preview actor: {e}")
            return None

    # ========================================================================
    # Multiple Shape Preview (Ambiguity Resolution)
    # ========================================================================

    def preview_shapes(
        self,
        shape_ids: List[str],
        shape_meshes: Optional[List[Any]] = None,
        selected_index: int = -1
    ) -> bool:
        """
        Preview multiple shapes with distinct colors for comparison.

        Used during ambiguity resolution to show all candidate shapes.

        Args:
            shape_ids: List of shape identifiers
            shape_meshes: Optional list of PyVista meshes
            selected_index: Index of currently selected candidate (-1 for none)

        Returns:
            True if preview was created successfully
        """
        if not HAS_PYVISTA:
            return False

        if not shape_ids:
            return False

        try:
            self.clear_preview()

            if shape_meshes is None:
                shape_meshes = [None] * len(shape_ids)

            success = True
            for i, (shape_id, mesh) in enumerate(zip(shape_ids, shape_meshes)):
                # Use distinct color for each candidate
                color = self.CANDIDATE_COLORS[i % len(self.CANDIDATE_COLORS)]

                # Highlight selected candidate
                if i == selected_index:
                    color = self.SELECTED_COLOR
                    opacity = 1.0
                else:
                    opacity = 0.6

                if not self._preview_single_shape_internal(shape_id, mesh, color, opacity):
                    success = False

            if success:
                self._preview_active = True
                request_render(self.plotter)

            return success

        except Exception as e:
            logger.error(f"[Preview] Error previewing shapes: {e}")
            return False

    def _preview_single_shape_internal(
        self,
        shape_id: str,
        mesh: Optional[Any],
        color: Tuple[float, float, float],
        opacity: float
    ) -> bool:
        """Internal method to preview a single shape without clearing others."""
        actor = self._find_or_create_shape_actor(shape_id, mesh)
        if actor is None:
            return False

        # Store original state
        original_color = actor.prop.color
        original_opacity = actor.prop.opacity

        self._preview_states[shape_id] = PreviewState(
            shape_id=shape_id,
            actor=actor,
            original_color=original_color,
            original_opacity=original_opacity
        )

        # Apply preview style
        actor.prop.color = color
        actor.prop.opacity = opacity
        actor.prop.show_edges = True
        actor.prop.line_width = 3

        return True

    # ========================================================================
    # Preview Control
    # ========================================================================

    def clear_preview(self) -> None:
        """Remove all preview highlights and restore original colors."""
        if not self._preview_active:
            return

        try:
            # Stop pulse animation
            self._stop_pulse_animation()

            # Restore original states
            for preview_state in self._preview_states.values():
                try:
                    preview_state.actor.prop.color = preview_state.original_color
                    preview_state.actor.prop.opacity = preview_state.original_opacity
                    preview_state.actor.prop.show_edges = False
                except Exception as e:
                    logger.debug(f"[Preview] Error restoring state: {e}")

            self._preview_states.clear()

            # Remove temporary preview actors
            for actor in self._preview_actors:
                try:
                    if hasattr(self, 'plotter') and self.plotter:
                        self.plotter.remove_actor(actor)
                except Exception as e:
                    logger.debug(f"[Preview] Error removing actor: {e}")

            self._preview_actors.clear()
            self._preview_active = False

            request_render(self.plotter)
            logger.debug("[Preview] Preview cleared")

        except Exception as e:
            logger.error(f"[Preview] Error clearing preview: {e}")

    def update_selected_candidate(self, index: int, shape_ids: List[str]) -> None:
        """
        Update preview to show which candidate is selected.

        Args:
            index: Index of selected candidate
            shape_ids: List of all candidate shape IDs
        """
        if not self._preview_active:
            return

        if index < 0 or index >= len(shape_ids):
            return

        try:
            # Reset all to default colors
            for i, shape_id in enumerate(shape_ids):
                if shape_id in self._preview_states:
                    color = self.CANDIDATE_COLORS[i % len(self.CANDIDATE_COLORS)]
                    state = self._preview_states[shape_id]
                    state.actor.prop.color = color
                    state.actor.prop.opacity = 0.6

            # Highlight selected
            selected_id = shape_ids[index]
            if selected_id in self._preview_states:
                state = self._preview_states[selected_id]
                state.actor.prop.color = self.SELECTED_COLOR
                state.actor.prop.opacity = 1.0

            request_render(self.plotter)

        except Exception as e:
            logger.error(f"[Preview] Error updating selection: {e}")

    # ========================================================================
    # Pulse Animation
    # ========================================================================

    def _start_pulse_animation(self) -> None:
        """Start pulsing animation for highlighted shapes."""
        if self._pulse_timer is not None:
            return

        try:
            from PySide6.QtCore import QTimer
            self._pulse_timer = QTimer()
            self._pulse_timer.timeout.connect(self._pulse_step)
            self._pulse_timer.start(50)  # 20 FPS

        except ImportError:
            # Qt not available, skip animation
            pass

    def _stop_pulse_animation(self) -> None:
        """Stop pulsing animation."""
        if self._pulse_timer is not None:
            self._pulse_timer.stop()
            self._pulse_timer = None

    def _pulse_step(self) -> None:
        """Single step of pulse animation."""
        if not self._preview_states:
            return

        # Calculate opacity pulse (0.4 to 1.0)
        pulse_factor = 0.2
        for state in self._preview_states.values():
            current_opacity = state.actor.prop.opacity
            new_opacity = current_opacity + (pulse_factor * self._pulse_direction)

            if new_opacity >= 1.0:
                new_opacity = 1.0
                self._pulse_direction = -1
            elif new_opacity <= 0.4:
                new_opacity = 0.4
                self._pulse_direction = 1

            state.actor.prop.opacity = new_opacity

        request_render(self.plotter)

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def is_preview_active(self) -> bool:
        """Check if preview is currently active."""
        return self._preview_active

    def get_previewed_shapes(self) -> List[str]:
        """Get list of currently previewed shape IDs."""
        return list(self._preview_states.keys())

    def has_preview(self, shape_id: str) -> bool:
        """Check if a specific shape is being previewed."""
        return shape_id in self._preview_states


# Export
__all__ = ['PreviewMixin', 'PreviewState']
