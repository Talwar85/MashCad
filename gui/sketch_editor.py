"""
MashCad - 2D Sketch Editor v4
Fusion360-Style mit Tab-Eingabe, geschlossene Profile, professionelle UX
Mit Build123d Backend für parametrische CAD-Operationen
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QMenu, QApplication, QFrame, QPushButton
)
from PySide6.QtCore import Qt, QPointF, QPoint, Signal, QRectF, QTimer, QThread
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath,
    QMouseEvent, QWheelEvent, QKeyEvent, QPolygonF, QFontMetrics
)

import threading 
from threading import Thread

from enum import Enum, auto
from typing import Optional, List, Tuple, Set
import math
import sys
import os
import numpy as np
from loguru import logger

try:
    from gui.design_tokens import DesignTokens
except ImportError:
    from design_tokens import DesignTokens


try:
    from gui.quadtree import QuadTree
    logger.success("QuadTree Module loaded.")
except ImportError:
    # Fallback class if file is missing to prevent crash
    class QuadTree:
        def __init__(self, *args): pass
        def insert(self, *args): pass
        def query(self, *args): return []
        def clear(self, *args): pass
    logger.warning("QuadTree Module NOT found. Falling back to linear search.")


_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from i18n import tr
from sketcher import Sketch, Point2D, Line2D, Circle2D, Arc2D, Constraint, ConstraintType

# Build123d für parametrische CAD-Operationen
HAS_BUILD123D = False
try:
    import build123d as b3d
    from build123d import (
        BuildPart, BuildSketch, BuildLine,
        Plane, Location, Locations, Vector,
        Line as B3DLine, Circle as B3DCircle, 
        CenterArc, ThreePointArc, TangentArc,
        Rectangle, Polygon, Polyline,
        extrude, fillet, chamfer, make_face,
        Mode
    )
    HAS_BUILD123D = True
    logger.success("Build123d erfolgreich geladen für Sketch-Editor")
except ImportError as e:
    logger.warning(f"Build123d nicht verfügbar: {e}")

# Importiere Dialoge und Tools - mehrere Fallback-Versuche
_import_ok = False
_import_error = None

# Versuch 1: Als Paket (gui.xxx)
if not _import_ok:
    try:
        from gui.sketch_dialogs import DimensionInput, ToolOptionsPopup
        from gui.sketch_tools import SketchTool, SnapType
        from gui.sketch_handlers import SketchHandlersMixin
        from gui.sketch_renderer import SketchRendererMixin
        _import_ok = True
    except ImportError as e:
        _import_error = f"gui.xxx: {e}"

# Versuch 2: Direkt (wenn aus gui/ heraus ausgeführt)
if not _import_ok:
    try:
        from sketch_dialogs import DimensionInput, ToolOptionsPopup
        from sketch_tools import SketchTool, SnapType
        from sketch_handlers import SketchHandlersMixin
        from sketch_renderer import SketchRendererMixin
        _import_ok = True
    except ImportError as e:
        _import_error = f"direct: {e}"

# Versuch 3: Relativer Import
if not _import_ok:
    try:
        from .sketch_dialogs import DimensionInput, ToolOptionsPopup
        from .sketch_tools import SketchTool, SnapType
        from .sketch_handlers import SketchHandlersMixin
        from .sketch_renderer import SketchRendererMixin
        _import_ok = True
    except ImportError as e:
        _import_error = f"relative: {e}"

if not _import_ok:
    logger.critical(f" Sketch-Module nicht gefunden! Letzter Fehler: {_import_error}")
    logger.critical("Bitte stelle sicher, dass sketch_handlers.py, sketch_renderer.py, sketch_tools.py und sketch_dialogs.py im gui/ Ordner liegen!")
    # Leere Fallback-Mixins damit es nicht crasht
    class SketchHandlersMixin: pass
    class SketchRendererMixin: pass
    class SketchTool:
        SELECT = 0
    class SnapType:
        NONE = 0
    class DimensionInput:
        def __init__(self, parent=None): pass
    class ToolOptionsPopup:
        def __init__(self, parent=None): pass


def ramer_douglas_peucker(points, epsilon):
    if len(points) < 3: return points
    
    dmax = 0.0
    index = 0
    end = len(points) - 1
    p1 = points[0]
    p2 = points[end]
    
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    norm = math.hypot(dx, dy)
    
    for i in range(1, end):
        p = points[i]
        # Senkrechter Abstand Punkt zur Linie
        if norm == 0:
            d = math.hypot(p[0]-p1[0], p[1]-p1[1])
        else:
            d = abs(dy * p[0] - dx * p[1] + p2[0] * p1[1] - p2[1] * p1[0]) / norm
        if d > dmax:
            index = i
            dmax = d

    if dmax > epsilon:
        res1 = ramer_douglas_peucker(points[:index+1], epsilon)
        res2 = ramer_douglas_peucker(points[index:], epsilon)
        return res1[:-1] + res2
    else:
        return [p1, p2]

class DXFImportWorker(QThread):
    finished_signal = Signal(list, list, list)  # lines, circles, arcs
    error_signal = Signal(str)
    progress_signal = Signal(str)

    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath

    def run(self):
        try:
            import ezdxf
            import ezdxf.path
            
            doc = ezdxf.readfile(self.filepath)
            msp = doc.modelspace()
            
            new_lines = []
            new_circles = []
            new_arcs = []  # (cx, cy, radius, start_angle, end_angle)
            
            # Helper: Konvertiert komplexe Formen in mikroskopisch feine Linien
            def add_path_as_lines(entity, matrix=None):
                try:
                    p = ezdxf.path.make_path(entity)
                    if matrix: p = p.transform(matrix)
                    
                    # 1. SAMPLING: Alle 0.01 mm ein Punkt (Fusion-Qualität)
                    raw_points = list(p.flattening(distance=0.01))
                    if len(raw_points) < 2: return
                    
                    # 2. OPTIMIERUNG: RDP entfernt überflüssige Punkte
                    # epsilon=0.005: Erlaubt max 5 Mikrometer Abweichung -> Unsichtbar für Auge
                    points_2d = [(v.x, v.y) for v in raw_points]
                    simplified = ramer_douglas_peucker(points_2d, 0.005)
                    
                    for k in range(len(simplified) - 1):
                        p1 = simplified[k]
                        p2 = simplified[k+1]
                        # Min-Länge Filter (0.001mm) gegen Grafik-Glitches
                        if math.hypot(p2[0]-p1[0], p2[1]-p1[1]) > 0.001:
                            new_lines.append((p1[0], p1[1], p2[0], p2[1]))
                except Exception as e:
                    logger.error(f"Path Error: {e}")

            def process_entity(entity, matrix=None):
                dxftype = entity.dxftype()
                
                # Blöcke rekursiv auflösen
                if dxftype == 'INSERT':
                    m = entity.matrix44()
                    if matrix: m = m * matrix
                    for virtual_entity in entity.virtual_entities():
                        process_entity(virtual_entity, m)
                
                # Echte Kreise
                elif dxftype == 'CIRCLE':
                    c = entity.dxf.center
                    if matrix: c = matrix.transform(c)
                    r = entity.dxf.radius
                    if matrix:
                        vec = matrix.transform_direction(ezdxf.math.Vec3(1, 0, 0))
                        r *= vec.magnitude
                    new_circles.append((c.x, c.y, r))

                # Linien direkt übernehmen
                elif dxftype == 'LINE':
                    start = entity.dxf.start
                    end = entity.dxf.end
                    if matrix:
                        start = matrix.transform(start)
                        end = matrix.transform(end)
                    new_lines.append((start.x, start.y, end.x, end.y))

                # Arcs als echte Arcs importieren
                elif dxftype == 'ARC':
                    c = entity.dxf.center
                    r = entity.dxf.radius
                    # DXF: Winkel in Grad, CCW von positiver X-Achse
                    start_angle = entity.dxf.start_angle
                    end_angle = entity.dxf.end_angle
                    
                    if matrix:
                        c = matrix.transform(c)
                        # Skalierung für Radius
                        vec = matrix.transform_direction(ezdxf.math.Vec3(1, 0, 0))
                        r *= vec.magnitude
                        # Rotation für Winkel (vereinfacht - funktioniert für 90°-Rotationen)
                        # Für komplexere Transformationen müsste man die Winkel neu berechnen
                        rot_angle = math.degrees(math.atan2(vec.y, vec.x))
                        start_angle += rot_angle
                        end_angle += rot_angle
                    
                    # Normalisiere Winkel auf 0-360
                    start_angle = start_angle % 360
                    end_angle = end_angle % 360
                    
                    new_arcs.append((c.x, c.y, r, start_angle, end_angle))

                # Splines, Polylines, Ellipsen -> High-Res Fitting
                elif dxftype in ['SPLINE', 'LWPOLYLINE', 'POLYLINE', 'ELLIPSE']:
                    add_path_as_lines(entity, matrix)

            # Start
            all_ents = list(msp)
            total = len(all_ents)
            for i, e in enumerate(all_ents):
                process_entity(e)
                if i % 20 == 0: 
                    self.progress_signal.emit(f"Importiere... {int(i/total*100)}%")

            self.finished_signal.emit(new_lines, new_circles, new_arcs)

        except Exception as e:
            self.error_signal.emit(str(e))
            
            
class SketchEditor(QWidget, SketchHandlersMixin, SketchRendererMixin):
    """Professioneller 2D-Sketch-Editor"""
    
    sketched_changed = Signal()
    tool_changed = Signal(SketchTool)
    status_message = Signal(str)
    construction_mode_changed = Signal(bool)
    grid_snap_mode_changed = Signal(bool)
    solver_finished_signal = Signal(bool, str, float) # success, message, dof

    # Farben
    BG_COLOR = QColor(28, 28, 28)
    GRID_MINOR = QColor(38, 38, 38)
    GRID_MAJOR = QColor(50, 50, 50)
    AXIS_X = QColor(180, 60, 60)
    AXIS_Y = QColor(60, 180, 60)
    GEO_COLOR = QColor(220, 220, 220)
    GEO_CONSTRUCTION = QColor(255, 140, 0)
    GEO_SELECTED = QColor(0, 150, 255)
    GEO_HOVER = QColor(100, 200, 255)
    PROFILE_CLOSED = QColor(0, 120, 215, 40)
    PROFILE_HOVER = QColor(0, 180, 255, 80)  # Helleres Blau beim Hover
    PROFILE_OPEN = QColor(255, 100, 0, 30)
    SNAP_COLOR = QColor(255, 100, 0)
    DIM_COLOR = QColor(255, 200, 100)
    CONSTRAINT_COLOR = QColor(100, 200, 100)
    PREVIEW_COLOR = QColor(0, 150, 255, 150)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(600, 400)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        
        self._solver_lock = threading.Lock()
        self.solver_finished_signal.connect(self._on_solver_finished)
        self._is_solving = False

        self.sketch = Sketch("Sketch1")
        self.view_offset = QPointF(0, 0)
        self.view_scale = 5.0
        self.grid_size = 1.0
        self.grid_snap = True
        self.snap_enabled = True
        self.snap_radius = 15
        
        self.current_tool = SketchTool.SELECT
        self.tool_step = 0
        self.tool_points = []
        self.tool_data = {}
        
        self.selected_lines = []
        self.selected_circles = []
        self.selected_arcs = []
        self.selected_points = []  # Standalone Punkte
        self.selected_constraints = []  # Für Constraint-Selektion
        self.hovered_entity = None
        self._last_hovered_entity = None

        # Editing State für Dimension-Input statt QInputDialog
        self.editing_entity = None  # Objekt das gerade bearbeitet wird (Line, Circle, Constraint)
        self.editing_mode = None    # "length", "radius", "angle", "dimension" etc.

        # HUD-Nachrichten System
        self._hud_message = ""
        self._hud_message_time = 0
        self._hud_duration = 3000
        self._hud_color = QColor(255, 255, 255)
        
        self.selection_box_start = None
        self.selection_box_end = None
        self.current_snap = None
        
        self.mouse_screen = QPointF(0, 0)
        self.mouse_world = QPointF(0, 0)
        self.is_panning = False
        self.pan_start = QPointF()
        
        self.undo_stack = []
        self.redo_stack = []
        self.max_undo = 50
        
        self.dim_input = DimensionInput(self)
        if hasattr(self.dim_input, 'choice_changed'):
            self.dim_input.choice_changed.connect(self._on_dim_choice_changed)
        
        self.dim_input.value_changed.connect(self._on_dim_value_changed)
        self.dim_input.confirmed.connect(self._on_dim_confirmed)
        self.dim_input.cancelled.connect(self._cancel_tool)
        self.dim_input_active = False
        self.viewport = None
        self.dim_input.value_changed.connect(self._on_dim_value_changed)
        
        self.live_length = 0.0
        self.live_angle = 0.0
        self.live_width = 0.0
        self.live_height = 0.0
        self.live_radius = 0.0
        
        self.polygon_sides = 6
        self.rect_mode = 0  # 0=2-Punkt, 1=Center (wie Fusion360)
        self.circle_mode = 0  # 0=Center-Radius, 1=2-Punkt, 2=3-Punkt
        self.construction_mode = False
        self.fillet_radius = 5.0
        self.offset_distance = 5.0
        self.chamfer_distance = 5.0
        self.extrude_operation = "New Body"  # Für Extrude-Dialog
        
        # Kreis-Segmente für Polygonisierung (für Face-Erkennung)
        self.circle_segments = 64  # Standard: 64 für gute Genauigkeit
        
        # Muttern-Aussparung (M2-M14)
        # Schlüsselweiten in mm für metrische Sechskant-Muttern (DIN 934)
        self.nut_sizes = {
            'M2': 4.0, 'M2.5': 5.0, 'M3': 5.5, 'M4': 7.0, 'M5': 8.0,
            'M6': 10.0, 'M8': 13.0, 'M10': 17.0, 'M12': 19.0, 'M14': 22.0
        }
        self.nut_size_names = ['M2', 'M2.5', 'M3', 'M4', 'M5', 'M6', 'M8', 'M10', 'M12', 'M14']
        self.nut_size_index = 4  # Default: M5
        self.nut_tolerance = 0.2  # Toleranz/Offset in mm für 3D-Druck
        
        self.closed_profiles = []
        self.profile_parent = []   # Hierarchie: Parent-Index für jeden Profil
        self.profile_children = [] # Hierarchie: Kinder-Indizes für jeden Profil
        self.hovered_face = None  # Face unter dem Cursor
        self._last_hovered_face = None
        
        # Offset-Tool Zustand
        self.offset_dragging = False
        self.offset_start_pos = None
        self.offset_profile = None  # Das Profil das geoffsetet wird
        self.offset_preview_lines = []  # Preview der Offset-Linien
        
        # Spline-Editing (Fusion360-Style)
        self.spline_dragging = False
        self.spline_drag_type = None  # 'point', 'handle_in', 'handle_out'
        self.spline_drag_spline = None  # Die Spline die bearbeitet wird
        self.spline_drag_cp_index = None  # Index des Kontrollpunkts
        self.selected_spline = None  # Aktuell ausgewählte Spline
        self.hovered_spline_element = None  # (spline, cp_index, element_type)
        
        # Schwebende Optionen-Palette
        self.tool_options = ToolOptionsPopup(self)
        self.tool_options.option_selected.connect(self._on_tool_option_selected)
        
        # Body-Referenzen für transparente Anzeige im Hintergrund (Fusion360-Style)
        self.reference_bodies = []  # Liste von {'edges_2d': [...], 'color': (r,g,b)}
        self.show_body_reference = True  # Toggle für Anzeige
        self.body_reference_opacity = 0.25  # Transparenz der Bodies
        self.sketch_plane_normal = (0, 0, 1)  # Normale der Sketch-Ebene
        self.sketch_plane_origin = (0, 0, 0)  # Ursprung der Sketch-Ebene
        
        # --- SPATIAL INDEX OPTIMIZATION ---
        self.spatial_index = None
        self.index_dirty = True
        # Mark index dirty whenever sketch changes
        self.sketched_changed.connect(self._mark_index_dirty)
        self.hovered_ref_edge = None
        self.setStyleSheet(f"background-color: {DesignTokens.COLOR_BG_CANVAS.name()};")

        QTimer.singleShot(100, self._center_view)
    
    def _safe_float(self, value):
        """
        Konvertiert JEDEN Wert sicher zu Python native float.
        Entfernt numpy.float64, numpy.bool_, etc.
        """
        if hasattr(value, 'item'):
            # numpy scalar - .item() gibt Python native zurück
            return float(value.item())
        elif isinstance(value, (bool, np.bool_)):
            # FEHLERFALL: Boolean wurde als Zahl behandelt
            logger.warning(f"Boolean erkannt statt float: {value}. Konvertiere zu 0.0 oder 1.0")
            return float(value)
        else:
            return float(value)

    def _safe_bool(self, value):
        """
        Konvertiert JEDEN Wert sicher zu Python native bool.
        """
        if isinstance(value, np.bool_):
            return bool(value)  # numpy bool → Python bool
        return bool(value)
    
    def _solve_async(self):
        """
        Runs the constraint solver in a background thread.
        Does not block the UI.
        """
        # If already solving, we skip this frame (simple throttling)
        # Alternatively, for heavy loads, one might implement a queue, 
        # but for CAD interaction, skipping 'stale' moves is often better.
        if self._is_solving:
            return

        def run_solver():
            with self._solver_lock:
                self._is_solving = True
                try:
                    # Run the math (CPU heavy)
                    result = self.sketch.solve()
                    
                    # Extract safe primitive types to pass via Signal
                    success = getattr(result, 'success', True)
                    msg = getattr(result, 'message', "Solved")
                    dof = getattr(result, 'dof', 0)
                    
                    # Emit result to Main Thread
                    self.solver_finished_signal.emit(success, msg, self._safe_float(dof))
                except Exception as e:
                    logger.error(f"Solver Crash: {e}")
                    self.solver_finished_signal.emit(False, str(e), 0.0)
                finally:
                    self._is_solving = False

        # Start thread as daemon (dies if app closes)
        thread = Thread(target=run_solver, daemon=True)
        thread.start()

    def _on_solver_finished(self, success, message, dof):
        """
        Called when the background thread finishes. 
        Safe to update UI here.
        """
        if not success:
            # Subtle visual warning or log (don't spam toast messages on drag)
            logger.warning(f"Solver divergence: {message}")
        
        # Recalculate profiles (Faces) based on new solved geometry
        self._find_closed_profiles()
        
        # Notify rest of the system
        self.sketched_changed.emit()
        
        # Trigger repaint of the new geometry state
        self.update()
        
        # Optional: Update status only if it was a discrete operation (not while dragging)
        if self.current_tool == SketchTool.SELECT and not self.is_panning:
             # Just logging to keep HUD clean during drag
             pass
            
    def _mark_index_dirty(self):
        self.index_dirty = True

    def _debug_inspect_geometry(self):
        """
        Forensische Suche: Findet Geometrie, die versehentlich Booleans statt Zahlen enthält.
        """
        import numpy as np
        
        logger.info("🕵️ Starte Geometrie-Inspektion...")
        
        found_error = False

        def is_bad(val, name):
            # Prüft auf bool (Python) oder numpy.bool_ (NumPy)
            if isinstance(val, (bool, np.bool_)):
                logger.critical(f"🚨 FEHLER GEFUNDEN in {name}!")
                logger.critical(f"   Wert ist BOOLEAN: {val} (Typ: {type(val)})")
                logger.critical(f"   Erwartet wurde float/int.")
                return True
            return False

        # 1. Linien prüfen
        for i, line in enumerate(self.sketch.lines):
            if is_bad(line.start.x, f"Line[{i}].start.x"): found_error = True
            if is_bad(line.start.y, f"Line[{i}].start.y"): found_error = True
            if is_bad(line.end.x,   f"Line[{i}].end.x"):   found_error = True
            if is_bad(line.end.y,   f"Line[{i}].end.y"):   found_error = True

        # 2. Kreise prüfen
        for i, circle in enumerate(self.sketch.circles):
            if is_bad(circle.center.x, f"Circle[{i}].center.x"): found_error = True
            if is_bad(circle.center.y, f"Circle[{i}].center.y"): found_error = True
            if is_bad(circle.radius,   f"Circle[{i}].radius"):   found_error = True

        # 3. Arcs prüfen
        for i, arc in enumerate(self.sketch.arcs):
            if is_bad(arc.center.x, f"Arc[{i}].center.x"): found_error = True
            if is_bad(arc.center.y, f"Arc[{i}].center.y"): found_error = True
            if is_bad(arc.radius,   f"Arc[{i}].radius"):   found_error = True
            if is_bad(arc.start_angle, f"Arc[{i}].start_angle"): found_error = True
            if is_bad(arc.end_angle,   f"Arc[{i}].end_angle"):   found_error = True

        if found_error:
            logger.critical("❌ Inspektion beendet: KORRUPTE GEOMETRIE GEFUNDEN.")
        else:
            logger.success("✅ Inspektion beendet: Keine Booleans in der Geometrie gefunden.")
            
        return found_error
 

    

    def _rebuild_spatial_index(self):
        """
        Final Defensive Version: Audits geometry first, then rebuilds with strict casting.
        """
        import numpy as np
        

        # --- INTERNAL AUDIT FUNCTION ---
        def audit_geometry(sketch):
            """Checks for numpy types in geometry."""
            problems = []
            
            def check(val, name):
                if isinstance(val, (np.bool_, np.int64, np.float64, np.float32)):
                    return f"{name}={val} ({type(val)})"
                return None

            for i, l in enumerate(sketch.lines):
                if err := check(l.start.x, f"L{i}.start.x"): problems.append(err)
                if err := check(l.start.y, f"L{i}.start.y"): problems.append(err)
                if err := check(l.end.x, f"L{i}.end.x"): problems.append(err)
                if err := check(l.end.y, f"L{i}.end.y"): problems.append(err)

            return problems

        # 1. RUN AUDIT
        # If this logs errors, we know the source data is 'infected' with numpy types
        #if problems := audit_geometry(self.sketch):
            #logger.warning(f"⚠️ Geometry contains NumPy types! First 3 issues: {problems[:3]}")
            # We don't abort, because the casting below should handle it, but it's good to know.

        # 2. STANDARD CHECKS
        has_geo = (len(self.sketch.lines) > 0 or len(self.sketch.circles) > 0 or 
                   len(self.sketch.arcs) > 0 or len(self.sketch.splines) > 0)
        
        if not has_geo:
            self.spatial_index = None
            self.index_dirty = False
            return

        # 3. HELPER FOR CASTING
        def to_float(v):
            try:
                if hasattr(v, 'item'): return self._safe_float(v.item())
                return self._safe_float(v)
            except: return 0.0

        # 4. CALCULATE BOUNDS
        min_x, min_y = self._safe_float('inf'), self._safe_float('inf')
        max_x, max_y = self._safe_float('-inf'), self._safe_float('-inf')

        for l in self.sketch.lines:
            x1, y1 = to_float(l.start.x), to_float(l.start.y)
            x2, y2 = to_float(l.end.x), to_float(l.end.y)
            min_x = min(min_x, x1, x2); max_x = max(max_x, x1, x2)
            min_y = min(min_y, y1, y2); max_y = max(max_y, y1, y2)
            
        for c in self.sketch.circles + self.sketch.arcs:
            r = to_float(c.radius)
            cx, cy = to_float(c.center.x), to_float(c.center.y)
            min_x = min(min_x, cx - r); max_x = max(max_x, cx + r)
            min_y = min(min_y, cy - r); max_y = max(max_y, cy + r)

        for s in self.sketch.splines:
             for cp in getattr(s, 'control_points', []):
                 px, py = to_float(cp.point.x), to_float(cp.point.y)
                 min_x = min(min_x, px); max_x = max(max_x, px)
                 min_y = min(min_y, py); max_y = max(max_y, py)

        if min_x == self._safe_float('inf'): min_x, max_x, min_y, max_y = -100.0, 100.0, -100.0, 100.0
        
        pad = 100.0
        try:
            # FORCE NATIVE FLOATS FOR QRECT
            x1 = self._safe_float(min_x - pad)
            y1 = self._safe_float(min_y - pad)
            w = self._safe_float(max_x - min_x + 2*pad)
            h = self._safe_float(max_y - min_y + 2*pad)
            assert isinstance(x1, float) and not isinstance(x1, np.floating), \
    f"x1 ist {type(x1)}, nicht Python float!"
            root_rect = QRectF(x1, y1, w, h)
            self.spatial_index = QuadTree(root_rect)
        except Exception as e:
            logger.critical(f"❌ QuadTree init crashed: {e}")
            return

        # 5. INSERT GEOMETRY
        for l in self.sketch.lines:
            x1, y1 = to_float(l.start.x), to_float(l.start.y)
            x2, y2 = to_float(l.end.x), to_float(l.end.y)
            
            # Manual Rect construction (safest)
            lx = min(x1, x2) - 2.0
            ly = min(y1, y2) - 2.0
            lw = abs(x2 - x1) + 4.0
            lh = abs(y2 - y1) + 4.0
            
            self.spatial_index.insert(l, QRectF(self._safe_float(lx), self._safe_float(ly), self._safe_float(lw), self._safe_float(lh)))

        for c in self.sketch.circles + self.sketch.arcs:
            cx, cy = to_float(c.center.x), to_float(c.center.y)
            r = to_float(c.radius)
            self.spatial_index.insert(c, QRectF(self._safe_float(cx-r), self._safe_float(cy-r), self._safe_float(2*r), self._safe_float(2*r)))

        for s in self.sketch.splines:
             cps = getattr(s, 'control_points', [])
             if not cps: continue
             sx_min = min((to_float(cp.point.x) for cp in cps), default=0.0)
             sx_max = max((to_float(cp.point.x) for cp in cps), default=0.0)
             sy_min = min((to_float(cp.point.y) for cp in cps), default=0.0)
             sy_max = max((to_float(cp.point.y) for cp in cps), default=0.0)
             w = max(sx_max - sx_min, 0.1)
             h = max(sy_max - sy_min, 0.1)
             self.spatial_index.insert(s, QRectF(self._safe_float(sx_min), self._safe_float(sy_min), self._safe_float(w), self._safe_float(h)))

        self.index_dirty = False
       
          
    def handle_option_changed(self, option: str, value):
        """Reagiert auf Änderungen aus dem ToolPanel (Checkboxen)"""
        if option == "construction":
            self.construction_mode = self._safe_bool(value)
            # Optional: Feedback in Statuszeile, wenn per Klick geändert
            state = tr("ON") if self.construction_mode else tr("OFF")
            self.status_message.emit(tr("Construction: {state}").format(state=state))
            
        elif option == "grid_snap":
            self.grid_snap = self._safe_bool(value)
            
        elif option == "grid_size":
            self.grid_size = float(value)
            
        self.update()

    def _get_entity_bbox(self, entity):
        """Liefert das Screen-Bounding-Rect für eine Entity (Hardened against NumPy)"""
        from sketcher import Line2D, Circle2D, Arc2D
        
        rect = QRectF()
        if entity is None: 
            return rect
        
        # Helper für sicheren Cast
        def safe_pt(x, y):
            return QPointF(self._safe_float(x), self._safe_float(y))
            
        try:
            if isinstance(entity, Line2D):
                # Explizite Floats vor QPointF Erstellung
                p1 = self.world_to_screen(safe_pt(entity.start.x, entity.start.y))
                p2 = self.world_to_screen(safe_pt(entity.end.x, entity.end.y))
                rect = QRectF(p1, p2).normalized()
                
            elif isinstance(entity, (Circle2D, Arc2D)):
                c = self.world_to_screen(safe_pt(entity.center.x, entity.center.y))
                r = self._safe_float(entity.radius) * self.view_scale
                rect = QRectF(c.x()-r, c.y()-r, 2*r, 2*r)
        except Exception:
            return QRectF() # Im Zweifel leeres Rect zurückgeben
            
        # Padding für Strichstärke (5px) + Glow (10px) = sicherheitshalber 15
        return rect.adjusted(-15, -15, 15, 15)
    
    def _calculate_plane_axes(self, normal_vec):
        """
        Berechnet stabile X- und Y-Achsen.
        Returns native tuples of floats to avoid NumPy types leaking into logic.
        """
        import numpy as np # Import lokal, falls global fehlt
        
        n = np.array(normal_vec, dtype=np.float64)
        norm = np.linalg.norm(n)
        if norm == 0: 
            return (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
        
        n = n / norm
        
        # Safe comparison avoiding numpy.bool output
        # abs(n[2]) liefert numpy scalar, float() macht es sicher
        if self._safe_float(abs(n[2])) > 0.999:
            x_dir = np.array([1.0, 0.0, 0.0], dtype=np.float64)
            y_dir = np.cross(n, x_dir)
            y_dir = y_dir / np.linalg.norm(y_dir)
            x_dir = np.cross(y_dir, n)
        else:
            global_up = np.array([0.0, 0.0, 1.0], dtype=np.float64)
            x_dir = np.cross(global_up, n)
            x_dir = x_dir / np.linalg.norm(x_dir)
            y_dir = np.cross(n, x_dir)
            y_dir = y_dir / np.linalg.norm(y_dir)
            
        # CRITICAL: Convert back to native python tuple immediately
        return tuple(map(float, x_dir)), tuple(map(float, y_dir))

    def to_native_float(self, value):
        """Sicheres Casting von NumPy → Python native"""
        if hasattr(value, 'item'):
            return value.item()
        elif isinstance(value, (np.integer, np.floating)):
            return value.item()
        return self._safe_float(value)


    def world_to_screen(self, w):
        # Punkt auslesen
        if hasattr(w, 'x') and not callable(w.x):
            wx = self._safe_float(w.x)
            wy = self._safe_float(w.y)
        else:
            wx = self._safe_float(w.x())  # ← Explizit zu Python float
            wy = self._safe_float(w.y())
        
        # View-Offset auslesen (auch explizit)
        ox = self._safe_float(self.view_offset.x())
        oy = self._safe_float(self.view_offset.y())
        
        # DANN berechnen
        screen_x = self._safe_float(wx * self.view_scale) + ox
        screen_y = self._safe_float(-wy * self.view_scale) + oy
        
        # DANN in QPointF
        return QPointF(screen_x, screen_y)
    
    def screen_to_world(self, s):
        """
        Konvertiert Screen-Koordinaten zu Welt-Koordinaten.
        Gibt QPointF zurück.
        """
        # s ist hier immer ein QPointF vom MouseEvent
        ox = self.view_offset.x()
        oy = self.view_offset.y()
        
        return QPointF((s.x() - ox) / self.view_scale,
                      -(s.y() - oy) / self.view_scale)
    
    def _center_view(self):
        self.view_offset = QPointF(self.width() / 2, self.height() / 2)
        self.update()

    def show_message(self, text: str, duration: int = 3000, color: QColor = None):
        """
        Zeigt eine HUD-Nachricht als zentralen Toast an.

        Args:
            text: Die anzuzeigende Nachricht
            duration: Anzeigedauer in ms (Standard: 3000)
            color: Textfarbe (Standard: weiß)
        """
        import time
        self._hud_message = text
        self._hud_message_time = time.time() * 1000
        self._hud_duration = duration
        self._hud_color = color if color else QColor(255, 255, 255)
        self.update()

        # Timer für Refresh während Fade-out
        QTimer.singleShot(duration - 500, self.update)
        QTimer.singleShot(duration, self.update)

    def set_reference_bodies(self, bodies_data, plane_normal=(0,0,1), plane_origin=(0,0,0), plane_x=None):
        self.reference_bodies = []
        self.sketch_plane_normal = plane_normal
        self.sketch_plane_origin = plane_origin
        
        if not bodies_data:
            self.update()
            return
        
        import numpy as np
        
        # Alles in float64 casten für Präzision
        n = np.array(plane_normal, dtype=np.float64)
        norm = np.linalg.norm(n)
        n = n / norm if norm > 0 else np.array([0,0,1], dtype=np.float64)
        
        if plane_x:
            u = np.array(plane_x, dtype=np.float64)
            u = u / np.linalg.norm(u)
        else:
            if self._safe_float(abs(n[2])) < 0.9:
                u = np.cross(n, [0, 0, 1])
            else:
                u = np.cross(n, [1, 0, 0])
            u = u / np.linalg.norm(u)
            
        v = np.cross(n, u)
        origin = np.array(plane_origin, dtype=np.float64)
        
        for body_info in bodies_data:
            mesh = body_info.get('mesh')
            # Farbe parsen
            raw_color = body_info.get('color', (0.6, 0.6, 0.8))
            if isinstance(raw_color, (tuple, list)):
                color = tuple(self._safe_float(x) for x in raw_color[:3]) # Sicherstellen float
            else:
                # Fallback für String-Farben
                try: 
                    c = QColor(raw_color)
                    color = (c.redF(), c.greenF(), c.blueF())
                except: 
                    color = (0.5, 0.5, 0.5)

            if mesh is None: continue
            
            try:
                edges = mesh.extract_feature_edges(
                    boundary_edges=True, feature_edges=True, 
                    manifold_edges=False, feature_angle=30
                )
                if edges.n_points == 0: edges = mesh.extract_all_edges()
                
                edges_2d = []
                if edges.n_lines > 0:
                    lines = edges.lines # Das ist ein NumPy Array!
                    points = edges.points # Das auch!
                    
                    i = 0
                    while i < len(lines):
                        # Expliziter Cast zu int für Loop-Index
                        n_pts = int(lines[i])
                        if n_pts >= 2:
                            # Vektorisierte Berechnung wäre schneller, aber hier loop for safety
                            # Wir holen den Segment-Block
                            segment_indices = lines[i+1 : i+1+n_pts]
                            
                            # Punkte holen
                            segment_points = points[segment_indices]
                            
                            # Projektion (Vector math)
                            rels = segment_points - origin
                            
                            # Dot Product für Projektion auf 2D Ebene
                            xs = np.dot(rels, u)
                            ys = np.dot(rels, v)
                            
                            # Liniensegmente speichern (Native Floats!)
                            for k in range(n_pts - 1):
                                edges_2d.append((
                                    self._safe_float(xs[k]), self._safe_float(ys[k]), 
                                    self._safe_float(xs[k+1]), self._safe_float(ys[k+1])
                                ))
                        
                        i += n_pts + 1
                
                if edges_2d:
                    self.reference_bodies.append({
                        'edges_2d': edges_2d,
                        'color': color
                    })
            except Exception as e:
                logger.error(f"Body reference error: {e}")
        
        self.update()
    
    def _draw_body_references(self, painter):
        """Zeichnet Bodies als transparente Referenz im Hintergrund"""
        if not self.show_body_reference or not self.reference_bodies:
            return
        
        painter.save()
        
        for body in self.reference_bodies:
            edges_2d = body.get('edges_2d', [])
            raw_color = body.get('color', (0.6, 0.6, 0.8))
            
            # --- FIX: Farbe sicherstellen ---
            if isinstance(raw_color, str):
                # Falls Farbe ein Name ist (z.B. "red"), nutze QColor zum Parsen
                c = QColor(raw_color)
                color = (c.redF(), c.greenF(), c.blueF())
            elif isinstance(raw_color, (tuple, list)) and len(raw_color) >= 3:
                color = raw_color
            else:
                color = (0.5, 0.5, 0.5) # Fallback Grau
            # --------------------------------

            # Farbe mit Transparenz
            r, g, b = int(color[0]*255), int(color[1]*255), int(color[2]*255)
            alpha = int(self.body_reference_opacity * 255)
            
            pen = QPen(QColor(r, g, b, alpha))
            pen.setWidth(1)
            painter.setPen(pen)
            
            for x1, y1, x2, y2 in edges_2d:
                p1 = self.world_to_screen(QPointF(x1, y1))
                p2 = self.world_to_screen(QPointF(x2, y2))
                painter.drawLine(p1, p2)
        
        painter.restore()
    
    
    def _find_closed_profiles(self):
        """
        Kombinierte Logik: 
        1. Welding (Punkte verschweißen) gegen Mikro-Lücken (für Slots/Langlöcher).
        2. Hierarchie-Analyse (wie im 3D Modus) für korrekte Löcher/Inseln.
        """
        from shapely.geometry import LineString, Polygon as ShapelyPolygon, Point
        from shapely.ops import polygonize, unary_union
        import numpy as np

        self.closed_profiles.clear()
        
        # --- PHASE 1: Fast Welding (Coordinate Hashing) ---
        WELD_GRID = 0.1 
        welded_points = {} # Map: (ix, iy) -> (float_x, float_y)

        def get_welded_pt(x, y):
            ix = int(round(x / WELD_GRID))
            iy = int(round(y / WELD_GRID))
            key = (ix, iy)
            
            if key in welded_points:
                return welded_points[key]
            
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0: continue
                    neighbor_key = (ix + dx, iy + dy)
                    if neighbor_key in welded_points:
                        nx, ny = welded_points[neighbor_key]
                        if (x - nx)**2 + (y - ny)**2 < (WELD_GRID/2)**2:
                            return (nx, ny)
            
            welded_points[key] = (x, y)
            return (x, y)

        shapely_lines = []
        
        # 1. Linien
        lines = [l for l in self.sketch.lines if not l.construction]
        for line in lines:
            p1 = get_welded_pt(line.start.x, line.start.y)
            p2 = get_welded_pt(line.end.x, line.end.y)
            if p1 != p2:
                shapely_lines.append(LineString([p1, p2]))

        # 2. Bögen
        arcs = [a for a in self.sketch.arcs if not a.construction]
        for arc in arcs:
            start_p = get_welded_pt(arc.start_point.x, arc.start_point.y)
            end_p = get_welded_pt(arc.end_point.x, arc.end_point.y)
            
            sweep = abs(arc.end_angle - arc.start_angle)
            if sweep < 0.1: sweep += 360
            
            # Optimierung: Weniger Segmente für kleine Bögen
            steps = max(4, int(sweep / 10))
            
            points = [start_p]
            diff = arc.end_angle - arc.start_angle
            for i in range(1, steps):
                t = i / steps
                angle = math.radians(arc.start_angle + diff * t)
                px = arc.center.x + arc.radius * math.cos(angle)
                py = arc.center.y + arc.radius * math.sin(angle)
                points.append((px, py))
            points.append(end_p)
            
            if len(points) >= 2:
                shapely_lines.append(LineString(points))

        # --- 3. KREISE (FEHLENDER BLOCK HINZUGEFÜGT) ---
        # Kreise müssen in Polygone umgewandelt werden, da Shapely keine echten Kreise kennt
        standalone_polys = []
        circles = [c for c in self.sketch.circles if not c.construction]
        
        for circle in circles:
            cx, cy, r = circle.center.x, circle.center.y, circle.radius
            pts = []
            segments = 64 # Auflösung für Collision Detection
            for i in range(segments):
                a = 2 * math.pi * i / segments
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
            standalone_polys.append(ShapelyPolygon(pts))

        # --- PHASE 2: Polygonize & Raw Polygons ---
        
        raw_polys = []
        
        # Aus Linien/Bögen Flächen finden
        if shapely_lines:
            try:
                merged = unary_union(shapely_lines)
                for poly in polygonize(merged):
                    if poly.area > 0.01:
                        raw_polys.append(poly)
            except Exception as e:
                logger.warning(f"Polygonize error: {e}")

        # Eigenständige Kreise hinzufügen (wenn sie nicht schon durch Linien abgedeckt sind)
        for c_poly in standalone_polys:
            # Check auf Duplikate (falls Kreise auch als Arcs gezeichnet wurden)
            is_duplicate = False
            for existing in raw_polys:
                if abs(existing.area - c_poly.area) < 0.1 and existing.intersection(c_poly).area > c_poly.area * 0.9:
                    is_duplicate = True
                    break
            if not is_duplicate:
                raw_polys.append(c_poly)

        if not raw_polys:
            return

        # --- PHASE 3: Hierarchie & Holes (Die Logic aus GeometryDetector) ---
        
        # Sortieren nach Größe (Groß zuerst -> Parents)
        raw_polys.sort(key=lambda p: p.area, reverse=True)
        
        # Wer enthält wen?
        # hierarchy[i] = Liste von Indizes, die in Polygon i liegen
        hierarchy = {i: [] for i in range(len(raw_polys))}
        for i, parent in enumerate(raw_polys):
            for j, child in enumerate(raw_polys):
                if i == j: continue
                # contains ist teuer, aber bei 2D Sketches ist N klein (<100)
                if parent.contains(child):
                    hierarchy[i].append(j)
        
        # Direkte Kinder finden (Direct Children)
        # Ein Polygon K ist direktes Kind von P, wenn es keinen Zwischen-Parent Z gibt.
        direct_children = {i: [] for i in range(len(raw_polys))}
        
        for parent_idx, children_indices in hierarchy.items():
            for child_idx in children_indices:
                is_direct = True
                for other_child in children_indices:
                    if child_idx == other_child: continue
                    # Wenn ein anderes Kind mein Kind enthält, bin ich nicht der direkte Parent
                    if raw_polys[other_child].contains(raw_polys[child_idx]):
                        is_direct = False
                        break
                if is_direct:
                    direct_children[parent_idx].append(child_idx)

        # Profile erstellen (Parent minus direkte Kinder)
        # Wir müssen vermeiden, dass Kinder doppelt gezeichnet werden.
        # Im Sketch-Modus wollen wir ALLES zeichnen, aber Löcher sollen "leer" sein.
        
        processed = set()
        
        for i in range(len(raw_polys)):
            # Wenn dieses Polygon ein direktes Kind von irgendwem ist, 
            # wird es dort ausgeschnitten. Aber: Wenn es selbst Kinder hat (Insel),
            # muss es später wieder als positiver Shape gezeichnet werden.
            # Die einfache Regel für QPainterPath (OddEvenFill) ist:
            # Wir brauchen das "End-Polygon" mit Löchern drin.
            
            # Wir verarbeiten hier nur die "Top Level" Parents und die "Inseln" (Level 2, 4...)
            # Aber noch einfacher: Wir berechnen einfach für JEDES Polygon die Differenz zu seinen direkten Kindern.
            # Das Ergebnis ist ein Ring (oder eine Vollfläche).
            
            poly = raw_polys[i]
            children = direct_children[i]
            
            final_shape = poly
            for child_idx in children:
                try:
                    final_shape = final_shape.difference(raw_polys[child_idx])
                except Exception as e:
                    logger.warning(f"Difference error: {e}")
            
            # Speichern als Polygon
            if not final_shape.is_empty and final_shape.area > 0.01:
                self.closed_profiles.append(('polygon', final_shape))
        
        # Hinweis: Diese Methode erzeugt jetzt Shapely-Polygone, die Löcher enthalten können!
        # Der Renderer muss das verstehen.
        self._build_profile_hierarchy()
        
    def _build_profile_hierarchy(self):
        """Baut Containment-Hierarchie auf: Welche Faces sind Löcher in anderen?"""
        from shapely.geometry import Polygon as ShapelyPolygon, Point as ShapelyPoint
        
        def get_profile_vertices(profile):
            """Extrahiert Vertices aus einem Profil für Point-in-Polygon Test"""
            profile_type, data = profile
            if profile_type == 'lines':
                vertices = []
                for line in data:
                    vertices.append((line.start.x, line.start.y))
                return vertices
            elif profile_type == 'polygon':
                # Shapely Polygon - coords direkt nutzen
                return list(data.exterior.coords)[:-1]  # Ohne Schlusspunkt
            elif profile_type == 'circle':
                # Kreis als Polygon approximieren (16 Punkte)
                circle = data
                vertices = []
                for i in range(16):
                    angle = 2 * math.pi * i / 16
                    x = circle.center.x + circle.radius * math.cos(angle)
                    y = circle.center.y + circle.radius * math.sin(angle)
                    vertices.append((x, y))
                return vertices
            return []
        
        def get_profile_area(profile):
            """Berechnet Fläche eines Profils"""
            profile_type, data = profile
            if profile_type == 'lines':
                vertices = get_profile_vertices(profile)
                if len(vertices) < 3:
                    return 0
                # Shoelace Formel
                area = 0
                n = len(vertices)
                for i in range(n):
                    j = (i + 1) % n
                    area += vertices[i][0] * vertices[j][1]
                    area -= vertices[j][0] * vertices[i][1]
                return abs(area / 2)
            elif profile_type == 'polygon':
                return abs(data.area)
            elif profile_type == 'circle':
                return math.pi * data.radius ** 2
            return 0
        
        def get_profile_point(profile):
            """Gibt einen Testpunkt für Point-in-Polygon zurück"""
            profile_type, data = profile
            if profile_type == 'lines':
                # Zentroid der Vertices
                vertices = get_profile_vertices(profile)
                if not vertices:
                    return None
                cx = sum(v[0] for v in vertices) / len(vertices)
                cy = sum(v[1] for v in vertices) / len(vertices)
                return (cx, cy)
            elif profile_type == 'polygon':
                centroid = data.centroid
                return (centroid.x, centroid.y)
            elif profile_type == 'circle':
                return (data.center.x, data.center.y)
            return None
        
        def point_in_polygon(px, py, vertices):
            """Ray-Casting Algorithmus"""
            n = len(vertices)
            inside = False
            j = n - 1
            for i in range(n):
                xi, yi = vertices[i]
                xj, yj = vertices[j]
                if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
                    inside = not inside
                j = i
            return inside
        
        # Initialisiere Hierarchie-Struktur
        # parent[i] = Index des Parent-Profils, oder -1 wenn Root
        # children[i] = Liste von Kind-Indizes
        n = len(self.closed_profiles)
        self.profile_parent = [-1] * n  # -1 = kein Parent (Root)
        self.profile_children = [[] for _ in range(n)]
        
        if n == 0:
            return
        
        # Sortiere Profile nach Fläche (größte zuerst)
        # Größere Profile können kleinere enthalten
        areas = [get_profile_area(p) for p in self.closed_profiles]
        sorted_indices = sorted(range(n), key=lambda i: areas[i], reverse=True)
        
        # Für jedes Profil: Finde den kleinsten Container
        for i in range(n):
            profile_i = self.closed_profiles[i]
            point_i = get_profile_point(profile_i)
            
            if point_i is None:
                continue
            
            # Finde den kleinsten Container (mit kleinster Fläche der enthält)
            best_parent = -1
            best_parent_area = self._safe_float('inf')
            
            for j in range(n):
                if i == j:
                    continue
                
                profile_j = self.closed_profiles[j]
                vertices_j = get_profile_vertices(profile_j)
                
                if len(vertices_j) < 3:
                    continue
                
                # Prüfe ob Punkt von i in j liegt
                if point_in_polygon(point_i[0], point_i[1], vertices_j):
                    # j enthält i
                    if areas[j] < best_parent_area and areas[j] > areas[i]:
                        best_parent = j
                        best_parent_area = areas[j]
            
            self.profile_parent[i] = best_parent
            if best_parent >= 0:
                self.profile_children[best_parent].append(i)
        
        # Debug-Ausgabe
        # for i, profile in enumerate(self.closed_profiles):
        #     parent = self.profile_parent[i]
        #     children = self.profile_children[i]
        #     print(f"Profile {i}: parent={parent}, children={children}, type={profile[0]}")
    
    def is_profile_closed(self):
        self._find_closed_profiles()
        return len(self.closed_profiles) > 0
    
    def snap_point(self, w):
        if not self.snap_enabled: return w, SnapType.NONE
        
        # Performance: Umwandlung nur einmal
        r_world = self.snap_radius / self.view_scale
        
        # 1. ORIGIN CHECK (Immer Priorität, sehr schnell)
        dist_sq_origin = w.x()**2 + w.y()**2
        if dist_sq_origin < (r_world * 2)**2: # Doppelter Radius für Origin
             return QPointF(0, 0), SnapType.CENTER

        best_pt, best_dist_sq, best_t = None, r_world**2, SnapType.NONE
        
        # 2. QUADTREE QUERY: Nur relevante Geometrie holen!
        query_rect = QRectF(w.x() - r_world, w.y() - r_world, r_world * 2, r_world * 2)
        
        # Falls Index dirty, neu bauen (sollte aber durch MouseMove schon aktuell sein)
        if self.index_dirty: self._rebuild_spatial_index()
            
        # Kandidaten holen (Viel weniger als self.sketch.lines!)
        candidates = self.spatial_index.query(query_rect) if self.spatial_index else (self.sketch.lines + self.sketch.circles + self.sketch.arcs)

        # 3. Optimierte Suche auf Kandidaten
        for entity in candidates:
            # --- LINIE ---
            if hasattr(entity, 'start') and hasattr(entity, 'end'):
                # Startpunkt
                d2 = (entity.start.x - w.x())**2 + (entity.start.y - w.y())**2
                if d2 < best_dist_sq:
                    best_dist_sq, best_pt, best_t = d2, QPointF(entity.start.x, entity.start.y), SnapType.ENDPOINT
                # Endpunkt
                d2 = (entity.end.x - w.x())**2 + (entity.end.y - w.y())**2
                if d2 < best_dist_sq:
                    best_dist_sq, best_pt, best_t = d2, QPointF(entity.end.x, entity.end.y), SnapType.ENDPOINT
                # Midpoint
                mid = entity.midpoint
                d2 = (mid.x - w.x())**2 + (mid.y - w.y())**2
                if d2 < best_dist_sq:
                    best_dist_sq, best_pt, best_t = d2, QPointF(mid.x, mid.y), SnapType.MIDPOINT

            # --- KREIS / BOGEN ---
            elif hasattr(entity, 'center') and hasattr(entity, 'radius'):
                # Zentrum
                d2 = (entity.center.x - w.x())**2 + (entity.center.y - w.y())**2
                if d2 < best_dist_sq:
                    best_dist_sq, best_pt, best_t = d2, QPointF(entity.center.x, entity.center.y), SnapType.CENTER
                
                # Quadranten (nur prüfen wenn Maus nah am Kreisring ist?)
                # Optimierung: Quadranten sind teuer (sin/cos). Nur prüfen wenn wir noch keinen sehr guten Snap haben
                if best_dist_sq > (r_world * 0.1)**2: 
                    for ang in [0, 90, 180, 270]:
                        qx = entity.center.x + entity.radius * math.cos(math.radians(ang))
                        qy = entity.center.y + entity.radius * math.sin(math.radians(ang))
                        d2_q = (qx - w.x())**2 + (qy - w.y())**2
                        if d2_q < best_dist_sq:
                            best_dist_sq, best_pt, best_t = d2_q, QPointF(qx, qy), SnapType.QUADRANT

        # 4. Schnittpunkte (Teuer! Nur berechnen für Kandidaten im Sichtbereich)
        # Wenn wir schon einen sehr guten Endpoint-Snap haben, überspringen wir Intersection oft
        if best_dist_sq > 0.0001: 
            # Wir prüfen nur Intersections zwischen den Kandidaten, nicht allen Linien!
            lines = [e for e in candidates if hasattr(e, 'start')]
            for i, l1 in enumerate(lines):
                for l2 in lines[i+1:]:
                    # Bounding Box Vorprüfung
                    if not (min(l1.start.x, l1.end.x) > max(l2.start.x, l2.end.x) or 
                            max(l1.start.x, l1.end.x) < min(l2.start.x, l2.end.x) or
                            min(l1.start.y, l1.end.y) > max(l2.start.y, l2.end.y) or 
                            max(l1.start.y, l1.end.y) < min(l2.start.y, l2.end.y)):
                        
                        inter = self._line_intersection(l1, l2)
                        if inter:
                            d2 = (inter.x() - w.x())**2 + (inter.y() - w.y())**2
                            if d2 < best_dist_sq:
                                best_dist_sq, best_pt, best_t = d2, inter, SnapType.INTERSECTION

        # Grid als Fallback
        if best_pt is None and self.grid_snap:
            gx = round(w.x() / self.grid_size) * self.grid_size
            gy = round(w.y() / self.grid_size) * self.grid_size
            best_pt, best_t = QPointF(gx, gy), SnapType.GRID
        
        return (best_pt, best_t) if best_pt else (w, SnapType.NONE)
    
    def _line_intersection(self, l1, l2):
        x1, y1, x2, y2 = l1.start.x, l1.start.y, l1.end.x, l1.end.y
        x3, y3, x4, y4 = l2.start.x, l2.start.y, l2.end.x, l2.end.y
        d = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
        if abs(d) < 1e-10: return None
        t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / d
        s = -((x1-x2)*(y1-y3) - (y1-y2)*(x1-x3)) / d
        if 0 <= t <= 1 and 0 <= s <= 1:
            return QPointF(x1 + t*(x2-x1), y1 + t*(y2-y1))
        return None
    
    def _save_undo(self):
        self.undo_stack.append(self.sketch.to_dict())
        self.redo_stack.clear()
        if len(self.undo_stack) > self.max_undo: self.undo_stack.pop(0)
    
    def undo(self):
        if not self.undo_stack:
            self.show_message(tr("Nothing to undo"), 1500, QColor(255, 200, 100))
            return
        self.redo_stack.append(self.sketch.to_dict())
        self.sketch = Sketch.from_dict(self.undo_stack.pop())
        self._clear_selection()
        self._find_closed_profiles()
        self.sketched_changed.emit()
        self.show_message(tr("Undone"), 1500)
        logger.debug("Undo performed")
        self.update()

    def redo(self):
        if not self.redo_stack:
            self.show_message(tr("Nothing to redo"), 1500, QColor(255, 200, 100))
            return
        self.undo_stack.append(self.sketch.to_dict())
        self.sketch = Sketch.from_dict(self.redo_stack.pop())
        self._clear_selection()
        self._find_closed_profiles()
        self.sketched_changed.emit()
        self.show_message(tr("Redone"), 1500)
        logger.debug("Redo performed")
        self.update()
    
    def import_dxf(self, filepath=None):
        """Startet den Import im Hintergrund"""
        from PySide6.QtWidgets import QFileDialog, QApplication
        from PySide6.QtGui import Qt
        
        try:
            import ezdxf
        except ImportError:
            self.status_message.emit("Fehler: 'ezdxf' fehlt.")
            return

        if filepath is None:
            filepath, _ = QFileDialog.getOpenFileName(
                self, "DXF importieren", "", "DXF Dateien (*.dxf);;Alle Dateien (*)"
            )
        if not filepath: return

        self.status_message.emit("Starte Import (High-Fidelity)...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        
        # Worker starten
        self._dxf_worker = DXFImportWorker(filepath)
        self._dxf_worker.finished_signal.connect(self._on_dxf_finished)
        self._dxf_worker.error_signal.connect(self._on_dxf_error)
        self._dxf_worker.progress_signal.connect(self.status_message.emit)
        self._dxf_worker.start()

    def _on_dxf_finished(self, lines, circles, arcs):
        from PySide6.QtWidgets import QApplication
        
        self._save_undo()
        
        # Linien hinzufügen
        for l in lines:
            self.sketch.add_line(l[0], l[1], l[2], l[3])
            
        # Kreise hinzufügen
        for c in circles:
            self.sketch.add_circle(c[0], c[1], c[2])
        
        # Arcs hinzufügen
        for a in arcs:
            # a = (cx, cy, radius, start_angle, end_angle)
            self.sketch.add_arc(a[0], a[1], a[2], a[3], a[4])
            
        QApplication.restoreOverrideCursor()
        self._find_closed_profiles()
        self.sketched_changed.emit()
        self.status_message.emit(f"Fertig: {len(lines)} Linien, {len(circles)} Kreise, {len(arcs)} Bögen.")
        self.update()
        self._dxf_worker = None

    def _on_dxf_error(self, err):
        from PySide6.QtWidgets import QApplication
        QApplication.restoreOverrideCursor()
        self.status_message.emit(f"Import Fehler: {err}")
        self._dxf_worker = None
    
    def export_dxf(self, filepath=None):
        """Exportiert als DXF-Datei"""
        from PySide6.QtWidgets import QFileDialog
        
        if filepath is None:
            filepath, _ = QFileDialog.getSaveFileName(
                self, "DXF exportieren", "", "DXF Dateien (*.dxf);;Alle Dateien (*)"
            )
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'w') as f:
                f.write("0\nSECTION\n2\nENTITIES\n")
                
                for line in self.sketch.lines:
                    f.write(f"0\nLINE\n8\n0\n")
                    f.write(f"10\n{line.start.x}\n20\n{line.start.y}\n30\n0\n")
                    f.write(f"11\n{line.end.x}\n21\n{line.end.y}\n31\n0\n")
                
                for circle in self.sketch.circles:
                    f.write(f"0\nCIRCLE\n8\n0\n")
                    f.write(f"10\n{circle.center.x}\n20\n{circle.center.y}\n30\n0\n")
                    f.write(f"40\n{circle.radius}\n")
                
                f.write("0\nENDSEC\n0\nEOF\n")
            
            self.status_message.emit(tr("DXF exported: {path}").format(path=filepath))
            
        except Exception as e:
            self.status_message.emit(tr("DXF export error: {e}").format(e=e))
    
    # ==================== BUILD123D INTEGRATION ====================
    
    def _detect_circle_from_points(self, points, tolerance=0.02):
        """
        Erkennt ob ein Polygon eigentlich ein Kreis ist.
        
        Args:
            points: Liste von (x, y) Tupeln
            tolerance: Relative Toleranz für Radius-Varianz
            
        Returns:
            (cx, cy, radius) als native Floats wenn es ein Kreis ist, sonst None
        """
        if len(points) < 8:
            return None
        
        import numpy as np
        pts = np.array(points)
        
        cx = np.mean(pts[:, 0])
        cy = np.mean(pts[:, 1])
        
        distances = np.sqrt((pts[:, 0] - cx)**2 + (pts[:, 1] - cy)**2)
        radius = np.mean(distances)
        
        if radius < 0.1:
            return None
        
        variance = np.std(distances) / radius
        
        # FIX: float() cast in comparison
        if self._safe_float(variance) < tolerance:
            # FIX: Native Floats zurückgeben
            return (self._safe_float(cx), self._safe_float(cy), self._safe_float(radius))
        
        return None
    
    def get_build123d_plane(self):
        """Sichere Methode um die Plane zu holen"""
        if not HAS_BUILD123D: return None
        origin = getattr(self.sketch, 'plane_origin', (0, 0, 0))
        normal = getattr(self.sketch, 'plane_normal', (0, 0, 1))
        x_dir = getattr(self.sketch, 'plane_x_dir', None) # Kann None sein!

        try:
            if x_dir:
                return Plane(origin=origin, x_dir=x_dir, z_dir=normal)
            else:
                # Fallback: Build123d rät die X-Richtung
                return Plane(origin=origin, z_dir=normal)
        except Exception:
            # Fallback bei mathematischen Fehlern (z.B. Vektoren parallel)
            return Plane.XY
    
    def get_build123d_sketch(self, plane=None):
        """
        Konvertiert den aktuellen Sketch zu einem Build123d BuildSketch.
        
        Returns:
            BuildSketch oder None wenn Build123d nicht verfügbar
        """
        if not HAS_BUILD123D:
            logger.warning("Build123d nicht verfügbar!")
            return None
        
        if plane is None:
            plane = self.get_build123d_plane()
        
        try:
            # Sammle alle nicht-construction Geometrie
            lines = [l for l in self.sketch.lines if not l.construction]
            circles = [c for c in self.sketch.circles if not c.construction]
            arcs = [a for a in self.sketch.arcs if not a.construction]
            
            if not lines and not circles and not arcs:
                logger.warning("Keine Geometrie im Sketch!")
                return None
            
            # Erstelle Build123d Sketch
            with BuildSketch(plane) as sketch:
                # Linien hinzufügen
                for line in lines:
                    with BuildLine():
                        B3DLine(
                            (line.start.x, line.start.y),
                            (line.end.x, line.end.y)
                        )
                
                # Kreise hinzufügen - mit Locations für Position
                for circle in circles:
                    with Locations([(circle.center.x, circle.center.y)]):
                        B3DCircle(radius=circle.radius)
                
                # Arcs hinzufügen (als CenterArc)
                for arc in arcs:
                    start_deg = arc.start_angle
                    end_deg = arc.end_angle
                    
                    # Berechne arc_size (Sweep)
                    arc_size = end_deg - start_deg
                    if arc_size < 0:
                        arc_size += 360
                    
                    with BuildLine():
                        CenterArc(
                            center=(arc.center.x, arc.center.y),
                            radius=arc.radius,
                            start_angle=start_deg,
                            arc_size=arc_size
                        )
                
                # Faces erzeugen aus den Linien
                make_face()
            
            return sketch
            
        except Exception as e:
            logger.error(f"Build123d Sketch Konvertierung fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_build123d_part(self, height: float, operation: str = "New Body"):
        """
        Extrudiert den Sketch. Fängt Fehler ab und liefert None zurück, 
        statt abzustürzen.
        """
        if not HAS_BUILD123D:
            return None, None, None
        
        # 1. Zwingend Profile neu berechnen (das repariert oft das "kaputte" Rechteck)
        self._find_closed_profiles()
        
        if not self.closed_profiles:
            logger.warning("Keine geschlossenen Profile gefunden.")
            return None, None, None
        
        # DEBUG: Zeige alle gefundenen Profile
        logger.debug(f"=== {len(self.closed_profiles)} Profile gefunden ===")
        for i, (p_type, p_data) in enumerate(self.closed_profiles):
            if p_type == 'polygon':
                n_holes = len(list(p_data.interiors)) if hasattr(p_data, 'interiors') else 0
                logger.debug(f"  [{i}] Polygon: area={p_data.area:.1f}, holes={n_holes}")
            elif p_type == 'circle':
                logger.debug(f"  [{i}] Circle: r={p_data.radius:.2f} at ({p_data.center.x:.1f}, {p_data.center.y:.1f})")
            
        plane = self.get_build123d_plane()
        
        try:
            solid = None
            
            with BuildPart() as part:
                with BuildSketch(plane):
                    created_any = False
                    for p_type, p_data in self.closed_profiles:
                        # Fall 1: Polygon
                        if p_type == 'polygon':
                            coords = list(p_data.exterior.coords)
                            # Duplikate entfernen und zu Floats konvertieren
                            pts = [(self._safe_float(c[0]), self._safe_float(c[1])) for c in coords]
                            if len(pts) > 0 and pts[0] == pts[-1]:
                                pts.pop() # Letzten Punkt weg, wenn doppelt
                            
                            if len(pts) >= 3:
                                logger.debug(f"Erstelle Polygon mit {len(pts)} Punkten")
                                Polygon(*pts, align=None)
                                created_any = True
                                
                                # Löcher (Interiors)
                                if hasattr(p_data, 'interiors'):
                                    for idx, interior in enumerate(p_data.interiors):
                                        hole_coords = list(interior.coords)
                                        h_pts = [(self._safe_float(c[0]), self._safe_float(c[1])) for c in hole_coords]
                                        if len(h_pts)>0 and h_pts[0]==h_pts[-1]: h_pts.pop()
                                        
                                        logger.debug(f"  Loch {idx}: {len(h_pts)} Punkte")
                                        
                                        if len(h_pts) >= 3:
                                            # FIX: Prüfen ob das Loch ein Kreis ist
                                            circle_info = self._detect_circle_from_points(h_pts)
                                            
                                            if circle_info:
                                                # Echten Kreis verwenden!
                                                cx, cy, radius = circle_info
                                                logger.info(f"  → Loch als ECHTER KREIS: r={radius:.2f} at ({cx:.2f}, {cy:.2f})")
                                                with Locations([(cx, cy)]):
                                                    B3DCircle(radius=radius, mode=Mode.SUBTRACT)
                                            else:
                                                # Normales Polygon-Loch
                                                logger.warning(f"  → Loch als POLYGON ({len(h_pts)} Punkte)")
                                                Polygon(*h_pts, align=None, mode=Mode.SUBTRACT)

                        # Fall 2: Kreis
                        elif p_type == 'circle':
                            logger.debug(f"Erstelle Kreis r={p_data.radius:.2f}")
                            with Locations((p_data.center.x, p_data.center.y)):
                                B3DCircle(radius=p_data.radius)
                            created_any = True

                # Nur extrudieren, wenn Sketch-Elemente da sind
                if created_any:
                    extrude(amount=height)
                    solid = part.part
            
            if solid is None:
                return None, None, None

            # Mesh generieren
            mesh_data = solid.tessellate(tolerance=0.05)
            verts = [(v.X, v.Y, v.Z) for v in mesh_data[0]]
            faces = [tuple(t) for t in mesh_data[1]]
            
            return solid, verts, faces
            
        except Exception as e:
            # Statt GUI-Absturz nur Log-Ausgabe
            logger.error(f"Extrude Fehler: {e}")
            return None, None, None
    
    def _build123d_direct(self, height: float, plane):
        """Erstellt Build123d Part direkt aus Sketch-Linien (Fallback)"""
        if not HAS_BUILD123D:
            return None, None, None
        
        lines = [l for l in self.sketch.lines if not l.construction]
        circles = [c for c in self.sketch.circles if not c.construction]
        
        if not lines and not circles:
            logger.warning("Build123d: Keine Geometrie!")
            return None, None, None
        
        try:
            with BuildPart() as part:
                with BuildSketch(plane):
                    # Versuche Rechteck zu erkennen (4 Linien, geschlossen)
                    if len(lines) == 4 and not circles:
                        # Sammle alle Endpunkte
                        points = set()
                        for l in lines:
                            points.add((round(l.start.x, 4), round(l.start.y, 4)))
                            points.add((round(l.end.x, 4), round(l.end.y, 4)))
                        
                        if len(points) == 4:
                            # Es ist ein Rechteck!
                            pts = list(points)
                            xs = [p[0] for p in pts]
                            ys = [p[1] for p in pts]
                            min_x, max_x = min(xs), max(xs)
                            min_y, max_y = min(ys), max(ys)
                            width = max_x - min_x
                            height_rect = max_y - min_y
                            center_x = (min_x + max_x) / 2
                            center_y = (min_y + max_y) / 2
                            
                            logger.debug(f"Rechteck erkannt: {width}x{height_rect} at ({center_x}, {center_y})")
                            
                            with Locations([(center_x, center_y)]):
                                Rectangle(width, height_rect)
                    
                    # Kreise hinzufügen
                    for circle in circles:
                        logger.debug(f"Kreis: r={circle.radius} at ({circle.center.x}, {circle.center.y})")
                        with Locations([(circle.center.x, circle.center.y)]):
                            B3DCircle(radius=circle.radius)
                
                extrude(amount=height)
            
            solid = part.part
            if solid is None:
                return None, None, None
            
            logger.success(f"Build123d Direct: Solid erstellt!")
            
            mesh_data = solid.tessellate(tolerance=0.1)
            verts = [(v.X, v.Y, v.Z) for v in mesh_data[0]]
            faces = [tuple(t) for t in mesh_data[1]]
            
            return solid, verts, faces
            
        except Exception as e:
            logger.error(f"Build123d Direct fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return None, None, None
    
    def _build123d_from_profiles(self, height: float, plane):
        """Erstellt Build123d Part auf der korrekten Ebene"""
        if not HAS_BUILD123D: return None, None, None
        
        try:
            with BuildPart() as part:
                # Plane wird jetzt korrekt ausgerichtet sein (dank z_dir oben)
                with BuildSketch(plane):
                    created = False
                    
                    for p_type, p_data in self.closed_profiles:
                        if p_type == 'polygon' and hasattr(p_data, 'exterior'):
                            coords = list(p_data.exterior.coords)
                            # Punkte in Float wandeln
                            pts = [(self._safe_float(c[0]), self._safe_float(c[1])) for c in coords]
                            
                            if len(pts) > 1 and pts[0] == pts[-1]: pts.pop()
                            
                            if len(pts) >= 3:
                                # WICHTIG: 
                                # 1. *pts (Sternchen) für Argument-Liste
                                # 2. align=None (damit es nicht zentriert wird)
                                Polygon(*pts, align=None)
                                created = True
                                
                        elif p_type == 'circle':
                            c = p_data.center
                            # Auch hier: Locations sind lokal auf der Plane
                            with Locations([(self._safe_float(c.x), self._safe_float(c.y))]):
                                B3DCircle(radius=self._safe_float(p_data.radius))
                            created = True
                            
                    if not created: return None, None, None

                # Extrusion in Richtung der Plane-Normalen
                extrude(amount=height)
            
            solid = part.part
            if solid is None: return None, None, None
            
            # Mesh für Anzeige generieren
            mesh = solid.tessellate(tolerance=0.01)
            verts = [(v.X, v.Y, v.Z) for v in mesh[0]]
            faces = [tuple(t) for t in mesh[1]]
            
            return solid, verts, faces
            
        except Exception as e:
            logger.error(f"Build123d Fehler: {e}")
            return None, None, None
    
    def has_build123d(self) -> bool:
        """Prüft ob Build123d verfügbar ist"""
        return HAS_BUILD123D
    
    def set_tool(self, tool):
        self._cancel_tool()
        self.current_tool = tool
        self.tool_changed.emit(tool)
        self._update_cursor()
        self._show_tool_hint()
        self._show_tool_options()  # Optionen-Popup
        self.update()
    
    def _show_tool_options(self):
        """Zeigt Optionen-Popup für Tools die Optionen haben"""
        tool = self.current_tool
        has_options = False
        
        # Rechteck: 2-Punkt vs Center
        if tool == SketchTool.RECTANGLE:
            self.tool_options.show_options(
                tr("RECTANGLE MODE"),
                "rect_mode",
                [("⬚", tr("2-Point")), ("⊞", tr("Center"))],
                self.rect_mode
            )
            has_options = True
            
        # Kreis: Center vs 2-Punkt vs 3-Punkt
        elif tool == SketchTool.CIRCLE:
            self.tool_options.show_options(
                tr("CIRCLE TYPE"),
                "circle_mode",
                [("◎", tr("Center")), ("⌀", tr("2-Point")), ("◯", tr("3-Point"))],
                self.circle_mode
            )
            has_options = True
            
        # Polygon: Anzahl Seiten
        elif tool == SketchTool.POLYGON:
            # Index finden oder Default 0
            idx = 0
            if self.polygon_sides in [3, 4, 5, 6, 8]:
                idx = [3, 4, 5, 6, 8].index(self.polygon_sides)
            
            self.tool_options.show_options(
                tr("SIDES"),
                "polygon_sides",
                [("△", "3"), ("◇", "4"), ("⬠", "5"), ("⬡", "6"), ("⯃", "8")],
                idx
            )
            has_options = True
            
        # Muttern-Aussparung: Größe M2-M14
        elif tool == SketchTool.NUT:
            self.tool_options.show_options(
                f"NUT: {self.nut_size_names[self.nut_size_index]}",
                "nut_size",
                [(f"⬡", s) for s in self.nut_size_names],
                self.nut_size_index
            )
            has_options = True
        
        else:
            self.tool_options.hide()
            return

        # POSITIONIERUNG
        if has_options:
            # FIX: Nur neu positionieren, wenn es noch nicht sichtbar ist!
            # Verhindert, dass das Fenster wegspringt, wenn man einen Button klickt.
            if not self.tool_options.isVisible():
                # Neue Smart-Positioning Methode verwenden
                self.tool_options.position_smart(self, 20, 20)
            
            # Sicherstellen, dass es über allem liegt
            self.tool_options.raise_()
    
    def _on_tool_option_selected(self, option_name, value):
        """Handler für Optionen-Auswahl"""
        if option_name == "rect_mode":
            self.rect_mode = value
        elif option_name == "circle_mode":
            self.circle_mode = value
        elif option_name == "polygon_sides":
            self.polygon_sides = [3, 4, 5, 6, 8][value]
        elif option_name == "nut_size":
            self.nut_size_index = value
        
        self._show_tool_hint()  # Hint aktualisieren
        self._show_tool_options()  # Optionen-Titel aktualisieren (für Toleranz-Anzeige)
        self.update()
    
    def _cancel_tool(self):
        self.tool_step = 0
        self.tool_points.clear()
        self.tool_data.clear()
        self.selection_box_start = None
        self.selection_box_end = None
        self.dim_input.hide()
        self.dim_input.unlock_all()  # Locks zurücksetzen!
        self.dim_input_active = False
        # NICHT tool_options.hide() - Palette bleibt sichtbar solange Tool aktiv!
        
        # Offset-Tool Reset
        self.offset_dragging = False
        self.offset_profile = None
        self.offset_start_pos = None
        self.offset_preview_lines = []
        
        self.update()
    
    def _update_cursor(self):
        if self.current_tool == SketchTool.SELECT: self.setCursor(Qt.ArrowCursor)
        elif self.current_tool == SketchTool.MOVE: self.setCursor(Qt.SizeAllCursor)
        else: self.setCursor(Qt.CrossCursor)
    
    def _show_tool_hint(self):
        n_sel = len(self.selected_lines) + len(self.selected_circles) + len(self.selected_arcs) + len(self.selected_points)
        sel_info = f" ({n_sel} ausgewählt)" if n_sel > 0 else ""
        
        hints = {
            SketchTool.SELECT: tr("Click=Select | Shift+Click=Multi | Drag=Box | Del=Delete"),
            SketchTool.LINE: tr("Click=Start | Tab=Length/Angle | RightClick=Finish"),
            SketchTool.RECTANGLE: tr("Rectangle") + f" ({tr('Center') if self.rect_mode else tr('2-Point')}) | " + tr("Click=Start"),
            SketchTool.RECTANGLE_CENTER: tr("Rectangle") + " (" + tr("Center") + ") | " + tr("Click=Start"),
            SketchTool.CIRCLE: tr("Circle") + f" ({[tr('Center'), tr('2-Point'), tr('3-Point')][self.circle_mode]}) | Tab=" + tr("Radius"),
            SketchTool.CIRCLE_2POINT: tr("Circle") + " (" + tr("2-Point") + ")",
            SketchTool.POLYGON: tr("Polygon") + f" ({self.polygon_sides} " + tr("{n} sides").format(n="") + ") | Tab",
            SketchTool.ARC_3POINT: tr("[A] Arc | Click=Start→Through→End"),
            SketchTool.SLOT: tr("Slot | Click=Start"),
            SketchTool.SPLINE: tr("Spline | Click=Points | Right=Finish"),
            SketchTool.MOVE: tr("[M] Move | Click=Base→Target") + sel_info,
            SketchTool.COPY: tr("Copy") + sel_info,
            SketchTool.ROTATE: tr("Rotate") + sel_info + " | Tab=°",
            SketchTool.MIRROR: tr("Mirror") + sel_info,
            SketchTool.SCALE: tr("[S] Scale | Click=Center") + sel_info,
            SketchTool.TRIM: tr("Trim | Click on segment"),
            SketchTool.EXTEND: tr("Extend | Click on line"),
            SketchTool.OFFSET: tr("Offset") + f" ({self.offset_distance:+g}mm) | Tab",
            SketchTool.FILLET_2D: tr("Fillet") + f" (R={self.fillet_radius:g}mm) | Tab=" + tr("Radius"),
            SketchTool.CHAMFER_2D: tr("Chamfer") + f" ({self.chamfer_distance:g}mm) | Tab=" + tr("Length"),
            SketchTool.DIMENSION: tr("Dimension | Click on element"),
            SketchTool.DIMENSION_ANGLE: tr("Angle") + " | " + tr("Click=Line1→Line2"),
            SketchTool.HORIZONTAL: tr("Horizontal (H)"),
            SketchTool.VERTICAL: tr("Vertical (V)"),
            SketchTool.PARALLEL: tr("Parallel | Click=Line1→Line2"),
            SketchTool.PERPENDICULAR: tr("Perpendicular | Click=Line1→Line2"),
            SketchTool.EQUAL: tr("Equal | Click=Element1→Element2"),
            SketchTool.CONCENTRIC: tr("Concentric | Click=Circle1→Circle2"),
            SketchTool.TANGENT: tr("Tangent") + " | " + tr("Click=Line→Circle"),
            SketchTool.PATTERN_LINEAR: tr("Lin. Pattern | Select→Dialog"),
            SketchTool.PATTERN_CIRCULAR: tr("Circ. Pattern | Select→Center"),
            SketchTool.GEAR: tr("Gear generator | Click=Center"),
            SketchTool.STAR: tr("Star") + " | " + tr("Click=Center"),
            SketchTool.NUT: tr("Nut") + f" {self.nut_size_names[self.nut_size_index]} | +/- " + tr("Tolerance"),
            SketchTool.TEXT: tr("Text") + " | " + tr("Click=Position"),
        }
        self.status_message.emit(hints.get(self.current_tool, ""))
    
    def _show_dimension_input(self):
        fields = []
        
        # LINE: Nach erstem Punkt
        if self.current_tool == SketchTool.LINE and self.tool_step >= 1:
            fields = [("L", "length", self.live_length, "mm"), ("∠", "angle", self.live_angle, "°")]
        
        # RECTANGLE: Nach erstem Punkt ODER bevor erster Punkt (dann Standardwerte)
        elif self.current_tool == SketchTool.RECTANGLE:
            if self.tool_step == 1:
                fields = [("B", "width", self.live_width, "mm"), ("H", "height", self.live_height, "mm")]
            elif self.tool_step == 0:
                fields = [("B", "width", 50.0, "mm"), ("H", "height", 30.0, "mm")]
                
        elif self.current_tool == SketchTool.RECTANGLE_CENTER:
            if self.tool_step == 1:
                fields = [("B", "width", self.live_width, "mm"), ("H", "height", self.live_height, "mm")]
            elif self.tool_step == 0:
                fields = [("B", "width", 50.0, "mm"), ("H", "height", 30.0, "mm")]
                
        # CIRCLE: Nach Zentrum ODER bevor (dann Standardwerte)
        elif self.current_tool == SketchTool.CIRCLE:
            if self.tool_step >= 1:
                fields = [("R", "radius", self.live_radius, "mm")]
            elif self.tool_step == 0:
                fields = [("R", "radius", 25.0, "mm")]
                
        # POLYGON: Nach Zentrum
        elif self.current_tool == SketchTool.POLYGON:
            if self.tool_step >= 1:
                fields = [("R", "radius", self.live_radius, "mm"), ("N", "sides", self._safe_float(self.polygon_sides), "")]
            elif self.tool_step == 0:
                fields = [("R", "radius", 25.0, "mm"), ("N", "sides", self._safe_float(self.polygon_sides), "")]
                
        elif self.current_tool == SketchTool.MOVE and self.tool_step == 1:
            fields = [("X", "dx", 0.0, "mm"), ("Y", "dy", 0.0, "mm")]
        elif self.current_tool == SketchTool.COPY and self.tool_step == 1:
            # COPY benutzt die gleichen Felder wie MOVE
            fields = [("X", "dx", 0.0, "mm"), ("Y", "dy", 0.0, "mm")]
        elif self.current_tool == SketchTool.ROTATE and self.tool_step >= 1:
            fields = [("∠", "angle", 0.0, "°")]
        elif self.current_tool == SketchTool.SCALE and self.tool_step >= 1:
            fields = [("F", "factor", 1.0, "")]
            
        # SLOT: Nach Startpunkt (Länge/Winkel), Nach Mittellinie (Breite)
        elif self.current_tool == SketchTool.SLOT:
            if self.tool_step == 1:
                fields = [("L", "length", 50.0, "mm"), ("∠", "angle", 0.0, "°")]
            elif self.tool_step == 2:
                fields = [("B", "width", 10.0, "mm")]
            
        # OFFSET: Immer verfügbar (auch negativ!)
        elif self.current_tool == SketchTool.OFFSET:
            fields = [("D", "distance", self.offset_distance, "mm")]
            
        elif self.current_tool == SketchTool.FILLET_2D:
            fields = [("R", "radius", self.fillet_radius, "mm")]
        elif self.current_tool == SketchTool.CHAMFER_2D:
            fields = [("L", "length", self.chamfer_distance, "mm")]
        
        # PATTERN: Linear und Circular
        elif self.current_tool == SketchTool.PATTERN_LINEAR and self.tool_step >= 1:
            count = self.tool_data.get('pattern_count', 3)
            spacing = self.tool_data.get('pattern_spacing', 20.0)
            fields = [("Anzahl", "count", self._safe_float(count), "x"), ("Abstand", "spacing", spacing, "mm")]
            
        elif self.current_tool == SketchTool.PATTERN_CIRCULAR and self.tool_step >= 1:
            count = self.tool_data.get('pattern_count', 6)
            angle = self.tool_data.get('pattern_angle', 360.0)
            fields = [("Anzahl", "count", self._safe_float(count), "x"), ("Winkel", "angle", angle, "°")]
            
        if not fields:
            self.status_message.emit(tr("Tab: Set a point first or choose another tool"))
            return
        
        self.dim_input.setup(fields)
        pos = self.mouse_screen
        x = min(int(pos.x()) + 20, self.width() - self.dim_input.width() - 10)
        y = min(int(pos.y()) - 40, self.height() - self.dim_input.height() - 10)
        self.dim_input.move(max(10, x), max(10, y))
        self.dim_input.show()
        self.dim_input.focus_field(0)
        self.dim_input_active = True
    
    def _on_dim_value_changed(self, key, value):
        if self.current_tool == SketchTool.LINE:
            if key == "length": self.live_length = value
            elif key == "angle": self.live_angle = value
        elif self.current_tool in [SketchTool.RECTANGLE, SketchTool.RECTANGLE_CENTER]:
            if key == "width": self.live_width = value
            elif key == "height": self.live_height = value
        elif self.current_tool == SketchTool.CIRCLE:
            if key == "radius": self.live_radius = value
        elif self.current_tool == SketchTool.POLYGON:
            if key == "radius": self.live_radius = value
            elif key == "sides": self.polygon_sides = max(3, min(64, int(value)))
        elif self.current_tool == SketchTool.OFFSET:
            self.offset_distance = value
            self._update_offset_preview()  # Preview sofort aktualisieren
        elif self.current_tool == SketchTool.FILLET_2D: self.fillet_radius = value
        elif self.current_tool == SketchTool.CHAMFER_2D: self.chamfer_distance = value
        elif self.current_tool == SketchTool.PATTERN_LINEAR:
            if key == "count": 
                self.tool_data['pattern_count'] = max(2, int(value))
            elif key == "spacing": 
                self.tool_data['pattern_spacing'] = value
            # Bei Linear Pattern müssen wir die Vorschau erzwingen
            self.update()
                
        elif self.current_tool == SketchTool.PATTERN_CIRCULAR:
            if key == "count": 
                self.tool_data['pattern_count'] = max(2, int(value))
            elif key == "angle": 
                self.tool_data['pattern_angle'] = value
            self.update()
        self.update()
    
    def _on_dim_confirmed(self):
        from sketcher.constraints import ConstraintType
        from sketcher.geometry import Line2D, Circle2D, Arc2D

        values = self.dim_input.get_values()

        # Helper für Solver-Check und Profil-Update
        def run_solver_and_update():
            result = self.sketch.solve()
            self._find_closed_profiles()
            self.sketched_changed.emit()
            
            # Prüfen ob der Solver erfolgreich war
            if hasattr(result, 'success') and not result.success:
                msg = getattr(result, 'message', 'Unbekannter Fehler')
                self.show_message(f"⚠️ Geometrie-Konflikt: {msg}", 4000, QColor(255, 50, 50))
            return result

        # === EDITING MODE: Constraint/Geometrie bearbeiten ===
        if self.editing_entity is not None:
            self._save_undo()

            if self.editing_mode == "constraint":
                # Constraint-Wert ändern
                new_val = values.get("value", 0.0)
                self.editing_entity.value = new_val
                run_solver_and_update()
                self.show_message(f"Constraint auf {new_val:.2f} geändert", 2000, QColor(100, 255, 100))
                logger.debug(f"Constraint {self.editing_entity.type.name} geändert auf {new_val}")

            elif self.editing_mode == "line_length":
                # Längen-Constraint zu Linie hinzufügen
                new_length = values.get("length", 10.0)
                self.sketch.add_length(self.editing_entity, new_length)
                run_solver_and_update()
                self.show_message(f"Länge {new_length:.2f} mm festgelegt", 2000, QColor(100, 255, 100))

            elif self.editing_mode == "circle_radius":
                # Radius-Constraint zu Kreis/Bogen hinzufügen
                new_radius = values.get("radius", 10.0)
                self.sketch.add_radius(self.editing_entity, new_radius)
                run_solver_and_update()
                self.show_message(f"Radius {new_radius:.2f} mm festgelegt", 2000, QColor(100, 255, 100))

            # Editing-State zurücksetzen
            self.editing_entity = None
            self.editing_mode = None
            self.dim_input.hide()
            self.dim_input.unlock_all()
            self.dim_input_active = False
            self.update()
            return

        # === EXTRUDE MODE ===
        if self.viewport and getattr(self.viewport, 'extrude_mode', False):
            height = values.get("height", 0.0)
            op = values.get("operation", "New Body") 
            
            self.viewport.extrude_height = height
            self.viewport.confirm_extrusion(operation=op)
            
            self.dim_input.hide()
            self.dim_input.unlock_all()
            self.dim_input_active = False
            self.status_message.emit(f"Extrusion ({op}) angewendet.")
            return
            
        # === SKETCH TOOLS ===
        
        if self.current_tool == SketchTool.LINE and self.tool_step >= 1:
            start = self.tool_points[-1]
            
            if self.dim_input.is_locked('length'):
                length = self.live_length
            else:
                length = values.get("length", 10)
            
            if self.dim_input.is_locked('angle'):
                angle_deg = self.live_angle
            else:
                angle_deg = values.get("angle", 0)
            
            angle = math.radians(angle_deg)
            end_x = start.x() + length * math.cos(angle)
            end_y = start.y() + length * math.sin(angle)
            
            self._save_undo()
            line = self.sketch.add_line(start.x(), start.y(), end_x, end_y, construction=self.construction_mode)
            
            # Optional: Hier könnten wir direkt Constraints (Länge/Winkel) hinzufügen,
            # wenn wir strikt parametrisch sein wollen. Aktuell setzen wir nur die Geometrie.
            
            self.tool_points.append(QPointF(end_x, end_y))
            self._find_closed_profiles() # Wichtig für Füllung
            self.sketched_changed.emit()
            
        elif self.current_tool == SketchTool.RECTANGLE:
            w = self.live_width if self.dim_input.is_locked('width') else values.get("width", 50)
            h = self.live_height if self.dim_input.is_locked('height') else values.get("height", 30)
            
            p1 = self.tool_points[0] if self.tool_step >= 1 else (self.mouse_world or QPointF(0, 0))
            self._save_undo()
            
            if self.rect_mode == 1: # Center
                self.sketch.add_rectangle(p1.x() - w/2, p1.y() - h/2, w, h, construction=self.construction_mode)
            else: # 2-Point
                mouse = self.mouse_world if self.mouse_world else p1
                x = p1.x() - w if mouse.x() < p1.x() else p1.x()
                y = p1.y() - h if mouse.y() < p1.y() else p1.y()
                self.sketch.add_rectangle(x, y, w, h, construction=self.construction_mode)
            
            run_solver_and_update()
            QTimer.singleShot(0, self._cancel_tool)
            
        elif self.current_tool == SketchTool.RECTANGLE_CENTER:
            w, h = values.get("width", 50), values.get("height", 30)
            c = self.tool_points[0] if self.tool_step >= 1 else (self.mouse_world or QPointF(0, 0))
            
            self._save_undo()
            self.sketch.add_rectangle(c.x() - w/2, c.y() - h/2, w, h, construction=self.construction_mode)
            run_solver_and_update()
            QTimer.singleShot(0, self._cancel_tool)
            
        elif self.current_tool == SketchTool.CIRCLE:
            r = self.live_radius if self.dim_input.is_locked('radius') else values.get("radius", 25)
            c = self.tool_points[0] if self.tool_step >= 1 else (self.mouse_world or QPointF(0, 0))
            
            self._save_undo()
            self.sketch.add_circle(c.x(), c.y(), r, construction=self.construction_mode)
            # Hinweis: Wenn wir hier Constraints wollen, müssten wir add_radius aufrufen
            run_solver_and_update()
            QTimer.singleShot(0, self._cancel_tool)
            
        elif self.current_tool == SketchTool.POLYGON:
            r = self.live_radius if self.dim_input.is_locked('radius') else values.get("radius", 25)
            n = int(values.get("sides", self.polygon_sides))
            c = self.tool_points[0] if self.tool_step >= 1 else (self.mouse_world or QPointF(0, 0))
            
            self._save_undo()
            # Berechnung der Punkte
            pts = [(c.x() + r*math.cos(2*math.pi*i/n - math.pi/2), c.y() + r*math.sin(2*math.pi*i/n - math.pi/2)) for i in range(n)]
            self.sketch.add_polygon(pts, closed=True, construction=self.construction_mode)
            run_solver_and_update()
            QTimer.singleShot(0, self._cancel_tool)
            
        elif self.current_tool == SketchTool.MOVE and self.tool_step == 1:
            dx, dy = values.get("dx", 0), values.get("dy", 0)
            self._save_undo()
            self._move_selection(dx, dy)
            # Move ruft intern oft solve() auf, aber sicherheitshalber:
            run_solver_and_update()
            self._cancel_tool()

        elif self.current_tool == SketchTool.ROTATE and self.tool_step >= 1:
            center = self.tool_points[0] if self.tool_points else QPointF(0, 0)
            angle = values.get("angle", 0)
            self._save_undo()
            self._rotate_selection(center, angle)
            run_solver_and_update()
            self._cancel_tool()

        elif self.current_tool == SketchTool.SCALE and self.tool_step >= 1:
            center = self.tool_points[0] if self.tool_points else QPointF(0, 0)
            factor = values.get("factor", 1.0)
            self._save_undo()
            self._scale_selection(center, factor)
            run_solver_and_update()
            self._cancel_tool()

        elif self.current_tool == SketchTool.COPY and self.tool_step == 1:
            dx, dy = values.get("dx", 0), values.get("dy", 0)
            self._save_undo()
            self._copy_selection_with_offset(dx, dy)
            run_solver_and_update()
            self._cancel_tool()

        # SLOT: Tab-Eingabe
        elif self.current_tool == SketchTool.SLOT:
            if self.tool_step == 1:
                p1 = self.tool_points[0]
                length = values.get("length", 50.0)
                angle = math.radians(values.get("angle", 0.0))
                p2 = QPointF(p1.x() + length * math.cos(angle), p1.y() + length * math.sin(angle))
                self.tool_points.append(p2)
                self.tool_step = 2
                self.status_message.emit(tr("Width | Tab=Enter width"))
            elif self.tool_step == 2:
                p1, p2 = self.tool_points[0], self.tool_points[1]
                width = values.get("width", 10.0)
                if width > 0.01:
                    self._save_undo()
                    self._create_slot(p1, p2, width)
                    run_solver_and_update()
                QTimer.singleShot(0, self._cancel_tool)
        
        # OFFSET, FILLET, CHAMFER: Nur Wert speichern
        elif self.current_tool == SketchTool.OFFSET:
            self.offset_distance = values.get("distance", 5.0)
            if self.tool_step == 1 and self.offset_profile:
                self._update_offset_preview()
                self.status_message.emit(tr("Offset: {dist}mm | Tab=Change | Enter/Click=Apply | Esc=Cancel").format(dist=f"{self.offset_distance:+.2f}"))
            else:
                self.status_message.emit(tr("Offset: {dist}mm | Click on element").format(dist=f"{self.offset_distance:+.2f}"))
            
        elif self.current_tool == SketchTool.FILLET_2D:
            self.fillet_radius = values.get("radius", 5.0)
            self.status_message.emit(tr("Fillet: R={r}mm (click corner)").format(r=self.fillet_radius))
            
        elif self.current_tool == SketchTool.CHAMFER_2D:
            self.chamfer_distance = values.get("length", 5.0)
            self.status_message.emit(tr("Chamfer: {d}mm (click corner)").format(d=self.chamfer_distance))
        
        # PATTERN LINEAR: Werte speichern und direkt anwenden bei Enter
        elif self.current_tool == SketchTool.PATTERN_LINEAR and self.tool_step >= 1:
            self.tool_data['pattern_count'] = max(2, int(values.get("count", 3)))
            self.tool_data['pattern_spacing'] = values.get("spacing", 20.0)
            # Bei Enter: Direkt anwenden mit aktueller Mausposition als Richtung
            self._apply_linear_pattern(self.mouse_world)
            return  # _apply_linear_pattern ruft _cancel_tool auf

        # PATTERN CIRCULAR: Werte speichern und direkt anwenden bei Enter
        elif self.current_tool == SketchTool.PATTERN_CIRCULAR and self.tool_step >= 1:
            self.tool_data['pattern_count'] = max(2, int(values.get("count", 6)))
            self.tool_data['pattern_angle'] = values.get("angle", 360.0)
            # Bei Enter: Direkt anwenden
            self._apply_circular_pattern()
            return  # _apply_circular_pattern ruft _cancel_tool auf
        
        self.dim_input.hide()
        self.dim_input.unlock_all()
        self.dim_input_active = False
        self.setFocus()
        self.update()
    
    def mousePressEvent(self, event):
        pos = event.position()
        self.mouse_screen = pos
        self.mouse_world = self.screen_to_world(pos)
        
        # Wenn DimensionInput aktiv: Klick außerhalb = BESTÄTIGEN
        if self.dim_input_active and self.dim_input.isVisible():
            if not self.dim_input.geometry().contains(pos.toPoint()):
                self._on_dim_confirmed()  # Bestätigt statt nur schließen!
                return
        
        if event.button() == Qt.MiddleButton:
            self.is_panning = True
            self.pan_start = pos
            self.setCursor(Qt.ClosedHandCursor)
            return
        
        if event.button() == Qt.LeftButton:
            # Constraint-Icon-Klick prüfen (höchste Priorität im SELECT-Modus)
            if self.current_tool == SketchTool.SELECT:
                clicked_constraint = self._find_constraint_at(pos)
                if clicked_constraint:
                    ctrl = event.modifiers() & Qt.ControlModifier
                    if not ctrl:
                        self.selected_constraints.clear()
                    if clicked_constraint not in self.selected_constraints:
                        self.selected_constraints.append(clicked_constraint)
                    else:
                        self.selected_constraints.remove(clicked_constraint)
                    self.status_message.emit(f"Constraint ausgewählt: {clicked_constraint.type.name}")
                    self.update()
                    return

            # Spline-Element-Klick prüfen (hat Priorität im SELECT-Modus)
            if self.current_tool == SketchTool.SELECT:
                spline_elem = self._find_spline_element_at(self.mouse_world)
                if spline_elem:
                    spline, cp_idx, elem_type = spline_elem
                    self.spline_dragging = True
                    self.spline_drag_spline = spline
                    self.spline_drag_cp_index = cp_idx
                    self.spline_drag_type = elem_type
                    self.selected_spline = spline
                    self._save_undo()
                    self.setCursor(Qt.ClosedHandCursor)
                    self.status_message.emit(tr("Drag spline {type} | Shift=Corner").format(type=elem_type))
                    return
            
            snapped, snap_type = self.snap_point(self.mouse_world)
            if self.current_tool == SketchTool.SELECT and not self._find_entity_at(snapped):
                # Auch Spline-Kurve selbst prüfen
                spline = self._find_spline_at(self.mouse_world)
                if spline:
                    self.selected_spline = spline
                    self._clear_selection()
                    self.status_message.emit(tr("Spline selected - drag points/handles"))
                    self.update()
                    return
                self.selection_box_start = pos
                self.selection_box_end = pos
                return
            handler = getattr(self, f'_handle_{self.current_tool.name.lower()}', None)
            if handler: handler(snapped, snap_type)
        elif event.button() == Qt.RightButton:
            if self.tool_step > 0: self._finish_current_operation()
            else: self._show_context_menu(pos)
        self.update()
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self.is_panning = False
            self._update_cursor()
        if event.button() == Qt.LeftButton:
            # Spline-Dragging beenden
            if self.spline_dragging:
                self._finish_spline_drag()
                self._update_cursor()
            if self.selection_box_start:
                self._finish_selection_box()
        self.update()

    def mouseDoubleClickEvent(self, event):
        """Doppelklick auf Constraint-Icon oder Geometrie öffnet DimensionInput-Editor"""
        from sketcher.constraints import ConstraintType
        from sketcher.geometry import Line2D, Circle2D, Arc2D

        pos = event.position()
        constraint = self._find_constraint_at(pos)

        if constraint and constraint.type in [ConstraintType.LENGTH, ConstraintType.RADIUS,
                                               ConstraintType.DIAMETER, ConstraintType.ANGLE,
                                               ConstraintType.DISTANCE]:
            # Constraint bearbeiten mit DimensionInput
            current_val = constraint.value if constraint.value else 0.0
            type_name = constraint.type.name

            # Editing-State setzen
            self.editing_entity = constraint
            self.editing_mode = "constraint"

            # Unit-Label basierend auf Typ
            if constraint.type == ConstraintType.ANGLE:
                unit = "°"
                label = "∠"
            elif constraint.type == ConstraintType.DIAMETER:
                unit = "mm"
                label = "Ø"
            elif constraint.type == ConstraintType.RADIUS:
                unit = "mm"
                label = "R"
            else:
                unit = "mm"
                label = "L"

            # DimensionInput Setup
            fields = [(label, "value", current_val, unit)]
            self.dim_input.setup(fields)
            self.dim_input.move(int(pos.x()) + 20, int(pos.y()) + 10)
            self.dim_input.show()
            self.dim_input.focus_field(0)
            self.dim_input_active = True
            self.show_message(f"{type_name}: Enter = Bestätigen, Esc = Abbrechen", 2000)
            return

        # Wenn kein Constraint getroffen: Prüfe auf Geometrie für Quick-Dimension
        world_pos = self.screen_to_world(pos)
        entity = self._find_entity_at(world_pos)

        if entity:
            if isinstance(entity, Line2D):
                # Quick-Length mit DimensionInput
                current_length = entity.length
                self.editing_entity = entity
                self.editing_mode = "line_length"

                fields = [("L", "length", current_length, "mm")]
                self.dim_input.setup(fields)
                self.dim_input.move(int(pos.x()) + 20, int(pos.y()) + 10)
                self.dim_input.show()
                self.dim_input.focus_field(0)
                self.dim_input_active = True
                self.show_message("Länge: Enter = Constraint hinzufügen, Esc = Abbrechen", 2000)

            elif isinstance(entity, (Circle2D, Arc2D)):
                # Quick-Radius mit DimensionInput
                current_radius = entity.radius
                self.editing_entity = entity
                self.editing_mode = "circle_radius"

                fields = [("R", "radius", current_radius, "mm")]
                self.dim_input.setup(fields)
                self.dim_input.move(int(pos.x()) + 20, int(pos.y()) + 10)
                self.dim_input.show()
                self.dim_input.focus_field(0)
                self.dim_input_active = True
                self.show_message("Radius: Enter = Constraint hinzufügen, Esc = Abbrechen", 2000)
    
    def _finish_spline_drag(self):
        """Beendet das Spline-Dragging und aktualisiert die Linien-Approximation"""
        if not self.spline_dragging or not self.spline_drag_spline:
            self.spline_dragging = False
            return
        
        spline = self.spline_drag_spline
        
        # Alte Linien der Spline entfernen (verwende gespeicherte Referenzen)
        if hasattr(spline, '_lines') and spline._lines:
            for old_line in spline._lines:
                if old_line in self.sketch.lines:
                    self.sketch.lines.remove(old_line)
                # Auch die Punkte entfernen
                if old_line.start in self.sketch.points:
                    self.sketch.points.remove(old_line.start)
                if old_line.end in self.sketch.points:
                    self.sketch.points.remove(old_line.end)
        
        # Neue Linien generieren
        new_lines = spline.to_lines(segments_per_span=10)
        spline._lines = new_lines  # Referenz aktualisieren
        
        for line in new_lines:
            self.sketch.lines.append(line)
            self.sketch.points.append(line.start)
        if new_lines:
            self.sketch.points.append(new_lines[-1].end)
        
        # Reset Drag-State aber behalte Spline-Selection
        self.spline_dragging = False
        self.spline_drag_spline = None
        self.spline_drag_cp_index = None
        self.spline_drag_type = None
        
        self.sketched_changed.emit()
        self._find_closed_profiles()
        self.status_message.emit(tr("Spline updated"))
    
    def mouseMoveEvent(self, event):
        pos = event.position()
        self.mouse_screen = pos
        self.mouse_world = self.screen_to_world(pos)
        if self.tool_step > 0:
            # Snap und Live-Werte müssen trotzdem berechnet werden
            snapped, snap_type = self.snap_point(self.mouse_world)
            self.current_snap = (snapped, snap_type) if snap_type != SnapType.NONE else None
            self._update_live_values(snapped)
            
            self.update() # Erzwingt komplettes Neuziehnen -> Löscht alte "Geister"
            return
        needs_full_update = False
        dirty_region = QRectF()
        
        # 1. Basis-Interaktionen
        if self.is_panning:
            self.view_offset += pos - self.pan_start
            self.pan_start = pos
            self.update() # Pan braucht Full Redraw
            return
            
        elif self.spline_dragging:
            self._drag_spline_element(event.modifiers() & Qt.ShiftModifier)
            # Dragging aktualisiert Update selber oder braucht Full Update
            return 
            
        elif self.selection_box_start:
            # Smart Update für Selection Box:
            # Altes Box-Rect und neues Box-Rect invalidieren
            old_rect = QRectF(self.selection_box_start, self.selection_box_end).normalized()
            self.selection_box_end = pos
            new_rect = QRectF(self.selection_box_start, self.selection_box_end).normalized()
            
            # Union der beiden Rects updaten (+ Padding für Border)
            dirty_region = old_rect.united(new_rect).adjusted(-2, -2, 2, 2)
            self.update(dirty_region.toRect())
            return
        
        else:
            # 2. Snapping und Hover-Logik
            snapped, snap_type = self.snap_point(self.mouse_world)
            
            # Snap-Update Check
            old_snap = self.current_snap
            self.current_snap = (snapped, snap_type) if snap_type != SnapType.NONE else None
            
            if self.current_snap != old_snap:
                # Snap hat sich geändert -> Bereich um alten und neuen Snap invalidieren
                if old_snap:
                    p_old = self.world_to_screen(old_snap[0])
                    dirty_region = dirty_region.united(QRectF(p_old.x()-10, p_old.y()-10, 20, 20))
                if self.current_snap:
                    p_new = self.world_to_screen(self.current_snap[0])
                    dirty_region = dirty_region.united(QRectF(p_new.x()-10, p_new.y()-10, 20, 20))
            
            if self.current_tool == SketchTool.PROJECT:
                self.hovered_ref_edge = self._find_reference_edge_at(self.mouse_world)
                if self.hovered_ref_edge:
                    # Cursor ändern um Interaktivität zu zeigen
                    self.setCursor(Qt.PointingHandCursor)
                    # Wir brauchen ein Update, um das Highlight zu zeichnen
                    dirty_region = dirty_region.united(self.rect()) 
                else:
                    self._update_cursor()
            else:
                self.hovered_ref_edge = None

            # Entity Hover Logic (DAS IST DER KEY PERF BOOSTER)
            new_hovered = self._find_entity_at(self.mouse_world)
            
            if new_hovered != self._last_hovered_entity:
                # 1. Markiere altes Entity als Dirty (um Highlight zu entfernen)
                if self._last_hovered_entity:
                    dirty_region = dirty_region.united(self._get_entity_bbox(self._last_hovered_entity))
                
                # 2. Markiere neues Entity als Dirty (um Highlight zu zeichnen)
                if new_hovered:
                    dirty_region = dirty_region.united(self._get_entity_bbox(new_hovered))
                
                self.hovered_entity = new_hovered
                self._last_hovered_entity = new_hovered
            
            # Face Hover Logic
            new_face = self._find_face_at(self.mouse_world)
            if new_face != self._last_hovered_face:
                # Da Faces groß sein können, machen wir hier lieber ein Full Update wenn sich Face ändert
                # ODER: Wir invalidieren das Bounding Rect des Faces (wäre besser)
                needs_full_update = True 
                self.hovered_face = new_face
                self._last_hovered_face = new_face

            # Cursor-Feedback
            if self.current_tool == SketchTool.SELECT:
                spline_elem = self._find_spline_element_at(self.mouse_world)
                if spline_elem != self.hovered_spline_element:
                     # Spline Handle Hover changed -> Update Spline area
                     if spline_elem:
                         # bbox der ganzen spline holen (teuer, aber ok für hover change)
                         pass # TODO
                     needs_full_update = True # Einfachheitshalber
                
                self.hovered_spline_element = spline_elem
                if spline_elem:
                    self.setCursor(Qt.OpenHandCursor)
                else:
                    self._update_cursor()
                    
            # 3. Live-Werte (für Tooltips/HUD)
            self._update_live_values(snapped)

        # FINAL UPDATE CALL
        if needs_full_update:
            self.update()
        elif not dirty_region.isEmpty():
            # Konvertiere float QRectF zu integer QRect für update()
            # .toAlignedRect() rundet sicher auf, damit nichts abgeschnitten wird
            self.update(dirty_region.toAlignedRect())
        elif self.dim_input.isVisible():
             # HUD Updates (Koordinaten etc) brauchen leider oft Full Update
             # Wenn wir nur Koordinaten unten links ändern, könnten wir das optimieren:
             # self.update(0, self.height()-30, 200, 30)
             pass
        
    def _find_reference_edge_at(self, pos):
        """Findet eine Kante in den Background-Bodies"""
        if not self.reference_bodies or not self.show_body_reference:
            return None
            
        r = self.snap_radius / self.view_scale
        px, py = pos.x(), pos.y()
        
        # Hilfsfunktion für Abstand Punkt zu Linie
        def dist_sq(x, y, x1, y1, x2, y2):
            A = x - x1
            B = y - y1
            C = x2 - x1
            D = y2 - y1
            dot = A * C + B * D
            len_sq = C * C + D * D
            param = -1
            if len_sq != 0:
                param = dot / len_sq
            
            if param < 0:
                xx, yy = x1, y1
            elif param > 1:
                xx, yy = x2, y2
            else:
                xx = x1 + param * C
                yy = y1 + param * D
                
            dx = x - xx
            dy = y - yy
            return dx * dx + dy * dy

        # Suche in allen Bodies
        for body in self.reference_bodies:
            edges = body.get('edges_2d', [])
            for edge in edges:
                x1, y1, x2, y2 = edge
                # Grober Bounding Box Check zuerst (Performance)
                if px < min(x1, x2) - r or px > max(x1, x2) + r or \
                   py < min(y1, y2) - r or py > max(y1, y2) + r:
                    continue
                
                d2 = dist_sq(px, py, x1, y1, x2, y2)
                if d2 < r*r:
                    return edge
        return None


    def _drag_spline_element(self, shift_pressed):
        """Zieht ein Spline-Element und aktualisiert die Vorschau sofort"""
        if not self.spline_drag_spline or self.spline_drag_cp_index is None:
            return
        
        spline = self.spline_drag_spline
        cp_idx = self.spline_drag_cp_index
        cp = spline.control_points[cp_idx]
        
        snapped, _ = self.snap_point(self.mouse_world)
        new_x, new_y = snapped.x(), snapped.y()
        
        # Positionen aktualisieren
        if self.spline_drag_type == 'point':
            cp.point.x = new_x
            cp.point.y = new_y
        elif self.spline_drag_type == 'handle_in':
            if shift_pressed: # Corner Mode
                cp.smooth = False
                cp.handle_in = (new_x - cp.point.x, new_y - cp.point.y)
            else: # Smooth Mode
                cp.smooth = True
                cp.set_handle_in_abs(new_x, new_y)
        elif self.spline_drag_type == 'handle_out':
            if shift_pressed:
                cp.smooth = False
                cp.handle_out = (new_x - cp.point.x, new_y - cp.point.y)
            else:
                cp.smooth = True
                cp.set_handle_out_abs(new_x, new_y)
        
        # FIX: Vorschau erzwingen
        try:
            # Wir speichern die temporären Linien direkt im Spline-Objekt
            spline._preview_lines = spline.to_lines(segments_per_span=10)
            self.update() # Wichtig: PaintEvent neu triggern
        except Exception as e:
            logger.error(f"Spline preview error: {e}")
    
    def _update_live_values(self, snapped):
        """Aktualisiert Live-Werte NUR wenn die Felder nicht manuell editiert wurden"""
        if self.current_tool == SketchTool.LINE and self.tool_step >= 1:
            start = self.tool_points[-1]
            dx, dy = snapped.x() - start.x(), snapped.y() - start.y()
            # Nur aktualisieren wenn nicht gelockt
            if not self.dim_input.is_locked('length'):
                self.live_length = math.hypot(dx, dy)
                if self.dim_input.isVisible():
                    self.dim_input.set_value('length', self.live_length)
            if not self.dim_input.is_locked('angle'):
                self.live_angle = math.degrees(math.atan2(dy, dx))
                if self.dim_input.isVisible():
                    self.dim_input.set_value('angle', self.live_angle)
                
        elif self.current_tool in [SketchTool.RECTANGLE, SketchTool.RECTANGLE_CENTER] and self.tool_step == 1:
            p1 = self.tool_points[0]
            if self.rect_mode == 1:  # Center-Modus
                new_width = abs(snapped.x() - p1.x()) * 2
                new_height = abs(snapped.y() - p1.y()) * 2
            else:  # 2-Punkt-Modus
                new_width = abs(snapped.x() - p1.x())
                new_height = abs(snapped.y() - p1.y())
            # Nur aktualisieren wenn nicht gelockt
            if not self.dim_input.is_locked('width'):
                self.live_width = new_width
                if self.dim_input.isVisible():
                    self.dim_input.set_value('width', self.live_width)
            if not self.dim_input.is_locked('height'):
                self.live_height = new_height
                if self.dim_input.isVisible():
                    self.dim_input.set_value('height', self.live_height)
                
        elif self.current_tool == SketchTool.CIRCLE and self.tool_step == 1:
            c = self.tool_points[0]
            if not self.dim_input.is_locked('radius'):
                self.live_radius = math.hypot(snapped.x() - c.x(), snapped.y() - c.y())
                if self.dim_input.isVisible():
                    self.dim_input.set_value('radius', self.live_radius)
                
        elif self.current_tool == SketchTool.POLYGON and self.tool_step == 1:
            c = self.tool_points[0]
            if not self.dim_input.is_locked('radius'):
                self.live_radius = math.hypot(snapped.x() - c.x(), snapped.y() - c.y())
                if self.dim_input.isVisible():
                    self.dim_input.set_value('radius', self.live_radius)
    
    def wheelEvent(self, event):
        pos = event.position()
        world_before = self.screen_to_world(pos)
        factor = 1.15 if event.angleDelta().y() > 0 else 1/1.15
        self.view_scale = max(0.5, min(200, self.view_scale * factor))
        world_after = self.screen_to_world(pos)
        self.view_offset += QPointF((world_after.x() - world_before.x()) * self.view_scale,
                                   -(world_after.y() - world_before.y()) * self.view_scale)
        self.update()
    
    
    def keyPressEvent(self, event):
        key, mod = event.key(), event.modifiers()
        if self.dim_input_active and self.dim_input.isVisible():
            if key == Qt.Key_Escape:
                self.dim_input.hide()
                self.dim_input_active = False
                self.setFocus()
                return
            elif key == Qt.Key_Tab:
                self.dim_input.next_field()
                return
            elif key in (Qt.Key_Return, Qt.Key_Enter):
                # FIX: Enter wird bereits vom LineEdit-Signal (returnPressed) verarbeitet.
                # Ein manueller Aufruf von _confirm() hier führt zur doppelten Erstellung 
                # (einmal korrekt, einmal als "Geister-Objekt" an der Mausposition).
                # Wir konsumieren das Event nur, damit es nicht weitergereicht wird.
                # self.dim_input._confirm() <--- ENTFERNT
                return
            return
        
        # Enter zum Bestätigen (für Offset etc.)
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if self.current_tool == SketchTool.OFFSET and self.tool_step == 1:
                self._apply_offset()
                return
            elif self.tool_step > 0:
                self._finish_current_operation()
                return
        
        if mod & Qt.ControlModifier:
            if key == Qt.Key_Z: self.undo(); return
            elif key == Qt.Key_Y: self.redo(); return
            elif key == Qt.Key_A: self._select_all(); return
            elif key == Qt.Key_I: self.import_dxf(); return
            elif key == Qt.Key_E: self.export_dxf(); return
        
        if key == Qt.Key_Tab:
            self._show_dimension_input()
            return
        
        shortcuts = {
            Qt.Key_Escape: lambda: self._cancel_tool() if self.tool_step > 0 else self.set_tool(SketchTool.SELECT),
            Qt.Key_Space: lambda: self.set_tool(SketchTool.SELECT),
            Qt.Key_L: lambda: self.set_tool(SketchTool.LINE),
            Qt.Key_R: lambda: self.set_tool(SketchTool.RECTANGLE),
            Qt.Key_C: lambda: self.set_tool(SketchTool.CIRCLE),
            Qt.Key_P: lambda: self.set_tool(SketchTool.POLYGON),
            Qt.Key_A: lambda: self.set_tool(SketchTool.ARC_3POINT),
            Qt.Key_M: lambda: self.set_tool(SketchTool.MOVE),
            Qt.Key_O: lambda: self.set_tool(SketchTool.OFFSET),
            Qt.Key_T: lambda: self.set_tool(SketchTool.TRIM),
            Qt.Key_E: lambda: self.set_tool(SketchTool.EXTEND),
            Qt.Key_D: lambda: self.set_tool(SketchTool.DIMENSION),
            Qt.Key_N: lambda: self.set_tool(SketchTool.NUT),  # N für Mutter
            Qt.Key_Delete: self._delete_selected,
            Qt.Key_F: self._fit_view,
            Qt.Key_G: self._toggle_grid_snap,
            Qt.Key_X: self._toggle_construction,
            Qt.Key_H: lambda: self._apply_constraint('horizontal'),
            Qt.Key_V: lambda: self._apply_constraint('vertical'),
            # Neue Shortcuts für Bearbeitungstools
            Qt.Key_K: lambda: self.set_tool(SketchTool.COPY),      # K für Kopieren
            Qt.Key_Q: lambda: self.set_tool(SketchTool.ROTATE),    # Q für Rotieren  
            Qt.Key_I: lambda: self.set_tool(SketchTool.MIRROR),    # I für Spiegeln (mIrror)
            Qt.Key_S: lambda: self.set_tool(SketchTool.SCALE),     # S für Skalieren
            Qt.Key_Plus: self._increase_tolerance,   # + für Toleranz erhöhen
            Qt.Key_Minus: self._decrease_tolerance,  # - für Toleranz verringern
            Qt.Key_P: lambda: self.set_tool(SketchTool.PROJECT), # <--- NEU
        }
        if key in shortcuts: shortcuts[key](); self.update()
    

  
            
    def _finish_current_operation(self):
        if self.current_tool == SketchTool.SPLINE and len(self.tool_points) >= 2:
            self._finish_spline()
            return
        self._cancel_tool()
    
    def _toggle_grid_snap(self):
        self.grid_snap = not self.grid_snap
        state = tr("ON") if self.grid_snap else tr("OFF")
        self.status_message.emit(tr("Grid snap: {state}").format(state=state))
        
        # WICHTIG: Signal senden, damit die Checkbox im ToolPanel aktualisiert wird
        self.grid_snap_mode_changed.emit(self.grid_snap)
        self.update()
    
    def _toggle_construction(self):
        self.construction_mode = not self.construction_mode
        state = tr("ON") if self.construction_mode else tr("OFF")
        self.status_message.emit(tr("Construction: {state}").format(state=state))
        
        # WICHTIG: Signal senden, damit die Checkbox im ToolPanel aktualisiert wird
        self.construction_mode_changed.emit(self.construction_mode)
        self.update()
    
    def _increase_tolerance(self):
        """Toleranz für Muttern erhöhen"""
        self.nut_tolerance = round(min(2.0, self.nut_tolerance + 0.1), 2)
        self.status_message.emit(tr("Nut tolerance: {tol}mm").format(tol=f"{self.nut_tolerance:.2f}"))
        if self.current_tool == SketchTool.NUT:
            self._show_tool_options()  # Titel aktualisieren
    
    def _decrease_tolerance(self):
        """Toleranz für Muttern verringern"""
        self.nut_tolerance = round(max(0.0, self.nut_tolerance - 0.1), 2)
        self.status_message.emit(tr("Nut tolerance: {tol}mm").format(tol=f"{self.nut_tolerance:.2f}"))
        if self.current_tool == SketchTool.NUT:
            self._show_tool_options()  # Titel aktualisieren
    
    def _clear_selection(self):
        self.selected_lines.clear()
        self.selected_circles.clear()
        self.selected_arcs.clear()
        self.selected_points.clear()
        self.selected_constraints.clear()
        self.selected_spline = None
    
    def _select_all(self):
        self._clear_selection()
        self.selected_lines = list(self.sketch.lines)
        self.selected_circles = list(self.sketch.circles)
        self.selected_arcs = list(self.sketch.arcs)
        # Nur standalone Punkte (nicht Teil anderer Geometrie)
        used_point_ids = set()
        for line in self.sketch.lines:
            used_point_ids.add(line.start.id)
            used_point_ids.add(line.end.id)
        for circle in self.sketch.circles:
            used_point_ids.add(circle.center.id)
        for arc in self.sketch.arcs:
            used_point_ids.add(arc.center.id)
        self.selected_points = [p for p in self.sketch.points if p.id not in used_point_ids]
        self.update()
    
    def _finish_selection_box(self):
        if not self.selection_box_start or not self.selection_box_end: return
        x1, y1 = self.selection_box_start.x(), self.selection_box_start.y()
        x2, y2 = self.selection_box_end.x(), self.selection_box_end.y()
        rect = QRectF(min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1))
        if not (QApplication.keyboardModifiers() & Qt.ShiftModifier): self._clear_selection()
        for line in self.sketch.lines:
            p1 = self.world_to_screen(QPointF(line.start.x, line.start.y))
            p2 = self.world_to_screen(QPointF(line.end.x, line.end.y))
            if rect.contains(p1) and rect.contains(p2) and line not in self.selected_lines:
                self.selected_lines.append(line)
        for circle in self.sketch.circles:
            center = self.world_to_screen(QPointF(circle.center.x, circle.center.y))
            r = circle.radius * self.view_scale
            if rect.contains(QRectF(center.x()-r, center.y()-r, 2*r, 2*r)) and circle not in self.selected_circles:
                self.selected_circles.append(circle)
        for arc in self.sketch.arcs:
            center = self.world_to_screen(QPointF(arc.center.x, arc.center.y))
            r = arc.radius * self.view_scale
            if rect.contains(QRectF(center.x()-r, center.y()-r, 2*r, 2*r)) and arc not in self.selected_arcs:
                self.selected_arcs.append(arc)
        # Standalone Punkte
        used_point_ids = self._get_used_point_ids()
        for pt in self.sketch.points:
            if pt.id not in used_point_ids:
                pos = self.world_to_screen(QPointF(pt.x, pt.y))
                if rect.contains(pos) and pt not in self.selected_points:
                    self.selected_points.append(pt)
        self.selection_box_start = None
        self.selection_box_end = None
    
    def _get_used_point_ids(self):
        """Gibt IDs aller Punkte zurück die Teil anderer Geometrie sind"""
        used = set()
        for line in self.sketch.lines:
            used.add(line.start.id)
            used.add(line.end.id)
        for circle in self.sketch.circles:
            used.add(circle.center.id)
        for arc in self.sketch.arcs:
            used.add(arc.center.id)
        return used
    
    def _delete_selected(self):
        # Zuerst Constraints löschen
        if self.selected_constraints:
            self._save_undo()
            count = len(self.selected_constraints)
            for c in self.selected_constraints[:]:
                if c in self.sketch.constraints:
                    self.sketch.constraints.remove(c)
            self.selected_constraints.clear()
            self.sketch.solve()
            self.sketched_changed.emit()
            self.show_message(f"{count} Constraint(s) gelöscht", 2000, QColor(100, 255, 100))
            logger.debug(f"Deleted {count} constraints")
            self.update()
            return

        if not self.selected_lines and not self.selected_circles and not self.selected_arcs and not self.selected_points:
            return
        self._save_undo()
        deleted_count = len(self.selected_lines) + len(self.selected_circles) + len(self.selected_arcs) + len(self.selected_points)
        for line in self.selected_lines[:]:
            self.sketch.delete_line(line)
        for circle in self.selected_circles[:]:
            self.sketch.delete_circle(circle)
        for arc in self.selected_arcs[:]:
            self.sketch.delete_arc(arc)
        for pt in self.selected_points[:]:
            if pt in self.sketch.points:
                self.sketch.points.remove(pt)
        self._clear_selection()
        self._find_closed_profiles()
        self.sketched_changed.emit()
        self.show_message(f"{deleted_count} Element(e) gelöscht", 2000, QColor(100, 255, 100))
        logger.debug(f"Deleted {deleted_count} elements")
        self.update()

    def _find_constraint_at(self, screen_pos):
        """Findet einen Constraint dessen Icon an der Screen-Position liegt"""
        if not hasattr(self, 'constraint_icon_rects'):
            return None
        for constraint, rect in self.constraint_icon_rects:
            if rect.contains(screen_pos):
                return constraint
        return None

    def _find_entity_at(self, pos):
        """
        Optimized hit-testing using Spatial Index (Quadtree).
        Complexity: O(log n)
        """
        # 1. Update Index if needed
        if self.index_dirty:
            self._rebuild_spatial_index()

        r_screen = self.snap_radius
        r_world = r_screen / self.view_scale
        
        # 2. Define Query Area (in World Coordinates)
        query_rect = QRectF(pos.x() - r_world, pos.y() - r_world, 
                            r_world * 2, r_world * 2)

        candidates = []
        
        # 3. Broad Phase: Get candidates from Quadtree
        if self.spatial_index:
            candidates = self.spatial_index.query(query_rect)
            # Add points separately or ensure they are in tree? 
            # Currently standalone points are not in tree in my snippet above, 
            # let's assume they are few or add them to tree if needed.
            # For now, we fallback to linear search for points if they are critical,
            # or add points to the tree in _rebuild.
        else:
            # Fallback if tree failed
            candidates = self.sketch.lines + self.sketch.circles + self.sketch.arcs + self.sketch.splines

        # 4. Narrow Phase: Exact Distance Check
        best_entity = None
        best_dist = r_world # Start with max allowed distance
        
        # Helper for Spline distance (computationally expensive, so strictly filter first)
        def check_spline(spline):
            # ... existing spline check logic from your code ...
            # Reuse logic from original _find_spline_at
            pts = spline.get_curve_points(segments_per_span=10)
            local_min = self._safe_float('inf')
            px, py = pos.x(), pos.y()
            for i in range(len(pts) - 1):
                x1, y1 = pts[i]
                x2, y2 = pts[i + 1]
                line_len = math.hypot(x2 - x1, y2 - y1)
                if line_len < 1e-9: continue
                t = max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / (line_len**2)))
                dist = math.hypot(px - (x1 + t * (x2 - x1)), py - (y1 + t * (y2 - y1)))
                if dist < local_min: local_min = dist
            return local_min

        for entity in candidates:
            dist = self._safe_float('inf')
            
            # Type-based distance check
            # We assume your entity classes have .distance_to_point or similar logic
            if hasattr(entity, 'start') and hasattr(entity, 'end'): # Line
                # Using sketcher's distance logic
                from sketcher import Point2D
                dist = entity.distance_to_point(Point2D(pos.x(), pos.y()))
            
            elif hasattr(entity, 'center') and hasattr(entity, 'radius'): # Circle/Arc
                center_dist = math.hypot(entity.center.x - pos.x(), entity.center.y - pos.y())
                dist = abs(center_dist - entity.radius)
                
                # Special check for Arcs (angle limit)
                if hasattr(entity, 'start_angle'): # It's an Arc
                    if dist < best_dist: # Only do angle math if close enough to ring
                        angle = math.degrees(math.atan2(pos.y() - entity.center.y, pos.x() - entity.center.x))
                        angle = angle % 360
                        s = entity.start_angle % 360
                        e = entity.end_angle % 360
                        # Check if angle is within sweep
                        in_arc = (s <= e and s <= angle <= e) or (s > e and (angle >= s or angle <= e))
                        if not in_arc: dist = self._safe_float('inf')

            elif hasattr(entity, 'control_points'): # Spline
                dist = check_spline(entity)

            # 5. Winner Check
            if dist < best_dist:
                best_dist = dist
                best_entity = entity

        # 6. Standalone Points (usually few, ok to check linearly or add to tree)
        # Re-using logic from original code for points
        used_point_ids = self._get_used_point_ids()
        for point in self.sketch.points:
             if point.id not in used_point_ids:
                 d = math.hypot(point.x - pos.x(), point.y - pos.y())
                 if d < best_dist:
                     best_dist = d
                     best_entity = point

        return best_entity
    
    def _find_line_at(self, pos):
        r = self.snap_radius / self.view_scale
        pt = Point2D(pos.x(), pos.y())
        for line in self.sketch.lines:
            if line.distance_to_point(pt) < r: return line
        return None
    
    def _find_circle_at(self, pos):
        r = self.snap_radius / self.view_scale
        for c in self.sketch.circles:
            dist = abs(math.hypot(c.center.x - pos.x(), c.center.y - pos.y()) - c.radius)
            if dist < r: return c
        return None
    
    def _find_arc_at(self, pos):
        """Findet einen Bogen an der Position"""
        r = self.snap_radius / self.view_scale
        px, py = pos.x(), pos.y()
        
        for arc in self.sketch.arcs:
            # 1. Distanz zum Radius prüfen
            dist_to_center = math.hypot(arc.center.x - pos.x(), arc.center.y - pos.y())
            if abs(dist_to_center - arc.radius) < r:
                # 2. Winkel prüfen
                angle = math.degrees(math.atan2(pos.y() - arc.center.y, pos.x() - arc.center.x))
                if angle < 0: angle += 360
                
                start = arc.start_angle % 360
                end = arc.end_angle % 360
                
                # Normalisierung für den Fall, dass Start > End (über 0° Grenze)
                is_within = False
                if start <= end:
                    is_within = start <= angle <= end
                else:
                    is_within = angle >= start or angle <= end
                
                if is_within:
                    return arc
                    
        return None
    
    def _find_spline_element_at(self, pos):
        """
        Findet Spline-Elemente (Kontrollpunkt oder Handle) an der Position.
        
        Returns:
            Tuple (spline, cp_index, element_type) oder None
            element_type: 'point', 'handle_in', 'handle_out'
        """
        r = self.snap_radius / self.view_scale
        px, py = pos.x(), pos.y()
        
        for spline in self.sketch.splines:
            for i, cp in enumerate(spline.control_points):
                # Kontrollpunkt prüfen
                dist = math.hypot(cp.point.x - px, cp.point.y - py)
                if dist < r:
                    return (spline, i, 'point')
                
                # Eingehender Handle prüfen (nur wenn nicht erster Punkt oder closed)
                if i > 0 or spline.closed:
                    h_in = cp.handle_in_abs
                    dist_in = math.hypot(h_in[0] - px, h_in[1] - py)
                    if dist_in < r:
                        return (spline, i, 'handle_in')
                
                # Ausgehender Handle prüfen (nur wenn nicht letzter Punkt oder closed)
                if i < len(spline.control_points) - 1 or spline.closed:
                    h_out = cp.handle_out_abs
                    dist_out = math.hypot(h_out[0] - px, h_out[1] - py)
                    if dist_out < r:
                        return (spline, i, 'handle_out')
        
        return None
    
    def _find_spline_at(self, pos):
        """Findet eine Spline-Kurve an der Position"""
        r = self.snap_radius / self.view_scale
        px, py = pos.x(), pos.y()
        
        for spline in self.sketch.splines:
            # Prüfe Abstand zu den Kurvenpunkten
            pts = spline.get_curve_points(segments_per_span=10)
            for i in range(len(pts) - 1):
                x1, y1 = pts[i]
                x2, y2 = pts[i + 1]
                # Punkt-Linien-Abstand
                line_len = math.hypot(x2 - x1, y2 - y1)
                if line_len < 0.001:
                    continue
                t = max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / (line_len * line_len)))
                closest_x = x1 + t * (x2 - x1)
                closest_y = y1 + t * (y2 - y1)
                dist = math.hypot(px - closest_x, py - closest_y)
                if dist < r:
                    return spline
        
        return None
    
    def _find_face_at(self, pos):
        """Findet die Fläche unter dem Cursor (Point-in-Polygon Test)"""
        px, py = pos.x(), pos.y()
        
        for profile_data in self.closed_profiles:
            if not isinstance(profile_data, tuple) or len(profile_data) != 2:
                continue
            
            profile_type, data = profile_data
            
            if profile_type == 'circle':
                # Kreis: Prüfe ob Punkt innerhalb
                circle = data
                dist = math.hypot(px - circle.center.x, py - circle.center.y)
                if dist <= circle.radius:
                    return profile_data
                    
            elif profile_type == 'lines':
                # Linien-Polygon: Ray-Casting Algorithmus
                lines = data
                if len(lines) < 3:
                    continue
                
                # Sammle Vertices des Polygons
                vertices = []
                for line in lines:
                    vertices.append((line.start.x, line.start.y))
                
                if self._point_in_polygon(px, py, vertices):
                    return profile_data
            
            elif profile_type == 'polygon':
                # Shapely Polygon: Nutze Shapely's contains
                from shapely.geometry import Point as ShapelyPoint
                point = ShapelyPoint(px, py)
                if data.contains(point):
                    return profile_data
        
        return None
    
    def _point_in_polygon(self, px, py, vertices):
        """Ray-Casting Algorithmus für Point-in-Polygon Test"""
        n = len(vertices)
        inside = False
        
        j = n - 1
        for i in range(n):
            xi, yi = vertices[i]
            xj, yj = vertices[j]
            
            if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        
        return inside
    
    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background: #2d2d30; color: #ddd; border: 1px solid #3f3f46; }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background: #094771; }
            QMenu::separator { background: #3f3f46; height: 1px; margin: 4px 8px; }
        """)

        has_selection = self.selected_lines or self.selected_circles or self.selected_arcs

        # === Constraint-Optionen ===
        if self.selected_lines:
            menu.addAction("Horizontal (H)", lambda: self._apply_constraint('horizontal'))
            menu.addAction("Vertikal (V)", lambda: self._apply_constraint('vertical'))
            if len(self.selected_lines) >= 2:
                menu.addAction("Parallel (P)", lambda: self._apply_constraint('parallel'))
                menu.addAction("Senkrecht", lambda: self._apply_constraint('perpendicular'))
                menu.addAction("Gleiche Länge (E)", lambda: self._apply_constraint('equal'))
            menu.addSeparator()

        if len(self.selected_circles) >= 2:
            menu.addAction("Konzentrisch", lambda: self._apply_constraint('concentric'))
            menu.addAction("Gleicher Radius", lambda: self._apply_constraint('equal_radius'))
            menu.addSeparator()

        # === Constraint-Verwaltung ===
        if has_selection:
            # Constraints der Auswahl sammeln
            selection_constraints = self._get_constraints_for_selection()
            if selection_constraints:
                constraint_menu = menu.addMenu(f"⚙ Constraints ({len(selection_constraints)})")
                constraint_menu.addAction(
                    f"Constraints der Auswahl löschen ({len(selection_constraints)})",
                    lambda: self._delete_constraints_of_selection()
                )
            menu.addSeparator()

        # Globale Constraint-Verwaltung
        if self.sketch.constraints:
            menu.addAction(
                f"Alle Constraints löschen ({len(self.sketch.constraints)})",
                self._delete_all_constraints
            )
            menu.addSeparator()

        # === Standard-Aktionen ===
        if has_selection:
            menu.addAction("Löschen (Del)", self._delete_selected)
            menu.addSeparator()

        menu.addAction("Alles auswählen (Ctrl+A)", self._select_all)
        menu.addAction("Ansicht einpassen (F)", self._fit_view)
        menu.exec(self.mapToGlobal(pos.toPoint()))

    def _get_constraints_for_selection(self):
        """Sammelt alle Constraints die zur aktuellen Auswahl gehören"""
        selected_entities = set()
        for line in self.selected_lines:
            selected_entities.add(id(line))
        for circle in self.selected_circles:
            selected_entities.add(id(circle))
        for arc in self.selected_arcs:
            selected_entities.add(id(arc))

        matching = []
        for c in self.sketch.constraints:
            for entity in c.entities:
                if id(entity) in selected_entities:
                    if c not in matching:
                        matching.append(c)
                    break
        return matching

    def _delete_constraints_of_selection(self):
        """Löscht alle Constraints der aktuell ausgewählten Elemente"""
        constraints_to_delete = self._get_constraints_for_selection()
        if not constraints_to_delete:
            self.show_message("Keine Constraints zu löschen", 2000, QColor(255, 200, 100))
            return

        self._save_undo()
        count = len(constraints_to_delete)
        for c in constraints_to_delete:
            if c in self.sketch.constraints:
                self.sketch.constraints.remove(c)

        self.sketch.solve()
        self.sketched_changed.emit()
        self.show_message(f"{count} Constraint(s) gelöscht", 2000, QColor(100, 255, 100))
        logger.info(f"Deleted {count} constraints from selection")
        self.update()

    def _delete_all_constraints(self):
        """Löscht alle Constraints im Sketch"""
        if not self.sketch.constraints:
            self.show_message("Keine Constraints vorhanden", 2000, QColor(255, 200, 100))
            return

        self._save_undo()
        count = len(self.sketch.constraints)
        self.sketch.constraints.clear()
        self.sketched_changed.emit()
        self.show_message(f"Alle {count} Constraints gelöscht", 2000, QColor(100, 255, 100))
        logger.info(f"Deleted all {count} constraints")
        self.update()
    
    def _fit_view(self):
        if not self.sketch.lines and not self.sketch.circles:
            self._center_view(); return
        minx = miny = self._safe_float('inf')
        maxx = maxy = self._safe_float('-inf')
        for l in self.sketch.lines:
            for p in [l.start, l.end]:
                minx, maxx = min(minx, p.x), max(maxx, p.x)
                miny, maxy = min(miny, p.y), max(maxy, p.y)
        for c in self.sketch.circles:
            minx = min(minx, c.center.x - c.radius)
            maxx = max(maxx, c.center.x + c.radius)
            miny = min(miny, c.center.y - c.radius)
            maxy = max(maxy, c.center.y + c.radius)
        if minx == self._safe_float('inf'): return
        pad = 60
        w, h = max(maxx-minx, 1), max(maxy-miny, 1)
        self.view_scale = min((self.width()-2*pad)/w, (self.height()-2*pad)/h)
        cx, cy = (minx+maxx)/2, (miny+maxy)/2
        self.view_offset = QPointF(self.width()/2 - cx*self.view_scale, self.height()/2 + cy*self.view_scale)
        self.update()
    
    def paintEvent(self, event):
        # 1. QPainter initialisieren
        p = QPainter(self)
        
        # WICHTIG: Clipping setzen, damit Qt nicht außerhalb des "Dirty Rects" malt.
        # Das spart GPU-Arbeit.
        p.setClipRect(event.rect())
        
        # Antialiasing für schöne Linien
        p.setRenderHint(QPainter.Antialiasing)
        
        # 2. Hintergrund füllen (Schneller als drawRect)
        p.fillRect(event.rect(), DesignTokens.COLOR_BG_CANVAS)
        
        # 3. Update-Rect für Culling vorbereiten
        # Wir nehmen das Event-Rect (den Bereich, der neu gezeichnet werden muss)
        # und machen es etwas größer (Padding).
        # Warum? Damit dicke Linien oder Kreise am Rand nicht "abgehackt" wirken,
        # wenn der Renderer entscheidet, sie seien knapp draußen.
        update_rect = QRectF(event.rect()).adjusted(-20, -20, 20, 20)
        
        # 4. Zeichen-Methoden aufrufen
        # Da wir update_rect übergeben, berechnet der Renderer intern:
        # "Liegt diese Linie innerhalb von update_rect?" -> Wenn nein, Skip.
        
        self._draw_grid(p, update_rect)
        self._draw_body_references(p)   # Falls vorhanden (projizierte 3D-Kanten)
        self._draw_profiles(p, update_rect)
        self._draw_axes(p)
        
        # Hier passiert die Magie der Performance-Optimierung:
        self._draw_geometry(p, update_rect)
        
        # UI-Elemente (Constraints, Snaps etc.) zeichnen
        self._draw_constraints(p) 
        self._draw_open_ends(p)
        self._draw_preview(p)
        self._draw_selection_box(p)
        self._draw_snap(p)
        self._draw_live_dimensions(p)
        self._draw_hud(p)
        
        p.end()
    
    def _on_dim_choice_changed(self, key, value):
        """Reagiert auf Dropdown-Auswahl im Dialog"""
        if key == "operation":
            self.extrude_operation = value

    def start_extrude_dialog(self):
        """Startet den Extrude-Dialog"""
        if not self.viewport:
            self.status_message.emit("Fehler: Kein Viewport verbunden!")
            return

        if not self.closed_profiles:
            self.status_message.emit("Keine geschlossenen Profile gefunden!")
            return
            
        self.viewport.set_extrude_mode(True)
        
        fields = [
            ("H", "height", 10.0, "mm"),
            ("Op", "operation", 0, ["New Body", "Join", "Cut"])
        ]
        
        self.dim_input.setup(fields)
        from PySide6.QtGui import QCursor
        pos = self.mapFromGlobal(QCursor.pos())
        self.dim_input.move(pos.x() + 20, pos.y() + 20)
        self.dim_input.show()
        self.dim_input.focus_field(0)
        self.dim_input_active = True
        self.status_message.emit("Extrude: Flächen wählen | Tab=Optionen | Enter=Anwenden")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.view_offset == QPointF(0, 0):
            self._center_view()

