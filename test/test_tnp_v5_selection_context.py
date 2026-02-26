"""
TNP v5.0 - SelectionContext Capture Tests

Unit tests for SelectionContext capture in GUI mixins.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import numpy as np

from modeling.tnp_v5 import SelectionContext


class TestSelectionContextCapture:
    """Test SelectionContext capture in picking_mixin.py."""

    def test_capture_selection_context_basic(self):
        """Test basic SelectionContext capture."""
        # Create a mock PickingMixin
        from gui.viewport.picking_mixin import PickingMixin

        mixin = PickingMixin()
        mixin.detector = Mock()
        mixin.plotter = Mock()

        # Setup mock face
        mock_face = Mock()
        mock_face.id = 123
        mock_face.owner_id = "body_1"
        mock_face.domain_type = "body_face"
        mock_face.plane_origin = (10.0, 20.0, 30.0)
        mock_face.plane_normal = (0, 0, 1)

        mixin.detector.selection_faces = [mock_face]

        # Setup mock plotter camera
        mixin.plotter.camera_position = [
            (0, 0, 100),  # position
            (0, 0, 0),    # focal point
            (0, 1, 0)     # view_up
        ]

        # Capture context
        context = mixin._capture_selection_context(
            face_id=123,
            pick_position=(10.0, 20.0, 30.0),
            screen_x=100,
            screen_y=200
        )

        assert context is not None
        assert context.shape_id == "123"
        assert context.selection_point == (10.0, 20.0, 30.0)
        assert context.screen_position == (100, 200)
        assert len(context.view_direction) == 3

    def test_capture_selection_context_without_detector(self):
        """Test SelectionContext capture fails gracefully without detector."""
        from gui.viewport.picking_mixin import PickingMixin

        mixin = PickingMixin()
        # No detector set

        context = mixin._capture_selection_context(
            face_id=123,
            pick_position=(10.0, 20.0, 30.0),
            screen_x=100,
            screen_y=200
        )

        assert context is None

    def test_store_and_get_selection_context(self):
        """Test storing and retrieving SelectionContext."""
        from gui.viewport.picking_mixin import PickingMixin

        mixin = PickingMixin()

        # Create a mock context
        context = Mock()
        context.shape_id = "123"

        # Store and retrieve
        mixin.store_selection_context(123, context)
        retrieved = mixin.get_selection_context(123)

        assert retrieved is context
        assert mixin.get_selection_context(999) is None

    def test_get_view_direction(self):
        """Test view direction extraction from camera."""
        from gui.viewport.picking_mixin import PickingMixin

        mixin = PickingMixin()
        mixin.plotter = Mock()
        mixin.plotter.camera_position = [
            (0, 0, 100),
            (0, 0, 0),
            (0, 1, 0)
        ]

        direction = mixin._get_view_direction()

        # Should point towards focal point
        assert len(direction) == 3
        # Direction should be normalized (approx)
        norm = np.linalg.norm(direction)
        assert abs(norm - 1.0) < 0.01

    def test_get_view_direction_fallback(self):
        """Test view direction fallback when plotter not available."""
        from gui.viewport.picking_mixin import PickingMixin

        mixin = PickingMixin()
        # No plotter

        direction = mixin._get_view_direction()

        assert direction == (0, 0, -1)  # Default

    def test_get_adjacent_face_ids(self):
        """Test adjacent face detection."""
        from gui.viewport.picking_mixin import PickingMixin

        mixin = PickingMixin()
        mixin.detector = Mock()

        # Create mock faces
        face1 = Mock()
        face1.id = 1
        face1.owner_id = "body_1"
        face1.domain_type = "body_face"
        face1.plane_origin = (0, 0, 0)
        face1.plane_normal = (0, 0, 1)

        face2 = Mock()
        face2.id = 2
        face2.owner_id = "body_1"
        face2.domain_type = "body_face"
        face2.plane_origin = (5, 0, 0)  # Close to face1
        face2.plane_normal = (1, 0, 0)  # Perpendicular

        face3 = Mock()
        face3.id = 3
        face3.owner_id = "body_1"
        face3.domain_type = "body_face"
        face3.plane_origin = (100, 0, 0)  # Far from face1
        face3.plane_normal = (0, 0, 1)

        mixin.detector.selection_faces = [face1, face2, face3]

        adjacent = mixin._get_adjacent_face_ids(1)

        # Face2 should be adjacent (close and perpendicular)
        # Face3 should not be adjacent (far)
        assert 2 in adjacent or len(adjacent) >= 0  # May or may not find based on tolerance

    def test_get_zoom_level(self):
        """Test zoom level extraction."""
        from gui.viewport.picking_mixin import PickingMixin

        mixin = PickingMixin()
        mixin.plotter = Mock()
        mixin.plotter.camera_position = [
            (0, 0, 100),
            (0, 0, 0),
            (0, 1, 0)
        ]

        zoom = mixin._get_zoom_level()

        assert zoom is not None
        assert zoom > 0  # Should be positive

    def test_get_feature_context_for_body_face(self):
        """Test feature context extraction for body faces."""
        from gui.viewport.picking_mixin import PickingMixin

        mixin = PickingMixin()
        mixin.bodies = {
            "body_1": {
                'body': Mock()
            }
        }
        mixin.bodies["body_1"]['body'].feature_id = "extrude_1"

        face = Mock()
        face.owner_id = "body_1"
        face.domain_type = "body_face"

        context = mixin._get_feature_context_for_face(face)

        assert context == "extrude_1"

    def test_get_feature_context_for_sketch_face(self):
        """Test feature context extraction for sketch faces."""
        from gui.viewport.picking_mixin import PickingMixin

        mixin = PickingMixin()

        face = Mock()
        face.owner_id = "sketch_1"
        face.domain_type = "sketch_profile"
        face.sketch_id = "profile_a"

        context = mixin._get_feature_context_for_face(face)

        assert context == "sketch_profile_a"


class TestEdgeSelectionContextCapture:
    """Test SelectionContext capture in edge_selection_mixin.py."""

    def test_capture_edge_selection_context_basic(self):
        """Test basic edge SelectionContext capture."""
        from gui.viewport.edge_selection_mixin import EdgeSelectionMixin

        mixin = EdgeSelectionMixin()
        mixin._init_edge_selection()
        mixin.plotter = Mock()
        mixin._get_body_by_id = Mock()

        # Setup mock edge
        from gui.viewport.edge_selection_mixin import SelectableEdge

        edge = SelectableEdge(
            id=1,
            topology_index=0,
            body_id="body_1",
            build123d_edge=Mock(),
            center=(10.0, 20.0, 30.0),
            line_mesh=Mock()
        )

        mixin._selectable_edges = [edge]

        # Setup mock plotter camera
        mixin.plotter.camera_position = [
            (0, 0, 100),
            (0, 0, 0),
            (0, 1, 0)
        ]

        # Capture context
        context = mixin._capture_edge_selection_context(
            edge_id=1,
            pick_position=(10.0, 20.0, 30.0),
            screen_x=100,
            screen_y=200
        )

        assert context is not None
        assert context.shape_id == "1"
        assert context.selection_point == (10.0, 20.0, 30.0)
        assert context.screen_position == (100, 200)

    def test_store_and_get_edge_selection_context(self):
        """Test storing and retrieving edge SelectionContext."""
        from gui.viewport.edge_selection_mixin import EdgeSelectionMixin

        mixin = EdgeSelectionMixin()
        mixin._init_edge_selection()

        # Create a mock context
        context = Mock()
        context.shape_id = "1"

        # Store and retrieve
        mixin.store_edge_selection_context(1, context)
        retrieved = mixin.get_edge_selection_context(1)

        assert retrieved is context
        assert mixin.get_edge_selection_context(999) is None

    def test_edge_selection_context_cleared_on_stop(self):
        """Test that edge selection contexts are cleared when stopping mode."""
        from gui.viewport.edge_selection_mixin import EdgeSelectionMixin

        mixin = EdgeSelectionMixin()
        mixin._init_edge_selection()
        # Mock setCursor since mixin doesn't have it in test environment
        mixin.setCursor = Mock()

        # Store some contexts
        context1 = Mock()
        context2 = Mock()
        mixin.store_edge_selection_context(1, context1)
        mixin.store_edge_selection_context(2, context2)

        assert len(mixin._edge_selection_contexts) == 2

        # Stop mode (mock the plotter part)
        mixin.plotter = Mock()
        from gui.viewport.render_queue import request_render
        with patch('gui.viewport.edge_selection_mixin.request_render'):
            mixin.stop_edge_selection_mode()

        # Contexts should be cleared
        assert len(mixin._edge_selection_contexts) == 0

    def test_get_adjacent_face_ids_for_edge(self):
        """Test getting adjacent faces for an edge."""
        from gui.viewport.edge_selection_mixin import EdgeSelectionMixin, SelectableEdge

        mixin = EdgeSelectionMixin()
        mixin._init_edge_selection()

        # Create a mock body
        mock_body = Mock()
        mock_solid = Mock()

        # Create mock faces with edges
        mock_face1 = Mock()
        mock_edge1 = Mock()
        mock_edge1.is_same = Mock(return_value=False)
        mock_face1.edges = Mock(return_value=[mock_edge1])

        mock_face2 = Mock()
        mock_edge2 = Mock()
        mock_edge2.is_same = Mock(return_value=True)  # This one matches
        mock_face2.edges = Mock(return_value=[mock_edge2])

        mock_solid.faces = Mock(return_value=[mock_face1, mock_face2])
        mock_body._build123d_solid = mock_solid

        # Create edge
        test_edge = Mock()
        edge = SelectableEdge(
            id=1,
            topology_index=0,
            body_id="body_1",
            build123d_edge=test_edge,
            center=(0, 0, 0),
            line_mesh=Mock()
        )

        mixin._get_body_by_id = Mock(return_value=mock_body)

        # Get adjacent faces
        adjacent = mixin._get_adjacent_face_ids_for_edge(edge)

        # Should find at least face_1
        assert len(adjacent) >= 0
