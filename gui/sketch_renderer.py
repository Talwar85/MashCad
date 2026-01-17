"""
MashCad - Sketch Renderer Mixin
All _draw_* methods for sketch visualization
Extracted from sketch_editor.py for better maintainability
"""

import math
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
  


class SketchRendererMixin:
    """Mixin containing all drawing methods for SketchEditor"""
    
    def _draw_grid(self, p):
        tl = self.screen_to_world(QPointF(0, 0))
        br = self.screen_to_world(QPointF(self.width(), self.height()))
        step = self.grid_size
        while step * self.view_scale < 15: step *= 2
        while step * self.view_scale > 80: step /= 2
        p.setPen(QPen(self.GRID_MINOR, 1))
        x = math.floor(tl.x() / step) * step
        while x < br.x():
            sx = self.world_to_screen(QPointF(x, 0)).x()
            p.drawLine(int(sx), 0, int(sx), self.height())
            x += step
        y = math.floor(br.y() / step) * step
        while y < tl.y():
            sy = self.world_to_screen(QPointF(0, y)).y()
            p.drawLine(0, int(sy), self.width(), int(sy))
            y += step
        p.setPen(QPen(self.GRID_MAJOR, 1))
        major_step = step * 5
        x = math.floor(tl.x() / major_step) * major_step
        while x < br.x():
            sx = self.world_to_screen(QPointF(x, 0)).x()
            p.drawLine(int(sx), 0, int(sx), self.height())
            x += major_step
        y = math.floor(br.y() / major_step) * major_step
        while y < tl.y():
            sy = self.world_to_screen(QPointF(0, y)).y()
            p.drawLine(0, int(sy), self.width(), int(sy))
            y += major_step
    
    def _draw_profiles(self, p):
        """Zeichnet alle erkannten Faces - Shapely hat Löcher bereits integriert"""
        from PySide6.QtGui import QPainterPath
        
        def profile_to_path(profile_data, scale, offset_func):
            """Konvertiert ein Profil in einen QPainterPath"""
            path = QPainterPath()
            profile_type, data = profile_data
            
            if profile_type == 'circle':
                circle = data
                center = offset_func(QPointF(circle.center.x, circle.center.y))
                radius = circle.radius * scale
                path.addEllipse(center, radius, radius)
                
            elif profile_type == 'lines':
                lines = data
                if len(lines) >= 3:
                    points = []
                    for line in lines:
                        points.append(offset_func(QPointF(line.start.x, line.start.y)))
                    if points:
                        path.moveTo(points[0])
                        for pt in points[1:]:
                            path.lineTo(pt)
                        path.closeSubpath()
            
            elif profile_type == 'polygon':
                # Shapely Polygon zu QPainterPath
                # Exterior (äußerer Rand)
                coords = list(data.exterior.coords)
                if len(coords) >= 3:
                    screen_pts = [offset_func(QPointF(c[0], c[1])) for c in coords]
                    path.moveTo(screen_pts[0])
                    for pt in screen_pts[1:]:
                        path.lineTo(pt)
                    path.closeSubpath()
                
                # Interiors (Löcher) - Shapely hat diese bereits erkannt!
                for interior in data.interiors:
                    hole_coords = list(interior.coords)
                    if len(hole_coords) >= 3:
                        hole_pts = [offset_func(QPointF(c[0], c[1])) for c in hole_coords]
                        path.moveTo(hole_pts[0])
                        for pt in hole_pts[1:]:
                            path.lineTo(pt)
                        path.closeSubpath()
            
            return path
        
        # Sicherheitscheck
        if not self.closed_profiles:
            return
        
        # EINFACH: Alle Profile zeichnen mit OddEvenFill
        # Shapely hat die Löcher bereits in den Polygonen integriert!
        for profile_data in self.closed_profiles:
            if not profile_data:
                continue
            
            path = profile_to_path(profile_data, self.view_scale, self.world_to_screen)
            path.setFillRule(Qt.OddEvenFill)  # Löcher werden automatisch leer
            
            # Prüfe ob dieses Profil gehovert ist
            is_hovered = (profile_data == self.hovered_face)
            
            p.setPen(Qt.NoPen)
            if is_hovered:
                p.setBrush(QBrush(self.PROFILE_HOVER))
            else:
                p.setBrush(QBrush(self.PROFILE_CLOSED))
            
            p.drawPath(path)
        
        # Offset-Preview zeichnen
        if self.offset_preview_lines:
            p.setPen(QPen(QColor(0, 200, 100), 2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            for line_data in self.offset_preview_lines:
                x1, y1, x2, y2 = line_data
                p1 = self.world_to_screen(QPointF(x1, y1))
                p2 = self.world_to_screen(QPointF(x2, y2))
                p.drawLine(p1, p2)
    
    def _draw_axes(self, p):
        o = self.world_to_screen(QPointF(0, 0))
        
        # Achsen
        p.setPen(QPen(self.AXIS_X, 2))
        p.drawLine(int(o.x()), int(o.y()), self.width(), int(o.y()))
        p.setPen(QPen(self.AXIS_Y, 2))
        p.drawLine(int(o.x()), int(o.y()), int(o.x()), 0)
        
        # Origin-Punkt - deutlich sichtbar!
        p.setPen(QPen(QColor(255, 200, 0), 2))  # Gelb/Orange
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(o, 8, 8)  # Größerer Kreis
        
        # Kreuz im Origin
        p.setPen(QPen(QColor(255, 200, 0), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(o, 5, 5)
    
    def _draw_geometry(self, p):
        # 1. Glow-Effekt für Auswahl
        if self.selected_lines or self.selected_circles or self.selected_arcs or self.selected_spline:
            glow_pen = QPen(QColor(0, 180, 255, 100), 8)
            p.setPen(glow_pen)
            p.setBrush(Qt.NoBrush)
            
            for line in self.selected_lines:
                # FIX: Hier stand vorher Point2D -> muss QPointF sein
                p.drawLine(self.world_to_screen(QPointF(line.start.x, line.start.y)), 
                          self.world_to_screen(QPointF(line.end.x, line.end.y)))
            for arc in self.selected_arcs:
                ctr = self.world_to_screen(QPointF(arc.center.x, arc.center.y))
                r = arc.radius * self.view_scale
                start_deg = int(arc.start_angle * 16)
                sweep = arc.end_angle - arc.start_angle
                if sweep <= 0: sweep += 360 
                sweep_deg = int(sweep * 16)
                p.drawArc(QRectF(ctr.x()-r, ctr.y()-r, 2*r, 2*r), -start_deg, -sweep_deg)

        # 2. Linien zeichnen
        for line in self.sketch.lines:
            # Spline-Linien überspringen, wenn wir sie gerade bearbeiten
            if self.spline_drag_spline and line in getattr(self.spline_drag_spline, '_lines', []):
                continue

            sel = line in self.selected_lines
            hov = self.hovered_entity == line
            col = self.GEO_CONSTRUCTION if line.construction else (QColor(50, 200, 255) if sel else (self.GEO_HOVER if hov else self.GEO_COLOR))
            w = 3.0 if sel else (2.5 if hov else 1.5)
            style = Qt.DashLine if line.construction else Qt.SolidLine
            
            p.setPen(QPen(col, w, style))
            p1 = self.world_to_screen(QPointF(line.start.x, line.start.y))
            p2 = self.world_to_screen(QPointF(line.end.x, line.end.y))
            p.drawLine(p1, p2)
            
            # Endpunkte
            p.setBrush(QBrush(self.BG_COLOR))
            p.setPen(QPen(col, 1))
            p.drawEllipse(p1, 2, 2)
            p.drawEllipse(p2, 2, 2)

        # 3. Kreise zeichnen
        for c in self.sketch.circles:
            sel = c in self.selected_circles
            hov = self.hovered_entity == c
            col = self.GEO_CONSTRUCTION if c.construction else (QColor(50, 200, 255) if sel else (self.GEO_HOVER if hov else self.GEO_COLOR))
            w = 3.0 if sel else (2.5 if hov else 1.5)
            style = Qt.DashLine if c.construction else Qt.SolidLine
            
            p.setPen(QPen(col, w, style))
            p.setBrush(Qt.NoBrush)
            ctr = self.world_to_screen(QPointF(c.center.x, c.center.y))
            r = c.radius * self.view_scale
            p.drawEllipse(ctr, r, r)

        # 4. Arcs (Bögen) zeichnen
        for arc in self.sketch.arcs:
            sel = arc in self.selected_arcs
            hov = self.hovered_entity == arc
            col = self.GEO_CONSTRUCTION if arc.construction else (QColor(50, 200, 255) if sel else (self.GEO_HOVER if hov else self.GEO_COLOR))
            w = 3.0 if sel else (2.5 if hov else 1.5)
            style = Qt.DashLine if arc.construction else Qt.SolidLine
            
            p.setPen(QPen(col, w, style))
            p.setBrush(Qt.NoBrush)
            
            ctr = self.world_to_screen(QPointF(arc.center.x, arc.center.y))
            r = arc.radius * self.view_scale
            rect = QRectF(ctr.x()-r, ctr.y()-r, 2*r, 2*r)
            
            start_angle = arc.start_angle
            end_angle = arc.end_angle
            sweep = end_angle - start_angle
            if sweep <= 0: sweep += 360
            
            p.drawArc(rect, int(-start_angle * 16), int(-sweep * 16))
            
            # Endpunkte zeichnen
            sx = arc.center.x + arc.radius * math.cos(math.radians(start_angle))
            sy = arc.center.y + arc.radius * math.sin(math.radians(start_angle))
            ex = arc.center.x + arc.radius * math.cos(math.radians(end_angle))
            ey = arc.center.y + arc.radius * math.sin(math.radians(end_angle))
            
            p.setBrush(QBrush(self.BG_COLOR))
            p.setPen(QPen(col, 1))
            p.drawEllipse(self.world_to_screen(QPointF(sx, sy)), 3, 3)
            p.drawEllipse(self.world_to_screen(QPointF(ex, ey)), 3, 3)

        # 5. Spline
        for spline in self.sketch.splines:
            is_selected = spline == self.selected_spline
            is_dragging = (spline == self.spline_drag_spline)
            
            col = self.GEO_CONSTRUCTION if spline.construction else self.GEO_COLOR
            if is_selected: col = QColor(50, 200, 255)
            
            lines_to_draw = []
            if is_dragging and hasattr(spline, '_preview_lines'):
                lines_to_draw = spline._preview_lines
            elif hasattr(spline, 'to_lines'):
                lines_to_draw = spline.to_lines(segments_per_span=10)
            
            path = QPainterPath()
            if lines_to_draw:
                path.moveTo(self.world_to_screen(QPointF(lines_to_draw[0].start.x, lines_to_draw[0].start.y)))
                for l in lines_to_draw:
                    path.lineTo(self.world_to_screen(QPointF(l.end.x, l.end.y)))
            
            p.setPen(QPen(col, 2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
            
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
    
    def _draw_constraints(self, p):
        """Zeichnet Constraint-Icons an den betroffenen Elementen (Fusion360-Style)"""
        p.setFont(QFont("Arial", 9, QFont.Bold))
        
        # Sammle Constraints pro Linie für Offset
        line_constraint_count = {}
        
        for c in self.sketch.constraints:
            try:
                if c.type == ConstraintType.HORIZONTAL and c.entities:
                    line = c.entities[0]
                    mid = self.world_to_screen(QPointF(line.midpoint.x, line.midpoint.y))
                    offset = line_constraint_count.get(line.id, 0) * 15
                    line_constraint_count[line.id] = line_constraint_count.get(line.id, 0) + 1
                    # Hintergrund-Box für bessere Lesbarkeit
                    p.setPen(Qt.NoPen)
                    p.setBrush(QBrush(QColor(30, 30, 30, 180)))
                    p.drawRoundedRect(int(mid.x())-10, int(mid.y())-18-offset, 20, 14, 3, 3)
                    p.setPen(QPen(self.CONSTRAINT_COLOR))
                    p.drawText(int(mid.x())-5, int(mid.y())-7-offset, "H")
                    
                elif c.type == ConstraintType.VERTICAL and c.entities:
                    line = c.entities[0]
                    mid = self.world_to_screen(QPointF(line.midpoint.x, line.midpoint.y))
                    offset = line_constraint_count.get(line.id, 0) * 15
                    line_constraint_count[line.id] = line_constraint_count.get(line.id, 0) + 1
                    p.setPen(Qt.NoPen)
                    p.setBrush(QBrush(QColor(30, 30, 30, 180)))
                    p.drawRoundedRect(int(mid.x())+5, int(mid.y())-5-offset, 20, 14, 3, 3)
                    p.setPen(QPen(self.CONSTRAINT_COLOR))
                    p.drawText(int(mid.x())+10, int(mid.y())+6-offset, "V")
                    
                elif c.type == ConstraintType.PARALLEL and len(c.entities) >= 2:
                    # Symbol an beiden Linien
                    for line in c.entities[:2]:
                        mid = self.world_to_screen(QPointF(line.midpoint.x, line.midpoint.y))
                        offset = line_constraint_count.get(line.id, 0) * 15
                        line_constraint_count[line.id] = line_constraint_count.get(line.id, 0) + 1
                        p.setPen(Qt.NoPen)
                        p.setBrush(QBrush(QColor(30, 30, 30, 180)))
                        p.drawRoundedRect(int(mid.x())-10, int(mid.y())-18-offset, 20, 14, 3, 3)
                        p.setPen(QPen(QColor(100, 180, 255)))
                        p.drawText(int(mid.x())-5, int(mid.y())-7-offset, "∥")
                        
                elif c.type == ConstraintType.PERPENDICULAR and len(c.entities) >= 2:
                    for line in c.entities[:2]:
                        mid = self.world_to_screen(QPointF(line.midpoint.x, line.midpoint.y))
                        offset = line_constraint_count.get(line.id, 0) * 15
                        line_constraint_count[line.id] = line_constraint_count.get(line.id, 0) + 1
                        p.setPen(Qt.NoPen)
                        p.setBrush(QBrush(QColor(30, 30, 30, 180)))
                        p.drawRoundedRect(int(mid.x())-10, int(mid.y())-18-offset, 20, 14, 3, 3)
                        p.setPen(QPen(QColor(255, 180, 100)))
                        p.drawText(int(mid.x())-5, int(mid.y())-7-offset, "⊥")
                        
                elif c.type == ConstraintType.EQUAL_LENGTH and len(c.entities) >= 2:
                    for line in c.entities[:2]:
                        mid = self.world_to_screen(QPointF(line.midpoint.x, line.midpoint.y))
                        offset = line_constraint_count.get(line.id, 0) * 15
                        line_constraint_count[line.id] = line_constraint_count.get(line.id, 0) + 1
                        p.setPen(Qt.NoPen)
                        p.setBrush(QBrush(QColor(30, 30, 30, 180)))
                        p.drawRoundedRect(int(mid.x())-10, int(mid.y())-18-offset, 20, 14, 3, 3)
                        p.setPen(QPen(QColor(200, 100, 255)))
                        p.drawText(int(mid.x())-4, int(mid.y())-7-offset, "=")
                        
                elif c.type == ConstraintType.LENGTH and c.value and c.entities:
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

                    text = f"{c.value:.1f}"
                    
                    # Box zeichnen
                    fm = QFontMetrics(p.font())
                    rect = fm.boundingRect(text)
                    box_w = rect.width() + 10
                    box_h = rect.height() + 4
                    
                    p.setPen(Qt.NoPen)
                    p.setBrush(QBrush(QColor(30, 30, 30, 200)))
                    # Zentrierte Box am neuen Ort
                    p.drawRoundedRect(int(text_pos.x() - box_w/2), int(text_pos.y() - box_h/2), 
                                      box_w, box_h, 3, 3)
                    
                    p.setPen(QPen(self.DIM_COLOR))
                    # Text zentrieren
                    p.drawText(int(text_pos.x() - rect.width()/2), 
                               int(text_pos.y() + rect.height()/2 - 3), text)
                    
                elif c.type == ConstraintType.RADIUS and c.value and c.entities:
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
                    offset = 40 # Länge der Linie nach außen
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
                    text = f"R{c.value:.1f}"
                    fm = QFontMetrics(p.font())
                    rect = fm.boundingRect(text)
                    
                    # Hintergrund für Text
                    p.setPen(Qt.NoPen)
                    p.setBrush(QBrush(QColor(30, 30, 30, 200)))
                    p.drawRoundedRect(int(p_text.x() - rect.width()/2 - 4), 
                                      int(p_text.y() - rect.height()/2 - 2), 
                                      rect.width()+8, rect.height()+4, 3, 3)
                    
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
            
        elif self.current_tool == SketchTool.SLOT:
            if self.tool_step == 1:
                # Schritt 1: Linie zeigen
                p.drawLine(self.world_to_screen(self.tool_points[0]), self.world_to_screen(snap))
            elif self.tool_step == 2:
                # Schritt 2: Langloch mit abgerundeten Enden
                p1, p2 = self.tool_points[0], self.tool_points[1]
                dx, dy = p2.x()-p1.x(), p2.y()-p1.y()
                length = math.hypot(dx, dy)
                if length > 0.01:
                    nx, ny = -dy/length, dx/length
                    width = abs((snap.x()-p1.x())*nx + (snap.y()-p1.y())*ny) * 2
                    hw = width/2
                    
                    # Langloch-Form mit Halbkreisen an den Enden
                    from PySide6.QtGui import QPainterPath
                    path = QPainterPath()
                    
                    # Start-Halbkreis (um p1)
                    p1_screen = self.world_to_screen(p1)
                    p2_screen = self.world_to_screen(p2)
                    hw_screen = hw * self.view_scale
                    
                    # Winkel der Mittellinie
                    angle = math.degrees(math.atan2(dy, dx))
                    
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
                    path.arcTo(rect2, angle + 90, -180)
                    path.lineTo(bot1)
                    # Halbkreis um p1
                    rect1 = QRectF(p1_screen.x()-hw_screen, p1_screen.y()-hw_screen, hw_screen*2, hw_screen*2)
                    path.arcTo(rect1, angle - 90, -180)
                    path.closeSubpath()
                    
                    p.drawPath(path)
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
            
            if total_dist > 0.01:
                count = self.tool_data.get('pattern_count', 3)
                spacing = self.tool_data.get('pattern_spacing', total_dist / max(1, count - 1))
                ux, uy = dx / total_dist, dy / total_dist
                
                p.setPen(QPen(QColor(100, 200, 255), 2, Qt.DashLine))
                
                # Zeichne Preview für jede Kopie
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
                
                # Richtungspfeil und Info
                p.setPen(QPen(QColor(255, 200, 0), 2))
                p.drawLine(self.world_to_screen(start), self.world_to_screen(snap))
                p.setFont(QFont("Arial", 10, QFont.Bold))
                mid = self.world_to_screen(QPointF((start.x() + snap.x())/2, (start.y() + snap.y())/2))
                p.drawText(int(mid.x()) + 10, int(mid.y()) - 10, f"{count}× @ {spacing:.1f}mm")
        
        # PATTERN CIRCULAR Preview
        elif self.current_tool == SketchTool.PATTERN_CIRCULAR and self.tool_step == 1:
            center = self.tool_points[0]
            count = self.tool_data.get('pattern_count', 6)
            total_angle = self.tool_data.get('pattern_angle', 360.0)
            angle_step = math.radians(total_angle / count)
            
            p.setPen(QPen(QColor(255, 150, 100), 2, Qt.DashLine))
            
            # Zeichne Preview für jede Kopie
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
            
            # Zentrum und Info
            p.setPen(QPen(QColor(255, 200, 0), 2))
            ctr_screen = self.world_to_screen(center)
            p.drawEllipse(ctr_screen, 8, 8)
            p.drawLine(int(ctr_screen.x())-12, int(ctr_screen.y()), int(ctr_screen.x())+12, int(ctr_screen.y()))
            p.drawLine(int(ctr_screen.x()), int(ctr_screen.y())-12, int(ctr_screen.x()), int(ctr_screen.y())+12)
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
    
