"""
MashCad - Unified Main Window
V3.0: Refactored with MessageManager, modular structure
"""

import sys
import os
import json
import math
import numpy as np
from loguru import logger


from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QToolBar, QStatusBar, QMenuBar, QMenu, QFileDialog,
    QMessageBox, QSplitter, QFrame, QTreeWidget, QTreeWidgetItem,
    QStackedWidget, QApplication, QDialog, QFormLayout,
    QDoubleSpinBox, QDialogButtonBox, QSpinBox, QLineEdit,
    QTableWidget, QTableWidgetItem, QPushButton, QHeaderView, QComboBox,
    QScrollArea, QGraphicsOpacityEffect
)

from PySide6.QtCore import Qt, Signal, QSize, QTimer, QPointF, QEvent, QPropertyAnimation, QEasingCurve, QObject, QPoint
from PySide6.QtGui import QKeySequence, QAction, QFont, QPainter, QPen, QBrush, QColor, QPolygonF


_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from i18n import tr
from sketcher import Sketch
from modeling import Document, Body, ExtrudeFeature, FilletFeature, ChamferFeature, FeatureType, SurfaceTextureFeature
from modeling.brep_utils import pick_face_by_ray, find_closest_face

# GUI Module
from gui.sketch_editor import SketchEditor, SketchTool
from gui.tool_panel import ToolPanel, PropertiesPanel
from gui.tool_panel_3d import ToolPanel3D, BodyPropertiesPanel
from gui.browser import ProjectBrowser
from gui.input_panels import ExtrudeInputPanel, FilletChamferPanel, TransformPanel, CenterHintWidget, ShellInputPanel, SweepInputPanel, LoftInputPanel
from gui.widgets.texture_panel import SurfaceTexturePanel
from gui.viewport_pyvista import PyVistaViewport, HAS_PYVISTA, HAS_BUILD123D
from gui.viewport.render_queue import request_render  # Phase 4: Performance
from config.tolerances import Tolerances  # Phase 5: Zentralisierte Toleranzen
from gui.log_panel import LogPanel
from gui.widgets import NotificationWidget, QtLogHandler, TNPStatsPanel
from gui.widgets.section_view_panel import SectionViewPanel
from gui.dialogs import VectorInputDialog, BooleanDialog
from gui.parameter_dialog import ParameterDialog
from gui.transform_state import TransformState

try:
    from ocp_tessellate.tessellator import tessellate
    HAS_OCP_TESSELLATE = True
except ImportError:
    HAS_OCP_TESSELLATE = False
    logger.warning("ocp-tessellate nicht gefunden. Nutze Standard-Tessellierung.")

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
        
        # Cache leeren beim Start (für saubere B-Rep Edges)
        try:
            from modeling.cad_tessellator import CADTessellator
            CADTessellator.notify_body_changed()
        except:
            pass
        
        self._setup_logging()
        self.document = Document("Projekt1")
        self._current_project_path = None  # Phase 8.2: Aktueller Projekt-Pfad

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
        
        # Konsole (stderr) für Debugging
        logger.add(sys.stderr, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")
        # Qt Handler für GUI
        logger.add(self.qt_log_handler.write, format="{message}", level="INFO")

    def _handle_log_message(self, level, message):
        """
        Zentrale Stelle für alle Nachrichten.
        1. Fügt IMMER einen Eintrag ins Log-Panel hinzu.
        2. Zeigt NUR bei Success/Error/Warning ein Overlay an.
        """
        # 1. Ins persistente Log schreiben
        self.log_panel.add_message(level, message)
        
        # 2. Overlay Entscheidung
        show_overlay = False
        if level in ["success", "error", "critical"]:
            show_overlay = True
        elif level == "warning":
            # Warnings auch zeigen, aber vielleicht kürzer (optional)
            show_overlay = True
            
        if show_overlay:
            self._show_toast_overlay(level, message)
            
    def _show_toast_overlay(self, level, message):
        """Erstellt das Toast-Popup (ehemals _show_notification)"""
        # Mapping von Loguru levels für Style
        if level in ["critical", "error"]: style = "error"
        elif level == "warning": style = "warning"
        elif level == "success": style = "success"
        else: style = "info"

        # Widget erstellen
        notif = NotificationWidget(message, style, self)
        self.notifications.append(notif)
        self._reposition_notifications()

    def show_notification(self, title: str, message: str, level: str = "info", duration: int = 3000):
        """
        Zeigt eine Toast-Notification an (für Result-Pattern Integration)

        Args:
            title: Titel der Notification (wird in message integriert)
            message: Haupt-Nachricht
            level: "info", "success", "warning", "error"
            duration: Dauer in ms (wird aktuell nicht verwendet, da NotificationWidget Auto-Close hat)
        """
        # Kombiniere Title und Message
        if title:
            full_message = f"{title}: {message}"
        else:
            full_message = message

        # Nutze bestehende Toast-Overlay Methode
        self._show_toast_overlay(level, full_message)



    def _cleanup_notification(self, notif):
        if notif in self.notifications:
            self.notifications.remove(notif)
        notif.deleteLater()
        # Nach dem Löschen die anderen aufrücken lassen
        # (Optional, hier vereinfacht lassen wir sie stehen bis sie verschwinden)

    def _reposition_notifications(self):
        """Berechnet Positionen und startet Animationen"""
        top_margin = 90
        spacing = 10
        y_pos = top_margin
        
        # Iteriere über alle aktiven Notifications
        for notif in self.notifications:
            if not notif.isVisible() and not notif.target_pos:
                # Neue Notification (noch nicht animiert)
                # Zentrieren
                x = (self.width() - notif.width()) // 2
                
                # Cleanup Signal verbinden
                notif.anim.finished.connect(
                    lambda n=notif: self._cleanup_notification(n) if n.anim.direction() == QPropertyAnimation.Backward else None
                )
                
                # Animation starten
                notif.show_anim(QPoint(x, y_pos))
            
            elif notif.isVisible():
                # Bereits sichtbare Notifications verschieben wir nicht (einfacher Stack)
                # Oder wir könnten sie hier updaten, wenn sich Fenstergröße ändert
                pass
            
            # Platz für die nächste berechnen
            y_pos += notif.height() + spacing
            
    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow { background: #1e1e1e; }
            QMenuBar { background: #1e1e1e; color: #ccc; padding: 2px; border-bottom: 1px solid #333; }
            QMenuBar::item { padding: 4px 8px; }
            QMenuBar::item:selected { background: #333; }
            QMenu { background: #252526; color: #ccc; border: 1px solid #333; }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background: #0078d4; }
            QToolBar { 
                background: #1e1e1e; 
                border: none;
                border-bottom: 1px solid #333;
                padding: 2px;
                spacing: 2px;
            }
            QToolBar QToolButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 3px;
                color: #ccc;
                padding: 4px 8px;
                font-size: 11px;
            }
            QToolBar QToolButton:hover {
                background: #333;
                border-color: #444;
            }
            QToolBar QToolButton:pressed {
                background: #0078d4;
            }
            QSplitter::handle {
                background: #333;
            }
            QSplitter::handle:horizontal {
                width: 1px;
            }
            QSplitter::handle:vertical {
                height: 1px;
            }
            QSplitter::handle:hover {
                background: #0078d4;
            }
            QStatusBar { 
                background: #1e1e1e; 
                color: #888; 
                border-top: 1px solid #333;
            }
        """)
        
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
        central = QWidget()
        central.setStyleSheet("background-color: #1e1e1e;")
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # === HAUPTSPLITTER ===
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setStyleSheet("QSplitter { background: #1e1e1e; }")
        
        # === LINKE SEITE: Browser + Tools horizontal ===
        left_container = QWidget()  # <--- Hier heißt die Variable "left_container"
        left_layout = QHBoxLayout(left_container)
        left_layout.setContentsMargins(0,0,0,0)
        left_layout.setSpacing(0)

        # 1. Spalte: Browser (oben) + Tabs [Log | TNP] (unten)
        browser_log_splitter = QSplitter(Qt.Vertical)
        browser_log_splitter.setHandleWidth(1)

        self.browser = ProjectBrowser()
        self.browser.set_document(self.document)
        browser_log_splitter.addWidget(self.browser)

        # Bottom tabs: Log + TNP Stats
        from PySide6.QtWidgets import QTabWidget
        self.bottom_tabs = QTabWidget()
        self.bottom_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background: #1e1e1e;
            }
            QTabBar::tab {
                background: #252526;
                color: #999;
                border: none;
                padding: 6px 14px;
                font-size: 11px;
                font-family: 'Segoe UI';
            }
            QTabBar::tab:selected {
                color: #ddd;
                border-bottom: 2px solid #0078d4;
            }
            QTabBar::tab:hover {
                color: #ccc;
                background: #2d2d30;
            }
        """)

        self.log_panel = LogPanel()
        self.tnp_stats_panel = TNPStatsPanel()

        self.bottom_tabs.addTab(self.log_panel, "Log")
        self.bottom_tabs.addTab(self.tnp_stats_panel, "TNP")
        self.bottom_tabs.setCurrentIndex(0)  # Log default

        browser_log_splitter.addWidget(self.bottom_tabs)

        browser_log_splitter.setStretchFactor(0, 3)
        browser_log_splitter.setStretchFactor(1, 1)

        left_layout.addWidget(browser_log_splitter)
        
        # Tool-Panel Stack (3D oder 2D)
        self.tool_stack = QStackedWidget()
        self.tool_stack.setMinimumWidth(220)
        self.tool_stack.setStyleSheet("background-color: #1e1e1e;")
        
        self.transform_panel = TransformPanel(self)
        self.transform_panel.values_changed.connect(self._on_transform_val_change)
        self.transform_panel.confirmed.connect(self._on_transform_confirmed)
        self.transform_panel.cancelled.connect(self._on_transform_cancelled)

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
        
        left_layout.addWidget(self.tool_stack)
        
        # === FIX: left_container statt left_widget ===
        self.main_splitter.addWidget(left_container) 
        
        # === MITTE: Viewport / Sketch Editor ===
        self.center_stack = QStackedWidget()
        self.center_stack.setStyleSheet("background-color: #1e1e1e;")
        
        self.viewport_3d = PyVistaViewport()
        self.center_stack.addWidget(self.viewport_3d)
        
        self.sketch_editor = SketchEditor()
        self.center_stack.addWidget(self.sketch_editor)
        
        self.main_splitter.addWidget(self.center_stack)
        self.sketch_editor.viewport = self.viewport_3d
        
        # Splitter-Einstellungen
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([340, 1000])
        
        layout.addWidget(self.main_splitter)
        
        # === RECHTE SEITE: Properties (nur wenn nötig) ===
        self.right_stack = QStackedWidget()
        self.right_stack.setMinimumWidth(140)
        self.right_stack.setMaximumWidth(200)
        self.right_stack.setStyleSheet("background-color: #1e1e1e;")
        
        # 3D-Properties (Index 0)
        self.body_properties = BodyPropertiesPanel()
        self.right_stack.addWidget(self.body_properties)
        
        # 2D-Properties (Index 1)
        self.properties_panel = PropertiesPanel()
        self.right_stack.addWidget(self.properties_panel)
        
        self.right_stack.setVisible(False)
        layout.addWidget(self.right_stack)
        
        # Extrude Input Panel (immer sichtbar während Extrude-Modus)
        self.extrude_panel = ExtrudeInputPanel(self)
        self.extrude_panel.height_changed.connect(self._on_extrude_panel_height_changed)
        self.extrude_panel.confirmed.connect(self._on_extrude_confirmed)
        self.extrude_panel.cancelled.connect(self._on_extrude_cancelled)
        self.extrude_panel.bodies_visibility_toggled.connect(self._on_toggle_bodies_visibility)
        self.extrude_panel.operation_changed.connect(self._on_extrude_operation_changed)
        self.extrude_panel.to_face_requested.connect(self._on_to_face_requested)

        # Transform Panel
        self.transform_panel = TransformPanel(self)
        self.transform_panel.transform_confirmed.connect(self._on_transform_panel_confirmed)
        self.transform_panel.transform_cancelled.connect(self._on_transform_panel_cancelled)
        self.transform_panel.mode_changed.connect(self._on_transform_mode_changed)
        self.transform_panel.grid_size_changed.connect(self._on_grid_size_changed)
        self.transform_panel.hide()

        # Offset Plane Input Panel
        from gui.input_panels import OffsetPlaneInputPanel
        self.offset_plane_panel = OffsetPlaneInputPanel(self)
        self.offset_plane_panel.offset_changed.connect(self._on_offset_plane_value_changed)
        self.offset_plane_panel.confirmed.connect(self._on_offset_plane_confirmed)
        self.offset_plane_panel.cancelled.connect(self._on_offset_plane_cancelled)
        self._offset_plane_pending = False

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

        # Surface Texture Panel (Phase 7)
        self.texture_panel = SurfaceTexturePanel(self)
        self.texture_panel.texture_applied.connect(self._on_texture_applied)
        self.texture_panel.preview_requested.connect(self._on_texture_preview_requested)
        self.texture_panel.cancelled.connect(self._on_texture_cancelled)

        self._texture_mode = False
        self._texture_target_body = None
        self._pending_texture_mode = False  # Für Body-Selektion im Viewport

        # Sweep Panel (Phase 6)
        self.sweep_panel = SweepInputPanel(self)
        self.sweep_panel.confirmed.connect(self._on_sweep_confirmed)
        self.sweep_panel.cancelled.connect(self._on_sweep_cancelled)
        self.sweep_panel.sketch_path_requested.connect(self._on_sweep_sketch_path_requested)

        self._sweep_mode = False
        self._sweep_phase = None  # 'profile' or 'path'
        self._sweep_profile_data = None
        self._sweep_path_data = None

        # Loft Panel (Phase 6)
        self.loft_panel = LoftInputPanel(self)
        self.loft_panel.confirmed.connect(self._on_loft_confirmed)
        self.loft_panel.cancelled.connect(self._on_loft_cancelled)
        self.loft_panel.add_profile_requested.connect(self._on_loft_add_profile)

        self._loft_mode = False
        self._loft_profiles = []

        # Section View Panel (Schnittansicht wie Fusion 360)
        self.section_panel = SectionViewPanel(self)
        self.section_panel.section_enabled.connect(self._on_section_enabled)
        self.section_panel.section_disabled.connect(self._on_section_disabled)
        self.section_panel.section_position_changed.connect(self._on_section_position_changed)
        self.section_panel.section_plane_changed.connect(self._on_section_plane_changed)
        self.section_panel.section_invert_toggled.connect(self._on_section_invert_toggled)
        self.section_panel.hide()  # Initially hidden

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
        self._create_toolbar()
     
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_extrude_panel()
        self._position_transform_panel()
        self._reposition_notifications()
    
    def _position_extrude_panel(self):
        """Positioniert das Extrude-Panel am unteren Rand des Fensters, zentriert."""
        if hasattr(self, 'extrude_panel') and self.extrude_panel.isVisible():
            # Panel Größe holen (oder Standard annehmen)
            pw = self.extrude_panel.width() if self.extrude_panel.width() > 10 else 320
            ph = self.extrude_panel.height() if self.extrude_panel.height() > 10 else 150
            
            # Koordinaten berechnen (Relativ zum MainWindow)
            # x = Mitte - halbe Panelbreite
            x = (self.width() - pw) // 2
            # y = Unten - Panelhöhe - etwas Abstand (z.B. 40px)
            y = self.height() - ph - 40
            
            self.extrude_panel.move(x, y)
            self.extrude_panel.raise_() # Sicherstellen, dass es vorne ist

    def _position_transform_panel(self):
        """Positioniert das Transform-Panel am unteren Rand, zentriert."""
        if hasattr(self, 'transform_panel') and self.transform_panel.isVisible():
            pw = self.transform_panel.width() if self.transform_panel.width() > 10 else 520
            ph = self.transform_panel.height() if self.transform_panel.height() > 10 else 60

            x = (self.width() - pw) // 2
            y = self.height() - ph - 40

            self.transform_panel.move(x, y)
            self.transform_panel.raise_()

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
        
    def _on_transform_mode_changed(self, mode: str):
        """Handler wenn Transform-Modus geändert wird"""
        if hasattr(self.viewport_3d, 'set_transform_mode'):
            self.viewport_3d.set_transform_mode(mode)
        logger.info(f"Transform Mode: {mode.capitalize()}")

    def _on_grid_size_changed(self, grid_size: float):
        """Handler wenn Grid-Size geändert wird"""
        # Update TransformState
        if hasattr(self.viewport_3d, 'transform_state') and self.viewport_3d.transform_state:
            self.viewport_3d.transform_state.snap_grid_size = grid_size
            logger.info(f"Grid-Size aktualisiert: {grid_size}mm (Ctrl+Drag für Snap)")

    def _on_pivot_mode_changed(self, mode: str):
        """Handler wenn Pivot-Mode geändert wird"""
        # Update TransformState
        if hasattr(self.viewport_3d, 'transform_state') and self.viewport_3d.transform_state:
            self.viewport_3d.transform_state.pivot_mode = mode
            logger.info(f"Pivot-Mode aktualisiert: {mode}")

            # Info: Bei 'origin' oder 'cursor' müsste Gizmo neu positioniert werden
            # Für jetzt: Nur bei Rotate/Scale relevant

    def _get_selected_body_id(self) -> str:
        """Gibt ID des aktuell für Transform selektierten Bodies zurück"""
        if hasattr(self, '_selected_body_for_transform') and self._selected_body_for_transform:
            return self._selected_body_for_transform
        return None
        
    def _show_transform_ui(self, body_id: str, body_name: str):
        """Zeigt Transform-UI für einen Body"""
        self._selected_body_for_transform = body_id

        # NEU: Extrude-Panel KOMPLETT deaktivieren (Fix 2 - verstärkt)
        if hasattr(self, 'extrude_panel'):
            self.extrude_panel.setVisible(False)
            self.extrude_panel.hide()
            self.extrude_panel.lower()  # Z-Index runter

        # Transform-Panel zeigen
        self.transform_panel.reset_values()
        self.transform_panel.show()
        self.transform_panel.raise_()
        self._position_transform_panel()

        # Gizmo zeigen
        if hasattr(self.viewport_3d, 'show_transform_gizmo'):
            self.viewport_3d.show_transform_gizmo(body_id)

        logger.info(f"Transform: {body_name} | G=Move R=Rotate S=Scale | Tab=Eingabe | Esc=Abbrechen")

    def _hide_transform_ui(self):
        """Versteckt Transform-UI"""
        self._selected_body_for_transform = None
        self.transform_panel.hide()
        if hasattr(self.viewport_3d, 'hide_transform_gizmo'):
            self.viewport_3d.hide_transform_gizmo()

    def _on_transform_values_live_update(self, x: float, y: float, z: float):
        """Handler für Live-Update der Transform-Werte während Drag"""
        if hasattr(self, 'transform_panel') and self.transform_panel.isVisible():
            self.transform_panel.set_values(x, y, z)

    def _create_toolbar(self):
        """Minimale Toolbar - nur Modus-Umschaltung"""
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        self.addToolBar(tb)
        
        # Nur Sketch-Fertig Button (erscheint im Sketch-Modus)
        self.btn_finish_sketch = tb.addAction("✓ Fertig (Esc)")
        self.btn_finish_sketch.triggered.connect(self._finish_sketch)
        self.btn_finish_sketch.setToolTip("Sketch beenden und zurück zum 3D-Modus")
        self.btn_finish_sketch.setVisible(False)
        
        # Versteckte Buttons für Tastenkürzel
        self.btn_new_sketch = None  # Wird über Tool Panel gesteuert
        self.btn_extrude = None     # Wird über Tool Panel gesteuert

    def _create_menus(self):
        mb = self.menuBar()
        
        # Datei-Menü
        file_menu = mb.addMenu(tr("File"))
        file_menu.addAction(tr("New Project"), self._new_project, QKeySequence.New)
        file_menu.addAction(tr("Open..."), self._open_project, QKeySequence.Open)
        file_menu.addAction(tr("Save..."), self._save_project, QKeySequence.Save)
        file_menu.addAction(tr("Save As..."), self._save_project_as)
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
        # NEU: Verbinde mit UndoStack
        undo_action = self.undo_stack.createUndoAction(self, tr("Undo"))
        undo_action.setShortcut(QKeySequence.Undo)
        edit_menu.addAction(undo_action)

        redo_action = self.undo_stack.createRedoAction(self, tr("Redo"))
        redo_action.setShortcut(QKeySequence.Redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()
        edit_menu.addAction(tr("Parameters..."), self._show_parameters_dialog, "Ctrl+Shift+P")

        # Transform-Menü
        transform_menu = mb.addMenu(tr("Transform"))
        transform_menu.addAction(tr("Move (G)"), lambda: self._start_transform_mode("move"), "G")
        transform_menu.addAction(tr("Rotate (R)"), lambda: self._start_transform_mode("rotate"), "R")
        transform_menu.addAction(tr("Scale (S)"), lambda: self._start_transform_mode("scale"), "S")
        transform_menu.addSeparator()
        transform_menu.addAction(tr("Create Pattern..."), self._create_pattern)

        # Ansicht-Menü
        view_menu = mb.addMenu(tr("View"))
        view_menu.addAction(tr("Isometric"), lambda: self.viewport_3d.set_view('iso'))
        view_menu.addAction(tr("Top"), lambda: self.viewport_3d.set_view('top'))
        view_menu.addAction(tr("Front"), lambda: self.viewport_3d.set_view('front'))
        view_menu.addAction(tr("Right"), lambda: self.viewport_3d.set_view('right'))
        
        # Hilfe-Menü
        help_menu = mb.addMenu(tr("Help"))
        help_menu.addAction(tr("About MashCad"), self._show_about)

    def _connect_signals(self):
        # 2D Tool Panel
        self.tool_panel.tool_selected.connect(self._on_sketch_tool_selected)
        self.tool_panel.option_changed.connect(self._on_opt_change)
        
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
        
        # Viewport Signale
        self.viewport_3d.plane_clicked.connect(self._on_plane_selected)
        if hasattr(self.viewport_3d, 'custom_plane_clicked'):
            self.viewport_3d.custom_plane_clicked.connect(self._on_custom_plane_selected)
            
        self.viewport_3d.offset_plane_drag_changed.connect(self._on_offset_plane_drag)
        self.viewport_3d.extrude_requested.connect(self._on_extrusion_finished)
        self.viewport_3d.height_changed.connect(self._on_viewport_height_changed)
        
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

        # NEU: Point-to-Point Move (Fusion 360-Style)
        if hasattr(self.viewport_3d, 'point_to_point_move'):
            self.viewport_3d.point_to_point_move.connect(self._on_point_to_point_move)

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

    # --- DEBOUNCED UPDATE LOGIC ---
    def _trigger_viewport_update(self):
        """Startet den Timer für das Update (Debounce)"""
        self._update_timer.start() # Reset timer if called again
        
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
            from loguru import logger
            logger.error(f"Import Fehler: {e}")
            logger.error(f"Import fehlgeschlagen: {str(e)}")
    
    def _update_viewport_all_impl(self):
        """Das eigentliche Update, wird vom Timer aufgerufen"""
        if not HAS_PYVISTA: return

        # 1. Sketches updaten
        visible_sketches = self.browser.get_visible_sketches()
        self.viewport_3d.set_sketches(visible_sketches)
        
        # 2. Bodies updaten
        self.viewport_3d.clear_bodies()
        
        # FIX: Variablen definieren, die vorher fehlten!
        default_color = (0.7, 0.7, 0.7)
        colors = [(0.6, 0.6, 0.8), (0.8, 0.6, 0.6), (0.6, 0.8, 0.6)]
        
        visible_bodies = self.browser.get_visible_bodies()
        
        for i, (b, visible) in enumerate(visible_bodies):
            if not visible:
                continue

            try:
                # Fall A: Vtk Cache vorhanden (Schnell & Modern)
                col = getattr(b, 'color', default_color)
                # Falls color None ist (manchmal bei Init), Default nehmen
                if col is None: col = default_color
                
                if hasattr(b, 'vtk_mesh') and b.vtk_mesh is not None:
                    self.viewport_3d.add_body(
                        bid=b.id, 
                        name=b.name, 
                        mesh_obj=b.vtk_mesh, 
                        edge_mesh_obj=b.vtk_edges, 
                        color=col
                    )
                    
                # Fall B: Fallback auf alte Listen (Legacy)
                elif hasattr(b, '_mesh_vertices') and b._mesh_vertices:
                    # FIX: Benannte Argumente (keywords) nutzen!
                    self.viewport_3d.add_body(
                        bid=b.id, 
                        name=b.name, 
                        verts=b._mesh_vertices,     # <-- Keyword wichtig!
                        faces=b._mesh_triangles,    # <-- Keyword wichtig!
                        color=colors[i % 3]
                    )
            except Exception as e:
                logger.exception(f"Fehler beim Laden von Body {b.name}: {e}")

        # Finales Rendering erzwingen
        if hasattr(self.viewport_3d, 'plotter'):
            request_render(self.viewport_3d.plotter, immediate=True)
        self.viewport_3d.update()

    def _update_viewport_all(self):
        """Aktualisiert ALLES im Viewport (Legacy Wrapper)"""
        # Sketches
        self.viewport_3d.set_sketches(self.browser.get_visible_sketches())
        
        # Bodies - komplett neu laden
        self.viewport_3d.clear_bodies()
        default_col = (0.7, 0.1, 0.1)
        
        for i, (b, visible) in enumerate(self.browser.get_visible_bodies()):
            if visible and hasattr(b, '_mesh_vertices') and b._mesh_vertices:
                # FIX: Benannte Argumente verwenden!
                self.viewport_3d.add_body(
                    bid=b.id, 
                    name=b.name, 
                    verts=b._mesh_vertices,     # Explizit benennen
                    faces=b._mesh_triangles,    # Explizit benennen
                    color=default_col
                ) 
        
    def _on_3d_action(self, action: str):
        """Verarbeitet 3D-Tool-Aktionen"""
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

            'measure': self._start_measure_mode,
            'mass_props': lambda: self._show_not_implemented("Masseeigenschaften"),
            'geometry_check': self._geometry_check_dialog,
            'surface_analysis': self._surface_analysis_dialog,
            'pushpull': self._pushpull_dialog,
            'nsided_patch': self._nsided_patch_dialog,
            'mesh_repair': self._mesh_repair_dialog,
            'hollow': self._hollow_dialog,
            'wall_thickness': self._wall_thickness_dialog,
            'lattice': self._lattice_dialog,
            'pattern': lambda: self._show_not_implemented("Muster"),
            'convert_to_brep': self._convert_selected_body_to_brep,
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
            logger.warning("Kein Körper ausgewählt.")
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
                self._update_tnp_stats(None)
            else:
                self.statusBar().showMessage("Ready")
                self.body_properties.clear()
                self._hide_transform_ui()
                self._update_tnp_stats(None)
    
    def _start_transform_mode(self, mode):
        """
        Startet den Transform-Modus.
        Unterstützt Multi-Select aus Browser.
        """
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
            self._show_transform_ui(body.id, body.name)

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
        """Startet Point-to-Point Move Modus (Fusion 360-Style) - OHNE Body-Selektion möglich"""
        body = self._get_active_body()

        if not body:
            # Warte auf Body-Selektion (wie bei Move/Rotate/Scale)
            self._pending_transform_mode = "point_to_point"
            self.viewport_3d.setCursor(Qt.CrossCursor)
            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)

            logger.info("Point-to-Point Move: Wähle einen Body im Browser oder 3D-Ansicht")
            return

        # Body vorhanden -> Starte Point-to-Point Modus
        if hasattr(self.viewport_3d, 'start_point_to_point_mode'):
            self.viewport_3d.start_point_to_point_mode(body.id)
            logger.success(f"Point-to-Point Move für {body.name}: Wähle Start-Punkt, dann Ziel-Punkt")

    def _on_viewport_body_clicked(self, body_id: str):
        """
        Handler für Body-Klick im Viewport.
        Unterstützt:
        - Pending Transform Mode (Move/Rotate/Scale)
        - Pending Fillet/Chamfer Mode
        - Point-to-Point Move
        """
        # Prüfe auf Fillet/Chamfer Pending Mode (NEU)
        if hasattr(self, '_pending_fillet_mode') and self._pending_fillet_mode:
            self._on_body_clicked_for_fillet(body_id)
            return

        # Prüfe auf Shell Pending Mode (Phase 6)
        if getattr(self, '_pending_shell_mode', False):
            self._on_body_clicked_for_shell(body_id)
            return

        # Prüfe auf Texture Pending Mode (Phase 7)
        if getattr(self, '_pending_texture_mode', False):
            self._on_body_clicked_for_texture(body_id)
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
            return

        # Normaler Transform-Modus (Move/Rotate/Scale)
        self._transform_mode = mode
        self._active_transform_body = body

        # Transform-UI zeigen
        self._show_transform_ui(body.id, body.name)

        logger.success(f"{mode.capitalize()}: {body.name} - Ziehe am Gizmo oder Tab für Eingabe")

    def _on_point_to_point_move(self, body_id: str, start_point: tuple, end_point: tuple):
        """
        Handler für Point-to-Point Move (Fusion 360-Style)

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

        except Exception as e:
            logger.error(f"❌ Point-to-Point Move fehlgeschlagen: {e}")
            import traceback
            logger.error(traceback.format_exc())

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

        self._on_transform_cancelled() # Cleanup UI
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
        logger.info(f"📥 _on_body_transform_requested HANDLER CALLED")
        logger.info(f"   body_ids: {body_ids}")
        logger.info(f"   mode: {mode}")
        logger.info(f"   data: {data}")

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
        logger.info(f"📥 _on_body_copy_requested HANDLER CALLED")
        logger.info(f"   body_id: {body_id}")
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
            new_body = Body(name=f"{body.name}_copy")
            
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
            self.document.bodies.append(new_body)
            
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
        
    def _update_viewport_all(self):
        """Aktualisiert ALLES im Viewport"""
        # Sketches
        self.viewport_3d.set_sketches(self.browser.get_visible_sketches())
        
        # Bodies - komplett neu laden um gelöschte zu entfernen
        self.viewport_3d.clear_bodies()
        colors = [(0.6,0.6,0.8), (0.8,0.6,0.6), (0.6,0.8,0.6)]
        for i, (b, visible) in enumerate(self.browser.get_visible_bodies()):
            if visible and hasattr(b, '_mesh_vertices'):
                self.viewport_3d.add_body(b.id, b.name, b._mesh_vertices, b._mesh_triangles, colors[i%3])

    def _set_mode(self, mode):
        self.mode = mode
        if mode == "3d":
            # 3D-Modus
            self.tool_stack.setCurrentIndex(0)  # 3D-ToolPanel
            self.center_stack.setCurrentIndex(0)  # Viewport
            self.right_stack.setVisible(False)
            self.btn_finish_sketch.setVisible(False)
            #self._update_viewport_all()
        else:
            # Sketch-Modus
            self.tool_stack.setCurrentIndex(1)  # 2D-ToolPanel
            self.center_stack.setCurrentIndex(1)  # Sketch Editor
            self.right_stack.setCurrentIndex(1)  # 2D Properties
            self.right_stack.setVisible(True)
            self.btn_finish_sketch.setVisible(True)
            self.sketch_editor.setFocus()

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

    def _finish_sketch(self):
        """Beendet den Sketch-Modus und räumt auf."""
        # Body-Referenzen im SketchEditor löschen (Ghost Bodies entfernen)
        if hasattr(self.sketch_editor, 'set_reference_bodies'):
            self.sketch_editor.set_reference_bodies([], (0,0,1), (0,0,0))
            
        self.active_sketch = None
        self._set_mode("3d")
        
        # Browser Refresh triggert Visibility-Check
        self.browser.refresh()
        
        # WICHTIG: Explizit Update anstoßen für sauberen Statuswechsel
        self._trigger_viewport_update()

    def _hole_dialog(self):
        """Hole-Dialog: Bohrung in selektierten Body."""
        from gui.dialogs.hole_dialog import HoleDialog
        from modeling import HoleFeature
        from gui.commands.feature_commands import AddFeatureCommand

        body = self._get_active_body()
        if not body or not body._build123d_solid:
            logger.warning("Kein Body mit Geometrie ausgewaehlt.")
            return

        dialog = HoleDialog(self)
        if dialog.exec():
            # Position: Mittelpunkt der oberen Flaeche (vereinfacht)
            solid = body._build123d_solid
            try:
                bb = solid.bounding_box()
                center = ((bb.min.X + bb.max.X) / 2,
                          (bb.min.Y + bb.max.Y) / 2,
                          bb.max.Z)
                direction = (0, 0, -1)
            except Exception:
                center = (0, 0, 0)
                direction = (0, 0, -1)

            feature = HoleFeature(
                hole_type=dialog.hole_type,
                diameter=dialog.diameter,
                depth=dialog.depth,
                position=center,
                direction=direction,
                counterbore_diameter=dialog.counterbore_diameter,
                counterbore_depth=dialog.counterbore_depth,
                countersink_angle=dialog.countersink_angle,
            )

            cmd = AddFeatureCommand(body, feature, self)
            self.undo_stack.push(cmd)
            self.statusBar().showMessage(f"Hole D={dialog.diameter}mm created")
            logger.success(f"Hole {dialog.hole_type} D={dialog.diameter}mm erstellt")

    def _thread_dialog(self):
        """Thread-Dialog: Gewinde auf Body, oder Schraube/Mutter erzeugen."""
        from gui.dialogs.thread_dialog import ThreadDialog
        from modeling import ThreadFeature, Body
        from gui.commands.feature_commands import AddFeatureCommand

        dialog = ThreadDialog(parent=self)
        if not dialog.exec():
            return

        mode = dialog.result_mode  # "thread", "bolt", "nut"

        if mode == "thread":
            # Apply thread to existing body
            body = self._get_active_body()
            if not body or not body._build123d_solid:
                logger.warning("Kein Body mit Geometrie ausgewaehlt.")
                return
            solid = body._build123d_solid
            try:
                bb = solid.bounding_box()
                center = ((bb.min.X + bb.max.X) / 2,
                          (bb.min.Y + bb.max.Y) / 2,
                          bb.min.Z)
            except Exception:
                center = (0, 0, 0)

            feature = ThreadFeature(
                thread_type=dialog.thread_type_str,
                standard="M",
                diameter=dialog.diameter,
                pitch=dialog.pitch,
                depth=dialog.depth,
                position=center,
                direction=(0, 0, 1),
                tolerance_class=dialog.tolerance_class,
                tolerance_offset=dialog.tolerance_offset,
            )
            cmd = AddFeatureCommand(body, feature, self)
            self.undo_stack.push(cmd)
            self.statusBar().showMessage(f"Thread M{dialog.diameter}x{dialog.pitch} ({dialog.tolerance_class}) created")

        elif mode == "bolt":
            self._generate_bolt(dialog)

        elif mode == "nut":
            self._generate_nut(dialog)

    def _generate_bolt(self, dialog):
        """Generate a bolt as a new body (hex head + threaded shaft)."""
        from modeling import Body
        try:
            import build123d as bd

            dia = dialog.diameter + dialog.tolerance_offset
            length = dialog.depth
            hex_af = dialog.hex_af  # across flats
            head_h = dialog.head_height

            # Hex head
            hex_sketch = bd.RegularPolygon(radius=hex_af / 2 / 0.866025, side_count=6)
            head = bd.extrude(hex_sketch, head_h)

            # Shaft
            shaft = bd.Pos(0, 0, -length) * bd.extrude(bd.Circle(dia / 2), length)

            bolt_solid = bd.Compound([head, shaft])
            # Fuse
            bolt_solid = bd.fuse(head, shaft)

            body = Body(name=f"Bolt_M{dialog.diameter:.0f}x{dialog.pitch}")
            body._build123d_solid = bolt_solid
            body.invalidate_mesh()
            self.document.bodies.append(body)
            self._update_body_from_build123d(body, bolt_solid)
            self.browser.refresh()
            self.statusBar().showMessage(f"Bolt M{dialog.diameter:.0f}x{length:.0f} generated")
            logger.success(f"Bolt M{dialog.diameter:.0f}x{length:.0f} erzeugt")
        except Exception as e:
            logger.error(f"Bolt generation failed: {e}")

    def _generate_nut(self, dialog):
        """Generate a nut as a new body (hex body with threaded hole)."""
        from modeling import Body
        try:
            import build123d as bd

            dia = dialog.diameter
            hex_af = dialog.hex_af
            nut_h = dialog.nut_height

            # Hex outer body
            hex_sketch = bd.RegularPolygon(radius=hex_af / 2 / 0.866025, side_count=6)
            hex_body = bd.extrude(hex_sketch, nut_h)

            # Hole through center
            hole = bd.extrude(bd.Circle(dia / 2), nut_h)

            nut_solid = bd.cut(hex_body, hole)

            body = Body(name=f"Nut_M{dialog.diameter:.0f}")
            body._build123d_solid = nut_solid
            body.invalidate_mesh()
            self.document.bodies.append(body)
            self._update_body_from_build123d(body, nut_solid)
            self.browser.refresh()
            self.statusBar().showMessage(f"Nut M{dialog.diameter:.0f} generated")
            logger.success(f"Nut M{dialog.diameter:.0f} erzeugt")
        except Exception as e:
            logger.error(f"Nut generation failed: {e}")

    def _mesh_repair_dialog(self):
        """Open mesh repair dialog."""
        from gui.dialogs.mesh_repair_dialog import MeshRepairDialog

        body = self._get_active_body()
        if not body or not body._build123d_solid:
            logger.warning("Kein Body mit Geometrie ausgewaehlt.")
            return

        dlg = MeshRepairDialog(body, parent=self)
        if dlg.exec() and dlg.repaired_solid is not None:
            body._build123d_solid = dlg.repaired_solid
            body.invalidate_mesh()
            self.viewport.update_body(body)
            self._refresh_browser()
            logger.success("Geometry repair angewendet")

    def _nsided_patch_dialog(self):
        """Open N-Sided Patch dialog for surface filling."""
        from gui.dialogs.nsided_patch_dialog import NSidedPatchDialog

        body = self._get_active_body()
        if not body or not body._build123d_solid:
            logger.warning("Kein Body mit Geometrie ausgewaehlt.")
            return

        dlg = NSidedPatchDialog(body, self.viewport, parent=self)
        # Übergebe bereits selektierte Kanten aus dem Viewport
        selected_edges = []
        if hasattr(self.viewport, 'get_selected_edges'):
            selected_edges = self.viewport.get_selected_edges() or []
            if selected_edges:
                dlg.set_selected_edges(selected_edges)
        if not dlg.exec():
            return

        # Edge-Selektoren für Feature-Persistenz erstellen
        if not selected_edges:
            selected_edges = dlg.selected_edges
        if len(selected_edges) < 3:
            logger.warning("Zu wenige Kanten für N-Sided Patch")
            return

        import numpy as np
        edge_selectors = []
        for edge in selected_edges:
            try:
                ec = edge.center()
                edge_selectors.append((ec.X, ec.Y, ec.Z))
            except Exception:
                continue

        from modeling import NSidedPatchFeature
        feat = NSidedPatchFeature(
            edge_selectors=edge_selectors,
            degree=dlg.degree_spin.value(),
            tangent=dlg.tangent_check.isChecked(),
        )
        body.features.append(feat)
        body._rebuild()
        self.viewport.update_body(body)
        self._refresh_browser()
        logger.success(f"N-Sided Patch mit {len(edge_selectors)} Kanten angewendet")

    def _pushpull_dialog(self):
        """Open PushPull: Erst Face-Pick-Modus, dann Dialog mit Distanz."""
        body = self._get_active_body()
        if not body or not body._build123d_solid:
            logger.warning("Kein Body mit Geometrie ausgewaehlt.")
            return

        # Prüfe ob bereits eine Face gepickt wurde
        face_center = getattr(self.viewport, '_last_picked_face_center', None)
        face_normal = getattr(self.viewport, '_last_picked_face_normal', None)

        if face_center is not None and face_normal is not None:
            self._pushpull_with_face(body, face_center, face_normal)
        else:
            # Aktiviere Face-Pick-Modus mit PushPull-Callback
            logger.info("PushPull: Klicke eine Face im Viewport...")
            self._pushpull_body = body
            self.viewport.set_plane_select_mode(True)
            # Temporär umleiten
            try:
                self.viewport.custom_plane_clicked.disconnect(self._on_custom_plane_selected)
            except Exception:
                pass
            self.viewport.custom_plane_clicked.connect(self._on_pushpull_face_picked)

    def _on_pushpull_face_picked(self, origin, normal):
        """Callback wenn Face für PushPull gepickt wurde."""
        self.viewport.set_plane_select_mode(False)
        self.viewport.custom_plane_clicked.disconnect(self._on_pushpull_face_picked)
        self.viewport.custom_plane_clicked.connect(self._on_custom_plane_selected)

        body = getattr(self, '_pushpull_body', None)
        if body is None:
            return

        self._pushpull_with_face(body, origin, normal)

    def _pushpull_with_face(self, body, face_center, face_normal):
        """PushPull Dialog öffnen mit bekannter Face."""
        from gui.dialogs.pushpull_dialog import PushPullDialog
        from modeling import PushPullFeature

        dlg = PushPullDialog(face_center=face_center, face_normal=face_normal, parent=self)
        if not dlg.exec():
            return

        feat = PushPullFeature(
            face_selector=(tuple(face_center), tuple(face_normal)),
            distance=dlg.distance,
        )
        body.features.append(feat)
        body._rebuild()
        self.viewport.update_body(body)
        self._refresh_browser()
        logger.success(f"PushPull {dlg.distance:+.1f}mm angewendet")

    def _surface_analysis_dialog(self):
        """Open surface analysis dialog (curvature, draft angle, zebra)."""
        from gui.dialogs.surface_analysis_dialog import SurfaceAnalysisDialog

        body = self._get_active_body()
        if not body or not body._build123d_solid:
            logger.warning("Kein Body mit Geometrie ausgewaehlt.")
            return

        SurfaceAnalysisDialog(body, self.viewport, parent=self).exec()

    def _wall_thickness_dialog(self):
        """Open wall thickness analysis dialog."""
        from gui.dialogs.wall_thickness_dialog import WallThicknessDialog

        body = self._get_active_body()
        if not body or not body._build123d_solid:
            logger.warning("Kein Body mit Geometrie ausgewaehlt.")
            return

        WallThicknessDialog(body, parent=self).exec()

    def _lattice_dialog(self):
        """Open lattice structure dialog for selected body."""
        from gui.dialogs.lattice_dialog import LatticeDialog
        from modeling import LatticeFeature

        body = self._get_active_body()
        if not body or not body._build123d_solid:
            logger.warning("Kein Body mit Geometrie ausgewaehlt.")
            return

        dlg = LatticeDialog(parent=self)
        if not dlg.exec():
            return

        feat = LatticeFeature(
            cell_type=dlg.cell_type,
            cell_size=dlg.cell_size,
            beam_radius=dlg.beam_radius,
        )
        body.features.append(feat)
        body._rebuild()
        body.invalidate_mesh()
        self._update_body_from_build123d(body, body._build123d_solid)
        self._browser.refresh()
        logger.success(f"Lattice ({dlg.cell_type}) angewendet auf {body.name}")

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

        feat = HollowFeature(
            wall_thickness=dlg.wall_thickness,
            drain_hole=dlg.drain_hole,
            drain_diameter=dlg.drain_diameter,
            drain_position=drain_pos,
            drain_direction=dlg.drain_direction,
        )
        body.features.append(feat)
        body._rebuild()
        body.invalidate_mesh()
        self._update_body_from_build123d(body, body._build123d_solid)
        self._browser.refresh()
        logger.success(f"Hollow angewendet auf {body.name} (Wandstärke {dlg.wall_thickness}mm)")

    def _geometry_check_dialog(self):
        """Open geometry validation/healing dialog for selected body."""
        from gui.dialogs.geometry_check_dialog import GeometryCheckDialog

        body = self._get_active_body()
        if not body or not body._build123d_solid:
            logger.warning("Kein Body mit Geometrie ausgewaehlt.")
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
            import build123d as bd

            t = dialog.result_type
            if t == "box":
                solid = bd.Box(dialog.length, dialog.width, dialog.height)
                name = f"Box_{dialog.length:.0f}x{dialog.width:.0f}x{dialog.height:.0f}"
            elif t == "cylinder":
                solid = bd.Cylinder(dialog.radius, dialog.height)
                name = f"Cylinder_R{dialog.radius:.0f}_H{dialog.height:.0f}"
            elif t == "sphere":
                solid = bd.Sphere(dialog.radius)
                name = f"Sphere_R{dialog.radius:.0f}"
            elif t == "cone":
                solid = bd.Cone(dialog.bottom_radius, dialog.top_radius, dialog.height)
                name = f"Cone_R{dialog.bottom_radius:.0f}_H{dialog.height:.0f}"
            else:
                return

            body = Body(name=name)
            body._build123d_solid = solid
            body.invalidate_mesh()
            self.document.bodies.append(body)
            self._update_body_from_build123d(body, solid)
            self.browser.refresh()
            self.statusBar().showMessage(f"{name} created")
            logger.success(f"Primitive {name} erstellt")
        except Exception as e:
            logger.error(f"Primitive creation failed: {e}")

    def _draft_dialog(self):
        """Draft-Dialog: Entformungsschraege anwenden."""
        from gui.dialogs.draft_dialog import DraftDialog
        from modeling import DraftFeature
        from gui.commands.feature_commands import AddFeatureCommand

        body = self._get_active_body()
        if not body or not body._build123d_solid:
            logger.warning("Kein Body mit Geometrie ausgewaehlt.")
            return

        dialog = DraftDialog(self)
        if dialog.exec():
            feature = DraftFeature(
                draft_angle=dialog.draft_angle,
                pull_direction=dialog.pull_direction,
            )

            cmd = AddFeatureCommand(body, feature, self)
            self.undo_stack.push(cmd)
            self.statusBar().showMessage(f"Draft {dialog.draft_angle}° applied")
            logger.success(f"Draft {dialog.draft_angle}° erstellt")

    def _split_body_dialog(self):
        """Split-Dialog: Koerper teilen."""
        from gui.dialogs.split_dialog import SplitDialog
        from modeling import SplitFeature
        from gui.commands.feature_commands import AddFeatureCommand

        body = self._get_active_body()
        if not body or not body._build123d_solid:
            logger.warning("Kein Body mit Geometrie ausgewaehlt.")
            return

        dialog = SplitDialog(self)
        if dialog.exec():
            feature = SplitFeature(
                plane_origin=dialog.plane_origin,
                plane_normal=dialog.plane_normal,
                keep_side=dialog.keep_side,
            )

            cmd = AddFeatureCommand(body, feature, self)
            self.undo_stack.push(cmd)
            self.statusBar().showMessage(f"Split ({dialog.keep_side}) applied")
            logger.success(f"Split Body ({dialog.keep_side}) erstellt")

    def _revolve_dialog(self):
        """Revolve-Dialog: Sketch um Achse rotieren."""
        from gui.dialogs.revolve_dialog import RevolveDialog
        from modeling import RevolveFeature
        from gui.commands.feature_commands import AddFeatureCommand

        # Verfuegbare Sketches sammeln
        sketches = []
        if self.document:
            for body in self.document.bodies:
                for f in body.features:
                    if hasattr(f, 'sketch') and f.sketch:
                        sketches.append(f.sketch)
            # Auch freie Sketches
            if hasattr(self.document, 'sketches'):
                sketches.extend(self.document.sketches)

        if not sketches:
            logger.warning("Keine Sketches vorhanden. Erstelle zuerst einen Sketch.")
            return

        dialog = RevolveDialog(sketches, self)
        if dialog.exec():
            # Aktiven Body holen oder neuen erstellen
            body = self._get_active_body()
            if not body:
                from modeling import Body
                body = Body(name="Body")
                self.document.bodies.append(body)

            feature = RevolveFeature(
                sketch=dialog.sketch,
                angle=dialog.angle,
                axis=dialog.axis,
                operation=dialog.operation,
            )

            cmd = AddFeatureCommand(body, feature, self)
            self.undo_stack.push(cmd)
            logger.success(f"Revolve erstellt: {dialog.angle}° um {dialog.axis}")

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
        # Bodies wieder einblenden falls versteckt
        self.viewport_3d.set_all_bodies_visible(True)
        if hasattr(self.viewport_3d, 'detector'):
            self.viewport_3d.detector.clear()
        self.viewport_3d.selected_face_ids.clear()
        self.viewport_3d.hover_face_id = -1
        self.viewport_3d._draw_selectable_faces_from_detector()
        logger.info(tr("Extrude abgebrochen"), 2000)
    
    def _on_toggle_bodies_visibility(self, hide: bool):
        """Toggle alle Bodies sichtbar/unsichtbar im Extrude-Modus"""
        self.viewport_3d.set_all_bodies_visible(not hide)
        
        # NEU: Detector aktualisieren wenn Sichtbarkeit geändert wird
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

        for sketch, visible in visible_sketches:
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
        extrude_mode = getattr(self.viewport_3d, 'extrude_mode', False)
        for body in self.document.bodies:
            if self.viewport_3d.is_body_visible(body.id):
                mesh = self.viewport_3d.get_body_mesh(body.id)
                if mesh:
                    self.viewport_3d.detector.process_body_mesh(body.id, mesh, extrude_mode=extrude_mode)

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
            selection_data = []
            for fid in self.viewport_3d.selected_face_ids:
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
                    target_sketch = next((s for s in self.document.sketches if s.id == source_id), None)
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
                                parent_body = next((b for b in self.document.bodies if b.id == target_sketch.parent_body_id), None)
                                if parent_body:
                                    target_bodies = [parent_body]
                                    logger.info(f"🎯 Join: Nutze Parent-Body '{parent_body.name}'")

                        # Für Cut/Intersect: Finde Body der mit Extrusion-Volumen überlappt
                        if not target_bodies:
                            priority_body = self._find_body_closest_to_sketch(target_sketch, selection_data)

                            if priority_body:
                                target_bodies = [priority_body]
                                logger.info(f"🎯 Auto-Target: Nutze nächsten Body '{priority_body.name}' (Proximity)")
                            elif self.document.bodies and operation != "New Body":
                                # Fallback: Wenn wir wirklich nichts finden (z.B. Skizze weit im Raum),
                                # nehmen wir bei Join/Cut lieber den letzten Körper als gar keinen oder alle.
                                # Das ist sicherer als "Alle schneiden".
                                target_bodies = [self.document.bodies[-1]]
                                logger.info(f"⚠️ Targeting Fallback: Nutze '{target_bodies[0].name}'")

                    if not target_bodies and operation == "Cut":
                         logger.warning("Kein Ziel-Körper gefunden. Bitte Körper im Browser auswählen.")
                         return

                    # --- FEATURE ANWENDEN ---
                    success_count = 0
                    from modeling import ExtrudeFeature
                    from gui.commands.feature_commands import AddFeatureCommand

                    for body in target_bodies:
                        feature = ExtrudeFeature(
                            sketch=target_sketch,
                            distance=height,
                            operation=operation,
                            precalculated_polys=polys
                        )

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
                success = self._extrude_body_face_build123d({
                    'body_id': first_face.owner_id,       
                    'center_3d': first_face.plane_origin, 
                    'normal': first_face.plane_normal
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
        self.viewport_3d.set_all_bodies_visible(True)
        
        if hasattr(self.viewport_3d, 'detector'):
            self.viewport_3d.detector.clear()
        self.viewport_3d.selected_face_ids.clear()
        self.viewport_3d.hover_face_id = -1
        self.viewport_3d._draw_selectable_faces_from_detector()    
            
        if success:
            self.browser.refresh()
            # TNP Statistiken aktualisieren
            self._update_tnp_stats()
            if msg: logger.success(msg)


    def _extract_face_as_polygon(self, face):
        """
        Extrahiert die Flächen-Kontur als Shapely Polygon.

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
            import numpy as np

            # 1. Hole Face-Surface für Koordinatentransformation
            surface = BRep_Tool.Surface_s(face.wrapped)

            # 2. Hole Face-Normale und Origin
            # Berechne Normale am Zentrum der Fläche
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

            # 3. Extrahiere Outer Wire Punkte
            from OCP.TopoDS import TopoDS

            wire_exp = TopExp_Explorer(face.wrapped, TopAbs_WIRE)
            if not wire_exp.More():
                logger.warning("Face hat keinen Wire")
                return None, None, None, None, None

            # ✅ FIX: Cast TopoDS_Shape -> TopoDS_Wire
            outer_wire_shape = wire_exp.Current()
            outer_wire = TopoDS.Wire_s(outer_wire_shape)

            # 4. Sammle alle Punkte entlang des Wire
            from OCP.BRepAdaptor import BRepAdaptor_Curve
            from OCP.GCPnts import GCPnts_UniformAbscissa

            points_3d = []
            edge_exp = BRepTools_WireExplorer(outer_wire)

            while edge_exp.More():
                edge = edge_exp.Current()

                try:
                    # BRepAdaptor_Curve ist einfacher zu verwenden als BRep_Tool.Curve_s
                    adaptor = BRepAdaptor_Curve(edge)
                    first = adaptor.FirstParameter()
                    last = adaptor.LastParameter()

                    # Sample Punkte entlang der Kante
                    n_samples = 10
                    for i in range(n_samples):
                        t = first + (last - first) * i / n_samples
                        pt = adaptor.Value(t)
                        points_3d.append((pt.X(), pt.Y(), pt.Z()))

                except Exception as edge_err:
                    logger.debug(f"Edge-Sampling fehlgeschlagen: {edge_err}")

                edge_exp.Next()

            if len(points_3d) < 3:
                logger.warning(f"Zu wenige Punkte extrahiert: {len(points_3d)}")
                return None, None, None, None, None

            # 5. Transformiere 3D-Punkte in 2D-Koordinaten (lokale Face-Ebene)
            origin = np.array(plane_origin)
            normal = np.array(plane_normal)
            x_dir = np.array(plane_x_dir)

            # Normalisieren
            normal = normal / np.linalg.norm(normal)
            x_dir = x_dir / np.linalg.norm(x_dir)

            # Y-Richtung als Kreuzprodukt
            y_dir = np.cross(normal, x_dir)
            y_dir = y_dir / np.linalg.norm(y_dir)

            # Projiziere Punkte auf 2D
            points_2d = []
            for p3d in points_3d:
                p = np.array(p3d) - origin
                x = np.dot(p, x_dir)
                y = np.dot(p, y_dir)
                points_2d.append((x, y))

            # 6. Erstelle Shapely Polygon
            try:
                polygon = ShapelyPolygon(points_2d)
                if not polygon.is_valid:
                    polygon = polygon.buffer(0)  # Reparatur

                # ✅ FIX: y_dir als Tuple speichern für korrekte 2D→3D Transformation beim Rebuild
                plane_y_dir = tuple(y_dir.tolist())

                # DEBUG: Zeige Koordinatensystem bei Extraktion
                logger.debug(f"  Koordinatensystem bei Extraktion:")
                logger.debug(f"    x_dir={plane_x_dir}")
                logger.debug(f"    y_dir={plane_y_dir}")
                logger.debug(f"    normal={plane_normal}")

                logger.info(f"✅ Face-Polygon extrahiert: {len(points_2d)} Punkte, Area={polygon.area:.1f}")
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
            from OCP.gp import gp_Pnt
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE
            from OCP.TopoDS import TopoDS

            # --- SCHRITT A: Face finden (Robuste Logik wie zuvor) ---
            b3d_obj = source_body._build123d_solid
            candidate_faces = b3d_obj.faces()

            if not candidate_faces:
                explorer = TopExp_Explorer(b3d_obj.wrapped, TopAbs_FACE)
                candidate_faces = []
                while explorer.More():
                    from build123d import Face
                    candidate_faces.append(Face(TopoDS.Face_s(explorer.Current())))
                    explorer.Next()

            mesh_center = Vector(face_data['center_3d'])
            ocp_pt_vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(mesh_center.X, mesh_center.Y, mesh_center.Z)).Vertex()

            best_face = None
            best_dist = float('inf')

            logger.debug(f"Face-Suche: mesh_center=({mesh_center.X:.2f}, {mesh_center.Y:.2f}, {mesh_center.Z:.2f}), {len(candidate_faces)} Kandidaten")

            for f in candidate_faces:
                try:
                    extrema = BRepExtrema_DistShapeShape(ocp_pt_vertex, f.wrapped)
                    if extrema.IsDone():
                        dist = extrema.Value()
                        if dist < best_dist:
                            best_dist = dist
                            best_face = f
                except Exception as ex:
                    logger.debug(f"Face-Distanz-Fehler: {ex}")

            # ✅ Erhöhter Schwellenwert: 10.0 statt 2.0
            # Bei größeren Körpern kann die Distanz zwischen Mesh-Zentrum und BREP-Face größer sein
            FACE_DISTANCE_THRESHOLD = 10.0

            if best_face is None:
                logger.error(f"FEHLER: Keine Fläche gefunden! ({len(candidate_faces)} Kandidaten geprüft)")
                return False

            if best_dist > FACE_DISTANCE_THRESHOLD:
                logger.error(f"FEHLER: Nächste Fläche zu weit entfernt (dist={best_dist:.2f} > {FACE_DISTANCE_THRESHOLD})")
                logger.debug(f"  mesh_center: ({mesh_center.X:.2f}, {mesh_center.Y:.2f}, {mesh_center.Z:.2f})")
                return False

            logger.info(f"Face gefunden: dist={best_dist:.3f}")

            # --- SCHRITT B: Face-Kontur als Polygon extrahieren ---
            # KEIN FALLBACK! Push/Pull MUSS parametrisch sein.
            polygon, plane_origin, plane_normal, plane_x_dir, plane_y_dir = self._extract_face_as_polygon(best_face)

            if polygon is None:
                logger.error("FEHLER: Konnte Face-Polygon nicht extrahieren. Push/Pull abgebrochen.")
                return False

            # Extrusions-Werkzeug erstellen
            new_geo = extrude(best_face, amount=height)

            # --- SCHRITT C: Multi-Body Operationen ---

            # 1. Ziele definieren
            targets = []

            if operation == "New Body":
                # Neuer Body mit parametrischem Feature
                new_body = self.document.new_body()

                from modeling import ExtrudeFeature
                feat = ExtrudeFeature(
                    sketch=None,
                    distance=height,
                    operation="New Body",
                    name="Push/Pull (New Body)",
                    precalculated_polys=[polygon],
                    plane_origin=plane_origin,
                    plane_normal=plane_normal,
                    plane_x_dir=plane_x_dir,
                    plane_y_dir=plane_y_dir  # ✅ FIX: Y-Richtung speichern
                )
                new_body.features.append(feat)
                new_body._build123d_solid = new_geo
                self._update_body_from_build123d(new_body, new_geo)
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

                    if operation == "Cut":
                        new_solid = old_solid - new_geo
                    elif operation == "Join":
                        new_solid = old_solid + new_geo
                    elif operation == "Intersect":
                        new_solid = old_solid & new_geo

                    # Nur speichern, wenn das Ergebnis valide ist und nicht leer
                    if new_solid is not None and not new_solid.is_null():
                        # Parametrisches Feature erstellen
                        from modeling import ExtrudeFeature
                        feat = ExtrudeFeature(
                            sketch=None,
                            distance=height,
                            operation=operation,
                            name=f"Push/Pull ({operation})",
                            precalculated_polys=[polygon],
                            plane_origin=plane_origin,
                            plane_normal=plane_normal,
                            plane_x_dir=plane_x_dir,
                            plane_y_dir=plane_y_dir  # ✅ FIX: Y-Richtung speichern
                        )
                        target.features.append(feat)

                        target._build123d_solid = new_solid
                        self._update_body_from_build123d(target, new_solid)
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
            # 1. Solid erstellen
            solid, verts, faces = self.sketch_editor.get_build123d_part(height, operation)
            
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
            except:
                pass
                
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

    def _update_body_mesh(self, body, mesh_override=None):
        """Lädt die Mesh-Daten aus dem Body-Objekt in den Viewport"""
        logger.debug(f"_update_body_mesh aufgerufen für '{body.name}' (id={body.id})")
        
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
                     color=getattr(body, 'color', None)
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
                 color=default_col
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
                 color=colors[col_idx]
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

            # Bestätigung für Extrude / Offset Plane
            if k in (Qt.Key_Return, Qt.Key_Enter):
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
                # Priorität 0.5: Offset Plane abbrechen
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
                if k == Qt.Key_S:
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

    def _on_rollback_changed(self, body, value):
        """Handle rollback slider change - rebuild body up to given feature index."""
        from modeling.cad_tessellator import CADTessellator
        n = len(body.features)
        rebuild_up_to = value if value < n else None
        body.rollback_index = rebuild_up_to

        CADTessellator.notify_body_changed()
        body._rebuild(rebuild_up_to=rebuild_up_to)
        self._update_body_from_build123d(body, body._build123d_solid)
        self.browser.refresh()
        self.browser.show_rollback_bar(body)
        self.statusBar().showMessage(f"Rollback: {value}/{n} Features")

    def _new_project(self):
        self.document = Document("Projekt1")
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
                self._current_project_path = path

                # UI aktualisieren
                self.browser.set_document(doc)
                self.browser.refresh()

                # Viewport aktualisieren
                self.viewport_3d.clear()
                for body in doc.bodies:
                    if body._build123d_solid or body.vtk_mesh:
                        self.viewport_3d.add_body(body.id, body)

                self.setWindowTitle(f"MashCAD - {os.path.basename(path)}")

                # TNP Stats aktualisieren
                self._update_tnp_stats()

                logger.success(f"Projekt geladen: {path}")
            else:
                QMessageBox.critical(self, "Fehler", "Projekt konnte nicht geladen werden.")
        except Exception as e:
            logger.error(f"Fehler beim Laden: {e}")
            QMessageBox.critical(self, "Fehler", f"Laden fehlgeschlagen:\n{e}")

    def _export_stl(self):
        """STL Export mit Quality-Dialog und Surface Texture Support."""
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
                        b3d_mesh = body._build123d_solid.tessellate(tolerance=linear_defl, angular_tolerance=angular_tol)
                        verts = [(v.X, v.Y, v.Z) for v in b3d_mesh[0]]
                        faces = []
                        for t in b3d_mesh[1]: faces.extend([3] + list(t))
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
                self.viewport_3d.plotter.render()
        except Exception as e:
            logger.debug(f"Camera focus Fehler (ignoriert): {e}")

    def _create_pattern(self):
        """
        Erstellt Linear oder Circular Pattern (Fusion 360-Style).
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
                self.document.bodies.append(new_body)
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

    # ── Measure Tool ──────────────────────────────────────────

    def _start_measure_mode(self):
        """Startet den Mess-Modus: 2 Punkte anklicken -> Distanz anzeigen"""
        self._measure_points = []
        self._measure_active = True
        self.viewport_3d.measure_mode = True
        self.statusBar().showMessage("Measure: Click first point on model")
        logger.info("Measure mode: Click 2 points to measure distance. Esc to cancel.")

        # Alten Measure-Actors entfernen
        self._clear_measure_actors()

    def _on_measure_point_picked(self, point):
        """Wird aufgerufen wenn ein Punkt im Measure-Modus gepickt wurde"""
        if not getattr(self, '_measure_active', False):
            return
        self._measure_points.append(point)

        # Marker zeichnen
        import pyvista as pv
        sphere = pv.Sphere(radius=0.3, center=point)
        actor_name = f"_measure_pt_{len(self._measure_points)}"
        self.viewport_3d.plotter.add_mesh(
            sphere, color="#00ff88", name=actor_name,
            reset_camera=False, pickable=False
        )

        if len(self._measure_points) == 1:
            self.statusBar().showMessage("Measure: Click second point")
        elif len(self._measure_points) == 2:
            self._show_measure_result()

    def _show_measure_result(self):
        """Berechnet und zeigt die Distanz zwischen 2 Punkten"""
        import numpy as np
        import pyvista as pv

        p1 = np.array(self._measure_points[0])
        p2 = np.array(self._measure_points[1])
        dist = np.linalg.norm(p2 - p1)

        # Linie zeichnen
        line = pv.Line(p1, p2)
        self.viewport_3d.plotter.add_mesh(
            line, color="#ffaa00", line_width=3,
            name="_measure_line", reset_camera=False, pickable=False
        )

        # Label am Mittelpunkt
        mid = (p1 + p2) / 2
        label_text = f"{dist:.2f} mm"
        self.viewport_3d.plotter.add_point_labels(
            [mid], [label_text],
            name="_measure_label",
            font_size=16, text_color="#ffaa00",
            point_color="#ffaa00", point_size=0,
            shape=None, fill_shape=False,
            reset_camera=False, pickable=False
        )

        self.statusBar().showMessage(f"Distance: {dist:.2f} mm")
        logger.success(f"Measure: {dist:.2f} mm  (P1={p1}, P2={p2})")

        # Modus beenden, Geometrie bleibt sichtbar bis naechstes Measure oder Esc
        self._measure_active = False
        self.viewport_3d.measure_mode = False

    def _clear_measure_actors(self):
        """Entfernt alle Mess-Visualisierungen"""
        for name in ["_measure_pt_1", "_measure_pt_2", "_measure_line", "_measure_label"]:
            try:
                self.viewport_3d.plotter.remove_actor(name)
            except Exception:
                pass

    def _cancel_measure_mode(self):
        """Bricht den Mess-Modus ab"""
        self._measure_active = False
        self._measure_points = []
        self.viewport_3d.measure_mode = False
        self._clear_measure_actors()
        self.statusBar().showMessage("Ready")
        logger.info("Measure cancelled")

    # ── End Measure Tool ──────────────────────────────────────

    def _show_parameters_dialog(self):
        """Öffnet den Parameter-Dialog (Fusion 360-Style)."""
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

    def _show_about(self):
        """Über-Dialog"""
        QMessageBox.about(self, tr("Über MashCad"),
            f"<h2>MashCad</h2>"
            f"<p>Version 2.6</p>"
            f"<p>Schlankes parametrisches CAD für 3D-Druck</p>"
            f"<p>© 2024-2025</p>"
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

        # Sweep Path Phase (Phase 6)
        if getattr(self, '_sweep_mode', False) and getattr(self, '_sweep_phase', None) == 'path':
            if count > 0:
                edges = self.viewport_3d.get_selected_edges()
                self._on_edge_selected_for_sweep(edges)

    def _on_fillet_confirmed(self):
        """
        Wendet Fillet/Chamfer mit robuster Fallback-Strategie an.
        Verwendet edge_operations.py für intelligente Fehlerbehandlung.
        """
        from modeling.edge_operations import apply_robust_fillet, apply_robust_chamfer
        from modeling.cad_tessellator import CADTessellator

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

        # Robuste Operation anwenden
        logger.info(f"Wende {mode} auf {len(edges)} Kanten an (r={radius})...")

        try:
            if mode == "chamfer":
                result = apply_robust_chamfer(body, edges, radius)
            else:
                result = apply_robust_fillet(body, edges, radius)

            if result.success:
                # Cache leeren und Body aktualisieren
                CADTessellator.notify_body_changed()

                body._build123d_solid = result.solid
                if hasattr(result.solid, 'wrapped'):
                    body.shape = result.solid.wrapped

                # Mesh aktualisieren
                body._update_mesh_from_solid(result.solid)

                # Fehlgeschlagene Kanten markieren
                for edge_idx in result.failed_edge_indices:
                    self.viewport_3d.mark_edge_as_failed(edge_idx)

                # Feature zur History hinzufügen
                # Legacy Point-Selectors (backward-compat)
                selectors = self.viewport_3d.get_edge_selectors()

                # TNP Phase 1: GeometricSelectors erstellen
                from modeling.geometric_selector import create_geometric_selectors_from_edges
                selected_edges = self.viewport_3d.get_selected_edges()
                geometric_selectors = create_geometric_selectors_from_edges(selected_edges)
                logger.debug(f"🎯 TNP Phase 1: {len(geometric_selectors)} GeometricSelectors erstellt")

                # ✅ TNP Phase 2: OCP Edge Shapes speichern
                ocp_edge_shapes = []
                for edge in selected_edges:
                    if hasattr(edge, 'wrapped'):
                        ocp_edge_shapes.append(edge.wrapped)
                    else:
                        logger.warning("Edge hat kein 'wrapped' Attribut - Phase 2 TNP nicht möglich")

                # ✅ TNP Phase 2: Finde vorheriges Boolean-Feature (für History-Lookup)
                depends_on_feature_id = None
                from modeling import ExtrudeFeature
                for feat in reversed(body.features):
                    if isinstance(feat, ExtrudeFeature) and feat.operation in ["Join", "Cut", "Intersect"]:
                        depends_on_feature_id = feat.id
                        logger.debug(f"🎯 TNP Phase 2: Fillet/Chamfer hängt von Feature {feat.name} ab")
                        break

                if mode == "chamfer":
                    feat = ChamferFeature(
                        distance=radius,
                        edge_selectors=selectors,
                        geometric_selectors=geometric_selectors,
                        ocp_edge_shapes=ocp_edge_shapes,  # ✅ Phase 2 TNP
                        depends_on_feature_id=depends_on_feature_id  # ✅ Phase 2 TNP
                    )
                else:
                    feat = FilletFeature(
                        radius=radius,
                        edge_selectors=selectors,
                        geometric_selectors=geometric_selectors,
                        ocp_edge_shapes=ocp_edge_shapes,  # ✅ Phase 2 TNP
                        depends_on_feature_id=depends_on_feature_id  # ✅ Phase 2 TNP
                    )

                logger.debug(f"✅ TNP Phase 2: Feature mit {len(ocp_edge_shapes)} OCP Edges erstellt")
                body.features.append(feat)

                # Visualisierung aktualisieren
                self._update_body_from_build123d(body, body._build123d_solid)

                # Aufräumen
                self.viewport_3d.stop_edge_selection_mode()
                self.fillet_panel.hide()
                self.browser.refresh()

                # TNP Statistiken aktualisieren
                self._update_tnp_stats(body)

                logger.success(f"{mode.capitalize()}: {result.message}")

            else:
                QMessageBox.warning(
                    self, "Fehler",
                    f"{mode.capitalize()} fehlgeschlagen:\n{result.message}"
                )
                logger.error(f"{mode.capitalize()} fehlgeschlagen: {result.message}")

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
        self._pending_shell_mode = False

        # WICHTIG: Face-Detection aktivieren damit Flächen wählbar sind
        # (Analog zu Extrude-Mode, aber für Body-Flächen)
        self.viewport_3d.set_extrude_mode(True)  # Aktiviert Face-Picking
        self._update_detector()  # Detector mit Body-Faces füllen

        # Panel anzeigen
        self.shell_panel.clear_opening_faces()
        self.shell_panel.show_at(self.viewport_3d)

        logger.info(f"Shell: Wähle Öffnungs-Flächen von '{body.name}' (Klick = hinzufügen, ESC = abbrechen)")

    def _on_face_selected_for_shell(self, face_id):
        """
        Callback wenn eine Fläche für Shell ausgewählt wird.
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

        # Face-Center als Selektor speichern (für TNP)
        # Für Body-Faces nutzen wir plane_origin als Fallback wenn kein Shapely-Polygon
        face_center = None

        if face.shapely_poly:
            centroid = face.shapely_poly.centroid
            # Transformiere 2D zu 3D
            plane_x = np.array(face.plane_x)
            plane_y = np.array(face.plane_y)
            origin = np.array(face.plane_origin)
            face_center = origin + centroid.x * plane_x + centroid.y * plane_y
        elif hasattr(face, 'plane_origin') and face.plane_origin is not None:
            # Fallback: Nutze plane_origin direkt (für Body-Faces)
            face_center = np.array(face.plane_origin)
            logger.debug(f"Shell: Nutze plane_origin als Face-Center: {face_center}")
        else:
            logger.warning(f"Shell: Face hat weder shapely_poly noch plane_origin - kann nicht verwendet werden")
            return

        face_selector = (tuple(face_center), tuple(face.plane_normal))

        # Prüfen ob schon ausgewählt (Toggle-Verhalten)
        already_selected = False
        for i, (fc, fn) in enumerate(self._shell_opening_faces):
            if np.linalg.norm(np.array(fc) - face_center) < 0.1:
                # Bereits ausgewählt → entfernen
                self._shell_opening_faces.pop(i)
                already_selected = True
                logger.info(f"Shell: Fläche entfernt ({len(self._shell_opening_faces)} Öffnungen)")
                break

        if not already_selected:
            self._shell_opening_faces.append(face_selector)
            self.shell_panel.add_opening_face(face_selector)
            logger.info(f"Shell: Fläche hinzugefügt ({len(self._shell_opening_faces)} Öffnungen)")

        # Panel aktualisieren
        self.shell_panel.update_face_count(len(self._shell_opening_faces))

    def _on_shell_confirmed(self):
        """
        Wendet Shell auf den Body an.
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
            # Shell Feature erstellen
            shell_feature = ShellFeature(
                thickness=thickness,
                opening_face_selectors=self._shell_opening_faces.copy()
            )

            # Feature zur History hinzufügen
            body.features.append(shell_feature)

            # Body neu berechnen
            CADTessellator.notify_body_changed()
            body._rebuild()

            # Visualisierung aktualisieren
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

        if not self._texture_target_body:
            logger.error("Kein Target-Body für Textur")
            return

        body = self._texture_target_body

        # Selektierte Faces vom Viewport holen
        selected_faces = self.viewport_3d.get_texture_selected_faces()

        if not selected_faces:
            logger.warning("Keine Faces selektiert für Textur")
            return

        # Face-Selectors erstellen (mit cell_ids für Viewport-Overlay)
        face_selectors = []
        viewport_face_data = []  # Für visuelles Feedback im Viewport
        for face_data in selected_faces:
            selector = {
                'center': face_data.get('center', (0, 0, 0)),
                'normal': face_data.get('normal', (0, 0, 1)),
                'area': face_data.get('area', 1.0),
                'surface_type': face_data.get('surface_type', 'plane'),
                'cell_ids': face_data.get('cell_ids', [])  # NEU: Für Preview!
            }
            face_selectors.append(selector)
            # Speichere cell_ids für Viewport-Overlay
            viewport_face_data.append({
                'cell_ids': face_data.get('cell_ids', []),
                'normal': face_data.get('normal', (0, 0, 1)),
                'center': face_data.get('center', (0, 0, 0)),
                # texture_feature wird unten gesetzt!
            })

        # SurfaceTextureFeature erstellen
        feature = SurfaceTextureFeature(
            name=f"Texture: {config['texture_type'].capitalize()}",
            texture_type=config['texture_type'],
            face_selectors=face_selectors,
            scale=config.get('scale', 1.0),
            depth=config.get('depth', 0.5),
            rotation=config.get('rotation', 0.0),
            invert=config.get('invert', False),
            type_params=config.get('type_params', {}),
            export_subdivisions=config.get('export_subdivisions', 4)
        )

        # Feature zum Body hinzufügen
        body.features.append(feature)

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
        # WICHTIG: Transform-Gizmo ausblenden, damit Klicks nicht abgefangen werden
        if hasattr(self.viewport_3d, 'hide_transform_gizmo'):
            self.viewport_3d.hide_transform_gizmo()

        self._sweep_mode = True
        self._sweep_phase = 'profile'
        self._sweep_profile_data = None
        self._sweep_path_data = None

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

        # Profil-Daten speichern
        profile_data = {
            'type': face.domain_type,
            'face_id': face_id,
            'plane_origin': face.plane_origin,
            'plane_normal': face.plane_normal,
            'plane_x': face.plane_x,
            'plane_y': face.plane_y,
            'shapely_poly': face.shapely_poly
        }

        self._sweep_profile_data = profile_data
        self.sweep_panel.set_profile(profile_data)

        # Zur Pfad-Phase wechseln
        self._sweep_phase = 'path'
        logger.info("Sweep: Profil ausgewählt. Klicke auf einen Pfad im Viewport (Sketch-Linie/Bogen/Spline oder Body-Edge)")

        # NEU: Direkte Viewport-Selektion für Sketch-Pfade aktivieren
        self.viewport_3d.start_sketch_path_mode()

        # Aktiviere sowohl Sketch-Element-Selektion als auch Edge-Selection
        # 1. Für Sketch-Elemente: Nutze Face-Selection im Detector
        self.viewport_3d.set_extrude_mode(True)  # Aktiviert allgemeine Selektion
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

        # Pfad-Daten speichern
        path_data = {
            'type': 'body_edge',
            'edge': edge,
            'edge_selector': self.viewport_3d.get_edge_selectors(),
            'build123d_edges': build123d_edges  # Direkte Edge-Referenzen
        }

        self._sweep_path_data = path_data
        self.sweep_panel.set_path(path_data)

        logger.info(f"Sweep: Pfad ausgewählt ({len(build123d_edges)} Edges). Drücke OK zum Ausführen")

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

            # Body finden oder erstellen
            if operation == "New Body" or not self.document.bodies:
                # Neuen Body erstellen
                from modeling import Body
                new_body = Body(name=f"Sweep_{len(self.document.bodies) + 1}")
                new_body.features.append(sweep_feature)
                self.document.bodies.append(new_body)
                target_body = new_body
            else:
                # Existierenden Body verwenden
                target_body = self.document.bodies[0]
                target_body.features.append(sweep_feature)

            # Body neu berechnen
            CADTessellator.notify_body_changed()
            target_body._rebuild()

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

    def _on_sketch_path_clicked(self, sketch_id: str, geom_type: str, index: int):
        """
        Handler für direkten Viewport-Klick auf Sketch-Element.
        Wird aufgerufen wenn User im Sweep-Pfad-Modus auf eine Linie/Arc/Spline klickt.
        """
        if not self._sweep_mode or self._sweep_phase != 'path':
            return

        # Finde den Sketch
        sketch = next((s for s in self.document.sketches if s.id == sketch_id), None)
        if not sketch:
            logger.warning(f"Sketch {sketch_id} nicht gefunden")
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
        path_options = []

        for sketch in self.document.sketches:
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

        logger.info(f"Sweep: Pfad aus Sketch gewählt - {name}")

    def _stop_sweep_mode(self):
        """Beendet den Sweep-Modus und räumt auf."""
        self._sweep_mode = False
        self._sweep_phase = None
        self._sweep_profile_data = None
        self._sweep_path_data = None
        self.sweep_panel.hide()

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
        # WICHTIG: Transform-Gizmo ausblenden, damit Klicks nicht abgefangen werden
        if hasattr(self.viewport_3d, 'hide_transform_gizmo'):
            self.viewport_3d.hide_transform_gizmo()

        self._loft_mode = True
        self._loft_profiles = []

        # Face-Detection aktivieren
        self.viewport_3d.set_extrude_mode(True)
        self._update_detector()

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
        if not self._loft_mode:
            return

        # Finde die Face-Daten
        face = next((f for f in self.viewport_3d.detector.selection_faces if f.id == face_id), None)
        if not face:
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

        # Prüfen ob schon ausgewählt (gleiche Z-Ebene)
        z_new = profile_data['plane_origin'][2] if isinstance(profile_data['plane_origin'], (list, tuple)) else 0

        for existing in self._loft_profiles:
            z_existing = existing['plane_origin'][2] if isinstance(existing['plane_origin'], (list, tuple)) else 0
            if abs(z_new - z_existing) < 0.1:
                logger.warning(f"Loft: Profil auf Z={z_new:.0f} bereits vorhanden - übersprungen")
                return

        # Profil hinzufügen
        self._loft_profiles.append(profile_data)
        self.loft_panel.add_profile(profile_data)

        logger.info(f"Loft: Profil auf Z={z_new:.0f} hinzugefügt ({len(self._loft_profiles)} Profile)")

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
            # Profile nach Z sortieren
            profiles_sorted = sorted(profiles, key=lambda p: p['plane_origin'][2] if isinstance(p['plane_origin'], (list, tuple)) else 0)

            # Loft Feature erstellen
            loft_feature = LoftFeature(
                profile_data=profiles_sorted,
                ruled=ruled,
                operation=operation
            )

            # Body finden oder erstellen
            if operation == "New Body" or not self.document.bodies:
                from modeling import Body
                new_body = Body(name=f"Loft_{len(self.document.bodies) + 1}")
                new_body.features.append(loft_feature)
                self.document.bodies.append(new_body)
                target_body = new_body
            else:
                target_body = self.document.bodies[0]
                target_body.features.append(loft_feature)

            # Body neu berechnen
            CADTessellator.notify_body_changed()
            target_body._rebuild()

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
        self.loft_panel.hide()

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
        Implementierung: Fusion 360-ähnliche Section Analysis mit Clipping Planes
        """
        if self.section_panel.isVisible():
            # Deaktiviere Section View
            self.section_panel.hide()
            if self.viewport_3d._section_view_enabled:
                self.viewport_3d.disable_section_view()
            logger.info("🔪 Section View Panel geschlossen")
        else:
            # Zeige Section View Panel
            # ✅ FIX: Berechne Position relativ zum Viewport
            viewport_geom = self.viewport_3d.geometry()

            # Position: Rechts oben im Viewport-Bereich
            panel_width = 320  # Feste Breite (aus SectionViewPanel)
            panel_x = viewport_geom.right() - panel_width - 30
            panel_y = viewport_geom.top() + 30

            # ✅ DEBUG: Zeige Positions-Info
            logger.debug(f"Section Panel Position: x={panel_x}, y={panel_y}, width={panel_width}")

            self.section_panel.move(panel_x, panel_y)
            self.section_panel.show()
            self.section_panel.raise_()

            # ✅ AUTO-AKTIVIEREN: Aktiviere Section View automatisch beim Öffnen
            if not self.section_panel._is_active:
                self.section_panel.toggle_button.click()  # Simuliere Button-Klick

            logger.info("🔪 Section View Panel geöffnet & aktiviert")
            logger.info("Tipp: Bewege Position-Slider um durch den Körper zu schneiden!")



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

    def _update_tnp_stats(self, body=None):
        """
        Aktualisiert das TNP-Statistiken-Panel.

        Args:
            body: Body-Objekt oder None (verwendet dann aktiven Body)
        """
        if not hasattr(self, 'tnp_stats_panel'):
            return

        if body is None:
            body = self._get_active_body()

        try:
            self.tnp_stats_panel.update_stats(body)
        except Exception as e:
            logger.debug(f"TNP Stats Update fehlgeschlagen: {e}")

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
            return

        from modeling.cad_tessellator import CADTessellator
        from modeling import Body

        # Neuen Body erstellen
        new_b = Body(name=f"{body.name}_Kopie")

        # Build123d Solid kopieren (NICHT deepcopy - das funktioniert nicht für OCP!)
        if hasattr(body, '_build123d_solid') and body._build123d_solid:
            try:
                # Build123d.copy() ist die korrekte Methode
                new_b._build123d_solid = body._build123d_solid.copy()
                logger.debug(f"Build123d Solid kopiert für {new_b.name}")
            except Exception as e:
                logger.error(f"Solid-Kopie fehlgeschlagen: {e}")
                return

        # Mesh generieren
        CADTessellator.notify_body_changed()
        self._update_body_from_build123d(new_b, new_b._build123d_solid)

        # Zum Document hinzufügen
        self.document.bodies.append(new_b)

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