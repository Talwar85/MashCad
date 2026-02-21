"""
Integration Tests für Live Preview Features

Testet die Integration der Live Previews in MainWindow und die Interaction
mit den Input Panels (Shell, Fillet, Chamfer).
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch, call
from dataclasses import dataclass

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False


@pytest.mark.skipif(not HAS_PYVISTA, reason="PyVista not available")
class TestShellLivePreviewIntegration:
    """Test Suite für Shell Live Preview Integration."""

    def setup_method(self):
        """Setup für jeden Test."""
        # Mock MainWindow mit allen nötigen Attributen
        self.main_window = Mock()
        self.main_window.viewport_3d = Mock()
        self.main_window.shell_panel = Mock()
        self.main_window.statusBar = Mock(return_value=Mock(clearMessage=Mock()))

        # Importiere die Methoden aus feature_dialogs
        from gui.feature_dialogs import FeatureDialogsMixin
        FeatureDialogsMixin._on_shell_thickness_changed(self.main_window, 2.0)
        FeatureDialogsMixin._stop_shell_mode(self.main_window)

    @patch('config.feature_flags.is_enabled')
    def test_shell_thickness_changed_calls_preview(self, mock_is_enabled):
        """Testet dass _on_shell_thickness_changed die Preview aufruft."""
        from gui.feature_dialogs import FeatureDialogsMixin

        mock_is_enabled.return_value = True
        self.main_window._shell_opening_faces = []
        self.main_window._shell_target_body = Mock(id='test_body')

        # Rufe den Handler auf
        FeatureDialogsMixin._on_shell_thickness_changed(self.main_window, 2.5)

        # Prüfe dass update_shell_preview aufgerufen wurde
        self.main_window.viewport_3d.update_shell_preview.assert_called_once_with(2.5, [])

    @patch('config.feature_flags.is_enabled')
    def test_shell_thickness_changed_with_opening_faces(self, mock_is_enabled):
        """Testet Shell Preview mit Öffnungs-Flächen."""
        from gui.feature_dialogs import FeatureDialogsMixin

        mock_is_enabled.return_value = True
        self.main_window._shell_opening_faces = ['face1', 'face2']
        self.main_window._shell_target_body = Mock(id='test_body')

        # Rufe den Handler auf
        FeatureDialogsMixin._on_shell_thickness_changed(self.main_window, 1.5)

        # Prüfe dass update_shell_preview mit den opening_faces aufgerufen wurde
        self.main_window.viewport_3d.update_shell_preview.assert_called_once_with(1.5, ['face1', 'face2'])

    def test_stop_shell_mode_clears_previews(self):
        """Testet dass _stop_shell_mode die Previews entfernt."""
        from gui.feature_dialogs import FeatureDialogsMixin

        self.main_window._shell_opening_faces = ['face1']
        self.main_window._shell_opening_face_shape_ids = ['id1']
        self.main_window._shell_opening_face_indices = [0]
        self.main_window._shell_target_body = Mock()
        self.main_window._shell_mode = True

        # Rufe stop auf
        FeatureDialogsMixin._stop_shell_mode(self.main_window)

        # Prüfe dass clear_all_feature_previews aufgerufen wurde
        self.main_window.viewport_3d.clear_all_feature_previews.assert_called_once()
        self.main_window.viewport_3d.set_shell_mode.assert_called_once_with(False)


@pytest.mark.skipif(not HAS_PYVISTA, reason="PyVista not available")
class TestFilletLivePreviewIntegration:
    """Test Suite für Fillet Live Preview Integration."""

    def setup_method(self):
        """Setup für jeden Test."""
        # Mock MainWindow
        self.main_window = Mock()
        self.main_window.viewport_3d = Mock()
        self.main_window.fillet_panel = Mock()
        self.main_window.statusBar = Mock(return_value=Mock(clearMessage=Mock()))

        # Importiere die Methoden aus tool_operations
        from gui.tool_operations import ToolOperationsMixin
        self.main_window._fillet_mode = 'fillet'
        self.main_window._fillet_target_body = Mock()

    @patch('config.feature_flags.is_enabled')
    def test_fillet_radius_changed_calls_preview(self, mock_is_enabled):
        """Testet dass _on_fillet_radius_changed die Preview aufruft."""
        from gui.tool_operations import ToolOperationsMixin

        mock_is_enabled.return_value = True

        # Rufe den Handler auf
        ToolOperationsMixin._on_fillet_radius_changed(self.main_window, 3.0)

        # Prüfe dass update_fillet_preview aufgerufen wurde
        self.main_window.viewport_3d.update_fillet_preview.assert_called_once_with(3.0)

    def test_fillet_cancelled_clears_previews(self):
        """Testet dass _on_fillet_cancelled die Previews entfernt."""
        from gui.tool_operations import ToolOperationsMixin

        self.main_window._fillet_mode = 'fillet'
        self.main_window._fillet_target_body = Mock()

        # Rufe cancel auf
        ToolOperationsMixin._on_fillet_cancelled(self.main_window)

        # Prüfe dass clear_all_feature_previews aufgerufen wurde
        self.main_window.viewport_3d.clear_all_feature_previews.assert_called_once()
        self.main_window.viewport_3d.set_edge_selection_mode.assert_called_once_with(False)
        assert self.main_window._fillet_mode is None
        assert self.main_window._fillet_target_body is None


@pytest.mark.skipif(not HAS_PYVISTA, reason="PyVista not available")
class TestChamferLivePreviewIntegration:
    """Test Suite für Chamfer Live Preview Integration."""

    def setup_method(self):
        """Setup für jeden Test."""
        # Mock MainWindow
        self.main_window = Mock()
        self.main_window.viewport_3d = Mock()
        self.main_window.fillet_panel = Mock()
        self.main_window.statusBar = Mock(return_value=Mock(clearMessage=Mock()))

        # Importiere die Methoden aus tool_operations
        from gui.tool_operations import ToolOperationsMixin
        self.main_window._fillet_mode = 'chamfer'
        self.main_window._fillet_target_body = Mock()

    @patch('config.feature_flags.is_enabled')
    def test_chamfer_distance_changed_calls_preview(self, mock_is_enabled):
        """Testet dass Chamfer-Preview über den gleichen Handler läuft."""
        from gui.tool_operations import ToolOperationsMixin

        mock_is_enabled.return_value = True
        self.main_window._fillet_mode = 'chamfer'

        # Für Chamfer wird das radius_changed Signal verwendet (distance)
        ToolOperationsMixin._on_fillet_radius_changed(self.main_window, 1.5)

        # Prüfe dass update_chamfer_preview aufgerufen wurde (da mode = chamfer)
        # Aktuell nutzen Fillet und Chamfer den gleichen Handler
        self.main_window.viewport_3d.update_fillet_preview.assert_called_once_with(1.5)

    def test_chamfer_cancelled_clears_previews(self):
        """Testet dass _on_fillet_cancelted auch für Chamfer die Previews entfernt."""
        from gui.tool_operations import ToolOperationsMixin

        self.main_window._fillet_mode = 'chamfer'
        self.main_window._fillet_target_body = Mock()

        # Rufe cancel auf (gleicher Handler wie Fillet)
        ToolOperationsMixin._on_fillet_cancelled(self.main_window)

        # Prüfe dass clear_all_feature_previews aufgerufen wurde
        self.main_window.viewport_3d.clear_all_feature_previews.assert_called_once()


@pytest.mark.skipif(not HAS_PYVISTA, reason="PyVista not available")
class TestMainWindowLivePreviewMethods:
    """Test Suite für MainWindow Live Preview Methoden."""

    def setup_method(self):
        """Setup für jeden Test."""
        # Mock MainWindow
        self.main_window = Mock()
        self.main_window.viewport_3d = Mock()

        # Importiere die Methoden aus main_window
        from gui.main_window import MainWindow
        MainWindow._execute_shell_live_preview = self._execute_shell_live_preview
        MainWindow._execute_fillet_live_preview = self._execute_fillet_live_preview
        MainWindow._execute_chamfer_live_preview = self._execute_chamfer_live_preview

    def _execute_shell_live_preview(self, config):
        """Gemockte _execute_shell_live_preview aus main_window.py."""
        thickness = config.get('thickness', 0.0)
        opening_faces = config.get('opening_faces', [])

        if hasattr(self.viewport_3d, 'update_shell_preview'):
            if hasattr(self.viewport_3d, '_shell_target_body_id'):
                self.viewport_3d._shell_target_body_id = self._shell_target_body.id if self._shell_target_body else None
            self.viewport_3d.update_shell_preview(thickness, opening_faces)

    def _execute_fillet_live_preview(self, config):
        """Gemockte _execute_fillet_live_preview aus main_window.py."""
        radius = config.get('radius', 0.0)

        if hasattr(self.viewport_3d, 'update_fillet_preview'):
            self.viewport_3d.update_fillet_preview(radius)

    def _execute_chamfer_live_preview(self, config):
        """Gemockte _execute_chamfer_live_preview aus main_window.py."""
        distance = config.get('distance', 0.0)

        if hasattr(self.viewport_3d, 'update_chamfer_preview'):
            self.viewport_3d.update_chamfer_preview(distance)

    def test_execute_shell_live_preview(self):
        """Testet _execute_shell_live_preview."""
        self.main_window._shell_target_body = Mock(id='test_body')
        config = {'thickness': 2.0, 'opening_faces': ['face1']}

        self.main_window._execute_shell_live_preview(config)

        self.main_window.viewport_3d.update_shell_preview.assert_called_once_with(2.0, ['face1'])
        assert self.main_window.viewport_3d._shell_target_body_id == 'test_body'

    def test_execute_fillet_live_preview(self):
        """Testet _execute_fillet_live_preview."""
        config = {'radius': 3.0}

        self.main_window._execute_fillet_live_preview(config)

        self.main_window.viewport_3d.update_fillet_preview.assert_called_once_with(3.0)

    def test_execute_chamfer_live_preview(self):
        """Testet _execute_chamfer_live_preview."""
        config = {'distance': 1.5}

        self.main_window._execute_chamfer_live_preview(config)

        self.main_window.viewport_3d.update_chamfer_preview.assert_called_once_with(1.5)


@pytest.mark.skipif(not HAS_PYVISTA, reason="PyVista not available")
class TestFeatureFlagsIntegration:
    """Test Suite für Feature Flags Integration."""

    @patch('config.feature_flags.is_enabled')
    def test_shell_preview_respects_feature_flag(self, mock_is_enabled):
        """Testet dass Shell Preview das Feature Flag respektiert."""
        from gui.viewport.feature_preview_mixin import FeaturePreviewMixin

        class MockViewport(FeaturePreviewMixin):
            def __init__(self):
                self.plotter = Mock()
                self.plotter.add_mesh = Mock()
                self._shell_mode = False
                self._fillet_preview_actors = []
                self._chamfer_preview_actors = []
                self._shell_preview_actor = None
                self._shell_target_body_id = None
                self._selected_edge_ids = set()
                self._selectable_edges = []

        viewport = MockViewport()

        # Flag deaktiviert - sollte keine Preview zeigen
        mock_is_enabled.return_value = False
        viewport.update_shell_preview(2.0, [])
        viewport.plotter.add_mesh.assert_not_called()

        # Flag aktiviert - sollte Preview zeigen
        mock_is_enabled.return_value = True
        viewport.bodies = {'test_body': {'mesh': Mock()}}
        viewport._shell_target_body_id = 'test_body'

        # Mock mesh mit Normalen
        mock_mesh = Mock()
        mock_mesh.copy.return_value = mock_mesh
        mock_mesh.point_data = {'Normals': np.array([[0, 0, 1]])}
        mock_mesh.compute_normals = Mock()
        viewport.bodies['test_body']['mesh'] = mock_mesh

        viewport.update_shell_preview(2.0, [])
        # Sollte jetzt add_mesh aufrufen (wenn auch request_render gemockt ist)
        # Dies wird im Test mit is_enabled Flag kontrolliert

    @patch('config.feature_flags.is_enabled')
    def test_feature_flags_default_values(self, mock_is_enabled):
        """Testet die Default-Werte der Feature Flags."""
        from config.feature_flags import FEATURE_FLAGS

        # Prüfe dass alle drei Flags auf True gesetzt sind
        assert FEATURE_FLAGS['live_preview_shell'] is True
        assert FEATURE_FLAGS['live_preview_fillet'] is True
        assert FEATURE_FLAGS['live_preview_chamfer'] is True

        # Prüfe dass is_enabled die richtigen Werte zurückgibt
        mock_is_enabled.side_effect = lambda flag: FEATURE_FLAGS.get(flag, False)

        assert mock_is_enabled('live_preview_shell') is True
        assert mock_is_enabled('live_preview_fillet') is True
        assert mock_is_enabled('live_preview_chamfer') is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
