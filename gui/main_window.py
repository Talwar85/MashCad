"""
MashCad - Unified Main Window
V4.0: AR-005 EXTENDED - Full modular structure with all mixins

This file contains ONLY the MainWindow class definition with __init__
and mixin inheritance. All functionality is in mixin modules.
"""

import sys
import os
from loguru import logger

from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import Qt

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Import all mixins
# AR-004 Phase 1 Split: Menu and Event Handlers
from gui.menu_actions import MenuActionsMixin
from gui.event_handlers import EventHandlersMixin

# AR-005 Phase 2 Split: Sketch, Feature, Viewport, Tool Operations
from gui.sketch_operations import SketchMixin
from gui.feature_operations import FeatureMixin
from gui.viewport_operations import ViewportMixin
from gui.tool_operations import ToolMixin

# AR-005 EXTENDED: Setup, Dialogs, Feature Dialogs
from gui.main_window_setup import SetupMixin
from gui.dialog_operations import DialogMixin
from gui.feature_dialogs import FeatureDialogsMixin


class MainWindow(
    # Setup must come first for _create_ui, _create_menus, _connect_signals
    SetupMixin,
    # Menu and Event handlers
    MenuActionsMixin,
    EventHandlersMixin,
    # Feature operations
    SketchMixin,
    FeatureMixin,
    FeatureDialogsMixin,
    DialogMixin,
    # Viewport and Tools
    ViewportMixin,
    ToolMixin,
    # QMainWindow must be last for proper MRO
    QMainWindow
):
    """
    MashCAD Main Window.
    
    All functionality is provided by mixin classes:
    - SetupMixin: UI creation, menus, signal connections
    - MenuActionsMixin: File/Edit/Help menu actions
    - EventHandlersMixin: Keyboard/Event handling
    - SketchMixin: Sketch operations
    - FeatureMixin: Feature operations (extrude, fillet, etc.)
    - FeatureDialogsMixin: Pattern, Shell, Texture, Sweep, Loft dialogs
    - DialogMixin: Hole, Thread, Draft, Split, Revolve dialogs
    - ViewportMixin: Viewport operations
    - ToolMixin: Tool activation and management
    """
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MashCAD")
        self.setMinimumSize(1400, 900)

        # Window Icon setzen
        from PySide6.QtGui import QIcon
        _icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icon.ico")
        if os.path.exists(_icon_path):
            self.setWindowIcon(QIcon(_icon_path))

        # Cache leeren beim Start (für saubere B-Rep Edges)
        try:
            from modeling.cad_tessellator import CADTessellator
            CADTessellator.notify_body_changed()
        except Exception as e:
            logger.debug(f"[main_window] Fehler beim Leeren des Tessellator-Cache: {e}")
        
        # Initialize document
        from modeling import Document
        from i18n import tr
        self.document = Document("Projekt1")
        self._current_project_path = None
        
        # Initialize managers
        from gui.managers.notification_manager import NotificationManager
        from gui.managers.preview_manager import PreviewManager
        from gui.managers.tnp_debug_manager import TNPDebugManager

        self.notification_manager = NotificationManager(self)
        self.preview_manager = PreviewManager(self)
        self.tnp_debug_manager = TNPDebugManager(self)
        
        # Controllers
        from gui.sketch_controller import SketchController
        from gui.export_controller import ExportController
        from gui.feature_controller import FeatureController
        
        self.sketch_controller = SketchController(self)
        self.export_controller = ExportController(self)
        self.feature_controller = FeatureController(self)

        # TNP v4.0: Debug Callback für Edge-Auflösungs-Visualisierung
        self.tnp_debug_manager.setup_callback()

        # Undo/Redo System
        from PySide6.QtGui import QUndoStack
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(50)

        # Mode state
        self.mode = "3d"
        self.active_sketch = None
        self.selected_edges = []
        self.notifications = []
        
        # Debounce Timer für Viewport Updates
        from PySide6.QtCore import QTimer
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(50)
        self._update_timer.timeout.connect(self._update_viewport_all_impl)
        
        # Live Preview System
        self._init_preview_system()
        
        # Setup UI (from SetupMixin)
        self._apply_theme()
        self._create_ui()
        self._create_menus()
        self._connect_signals()

        # Install event filter
        QApplication.instance().installEventFilter(self)
        
        # Initial state
        self._set_mode("3d")
        self.selection_mode = "all"
        self.statusBar().showMessage("Ready")
        logger.info(tr("Ready"))
        logger.info("Ready. PyVista & Build123d active.")
    
    def _init_preview_system(self):
        """Initialize the live preview system."""
        from PySide6.QtCore import QTimer
        from config.feature_flags import FEATURE_FLAGS
        
        self._preview_timers = {}
        self._preview_configs = {}
        self._preview_debounce_ms = FEATURE_FLAGS.get("preview_debounce_ms", 150)
        
        # Initialize preview timers for each feature type
        for feature_type in ['texture', 'pattern', 'shell', 'fillet', 'chamfer']:
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(lambda ft=feature_type: self._execute_live_preview(ft))
            self._preview_timers[feature_type] = timer
            self._preview_configs[feature_type] = None
    
    # =========================================================================
    # Preview System Methods (delegated to PreviewManager)
    # =========================================================================
    
    def _preview_track_actor(self, group: str, actor_name: str):
        """Delegiert an PreviewManager."""
        self.preview_manager.track_actor(group, actor_name)

    def _preview_clear_group(self, group: str, *, render: bool = True):
        """Delegiert an PreviewManager."""
        self.preview_manager.clear_group(group, render=render)

    def _preview_clear_all(self, *, render: bool = True):
        """Delegiert an PreviewManager."""
        self.preview_manager.clear_all(render=render)

    def _clear_transient_previews(self, reason: str = "", *, clear_interaction_modes: bool = False):
        """Delegiert an PreviewManager."""
        self.preview_manager.clear_transient_previews(reason, clear_interaction_modes=clear_interaction_modes)

    def _execute_live_preview(self, feature_type: str):
        """Execute debounced live preview for a feature type."""
        from config.feature_flags import is_enabled
        
        config = self._preview_configs.get(feature_type)
        if not config:
            return
        
        try:
            if feature_type == 'texture':
                self._execute_texture_live_preview(config)
            elif feature_type == 'pattern':
                self._execute_pattern_live_preview(config)
            elif feature_type == 'shell':
                if is_enabled("live_preview_shell"):
                    self._execute_shell_live_preview(config)
            elif feature_type == 'fillet':
                if is_enabled("live_preview_fillet"):
                    self._execute_fillet_live_preview(config)
            elif feature_type == 'chamfer':
                if is_enabled("live_preview_chamfer"):
                    self._execute_chamfer_live_preview(config)
        except Exception as e:
            logger.debug(f"Live preview error for {feature_type}: {e}")
    
    def _execute_texture_live_preview(self, config: dict):
        """Execute texture live preview with LOD optimization."""
        from config.feature_flags import is_enabled
        
        body = config.get('body')
        if not body:
            return
        
        self._preview_clear_group(f"texture_preview_{body.id}", render=False)
        
        use_normal_map = is_enabled("normal_map_preview")
        
        if hasattr(self.viewport_3d, '_preview_quality'):
            self.viewport_3d._preview_quality = "live"
        if hasattr(self.viewport_3d, '_preview_mode'):
            self.viewport_3d._preview_mode = "normal_map" if use_normal_map else "displacement"
        
        self.viewport_3d.refresh_texture_previews(body.id)
        
        mode_str = "normal map" if use_normal_map else "displacement"
        logger.debug(f"Texture live preview ({mode_str}) updated for body {body.id}")
    
    def _execute_pattern_live_preview(self, config: dict):
        """Execute pattern live preview."""
        params = config.get('params', {})
        self._update_pattern_preview(params)
    
    def _execute_shell_live_preview(self, config: dict):
        """Execute shell live preview."""
        pass  # TODO: Implement when live_preview_shell is enabled
    
    def _execute_fillet_live_preview(self, config: dict):
        """Execute fillet live preview."""
        pass  # TODO: Implement when live_preview_fillet is enabled
    
    def _execute_chamfer_live_preview(self, config: dict):
        """Execute chamfer live preview."""
        pass  # TODO: Implement when live_preview_chamfer is enabled
    
    def _request_live_preview(self, feature_type: str, config: dict):
        """Request a live preview with debouncing."""
        from config.feature_flags import is_enabled
        
        flag_name = f"live_preview_{feature_type}"
        if not is_enabled(flag_name):
            return
        
        self._preview_configs[feature_type] = config
        self._preview_timers[feature_type].start(self._preview_debounce_ms)
    
    def _cancel_live_preview(self, feature_type: str):
        """Cancel a pending live preview."""
        if feature_type in self._preview_timers:
            self._preview_timers[feature_type].stop()
        self._preview_configs[feature_type] = None
    
    def _cleanup_notification(self, notif):
        """Cleanup notification."""
        self.notification_manager.cleanup_notification(notif)

    def _setup_tnp_debug_callback(self):
        """Delegiert an TNPDebugManager."""
        self.tnp_debug_manager.setup_callback()

    def _reposition_notifications(self):
        """Delegiert an NotificationManager."""
        self.notification_manager.reposition_notifications()
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _get_active_body(self):
        """Hilfsfunktion: Gibt den aktuell im Browser ausgewählten Body zurück."""
        if hasattr(self, 'browser'):
            selected = self.browser.get_selected_bodies()
            return selected[0] if selected else None
        return None
    
    def _update_body_from_build123d(self, body, solid):
        """Aktualisiert einen Body aus einem build123d Solid."""
        if not solid:
            return
        
        body._build123d_solid = solid
        
        # Tessellate for viewport
        try:
            from ocp_tessellate.tessellator import tessellate
            import pyvista as pv
            
            vertices, triangles = tessellate(solid, 0.1, 0.1)
            mesh = pv.PolyData(vertices, triangles)
            body.vtk_mesh = mesh
        except Exception as e:
            logger.debug(f"Tessellation failed: {e}")
    
    def _trigger_viewport_update(self):
        """Startet den Timer für das Update (Debounce)."""
        self._update_timer.start()

    def _update_viewport_all(self):
        """Aktualisiert ALLES im Viewport."""
        self._trigger_viewport_update()

    def _update_viewport_all_impl(self):
        """Implementierung des Viewport-Updates."""
        if not hasattr(self, 'viewport_3d') or not self.viewport_3d:
            return

        # Bodies rendern
        for body in self.document.get_all_bodies():
            if self.viewport_3d.is_body_visible(body.id):
                self._update_single_body(body)

        # Sketches rendern
        visible_sketches = self.browser.get_visible_sketches()
        self.viewport_3d.set_sketches(visible_sketches)

        # Konstruktionsebenen rendern
        self._render_construction_planes()

        # Getting Started Overlay aktualisieren
        self._update_getting_started()
    
    def _update_single_body(self, body):
        """Aktualisiert einen einzelnen Body im Viewport."""
        if not hasattr(self, 'viewport_3d') or not self.viewport_3d:
            return

        mesh = self.viewport_3d.get_body_mesh(body.id)
        if mesh is None:
            self._update_body_mesh(body)
            mesh = self.viewport_3d.get_body_mesh(body.id)

        if mesh is not None:
            color = getattr(body, 'color', (0.6, 0.6, 0.8))
            self.viewport_3d.set_body_mesh(body.id, mesh, color)

    def _update_body_mesh(self, body, mesh_override=None):
        """Lädt die Mesh-Daten aus dem Body-Objekt in den Viewport."""
        if not hasattr(self, 'viewport_3d'):
            return

        mesh = mesh_override or getattr(body, 'vtk_mesh', None)
        if mesh is None:
            solid = getattr(body, '_build123d_solid', None)
            if solid is not None:
                try:
                    from ocp_tessellate.tessellator import tessellate
                    import pyvista as pv
                    vertices, triangles = tessellate(solid, 0.1, 0.1)
                    mesh = pv.PolyData(vertices, triangles)
                    body.vtk_mesh = mesh
                except Exception as e:
                    logger.debug(f"Mesh-Tessellation fehlgeschlagen für {body.name}: {e}")
                    return

        if mesh is not None:
            color = getattr(body, 'color', (0.6, 0.6, 0.8))
            self.viewport_3d.set_body_mesh(body.id, mesh, color)

    def _update_getting_started(self):
        """Versteckt Getting-Started Overlay wenn Dokument nicht mehr leer ist."""
        if not hasattr(self, '_getting_started_overlay'):
            return
            
        has_content = False
        if hasattr(self.document, 'bodies') and self.document.bodies:
            has_content = True
        if hasattr(self.document, 'sketches') and self.document.sketches:
            has_content = True
        if hasattr(self.document, 'get_all_bodies'):
            all_bodies = self.document.get_all_bodies()
            if all_bodies:
                has_content = True

        if has_content and self._getting_started_overlay.isVisible():
            self._getting_started_overlay.hide()
    
    def _render_construction_planes(self):
        """Rendert alle Konstruktionsebenen im Viewport."""
        if hasattr(self, 'viewport_3d') and hasattr(self.document, 'planes'):
            self.viewport_3d.render_construction_planes(self.document.planes)
    
    def keyReleaseEvent(self, event):
        """Key-Release Handler für 3D-Peek."""
        if hasattr(self, 'sketch_controller') and self.sketch_controller.handle_key_release(event):
            return
        if getattr(self, '_peek_3d_active', False):
            if event.key() == Qt.Key_Space and not event.isAutoRepeat():
                self._on_peek_3d(False)
                return
        super().keyReleaseEvent(event)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Main entry point for MashCAD."""
    from PySide6.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
