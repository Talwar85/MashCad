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


def format_zoom_label(view_scale: float) -> str:
    """W32: Single source of truth for zoom label formatting.
    Used by sketch overlay HUD and status bar badge."""
    if view_scale == int(view_scale):
        return f"{int(view_scale)}x"
    return f"{view_scale:.1f}x"
from typing import Optional, List, Tuple, Set
import inspect
import math
import time
import sys
import os
import numpy as np
from loguru import logger
from config.tolerances import Tolerances  # Phase 5: Zentralisierte Toleranzen
from config.feature_flags import is_enabled  # Nur für sketch_input_logging Debug-Flag

try:
    from gui.design_tokens import DesignTokens
except ImportError:
    from design_tokens import DesignTokens

try:
    from gui.sketch_snapper import SmartSnapper
except ImportError:
    try:
        from sketch_snapper import SmartSnapper
        logger.success("SmartSnapper Module loaded.")
    except ImportError:
        logger.error("SmartSnapper not found. Snapping will be degraded.")
        SmartSnapper = None


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
from sketcher import Sketch, Point2D, Line2D, Circle2D, Arc2D, Ellipse2D, Polygon2D, Constraint, ConstraintType
try:
    from gui.sketch_feedback import format_solver_failure_message
except ImportError:
    try:
        from sketch_feedback import format_solver_failure_message
    except ImportError:
        from .sketch_feedback import format_solver_failure_message

# Phase 8: Sketch Input Logger
try:
    from gui.sketch_input_logger import sketch_logger
except ImportError:
    sketch_logger = None

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
    finished_signal = Signal(list, list, list, list)  # lines, circles, arcs, native_splines
    error_signal = Signal(str)
    progress_signal = Signal(str)

    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath

    def run(self):
        try:
            import ezdxf

            # ezdxf.path nur in neueren Versionen verfügbar
            try:
                import ezdxf.path
                HAS_EZDXF_PATH = True
            except ImportError:
                HAS_EZDXF_PATH = False
                logger.info("ezdxf.path nicht verfügbar - nutze Fallback für Splines")

            doc = ezdxf.readfile(self.filepath)
            msp = doc.modelspace()

            new_lines = []
            new_circles = []
            new_arcs = []  # (cx, cy, radius, start_angle, end_angle)
            new_native_splines = []  # Native B-Spline Daten: (control_points, knots, degree, weights)

            def flatten_spline_fallback(entity, matrix=None):
                """Fallback für Spline-Konvertierung ohne ezdxf.path"""
                try:
                    # Kontrollpunkte und Knoten holen
                    ctrl_pts = list(entity.control_points)
                    if len(ctrl_pts) < 2:
                        return []

                    degree = entity.dxf.degree
                    knots = list(entity.knots) if hasattr(entity, 'knots') else []

                    # B-Spline korrekt evaluieren mit scipy
                    try:
                        from scipy import interpolate
                        import numpy as np

                        # Kontrollpunkte als Arrays
                        ctrl_x = np.array([p[0] for p in ctrl_pts])
                        ctrl_y = np.array([p[1] for p in ctrl_pts])

                        if knots and len(knots) == len(ctrl_pts) + degree + 1:
                            # Echte B-Spline Evaluation mit Knotenvektor
                            knots_arr = np.array(knots)

                            # Parameter-Bereich aus Knoten
                            t_min = knots_arr[degree]
                            t_max = knots_arr[-(degree + 1)]

                            # Evaluierungspunkte
                            n_points = max(100, len(ctrl_pts) * 3)
                            t_eval = np.linspace(t_min, t_max, n_points)

                            # BSpline für X und Y
                            try:
                                bspline_x = interpolate.BSpline(knots_arr, ctrl_x, degree)
                                bspline_y = interpolate.BSpline(knots_arr, ctrl_y, degree)
                                x_new = bspline_x(t_eval)
                                y_new = bspline_y(t_eval)
                                points = list(zip(x_new, y_new))
                            except Exception:
                                # BSpline fehlgeschlagen - Fallback auf Interpolation
                                points = None
                        else:
                            points = None

                        # Fallback: Interpolation durch Kontrollpunkte (weniger genau)
                        if points is None:
                            pts = np.array([(p[0], p[1]) for p in ctrl_pts])
                            t = np.linspace(0, 1, len(pts))
                            t_new = np.linspace(0, 1, max(100, len(pts) * 3))

                            k = min(3, degree, len(pts) - 1)
                            if k >= 1:
                                tck_x = interpolate.splrep(t, pts[:, 0], k=k, s=0)
                                tck_y = interpolate.splrep(t, pts[:, 1], k=k, s=0)
                                x_new = interpolate.splev(t_new, tck_x)
                                y_new = interpolate.splev(t_new, tck_y)
                                points = list(zip(x_new, y_new))
                            else:
                                points = [(p[0], p[1]) for p in ctrl_pts]

                    except ImportError:
                        # Ohne scipy: Kontrollpunkte als Polyline (ungenau aber besser als nichts)
                        points = [(p[0], p[1]) for p in ctrl_pts]

                    # Matrix anwenden
                    if matrix and points:
                        transformed = []
                        for px, py in points:
                            pt = matrix.transform(ezdxf.math.Vec3(px, py, 0))
                            transformed.append((pt.x, pt.y))
                        points = transformed

                    return points
                except Exception as e:
                    logger.debug(f"Spline fallback error: {e}")
                    return []

            def flatten_lwpolyline(entity, matrix=None):
                """LWPOLYLINE zu Punkten konvertieren"""
                try:
                    points = []
                    for pt in entity.get_points():
                        x, y = pt[0], pt[1]
                        if matrix:
                            transformed = matrix.transform(ezdxf.math.Vec3(x, y, 0))
                            x, y = transformed.x, transformed.y
                        points.append((x, y))

                    # Geschlossene Polyline?
                    if entity.closed and points:
                        points.append(points[0])

                    return points
                except Exception as e:
                    logger.debug(f"LWPOLYLINE error: {e}")
                    return []

            # === NATIVE SPLINE EXTRAKTION (NEU) ===
            def extract_native_spline(entity, matrix=None):
                """
                Extrahiert native B-Spline Daten für saubere Extrusion.

                Returns:
                    (control_points, knots, degree, weights) oder None bei Fehler
                """
                try:
                    ctrl_pts = list(entity.control_points)
                    if len(ctrl_pts) < 2:
                        return None

                    degree = entity.dxf.degree
                    knots = list(entity.knots) if hasattr(entity, 'knots') else []
                    weights = list(entity.weights) if hasattr(entity, 'weights') else []

                    # Matrix anwenden auf Kontrollpunkte
                    control_points = []
                    for p in ctrl_pts:
                        if matrix:
                            pt = matrix.transform(ezdxf.math.Vec3(p[0], p[1], 0))
                            control_points.append((pt.x, pt.y))
                        else:
                            control_points.append((p[0], p[1]))

                    logger.debug(f"Native Spline: {len(control_points)} ctrl pts, deg={degree}, {len(knots)} knots")
                    return (control_points, knots, degree, weights)

                except Exception as e:
                    logger.warning(f"Native Spline extraction failed: {e}")
                    return None

            # Helper: Konvertiert komplexe Formen in Linien (Fallback für Nicht-Splines)
            def add_path_as_lines(entity, matrix=None):
                points_2d = []

                # Methode 1: ezdxf.path (moderne Version)
                if HAS_EZDXF_PATH:
                    try:
                        p = ezdxf.path.make_path(entity)
                        if matrix:
                            p = p.transform(matrix)
                        raw_points = list(p.flattening(distance=0.01))
                        if raw_points:
                            points_2d = [(v.x, v.y) for v in raw_points]
                    except Exception as e:
                        logger.debug(f"ezdxf.path failed: {e}")

                # Methode 2: Fallback für Ältere Versionen
                if not points_2d:
                    dxftype = entity.dxftype()
                    if dxftype == 'SPLINE':
                        points_2d = flatten_spline_fallback(entity, matrix)
                    elif dxftype in ['LWPOLYLINE', 'POLYLINE']:
                        points_2d = flatten_lwpolyline(entity, matrix)
                    elif dxftype == 'ELLIPSE':
                        # Ellipse als Polygon approximieren
                        try:
                            cx, cy = entity.dxf.center.x, entity.dxf.center.y
                            # Vereinfachte Ellipsen-Approximation
                            points_2d = []
                            for i in range(64):
                                angle = 2 * math.pi * i / 64
                                # Vereinfacht: Nur für Kreise exakt
                                ratio = getattr(entity.dxf, 'ratio', 1.0)
                                major = entity.dxf.major_axis
                                px = cx + major.x * math.cos(angle) * ratio
                                py = cy + major.y * math.cos(angle) + major.x * math.sin(angle)
                                if matrix:
                                    pt = matrix.transform(ezdxf.math.Vec3(px, py, 0))
                                    px, py = pt.x, pt.y
                                points_2d.append((px, py))
                        except Exception:
                            pass

                if len(points_2d) < 2:
                    return

                # RDP-Vereinfachung - Balance zwischen Performance und QualitÄt
                if len(points_2d) > 500:
                    rdp_tolerance = 0.15  # 0.15mm für sehr komplexe Kurven
                elif len(points_2d) > 200:
                    rdp_tolerance = 0.05  # 0.05mm für komplexe Kurven
                elif len(points_2d) > 50:
                    rdp_tolerance = 0.02  # 0.02mm für mittlere Kurven
                else:
                    rdp_tolerance = 0.005  # 0.005mm für einfache Kurven

                simplified = ramer_douglas_peucker(points_2d, rdp_tolerance)
                logger.debug(f"RDP: {len(points_2d)} -> {len(simplified)} Punkte (tol={rdp_tolerance})")

                for k in range(len(simplified) - 1):
                    p1 = simplified[k]
                    p2 = simplified[k+1]
                    if math.hypot(p2[0]-p1[0], p2[1]-p1[1]) > 0.001:
                        new_lines.append((p1[0], p1[1], p2[0], p2[1]))

            def process_entity(entity, matrix=None):
                dxftype = entity.dxftype()
                
                # Blücke rekursiv auflüsen
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
                    start_angle_raw = entity.dxf.start_angle
                    end_angle_raw = entity.dxf.end_angle

                    if matrix:
                        c = matrix.transform(c)
                        # Skalierung für Radius
                        vec = matrix.transform_direction(ezdxf.math.Vec3(1, 0, 0))
                        r *= vec.magnitude
                        # Rotation für Winkel
                        rot_angle = math.degrees(math.atan2(vec.y, vec.x))
                        start_angle_raw += rot_angle
                        end_angle_raw += rot_angle

                    # Berechne Sweep BEVOR Normalisierung (wichtig für Vollkreise!)
                    sweep_raw = end_angle_raw - start_angle_raw
                    while sweep_raw < 0:
                        sweep_raw += 360
                    while sweep_raw > 360:
                        sweep_raw -= 360

                    # Vollkreis-Erkennung: Wenn Sweep ~360° ist, als CIRCLE importieren
                    if sweep_raw > 359.5 or sweep_raw < 0.5:
                        # Das ist ein Vollkreis als ARC definiert -> als Circle importieren
                        logger.debug(f"Vollkreis-Arc erkannt: center=({c.x:.2f}, {c.y:.2f}), r={r:.2f}")
                        new_circles.append((c.x, c.y, r))
                    else:
                        # Echter Arc (Teilkreis)
                        start_angle = start_angle_raw % 360
                        end_angle = end_angle_raw % 360
                        new_arcs.append((c.x, c.y, r, start_angle, end_angle))
                        logger.debug(f"Arc: center=({c.x:.2f}, {c.y:.2f}), r={r:.2f}, {start_angle:.1f}° -> {end_angle:.1f}° (sweep={sweep_raw:.1f}°)")

                # SPLINES -> Hybrid-Ansatz: Native für einfache, Polyline für komplexe
                elif dxftype == 'SPLINE':
                    # Schwellenwert: Komplexe Splines (viele Kontrollpunkte) als Polyline
                    NATIVE_SPLINE_THRESHOLD = 20  # Erhüht auf 20 für bessere Erkennung kleiner Splines

                    try:
                        ctrl_pts = list(entity.control_points)
                        n_ctrl = len(ctrl_pts)
                    except Exception as e:
                        logger.debug(f"Spline ctrl_pts Zugriff fehlgeschlagen: {e}")
                        n_ctrl = 999  # Force polyline fallback on error

                    # Prüfe ob Spline geschlossen ist (für Schraubenlücher etc.)
                    is_closed_spline = False
                    try:
                        # Evaluiere Start/End des Splines
                        from scipy import interpolate as sp_interp
                        import numpy as np
                        knots = list(entity.knots) if hasattr(entity, 'knots') else []
                        degree = entity.dxf.degree
                        if knots and len(knots) == n_ctrl + degree + 1:
                            ctrl_x = np.array([p[0] for p in ctrl_pts])
                            ctrl_y = np.array([p[1] for p in ctrl_pts])
                            knots_arr = np.array(knots)
                            t_min = knots_arr[degree]
                            t_max = knots_arr[-(degree + 1)]
                            bspline_x = sp_interp.BSpline(knots_arr, ctrl_x, degree)
                            bspline_y = sp_interp.BSpline(knots_arr, ctrl_y, degree)
                            start_pt = (float(bspline_x(t_min)), float(bspline_y(t_min)))
                            end_pt = (float(bspline_x(t_max)), float(bspline_y(t_max)))
                            gap = math.hypot(end_pt[0] - start_pt[0], end_pt[1] - start_pt[1])
                            is_closed_spline = gap < 0.5  # < 0.5mm = geschlossen
                    except Exception as e:
                        logger.debug(f"Closed-Spline Erkennung fehlgeschlagen: {e}")

                    logger.debug(f"SPLINE: {n_ctrl} ctrl pts, closed={is_closed_spline}")

                    # Kleine geschlossene Splines (Schraubenlücher) -> Als Kreis/Polygon
                    if is_closed_spline and n_ctrl <= 30:
                        # Evaluiere und erstelle Polygon direkt
                        try:
                            pts_2d = flatten_spline_fallback(entity, matrix)
                            if pts_2d and len(pts_2d) >= 3:
                                # Als geschlossene Form zu circles hinzufügen
                                # Berechne Bounding Box für Radius-SchÄtzung
                                xs = [p[0] for p in pts_2d]
                                ys = [p[1] for p in pts_2d]
                                cx = sum(xs) / len(xs)
                                cy = sum(ys) / len(ys)
                                r_approx = max(max(xs) - min(xs), max(ys) - min(ys)) / 2
                                new_circles.append((cx, cy, r_approx))
                                logger.info(f"Geschlossener Spline als Kreis: center=({cx:.2f}, {cy:.2f}), r≈{r_approx:.2f}")
                        except Exception as e:
                            logger.debug(f"Closed spline as circle failed: {e}")
                            add_path_as_lines(entity, matrix)

                    elif n_ctrl > NATIVE_SPLINE_THRESHOLD:
                        # Komplexer Spline -> Polyline-Methode
                        logger.info(f"Komplexer Spline ({n_ctrl} Kontrollpunkte) -> Polyline-Import")
                        lines_before = len(new_lines)
                        add_path_as_lines(entity, matrix)
                        lines_added = len(new_lines) - lines_before
                        logger.debug(f"  -> {lines_added} Liniensegmente erzeugt")
                    else:
                        # Einfacher offener Spline -> Native versuchen
                        spline_data = extract_native_spline(entity, matrix)
                        if spline_data:
                            new_native_splines.append(spline_data)
                            logger.info(f"Native Spline importiert: {len(spline_data[0])} Kontrollpunkte")
                        else:
                            logger.warning("Spline Fallback: Konvertiere zu Linien")
                            add_path_as_lines(entity, matrix)

                # Polylines, Ellipsen -> High-Res Fitting (weiterhin als Linien)
                elif dxftype in ['LWPOLYLINE', 'POLYLINE', 'ELLIPSE']:
                    add_path_as_lines(entity, matrix)

                # HATCH (Schraffuren) - Boundary-Pfade extrahieren
                elif dxftype == 'HATCH':
                    try:
                        for boundary in entity.paths:
                            # Boundary-Pfad in Linien konvertieren
                            if hasattr(boundary, 'vertices'):
                                verts = list(boundary.vertices)
                                for k in range(len(verts)):
                                    p1 = verts[k]
                                    p2 = verts[(k + 1) % len(verts)]
                                    x1, y1 = p1[:2]
                                    x2, y2 = p2[:2]
                                    if matrix:
                                        pt1 = matrix.transform(ezdxf.math.Vec3(x1, y1, 0))
                                        pt2 = matrix.transform(ezdxf.math.Vec3(x2, y2, 0))
                                        x1, y1 = pt1.x, pt1.y
                                        x2, y2 = pt2.x, pt2.y
                                    if math.hypot(x2-x1, y2-y1) > 0.001:
                                        new_lines.append((x1, y1, x2, y2))
                    except Exception as he:
                        logger.debug(f"HATCH boundary extraction: {he}")

                # POINT - als sehr kleiner Kreis (Marker)
                elif dxftype == 'POINT':
                    try:
                        loc = entity.dxf.location
                        if matrix:
                            loc = matrix.transform(loc)
                        # Punkt als kleinen Kreis darstellen (0.5mm Radius)
                        new_circles.append((loc.x, loc.y, 0.5))
                    except Exception:
                        pass

                # SOLID/3DFACE - als Linien um die Ecken
                elif dxftype in ['SOLID', '3DFACE']:
                    try:
                        pts = []
                        for attr in ['vtx0', 'vtx1', 'vtx2', 'vtx3']:
                            if hasattr(entity.dxf, attr):
                                pt = getattr(entity.dxf, attr)
                                if matrix:
                                    pt = matrix.transform(pt)
                                pts.append((pt.x, pt.y))
                        # Linien zwischen Punkten
                        for k in range(len(pts)):
                            p1 = pts[k]
                            p2 = pts[(k + 1) % len(pts)]
                            if math.hypot(p2[0]-p1[0], p2[1]-p1[1]) > 0.001:
                                new_lines.append((p1[0], p1[1], p2[0], p2[1]))
                    except Exception:
                        pass

                # TEXT/MTEXT - ignorieren (keine Geometrie)
                elif dxftype in ['TEXT', 'MTEXT', 'ATTRIB', 'ATTDEF']:
                    pass  # Text wird übersprungen

                # DIMENSION - ignorieren (Bemaüƒungen)
                elif dxftype in ['DIMENSION', 'LEADER', 'TOLERANCE']:
                    pass  # Bemaüƒungen überspringen

                # Fallback: Versuche path.make_path für unbekannte Typen
                else:
                    try:
                        add_path_as_lines(entity, matrix)
                    except Exception:
                        logger.debug(f"DXF Entity '{dxftype}' übersprungen")

            # Start
            all_ents = list(msp)
            total = len(all_ents)
            skipped_types = set()
            for i, e in enumerate(all_ents):
                process_entity(e)
                if i % 20 == 0:
                    self.progress_signal.emit(f"Importiere... {int(i/total*100)}%")

            if skipped_types:
                logger.info(f"DXF: ü£bersprungene Entity-Typen: {skipped_types}")

            self.finished_signal.emit(new_lines, new_circles, new_arcs, new_native_splines)

        except Exception as e:
            self.error_signal.emit(str(e))
            
            
class SketchEditor(QWidget, SketchHandlersMixin, SketchRendererMixin):
    """Professioneller 2D-Sketch-Editor"""
    
    sketched_changed = Signal()
    tool_changed = Signal(SketchTool)
    status_message = Signal(str)
    construction_mode_changed = Signal(bool)
    grid_snap_mode_changed = Signal(bool)
    exit_requested = Signal()  # Escape Level 4: Sketch verlassen
    solver_finished_signal = Signal(bool, str, float, str) # success, message, dof, status
    zoom_changed = Signal(float)  # W32: Emits view_scale for live status bar update
    peek_3d_requested = Signal(bool)  # True = zeige 3D, False = zurück zu Sketch
    
    # W26 FIX: Echter Projection-Preview-Hook
    # Signal wird emittiert wenn User im PROJECT-Tool über einer Kante hovered
    projection_preview_requested = Signal(object, str)  # (edge_tuple, projection_type)
    projection_preview_cleared = Signal()

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
    SELECTION_FILTER_ORDER = ("all", "line", "circle", "arc", "spline", "point")
    SELECTION_FILTER_LABELS = {
        "all": "All",
        "line": "Lines",
        "circle": "Circles",
        "arc": "Arcs",
        "spline": "Splines",
        "point": "Points",
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(600, 400)
        
        self.setFocusPolicy(Qt.StrongFocus)
        
        self._solver_lock = threading.Lock()
        self.solver_finished_signal.connect(self._on_solver_finished)
        self._is_solving = False
        self._last_solver_feedback_ms = 0.0
        self._last_solver_feedback_text = ""
        self.last_snap_diagnostic = ""
        self.last_snap_confidence = 0.0
        self.last_snap_priority = 0
        self.last_snap_distance = 0.0
        self._last_snap_feedback_ms = 0.0
        self._last_snap_feedback_text = ""

        self.sketch = Sketch("Sketch1")
        self.view_offset = QPointF(0, 0)
        self.view_scale = 5.0
        self.grid_size = 1.0
        self.grid_snap = True
        self.snap_enabled = True
        self.snap_radius = Tolerances.SKETCH_SNAP_RADIUS_PX  # Konfigurierbarer Fangradius
        self.performance_mode = True
        
        # ... Snapper initialisieren ...
        if SmartSnapper:
            self.snapper = SmartSnapper(self)
        else:
            self.snapper = None

        self.current_tool = SketchTool.SELECT
        self._tool_step = 0  # Private backing field for tool_step property
        self._last_auto_show_step = -1  # Prevent multiple auto-shows for same step
        self.tool_points = []
        self.tool_data = {}
        
        self.selected_lines = []
        self.selected_circles = []
        self.selected_arcs = []
        self.selected_ellipses = []
        self.selected_polygons = []
        self.selected_points = []  # Standalone Punkte
        self.selected_constraints = []  # Für Constraint-Selektion
        self.hovered_entity = None
        self._last_hovered_entity = None
        self.selection_filter_mode = "all"
        self._overlap_cycle_candidates = []
        self._overlap_cycle_signature = ()
        self._overlap_cycle_index = 0
        self._overlap_cycle_anchor_screen = QPointF(-1.0, -1.0)
        self._overlap_cycle_anchor_world = QPointF()
        self._overlap_cycle_anchor_radius_px = 10.0
        self._last_non_select_tool = SketchTool.LINE

        # Constraint Selection Highlighting (für 2-Entity Constraints)
        self._constraint_highlighted_entity = None
        self._constraint_highlight_color = QColor(0, 255, 255)  # Cyan

        # Editing State für Dimension-Input statt QInputDialog
        self.editing_entity = None  # Objekt das gerade bearbeitet wird (Line, Circle, Constraint)
        self.editing_mode = None    # "length", "radius", "angle", "dimension" etc.

        # HUD-Nachrichten System
        self._hud_message = ""
        self._hud_message_time = 0
        self._hud_duration = 3000
        self._hud_color = QColor(255, 255, 255)

        # W10 Paket C: Discoverability v4 Anti-Spam - Hint-Tracking
        self._hint_history = []  # Liste von (text, timestamp_ms) Tupeln
        self._hint_cooldown_ms = 5000  # Cooldown zwischen gleichen Hinweisen (5s)
        self._hint_max_history = 10  # Max Anzahl gespeicherter Hinweise
        
        # W16 Paket B: Discoverability v2 - Navigation und Tutorial-Modus
        self._peek_3d_active = False  # True wenn 3D-Peek aktiv (Space gehalten)
        self._tutorial_mode_enabled = False  # Tutorial-Modus für neue Nutzer
        self._tutorial_mode = self._tutorial_mode_enabled  # API-Alias für W17 Tests
        self._hint_priority_levels = {
            'CRITICAL': 3,   # Errors, Blockierende Hinweise
            'WARNING': 2,    # Wichtige Warnungen
            'INFO': 1,       # Normale Hinweise
            'TUTORIAL': 0,   # Tutorial-Hinweise (niedrigste PrioritÄt)
        }
        self._current_hint_priority = 0  # Aktuelle angezeigte PrioritÄt
        self._hint_context = 'sketch'  # 'sketch', 'peek_3d', 'direct_edit'
        
        self.selection_box_start = None
        self.selection_box_end = None
        self.current_snap = None
        self.preview_geometry = []
        
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
        # Phase 8: Connect new signals
        if hasattr(self.dim_input, 'field_committed'):
            self.dim_input.field_committed.connect(self._on_dim_field_committed)
        if hasattr(self.dim_input, 'field_reset'):
            self.dim_input.field_reset.connect(self._on_dim_field_reset)
        # Phase 8: Per-field enter mode (Enter bestÄtigt nur aktuelles Feld)
        if hasattr(self.dim_input, 'set_per_field_enter'):
            self.dim_input.set_per_field_enter(True)
        self.dim_input_active = False
        self.viewport = None

        # Canvas / Bildreferenz (CAD-Style)
        self.canvas_image = None        # QPixmap
        self.canvas_world_rect = None   # QRectF in Weltkoordinaten
        self.canvas_opacity = 0.4
        self.canvas_visible = True
        self.canvas_locked = False
        self.canvas_file_path = None
        self._canvas_dragging = False
        self._canvas_drag_offset = QPointF(0, 0)
        self._canvas_calibrating = False
        self._canvas_calib_points = []  # [(screen_x, screen_y), ...]

        self.live_length = 0.0
        self.live_angle = 0.0
        self.live_width = 0.0
        self.live_height = 0.0
        self.live_radius = 0.0
        self.live_dx = 0.0  # Für Modify-Tools (MOVE, COPY)
        self.live_dy = 0.0  # Für Modify-Tools (MOVE, COPY)
        
        self.polygon_sides = 6
        self.rect_mode = 0  # 0=2-Punkt, 1=Center (wie Fusion360)
        self.circle_mode = 0  # 0=Center-Radius, 1=2-Punkt, 2=3-Punkt
        self.construction_mode = False
        self.fillet_radius = 5.0
        self.offset_distance = 5.0
        self.chamfer_distance = 5.0
        
        # W26: Projection-Preview State
        self._last_projection_edge = None  # Für Change-Detection
        self._projection_type = "edge"  # Default: "edge" | "silhouette" | "intersection" | "mesh_outline"
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
        self.selected_splines = []  # AusgewÄhlte Splines (Liste)
        self.hovered_spline_element = None  # (spline, cp_index, element_type)

        # Direct Manipulation (Fusion/Onshape-Ähnlich)
        # Kreis/Polygon: Center-Drag und Radius-Drag direkt im SELECT-Modus.
        self._direct_hover_handle = None
        self._direct_edit_dragging = False
        self._direct_edit_mode = None  # "center" | "radius"
        self._direct_edit_circle = None
        self._direct_edit_source = None  # "circle" | "polygon"
        self._direct_edit_start_pos = QPointF()
        self._direct_edit_start_center = QPointF()
        self._direct_edit_start_radius = 0.0
        self._direct_edit_anchor_angle = 0.0
        self._direct_edit_drag_moved = False
        self._direct_edit_radius_constraints = []
        self._direct_edit_line = None
        self._direct_edit_line_context = None
        self._direct_edit_line_length_constraints = []
        self._direct_edit_live_solve = False
        self._direct_edit_pending_solve = False
        self._direct_edit_last_live_solve_ts = 0.0
        self._direct_edit_live_solve_interval_s = 1.0 / 30.0
        # W20 P1: Arc Direct Edit State
        self._direct_edit_arc = None
        self._direct_edit_start_start_angle = 0.0
        self._direct_edit_start_end_angle = 0.0
        # W25: Ellipse/Polygon Direct Edit State
        self._direct_edit_ellipse = None
        self._direct_edit_start_radius_x = 0.0
        self._direct_edit_start_radius_y = 0.0
        self._direct_edit_start_rotation = 0.0
        self._direct_edit_polygon = None
        self._direct_edit_polygon_vertex_idx = -1
        self._direct_edit_polygon_vertex_start = QPointF()
        
        # Schwebende Optionen-Palette
        self.tool_options = ToolOptionsPopup(self)
        self.tool_options.option_selected.connect(self._on_tool_option_selected)
        
        # Body-Referenzen für transparente Anzeige im Hintergrund (Fusion360-Style)
        self.reference_bodies = []  # Liste von {'edges_2d': [...], 'color': (r,g,b)}
        self.show_body_reference = True  # Toggle für Anzeige
        self.body_reference_opacity = 0.25  # Transparenz der Bodies
        self.reference_clip_mode = "all"  # all | front | section
        self.reference_section_thickness = 1.0
        self.reference_depth_tol = 1e-3
        self.sketch_plane_normal = (0, 0, 1)  # Normale der Sketch-Ebene
        self.sketch_plane_origin = (0, 0, 0)  # Ursprung der Sketch-Ebene
        self.sketch_plane_x_dir = (1, 0, 0)  # X-Achse der Sketch-Ebene (3D)
        self.sketch_plane_y_dir = (0, 1, 0)  # Y-Achse der Sketch-Ebene (3D)
        self.projected_world_origin = (0, 0)  # Welt-Origin projiziert auf Sketch (2D)
        self.view_rotation = 0  # Ansicht-Rotation in Grad (0, 90, 180, 270)
        
        # --- SPATIAL INDEX OPTIMIZATION ---
        self.spatial_index = None
        self.index_dirty = True
        # Mark index dirty whenever sketch changes
        self.sketched_changed.connect(self._mark_index_dirty)
        self.hovered_ref_edge = None
        self.setStyleSheet(f"background-color: {DesignTokens.COLOR_BG_CANVAS.name()};")
        self.setMouseTracking(True)
        QTimer.singleShot(100, self._center_view)

        # Phase 4.4: Update-Debouncing für Performance
        self._update_pending = False
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(16)  # ~60 FPS max
        self._update_timer.timeout.connect(self._do_debounced_update)

    def request_update(self):
        """
        Phase 4.4: Debounced Update-Request.

        Problem: 30+ self.request_update() Aufrufe → Lag bei 100+ Constraints
        Lüsung: Sammle alle Requests, führe max 1 Update pro 16ms aus.
        """
        if not self._update_pending:
            self._update_pending = True
            self._update_timer.start()

    def _do_debounced_update(self):
        """Führt das tatsÄchliche Qt-Update aus."""
        self._update_pending = False
        super().update()  # Direkter Qt-Update (nicht request_update!)

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

    @staticmethod
    def _solver_status_name(result) -> str:
        status = getattr(result, "status", None)
        name = getattr(status, "name", "")
        if isinstance(name, str):
            return name
        if isinstance(status, str):
            return status
        return ""

    def _emit_solver_feedback(self, success: bool, message: str, dof: float = 0.0, status_name: str = "", context: str = "Solver", show_hud: bool = True):
        """
        Konsistentes UI-Feedback fuer Solver-Resultate.
        """
        if success:
            return

        import time

        text = format_solver_failure_message(status_name, message, dof=dof, context=context)
        self.status_message.emit(text)
        logger.warning(text)

        if not show_hud:
            return

        now_ms = time.time() * 1000.0
        repeated = text == self._last_solver_feedback_text and (now_ms - self._last_solver_feedback_ms) < 1200.0
        if not repeated:
            self._last_solver_feedback_ms = now_ms
            self._last_solver_feedback_text = text
            self.show_message(text, 4000, QColor(255, 90, 90))

    def _emit_snap_diagnostic_feedback(self, snap_type):
        """
        Show throttled, actionable diagnostics when snapping does not lock as expected.
        """
        drawing_tools = {
            SketchTool.LINE,
            SketchTool.RECTANGLE,
            SketchTool.RECTANGLE_CENTER,
            SketchTool.CIRCLE,
            SketchTool.ELLIPSE,
            SketchTool.CIRCLE_2POINT,
            SketchTool.CIRCLE_3POINT,
            SketchTool.POLYGON,
            SketchTool.ARC_3POINT,
            SketchTool.SLOT,
            SketchTool.SPLINE,
            SketchTool.POINT,
        }
        if self.current_tool not in drawing_tools:
            return
        if snap_type != SnapType.NONE:
            return
        text = (self.last_snap_diagnostic or "").strip()
        if not text:
            return

        import time

        now_ms = time.time() * 1000.0
        repeated = text == self._last_snap_feedback_text and (now_ms - self._last_snap_feedback_ms) < 1500.0
        if repeated:
            return

        self._last_snap_feedback_ms = now_ms
        self._last_snap_feedback_text = text
        if hasattr(self, "show_message"):
            self.show_message(text, 2200, QColor(255, 190, 90))
        else:
            self.status_message.emit(text)
    
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
                    dof = getattr(result, 'dof', None)
                    if dof is None:
                        try:
                            _, _, dof = self.sketch.calculate_dof()
                        except Exception:
                            dof = 0.0
                    status_name = self._solver_status_name(result)
                    
                    # Emit result to Main Thread
                    self.solver_finished_signal.emit(success, msg, self._safe_float(dof), status_name)
                except Exception as e:
                    logger.error(f"Solver Crash: {e}")
                    self.solver_finished_signal.emit(False, str(e), 0.0, "INCONSISTENT")
                finally:
                    self._is_solving = False

        # Start thread as daemon (dies if app closes)
        thread = Thread(target=run_solver, daemon=True)
        thread.start()

    def _on_solver_finished(self, success, message, dof, status_name):
        """
        Called when the background thread finishes. 
        Safe to update UI here.
        """
        if not success:
            # Do not spam HUD while user is actively dragging.
            is_live_interaction = self.is_panning or (QApplication.mouseButtons() != Qt.NoButton)
            self._emit_solver_feedback(
                success=False,
                message=message,
                dof=dof,
                status_name=status_name,
                context="Constraint solve",
                show_hud=not is_live_interaction,
            )
        
        # Recalculate profiles (Faces) based on new solved geometry
        self._find_closed_profiles()
        
        # Notify rest of the system
        self.sketched_changed.emit()
        
        # Trigger repaint of the new geometry state
        self.request_update()
        
        # Optional: Update status only if it was a discrete operation (not while dragging)
        if self.current_tool == SketchTool.SELECT and not self.is_panning:
             # Just logging to keep HUD clean during drag
             pass
            
    def _mark_index_dirty(self):
        self.index_dirty = True

    def _debug_inspect_geometry(self):
        """
        Forensische Suche: Findet Geometrie, die versehentlich Booleans statt Zahlen enthÄlt.
        """
        import numpy as np
        
        logger.info("­ƒòÁ´©Å Starte Geometrie-Inspektion...")
        
        found_error = False

        def is_bad(val, name):
            # Prüft auf bool (Python) oder numpy.bool_ (NumPy)
            if isinstance(val, (bool, np.bool_)):
                logger.critical(f"­ƒÜ¿ FEHLER GEFUNDEN in {name}!")
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
                err = check(l.start.x, f"L{i}.start.x")
                if err: problems.append(err)
                err = check(l.start.y, f"L{i}.start.y")
                if err: problems.append(err)
                err = check(l.end.x, f"L{i}.end.x")
                if err: problems.append(err)
                err = check(l.end.y, f"L{i}.end.y")
                if err: problems.append(err)

            return problems

        # 1. RUN AUDIT
        # If this logs errors, we know the source data is 'infected' with numpy types
        #problems = audit_geometry(self.sketch)
        #if problems:
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
            except Exception as e:
                logger.debug(f"Float-Konvertierung fehlgeschlagen: {e}")
                return 0.0

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
            # Optional: Feedback in Statuszeile, wenn per Klick geÄndert
            state = tr("ON") if self.construction_mode else tr("OFF")
            self.status_message.emit(tr("Construction: {state}").format(state=state))
            
        elif option == "grid_snap":
            self.grid_snap = self._safe_bool(value)

        elif option == "grid_size":
            self.grid_size = float(value)

        elif option == "snap_radius":
            self.snap_radius = int(value)
            state = f"{self.snap_radius} px"
            self.status_message.emit(tr("Snap Radius: {state}").format(state=state))

        elif option == "performance_mode":
            self.performance_mode = self._safe_bool(value)
            state = tr("ON") if self.performance_mode else tr("OFF")
            self.status_message.emit(tr("Performance mode: {state}").format(state=state))

        self.request_update()

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
            
        # Padding für StrichstÄrke (5px) + Glow (10px) = sicherheitshalber 15
        return rect.adjusted(-15, -15, 15, 15)

    def _get_circle_dirty_rect(self, cx: float, cy: float, radius: float) -> QRectF:
        """
        Screen-Dirty-Rect fuer Circle-Direct-Edit.
        Enthaelt Kreis, Selection-Glow, Handles und kleine Sicherheitsreserve.
        """
        center_screen = self.world_to_screen(QPointF(float(cx), float(cy)))
        r_screen = max(1.0, float(radius) * float(self.view_scale))
        rect = QRectF(
            center_screen.x() - r_screen,
            center_screen.y() - r_screen,
            2.0 * r_screen,
            2.0 * r_screen,
        )
        return rect.adjusted(-28.0, -28.0, 28.0, 28.0)

    # W28: Dirty-Rect Methoden für Arc, Ellipse, Polygon Direct-Manipulation
    def _get_arc_dirty_rect(self, arc) -> QRectF:
        """
        Screen-Dirty-Rect für Arc-Direct-Edit.
        Enthält Arc, Selection-Glow, Handles und Sicherheitsreserve.
        """
        from sketcher import Arc2D
        if not isinstance(arc, Arc2D):
            return QRectF()
        
        center_screen = self.world_to_screen(QPointF(float(arc.center.x), float(arc.center.y)))
        r_screen = max(1.0, float(arc.radius) * float(self.view_scale))
        rect = QRectF(
            center_screen.x() - r_screen,
            center_screen.y() - r_screen,
            2.0 * r_screen,
            2.0 * r_screen,
        )
        return rect.adjusted(-32.0, -32.0, 32.0, 32.0)

    def _get_ellipse_dirty_rect(self, ellipse) -> QRectF:
        """
        Screen-Dirty-Rect für Ellipse-Direct-Edit.
        Enthält Ellipse, Selection-Glow, Handles und Sicherheitsreserve.
        """
        center_screen = self.world_to_screen(QPointF(float(ellipse.center.x), float(ellipse.center.y)))
        rx = max(0.01, float(getattr(ellipse, "radius_x", 0.01)))
        ry = max(0.01, float(getattr(ellipse, "radius_y", 0.01)))
        rx_screen = max(1.0, rx * float(self.view_scale))
        ry_screen = max(1.0, ry * float(self.view_scale))
        rect = QRectF(
            center_screen.x() - rx_screen,
            center_screen.y() - ry_screen,
            2.0 * rx_screen,
            2.0 * ry_screen,
        )
        return rect.adjusted(-32.0, -32.0, 32.0, 32.0)

    def _get_polygon_dirty_rect(self, polygon) -> QRectF:
        """
        Screen-Dirty-Rect für Polygon-Direct-Edit.
        Enthält alle Vertices, Selection-Glow und Sicherheitsreserve.
        """
        points = getattr(polygon, "points", [])
        if not points:
            return QRectF()
        
        rect = QRectF()
        for pt in points:
            p_screen = self.world_to_screen(QPointF(float(pt.x), float(pt.y)))
            if rect.isEmpty():
                rect = QRectF(p_screen.x() - 10, p_screen.y() - 10, 20, 20)
            else:
                rect = rect.united(QRectF(p_screen.x() - 10, p_screen.y() - 10, 20, 20))
        return rect.adjusted(-28.0, -28.0, 28.0, 28.0)
    
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
            wx = self._safe_float(w.x())  # → Explizit zu Python float
            wy = self._safe_float(w.y())

        # Ansicht-Rotation anwenden (vor Scale/Translate)
        rot = self.view_rotation
        if rot == 90:
            wx, wy = wy, -wx
        elif rot == 180:
            wx, wy = -wx, -wy
        elif rot == 270:
            wx, wy = -wy, wx

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

        wx = (s.x() - ox) / self.view_scale
        wy = -(s.y() - oy) / self.view_scale

        # Inverse Ansicht-Rotation anwenden
        rot = self.view_rotation
        if rot == 90:
            wx, wy = -wy, wx
        elif rot == 180:
            wx, wy = -wx, -wy
        elif rot == 270:
            wx, wy = wy, -wx

        return QPointF(wx, wy)
    
    def _center_view(self):
        self.view_offset = QPointF(self.width() / 2, self.height() / 2)
        self.request_update()

    def rotate_view(self):
        """Rotiert die Sketch-Ansicht um 90° im Uhrzeigersinn."""
        self.view_rotation = (self.view_rotation + 90) % 360
        from loguru import logger
        logger.debug(f"[Sketch] View rotation: {self.view_rotation}°")
        self.request_update()

    def show_message(self, text: str, duration: int = 3000, color: QColor = None,
                    force: bool = False, priority: int = 0):
        """
        Zeigt eine HUD-Nachricht als zentralen Toast an.

        W10 Paket C: Erweitert um Anti-Spam Hint-Tracking.

        Args:
            text: Die anzuzeigende Nachricht
            duration: Anzeigedauer in ms (Standard: 3000)
            color: Textfarbe (Standard: weiüƒ)
            force: Wenn True, wird Cooldown ignoriert (für wichtige Hinweise)
            priority: Priority-Level (hüher = wichtiger, überschreibt niedrigere wÄhrend Cooldown)

        Returns:
            True wenn Nachricht angezeigt wurde, False wenn unterdrückt (Cooldown)
        """
        import time

        current_time_ms = time.time() * 1000

        # W10 Paket C: Hint-Tracking und Cooldown-Logik
        if not force:
            # Prüfen ob derselbe Hinweis kürzlich angezeigt wurde
            for hint_text, hint_time_ms in self._hint_history:
                if hint_text == text:
                    # Cooldown prüfen
                    time_since_last = current_time_ms - hint_time_ms
                    if time_since_last < self._hint_cooldown_ms:
                        # Hinweis ist noch im Cooldown - prüfe Priority
                        if priority <= 0:
                            # Niedrige Priority: Nicht anzeigen
                            return False
                        # Hohe Priority: Cooldown brechen

        # Hinweis anzeigen
        self._hud_message = text
        self._hud_message_time = current_time_ms
        self._hud_duration = duration
        self._hud_color = color if color else QColor(255, 255, 255)

        # Hint-Trackung aktualisieren
        # Alten Eintrag für denselben Text entfernen (um Duplikate zu vermeiden)
        self._hint_history = [(t, tm) for t, tm in self._hint_history if t != text]
        # Neuen Eintrag hinzufügen
        self._hint_history.append((text, current_time_ms))
        # History auf Max-LÄnge begrenzen
        if len(self._hint_history) > self._hint_max_history:
            self._hint_history = self._hint_history[-self._hint_max_history:]

        self.request_update()

        # Timer für Refresh wÄhrend Fade-out
        QTimer.singleShot(duration - 500, self.update)
        QTimer.singleShot(duration, self.update)

        return True

    # PAKET B W6: Alias für Konsistenz mit bestehendem Code
    _show_hud = show_message

    def set_reference_bodies(self, bodies_data, plane_normal=(0,0,1), plane_origin=(0,0,0), plane_x=None):
        self.reference_bodies = []
        self.sketch_plane_normal = plane_normal
        self.sketch_plane_origin = plane_origin

        import numpy as np

        # Alles in float64 casten für PrÄzision
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

        # NEU: Speichere Achsen für Orientierungs-Indikator
        self.sketch_plane_x_dir = tuple(u)
        self.sketch_plane_y_dir = tuple(v)

        # Berechne projizierten Welt-Origin auf die Sketch-Ebene
        # Welt-Origin (0,0,0) → projiziere auf Ebene
        world_origin = np.array([0.0, 0.0, 0.0])
        rel = world_origin - origin
        self.projected_world_origin = (float(np.dot(rel, u)), float(np.dot(rel, v)))

        from loguru import logger
        if is_enabled("sketch_debug"):
            logger.debug(f"[Orientation] Plane origin: {plane_origin}, normal: {plane_normal}")
            logger.debug(f"[Orientation] Plane X-dir: {self.sketch_plane_x_dir}, Y-dir: {self.sketch_plane_y_dir}")
            logger.debug(f"[Orientation] Projected world origin: {self.projected_world_origin}")

        if not bodies_data:
            self.request_update()
            return
        
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
                except Exception as e:
                    logger.debug(f"QColor-Parsing fehlgeschlagen für '{raw_color}': {e}")
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
                            # Vektorisierte Berechnung wÄre schneller, aber hier loop for safety
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
                                p3d_1 = segment_points[k]
                                p3d_2 = segment_points[k + 1]
                                d1 = self._safe_float(np.dot(p3d_1 - origin, n))
                                d2 = self._safe_float(np.dot(p3d_2 - origin, n))
                                edges_2d.append((
                                    self._safe_float(xs[k]), self._safe_float(ys[k]), 
                                    self._safe_float(xs[k+1]), self._safe_float(ys[k+1]),
                                    d1, d2,
                                ))
                        
                        i += n_pts + 1
                
                if edges_2d:
                    self.reference_bodies.append({
                        'edges_2d': edges_2d,
                        'color': color
                    })
            except Exception as e:
                logger.error(f"Body reference error: {e}")
        
        self.request_update()

    @staticmethod
    def _reference_edge_components(edge):
        """Normalize edge tuple to (x1, y1, x2, y2, d1, d2)."""
        if isinstance(edge, (tuple, list)):
            if len(edge) >= 6:
                return (
                    float(edge[0]), float(edge[1]), float(edge[2]), float(edge[3]),
                    float(edge[4]), float(edge[5]),
                )
            if len(edge) >= 4:
                return float(edge[0]), float(edge[1]), float(edge[2]), float(edge[3]), 0.0, 0.0
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

    def _is_reference_edge_visible(self, d1: float, d2: float) -> bool:
        mode = getattr(self, "reference_clip_mode", "all")
        tol = max(float(getattr(self, "reference_depth_tol", 1e-3)), 1e-9)
        band = max(float(getattr(self, "reference_section_thickness", 1.0)), tol)
        if mode == "front":
            return d1 >= -tol and d2 >= -tol
        if mode == "section":
            crossing = (d1 < -tol and d2 > tol) or (d1 > tol and d2 < -tol)
            near_plane = abs(d1) <= band or abs(d2) <= band
            return crossing or near_plane
        return True

    def _cycle_reference_clip_mode(self):
        order = ("all", "front", "section")
        try:
            idx = order.index(self.reference_clip_mode)
        except ValueError:
            idx = 0
        self._set_reference_clip_mode(order[(idx + 1) % len(order)], announce=True)

    def _set_reference_clip_mode(self, mode: str, announce: bool = True):
        if mode not in {"all", "front", "section"}:
            return
        self.reference_clip_mode = mode
        if announce:
            labels = {"all": "All", "front": "Front", "section": "Section"}
            self.status_message.emit(
                tr("Reference clip: {mode}").format(mode=labels.get(self.reference_clip_mode, self.reference_clip_mode))
            )
        self.request_update()

    def _adjust_reference_section_thickness(self, delta: float):
        val = float(getattr(self, "reference_section_thickness", 1.0)) + float(delta)
        self.reference_section_thickness = max(0.05, min(50.0, val))
        self.status_message.emit(
            tr("Section band: {val} mm").format(val=f"{self.reference_section_thickness:.2f}")
        )
        self.request_update()
    
    def _draw_body_references(self, painter):
        """Zeichnet Bodies als transparente Referenz im Hintergrund."""
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
            base_alpha = int(self.body_reference_opacity * 255)
            depth_tol = max(float(self.reference_depth_tol), 1e-9)
            section_band = max(float(self.reference_section_thickness), depth_tol)

            for edge in edges_2d:
                x1, y1, x2, y2, z1, z2 = self._reference_edge_components(edge)
                if not self._is_reference_edge_visible(z1, z2):
                    continue

                behind = z1 < -depth_tol and z2 < -depth_tol
                crossing = (z1 < -depth_tol and z2 > depth_tol) or (z1 > depth_tol and z2 < -depth_tol)
                near_plane = abs(z1) <= section_band or abs(z2) <= section_band

                alpha = base_alpha
                pen = QPen(QColor(r, g, b, alpha))
                pen.setWidth(1)

                if self.reference_clip_mode == "all":
                    if behind:
                        alpha = max(20, int(base_alpha * 0.35))
                        pen.setColor(QColor(r, g, b, alpha))
                        pen.setStyle(Qt.DashLine)
                    elif crossing or near_plane:
                        pen.setWidth(2)
                elif self.reference_clip_mode == "front":
                    if crossing or near_plane:
                        pen.setWidth(2)
                elif self.reference_clip_mode == "section":
                    alpha = max(alpha, 120)
                    pen.setColor(QColor(r, g, b, alpha))
                    pen.setWidth(2)

                painter.setPen(pen)
                p1 = self.world_to_screen(QPointF(x1, y1))
                p2 = self.world_to_screen(QPointF(x2, y2))
                painter.drawLine(p1, p2)
        
        painter.restore()
    
    
    def _find_closed_profiles(self):
        """
        Kombinierte Logik: 
        1. Welding (Punkte verschweiüƒen) gegen Mikro-Lücken (für Slots/Langlücher).
        2. Hierarchie-Analyse (wie im 3D Modus) für korrekte Lücher/Inseln.
        """
       
        from shapely.geometry import LineString, Polygon as ShapelyPolygon, Point
        from shapely.ops import polygonize, unary_union
        import numpy as np

        self.closed_profiles.clear()

        # --- PHASE 1: Fast Welding (Coordinate Hashing) ---
        # Erhüht auf 0.5mm für bessere DXF-KompatibilitÄt (Fusion nutzt Ähnliche Werte)
        WELD_GRID = 0.5
        welded_points = {} # Map: (ix, iy) -> (float_x, float_y)

        def get_welded_pt(x, y):
            ix = int(round(x / WELD_GRID))
            iy = int(round(y / WELD_GRID))
            key = (ix, iy)

            if key in welded_points:
                return welded_points[key]

            # Suche in Nachbarzellen nach nahen Punkten (erweitert auf 2 Zellen Radius)
            for dx in [-2, -1, 0, 1, 2]:
                for dy in [-2, -1, 0, 1, 2]:
                    if dx == 0 and dy == 0: continue
                    neighbor_key = (ix + dx, iy + dy)
                    if neighbor_key in welded_points:
                        nx, ny = welded_points[neighbor_key]
                        # Toleranz erhüht auf WELD_GRID (statt WELD_GRID/2)
                        if (x - nx)**2 + (y - ny)**2 < WELD_GRID**2:
                            return (nx, ny)

            welded_points[key] = (x, y)
            return (x, y)

        shapely_lines = []
        geometry_sources = []  # Parallel list: Original geometry for each LineString

        # 1. Linien
        lines = [l for l in self.sketch.lines if not l.construction]
        if is_enabled("sketch_debug"):
            logger.info(f"[PROFILE] Lines: {len(lines)} non-construction / {len(self.sketch.lines)} total")
        for line_idx, line in enumerate(lines):
            p1 = get_welded_pt(line.start.x, line.start.y)
            p2 = get_welded_pt(line.end.x, line.end.y)
            if is_enabled("sketch_debug"):
                logger.debug(f"[PROFILE] Line {line_idx}: ({line.start.x:.2f},{line.start.y:.2f})→({line.end.x:.2f},{line.end.y:.2f}) welded to {p1}→{p2}")
            if p1 != p2:
                shapely_lines.append(LineString([p1, p2]))
                geometry_sources.append(('line', line, p1, p2))

        # 2. Bügen
        arcs = [a for a in self.sketch.arcs if not a.construction]
        all_arcs = self.sketch.arcs
        if is_enabled("sketch_debug"):
            logger.info(f"[PROFILE] Arcs: {len(arcs)} non-construction / {len(all_arcs)} total")
        for arc_idx, arc in enumerate(arcs):
            # FIX: Für Slots verwende die Marker-Punkte (exakt mit Linien verbunden)
            # statt der berechneten start_point/end_point (künnen Floating-Point Abweichungen haben)
            start_marker = getattr(arc, '_start_marker', None)
            end_marker = getattr(arc, '_end_marker', None)

            if is_enabled("sketch_debug"):
                logger.debug(f"[PROFILE] Arc {arc_idx}: center=({arc.center.x:.2f}, {arc.center.y:.2f}), "
                            f"r={arc.radius:.2f}, angles={arc.start_angle:.1f}°→{arc.end_angle:.1f}°, "
                            f"construction={arc.construction}, has_markers={start_marker is not None}")

            if start_marker and end_marker:
                # Slot-Arc: Verwende die exakten Verbindungspunkte
                start_p = get_welded_pt(start_marker.x, start_marker.y)
                end_p = get_welded_pt(end_marker.x, end_marker.y)

                # WICHTIG: Berechne Winkel aus den Marker-Punkten, nicht aus arc.start_angle/end_angle
                # da diese nach Solver-LÄufen nicht mehr stimmen künnten
                cx, cy = arc.center.x, arc.center.y
                actual_start_angle = math.degrees(math.atan2(start_marker.y - cy, start_marker.x - cx))
                actual_end_angle = math.degrees(math.atan2(end_marker.y - cy, end_marker.x - cx))

                # Sweep berechnen (immer CCW, also positive Richtung)
                sweep = actual_end_angle - actual_start_angle
                # Normalisiere auf positive Werte für CCW
                while sweep <= 0:
                    sweep += 360
                while sweep > 360:
                    sweep -= 360

                use_start_angle = actual_start_angle
                if is_enabled("sketch_debug"):
                    logger.debug(f"[PROFILE] Arc {arc_idx} (SLOT): marker_start=({start_marker.x:.2f}, {start_marker.y:.2f}), "
                                f"marker_end=({end_marker.x:.2f}, {end_marker.y:.2f}), "
                                f"actual_angles={actual_start_angle:.1f}°→{actual_end_angle:.1f}°, sweep={sweep:.1f}°")
            else:
                # Normaler Arc: Berechne aus Winkeln
                start_p = get_welded_pt(arc.start_point.x, arc.start_point.y)
                end_p = get_welded_pt(arc.end_point.x, arc.end_point.y)

                # Korrekte Sweep-Berechnung
                sweep = arc.end_angle - arc.start_angle
                # Normalisiere auf positive Werte
                while sweep < 0:
                    sweep += 360
                while sweep > 360:
                    sweep -= 360
                # Sehr kleine Sweeps als Vollkreis behandeln (z.B. 359.99° -> 360°)
                if sweep < 0.1:
                    sweep = 360

                use_start_angle = arc.start_angle
                if is_enabled("sketch_debug"):
                    logger.debug(f"[PROFILE] Arc {arc_idx} (NORMAL): start_p={start_p}, end_p={end_p}, sweep={sweep:.1f}°")

            # Segmente basierend auf Sweep (mindestens 8 für gute Kurven)
            steps = max(8, int(sweep / 5))

            points = [start_p]
            for i in range(1, steps):
                t = i / steps
                angle = math.radians(use_start_angle + sweep * t)
                px = arc.center.x + arc.radius * math.cos(angle)
                py = arc.center.y + arc.radius * math.sin(angle)
                # Zwischenpunkte auch durch Welding
                points.append(get_welded_pt(px, py))
            points.append(end_p)

            if is_enabled("sketch_debug"):
                logger.debug(f"[PROFILE] Arc {arc_idx}: Generated {len(points)} points for LineString")
            # Show first, middle, and last point to verify arc direction
            if len(points) >= 3:
                mid_idx = len(points) // 2
                if is_enabled("sketch_debug"):
                    logger.info(f"[PROFILE] Arc {arc_idx} trace: START({points[0][0]:.1f}, {points[0][1]:.1f}) → "
                               f"MID({points[mid_idx][0]:.1f}, {points[mid_idx][1]:.1f}) → "
                               f"END({points[-1][0]:.1f}, {points[-1][1]:.1f})")

            if len(points) >= 2:
                shapely_lines.append(LineString(points))
                # WICHTIG: Speichere ALLE Segment-Paare des Arcs für korrektes Matching
                for seg_idx in range(len(points) - 1):
                    seg_start = points[seg_idx]
                    seg_end = points[seg_idx + 1]
                    geometry_sources.append(('arc', arc, seg_start, seg_end))

        # --- 2b. NATIVE SPLINES (NEU für saubere Extrusion) ---
        # Splines als LineStrings für Shapely-Polygonisierung,
        # aber Original-Daten bleiben in sketch.native_splines für Build123d
        # NEU: Geschlossene Splines werden als standalone_polys behandelt (wie Kreise)
        native_splines = getattr(self.sketch, 'native_splines', [])
        closed_spline_polys = []  # Für geschlossene Splines

        for spline in native_splines:
            if spline.construction:
                continue
            try:
                # Evaluiere Spline zu Punkten für Shapely
                pts = spline.evaluate_points(50)  # Hohe Auflüsung für gute Profil-Erkennung
                if len(pts) >= 2:
                    # Start/End durch Welding
                    welded_pts = []
                    for px, py in pts:
                        welded_pts.append(get_welded_pt(px, py))

                    # Prüfe ob Spline geschlossen ist (Start ≈ End)
                    start_pt = welded_pts[0]
                    end_pt = welded_pts[-1]
                    gap = math.hypot(end_pt[0] - start_pt[0], end_pt[1] - start_pt[1])

                    if gap < WELD_GRID:  # Geschlossen!
                        # Erstelle Polygon direkt (wie bei Kreisen)
                        # Letzen Punkt entfernen wenn er mit erstem identisch ist
                        if welded_pts[-1] == welded_pts[0]:
                            poly_pts = welded_pts[:-1]
                        else:
                            poly_pts = welded_pts
                        if len(poly_pts) >= 3:
                            closed_poly = ShapelyPolygon(poly_pts)
                            if closed_poly.is_valid and closed_poly.area > 0.01:
                                closed_spline_polys.append(closed_poly)
                                logger.info(f"Geschlossener Spline als Polygon: {len(poly_pts)} Punkte, area={closed_poly.area:.2f}")
                            else:
                                # Fallback: Als LineString
                                shapely_lines.append(LineString(welded_pts))
                    else:
                        # Offener Spline -> als LineString für Polygonisierung
                        shapely_lines.append(LineString(welded_pts))

                    # Speichere Segment-Paare für Geometrie-Matching
                    for seg_idx in range(len(welded_pts) - 1):
                        seg_start = welded_pts[seg_idx]
                        seg_end = welded_pts[seg_idx + 1]
                        geometry_sources.append(('spline', spline, seg_start, seg_end))

                    logger.debug(f"Native Spline: {len(welded_pts)} Punkte, gap={gap:.4f}mm, closed={gap < WELD_GRID}")
            except Exception as e:
                logger.warning(f"Spline-Konvertierung für Profil fehlgeschlagen: {e}")

        # --- 3. KREISE ---
        # Kreise müssen in Polygone umgewandelt werden, da Shapely keine echten Kreise kennt
        # NEU: ü£berlappende Kreise werden als Arcs behandelt für korrekte Profile-Erkennung
        standalone_polys = []
        circles = [c for c in self.sketch.circles if not c.construction]

        if circles:
            logger.debug(f"Verarbeite {len(circles)} Kreise für Profil-Erkennung")

        if circles:
            # NEU: Kreis-ü£berlappungs-Erkennung (Kreis-Kreis UND Kreis-Linie)
            from sketcher.geometry import get_circle_circle_intersection, circle_line_intersection
            from sketcher import Circle2D

            # Finde alle Schnittpunkte für jeden Kreis
            circle_intersections = {i: [] for i in range(len(circles))}
            overlapping_circles = set()

            # 1. Kreis-Kreis Schnittpunkte
            for i in range(len(circles)):
                for j in range(i + 1, len(circles)):
                    c1, c2 = circles[i], circles[j]
                    pts = get_circle_circle_intersection(c1, c2)

                    if len(pts) >= 1:
                        overlapping_circles.add(i)
                        overlapping_circles.add(j)

                        for pt in pts:
                            angle1 = math.atan2(pt.y - c1.center.y, pt.x - c1.center.x)
                            circle_intersections[i].append((angle1, pt))

                            angle2 = math.atan2(pt.y - c2.center.y, pt.x - c2.center.x)
                            circle_intersections[j].append((angle2, pt))

            # 2. Kreis-Linie Schnittpunkte (NEU!)
            for idx, circle in enumerate(circles):
                for line in lines:
                    try:
                        pts = circle_line_intersection(circle, line)
                        if pts:
                            overlapping_circles.add(idx)
                            for pt in pts:
                                angle = math.atan2(pt.y - circle.center.y, pt.x - circle.center.x)
                                circle_intersections[idx].append((angle, pt))
                    except Exception:
                        pass  # Intersection-Fehler ignorieren

            # Verarbeite Kreise
            for idx, circle in enumerate(circles):
                cx, cy, r = circle.center.x, circle.center.y, circle.radius

                if idx in overlapping_circles and circle_intersections[idx]:
                    # ü£berlappender Kreis: Teile in Arcs und füge zu shapely_lines hinzu
                    intersections = circle_intersections[idx]
                    # Sortiere nach Winkel
                    intersections.sort(key=lambda x: x[0])

                    logger.debug(f"  Kreis {idx} überlappt: {len(intersections)} Schnittpunkte")

                    # Erstelle Arcs zwischen Schnittpunkten
                    for seg_idx in range(len(intersections)):
                        start_angle = intersections[seg_idx][0]
                        end_angle = intersections[(seg_idx + 1) % len(intersections)][0]

                        # Handle Wrap-Around
                        if end_angle <= start_angle:
                            end_angle += 2 * math.pi

                        # Erstelle Arc als LineString
                        arc_pts = []
                        sweep = end_angle - start_angle
                        steps = max(8, int(sweep / 0.1))  # ~0.1 rad pro Segment

                        for step in range(steps + 1):
                            t = step / steps
                            a = start_angle + sweep * t
                            px = cx + r * math.cos(a)
                            py = cy + r * math.sin(a)
                            arc_pts.append(get_welded_pt(px, py))

                        if len(arc_pts) >= 2:
                            shapely_lines.append(LineString(arc_pts))
                            # Segment-Info für Geometry-Matching
                            for s in range(len(arc_pts) - 1):
                                geometry_sources.append(('circle_arc', circle, arc_pts[s], arc_pts[s + 1]))
                else:
                    # Nicht-überlappender Kreis: Behandle als standalone Polygon
                    pts = []
                    segments = 64
                    for i in range(segments):
                        a = 2 * math.pi * i / segments
                        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
                    circle_poly = ShapelyPolygon(pts)
                    standalone_polys.append(circle_poly)
                    logger.debug(f"  Kreis: center=({cx:.2f}, {cy:.2f}), r={r:.2f}, area={circle_poly.area:.2f}")

        # Geschlossene Splines hinzufügen (wie Kreise behandeln)
        if closed_spline_polys:
            logger.info(f"Füge {len(closed_spline_polys)} geschlossene Splines als Polygone hinzu")
            standalone_polys.extend(closed_spline_polys)

        # --- PHASE 2: Gap Closing & Polygonize ---

        raw_polys = []

        # Aus Linien/Bügen FlÄchen finden
        if shapely_lines:
            try:
                merged = unary_union(shapely_lines)

                # PHASE 2a: Lücken schlieüƒen (für DXF-KompatibilitÄt)
                # Finde offene Endpunkte und verbinde nahe Punkte
                if hasattr(merged, 'geoms'):
                    # Es ist eine MultiLineString - suche offene Enden
                    endpoints = []
                    for geom in merged.geoms:
                        if hasattr(geom, 'coords'):
                            coords = list(geom.coords)
                            if len(coords) >= 2:
                                endpoints.append(coords[0])
                                endpoints.append(coords[-1])

                    # Verbinde nahe Endpunkte (Gap < 1mm)
                    GAP_TOLERANCE = 1.0
                    additional_lines = []
                    used = set()
                    for i, p1 in enumerate(endpoints):
                        if i in used:
                            continue
                        for j, p2 in enumerate(endpoints):
                            if j <= i or j in used:
                                continue
                            dist = math.hypot(p1[0] - p2[0], p1[1] - p2[1])
                            if 0 < dist < GAP_TOLERANCE:
                                # Kleine Lücke gefunden - verbinden
                                additional_lines.append(LineString([p1, p2]))
                                used.add(i)
                                used.add(j)
                                break

                    if additional_lines:
                        logger.debug(f"Gap closing: {len(additional_lines)} kleine Lücken geschlossen")
                        merged = unary_union([merged] + additional_lines)

                for poly in polygonize(merged):
                    if poly.area > 0.01:
                        raw_polys.append(poly)
            except Exception as e:
                logger.warning(f"Polygonize error: {e}")

        # EigenstÄndige Kreise hinzufügen (wenn sie nicht schon durch Linien abgedeckt sind)
        # WICHTIG: Nur ECHTE Duplikate filtern (gleiche Position + gleiche Grüüƒe)
        # Kreise innerhalb anderer Polygone sind KEINE Duplikate - sie werden spÄter als Lücher erkannt
        for c_poly in standalone_polys:
            is_duplicate = False
            c_centroid = c_poly.centroid
            c_area = c_poly.area

            for existing in raw_polys:
                # 1. Grüüƒen-Check: Nur Ähnliche Grüüƒen vergleichen (°10%)
                area_ratio = existing.area / c_area if c_area > 0 else 999
                if area_ratio < 0.9 or area_ratio > 1.1:
                    continue

                # 2. Centroid-Check: Müssen fast identisch sein (innerhalb 5% des Radius)
                e_centroid = existing.centroid
                centroid_dist = math.hypot(c_centroid.x - e_centroid.x, c_centroid.y - e_centroid.y)
                radius_approx = math.sqrt(c_area / math.pi)

                # Nur Duplikat wenn Centroids SEHR nah (< 5% des Radius)
                if centroid_dist < radius_approx * 0.05:
                    is_duplicate = True
                    logger.debug(f"Kreis-Duplikat erkannt: area={c_area:.2f}, centroid_dist={centroid_dist:.4f}")
                    break

            if not is_duplicate:
                raw_polys.append(c_poly)
                logger.debug(f"EigenstÄndiger Kreis hinzugefügt: area={c_area:.2f} @ ({c_centroid.x:.2f}, {c_centroid.y:.2f})")

        if not raw_polys:
            return

        # --- PHASE 3: Hierarchie & Holes (Die Logic aus GeometryDetector) ---

        # Sortieren nach Grüüƒe (Groüƒ zuerst -> Parents)
        raw_polys.sort(key=lambda p: p.area, reverse=True)

        n_polys = len(raw_polys)

        # OPTIMIERUNG: Bei vielen Polygonen Bounding-Box Pre-Filter verwenden
        # und Fortschritt loggen
        if n_polys > 20:
            logger.info(f"Hierarchie-Analyse: {n_polys} Polygone (kann dauern...)")

        # Pre-compute bounding boxes für schnellen Vorfilter
        bounds = [p.bounds for p in raw_polys]  # (minx, miny, maxx, maxy)

        def bbox_contains(parent_bounds, child_bounds):
            """Schneller Check ob Parent-BBox die Child-BBox enthalten KÖNNTE"""
            return (parent_bounds[0] <= child_bounds[0] and
                    parent_bounds[1] <= child_bounds[1] and
                    parent_bounds[2] >= child_bounds[2] and
                    parent_bounds[3] >= child_bounds[3])

        # Wer enthÄlt wen?
        # hierarchy[i] = Liste von Indizes, die in Polygon i liegen
        hierarchy = {i: [] for i in range(n_polys)}
        contains_checks = 0

        for i, parent in enumerate(raw_polys):
            parent_bounds = bounds[i]
            for j, child in enumerate(raw_polys):
                if i == j:
                    continue
                # OPTIMIERUNG: Grüüƒenfilter - Kind kann nicht grüüƒer als Parent sein
                if raw_polys[j].area >= raw_polys[i].area:
                    continue
                # OPTIMIERUNG: Bounding Box Vorfilter
                if not bbox_contains(parent_bounds, bounds[j]):
                    continue
                # Jetzt erst teurer contains() Check
                try:
                    contains_checks += 1
                    if parent.contains(child):
                        hierarchy[i].append(j)
                except Exception as e:
                    logger.debug(f"Contains check skipped for poly {i}/{j}: {e}")
                    continue

        if n_polys > 20:
            logger.debug(f"  → {contains_checks} contains() Checks durchgeführt (statt max {n_polys*n_polys})")

        # Direkte Kinder finden (Direct Children)
        direct_children = {i: [] for i in range(n_polys)}

        for parent_idx, children_indices in hierarchy.items():
            for child_idx in children_indices:
                is_direct = True
                for other_child in children_indices:
                    if child_idx == other_child:
                        continue
                    # OPTIMIERUNG: Grüüƒenfilter
                    if raw_polys[child_idx].area >= raw_polys[other_child].area:
                        continue
                    # OPTIMIERUNG: BBox Vorfilter
                    if not bbox_contains(bounds[other_child], bounds[child_idx]):
                        continue
                    try:
                        if raw_polys[other_child].contains(raw_polys[child_idx]):
                            is_direct = False
                            break
                    except Exception:
                        continue
                if is_direct:
                    direct_children[parent_idx].append(child_idx)

        # Profile erstellen (Parent minus direkte Kinder)
        # Wir müssen vermeiden, dass Kinder doppelt gezeichnet werden.
        #
        # Hierarchie-Logik:
        # - Level 0: Top-Level Polygone (keine Eltern) → hinzufügen mit Lüchern
        # - Level 1: Kinder von Level 0 → werden als Lücher abgezogen, NICHT separat hinzufügen
        # - Level 2: Kinder von Level 1 (Inseln in Lüchern) → hinzufügen mit Lüchern
        # - Level 3: usw.
        #
        # Regel: Nur Polygone auf geraden Levels (0, 2, 4, ...) hinzufügen

        # Finde alle Polygone die Kinder von anderen sind (und selbst keine Kinder haben)
        is_pure_child = set()  # Polygone die Kinder sind und selbst keine Kinder haben
        for parent_idx, children_indices in direct_children.items():
            for child_idx in children_indices:
                # Wenn das Kind selbst keine Kinder hat, ist es ein "reines Loch"
                if not direct_children[child_idx]:
                    is_pure_child.add(child_idx)

        # Berechne Level für jedes Polygon (Level = Anzahl Ancestors)
        def get_level(idx, cache={}):
            if idx in cache:
                return cache[idx]
            # Finde Parent
            for parent_idx, children_indices in direct_children.items():
                if idx in children_indices:
                    level = get_level(parent_idx, cache) + 1
                    cache[idx] = level
                    return level
            cache[idx] = 0  # Kein Parent = Top-Level
            return 0

        # --- Baue Endpoint-zu-Geometry Mapping für spÄteres Matching ---
        # Key: (welded_start, welded_end) -> (geom_type, geom_obj)
        # Auch reversed key für bidirektionale Suche
        endpoint_to_geom = {}
        for geom_type, geom_obj, start_p, end_p in geometry_sources:
            key_fwd = (start_p, end_p)
            key_rev = (end_p, start_p)
            endpoint_to_geom[key_fwd] = (geom_type, geom_obj)
            endpoint_to_geom[key_rev] = (geom_type, geom_obj)  # Reversed lookup

        def match_polygon_to_geometry(poly, endpoint_map, tolerance=0.5):
            """
            Matches polygon exterior segments to original geometry objects.
            Returns list of (geom_type, geom_obj) in polygon order.
            """
            coords = list(poly.exterior.coords)
            matched_geometry = []

            for i in range(len(coords) - 1):
                p1 = coords[i]
                p2 = coords[i + 1]

                # Direct key lookup
                key = (p1, p2)
                if key in endpoint_map:
                    matched_geometry.append(endpoint_map[key])
                    continue

                # Fuzzy matching for near-coincident points
                best_match = None
                best_dist = tolerance ** 2

                for (ep1, ep2), geom_info in endpoint_map.items():
                    # Check if this segment's endpoints match within tolerance
                    dist1 = (p1[0] - ep1[0])**2 + (p1[1] - ep1[1])**2
                    dist2 = (p2[0] - ep2[0])**2 + (p2[1] - ep2[1])**2
                    total_dist = dist1 + dist2

                    if total_dist < best_dist:
                        best_dist = total_dist
                        best_match = geom_info

                if best_match:
                    matched_geometry.append(best_match)
                else:
                    # No match found - might be a gap-closing line
                    matched_geometry.append(('gap', None))

            return matched_geometry

        for i in range(len(raw_polys)):
            level = get_level(i)

            # Nur gerade Levels hinzufügen (0, 2, 4, ...)
            # Ungerade Levels (1, 3, 5, ...) sind Lücher und werden per difference() abgezogen
            if level % 2 != 0:
                continue

            poly = raw_polys[i]
            children = direct_children[i]

            final_shape = poly
            for child_idx in children:
                try:
                    final_shape = final_shape.difference(raw_polys[child_idx])
                except Exception as e:
                    logger.warning(f"Difference error: {e}")

            # Speichern als Polygon MIT Geometry-Mapping
            if not final_shape.is_empty and final_shape.area > 0.01:
                # Match polygon segments to source geometry
                matched_geom = match_polygon_to_geometry(final_shape, endpoint_to_geom)

                # Dedupliziere: Entferne aufeinanderfolgende Duplikate
                # (z.B. wenn ein Spline aus vielen Segmenten besteht)
                unique_geom = []
                for geom_info in matched_geom:
                    if not unique_geom or unique_geom[-1] != geom_info:
                        unique_geom.append(geom_info)

                # Log für Debugging
                geom_types = [g[0] for g in unique_geom if g[0] != 'gap']
                if geom_types:
                    logger.debug(f"Profile {i}: {len(unique_geom)} geometry segments: {set(geom_types)}")

                # Store as (type, polygon, geometry_list)
                self.closed_profiles.append(('polygon', final_shape, unique_geom))

        # Store geometry mapping on sketch for extrusion to access
        # Key: polygon area (rounded) for fast lookup
        if not hasattr(self.sketch, '_profile_geometry_map'):
            self.sketch._profile_geometry_map = {}

        for profile_tuple in self.closed_profiles:
            if len(profile_tuple) == 3:
                _, poly, geom_list = profile_tuple
                # Create stable key from polygon bounds + area
                bounds = poly.bounds
                key = (round(bounds[0], 2), round(bounds[1], 2),
                       round(bounds[2], 2), round(bounds[3], 2),
                       round(poly.area, 2))
                self.sketch._profile_geometry_map[key] = geom_list
                logger.debug(f"Stored geometry map for profile: {key}")

        # Hinweis: Diese Methode erzeugt jetzt Shapely-Polygone, die Lücher enthalten künnen!
        # Der Renderer muss das verstehen.
        self._build_profile_hierarchy()

        # CAD Kernel First: Synchronisiere Profile auf das Sketch-Objekt
        # Damit kann _compute_extrude_part/_compute_revolve die Profile direkt
        # aus dem Sketch abrufen (ohne SketchEditor zu benütigen)
        self._sync_profiles_to_sketch()

    def _sync_profiles_to_sketch(self):
        """
        CAD Kernel First: Kopiert die closed_profiles auf das Sketch-Objekt.

        Dies ermüglicht es dem Rebuild-Prozess, Profile direkt aus dem Sketch
        abzurufen, ohne den SketchEditor zu benütigen.

        WICHTIG: Wir speichern ALLE selektierbaren Faces - sowohl Parents
        als auch Lücher (Interiors). Das ermüglicht dem User, einzelne
        Lücher zu extrudieren.
        """
        if not self.sketch:
            return

        from shapely.geometry import Polygon as ShapelyPolygon

        # Extrahiere Shapely Polygone (nicht die Metadaten)
        polys = []
        for profile_tuple in self.closed_profiles:
            if len(profile_tuple) >= 2:
                p_type = profile_tuple[0]
                p_data = profile_tuple[1]
                if p_type == 'polygon' and hasattr(p_data, 'exterior'):
                    polys.append(p_data)

                    # NEU: Auch die Interiors (Lücher) als separate Polygone hinzufügen
                    # damit sie bei der Selektion gematcht werden künnen
                    for interior in p_data.interiors:
                        try:
                            hole_poly = ShapelyPolygon(interior.coords)
                            if hole_poly.is_valid and hole_poly.area > 0.01:
                                polys.append(hole_poly)
                                logger.debug(f"  → Hole als Profil: area={hole_poly.area:.1f} @ ({hole_poly.centroid.x:.2f}, {hole_poly.centroid.y:.2f})")
                        except Exception as e:
                            logger.warning(f"Hole zu Polygon fehlgeschlagen: {e}")

                elif p_type == 'circle':
                    # Kreis zu Polygon konvertieren
                    circle = p_data
                    coords = []
                    for i in range(32):
                        angle = 2 * math.pi * i / 32
                        x = circle.center.x + circle.radius * math.cos(angle)
                        y = circle.center.y + circle.radius * math.sin(angle)
                        coords.append((x, y))
                    if coords:
                        polys.append(ShapelyPolygon(coords))

        self.sketch.closed_profiles = polys
        logger.debug(f"[CAD Kernel First] Synced {len(polys)} profiles to sketch (inkl. Holes)")

    def _build_profile_hierarchy(self):
        """Baut Containment-Hierarchie auf: Welche Faces sind Lücher in anderen?"""
        from shapely.geometry import Polygon as ShapelyPolygon, Point as ShapelyPoint

        def get_profile_vertices(profile):
            """Extrahiert Vertices aus einem Profil für Point-in-Polygon Test"""
            # Handle both 2-tuple and 3-tuple formats
            profile_type = profile[0]
            data = profile[1]
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
            """Berechnet FlÄche eines Profils"""
            # Handle both 2-tuple and 3-tuple formats
            profile_type = profile[0]
            data = profile[1]
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
            # Handle both 2-tuple and 3-tuple formats
            profile_type = profile[0]
            data = profile[1]
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
        
        # Sortiere Profile nach FlÄche (grüüƒte zuerst)
        # Grüüƒere Profile künnen kleinere enthalten
        areas = [get_profile_area(p) for p in self.closed_profiles]
        sorted_indices = sorted(range(n), key=lambda i: areas[i], reverse=True)
        
        # Für jedes Profil: Finde den kleinsten Container
        for i in range(n):
            profile_i = self.closed_profiles[i]
            point_i = get_profile_point(profile_i)
            
            if point_i is None:
                continue
            
            # Finde den kleinsten Container (mit kleinster FlÄche der enthÄlt)
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
                    # j enthÄlt i
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
    

    # In sketch_editor.py

    def snap_point(self, w):
        if not self.snap_enabled: 
            self.last_snap_diagnostic = ""
            self.last_snap_confidence = 0.0
            self.last_snap_priority = 0
            self.last_snap_distance = 0.0
            return w, SnapType.NONE, None  # <--- Drittes Element: Entity
            
        if self.snapper:
            if self.index_dirty: self._rebuild_spatial_index()
            screen_pos = self.world_to_screen(w)
            res = self.snapper.snap(screen_pos)
            self.last_snap_diagnostic = getattr(res, "diagnostic", "") or ""
            self.last_snap_confidence = float(getattr(res, "confidence", 0.0) or 0.0)
            self.last_snap_priority = int(getattr(res, "priority", 0) or 0)
            self.last_snap_distance = float(getattr(res, "distance", 0.0) or 0.0)
            # Rückgabe: Punkt, Typ, Getroffenes Entity (für Auto-Constraints)
            return res.point, res.type, res.target_entity
            
        else:
            self.last_snap_diagnostic = ""
            self.last_snap_confidence = 0.0
            self.last_snap_priority = 0
            self.last_snap_distance = 0.0
            if self.grid_snap:
                 gx = round(w.x() / self.grid_size) * self.grid_size
                 gy = round(w.y() / self.grid_size) * self.grid_size
                 return QPointF(gx, gy), SnapType.GRID, None
            return w, SnapType.NONE, None
    
    
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
    
    def _get_canvas_dict(self):
        """Canvas-State als Dict für Undo/Save."""
        if not self.canvas_image or not self.canvas_world_rect:
            return None
        wr = self.canvas_world_rect
        return {
            'file_path': self.canvas_file_path,
            'rect': [wr.x(), wr.y(), wr.width(), wr.height()],
            'opacity': self.canvas_opacity,
            'visible': self.canvas_visible,
            'locked': self.canvas_locked,
        }

    def _restore_canvas_dict(self, data):
        """Canvas-State aus Dict wiederherstellen."""
        if not data:
            self.canvas_image = None
            self.canvas_world_rect = None
            self.canvas_file_path = None
            return
        from PySide6.QtGui import QPixmap
        path = data.get('file_path')
        if path:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self.canvas_image = pixmap
                self.canvas_file_path = path
            else:
                self.canvas_image = None
                self.canvas_file_path = None
                return
        r = data.get('rect', [0, 0, 100, 100])
        self.canvas_world_rect = QRectF(r[0], r[1], r[2], r[3])
        self.canvas_opacity = data.get('opacity', 0.4)
        self.canvas_visible = data.get('visible', True)
        self.canvas_locked = data.get('locked', False)

    def _save_undo(self):
        state = self.sketch.to_dict()
        state['_canvas'] = self._get_canvas_dict()
        self.undo_stack.append(state)
        self.redo_stack.clear()
        if len(self.undo_stack) > self.max_undo: self.undo_stack.pop(0)

        # Performance Optimization 1.6: Invalidiere Intersection Cache bei Geometrie-Änderungen
        if self.snapper and hasattr(self.snapper, 'invalidate_intersection_cache'):
            self.snapper.invalidate_intersection_cache()
    
    def _rollback_last_undo_state(self) -> bool:
        """Stiller Rollback auf den letzten Undo-Snapshot."""
        if not self.undo_stack:
            return False

        state = self.undo_stack.pop()
        self.sketch = Sketch.from_dict(state)
        self._restore_canvas_dict(state.get('_canvas'))
        self._clear_selection()
        self._find_closed_profiles()
        self.sketched_changed.emit()

        if self.snapper and hasattr(self.snapper, 'invalidate_intersection_cache'):
            self.snapper.invalidate_intersection_cache()

        self.request_update()
        return True

    def undo(self):
        if not self.undo_stack:
            self.show_message(tr("Nothing to undo"), 1500, QColor(255, 200, 100))
            return
        redo_state = self.sketch.to_dict()
        redo_state['_canvas'] = self._get_canvas_dict()
        self.redo_stack.append(redo_state)
        state = self.undo_stack.pop()
        self.sketch = Sketch.from_dict(state)
        self._restore_canvas_dict(state.get('_canvas'))
        self._clear_selection()
        self._find_closed_profiles()
        self.sketched_changed.emit()
        self.show_message(tr("Undone"), 1500)
        logger.debug("Undo performed")

        # Performance Optimization 1.6: Invalidiere Intersection Cache
        if self.snapper and hasattr(self.snapper, 'invalidate_intersection_cache'):
            self.snapper.invalidate_intersection_cache()

        self.request_update()

    def redo(self):
        if not self.redo_stack:
            self.show_message(tr("Nothing to redo"), 1500, QColor(255, 200, 100))
            return
        undo_state = self.sketch.to_dict()
        undo_state['_canvas'] = self._get_canvas_dict()
        self.undo_stack.append(undo_state)
        state = self.redo_stack.pop()
        self.sketch = Sketch.from_dict(state)
        self._restore_canvas_dict(state.get('_canvas'))
        self._clear_selection()
        self._find_closed_profiles()
        self.sketched_changed.emit()
        self.show_message(tr("Redone"), 1500)
        logger.debug("Redo performed")

        # Performance Optimization 1.6: Invalidiere Intersection Cache
        if self.snapper and hasattr(self.snapper, 'invalidate_intersection_cache'):
            self.snapper.invalidate_intersection_cache()

        self.request_update()
    
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

    def _on_dxf_finished(self, lines, circles, arcs, native_splines=None):
        from PySide6.QtWidgets import QApplication
        from sketcher.geometry import Spline2D

        if native_splines is None:
            native_splines = []

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

        # Native Splines hinzufügen (NEU)
        for spline_data in native_splines:
            control_points, knots, degree, weights = spline_data
            spline = Spline2D(
                control_points=control_points,
                knots=knots,
                degree=degree,
                weights=weights
            )
            self.sketch.native_splines.append(spline)
            logger.info(f"Native Spline hinzugefügt: {len(control_points)} ctrl pts, deg={degree}")

        QApplication.restoreOverrideCursor()
        self._find_closed_profiles()
        self.sketched_changed.emit()

        # Status-Meldung mit Spline-Count
        msg = f"Fertig: {len(lines)} Linien, {len(circles)} Kreise, {len(arcs)} Bügen"
        if native_splines:
            msg += f", {len(native_splines)} Splines (nativ)"
        self.status_message.emit(msg)

        self.request_update()
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
    
    def _detect_circle_from_points(self, points, tolerance=None):
        """
        Erkennt ob ein Polygon eigentlich ein Kreis ist.

        Args:
            points: Liste von (x, y) Tupeln
            tolerance: Relative Toleranz für Radius-Varianz (default: SKETCH_CIRCLE_FIT)

        Returns:
            (cx, cy, radius) als native Floats wenn es ein Kreis ist, sonst None
        """
        if tolerance is None:
            tolerance = Tolerances.SKETCH_CIRCLE_FIT
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
                # Fallback: Build123d rÄt die X-Richtung
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
        Extrudiert den Sketch. FÄngt Fehler ab und liefert None zurück, 
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
        for i, profile_tuple in enumerate(self.closed_profiles):
            p_type = profile_tuple[0]
            p_data = profile_tuple[1]
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
                    for profile_tuple in self.closed_profiles:
                        # Handle both 2-tuple and 3-tuple formats
                        p_type = profile_tuple[0]
                        p_data = profile_tuple[1]
                        # Fall 1: Polygon
                        if p_type == 'polygon':
                            # FIX: MultiPolygon behandeln (kann von difference() kommen)
                            from shapely.geometry import MultiPolygon as ShapelyMultiPolygon

                            polygons_to_process = []
                            if isinstance(p_data, ShapelyMultiPolygon):
                                polygons_to_process = list(p_data.geoms)
                            else:
                                polygons_to_process = [p_data]

                            for sub_poly in polygons_to_process:
                                if not hasattr(sub_poly, 'exterior'):
                                    continue

                                # FIX: Ensure polygon exterior is CCW (counter-clockwise)
                                # Shapely's is_ccw checks if the exterior ring is CCW
                                from shapely.geometry import polygon as shapely_polygon
                                if not sub_poly.exterior.is_ccw:
                                    logger.warning(f"[EXTRUDE] Polygon exterior is CW - reversing to CCW")
                                    sub_poly = shapely_polygon.orient(sub_poly, sign=1.0)  # Force CCW

                                coords = list(sub_poly.exterior.coords)
                                # Duplikate entfernen und zu Floats konvertieren
                                pts = [(self._safe_float(c[0]), self._safe_float(c[1])) for c in coords]
                                if len(pts) > 0 and pts[0] == pts[-1]:
                                    pts.pop() # Letzten Punkt weg, wenn doppelt

                                if len(pts) >= 3:
                                    logger.info(f"[EXTRUDE] Polygon: {len(pts)} pts, is_ccw={sub_poly.exterior.is_ccw}, area={sub_poly.area:.1f}")
                                    # Log key points to see the shape
                                    # For a slot: should see 4 corners + arc points
                                    step = max(1, len(pts) // 20)  # Sample ~20 points
                                    sampled = [(i, pts[i]) for i in range(0, len(pts), step)]
                                    for idx, pt in sampled[:15]:  # Max 15 samples
                                        logger.debug(f"  [{idx:3d}] ({pt[0]:8.2f}, {pt[1]:8.2f})")
                                    Polygon(*pts, align=None)
                                    created_any = True

                                    # Lücher (Interiors)
                                    if hasattr(sub_poly, 'interiors'):
                                        for idx, interior in enumerate(sub_poly.interiors):
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
            mesh_data = solid.tessellate(tolerance=Tolerances.TESSELLATION_PREVIEW)
            verts = [(v.X, v.Y, v.Z) for v in mesh_data[0]]
            faces = [tuple(t) for t in mesh_data[1]]
            
            return solid, verts, faces
            
        except Exception as e:
            # Statt GUI-Absturz nur Log-Ausgabe
            logger.error(f"Extrude Fehler: {e}")
            return None, None, None

    def get_build123d_profiles(self):
        """
        Holt Profile mittels Build123d-basierter Detection (Phase 2).

        Nutzt OpenCASCADE für exakte Geometrie statt Shapely-Approximation.
        Kreise bleiben echte Kreise, keine 64-Eck Polygone.

        Returns:
            Tuple (faces, error) - faces ist Liste von Build123d Face-Objekten
        """
        try:
            from sketcher.profile_detector_b3d import Build123dProfileDetector, is_available

            if not is_available():
                return None, "Build123d nicht verfügbar"

            plane = self.get_build123d_plane()
            detector = Build123dProfileDetector()
            faces, error = detector.get_profiles_for_extrude(self.sketch, plane)

            if error:
                logger.warning(f"Build123d Profile-Detection: {error}")
                return None, error

            logger.info(f"Build123d Profile-Detection: {len(faces)} exakte Faces gefunden")
            return faces, None

        except Exception as e:
            logger.error(f"Build123d Profile-Detection Fehler: {e}")
            return None, str(e)

    def get_build123d_part_v2(self, height: float, operation: str = "New Body"):
        """
        Extrudiert mit Build123d-basierter Profile-Detection (Phase 2).

        Vorteile gegenüber get_build123d_part():
        - Kreise sind echte analytische Kurven
        - ü£berlappende Geometrie wird exakt berechnet
        - Konsistenz zwischen 2D und 3D

        Returns:
            Tuple (solid, vertices, faces) oder (None, None, None) bei Fehler
        """
        if not HAS_BUILD123D:
            return None, None, None

        # Versuche Build123d Profile-Detection
        logger.info("Build123d V2: Versuche exakte Profile-Detection...")
        b3d_faces, error = self.get_build123d_profiles()

        if b3d_faces is None or not b3d_faces:
            # Fallback zur alten Methode
            logger.warning(f"Build123d Profile-Detection nicht verfügbar ({error}), nutze Shapely-Fallback")
            return self.get_build123d_part(height, operation)

        plane = self.get_build123d_plane()

        try:
            from build123d import BuildPart, extrude
            from config import Tolerances

            with BuildPart() as part:
                # Faces direkt extrudieren
                for face in b3d_faces:
                    extrude(face, amount=height)

                solid = part.part

            if solid is None:
                return None, None, None

            # Mesh generieren
            mesh_data = solid.tessellate(tolerance=Tolerances.TESSELLATION_PREVIEW)
            verts = [(v.X, v.Y, v.Z) for v in mesh_data[0]]
            faces = [tuple(t) for t in mesh_data[1]]

            logger.success(f"Build123d V2 Extrude erfolgreich: {len(verts)} Vertices")
            return solid, verts, faces

        except Exception as e:
            logger.error(f"Build123d V2 Extrude Fehler: {e}")
            import traceback
            traceback.print_exc()
            # Fallback
            return self.get_build123d_part(height, operation)

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

            mesh_data = solid.tessellate(tolerance=Tolerances.TESSELLATION_COARSE)
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

                    for profile_tuple in self.closed_profiles:
                        # Handle both 2-tuple and 3-tuple formats
                        p_type = profile_tuple[0]
                        p_data = profile_tuple[1]
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
            mesh = solid.tessellate(tolerance=Tolerances.TESSELLATION_QUALITY)
            verts = [(v.X, v.Y, v.Z) for v in mesh[0]]
            faces = [tuple(t) for t in mesh[1]]
            
            return solid, verts, faces
            
        except Exception as e:
            logger.error(f"Build123d Fehler: {e}")
            return None, None, None
    
    def has_build123d(self) -> bool:
        """Prüft ob Build123d verfügbar ist"""
        return HAS_BUILD123D

    # ========== Phase 8: Smart Entry - tool_step Property ==========

    @property
    def tool_step(self) -> int:
        """Current step in multi-step tool operation."""
        return self._tool_step

    @tool_step.setter
    def tool_step(self, value: int):
        """Sets tool_step and triggers auto-show check if enabled."""
        old_value = self._tool_step
        self._tool_step = value

        # Trigger auto-show check when step changes (Phase 8: Smart Entry)
        if value != old_value:
            self._check_auto_show_dim_input()

    def _should_auto_show_dim_input(self) -> bool:
        """
        Checks if DimensionInput panel should auto-show.

        Phase 8: Smart Entry - Panel shows automatically after first point
        for most drawing tools, eliminating the need to press Tab.
        """
        # Don't show if already visible
        if self.dim_input.isVisible():
            return False

        # Don't trigger for same step twice
        if self._last_auto_show_step == self._tool_step:
            return False

        # Map: tool → required step for auto-show
        auto_show_tools = {
            SketchTool.LINE: 1,           # After 1st point
            SketchTool.RECTANGLE: 1,
            SketchTool.RECTANGLE_CENTER: 1,
            SketchTool.CIRCLE: 1,
            SketchTool.ELLIPSE: 1,
            SketchTool.POLYGON: 1,
            SketchTool.SLOT: 1,
            SketchTool.NUT: 1,            # After center point
            SketchTool.STAR: 1,           # After center point
            SketchTool.MOVE: 1,
            SketchTool.COPY: 1,
            SketchTool.ROTATE: 1,
            SketchTool.SCALE: 1,
            SketchTool.PATTERN_LINEAR: 1,
            SketchTool.PATTERN_CIRCULAR: 1,
            # OFFSET, FILLET_2D, CHAMFER_2D: Show immediately on selection (step 0)
            SketchTool.OFFSET: 0,
            SketchTool.FILLET_2D: 0,
            SketchTool.CHAMFER_2D: 0,
        }

        required_step = auto_show_tools.get(self.current_tool)
        if required_step is None:
            return False

        # 3-Punkt Kreis braucht kein dim_input - wird durch 3 Klicks definiert
        if self.current_tool == SketchTool.CIRCLE and self.circle_mode == 2:
            return False

        return self._tool_step >= required_step

    def _check_auto_show_dim_input(self):
        """
        Called when tool_step changes. Shows DimensionInput if appropriate.

        Phase 8: Smart Entry - Eliminates need for Tab key.
        """
        if not self._should_auto_show_dim_input():
            return

        # Mark this step as handled
        self._last_auto_show_step = self._tool_step

        # Use existing show method
        self._show_dimension_input()

        # Log the auto-show event
        if sketch_logger and is_enabled("sketch_input_logging"):
            tool_name = self.current_tool.name if self.current_tool else "UNKNOWN"
            fields = list(self.dim_input.fields.keys()) if hasattr(self.dim_input, 'fields') else []
            sketch_logger.log_show(tool_name, fields, source="auto")

    def _should_forward_to_dim_input(self, char: str) -> bool:
        """
        Checks if a typed character should be forwarded to DimensionInput.

        Phase 8: Direct Number Input - allows typing numbers without Tab.

        Args:
            char: The typed character

        Returns:
            True if character should be forwarded
        """
        # Only when tool is active and could show dimension input
        if self.current_tool == SketchTool.SELECT:
            return False

        # Numeric and formula-friendly characters.
        if not char or (char not in "0123456789.,+-*/()^" and not char.isalpha() and char != "_"):
            return False

        # If dim_input already visible and active, Qt handles input
        if self.dim_input_active and self.dim_input.isVisible():
            return False

        # Check if this tool supports dimension input at current step
        tools_with_dim_input = {
            SketchTool.LINE, SketchTool.RECTANGLE, SketchTool.RECTANGLE_CENTER,
            SketchTool.CIRCLE, SketchTool.ELLIPSE, SketchTool.POLYGON, SketchTool.SLOT, SketchTool.NUT, SketchTool.STAR,
            SketchTool.MOVE, SketchTool.COPY, SketchTool.ROTATE, SketchTool.SCALE,
            SketchTool.OFFSET, SketchTool.FILLET_2D, SketchTool.CHAMFER_2D,
            SketchTool.PATTERN_LINEAR, SketchTool.PATTERN_CIRCULAR,
        }

        if self.current_tool not in tools_with_dim_input:
            return False

        # For most tools, need at least step 1 (first point set)
        # For OFFSET, FILLET_2D, CHAMFER_2D: can type at step 0 (after selection)
        immediate_tools = {SketchTool.OFFSET, SketchTool.FILLET_2D, SketchTool.CHAMFER_2D}
        if self.current_tool in immediate_tools:
            return True

        return self._tool_step >= 1

    def _try_forward_to_dim_input(self, event) -> bool:
        """
        Tries to forward a key event to DimensionInput.

        Phase 8: Direct Number Input - shows panel and forwards character.

        Args:
            event: QKeyEvent

        Returns:
            True if event was handled
        """
        char = event.text()

        if not self._should_forward_to_dim_input(char):
            return False

        # Show dimension input if not visible
        if not self.dim_input.isVisible():
            self._show_dimension_input()

        # If still not visible (e.g., no fields for current tool), abort
        if not self.dim_input.isVisible():
            return False

        # Forward the character
        if self.dim_input.forward_key(char):
            self.dim_input_active = True

            # Log the forward event
            if sketch_logger and is_enabled("sketch_input_logging"):
                tool_name = self.current_tool.name if self.current_tool else "UNKNOWN"
                field_key = self.dim_input.get_active_field_key()
                sketch_logger.log_forward(tool_name, field_key or "unknown", char)

            self.request_update()
            return True

        return False

    # ========== End Phase 8: Smart Entry ==========

    def set_tool(self, tool):
        self._cancel_tool()
        if tool != SketchTool.SELECT:
            self._last_non_select_tool = tool
        self.current_tool = tool
        self._reset_overlap_cycle_state(clear_hover=(tool != SketchTool.SELECT))
        self.tool_changed.emit(tool)
        self._update_cursor()
        self._show_tool_hint()
        self._show_tool_options()  # Optionen-Popup
        self.request_update()
    
    def _show_tool_options(self):
        """Zeigt Optionen-Popup für Tools die Optionen haben"""
        tool = self.current_tool
        has_options = False
        
        # Rechteck: 2-Punkt vs Center
        if tool == SketchTool.RECTANGLE:
            self.tool_options.show_options(
                tr("RECTANGLE MODE"),
                "rect_mode",
                [("□", tr("2-Point")), ("◎", tr("Center"))],
                self.rect_mode
            )
            has_options = True
            
        # Kreis: Center vs 2-Punkt vs 3-Punkt
        elif tool == SketchTool.CIRCLE:
            self.tool_options.show_options(
                tr("CIRCLE TYPE"),
                "circle_mode",
                [("⊙", tr("Center")), ("⌀", tr("2-Point")), ("△", tr("3-Point"))],
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
                [("▴", "3"), ("◆", "4"), ("⬟", "5"), ("⬡", "6"), ("⯃", "8")],
                idx
            )
            has_options = True
            
        # Muttern-Aussparung: Grüüƒe M2-M14
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
        self.request_update()
    
    def _cancel_tool(self):
        self.tool_step = 0
        self._last_auto_show_step = -1  # Reset auto-show tracking for next operation
        self.tool_points.clear()
        self.tool_data.clear()
        self.preview_geometry = []
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

        # Direct edit reset
        self._direct_hover_handle = None
        self._direct_edit_dragging = False
        self._direct_edit_mode = None
        self._direct_edit_circle = None
        self._direct_edit_source = None
        self._direct_edit_drag_moved = False
        self._direct_edit_radius_constraints = []
        self._direct_edit_line = None
        self._direct_edit_line_context = None
        self._direct_edit_line_length_constraints = []
        self._direct_edit_live_solve = False
        self._direct_edit_pending_solve = False
        self._direct_edit_last_live_solve_ts = 0.0
        # W20 P1: Arc Direct Edit Cleanup
        self._direct_edit_arc = None
        self._direct_edit_start_start_angle = 0.0
        self._direct_edit_start_end_angle = 0.0

        # W26: ensure projection preview is cleared immediately on cancel.
        if self._last_projection_edge is not None:
            self._last_projection_edge = None
            self.projection_preview_cleared.emit()
        self.hovered_ref_edge = None
        
        # W16 Paket B: Kontext zurücksetzen und Navigation-Hint aktualisieren
        self._hint_context = 'sketch'
        self._show_tool_hint()

        # Constraint Highlight zurücksetzen
        self._clear_constraint_highlight()
        self._reset_overlap_cycle_state(clear_hover=False)

        self.request_update()

    def _highlight_constraint_entity(self, entity):
        """
        Hebt eine Entity für 2-Entity Constraint Auswahl hervor.
        Zeigt dem User visuell welches Element bereits ausgewÄhlt ist.
        """
        self._constraint_highlighted_entity = entity
        self.request_update()

    def _clear_constraint_highlight(self):
        """Entfernt das Constraint-Selection Highlight."""
        if self._constraint_highlighted_entity is not None:
            self._constraint_highlighted_entity = None
            self.request_update()

    def _find_polygon_driver_circle_for_line(self, line):
        """
        Findet den Konstruktionskreis, der ein regulÄres Polygon steuert.

        Heuristik:
        - Suche POINT_ON_CIRCLE Constraints für beide Linienendpunkte.
        - Der hÄufigste Kreis-Kandidat ist der Treiberkreis.
        """
        if line is None:
            return None

        endpoint_ids = {
            getattr(getattr(line, "start", None), "id", None),
            getattr(getattr(line, "end", None), "id", None),
        }
        endpoint_ids.discard(None)
        if not endpoint_ids:
            return None

        candidate_counts = {}
        for c in self.sketch.constraints:
            if c.type != ConstraintType.POINT_ON_CIRCLE or len(c.entities) < 2:
                continue

            point = c.entities[0]
            circle = c.entities[1]

            if not isinstance(circle, Circle2D):
                continue
            if getattr(point, "id", None) not in endpoint_ids:
                continue

            cid = id(circle)
            if cid not in candidate_counts:
                candidate_counts[cid] = [circle, 0]
            candidate_counts[cid][1] += 1

        if not candidate_counts:
            return None

        # Priorisiere Kreise, auf denen beide Endpunkte liegen (count >= 2).
        best_circle, best_count = max(candidate_counts.values(), key=lambda item: item[1])
        if best_count < 1:
            return None
        return best_circle

    def _collect_driver_circles_for_lines(self, lines):
        """Sammelt eindeutige Polygon-Treiberkreise aus einer Linienliste."""
        circles = []
        seen = set()
        for line in lines or []:
            circle = self._find_polygon_driver_circle_for_line(line)
            if circle is None:
                continue
            cid = id(circle)
            if cid in seen:
                continue
            seen.add(cid)
            circles.append(circle)
        return circles

    @staticmethod
    def _line_axis_orientation(line, tol: float = 1e-6):
        """Bestimmt, ob eine Linie horizontal/vertikal ist (oder None)."""
        if line is None:
            return None
        dx = float(line.end.x - line.start.x)
        dy = float(line.end.y - line.start.y)
        if abs(dy) <= max(tol, abs(dx) * 1e-6):
            return "horizontal"
        if abs(dx) <= max(tol, abs(dy) * 1e-6):
            return "vertical"
        return None

    def _lines_sharing_point(self, point, exclude_line=None):
        if point is None:
            return []
        out = []
        for line in self.sketch.lines:
            if line is exclude_line:
                continue
            if line.start is point or line.end is point:
                out.append(line)
        return out

    def _build_rectangle_edge_drag_context(self, edge_line):
        """
        Ermittelt Rectangle-Resize-Kontext für eine ausgewÄhlte Kante.
        Erwartet ein orthogonales 4-Linien-Rechteck mit geteilten Eckpunkten.
        """
        if not isinstance(edge_line, Line2D):
            return None
        if getattr(edge_line, "construction", False):
            return None

        orientation = self._line_axis_orientation(edge_line)
        if orientation not in ("horizontal", "vertical"):
            return None

        expected_adj = "vertical" if orientation == "horizontal" else "horizontal"

        def pick_adjacent(shared_point):
            candidates = []
            for line in self._lines_sharing_point(shared_point, exclude_line=edge_line):
                if getattr(line, "construction", False):
                    continue
                if self._line_axis_orientation(line) == expected_adj:
                    candidates.append(line)
            return candidates[0] if candidates else None

        adj_start = pick_adjacent(edge_line.start)
        adj_end = pick_adjacent(edge_line.end)
        if adj_start is None or adj_end is None or adj_start is adj_end:
            return None

        other_start = adj_start.end if adj_start.start is edge_line.start else adj_start.start
        other_end = adj_end.end if adj_end.start is edge_line.end else adj_end.start
        if other_start is None or other_end is None or other_start is other_end:
            return None

        opposite = None
        for line in self.sketch.lines:
            if line in (edge_line, adj_start, adj_end):
                continue
            if ((line.start is other_start and line.end is other_end) or
                (line.start is other_end and line.end is other_start)):
                opposite = line
                break

        if opposite is None:
            return None
        if self._line_axis_orientation(opposite) != orientation:
            return None

        target_length_lines = [adj_start, adj_end]
        length_constraints = [
            c for c in self.sketch.constraints
            if c.type == ConstraintType.LENGTH
            and any(line in getattr(c, "entities", ()) for line in target_length_lines)
        ]

        return {
            "edge": edge_line,
            "orientation": orientation,
            "adj_start": adj_start,
            "adj_end": adj_end,
            "opposite": opposite,
            "target_length_lines": target_length_lines,
            "length_constraints": length_constraints,
            "edge_start_x": float(edge_line.start.x),
            "edge_start_y": float(edge_line.start.y),
            "edge_end_x": float(edge_line.end.x),
            "edge_end_y": float(edge_line.end.y),
        }

    def _resolve_direct_edit_target_rect_edge(self):
        """
        Direct-Resize für Rechteckkante:
        - exakt eine selektierte Linie
        - Maus hovert diese Linie
        - Linie ist als Rechteckkante identifizierbar
        """
        if len(self.selected_lines) != 1:
            return None, None
        line = self.selected_lines[0]
        if self._last_hovered_entity is not line:
            return None, None
        context = self._build_rectangle_edge_drag_context(line)
        if not context:
            return None, None
        return line, context

    def _build_line_move_drag_context(self, line):
        """
        Kontext für direktes Verschieben einer einzelnen Linie.
        EnthÄlt Startkoordinaten und visuell abhÄngige Geometrie für Dirty-Rect-Updates.
        """
        if not isinstance(line, Line2D):
            return None

        points = [line.start, line.end]
        connected_entities = []
        seen = set()

        def add_entity(entity):
            if entity is None:
                return
            eid = id(entity)
            if eid in seen:
                return
            seen.add(eid)
            connected_entities.append(entity)

        add_entity(line)
        for other in self._lines_sharing_point(line.start, exclude_line=line):
            add_entity(other)
        for other in self._lines_sharing_point(line.end, exclude_line=line):
            add_entity(other)
        for circle in self.sketch.circles:
            if circle.center in points:
                add_entity(circle)
        for arc in self.sketch.arcs:
            if arc.center in points:
                add_entity(arc)

        constraints = [
            c for c in self.sketch.constraints
            if line in getattr(c, "entities", ())
            or line.start in getattr(c, "entities", ())
            or line.end in getattr(c, "entities", ())
        ]

        return {
            "line": line,
            "start_start_x": float(line.start.x),
            "start_start_y": float(line.start.y),
            "start_end_x": float(line.end.x),
            "start_end_y": float(line.end.y),
            "connected_entities": connected_entities,
            "constraints": constraints,
        }

    def _resolve_direct_edit_target_line(self):
        """
        Ermittelt eine frei verschiebbare Linie für Direct-Edit.
        Rechteckkanten (Resize-Modus) und Polygon-Treiberlinien werden hier bewusst
        ausgeschlossen, um deren Spezialverhalten nicht zu überschreiben.
        """
        line = None
        hovered = self._last_hovered_entity

        if isinstance(hovered, Line2D):
            line = hovered
        elif len(self.selected_lines) == 1:
            line = self.selected_lines[0]

        if not isinstance(line, Line2D):
            return None, None

        # Ellipsen sind als Linienbündel modelliert; freie Linien-Handles darauf sperren.
        if getattr(line, "_ellipse_bundle", None) is not None:
            return None, None

        # Polygon-Linien bleiben im Circle/Polygon-Direct-Edit Pfad.
        if self._find_polygon_driver_circle_for_line(line) is not None:
            return None, None

        # Rechteckkanten nur über den dedizierten line_edge Resize-Modus bearbeiten.
        if self._build_rectangle_edge_drag_context(line):
            return None, None

        context = self._build_line_move_drag_context(line)
        if not context:
            return None, None
        return line, context

    def _resolve_direct_edit_target_circle(self):
        """
        Ermittelt den aktuell bearbeitbaren Kreis:
        - Direkt gehoverter Kreis
        - Polygon-Treiberkreis unter gehoverter Linie
        - Fallback auf Selektion (ein Kreis oder eine Polygon-Linie)
        """
        hovered = self._last_hovered_entity

        if isinstance(hovered, Circle2D):
            return hovered, "circle"

        if isinstance(hovered, Line2D):
            poly_circle = self._find_polygon_driver_circle_for_line(hovered)
            if poly_circle is not None:
                return poly_circle, "polygon"

        if len(self.selected_circles) == 1:
            return self.selected_circles[0], "circle"

        if len(self.selected_lines) == 1:
            poly_circle = self._find_polygon_driver_circle_for_line(self.selected_lines[0])
            if poly_circle is not None:
                return poly_circle, "polygon"

        return None, None

    def _resolve_direct_edit_target_arc(self):
        """
        W32: Ermittelt den aktuell bearbeitbaren Arc mit verbessertem Handle-Management.
        
        Returns:
            Tuple (Arc2D, source) oder (None, None)
        """
        # Wenn wir gerade draggen, behalte den aktuellen Arc bei
        if self._direct_edit_dragging and self._direct_edit_arc is not None:
            return self._direct_edit_arc, "arc"
        
        hovered = self._last_hovered_entity
        
        if isinstance(hovered, Arc2D):
            return hovered, "arc"
        
        if len(self.selected_arcs) == 1:
            return self.selected_arcs[0], "arc"
        
        return None, None

    def _resolve_direct_edit_target_ellipse(self):
        """
        Ermittelt die aktuell bearbeitbare Ellipse.
        Unterstützt auch Test-Harness-Objekte via _test_selected_ellipse.
        """
        hovered = self._last_hovered_entity

        if isinstance(hovered, Ellipse2D):
            return hovered, "ellipse"

        if len(self.selected_ellipses) == 1:
            return self.selected_ellipses[0], "ellipse"

        test_sel = getattr(self, "_test_selected_ellipse", None)
        if isinstance(test_sel, Ellipse2D):
            return test_sel, "ellipse"

        return None, None

    def _resolve_direct_edit_target_polygon(self):
        """
        Ermittelt das aktuell bearbeitbare Polygon.
        Unterstützt auch Test-Harness-Objekte via _test_selected_polygon.
        """
        hovered = self._last_hovered_entity

        if isinstance(hovered, Polygon2D):
            return hovered, "polygon"

        if len(self.selected_polygons) == 1:
            return self.selected_polygons[0], "polygon"

        test_sel = getattr(self, "_test_selected_polygon", None)
        if isinstance(test_sel, Polygon2D):
            return test_sel, "polygon"

        return None, None

    def _resolve_direct_edit_target_slot(self):
        """
        Ermittelt das aktuell bearbeitbare Slot.
        Slots werden über ihre Center-Line identifiziert (Markierung _slot_center_line).
        """
        # Check hovered entity first
        hovered = self._last_hovered_entity
        if isinstance(hovered, Line2D):
            # Check if this line is a slot center line
            if getattr(hovered, '_slot_center_line', False):
                return hovered, "slot"
            # Check if this line is part of a slot (top/bottom lines)
            if hasattr(hovered, '_slot_parent_center_line'):
                parent = hovered._slot_parent_center_line
                if parent is not None:
                    return parent, "slot"

        # Check selected lines for slot components
        for line in getattr(self, 'selected_lines', []):
            if getattr(line, '_slot_center_line', False):
                return line, "slot"
            if hasattr(line, '_slot_parent_center_line'):
                parent = line._slot_parent_center_line
                if parent is not None:
                    return parent, "slot"

        return None, None

    def _get_direct_edit_handles_world(self):
        """
        Liefert Handle-Daten für Direct Manipulation in Weltkoordinaten.

        Returns:
            Dict mit circle, source, center, radius_point, angle oder None.
        """
        if self.current_tool != SketchTool.SELECT:
            return None

        if self._direct_edit_dragging and self._direct_edit_circle is not None:
            circle = self._direct_edit_circle
            source = self._direct_edit_source
            if self._direct_edit_mode == "radius":
                angle = self._direct_edit_anchor_angle
            else:
                dx = self.mouse_world.x() - circle.center.x
                dy = self.mouse_world.y() - circle.center.y
                angle = math.atan2(dy, dx) if (abs(dx) > 1e-9 or abs(dy) > 1e-9) else 0.0
        else:
            circle, source = self._resolve_direct_edit_target_circle()
            if circle is None:
                return None
            dx = self.mouse_world.x() - circle.center.x
            dy = self.mouse_world.y() - circle.center.y
            angle = math.atan2(dy, dx) if (abs(dx) > 1e-9 or abs(dy) > 1e-9) else 0.0

        center = QPointF(circle.center.x, circle.center.y)
        radius_point = QPointF(
            circle.center.x + circle.radius * math.cos(angle),
            circle.center.y + circle.radius * math.sin(angle),
        )

        return {
            "circle": circle,
            "source": source,
            "center": center,
            "radius_point": radius_point,
            "angle": angle,
        }

    def _pick_direct_edit_handle(self, world_pos):
        """
        Hit-Test für Direct-Edit:
        - Circle/Polygon: Center- und Radius-Handle
        - Rectangle: selektierte Kante direkt ziehen
        - Line: freie Linie per Drag verschieben

        Returns:
            Dict mit mode + Handle-Daten oder None.
        """
        handles = self._get_direct_edit_handles_world()
        hit_radius = max(8.0 / self.view_scale, (self.snap_radius / self.view_scale) * 0.55)

        if handles:
            circle = handles["circle"]
            center = handles["center"]
            radius_point = handles["radius_point"]

            d_center = math.hypot(world_pos.x() - center.x(), world_pos.y() - center.y())
            if d_center <= hit_radius:
                return {**handles, "kind": "circle", "mode": "center"}

            d_handle = math.hypot(world_pos.x() - radius_point.x(), world_pos.y() - radius_point.y())
            if d_handle <= hit_radius:
                return {**handles, "kind": "circle", "mode": "radius"}

            # Komfort: Klick direkt auf Kreisbahn startet Radius-Drag.
            d_ring = abs(math.hypot(world_pos.x() - center.x(), world_pos.y() - center.y()) - circle.radius)
            if d_ring <= hit_radius * 0.75:
                return {**handles, "kind": "circle", "mode": "radius"}

        # W30 AP1: Line Endpoint and Midpoint Handles (Direct Manipulation Parity with Circle)
        hovered = self._last_hovered_entity
        if isinstance(hovered, Line2D) and not getattr(hovered, "construction", False):
            if getattr(hovered, "_ellipse_bundle", None) is not None:
                hovered = None
        if isinstance(hovered, Line2D) and not getattr(hovered, "construction", False):
            # Check if this line is part of a rectangle (skip - handled by rect edge logic)
            rect_context = self._build_rectangle_edge_drag_context(hovered)
            if rect_context is None:
                # Not a rectangle edge - add endpoint/midpoint handles
                start_point = QPointF(hovered.start.x, hovered.start.y)
                end_point = QPointF(hovered.end.x, hovered.end.y)
                midpoint = QPointF((hovered.start.x + hovered.end.x) / 2, (hovered.start.y + hovered.end.y) / 2)

                # Start Endpoint Handle (yellow circle)
                d_start = math.hypot(world_pos.x() - start_point.x(), world_pos.y() - start_point.y())
                if d_start <= hit_radius:
                    return {
                        "kind": "line",
                        "mode": "endpoint_start",
                        "line": hovered,
                        "source": "line",
                        "endpoint": "start",
                        "start_pos": start_point,
                    }

                # End Endpoint Handle (yellow circle)
                d_end = math.hypot(world_pos.x() - end_point.x(), world_pos.y() - end_point.y())
                if d_end <= hit_radius:
                    return {
                        "kind": "line",
                        "mode": "endpoint_end",
                        "line": hovered,
                        "source": "line",
                        "endpoint": "end",
                        "end_pos": end_point,
                    }

                # Midpoint Handle (green square - like circle center)
                d_midpoint = math.hypot(world_pos.x() - midpoint.x(), world_pos.y() - midpoint.y())
                if d_midpoint <= hit_radius:
                    return {
                        "kind": "line",
                        "mode": "midpoint",
                        "line": hovered,
                        "source": "line",
                        "midpoint": midpoint,
                    }

        line, context = self._resolve_direct_edit_target_rect_edge()
        if line is not None and context is not None:
            dist = line.distance_to_point(Point2D(world_pos.x(), world_pos.y()))
            if dist <= hit_radius:
                return {
                    "kind": "line",
                    "mode": "line_edge",
                    "line": line,
                    "source": "rectangle",
                    "orientation": context["orientation"],
                    "context": context,
                }

        line, context = self._resolve_direct_edit_target_line()
        if line is not None and context is not None:
            dist = line.distance_to_point(Point2D(world_pos.x(), world_pos.y()))
            if dist <= hit_radius:
                return {
                    "kind": "line",
                    "mode": "line_move",
                    "line": line,
                    "source": "line",
                    "context": context,
                }

        # W20 P1: Arc Direct Manipulation Handles
        arc, arc_source = self._resolve_direct_edit_target_arc()
        if arc is not None:
            center = QPointF(arc.center.x, arc.center.y)
            
            # Center Handle
            d_center = math.hypot(world_pos.x() - center.x(), world_pos.y() - center.y())
            if d_center <= hit_radius:
                return {
                    "kind": "arc",
                    "mode": "center",
                    "arc": arc,
                    "source": arc_source,
                    "center": center,
                }
            
            # Radius Handle (auf dem Arc)
            mid_angle = (arc.start_angle + arc.end_angle) / 2
            radius_point = QPointF(
                arc.center.x + arc.radius * math.cos(math.radians(mid_angle)),
                arc.center.y + arc.radius * math.sin(math.radians(mid_angle)),
            )
            d_radius = math.hypot(world_pos.x() - radius_point.x(), world_pos.y() - radius_point.y())
            if d_radius <= hit_radius:
                return {
                    "kind": "arc",
                    "mode": "radius",
                    "arc": arc,
                    "source": arc_source,
                    "center": center,
                    "radius_point": radius_point,
                    "angle": mid_angle,
                }
            
            # Start Angle Handle
            start_point = QPointF(
                arc.center.x + arc.radius * math.cos(math.radians(arc.start_angle)),
                arc.center.y + arc.radius * math.sin(math.radians(arc.start_angle)),
            )
            d_start = math.hypot(world_pos.x() - start_point.x(), world_pos.y() - start_point.y())
            if d_start <= hit_radius:
                return {
                    "kind": "arc",
                    "mode": "start_angle",
                    "arc": arc,
                    "source": arc_source,
                    "center": center,
                    "angle_point": start_point,
                }
            
            # End Angle Handle
            end_point = QPointF(
                arc.center.x + arc.radius * math.cos(math.radians(arc.end_angle)),
                arc.center.y + arc.radius * math.sin(math.radians(arc.end_angle)),
            )
            d_end = math.hypot(world_pos.x() - end_point.x(), world_pos.y() - end_point.y())
            if d_end <= hit_radius:
                return {
                    "kind": "arc",
                    "mode": "end_angle",
                    "arc": arc,
                    "source": arc_source,
                    "center": center,
                    "angle_point": end_point,
                }
            
            # Komfort: Klick auf Arc-Bahn startet Radius-Drag
            d_to_center = math.hypot(world_pos.x() - center.x(), world_pos.y() - center.y())
            if abs(d_to_center - arc.radius) <= hit_radius * 0.75:
                angle = math.degrees(math.atan2(world_pos.y() - center.y(), world_pos.x() - center.x()))
                return {
                    "kind": "arc",
                    "mode": "radius",
                    "arc": arc,
                    "source": arc_source,
                    "center": center,
                    "angle": angle,
                }

        # W25: Ellipse Direct Manipulation Handles
        # W30 AP4: Simplified - Y-radius and rotation only during active edit
        ellipse, ellipse_source = self._resolve_direct_edit_target_ellipse()
        if ellipse is not None:
            center = QPointF(ellipse.center.x, ellipse.center.y)
            rotation_rad = math.radians(float(getattr(ellipse, "rotation", 0.0)))
            ux, uy = math.cos(rotation_rad), math.sin(rotation_rad)
            vx, vy = -math.sin(rotation_rad), math.cos(rotation_rad)

            rx = max(0.01, float(getattr(ellipse, "radius_x", 0.01)))
            ry = max(0.01, float(getattr(ellipse, "radius_y", 0.01)))

            x_handle = QPointF(center.x() + rx * ux, center.y() + rx * uy)
            y_handle = QPointF(center.x() + ry * vx, center.y() + ry * vy)
            rot_handle = QPointF(center.x() + (rx * 1.2) * ux, center.y() + (rx * 1.2) * uy)

            # Center handle always available
            if math.hypot(world_pos.x() - center.x(), world_pos.y() - center.y()) <= hit_radius:
                return {"kind": "ellipse", "mode": "center", "ellipse": ellipse, "source": ellipse_source}

            # Primary X-radius handle always available
            if math.hypot(world_pos.x() - x_handle.x(), world_pos.y() - x_handle.y()) <= hit_radius:
                return {"kind": "ellipse", "mode": "radius_x", "ellipse": ellipse, "source": ellipse_source}

            # W30 AP4: Y-radius and rotation only during active editing (simplified visual)
            is_active_edit = self._direct_edit_dragging and self._direct_edit_ellipse is ellipse
            if is_active_edit:
                if math.hypot(world_pos.x() - y_handle.x(), world_pos.y() - y_handle.y()) <= hit_radius:
                    return {"kind": "ellipse", "mode": "radius_y", "ellipse": ellipse, "source": ellipse_source}
                if math.hypot(world_pos.x() - rot_handle.x(), world_pos.y() - rot_handle.y()) <= hit_radius:
                    return {"kind": "ellipse", "mode": "rotation", "ellipse": ellipse, "source": ellipse_source}

        # W25: Polygon Direct Manipulation Handles (Vertex)
        # W30 AP4: Only pickable when polygon is hovered or selected
        polygon, polygon_source = self._resolve_direct_edit_target_polygon()
        if polygon is not None:
            # Only check vertices if polygon is being hovered or is selected
            is_selected = polygon in getattr(self, 'selected_polygons', [])
            is_hovered = isinstance(self._last_hovered_entity, type(polygon)) and self._last_hovered_entity is polygon

            if is_selected or is_hovered:
                # W34: Check for center handle first (before vertex handles)
                # Calculate centroid from polygon points
                points = getattr(polygon, "points", [])
                if points and len(points) >= 3:
                    cx = sum(pt.x for pt in points) / len(points)
                    cy = sum(pt.y for pt in points) / len(points)
                    d_center = math.hypot(world_pos.x() - cx, world_pos.y() - cy)
                    if d_center <= hit_radius:
                        return {
                            "kind": "polygon",
                            "mode": "center",
                            "polygon": polygon,
                            "source": polygon_source,
                            "center": QPointF(cx, cy),
                        }

                # Vertex handles (existing functionality)
                for idx, pt in enumerate(points):
                    if math.hypot(world_pos.x() - pt.x, world_pos.y() - pt.y) <= hit_radius:
                        return {
                            "kind": "polygon",
                            "mode": "vertex",
                            "polygon": polygon,
                            "source": polygon_source,
                            "vertex_idx": idx,
                        }

        # W34: Slot Direct Edit Handles
        slot, slot_source = self._resolve_direct_edit_target_slot()
        if slot is not None:
            # Center line midpoint handle (move entire slot)
            midpoint = QPointF((slot.start.x + slot.end.x) / 2, (slot.start.y + slot.end.y) / 2)
            d_midpoint = math.hypot(world_pos.x() - midpoint.x(), world_pos.y() - midpoint.y())
            if d_midpoint <= hit_radius:
                return {
                    "kind": "slot",
                    "mode": "center",
                    "slot": slot,
                    "source": slot_source,
                    "midpoint": midpoint,
                }

            # Length handles (on center line endpoints)
            d_start = math.hypot(world_pos.x() - slot.start.x, world_pos.y() - slot.start.y)
            if d_start <= hit_radius:
                return {
                    "kind": "slot",
                    "mode": "length_start",
                    "slot": slot,
                    "source": slot_source,
                }

            d_end = math.hypot(world_pos.x() - slot.end.x, world_pos.y() - slot.end.y)
            if d_end <= hit_radius:
                return {
                    "kind": "slot",
                    "mode": "length_end",
                    "slot": slot,
                    "source": slot_source,
                }

            # Radius handle (find on arc caps - check distance to arc edges)
            for arc in self.sketch.arcs:
                if hasattr(arc, '_slot_arc') and arc._slot_arc:
                    # Check distance to arc edge
                    d_arc_center = math.hypot(world_pos.x() - arc.center.x, world_pos.y() - arc.center.y)
                    d_from_radius = abs(d_arc_center - arc.radius)
                    if d_from_radius <= hit_radius * 0.75:
                        return {
                            "kind": "slot",
                            "mode": "radius",
                            "slot": slot,
                            "arc": arc,
                            "source": slot_source,
                        }

        return None

    def _start_direct_edit_drag(self, handle_hit):
        """Startet Circle/Polygon/Rectangle/Line-Direct-Manipulation."""
        if not handle_hit:
            return

        kind = handle_hit.get("kind", "circle")
        mode = handle_hit["mode"]

        self._save_undo()

        self._direct_edit_dragging = True
        self._direct_edit_mode = mode
        self._direct_edit_source = handle_hit.get("source")
        self._direct_edit_start_pos = QPointF(self.mouse_world.x(), self.mouse_world.y())
        self._direct_edit_drag_moved = False
        self._direct_edit_last_live_solve_ts = 0.0
        self._direct_edit_pending_solve = False
        
        # W16 Paket B: Kontext für Navigation-Hints aktualisieren
        self._hint_context = 'direct_edit'
        self._show_tool_hint()  # Sofort Navigation-Hint aktualisieren

        # Reset mode-specific caches
        self._direct_edit_circle = None
        self._direct_edit_radius_constraints = []
        self._direct_edit_line = None
        self._direct_edit_line_context = None
        self._direct_edit_line_length_constraints = []
        self._direct_edit_arc = None
        self._direct_edit_start_start_angle = 0.0
        self._direct_edit_start_end_angle = 0.0
        self._direct_edit_ellipse = None
        self._direct_edit_start_radius_x = 0.0
        self._direct_edit_start_radius_y = 0.0
        self._direct_edit_start_rotation = 0.0
        self._direct_edit_polygon = None
        self._direct_edit_polygon_vertex_idx = -1
        self._direct_edit_polygon_vertex_start = QPointF()
        # W34: Polygon center drag variables
        self._direct_edit_polygon_driver_circle = None
        self._direct_edit_polygon_start_center = QPointF()
        self._direct_edit_start_circle_center = QPointF()
        self._direct_edit_polygon_point_starts = []  # W34-fix: start positions of all polygon points
        # W34: Slot drag variables
        self._direct_edit_slot = None
        self._direct_edit_slot_arc = None
        self._direct_edit_slot_start_center = QPointF()
        self._direct_edit_slot_start_length = 0.0
        self._direct_edit_slot_start_radius = 0.0

        if kind == "line" and mode in ("line_edge", "line_move"):
            line = handle_hit.get("line")
            context = handle_hit.get("context")
            if line is None or context is None:
                self._direct_edit_dragging = False
                return

            self._direct_edit_line = line
            self._direct_edit_line_context = context
            self._direct_edit_line_length_constraints = list(context.get("length_constraints", []))
            self._direct_edit_live_solve = self._direct_edit_requires_live_solve(
                mode=mode,
                source=self._direct_edit_source,
                line_context=context,
            )

            if line not in self.selected_lines:
                self._clear_selection()
                self.selected_lines = [line]

            self.setCursor(Qt.ClosedHandCursor)
            self.request_update()
            return

        # W30 AP1: Line Endpoint and Midpoint Direct Edit (Parity with Circle)
        # W33 EPIC AA4: Live-Solve-Logik fuer Line-Endpoints
        if kind == "line" and mode in ("endpoint_start", "endpoint_end", "midpoint"):
            line = handle_hit.get("line")
            if line is None:
                self._direct_edit_dragging = False
                return

            self._direct_edit_line = line
            endpoint = handle_hit.get("endpoint")

            if mode == "endpoint_start":
                # Store initial endpoint position
                self._direct_edit_endpoint_start = QPointF(float(line.start.x), float(line.start.y))
                self._direct_edit_endpoint_other = QPointF(float(line.end.x), float(line.end.y))
                self._direct_edit_active_endpoint = "start"
                self.setCursor(Qt.SizeAllCursor)
            elif mode == "endpoint_end":
                # Store initial endpoint position
                self._direct_edit_endpoint_start = QPointF(float(line.end.x), float(line.end.y))
                self._direct_edit_endpoint_other = QPointF(float(line.start.x), float(line.start.y))
                self._direct_edit_active_endpoint = "end"
                self.setCursor(Qt.SizeAllCursor)
            elif mode == "midpoint":
                # Move entire line via midpoint (like circle center)
                context = self._build_line_move_drag_context(line)
                self._direct_edit_line_context = context
                self._direct_edit_endpoint_start = QPointF(float(line.start.x), float(line.start.y))
                self._direct_edit_endpoint_end = QPointF(float(line.end.x), float(line.end.y))
                self.setCursor(Qt.ClosedHandCursor)
                # W33 EPIC AA4: Live-Solve fuer Midpoint-Drag wenn Constraints existieren
                self._direct_edit_live_solve = self._direct_edit_requires_live_solve(
                    mode="line_move",
                    source="line",
                    line_context=context,
                )

            if line not in self.selected_lines:
                self._clear_selection()
                self.selected_lines = [line]

            self.request_update()
            return

        # W20 P1: Arc Direct Edit
        if kind == "arc":
            arc = handle_hit.get("arc")
            if arc is None:
                self._direct_edit_dragging = False
                return
            
            # Store arc for dragging
            self._direct_edit_arc = arc
            self._direct_edit_start_center = QPointF(arc.center.x, arc.center.y)
            self._direct_edit_start_radius = float(arc.radius)
            self._direct_edit_start_start_angle = float(arc.start_angle)
            self._direct_edit_start_end_angle = float(arc.end_angle)
            
            if mode == "center":
                self.setCursor(Qt.ClosedHandCursor)
            elif mode == "radius":
                self._direct_edit_anchor_angle = math.radians(handle_hit.get("angle", 0.0))
                self.setCursor(Qt.SizeFDiagCursor)
            elif mode in ("start_angle", "end_angle"):
                self.setCursor(Qt.SizeAllCursor)
            
            if arc not in self.selected_arcs:
                self._clear_selection()
                self.selected_arcs = [arc]
            
            self.request_update()
            return

        # Ellipse direct edit
        if kind == "ellipse":
            ellipse = handle_hit.get("ellipse")
            if ellipse is None:
                self._direct_edit_dragging = False
                return

            self._direct_edit_ellipse = ellipse
            self._direct_edit_start_center = QPointF(float(ellipse.center.x), float(ellipse.center.y))
            self._direct_edit_start_radius_x = float(getattr(ellipse, "radius_x", 0.0))
            self._direct_edit_start_radius_y = float(getattr(ellipse, "radius_y", 0.0))
            self._direct_edit_start_rotation = float(getattr(ellipse, "rotation", 0.0))

            if ellipse not in self.selected_ellipses:
                self._clear_selection()
                self.selected_ellipses = [ellipse]

            self.setCursor(Qt.ClosedHandCursor)
            self.request_update()
            return

        # W34: Polygon Center Direct Edit (Move entire polygon via driver circle)
        if kind == "polygon" and mode == "center":
            polygon = handle_hit.get("polygon")
            if polygon is None:
                self._direct_edit_dragging = False
                return

            self._direct_edit_polygon = polygon
            center_handle = handle_hit.get("center", QPointF())
            self._direct_edit_polygon_start_center = center_handle

            # Find driver circle for this polygon
            points = getattr(polygon, "points", [])
            driver_circle = None
            if points:
                # Try to find the driver circle through the polygon lines
                for line in self.sketch.lines:
                    if line.start in points or line.end in points:
                        driver_circle = self._find_polygon_driver_circle_for_line(line)
                        if driver_circle is not None:
                            self._direct_edit_polygon_driver_circle = driver_circle
                            self._direct_edit_start_circle_center = QPointF(
                                float(driver_circle.center.x),
                                float(driver_circle.center.y)
                            )
                            # W34-fix: save start positions of all polygon points
                            self._direct_edit_polygon_point_starts = [
                                QPointF(float(p.x), float(p.y)) for p in points
                            ]
                            break

            if polygon not in self.selected_polygons:
                self._clear_selection()
                self.selected_polygons = [polygon]

            self.setCursor(Qt.ClosedHandCursor)
            self.request_update()
            return

        # Polygon direct edit
        if kind == "polygon" and mode == "vertex":
            polygon = handle_hit.get("polygon")
            vertex_idx = int(handle_hit.get("vertex_idx", -1))
            points = getattr(polygon, "points", None)
            if polygon is None or points is None or vertex_idx < 0 or vertex_idx >= len(points):
                self._direct_edit_dragging = False
                return

            self._direct_edit_polygon = polygon
            self._direct_edit_polygon_vertex_idx = vertex_idx
            pt = points[vertex_idx]
            self._direct_edit_polygon_vertex_start = QPointF(float(pt.x), float(pt.y))

            if polygon not in self.selected_polygons:
                self._clear_selection()
                self.selected_polygons = [polygon]

            self.setCursor(Qt.ClosedHandCursor)
            self.request_update()
            return

        # W34: Slot Direct Edit
        if kind == "slot":
            slot = handle_hit.get("slot")
            if slot is None:
                self._direct_edit_dragging = False
                return

            self._direct_edit_slot = slot
            self._direct_edit_slot_start_center = QPointF(
                (slot.start.x + slot.end.x) / 2,
                (slot.start.y + slot.end.y) / 2
            )

            # Calculate initial slot length
            dx = slot.end.x - slot.start.x
            dy = slot.end.y - slot.start.y
            self._direct_edit_slot_start_length = math.hypot(dx, dy)

            # Find arc caps for radius editing
            if mode == "radius":
                arc = handle_hit.get("arc")
                if arc is not None:
                    self._direct_edit_slot_arc = arc
                    self._direct_edit_slot_start_radius = float(arc.radius)

            if slot not in self.selected_lines:
                self._clear_selection()
                self.selected_lines = [slot]

            if mode == "center":
                self.setCursor(Qt.ClosedHandCursor)
            elif mode in ("length_start", "length_end"):
                self.setCursor(Qt.SizeHorCursor)
            elif mode == "radius":
                self.setCursor(Qt.SizeVerCursor)

            self.request_update()
            return

        # Default: Circle/Polygon direct edit
        circle = handle_hit.get("circle")
        if circle is None:
            self._direct_edit_dragging = False
            return

        self._direct_edit_circle = circle
        self._direct_edit_start_center = QPointF(circle.center.x, circle.center.y)
        self._direct_edit_start_radius = float(circle.radius)
        self._direct_edit_anchor_angle = float(handle_hit.get("angle", 0.0))
        self._direct_edit_live_solve = self._direct_edit_requires_live_solve(
            circle=circle,
            source=self._direct_edit_source,
            mode=mode,
        )
        self._direct_edit_radius_constraints = [
            c for c in self.sketch.constraints
            if (circle in getattr(c, "entities", ()))
            and c.type in (ConstraintType.RADIUS, ConstraintType.DIAMETER)
        ]

        if circle not in self.selected_circles:
            self._clear_selection()
            self.selected_circles = [circle]

        self.setCursor(Qt.ClosedHandCursor)
        self.request_update()

    def _direct_edit_requires_live_solve(self, circle=None, source=None, mode=None, line_context=None) -> bool:
        """
        Live-Solve nur dort, wo es für visuelles Follow-Up nütig ist.
        """
        if mode == "line_edge":
            if not line_context:
                return False
            allowed_types = {
                ConstraintType.HORIZONTAL,
                ConstraintType.VERTICAL,
                ConstraintType.COINCIDENT,
                ConstraintType.LENGTH,
            }
            involved_lines = [
                line_context.get("edge"),
                line_context.get("adj_start"),
                line_context.get("adj_end"),
                line_context.get("opposite"),
            ]
            involved_lines = [line for line in involved_lines if line is not None]
            involved_line_ids = {id(line) for line in involved_lines}

            involved_points = []
            for line in involved_lines:
                start = getattr(line, "start", None)
                end = getattr(line, "end", None)
                if start is not None:
                    involved_points.append(start)
                if end is not None:
                    involved_points.append(end)
            involved_point_ids = {id(point) for point in involved_points}

            for c in self.sketch.constraints:
                entities = tuple(getattr(c, "entities", ()) or ())
                entity_ids = {id(entity) for entity in entities}
                if not entity_ids.intersection(involved_line_ids) and not entity_ids.intersection(involved_point_ids):
                    continue
                if c.type in allowed_types:
                    continue
                return True
            return False

        if mode == "line_move":
            if not line_context:
                return False
            line = line_context.get("line")
            if line is None:
                return False
            line_points = [getattr(line, "start", None), getattr(line, "end", None)]
            line_points = [point for point in line_points if point is not None]
            line_point_ids = {id(point) for point in line_points}
            allowed_types = {
                ConstraintType.HORIZONTAL,
                ConstraintType.VERTICAL,
                ConstraintType.LENGTH,
                ConstraintType.PARALLEL,
                ConstraintType.PERPENDICULAR,
                ConstraintType.COLLINEAR,
                ConstraintType.EQUAL_LENGTH,
                ConstraintType.COINCIDENT,
            }
            for c in self.sketch.constraints:
                entities = tuple(getattr(c, "entities", ()) or ())
                entity_ids = {id(entity) for entity in entities}
                if id(line) not in entity_ids and not entity_ids.intersection(line_point_ids):
                    continue
                if c.type in allowed_types:
                    continue
                return True
            return False

        if circle is None:
            return False

        if source == "polygon":
            return True

        for c in self.sketch.constraints:
            entities = getattr(c, "entities", ())
            if circle not in entities and circle.center not in entities:
                continue
            if c.type in (ConstraintType.RADIUS, ConstraintType.DIAMETER):
                continue
            return True
        return False

    def _maybe_live_solve_during_direct_drag(self):
        """Gedrosseltes Live-Solve für komplexe AbhÄngigkeiten beim Drag."""
        if not self._direct_edit_live_solve:
            return

        now = time.perf_counter()
        if (now - self._direct_edit_last_live_solve_ts) < self._direct_edit_live_solve_interval_s:
            self._direct_edit_pending_solve = True
            return

        try:
            self.sketch.solve()
        except Exception as e:
            logger.debug(f"Direct drag solve failed: {e}")

        self._direct_edit_last_live_solve_ts = now
        self._direct_edit_pending_solve = False

    def _update_circle_radius_constraint(self, circle, new_radius: float):
        """Synchronisiert Radius-Änderungen mit vorhandenen Radius/Diameter-Constraints."""
        found = False
        constraints = self._direct_edit_radius_constraints
        if not isinstance(constraints, list):
            constraints = []
        if not constraints:
            constraints = [
                c for c in self.sketch.constraints
                if (circle in getattr(c, "entities", ()))
                and c.type in (ConstraintType.RADIUS, ConstraintType.DIAMETER)
            ]
            self._direct_edit_radius_constraints = constraints

        for c in constraints:
            if c.type == ConstraintType.RADIUS:
                c.value = float(new_radius)
                found = True
            elif c.type == ConstraintType.DIAMETER:
                c.value = float(new_radius) * 2.0
                found = True

        circle.radius = float(new_radius)
        if not found:
            created = self.sketch.add_radius(circle, float(new_radius))
            if created is not None:
                self._direct_edit_radius_constraints.append(created)

    def _line_drag_dirty_rect(self, context) -> QRectF:
        lines = [
            context.get("edge"),
            context.get("adj_start"),
            context.get("adj_end"),
            context.get("opposite"),
        ]
        rect = QRectF()
        for line in lines:
            if line is None:
                continue
            bbox = self._get_entity_bbox(line)
            if rect.isEmpty():
                rect = QRectF(bbox)
            else:
                rect = rect.united(bbox)
        return rect.adjusted(-8.0, -8.0, 8.0, 8.0)

    def _line_move_dirty_rect(self, context) -> QRectF:
        entities = context.get("connected_entities", [])
        rect = QRectF()
        for entity in entities:
            bbox = self._get_entity_bbox(entity)
            if rect.isEmpty():
                rect = QRectF(bbox)
            else:
                rect = rect.united(bbox)
        return rect.adjusted(-8.0, -8.0, 8.0, 8.0)

    def _update_line_edge_length_constraints(self, context, new_length: float):
        constraints = context.get("length_constraints")
        if not isinstance(constraints, list):
            constraints = []

        if not constraints:
            target_lines = context.get("target_length_lines", [])
            if target_lines:
                created = self.sketch.add_length(target_lines[0], float(new_length))
                if created is not None:
                    constraints.append(created)

        for c in constraints:
            if c.type == ConstraintType.LENGTH:
                c.value = float(new_length)

        context["length_constraints"] = constraints
        self._direct_edit_line_length_constraints = constraints

    def _apply_direct_edit_line_drag(self, world_pos, axis_lock=False):
        context = self._direct_edit_line_context
        if not context:
            return

        edge = context.get("edge")
        adj_start = context.get("adj_start")
        adj_end = context.get("adj_end")
        orientation = context.get("orientation")
        if edge is None or adj_start is None or adj_end is None:
            return

        dirty_old = self._line_drag_dirty_rect(context)

        if orientation == "horizontal":
            dy = world_pos.y() - self._direct_edit_start_pos.y()
            edge.start.y = context.get("edge_start_y", float(edge.start.y)) + dy
            edge.end.y = context.get("edge_end_y", float(edge.end.y)) + dy
        elif orientation == "vertical":
            dx = world_pos.x() - self._direct_edit_start_pos.x()
            edge.start.x = context.get("edge_start_x", float(edge.start.x)) + dx
            edge.end.x = context.get("edge_end_x", float(edge.end.x)) + dx
        else:
            return

        new_length = 0.5 * (abs(float(adj_start.length)) + abs(float(adj_end.length)))
        new_length = max(0.01, float(new_length))
        self._update_line_edge_length_constraints(context, new_length)

        self._direct_edit_drag_moved = True
        self._maybe_live_solve_during_direct_drag()
        if self._direct_edit_live_solve:
            self.request_update()
            return

        dirty_new = self._line_drag_dirty_rect(context)
        dirty = dirty_old.united(dirty_new)
        if dirty.isEmpty():
            self.request_update()
        else:
            self.update(dirty.toAlignedRect())

    def _apply_direct_edit_line_move_drag(self, world_pos, axis_lock=False):
        context = self._direct_edit_line_context
        if not context:
            return

        line = context.get("line")
        if line is None:
            return

        dirty_old = self._line_move_dirty_rect(context)

        dx = world_pos.x() - self._direct_edit_start_pos.x()
        dy = world_pos.y() - self._direct_edit_start_pos.y()
        if axis_lock:
            if abs(dx) >= abs(dy):
                dy = 0.0
            else:
                dx = 0.0

        line.start.x = context.get("start_start_x", float(line.start.x)) + dx
        line.start.y = context.get("start_start_y", float(line.start.y)) + dy
        line.end.x = context.get("start_end_x", float(line.end.x)) + dx
        line.end.y = context.get("start_end_y", float(line.end.y)) + dy

        self._direct_edit_drag_moved = True
        self._maybe_live_solve_during_direct_drag()
        if self._direct_edit_live_solve:
            self.request_update()
            return

        dirty_new = self._line_move_dirty_rect(context)
        dirty = dirty_old.united(dirty_new)
        if dirty.isEmpty():
            self.request_update()
        else:
            self.update(dirty.toAlignedRect())

    def _apply_direct_edit_drag(self, world_pos, axis_lock=False):
        """Aktualisiert Geometrie wÄhrend des Drag-Vorgangs."""
        if not self._direct_edit_dragging:
            return

        if self._direct_edit_mode == "line_edge":
            self._apply_direct_edit_line_drag(world_pos, axis_lock=axis_lock)
            return
        if self._direct_edit_mode == "line_move":
            self._apply_direct_edit_line_move_drag(world_pos, axis_lock=axis_lock)
            return

        # W30 AP1: Line Endpoint Dragging
        if self._direct_edit_mode in ("endpoint_start", "endpoint_end"):
            line = self._direct_edit_line
            if line is not None:
                # Update the active endpoint
                if self._direct_edit_active_endpoint == "start":
                    line.start.x = world_pos.x()
                    line.start.y = world_pos.y()
                else:  # end
                    line.end.x = world_pos.x()
                    line.end.y = world_pos.y()

                self._direct_edit_drag_moved = True
                self._maybe_live_solve_during_direct_drag()
                if self._direct_edit_live_solve:
                    self.request_update()
                else:
                    # Minimal dirty rect update
                    bbox = self._get_entity_bbox(line)
                    dirty = QRectF(bbox).adjusted(-8.0, -8.0, 8.0, 8.0)
                    self.update(dirty.toAlignedRect())
            return

        # W30 AP1: Line Midpoint Dragging (move entire line)
        if self._direct_edit_mode == "midpoint":
            line = self._direct_edit_line
            if line is not None:
                dx = world_pos.x() - self._direct_edit_start_pos.x()
                dy = world_pos.y() - self._direct_edit_start_pos.y()
                if axis_lock:
                    if abs(dx) >= abs(dy):
                        dy = 0.0
                    else:
                        dx = 0.0

                line.start.x = self._direct_edit_endpoint_start.x() + dx
                line.start.y = self._direct_edit_endpoint_start.y() + dy
                line.end.x = self._direct_edit_endpoint_end.x() + dx
                line.end.y = self._direct_edit_endpoint_end.y() + dy

                self._direct_edit_drag_moved = True
                self._maybe_live_solve_during_direct_drag()
                if self._direct_edit_live_solve:
                    self.request_update()
                else:
                    # Minimal dirty rect update
                    bbox = self._get_entity_bbox(line)
                    dirty = QRectF(bbox).adjusted(-8.0, -8.0, 8.0, 8.0)
                    self.update(dirty.toAlignedRect())
            return

        # W20 P1: Arc Direct Edit Dragging
        # W28: SHIFT-Achsenlock + Dirty-Rect für Performance
        if hasattr(self, '_direct_edit_arc') and self._direct_edit_arc is not None:
            arc = self._direct_edit_arc
            mode = self._direct_edit_mode
            
            # Dirty-Rect für Arc
            dirty_old = self._get_arc_dirty_rect(arc)
            
            if mode == "center":
                dx = world_pos.x() - self._direct_edit_start_pos.x()
                dy = world_pos.y() - self._direct_edit_start_pos.y()
                if axis_lock:
                    if abs(dx) >= abs(dy):
                        dy = 0.0
                    else:
                        dx = 0.0
                arc.center.x = self._direct_edit_start_center.x() + dx
                arc.center.y = self._direct_edit_start_center.y() + dy
                
            elif mode == "radius":
                # W28: SHIFT-Lock für Radius auf 45°-Inkremente
                angle = math.atan2(world_pos.y() - arc.center.y, world_pos.x() - arc.center.x)
                if axis_lock:
                    # Snap to 45° increments
                    angle_deg = math.degrees(angle)
                    angle_deg = round(angle_deg / 45.0) * 45.0
                    angle = math.radians(angle_deg)
                new_radius = math.hypot(world_pos.x() - arc.center.x, world_pos.y() - arc.center.y)
                arc.radius = max(0.01, new_radius)

                # W34: Update marker positions when radius changes
                if hasattr(arc, '_start_marker') and arc._start_marker is not None:
                    start_angle_rad = math.radians(arc.start_angle)
                    arc._start_marker.x = arc.center.x + arc.radius * math.cos(start_angle_rad)
                    arc._start_marker.y = arc.center.y + arc.radius * math.sin(start_angle_rad)
                if hasattr(arc, '_end_marker') and arc._end_marker is not None:
                    end_angle_rad = math.radians(arc.end_angle)
                    arc._end_marker.x = arc.center.x + arc.radius * math.cos(end_angle_rad)
                    arc._end_marker.y = arc.center.y + arc.radius * math.sin(end_angle_rad)

            elif mode == "start_angle":
                angle = math.degrees(math.atan2(world_pos.y() - arc.center.y, world_pos.x() - arc.center.x))
                if axis_lock:
                    # Snap to 45° increments
                    angle = round(angle / 45.0) * 45.0
                arc.start_angle = angle

                # W34: Update start marker point
                if hasattr(arc, '_start_marker') and arc._start_marker is not None:
                    angle_rad = math.radians(angle)
                    arc._start_marker.x = arc.center.x + arc.radius * math.cos(angle_rad)
                    arc._start_marker.y = arc.center.y + arc.radius * math.sin(angle_rad)

            elif mode == "end_angle":
                angle = math.degrees(math.atan2(world_pos.y() - arc.center.y, world_pos.x() - arc.center.x))
                if axis_lock:
                    # Snap to 45° increments
                    angle = round(angle / 45.0) * 45.0
                arc.end_angle = angle

                # W34: Update end marker point
                if hasattr(arc, '_end_marker') and arc._end_marker is not None:
                    angle_rad = math.radians(angle)
                    arc._end_marker.x = arc.center.x + arc.radius * math.cos(angle_rad)
                    arc._end_marker.y = arc.center.y + arc.radius * math.sin(angle_rad)
            
            self._direct_edit_drag_moved = True
            
            # W28: Dirty-Rect Update statt Full Redraw
            dirty_new = self._get_arc_dirty_rect(arc)
            dirty = dirty_old.united(dirty_new)
            if dirty.isEmpty():
                self.request_update()
            else:
                self.update(dirty.toAlignedRect())
            return

        # Ellipse direct edit
        # W28: SHIFT-Achsenlock + Dirty-Rect für Performance
        if self._direct_edit_ellipse is not None:
            ellipse = self._direct_edit_ellipse
            mode = self._direct_edit_mode

            # Dirty-Rect für Ellipse
            dirty_old = self._get_ellipse_dirty_rect(ellipse)

            if mode == "center":
                dx = world_pos.x() - self._direct_edit_start_pos.x()
                dy = world_pos.y() - self._direct_edit_start_pos.y()
                if axis_lock:
                    if abs(dx) >= abs(dy):
                        dy = 0.0
                    else:
                        dx = 0.0
                ellipse.center.x = self._direct_edit_start_center.x() + dx
                ellipse.center.y = self._direct_edit_start_center.y() + dy
            elif mode == "radius_x":
                rot = math.radians(self._direct_edit_start_rotation)
                ux, uy = math.cos(rot), math.sin(rot)
                vx = world_pos.x() - ellipse.center.x
                vy = world_pos.y() - ellipse.center.y
                proj = (vx * ux) + (vy * uy)
                new_rx = max(0.01, abs(float(proj)))
                # W28: SHIFT-Lock für proportionalen Resize beider Achsen
                if axis_lock:
                    ratio = self._direct_edit_start_radius_x / self._direct_edit_start_radius_y if self._direct_edit_start_radius_y > 0 else 1.0
                    ellipse.radius_x = new_rx
                    ellipse.radius_y = new_rx / ratio if ratio > 0 else new_rx
                else:
                    ellipse.radius_x = new_rx
            elif mode == "radius_y":
                rot = math.radians(self._direct_edit_start_rotation)
                px, py = -math.sin(rot), math.cos(rot)
                vx = world_pos.x() - ellipse.center.x
                vy = world_pos.y() - ellipse.center.y
                proj = (vx * px) + (vy * py)
                new_ry = max(0.01, abs(float(proj)))
                # W28: SHIFT-Lock für proportionalen Resize beider Achsen
                if axis_lock:
                    ratio = self._direct_edit_start_radius_x / self._direct_edit_start_radius_y if self._direct_edit_start_radius_y > 0 else 1.0
                    ellipse.radius_y = new_ry
                    ellipse.radius_x = new_ry * ratio
                else:
                    ellipse.radius_y = new_ry
            elif mode == "rotation":
                angle = math.degrees(
                    math.atan2(world_pos.y() - ellipse.center.y, world_pos.x() - ellipse.center.x)
                )
                if axis_lock:
                    # Snap to 45° increments
                    angle = round(angle / 45.0) * 45.0
                ellipse.rotation = float(angle)
            else:
                return

            self._direct_edit_drag_moved = True

            # W34: Immediate ellipse geometry update for live visual feedback
            # This ensures segment points are updated immediately after property changes
            self.sketch._update_ellipse_geometry()

            # W28: Dirty-Rect Update statt Full Redraw
            dirty_new = self._get_ellipse_dirty_rect(ellipse)
            dirty = dirty_old.united(dirty_new)
            if dirty.isEmpty():
                self.request_update()
            else:
                self.update(dirty.toAlignedRect())
            return

        # W34: Polygon direct edit
        # W28: SHIFT-Achsenlock + Dirty-Rect für Performance
        if self._direct_edit_polygon is not None and self._direct_edit_mode in ("vertex", "center"):
            polygon = self._direct_edit_polygon

            # W34: Handle center mode (move entire polygon via driver circle)
            if self._direct_edit_mode == "center":
                driver_circle = self._direct_edit_polygon_driver_circle
                if driver_circle is not None:
                    # Dirty-Rect für Polygon
                    dirty_old = self._get_polygon_dirty_rect(polygon)

                    dx = world_pos.x() - self._direct_edit_start_pos.x()
                    dy = world_pos.y() - self._direct_edit_start_pos.y()
                    if axis_lock:
                        if abs(dx) >= abs(dy):
                            dy = 0.0
                        else:
                            dx = 0.0

                    # Move driver circle center
                    driver_circle.center.x = self._direct_edit_start_circle_center.x() + dx
                    driver_circle.center.y = self._direct_edit_start_circle_center.y() + dy

                    # W34-fix: Move all polygon points together (solver only runs on finish)
                    points = getattr(polygon, "points", [])
                    for i, pt in enumerate(points):
                        if i < len(self._direct_edit_polygon_point_starts):
                            pt.x = self._direct_edit_polygon_point_starts[i].x() + dx
                            pt.y = self._direct_edit_polygon_point_starts[i].y() + dy

                    self._direct_edit_drag_moved = True

                    # W28: Dirty-Rect Update statt Full Redraw
                    dirty_new = self._get_polygon_dirty_rect(polygon)
                    dirty = dirty_old.united(dirty_new)
                    if dirty.isEmpty():
                        self.request_update()
                    else:
                        self.update(dirty.toAlignedRect())
                return

            # Original vertex drag mode
            vertex_idx = self._direct_edit_polygon_vertex_idx
            points = getattr(polygon, "points", None)
            if points is None or vertex_idx < 0 or vertex_idx >= len(points):
                return

            # Dirty-Rect für Polygon
            dirty_old = self._get_polygon_dirty_rect(polygon)

            dx = world_pos.x() - self._direct_edit_start_pos.x()
            dy = world_pos.y() - self._direct_edit_start_pos.y()
            if axis_lock:
                if abs(dx) >= abs(dy):
                    dy = 0.0
                else:
                    dx = 0.0

            pt = points[vertex_idx]
            pt.x = self._direct_edit_polygon_vertex_start.x() + dx
            pt.y = self._direct_edit_polygon_vertex_start.y() + dy

            self._direct_edit_drag_moved = True
            
            # W28: Dirty-Rect Update statt Full Redraw
            dirty_new = self._get_polygon_dirty_rect(polygon)
            dirty = dirty_old.united(dirty_new)
            if dirty.isEmpty():
                self.request_update()
            else:
                self.update(dirty.toAlignedRect())
            return

        # W34: Slot direct edit
        if self._direct_edit_slot is not None:
            slot = self._direct_edit_slot
            mode = self._direct_edit_mode

            # Calculate dirty rect for slot (bounding box of all components)
            dirty_old = QRectF()
            for line in self.sketch.lines:
                if getattr(line, '_slot_center_line', False) or getattr(line, '_slot_parent_center_line', None) is slot:
                    bbox = self._get_entity_bbox(line)
                    dirty_old = dirty_old.united(QRectF(bbox))
            for arc in self.sketch.arcs:
                if hasattr(arc, '_slot_arc') and arc._slot_arc:
                    bbox = self._get_arc_dirty_rect(arc)
                    dirty_old = dirty_old.united(bbox)

            if mode == "center":
                # Move entire slot by moving the center line
                dx = world_pos.x() - self._direct_edit_start_pos.x()
                dy = world_pos.y() - self._direct_edit_start_pos.y()
                if axis_lock:
                    if abs(dx) >= abs(dy):
                        dy = 0.0
                    else:
                        dx = 0.0

                # Move center line endpoints
                slot.start.x = slot.start.x + dx
                slot.start.y = slot.start.y + dy
                slot.end.x = slot.end.x + dx
                slot.end.y = slot.end.y + dy

                # Move arc centers (they're at the same position as center line endpoints)
                for arc in self.sketch.arcs:
                    if hasattr(arc, '_slot_arc') and arc._slot_arc:
                        arc.center.x += dx
                        arc.center.y += dy

                self._direct_edit_drag_moved = True

            elif mode in ("length_start", "length_end"):
                # Change slot length by moving one endpoint
                dx = world_pos.x() - self._direct_edit_start_pos.x()
                dy = world_pos.y() - self._direct_edit_start_pos.y()
                if axis_lock:
                    if abs(dx) >= abs(dy):
                        dy = 0.0
                    else:
                        dx = 0.0

                if mode == "length_start":
                    # Move start point along the line direction
                    slot.start.x += dx
                    slot.start.y += dy
                else:
                    # Move end point along the line direction
                    slot.end.x += dx
                    slot.end.y += dy

                # Update corresponding arc center
                for arc in self.sketch.arcs:
                    if hasattr(arc, '_slot_arc') and arc._slot_arc:
                        # Check if this arc is at the start or end
                        arc_center_dist_start = math.hypot(arc.center.x - slot.start.x, arc.center.y - slot.start.y)
                        arc_center_dist_end = math.hypot(arc.center.x - slot.end.x, arc.center.y - slot.end.y)
                        if mode == "length_start" and arc_center_dist_start < 1e-6:
                            arc.center.x = slot.start.x
                            arc.center.y = slot.start.y
                        elif mode == "length_end" and arc_center_dist_end < 1e-6:
                            arc.center.x = slot.end.x
                            arc.center.y = slot.end.y

                self._direct_edit_drag_moved = True

            elif mode == "radius":
                # Change slot radius by updating arc radii
                arc = self._direct_edit_slot_arc
                if arc is not None:
                    # Calculate new radius based on mouse distance from center
                    dx = world_pos.x() - self._direct_edit_start_pos.x()
                    dy = world_pos.y() - self._direct_edit_start_pos.y()

                    # Project mouse movement onto radius direction
                    new_radius = self._direct_edit_slot_start_radius + dx  # Simplified: use x-delta
                    new_radius = max(0.01, abs(new_radius))

                    # Update both arc caps
                    for slot_arc in self.sketch.arcs:
                        if hasattr(slot_arc, '_slot_arc') and slot_arc._slot_arc:
                            slot_arc.radius = new_radius

                            # Update marker points for this arc
                            if hasattr(slot_arc, '_start_marker') and slot_arc._start_marker is not None:
                                start_angle_rad = math.radians(slot_arc.start_angle)
                                slot_arc._start_marker.x = slot_arc.center.x + new_radius * math.cos(start_angle_rad)
                                slot_arc._start_marker.y = slot_arc.center.y + new_radius * math.sin(start_angle_rad)
                            if hasattr(slot_arc, '_end_marker') and slot_arc._end_marker is not None:
                                end_angle_rad = math.radians(slot_arc.end_angle)
                                slot_arc._end_marker.x = slot_arc.center.x + new_radius * math.cos(end_angle_rad)
                                slot_arc._end_marker.y = slot_arc.center.y + new_radius * math.sin(end_angle_rad)

                    self._direct_edit_drag_moved = True

            # Calculate new dirty rect and update
            dirty_new = QRectF()
            for line in self.sketch.lines:
                if getattr(line, '_slot_center_line', False) or getattr(line, '_slot_parent_center_line', None) is slot:
                    bbox = self._get_entity_bbox(line)
                    dirty_new = dirty_new.united(QRectF(bbox))
            for arc in self.sketch.arcs:
                if hasattr(arc, '_slot_arc') and arc._slot_arc:
                    bbox = self._get_arc_dirty_rect(arc)
                    dirty_new = dirty_new.united(bbox)

            dirty = dirty_old.united(dirty_new)
            if dirty.isEmpty():
                self.request_update()
            else:
                self.update(dirty.toAlignedRect())
            return

        if self._direct_edit_circle is None:
            return

        circle = self._direct_edit_circle
        mode = self._direct_edit_mode
        old_cx = float(circle.center.x)
        old_cy = float(circle.center.y)
        old_radius = float(circle.radius)

        if mode == "center":
            dx = world_pos.x() - self._direct_edit_start_pos.x()
            dy = world_pos.y() - self._direct_edit_start_pos.y()
            if axis_lock:
                if abs(dx) >= abs(dy):
                    dy = 0.0
                else:
                    dx = 0.0

            circle.center.x = self._direct_edit_start_center.x() + dx
            circle.center.y = self._direct_edit_start_center.y() + dy

        elif mode == "radius":
            new_radius = math.hypot(world_pos.x() - circle.center.x, world_pos.y() - circle.center.y)
            new_radius = max(0.01, new_radius)
            self._direct_edit_anchor_angle = math.atan2(
                world_pos.y() - circle.center.y,
                world_pos.x() - circle.center.x,
            )
            self._update_circle_radius_constraint(circle, new_radius)

        else:
            return

        self._direct_edit_drag_moved = True
        # Live-Solve nur bei komplexen Abhaengigkeiten und dann gedrosselt.
        self._maybe_live_solve_during_direct_drag()
        if self._direct_edit_live_solve:
            # Abhaengige Geometrie kann ueber den Kreis hinaus veraendert werden.
            self.request_update()
            return

        # Fast path: nur den tatsaechlich geaenderten Kreisbereich neu zeichnen.
        dirty_old = self._get_circle_dirty_rect(old_cx, old_cy, old_radius)
        dirty_new = self._get_circle_dirty_rect(circle.center.x, circle.center.y, circle.radius)
        dirty = dirty_old.united(dirty_new)
        if dirty.isEmpty():
            self.request_update()
        else:
            self.update(dirty.toAlignedRect())

    def _finish_direct_edit_drag(self):
        """
        Schliesst Direct-Manipulation ab und propagiert UI-Updates.

        W33 EPIC AA1: Constraint-Rollback bei unloesbarem Drag.
        """
        if not self._direct_edit_dragging:
            return

        moved = self._direct_edit_drag_moved
        mode = self._direct_edit_mode
        source = self._direct_edit_source or "circle"

        # W25: Zentralisiertes Zurücksetzen des Direct-Edit-Zustands
        self._reset_direct_edit_state()

        if moved:
            # W33 EPIC AA1.2: Final-Solve mit Rollback bei Fehler
            result = self.sketch.solve()
            success = getattr(result, "success", True)

            if not success:
                # W33 EPIC AA1.1: Rollback bei unloesbarem Zustand
                self._rollback_last_undo_state()
                # W33 EPIC AA2: Verbesserte Solver-Feedback-Meldung
                try:
                    from gui.sketch_feedback import format_direct_edit_solver_message
                    error_msg = format_direct_edit_solver_message(
                        mode=mode,
                        status=getattr(result, "status", ""),
                        message=getattr(result, "message", "Solve failed"),
                        dof=getattr(result, "dof", None),
                    )
                except ImportError:
                    error_msg = f"Direct edit: {getattr(result, 'message', 'Solve failed')}"

                self._emit_solver_feedback(
                    success=False,
                    message=error_msg,
                    dof=float(getattr(result, "dof", 0.0) or 0.0),
                    status_name=self._solver_status_name(result),
                    context="Direct edit",
                    show_hud=True,
                )
                # Nach Rollback keine weiteren Updates
                return

            # Erfolg: Profile finden und Update senden
            self._find_closed_profiles()
            self.sketched_changed.emit()

            if mode == "radius":
                self.status_message.emit(f"{source.title()} radius updated")
            elif mode == "center":
                self.status_message.emit(f"{source.title()} moved")
            elif mode == "line_edge":
                self.status_message.emit(tr("Rectangle size updated"))
            elif mode == "line_move":
                self.status_message.emit(tr("Line moved"))
            elif mode in ("radius_x", "radius_y"):
                self.status_message.emit(tr("Ellipse axis updated"))
            elif mode == "rotation":
                self.status_message.emit(tr("Ellipse rotation updated"))
            elif mode == "vertex":
                self.status_message.emit(tr("Polygon vertex moved"))
            elif mode in ("endpoint_start", "endpoint_end"):
                self.status_message.emit(tr("Line endpoint updated"))
            elif mode == "midpoint":
                self.status_message.emit(tr("Line moved"))
            elif mode in ("start_angle", "end_angle"):
                self.status_message.emit(tr("Arc angle updated"))

        self.request_update()

    @staticmethod
    def _direct_handle_signature(handle):
        """Stabile Signatur für Hover-Change-Detection bei Direct-Handles."""
        if not handle:
            return None
        mode = handle.get("mode")
        kind = handle.get("kind", "circle")
        if kind == "line":
            return (mode, kind, id(handle.get("line")), handle.get("orientation"))
        if kind == "arc":
            return (mode, kind, id(handle.get("arc")))
        if kind == "ellipse":
            return (mode, kind, id(handle.get("ellipse")))
        if kind == "polygon":
            return (mode, kind, id(handle.get("polygon")), handle.get("vertex_idx"))
        return (mode, kind, id(handle.get("circle")))
    
    def _update_cursor(self):
        # W28: Direct-Manipulation Parity - konsistente Cursor für alle Handle-Typen
        if self._direct_edit_dragging:
            # Während Drag: Cursor basierend auf Modus
            mode = self._direct_edit_mode
            if mode == "center":
                self.setCursor(Qt.ClosedHandCursor)
            elif mode == "line_edge":
                orientation = getattr(self, '_direct_edit_line_context', {}).get("orientation")
                if orientation == "horizontal":
                    self.setCursor(Qt.SizeVerCursor)
                elif orientation == "vertical":
                    self.setCursor(Qt.SizeHorCursor)
                else:
                    self.setCursor(Qt.SizeAllCursor)
            elif mode == "line_move":
                self.setCursor(Qt.ClosedHandCursor)
            elif mode == "midpoint":
                self.setCursor(Qt.ClosedHandCursor)
            elif mode in ("endpoint_start", "endpoint_end"):
                self.setCursor(Qt.SizeAllCursor)
            elif mode == "radius":
                self.setCursor(Qt.SizeFDiagCursor)
            elif mode in ("radius_x", "radius_y"):
                self.setCursor(Qt.SizeFDiagCursor)
            elif mode == "rotation":
                self.setCursor(Qt.SizeAllCursor)
            elif mode == "vertex":
                self.setCursor(Qt.ClosedHandCursor)
            elif mode in ("start_angle", "end_angle"):
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.ClosedHandCursor)
            return

        if self.current_tool == SketchTool.SELECT and self._direct_hover_handle:
            mode = self._direct_hover_handle.get("mode")
            kind = self._direct_hover_handle.get("kind", "circle")
            if mode == "center":
                self.setCursor(Qt.OpenHandCursor)
            elif mode == "line_edge":
                orientation = self._direct_hover_handle.get("orientation")
                if orientation == "horizontal":
                    self.setCursor(Qt.SizeVerCursor)
                elif orientation == "vertical":
                    self.setCursor(Qt.SizeHorCursor)
                else:
                    self.setCursor(Qt.SizeAllCursor)
            elif mode == "line_move":
                self.setCursor(Qt.OpenHandCursor)
            elif mode == "midpoint":
                self.setCursor(Qt.OpenHandCursor)
            elif mode in ("endpoint_start", "endpoint_end"):
                self.setCursor(Qt.SizeAllCursor)
            elif mode == "radius":
                self.setCursor(Qt.SizeFDiagCursor)
            elif mode in ("radius_x", "radius_y"):
                self.setCursor(Qt.SizeFDiagCursor)
            elif mode == "rotation":
                self.setCursor(Qt.SizeAllCursor)
            elif mode == "vertex":
                self.setCursor(Qt.OpenHandCursor)
            elif mode in ("start_angle", "end_angle"):
                # Arc angle handles
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.SizeHorCursor)
            return

        if self.current_tool == SketchTool.SELECT:
            if self.hovered_entity is not None:
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
        elif self.current_tool == SketchTool.MOVE: self.setCursor(Qt.SizeAllCursor)
        else: self.setCursor(Qt.CrossCursor)
    
    def _show_tool_hint(self):
        n_sel = (
            len(self.selected_lines)
            + len(self.selected_circles)
            + len(self.selected_arcs)
            + len(self.selected_points)
            + len(self.selected_splines)
        )
        sel_info = f" ({n_sel} ausgewÄhlt)" if n_sel > 0 else ""
        
        hints = {
            SketchTool.SELECT: tr("Click=Select | Shift+Click=Multi | Drag=Box | Tab=Cycle overlap | W=Filter ({flt}) | Y=Repeat tool | Shift+C=Clip | Line: drag to move | Circle/Polygon: drag center or rim | Rectangle: select edge + drag | Del=Delete").format(
                flt=self._selection_filter_label()
            ),
            SketchTool.LINE: tr("Click=Start | Tab=Length/Angle | RightClick=Finish"),
            SketchTool.RECTANGLE: tr("Rectangle") + f" ({tr('Center') if self.rect_mode else tr('2-Point')}) | " + tr("Click=Start"),
            SketchTool.RECTANGLE_CENTER: tr("Rectangle") + " (" + tr("Center") + ") | " + tr("Click=Start"),
            SketchTool.CIRCLE: tr("Circle") + f" ({[tr('Center'), tr('2-Point'), tr('3-Point')][self.circle_mode]}) | Tab=" + tr("Radius"),
            SketchTool.ELLIPSE: tr("Ellipse | Click=Center→Major→Minor | Tab=Input"),
            SketchTool.CIRCLE_2POINT: tr("Circle") + " (" + tr("2-Point") + ")",
            SketchTool.POLYGON: tr("Polygon") + f" ({self.polygon_sides} " + tr("{n} sides").format(n="") + ") | Tab",
            SketchTool.ARC_3POINT: tr("[A] Arc | Click=Start→Through→End"),
            SketchTool.SLOT: tr("Slot | Click=Start"),
            SketchTool.PROJECT: tr("Project | Hover edge + click | Shift+C=Clip mode ({mode}) | [ ]=Section band").format(
                mode=getattr(self, "reference_clip_mode", "all")
            ),
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
            SketchTool.CANVAS: tr("Canvas") + " | " + tr("Click to place image reference"),
        }
        tool_hint = hints.get(self.current_tool, "")
        
        # W16 Paket B: Kontext-sensitive Navigation-Hints
        nav_hint = self._get_navigation_hints_for_context()
        
        # Tutorial-Modus: Erweiterte Hinweise für neue Nutzer
        if self._tutorial_mode_enabled and not self._peek_3d_active:
            tutorial_hint = self._get_tutorial_hint_for_tool()
            if tutorial_hint:
                tool_hint = f"{tool_hint} | {tutorial_hint}" if tool_hint else tutorial_hint
        
        if tool_hint:
            self.status_message.emit(f"{tool_hint} | {nav_hint}")
        else:
            self.status_message.emit(nav_hint)
    
    def _get_navigation_hints_for_context(self):
        """
        W16 Paket B: Liefert kontext-sensitive Navigation-Hinweise.
        
        Returns:
            str: Navigation-Hinweis passend zum aktuellen Kontext
        """
        if self._peek_3d_active:
            return tr("Space loslassen=Zurück zum Sketch | Maus bewegen=Ansicht rotieren")
        elif self._direct_edit_dragging:
            return tr("Esc=Abbrechen | Drag=Ändern | Enter=Bestätigen")
        elif self._tutorial_mode_enabled:
            return tr("Shift+R=Ansicht drehen | Space=3D-Peek | F1=Tutorial aus")
        else:
            return tr("Shift+R=Ansicht drehen | Space halten=3D-Peek")
    
    def _get_tutorial_hint_for_tool(self, tool=None):
        """
        W16 Paket B: Liefert Tutorial-Hinweise für den aktuellen Tool-Modus.
        
        Args:
            tool: Optional Tool-Constant (default: current_tool)
        
        Returns:
            str: Tutorial-Hinweis oder leerer String
        """
        target_tool = tool if tool is not None else self.current_tool
        tutorial_hints = {
            SketchTool.SELECT: tr("Tipp: Ziehe Kreise am Rand um den Radius zu Ändern"),
            SketchTool.LINE: tr("Tipp: Nutze Tab für exakte LÄngen/Winkeleingabe"),
            SketchTool.CIRCLE: tr("Tipp: Ziehe vom Mittelpunkt aus für exakten Radius"),
            SketchTool.RECTANGLE: tr("Tipp: Rechteck-Ecken künnen nach dem Zeichnen verschoben werden"),
            SketchTool.DIMENSION: tr("Tipp: Dimensionen schrÄnken die Geometrie ein"),
            SketchTool.FILLET_2D: tr("Tipp: Ziehe nacheinander zwei Linien für eine Rundung"),
        }
        return tutorial_hints.get(target_tool, "")
    
    def set_tutorial_mode(self, enabled: bool):
        """
        W16 Paket B: Aktiviert/Deaktiviert den Tutorial-Modus.
        
        Args:
            enabled: True für Tutorial-Modus aktiviert
        """
        self._tutorial_mode_enabled = enabled
        self._tutorial_mode = enabled  # API-Alias synchronisieren
        self._show_tool_hint()  # Sofort aktualisieren
        if enabled:
            self.show_message(tr("Tutorial-Modus aktiviert - Erweiterte Hinweise werden angezeigt"), 3000)
        else:
            self.show_message(tr("Tutorial-Modus deaktiviert"), 2000)
    
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

        # ELLIPSE: Step 1 = Major + Angle, Step 2 = Minor
        elif self.current_tool == SketchTool.ELLIPSE:
            if self.tool_step == 1:
                fields = [
                    ("Ra", "major", self.live_length if self.live_length > 0 else 25.0, "mm"),
                    ("∠", "angle", self.live_angle, "°"),
                ]
            elif self.tool_step == 2:
                fields = [("Rb", "minor", self.live_radius if self.live_radius > 0 else 12.0, "mm")]
                
        # POLYGON: Nach Zentrum (mit Rotation)
        elif self.current_tool == SketchTool.POLYGON:
            if self.tool_step >= 1:
                fields = [("R", "radius", self.live_radius, "mm"),
                          ("∠", "angle", self.live_angle, "°"),
                          ("N", "sides", self._safe_float(self.polygon_sides), "")]
            elif self.tool_step == 0:
                fields = [("R", "radius", 25.0, "mm"),
                          ("∠", "angle", 0.0, "°"),
                          ("N", "sides", self._safe_float(self.polygon_sides), "")]
                
        elif self.current_tool == SketchTool.MOVE and self.tool_step == 1:
            fields = [("X", "dx", 0.0, "mm"), ("Y", "dy", 0.0, "mm")]
        elif self.current_tool == SketchTool.COPY and self.tool_step == 1:
            # COPY benutzt die gleichen Felder wie MOVE
            fields = [("X", "dx", 0.0, "mm"), ("Y", "dy", 0.0, "mm")]
        elif self.current_tool == SketchTool.ROTATE and self.tool_step >= 1:
            fields = [("∠", "angle", 0.0, "°")]
        elif self.current_tool == SketchTool.SCALE and self.tool_step >= 1:
            fields = [("F", "factor", 1.0, "")]
            
        # SLOT: Nach Startpunkt (LÄnge/Winkel), Nach Mittellinie (Radius)
        elif self.current_tool == SketchTool.SLOT:
            if self.tool_step == 1:
                fields = [("L", "length", self.live_length if self.live_length > 0 else 50.0, "mm"),
                          ("∠", "angle", self.live_angle, "°")]
            elif self.tool_step == 2:
                fields = [("R", "radius", self.live_radius if self.live_radius > 0 else 5.0, "mm")]

        # NUT: Nach Position (Winkel für Rotation)
        elif self.current_tool == SketchTool.NUT:
            if self.tool_step >= 1:
                fields = [("∠", "angle", self.live_angle, "°")]
            elif self.tool_step == 0:
                fields = [("∠", "angle", 0.0, "°")]

        # STAR: Nach Zentrum (Spitzen, Radien)
        elif self.current_tool == SketchTool.STAR:
            if self.tool_step >= 1:
                n = self.tool_data.get('star_points', 5)
                ro = self.tool_data.get('star_r_outer', 50.0)
                ri = self.tool_data.get('star_r_inner', 25.0)
                fields = [("N", "points", self._safe_float(n), ""),
                          ("Ro", "r_outer", ro, "mm"),
                          ("Ri", "r_inner", ri, "mm")]
            elif self.tool_step == 0:
                fields = [("N", "points", 5.0, ""),
                          ("Ro", "r_outer", 50.0, "mm"),
                          ("Ri", "r_inner", 25.0, "mm")]

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
        elif self.current_tool == SketchTool.ELLIPSE:
            if key == "major":
                self.live_length = value
            elif key == "minor":
                self.live_radius = value
            elif key == "angle":
                self.live_angle = value
        elif self.current_tool == SketchTool.POLYGON:
            if key == "radius": self.live_radius = value
            elif key == "angle": self.live_angle = value
            elif key == "sides": self.polygon_sides = max(3, min(64, int(value)))
        elif self.current_tool == SketchTool.SLOT:
            # Step 1: Length/Angle of centerline
            # Step 2: Radius
            if key == "length":
                self.live_length = value
                logger.debug(f"[SLOT] live_length updated to {value}")
            elif key == "angle":
                self.live_angle = value
                logger.debug(f"[SLOT] live_angle updated to {value}")
            elif key == "radius":
                self.live_radius = value
                logger.debug(f"[SLOT] live_radius updated to {value}")
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
            self.request_update()
                
        elif self.current_tool == SketchTool.PATTERN_CIRCULAR:
            if key == "count":
                self.tool_data['pattern_count'] = max(2, int(value))
            elif key == "angle":
                self.tool_data['pattern_angle'] = value
            self.request_update()
        elif self.current_tool == SketchTool.STAR:
            if key == "points":
                self.tool_data['star_points'] = max(3, int(value))
            elif key == "r_outer":
                self.tool_data['star_r_outer'] = max(0.1, value)
            elif key == "r_inner":
                self.tool_data['star_r_inner'] = max(0.1, value)
            self.request_update()
        self.request_update()

    def _on_dim_field_committed(self, key: str, value: float):
        """
        Called when a single field is committed in per-field enter mode.

        Phase 8: Per-field enter - updates live values and logs.

        Args:
            key: Field key that was committed
            value: Committed value
        """
        # Update live value (same as _on_dim_value_changed but for committed values)
        self._on_dim_value_changed(key, value)

        # Log the commit event
        if sketch_logger and is_enabled("sketch_input_logging"):
            tool_name = self.current_tool.name if self.current_tool else "UNKNOWN"
            sketch_logger.log_commit(tool_name, key, value)

    def _on_dim_field_reset(self, key: str):
        """
        Called when a field is reset to auto mode (double-click).

        Phase 8: Reset to auto - recalculates value from mouse position.

        Args:
            key: Field key that was reset
        """
        # Update the field with current live value
        if key == "length":
            self.dim_input.set_value("length", self.live_length)
        elif key == "angle":
            self.dim_input.set_value("angle", self.live_angle)
        elif key == "width":
            self.dim_input.set_value("width", self.live_width)
        elif key == "height":
            self.dim_input.set_value("height", self.live_height)
        elif key == "radius":
            self.dim_input.set_value("radius", self.live_radius)
        elif key == "major":
            self.dim_input.set_value("major", self.live_length)
        elif key == "minor":
            self.dim_input.set_value("minor", self.live_radius)
        elif key == "distance":
            self.dim_input.set_value("distance", self.offset_distance)
        elif key == "factor":
            self.dim_input.set_value("factor", 1.0)  # Default scale

        # Log the unlock event
        if sketch_logger and is_enabled("sketch_input_logging"):
            tool_name = self.current_tool.name if self.current_tool else "UNKNOWN"
            sketch_logger.log_unlock(tool_name, key)

        self.request_update()

    def _on_dim_confirmed(self):
        from sketcher.constraints import ConstraintType
        from sketcher.geometry import Line2D, Circle2D, Arc2D

        if self.dim_input.has_errors():
            msg = getattr(self.dim_input, "_last_validation_error", None) or tr("Ungültiger Eingabewert")
            self.status_message.emit(msg)
            self.show_message(msg, 1800, QColor(255, 140, 100))
            return

        values = self.dim_input.get_values()

        # Helper für Solver-Check und Profil-Update
        def run_solver_and_update():
            result = self.sketch.solve()
            success = bool(getattr(result, "success", True))
            status_name = self._solver_status_name(result)
            dof = getattr(result, "dof", None)
            if dof is None:
                try:
                    _, _, dof = self.sketch.calculate_dof()
                except Exception:
                    dof = 0.0
            self._emit_solver_feedback(
                success=success,
                message=getattr(result, "message", ""),
                dof=self._safe_float(dof),
                status_name=status_name,
                context="Constraint edit",
                show_hud=True,
            )
            self._find_closed_profiles()
            self.sketched_changed.emit()
            return result

        def solve_quiet():
            try:
                return self.sketch.solve()
            except Exception as e:
                logger.debug(f"Quiet solve failed: {e}")
                return None

        def is_success(result) -> bool:
            return bool(getattr(result, "success", True)) if result is not None else False

        def get_valid_formula(field_key: str):
            raw_map = {}
            try:
                raw_map = self.dim_input.get_raw_texts()
            except Exception:
                return None

            raw = (raw_map.get(field_key, "") or "").strip()
            if not raw:
                return None

            try:
                float(raw.replace(',', '.'))
                return None
            except ValueError:
                pass

            evaluator = getattr(self.dim_input, "_evaluate_expression", None)
            if callable(evaluator):
                try:
                    if evaluator(raw) is None:
                        return None
                except Exception:
                    return None

            return raw

        def line_parallel_score(line_a: Line2D, line_b: Line2D) -> float:
            ax = line_a.end.x - line_a.start.x
            ay = line_a.end.y - line_a.start.y
            bx = line_b.end.x - line_b.start.x
            by = line_b.end.y - line_b.start.y
            la = math.hypot(ax, ay)
            lb = math.hypot(bx, by)
            if la < 1e-9 or lb < 1e-9:
                return -1.0

            # |cross|/(|a||b|) ~ 0 => parallel.
            parallel_error = abs(ax * by - ay * bx) / (la * lb)
            if parallel_error > 1e-3:
                return -1.0

            ma_x = (line_a.start.x + line_a.end.x) * 0.5
            ma_y = (line_a.start.y + line_a.end.y) * 0.5
            mb_x = (line_b.start.x + line_b.end.x) * 0.5
            mb_y = (line_b.start.y + line_b.end.y) * 0.5
            distance = math.hypot(ma_x - mb_x, ma_y - mb_y)

            equal_hint = any(
                c.type == ConstraintType.EQUAL_LENGTH and line_a in c.entities and line_b in c.entities
                for c in self.sketch.constraints
            )
            return distance - (1000.0 if equal_hint else 0.0)

        def length_constraints_for_line(line: Line2D):
            return [
                c for c in self.sketch.constraints
                if c.type == ConstraintType.LENGTH and line in c.entities
            ]

        def apply_length_value(constraint, new_length: float, formula_text=None) -> bool:
            old_value = constraint.value
            old_formula = constraint.formula

            constraint.value = float(new_length)
            constraint.formula = formula_text
            if is_success(solve_quiet()):
                return True

            constraint.value = old_value
            constraint.formula = old_formula
            solve_quiet()
            return False

        def try_add_length_constraint(line: Line2D, new_length: float, formula_text=None) -> bool:
            added = self.sketch.add_length(line, float(new_length))
            if added is None:
                return False

            added.formula = formula_text
            if is_success(solve_quiet()):
                return True

            self.sketch.remove_constraint(added)
            solve_quiet()
            return False

        def apply_line_length_edit(line: Line2D, new_length: float, formula_text=None):
            # 1) Direkt vorhandenen Constraint aktualisieren.
            for existing in length_constraints_for_line(line):
                if apply_length_value(existing, new_length, formula_text):
                    return True, "direct"

            # 2) Neuen Constraint auf diese Linie versuchen.
            if try_add_length_constraint(line, new_length, formula_text):
                return True, "added"

            # 3) Fallback: vorhandenen Driver auf paralleler Linie aktualisieren
            # (wichtig für Rechteck-Hühe, wenn die gegenüberliegende Seite der Driver ist).
            candidates = []
            for c in self.sketch.constraints:
                if c.type != ConstraintType.LENGTH or not c.entities:
                    continue
                other_line = c.entities[0]
                if not isinstance(other_line, Line2D) or other_line is line:
                    continue
                score = line_parallel_score(line, other_line)
                if score >= 0.0:
                    candidates.append((score, c))

            candidates.sort(key=lambda item: item[0])
            for _, candidate in candidates:
                if apply_length_value(candidate, new_length, formula_text):
                    return True, "parallel"

            return False, "failed"

        def radius_constraints_for_entity(entity):
            return [
                c for c in self.sketch.constraints
                if c.type in (ConstraintType.RADIUS, ConstraintType.DIAMETER) and entity in c.entities
            ]

        def radius_formula_for_constraint(constraint, formula_text):
            if not formula_text:
                return None
            if constraint.type == ConstraintType.DIAMETER:
                return f"({formula_text})*2"
            return formula_text

        def apply_radius_value(constraint, new_radius: float, formula_text=None) -> bool:
            old_value = constraint.value
            old_formula = constraint.formula

            constraint.value = float(new_radius) * (2.0 if constraint.type == ConstraintType.DIAMETER else 1.0)
            constraint.formula = radius_formula_for_constraint(constraint, formula_text)
            if is_success(solve_quiet()):
                return True

            constraint.value = old_value
            constraint.formula = old_formula
            solve_quiet()
            return False

        def apply_circle_radius_edit(entity, new_radius: float, formula_text=None):
            for existing in radius_constraints_for_entity(entity):
                if apply_radius_value(existing, new_radius, formula_text):
                    return True

            added = self.sketch.add_radius(entity, float(new_radius))
            if added is None:
                return False

            added.formula = formula_text
            if is_success(solve_quiet()):
                return True

            self.sketch.remove_constraint(added)
            solve_quiet()
            return False

        # === EDITING MODE: Constraint/Geometrie bearbeiten ===
        if self.editing_entity is not None:
            self._save_undo()

            if self.editing_mode == "constraint":
                # Constraint-Wert Ändern
                new_val = values.get("value", 0.0)
                self.editing_entity.value = new_val
                run_solver_and_update()
                self.show_message(f"Constraint auf {new_val:.2f} geÄndert", 2000, QColor(100, 255, 100))
                logger.debug(f"Constraint {self.editing_entity.type.name} geÄndert auf {new_val}")

            elif self.editing_mode == "line_length":
                # LÄnge robust bearbeiten: vorhandenen Driver aktualisieren statt blind zu duplizieren.
                new_length = values.get("length", 10.0)
                formula_text = get_valid_formula("length")
                updated, strategy = apply_line_length_edit(self.editing_entity, new_length, formula_text)
                run_solver_and_update()

                if updated:
                    if strategy == "parallel":
                        self.show_message(
                            f"LÄnge {new_length:.2f} mm aktualisiert (bestehender Hühen-Constraint)",
                            2200,
                            QColor(100, 255, 100),
                        )
                    else:
                        self.show_message(f"LÄnge {new_length:.2f} mm festgelegt", 2000, QColor(100, 255, 100))
                else:
                    self.show_message(
                        tr("LÄnge konnte nicht konfliktfrei gesetzt werden"),
                        2200,
                        QColor(255, 120, 120),
                    )

            elif self.editing_mode == "circle_radius":
                # Radius-Constraint aktualisieren oder hinzufügen.
                new_radius = values.get("radius", 10.0)
                formula_text = get_valid_formula("radius")
                updated = apply_circle_radius_edit(self.editing_entity, new_radius, formula_text)
                run_solver_and_update()

                if updated:
                    self.show_message(f"Radius {new_radius:.2f} mm festgelegt", 2000, QColor(100, 255, 100))
                else:
                    self.show_message(
                        tr("Radius konnte nicht gesetzt werden"),
                        2200,
                        QColor(255, 120, 120),
                    )

            # Editing-State zurücksetzen
            self.editing_entity = None
            self.editing_mode = None
            self.dim_input.hide()
            self.dim_input.unlock_all()
            self.dim_input_active = False
            self.request_update()
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
            
            # Optional: Hier künnten wir direkt Constraints (LÄnge/Winkel) hinzufügen,
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
                lines = self.sketch.add_rectangle(p1.x() - w/2, p1.y() - h/2, w, h, construction=self.construction_mode)
            else: # 2-Point
                mouse = self.mouse_world if self.mouse_world else p1
                x = p1.x() - w if mouse.x() < p1.x() else p1.x()
                y = p1.y() - h if mouse.y() < p1.y() else p1.y()
                lines = self.sketch.add_rectangle(x, y, w, h, construction=self.construction_mode)

            # Automatische Bemaüƒung hinzufügen (Constraints)
            if lines and len(lines) >= 4:
                self.sketch.add_length(lines[0], w)  # Breite (Unten)
                self.sketch.add_length(lines[3], h)  # Hühe (Links)

            run_solver_and_update()
            QTimer.singleShot(0, self._cancel_tool)
            
        elif self.current_tool == SketchTool.RECTANGLE_CENTER:
            w, h = values.get("width", 50), values.get("height", 30)
            c = self.tool_points[0] if self.tool_step >= 1 else (self.mouse_world or QPointF(0, 0))

            self._save_undo()
            lines = self.sketch.add_rectangle(c.x() - w/2, c.y() - h/2, w, h, construction=self.construction_mode)

            # Automatische Bemaüƒung hinzufügen (Constraints)
            if lines and len(lines) >= 4:
                self.sketch.add_length(lines[0], w)  # Breite (Unten)
                self.sketch.add_length(lines[3], h)  # Hühe (Links)

            run_solver_and_update()
            QTimer.singleShot(0, self._cancel_tool)

        elif self.current_tool == SketchTool.CIRCLE:
            # Nur für Center-Radius-Modus (circle_mode == 0) via dim_input bestÄtigen
            # 2-Punkt und 3-Punkt werden durch Klicks im Handler abgeschlossen
            if self.circle_mode == 0:
                r = self.live_radius if self.dim_input.is_locked('radius') else values.get("radius", 25)
                c = self.tool_points[0] if self.tool_step >= 1 else (self.mouse_world or QPointF(0, 0))

                self._save_undo()
                circle = self.sketch.add_circle(c.x(), c.y(), r, construction=self.construction_mode)

                # Automatische Bemaüƒung hinzufügen (Constraints)
                if circle:
                    self.sketch.add_radius(circle, r)

                run_solver_and_update()
                QTimer.singleShot(0, self._cancel_tool)
            elif self.circle_mode == 1 and self.tool_step >= 1:
                # 2-Punkt-Modus: p1 und mouse_world definieren den Durchmesser
                p1 = self.tool_points[0]
                if self.mouse_world:
                    p2 = self.mouse_world
                    # Zentrum = Mitte zwischen p1 und p2
                    cx = (p1.x() + p2.x()) / 2
                    cy = (p1.y() + p2.y()) / 2
                    # Radius = halber Abstand
                    r = math.hypot(p2.x() - p1.x(), p2.y() - p1.y()) / 2

                    if r > 0.01:
                        self._save_undo()
                        circle = self.sketch.add_circle(cx, cy, r, construction=self.construction_mode)
                        if circle:
                            self.sketch.add_radius(circle, r)
                        run_solver_and_update()

                QTimer.singleShot(0, self._cancel_tool)
            # 3-Punkt-Modus: Keine dim_input BestÄtigung - muss durch 3 Klicks erfolgen
            
        elif self.current_tool == SketchTool.ELLIPSE:
            if self.tool_step == 1:
                center = self.tool_points[0] if self.tool_step >= 1 else (self.mouse_world or QPointF(0, 0))
                major_radius = self.live_length if self.dim_input.is_locked('major') else values.get("major", self.live_length or 25.0)
                angle_deg = self.live_angle if self.dim_input.is_locked('angle') else values.get("angle", self.live_angle)

                major_radius = max(0.01, abs(float(major_radius)))
                angle_rad = math.radians(float(angle_deg))
                major_end = QPointF(
                    center.x() + major_radius * math.cos(angle_rad),
                    center.y() + major_radius * math.sin(angle_rad),
                )

                self.tool_points.append(major_end)
                self.tool_step = 2
                self.status_message.emit(tr("Minor radius | Tab=Input"))

                # Direkt auf Schritt-2 Feld umstellen (wie beim Slot-Tool).
                self.dim_input.committed_values.clear()
                self.dim_input.unlock_all()
                minor_default = self.live_radius if self.live_radius > 0 else max(0.01, major_radius * 0.6)
                self.dim_input.setup([("Rb", "minor", minor_default, "mm")])
                pos = self.mouse_screen
                x = min(int(pos.x()) + 20, self.width() - self.dim_input.width() - 10)
                y = min(int(pos.y()) - 40, self.height() - self.dim_input.height() - 10)
                self.dim_input.move(max(10, x), max(10, y))
                self.dim_input.show()
                self.dim_input.focus_field(0)
                self.dim_input_active = True
                return

            elif self.tool_step == 2:
                center = self.tool_points[0]
                major_end = self.tool_points[1]
                dx = major_end.x() - center.x()
                dy = major_end.y() - center.y()
                major_radius = math.hypot(dx, dy)
                if major_radius <= 0.01:
                    self.status_message.emit(tr("Major axis too short"))
                    QTimer.singleShot(0, self._cancel_tool)
                    return

                angle_deg = math.degrees(math.atan2(dy, dx))
                minor_radius = self.live_radius if self.dim_input.is_locked('minor') else values.get("minor", self.live_radius or major_radius * 0.5)
                minor_radius = max(0.01, abs(float(minor_radius)))

                self._save_undo()
                _, _, _, center_point = self.sketch.add_ellipse(
                    cx=center.x(),
                    cy=center.y(),
                    major_radius=major_radius,
                    minor_radius=minor_radius,
                    angle_deg=angle_deg,
                    construction=self.construction_mode,
                    segments=max(24, int(getattr(self, "circle_segments", 64) * 0.5)),
                )

                center_snap_type, center_snap_entity = getattr(self, "_ellipse_center_snap", (SnapType.NONE, None))
                self._apply_center_snap_constraint(center_point, center_snap_type, center_snap_entity)
                run_solver_and_update()

                if hasattr(self, "_ellipse_center_snap"):
                    del self._ellipse_center_snap
                QTimer.singleShot(0, self._cancel_tool)
                return

        elif self.current_tool == SketchTool.POLYGON:
            r = self.live_radius if self.dim_input.is_locked('radius') else values.get("radius", 25)
            n = int(values.get("sides", self.polygon_sides))
            c = self.tool_points[0] if self.tool_step >= 1 else (self.mouse_world or QPointF(0, 0))

            # Phase 8: Use angle from input (degrees -> radians)
            # If locked, use live_angle; otherwise get from values with fallback to live_angle
            angle_deg = self.live_angle if self.dim_input.is_locked('angle') else values.get("angle", self.live_angle)
            angle_rad = math.radians(angle_deg)

            self._save_undo()
            # Parametrisches Polygon mit Konstruktionskreis (wie in _handle_polygon)
            lines, const_circle = self.sketch.add_regular_polygon(
                c.x(), c.y(), r, n,
                angle_offset=angle_rad,
                construction=self.construction_mode
            )

            # Radius-Bemaüƒung für den Konstruktionskreis hinzufügen
            if const_circle:
                self.sketch.add_radius(const_circle, r)

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
                logger.info(f"[SLOT-TAB] Step 1→2: Confirmed length/angle via Tab")
                p1 = self.tool_points[0]
                length = values.get("length", 50.0)
                angle = math.radians(values.get("angle", 0.0))
                p2 = QPointF(p1.x() + length * math.cos(angle), p1.y() + length * math.sin(angle))
                self.tool_points.append(p2)
                self.tool_step = 2
                self.status_message.emit(tr("Radius | Tab=Enter radius"))
                logger.debug(f"[SLOT-TAB] p1={p1.x():.2f},{p1.y():.2f} p2={p2.x():.2f},{p2.y():.2f} length={length:.2f}")

                # Directly reconfigure the panel with radius field
                # Clear committed values and unlock all fields first
                self.dim_input.committed_values.clear()
                self.dim_input.unlock_all()

                # Setup new fields for step 2 (radius)
                radius_default = self.live_radius if self.live_radius > 0 else 5.0
                fields = [("R", "radius", radius_default, "mm")]
                self.dim_input.setup(fields)
                logger.debug(f"[SLOT-TAB] Radius panel setup: default={radius_default:.2f}")

                # Position near mouse and show
                pos = self.mouse_screen
                x = min(int(pos.x()) + 20, self.width() - self.dim_input.width() - 10)
                y = min(int(pos.y()) - 40, self.height() - self.dim_input.height() - 10)
                self.dim_input.move(max(10, x), max(10, y))
                self.dim_input.show()
                self.dim_input.focus_field(0)
                self.dim_input_active = True
                logger.success(f"[SLOT-TAB] Radius panel shown at ({x}, {y}), visible={self.dim_input.isVisible()}")

                return  # Don't run cleanup code at end of method
            elif self.tool_step == 2:
                p1, p2 = self.tool_points[0], self.tool_points[1]
                radius = values.get("radius", 5.0)
                logger.info(f"[SLOT-TAB] Step 2: Creating slot with radius={radius:.2f}")
                if radius > 0.01:
                    self._save_undo()
                    # Create slot using sketch.add_slot
                    length = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
                    center_line, main_arc = self.sketch.add_slot(
                        p1.x(), p1.y(), p2.x(), p2.y(), radius,
                        construction=self.construction_mode
                    )
                    # Add constraints for length and radius
                    if length > 0.01:
                        self.sketch.add_length(center_line, length)
                    self.sketch.add_radius(main_arc, radius)
                    run_solver_and_update()
                    logger.success(f"[SLOT-TAB] Slot created: length={length:.2f}, radius={radius:.2f}")
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

        # NUT: Tab-Eingabe für Rotation
        elif self.current_tool == SketchTool.NUT and self.tool_step >= 1:
            center = self.tool_points[0]
            rotation_angle = math.radians(values.get("angle", self.live_angle))

            # Schlüsselweite mit Toleranz
            size_name = self.nut_size_names[self.nut_size_index]
            sw = self.nut_sizes[size_name] + self.nut_tolerance

            # Schraubendurchmesser aus dem Namen extrahieren (M3 -> 3mm, M2.5 -> 2.5mm)
            screw_diameter = float(size_name[1:])
            hole_radius = (screw_diameter + self.nut_tolerance) / 2

            # Sechskant: Radius zum Eckpunkt = SW / sqrt(3)
            hex_radius = sw / math.sqrt(3)

            self._save_undo()

            # 6 Punkte für Sechskant mit Rotation
            points = []
            for i in range(6):
                angle = rotation_angle + math.radians(30 + i * 60)
                px = center.x() + hex_radius * math.cos(angle)
                py = center.y() + hex_radius * math.sin(angle)
                points.append((px, py))

            self.sketch.add_polygon(points, closed=True, construction=self.construction_mode)

            # Schraubenloch (Kreis in der Mitte)
            self.sketch.add_circle(center.x(), center.y(), hole_radius, construction=self.construction_mode)

            self.sketch.solve()
            self.sketched_changed.emit()
            self._find_closed_profiles()

            # Info anzeigen
            self.status_message.emit(f"{size_name} " + tr("Nut") + f" (SW {sw:.2f}mm, " + tr("Hole") + f" ⌀{screw_diameter + self.nut_tolerance:.2f}mm)")
            QTimer.singleShot(0, self._cancel_tool)
            return

        # STAR: Tab-Eingabe für Stern
        elif self.current_tool == SketchTool.STAR and self.tool_step >= 1:
            center = self.tool_points[0]
            n = max(3, int(values.get("points", self.tool_data.get('star_points', 5))))
            ro = values.get("r_outer", self.tool_data.get('star_r_outer', 50.0))
            ri = values.get("r_inner", self.tool_data.get('star_r_inner', 25.0))

            self._save_undo()

            # Stern-Punkte berechnen
            points = []
            step = math.pi / n
            for i in range(2 * n):
                r = ro if i % 2 == 0 else ri
                angle = i * step - math.pi / 2  # Startet oben
                px = center.x() + r * math.cos(angle)
                py = center.y() + r * math.sin(angle)
                points.append((px, py))

            # Linien erstellen
            for i in range(len(points)):
                p1 = points[i]
                p2 = points[(i + 1) % len(points)]
                self.sketch.add_line(p1[0], p1[1], p2[0], p2[1], construction=self.construction_mode)

            self.sketch.solve()
            self.sketched_changed.emit()
            self._find_closed_profiles()
            self.status_message.emit(tr("Star") + f" ({n} " + tr("points") + f", Ro={ro:.1f}, Ri={ri:.1f})")
            QTimer.singleShot(0, self._cancel_tool)
            return

        if is_enabled("sketch_debug"):
            logger.debug(f"[DIM] Fallthrough hide at end of _on_dim_confirmed (tool={self.current_tool.name}, step={self.tool_step})")
        self.dim_input.hide()
        self.dim_input.unlock_all()
        self.dim_input_active = False
        self.setFocus()
        self.request_update()

    def mousePressEvent(self, event):
        pos = event.position()
        self.mouse_screen = pos
        self.mouse_world = self.screen_to_world(pos)

        # 1. Dimension Input Handling (Klick auüƒerhalb des Panels)
        if self.dim_input_active and self.dim_input.isVisible():
            panel_geo = self.dim_input.geometry()
            click_in_panel = panel_geo.contains(pos.toPoint())
            if is_enabled("sketch_debug"):
                logger.debug(f"[CLICK] dim_input_active=True, panel at {panel_geo}, click at {pos.toPoint()}, in_panel={click_in_panel}")
            if not click_in_panel:
                if event.button() == Qt.LeftButton:
                    # Links-Klick außerhalb = Bestätigen
                    if is_enabled("sketch_debug"):
                        logger.info(f"[CLICK] Left-click outside panel → confirming dim_input")
                    self._on_dim_confirmed()
                    return
                elif event.button() == Qt.RightButton:
                    # Rechts-Klick auüƒerhalb = Abbrechen
                    if is_enabled("sketch_debug"):
                        logger.info(f"[CLICK] Right-click outside panel → canceling")
                    self.dim_input.hide()
                    self.dim_input.unlock_all()
                    self.dim_input_active = False
                    self._cancel_tool()
                    self.setFocus()
                    self.request_update()
                    return
        
        # 2. Panning (Mittelklick)
        if event.button() == Qt.MiddleButton:
            self.is_panning = True
            self.pan_start = pos
            self.setCursor(Qt.ClosedHandCursor)
            return
        
        # 3. Linksklick Interaktionen
        if event.button() == Qt.LeftButton:
            
            # A. Constraint-Icon-Klick prüfen (hüchste PrioritÄt im SELECT-Modus)
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
                    
                    self.status_message.emit(f"Constraint ausgewÄhlt: {clicked_constraint.type.name}")
                    self.request_update()
                    return

            # A1. Direct Manipulation Handle (Circle/Polygon/Rectangle) im SELECT-Modus
            if self.current_tool == SketchTool.SELECT:
                handle_hit = self._pick_direct_edit_handle(self.mouse_world)
                if handle_hit:
                    self._start_direct_edit_drag(handle_hit)
                    return

            # A1.5. Canvas-Kalibrierung (hat hüchste PrioritÄt wenn aktiv)
            if self._canvas_calibrating:
                if self._canvas_calibration_click(self.mouse_world):
                    return

            # A2. Canvas-Drag prüfen (SELECT-Modus, Canvas nicht gesperrt)
            if self.current_tool == SketchTool.SELECT and self.canvas_image and not self.canvas_locked:
                if self._canvas_hit_test(self.mouse_world):
                    if self._canvas_start_drag(self.mouse_world):
                        return

            # B. Spline-Element-Klick prüfen (hat PrioritÄt im SELECT-Modus)
            if self.current_tool == SketchTool.SELECT:
                spline_elem = self._find_spline_element_at(self.mouse_world)
                if spline_elem:
                    spline, cp_idx, elem_type = spline_elem
                    if not self._entity_passes_selection_filter(spline):
                        spline_elem = None
                if spline_elem:
                    spline, cp_idx, elem_type = spline_elem
                    self.spline_dragging = True
                    self.spline_drag_spline = spline
                    self.spline_drag_cp_index = cp_idx
                    self.spline_drag_type = elem_type
                    self.selected_splines = [spline]
                    self._save_undo()
                    self.setCursor(Qt.ClosedHandCursor)
                    self.status_message.emit(tr("Drag spline {type} | Shift=Corner").format(type=elem_type))
                    return
            
            # C. SNAPPING (Hier ist der entscheidende Fix für die Kreis-Verbindung!)
            # Wir holen uns jetzt 3 Werte: Punkt, Typ UND das Entity (Kreis/Linie)
            snapped, snap_type, snap_entity = self.snap_point(self.mouse_world)
            
            # D. Selektion (wenn kein Tool aktiv)
            if self.current_tool == SketchTool.SELECT and not self._pick_select_hit(snapped):
                # Auch Spline-Kurve selbst prüfen (Body-Klick)
                spline = self._find_spline_at(self.mouse_world)
                if spline and self._entity_passes_selection_filter(spline):
                    self._clear_selection()
                    self.selected_splines = [spline]
                    
                    # Body-Dragging initialisieren
                    self.spline_dragging = True
                    self.spline_drag_spline = spline
                    self.spline_drag_cp_index = -1
                    self.spline_drag_type = 'body'
                    self.spline_drag_start_pos = self.mouse_world
                    
                    self.setCursor(Qt.ClosedHandCursor)
                    self.status_message.emit(tr("Spline selected - drag to move"))
                    self.request_update()
                    return
                
                # Selection Box starten
                self.selection_box_start = pos
                self.selection_box_end = pos
                return
            
            # E. TOOL HANDLER AUFRUFEN
            # Wir rufen die _handle_... Methode auf und übergeben das snap_entity
            handler_name = f'_handle_{self.current_tool.name.lower()}'
            handler = getattr(self, handler_name, None)
            
            if handler:
                try:
                    # Signaturbasiert dispatchen, damit interne TypeError im Handler
                    # nicht als "falsche Argumentzahl" maskiert werden.
                    expects_snap_entity = False
                    try:
                        expects_snap_entity = len(inspect.signature(handler).parameters) >= 3
                    except Exception:
                        expects_snap_entity = False

                    if expects_snap_entity:
                        handler(snapped, snap_type, snap_entity)
                    else:
                        handler(snapped, snap_type)
                except Exception as e:
                    logger.error(f"Handler {handler_name} failed: {e}")
                    import traceback
                    traceback.print_exc()

        # 4. Rechtsklick (Abbrechen / Kontextmenü)
        elif event.button() == Qt.RightButton:
            from loguru import logger
            logger.debug(f"[MOUSE] Right Click at {pos} / World {self.mouse_world}")

            # Leerer Bereich: Rechtsklick soll immer "eine Ebene" abbrechen.
            if self._is_empty_right_click_target(pos, self.mouse_world):
                if self._cancel_right_click_empty_action():
                    logger.debug("[MOUSE] Empty right-click -> action cancelled")
                else:
                    logger.debug("[MOUSE] Empty right-click -> nothing to cancel")
                self.request_update()
                return

            if self.tool_step > 0:
                logger.debug("[MOUSE] Cancelling current tool step")
                self._finish_current_operation()
            else:
                logger.debug("[MOUSE] Showing context menu")
                self._show_context_menu(pos)
        
        self.request_update()
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self.is_panning = False
            self._update_cursor()
        if event.button() == Qt.LeftButton:
            if self._direct_edit_dragging:
                self._finish_direct_edit_drag()
                self._update_cursor()
                self.request_update()
                return
            # Spline-Dragging beenden
            if self.spline_dragging:
                self._finish_spline_drag()
                self._update_cursor()
            if self._canvas_dragging:
                self._canvas_end_drag()
            if self.selection_box_start:
                self._finish_selection_box()
        self.request_update()

    def mouseDoubleClickEvent(self, event):
        """Doppelklick auf Constraint-Icon oder Geometrie üffnet DimensionInput-Editor"""
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
                label = "üÿ"
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
                self.show_message("LÄnge: Enter = Constraint hinzufügen, Esc = Abbrechen", 2000)

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

        # Performance Optimization 2.1: Invalidiere Cache vor finaler Linien-Generierung
        if hasattr(spline, 'invalidate_cache'):
            spline.invalidate_cache()

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
            snapped, snap_type, snap_entity = self.snap_point(self.mouse_world)
            self.current_snap = (snapped, snap_type, snap_entity) if snap_type != SnapType.NONE else None
            self._emit_snap_diagnostic_feedback(snap_type)
            self._update_live_values(snapped)
            
            self.request_update() # Erzwingt komplettes Neuziehnen -> Löscht alte "Geister"
            return
        needs_full_update = False
        dirty_region = QRectF()
        
        # 1. Basis-Interaktionen
        if self.is_panning:
            self.view_offset += pos - self.pan_start
            self.pan_start = pos
            self.request_update() # Pan braucht Full Redraw
            return
            
        elif self._canvas_dragging:
            self._canvas_update_drag(self.mouse_world)
            return

        elif self._direct_edit_dragging:
            self._apply_direct_edit_drag(
                self.mouse_world,
                axis_lock=bool(event.modifiers() & Qt.ShiftModifier),
            )
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
            snapped, snap_type, snap_entity = self.snap_point(self.mouse_world)
            self._emit_snap_diagnostic_feedback(snap_type)
            
            # Snap-Update Check
            old_snap = self.current_snap
            self.current_snap = (snapped, snap_type, snap_entity)
            
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

            # Entity Hover Logic mit Selection-Filter + Overlap-Cycle
            if self.current_tool == SketchTool.SELECT:
                hover_candidates = self._update_overlap_cycle_candidates(self.mouse_world, pos)
                if hover_candidates:
                    idx = min(self._overlap_cycle_index, len(hover_candidates) - 1)
                    new_hovered = hover_candidates[idx]
                else:
                    new_hovered = None
            else:
                self._reset_overlap_cycle_state(clear_hover=False)
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
                prev_handle_sig = self._direct_handle_signature(self._direct_hover_handle)
                self._direct_hover_handle = self._pick_direct_edit_handle(self.mouse_world)
                new_handle_sig = self._direct_handle_signature(self._direct_hover_handle)
                if prev_handle_sig != new_handle_sig:
                    needs_full_update = True

                spline_elem = self._find_spline_element_at(self.mouse_world)
                if spline_elem:
                    spline, _, _ = spline_elem
                    if not self._entity_passes_selection_filter(spline):
                        spline_elem = None
                if spline_elem != self.hovered_spline_element:
                     # Spline Handle Hover changed -> Update Spline area
                     if spline_elem:
                         # bbox der ganzen spline holen (teuer, aber ok für hover change)
                         pass # TODO
                     needs_full_update = True # Einfachheitshalber
                
                self.hovered_spline_element = spline_elem
                if self._direct_hover_handle:
                    mode = self._direct_hover_handle.get("mode")
                    if mode == "center":
                        self.setCursor(Qt.OpenHandCursor)
                    elif mode == "line_edge":
                        orientation = self._direct_hover_handle.get("orientation")
                        if orientation == "horizontal":
                            self.setCursor(Qt.SizeHorCursor)
                        elif orientation == "vertical":
                            self.setCursor(Qt.SizeVerCursor)
                        else:
                            self.setCursor(Qt.SizeAllCursor)
                    elif mode == "line_move":
                        self.setCursor(Qt.OpenHandCursor)
                    else:
                        self.setCursor(Qt.SizeHorCursor)
                elif spline_elem:
                    self.setCursor(Qt.OpenHandCursor)
                else:
                    self._update_cursor()
            else:
                self._direct_hover_handle = None
                    
            # 3. Live-Werte (für Tooltips/HUD)
            self._update_live_values(snapped)

        # FINAL UPDATE CALL
        if needs_full_update:
            self.request_update()
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
        """Findet eine Kante in den Background-Bodies."""
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

        best_edge = None
        best_score = float("inf")
        depth_tol = max(float(self.reference_depth_tol), 1e-9)

        # Suche in allen Bodies
        for body in self.reference_bodies:
            edges = body.get('edges_2d', [])
            for edge in edges:
                x1, y1, x2, y2, d1, d2 = self._reference_edge_components(edge)
                if not self._is_reference_edge_visible(d1, d2):
                    continue
                # Grober Bounding Box Check zuerst (Performance)
                if px < min(x1, x2) - r or px > max(x1, x2) + r or \
                   py < min(y1, y2) - r or py > max(y1, y2) + r:
                    continue
                
                dist2 = dist_sq(px, py, x1, y1, x2, y2)
                if dist2 < r * r:
                    side_penalty = 0.0
                    if self.reference_clip_mode == "all":
                        behind = d1 < -depth_tol and d2 < -depth_tol
                        if behind:
                            side_penalty = 0.35 * (r * r)
                    score = dist2 + side_penalty
                    if score < best_score:
                        best_score = score
                        best_edge = (x1, y1, x2, y2)
        return best_edge


    def _find_spline_element_at(self, pos: QPointF, threshold=None):
        """
        Findet ein Spline-Element (Punkt, Handle) an der Position.
        Returns: (spline, index, type_str) oder None
        type_str: 'point', 'handle_in', 'handle_out'
        """
        if threshold is None:
            # FIX: Grüüƒerer Threshold für bessere Usability (v.a. bei Handles)
            threshold = 12.0 / self.view_scale
            
        px, py = pos.x(), pos.y()
        
        # Priority 1: Handles of selected splines
        for spline in self.selected_splines:
            for i, cp in enumerate(spline.control_points):
                # Handle In
                if i > 0 or spline.closed:
                    hx, hy = cp.handle_in_abs
                    if math.hypot(px - hx, py - hy) < threshold:
                         return (spline, i, 'handle_in')
                         
                # Handle Out
                if i < len(spline.control_points)-1 or spline.closed:
                    hx, hy = cp.handle_out_abs
                    if math.hypot(px - hx, py - hy) < threshold:
                         return (spline, i, 'handle_out')
        
        # Priority 2: Control Points (all splines)
        for spline in self.sketch.splines:
            for i, cp in enumerate(spline.control_points):
                if math.hypot(px - cp.point.x, py - cp.point.y) < threshold:
                    return (spline, i, 'point')
        return None

    def _find_spline_at(self, pos: QPointF, threshold=None):
        """Findet einen Spline an der gegebenen Position (World-Coordinates)."""
        if threshold is None:
            threshold = 8.0 / self.view_scale
            
        px, py = pos.x(), pos.y()
        
        for spline in self.sketch.splines:
            # Wir nutzen die gecachten Linien oder generieren sie
            lines = getattr(spline, '_lines', [])
            if not lines:
                lines = spline.to_lines(segments_per_span=10)
                spline._lines = lines # Cache update
                
            for line in lines:
                x1, y1 = line.start.x, line.start.y
                x2, y2 = line.end.x, line.end.y
                
                dx = x2 - x1
                dy = y2 - y1
                l2 = dx*dx + dy*dy
                if l2 == 0: continue
                
                t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / l2))
                dist = math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
                
                if dist < threshold:
                    return spline       
        return None

    def _drag_spline_element(self, shift_pressed):
        """Zieht ein Spline-Element und aktualisiert die Vorschau sofort"""
        if not self.spline_drag_spline:
            return
            
        spline = self.spline_drag_spline
        
        # === A. Body Dragging ===
        if self.spline_drag_type == 'body':
             # Delta berechnen
             dx = self.mouse_world.x() - self.spline_drag_start_pos.x()
             dy = self.mouse_world.y() - self.spline_drag_start_pos.y()
             
             # Alle Punkte verschieben
             for cp in spline.control_points:
                 cp.point.x += dx
                 cp.point.y += dy
                 
             # Start-Pos für nÄchstes Event updaten
             self.spline_drag_start_pos = self.mouse_world
             
             # Cache invalidieren und Linien neu berechnen
             spline.invalidate_cache()
             spline._lines = spline.to_lines(segments_per_span=10)
             self.sketched_changed.emit()
             self._find_closed_profiles()
             self.request_update()
             return

        if self.spline_drag_cp_index is None: return
        
        cp_idx = self.spline_drag_cp_index
        cp = spline.control_points[cp_idx]
        
        snapped, _, _ = self.snap_point(self.mouse_world)
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
            # Performance Optimization 2.1: Invalidiere Cache vor Neuberechnung
            if hasattr(spline, 'invalidate_cache'):
                spline.invalidate_cache()

            # Wir speichern die temporÄren Linien direkt im Spline-Objekt
            spline._preview_lines = spline.to_lines(segments_per_span=10)
            self.request_update() # Wichtig: PaintEvent neu triggern
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

        elif self.current_tool == SketchTool.ELLIPSE:
            if self.tool_step == 1:
                c = self.tool_points[0]
                dx = snapped.x() - c.x()
                dy = snapped.y() - c.y()
                if not self.dim_input.is_locked('major'):
                    self.live_length = math.hypot(dx, dy)
                    if self.dim_input.isVisible():
                        self.dim_input.set_value('major', self.live_length)
                if not self.dim_input.is_locked('angle'):
                    self.live_angle = math.degrees(math.atan2(dy, dx))
                    if self.dim_input.isVisible():
                        self.dim_input.set_value('angle', self.live_angle)
            elif self.tool_step == 2:
                center = self.tool_points[0]
                major_end = self.tool_points[1]
                dx = major_end.x() - center.x()
                dy = major_end.y() - center.y()
                major_radius = math.hypot(dx, dy)
                if major_radius > 0.01 and not self.dim_input.is_locked('minor'):
                    ux = dx / major_radius
                    uy = dy / major_radius
                    vx = -uy
                    vy = ux
                    rel_x = snapped.x() - center.x()
                    rel_y = snapped.y() - center.y()
                    self.live_radius = abs(rel_x * vx + rel_y * vy)
                    if self.dim_input.isVisible():
                        self.dim_input.set_value('minor', self.live_radius)
                
        elif self.current_tool == SketchTool.POLYGON and self.tool_step == 1:
            c = self.tool_points[0]
            if not self.dim_input.is_locked('radius'):
                self.live_radius = math.hypot(snapped.x() - c.x(), snapped.y() - c.y())
                if self.dim_input.isVisible():
                    self.dim_input.set_value('radius', self.live_radius)
            # Phase 8: Track angle for polygon rotation
            if not self.dim_input.is_locked('angle'):
                self.live_angle = math.degrees(math.atan2(snapped.y() - c.y(), snapped.x() - c.x()))
                if self.dim_input.isVisible():
                    self.dim_input.set_value('angle', self.live_angle)

        elif self.current_tool == SketchTool.SLOT:
            if self.tool_step == 1:
                # Step 1: Track length and angle from mouse
                p1 = self.tool_points[0]
                dx, dy = snapped.x() - p1.x(), snapped.y() - p1.y()
                if not self.dim_input.is_locked('length'):
                    self.live_length = math.hypot(dx, dy)
                    if self.dim_input.isVisible():
                        self.dim_input.set_value('length', self.live_length)
                if not self.dim_input.is_locked('angle'):
                    self.live_angle = math.degrees(math.atan2(dy, dx))
                    if self.dim_input.isVisible():
                        self.dim_input.set_value('angle', self.live_angle)
            elif self.tool_step == 2:
                # Step 2: Track radius (perpendicular distance from centerline)
                p1, p2 = self.tool_points[0], self.tool_points[1]
                dx_line = p2.x() - p1.x()
                dy_line = p2.y() - p1.y()
                length = math.hypot(dx_line, dy_line)
                if length > 0.01 and not self.dim_input.is_locked('radius'):
                    # Perpendicular distance from mouse to centerline
                    ux, uy = dx_line / length, dy_line / length
                    nx, ny = -uy, ux  # Normal vector
                    vx, vy = snapped.x() - p1.x(), snapped.y() - p1.y()
                    self.live_radius = abs(vx * nx + vy * ny)
                    if self.dim_input.isVisible():
                        self.dim_input.set_value('radius', self.live_radius)

        elif self.current_tool == SketchTool.NUT and self.tool_step == 1:
            # Track angle for nut rotation
            c = self.tool_points[0]
            if not self.dim_input.is_locked('angle'):
                self.live_angle = math.degrees(math.atan2(snapped.y() - c.y(), snapped.x() - c.x()))
                if self.dim_input.isVisible():
                    self.dim_input.set_value('angle', self.live_angle)

        # Phase 8: Live-Werte für Modify-Tools (MOVE, COPY, ROTATE, SCALE)
        elif self.current_tool == SketchTool.MOVE and self.tool_step == 1:
            p1 = self.tool_points[0]
            if not self.dim_input.is_locked('dx'):
                dx = snapped.x() - p1.x()
                if self.dim_input.isVisible():
                    self.dim_input.set_value('dx', dx)
            if not self.dim_input.is_locked('dy'):
                dy = snapped.y() - p1.y()
                if self.dim_input.isVisible():
                    self.dim_input.set_value('dy', dy)

        elif self.current_tool == SketchTool.COPY and self.tool_step == 1:
            # COPY benutzt die gleichen Felder wie MOVE
            p1 = self.tool_points[0]
            if not self.dim_input.is_locked('dx'):
                dx = snapped.x() - p1.x()
                if self.dim_input.isVisible():
                    self.dim_input.set_value('dx', dx)
            if not self.dim_input.is_locked('dy'):
                dy = snapped.y() - p1.y()
                if self.dim_input.isVisible():
                    self.dim_input.set_value('dy', dy)

        elif self.current_tool == SketchTool.ROTATE and self.tool_step >= 1:
            center = self.tool_points[0]
            if not self.dim_input.is_locked('angle'):
                angle = math.degrees(math.atan2(snapped.y() - center.y(), snapped.x() - center.x()))
                self.live_angle = angle
                if self.dim_input.isVisible():
                    self.dim_input.set_value('angle', angle)

        elif self.current_tool == SketchTool.SCALE and self.tool_step == 1:
            center = self.tool_points[0]
            current_dist = math.hypot(snapped.x() - center.x(), snapped.y() - center.y())
            base_dist = self.tool_data.get('base_dist', current_dist)
            if base_dist > 0.01 and not self.dim_input.is_locked('factor'):
                factor = current_dist / base_dist
                if self.dim_input.isVisible():
                    self.dim_input.set_value('factor', factor)

    def wheelEvent(self, event):
        pos = event.position()
        world_pos = self.screen_to_world(pos)
        
        # === Phase 19: NURBS Weight Editing ===
        # Wenn Maus über einem Spline-Punkt ist -> Gewicht Ändern statt Zoomen
        spline_elem = self._find_spline_element_at(world_pos)
        if spline_elem and spline_elem[2] == 'point':
            spline, idx, _ = spline_elem
            cp = spline.control_points[idx]
            
            delta = event.angleDelta().y()
            if delta != 0:
                factor = 1.1 if delta > 0 else 0.9
                # Limit weight (0.1 bis 100.0)
                new_weight = max(0.1, min(100.0, cp.weight * factor))
                
                if abs(new_weight - cp.weight) > 0.001:
                    cp.weight = new_weight
                    spline.invalidate_cache() # Kurve neu berechnen
                    self.sketched_changed.emit()
                    self.status_message.emit(f"Spline Point Weight: {new_weight:.2f}")
                    self.request_update()
            
            event.accept()
            return
            
        # Standard Zoom
        world_before = world_pos
        factor = 1.15 if event.angleDelta().y() > 0 else 1/1.15
        self.view_scale = max(0.5, min(200, self.view_scale * factor))
        self._emit_zoom_changed()
        world_after = self.screen_to_world(pos)
        
        # Offset anpassen damit Zoom zur Mausposition geht
        dx = (world_after.x() - world_before.x()) * self.view_scale
        dy = -(world_after.y() - world_before.y()) * self.view_scale
        self.view_offset += QPointF(dx, dy)
        
        self.request_update()
    
    
    def keyPressEvent(self, event):
        key, mod = event.key(), event.modifiers()
        if key == Qt.Key_Escape:
            logger.debug("[sketch_editor] Escape Keypress")
            self._handle_escape_logic()
            return

        # Shift+R: Ansicht um 90° drehen
        if key == Qt.Key_R and (mod & Qt.ShiftModifier):
            self.rotate_view()
            return

        # Shift+C: Clip-Modus fuer Referenzkanten umschalten.
        if key == Qt.Key_C and (mod & Qt.ShiftModifier):
            self._cycle_reference_clip_mode()
            return

        # [ / ]: Section-Band Breite fuer Referenz-Clip.
        if key == Qt.Key_BracketLeft:
            self._adjust_reference_section_thickness(-0.25)
            return
        if key == Qt.Key_BracketRight:
            self._adjust_reference_section_thickness(0.25)
            return

        # Space: 3D-Peek (zeigt temporÄr 3D-Viewport)
        if key == Qt.Key_Space and not event.isAutoRepeat():
            self._peek_3d_active = True
            self._hint_context = 'peek_3d'
            self.peek_3d_requested.emit(True)
            return

        # Phase 8: Direct Number Input - forward numbers to dimension input
        if not (mod & Qt.ControlModifier):
            if self._try_forward_to_dim_input(event):
                return

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
            # Phase 8: Handle direct number input when panel is visible
            # If the active field is unlocked and user types a digit, select all first
            # so Qt will replace instead of append
            char = event.text()
            if char and (char in "0123456789.,+-*/()^" or char.isalpha() or char == "_"):
                active_key = self.dim_input.get_active_field_key()
                if active_key and not self.dim_input.is_locked(active_key):
                    # Select all so the next character replaces
                    self.dim_input.select_active_field()
                    # Let Qt handle the key normally (it will replace selection)
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
            # W33: Verhindere Undo/Redo während aktiver Direct-Edit-Drag-Operation
            if key == Qt.Key_Z:
                if self._direct_edit_dragging:
                    self._show_hud(tr("Nicht während Drag verfügbar"))
                    return
                self.undo()
                return
            elif key == Qt.Key_Y:
                if self._direct_edit_dragging:
                    self._show_hud(tr("Nicht während Drag verfügbar"))
                    return
                self.redo()
                return
            elif key == Qt.Key_A: self._select_all(); return
            elif key == Qt.Key_I: self.import_dxf(); return
            elif key == Qt.Key_E: self.export_dxf(); return
            elif key == Qt.Key_B: self._canvas_toggle_visible(); return

        if key == Qt.Key_W and self.current_tool == SketchTool.SELECT:
            self._cycle_selection_filter()
            self._show_tool_hint()
            return
        
        if key == Qt.Key_Tab:
            if self.current_tool == SketchTool.SELECT and self._cycle_overlap_candidate():
                return
            self._show_dimension_input()
            return
        
        shortcuts = {
            #Qt.Key_Escape: lambda: self._cancel_tool() if self.tool_step > 0 else self.set_tool(SketchTool.SELECT),
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
            Qt.Key_Y: self._repeat_last_tool,      # Y = letztes Werkzeug wiederholen
            Qt.Key_Plus: self._increase_tolerance,   # + für Toleranz erhühen
            Qt.Key_Minus: self._decrease_tolerance,  # - für Toleranz verringern
            Qt.Key_P: lambda: self.set_tool(SketchTool.PROJECT), # <--- NEU
        }

        # W33: Separate Navigation Shortcuts (werden zuerst verarbeitet)
        if key == Qt.Key_Home:
            self._reset_view_to_origin()
            return
        # 0-Taste auch für Origin Reset (wie CAD-Standard)
        if key == Qt.Key_0 and not (mod & Qt.ControlModifier):
            self._reset_view_to_origin()
            return

        if key in shortcuts: shortcuts[key](); self.request_update()


    def _handle_escape_logic(self):
        """
        Hierarchisches Beenden von Aktionen (CAD-Style).
        Jeder Escape bricht nur EINE Ebene ab:
        0. Direct-Edit-Drag abbrechen (W14 Fixup)
        1. Canvas-Kalibrierung abbrechen
        2. Laufende Geometrie-Erstellung abbrechen (tool_step > 0)
        3. Aktives Tool beenden → SELECT
        4. Auswahl aufheben
        5. Signal an main_window → Sketch verlassen
        """
        # Level 0: Direct-Edit-Drag abbrechen (W14 Fixup, W25: Zentralisiert)
        if self._direct_edit_dragging:
            self._reset_direct_edit_state()
            self._update_cursor()
            self._show_hud(tr("Direktes Bearbeiten abgebrochen"))
            self._show_tool_hint()
            self.request_update()
            return

        # Level 1: Canvas-Kalibrierung abbrechen
        if self._canvas_calibrating:
            self._canvas_calibrating = False
            self._canvas_calib_points = []
            self._show_hud(tr("Kalibrierung abgebrochen"))
            self.request_update()
            return

        # Level 2: Laufende Operation abbrechen (z.B. Linie hat Startpunkt)
        if self.tool_step > 0:
            # W33: Spline mit >=2 Punkten wird finalisiert, nicht abgebrochen
            if self.current_tool == SketchTool.SPLINE and len(self.tool_points) >= 2:
                self._finish_spline()
                self.status_message.emit(tr("Spline erstellt"))
                return
            self._cancel_tool()
            self.status_message.emit(tr("Aktion abgebrochen"))
            return

        # Level 3: Aktives Tool beenden (zurück zu Select)
        if self.current_tool != SketchTool.SELECT:
            self.set_tool(SketchTool.SELECT)
            self.status_message.emit(tr("Werkzeug deaktiviert"))
            return

        # Level 4: Selektion aufheben
        if (self.selected_lines or self.selected_points or self.selected_circles
                or self.selected_arcs or self.selected_constraints or self.selected_splines):
            self._clear_selection()
            self.request_update()
            return

        # Level 5: Sketch verlassen — Signal an main_window
        # W26 FIX: Clear projection preview when leaving sketch
        if self._last_projection_edge is not None:
            self._last_projection_edge = None
            self.projection_preview_cleared.emit()
        self.exit_requested.emit()
            
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
        self.request_update()
    
    def _toggle_construction(self):
        self.construction_mode = not self.construction_mode
        state = tr("ON") if self.construction_mode else tr("OFF")
        self.status_message.emit(tr("Construction: {state}").format(state=state))

        # WICHTIG: Signal senden, damit die Checkbox im ToolPanel aktualisiert wird
        self.construction_mode_changed.emit(self.construction_mode)
        self.request_update()

    def keyReleaseEvent(self, event):
        """Handle key release - z.B. für 3D-Peek (Space loslassen)."""
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._peek_3d_active = False
            self._hint_context = 'sketch'
            self.peek_3d_requested.emit(False)  # Zurück zum Sketch
            return
        super().keyReleaseEvent(event)

    def _increase_tolerance(self):
        """Toleranz für Muttern erhühen"""
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
        self.selected_ellipses.clear()
        self.selected_polygons.clear()
        self.selected_points.clear()
        self.selected_constraints.clear()
        self.selected_splines.clear()
    
    def _select_all(self):
        self._clear_selection()
        self.selected_lines = [line for line in self.sketch.lines if self._entity_passes_selection_filter(line)]
        self.selected_circles = [circle for circle in self.sketch.circles if self._entity_passes_selection_filter(circle)]
        self.selected_arcs = [arc for arc in self.sketch.arcs if self._entity_passes_selection_filter(arc)]
        # Nur standalone Punkte (nicht Teil anderer Geometrie)
        used_point_ids = set()
        for line in self.sketch.lines:
            used_point_ids.add(line.start.id)
            used_point_ids.add(line.end.id)
        for circle in self.sketch.circles:
            used_point_ids.add(circle.center.id)
        for arc in self.sketch.arcs:
            used_point_ids.add(arc.center.id)
        self.selected_points = [
            p for p in self.sketch.points
            if p.id not in used_point_ids and self._entity_passes_selection_filter(p)
        ]
        self.selected_splines = [s for s in self.sketch.splines if self._entity_passes_selection_filter(s)]
        self.request_update()

    def _finish_selection_box(self):
        if not self.selection_box_start or not self.selection_box_end: return
        x1, y1 = self.selection_box_start.x(), self.selection_box_start.y()
        x2, y2 = self.selection_box_end.x(), self.selection_box_end.y()
        rect = QRectF(min(x1,x2), min(y1,y2), abs(x2-x1), abs(y2-y1))
        if not (QApplication.keyboardModifiers() & Qt.ShiftModifier): self._clear_selection()
        for line in self.sketch.lines:
            if not self._entity_passes_selection_filter(line):
                continue
            p1 = self.world_to_screen(QPointF(line.start.x, line.start.y))
            p2 = self.world_to_screen(QPointF(line.end.x, line.end.y))
            if rect.contains(p1) and rect.contains(p2) and line not in self.selected_lines:
                self.selected_lines.append(line)
        for circle in self.sketch.circles:
            if not self._entity_passes_selection_filter(circle):
                continue
            center = self.world_to_screen(QPointF(circle.center.x, circle.center.y))
            r = circle.radius * self.view_scale
            if rect.contains(QRectF(center.x()-r, center.y()-r, 2*r, 2*r)) and circle not in self.selected_circles:
                self.selected_circles.append(circle)
        for arc in self.sketch.arcs:
            if not self._entity_passes_selection_filter(arc):
                continue
            center = self.world_to_screen(QPointF(arc.center.x, arc.center.y))
            r = arc.radius * self.view_scale
            if rect.contains(QRectF(center.x()-r, center.y()-r, 2*r, 2*r)) and arc not in self.selected_arcs:
                self.selected_arcs.append(arc)
        # Standalone Punkte
        used_point_ids = self._get_used_point_ids()
        for pt in self.sketch.points:
            if pt.id not in used_point_ids:
                if not self._entity_passes_selection_filter(pt):
                    continue
                pos = self.world_to_screen(QPointF(pt.x, pt.y))
                if rect.contains(pos) and pt not in self.selected_points:
                    self.selected_points.append(pt)
        for spline in self.sketch.splines:
            if not self._entity_passes_selection_filter(spline):
                continue
            all_inside = True
            for cp in spline.control_points:
                sp = self.world_to_screen(QPointF(cp.point.x, cp.point.y))
                if not rect.contains(sp):
                    all_inside = False
                    break
            if all_inside and spline not in self.selected_splines:
                self.selected_splines.append(spline)
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
        # Zuerst Constraints lüschen
        if self.selected_constraints:
            self._save_undo()
            count = len(self.selected_constraints)
            for c in self.selected_constraints[:]:
                if c in self.sketch.constraints:
                    self.sketch.constraints.remove(c)
            self.selected_constraints.clear()
            solve_result = self.sketch.solve()
            if not solve_result.success:
                logger.warning(f"Solver nach Constraint-Lüschung nicht konvergiert: {solve_result.message}")
            self.sketched_changed.emit()
            self.show_message(f"{count} Constraint(s) gelüscht", 2000, QColor(100, 255, 100))
            logger.debug(f"Deleted {count} constraints")
            self.request_update()
            return

        if not self.selected_lines and not self.selected_circles and not self.selected_arcs and not self.selected_points and not self.selected_splines:
            return
        self._save_undo()
        deleted_count = len(self.selected_lines) + len(self.selected_circles) + len(self.selected_arcs) + len(self.selected_points) + len(self.selected_splines)
        for line in self.selected_lines[:]:
            self.sketch.delete_line(line)
        for circle in self.selected_circles[:]:
            self.sketch.delete_circle(circle)
        for arc in self.selected_arcs[:]:
            self.sketch.delete_arc(arc)
        for pt in self.selected_points[:]:
            if pt in self.sketch.points:
                self.sketch.points.remove(pt)
        for spline in self.selected_splines[:]:
            if spline in self.sketch.splines:
                self.sketch.splines.remove(spline)
        self._clear_selection()
        self._find_closed_profiles()
        self.sketched_changed.emit()
        self.show_message(f"{deleted_count} Element(e) gelüscht", 2000, QColor(100, 255, 100))
        logger.debug(f"Deleted {deleted_count} elements")
        self.request_update()

    def _find_constraint_at(self, screen_pos):
        """Findet einen Constraint dessen Icon an der Screen-Position liegt"""
        if not hasattr(self, 'constraint_icon_rects'):
            return None
        for constraint, rect in self.constraint_icon_rects:
            if rect.contains(screen_pos):
                return constraint
        return None

    @staticmethod
    def _entity_kind(entity):
        if isinstance(entity, Line2D):
            return "line"
        if isinstance(entity, Circle2D):
            return "circle"
        if isinstance(entity, Arc2D):
            return "arc"
        if isinstance(entity, Point2D):
            return "point"
        if hasattr(entity, "control_points"):
            return "spline"
        return "unknown"

    def _selection_filter_label(self, mode: Optional[str] = None) -> str:
        key = mode or self.selection_filter_mode
        return self.SELECTION_FILTER_LABELS.get(key, str(key))

    def _entity_passes_selection_filter(self, entity) -> bool:
        mode = getattr(self, "selection_filter_mode", "all")
        if mode == "all":
            return True
        return self._entity_kind(entity) == mode

    def _entity_pick_priority(self, entity) -> int:
        # Linien/Flaechenkanten zuerst, Punkte zuletzt, damit Selektion stabil bleibt.
        kind = self._entity_kind(entity)
        return {
            "line": 0,
            "circle": 1,
            "arc": 2,
            "spline": 3,
            "point": 4,
        }.get(kind, 99)

    def _entity_distance_to_pos(self, entity, pos: QPointF) -> float:
        dist = self._safe_float("inf")

        if isinstance(entity, Line2D):
            dist = entity.distance_to_point(Point2D(pos.x(), pos.y()))
            return float(dist)

        if isinstance(entity, (Circle2D, Arc2D)):
            center_dist = math.hypot(entity.center.x - pos.x(), entity.center.y - pos.y())
            dist = abs(center_dist - entity.radius)
            if isinstance(entity, Arc2D):
                angle = math.degrees(math.atan2(pos.y() - entity.center.y, pos.x() - entity.center.x)) % 360
                s = entity.start_angle % 360
                e = entity.end_angle % 360
                in_arc = (s <= e and s <= angle <= e) or (s > e and (angle >= s or angle <= e))
                if not in_arc:
                    return self._safe_float("inf")
            return float(dist)

        if hasattr(entity, "control_points"):
            pts = entity.get_curve_points(segments_per_span=10)
            px, py = pos.x(), pos.y()
            best = self._safe_float("inf")
            for i in range(len(pts) - 1):
                x1, y1 = pts[i]
                x2, y2 = pts[i + 1]
                line_len_sq = (x2 - x1) ** 2 + (y2 - y1) ** 2
                if line_len_sq < 1e-12:
                    continue
                t = max(0.0, min(1.0, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / line_len_sq))
                cx = x1 + t * (x2 - x1)
                cy = y1 + t * (y2 - y1)
                best = min(best, math.hypot(px - cx, py - cy))
            return float(best)

        if isinstance(entity, Point2D):
            return float(math.hypot(entity.x - pos.x(), entity.y - pos.y()))

        return self._safe_float("inf")

    def _find_entities_at(self, pos: QPointF, apply_selection_filter: bool = False):
        """
        Liefert alle treffenden Entitaeten an Position `pos`, sortiert nach Distanz + Prioritaet.
        """
        if self.index_dirty:
            self._rebuild_spatial_index()

        r_world = self.snap_radius / self.view_scale
        query_rect = QRectF(pos.x() - r_world, pos.y() - r_world, r_world * 2, r_world * 2)

        if self.spatial_index:
            broad_candidates = list(self.spatial_index.query(query_rect))
        else:
            broad_candidates = list(self.sketch.lines) + list(self.sketch.circles) + list(self.sketch.arcs) + list(self.sketch.splines)

        hits = []
        seen = set()
        for entity in broad_candidates:
            ent_id = id(entity)
            if ent_id in seen:
                continue
            seen.add(ent_id)

            if apply_selection_filter and not self._entity_passes_selection_filter(entity):
                continue

            dist = self._entity_distance_to_pos(entity, pos)
            if dist <= r_world:
                hits.append((dist, self._entity_pick_priority(entity), ent_id, entity))

        used_point_ids = self._get_used_point_ids()
        for point in self.sketch.points:
            if point.id in used_point_ids:
                continue
            if apply_selection_filter and not self._entity_passes_selection_filter(point):
                continue
            dist = self._entity_distance_to_pos(point, pos)
            if dist <= r_world:
                hits.append((dist, self._entity_pick_priority(point), id(point), point))

        hits.sort(key=lambda row: (row[0], row[1], row[2]))
        return [row[3] for row in hits]

    def _find_entity_at(self, pos, apply_selection_filter: bool = False):
        entities = self._find_entities_at(pos, apply_selection_filter=apply_selection_filter)
        return entities[0] if entities else None

    @staticmethod
    def _entities_signature(entities) -> tuple:
        return tuple(id(e) for e in entities)

    def _reset_overlap_cycle_state(self, clear_hover: bool = False):
        self._overlap_cycle_candidates = []
        self._overlap_cycle_signature = ()
        self._overlap_cycle_index = 0
        self._overlap_cycle_anchor_screen = QPointF(-1.0, -1.0)
        self._overlap_cycle_anchor_world = QPointF()
        if clear_hover:
            self.hovered_entity = None
            self._last_hovered_entity = None

    def _is_same_overlap_anchor(self, screen_pos: QPointF) -> bool:
        dx = screen_pos.x() - self._overlap_cycle_anchor_screen.x()
        dy = screen_pos.y() - self._overlap_cycle_anchor_screen.y()
        return (dx * dx + dy * dy) <= (self._overlap_cycle_anchor_radius_px ** 2)

    def _update_overlap_cycle_candidates(self, world_pos: QPointF, screen_pos: QPointF):
        candidates = self._find_entities_at(world_pos, apply_selection_filter=True)
        signature = self._entities_signature(candidates)
        same_anchor = self._is_same_overlap_anchor(screen_pos)

        if signature != self._overlap_cycle_signature or not same_anchor:
            self._overlap_cycle_signature = signature
            self._overlap_cycle_candidates = candidates
            self._overlap_cycle_index = 0
            self._overlap_cycle_anchor_world = QPointF(world_pos.x(), world_pos.y())
            self._overlap_cycle_anchor_screen = QPointF(screen_pos.x(), screen_pos.y())
        else:
            self._overlap_cycle_candidates = candidates
            if self._overlap_cycle_candidates:
                self._overlap_cycle_index = min(self._overlap_cycle_index, len(self._overlap_cycle_candidates) - 1)
            else:
                self._overlap_cycle_index = 0

        return self._overlap_cycle_candidates

    def _pick_select_hit(self, world_pos: QPointF):
        screen_pos = self.world_to_screen(world_pos)
        candidates = self._update_overlap_cycle_candidates(world_pos, screen_pos)
        if not candidates:
            return None
        idx = min(self._overlap_cycle_index, len(candidates) - 1)
        return candidates[idx]

    def _cycle_overlap_candidate(self) -> bool:
        if self.current_tool != SketchTool.SELECT:
            return False
        candidates = self._update_overlap_cycle_candidates(self.mouse_world, self.mouse_screen)
        if len(candidates) <= 1:
            return False

        self._overlap_cycle_index = (self._overlap_cycle_index + 1) % len(candidates)
        target = candidates[self._overlap_cycle_index]
        self.hovered_entity = target
        self._last_hovered_entity = target
        kind = self._entity_kind(target)
        self.status_message.emit(
            tr("Overlap cycle: {idx}/{total} ({kind})").format(
                idx=self._overlap_cycle_index + 1,
                total=len(candidates),
                kind=kind,
            )
        )
        self._update_cursor()
        self.request_update()
        return True

    def _set_selection_filter_mode(self, mode: str, announce: bool = True):
        if mode not in self.SELECTION_FILTER_ORDER:
            return
        if mode == self.selection_filter_mode:
            return

        self.selection_filter_mode = mode
        self._reset_overlap_cycle_state(clear_hover=True)
        if announce:
            label = self._selection_filter_label(mode)
            self.status_message.emit(tr("Selection filter: {label}").format(label=label))
        self.request_update()

    def _cycle_selection_filter(self):
        order = list(self.SELECTION_FILTER_ORDER)
        try:
            idx = order.index(self.selection_filter_mode)
        except ValueError:
            idx = 0
        self._set_selection_filter_mode(order[(idx + 1) % len(order)], announce=True)

    def _repeat_last_tool(self):
        tool = getattr(self, "_last_non_select_tool", SketchTool.SELECT)
        if tool == SketchTool.SELECT:
            self.status_message.emit(tr("No previous tool to repeat"))
            return
        self.set_tool(tool)
        self.status_message.emit(tr("Repeat tool: {tool}").format(tool=tool.name))
    
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
        """Findet die FlÄche unter dem Cursor (Point-in-Polygon Test)"""
        px, py = pos.x(), pos.y()

        for profile_data in self.closed_profiles:
            if not isinstance(profile_data, tuple) or len(profile_data) < 2:
                continue

            # Handle both 2-tuple and 3-tuple formats
            profile_type = profile_data[0]
            data = profile_data[1]
            
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
        menu.setStyleSheet(DesignTokens.stylesheet_sketch())

        has_selection = bool(
            self.selected_lines or self.selected_circles or self.selected_arcs
            or self.selected_points or self.selected_splines
        )

        if self.current_tool == SketchTool.SELECT:
            filter_menu = menu.addMenu("Selection Filter")
            for mode in self.SELECTION_FILTER_ORDER:
                action = filter_menu.addAction(self._selection_filter_label(mode))
                action.setCheckable(True)
                action.setChecked(mode == self.selection_filter_mode)
                action.triggered.connect(lambda checked=False, m=mode: self._set_selection_filter_mode(m))
            filter_menu.addSeparator()
            filter_menu.addAction("Cycle Filter (W)", self._cycle_selection_filter)
            if len(self._overlap_cycle_candidates) > 1:
                menu.addAction(
                    f"Cycle Overlap (Tab) [{self._overlap_cycle_index + 1}/{len(self._overlap_cycle_candidates)}]",
                    self._cycle_overlap_candidate,
                )
            menu.addSeparator()

        # === Constraint-Optionen ===
        if self.selected_lines:
            menu.addAction("Horizontal (H)", lambda: self._apply_constraint('horizontal'))
            menu.addAction("Vertikal (V)", lambda: self._apply_constraint('vertical'))
            if len(self.selected_lines) >= 2:
                menu.addAction("Parallel (P)", lambda: self._apply_constraint('parallel'))
                menu.addAction("Senkrecht", lambda: self._apply_constraint('perpendicular'))
                menu.addAction("Gleiche LÄnge (E)", lambda: self._apply_constraint('equal'))
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
                    f"Constraints der Auswahl lüschen ({len(selection_constraints)})",
                    lambda: self._delete_constraints_of_selection()
                )
            menu.addSeparator()

        # Globale Constraint-Verwaltung
        if self.sketch.constraints:
            menu.addAction(
                f"Alle Constraints lüschen ({len(self.sketch.constraints)})",
                self._delete_all_constraints
            )
            menu.addSeparator()

        # === Spline-Optionen ===
        # WICHTIG: pos ist Screen-Coordinates, wir brauchen World-Coordinates für Detection
        world_pos = self.screen_to_world(pos)
        
        # Prüfe ob Spline-Element unter Cursor
        spline_elem = self._find_spline_element_at(world_pos)
        if spline_elem:
            spline, idx, elem_type = spline_elem
            if elem_type == 'point':
                menu.addAction("Spline-Punkt lüschen", lambda: self._delete_spline_point(spline, idx))
                menu.addSeparator()
        
        # Prüfe ob Spline-Kurve unter Cursor oder selektiert
        hover_spline = self._find_spline_at(world_pos)
        target_splines = set(self.selected_splines)
        if hover_spline:
            target_splines.add(hover_spline)
        
        if target_splines:
            menu.addSection("Spline")
            for sp in target_splines:
                if sp.closed:
                    menu.addAction("Spline üffnen", lambda s=sp: self._toggle_spline_closed(s, False))
                else:
                    menu.addAction("Spline schlieüƒen", lambda s=sp: self._toggle_spline_closed(s, True))
            
            if hover_spline:
                 menu.addAction("Punkt einfügen", lambda: self._insert_spline_point(hover_spline, world_pos))

            # Curvature Comb Toggle
            any_curvature_visible = any(getattr(sp, 'show_curvature', False) for sp in target_splines)
            curv_label = "Krümmungsanalyse ausblenden" if any_curvature_visible else "Krümmungsanalyse anzeigen"
            
            def toggle_curvature(splines=target_splines, state=not any_curvature_visible):
                for sp in splines:
                    setattr(sp, 'show_curvature', state)
                self.request_update()
            
            menu.addAction(curv_label, toggle_curvature)
            
            menu.addSeparator()

        if self.reference_bodies:
            clip_labels = {"all": "All", "front": "Front only", "section": "Section band"}
            clip_menu = menu.addMenu("Reference Clip")
            for mode in ("all", "front", "section"):
                action = clip_menu.addAction(clip_labels.get(mode, mode))
                action.setCheckable(True)
                action.setChecked(mode == self.reference_clip_mode)
                action.triggered.connect(lambda checked=False, m=mode: self._set_reference_clip_mode(m, announce=True))
            clip_menu.addSeparator()
            clip_menu.addAction("Cycle Mode (Shift+C)", self._cycle_reference_clip_mode)
            clip_menu.addAction("Band +0.25 mm (])", lambda: self._adjust_reference_section_thickness(+0.25))
            clip_menu.addAction("Band -0.25 mm ([)", lambda: self._adjust_reference_section_thickness(-0.25))
            menu.addSeparator()

        # === Standard-Aktionen ===
        if has_selection:
            menu.addAction("Löschen (Del)", self._delete_selected)
            menu.addSeparator()

        if self.current_tool == SketchTool.SELECT:
            menu.addAction("Repeat Last Tool (Y)", self._repeat_last_tool)
            menu.addSeparator()

        menu.addAction("Alles auswählen (Ctrl+A)", self._select_all)
        menu.addAction("Ansicht einpassen (F)", self._fit_view)

        # === Canvas-Optionen ===
        if self.canvas_image is not None:
            menu.addSeparator()
            canvas_menu = menu.addMenu("▶ Canvas")

            vis_text = "Ausblenden" if self.canvas_visible else "Einblenden"
            canvas_menu.addAction(vis_text, self._canvas_toggle_visible)

            lock_text = "Entsperren" if self.canvas_locked else "Sperren"
            canvas_menu.addAction(lock_text, self._canvas_toggle_locked)

            # Opacity sub-menu
            opacity_menu = canvas_menu.addMenu("Deckkraft")
            for pct in [10, 20, 30, 40, 50, 60, 70, 80, 90]:
                val = pct / 100.0
                label = f"{pct}%" + (" ✓" if abs(self.canvas_opacity - val) < 0.05 else "")
                opacity_menu.addAction(label, lambda v=val: self.canvas_set_opacity(v))

            # Size sub-menu
            size_menu = canvas_menu.addMenu("Größe (mm)")
            for sz in [50, 100, 150, 200, 300, 500]:
                size_menu.addAction(f"{sz} mm", lambda s=sz: self.canvas_set_size(float(s)))

            canvas_menu.addSeparator()
            canvas_menu.addAction("Kalibrieren (2 Punkte)", self.canvas_start_calibration)
            canvas_menu.addSeparator()
            canvas_menu.addAction("Entfernen", self.canvas_remove)

        # Show menu at global position
        from loguru import logger
        global_pos = self.mapToGlobal(pos.toPoint())
        logger.debug(f"[MENU] Showing Context Menu with {len(menu.actions())} actions at {global_pos} (Size: {menu.sizeHint()})")
        menu.exec(global_pos)

    def _delete_spline_point(self, spline, idx):
        if len(spline.control_points) <= 2:
            self.show_message("Spline muss mindestens 2 Punkte haben", 2000, QColor(255, 100, 100))
            return
        
        self._save_undo()
        spline.control_points.pop(idx)
        # Re-calc lines
        spline._lines = spline.to_lines(segments_per_span=10)
        self.sketched_changed.emit()
        self._find_closed_profiles()
        self.request_update()
        
    def _toggle_spline_closed(self, spline, closed):
        self._save_undo()
        spline.closed = closed
        # Re-calc lines
        spline._lines = spline.to_lines(segments_per_span=10)
        self.sketched_changed.emit()
        self._find_closed_profiles()
        self.request_update()

    def _insert_spline_point(self, spline, pos):
        # Finde besten Einfüge-Punkt (Index)
        # Wir suchen das Segment, dem der Punkt am nÄchsten ist
        pts = spline.get_curve_points(segments_per_span=10)
        best_idx = -1
        min_dist = self._safe_float('inf')
        
        px, py = pos.x(), pos.y()
        
        # Mapping von curve-points zu control-points ist nicht trivial bei Bezier.
        # Einfacherer Ansatz: Finde den Control-Point, nach dem wir einfügen sollten.
        # Wir iterieren durch die Segmente der Kurve.
        
        # Besser: Wir fügen den Punkt einfach da ein, wo er geometrisch am besten passt?
        # Nein, bei Bezier splines ist die Reihenfolge wichtig.
        
        # Workaround: Wir suchen die nÄchstgelegene Stelle auf der Kurve (t-Wert) 
        # und fügen dort einen Control Point ein?
        # Das würde die Kurve verÄndern.
        
        # Einfachster UX-Ansatz:
        # Finde Segment i -> i+1, das dem Klick am nÄchsten ist.
        
        for i in range(len(spline.control_points) - (0 if spline.closed else 1)):
            p1 = spline.control_points[i].point
            p2 = spline.control_points[(i + 1) % len(spline.control_points)].point
            
            # Prüfe Abstand zu Segment p1-p2 (als Linie genÄhert)
            dx = p2.x - p1.x
            dy = p2.y - p1.y
            l2 = dx*dx + dy*dy
            if l2 == 0: continue
            
            t = ((px - p1.x) * dx + (py - p1.y) * dy) / l2
            t = max(0, min(1, t))
            dist = math.hypot(px - (p1.x + t * dx), py - (p1.y + t * dy))
            
            if dist < min_dist:
                min_dist = dist
                best_idx = i
        
        if best_idx != -1:
            self._save_undo()
            
            # Remove OLD lines from sketch to prevent "ghost lines"
            # Note: spline._lines contains the objects that are currently in self.sketch.lines
            if hasattr(spline, '_lines'):
                for line in spline._lines:
                    if line in self.sketch.lines:
                        self.sketch.lines.remove(line)
            
            # Insert AFTER best_idx
            spline.insert_point(best_idx + 1, px, py)
            
            # Generate NEW lines and add to sketch
            new_lines = spline.to_lines(segments_per_span=10)
            spline._lines = new_lines
            self.sketch.lines.extend(new_lines)
            
            self.sketched_changed.emit()
            self._find_closed_profiles()
            self.request_update()

    def _get_constraints_for_selection(self):
        """Sammelt alle Constraints die zur aktuellen Auswahl gehüren"""
        selected_entities = set()
        for line in self.selected_lines:
            selected_entities.add(id(line))
        for circle in self.selected_circles:
            selected_entities.add(id(circle))
        for arc in self.selected_arcs:
            selected_entities.add(id(arc))
        for point in self.selected_points:
            selected_entities.add(id(point))

        matching = []
        for c in self.sketch.constraints:
            for entity in c.entities:
                if id(entity) in selected_entities:
                    if c not in matching:
                        matching.append(c)
                    break
        return matching

    def _delete_constraints_of_selection(self):
        """Lüscht alle Constraints der aktuell ausgewÄhlten Elemente"""
        constraints_to_delete = self._get_constraints_for_selection()
        if not constraints_to_delete:
            self.show_message("Keine Constraints zu lüschen", 2000, QColor(255, 200, 100))
            return

        self._save_undo()
        count = len(constraints_to_delete)
        for c in constraints_to_delete:
            if c in self.sketch.constraints:
                self.sketch.constraints.remove(c)

        solve_result = self.sketch.solve()
        if not solve_result.success:
            logger.warning(f"Solver nach Constraint-Lüschung nicht konvergiert: {solve_result.message}")
        self.sketched_changed.emit()
        self.show_message(f"{count} Constraint(s) gelüscht", 2000, QColor(100, 255, 100))
        logger.info(f"Deleted {count} constraints from selection")
        self.request_update()

    def _delete_all_constraints(self):
        """Lüscht alle Constraints im Sketch"""
        if not self.sketch.constraints:
            self.show_message("Keine Constraints vorhanden", 2000, QColor(255, 200, 100))
            return

        self._save_undo()
        count = len(self.sketch.constraints)
        self.sketch.constraints.clear()
        self.sketched_changed.emit()
        self.show_message(f"Alle {count} Constraints gelüscht", 2000, QColor(100, 255, 100))
        logger.info(f"Deleted all {count} constraints")
        self.request_update()
    
    def _canvas_toggle_visible(self):
        self.canvas_visible = not self.canvas_visible
        self.request_update()

    def _canvas_toggle_locked(self):
        self.canvas_locked = not self.canvas_locked
        state = tr("gesperrt") if self.canvas_locked else tr("entsperrt")
        self._show_hud(f"Canvas {state}")

    def _emit_zoom_changed(self):
        """W32: Emit current view_scale for consistent zoom display."""
        self.zoom_changed.emit(self.view_scale)

    def set_zoom_to(self, scale: float):
        """W32: Set zoom to a specific view_scale. Called from status bar presets."""
        self.view_scale = max(0.5, min(200, scale))
        self._emit_zoom_changed()
        self.request_update()

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
        self._emit_zoom_changed()
        self.request_update()

    def _reset_view_to_origin(self):
        """
        W33: Setzt die Ansicht auf den Koordinatenursprung (0,0) zurück.
        Zentriert den Ursprung und setzt einen sinnvollen Standard-Zoom.
        """
        # Ursprung in die Mitte des Viewports
        self.view_offset = QPointF(self.width() / 2, self.height() / 2)
        # Rotation zurücksetzen
        self.view_rotation = 0
        # Sinnvoller Standard-Zoom (1.0 = 1:1)
        self.view_scale = 1.0
        self._emit_zoom_changed()
        self.request_update()
        from loguru import logger
        logger.debug("[Sketch] View reset to origin (0,0)")
        self.show_message(tr("View reset to origin"), duration=1500)

    def _draw_direct_edit_handles(self, painter):
        """
        W20 P1: Zeichnet Direct-Edit Handles für Circle, Arc, Line, Rectangle.
        """
        if self.current_tool != SketchTool.SELECT:
            return
        
        handle_radius = 6
        
        # Circle Handles
        circle, source = self._resolve_direct_edit_target_circle()
        if circle is not None:
            center_screen = self.world_to_screen(circle.center)
            
            # Center Handle (green square)
            painter.setPen(QPen(QColor(0, 255, 0), 2))
            painter.setBrush(QColor(0, 255, 0, 128))
            painter.drawRect(int(center_screen.x() - handle_radius), 
                           int(center_screen.y() - handle_radius),
                           handle_radius * 2, handle_radius * 2)
            
            # Radius Handle (blue circle)
            dx = self.mouse_world.x() - circle.center.x
            dy = self.mouse_world.y() - circle.center.y
            angle = math.atan2(dy, dx) if (abs(dx) > 1e-9 or abs(dy) > 1e-9) else 0.0
            radius_point = Point2D(
                circle.center.x + circle.radius * math.cos(angle),
                circle.center.y + circle.radius * math.sin(angle)
            )
            radius_screen = self.world_to_screen(radius_point)
            
            painter.setPen(QPen(QColor(0, 128, 255), 2))
            painter.setBrush(QColor(0, 128, 255, 128))
            painter.drawEllipse(int(radius_screen.x() - handle_radius),
                              int(radius_screen.y() - handle_radius),
                              handle_radius * 2, handle_radius * 2)
        
        # W32: Arc Handles mit verbesserter Visualisierung und aktivem Zustand
        arc, arc_source = self._resolve_direct_edit_target_arc()
        if arc is not None:
            center_screen = self.world_to_screen(arc.center)
            
            # Prüfe ob dieser Arc aktiv bearbeitet wird
            is_active_edit = self._direct_edit_dragging and self._direct_edit_arc is arc
            
            # W32: Zeichne "Ghost" Arc während des Drags für besseres Feedback
            if is_active_edit:
                painter.setPen(QPen(QColor(0, 200, 255), 2, Qt.DashLine))
                painter.setBrush(Qt.NoBrush)
                # Berechne Bounding Box für den Arc
                r_screen = max(1.0, float(arc.radius) * float(self.view_scale))
                painter.drawEllipse(
                    int(center_screen.x() - r_screen),
                    int(center_screen.y() - r_screen),
                    int(2 * r_screen),
                    int(2 * r_screen)
                )
            
            # Center Handle (green square) - immer sichtbar
            # W32: Vergrößert wenn aktiv
            center_size = handle_radius + 2 if is_active_edit else handle_radius
            painter.setPen(QPen(QColor(0, 255, 0), 2))
            painter.setBrush(QColor(0, 255, 0, 180 if is_active_edit else 128))
            painter.drawRect(int(center_screen.x() - center_size), 
                           int(center_screen.y() - center_size),
                           center_size * 2, center_size * 2)
            
            # W32: Radius Handle (cyan circle on arc mid) - prominent wenn nicht aktiv
            mid_angle = math.radians((arc.start_angle + arc.end_angle) / 2)
            radius_point = Point2D(
                arc.center.x + arc.radius * math.cos(mid_angle),
                arc.center.y + arc.radius * math.sin(mid_angle)
            )
            radius_screen = self.world_to_screen(radius_point)
            
            # Radius Handle ist wichtigster Handle - immer prominent
            radius_size = handle_radius + 3 if not is_active_edit else handle_radius + 1
            painter.setPen(QPen(QColor(0, 255, 255), 3 if not is_active_edit else 2))
            painter.setBrush(QColor(0, 255, 255, 200 if not is_active_edit else 150))
            painter.drawEllipse(int(radius_screen.x() - radius_size),
                              int(radius_screen.y() - radius_size),
                              radius_size * 2, radius_size * 2)
            
            # W32: Verbindungslinie Center → Radius Handle für klare Assoziation
            if not is_active_edit:
                painter.setPen(QPen(QColor(0, 255, 255, 80), 1))
                painter.drawLine(center_screen, radius_screen)
            
            # Start/End Angle Handles nur wenn aktiv oder gehovered
            show_angle_handles = is_active_edit or self._last_hovered_entity is arc
            
            if show_angle_handles:
                # Start Angle Handle (orange)
                start_point = Point2D(
                    arc.center.x + arc.radius * math.cos(math.radians(arc.start_angle)),
                    arc.center.y + arc.radius * math.sin(math.radians(arc.start_angle))
                )
                start_screen = self.world_to_screen(start_point)
                
                painter.setPen(QPen(QColor(255, 165, 0), 2))
                painter.setBrush(QColor(255, 165, 0, 128))
                painter.drawEllipse(int(start_screen.x() - handle_radius),
                                  int(start_screen.y() - handle_radius),
                                  handle_radius * 2, handle_radius * 2)
                
                # End Angle Handle (magenta)
                end_point = Point2D(
                    arc.center.x + arc.radius * math.cos(math.radians(arc.end_angle)),
                    arc.center.y + arc.radius * math.sin(math.radians(arc.end_angle))
                )
                end_screen = self.world_to_screen(end_point)
                
                painter.setPen(QPen(QColor(255, 0, 255), 2))
                painter.setBrush(QColor(255, 0, 255, 128))
                painter.drawEllipse(int(end_screen.x() - handle_radius),
                                  int(end_screen.y() - handle_radius),
                                  handle_radius * 2, handle_radius * 2)
                
                # W32: Zeichne Winkel-Sector für visuelles Feedback
                if is_active_edit and self._direct_edit_mode in ("start_angle", "end_angle"):
                    painter.setPen(QPen(QColor(255, 200, 100, 150), 1, Qt.DashLine))
                    painter.setBrush(QColor(255, 200, 100, 30))
                    # Vereinfachte Sector-Darstellung als Dreieck
                    path = QPainterPath()
                    path.moveTo(center_screen)
                    path.lineTo(start_screen)
                    path.lineTo(end_screen)
                    path.closeSubpath()
                    painter.drawPath(path)

        # W30 AP1: Line Handles (Endpoint + Midpoint - Direct Manipulation Parity with Circle)
        hovered = self._last_hovered_entity
        if isinstance(hovered, Line2D) and not getattr(hovered, "construction", False):
            # Check if this line is part of a rectangle (skip - handled by rect edge logic)
            rect_context = self._build_rectangle_edge_drag_context(hovered)
            if rect_context is None:
                # Not a rectangle edge - draw endpoint/midpoint handles
                start_point = self.world_to_screen(hovered.start)
                end_point = self.world_to_screen(hovered.end)
                midpoint = self.world_to_screen(Point2D(
                    (hovered.start.x + hovered.end.x) / 2,
                    (hovered.start.y + hovered.end.y) / 2
                ))

                # Start Endpoint Handle (yellow circle)
                painter.setPen(QPen(QColor(255, 255, 0), 2))
                painter.setBrush(QColor(255, 255, 0, 128))
                painter.drawEllipse(int(start_point.x() - handle_radius),
                                  int(start_point.y() - handle_radius),
                                  handle_radius * 2, handle_radius * 2)

                # End Endpoint Handle (yellow circle)
                painter.setPen(QPen(QColor(255, 255, 0), 2))
                painter.setBrush(QColor(255, 255, 0, 128))
                painter.drawEllipse(int(end_point.x() - handle_radius),
                                  int(end_point.y() - handle_radius),
                                  handle_radius * 2, handle_radius * 2)

                # Midpoint Handle (green square - like circle center)
                painter.setPen(QPen(QColor(0, 255, 0), 2))
                painter.setBrush(QColor(0, 255, 0, 128))
                painter.drawRect(int(midpoint.x() - handle_radius),
                               int(midpoint.y() - handle_radius),
                               handle_radius * 2, handle_radius * 2)

        # W30 AP4: Simplified Ellipse Handles (only center + primary X-radius in normal mode)
        ellipse, ellipse_source = self._resolve_direct_edit_target_ellipse()
        if ellipse is not None:
            center = self.world_to_screen(ellipse.center)
            rotation_rad = math.radians(float(getattr(ellipse, "rotation", 0.0)))
            ux, uy = math.cos(rotation_rad), math.sin(rotation_rad)

            rx = max(0.01, float(getattr(ellipse, "radius_x", 0.01)))
            ry = max(0.01, float(getattr(ellipse, "radius_y", 0.01)))

            # Center Handle (green square)
            painter.setPen(QPen(QColor(0, 255, 0), 2))
            painter.setBrush(QColor(0, 255, 0, 128))
            painter.drawRect(int(center.x() - handle_radius),
                           int(center.y() - handle_radius),
                           handle_radius * 2, handle_radius * 2)

            # Primary X-Radius Handle (blue circle)
            x_handle_world = Point2D(
                ellipse.center.x + rx * ux,
                ellipse.center.y + rx * uy
            )
            x_handle = self.world_to_screen(x_handle_world)

            painter.setPen(QPen(QColor(0, 128, 255), 2))
            painter.setBrush(QColor(0, 128, 255, 128))
            painter.drawEllipse(int(x_handle.x() - handle_radius),
                              int(x_handle.y() - handle_radius),
                              handle_radius * 2, handle_radius * 2)

            # W30 AP4: Y-radius and rotation handles only during active edit (dragging)
            if self._direct_edit_dragging and self._direct_edit_ellipse is ellipse:
                # Y-Radius Handle (red circle)
                vx, vy = -math.sin(rotation_rad), math.cos(rotation_rad)
                y_handle_world = Point2D(
                    ellipse.center.x + ry * vx,
                    ellipse.center.y + ry * vy
                )
                y_handle = self.world_to_screen(y_handle_world)

                painter.setPen(QPen(QColor(255, 100, 100), 2))
                painter.setBrush(QColor(255, 100, 100, 128))
                painter.drawEllipse(int(y_handle.x() - handle_radius),
                                  int(y_handle.y() - handle_radius),
                                  handle_radius * 2, handle_radius * 2)

                # Rotation Handle (purple circle - further out)
                rot_handle_world = Point2D(
                    ellipse.center.x + (rx * 1.2) * ux,
                    ellipse.center.y + (rx * 1.2) * uy
                )
                rot_handle = self.world_to_screen(rot_handle_world)

                painter.setPen(QPen(QColor(180, 0, 255), 2))
                painter.setBrush(QColor(180, 0, 255, 128))
                painter.drawEllipse(int(rot_handle.x() - handle_radius),
                                  int(rot_handle.y() - handle_radius),
                                  handle_radius * 2, handle_radius * 2)

        # W30 AP4: Simplified Polygon Handles (only when hovered/selected)
        polygon, polygon_source = self._resolve_direct_edit_target_polygon()
        if polygon is not None:
            # Only show vertices when polygon is hovered or selected
            is_selected = polygon in getattr(self, 'selected_polygons', [])
            is_hovered = isinstance(self._last_hovered_entity, type(polygon))

            if is_selected or is_hovered:
                points = getattr(polygon, "points", [])
                # Highlight active vertex during drag
                active_idx = getattr(self, '_direct_edit_polygon_vertex_idx', -1)

                for idx, pt in enumerate(points):
                    pt_screen = self.world_to_screen(pt)

                    # Active vertex is more prominent
                    if idx == active_idx:
                        painter.setPen(QPen(QColor(255, 255, 0), 3))
                        painter.setBrush(QColor(255, 255, 0, 180))
                        radius = handle_radius + 2
                    else:
                        # Subtle styling for non-active vertices
                        painter.setPen(QPen(QColor(200, 200, 200), 1))
                        painter.setBrush(QColor(150, 150, 150, 100))
                        radius = handle_radius - 1

                    painter.drawEllipse(int(pt_screen.x() - radius),
                                      int(pt_screen.y() - radius),
                                      radius * 2, radius * 2)

    def paintEvent(self, event):
        # 1. QPainter initialisieren
        p = QPainter(self)
        
        # WICHTIG: Clipping setzen, damit Qt nicht auüƒerhalb des "Dirty Rects" malt.
        # Das spart GPU-Arbeit.
        p.setClipRect(event.rect())
        
        # Antialiasing für schüne Linien
        p.setRenderHint(QPainter.Antialiasing)
        
        # 2. Hintergrund füllen (Schneller als drawRect)
        p.fillRect(event.rect(), DesignTokens.COLOR_BG_CANVAS)
        
        # 3. Update-Rect für Culling vorbereiten
        # Wir nehmen das Event-Rect (den Bereich, der neu gezeichnet werden muss)
        # und machen es etwas grüüƒer (Padding).
        # Warum? Damit dicke Linien oder Kreise am Rand nicht "abgehackt" wirken,
        # wenn der Renderer entscheidet, sie seien knapp drauüƒen.
        update_rect = QRectF(event.rect()).adjusted(-20, -20, 20, 20)
        
        # 4. Zeichen-Methoden aufrufen
        # Da wir update_rect übergeben, berechnet der Renderer intern:
        # "Liegt diese Linie innerhalb von update_rect?" -> Wenn nein, Skip.
        
        self._draw_grid(p, update_rect)
        self._draw_canvas(p, update_rect)  # Bildreferenz (hinter Geometrie)
        self._draw_body_references(p)   # Falls vorhanden (projizierte 3D-Kanten)
        self._draw_profiles(p, update_rect)
        self._draw_axes(p)
        self._draw_orientation_indicator(p)  # 3D-Orientierung anzeigen (Feature Flag)

        # Hier passiert die Magie der Performance-Optimierung:
        self._draw_geometry(p, update_rect)
        self._draw_native_splines(p)  # Native B-Splines aus DXF Import

        # UI-Elemente (Constraints, Snaps etc.) zeichnen
        fast_drag = bool(self.performance_mode and self._direct_edit_dragging)
        if not fast_drag:
            self._draw_constraints(p)
        if not self._direct_edit_dragging:
            self._draw_open_ends(p)
        self._draw_preview(p)
        self._draw_selection_box(p)
        self._draw_snap(p)
        self._draw_direct_edit_handles(p)
        if not fast_drag:
            self._draw_snap_feedback_overlay(p)
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
        self.status_message.emit("Extrude: FlÄchen wÄhlen | Tab=Optionen | Enter=Anwenden")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.view_offset == QPointF(0, 0):
            self._center_view()

    def _is_empty_right_click_target(self, screen_pos: QPointF, world_pos: QPointF) -> bool:
        """True, wenn unter dem Cursor keine editierbare/auswÄhlbare Sketch-EntitÄt liegt."""
        if self._find_constraint_at(screen_pos):
            return False
        if self._find_spline_element_at(world_pos):
            return False
        if self._find_entity_at(world_pos):
            return False
        if self._find_face_at(world_pos):
            return False
        if self.canvas_image and self._canvas_hit_test(world_pos):
            return False
        return True

    def _cancel_right_click_empty_action(self) -> bool:
        """
        Bricht genau eine sinnvolle Interaktion für Rechtsklick im leeren Bereich ab.
        PAKET B W6: HUD-Feedback für alle Abbruch-FÄlle hinzugefügt.
        W25: Direct-Edit-Drag Abbruch hinzugefügt für Konsistenz mit ESC.
        """
        # W25: Level 0 - Direct-Edit-Drag abbrechen (Konsistenz mit _handle_escape_logic)
        if self._direct_edit_dragging:
            self._reset_direct_edit_state()
            self._show_hud(tr("Direktes Bearbeiten abgebrochen"))
            self._update_cursor()
            self.request_update()
            return True

        if self.dim_input_active and self.dim_input.isVisible():
            self.dim_input.hide()
            self.dim_input.unlock_all()
            self.dim_input_active = False
            self.setFocus()
            self._show_hud(tr("Eingabe abgebrochen"))
            return True

        if self._canvas_calibrating:
            self._canvas_calibrating = False
            self._canvas_calib_points = []
            self._show_hud(tr("Kalibrierung abgebrochen"))
            return True

        if self.selection_box_start:
            self.selection_box_start = None
            self.selection_box_end = None
            # Kein HUD nütig für Box-Abbruch (passiert oft versehentlich)
            return True

        if self.tool_step > 0:
            if self.current_tool == SketchTool.SPLINE and len(self.tool_points) >= 2:
                self._finish_spline()
                self._show_hud(tr("Spline erstellt"))
            else:
                self._cancel_tool()
                self._show_hud(tr("Aktion abgebrochen"))
            return True

        if self.current_tool != SketchTool.SELECT:
            self.set_tool(SketchTool.SELECT)
            self._show_hud(tr("Werkzeug deaktiviert"))
            return True

        if (self.selected_lines or self.selected_points or self.selected_circles
                or self.selected_arcs or self.selected_constraints or self.selected_splines):
            self._clear_selection()
            # PAKET B W6: HUD-Feedback für Selektion-Clear
            self._show_hud(tr("Selektion aufgehoben"))
            return True

        return False

    def _reset_direct_edit_state(self):
        """
        W25: Zentralisierte Methode zum Zurücksetzen aller Direct-Edit-ZustÄnde.
        Sorgt für konsistente Zustandsbereinigung nach ESC/Finish/Rechtsklick.
        """
        self._direct_edit_dragging = False
        self._direct_edit_mode = None
        self._direct_edit_circle = None
        self._direct_edit_source = None
        self._direct_edit_drag_moved = False
        self._direct_edit_radius_constraints = []
        self._direct_edit_line = None
        self._direct_edit_line_context = None
        self._direct_edit_line_length_constraints = []
        self._direct_edit_arc = None
        self._direct_edit_start_start_angle = 0.0
        self._direct_edit_start_end_angle = 0.0
        self._direct_edit_ellipse = None
        self._direct_edit_start_radius_x = 0.0
        self._direct_edit_start_radius_y = 0.0
        self._direct_edit_start_rotation = 0.0
        self._direct_edit_polygon = None
        self._direct_edit_polygon_vertex_idx = -1
        self._direct_edit_polygon_vertex_start = QPointF()
        self._direct_edit_live_solve = False
        self._direct_edit_pending_solve = False
        self._direct_edit_last_live_solve_ts = 0.0
        # W25: Kontext zurücksetzen für korrekte Navigation-Hints
        self._hint_context = 'sketch'
