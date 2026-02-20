"""
MashCAD Main Window Setup Module
=================================

Extracted from main_window.py (AR-005 EXTENDED).

This module contains UI setup and initialization code as a mixin class.
Maintains backward compatibility by being imported into MainWindow.

Usage:
    class MainWindow(SetupMixin, QMainWindow):
        pass
"""

from typing import TYPE_CHECKING
from loguru import logger

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QSplitter, QStackedWidget, QWidget, QVBoxLayout, QHBoxLayout, QDockWidget

if TYPE_CHECKING:
    from gui.main_window import MainWindow


class SetupMixin:
    """
    Mixin class containing UI setup and initialization for MainWindow.
    
    This class provides:
    - Theme application
    - UI creation (_create_ui)
    - Menu creation (_create_menus)
    - Signal connections (_connect_signals)
    - Logging setup
    
    All methods assume they are called within a MainWindow context
    and access MainWindow attributes via `self`.
    """
    
    # =========================================================================
    # Logging Setup
    # =========================================================================
    
    def _setup_logging(self):
        """Setup logging handlers for the application."""
        from gui.widgets import QtLogHandler
        import sys
        
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
            
    def _show_toast_overlay(self, level, message, status_class="", severity=""):
        """
        Delegiert an NotificationManager.

        W10 Paket B: Erweitert um status_class/severity Parameter.
        """
        self.notification_manager.show_toast_overlay(level, message, status_class=status_class, severity=severity)

    def show_notification(self, title: str, message: str, level: str = "info", duration: int = 3000,
                         status_class: str = "", severity: str = ""):
        """
        Zeigt eine Toast-Notification an.

        W10 Paket B: Erweitert um status_class/severity Parameter aus Error-Envelope v2.

        Args:
            title: Titel der Notification
            message: Nachricht der Notification
            level: Legacy level (info/warning/error/success/critical)
            duration: Anzeigedauer in ms
            status_class: status_class aus Error-Envelope v2 (WARNING_RECOVERABLE, BLOCKED, CRITICAL, ERROR)
            severity: severity aus Error-Envelope v2 (warning, blocked, critical, error)
        """
        self.notification_manager.show_notification(title, message, level, duration,
                                                     status_class=status_class, severity=severity)
    
    # =========================================================================
    # Theme
    # =========================================================================
    
    def _apply_theme(self):
        """Apply the application theme."""
        from gui.design_tokens import DesignTokens
        self.setStyleSheet(DesignTokens.stylesheet_main())
    
    # =========================================================================
    # UI Creation
    # =========================================================================
    
    def _create_ui(self):
        """Create the main user interface."""
        from gui.design_tokens import DesignTokens
        from i18n import tr
        from PySide6.QtWidgets import QTabWidget
        
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

        self._create_browser_panel()
        self._create_log_panel(tr)
        self._create_tnp_panel()

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
        self._create_tool_stack(DesignTokens, left_splitter)
        
        # Browser/TNP Tabs kollabierbar, ToolPanel bleibt
        left_splitter.setCollapsible(0, True)
        left_splitter.setCollapsible(1, False)
        left_splitter.setSizes([140, 200])
        
        self.main_splitter.addWidget(left_splitter)
        
        # === MITTE: Viewport / Sketch Editor ===
        self._create_center_stack(DesignTokens)
        
        self.main_splitter.addWidget(self.center_stack)
        self.sketch_editor.viewport = self.viewport_3d

        # Transform Toolbar (floating rechts im Viewport)
        self._create_transform_toolbar()

        # Splitter-Einstellungen
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([340, 1000])
        
        layout.addWidget(self.main_splitter)
        
        # === RECHTE SEITE: Properties (nur wenn nötig) ===
        self._create_right_stack(DesignTokens, layout)
        
        # W26 F-UX-1: Feature Detail Panel als DockWidget
        self._create_feature_detail_dock(tr)

        # === STATUS BAR (unten) ===
        self._create_status_bar(main_vertical)
        
        # === INPUT PANELS ===
        self._create_input_panels()
        
        # === CONNECT SKETCH EDITOR ===
        self._connect_sketch_editor_signals()

    def _create_browser_panel(self):
        """Create the project browser panel."""
        from gui.browser import ProjectBrowser
        
        self.browser = ProjectBrowser()
        self.browser.set_document(self.document)

    def _create_log_panel(self, tr):
        """Create the log panel."""
        from gui.log_panel import LogPanel
        from gui.widgets import TNPStatsPanel, OperationSummaryWidget, FeatureDetailPanel
        
        self.log_panel = LogPanel()
        self.tnp_stats_panel = TNPStatsPanel()
        self.operation_summary = OperationSummaryWidget()
        
        # W26 F-UX-1: Feature Detail Panel für Recovery-Actions
        self.feature_detail_panel = FeatureDetailPanel()
        self.feature_detail_panel.setMinimumWidth(250)
        self.feature_detail_panel.setMaximumWidth(350)

    def _create_tnp_panel(self):
        """Create TNP stats panel connections."""
        # TNP panel is created in _create_log_panel
        pass

    def _create_tool_stack(self, DesignTokens, left_splitter):
        """Create the tool panel stack."""
        from gui.tool_panel import ToolPanel
        from gui.tool_panel_3d import ToolPanel3D
        from gui.transform_state import TransformState
        
        # Tool-Panel Stack (3D oder 2D)
        self.tool_stack = QStackedWidget()
        self.tool_stack.setMinimumWidth(220)
        self.tool_stack.setStyleSheet(f"background-color: {DesignTokens.COLOR_BG_PANEL.name()};")

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

    def _create_center_stack(self, DesignTokens):
        """Create the center stack with viewport and sketch editor."""
        from gui.viewport_pyvista import PyVistaViewport
        from gui.sketch_editor import SketchEditor
        from gui.widgets.getting_started_overlay import GettingStartedOverlay
        
        self.center_stack = QStackedWidget()
        self.center_stack.setStyleSheet(f"background-color: {DesignTokens.COLOR_BG_PANEL.name()};")
        
        self.viewport_3d = PyVistaViewport()
        self.viewport_3d.document = self.document
        self.center_stack.addWidget(self.viewport_3d)

        # Getting Started Overlay (zentriert im Viewport)
        self._getting_started_overlay = GettingStartedOverlay(self.viewport_3d)
        self._getting_started_overlay.action_triggered.connect(self._on_3d_action)
        self._getting_started_overlay.action_triggered.connect(lambda: self._getting_started_overlay.hide())
        self._getting_started_overlay.recent_file_requested.connect(self._open_recent_file)
        self._getting_started_overlay.tutorial_requested.connect(self._start_tutorial)
        
        self.sketch_editor = SketchEditor()
        self.center_stack.addWidget(self.sketch_editor)

    def _create_transform_toolbar(self):
        """Create the transform toolbar."""
        from gui.widgets.transform_toolbar import TransformToolbar
        
        self.transform_toolbar = TransformToolbar(self.viewport_3d)
        self.transform_toolbar.action_triggered.connect(self._on_3d_action)
        self.transform_toolbar.raise_()
        self.viewport_3d.installEventFilter(self)

    def _create_right_stack(self, DesignTokens, layout):
        """Create the right properties stack."""
        from gui.tool_panel import PropertiesPanel
        from gui.tool_panel_3d import BodyPropertiesPanel
        
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

    def _create_feature_detail_dock(self, tr):
        """Create the feature detail dock widget."""
        self.feature_detail_dock = QDockWidget(tr("Feature Details"), self)
        self.feature_detail_dock.setWidget(self.feature_detail_panel)
        self.feature_detail_dock.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self.feature_detail_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.feature_detail_dock.setStyleSheet("""
            QDockWidget { color: #ccc; font-size: 11px; }
            QDockWidget::title {
                background: #252526; padding: 4px 8px;
                border-bottom: 1px solid #333;
            }
        """)
        self.addDockWidget(Qt.RightDockWidgetArea, self.feature_detail_dock)
        self.feature_detail_dock.hide()  # Initial versteckt

    def _create_status_bar(self, main_vertical):
        """Create the status bar."""
        from gui.widgets.status_bar import MashCadStatusBar
        from gui.viewport.render_queue import RenderQueue
        from config.feature_flags import is_enabled
        
        self.mashcad_status_bar = MashCadStatusBar()
        main_vertical.addWidget(self.mashcad_status_bar)

        # FPS Counter mit StatusBar verbinden
        RenderQueue.register_fps_callback(self.mashcad_status_bar.update_fps)

        # W3: Strict Mode Indicator
        if is_enabled("strict_topology_fallback_policy"):
            self.mashcad_status_bar.set_strict_mode(True)

    def _create_input_panels(self):
        """Create all input panels."""
        from gui.input_panels import (
            ExtrudeInputPanel, FilletChamferPanel, TransformPanel,
            ShellInputPanel, SweepInputPanel, LoftInputPanel,
            PatternInputPanel, NSidedPatchInputPanel, LatticeInputPanel,
            CenterHintWidget, PointToPointMovePanel
        )
        from gui.input_panels import RevolveInputPanel, OffsetPlaneInputPanel, HoleInputPanel
        from gui.input_panels import ThreadInputPanel, DraftInputPanel, SplitInputPanel
        from gui.widgets.texture_panel import SurfaceTexturePanel
        from gui.widgets.section_view_panel import SectionViewPanel
        
        # Extrude Input Panel
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
        self.revolve_panel = RevolveInputPanel(self)
        self.revolve_panel.angle_changed.connect(self._on_revolve_angle_changed)
        self.revolve_panel.axis_changed.connect(self._on_revolve_axis_changed)
        self.revolve_panel.operation_changed.connect(self._on_revolve_operation_changed)
        self.revolve_panel.confirmed.connect(self._on_revolve_confirmed)
        self.revolve_panel.cancelled.connect(self._on_revolve_cancelled)
        self.revolve_panel.direction_flipped.connect(self._on_revolve_direction_flipped)

        # Offset Plane Input Panel
        self.offset_plane_panel = OffsetPlaneInputPanel(self)
        self.offset_plane_panel.offset_changed.connect(self._on_offset_plane_value_changed)
        self.offset_plane_panel.confirmed.connect(self._on_offset_plane_confirmed)
        self.offset_plane_panel.cancelled.connect(self._on_offset_plane_cancelled)
        self._offset_plane_pending = False

        # Hole Input Panel
        self.hole_panel = HoleInputPanel(self)
        self.hole_panel.diameter_changed.connect(self._on_hole_diameter_changed)
        self.hole_panel.depth_changed.connect(self._on_hole_depth_changed)
        self.hole_panel.confirmed.connect(self._on_hole_confirmed)
        self.hole_panel.cancelled.connect(self._on_hole_cancelled)
        self._hole_mode = False
        self._hole_face_selector = None
        self._hole_face_shape_id = None
        self._hole_face_index = None

        # Thread Input Panel
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
        self.draft_panel = DraftInputPanel(self)
        self.draft_panel.angle_changed.connect(self._on_draft_angle_changed)
        self.draft_panel.axis_changed.connect(self._on_draft_axis_changed)
        self.draft_panel.confirmed.connect(self._on_draft_confirmed)
        self.draft_panel.cancelled.connect(self._on_draft_cancelled)
        self._draft_mode = False

        # Split Input Panel
        self.split_panel = SplitInputPanel(self)
        self.split_panel.plane_changed.connect(self._on_split_plane_changed)
        self.split_panel.position_changed.connect(self._on_split_position_changed)
        self.split_panel.angle_changed.connect(self._on_split_angle_changed)
        self.split_panel.keep_changed.connect(self._on_split_keep_changed)
        self.split_panel.confirmed.connect(self._on_split_confirmed)
        self.split_panel.cancelled.connect(self._on_split_cancelled)
        self._split_mode = False

        # Center Hint Widget
        self.center_hint = CenterHintWidget(self)
        self.center_hint.hide()
        
        # Fillet/Chamfer Panel
        self.fillet_panel = FilletChamferPanel(self)
        self.fillet_panel.radius_changed.connect(self._on_fillet_radius_changed)
        self.fillet_panel.confirmed.connect(self._on_fillet_confirmed)
        self.fillet_panel.cancelled.connect(self._on_fillet_cancelled)

        self._fillet_mode = None  # 'fillet' or 'chamfer'
        self._fillet_target_body = None

        # Shell Panel
        self.shell_panel = ShellInputPanel(self)
        self.shell_panel.thickness_changed.connect(self._on_shell_thickness_changed)
        self.shell_panel.confirmed.connect(self._on_shell_confirmed)
        self.shell_panel.cancelled.connect(self._on_shell_cancelled)

        self._shell_mode = False
        self._shell_target_body = None
        self._shell_opening_faces = []
        self._shell_opening_face_shape_ids = []
        self._shell_opening_face_indices = []

        # Surface Texture Panel
        self.texture_panel = SurfaceTexturePanel(self)
        self.texture_panel.texture_applied.connect(self._on_texture_applied)
        self.texture_panel.preview_requested.connect(self._on_texture_preview_requested)
        self.texture_panel.cancelled.connect(self._on_texture_cancelled)

        self._texture_mode = False
        self._texture_target_body = None
        self._pending_texture_mode = False
        self._pending_mesh_convert_mode = False

        # Sweep Panel
        self.sweep_panel = SweepInputPanel(self)
        self.sweep_panel.confirmed.connect(self._on_sweep_confirmed)
        self.sweep_panel.cancelled.connect(self._on_sweep_cancelled)
        self.sweep_panel.sketch_path_requested.connect(self._on_sweep_sketch_path_requested)
        self.sweep_panel.profile_cleared.connect(self._on_sweep_profile_cleared)
        self.sweep_panel.path_cleared.connect(self._on_sweep_path_cleared)

        self._sweep_mode = False
        self._sweep_phase = None
        self._sweep_profile_data = None
        self._sweep_path_data = None
        self._sweep_profile_shape_id = None
        self._sweep_profile_face_index = None
        self._sweep_profile_geometric_selector = None

        # Loft Panel
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
        self._preview_actor_groups = {}
        self._pending_pattern_mode = False

        # N-Sided Patch Panel
        self.nsided_patch_panel = NSidedPatchInputPanel(self)
        self.nsided_patch_panel.confirmed.connect(self._on_nsided_patch_confirmed)
        self.nsided_patch_panel.cancelled.connect(self._on_nsided_patch_cancelled)

        self._nsided_patch_mode = False
        self._nsided_patch_target_body = None
        self._pending_nsided_patch_mode = False

        # Lattice Panel
        self.lattice_panel = LatticeInputPanel(self)
        self.lattice_panel.confirmed.connect(self._on_lattice_confirmed)
        self.lattice_panel.cancelled.connect(self._on_lattice_cancelled)

        self._lattice_mode = False
        self._lattice_target_body = None
        self._pending_lattice_mode = False

        # Section View Panel
        self.section_panel = SectionViewPanel(self)
        self.section_panel.section_enabled.connect(self._on_section_enabled)
        self.section_panel.section_disabled.connect(self._on_section_disabled)
        self.section_panel.section_position_changed.connect(self._on_section_position_changed)
        self.section_panel.section_plane_changed.connect(self._on_section_plane_changed)
        self.section_panel.section_invert_toggled.connect(self._on_section_invert_toggled)
        self.section_panel.close_requested.connect(self._toggle_section_view)
        self.section_panel.hide()

        # Point-to-Point Move Panel
        self.p2p_panel = PointToPointMovePanel(self)
        self.p2p_panel.pick_body_requested.connect(self._on_p2p_pick_body_requested)
        self.p2p_panel.reset_requested.connect(self._reset_point_to_point_move)
        self.p2p_panel.cancel_requested.connect(self._cancel_point_to_point_move)
        self.p2p_panel.hide()
        self._p2p_body_id = None
        self._p2p_repick_body = False

        # Edge Selection Signal verbinden
        self.viewport_3d.edge_selection_changed.connect(self._on_edge_selection_changed)

        # Texture Face Selection Signal verbinden
        self.viewport_3d.texture_face_selected.connect(self._on_texture_face_selected)

        # Sketch-Pfad-Selektion für Sweep
        self.viewport_3d.sketch_path_clicked.connect(self._on_sketch_path_clicked)

    def _connect_sketch_editor_signals(self):
        """Connect sketch editor signals."""
        self.tool_panel.option_changed.connect(self.sketch_editor.handle_option_changed)
        self.sketch_editor.construction_mode_changed.connect(self.tool_panel.set_construction)
        self.sketch_editor.grid_snap_mode_changed.connect(self.tool_panel.set_grid_snap)
        self.sketch_editor.exit_requested.connect(self._finish_sketch)
        self.sketch_editor.sketched_changed.connect(self._on_sketch_changed_refresh_viewport)
        self.sketch_editor.solver_finished_signal.connect(self._on_solver_dof_updated)
        
        # W32: Live zoom badge
        self.sketch_editor.zoom_changed.connect(self.mashcad_status_bar.set_zoom)
        self.mashcad_status_bar.zoom_preset_requested.connect(self.sketch_editor.set_zoom_to)
        self.mashcad_status_bar.zoom_fit_requested.connect(self.sketch_editor._fit_view)
        
        # W26 FIX: Projection-Preview Signals
        self.sketch_editor.projection_preview_requested.connect(self._on_projection_preview_requested)
        self.sketch_editor.projection_preview_cleared.connect(self._on_projection_preview_cleared)

    def showEvent(self, event):
        """Handle show event."""
        super().showEvent(event)
        QTimer.singleShot(0, self._reposition_all_panels)

    # =========================================================================
    # Menu Creation
    # =========================================================================
    
    def _create_menus(self):
        """Create the application menus."""
        from i18n import tr
        from PySide6.QtGui import QKeySequence
        
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
        file_menu.addAction(tr("Export 3MF..."), self._export_3mf)
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

    # =========================================================================
    # Signal Connections
    # =========================================================================
    
    def _connect_signals(self):
        """Connect all signals between components."""
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
        self.browser.feature_deleted.connect(self._on_feature_deleted)
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
        
        # W26 F-UX-1: Browser Batch-Signale für Problem-Features
        self.browser.batch_retry_rebuild.connect(self._on_batch_retry_rebuild)
        self.browser.batch_open_diagnostics.connect(self._on_batch_open_diagnostics)
        self.browser.batch_isolate_bodies.connect(self._on_batch_isolate_bodies)
        
        # W29 E2E Closeout: Browser Batch-Signale für Unhide/Focus
        self.browser.batch_unhide_bodies.connect(self._on_batch_unhide_bodies)
        self.browser.batch_focus_features.connect(self._on_batch_focus_features)
        
        # W26 F-UX-1: FeatureDetailPanel Recovery-Signale
        self.feature_detail_panel.recovery_action_requested.connect(self._on_recovery_action_requested)
        self.feature_detail_panel.edit_feature_requested.connect(self._on_edit_feature_requested)
        self.feature_detail_panel.rebuild_feature_requested.connect(self._on_rebuild_feature_requested)
        self.feature_detail_panel.delete_feature_requested.connect(self._on_delete_feature_requested)
        self.feature_detail_panel.highlight_edges_requested.connect(self._on_highlight_edges_requested)
        
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


# =============================================================================
# Backward Compatibility Exports
# =============================================================================

__all__ = [
    'SetupMixin',
]
