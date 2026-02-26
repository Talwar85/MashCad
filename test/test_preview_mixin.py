"""
TNP v5.0 - Preview Mixin Tests

Tests for the PreviewMixin class used for shape highlighting
during ambiguity resolution.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from gui.viewport.preview_mixin import (
    PreviewMixin,
    PreviewState,
)


class TestPreviewState:
    """Test PreviewState dataclass."""

    def test_creation(self):
        """Test creating a preview state."""
        state = PreviewState(
            shape_id="test_shape",
            actor=Mock(),
            original_color=(1.0, 0.0, 0.0),
            original_opacity=0.5
        )

        assert state.shape_id == "test_shape"
        assert state.original_color == (1.0, 0.0, 0.0)
        assert state.original_opacity == 0.5


class TestPreviewMixinInit:
    """Test PreviewMixin initialization."""

    def test_init_preview_state(self):
        """Test preview state initialization."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        assert mixin._preview_states == {}
        assert mixin._preview_actors == []
        assert mixin._preview_active is False
        assert mixin._pulse_timer is None
        assert mixin._pulse_direction == 1

    def test_default_colors(self):
        """Test default color constants."""
        assert PreviewMixin.PREVIEW_COLOR == (1.0, 0.5, 0.0)
        assert PreviewMixin.HIGHLIGHT_COLOR == (0.0, 0.8, 1.0)
        assert PreviewMixin.SELECTED_COLOR == (0.2, 1.0, 0.2)

    def test_candidate_colors_list(self):
        """Test candidate colors list exists and has enough colors."""
        colors = PreviewMixin.CANDIDATE_COLORS

        assert len(colors) >= 8
        # All should be RGB tuples
        for color in colors:
            assert len(color) == 3
            assert all(0 <= c <= 1 for c in color)


class TestPreviewShape:
    """Test single shape preview functionality."""

    def test_preview_shape_no_pyvista(self):
        """Test preview without PyVista returns False."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        # Mock HAS_PYVISTA to False
        with patch('gui.viewport.preview_mixin.HAS_PYVISTA', False):
            result = mixin.preview_shape("test_id")

        assert result is False

    def test_preview_shape_with_mock(self):
        """Test preview with mocked PyVista."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        # Mock the plotter and actor
        mock_plotter = Mock()
        mock_actor = Mock()
        mock_actor.prop = Mock()
        mock_actor.prop.color = (0.5, 0.5, 0.5)
        mock_actor.prop.opacity = 1.0

        mixin.plotter = mock_plotter

        # Mock _find_actor_by_shape_id to return our actor
        mixin._find_actor_by_shape_id = Mock(return_value=mock_actor)

        # Mock request_render
        with patch('gui.viewport.preview_mixin.request_render'):
            result = mixin.preview_shape("test_shape")

        assert result is True
        assert "test_shape" in mixin._preview_states
        assert mixin._preview_active is True

    def test_preview_clears_existing(self):
        """Test that preview clears existing preview first."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        # Add existing preview state
        mock_actor = Mock()
        mock_actor.prop = Mock()
        mixin._preview_states["existing"] = PreviewState(
            shape_id="existing",
            actor=mock_actor,
            original_color=(0.5, 0.5, 0.5),
            original_opacity=1.0
        )

        mock_plotter = Mock()
        mixin.plotter = mock_plotter
        mixin._find_actor_by_shape_id = Mock(return_value=None)
        mixin.clear_preview = Mock()

        with patch('gui.viewport.preview_mixin.request_render'):
            mixin.preview_shape("new_shape")

        # Should have cleared existing
        mixin.clear_preview.assert_called_once()

    def test_preview_applies_style(self):
        """Test that preview applies correct style."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        mock_actor = Mock()
        mock_actor.prop = Mock()
        mock_actor.prop.color = (0.5, 0.5, 0.5)
        mock_actor.prop.opacity = 1.0

        mock_plotter = Mock()
        mixin.plotter = mock_plotter
        mixin._find_actor_by_shape_id = Mock(return_value=mock_actor)

        with patch('gui.viewport.preview_mixin.request_render'):
            mixin.preview_shape("test_shape", color=(1.0, 0.0, 0.0))

        # Check style was applied
        assert mock_actor.prop.color == (1.0, 0.0, 0.0)
        assert mock_actor.prop.opacity == 0.8
        assert mock_actor.prop.show_edges is True
        assert mock_actor.prop.line_width == 2


class TestPreviewShapes:
    """Test multiple shape preview functionality."""

    def test_preview_shapes_empty_list(self):
        """Test preview with empty list returns False."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        with patch('gui.viewport.preview_mixin.HAS_PYVISTA', True):
            result = mixin.preview_shapes([])

        assert result is False

    def test_preview_shapes_single(self):
        """Test preview with single shape."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        mock_plotter = Mock()
        mixin.plotter = mock_plotter
        mixin._preview_single_shape_internal = Mock(return_value=True)

        with patch('gui.viewport.preview_mixin.request_render'):
            result = mixin.preview_shapes(["shape1"])

        assert result is True
        assert mixin._preview_single_shape_internal.call_count == 1

    def test_preview_shapes_multiple(self):
        """Test preview with multiple shapes."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        mock_plotter = Mock()
        mixin.plotter = mock_plotter
        mixin._preview_single_shape_internal = Mock(return_value=True)

        shapes = ["shape1", "shape2", "shape3"]

        with patch('gui.viewport.preview_mixin.request_render'):
            result = mixin.preview_shapes(shapes)

        assert result is True
        assert mixin._preview_single_shape_internal.call_count == 3

    def test_preview_shapes_with_selection(self):
        """Test preview with selected candidate."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        colors_used = []
        original_color = (0.5, 0.5, 0.5)

        def mock_preview(shape_id, mesh, color, opacity):
            colors_used.append((shape_id, color, opacity))
            return True

        mixin._preview_single_shape_internal = mock_preview

        shapes = ["shape1", "shape2", "shape3"]

        with patch('gui.viewport.preview_mixin.request_render'):
            mixin.preview_shapes(shapes, selected_index=1)

        # Check colors used
        assert len(colors_used) == 3

        # First and third should have candidate colors (opacity 0.6)
        assert colors_used[0][2] == 0.6
        assert colors_used[2][2] == 0.6

        # Second (selected) should have selected color (opacity 1.0)
        assert colors_used[1][1] == PreviewMixin.SELECTED_COLOR
        assert colors_used[1][2] == 1.0

    def test_preview_shapes_uses_distinct_colors(self):
        """Test that distinct colors are used for each candidate."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        colors_used = []

        def mock_preview(shape_id, mesh, color, opacity):
            colors_used.append(color)
            return True

        mixin._preview_single_shape_internal = mock_preview

        shapes = ["s1", "s2", "s3", "s4"]

        with patch('gui.viewport.preview_mixin.request_render'):
            mixin.preview_shapes(shapes)

        # Should use first 4 candidate colors
        assert colors_used[0] == PreviewMixin.CANDIDATE_COLORS[0]
        assert colors_used[1] == PreviewMixin.CANDIDATE_COLORS[1]
        assert colors_used[2] == PreviewMixin.CANDIDATE_COLORS[2]
        assert colors_used[3] == PreviewMixin.CANDIDATE_COLORS[3]


class TestClearPreview:
    """Test preview clearing functionality."""

    def test_clear_empty_preview(self):
        """Test clearing when no preview is active."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        # Should not raise
        mixin.clear_preview()

        assert mixin._preview_active is False

    def test_clear_restores_colors(self):
        """Test that clearing restores original colors."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        # Add preview state
        mock_actor = Mock()
        mock_actor.prop = Mock()
        original_color = (0.5, 0.5, 0.5)

        mixin._preview_states["test"] = PreviewState(
            shape_id="test",
            actor=mock_actor,
            original_color=original_color,
            original_opacity=1.0
        )
        mixin._preview_active = True

        mock_plotter = Mock()
        mixin.plotter = mock_plotter

        with patch('gui.viewport.preview_mixin.request_render'):
            mixin.clear_preview()

        # Check original color was restored
        assert mock_actor.prop.color == original_color
        assert mock_actor.prop.opacity == 1.0
        assert mock_actor.prop.show_edges is False

    def test_clear_stops_pulse(self):
        """Test that clearing stops pulse animation."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        # Mock pulse timer
        mock_timer = Mock()
        mixin._pulse_timer = mock_timer
        mixin._preview_active = True  # Set active so clear doesn't return early

        mixin.clear_preview()

        mock_timer.stop.assert_called_once()
        assert mixin._pulse_timer is None

    def test_clear_removes_temp_actors(self):
        """Test that clearing removes temporary preview actors."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        # Add temporary actor
        mock_actor = Mock()
        mixin._preview_actors.append(mock_actor)
        mixin._preview_active = True  # Set active so clear doesn't return early

        mock_plotter = Mock()
        mock_plotter.remove_actor = Mock()
        mixin.plotter = mock_plotter

        with patch('gui.viewport.preview_mixin.request_render'):
            mixin.clear_preview()

        # Actor should be removed
        mock_plotter.remove_actor.assert_called_once_with(mock_actor)
        assert len(mixin._preview_actors) == 0


class TestUpdateSelectedCandidate:
    """Test updating selected candidate highlight."""

    def test_update_nothing_when_not_active(self):
        """Test that update does nothing when preview not active."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        # Should not raise
        mixin.update_selected_candidate(0, ["shape1"])

    def test_update_selected_candidate(self):
        """Test updating selected candidate."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        # Create mock states
        states = {}
        for i in range(3):
            mock_actor = Mock()
            mock_actor.prop = Mock()
            states[f"shape{i}"] = PreviewState(
                shape_id=f"shape{i}",
                actor=mock_actor,
                original_color=(0.5, 0.5, 0.5),
                original_opacity=1.0
            )

        mixin._preview_states = states
        mixin._preview_active = True

        mock_plotter = Mock()
        mixin.plotter = mock_plotter

        with patch('gui.viewport.preview_mixin.request_render'):
            mixin.update_selected_candidate(1, ["shape0", "shape1", "shape2"])

        # First and third should have candidate colors and opacity 0.6
        assert states["shape0"].actor.prop.opacity == 0.6
        assert states["shape2"].actor.prop.opacity == 0.6

        # Second (selected) should have selected color and opacity 1.0
        assert states["shape1"].actor.prop.color == PreviewMixin.SELECTED_COLOR
        assert states["shape1"].actor.prop.opacity == 1.0

    def test_update_invalid_index(self):
        """Test update with invalid index does nothing."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        # Add some state
        mock_actor = Mock()
        mixin._preview_states["shape1"] = PreviewState(
            shape_id="shape1",
            actor=mock_actor,
            original_color=(0.5, 0.5, 0.5),
            original_opacity=1.0
        )
        mixin._preview_active = True

        # Invalid index - should not raise
        mixin.update_selected_candidate(5, ["shape1"])


class TestUtilityMethods:
    """Test utility methods."""

    def test_is_preview_active(self):
        """Test checking if preview is active."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        assert mixin.is_preview_active() is False

        mixin._preview_active = True
        assert mixin.is_preview_active() is True

    def test_get_previewed_shapes(self):
        """Test getting list of previewed shapes."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        assert mixin.get_previewed_shapes() == []

        mixin._preview_states = {"shape1": None, "shape2": None}

        shapes = mixin.get_previewed_shapes()
        assert "shape1" in shapes
        assert "shape2" in shapes

    def test_has_preview(self):
        """Test checking if specific shape is previewed."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        assert mixin.has_preview("shape1") is False

        mixin._preview_states = {"shape1": None}

        assert mixin.has_preview("shape1") is True
        assert mixin.has_preview("shape2") is False


class TestPulseAnimation:
    """Test pulse animation functionality."""

    def test_pulse_step_without_states(self):
        """Test pulse step with no preview states."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        # Should not raise
        mixin._pulse_step()

    def test_pulse_step_with_states(self):
        """Test pulse step updates opacity."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        # Create mock state
        mock_actor = Mock()
        mock_actor.prop = Mock()
        mock_actor.prop.opacity = 0.5

        mixin._preview_states = {
            "test": PreviewState(
                shape_id="test",
                actor=mock_actor,
                original_color=(0.5, 0.5, 0.5),
                original_opacity=1.0
            )
        }

        mock_plotter = Mock()
        mixin.plotter = mock_plotter

        with patch('gui.viewport.preview_mixin.request_render'):
            mixin._pulse_step()

        # Opacity should have changed
        # (direction is +1 initially, so 0.5 + 0.2 = 0.7)
        assert mock_actor.prop.opacity > 0.5

    def test_pulse_direction_change(self):
        """Test pulse direction changes at limits."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()
        mixin._pulse_direction = 1

        # Create mock state with high opacity
        mock_actor = Mock()
        mock_actor.prop = Mock()
        mock_actor.prop.opacity = 0.95

        mixin._preview_states = {
            "test": PreviewState(
                shape_id="test",
                actor=mock_actor,
                original_color=(0.5, 0.5, 0.5),
                original_opacity=1.0
            )
        }

        mock_plotter = Mock()
        mixin.plotter = mock_plotter

        with patch('gui.viewport.preview_mixin.request_render'):
            mixin._pulse_step()

        # Should hit limit and reverse direction
        assert mixin._pulse_direction == -1
        assert mock_actor.prop.opacity == 1.0


class TestFindActor:
    """Test actor finding functionality."""

    def test_find_actor_in_body_actors(self):
        """Test finding actor in body_actors."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        # Mock body actors
        mock_actor = Mock()
        mixin._body_actors = {"body_123": mock_actor}

        result = mixin._find_actor_by_shape_id("body_123")

        assert result == mock_actor

    def test_find_actor_not_found(self):
        """Test when actor is not found."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        mixin._body_actors = {}
        mixin.plotter = Mock()
        mixin.plotter.renderer = Mock()
        mixin.plotter.renderer.actors = Mock()
        mixin.plotter.renderer.actors.values = Mock(return_value=[])

        result = mixin._find_actor_by_shape_id("nonexistent")

        assert result is None


class TestAddPreviewActor:
    """Test adding preview actors."""

    def test_add_preview_actor_no_plotter(self):
        """Test adding actor when no plotter exists."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        result = mixin._add_preview_actor("test", Mock())

        assert result is None

    def test_add_preview_actor_success(self):
        """Test successfully adding preview actor."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        mock_plotter = Mock()
        mock_actor = Mock()
        mock_plotter.add_mesh = Mock(return_value=mock_actor)
        mixin.plotter = mock_plotter

        mock_mesh = Mock()

        result = mixin._add_preview_actor("test", mock_mesh)

        assert result == mock_actor
        assert mock_actor in mixin._preview_actors

    def test_add_preview_actor_error(self):
        """Test error handling when adding actor."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        mock_plotter = Mock()
        mock_plotter.add_mesh = Mock(side_effect=Exception("Test error"))
        mixin.plotter = mock_plotter

        result = mixin._add_preview_actor("test", Mock())

        assert result is None


class TestColorCycling:
    """Test color cycling for many candidates."""

    def test_colors_wrap_around(self):
        """Test that colors wrap around for many candidates."""
        mixin = PreviewMixin()
        mixin._init_preview_mixin()

        # More candidates than colors
        shapes = [f"shape{i}" for i in range(12)]
        colors_used = []

        def mock_preview(shape_id, mesh, color, opacity):
            colors_used.append(color)
            return True

        mixin._preview_single_shape_internal = mock_preview

        with patch('gui.viewport.preview_mixin.request_render'):
            mixin.preview_shapes(shapes)

        # Should wrap around and reuse colors
        assert len(colors_used) == 12
        # First 8 should match first 8 colors
        for i in range(8):
            assert colors_used[i] == PreviewMixin.CANDIDATE_COLORS[i]
        # 9th should match 1st color (index 8 wraps to 0)
        assert colors_used[8] == PreviewMixin.CANDIDATE_COLORS[0]
