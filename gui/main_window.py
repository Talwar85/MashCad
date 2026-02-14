"""
MashCad - Unified Main Window
V3.0: Refactored with MessageManager, modular structure
"""

import sys
import os
import json
import math
import uuid
import numpy as np
from loguru import logger


from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QToolBar, QStatusBar, QMenuBar, QMenu, QFileDialog,
    QMessageBox, QSplitter, QFrame, QTreeWidget, QTreeWidgetItem,
    QStackedWidget, QApplication, QDialog, QFormLayout,
    QDoubleSpinBox, QDialogButtonBox, QSpinBox, QLineEdit,
    QTableWidget, QTableWidgetItem, QPushButton, QHeaderView, QComboBox,
    QScrollArea, QGraphicsOpacityEffect, QSizePolicy, QDockWidget
)

from PySide6.QtCore import Qt, Signal, QSize, QTimer, QPointF, QEvent, QPropertyAnimation, QEasingCurve, QObject, QPoint
from PySide6.QtGui import QKeySequence, QAction, QFont, QPainter, QPen, QBrush, QColor, QPolygonF


_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from i18n import tr
from sketcher import Sketch
from modeling import Document, Body, ExtrudeFeature, FilletFeature, ChamferFeature, FeatureType, SurfaceTextureFeature, PrimitiveFeature
from modeling.brep_utils import pick_face_by_ray, find_closest_face

# GUI Module
from gui.sketch_editor import SketchEditor, SketchTool
from gui.tool_panel import ToolPanel, PropertiesPanel
from gui.tool_panel_3d import ToolPanel3D, BodyPropertiesPanel
from gui.browser import ProjectBrowser
from gui.input_panels import ExtrudeInputPanel, FilletChamferPanel, TransformPanel, CenterHintWidget, ShellInputPanel, SweepInputPanel, LoftInputPanel, PatternInputPanel, NSidedPatchInputPanel, LatticeInputPanel, MeasureInputPanel, PointToPointMovePanel
from gui.widgets.transform_toolbar import TransformToolbar
from gui.widgets.texture_panel import SurfaceTexturePanel
from gui.viewport_pyvista import PyVistaViewport, HAS_PYVISTA, HAS_BUILD123D
from gui.viewport.render_queue import request_render  # Phase 4: Performance
from gui.workers.export_worker import STLExportWorker, STEPExportWorker  # Phase 6: Async Export
from config.tolerances import Tolerances  # Phase 5: Zentralisierte Toleranzen
from config.feature_flags import is_enabled  # Performance Plan Phase 5+
from config.recent_files import get_recent_files, add_recent_file
from config.version import APP_NAME, VERSION, COPYRIGHT  # Zentrale Versionsverwaltung
from gui.log_panel import LogPanel
from gui.widgets import NotificationWidget, QtLogHandler, TNPStatsPanel, OperationSummaryWidget
from gui.widgets.section_view_panel import SectionViewPanel
from gui.widgets.brep_cleanup_panel import BRepCleanupPanel
from gui.widgets.status_bar import MashCadStatusBar
from gui.dialogs import VectorInputDialog, BooleanDialog
from gui.parameter_dialog import ParameterDialog
from gui.transform_state import TransformState

try:
    from ocp_tessellate.tessellator import tessellate
    HAS_OCP_TESSELLATE = True
except ImportError as e:
    HAS_OCP_TESSELLATE = False
    logger.critical(f"ocp-tessellate (Critical Dependency) nicht gefunden: {e}")
    logger.critical("Bitte installieren mit: pip install ocp-tessellate")
    sys.exit(1)

# Surface Texture Export
try:
    from modeling.textured_tessellator import TexturedTessellator
    from modeling.texture_exporter import apply_textures_to_body, ResultStatus
    HAS_TEXTURE_EXPORT = True
except ImportError:
    HAS_TEXTURE_EXPORT = False
    logger.debug("Texture Export Module nicht verfügbar.")


if not HAS_PYVISTA:
    logger.critical("PyVista is required! Install with: pip install pyvista pyvistaqt")
    sys.exit(1)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MashCAD")
        self.setMinimumSize(1400, 900)

        # Window Icon setzen
        import os as _os
        from PySide6.QtGui import QIcon
        _icon_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "icon.ico")
        if _os.path.exists(_icon_path):
            self.setWindowIcon(QIcon(_icon_path))

        # Cache leeren beim Start (für saubere B-Rep Edges)
        try:
            from modeling.cad_tessellator import CADTessellator
            CADTessellator.notify_body_changed()
        except Exception as e:
            logger.debug(f"[main_window] Fehler beim Leeren des Tessellator-Cache: {e}")
        
        self._setup_logging()
        self.document = Document("Projekt1")
        self._current_project_path = None  # Phase 8.2: Aktueller Projekt-Pfad
        
        # Managers
        from gui.managers.notification_manager import NotificationManager
        from gui.managers.preview_manager import PreviewManager
        from gui.managers.tnp_debug_manager import TNPDebugManager

        self.notification_manager = NotificationManager(self)
        self.preview_manager = PreviewManager(self)
        self.tnp_debug_manager = TNPDebugManager(self)

        # TNP v4.0: Debug Callback für Edge-Auflösungs-Visualisierung
        self.tnp_debug_manager.setup_callback()

        # NEU: Undo/Redo System
        from PySide6.QtGui import QUndoStack
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(50)  # Max 50 Undo-Schritte

        self.mode = "3d"
        self.active_sketch = None
        self.selected_edges = [] # Liste der Indizes für Fillet
        # Debounce Timer für Viewport Updates (Verhindert Mehrfachaufrufe)
        self.notifications = []
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(50) # 50ms warten
        self._update_timer.timeout.connect(self._update_viewport_all_impl)                                                                   
        self._apply_theme()
        self._create_ui()
        self._create_menus()
        self._connect_signals()

        QApplication.instance().installEventFilter(self)
        self._set_mode("3d")
        self.selection_mode = "all"
        self.statusBar().showMessage("Ready")
        logger.info(tr("Ready"))
        logger.info("Ready. PyVista & Build123d active.")
        
    def _setup_logging(self):
        logger.remove()
        self.qt_log_handler = QtLogHandler()
        # Verbinde Signal mit neuer zentraler Log-Methode
        self.qt_log_handler.new_message.connect(self._handle_log_message)

        # Konsole (stderr) für Debugging - nur wenn verfügbar (nicht in gebündelter App ohne Konsole)
        if sys.stderr is not None:
            logger.add(sys.stderr, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")
        # Qt Handler für GUI
        logger.add(self.qt_log_handler.write, format="{message}", level="INFO")

    def _handle_log_message(self, level, message):
        """
        Zentrale Stelle für alle Nachrichten.
        Delegiert an NotificationManager.
        """
        # 1. Ins persistente Log schreiben (nur wenn Panel existiert)
        if hasattr(self, 'log_panel') and self.log_panel:
            self.log_panel.add_message(level, message)
        
        # 2. Overlay Entscheidung
        show_overlay = False
        if level in ["success", "error", "critical"]:
            show_overlay = True
        elif level == "warning":
            # Warnings auch zeigen, aber vielleicht kürzer (optional)
            show_overlay = True
            
        if show_overlay:
            self.notification_manager.show_toast_overlay(level, message)
            
    def _show_toast_overlay(self, level, message):
        """Delegiert an NotificationManager."""
        self.notification_manager.show_toast_overlay(level, message)

    def show_notification(self, title: str, message: str, level: str = "info", duration: int = 3000):
        """Delegiert an NotificationManager."""
        self.notification_manager.show_notification(title, message, level, duration)

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



    def _cleanup_notification(self, notif):
        self.notification_manager.cleanup_notification(notif)

    def _setup_tnp_debug_callback(self):
        """Delegiert an TNPDebugManager."""
        self.tnp_debug_manager.setup_callback()

    def _reposition_notifications(self):
        """Delegiert an NotificationManager."""
        self.notification_manager.reposition_notifications()
            
    def _apply_theme(self):
        from gui.design_tokens import DesignTokens
        self.setStyleSheet(DesignTokens.stylesheet_main())
        
    def _calculate_plane_axes(self, normal_vec):
        """
        Berechnet stabile X- und Y-Achsen für eine Ebene basierend auf der Normalen.
        Muss IDENTISCH zu viewport_pyvista.py sein!
        """
        n = np.array(normal_vec)
        norm = np.linalg.norm(n)
        if norm == 0: return (1,0,0), (0,1,0)
        n = n / norm
        
        # Globale Up-Vektor Strategie (Z-Up)
        if abs(n[2]) > 0.999:
            # Normale ist (0,0,1) oder (0,0,-1)
            x_dir = np.array([1.0, 0.0, 0.0])
            y_dir = np.cross(n, x_dir)
            y_dir = y_dir / np.linalg.norm(y_dir)
            x_dir = np.cross(y_dir, n)
        else:
            global_up = np.array([0.0, 0.0, 1.0])
            x_dir = np.cross(global_up, n)
            x_dir = x_dir / np.linalg.norm(x_dir)
            y_dir = np.cross(n, x_dir)
            y_dir = y_dir / np.linalg.norm(y_dir)
            
        return tuple(x_dir), tuple(y_dir)
        
    def _create_ui(self):
        from gui.design_tokens import DesignTokens
        central = QWidget()
        central.setStyleSheet(f"background-color: {DesignTokens.COLOR_BG_PANEL.name()};")
        self.setCentralWidget(central)

        # Haupt-Layout: Vertikal (Content oben, StatusBar unten)
        main_vertical = QVBoxLayout(central)
        main_vertical.setContentsMargins(0, 0, 0, 0)
        main_vertical.setSpacing(0)

        # Content-Container für horizontales Layout
        content_widget = QWidget()
        content_widget.setStyleSheet(f"background-color: {DesignTokens.COLOR_BG_PANEL.name()};")
        layout = QHBoxLayout(content_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        main_vertical.addWidget(content_widget, stretch=1)
        
        # === HAUPTSPLITTER ===
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setStyleSheet("QSplitter { background: #262626; }")
        
        # === LINKE SEITE: Browser + Tools (innerer Splitter) ===
        left_splitter = QSplitter(Qt.Horizontal)
        left_splitter.setHandleWidth(3)

        # 1. Spalte: Tabs [Browser | TNP]
        from PySide6.QtWidgets import QTabWidget
        self.left_tabs = QTabWidget()
        self.left_tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: {DesignTokens.COLOR_BG_PANEL.name()};
            }}
            QTabBar::tab {{
                background: {DesignTokens.COLOR_BG_PANEL.name()};
                color: {DesignTokens.COLOR_TEXT_MUTED.name()};
                border: none;
                padding: 6px 14px;
                font-size: 11px;
                font-family: 'Segoe UI';
            }}
            QTabBar::tab:selected {{
                color: {DesignTokens.COLOR_TEXT_PRIMARY.name()};
                border-bottom: 2px solid {DesignTokens.COLOR_PRIMARY.name()};
            }}
            QTabBar::tab:hover {{
                color: {DesignTokens.COLOR_TEXT_SECONDARY.name()};
                background: {DesignTokens.COLOR_BG_ELEVATED.name()};
            }}
        """)

        self.browser = ProjectBrowser()
        self.browser.set_document(self.document)

        self.log_panel = LogPanel()
        self.tnp_stats_panel = TNPStatsPanel()
        self.operation_summary = OperationSummaryWidget()

        self.left_tabs.addTab(self.browser, "Browser")
        self.left_tabs.addTab(self.tnp_stats_panel, "TNP")
        self.left_tabs.setCurrentIndex(0)  # Browser default

        # Log-Panel als DockWidget (undockbar/frei positionierbar)
        self.log_dock = QDockWidget(tr("Log"), self)
        self.log_dock.setWidget(self.log_panel)
        self.log_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.log_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable)
        self.log_dock.setStyleSheet("""
            QDockWidget { color: #ccc; font-size: 11px; }
            QDockWidget::title {
                background: #252526; padding: 4px 8px;
                border-bottom: 1px solid #333;
            }
        """)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.log_dock)
        self.log_dock.hide()

        self.tnp_stats_panel.body_pick_requested.connect(self._on_tnp_body_pick_requested)

        # Backwards-compatible alias
        self.bottom_tabs = self.left_tabs

        left_splitter.addWidget(self.left_tabs)
        
        # Tool-Panel Stack (3D oder 2D)
        self.tool_stack = QStackedWidget()
        self.tool_stack.setMinimumWidth(220)
        self.tool_stack.setStyleSheet(f"background-color: {DesignTokens.COLOR_BG_PANEL.name()};")

        # PERFORMANCE: TransformPanel wird später bei line 466 erstellt
        # Doppelte Erstellung entfernt (Memory Leak verhindert)

        # NEU: Zentrale Transform-State-Machine
        self.transform_state = TransformState()
        # Legacy-Aliases für Kompatibilität (werden nach und nach ersetzt)
        self._active_transform_body = None
        self._transform_mode = None
        self._pending_transform_mode = None
        
        # 3D-ToolPanel (Index 0)
        self.tool_panel_3d = ToolPanel3D()
        self.tool_stack.addWidget(self.tool_panel_3d)
                
        # 2D-ToolPanel (Index 1) 
        self.tool_panel = ToolPanel()
        self.tool_stack.addWidget(self.tool_panel)
        
        left_splitter.addWidget(self.tool_stack)
        
        # Browser/TNP Tabs kollabierbar, ToolPanel bleibt
        left_splitter.setCollapsible(0, True)
        left_splitter.setCollapsible(1, False)
        left_splitter.setSizes([140, 200])
        
        self.main_splitter.addWidget(left_splitter)
        
        # === MITTE: Viewport / Sketch Editor ===
        self.center_stack = QStackedWidget()
        self.center_stack.setStyleSheet(f"background-color: {DesignTokens.COLOR_BG_PANEL.name()};")
        
        self.viewport_3d = PyVistaViewport()
        self.viewport_3d.document = self.document
        self.center_stack.addWidget(self.viewport_3d)

        # Getting Started Overlay (zentriert im Viewport)
        from gui.widgets.getting_started_overlay import GettingStartedOverlay
        self._getting_started_overlay = GettingStartedOverlay(self.viewport_3d)
        self._getting_started_overlay.action_triggered.connect(self._on_3d_action)
        self._getting_started_overlay.action_triggered.connect(lambda: self._getting_started_overlay.hide())
        self._getting_started_overlay.recent_file_requested.connect(self._open_recent_file)
        
        self.sketch_editor = SketchEditor()
        self.center_stack.addWidget(self.sketch_editor)
        
        self.main_splitter.addWidget(self.center_stack)
        self.sketch_editor.viewport = self.viewport_3d

        # Transform Toolbar (floating rechts im Viewport)
        self.transform_toolbar = TransformToolbar(self.viewport_3d)
        self.transform_toolbar.action_triggered.connect(self._on_3d_action)
        self.transform_toolbar.raise_()
        self.viewport_3d.installEventFilter(self)

        # Splitter-Einstellungen
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([340, 1000])
        
        layout.addWidget(self.main_splitter)
        
        # === RECHTE SEITE: Properties (nur wenn nötig) ===
        self.right_stack = QStackedWidget()
        self.right_stack.setMinimumWidth(140)
        self.right_stack.setMaximumWidth(200)
        self.right_stack.setStyleSheet(f"background-color: {DesignTokens.COLOR_BG_PANEL.name()};")
        
        # 3D-Properties (Index 0)
        self.body_properties = BodyPropertiesPanel()
        self.body_properties.opacity_changed.connect(self._on_body_opacity_changed)
        self.right_stack.addWidget(self.body_properties)

        # 2D-Properties (Index 1)
        self.properties_panel = PropertiesPanel()
        self.right_stack.addWidget(self.properties_panel)
        
        self.right_stack.setVisible(False)
        layout.addWidget(self.right_stack)

        # === STATUS BAR (unten) ===
        self.mashcad_status_bar = MashCadStatusBar()
        main_vertical.addWidget(self.mashcad_status_bar)

        # FPS Counter mit StatusBar verbinden
        from gui.viewport.render_queue import RenderQueue
        RenderQueue.register_fps_callback(self.mashcad_status_bar.update_fps)

        # Extrude Input Panel (immer sichtbar während Extrude-Modus)
        self.extrude_panel = ExtrudeInputPanel(self)
        self.extrude_panel.height_changed.connect(self._on_extrude_panel_height_changed)
        self.extrude_panel.confirmed.connect(self._on_extrude_confirmed)
        self.extrude_panel.cancelled.connect(self._on_extrude_cancelled)
        self.extrude_panel.bodies_visibility_toggled.connect(self._on_toggle_bodies_visibility)
        self.extrude_panel.bodies_visibility_state_changed.connect(self._on_bodies_visibility_state_changed)
        self.extrude_panel.operation_changed.connect(self._on_extrude_operation_changed)
        self.extrude_panel.to_face_requested.connect(self._on_to_face_requested)

        # Transform Panel
        self.transform_panel = TransformPanel(self)
        self.transform_panel.transform_confirmed.connect(self._on_transform_panel_confirmed)
        self.transform_panel.transform_cancelled.connect(self._on_transform_panel_cancelled)
        self.transform_panel.mode_changed.connect(self._on_transform_mode_changed)
        self.transform_panel.grid_size_changed.connect(self._on_grid_size_changed)
        self.transform_panel.hide()

        # Revolve Input Panel
        from gui.input_panels import RevolveInputPanel
        self.revolve_panel = RevolveInputPanel(self)
        self.revolve_panel.angle_changed.connect(self._on_revolve_angle_changed)
        self.revolve_panel.axis_changed.connect(self._on_revolve_axis_changed)
        self.revolve_panel.operation_changed.connect(self._on_revolve_operation_changed)
        self.revolve_panel.confirmed.connect(self._on_revolve_confirmed)
        self.revolve_panel.cancelled.connect(self._on_revolve_cancelled)
        self.revolve_panel.direction_flipped.connect(self._on_revolve_direction_flipped)

        # Offset Plane Input Panel
        from gui.input_panels import OffsetPlaneInputPanel
        self.offset_plane_panel = OffsetPlaneInputPanel(self)
        self.offset_plane_panel.offset_changed.connect(self._on_offset_plane_value_changed)
        self.offset_plane_panel.confirmed.connect(self._on_offset_plane_confirmed)
        self.offset_plane_panel.cancelled.connect(self._on_offset_plane_cancelled)
        self._offset_plane_pending = False

        # Hole Input Panel
        from gui.input_panels import HoleInputPanel
        self.hole_panel = HoleInputPanel(self)
        self.hole_panel.diameter_changed.connect(self._on_hole_diameter_changed)
        self.hole_panel.depth_changed.connect(self._on_hole_depth_changed)
        self.hole_panel.confirmed.connect(self._on_hole_confirmed)
        self.hole_panel.cancelled.connect(self._on_hole_cancelled)
        self._hole_mode = False
        self._hole_face_selector = None
        self._hole_face_shape_id = None
        self._hole_face_index = None

        # Thread Input Panel (für interaktive Gewinde auf zylindrischen Flächen)
        from gui.input_panels import ThreadInputPanel
        self.thread_panel = ThreadInputPanel(self)
        self.thread_panel.diameter_changed.connect(self._on_thread_diameter_changed)
        self.thread_panel.pitch_changed.connect(self._on_thread_pitch_changed)
        self.thread_panel.depth_changed.connect(self._on_thread_depth_changed)
        self.thread_panel.tolerance_changed.connect(self._on_thread_tolerance_changed)
        self.thread_panel.confirmed.connect(self._on_thread_confirmed)
        self.thread_panel.cancelled.connect(self._on_thread_cancelled)
        self._thread_mode = False
        self._thread_target_body = None
        self._thread_position = None
        self._thread_direction = None
        self._thread_detected_diameter = None
        self._thread_is_internal = False
        self._thread_face_selector = None
        self._thread_face_shape_id = None
        self._thread_face_index = None

        # Draft Input Panel
        from gui.input_panels import DraftInputPanel
        self.draft_panel = DraftInputPanel(self)
        self.draft_panel.angle_changed.connect(self._on_draft_angle_changed)
        self.draft_panel.axis_changed.connect(self._on_draft_axis_changed)
        self.draft_panel.confirmed.connect(self._on_draft_confirmed)
        self.draft_panel.cancelled.connect(self._on_draft_cancelled)
        self._draft_mode = False

        # Split Input Panel
        from gui.input_panels import SplitInputPanel
        self.split_panel = SplitInputPanel(self)
        self.split_panel.plane_changed.connect(self._on_split_plane_changed)
        self.split_panel.position_changed.connect(self._on_split_position_changed)
        self.split_panel.angle_changed.connect(self._on_split_angle_changed)
        self.split_panel.keep_changed.connect(self._on_split_keep_changed)
        self.split_panel.confirmed.connect(self._on_split_confirmed)
        self.split_panel.cancelled.connect(self._on_split_cancelled)
        self._split_mode = False

        # Center Hint Widget (große zentrale Hinweise)
        self.center_hint = CenterHintWidget(self)
        self.center_hint.hide()
        
        # Fillet/Chamfer Panel
        self.fillet_panel = FilletChamferPanel(self)
        self.fillet_panel.radius_changed.connect(self._on_fillet_radius_changed)
        self.fillet_panel.confirmed.connect(self._on_fillet_confirmed)
        self.fillet_panel.cancelled.connect(self._on_fillet_cancelled)

        self._fillet_mode = None  # 'fillet' or 'chamfer'
        self._fillet_target_body = None

        # Shell Panel (Phase 6)
        self.shell_panel = ShellInputPanel(self)
        self.shell_panel.thickness_changed.connect(self._on_shell_thickness_changed)
        self.shell_panel.confirmed.connect(self._on_shell_confirmed)
        self.shell_panel.cancelled.connect(self._on_shell_cancelled)

        self._shell_mode = False
        self._shell_target_body = None
        self._shell_opening_faces = []  # Liste der ausgewählten Öffnungs-Flächen
        self._shell_opening_face_shape_ids = []
        self._shell_opening_face_indices = []

        # Surface Texture Panel (Phase 7)
        self.texture_panel = SurfaceTexturePanel(self)
        self.texture_panel.texture_applied.connect(self._on_texture_applied)
        self.texture_panel.preview_requested.connect(self._on_texture_preview_requested)
        self.texture_panel.cancelled.connect(self._on_texture_cancelled)

        self._texture_mode = False
        self._texture_target_body = None
        self._pending_texture_mode = False  # Für Body-Selektion im Viewport
        self._pending_mesh_convert_mode = False  # Für Mesh-zu-CAD Viewport-Selektion

        # Sweep Panel (Phase 6)
        self.sweep_panel = SweepInputPanel(self)
        self.sweep_panel.confirmed.connect(self._on_sweep_confirmed)
        self.sweep_panel.cancelled.connect(self._on_sweep_cancelled)
        self.sweep_panel.sketch_path_requested.connect(self._on_sweep_sketch_path_requested)
        self.sweep_panel.profile_cleared.connect(self._on_sweep_profile_cleared)
        self.sweep_panel.path_cleared.connect(self._on_sweep_path_cleared)

        self._sweep_mode = False
        self._sweep_phase = None  # 'profile' or 'path'
        self._sweep_profile_data = None
        self._sweep_path_data = None
        self._sweep_profile_shape_id = None
        self._sweep_profile_face_index = None
        self._sweep_profile_geometric_selector = None

        # Loft Panel (Phase 6)
        self.loft_panel = LoftInputPanel(self)
        self.loft_panel.confirmed.connect(self._on_loft_confirmed)
        self.loft_panel.cancelled.connect(self._on_loft_cancelled)
        self.loft_panel.add_profile_requested.connect(self._on_loft_add_profile)

        self._loft_mode = False
        self._loft_profiles = []

        # Pattern Panel
        self.pattern_panel = PatternInputPanel(self)
        self.pattern_panel.parameters_changed.connect(self._on_pattern_parameters_changed)
        self.pattern_panel.confirmed.connect(self._on_pattern_confirmed)
        self.pattern_panel.cancelled.connect(self._on_pattern_cancelled)
        self.pattern_panel.center_pick_requested.connect(self._on_pattern_center_pick_requested)

        self._pattern_mode = False
        self._pattern_target_body = None
        self._pattern_center_pick_mode = False
        # Gruppenbasierte Preview-Aktor-Verwaltung (robustes Cleanup)
        self._preview_actor_groups = {}
        self._pending_pattern_mode = False  # Für Viewport-Selektion

        # N-Sided Patch Panel
        self.nsided_patch_panel = NSidedPatchInputPanel(self)
        self.nsided_patch_panel.confirmed.connect(self._on_nsided_patch_confirmed)
        self.nsided_patch_panel.cancelled.connect(self._on_nsided_patch_cancelled)

        self._nsided_patch_mode = False
        self._nsided_patch_target_body = None
        self._pending_nsided_patch_mode = False

        # Lattice Panel (wie Pattern - mit Viewport Body-Selektion)
        self.lattice_panel = LatticeInputPanel(self)
        self.lattice_panel.confirmed.connect(self._on_lattice_confirmed)
        self.lattice_panel.cancelled.connect(self._on_lattice_cancelled)

        self._lattice_mode = False
        self._lattice_target_body = None
        self._pending_lattice_mode = False

        # Section View Panel (Schnittansicht wie CAD)
        self.section_panel = SectionViewPanel(self)
        self.section_panel.section_enabled.connect(self._on_section_enabled)
        self.section_panel.section_disabled.connect(self._on_section_disabled)
        self.section_panel.section_position_changed.connect(self._on_section_position_changed)
        self.section_panel.section_plane_changed.connect(self._on_section_plane_changed)
        self.section_panel.section_invert_toggled.connect(self._on_section_invert_toggled)
        self.section_panel.close_requested.connect(self._toggle_section_view)
        self.section_panel.hide()  # Initially hidden

        # Measure Panel (Inspect)
        self.measure_panel = MeasureInputPanel(self)
        self.measure_panel.pick_point_requested.connect(self._on_measure_pick_requested)
        self.measure_panel.clear_requested.connect(self._clear_measure_points)
        self.measure_panel.close_requested.connect(self._close_measure_panel)
        self.measure_panel.hide()

        # Point-to-Point Move Panel
        self.p2p_panel = PointToPointMovePanel(self)
        self.p2p_panel.pick_body_requested.connect(self._on_p2p_pick_body_requested)
        self.p2p_panel.reset_requested.connect(self._reset_point_to_point_move)
        self.p2p_panel.cancel_requested.connect(self._cancel_point_to_point_move)
        self.p2p_panel.hide()
        self._p2p_body_id = None
        self._p2p_repick_body = False

        # BREP Cleanup Panel
        self.brep_cleanup_panel = BRepCleanupPanel(self)
        self.brep_cleanup_panel.feature_selected.connect(self._on_brep_cleanup_feature_selected)
        self.brep_cleanup_panel.merge_requested.connect(self._on_brep_cleanup_merge)
        self.brep_cleanup_panel.merge_all_requested.connect(self._on_brep_cleanup_merge_all)
        self.brep_cleanup_panel.close_requested.connect(self._close_brep_cleanup)
        self.brep_cleanup_panel.hide()  # Initially hidden
        self._pending_brep_cleanup_mode = False

        # BREP Cleanup Viewport Signals
        self.viewport_3d.brep_cleanup_features_changed.connect(self.brep_cleanup_panel.set_features)
        self.viewport_3d.brep_cleanup_selection_changed.connect(self.brep_cleanup_panel.update_selection)
        self.viewport_3d.brep_cleanup_face_hovered.connect(
            lambda idx, info: self.brep_cleanup_panel.update_face_info(info)
        )

        # Edge Selection Signal verbinden
        self.viewport_3d.edge_selection_changed.connect(self._on_edge_selection_changed)

        # Texture Face Selection Signal verbinden
        self.viewport_3d.texture_face_selected.connect(self._on_texture_face_selected)

        # Sketch-Pfad-Selektion für Sweep (direkter Viewport-Klick)
        self.viewport_3d.sketch_path_clicked.connect(self._on_sketch_path_clicked)

        self.tool_panel.option_changed.connect(self.sketch_editor.handle_option_changed)
        # 2. Vom Editor zum Panel (Wenn man 'X' oder 'G' drückt -> Checkbox Update)
        self.sketch_editor.construction_mode_changed.connect(self.tool_panel.set_construction)
        self.sketch_editor.grid_snap_mode_changed.connect(self.tool_panel.set_grid_snap)
        self.sketch_editor.exit_requested.connect(self._finish_sketch)
        self.sketch_editor.sketched_changed.connect(self._on_sketch_changed_refresh_viewport)
        self.sketch_editor.solver_finished_signal.connect(self._on_solver_dof_updated)
        # Toolbar entfernt - war nutzlos laut User
     
    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._reposition_all_panels)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_all_panels()

    def _reposition_all_panels(self):
        self._position_extrude_panel()
        self._position_transform_panel()
        self._position_transform_toolbar()
        self._reposition_notifications()
        if hasattr(self, '_getting_started_overlay') and self._getting_started_overlay.isVisible():
            self._getting_started_overlay.center_on_parent()
        if hasattr(self, "measure_panel") and self.measure_panel.isVisible():
            self.measure_panel.show_at(self.viewport_3d)
        if hasattr(self, "p2p_panel") and self.p2p_panel.isVisible():
            self.p2p_panel.show_at(self.viewport_3d)
        if hasattr(self, "section_panel") and self.section_panel.isVisible():
            if hasattr(self.section_panel, "clamp_to_parent"):
                self.section_panel.clamp_to_parent()
    
    def _position_extrude_panel(self):
        """Positioniert das Extrude-Panel rechts mittig im Viewport."""
        if hasattr(self, 'extrude_panel') and self.extrude_panel.isVisible():
            self.extrude_panel.adjustSize()
            pw = self.extrude_panel.width()
            ph = self.extrude_panel.height()

            if hasattr(self, 'viewport_3d') and self.viewport_3d:
                vg = self.viewport_3d.geometry()
                top_left = self.viewport_3d.mapTo(self, QPoint(0, 0))
                area_x, area_y, area_w, area_h = top_left.x(), top_left.y(), vg.width(), vg.height()
            else:
                area_x, area_y, area_w, area_h = 0, 0, self.width(), self.height()

            margin = 12
            x = area_x + area_w - pw - margin
            y = area_y + (area_h - ph) // 2

            # Position links vom Transform-Panel oder Transform-Toolbar
            if hasattr(self, 'transform_panel') and self.transform_panel.isVisible():
                x = min(x, self.transform_panel.x() - pw - margin)
                y = self.transform_panel.y() + (self.transform_panel.height() - ph) // 2
            if hasattr(self, 'transform_toolbar') and self.transform_toolbar.isVisible():
                tb_pos = self.transform_toolbar.mapTo(self, QPoint(0, 0))
                x = min(x, tb_pos.x() - pw - margin)

            x = max(area_x + margin, min(x, area_x + area_w - pw - margin))
            y = max(area_y + margin, min(y, area_y + area_h - ph - margin))

            self.extrude_panel.move(x, y)
            self.extrude_panel.raise_()

    def _position_transform_panel(self):
        """Positioniert das Transform-Panel rechts mittig im Viewport."""
        if hasattr(self, 'transform_panel') and self.transform_panel.isVisible():
            self.transform_panel.adjustSize()
            pw = self.transform_panel.width()
            ph = self.transform_panel.height()

            if hasattr(self, 'viewport_3d') and self.viewport_3d:
                vg = self.viewport_3d.geometry()
                top_left = self.viewport_3d.mapTo(self, QPoint(0, 0))
                area_x, area_y, area_w, area_h = top_left.x(), top_left.y(), vg.width(), vg.height()
            else:
                area_x, area_y, area_w, area_h = 0, 0, self.width(), self.height()

            margin = 12
            x = area_x + area_w - pw - margin
            y = area_y + (area_h - ph) // 2

            if hasattr(self, 'transform_toolbar') and self.transform_toolbar.isVisible():
                tb_pos = self.transform_toolbar.mapTo(self, QPoint(0, 0))
                x = min(x, tb_pos.x() - pw - margin)

            x = max(area_x + margin, min(x, area_x + area_w - pw - margin))
            y = max(area_y + margin, min(y, area_y + area_h - ph - margin))

            self.transform_panel.move(x, y)
            self.transform_panel.raise_()

    def _position_transform_toolbar(self):
        """Positioniert die Transform-Toolbar rechts im Viewport, vertikal zentriert."""
        if hasattr(self, 'transform_toolbar') and hasattr(self, 'viewport_3d'):
            vw = self.viewport_3d.width()
            vh = self.viewport_3d.height()
            tw = self.transform_toolbar.width()
            th = self.transform_toolbar.height()
            x = vw - tw - 8
            y = (vh - th) // 2
            self.transform_toolbar.move(x, y)
            self.transform_toolbar.raise_()

    def _on_transform_panel_confirmed(self, mode: str, data):
        """Handler wenn Transform im Panel bestätigt wird"""
        body_id = self._get_selected_body_id()
        if not body_id:
            logger.warning("Kein Body selektiert für Transform")
            return

        self._on_body_transform_requested(body_id, mode, data)
        self.transform_panel.reset_values()

    def _on_transform_panel_cancelled(self):
        """Handler wenn Transform abgebrochen wird"""
        if hasattr(self.viewport_3d, 'hide_transform_gizmo'):
            self.viewport_3d.hide_transform_gizmo()
        self.transform_panel.hide()
        self._selected_body_for_transform = None
        self.transform_toolbar.clear_active()
        
    def _on_transform_mode_changed(self, mode: str):
        """Handler wenn Transform-Modus geändert wird"""
        if hasattr(self.viewport_3d, 'set_transform_mode'):
            self.viewport_3d.set_transform_mode(mode)
        mode_to_action = {"move": "move_body", "rotate": "rotate_body", "scale": "scale_body"}
        if mode in mode_to_action:
            self.transform_toolbar.set_active(mode_to_action[mode])

    def _on_grid_size_changed(self, grid_size: float):
        """Handler wenn Grid-Size geändert wird"""
        # Update TransformState
        if hasattr(self.viewport_3d, 'transform_state') and self.viewport_3d.transform_state:
            self.viewport_3d.transform_state.snap_grid_size = grid_size
        pass

    def _on_pivot_mode_changed(self, mode: str):
        """Handler wenn Pivot-Mode geändert wird"""
        # Update TransformState
        if hasattr(self.viewport_3d, 'transform_state') and self.viewport_3d.transform_state:
            self.viewport_3d.transform_state.pivot_mode = mode
        pass

            # Info: Bei 'origin' oder 'cursor' müsste Gizmo neu positioniert werden
            # Für jetzt: Nur bei Rotate/Scale relevant

    def _get_selected_body_id(self) -> str:
        """Gibt ID des aktuell für Transform selektierten Bodies zurück"""
        if hasattr(self, '_selected_body_for_transform') and self._selected_body_for_transform:
            return self._selected_body_for_transform
        return None
        
    def _show_transform_ui(self, body_id: str, body_name: str, mode: str = None):
        """Zeigt Transform-UI für einen Body"""
        self._selected_body_for_transform = body_id

        # NEU: Extrude-Panel KOMPLETT deaktivieren (Fix 2 - verstärkt)
        if hasattr(self, 'extrude_panel'):
            self.extrude_panel.setVisible(False)
            self.extrude_panel.hide()
            self.extrude_panel.lower()  # Z-Index runter

        # Transform-Panel zeigen
        self.transform_panel.reset_values()
        if mode:
            self.transform_panel.set_mode(mode)
        self.transform_panel.show()
        self.transform_panel.raise_()
        self._position_transform_panel()

        # Gizmo zeigen
        if hasattr(self.viewport_3d, 'show_transform_gizmo'):
            self.viewport_3d.show_transform_gizmo(body_id)

        logger.info(f"Transform: {body_name} | G=Move R=Rotate S=Scale | Tab=Eingabe | Esc=Abbrechen")

    def _hide_transform_ui(self):
        """Versteckt Transform-UI und alle interaktiven Panels."""
        self._selected_body_for_transform = None
        self.transform_panel.hide()
        if hasattr(self.viewport_3d, 'hide_transform_gizmo'):
            self.viewport_3d.hide_transform_gizmo()
        if hasattr(self, 'transform_toolbar'):
            self.transform_toolbar.clear_active()

    def _on_transform_values_live_update(self, x: float, y: float, z: float):
        """Handler für Live-Update der Transform-Werte während Drag"""
        if hasattr(self, 'transform_panel') and self.transform_panel.isVisible():
            self.transform_panel.set_values(x, y, z)

    def _create_menus(self):
        mb = self.menuBar()
        
        # Datei-Menü
        file_menu = mb.addMenu(tr("File"))
        file_menu.addAction(tr("New Project"), self._new_project, QKeySequence.New)
        file_menu.addAction(tr("Open..."), self._open_project, QKeySequence.Open)
        file_menu.addAction(tr("Save..."), self._save_project, QKeySequence.Save)
        file_menu.addAction(tr("Save As..."), self._save_project_as)
        file_menu.addSeparator()
        self._recent_menu = file_menu.addMenu(tr("Recent Files"))
        self._update_recent_files_menu()
        file_menu.addSeparator()
        file_menu.addAction(tr("Export STL..."), self._export_stl)
        file_menu.addAction(tr("Export STEP..."), self._export_step)
        file_menu.addAction(tr("Import STEP..."), self._import_step)
        file_menu.addAction(tr("Export SVG..."), self._export_svg)
        file_menu.addAction(tr("Import SVG..."), self._import_svg)
        file_menu.addSeparator()
        file_menu.addAction(tr("Quit"), self.close, QKeySequence.Quit)
        
        # Bearbeiten-Menü
        edit_menu = mb.addMenu(tr("Edit"))

        # Custom Undo/Redo Actions die Sketch-Editor priorisieren
        undo_action = edit_menu.addAction(tr("Undo"), self._smart_undo)
        undo_action.setShortcut(QKeySequence.Undo)

        redo_action = edit_menu.addAction(tr("Redo"), self._smart_redo)
        redo_action.setShortcut(QKeySequence.Redo)

        edit_menu.addSeparator()
        edit_menu.addAction(tr("Parameters..."), self._show_parameters_dialog, "Ctrl+Shift+P")

        
        # Ansicht-Menü
        view_menu = mb.addMenu(tr("View"))
        view_menu.addAction(tr("Isometric"), lambda: self.viewport_3d.set_view('iso'))
        view_menu.addAction(tr("Top"), lambda: self.viewport_3d.set_view('top'))
        view_menu.addAction(tr("Front"), lambda: self.viewport_3d.set_view('front'))
        view_menu.addAction(tr("Right"), lambda: self.viewport_3d.set_view('right'))
        view_menu.addSeparator()
        view_menu.addAction(self.log_dock.toggleViewAction())

        # Hilfe-Menü
        help_menu = mb.addMenu(tr("Help"))
        help_menu.addAction(tr("Language") + " / Sprache", self._change_language)
        help_menu.addSeparator()
        help_menu.addAction(tr("About MashCad"), self._show_about)

    def _connect_signals(self):
        # 2D Tool Panel
        self.tool_panel.tool_selected.connect(self._on_sketch_tool_selected)
        self.tool_panel.option_changed.connect(self._on_opt_change)
        self.tool_panel.finish_sketch_requested.connect(self._finish_sketch)
        self.tool_panel.rotate_view_requested.connect(self._rotate_sketch_view)
        self.sketch_editor.peek_3d_requested.connect(self._on_peek_3d)

        # 3D Tool Panel
        self.tool_panel_3d.action_triggered.connect(self._on_3d_action)
        
        # Browser
        self.browser.feature_double_clicked.connect(self._edit_feature)
        self.browser.feature_selected.connect(self._on_feature_selected)
        self.browser.feature_deleted.connect(self._on_feature_deleted)  # NEU
        self.browser.rollback_changed.connect(self._on_rollback_changed)
        self.browser.plane_selected.connect(self._on_browser_plane_selected)
        self.browser.construction_plane_selected.connect(self._on_construction_plane_selected)

        # WICHTIG: Visibility changed muss ALLES neu laden (Sketches + Bodies)
        self.browser.visibility_changed.connect(self._trigger_viewport_update)

        if hasattr(self.viewport_3d, 'set_body_visibility'):
            self.browser.body_vis_changed.connect(self.viewport_3d.set_body_visibility)
        self.browser.construction_plane_vis_changed.connect(self._on_construction_plane_vis_changed)

        # Phase 3 Assembly: Component-Signale
        self.browser.component_activated.connect(self._on_component_activated)
        self.browser.component_created.connect(self._on_component_created)
        self.browser.component_deleted.connect(self._on_component_deleted)
        self.browser.component_renamed.connect(self._on_component_renamed)
        self.browser.component_vis_changed.connect(self._on_component_vis_changed)

        # Phase 6: Body/Sketch verschieben zwischen Components
        self.browser.body_moved_to_component.connect(self._on_body_moved_to_component)
        self.browser.sketch_moved_to_component.connect(self._on_sketch_moved_to_component)
        
        # Viewport Signale
        self.viewport_3d.plane_clicked.connect(self._on_plane_selected)
        if hasattr(self.viewport_3d, 'custom_plane_clicked'):
            self.viewport_3d.custom_plane_clicked.connect(self._on_custom_plane_selected)
            
        self.viewport_3d.offset_plane_drag_changed.connect(self._on_offset_plane_drag)
        self.viewport_3d.extrude_requested.connect(self._on_extrusion_finished)
        self.viewport_3d.height_changed.connect(self._on_viewport_height_changed)
        self.viewport_3d.extrude_cancelled.connect(self._on_extrude_cancelled)
        
        # NEU: Transform-Signal vom neuen Gizmo-System
        if hasattr(self.viewport_3d, 'body_transform_requested'):
            self.viewport_3d.body_transform_requested.connect(self._on_body_transform_requested)
            
        # NEU: Live-Update der Transform-Werte für Panel
        if hasattr(self.viewport_3d, 'transform_changed'):
            self.viewport_3d.transform_changed.connect(self._on_transform_values_live_update)
            
        # NEU: Copy-Signal (Shift+Drag)
        if hasattr(self.viewport_3d, 'body_copy_requested'):
            self.viewport_3d.body_copy_requested.connect(self._on_body_copy_requested)
            
        # NEU: Mirror-Signal
        if hasattr(self.viewport_3d, 'body_mirror_requested'):
            self.viewport_3d.body_mirror_requested.connect(self._on_body_mirror_requested)
            
        # NEU: Mirror-Dialog Signal
        if hasattr(self.viewport_3d, 'mirror_requested'):
            self.viewport_3d.mirror_requested.connect(self._show_mirror_dialog)

        # NEU: Body-Click für pending transform mode (Fix 1)
        if hasattr(self.viewport_3d, 'body_clicked'):
            self.viewport_3d.body_clicked.connect(self._on_viewport_body_clicked)

        # Measure-Tool Signal
        self.viewport_3d.measure_point_picked.connect(self._on_measure_point_picked)

        # NEU: Point-to-Point Move (CAD-Style)
        if hasattr(self.viewport_3d, 'point_to_point_move'):
            self.viewport_3d.point_to_point_move.connect(self._on_point_to_point_move)
        if hasattr(self.viewport_3d, 'point_to_point_start_picked'):
            self.viewport_3d.point_to_point_start_picked.connect(self._on_point_to_point_start_picked)
        if hasattr(self.viewport_3d, 'point_to_point_cancelled'):
            self.viewport_3d.point_to_point_cancelled.connect(self._on_point_to_point_cancelled)

        # NEU: TransformState-Referenz im Viewport setzen
        self.viewport_3d.transform_state = self.transform_state
        # NEU: TransformState-Referenz im Transform-Controller setzen
        if hasattr(self.viewport_3d, '_transform_ctrl'):
            self.viewport_3d._transform_ctrl.transform_state = self.transform_state

        # NEU: Face-Selection für automatische Operation-Erkennung
        if hasattr(self.viewport_3d, 'face_selected'):
            self.viewport_3d.face_selected.connect(self._on_face_selected_for_extrude)
        if hasattr(self.viewport_3d, 'target_face_selected'):
            self.viewport_3d.target_face_selected.connect(self._on_target_face_selected)
        if hasattr(self.viewport_3d, 'hole_face_clicked'):
            self.viewport_3d.hole_face_clicked.connect(self._on_body_face_clicked_for_hole)
        if hasattr(self.viewport_3d, 'thread_face_clicked'):
            self.viewport_3d.thread_face_clicked.connect(self._on_cylindrical_face_clicked_for_thread)
        if hasattr(self.viewport_3d, 'draft_face_clicked'):
            self.viewport_3d.draft_face_clicked.connect(self._on_body_face_clicked_for_draft)
        if hasattr(self.viewport_3d, 'split_body_clicked'):
            self.viewport_3d.split_body_clicked.connect(self._on_split_body_clicked)
        if hasattr(self.viewport_3d, 'split_drag_changed'):
            self.viewport_3d.split_drag_changed.connect(self._on_split_drag)

    # --- DEBOUNCED UPDATE LOGIC ---
    def _trigger_viewport_update(self):
        """Startet den Timer für das Update (Debounce)"""
        self._update_timer.start()
        self._update_getting_started()

    def _update_getting_started(self):
        """Versteckt Getting-Started Overlay wenn Dokument nicht mehr leer ist."""
        if hasattr(self, '_getting_started_overlay') and self._getting_started_overlay.isVisible():
            if hasattr(self, 'document'):
                if self.document.bodies or self.document.sketches:
                    self._getting_started_overlay.hide()
        
    # In Klasse MainWindow:
    
    # In gui/main_window.py

    def _import_mesh_dialog(self):
        """Importiert STL/OBJ Dateien als neuen Body"""
        path, _ = QFileDialog.getOpenFileName(
            self, 
            "Mesh importieren", 
            "", 
            "Mesh Files (*.stl *.obj *.ply);;All Files (*.*)"
        )
        
        if not path:
            return

        try:
            import pyvista as pv
            import os
            
            # 1. Datei laden
            mesh = pv.read(path)
            
            # FIX: n_cells statt n_faces nutzen (PyVista Update)
            if not mesh or mesh.n_cells == 0:
                logger.warning("Fehler: Leeres Mesh oder ungültiges Format.")
                return

            # 2. Neuen Body im Dokument anlegen
            filename = os.path.basename(path)
            new_body = self.document.new_body(name=filename)
            
            # 3. WICHTIG: Das Mesh direkt zuweisen (als VTK Objekt)
            new_body.vtk_mesh = mesh
            
            # 4. Viewport aktualisieren
            self.viewport_3d.add_body(
                bid=new_body.id,
                name=new_body.name,
                mesh_obj=mesh,
                color=(0.7, 0.7, 0.7) 
            )
            
            # 5. Browser aktualisieren
            self.browser.refresh()
            
            # FIX: n_cells statt n_faces für die Anzeige
            logger.info(f"Importiert: {filename} ({mesh.n_cells} Faces)")
            
            # Optional: Alles zeigen
            # self.viewport_3d.plotter.reset_camera()

        except Exception as e:
            logger.error(f"Import fehlgeschlagen: {e}")
    
    def _update_viewport_all_impl(self):
        """
        Das eigentliche Update, wird vom Timer aufgerufen.

        SMART UPDATE: Entfernt/fügt nur Bodies hinzu die sich wirklich geändert haben.
        Verhindert Flicker bei unveränderten Bodies.
        """
        if not HAS_PYVISTA:
            return

        # 1. Sketches updaten
        visible_sketches = self.browser.get_visible_sketches()
        self.viewport_3d.set_sketches(visible_sketches)

        # 2. Bodies SMART updaten - kein clear_bodies() mehr!
        default_color = (0.7, 0.7, 0.7)
        colors = [(0.6, 0.6, 0.8), (0.8, 0.6, 0.6), (0.6, 0.8, 0.6)]

        visible_bodies = self.browser.get_visible_bodies()

        # Sammle alle Body-IDs die sichtbar sein sollen
        should_be_visible = set()

        for i, body_info in enumerate(visible_bodies):
            # Backward-compatible: 2 oder 3 Elemente
            if len(body_info) == 3:
                b, visible, is_inactive = body_info
            else:
                b, visible = body_info
                is_inactive = False

            if not visible:
                continue

            should_be_visible.add(b.id)

            # Prüfe ob Body bereits im Viewport ist mit korrektem State
            existing = self.viewport_3d.bodies.get(b.id)
            if existing:
                # Body existiert - prüfe ob Opacity-Update nötig
                current_opacity = existing.get('opacity', 1.0)
                target_opacity = 0.35 if is_inactive else 1.0

                if abs(current_opacity - target_opacity) > 0.01:
                    # Nur Opacity updaten, kein Mesh-Refresh
                    self.viewport_3d.set_body_appearance(b.id, inactive=is_inactive)
                continue  # Body existiert bereits, nichts weiter tun

            # Body ist NEU - hinzufügen
            try:
                col = getattr(b, 'color', default_color)
                if col is None:
                    col = default_color

                # Phase 9: Async Tessellation wenn Flag aktiv und Mesh noch nicht generiert
                if (is_enabled("async_tessellation") and
                    hasattr(b, 'request_async_tessellation') and
                    hasattr(b, '_mesh_cache_valid') and not b._mesh_cache_valid):

                    def _make_async_callback(body_ref, color_ref, inactive_ref):
                        def _on_ready(body_id, mesh, edges, face_info):
                            if mesh is None:
                                return
                            self.viewport_3d.add_body(
                                bid=body_id,
                                name=body_ref.name,
                                mesh_obj=mesh,
                                edge_mesh_obj=edges,
                                color=color_ref,
                                inactive_component=inactive_ref
                            )
                            if hasattr(self.viewport_3d, 'plotter'):
                                from gui.viewport.render_queue import request_render
                                request_render(self.viewport_3d.plotter, immediate=True)
                        return _on_ready

                    b.request_async_tessellation(on_ready=_make_async_callback(b, col, is_inactive))

                elif hasattr(b, 'vtk_mesh') and b.vtk_mesh is not None:
                    self.viewport_3d.add_body(
                        bid=b.id,
                        name=b.name,
                        mesh_obj=b.vtk_mesh,
                        edge_mesh_obj=b.vtk_edges,
                        color=col,
                        inactive_component=is_inactive
                    )
                elif hasattr(b, '_mesh_vertices') and b._mesh_vertices:
                    self.viewport_3d.add_body(
                        bid=b.id,
                        name=b.name,
                        verts=b._mesh_vertices,
                        faces=b._mesh_triangles,
                        color=colors[i % 3],
                        inactive_component=is_inactive
                    )
            except Exception as e:
                logger.exception(f"Fehler beim Laden von Body {b.name}: {e}")

        # 3. Bodies entfernen die nicht mehr sichtbar sein sollen
        current_body_ids = set(self.viewport_3d.bodies.keys())
        to_remove = current_body_ids - should_be_visible

        for body_id in to_remove:
            self.viewport_3d.clear_bodies(only_body_id=body_id)

        # Finales Rendering nur wenn nötig
        if to_remove or (should_be_visible - current_body_ids):
            if hasattr(self.viewport_3d, 'plotter'):
                request_render(self.viewport_3d.plotter, immediate=True)
            self.viewport_3d.update()

    def _update_single_body(self, body):
        """
        Aktualisiert NUR EINEN Body im Viewport - ohne Flicker bei anderen Bodies.

        Performance-Optimierung: Verwendet update_single_body() statt clear_bodies().

        Args:
            body: Body-Objekt das aktualisiert werden soll
        """
        if not HAS_PYVISTA:
            return

        # Prüfe ob Body in inaktiver Component ist
        is_inactive = False
        if hasattr(self.document, '_assembly_enabled') and self.document._assembly_enabled:
            active_comp = self.document._active_component
            # Finde Component die diesen Body enthält
            comp = self._find_component_for_body(body)
            if comp and comp != active_comp:
                # Prüfe ob comp ein Sub-Component der aktiven ist
                is_sub = False
                current = comp
                while current:
                    if current == active_comp:
                        is_sub = True
                        break
                    current = current.parent
                is_inactive = not is_sub

        # Body aktualisieren
        col = getattr(body, 'color', (0.7, 0.7, 0.7))
        if col is None:
            col = (0.7, 0.7, 0.7)

        if hasattr(self.viewport_3d, 'update_single_body'):
            self.viewport_3d.update_single_body(body, color=col, inactive_component=is_inactive)
        else:
            # Fallback: Full refresh (alt)
            self._update_viewport_all_impl()

    def _find_component_for_body(self, body):
        """Findet die Component die einen Body enthält."""
        if not hasattr(self.document, 'root_component'):
            return None

        def search(comp):
            if body in comp.bodies:
                return comp
            for sub in comp.sub_components:
                result = search(sub)
                if result:
                    return result
            return None

        return search(self.document.root_component)

    _TOOL_HINTS = {
        'new_sketch': ("Sketch", tr("Select a plane or face · Esc: cancel")),
        'extrude': ("Extrude", tr("Select closed profile, set height · Enter: confirm · Esc: cancel")),
        'revolve': ("Revolve", tr("Select profile + axis · Enter: confirm · Esc: cancel")),
        'sweep': ("Sweep", tr("Select profile, then path · Esc: cancel")),
        'loft': ("Loft", tr("Select 2+ profiles · Esc: cancel")),
        'fillet': ("Fillet", tr("Select edges, set radius · Enter: confirm · Esc: cancel")),
        'chamfer': ("Chamfer", tr("Select edges, set distance · Enter: confirm · Esc: cancel")),
        'shell': ("Shell", tr("Select face to open, set thickness · Esc: cancel")),
        'hole': ("Hole", tr("Select planar face · Esc: cancel")),
        'draft': ("Draft", tr("Select faces, set angle · Esc: cancel")),
        'measure': ("Measure", tr("Click two points or edges to measure")),
        'split_body': ("Split", tr("Select body, choose plane · Esc: cancel")),
        'pattern': ("Pattern", tr("Select body, set count/spacing · Esc: cancel")),
        'thread': ("Thread", tr("Select cylindrical face · Esc: cancel")),
        'surface_texture': ("Texture", tr("Select body, choose texture type")),
    }

    def _on_3d_action(self, action: str):
        """Verarbeitet 3D-Tool-Aktionen"""
        if hasattr(self, '_getting_started_overlay'):
            self._getting_started_overlay.hide()

        hint = self._TOOL_HINTS.get(action)
        if hint and hasattr(self, 'mashcad_status_bar'):
            self.mashcad_status_bar.set_tool_hint(hint[0], hint[1])

        actions = {
            'new_sketch': self._new_sketch,
            'offset_plane': self._start_offset_plane,
            'extrude': self._extrude_dialog,
            'import_mesh': self._import_mesh_dialog,
            'export_stl': self._export_stl,
            'export_step': self._export_step,
            'export_dxf': lambda: self._show_not_implemented("DXF Export"),
            'primitive_box': lambda: self._primitive_dialog("box"),
            'primitive_cylinder': lambda: self._primitive_dialog("cylinder"),
            'primitive_sphere': lambda: self._primitive_dialog("sphere"),
            'primitive_cone': lambda: self._primitive_dialog("cone"),
            'revolve': self._revolve_dialog,
            'sweep': self._start_sweep,
            'loft': self._start_loft,
            
            # --- Implementierte Transformationen ---
            'move_body': lambda: self._start_transform_mode("move"),
            'copy_body': self._copy_body,
            'rotate_body': lambda: self._start_transform_mode("rotate"),
            'mirror_body': self._mirror_body,
            'scale_body': lambda: self._start_transform_mode("scale"),
            'point_to_point_move': self._start_point_to_point_move,
            
            # --- Implementierte Booleans ---
            'boolean_union': lambda: self._boolean_operation_dialog("Union"),
            'boolean_cut': lambda: self._boolean_operation_dialog("Cut"),
            'boolean_intersect': lambda: self._boolean_operation_dialog("Intersect"),
            
            'fillet': self._start_fillet,
            'chamfer': self._start_chamfer,

            # Inspection Tools
            'section_view': self._toggle_section_view,

            'export_dxf': lambda: self._show_not_implemented("DXF Export"),

            'shell': self._start_shell,
            'surface_texture': self._start_texture_mode,
            'hole': self._hole_dialog,
            'draft': self._draft_dialog,
            'split_body': self._split_body_dialog,
            'thread': self._thread_dialog,
            'sketch_agent': self._sketch_agent_dialog,

            'measure': self._start_measure_mode,
            'mass_props': lambda: self._show_not_implemented("Masseeigenschaften"),
            'geometry_check': self._geometry_check_dialog,
            'surface_analysis': self._surface_analysis_dialog,
            'nsided_patch': self._nsided_patch_dialog,
            'mesh_repair': self._mesh_repair_dialog,
            'hollow': self._hollow_dialog,
            'wall_thickness': self._wall_thickness_dialog,
            'lattice': self._start_lattice,
            'pattern': self._start_pattern,
            'convert_to_brep': self._convert_selected_body_to_brep,
            'brep_cleanup': self._toggle_brep_cleanup,
        }
        
        if action in actions:
            actions[action]()
        else:
            logger.warning(f"Unbekannte 3D-Aktion: {action}")
            
    def _convert_selected_body_to_brep(self):
        """Konvertiert ausgewählten Mesh-Body zu BREP-Solid."""
        from PySide6.QtWidgets import QApplication, QMessageBox
        from PySide6.QtCore import Qt

        body = self._get_active_body()
        if not body:
            # Kein Body gewählt → Pending-Mode (wie bei Fillet/Chamfer)
            self._pending_mesh_convert_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)

            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)

            logger.info("Mesh zu CAD: Klicke auf einen Mesh-Körper in der 3D-Ansicht")
            return

        if body._build123d_solid is not None:
            logger.info(f"'{body.name}' ist bereits ein CAD-Solid.")
            return

        if body.vtk_mesh is None:
            logger.warning("Kein Mesh vorhanden zum Konvertieren.")
            return

        logger.info(f"Konvertiere '{body.name}' zu BREP (bitte warten)...")

        # UI updaten und Cursor auf "Warten" setzen
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()

        try:
            success = body.convert_to_brep()

            if success:
                logger.success(f"Erfolg! '{body.name}' ist jetzt ein CAD-Solid.")

                # Browser aktualisieren
                self.browser.refresh()

                # VIEWPORT FIX: Alte Darstellung entfernen
                if body.id in self.viewport_3d._body_actors:
                    for actor_name in self.viewport_3d._body_actors[body.id]:
                        try:
                            self.viewport_3d.plotter.remove_actor(actor_name)
                        except: pass
                    # Auch aus _body_actors entfernen
                    del self.viewport_3d._body_actors[body.id]
                
                # WICHTIG: Body aus viewport.bodies entfernen damit er neu geladen wird
                # (sonst überspringt _update_viewport_all_impl den Body weil er existiert)
                if body.id in self.viewport_3d.bodies:
                    del self.viewport_3d.bodies[body.id]

                # Neu laden
                self._update_viewport_all_impl()

                # Rendern erzwingen
                if hasattr(self.viewport_3d, 'plotter'):
                    request_render(self.viewport_3d.plotter, immediate=True)
                    self.viewport_3d.update()

            else:
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(
                    self,
                    "Fehler",
                    "Konvertierung fehlgeschlagen.\nIst das Mesh geschlossen und valide?"
                )
                logger.error("Mesh-zu-BREP Konvertierung fehlgeschlagen")

        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Fehler", f"Kritischer Fehler: {e}")
            traceback.print_exc()

        finally:
            QApplication.restoreOverrideCursor()

    def _on_body_clicked_for_mesh_convert(self, body_id: str):
        """
        Callback wenn im Pending-Mode ein Body für Mesh-Konvertierung angeklickt wird.
        """
        from PySide6.QtWidgets import QApplication, QMessageBox
        from PySide6.QtCore import Qt

        self._pending_mesh_convert_mode = False

        # Pending-Mode deaktivieren
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        # Body finden
        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.warning(f"Body {body_id} nicht gefunden")
            return

        # Prüfungen
        if body._build123d_solid is not None:
            logger.info(f"'{body.name}' ist bereits ein CAD-Solid.")
            return

        if body.vtk_mesh is None:
            logger.warning("Kein Mesh vorhanden zum Konvertieren.")
            return

        logger.info(f"Konvertiere '{body.name}' zu BREP (bitte warten)...")

        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()

        try:
            success = body.convert_to_brep()

            if success:
                logger.success(f"Erfolg! '{body.name}' ist jetzt ein CAD-Solid.")
                self.browser.refresh()

                if body.id in self.viewport_3d._body_actors:
                    for actor_name in self.viewport_3d._body_actors[body.id]:
                        try:
                            self.viewport_3d.plotter.remove_actor(actor_name)
                        except: pass
                    del self.viewport_3d._body_actors[body.id]
                
                # WICHTIG: Body aus viewport.bodies entfernen damit er neu geladen wird
                if body.id in self.viewport_3d.bodies:
                    del self.viewport_3d.bodies[body.id]

                self._update_viewport_all_impl()

                if hasattr(self.viewport_3d, 'plotter'):
                    request_render(self.viewport_3d.plotter, immediate=True)
                    self.viewport_3d.update()
            else:
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(
                    self,
                    "Fehler",
                    "Konvertierung fehlgeschlagen.\nIst das Mesh geschlossen und valide?"
                )
                logger.error("Mesh-zu-BREP Konvertierung fehlgeschlagen")

        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Fehler", f"Kritischer Fehler: {e}")
            import traceback
            traceback.print_exc()

        finally:
            QApplication.restoreOverrideCursor()

    def _show_not_implemented(self, feature: str):
        """Zeigt Hinweis für noch nicht implementierte Features"""
        logger.warning(f"{feature} - {tr('Coming soon!')}", 3000)
    
    def _on_sketch_tool_selected(self, tool_name: str):
        """Verarbeitet Tool-Auswahl aus dem Sketch-ToolPanel"""
        # Spezielle Aktionen (kein Tool-Wechsel)
        special_actions = {
            'import_dxf': self.sketch_editor.import_dxf,
            'export_dxf': self.sketch_editor.export_dxf,
            'import_svg': lambda: self._show_not_implemented("SVG Import"),
            'export_svg': lambda: self._show_not_implemented("SVG Export"),
        }
        
        if tool_name in special_actions:
            special_actions[tool_name]()
        else:
            # Normaler Tool-Wechsel
            tool = getattr(SketchTool, tool_name.upper(), SketchTool.SELECT)
            self.sketch_editor.set_tool(tool)
    
    def _get_export_candidates(self):
        """
        Hilfsfunktion: Gibt eine Liste von Bodies zurück.
        Entweder der aktuell selektierte, oder ALLE sichtbaren, wenn nichts selektiert ist.
        """
        selected = self._get_active_body()
        if selected:
            return [selected]
        
        # Wenn nichts selektiert ist, nehmen wir alle sichtbaren
        candidates = []
        for body in self.document.bodies:
            # Check visibility via viewport
            if self.viewport_3d.is_body_visible(body.id):
                candidates.append(body)
        return candidates
        
    def _on_feature_selected(self, data):
        """Wird aufgerufen wenn ein Feature im Tree ausgewählt wird"""
        # Vorheriges Highlight entfernen
        if hasattr(self, '_highlighted_body_id') and self._highlighted_body_id:
            self.viewport_3d.unhighlight_body(self._highlighted_body_id)
            self._highlighted_body_id = None

        if data and len(data) >= 2:
            if data[0] == 'body':
                body = data[1]
                self.body_properties.update_body(body)
                self.statusBar().showMessage(f"Body: {body.name}")
                if hasattr(body, 'id'):
                    self._selected_body_for_transform = body.id
                    self.viewport_3d.highlight_body(body.id)
                    self._highlighted_body_id = body.id
                self._update_tnp_stats(body)
                self.browser.show_rollback_bar(body)
            elif data[0] == 'feature' and len(data) >= 3:
                feature = data[1]
                body = data[2]
                self.statusBar().showMessage(f"Feature: {feature.name}")
                # Highlight den Body des Features
                if hasattr(body, 'id'):
                    self.viewport_3d.highlight_body(body.id)
                    self._highlighted_body_id = body.id
                self.body_properties.clear()
                self._hide_transform_ui()
                self._update_tnp_stats(body)
            else:
                self.statusBar().showMessage("Ready")
                self.body_properties.clear()
                self._hide_transform_ui()
                self._update_tnp_stats()
    
    def _start_transform_mode(self, mode):
        """
        Startet den Transform-Modus.
        Unterstützt Multi-Select aus Browser.
        """
        # Toolbar-Button highlighten
        mode_to_action = {"move": "move_body", "rotate": "rotate_body", "scale": "scale_body"}
        if mode in mode_to_action:
            self.transform_toolbar.set_active(mode_to_action[mode])

        # WICHTIG: Extrude-Panel KOMPLETT deaktivieren, auch im pending mode
        if hasattr(self, 'extrude_panel'):
            self.extrude_panel.setVisible(False)
            self.extrude_panel.hide()
            self.extrude_panel.lower()  # Z-Index runter

        # NEU: Prüfe Multi-Select im Browser
        selected_bodies = self.browser.get_selected_bodies()

        # Fall 1: Kein Body gewählt -> Warte auf Selektion
        if not selected_bodies:
            # NEU: State-Machine verwenden
            self.transform_state.start_pending_transform(mode)
            # Legacy-Kompatibilität
            self._pending_transform_mode = mode

            self.viewport_3d.setCursor(Qt.CrossCursor)
            # Aktiviere Body-Highlighting im Viewport
            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)

            logger.info(f"{mode.capitalize()}: Wähle einen oder mehrere Bodies im Browser oder 3D-Ansicht")
            return

        # Fall 2: Single-Body -> Standard-Verhalten mit Gizmo
        if len(selected_bodies) == 1:
            body = selected_bodies[0]
            # NEU: State-Machine verwenden
            self.transform_state.start_transform(mode, body.id)
            # Legacy-Kompatibilität
            self._transform_mode = mode
            self._active_transform_body = body
            self._pending_transform_mode = None

            self.viewport_3d.setCursor(Qt.ArrowCursor)

            # Transform-UI zeigen
            self._show_transform_ui(body.id, body.name, mode)

            # WICHTIG: Mode auf Viewport setzen, damit Gizmo korrekt angezeigt wird
            if hasattr(self.viewport_3d, 'set_transform_mode'):
                self.viewport_3d.set_transform_mode(mode)

            logger.success(f"{mode.capitalize()}: {body.name} - Ziehe am Gizmo oder Tab für Eingabe")

        # Fall 3: Multi-Body -> Zeige Dialog für numerische Eingabe (kein Gizmo)
        else:
            # NEU: Multi-Select Transform via Dialog
            self._start_multi_body_transform(mode, selected_bodies)

    def _start_multi_body_transform(self, mode: str, bodies: list):
        """
        Startet Multi-Body Transform mit numerischer Eingabe-Dialog.

        Args:
            mode: "move", "rotate", "scale"
            bodies: Liste von Body-Objekten
        """
        from PySide6.QtWidgets import QInputDialog

        body_count = len(bodies)
        body_names = ", ".join([b.name for b in bodies[:3]]) + (f" +{body_count-3} mehr" if body_count > 3 else "")

        logger.info(f"{mode.capitalize()}: {body_count} Bodies selektiert - {body_names}")

        # Zeige Input-Dialog basierend auf Modus
        if mode == "move":
            text, ok = QInputDialog.getText(
                self,
                f"Multi-Body Move ({body_count} Bodies)",
                f"Verschiebung (X, Y, Z in mm):\nFormat: 10, 0, 5\n\nBodies: {body_names}",
                text="0, 0, 0"
            )
            if ok and text:
                try:
                    coords = [float(x.strip()) for x in text.split(",")]
                    if len(coords) == 3:
                        body_ids = [b.id for b in bodies]
                        self._on_body_transform_requested(body_ids, "move", {"translation": coords})
                except ValueError:
                    logger.error(f"Ungültige Eingabe: {text}")

        elif mode == "rotate":
            text, ok = QInputDialog.getText(
                self,
                f"Multi-Body Rotate ({body_count} Bodies)",
                f"Rotation (Achse, Winkel):\nFormat: Z, 45\n\nBodies: {body_names}",
                text="Z, 0"
            )
            if ok and text:
                try:
                    parts = [x.strip() for x in text.split(",")]
                    axis = parts[0].upper()
                    angle = float(parts[1])
                    if axis in ["X", "Y", "Z"]:
                        body_ids = [b.id for b in bodies]
                        self._on_body_transform_requested(body_ids, "rotate", {"axis": axis, "angle": angle})
                except (ValueError, IndexError):
                    logger.error(f"Ungültige Eingabe: {text}")

        elif mode == "scale":
            factor, ok = QInputDialog.getDouble(
                self,
                f"Multi-Body Scale ({body_count} Bodies)",
                f"Skalierungs-Faktor:\n\nBodies: {body_names}",
                value=1.0,
                min=0.01,
                max=100.0,
                decimals=2
            )
            if ok:
                body_ids = [b.id for b in bodies]
                self._on_body_transform_requested(body_ids, "scale", {"factor": factor})

    def _start_point_to_point_move(self):
        """Startet Point-to-Point Move Modus (CAD-Style) - OHNE Body-Selektion möglich"""
        self.transform_toolbar.set_active("point_to_point_move")
        body = self._get_active_body()

        if not body:
            # Warte auf Body-Selektion (wie bei Move/Rotate/Scale)
            self._pending_transform_mode = "point_to_point"
            self.viewport_3d.setCursor(Qt.CrossCursor)
            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)

            logger.info("Point-to-Point Move: Wähle einen Body im Browser oder 3D-Ansicht")
            if hasattr(self, "p2p_panel"):
                self._p2p_body_id = None
                self.p2p_panel.reset()
                self.p2p_panel.set_status(tr("Pick body"))
                self.p2p_panel.show_at(self.viewport_3d)
            return

        # Body vorhanden -> Starte Point-to-Point Modus
        if hasattr(self.viewport_3d, 'start_point_to_point_mode'):
            self.viewport_3d.start_point_to_point_mode(body.id)
            logger.success(f"Point-to-Point Move für {body.name}: Wähle Start-Punkt, dann Ziel-Punkt")
            if hasattr(self, "p2p_panel"):
                self._p2p_body_id = body.id
                self.p2p_panel.reset()
                self.p2p_panel.set_body(body.name)
                self.p2p_panel.set_status(tr("Pick start point"))
                self.p2p_panel.show_at(self.viewport_3d)
            self._p2p_repick_body = False

    def _on_viewport_body_clicked(self, body_id: str):
        """
        Handler für Body-Klick im Viewport.
        Unterstützt:
        - Pending Transform Mode (Move/Rotate/Scale)
        - Pending Fillet/Chamfer Mode
        - Point-to-Point Move
        """
        # Prüfe auf Split Pending Mode
        if getattr(self, '_pending_split_mode', False):
            self._pending_split_mode = False
            self.viewport_3d.setCursor(Qt.ArrowCursor)
            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(False)
            self._on_split_body_clicked(body_id)
            return

        # Prüfe auf Fillet/Chamfer Pending Mode (NEU)
        if hasattr(self, '_pending_fillet_mode') and self._pending_fillet_mode:
            self._on_body_clicked_for_fillet(body_id)
            return

        # Prüfe auf Thread Pending Mode
        if getattr(self, '_pending_thread_mode', False):
            self._on_body_clicked_for_thread(body_id)
            return

        # Prüfe auf BREP Cleanup Pending Mode
        if getattr(self, '_pending_brep_cleanup_mode', False):
            self._on_body_clicked_for_brep_cleanup(body_id)
            return

        # Prüfe auf Shell Pending Mode (Phase 6)
        if getattr(self, '_pending_shell_mode', False):
            self._on_body_clicked_for_shell(body_id)
            return

        # Prüfe auf Texture Pending Mode (Phase 7)
        if getattr(self, '_pending_texture_mode', False):
            self._on_body_clicked_for_texture(body_id)
            return

        # Prüfe auf Mesh Convert Pending Mode
        if getattr(self, '_pending_mesh_convert_mode', False):
            self._on_body_clicked_for_mesh_convert(body_id)
            return

        # Prüfe auf Pattern Pending Mode
        if getattr(self, '_pending_pattern_mode', False):
            self._on_body_clicked_for_pattern(body_id)
            return

        # Prüfe auf Lattice Pending Mode
        if getattr(self, '_pending_lattice_mode', False):
            self._on_body_clicked_for_lattice(body_id)
            return

        # Prüfe auf N-Sided Patch Pending Mode
        if getattr(self, '_pending_nsided_patch_mode', False):
            self._on_body_clicked_for_nsided_patch(body_id)
            return

        # Prüfe auf Geometry Check Pending Mode
        if getattr(self, '_pending_geometry_check_mode', False):
            self._on_body_clicked_for_geometry_check(body_id)
            return

        # Prüfe auf Mesh Repair Pending Mode
        if getattr(self, '_pending_mesh_repair_mode', False):
            self._on_body_clicked_for_mesh_repair(body_id)
            return

        # Prüfe auf Surface Analysis Pending Mode
        if getattr(self, '_pending_surface_analysis_mode', False):
            self._on_body_clicked_for_surface_analysis(body_id)
            return

        # Prüfe auf Wall Thickness Pending Mode
        if getattr(self, '_pending_wall_thickness_mode', False):
            self._on_body_clicked_for_wall_thickness(body_id)
            return

        # Prüfe auf TNP Body-Pick Mode
        if getattr(self, '_pending_tnp_pick_mode', False):
            self._on_body_clicked_for_tnp(body_id)
            return

        # Nur reagieren wenn wir auf Body-Selektion warten (Transform)
        if not self._pending_transform_mode:
            return

        # Body in der Document-Liste finden
        body = None
        for b in self.document.bodies:
            if b.id == body_id:
                body = b
                break

        if not body:
            logger.warning(f"Body {body_id} nicht gefunden")
            return

        mode = self._pending_transform_mode
        self._pending_transform_mode = None
        self.viewport_3d.setCursor(Qt.ArrowCursor)

        # Deaktiviere Body-Highlighting im Viewport
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        # Spezial-Fall: Point-to-Point Move
        if mode == "point_to_point":
            if hasattr(self.viewport_3d, 'start_point_to_point_mode'):
                self.viewport_3d.start_point_to_point_mode(body.id)
                logger.success(f"Point-to-Point Move für {body.name}: Wähle Start-Punkt, dann Ziel-Punkt")
                if hasattr(self, "p2p_panel"):
                    self._p2p_body_id = body.id
                    self.p2p_panel.reset()
                    self.p2p_panel.set_body(body.name)
                    self.p2p_panel.set_status(tr("Pick start point"))
                    self.p2p_panel.show_at(self.viewport_3d)
                self._p2p_repick_body = False
            return

        # Normaler Transform-Modus (Move/Rotate/Scale)
        self._transform_mode = mode
        self._active_transform_body = body

        # Transform-UI zeigen
        self._show_transform_ui(body.id, body.name, mode)

        logger.success(f"{mode.capitalize()}: {body.name} - Ziehe am Gizmo oder Tab für Eingabe")

    def _on_point_to_point_move(self, body_id: str, start_point: tuple, end_point: tuple):
        """
        Handler für Point-to-Point Move (CAD-Style)

        WICHTIG: Nutzt das normale Transform-Command-System für Undo/Redo Support
        und korrekte Mesh-Updates!
        """
        # Body finden
        body = None
        for b in self.document.bodies:
            if b.id == body_id:
                body = b
                break

        if not body:
            logger.error("Body nicht gefunden für Point-to-Point Move")
            return

        try:
            # Berechne Verschiebungs-Vektor
            dx = end_point[0] - start_point[0]
            dy = end_point[1] - start_point[1]
            dz = end_point[2] - start_point[2]

            logger.info(f"🎯 Point-to-Point Move: {start_point} → {end_point}")
            logger.info(f"   Verschiebung: dx={dx:.2f}, dy={dy:.2f}, dz={dz:.2f}")

            # WICHTIG: Nutze das normale Transform-Command-System!
            # Das stellt sicher, dass die Transform korrekt angewendet wird (inkl. Undo/Redo)
            translation_data = [dx, dy, dz]

            # Rufe den normalen Transform-Handler auf (der TransformCommand nutzt)
            self._on_body_transform_requested(body_id, "move", translation_data)

            logger.success(f"✅ Point-to-Point Move auf {body.name} durchgeführt")

            if hasattr(self, "p2p_panel"):
                self.p2p_panel.set_target_point(end_point)
                self.p2p_panel.set_status(tr("Done"))
                self.p2p_panel.hide()
            if hasattr(self, "transform_toolbar"):
                self.transform_toolbar.clear_active()
            self._p2p_body_id = None

        except Exception as e:
            logger.error(f"❌ Point-to-Point Move fehlgeschlagen: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            self._p2p_repick_body = False

    def _on_point_to_point_start_picked(self, point: tuple):
        if hasattr(self, "p2p_panel"):
            self.p2p_panel.set_start_point(point)
            self.p2p_panel.set_status(tr("Pick target point"))

    def _on_point_to_point_cancelled(self):
        if self._p2p_repick_body:
            return
        if hasattr(self, "p2p_panel"):
            self.p2p_panel.hide()
        if hasattr(self, "transform_toolbar"):
            self.transform_toolbar.clear_active()
        self._p2p_body_id = None

    def _reset_point_to_point_move(self):
        if getattr(self, "_p2p_body_id", None):
            if hasattr(self.viewport_3d, "start_point_to_point_mode"):
                self.viewport_3d.start_point_to_point_mode(self._p2p_body_id)
            if hasattr(self, "p2p_panel"):
                self.p2p_panel.set_start_point(None)
                self.p2p_panel.set_target_point(None)
                self.p2p_panel.set_status(tr("Pick start point"))
                self.p2p_panel.show_at(self.viewport_3d)
        else:
            self._pending_transform_mode = "point_to_point"
            self.viewport_3d.setCursor(Qt.CrossCursor)
            if hasattr(self.viewport_3d, "set_pending_transform_mode"):
                self.viewport_3d.set_pending_transform_mode(True)
            if hasattr(self, "p2p_panel"):
                self.p2p_panel.reset()
                self.p2p_panel.set_status(tr("Pick body"))
                self.p2p_panel.show_at(self.viewport_3d)

    def _cancel_point_to_point_move(self):
        self._pending_transform_mode = None
        if hasattr(self.viewport_3d, "set_pending_transform_mode"):
            self.viewport_3d.set_pending_transform_mode(False)
        if hasattr(self.viewport_3d, "cancel_point_to_point_mode"):
            self.viewport_3d.cancel_point_to_point_mode()
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self, "p2p_panel"):
            self.p2p_panel.hide()
        if hasattr(self, "transform_toolbar"):
            self.transform_toolbar.clear_active()
        self._p2p_body_id = None
        self._p2p_repick_body = False

    def _on_p2p_pick_body_requested(self):
        """Allow re-picking the body for point-to-point move."""
        self._p2p_repick_body = True
        self._p2p_body_id = None
        if hasattr(self.viewport_3d, "cancel_point_to_point_mode"):
            self.viewport_3d.cancel_point_to_point_mode()
        self._pending_transform_mode = "point_to_point"
        self.viewport_3d.setCursor(Qt.CrossCursor)
        if hasattr(self.viewport_3d, "set_pending_transform_mode"):
            self.viewport_3d.set_pending_transform_mode(True)
        if hasattr(self, "p2p_panel"):
            self.p2p_panel.reset()
            self.p2p_panel.set_status(tr("Pick body"))
            self.p2p_panel.show_at(self.viewport_3d)

    def _on_transform_val_change(self, x, y, z):
        """Live Update vom Panel -> Viewport Actor"""
        if self._transform_mode:
            self.viewport_3d.apply_transform_values(x, y, z, self._transform_mode)
            
    def _on_viewport_transform_update(self, x, y, z):
        """Live Update vom Viewport Gizmo -> Panel Input Felder"""
        # Werte an das Panel senden, damit die Zahlen sich drehen
        if hasattr(self, 'transform_panel'):
            self.transform_panel.update_values(x, y, z)
        
    def _on_transform_confirmed(self):
        """Finalisieren der Transformation"""
        if not self._active_transform_body: return
        
        # Werte aus dem Panel sind die "Wahrheit"
        vals = self.transform_panel.get_values()
        dx, dy, dz = vals
        
        body = self._active_transform_body
        
        if HAS_BUILD123D and getattr(body, '_build123d_solid', None):
            from build123d import Location, Axis
            
            try:
                if self._transform_mode == "move":
                    # Translation
                    body._build123d_solid = body._build123d_solid.move(Location((dx, dy, dz)))
                    
                elif self._transform_mode == "scale":
                    # Uniform Scale (Panel hat x=y=z bei scale, meistens)
                    # Wir nehmen X als Faktor
                    factor = dx
                    if factor > 0:
                        body._build123d_solid = body._build123d_solid.scale(factor)
                        
                elif self._transform_mode == "rotate":
                    # Euler Rotation (sequentiell)
                    # Build123d rotiert um Achsen
                    solid = body._build123d_solid
                    if dx != 0: solid = solid.rotate(Axis.X, dx)
                    if dy != 0: solid = solid.rotate(Axis.Y, dy)
                    if dz != 0: solid = solid.rotate(Axis.Z, dz)
                    body._build123d_solid = solid
                    
                # Mesh aktualisieren
                self._update_body_from_build123d(body, body._build123d_solid)
                logger.success(f"Transform {self._transform_mode} applied via Build123d")

            except Exception as e:
                logger.exception(f"Transform Error: {e}")

        else:
            # Fallback Mesh-Only (wenn kein Build123d Objekt da ist)
            mesh = self.viewport_3d.get_body_mesh(body.id)
            if mesh:
                if self._transform_mode == "move":
                    mesh.translate((dx, dy, dz), inplace=True)
                elif self._transform_mode == "scale":
                    mesh.scale(dx, inplace=True) # Uniform scale logic needed usually
                elif self._transform_mode == "rotate":
                    mesh.rotate_x(dx, inplace=True)
                    mesh.rotate_y(dy, inplace=True)
                    mesh.rotate_z(dz, inplace=True)
                self._update_body_mesh(body, mesh)

        # Reset panel values but keep gizmo and panel visible for further transforms
        self.transform_panel.reset_values()
        # Refresh gizmo position to new body position
        self.viewport_3d.update_transform_gizmo_position()
        self.browser.refresh()

    def _on_transform_cancelled(self):
        self.transform_panel.hide()
        self.viewport_3d.end_transform()
        # Viewport Refresh um visuelle Gizmo-Vorschau zurückzusetzen falls Cancel
        self._update_viewport_all()
        self._active_transform_body = None
        self._transform_mode = None
        
    def _on_body_transform_requested(self, body_ids, mode: str, data):
        """
        Handler für das neue Gizmo-basierte Transform-System.
        Erstellt TransformFeature statt direkter Mutation (Feature-History).

        Args:
            body_ids: str (single body) oder List[str] (multi-select)
            mode: "move", "rotate", "scale", "mirror"
            data: Transform-Daten (Liste oder Dict)
        """
        pass
        pass
        pass
        pass

        # Normalisiere zu Liste
        if isinstance(body_ids, str):
            body_ids = [body_ids]

        logger.info(f"   Normalized to {len(body_ids)} bodies")

        from modeling import TransformFeature
        from modeling.cad_tessellator import CADTessellator

        # Performance Optimization 1.2: Cache-Clearing verschoben zu TransformCommand.redo()
        # (per-shape invalidation statt global)
        try:
            # Normalisiere data-Format
            transform_data = self._normalize_transform_data(mode, data)

            # Wende Transform auf alle selektierten Bodies an
            success_count = 0
            for body_id in body_ids:
                body = next((b for b in self.document.bodies if b.id == body_id), None)
                if not body:
                    logger.warning(f"Body {body_id} nicht gefunden für Transform")
                    continue

                if not HAS_BUILD123D or not getattr(body, '_build123d_solid', None):
                    logger.warning(f"Build123d nicht verfügbar für Body {body_id}")
                    continue

                # Berechne Body-Zentrum für Rotate/Scale
                body_transform_data = transform_data.copy()
                if mode in ["rotate", "scale"]:
                    bounds = body._build123d_solid.bounding_box()
                    center = [
                        (bounds.min.X + bounds.max.X) / 2,
                        (bounds.min.Y + bounds.max.Y) / 2,
                        (bounds.min.Z + bounds.max.Z) / 2
                    ]
                    body_transform_data["center"] = center

                # Erstelle TransformFeature
                feature = TransformFeature(
                    mode=mode,
                    data=body_transform_data,
                    name=f"Transform: {mode.capitalize()}"
                )

                # NEU: Push to Undo Stack (calls redo() automatically)
                # Cache wird in TransformCommand.redo() invalidiert (per-shape)
                from gui.commands.transform_command import TransformCommand
                cmd = TransformCommand(body, feature, self)
                self.undo_stack.push(cmd)
                success_count += 1

            # Gizmo an neuer Position anzeigen (nur bei Single-Select)
            if len(body_ids) == 1:
                gizmo_was_active = hasattr(self.viewport_3d, 'is_transform_active') and self.viewport_3d.is_transform_active()
                if gizmo_was_active and hasattr(self.viewport_3d, 'show_transform_gizmo'):
                    self.viewport_3d.show_transform_gizmo(body_ids[0], force_refresh=False)

            # UI aufräumen
            if hasattr(self, 'transform_panel'):
                self.transform_panel.hide()

            if success_count > 0:
                logger.success(f"Transform-Feature auf {success_count} Bodies angewendet (Undo: Ctrl+Z)")
            else:
                logger.warning("Keine Bodies transformiert")

        except Exception as e:
            logger.exception(f"Transform Error: {e}")

    def _normalize_transform_data(self, mode: str, data) -> dict:
        """
        Normalisiert Transform-Daten in einheitliches Dict-Format.

        Args:
            mode: "move", "rotate", "scale", "mirror"
            data: Liste oder Dict mit Transform-Parametern

        Returns:
            Dict mit standardisierten Keys
        """
        if mode == "move":
            if isinstance(data, list):
                return {"translation": data}
            else:
                return {"translation": data.get("translation", [0, 0, 0])}

        elif mode == "rotate":
            if isinstance(data, dict):
                return {
                    "axis": data.get("axis", "Z"),
                    "angle": data.get("angle", 0)
                }
            else:
                # Legacy: [rx, ry, rz] - nehme nur erste Achse
                angles = data if isinstance(data, (list, tuple)) else [0, 0, 0]
                if angles[0] != 0:
                    return {"axis": "X", "angle": angles[0]}
                elif angles[1] != 0:
                    return {"axis": "Y", "angle": angles[1]}
                else:
                    return {"axis": "Z", "angle": angles[2]}

        elif mode == "scale":
            # FIX Bug 1.4: Prüfe "factor" ZUERST, dann "scale"
            if isinstance(data, dict):
                # Panel sendet {"factor": 0.5}, Gizmo sendet auch {"factor": ...}
                if "factor" in data:
                    factor = data["factor"]
                elif "scale" in data:
                    scale = data["scale"]
                    factor = scale[0] if isinstance(scale, list) else scale
                else:
                    factor = 1.0
            else:
                factor = float(data) if data else 1.0
            return {"factor": factor}

        elif mode == "mirror":
            if isinstance(data, dict):
                return {"plane": data.get("plane", "XY")}
            else:
                return {"plane": "XY"}

        return {}

    def _on_body_copy_requested(self, body_id: str, mode: str, data):
        """
        Handler für Copy+Transform (Shift+Drag).
        Kopiert den Body und wendet dann den Transform an.
        """
        pass
        pass
        logger.info(f"   mode: {mode}")
        logger.info(f"   data: {data}")
        
        # Original Body finden
        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.error(f"Body {body_id} nicht gefunden für Copy")
            return
            
        if not HAS_BUILD123D or not getattr(body, '_build123d_solid', None):
            logger.error("Build123d nicht verfügbar für Copy")
            return
            
        from build123d import Location, Axis, copy as b123d_copy
        from modeling.cad_tessellator import CADTessellator
        from modeling import Body
        
        try:
            # 1. Neuen Body erstellen
            new_body = Body(name=f"{body.name}_copy", document=self.document)
            
            # 2. Solid kopieren (Build123d hat keine .copy() - wir müssen neu konstruieren)
            # Workaround: Kopiere durch Location-Identity-Transform
            from build123d import Location
            new_body._build123d_solid = body._build123d_solid.moved(Location((0, 0, 0)))
            
            # 3. Cache leeren
            CADTessellator.notify_body_changed()
            
            # 4. Transform anwenden auf die Kopie
            if mode == "move":
                if isinstance(data, list):
                    dx, dy, dz = data
                else:
                    dx, dy, dz = data.get("translation", [0, 0, 0])
                new_body._build123d_solid = new_body._build123d_solid.move(Location((dx, dy, dz)))
                logger.success(f"Copy+Move ({dx:.2f}, {dy:.2f}, {dz:.2f}) → {new_body.name}")
                
            elif mode == "rotate":
                if isinstance(data, dict):
                    axis_name = data.get("axis", "Z")
                    angle = data.get("angle", 0)
                else:
                    axis_name, angle = "Z", 0
                    
                axis_map = {"X": Axis.X, "Y": Axis.Y, "Z": Axis.Z}
                axis = axis_map.get(axis_name, Axis.Z)
                new_body._build123d_solid = new_body._build123d_solid.rotate(axis, angle)
                logger.success(f"Copy+Rotate ({axis_name}, {angle:.1f}°) → {new_body.name}")
                
            elif mode == "scale":
                if isinstance(data, dict):
                    factor = data.get("factor", 1.0)
                else:
                    factor = 1.0
                new_body._build123d_solid = new_body._build123d_solid.scale(factor)
                logger.success(f"Copy+Scale ({factor:.2f}) → {new_body.name}")
            
            # 5. Mesh generieren
            self._update_body_from_build123d(new_body, new_body._build123d_solid)
            
            # 6. Zum Document hinzufügen
            self.document.add_body(new_body, set_active=False)
            
            # 7. UI aktualisieren
            self.browser.refresh()
            
            # 8. Neuen Body selektieren
            if hasattr(self.viewport_3d, 'show_transform_gizmo'):
                self.viewport_3d.show_transform_gizmo(new_body.id)
                
        except Exception as e:
            logger.exception(f"Copy+Transform Error: {e}")
            
    def _on_body_mirror_requested(self, body_id: str, plane: str):
        """
        Handler für Mirror-Operation.
        Spiegelt den Body an der angegebenen Ebene.
        """
        logger.debug(f"Mirror requested: {plane} auf {body_id}")
        
        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.error(f"Body {body_id} nicht gefunden für Mirror")
            return
            
        if not HAS_BUILD123D or not getattr(body, '_build123d_solid', None):
            logger.error("Build123d nicht verfügbar für Mirror")
            return
            
        from build123d import Plane as B123Plane, mirror as b123d_mirror
        from modeling.cad_tessellator import CADTessellator
        
        try:
            CADTessellator.notify_body_changed()
            
            # Ebene bestimmen
            plane_map = {
                "XY": B123Plane.XY,
                "XZ": B123Plane.XZ,
                "YZ": B123Plane.YZ,
            }
            mirror_plane = plane_map.get(plane.upper(), B123Plane.XY)
            
            # Mirror anwenden
            body._build123d_solid = b123d_mirror(body._build123d_solid, about=mirror_plane)
            
            logger.success(f"Mirror ({plane}) auf {body.name}")
            
            # Mesh aktualisieren
            self._update_body_from_build123d(body, body._build123d_solid)
            
            # UI aktualisieren
            if hasattr(self.viewport_3d, 'show_transform_gizmo'):
                self.viewport_3d.show_transform_gizmo(body_id)
            self.browser.refresh()
            
        except Exception as e:
            logger.exception(f"Mirror Error: {e}")
            
    def _show_mirror_dialog(self, body_id: str):
        """Zeigt Dialog zur Auswahl der Mirror-Ebene"""
        from PySide6.QtWidgets import QMessageBox, QPushButton
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Mirror")
        msg.setText("Spiegelebene wählen:")
        msg.setIcon(QMessageBox.Question)
        
        btn_xy = msg.addButton("XY (Horizontal)", QMessageBox.ActionRole)
        btn_xz = msg.addButton("XZ (Frontal)", QMessageBox.ActionRole)
        btn_yz = msg.addButton("YZ (Seitlich)", QMessageBox.ActionRole)
        msg.addButton(QMessageBox.Cancel)
        
        msg.exec()
        
        clicked = msg.clickedButton()
        if clicked == btn_xy:
            self._on_body_mirror_requested(body_id, "XY")
        elif clicked == btn_xz:
            self._on_body_mirror_requested(body_id, "XZ")
        elif clicked == btn_yz:
            self._on_body_mirror_requested(body_id, "YZ")

    def _on_body_opacity_changed(self, body_id: str, opacity: float):
        """
        Handler für Transparenz-Änderungen aus dem BodyPropertiesPanel.

        Args:
            body_id: ID des Bodies
            opacity: Transparenz (0.0 = unsichtbar, 1.0 = undurchsichtig)
        """
        # Im Viewport anwenden
        self.viewport_3d.set_body_opacity(body_id, opacity)

        # Im Body-Model speichern für Persistenz
        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if body:
            body.display_opacity = opacity
            logger.debug(f"Body '{body.name}' Transparenz: {int(opacity * 100)}%")

    def _update_viewport_all(self):
        """Aktualisiert ALLES im Viewport"""
        # Sketches
        self.viewport_3d.set_sketches(self.browser.get_visible_sketches())
        
        # Bodies - komplett neu laden um gelöschte zu entfernen
        self.viewport_3d.clear_bodies()
        colors = [(0.6,0.6,0.8), (0.8,0.6,0.6), (0.6,0.8,0.6)]
        for i, body_info in enumerate(self.browser.get_visible_bodies()):
            # Assembly-System: 3-Tupel (body, visible, is_inactive_component)
            if len(body_info) == 3:
                b, visible, is_inactive = body_info
            else:
                b, visible = body_info
                is_inactive = False

            if visible and hasattr(b, '_mesh_vertices'):
                self.viewport_3d.add_body(
                    bid=b.id,
                    name=b.name,
                    verts=b._mesh_vertices,
                    faces=b._mesh_triangles,
                    color=colors[i % 3],
                    inactive_component=is_inactive
                )

    def _set_mode(self, mode):
        prev_mode = getattr(self, "mode", None)
        if prev_mode != mode:
            self._clear_transient_previews(
                reason=f"mode:{prev_mode}->{mode}",
                clear_interaction_modes=True,
            )
        self.mode = mode
        if mode == "3d":
            # 3D-Modus
            self.tool_stack.setCurrentIndex(0)  # 3D-ToolPanel
            self.center_stack.setCurrentIndex(0)  # Viewport
            self.right_stack.setVisible(False)
            if hasattr(self, 'transform_toolbar'):
                self.transform_toolbar.setVisible(True)
            # Update UI
            if hasattr(self, 'mashcad_status_bar'):
                self.mashcad_status_bar.set_mode("3D")
        else:
            # Sketch-Modus
            self.tool_stack.setCurrentIndex(1)  # 2D-ToolPanel
            self.center_stack.setCurrentIndex(1)  # Sketch Editor
            self.right_stack.setCurrentIndex(1)  # 2D Properties
            self.right_stack.setVisible(True)
            if hasattr(self, 'transform_toolbar'):
                self.transform_toolbar.setVisible(False)
            self.sketch_editor.setFocus()
            # Update UI
            if hasattr(self, 'mashcad_status_bar'):
                self.mashcad_status_bar.set_mode("2D")

    def _new_sketch(self):
        self.viewport_3d.set_plane_select_mode(True)
        logger.info(tr("Wähle Ebene: 1=XY, 2=XZ, 3=YZ oder Klick auf Fläche"))
        self.setFocus()

    def _start_offset_plane(self):
        """Startet den interaktiven Offset-Plane-Workflow (Fusion-Style)."""
        self._offset_plane_pending = True
        self.viewport_3d.set_plane_select_mode(True)
        self.statusBar().showMessage(tr("Wähle Basisebene: Klick auf Standardebene oder Körperfläche"))
        logger.info("Offset Plane: Wähle Basisebene...")

    def _start_offset_plane_drag(self, origin, normal):
        """Phase 2: Offset einstellen nach Basis-Auswahl."""
        import numpy as np
        self._offset_plane_pending = False
        self.viewport_3d.set_plane_select_mode(False)
        self.viewport_3d.set_offset_plane_mode(True)
        self.viewport_3d.set_offset_plane_base(
            np.array(origin, dtype=float),
            np.array(normal, dtype=float)
        )
        self.offset_plane_panel.reset()
        self.offset_plane_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage(tr("Offset einstellen: Mausdrag oder Zahleneingabe, Enter = bestätigen"))

    def _on_offset_plane_value_changed(self, offset):
        """Panel-Wert geändert → Preview aktualisieren."""
        if self.viewport_3d.offset_plane_mode:
            self.viewport_3d.update_offset_plane_preview(offset)

    def _on_offset_plane_drag(self, offset):
        """Viewport-Drag → Panel-Wert synchronisieren."""
        self.offset_plane_panel.set_offset(offset)

    def _on_offset_plane_confirmed(self):
        """Offset Plane bestätigen und erstellen."""
        from modeling import ConstructionPlane
        offset = self.offset_plane_panel.get_offset()
        name = self.offset_plane_panel.get_name()
        origin = self.viewport_3d._offset_plane_base_origin
        normal = self.viewport_3d._offset_plane_base_normal

        if origin is None or normal is None:
            logger.error("Keine Basis für Offset Plane gesetzt")
            self._on_offset_plane_cancelled()
            return

        plane = ConstructionPlane.from_face(
            tuple(origin), tuple(normal), offset, name
        )
        self.document.planes.append(plane)

        self.viewport_3d.set_offset_plane_mode(False)
        self.offset_plane_panel.hide()
        self.browser.refresh()
        self._render_construction_planes()
        self.statusBar().showMessage(f"Plane '{plane.name}' erstellt")
        logger.success(f"Offset Plane erstellt: {plane.name}")

    def _on_offset_plane_cancelled(self):
        """Offset Plane abbrechen."""
        self._offset_plane_pending = False
        self.viewport_3d.set_offset_plane_mode(False)
        self.viewport_3d.set_plane_select_mode(False)
        self.offset_plane_panel.hide()
        self.statusBar().showMessage(tr("Versatzebene abgebrochen"))

    def _render_construction_planes(self):
        """Rendert alle Konstruktionsebenen im Viewport."""
        if hasattr(self, 'viewport_3d') and hasattr(self.document, 'planes'):
            self.viewport_3d.render_construction_planes(self.document.planes)

    def _on_construction_plane_vis_changed(self, plane_id, visible):
        """Browser hat Plane-Sichtbarkeit geändert."""
        if hasattr(self, 'viewport_3d'):
            self.viewport_3d.set_construction_plane_visibility(plane_id, visible)
            self._render_construction_planes()

    def _on_construction_plane_selected(self, cp):
        """Create sketch on a construction plane when clicked in browser."""
        self._create_sketch_at(cp.origin, cp.normal, x_dir_override=cp.x_dir)

    def _on_browser_plane_selected(self, plane):
        """Wird aufgerufen wenn eine Ebene im Browser angeklickt wird"""
        self._on_plane_selected(plane)
    
    def _on_plane_selected(self, plane):
        # DEFINITION: (Origin, Normal, X_Direction)
        plane_defs = {
            'xy': ((0,0,0), (0,0,1), (1,0,0)),
            'xz': ((0,0,0), (0,1,0), (1,0,0)),
            'yz': ((0,0,0), (1,0,0), (0,1,0))
        }
        default = ((0,0,0), (0,0,1), (1,0,0))
        origin, normal, x_dir = plane_defs.get(plane, default)

        # Offset Plane Workflow: Phase 2 starten
        if self._offset_plane_pending:
            self._start_offset_plane_drag(origin, normal)
            return

        self.viewport_3d.set_plane_select_mode(False)
        self._create_sketch_at(origin, normal, x_dir_override=x_dir)

    def _on_custom_plane_selected(self, origin, normal):
        # Offset Plane Workflow: Face-Pick → Phase 2 starten
        if self._offset_plane_pending:
            self._start_offset_plane_drag(origin, normal)
            return

        self.viewport_3d.set_plane_select_mode(False)
        x_dir = getattr(self.viewport_3d, '_last_picked_x_dir', None)
        self._create_sketch_at(origin, normal, x_dir)

    def _create_sketch_at(self, origin, normal, x_dir_override=None):
        s = self.document.new_sketch(f"Sketch{len(self.document.sketches)+1}")

        # Berechne Achsen
        if x_dir_override:
            # PERFEKT: Wir haben eine stabile Achse vom Detector
            x_dir = x_dir_override
            # Y berechnen (Kreuzprodukt)
            import numpy as np
            n_vec = np.array(normal)
            x_vec = np.array(x_dir)
            y_vec = np.cross(n_vec, x_vec)
            y_dir = tuple(y_vec)
        else:
            # Fallback: Raten (das was bisher Probleme machte)
            x_dir, y_dir = self._calculate_plane_axes(normal)

        # Speichere ALLES im Sketch
        s.plane_origin = origin
        s.plane_normal = normal
        s.plane_x_dir = x_dir  # <--- Das ist der Schlüssel zum Erfolg
        s.plane_y_dir = y_dir

        # ✅ FIX: Speichere Parent-Body für korrektes Targeting
        if hasattr(self.viewport_3d, '_last_picked_body_id') and self.viewport_3d._last_picked_body_id:
            s.parent_body_id = self.viewport_3d._last_picked_body_id
            logger.info(f"✅ Sketch erstellt auf Body: {s.parent_body_id}")
            # Reset after use
            self.viewport_3d._last_picked_body_id = None
        
        self.active_sketch = s
        self.sketch_editor.sketch = s
        
        # Bodies als Referenz übergeben (für Snapping auf Kanten)
        self._set_sketch_body_references(origin, normal)
        
        self._set_mode("sketch")
        self.browser.refresh()
    
    def _set_sketch_body_references(self, origin, normal, x_dir_override=None):
        """
        Sammelt Body-Daten und übergibt sie an den SketchEditor.
        FIX: Nutzt set_reference_bodies statt set_background_geometry.
        """
        bodies_data = []
        
        # Alle sichtbaren Körper durchgehen
        for bid, body in self.viewport_3d.bodies.items():
            if not self.viewport_3d.is_body_visible(bid): continue
            
            # Mesh holen (PyVista PolyData)
            mesh = self.viewport_3d.get_body_mesh(bid)
            
            if mesh is not None:
                # Farbe holen (oder Default)
                color = body.get('color', (0.6, 0.6, 0.8))
                
                bodies_data.append({
                    'mesh': mesh,
                    'color': color
                })
        
        # WICHTIG: Achsen berechnen, falls nicht übergeben
        if x_dir_override is None:
            x_dir_override, _ = self._calculate_plane_axes(normal)

        # Übergebe an SketchEditor (mit der korrekten Methode!)
        if hasattr(self.sketch_editor, 'set_reference_bodies'):
            self.sketch_editor.set_reference_bodies(
                bodies_data,
                normal,
                origin,
                plane_x=x_dir_override  # Das verhindert die Rotation!
            )

            # Automatische Ansicht-Ausrichtung basierend auf 3D-Kamera
            self._auto_align_sketch_view(normal, x_dir_override)

    def _on_sketch_changed_refresh_viewport(self):
        """
        Aktualisiert Sketch-Wireframes im 3D-Viewport nach Sketch-Änderungen.
        KRITISCH: Triggert auch Rebuild von Bodies die von diesem Sketch abhängen!
        """
        self.viewport_3d.set_sketches(self.browser.get_visible_sketches())

        # Parametric CAD: Update bodies that depend on this sketch (DEBOUNCED)
        if self.mode == "sketch" and hasattr(self.sketch_editor, 'sketch'):
            self._schedule_parametric_rebuild()

    def _schedule_parametric_rebuild(self):
        """
        Debounced Rebuild für parametrische Updates.
        Wartet 300ms nach der letzten Sketch-Änderung bevor Rebuild getriggert wird.
        """
        if not hasattr(self, '_parametric_rebuild_timer'):
            from PySide6.QtCore import QTimer
            self._parametric_rebuild_timer = QTimer()
            self._parametric_rebuild_timer.setSingleShot(True)
            self._parametric_rebuild_timer.timeout.connect(self._do_parametric_rebuild)

        # Timer neu starten (Debounce)
        self._parametric_rebuild_timer.stop()
        self._parametric_rebuild_timer.start(300)  # 300ms Debounce

    def _do_parametric_rebuild(self):
        """Führt den tatsächlichen parametrischen Rebuild aus."""
        if self.mode == "sketch" and hasattr(self.sketch_editor, 'sketch'):
            self._update_bodies_depending_on_sketch(self.sketch_editor.sketch)

    def _compute_profile_hash(self, feature, sketch) -> str:
        """
        Berechnet einen Hash der für ein Feature relevanten Profile.
        
        Dieser Hash basiert auf:
        - Den Centroids der vom feature.profile_selector referenzierten Profile
        - Den Geometrie-Daten (exterior coords) dieser Profile
        
        WICHTIG: Die Profile werden nach Centroid sortiert, damit die Reihenfolge
        stabil ist und nicht von der internen Sortierung des Sketch-Solvers abhängt.
        
        Args:
            feature: Das Feature (ExtrudeFeature oder RevolveFeature)
            sketch: Der Sketch mit den closed_profiles
            
        Returns:
            Ein Hash-String der relevanten Profile. Leerer String wenn keine Profile gefunden.
        """
        import hashlib
        
        profile_selector = getattr(feature, 'profile_selector', [])
        sketch_profiles = getattr(sketch, 'closed_profiles', [])
        
        if not profile_selector or not sketch_profiles:
            return ""
        
        # Finde die Profile, die zum Selektor passen (ähnlich wie _filter_profiles_by_selector)
        matched_profiles = []
        used_indices = set()
        tolerance = 5.0
        
        for sel_cx, sel_cy in profile_selector:
            best_match_idx = None
            best_match_dist = float('inf')
            
            for i, poly in enumerate(sketch_profiles):
                if i in used_indices:
                    continue
                try:
                    centroid = poly.centroid
                    dist = ((centroid.x - sel_cx) ** 2 + (centroid.y - sel_cy) ** 2) ** 0.5
                    if dist < tolerance and dist < best_match_dist:
                        best_match_dist = dist
                        best_match_idx = i
                except Exception as e:
                    logger.debug(f"[main_window] Profil-Matching Fehler: {e}")
                    continue
            
            if best_match_idx is not None:
                used_indices.add(best_match_idx)
                matched_profiles.append(sketch_profiles[best_match_idx])
        
        if not matched_profiles:
            return ""
        
        # WICHTIG: Sortiere Profile nach Centroid für stabile Reihenfolge
        # Die interne Sortierung des Sketch-Solvers kann sich ändern!
        def profile_sort_key(poly):
            try:
                c = poly.centroid
                return (round(c.x, 6), round(c.y, 6))
            except Exception as e:
                logger.debug(f"[main_window] Fehler beim Profil-Sortieren: {e}")
                return (0.0, 0.0)
        
        matched_profiles = sorted(matched_profiles, key=profile_sort_key)
        
        # Erstelle einen Hash basierend auf den Geometrie-Daten der gematchten Profile
        hasher = hashlib.md5()
        for poly in matched_profiles:
            # Centroid
            c = poly.centroid
            hasher.update(f"centroid:{c.x:.6f},{c.y:.6f};".encode())
            # Area
            hasher.update(f"area:{poly.area:.6f};".encode())
            # Exterior coords (vereinfacht)
            coords = list(poly.exterior.coords)
            for coord in coords[:10]:  # Max 10 Punkte pro Profil (Performance)
                hasher.update(f"{coord[0]:.4f},{coord[1]:.4f};".encode())
        
        return hasher.hexdigest()
    
    def _update_bodies_depending_on_sketch(self, sketch):
        """
        CAD Kernel First: Findet alle Bodies mit Features die von diesem Sketch
        abhängen und triggert Rebuild.
        
        OPTIMIERT: Prüft ob sich die tatsächlich verwendeten Profile geändert haben.
        Wenn nur neue Profile hinzugefügt wurden (ohne die verwendeten zu ändern),
        wird kein Rebuild durchgeführt.

        WICHTIG: Keine precalculated_polys Updates mehr!
        Profile werden beim Rebuild direkt aus dem Sketch abgeleitet.

        Args:
            sketch: Der geänderte Sketch
        """
        if not sketch:
            return

        from modeling import ExtrudeFeature, RevolveFeature

        sketch_id = getattr(sketch, 'id', None)
        bodies_to_rebuild = []
        skipped_bodies = []

        for body in self.document.bodies:
            needs_rebuild = False
            body_uses_sketch = False
            
            for feature in body.features:
                # ExtrudeFeature oder RevolveFeature mit diesem Sketch?
                if isinstance(feature, (ExtrudeFeature, RevolveFeature)):
                    # Vergleiche sowohl per Objekt-Identität ALS AUCH per ID (für geladene Projekte)
                    feature_sketch = feature.sketch
                    is_same_sketch = (
                        feature_sketch is sketch or
                        (feature_sketch and sketch_id and getattr(feature_sketch, 'id', None) == sketch_id)
                    )

                    if is_same_sketch:
                        body_uses_sketch = True
                        # OPTIMIERUNG: Prüfe ob sich die verwendeten Profile wirklich geändert haben
                        current_hash = self._compute_profile_hash(feature, sketch)
                        stored_hash = getattr(feature, '_profile_hash', None)
                        
                        if current_hash != stored_hash:
                            # Profile haben sich geändert oder Hash wurde noch nie gesetzt
                            feature._profile_hash = current_hash
                            needs_rebuild = True
                            # Nur loggen wenn sich wirklich etwas geändert hat (nicht beim ersten Mal)
                            if stored_hash is not None:
                                logger.debug(f"[PARAMETRIC] Profile changed for '{body.name}'/{feature.name}")
                        # else: Profile unverändert - kein Logging (zu chatty)
            
            if needs_rebuild and body not in bodies_to_rebuild:
                bodies_to_rebuild.append(body)
            elif body_uses_sketch and not needs_rebuild:
                skipped_bodies.append(body.name)

        # Rebuild alle betroffenen Bodies
        # CAD KERNEL FIRST: Profile werden beim Rebuild aus dem Sketch abgeleitet!
        if bodies_to_rebuild:
            logger.info(f"[PARAMETRIC] Rebuilding {len(bodies_to_rebuild)} body/bodies, skipped {len(skipped_bodies)} (profiles unchanged)")

        for body in bodies_to_rebuild:
            try:
                from modeling.cad_tessellator import CADTessellator
                CADTessellator.notify_body_changed()
                body._rebuild()
                self._update_body_from_build123d(body, body._build123d_solid)
                logger.info(f"[PARAMETRIC] Rebuilt body '{body.name}' after sketch change")
            except Exception as e:
                logger.error(f"[PARAMETRIC] Rebuild failed for '{body.name}': {e}")

    def _on_solver_dof_updated(self, success: bool, message: str, dof: float):
        """
        Wird aufgerufen wenn der Sketcher-Solver fertig ist.
        Aktualisiert die DOF-Anzeige in der Statusleiste.
        """
        # DOF in Integer konvertieren (kommt als float vom Signal)
        dof_int = int(dof) if dof >= 0 else -1

        # StatusBar aktualisieren (nur im Sketch-Modus sichtbar)
        is_sketch_mode = self.mode == "sketch"
        self.mashcad_status_bar.set_dof(dof_int, visible=is_sketch_mode)

    def _finish_sketch(self):
        """Beendet den Sketch-Modus und räumt auf."""
        # Body-Referenzen im SketchEditor löschen (Ghost Bodies entfernen)
        if hasattr(self.sketch_editor, 'set_reference_bodies'):
            self.sketch_editor.set_reference_bodies([], (0,0,1), (0,0,0))

        # DOF-Anzeige ausblenden
        self.mashcad_status_bar.set_dof(0, visible=False)

        self.active_sketch = None
        self._set_mode("3d")
        
        # Browser Refresh triggert Visibility-Check
        self.browser.refresh()
        
        # WICHTIG: Explizit Update anstoßen für sauberen Statuswechsel
        self._trigger_viewport_update()

    def _rotate_sketch_view(self):
        """Rotiert die Sketch-Ansicht um 90°."""
        if hasattr(self.sketch_editor, 'rotate_view'):
            self.sketch_editor.rotate_view()

    def _on_peek_3d(self, show_3d: bool):
        """
        Temporär 3D-Viewport zeigen während Space gedrückt (Peek-Modus).
        Hilft zur Orientierung im Sketch.
        """
        if show_3d:
            # Zeige 3D-Viewport
            self._peek_3d_active = True
            self.center_stack.setCurrentIndex(0)
            self.statusBar().showMessage(tr("3D-Vorschau (Space loslassen für Sketch)"), 0)

            # grabKeyboard() auf MainWindow - fängt ALLE Key-Events ab (plattformübergreifend)
            self.grabKeyboard()
        else:
            # Zurück zum Sketch
            self._peek_3d_active = False
            self.releaseKeyboard()
            self.center_stack.setCurrentIndex(1)
            self.sketch_editor.setFocus()
            self.statusBar().clearMessage()

    def keyReleaseEvent(self, event):
        """Key-Release Handler für 3D-Peek (grabKeyboard leitet hierher)."""
        if getattr(self, '_peek_3d_active', False):
            if event.key() == Qt.Key_Space and not event.isAutoRepeat():
                self._on_peek_3d(False)
                return
        super().keyReleaseEvent(event)

    def eventFilter(self, obj, event):
        """Event-Filter für globale Shortcuts und Viewport-Resize."""
        from PySide6.QtCore import QEvent

        if obj is self.viewport_3d and event.type() == QEvent.Resize:
            self._position_transform_toolbar()

        # Backup für 3D-Peek Space-Release
        if getattr(self, '_peek_3d_active', False):
            if event.type() == QEvent.KeyRelease and event.key() == Qt.Key_Space:
                if not event.isAutoRepeat():
                    self._on_peek_3d(False)
                    return True

        return super().eventFilter(obj, event)

    def _auto_align_sketch_view(self, plane_normal, plane_x):
        """
        Richtet die Sketch-Ansicht automatisch an der 3D-Kamera aus.
        Nutzt die Screen-Projektion der Sketch-Achsen (wie die 3D-Achsen).
        """
        import numpy as np

        try:
            # Sketch-Ebenen-Achsen in 3D
            n = np.array(plane_normal, dtype=np.float64)
            n = n / np.linalg.norm(n)
            x_dir = np.array(plane_x, dtype=np.float64)
            x_dir = x_dir / np.linalg.norm(x_dir)
            y_dir = np.cross(n, x_dir)
            y_dir = y_dir / np.linalg.norm(y_dir)

            # VTK World-to-Display Projektion
            ren = self.viewport_3d.plotter.renderer

            def world_to_screen(pt):
                """Konvertiert 3D Welt-Koordinate zu 2D Screen-Koordinate."""
                ren.SetWorldPoint(pt[0], pt[1], pt[2], 1.0)
                ren.WorldToDisplay()
                d_pt = ren.GetDisplayPoint()
                return np.array([d_pt[0], d_pt[1]])

            origin_screen = world_to_screen([0, 0, 0])
            x_end_screen = world_to_screen(x_dir * 100)
            y_end_screen = world_to_screen(y_dir * 100)

            # Screen-Vektoren (Y nach oben = positive Richtung)
            # VTK view coords: (0,0) = unten links, Y wächst nach oben
            sx = np.array([x_end_screen[0] - origin_screen[0], x_end_screen[1] - origin_screen[1]])
            sy = np.array([y_end_screen[0] - origin_screen[0], y_end_screen[1] - origin_screen[1]])

            # Normalisiere
            sx_len = np.linalg.norm(sx)
            sy_len = np.linalg.norm(sy)
            if sx_len < 0.001 or sy_len < 0.001:
                logger.debug("[Auto-Align] Achsen zu kurz auf Screen")
                self.sketch_editor.view_rotation = 0
                return
            sx = sx / sx_len
            sy = sy / sy_len

            # Screen "oben" ist (0, 1)
            screen_up = np.array([0, 1])

            # Welche der 4 Rotationen bringt "oben im Sketch" ≈ "oben am Screen"?
            # Bei 0°: Sketch-Y ist oben → sy sollte ≈ screen_up sein
            # Bei 90°: -Sketch-X ist oben → -sx sollte ≈ screen_up sein
            # Bei 180°: -Sketch-Y ist oben → -sy sollte ≈ screen_up sein
            # Bei 270°: Sketch-X ist oben → sx sollte ≈ screen_up sein
            candidates = [
                (0, sy),       # 0°: Sketch-Y zeigt nach oben
                (90, -sx),     # 90°: -Sketch-X zeigt nach oben
                (180, -sy),    # 180°: -Sketch-Y zeigt nach oben
                (270, sx),     # 270°: Sketch-X zeigt nach oben
            ]

            best_rot = 0
            best_dot = -2
            for rot, up_vec in candidates:
                dot = np.dot(up_vec, screen_up)
                if dot > best_dot:
                    best_dot = dot
                    best_rot = rot

            self.sketch_editor.view_rotation = best_rot
            logger.debug(f"[Auto-Align] {best_rot}° (screen Y-dir, dot={best_dot:.2f})")

        except Exception as e:
            logger.debug(f"[Auto-Align] Konnte Ansicht nicht ausrichten: {e}")

    def _hole_dialog(self):
        """Startet interaktiven Hole-Workflow (Fusion-style).
        Kein Body muss vorher selektiert sein — einfach auf Face klicken.
        """
        has_bodies = any(b._build123d_solid for b in self.document.bodies if b._build123d_solid)
        if not has_bodies:
            self.statusBar().showMessage("Keine Bodies mit Geometrie vorhanden")
            logger.warning("Hole: Keine Bodies mit Geometrie.")
            return

        self._hide_transform_ui()
        self._hole_mode = True
        self._hole_target_body = None  # wird beim Face-Klick gesetzt
        self._hole_face_selector = None
        self._hole_face_shape_id = None
        self._hole_face_index = None
        self.viewport_3d.set_hole_mode(True)
        self.hole_panel.reset()
        self.hole_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage("Hole: Klicke auf eine Fläche eines Bodys")
        logger.info("Hole-Modus gestartet — Fläche auf Body klicken")

    def _on_hole_diameter_changed(self, value):
        """Live-Update der Hole-Preview bei Durchmesser-Änderung."""
        if not self._hole_mode:
            return
        pos = self.viewport_3d._hole_position
        normal = self.viewport_3d._hole_normal
        if pos and normal:
            depth = self.hole_panel.get_depth()
            self.viewport_3d.show_hole_preview(pos, normal, value, depth)

    def _on_hole_depth_changed(self, value):
        """Live-Update der Hole-Preview bei Tiefen-Änderung."""
        if not self._hole_mode:
            return
        pos = self.viewport_3d._hole_position
        normal = self.viewport_3d._hole_normal
        if pos and normal:
            diameter = self.hole_panel.get_diameter()
            self.viewport_3d.show_hole_preview(pos, normal, diameter, value)

    def _resolve_ocp_face_id_from_cell(self, body_id: str, cell_id: int):
        """Ermittelt OCP-Face-Index aus einem Mesh-Cell-Index."""
        try:
            body_data = getattr(self.viewport_3d, "bodies", {}).get(body_id, {})
            mesh = body_data.get("mesh") if isinstance(body_data, dict) else None
            if mesh is None or not hasattr(mesh, "cell_data") or "face_id" not in mesh.cell_data:
                return None
            face_ids = mesh.cell_data["face_id"]
            if 0 <= int(cell_id) < len(face_ids):
                return int(face_ids[int(cell_id)])
        except Exception as e:
            logger.debug(f"[main_window] OCP Face-ID Lookup fehlgeschlagen: {e}")
        return None

    def _resolve_solid_face_from_pick(
        self,
        body,
        body_id: str,
        *,
        cell_id: int = None,
        position=None,
        ocp_face_id: int = None,
        center_fallback_tol: float = 5.0,
    ):
        """
        Loest ein Build123d-Face aus Klickdaten auf.
        Reihenfolge: OCP face_id/index -> Distanz-Fallback ueber Face-Center.
        """
        if not body or not getattr(body, "_build123d_solid", None):
            return None, ocp_face_id

        if ocp_face_id is None and cell_id is not None:
            ocp_face_id = self._resolve_ocp_face_id_from_cell(body_id, cell_id)

        if ocp_face_id is not None:
            try:
                from modeling.topology_indexing import face_from_index

                resolved = face_from_index(body._build123d_solid, int(ocp_face_id))
                if resolved is not None:
                    return resolved, int(ocp_face_id)
            except Exception as e:
                logger.debug(f"[main_window] face_from_index fehlgeschlagen: {e}")

        if position is None:
            return None, ocp_face_id

        try:
            pos_arr = np.array(position, dtype=float)
            best_face = None
            best_face_index = None
            best_dist = float("inf")
            from modeling.topology_indexing import iter_faces_with_indices

            for face_idx, solid_face in iter_faces_with_indices(body._build123d_solid):
                try:
                    fc = solid_face.center()
                    solid_center = np.array([fc.X, fc.Y, fc.Z], dtype=float)
                    dist = np.linalg.norm(solid_center - pos_arr)
                    if dist < best_dist:
                        best_dist = dist
                        best_face = solid_face
                        best_face_index = int(face_idx)
                except Exception:
                    continue
            if best_face is not None and best_dist < center_fallback_tol:
                return best_face, best_face_index if best_face_index is not None else ocp_face_id
        except Exception as e:
            logger.debug(f"[main_window] Face-Center Fallback fehlgeschlagen: {e}")

        return None, ocp_face_id

    def _find_or_register_face_shape_id(
        self,
        body,
        face,
        *,
        local_index: int = 0,
        feature_id: str = None,
        force_feature_local: bool = False,
    ):
        """Sucht/registriert eine Face-ShapeID.

        `local_index` ist der Referenz-Slot im Feature (nicht der Topologieindex im Solid).
        """
        if not body or face is None or not body._document or not hasattr(body._document, "_shape_naming_service"):
            return None

        service = body._document._shape_naming_service
        source_feature_id = body.features[-1].id if getattr(body, "features", None) else body.id
        target_feature_id = feature_id or source_feature_id
        target_local_index = max(0, int(local_index))
        try:
            shape_id = service.find_shape_id_by_face(face, require_exact=True)
            if shape_id is not None:
                if not force_feature_local:
                    return shape_id
                same_slot = (
                    getattr(shape_id, "feature_id", None) == target_feature_id
                    and int(getattr(shape_id, "local_index", -1)) == target_local_index
                )
                if same_slot:
                    return shape_id
        except Exception as e:
            logger.debug(f"[main_window] ShapeID Lookup fehlgeschlagen: {e}")

        try:
            if not hasattr(face, "wrapped"):
                return None
            from modeling.tnp_system import ShapeType

            fc = face.center()
            area = float(face.area) if hasattr(face, "area") else 0.0
            return service.register_shape(
                ocp_shape=face.wrapped,
                shape_type=ShapeType.FACE,
                feature_id=target_feature_id,
                local_index=target_local_index,
                geometry_data=(fc.X, fc.Y, fc.Z, area),
            )
        except Exception as e:
            logger.debug(f"[main_window] ShapeID Registrierung fehlgeschlagen: {e}")
            return None

    def _on_hole_confirmed(self):
        """Hole bestätigt — Feature erstellen."""
        from modeling import HoleFeature
        from gui.commands.feature_commands import AddFeatureCommand

        pos = self.viewport_3d._hole_position
        normal = self.viewport_3d._hole_normal
        face_selector = getattr(self, '_hole_face_selector', None)
        face_index = getattr(self, '_hole_face_index', None)
        if not pos or not normal:
            self.statusBar().showMessage("Keine Fläche ausgewählt!")
            return

        body = getattr(self, '_hole_target_body', None)
        if not body:
            self._finish_hole_ui()
            return

        diameter = self.hole_panel.get_diameter()
        depth = self.hole_panel.get_depth()
        hole_type = self.hole_panel.get_hole_type()
        has_primary_face_ref = (
            self._hole_face_shape_id is not None
            or face_index is not None
        )

        feature = HoleFeature(
            hole_type=hole_type,
            diameter=diameter,
            depth=depth,
            position=pos,
            direction=tuple(-n for n in normal),  # drill INTO face
            # Selector nur als Legacy-Recovery behalten, wenn keine TNP-v4 Referenz vorhanden ist.
            face_selectors=[face_selector] if (face_selector and not has_primary_face_ref) else [],
        )
        
        # TNP v4.0: Single-face ShapeID immer feature-lokal in Slot 0 führen.
        if self._hole_face_shape_id is not None:
            feature_shape_id = None
            try:
                if face_index is not None and getattr(body, "_build123d_solid", None) is not None:
                    from modeling.topology_indexing import face_from_index

                    resolved_face = face_from_index(body._build123d_solid, int(face_index))
                    if resolved_face is not None:
                        feature_shape_id = self._find_or_register_face_shape_id(
                            body,
                            resolved_face,
                            local_index=0,
                            feature_id=feature.id,
                            force_feature_local=True,
                        )
            except Exception as sid_err:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"Hole: Feature-lokale ShapeID konnte nicht registriert werden: {sid_err}")

            feature.face_shape_ids = [feature_shape_id or self._hole_face_shape_id]
            if is_enabled("tnp_debug_logging"):
                logger.debug("TNP v4.0: Hole Face-ShapeID übernommen (feature-lokaler Slot 0)")
        if face_index is not None:
            try:
                feature.face_indices = [int(face_index)]
            except Exception:
                pass

        cmd = AddFeatureCommand(body, feature, self)
        self.undo_stack.push(cmd)
        if feature.status == "ERROR":
            msg = feature.status_message or "Kernel-Operation fehlgeschlagen"
            self.statusBar().showMessage(f"Hole fehlgeschlagen: {msg}", 8000)
            logger.error(f"Hole fehlgeschlagen: {msg}")
        elif feature.status == "WARNING":
            msg = feature.status_message or "Fallback verwendet"
            self.statusBar().showMessage(f"Hole mit Warnung: {msg}", 6000)
            logger.warning(f"Hole mit Warnung: {msg}")
        else:
            self.statusBar().showMessage(f"Hole D={diameter}mm erstellt")
            logger.success(f"Hole {hole_type} D={diameter}mm at {pos}")
        self._finish_hole_ui()

    def _on_hole_cancelled(self):
        """Hole abgebrochen."""
        self._finish_hole_ui()
        self.statusBar().showMessage("Hole abgebrochen")

    def _finish_hole_ui(self):
        """Hole-UI aufräumen."""
        self._hole_mode = False
        self._hole_target_body = None
        self._hole_face_selector = None
        self._hole_face_shape_id = None
        self._hole_face_index = None
        self.viewport_3d.set_hole_mode(False)
        self.hole_panel.hide()

    def _on_body_face_clicked_for_hole(self, body_id, cell_id, normal, position):
        """Body-Face wurde im Hole-Modus geklickt.
        TNP-robust: Erstellt GeometricFaceSelector für stabile Face-Referenzierung.
        """
        if not self._hole_mode:
            return

        # Auto-detect body from click
        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body or not body._build123d_solid:
            self.statusBar().showMessage("Kein gültiger Body getroffen")
            return

        self._hole_target_body = body
        self.viewport_3d._hole_position = tuple(position)
        self.viewport_3d._hole_normal = tuple(normal)
        
        # TNP-ROBUST: GeometricFaceSelector + echte ShapeID aus aktuellem Solid.
        try:
            from modeling.geometric_selector import GeometricFaceSelector

            best_face, resolved_face_id = self._resolve_solid_face_from_pick(
                body,
                body.id,
                cell_id=cell_id,
                position=position,
            )
            if best_face is not None:
                geo_selector = GeometricFaceSelector.from_face(best_face)
                self._hole_face_selector = geo_selector.to_dict()
                self._hole_face_shape_id = self._find_or_register_face_shape_id(
                    body,
                    best_face,
                    # Single-face reference: feature-local slot is always 0.
                    local_index=0,
                )
                self._hole_face_index = resolved_face_id
                logger.debug(f"Hole: GeometricFaceSelector erstellt (area={geo_selector.area:.1f})")
            else:
                self._hole_face_selector = {
                    "center": list(position),
                    "normal": list(normal),
                    "area": 0.0,
                    "surface_type": "unknown",
                    "tolerance": 10.0,
                }
                self._hole_face_shape_id = None
                self._hole_face_index = None
                logger.warning("Hole: Konnte Face nicht finden, verwende Fallback")
        except Exception as e:
            logger.warning(f"Hole: Konnte GeometricFaceSelector nicht erstellen: {e}")
            self._hole_face_selector = None
            self._hole_face_shape_id = None
            self._hole_face_index = None

        diameter = self.hole_panel.get_diameter()
        depth = self.hole_panel.get_depth()
        self.viewport_3d.show_hole_preview(position, normal, diameter, depth)
        self.statusBar().showMessage(f"Hole auf {body.name} — Parameter einstellen, Enter bestätigen")

    def _thread_dialog(self):
        """Thread-Dialog: Interaktives Gewinde auf zylindrische Fläche (wie Hole),
        oder Schraube/Mutter erzeugen."""
        from gui.dialogs.thread_dialog import ThreadDialog

        dialog = ThreadDialog(parent=self)
        if not dialog.exec():
            return

        mode = dialog.result_mode  # "thread", "bolt", "nut"

        if mode == "thread":
            # Thread on Body - interaktiver Modus wie Hole
            self._start_interactive_thread_mode()

        elif mode == "bolt":
            self._generate_bolt(dialog)

        elif mode == "nut":
            self._generate_nut(dialog)

    def _sketch_agent_dialog(self):
        """Sketch Agent Dialog: Generative CAD-Part-Erstellung mit AI."""
        from gui.dialogs.sketch_agent_dialog import show_sketch_agent_dialog

        show_sketch_agent_dialog(self.document, self.viewport_3d, self)

    def _start_interactive_thread_mode(self):
        """Startet interaktiven Thread-Workflow (Fusion-style).
        Klicke auf eine zylindrische Fläche, um ein Gewinde zu erstellen.
        """
        has_bodies = any(b._build123d_solid for b in self.document.bodies if b._build123d_solid)
        if not has_bodies:
            self.statusBar().showMessage("Keine Bodies mit Geometrie vorhanden")
            logger.warning("Thread: Keine Bodies mit Geometrie.")
            return

        self._hide_transform_ui()
        self._thread_mode = True
        self._thread_target_body = None
        self._thread_position = None
        self._thread_direction = None
        self._thread_detected_diameter = None
        self._thread_is_internal = False
        self._thread_face_selector = None
        self._thread_face_shape_id = None
        self._thread_face_index = None
        self.viewport_3d.set_thread_mode(True)
        self.thread_panel.reset()
        self.thread_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage("Thread: Klicke auf eine zylindrische Fläche (Loch oder Bolzen)")
        logger.info("Thread-Modus gestartet — zylindrische Fläche auf Body klicken")

    def _on_thread_diameter_changed(self, value):
        """Live-Update der Thread-Preview bei Durchmesser-Änderung."""
        if not self._thread_mode:
            return
        self._update_thread_preview()

    def _on_thread_pitch_changed(self, value):
        """Live-Update bei Pitch-Änderung."""
        if not self._thread_mode:
            return
        # Pitch beeinflusst nur die Geometrie, nicht die Preview
        pass

    def _on_thread_depth_changed(self, value):
        """Live-Update der Thread-Preview bei Tiefen-Änderung."""
        if not self._thread_mode:
            return
        self._update_thread_preview()

    def _on_thread_tolerance_changed(self, value):
        """Live-Update bei Toleranz-Änderung."""
        if not self._thread_mode:
            return
        # Toleranz beeinflusst nur die Endgeometrie, nicht die Preview

    def _update_thread_preview(self):
        """Aktualisiert die Thread-Preview basierend auf aktuellen Panel-Werten."""
        pos = self._thread_position
        direction = self._thread_direction
        if pos and direction:
            diameter = self.thread_panel.get_diameter()
            depth = self.thread_panel.get_depth()
            is_internal = self._thread_is_internal
            self.viewport_3d.show_thread_preview(pos, direction, diameter, depth, is_internal)

    def _on_cylindrical_face_clicked_for_thread(self, body_id, cell_id, axis_dir, position, diameter):
        """Zylindrische Fläche wurde im Thread-Modus geklickt."""
        if not self._thread_mode:
            return

        # Finde Body
        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body or not body._build123d_solid:
            self.statusBar().showMessage("Kein gültiger Body getroffen")
            return

        self._thread_target_body = body
        self._thread_position = tuple(position)
        self._thread_direction = tuple(axis_dir)
        self._thread_detected_diameter = diameter
        self._thread_face_selector = None
        self._thread_face_shape_id = None
        self._thread_face_index = None

        try:
            from modeling.geometric_selector import GeometricFaceSelector

            best_face, resolved_face_id = self._resolve_solid_face_from_pick(
                body,
                body.id,
                cell_id=cell_id,
                position=position,
            )
            if best_face is not None:
                geo_selector = GeometricFaceSelector.from_face(best_face)
                self._thread_face_selector = geo_selector.to_dict()
                self._thread_face_shape_id = self._find_or_register_face_shape_id(
                    body,
                    best_face,
                    # Single-face reference: feature-local slot is always 0.
                    local_index=0,
                )
                self._thread_face_index = int(resolved_face_id) if resolved_face_id is not None else None
            else:
                self._thread_face_selector = {
                    "center": list(position),
                    "normal": list(axis_dir),
                    "area": 0.0,
                    "surface_type": "cylinder",
                    "tolerance": 10.0,
                }
        except Exception as e:
            logger.warning(f"Thread: Konnte Face-Referenz nicht erstellen: {e}")

        # Bestimme ob internal (Loch) oder external (Bolzen)
        # Das wird vom Viewport über die detect-Funktion bestimmt
        # Hier nutzen wir die Information aus dem Signal

        # Auto-detect thread type basierend auf Zylinder-Typ
        # (wird im viewport_pyvista bestimmt)
        cyl_info = self.viewport_3d._detect_cylindrical_face(body_id, cell_id, position)
        if cyl_info:
            _, _, is_internal = cyl_info
            self._thread_is_internal = is_internal
            # Setze Thread-Typ im Panel
            self.thread_panel.type_combo.setCurrentIndex(1 if is_internal else 0)

        # Setze erkannten Durchmesser im Panel
        self.thread_panel.set_detected_diameter(diameter)

        # Zeige Preview
        depth = self.thread_panel.get_depth()
        self.viewport_3d.show_thread_preview(position, axis_dir, diameter, depth, self._thread_is_internal)

        thread_type_str = "Internal (Loch)" if self._thread_is_internal else "External (Bolzen)"
        self.statusBar().showMessage(
            f"Thread auf {body.name} — D={diameter:.2f}mm, {thread_type_str} — Parameter einstellen, Enter bestätigen"
        )

    def _on_thread_confirmed(self):
        """Thread bestätigt — Feature erstellen."""
        from modeling import ThreadFeature
        from gui.commands.feature_commands import AddFeatureCommand

        pos = self._thread_position
        direction = self._thread_direction
        if not pos or not direction:
            self.statusBar().showMessage("Keine zylindrische Fläche ausgewählt!")
            return

        body = getattr(self, '_thread_target_body', None)
        if not body:
            self._finish_thread_ui()
            return

        diameter = self.thread_panel.get_diameter()
        pitch = self.thread_panel.get_pitch()
        depth = self.thread_panel.get_depth()
        thread_type = self.thread_panel.get_thread_type()
        tolerance_offset = self.thread_panel.get_tolerance_offset()

        feature = ThreadFeature(
            thread_type=thread_type,
            standard="M",
            diameter=diameter,
            pitch=pitch,
            depth=depth,
            position=pos,
            direction=direction,
            tolerance_class="custom" if tolerance_offset != 0 else "6g" if thread_type == "external" else "6H",
            tolerance_offset=tolerance_offset,
            # Selector nur als Legacy-Recovery behalten, wenn keine TNP-v4 Referenz vorhanden ist.
            face_selector=(
                getattr(self, "_thread_face_selector", None)
                if (self._thread_face_shape_id is None and getattr(self, "_thread_face_index", None) is None)
                else None
            ),
        )
        if self._thread_face_shape_id is not None:
            feature_shape_id = None
            try:
                if getattr(self, "_thread_face_index", None) is not None and getattr(body, "_build123d_solid", None) is not None:
                    from modeling.topology_indexing import face_from_index

                    resolved_face = face_from_index(body._build123d_solid, int(self._thread_face_index))
                    if resolved_face is not None:
                        feature_shape_id = self._find_or_register_face_shape_id(
                            body,
                            resolved_face,
                            local_index=0,
                            feature_id=feature.id,
                            force_feature_local=True,
                        )
            except Exception as sid_err:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"Thread: Feature-lokale ShapeID konnte nicht registriert werden: {sid_err}")
            feature.face_shape_id = feature_shape_id or self._thread_face_shape_id
        if getattr(self, "_thread_face_index", None) is not None:
            feature.face_index = int(self._thread_face_index)

        cmd = AddFeatureCommand(body, feature, self)
        self.undo_stack.push(cmd)
        self.statusBar().showMessage(f"Thread M{diameter:.0f}x{pitch} erstellt")
        logger.success(f"Thread M{diameter:.0f}x{pitch} ({thread_type}) at {pos}")
        self._finish_thread_ui()

    def _on_thread_cancelled(self):
        """Thread abgebrochen."""
        self._finish_thread_ui()
        self.statusBar().showMessage("Thread abgebrochen")

    def _finish_thread_ui(self):
        """Thread-UI aufräumen."""
        self._thread_mode = False
        self._thread_target_body = None
        self._thread_position = None
        self._thread_direction = None
        self._thread_detected_diameter = None
        self._thread_is_internal = False
        self._thread_face_selector = None
        self._thread_face_shape_id = None
        self._thread_face_index = None
        self.viewport_3d.set_thread_mode(False)
        self.thread_panel.hide()

    def _generate_bolt(self, dialog):
        """Generate a bolt as a new body (hex head + REAL threaded shaft)."""
        from modeling import Body, ThreadFeature
        try:
            import build123d as bd

            dia = dialog.diameter
            length = dialog.depth
            hex_af = dialog.hex_af  # across flats
            head_h = dialog.head_height
            pitch = dialog.pitch
            tolerance_offset = dialog.tolerance_offset

            # 1. Hex head
            hex_sketch = bd.RegularPolygon(radius=hex_af / 2 / 0.866025, side_count=6)
            head = bd.extrude(hex_sketch, head_h)

            # 2. Shaft (mit Toleranz-Offset)
            shaft_dia = dia + tolerance_offset
            shaft = bd.Pos(0, 0, -length) * bd.extrude(bd.Circle(shaft_dia / 2), length)

            # 3. Fuse head + shaft (Build123d native operator)
            bolt_solid = head + shaft

            body = Body(name=f"Bolt_M{dia:.0f}x{pitch}", document=self.document)
            body._build123d_solid = bolt_solid

            # 4. Echte Gewinde auf Schaft anwenden
            try:
                feature = ThreadFeature(
                    thread_type="external",
                    standard="M",
                    diameter=shaft_dia,
                    pitch=pitch,
                    depth=length,
                    position=(0, 0, -length),  # Start am Schaft-Ende
                    direction=(0, 0, 1),        # Nach oben
                    tolerance_class=dialog.tolerance_class,
                    tolerance_offset=tolerance_offset,
                )
                threaded_solid = body._compute_thread(feature, bolt_solid)
                body._build123d_solid = threaded_solid
                logger.info(f"[BOLT] Echte Gewinde M{dia}x{pitch} erstellt")
            except Exception as thread_err:
                logger.warning(f"Thread creation failed, using smooth shaft: {thread_err}")
                # Fallback: Glatter Schaft (wie vorher)

            body.invalidate_mesh()
            self.document.add_body(body, set_active=False)
            self._update_body_from_build123d(body, body._build123d_solid)
            self.browser.refresh()
            tol_str = f" ({dialog.tolerance_class})" if dialog.tolerance_class != "custom" else f" (+{tolerance_offset:.3f}mm)"
            self.statusBar().showMessage(f"Bolt M{dia:.0f}x{length:.0f}{tol_str} generated")
            logger.success(f"Bolt M{dia:.0f}x{length:.0f} erzeugt")
        except Exception as e:
            logger.error(f"Bolt generation failed: {e}")

    def _generate_nut(self, dialog):
        """Generate a nut as a new body (hex body with REAL internal threads)."""
        from modeling import Body, ThreadFeature
        try:
            import build123d as bd

            dia = dialog.diameter
            hex_af = dialog.hex_af
            nut_h = dialog.nut_height
            pitch = dialog.pitch
            tolerance_offset = dialog.tolerance_offset

            # 1. Hex outer body
            hex_sketch = bd.RegularPolygon(radius=hex_af / 2 / 0.866025, side_count=6)
            hex_body = bd.extrude(hex_sketch, nut_h)

            # 2. Kernloch-Durchmesser für Innengewinde
            # ISO: Kernloch = Nenndurchmesser - 1.0825 * Pitch
            core_dia = dia - 1.0825 * pitch + tolerance_offset
            hole = bd.extrude(bd.Circle(core_dia / 2), nut_h)

            # Build123d native operator für Cut
            nut_solid = hex_body - hole

            body = Body(name=f"Nut_M{dia:.0f}", document=self.document)
            body._build123d_solid = nut_solid

            # 3. Echte Innengewinde anwenden
            try:
                feature = ThreadFeature(
                    thread_type="internal",
                    standard="M",
                    diameter=dia,
                    pitch=pitch,
                    depth=nut_h,
                    position=(0, 0, 0),
                    direction=(0, 0, 1),
                    tolerance_class=dialog.tolerance_class,
                    tolerance_offset=tolerance_offset,
                )
                threaded_solid = body._compute_thread(feature, nut_solid)
                body._build123d_solid = threaded_solid
                logger.info(f"[NUT] Echte Innengewinde M{dia}x{pitch} erstellt")
            except Exception as thread_err:
                logger.warning(f"Internal thread creation failed, using smooth hole: {thread_err}")
                # Fallback: Glatte Bohrung (wie vorher)

            body.invalidate_mesh()
            self.document.add_body(body, set_active=False)
            self._update_body_from_build123d(body, body._build123d_solid)
            self.browser.refresh()
            tol_str = f" ({dialog.tolerance_class})" if dialog.tolerance_class != "custom" else f" (+{tolerance_offset:.3f}mm)"
            self.statusBar().showMessage(f"Nut M{dia:.0f}{tol_str} generated")
            logger.success(f"Nut M{dia:.0f} erzeugt")
        except Exception as e:
            logger.error(f"Nut generation failed: {e}")

    def _mesh_repair_dialog(self):
        """
        Open mesh repair dialog with viewport selection support.

        UX-Pattern (wie Fillet/Chamfer):
        - Falls Body im Browser ausgewählt → sofort Dialog öffnen
        - Falls kein Body → Pending-Mode, warte auf Viewport-Klick
        """
        selected_bodies = self.browser.get_selected_bodies()

        if not selected_bodies:
            # Pending Mode aktivieren
            self._pending_mesh_repair_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)

            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)

            logger.info("Mesh Repair: Klicke auf einen Körper in der 3D-Ansicht")
            return

        # Body gewählt → direkt Dialog öffnen
        body = selected_bodies[0]
        self._open_mesh_repair_for_body(body)

    def _on_body_clicked_for_mesh_repair(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body angeklickt wird."""
        self._pending_mesh_repair_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.warning(f"Body {body_id} nicht gefunden")
            return

        self._open_mesh_repair_for_body(body)

    def _open_mesh_repair_for_body(self, body):
        """Öffnet den Mesh Repair Dialog für einen spezifischen Body."""
        from gui.dialogs.mesh_repair_dialog import MeshRepairDialog

        if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
            logger.warning(f"'{body.name}' hat keine CAD-Daten (nur Mesh).")
            return

        dlg = MeshRepairDialog(body, parent=self)
        if dlg.exec() and dlg.repaired_solid is not None:
            body._build123d_solid = dlg.repaired_solid
            body.invalidate_mesh()
            self._update_body_mesh(body)
            self.browser.refresh()
            logger.success("Geometry repair angewendet")

    def _nsided_patch_dialog(self):
        """
        Startet N-Sided Patch mit Viewport-Selektion (wie Fillet/Chamfer).

        UX-Pattern:
        - Falls Body ausgewählt → sofort Edge-Selektion starten
        - Falls kein Body → Pending-Mode, warte auf Klick
        """
        selected_bodies = self.browser.get_selected_bodies()

        # Fall 1: Kein Body gewählt → Pending-Mode
        if not selected_bodies:
            self._pending_nsided_patch_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)

            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)

            logger.info("N-Sided Patch: Klicke auf einen Körper in der 3D-Ansicht")
            return

        # Fall 2: Body gewählt → direkt starten
        body = selected_bodies[0]
        self._activate_nsided_patch_for_body(body)

    def _on_body_clicked_for_nsided_patch(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body für N-Sided Patch angeklickt wird."""
        self._pending_nsided_patch_mode = False

        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.warning(f"Body {body_id} nicht gefunden")
            return

        self._activate_nsided_patch_for_body(body)

    def _activate_nsided_patch_for_body(self, body):
        """Aktiviert N-Sided Patch-Modus für einen Body."""
        if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
            logger.warning(f"'{body.name}' hat keine CAD-Daten (nur Mesh).")
            return

        # Transform-Gizmo ausblenden
        if hasattr(self.viewport_3d, 'hide_gizmo'):
            self.viewport_3d.hide_gizmo()
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        self._nsided_patch_mode = True
        self._nsided_patch_target_body = body
        self.nsided_patch_panel.set_target_body(body)
        self.nsided_patch_panel.reset()

        # Body-Lookup Callback setzen (wie bei Fillet/Chamfer)
        self.viewport_3d.set_edge_selection_callbacks(
            get_body_by_id=lambda bid: next((b for b in self.document.bodies if b.id == bid), None)
        )

        # Edge-Selection-Modus starten (wie bei Fillet/Chamfer)
        if hasattr(self.viewport_3d, 'start_edge_selection_mode'):
            self.viewport_3d.start_edge_selection_mode(body.id)

        self.nsided_patch_panel.show_at(self.viewport_3d)
        logger.info(f"N-Sided Patch für '{body.name}' - Wähle mindestens 3 zusammenhängende Boundary-Kanten")

    def _on_nsided_patch_edge_selection_changed(self, count: int):
        """Handler wenn sich die Kanten-Selektion für N-Sided Patch ändert."""
        if self._nsided_patch_mode:
            self.nsided_patch_panel.update_edge_count(count)

    def _on_nsided_patch_confirmed(self):
        """Handler wenn N-Sided Patch bestätigt wird."""
        if not self._nsided_patch_mode or not self._nsided_patch_target_body:
            return

        body = self._nsided_patch_target_body

        # Kanten aus Edge-Selection holen
        selected_edges = []
        selected_edge_indices = []
        if hasattr(self.viewport_3d, 'get_selected_edges'):
            selected_edges = self.viewport_3d.get_selected_edges() or []
        if hasattr(self.viewport_3d, 'get_selected_edge_topology_indices'):
            selected_edge_indices = self.viewport_3d.get_selected_edge_topology_indices() or []

        if len(selected_edges) < 3:
            logger.warning("N-Sided Patch benötigt mindestens 3 Kanten")
            return

        degree = self.nsided_patch_panel.get_degree()
        tangent = self.nsided_patch_panel.get_tangent()

        from modeling import NSidedPatchFeature
        from modeling.geometric_selector import GeometricEdgeSelector
        from modeling.tnp_system import ShapeType
        from gui.commands.feature_commands import AddFeatureCommand

        geometric_selectors = []
        for edge in selected_edges:
            try:
                geometric_selectors.append(GeometricEdgeSelector.from_edge(edge).to_dict())
            except Exception as e:
                logger.debug(f"N-Sided Patch: GeometricSelector fehlgeschlagen: {e}")

        if len(geometric_selectors) < 3:
            logger.warning("N-Sided Patch: Konnte nicht genug TNP-v4 GeometricSelectors erzeugen")
            return

        feat = NSidedPatchFeature(
            edge_indices=selected_edge_indices,
            geometric_selectors=geometric_selectors,
            degree=degree,
            tangent=tangent,
        )

        # TNP v4.0: ShapeIDs für ausgewählte Edges ermitteln/registrieren
        edge_shape_ids = []
        shape_service = getattr(self.document, "_shape_naming_service", None)
        if shape_service:
            for idx, edge in enumerate(selected_edges):
                try:
                    shape_id = shape_service.find_shape_id_by_edge(edge, require_exact=True)
                    if shape_id is None and hasattr(edge, "wrapped"):
                        ec = edge.center()
                        edge_len = edge.length if hasattr(edge, "length") else 0.0
                        shape_id = shape_service.register_shape(
                            ocp_shape=edge.wrapped,
                            shape_type=ShapeType.EDGE,
                            feature_id=feat.id,
                            local_index=idx,
                            geometry_data=(ec.X, ec.Y, ec.Z, edge_len),
                        )
                    if shape_id is not None:
                        edge_shape_ids.append(shape_id)
                except Exception as e:
                    logger.debug(f"N-Sided Patch: ShapeID-Auflösung fehlgeschlagen: {e}")
        feat.edge_shape_ids = edge_shape_ids

        # KRITISCH: Verwende AddFeatureCommand für korrektes Undo/Redo!
        cmd = AddFeatureCommand(body, feat, self, description=f"N-Sided Patch ({len(selected_edges)} edges)")
        self.undo_stack.push(cmd)

        # Prüfe ob Operation erfolgreich war
        if body._build123d_solid is None:
            logger.warning("N-Sided Patch ließ Body leer - Undo")
            self.undo_stack.undo()
            logger.error("N-Sided Patch fehlgeschlagen: Geometrie ungültig")
        else:
            self._update_body_mesh(body)
            self.browser.refresh()
            logger.success(
                f"N-Sided Patch mit {len(selected_edges)} Kanten angewendet "
                f"(TopoIdx: {len(selected_edge_indices)}, ShapeIDs: {len(edge_shape_ids)})"
            )

        # Mode beenden
        self._stop_nsided_patch_mode()

    def _on_nsided_patch_cancelled(self):
        """Handler wenn N-Sided Patch abgebrochen wird."""
        self._stop_nsided_patch_mode()
        logger.info("N-Sided Patch abgebrochen")

    def _stop_nsided_patch_mode(self):
        """Beendet den N-Sided Patch Modus."""
        self._nsided_patch_mode = False
        self._nsided_patch_target_body = None
        self._pending_nsided_patch_mode = False

        # Edge-Selection stoppen
        if hasattr(self.viewport_3d, 'stop_edge_selection_mode'):
            self.viewport_3d.stop_edge_selection_mode()

        self.nsided_patch_panel.hide()

    def _surface_analysis_dialog(self):
        """
        Open surface analysis dialog with viewport selection support.

        UX-Pattern (wie Fillet/Chamfer):
        - Falls Body im Browser ausgewählt → sofort Dialog öffnen
        - Falls kein Body → Pending-Mode, warte auf Viewport-Klick
        """
        selected_bodies = self.browser.get_selected_bodies()

        if not selected_bodies:
            # Pending Mode aktivieren
            self._pending_surface_analysis_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)

            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)

            logger.info("Surface Analysis: Klicke auf einen Körper in der 3D-Ansicht")
            return

        # Body gewählt → direkt Dialog öffnen
        body = selected_bodies[0]
        self._open_surface_analysis_for_body(body)

    def _on_body_clicked_for_surface_analysis(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body angeklickt wird."""
        self._pending_surface_analysis_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.warning(f"Body {body_id} nicht gefunden")
            return

        self._open_surface_analysis_for_body(body)

    def _open_surface_analysis_for_body(self, body):
        """Öffnet den Surface Analysis Dialog für einen spezifischen Body."""
        from gui.dialogs.surface_analysis_dialog import SurfaceAnalysisDialog

        if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
            logger.warning(f"'{body.name}' hat keine CAD-Daten (nur Mesh).")
            return

        SurfaceAnalysisDialog(body, self.viewport_3d, parent=self).exec()

    def _wall_thickness_dialog(self):
        """
        Open wall thickness analysis dialog with viewport selection support.

        UX-Pattern (wie Fillet/Chamfer):
        - Falls Body im Browser ausgewählt → sofort Dialog öffnen
        - Falls kein Body → Pending-Mode, warte auf Viewport-Klick
        """
        selected_bodies = self.browser.get_selected_bodies()

        if not selected_bodies:
            # Pending Mode aktivieren
            self._pending_wall_thickness_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)

            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)

            logger.info("Wall Thickness: Klicke auf einen Körper in der 3D-Ansicht")
            return

        # Body gewählt → direkt Dialog öffnen
        body = selected_bodies[0]
        self._open_wall_thickness_for_body(body)

    def _on_body_clicked_for_wall_thickness(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body angeklickt wird."""
        self._pending_wall_thickness_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.warning(f"Body {body_id} nicht gefunden")
            return

        self._open_wall_thickness_for_body(body)

    def _open_wall_thickness_for_body(self, body):
        """Öffnet den Wall Thickness Dialog für einen spezifischen Body."""
        from gui.dialogs.wall_thickness_dialog import WallThicknessDialog

        if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
            logger.warning(f"'{body.name}' hat keine CAD-Daten (nur Mesh).")
            return

        WallThicknessDialog(body, parent=self).exec()

    def _start_lattice(self):
        """
        Startet Lattice-Modus mit Viewport-Selektion (wie Pattern/Fillet).

        UX-Pattern:
        - Falls Body ausgewählt → sofort Panel anzeigen
        - Falls kein Body → Pending-Mode, warte auf Klick
        """
        selected_bodies = self.browser.get_selected_bodies()

        if not selected_bodies:
            # Pending Mode aktivieren
            self._pending_lattice_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)

            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)

            logger.info("Lattice: Klicke auf einen Körper in der 3D-Ansicht")
            return

        # Body gewählt → direkt starten
        body = selected_bodies[0]
        self._activate_lattice_for_body(body)

    def _on_body_clicked_for_lattice(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body für Lattice angeklickt wird."""
        self._pending_lattice_mode = False

        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.warning(f"Body {body_id} nicht gefunden")
            return

        self._activate_lattice_for_body(body)

    def _activate_lattice_for_body(self, body):
        """Aktiviert Lattice-Modus für einen Body."""
        if body._build123d_solid is None:
            logger.warning("Lattice erfordert einen CAD-Body (kein Mesh)")
            return

        self._lattice_mode = True
        self._lattice_target_body = body
        self.lattice_panel.set_target_body(body)
        self.lattice_panel.reset()
        self.lattice_panel.show_at(self.viewport_3d)

        logger.info(f"Lattice für '{body.name}' - Parameter anpassen, Generate zum Anwenden")

    def _on_lattice_confirmed(self):
        """Wird aufgerufen wenn der User im Lattice-Panel 'Generate' klickt."""
        from modeling import LatticeFeature
        from modeling.lattice_generator import LatticeGenerator
        from PySide6.QtCore import QThread, Signal as QSignal
        from PySide6.QtWidgets import QProgressDialog

        body = self.lattice_panel.get_target_body()
        if not body or not body._build123d_solid:
            logger.warning("Kein gültiger Body für Lattice")
            return

        params = self.lattice_panel.get_parameters()
        cell_type = params["cell_type"]
        cell_size = params["cell_size"]
        beam_radius = params["beam_radius"]
        shell_thickness = params["shell_thickness"]
        solid = body._build123d_solid

        # Panel ausblenden während Berechnung
        self.lattice_panel.hide()

        # Worker thread für lange Berechnung
        class LatticeWorker(QThread):
            progress = QSignal(int, str)
            finished_ok = QSignal(object)
            finished_err = QSignal(str)

            def run(self):
                try:
                    result = LatticeGenerator.generate(
                        solid, cell_type=cell_type, cell_size=cell_size,
                        beam_radius=beam_radius,
                        progress_callback=lambda pct, msg: self.progress.emit(pct, msg),
                        shell_thickness=shell_thickness,
                    )
                    self.finished_ok.emit(result)
                except Exception as e:
                    self.finished_err.emit(str(e))

        from PySide6.QtCore import Qt as QtConst
        from gui.design_tokens import DesignTokens

        progress_dlg = QProgressDialog("Lattice generieren...", "Abbrechen", 0, 100, self)
        progress_dlg.setWindowTitle("Lattice")
        progress_dlg.setWindowModality(QtConst.WindowModal)
        progress_dlg.setMinimumWidth(350)
        progress_dlg.setMinimumDuration(0)
        progress_dlg.setValue(0)
        progress_dlg.setAutoClose(False)
        progress_dlg.setAutoReset(False)
        progress_dlg.setStyleSheet(DesignTokens.stylesheet_dialog())

        worker = LatticeWorker()

        def on_progress(pct, msg):
            if not progress_dlg.wasCanceled():
                progress_dlg.setValue(pct)
                progress_dlg.setLabelText(msg)

        def on_success(lattice_solid):
            progress_dlg.setValue(100)
            progress_dlg.close()
            if lattice_solid is not None:
                # Validierung: Zähle Faces im Ergebnis vs Original
                from OCP.TopExp import TopExp_Explorer
                from OCP.TopAbs import TopAbs_FACE

                # Original Face-Count
                original_faces = 0
                if hasattr(solid, 'wrapped'):
                    exp = TopExp_Explorer(solid.wrapped, TopAbs_FACE)
                else:
                    exp = TopExp_Explorer(solid, TopAbs_FACE)
                while exp.More():
                    original_faces += 1
                    exp.Next()

                # Lattice Face-Count
                lattice_faces = 0
                if hasattr(lattice_solid, 'wrapped'):
                    exp = TopExp_Explorer(lattice_solid.wrapped, TopAbs_FACE)
                else:
                    exp = TopExp_Explorer(lattice_solid, TopAbs_FACE)
                while exp.More():
                    lattice_faces += 1
                    exp.Next()

                logger.info(f"Lattice Validierung: Original={original_faces} Faces, Lattice={lattice_faces} Faces")

                # Lattice sollte VIEL mehr Faces haben als Original (mindestens 3x)
                # Ein einfacher Box hat 6 Faces, ein Lattice mit 50 Beams hat ~600+ Faces
                MIN_FACE_RATIO = 3.0
                if lattice_faces <= original_faces * MIN_FACE_RATIO:
                    logger.error(
                        f"Lattice-Generierung fehlgeschlagen: Ergebnis hat nur {lattice_faces} Faces "
                        f"(erwartet mindestens {int(original_faces * MIN_FACE_RATIO)}). "
                        f"Boolean-Schnitt hat wahrscheinlich nicht funktioniert."
                    )
                    QMessageBox.warning(
                        self, "Lattice fehlgeschlagen",
                        f"Die Lattice-Generierung hat keine gültige Gitterstruktur erzeugt.\n\n"
                        f"Original: {original_faces} Flächen\n"
                        f"Ergebnis: {lattice_faces} Flächen\n\n"
                        f"Mögliche Ursachen:\n"
                        f"• Cell-Size zu groß für den Body\n"
                        f"• Beam-Radius zu klein\n"
                        f"• Body-Geometrie zu komplex\n\n"
                        f"Versuchen Sie eine kleinere Cell-Size oder größeren Beam-Radius."
                    )
                    self._lattice_mode = False
                    self._lattice_target_body = None
                    worker.deleteLater()
                    return

                # Validierung bestanden - Lattice anwenden
                from gui.commands.feature_commands import AddFeatureCommand

                feat = LatticeFeature(
                    cell_type=cell_type, cell_size=cell_size, beam_radius=beam_radius,
                    shell_thickness=shell_thickness,
                )

                # Speichere pre-computed solid damit _rebuild() es verwenden kann
                feat._precomputed_solid = lattice_solid

                # KRITISCH: Verwende AddFeatureCommand für korrektes Undo/Redo!
                cmd = AddFeatureCommand(body, feat, self, description=f"Lattice ({cell_type})")
                self.undo_stack.push(cmd)

                body.invalidate_mesh()
                self._update_body_from_build123d(body, body._build123d_solid)
                self.browser.refresh()
                logger.success(f"Lattice ({cell_type}) angewendet auf {body.name} ({lattice_faces} Faces)")
            self._lattice_mode = False
            self._lattice_target_body = None
            worker.deleteLater()

        def on_error(msg):
            progress_dlg.close()
            logger.error(f"Lattice fehlgeschlagen: {msg}")
            self._lattice_mode = False
            self._lattice_target_body = None
            worker.deleteLater()

        worker.progress.connect(on_progress, QtConst.QueuedConnection)
        worker.finished_ok.connect(on_success, QtConst.QueuedConnection)
        worker.finished_err.connect(on_error, QtConst.QueuedConnection)

        # Keep reference to prevent GC
        self._lattice_worker = worker
        worker.start()

    def _on_lattice_cancelled(self):
        """Wird aufgerufen wenn der User das Lattice-Panel abbricht."""
        self.lattice_panel.hide()
        self._lattice_mode = False
        self._lattice_target_body = None
        self._pending_lattice_mode = False
        logger.info("Lattice abgebrochen")

    def _hollow_dialog(self):
        """Open hollow dialog for selected body."""
        from gui.dialogs.hollow_dialog import HollowDialog
        from modeling import HollowFeature

        body = self._get_active_body()
        if not body or not body._build123d_solid:
            logger.warning("Kein Body mit Geometrie ausgewaehlt.")
            return

        dlg = HollowDialog(parent=self)
        if not dlg.exec():
            return

        # Drain hole position = center of bounding box bottom
        drain_pos = (0, 0, 0)
        try:
            bb = body._build123d_solid.bounding_box()
            cx = (bb.min.X + bb.max.X) / 2
            cy = (bb.min.Y + bb.max.Y) / 2
            cz = bb.min.Z
            drain_pos = (cx, cy, cz)
        except Exception:
            pass

        from gui.commands.feature_commands import AddFeatureCommand

        feat = HollowFeature(
            wall_thickness=dlg.wall_thickness,
            drain_hole=dlg.drain_hole,
            drain_diameter=dlg.drain_diameter,
            drain_position=drain_pos,
            drain_direction=dlg.drain_direction,
        )

        # KRITISCH: Verwende AddFeatureCommand für korrektes Undo/Redo!
        cmd = AddFeatureCommand(body, feat, self, description=f"Hollow (Wandstärke {dlg.wall_thickness}mm)")
        self.undo_stack.push(cmd)

        # Prüfe ob Operation erfolgreich war
        if body._build123d_solid is None:
            logger.warning("Hollow ließ Body leer - Undo")
            self.undo_stack.undo()
            logger.error("Hollow fehlgeschlagen: Geometrie ungültig")
        else:
            body.invalidate_mesh()
            self._update_body_from_build123d(body, body._build123d_solid)
            self._browser.refresh()
            logger.success(f"Hollow angewendet auf {body.name} (Wandstärke {dlg.wall_thickness}mm)")

    def _geometry_check_dialog(self):
        """
        Open geometry validation/healing dialog with viewport selection support.

        UX-Pattern (wie Fillet/Chamfer):
        - Falls Body im Browser ausgewählt → sofort Dialog öffnen
        - Falls kein Body → Pending-Mode, warte auf Viewport-Klick
        """
        selected_bodies = self.browser.get_selected_bodies()

        if not selected_bodies:
            # Pending Mode aktivieren
            self._pending_geometry_check_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)

            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)

            logger.info("Check Geometry: Klicke auf einen Körper in der 3D-Ansicht")
            return

        # Body gewählt → direkt Dialog öffnen
        body = selected_bodies[0]
        self._open_geometry_check_for_body(body)

    def _on_body_clicked_for_geometry_check(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body angeklickt wird."""
        self._pending_geometry_check_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.warning(f"Body {body_id} nicht gefunden")
            return

        self._open_geometry_check_for_body(body)

    def _open_geometry_check_for_body(self, body):
        """Öffnet den Geometry Check Dialog für einen spezifischen Body."""
        from gui.dialogs.geometry_check_dialog import GeometryCheckDialog

        if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
            logger.warning(f"'{body.name}' hat keine CAD-Daten (nur Mesh).")
            return

        dialog = GeometryCheckDialog(body, parent=self)
        if dialog.exec() and dialog.healed_solid is not None:
            body._build123d_solid = dialog.healed_solid
            body.invalidate_mesh()
            self._update_body_from_build123d(body, dialog.healed_solid)
            self.statusBar().showMessage(f"Geometry healed: {body.name}")
            logger.success(f"Geometry healed for {body.name}")

    def _primitive_dialog(self, ptype="box"):
        """Create a primitive solid (Box, Cylinder, Sphere, Cone) as new body."""
        from gui.dialogs.primitive_dialog import PrimitiveDialog
        from modeling import Body

        dialog = PrimitiveDialog(primitive_type=ptype, parent=self)
        if not dialog.exec():
            return

        try:
            t = dialog.result_type
            if t == "box":
                name = f"Box_{dialog.length:.0f}x{dialog.width:.0f}x{dialog.height:.0f}"
                feature = PrimitiveFeature(
                    primitive_type="box", name=name,
                    parameters={"length": dialog.length, "width": dialog.width, "height": dialog.height}
                )
            elif t == "cylinder":
                name = f"Cylinder_R{dialog.radius:.0f}_H{dialog.height:.0f}"
                feature = PrimitiveFeature(
                    primitive_type="cylinder", name=name,
                    parameters={"radius": dialog.radius, "height": dialog.height}
                )
            elif t == "sphere":
                name = f"Sphere_R{dialog.radius:.0f}"
                feature = PrimitiveFeature(
                    primitive_type="sphere", name=name,
                    parameters={"radius": dialog.radius}
                )
            elif t == "cone":
                name = f"Cone_R{dialog.bottom_radius:.0f}_H{dialog.height:.0f}"
                feature = PrimitiveFeature(
                    primitive_type="cone", name=name,
                    parameters={"bottom_radius": dialog.bottom_radius,
                                "top_radius": dialog.top_radius, "height": dialog.height}
                )
            else:
                return

            body = Body(name=name, document=self.document)
            self.document.add_body(body, set_active=False)
            body.add_feature(feature)
            self._update_body_from_build123d(body, body._build123d_solid)
            self.browser.refresh()
            self.statusBar().showMessage(f"{name} created")
            logger.success(f"Primitive {name} erstellt")
        except Exception as e:
            logger.error(f"Primitive creation failed: {e}")

    def _draft_dialog(self):
        """Startet interaktiven Draft-Workflow (Fusion-style).
        Klick auf Body-Faces → Winkel einstellen → Enter.
        """
        has_bodies = any(b._build123d_solid for b in self.document.bodies if b._build123d_solid)
        if not has_bodies:
            self.statusBar().showMessage("Keine Bodies mit Geometrie vorhanden")
            return

        self._hide_transform_ui()
        self._draft_mode = True
        self._draft_target_body = None
        # Body-Faces erkennen für full-face Highlighting
        self.viewport_3d.detected_faces = []
        self.viewport_3d._detect_body_faces()
        logger.info(f"Draft: {len(self.viewport_3d.detected_faces)} Body-Faces erkannt")
        self.viewport_3d.set_draft_mode(True)
        self.draft_panel.reset()
        self.draft_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage("Draft: Klicke auf Flächen des Bodys (Mehrfachselektion mit Klick)")
        logger.info("Draft-Modus gestartet — Flächen auf Body klicken")

    def _on_body_face_clicked_for_draft(self, body_id, cell_id, normal, position):
        """Body-Face wurde im Draft-Modus geklickt.
        Face-Toggle passiert schon im Viewport (_toggle_draft_face).
        Hier nur Body setzen und UI updaten.
        """
        if not self._draft_mode:
            return

        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body or not body._build123d_solid:
            return

        self._draft_target_body = body
        count = len(self.viewport_3d._draft_selected_faces)
        self.draft_panel.set_face_count(count)
        self.statusBar().showMessage(f"Draft: {count} Face(s) ausgewählt — Winkel einstellen, Enter bestätigen")
        self._update_draft_preview()

    def _on_draft_angle_changed(self, value):
        """Draft-Winkel geändert."""
        self._update_draft_preview()

    def _on_draft_axis_changed(self, axis):
        """Draft Pull-Richtung geändert."""
        self._update_draft_preview()

    def _update_draft_preview(self):
        """Live-Preview des Draft-Ergebnisses."""
        body = getattr(self, '_draft_target_body', None)
        faces = self.viewport_3d._draft_selected_faces
        if not body or not body._build123d_solid or not faces:
            self.viewport_3d.clear_draft_preview()
            return

        try:
            from modeling import DraftFeature
            angle = self.draft_panel.get_angle()
            pull_dir = self.draft_panel.get_pull_direction()
            face_normals = [tuple(f.get('normal', (0, 0, 0))) for f in faces]

            feature = DraftFeature(
                draft_angle=angle,
                pull_direction=pull_dir,
                face_selectors=[{'normal': n} for n in face_normals],
            )

            # Compute draft on kernel (temporary, not committed)
            result_solid = body._compute_draft(feature, body._build123d_solid)
            if result_solid is None:
                self.viewport_3d.clear_draft_preview()
                return

            # Tessellate and show preview
            from modeling.cad_tessellator import CADTessellator
            mesh, _ = CADTessellator.tessellate(result_solid)
            if mesh is not None:
                self.viewport_3d._show_draft_preview_mesh(mesh)
            else:
                self.viewport_3d.clear_draft_preview()
        except Exception as e:
            logger.debug(f"Draft preview error: {e}")
            self.viewport_3d.clear_draft_preview()

    def _on_draft_confirmed(self):
        """Draft bestätigt — Feature erstellen.
        TNP-robust: Erstellt GeometricFaceSelectors für stabile Face-Referenzierung.
        """
        from modeling import DraftFeature
        from modeling.geometric_selector import GeometricFaceSelector
        from gui.commands.feature_commands import AddFeatureCommand

        body = getattr(self, '_draft_target_body', None)
        if not body:
            self.statusBar().showMessage("Kein Body ausgewählt!")
            self._finish_draft_ui()
            return

        faces = self.viewport_3d._draft_selected_faces
        if not faces:
            self.statusBar().showMessage("Keine Flächen ausgewählt!")
            return

        angle = self.draft_panel.get_angle()
        pull_dir = self.draft_panel.get_pull_direction()

        # TNP-ROBUST: Erstelle GeometricFaceSelectors für jedes Face
        face_selectors = []
        face_shape_ids = []
        face_indices = []
        for idx, face_data in enumerate(faces):
            try:
                normal = face_data.get("normal", (0, 0, 1))
                center = face_data.get("center_3d", face_data.get("center", (0.0, 0.0, 0.0)))

                cell_ids = face_data.get("cell_ids", []) or []
                candidate_cell_id = int(cell_ids[0]) if cell_ids else None

                explicit_face_id = face_data.get("face_id")
                explicit_face_id = int(explicit_face_id) if explicit_face_id is not None else None

                best_face, resolved_face_id = self._resolve_solid_face_from_pick(
                    body,
                    body.id,
                    cell_id=candidate_cell_id,
                    position=center,
                    ocp_face_id=explicit_face_id,
                )

                if best_face is not None:
                    geo_selector = GeometricFaceSelector.from_face(best_face)
                    face_selectors.append(geo_selector.to_dict())
                    shape_id = self._find_or_register_face_shape_id(
                        body,
                        best_face,
                        # Multi-face reference: slot index in feature reference list.
                        local_index=idx,
                    )
                    if shape_id is not None:
                        face_shape_ids.append(shape_id)
                    if resolved_face_id is not None:
                        face_indices.append(int(resolved_face_id))
                else:
                    face_selectors.append(
                        {
                            "center": list(center),
                            "normal": list(normal),
                            "area": 0.0,
                            "surface_type": "unknown",
                            "tolerance": 10.0,
                        }
                    )
            except Exception as e:
                logger.warning(f"Draft: Konnte Face-Referenz nicht erstellen: {e}")
                continue

        feature = DraftFeature(
            draft_angle=angle,
            pull_direction=pull_dir,
            face_selectors=face_selectors,
        )
        
        if face_shape_ids:
            feature.face_shape_ids = face_shape_ids
        if face_indices:
            feature.face_indices = sorted(set(face_indices))
        if is_enabled("tnp_debug_logging"):
            logger.debug(
                f"TNP v4.0: Draft-Referenzen vorbereitet "
                f"(selectors={len(face_selectors)}, shape_ids={len(face_shape_ids)}, "
                f"indices={len(feature.face_indices or [])})"
            )

        cmd = AddFeatureCommand(body, feature, self)
        self.undo_stack.push(cmd)
        if feature.status == "ERROR":
            msg = feature.status_message or "Kernel-Operation fehlgeschlagen"
            self.statusBar().showMessage(f"Draft fehlgeschlagen: {msg}", 8000)
            logger.error(f"Draft fehlgeschlagen: {msg}")
        elif feature.status == "WARNING":
            msg = feature.status_message or "Fallback verwendet"
            self.statusBar().showMessage(f"Draft mit Warnung: {msg}", 6000)
            logger.warning(f"Draft mit Warnung: {msg}")
        else:
            self.statusBar().showMessage(f"Draft {angle}° auf {len(faces)} Faces erstellt")
            logger.success(f"Draft {angle}° auf {len(faces)} Faces")
        self._finish_draft_ui()

    def _on_draft_cancelled(self):
        """Draft abgebrochen."""
        self._finish_draft_ui()
        self.statusBar().showMessage("Draft abgebrochen")

    def _finish_draft_ui(self):
        """Draft-UI aufräumen."""
        self._draft_mode = False
        self._draft_target_body = None
        self.viewport_3d.set_draft_mode(False)
        self.draft_panel.hide()

    def _split_body_dialog(self):
        """Startet interaktiven Split-Workflow (PrusaSlicer-style)."""
        has_bodies = any(b._build123d_solid for b in self.document.bodies if b._build123d_solid)
        if not has_bodies:
            self.statusBar().showMessage("Keine Bodies mit Geometrie vorhanden")
            return

        self._hide_transform_ui()
        self._split_mode = True
        self._split_target_body = None
        self.split_panel.reset()
        self.split_panel.show_at(self.viewport_3d)

        # Use proven body-pick mechanism (same as fillet/chamfer/transform)
        self._pending_split_mode = True
        self.viewport_3d.setCursor(Qt.CrossCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(True)

        self.statusBar().showMessage("Split: Klicke auf einen Body im Viewport")
        logger.info("Split-Modus gestartet — Body im Viewport klicken")

    def _on_split_body_clicked(self, body_id):
        """Body wurde im Split-Modus geklickt."""
        if not self._split_mode:
            return
        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body or not body._build123d_solid:
            return

        self._split_target_body = body
        # Now activate split viewport mode for drag interaction
        self.viewport_3d.set_split_mode(True)
        center = self.viewport_3d.set_split_body(body_id)
        if center is not None:
            self.split_panel.set_position(center)
        self.statusBar().showMessage("Split: Ebene verschieben (Drag/Zahleneingabe), Enter bestätigen")
        self._update_split_preview()

    def _on_split_plane_changed(self, plane):
        """Schnittebene geändert (XY/XZ/YZ)."""
        if not self._split_mode or not self._split_target_body:
            return
        self.viewport_3d._split_plane_axis = plane
        # Recenter position for new axis
        center = self.viewport_3d.set_split_body(self._split_target_body.id)
        if center is not None:
            self.split_panel.set_position(center)
        self._update_split_preview()

    def _on_split_position_changed(self, value):
        """Position per Panel geändert."""
        if not self._split_mode or not self._split_target_body:
            return
        self.viewport_3d.update_split_plane(self.viewport_3d._split_plane_axis, value)
        self._update_split_preview()

    def _on_split_angle_changed(self, angle):
        """Schnittwinkel geändert."""
        if not self._split_mode or not self._split_target_body:
            return
        self.viewport_3d._split_angle = angle
        self.viewport_3d._draw_split_plane()
        self._schedule_split_preview()

    def _on_split_keep_changed(self, keep):
        """Keep-Seite geändert."""
        self._update_split_preview()

    def _on_split_drag(self, position):
        """Viewport-Drag → Panel synchronisieren."""
        self.split_panel.set_position(position)
        self._schedule_split_preview()

    def _schedule_split_preview(self):
        """Debounced split preview — verhindert Spam bei schnellem Drag."""
        if not hasattr(self, '_split_preview_timer'):
            from PySide6.QtCore import QTimer
            self._split_preview_timer = QTimer(self)
            self._split_preview_timer.setSingleShot(True)
            self._split_preview_timer.timeout.connect(self._update_split_preview)
        self._split_preview_timer.start(150)  # 150ms debounce

    def _split_origin_normal(self):
        """Berechnet Origin und Normal für die aktuelle Split-Konfiguration (inkl. Winkel)."""
        import numpy as np
        axis = self.viewport_3d._split_plane_axis
        pos = self.viewport_3d._split_position
        angle_deg = self.split_panel.get_angle()

        if axis == "XY":
            origin, normal = (0, 0, pos), np.array([0.0, 0.0, 1.0])
        elif axis == "XZ":
            origin, normal = (0, pos, 0), np.array([0.0, 1.0, 0.0])
        else:
            origin, normal = (pos, 0, 0), np.array([1.0, 0.0, 0.0])

        if abs(angle_deg) > 0.01:
            # Rotate normal around a perpendicular axis
            angle_rad = np.radians(angle_deg)
            # Pick rotation axis perpendicular to normal
            if axis == "XY":
                rot_axis = np.array([1.0, 0.0, 0.0])  # rotate around X
            elif axis == "XZ":
                rot_axis = np.array([1.0, 0.0, 0.0])  # rotate around X
            else:
                rot_axis = np.array([0.0, 1.0, 0.0])  # rotate around Y
            # Rodrigues rotation
            k = rot_axis
            c, s = np.cos(angle_rad), np.sin(angle_rad)
            normal = normal * c + np.cross(k, normal) * s + k * np.dot(k, normal) * (1 - c)
            normal = normal / (np.linalg.norm(normal) + 1e-12)

        return origin, tuple(normal)

    def _update_split_preview(self):
        """Live-Preview beider Hälften."""
        body = getattr(self, '_split_target_body', None)
        if not body or not body._build123d_solid:
            self.viewport_3d.clear_split_preview_meshes()
            return

        try:
            from modeling import SplitFeature
            from modeling.cad_tessellator import CADTessellator

            origin, normal = self._split_origin_normal()

            above_mesh = None
            below_mesh = None

            for side in ["above", "below"]:
                feature = SplitFeature(
                    plane_origin=origin,
                    plane_normal=normal,
                    keep_side=side,
                )
                try:
                    result = body._compute_split(feature, body._build123d_solid)
                    if result is not None:
                        mesh, _ = CADTessellator.tessellate(result)
                        if side == "above":
                            above_mesh = mesh
                        else:
                            below_mesh = mesh
                except Exception:
                    pass

            self.viewport_3d.show_split_preview(above_mesh, below_mesh)

            # Dim original body — use correct actor name (body_<id>_m)
            body_data = self.viewport_3d.bodies.get(body.id)
            if body_data and 'mesh' in body_data:
                try:
                    self.viewport_3d.plotter.add_mesh(
                        body_data['mesh'], color='#666666', opacity=0.15,
                        name=f"body_{body.id}_m", pickable=False
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.debug(f"Split preview error: {e}")
            self.viewport_3d.clear_split_preview_meshes()

    def _on_split_confirmed(self):
        """Split bestätigt — Feature erstellen."""
        from modeling import SplitFeature
        from gui.commands.feature_commands import AddFeatureCommand, SplitBodyCommand

        body = getattr(self, '_split_target_body', None)
        if not body:
            self.statusBar().showMessage("Kein Body ausgewählt!")
            self._finish_split_ui()
            return

        keep = self.split_panel.get_keep_side()
        origin, normal = self._split_origin_normal()

        if keep == "both":
            # Multi-Body Split Architecture (AGENTS.md Phase 5)
            # Verwende SplitBodyCommand für korrektes Undo/Redo
            cmd = SplitBodyCommand(
                self.document,
                body,
                origin,
                normal,
                self
            )
            self.undo_stack.push(cmd)

            self.statusBar().showMessage("Split (both) — 2 Bodies erstellt")
            logger.success("Split Body (both) erstellt — mit shared Historie und Undo/Redo")
        else:
            # Legacy: Nur eine Seite behalten
            feature = SplitFeature(
                plane_origin=origin, plane_normal=normal, keep_side=keep,
            )
            cmd = AddFeatureCommand(body, feature, self)
            self.undo_stack.push(cmd)
            self.statusBar().showMessage(f"Split ({keep}) applied")
            logger.success(f"Split Body ({keep}) erstellt")

        self._finish_split_ui()

    def _on_split_cancelled(self):
        """Split abgebrochen."""
        self._finish_split_ui()
        self.statusBar().showMessage("Split abgebrochen")

    def _finish_split_ui(self):
        """Split-UI aufräumen."""
        self._split_mode = False
        self._pending_split_mode = False
        self._split_target_body = None
        self.viewport_3d.set_split_mode(False)
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)
        self.split_panel.hide()
        # Restore body visibility — full re-render
        self._trigger_viewport_update()

    def _revolve_dialog(self):
        """Startet den interaktiven Revolve-Workflow (Fusion-Style)."""
        self._update_detector()

        if not self.viewport_3d.detector.selection_faces:
            logger.warning("Keine Sketch-Profile gefunden. Erstelle zuerst einen Sketch.")
            return

        self._hide_transform_ui()
        self.viewport_3d.set_revolve_mode(True)
        self.viewport_3d.set_selection_mode("face")
        self.revolve_panel.reset()
        self.revolve_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage(tr("Revolve: Wähle Profil-Fläche"))

    def _on_revolve_angle_changed(self, angle):
        """Panel-Winkel geändert → Preview aktualisieren."""
        if self.viewport_3d.revolve_mode and self.viewport_3d._revolve_selected_faces:
            self.viewport_3d.show_revolve_preview(
                angle, self.revolve_panel.get_axis(),
                self.revolve_panel.get_operation()
            )

    def _on_revolve_axis_changed(self, axis):
        """Panel-Achse geändert → Preview aktualisieren."""
        if self.viewport_3d.revolve_mode and self.viewport_3d._revolve_selected_faces:
            self.viewport_3d.show_revolve_preview(
                self.revolve_panel.get_angle(), axis,
                self.revolve_panel.get_operation()
            )

    def _on_revolve_operation_changed(self, operation):
        """Panel-Operation geändert → Preview-Farbe aktualisieren."""
        if self.viewport_3d.revolve_mode and self.viewport_3d._revolve_selected_faces:
            self.viewport_3d.show_revolve_preview(
                self.revolve_panel.get_angle(),
                self.revolve_panel.get_axis(), operation
            )

    def _on_revolve_direction_flipped(self):
        """Revolve-Richtung umkehren → Preview aktualisieren."""
        if self.viewport_3d.revolve_mode and self.viewport_3d._revolve_selected_faces:
            self.viewport_3d.show_revolve_preview(
                self.revolve_panel.get_angle(),
                self.revolve_panel.get_axis(),
                self.revolve_panel.get_operation()
            )

    def _on_revolve_confirmed(self):
        """Revolve bestätigen und Feature erstellen."""
        from modeling import RevolveFeature
        from gui.commands.feature_commands import AddFeatureCommand

        face_ids = self.viewport_3d._revolve_selected_faces
        if not face_ids:
            logger.warning("Keine Fläche selektiert.")
            self._on_revolve_cancelled()
            return

        angle = self.revolve_panel.get_angle()
        axis = self.revolve_panel.get_axis()
        operation = self.revolve_panel.get_operation()

        # Sketch + Polygone aus Detector extrahieren (wie Extrude)
        selection_data = []
        for fid in face_ids:
            face = next((f for f in self.viewport_3d.detector.selection_faces if f.id == fid), None)
            if face:
                selection_data.append(face)

        if not selection_data:
            logger.warning("Keine Face-Daten gefunden.")
            self._on_revolve_cancelled()
            return

        first_face = selection_data[0]

        # Revolve benötigt ein Sketch-Profil
        if not first_face.domain_type.startswith('sketch'):
            logger.warning("Revolve benötigt ein Sketch-Profil. Body-Flächen werden nicht unterstützt.")
            self._on_revolve_cancelled()
            return

        source_id = first_face.owner_id
        # WICHTIG: get_all_sketches() statt .sketches - letzteres nur für aktive Component!
        target_sketch = next((s for s in self.document.get_all_sketches() if s.id == source_id), None)
        polys = [f.shapely_poly for f in selection_data]

        if not target_sketch:
            logger.error("Sketch nicht gefunden.")
            self._on_revolve_cancelled()
            return

        # CAD KERNEL FIRST: Finde die passenden Profile in sketch.closed_profiles
        # und speichere DEREN Centroids (nicht die aus der UI-Auswahl!)
        # Das garantiert dass die Centroids beim Rebuild übereinstimmen.
        # Profile kommen NUR aus: 1) SketchEditor-Detection, 2) Laden aus Datei
        sketch_profiles = getattr(target_sketch, 'closed_profiles', [])
        profile_selector = []

        for sel_poly in polys:
            try:
                sel_centroid = sel_poly.centroid
                sel_cx, sel_cy = sel_centroid.x, sel_centroid.y
                sel_area = sel_poly.area

                # Finde das passende Profil in sketch.closed_profiles
                best_match = None
                best_dist = float('inf')

                for sketch_poly in sketch_profiles:
                    sk_centroid = sketch_poly.centroid
                    sk_cx, sk_cy = sk_centroid.x, sk_centroid.y
                    sk_area = sketch_poly.area

                    # Centroid-Distanz
                    import math
                    dist = math.hypot(sel_cx - sk_cx, sel_cy - sk_cy)

                    # Area-Check (innerhalb 20% Toleranz)
                    area_diff = abs(sel_area - sk_area) / max(sel_area, sk_area, 1)

                    if dist < best_dist and area_diff < 0.2:
                        best_dist = dist
                        best_match = (sk_cx, sk_cy)

                if best_match:
                    profile_selector.append(best_match)
                    logger.debug(f"[REVOLVE] Matched selection ({sel_cx:.2f}, {sel_cy:.2f}) → sketch ({best_match[0]:.2f}, {best_match[1]:.2f})")
                else:
                    # Kein Match gefunden - Fehler!
                    logger.error(f"[REVOLVE] No match in sketch.closed_profiles for ({sel_cx:.2f}, {sel_cy:.2f})")
                    logger.error(f"[REVOLVE] Verfügbare Profile: {[(p.centroid.x, p.centroid.y) for p in sketch_profiles]}")
            except Exception as e:
                logger.warning(f"Profile-Matching fehlgeschlagen: {e}")

        # CAD KERNEL FIRST: Wenn Auswahl getroffen aber kein Match → Abbruch!
        if polys and not profile_selector:
            logger.error(f"[REVOLVE] Matching fehlgeschlagen! {len(polys)} selektiert, 0 gematcht. Abbruch.")
            self._on_revolve_cancelled()
            return

        # Target Body bestimmen
        if operation == "New Body":
            body = self.document.new_body()
        else:
            body = self._get_active_body()
            if not body:
                body = self.document.new_body()

        feature = RevolveFeature(
            sketch=target_sketch,
            angle=angle,
            axis=axis,
            operation=operation,
            profile_selector=profile_selector,  # CAD Kernel First!
            precalculated_polys=polys,  # Nur für sketchless mode
        )

        is_new_body = (operation == "New Body")
        try:
            cmd = AddFeatureCommand(body, feature, self, description=f"Revolve ({operation})")
            self.undo_stack.push(cmd)

            # Safety check
            if hasattr(body, 'vtk_mesh') and (body.vtk_mesh is None or body.vtk_mesh.n_points == 0):
                logger.warning("Revolve ließ Body verschwinden. Undo.")
                self.undo_stack.undo()
                # Leeren Body entfernen wenn neu erstellt
                if is_new_body and body in self.document.bodies and not body.features:
                    self.document.bodies.remove(body)
            else:
                logger.success(f"Revolve erstellt: {angle}° um {axis}")
        except Exception as e:
            logger.error(f"Revolve fehlgeschlagen: {e}")
            if is_new_body and body in self.document.bodies and not body.features:
                self.document.bodies.remove(body)

        self._finish_revolve_ui()

    def _on_revolve_cancelled(self):
        """Revolve abbrechen."""
        self._finish_revolve_ui()
        self.statusBar().showMessage(tr("Revolve abgebrochen"))

    def _finish_revolve_ui(self):
        """Revolve UI aufräumen."""
        self.revolve_panel.hide()
        self.viewport_3d.set_revolve_mode(False)
        if hasattr(self.viewport_3d, 'detector'):
            self.viewport_3d.detector.clear()
        self.viewport_3d._draw_selectable_faces_from_detector()
        self.browser.refresh()
        self._update_tnp_stats()
        # ASSEMBLY FIX: Viewport komplett neu rendern damit inactive Components
        # ihre korrekte Transparenz behalten
        self._update_viewport_all_impl()

    def _on_face_selected_for_revolve(self, face_id):
        """Face-Klick im Revolve-Modus → Selektion speichern + Preview."""
        self.viewport_3d._revolve_selected_faces = list(self.viewport_3d.selected_face_ids)
        self.statusBar().showMessage(tr("Revolve: Achse wählen (X/Y/Z) und Winkel einstellen"))
        # Sofort Preview mit aktuellen Panel-Werten
        self.viewport_3d.show_revolve_preview(
            self.revolve_panel.get_angle(),
            self.revolve_panel.get_axis(),
            self.revolve_panel.get_operation()
        )

    def _extrude_dialog(self):
        """Startet den Extrude-Modus."""
        # 1. Detector leeren und füllen
        self._update_detector()

        if not self.viewport_3d.detector.selection_faces:
            logger.error("Keine geschlossenen Flächen gefunden!", 3000)
            return

        # Transform-Panel verstecken
        self._hide_transform_ui()

        # 2. Modus aktivieren
        self.viewport_3d.set_extrude_mode(True)
        self.viewport_3d.set_selection_mode("face")

        # 3. Panel anzeigen UND nach vorne bringen
        self.extrude_panel.reset()
        self.extrude_panel.setVisible(True)
        self.extrude_panel.show()
        
        # FIX PROBLEM 1: Panel Positionierung verzögern!
        # Qt braucht ein paar Millisekunden, um die Breite des Panels zu berechnen.
        # Ohne Timer ist width() oft 0 oder falsch, daher landet es oben.
        QTimer.singleShot(10, self._position_extrude_panel)
        
        logger.info("Fläche wählen und ziehen. Bestätigen mit Enter oder Rechtsklick.")

    def _on_viewport_height_changed(self, h):
        """Wird aufgerufen wenn sich die Höhe durch Maus-Drag ändert"""
        # Update das Input-Panel mit dem aktuellen Wert
        self.extrude_panel.set_height(h)
        
        # Dynamische Operation-Anpassung für Body-Faces
        self._update_operation_from_height(h)
    
    def _update_operation_from_height(self, height):
        """
        Passt die Operation dynamisch an die Extrusionsrichtung an.
        - Positive Höhe (weg von Oberfläche) = Join
        - Negative Höhe (in Oberfläche) = Cut
        """
        # Nur wenn im Extrude-Modus und Faces ausgewählt
        if not self.viewport_3d.extrude_mode:
            return
            
        if not self.viewport_3d.selected_face_ids:
            return
        
        # Prüfe ob es sich um Body-Faces handelt
        face_id = next(iter(self.viewport_3d.selected_face_ids))
        face = next((f for f in self.viewport_3d.detector.selection_faces if f.id == face_id), None)
        
        if not face:
            return
            
        # Nur für Body-Faces automatisch anpassen
        if face.domain_type.startswith('body'):
            # Body-Face: Positive Höhe = raus aus Body = Join
            #           Negative Höhe = in Body hinein = Cut
            if height >= 0:
                suggested = "Join"
            else:
                suggested = "Cut"
            
            current = self.extrude_panel.get_operation()
            if current != suggested and current in ["Join", "Cut"]:
                self.extrude_panel.set_suggested_operation(suggested)
    
    def _on_extrude_panel_height_changed(self, height):
        """Live-Vorschau wenn Wert im Panel geändert wird"""
        if hasattr(self.viewport_3d, 'show_extrude_preview'):
            operation = self.extrude_panel.get_operation()
            self.viewport_3d.extrude_operation = operation  # Sync
            self.viewport_3d.show_extrude_preview(height, operation)
    
    def _on_extrude_operation_changed(self, operation):
        """Wird aufgerufen wenn die Operation im Panel geändert wird"""
        # Operation im Viewport speichern für Drag-Farbe
        self.viewport_3d.extrude_operation = operation
        
        height = self.extrude_panel.get_height()
        if hasattr(self.viewport_3d, 'show_extrude_preview'):
            self.viewport_3d.show_extrude_preview(height, operation)
    
    def _on_to_face_requested(self):
        """User hat 'To Face' im Panel geklickt — Ziel-Pick aktivieren."""
        if not self.viewport_3d.extrude_mode:
            return
        self.viewport_3d._to_face_picking = True
        self.viewport_3d.setCursor(Qt.CrossCursor)
        self.statusBar().showMessage("Zielfläche auswählen...", 0)

    def _on_target_face_selected(self, target_face_id):
        """Ziel-Face für 'Extrude to Face' wurde gepickt."""
        height = self.viewport_3d.calculate_to_face_height(target_face_id)
        if abs(height) < 0.001:
            self.statusBar().showMessage("Zielfläche liegt auf gleicher Ebene", 3000)
            self.extrude_panel.set_to_face_mode(False)
            return

        self.extrude_panel.set_to_face_height(height)
        operation = self.extrude_panel.get_operation()
        self.viewport_3d.show_extrude_preview(height, operation)
        self.statusBar().showMessage(f"Extrude bis Fläche: {height:.2f} mm", 3000)

    def _on_face_selected_for_extrude(self, face_id):
        """
        Automatische Operation-Erkennung wenn eine Fläche ausgewählt wird.
        Auch für Shell-Mode verwendet.
        """
        # Shell-Mode hat Priorität (Phase 6)
        if getattr(self, '_shell_mode', False):
            self._on_face_selected_for_shell(face_id)
            return

        # Sweep-Profil-Phase (Phase 6)
        if getattr(self, '_sweep_mode', False) and getattr(self, '_sweep_phase', None) == 'profile':
            self._on_face_selected_for_sweep(face_id)
            return

        # Loft-Mode (Phase 6)
        if getattr(self, '_loft_mode', False):
            self._on_face_selected_for_loft(face_id)
            return

        # Revolve-Mode: Face-Pick → Preview anzeigen
        if self.viewport_3d.revolve_mode:
            self._on_face_selected_for_revolve(face_id)
            return

        if not self.viewport_3d.extrude_mode:
            return

        # Height zurücksetzen bei Face-Wechsel (verhindert Akkumulation)
        self.extrude_panel.height_input.blockSignals(True)
        self.extrude_panel._height = 0.0
        self.extrude_panel.height_input.setValue(0.0)
        self.extrude_panel.height_input.blockSignals(False)

        # Finde die selektierte Fläche
        face = next((f for f in self.viewport_3d.detector.selection_faces if f.id == face_id), None)
        if not face:
            return

        # Body-Face: Start mit "Join" (positive Extrusion = Material hinzufügen)
        # Die dynamische Anpassung erfolgt in _update_operation_from_height
        if face.domain_type.startswith('body'):
            self.extrude_panel.set_suggested_operation("Join")
            return

        # Sketch-Face: Prüfe ob auf einem Body
        if face.domain_type.startswith('sketch'):
            suggested_op = self._detect_extrude_operation(face)
            self.extrude_panel.set_suggested_operation(suggested_op)
        
    def _detect_extrude_operation(self, sketch_face) -> str:
        """
        Erkennt automatisch welche Operation sinnvoll ist.
        Returns: "New Body", "Join", oder "Cut"
        """
        # Wenn keine Bodies existieren -> New Body
        if not self.document.bodies:
            return "New Body"
        
        # Hole die Ebene der Sketch-Fläche
        face_origin = np.array(sketch_face.plane_origin)
        face_normal = np.array(sketch_face.plane_normal)
        
        # Prüfe für jeden sichtbaren Body ob die Fläche darauf liegt
        for body in self.document.bodies:
            if not self.viewport_3d.is_body_visible(body.id):
                continue
                
            mesh = self.viewport_3d.get_body_mesh(body.id)
            if mesh is None:
                continue
            
            # Prüfe ob ein Punkt der Sketch-Fläche nahe am Body ist
            # Nutze das Zentrum des Sketch-Polygons
            if sketch_face.shapely_poly:
                centroid = sketch_face.shapely_poly.centroid
                # Transformiere 2D Zentrum zu 3D
                ox, oy, oz = sketch_face.plane_origin
                ux, uy, uz = sketch_face.plane_x
                vx, vy, vz = sketch_face.plane_y
                center_3d = np.array([
                    ox + centroid.x * ux + centroid.y * vx,
                    oy + centroid.x * uy + centroid.y * vy,
                    oz + centroid.x * uz + centroid.y * vz
                ])
                
                # Finde nächsten Punkt auf dem Body
                try:
                    closest_idx = mesh.find_closest_point(center_3d)
                    closest_pt = mesh.points[closest_idx]
                    distance = np.linalg.norm(closest_pt - center_3d)
                    
                    # Wenn sehr nah (< 1mm), liegt die Fläche auf dem Body
                    if distance < 1.0:
                        # Ray-Cast in Normalenrichtung um zu prüfen ob wir "ins" Body zeigen
                        # Vereinfacht: Wenn nah, ist es wahrscheinlich Join oder Cut
                        # Positives Extrudieren = Join, Negatives = Cut
                        return "Join"  # Default: Join, User kann auf Cut wechseln
                        
                except Exception:
                    pass
        
        # Kein Body in der Nähe -> New Body
        return "New Body"
    
    def _on_extrude_confirmed(self):
        """Wird aufgerufen, wenn im Panel OK oder Enter gedrückt wurde"""
        height = self.extrude_panel.get_height()
        operation = self.extrude_panel.get_operation()
        
        # Wir übergeben None für die Indizes, da _on_extrusion_finished 
        # jetzt direkt den Detector im Viewport abfragt.
        self._on_extrusion_finished(None, height, operation)
    
    def _on_extrude_cancelled(self):
        """Extrude abgebrochen"""
        self.viewport_3d.set_extrude_mode(False)
        self.extrude_panel.setVisible(False)
        if hasattr(self.viewport_3d, 'detector'):
            self.viewport_3d.detector.clear()
        self.viewport_3d.selected_face_ids.clear()
        self.viewport_3d.hover_face_id = -1
        self.viewport_3d._draw_selectable_faces_from_detector()
        # ASSEMBLY FIX: Viewport komplett neu rendern damit inactive Components
        # ihre korrekte Transparenz behalten (statt set_all_bodies_opacity(1.0))
        self._update_viewport_all_impl()
        logger.info(tr("Extrude abgebrochen"), 2000)
    
    def _on_toggle_bodies_visibility(self, hide: bool):
        """Legacy Handler - wird von bodies_visibility_state_changed ersetzt"""
        # Wird noch für Kompatibilität aufgerufen, eigentliche Logik in _on_bodies_visibility_state_changed
        pass

    def _on_bodies_visibility_state_changed(self, state: int):
        """
        3-Stufen Visibility Toggle:
        0 = Normal (mit Component-Transparenz)
        1 = X-Ray (20% transparent)
        2 = Versteckt (komplett unsichtbar)
        """
        if state == 0:  # Normal - respektiert inactive Component Transparenz
            # ASSEMBLY FIX: Viewport komplett neu rendern damit inactive Components
            # ihre korrekte Transparenz bekommen (nicht alle auf 1.0 setzen!)
            self._update_viewport_all_impl()
        elif state == 1:  # X-Ray
            self.viewport_3d.set_all_bodies_visible(True)
            self.viewport_3d.set_all_bodies_opacity(0.2)
        else:  # state == 2: Versteckt
            self.viewport_3d.set_all_bodies_visible(False)

        # Detector aktualisieren
        if self.viewport_3d.extrude_mode:
            self._update_detector()
            self.viewport_3d._draw_selectable_faces_from_detector()

    def _update_detector(self):
        """
        Lädt ALLE sichtbaren Geometrien in den Detector.
        """
        if not hasattr(self.viewport_3d, 'detector'): return
        
        self.viewport_3d.detector.clear()
        
        # A) Sketches verarbeiten
        visible_sketches = self.browser.get_visible_sketches()

        for sketch_info in visible_sketches:
            # Backward-compatible: 2- oder 3-Tupel
            if len(sketch_info) == 3:
                sketch, visible, is_inactive = sketch_info
            else:
                sketch, visible = sketch_info

            if visible:
                x_dir = getattr(sketch, 'plane_x_dir', None)
                y_dir = getattr(sketch, 'plane_y_dir', None)
                
                # Fallback Berechnung falls Achsen fehlen (bei alten Projekten)
                if x_dir is None:
                     x_dir, y_dir = self.viewport_3d._calculate_plane_axes(sketch.plane_normal)
                
                self.viewport_3d.detector.process_sketch(
                    sketch, 
                    sketch.plane_origin, 
                    sketch.plane_normal, 
                    x_dir,
                    y_dir 
                )
        
        # B) Body-Flächen verarbeiten (NUR sichtbare!)
        # Performance Optimization Phase 2.2: Übergebe extrude_mode für Dynamic Priority
        # WICHTIG: get_all_bodies() statt .bodies - letzteres nur für aktive Component!
        extrude_mode = getattr(self.viewport_3d, 'extrude_mode', False)
        for body in self.document.get_all_bodies():
            if self.viewport_3d.is_body_visible(body.id):
                mesh = self.viewport_3d.get_body_mesh(body.id)
                if mesh:
                    # FIX: B-Rep face_info übergeben für korrekte Normalen
                    face_info = getattr(body, 'face_info', None)
                    self.viewport_3d.detector.process_body_mesh(
                        body.id, mesh, extrude_mode=extrude_mode, face_info=face_info
                    )

        count = len(self.viewport_3d.detector.selection_faces)
        if count == 0:
            logger.warning("Keine geschlossenen Flächen erkannt!")
    
    def _get_plane_from_sketch(self, sketch):
        """Erstellt ein build123d Plane Objekt aus den Sketch-Metadaten"""
        from build123d import Plane, Vector
        return Plane(
            origin=Vector(sketch.plane_origin),
            z_dir=Vector(sketch.plane_normal),
            x_dir=Vector(sketch.plane_x_dir)
        )
    
    def _on_extrusion_finished(self, face_indices, height, operation="New Body"):
        """
        Erstellt die finale Geometrie.
        FIX V2: Robustes Targeting. Verhindert "Cut All" Katastrophen.
        Wählt IMMER nur einen Ziel-Körper aus (den passendsten), anstatt alle zu schneiden.
        """
        
        # Debounce
        if getattr(self, '_is_processing_extrusion', False):
            return
        self._is_processing_extrusion = True

        try:
            # 1. Daten sammeln
            # Nutze face_indices aus dem Signal wenn vorhanden, sonst selected_face_ids
            face_ids = face_indices if face_indices else list(self.viewport_3d.selected_face_ids)

            selection_data = []
            for fid in face_ids:
                face = next((f for f in self.viewport_3d.detector.selection_faces if f.id == fid), None)
                if face: selection_data.append(face)

            if not selection_data:
                logger.warning(tr("Nichts selektiert."))
                return

            first_face = selection_data[0]

            # Fall A: Sketch-Extrusion
            if first_face.domain_type.startswith('sketch'):
                try:
                    source_id = first_face.owner_id
                    # WICHTIG: get_all_sketches() statt .sketches - letzteres nur für aktive Component!
                    target_sketch = next((s for s in self.document.get_all_sketches() if s.id == source_id), None)
                    polys = [f.shapely_poly for f in selection_data]

                    # --- TARGETING LOGIK (STRIKT) ---
                    target_bodies = []
                    
                    # 1. User hat explizit einen Body im Browser selektiert?
                    active_body = self._get_active_body()
                    browser_selection = self.browser.tree.selectedItems()
                    has_explicit_selection = len(browser_selection) > 0

                    if operation == "New Body":
                        # Immer neuer Körper
                        target_bodies = [self.document.new_body()]
                        
                    elif has_explicit_selection and active_body:
                        # Explizite Wahl gewinnt immer
                        target_bodies = [active_body]
                        
                    else:
                        # AUTO-DETECTION
                        # ✅ FIX: Operation-aware targeting
                        # - Join: Use parent body (adding to same body)
                        # - Cut: Use intersecting body (cutting whatever the volume hits)

                        if operation == "Join":
                            # Join sollte den Parent-Body nutzen (Material hinzufügen)
                            if hasattr(target_sketch, 'parent_body_id') and target_sketch.parent_body_id:
                                # WICHTIG: find_body_by_id durchsucht alle Components!
                                parent_body = self.document.find_body_by_id(target_sketch.parent_body_id)
                                if parent_body:
                                    target_bodies = [parent_body]
                                    logger.info(f"🎯 Join: Nutze Parent-Body '{parent_body.name}'")

                        # Für Cut/Intersect: Finde Body der mit Extrusion-Volumen überlappt
                        if not target_bodies:
                            priority_body = self._find_body_closest_to_sketch(target_sketch, selection_data)

                            if priority_body:
                                target_bodies = [priority_body]
                                logger.info(f"🎯 Auto-Target: Nutze nächsten Body '{priority_body.name}' (Proximity)")
                            else:
                                # Fallback: Wenn wir wirklich nichts finden (z.B. Skizze weit im Raum),
                                # nehmen wir bei Join/Cut lieber den letzten Körper als gar keinen oder alle.
                                # WICHTIG: get_all_bodies() statt .bodies - letzteres nur für aktive Component!
                                all_bodies = self.document.get_all_bodies()
                                if all_bodies and operation != "New Body":
                                    target_bodies = [all_bodies[-1]]
                                    logger.info(f"⚠️ Targeting Fallback: Nutze '{target_bodies[0].name}'")

                    if not target_bodies and operation == "Cut":
                         logger.warning("Kein Ziel-Körper gefunden. Bitte Körper im Browser auswählen.")
                         return

                    # --- FEATURE ANWENDEN ---
                    success_count = 0
                    from modeling import ExtrudeFeature
                    from gui.commands.feature_commands import AddFeatureCommand

                    # CAD KERNEL FIRST: Finde die passenden Profile in sketch.closed_profiles
                    # und speichere DEREN Centroids (nicht die aus der UI-Auswahl!)
                    # Das garantiert dass die Centroids beim Rebuild übereinstimmen.
                    # Profile kommen NUR aus: 1) SketchEditor-Detection, 2) Laden aus Datei
                    sketch_profiles = getattr(target_sketch, 'closed_profiles', [])
                    profile_selector = []

                    for sel_poly in polys:
                        try:
                            sel_centroid = sel_poly.centroid
                            sel_cx, sel_cy = sel_centroid.x, sel_centroid.y
                            sel_area = sel_poly.area

                            # Finde das passende Profil in sketch.closed_profiles
                            best_match = None
                            best_dist = float('inf')

                            for sketch_poly in sketch_profiles:
                                sk_centroid = sketch_poly.centroid
                                sk_cx, sk_cy = sk_centroid.x, sk_centroid.y
                                sk_area = sketch_poly.area

                                # Centroid-Distanz
                                import math
                                dist = math.hypot(sel_cx - sk_cx, sel_cy - sk_cy)

                                # Area-Check (innerhalb 20% Toleranz)
                                area_diff = abs(sel_area - sk_area) / max(sel_area, sk_area, 1)

                                if dist < best_dist and area_diff < 0.2:
                                    best_dist = dist
                                    best_match = (sk_cx, sk_cy)

                            if best_match:
                                profile_selector.append(best_match)
                                logger.debug(f"[EXTRUDE] Matched selection ({sel_cx:.2f}, {sel_cy:.2f}) → sketch ({best_match[0]:.2f}, {best_match[1]:.2f})")
                            else:
                                # Kein Match gefunden - Fehler!
                                logger.error(f"[EXTRUDE] No match in sketch.closed_profiles for ({sel_cx:.2f}, {sel_cy:.2f})")
                                logger.error(f"[EXTRUDE] Verfügbare Profile: {[(p.centroid.x, p.centroid.y) for p in sketch_profiles]}")
                        except Exception as e:
                            logger.warning(f"Profile-Matching fehlgeschlagen: {e}")

                    # CAD KERNEL FIRST: Wenn Auswahl getroffen aber kein Match → Abbruch!
                    if polys and not profile_selector:
                        logger.error(f"[EXTRUDE] Matching fehlgeschlagen! {len(polys)} selektiert, 0 gematcht. Abbruch.")
                        self._on_extrude_cancelled()
                        return

                    for body in target_bodies:
                        feature = ExtrudeFeature(
                            sketch=target_sketch,
                            distance=height,
                            operation=operation,
                            profile_selector=profile_selector,  # CAD Kernel First!
                            precalculated_polys=polys,  # Nur für Push/Pull (sketchless)
                            plane_origin=getattr(target_sketch, 'plane_origin', (0, 0, 0)),
                            plane_normal=getattr(target_sketch, 'plane_normal', (0, 0, 1)),
                            plane_x_dir=getattr(target_sketch, 'plane_x_dir', None),
                            plane_y_dir=getattr(target_sketch, 'plane_y_dir', None),
                        )
                        
                        # Initialen Profile-Hash setzen für Performance-Optimierung
                        # (verhindert unnötige Rebuilds wenn sich der Sketch ändert)
                        feature._profile_hash = self._compute_profile_hash(feature, target_sketch)

                        try:
                            cmd = AddFeatureCommand(
                                body, feature, self,
                                description=f"Extrude ({operation})"
                            )
                            self.undo_stack.push(cmd)  
                            
                            # Safety Check: Hat die Operation den Body zerstört?
                            if hasattr(body, 'vtk_mesh') and (body.vtk_mesh is None or body.vtk_mesh.n_points == 0):
                                logger.warning(f"Operation ließ Body '{body.name}' verschwinden (Invalid Result). Undo.")
                                self.undo_stack.undo()
                            else:
                                success_count += 1

                        except Exception as e:
                            logger.warning(f"Operation an {body.name} fehlgeschlagen: {e}")

                    if success_count > 0:
                        self._finish_extrusion_ui(msg=f"Extrusion ({operation}) auf '{target_bodies[0].name}' angewendet.")
                    else:
                        logger.warning("Operation hatte keinen Effekt.")

                except Exception as e:
                    logger.error(f"Sketch Extrude Error: {e}")
                    import traceback
                    traceback.print_exc()

            # Fall B: Body-Face Extrusion (Push/Pull)
            elif first_face.domain_type == 'body_face':
                # WICHTIG: sample_point statt plane_origin für B-Rep Matching!
                # Bei Ring-Flächen liegt plane_origin im Loch, sample_point auf der Fläche
                matching_point = getattr(first_face, 'sample_point', None) or first_face.plane_origin
                success = self._extrude_body_face_build123d({
                    'body_id': first_face.owner_id,
                    'center_3d': matching_point,
                    'normal': first_face.plane_normal,
                    'ocp_face_id': getattr(first_face, 'ocp_face_id', None)  # Exakte Face-ID!
                }, height, operation)
                
                if success:
                    self._finish_extrusion_ui(msg="Push/Pull erfolgreich.")
                else:
                    logger.error("Push/Pull fehlgeschlagen.")
        
        finally:
            self._is_processing_extrusion = False

    def _find_body_closest_to_sketch(self, sketch, faces):
        """
        Hilfsfunktion: Findet den Body, der der Skizze am nächsten ist.
        FIX: Nutzt 'representative_point' statt Centroid für bessere Erkennung bei Ringen.
        """
        if not self.document.bodies: return None
        
        try:
            face = faces[0]
            
            # Punkt AUF der Fläche finden (nicht Loch-Mitte!)
            if face.shapely_poly:
                # representative_point() garantiert einen Punkt INNERHALB des Polygons
                # (wichtig bei Ringen/Donuts, wo centroid im Loch liegt)
                pt2d = face.shapely_poly.representative_point()
                
                ox, oy, oz = sketch.plane_origin
                ux, uy, uz = sketch.plane_x_dir if hasattr(sketch, 'plane_x_dir') and sketch.plane_x_dir else (1,0,0)
                vx, vy, vz = sketch.plane_y_dir if hasattr(sketch, 'plane_y_dir') and sketch.plane_y_dir else (0,1,0)
                
                p_sketch = np.array([
                    ox + pt2d.x * ux + pt2d.y * vx,
                    oy + pt2d.x * uy + pt2d.y * vy,
                    oz + pt2d.x * uz + pt2d.y * vz
                ])
            else:
                p_sketch = np.array(face.plane_origin)
            
            best_body = None
            min_dist = float('inf')
            
            # Suche den absolut nächsten Body (ohne strenges 1mm Limit)
            for body in self.document.bodies:
                if not self.viewport_3d.is_body_visible(body.id): continue
                
                mesh = self.viewport_3d.get_body_mesh(body.id)
                if mesh and mesh.n_points > 0:
                    idx = mesh.find_closest_point(p_sketch)
                    closest = np.array(mesh.points[idx])
                    dist = np.linalg.norm(closest - p_sketch)
                    
                    if dist < min_dist:
                        min_dist = dist
                        best_body = body
            
            # Wenn wir einen Body gefunden haben, der halbwegs nah ist (< 50mm), nehmen wir ihn.
            # Das ist besser als gar nichts zu finden.
            if best_body and min_dist < 50.0:
                return best_body
                
        except Exception as e:
            logger.debug(f"Smart Target Error: {e}")
            
        return None

    def _finish_extrusion_ui(self, success=True, msg=""):
        """Hilfsfunktion zum Aufräumen der UI"""
        self.extrude_panel.setVisible(False)
        self.viewport_3d.set_extrude_mode(False)

        # FIX: Detector mit aktuellen Body-Meshes neu laden (nicht nur leeren!)
        # Sonst sind nach Push/Pull keine SelectionFaces mehr verfügbar
        if hasattr(self.viewport_3d, '_update_detector_for_picking'):
            self.viewport_3d._update_detector_for_picking()
        elif hasattr(self.viewport_3d, 'detector'):
            self.viewport_3d.detector.clear()

        self.viewport_3d.selected_face_ids.clear()
        self.viewport_3d.hover_face_id = -1
        self.viewport_3d._draw_selectable_faces_from_detector()

        if success:
            self.browser.refresh()
            # TNP Statistiken aktualisieren
            self._update_tnp_stats()
            # Keine logger.success() mehr - Operation Summary Widget zeigt die Info

        # ASSEMBLY FIX: Viewport komplett neu rendern damit inactive Components
        # ihre korrekte Transparenz behalten (statt set_all_bodies_opacity(1.0))
        self._update_viewport_all_impl()


    def _extract_face_as_polygon(self, face):
        """
        Extrahiert die Flächen-Kontur als Shapely Polygon MIT Löchern.

        Dies ermöglicht es, Push/Pull als PARAMETRISCHES Feature zu speichern,
        das beim Rebuild rekonstruiert werden kann.

        Returns:
            (polygon, plane_origin, plane_normal, plane_x_dir, plane_y_dir) oder (None, None, None, None, None)
        """
        try:
            from shapely.geometry import Polygon as ShapelyPolygon
            from OCP.BRep import BRep_Tool
            from OCP.BRepTools import BRepTools_WireExplorer
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_WIRE, TopAbs_EDGE
            from OCP.gp import gp_Pnt, gp_Vec
            from OCP.TopoDS import TopoDS
            from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
            from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere
            from OCP.BRep import BRep_Tool as BRT
            from OCP.TopAbs import TopAbs_REVERSED
            import numpy as np

            # 0. Prüfe Flächentyp - nur planare Flächen können sauber zu 2D Polygon werden
            surface_adaptor = BRepAdaptor_Surface(face.wrapped)
            surface_type = surface_adaptor.GetType()

            surface_type_names = {
                GeomAbs_Plane: "Plane",
                GeomAbs_Cylinder: "Cylinder",
                GeomAbs_Cone: "Cone",
                GeomAbs_Sphere: "Sphere",
            }
            type_name = surface_type_names.get(surface_type, f"Other({surface_type})")

            if surface_type != GeomAbs_Plane:
                logger.info(f"Face ist {type_name} - Polygon-Extraktion nicht möglich (nur für Planes)")
                return None, None, None, None, None

            # 1. Hole Face-Surface für Koordinatentransformation
            surface = BRep_Tool.Surface_s(face.wrapped)

            # 2. Hole Face-Normale und Origin
            from OCP.BRepGProp import BRepGProp_Face
            prop = BRepGProp_Face(face.wrapped)

            # Finde UV-Zentrum
            umin, umax, vmin, vmax = BRep_Tool.Surface_s(face.wrapped).Bounds()
            u_mid = (umin + umax) / 2
            v_mid = (vmin + vmax) / 2

            # Berechne Punkt und Normale am Zentrum
            pnt = gp_Pnt()
            normal_vec = gp_Vec()
            prop.Normal(u_mid, v_mid, pnt, normal_vec)

            plane_origin = (pnt.X(), pnt.Y(), pnt.Z())
            plane_normal = (normal_vec.X(), normal_vec.Y(), normal_vec.Z())

            # X-Richtung: Eine Tangente zur Fläche
            d1u = gp_Vec()
            d1v = gp_Vec()
            surface.D1(u_mid, v_mid, pnt, d1u, d1v)
            d1u.Normalize()
            plane_x_dir = (d1u.X(), d1u.Y(), d1u.Z())

            # 3. Koordinatensystem vorbereiten
            origin = np.array(plane_origin)
            normal = np.array(plane_normal)
            x_dir = np.array(plane_x_dir)

            # WICHTIG: Normalisieren!
            normal_len = np.linalg.norm(normal)
            x_len = np.linalg.norm(x_dir)

            if normal_len < 1e-10 or x_len < 1e-10:
                logger.warning(f"Degeneriertes Koordinatensystem: normal_len={normal_len}, x_len={x_len}")
                return None, None, None, None, None

            normal = normal / normal_len
            x_dir = x_dir / x_len
            y_dir = np.cross(normal, x_dir)
            y_len = np.linalg.norm(y_dir)

            if y_len < 1e-10:
                logger.warning(f"Degenerierte Y-Achse (normal und x_dir parallel?)")
                return None, None, None, None, None

            y_dir = y_dir / y_len

            # KRITISCH: plane_normal muss normalisiert zurückgegeben werden!
            plane_normal = tuple(normal.tolist())
            plane_x_dir = tuple(x_dir.tolist())

            def _add_unique(pt_list, new_pt, tol=1e-8):
                """Fügt Punkt hinzu, wenn er nicht fast-identisch mit dem letzten ist."""
                if not pt_list or sum((a-b)**2 for a, b in zip(pt_list[-1], new_pt)) > tol:
                    pt_list.append(new_pt)

            def _extract_wire_points_2d(wire):
                """Extrahiert 2D-Punkte aus einem Wire."""
                points_3d = []
                edge_exp = BRepTools_WireExplorer(wire)

                while edge_exp.More():
                    edge = edge_exp.Current()
                    vertex = edge_exp.CurrentVertex()

                    try:
                        adaptor = BRepAdaptor_Curve(edge)

                        if adaptor.GetType() == GeomAbs_Line:
                            vpt = BRT.Pnt_s(vertex)
                            _add_unique(points_3d, (vpt.X(), vpt.Y(), vpt.Z()))
                        else:
                            reversed_edge = edge.Orientation() == TopAbs_REVERSED
                            first = adaptor.FirstParameter()
                            last = adaptor.LastParameter()
                            n_samples = 10
                            for i in range(n_samples):
                                if reversed_edge:
                                    t = last - (last - first) * i / n_samples
                                else:
                                    t = first + (last - first) * i / n_samples
                                pt = adaptor.Value(t)
                                _add_unique(points_3d, (pt.X(), pt.Y(), pt.Z()))

                    except Exception as edge_err:
                        logger.debug(f"Edge-Sampling fehlgeschlagen: {edge_err}")

                    edge_exp.Next()

                # Letzten Punkt entfernen falls Ringschluss
                if len(points_3d) > 2:
                    if sum((a-b)**2 for a, b in zip(points_3d[-1], points_3d[0])) < 1e-8:
                        points_3d.pop()

                # Transformiere 3D -> 2D
                points_2d = []
                for p3d in points_3d:
                    p = np.array(p3d) - origin
                    x = np.dot(p, x_dir)
                    y = np.dot(p, y_dir)
                    new_2d = (x, y)
                    if not points_2d or (points_2d[-1][0] - new_2d[0])**2 + (points_2d[-1][1] - new_2d[1])**2 > 1e-10:
                        points_2d.append(new_2d)

                if len(points_2d) > 2 and (points_2d[-1][0] - points_2d[0][0])**2 + (points_2d[-1][1] - points_2d[0][1])**2 < 1e-10:
                    points_2d.pop()

                # Debug: Zeige 3D→2D Transformation
                if len(points_3d) > 0:
                    logger.trace(f"  Wire: {len(points_3d)} 3D pts → {len(points_2d)} 2D pts")
                    if len(points_3d) <= 5:
                        for i, (p3, p2) in enumerate(zip(points_3d[:5], points_2d[:5])):
                            logger.trace(f"    [{i}] 3D={p3} → 2D={p2}")

                return points_2d

            # 4. Alle Wires extrahieren (outer + inner holes)
            wire_exp = TopExp_Explorer(face.wrapped, TopAbs_WIRE)
            if not wire_exp.More():
                logger.warning("Face hat keinen Wire")
                return None, None, None, None, None

            all_rings_2d = []
            while wire_exp.More():
                wire_shape = wire_exp.Current()
                wire = TopoDS.Wire_s(wire_shape)
                pts_2d = _extract_wire_points_2d(wire)
                if len(pts_2d) >= 3:
                    all_rings_2d.append(pts_2d)
                wire_exp.Next()

            if not all_rings_2d:
                logger.warning("Keine gültigen Wires extrahiert")
                return None, None, None, None, None

            logger.info(f"Face hat {len(all_rings_2d)} Wire(s) - {len(all_rings_2d)-1} Löcher")

            # 5. Erstelle Shapely Polygon mit Holes
            try:
                from shapely.geometry import LinearRing

                # Erster Wire = Outer, Rest = Holes
                exterior = all_rings_2d[0]
                holes = all_rings_2d[1:] if len(all_rings_2d) > 1 else None

                polygon = ShapelyPolygon(exterior, holes)

                if not polygon.is_valid:
                    from shapely.validation import make_valid
                    repaired = make_valid(polygon)
                    if repaired.geom_type == 'Polygon':
                        polygon = repaired
                    elif repaired.geom_type in ('MultiPolygon', 'GeometryCollection'):
                        polys = [g for g in repaired.geoms if g.geom_type == 'Polygon']
                        if polys:
                            polygon = max(polys, key=lambda p: p.area)
                        else:
                            polygon = ShapelyPolygon(exterior).buffer(0)

                plane_y_dir = tuple(y_dir.tolist())

                # Detailliertes Logging für Debugging
                logger.debug(f"  Koordinatensystem bei Extraktion:")
                logger.debug(f"    origin={plane_origin}")
                logger.debug(f"    x_dir={plane_x_dir}")
                logger.debug(f"    y_dir={plane_y_dir}")
                logger.debug(f"    normal={plane_normal}")

                # Polygon-Validierung
                n_interiors = len(list(polygon.interiors)) if hasattr(polygon, 'interiors') else 0
                poly_area = polygon.area

                if poly_area < 1e-6:
                    # Analysiere warum Fläche 0 ist
                    logger.warning(f"⚠️ Polygon hat Area≈0! Analysiere...")
                    if len(exterior) >= 3:
                        # Zeige erste/letzte Punkte
                        logger.warning(f"  Erste 3 Punkte: {exterior[:3]}")
                        logger.warning(f"  Letzte 3 Punkte: {exterior[-3:]}")
                        # Prüfe Bounding Box
                        xs = [p[0] for p in exterior]
                        ys = [p[1] for p in exterior]
                        dx = max(xs) - min(xs)
                        dy = max(ys) - min(ys)
                        logger.warning(f"  2D BBox: dx={dx:.4f}, dy={dy:.4f}")
                        if dx < 1e-6 or dy < 1e-6:
                            logger.warning(f"  → Polygon ist quasi-linear (alle Punkte auf einer Linie)!")

                logger.info(f"✅ Face-Polygon extrahiert: {len(exterior)} Punkte, {n_interiors} Löcher, Area={poly_area:.1f}")
                return polygon, plane_origin, plane_normal, plane_x_dir, plane_y_dir

            except Exception as poly_err:
                logger.warning(f"Polygon-Erstellung fehlgeschlagen: {poly_err}")
                return None, None, None, None, None

        except Exception as e:
            logger.warning(f"Face-Extraktion fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return None, None, None, None, None

    def _extrude_body_face_build123d(self, face_data, height, operation):
        """
        Version 5.0: PARAMETRISCHES Push/Pull!

        Statt nur das Solid direkt zu modifizieren, erstellen wir jetzt ein
        echtes ExtrudeFeature mit der Flächen-Kontur als precalculated_polys.

        Das Feature kann dann beim Rebuild rekonstruiert werden!
        """
        try:
            # 1. Source Body finden (der, dem die Fläche gehört)
            source_body_id = face_data.get('body_id')
            source_body = next((b for b in self.document.bodies if b.id == source_body_id), None)

            if not source_body or not hasattr(source_body, '_build123d_solid') or source_body._build123d_solid is None:
                logger.error(f"Fehler: Body oder BREP-Daten fehlen.")
                return False

            from build123d import Vector, extrude, Shape, Compound
            from OCP.BRepExtrema import BRepExtrema_DistShapeShape
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
            from OCP.TopExp import TopExp_Explorer
            from OCP.gp import gp_Pnt
            from modeling.geometric_selector import GeometricFaceSelector
            from modeling.topology_indexing import face_from_index, face_index_of, iter_faces_with_indices
            import numpy as np

            # --- SCHRITT A: Face finden (Robuste Logik wie zuvor) ---
            b3d_obj = source_body._build123d_solid
            candidate_faces = b3d_obj.faces()

            if not candidate_faces:
                candidate_faces = [face for _, face in iter_faces_with_indices(b3d_obj)]

            mesh_center = Vector(face_data['center_3d'])
            ocp_pt_vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(mesh_center.X, mesh_center.Y, mesh_center.Z)).Vertex()

            # Normale aus face_data für korrektes Matching
            expected_normal = face_data.get('normal')
            expected_normal_vec = None
            use_normal = False
            if expected_normal:
                n_arr = np.array(expected_normal, dtype=float)
                n_len = np.linalg.norm(n_arr)
                if n_len > 0.1:
                    expected_normal_vec = n_arr / n_len  # Normalisieren
                    expected_normal = expected_normal_vec
                    use_normal = True
                    logger.debug(f"Face-Suche: Normale=({expected_normal[0]:.2f}, {expected_normal[1]:.2f}, {expected_normal[2]:.2f})")

            # Face-Suche: BREP-Face mit passender Normale UND nächster Distanz finden
            best_face = None
            best_face_index = None
            best_dist = float('inf')

            # === NEU: DIREKTE FACE-SUCHE via ocp_face_id ===
            ocp_face_id = face_data.get('ocp_face_id')
            if ocp_face_id is not None:
                resolved = face_from_index(b3d_obj, int(ocp_face_id))
                if resolved is not None:
                    best_face = resolved
                    best_face_index = int(ocp_face_id)
                    best_dist = 0.0  # Exakter Match!
                    logger.info(f"Face direkt via ocp_face_id={ocp_face_id} gefunden")

            # Fallback: Distanz-basierte Suche (nur wenn ocp_face_id nicht gefunden)
            if best_face is None:
                # Fallback: Falls kein Normal-Match, bestes per Distanz
                fallback_face = None
                fallback_dist = float('inf')

                logger.debug(f"Face-Suche: mesh_center=({mesh_center.X:.2f}, {mesh_center.Y:.2f}, {mesh_center.Z:.2f}), {len(candidate_faces)} Kandidaten")

                for f in candidate_faces:
                    try:
                        extrema = BRepExtrema_DistShapeShape(ocp_pt_vertex, f.wrapped)
                        if extrema.IsDone():
                            dist = extrema.Value()

                            # Fallback tracken (für den Fall dass Normal-Match fehlschlägt)
                            if dist < fallback_dist:
                                fallback_dist = dist
                                fallback_face = f

                            # Normal-Matching wenn Normale verfügbar
                            if use_normal:
                                f_center = f.center()
                                f_normal = f.normal_at(f_center)
                                import numpy as np
                                dot = np.dot(expected_normal, [f_normal.X, f_normal.Y, f_normal.Z])
                                # FIX: abs(dot) erlaubt invertierte Normalen (z.B. bei Z-Faces)
                                if abs(dot) > 0.7 and dist < best_dist:
                                    best_dist = dist
                                    best_face = f
                            else:
                                # Ohne Normale: nur Distanz
                                if dist < best_dist:
                                    best_dist = dist
                                    best_face = f
                    except Exception as ex:
                        logger.debug(f"Face-Distanz-Fehler: {ex}")

                # Fallback wenn Normal-Match nichts gefunden hat
                if best_face is None and fallback_face is not None:
                    logger.warning(f"Normal-Match fehlgeschlagen, nutze Distanz-Fallback")
                    best_face = fallback_face
                    best_dist = fallback_dist

            # Dynamischer Schwellenwert basierend auf Body-Bounding-Box-Diagonale
            try:
                bb = b3d_obj.bounding_box()
                import numpy as np
                diag = np.sqrt((bb.max.X - bb.min.X)**2 + (bb.max.Y - bb.min.Y)**2 + (bb.max.Z - bb.min.Z)**2)
                FACE_DISTANCE_THRESHOLD = max(10.0, diag * 0.25)
            except Exception:
                FACE_DISTANCE_THRESHOLD = 25.0

            if best_face is None:
                logger.error(f"FEHLER: Keine Fläche gefunden! ({len(candidate_faces)} Kandidaten geprüft)")
                return False

            if best_dist > FACE_DISTANCE_THRESHOLD:
                logger.error(f"FEHLER: Nächste Fläche zu weit entfernt (dist={best_dist:.2f} > {FACE_DISTANCE_THRESHOLD:.1f})")
                logger.debug(f"  mesh_center: ({mesh_center.X:.2f}, {mesh_center.Y:.2f}, {mesh_center.Z:.2f})")
                return False

            logger.info(f"Face gefunden: dist={best_dist:.3f}")

            if best_face_index is None:
                try:
                    best_face_index = face_index_of(b3d_obj, best_face)
                except Exception as idx_e:
                    logger.debug(f"Face-Index-Auflösung fehlgeschlagen: {idx_e}")
            if best_face_index is not None:
                best_face_index = int(best_face_index)

            has_primary_face_ref = best_face_index is not None

            # Geometric selector nur als Legacy-Recovery mitschreiben.
            face_selector_dict = None
            if not has_primary_face_ref:
                try:
                    face_selector = GeometricFaceSelector.from_face(best_face)
                    face_selector_dict = face_selector.to_dict()
                    if is_enabled("tnp_debug_logging"):
                        logger.debug(f"TNP Legacy-Fallback: GeometricFaceSelector erstellt: center={face_selector.center}")
                except Exception as sel_e:
                    if is_enabled("tnp_debug_logging"):
                        logger.warning(f"TNP Legacy-Fallback: Konnte GeometricFaceSelector nicht erstellen: {sel_e}")

            # DEBUG: Prüfe Wire-Struktur des gefundenen Faces
            try:
                from OCP.TopAbs import TopAbs_WIRE
                wire_count = 0
                wire_exp = TopExp_Explorer(best_face.wrapped, TopAbs_WIRE)
                while wire_exp.More():
                    wire_count += 1
                    wire_exp.Next()
                logger.info(f"Face hat {wire_count} Wire(s) (1=outer only, >1=mit Löchern)")
            except Exception as wire_err:
                logger.debug(f"Wire-Count fehlgeschlagen: {wire_err}")

            # NOTE: Height-Inversion basierend auf Mesh vs B-Rep Normale wurde entfernt.
            # Das Face wird jetzt direkt via ocp_face_id gefunden, und die Preview-Logik
            # berechnet height bereits korrekt basierend auf der Drag-Richtung.

            # Bestimme eine orientierte Face-Normale (Selection-Info bevorzugt)
            face_center = best_face.center()
            face_normal_vec = None
            if expected_normal_vec is not None:
                face_normal_vec = np.array(expected_normal_vec, dtype=float)
            else:
                f_normal = best_face.normal_at(face_center)
                face_normal_vec = np.array([f_normal.X, f_normal.Y, f_normal.Z], dtype=float)
                try:
                    from OCP.TopAbs import TopAbs_REVERSED
                    if best_face.wrapped.Orientation() == TopAbs_REVERSED:
                        face_normal_vec = -face_normal_vec
                except Exception:
                    pass

            n_len = np.linalg.norm(face_normal_vec)
            if n_len < 1e-6:
                face_normal_vec = np.array([0.0, 0.0, 1.0], dtype=float)
            else:
                face_normal_vec = face_normal_vec / n_len

            # --- SCHRITT B: Face-Kontur als Polygon extrahieren ---
            # Versuche Polygon zu extrahieren für parametrische Speicherung
            # Bei Fehlschlag: Extrusion läuft trotzdem, aber weniger parametrisch
            polygon, plane_origin, plane_normal, plane_x_dir, plane_y_dir = self._extract_face_as_polygon(best_face)

            # Face als BREP für Rebuild speichern (für nicht-planare Flächen)
            face_brep_str = None
            face_type_str = None

            if polygon is None:
                # Kein Problem für BRepFeat - das arbeitet direkt mit der Face
                logger.debug("Polygon-Extraktion nicht möglich - BRepFeat nutzt Face direkt")
                # Fallback: Nutze Face-Center und Normal als Referenz
                plane_origin = (face_center.X, face_center.Y, face_center.Z)
                plane_normal = (float(face_normal_vec[0]), float(face_normal_vec[1]), float(face_normal_vec[2]))

                # Face als BREP serialisieren für Rebuild!
                try:
                    from OCP.BRepTools import BRepTools
                    from OCP.BRepAdaptor import BRepAdaptor_Surface
                    from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere
                    import tempfile
                    import os

                    # Face-Typ ermitteln
                    adaptor = BRepAdaptor_Surface(best_face.wrapped)
                    surf_type = adaptor.GetType()
                    type_map = {
                        GeomAbs_Plane: "plane",
                        GeomAbs_Cylinder: "cylinder",
                        GeomAbs_Cone: "cone",
                        GeomAbs_Sphere: "sphere",
                    }
                    face_type_str = type_map.get(surf_type, "other")

                    # BREP in temporäre Datei schreiben und lesen
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.brep', delete=False) as f:
                        temp_path = f.name
                    BRepTools.Write_s(best_face.wrapped, temp_path)
                    with open(temp_path, 'r') as f:
                        face_brep_str = f.read()
                    os.unlink(temp_path)

                    logger.debug(f"Face als BREP gespeichert: type={face_type_str}, size={len(face_brep_str)} bytes")
                except Exception as brep_err:
                    logger.warning(f"Face BREP-Serialisierung fehlgeschlagen: {brep_err}")

            # Extrusions-Werkzeug erstellen
            # FÜR JOIN: BRepFeat_MakePrism (lokale Op, KEINE neuen Nähte - erhält Zylinder!)
            # FÜR ANDERE: BRepPrimAPI_MakePrism + Boolean

            from OCP.gp import gp_Vec, gp_Dir
            from build123d import Solid

            # Extrusionsrichtung bestimmen
            direction_vec = np.array(face_normal_vec, dtype=float)
            if operation == "Cut":
                direction_vec = -direction_vec
            elif operation not in ("Join", "Cut") and height < 0:
                direction_vec = -direction_vec

            abs_height = abs(height)

            new_geo = None

            # === METHODE 1: BRepFeat_MakePrism für Join UND Cut (BEVORZUGT - lokale Op!) ===
            # BRepFeat ist robuster bei konvertierten Mesh-Bodies und erzeugt keine Nähte
            if operation in ("Join", "Cut"):
                try:
                    from OCP.BRepFeat import BRepFeat_MakePrism

                    # direction_vec berücksichtigt Operation (Join/Cut) bereits
                    # fuse_mode: 1=Fuse (Join), 0=Cut
                    if operation == "Join":
                        direction = gp_Dir(float(direction_vec[0]), float(direction_vec[1]), float(direction_vec[2]))
                        fuse_mode = 1
                    else:  # Cut
                        direction = gp_Dir(float(direction_vec[0]), float(direction_vec[1]), float(direction_vec[2]))
                        fuse_mode = 0

                    logger.debug(f"BRepFeat_MakePrism: direction=({direction_vec[0]:.3f}, {direction_vec[1]:.3f}, {direction_vec[2]:.3f}), fuse_mode={fuse_mode}, height={abs_height}")

                    prism = BRepFeat_MakePrism()
                    prism.Init(
                        source_body._build123d_solid.wrapped,  # Base shape
                        best_face.wrapped,                      # Profile face
                        best_face.wrapped,                      # Sketch face (same)
                        direction,                              # Direction
                        fuse_mode,                              # Fuse mode
                        False                                   # Modify (False = copy)
                    )
                    prism.Perform(abs_height)

                    is_done = prism.IsDone()
                    logger.debug(f"BRepFeat_MakePrism.IsDone() = {is_done}")

                    if is_done:
                        # WICHTIG: Pre-USD Result für History-Tracking aufheben!
                        # UnifySameDomain zerstört die Topologie, auf die die
                        # BRepFeat-History verweist.
                        pre_usd_result_shape = prism.Shape()
                        result_shape = pre_usd_result_shape

                        # UnifySameDomain anwenden um koplanare Faces zu vereinen
                        # (BRepFeat erstellt eine Kante zwischen alter und neuer Geometrie)
                        try:
                            from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
                            upgrader = ShapeUpgrade_UnifySameDomain(result_shape, True, True, True)
                            upgrader.SetLinearTolerance(0.01)   # 0.01mm
                            upgrader.SetAngularTolerance(0.01)  # ~0.5°
                            upgrader.Build()
                            unified_shape = upgrader.Shape()
                            if unified_shape and not unified_shape.IsNull():
                                result_shape = unified_shape
                                logger.debug("BRepFeat: UnifySameDomain angewendet")
                        except Exception as unify_err:
                            logger.debug(f"BRepFeat UnifySameDomain: {unify_err}")

                        new_solid = Solid(result_shape)

                        is_valid = new_solid.is_valid()
                        volume = new_solid.volume
                        original_volume = source_body._build123d_solid.volume
                        logger.debug(f"BRepFeat result: is_valid={is_valid}, volume={volume:.2f} (original={original_volume:.2f})")

                        # FIX: Prüfe auf gültiges Ergebnis
                        # - Volume muss positiv sein (negative = inside-out)
                        # - Bei Cut: Volume muss kleiner sein als original (sonst hat Cut nicht funktioniert)
                        volume_valid = volume > 0.001  # > 0.001 mm³
                        if operation == "Cut":
                            volume_valid = volume_valid and volume < original_volume - 0.01

                        if is_valid and volume_valid:
                            # ERFOLG! Direkt das Ergebnis verwenden - keine Boolean nötig!
                            logger.info(f"✅ BRepFeat_MakePrism erfolgreich (lokale Op - Zylinder bleiben intakt)")
                            
                            # Feature erstellen
                            from modeling import ExtrudeFeature
                            from gui.commands.feature_commands import AddFeatureCommand

                            old_solid = source_body._build123d_solid

                            feat = ExtrudeFeature(
                                sketch=None,
                                distance=height,
                                operation=operation,
                                name=f"Push/Pull ({operation})",
                                precalculated_polys=[polygon] if polygon is not None else None,
                                plane_origin=plane_origin,
                                plane_normal=plane_normal,
                                plane_x_dir=plane_x_dir if polygon is not None else None,
                                plane_y_dir=plane_y_dir if polygon is not None else None,
                                face_brep=face_brep_str,
                                face_type=face_type_str,
                                face_index=best_face_index,
                                face_selector=face_selector_dict,
                            )

                            # Feature-lokale Face-ShapeID registrieren.
                            feat_face_shape_id = self._find_or_register_face_shape_id(
                                source_body,
                                best_face,
                                # Single-face Push/Pull reference: feature-local slot is 0.
                                local_index=0,
                                feature_id=feat.id,
                                force_feature_local=True,
                            )
                            if feat_face_shape_id is not None:
                                feat.face_shape_id = feat_face_shape_id

                            # === TNP v4.0: BRepFeat Operation tracken (mit echter Feature-ID) ===
                            # WICHTIG: prism-Operator direkt als occt_history und
                            # pre-USD Result als result_solid übergeben, damit
                            # _shape_exists_in_solid die Generated-Shapes findet.
                            try:
                                if hasattr(self, 'document') and self.document and hasattr(self.document, '_shape_naming_service'):
                                    service = self.document._shape_naming_service
                                    service.track_brepfeat_operation(
                                        feature_id=feat.id,
                                        source_solid=old_solid,
                                        result_solid=pre_usd_result_shape,
                                        modified_face=best_face,
                                        direction=(float(direction_vec[0]), float(direction_vec[1]), float(direction_vec[2])),
                                        distance=abs_height,
                                        occt_history=prism,
                                    )
                            except Exception as tnp_e:
                                if is_enabled("tnp_debug_logging"):
                                    logger.debug(f"TNP BRepFeat Tracking fehlgeschlagen: {tnp_e}")

                            # === Geometry Delta für Operation Summary berechnen (VORHER = old_solid, NACHHER = new_solid) ===
                            try:
                                from modeling import _solid_metrics
                                logger.debug(f"Push/Pull Geometry Delta: old_solid={old_solid is not None}, new_solid={new_solid is not None}")
                                before_m = _solid_metrics(old_solid) if old_solid is not None else None
                                after_m = _solid_metrics(new_solid) if new_solid is not None else None
                                logger.debug(f"Push/Pull Metrics: before={before_m}, after={after_m}")
                                if before_m and after_m and before_m["volume"] and after_m["volume"]:
                                    pre_vol = before_m["volume"]
                                    post_vol = after_m["volume"]
                                    vol_pct = ((post_vol - pre_vol) / pre_vol * 100.0) if pre_vol > 1e-12 else 0.0
                                    feat._geometry_delta = {
                                        "volume_before": round(pre_vol, 2),
                                        "volume_after": round(post_vol, 2),
                                        "volume_pct": round(vol_pct, 1),
                                        "faces_before": before_m["faces"],
                                        "faces_after": after_m["faces"],
                                        "faces_delta": after_m["faces"] - before_m["faces"],
                                        "edges_before": before_m["edges"],
                                        "edges_after": after_m["edges"],
                                        "edges_delta": after_m["edges"] - before_m["edges"],
                                    }
                                    logger.success(f"Push/Pull Geometry Delta gesetzt: Vol {pre_vol:.0f} → {post_vol:.0f} ({vol_pct:+.1f}%)")
                                else:
                                    logger.warning(f"Push/Pull Geometry Delta: Metrics unvollständig (before={before_m is not None}, after={after_m is not None})")
                            except Exception as e:
                                logger.error(f"Push/Pull Geometry Delta Fehler: {e}")
                                import traceback
                                traceback.print_exc()

                            # Body direkt aktualisieren (KEIN Boolean!)
                            source_body._build123d_solid = new_solid
                            source_body.invalidate_mesh()

                            # skip_rebuild=True weil BRepFeat das Solid bereits aktualisiert hat
                            cmd = AddFeatureCommand(source_body, feat, self, description=f"Push/Pull ({operation})", skip_rebuild=True)
                            self.undo_stack.push(cmd)

                            # Operation Summary DIREKT aufrufen mit korrekten Werten aus _geometry_delta
                            # (AddFeatureCommand kann pre/post nicht mehr unterscheiden bei skip_rebuild=True)
                            if hasattr(feat, '_geometry_delta') and feat._geometry_delta:
                                gd = feat._geometry_delta
                                pre_sig = {
                                    "volume": gd["volume_before"],
                                    "faces": gd["faces_before"],
                                    "edges": gd["edges_before"],
                                }
                                post_sig = {
                                    "volume": gd["volume_after"],
                                    "faces": gd["faces_after"],
                                    "edges": gd["edges_after"],
                                }
                                if hasattr(self, 'operation_summary'):
                                    self.operation_summary.show_summary(feat.name, pre_sig, post_sig, feat, self)

                            # Face-Zählung für Debug
                            from OCP.TopAbs import TopAbs_FACE
                            face_count = 0
                            exp = TopExp_Explorer(new_solid.wrapped, TopAbs_FACE)
                            while exp.More():
                                face_count += 1
                                exp.Next()
                            logger.info(f"✅ Push/Pull {operation}: {face_count} Faces (BRepFeat - lokale Op)")

                            return True
                        else:
                            # BRepFeat produzierte ungültiges Ergebnis
                            if volume <= 0.001:
                                logger.warning(f"BRepFeat_MakePrism: Volume zu klein ({volume:.4f}mm³), Fallback auf Boolean")
                            elif operation == "Cut" and volume >= original_volume - 0.01:
                                logger.warning(f"BRepFeat_MakePrism: Cut hatte keinen Effekt (Vol {original_volume:.2f}→{volume:.2f}), Fallback auf Boolean")
                            else:
                                logger.warning(f"BRepFeat_MakePrism: Ergebnis ungültig (is_valid=False), Fallback auf Boolean")
                    else:
                        logger.warning(f"BRepFeat_MakePrism: IsDone()=False, Fallback auf Boolean")

                except Exception as feat_err:
                    logger.warning(f"BRepFeat_MakePrism fehlgeschlagen: {feat_err}, Fallback auf Boolean")
                    import traceback
                    traceback.print_exc()

            # === METHODE 2: BRepPrimAPI_MakePrism + Boolean (für Cut, New Body, oder Fallback) ===
            try:
                from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism

                extrude_vec = gp_Vec(
                    float(direction_vec[0]) * abs_height,
                    float(direction_vec[1]) * abs_height,
                    float(direction_vec[2]) * abs_height
                )

                prism_maker = BRepPrimAPI_MakePrism(best_face.wrapped, extrude_vec)
                prism_maker.Build()

                if not prism_maker.IsDone():
                    raise ValueError("BRepPrimAPI_MakePrism fehlgeschlagen")

                prism_shape = prism_maker.Shape()
                new_geo = Solid(prism_shape)
                logger.info(f"✅ OCP-Extrusion (Boolean-Pfad): volume={new_geo.volume:.2f}")

            except Exception as ocp_extrude_err:
                logger.warning(f"OCP-Extrusion fehlgeschlagen: {ocp_extrude_err}, Fallback auf build123d")
                new_geo = extrude(best_face, amount=abs_height, dir=Vector(*direction_vec))

            # --- SCHRITT C: Multi-Body Operationen ---

            # 1. Ziele definieren
            targets = []

            if operation == "New Body":
                # Neuer Body mit parametrischem Feature
                from modeling import ExtrudeFeature
                from gui.commands.feature_commands import AddBodyCommand

                new_body = self.document.new_body()
                # Entferne Body erstmal wieder - wird durch AddBodyCommand hinzugefügt
                if new_body in self.document.bodies:
                    self.document.bodies.remove(new_body)

                feat = ExtrudeFeature(
                    sketch=None,
                    distance=height,
                    operation="New Body",
                    name="Push/Pull (New Body)",
                    precalculated_polys=[polygon] if polygon is not None else None,
                    plane_origin=plane_origin,
                    plane_normal=plane_normal,
                    plane_x_dir=plane_x_dir if polygon is not None else None,
                    plane_y_dir=plane_y_dir if polygon is not None else None
                )

                # Geometry Delta für New Body (von 0 zu Volume)
                try:
                    from modeling import _solid_metrics
                    logger.debug(f"Push/Pull New Body: new_geo={new_geo is not None}")
                    after_m = _solid_metrics(new_geo) if new_geo is not None else None
                    logger.debug(f"Push/Pull New Body Metrics: {after_m}")
                    if after_m and after_m["volume"]:
                        feat._geometry_delta = {
                            "volume_before": 0.0,
                            "volume_after": round(after_m["volume"], 2),
                            "volume_pct": 100.0,  # Neu = 100% Zunahme
                            "faces_before": 0,
                            "faces_after": after_m["faces"],
                            "faces_delta": after_m["faces"],
                            "edges_before": 0,
                            "edges_after": after_m["edges"],
                            "edges_delta": after_m["edges"],
                        }
                        logger.success(f"Push/Pull New Body Geometry Delta gesetzt: Vol {after_m['volume']:.0f} mm³")
                    else:
                        logger.warning(f"Push/Pull New Body: Metrics unvollständig (after_m={after_m is not None})")
                except Exception as e:
                    logger.error(f"Push/Pull New Body Geometry Delta Fehler: {e}")
                    import traceback
                    traceback.print_exc()

                new_body.features.append(feat)
                new_body._build123d_solid = new_geo
                new_body.invalidate_mesh()

                # KRITISCH: AddBodyCommand für korrektes Undo/Redo!
                cmd = AddBodyCommand(self.document, new_body, self, description="Push/Pull (New Body)")
                self.undo_stack.push(cmd)

                # Operation Summary mit korrekten Werten aus _geometry_delta
                if hasattr(feat, '_geometry_delta') and feat._geometry_delta:
                    gd = feat._geometry_delta
                    pre_sig = {
                        "volume": gd["volume_before"],
                        "faces": gd["faces_before"],
                        "edges": gd["edges_before"],
                    }
                    post_sig = {
                        "volume": gd["volume_after"],
                        "faces": gd["faces_after"],
                        "edges": gd["edges_after"],
                    }
                    if hasattr(self, 'operation_summary'):
                        self.operation_summary.show_summary(feat.name, pre_sig, post_sig, feat, self)

                logger.info(f"✅ Push/Pull New Body '{new_body.name}' erstellt")
                return True

            elif operation == "Cut":
                # CUT: Wir schneiden ALLES was sichtbar ist!
                targets = [b for b in self.document.bodies if self.viewport_3d.is_body_visible(b.id)]

            else:  # Join / Intersect
                # Normalerweise joinen wir nur mit dem Körper, von dem wir gestartet sind
                targets = [source_body]

            # 2. Operation auf alle Ziele anwenden
            success_count = 0

            for target in targets:
                try:
                    if not hasattr(target, '_build123d_solid') or target._build123d_solid is None:
                        continue

                    old_solid = target._build123d_solid
                    new_solid = None

                    # DEBUG: Zeige Geometrie vor Boolean
                    logger.info(f"Boolean {operation}: old_solid volume={old_solid.volume:.2f}, new_geo volume={new_geo.volume:.2f}")

                    if operation == "Cut":
                        new_solid = old_solid - new_geo
                    elif operation == "Join":
                        new_solid = old_solid + new_geo
                    elif operation == "Intersect":
                        new_solid = old_solid & new_geo

                    # FIX: UnifySameDomain nach Boolean-Op - verschmilzt koplanare/kozylindrische Faces
                    if new_solid is not None:
                        try:
                            from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
                            from OCP.TopAbs import TopAbs_FACE
                            from build123d import Solid

                            ocp_shape = new_solid.wrapped

                            # Zähle Faces vorher
                            face_count_before = 0
                            exp = TopExp_Explorer(ocp_shape, TopAbs_FACE)
                            while exp.More():
                                face_count_before += 1
                                exp.Next()

                            upgrader = ShapeUpgrade_UnifySameDomain(ocp_shape, True, True, True)
                            # Erhöhte Toleranzen für besseres Zylinder-Merging
                            upgrader.SetLinearTolerance(0.1)   # 0.1mm - großzügiger
                            upgrader.SetAngularTolerance(0.1)  # ~5.7° - für zylindrische Flächen
                            upgrader.Build()
                            unified = upgrader.Shape()
                            if unified and not unified.IsNull():
                                # Zähle Faces nachher
                                face_count_after = 0
                                exp = TopExp_Explorer(unified, TopAbs_FACE)
                                while exp.More():
                                    face_count_after += 1
                                    exp.Next()
                                new_solid = Solid(unified)
                                if face_count_before != face_count_after:
                                    logger.debug(f"UnifySameDomain ({operation}): {face_count_before} → {face_count_after} Faces")
                        except Exception as unify_err:
                            logger.trace(f"UnifySameDomain ({operation}): {unify_err}")

                    # ShapeList → größtes Solid nehmen
                    if hasattr(new_solid, '__iter__') and not hasattr(new_solid, 'is_null'):
                        solids = list(new_solid)
                        if solids:
                            new_solid = max(solids, key=lambda s: s.volume if hasattr(s, 'volume') else 0)
                        else:
                            new_solid = None

                    # Nur speichern, wenn das Ergebnis valide ist und nicht leer
                    if new_solid is not None and not new_solid.is_null():
                        # Parametrisches Feature erstellen
                        from modeling import ExtrudeFeature
                        from gui.commands.feature_commands import AddFeatureCommand

                        # Boolean-Pfad hat keine face_shape_id (anders als BRepFeat-Pfad)
                        # Verwende None oder lese aus best_face wenn verfügbar
                        boolean_face_shape_id = None
                        if best_face is not None and hasattr(best_face, 'wrapped'):
                            try:
                                boolean_face_shape_id = self._find_or_register_face_shape_id(
                                    target,
                                    best_face,
                                    local_index=0,
                                    feature_id=None,  # Wird später gesetzt
                                    force_feature_local=True,
                                )
                            except Exception:
                                pass

                        feat = ExtrudeFeature(
                            sketch=None,
                            distance=height,
                            operation=operation,
                            name=f"Push/Pull ({operation})",
                            precalculated_polys=[polygon] if polygon is not None else None,
                            plane_origin=plane_origin,
                            plane_normal=plane_normal,
                            plane_x_dir=plane_x_dir if polygon is not None else None,
                            plane_y_dir=plane_y_dir if polygon is not None else None,
                            face_shape_id=boolean_face_shape_id,  # TNP v4: face_shape_id=face_shape_id
                            face_index=best_face_index,
                            face_selector=face_selector_dict,
                        )

                        # KRITISCH: AddFeatureCommand für korrektes Undo/Redo!
                        cmd = AddFeatureCommand(target, feat, self, description=f"Push/Pull ({operation})")
                        self.undo_stack.push(cmd)

                        success_count += 1
                        logger.info(f"✅ Push/Pull {operation} auf '{target.name}' (parametrisch)")
                        
                except Exception as e:
                    logger.exception(f"Body-Face Op '{operation}' an {target.name} gescheitert: {e}")

            return success_count > 0
            
        except Exception as e:
            logger.exception(f"CRITICAL ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False
            
            
    def _extrude_with_build123d(self, face_indices, height, operation="New Body"):
        try:
            # 1. Solid erstellen (Build123d-basierte Profile-Detection)
            solid, verts, faces = self.sketch_editor.get_build123d_part_v2(height, operation)
            
            if solid is None or not verts:
                logger.error("Build123d: Keine Geometrie erzeugt.")
                return False

            # 2. Neuen Body im Dokument anlegen
            new_body = self.document.new_body(f"Body {len(self.document.bodies)+1}")
            
            # 3. Daten zuweisen
            new_body._build123d_solid = solid 
            new_body._mesh_vertices = verts
            new_body._mesh_triangles = faces
            
            # 4. Im Viewport anzeigen
            self.viewport_3d.add_body(new_body.id, new_body.name, verts, faces)
            
            # 5. WICHTIG: Browser aktualisieren, damit der Body in der Liste erscheint!
            if hasattr(self, 'browser'):
                self.browser.refresh()  # <--- DIESE ZEILE HAT GEFEHLT
            
            logger.success(f"Extrusion erfolgreich. Solid gespeichert.")
            return True
            
        except Exception as e:
            logger.exception(f"Build123d Extrude Error: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    
    
    def _update_body_from_build123d(self, body, solid):
        """
        Regeneriert das Mesh aus dem Solid und aktualisiert den Viewport.

        WICHTIG: Diese Methode wird für direkte Solid-Updates verwendet (Push/Pull),
        wo KEIN _rebuild() aufgerufen wird. Daher MUSS das Mesh hier regeneriert werden!
        """
        from modeling.cad_tessellator import CADTessellator

        # 1. Cache leeren - das Solid hat sich geändert!
        CADTessellator.notify_body_changed()

        # 2. Mesh aus dem neuen Solid regenerieren
        body._update_mesh_from_solid(solid)

        # 3. Viewport aktualisieren
        self._update_body_mesh(body)

    def _show_extrude_input_dialog(self):
        """Legacy Dialog - wird durch Panel ersetzt"""
        # Falls Tab gedrückt wird, fokussiere das Panel
        self.extrude_panel.height_input.setFocus()
        self.extrude_panel.height_input.selectAll()
    
    def _on_3d_click(self, event):
        """CAD-Selection über GeometryDetector (Sketch + Body Faces)"""

        # 1. Klick-Position
        pos = event.position() if hasattr(event, 'position') else event.pos()
        x, y = int(pos.x()), int(pos.y())

        # 2. Ray aus Viewport
        ray_origin, ray_dir = self.viewport_3d.get_ray_from_click(x, y)

        # 3. Selection-Mode an Viewport übergeben (wird dort in Filter übersetzt)
        self.viewport_3d.set_selection_mode(self.selection_mode)

        # 4. ZENTRALER CAD-Pick
        face_id = self.viewport_3d.detector.pick(
            ray_origin,
            ray_dir,
            selection_filter=self.viewport_3d.active_selection_filter
        )

        # 5. Ergebnis verarbeiten
        if face_id != -1:
            face = next(
                (f for f in self.viewport_3d.detector.selection_faces if f.id == face_id),
                None
            )

            if face:
                logger.debug(
                    f"Selection: {face.domain_type} ({face.owner_id})"
                )

                # Einheitliche Selection States
                self.selected_face_id = face.id
                self.selected_body = (
                    self.document.get_body(face.owner_id)
                    if face.domain_type == "body_face"
                    else None
                )

                # Optional: Highlight im Viewport
                self.viewport_3d.highlight_selection(face.id)

        else:
            logger.error("Nichts getroffen")
            self.selected_face_id = None
            self.selected_body = None

        
        
    def _create_body_from_data(self, verts, faces, height, operation):
        import numpy as np
        import pyvista as pv
        
        # Versuche Build123d für robustere Operationen
        if HAS_BUILD123D and operation in ["Join", "Cut", "Intersect"]:
            result = self._build123d_boolean(verts, faces, height, operation)
            if result is not None:
                return
        
        # PyVista Fallback
        v = np.array(verts, dtype=np.float32)
        f = []
        for face in faces: f.extend([len(face)] + list(face))
        
        new_mesh = pv.PolyData(v, np.array(f, dtype=np.int32))
        new_mesh = self._prepare_mesh_for_boolean(new_mesh)
        
        if operation in ["Join", "Cut", "Intersect"]:
            target_body = None
            target_mesh = None
            
            for body in self.document.bodies:
                mesh = self.viewport_3d.get_body_mesh(body.id)
                if mesh and mesh.n_points > 0:
                    target_body = body
                    target_mesh = self._prepare_mesh_for_boolean(mesh)
                    break
            
            if target_mesh:
                result = self._perform_boolean_operation(target_mesh, new_mesh, operation)
                if result and result.n_points > 0:
                    self._update_body_mesh(target_body, result)
                    return
                else:
                    logger.warning(f"Boolean operation '{operation}' failed - creating new body instead")

        # Neuer Body
        b = self.document.new_body(f"Body{len(self.document.bodies)+1}")
        feat = ExtrudeFeature(FeatureType.EXTRUDE, "Extrude", None, abs(height))
        b.features.append(feat)
        b._mesh_vertices = verts
        b._mesh_triangles = faces
        b._build123d_solid = None  # Placeholder für BREP
        self.viewport_3d.add_body(
            bid=b.id, 
            name=b.name, 
            verts=verts, 
            faces=faces
        )
        pass
    
    def _build123d_boolean(self, verts, faces, height, operation):
        """Führt Boolean-Operation mit Build123d durch (robuster als PyVista)"""
        try:
            from build123d import Solid, Compound
            import numpy as np
            import pyvista as pv
            
            # Konvertiere neues Mesh zu PyVista
            v = np.array(verts, dtype=np.float32)
            f = []
            for face in faces: f.extend([len(face)] + list(face))
            new_mesh = pv.PolyData(v, np.array(f, dtype=np.int32)).clean()
            
            # Finde Target Body mit Build123d Solid
            target_body = None
            target_solid = None
            
            for body in self.document.bodies:
                if hasattr(body, '_build123d_solid') and body._build123d_solid is not None:
                    target_body = body
                    target_solid = body._build123d_solid
                    break
            
            if target_solid is None:
                # Kein Build123d Solid vorhanden - Fallback
                return None
            
            # Konvertiere neues Mesh zu Build123d (schwierig - braucht Solid)
            # Für jetzt: Fallback zu PyVista
            logger.warning("Build123d Boolean: Target hat kein BREP - verwende PyVista")
            return None
            
        except Exception as e:
            logger.exception(f"Build123d Boolean error: {e}")
            return None
    
    def _prepare_mesh_for_boolean(self, mesh):
        """Bereitet ein Mesh für Boolean-Operationen vor"""
        import pyvista as pv
        
        try:
            # 1. Triangulieren (boolean braucht Dreiecke)
            mesh = mesh.triangulate()
            
            # 2. Clean (entfernt doppelte Punkte, degenerierte Faces)
            mesh = mesh.clean(tolerance=Tolerances.MESH_CLEAN)
            
            # 3. Normals berechnen und konsistent machen
            mesh.compute_normals(cell_normals=True, point_normals=True, 
                               split_vertices=False, consistent_normals=True, 
                               inplace=True)
            
            # 4. Fill holes wenn vorhanden
            try:
                mesh = mesh.fill_holes(hole_size=1000)
            except Exception as e:
                logger.debug(f"[main_window] Fehler beim Füllen von Mesh-Löchern: {e}")
                
            return mesh
        except Exception as e:
            logger.exception(f"Mesh preparation error: {e}")
            return mesh
    
    def _perform_boolean_operation(self, target, tool, operation):
        """Führt Boolean-Operation mit Fehlerbehandlung durch"""
        import pyvista as pv
        
        try:
            # Versuche zuerst mit PyVista
            if operation == "Cut":
                result = target.boolean_difference(tool)
            elif operation == "Join":
                result = target.boolean_union(tool)
            elif operation == "Intersect":
                result = target.boolean_intersection(tool)
            else:
                return None
            
            if result and result.n_points > 0:
                # Ergebnis aufräumen
                result = result.clean(tolerance=Tolerances.MESH_CLEAN)
                result.compute_normals(inplace=True)
                return result
                
        except Exception as e:
            logger.exception(f"PyVista boolean failed: {e}")
            
            # Fallback: Versuche mit vtkBooleanOperationPolyDataFilter direkt
            try:
                return self._vtk_boolean_fallback(target, tool, operation)
            except Exception as e2:
                logger.exception(f"VTK fallback also failed: {e2}")
        
        return None
    
    def _vtk_boolean_fallback(self, target, tool, operation):
        """VTK Boolean als Fallback"""
        import vtk
        import pyvista as pv
        
        # Konvertiere zu VTK
        target_vtk = target.extract_surface()
        tool_vtk = tool.extract_surface()
        
        # VTK Boolean Filter
        boolean = vtk.vtkBooleanOperationPolyDataFilter()
        boolean.SetInputData(0, target_vtk)
        boolean.SetInputData(1, tool_vtk)
        
        if operation == "Cut":
            boolean.SetOperationToDifference()
        elif operation == "Join":
            boolean.SetOperationToUnion()
        elif operation == "Intersect":
            boolean.SetOperationToIntersection()
        
        boolean.SetTolerance(Tolerances.KERNEL_PRECISION)
        boolean.Update()
        
        result = pv.wrap(boolean.GetOutput())
        if result.n_points > 0:
            return result.clean()
        return None

    def _is_body_in_inactive_component(self, body) -> bool:
        """Prüft ob Body zu einer inaktiven Component gehört (Assembly-System)."""
        if not hasattr(self.document, '_assembly_enabled') or not self.document._assembly_enabled:
            return False
        if not hasattr(self.document, 'root_component') or not self.document.root_component:
            return False

        active_comp = self.document._active_component

        def find_body_component(component):
            """Findet die Component die den Body enthält."""
            if body in component.bodies:
                return component
            for sub in component.sub_components:
                found = find_body_component(sub)
                if found:
                    return found
            return None

        body_comp = find_body_component(self.document.root_component)
        return body_comp is not None and body_comp != active_comp

    def _update_body_mesh(self, body, mesh_override=None):
        """Lädt die Mesh-Daten aus dem Body-Objekt in den Viewport"""
        logger.debug(f"_update_body_mesh aufgerufen für '{body.name}' (id={body.id})")

        # Assembly: Prüfen ob Body zu inaktiver Component gehört
        is_inactive = self._is_body_in_inactive_component(body)

        if hasattr(body, 'vtk_mesh') and body.vtk_mesh is not None:
            if body.vtk_mesh.n_points == 0:
                logger.warning(f"Warnung: Body '{body.name}' ist leer (0 Punkte). Überspringe Rendering.")
                return

        # 1. Fallback für manuelles Mesh (z.B. aus Boolean-Preview)
        if mesh_override:
             import numpy as np
             logger.debug(f"Verwende mesh_override")
             if hasattr(mesh_override, 'points'): # PyVista Mesh
                 self.viewport_3d.add_body(
                     bid=body.id,
                     name=body.name,
                     mesh_obj=mesh_override,
                     color=getattr(body, 'color', None),
                     inactive_component=is_inactive
                 )
                 # Body-Referenz setzen und Texture-Preview aktualisieren
                 self.viewport_3d.set_body_object(body.id, body)
                 self.viewport_3d.refresh_texture_previews(body.id)
             return

        # 2. NEUER PFAD: Prüfen auf VTK/PyVista Cache (aus cad_tessellator)
        if hasattr(body, 'vtk_mesh') and body.vtk_mesh is not None:
             logger.debug(f"Verwende vtk_mesh: {body.vtk_mesh.n_points} Punkte, vtk_edges: {body.vtk_edges.n_lines if body.vtk_edges else 'None'}")
             # Farbe bestimmen (Round Robin)
             try:
                 col_idx = self.document.bodies.index(body) % 3
             except: col_idx = 0
             default_col = (0.7, 0.7, 0.7)

             self.viewport_3d.add_body(
                 bid=body.id,
                 name=body.name,
                 mesh_obj=body.vtk_mesh,
                 edge_mesh_obj=body.vtk_edges,
                 color=default_col,
                 inactive_component=is_inactive
             )
             # Body-Referenz setzen und Texture-Preview aktualisieren
             self.viewport_3d.set_body_object(body.id, body)
             self.viewport_3d.refresh_texture_previews(body.id)
             return

        # 3. LEGACY PFAD: Alte Listen (nur Fallback)
        if hasattr(body, '_mesh_vertices') and body._mesh_vertices:
             logger.debug(f"Verwende Legacy _mesh_vertices")
             try:
                 col_idx = self.document.bodies.index(body) % 3
             except: col_idx = 0
             colors = [(0.6,0.6,0.8), (0.8,0.6,0.6), (0.6,0.8,0.6)]

             self.viewport_3d.add_body(
                 bid=body.id,
                 name=body.name,
                 verts=body._mesh_vertices,
                 faces=body._mesh_triangles,
                 color=colors[col_idx],
                 inactive_component=is_inactive
             )
             # Body-Referenz setzen und Texture-Preview aktualisieren
             self.viewport_3d.set_body_object(body.id, body)
             self.viewport_3d.refresh_texture_previews(body.id)
        else:
            logger.warning(f"Body '{body.name}' hat keine Mesh-Daten!")

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent, Qt

        if event.type() == QEvent.KeyPress:
            # Keine Shortcuts wenn ein Dialog offen ist oder ein Textfeld Fokus hat
            from PySide6.QtWidgets import QApplication, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox
            focus_widget = QApplication.focusWidget()
            if isinstance(focus_widget, (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox)):
                return False  # Event normal weiterleiten an das Textfeld
            if isinstance(focus_widget, QComboBox) and focus_widget.isEditable():
                return False
            active_modal = QApplication.activeModalWidget()
            if active_modal and active_modal is not self:
                return False  # Dialog ist offen → Shortcuts ignorieren

            k = event.key()
             # Tab - fokussiert Input-Felder
            if k == Qt.Key_Tab:
                if self.mode == "sketch":
                    self.sketch_editor.keyPressEvent(event)
                    return True
                if self.viewport_3d.extrude_mode:
                    # Fokussiere das Extrude-Panel
                    self.extrude_panel.height_input.setFocus()
                    self.extrude_panel.height_input.selectAll()
                    return True
            
            # Revolve-Modus: Achsen-Shortcuts
            if self.viewport_3d.revolve_mode:
                if k == Qt.Key_X:
                    self.revolve_panel.set_axis('X')
                    return True
                if k == Qt.Key_Y:
                    self.revolve_panel.set_axis('Y')
                    return True
                if k == Qt.Key_Z:
                    self.revolve_panel.set_axis('Z')
                    return True
                if k == Qt.Key_F:
                    self.revolve_panel._flip_direction()
                    return True
                if k == Qt.Key_Tab:
                    self.revolve_panel.angle_input.setFocus()
                    self.revolve_panel.angle_input.selectAll()
                    return True

            if k == Qt.Key_E:
                if not self.viewport_3d.extrude_mode:
                    self._extrude_dialog()
                return True
                
            # Selektions-Modi umschalten (Pipeline an Viewport senden)
            if self.mode == "3d" :
                 # F - Flip Richtung im Extrude-Modus
                if k == Qt.Key_F and self.viewport_3d.extrude_mode:
                    self.extrude_panel._flip_direction()
                    return True
            
                if k == Qt.Key_U:
                    self.viewport_3d.set_selection_mode("face")
                    logger.success("Modus: Flächen")
                    return True # Event konsumiert
                elif k == Qt.Key_I:
                    self.viewport_3d.set_selection_mode("hole")
                    logger.success("Modus: Löcher")
                    return True
                elif k == Qt.Key_O:
                    self.viewport_3d.set_selection_mode("sketch")
                    logger.success("Modus: Skizze")
                    return True

            # Hole-Modus: Tab für Fokus
            if self._hole_mode:
                if k == Qt.Key_Tab:
                    self.hole_panel.diameter_input.setFocus()
                    self.hole_panel.diameter_input.selectAll()
                    return True

            # Draft-Modus: Achsen-Shortcuts + Tab
            if self._draft_mode:
                if k == Qt.Key_X:
                    self.draft_panel._set_axis('X')
                    return True
                if k == Qt.Key_Y:
                    self.draft_panel._set_axis('Y')
                    return True
                if k == Qt.Key_Z:
                    self.draft_panel._set_axis('Z')
                    return True
                if k == Qt.Key_Tab:
                    self.draft_panel.angle_input.setFocus()
                    self.draft_panel.angle_input.selectAll()
                    return True

            # Bestätigung für Revolve / Extrude / Offset Plane / Hole / Draft
            if k in (Qt.Key_Return, Qt.Key_Enter):
                if self._draft_mode:
                    self._on_draft_confirmed()
                    return True
                if self._hole_mode:
                    self._on_hole_confirmed()
                    return True
                if self.viewport_3d.revolve_mode:
                    self._on_revolve_confirmed()
                    return True
                if self.viewport_3d.offset_plane_mode:
                    self._on_offset_plane_confirmed()
                    return True
                if self.viewport_3d.extrude_mode:
                    self._on_extrude_confirmed()
                    return True
            
            if k == Qt.Key_Escape:
                # Priorität 0: Measure abbrechen
                if getattr(self, '_measure_active', False):
                    self._cancel_measure_mode()
                    return True
                # Draft abbrechen
                if self._draft_mode:
                    self._on_draft_cancelled()
                    return True
                # Hole abbrechen
                if self._hole_mode:
                    self._on_hole_cancelled()
                    return True
                # Priorität 0.5: Revolve abbrechen
                if self.viewport_3d.revolve_mode:
                    self._on_revolve_cancelled()
                    return True
                # Priorität 0.6: Offset Plane abbrechen
                if self.viewport_3d.offset_plane_mode or self._offset_plane_pending:
                    self._on_offset_plane_cancelled()
                    return True
                # Priorität 1: Extrude abbrechen
                if self.viewport_3d.extrude_mode:
                    self._on_extrude_cancelled()
                    return True
                # Priorität 2: Plane-Select abbrechen
                elif self.viewport_3d.plane_select_mode:
                    self.viewport_3d.set_plane_select_mode(False)
                    logger.info("Ebenen-Auswahl abgebrochen")
                    return True
                # Sketch-Escape wird hierarchisch vom SketchEditor selbst verarbeitet
                # → exit_requested Signal → _finish_sketch()
                    
           
            
            
            # Plane Selection Shortcuts
            if self.viewport_3d.plane_select_mode:
                if k in [Qt.Key_1, Qt.Key_T]:
                    self._on_plane_selected('xy')
                    return True
                if k in [Qt.Key_2, Qt.Key_F]:
                    self._on_plane_selected('xz')
                    return True
                if k in [Qt.Key_3, Qt.Key_R]:
                    self._on_plane_selected('yz')
                    return True
                    
                    
            # 3D Mode Shortcuts
            if self.mode == "3d" and not self.viewport_3d.extrude_mode:
                if k == Qt.Key_E:
                    self._extrude_dialog()
                    return True
                if k == Qt.Key_N:
                    self._new_sketch()
                    return True

                # G/R/S/M - Transform Shortcuts (nur wenn Gizmo sichtbar)
                if k == Qt.Key_G:
                    if self.viewport_3d.handle_transform_key('g'):
                        return True
                if k == Qt.Key_R:
                    if self.viewport_3d.handle_transform_key('r'):
                        return True
                if k == Qt.Key_M:
                    if self.viewport_3d.handle_transform_key('m'):
                        return True

                # H - Hide/Show selektierte Bodies
                if k == Qt.Key_H:
                    selected = self.browser.get_selected_bodies()
                    if selected:
                        for body in selected:
                            vis = self.browser.body_visibility.get(body.id, True)
                            self.browser.body_visibility[body.id] = not vis
                            self.browser.body_vis_changed.emit(body.id, not vis)
                        self.browser.refresh()
                        self.browser.visibility_changed.emit()
                        return True

                # Delete - Selektierten Body loeschen
                if k == Qt.Key_Delete:
                    selected = self.browser.get_selected_bodies()
                    if selected:
                        for body in selected:
                            self.browser._del_body(body)
                        return True

        return False
        #return super().eventFilter(obj, event)

    def _on_opt_change(self, o, v): pass

    def _delete_selected(self):
        """Löscht alle ausgewählten Bodies."""
        selected = self.browser.get_selected_bodies()
        if selected:
            for body in selected:
                self.browser._del_body(body)

    def _edit_feature(self, d): 
        """
        Wird aufgerufen durch Doppelklick im Browser.
        FIX: Lädt jetzt auch die Referenz-Geometrie für den Hintergrund!
        """
        if d[0] == 'sketch':
            sketch = d[1]
            self.active_sketch = sketch
            self.sketch_editor.sketch = sketch
            
            # 1. Gespeicherte Achsen holen (oder Fallback berechnen)
            origin = sketch.plane_origin
            normal = sketch.plane_normal
            x_dir = getattr(sketch, 'plane_x_dir', None)
            
            if x_dir is None:
                # Fallback für alte Skizzen ohne gespeicherte X-Achse
                x_dir, _ = self._calculate_plane_axes(normal)

            # 2. Hintergrund-Referenzen laden (LÖST PROBLEM 2)
            # Wir übergeben explizit x_dir, damit der Hintergrund nicht verdreht ist
            self._set_sketch_body_references(origin, normal, x_dir)
            
            # 3. Modus wechseln
            self._set_mode("sketch")
            
            # 4. Statusmeldung
            logger.success(f"Bearbeite Skizze: {sketch.name}")

        elif d[0] == 'feature':
            feature = d[1]
            body = d[2]

            from modeling import (TransformFeature, ExtrudeFeature, FilletFeature,
                                  ChamferFeature, ShellFeature, RevolveFeature, FeatureType)
            if isinstance(feature, TransformFeature) or feature.type == FeatureType.TRANSFORM:
                self._edit_transform_feature(feature, body)
            elif isinstance(feature, ExtrudeFeature):
                self._edit_parametric_feature(feature, body, 'extrude')
            elif isinstance(feature, FilletFeature):
                self._edit_parametric_feature(feature, body, 'fillet')
            elif isinstance(feature, ChamferFeature):
                self._edit_parametric_feature(feature, body, 'chamfer')
            elif isinstance(feature, ShellFeature):
                self._edit_parametric_feature(feature, body, 'shell')
            elif isinstance(feature, RevolveFeature):
                self._edit_parametric_feature(feature, body, 'revolve')
            else:
                logger.info(f"Feature '{feature.name}' kann nicht editiert werden (Typ: {feature.type})")


    def _edit_transform_feature(self, feature, body):
        """
        Öffnet den Transform-Edit-Dialog und aktualisiert den Body nach Änderung.
        """
        from gui.dialogs.transform_edit_dialog import TransformEditDialog
        from gui.commands.feature_commands import EditFeatureCommand

        # Speichere alte Daten für Undo
        old_data = feature.data.copy()

        dialog = TransformEditDialog(feature, body, self)

        if dialog.exec():
            # Feature wurde geändert
            new_data = feature.data.copy()

            # Push to Undo Stack
            cmd = EditFeatureCommand(body, feature, old_data, new_data, self)
            self.undo_stack.push(cmd)

            logger.success(f"Transform-Feature '{feature.name}' aktualisiert (Undo: Ctrl+Z)")

    def _edit_parametric_feature(self, feature, body, feature_type: str):
        """
        Generischer Edit-Dialog fuer parametrische Features.
        Unterstuetzt: extrude, fillet, chamfer, shell
        """
        from gui.commands.feature_commands import EditFeatureCommand

        # Alte Daten sichern
        if feature_type == 'extrude':
            from gui.dialogs.feature_edit_dialogs import ExtrudeEditDialog
            old_data = {
                'distance': feature.distance,
                'direction': feature.direction,
                'operation': feature.operation,
            }
            dialog = ExtrudeEditDialog(feature, body, self)
        elif feature_type == 'fillet':
            from gui.dialogs.feature_edit_dialogs import FilletEditDialog
            old_data = {'radius': feature.radius}
            dialog = FilletEditDialog(feature, body, self)
        elif feature_type == 'chamfer':
            from gui.dialogs.feature_edit_dialogs import ChamferEditDialog
            old_data = {'distance': feature.distance}
            dialog = ChamferEditDialog(feature, body, self)
        elif feature_type == 'shell':
            from gui.dialogs.feature_edit_dialogs import ShellEditDialog
            old_data = {'thickness': feature.thickness}
            dialog = ShellEditDialog(feature, body, self)
        elif feature_type == 'revolve':
            from gui.dialogs.feature_edit_dialogs import RevolveEditDialog
            old_data = {'angle': feature.angle, 'axis': feature.axis, 'operation': feature.operation}
            dialog = RevolveEditDialog(feature, body, self)
        elif feature_type == 'loft':
            from gui.dialogs.feature_edit_dialogs import LoftEditDialog
            old_data = {
                'ruled': feature.ruled,
                'operation': feature.operation,
                'start_continuity': feature.start_continuity,
                'end_continuity': feature.end_continuity
            }
            dialog = LoftEditDialog(feature, body, self)
        elif feature_type == 'sweep':
            from gui.dialogs.feature_edit_dialogs import SweepEditDialog
            old_data = {
                'operation': feature.operation,
                'is_frenet': feature.is_frenet,
                'twist_angle': feature.twist_angle
            }
            dialog = SweepEditDialog(feature, body, self)
        else:
            logger.warning(f"Unbekannter Feature-Typ: {feature_type}")
            return

        if dialog.exec():
            # Neue Daten nach Dialog-Aenderung
            if feature_type == 'extrude':
                new_data = {
                    'distance': feature.distance,
                    'direction': feature.direction,
                    'operation': feature.operation,
                }
            elif feature_type == 'fillet':
                new_data = {'radius': feature.radius}
            elif feature_type == 'chamfer':
                new_data = {'distance': feature.distance}
            elif feature_type == 'shell':
                new_data = {'thickness': feature.thickness}
            elif feature_type == 'revolve':
                new_data = {'angle': feature.angle, 'axis': feature.axis, 'operation': feature.operation}
            elif feature_type == 'loft':
                new_data = {
                    'ruled': feature.ruled,
                    'operation': feature.operation,
                    'start_continuity': feature.start_continuity,
                    'end_continuity': feature.end_continuity
                }
            elif feature_type == 'sweep':
                new_data = {
                    'operation': feature.operation,
                    'is_frenet': feature.is_frenet,
                    'twist_angle': feature.twist_angle
                }

            cmd = EditFeatureCommand(body, feature, old_data, new_data, self)
            self.undo_stack.push(cmd)
            logger.success(f"Feature '{feature.name}' aktualisiert (Undo: Ctrl+Z)")

    def _on_feature_deleted(self, feature, body):
        """
        Handler fuer Feature-Loeschung aus dem Browser.
        Warnt bei abhaengigen Features, triggert Rebuild.
        """
        from gui.commands.feature_commands import DeleteFeatureCommand
        from modeling import FilletFeature, ChamferFeature, ShellFeature

        logger.info(f"Lösche Feature '{feature.name}' aus {body.name}...")

        # Abhaengigkeits-Check: Features die NACH diesem kommen und davon abhaengen koennten
        feature_index = body.features.index(feature) if feature in body.features else 0
        dependent_features = []
        for f in body.features[feature_index + 1:]:
            if isinstance(f, (FilletFeature, ChamferFeature, ShellFeature)):
                dependent_features.append(f.name)

        if dependent_features:
            from PySide6.QtWidgets import QMessageBox
            deps_str = ", ".join(dependent_features)
            reply = QMessageBox.question(
                self,
                "Feature loeschen?",
                f"'{feature.name}' wird von nachfolgenden Features verwendet:\n"
                f"{deps_str}\n\n"
                f"Diese Features koennten nach dem Loeschen fehlschlagen.\n"
                f"Trotzdem loeschen?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        # Push to Undo Stack
        cmd = DeleteFeatureCommand(body, feature, feature_index, self)
        self.undo_stack.push(cmd)

        logger.success(f"Feature '{feature.name}' gelöscht (Undo: Ctrl+Z)")

    # =========================================================================
    # Phase 3 Assembly: Component-Handler
    # =========================================================================

    def _on_component_activated(self, component):
        """
        Aktiviert eine Component als aktive Bearbeitungs-Component.

        In Assembly-Modus: Bodies/Sketches werden relativ zur aktiven Component bearbeitet.
        UNDO/REDO: Verwendet ActivateComponentCommand.
        """
        if not hasattr(self.document, '_assembly_enabled') or not self.document._assembly_enabled:
            return

        from gui.commands.component_commands import ActivateComponentCommand

        # Aktuelle Component merken für Undo
        previous_active = self.document._active_component

        # Nur Command pushen wenn es eine echte Änderung ist
        if previous_active != component:
            cmd = ActivateComponentCommand(component, previous_active, self)
            self.undo_stack.push(cmd)
            self.statusBar().showMessage(f"Aktive Component: {component.name}")

    def _on_component_created(self, parent_component, new_component):
        """
        Handler für neue Component-Erstellung.

        UNDO/REDO: Verwendet CreateComponentCommand.
        HINWEIS: Browser erstellt die Component, Command verwaltet nur add/remove.
        """
        if not hasattr(self.document, '_assembly_enabled') or not self.document._assembly_enabled:
            return

        from gui.commands.component_commands import CreateComponentCommand

        # Command mit der bereits erstellten Component
        cmd = CreateComponentCommand(parent_component, new_component.name, self)
        cmd.created_component = new_component  # Vorhandene Component verwenden
        self.undo_stack.push(cmd)
        self.statusBar().showMessage(f"Component erstellt: {new_component.name}")

    def _on_component_deleted(self, component):
        """
        Handler für Component-Löschung.

        Löscht Component inkl. aller Bodies/Sketches/Sub-Components.
        UNDO/REDO: Verwendet DeleteComponentCommand.
        """
        if not hasattr(self.document, '_assembly_enabled') or not self.document._assembly_enabled:
            return

        if component.parent is None:
            logger.warning("[ASSEMBLY] Root-Component kann nicht gelöscht werden")
            return

        from gui.commands.component_commands import DeleteComponentCommand

        cmd = DeleteComponentCommand(component, self)
        self.undo_stack.push(cmd)
        self.statusBar().showMessage(f"Component gelöscht: {component.name}")

    def _on_component_renamed(self, component, new_name):
        """
        Handler für Component-Umbenennung.

        UNDO/REDO: Verwendet RenameComponentCommand.
        """
        if not hasattr(self.document, '_assembly_enabled') or not self.document._assembly_enabled:
            return

        from gui.commands.component_commands import RenameComponentCommand

        old_name = component.name
        cmd = RenameComponentCommand(component, old_name, new_name, self)
        self.undo_stack.push(cmd)
        self.statusBar().showMessage(f"Component umbenannt: {old_name} → {new_name}")

    def _on_component_vis_changed(self, component_id: str, visible: bool):
        """
        Handler für Component-Visibility-Änderung.

        Blendet alle Bodies/Sketches der Component (und Sub-Components) ein/aus.
        """
        self._trigger_viewport_update()
        logger.debug(f"[ASSEMBLY] Component visibility geändert: {component_id} → {visible}")

    def _on_body_moved_to_component(self, body, source_comp, target_comp):
        """
        Handler für Body-Verschiebung zwischen Components.

        UNDO/REDO: Verwendet MoveBodyToComponentCommand.
        """
        if not hasattr(self.document, '_assembly_enabled') or not self.document._assembly_enabled:
            return

        from gui.commands.component_commands import MoveBodyToComponentCommand

        cmd = MoveBodyToComponentCommand(body, source_comp, target_comp, self)
        self.undo_stack.push(cmd)
        self.statusBar().showMessage(f"Body '{body.name}' verschoben: {source_comp.name} → {target_comp.name}")

    def _on_sketch_moved_to_component(self, sketch, source_comp, target_comp):
        """
        Handler für Sketch-Verschiebung zwischen Components.

        UNDO/REDO: Verwendet MoveSketchToComponentCommand.
        """
        if not hasattr(self.document, '_assembly_enabled') or not self.document._assembly_enabled:
            return

        from gui.commands.component_commands import MoveSketchToComponentCommand

        cmd = MoveSketchToComponentCommand(sketch, source_comp, target_comp, self)
        self.undo_stack.push(cmd)
        self.statusBar().showMessage(f"Sketch '{sketch.name}' verschoben: {source_comp.name} → {target_comp.name}")

    def _on_rollback_changed(self, body, value):
        """Handle rollback slider change - rebuild body up to given feature index."""
        from modeling.cad_tessellator import CADTessellator
        n = len(body.features)
        rebuild_up_to = value if value < n else None
        body.rollback_index = rebuild_up_to

        CADTessellator.notify_body_changed()

        def _on_rebuild_progress(current, total, name):
            self.statusBar().showMessage(f"Rebuild {current + 1}/{total}: {name}")
            QApplication.processEvents()

        body._rebuild(rebuild_up_to=rebuild_up_to, progress_callback=_on_rebuild_progress if n >= 5 else None)
        self._update_body_from_build123d(body, body._build123d_solid)
        self.browser.refresh()
        self.browser.show_rollback_bar(body)
        self.statusBar().showMessage(f"Rollback: {value}/{n} Features")

    def _new_project(self):
        self.document = Document("Projekt1")
        self._setup_tnp_debug_callback()  # TNP v4.0: Callback neu registrieren
        self.browser.set_document(self.document)
        self._set_mode("3d")
    
    def set_selection_mode(self, mode):
        from gui.geometry_detector import SelectionFilter

        if mode == "face":
            self.active_selection_filter = SelectionFilter.FACE
        elif mode == "hole":
            self.active_selection_filter = SelectionFilter.HOLE
        elif mode == "sketch":
            self.active_selection_filter = SelectionFilter.SKETCH
        else:
            self.active_selection_filter = SelectionFilter.ALL
        
    # =========================================================================
    # Phase 8.2: Projekt Save/Load
    # =========================================================================

    def _save_project(self):
        """Speichert das aktuelle Projekt."""
        # Wenn schon ein Pfad bekannt ist, direkt speichern
        if hasattr(self, '_current_project_path') and self._current_project_path:
            self._do_save_project(self._current_project_path)
        else:
            self._save_project_as()

    def _save_project_as(self):
        """Speichert das Projekt unter neuem Namen."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Projekt speichern"),
            "",
            "MashCAD Project (*.mshcad);;All Files (*)"
        )
        if path:
            self._do_save_project(path)

    def _do_save_project(self, path: str):
        """Führt die eigentliche Speicherung durch."""
        try:
            if self.document.save_project(path):
                self._current_project_path = path
                self.setWindowTitle(f"MashCAD - {os.path.basename(path)}")
                add_recent_file(path)
                self._update_recent_files_menu()
                logger.success(f"Projekt gespeichert: {path}")
            else:
                QMessageBox.critical(self, "Fehler", "Projekt konnte nicht gespeichert werden.")
        except Exception as e:
            logger.error(f"Fehler beim Speichern: {e}")
            QMessageBox.critical(self, "Fehler", f"Speichern fehlgeschlagen:\n{e}")

    def _open_project(self):
        """Öffnet ein bestehendes Projekt."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Projekt öffnen"),
            "",
            "MashCAD Project (*.mshcad);;All Files (*)"
        )
        if not path:
            return

        try:
            doc = Document.load_project(path)
            if doc:
                # Altes Dokument ersetzen
                self.document = doc
                self._setup_tnp_debug_callback()  # TNP v4.0: Callback neu registrieren
                self._current_project_path = path

                # UI aktualisieren
                self.browser.set_document(doc)
                self.browser.refresh()

                # Viewport aktualisieren - direkter Aufruf für sofortiges Update
                self._update_viewport_all_impl()

                # Sketches im Viewport aktualisieren
                self.viewport_3d.set_sketches(self.browser.get_visible_sketches())

                # Aktiven Sketch setzen
                if doc.active_sketch:
                    self.active_sketch = doc.active_sketch
                    self.sketch_editor.sketch = doc.active_sketch

                self.setWindowTitle(f"MashCAD - {os.path.basename(path)}")

                # Konstruktionsebenen rendern
                self._render_construction_planes()

                # TNP Stats aktualisieren
                self._update_tnp_stats()

                add_recent_file(path)
                self._update_recent_files_menu()
                logger.success(f"Projekt geladen: {path}")
            else:
                QMessageBox.critical(self, "Fehler", "Projekt konnte nicht geladen werden.")
        except Exception as e:
            logger.error(f"Fehler beim Laden: {e}")
            QMessageBox.critical(self, "Fehler", f"Laden fehlgeschlagen:\n{e}")

    def _update_recent_files_menu(self):
        """Updates the recent files submenu."""
        self._recent_menu.clear()
        recent = get_recent_files()
        if not recent:
            action = self._recent_menu.addAction(tr("No recent files"))
            action.setEnabled(False)
            return
        for path in recent:
            display = os.path.basename(path)
            action = self._recent_menu.addAction(display)
            action.setToolTip(path)
            action.triggered.connect(lambda checked=False, p=path: self._open_recent_file(p))

    def _open_recent_file(self, path: str):
        """Opens a recent project file."""
        if not os.path.exists(path):
            logger.warning(f"Datei nicht gefunden: {path}")
            self._update_recent_files_menu()
            return
        try:
            doc = Document.load_project(path)
            if doc:
                self.document = doc
                self._setup_tnp_debug_callback()
                self._current_project_path = path
                self.browser.set_document(doc)
                self.browser.refresh()
                self._update_viewport_all_impl()
                self.viewport_3d.set_sketches(self.browser.get_visible_sketches())
                if doc.active_sketch:
                    self.active_sketch = doc.active_sketch
                    self.sketch_editor.sketch = doc.active_sketch
                self.setWindowTitle(f"MashCAD - {os.path.basename(path)}")
                self._render_construction_planes()
                self._update_tnp_stats()
                add_recent_file(path)
                self._update_recent_files_menu()
                logger.success(f"Projekt geladen: {path}")
        except Exception as e:
            logger.error(f"Fehler beim Öffnen: {e}")

    def _export_stl(self):
        """STL Export mit Quality-Dialog und Surface Texture Support.

        PERFORMANCE (Phase 6): Async Export für große Meshes.
        """
        bodies = self._get_export_candidates()
        if not bodies:
            logger.warning("Keine sichtbaren Körper zum Exportieren.")
            return

        # Show export settings dialog
        from gui.dialogs.stl_export_dialog import STLExportDialog
        dlg = STLExportDialog(parent=self)
        if dlg.exec() != QDialog.Accepted:
            return

        linear_defl = dlg.linear_deflection
        angular_tol = dlg.angular_tolerance
        is_binary = dlg.is_binary
        scale = dlg.scale_factor

        path, _ = QFileDialog.getSaveFileName(self, tr("STL exportieren"), "", "STL Files (*.stl)")
        if not path: return

        # PERFORMANCE Phase 6: Async export für große Meshes
        # Schätze Mesh-Größe basierend auf Body-Count und Quality
        estimated_complexity = len(bodies) * (1.0 / max(0.01, linear_defl))
        use_async = estimated_complexity > 100 or len(bodies) > 3

        if use_async:
            self._export_stl_async(bodies, path, linear_defl, angular_tol, is_binary, scale)
            return

        try:
            import pyvista as pv
            merged_polydata = None
            texture_applied_count = 0

            for body in bodies:
                mesh_to_add = None

                # Check for SurfaceTextureFeatures
                has_textures = HAS_TEXTURE_EXPORT and any(
                    isinstance(f, SurfaceTextureFeature) and not f.suppressed
                    for f in getattr(body, 'features', [])
                )

                if has_textures and HAS_BUILD123D and hasattr(body, '_build123d_solid') and body._build123d_solid:
                    # Use TexturedTessellator for bodies with textures
                    try:
                        logger.info(f"Tesselliere '{body.name}' mit Textur-Mapping...")
                        mesh, face_mappings = TexturedTessellator.tessellate_with_face_map(
                            body._build123d_solid,
                            quality=linear_defl,
                            angular_tolerance=angular_tol
                        )

                        if mesh is not None:
                            # Apply textures
                            mesh, results = apply_textures_to_body(mesh, body, face_mappings)

                            # Log results
                            for result in results:
                                if result.status == ResultStatus.ERROR:
                                    logger.error(f"Textur-Fehler: {result.message}")
                                elif result.status == ResultStatus.WARNING:
                                    logger.warning(f"Textur-Warnung: {result.message}")
                                elif result.status == ResultStatus.SUCCESS:
                                    texture_applied_count += 1
                                    logger.debug(f"Textur angewendet: {result.message}")

                            mesh_to_add = mesh

                    except Exception as e:
                        logger.warning(f"Texture-Export für '{body.name}' fehlgeschlagen: {e}")
                        import traceback
                        traceback.print_exc()
                        # Fallback to standard tessellation
                        has_textures = False

                # Standard tessellation (no textures or texture failed)
                if mesh_to_add is None and HAS_BUILD123D and hasattr(body, '_build123d_solid') and body._build123d_solid:
                    try:
                        # Phase 6: Use export cache
                        from modeling.cad_tessellator import CADTessellator
                        verts, faces_tris = CADTessellator.tessellate_for_export(
                            body._build123d_solid,
                            linear_deflection=linear_defl,
                            angular_tolerance=angular_tol
                        )
                        if verts and faces_tris:
                            faces = []
                            for t in faces_tris: faces.extend([3] + list(t))
                            mesh_to_add = pv.PolyData(np.array(verts), np.array(faces))
                    except Exception as e:
                        logger.warning(f"Build123d Tessellierung fehlgeschlagen: {e}")

                if mesh_to_add is None:
                    mesh_to_add = self.viewport_3d.get_body_mesh(body.id)

                if mesh_to_add:
                    if merged_polydata is None: merged_polydata = mesh_to_add
                    else: merged_polydata = merged_polydata.merge(mesh_to_add)

            if merged_polydata:
                # Apply unit scaling if needed (inch)
                if abs(scale - 1.0) > 1e-6:
                    merged_polydata.points *= scale

                merged_polydata.save(path, binary=is_binary)
                qual_name = ["Draft", "Standard", "Fine", "Ultra"][dlg.quality_slider.value()]
                if texture_applied_count > 0:
                    logger.success(f"STL gespeichert: {path} ({qual_name}, {texture_applied_count} Texturen)")
                else:
                    n_tri = merged_polydata.n_cells
                    logger.success(f"STL gespeichert: {path} ({qual_name}, {n_tri:,} Dreiecke)")
            else:
                logger.error("Konnte keine Mesh-Daten generieren.")

        except Exception as e:
            logger.error(f"STL Export Fehler: {e}")
            import traceback
            traceback.print_exc()

    def _export_stl_async(self, bodies, filepath, linear_defl, angular_tol, is_binary, scale):
        """
        PERFORMANCE (Phase 6): Async STL Export mit Progress-Dialog.

        UI bleibt responsiv während des Exports.
        """
        from PySide6.QtWidgets import QProgressDialog

        # Progress-Dialog erstellen
        progress = QProgressDialog(
            "Exportiere STL...",
            "Abbrechen",
            0, 100,
            self
        )
        progress.setWindowTitle("STL Export")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        # Worker erstellen
        self._export_worker = STLExportWorker(
            bodies=bodies,
            filepath=filepath,
            linear_deflection=linear_defl,
            angular_tolerance=angular_tol,
            binary=is_binary,
            scale=scale
        )

        # Signals verbinden
        def on_progress(percent, status):
            progress.setValue(percent)
            progress.setLabelText(status)

        def on_finished(result):
            progress.close()
            logger.success(f"STL gespeichert: {result}")
            self._export_worker = None

        def on_error(error_msg):
            progress.close()
            logger.error(f"STL Export Fehler: {error_msg}")
            self._export_worker = None

        def on_cancel():
            if hasattr(self, '_export_worker') and self._export_worker:
                self._export_worker.cancel()

        self._export_worker.progress.connect(on_progress)
        self._export_worker.finished.connect(on_finished)
        self._export_worker.error.connect(on_error)
        progress.canceled.connect(on_cancel)

        # Worker starten
        logger.info("Starting async STL export...")
        self._export_worker.start()

    def _export_step(self):
        """STEP Export mit FIX für 'Part object has no attribute export_step'"""
        if not HAS_BUILD123D:
            logger.error("Build123d fehlt. STEP Export nicht möglich.")
            return

        bodies = self._get_export_candidates()
        if not bodies:
            logger.warning("Keine sichtbaren Körper zum Exportieren.")
            return
            
        valid_solids = []
        for b in bodies:
            if hasattr(b, '_build123d_solid') and b._build123d_solid:
                valid_solids.append(b._build123d_solid)
                
        if not valid_solids:
            logger.error("Keine CAD-Daten (BREP) vorhanden. Nur Mesh-Objekte können nicht als STEP exportiert werden.")
            return

        path, _ = QFileDialog.getSaveFileName(self, tr("STEP exportieren"), "", "STEP Files (*.step *.stp)")
        if not path: return
        
        try:
            from build123d import Compound, export_step
            
            # WICHTIG: Wir nutzen die Funktion export_step(obj, path), nicht die Methode!
            if len(valid_solids) == 1:
                export_shape = valid_solids[0]
            else:
                export_shape = Compound(children=valid_solids)
            
            # DER FIX: Globale Funktion nutzen
            export_step(export_shape, path)
            
            logger.success(f"STEP gespeichert: {path}")
                
        except Exception as e:
            logger.error(f"STEP Export Fehler: {e}")
            import traceback
            traceback.print_exc()

    def _export_svg(self):
        """Export visible bodies as SVG (projected edges onto a plane)."""
        bodies = self._get_export_candidates()
        if not bodies:
            logger.warning("Keine sichtbaren Koerper.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Export SVG", "", "SVG Files (*.svg)")
        if not path:
            return

        try:
            from OCP.BRepMesh import BRepMesh_IncrementalMesh
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_EDGE
            from OCP.BRepAdaptor import BRepAdaptor_Curve
            from OCP.GCPnts import GCPnts_UniformDeflection

            all_lines = []
            min_x = min_y = float('inf')
            max_x = max_y = float('-inf')

            for body in bodies:
                solid = getattr(body, '_build123d_solid', None)
                if solid is None:
                    continue
                shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

                explorer = TopExp_Explorer(shape, TopAbs_EDGE)
                while explorer.More():
                    edge = explorer.Current()
                    try:
                        curve = BRepAdaptor_Curve(edge)
                        discretizer = GCPnts_UniformDeflection(curve, 0.1)
                        if discretizer.IsDone():
                            points = []
                            for i in range(1, discretizer.NbPoints() + 1):
                                p = discretizer.Value(i)
                                # Project onto XY (top view)
                                points.append((p.X(), -p.Y()))  # flip Y for SVG
                                min_x = min(min_x, p.X())
                                max_x = max(max_x, p.X())
                                min_y = min(min_y, -p.Y())
                                max_y = max(max_y, -p.Y())
                            if len(points) > 1:
                                all_lines.append(points)
                    except Exception:
                        pass
                    explorer.Next()

            if not all_lines:
                logger.warning("Keine Kanten gefunden.")
                return

            # SVG generation
            margin = 10
            width = max_x - min_x + 2 * margin
            height = max_y - min_y + 2 * margin

            svg_lines = [
                f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'viewBox="{min_x - margin} {min_y - margin} {width} {height}" '
                f'width="{width}mm" height="{height}mm">',
                '<g stroke="black" stroke-width="0.2" fill="none">',
            ]
            for pts in all_lines:
                d = f'M {pts[0][0]:.3f},{pts[0][1]:.3f}'
                for p in pts[1:]:
                    d += f' L {p[0]:.3f},{p[1]:.3f}'
                svg_lines.append(f'  <path d="{d}"/>')
            svg_lines.append('</g>')
            svg_lines.append('</svg>')

            with open(path, 'w') as f:
                f.write('\n'.join(svg_lines))

            logger.success(f"SVG exportiert: {path}")

        except Exception as e:
            logger.error(f"SVG Export Fehler: {e}")
            import traceback
            traceback.print_exc()

    def _import_svg(self):
        """Import SVG as sketch geometry."""
        path, _ = QFileDialog.getOpenFileName(self, "Import SVG", "", "SVG Files (*.svg)")
        if not path:
            return

        try:
            import xml.etree.ElementTree as ET
            import re

            tree = ET.parse(path)
            root = tree.getroot()
            ns = {'svg': 'http://www.w3.org/2000/svg'}

            # Create new sketch
            from sketcher import Sketch
            from sketcher.geometry import Line as SketchLine, Point2D

            sketch = Sketch(name=f"SVG Import")
            sketch.plane_origin = (0, 0, 0)
            sketch.plane_normal = (0, 0, 1)
            sketch.plane_x_dir = (1, 0, 0)
            sketch.plane_y_dir = (0, 1, 0)

            def parse_path_d(d_str):
                """Parse SVG path d attribute into line segments."""
                segments = []
                current = [0.0, 0.0]
                tokens = re.findall(r'[MLHVZCSQTAmlhvzcsqta]|[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', d_str)
                i = 0
                cmd = 'M'
                while i < len(tokens):
                    t = tokens[i]
                    if t.isalpha():
                        cmd = t
                        i += 1
                        continue
                    if cmd in ('M', 'm'):
                        x, y = float(tokens[i]), float(tokens[i+1])
                        if cmd == 'm':
                            current = [current[0] + x, current[1] + y]
                        else:
                            current = [x, y]
                        i += 2
                        cmd = 'L' if cmd == 'M' else 'l'
                    elif cmd in ('L', 'l'):
                        x, y = float(tokens[i]), float(tokens[i+1])
                        start = list(current)
                        if cmd == 'l':
                            current = [current[0] + x, current[1] + y]
                        else:
                            current = [x, y]
                        segments.append((start, list(current)))
                        i += 2
                    elif cmd in ('H', 'h'):
                        x = float(tokens[i])
                        start = list(current)
                        if cmd == 'h':
                            current[0] += x
                        else:
                            current[0] = x
                        segments.append((start, list(current)))
                        i += 1
                    elif cmd in ('V', 'v'):
                        y = float(tokens[i])
                        start = list(current)
                        if cmd == 'v':
                            current[1] += y
                        else:
                            current[1] = y
                        segments.append((start, list(current)))
                        i += 1
                    elif cmd in ('Z', 'z'):
                        i += 1
                    else:
                        i += 1  # skip unsupported commands
                return segments

            # Parse all <path> elements
            line_count = 0
            for path_elem in root.iter('{http://www.w3.org/2000/svg}path'):
                d = path_elem.get('d', '')
                if d:
                    segs = parse_path_d(d)
                    for (x1, y1), (x2, y2) in segs:
                        line = SketchLine(
                            start=Point2D(x1, -y1),  # flip Y back
                            end=Point2D(x2, -y2)
                        )
                        sketch.geometry.append(line)
                        line_count += 1

            # Also parse <line> elements
            for line_elem in root.iter('{http://www.w3.org/2000/svg}line'):
                x1 = float(line_elem.get('x1', 0))
                y1 = float(line_elem.get('y1', 0))
                x2 = float(line_elem.get('x2', 0))
                y2 = float(line_elem.get('y2', 0))
                line = SketchLine(
                    start=Point2D(x1, -y1),
                    end=Point2D(x2, -y2)
                )
                sketch.geometry.append(line)
                line_count += 1

            # Also parse <rect> elements
            for rect_elem in root.iter('{http://www.w3.org/2000/svg}rect'):
                x = float(rect_elem.get('x', 0))
                y = float(rect_elem.get('y', 0))
                w = float(rect_elem.get('width', 0))
                h = float(rect_elem.get('height', 0))
                corners = [(x, -y), (x+w, -y), (x+w, -(y+h)), (x, -(y+h))]
                for i in range(4):
                    p1 = corners[i]
                    p2 = corners[(i+1) % 4]
                    line = SketchLine(
                        start=Point2D(p1[0], p1[1]),
                        end=Point2D(p2[0], p2[1])
                    )
                    sketch.geometry.append(line)
                    line_count += 1

            if line_count == 0:
                logger.warning("Keine Geometrie in SVG gefunden.")
                return

            self.document.sketches.append(sketch)
            self.browser.refresh()
            logger.success(f"SVG importiert: {line_count} Linien als Sketch '{sketch.name}'")

        except Exception as e:
            logger.error(f"SVG Import Fehler: {e}")
            import traceback
            traceback.print_exc()

    def _import_step(self):
        """
        Phase 8.3: STEP Import mit Auto-Healing.

        Importiert STEP-Datei und erstellt neue Bodies.
        Unterstützt AP214 und AP242 Dateien.
        """
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("STEP importieren"),
            "",
            "STEP Files (*.step *.stp);;All Files (*)"
        )

        if not path:
            return

        try:
            # Document.import_step nutzen (Phase 8.3)
            new_bodies = self.document.import_step(path, auto_heal=True)

            if new_bodies:
                # Browser aktualisieren (macht Bodies sichtbar)
                self.browser.refresh()

                # WICHTIG: Gleiche Refresh-Logik wie _finish_sketch verwenden!
                # Dies triggert _update_viewport_all_impl() was:
                # 1. clear_bodies() aufruft
                # 2. Alle sichtbaren Bodies neu hinzufügt
                self._trigger_viewport_update()

                # Zusätzlich: Kamera auf neue Objekte ausrichten
                # (nach kurzer Verzögerung, da _trigger_viewport_update async ist)
                from PySide6.QtCore import QTimer
                QTimer.singleShot(100, lambda: self._focus_camera_on_bodies(new_bodies))

                logger.success(f"STEP Import: {len(new_bodies)} Body(s) importiert von {path}")
            else:
                logger.warning("STEP Import: Keine Bodies erstellt")

        except Exception as e:
            logger.error(f"STEP Import Fehler: {e}")
            import traceback
            traceback.print_exc()

    def _focus_camera_on_bodies(self, bodies):
        """Fokussiert die Kamera auf die angegebenen Bodies."""
        try:
            if HAS_PYVISTA and self.viewport_3d and self.viewport_3d.plotter:
                self.viewport_3d.plotter.reset_camera()
                request_render(self.viewport_3d.plotter)  # PERFORMANCE: Use debounced queue
        except Exception as e:
            logger.debug(f"Camera focus Fehler (ignoriert): {e}")

    def _create_pattern(self):
        """
        Erstellt Linear oder Circular Pattern (CAD-Style).
        Erzeugt N Kopien des selektierten Bodies mit Transform-Features.
        """
        # Body-Selektion prüfen
        selected_bodies = self.browser.get_selected_bodies()

        if len(selected_bodies) != 1:
            logger.warning("Bitte genau einen Body für Pattern auswählen")
            return

        body = selected_bodies[0]

        # Pattern-Dialog öffnen
        from gui.dialogs.pattern_dialog import PatternDialog

        dialog = PatternDialog(body, self)
        if not dialog.exec():
            return  # Abgebrochen

        pattern_data = dialog.get_pattern_data()
        if not pattern_data:
            return

        from modeling import TransformFeature
        from modeling.cad_tessellator import CADTessellator

        pattern_type = pattern_data["type"]
        count = pattern_data["count"]

        logger.info(f"Erstelle {pattern_type} Pattern mit {count} Kopien für {body.name}")

        # Performance Optimization 1.2: Per-Shape Cache-Invalidierung für Pattern-Bodies
        try:
            new_bodies = []

            for i in range(1, count):  # Start bei 1 (Original bleibt)
                # Kopiere Body
                import copy
                new_body = copy.deepcopy(body)
                new_body.id = f"{body.id}_pattern_{i}"
                new_body.name = f"{body.name} (Pattern {i})"

                # ✅ FIX: Clear entire cache for consistency
                # Deepcopy shouldn't reuse IDs, but full clear is safer
                CADTessellator.notify_body_changed()

                # Erstelle Transform-Feature basierend auf Pattern-Typ
                if pattern_type == "linear":
                    spacing = pattern_data["spacing"]
                    axis = pattern_data["axis"]

                    # Offset für dieses Element
                    offset = spacing * i

                    translation = [0, 0, 0]
                    if axis == "X":
                        translation[0] = offset
                    elif axis == "Y":
                        translation[1] = offset
                    elif axis == "Z":
                        translation[2] = offset

                    transform_feature = TransformFeature(
                        mode="move",
                        data={"translation": translation},
                        name=f"Pattern Move {i}"
                    )

                elif pattern_type == "circular":
                    axis = pattern_data["axis"]
                    angle_per_copy = pattern_data["angle"]

                    # Rotation für dieses Element
                    total_angle = angle_per_copy * i

                    # Berechne Body-Center als Rotation-Center
                    if hasattr(new_body, '_build123d_solid') and new_body._build123d_solid:
                        bounds = new_body._build123d_solid.bounding_box()
                        center = [
                            (bounds.min.X + bounds.max.X) / 2,
                            (bounds.min.Y + bounds.max.Y) / 2,
                            (bounds.min.Z + bounds.max.Z) / 2
                        ]
                    else:
                        center = [0, 0, 0]

                    transform_feature = TransformFeature(
                        mode="rotate",
                        data={"axis": axis, "angle": total_angle, "center": center},
                        name=f"Pattern Rotate {i}"
                    )

                # Feature zum Body hinzufügen
                new_body.add_feature(transform_feature)

                # Body zum Dokument hinzufügen
                self.document.add_body(new_body, set_active=False)
                new_bodies.append(new_body)

            # UI aktualisieren
            for new_body in new_bodies:
                self._update_body_from_build123d(new_body, new_body._build123d_solid)

            self.browser.refresh()

            logger.success(f"Pattern erstellt: {count} Kopien von {body.name}")

        except Exception as e:
            logger.exception(f"Pattern-Error: {e}")

    def _show_not_implemented(self, feature: str):
        logger.info(f"{feature} - Coming soon!")

    # ── Pattern Feature (New UX) ──────────────────────────────

    def _get_body_center(self, body) -> tuple:
        """Berechnet das Zentrum eines Bodies aus Bounding Box."""
        try:
            if body.vtk_mesh is not None:
                bounds = body.vtk_mesh.bounds
                center = (
                    (bounds[0] + bounds[1]) / 2,
                    (bounds[2] + bounds[3]) / 2,
                    (bounds[4] + bounds[5]) / 2
                )
                return center
            elif body._build123d_solid is not None:
                bb = body._build123d_solid.bounding_box()
                return (
                    (bb.min.X + bb.max.X) / 2,
                    (bb.min.Y + bb.max.Y) / 2,
                    (bb.min.Z + bb.max.Z) / 2
                )
        except Exception as e:
            logger.debug(f"Body center calculation failed: {e}")
        return (0.0, 0.0, 0.0)

    def _duplicate_body(self, body, new_name: str):
        """Erstellt eine Kopie eines Bodies mit transformiertem Solid."""
        from modeling import Body
        from build123d import Solid

        new_body = Body(name=new_name, document=self.document)
        new_body.id = f"{body.id}_{new_name.replace(' ', '_')}"

        if body._build123d_solid is not None:
            # Kopiere das Solid (build123d .copy() auf dem Solid)
            try:
                new_body._build123d_solid = body._build123d_solid.copy()
            except Exception as e:
                logger.debug(f"[main_window] Fehler beim Kopieren des Bodies (Fallback wird verwendet): {e}")
                # Fallback: Wrapped Shape kopieren
                from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
                copier = BRepBuilderAPI_Copy(body._build123d_solid.wrapped)
                new_body._build123d_solid = Solid(copier.Shape())

        new_body.invalidate_mesh()
        return new_body

    def _start_pattern(self):
        """
        Startet Pattern-Modus mit Viewport-Selektion (wie Fillet/Chamfer).

        UX-Pattern:
        - Falls Body ausgewählt → sofort starten
        - Falls kein Body → Pending-Mode, warte auf Klick
        """
        self._clear_transient_previews(reason="start_pattern", clear_interaction_modes=True)
        selected_bodies = self.browser.get_selected_bodies()

        if not selected_bodies:
            # Pending Mode aktivieren
            self._pending_pattern_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)

            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)

            logger.info("Pattern: Klicke auf einen Körper in der 3D-Ansicht")
            return

        # Body gewählt → direkt starten
        body = selected_bodies[0]
        self._activate_pattern_for_body(body)

    def _on_body_clicked_for_pattern(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body für Pattern angeklickt wird."""
        self._pending_pattern_mode = False

        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.warning(f"Body {body_id} nicht gefunden")
            return

        self._activate_pattern_for_body(body)

    def _activate_pattern_for_body(self, body):
        """Aktiviert Pattern-Modus für einen Body."""
        if body._build123d_solid is None:
            logger.warning("Pattern erfordert einen CAD-Body (kein Mesh)")
            return

        self._pattern_mode = True
        self._pattern_target_body = body
        self.pattern_panel.set_target_body(body)
        self.pattern_panel.reset()
        self.pattern_panel.show_at(self.viewport_3d)

        logger.info(f"Pattern für '{body.name}' - Parameter anpassen, OK zum Bestätigen")

        # Initial preview generieren
        self._update_pattern_preview(self.pattern_panel.get_pattern_data())

    def _on_pattern_parameters_changed(self, params: dict):
        """Handler für Live-Preview wenn Parameter geändert werden."""
        if self._pattern_mode:
            self._update_pattern_preview(params)

    def _update_pattern_preview(self, params: dict):
        """Generiert/aktualisiert Pattern-Preview."""
        # Alte Preview entfernen
        self._preview_clear_group("pattern")

        if not self._pattern_target_body:
            return

        body = self._pattern_target_body
        count = params.get("count", 3)
        pattern_type = params.get("type", "linear")

        try:
            import pyvista as pv
            from build123d import Rotation, Location, Vector

            solid = body._build123d_solid
            if solid is None:
                return

            for i in range(1, count):  # Skip original (i=0)
                if pattern_type == "linear":
                    spacing = params.get("spacing", 10.0)
                    axis = params.get("axis", "X")

                    offset = {"X": (spacing * i, 0, 0),
                              "Y": (0, spacing * i, 0),
                              "Z": (0, 0, spacing * i)}[axis]

                    loc = Location(Vector(*offset))
                    preview_solid = solid.moved(loc)

                else:  # circular
                    total_angle = params.get("angle", 360.0)
                    axis = params.get("axis", "Z")
                    full_circle = params.get("full_circle", True)

                    if full_circle:
                        angle_per_copy = total_angle / count
                    else:
                        angle_per_copy = total_angle / (count - 1) if count > 1 else total_angle

                    angle = angle_per_copy * i

                    # Center from params (body_center, origin, or custom)
                    center_mode = params.get("center_mode", "body_center")
                    if center_mode == "origin":
                        center = (0.0, 0.0, 0.0)
                    elif center_mode == "custom" and params.get("center"):
                        center = params["center"]
                    else:
                        center = self._get_body_center(body)

                    rot = Rotation(
                        *(1 if axis == "X" else 0, 1 if axis == "Y" else 0, 1 if axis == "Z" else 0),
                        angle
                    )
                    loc = Location(Vector(*center)) * Location(rot) * Location(Vector(*[-c for c in center]))
                    preview_solid = solid.moved(loc)

                # Tessellieren und als Preview anzeigen
                from modeling.cad_tessellator import CADTessellator
                mesh, _ = CADTessellator.tessellate(preview_solid)

                if mesh:
                    actor_name = f"_pattern_preview_{i}"
                    self.viewport_3d.plotter.add_mesh(
                        mesh,
                        color="#4488ff",
                        opacity=0.5,
                        name=actor_name
                    )
                    self._preview_track_actor("pattern", actor_name)

            request_render(self.viewport_3d.plotter)

        except Exception as e:
            logger.debug(f"Pattern preview error: {e}")

    def _clear_pattern_preview(self):
        """Entfernt Pattern-Preview."""
        self._preview_clear_group("pattern")

    def _on_pattern_confirmed(self):
        """Handler wenn Pattern bestätigt wird."""
        if not self._pattern_mode or not self._pattern_target_body:
            return

        body = self._pattern_target_body
        params = self.pattern_panel.get_pattern_data()

        # Preview entfernen
        self._clear_pattern_preview()

        # Pattern erstellen (alte Logik nutzen)
        self._execute_pattern(body, params)

        # Mode beenden
        self._pattern_mode = False
        self._pattern_target_body = None
        self.pattern_panel.hide()

    def _on_pattern_cancelled(self):
        """Handler wenn Pattern abgebrochen wird."""
        self._clear_pattern_preview()
        self._pattern_mode = False
        self._pattern_target_body = None
        self._pattern_center_pick_mode = False
        self.pattern_panel.hide()
        logger.info("Pattern abgebrochen")

    def _on_pattern_center_pick_requested(self):
        """Handler wenn User Custom Center auswählen will."""
        self._pattern_center_pick_mode = True
        from PySide6.QtCore import Qt
        self.viewport_3d.setCursor(Qt.CrossCursor)
        # Enable point picking mode in viewport (reuse measure mode infrastructure)
        self.viewport_3d.measure_mode = True
        self.statusBar().showMessage("Klicke auf einen Punkt im Viewport als Rotationszentrum")
        logger.info("Pattern: Klicke Punkt für Rotationszentrum")

    def _on_pattern_center_picked(self, point: tuple):
        """Handler wenn ein Zentrum-Punkt gepickt wurde."""
        if not self._pattern_center_pick_mode:
            return

        self._pattern_center_pick_mode = False
        from PySide6.QtCore import Qt
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        # Disable point picking mode
        self.viewport_3d.measure_mode = False

        # Set the custom center in the panel
        self.pattern_panel.set_custom_center(point[0], point[1], point[2])
        self.statusBar().showMessage(f"Rotationszentrum: ({point[0]:.2f}, {point[1]:.2f}, {point[2]:.2f})")
        logger.info(f"Pattern Center gesetzt: {point}")

    def _execute_pattern(self, body, params: dict):
        """Führt Pattern aus und erstellt die Bodies.

        WICHTIG: Pattern-Bodies bekommen KEINE Features!
        Der Solid wird direkt kopiert und transformiert.
        Das verhindert leere Bodies nach _rebuild().
        """
        from modeling import Body
        from build123d import Location, Axis

        pattern_type = params["type"]
        count = params["count"]

        logger.info(f"Erstelle {pattern_type} Pattern mit {count} Kopien für {body.name}")

        if body._build123d_solid is None:
            logger.error("Pattern: Source-Body hat keinen Solid!")
            return

        new_bodies = []

        try:
            for i in range(1, count):
                # 1. Body mit Solid-Kopie erstellen
                new_body = self._duplicate_body(body, f"{body.name} ({i+1})")
                new_body.id = f"{body.id}_pattern_{i}"

                # 2. Transform DIREKT auf den kopierten Solid anwenden (ohne Features!)
                if new_body._build123d_solid is not None:
                    solid = new_body._build123d_solid

                    if pattern_type == "linear":
                        spacing = params["spacing"]
                        axis = params["axis"]

                        # Linear translation
                        if axis == "X":
                            solid = solid.move(Location((spacing * i, 0, 0)))
                        elif axis == "Y":
                            solid = solid.move(Location((0, spacing * i, 0)))
                        else:  # Z
                            solid = solid.move(Location((0, 0, spacing * i)))

                    else:  # circular
                        axis_name = params["axis"]
                        total_angle = params["angle"]
                        full_circle = params.get("full_circle", True)

                        if full_circle:
                            angle_per_copy = total_angle / count
                        else:
                            angle_per_copy = total_angle / (count - 1) if count > 1 else total_angle

                        total_angle_for_copy = angle_per_copy * i

                        # Center ermitteln
                        center_mode = params.get("center_mode", "body_center")
                        if center_mode == "origin":
                            center = (0.0, 0.0, 0.0)
                        elif center_mode == "custom" and params.get("center"):
                            center = params["center"]
                        else:
                            center = self._get_body_center(body)

                        cx, cy, cz = center

                        # Rotation um beliebigen Punkt:
                        # 1. Move to origin, 2. Rotate, 3. Move back
                        axis_map = {"X": Axis.X, "Y": Axis.Y, "Z": Axis.Z}
                        rot_axis = axis_map.get(axis_name, Axis.Z)

                        solid = solid.move(Location((-cx, -cy, -cz)))
                        solid = solid.rotate(rot_axis, total_angle_for_copy)
                        solid = solid.move(Location((cx, cy, cz)))

                    # Transformierten Solid zuweisen
                    new_body._build123d_solid = solid
                    new_body.invalidate_mesh()

                # Body zu Document hinzufügen
                self.document.add_body(new_body, set_active=False)
                new_bodies.append(new_body)

            # UI aktualisieren
            for new_body in new_bodies:
                self._update_body_mesh(new_body)

            self.browser.refresh()
            self._update_viewport_all_impl()

            logger.success(f"Pattern erstellt: {count} Kopien von {body.name}")

        except Exception as e:
            logger.exception(f"Pattern-Error: {e}")

    # ── Measure Tool ──────────────────────────────────────────

    def _start_measure_mode(self):
        """Startet den Mess-Modus: 2 Punkte anklicken -> Distanz anzeigen"""
        self._clear_transient_previews(reason="start_measure_mode", clear_interaction_modes=True)
        self._measure_points = [None, None]
        self._measure_pick_target = 1
        self._measure_active = True
        self.viewport_3d.measure_mode = True
        self.statusBar().showMessage(tr("Measure: Click first point on model"))
        logger.info("Measure mode: Click 2 points to measure distance. Esc to cancel.")

        self._clear_measure_actors()
        if hasattr(self, "measure_panel"):
            self.measure_panel.reset()
            self.measure_panel.set_status(tr("Pick first point"))
            self.measure_panel.show_at(self.viewport_3d)

    def _on_measure_point_picked(self, point):
        """Wird aufgerufen wenn ein Punkt im Measure-Modus gepickt wurde"""
        # Pattern Center Pick hat Priorität
        if getattr(self, '_pattern_center_pick_mode', False):
            self._on_pattern_center_picked(point)
            return

        if not getattr(self, '_measure_active', False):
            return

        target = getattr(self, "_measure_pick_target", None)
        if target not in (1, 2):
            target = 1 if self._measure_points[0] is None else 2

        idx = 0 if target == 1 else 1
        self._measure_points[idx] = point

        self._update_measure_visuals()
        self._update_measure_ui()

        # Auto-advance if other point missing
        if self._measure_points[0] is None or self._measure_points[1] is None:
            next_target = 1 if self._measure_points[0] is None else 2
            self._measure_pick_target = next_target
            self._measure_active = True
            self.viewport_3d.measure_mode = True
            if hasattr(self, "measure_panel"):
                self.measure_panel.set_status(tr("Pick first point") if next_target == 1 else tr("Pick second point"))
            self.statusBar().showMessage(tr("Measure: Click first point on model") if next_target == 1 else tr("Measure: Click second point"))
        else:
            self._measure_pick_target = None
            self._measure_active = False
            self.viewport_3d.measure_mode = False
            if hasattr(self, "measure_panel"):
                self.measure_panel.set_status(tr("Done"))

    def _clear_measure_actors(self, render: bool = True):
        """Entfernt alle Mess-Visualisierungen"""
        self._preview_clear_group("measure", render=render)

    def _update_measure_visuals(self):
        """Aktualisiert alle Mess-Visualisierungen (Punkte, Linie, Label)."""
        self._clear_measure_actors(render=False)
        plotter = getattr(self.viewport_3d, "plotter", None)
        if not plotter:
            return

        import numpy as np
        import pyvista as pv

        p1 = self._measure_points[0]
        p2 = self._measure_points[1]

        if p1 is not None:
            actor_name = "_measure_pt_1"
            sphere = pv.Sphere(radius=0.3, center=p1)
            plotter.add_mesh(
                sphere, color="#00ff88", name=actor_name,
                reset_camera=False, pickable=False
            )
            self._preview_track_actor("measure", actor_name)

        if p2 is not None:
            actor_name = "_measure_pt_2"
            sphere = pv.Sphere(radius=0.3, center=p2)
            plotter.add_mesh(
                sphere, color="#00ff88", name=actor_name,
                reset_camera=False, pickable=False
            )
            self._preview_track_actor("measure", actor_name)

        if p1 is not None and p2 is not None:
            p1n = np.array(p1)
            p2n = np.array(p2)
            dist = np.linalg.norm(p2n - p1n)
            line = pv.Line(p1n, p2n)
            actor_name = "_measure_line"
            plotter.add_mesh(
                line, color="#ffaa00", line_width=3,
                name=actor_name, reset_camera=False, pickable=False
            )
            self._preview_track_actor("measure", actor_name)

            mid = (p1n + p2n) / 2
            label_text = f"{dist:.2f} mm"
            actor_name = "_measure_label"
            plotter.add_point_labels(
                [mid], [label_text],
                name=actor_name,
                font_size=16, text_color="#ffaa00",
                point_color="#ffaa00", point_size=0,
                shape=None, fill_shape=False,
                reset_camera=False, pickable=False
            )
            self._preview_track_actor("measure", actor_name)

            self.statusBar().showMessage(tr("Distance: {d:.2f} mm").format(d=dist))
            logger.success(f"Measure: {dist:.2f} mm  (P1={p1n}, P2={p2n})")
        request_render(plotter)

    def _update_measure_ui(self):
        if not hasattr(self, "measure_panel"):
            return
        p1 = self._measure_points[0]
        p2 = self._measure_points[1]
        self.measure_panel.set_points(p1, p2)
        if p1 is not None and p2 is not None:
            import numpy as np
            dist = np.linalg.norm(np.array(p2) - np.array(p1))
            self.measure_panel.set_distance(dist)
        else:
            self.measure_panel.set_distance(None)

    def _on_measure_pick_requested(self, which: int):
        """User wants to re-pick P1 or P2."""
        if not hasattr(self, "_measure_points"):
            self._measure_points = [None, None]
        self._measure_pick_target = which
        self._measure_active = True
        self.viewport_3d.measure_mode = True
        if hasattr(self, "measure_panel"):
            self.measure_panel.set_status(tr("Pick first point") if which == 1 else tr("Pick second point"))
        self.statusBar().showMessage(tr("Measure: Click first point on model") if which == 1 else tr("Measure: Click second point"))

    def _clear_measure_points(self):
        self._measure_points = [None, None]
        self._measure_pick_target = 1
        self._measure_active = True
        self.viewport_3d.measure_mode = True
        self._clear_measure_actors()
        if hasattr(self, "measure_panel"):
            self.measure_panel.reset()
        self.statusBar().showMessage(tr("Measure: Click first point on model"))

    def _close_measure_panel(self):
        self._cancel_measure_mode()
        if hasattr(self, "measure_panel"):
            self.measure_panel.hide()

    def _cancel_measure_mode(self):
        """Bricht den Mess-Modus ab"""
        self._measure_active = False
        self._measure_points = [None, None]
        self._measure_pick_target = None
        self.viewport_3d.measure_mode = False
        self._clear_measure_actors()
        self.statusBar().showMessage(tr("Ready"))
        if hasattr(self, "measure_panel"):
            self.measure_panel.reset()
            self.measure_panel.set_status(tr("Inactive"))
        logger.info("Measure cancelled")

    # ── End Measure Tool ──────────────────────────────────────

    # ── Smart Undo/Redo (Sketch-Editor priorisiert) ──────────────────────────────────────

    def _smart_undo(self):
        """
        Smart Undo: Priorisiert Sketch-Editor Undo wenn aktiv.

        Wenn im Sketch-Modus: Ruft sketch_editor.undo() auf
        Sonst: Ruft 3D undo_stack.undo() auf
        """
        if self.mode == "sketch" and hasattr(self, 'sketch_editor') and self.sketch_editor:
            self.sketch_editor.undo()
            logger.debug("Smart Undo: Sketch-Editor")
        else:
            if self.undo_stack.canUndo():
                self.undo_stack.undo()
                self._update_tnp_stats()
                logger.debug("Smart Undo: 3D UndoStack")

    def _smart_redo(self):
        """
        Smart Redo: Priorisiert Sketch-Editor Redo wenn aktiv.

        Wenn im Sketch-Modus: Ruft sketch_editor.redo() auf
        Sonst: Ruft 3D undo_stack.redo() auf
        """
        if self.mode == "sketch" and hasattr(self, 'sketch_editor') and self.sketch_editor:
            self.sketch_editor.redo()
            logger.debug("Smart Redo: Sketch-Editor")
        else:
            if self.undo_stack.canRedo():
                self.undo_stack.redo()
                self._update_tnp_stats()
                logger.debug("Smart Redo: 3D UndoStack")

    def _show_parameters_dialog(self):
        """Öffnet den Parameter-Dialog (Style)."""
        from core.parameters import get_parameters

        params = get_parameters()
        dialog = ParameterDialog(params, self)
        dialog.parameters_changed.connect(self._on_parameters_changed)
        dialog.exec_()

    def _on_parameters_changed(self):
        """Reagiert auf Änderungen der Parameter — re-solve Constraints mit Formeln."""
        from sketcher.constraints import resolve_constraint_value

        # 1. Alle Sketches: Constraints mit Formeln aktualisieren + re-solve
        if hasattr(self, 'document') and self.document:
            for sketch in getattr(self.document, 'sketches', []):
                needs_solve = False
                for c in sketch.constraints:
                    if c.formula:
                        resolve_constraint_value(c)
                        needs_solve = True
                if needs_solve:
                    sketch.solve()

        # 2. Sketch-Editor aktualisieren
        if hasattr(self, 'sketch_editor') and self.sketch_editor:
            self.sketch_editor.request_update()

        # 3. 3D-Features mit Formeln aktualisieren
        if hasattr(self, 'document') and self.document:
            for body in getattr(self.document, 'bodies', []):
                if self._resolve_feature_formulas(body):
                    body._rebuild()
                    body.invalidate_mesh()

        logger.info("Parameter aktualisiert — Constraints und Features neu berechnet")

    def _resolve_feature_formulas(self, body) -> bool:
        """Löst Feature-Formeln auf. Gibt True zurück wenn sich etwas geändert hat."""
        from core.parameters import get_parameters
        params = get_parameters()
        if not params:
            return False

        changed = False
        for feat in getattr(body, 'features', []):
            # Prüfe alle *_formula Felder
            for attr in dir(feat):
                if attr.endswith('_formula'):
                    formula = getattr(feat, attr, None)
                    if formula:
                        value_attr = attr[:-8]  # Remove '_formula'
                        try:
                            params.set("__resolve__", formula)
                            try:
                                val = params.get("__resolve__")
                                if val is not None and getattr(feat, value_attr, None) != val:
                                    setattr(feat, value_attr, val)
                                    changed = True
                            finally:
                                try:
                                    params.delete("__resolve__")
                                except Exception:
                                    pass
                        except Exception as e:
                            logger.warning(f"Feature-Formel '{formula}' für {value_attr} fehlgeschlagen: {e}")
        return changed

    def _change_language(self):
        """Sprache wechseln — speichert und zeigt Restart-Hinweis."""
        from gui.language_dialog import ask_language_switch
        from i18n import get_language
        old_lang = get_language()
        chosen = ask_language_switch(self)
        if chosen and chosen != old_lang:
            QMessageBox.information(
                self,
                "Language Changed" if chosen == "en" else "Sprache geändert",
                "Please restart MashCAD to apply the new language."
                if chosen == "en" else
                "Bitte starte MashCAD neu, um die neue Sprache zu übernehmen."
            )

    def _show_about(self):
        """Über-Dialog"""
        QMessageBox.about(self, tr("Über MashCad"),
            f"<h2>{APP_NAME}</h2>"
            f"<p>Version {VERSION}</p>"
            f"<p>Schlankes parametrisches CAD für 3D-Druck</p>"
            f"<p>{COPYRIGHT}</p>"
            f"<p><b>Features:</b></p>"
            f"<ul>"
            f"<li>2D Sketch mit Constraints</li>"
            f"<li>3D Extrusion</li>"
            f"<li>PyVista/VTK Rendering</li>"
            f"</ul>"
        )
    
    # ==================== FILLET / CHAMFER ====================
    
    def _start_fillet(self):
        """
        Startet den neuen interaktiven Fillet-Workflow.
        Verwendet EdgeSelectionMixin für Tube-basierte Kantenauswahl.

        UX-Pattern wie Transform:
        - Falls Body ausgewählt → sofort starten
        - Falls kein Body → Pending-Mode, warte auf Klick
        """
        self._start_fillet_chamfer_mode("fillet")

    def _start_chamfer(self):
        """
        Startet den neuen interaktiven Chamfer-Workflow.
        Verwendet EdgeSelectionMixin für Tube-basierte Kantenauswahl.

        UX-Pattern wie Transform:
        - Falls Body ausgewählt → sofort starten
        - Falls kein Body → Pending-Mode, warte auf Klick
        """
        self._start_fillet_chamfer_mode("chamfer")

    def _start_fillet_chamfer_mode(self, mode: str):
        """
        Gemeinsame Logik für Fillet/Chamfer mit Transform-ähnlicher UX.

        Args:
            mode: "fillet" oder "chamfer"
        """
        # Prüfe ob Body im Browser ausgewählt
        selected_bodies = self.browser.get_selected_bodies()

        # Fall 1: Kein Body gewählt → Pending-Mode (wie bei Transform)
        if not selected_bodies:
            self._pending_fillet_mode = mode
            self.viewport_3d.setCursor(Qt.CrossCursor)

            # Aktiviere Body-Highlighting im Viewport (gleiche Methode wie Transform)
            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)

            logger.info(f"{mode.capitalize()}: Klicke auf einen Körper in der 3D-Ansicht oder wähle im Browser")
            return

        # Fall 2: Body gewählt → direkt starten
        body = selected_bodies[0]
        self._activate_fillet_chamfer_for_body(body, mode)

    def _on_body_clicked_for_fillet(self, body_id: str):
        """
        Callback wenn im Pending-Mode ein Body angeklickt wird.
        Wird vom _on_viewport_body_clicked Handler aufgerufen.
        """
        mode = getattr(self, '_pending_fillet_mode', 'fillet')
        self._pending_fillet_mode = None

        # Pending-Mode deaktivieren (gleiche Methode wie Transform)
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        # Body finden
        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.warning(f"Body {body_id} nicht gefunden")
            return

        self._activate_fillet_chamfer_for_body(body, mode)

    def _activate_fillet_chamfer_for_body(self, body, mode: str):
        """
        Aktiviert Fillet/Chamfer für einen spezifischen Body.

        Args:
            body: Body-Objekt
            mode: "fillet" oder "chamfer"
        """
        if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
            logger.warning(f"'{body.name}' hat keine CAD-Daten (nur Mesh).")
            return

        self._fillet_mode = mode
        self._fillet_body = body
        self._pending_fillet_mode = None

        # Body-Lookup Callback setzen
        self.viewport_3d.set_edge_selection_callbacks(
            get_body_by_id=lambda bid: next((b for b in self.document.bodies if b.id == bid), None)
        )

        # Edge Selection Mode starten
        self.viewport_3d.start_edge_selection_mode(body.id)

        # Panel anzeigen
        self.fillet_panel.set_target_body(body)
        self.fillet_panel.set_mode(mode)
        self.fillet_panel.show_at(self.viewport_3d)

        logger.info(f"{mode.capitalize()}: Klicke auf Kanten von '{body.name}' (A = alle wählen, ESC = abbrechen)")

    def _on_edge_selection_changed(self, count: int):
        """
        Callback wenn sich die Kantenauswahl ändert.
        Aktualisiert das Panel mit der Anzahl selektierter Kanten.
        """
        # Fillet/Chamfer Panel
        if hasattr(self, 'fillet_panel') and self.fillet_panel.isVisible():
            self.fillet_panel.update_edge_count(count)

        # N-Sided Patch Panel
        if getattr(self, '_nsided_patch_mode', False) and hasattr(self, 'nsided_patch_panel'):
            self.nsided_patch_panel.update_edge_count(count)

        # Sweep Path Phase (Phase 6)
        if getattr(self, '_sweep_mode', False) and getattr(self, '_sweep_phase', None) == 'path':
            if count > 0:
                edges = self.viewport_3d.get_selected_edges()
                self._on_edge_selected_for_sweep(edges)

    def _on_fillet_confirmed(self):
        """
        Wendet Fillet/Chamfer über die Feature-Pipeline mit Undo/Redo an.
        """
        radius = self.fillet_panel.get_radius()
        body = self.fillet_panel.get_target_body()
        mode = getattr(self, '_fillet_mode', 'fillet')

        # Selektierte Kanten vom Viewport holen
        edges = self.viewport_3d.get_selected_edges()

        if not edges:
            res = QMessageBox.question(
                self, "Keine Kanten",
                "Keine Kanten ausgewählt. Alle Kanten bearbeiten?",
                QMessageBox.Yes | QMessageBox.No
            )
            if res == QMessageBox.Yes:
                # Alle Kanten nehmen
                edges = list(body._build123d_solid.edges())
            else:
                return

        # Feature erstellen und via Undo-Stack anwenden
        logger.info(f"Wende {mode} auf {len(edges)} Kanten an (r={radius})...")

        try:
            from gui.commands.feature_commands import AddFeatureCommand
            from modeling.geometric_selector import create_geometric_selectors_from_edges
            from modeling.tnp_system import ShapeType

            selected_edge_indices = []
            if hasattr(self.viewport_3d, "get_selected_edge_topology_indices"):
                selected_edge_indices = self.viewport_3d.get_selected_edge_topology_indices() or []
            if not selected_edge_indices and body is not None and hasattr(body, "_build123d_solid") and body._build123d_solid:
                try:
                    all_edges = list(body._build123d_solid.edges())

                    def _is_same_edge(edge_a, edge_b) -> bool:
                        try:
                            wa = edge_a.wrapped if hasattr(edge_a, "wrapped") else edge_a
                            wb = edge_b.wrapped if hasattr(edge_b, "wrapped") else edge_b
                            return wa.IsSame(wb)
                        except Exception:
                            return edge_a is edge_b

                    for edge in edges:
                        for edge_idx, candidate in enumerate(all_edges):
                            if _is_same_edge(candidate, edge):
                                selected_edge_indices.append(edge_idx)
                                break
                except Exception:
                    pass
            selected_edge_indices = sorted(set(int(i) for i in selected_edge_indices))

            # TNP Phase 1: GeometricSelectors erstellen
            # WICHTIG: Nutze die bereits ermittelten `edges` (inkl. "alle Kanten"),
            # nicht nochmal get_selected_edges() aufrufen!
            geometric_selectors = create_geometric_selectors_from_edges(edges)
            if is_enabled("tnp_debug_logging"):
                logger.debug(f"TNP Phase 1: {len(geometric_selectors)} GeometricSelectors erstellt")

            # TNP Phase 2: OCP Edge Shapes speichern
            ocp_edge_shapes = []
            for edge in edges:
                if hasattr(edge, 'wrapped'):
                    ocp_edge_shapes.append(edge.wrapped)

            # TNP Phase 2: Finde vorheriges Boolean-Feature (für History-Lookup)
            depends_on_feature_id = None
            from modeling import ExtrudeFeature
            for feat in reversed(body.features):
                if isinstance(feat, ExtrudeFeature) and feat.operation in ["Join", "Cut", "Intersect"]:
                    depends_on_feature_id = feat.id
                    if is_enabled("tnp_debug_logging"):
                        logger.debug(f"TNP Phase 2: Fillet/Chamfer hängt von Feature {feat.name} ab")
                    break

            # Feature erstellen (ZUERST - damit es eine ID bekommt)
            if mode == "chamfer":
                feature = ChamferFeature(
                    distance=radius,
                    edge_indices=selected_edge_indices,
                    geometric_selectors=geometric_selectors,
                    ocp_edge_shapes=ocp_edge_shapes,
                    depends_on_feature_id=depends_on_feature_id
                )
            else:
                feature = FilletFeature(
                    radius=radius,
                    edge_indices=selected_edge_indices,
                    geometric_selectors=geometric_selectors,
                    ocp_edge_shapes=ocp_edge_shapes,
                    depends_on_feature_id=depends_on_feature_id
                )
            
            # TNP v4.0: ShapeIDs für ausgewählte Edges finden (nicht neu erstellen!)
            edge_shape_ids = []
            if body._document and hasattr(body._document, '_shape_naming_service'):
                service = body._document._shape_naming_service
                for edge in edges:
                    # Finde existierende ShapeID für diese Edge
                    shape_id = service.find_shape_id_by_edge(edge, require_exact=True)
                    if shape_id:
                        edge_shape_ids.append(shape_id)
                        if is_enabled("tnp_debug_logging"):
                            logger.debug(f"TNP v4.0: ShapeID gefunden für Edge: {shape_id.uuid[:8]}...")
                    else:
                        # Fallback: Edge jetzt registrieren, damit TNP weiterarbeiten kann
                        try:
                            shape_id = service.register_shape(
                                ocp_shape=edge.wrapped,
                                shape_type=ShapeType.EDGE,
                                feature_id=feature.id,
                                local_index=len(edge_shape_ids)
                            )
                            edge_shape_ids.append(shape_id)
                            if is_enabled("tnp_debug_logging"):
                                logger.debug(f"TNP v4.0: Edge registriert (Fallback) {shape_id.uuid[:8]}...")
                        except Exception as e:
                            if is_enabled("tnp_debug_logging"):
                                logger.warning(f"TNP v4.0: Keine ShapeID für Edge gefunden: {e}")
            else:
                if is_enabled("tnp_debug_logging"):
                    logger.warning("TNP v4.0: Kein NamingService verfügbar")
            
            feature.edge_shape_ids = edge_shape_ids
            if is_enabled("tnp_debug_logging"):
                logger.debug(f"TNP v4.0: {len(edge_shape_ids)} ShapeIDs für Feature {feature.id} gefunden")

            # TNP v4.0: Keine zusätzliche Registrierung nötig
            # ShapeIDs wurden bereits vom Extrude registriert

            # KRITISCH: Verwende AddFeatureCommand für korrektes Undo/Redo!
            # Das ruft body.add_feature() auf, was _rebuild() triggert.
            # Geometry-Snapshot VOR Operation (für Operation Summary)
            _pre_sig = self._solid_signature_safe(body)

            cmd = AddFeatureCommand(body, feature, self, description=f"{mode.capitalize()} R={radius}")
            self.undo_stack.push(cmd)

            # Geometry-Snapshot NACH Operation
            _post_sig = self._solid_signature_safe(body)

            # Prüfe ob Operation erfolgreich war
            if body._build123d_solid is None or (hasattr(body, 'vtk_mesh') and body.vtk_mesh is None):
                logger.warning(f"{mode.capitalize()} ließ Body leer - Undo")
                self.undo_stack.undo()
                QMessageBox.warning(
                    self, "Fehler",
                    f"{mode.capitalize()} fehlgeschlagen: Geometrie ungültig"
                )
            else:
                # Aufräumen bei Erfolg
                self.viewport_3d.stop_edge_selection_mode()
                self.fillet_panel.hide()
                self.browser.refresh()

                # TNP Statistiken aktualisieren
                self._update_tnp_stats(body)

                # Toast mit Geometry-Delta
                n_edges = len(selected_edge_indices)
                vol_info = ""
                if _pre_sig and _post_sig and _pre_sig["volume"] > 1e-6:
                    vol_pct = ((_post_sig["volume"] - _pre_sig["volume"]) / _pre_sig["volume"]) * 100
                    vol_info = f", Vol {vol_pct:+.1f}%"
                logger.success(f"{mode.capitalize()} R={radius}mm — {n_edges} Kanten{vol_info}")
                # Operation Summary wird zentral von AddFeatureCommand.redo() angezeigt

        except Exception as e:
            logger.error(f"Feature Creation Error: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Fehler", f"Unerwarteter Fehler:\n{str(e)}")

    def _on_fillet_radius_changed(self, radius):
        """
        Callback wenn der Radius geändert wird.
        Aktuell nur für spätere Preview-Funktionalität reserviert.
        """
        # TODO: Live-Preview wenn Performance es erlaubt
        pass

    def _on_fillet_cancelled(self):
        """Bricht die Fillet/Chamfer-Operation ab."""
        self.viewport_3d.stop_edge_selection_mode()
        self.fillet_panel.hide()
        logger.info("Fillet/Chamfer abgebrochen")

    # ==================== SHELL (Phase 6) ====================

    def _start_shell(self):
        """
        Startet den Shell-Workflow.

        UX-Pattern wie Fillet/Chamfer:
        - Falls Body ausgewählt → sofort starten
        - Falls kein Body → Pending-Mode, warte auf Klick
        """
        self._clear_transient_previews(reason="start_shell", clear_interaction_modes=True)
        # Prüfe ob Body im Browser ausgewählt
        selected_bodies = self.browser.get_selected_bodies()

        # Fall 1: Kein Body gewählt → Pending-Mode
        if not selected_bodies:
            self._pending_shell_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)

            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)

            logger.info("Shell: Klicke auf einen Körper in der 3D-Ansicht oder wähle im Browser")
            return

        # Fall 2: Body gewählt → direkt starten
        body = selected_bodies[0]
        self._activate_shell_for_body(body)

    def _on_body_clicked_for_shell(self, body_id: str):
        """
        Callback wenn im Pending-Mode ein Body angeklickt wird.
        """
        self._pending_shell_mode = False

        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.warning(f"Body {body_id} nicht gefunden")
            return

        self._activate_shell_for_body(body)

    def _activate_shell_for_body(self, body):
        """
        Aktiviert Shell-Modus für einen spezifischen Body.
        """
        if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
            logger.warning(f"'{body.name}' hat keine CAD-Daten (nur Mesh).")
            return

        # WICHTIG: Transform-Gizmo ausblenden, damit Klicks nicht abgefangen werden
        if hasattr(self.viewport_3d, 'hide_transform_gizmo'):
            self.viewport_3d.hide_transform_gizmo()

        self._shell_mode = True
        self._shell_target_body = body
        self._shell_opening_faces = []
        self._shell_opening_face_shape_ids = []
        self._shell_opening_face_indices = []
        self._pending_shell_mode = False

        # WICHTIG: Face-Detection aktivieren damit Flächen wählbar sind
        # (Analog zu Extrude-Mode, aber OHNE Extrude-Preview!)
        self.viewport_3d.set_extrude_mode(True, enable_preview=False)  # Aktiviert Face-Picking
        self._update_detector()  # Detector mit Body-Faces füllen

        # Panel anzeigen
        self.shell_panel.clear_opening_faces()
        self.shell_panel.show_at(self.viewport_3d)

        logger.info(f"Shell: Wähle Öffnungs-Flächen von '{body.name}' (Klick = hinzufügen, ESC = abbrechen)")

    def _on_face_selected_for_shell(self, face_id):
        """
        Callback wenn eine Fläche für Shell ausgewählt wird.
        TNP-robust: Erstellt GeometricFaceSelector für stabile Referenzierung.
        """
        logger.debug(f"Shell: _on_face_selected_for_shell aufgerufen mit face_id={face_id}")

        if not self._shell_mode or not self._shell_target_body:
            logger.debug(f"Shell: Abgebrochen - _shell_mode={getattr(self, '_shell_mode', False)}, target_body={self._shell_target_body}")
            return

        # Finde die Face-Daten
        face = next((f for f in self.viewport_3d.detector.selection_faces if f.id == face_id), None)
        if not face:
            logger.warning(f"Shell: Face mit ID {face_id} nicht im Detector gefunden")
            return

        logger.debug(f"Shell: Face gefunden - domain_type={face.domain_type}, has_shapely={face.shapely_poly is not None}")

        # Nur Body-Faces akzeptieren
        if not face.domain_type.startswith('body'):
            logger.warning(f"Shell: Nur Body-Flächen erlaubt, aber domain_type={face.domain_type}")
            return

        # TNP-v4: Face indexbasiert auflösen (ocp_face_id), dann Geometric-Fallback.
        try:
            from modeling.geometric_selector import GeometricFaceSelector

            body = self._shell_target_body
            if not body or not body._build123d_solid:
                return

            # Face-Center als Fallback-Punkt
            face_center = None
            if face.shapely_poly:
                centroid = face.shapely_poly.centroid
                plane_x = np.array(face.plane_x)
                plane_y = np.array(face.plane_y)
                origin = np.array(face.plane_origin)
                face_center = origin + centroid.x * plane_x + centroid.y * plane_y
            elif hasattr(face, 'plane_origin') and face.plane_origin is not None:
                face_center = np.array(face.plane_origin)
            else:
                logger.warning(f"Shell: Kann Face-Center nicht bestimmen")
                return

            best_face, resolved_face_id = self._resolve_solid_face_from_pick(
                body,
                body.id,
                position=face_center,
                ocp_face_id=getattr(face, "ocp_face_id", None),
            )

            if best_face is not None:
                geo_selector = GeometricFaceSelector.from_face(best_face)
                face_selector = geo_selector.to_dict()
                face_shape_id = self._find_or_register_face_shape_id(
                    body,
                    best_face,
                    # Use current opening slot index (not topology index).
                    local_index=max(0, len(self._shell_opening_face_shape_ids)),
                )
                logger.debug(f"Shell: GeometricFaceSelector erstellt (area={geo_selector.area:.1f})")
            else:
                face_selector = {
                    "center": list(face_center),
                    "normal": list(face.plane_normal),
                    "area": 0.0,
                    "surface_type": "unknown",
                    "tolerance": 10.0
                }
                face_shape_id = None
                logger.warning(f"Shell: Konnte Face nicht finden, verwende Fallback")
                 
        except Exception as e:
            logger.warning(f"Shell: Konnte GeometricFaceSelector nicht erstellen: {e}")
            return

        # Prüfen ob schon ausgewählt (Toggle-Verhalten) - Vergleiche mit center
        already_selected = False
        center_arr = np.array(face_selector["center"])
        for i, existing_sel in enumerate(self._shell_opening_faces):
            existing_center = np.array(existing_sel.get("center", [0,0,0]))
            if np.linalg.norm(existing_center - center_arr) < 0.1:
                # Bereits ausgewählt → entfernen
                self._shell_opening_faces.pop(i)
                if i < len(self._shell_opening_face_shape_ids):
                    self._shell_opening_face_shape_ids.pop(i)
                if i < len(self._shell_opening_face_indices):
                    self._shell_opening_face_indices.pop(i)
                already_selected = True
                logger.info(f"Shell: Fläche entfernt ({len(self._shell_opening_faces)} Öffnungen)")
                break

        if not already_selected:
            self._shell_opening_faces.append(face_selector)
            self._shell_opening_face_shape_ids.append(face_shape_id)
            self._shell_opening_face_indices.append(
                int(resolved_face_id) if resolved_face_id is not None else None
            )
            self.shell_panel.add_opening_face(face_selector)
            logger.info(f"Shell: Fläche hinzugefügt ({len(self._shell_opening_faces)} Öffnungen)")

        # Panel aktualisieren
        self.shell_panel.update_face_count(len(self._shell_opening_faces))

    def _on_shell_confirmed(self):
        """
        Wendet Shell auf den Body an.
        TNP v4.0: Sucht existierende ShapeIDs für die ausgewählten Faces.
        """
        from modeling.cad_tessellator import CADTessellator
        from modeling import ShellFeature

        thickness = self.shell_panel.get_thickness()
        body = self._shell_target_body

        if not body:
            logger.error("Shell: Kein Body ausgewählt")
            return

        logger.info(f"Wende Shell auf '{body.name}' an (Wandstärke={thickness}mm, {len(self._shell_opening_faces)} Öffnungen)...")

        try:
            from gui.commands.feature_commands import AddFeatureCommand

            shell_feature = ShellFeature(
                thickness=thickness,
                opening_face_selectors=self._shell_opening_faces.copy()
            )

            # TNP-v4: ShapeIDs aus der Face-Auswahl übernehmen (bereits beim Klick aufgelöst).
            face_shape_ids = [sid for sid in self._shell_opening_face_shape_ids if sid is not None]
            face_indices = [idx for idx in self._shell_opening_face_indices if idx is not None]
            shell_feature.face_shape_ids = face_shape_ids
            if face_indices:
                shell_feature.face_indices = sorted(set(int(i) for i in face_indices))
            if is_enabled("tnp_debug_logging"):
                logger.debug(
                    f"TNP v4.0: {len(face_shape_ids)}/{len(self._shell_opening_faces)} Face-ShapeIDs "
                    f"und {len(shell_feature.face_indices or [])} Face-Indizes für Shell gefunden"
                )

            cmd = AddFeatureCommand(body, shell_feature, self, description=f"Shell ({thickness}mm)")
            self.undo_stack.push(cmd)

            # Prüfe ob Operation erfolgreich war
            if body._build123d_solid is None:
                logger.warning("Shell ließ Body leer - Undo")
                self.undo_stack.undo()
                QMessageBox.critical(self, "Fehler", "Shell fehlgeschlagen: Geometrie ungültig")
                return

            if shell_feature.status == "ERROR":
                msg = shell_feature.status_message or "Kernel-Operation fehlgeschlagen"
                self.statusBar().showMessage(f"Shell fehlgeschlagen: {msg}", 8000)
                logger.error(f"Shell fehlgeschlagen: {msg}")
                self._stop_shell_mode()
                self.browser.refresh()
                return
            if shell_feature.status == "WARNING":
                msg = shell_feature.status_message or "Fallback verwendet"
                self.statusBar().showMessage(f"Shell mit Warnung: {msg}", 6000)
                logger.warning(f"Shell mit Warnung: {msg}")

            # Visualisierung aktualisieren
            CADTessellator.notify_body_changed()
            self._update_body_from_build123d(body, body._build123d_solid)

            # Aufräumen
            self._stop_shell_mode()
            self.browser.refresh()

            logger.success(f"Shell erfolgreich: Wandstärke {thickness}mm mit {len(self._shell_opening_faces)} Öffnungen")

        except Exception as e:
            logger.error(f"Shell fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Fehler", f"Shell fehlgeschlagen:\n{str(e)}")

    def _on_shell_thickness_changed(self, thickness: float):
        """
        Callback wenn die Wandstärke geändert wird.
        Aktuell nur für spätere Preview-Funktionalität reserviert.
        """
        # TODO: Live-Preview wenn Performance es erlaubt
        pass

    def _on_shell_cancelled(self):
        """Bricht die Shell-Operation ab."""
        self._stop_shell_mode()
        logger.info("Shell abgebrochen")

    def _stop_shell_mode(self):
        """Beendet den Shell-Modus und räumt auf."""
        self._shell_mode = False
        self._shell_target_body = None
        self._shell_opening_faces = []
        self._shell_opening_face_shape_ids = []
        self._shell_opening_face_indices = []
        self.shell_panel.hide()

        # Face-Detection deaktivieren
        self.viewport_3d.set_extrude_mode(False)

    # ==================== SURFACE TEXTURE (Phase 7) ====================

    def _start_texture_mode(self):
        """
        Startet den Surface Texture Modus.
        Workflow wie Fillet/Shell: Body auswählen → Faces selektieren → Textur anwenden

        Unterstützt:
        - Body bereits im Browser ausgewählt → direkt starten
        - Kein Body ausgewählt → Pending-Mode für Viewport-Selektion
        """
        self._clear_transient_previews(reason="start_texture_mode", clear_interaction_modes=True)
        # Prüfe ob Body im Browser ausgewählt
        selected_bodies = self.browser.get_selected_bodies()

        # Fall 1: Kein Body gewählt → Pending-Mode (wie bei Fillet/Shell)
        if not selected_bodies:
            self._pending_texture_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)

            # Aktiviere Body-Highlighting im Viewport
            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)

            logger.info("Surface Texture: Klicke auf einen Körper in der 3D-Ansicht oder wähle im Browser")
            return

        # Fall 2: Body gewählt → direkt starten
        body = selected_bodies[0]
        self._activate_texture_for_body(body)

    def _on_body_clicked_for_texture(self, body_id: str):
        """
        Callback wenn im Pending-Mode ein Body angeklickt wird.
        Wird vom _on_viewport_body_clicked Handler aufgerufen.
        """
        self._pending_texture_mode = False

        # Pending-Mode deaktivieren
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        # Body finden
        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.warning(f"Body {body_id} nicht gefunden")
            return

        self._activate_texture_for_body(body)

    def _activate_texture_for_body(self, body):
        """
        Aktiviert Texture-Mode für einen spezifischen Body.

        Args:
            body: Body-Objekt
        """
        if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
            logger.warning(f"'{body.name}' hat keine CAD-Daten (nur Mesh). Texturen nur auf BREP-Bodies.")
            return

        self._texture_mode = True
        self._texture_target_body = body
        self._pending_texture_mode = False

        # WICHTIG: Face-Detection aktivieren (wie bei Shell/Extrude)
        self.viewport_3d.set_extrude_mode(True)
        self._update_detector()

        # Face-Selektionsmodus im Viewport starten
        self.viewport_3d.start_texture_face_mode(body.id)

        # Panel anzeigen
        self.texture_panel.reset()
        self.texture_panel.show_at(self.viewport_3d)

        logger.info(f"Surface Texture: Klicke auf Faces von '{body.name}' (ESC = abbrechen)")

    def _on_texture_face_selected(self, count: int):
        """Callback wenn Texture-Faces im Viewport selektiert werden."""
        if self._texture_mode and hasattr(self, 'texture_panel'):
            self.texture_panel.set_face_count(count)

    def _on_texture_applied(self, config: dict):
        """
        Wendet die Textur auf den Body an.

        Args:
            config: Textur-Konfiguration aus SurfaceTexturePanel
        """
        from modeling.cad_tessellator import CADTessellator
        from modeling.geometric_selector import GeometricFaceSelector

        if not self._texture_target_body:
            logger.error("Kein Target-Body für Textur")
            return

        body = self._texture_target_body

        # Selektierte Faces vom Viewport holen
        selected_faces = self.viewport_3d.get_texture_selected_faces()

        if not selected_faces:
            logger.warning("Keine Faces selektiert für Textur")
            return

        # TNP v4.0: Face-Referenzen erstellen (ShapeID/Index primary, Selector fallback).
        face_selectors = []
        face_shape_ids = []
        face_indices = []
        for idx, face_data in enumerate(selected_faces):
            center = face_data.get("center", (0, 0, 0))
            normal = face_data.get("normal", (0, 0, 1))
            cell_ids = face_data.get("cell_ids", []) or []

            candidate_cell_id = int(cell_ids[0]) if cell_ids else None
            explicit_face_id = face_data.get("face_id")
            explicit_face_id = int(explicit_face_id) if explicit_face_id is not None else None

            try:
                best_face, resolved_face_id = self._resolve_solid_face_from_pick(
                    body,
                    body.id,
                    cell_id=candidate_cell_id,
                    position=center,
                    ocp_face_id=explicit_face_id,
                )
                if best_face is not None:
                    geo_selector = GeometricFaceSelector.from_face(best_face)
                    selector = geo_selector.to_dict()
                    selector["cell_ids"] = list(cell_ids)
                    shape_id = self._find_or_register_face_shape_id(
                        body,
                        best_face,
                        # Multi-face reference: slot index in feature reference list.
                        local_index=idx,
                    )
                    if shape_id is not None:
                        face_shape_ids.append(shape_id)
                    if resolved_face_id is not None:
                        face_indices.append(int(resolved_face_id))
                else:
                    if resolved_face_id is not None:
                        face_indices.append(int(resolved_face_id))
                    selector = {
                        "center": list(center),
                        "normal": list(normal),
                        "area": float(face_data.get("area", 1.0)),
                        "surface_type": face_data.get("surface_type", "plane"),
                        "tolerance": 10.0,
                        "cell_ids": list(cell_ids),
                    }
            except Exception as e:
                logger.warning(f"Texture: Face-Referenz konnte nicht aufgelöst werden: {e}")
                if resolved_face_id is not None:
                    face_indices.append(int(resolved_face_id))
                selector = {
                    "center": list(center),
                    "normal": list(normal),
                    "area": float(face_data.get("area", 1.0)),
                    "surface_type": face_data.get("surface_type", "plane"),
                    "tolerance": 10.0,
                    "cell_ids": list(cell_ids),
                }

            face_selectors.append(selector)

        from gui.commands.feature_commands import AddFeatureCommand

        # SurfaceTextureFeature erstellen
        feature = SurfaceTextureFeature(
            name=f"Texture: {config['texture_type'].capitalize()}",
            texture_type=config['texture_type'],
            face_selectors=face_selectors,
            scale=config.get('scale', 1.0),
            depth=config.get('depth', 0.5),
            rotation=config.get('rotation', 0.0),
            invert=config.get('invert', False),
            solid_base=config.get('solid_base', True),  # Default True für 3D-Druck-Sicherheit
            type_params=config.get('type_params', {}),
            export_subdivisions=config.get('export_subdivisions', 4)
        )
        if face_shape_ids:
            feature.face_shape_ids = face_shape_ids
        if face_indices:
            feature.face_indices = sorted(set(int(i) for i in face_indices))
        if is_enabled("tnp_debug_logging"):
            logger.debug(
                f"TNP v4.0: Texture-Referenzen vorbereitet "
                f"(selectors={len(face_selectors)}, shape_ids={len(face_shape_ids)}, "
                f"indices={len(feature.face_indices or [])})"
            )

        # KRITISCH: Verwende AddFeatureCommand für korrektes Undo/Redo!
        # SurfaceTexture modifiziert den Solid nicht, nur die Feature-Liste
        cmd = AddFeatureCommand(body, feature, self, description=f"Texture ({config['texture_type']})")
        self.undo_stack.push(cmd)

        # Cache invalidieren für nächsten Render
        CADTessellator.notify_body_changed()

        # Browser aktualisieren
        self.browser.refresh()

        # Body-Referenz setzen für Texture-Previews
        self.viewport_3d.set_body_object(body.id, body)

        # ALLE Texturen des Bodies im Viewport anzeigen (nicht nur die neue!)
        self.viewport_3d.refresh_texture_previews(body.id)

        # Texture-Mode beenden
        self._stop_texture_mode()

        # Benutzer informieren (Textur ist nur beim Export sichtbar)
        self.show_notification(
            "Textur angewendet",
            f"'{config['texture_type']}' auf {len(face_selectors)} Face(s). Sichtbar beim STL-Export.",
            "success"
        )

        logger.success(f"Textur '{feature.name}' auf {len(face_selectors)} Face(s) angewendet")

    def _on_texture_preview_requested(self, config: dict):
        """
        Preview für Textur (optional - aktuell nicht implementiert).

        Note: Live-Preview würde Normal-Map-Rendering im Shader erfordern.
        Für MVP: Kein Preview, nur Export-Zeit Anwendung.
        """
        # TODO: Optional - Normal-Map Preview im Viewport
        pass

    def _on_texture_cancelled(self):
        """Bricht die Textur-Operation ab."""
        self._stop_texture_mode()
        logger.info("Surface Texture abgebrochen")

    def _stop_texture_mode(self):
        """Beendet den Texture-Modus und räumt auf."""
        self._texture_mode = False
        self._texture_target_body = None
        self._pending_texture_mode = False
        self.texture_panel.hide()

        # Face-Detection deaktivieren
        self.viewport_3d.set_extrude_mode(False)

        # Viewport aufräumen
        self.viewport_3d.stop_texture_face_mode()

    # ==================== SWEEP (Phase 6) ====================

    def _start_sweep(self):
        """
        Startet den Sweep-Workflow.

        Zwei-Phasen Selektion:
        1. Profil auswählen (Face)
        2. Pfad auswählen (Edge)
        """
        self._clear_transient_previews(reason="start_sweep", clear_interaction_modes=True)
        # WICHTIG: Transform-Gizmo ausblenden, damit Klicks nicht abgefangen werden
        if hasattr(self.viewport_3d, 'hide_transform_gizmo'):
            self.viewport_3d.hide_transform_gizmo()

        self._sweep_mode = True
        self._sweep_phase = 'profile'
        self._sweep_profile_data = None
        self._sweep_path_data = None
        self._sweep_profile_shape_id = None
        self._sweep_profile_face_index = None
        self._sweep_profile_geometric_selector = None

        # Face-Detection aktivieren
        self.viewport_3d.set_extrude_mode(True)
        self._update_detector()

        # Panel anzeigen und zurücksetzen
        self.sweep_panel.reset()
        self.sweep_panel.show_at(self.viewport_3d)

        logger.info("Sweep: Wähle ein Profil (Face) aus")

    def _on_face_selected_for_sweep(self, face_id):
        """
        Callback wenn eine Fläche für Sweep-Profil ausgewählt wird.
        """
        if not self._sweep_mode or self._sweep_phase != 'profile':
            return

        # Finde die Face-Daten
        face = next((f for f in self.viewport_3d.detector.selection_faces if f.id == face_id), None)
        if not face:
            return

        self._sweep_profile_shape_id = None
        self._sweep_profile_face_index = None
        self._sweep_profile_geometric_selector = None

        # Profil-Daten speichern
        profile_data = {
            'type': face.domain_type,
            'owner_id': face.owner_id,
            'face_id': face_id,
            'plane_origin': face.plane_origin,
            'plane_normal': face.plane_normal,
            'plane_x': face.plane_x,
            'plane_y': face.plane_y,
            'shapely_poly': face.shapely_poly
        }

        if face.domain_type == "body_face":
            profile_data["body_id"] = face.owner_id
            profile_data["ocp_face_id"] = getattr(face, "ocp_face_id", None)

            target_body = self.document.find_body_by_id(face.owner_id)
            resolved_face = None
            resolved_face_index = getattr(face, "ocp_face_id", None)
            if target_body is not None and getattr(target_body, "_build123d_solid", None) is not None:
                try:
                    pick_position = getattr(face, "sample_point", None) or face.plane_origin
                    resolved_face, resolved_face_index = self._resolve_solid_face_from_pick(
                        target_body,
                        face.owner_id,
                        position=pick_position,
                        ocp_face_id=getattr(face, "ocp_face_id", None),
                    )
                except Exception as e:
                    logger.debug(f"Sweep: Profil-Face Auflösung fehlgeschlagen: {e}")

            if resolved_face_index is not None:
                try:
                    resolved_face_index = int(resolved_face_index)
                    self._sweep_profile_face_index = resolved_face_index
                    profile_data["face_index"] = resolved_face_index
                except Exception:
                    resolved_face_index = None

            if resolved_face is not None and target_body is not None:
                self._sweep_profile_shape_id = self._find_or_register_face_shape_id(
                    target_body,
                    resolved_face,
                    # Single profile-face reference: feature-local slot is always 0.
                    local_index=0,
                )

            has_primary_profile_ref = (
                self._sweep_profile_shape_id is not None
                or self._sweep_profile_face_index is not None
            )
            if resolved_face is not None and not has_primary_profile_ref:
                try:
                    from modeling.geometric_selector import GeometricFaceSelector

                    geo_selector = GeometricFaceSelector.from_face(resolved_face)
                    self._sweep_profile_geometric_selector = geo_selector.to_dict()
                except Exception as e:
                    logger.debug(f"Sweep: Konnte Profil-GeometricSelector nicht erzeugen: {e}")

        self._sweep_profile_data = profile_data
        self.sweep_panel.set_profile(profile_data)

        # Profil im Viewport highlighten
        self._highlight_sweep_profile(profile_data)

        # Zur Pfad-Phase wechseln
        self._sweep_phase = 'path'
        logger.info("Sweep: Profil ausgewählt. Klicke auf einen Pfad im Viewport (Sketch-Linie/Bogen/Spline oder Body-Edge)")

        # NEU: Direkte Viewport-Selektion für Sketch-Pfade aktivieren
        self.viewport_3d.start_sketch_path_mode()

        # Aktiviere sowohl Sketch-Element-Selektion als auch Edge-Selection
        # 1. Für Sketch-Elemente: Nutze Face-Selection im Detector
        # FIX: enable_preview=False damit keine Extrude-Preview während Sweep gezeigt wird
        self.viewport_3d.set_extrude_mode(True, enable_preview=False)
        self._update_detector()

        # 2. Für Body-Edges: Edge-Selection-Mode aktivieren
        if self.document.bodies:
            body = self.document.bodies[0]
            if hasattr(body, '_build123d_solid') and body._build123d_solid:
                self.viewport_3d.set_edge_selection_callbacks(
                    get_body_by_id=lambda bid: next((b for b in self.document.bodies if b.id == bid), None)
                )
                self.viewport_3d.start_edge_selection_mode(body.id)

    def _on_edge_selected_for_sweep(self, edges: list):
        """
        Callback wenn eine Kante für Sweep-Pfad ausgewählt wird.
        """
        if not self._sweep_mode or self._sweep_phase != 'path':
            return

        if not edges:
            return

        # Erste Kante als Pfad verwenden
        edge = edges[0]

        # Hole echte Build123d Edges für robuste Pfad-Auflösung
        build123d_edges = self.viewport_3d.get_selected_edges()
        edge_indices = []
        if hasattr(self.viewport_3d, "get_selected_edge_topology_indices"):
            edge_indices = self.viewport_3d.get_selected_edge_topology_indices() or []
        path_body_id = getattr(self.viewport_3d, "_edge_selection_body_id", None)
        path_geo_selector = None
        if not edge_indices:
            try:
                from modeling.geometric_selector import GeometricEdgeSelector
                path_geo_selector = GeometricEdgeSelector.from_edge(edge).to_dict()
            except Exception as e:
                logger.debug(f"Sweep: Konnte GeometricEdgeSelector nicht erzeugen: {e}")

        # Pfad-Daten speichern
        path_data = {
            'type': 'body_edge',
            'body_id': path_body_id,
            'edge_indices': edge_indices,
            'build123d_edges': build123d_edges,  # Direkte Edge-Referenzen (Session)
        }
        if path_geo_selector is not None:
            path_data['path_geometric_selector'] = path_geo_selector

        self._sweep_path_data = path_data
        self.sweep_panel.set_path(path_data)

        # Pfad im Viewport highlighten
        self._highlight_sweep_path(path_data)

        logger.info(
            f"Sweep: Pfad ausgewählt ({len(build123d_edges)} Edge(s), "
            f"TopoIdx={len(edge_indices)}). Drücke OK zum Ausführen"
        )

    def _on_sweep_confirmed(self):
        """
        Wendet Sweep auf das Profil an.
        """
        from modeling.cad_tessellator import CADTessellator
        from modeling import SweepFeature

        if not self._sweep_profile_data or not self._sweep_path_data:
            logger.error("Sweep: Profil oder Pfad fehlt")
            return

        operation = self.sweep_panel.get_operation()
        is_frenet = self.sweep_panel.is_frenet()

        logger.info(f"Wende Sweep an (Operation={operation}, Frenet={is_frenet})...")

        try:
            from gui.commands.feature_commands import AddFeatureCommand, AddBodyCommand

            # Sweep Feature erstellen
            sweep_feature = SweepFeature(
                profile_data=self._sweep_profile_data,
                path_data=self._sweep_path_data,
                is_frenet=is_frenet,
                operation=operation,
                twist_angle=self.sweep_panel.get_twist_angle(),
                scale_start=self.sweep_panel.get_scale_start(),
                scale_end=self.sweep_panel.get_scale_end(),
            )
            if self._sweep_profile_shape_id is not None:
                sweep_feature.profile_shape_id = self._sweep_profile_shape_id
            if self._sweep_profile_face_index is not None:
                sweep_feature.profile_face_index = int(self._sweep_profile_face_index)
            if (
                self._sweep_profile_geometric_selector
                and sweep_feature.profile_shape_id is None
                and sweep_feature.profile_face_index is None
            ):
                sweep_feature.profile_geometric_selector = self._sweep_profile_geometric_selector

            path_edges = self._sweep_path_data.get("build123d_edges") or []
            path_edge_indices = self._sweep_path_data.get("edge_indices") or []
            path_geo_selector = self._sweep_path_data.get("path_geometric_selector")
            if path_geo_selector and not path_edge_indices:
                sweep_feature.path_geometric_selector = path_geo_selector
            shape_service = getattr(self.document, "_shape_naming_service", None)
            if (path_edges or path_edge_indices) and shape_service:
                try:
                    from modeling.tnp_system import ShapeType
                    path_edge = None
                    if path_edge_indices:
                        from modeling.topology_indexing import edge_from_index

                        path_body_id = self._sweep_path_data.get("body_id")
                        path_body = self.document.find_body_by_id(path_body_id) if path_body_id else None
                        if path_body is None and self.document.bodies:
                            path_body = self.document.bodies[0]
                        if path_body and getattr(path_body, "_build123d_solid", None):
                            path_edge = edge_from_index(path_body._build123d_solid, int(path_edge_indices[0]))

                    if path_edge is None and path_edges:
                        path_edge = path_edges[0]
                    if path_edge is None:
                        raise ValueError("Keine gültige Sweep-Pfadkante für ShapeID-Registrierung gefunden")

                    shape_id = shape_service.find_shape_id_by_edge(path_edge, require_exact=True)
                    if shape_id is None and hasattr(path_edge, "wrapped"):
                        ec = path_edge.center()
                        edge_len = path_edge.length if hasattr(path_edge, "length") else 0.0
                        shape_id = shape_service.register_shape(
                            ocp_shape=path_edge.wrapped,
                            shape_type=ShapeType.EDGE,
                            feature_id=sweep_feature.id,
                            local_index=0,
                            geometry_data=(ec.X, ec.Y, ec.Z, edge_len),
                        )
                    if shape_id is not None:
                        sweep_feature.path_shape_id = shape_id
                except Exception as e:
                    logger.debug(f"Sweep: Path-ShapeID konnte nicht gesetzt werden: {e}")
            if path_edge_indices or sweep_feature.path_shape_id is not None:
                sweep_feature.path_geometric_selector = None

            # Body finden oder erstellen
            is_new_body = operation == "New Body" or not self.document.bodies
            if is_new_body:
                # Neuen Body erstellen
                from modeling import Body
                target_body = Body(name=f"Sweep_{len(self.document.bodies) + 1}", document=self.document)
                target_body.features.append(sweep_feature)

                # Rebuild vor AddBodyCommand
                CADTessellator.notify_body_changed()
                target_body._rebuild()

                # Prüfe ob erfolgreich
                if not target_body._build123d_solid or (hasattr(target_body._build123d_solid, 'is_null') and target_body._build123d_solid.is_null()):
                    raise ValueError("Sweep konnte keinen gültigen Solid erzeugen")

                # KRITISCH: AddBodyCommand für korrektes Undo/Redo!
                cmd = AddBodyCommand(self.document, target_body, self, description=f"Sweep (New Body)")
                self.undo_stack.push(cmd)
            else:
                # Existierenden Body verwenden - KRITISCH: AddFeatureCommand für Undo!
                target_body = self.document.bodies[0]
                cmd = AddFeatureCommand(target_body, sweep_feature, self, description=f"Sweep ({operation})")
                self.undo_stack.push(cmd)

                # Prüfe ob Rebuild erfolgreich war
                if not target_body._build123d_solid or (hasattr(target_body._build123d_solid, 'is_null') and target_body._build123d_solid.is_null()):
                    self.undo_stack.undo()
                    raise ValueError("Sweep konnte keinen gültigen Solid erzeugen")

            # Visualisierung aktualisieren
            self._update_body_from_build123d(target_body, target_body._build123d_solid)

            # Aufräumen
            self._stop_sweep_mode()
            self.browser.refresh()

            logger.success(f"Sweep erfolgreich: {operation}")

        except Exception as e:
            logger.error(f"Sweep fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Fehler", f"Sweep fehlgeschlagen:\n{str(e)}")

    def _on_sweep_cancelled(self):
        """Bricht die Sweep-Operation ab."""
        self._stop_sweep_mode()
        logger.info("Sweep abgebrochen")

    def _on_sweep_profile_cleared(self):
        """Handler wenn Profil-Auswahl entfernt wird."""
        self._sweep_profile_data = None
        self._sweep_profile_shape_id = None
        self._sweep_profile_face_index = None
        self._sweep_profile_geometric_selector = None
        logger.info("Sweep Profil-Auswahl entfernt")
        # Entferne Highlight im Viewport
        self._clear_sweep_highlight('profile')

    def _on_sweep_path_cleared(self):
        """Handler wenn Pfad-Auswahl entfernt wird."""
        self._sweep_path_data = None
        logger.info("Sweep Pfad-Auswahl entfernt")
        # Entferne Highlight im Viewport
        self._clear_sweep_highlight('path')

    def _clear_sweep_highlight(self, element_type: str, render: bool = True):
        """Entfernt das Sweep-Highlight für Profil oder Pfad."""
        self._preview_clear_group(f"sweep_{element_type}", render=render)

    def _highlight_sweep_profile(self, profile_data: dict):
        """Highlightet das ausgewählte Sweep-Profil im Viewport."""
        import pyvista as pv
        import numpy as np

        if not hasattr(self.viewport_3d, 'plotter') or not self.viewport_3d.plotter:
            return

        try:
            # Entferne altes Highlight
            self._clear_sweep_highlight('profile', render=False)

            shapely_poly = profile_data.get('shapely_poly')
            if not shapely_poly:
                return

            plane_origin = profile_data.get('plane_origin', (0, 0, 0))
            plane_normal = profile_data.get('plane_normal', (0, 0, 1))
            plane_x = profile_data.get('plane_x', (1, 0, 0))
            plane_y = profile_data.get('plane_y', (0, 1, 0))

            # Konvertiere Shapely-Polygon zu 3D-Punkten
            if hasattr(shapely_poly, 'exterior'):
                coords = list(shapely_poly.exterior.coords)
            else:
                coords = list(shapely_poly.coords)

            if len(coords) < 2:
                return

            # 2D zu 3D Transformation
            points_3d = []
            for x2d, y2d in coords:
                p3d = (
                    plane_origin[0] + x2d * plane_x[0] + y2d * plane_y[0],
                    plane_origin[1] + x2d * plane_x[1] + y2d * plane_y[1],
                    plane_origin[2] + x2d * plane_x[2] + y2d * plane_y[2]
                )
                points_3d.append(p3d)

            points = np.array(points_3d, dtype=np.float32)

            # Erstelle Linien-Mesh für das Profil
            n = len(points)
            lines = []
            for i in range(n - 1):
                lines.extend([2, i, i + 1])
            lines = np.array(lines, dtype=np.int32)

            poly = pv.PolyData(points, lines=lines)
            actor_name = "sweep_profile_highlight"
            self.viewport_3d.plotter.add_mesh(
                poly,
                name=actor_name,
                color="#00ff00",  # Grün für Profil
                line_width=4,
                render_lines_as_tubes=True
            )
            self._preview_track_actor("sweep_profile", actor_name)
            request_render(self.viewport_3d.plotter)  # PERFORMANCE: Use debounced queue

        except Exception as e:
            logger.warning(f"Profil-Highlight fehlgeschlagen: {e}")

    def _highlight_sweep_path(self, path_data: dict):
        """Highlightet den ausgewählten Sweep-Pfad im Viewport."""
        import pyvista as pv
        import numpy as np

        if not hasattr(self.viewport_3d, 'plotter') or not self.viewport_3d.plotter:
            return

        try:
            # Entferne altes Highlight
            self._clear_sweep_highlight('path', render=False)

            path_type = path_data.get('type')

            if path_type == 'sketch_edge':
                # Sketch-basierter Pfad
                geom_type = path_data.get('geometry_type')
                plane_origin = path_data.get('plane_origin', (0, 0, 0))
                plane_x = path_data.get('plane_x', (1, 0, 0))
                plane_y = path_data.get('plane_y', (0, 1, 0))

                points_2d = []

                if geom_type == 'line':
                    start = path_data.get('start')
                    end = path_data.get('end')
                    if start and end:
                        points_2d = [start, end]

                elif geom_type == 'arc':
                    # Generiere Punkte entlang des Bogens
                    center = path_data.get('center', (0, 0))
                    radius = path_data.get('radius', 1)
                    start_angle = path_data.get('start_angle', 0)
                    end_angle = path_data.get('end_angle', np.pi)

                    n_pts = 32
                    angles = np.linspace(start_angle, end_angle, n_pts)
                    for a in angles:
                        x = center[0] + radius * np.cos(a)
                        y = center[1] + radius * np.sin(a)
                        points_2d.append((x, y))

                elif geom_type == 'spline':
                    ctrl_pts = path_data.get('control_points', [])
                    if ctrl_pts:
                        # Für Splines: Interpoliere Punkte
                        points_2d = ctrl_pts

                if not points_2d:
                    return

                # 2D zu 3D Transformation
                points_3d = []
                for x2d, y2d in points_2d:
                    p3d = (
                        plane_origin[0] + x2d * plane_x[0] + y2d * plane_y[0],
                        plane_origin[1] + x2d * plane_x[1] + y2d * plane_y[1],
                        plane_origin[2] + x2d * plane_x[2] + y2d * plane_y[2]
                    )
                    points_3d.append(p3d)

                points = np.array(points_3d, dtype=np.float32)

            elif path_type == 'body_edge':
                # Body-Edge-basierter Pfad
                build123d_edges = list(path_data.get('build123d_edges', []) or [])
                if not build123d_edges:
                    edge_indices = path_data.get("edge_indices") or []
                    if edge_indices:
                        try:
                            from modeling.topology_indexing import edge_from_index

                            body_id = path_data.get("body_id")
                            body = self.document.find_body_by_id(body_id) if body_id else None
                            if body is None and self.document.bodies:
                                body = self.document.bodies[0]
                            solid = getattr(body, "_build123d_solid", None) if body else None
                            if solid is not None:
                                for edge_idx in edge_indices:
                                    resolved = edge_from_index(solid, int(edge_idx))
                                    if resolved is not None:
                                        build123d_edges.append(resolved)
                        except Exception as e:
                            logger.debug(f"Sweep: Highlight-Edge-Auflösung via Topology-Index fehlgeschlagen: {e}")
                if not build123d_edges:
                    return

                # Tesselliere die Edges
                points_3d = []
                for edge in build123d_edges:
                    if hasattr(edge, 'wrapped'):
                        from OCP.BRepAdaptor import BRepAdaptor_Curve
                        from OCP.GCPnts import GCPnts_UniformAbscissa

                        curve = BRepAdaptor_Curve(edge.wrapped)
                        u_start = curve.FirstParameter()
                        u_end = curve.LastParameter()

                        n_pts = 32
                        for i in range(n_pts + 1):
                            u = u_start + (u_end - u_start) * i / n_pts
                            pnt = curve.Value(u)
                            points_3d.append((pnt.X(), pnt.Y(), pnt.Z()))

                if not points_3d:
                    return

                points = np.array(points_3d, dtype=np.float32)

            else:
                return

            # Erstelle Linien-Mesh für den Pfad
            n = len(points)
            if n < 2:
                return

            lines = []
            for i in range(n - 1):
                lines.extend([2, i, i + 1])
            lines = np.array(lines, dtype=np.int32)

            poly = pv.PolyData(points, lines=lines)
            actor_name = "sweep_path_highlight"
            self.viewport_3d.plotter.add_mesh(
                poly,
                name=actor_name,
                color="#ff8800",  # Orange für Pfad
                line_width=4,
                render_lines_as_tubes=True
            )
            self._preview_track_actor("sweep_path", actor_name)
            request_render(self.viewport_3d.plotter)  # PERFORMANCE: Use debounced queue

        except Exception as e:
            logger.warning(f"Pfad-Highlight fehlgeschlagen: {e}")

    def _on_sketch_path_clicked(self, sketch_id: str, geom_type: str, index: int):
        """
        Handler für direkten Viewport-Klick auf Sketch-Element.
        Wird aufgerufen wenn User im Sweep-Pfad-Modus auf eine Linie/Arc/Spline klickt.
        """
        if not self._sweep_mode or self._sweep_phase != 'path':
            return

        logger.info(f"Sketch-Pfad Handler aufgerufen: sketch_id={sketch_id}, geom_type={geom_type}, index={index}")

        # Finde den Sketch (robuster Vergleich: String-Konvertierung)
        # WICHTIG: get_all_sketches() statt .sketches - letzteres nur für aktive Component!
        all_sketches = self.document.get_all_sketches()
        sketch = next((s for s in all_sketches if str(s.id) == str(sketch_id)), None)
        if not sketch:
            logger.warning(f"Sketch {sketch_id} nicht gefunden. Verfügbare IDs: {[s.id for s in all_sketches]}")
            return

        # Finde das Geometrie-Element
        geom = None
        if geom_type == 'line':
            lines = getattr(sketch, 'lines', [])
            if 0 <= index < len(lines):
                geom = lines[index]
        elif geom_type == 'arc':
            arcs = getattr(sketch, 'arcs', [])
            if 0 <= index < len(arcs):
                geom = arcs[index]
        elif geom_type == 'spline':
            splines = getattr(sketch, 'splines', []) + getattr(sketch, 'native_splines', [])
            if 0 <= index < len(splines):
                geom = splines[index]

        if not geom:
            logger.warning(f"Geometrie {geom_type}[{index}] im Sketch {sketch_id} nicht gefunden")
            return

        # Path-Daten erstellen (identisch zu _on_sweep_sketch_path_requested)
        path_data = {
            'type': 'sketch_edge',
            'geometry_type': geom_type,
            'plane_origin': sketch.plane_origin,
            'plane_normal': sketch.plane_normal,
            'plane_x': getattr(sketch, 'plane_x_dir', (1, 0, 0)),
            'plane_y': getattr(sketch, 'plane_y_dir', (0, 1, 0)),
        }

        # Geometrie-spezifische Daten
        if geom_type == 'arc':
            center = geom.center
            path_data['center'] = (center.x, center.y)
            path_data['radius'] = geom.radius
            path_data['start_angle'] = geom.start_angle
            path_data['end_angle'] = geom.end_angle
        elif geom_type == 'line':
            path_data['start'] = (geom.start.x, geom.start.y)
            path_data['end'] = (geom.end.x, geom.end.y)
        elif geom_type == 'spline':
            ctrl_pts = getattr(geom, 'control_points', None)
            if ctrl_pts is None:
                ctrl_pts = getattr(geom, 'points', [])
            if ctrl_pts and hasattr(ctrl_pts[0], 'x'):
                path_data['control_points'] = [(p.x, p.y) for p in ctrl_pts]
            else:
                path_data['control_points'] = ctrl_pts

        # Pfad setzen
        self._sweep_path_data = path_data
        self.sweep_panel.set_path(path_data)

        # Pfad im Viewport highlighten
        self._highlight_sweep_path(path_data)

        # Sketch-Pfad-Modus beenden (Pfad wurde ausgewählt)
        self.viewport_3d.stop_sketch_path_mode()

        # Visuelles Feedback
        logger.success(f"Sweep: Pfad ausgewählt - {sketch.name}: {geom_type.capitalize()}")
        logger.info("Drücke OK um Sweep auszuführen")

    def _on_sweep_sketch_path_requested(self):
        """
        Öffnet Dialog zur Auswahl eines Sketch-Elements als Pfad.
        Sucht Bögen, Linien und Splines in sichtbaren Sketches.
        """
        from PySide6.QtWidgets import QInputDialog

        # Sammle verfügbare Pfad-Geometrien aus Sketches
        # WICHTIG: get_all_sketches() statt .sketches - letzteres nur für aktive Component!
        path_options = []

        for sketch in self.document.get_all_sketches():
            # Bögen - perfekt für Sweep
            for arc in getattr(sketch, 'arcs', []):
                path_options.append({
                    'name': f"{sketch.name}: Bogen (R={arc.radius:.1f}mm)",
                    'sketch': sketch,
                    'geometry': arc,
                    'type': 'arc'
                })

            # Linien - für gerade Sweeps
            for line in getattr(sketch, 'lines', []):
                # Line2D hat length property oder berechne manuell
                length = getattr(line, 'length', None)
                if length is None:
                    length = ((line.end.x - line.start.x)**2 + (line.end.y - line.start.y)**2)**0.5
                path_options.append({
                    'name': f"{sketch.name}: Linie (L={length:.1f}mm)",
                    'sketch': sketch,
                    'geometry': line,
                    'type': 'line'
                })

            # Splines - für komplexe Pfade
            for spline in getattr(sketch, 'splines', []):
                n_pts = len(getattr(spline, 'control_points', getattr(spline, 'points', [])))
                path_options.append({
                    'name': f"{sketch.name}: Spline ({n_pts} Punkte)",
                    'sketch': sketch,
                    'geometry': spline,
                    'type': 'spline'
                })

            # Native Splines (aus DXF)
            for spline in getattr(sketch, 'native_splines', []):
                n_pts = len(getattr(spline, 'control_points', []))
                path_options.append({
                    'name': f"{sketch.name}: B-Spline ({n_pts} Punkte)",
                    'sketch': sketch,
                    'geometry': spline,
                    'type': 'spline'
                })

        if not path_options:
            QMessageBox.warning(
                self, "Kein Pfad gefunden",
                "Keine Bögen, Linien oder Splines in Sketches gefunden.\n\n"
                "Zeichne zuerst einen Bogen oder eine Linie im Sketch."
            )
            return

        # Auto-Select wenn nur ein Pfad verfügbar
        if len(path_options) == 1:
            selected = path_options[0]
            logger.info(f"Sweep: Auto-Auswahl (einziger Pfad): {selected['name']}")
        else:
            # Dialog zur Auswahl bei mehreren Pfaden
            names = [opt['name'] for opt in path_options]
            name, ok = QInputDialog.getItem(
                self, "Sweep-Pfad wählen",
                "Wähle einen Pfad aus den Sketches:",
                names, 0, False
            )

            if not ok:
                return

            # Gewählte Option finden
            selected = next((opt for opt in path_options if opt['name'] == name), None)
        if not selected:
            return

        sketch = selected['sketch']
        geom = selected['geometry']
        geom_type = selected['type']

        # Path-Daten erstellen
        path_data = {
            'type': 'sketch_edge',
            'geometry_type': geom_type,
            'plane_origin': sketch.plane_origin,
            'plane_normal': sketch.plane_normal,
            'plane_x': getattr(sketch, 'plane_x_dir', (1, 0, 0)),
            'plane_y': getattr(sketch, 'plane_y_dir', (0, 1, 0)),
        }

        # Geometrie-spezifische Daten
        if geom_type == 'arc':
            # Arc2D hat center als Point2D
            center = geom.center
            path_data['center'] = (center.x, center.y)
            path_data['radius'] = geom.radius
            path_data['start_angle'] = geom.start_angle
            path_data['end_angle'] = geom.end_angle
        elif geom_type == 'line':
            # Line2D hat start/end als Point2D
            path_data['start'] = (geom.start.x, geom.start.y)
            path_data['end'] = (geom.end.x, geom.end.y)
        elif geom_type == 'spline':
            # Spline kann control_points oder points haben
            ctrl_pts = getattr(geom, 'control_points', None)
            if ctrl_pts is None:
                ctrl_pts = getattr(geom, 'points', [])
            # Konvertiere zu Tupel-Liste falls Point2D
            if ctrl_pts and hasattr(ctrl_pts[0], 'x'):
                path_data['control_points'] = [(p.x, p.y) for p in ctrl_pts]
            else:
                path_data['control_points'] = ctrl_pts

        self._sweep_path_data = path_data
        self.sweep_panel.set_path(path_data)

        # Pfad im Viewport highlighten
        self._highlight_sweep_path(path_data)

        logger.info(f"Sweep: Pfad aus Sketch gewählt - {name}")

    def _stop_sweep_mode(self):
        """Beendet den Sweep-Modus und räumt auf."""
        self._sweep_mode = False
        self._sweep_phase = None
        self._sweep_profile_data = None
        self._sweep_path_data = None
        self._sweep_profile_shape_id = None
        self._sweep_profile_face_index = None
        self._sweep_profile_geometric_selector = None
        self.sweep_panel.hide()

        # Highlights entfernen
        self._clear_sweep_highlight('profile', render=False)
        self._clear_sweep_highlight('path')

        # Sketch-Pfad-Modus stoppen
        if hasattr(self.viewport_3d, 'stop_sketch_path_mode'):
            self.viewport_3d.stop_sketch_path_mode()

        # Edge-Selection stoppen falls aktiv
        if hasattr(self.viewport_3d, 'stop_edge_selection_mode'):
            self.viewport_3d.stop_edge_selection_mode()

    # ==================== LOFT (Phase 6) ====================

    def _start_loft(self):
        """
        Startet den Loft-Workflow.

        Loft verbindet mehrere Profile auf verschiedenen Z-Ebenen.
        """
        self._clear_transient_previews(reason="start_loft", clear_interaction_modes=True)
        # WICHTIG: Transform-Gizmo ausblenden, damit Klicks nicht abgefangen werden
        if hasattr(self.viewport_3d, 'hide_transform_gizmo'):
            self.viewport_3d.hide_transform_gizmo()

        self._loft_mode = True
        self._loft_profiles = []
        logger.info(f"Loft: Modus aktiviert. _loft_mode={self._loft_mode}")

        # Face-Detection aktivieren (OHNE Extrude-Preview!)
        self.viewport_3d.set_extrude_mode(True, enable_preview=False)
        self._update_detector()

        # Debug: Zeige Detector-Status
        face_count = len(self.viewport_3d.detector.selection_faces)
        sketch_faces = [f for f in self.viewport_3d.detector.selection_faces if f.domain_type.startswith('sketch')]
        logger.info(f"Loft: Detector hat {face_count} Faces ({len(sketch_faces)} Sketch-Faces)")
        for sf in sketch_faces:
            logger.info(f"  - Face {sf.id}: {sf.domain_type}, owner={sf.owner_id}")

        # Panel anzeigen und zurücksetzen
        self.loft_panel.reset()
        self.loft_panel.show_at(self.viewport_3d)

        logger.info("Loft: Wähle Profile (Flächen) auf verschiedenen Z-Ebenen aus")

    def _on_loft_add_profile(self):
        """
        Callback wenn "Profil hinzufügen" geklickt wird.
        Aktiviert Face-Selection-Mode.
        """
        logger.info("Loft: Klicke auf eine Fläche um sie als Profil hinzuzufügen")

    def _on_face_selected_for_loft(self, face_id):
        """
        Callback wenn eine Fläche für Loft-Profil ausgewählt wird.
        """
        logger.info(f"Loft: _on_face_selected_for_loft aufgerufen mit face_id={face_id}")

        if not self._loft_mode:
            logger.warning("Loft: Nicht im Loft-Modus!")
            return

        # Debug: Zeige alle verfügbaren Faces
        all_faces = self.viewport_3d.detector.selection_faces
        logger.debug(f"Loft: {len(all_faces)} selection_faces verfügbar")
        for f in all_faces:
            logger.debug(f"  Face id={f.id}, type={f.domain_type}, owner={f.owner_id}")

        # Finde die Face-Daten
        face = next((f for f in self.viewport_3d.detector.selection_faces if f.id == face_id), None)
        if not face:
            logger.warning(f"Loft: Face mit id={face_id} nicht in selection_faces gefunden!")
            return

        # Profil-Daten erstellen
        profile_data = {
            'type': face.domain_type,
            'face_id': face_id,
            'plane_origin': face.plane_origin,
            'plane_normal': face.plane_normal,
            'plane_x': face.plane_x,
            'plane_y': face.plane_y,
            'shapely_poly': face.shapely_poly
        }

        # Prüfen ob schon ausgewählt (gleiche Ebenen-Position)
        # Berechne Position entlang der Normalen für korrekten Vergleich bei beliebigen Ebenen
        import numpy as np
        origin_new = np.array(profile_data['plane_origin'])
        normal_new = np.array(profile_data['plane_normal'])

        for existing in self._loft_profiles:
            origin_existing = np.array(existing['plane_origin'])
            normal_existing = np.array(existing['plane_normal'])

            # Prüfe ob Ebenen parallel sind (gleiche Normale)
            dot_normals = abs(np.dot(normal_new, normal_existing))
            if dot_normals < 0.99:
                # Nicht parallel - verschiedene Ebenen-Orientierung, erlauben
                continue

            # Für parallele Ebenen: Distanz entlang der Normalen prüfen
            dist_along_normal = abs(np.dot(origin_new - origin_existing, normal_new))
            if dist_along_normal < 0.1:
                logger.warning(f"Loft: Profil auf gleicher Ebene bereits vorhanden (dist={dist_along_normal:.2f}mm) - übersprungen")
                return

        # Profil hinzufügen
        self._loft_profiles.append(profile_data)
        self.loft_panel.add_profile(profile_data)

        # Highlighting für das neue Profil
        profile_index = len(self._loft_profiles) - 1
        self._highlight_loft_profile(profile_data, profile_index)

        # Preview aktualisieren wenn mindestens 2 Profile
        if len(self._loft_profiles) >= 2:
            self._update_loft_preview()

        # Berechne Position für Log
        pos_along_normal = np.dot(origin_new, normal_new)
        logger.info(f"Loft: Profil hinzugefügt (pos={pos_along_normal:.1f}mm, {len(self._loft_profiles)} Profile)")

    def _on_loft_confirmed(self):
        """
        Wendet Loft auf die Profile an.
        """
        from modeling.cad_tessellator import CADTessellator
        from modeling import LoftFeature

        profiles = self.loft_panel.get_profiles()

        if len(profiles) < 2:
            logger.error("Loft: Mindestens 2 Profile benötigt")
            return

        operation = self.loft_panel.get_operation()
        ruled = self.loft_panel.is_ruled()

        logger.info(f"Wende Loft an ({len(profiles)} Profile, Operation={operation}, Ruled={ruled})...")

        try:
            from gui.commands.feature_commands import AddFeatureCommand, AddBodyCommand

            # Profile nach Z sortieren
            profiles_sorted = sorted(profiles, key=lambda p: p['plane_origin'][2] if isinstance(p['plane_origin'], (list, tuple)) else 0)

            # Loft Feature erstellen
            loft_feature = LoftFeature(
                profile_data=profiles_sorted,
                ruled=ruled,
                operation=operation
            )

            # Body finden oder erstellen
            is_new_body = operation == "New Body" or not self.document.bodies
            if is_new_body:
                from modeling import Body
                target_body = Body(name=f"Loft_{len(self.document.bodies) + 1}", document=self.document)
                target_body.features.append(loft_feature)

                # Rebuild vor AddBodyCommand
                CADTessellator.notify_body_changed()
                target_body._rebuild()

                # Prüfe ob erfolgreich
                if not target_body._build123d_solid or (hasattr(target_body._build123d_solid, 'is_null') and target_body._build123d_solid.is_null()):
                    raise ValueError("Loft konnte keinen gültigen Solid erzeugen")

                # KRITISCH: AddBodyCommand für korrektes Undo/Redo!
                cmd = AddBodyCommand(self.document, target_body, self, description=f"Loft (New Body)")
                self.undo_stack.push(cmd)
            else:
                # Existierenden Body verwenden - KRITISCH: AddFeatureCommand für Undo!
                target_body = self.document.bodies[0]
                cmd = AddFeatureCommand(target_body, loft_feature, self, description=f"Loft ({operation})")
                self.undo_stack.push(cmd)

                # Prüfe ob Rebuild erfolgreich war
                if not target_body._build123d_solid or (hasattr(target_body._build123d_solid, 'is_null') and target_body._build123d_solid.is_null()):
                    self.undo_stack.undo()
                    raise ValueError("Loft konnte keinen gültigen Solid erzeugen")

            # Visualisierung aktualisieren
            self._update_body_from_build123d(target_body, target_body._build123d_solid)

            # Aufräumen
            self._stop_loft_mode()
            self.browser.refresh()

            logger.success(f"Loft erfolgreich: {len(profiles)} Profile verbunden")

        except Exception as e:
            logger.error(f"Loft fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Fehler", f"Loft fehlgeschlagen:\n{str(e)}")

    def _on_loft_cancelled(self):
        """Bricht die Loft-Operation ab."""
        self._stop_loft_mode()
        logger.info("Loft abgebrochen")

    def _stop_loft_mode(self):
        """Beendet den Loft-Modus und räumt auf."""
        self._loft_mode = False
        self._loft_profiles = []
        self._clear_loft_highlights()
        self._clear_loft_preview()
        self.loft_panel.hide()

    def _clear_loft_highlights(self):
        """Entfernt alle Loft-Profile-Highlights."""
        self._preview_clear_group("loft_highlights")

    def _clear_loft_preview(self):
        """Entfernt die Loft-Preview."""
        self._preview_clear_group("loft_preview")

    def _highlight_loft_profile(self, profile_data: dict, profile_index: int):
        """Highlightet ein Loft-Profil im Viewport."""
        import pyvista as pv
        import numpy as np

        if not hasattr(self.viewport_3d, 'plotter') or not self.viewport_3d.plotter:
            return

        try:
            shapely_poly = profile_data.get('shapely_poly')
            if not shapely_poly:
                return

            plane_origin = profile_data.get('plane_origin', (0, 0, 0))
            plane_x = profile_data.get('plane_x', (1, 0, 0))
            plane_y = profile_data.get('plane_y', (0, 1, 0))

            # Konvertiere Shapely-Polygon zu 3D-Punkten
            if hasattr(shapely_poly, 'exterior'):
                coords = list(shapely_poly.exterior.coords)
            else:
                coords = list(shapely_poly.coords)

            if len(coords) < 2:
                return

            # 2D zu 3D Transformation
            points_3d = []
            for x2d, y2d in coords:
                p3d = (
                    plane_origin[0] + x2d * plane_x[0] + y2d * plane_y[0],
                    plane_origin[1] + x2d * plane_x[1] + y2d * plane_y[1],
                    plane_origin[2] + x2d * plane_x[2] + y2d * plane_y[2]
                )
                points_3d.append(p3d)

            points = np.array(points_3d, dtype=np.float32)

            # Erstelle Linien-Mesh für das Profil
            n = len(points)
            lines = []
            for i in range(n - 1):
                lines.extend([2, i, i + 1])
            lines = np.array(lines, dtype=np.int32)

            # Verschiedene Farben für verschiedene Profile
            colors = ["#00ff00", "#00ccff", "#ff9900", "#ff00ff", "#ffff00"]
            color = colors[profile_index % len(colors)]

            poly = pv.PolyData(points, lines=lines)
            actor_name = f"loft_profile_{profile_index}_highlight"
            self.viewport_3d.plotter.add_mesh(
                poly,
                name=actor_name,
                color=color,
                line_width=4,
                render_lines_as_tubes=True
            )
            self._preview_track_actor("loft_highlights", actor_name)
            request_render(self.viewport_3d.plotter)  # PERFORMANCE: Use debounced queue

        except Exception as e:
            logger.warning(f"Loft-Profil-Highlight fehlgeschlagen: {e}")

    def _update_loft_preview(self):
        """Zeigt eine Preview des Loft-Ergebnisses."""
        import pyvista as pv
        import numpy as np

        if len(self._loft_profiles) < 2:
            self._clear_loft_preview()
            return

        try:
            # Einfache Linien-Preview zwischen Profilen
            self._clear_loft_preview()

            all_points = []
            all_lines = []
            point_offset = 0

            # Sammle alle Profil-Punkte
            profile_points_list = []
            for profile_data in sorted(self._loft_profiles, key=lambda p: p['plane_origin'][2]):
                shapely_poly = profile_data.get('shapely_poly')
                if not shapely_poly or not hasattr(shapely_poly, 'exterior'):
                    continue

                plane_origin = profile_data.get('plane_origin', (0, 0, 0))
                plane_x = profile_data.get('plane_x', (1, 0, 0))
                plane_y = profile_data.get('plane_y', (0, 1, 0))

                coords = list(shapely_poly.exterior.coords)[:-1]  # Ohne Schluss-Duplikat
                points_3d = []
                for x2d, y2d in coords:
                    p3d = [
                        plane_origin[0] + x2d * plane_x[0] + y2d * plane_y[0],
                        plane_origin[1] + x2d * plane_x[1] + y2d * plane_y[1],
                        plane_origin[2] + x2d * plane_x[2] + y2d * plane_y[2]
                    ]
                    points_3d.append(p3d)
                profile_points_list.append(points_3d)

            if len(profile_points_list) < 2:
                return

            # Verbindungslinien zwischen Profilen
            for i in range(len(profile_points_list) - 1):
                prof1 = profile_points_list[i]
                prof2 = profile_points_list[i + 1]

                # Einfache Verbindung: Verbinde entsprechende Punkte
                n_points = min(len(prof1), len(prof2))
                for j in range(0, n_points, max(1, n_points // 8)):  # Nur einige Punkte verbinden
                    all_points.append(prof1[j])
                    all_points.append(prof2[j % len(prof2)])
                    all_lines.extend([2, point_offset, point_offset + 1])
                    point_offset += 2

            if not all_points:
                return

            points = np.array(all_points, dtype=np.float32)
            lines = np.array(all_lines, dtype=np.int32)

            poly = pv.PolyData(points, lines=lines)
            self.viewport_3d.plotter.add_mesh(
                poly,
                name="loft_preview",
                color="#8888ff",  # Hellblau für Preview
                line_width=2,
                opacity=0.6,
                render_lines_as_tubes=True
            )
            self._preview_track_actor("loft_preview", "loft_preview")
            request_render(self.viewport_3d.plotter)  # PERFORMANCE: Use debounced queue

        except Exception as e:
            logger.warning(f"Loft-Preview fehlgeschlagen: {e}")

    # ==================== SECTION VIEW ====================

    def _on_section_enabled(self, plane: str, position: float):
        """Section View wurde aktiviert."""
        logger.info(f"🔪 Section View aktiviert: {plane} @ {position:.1f}mm")

        # Berechne Bounds für Slider
        min_pos, max_pos, default_pos = self.viewport_3d.get_section_bounds()
        self.section_panel.set_slider_bounds(min_pos, max_pos, default_pos)

        # Aktiviere in Viewport
        self.viewport_3d.enable_section_view(plane, position)

    def _on_section_disabled(self):
        """Section View wurde deaktiviert."""
        logger.info("🔪 Section View deaktiviert")
        self.viewport_3d.disable_section_view()

    def _on_section_position_changed(self, position: float):
        """Section Position wurde geändert."""
        self.viewport_3d.update_section_position(position)

    def _on_section_plane_changed(self, plane: str):
        """Section Plane wurde geändert."""
        logger.debug(f"🔪 Section Plane: {plane}")
        # Re-enable mit neuer Plane wird im Panel selbst gemacht

    def _on_section_invert_toggled(self):
        """Section Seite wurde invertiert."""
        self.viewport_3d.toggle_section_invert()

    def _toggle_section_view(self):
        """
        Öffnet/Schließt Section View Panel.

        User-Story: "ich brauchte für körper noch schnittansicht um besser zu prüfen ob cuts gingen"
        Implementierung: Cad-ähnliche Section Analysis mit Clipping Planes
        """
        if self.section_panel.isVisible():
            # Deaktiviere Section View
            self.section_panel.hide()
            if self.viewport_3d._section_view_enabled:
                self.viewport_3d.disable_section_view()
            logger.info("🔪 Section View Panel geschlossen")
        else:
            # Zeige Section View Panel
            if hasattr(self.section_panel, "_user_moved") and self.section_panel._user_moved:
                self.section_panel.show()
                self.section_panel.raise_()
                if hasattr(self.section_panel, "clamp_to_parent"):
                    self.section_panel.clamp_to_parent()
            else:
                self.section_panel.show_at(self.viewport_3d)

            # ✅ AUTO-AKTIVIEREN: Aktiviere Section View automatisch beim Öffnen
            if not self.section_panel._is_active:
                self.section_panel.toggle_button.click()  # Simuliere Button-Klick

            logger.info("🔪 Section View Panel geöffnet & aktiviert")
            logger.info("Tipp: Bewege Position-Slider um durch den Körper zu schneiden!")

    # ==================== BREP CLEANUP ====================

    def _toggle_brep_cleanup(self):
        """
        Oeffnet/Schliesst BREP Cleanup Panel.

        UX wie Fillet/Chamfer:
        - Falls Body ausgewaehlt -> sofort starten
        - Falls kein Body -> Pending-Mode, warte auf Viewport-Klick
        """
        if self.brep_cleanup_panel.isVisible():
            self._close_brep_cleanup()
            return

        # Prüfe ob Body im Browser ausgewählt
        selected_bodies = self.browser.get_selected_bodies()

        # Fall 1: Kein Body gewählt -> Pending-Mode
        if not selected_bodies:
            self._pending_brep_cleanup_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)

            # Aktiviere Body-Highlighting
            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)

            logger.info("BREP Cleanup: Klicke auf einen Koerper in der 3D-Ansicht")
            self.show_notification("Body waehlen", "Klicke auf einen Koerper fuer BREP Cleanup", "info")
            return

        # Fall 2: Body gewählt -> direkt starten
        body = selected_bodies[0]
        self._activate_brep_cleanup_for_body(body)

    def _on_body_clicked_for_brep_cleanup(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body angeklickt wird."""
        self._pending_brep_cleanup_mode = False

        # Pending-Mode deaktivieren
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        # Body finden
        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.warning(f"Body {body_id} nicht gefunden")
            return

        self._activate_brep_cleanup_for_body(body)

    def _activate_brep_cleanup_for_body(self, body):
        """Startet BREP Cleanup fuer einen Body."""
        if not hasattr(body, '_build123d_solid') or body._build123d_solid is None:
            self.show_notification("Kein BREP", "Der Body hat kein BREP. Zuerst Mesh zu CAD konvertieren.", "warning")
            return

        # Body-Lookup Callback setzen (damit Viewport den Body finden kann)
        self.viewport_3d._get_body_by_id = lambda bid: next(
            (b for b in self.document.bodies if b.id == bid), None
        )

        # Cleanup-Modus im Viewport starten
        success = self.viewport_3d.start_brep_cleanup_mode(body.id)
        if not success:
            self.show_notification("Fehler", "BREP Cleanup konnte nicht gestartet werden.", "error")
            return

        # Panel positionieren und zeigen
        viewport_geom = self.viewport_3d.geometry()
        panel_width = 350
        panel_x = viewport_geom.right() - panel_width - 30
        panel_y = viewport_geom.top() + 30

        self.brep_cleanup_panel.move(panel_x, panel_y)
        self.brep_cleanup_panel.show()
        self.brep_cleanup_panel.raise_()

        logger.info(f"BREP Cleanup gestartet fuer Body: {body.name}")

    def _close_brep_cleanup(self):
        """Schliesst BREP Cleanup Modus."""
        self._pending_brep_cleanup_mode = False
        self.brep_cleanup_panel.hide()
        self.viewport_3d.stop_brep_cleanup_mode()
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)
        logger.info("BREP Cleanup Panel geschlossen")

    def _on_brep_cleanup_feature_selected(self, feature_idx: int, additive: bool = False):
        """Feature im Panel ausgewaehlt."""
        self.viewport_3d.select_feature_by_index(feature_idx, additive)

    def _on_brep_cleanup_merge(self):
        """Merge-Button geklickt."""
        success = self.viewport_3d.execute_brep_cleanup_merge()
        if success:
            self.show_notification("Merge erfolgreich", "Faces wurden zusammengefuehrt.", "success")
            # Browser aktualisieren
            self._refresh_browser()
        else:
            self.show_notification("Merge fehlgeschlagen", "Konnte Faces nicht zusammenfuehren.", "error")

    def _on_brep_cleanup_merge_all(self):
        """Alle-Merge-Button geklickt."""
        body = self._get_active_body()
        if not body:
            return

        try:
            from modeling.brep_face_merger import merge_with_transaction
            result = merge_with_transaction(body)

            if result.is_success:
                self.show_notification("Auto-Merge erfolgreich", result.message, "success")
                self.viewport_3d.update_body_in_viewport(body.id)
                self._refresh_browser()

                # Analyse neu starten
                if self.viewport_3d.brep_cleanup_active:
                    self.viewport_3d.stop_brep_cleanup_mode()
                    self.viewport_3d.start_brep_cleanup_mode(body.id)
            else:
                self.show_notification("Auto-Merge fehlgeschlagen", result.message, "error")

        except Exception as e:
            self.show_notification("Fehler", f"Auto-Merge fehlgeschlagen: {e}", "error")


    # ==================== 3D OPERATIONEN ====================

    def _get_active_body(self):
        """Hilfsfunktion: Gibt den aktuell im Browser ausgewählten Body zurück"""
        items = self.browser.tree.selectedItems()
        if not items: return None
        # Wir suchen die ID aus dem Tree-Item
        # (Dies hängt von Ihrer Browser-Implementierung ab, hier eine generische Lösung)
        # Wenn Browser selection ein Body-Objekt liefert:
        if hasattr(self.browser, 'get_selected_body'):
            return self.browser.get_selected_body()
        
        # Fallback: Letzten Body nehmen
        if self.document.bodies:
            return self.document.bodies[-1]
        return None

    def _on_tnp_body_pick_requested(self):
        """User hat den Pick-Button im TNP-Panel geklickt."""
        self._pending_tnp_pick_mode = True
        self.viewport_3d.setCursor(Qt.CrossCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(True)
        self.statusBar().showMessage(tr("Body im Viewport anklicken…"))

    def _on_body_clicked_for_tnp(self, body_id: str):
        """Body wurde im Viewport für TNP-Panel ausgewählt."""
        self._pending_tnp_pick_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)
        try:
            body = None
            for b in self.document.bodies:
                if getattr(b, 'id', None) == body_id:
                    body = b
                    break

            if body:
                self._update_tnp_stats(body)
                self.statusBar().showMessage(f"TNP: {body.name}")
            else:
                self.statusBar().showMessage(tr("Body nicht gefunden"))
        except Exception as e:
            logger.error(f"TNP Body-Pick fehlgeschlagen: {e}")
            self.statusBar().showMessage(tr("TNP-Auswahl fehlgeschlagen"))
        finally:
            if hasattr(self, "tnp_stats_panel"):
                self.tnp_stats_panel.set_picking_active(False)

    def _solid_signature_safe(self, body) -> dict:
        """Erzeugt einen Geometry-Fingerprint (volume, faces, edges) oder None."""
        try:
            solid = body._build123d_solid if body else None
            if solid is None:
                return None
            return {
                "volume": float(solid.volume),
                "faces": len(list(solid.faces())),
                "edges": len(list(solid.edges())),
            }
        except Exception:
            return None

    def _update_tnp_stats(self, body=None):
        """
        Aktualisiert das TNP-Statistiken-Panel.

        Merkt sich den letzten Body, sodass nach Aktionen das Panel
        nicht leer wird (der User muss nicht erneut im Browser selektieren).

        Args:
            body: Body-Objekt oder None (verwendet dann letzten/aktiven Body)
        """
        if not hasattr(self, 'tnp_stats_panel'):
            return

        if body is not None:
            self._last_tnp_body_id = getattr(body, 'id', None)
        else:
            body = self._get_active_body()
            if body is None and hasattr(self, '_last_tnp_body_id') and self._last_tnp_body_id:
                for b in self.document.bodies:
                    if getattr(b, 'id', None) == self._last_tnp_body_id:
                        body = b
                        break

        try:
            self.tnp_stats_panel.update_stats(body)
        except Exception as e:
            logger.error(f"TNP Stats Update fehlgeschlagen: {e}")
            try:
                self.tnp_stats_panel.update_stats(None)
            except Exception:
                pass

    def _move_body(self):
        body = self._get_active_body()
        if not body: return logger.warning("Kein Körper ausgewählt!")
        
        dlg = VectorInputDialog("Verschieben", ("X (mm):", "Y (mm):", "Z (mm):"), (0,0,0), self)
        if dlg.exec():
            dx, dy, dz = dlg.get_values()
            if dx==0 and dy==0 and dz==0: return
            
            # 1. Build123d Transformation (für saubere Historie)
            if HAS_BUILD123D and hasattr(body, '_build123d_solid') and body._build123d_solid:
                from build123d import Location
                body._build123d_solid = body._build123d_solid.move(Location((dx, dy, dz)))
                # Mesh neu generieren
                self._update_body_from_build123d(body, body._build123d_solid)
            else:
                # 2. PyVista Mesh Transformation (Fallback)
                mesh = self.viewport_3d.get_body_mesh(body.id)
                if mesh:
                    mesh.translate((dx, dy, dz), inplace=True)
                    self._update_body_mesh(body, mesh)
            
            self.browser.refresh()
            logger.success(f"Körper verschoben: {dx}, {dy}, {dz}")

    def _scale_body(self):
        body = self._get_active_body()
        if not body: return logger.warning("Kein Körper ausgewählt!")
        
        dlg = VectorInputDialog("Skalieren", ("Faktor:",), (1.0,), self)
        if dlg.exec():
            s = dlg.get_values()[0]
            if s == 1.0 or s <= 0: return

            if HAS_BUILD123D and hasattr(body, '_build123d_solid') and body._build123d_solid:
                body._build123d_solid = body._build123d_solid.scale(s)
                self._update_body_from_build123d(body, body._build123d_solid)
            else:
                mesh = self.viewport_3d.get_body_mesh(body.id)
                if mesh:
                    mesh.scale(s, inplace=True)
                    self._update_body_mesh(body, mesh)
            self.browser.refresh()

    def _rotate_body(self):
        body = self._get_active_body()
        if not body: return logger.warning("Kein Körper ausgewählt!")
        
        # Einfacher Dialog: Achse + Winkel
        dlg = VectorInputDialog("Rotieren", ("X-Achse (0/1):", "Y-Achse (0/1):", "Z-Achse (0/1):", "Winkel (°):"), (0,0,1,90), self)
        # Hack: Label 4 ist Winkel. Wir nutzen VectorInputDialog generisch.
        if dlg.exec():
            ax, ay, az, angle = dlg.get_values()
            if angle == 0: return
            
            axis = (ax, ay, az)
            
            if HAS_BUILD123D and hasattr(body, '_build123d_solid') and body._build123d_solid:
                from build123d import Axis, Location
                # Rotation um Zentrum oder Ursprung? Hier Ursprung (einfacher)
                # Für Rotation um Objektzentrum müsste man BoundingBox Center berechnen
                body._build123d_solid = body._build123d_solid.rotate(Axis((0,0,0), axis), angle)
                self._update_body_from_build123d(body, body._build123d_solid)
            else:
                mesh = self.viewport_3d.get_body_mesh(body.id)
                if mesh:
                    mesh.rotate_vector(vector=axis, angle=angle, inplace=True)
                    self._update_body_mesh(body, mesh)
            self.browser.refresh()

    def _copy_body(self):
        """Kopiert den aktiven Body als neuen Body."""
        body = self._get_active_body()
        if not body:
            logger.warning("Kein Body ausgewählt für Kopieren")
            return

        from modeling.cad_tessellator import CADTessellator
        from modeling import Body

        # Neuen Body erstellen
        new_b = Body(name=f"{body.name}_Kopie", document=self.document)

        # Build123d Solid kopieren
        # HINWEIS: Build123d Part/Solid hat keine .copy() Methode!
        # Workaround: moved(Location((0,0,0))) erstellt eine Kopie
        if hasattr(body, '_build123d_solid') and body._build123d_solid:
            try:
                from build123d import Location
                # Identity-Move erstellt eine Kopie des Shapes
                new_b._build123d_solid = body._build123d_solid.moved(Location((0, 0, 0)))
                logger.debug(f"Build123d Solid kopiert für {new_b.name}")
            except Exception as e:
                logger.error(f"Solid-Kopie mit moved() fehlgeschlagen: {e}")
                # Fallback: OCP BRepBuilderAPI_Copy
                try:
                    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
                    from build123d import Solid
                    copier = BRepBuilderAPI_Copy(body._build123d_solid.wrapped)
                    copier.Perform(body._build123d_solid.wrapped)
                    if copier.IsDone():
                        new_b._build123d_solid = Solid(copier.Shape())
                        logger.debug(f"OCP Copy erfolgreich für {new_b.name}")
                    else:
                        logger.error("OCP Copy fehlgeschlagen")
                        return
                except Exception as e2:
                    logger.error(f"Auch OCP Copy fehlgeschlagen: {e2}")
                    return

        # Mesh generieren
        CADTessellator.notify_body_changed()
        self._update_body_from_build123d(new_b, new_b._build123d_solid)

        # Zum Document hinzufügen
        self.document.add_body(new_b, set_active=False)

        # UI aktualisieren
        self.browser.refresh()
        logger.success(f"Kopie erstellt: {new_b.name}")

    def _mirror_body(self):
        body = self._get_active_body()
        if not body: return

        # Einfachheitshalber Mirror an XZ Ebene (Y spiegeln)
        # In Zukunft könnte man Plane Selection machen
        if HAS_BUILD123D and hasattr(body, '_build123d_solid') and body._build123d_solid:
            from build123d import Plane
            # Mirror an XZ Plane (Normal Y)
            body._build123d_solid = body._build123d_solid.mirror(Plane.XZ)
            self._update_body_from_build123d(body, body._build123d_solid)
        else:
            mesh = self.viewport_3d.get_body_mesh(body.id)
            if mesh:
                mesh.reflect((0,1,0), point=(0,0,0), inplace=True)
                self._update_body_mesh(body, mesh)
        self.browser.refresh()

    def _boolean_operation_dialog(self, op_type="Cut"):
        """Führt Union, Cut oder Intersect aus"""
        if len(self.document.bodies) < 2:
            QMessageBox.warning(self, "Fehler", "Mindestens 2 Körper benötigt!")
            return

        dlg = BooleanDialog(self.document.bodies, op_type, self)
        if dlg.exec():
            tid, tool_id = dlg.get_ids()
            if tid == tool_id: return
            
            target = next(b for b in self.document.bodies if b.id == tid)
            tool = next(b for b in self.document.bodies if b.id == tool_id)
            
            success = False
            
            # 1. Versuch: Build123d (Exakt)
            if HAS_BUILD123D:
                try:
                    s1 = getattr(target, '_build123d_solid', None)
                    s2 = getattr(tool, '_build123d_solid', None)

                    if s1 and s2:
                        # Phase 5: BBox Early-Rejection (nur für Cut/Intersect sinnvoll)
                        if is_enabled("bbox_early_rejection") and op_type in ["Cut", "Intersect"]:
                            try:
                                bbox1 = s1.bounding_box()
                                bbox2 = s2.bounding_box()

                                # Prüfe ob BBoxes sich überschneiden
                                # BBox format: min(x,y,z), max(x,y,z)
                                overlap_x = not (bbox1.max.X < bbox2.min.X or bbox2.max.X < bbox1.min.X)
                                overlap_y = not (bbox1.max.Y < bbox2.min.Y or bbox2.max.Y < bbox1.min.Y)
                                overlap_z = not (bbox1.max.Z < bbox2.min.Z or bbox2.max.Z < bbox1.min.Z)

                                if not (overlap_x and overlap_y and overlap_z):
                                    # Keine Überschneidung → Operation würde fehlschlagen
                                    logger.info(f"BBox Early-Rejection: Geometrien überschneiden sich nicht")
                                    QMessageBox.information(
                                        self,
                                        "Info",
                                        f"Die Geometrien überschneiden sich nicht.\n{op_type}-Operation nicht möglich."
                                    )
                                    return  # Early-Return spart 50-100ms
                            except Exception as e:
                                logger.debug(f"BBox check failed, continuing anyway: {e}")

                        new_solid = None
                        if op_type == "Union": new_solid = s1 + s2
                        elif op_type == "Cut": new_solid = s1 - s2
                        elif op_type == "Intersect": new_solid = s1 & s2
                        
                        if new_solid:
                            target._build123d_solid = new_solid
                            self._update_body_from_build123d(target, new_solid)
                            
                            # Tool löschen oder verstecken? Meistens löschen bei Boolean
                            # Wir verstecken es erstmal
                            self.viewport_3d.set_body_visibility(tool.id, False)
                            success = True
                except Exception as e:
                    logger.exception(f"Build123d Boolean Error: {e}")

            # 2. Versuch: PyVista Mesh Boolean (Fallback)
            if not success:
                m1 = self.viewport_3d.get_body_mesh(target.id)
                m2 = self.viewport_3d.get_body_mesh(tool.id)
                
                if m1 and m2:
                    res = self._perform_boolean_operation(m1, m2, op_type)
                    if res:
                        self._update_body_mesh(target, res)
                        self.viewport_3d.set_body_visibility(tool.id, False)
                        success = True
            
            if success:
                logger.success(f"Boolean {op_type} erfolgreich.")
                self.browser.refresh()
            else:
                QMessageBox.warning(self, "Fehler", "Operation fehlgeschlagen (Geometrie Fehler).")
