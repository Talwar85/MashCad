"""
MashCad - PyVista 3D Viewport
V3.0: Modular mit Mixins für bessere Wartbarkeit

W31: Headless-safe Bootstrap - EPIC A2 Implementation
- Erkennung von headless Modus via Umgebungsvariablen
- Mock-Implementierung für QtInteractor in Tests
- Verhindert Access Violations bei QT_QPA_PLATFORM='offscreen'
"""

import os
import math
import numpy as np
from typing import Optional, List, Tuple, Dict, Any
import uuid
from loguru import logger
from gui.geometry_detector import GeometryDetector
import time
from modeling.geometry_utils import normalize_plane_axes


# =============================================================================
# W31 EPIC A2: Headless Mode Detection & Mock Infrastructure
# =============================================================================

def is_headless_mode() -> bool:
    """
    Erkennung von headless/headless-safe Modus.

    Returns:
        True wenn in einem headless Test-Umfeld (QT_QPA_PLATFORM='offscreen')
    """
    return os.environ.get('QT_QPA_PLATFORM') == 'offscreen' or \
           os.environ.get('PYTEST_CURRENT_TEST') is not None or \
           os.environ.get('LITECAD_HEADLESS') == '1'


class MockInteractorWidget:
    """
    Mock-Implementierung von QtInteractor für headless Tests.

    Stellt die gleiche API wie QtInteractor.interactor zur Verfügung,
    ohne echte VTK/OpenGL Ressourcen zu erstellen.
    """

    def __init__(self, parent=None):
        self._parent = parent
        self._style_sheet = ""
        self._mouse_tracking = False

    def setStyleSheet(self, style):
        self._style_sheet = style

    def setMouseTracking(self, enabled):
        self._mouse_tracking = enabled

    def installEventFilter(self, filter_obj):
        pass  # No-op in headless

    def show(self):
        pass

    def hide(self):
        pass

    def close(self):
        pass

    def height(self):
        # Default height used by picker coordinate conversion in headless tests.
        return 800


class MockPlotter:
    """
    Mock-Implementierung von QtInteractor (Plotter) für headless Tests.

    Stellt die gleiche API wie der echte Plotter zur Verfügung,
    aber führt keine echten VTK-Operationen aus.
    """

    def __init__(self, parent=None):
        self.interactor = MockInteractorWidget(parent)
        self._iren = None
        self._ren_win = None
        self._actors = {}
        self._background = '#1e1e1e'
        self._camera_position = (1, 1, 1)
        self._focal_point = (0, 0, 0)
        self._view_up = (0, 0, 1)
        self._is_closed = False

    # Attribute-Emulation für hasattr() Checks
    @property
    def iren(self):
        return self._iren

    @property
    def ren_win(self):
        return self._ren_win

    def set_background(self, color, top=None):
        self._background = color

    def enable_trackball_style(self):
        pass

    def add_key_event(self, key, callback):
        pass

    def enable_anti_aliasing(self, method):
        pass

    def hide_axes(self):
        pass

    def add_mesh(self, mesh, **kwargs):
        # Speichere Actor für spätere Referenz
        name = kwargs.get('name', f'mesh_{len(self._actors)}')
        self._actors[name] = (mesh, kwargs)
        return name

    def remove_actor(self, actor, **_kwargs):
        """
        Entfernt einen Actor aus dem Mock-Registry.

        Akzeptiert sowohl den Actor-Namen (str) als auch die gespeicherte
        Mesh-Referenz aus add_mesh().
        """
        if actor is None:
            return

        if isinstance(actor, str):
            self._actors.pop(actor, None)
            return

        keys_to_remove = []
        for key, value in self._actors.items():
            mesh_obj, _kwargs = value
            if mesh_obj is actor:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            self._actors.pop(key, None)

    def clear(self):
        self._actors.clear()

    def view_isometric(self):
        pass

    def reset_camera(self):
        pass

    def render(self):
        pass

    def close(self):
        self._is_closed = True

    def add_text(self, *args, **kwargs):
        return None

    def add_point_labels(self, *args, **kwargs):
        name = kwargs.get('name', f'labels_{len(self._actors)}')
        self._actors[name] = ("labels", kwargs)
        return name

    def add_camera_orientation_widget(self):
        return None

    def set_position(self, position):
        self._camera_position = position

    def set_focus(self, focal_point):
        self._focal_point = focal_point

    def set_viewup(self, view_up):
        self._view_up = view_up


def create_headless_safe_plotter(parent=None):
    """
    Erstellt einen Plotter (echt oder Mock) basierend auf Umgebung.

    Args:
        parent: Parent Widget

    Returns:
        QtInteractor oder MockPlotter
    """
    if is_headless_mode():
        logger.debug("[W31-HEADLESS] Using MockPlotter for headless mode")
        return MockPlotter(parent)
    else:
        from pyvistaqt import QtInteractor
        return QtInteractor(parent)


# End of W31 EPIC A2 Headless Infrastructure
# =============================================================================

# Mixins importieren
from gui.viewport.extrude_mixin import ExtrudeMixin
from gui.viewport.picking_mixin import PickingMixin
from gui.viewport.body_mixin import BodyRenderingMixin
from gui.viewport.transform_mixin_v3 import TransformMixinV3
from gui.viewport.edge_selection_mixin import EdgeSelectionMixin
from gui.viewport.section_view_mixin import SectionViewMixin, SectionClipCache
from gui.viewport.selection_mixin import SelectionMixin  # Paket B: Unified Selection API
from gui.viewport.feature_preview_mixin import FeaturePreviewMixin  # Live Preview für Shell, Fillet, Chamfer
from gui.viewport.render_queue import request_render  # Phase 4: Performance
from config.tolerances import Tolerances  # Phase 5: Zentralisierte Toleranzen
from config.feature_flags import is_enabled  # Performance Plan Phase 3
from gui.design_tokens import DesignTokens  # NEU: Single Source of Truth

from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame, QLabel, QToolButton, QApplication
from PySide6.QtCore import Qt, Signal, QTimer, QEvent, QPoint
from PySide6.QtGui import QCursor, QColor

# ==================== IMPORTS ====================
HAS_PYVISTA = False
try:
    import pyvista as pv
    from pyvistaqt import QtInteractor
    import vtk 
    HAS_PYVISTA = True
    logger.success("PyVista & VTK erfolgreich geladen.")
except ImportError as e:
    logger.error(f"PyVista Import-Fehler: {e}")

HAS_BUILD123D = False
try:
    import build123d
    HAS_BUILD123D = True
except ImportError as e:
    logger.debug(f"build123d not available: {e}")

HAS_SHAPELY = False
try:
    from shapely.geometry import LineString, Polygon, Point
    from shapely.ops import polygonize, unary_union, triangulate
    HAS_SHAPELY = True
except ImportError as e:
    logger.debug(f"shapely not available: {e}")


# =============================================================================
# G1 Core Stability: Safe Exception Handling Helpers
# =============================================================================

def _log_suppressed_exception(context: str, error: Exception, level: str = "debug") -> None:
    """
    Log a suppressed exception with context for observability.
    
    G1 Core Stability: Replaces silent exception-swallowing patterns
    with structured logging while preserving application stability.
    
    Args:
        context: Description of the operation that failed
        error: The caught exception
        level: Log level ('debug', 'warning', 'error')
    """
    log_msg = f"[viewport] {context}: {error}"
    if level == "error":
        logger.error(log_msg)
    elif level == "warning":
        logger.warning(log_msg)
    else:
        logger.debug(log_msg)


def _safe_remove_actor(plotter, actor_name: str, context: str = "actor removal") -> bool:
    """
    Safely remove an actor from the plotter with structured logging.
    
    G1 Core Stability: Centralizes safe actor removal with consistent
    error handling and observability.
    
    Args:
        plotter: The PyVista plotter instance
        actor_name: Name of the actor to remove
        context: Context string for logging
        
    Returns:
        True if removal succeeded, False otherwise
    """
    try:
        plotter.remove_actor(actor_name, render=False)
        return True
    except Exception as e:
        _log_suppressed_exception(f"{context} ('{actor_name}')", e)
        return False


def _safe_actors_remove(plotter, actor_names: list, context: str = "batch actor removal") -> int:
    """
    Safely remove multiple actors from the plotter.
    
    Args:
        plotter: The PyVista plotter instance
        actor_names: List of actor names to remove
        context: Context string for logging
        
    Returns:
        Number of successfully removed actors
    """
    removed = 0
    for name in actor_names:
        if _safe_remove_actor(plotter, name, context):
            removed += 1
    return removed


class OverlayHomeButton(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText("🏠")
        self.setFixedSize(32, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Standardansicht (Home)")
        p = DesignTokens.COLOR_PRIMARY.name()
        elevated = DesignTokens.COLOR_BG_ELEVATED.name()
        self.setStyleSheet(f"""
            QToolButton {{
                background-color: {elevated};
                color: {DesignTokens.COLOR_TEXT_PRIMARY.name()};
                border: 1px solid {DesignTokens.COLOR_BORDER.name()};
                border-radius: 4px;
                font-size: 16px;
            }}
            QToolButton:hover {{
                background-color: {p};
                border: 1px solid {p};
                color: white;
            }}
        """)


class PyVistaViewport(QWidget, SelectionMixin, ExtrudeMixin, PickingMixin, BodyRenderingMixin, TransformMixinV3, EdgeSelectionMixin, SectionViewMixin, FeaturePreviewMixin):
    view_changed = Signal()
    plane_clicked = Signal(str)
    custom_plane_clicked = Signal(tuple, tuple)
    extrude_requested = Signal(list, float, str)
    height_changed = Signal(float)
    face_selected = Signal(int)
    target_face_selected = Signal(int)  # "Extrude to Face" Ziel-Pick
    transform_changed = Signal(float, float, float) # für UI-Panel Update
    clicked_3d_point = Signal(int, tuple) # body_id, (x,y,z)
    body_clicked = Signal(str)  # body_id - NEU: Für pending transform mode (Fix 1)
    body_transform_requested = Signal(str, str, object)  # body_id, mode, data
    body_copy_requested = Signal(str, str, object)  # body_id, mode, data - Kopiert Body und transformiert
    body_mirror_requested = Signal(str, str)  # body_id, plane (XY/XZ/YZ)
    mirror_requested = Signal(str)  # body_id - Öffnet Mirror-Dialog
    point_to_point_move = Signal(str, tuple, tuple)  # body_id, start_point, end_point - NEU: Point-to-Point Move
    point_to_point_start_picked = Signal(tuple)  # start point picked
    point_to_point_cancelled = Signal()
    edge_selection_changed = Signal(int)  # NEU: Anzahl selektierter Kanten für Fillet/Chamfer
    sketch_path_clicked = Signal(str, str, int)  # NEU: sketch_id, geom_type ('line', 'arc', 'spline'), index
    texture_face_selected = Signal(int)  # NEU: Anzahl selektierter Faces für Texture
    measure_point_picked = Signal(tuple)  # (x, y, z) - Punkt fuer Measure-Tool
    offset_plane_drag_changed = Signal(float)  # Offset-Wert während Drag
    hole_face_clicked = Signal(str, int, tuple, tuple)  # body_id, cell_id, normal, position
    thread_face_clicked = Signal(str, int, tuple, tuple, float)  # body_id, cell_id, normal, position, cylinder_diameter
    draft_face_clicked = Signal(str, int, tuple, tuple)  # body_id, cell_id, normal, position
    split_body_clicked = Signal(str)  # body_id
    split_drag_changed = Signal(float)  # position during drag
    split_drag_changed = Signal(float)  # position during drag
    extrude_cancelled = Signal()  # Rechtsklick/Esc bricht Extrude ab
    background_clicked = Signal()  # Klick ins Leere (Deselect)
    create_sketch_requested = Signal(int)  # face_id für Sketch-Erstellung


    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._viewcube_created = False  # VOR _setup_plotter initialisieren

        # NEU: Referenz auf zentrale TransformState (wird später von MainWindow gesetzt)
        self.transform_state = None

        # Dunkler Hintergrund für das Widget selbst (Figma neutral-900)
        self.setStyleSheet(f"background-color: {DesignTokens.COLOR_BG_CANVAS.name()};")
        self.setAutoFillBackground(True)

        self._setup_ui()
        
        if HAS_PYVISTA:
            self._setup_plotter()
            self._setup_scene()
        
        # State
        self.sketches = []
        self.bodies = {}
        self._pending_body_refs = {}  # body_id -> Body reference (for async add_body timing)
        self.detected_faces = []
        self.active_selection_filter = GeometryDetector.SelectionFilter.ALL
        self.selected_faces = set()
        self.hovered_face = -1
        self.hovered_body_face = None  # (body_id, cell_id, normal, position)
        self.body_face_extrude = None  # Für Extrusion von Body-Flächen
        self._last_picked_face_center = None
        self._last_picked_face_normal = None
        
        # Modes
        self.plane_select_mode = False
        self.extrude_mode = False
        self.extrude_preview_enabled = True  # FIX: Separate flag for extrude preview (False for Loft/Shell)
        self._to_face_picking = False  # "Extrude to Face" Ziel-Pick-Modus
        self.measure_mode = False
        self._measure_actor_names = []
        self.revolve_mode = False
        self._revolve_preview_actor = None
        self._revolve_axis = (0, 1, 0)
        self._revolve_angle = 360.0
        self._revolve_selected_faces = []

        self.hole_mode = False
        self._hole_preview_actor = None
        self._hole_position = None      # (x, y, z) on face
        self._hole_normal = None        # face normal
        self._hole_diameter = 8.0
        self._hole_depth = 0.0          # 0 = through all
        self._hole_body_id = None

        self.thread_mode = False
        self._thread_preview_actor = None
        self._thread_position = None    # (x, y, z) on cylindrical face
        self._thread_direction = None   # axis direction of cylinder
        self._thread_diameter = 10.0
        self._thread_depth = 20.0
        self._thread_body_id = None
        self._thread_is_internal = False  # True for holes, False for shafts

        self.draft_mode = False
        self._draft_selected_faces = []  # list of (body_id, cell_id, normal, position)
        self._draft_body_id = None
        self._draft_preview_actor = None

        self.split_mode = False
        self._split_body_id = None
        self._split_plane_axis = "XY"
        self._split_position = 0.0
        self._split_angle = 0.0         # cut angle in degrees


        self._split_bb = None           # body bounding box
        self._split_dragging = False
        self._split_drag_start = None
        self._split_drag_start_pos = 0.0

        self.offset_plane_mode = False
        self._offset_plane_base_origin = None
        self._offset_plane_base_normal = None
        self._offset_plane_preview_actor = None
        self._offset_plane_edge_actor = None
        self._offset_plane_offset = 0.0
        self._offset_plane_dragging = False
        self._offset_plane_drag_start = None
        self._offset_plane_drag_start_offset = 0.0

        # Edge Selection Mixin initialisieren
        self._init_edge_selection()

        # Section View Mixin initialisieren
        self._init_section_view()

        # Paket B: Unified Selection API initialisieren
        self._init_selection_state()

        # Box selection
        self._box_select_active = False
        self._box_select_start = None
        self._box_select_rect = None  # QRubberBand

        self.pending_transform_mode = False  # NEU: Für Body-Highlighting
        self.point_to_point_mode = False  # NEU: Point-to-Point Move (wie CAD)
        self._sweep_mode = False
        self._loft_mode = False
        self.sketch_path_mode = False  # NEU: Sketch-Element-Selektion für Sweep-Pfad
        self.texture_face_mode = False  # NEU: Face-Selektion für Surface Texture
        self._texture_body_id = None  # Body für Texture-Selektion
        self._texture_selected_faces = []  # Liste von selektierten Body-Faces für Texture
        self.point_to_point_start = None  # Erster ausgewählter Punkt (x, y, z)
        self.point_to_point_body_id = None  # Body, der verschoben wird

        # Phase 3: Performance - Cached Hover Markers (statt 60x/sec neu erstellen)
        self._p2p_hover_marker_mesh = None  # Cached Sphere Mesh (orange, radius 1.5)
        self._p2p_hover_marker_actor = None  # Cached VTK Actor
        self._p2p_start_marker_mesh = None  # Cached Sphere Mesh (yellow, radius 2.0)
        self._p2p_start_marker_actor = None  # Cached VTK Actor
        self.extrude_height = 0.0
        self.extrude_operation = "New Body"  # NEU: Aktuelle Operation für Farbe
        self.is_dragging = False
        self.drag_start_pos = QPoint()
        self.drag_start_height = 0.0

        # ✅ FIX: Track last picked body for sketch targeting
        self._last_picked_body_id = None
        
        # Tracking
        self._sketch_actors = []
        self._body_actors = {}
        self._plane_actors = {}
        self._construction_plane_actors = {}
        self._face_actors = []
        self._preview_actor = None
        self.last_highlighted_plane = None
        self.detector = GeometryDetector()
        self.selected_face_ids = set()
        self.hover_face_id = None
        self.hover_body_id = None  # NEU: Für Body-Highlighting im pending transform mode
        
        self.setFocusPolicy(Qt.StrongFocus)
        
        self.transform_actor = None # Der Actor der gerade transformiert wird
        self.transform_widget = None # Das Gizmo
        self.original_matrix = None # Zum Zurücksetzen
        self._last_pick_time = 0
        self._pick_interval = 0.05  # 20 Checks pro Sekunde (50ms)

        # Phase 4: Globales Mouse-Event Throttling
        self._last_mouse_move_time = 0
        self._mouse_move_interval = 0.016  # ~60 FPS max (16ms)
        self._right_click_start_pos = None
        self._right_click_start_global_pos = None
        self._right_click_start_time = 0.0
        self._trace_hint_face_id = None
        self._trace_hint_label = None
        self._projection_preview_label = None
        self._projection_preview_actor_names = []

        # PERFORMANCE: Reusable cell picker (avoid creating new picker per hover)
        self._body_cell_picker = None  # Lazy init on first use

        # Phase 4: Performance - Picker Pool (verschiedene Toleranzen für verschiedene Use-Cases)
        self._picker_standard = None  # Standard tolerance (PICKER_TOLERANCE)
        self._picker_coarse = None    # Coarse tolerance (PICKER_TOLERANCE_COARSE)
        self._picker_measure = None   # Measure mode (0.005)

        # PERFORMANCE: Hover pick cache (avoid redundant picks within same frame)
        self._hover_pick_cache = None  # (timestamp, x, y, body_id, cell_id, normal, position)
        self._hover_pick_cache_ttl = 0.008  # 8ms cache validity (~120 FPS worth)

        # Phase 1: Viewport LOD system (coarse during camera interaction)
        self._lod_enabled = bool(is_enabled("viewport_lod_system"))
        self._lod_quality_high = float(Tolerances.TESSELLATION_QUALITY)
        self._lod_quality_interaction = float(Tolerances.TESSELLATION_PREVIEW)
        self._lod_min_points = 2500
        self._lod_applied_quality = {}  # body_id -> tessellation quality
        self._lod_restore_timer = QTimer(self)
        self._lod_restore_timer.setSingleShot(True)
        self._lod_restore_timer.setInterval(100)
        self._lod_restore_timer.timeout.connect(self._on_lod_restore_timeout)
        self._frustum_culling_enabled = bool(is_enabled("viewport_frustum_culling"))
        self._frustum_culled_body_ids = set()
        self._frustum_culling_margin = 1.05

        # Route direct viewport events through the same eventFilter logic.
        # Must be installed after state initialization because style/focus setup
        # can fire early events.
        self.installEventFilter(self)

    def cancel_drag(self):
        """
        Cancels any active drag operation.
        Used by Abort Logic (Escape).
        """
        if self.is_dragging:
            self.is_dragging = False
            self.drag_start_pos = QPoint()
            # Reset cursor
            self.setCursor(Qt.ArrowCursor)
            logger.debug("[Viewport] Drag cancelled via Abort/Escape")
        
        if self._offset_plane_dragging:
            self._offset_plane_dragging = False
            self._offset_plane_drag_start = None
            self.setCursor(Qt.ArrowCursor)
            
        if self._split_dragging:
            self._split_dragging = False
            self.setCursor(Qt.ArrowCursor)

        self._safe_request_render()

    def _safe_request_render(self, immediate: bool = False):
        """
        Queue a viewport render only when the plotter is available.
        Avoid direct render calls in high-frequency abort paths.
        """
        if not HAS_PYVISTA:
            return
        plotter = getattr(self, "plotter", None)
        if plotter is None:
            return
        try:
            request_render(plotter, immediate=immediate)
        except Exception as e:
            logger.debug(f"[viewport] Render request skipped: {e}")

    def _on_camera_interaction_start(self):
        """Start interaction callback: switch large meshes to interaction LOD."""
        if not getattr(self, "_lod_enabled", False):
            return
        try:
            if self._lod_restore_timer.isActive():
                self._lod_restore_timer.stop()
            self._apply_lod_to_visible_bodies(interaction_active=True)
        except Exception as e:
            _log_suppressed_exception("camera interaction start LOD", e)

    def _on_camera_interaction_end(self):
        """End interaction callback: emit view change and restore quality LOD."""
        self.view_changed.emit()
        try:
            self._apply_frustum_culling(force=False)
            if getattr(self, "_lod_enabled", False):
                self._lod_restore_timer.start()
        except Exception as e:
            _log_suppressed_exception("camera interaction end LOD", e)

    def _on_lod_restore_timeout(self):
        """Delayed quality-restore to avoid immediate re-tessellation thrash."""
        if not getattr(self, "_lod_enabled", False):
            return
        self._apply_lod_to_visible_bodies(interaction_active=False)
        self._apply_frustum_culling(force=False)

    def _is_body_actor_visible(self, body_id: str) -> bool:
        actor_names = self._body_actors.get(body_id)
        if not actor_names:
            return False
        mesh_actor = self.plotter.renderer.actors.get(actor_names[0])
        if not mesh_actor:
            return False
        try:
            return bool(mesh_actor.GetVisibility())
        except Exception:
            return True

    def _apply_lod_to_visible_bodies(self, interaction_active: bool) -> None:
        """
        Apply viewport LOD by swapping actor input meshes.

        - During camera interaction: preview quality for large bodies
        - After interaction: full quality
        """
        if not HAS_PYVISTA or not hasattr(self, "plotter"):
            return

        from modeling.cad_tessellator import CADTessellator

        target_quality = (
            self._lod_quality_interaction
            if interaction_active
            else self._lod_quality_high
        )

        updated = 0
        for body_id in list(self._body_actors.keys()):
            body_data = self.bodies.get(body_id) or {}
            source_mesh = body_data.get("mesh")
            if source_mesh is None:
                continue
            current_quality = self._lod_applied_quality.get(body_id)
            source_points = int(getattr(source_mesh, "n_points", 0))
            if source_points < self._lod_min_points:
                is_interaction_lod = (
                    current_quality is not None
                    and abs(current_quality - self._lod_quality_interaction) < 1e-12
                )
                # Allow restoring full quality even if current interaction mesh is small.
                if not (not interaction_active and is_interaction_lod):
                    continue
            if not self._is_body_actor_visible(body_id):
                continue

            if current_quality is not None and abs(current_quality - target_quality) < 1e-12:
                continue

            body_ref = body_data.get("body_ref") or body_data.get("body")
            solid = getattr(body_ref, "_build123d_solid", None) if body_ref else None
            if solid is None:
                continue

            mesh, edge_mesh, _face_info = CADTessellator.tessellate_with_face_ids(
                solid,
                quality=target_quality,
            )
            if mesh is None:
                continue

            if not self._apply_lod_mesh_to_actor(body_id, mesh, edge_mesh):
                continue

            self.bodies[body_id]["mesh"] = mesh
            self._lod_applied_quality[body_id] = target_quality
            updated += 1

        if updated > 0:
            request_render(self.plotter, immediate=interaction_active)
            logger.debug(
                f"[LOD] Updated {updated} bodies at quality={target_quality:.4f} "
                f"(interaction={interaction_active})"
            )

    def _apply_lod_mesh_to_actor(self, body_id: str, mesh, edge_mesh) -> bool:
        """Swap actor mapper input for LOD without recreating actors."""
        actor_names = self._body_actors.get(body_id)
        if not actor_names:
            return False

        mesh_actor = self.plotter.renderer.actors.get(actor_names[0])
        if not mesh_actor:
            return False

        display_mesh = mesh
        if getattr(self, "_section_view_enabled", False):
            try:
                plane_origins = {
                    "XY": [0, 0, self._section_position],
                    "YZ": [self._section_position, 0, 0],
                    "XZ": [0, self._section_position, 0],
                }
                plane_normals = {
                    "XY": [0, 0, 1],
                    "YZ": [1, 0, 0],
                    "XZ": [0, 1, 0],
                }
                origin = plane_origins.get(self._section_plane, [0, 0, self._section_position])
                normal = plane_normals.get(self._section_plane, [0, 0, 1])
                if self._section_invert:
                    normal = [-n for n in normal]

                SectionClipCache.invalidate_body(body_id)
                display_mesh = SectionClipCache.get_clipped(
                    body_id=body_id,
                    mesh=mesh,
                    plane=self._section_plane,
                    position=self._section_position,
                    normal=normal,
                    origin=origin,
                    inverted=self._section_invert,
                )
            except Exception as e:
                _log_suppressed_exception(f"LOD section clip update (body={body_id})", e)
                display_mesh = mesh

        try:
            mapper = mesh_actor.GetMapper()
            mapper.SetInputData(display_mesh)
            mapper.Modified()
            mesh_actor.SetVisibility(True)

            if len(actor_names) > 1 and edge_mesh is not None:
                edge_actor = self.plotter.renderer.actors.get(actor_names[1])
                if edge_actor:
                    edge_mapper = edge_actor.GetMapper()
                    edge_mapper.SetInputData(edge_mesh)
                    edge_mapper.Modified()
            return True
        except Exception as e:
            _log_suppressed_exception(f"LOD actor update (body={body_id})", e)
            return False

    def _get_camera_aspect_ratio(self) -> float:
        """Best-effort camera aspect ratio extraction."""
        renderer = getattr(self.plotter, "renderer", None)
        if renderer is not None and hasattr(renderer, "GetTiledAspectRatio"):
            try:
                aspect = float(renderer.GetTiledAspectRatio())
                if aspect > 1e-6:
                    return aspect
            except Exception:
                pass

        render_window = getattr(self.plotter, "render_window", None)
        if render_window is not None and hasattr(render_window, "GetSize"):
            try:
                w, h = render_window.GetSize()
                if h and h > 0:
                    return float(w) / float(h)
            except Exception:
                pass

        return 1.0

    def _is_bounds_in_camera_frustum(self, bounds) -> bool:
        """Approximate frustum check using bounding sphere in camera space."""
        if bounds is None or len(bounds) != 6:
            return True

        try:
            xmin, xmax, ymin, ymax, zmin, zmax = [float(v) for v in bounds]
        except Exception:
            return True

        if not np.isfinite([xmin, xmax, ymin, ymax, zmin, zmax]).all():
            return True

        dx = max(0.0, xmax - xmin)
        dy = max(0.0, ymax - ymin)
        dz = max(0.0, zmax - zmin)
        center = np.array(
            [(xmin + xmax) * 0.5, (ymin + ymax) * 0.5, (zmin + zmax) * 0.5],
            dtype=float,
        )
        radius = 0.5 * float(np.linalg.norm([dx, dy, dz]))
        radius *= float(max(1.0, self._frustum_culling_margin))

        camera = getattr(self.plotter, "camera", None)
        if camera is None:
            return True

        try:
            cam_pos = np.array(camera.GetPosition(), dtype=float)
            cam_focal = np.array(camera.GetFocalPoint(), dtype=float)
            cam_up = np.array(camera.GetViewUp(), dtype=float)
        except Exception:
            return True

        forward = cam_focal - cam_pos
        forward_norm = np.linalg.norm(forward)
        if forward_norm < 1e-12:
            return True
        forward /= forward_norm

        right = np.cross(forward, cam_up)
        right_norm = np.linalg.norm(right)
        if right_norm < 1e-12:
            return True
        right /= right_norm
        up = np.cross(right, forward)

        try:
            near_clip, far_clip = camera.GetClippingRange()
        except Exception:
            near_clip, far_clip = 0.1, 1e9
        near_clip = max(float(near_clip), 1e-6)
        far_clip = max(float(far_clip), near_clip + 1e-3)

        to_center = center - cam_pos
        depth = float(np.dot(to_center, forward))
        if depth + radius < near_clip:
            return False
        if depth - radius > far_clip:
            return False

        try:
            vfov_deg = float(camera.GetViewAngle())
        except Exception:
            vfov_deg = 60.0
        vfov_deg = max(1.0, min(179.0, vfov_deg))
        vfov_rad = math.radians(vfov_deg)
        half_h = math.tan(vfov_rad * 0.5) * max(depth, near_clip)
        half_w = half_h * self._get_camera_aspect_ratio()

        x_cam = float(np.dot(to_center, right))
        y_cam = float(np.dot(to_center, up))
        if abs(x_cam) - radius > half_w:
            return False
        if abs(y_cam) - radius > half_h:
            return False
        return True

    def _apply_frustum_culling(self, force: bool = False) -> int:
        """
        Apply camera frustum culling to mesh/edge actors.

        Returns:
            Number of actors whose visibility changed.
        """
        if not getattr(self, "_frustum_culling_enabled", False):
            return 0
        if not HAS_PYVISTA or not hasattr(self, "plotter"):
            return 0
        renderer = getattr(self.plotter, "renderer", None)
        if renderer is None or not hasattr(renderer, "actors"):
            return 0

        changed = 0
        for body_id, actor_names in self._body_actors.items():
            if not actor_names:
                continue
            mesh_actor = renderer.actors.get(actor_names[0])
            if mesh_actor is None:
                continue

            body_data = self.bodies.get(body_id) or {}
            requested_visible = bool(body_data.get("requested_visible", True))
            in_frustum = True
            if requested_visible:
                bounds = mesh_actor.GetBounds() if hasattr(mesh_actor, "GetBounds") else None
                in_frustum = self._is_bounds_in_camera_frustum(bounds)

            desired_visible = requested_visible and in_frustum
            try:
                current_visible = bool(mesh_actor.GetVisibility())
            except Exception:
                current_visible = desired_visible

            if force or current_visible != desired_visible:
                try:
                    mesh_actor.SetVisibility(desired_visible)
                    changed += 1
                except Exception as e:
                    _log_suppressed_exception(f"frustum mesh visibility (body={body_id})", e)

            if len(actor_names) > 1:
                edge_actor = renderer.actors.get(actor_names[1])
                if edge_actor is not None:
                    try:
                        edge_current = bool(edge_actor.GetVisibility())
                    except Exception:
                        edge_current = desired_visible
                    if force or edge_current != desired_visible:
                        try:
                            edge_actor.SetVisibility(desired_visible)
                        except Exception as e:
                            _log_suppressed_exception(f"frustum edge visibility (body={body_id})", e)

            if requested_visible and not in_frustum:
                self._frustum_culled_body_ids.add(body_id)
            else:
                self._frustum_culled_body_ids.discard(body_id)

        if changed > 0:
            request_render(self.plotter)
            logger.debug(f"[FrustumCulling] Updated visibility for {changed} bodies")
        return changed

    def clear_selection(self):
        """
        Clears all current selections (faces, edges, etc.)
        Used by Abort Logic (Escape).

        W7 PAKET B: Uses Unified Selection API (clear_all_selection).
        """
        # W7: Unified API - Single Source of Truth
        self.clear_all_selection()  # Clears both selected_face_ids and legacy wrappers
        self.face_selected.emit(-1) # Notify UI (-1 = none)
        self.edge_selection_changed.emit(0)

        # 3. Clear TNP Selection Manager
        if hasattr(self, 'selection_manager'):
            # Only if method exists
            if hasattr(self.selection_manager, 'clear_selection'):
                self.selection_manager.clear_selection()

        # 4. Trigger Repaint
        self._safe_request_render()

        logger.debug("[Viewport] Selection cleared via Abort/Escape")

    def _get_picker(self, tolerance_type: str = "standard"):

        """
        Phase 4: Performance - Wiederverwendbarer Picker Pool

        Args:
            tolerance_type: "standard", "coarse", oder "measure"

        Returns:
            Gecachter VTK CellPicker mit entsprechender Toleranz
        """
        # Picker wiederverwenden
        import vtk
        if tolerance_type == "coarse":
            if self._picker_coarse is None:
                self._picker_coarse = vtk.vtkCellPicker()
                self._picker_coarse.SetTolerance(Tolerances.PICKER_TOLERANCE_COARSE)
            return self._picker_coarse
        elif tolerance_type == "measure":
            if self._picker_measure is None:
                self._picker_measure = vtk.vtkCellPicker()
                self._picker_measure.SetTolerance(0.005)
            return self._picker_measure
        else:  # standard
            if self._picker_standard is None:
                self._picker_standard = vtk.vtkCellPicker()
                self._picker_standard.SetTolerance(Tolerances.PICKER_TOLERANCE)
            return self._picker_standard

    def set_selection_mode(self, mode: str):
        """Übersetzt den String-Modus aus dem MainWindow in Detector-Filter."""
        from gui.geometry_detector import GeometryDetector
        
        mapping = {
            "face": GeometryDetector.SelectionFilter.FACE,
            "hole": GeometryDetector.SelectionFilter.HOLE,
            "sketch": GeometryDetector.SelectionFilter.SKETCH,
            "all": GeometryDetector.SelectionFilter.ALL
        }
        # Setzt den aktiven Filter für den Detector
        self.active_selection_filter = mapping.get(mode, GeometryDetector.SelectionFilter.ALL)
        
        # Visuelles Feedback: Hover zurücksetzen
        self._update_hover(-1)
        request_render(self.plotter)
        
    def _setup_ui(self):
        # Direktes Layout ohne zusätzlichen Frame
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        if not HAS_PYVISTA:
            self.main_layout.addWidget(QLabel("PyVista fehlt! Installiere: pip install pyvista pyvistaqt"))
            return

        # Selection filter toolbar (floating overlay)
        self._setup_selection_filter_bar()
            
    def _setup_selection_filter_bar(self):
        """Floating selection filter toolbar (Figma-Style) at top-center of viewport."""
        from PySide6.QtWidgets import QPushButton, QHBoxLayout
        self._filter_bar = QFrame(self)
        bg = DesignTokens.COLOR_BG_PANEL.name()
        border = DesignTokens.COLOR_BORDER.name()
        self._filter_bar.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border-radius: 6px;
                border: 1px solid {border};
            }}
        """)
        bar_layout = QHBoxLayout(self._filter_bar)
        bar_layout.setContentsMargins(6, 4, 6, 4)
        bar_layout.setSpacing(4)

        self._filter_buttons = {}
        # Figma-Style Labels mit Symbolen
        filters = [
            ("✱ All", "ALL"),
            ("✎ Sketch", "SKETCH"),
            ("● Vertex", "VERTEX"),
            ("— Edge", "EDGE"),
            ("□ Face", "FACE"),
            ("⬡ Body", "BODY"),
        ]
        for label, key in filters:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == "ALL")  # ALL ist default
            elevated = DesignTokens.COLOR_BG_ELEVATED.name()
            border = DesignTokens.COLOR_BORDER.name()
            p = DesignTokens.COLOR_PRIMARY.name()
            txt = DesignTokens.COLOR_TEXT_PRIMARY.name()
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {txt};
                    border: 1px solid {border};
                    border-radius: 4px;
                    font-size: 12px;
                    font-family: 'Segoe UI', sans-serif;
                    padding: 6px 12px;
                    min-width: 70px;
                }}
                QPushButton:hover {{
                    background: {elevated};
                    border-color: #525252;
                }}
                QPushButton:checked {{
                    background: {p};
                    border-color: {p};
                    color: white;
                }}
            """)
            btn.clicked.connect(lambda checked, k=key: self._set_selection_filter(k))
            bar_layout.addWidget(btn)
            self._filter_buttons[key] = btn

        self._filter_bar.adjustSize()
        self._filter_bar.move((self.width() - self._filter_bar.width()) // 2, 10)
        self._filter_bar.raise_()

    def _set_selection_filter(self, key):
        """Set active selection filter from toolbar (Figma-Style)."""
        from gui.geometry_detector import GeometryDetector
        mapping = {
            "ALL": GeometryDetector.SelectionFilter.ALL,  # Alles selektierbar
            "SKETCH": {"sketch_profile", "sketch_shell"},  # Nur Sketch-Elemente (für Extrude!)
            "VERTEX": {"vertex"},  # Vertex-Selektion
            "EDGE": {"body_edge"},
            "FACE": GeometryDetector.SelectionFilter.FACE,
            "BODY": {"body_face", "sketch_shell", "sketch_profile"},
        }
        self.active_selection_filter = mapping.get(key, GeometryDetector.SelectionFilter.ALL)
        # Update button states (radio-like)
        for k, btn in self._filter_buttons.items():
            btn.setChecked(k == key)

    def on_mouse_move(self, event):
        """CAD-typisches Hover / Preselect"""
        current_time = time.time()
        if (current_time - self._last_pick_time < self._pick_interval):
            return 
            
        self._last_pick_time = current_time

        pos = event.position() if hasattr(event, 'position') else event.pos()
        x, y = int(pos.x()), int(pos.y())

        #ray_origin, ray_dir = self.get_ray_from_click(x, y)

        # WICHTIG: Nutze self.pick statt self.detector.pick
        face_id = self.pick(x, y, selection_filter=self.active_selection_filter) # <-- NEU: x, y übergeben

        if face_id != self.hover_face_id:
            self._update_hover(face_id)
    
    
    def _update_hover(self, face_id):
        """
        Aktualisiert den Hover-Status und zeichnet die Szene neu.
        Nutzt jetzt die optimierte _draw_selectable_faces_from_detector Methode.
        """
        if face_id == getattr(self, 'hover_face_id', -1):
            return

        self.hover_face_id = face_id

        # Trace assist only for body faces in neutral 3D context.
        trace_face_id = None
        if self._is_trace_assist_allowed() and face_id not in (-1, None):
            try:
                if hasattr(self, "detector") and self.detector is not None:
                    face = next(
                        (f for f in self.detector.selection_faces if getattr(f, "id", -1) == face_id),
                        None,
                    )
                    if face and getattr(face, "domain_type", "") == "body_face":
                        trace_face_id = int(face_id)
            except Exception:
                trace_face_id = None

        if trace_face_id is not None:
            self.show_trace_hint(trace_face_id)
        else:
            self.clear_trace_hint()

        # Zeichnen aktualisieren (das kümmert sich jetzt um Hover UND Selection)
        self._draw_selectable_faces_from_detector()
        
    def _set_face_highlight(self, face_id, state):
        face = next(
            (f for f in self.detector.selection_faces if f.id == face_id),
            None
        )
        if not face or not face.display_mesh:
            return

        if state:
            self.add_mesh(
                face.display_mesh,
                name=f"hover_{face_id}",
                opacity=0.4,
                pickable=False
            )
        else:
            self.remove_actor(f"hover_{face_id}")


    
    def _setup_plotter(self):
        self._drag_screen_vector = np.array([1.0, 0.0])

        # W31 EPIC A2: Headless-safe QtInteractor Erstellung
        # Verwendet MockPlotter in headless Tests, echten QtInteractor sonst
        self.plotter = create_headless_safe_plotter(self)
        self.plotter.interactor.setStyleSheet(f"background-color: {DesignTokens.COLOR_BG_PANEL.name()};")

        # Layout nur hinzufügen wenn wir nicht im Mock-Modus sind
        if not is_headless_mode():
            self.main_layout.addWidget(self.plotter.interactor)
        
        # --- PERFORMANCE & FIX START ---
        # Hier lag der Absturz. Wir machen das jetzt robust für alle Versionen.
        if hasattr(self.plotter, 'iren'):
            try:
                # Versuch 1: PyVista Style (snake_case) - Wahrscheinlich deine Version
                self.plotter.iren.set_desired_update_rate(60.0)
            except AttributeError:
                try:
                    # Versuch 2: VTK Style (CamelCase) - Fallback
                    self.plotter.iren.SetDesiredUpdateRate(60.0)
                except AttributeError:
                    # Wenn beides fehlt, ist es nicht kritisch, nur weniger optimiert.
                    pass
        
        # Events
        self.plotter.interactor.setMouseTracking(True)
        self.plotter.interactor.installEventFilter(self)
        
        # Kamera-Stil
        self.plotter.enable_trackball_style()

        # Wireframe Toggle (W-Taste) - echtes Toggle statt nur Wireframe-Modus setzen
        self._wireframe_mode = False
        self.plotter.add_key_event('w', self._toggle_wireframe)
        self.plotter.add_key_event('W', self._toggle_wireframe)

        # --- VISUAL QUALITÄT ---
        # Hintergrund
        self.plotter.set_background('#1e1e1e', top='#2d2d30')
        
        # WICHTIG: FXAA macht Linien unscharf. Für CAD nutzen wir lieber MSAA (Multi-Sampling).
        # Das kostet minimal mehr GPU, sieht aber bei Drahtgittermodellen viel besser aus.
        if hasattr(self.plotter, 'ren_win') and hasattr(self.plotter.ren_win, 'SetMultiSamples'):
            self.plotter.ren_win.SetMultiSamples(4) # 4x oder 8x Glättung
        else:
            # Fallback falls MSAA nicht geht
            try:
                self.plotter.enable_anti_aliasing('fxaa')
            except Exception as e:
                _log_suppressed_exception("FXAA anti-aliasing setup", e)
        # --- PERFORMANCE & FIX END ---

        # UI Cleanup: Entferne Standard-Achsen
        try:
            self.plotter.hide_axes()
        except Exception as e:
            _log_suppressed_exception("hide_axes cleanup", e)
        
        # ViewCube Widget — wird verzögert erstellt (siehe _create_cam_widget)
        self._cam_widget = None
        self._cam_widget_initialized = False
        
        # Home Button Overlay
        self.btn_home = OverlayHomeButton(self)
        self.btn_home.clicked.connect(self._reset_camera_animated)
        self.btn_home.move(20, 20)
        self.btn_home.raise_()
        self.btn_home.show()

        # Trace assist hint overlay
        self._trace_hint_label = QLabel(self)
        self._trace_hint_label.setStyleSheet(
            """
            QLabel {
                background-color: rgba(24, 24, 27, 220);
                color: #d4d4d8;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            """
        )
        self._trace_hint_label.hide()
        self._trace_hint_label.raise_()

        # Projection preview hint overlay
        self._projection_preview_label = QLabel(self)
        self._projection_preview_label.setStyleSheet(
            """
            QLabel {
                background-color: rgba(20, 38, 32, 220);
                color: #9ef7c4;
                border: 1px solid #2f7a5a;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            """
        )
        self._projection_preview_label.hide()
        self._projection_preview_label.raise_()
        
        self._viewcube_created = True
        
        # Observer für View-Changes
        try:
            if hasattr(self.plotter, 'iren') and self.plotter.iren:
                self.plotter.iren.AddObserver('StartInteractionEvent', lambda o, e: self._on_camera_interaction_start())
                self.plotter.iren.AddObserver('EndInteractionEvent', lambda o, e: self._on_camera_interaction_end())
        except Exception as e:
            _log_suppressed_exception("EndInteractionEvent observer setup", e)

        # FPS-Observer an VTK RenderWindow anhängen
        from gui.viewport.render_queue import RenderQueue
        RenderQueue.attach_fps_observer(self.plotter)
    
    def _reset_camera_animated(self):
        self.plotter.view_isometric()
        self.plotter.reset_camera()
        self.view_changed.emit()
        self._apply_frustum_culling(force=False)
        if getattr(self, "_lod_enabled", False):
            self._lod_restore_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, self._deferred_init_cam_widget)

    def _deferred_init_cam_widget(self):
        """Erstellt das Camera Orientation Widget erst nach dem ersten Layout-Pass."""
        if self._cam_widget_initialized:
            return
        self._cam_widget_initialized = True
        self._create_cam_widget()
        self._refresh_widget_layout()

    def _create_cam_widget(self):
        """Erstellt das VTK Camera Orientation Widget mit korrekter Viewport-Größe."""
        try:
            if self._cam_widget:
                self.plotter.remove_actor(self._cam_widget)
                self._cam_widget = None
        except Exception as e:
            _log_suppressed_exception("cam_widget cleanup", e)

        try:
            widget = self.plotter.add_camera_orientation_widget()
            if widget:
                self._cam_widget = widget
        except Exception as e:
            logger.warning(f"ViewCube creation failed: {e}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_widget_layout()

    def _refresh_widget_layout(self):
        if hasattr(self, 'btn_home'):
            self.btn_home.move(20, 20)
            self.btn_home.raise_()
        if hasattr(self, '_trace_hint_label') and self._trace_hint_label is not None:
            self._trace_hint_label.move(20, 60)
            self._trace_hint_label.raise_()
        if hasattr(self, '_projection_preview_label') and self._projection_preview_label is not None:
            self._projection_preview_label.move(20, 90)
            self._projection_preview_label.raise_()
        if hasattr(self, '_filter_bar'):
            self._filter_bar.move((self.width() - self._filter_bar.width()) // 2, 10)
            self._filter_bar.raise_()

    def _is_trace_assist_allowed(self) -> bool:
        """Trace-Hinweis nur im neutralen 3D-Arbeitszustand anzeigen."""
        return not any(
            (
                self.extrude_mode,
                self.measure_mode,
                self.revolve_mode,
                self.hole_mode,
                self.thread_mode,
                self.draft_mode,
                self.split_mode,
                self.offset_plane_mode,
                self.point_to_point_mode,
                self.sketch_path_mode,
                self.texture_face_mode,
                self.edge_select_mode,
                self.pending_transform_mode,
                self.plane_select_mode,
            )
        )

    def _resolve_trace_assist_face_id(self, body_id: str, pos) -> Optional[int]:
        """Bestimmt die naechste SelectionFace-ID fuer Trace-Assist."""
        if not hasattr(self, "detector") or self.detector is None:
            return None
        faces = [
            f for f in getattr(self.detector, "selection_faces", [])
            if getattr(f, "domain_type", "") == "body_face" and getattr(f, "owner_id", None) == body_id
        ]
        if not faces:
            return None
        clicked_pos = np.array(pos, dtype=float)
        best_face = min(
            faces,
            key=lambda f: float(np.linalg.norm(clicked_pos - np.array(getattr(f, "plane_origin", (0, 0, 0)), dtype=float))),
        )
        return int(getattr(best_face, "id", -1)) if getattr(best_face, "id", None) is not None else None

    def show_trace_hint(self, face_id: int):
        """Zeigt den Trace-Assist-Hinweis fuer eine gehoverte Flaeche."""
        if face_id is None or int(face_id) < 0:
            self.clear_trace_hint()
            return
        self._trace_hint_face_id = int(face_id)
        if self._trace_hint_label is not None:
            self._trace_hint_label.setText("T: Auf Sketch-Ebene nachzeichnen")
            self._trace_hint_label.adjustSize()
            self._trace_hint_label.show()
            self._trace_hint_label.raise_()

    def clear_trace_hint(self):
        """Entfernt den Trace-Assist-Hinweis."""
        self._trace_hint_face_id = None
        if self._trace_hint_label is not None:
            self._trace_hint_label.hide()

    def show_projection_preview(self, edges: list, target_plane=None):
        """Zeigt eine leichte Projection-Preview (Overlay + optionale Linien)."""
        self.clear_projection_preview()
        edge_count = len(edges) if edges else 0
        plane_label = f" ({target_plane})" if target_plane else ""
        if self._projection_preview_label is not None:
            self._projection_preview_label.setText(f"Projection Preview: {edge_count} edges{plane_label}")
            self._projection_preview_label.adjustSize()
            self._projection_preview_label.show()
            self._projection_preview_label.raise_()

        if not HAS_PYVISTA or not edges:
            return

        try:
            for idx, edge in enumerate(edges):
                if not isinstance(edge, (list, tuple)) or len(edge) != 2:
                    continue
                p0, p1 = edge
                if len(p0) < 3 or len(p1) < 3:
                    continue
                pts = np.array([p0[:3], p1[:3]], dtype=float)
                line = pv.lines_from_points(pts)
                actor_name = f"projection_preview_{idx}"
                self.plotter.add_mesh(
                    line,
                    color="#00e0a4",
                    line_width=2.0,
                    name=actor_name,
                    pickable=False,
                    render_lines_as_tubes=True,
                )
                self._projection_preview_actor_names.append(actor_name)
            self._safe_request_render()
        except Exception as e:
            logger.debug(f"[viewport] projection preview draw failed: {e}")

    def clear_projection_preview(self):
        """Entfernt Projection-Preview Overlay und Linien."""
        if self._projection_preview_label is not None:
            self._projection_preview_label.hide()
        if HAS_PYVISTA:
            for actor_name in self._projection_preview_actor_names:
                _safe_remove_actor(self.plotter, actor_name, "projection preview cleanup")
            if self._projection_preview_actor_names:
                self._safe_request_render()
        self._projection_preview_actor_names = []

    def _toggle_wireframe(self):
        """Togglet zwischen Wireframe und Surface Modus für alle Meshes."""
        self._wireframe_mode = not self._wireframe_mode
        style = 'wireframe' if self._wireframe_mode else 'surface'

        # Alle Actors durchgehen
        for actor in self.plotter.renderer.GetActors():
            if actor.GetMapper():
                prop = actor.GetProperty()
                if self._wireframe_mode:
                    prop.SetRepresentationToWireframe()
                else:
                    prop.SetRepresentationToSurface()

        request_render(self.plotter)  # PERFORMANCE: Use debounced render queue
        pass

    def _setup_scene(self):
        self._draw_grid(200)
        self._draw_axes(50)
        self.plotter.camera_position = 'iso'
        self.plotter.reset_camera()
        
    def _calculate_plane_axes(self, normal_vec):
        _normal, x_dir, y_dir = normalize_plane_axes(normal_vec)
        return x_dir, y_dir
        
    # start_transform ist jetzt im TransformMixin definiert
        
    def select_body_at(self, x, y):
        """Picking Logik für Bodies"""
        picker = self._get_picker("standard")  # Phase 4: Reuse picker
        picker.Pick(x, self.plotter.interactor.height()-y, 0, self.plotter.renderer)
        actor = picker.GetActor()
        
        if actor:
            for bid, actors in self._body_actors.items():
                # FIX: Prüfen ob der getroffene Actor zu IRGENDEINEM Teil des Bodies gehört
                for name in actors:
                    if self.plotter.renderer.actors.get(name) == actor:
                        return bid
        return None

    def highlight_body(self, body_id: str):
        """Hebt einen Body farblich hervor (für pending transform mode)"""
        if not body_id or body_id not in self._body_actors:
            return

        # Ändere die Farbe des Body-Meshes zu einem hellen Blau
        mesh_name = f"body_{body_id}_m"
        try:
            actor = self.plotter.renderer.actors.get(mesh_name)
            if actor:
                actor.GetProperty().SetColor(0.4, 0.7, 1.0)  # Helles Blau
                actor.GetProperty().SetOpacity(0.8)
                request_render(self.plotter)
        except Exception as e:
            _log_suppressed_exception("highlight_body", e)

    def unhighlight_body(self, body_id: str):
        """Entfernt das Highlighting von einem Body"""
        if not body_id or body_id not in self._body_actors:
            return

        # Setze die Farbe zurück auf Standard
        mesh_name = f"body_{body_id}_m"
        try:
            actor = self.plotter.renderer.actors.get(mesh_name)
            if actor:
                # Standard-Farbe (grau)
                actor.GetProperty().SetColor(0.6, 0.6, 0.8)
                actor.GetProperty().SetOpacity(1.0)
                request_render(self.plotter)
        except Exception as e:
            _log_suppressed_exception("unhighlight_body", e)

    def set_pending_transform_mode(self, active: bool):
        """Aktiviert/deaktiviert den pending transform mode für Body-Highlighting"""
        self.pending_transform_mode = active
        if not active and self.hover_body_id:
            # Highlighting zurücksetzen wenn mode endet
            self.unhighlight_body(self.hover_body_id)
            self.hover_body_id = None
        pass

    def set_measure_mode(self, enabled: bool):
        """Aktiviert/deaktiviert Measure-Picking im Viewport."""
        self.measure_mode = bool(enabled)
        if not self.measure_mode:
            self.hovered_body_face = None
            self._clear_body_face_highlight()
            self.setCursor(Qt.ArrowCursor)
        else:
            self.setCursor(Qt.CrossCursor)

    def clear_measure_actors(self, render: bool = True):
        """Entfernt alle Measure-Visualisierungen aus dem Viewport."""
        for actor_name in list(getattr(self, "_measure_actor_names", [])):
            _safe_remove_actor(self.plotter, actor_name, "measure actor cleanup")
        self._measure_actor_names = []
        if render:
            request_render(self.plotter)

    def update_measure_visuals(self, points):
        """
        Zeichnet Measure-Visualisierung (Punkte, Linie, Distanzlabel).

        Args:
            points: Sequenz [p1, p2] mit 3D-Punkten oder None-Einträgen.
        """
        self.clear_measure_actors(render=False)

        if not HAS_PYVISTA:
            return

        p1 = points[0] if points and len(points) > 0 else None
        p2 = points[1] if points and len(points) > 1 else None

        try:
            if p1 is not None:
                actor_name = "_measure_pt_1"
                self.plotter.add_mesh(
                    pv.Sphere(radius=0.3, center=p1),
                    color="#00ff88",
                    name=actor_name,
                    pickable=False,
                )
                self._measure_actor_names.append(actor_name)

            if p2 is not None:
                actor_name = "_measure_pt_2"
                self.plotter.add_mesh(
                    pv.Sphere(radius=0.3, center=p2),
                    color="#00ff88",
                    name=actor_name,
                    pickable=False,
                )
                self._measure_actor_names.append(actor_name)

            if p1 is not None and p2 is not None:
                p1n = np.array(p1, dtype=float)
                p2n = np.array(p2, dtype=float)
                dist = float(np.linalg.norm(p2n - p1n))

                line_name = "_measure_line"
                self.plotter.add_mesh(
                    pv.Line(p1n, p2n),
                    color="#ffaa00",
                    line_width=3,
                    name=line_name,
                    pickable=False,
                )
                self._measure_actor_names.append(line_name)

                if hasattr(self.plotter, "add_point_labels"):
                    label_name = "_measure_label"
                    mid = (p1n + p2n) / 2.0
                    self.plotter.add_point_labels(
                        [mid],
                        [f"{dist:.2f} mm"],
                        name=label_name,
                        font_size=16,
                        text_color="#ffaa00",
                        point_color="#ffaa00",
                        point_size=0,
                        shape=None,
                        fill_shape=False,
                        pickable=False,
                    )
                    self._measure_actor_names.append(label_name)

            request_render(self.plotter)
        except Exception as e:
            _log_suppressed_exception("measure visuals update", e)

    def pick_point_on_geometry(self, screen_x: int, screen_y: int, snap_to_vertex: bool = True, log_pick: bool = True):
        """
        Picked einen 3D-Punkt auf der Geometrie (CAD-Style).
        Gibt (body_id, point) zurück oder (None, None) wenn nichts getroffen.

        Args:
            screen_x, screen_y: Screen-Koordinaten
            snap_to_vertex: Wenn True, snapped auf nächstgelegenen Vertex (Fusion-Style)
            log_pick: Wenn False, kein Debug-Logging (für hover performance)

        Returns:
            (body_id, point) oder (None, None)
        """
        import numpy as np

        picker = self._get_picker("standard")  # Phase 4: Reuse picker

        # Pick durchführen
        picker.Pick(screen_x, self.plotter.interactor.height() - screen_y, 0, self.plotter.renderer)

        # Prüfe ob etwas getroffen wurde
        actor = picker.GetActor()
        if not actor:
            return None, None

        # Finde Body-ID
        body_id = None
        for bid, actors in self._body_actors.items():
            for name in actors:
                if self.plotter.renderer.actors.get(name) == actor:
                    body_id = bid
                    break
            if body_id:
                break

        if not body_id:
            return None, None

        # Hole den genauen 3D-Punkt
        picked_point = picker.GetPickPosition()
        point = np.array([picked_point[0], picked_point[1], picked_point[2]])

        # SNAP TO VERTEX (CAD-Style)
        if snap_to_vertex:
            mesh_name = f"body_{body_id}_m"
            mesh_actor = self.plotter.renderer.actors.get(mesh_name)
            if mesh_actor:
                mapper = mesh_actor.GetMapper()
                if mapper:
                    polydata = mapper.GetInput()
                    points = polydata.GetPoints()

                    # Finde nächstgelegenen Vertex
                    min_dist = float('inf')
                    nearest_vertex = None
                    snap_threshold = 5.0  # 5 Einheiten max

                    for i in range(points.GetNumberOfPoints()):
                        vertex = np.array(points.GetPoint(i))
                        dist = np.linalg.norm(point - vertex)
                        if dist < min_dist and dist < snap_threshold:
                            min_dist = dist
                            nearest_vertex = vertex

                    if nearest_vertex is not None:
                        point = nearest_vertex
                        # Vertex snapping erfolgreich

        point_tuple = (float(point[0]), float(point[1]), float(point[2]))
        return body_id, point_tuple

    def start_point_to_point_mode(self, body_id: str):
        """Startet den Point-to-Point Move Modus für einen Body"""
        self.point_to_point_mode = True
        self.point_to_point_start = None
        self.point_to_point_body_id = body_id
        self.setCursor(Qt.CrossCursor)

        # Phase 3: Performance - Marker einmal erstellen (statt 60x/sec)
        if HAS_PYVISTA:
            import pyvista as pv
            if self._p2p_hover_marker_mesh is None:
                self._p2p_hover_marker_mesh = pv.Sphere(center=(0, 0, 0), radius=1.5)
            if self._p2p_start_marker_mesh is None:
                self._p2p_start_marker_mesh = pv.Sphere(center=(0, 0, 0), radius=2.0)

        logger.info("Point-to-Point Mode: Wähle Start-Punkt auf Geometrie")

    def cancel_point_to_point_mode(self):
        """Bricht den Point-to-Point Modus ab"""
        self.point_to_point_mode = False
        self.point_to_point_start = None
        self.point_to_point_body_id = None
        try:
            self.setCursor(Qt.ArrowCursor)
        except Exception as e:
            _log_suppressed_exception("setCursor in P2P cancel", e)

        # Phase 3: Performance - Marker cleanup
        try:
            # Actors bleiben cached, nur verstecken
            if hasattr(self, '_p2p_hover_marker_actor') and self._p2p_hover_marker_actor:
                self._p2p_hover_marker_actor.SetVisibility(False)
            if hasattr(self, '_p2p_start_marker_actor') and self._p2p_start_marker_actor:
                self._p2p_start_marker_actor.SetVisibility(False)
        except Exception as e:
            logger.debug(f"[viewport] P2P cleanup warning: {e}")
        logger.info("Point-to-Point Mode abgebrochen")
        try:
            self.point_to_point_cancelled.emit()
        except Exception as e:
            _log_suppressed_exception("point_to_point_cancelled emit", e)

    def highlight_edge(self, p1, p2):
        """Zeichnet eine rote Linie (genutzt für Fillet/Chamfer Vorschau)"""
        import uuid
        import pyvista as pv
        
        # Linie erstellen
        line = pv.Line(p1, p2)
        
        # Eindeutigen Namen generieren, damit wir mehrere Linien haben können
        name = f"highlight_{uuid.uuid4()}"
        
        self.plotter.add_mesh(line, color='red', line_width=5, name=name)

    def clear_highlight(self):
        """Entfernt alle Highlight-Linien"""
        # Suche alle Actors, die mit "highlight_" beginnen
        to_remove = [name for name in self.plotter.renderer.actors.keys() if name.startswith("highlight_")]

        for name in to_remove:
            self.plotter.remove_actor(name)

        # Zur Sicherheit Rendern
        request_render(self.plotter)

    def clear_all_highlights(self):
        """
        Entfernt ALLE Highlight-Typen aus dem Viewport.
        Sollte aufgerufen werden wenn ein Modus beendet wird.
        """
        # 1. Standard highlight_ Actors
        self.clear_highlight()

        # 2. Face actors (Extrude/Loft Selection)
        self._clear_face_actors()

        # 3. Body Face Highlight (Hover)
        self._clear_body_face_highlight()

        # 4. Draft Face Highlights
        self._clear_draft_face_highlights()

        # 5. Texture Face Highlights
        self._clear_texture_face_highlights()

        # 7. Edge Highlights
        if hasattr(self, '_clear_edge_highlights'):
            self._clear_edge_highlights()

        # 8. Plane Hover Highlight
        self._clear_plane_hover_highlight()

        # 9. Sweep Highlights
        _safe_remove_actor(self.plotter, 'sweep_profile_highlight', "sweep profile highlight cleanup")
        _safe_remove_actor(self.plotter, 'sweep_path_highlight', "sweep path highlight cleanup")

        # 10. Sonstige bekannte Highlight-Namen
        highlight_patterns = [
            'det_face_', 'draft_face_highlight_', 'texture_face_highlight_',
            'body_face_highlight', 'body_face_arrow',
        ]
        for name in list(self.plotter.renderer.actors.keys()):
            for pattern in highlight_patterns:
                if pattern in name:
                    _safe_remove_actor(self.plotter, name, "pattern highlight cleanup")
                    break

        request_render(self.plotter)
        
    # Transform-Methoden sind jetzt im TransformMixin
    # (start_transform, end_transform, apply_transform_values, etc.)

    def get_current_transform_matrix(self):
        """Gibt die aktuelle Matrix des transformierten Objekts zurück (für Apply)"""
        if hasattr(self, '_transform_controller') and self._transform_controller.state:
            vals = self._transform_controller.get_values()
            # Einfache 4x4 Identity mit Translation
            return [
                [1, 0, 0, vals[0]],
                [0, 1, 0, vals[1]],
                [0, 0, 1, vals[2]],
                [0, 0, 0, 1]
            ]
        return None
        
    def _draw_grid(self, size=200, spacing=10):
        _safe_remove_actor(self.plotter, 'grid_main', "grid cleanup")
        n_lines = int(size/spacing)+1
        lines = []
        h = size/2
        for i in range(n_lines):
            p = -h + i*spacing
            lines.append(pv.Line((-h, p, 0), (h, p, 0)))
            lines.append(pv.Line((p, -h, 0), (p, h, 0)))
        if lines:
            grid = pv.MultiBlock(lines).combine()
            self.plotter.add_mesh(grid, color='#3a3a3a', line_width=1, name='grid_main', pickable=False)

    def update_grid_to_model(self):
        """Passt Grid-Groesse an die Bounding-Box aller Bodies an."""
        max_extent = 50.0
        for bid, info in self.bodies.items():
            mesh = info.get('mesh')
            if mesh is not None and hasattr(mesh, 'bounds'):
                b = mesh.bounds  # (xmin, xmax, ymin, ymax, zmin, zmax)
                extent = max(abs(b[1] - b[0]), abs(b[3] - b[2]), abs(b[5] - b[4]))
                max_extent = max(max_extent, extent)

        # Grid = 4x groesste Ausdehnung, gerundet auf naechste 10er-Potenz
        import math
        grid_size = max_extent * 4
        # Spacing: ~20 Linien sichtbar
        spacing = max(1, round(grid_size / 20))
        # Auf schoene Werte runden (1, 2, 5, 10, 20, 50, ...)
        magnitude = 10 ** math.floor(math.log10(spacing)) if spacing > 0 else 1
        for nice in [1, 2, 5, 10]:
            if spacing <= nice * magnitude:
                spacing = nice * magnitude
                break
        grid_size = spacing * 20
        self._draw_grid(size=grid_size, spacing=spacing)
    
    def _draw_axes(self, length=50):
        for axis_name in ['axis_x_org', 'axis_y_org', 'axis_z_org']:
            _safe_remove_actor(self.plotter, axis_name, "axes cleanup")
        self.plotter.add_mesh(pv.Line((0,0,0),(length,0,0)), color='#ff4444', line_width=3, name='axis_x_org')
        self.plotter.add_mesh(pv.Line((0,0,0),(0,length,0)), color='#44ff44', line_width=3, name='axis_y_org')
        self.plotter.add_mesh(pv.Line((0,0,0),(0,0,length)), color='#4444ff', line_width=3, name='axis_z_org')

    # ==================== CONSTRUCTION PLANES ====================
    def render_construction_planes(self, planes):
        """Rendert Konstruktionsebenen im Viewport.

        Args:
            planes: Liste von ConstructionPlane-Objekten
        """
        # Alte Plane-Actors entfernen
        for name in list(self._construction_plane_actors.keys()):
            _safe_remove_actor(self.plotter, name, "construction plane cleanup")
        self._construction_plane_actors.clear()

        for cp in planes:
            if not cp.visible:
                continue
            actor_name = f"cp_{cp.id}"
            try:
                import numpy as np
                origin = np.array(cp.origin, dtype=float)
                normal = np.array(cp.normal, dtype=float)
                x_dir = np.array(cp.x_dir, dtype=float)
                plane_mesh = pv.Plane(
                    center=origin,
                    direction=normal,
                    i_size=150,
                    j_size=150,
                    i_resolution=1,
                    j_resolution=1,
                )
                self.plotter.add_mesh(
                    plane_mesh,
                    color='#bb88dd',
                    opacity=0.15,
                    name=actor_name,
                    pickable=False,
                )
                # Rand-Linien für bessere Sichtbarkeit
                edge_name = f"cp_edge_{cp.id}"
                edges = plane_mesh.extract_feature_edges(
                    boundary_edges=True, feature_edges=False,
                    manifold_edges=False, non_manifold_edges=False,
                )
                self.plotter.add_mesh(
                    edges, color='#bb88dd', opacity=0.4,
                    line_width=1, name=edge_name, pickable=False,
                )
                self._construction_plane_actors[actor_name] = cp.id
                self._construction_plane_actors[edge_name] = cp.id
            except Exception as e:
                from loguru import logger
                logger.warning(f"Konstruktionsebene '{cp.name}' konnte nicht gerendert werden: {e}")

        try:
            self.plotter.update()
        except Exception as e:
            _log_suppressed_exception("construction planes update", e)

    def set_construction_plane_visibility(self, plane_id, visible):
        """Setzt die Sichtbarkeit einer Konstruktionsebene."""
        for actor_name, pid in self._construction_plane_actors.items():
            if pid == plane_id:
                try:
                    if actor_name in self.plotter.renderer.actors:
                        self.plotter.renderer.actors[actor_name].SetVisibility(visible)
                except Exception as e:
                    _log_suppressed_exception(f"construction plane visibility for {actor_name}", e)
        try:
            self.plotter.update()
        except Exception as e:
            _log_suppressed_exception("construction plane visibility update", e)

    # ==================== REVOLVE MODE ====================

    def set_revolve_mode(self, enabled):
        """Aktiviert/deaktiviert den interaktiven Revolve-Modus."""
        self.revolve_mode = enabled
        if enabled:
            self._revolve_selected_faces = []
            self._draw_selectable_faces_from_detector()

            # FIX: VTK Picker braucht echten Render für aktuellen Depth-Buffer
            try:
                self.plotter.render()
                if hasattr(self.plotter, 'render_window') and self.plotter.render_window:
                    self.plotter.render_window.Render()
            except Exception as e:
                logger.debug(f"Force render failed: {e}")
                request_render(self.plotter, immediate=True)
        else:
            self._revolve_selected_faces = []
            self.clear_revolve_preview()
            self._clear_face_actors()
            request_render(self.plotter)

    def show_revolve_preview(self, angle, axis, operation="New Body"):
        """VTK-basierte Revolve-Preview um Standard-Achse."""
        self.clear_revolve_preview()
        self._revolve_angle = angle
        self._revolve_axis = axis

        if not self._revolve_selected_faces or abs(angle) < 0.1:
            return

        try:
            import pyvista as pv

            preview_meshes = []
            for fid in self._revolve_selected_faces:
                face = next((f for f in self.detector.selection_faces if f.id == fid), None)
                if not face or face.display_mesh is None:
                    continue

                mesh = face.display_mesh.copy()

                # Transform mesh so revolve axis aligns with Z,
                # then use extrude_rotate, then transform back
                axis_vec = np.array(axis, dtype=float)
                axis_len = np.linalg.norm(axis_vec)
                if axis_len < 1e-9:
                    continue
                axis_vec = axis_vec / axis_len

                # Build rotation matrix to align axis_vec → Z
                z = np.array([0.0, 0.0, 1.0])
                if np.allclose(axis_vec, z):
                    rot_matrix = np.eye(4)
                elif np.allclose(axis_vec, -z):
                    rot_matrix = np.eye(4)
                    rot_matrix[0, 0] = -1
                    rot_matrix[2, 2] = -1
                else:
                    v = np.cross(axis_vec, z)
                    s = np.linalg.norm(v)
                    c = np.dot(axis_vec, z)
                    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
                    R = np.eye(3) + vx + vx @ vx * (1 - c) / (s * s)
                    rot_matrix = np.eye(4)
                    rot_matrix[:3, :3] = R

                # Apply forward transform
                mesh.transform(rot_matrix, inplace=True)

                # extrude_rotate rotates around Z-axis through origin
                try:
                    revolved = mesh.extrude_rotate(
                        resolution=36,
                        angle=angle,
                        capping=True,
                    )
                    # Apply inverse transform
                    inv_matrix = np.linalg.inv(rot_matrix)
                    revolved.transform(inv_matrix, inplace=True)
                    preview_meshes.append(revolved)
                except Exception as e:
                    logger.debug(f"Revolve preview extrude_rotate failed: {e}")
                    continue

            if preview_meshes:
                combined = preview_meshes[0]
                for m in preview_meshes[1:]:
                    combined = combined.merge(m)

                op_colors = {
                    "New Body": '#6699ff', "Join": '#66ff66',
                    "Cut": '#ff6666', "Intersect": '#ffaa66'
                }
                col = op_colors.get(operation, '#6699ff')
                self.plotter.add_mesh(combined, color=col, opacity=0.5,
                                      name='revolve_preview', pickable=False)
                self._revolve_preview_actor = 'revolve_preview'
                request_render(self.plotter)
        except Exception as e:
            logger.error(f"Revolve preview error: {e}")

    def clear_revolve_preview(self):
        """Entfernt die Revolve-Preview."""
        if self._revolve_preview_actor:
            _safe_remove_actor(self.plotter, self._revolve_preview_actor, "revolve preview cleanup")
            self._revolve_preview_actor = None

    # ==================== HOLE MODE ====================
    def set_hole_mode(self, enabled):
        """Aktiviert/deaktiviert den interaktiven Hole-Modus."""
        self.hole_mode = enabled
        if enabled:
            self._hole_position = None
            self._hole_normal = None
            self._hole_body_id = None
            # Enable body face picking (X-ray not needed, we pick on body surface)
        else:
            self.clear_hole_preview()
            self._hole_position = None
            self._hole_normal = None
            self._hole_body_id = None

    def show_hole_preview(self, position, normal, diameter, depth):
        """Zeigt Hole-Preview als halbtransparenten Zylinder."""
        self.clear_hole_preview()
        if position is None or normal is None:
            return

        try:
            import pyvista as pv
            radius = diameter / 2.0
            actual_depth = depth if depth > 0 else 100.0  # through all = large

            # Create cylinder along Z, then rotate to match normal
            cyl = pv.Cylinder(
                center=(0, 0, -actual_depth / 2.0),
                direction=(0, 0, -1),
                radius=radius,
                height=actual_depth,
                resolution=32,
                capping=True,
            )

            # Align cylinder direction to face normal (inverted = drilling into face)
            n = np.array(normal, dtype=float)
            n_len = np.linalg.norm(n)
            if n_len < 1e-9:
                return
            n = n / n_len

            # Build transform: translate to position, align -Z to -normal (drill into surface)
            z = np.array([0.0, 0.0, -1.0])
            target = -n  # drill into surface

            if np.allclose(z, target):
                rot = np.eye(4)
            elif np.allclose(z, -target):
                rot = np.eye(4)
                rot[0, 0] = -1
                rot[2, 2] = -1
            else:
                v = np.cross(z, target)
                s = np.linalg.norm(v)
                c = np.dot(z, target)
                vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
                R = np.eye(3) + vx + vx @ vx * (1 - c) / (s * s)
                rot = np.eye(4)
                rot[:3, :3] = R

            cyl.transform(rot, inplace=True)

            # Translate to position
            pos = np.array(position, dtype=float)
            cyl.points += pos

            self.plotter.add_mesh(cyl, color='#ff6666', opacity=0.45,
                                  name='hole_preview', pickable=False)
            self._hole_preview_actor = 'hole_preview'
            self._hole_position = tuple(position)
            self._hole_normal = tuple(normal)
            self._hole_diameter = diameter
            self._hole_depth = depth
            request_render(self.plotter)
        except Exception as e:
            logger.error(f"Hole preview error: {e}")

    def clear_hole_preview(self):
        """Entfernt die Hole-Preview."""
        if self._hole_preview_actor:
            _safe_remove_actor(self.plotter, self._hole_preview_actor, "hole preview cleanup")
            self._hole_preview_actor = None

    # ==================== THREAD MODE ====================
    def set_thread_mode(self, enabled):
        """Aktiviert/deaktiviert den interaktiven Thread-Modus für zylindrische Flächen."""
        self.thread_mode = enabled
        if enabled:
            self._thread_position = None
            self._thread_direction = None
            self._thread_body_id = None
            self._thread_is_internal = False
        else:
            self.clear_thread_preview()
            self._thread_position = None
            self._thread_direction = None
            self._thread_body_id = None

    def show_thread_preview(self, position, direction, diameter, depth, is_internal=False):
        """Zeigt Thread-Preview als Zylinder mit Spirallinie."""
        self.clear_thread_preview()
        if position is None or direction is None:
            return

        try:
            import pyvista as pv
            radius = diameter / 2.0

            # Create cylinder along the axis direction
            cyl = pv.Cylinder(
                center=(0, 0, depth / 2.0),
                direction=(0, 0, 1),
                radius=radius,
                height=depth,
                resolution=32,
                capping=True,
            )

            # Align cylinder to thread direction
            d = np.array(direction, dtype=float)
            d_len = np.linalg.norm(d)
            if d_len < 1e-9:
                return
            d = d / d_len

            # Build rotation from Z to direction
            z = np.array([0.0, 0.0, 1.0])
            if np.allclose(z, d):
                rot = np.eye(4)
            elif np.allclose(z, -d):
                rot = np.eye(4)
                rot[0, 0] = -1
                rot[2, 2] = -1
            else:
                v = np.cross(z, d)
                s = np.linalg.norm(v)
                c = np.dot(z, d)
                vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
                R = np.eye(3) + vx + vx @ vx * (1 - c) / (s * s)
                rot = np.eye(4)
                rot[:3, :3] = R

            cyl.transform(rot, inplace=True)

            # Translate to position
            pos = np.array(position, dtype=float)
            cyl.points += pos

            # Different color for internal vs external threads
            color = '#66aaff' if not is_internal else '#ffaa66'

            self.plotter.add_mesh(cyl, color=color, opacity=0.45,
                                  name='thread_preview', pickable=False)
            self._thread_preview_actor = 'thread_preview'
            self._thread_position = tuple(position)
            self._thread_direction = tuple(direction)
            self._thread_diameter = diameter
            self._thread_depth = depth
            self._thread_is_internal = is_internal
            request_render(self.plotter)
        except Exception as e:
            logger.error(f"Thread preview error: {e}")

    def clear_thread_preview(self):
        """Entfernt die Thread-Preview."""
        if self._thread_preview_actor:
            _safe_remove_actor(self.plotter, self._thread_preview_actor, "thread preview cleanup")
            self._thread_preview_actor = None

    def _detect_cylindrical_face(self, body_id: str, cell_id: int, click_pos) -> Optional[Tuple[float, Tuple[float, float, float], bool]]:
        """
        Erkennt ob eine Face zylindrisch ist und gibt Durchmesser, Achsrichtung und Typ zurück.

        Args:
            body_id: ID des Bodies
            cell_id: Cell-ID im Mesh (approximiert Face-Index)
            click_pos: Klick-Position (x, y, z)

        Returns:
            Tuple (diameter, axis_direction, is_internal) oder None wenn keine Zylinderfläche
        """
        try:
            from OCP.BRepAdaptor import BRepAdaptor_Surface
            from OCP.GeomAbs import GeomAbs_Cylinder
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
            from OCP.TopoDS import TopoDS
            from OCP.BRep import BRep_Tool
            from OCP.BRepGProp import BRepGProp
            from OCP.GProp import GProp_GProps

            # Finde Body
            body_data = self.bodies.get(body_id)
            if not body_data:
                logger.warning(f"Thread: Body {body_id} nicht gefunden")
                return None

            # Hole das Solid vom Body
            body_ref = body_data.get('body_ref') or body_data.get('body')
            if not body_ref or not hasattr(body_ref, '_build123d_solid'):
                logger.warning(f"Thread: Body {body_id} hat kein Solid")
                return None

            solid = body_ref._build123d_solid
            if solid is None:
                return None

            ocp_shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

            # Iteriere über alle Faces und finde die nächste zur Klick-Position
            explorer = TopExp_Explorer(ocp_shape, TopAbs_FACE)
            click_pt = np.array(click_pos)
            best_face = None
            best_dist = float('inf')
            best_idx = -1
            face_idx = 0

            while explorer.More():
                face = TopoDS.Face_s(explorer.Current())

                # Berechne Face-Zentrum
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, props)
                center = props.CentreOfMass()
                face_center = np.array([center.X(), center.Y(), center.Z()])

                dist = np.linalg.norm(face_center - click_pt)
                if dist < best_dist:
                    best_dist = dist
                    best_face = face
                    best_idx = face_idx

                explorer.Next()
                face_idx += 1

            if best_face is None:
                logger.warning("Thread: Keine Face gefunden")
                return None

            # Analysiere die gefundene Face
            adaptor = BRepAdaptor_Surface(best_face)
            surf_type = adaptor.GetType()

            if surf_type != GeomAbs_Cylinder:
                logger.info(f"Thread: Face {best_idx} ist keine Zylinderfläche (Typ: {surf_type})")
                return None

            # Extrahiere Zylinderparameter
            cyl = adaptor.Cylinder()
            axis = cyl.Axis()
            loc = axis.Location()
            direction = axis.Direction()

            axis_dir = (direction.X(), direction.Y(), direction.Z())
            radius = cyl.Radius()
            diameter = radius * 2.0

            # Bestimme ob Internal (Loch) oder External (Bolzen)
            # REVERSED = Loch, FORWARD = Bolzen
            is_internal = (best_face.Orientation() == TopAbs_REVERSED)

            logger.info(f"Thread: Zylinderfläche erkannt - D={diameter:.2f}mm, "
                       f"{'Internal (Loch)' if is_internal else 'External (Bolzen)'}")

            return (diameter, axis_dir, is_internal)

        except Exception as e:
            logger.error(f"Thread: Fehler bei Zylindererkennung: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ==================== DRAFT MODE ====================
    def set_draft_mode(self, enabled):
        """Aktiviert/deaktiviert den interaktiven Draft-Modus."""
        self.draft_mode = enabled
        if enabled:
            self._draft_selected_faces = []
            self._draft_body_id = None

            # FIX: VTK Picker braucht echten Render für aktuellen Depth-Buffer
            try:
                self.plotter.render()
                if hasattr(self.plotter, 'render_window') and self.plotter.render_window:
                    self.plotter.render_window.Render()
            except Exception as e:
                logger.debug(f"Force render failed: {e}")
                request_render(self.plotter, immediate=True)
        else:
            self._draft_selected_faces = []
            self._draft_body_id = None
            self.clear_draft_preview()
            self._clear_body_face_highlight()

    def _toggle_draft_face(self, face_data):
        """Toggle Face in Draft-Selektion mit full-face orange Highlight."""
        new_normal = face_data.get('normal', (0, 0, 0))
        body_id = face_data.get('body_id')

        # First face sets the body
        if not self._draft_selected_faces:
            self._draft_body_id = body_id
        elif body_id != self._draft_body_id:
            logger.warning("Draft: Nur Faces vom gleichen Body erlaubt")
            return

        # Toggle: deselect if same face already selected (by cell_ids overlap)
        new_cells = set(face_data.get('cell_ids', []))
        for i, f in enumerate(self._draft_selected_faces):
            existing_cells = set(f.get('cell_ids', []))
            if new_cells and existing_cells and new_cells & existing_cells:
                self._draft_selected_faces.pop(i)
                self._update_draft_face_highlights()
                return

        self._draft_selected_faces.append(face_data)
        self._update_draft_face_highlights()

    def _update_draft_face_highlights(self):
        """Orange full-face Highlights für Draft-selektierte Faces."""
        self._clear_draft_face_highlights()

        for i, face_data in enumerate(self._draft_selected_faces):
            try:
                mesh = face_data.get('mesh')
                cell_ids = face_data.get('cell_ids', [])

                if mesh is not None and cell_ids:
                    face_mesh = mesh.extract_cells(cell_ids)
                    face_normal = face_data.get('normal', (0, 0, 1))
                    normal_arr = np.array(face_normal)
                    norm_len = np.linalg.norm(normal_arr)
                    if norm_len > 1e-10:
                        normal_arr = normal_arr / norm_len
                    face_mesh_copy = face_mesh.copy()
                    face_mesh_copy.points = face_mesh_copy.points + normal_arr * 0.3

                    self.plotter.add_mesh(
                        face_mesh_copy,
                        color='orange',
                        opacity=0.7,
                        name=f'draft_face_highlight_{i}',
                        pickable=False,
                        show_edges=True,
                        edge_color='darkorange',
                        line_width=2
                    )
            except Exception as e:
                logger.debug(f"Draft Face Highlight Error: {e}")

        request_render(self.plotter)

    def _clear_draft_face_highlights(self):
        """Entfernt Draft-Face-Highlights."""
        for i in range(50):
            try:
                self.plotter.remove_actor(f'draft_face_highlight_{i}')
            except Exception as e:
                logger.debug(f"[viewport] Fehler beim Entfernen draft_face_highlight_{i}: {e}")

    def _show_draft_preview_mesh(self, mesh):
        """Zeigt halbtransparentes Draft-Ergebnis als Live-Preview."""
        try:
            self.plotter.remove_actor('draft_preview')
        except Exception:
            pass
        try:
            self._draft_preview_actor = self.plotter.add_mesh(
                mesh,
                color='#50bb50',
                opacity=0.4,
                name='draft_preview',
                pickable=False,
                show_edges=True,
                edge_color='#309030',
                line_width=1
            )
            request_render(self.plotter)
        except Exception as e:
            logger.debug(f"Draft preview mesh error: {e}")

    def clear_draft_preview(self):
        """Entfernt alle Draft-Visualisierungen."""
        self._clear_draft_face_highlights()
        try:
            self.plotter.remove_actor('draft_preview')
        except Exception:
            pass
        self._draft_preview_actor = None

    # ==================== SPLIT MODE ====================
    def set_split_mode(self, enabled):
        """Aktiviert/deaktiviert den interaktiven Split-Modus."""
        self.split_mode = enabled
        if enabled:
            self._split_body_id = None
            self._split_bb = None
            self._split_dragging = False
        else:
            self._split_body_id = None
            self._split_bb = None
            self._split_dragging = False
            self.clear_split_preview()

    def set_split_body(self, body_id):
        """Body setzen und Schnittebene auf Mitte der Bounding Box."""
        import numpy as np
        self._split_body_id = body_id
        body_data = self.bodies.get(body_id)
        if body_data is None:
            return

        mesh = body_data.get('mesh')
        if mesh is None:
            return

        bounds = mesh.bounds  # (xmin, xmax, ymin, ymax, zmin, zmax)
        self._split_bb = bounds

        # Default position: center of BB along current axis
        axis_map = {"XY": 4, "XZ": 2, "YZ": 0}  # index into bounds (min)
        idx = axis_map.get(self._split_plane_axis, 4)
        center = (bounds[idx] + bounds[idx + 1]) / 2.0
        self._split_position = center
        self._draw_split_plane()
        return center

    def update_split_plane(self, axis, position):
        """Aktualisiert Schnittebene."""
        self._split_plane_axis = axis
        self._split_position = position
        self._draw_split_plane()

    def _draw_split_plane(self):
        """Rendert die halbtransparente Schnittebene."""
        import numpy as np
        # Remove old plane
        for name in ['split_plane', 'split_plane_edge']:
            try:
                self.plotter.remove_actor(name)
            except Exception:
                pass

        if self._split_bb is None:
            return

        bounds = self._split_bb
        # Compute plane size from BB diagonal
        dx = bounds[1] - bounds[0]
        dy = bounds[3] - bounds[2]
        dz = bounds[5] - bounds[4]
        diag = max(dx, dy, dz) * 1.5
        if diag < 10:
            diag = 50

        pos = self._split_position
        axis = self._split_plane_axis

        if axis == "XY":
            center = ((bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2, pos)
            direction = np.array([0.0, 0.0, 1.0])
            rot_axis = np.array([1.0, 0.0, 0.0])
        elif axis == "XZ":
            center = ((bounds[0] + bounds[1]) / 2, pos, (bounds[4] + bounds[5]) / 2)
            direction = np.array([0.0, 1.0, 0.0])
            rot_axis = np.array([1.0, 0.0, 0.0])
        else:  # YZ
            center = (pos, (bounds[2] + bounds[3]) / 2, (bounds[4] + bounds[5]) / 2)
            direction = np.array([1.0, 0.0, 0.0])
            rot_axis = np.array([0.0, 1.0, 0.0])

        # Apply angle rotation (Rodrigues)
        angle_deg = self._split_angle
        if abs(angle_deg) > 0.01:
            angle_rad = np.radians(angle_deg)
            k = rot_axis
            c, s = np.cos(angle_rad), np.sin(angle_rad)
            direction = direction * c + np.cross(k, direction) * s + k * np.dot(k, direction) * (1 - c)
            direction = direction / (np.linalg.norm(direction) + 1e-12)

        try:
            plane_mesh = pv.Plane(
                center=center,
                direction=direction,
                i_size=diag,
                j_size=diag,
                i_resolution=1,
                j_resolution=1,
            )
            self.plotter.add_mesh(
                plane_mesh,
                color='#5599dd',
                opacity=0.25,
                name='split_plane',
                pickable=False,
            )
            edges = plane_mesh.extract_feature_edges(
                boundary_edges=True, feature_edges=False,
                manifold_edges=False, non_manifold_edges=False,
            )
            self.plotter.add_mesh(
                edges, color='#5599dd', opacity=0.6,
                line_width=2, name='split_plane_edge',
                pickable=False,
            )
            request_render(self.plotter)
        except Exception as e:
            logger.debug(f"Split plane draw error: {e}")

    def show_split_preview(self, above_mesh, below_mesh):
        """Zeigt beide Hälften als farbige Preview."""
        self.clear_split_preview_meshes()
        try:
            if above_mesh is not None:
                self.plotter.add_mesh(
                    above_mesh, color='#00cccc', opacity=0.45,
                    name='split_preview_above', pickable=False,
                    show_edges=True, edge_color='#009999', line_width=1
                )
            if below_mesh is not None:
                self.plotter.add_mesh(
                    below_mesh, color='#cc44cc', opacity=0.45,
                    name='split_preview_below', pickable=False,
                    show_edges=True, edge_color='#993399', line_width=1
                )
            request_render(self.plotter)
        except Exception as e:
            logger.debug(f"Split preview error: {e}")

    def clear_split_preview_meshes(self):
        """Entfernt nur die Preview-Meshes (nicht die Ebene)."""
        for name in ['split_preview_above', 'split_preview_below']:
            try:
                self.plotter.remove_actor(name)
            except Exception:
                pass

    def clear_split_preview(self):
        """Entfernt alle Split-Visualisierungen."""
        self.clear_split_preview_meshes()
        for name in ['split_plane', 'split_plane_edge']:
            try:
                self.plotter.remove_actor(name)
            except Exception:
                pass

    def handle_split_mouse_press(self, x, y):
        """Startet Split-Plane Drag oder Body-Click."""
        if not self.split_mode:
            return False

        # If no body selected yet, use hovered_body_face from hover
        if self._split_body_id is None:
            if self.hovered_body_face is not None:
                body_id = self.hovered_body_face[0]
                logger.debug(f"Split: Body '{body_id}' geklickt")
                self.split_body_clicked.emit(body_id)
                return True
            return False

        # Body already selected — start drag
        from PySide6.QtCore import QPoint
        self._split_dragging = True
        self._split_drag_start = QPoint(x, y)
        self._split_drag_start_pos = self._split_position
        return True

    def handle_split_mouse_move(self, x, y):
        """Drag für Split-Position."""
        if not self._split_dragging or self._split_drag_start is None:
            return False
        import numpy as np

        dy = -(y - self._split_drag_start.y())
        scale = self._get_pixel_to_world_scale(
            np.array([0, 0, self._split_position])
        ) if hasattr(self, '_get_pixel_to_world_scale') else 0.5
        delta = dy * scale

        new_pos = self._split_drag_start_pos + delta
        self._split_position = new_pos
        self._draw_split_plane()
        self.split_drag_changed.emit(new_pos)
        return True

    def handle_split_mouse_release(self):
        """Beendet Split-Drag."""
        if not self._split_dragging:
            return False
        self._split_dragging = False
        self._split_drag_start = None
        return True

    # ==================== OFFSET PLANE MODE ====================
    def set_offset_plane_mode(self, enabled):
        """Aktiviert/deaktiviert den interaktiven Offset-Plane-Modus."""
        self.offset_plane_mode = enabled
        if enabled:
            # FIX: VTK Picker braucht echten Render für aktuellen Depth-Buffer
            try:
                self.plotter.render()
                if hasattr(self.plotter, 'render_window') and self.plotter.render_window:
                    self.plotter.render_window.Render()
            except Exception as e:
                logger.debug(f"Force render failed: {e}")
                request_render(self.plotter, immediate=True)
        else:
            self.clear_offset_plane_preview()
            self._offset_plane_dragging = False
            self._offset_plane_base_origin = None
            self._offset_plane_base_normal = None

    def set_offset_plane_base(self, origin, normal):
        """Setzt die Basis-Ebene für den Offset."""
        import numpy as np
        self._offset_plane_base_origin = np.array(origin, dtype=float)
        n = np.array(normal, dtype=float)
        norm_len = np.linalg.norm(n)
        if norm_len > 1e-12:
            n = n / norm_len
        self._offset_plane_base_normal = n
        self._offset_plane_offset = 0.0
        self._draw_offset_plane_preview(0.0)

    def update_offset_plane_preview(self, offset):
        """Aktualisiert die Preview-Ebene mit neuem Offset."""
        self._offset_plane_offset = offset
        self._draw_offset_plane_preview(offset)

    def _draw_offset_plane_preview(self, offset):
        """Rendert die halbtransparente Preview-Ebene mit Gizmo-Pfeil."""
        if self._offset_plane_base_origin is None:
            return
        import numpy as np
        # Alte Actors entfernen
        self.clear_offset_plane_preview()

        center = self._offset_plane_base_origin + self._offset_plane_base_normal * offset
        try:
            # Preview-Ebene
            plane_mesh = pv.Plane(
                center=center,
                direction=self._offset_plane_base_normal,
                i_size=200,
                j_size=200,
                i_resolution=1,
                j_resolution=1,
            )
            self._offset_plane_preview_actor = 'offset_plane_preview'
            self.plotter.add_mesh(
                plane_mesh,
                color='#bb88dd',
                opacity=0.25,
                name='offset_plane_preview',
                pickable=False,
            )
            # Rand-Linien
            edges = plane_mesh.extract_feature_edges(
                boundary_edges=True, feature_edges=False,
                manifold_edges=False, non_manifold_edges=False,
            )
            self._offset_plane_edge_actor = 'offset_plane_preview_edge'
            self.plotter.add_mesh(
                edges, color='#bb88dd', opacity=0.6,
                line_width=2, name='offset_plane_preview_edge',
                pickable=False,
            )
            
            # === GIZMO-PFEIL entlang der Normalen ===
            arrow_start = center
            arrow_end = center + self._offset_plane_base_normal * 50  # 50mm Pfeil
            arrow_line = pv.Line(arrow_start, arrow_end)
            
            # Pfeil-Spitze (Kegel)
            arrow_tip = pv.Cone(
                center=arrow_end + self._offset_plane_base_normal * 5,
                direction=self._offset_plane_base_normal,
                height=10,
                radius=3,
                resolution=16
            )
            
            self.plotter.add_mesh(
                arrow_line, color='#ffcc00', line_width=4,
                name='offset_plane_arrow_line', pickable=False
            )
            self.plotter.add_mesh(
                arrow_tip, color='#ffcc00', opacity=0.9,
                name='offset_plane_arrow_tip', pickable=True  # Pickable für Hover!
            )
            
            # Speichere Pfeil-Daten für Hover-Detection
            # WICHTIG: Die Spitze (Cone) ist bei arrow_end + normal*5
            arrow_tip_center = arrow_end + self._offset_plane_base_normal * 5
            self._offset_plane_arrow_center = arrow_tip_center
            self._offset_plane_arrow_radius = 20  # Größerer Radius für bessere Trefferquote
            
            self.plotter.update()
        except Exception as e:
            from loguru import logger
            logger.warning(f"Offset Plane Preview Fehler: {e}")

    def clear_offset_plane_preview(self):
        """Entfernt die Preview-Ebene und den Gizmo-Pfeil."""
        for name in ['offset_plane_preview', 'offset_plane_preview_edge',
                     'offset_plane_arrow_line', 'offset_plane_arrow_tip']:
            try:
                self.plotter.remove_actor(name)
            except Exception:
                pass
        self._offset_plane_preview_actor = None
        self._offset_plane_edge_actor = None
        self._offset_plane_arrow_center = None
    
    def _update_offset_plane_transform(self, offset):
        """
        Aktualisiert die Position durch komplettes Neuerstellen (korrigiert Pfeil-Position).
        PERFORMANCE: Wir verwenden Request Render Queue statt direktem Render.
        """
        try:
            self._draw_offset_plane_preview(offset)
        except Exception:
            pass

    def handle_offset_plane_mouse_press(self, x, y):
        """Startet Drag für Offset."""
        if not self.offset_plane_mode or self._offset_plane_base_origin is None:
            return False
        from PySide6.QtCore import QPoint
        
        # WICHTIG: Prüfe ob der Benutzer auf den Pfeil/Handle geklickt hat
        if not self._is_point_on_offsetplane_handle(x, y):
            return False  # Nicht auf das Gizmo geklickt - Event nicht behandeln
        
        # Speichere Start-Position für Screen-Space Dragging
        self._drag_last_screen = (x, y)
        
        self._offset_plane_dragging = True
        self._offset_plane_drag_start = QPoint(x, y)
        return True

    def _raycast_to_offsetplane_line(self, screen_x, screen_y):
        """Raycast von Screen-Koordinaten auf die Normalen-Linie des OffsetPlanes."""
        try:
            # Hole Camera-Position und Ray-Richtung
            camera = self.plotter.camera
            if camera is None:
                return None
            
            # Ray durch Maus-Position
            ray_origin = np.array(camera.GetPosition())
            
            # Berechne Ray-Richtung durch Unproject
            renderer = self.plotter.renderer
            display_point = [screen_x, screen_y, 0.0]
            world_point = [0.0, 0.0, 0.0]
            renderer.SetDisplayPoint(display_point)
            renderer.DisplayToWorld()
            world_at_display = renderer.GetWorldPoint()
            
            # Ray-Richtung
            near_point = np.array([world_at_display[0], world_at_display[1], world_at_display[2]])
            ray_dir = near_point - ray_origin
            ray_dir = ray_dir / np.linalg.norm(ray_dir)
            
            # Linie: base_origin + t * normal
            # Ray: ray_origin + s * ray_dir
            # Schnittpunkt wenn beide gleich sind
            
            # Berechne kürzeste Distanz zwischen Ray und Normalen-Linie
            line_origin = self._offset_plane_base_origin
            line_dir = self._offset_plane_base_normal
            
            # Cross product für kürzeste Verbindung
            w0 = ray_origin - line_origin
            a = np.dot(line_dir, line_dir)  # = 1 (normalisiert)
            b = np.dot(line_dir, ray_dir)
            c = np.dot(ray_dir, ray_dir)    # = 1 (normalisiert)
            d = np.dot(line_dir, w0)
            e = np.dot(ray_dir, w0)
            
            denom = a * c - b * b
            if abs(denom) < 1e-6:
                return None  # Parallel
            
            # Parameter für kürzeste Verbindung
            t = (b * e - c * d) / denom  # Auf Normalen-Linie
            
            # Begrenze t auf sinnvollen Bereich (z.B. -500 bis +500mm)
            t = max(-500, min(500, t))
            
            return line_origin + t * line_dir
            
        except Exception as e:
            return None

    def handle_offset_plane_mouse_move(self, x, y):
        """Aktualisiert Offset durch Screen-Space Projektion (wie Transform-Gizmo)."""
        if not self._offset_plane_dragging:
            # Hover-Modus: Prüfe ob über Pfeil
            return self._update_offsetplane_hover_cursor(x, y)
        
        # Screen-Space Projektion wie Transform-Gizmo (nicht Raycast!)
        dx_screen = x - self._drag_last_screen[0]
        dy_screen = y - self._drag_last_screen[1]
        self._drag_last_screen = (x, y)
        
        try:
            renderer = self.plotter.renderer
            center = self._offset_plane_base_origin + self._offset_plane_base_normal * self._offset_plane_offset
            
            # Projiziere Center auf Screen
            renderer.SetWorldPoint(*center, 1.0)
            renderer.WorldToDisplay()
            center_screen = np.array(renderer.GetDisplayPoint()[:2])
            
            # Projiziere Punkt entlang Normalen auf Screen
            axis_point = center + self._offset_plane_base_normal * 100
            renderer.SetWorldPoint(*axis_point, 1.0)
            renderer.WorldToDisplay()
            axis_screen = np.array(renderer.GetDisplayPoint()[:2])
            
            # Screen-Achsen-Richtung
            screen_axis_dir = axis_screen - center_screen
            screen_axis_len = np.linalg.norm(screen_axis_dir)
            
            if screen_axis_len > 1:
                screen_axis_dir = screen_axis_dir / screen_axis_len
                # Maus-Bewegung auf Achse projizieren
                screen_movement = np.array([dx_screen, -dy_screen])
                movement_along_axis = np.dot(screen_movement, screen_axis_dir)
                # Sensitivity: wie viel 3D-Bewegung pro Screen-Pixel
                sensitivity = 100.0 / screen_axis_len
                delta_offset = movement_along_axis * sensitivity
            else:
                delta_offset = 0
            
            new_offset = self._offset_plane_offset + delta_offset
            new_offset = max(-1000, min(1000, new_offset))  # Begrenzung
            
            self._offset_plane_offset = new_offset
            self._update_offset_plane_transform(new_offset)
            return True
            
        except Exception:
            return False
    
    def _update_offsetplane_hover_cursor(self, x, y):
        """Ändert Cursor wenn über Gizmo-Pfeil (Raycasting wie Transform-Gizmo)."""
        if not hasattr(self, '_offset_plane_arrow_center') or self._offset_plane_arrow_center is None:
            return False
        
        try:
            # Raycasting wie Transform-Gizmo
            is_hit = self._is_point_on_offsetplane_handle(x, y)
            
            from PySide6.QtCore import Qt
            if is_hit:
                self.plotter.setCursor(Qt.SizeVerCursor)
                return True
            else:
                self.plotter.setCursor(Qt.ArrowCursor)
                return False
        except Exception as e:
            logger.debug(f"[viewport] Fehler beim OffsetPlane Hover Cursor: {e}")
            return False

    def _is_point_on_offsetplane_handle(self, x, y):
        """Prüft ob Punkt (x,y) auf dem Offset-Plane Handle/Pfeil liegt (Raycasting wie Transform-Gizmo)."""
        if not hasattr(self, '_offset_plane_arrow_center') or self._offset_plane_arrow_center is None:
            logger.debug(f"OffsetPlane: Kein Arrow Center (x={x}, y={y})")
            return False
        
        try:
            # Raycasting wie Transform-Gizmo
            ray_origin, ray_dir = self._get_ray_for_offsetplane((x, y))
            if ray_origin is None:
                return False
            
            # Prüfe Kollision mit Pfeil-Spitze (Kegel)
            arrow_tip_center = self._offset_plane_arrow_center
            arrow_tip_radius = 5.0  # Radius der Cone-Spitze
            
            # Ray-Sphere Test (vereinfacht für Cone)
            hit, distance = self._ray_intersects_sphere(
                ray_origin, ray_dir, 
                arrow_tip_center, arrow_tip_radius
            )
            
            return hit
            
        except Exception as e:
            return False
            return False
    
    def _get_ray_for_offsetplane(self, screen_pos):
        """Berechnet Ray aus Screen-Position (wie Transform-Gizmo)."""
        try:
            x, y = screen_pos
            renderer = self.plotter.renderer
            height = self.plotter.interactor.height()
            y_flipped = height - y
            
            renderer.SetDisplayPoint(x, y_flipped, 0)
            renderer.DisplayToWorld()
            near = np.array(renderer.GetWorldPoint()[:3])
            
            renderer.SetDisplayPoint(x, y_flipped, 1)
            renderer.DisplayToWorld()
            far = np.array(renderer.GetWorldPoint()[:3])
            
            direction = far - near
            direction = direction / np.linalg.norm(direction)
            
            return near, direction
        except Exception as e:
            logger.debug(f"[viewport] Fehler beim Raycasting für OffsetPlane: {e}")
            return None, None
    
    def _ray_intersects_sphere(self, ray_origin, ray_dir, sphere_center, sphere_radius):
        """Ray-Sphere Intersection Test."""
        oc = ray_origin - sphere_center
        a = np.dot(ray_dir, ray_dir)
        b = 2.0 * np.dot(oc, ray_dir)
        c = np.dot(oc, oc) - sphere_radius * sphere_radius
        discriminant = b * b - 4 * a * c
        
        if discriminant < 0:
            return False, float('inf')
        
        # Nahstes Intersection finden
        sqrt_disc = np.sqrt(discriminant)
        t1 = (-b - sqrt_disc) / (2.0 * a)
        t2 = (-b + sqrt_disc) / (2.0 * a)
        
        t = min(t for t in [t1, t2] if t > 0) if any(t > 0 for t in [t1, t2]) else None
        
        if t is None:
            return False, float('inf')
        
        return True, t

    def handle_offset_plane_mouse_release(self):
        """Beendet Drag und setzt Cursor zurück."""
        if not self._offset_plane_dragging:
            return False
        self._offset_plane_dragging = False
        self._offset_plane_drag_start = None
        # Cursor zurücksetzen
        from PySide6.QtCore import Qt
        self.plotter.setCursor(Qt.ArrowCursor)
        return True

    # ==================== EVENT FILTER ====================
    def eventFilter(self, obj, event):
        if not HAS_PYVISTA: return False
        from PySide6.QtCore import QEvent, Qt, QPoint
        from PySide6.QtWidgets import QApplication

        if self._trace_hint_face_id is not None and not self._is_trace_assist_allowed():
            self.clear_trace_hint()

        # Trace Assist Shortcut: T startet direkt "Create Sketch" auf gehoverter Face.
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_T:
            if self._trace_hint_face_id is not None and self._is_trace_assist_allowed():
                self.create_sketch_requested.emit(int(self._trace_hint_face_id))
                self.clear_trace_hint()
                return True

        # Phase 4: Globales Mouse-Move Throttling (max 60 FPS)
        if event.type() == QEvent.MouseMove:
            current_time = time.time()
            if current_time - self._last_mouse_move_time < self._mouse_move_interval:
                return False  # Event ignorieren, zu schnell
            self._last_mouse_move_time = current_time

        def _event_global_point(evt):
            if hasattr(evt, "globalPosition"):
                gp = evt.globalPosition()
                return gp.toPoint() if hasattr(gp, "toPoint") else QPoint(int(gp.x()), int(gp.y()))
            if hasattr(evt, "globalPos"):
                return evt.globalPos()
            if hasattr(evt, "pos") and hasattr(obj, "mapToGlobal"):
                return obj.mapToGlobal(evt.pos())
            return QPoint(0, 0)

        # P0-2: Right-Click Abort & Background Clear (Welle 6 Consolidated)
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.RightButton:
            # 1. Abort active Drag/Operation immediately on Press
            if self.is_dragging or self._offset_plane_dragging or self._split_dragging:
                self.cancel_drag()
                return True # Consume event (prevent Zoom/Menu start)
            
            if self.extrude_mode:
                self.extrude_cancelled.emit()
                return True
                
            if self.point_to_point_mode:
                self.cancel_point_to_point_mode()
                return True
            
            # Record state for potential "Click on Background" detection (on Release)
            self._right_click_start_pos = event.pos() if hasattr(event, 'pos') else QPoint(0,0)
            self._right_click_start_global_pos = _event_global_point(event)
            self._right_click_start_time = time.time()

            # Fast-path: If right-press is already on background, clear immediately.
            # This keeps deselect behavior reliable even when release events are
            # absorbed by VTK/Qt interaction handling.
            try:
                if hasattr(self, "pick"):
                    local_pos = event.position() if hasattr(event, "position") else event.pos()
                    x, y = int(local_pos.x()), int(local_pos.y())
                    picked_id = self.pick(x, y, selection_filter=self.active_selection_filter)
                    if picked_id == -1:
                        self.clear_selection()
                        self.background_clicked.emit()
                        self._right_click_start_pos = None
                        self._right_click_start_global_pos = None
                        self._right_click_start_time = 0.0
                        return True
            except Exception:
                pass
            
            # Consume press and defer all right-click decisions to release.
            return True

        elif event.type() == QEvent.MouseButtonRelease and event.button() == Qt.RightButton:
            # 2. Handle "Click on Background" -> Deselect
            if self._right_click_start_global_pos is not None:
                current_time = time.time()
                pos = event.pos() if hasattr(event, 'pos') else QPoint(0,0)
                global_pos = _event_global_point(event)
                dist = (global_pos - self._right_click_start_global_pos).manhattanLength()
                duration = current_time - self._right_click_start_time
                
                self._right_click_start_pos = None # Reset
                self._right_click_start_global_pos = None
                self._right_click_start_time = 0.0
                
                # Thresholds for "Click": < 5 pixels move, < 0.3s duration
                if dist < 5 and duration < 0.3:
                    # It was a click!
                    if hasattr(self, "plotter") and hasattr(self.plotter, "interactor"):
                        local_pick_pos = self.plotter.interactor.mapFromGlobal(global_pos)
                    else:
                        local_pick_pos = pos
                    x, y = int(local_pick_pos.x()), int(local_pick_pos.y())
                    
                    try:
                        # Use pick() from PickingMixin
                        if hasattr(self, 'pick'):
                            picked_id = self.pick(x, y, selection_filter=self.active_selection_filter)
                            if picked_id == -1:
                                # Background clicked -> Clear Selection
                                self.clear_selection()
                                self.background_clicked.emit()
                                return True # Consume (no context menu)
                            self._show_context_menu(pos)
                            return True
                    except Exception:
                        pass


        # --- OFFSET PLANE MODE (Muss VOR Transform Mode geprüft werden) ---
        if self.offset_plane_mode:
            event_type = event.type()
            
            if event_type in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseMove):
                pos = event.position() if hasattr(event, 'position') else event.pos()
                screen_pos = (int(pos.x()), int(pos.y()))
                
                # Offset Plane Drag
                if event_type == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                    if self.handle_offset_plane_mouse_press(screen_pos[0], screen_pos[1]):
                        return True
                elif event_type == QEvent.MouseMove and self._offset_plane_dragging:
                    if self.handle_offset_plane_mouse_move(screen_pos[0], screen_pos[1]):
                        # Signal an MainWindow für Panel-Sync
                        if hasattr(self, 'offset_plane_drag_changed'):
                            self.offset_plane_drag_changed.emit(self._offset_plane_offset)
                        return True
                elif event_type == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                    if self.handle_offset_plane_mouse_release():
                        return True
                elif event_type == QEvent.MouseMove:
                    # Hover-Effekt für Cursor
                    if self._update_offsetplane_hover_cursor(screen_pos[0], screen_pos[1]):
                        return True

        # --- TRANSFORM MODE (Onshape-Style Gizmo V2) ---
        if self.is_transform_active():
            event_type = event.type()
            
            # Nur Mouse-Events haben position()
            if event_type in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseMove):
                pos = event.position() if hasattr(event, 'position') else event.pos()
                screen_pos = (int(pos.x()), int(pos.y()))

                # Split Mode Drag / Body-Click
                if self.split_mode:
                    if event_type == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                        if self.handle_split_mouse_press(screen_pos[0], screen_pos[1]):
                            return True
                    elif event_type == QEvent.MouseMove and self._split_dragging:
                        if self.handle_split_mouse_move(screen_pos[0], screen_pos[1]):
                            return True
                    elif event_type == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                        if self.handle_split_mouse_release():
                            return True

                if event_type == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                    if self.handle_transform_mouse_press(screen_pos):
                        return True
                        
                elif event_type == QEvent.MouseMove:
                    if self.handle_transform_mouse_move(screen_pos):
                        return True
                        
                elif event_type == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                    if self.handle_transform_mouse_release(screen_pos):
                        return True
                    
            # NEU: ACHSEN-LOCKING (X/Y/Z Keys während Transform)
            elif event_type == QEvent.KeyPress:
                if event.key() == Qt.Key_Escape:
                    self.hide_transform_gizmo()
                    return True

                # Achsen-Lock mit X/Y/Z Keys
                if self.transform_state:
                    if event.key() == Qt.Key_X:
                        # Toggle X-Achsen-Lock
                        if event.modifiers() & Qt.ShiftModifier:
                            # Shift+X = YZ-Ebene (bewege auf Y und Z)
                            self.transform_state.toggle_plane_lock("YZ")
                            # Visueller Indikator
                            if hasattr(self, '_transform_ctrl') and self._transform_ctrl.gizmo:
                                if self.transform_state.plane_lock == "YZ":
                                    self._transform_ctrl.gizmo.show_plane_constraint_indicator("YZ")
                                else:
                                    self._transform_ctrl.gizmo.hide_constraint_indicators()
                        else:
                            # X = X-Achse
                            self.transform_state.toggle_axis_lock("X")
                            # Visueller Indikator
                            if hasattr(self, '_transform_ctrl') and self._transform_ctrl.gizmo:
                                if self.transform_state.axis_lock == "X":
                                    self._transform_ctrl.gizmo.show_axis_constraint_indicator("X")
                                else:
                                    self._transform_ctrl.gizmo.hide_constraint_indicators()
                        return True

                    elif event.key() == Qt.Key_Y:
                        if event.modifiers() & Qt.ShiftModifier:
                            # Shift+Y = XZ-Ebene
                            self.transform_state.toggle_plane_lock("XZ")
                            # Visueller Indikator
                            if hasattr(self, '_transform_ctrl') and self._transform_ctrl.gizmo:
                                if self.transform_state.plane_lock == "XZ":
                                    self._transform_ctrl.gizmo.show_plane_constraint_indicator("XZ")
                                else:
                                    self._transform_ctrl.gizmo.hide_constraint_indicators()
                        else:
                            self.transform_state.toggle_axis_lock("Y")
                            # Visueller Indikator
                            if hasattr(self, '_transform_ctrl') and self._transform_ctrl.gizmo:
                                if self.transform_state.axis_lock == "Y":
                                    self._transform_ctrl.gizmo.show_axis_constraint_indicator("Y")
                                else:
                                    self._transform_ctrl.gizmo.hide_constraint_indicators()
                        return True

                    elif event.key() == Qt.Key_Z:
                        if event.modifiers() & Qt.ShiftModifier:
                            # Shift+Z = XY-Ebene
                            self.transform_state.toggle_plane_lock("XY")
                            # Visueller Indikator
                            if hasattr(self, '_transform_ctrl') and self._transform_ctrl.gizmo:
                                if self.transform_state.plane_lock == "XY":
                                    self._transform_ctrl.gizmo.show_plane_constraint_indicator("XY")
                                else:
                                    self._transform_ctrl.gizmo.hide_constraint_indicators()
                        else:
                            self.transform_state.toggle_axis_lock("Z")
                            # Visueller Indikator
                            if hasattr(self, '_transform_ctrl') and self._transform_ctrl.gizmo:
                                if self.transform_state.axis_lock == "Z":
                                    self._transform_ctrl.gizmo.show_axis_constraint_indicator("Z")
                                else:
                                    self._transform_ctrl.gizmo.hide_constraint_indicators()
                        return True

                    # NEU: MODALE NUMERISCHE EINGABE (Blender-Style)
                    # Während Drag: Tippe Zahl → Enter zum Anwenden
                    text = event.text()

                    # Ziffern, Dezimalpunkt, Minus-Zeichen
                    if text and (text.isdigit() or text in ['.', '-']):
                        self.transform_state.numeric_input += text
                        self._show_numeric_input_overlay(self.transform_state.numeric_input)
                        return True

                    # Enter: Wert anwenden
                    elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                        if self.transform_state.numeric_input:
                            try:
                                value = float(self.transform_state.numeric_input)
                                self._apply_numeric_transform(value)
                                self.transform_state.numeric_input = ""
                                self._hide_numeric_input_overlay()
                                logger.success(f"Numerischer Wert angewendet: {value}")
                            except ValueError:
                                logger.warning(f"Ungültige Eingabe: {self.transform_state.numeric_input}")
                                self.transform_state.numeric_input = ""
                                self._hide_numeric_input_overlay()
                        return True

                    # Backspace: Letztes Zeichen löschen
                    elif event.key() == Qt.Key_Backspace:
                        if self.transform_state.numeric_input:
                            self.transform_state.numeric_input = self.transform_state.numeric_input[:-1]
                            if self.transform_state.numeric_input:
                                self._show_numeric_input_overlay(self.transform_state.numeric_input)
                            else:
                                self._hide_numeric_input_overlay()
                        return True

        # --- TEXTURE FACE SELECTION MODE ---
        if self.texture_face_mode:
            event_type = event.type()

            # Mouse Move: Face-Hover anzeigen (NUR wenn keine Maustaste gedrückt!)
            if event_type == QEvent.MouseMove:
                buttons = event.buttons()
                if buttons == Qt.NoButton:
                    # Kein Button gedrückt → Hover-Highlight
                    pos = event.position() if hasattr(event, 'position') else event.pos()
                    x, y = int(pos.x()), int(pos.y())
                    self._hover_body_face(x, y)
                # IMMER False zurückgeben damit VTK die Events für Kamera bekommt
                return False

            # NUR Left-Click für Face-Selektion abfangen - ABER NUR wenn Body getroffen!
            if event_type == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    # Nur konsumieren wenn tatsächlich eine Face gehovered ist
                    if self.hovered_body_face is not None:
                        self._click_body_face()
                        return True
                    # Kein Body getroffen → Kamera-Rotation erlauben
                    return False
                # Middle/Right Button: Für Kamera-Kontrolle durchlassen
                return False

            # Mouse Release: Für Kamera durchlassen
            if event_type == QEvent.MouseButtonRelease:
                return False

            if event_type == QEvent.KeyPress:
                if event.key() == Qt.Key_Escape:
                    self.stop_texture_face_mode()
                    return True

            # Alle anderen Events (Wheel, etc.) durchlassen
            return False

        # --- BREP CLEANUP MODE (Face-Picking für Merge) ---
        if getattr(self, '_brep_cleanup_mode', False):
            event_type = event.type()

            if event_type == QEvent.MouseMove:
                buttons = event.buttons()
                if buttons == Qt.NoButton:
                    pos = event.position() if hasattr(event, 'position') else event.pos()
                    x, y = int(pos.x()), int(pos.y())
                    if hasattr(self, '_brep_cleanup_handle_hover'):
                        self._brep_cleanup_handle_hover(x, y)
                return False  # Kamera-Kontrolle erlauben

            if event_type == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    pos = event.position() if hasattr(event, 'position') else event.pos()
                    x, y = int(pos.x()), int(pos.y())
                    # Ctrl-Status vom Event holen für Multi-Select
                    is_multi_select = bool(event.modifiers() & Qt.ControlModifier)
                    if hasattr(self, '_brep_cleanup_handle_click'):
                        self._brep_cleanup_handle_click(x, y, is_multi_select)
                        return True
                return False

            if event_type == QEvent.KeyPress:
                if event.key() == Qt.Key_Escape:
                    if hasattr(self, 'stop_brep_cleanup_mode'):
                        self.stop_brep_cleanup_mode()
                    return True

            return False

        # --- EDGE SELECTION MODE (Fillet/Chamfer) ---
        if self.edge_select_mode:
            if event.type() == QEvent.MouseMove:
                pos = event.position() if hasattr(event, 'position') else event.pos()
                x, y = int(pos.x()), int(pos.y())
                self.handle_edge_mouse_move(x, y)
                return True

            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                pos = event.position() if hasattr(event, 'position') else event.pos()
                x, y = int(pos.x()), int(pos.y())
                is_multi = QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.ShiftModifier)
                if self.handle_edge_click(x, y, is_multi):
                    return True

            if event.type() == QEvent.KeyPress:
                if event.key() == Qt.Key_Escape:
                    self.stop_edge_selection_mode()
                    return True
                # A-Taste: Alle Kanten selektieren
                if event.key() == Qt.Key_A:
                    self.select_all_edges()
                    return True

            return False

        # --- HOLE MODE (Body-Face picking for hole placement) ---
        if self.hole_mode:
            event_type = event.type()

            if event_type == QEvent.MouseMove:
                buttons = event.buttons()
                if buttons == Qt.NoButton:
                    pos = event.position() if hasattr(event, 'position') else event.pos()
                    x, y = int(pos.x()), int(pos.y())
                    self._hover_body_face(x, y)
                return False  # Let VTK handle camera

            if event_type == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    if self.hovered_body_face is not None:
                        self._click_body_face()
                        return True
                    return False
                return False

            if event_type == QEvent.MouseButtonRelease:
                return False

            return False

        # --- THREAD MODE (Body-Face picking for thread on cylindrical faces) ---
        if self.thread_mode:
            event_type = event.type()

            if event_type == QEvent.MouseMove:
                buttons = event.buttons()
                if buttons == Qt.NoButton:
                    pos = event.position() if hasattr(event, 'position') else event.pos()
                    x, y = int(pos.x()), int(pos.y())
                    self._hover_body_face(x, y)
                return False  # Let VTK handle camera

            if event_type == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    if self.hovered_body_face is not None:
                        self._click_body_face()
                        return True
                    return False
                return False

            if event_type == QEvent.MouseButtonRelease:
                return False

            return False

        # --- DRAFT MODE (Body-Face picking for draft) ---
        # --- SPLIT MODE (body already selected, drag/keyboard) ---
        if self.split_mode and self._split_body_id is not None:
            event_type = event.type()

            if event_type == QEvent.KeyPress:
                key = event.key()
                if key == Qt.Key_X:
                    self.split_drag_changed.emit(self._split_position)  # trigger sync
                    return True
                elif key == Qt.Key_Y:
                    return True
                elif key == Qt.Key_Z:
                    return True
                elif key == Qt.Key_Up:
                    self._split_position += 1.0
                    self._draw_split_plane()
                    self.split_drag_changed.emit(self._split_position)
                    return True
                elif key == Qt.Key_Down:
                    self._split_position -= 1.0
                    self._draw_split_plane()
                    self.split_drag_changed.emit(self._split_position)
                    return True

            # Let mouse events pass through to eventFilter split handler above
            return False

        if self.draft_mode:
            event_type = event.type()

            if event_type == QEvent.MouseMove:
                buttons = event.buttons()
                if buttons == Qt.NoButton:
                    pos = event.position() if hasattr(event, 'position') else event.pos()
                    x, y = int(pos.x()), int(pos.y())
                    self._hover_body_face(x, y)
                return False

            if event_type == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    if self.hovered_body_face is not None:
                        self._click_body_face()
                        return True
                    return False
                return False

            if event_type == QEvent.MouseButtonRelease:
                return False

            return False

        # --- POINT-TO-POINT MOVE MODE (CAD-Style) ---
        if self.point_to_point_mode:
            # Mouse Move: Zeige Hover-Vertex (KEIN LOGGING für Performance)
            if event.type() == QEvent.MouseMove:
                pos = event.position() if hasattr(event, 'position') else event.pos()
                x, y = int(pos.x()), int(pos.y())

                # WICHTIG: log_pick=False für hover (kein Debug-Output bei jedem Frame)
                body_id, point = self.pick_point_on_geometry(x, y, snap_to_vertex=True, log_pick=False)
                if point:
                    # Phase 3: Performance - Marker-Position updaten statt neu erstellen
                    # Reuse existing marker, only update position
                    if self._p2p_hover_marker_actor is None:
                        # Erster Hover: Erstelle Actor einmal
                        import pyvista as pv
                        self.plotter.add_mesh(
                            self._p2p_hover_marker_mesh,
                            color='orange',
                            opacity=0.8,
                            name='p2p_hover_marker'
                        )
                        if 'p2p_hover_marker' in self.plotter.renderer.actors:
                            self._p2p_hover_marker_actor = self.plotter.renderer.actors['p2p_hover_marker']

                    # Update Position via VTK Transform (FAST!)
                    if self._p2p_hover_marker_actor:
                        self._p2p_hover_marker_actor.SetPosition(point)
                        self._p2p_hover_marker_actor.SetVisibility(True)
                else:
                    # Kein Treffer: Verstecke Marker
                    if self._p2p_hover_marker_actor:
                        # Nur verstecken statt entfernen
                        self._p2p_hover_marker_actor.SetVisibility(False)
                        request_render(self.plotter)
                return True

            # Mouse Click: Wähle Punkt
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                pos = event.position() if hasattr(event, 'position') else event.pos()
                x, y = int(pos.x()), int(pos.y())

                # WICHTIG: Verstecke Hover-Marker BEVOR wir picken (sonst blockt er den Pick!)
                if self._p2p_hover_marker_actor:
                    # Nur verstecken, nicht entfernen (Actor bleibt gecacht)
                    self._p2p_hover_marker_actor.SetVisibility(False)

                body_id, point = self.pick_point_on_geometry(x, y)
                if point:
                    if not self.point_to_point_start:
                        # Erster Punkt ausgewählt
                        self.point_to_point_start = point
                        self.point_to_point_body_id = body_id
                        self.point_to_point_start_picked.emit(point)

                        # Phase 3: Performance - Start-Marker cachen
                        # Reuse cached start marker
                        if self._p2p_start_marker_actor is None:
                            self.plotter.add_mesh(
                                self._p2p_start_marker_mesh,
                                color='yellow',
                                name='p2p_start_marker'
                            )
                            if 'p2p_start_marker' in self.plotter.renderer.actors:
                                self._p2p_start_marker_actor = self.plotter.renderer.actors['p2p_start_marker']

                        if self._p2p_start_marker_actor:
                            self._p2p_start_marker_actor.SetPosition(point)
                            self._p2p_start_marker_actor.SetVisibility(True)

                        logger.success(f"✅ Start-Punkt gewählt. Jetzt Ziel-Punkt klicken.")
                    else:
                        # Zweiter Punkt ausgewählt - führe Move durch
                        end_point = point
                        # Emittiere Signal für MainWindow
                        self.point_to_point_move.emit(self.point_to_point_body_id, self.point_to_point_start, end_point)
                        # Reset
                        self.cancel_point_to_point_mode()
                return True

            # ESC zum Abbrechen
            if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
                self.cancel_point_to_point_mode()
                return True
            return False

        # --- PLANE SELECT MODE ---
        if self.plane_select_mode:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                pos = event.position() if hasattr(event, 'position') else event.pos()
                self._pick_plane_at_position(int(pos.x()), int(pos.y()))
                return True

            if event.type() == QEvent.MouseMove:
                pos = event.position() if hasattr(event, 'position') else event.pos()
                self._highlight_plane_at_position(int(pos.x()), int(pos.y()))
                return True
            return False

        # --- EXTRUDE MODE LOGIK (NEU) ---
        if self.extrude_mode:
            # Esc: "To Face"-Pick abbrechen
            if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape and self._to_face_picking:
                self._to_face_picking = False
                self.setCursor(Qt.ArrowCursor)
                return True

            # Rechtsklick zum ABBRECHEN (nicht Bestätigen!)
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.RightButton:
                self._clear_preview()
                self.extrude_height = 0.0
                self.selected_face_ids.clear()
                self.is_dragging = False
                self._is_potential_drag = False
                self._draw_selectable_faces_from_detector()
                self.extrude_cancelled.emit()
                return True
            
            # Enter Taste zum Bestätigen
            if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.confirm_extrusion()
                return True

        # --- MOUSE MOVE ---
        if event.type() == QEvent.MouseMove:
            pos = event.position() if hasattr(event, 'position') else event.pos()
            x, y = int(pos.x()), int(pos.y())

            # Dragging Logik (Extrude Höhe ziehen)
            # FIX: Nur Preview zeigen wenn extrude_preview_enabled (nicht bei Loft/Shell!)
            if self.extrude_mode and getattr(self, 'is_dragging', False) and getattr(self, 'extrude_preview_enabled', True):
                delta = self._calculate_extrude_delta(pos)
                self.show_extrude_preview(self.drag_start_height + delta, self.extrude_operation)
                self.height_changed.emit(self.extrude_height)
                return True
            
            # Drag Start erkennen
            elif self.extrude_mode and getattr(self, '_is_potential_drag', False):
                if (pos - self._potential_drag_start).manhattanLength() > 5:
                    self.is_dragging = True
                    self._is_potential_drag = False
                    self.drag_start_pos = self._potential_drag_start
                    self.drag_start_height = self.extrude_height
                    return True
            
            # Normales Hovering (Nur wenn Maus nicht gedrückt oder Drag aktiv)
            elif not (event.buttons() & Qt.LeftButton):
                pos = event.position() if hasattr(event, 'position') else event.pos()
                x, y = int(pos.x()), int(pos.y())

                # NEU: Body-Hover für pending transform mode
                if self.pending_transform_mode:
                    body_id = self.select_body_at(x, y)
                    if body_id != self.hover_body_id:
                        # Altes Highlighting entfernen
                        if self.hover_body_id:
                            self.unhighlight_body(self.hover_body_id)
                        # Neues Highlighting setzen
                        self.hover_body_id = body_id
                        if body_id:
                            self.highlight_body(body_id)
                    return False

                # ÄNDERUNG: Face-Hovering (nur wenn NICHT im pending transform mode)
                hit_id = self.pick(x, y, selection_filter=self.active_selection_filter)
                if hit_id != getattr(self, 'hover_face_id', -1):
                    self._update_hover(hit_id)
            return False

        # --- BOX SELECT: Mouse move updates rubber band ---
        if event.type() == QEvent.MouseMove and self._box_select_active:
            from PySide6.QtCore import QRect, QPoint
            pos = event.position() if hasattr(event, 'position') else event.pos()
            cur = QPoint(int(pos.x()), int(pos.y()))
            if self._box_select_rect:
                self._box_select_rect.setGeometry(QRect(self._box_select_start, cur).normalized())
            return True

        # --- BOX SELECT: Release finishes selection ---
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton and self._box_select_active:
            self._box_select_active = False
            if self._box_select_rect:
                rect = self._box_select_rect.geometry()
                self._box_select_rect.hide()
                self._box_select_rect.deleteLater()
                self._box_select_rect = None
                # Select bodies whose screen-projected center is inside rect
                self._select_bodies_in_rect(rect)
            return True

        # --- MOUSE PRESS (Left) ---
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            pos = event.position() if hasattr(event, 'position') else event.pos()
            x, y = int(pos.x()), int(pos.y())

            # Box select: Ctrl+drag starts rubber band
            mods = QApplication.keyboardModifiers()
            if mods & Qt.ControlModifier and not self.extrude_mode and not self.measure_mode:
                from PySide6.QtWidgets import QRubberBand
                from PySide6.QtCore import QPoint, QSize
                self._box_select_active = True
                self._box_select_start = QPoint(x, y)
                self._box_select_rect = QRubberBand(QRubberBand.Rectangle, self)
                self._box_select_rect.setGeometry(x, y, 0, 0)
                self._box_select_rect.show()
                return True

            # NEU (Fix 1): Body-Picking NUR für pending transform mode
            # WICHTIG: Nur wenn MainWindow explizit auf Body-Klick wartet!
            if self.pending_transform_mode:
                body_id = self.select_body_at(x, y)
                if body_id:
                    self.body_clicked.emit(body_id)
                    return True

            # NEU: Sketch-Pfad-Selektion für Sweep (direkter Viewport-Klick)
            if self.sketch_path_mode:
                sketch_id, geom_type, index = self._pick_sketch_element_at(x, y)
                logger.debug(f"Sketch-Pfad Pick Ergebnis: sketch_id={sketch_id}, geom_type={geom_type}, index={index}")
                if sketch_id and geom_type in ('line', 'arc', 'spline'):
                    self.sketch_path_clicked.emit(sketch_id, geom_type, index)
                    return True

            # Measure-Modus: Punkt auf Modell picken mit Vertex/Edge-Snapping
            if self.measure_mode:
                import numpy as np

                picker = self._get_picker("measure")  # Phase 4: Reuse picker
                height = self.plotter.interactor.height()
                picker.Pick(x, height - y, 0, self.plotter.renderer)
                if picker.GetCellId() != -1:
                    pos = np.array(picker.GetPickPosition())

                    # Snap zu naechstem Vertex oder Edge-Midpoint
                    snap_pos = self._snap_measure_point(pos)
                    self.measure_point_picked.emit(tuple(snap_pos))
                return True

            # "Extrude to Face" — Ziel-Pick abfangen
            if self._to_face_picking:
                hit_id = self.pick(x, y, selection_filter=self.active_selection_filter)
                if hit_id != -1:
                    self._to_face_picking = False
                    self.setCursor(Qt.ArrowCursor)
                    self.target_face_selected.emit(hit_id)
                    return True

            # FIX: In Extrude-Mode vor dem Pick aufräumen
            if self.extrude_mode:
                # Preview löschen falls vorhanden
                if getattr(self, '_preview_actor', None):
                    self._clear_preview()

                # WICHTIG: State für neuen Drag vorbereiten
                # Ohne diesen Reset kann der zweite Drag-Versuch fehlschlagen
                self.is_dragging = False

            # Face-Selection (für Extrude etc.)
            hit_id = self.pick(x, y, selection_filter=self.active_selection_filter)

            # Multi-Select vorab prüfen (für beide Zweige)
            is_multi = QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.ShiftModifier)

            if hit_id != -1:
                if not is_multi:
                    self.selected_face_ids.clear()

                # Toggle bei Multi-Select
                if is_multi and hit_id in self.selected_face_ids:
                    self.selected_face_ids.discard(hit_id)
                else:
                    self.selected_face_ids.add(hit_id)

                # Extrude Drag vorbereiten
                if self.extrude_mode:
                    self._is_potential_drag = True
                    self._potential_drag_start = pos
                    # Reset height bei Face-Wechsel
                    self.extrude_height = 0.0
                    face = next((f for f in self.detector.selection_faces if f.id == hit_id), None)
                    if face:
                        self._cache_drag_direction_for_face_v2(face)

                self._draw_selectable_faces_from_detector()

                # Signal für automatische Operation-Erkennung
                self.face_selected.emit(hit_id)
                return True
            else:
                # Kein Face getroffen -> Background Click
                if not is_multi:
                    # 1. Alle Selections clearen (konsistent mit abort logic)
                    self.clear_selection()
                    self._draw_selectable_faces_from_detector()

                    # 2. Body Selection clearen (via Signal)
                    self.background_clicked.emit()


        # --- MOUSE PRESS (Right) - Context Menu ---
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.RightButton:
            # Nur wenn kein aktiver Modus (außer Extrude, der hat eigenes Handling)
            if (
                not self.extrude_mode
                and not self.measure_mode
                and not self.point_to_point_mode
                and self._right_click_start_pos is None
            ):
                 pos = event.position() if hasattr(event, 'position') else event.pos()
                 self._show_context_menu(pos)
                 return True

        # --- MOUSE RELEASE ---
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if self.extrude_mode:
                # NUR resetten wenn wir tatsächlich gedraggt haben
                # Sonst bleibt _is_potential_drag True für den nächsten Drag-Versuch
                if getattr(self, 'is_dragging', False):
                    self.is_dragging = False
                    self._is_potential_drag = False
                # Bei einfachem Klick (ohne Drag) _is_potential_drag NICHT resetten
                # damit der User sofort nach dem Klick draggen kann

        return False
        #return super().eventFilter(obj, event)

    def leaveEvent(self, event):
        """
        FIX: Reset drag state wenn Maus den Viewport verlässt.
        Verhindert "stuck" Extrude-Drag wenn Maus außerhalb losgelassen wird.
        """
        if self.extrude_mode:
            if getattr(self, 'is_dragging', False) or getattr(self, '_is_potential_drag', False):
                self.is_dragging = False
                self._is_potential_drag = False

        # Auch andere Drag-States resetten
        if getattr(self, '_split_dragging', False):
            self._split_dragging = False
            self._split_drag_start = None

        if getattr(self, '_offset_plane_dragging', False):
            self._offset_plane_dragging = False
            self._offset_plane_drag_start = None

        super().leaveEvent(event)

    def _select_bodies_in_rect(self, rect):
        """Select all bodies whose projected center falls inside the screen rectangle."""
        import vtk
        selected = []
        renderer = self.plotter.renderer
        for bid, info in self.bodies.items():
            mesh = info.get('mesh')
            if mesh is None:
                continue
            center = mesh.center
            coord = vtk.vtkCoordinate()
            coord.SetCoordinateSystemToWorld()
            coord.SetValue(center[0], center[1], center[2])
            display = coord.GetComputedDisplayValue(renderer)
            # VTK display coords: origin at bottom-left; Qt: origin at top-left
            sx = display[0]
            sy = self.plotter.interactor.height() - display[1]
            if rect.contains(int(sx), int(sy)):
                selected.append(bid)
                self.highlight_body(bid)
        if selected:
            self.box_selected = selected
            logger.info(f"Box select: {len(selected)} bodies selected")
            self.body_clicked.emit(selected[0])  # Signal first selected

    def _snap_measure_point(self, pos):
        """Snap pick-position to nearest vertex or edge midpoint/center."""
        import numpy as np
        best_pt = pos
        best_dist = 8.0  # Max snap distance in world units

        for bid, info in self.bodies.items():
            body_obj = info.get("body_obj")
            if not body_obj:
                continue
            solid = getattr(body_obj, "_build123d_solid", None)
            if solid is None:
                continue
            try:
                # Snap to vertices
                for v in solid.vertices():
                    vp = np.array([v.X, v.Y, v.Z])
                    d = np.linalg.norm(pos - vp)
                    if d < best_dist:
                        best_dist = d
                        best_pt = vp

                # Snap to edge midpoints
                for e in solid.edges():
                    try:
                        mp = e @ 0.5  # Build123d: evaluate at parameter 0.5
                        ep = np.array([mp.X, mp.Y, mp.Z])
                        d = np.linalg.norm(pos - ep)
                        if d < best_dist:
                            best_dist = d
                            best_pt = ep
                    except Exception:
                        pass
            except Exception:
                continue

        return best_pt

    def _handle_3d_click(self, x, y):
        """Erkennt Klick auf 3D Körper und sendet Signal"""
        if not self.bodies: return
        try:
            picker = self._get_picker("standard")  # Phase 4: Reuse picker
            picker.Pick(x, self.plotter.interactor.height()-y, 0, self.plotter.renderer)
            
            actor = picker.GetActor()
            if actor:
                body_id = None
                for bid, actors in self._body_actors.items():
                    # FIX: Iteriere über alle Actors des Bodies
                    for name in actors:
                        if self.plotter.renderer.actors.get(name) == actor:
                            body_id = bid
                            break
                    if body_id is not None: break
                
                if body_id is not None:
                    pos = picker.GetPickPosition()
                    self.clicked_3d_point.emit(body_id, pos)
        except Exception as e:
            logger.error(f" {e}")
            
    def _cache_drag_direction_for_face(self, face_idx):
        """Hilfsfunktion um Richtung basierend auf einem Face zu setzen"""
        if face_idx < 0 or face_idx >= len(self.detected_faces): return
        
        face = self.detected_faces[face_idx]
        normal = np.array(face.get('normal', (0,0,1)))
        
        if face.get('type') == 'body_face':
            center = np.array(face.get('center_3d', (0,0,0)))
        else:
            c2 = face['center_2d']
            center = np.array(self._transform_2d_to_3d(c2[0], c2[1], face['normal'], face['origin']))

        # Projektion berechnen (wie vorher in _cache_drag_direction)
        def world_to_display(pt):
            self.plotter.renderer.SetWorldPoint(pt[0], pt[1], pt[2], 1.0)
            self.plotter.renderer.WorldToDisplay()
            d_pt = self.plotter.renderer.GetDisplayPoint()
            height = self.plotter.interactor.height()
            return np.array([d_pt[0], height - d_pt[1]])

        p_start = world_to_display(center)
        p_end = world_to_display(center + normal * 10.0)
        vec = p_end - p_start
        
        if np.linalg.norm(vec) < 0.1:
            self._drag_screen_vector = np.array([1.0, 0.0])
        else:
            self._drag_screen_vector = vec / np.linalg.norm(vec)
            
            
    def _cache_drag_direction(self):
        """Wrapper für Kompatibilität"""
        if self.selected_faces:
            self._cache_drag_direction_for_face(list(self.selected_faces)[0])
    
    def _highlight_plane_at_position(self, x, y):
        """
        Kombiniert Standard-Ebenen Highlight mit GeometryDetector Highlight.
        Ersetzt den 'grünen Kreis' durch echte Flächen-Hervorhebung.
        """
        if not self._plane_actors: return
        
        height = self.plotter.interactor.height()
        
        # 1. Standard-Ebenen prüfen (XY, XZ, YZ) - die bleiben wie sie sind
        import vtk
        picker = vtk.vtkPropPicker()
        picker.Pick(x, height-y, 0, self.plotter.renderer)
        actor = picker.GetActor()
        found_std_plane = None
        
        if actor:
            for k, v in self._plane_actors.items():
                if self.plotter.renderer.actors.get(v) == actor: 
                    found_std_plane = k; break
        
        # Standard-Ebenen Highlight setzen
        if found_std_plane != self.last_highlighted_plane:
            self.last_highlighted_plane = found_std_plane
            for k in ['xy','xz','yz']:
                self._set_opacity(k, 0.7 if k == found_std_plane else 0.25)
            request_render(self.plotter)

        # 2. Wenn keine Standard-Ebene, prüfe auf Body-Flächen via Detector
        # (Nur wenn wir nicht gerade über einer Standardebene hovern)
        new_hover_id = -1
        
        if found_std_plane is None:
            # Nutze die intelligente Pick-Logik
            new_hover_id = self.pick(x, y, selection_filter={"body_face"})
        
        # Nur neu zeichnen wenn sich was geändert hat
        if new_hover_id != getattr(self, 'hover_face_id', -1):
            self.hover_face_id = new_hover_id
            # Nutzt die gleiche Methode wie Extrude -> Blaue Fläche!
            self._draw_selectable_faces_from_detector()
    
    def _draw_plane_hover_highlight(self, pos, normal):
        """Zeichnet Highlight für Body-Fläche im Plane-Select-Modus"""
        self._clear_plane_hover_highlight()
        try:
            center = np.array(pos)
            n = np.array(normal)
            n = n / np.linalg.norm(n) if np.linalg.norm(n) > 0 else np.array([0,0,1])

            # FIX: Sicherstellen dass Normal zur Kamera zeigt (nicht ins Body hinein)
            cam_pos = np.array(self.plotter.camera_position[0])
            view_dir = center - cam_pos
            view_dir = view_dir / np.linalg.norm(view_dir)
            if np.dot(n, view_dir) > 0:
                n = -n

            # Erstelle einen Kreis senkrecht zur Normalen
            radius = 8.0
            if abs(n[2]) < 0.9:
                u = np.cross(n, [0, 0, 1])
            else:
                u = np.cross(n, [1, 0, 0])
            u = u / np.linalg.norm(u)
            v = np.cross(n, u)

            # OFFSET: Highlight leicht vom Body weg (Z-Fighting vermeiden)
            offset_center = center + n * 0.5

            points = []
            for i in range(33):
                angle = i * 2 * math.pi / 32
                p = offset_center + radius * (math.cos(angle) * u + math.sin(angle) * v)
                points.append(p)

            pts = np.array(points)
            lines = pv.lines_from_points(pts)
            self.plotter.add_mesh(lines, color='lime', line_width=3, name='plane_hover')

            # Pfeil für Normale
            arrow = pv.Arrow(start=offset_center, direction=n, scale=10)
            self.plotter.add_mesh(arrow, color='lime', name='plane_hover_arrow')

            self.plotter.update()
        except Exception as e:
            logger.debug(f"Plane hover highlight failed: {e}")
    
    def _clear_plane_hover_highlight(self):
        """Entfernt Plane-Hover-Highlight"""
        _safe_remove_actor(self.plotter, 'plane_hover', "plane hover highlight clear")
        _safe_remove_actor(self.plotter, 'plane_hover_arrow', "plane hover arrow clear")

    def _set_opacity(self, key, val):
        try:
            self.plotter.renderer.actors.get(self._plane_actors[key]).GetProperty().SetOpacity(val)
        except Exception as e:
            _log_suppressed_exception(f"plane opacity set (key='{key}')", e)

    def _pick_plane_at_position(self, x, y):
        """
        Wählt die Ebene aus.
        Priorität: 1. Standard-Ebenen, 2. Body-Flächen (via Detector)
        """
        import vtk
        height = self.plotter.interactor.height()
        
        # 1. Standard-Ebenen (XY, XZ, YZ)
        picker = vtk.vtkPropPicker()
        picker.Pick(x, height - y, 0, self.plotter.renderer)
        actor = picker.GetActor()
        
        if actor:
            for name, actor_name in self._plane_actors.items():
                if self.plotter.renderer.actors.get(actor_name) == actor:
                    self.plane_clicked.emit(name)
                    return

        # 2. Body-Flächen via Detector (Das ist die Verbesserung!)
        # Wir nutzen das Ergebnis vom Hover, oder picken neu
        face_id = self.pick(x, y, selection_filter={"body_face"})
        
        if face_id != -1:
            # Face Objekt holen
            face = next((f for f in self.detector.selection_faces if f.id == face_id), None)
            if face:
                logger.info(f"Sketch Plane gewählt: Face {face.id} auf Body {face.owner_id}")

                # Sende Origin und Normal
                self.custom_plane_clicked.emit(
                    face.plane_origin,
                    face.plane_normal
                )

                # Speichere die stabile X-Achse für Schritt 2 (siehe vorherige Antwort)
                self._last_picked_x_dir = face.plane_x

                # ✅ FIX: Speichere auch die Body-ID für korrektes Targeting
                self._last_picked_body_id = face.owner_id

                # Face-Daten für Face-basierte Features
                self._last_picked_face_center = face.plane_origin
                self._last_picked_face_normal = face.plane_normal
                return

    def _update_detector_for_picking(self):
        """Lädt alle sichtbaren Body-Meshes in den Detector"""
        if not hasattr(self, 'detector'): return
        
        # Detector leeren
        self.detector.clear()
        
        # Nur Bodies laden (Sketches brauchen wir nicht um darauf zu sketchen)
        # Performance Optimization Phase 2.2: Übergebe extrude_mode für Dynamic Priority
        extrude_mode = getattr(self, 'extrude_mode', False)
        for bid, body_data in self.bodies.items():
            if self.is_body_visible(bid) and 'mesh' in body_data:
                # FIX: B-Rep face_info übergeben wenn Body-Objekt verfügbar
                face_info = None
                body_obj = body_data.get('body')
                if body_obj and hasattr(body_obj, 'face_info'):
                    face_info = body_obj.face_info
                self.detector.process_body_mesh(
                    bid, body_data['mesh'], extrude_mode=extrude_mode, face_info=face_info
                )
            
   
        
    def _on_face_clicked(self, point, hover_only=False):
        best_dist = float('inf')
        best_idx = -1
        
        for i, face in enumerate(self.detected_faces):
            # Body-Face oder Sketch-Face?
            if face.get('type') == 'body_face':
                c3 = face.get('center_3d', (0, 0, 0))
            else:
                c2 = face['center_2d']
                c3 = self._transform_2d_to_3d(c2[0], c2[1], face['normal'], face['origin'])
            
            dist = math.sqrt(sum((point[k]-c3[k])**2 for k in range(3)))
            if dist < best_dist:
                best_dist = dist
                best_idx = i
        
        if best_idx >= 0 and best_dist < 200:
            if hover_only:
                # Nur neu zeichnen wenn sich hover geändert hat
                if self.hovered_face != best_idx:
                    self.hovered_face = best_idx
                    self._draw_selectable_faces()
            else:
                # Klick: Toggle Auswahl
                # W8 PAKET B: Use Unified Selection API toggle_face_selection()
                # Check modifiers for multi-select
                is_multi = QApplication.keyboardModifiers() & Qt.ControlModifier
                self.toggle_face_selection(best_idx, is_multi=is_multi)
                self._draw_selectable_faces()
                self.face_selected.emit(best_idx)
        elif hover_only and self.hovered_face != -1:
            # Nichts getroffen - hover zurücksetzen
            self.hovered_face = -1
            self._draw_selectable_faces()

    def _transform_2d_to_3d(self, x, y, normal, origin):
        """Wandelt lokale Sketch-Koordinaten in globale 3D-Koordinaten um"""
        ox, oy, oz = origin
        
        # Standard-Berechnung
        ux, uy = self._calculate_plane_axes(normal)
        
        # P_world = Origin + x*U + y*V
        px = ox + x * ux[0] + y * uy[0]
        py = oy + x * ux[1] + y * uy[1]
        pz = oz + x * ux[2] + y * uy[2]
        return (px, py, pz)

    def _apply_boolean_operation(self, new_mesh, operation, target_body_id=None):
        """Führt Boolean Ops durch: Union, Difference, New Body"""
        import vtk
        
        # 1. Neuer Körper
        if operation == "New Body" or not self.bodies or target_body_id is None:
            new_id = max(self.bodies.keys(), default=0) + 1
            self.add_body(new_id, f"Body {new_id}", new_mesh.points, [], color=None)
            # Hinweis: add_body erwartet verts/faces, aber wir können PyVista mesh direkt nutzen wenn wir add_body anpassen
            # Besserer Weg hier: Direkt mesh speichern
            self._add_mesh_as_body(new_id, new_mesh)
            return

        # 2. Bestehenden Körper holen
        # Wir nehmen vereinfacht an, es gibt einen 'aktiven' Körper oder den zuletzt erstellten
        target_id = target_body_id if target_body_id else list(self.bodies.keys())[-1]
        target_mesh = self.bodies[target_id]['mesh']

        try:
            # PyVista Boolean Operations (benötigt triangulierte, saubere Meshes)
            # Sicherstellen, dass alles Dreiecke sind
            if not target_mesh.is_all_triangles: target_mesh = target_mesh.triangulate()
            if not new_mesh.is_all_triangles: new_mesh = new_mesh.triangulate()
            
            result_mesh = None
            
            if operation == "Join":
                result_mesh = target_mesh.boolean_union(new_mesh)
            elif operation == "Cut":
                result_mesh = target_mesh.boolean_difference(new_mesh)
            elif operation == "Intersect":
                result_mesh = target_mesh.boolean_intersection(new_mesh)
                
            if result_mesh and result_mesh.n_points > 0:
                # Körper aktualisieren
                self._add_mesh_as_body(target_id, result_mesh, color=self.bodies[target_id]['color'])
                logger.success(f"Boolean success.")
            else:
                logger.warning("Boolean Operation failed (empty result).")
                # Fallback: Als neuen Körper hinzufügen, damit Arbeit nicht verloren geht
                self._apply_boolean_operation(new_mesh, "New Body")

        except Exception as e:
            logger.error(f" {e}")
            self._apply_boolean_operation(new_mesh, "New Body")
            
    def _add_mesh_as_body(self, bid, mesh, color=None):
        """Interne Hilfsfunktion um ein PyVista Mesh direkt als Body zu speichern"""
        # Alten Actor entfernen
        if bid in self._body_actors:
            for n in self._body_actors[bid]:
                _safe_remove_actor(self.plotter, n, f"body actor cleanup (bid='{bid}')")
        
        mesh = mesh.clean() # Wichtig für Rendering
        mesh.compute_normals(inplace=True)
        
        col = color or "lightblue"
        n1 = f"body_{bid}_m"
        # PBR (Physically Based Rendering) für Metall-Look
        self.plotter.add_mesh(mesh, color=col, name=n1, show_edges=False, 
                              smooth_shading=True, pbr=True, metallic=0.5, roughness=0.4)
        
        n2 = f"body_{bid}_e"
        edges = mesh.extract_feature_edges(feature_angle=45)
        self.plotter.add_mesh(edges, color="black", line_width=2, name=n2)
        
        self._body_actors[bid] = (n1, n2)
        self.bodies[bid] = {'mesh': mesh, 'color': col}
        request_render(self.plotter)

    # ==================== PUBLIC API ====================
    def set_plane_select_mode(self, enabled):
        self.plane_select_mode = enabled
        self.last_highlighted_plane = None
        
        # Reset Hover
        self.hover_face_id = -1
        self.selected_face_ids.clear()
        
        if enabled:
            self._show_selection_planes()

            # WICHTIG: Detector mit Geometrie füllen, genau wie beim Extrude!
            # Wir nutzen die Hilfsfunktion, um nicht alles doppelt zu schreiben
            self._update_detector_for_picking()

            # FIX: VTK Picker braucht echten Render für aktuellen Depth-Buffer
            try:
                self.plotter.render()
                if hasattr(self.plotter, 'render_window') and self.plotter.render_window:
                    self.plotter.render_window.Render()
            except Exception as e:
                logger.debug(f"Force render failed: {e}")
                request_render(self.plotter, immediate=True)
        else:
            self._hide_selection_planes()
            # Aufräumen
            self._clear_face_actors()
            self._clear_plane_hover_highlight() # Alte Visualisierung löschen
            request_render(self.plotter)

    def set_extrude_mode(self, enabled, enable_preview=True):
        """
        Aktiviert Face-Picking-Modus und optional die Extrude-Preview.

        Args:
            enabled: Aktiviert Face-Picking
            enable_preview: Zeigt Extrude-Preview während Drag (False für Loft/Shell!)
        """
        self.extrude_mode = enabled
        self.extrude_preview_enabled = enable_preview if enabled else True

        # Reset Selection beim Start
        if enabled:
            self.selected_face_ids.clear()
            self._drag_screen_vector = np.array([0.0, -1.0])
            # HINWEIS: Detector wird von _extrude_dialog() via _update_detector() befüllt
            # NICHT hier _update_detector_for_picking() aufrufen - das löscht Sketch-Profile!
            # Zeichnen anstoßen (initial leer, da nichts selektiert)
            self._draw_selectable_faces_from_detector()
            request_render(self.plotter)
        else:
            self.selected_face_ids.clear()
            self._clear_face_actors()
            self._clear_preview()
            # FIX: Auch alle anderen Highlights aufräumen (verhindert hängende Highlights)
            self._clear_body_face_highlight()
            self._clear_texture_face_highlights()
            request_render(self.plotter)

    def set_sweep_mode(self, enabled: bool):
        """
        Aktiviert/Deaktiviert Sweep-Interaktionsmodus.

        Der Sweep-Profil-Pick nutzt denselben Face-Picking-Pfad wie Extrude,
        jedoch ohne Extrude-Preview.
        """
        self._sweep_mode = bool(enabled)
        if self._sweep_mode:
            self.set_extrude_mode(True, enable_preview=False)
        else:
            if hasattr(self, 'stop_sketch_path_mode'):
                self.stop_sketch_path_mode()
            # Nur deaktivieren, wenn Loft nicht parallel aktiv ist.
            if not getattr(self, '_loft_mode', False):
                self.set_extrude_mode(False)

    def set_loft_mode(self, enabled: bool):
        """
        Aktiviert/Deaktiviert Loft-Interaktionsmodus.

        Loft-Profil-Picks laufen über Face-Picking ohne Extrude-Preview.
        """
        self._loft_mode = bool(enabled)
        if self._loft_mode:
            self.set_extrude_mode(True, enable_preview=False)
        else:
            # Nur deaktivieren, wenn Sweep nicht parallel aktiv ist.
            if not getattr(self, '_sweep_mode', False):
                self.set_extrude_mode(False)

    # ==================== SKETCH PATH SELECTION MODE ====================

    def start_sketch_path_mode(self):
        """
        Aktiviert Sketch-Element-Selektion für Sweep-Pfade.
        In diesem Modus kann der User direkt auf Sketch-Linien, Bögen und Splines klicken.
        """
        self.sketch_path_mode = True
        # Highlight alle Sketch-Elemente
        self._highlight_sketch_paths()
        logger.info("Sketch-Pfad-Modus aktiviert: Klicke auf eine Linie, Bogen oder Spline im Viewport")

    def stop_sketch_path_mode(self):
        """Beendet den Sketch-Pfad-Modus."""
        self.sketch_path_mode = False
        self._unhighlight_sketch_paths()
        logger.debug("Sketch-Pfad-Modus beendet")

    def _highlight_sketch_paths(self):
        """Hebt alle Sketch-Pfad-Elemente (Linien, Bögen, Splines) hervor."""
        for actor_name in self._sketch_actors:
            # Nur Linien, Bögen und Splines highlighten (nicht Kreise)
            if '_l_' in actor_name or '_a_' in actor_name or '_sp_' in actor_name:
                try:
                    actor = self.plotter.renderer.actors.get(actor_name)
                    if actor:
                        # Helle Farbe für Pfad-Kandidaten
                        actor.GetProperty().SetColor(0.0, 1.0, 0.5)  # Hellgrün
                        actor.GetProperty().SetLineWidth(5)
                except Exception as e:
                    logger.debug(f"[viewport] Fehler beim Highlight Sketch-Pfad {actor_name}: {e}")
        request_render(self.plotter)

    def _unhighlight_sketch_paths(self):
        """Setzt Sketch-Elemente auf Normalfarbe zurück."""
        for actor_name in self._sketch_actors:
            try:
                actor = self.plotter.renderer.actors.get(actor_name)
                if actor:
                    # Zurück zur Standardfarbe
                    actor.GetProperty().SetColor(0.3, 0.58, 1.0)  # #4d94ff
                    actor.GetProperty().SetLineWidth(3)
            except Exception as e:
                logger.debug(f"[viewport] Fehler beim Unhighlight Sketch-Pfad {actor_name}: {e}")
        request_render(self.plotter)

    def _pick_sketch_element_at(self, x: int, y: int) -> tuple:
        """
        Findet ein Sketch-Element (Linie, Bogen, Spline) an der Klickposition.
        Verwendet Proximity-basiertes Picking für maximale Zuverlässigkeit.

        Returns:
            Tuple (sketch_id, geom_type, index) oder (None, None, None) wenn nichts getroffen.
            geom_type: 'line', 'arc', 'circle', 'spline'
        """
        # Proximity-Picking ist zuverlässiger als VTK Actor-Matching
        result = self._pick_sketch_element_by_proximity(x, y)
        if result[0]:
            logger.info(f"Sketch-Element gefunden bei ({x}, {y}): {result}")
        else:
            logger.debug(f"Kein Sketch-Element bei ({x}, {y}) gefunden")
        return result

    def _pick_sketch_element_by_proximity(self, x: int, y: int) -> tuple:
        """
        Findet Sketch-Element durch Proximity-Check.
        Liest Geometrie direkt aus den Sketch-Objekten (nicht aus Actors).
        """
        import numpy as np
        import math

        try:
            height = self.plotter.interactor.height()
            best_dist = float('inf')
            best_result = (None, None, None)

            logger.debug(f"Proximity-Picking: Suche in {len(self.sketches)} Sketches bei ({x}, {y})")

            for sketch, visible in self.sketches:
                if not visible:
                    continue

                sid = str(getattr(sketch, 'id', id(sketch)))
                norm = tuple(getattr(sketch, 'plane_normal', (0, 0, 1)))
                orig = getattr(sketch, 'plane_origin', (0, 0, 0))
                cached_x = getattr(sketch, 'plane_x_dir', None)
                cached_y = getattr(sketch, 'plane_y_dir', None)

                # Berechne Transformation 2D -> 3D
                if cached_x and cached_y:
                    ux, uy, uz = cached_x
                    vx, vy, vz = cached_y
                else:
                    (ux, uy, uz), (vx, vy, vz) = self._calculate_plane_axes(norm)
                ox, oy, oz = orig

                def to_3d(lx, ly):
                    return (ox + lx * ux + ly * vx, oy + lx * uy + ly * vy, oz + lx * uz + ly * vz)

                def to_screen(pt_3d):
                    self.plotter.renderer.SetWorldPoint(pt_3d[0], pt_3d[1], pt_3d[2], 1.0)
                    self.plotter.renderer.WorldToDisplay()
                    display = self.plotter.renderer.GetDisplayPoint()
                    return display[0], height - display[1]

                # Prüfe Linien
                for i, line in enumerate(getattr(sketch, 'lines', [])):
                    if getattr(line, 'construction', False):
                        continue  # Konstruktionslinien überspringen
                    p1_3d = to_3d(line.start.x, line.start.y)
                    p2_3d = to_3d(line.end.x, line.end.y)
                    p1_screen = to_screen(p1_3d)
                    p2_screen = to_screen(p2_3d)

                    # Distanz Punkt zu Liniensegment
                    dist = self._point_to_segment_distance(x, y, p1_screen[0], p1_screen[1], p2_screen[0], p2_screen[1])
                    if dist < best_dist and dist < 50:
                        best_dist = dist
                        best_result = (sid, 'line', i)

                # Prüfe Bögen
                for i, arc in enumerate(getattr(sketch, 'arcs', [])):
                    if getattr(arc, 'construction', False):
                        continue
                    # Mittelwert der Bogenpunkte
                    start_a = math.radians(arc.start_angle)
                    end_a = math.radians(arc.end_angle)
                    mid_a = (start_a + end_a) / 2
                    mid_x = arc.center.x + arc.radius * math.cos(mid_a)
                    mid_y = arc.center.y + arc.radius * math.sin(mid_a)
                    mid_3d = to_3d(mid_x, mid_y)
                    mid_screen = to_screen(mid_3d)
                    dist = ((mid_screen[0] - x)**2 + (mid_screen[1] - y)**2)**0.5
                    if dist < best_dist and dist < 50:
                        best_dist = dist
                        best_result = (sid, 'arc', i)

                # Prüfe Splines
                for i, spline in enumerate(getattr(sketch, 'splines', []) + getattr(sketch, 'native_splines', [])):
                    if getattr(spline, 'construction', False):
                        continue
                    ctrl_pts = getattr(spline, 'control_points', getattr(spline, 'points', []))
                    if ctrl_pts:
                        # Mittelwert der Kontrollpunkte
                        if hasattr(ctrl_pts[0], 'x'):
                            mid_x = sum(p.x for p in ctrl_pts) / len(ctrl_pts)
                            mid_y = sum(p.y for p in ctrl_pts) / len(ctrl_pts)
                        else:
                            mid_x = sum(p[0] for p in ctrl_pts) / len(ctrl_pts)
                            mid_y = sum(p[1] for p in ctrl_pts) / len(ctrl_pts)
                        mid_3d = to_3d(mid_x, mid_y)
                        mid_screen = to_screen(mid_3d)
                        dist = ((mid_screen[0] - x)**2 + (mid_screen[1] - y)**2)**0.5
                        if dist < best_dist and dist < 50:
                            best_dist = dist
                            best_result = (sid, 'spline', i)

            if best_result[0]:
                logger.info(f"Proximity-Picking Erfolg: sketch={best_result[0]}, type={best_result[1]}, idx={best_result[2]} (dist={best_dist:.1f}px)")
            else:
                logger.debug(f"Proximity-Picking: Nichts gefunden in {len(self.sketches)} Sketches")
            return best_result

        except Exception as e:
            logger.error(f"Proximity-Picking Fehler: {e}")
            import traceback
            traceback.print_exc()
            return (None, None, None)

    def _point_to_segment_distance(self, px, py, x1, y1, x2, y2):
        """Berechnet die kürzeste Distanz von Punkt (px, py) zum Liniensegment (x1,y1)-(x2,y2)."""
        import math
        dx = x2 - x1
        dy = y2 - y1
        length_sq = dx * dx + dy * dy

        if length_sq == 0:
            # Segment ist ein Punkt
            return math.sqrt((px - x1)**2 + (py - y1)**2)

        # Projektion des Punktes auf die Linie
        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_sq))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy

        return math.sqrt((px - proj_x)**2 + (py - proj_y)**2)

    def _draw_selectable_faces_from_detector(self):
        """
        PERFORMANCE FIX:
        Zeichnet NUR die aktuell selektierten Flächen und die gehoverte Fläche.
        Zeichnet NICHT mehr alle 60+ Kandidaten als transparente Overlays,
        da dies bei komplexen Modellen extrem laggt.
        """
        if not self.selected_face_ids and getattr(self, 'hover_face_id', -1) == -1 and not self._face_actors:
            return

        self._clear_face_actors()
        
        # 1. Sammle relevante IDs (Selected + Hovered)
        relevant_ids = set(self.selected_face_ids)
        if getattr(self, 'hover_face_id', -1) != -1:
            relevant_ids.add(self.hover_face_id)
            
        if not relevant_ids:
            # Nichts zu tun, Render nur erzwingen um alte zu löschen
            request_render(self.plotter)
            return
            
        # 2. Nur relevante zeichnen
        for face in self.detector.selection_faces:
            if face.id not in relevant_ids:
                continue

            is_selected = face.id in self.selected_face_ids
            is_hovered = face.id == getattr(self, 'hover_face_id', -1)

            # Farbe und Transparenz (FIX: Erhöhte Sichtbarkeit)
            if is_selected:
                color = '#ff8800'  # Leuchtend Orange
                opacity = 0.85
                edge_color = '#ff4400'  # Kontrastkanten
            elif is_hovered:
                color = '#55bbff'  # Hellblau (heller)
                opacity = 0.7
                edge_color = '#0088ff'  # Kontrastkanten
            else:
                continue

            if face.display_mesh:
                name = f"det_face_{face.id}"

                # FIX: Zylinder/Flächen mit variierender Normale
                # Bei gekrümmten Flächen (Zylinder) würde ein einheitlicher Offset
                # nur einen Teil korrekt platzieren. Stattdessen skalieren wir.
                # Erkennung: Wenn die Mesh-Normalen stark variieren, ist es gekrümmt.
                display_mesh = face.display_mesh
                if 'Normals' in display_mesh.cell_data and display_mesh.n_cells > 1:
                    normals = display_mesh.cell_data['Normals']
                    # Varianz der Normalen prüfen
                    normal_variance = np.std(normals, axis=0).sum()
                    if normal_variance > 0.1:  # Gekrümmte Fläche (Zylinder, Kugel)
                        # Skalierung statt Translation (dehnt mesh leicht nach aussen)
                        center = display_mesh.center_of_mass()
                        # PyVista scale() hat kein center-Argument - manueller Workaround
                        translated = display_mesh.translate(-center, inplace=False)
                        scaled = translated.scale((1.02, 1.02, 1.02), inplace=False)
                        highlight_mesh = scaled.translate(center, inplace=False)
                    else:
                        # Ebene Fläche - Offset funktioniert
                        offset = np.array(face.plane_normal) * 0.5
                        highlight_mesh = display_mesh.translate(offset, inplace=False)
                else:
                    # Keine Normalen-Infos - Fallback zu Offset
                    offset = np.array(face.plane_normal) * 0.5
                    highlight_mesh = display_mesh.translate(offset, inplace=False)

                self.plotter.add_mesh(
                    highlight_mesh,
                    color=color,
                    opacity=opacity,
                    name=name,
                    pickable=False,
                    show_edges=False,  # Keine Dreieckskanten - glatte Fläche
                )
                self._face_actors.append(name)

            else:
                # Performance Optimization Phase 2.4: Fallback-Highlighting (Wireframe)
                # Wenn display_mesh fehlt, zeichne zumindest den Umriss als Feedback
                logger.debug(f"⚠️ Face {face.id} hat kein display_mesh - nutze Wireframe-Fallback")

                try:
                    # Erstelle einen simplen Marker an der plane_origin
                    center = np.array(face.plane_origin)
                    normal = np.array(face.plane_normal)

                    # Erstelle ein kleines Quad als Highlight
                    if abs(normal[2]) < 0.9:
                        u = np.cross(normal, [0, 0, 1])
                    else:
                        u = np.cross(normal, [1, 0, 0])
                    u = u / np.linalg.norm(u)
                    v = np.cross(normal, u)

                    size = 10.0  # 10mm großes Quad
                    pts = [
                        center + size * (-u - v),
                        center + size * (u - v),
                        center + size * (u + v),
                        center + size * (-u + v),
                    ]

                    import pyvista as pv
                    quad = pv.PolyData(np.array(pts), faces=[4, 0, 1, 2, 3])

                    name = f"det_face_fallback_{face.id}"
                    self.plotter.add_mesh(
                        quad,
                        color=color,
                        opacity=opacity,
                        style='wireframe',  # Wireframe statt Solid
                        line_width=3,
                        name=name,
                        pickable=False
                    )
                    self._face_actors.append(name)

                except Exception as e:
                    logger.warning(f"Konnte Fallback-Highlight nicht zeichnen: {e}")

        request_render(self.plotter)
        
        
    def set_edge_select_mode(self, enabled):
        """Aktiviert/deaktiviert den Edge-Selection-Modus für Fillet/Chamfer"""
        self.edge_select_mode = getattr(self, 'edge_select_mode', False)
        
        # Wenn wir umschalten
        if enabled != self.edge_select_mode:
            self.edge_select_mode = enabled
            self.selected_edges = getattr(self, 'selected_edges', set())
            
            if enabled:
                # WICHTIG für Face-Picking im Edge-Mode:
                # Wir laden die Body-Faces in den Detector, damit _try_select_loop_from_face_click funktioniert
                self._update_detector_for_picking()
            else:
                self._clear_edge_highlights()

   

    def _highlight_all_edges(self):
        """Zeigt alle Kanten der Bodies als selektierbar an"""
        try:
            for bid, body_data in self.bodies.items():
                mesh = body_data.get('mesh')
                if mesh:
                    edges = mesh.extract_feature_edges(feature_angle=30)
                    name = f"edges_highlight_{bid}"
                    self.plotter.add_mesh(edges, color='yellow', line_width=2, 
                                         name=name, opacity=0.7)
            self.plotter.update()
        except Exception as e:
            logger.error(f" {e}")
    
    def _clear_edge_highlights(self):
        """Entfernt alle Edge-Highlights"""
        try:
            for bid in self.bodies.keys():
                name = f"edges_highlight_{bid}"
                try:
                    self.plotter.remove_actor(name)
                except Exception as e:
                    logger.debug(f"[viewport] Fehler beim Entfernen Edge-Highlight {name}: {e}")
            self.plotter.update()
        except Exception as e:
            logger.debug(f"[viewport] Fehler beim Entfernen Edge-Highlights: {e}")

    def mark_edge_as_failed(self, edge_idx):
        """Markiert eine Kante visuell als fehlgeschlagen (rot)."""
        try:
            from gui.viewport.edge_selection_mixin import EdgeSelectionMixin
            if hasattr(self, '_edge_data') and edge_idx < len(self._edge_data):
                edge = self._edge_data[edge_idx]
                p1, p2 = edge.get('p1'), edge.get('p2')
                if p1 is not None and p2 is not None:
                    import pyvista as pv
                    line = pv.Line(p1, p2)
                    self.plotter.add_mesh(line, color='red', line_width=4,
                                          name=f'failed_edge_{edge_idx}', pickable=False)
        except Exception as e:
            logger.debug(f"mark_edge_as_failed: {e}")

    def _restore_body_colors(self):
        """Stellt Original-Farben aller Bodies wieder her"""
        # FIX: Variable Anzahl von Actors unterstützen
        for bid, actors in self._body_actors.items():
            try:
                if not actors: continue
                mesh_name = actors[0] # Das erste Element ist immer das Mesh
                
                if mesh_name in self.plotter.renderer.actors:
                    actor = self.plotter.renderer.actors[mesh_name]
                    prop = actor.GetProperty()
                    if bid in self.bodies:
                        col = self.bodies[bid].get('color', (0.6, 0.6, 0.8))
                        prop.SetColor(*col)
                        prop.SetOpacity(1.0)
            except Exception as e:
                logger.debug(f"[viewport] Fehler beim Wiederherstellen Body-Farbe {bid}: {e}")
        request_render(self.plotter)
    
    def _get_cells_for_detector_face(self, detector_face, mesh):
        """
        Findet alle cell_ids (Dreiecke) die zu einer Detector-Face gehören.

        KONSISTENZ: Verwendet die gleiche Logik wie bei Body-Face Detection.

        Args:
            detector_face: Face vom GeometryDetector
            mesh: PyVista Mesh des Bodies

        Returns:
            List von cell_ids (Dreiecke) die zu dieser Face gehören
        """
        import numpy as np

        if mesh is None or mesh.n_cells == 0:
            return []

        # Berechne Normalen falls nötig
        if 'Normals' not in mesh.cell_data:
            mesh.compute_normals(cell_normals=True, inplace=True)

        cell_normals = mesh.cell_data.get('Normals')
        if cell_normals is None:
            return []

        # Face-Normal und Origin
        face_normal = np.array(detector_face.plane_normal)
        face_origin = np.array(detector_face.plane_origin)

        # Finde alle Zellen mit ähnlicher Normale und naher Position
        NORMAL_THRESHOLD = 0.1  # Winkeltoleranz
        DISTANCE_THRESHOLD = 5.0  # mm - räumliche Toleranz

        cell_centers = mesh.cell_centers().points
        cell_ids = []

        for i, (cell_normal, cell_center) in enumerate(zip(cell_normals, cell_centers)):
            # Prüfe Normale (Dot-Product nahe 1 oder -1)
            dot = np.dot(face_normal, cell_normal)
            if abs(abs(dot) - 1.0) > NORMAL_THRESHOLD:
                continue

            # Prüfe räumliche Nähe (Projektion auf Ebene)
            # Distanz des Zellzentrums zur Face-Ebene
            dist_to_plane = abs(np.dot(cell_center - face_origin, face_normal))
            if dist_to_plane > DISTANCE_THRESHOLD:
                continue

            cell_ids.append(i)

        logger.trace(f"Detector-Face → {len(cell_ids)} Dreiecke gefunden (Normal={face_normal}, Origin={face_origin})")
        return cell_ids

    def _detect_brep_faces_for_texture(self, body_id: str):
        """
        Lädt B-Rep Faces aus face_info für Texture Face Selection.

        PERFORMANCE: Verwendet vorberechnete face_info aus tessellate_with_face_ids()
        statt Mesh-Triangle Clustering. Dadurch werden echte B-Rep Faces erkannt,
        nicht einzelne Tessellations-Dreiecke!

        Args:
            body_id: ID des Bodies dessen Faces geladen werden sollen
        """
        body_data = self.bodies.get(body_id)
        if not body_data:
            logger.warning(f"Body {body_id} nicht in self.bodies gefunden")
            return

        mesh = body_data.get('mesh')
        if mesh is None or not hasattr(mesh, 'cell_data'):
            logger.warning(f"Body {body_id} hat kein gültiges Mesh")
            return

        # Prüfe ob Mesh face_id cell_data hat (von tessellate_with_face_ids)
        if 'face_id' not in mesh.cell_data:
            logger.warning(f"Body {body_id} Mesh hat keine face_id cell_data - fallback zu Clustering")
            self._detect_body_faces()  # Fallback
            return

        # Hole face_info vom Body-Objekt (falls verfügbar)
        body_obj = self._body_objects.get(body_id)
        face_info = getattr(body_obj, '_face_info_cache', None) if body_obj else None

        if not face_info:
            logger.warning(f"Body {body_id} hat keine _face_info_cache - fallback zu Clustering")
            self._detect_body_faces()  # Fallback
            return

        # Erstelle detected_faces aus face_info
        import numpy as np
        face_ids_array = mesh.cell_data['face_id']

        logger.debug(f"B-Rep Face Detection: {len(face_info)} Faces, {mesh.n_cells} cells")

        for face_id, info in face_info.items():
            # Finde alle Zellen (Dreiecke) die zu dieser B-Rep Face gehören
            cell_ids = np.where(face_ids_array == face_id)[0].tolist()

            if not cell_ids:
                continue

            # Berechne Zentrum der Face aus allen Dreiecken
            cell_centers = mesh.cell_centers().points
            face_cell_centers = cell_centers[cell_ids]
            center_3d = np.mean(face_cell_centers, axis=0)

            # detected_face erstellen
            detected_face = {
                'type': 'body_face',
                'body_id': body_id,
                'cell_ids': cell_ids,  # ALLE Dreiecke dieser Face!
                'normal': info.get('normal', (0, 0, 1)),
                'center_3d': tuple(center_3d),
                'center_2d': (center_3d[0], center_3d[1]),
                'origin': info.get('center', tuple(center_3d)),
                'mesh': mesh,
                'face_id': face_id  # B-Rep Face-ID
            }

            self.detected_faces.append(detected_face)
            logger.debug(f"  Face {face_id}: {len(cell_ids)} Dreiecke, Normal={info.get('normal')}")

        logger.success(f"✓ B-Rep Faces geladen: {len(self.detected_faces)} Faces mit korrekten cell_ids")

    def _detect_body_faces(self):
        """Erkennt Flächen von 3D-Bodies und fügt sie zu detected_faces hinzu.

        FIX: Nutzt face_id aus Tessellator für korrekte Zylinder-Face-Erkennung.
        Bei Zylindern haben alle Mantel-Dreiecke die gleiche face_id, aber
        unterschiedliche Normalen. Nach face_id zu gruppieren sorgt dafür, dass
        der ganze Zylinder-Mantel als eine Face erkannt wird (wie in Fusion 360).

        OPTIMIERT: Verwendet cell_centers() und numpy für 10x schnellere Detection.
        """
        if not self.bodies:
            return

        import numpy as np

        logger.debug(f"Starte Face-Detection für {len(self.bodies)} Bodies...")
        count_before = len(self.detected_faces)

        for bid, body_data in self.bodies.items():
            mesh = body_data.get('mesh')
            if mesh is None:
                continue

            try:
                # Prüfen ob Mesh Zellen hat
                if mesh.n_cells == 0:
                    logger.debug(f"Body {bid} hat keine Zellen (Faces).")
                    continue

                # FIX: ZUERST face_id-basierte Gruppierung versuchen (für Zylinder!)
                if 'face_id' in mesh.cell_data:
                    face_ids = np.asarray(mesh.cell_data['face_id']).astype(np.int64)
                    all_cell_centers = mesh.cell_centers().points

                    # Normalen für Highlight berechnen
                    if 'Normals' not in mesh.cell_data:
                        mesh.compute_normals(cell_normals=True, inplace=True)
                    cell_normals = mesh.cell_data.get('Normals')

                    # Gruppiere Zellen nach face_id
                    unique_face_ids = np.unique(face_ids)

                    logger.debug(f"Body {bid}: {len(unique_face_ids)} unique face_ids")

                    for face_id in unique_face_ids:
                        # Finde alle Zellen mit dieser face_id
                        cell_mask = (face_ids == face_id)
                        cell_ids = np.where(cell_mask)[0]

                        if len(cell_ids) == 0:
                            continue

                        # Berechne durchschnittliche Normale und Center für diese Face
                        group_normals = cell_normals[cell_mask]
                        group_centers = all_cell_centers[cell_mask]
                        center_3d = np.mean(group_centers, axis=0)
                        avg_normal = np.mean(group_normals, axis=0)
                        norm_length = np.linalg.norm(avg_normal)
                        if norm_length > 1e-10:
                            avg_normal = avg_normal / norm_length
                        normal_key = tuple(avg_normal)

                        # Face registrieren
                        self.detected_faces.append({
                            'type': 'body_face',
                            'body_id': bid,
                            'cell_ids': cell_ids.tolist(),
                            'normal': normal_key,
                            'center_3d': tuple(center_3d),
                            'sample_point': tuple(group_centers[0]),
                            'center_2d': (center_3d[0], center_3d[1]),
                            'origin': tuple(center_3d),
                            'mesh': mesh,
                            'face_id': int(face_id)  # Für Debug/Reference
                        })

                    logger.debug(f"Body {bid}: {len(unique_face_ids)} Faces via face_id detected")
                    continue  # Nächsten Body verarbeiten

                # FALLBACK: Normalen-basierte Gruppierung (wenn kein face_id verfügbar)
                # Normalen berechnen falls nötig
                if 'Normals' not in mesh.cell_data:
                    mesh.compute_normals(cell_normals=True, inplace=True)

                cell_normals = mesh.cell_data.get('Normals')
                if cell_normals is None or len(cell_normals) == 0:
                    logger.debug(f"Keine Normalen für Body {bid} gefunden.")
                    continue

                # OPTIMIERUNG: Cell centers einmal vorberechnen (viel schneller als get_cell!)
                all_cell_centers = mesh.cell_centers().points

                # Runde Normalen für Gruppierung (Quantisierung)
                rounded_normals = np.round(cell_normals, 2)

                # OPTIMIERUNG: Numpy-basierte Gruppierung statt Python-Loop
                # Erstelle eindeutige Normal-Keys
                unique_normals, inverse_indices = np.unique(
                    rounded_normals, axis=0, return_inverse=True
                )

                # Für jede eindeutige Normale Face-Gruppen erstellen
                # WICHTIG: Faces mit gleicher Normale aber unterschiedlicher Position TRENNEN!
                for group_idx, normal in enumerate(unique_normals):
                    # Finde alle Zellen mit dieser Normale
                    cell_mask = (inverse_indices == group_idx)
                    cell_ids = np.where(cell_mask)[0]

                    if len(cell_ids) == 0:
                        continue

                    # OPTIMIERUNG: Zentren aus vorberechneten Cell-Centers
                    group_centers = all_cell_centers[cell_mask]

                    # SUB-GRUPPIERUNG: Faces mit gleicher Normale aber weit auseinander trennen
                    # z.B. obere/untere Z-Fläche haben beide Normal=(0,0,±1) aber unterschiedliche Z-Position
                    SPATIAL_THRESHOLD = 5.0  # mm - Faces weiter auseinander = separate Faces

                    # Starte mit erster Zelle als Seed
                    remaining_indices = list(range(len(cell_ids)))
                    while remaining_indices:
                        # Neue Sub-Gruppe starten
                        seed_idx = remaining_indices[0]
                        seed_center = group_centers[seed_idx]
                        sub_group_indices = [seed_idx]
                        remaining_indices.remove(seed_idx)

                        # Finde alle Zellen nahe am Seed
                        indices_to_remove = []
                        for idx in remaining_indices:
                            dist = np.linalg.norm(group_centers[idx] - seed_center)
                            if dist < SPATIAL_THRESHOLD:
                                sub_group_indices.append(idx)
                                indices_to_remove.append(idx)

                        for idx in indices_to_remove:
                            remaining_indices.remove(idx)

                        # Face für diese Sub-Gruppe registrieren
                        sub_cell_ids = cell_ids[sub_group_indices].tolist()
                        sub_centers = group_centers[sub_group_indices]
                        center_3d = np.mean(sub_centers, axis=0)
                        sample_point = sub_centers[0]  # Erstes Dreieckszentrum
                        normal_key = tuple(normal)

                        self.detected_faces.append({
                            'type': 'body_face',
                            'body_id': bid,
                            'cell_ids': sub_cell_ids,
                            'normal': normal_key,
                            'center_3d': tuple(center_3d),
                            'sample_point': tuple(sample_point),
                            'center_2d': (center_3d[0], center_3d[1]),
                            'origin': tuple(center_3d),
                            'mesh': mesh
                        })

            except Exception as e:
                logger.debug(f"Body face detection error for body {bid}: {e}")
                import traceback
                traceback.print_exc()

        added = len(self.detected_faces) - count_before
        logger.debug(f"Detection fertig. {added} Body-Faces gefunden.")

    def set_sketches(self, sketches):
        """
        Zeichnet 2D-Sketches im 3D-Raum (Batch-Rendering V2.1 - Fix).
        Unterstützt 2-Tupel (sketch, visible) und 3-Tupel (sketch, visible, is_inactive).
        """
        self.sketches = list(sketches)
        if not HAS_PYVISTA: return

        # 1. Alte Sketch-Actors entfernen
        for n in self._sketch_actors:
            _safe_remove_actor(self.plotter, n, "sketch actor cleanup")
        self._sketch_actors.clear()

        # 2. Sketches rendern
        for sketch_info in self.sketches:
            # Backward-compatible: 2- oder 3-Tupel
            if len(sketch_info) == 3:
                s, visible, is_inactive = sketch_info
            else:
                s, visible = sketch_info
                is_inactive = False

            if visible:
                self._render_sketch_batched(s, inactive_component=is_inactive)

        request_render(self.plotter)

    def _render_sketch_batched(self, s, inactive_component=False):
        """
        Kombiniert Geometrie zu einem Mesh (High-Performance).
        FIX: Nutzt explizit 'lines=' für PolyData.

        Args:
            s: Sketch-Objekt
            inactive_component: True wenn Sketch zu inaktiver Component gehört (gedimmte Darstellung)
        """
        sid = getattr(s, 'id', id(s))
        norm = tuple(getattr(s, 'plane_normal', (0,0,1)))
        orig = getattr(s, 'plane_origin', (0,0,0))
        
        # Caching der Achsen
        cached_x = getattr(s, 'plane_x_dir', None)
        cached_y = getattr(s, 'plane_y_dir', None)
        
        if cached_x and cached_y:
            ux, uy, uz = cached_x
            vx, vy, vz = cached_y
            ox, oy, oz = orig
        else:
            (ux, uy, uz), (vx, vy, vz) = self._calculate_plane_axes(norm)
            ox, oy, oz = orig

        # Listen für Punkte: Immer [Start, End, Start, End, ...]
        reg_points = []
        const_points = []
        
        def to_3d(lx, ly):
            return (
                ox + lx * ux + ly * vx,
                oy + lx * uy + ly * vy,
                oz + lx * uz + ly * vz
            )

        # --- 1. Linien ---
        for l in getattr(s, 'lines', []):
            p1 = to_3d(l.start.x, l.start.y)
            p2 = to_3d(l.end.x, l.end.y)
            target = const_points if getattr(l, 'construction', False) else reg_points
            target.extend([p1, p2])

        # --- Helper für Kurven ---
        def add_poly_segments(points_2d_list, is_const):
            target = const_points if is_const else reg_points
            # Wandle 2D Punkte in 3D Linien-Segmente um
            pts_3d = [to_3d(p[0], p[1]) for p in points_2d_list]
            for i in range(len(pts_3d) - 1):
                target.append(pts_3d[i])
                target.append(pts_3d[i+1])

        # --- 2. Kreise ---
        for c in getattr(s, 'circles', []):
            pts = []
            steps = 64
            for j in range(steps + 1):
                angle = j * 2 * math.pi / steps
                lx = c.center.x + c.radius * math.cos(angle)
                ly = c.center.y + c.radius * math.sin(angle)
                pts.append((lx, ly))
            add_poly_segments(pts, getattr(c, 'construction', False))

        # --- 3. Bögen (Arcs) ---
        for arc in getattr(s, 'arcs', []):
            pts = []
            start, end = arc.start_angle, arc.end_angle
            sweep = end - start
            if sweep < 0.1: sweep += 360
            steps = max(12, int(sweep / 5))
            
            for j in range(steps + 1):
                t = math.radians(start + sweep * (j / steps))
                lx = arc.center.x + arc.radius * math.cos(t)
                ly = arc.center.y + arc.radius * math.sin(t)
                pts.append((lx, ly))
            add_poly_segments(pts, getattr(arc, 'construction', False))
            
        # --- 4. Splines ---
        for spline in getattr(s, 'splines', []):
            pts_2d = []
            # Versuche Punkte zu holen
            if hasattr(spline, 'get_curve_points'):
                 pts_2d = spline.get_curve_points(segments_per_span=10)
            elif hasattr(spline, 'to_lines'):
                 lines = spline.to_lines(segments_per_span=10)
                 if lines:
                     pts_2d.append((lines[0].start.x, lines[0].start.y))
                     for l in lines: pts_2d.append((l.end.x, l.end.y))
            
            if len(pts_2d) > 1:
                add_poly_segments(pts_2d, getattr(spline, 'construction', False))
        
        # --- 5. Ellipsen ---
        for ellipse in getattr(s, 'ellipses', []):
            pts = []
            steps = 64
            for j in range(steps + 1):
                angle = j * 360 / steps
                pt = ellipse.point_at_angle(angle)
                pts.append((pt.x, pt.y))
            add_poly_segments(pts, getattr(ellipse, 'construction', False))

        # --- BATCH MESH ERSTELLEN (FIXED) ---
        def create_lines_mesh(point_list):
            if not point_list: return None
            points = np.array(point_list)
            n_segments = len(point_list) // 2
            
            # Zellen-Array für VTK Lines: [AnzahlPunkte, Index1, Index2, AnzahlPunkte, ...]
            # Da es Liniensegmente sind, ist AnzahlPunkte immer 2.
            cells = np.full((n_segments, 3), 2, dtype=int)
            cells[:, 1] = np.arange(0, len(point_list), 2)
            cells[:, 2] = np.arange(1, len(point_list), 2)
            
            # WICHTIG: 'lines=' Parameter verwenden, nicht positionales Argument!
            return pv.PolyData(points, lines=cells.flatten())

        # Actors hinzufügen - bei inaktiven Components gedimmte Farben
        if inactive_component:
            reg_color = '#666666'    # Grau statt Blau für inaktive
            const_color = '#444444'  # Dunkelgrau
            reg_opacity = 0.4
            const_opacity = 0.3
        else:
            reg_color = '#4d94ff'    # Blau für aktive Component
            const_color = 'gray'
            reg_opacity = 1.0
            const_opacity = 0.6

        if reg_points:
            mesh = create_lines_mesh(reg_points)
            name = f"sketch_{sid}_reg"
            self.plotter.add_mesh(mesh, color=reg_color, line_width=3, name=name, pickable=False, opacity=reg_opacity)
            self._sketch_actors.append(name)

        if const_points:
            mesh = create_lines_mesh(const_points)
            name = f"sketch_{sid}_const"
            self.plotter.add_mesh(mesh, color=const_color, line_width=1, name=name, pickable=False, opacity=const_opacity)
            self._sketch_actors.append(name)

    def set_all_bodies_opacity(self, opacity: float):
        """
        Setzt die Transparenz aller Bodies (X-Ray Mode).

        Args:
            opacity: 0.0 = vollständig transparent, 1.0 = vollständig undurchsichtig
        """
        opacity = max(0.0, min(1.0, opacity))  # Clamp to [0, 1]
        for body_id in self._body_actors:
            try:
                m, e = self._body_actors[body_id]
                mesh_actor = self.plotter.renderer.actors.get(m)
                edge_actor = self.plotter.renderer.actors.get(e)
                if mesh_actor:
                    mesh_actor.GetProperty().SetOpacity(opacity)
                if edge_actor:
                    # Edges etwas sichtbarer lassen für bessere Orientierung
                    edge_actor.GetProperty().SetOpacity(min(1.0, opacity + 0.3))
            except Exception as e:
                _log_suppressed_exception(f"body opacity set (body_id='{body_id}')", e)
        request_render(self.plotter)

    def set_body_opacity(self, body_id: str, opacity: float):
        """
        Setzt die Transparenz eines einzelnen Bodies.

        Args:
            body_id: ID des Bodies
            opacity: 0.0 = vollständig transparent, 1.0 = vollständig undurchsichtig
        """
        opacity = max(0.0, min(1.0, opacity))
        if body_id not in self._body_actors:
            return
        try:
            m, e = self._body_actors[body_id]
            mesh_actor = self.plotter.renderer.actors.get(m)
            edge_actor = self.plotter.renderer.actors.get(e)
            if mesh_actor:
                mesh_actor.GetProperty().SetOpacity(opacity)
            if edge_actor:
                edge_actor.GetProperty().SetOpacity(min(1.0, opacity + 0.3))
            # Speichere Opacity im Body-Dict für spätere Referenz
            if body_id in self.bodies:
                self.bodies[body_id]['opacity'] = opacity
        except Exception as e:
            _log_suppressed_exception(f"single body opacity set (body_id='{body_id}')", e)
        request_render(self.plotter)

    def update_single_body(self, body, color=None, inactive_component=False):
        """
        Aktualisiert NUR EINEN Body - ohne andere Bodies zu berühren.

        Performance-Optimierung: Kein Flicker für unveränderte Bodies.
        Phase 9: Unterstützt async Tessellation wenn Feature-Flag aktiv.

        Args:
            body: Body-Objekt mit vtk_mesh
            color: Optional - Farbe
            inactive_component: True wenn in inaktiver Component
        """
        default_color = (0.7, 0.7, 0.7)
        col = color if color else getattr(body, 'color', default_color)
        if col is None:
            col = default_color
        requested_visible = bool(
            self.bodies.get(body.id, {}).get('requested_visible', True)
        )

        # Phase 9: Async Tessellation
        if hasattr(body, 'request_async_tessellation'):
            if not hasattr(body, '_mesh_cache_valid') or not body._mesh_cache_valid:
                # Mesh ist invalid → async tessellieren
                def _on_async_mesh_ready(body_id, mesh, edges, face_info):
                    """Callback: Mesh fertig, Actor im Main-Thread aktualisieren."""
                    if mesh is None:
                        return
                    self.clear_bodies(only_body_id=body_id)
                    self.add_body(
                        bid=body_id,
                        name=body.name,
                        mesh_obj=mesh,
                        edge_mesh_obj=edges,
                        color=col,
                        visible=requested_visible,
                        inactive_component=inactive_component
                    )
                    if body_id in self.bodies:
                        self.bodies[body_id]['body'] = body
                        self.bodies[body_id]['body_ref'] = body
                    self._lod_applied_quality[body_id] = self._lod_quality_high
                    if hasattr(self, 'plotter'):
                        from gui.viewport.render_queue import request_render
                        request_render(self.plotter, immediate=True)

                body.request_async_tessellation(on_ready=_on_async_mesh_ready)
                return True

        # Synchroner Pfad (Mesh bereits im Cache)
        if not hasattr(body, 'vtk_mesh') or body.vtk_mesh is None:
            return False

        # Alten Actor entfernen (nur für diesen Body!)
        self.clear_bodies(only_body_id=body.id)

        # Neuen Actor hinzufügen
        self.add_body(
            bid=body.id,
            name=body.name,
            mesh_obj=body.vtk_mesh,
            edge_mesh_obj=body.vtk_edges,
            color=col,
            visible=requested_visible,
            inactive_component=inactive_component
        )

        if body.id in self.bodies:
            self.bodies[body.id]['body'] = body
            self.bodies[body.id]['body_ref'] = body
            self._lod_applied_quality[body.id] = self._lod_quality_high

        return True

    def set_body_object(self, body_id: str, body_obj):
        """Setzt die Body-Objekt-Referenz für Texture-Previews."""
        if body_id in self.bodies:
            self.bodies[body_id]['body'] = body_obj
            self.bodies[body_id]['body_ref'] = body_obj
            self._lod_applied_quality.setdefault(body_id, self._lod_quality_high)
            self._pending_body_refs.pop(body_id, None)
        else:
            # Async update path: Body may be added after this call.
            self._pending_body_refs[body_id] = body_obj

        # FIX Phase 7: Detector aktualisieren wenn Selection-Mode aktiv
        # Jetzt ist face_info verfügbar (Body-Objekt gesetzt)
        if getattr(self, 'edge_select_mode', False) or getattr(self, 'face_selection_mode', False):
            self._update_detector_for_picking()

    def set_body_appearance(self, body_id: str, opacity: float = None, color: tuple = None, inactive: bool = None):
        """
        Ändert Opacity/Farbe eines Body-Actors OHNE ihn zu entfernen/neu hinzuzufügen.

        Performance-Optimierung: Vermeidet Flackern bei Component-Aktivierung.

        Args:
            body_id: ID des Bodies
            opacity: Neue Opacity (0.0-1.0), None = nicht ändern
            color: Neue Farbe (r,g,b), None = nicht ändern
            inactive: Wenn True, wird grau + 35% opacity gesetzt
        """
        if body_id not in self._body_actors:
            return False

        actor_names = self._body_actors.get(body_id, [])
        mesh_actor_name = f"body_{body_id}_m"

        # Actor aus PyVista holen
        if mesh_actor_name not in self.plotter.renderer.actors:
            return False

        actor = self.plotter.renderer.actors[mesh_actor_name]

        # Inactive-Modus: Grau + Transparent + nicht pickable
        if inactive is not None:
            if inactive:
                opacity = 0.35
                color = (0.5, 0.5, 0.5)  # Grau
                actor.SetPickable(False)  # Inaktive Bodies nicht anklickbar
            else:
                opacity = 1.0
                # Farbe aus bodies-Dict wiederherstellen
                if body_id in self.bodies and 'color' in self.bodies[body_id]:
                    color = self.bodies[body_id]['color']
                actor.SetPickable(True)  # Aktive Bodies anklickbar

        # Opacity setzen
        if opacity is not None:
            prop = actor.GetProperty()
            prop.SetOpacity(opacity)
            # Auch in bodies-Dict speichern
            if body_id in self.bodies:
                self.bodies[body_id]['opacity'] = opacity

        # Farbe setzen
        if color is not None:
            prop = actor.GetProperty()
            prop.SetColor(color[0], color[1], color[2])
            # Auch in bodies-Dict speichern
            if body_id in self.bodies:
                self.bodies[body_id]['color'] = color

        # Render anfordern (kein full refresh!)
        request_render(self.plotter)
        return True

    def set_component_bodies_inactive(self, body_ids: list, inactive: bool):
        """
        Setzt mehrere Bodies auf aktiv/inaktiv Aussehen.

        Performance-Optimierung für Component-Aktivierung.

        Args:
            body_ids: Liste von Body-IDs
            inactive: True = grau/transparent, False = normal
        """
        changed = False
        for bid in body_ids:
            if self.set_body_appearance(bid, inactive=inactive):
                changed = True

        if changed:
            request_render(self.plotter, immediate=True)

        return changed

    def refresh_texture_previews(self, body_id: str = None):
        """
        Aktualisiert alle Texture-Previews für einen Body oder alle Bodies.

        Args:
            body_id: Wenn angegeben, nur diesen Body aktualisieren
        """
        from modeling import SurfaceTextureFeature

        body_ids = [body_id] if body_id else list(self.bodies.keys())

        for bid in body_ids:
            if bid not in self.bodies:
                continue

            body_data = self.bodies[bid]
            body = body_data.get('body')
            mesh = body_data.get('mesh')

            if body is None or mesh is None:
                continue

            # Sammle alle Texture-Features für diesen Body
            texture_features = [
                f for f in body.features
                if isinstance(f, SurfaceTextureFeature) and not f.suppressed
            ]

            if not texture_features:
                # Keine Texturen - alte Overlays entfernen
                self._clear_textured_faces_overlay(bid)
                continue

            # Für jedes Texture-Feature die Face-Daten sammeln
            # WICHTIG: Jede Face bekommt ihr eigenes Texture-Feature!
            face_data_list = []
            mesh_face_ids = None
            shape_service = None
            solid = getattr(body, "_build123d_solid", None)
            try:
                if hasattr(mesh, "cell_data") and "face_id" in mesh.cell_data:
                    mesh_face_ids = np.asarray(mesh.cell_data["face_id"]).astype(np.int64)
            except Exception:
                mesh_face_ids = None

            if getattr(body, "_document", None) is not None:
                shape_service = getattr(body._document, "_shape_naming_service", None)

            for feat in texture_features:
                selectors = list(getattr(feat, "face_selectors", []) or [])
                face_indices = list(getattr(feat, "face_indices", []) or [])
                face_shape_ids = list(getattr(feat, "face_shape_ids", []) or [])
                has_topological_refs = bool(face_indices or face_shape_ids)
                added_from_topology = False

                seen_indices = set()

                def _add_face_data(face_idx: int, selector_idx: int = -1) -> bool:
                    if mesh_face_ids is None:
                        return False

                    try:
                        face_idx = int(face_idx)
                    except Exception:
                        return False

                    if face_idx in seen_indices:
                        return False

                    try:
                        cell_ids = np.where(mesh_face_ids == face_idx)[0].astype(np.int64).tolist()
                    except Exception:
                        cell_ids = []

                    if not cell_ids:
                        return False

                    seen_indices.add(face_idx)
                    selector = (
                        selectors[selector_idx]
                        if (
                            selector_idx >= 0
                            and selector_idx < len(selectors)
                            and isinstance(selectors[selector_idx], dict)
                        )
                        else {}
                    )
                    face_data_list.append({
                        'cell_ids': cell_ids,
                        'normal': selector.get('normal', (0, 0, 1)),
                        'center': selector.get('center', (0, 0, 0)),
                        'texture_feature': feat,
                    })
                    return True

                # TNP v4.0 primary: Face-Indizes -> aktuelle Mesh-cell_ids mappen.
                for i, raw_idx in enumerate(face_indices):
                    if _add_face_data(raw_idx, i):
                        added_from_topology = True

                # TNP v4.0 secondary: ShapeIDs -> FaceIndex -> Mesh-cell_ids.
                if (
                    not added_from_topology
                    and face_shape_ids
                    and shape_service is not None
                    and solid is not None
                ):
                    try:
                        from build123d import Face
                        from modeling.topology_indexing import face_index_of

                        ocp_solid = solid.wrapped if hasattr(solid, "wrapped") else solid
                        for i, shape_id in enumerate(face_shape_ids):
                            if not hasattr(shape_id, "uuid"):
                                continue
                            try:
                                resolved_ocp, _method = shape_service.resolve_shape_with_method(
                                    shape_id,
                                    ocp_solid,
                                    log_unresolved=False,
                                )
                            except Exception:
                                continue
                            if resolved_ocp is None:
                                continue
                            try:
                                face_idx = face_index_of(solid, Face(resolved_ocp))
                            except Exception:
                                face_idx = None
                            if face_idx is None:
                                continue
                            if _add_face_data(face_idx, i):
                                added_from_topology = True
                    except Exception:
                        pass

                if added_from_topology:
                    continue

                # Legacy/Recovery nur wenn Feature keine topologischen Refs hat.
                if not added_from_topology and not has_topological_refs:
                    for selector in selectors:
                        if not isinstance(selector, dict):
                            continue
                        face_data = {
                            'cell_ids': selector.get('cell_ids', []),
                            'normal': selector.get('normal', (0, 0, 1)),
                            'center': selector.get('center', (0, 0, 0)),
                            'texture_feature': feat,  # WICHTIG: Feature mit Face verknüpfen!
                        }
                        if face_data['cell_ids']:
                            face_data_list.append(face_data)

            if face_data_list:
                self.show_textured_faces_overlay(bid, face_data_list, 'mixed')

        if is_enabled("viewport_debug"):
            logger.debug(f"Texture-Previews aktualisiert für {len(body_ids)} Bodies")

    def get_selected_faces(self):
        return [self.detected_faces[i] for i in self.selected_faces if i < len(self.detected_faces)]

    # ==================== Texture Face Selection Mode ====================

    def start_texture_face_mode(self, body_id: str):
        """Startet Face-Selektionsmodus für Surface Texture - GENAU WIE EXTRUDE."""
        self.texture_face_mode = True
        self._texture_body_id = body_id
        self._texture_selected_faces = []

        # KONSISTENZ: Nutze das gleiche System wie Extrude (Detector)
        logger.debug("🔄 Texture Mode: Lade Detector wie bei Extrude")
        self._update_detector_for_picking()

        # Debug: Zeige erkannte Faces vom Detector
        n_faces = len(self.detector.selection_faces) if hasattr(self, 'detector') else 0
        body_faces = [f for f in (self.detector.selection_faces if hasattr(self, 'detector') else [])
                     if f.domain_type == 'body_face' and f.owner_id == body_id]
        logger.info(f"Texture Mode: Detector hat {n_faces} Faces total, {len(body_faces)} vom Body '{body_id}'")

        self.setCursor(Qt.PointingHandCursor)
        logger.info(f"Texture Mode: Klicke auf Faces von Body '{body_id}'")
        request_render(self.plotter)

    def stop_texture_face_mode(self):
        """Beendet Face-Selektionsmodus für Texture."""
        self.texture_face_mode = False
        self._texture_body_id = None
        self._texture_selected_faces = []
        self._clear_texture_face_highlights()
        self._clear_body_face_highlight()  # Auch Hover-Highlight entfernen
        self.hovered_body_face = None
        self.setCursor(Qt.ArrowCursor)
        request_render(self.plotter)

    def get_texture_selected_faces(self):
        """Gibt selektierte Face-Daten für Texture zurück."""
        return self._texture_selected_faces

    def _add_texture_face(self, face_data: dict):
        """Fügt Face zur Texture-Selektion hinzu."""
        # Prüfen ob Face schon selektiert (anhand der Normalen - gleiche Fläche = gleiche Normale)
        new_normal = face_data.get('normal', (0, 0, 1))

        for f in self._texture_selected_faces:
            existing_normal = f.get('normal', (0, 0, 1))
            # Vergleiche Normalen (Toleranz für Rundungsfehler)
            if (abs(existing_normal[0] - new_normal[0]) < 0.01 and
                abs(existing_normal[1] - new_normal[1]) < 0.01 and
                abs(existing_normal[2] - new_normal[2]) < 0.01):
                # Gleiche Fläche bereits selektiert → deselektieren
                self._texture_selected_faces.remove(f)
                self._update_texture_face_highlights()
                self.texture_face_selected.emit(len(self._texture_selected_faces))
                logger.debug(f"Face deselektiert (Normal: {new_normal})")
                return

        # Neu hinzufügen
        self._texture_selected_faces.append(face_data)
        self._update_texture_face_highlights()
        self.texture_face_selected.emit(len(self._texture_selected_faces))
        logger.debug(f"Face selektiert (Normal: {new_normal})")

    def _update_texture_face_highlights(self):
        """Aktualisiert Highlight für selektierte Texture-Faces."""
        self._clear_texture_face_highlights()

        for i, face_data in enumerate(self._texture_selected_faces):
            try:
                mesh = face_data.get('mesh')
                cell_ids = face_data.get('cell_ids', [])

                if mesh is not None and cell_ids:
                    # Echtes Face-Overlay wie bei Extrude
                    face_mesh = mesh.extract_cells(cell_ids)

                    # WICHTIG: Offset entlang Normalen um Z-Fighting zu vermeiden!
                    # Das Highlight wird 1.0mm nach außen verschoben (erhöht für bessere Sichtbarkeit bei Texturen)
                    face_normal = face_data.get('normal', (0, 0, 1))
                    offset = 1.0  # mm - erhöht für Texture-Mode
                    normal_arr = np.array(face_normal)
                    normal_arr = normal_arr / (np.linalg.norm(normal_arr) + 1e-10)

                    # Verschiebe alle Punkte des Face-Mesh
                    face_mesh_copy = face_mesh.copy()
                    face_mesh_copy.points = face_mesh_copy.points + normal_arr * offset

                    self.plotter.add_mesh(
                        face_mesh_copy,
                        color='orange',
                        opacity=0.7,
                        name=f'texture_face_highlight_{i}',
                        pickable=False,
                        show_edges=True,
                        edge_color='darkorange',
                        line_width=2
                    )
                else:
                    # Fallback: Punkt am Zentrum
                    center = face_data.get('center', (0, 0, 0))
                    import pyvista as pv
                    point = pv.PolyData([center])
                    self.plotter.add_mesh(
                        point,
                        color='orange',
                        point_size=15,
                        render_points_as_spheres=True,
                        name=f'texture_face_highlight_{i}'
                    )
            except Exception as e:
                logger.debug(f"Texture Face Highlight Error: {e}")

    def _clear_texture_face_highlights(self):
        """Entfernt Texture-Face-Highlights."""
        for i in range(50):  # Max 50 highlights
            try:
                self.plotter.remove_actor(f'texture_face_highlight_{i}')
            except Exception as e:
                logger.debug(f"[viewport] Fehler beim Entfernen Texture-Face-Highlight {i}: {e}")

    def show_textured_faces_overlay(self, body_id: str, face_data_list: list, texture_type: str):
        """
        Zeigt permanentes Overlay für texturierte Flächen.
        Jetzt mit ECHTER 3D-Geometrie (Displacement)!

        Args:
            body_id: ID des Bodies
            face_data_list: Liste mit {'cell_ids': [...], 'normal': (...), 'center': (...), 'texture_feature': ...}
            texture_type: Name der Textur für Logging (Fallback)
        """
        # Alte Overlays für diesen Body entfernen
        self._clear_textured_faces_overlay(body_id)

        if body_id not in self.bodies:
            logger.warning(f"Body {body_id} nicht gefunden für Texture-Overlay")
            return

        mesh = self.bodies[body_id].get('mesh')
        if mesh is None:
            return

        # Farben für verschiedene Textur-Typen
        texture_colors = {
            'ripple': '#4a90d9',
            'honeycomb': '#d9a54a',
            'diamond': '#9b59b6',
            'knurl': '#27ae60',
            'crosshatch': '#e74c3c',
            'voronoi': '#1abc9c',
            'custom': '#95a5a6',
        }

        for i, face_data in enumerate(face_data_list):
            cell_ids = face_data.get('cell_ids', [])
            if not cell_ids:
                continue

            # WICHTIG: Jede Face hat ihr eigenes Texture-Feature!
            texture_feature = face_data.get('texture_feature')
            face_texture_type = texture_feature.texture_type if texture_feature else texture_type

            try:
                # Face-Mesh extrahieren
                face_mesh = mesh.extract_cells(cell_ids)
                if face_mesh.n_cells == 0:
                    continue

                face_mesh = face_mesh.extract_surface()
                actor_name = f'textured_overlay_{body_id}_{i}'

                # Preview-Modus prüfen (displacement oder normal_map)
                preview_mode = getattr(self, '_preview_mode', 'displacement')
                from config.feature_flags import is_enabled
                
                # Echtes 3D-Displacement oder Normal-Map anwenden wenn Feature vorhanden
                if texture_feature is not None:
                    if preview_mode == 'normal_map' and is_enabled("normal_map_preview"):
                        # Normal-Map Preview (keine Geometrie-Änderung)
                        preview_mesh = self._apply_normal_map_preview(
                            face_mesh, face_data, texture_feature
                        )
                        if preview_mesh is not None:
                            face_mesh = preview_mesh
                            logger.debug(f"Normal-Map Preview für Face {i}: {face_texture_type}")
                    else:
                        # Displacement Preview (Standard)
                        displaced_mesh = self._apply_texture_preview(
                            face_mesh, face_data, texture_feature
                        )
                        if displaced_mesh is not None:
                            face_mesh = displaced_mesh
                            logger.debug(f"Displacement für Face {i} angewendet: {face_texture_type}")

                # Farbe basierend auf DIESEM Face's Textur-Typ
                color = texture_colors.get(face_texture_type, '#4a90d9')

                # Offset entlang Normalen um Z-Fighting zu vermeiden
                face_normal = face_data.get('normal', (0, 0, 1))
                normal_arr = np.array(face_normal)
                norm_len = np.linalg.norm(normal_arr)
                if norm_len > 0:
                    normal_arr = normal_arr / norm_len
                face_mesh.points = face_mesh.points + normal_arr * 0.15  # 0.15mm offset für Z-Fighting

                # Normalen neu berechnen für korrektes Shading
                face_mesh.compute_normals(inplace=True)

                self.plotter.add_mesh(
                    face_mesh,
                    color=color,
                    opacity=1.0,  # Vollständig opak für bessere Sichtbarkeit
                    name=actor_name,
                    pickable=False,
                    show_edges=False,  # Keine Edges - zeigt das 3D-Relief besser
                    smooth_shading=True,  # Glatte Schattierung für 3D-Effekt
                    specular=0.3,  # Etwas Glanz für bessere Tiefenwahrnehmung
                )
            except Exception as e:
                logger.warning(f"Texture-Overlay Fehler für Face {i}: {e}")
                import traceback
                traceback.print_exc()

        request_render(self.plotter)
        logger.info(f"3D-Texture-Preview für {len(face_data_list)} Faces angezeigt")

    def _apply_texture_preview(self, face_mesh, face_data, texture_feature):
        """
        Wendet Texture-Displacement für Preview an.
        Verwendet weniger Subdivisions für bessere Performance.
        """
        try:
            from modeling.surface_texture import TextureGenerator, sample_heightmap_at_uvs
            from modeling.texture_exporter import TextureExporter

            # Preview-Einstellungen: Adaptive Subdivisions basierend auf Quality-Modus
            # Quality-Modus aus Feature lesen: 0=Fast, 1=Balanced, 2=Detailed
            quality_mode = getattr(texture_feature, 'quality_mode', 1)  # Default: Balanced

            # Subdivisions basierend auf Quality-Modus
            if quality_mode == 0:  # Fast
                preview_subdivisions = 2  # ~250 Vertices (sehr schnell)
            elif quality_mode == 1:  # Balanced (Default)
                preview_subdivisions = 3  # ~500 Vertices (gute Balance)
            else:  # Detailed (2)
                preview_subdivisions = 5  # ~2000 Vertices (hohe Qualität)

            # 2 subdivisions = ~250 Vertices (sehr schnell, weniger Details)
            # 3 subdivisions = ~500 Vertices (gute Balance)
            # 5 subdivisions = ~2000 Vertices (hohe Qualität)

            # Kopie erstellen um Original nicht zu verändern
            face_mesh = face_mesh.copy()

            # Triangulieren falls nötig
            if not face_mesh.is_all_triangles:
                face_mesh = face_mesh.triangulate()

            # Subdividen für genug Vertices - loop für bessere Qualität bei gekrümmten Flächen
            face_mesh = face_mesh.subdivide(preview_subdivisions, subfilter='loop')

            # Normalen berechnen
            face_mesh.compute_normals(inplace=True)

            # UVs berechnen
            face_center = face_data.get('center', (0, 0, 0))
            face_normal = face_data.get('normal', (0, 0, 1))
            uvs = TextureExporter._compute_uvs(face_mesh, face_center, face_normal)

            # Heightmap generieren (mit wave_width Unterstützung)
            type_params = texture_feature.type_params.copy()
            wave_width = type_params.get("wave_width")
            
            if wave_width and wave_width > 0:
                # Berechne Face-Größe aus UV-Bounds
                u_min, u_max = uvs[:, 0].min(), uvs[:, 0].max()
                v_min, v_max = uvs[:, 1].min(), uvs[:, 1].max()
                face_size = max(u_max - u_min, v_max - v_min)
                
                # Berechne wave_count basierend auf Face-Größe und gewünschter Wellenbreite
                wave_count = face_size / wave_width
                type_params["wave_count"] = wave_count
                logger.debug(f"Preview Ripple: face_size={face_size:.2f}mm, wave_width={wave_width}mm, wave_count={wave_count:.2f}")

            heightmap = TextureGenerator.generate(
                texture_feature.texture_type,
                type_params,
                size=128  # Kleiner für Preview
            )

            # Heights sampeln
            heights = sample_heightmap_at_uvs(
                heightmap,
                uvs,
                scale=texture_feature.scale,
                rotation=texture_feature.rotation
            )

            # Debug: Height-Statistik
            logger.info(f"Preview Heights: min={heights.min():.3f}, max={heights.max():.3f}, "
                       f"mean={heights.mean():.3f}, std={heights.std():.3f}")

            # Invertieren falls gewünscht
            if texture_feature.invert:
                heights = 1.0 - heights

            # Displacement-Modus: solid_base=True = keine Löcher (nur positiv)
            solid_base = getattr(texture_feature, 'solid_base', True)
            if solid_base:
                # Verschiebe so dass Minimum bei 0 ist (keine Löcher)
                heights_shifted = heights - heights.min()
            else:
                # Bidirektional: -0.5 bis +0.5
                heights_shifted = heights - 0.5

            # Displacement anwenden
            depth = texture_feature.depth
            normals = face_mesh.point_data.get('Normals')

            if normals is None:
                normal_arr = np.array(face_normal)
                normal_arr = normal_arr / (np.linalg.norm(normal_arr) + 1e-10)
                normals = np.tile(normal_arr, (face_mesh.n_points, 1))
                logger.debug(f"Fallback-Normalen verwendet: {normal_arr}")

            # Displacement anwenden
            displacement = heights_shifted * depth
            mode_str = "solid" if solid_base else "bidirectional"
            logger.info(f"Preview Displacement ({mode_str}): min={displacement.min():.3f}mm, max={displacement.max():.3f}mm, "
                       f"depth={depth}mm, type={texture_feature.texture_type}")

            # Displacement anwenden
            face_mesh.points = face_mesh.points + normals * displacement[:, np.newaxis]

            logger.info(f"Preview erfolgreich: {face_mesh.n_points} Vertices, {texture_feature.texture_type}")
            return face_mesh

        except Exception as e:
            logger.error(f"Texture-Preview Fehler: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _apply_normal_map_preview(self, face_mesh, face_data, texture_feature):
        """
        Wendet Normal-Map-Preview an (ohne Geometry-Änderung).
        
        High-Priority TODO 2026: Normal-Map Preview im Viewport
        
        Modifiziert nur die Normalen für visuelle Darstellung des Textureffekts.
        Die Geometrie bleibt unverändert - nur die Beleuchtung reagiert anders.
        
        Args:
            face_mesh: PyVista Mesh der Face
            face_data: Face-Metadaten (center, normal)
            texture_feature: SurfaceTextureFeature mit Parametern
            
        Returns:
            Modifiziertes Mesh mit perturbierten Normalen
        """
        try:
            from modeling.surface_texture import (
                TextureGenerator, generate_normal_map_from_heightmap,
                sample_normal_map_at_uvs, apply_normal_perturbation
            )
            from modeling.texture_exporter import TextureExporter
            from config.feature_flags import is_enabled
            
            if not is_enabled("normal_map_preview"):
                return None
            
            # Kopie erstellen
            face_mesh = face_mesh.copy()
            
            # Normalen berechnen falls nicht vorhanden
            face_mesh.compute_normals(inplace=True)
            
            # UVs berechnen
            face_center = face_data.get('center', (0, 0, 0))
            face_normal = face_data.get('normal', (0, 0, 1))
            uvs = TextureExporter._compute_uvs(face_mesh, face_center, face_normal)
            
            # Heightmap generieren
            type_params = texture_feature.type_params.copy()
            wave_width = type_params.get("wave_width")
            
            if wave_width and wave_width > 0:
                u_min, u_max = uvs[:, 0].min(), uvs[:, 0].max()
                v_min, v_max = uvs[:, 1].min(), uvs[:, 1].max()
                face_size = max(u_max - u_min, v_max - v_min)
                wave_count = face_size / wave_width
                type_params["wave_count"] = wave_count
            
            heightmap = TextureGenerator.generate(
                texture_feature.texture_type,
                type_params,
                size=128  # Kleiner für Preview
            )
            
            # Normal-Map aus Heightmap generieren
            normal_strength = texture_feature.type_params.get("normal_strength", 1.0)
            normal_map = generate_normal_map_from_heightmap(heightmap, strength=normal_strength)
            
            # Normal-Map an UVs sampeln
            tangent_normals = sample_normal_map_at_uvs(
                normal_map,
                uvs,
                scale=texture_feature.scale,
                rotation=texture_feature.rotation
            )
            
            # Original-Normalen abrufen
            vertex_normals = face_mesh.point_data.get('Normals')
            if vertex_normals is None:
                # Fallback: Face-Normale für alle Vertices
                normal_arr = np.array(face_normal)
                normal_arr = normal_arr / (np.linalg.norm(normal_arr) + 1e-10)
                vertex_normals = np.tile(normal_arr, (face_mesh.n_points, 1))
            
            # Normalen perturbieren
            blend_factor = texture_feature.depth  # Tiefe als Blend-Faktor
            perturbed_normals = apply_normal_perturbation(
                vertex_normals, tangent_normals, blend_factor
            )
            
            # Perturbierte Normalen setzen
            face_mesh.point_data['Normals'] = perturbed_normals
            
            logger.info(f"Normal-Map Preview: {face_mesh.n_points} Vertices, "
                       f"strength={normal_strength:.2f}, blend={blend_factor:.2f}")
            
            return face_mesh
            
        except Exception as e:
            logger.error(f"Normal-Map Preview Fehler: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _clear_textured_faces_overlay(self, body_id: str):
        """Entfernt Texture-Overlays für einen Body."""
        for i in range(50):  # Max 50 Overlays pro Body
            try:
                self.plotter.remove_actor(f'textured_overlay_{body_id}_{i}')
            except Exception as e:
                logger.debug(f"[viewport] Fehler beim Entfernen Texture-Overlay {body_id}_{i}: {e}")

    def get_extrusion_data(self, face_idx, height):
        if face_idx < 0 or face_idx >= len(self.detected_faces): 
            return [], []
        
        face = self.detected_faces[face_idx]
        
        # Body-Face oder Sketch-Face?
        if face.get('type') == 'body_face':
            return self._calculate_body_face_extrusion(face, height)
        else:
            return self._calculate_extrusion_geometry(face, height)

    def _calculate_extrusion_geometry(self, face, height):
        if not HAS_SHAPELY: return [], []
        poly = face.get('shapely_poly')
        if not poly: return [], []
        normal = face['normal']; origin = face['origin']
        try:
            tris = triangulate(poly)
            valid_tris = [t for t in tris if poly.contains(t.centroid)]
        except Exception:
            return [], []
        verts = []; faces = []; v_map = {}
        def add(x,y,z):
            k = (round(x,4), round(y,4), round(z,4))
            if k in v_map: return v_map[k]
            idx = len(verts); verts.append((x,y,z)); v_map[k] = idx; return idx
        def trans(x,y,h): return self._transform_2d_to_3d(x,y,normal,origin)
        def trans_h(x,y,h):
            p = self._transform_2d_to_3d(x,y,normal,origin)
            nx, ny, nz = normal
            return (p[0]+nx*h, p[1]+ny*h, p[2]+nz*h)

        for t in valid_tris:
            xx, yy = t.exterior.coords.xy
            p = list(zip(xx[:3], yy[:3]))
            b = [add(*trans(x,y,0)) for x,y in p]
            t_Idx = [add(*trans_h(x,y,height)) for x,y in p]
            if height > 0:
                faces.append((b[0], b[2], b[1])); faces.append((t_Idx[0], t_Idx[1], t_Idx[2]))
            else:
                faces.append((b[0], b[1], b[2])); faces.append((t_Idx[0], t_Idx[2], t_Idx[1]))

        rings = [poly.exterior] + list(poly.interiors)
        for ring in rings:
            pts = list(ring.coords)
            for i in range(len(pts)-1):
                x1,y1 = pts[i]; x2,y2 = pts[i+1]
                b1 = add(*trans(x1,y1,0)); b2 = add(*trans(x2,y2,0))
                t1 = add(*trans_h(x1,y1,height)); t2 = add(*trans_h(x2,y2,height))
                if height > 0:
                    faces.append((b1, b2, t2)); faces.append((b1, t2, t1))
                else:
                    faces.append((b1, t1, t2)); faces.append((b1, t2, b2))
        return verts, faces

    def _detect_faces(self):
        """
        Erkennt Flächen aus Sketches für 3D-Extrusion.
        FIX: Nutzt Randpunkte statt Zentroiden als Selektor, um "Loch-Probleme" zu vermeiden.
        """
        self.detected_faces = []
        if not HAS_SHAPELY: return
        
        from shapely.ops import polygonize, unary_union
        from shapely.geometry import LineString, Polygon
        
        def rnd(val): return round(val, 5)
            
        for s, vis in self.sketches:
            if not vis: continue
            norm = tuple(getattr(s, 'plane_normal', (0,0,1)))
            orig = getattr(s, 'plane_origin', (0,0,0))
            
            all_segments = []
            
            # --- Geometrie sammeln (Identisch wie zuvor) ---
            for l in getattr(s, 'lines', []):
                if not getattr(l, 'construction', False):
                    all_segments.append(LineString([(rnd(l.start.x), rnd(l.start.y)), (rnd(l.end.x), rnd(l.end.y))]))
            
            for arc in getattr(s, 'arcs', []):
                if not getattr(arc, 'construction', False):
                    pts = []
                    start, end = arc.start_angle, arc.end_angle
                    sweep = end - start
                    if sweep < 0.1: sweep += 360
                    steps = max(12, int(sweep / 5))
                    for i in range(steps + 1):
                        t = math.radians(start + sweep * (i / steps))
                        x = arc.center.x + arc.radius * math.cos(t)
                        y = arc.center.y + arc.radius * math.sin(t)
                        pts.append((rnd(x), rnd(y)))
                    if len(pts) >= 2: all_segments.append(LineString(pts))

            for c in getattr(s, 'circles', []):
                if not getattr(c, 'construction', False):
                    pts = []
                    for i in range(65):
                        angle = i * 2 * math.pi / 64
                        x = c.center.x + c.radius * math.cos(angle)
                        y = c.center.y + c.radius * math.sin(angle)
                        pts.append((rnd(x), rnd(y)))
                    all_segments.append(LineString(pts))
            
            for spline in getattr(s, 'splines', []):
                if not getattr(spline, 'construction', False):
                     # ... Spline logic (wie gehabt) ...
                     pass 

            # --- Polygonize & Daten speichern ---
            if all_segments:
                try:
                    merged = unary_union(all_segments)
                    for poly in polygonize(merged):
                        if poly.is_valid and poly.area > 0.01:
                            # FIX: Wähle einen Punkt auf dem RAND statt im Zentrum.
                            # Das Zentrum eines "Donuts" läge im Loch -> Falsche Auswahl.
                            # Der Randpunkt ist eindeutig Teil der Außenform.
                            pt = poly.exterior.coords[0]
                            
                            self.detected_faces.append({
                                'shapely_poly': poly,
                                'coords': list(poly.exterior.coords),
                                'normal': norm,
                                'origin': orig,
                                'sketch': s,
                                'center_2d': (pt[0], pt[1]) # HIER IST DER FIX
                            })
                except Exception as e:
                    logger.error(f" {e}")
        
        # Sortieren: Kleine Flächen zuerst
        self.detected_faces.sort(key=lambda x: x['shapely_poly'].area)
    
    def _compute_atomic_regions_from_polygons(self, polygons):
        """
        Berechnet alle atomaren (nicht weiter teilbaren) Regionen 
        aus einer Liste von überlappenden Polygonen.
        
        Beispiel: 4 überlappende Kreise → 9 atomare Regionen
        """
        if not polygons:
            return []
        if len(polygons) == 1:
            return polygons
        
        from shapely.geometry import Polygon, MultiPolygon
        
        n = len(polygons)
        
        # Für jede mögliche Kombination von Polygonen berechnen wir die Region,
        # die IN allen Polygonen der Kombination liegt, aber NICHT in anderen.
        
        # Effizienterer Ansatz: Iterativ aufbauen
        # Start mit dem ersten Polygon, dann mit jedem weiteren schneiden/subtrahieren
        
        atomic = []
        
        # Methode: Für jedes Polygon berechne die Teile die:
        # - nur in diesem Polygon sind
        # - in diesem UND anderen sind (Schnittmengen)
        
        # Wir verwenden einen "overlay" Ansatz
        all_regions = []
        
        # Initialisiere mit dem ersten Polygon
        current_regions = [{'poly': polygons[0], 'inside': {0}}]
        
        for i in range(1, n):
            new_poly = polygons[i]
            next_regions = []
            
            for region in current_regions:
                poly = region['poly']
                inside_set = region['inside']
                
                if not poly.is_valid or poly.is_empty:
                    continue
                
                try:
                    # Teil der Region der AUCH im neuen Polygon ist
                    intersection = poly.intersection(new_poly)
                    # Teil der Region der NICHT im neuen Polygon ist
                    difference = poly.difference(new_poly)
                    
                    # Intersection hinzufügen (ist in allen bisherigen + dem neuen)
                    if intersection.is_valid and not intersection.is_empty:
                        for p in self._extract_polygons(intersection):
                            if p.area > 0.01:
                                next_regions.append({
                                    'poly': p, 
                                    'inside': inside_set | {i}
                                })
                    
                    # Difference hinzufügen (ist nur in den bisherigen)
                    if difference.is_valid and not difference.is_empty:
                        for p in self._extract_polygons(difference):
                            if p.area > 0.01:
                                next_regions.append({
                                    'poly': p, 
                                    'inside': inside_set.copy()
                                })
                except Exception as e:
                    # Bei Fehler: Region beibehalten
                    next_regions.append(region)
            
            # Auch den Teil des neuen Polygons der in KEINER bisherigen Region war
            try:
                remaining = new_poly
                for region in current_regions:
                    if region['poly'].is_valid:
                        remaining = remaining.difference(region['poly'])
                
                if remaining.is_valid and not remaining.is_empty:
                    for p in self._extract_polygons(remaining):
                        if p.area > 0.01:
                            next_regions.append({
                                'poly': p, 
                                'inside': {i}
                            })
            except Exception as e:
                logger.debug(f"[viewport] Fehler beim Entfernen Body-Face-Selection: {e}")
            
            current_regions = next_regions
        
        # Extrahiere nur die Polygone
        result = [r['poly'] for r in current_regions if r['poly'].is_valid and r['poly'].area > 0.01]
        
        # Deduplizierung
        final = []
        for poly in result:
            is_dup = False
            for existing in final:
                try:
                    # Wenn fast identisch (symmetrische Differenz sehr klein)
                    sym_diff = poly.symmetric_difference(existing)
                    if sym_diff.area < min(poly.area, existing.area) * 0.05:
                        is_dup = True
                        break
                except Exception as e:
                    logger.debug(f"[viewport] Duplikat-Check Fehler: {e}")
                    pass
            if not is_dup:
                final.append(poly)
        
        return final
    
    def _extract_polygons(self, geom):
        """Extrahiert alle Polygone aus einer Shapely Geometrie"""
        from shapely.geometry import Polygon, MultiPolygon, GeometryCollection
        
        if geom.is_empty:
            return []
        if geom.geom_type == 'Polygon':
            return [geom]
        elif geom.geom_type == 'MultiPolygon':
            return list(geom.geoms)
        elif geom.geom_type == 'GeometryCollection':
            result = []
            for g in geom.geoms:
                result.extend(self._extract_polygons(g))
            return result
        return []
    
    def _calculate_body_face_extrusion(self, face, height):
        """Berechnet vollständige Extrusion für eine Body-Fläche inkl. Seitenwände"""
        try:
            mesh = face.get('mesh')
            cell_ids = face.get('cell_ids', [])
            normal = np.array(face.get('normal', (0,0,1)))
            
            if mesh is None or not cell_ids:
                return [], []
            
            # Normalisiere
            norm_len = np.linalg.norm(normal)
            n = normal / norm_len if norm_len > 0 else np.array([0,0,1])
            
            # Extrahiere Fläche
            face_mesh = mesh.extract_cells(cell_ids)
            
            # Finde Randkanten der Fläche
            edges = face_mesh.extract_feature_edges(
                boundary_edges=True, 
                feature_edges=False, 
                manifold_edges=False
            )
            
            # Wenn keine Kanten gefunden, nutze alle Kanten
            if edges.n_points == 0:
                edges = face_mesh.extract_all_edges()
            
            # Sammle Randpunkte
            edge_points = edges.points if edges.n_points > 0 else face_mesh.points
            
            verts = []
            faces = []
            v_map = {}
            
            def add_vert(p):
                """Fügt Vertex hinzu, vermeidet Duplikate"""
                key = (round(p[0], 4), round(p[1], 4), round(p[2], 4))
                if key in v_map:
                    return v_map[key]
                idx = len(verts)
                verts.append(tuple(p))
                v_map[key] = idx
                return idx
            
            # Bottom-Fläche (Original-Geometrie)
            for i in range(face_mesh.n_cells):
                cell = face_mesh.get_cell(i)
                pts = cell.points
                if len(pts) >= 3:
                    indices = [add_vert(p) for p in pts]
                    if height > 0:
                        faces.append(tuple(reversed(indices)))  # Normale nach unten
                    else:
                        faces.append(tuple(indices))
            
            # Top-Fläche (extrudiert)
            for i in range(face_mesh.n_cells):
                cell = face_mesh.get_cell(i)
                pts = cell.points
                if len(pts) >= 3:
                    top_pts = [p + n * height for p in pts]
                    indices = [add_vert(p) for p in top_pts]
                    if height > 0:
                        faces.append(tuple(indices))  # Normale nach oben
                    else:
                        faces.append(tuple(reversed(indices)))
            
            # Seitenwände aus Randkanten
            if edges.n_lines > 0:
                lines = edges.lines
                i = 0
                while i < len(lines):
                    n_pts_line = lines[i]
                    if n_pts_line >= 2:
                        for j in range(n_pts_line - 1):
                            p1 = edge_points[lines[i + 1 + j]]
                            p2 = edge_points[lines[i + 2 + j]]
                            
                            # 4 Punkte für Quad: bottom1, bottom2, top2, top1
                            b1 = add_vert(p1)
                            b2 = add_vert(p2)
                            t1 = add_vert(p1 + n * height)
                            t2 = add_vert(p2 + n * height)
                            
                            # Zwei Dreiecke für das Quad
                            if height > 0:
                                faces.append((b1, b2, t2))
                                faces.append((b1, t2, t1))
                            else:
                                faces.append((b1, t1, t2))
                                faces.append((b1, t2, b2))
                    i += n_pts_line + 1
            else:
                # Fallback: Nutze alle Kanten des Meshes
                for i in range(face_mesh.n_cells):
                    cell = face_mesh.get_cell(i)
                    pts = cell.points
                    n_cell_pts = len(pts)
                    for j in range(n_cell_pts):
                        p1 = pts[j]
                        p2 = pts[(j + 1) % n_cell_pts]
                        
                        b1 = add_vert(p1)
                        b2 = add_vert(p2)
                        t1 = add_vert(p1 + n * height)
                        t2 = add_vert(p2 + n * height)
                        
                        if height > 0:
                            faces.append((b1, b2, t2))
                            faces.append((b1, t2, t1))
                        else:
                            faces.append((b1, t1, t2))
                            faces.append((b1, t2, b2))
            
            return verts, faces
            
        except Exception as e:
            logger.error(f" {e}")
            import traceback
            traceback.print_exc()
            return [], []

    def _get_body_id_for_actor(self, picked_actor):
        """Findet Body-ID für einen gepickten VTK-Actor.

        VTK CellPicker gibt Raw-VTK-Actors zurück, die sich von PyVista's
        gewrappten Actors unterscheiden. Daher vergleichen wir die VTK-Adressen.
        """
        if picked_actor is None:
            return None

        # Hole VTK-Adresse des gepickten Actors
        picked_addr = picked_actor.GetAddressAsString("")

        for bid, actor_names in self._body_actors.items():
            for name in actor_names:
                if name in self.plotter.renderer.actors:
                    registered_actor = self.plotter.renderer.actors[name]
                    # Vergleiche VTK-Adressen
                    if registered_actor.GetAddressAsString("") == picked_addr:
                        return bid
        return None

    def _rebuild_actor_body_cache(self):
        """Debug-Ausgabe für Actor-Cache (nicht mehr für Lookup verwendet)."""
        logger.debug(f"Renderer actors: {list(self.plotter.renderer.actors.keys())}")
        for bid, actors in self._body_actors.items():
            logger.debug(f"Body '{bid}' hat actors: {actors}")
    
    def _draw_body_face_highlight(self, pos, normal):
        """Zeichnet Highlight auf gehoverter Body-Fläche.

        FIX: Offset vom Body weg um Z-Fighting zu vermeiden.
        FIX: Normal richtung Kamera korrigieren falls invertiert.
        """
        self._clear_body_face_highlight()
        try:
            center = np.array(pos)
            n = np.array(normal)
            norm_len = np.linalg.norm(n)
            if norm_len > 0:
                n = n / norm_len
            else:
                n = np.array([0, 0, 1])

            # FIX: Sicherstellen dass Normal zur Kamera zeigt (nicht ins Body hinein)
            # View-Direction berechnen (von Kamera zum Punkt)
            cam_pos = np.array(self.plotter.camera_position[0])
            view_dir = center - cam_pos
            view_dir = view_dir / np.linalg.norm(view_dir)

            # Wenn Normal weg von Kamera zeigt (dot > 0), invertieren
            if np.dot(n, view_dir) > 0:
                n = -n

            # OFFSET: Highlight leicht vom Body weg verschieben (Z-Fighting vermeiden)
            offset_center = center + n * 0.5  # 0.5mm Offset

            # Erstelle einen Kreis senkrecht zur Normalen
            radius = 8.0  # Etwas größer für bessere Sichtbarkeit

            # Finde zwei Vektoren senkrecht zur Normalen
            if abs(n[2]) < 0.9:
                u = np.cross(n, [0, 0, 1])
            else:
                u = np.cross(n, [1, 0, 0])
            u = u / np.linalg.norm(u)
            v = np.cross(n, u)

            # Kreis-Punkte
            points = []
            for i in range(33):
                angle = i * 2 * math.pi / 32
                p = offset_center + radius * (math.cos(angle) * u + math.sin(angle) * v)
                points.append(p)

            # Als Linie zeichnen mit render_lines_as_tubes für bessere Sichtbarkeit
            pts = np.array(points)
            lines = pv.lines_from_points(pts)
            self.plotter.add_mesh(
                lines, color='cyan', line_width=5,
                name='body_face_highlight',
                render_lines_as_tubes=True
            )

            # Normale als Pfeil (zeigt Extrude-Richtung)
            arrow = pv.Arrow(start=offset_center, direction=n, scale=10)
            self.plotter.add_mesh(arrow, color='cyan', name='body_face_arrow')

            # Render erzwingen statt nur update
            request_render(self.plotter, immediate=True)
        except Exception as e:
            logger.error(f"Highlight Fehler: {e}")
            import traceback
            traceback.print_exc()
    
    def _clear_body_face_highlight(self):
        """Entfernt Body-Face-Highlight"""
        _safe_remove_actor(self.plotter, 'body_face_highlight', "body face highlight clear")
        _safe_remove_actor(self.plotter, 'body_face_arrow', "body face arrow clear")
        # Kein render hier - wird beim nächsten Hover gemacht

    def _draw_full_face_hover(self, body_id, rounded_normal, raw_normal, cell_id=None):
        """Zeichnet full-face blaues Highlight auf gehoverter Body-Fläche (Draft/Texture Mode)."""
        import numpy as np
        self._clear_body_face_highlight()
        try:
            mesh = None
            cell_ids = []

            # KONSISTENZ: Für Texture Mode, hole Face vom Detector (wie beim Click)
            if self.texture_face_mode and hasattr(self, 'detector'):
                # Hole Position vom hovered_body_face
                if self.hovered_body_face:
                    _, _, _, pos = self.hovered_body_face
                    clicked_pos = np.array(pos)

                    matching_detector_face = None
                    min_dist = float('inf')

                    for face in self.detector.selection_faces:
                        if face.domain_type != 'body_face':
                            continue
                        if face.owner_id != body_id:
                            continue

                        # Berechne Distanz zur Face-Origin
                        face_origin = np.array(face.plane_origin)
                        dist = np.linalg.norm(clicked_pos - face_origin)

                        if dist < min_dist:
                            min_dist = dist
                            matching_detector_face = face

                    if matching_detector_face:
                        mesh = self.bodies.get(body_id, {}).get('mesh')
                        cell_ids = self._get_cells_for_detector_face(matching_detector_face, mesh)
            else:
                # FALLBACK: Für Draft/Hole/Thread Mode (verwenden detected_faces)
                face_data = None
                for face in self.detected_faces:
                    if face.get('type') != 'body_face':
                        continue
                    if face.get('body_id') != body_id:
                        continue
                    if cell_id is not None and cell_id in face.get('cell_ids', []):
                        face_data = face
                        break

                if face_data:
                    mesh = face_data.get('mesh')
                    cell_ids = face_data.get('cell_ids', [])

            # Zeichne Face-Highlight
            if mesh is None or not cell_ids:
                return

            face_mesh = mesh.extract_cells(cell_ids)
            normal_arr = np.array(raw_normal)
            norm_len = np.linalg.norm(normal_arr)
            if norm_len > 1e-10:
                normal_arr = normal_arr / norm_len
            face_mesh_copy = face_mesh.copy()
            face_mesh_copy.points = face_mesh_copy.points + normal_arr * 0.3

            self.plotter.add_mesh(
                face_mesh_copy,
                color='#55bbff',
                opacity=0.65,
                name='body_face_highlight',
                pickable=False,
                show_edges=True,
                edge_color='#0088ff',
                line_width=2
            )
            request_render(self.plotter, immediate=True)
        except Exception as e:
            logger.debug(f"Full-face hover error: {e}")
    
    def _click_body_face(self):
        """Klick auf Body-Face - bereitet Extrusion oder Texture-Selektion vor"""
        if self.hovered_body_face is None:
            return
        self.clear_trace_hint()

        body_id, cell_id, normal, pos = self.hovered_body_face

        # Hole Mode: Emit face click for hole placement
        if self.hole_mode:
            self.hole_face_clicked.emit(body_id, cell_id, tuple(normal), tuple(pos))
            self._draw_body_face_selection(pos, normal)
            return

        # Thread Mode: Emit face click for thread placement on cylindrical faces
        if self.thread_mode:
            # Detect if face is cylindrical and get its properties
            cyl_info = self._detect_cylindrical_face(body_id, cell_id, pos)
            if cyl_info:
                diameter, axis_dir, is_internal = cyl_info
                self.thread_face_clicked.emit(body_id, cell_id, tuple(axis_dir), tuple(pos), diameter)
                self._draw_body_face_selection(pos, axis_dir)
            else:
                logger.warning("Thread: Keine zylindrische Fläche erkannt")
            return

        # Draft Mode: Full-face selection with orange highlight
        if self.draft_mode:
            # Find matching detected_face by cell_id membership (robust after Draft/Hole)
            face_data = None
            for face in self.detected_faces:
                if face.get('type') != 'body_face':
                    continue
                if face.get('body_id') != body_id:
                    continue
                if cell_id in face.get('cell_ids', []):
                    face_data = face
                    break

            if face_data is None:
                face_data = {
                    'body_id': body_id, 'cell_ids': [cell_id],
                    'normal': normal, 'center': pos,
                    'mesh': self.bodies.get(body_id, {}).get('mesh'),
                }

            self._toggle_draft_face(face_data)
            self.draft_face_clicked.emit(body_id, cell_id, tuple(normal), tuple(pos))
            return

        # Texture Face Mode: Sammle Faces für Texturierung (GENAU WIE EXTRUDE)
        if self.texture_face_mode:
            # Nur Faces vom richtigen Body akzeptieren
            if self._texture_body_id and body_id != self._texture_body_id:
                logger.warning(f"Face von anderem Body ignoriert (erwartet: '{self._texture_body_id}', geklickt: '{body_id}')")
                return

            # KONSISTENZ: Hole Face vom Detector (wie Extrude)
            if not hasattr(self, 'detector'):
                logger.error("❌ Kein Detector verfügbar für Texture Face Selection!")
                return

            # Finde die geklickte Face vom Detector basierend auf Position
            import numpy as np
            clicked_pos = np.array(pos)
            matching_detector_face = None
            min_dist = float('inf')

            for face in self.detector.selection_faces:
                if face.domain_type != 'body_face':
                    continue
                if face.owner_id != body_id:
                    continue

                # Berechne Distanz zur Face-Origin
                face_origin = np.array(face.plane_origin)
                dist = np.linalg.norm(clicked_pos - face_origin)

                if dist < min_dist:
                    min_dist = dist
                    matching_detector_face = face

            if matching_detector_face is None:
                logger.error(f"❌ Keine Face vom Detector gefunden für Klick-Position {pos}")
                return

            # Konvertiere Detector-Face zu face_data Format
            mesh = self.bodies.get(body_id, {}).get('mesh')
            face_normal = matching_detector_face.plane_normal

            # WICHTIG: Hole ALLE cell_ids dieser Face aus dem Mesh
            # (Die Detector-Face hat kein display_mesh für Bodies, daher müssen wir die cell_ids aus dem Mesh holen)
            cell_ids = self._get_cells_for_detector_face(matching_detector_face, mesh)

            face_data = {
                'body_id': body_id,
                'cell_ids': cell_ids,
                'normal': face_normal,
                'center': matching_detector_face.plane_origin,
                'mesh': mesh,
                'area': len(cell_ids),  # Approximation
                'surface_type': 'plane'
            }

            self._add_texture_face(face_data)
            logger.success(f"✓ Texture Face hinzugefügt: {len(cell_ids)} Dreiecke, Total: {len(self._texture_selected_faces)} Faces")
            return

        # Standard Extrusion-Modus
        # Speichere die Flächen-Daten für Extrusion
        # Wir erstellen ein "detected_face" aus der Body-Fläche
        self.body_face_extrude = {
            'body_id': body_id,
            'cell_id': cell_id,
            'normal': normal,
            'origin': pos,
            'mesh': self.bodies.get(body_id, {}).get('mesh')
        }

        # Markiere als ausgewählt
        # W7 PAKET B: Use Unified API
        self.clear_face_selection()
        self.selected_face_ids.add(-1)  # Special marker für Body-Face

        logger.info(f"Body face selected: body={body_id}, normal={normal}, pos={pos}")

        # Zeige Preview
        self._draw_body_face_selection(pos, normal)
    
    def _clear_preview(self):
        if self._preview_actor: 
            try: self.plotter.remove_actor(self._preview_actor)
            except Exception:
                pass
            self._preview_actor = None

    def _draw_selectable_faces(self):
        """Zeichnet NUR die gehoverte und ausgewählte Flächen - nicht alle"""
        self._clear_face_actors()
        
        for i, face in enumerate(self.detected_faces):
            is_selected = i in self.selected_faces
            is_hovered = i == self.hovered_face
            
            # Nur zeichnen wenn selected oder hovered!
            if not is_selected and not is_hovered:
                continue
            
            if is_selected: 
                col = 'orange'
                op = 0.7
            else:  # hovered
                col = '#44aaff'
                op = 0.5
            
            # Body-Face oder Sketch-Face?
            if face.get('type') == 'body_face':
                self._draw_body_face_overlay(i, face, col, op)
            else:
                # Sketch-Face
                v, f = self.get_extrusion_data(i, 0)
                if v:
                    vv = np.array(v, dtype=np.float32)
                    ff = []
                    for x in f: ff.extend([3]+list(x))
                    mesh = pv.PolyData(vv, np.array(ff, dtype=np.int32))
                    n = f"face_{i}"
                    self.plotter.add_mesh(mesh, color=col, opacity=op, name=n, pickable=True)
                    self._face_actors.append(n)
        
        self.plotter.update()
    
    def _draw_body_face_overlay(self, face_idx, face, color, opacity):
        """Zeichnet Overlay für eine Body-Fläche"""
        try:
            mesh = face.get('mesh')
            cell_ids = face.get('cell_ids', [])
            
            if mesh is None or not cell_ids:
                return
            
            # Extrahiere nur die Zellen dieser Fläche
            face_mesh = mesh.extract_cells(cell_ids)
            
            n = f"face_{face_idx}"
            self.plotter.add_mesh(face_mesh, color=color, opacity=opacity, 
                                  name=n, pickable=True, show_edges=False)
            self._face_actors.append(n)
        except Exception as e:
            logger.error(f" {e}")

    def _clear_face_actors(self):
        for n in self._face_actors:
            _safe_remove_actor(self.plotter, n, "face actor cleanup")
        self._face_actors.clear()

    def _render_sketch(self, s):
        norm = tuple(getattr(s,'plane_normal',(0,0,1)))
        orig = getattr(s,'plane_origin',(0,0,0))
        
        # FIX: Wenn wir eine gespeicherte X-Achse haben, NUTZEN wir sie!
        # Das verhindert, dass die Skizze sich dreht.
        cached_x = getattr(s, 'plane_x_dir', None)
        cached_y = getattr(s, 'plane_y_dir', None)
        
        sid = getattr(s,'id',id(s))
        
        # Lokale Funktion mit Closure über Koordinatensystem
        def t3d(x, y): 
            if cached_x and cached_y:
                # Exakte Transformation: P = Origin + x*X_Axis + y*Y_Axis
                px = orig[0] + x * cached_x[0] + y * cached_y[0]
                py = orig[1] + x * cached_x[1] + y * cached_y[1]
                pz = orig[2] + x * cached_x[2] + y * cached_y[2]
                return (px, py, pz)
            else:
                # Fallback zur alten Berechnung (Raten)
                return self._transform_2d_to_3d(x, y, norm, orig)
        
        # Linien
        for i,l in enumerate(getattr(s,'lines',[])):
            col = 'gray' if getattr(l,'construction',False) else '#4d94ff'
            self.plotter.add_mesh(pv.Line(t3d(l.start.x,l.start.y), t3d(l.end.x,l.end.y)), color=col, line_width=3, name=f"s_{sid}_l_{i}", pickable=True)
            self._sketch_actors.append(f"s_{sid}_l_{i}")
            
        # Kreise
        for i,c in enumerate(getattr(s,'circles',[])):
            pts = [t3d(c.center.x+c.radius*math.cos(j*6.28/64), c.center.y+c.radius*math.sin(j*6.28/64)) for j in range(65)]
            col = 'gray' if getattr(c,'construction',False) else '#4d94ff'
            self.plotter.add_mesh(pv.lines_from_points(np.array(pts)), color=col, line_width=3, name=f"s_{sid}_c_{i}", pickable=True)
            self._sketch_actors.append(f"s_{sid}_c_{i}")
            
        # Arcs (Neu: Bessere Darstellung)
        for i, arc in enumerate(getattr(s, 'arcs', [])):
            col = 'gray' if getattr(arc,'construction',False) else '#4d94ff'
            pts = []
            start = arc.start_angle
            end = arc.end_angle
            sweep = end - start
            if sweep < 0.1: sweep += 360
            steps = 32
            for j in range(steps+1):
                t = math.radians(start + sweep * (j/steps))
                x = arc.center.x + arc.radius * math.cos(t)
                y = arc.center.y + arc.radius * math.sin(t)
                pts.append(t3d(x, y))
            if len(pts) > 1:
                self.plotter.add_mesh(pv.lines_from_points(np.array(pts)), color=col, line_width=3, name=f"s_{sid}_a_{i}", pickable=True)
                self._sketch_actors.append(f"s_{sid}_a_{i}")

        # Splines (Neu!)
        for i, spline in enumerate(getattr(s, 'splines', [])):
            col = 'gray' if getattr(spline,'construction',False) else '#4d94ff'
            pts_2d = []
            # Punkte holen
            if hasattr(spline, 'get_curve_points'):
                 pts_2d = spline.get_curve_points(segments_per_span=10)
            elif hasattr(spline, 'to_lines'):
                 lines = spline.to_lines(segments_per_span=10)
                 if lines:
                     pts_2d.append((lines[0].start.x, lines[0].start.y))
                     for l in lines: pts_2d.append((l.end.x, l.end.y))
            
            if len(pts_2d) > 1:
                pts_3d = [t3d(p[0], p[1]) for p in pts_2d]
                self.plotter.add_mesh(pv.lines_from_points(np.array(pts_3d)), color=col, line_width=3, name=f"s_{sid}_sp_{i}", pickable=True)
                self._sketch_actors.append(f"s_{sid}_sp_{i}")
        
        # Ellipsen (Native Ellipse2D)
        for i, ellipse in enumerate(getattr(s, 'ellipses', [])):
            col = 'gray' if getattr(ellipse, 'construction', False) else '#4d94ff'
            pts = []
            # Ellipse als geschlossene Kurve mit 64 Segmenten
            for j in range(65):
                angle = math.radians(j * 360 / 64)
                pt = ellipse.point_at_angle(angle)
                pts.append(t3d(pt.x, pt.y))
            if len(pts) > 1:
                self.plotter.add_mesh(pv.lines_from_points(np.array(pts)), color=col, line_width=3, name=f"s_{sid}_e_{i}", pickable=True)
                self._sketch_actors.append(f"s_{sid}_e_{i}")

    def _show_selection_planes(self):
        sz = 150; op = 0.25
        self.plotter.add_mesh(pv.Plane(center=(0,0,0), direction=(0,0,1), i_size=sz, j_size=sz), color='blue', opacity=op, name='xy', pickable=True)
        self.plotter.add_mesh(pv.Plane(center=(0,0,0), direction=(0,1,0), i_size=sz, j_size=sz), color='green', opacity=op, name='xz', pickable=True)
        self.plotter.add_mesh(pv.Plane(center=(0,0,0), direction=(1,0,0), i_size=sz, j_size=sz), color='red', opacity=op, name='yz', pickable=True)
        self._plane_actors = {'xy':'xy','xz':'xz','yz':'yz'}

    def _hide_selection_planes(self):
        for n in ['xy','xz','yz']:
            _safe_remove_actor(self.plotter, n, "selection plane cleanup")
        self._plane_actors.clear()

    def set_view(self, view_name):
        """Setzt eine Standardansicht"""
        if not HAS_PYVISTA:
            return
        
        views = {
            'iso': 'iso',
            'top': 'xy',
            'front': 'xz', 
            'right': 'yz',
            'back': '-xz',
            'left': '-yz',
            'bottom': '-xy'
        }
        
        if view_name in views:
            try:
                self.plotter.view_vector(views[view_name])
                self.plotter.reset_camera()
                self.view_changed.emit()
                self._apply_frustum_culling(force=False)
                if getattr(self, "_lod_enabled", False):
                    self._lod_restore_timer.start()
            except Exception as e:
                logger.debug(f"[viewport] Fehler beim Setzen der Ansicht {view_name}: {e}")
                # Fallback
                if view_name == 'iso':
                    self.plotter.view_isometric()
                elif view_name == 'top':
                    self.plotter.view_xy()
                elif view_name == 'front':
                    self.plotter.view_xz()
                elif view_name == 'right':
                    self.plotter.view_yz()
                self.plotter.reset_camera()
                self.view_changed.emit()
                self._apply_frustum_culling(force=False)
                if getattr(self, "_lod_enabled", False):
                    self._lod_restore_timer.start()

    # ==================== MODALE NUMERISCHE EINGABE ====================
    def _show_numeric_input_overlay(self, text: str):
        """Zeigt Floating-Label für numerische Eingabe während Transform"""
        from PySide6.QtWidgets import QLabel
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QCursor

        # Entferne altes Overlay (falls vorhanden)
        self._hide_numeric_input_overlay()

        # Erstelle neues Label
        self._numeric_overlay = QLabel(f"Value: {text}", self)
        p = DesignTokens.COLOR_PRIMARY.name()
        self._numeric_overlay.setStyleSheet(f"""
            QLabel {{
                background: {p};
                color: white;
                padding: 8px 12px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                border: 2px solid rgba(255, 255, 255, 100);
            }}
        """)
        self._numeric_overlay.setWindowFlags(Qt.ToolTip)  # Bleibt über allem
        self._numeric_overlay.adjustSize()

        # Position nahe Cursor (leicht versetzt nach rechts unten)
        cursor_pos = QCursor.pos()
        overlay_pos = self.mapFromGlobal(cursor_pos)
        self._numeric_overlay.move(overlay_pos.x() + 20, overlay_pos.y() + 20)
        self._numeric_overlay.show()

        logger.debug(f"Numeric overlay shown: {text}")

    def _hide_numeric_input_overlay(self):
        """Versteckt Floating-Label für numerische Eingabe"""
        if hasattr(self, '_numeric_overlay') and self._numeric_overlay:
            self._numeric_overlay.deleteLater()
            self._numeric_overlay = None

    def _apply_numeric_transform(self, value: float):
        """
        Wendet numerischen Wert auf aktiven Transform an.

        Verhalten basierend auf Modus:
        - Move: Bewegt um 'value' Einheiten (auf gesperrter Achse falls aktiv)
        - Rotate: Rotiert um 'value' Grad
        - Scale: Skaliert mit Faktor 'value'
        """
        if not self.transform_state or not self.transform_state.active_body_id:
            logger.warning("Kein aktiver Transform - numerischer Wert ignoriert")
            return

        mode = self.transform_state.mode
        body_id = self.transform_state.active_body_id

        # Bestimme Transform-Data basierend auf Modus
        if mode == "move":
            # Move: Nutze axis_lock falls vorhanden
            axis_lock = self.transform_state.axis_lock

            if axis_lock == "X":
                translation = [value, 0, 0]
            elif axis_lock == "Y":
                translation = [0, value, 0]
            elif axis_lock == "Z":
                translation = [0, 0, value]
            else:
                # Kein Lock: Bewege entlang Kamera-Blickrichtung (oder X als Default)
                logger.warning("Keine Achse gesperrt - verwende X-Achse als Default")
                translation = [value, 0, 0]

            data = {"translation": translation}
            logger.info(f"Move mit numerischem Wert: {translation}")

        elif mode == "rotate":
            # Rotate: Winkel in Grad
            axis_lock = self.transform_state.axis_lock or "Z"  # Default Z-Achse
            data = {"axis": axis_lock, "angle": value}
            logger.info(f"Rotate um {value}° auf {axis_lock}-Achse")

        elif mode == "scale":
            # Scale: Faktor (1.0 = keine Änderung)
            if value <= 0:
                logger.error("Scale-Faktor muss > 0 sein")
                return
            data = {"factor": value}
            logger.info(f"Scale mit Faktor {value}")

        else:
            logger.error(f"Unbekannter Transform-Modus: {mode}")
            return

        # Emittiere Transform-Signal
        self.body_transform_requested.emit(body_id, mode, data)

        # Reset Transform-State
        self.transform_state.reset()
        self.hide_transform_gizmo()

    def update(self): self.plotter.update(); super().update()

    def _show_context_menu(self, pos):
        """Zeigt Kontext-Menü an der Mausposition."""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction
        
        # Picken was unter der Maus ist (Face oder Body)
        local_pos = pos.toPoint() if hasattr(pos, "toPoint") else pos
        x, y = int(local_pos.x()), int(local_pos.y())
        hit_id = self.pick(x, y, selection_filter=self.active_selection_filter)
        
        menu = QMenu(self)
        menu.aboutToHide.connect(self.clear_trace_hint)
        
        # 1. Sketch auf Face erstellen
        if hit_id != -1:
             # Finde Face
             if hasattr(self, 'detector') and self.detector and self.detector.selection_faces:
                 face = next((f for f in self.detector.selection_faces if f.id == hit_id), None)
                 if face:
                     if getattr(face, "domain_type", "") == "body_face" and self._is_trace_assist_allowed():
                         self.show_trace_hint(hit_id)

                     action = QAction("Create Sketch (T)", self)

                     def _request_create_sketch(fid=hit_id):
                         self.create_sketch_requested.emit(fid)
                         self.clear_trace_hint()

                     action.triggered.connect(_request_create_sketch)
                     menu.addAction(action)
                     
                     menu.addSeparator()

        # 2. View Operations (Immer verfügbar)
        action_home = QAction("🏠 Home View", self)
        action_home.triggered.connect(lambda: self.view_iso())
        menu.addAction(action_home)

        action_fit = QAction("🔍 Fit View", self)
        action_fit.triggered.connect(lambda: self.view_fit())
        menu.addAction(action_fit)

        # Show Menu
        global_pos = self.mapToGlobal(local_pos)
        menu.exec(global_pos)


def create_viewport(parent=None):
    return PyVistaViewport(parent) if HAS_PYVISTA else QWidget(parent)
