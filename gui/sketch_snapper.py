import math
import sys
import os
from dataclasses import dataclass
from typing import List, Tuple, Optional
from PySide6.QtCore import QPointF, QRectF
from loguru import logger

# --- PATH FIX START ---
# Wir fügen das Parent-Verzeichnis (Root) zum Pfad hinzu, 
# damit 'sketcher' und 'gui' sauber gefunden werden.
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir) # Geht von /gui nach / (Root)
if root_dir not in sys.path:
    sys.path.append(root_dir)
# --- PATH FIX END ---

try:
    # Versuch 1: Sauberer Import über das Package 'sketcher'
    # Wir importieren es 'as geometry', damit der restliche Code (geometry.func()) funktioniert
    import sketcher.geometry as geometry 
    from sketcher.geometry import Point2D, Line2D, Circle2D, Arc2D
    
    # Import aus dem Nachbar-Modul im gleichen Ordner (gui) oder via Root
    try:
        from gui.sketch_tools import SketchTool, SnapType
    except ImportError:
        from sketch_tools import SketchTool, SnapType

except ImportError as e:
    logger.error(f"CRITICAL IMPORT ERROR in Snapper: {e}")
    # Fallback für Flat-Structure (wenn alle Dateien in einem Ordner liegen)
    try:
        import geometry
        from sketch_tools import SketchTool, SnapType
        from sketcher import Point2D, Line2D, Circle2D, Arc2D
    except ImportError:
        # Notfall-Dummy, damit die IDE nicht komplett rot leuchtet
        class Point2D: pass
        class SketchTool: pass
        class SnapType: pass

@dataclass
class SnapResult:
    point: QPointF
    type: SnapType
    target_entity: any = None # Das Objekt, das wir getroffen haben
    diagnostic: str = ""
    priority: int = 0
    distance: float = 0.0
    confidence: float = 0.0

class SmartSnapper:
    """
    Advanced Snapper mit echter Linie-Kreis-Schnittberechnung.
    """
    
    SNAP_DIST_SCREEN = 15
    SNAP_DIST_SCREEN_MIN = 6
    SNAP_DIST_SCREEN_MAX = 80
    SNAP_WORLD_MIN = 1e-4
    SNAP_WORLD_MIN_FACTOR = 1e-6
    SNAP_WORLD_MAX_FACTOR = 3e-1
    STICKY_RELEASE_FACTOR = 1.5
    STICKY_PREEMPT_PRIORITY_DELTA = 2
    DENSE_ENTITY_THRESHOLD = 16
    DENSE_INFERENCE_PENALTY = 2
    DENSE_EXACT_SNAP_BOOST = 1
    MAX_INTERSECTION_ENTITIES = 96
    
    PRIORITY_MAP = {
        SnapType.ENDPOINT: 20,
        SnapType.MIDPOINT: 15,
        SnapType.CENTER: 15,
        SnapType.QUADRANT: 15,
        SnapType.INTERSECTION: 18, # Schnittpunkte sind wichtig!
        SnapType.VIRTUAL_INTERSECTION: 11,
        SnapType.PERPENDICULAR: 16,
        SnapType.TANGENT: 16,
        SnapType.ANGLE_45: 13,
        SnapType.HORIZONTAL: 14,
        SnapType.VERTICAL: 14,
        SnapType.PARALLEL: 13,
        SnapType.ORIGIN: 19,       # Origin hat hohe Priorität (fast wie Endpoint)
        SnapType.EDGE: 5,          # Irgendwo auf der Kante (niedrigste Prio der Geo-Snaps)
        SnapType.GRID: 1,
        SnapType.NONE: 0
    }

    def __init__(self, sketch_editor):
        self.editor = sketch_editor
        self.sketch = sketch_editor.sketch

        # Performance Optimization 1.6: Intersection Cache (60-80% Reduktion bei großen Sketches!)
        self._intersection_cache = {}  # {(entity1_id, entity2_id): [Point2D, ...]}
        self._cache_version = 0
        self._sticky_snap: Optional[SnapResult] = None
        self._is_dense_context = False

    def _editor_snap_radius_px(self) -> float:
        """
        Active snap radius in pixels, honoring editor settings with sane clamps.
        """
        raw = getattr(self.editor, "snap_radius", self.SNAP_DIST_SCREEN)
        try:
            px = float(raw)
        except Exception:
            px = float(self.SNAP_DIST_SCREEN)
        return max(self.SNAP_DIST_SCREEN_MIN, min(self.SNAP_DIST_SCREEN_MAX, px))

    def _scene_world_diag(self) -> float:
        """
        Conservative diagonal of the current 2D sketch extent in world units.
        """
        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")

        def include_xy(x, y):
            nonlocal min_x, min_y, max_x, max_y
            min_x = min(min_x, float(x))
            min_y = min(min_y, float(y))
            max_x = max(max_x, float(x))
            max_y = max(max_y, float(y))

        try:
            for line in getattr(self.sketch, "lines", []):
                include_xy(line.start.x, line.start.y)
                include_xy(line.end.x, line.end.y)

            for circle in getattr(self.sketch, "circles", []):
                cx, cy = float(circle.center.x), float(circle.center.y)
                r = abs(float(circle.radius))
                include_xy(cx - r, cy - r)
                include_xy(cx + r, cy + r)

            for arc in getattr(self.sketch, "arcs", []):
                cx, cy = float(arc.center.x), float(arc.center.y)
                r = abs(float(arc.radius))
                include_xy(cx - r, cy - r)
                include_xy(cx + r, cy + r)
                include_xy(arc.start_point.x, arc.start_point.y)
                include_xy(arc.end_point.x, arc.end_point.y)

            for p in getattr(self.sketch, "points", []):
                include_xy(p.x, p.y)
        except Exception:
            return 0.0

        if min_x == float("inf"):
            return 0.0
        return math.hypot(max_x - min_x, max_y - min_y)

    def _compute_snap_radius_world(self) -> float:
        """
        Converts snap radius from pixels to world units and clamps it against
        sketch size so zoom extremes do not create over- or under-snapping.
        """
        px = self._editor_snap_radius_px()
        view_scale = max(float(getattr(self.editor, "view_scale", 1.0)), 1e-9)
        base_world = px / view_scale

        scene_diag = self._scene_world_diag()
        if scene_diag <= 0.0:
            return max(self.SNAP_WORLD_MIN, base_world)

        min_world = max(self.SNAP_WORLD_MIN, scene_diag * self.SNAP_WORLD_MIN_FACTOR)
        max_world = max(min_world * 4.0, scene_diag * self.SNAP_WORLD_MAX_FACTOR)
        return max(min_world, min(max_world, base_world))

    def invalidate_intersection_cache(self):
        """
        Performance Optimization 1.6: Invalidiert Intersection-Cache.
        Aufruf bei Geometrie-Änderungen (neue Linien, Move, etc.)
        """
        self._intersection_cache.clear()
        self._cache_version += 1
        self._sticky_snap = None

    def _is_drawing_tool_active(self) -> bool:
        tool = getattr(self.editor, "current_tool", None)
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
        return tool in drawing_tools

    def _priority_for_snap_type(self, snap_type: SnapType) -> int:
        priority = int(self.PRIORITY_MAP.get(snap_type, 0))
        if snap_type == SnapType.VIRTUAL_INTERSECTION and self._is_drawing_tool_active():
            # In drawing mode prefer virtual intersections over generic edge snaps.
            priority += 6
        if self._is_dense_context:
            if snap_type in {
                SnapType.HORIZONTAL,
                SnapType.VERTICAL,
                SnapType.PARALLEL,
                SnapType.PERPENDICULAR,
                SnapType.TANGENT,
                SnapType.ANGLE_45,
                SnapType.VIRTUAL_INTERSECTION,
            }:
                priority = max(0, priority - self.DENSE_INFERENCE_PENALTY)
            elif snap_type in {
                SnapType.ENDPOINT,
                SnapType.MIDPOINT,
                SnapType.CENTER,
                SnapType.INTERSECTION,
                SnapType.QUADRANT,
                SnapType.ORIGIN,
            }:
                priority += self.DENSE_EXACT_SNAP_BOOST
        return priority

    @staticmethod
    def _distance_world(p: Point2D, mouse_world: QPointF) -> float:
        return math.hypot(float(p.x) - mouse_world.x(), float(p.y) - mouse_world.y())

    @staticmethod
    def _distance_points(p1: Point2D, p2: Point2D) -> float:
        return math.hypot(float(p1.x) - float(p2.x), float(p1.y) - float(p2.y))

    def _active_line_start_point(self) -> Optional[Point2D]:
        """
        Returns the active anchor point for line-like inference tools.
        """
        tool = getattr(self.editor, "current_tool", None)
        step = int(getattr(self.editor, "tool_step", 0))
        tool_points = getattr(self.editor, "tool_points", None) or []
        if not tool_points:
            return None

        # LINE: Polyline mode uses the last confirmed point as anchor.
        if tool == SketchTool.LINE and step >= 1:
            start = tool_points[-1]
        # Other tools: first point acts as direction/inference anchor.
        elif tool in {
            SketchTool.RECTANGLE,
            SketchTool.RECTANGLE_CENTER,
            SketchTool.ELLIPSE,
            SketchTool.POLYGON,
            SketchTool.SLOT,
            SketchTool.NUT,
            SketchTool.STAR,
        } and step == 1:
            start = tool_points[0]
        else:
            return None

        try:
            if hasattr(start, "x") and callable(start.x):
                return Point2D(float(start.x()), float(start.y()))
            return Point2D(float(start.x), float(start.y))
        except Exception:
            return None

    @staticmethod
    def _perpendicular_projection_on_segment(point: Point2D, line: Line2D) -> Optional[Point2D]:
        dx = float(line.end.x - line.start.x)
        dy = float(line.end.y - line.start.y)
        denom = dx * dx + dy * dy
        if denom < 1e-12:
            return None
        px = float(point.x - line.start.x)
        py = float(point.y - line.start.y)
        t = (px * dx + py * dy) / denom
        seg_tol = 1e-6
        if t < -seg_tol or t > 1.0 + seg_tol:
            return None
        t = max(0.0, min(1.0, t))
        return Point2D(line.start.x + t * dx, line.start.y + t * dy)

    @staticmethod
    def _is_point_on_arc(arc: Arc2D, point: Point2D, tol_deg: float = 1e-5) -> bool:
        ang = math.degrees(math.atan2(point.y - arc.center.y, point.x - arc.center.x)) % 360.0
        start = float(arc.start_angle) % 360.0
        sweep = float(arc.sweep_angle)
        rel = (ang - start) % 360.0
        return rel <= (sweep + tol_deg)

    def _tangent_points_from_curve(self, start: Point2D, curve) -> List[Point2D]:
        """
        Tangent points from an external point to Circle2D / Arc2D.
        """
        if not hasattr(curve, "center") or not hasattr(curve, "radius"):
            return []

        cx = float(curve.center.x)
        cy = float(curve.center.y)
        r = abs(float(curve.radius))
        dx = float(start.x) - cx
        dy = float(start.y) - cy
        d2 = dx * dx + dy * dy

        if r < 1e-12 or d2 <= (r * r + 1e-12):
            return []

        l = (r * r) / d2
        m = (r * math.sqrt(max(0.0, d2 - r * r))) / d2
        p1 = Point2D(cx + l * dx - m * dy, cy + l * dy + m * dx)
        p2 = Point2D(cx + l * dx + m * dy, cy + l * dy - m * dx)

        points = [p1]
        if self._distance_points(p1, p2) > 1e-8:
            points.append(p2)

        if isinstance(curve, Arc2D):
            points = [p for p in points if self._is_point_on_arc(curve, p)]

        return points

    @staticmethod
    def _line_unit_direction(line: Line2D) -> Optional[tuple]:
        dx = float(line.end.x - line.start.x)
        dy = float(line.end.y - line.start.y)
        n = math.hypot(dx, dy)
        if n < 1e-12:
            return None
        return (dx / n, dy / n)

    def _add_axis_inference_candidates(
        self,
        line_start: Point2D,
        mouse_world: QPointF,
        snap_radius: float,
        candidates,
    ) -> None:
        horizontal_pt = Point2D(float(mouse_world.x()), float(line_start.y))
        vertical_pt = Point2D(float(line_start.x), float(mouse_world.y()))

        dist_h = self._distance_world(horizontal_pt, mouse_world)
        if dist_h < snap_radius and self._distance_points(line_start, horizontal_pt) > 1e-6:
            candidates.append(
                (
                    dist_h,
                    self._priority_for_snap_type(SnapType.HORIZONTAL),
                    SnapResult(QPointF(horizontal_pt.x, horizontal_pt.y), SnapType.HORIZONTAL, None),
                )
            )

        dist_v = self._distance_world(vertical_pt, mouse_world)
        if dist_v < snap_radius and self._distance_points(line_start, vertical_pt) > 1e-6:
            candidates.append(
                (
                    dist_v,
                    self._priority_for_snap_type(SnapType.VERTICAL),
                    SnapResult(QPointF(vertical_pt.x, vertical_pt.y), SnapType.VERTICAL, None),
                )
            )

    def _add_parallel_inference_candidate(
        self,
        line_start: Point2D,
        mouse_world: QPointF,
        snap_radius: float,
        ref_line: Line2D,
        candidates,
    ) -> None:
        u = self._line_unit_direction(ref_line)
        if u is None:
            return

        vx = float(mouse_world.x()) - float(line_start.x)
        vy = float(mouse_world.y()) - float(line_start.y)
        t = vx * u[0] + vy * u[1]
        cand = Point2D(float(line_start.x) + t * u[0], float(line_start.y) + t * u[1])

        if self._distance_points(line_start, cand) < 1e-6:
            return
        dist = self._distance_world(cand, mouse_world)
        if dist < snap_radius:
            candidates.append(
                (
                    dist,
                    self._priority_for_snap_type(SnapType.PARALLEL),
                    SnapResult(QPointF(cand.x, cand.y), SnapType.PARALLEL, ref_line),
                )
            )

    def _add_45deg_inference_candidates(
        self,
        line_start: Point2D,
        mouse_world: QPointF,
        snap_radius: float,
        candidates,
    ) -> None:
        vx = float(mouse_world.x()) - float(line_start.x)
        vy = float(mouse_world.y()) - float(line_start.y)
        if (vx * vx + vy * vy) < 1e-12:
            return

        inv_sqrt2 = math.sqrt(0.5)
        diag_axes = (
            (inv_sqrt2, inv_sqrt2),
            (inv_sqrt2, -inv_sqrt2),
        )
        for ux, uy in diag_axes:
            t = vx * ux + vy * uy
            cand = Point2D(float(line_start.x) + t * ux, float(line_start.y) + t * uy)
            if self._distance_points(line_start, cand) < 1e-6:
                continue
            dist = self._distance_world(cand, mouse_world)
            if dist < snap_radius:
                candidates.append(
                    (
                        dist,
                        self._priority_for_snap_type(SnapType.ANGLE_45),
                        SnapResult(
                            QPointF(cand.x, cand.y),
                            SnapType.ANGLE_45,
                            {"axis": (ux, uy)},
                        ),
                    )
                )

    def _collect_line_inference_candidates(
        self,
        line_start: Point2D,
        mouse_world: QPointF,
        snap_radius: float,
        entities,
        candidates,
    ) -> None:
        """
        Adds higher-level inferencing candidates while drawing a line:
        - horizontal/vertical from current start point
        - parallel to existing lines
        - perpendicular to existing lines
        - tangent to existing circles/arcs
        """
        self._add_axis_inference_candidates(
            line_start=line_start,
            mouse_world=mouse_world,
            snap_radius=snap_radius,
            candidates=candidates,
        )
        self._add_45deg_inference_candidates(
            line_start=line_start,
            mouse_world=mouse_world,
            snap_radius=snap_radius,
            candidates=candidates,
        )

        for entity in entities:
            if isinstance(entity, Line2D):
                # Ellipse ist intern segmentiert; diese Hilfssegmente sollen
                # keine Parallel/Perpendicular-Inferenz dominieren.
                if bool(getattr(entity, "_ellipse_segment", False)):
                    continue

                self._add_parallel_inference_candidate(
                    line_start=line_start,
                    mouse_world=mouse_world,
                    snap_radius=snap_radius,
                    ref_line=entity,
                    candidates=candidates,
                )

                proj = self._perpendicular_projection_on_segment(line_start, entity)
                if proj is None:
                    continue
                if self._distance_points(line_start, proj) < 1e-6:
                    continue
                dist = self._distance_world(proj, mouse_world)
                if dist < snap_radius:
                    candidates.append(
                        (
                            dist,
                            self._priority_for_snap_type(SnapType.PERPENDICULAR),
                            SnapResult(QPointF(proj.x, proj.y), SnapType.PERPENDICULAR, entity),
                        )
                    )
                continue

            if isinstance(entity, (Circle2D, Arc2D)):
                for tangent_pt in self._tangent_points_from_curve(line_start, entity):
                    if self._distance_points(line_start, tangent_pt) < 1e-6:
                        continue
                    dist = self._distance_world(tangent_pt, mouse_world)
                    if dist < snap_radius:
                        candidates.append(
                            (
                                dist,
                                self._priority_for_snap_type(SnapType.TANGENT),
                                SnapResult(QPointF(tangent_pt.x, tangent_pt.y), SnapType.TANGENT, entity),
                            )
                        )

    def _can_use_sticky(self) -> bool:
        """
        Sticky/magnetic lock is only used while actively drawing.
        """
        return self._is_drawing_tool_active()

    def _maybe_apply_sticky_snap(
        self,
        winner: Optional[SnapResult],
        mouse_world: QPointF,
        snap_radius: float,
    ) -> Optional[SnapResult]:
        """
        Keeps the previous snap for small mouse movements to reduce flicker/jitter.
        """
        if not self._can_use_sticky():
            self._sticky_snap = None
            return winner

        sticky = self._sticky_snap
        if sticky is None or sticky.type in (SnapType.NONE, SnapType.GRID):
            return winner

        sticky_pt = Point2D(sticky.point.x(), sticky.point.y())
        sticky_dist = self._distance_world(sticky_pt, mouse_world)
        release_radius = max(snap_radius, snap_radius * self.STICKY_RELEASE_FACTOR)
        if sticky_dist > release_radius:
            self._sticky_snap = None
            return winner

        if winner is None:
            return sticky

        sticky_prio = self._priority_for_snap_type(sticky.type)
        winner_prio = self._priority_for_snap_type(winner.type)
        if winner_prio >= (sticky_prio + self.STICKY_PREEMPT_PRIORITY_DELTA):
            return winner

        winner_dist = self._distance_world(Point2D(winner.point.x(), winner.point.y()), mouse_world)
        if winner_prio > sticky_prio and winner_dist < (sticky_dist * 0.75):
            return winner

        if winner_prio == sticky_prio and winner_dist < (sticky_dist * 0.65):
            return winner

        return sticky

    def _update_sticky_snap(self, winner: Optional[SnapResult]) -> None:
        if winner is None or winner.type in (SnapType.NONE, SnapType.GRID):
            return
        self._sticky_snap = winner

    def _no_snap_diagnostic(self, snap_radius: float, nearest_virtual_dist: float) -> str:
        """
        Explain why snapping did not happen for drawing workflows.
        """
        if not self._is_drawing_tool_active():
            return ""

        if math.isfinite(nearest_virtual_dist):
            if nearest_virtual_dist <= (snap_radius * 3.0):
                return (
                    f"Virtueller Schnittpunkt knapp ausserhalb Fangradius "
                    f"({nearest_virtual_dist:.2f}mm > {snap_radius:.2f}mm). "
                    "Tipp: Leicht reinzoomen oder Snap-Radius im Toolpanel erhoehen."
                )
            return (
                f"Virtueller Schnittpunkt erkannt, aber zu weit entfernt "
                f"({nearest_virtual_dist:.2f}mm). "
                "Tipp: Mit F Ansicht einpassen und dann naeher an die Zielstelle zoomen."
            )

        return (
            "Kein Fangpunkt im aktuellen Radius. "
            "Tipp: Mit Mausrad zoomen und Snap-Radius im Toolpanel pruefen."
        )

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def _compute_snap_confidence(
        self,
        best_dist: float,
        best_prio: int,
        second_dist: Optional[float],
        second_prio: Optional[int],
        snap_radius: float,
    ) -> float:
        radius = max(float(snap_radius), 1e-9)
        distance_score = self._clamp01(1.0 - (float(best_dist) / radius))
        priority_score = self._clamp01(float(best_prio) / 20.0)

        if second_dist is not None and second_prio is not None:
            prio_gap = max(0.0, float(best_prio - second_prio))
            dist_gap = max(0.0, float(second_dist - best_dist))
            separation = self._clamp01((0.55 * (prio_gap / 6.0)) + (0.45 * (dist_gap / radius)))
        else:
            separation = 1.0

        confidence = (
            0.45 * distance_score
            + 0.35 * priority_score
            + 0.20 * separation
        )
        return self._clamp01(confidence)

    def snap(self, mouse_screen_pos: QPointF) -> SnapResult:
        mouse_world = self.editor.screen_to_world(mouse_screen_pos)
        snap_radius = self._compute_snap_radius_world()
        
        candidates = []
        nearest_virtual_dist = float("inf")

        # Performance: Nur Objekte in der Nähe holen
        entities = []
        if hasattr(self.editor, 'spatial_index') and self.editor.spatial_index:
            query_rect = QRectF(mouse_world.x() - snap_radius*5, 
                                mouse_world.y() - snap_radius*5, 
                                snap_radius * 10, snap_radius * 10)
            entities = self.editor.spatial_index.query(query_rect)
        else:
            entities = self.sketch.lines + self.sketch.circles + self.sketch.arcs + getattr(self.sketch, 'splines', [])
        self._is_dense_context = len(entities) >= self.DENSE_ENTITY_THRESHOLD

        # 0. Kontext-Inferenz fuer aktiven Linienzug.
        line_start = self._active_line_start_point()
        if line_start is not None:
            self._collect_line_inference_candidates(
                line_start=line_start,
                mouse_world=mouse_world,
                snap_radius=snap_radius,
                entities=entities,
                candidates=candidates,
            )

        # 1. Standard Punkte (Endpunkte, Mitte, Zentrum)
        for entity in entities:
            # LINIE
            if hasattr(entity, 'start') and hasattr(entity, 'end'):
                suppress_point_snaps = bool(getattr(entity, "_suppress_endpoint_markers", False))
                if not suppress_point_snaps:
                    self._check_point(entity.start, mouse_world, snap_radius, SnapType.ENDPOINT, entity, candidates)
                    self._check_point(entity.end, mouse_world, snap_radius, SnapType.ENDPOINT, entity, candidates)
                    mid = Point2D((entity.start.x + entity.end.x)/2, (entity.start.y + entity.end.y)/2)
                    self._check_point(mid, mouse_world, snap_radius, SnapType.MIDPOINT, entity, candidates)
                
                # Nearest Point on Line (Edge)
                closest = self._closest_point_on_segment(entity.start, entity.end, mouse_world)
                self._check_point(closest, mouse_world, snap_radius, SnapType.EDGE, entity, candidates)

            # KREIS / BOGEN
            elif hasattr(entity, 'center'):
                self._check_point(entity.center, mouse_world, snap_radius, SnapType.CENTER, entity, candidates)
                
                # Quadranten (0, 90, 180, 270 Grad)
                if hasattr(entity, 'radius'):
                    for angle in [0, 90, 180, 270]:
                        qx = entity.center.x + entity.radius * math.cos(math.radians(angle))
                        qy = entity.center.y + entity.radius * math.sin(math.radians(angle))
                        self._check_point(Point2D(qx, qy), mouse_world, snap_radius, SnapType.QUADRANT, entity, candidates)
                    
                    # Nearest Point on Circle Edge
                    closest_edge = self._closest_point_on_circle(entity, mouse_world)
                    self._check_point(closest_edge, mouse_world, snap_radius, SnapType.EDGE, entity, candidates)

            # SPLINE (Neu: Snap to Control Points)
            elif hasattr(entity, 'control_points'):
                 # Endpunkte (falls Start/End properties existieren)
                 if hasattr(entity, 'start_point'):
                     self._check_point(entity.start_point, mouse_world, snap_radius, SnapType.ENDPOINT, entity, candidates)
                 if hasattr(entity, 'end_point'):
                     self._check_point(entity.end_point, mouse_world, snap_radius, SnapType.ENDPOINT, entity, candidates)
                 
                 # Control Points als "Endpoint" behandeln
                 for pt in entity.control_points:
                     # pt ist meist (x, y) Tuple oder Point2D
                     if isinstance(pt, (tuple, list)) and len(pt) >= 2:
                         p_obj = Point2D(pt[0], pt[1])
                         self._check_point(p_obj, mouse_world, snap_radius, SnapType.ENDPOINT, entity, candidates)
                     elif hasattr(pt, 'x') and hasattr(pt, 'y'):
                         self._check_point(pt, mouse_world, snap_radius, SnapType.ENDPOINT, entity, candidates)

        # 2. SCHNITTPUNKTE (Intersection)
        # Performance Optimization 1.6: Mit Cache (60-80% Reduktion!)
        # Das ist der teure Teil, daher nur berechnen, wenn wir grob in der Nähe sind
        if len(entities) > self.MAX_INTERSECTION_ENTITIES:
            entities = []
        for i, ent1 in enumerate(entities):
            if self._skip_intersection_for_entity(ent1):
                continue
            for ent2 in entities[i+1:]:
                if self._skip_intersection_for_entity(ent2):
                    continue
                # Cache-Key (sortiert für Symmetrie)
                e1_id = id(ent1)
                e2_id = id(ent2)
                cache_key = (min(e1_id, e2_id), max(e1_id, e2_id))

                # Cache-Lookup
                if cache_key in self._intersection_cache:
                    intersects = self._intersection_cache[cache_key]
                else:
                    # Berechne und cache
                    intersects = self._calculate_intersections(ent1, ent2)
                    self._intersection_cache[cache_key] = intersects

                for p in intersects:
                    snap_type = SnapType.INTERSECTION
                    target_entity = None
                    point_obj = p

                    # Line/Line liefert Meta-Infos fuer virtuelle Schnitte.
                    if isinstance(p, tuple) and len(p) >= 2 and isinstance(p[1], bool):
                        point_obj = p[0]
                        is_virtual = bool(p[1])
                        meta_entities = p[2] if len(p) > 2 else None
                        snap_type = SnapType.VIRTUAL_INTERSECTION if is_virtual else SnapType.INTERSECTION
                        if is_virtual and point_obj is not None:
                            nearest_virtual_dist = min(
                                nearest_virtual_dist,
                                self._distance_world(point_obj, mouse_world),
                            )
                        if meta_entities is not None:
                            target_entity = {
                                "virtual": is_virtual,
                                "entities": meta_entities,
                            }

                    self._check_point(point_obj, mouse_world, snap_radius, snap_type, target_entity, candidates)

        # 3. ORIGIN (Achsenursprung 0,0)
        origin = Point2D(0, 0)
        self._check_point(origin, mouse_world, snap_radius, SnapType.ORIGIN, None, candidates)

        # 4. Grid
        if self.editor.grid_snap:
            grid_pt = self._calculate_grid_snap(mouse_world)
            dist = math.hypot(grid_pt.x() - mouse_world.x(), grid_pt.y() - mouse_world.y())
            if dist < snap_radius:
                candidates.append((dist, self._priority_for_snap_type(SnapType.GRID), SnapResult(grid_pt, SnapType.GRID)))

        # Gewinner ermitteln
        winner: Optional[SnapResult] = None
        if candidates:
            candidates.sort(key=lambda c: (-c[1], c[0]))
            best_dist, best_prio, best_result = candidates[0]
            second_dist = None
            second_prio = None
            if len(candidates) > 1:
                second_dist = float(candidates[1][0])
                second_prio = int(candidates[1][1])
            best_result.distance = float(best_dist)
            best_result.priority = int(best_prio)
            best_result.confidence = self._compute_snap_confidence(
                best_dist=best_dist,
                best_prio=best_prio,
                second_dist=second_dist,
                second_prio=second_prio,
                snap_radius=snap_radius,
            )
            winner = best_result

        winner = self._maybe_apply_sticky_snap(winner, mouse_world, snap_radius)
        self._update_sticky_snap(winner)
        if winner is not None:
            if winner.priority <= 0:
                winner.priority = self._priority_for_snap_type(winner.type)
            if winner.distance <= 0.0:
                winner.distance = self._distance_world(
                    Point2D(winner.point.x(), winner.point.y()),
                    mouse_world,
                )
            if winner.confidence <= 0.0:
                winner.confidence = self._compute_snap_confidence(
                    best_dist=winner.distance,
                    best_prio=winner.priority,
                    second_dist=None,
                    second_prio=None,
                    snap_radius=snap_radius,
                )
            return winner

        return SnapResult(
            mouse_world,
            SnapType.NONE,
            diagnostic=self._no_snap_diagnostic(snap_radius, nearest_virtual_dist),
        )
    # --- Hilfs-Mathematik ---

    def _check_point(self, pt_obj, mouse_world, radius, type_enum, entity, candidates_list):
        px = pt_obj.x if hasattr(pt_obj, 'x') and not callable(pt_obj.x) else pt_obj.x()
        py = pt_obj.y if hasattr(pt_obj, 'y') and not callable(pt_obj.y) else pt_obj.y()
            
        dist = math.hypot(px - mouse_world.x(), py - mouse_world.y())
        if dist < radius:
            res = SnapResult(QPointF(px, py), type_enum, entity)
            candidates_list.append((dist, self._priority_for_snap_type(type_enum), res))

    @staticmethod
    def _line_param(line: Line2D, point: Point2D) -> float:
        dx = float(line.end.x - line.start.x)
        dy = float(line.end.y - line.start.y)
        denom = dx * dx + dy * dy
        if denom < 1e-12:
            return float("inf")
        px = float(point.x - line.start.x)
        py = float(point.y - line.start.y)
        return (px * dx + py * dy) / denom

    def _closest_point_on_segment(self, p1, p2, p):
        # Vektor-Projektion um den nächsten Punkt auf einer Linie zu finden
        x1, y1 = p1.x, p1.y
        x2, y2 = p2.x, p2.y
        px, py = p.x(), p.y()
        
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0: return Point2D(x1, y1)
        
        t = ((px - x1) * dx + (py - y1) * dy) / (dx*dx + dy*dy)
        t = max(0, min(1, t)) # Clamp auf Segment
        return Point2D(x1 + t * dx, y1 + t * dy)

    def _closest_point_on_circle(self, circle, p):
        # Vektor vom Zentrum zur Maus, auf Radius normalisieren
        cx, cy = circle.center.x, circle.center.y
        px, py = p.x(), p.y()
        
        dx, dy = px - cx, py - cy
        dist = math.hypot(dx, dy)
        if dist < 1e-9: return Point2D(cx + circle.radius, cy) # Fallback
        
        scale = circle.radius / dist
        return Point2D(cx + dx * scale, cy + dy * scale)

    def _calculate_intersections(self, e1, e2) -> List[Point2D]:
        """
        Zentrale Weiche zur Berechnung von Schnittpunkten zwischen beliebigen Elementen.
        Nutzt geometry.py für die Mathematik.
        """
        # Typ-Checks für Dispatching
        is_l1, is_l2 = isinstance(e1, Line2D), isinstance(e2, Line2D)
        is_c1, is_c2 = isinstance(e1, Circle2D), isinstance(e2, Circle2D)
        is_a1, is_a2 = isinstance(e1, Arc2D), isinstance(e2, Arc2D)

        try:
            # 1. Linie - Linie
            if is_l1 and is_l2:
                # geometry.line_line_intersection gibt einen einzelnen Point2D oder None zurück.
                # Wir müssen das in eine Liste [] packen!
                pt = geometry.line_line_intersection(e1, e2)
                if not pt:
                    return []

                t1 = self._line_param(e1, pt)
                t2 = self._line_param(e2, pt)
                seg_tol = 1e-6
                on_seg_1 = -seg_tol <= t1 <= 1.0 + seg_tol
                on_seg_2 = -seg_tol <= t2 <= 1.0 + seg_tol
                is_virtual = not (on_seg_1 and on_seg_2)
                return [(pt, is_virtual, (e1, e2))]

            # 2. Kreis - Linie (und umgekehrt)
            elif is_c1 and is_l2:
                return geometry.circle_line_intersection(e1, e2)
            elif is_l1 and is_c2:
                return geometry.circle_line_intersection(e2, e1)

            # 3. Kreis - Kreis
            elif is_c1 and is_c2:
                return geometry.get_circle_circle_intersection(e1, e2)

            # 4. Arc - Linie (und umgekehrt)
            elif is_a1 and is_l2:
                return geometry.arc_line_intersection(e1, e2)
            elif is_l1 and is_a2:
                return geometry.arc_line_intersection(e2, e1)

            # 5. Arc - Kreis (und umgekehrt)
            elif is_a1 and is_c2:
                return geometry.arc_circle_intersection(e1, e2)
            elif is_c1 and is_a2:
                return geometry.arc_circle_intersection(e2, e1)
            
            # (Optional: Arc-Arc könnte hier noch ergänzt werden, falls benötigt)

        except Exception as e:
            logger.warning(f"Intersection calculation failed: {e}")
            return []

        return []

    @staticmethod
    def _skip_intersection_for_entity(entity) -> bool:
        """
        Ellipsen werden intern als Proxy-Segmente modelliert.
        Intersection-Snap auf diesen Segmenten erzeugt hohen O(n^2)-Overhead
        bei geringem UX-Nutzen.
        """
        return bool(getattr(entity, "_ellipse_segment", False))

    def _calculate_grid_snap(self, pos):
        grid_sz = self.editor.grid_size
        x = round(pos.x() / grid_sz) * grid_sz
        y = round(pos.y() / grid_sz) * grid_sz
        return QPointF(x, y)
