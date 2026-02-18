"""
MashCad - Sketch Renderer Mixin
All _draw_* methods for sketch visualization
Extracted from sketch_editor.py for better maintainability
"""

import math
import time
from loguru import logger
from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPainterPath, QFont, QPolygonF, QFontMetrics
from i18n import tr

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
        """Zeichnet Canvas-Bildreferenz als Hintergrund (CAD-Style)."""
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

        # Alle 4 Ecken in Welt-Koordinaten (wichtig bei Rotation!)
        corners = [
            self.screen_to_world(QPointF(0, 0)),
            self.screen_to_world(QPointF(self.width(), 0)),
            self.screen_to_world(QPointF(0, self.height())),
            self.screen_to_world(QPointF(self.width(), self.height()))
        ]

        # Min/Max über alle Ecken (funktioniert bei jeder Rotation)
        start_x = min(c.x() for c in corners)
        end_x = max(c.x() for c in corners)
        start_y = min(c.y() for c in corners)
        end_y = max(c.y() for c in corners)

        step = self.grid_size
        while step * self.view_scale < 15: step *= 2
        while step * self.view_scale > 80: step /= 2
        
        # Minor Grid - bei Rotation müssen Linien als 2 Endpunkte gezeichnet werden
        p.setPen(DesignTokens.pen_grid_minor())

        # Vertikale Linien (x = const, von start_y bis end_y)
        x = math.floor(start_x / step) * step
        while x < end_x + step:
            p1 = self.world_to_screen(QPointF(x, start_y))
            p2 = self.world_to_screen(QPointF(x, end_y))
            p.drawLine(p1.toPoint(), p2.toPoint())
            x += step

        # Horizontale Linien (y = const, von start_x bis end_x)
        y = math.floor(start_y / step) * step
        while y < end_y + step:
            p1 = self.world_to_screen(QPointF(start_x, y))
            p2 = self.world_to_screen(QPointF(end_x, y))
            p.drawLine(p1.toPoint(), p2.toPoint())
            y += step

        # Major Grid
        p.setPen(QPen(DesignTokens.COLOR_GRID_MAJOR, 1))
        major_step = step * 5
        x = math.floor(start_x / major_step) * major_step
        while x < end_x + major_step:
            p1 = self.world_to_screen(QPointF(x, start_y))
            p2 = self.world_to_screen(QPointF(x, end_y))
            p.drawLine(p1.toPoint(), p2.toPoint())
            x += major_step
        y = math.floor(start_y / major_step) * major_step
        while y < end_y + major_step:
            p1 = self.world_to_screen(QPointF(start_x, y))
            p2 = self.world_to_screen(QPointF(end_x, y))
            p.drawLine(p1.toPoint(), p2.toPoint())
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
        """Zeichnet Koordinatenachsen (rotieren mit der Ansicht)."""
        o = self.world_to_screen(QPointF(0, 0))

        # Achsenlänge in Weltkoordinaten (groß genug um Bildschirm zu füllen)
        axis_length = 10000

        # X-Achse: Von Origin nach rechts in Welt-Koordinaten
        x_end = self.world_to_screen(QPointF(axis_length, 0))
        p.setPen(QPen(DesignTokens.COLOR_AXIS_X, 2))
        p.drawLine(o.toPoint(), x_end.toPoint())

        # Y-Achse: Von Origin nach oben in Welt-Koordinaten
        y_end = self.world_to_screen(QPointF(0, axis_length))
        p.setPen(QPen(DesignTokens.COLOR_AXIS_Y, 2))
        p.drawLine(o.toPoint(), y_end.toPoint())

        # Origin schön modern: Weißer Punkt mit dunklem Rand
        p.setPen(QPen(DesignTokens.COLOR_BG_CANVAS, 2))
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.drawEllipse(o, 4, 4)

    def _draw_orientation_indicator(self, p):
        """
        Zeichnet Orientierungs-Hilfe für 2D↔3D Mapping (Feature Flag: sketch_orientation_indicator)

        Zeigt:
        1. Projizierter Welt-Origin (gestricheltes Kreuz) - wo ist (0,0,0) relativ zum Sketch?
        2. 3D-Achsen-Indikator (Ecke rechts oben) - welche 3D-Richtung = welche Sketch-Richtung?
        3. Labels für das Achsen-Mapping
        """
        from config.feature_flags import is_enabled
        if not is_enabled("sketch_orientation_indicator"):
            return

        from loguru import logger

        # Hole Orientierungs-Daten
        proj_origin = getattr(self, 'projected_world_origin', (0, 0))
        x_dir = getattr(self, 'sketch_plane_x_dir', (1, 0, 0))
        y_dir = getattr(self, 'sketch_plane_y_dir', (0, 1, 0))

        # === 1. PROJIZIERTER WELT-ORIGIN ===
        # Zeichne gestricheltes Kreuz an der Position wo Welt-(0,0,0) auf diese Ebene projiziert wird
        if proj_origin != (0, 0):  # Nur zeichnen wenn nicht am Sketch-Origin
            wo_screen = self.world_to_screen(QPointF(proj_origin[0], proj_origin[1]))

            # Gestrichelter Pen
            pen = QPen(QColor(255, 200, 100, 180), 1, Qt.DashLine)
            p.setPen(pen)

            cross_size = 15
            p.drawLine(int(wo_screen.x() - cross_size), int(wo_screen.y()),
                       int(wo_screen.x() + cross_size), int(wo_screen.y()))
            p.drawLine(int(wo_screen.x()), int(wo_screen.y() - cross_size),
                       int(wo_screen.x()), int(wo_screen.y() + cross_size))

            # Label "World (0,0,0)"
            p.setFont(QFont("Segoe UI", 8))
            p.setPen(QColor(255, 200, 100, 200))
            p.drawText(int(wo_screen.x() + 10), int(wo_screen.y() - 5), "World Origin")

        # === 2. 3D-ORIENTIERUNGS-INDIKATOR (Ecke rechts oben) ===
        # Zeigt welche Ebene der Sketch ist und Blickrichtung relativ zur 3D-Kamera
        indicator_x = self.width() - 115
        indicator_y = 75

        # Hole auch die Normale für Ebenen-Bestimmung
        normal = getattr(self, 'sketch_plane_normal', (0, 0, 1))

        # Bestimme welche Standard-Ebene das ist und Blickrichtung
        def get_plane_info(normal):
            """Bestimmt Ebenen-Name und Blickrichtung."""
            nx, ny, nz = normal
            anx, any, anz = abs(nx), abs(ny), abs(nz)

            # Welche Achse zeigt die Normale?
            if anz > 0.9:  # Normale zeigt in Z → XY-Ebene
                view_dir = "von oben" if nz > 0 else "von unten"
                return "XY-Ebene", view_dir, "Z"
            elif any > 0.9:  # Normale zeigt in Y → XZ-Ebene
                view_dir = "von vorne" if ny > 0 else "von hinten"
                return "XZ-Ebene", view_dir, "Y"
            elif anx > 0.9:  # Normale zeigt in X → YZ-Ebene
                view_dir = "von rechts" if nx > 0 else "von links"
                return "YZ-Ebene", view_dir, "X"
            else:
                return "Schräge Ebene", "", ""

        plane_name, view_hint, _ = get_plane_info(normal)

        # Hintergrund-Box
        p.setPen(QPen(QColor(80, 80, 90), 1))
        p.setBrush(QColor(30, 30, 35, 240))
        p.drawRoundedRect(indicator_x - 65, indicator_y - 55, 155, 90, 8, 8)

        # Zeile 1: Ebenen-Name groß
        p.setFont(QFont("Segoe UI", 11, QFont.Bold))
        p.setPen(QColor(100, 170, 255))  # Blau
        p.drawText(indicator_x - 60, indicator_y - 38, plane_name)

        # Zeile 2: Blickrichtung
        if view_hint:
            p.setFont(QFont("Segoe UI", 9))
            p.setPen(QColor(255, 200, 100))  # Orange für Blickrichtung
            p.drawText(indicator_x - 60, indicator_y - 20, f"Blick {view_hint}")

        # Trennlinie
        p.setPen(QPen(QColor(70, 70, 80), 1))
        p.drawLine(indicator_x - 60, indicator_y - 10, indicator_x + 85, indicator_y - 10)

        # Achsen-Mapping kompakt
        def get_axis_label(direction):
            """Gibt Label für dominante Achsenrichtung zurück."""
            x, y, z = direction
            ax, ay, az = abs(x), abs(y), abs(z)
            if ax > ay and ax > az:
                return "X" if x > 0 else "-X"
            elif ay > ax and ay > az:
                return "Y" if y > 0 else "-Y"
            else:
                return "Z" if z > 0 else "-Z"

        x_world = get_axis_label(x_dir)
        y_world = get_axis_label(y_dir)

        # Zeile 3+4: Achsen-Mapping
        p.setFont(QFont("Segoe UI", 9))

        # Rechts im Sketch = welche Welt-Achse
        p.setPen(DesignTokens.COLOR_AXIS_X)
        p.drawText(indicator_x - 60, indicator_y + 8, f"Sketch rechts → Welt {x_world}")

        # Oben im Sketch = welche Welt-Achse
        p.setPen(DesignTokens.COLOR_AXIS_Y)
        p.drawText(indicator_x - 60, indicator_y + 25, f"Sketch oben  → Welt {y_world}")

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
            if not l.construction and not bool(getattr(l, "_suppress_endpoint_markers", False)):
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
                if not line.construction and not bool(getattr(line, "_suppress_endpoint_markers", False)):
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
        path_constraint_highlight = QPainterPath()  # Für 2-Entity Constraint Auswahl

        # Constraint Highlight Entity (falls aktiv)
        highlight_entity = getattr(self, '_constraint_highlighted_entity', None)

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
            is_constraint_highlight = (highlight_entity is not None and line is highlight_entity)

            if is_constraint_highlight:
                path_constraint_highlight.moveTo(p1)
                path_constraint_highlight.lineTo(p2)
            elif is_sel:
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

            if bool(getattr(line, "_suppress_endpoint_markers", False)):
                continue

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
            is_constraint_highlight = (highlight_entity is not None and c is highlight_entity)

            if is_constraint_highlight:
                path_constraint_highlight.addEllipse(ctr, r, r)
            elif is_sel:
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
            is_constraint_highlight = (highlight_entity is not None and arc is highlight_entity)

            if is_constraint_highlight:
                path_constraint_highlight.addPath(temp_path)
            elif is_sel:
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

        # Constraint Highlight (Cyan, dick, für 2-Entity Constraint Auswahl)
        if not path_constraint_highlight.isEmpty():
            highlight_color = getattr(self, '_constraint_highlight_color', QColor(0, 255, 255))
            pen = QPen(highlight_color, 3.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path_constraint_highlight)
            # Glow-Effekt für bessere Sichtbarkeit
            glow_color = QColor(highlight_color)
            glow_color.setAlpha(80)
            p.setPen(QPen(glow_color, 8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(path_constraint_highlight)

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
            is_hov = self.hovered_entity == pt

            # Farbe basierend auf Zustand
            if is_sel:
                p.setPen(QPen(DesignTokens.COLOR_GEO_SELECTED, 2))
                p.setBrush(DesignTokens.COLOR_GEO_SELECTED)
                size = 5
            elif is_hov:
                p.setPen(QPen(DesignTokens.COLOR_GEO_HOVER, 2))
                p.setBrush(DesignTokens.COLOR_GEO_HOVER)
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
            
            # Zeichne Curvature Comb (falls aktiviert)
            if getattr(spline, 'show_curvature', False):
                self._draw_curvature_comb(p, spline)
            
            # Visibility Improvements (User Feedback)
            # 1. Show Points ALWAYS (but smaller/subtle if not selected)
            # 2. Show Handles only if selected or hovered
            is_hovered = (spline == self._last_hovered_entity)
            
            if is_selected or is_dragging or is_hovered:
                self._draw_spline_handles(p, spline, draw_handles=True)
            else:
                # Minimalistic view: just points, no handles
                self._draw_spline_handles(p, spline, draw_handles=False)
    
    def _draw_spline_handles(self, p, spline, draw_handles=True):
        handle_color = QColor(100, 200, 100)
        point_color = QColor(255, 255, 255)
        
        # Unselected: More subtle
        if not draw_handles:
            point_color = QColor(DesignTokens.COLOR_GEO_BODY) # Same as line
        
        for i, cp in enumerate(spline.control_points):
            pt_screen = self.world_to_screen(QPointF(cp.point.x, cp.point.y))
            
            # Punkt
            p.setPen(QPen(point_color, 2))
            p.setBrush(QBrush(self.BG_COLOR))
            # Smaller if unselected
            size = 4 if draw_handles else 3
            
            # === Phase 19: Weight Visualization ===
            # Visualize weight by scaling the point
            if hasattr(cp, 'weight'):
                 w_factor = math.sqrt(cp.weight)
                 # Clamp size factor
                 size *= max(0.5, min(4.0, w_factor))

            p.drawEllipse(pt_screen, size, size)
            
            # Handles only if requested
            if not draw_handles:
                continue
                
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

        def _entity_visible(entity):
            if hasattr(entity, 'start') and hasattr(entity, 'end'):  # Line
                p_mid = self.world_to_screen(entity.midpoint)
                return viewport_rect.contains(p_mid)

            if hasattr(entity, 'center'):  # Circle/Arc
                p_center = self.world_to_screen(entity.center)
                if viewport_rect.contains(p_center):
                    return True
                r_screen = getattr(entity, 'radius', 0) * self.view_scale
                bounds = QRectF(p_center.x() - r_screen, p_center.y() - r_screen, 2 * r_screen, 2 * r_screen)
                return viewport_rect.intersects(bounds)

            # Point2D / QPointF
            if hasattr(entity, 'x') and hasattr(entity, 'y'):
                p_pt = self.world_to_screen(entity)
                return viewport_rect.contains(p_pt)

            return False

        for c in self.sketch.constraints:
            if not c.entities:
                continue

            is_visible = any(_entity_visible(ent) for ent in c.entities)
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

                elif c.type == ConstraintType.TANGENT and len(c.entities) >= 2:
                    # TANGENT: Symbol am Berührpunkt zwischen Line und Circle/Arc
                    e1, e2 = c.entities[0], c.entities[1]

                    # Finde die Linie und den Kreis/Arc
                    line_entity = None
                    circle_entity = None
                    for e in [e1, e2]:
                        if hasattr(e, 'start') and hasattr(e, 'end'):  # Line
                            line_entity = e
                        elif hasattr(e, 'center') and hasattr(e, 'radius'):  # Circle/Arc
                            circle_entity = e

                    if line_entity and circle_entity:
                        # Berechne Tangent-Punkt (nächster Punkt auf Linie zum Kreismittelpunkt)
                        cx, cy = circle_entity.center.x, circle_entity.center.y
                        x1, y1 = line_entity.start.x, line_entity.start.y
                        x2, y2 = line_entity.end.x, line_entity.end.y
                        dx, dy = x2 - x1, y2 - y1
                        line_len_sq = dx*dx + dy*dy
                        if line_len_sq > 1e-10:
                            t = max(0, min(1, ((cx - x1)*dx + (cy - y1)*dy) / line_len_sq))
                            tangent_x = x1 + t * dx
                            tangent_y = y1 + t * dy
                        else:
                            tangent_x, tangent_y = x1, y1
                        mid = self.world_to_screen(QPointF(tangent_x, tangent_y))
                    elif circle_entity:
                        # Zwei Kreise: Symbol am Berührpunkt
                        mid = self.world_to_screen(circle_entity.center)
                    else:
                        continue

                    icon_rect = QRectF(int(mid.x())-10, int(mid.y())-18, 20, 14)
                    self.constraint_icon_rects.append((c, icon_rect))
                    is_selected = hasattr(self, 'selected_constraints') and c in self.selected_constraints
                    bg_color = QColor(0, 120, 212, 200) if is_selected else QColor(30, 30, 30, 180)
                    p.setPen(Qt.NoPen)
                    p.setBrush(QBrush(bg_color))
                    p.drawRoundedRect(icon_rect, 3, 3)
                    p.setPen(QPen(QColor(255, 200, 50)))  # Gold/Orange für Tangent
                    p.drawText(int(mid.x())-4, int(mid.y())-7, "T")

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
                    if c.value is None or c.value == 0:
                        logger.warning(f"[Constraints] RADIUS constraint has no value: {c}")
                    if not c.entities:
                        logger.warning(f"[Constraints] RADIUS constraint has no entities: {c}")

                    if c.entities:
                        circle = c.entities[0]
                        display_value = c.value if (c.value is not None and c.value != 0) else getattr(circle, 'radius', None)
                        if display_value is None:
                            continue
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
                            text = f"R {c.formula} = {display_value:.1f}"
                        else:
                            text = f"R{display_value:.1f}"
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

    def _calc_circle_3points(self, p1, p2, p3):
        """Berechnet Mittelpunkt und Radius eines Kreises durch 3 Punkte."""
        x1, y1 = p1.x(), p1.y()
        x2, y2 = p2.x(), p2.y()
        x3, y3 = p3.x(), p3.y()

        # Determinante für Kollinearitäts-Check
        d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
        if abs(d) < 1e-10:
            return None, 0  # Punkte sind kollinear

        # Mittelpunkt berechnen (Umkreisformel)
        ux = ((x1*x1 + y1*y1) * (y2 - y3) + (x2*x2 + y2*y2) * (y3 - y1) + (x3*x3 + y3*y3) * (y1 - y2)) / d
        uy = ((x1*x1 + y1*y1) * (x3 - x2) + (x2*x2 + y2*y2) * (x1 - x3) + (x3*x3 + y3*y3) * (x2 - x1)) / d

        # Radius berechnen
        r = math.hypot(x1 - ux, y1 - uy)

        return QPointF(ux, uy), r

    def _draw_preview(self, p):
        # Für Bearbeitungstools auch ohne tool_points zeichnen wenn tool_step > 0
        edit_tools = [SketchTool.MOVE, SketchTool.COPY, SketchTool.ROTATE, SketchTool.MIRROR, SketchTool.SCALE]
        has_preview_geometry = bool(getattr(self, "preview_geometry", None))
        if (
            not self.tool_points
            and self.tool_step == 0
            and self.current_tool not in edit_tools
            and not has_preview_geometry
        ):
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
                # 2-Punkt Modus: p1 und Cursor (snap) definieren den Durchmesser
                # Center = Mittelpunkt, Radius = halber Abstand
                p1 = self.tool_points[0]
                cx, cy = (p1.x() + snap.x()) / 2, (p1.y() + snap.y()) / 2
                r = math.hypot(snap.x() - p1.x(), snap.y() - p1.y()) / 2 * self.view_scale
                ctr = self.world_to_screen(QPointF(cx, cy))
                p.drawEllipse(ctr, r, r)
                # Durchmesser-Linie anzeigen
                p.drawLine(self.world_to_screen(p1), self.world_to_screen(snap))
            elif self.circle_mode == 2:
                # 3-Punkt Modus (wie CAD: nur Punkte markieren, Kreis erst ab 2 Punkten)
                if self.tool_step == 1:
                    # Ein Punkt gesetzt - nur Punkt markieren (keine Linie)
                    pt1 = self.tool_points[0]
                    p.setBrush(QBrush(QColor(0, 120, 215)))  # Blau gefüllt
                    p.drawEllipse(self.world_to_screen(pt1), 5, 5)
                    p.setBrush(Qt.NoBrush)
                elif self.tool_step == 2:
                    # Zwei Punkte gesetzt - Kreis-Preview durch alle 3 Punkte
                    pt1, pt2 = self.tool_points[0], self.tool_points[1]
                    pt3 = snap
                    center, radius = self._calc_circle_3points(pt1, pt2, pt3)
                    if center and radius > 0.01:
                        ctr = self.world_to_screen(center)
                        r = radius * self.view_scale
                        p.drawEllipse(ctr, r, r)
                    # Alle 3 Punkte markieren (gefüllt)
                    p.setBrush(QBrush(QColor(0, 120, 215)))
                    for pt in [pt1, pt2, pt3]:
                        p.drawEllipse(self.world_to_screen(pt), 5, 5)
                    p.setBrush(Qt.NoBrush)
            
        elif self.current_tool == SketchTool.ELLIPSE and self.tool_step >= 1:
            center = self.tool_points[0]

            if self.tool_step == 1:
                if use_dim_input and self.live_length > 0:
                    major_radius = self.live_length
                    angle_rad = math.radians(self.live_angle)
                    major_end = QPointF(
                        center.x() + major_radius * math.cos(angle_rad),
                        center.y() + major_radius * math.sin(angle_rad),
                    )
                else:
                    major_end = snap
                    major_radius = math.hypot(major_end.x() - center.x(), major_end.y() - center.y())

                if major_radius > 0.01:
                    dx = major_end.x() - center.x()
                    dy = major_end.y() - center.y()
                    ux = dx / major_radius
                    uy = dy / major_radius
                    p_major_1 = QPointF(center.x() - ux * major_radius, center.y() - uy * major_radius)
                    p_major_2 = QPointF(center.x() + ux * major_radius, center.y() + uy * major_radius)
                    p.drawLine(self.world_to_screen(p_major_1), self.world_to_screen(p_major_2))

            elif self.tool_step == 2:
                major_end = self.tool_points[1]
                dx = major_end.x() - center.x()
                dy = major_end.y() - center.y()
                major_radius = math.hypot(dx, dy)
                if major_radius > 0.01:
                    ux = dx / major_radius
                    uy = dy / major_radius
                    vx = -uy
                    vy = ux

                    if use_dim_input and self.live_radius > 0:
                        minor_radius = self.live_radius
                    else:
                        rel_x = snap.x() - center.x()
                        rel_y = snap.y() - center.y()
                        minor_radius = abs(rel_x * vx + rel_y * vy)
                    minor_radius = max(0.01, minor_radius)

                    p_major_1 = QPointF(center.x() - ux * major_radius, center.y() - uy * major_radius)
                    p_major_2 = QPointF(center.x() + ux * major_radius, center.y() + uy * major_radius)
                    p_minor_1 = QPointF(center.x() - vx * minor_radius, center.y() - vy * minor_radius)
                    p_minor_2 = QPointF(center.x() + vx * minor_radius, center.y() + vy * minor_radius)
                    p.drawLine(self.world_to_screen(p_major_1), self.world_to_screen(p_major_2))
                    p.drawLine(self.world_to_screen(p_minor_1), self.world_to_screen(p_minor_2))

                    path = QPainterPath()
                    n_pts = 64
                    for i in range(n_pts + 1):
                        t = (2.0 * math.pi * i) / float(n_pts)
                        lx = major_radius * math.cos(t)
                        ly = minor_radius * math.sin(t)
                        x = center.x() + lx * ux + ly * vx
                        y = center.y() + lx * uy + ly * vy
                        sp = self.world_to_screen(QPointF(x, y))
                        if i == 0:
                            path.moveTo(sp)
                        else:
                            path.lineTo(sp)
                    p.drawPath(path)

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
                    # QPainterPath ist bereits global importiert
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
            
            # CAD Style: Magenta/Lila Highlight für Projektion
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
                p.setBrush(QBrush(QColor(0, 120, 215)))
                p.drawEllipse(self.world_to_screen(pt), 4, 4)
                p.setBrush(Qt.NoBrush)
            
            if len(self.tool_points) >= 1:
                try:
                    # Zeichne Vorschau-Kurve durch alle Punkte + aktuellen Snap
                    from sketcher.geometry import BezierSpline
                    preview_spline = BezierSpline()
                    for pt in self.tool_points:
                        preview_spline.add_point(pt.x(), pt.y())
                    
                    # Aktueller Punkt (Snap)
                    preview_spline.add_point(snap.x(), snap.y())
                    
                    # Kurve zeichnen
                    pts = preview_spline.get_curve_points(segments_per_span=10)
                    if pts:
                        path = QPainterPath()
                        path.moveTo(self.world_to_screen(QPointF(pts[0][0], pts[0][1])))
                        for px, py in pts[1:]:
                            path.lineTo(self.world_to_screen(QPointF(px, py)))
                        
                        p.setPen(QPen(self.PREVIEW_COLOR, 2, Qt.SolidLine)) # Solid line for better visibility
                        p.drawPath(path)
                        
                        # Gummiband-Linie zum letzten Punkt (optional, aber hilfreich)
                        # p.setPen(QPen(self.PREVIEW_COLOR, 1, Qt.DashLine))
                        # p.drawLine(self.world_to_screen(self.tool_points[-1]), self.world_to_screen(snap))

                except Exception as e:
                    logger.debug(f"[sketch_renderer.py] Fehler Spline Preview: {e}")
        
        # === PREVIEW FÜR BEARBEITUNGSTOOLS ===
        
        # MOVE Preview
        elif self.current_tool == SketchTool.MOVE and self.tool_step == 1:
            # Bei aktiver Tab-Eingabe: Werte aus dim_input verwenden
            if self.dim_input_active and self.dim_input.isVisible():
                try:
                    vals = self.dim_input.get_values()
                    dx = vals.get("dx", 0)
                    dy = vals.get("dy", 0)
                except Exception as e:
                    logger.debug(f"[sketch_renderer.py] Fehler: {e}")
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
                except Exception as e:
                    logger.debug(f"[sketch_renderer.py] Fehler: {e}")
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
                except Exception as e:
                    logger.debug(f"[sketch_renderer.py] Fehler: {e}")
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
                except Exception as e:
                    logger.debug(f"[sketch_renderer.py] Fehler: {e}")
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

        # Geometrische Preview-Overlays (z.B. Trim)
        preview_items = getattr(self, "preview_geometry", []) or []
        if preview_items:
            p.save()
            p.setPen(QPen(QColor(255, 170, 80, 220), 2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            for item in preview_items:
                if hasattr(item, "start") and hasattr(item, "end"):
                    p.drawLine(
                        self.world_to_screen(QPointF(item.start.x, item.start.y)),
                        self.world_to_screen(QPointF(item.end.x, item.end.y)),
                    )
                    continue

                if hasattr(item, "center") and hasattr(item, "radius") and hasattr(item, "start_angle") and hasattr(item, "end_angle"):
                    r_world = float(item.radius)
                    if r_world <= 0.0:
                        continue

                    sweep = float(item.end_angle) - float(item.start_angle)
                    while sweep < 0.0:
                        sweep += 360.0
                    while sweep > 360.0:
                        sweep -= 360.0
                    if sweep < 0.1:
                        continue

                    steps = max(16, int(sweep / 3.0))
                    path = QPainterPath()
                    for idx in range(steps + 1):
                        t = idx / steps
                        ang = math.radians(float(item.start_angle) + sweep * t)
                        world_pt = QPointF(
                            item.center.x + r_world * math.cos(ang),
                            item.center.y + r_world * math.sin(ang),
                        )
                        screen_pt = self.world_to_screen(world_pt)
                        if idx == 0:
                            path.moveTo(screen_pt)
                        else:
                            path.lineTo(screen_pt)
                    p.drawPath(path)
                    continue

                if hasattr(item, "center") and hasattr(item, "radius"):
                    ctr = self.world_to_screen(QPointF(item.center.x, item.center.y))
                    r = float(item.radius) * self.view_scale
                    if r > 0.0:
                        p.drawEllipse(ctr, r, r)
            p.restore()
    
    def _draw_selection_box(self, p):
        if self.selection_box_start and self.selection_box_end:
            rect = QRectF(self.selection_box_start, self.selection_box_end).normalized()
            p.setPen(QPen(self.GEO_SELECTED, 1, Qt.DashLine))
            p.setBrush(QBrush(QColor(0, 150, 255, 30)))
            p.drawRect(rect)

    def _draw_direct_edit_handles(self, p):
        """
        Zeichnet direkte Manipulations-Handles für Circle/Polygon:
        - Center-Handle (verschieben)
        - Radius-Handle (Größe ändern)
        """
        if getattr(self, "current_tool", None) != SketchTool.SELECT:
            return
        if not hasattr(self, "_get_direct_edit_handles_world"):
            return

        handles = self._get_direct_edit_handles_world()
        if not handles:
            return

        center_world = handles["center"]
        radius_world = handles["radius_point"]
        source = handles.get("source", "circle")

        center_screen = self.world_to_screen(center_world)
        radius_screen = self.world_to_screen(radius_world)

        hover = getattr(self, "_direct_hover_handle", None)
        hover_mode = hover.get("mode") if hover else None
        drag_mode = getattr(self, "_direct_edit_mode", None) if getattr(self, "_direct_edit_dragging", False) else None

        is_center_active = hover_mode == "center" or drag_mode == "center"
        is_radius_active = hover_mode == "radius" or drag_mode == "radius"

        # Helper-Linie vom Zentrum zur Radius-Handle
        guide_color = QColor(120, 220, 255, 170) if source == "circle" else QColor(255, 190, 110, 170)
        p.setPen(QPen(guide_color, 1.5, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawLine(center_screen, radius_screen)

        # Center-Handle
        center_fill = QColor(30, 180, 255, 240) if is_center_active else QColor(20, 120, 200, 210)
        center_stroke = QColor(255, 255, 255, 230)
        center_size = 7 if is_center_active else 6

        p.setPen(QPen(center_stroke, 1.5))
        p.setBrush(QBrush(center_fill))
        p.drawEllipse(center_screen, center_size, center_size)
        p.setPen(QPen(QColor(255, 255, 255, 230), 1))
        p.drawLine(
            QPointF(center_screen.x() - 4, center_screen.y()),
            QPointF(center_screen.x() + 4, center_screen.y()),
        )
        p.drawLine(
            QPointF(center_screen.x(), center_screen.y() - 4),
            QPointF(center_screen.x(), center_screen.y() + 4),
        )

        # Radius-Handle
        radius_fill = QColor(255, 160, 70, 245) if is_radius_active else QColor(220, 130, 50, 215)
        radius_stroke = QColor(255, 245, 220, 230)
        radius_size = 6 if is_radius_active else 5
        radius_rect = QRectF(
            radius_screen.x() - radius_size,
            radius_screen.y() - radius_size,
            radius_size * 2,
            radius_size * 2,
        )
        p.setPen(QPen(radius_stroke, 1.5))
        p.setBrush(QBrush(radius_fill))
        p.drawRect(radius_rect)

    @staticmethod
    def _unit_vec(dx: float, dy: float):
        n = math.hypot(dx, dy)
        if n < 1e-9:
            return None
        return (dx / n, dy / n)

    def _line_tool_start_world(self):
        if self.current_tool != SketchTool.LINE or self.tool_step < 1:
            return None
        if not self.tool_points:
            return None
        return self.tool_points[-1]

    def _draw_perpendicular_snap_guides(self, p, snap_screen: QPointF, target_line):
        if not (target_line and hasattr(target_line, "start") and hasattr(target_line, "end")):
            return
        start_world = self._line_tool_start_world()
        if start_world is None:
            return

        line_start_screen = self.world_to_screen(start_world)
        ref_a = self.world_to_screen(QPointF(target_line.start.x, target_line.start.y))
        ref_b = self.world_to_screen(QPointF(target_line.end.x, target_line.end.y))

        p.save()
        p.setPen(QPen(QColor(120, 220, 255, 130), 1, Qt.DashLine))
        p.drawLine(ref_a, ref_b)
        p.setPen(QPen(QColor(0, 205, 255, 190), 1, Qt.DashLine))
        p.drawLine(line_start_screen, snap_screen)

        u = self._unit_vec(ref_b.x() - ref_a.x(), ref_b.y() - ref_a.y())
        v = self._unit_vec(line_start_screen.x() - snap_screen.x(), line_start_screen.y() - snap_screen.y())
        if u and v:
            m = 9.0
            a = QPointF(snap_screen.x() + u[0] * m, snap_screen.y() + u[1] * m)
            c = QPointF(snap_screen.x() + v[0] * m, snap_screen.y() + v[1] * m)
            b = QPointF(a.x() + v[0] * m, a.y() + v[1] * m)
            p.setPen(QPen(QColor(0, 230, 255), 2))
            p.drawLine(snap_screen, a)
            p.drawLine(snap_screen, c)
            p.drawLine(a, b)
            p.drawLine(c, b)
        p.restore()

    def _draw_tangent_snap_guides(self, p, snap_screen: QPointF, target_curve):
        if not (target_curve and hasattr(target_curve, "center") and hasattr(target_curve, "radius")):
            return
        start_world = self._line_tool_start_world()
        if start_world is None:
            return

        line_start_screen = self.world_to_screen(start_world)
        center_screen = self.world_to_screen(QPointF(target_curve.center.x, target_curve.center.y))

        p.save()
        p.setPen(QPen(QColor(255, 200, 120, 150), 1, Qt.DashLine))
        p.drawLine(center_screen, snap_screen)
        p.setPen(QPen(QColor(255, 220, 140, 185), 1, Qt.DashLine))
        p.drawLine(line_start_screen, snap_screen)

        ur = self._unit_vec(center_screen.x() - snap_screen.x(), center_screen.y() - snap_screen.y())
        ut = self._unit_vec(line_start_screen.x() - snap_screen.x(), line_start_screen.y() - snap_screen.y())
        if ur and ut:
            m = 9.0
            a = QPointF(snap_screen.x() + ur[0] * m, snap_screen.y() + ur[1] * m)
            c = QPointF(snap_screen.x() + ut[0] * m, snap_screen.y() + ut[1] * m)
            b = QPointF(a.x() + ut[0] * m, a.y() + ut[1] * m)
            p.setPen(QPen(QColor(255, 235, 170), 2))
            p.drawLine(snap_screen, a)
            p.drawLine(snap_screen, c)
            p.drawLine(a, b)
            p.drawLine(c, b)
        p.restore()

    def _draw_axis_snap_guides(self, p, snap_screen: QPointF, horizontal: bool):
        start_world = self._line_tool_start_world()
        if start_world is None:
            return
        line_start_screen = self.world_to_screen(start_world)

        p.save()
        p.setPen(QPen(QColor(120, 220, 255, 110), 1, Qt.DashLine))
        p.drawLine(line_start_screen, snap_screen)
        if horizontal:
            p.drawLine(QPointF(0, snap_screen.y()), QPointF(self.width(), snap_screen.y()))
        else:
            p.drawLine(QPointF(snap_screen.x(), 0), QPointF(snap_screen.x(), self.height()))
        p.restore()

    def _draw_parallel_snap_guides(self, p, snap_screen: QPointF, target_line):
        if not (target_line and hasattr(target_line, "start") and hasattr(target_line, "end")):
            return
        start_world = self._line_tool_start_world()
        if start_world is None:
            return

        line_start_screen = self.world_to_screen(start_world)
        ref_a = self.world_to_screen(QPointF(target_line.start.x, target_line.start.y))
        ref_b = self.world_to_screen(QPointF(target_line.end.x, target_line.end.y))

        p.save()
        p.setPen(QPen(QColor(180, 210, 255, 130), 1, Qt.DashLine))
        p.drawLine(ref_a, ref_b)
        p.setPen(QPen(QColor(170, 205, 255, 190), 1, Qt.DashLine))
        p.drawLine(line_start_screen, snap_screen)

        u = self._unit_vec(ref_b.x() - ref_a.x(), ref_b.y() - ref_a.y())
        if u:
            n = (-u[1], u[0])
            mid = QPointF((line_start_screen.x() + snap_screen.x()) * 0.5, (line_start_screen.y() + snap_screen.y()) * 0.5)
            for off in (-3.0, 3.0):
                a = QPointF(mid.x() + n[0] * off - u[0] * 4.0, mid.y() + n[1] * off - u[1] * 4.0)
                b = QPointF(mid.x() + n[0] * off + u[0] * 4.0, mid.y() + n[1] * off + u[1] * 4.0)
                p.setPen(QPen(QColor(200, 220, 255), 2))
                p.drawLine(a, b)
        p.restore()

    def _draw_angle45_snap_guides(self, p, snap_screen: QPointF):
        start_world = self._line_tool_start_world()
        if start_world is None:
            return
        line_start_screen = self.world_to_screen(start_world)

        p.save()
        p.setPen(QPen(QColor(150, 225, 255, 120), 1, Qt.DashLine))
        p.drawLine(line_start_screen, snap_screen)

        u = self._unit_vec(
            snap_screen.x() - line_start_screen.x(),
            snap_screen.y() - line_start_screen.y(),
        )
        if u:
            inv_sqrt2 = math.sqrt(0.5)
            diag_a = (inv_sqrt2, inv_sqrt2)
            diag_b = (inv_sqrt2, -inv_sqrt2)
            dot_a = abs(u[0] * diag_a[0] + u[1] * diag_a[1])
            dot_b = abs(u[0] * diag_b[0] + u[1] * diag_b[1])
            base = diag_a if dot_a >= dot_b else diag_b
            sign = 1.0 if (u[0] * base[0] + u[1] * base[1]) >= 0.0 else -1.0
            ux, uy = base[0] * sign, base[1] * sign

            span = float(max(self.width(), self.height())) * 1.5
            a = QPointF(snap_screen.x() - ux * span, snap_screen.y() - uy * span)
            b = QPointF(snap_screen.x() + ux * span, snap_screen.y() + uy * span)
            p.setPen(QPen(QColor(170, 230, 255, 140), 1, Qt.DashLine))
            p.drawLine(a, b)
        p.restore()

    def _draw_curvature_comb(self, p: QPainter, spline):
        """
        Zeichnet eine Krümmungsanalyse (Curvature Comb) für den Spline.
        """
        try:
            # Skalierung basierend auf Zoom-Level (damit die Kämme nicht riesig werden beim Rauszoomen)
            # Experimenteller Faktor.
            scale_factor = 1.0 / self.view_scale * 0.5 
            
            comb_data = spline.get_curvature_comb(num_samples=100, scale=scale_factor)
            if not comb_data:
                return

            # Style
            p.save()
            # Kämme (Quills) in hellem Blau
            p.setPen(QPen(QColor(0, 150, 255, 100), 1))
            
            # Pfad für die Oberschwingung (Top-Line)
            top_line = QPainterPath()
            
            for i, (start, end, k) in enumerate(comb_data):
                s = self.world_to_screen(QPointF(start.x, start.y))
                e = self.world_to_screen(QPointF(end.x, end.y))
                
                # Zeichne Quill (Linie vom Kurvenpunkt zum Krümmungswert)
                p.drawLine(s, e)
                
                # Sammle Punkte für Top-Line
                if i == 0:
                    top_line.moveTo(e)
                else:
                    top_line.lineTo(e)
            
            # Zeichne verbindende Linie oben drauf
            p.setPen(QPen(QColor(0, 100, 200, 180), 2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(top_line)
            
            p.restore()
        except Exception as e:
            logger.debug(f"Failed to draw curvature comb: {e}")

    def _should_show_snap_label(self, snap_type, pos: QPointF) -> bool:
        # Define tools that should show snap labels
        drawing_tools = [
            SketchTool.LINE, SketchTool.RECTANGLE, SketchTool.RECTANGLE_CENTER,
            SketchTool.CIRCLE, SketchTool.ELLIPSE, SketchTool.ARC_3POINT, SketchTool.POLYGON, 
            SketchTool.SLOT, SketchTool.SPLINE, SketchTool.NUT, SketchTool.STAR
        ]
        
        if self.current_tool not in drawing_tools or self.tool_step < 1:
            self._snap_label_key = None
            self._snap_label_since_ms = 0.0
            return False
        if snap_type in (SnapType.NONE, SnapType.GRID, SnapType.EDGE):
            self._snap_label_key = None
            self._snap_label_since_ms = 0.0
            return False

        # Quantized position avoids re-starting the delay on tiny sub-pixel jitter.
        key = (int(getattr(snap_type, "value", 0)), int(pos.x() / 2.0), int(pos.y() / 2.0))
        now_ms = time.monotonic() * 1000.0
        last_key = getattr(self, "_snap_label_key", None)
        if key != last_key:
            self._snap_label_key = key
            self._snap_label_since_ms = now_ms
            return False

        since_ms = float(getattr(self, "_snap_label_since_ms", now_ms))
        return (now_ms - since_ms) >= 90.0

    def _snap_visual_style(self, snap_type):
        """
        Returns a consistent visual style for snap marker + label.
        """
        style_map = {
            SnapType.ENDPOINT: (QColor(90, 210, 255), tr("Endpoint")),
            SnapType.MIDPOINT: (QColor(80, 230, 190), tr("Midpoint")),
            SnapType.CENTER: (QColor(255, 205, 100), tr("Center")),
            SnapType.QUADRANT: (QColor(200, 210, 255), tr("Quadrant")),
            SnapType.INTERSECTION: (QColor(255, 255, 255), tr("Intersection")),
            SnapType.VIRTUAL_INTERSECTION: (QColor(120, 220, 255), tr("Virtual")),
            SnapType.PERPENDICULAR: (QColor(0, 230, 255), tr("Perpendicular")),
            SnapType.TANGENT: (QColor(255, 225, 150), tr("Tangent")),
            SnapType.ANGLE_45: (QColor(165, 230, 255), tr("45 deg")),
            SnapType.HORIZONTAL: (QColor(120, 235, 255), tr("Horizontal")),
            SnapType.VERTICAL: (QColor(140, 240, 255), tr("Vertical")),
            SnapType.PARALLEL: (QColor(190, 220, 255), tr("Parallel")),
            SnapType.ORIGIN: (QColor(170, 255, 170), tr("Origin")),
            SnapType.EDGE: (QColor(160, 170, 190), tr("Edge")),
        }
        return style_map.get(snap_type, (self.SNAP_COLOR, "Snap"))

    def _draw_snap_label(self, p, pos: QPointF, snap_type):
        """
        Draw short snap text near the cursor for stronger CAD-like feedback.
        """
        if not self._should_show_snap_label(snap_type, pos):
            return
        color, label = self._snap_visual_style(snap_type)
        if not label:
            return

        p.save()
        font = QFont("Segoe UI", 8)
        p.setFont(font)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(label) + 8
        h = fm.height() + 4
        x = int(pos.x()) + 12
        y = int(pos.y()) - (h + 10)
        rect = QRectF(x, y, w, h)

        p.setPen(QPen(QColor(20, 20, 20, 220), 1))
        p.setBrush(QBrush(QColor(20, 20, 20, 180)))
        p.drawRoundedRect(rect, 4, 4)
        p.setPen(QPen(color, 1))
        p.drawText(rect, Qt.AlignCenter, label)
        p.restore()

    def _draw_snap_feedback_overlay(self, p):
        """
        Draws a compact confidence/info overlay close to the cursor while sketching.
        """
        drawing_tools = [
            SketchTool.LINE, SketchTool.RECTANGLE, SketchTool.RECTANGLE_CENTER,
            SketchTool.CIRCLE, SketchTool.ELLIPSE, SketchTool.ARC_3POINT, SketchTool.POLYGON, 
            SketchTool.SLOT, SketchTool.SPLINE, SketchTool.NUT, SketchTool.STAR
        ]
        drawing_mode = self.current_tool in drawing_tools and self.tool_step >= 1
        
        if not drawing_mode:
            return

        cursor = QPointF(self.mouse_screen.x(), self.mouse_screen.y())
        x = int(cursor.x()) + 14
        y = int(cursor.y()) + 10

        if self.current_snap and self.current_snap[1] not in (SnapType.NONE, SnapType.GRID):
            snap_type = self.current_snap[1]
            _, label = self._snap_visual_style(snap_type)
            confidence = max(0.0, min(1.0, float(getattr(self, "last_snap_confidence", 0.0))))
            confidence_pct = int(round(confidence * 100.0))

            text = f"{label}: {confidence_pct}%"
            font = QFont("Segoe UI", 8)
            p.save()
            p.setFont(font)
            fm = p.fontMetrics()
            w = fm.horizontalAdvance(text) + 10
            h = fm.height() + 6
            rect = QRectF(x, y, w, h)
            p.setPen(QPen(QColor(20, 24, 30, 220), 1))
            p.setBrush(QBrush(QColor(24, 30, 38, 180)))
            p.drawRoundedRect(rect, 4, 4)
            p.setPen(QPen(QColor(175, 235, 255), 1))
            p.drawText(rect, Qt.AlignCenter, text)
            p.restore()
            return

        diagnostic = (getattr(self, "last_snap_diagnostic", "") or "").strip()
        if not diagnostic:
            return

        text = diagnostic
        tip_idx = text.find("Tipp:")
        if tip_idx > 0:
            text = text[:tip_idx].strip()
        if len(text) > 86:
            text = text[:83].rstrip() + "..."
        if not text:
            return

        p.save()
        p.setFont(QFont("Segoe UI", 8))
        fm = p.fontMetrics()
        w = min(max(170, fm.horizontalAdvance(text) + 12), 360)
        h = fm.height() + 8
        rect = QRectF(x, y, w, h)
        p.setPen(QPen(QColor(65, 50, 28, 220), 1))
        p.setBrush(QBrush(QColor(70, 56, 30, 180)))
        p.drawRoundedRect(rect, 4, 4)
        p.setPen(QPen(QColor(255, 215, 135), 1))
        p.drawText(rect.adjusted(6, 0, -6, 0), Qt.AlignVCenter | Qt.AlignLeft, text)
        p.restore()
    
    def _draw_snap(self, p):
        if not self.current_snap or self.current_snap[1] == SnapType.GRID: return
        pos = self.world_to_screen(self.current_snap[0])
        st = self.current_snap[1]
        snap_color, _ = self._snap_visual_style(st)
        p.setPen(QPen(snap_color, 2))
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
        elif st == SnapType.VIRTUAL_INTERSECTION:
            p.save()
            p.setPen(QPen(QColor(120, 220, 255), 2, Qt.DashLine))
            p.drawLine(int(pos.x())-6, int(pos.y())-6, int(pos.x())+6, int(pos.y())+6)
            p.drawLine(int(pos.x())+6, int(pos.y())-6, int(pos.x())-6, int(pos.y())+6)
            p.drawEllipse(pos, 4, 4)

            # Optional visual hint for extension lines when metadata is available.
            snap_meta = self.current_snap[2] if len(self.current_snap) > 2 else None
            entities = snap_meta.get("entities") if isinstance(snap_meta, dict) else None
            if entities:
                p.setPen(QPen(QColor(120, 220, 255, 140), 1, Qt.DashLine))
                for entity in entities:
                    if not (hasattr(entity, "start") and hasattr(entity, "end")):
                        continue
                    s = self.world_to_screen(QPointF(entity.start.x, entity.start.y))
                    e = self.world_to_screen(QPointF(entity.end.x, entity.end.y))
                    p.drawLine(s, e)
                    # Extension ray from closer endpoint to virtual snap point.
                    ds = (s.x() - pos.x()) ** 2 + (s.y() - pos.y()) ** 2
                    de = (e.x() - pos.x()) ** 2 + (e.y() - pos.y()) ** 2
                    anchor = s if ds <= de else e
                    p.drawLine(anchor, pos)
            p.restore()
        elif st == SnapType.PERPENDICULAR:
            self._draw_perpendicular_snap_guides(p, pos, self.current_snap[2] if len(self.current_snap) > 2 else None)
            x = int(pos.x())
            y = int(pos.y())
            p.drawLine(x - 8, y + 6, x + 2, y + 6)
            p.drawLine(x + 2, y + 6, x + 2, y - 4)
            p.drawLine(x - 8, y - 4, x + 2, y - 4)
        elif st == SnapType.TANGENT:
            self._draw_tangent_snap_guides(p, pos, self.current_snap[2] if len(self.current_snap) > 2 else None)
            x = int(pos.x())
            y = int(pos.y())
            p.drawEllipse(pos, 5, 5)
            p.drawLine(x - 9, y + 7, x + 9, y + 7)
        elif st == SnapType.ANGLE_45:
            self._draw_angle45_snap_guides(p, pos)
            x = int(pos.x())
            y = int(pos.y())
            p.drawLine(x - 8, y + 8, x + 8, y - 8)
            p.drawLine(x - 8, y + 4, x + 4, y - 8)
        elif st == SnapType.HORIZONTAL:
            self._draw_axis_snap_guides(p, pos, horizontal=True)
            x = int(pos.x())
            y = int(pos.y())
            p.drawLine(x - 9, y, x + 9, y)
            p.drawLine(x - 9, y - 3, x - 9, y + 3)
            p.drawLine(x + 9, y - 3, x + 9, y + 3)
        elif st == SnapType.VERTICAL:
            self._draw_axis_snap_guides(p, pos, horizontal=False)
            x = int(pos.x())
            y = int(pos.y())
            p.drawLine(x, y - 9, x, y + 9)
            p.drawLine(x - 3, y - 9, x + 3, y - 9)
            p.drawLine(x - 3, y + 9, x + 3, y + 9)
        elif st == SnapType.PARALLEL:
            self._draw_parallel_snap_guides(p, pos, self.current_snap[2] if len(self.current_snap) > 2 else None)
            x = int(pos.x())
            y = int(pos.y())
            p.drawLine(x - 8, y - 3, x + 8, y - 3)
            p.drawLine(x - 8, y + 3, x + 8, y + 3)
        elif st == SnapType.ORIGIN:
            # Origin: Kreis mit Kreuz (ähnlich wie Center aber größer/hervorgehoben)
            p.drawEllipse(pos, 6, 6)
            p.drawLine(int(pos.x())-8, int(pos.y()), int(pos.x())+8, int(pos.y()))
            p.drawLine(int(pos.x()), int(pos.y())-8, int(pos.x()), int(pos.y())+8)
        self._draw_snap_label(p, pos, st)
    
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
        elif self.current_tool == SketchTool.ELLIPSE and self.tool_step >= 1:
            ctr = self.world_to_screen(self.tool_points[0])
            p.setPen(QPen(self.DIM_COLOR))
            if self.tool_step == 1:
                p.drawText(int(ctr.x())+10, int(ctr.y())-8, f"Ra {self.live_length:.1f} @ {self.live_angle:.1f}°")
            else:
                p.drawText(int(ctr.x())+10, int(ctr.y())-8, f"Rb {self.live_radius:.1f} mm")
        elif self.current_tool == SketchTool.POLYGON and self.tool_step == 1:
            ctr = self.world_to_screen(self.tool_points[0])
            p.setPen(QPen(self.DIM_COLOR))
            p.drawText(int(ctr.x())+10, int(ctr.y())-int(self.live_radius*self.view_scale)-8, f"R {self.live_radius:.1f} ({self.polygon_sides})")
    
    def _draw_hud(self, p):
        p.setPen(QPen(QColor(150, 150, 150)))
        p.setFont(QFont("Consolas", 10))
        p.drawText(10, self.height() - 10, f"X: {self.mouse_world.x():.2f}  Y: {self.mouse_world.y():.2f}")
        from gui.sketch_editor import format_zoom_label
        p.drawText(self.width() - 100, self.height() - 10, f"Zoom: {format_zoom_label(self.view_scale)}")
        tool_name = self.current_tool.name.replace('_', ' ').title()
        p.setFont(QFont("Arial", 12, QFont.Bold))
        p.setPen(QPen(self.GEO_SELECTED))
        p.drawText(12, 25, f"Tool: {tool_name}")

        hint_y = 45
        p.setFont(QFont("Arial", 10))
        p.setPen(QPen(QColor(110, 180, 255, 220)))
        p.drawText(12, hint_y, tr("Navigation: Shift+R=Ansicht drehen | Space halten=3D-Peek"))
        hint_y += 18

        # Tab hint for drawing tools.
        drawing_tools = [
            SketchTool.LINE,
            SketchTool.RECTANGLE,
            SketchTool.CIRCLE,
            SketchTool.ELLIPSE,
            SketchTool.POLYGON,
            SketchTool.SLOT,
            SketchTool.ARC_3POINT,
        ]
        if self.current_tool in drawing_tools and self.tool_step >= 1:
            p.setFont(QFont("Arial", 10))
            p.setPen(QPen(QColor(100, 180, 255, 180)))
            p.drawText(12, hint_y, tr("Tipp: Tab = Masse eingeben"))
            hint_y += 18

        sel_count = len(self.selected_lines) + len(self.selected_circles)
        if sel_count > 0:
            p.setFont(QFont("Arial", 10))
            p.setPen(QPen(QColor(150, 150, 150)))
            p.drawText(12, hint_y, tr("Ausgewaehlt: {count}").format(count=sel_count))

        profile_count = len(self.closed_profiles)
        p.setFont(QFont("Arial", 10))
        if profile_count > 0:
            p.setPen(QPen(QColor(100, 200, 100)))
            p.drawText(self.width() - 180, 25, f"✓ {profile_count} geschlossene Profile")
        else:
            p.setPen(QPen(QColor(200, 150, 100)))
            p.drawText(self.width() - 160, 25, "○ Kein geschlossenes Profil")

        # Constraint status.
        constraint_count = len(self.sketch.constraints)
        if constraint_count > 0:
            p.setFont(QFont("Arial", 9))
            p.setPen(QPen(QColor(150, 200, 150)))
            p.drawText(self.width() - 180, 42, f"⚙ {constraint_count} Constraints")

        y = 58
        p.setFont(QFont("Arial", 10))
        if self.construction_mode:
            p.setPen(QPen(self.GEO_CONSTRUCTION))
            p.drawText(self.width() - 130, y, "KONSTRUKTION (X)")
            y += 18
        if not self.grid_snap:
            p.setPen(QPen(QColor(180, 100, 100)))
            p.drawText(self.width() - 100, y, "Grid: AUS (G)")

        # Draw central HUD toast.
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
    
