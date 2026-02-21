"""
Unit Tests für FeaturePreviewMixin

Testet die Live Preview Methoden für Shell, Fillet und Chamfer.
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False


@pytest.mark.skipif(not HAS_PYVISTA, reason="PyVista not available")
class TestFeaturePreviewMixin:
    """Test Suite für FeaturePreviewMixin."""

    def setup_method(self):
        """Setup für jeden Test."""
        # Erstelle ein Mock-Viewport-Objekt mit dem Mixin
        from gui.viewport.feature_preview_mixin import FeaturePreviewMixin

        class MockViewport(FeaturePreviewMixin):
            def __init__(self):
                self.plotter = Mock()
                self.plotter.add_mesh = Mock()
                self.plotter.remove_actor = Mock()
                self._shell_mode = False
                self._fillet_preview_actors = []
                self._chamfer_preview_actors = []
                self._shell_preview_actor = None
                self._shell_target_body_id = None
                self._selected_edge_ids = set()
                self._selectable_edges = []

        self.viewport = MockViewport()

    def test_init_feature_preview(self):
        """Testet die Initialisierung des Feature Preview State."""
        self.viewport._init_feature_preview()

        assert self.viewport._shell_preview_actor is None
        assert self.viewport._fillet_preview_actors == []
        assert self.viewport._chamfer_preview_actors == []
        assert self.viewport._shell_preview_thickness == 0.0
        assert self.viewport._fillet_preview_radius == 0.0
        assert self.viewport._chamfer_preview_distance == 0.0

    def test_set_shell_mode_enabled(self):
        """Testet das Aktivieren des Shell-Modus."""
        self.viewport.set_shell_mode(True)

        assert self.viewport._shell_mode is True

    def test_set_shell_mode_disabled(self):
        """Testet das Deaktivieren des Shell-Modus."""
        self.viewport.set_shell_mode(True)
        self.viewport.set_shell_mode(False)

        assert self.viewport._shell_mode is False

    @patch('config.feature_flags.is_enabled')
    def test_update_shell_preview_disabled_by_flag(self, mock_is_enabled):
        """Testet dass Shell Preview deaktiviert wird wenn Flag False."""
        mock_is_enabled.return_value = False

        # Sollte kein add_mesh aufrufen
        self.viewport.update_shell_preview(2.0, [])
        self.viewport.plotter.add_mesh.assert_not_called()

    @patch('config.feature_flags.is_enabled')
    @patch('gui.viewport.feature_preview_mixin.request_render')
    def test_update_shell_preview_enabled(self, mock_request_render, mock_is_enabled):
        """Testet Shell Preview mit aktiviertem Flag."""
        mock_is_enabled.return_value = True

        # Mock bodies und mesh
        mock_mesh = Mock()
        mock_mesh.copy.return_value = mock_mesh
        mock_mesh.point_data = {'Normals': np.array([[0, 0, 1], [0, 0, 1]])}
        mock_mesh.compute_normals = Mock(return_value=None)

        self.viewport.bodies = {
            'test_body': {'mesh': mock_mesh}
        }
        self.viewport._shell_target_body_id = 'test_body'

        # Preview aktualisieren
        self.viewport.update_shell_preview(2.0, [])

        # Prüfe dass add_mesh aufgerufen wurde
        self.viewport.plotter.add_mesh.assert_called_once()
        mock_request_render.assert_called_once()

    @patch('config.feature_flags.is_enabled')
    @patch('gui.viewport.feature_preview_mixin.request_render')
    def test_update_fillet_preview_enabled(self, mock_request_render, mock_is_enabled):
        """Testet Fillet Preview mit aktiviertem Flag."""
        mock_is_enabled.return_value = True

        # Mock Selektierte Kanten
        from gui.viewport.edge_selection_mixin import SelectableEdge

        edge = SelectableEdge(
            id=1,
            topology_index=0,
            body_id='test_body',
            build123d_edge=None,
            center=(0, 0, 0),
            line_mesh=None,
            length=10.0,
            points=np.array([[0, 0, 0], [10, 0, 0]]),
            bbox=(0, 10, 0, 0, 0, 0)
        )

        self.viewport._selectable_edges = [edge]
        self.viewport._selected_edge_ids = {1}

        # Preview aktualisieren
        self.viewport.update_fillet_preview(2.0)

        # Prüfe dass add_mesh aufgerufen wurde (für den Tubus)
        assert self.viewport.plotter.add_mesh.call_count > 0
        mock_request_render.assert_called_once()

    @patch('config.feature_flags.is_enabled')
    @patch('gui.viewport.feature_preview_mixin.request_render')
    def test_update_chamfer_preview_enabled(self, mock_request_render, mock_is_enabled):
        """Testet Chamfer Preview mit aktiviertem Flag."""
        mock_is_enabled.return_value = True

        # Mock Selektierte Kanten
        from gui.viewport.edge_selection_mixin import SelectableEdge

        edge = SelectableEdge(
            id=1,
            topology_index=0,
            body_id='test_body',
            build123d_edge=None,
            center=(0, 0, 0),
            line_mesh=None,
            length=10.0,
            points=np.array([[0, 0, 0], [10, 0, 0]]),
            bbox=(0, 10, 0, 0, 0, 0)
        )

        self.viewport._selectable_edges = [edge]
        self.viewport._selected_edge_ids = {1}

        # Preview aktualisieren
        self.viewport.update_chamfer_preview(1.5)

        # Prüfe dass add_mesh aufgerufen wurde (für den Tubus)
        assert self.viewport.plotter.add_mesh.call_count > 0
        mock_request_render.assert_called_once()

    def test_clear_shell_preview(self):
        """Testet das Entfernen der Shell Preview."""
        self.viewport._shell_preview_actor = 'test_actor'
        self.viewport._clear_shell_preview()

        self.viewport.plotter.remove_actor.assert_called_once_with('test_actor')
        assert self.viewport._shell_preview_actor is None

    def test_clear_fillet_preview(self):
        """Testet das Entfernen der Fillet Preview."""
        self.viewport._fillet_preview_actors = ['actor1', 'actor2']
        self.viewport._clear_fillet_preview()

        assert self.viewport.plotter.remove_actor.call_count == 2
        assert self.viewport._fillet_preview_actors == []

    def test_clear_chamfer_preview(self):
        """Testet das Entfernen der Chamfer Preview."""
        self.viewport._chamfer_preview_actors = ['actor1', 'actor2']
        self.viewport._clear_chamfer_preview()

        assert self.viewport.plotter.remove_actor.call_count == 2
        assert self.viewport._chamfer_preview_actors == []

    def test_clear_all_feature_previews(self):
        """Testet das Entfernen aller Feature Previews."""
        # Setze alle Previews
        self.viewport._shell_preview_actor = 'shell_actor'
        self.viewport._fillet_preview_actors = ['fillet_actor']
        self.viewport._chamfer_preview_actors = ['chamfer_actor']

        # Alle entfernen
        self.viewport.clear_all_feature_previews()

        # Prüfe dass alle entfernt wurden
        assert self.viewport.plotter.remove_actor.call_count == 3
        assert self.viewport._shell_preview_actor is None
        assert self.viewport._fillet_preview_actors == []
        assert self.viewport._chamfer_preview_actors == []


@pytest.mark.skipif(not HAS_PYVISTA, reason="PyVista not available")
class TestFeaturePreviewIntegration:
    """Integration Tests für Feature Preview mit echten PyVista Meshes."""

    def test_shell_preview_with_real_mesh(self):
        """Testet Shell Preview mit einem echten PyVista Mesh."""
        from gui.viewport.feature_preview_mixin import FeaturePreviewMixin

        # Erstelle Mock Viewport mit echtem PyVista Plotter
        class MockViewport(FeaturePreviewMixin):
            def __init__(self):
                # Echter PyVista Plotter (headless)
                self.plotter = pv.Plotter(off_screen=True)
                self._shell_mode = False
                self._fillet_preview_actors = []
                self._chamfer_preview_actors = []
                self._shell_preview_actor = None
                self._shell_target_body_id = None
                self._selected_edge_ids = set()
                self._selectable_edges = []

        viewport = MockViewport()
        viewport._init_feature_preview()

        # Erstelle einen einfachen Würfel als Test-Mesh
        cube = pv.Cube()
        cube.compute_normals(inplace=True)

        viewport.bodies = {
            'test_body': {'mesh': cube}
        }
        viewport._shell_target_body_id = 'test_body'

        # Preview aufrufen
        with patch('config.feature_flags.is_enabled', return_value=True):
            viewport.update_shell_preview(0.5, [])

        # Prüfe dass ein Actor hinzugefügt wurde
        actors = viewport.plotter.renderer.actors
        shell_actors = [a for a in actors.values() if 'shell' in str(a).lower()]
        assert len(shell_actors) > 0, "Shell Preview Actor sollte hinzugefügt worden sein"

        # Cleanup
        viewport.plotter.close()

    def test_fillet_preview_with_real_edges(self):
        """Testet Fillet Preview mit echten Kanten-Daten."""
        from gui.viewport.feature_preview_mixin import FeaturePreviewMixin
        from gui.viewport.edge_selection_mixin import SelectableEdge

        class MockViewport(FeaturePreviewMixin):
            def __init__(self):
                self.plotter = pv.Plotter(off_screen=True)
                self._shell_mode = False
                self._fillet_preview_actors = []
                self._chamfer_preview_actors = []
                self._shell_preview_actor = None
                self._selected_edge_ids = set()
                self._selectable_edges = []

        viewport = MockViewport()
        viewport._init_feature_preview()

        # Erstelle Kante mit echten Punkten
        edge = SelectableEdge(
            id=1,
            topology_index=0,
            body_id='test_body',
            build123d_edge=None,
            center=(5, 0, 0),
            line_mesh=None,
            length=10.0,
            points=np.array([[0, 0, 0], [10, 0, 0]]),
            bbox=(0, 10, 0, 0, 0, 0)
        )

        viewport._selectable_edges = [edge]
        viewport._selected_edge_ids = {1}

        # Preview aufrufen
        with patch('config.feature_flags.is_enabled', return_value=True):
            viewport.update_fillet_preview(1.0)

        # Prüfe dass ein Actor hinzugefügt wurde
        actors = viewport.plotter.renderer.actors
        fillet_actors = [a for a in actors.values() if 'fillet' in str(a).lower()]
        assert len(fillet_actors) > 0, "Fillet Preview Actor sollte hinzugefügt worden sein"

        # Cleanup
        viewport.plotter.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
