"""
MashCad - Sketch Renderer Mixin
All _draw_* methods for sketch visualization
Extracted from sketch_editor.py for better maintainability
"""

import math
from loguru import logger
from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPainterPath, QFont, QPolygonF, QFontMetrics

# Importiere SketchTool und SnapType
try:
    from gui.sketch_tools import SketchTool, SnapType
except ImportError:
    try:
        from sketch_tools import SketchTool, SnapType
    except ImportError:
        from .sketch_tools import SketchTool, SnapType

try:
    # Versuche ConstraintType aus dem sketcher Paket zu laden
    from sketcher import ConstraintType
except ImportError:
    try:
        # Fallback: Direkt aus constraints
        from constraints import ConstraintType
    except ImportError:
        pass
  
try:
    from gui.design_tokens import DesignTokens
except ImportError:
    from design_tokens import DesignTokens

class SketchRendererMixin:
    """Mixin containing all drawing methods for SketchEditor"""
    def _is_item_visible(self, item_rect, update_rect):
        """
        High-Performance Culling:
        Prüft ob das Bounding-Rect des Items das Update-Rect berührt.
        """
        if update_rect is None: return True
        return update_rect.intersects(item_rect)
    
    def _get_line_bounds(self, line):
        """Berechnet Screen-Bounds für eine Linie inkl. Pen-Width Padding"""
        p1 = self.world_to_screen(QPointF(line.start.x, line.start.y))
        p2 = self.world_to_screen(QPointF(line.end.x, line.end.y))
        # +10 Padding für Liniendicke, Punkte und Glow-Effekt
        return QRectF(p1, p2).normalized().adjusted(-10, -10, 10, 10)

    def _get_circle_bounds(self, circle):
        """Berechnet Screen-Bounds für Kreis"""
        c = self.world_to_screen(QPointF(circle.center.x, circle.center.y))
        r = circle.radius * self.view_scale
        return QRectF(c.x() - r, c.y() - r, 2*r, 2*r).adjusted(-10, -10, 10, 10)

    def _get_arc_bounds(self, arc):
        """Berechnet Screen-Bounds für Arc (Vereinfacht als Rect des vollen Kreises)"""
        # Optimierung: Man könnte genaues Arc-Rect berechnen, aber Kreis-Rect ist viel schneller
        c = self.world_to_screen(QPointF(arc.center.x, arc.center.y))
        r = arc.radius * self.view_scale
        return QRectF(c.x() - r, c.y() - r, 2*r, 2*r).adjusted(-10, -10, 10, 10)
    

    def _draw_canvas(self, p, update_rect=None):
        """Zeichnet Canvas-Bildreferenz als Hintergrund (Fusion 360-Style)."""
        if not self.canvas_image or not self.canvas_visible or not self.canvas_world_rect:
            return

        wr = self.canvas_world_rect
        # Weltkoordinaten → Screen (Y-Achse ist invertiert)
        tl = self.world_to_screen(QPointF(wr.x(), wr.y() + wr.height()))
        br = self.world_to_screen(QPointF(wr.x() + wr.width(), wr.y()))
        screen_rect = QRectF(tl, br)

        if update_rect and not update_rect.intersects(screen_rect):
            return

        p.setOpacity(self.canvas_opacity)
        p.drawPixmap(screen_rect.toRect(), self.canvas_image)
        p.setOpacity(1.0)

        # Rahmen wenn Canvas-Tool aktiv oder Canvas selektiert
        if getattr(self, 'current_tool', None) == SketchTool.CANVAS or getattr(self, '_canvas_dragging', False):
            pen = QPen(QColor(0, 150, 255, 120), 1, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(screen_rect)

        # Kalibrierungspunkte zeichnen
        calib_pts = getattr(self, '_canvas_calib_points', [])
        if getattr(self, '_canvas_calibrating', False) and calib_pts:
            calib_color = QColor(255, 80, 0)
            p.setPen(QPen(calib_color, 2))
            p.setBrush(QBrush(calib_color))
            for cp in calib_pts:
                sp = self.world_to_screen(cp)
                p.drawEllipse(sp, 5, 5)
            if len(calib_pts) == 1:
                # Linie von Punkt 1 zur aktuellen Mausposition
                sp1 = self.world_to_screen(calib_pts[0])
                sp2 = self.world_to_screen(getattr(self, 'mouse_world', QPointF(0, 0)))
                p.setPen(QPen(calib_color, 1, Qt.DashLine))
                p.drawLine(sp1, sp2)

    def _draw_grid(self, p, update_rect=None):
        # Grid nur zeichnen, wenn es das Update-Rect berührt
        # Da das Grid den ganzen Screen füllt, prüfen wir hier nur grob
        # Wir könnten optimieren, indem wir nur die Linien innerhalb des Rects berechnen
        
        tl = self.screen_to_world(QPointF(0, 0))
        br = self.screen_to_world(QPointF(self.width(), self.height()))
        
        # Falls update_rect klein ist, berechne Start/Ende genauer
        if update_rect and update_rect.width() < self.width():
             tl_rect = self.screen_to_world(update_rect.topLeft())
             br_rect = self.screen_to_world(update_rect.bottomRight())
             # Wir nehmen das Maximum, um sicherzugehen, aber clampen auf Viewport
             start_x = max(tl.x(), tl_rect.x())
             end_x = min(br.x(), br_rect.x())
             start_y = min(tl.y(), tl_rect.y()) # Y ist invertiert
             end_y = max(br.y(), br_rect.y())
        else:
             start_x, end_x = tl.x(), br.x()
             start_y, end_y = br.y(), tl.y() # Y invertiert

        step = self.grid_size
        while step * self.view_scale < 15: step *= 2
        while step * self.view_scale > 80: step /= 2
        
        # Minor Grid
        p.setPen(DesignTokens.pen_grid_minor())
        
        # Vertikale Linien
        x = math.floor(start_x / step) * step
        while x < end_x + step:
            sx = self.world_to_screen(QPointF(x, 0)).x()
            # Nur zeichnen wenn im Update-Bereich (horizontal)
            if update_rect is None or (sx >= update_rect.left() - 1 and sx <= update_rect.right() + 1):
                p.drawLine(int(sx), 0, int(sx), self.height())
            x += step
            
        # Horizontale Linien
        y = math.floor(start_y / step) * step
        while y < end_y + step:
            sy = self.world_to_screen(QPointF(0, y)).y()
            if update_rect is None or (sy >= update_rect.top() - 1 and sy <= update_rect.bottom() + 1):
                p.drawLine(0, int(sy), self.width(), int(sy))
            y += step

        # Major Grid (ähnliche Logik, vereinfacht: immer zeichnen, da wenige Linien)
        p.setPen(QPen(DesignTokens.COLOR_GRID_MAJOR, 1))
        major_step = step * 5
        x = math.floor(tl.x() / major_step) * major_step
        while x < br.x():
            sx = self.world_to_screen(QPointF(x, 0)).x()
            if update_rect is None or (sx >= update_rect.left() - 5 and sx <= update_rect.right() + 5):
                p.drawLine(int(sx), 0, int(sx), self.height())
            x += major_step
        y = math.floor(br.y() / major_step) * major_step
        while y < tl.y():
            sy = self.world_to_screen(QPointF(0, y)).y()
            if update_rect is None or (sy >= update_rect.top() - 5 and sy <= update_rect.bottom() + 5):
                p.drawLine(0, int(sy), self.width(), int(sy))
            y += major_step
    
    def _draw_profiles(self, p, update_rect=None):
        if not self.closed_profiles: return

        # Performance: Profile nur zeichnen, wenn ihr Bounding-Box sichtbar ist
        # Da Polygon-Check teuer ist, machen wir das hier grob über world_to_screen des ersten Punktes
        
        for profile_data in self.closed_profiles:
            # TODO: Culling für Profile implementieren
            # Aktuell zeichnen wir alle, da Profile oft groß sind
            # und QPainterPath Clipping effizient ist.
            
            # ... (Rest des Codes aus _draw_profiles hier einfügen, unverändert) ...
            # Der Inhalt bleibt identisch zum originalen Code, wir ändern nur die Signatur
            
            # COPY-PASTE vom Original _draw_profiles Logik hier:
            from PySide6.QtGui import QPainterPath
            def profile_to_path(profile_data, scale, offset_func):
                path = QPainterPath()
                # Handle both 2-tuple and 3-tuple formats
                profile_type = profile_data[0]
                data = profile_data[1]
                if profile_type == 'circle':
                    circle = data
                    center = offset_func(QPointF(circle.center.x, circle.center.y))
                    radius = circle.radius * scale
                    path.addEllipse(center, radius, radius)
                elif profile_type == 'lines':
                    lines = data
                    if len(lines) >= 3:
                        points = [offset_func(QPointF(l.start.x, l.start.y)) for l in lines]
                        if points:
                            path.moveTo(points[0])
                            for pt in points[1:]: path.lineTo(pt)
                            path.closeSubpath()
                elif profile_type == 'polygon':
                    coords = list(data.exterior.coords)
                    if len(coords) >= 3:
                        screen_pts = [offset_func(QPointF(c[0], c[1])) for c in coords]
                        path.moveTo(screen_pts[0])
                        for pt in screen_pts[1:]: path.lineTo(pt)
                        path.closeSubpath()
                    for interior in data.interiors:
                        hole_coords = list(interior.coords)
                        if len(hole_coords) >= 3:
                            hole_pts = [offset_func(QPointF(c[0], c[1])) for c in hole_coords]
                            path.moveTo(hole_pts[0])
                            for pt in hole_pts[1:]: path.lineTo(pt)
                            path.closeSubpath()
                return path

            if not profile_data: continue
            
            path = profile_to_path(profile_data, self.view_scale, self.world_to_screen)
            
            # QUICK CHECK: Wenn Path komplett außerhalb Update-Rect -> Skip
            if update_rect and not update_rect.intersects(path.boundingRect()):
                continue

            path.setFillRule(Qt.OddEvenFill)
            is_hovered = (profile_data == self.hovered_face)
            p.setPen(Qt.NoPen)
            color = DesignTokens.COLOR_PROFILE_HOVER if is_hovered else DesignTokens.COLOR_PROFILE_FILL
            p.setBrush(QBrush(color))
            p.drawPath(path)

        # Offset Preview
        if self.offset_preview_lines:
            p.setPen(QPen(QColor(0, 200, 100), 2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            for line_data in self.offset_preview_lines:
                x1, y1, x2, y2 = line_data
                p1 = self.world_to_screen(QPointF(x1, y1))
                p2 = self.world_to_screen(QPointF(x2, y2))
                # Check Visibility
                if update_rect:
                    line_rect = QRectF(p1, p2).normalized().adjusted(-2,-2,2,2)
                    if not update_rect.intersects(line_rect): continue
                p.drawLine(p1, p2)
    
    def _draw_axes(self, p):
        o = self.world_to_screen(QPointF(0, 0))
        
        p.setPen(QPen(DesignTokens.COLOR_AXIS_X, 2))
        p.drawLine(int(o.x()), int(o.y()), self.width(), int(o.y()))
        p.setPen(QPen(DesignTokens.COLOR_AXIS_Y, 2))
        p.drawLine(int(o.x()), int(o.y()), int(o.x()), 0)
        
        # Origin schön modern: Weißer Punkt mit dunklem Rand
        p.setPen(QPen(DesignTokens.COLOR_BG_CANVAS, 2))
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.drawEllipse(o, 4, 4)
    
    def _draw_open_ends(self, p):
        """
        Zeichnet rote Markierungen an Punkten, die nicht geschlossen sind.
        Hilft dem User zu erkennen, warum eine Fläche nicht gefüllt wird.

        Ein Punkt gilt als "geschlossen" wenn:
        - Er mit mindestens einem anderen Endpunkt übereinstimmt (Count >= 2)
        - ODER er auf einem Kreis liegt (Toleranz-basiert)
        - ODER er auf einer Linie liegt (T-Kreuzung)
        """
        import math

        TOLERANCE = 0.5  # 0.5mm Toleranz für Punkt-auf-Geometrie

        # Alle Endpunkte von Linien und Bögen sammeln
        endpoints = []
        for l in self.sketch.lines:
            if not l.construction:
                endpoints.append(l.start)
                endpoints.append(l.end)
        for a in self.sketch.arcs:
            if not a.construction:
                endpoints.append(a.start_point)
                endpoints.append(a.end_point)

        # Dictionary um zu zählen wie oft ein Punkt vorkommt
        coord_counts = {}
        ENDPOINT_TOLERANCE_DECIMALS = 1  # 0.1mm für Endpunkt-Matching

        for pt in endpoints:
            key = (round(pt.x, ENDPOINT_TOLERANCE_DECIMALS), round(pt.y, ENDPOINT_TOLERANCE_DECIMALS))
            coord_counts[key] = coord_counts.get(key, 0) + 1

        def point_on_circle(pt, circle, tol):
            """Prüft ob Punkt auf Kreisumfang liegt."""
            dist = math.hypot(pt.x - circle.center.x, pt.y - circle.center.y)
            return abs(dist - circle.radius) < tol

        def point_on_line(pt, line, tol):
            """Prüft ob Punkt auf Linie liegt (nicht nur Endpunkte)."""
            # Distanz Punkt zu Liniensegment
            x1, y1 = line.start.x, line.start.y
            x2, y2 = line.end.x, line.end.y
            px, py = pt.x, pt.y

            dx, dy = x2 - x1, y2 - y1
            length_sq = dx*dx + dy*dy
            if length_sq < 1e-10:
                return False

            t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / length_sq))
            closest_x = x1 + t * dx
            closest_y = y1 + t * dy
            dist = math.hypot(px - closest_x, py - closest_y)

            # Nur als "auf Linie" zählen wenn NICHT an den Endpunkten
            if t > 0.01 and t < 0.99 and dist < tol:
                return True
            return False

        # Zeichne rote Punkte für "einsame" Enden
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(255, 0, 50, 180)))

        for pt in endpoints:
            key = (round(pt.x, ENDPOINT_TOLERANCE_DECIMALS), round(pt.y, ENDPOINT_TOLERANCE_DECIMALS))

            # Bereits verbunden durch anderen Endpunkt?
            if coord_counts[key] >= 2:
                continue

            # Liegt auf einem Kreis?
            on_circle = False
            for circle in self.sketch.circles:
                if not circle.construction and point_on_circle(pt, circle, TOLERANCE):
                    on_circle = True
                    break

            if on_circle:
                continue

            # Liegt auf einer Linie (T-Kreuzung)?
            on_line = False
            for line in self.sketch.lines:
                if not line.construction:
                    # Nicht die eigene Linie prüfen
                    if pt != line.start and pt != line.end:
                        if point_on_line(pt, line, TOLERANCE):
                            on_line = True
                            break

            if on_line:
                continue

            # Wirklich ein offenes Ende!
            screen_pos = self.world_to_screen(QPointF(pt.x, pt.y))
            p.drawEllipse(screen_pos, 5, 5)
            p.setPen(QPen(QColor(255, 0, 0), 1))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(screen_pos, 10, 10)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(255, 0, 50, 180)))
                
    def _draw_geometry(self, p, update_rect=None):
        """
        Ultimate Performance Render:
        1. Culling: Ignoriert alles außerhalb von update_rect.
        2. Batching: Sammelt Geometrie in QPainterPaths.
        """
        
        # --- 0. Vorbereitung ---
        path_normal = QPainterPath()       
        path_construction = QPainterPath() 
        path_fixed = QPainterPath()        
        path_selected = QPainterPath()     
        path_hover = QPainterPath()        
        path_glow = QPainterPath()
        path_endpoints = QPainterPath()
        path_fixed_points = QPainterPath()

        def is_visible(bounds):
            if update_rect is None: return True
            return update_rect.intersects(bounds)

        # Spline-Linien sammeln, um sie NICHT doppelt zu zeichnen (verhindert "schwarze Fläche")
        spline_lines_ids = set()
        for s in self.sketch.splines:
            if hasattr(s, '_lines'):
                for l in s._lines: spline_lines_ids.add(id(l))

        # --- 1. Linien sammeln ---
        for line in self.sketch.lines:
            # Überspringe Linien, die Teil eines Splines sind (wir zeichnen den Spline selbst)
            if id(line) in spline_lines_ids: 
                continue

            bounds = self._get_line_bounds(line)
            if not is_visible(bounds): continue

            p1 = self.world_to_screen(line.start)
            p2 = self.world_to_screen(line.end)
            
            is_sel = line in self.selected_lines
            is_hov = self.hovered_entity == line
            is_fixed = getattr(line, 'fixed', False)
            
            if is_sel:
                path_selected.moveTo(p1)
                path_selected.lineTo(p2)
                path_glow.moveTo(p1)
                path_glow.lineTo(p2)
            elif is_hov:
                path_hover.moveTo(p1)
                path_hover.lineTo(p2)
            elif line.construction:
                path_construction.moveTo(p1)
                path_construction.lineTo(p2)
            elif is_fixed:
                path_fixed.moveTo(p1)
                path_fixed.lineTo(p2)
            else:
                path_normal.moveTo(p1)
                path_normal.lineTo(p2)

            for pt, screen_pt in [(line.start, p1), (line.end, p2)]:
                if hasattr(pt, 'fixed') and pt.fixed:
                    path_fixed_points.addEllipse(screen_pt, 4, 4)
                else:
                    path_endpoints.addEllipse(screen_pt, 2, 2)

        # --- 2. Kreise sammeln ---
        for c in self.sketch.circles:
            bounds = self._get_circle_bounds(c)
            if not is_visible(bounds): continue

            ctr = self.world_to_screen(c.center)
            r = c.radius * self.view_scale
            
            is_sel = c in self.selected_circles
            is_hov = self.hovered_entity == c
            is_fixed = getattr(c, 'fixed', False)

            if is_sel:
                path_selected.addEllipse(ctr, r, r)
                path_glow.addEllipse(ctr, r, r)
            elif is_hov:
                path_hover.addEllipse(ctr, r, r)
            elif c.construction:
                path_construction.addEllipse(ctr, r, r)
            elif is_fixed:
                path_fixed.addEllipse(ctr, r, r)
            else:
                path_normal.addEllipse(ctr, r, r)

        # --- 3. Arcs sammeln (Point-Based Method - keine Winkel-Mathe-Probleme) ---
        for arc in self.sketch.arcs:
            bounds = self._get_arc_bounds(arc)
            if not is_visible(bounds): continue

            # Point-based Ansatz: Arc als Polyline durch gesampelte Punkte
            # Das vermeidet alle Winkel-Konvertierungsprobleme mit Qt
            sweep = arc.end_angle - arc.start_angle
            # Normalisiere auf positive Werte für korrekten Bogen
            while sweep < 0:
                sweep += 360
            while sweep > 360:
                sweep -= 360
            if sweep < 0.1:
                sweep = 360  # Fast geschlossener Bogen

            # Anzahl Segmente basierend auf Sweep (mehr = glatter)
            steps = max(16, int(sweep / 3))  # ~3° pro Segment für glatten Bogen

            temp_path = QPainterPath()
            first_point = None
            last_point = None

            for i in range(steps + 1):
                t = i / steps
                angle_rad = math.radians(arc.start_angle + sweep * t)
                world_pt = QPointF(
                    arc.center.x + arc.radius * math.cos(angle_rad),
                    arc.center.y + arc.radius * math.sin(angle_rad)
                )
                screen_pt = self.world_to_screen(world_pt)

                if i == 0:
                    temp_path.moveTo(screen_pt)
                    first_point = screen_pt
                else:
                    temp_path.lineTo(screen_pt)
                last_point = screen_pt

            # --- Zuweisung zu Styles ---
            is_sel = arc in self.selected_arcs
            is_hov = self.hovered_entity == arc
            is_fixed = getattr(arc, 'fixed', False)

            if is_sel:
                path_selected.addPath(temp_path)
                path_glow.addPath(temp_path)
            elif is_hov:
                path_hover.addPath(temp_path)
            elif arc.construction:
                path_construction.addPath(temp_path)
            elif is_fixed:
                path_fixed.addPath(temp_path)
            else:
                path_normal.addPath(temp_path)

            # Endpunkte zeichnen
            if first_point:
                path_endpoints.addEllipse(first_point, 3, 3)
            if last_point:
                path_endpoints.addEllipse(last_point, 3, 3)

        # --- 4. ZEICHNEN ---

        if not path_glow.isEmpty():
            glow_color = QColor(DesignTokens.COLOR_GEO_SELECTED)
            glow_color.setAlpha(60)
            glow_pen = QPen(glow_color, 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(glow_pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path_glow)

        if not path_construction.isEmpty():
            p.setPen(DesignTokens.pen_geo_construction())
            p.setBrush(Qt.NoBrush)
            p.drawPath(path_construction)
            
        if not path_fixed.isEmpty():
            pen = QPen(DesignTokens.COLOR_GEO_FIXED, 1.5)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path_fixed)

        if not path_normal.isEmpty():
            p.setPen(DesignTokens.pen_geo_normal())
            p.setBrush(Qt.NoBrush)
            p.drawPath(path_normal)

        if not path_hover.isEmpty():
            pen = QPen(DesignTokens.COLOR_GEO_HOVER, 2.5)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path_hover)

        if not path_selected.isEmpty():
            p.setPen(DesignTokens.pen_geo_selected())
            p.setBrush(Qt.NoBrush)
            p.drawPath(path_selected)

        if not path_endpoints.isEmpty():
            p.setPen(QPen(DesignTokens.COLOR_GEO_BODY, 1)) 
            p.setBrush(DesignTokens.COLOR_BG_CANVAS)
            p.drawPath(path_endpoints)
            
        if not path_fixed_points.isEmpty():
            p.setPen(QPen(DesignTokens.COLOR_GEO_FIXED, 2))
            p.setBrush(DesignTokens.COLOR_GEO_FIXED)
            p.drawPath(path_fixed_points)

        # --- 4b. Standalone Punkte zeichnen (Point Tool) ---
        for pt in self.sketch.points:
            # Nur standalone Punkte (nicht Linien-Endpunkte)
            if not getattr(pt, 'standalone', False):
                continue

            screen_pt = self.world_to_screen(QPointF(pt.x, pt.y))
            is_sel = pt in self.selected_points

            # Farbe basierend auf Zustand
            if is_sel:
                p.setPen(QPen(DesignTokens.COLOR_GEO_SELECTED, 2))
                p.setBrush(DesignTokens.COLOR_GEO_SELECTED)
                size = 5
            elif getattr(pt, 'construction', False):
                p.setPen(QPen(DesignTokens.COLOR_GEO_CONSTRUCTION, 2))
                p.setBrush(DesignTokens.COLOR_GEO_CONSTRUCTION)
                size = 4
            else:
                p.setPen(QPen(DesignTokens.COLOR_GEO_BODY, 2))
                p.setBrush(DesignTokens.COLOR_GEO_BODY)
                size = 4

            # Punkt als ausgefüllter Kreis mit X-Kreuz
            p.drawEllipse(screen_pt, size, size)
            # Kleines X-Kreuz für bessere Sichtbarkeit
            p.drawLine(QPointF(screen_pt.x() - size, screen_pt.y() - size),
                       QPointF(screen_pt.x() + size, screen_pt.y() + size))
            p.drawLine(QPointF(screen_pt.x() + size, screen_pt.y() - size),
                       QPointF(screen_pt.x() - size, screen_pt.y() + size))

        # --- 5. Splines (Separat & Korrigiert) ---
        for spline in self.sketch.splines:
            if update_rect:
                # Grober Bounding Box Check für Spline
                cps = spline.control_points
                if not cps: continue
                # ... (hier vereinfacht, im Zweifel zeichnen) ...

            is_selected = spline in self.selected_splines
            is_dragging = (spline == self.spline_drag_spline)
            
            col = DesignTokens.COLOR_GEO_CONSTRUCTION if spline.construction else DesignTokens.COLOR_GEO_BODY
            width = 2
            if is_selected: 
                col = DesignTokens.COLOR_GEO_SELECTED
                width = 3
            
            lines_to_draw = []
            if is_dragging and hasattr(spline, '_preview_lines'):
                lines_to_draw = spline._preview_lines
            elif hasattr(spline, 'to_lines'):
                lines_to_draw = spline.to_lines(segments_per_span=10)
            
            if not lines_to_draw: continue

            spline_path = QPainterPath()
            first = lines_to_draw[0]
            spline_path.moveTo(self.world_to_screen(first.start))
            for l in lines_to_draw:
                spline_path.lineTo(self.world_to_screen(l.end))
            
            if is_selected:
                glow_pen = QPen(QColor(DesignTokens.COLOR_GEO_SELECTED), 8)
                # FIX: .getColor() existiert nicht. Korrekte PySide6 Syntax:
                c = glow_pen.color()
                c.setAlpha(100)
                glow_pen.setColor(c)
                
                p.setPen(glow_pen)
                p.setBrush(Qt.NoBrush)
                p.drawPath(spline_path)
                
            p.setPen(QPen(col, width))
            p.setBrush(Qt.NoBrush)
            p.drawPath(spline_path)
            
            if is_selected or is_dragging:
                self._draw_spline_handles(p, spline)
    
    def _draw_spline_handles(self, p, spline):
        handle_color = QColor(100, 200, 100)
        point_color = QColor(255, 255, 255)
        
        for i, cp in enumerate(spline.control_points):
            pt_screen = self.world_to_screen(QPointF(cp.point.x, cp.point.y))
            
            # Punkt
            p.setPen(QPen(point_color, 2))
            p.setBrush(QBrush(self.BG_COLOR))
            p.drawEllipse(pt_screen, 4, 4)
            
            # Handles
            p.setPen(QPen(handle_color, 1))
            p.setBrush(QBrush(handle_color))
            
            if i > 0 or spline.closed:
                h = cp.handle_in_abs
                hp = self.world_to_screen(QPointF(h[0], h[1]))
                p.drawLine(pt_screen, hp)
                p.drawEllipse(hp, 3, 3)
                
            if i < len(spline.control_points)-1 or spline.closed:
                h = cp.handle_out_abs
                hp = self.world_to_screen(QPointF(h[0], h[1]))
                p.drawLine(pt_screen, hp)
                p.drawEllipse(hp, 3, 3)

    def _draw_native_splines(self, p):
        """Zeichnet native B-Splines (aus DXF Import) - diese erzeugen saubere Extrusions-Flächen."""
        native_splines = getattr(self.sketch, 'native_splines', [])
        if not native_splines:
            return

        for spline in native_splines:
            if spline.construction:
                continue

            # Spline als Linien-Approximation für Anzeige
            try:
                lines = spline.to_lines(segments=50)
                if not lines:
                    continue

                col = DesignTokens.COLOR_GEO_CONSTRUCTION if spline.construction else DesignTokens.COLOR_GEO_BODY
                width = 2

                spline_path = QPainterPath()
                first = lines[0]
                spline_path.moveTo(self.world_to_screen(first.start))
                for l in lines:
                    spline_path.lineTo(self.world_to_screen(l.end))

                p.setPen(QPen(col, width))
                p.setBrush(Qt.NoBrush)
                p.drawPath(spline_path)

            except Exception as e:
                from loguru import logger
                logger.debug(f"Native Spline Rendering fehlgeschlagen: {e}")

    def _draw_constraints(self, p):
        """Zeichnet Constraint-Icons an den betroffenen Elementen (Fusion360-Style)"""
        from loguru import logger

        p.setFont(QFont("Segoe UI", 8, QFont.Bold))

        # Speichere Bounding-Boxes für Constraint-Klick-Erkennung
        if not hasattr(self, 'constraint_icon_rects'):
            self.constraint_icon_rects = []
        self.constraint_icon_rects.clear()

        # Performance Optimization 1.4: Aggressive Viewport Culling für Constraint-Icons
        line_constraint_count = {}

        # Viewport mit Padding für Icons (Icons können leicht außerhalb sein)
        viewport_rect = QRectF(0, 0, self.width(), self.height()).adjusted(-50, -50, 50, 50)

        # Pre-filter: Nur Constraints mit Entities im Viewport
        visible_constraints = []

        for c in self.sketch.constraints:
            if not c.entities:
                continue

            entity = c.entities[0]
            is_visible = False

            if hasattr(entity, 'start') and hasattr(entity, 'end'):  # Line
                # Check ob Mittelpunkt im Viewport
                p_mid = self.world_to_screen(entity.midpoint)
                is_visible = viewport_rect.contains(p_mid)

            elif hasattr(entity, 'center'):  # Circle/Arc
                p_center = self.world_to_screen(entity.center)
                # Check Center + Radius-Bounds
                if viewport_rect.contains(p_center):
                    is_visible = True
                else:
                    # Grober Radius-Check falls Center außerhalb
                    r_screen = getattr(entity, 'radius', 0) * self.view_scale
                    bounds = QRectF(p_center.x()-r_screen, p_center.y()-r_screen, 2*r_screen, 2*r_screen)
                    is_visible = viewport_rect.intersects(bounds)

            if is_visible:
                visible_constraints.append(c)

        # Jetzt nur visible Constraints zeichnen (50-80% Reduktion bei großen Sketches!)
        for c in visible_constraints:
            try:
                if c.type == ConstraintType.HORIZONTAL and c.entities:
                    line = c.entities[0]
                    mid = self.world_to_screen(QPointF(line.midpoint.x, line.midpoint.y))
                    offset = line_constraint_count.get(line.id, 0) * 15
                    line_constraint_count[line.id] = line_constraint_count.get(line.id, 0) + 1
                    # Bounding-Box speichern
                    icon_rect = QRectF(int(mid.x())-10, int(mid.y())-18-offset, 20, 14)
                    self.constraint_icon_rects.append((c, icon_rect))
                    # Highlight wenn selektiert
                    is_selected = hasattr(self, 'selected_constraints') and c in self.selected_constraints
                    bg_color = QColor(0, 120, 212, 200) if is_selected else QColor(30, 30, 30, 180)
                    # Hintergrund-Box für bessere Lesbarkeit
                    p.setPen(Qt.NoPen)
                    p.setBrush(QBrush(bg_color))
                    p.drawRoundedRect(icon_rect, 3, 3)
                    p.setPen(QPen(self.CONSTRAINT_COLOR))
                    p.drawText(int(mid.x())-5, int(mid.y())-7-offset, "H")

                elif c.type == ConstraintType.VERTICAL and c.entities:
                    line = c.entities[0]
                    mid = self.world_to_screen(QPointF(line.midpoint.x, line.midpoint.y))
                    offset = line_constraint_count.get(line.id, 0) * 15
                    line_constraint_count[line.id] = line_constraint_count.get(line.id, 0) + 1
                    icon_rect = QRectF(int(mid.x())+5, int(mid.y())-5-offset, 20, 14)
                    self.constraint_icon_rects.append((c, icon_rect))
                    is_selected = hasattr(self, 'selected_constraints') and c in self.selected_constraints
                    bg_color = QColor(0, 120, 212, 200) if is_selected else QColor(30, 30, 30, 180)
                    p.setPen(Qt.NoPen)
                    p.setBrush(QBrush(bg_color))
                    p.drawRoundedRect(icon_rect, 3, 3)
                    p.setPen(QPen(self.CONSTRAINT_COLOR))
                    p.drawText(int(mid.x())+10, int(mid.y())+6-offset, "V")
                    
                elif c.type == ConstraintType.PARALLEL and len(c.entities) >= 2:
                    # Symbol an beiden Linien
                    for line in c.entities[:2]:
                        mid = self.world_to_screen(QPointF(line.midpoint.x, line.midpoint.y))
                        offset = line_constraint_count.get(line.id, 0) * 15
                        line_constraint_count[line.id] = line_constraint_count.get(line.id, 0) + 1
                        icon_rect = QRectF(int(mid.x())-10, int(mid.y())-18-offset, 20, 14)
                        self.constraint_icon_rects.append((c, icon_rect))
                        is_selected = hasattr(self, 'selected_constraints') and c in self.selected_constraints
                        bg_color = QColor(0, 120, 212, 200) if is_selected else QColor(30, 30, 30, 180)
                        p.setPen(Qt.NoPen)
                        p.setBrush(QBrush(bg_color))
                        p.drawRoundedRect(icon_rect, 3, 3)
                        p.setPen(QPen(QColor(100, 180, 255)))
                        p.drawText(int(mid.x())-5, int(mid.y())-7-offset, "∥")

                elif c.type == ConstraintType.PERPENDICULAR and len(c.entities) >= 2:
                    for line in c.entities[:2]:
                        mid = self.world_to_screen(QPointF(line.midpoint.x, line.midpoint.y))
                        offset = line_constraint_count.get(line.id, 0) * 15
                        line_constraint_count[line.id] = line_constraint_count.get(line.id, 0) + 1
                        icon_rect = QRectF(int(mid.x())-10, int(mid.y())-18-offset, 20, 14)
                        self.constraint_icon_rects.append((c, icon_rect))
                        is_selected = hasattr(self, 'selected_constraints') and c in self.selected_constraints
                        bg_color = QColor(0, 120, 212, 200) if is_selected else QColor(30, 30, 30, 180)
                        p.setPen(Qt.NoPen)
                        p.setBrush(QBrush(bg_color))
                        p.drawRoundedRect(icon_rect, 3, 3)
                        p.setPen(QPen(QColor(255, 180, 100)))
                        p.drawText(int(mid.x())-5, int(mid.y())-7-offset, "⊥")

                elif c.type == ConstraintType.EQUAL_LENGTH and len(c.entities) >= 2:
                    for line in c.entities[:2]:
                        mid = self.world_to_screen(QPointF(line.midpoint.x, line.midpoint.y))
                        offset = line_constraint_count.get(line.id, 0) * 15
                        line_constraint_count[line.id] = line_constraint_count.get(line.id, 0) + 1
                        icon_rect = QRectF(int(mid.x())-10, int(mid.y())-18-offset, 20, 14)
                        self.constraint_icon_rects.append((c, icon_rect))
                        is_selected = hasattr(self, 'selected_constraints') and c in self.selected_constraints
                        bg_color = QColor(0, 120, 212, 200) if is_selected else QColor(30, 30, 30, 180)
                        p.setPen(Qt.NoPen)
                        p.setBrush(QBrush(bg_color))
                        p.drawRoundedRect(icon_rect, 3, 3)
                        p.setPen(QPen(QColor(200, 100, 255)))
                        p.drawText(int(mid.x())-4, int(mid.y())-7-offset, "=")
                        
                elif c.type == ConstraintType.LENGTH:
                    if c.value and c.entities:
                        line = c.entities[0]

                        # 1. Bildschirm-Koordinaten berechnen
                        s_start = self.world_to_screen(QPointF(line.start.x, line.start.y))
                        s_end = self.world_to_screen(QPointF(line.end.x, line.end.y))

                        # 2. Mittelpunkt auf dem Bildschirm
                        mid = (s_start + s_end) / 2

                        # 3. Normalenvektor berechnen (Senkrecht zur Linie)
                        dx = s_end.x() - s_start.x()
                        dy = s_end.y() - s_start.y()
                        length_screen = math.hypot(dx, dy)

                        text_pos = mid

                        if length_screen > 0:
                            # Einheitsvektor der Normalen (-dy, dx) ist 90° rotiert
                            # Wir nutzen einen Offset von 30 Pixeln
                            offset_dist = 30

                            # Einfache Heuristik: Wir schieben immer in eine bestimmte relative Richtung,
                            # damit es bei Rechtecken meistens "außen" landet (hängt von der Zeichenrichtung ab)
                            nx = -dy / length_screen
                            ny = dx / length_screen

                            text_pos = QPointF(mid.x() + nx * offset_dist, mid.y() + ny * offset_dist)

                            # Eine dünne Hilfslinie zeichnen (Dimension Line Style)
                            p.setPen(QPen(QColor(100, 100, 100, 100), 1, Qt.DashLine))
                            p.drawLine(mid, text_pos)

                        if c.formula:
                            text = f"{c.formula} = {c.value:.1f}"
                        else:
                            text = f"{c.value:.1f}"

                        # Box zeichnen
                        fm = QFontMetrics(p.font())
                        rect = fm.boundingRect(text)
                        box_w = rect.width() + 10
                        box_h = rect.height() + 4

                        icon_rect = QRectF(int(text_pos.x() - box_w/2), int(text_pos.y() - box_h/2), box_w, box_h)
                        self.constraint_icon_rects.append((c, icon_rect))
                        is_selected = hasattr(self, 'selected_constraints') and c in self.selected_constraints
                        bg_color = QColor(0, 120, 212, 200) if is_selected else QColor(30, 30, 30, 200)

                        p.setPen(Qt.NoPen)
                        p.setBrush(QBrush(bg_color))
                        # Zentrierte Box am neuen Ort
                        p.drawRoundedRect(icon_rect, 3, 3)

                        p.setPen(QPen(self.DIM_COLOR))
                        # Text zentrieren
                        p.drawText(int(text_pos.x() - rect.width()/2),
                                   int(text_pos.y() + rect.height()/2 - 3), text)
                    
                elif c.type == ConstraintType.RADIUS:
                    # Debug: Check why RADIUS constraints might not be drawn
                    if not c.value:
                        logger.warning(f"[Constraints] RADIUS constraint has no value: {c}")
                    if not c.entities:
                        logger.warning(f"[Constraints] RADIUS constraint has no entities: {c}")

                    if c.value and c.entities:
                        circle = c.entities[0]
                        r_screen = circle.radius * self.view_scale

                        # Mittelpunkt im Screen-Space
                        center = self.world_to_screen(QPointF(circle.center.x, circle.center.y))

                        # Wir zeichnen die Bemaßung immer in einem festen Winkel (z.B. 45° nach rechts oben)
                        # Das sieht meistens am saubersten aus.
                        angle_deg = -45
                        angle_rad = math.radians(angle_deg)

                        # Richtung berechnen
                        dir_x = math.cos(angle_rad)
                        dir_y = math.sin(angle_rad)

                        # Punkt auf dem Kreisring
                        rim_x = center.x() + dir_x * r_screen
                        rim_y = center.y() + dir_y * r_screen
                        p_rim = QPointF(rim_x, rim_y)

                        # Punkt für den Text (etwas weiter draußen)
                        offset = 40  # Länge der Linie nach außen
                        text_x = rim_x + dir_x * offset
                        text_y = rim_y + dir_y * offset
                        p_text = QPointF(text_x, text_y)

                        # 1. Linie vom Zentrum zum Text
                        p.setPen(QPen(self.DIM_COLOR, 1, Qt.DashLine))
                        p.drawLine(center, p_text)

                        # 2. Optional: Kleiner Punkt oder Pfeil am Kreisring
                        p.setBrush(QBrush(self.DIM_COLOR))
                        p.drawEllipse(p_rim, 2, 2)

                        # 3. Text Box
                        if c.formula:
                            text = f"R {c.formula} = {c.value:.1f}"
                        else:
                            text = f"R{c.value:.1f}"
                        fm = QFontMetrics(p.font())
                        rect = fm.boundingRect(text)

                        icon_rect = QRectF(int(p_text.x() - rect.width()/2 - 4),
                                           int(p_text.y() - rect.height()/2 - 2),
                                           rect.width()+8, rect.height()+4)
                        self.constraint_icon_rects.append((c, icon_rect))
                        is_selected = hasattr(self, 'selected_constraints') and c in self.selected_constraints
                        bg_color = QColor(0, 120, 212, 200) if is_selected else QColor(30, 30, 30, 200)

                        # Hintergrund für Text
                        p.setPen(Qt.NoPen)
                        p.setBrush(QBrush(bg_color))
                        p.drawRoundedRect(icon_rect, 3, 3)

                        # Text selbst
                        p.setPen(QPen(self.DIM_COLOR))
                        p.drawText(int(p_text.x() - rect.width()/2),
                                   int(p_text.y() + rect.height()/2 - 2), text)
                    
                elif c.type == ConstraintType.CONCENTRIC and len(c.entities) >= 2:
                    # Symbol am Mittelpunkt
                    for circ in c.entities[:2]:
                        if hasattr(circ, 'center'):
                            pos = self.world_to_screen(QPointF(circ.center.x, circ.center.y))
                            p.setPen(QPen(QColor(255, 200, 100), 2))
                            p.setBrush(Qt.NoBrush)
                            p.drawEllipse(int(pos.x())-6, int(pos.y())-6, 12, 12)
                            p.drawEllipse(int(pos.x())-3, int(pos.y())-3, 6, 6)
                            
            except Exception:
                pass  # Constraint-Zeichenfehler ignorieren
    
    def _draw_preview(self, p):
        # Für Bearbeitungstools auch ohne tool_points zeichnen wenn tool_step > 0
        edit_tools = [SketchTool.MOVE, SketchTool.COPY, SketchTool.ROTATE, SketchTool.MIRROR, SketchTool.SCALE]
        if not self.tool_points and self.tool_step == 0 and self.current_tool not in edit_tools:
            return
        
        p.setPen(QPen(self.PREVIEW_COLOR, 2, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        snap = self.current_snap[0] if self.current_snap else self.mouse_world
        
        # Bei aktivem DimensionInput: Live-Werte für Preview nutzen!
        use_dim_input = self.dim_input.isVisible() and self.dim_input_active
        
        if self.current_tool == SketchTool.LINE and self.tool_step >= 1:
            start = self.tool_points[-1]
            if use_dim_input:
                # Live-Preview mit eingegebenen Werten
                end_x = start.x() + self.live_length * math.cos(math.radians(self.live_angle))
                end_y = start.y() + self.live_length * math.sin(math.radians(self.live_angle))
                end = QPointF(end_x, end_y)
                p.drawLine(self.world_to_screen(start), self.world_to_screen(end))
            else:
                p.drawLine(self.world_to_screen(start), self.world_to_screen(snap))
                
        elif self.current_tool == SketchTool.RECTANGLE and self.tool_step >= 1:
            p1 = self.tool_points[0]
            if use_dim_input and self.live_width > 0 and self.live_height > 0:
                # Live-Preview mit eingegebenen Maßen
                if self.rect_mode == 1:  # Center
                    rect_world = QRectF(p1.x()-self.live_width/2, p1.y()-self.live_height/2, 
                                       self.live_width, self.live_height)
                else:  # 2-Punkt: Richtung von Mausposition!
                    # X-Richtung
                    if snap.x() < p1.x():
                        x = p1.x() - self.live_width
                    else:
                        x = p1.x()
                    # Y-Richtung
                    if snap.y() < p1.y():
                        y = p1.y() - self.live_height
                    else:
                        y = p1.y()
                    rect_world = QRectF(x, y, self.live_width, self.live_height)
                tl = self.world_to_screen(QPointF(rect_world.left(), rect_world.top()))
                br = self.world_to_screen(QPointF(rect_world.right(), rect_world.bottom()))
                p.drawRect(QRectF(tl, br).normalized())
            else:
                if self.rect_mode == 1:  # Center
                    c = p1
                    w, h = abs(snap.x()-c.x())*2, abs(snap.y()-c.y())*2
                    rect_world = QRectF(c.x()-w/2, c.y()-h/2, w, h)
                    tl = self.world_to_screen(QPointF(rect_world.left(), rect_world.top()))
                    br = self.world_to_screen(QPointF(rect_world.right(), rect_world.bottom()))
                    p.drawRect(QRectF(tl, br).normalized())
                else:
                    p.drawRect(QRectF(self.world_to_screen(p1), self.world_to_screen(snap)).normalized())
                    
        elif self.current_tool == SketchTool.RECTANGLE_CENTER and self.tool_step == 1:
            c = self.tool_points[0]
            if use_dim_input and self.live_width > 0 and self.live_height > 0:
                rect_world = QRectF(c.x()-self.live_width/2, c.y()-self.live_height/2, 
                                   self.live_width, self.live_height)
            else:
                w, h = abs(snap.x()-c.x())*2, abs(snap.y()-c.y())*2
                rect_world = QRectF(c.x()-w/2, c.y()-h/2, w, h)
            p1 = self.world_to_screen(QPointF(rect_world.left(), rect_world.top()))
            p2 = self.world_to_screen(QPointF(rect_world.right(), rect_world.bottom()))
            p.drawRect(QRectF(p1, p2).normalized())
            
        elif self.current_tool == SketchTool.CIRCLE and self.tool_step >= 1:
            if self.circle_mode == 0:
                # Center-Radius Modus: tool_points[0] ist Center
                ctr = self.world_to_screen(self.tool_points[0])
                if use_dim_input and self.live_radius > 0:
                    r = self.live_radius * self.view_scale
                else:
                    c = self.tool_points[0]
                    r = math.hypot(snap.x()-c.x(), snap.y()-c.y()) * self.view_scale
                p.drawEllipse(ctr, r, r)
            elif self.circle_mode == 1:
                # 2-Punkt Modus: Center ist zwischen tool_points[0] und snap
                p1 = self.tool_points[0]
                cx, cy = (p1.x() + snap.x()) / 2, (p1.y() + snap.y()) / 2
                r = math.hypot(snap.x() - p1.x(), snap.y() - p1.y()) / 2 * self.view_scale
                ctr = self.world_to_screen(QPointF(cx, cy))
                p.drawEllipse(ctr, r, r)
                # Durchmesser-Linie anzeigen
                p.drawLine(self.world_to_screen(p1), self.world_to_screen(snap))
            elif self.circle_mode == 2:
                # 3-Punkt Modus
                if self.tool_step == 1:
                    # Nur erster Punkt - zeige Linie zum Cursor
                    p.drawLine(self.world_to_screen(self.tool_points[0]), self.world_to_screen(snap))
                elif self.tool_step == 2:
                    # Zwei Punkte - berechne Kreis durch alle 3
                    p1, p2 = self.tool_points[0], self.tool_points[1]
                    p3 = snap
                    center, radius = self._calc_circle_3points(p1, p2, p3)
                    if center and radius > 0.01:
                        ctr = self.world_to_screen(center)
                        r = radius * self.view_scale
                        p.drawEllipse(ctr, r, r)
                    # Punkte markieren
                    for pt in [p1, p2]:
                        p.drawEllipse(self.world_to_screen(pt), 4, 4)
            
        elif self.current_tool == SketchTool.POLYGON and self.tool_step == 1:
            c = self.tool_points[0]
            if use_dim_input and self.live_radius > 0:
                r = self.live_radius
            else:
                r = math.hypot(snap.x()-c.x(), snap.y()-c.y())
            # FIX: Use live_angle when dim_input is active, otherwise calculate from mouse
            if use_dim_input:
                sa = math.radians(self.live_angle)
            else:
                sa = math.atan2(snap.y()-c.y(), snap.x()-c.x())
            pts = [self.world_to_screen(QPointF(c.x() + r*math.cos(sa + 2*math.pi*i/self.polygon_sides), c.y() + r*math.sin(sa + 2*math.pi*i/self.polygon_sides))) for i in range(self.polygon_sides)]
            p.drawPolygon(QPolygonF(pts))
        
        elif self.current_tool == SketchTool.NUT and self.tool_step == 1:
            # NUT Preview mit Rotation
            c = self.tool_points[0]
            rotation_angle = math.atan2(snap.y()-c.y(), snap.x()-c.x())
            
            # Schlüsselweite und Radius berechnen
            size_name = self.nut_size_names[self.nut_size_index]
            sw = self.nut_sizes[size_name] + self.nut_tolerance
            hex_radius = sw / math.sqrt(3)
            screw_diameter = float(size_name[1:])
            hole_radius = (screw_diameter + self.nut_tolerance) / 2
            
            # Sechskant zeichnen
            pts = []
            for i in range(6):
                angle = rotation_angle + math.radians(30 + i * 60)
                px = c.x() + hex_radius * math.cos(angle)
                py = c.y() + hex_radius * math.sin(angle)
                pts.append(self.world_to_screen(QPointF(px, py)))
            p.drawPolygon(QPolygonF(pts))
            
            # Schraubenloch zeichnen
            ctr = self.world_to_screen(c)
            r_screen = hole_radius * self.view_scale
            p.drawEllipse(ctr, r_screen, r_screen)

        elif self.current_tool == SketchTool.STAR and self.tool_step >= 1:
            # Star Preview mit Live-Werten aus dimension input
            c = self.tool_points[0]

            # Hole Werte aus dim_input (wenn vorhanden)
            if hasattr(self, 'dim_input') and self.dim_input.isVisible():
                values = self.dim_input.get_values()
                n = int(values.get("points", 5))
                ro = values.get("r_outer", 50.0)
                ri = values.get("r_inner", 25.0)
            else:
                n = 5
                ro = 50.0
                ri = 25.0

            # Stern-Punkte berechnen
            pts = []
            step = math.pi / n
            for i in range(2 * n):
                r = ro if i % 2 == 0 else ri
                angle = i * step - math.pi / 2  # Startet oben
                px = c.x() + r * math.cos(angle)
                py = c.y() + r * math.sin(angle)
                pts.append(self.world_to_screen(QPointF(px, py)))

            # Stern zeichnen
            p.drawPolygon(QPolygonF(pts))

        elif self.current_tool == SketchTool.SLOT:
            if self.tool_step == 1:
                # Schritt 1: Linie zeigen (mit dim_input-Werten wenn aktiv)
                p1 = self.tool_points[0]
                # Debug: Check if dim_input values should be used
                dim_visible = self.dim_input.isVisible() if hasattr(self, 'dim_input') else False
                dim_active = getattr(self, 'dim_input_active', False)
                if use_dim_input and self.live_length > 0:
                    # Use locked length/angle values
                    length = self.live_length
                    angle = math.radians(self.live_angle)
                    end_x = p1.x() + length * math.cos(angle)
                    end_y = p1.y() + length * math.sin(angle)
                    end_pt = QPointF(end_x, end_y)
                    logger.debug(f"[SLOT-PREVIEW] Using dim_input: L={length:.1f}, A={self.live_angle:.1f}°")
                else:
                    end_pt = snap
                    logger.debug(f"[SLOT-PREVIEW] use_dim_input={use_dim_input}, live_length={self.live_length}")
                p.drawLine(self.world_to_screen(p1), self.world_to_screen(end_pt))
            elif self.tool_step == 2:
                # Schritt 2: Langloch mit abgerundeten Enden
                p1, p2 = self.tool_points[0], self.tool_points[1]
                dx, dy = p2.x()-p1.x(), p2.y()-p1.y()
                length = math.hypot(dx, dy)
                if length > 0.01:
                    nx, ny = -dy/length, dx/length
                    # FIX: Use live_radius when dim_input is active
                    if use_dim_input and self.live_radius > 0:
                        hw = self.live_radius
                    else:
                        width = abs((snap.x()-p1.x())*nx + (snap.y()-p1.y())*ny) * 2
                        hw = width/2
                    
                    # Langloch-Form mit Halbkreisen an den Enden
                    from PySide6.QtGui import QPainterPath
                    path = QPainterPath()
                    
                    # Start-Halbkreis (um p1)
                    p1_screen = self.world_to_screen(p1)
                    p2_screen = self.world_to_screen(p2)
                    hw_screen = hw * self.view_scale

                    # Winkel der Mittellinie - direkt im Screen-Space berechnen!
                    # (Robuster Ansatz: Punkte transformieren, dann Winkel messen)
                    screen_dx = p2_screen.x() - p1_screen.x()
                    screen_dy = p2_screen.y() - p1_screen.y()
                    screen_angle = math.degrees(math.atan2(screen_dy, screen_dx))
                    # Qt-Konvention: Negieren weil screen Y nach unten zeigt
                    qt_angle = -screen_angle

                    # Obere Linie
                    top1 = self.world_to_screen(QPointF(p1.x()+nx*hw, p1.y()+ny*hw))
                    top2 = self.world_to_screen(QPointF(p2.x()+nx*hw, p2.y()+ny*hw))
                    # Untere Linie
                    bot1 = self.world_to_screen(QPointF(p1.x()-nx*hw, p1.y()-ny*hw))
                    bot2 = self.world_to_screen(QPointF(p2.x()-nx*hw, p2.y()-ny*hw))

                    # Path aufbauen
                    path.moveTo(top1)
                    path.lineTo(top2)
                    # Halbkreis um p2
                    rect2 = QRectF(p2_screen.x()-hw_screen, p2_screen.y()-hw_screen, hw_screen*2, hw_screen*2)
                    path.arcTo(rect2, qt_angle + 90, -180)
                    path.lineTo(bot1)
                    # Halbkreis um p1
                    rect1 = QRectF(p1_screen.x()-hw_screen, p1_screen.y()-hw_screen, hw_screen*2, hw_screen*2)
                    path.arcTo(rect1, qt_angle - 90, -180)
                    path.closeSubpath()
                    
                    p.drawPath(path)
        elif self.current_tool == SketchTool.PROJECT and hasattr(self, 'hovered_ref_edge') and self.hovered_ref_edge:
            x1, y1, x2, y2 = self.hovered_ref_edge
            p1 = self.world_to_screen(QPointF(x1, y1))
            p2 = self.world_to_screen(QPointF(x2, y2))
            
            # Fusion 360 Style: Magenta/Lila Highlight für Projektion
            pen = QPen(QColor(255, 0, 255), 3) # Magenta, Dicke 3
            p.setPen(pen)
            p.drawLine(p1, p2)
            
            # Kleine Endpunkte zur Orientierung
            p.setBrush(QBrush(QColor(255, 0, 255)))
            p.drawEllipse(p1, 4, 4)
            p.drawEllipse(p2, 4, 4)
            
            # Cursor-Text (Optional, aber cool)
            p.setFont(QFont("Arial", 8))
            p.drawText(int(p2.x()) + 10, int(p2.y()), "Project")
        elif self.current_tool == SketchTool.ARC_3POINT and self.tool_points:
            for pt in self.tool_points:
                p.drawEllipse(self.world_to_screen(pt), 4, 4)
        elif self.current_tool == SketchTool.SPLINE and len(self.tool_points) >= 1:
            for pt in self.tool_points:
                p.drawEllipse(self.world_to_screen(pt), 4, 4)
            if len(self.tool_points) >= 2:
                try:
                    from gui.generators import generate_spline_points
                    ctrl_pts = [(pt.x(), pt.y()) for pt in self.tool_points] + [(snap.x(), snap.y())]
                    spline_pts = generate_spline_points(ctrl_pts, segments_per_span=6)
                    for i in range(len(spline_pts) - 1):
                        p.drawLine(self.world_to_screen(QPointF(spline_pts[i][0], spline_pts[i][1])), self.world_to_screen(QPointF(spline_pts[i+1][0], spline_pts[i+1][1])))
                except: pass
        
        # === PREVIEW FÜR BEARBEITUNGSTOOLS ===
        
        # MOVE Preview
        elif self.current_tool == SketchTool.MOVE and self.tool_step == 1:
            # Bei aktiver Tab-Eingabe: Werte aus dim_input verwenden
            if self.dim_input_active and self.dim_input.isVisible():
                try:
                    vals = self.dim_input.get_values()
                    dx = vals.get("dx", 0)
                    dy = vals.get("dy", 0)
                except:
                    dx = snap.x() - self.tool_points[0].x()
                    dy = snap.y() - self.tool_points[0].y()
            else:
                dx = snap.x() - self.tool_points[0].x()
                dy = snap.y() - self.tool_points[0].y()
            
            p.setPen(QPen(QColor(0, 200, 100), 2, Qt.DashLine))
            # Zeige verschobene Linien
            for line in self.selected_lines:
                s = self.world_to_screen(QPointF(line.start.x + dx, line.start.y + dy))
                e = self.world_to_screen(QPointF(line.end.x + dx, line.end.y + dy))
                p.drawLine(s, e)
            # Zeige verschobene Kreise
            for c in self.selected_circles:
                ctr = self.world_to_screen(QPointF(c.center.x + dx, c.center.y + dy))
                r = c.radius * self.view_scale
                p.drawEllipse(ctr, r, r)
            # Zeige Verschiebungspfeil und Offset-Text
            base_screen = self.world_to_screen(self.tool_points[0])
            target_screen = self.world_to_screen(QPointF(self.tool_points[0].x() + dx, self.tool_points[0].y() + dy))
            p.setPen(QPen(QColor(255, 200, 0), 2))
            p.drawLine(base_screen, target_screen)
            # X/Y Offset-Anzeige
            p.setFont(QFont("Arial", 10, QFont.Bold))
            p.setPen(QPen(QColor(255, 200, 0)))
            offset_text = f"ΔX: {dx:.1f}  ΔY: {dy:.1f}"
            text_pos = QPointF((base_screen.x() + target_screen.x()) / 2, 
                               (base_screen.y() + target_screen.y()) / 2 - 15)
            p.drawText(int(text_pos.x()) - 50, int(text_pos.y()), offset_text)
        
        # COPY Preview
        elif self.current_tool == SketchTool.COPY and self.tool_step == 1:
            # Bei aktiver Tab-Eingabe: Werte aus dim_input verwenden
            if self.dim_input_active and self.dim_input.isVisible():
                try:
                    vals = self.dim_input.get_values()
                    dx = vals.get("dx", 0)
                    dy = vals.get("dy", 0)
                except:
                    dx = snap.x() - self.tool_points[0].x()
                    dy = snap.y() - self.tool_points[0].y()
            else:
                dx = snap.x() - self.tool_points[0].x()
                dy = snap.y() - self.tool_points[0].y()

            p.setPen(QPen(QColor(100, 200, 255), 2, Qt.DashLine))
            for line in self.selected_lines:
                s = self.world_to_screen(QPointF(line.start.x + dx, line.start.y + dy))
                e = self.world_to_screen(QPointF(line.end.x + dx, line.end.y + dy))
                p.drawLine(s, e)
            for c in self.selected_circles:
                ctr = self.world_to_screen(QPointF(c.center.x + dx, c.center.y + dy))
                r = c.radius * self.view_scale
                p.drawEllipse(ctr, r, r)
            # Verschiebungspfeil und Offset-Text
            p.setPen(QPen(QColor(255, 200, 0), 2))
            base_screen = self.world_to_screen(self.tool_points[0])
            target_screen = self.world_to_screen(QPointF(self.tool_points[0].x() + dx, self.tool_points[0].y() + dy))
            p.drawLine(base_screen, target_screen)
            # Offset-Anzeige
            p.setFont(QFont("Arial", 10, QFont.Bold))
            offset_text = f"ΔX: {dx:.1f}  ΔY: {dy:.1f}"
            text_pos = QPointF((base_screen.x() + target_screen.x()) / 2,
                               (base_screen.y() + target_screen.y()) / 2 - 15)
            p.drawText(int(text_pos.x()) - 50, int(text_pos.y()), offset_text)
        
        # ROTATE Preview
        elif self.current_tool == SketchTool.ROTATE and self.tool_step == 1:
            center = self.tool_points[0]
            
            # Bei aktiver Tab-Eingabe: Winkel aus dim_input verwenden
            if self.dim_input_active and self.dim_input.isVisible():
                try:
                    vals = self.dim_input.get_values()
                    angle_deg = vals.get("angle", 0)
                    angle = math.radians(angle_deg)
                except:
                    angle = math.atan2(snap.y() - center.y(), snap.x() - center.x())
                    angle_deg = math.degrees(angle)
            else:
                angle = math.atan2(snap.y() - center.y(), snap.x() - center.x())
                angle_deg = math.degrees(angle)
            
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            p.setPen(QPen(QColor(255, 150, 0), 2, Qt.DashLine))
            for line in self.selected_lines:
                for pt in [(line.start.x, line.start.y), (line.end.x, line.end.y)]:
                    dx, dy = pt[0] - center.x(), pt[1] - center.y()
                    rx = center.x() + dx * cos_a - dy * sin_a
                    ry = center.y() + dx * sin_a + dy * cos_a
                    if pt == (line.start.x, line.start.y):
                        rs = self.world_to_screen(QPointF(rx, ry))
                    else:
                        re = self.world_to_screen(QPointF(rx, ry))
                p.drawLine(rs, re)
            for c in self.selected_circles:
                dx, dy = c.center.x - center.x(), c.center.y - center.y()
                rx = center.x() + dx * cos_a - dy * sin_a
                ry = center.y() + dx * sin_a + dy * cos_a
                ctr = self.world_to_screen(QPointF(rx, ry))
                r = c.radius * self.view_scale
                p.drawEllipse(ctr, r, r)
            # Zeige Rotationszentrum und Winkel
            p.setPen(QPen(QColor(255, 200, 0), 2))
            ctr_screen = self.world_to_screen(center)
            p.drawLine(int(ctr_screen.x())-10, int(ctr_screen.y()), int(ctr_screen.x())+10, int(ctr_screen.y()))
            p.drawLine(int(ctr_screen.x()), int(ctr_screen.y())-10, int(ctr_screen.x()), int(ctr_screen.y())+10)
            # Winkel-Anzeige
            p.setFont(QFont("Arial", 10, QFont.Bold))
            p.drawText(int(ctr_screen.x()) + 15, int(ctr_screen.y()) - 15, f"∠ {angle_deg:.1f}°")
        
        # MIRROR Preview
        elif self.current_tool == SketchTool.MIRROR and self.tool_step == 1:
            p1 = self.tool_points[0]
            p2 = snap
            # Zeige Spiegelachse
            p.setPen(QPen(QColor(255, 100, 100), 2, Qt.DashDotLine))
            p.drawLine(self.world_to_screen(p1), self.world_to_screen(p2))
            # Gespiegelte Elemente
            dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
            length = math.hypot(dx, dy)
            if length > 0.01:
                dx, dy = dx / length, dy / length
                def mirror_pt(px, py):
                    t = (px - p1.x()) * dx + (py - p1.y()) * dy
                    proj_x, proj_y = p1.x() + t * dx, p1.y() + t * dy
                    return 2 * proj_x - px, 2 * proj_y - py
                p.setPen(QPen(QColor(255, 150, 200), 2, Qt.DashLine))
                for line in self.selected_lines:
                    sx, sy = mirror_pt(line.start.x, line.start.y)
                    ex, ey = mirror_pt(line.end.x, line.end.y)
                    p.drawLine(self.world_to_screen(QPointF(sx, sy)), self.world_to_screen(QPointF(ex, ey)))
                for c in self.selected_circles:
                    cx, cy = mirror_pt(c.center.x, c.center.y)
                    ctr = self.world_to_screen(QPointF(cx, cy))
                    r = c.radius * self.view_scale
                    p.drawEllipse(ctr, r, r)
        
        # SCALE Preview
        elif self.current_tool == SketchTool.SCALE and self.tool_step == 1:
            center = self.tool_points[0]
            
            # Bei aktiver Tab-Eingabe: Faktor aus dim_input verwenden
            if self.dim_input_active and self.dim_input.isVisible():
                try:
                    vals = self.dim_input.get_values()
                    factor = vals.get("factor", 1.0)
                except:
                    current_dist = math.hypot(snap.x() - center.x(), snap.y() - center.y())
                    base_dist = self.tool_data.get('base_dist', current_dist)
                    factor = current_dist / base_dist if base_dist > 0.01 else 1.0
            else:
                current_dist = math.hypot(snap.x() - center.x(), snap.y() - center.y())
                base_dist = self.tool_data.get('base_dist', current_dist)
                factor = current_dist / base_dist if base_dist > 0.01 else 1.0
            
            p.setPen(QPen(QColor(200, 100, 255), 2, Qt.DashLine))
            for line in self.selected_lines:
                sx = center.x() + (line.start.x - center.x()) * factor
                sy = center.y() + (line.start.y - center.y()) * factor
                ex = center.x() + (line.end.x - center.x()) * factor
                ey = center.y() + (line.end.y - center.y()) * factor
                p.drawLine(self.world_to_screen(QPointF(sx, sy)), self.world_to_screen(QPointF(ex, ey)))
            for c in self.selected_circles:
                cx = center.x() + (c.center.x - center.x()) * factor
                cy = center.y() + (c.center.y - center.y()) * factor
                ctr = self.world_to_screen(QPointF(cx, cy))
                r = c.radius * factor * self.view_scale
                p.drawEllipse(ctr, r, r)
            # Zeige Skalierungszentrum
            p.setPen(QPen(QColor(255, 200, 0), 2))
            ctr_screen = self.world_to_screen(center)
            p.drawEllipse(ctr_screen, 5, 5)
            # Faktor-Anzeige
            p.setFont(QFont("Arial", 10, QFont.Bold))
            p.drawText(int(ctr_screen.x()) + 10, int(ctr_screen.y()) - 10, f"×{factor:.2f}")
        
        # PATTERN LINEAR Preview
        elif self.current_tool == SketchTool.PATTERN_LINEAR and self.tool_step == 1:
            start = self.tool_points[0]
            dx = snap.x() - start.x()
            dy = snap.y() - start.y()
            total_dist = math.hypot(dx, dy)

            # Werte aus tool_data (werden durch DimensionInput aktualisiert)
            count = self.tool_data.get('pattern_count', 3)
            spacing = self.tool_data.get('pattern_spacing', 20.0)

            # Richtung berechnen
            if total_dist > 0.01:
                ux, uy = dx / total_dist, dy / total_dist
            else:
                # Fallback: gespeicherte Richtung oder Default
                direction = self.tool_data.get('pattern_direction', (1.0, 0.0))
                ux, uy = direction

            p.setPen(QPen(QColor(100, 200, 255), 2, Qt.DashLine))

            # Zeichne Preview für jede Kopie (inkl. Arcs)
            for i in range(1, count):
                offset_x = ux * spacing * i
                offset_y = uy * spacing * i

                for line in self.selected_lines:
                    s = self.world_to_screen(QPointF(line.start.x + offset_x, line.start.y + offset_y))
                    e = self.world_to_screen(QPointF(line.end.x + offset_x, line.end.y + offset_y))
                    p.drawLine(s, e)

                for c in self.selected_circles:
                    ctr = self.world_to_screen(QPointF(c.center.x + offset_x, c.center.y + offset_y))
                    r = c.radius * self.view_scale
                    p.drawEllipse(ctr, r, r)

                for arc in self.selected_arcs:
                    # Screen-Space Arc Rendering (robust)
                    arc_cx = arc.center.x + offset_x
                    arc_cy = arc.center.y + offset_y
                    ctr = self.world_to_screen(QPointF(arc_cx, arc_cy))
                    r = arc.radius * self.view_scale
                    rect = QRectF(ctr.x() - r, ctr.y() - r, 2 * r, 2 * r)

                    # Berechne Start/End in World, transformiere zu Screen
                    p_start = self.world_to_screen(QPointF(
                        arc_cx + arc.radius * math.cos(math.radians(arc.start_angle)),
                        arc_cy + arc.radius * math.sin(math.radians(arc.start_angle))
                    ))
                    p_end = self.world_to_screen(QPointF(
                        arc_cx + arc.radius * math.cos(math.radians(arc.end_angle)),
                        arc_cy + arc.radius * math.sin(math.radians(arc.end_angle))
                    ))

                    # Winkel im Screen-Space messen
                    screen_a1 = math.degrees(math.atan2(p_start.y() - ctr.y(), p_start.x() - ctr.x()))
                    screen_a2 = math.degrees(math.atan2(p_end.y() - ctr.y(), p_end.x() - ctr.x()))
                    qt_start = -screen_a1
                    qt_sweep = ((-screen_a2) - qt_start + 180) % 360 - 180

                    p.drawArc(rect, int(qt_start * 16), int(qt_sweep * 16))

            # Richtungspfeil und Info
            p.setPen(QPen(QColor(255, 200, 0), 2))
            if total_dist > 0.01:
                p.drawLine(self.world_to_screen(start), self.world_to_screen(snap))
            else:
                # Zeige Richtung mit spacing
                end_pt = QPointF(start.x() + ux * spacing, start.y() + uy * spacing)
                p.drawLine(self.world_to_screen(start), self.world_to_screen(end_pt))

            p.setFont(QFont("Arial", 10, QFont.Bold))
            mid = self.world_to_screen(QPointF(start.x() + ux * spacing / 2, start.y() + uy * spacing / 2))
            p.drawText(int(mid.x()) + 10, int(mid.y()) - 10, f"{count}× @ {spacing:.1f}mm")
        
        # PATTERN CIRCULAR Preview
        elif self.current_tool == SketchTool.PATTERN_CIRCULAR and self.tool_step == 1:
            center = self.tool_points[0]
            count = self.tool_data.get('pattern_count', 6)
            total_angle = self.tool_data.get('pattern_angle', 360.0)
            angle_step = math.radians(total_angle / count)

            p.setPen(QPen(QColor(255, 150, 100), 2, Qt.DashLine))

            # Zeichne Preview für jede Kopie (inkl. Arcs)
            for i in range(1, count):
                angle = angle_step * i
                cos_a, sin_a = math.cos(angle), math.sin(angle)

                for line in self.selected_lines:
                    sx = center.x() + (line.start.x - center.x()) * cos_a - (line.start.y - center.y()) * sin_a
                    sy = center.y() + (line.start.x - center.x()) * sin_a + (line.start.y - center.y()) * cos_a
                    ex = center.x() + (line.end.x - center.x()) * cos_a - (line.end.y - center.y()) * sin_a
                    ey = center.y() + (line.end.x - center.x()) * sin_a + (line.end.y - center.y()) * cos_a
                    p.drawLine(self.world_to_screen(QPointF(sx, sy)), self.world_to_screen(QPointF(ex, ey)))

                for c in self.selected_circles:
                    cx = center.x() + (c.center.x - center.x()) * cos_a - (c.center.y - center.y()) * sin_a
                    cy = center.y() + (c.center.x - center.x()) * sin_a + (c.center.y - center.y()) * cos_a
                    ctr = self.world_to_screen(QPointF(cx, cy))
                    r = c.radius * self.view_scale
                    p.drawEllipse(ctr, r, r)

                for arc in self.selected_arcs:
                    # Arc-Zentrum rotieren
                    acx = center.x() + (arc.center.x - center.x()) * cos_a - (arc.center.y - center.y()) * sin_a
                    acy = center.y() + (arc.center.x - center.x()) * sin_a + (arc.center.y - center.y()) * cos_a
                    ctr = self.world_to_screen(QPointF(acx, acy))
                    r = arc.radius * self.view_scale
                    rect = QRectF(ctr.x() - r, ctr.y() - r, 2 * r, 2 * r)

                    # Screen-Space Arc Rendering (robust)
                    # Arc-Winkel um den Pattern-Winkel rotieren
                    new_start_world = arc.start_angle + math.degrees(angle)
                    new_end_world = arc.end_angle + math.degrees(angle)

                    # Berechne Start/End in World, transformiere zu Screen
                    p_start = self.world_to_screen(QPointF(
                        acx + arc.radius * math.cos(math.radians(new_start_world)),
                        acy + arc.radius * math.sin(math.radians(new_start_world))
                    ))
                    p_end = self.world_to_screen(QPointF(
                        acx + arc.radius * math.cos(math.radians(new_end_world)),
                        acy + arc.radius * math.sin(math.radians(new_end_world))
                    ))

                    # Winkel im Screen-Space messen
                    screen_a1 = math.degrees(math.atan2(p_start.y() - ctr.y(), p_start.x() - ctr.x()))
                    screen_a2 = math.degrees(math.atan2(p_end.y() - ctr.y(), p_end.x() - ctr.x()))
                    qt_start = -screen_a1
                    qt_sweep = ((-screen_a2) - qt_start + 180) % 360 - 180

                    p.drawArc(rect, int(qt_start * 16), int(qt_sweep * 16))

            # Zentrum und Info
            p.setPen(QPen(QColor(255, 200, 0), 2))
            ctr_screen = self.world_to_screen(center)
            p.drawEllipse(ctr_screen, 8, 8)
            p.drawLine(int(ctr_screen.x()) - 12, int(ctr_screen.y()), int(ctr_screen.x()) + 12, int(ctr_screen.y()))
            p.drawLine(int(ctr_screen.x()), int(ctr_screen.y()) - 12, int(ctr_screen.x()), int(ctr_screen.y()) + 12)
            p.setFont(QFont("Arial", 10, QFont.Bold))
            p.drawText(int(ctr_screen.x()) + 15, int(ctr_screen.y()) - 15, f"{count}× über {total_angle:.0f}°")
    
    def _draw_selection_box(self, p):
        if self.selection_box_start and self.selection_box_end:
            rect = QRectF(self.selection_box_start, self.selection_box_end).normalized()
            p.setPen(QPen(self.GEO_SELECTED, 1, Qt.DashLine))
            p.setBrush(QBrush(QColor(0, 150, 255, 30)))
            p.drawRect(rect)
    
    def _draw_snap(self, p):
        if not self.current_snap or self.current_snap[1] == SnapType.GRID: return
        pos = self.world_to_screen(self.current_snap[0])
        st = self.current_snap[1]
        p.setPen(QPen(self.SNAP_COLOR, 2))
        p.setBrush(Qt.NoBrush)
        if st == SnapType.ENDPOINT: p.drawRect(int(pos.x())-5, int(pos.y())-5, 10, 10)
        elif st == SnapType.MIDPOINT:
            path = QPainterPath()
            path.moveTo(pos.x(), pos.y()-7)
            path.lineTo(pos.x()-6, pos.y()+5)
            path.lineTo(pos.x()+6, pos.y()+5)
            path.closeSubpath()
            p.drawPath(path)
        elif st == SnapType.CENTER:
            p.drawLine(int(pos.x())-7, int(pos.y()), int(pos.x())+7, int(pos.y()))
            p.drawLine(int(pos.x()), int(pos.y())-7, int(pos.x()), int(pos.y())+7)
        elif st == SnapType.QUADRANT: p.drawEllipse(pos, 5, 5)
        elif st == SnapType.INTERSECTION:
            p.drawLine(int(pos.x())-5, int(pos.y())-5, int(pos.x())+5, int(pos.y())+5)
            p.drawLine(int(pos.x())+5, int(pos.y())-5, int(pos.x())-5, int(pos.y())+5)
    
    def _draw_snap_guides(self, p: QPainter):
        """
        Zeichnet das Feedback. 
        Wichtig: Nutze QPainterPath für gestrichelte Linien (Performance).
        """
        if not self.last_snap_result or self.last_snap_result.type == SnapType.NONE:
            return

        res = self.last_snap_result
        screen_pt = self.world_to_screen(res.point)
        
        # 1. Guides (Hintergrund)
        if res.guides:
            p.setPen(QPen(QColor(0, 150, 255, 120), 1, Qt.DashLine))
            for gtype, val in res.guides:
                if gtype == "vline":
                    sx = self.world_to_screen(QPointF(val, 0)).x()
                    p.drawLine(sx, 0, sx, self.height())
                elif gtype == "hline":
                    sy = self.world_to_screen(QPointF(0, val)).y()
                    p.drawLine(0, sy, self.width(), sy)

        # 2. Der Marker (Vordergrund)
        # Fusion Style: Verschiedene Symbole für verschiedene Snaps
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.setBrush(QColor(0, 120, 255, 100)) # Blau halbtransparent
        
        s = 10 # Größe
        r = QRectF(screen_pt.x() - s/2, screen_pt.y() - s/2, s, s)
        
        if res.type == SnapType.ENDPOINT:
            p.drawRect(r) # Quadrat für Endpunkt
        elif res.type == SnapType.MIDPOINT:
            # Dreieck zeichnen
            tri = QPolygonF([
                QPointF(screen_pt.x(), screen_pt.y() - s/2),
                QPointF(screen_pt.x() - s/2, screen_pt.y() + s/2),
                QPointF(screen_pt.x() + s/2, screen_pt.y() + s/2)
            ])
            p.drawPolygon(tri)
        elif res.type == SnapType.CENTER:
            p.drawEllipse(r) # Kreis für Zentrum
        else:
            # Standard X oder kleiner Kreis
            p.drawEllipse(screen_pt, 3, 3)
    
    def _draw_fusion_input_box(self, p: QPainter, center: QPointF, label: str, value_text: str, active: bool = True):
        """
        Zeichnet eine Input-Box im Fusion-Style (Blau hinterlegt).
        """
        text = f"{label} {value_text}"
        fm = p.fontMetrics()
        rect = fm.boundingRect(text)
        
        # Padding
        pad_x = 8
        pad_y = 4
        w = rect.width() + (pad_x * 2)
        h = rect.height() + (pad_y * 2)
        
        # Box zentriert um 'center' positionieren
        x = center.x() - (w / 2)
        y = center.y() - (h / 2)
        box_rect = QRectF(x, y, w, h)
        
        # Style: Fusion Blue (#0064C8) oder Grau, wenn inaktiv
        bg_color = QColor(0, 100, 200, 220) if active else QColor(80, 80, 80, 200)
        border_color = QColor(255, 255, 255, 150)
        
        p.setPen(QPen(border_color, 1))
        p.setBrush(QBrush(bg_color))
        p.drawRoundedRect(box_rect, 4, 4)
        
        # Text
        p.setPen(QColor(255, 255, 255))
        # Text exakt zentrieren
        p.drawText(box_rect, Qt.AlignCenter, text)

        
    def _draw_live_dimensions(self, p):
        if self.tool_step == 0: return
        p.setFont(QFont("Consolas", 11, QFont.Bold))
        snap = self.current_snap[0] if self.current_snap else self.mouse_world
        if self.current_tool == SketchTool.LINE and self.tool_step >= 1:
            start = self.tool_points[-1]
            p1, p2 = self.world_to_screen(start), self.world_to_screen(snap)
            mid = QPointF((p1.x()+p2.x())/2, (p1.y()+p2.y())/2)
            text = f"{self.live_length:.1f} mm @ {self.live_angle:.1f}°"
            fm = QFontMetrics(p.font())
            rect = fm.boundingRect(text)
            p.fillRect(QRectF(mid.x()+10, mid.y()-rect.height()-5, rect.width()+10, rect.height()+6), QColor(30, 30, 30, 200))
            p.setPen(QPen(self.DIM_COLOR))
            p.drawText(int(mid.x())+15, int(mid.y())-5, text)
        elif self.current_tool in [SketchTool.RECTANGLE, SketchTool.RECTANGLE_CENTER] and self.tool_step == 1:
            p1 = self.world_to_screen(self.tool_points[0])
            p2 = self.world_to_screen(snap)
            rect = QRectF(p1, p2).normalized()
            p.setPen(QPen(self.DIM_COLOR))
            p.drawText(int(rect.center().x())-40, int(rect.bottom())+18, f"{self.live_width:.1f} × {self.live_height:.1f} mm")
        elif self.current_tool == SketchTool.CIRCLE and self.tool_step == 1:
            ctr = self.world_to_screen(self.tool_points[0])
            p.setPen(QPen(self.DIM_COLOR))
            diameter = self.live_radius * 2
            p.drawText(int(ctr.x())+10, int(ctr.y())-int(self.live_radius*self.view_scale)-8, f"R {self.live_radius:.1f} / Ø {diameter:.1f} mm")
        elif self.current_tool == SketchTool.POLYGON and self.tool_step == 1:
            ctr = self.world_to_screen(self.tool_points[0])
            p.setPen(QPen(self.DIM_COLOR))
            p.drawText(int(ctr.x())+10, int(ctr.y())-int(self.live_radius*self.view_scale)-8, f"R {self.live_radius:.1f} ({self.polygon_sides})")
    
    def _draw_hud(self, p):
        p.setPen(QPen(QColor(150, 150, 150)))
        p.setFont(QFont("Consolas", 10))
        p.drawText(10, self.height()-10, f"X: {self.mouse_world.x():.2f}  Y: {self.mouse_world.y():.2f}")
        p.drawText(self.width()-100, self.height()-10, f"Zoom: {self.view_scale:.1f}x")
        tool_name = self.current_tool.name.replace('_', ' ').title()
        p.setFont(QFont("Arial", 12, QFont.Bold))
        p.setPen(QPen(self.GEO_SELECTED))
        p.drawText(12, 25, f"Tool: {tool_name}")
        
        # Tab-Hinweis für Zeichentools (dezent)
        drawing_tools = [SketchTool.LINE, SketchTool.RECTANGLE, SketchTool.CIRCLE, 
                        SketchTool.POLYGON, SketchTool.SLOT, SketchTool.ARC_3POINT]
        if self.current_tool in drawing_tools and self.tool_step >= 1:
            p.setFont(QFont("Arial", 10))
            p.setPen(QPen(QColor(100, 180, 255, 180)))
            p.drawText(12, 65, "💡 Tab = Maße eingeben")
        
        sel_count = len(self.selected_lines) + len(self.selected_circles)
        if sel_count > 0:
            p.setFont(QFont("Arial", 10))
            p.setPen(QPen(QColor(150, 150, 150)))
            p.drawText(12, 45, f"Ausgewählt: {sel_count}")
        profile_count = len(self.closed_profiles)
        p.setFont(QFont("Arial", 10))
        if profile_count > 0:
            p.setPen(QPen(QColor(100, 200, 100)))
            p.drawText(self.width()-180, 25, f"✓ {profile_count} geschlossene Profile")
        else:
            p.setPen(QPen(QColor(200, 150, 100)))
            p.drawText(self.width()-160, 25, "○ Kein geschlossenes Profil")
        
        # Constraint-Status anzeigen
        constraint_count = len(self.sketch.constraints)
        if constraint_count > 0:
            p.setFont(QFont("Arial", 9))
            p.setPen(QPen(QColor(150, 200, 150)))
            p.drawText(self.width()-180, 42, f"⚙ {constraint_count} Constraints")
        
        y = 58
        p.setFont(QFont("Arial", 10))
        if self.construction_mode:
            p.setPen(QPen(self.GEO_CONSTRUCTION))
            p.drawText(self.width()-130, y, "KONSTRUKTION (X)")
            y += 18
        if not self.grid_snap:
            p.setPen(QPen(QColor(180, 100, 100)))
            p.drawText(self.width()-100, y, "Grid: AUS (G)")

        # HUD-Nachricht zeichnen (zentraler Toast)
        self._draw_hud_message(p)

    def _draw_hud_message(self, p):
        """Zeichnet die zentrale HUD-Nachricht (Toast-Style)"""
        import time
        if not hasattr(self, '_hud_message') or not self._hud_message:
            return

        # Prüfe ob Nachricht noch gültig
        elapsed = (time.time() * 1000) - self._hud_message_time
        if elapsed > self._hud_duration:
            self._hud_message = ""
            return

        # Fade-out Effekt
        alpha = 255
        if elapsed > self._hud_duration - 500:
            alpha = int(255 * (self._hud_duration - elapsed) / 500)

        # Box-Größe berechnen
        p.setFont(QFont("Arial", 14, QFont.Bold))
        fm = p.fontMetrics()
        text_rect = fm.boundingRect(self._hud_message)
        box_w = text_rect.width() + 40
        box_h = text_rect.height() + 20

        # Zentriert oben
        x = (self.width() - box_w) // 2
        y = 60

        # Hintergrund
        bg_color = QColor(30, 30, 35, min(220, alpha))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(bg_color))
        p.drawRoundedRect(x, y, box_w, box_h, 8, 8)

        # Border
        border_color = QColor(self._hud_color)
        border_color.setAlpha(alpha)
        p.setPen(QPen(border_color, 2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(x, y, box_w, box_h, 8, 8)

        # Text
        text_color = QColor(self._hud_color)
        text_color.setAlpha(alpha)
        p.setPen(text_color)
        p.drawText(x + 20, y + box_h - 10, self._hud_message)
    
