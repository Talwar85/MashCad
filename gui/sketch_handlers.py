"""
LiteCAD - Sketch Handlers Mixin
All _handle_* methods for sketch tools
Extracted from sketch_editor.py for better maintainability
"""

import math
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication, QInputDialog

from sketcher import Point2D, Line2D, Circle2D, Arc2D
from i18n import tr

# Importiere SketchTool und SnapType
try:
    from gui.sketch_tools import SketchTool, SnapType
except ImportError:
    try:
        from sketch_tools import SketchTool, SnapType
    except ImportError:
        from .sketch_tools import SketchTool, SnapType


class SketchHandlersMixin:
    """Mixin containing all tool handler methods for SketchEditor"""
    
    def _handle_select(self, pos, snap_type):
        hit = self._find_entity_at(pos)
        if not (QApplication.keyboardModifiers() & Qt.ShiftModifier): self._clear_selection()
        if hit:
            if isinstance(hit, Line2D):
                if hit in self.selected_lines: self.selected_lines.remove(hit)
                else: self.selected_lines.append(hit)
            elif isinstance(hit, Circle2D):
                if hit in self.selected_circles: self.selected_circles.remove(hit)
                else: self.selected_circles.append(hit)
            elif isinstance(hit, Arc2D):
                if hit in self.selected_arcs: self.selected_arcs.remove(hit)
                else: self.selected_arcs.append(hit)
            elif isinstance(hit, Point2D):
                if hit in self.selected_points: self.selected_points.remove(hit)
                else: self.selected_points.append(hit)
    
    def _handle_line(self, pos, snap_type):
        if self.tool_step == 0:
            self.tool_points = [pos]
            self.tool_step = 1
            self.status_message.emit(tr("Endpoint | Tab=Length/Angle | Right=Finish"))
        else:
            start = self.tool_points[-1]
            if math.hypot(pos.x()-start.x(), pos.y()-start.y()) > 0.01:
                self._save_undo()
                self.sketch.add_line(start.x(), start.y(), pos.x(), pos.y(), construction=self.construction_mode)
                self.sketched_changed.emit()
                self._find_closed_profiles()
                self.tool_points.append(pos)
    
    def _handle_rectangle(self, pos, snap_type):
        """Rechteck mit Modus-Unterstützung (0=2-Punkt, 1=Center)"""
        if self.rect_mode == 1:
            # Center-Modus
            if self.tool_step == 0:
                self.tool_points = [pos]
                self.tool_step = 1
                self.status_message.emit(tr("Corner | Tab=Width/Height"))
            else:
                c = self.tool_points[0]
                w, h = abs(pos.x()-c.x())*2, abs(pos.y()-c.y())*2
                if w > 0.01 and h > 0.01:
                    self._save_undo()
                    self.sketch.add_rectangle(c.x()-w/2, c.y()-h/2, w, h, construction=self.construction_mode)
                    self.sketch.solve()
                    self.sketched_changed.emit()
                    self._find_closed_profiles()
                self._cancel_tool()
        else:
            # 2-Punkt-Modus (Standard)
            if self.tool_step == 0:
                self.tool_points = [pos]
                self.tool_step = 1
                self.status_message.emit(tr("Opposite corner | Tab=Width/Height"))
            else:
                p1, p2 = self.tool_points[0], pos
                w, h = abs(p2.x()-p1.x()), abs(p2.y()-p1.y())
                if w > 0.01 and h > 0.01:
                    self._save_undo()
                    self.sketch.add_rectangle(min(p1.x(),p2.x()), min(p1.y(),p2.y()), w, h, construction=self.construction_mode)
                    self.sketch.solve()
                    self.sketched_changed.emit()
                    self._find_closed_profiles()
                self._cancel_tool()
    
    def _handle_rectangle_center(self, pos, snap_type):
        if self.tool_step == 0:
            self.tool_points = [pos]
            self.tool_step = 1
            self.status_message.emit(tr("Corner | Tab=Width/Height"))
        else:
            c = self.tool_points[0]
            w, h = abs(pos.x()-c.x())*2, abs(pos.y()-c.y())*2
            if w > 0.01 and h > 0.01:
                self._save_undo()
                self.sketch.add_rectangle(c.x()-w/2, c.y()-h/2, w, h, construction=self.construction_mode)
                self.sketch.solve()
                self.sketched_changed.emit()
                self._find_closed_profiles()
            self._cancel_tool()
    
    def _handle_circle(self, pos, snap_type):
        """Kreis mit Modus-Unterstützung (0=Center-Radius, 1=2-Punkt, 2=3-Punkt)"""
        if self.circle_mode == 1:
            # 2-Punkt-Modus (Durchmesser)
            if self.tool_step == 0:
                self.tool_points = [pos]
                self.tool_step = 1
                self.status_message.emit(tr("Second point (diameter)"))
            else:
                p1, p2 = self.tool_points[0], pos
                cx, cy = (p1.x()+p2.x())/2, (p1.y()+p2.y())/2
                r = math.hypot(p2.x()-p1.x(), p2.y()-p1.y()) / 2
                if r > 0.01:
                    self._save_undo()
                    self.sketch.add_circle(cx, cy, r, construction=self.construction_mode)
                    self.sketched_changed.emit()
                    self._find_closed_profiles()
                self._cancel_tool()
        elif self.circle_mode == 2:
            # 3-Punkt-Modus
            if self.tool_step == 0:
                self.tool_points = [pos]
                self.tool_step = 1
                self.status_message.emit(tr("Second point"))
            elif self.tool_step == 1:
                self.tool_points.append(pos)
                self.tool_step = 2
                self.status_message.emit(tr("Third point"))
            else:
                p1, p2, p3 = self.tool_points[0], self.tool_points[1], pos
                center, r = self._calc_circle_3points(p1, p2, p3)
                if center and r > 0.01:
                    self._save_undo()
                    self.sketch.add_circle(center.x(), center.y(), r, construction=self.construction_mode)
                    self.sketched_changed.emit()
                    self._find_closed_profiles()
                self._cancel_tool()
        else:
            # Center-Radius-Modus (Standard)
            if self.tool_step == 0:
                self.tool_points = [pos]
                self.tool_step = 1
                self.status_message.emit(tr("Radius | Tab=Input"))
            else:
                c = self.tool_points[0]
                r = math.hypot(pos.x()-c.x(), pos.y()-c.y())
                if r > 0.01:
                    self._save_undo()
                    self.sketch.add_circle(c.x(), c.y(), r, construction=self.construction_mode)
                    self.sketched_changed.emit()
                    self._find_closed_profiles()
                self._cancel_tool()
    
    def _calc_circle_3points(self, p1, p2, p3):
        """Berechnet Mittelpunkt und Radius eines Kreises durch 3 Punkte"""
        x1, y1 = p1.x(), p1.y()
        x2, y2 = p2.x(), p2.y()
        x3, y3 = p3.x(), p3.y()
        
        # Determinante für Kollinearitäts-Check
        d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
        if abs(d) < 1e-10:
            return None, 0  # Punkte sind kollinear
        
        # Mittelpunkt berechnen
        ux = ((x1*x1 + y1*y1) * (y2 - y3) + (x2*x2 + y2*y2) * (y3 - y1) + (x3*x3 + y3*y3) * (y1 - y2)) / d
        uy = ((x1*x1 + y1*y1) * (x3 - x2) + (x2*x2 + y2*y2) * (x1 - x3) + (x3*x3 + y3*y3) * (x2 - x1)) / d
        
        # Radius
        r = math.hypot(x1 - ux, y1 - uy)
        
        return QPointF(ux, uy), r
    
    def _handle_circle_2point(self, pos, snap_type):
        if self.tool_step == 0:
            self.tool_points = [pos]
            self.tool_step = 1
            self.status_message.emit(tr("Second point"))
        else:
            p1, p2 = self.tool_points[0], pos
            cx, cy = (p1.x()+p2.x())/2, (p1.y()+p2.y())/2
            r = math.hypot(p2.x()-p1.x(), p2.y()-p1.y()) / 2
            if r > 0.01:
                self._save_undo()
                self.sketch.add_circle(cx, cy, r, construction=self.construction_mode)
                self.sketched_changed.emit()
                self._find_closed_profiles()
            self._cancel_tool()
    
    def _handle_polygon(self, pos, snap_type):
        if self.tool_step == 0:
            self.tool_points = [pos]
            self.tool_step = 1
            self.status_message.emit(tr("Radius") + f" ({self.polygon_sides} " + tr("{n} sides").format(n="") + ") | Tab")
        else:
            c = self.tool_points[0]
            r = math.hypot(pos.x()-c.x(), pos.y()-c.y())
            angle = math.atan2(pos.y()-c.y(), pos.x()-c.x())
            if r > 0.01:
                self._save_undo()
                pts = [(c.x() + r*math.cos(angle + 2*math.pi*i/self.polygon_sides),
                        c.y() + r*math.sin(angle + 2*math.pi*i/self.polygon_sides)) for i in range(self.polygon_sides)]
                self.sketch.add_polygon(pts, closed=True, construction=self.construction_mode)
                self.sketch.solve()
                self.sketched_changed.emit()
                self._find_closed_profiles()
            self._cancel_tool()
    
    def _handle_arc_3point(self, pos, snap_type):
        self.tool_points.append(pos)
        n = len(self.tool_points)
        if n == 1: self.tool_step = 1; self.status_message.emit(tr("Through point"))
        elif n == 2: self.tool_step = 2; self.status_message.emit(tr("Endpoint"))
        else:
            p1, p2, p3 = self.tool_points[:3]
            arc = self._calc_arc_3point(p1, p2, p3)
            if arc:
                self._save_undo()
                self.sketch.add_arc(*arc, construction=self.construction_mode)
                self.sketched_changed.emit()
            self._cancel_tool()
    
    def _calc_arc_3point(self, p1, p2, p3):
        ax, ay, bx, by, cx, cy = p1.x(), p1.y(), p2.x(), p2.y(), p3.x(), p3.y()
        d = 2*(ax*(by-cy) + bx*(cy-ay) + cx*(ay-by))
        if abs(d) < 1e-10: return None
        ux = ((ax*ax+ay*ay)*(by-cy) + (bx*bx+by*by)*(cy-ay) + (cx*cx+cy*cy)*(ay-by)) / d
        uy = ((ax*ax+ay*ay)*(cx-bx) + (bx*bx+by*by)*(ax-cx) + (cx*cx+cy*cy)*(bx-ax)) / d
        r = math.hypot(ax-ux, ay-uy)
        start = math.degrees(math.atan2(ay-uy, ax-ux))
        end = math.degrees(math.atan2(cy-uy, cx-ux))
        return (ux, uy, r, start, end)
    
    def _handle_slot(self, pos, snap_type):
        if self.tool_step == 0:
            self.tool_points = [pos]; self.tool_step = 1
            self.status_message.emit(tr("Endpoint center line | Tab=Length/Angle"))
        elif self.tool_step == 1:
            self.tool_points.append(pos); self.tool_step = 2
            self.status_message.emit(tr("Width | Tab=Enter width"))
        else:
            p1, p2 = self.tool_points[0], self.tool_points[1]
            dx, dy = p2.x()-p1.x(), p2.y()-p1.y()
            length = math.hypot(dx, dy)
            if length > 0.01:
                nx, ny = -dy/length, dx/length
                width = abs((pos.x()-p1.x())*nx + (pos.y()-p1.y())*ny) * 2
                if width > 0.01:
                    self._save_undo()
                    self._create_slot(p1, p2, width)
                    self.sketched_changed.emit()
                    self._find_closed_profiles()
            self._cancel_tool()
    
    def _create_slot(self, p1, p2, width):
        dx, dy = p2.x()-p1.x(), p2.y()-p1.y()
        length = math.hypot(dx, dy)
        if length < 0.01: return
        
        # Senkrechte Vektoren
        ux, uy = dx/length, dy/length
        nx, ny = -uy, ux
        r = width / 2
        
        # Eckpunkte
        t1x, t1y = p1.x() + nx*r, p1.y() + ny*r
        t2x, t2y = p2.x() + nx*r, p2.y() + ny*r
        b1x, b1y = p1.x() - nx*r, p1.y() - ny*r
        b2x, b2y = p2.x() - nx*r, p2.y() - ny*r
        
        # Linien hinzufügen
        self.sketch.add_line(t1x, t1y, t2x, t2y, construction=self.construction_mode)
        self.sketch.add_line(b1x, b1y, b2x, b2y, construction=self.construction_mode)
        
        # Winkel der Achse
        base_angle = math.degrees(math.atan2(dy, dx))
        
        # Bögen hinzufügen (CCW definiert)
        # Linker Bogen: Startet "Unten" (-90 relativ) und geht nach "Oben" (+90 relativ) -> Hinten rum
        self.sketch.add_arc(p1.x(), p1.y(), r, base_angle + 90, base_angle + 270, construction=self.construction_mode)
        
        # Rechter Bogen: Startet "Oben" (+90 relativ) und geht nach "Unten" (-90 relativ) -> Vorne rum
        self.sketch.add_arc(p2.x(), p2.y(), r, base_angle - 90, base_angle + 90, construction=self.construction_mode)
    
    def _handle_spline(self, pos, snap_type):
        self.tool_points.append(pos)
        self.tool_step = len(self.tool_points)
        self.status_message.emit(tr("Point {n} | Right=Finish | Tab=Input").format(n=len(self.tool_points)))
    
    def _finish_spline(self):
        if len(self.tool_points) < 2: return
        try:
            from sketcher.geometry import BezierSpline
            
            self._save_undo()
            
            # Neue BezierSpline erstellen
            spline = BezierSpline()
            spline.construction = self.construction_mode
            
            for p in self.tool_points:
                spline.add_point(p.x(), p.y())
            
            # Spline zum Sketch hinzufügen
            self.sketch.splines.append(spline)
            
            # Auch als Linien für Kompatibilität (Export etc.)
            lines = spline.to_lines(segments_per_span=10)
            spline._lines = lines  # Referenz speichern für späteren Update
            
            for line in lines:
                self.sketch.lines.append(line)
                self.sketch.points.append(line.start)
            if lines:
                self.sketch.points.append(lines[-1].end)
            
            # Spline auswählen für sofortiges Editing
            self.selected_spline = spline
            
            self.sketched_changed.emit()
            self._find_closed_profiles()
            self.status_message.emit(tr("Spline created - drag points/handles to edit"))
        except Exception as e:
            print(f"Spline error: {e}")
        self._cancel_tool()
    
    def _handle_move(self, pos, snap_type):
        """Verschieben: Basispunkt → Zielpunkt (wie Fusion360)"""
        if not self.selected_lines and not self.selected_circles and not self.selected_arcs:
            self.status_message.emit(tr("Select elements first!"))
            return
        
        if self.tool_step == 0:
            # Schritt 1: Basispunkt wählen
            self.tool_points = [pos]
            self.tool_step = 1
            self.status_message.emit(tr("Target point | [Tab] for X/Y input"))
        else:
            # Schritt 2: Zielpunkt - verschieben
            dx = pos.x() - self.tool_points[0].x()
            dy = pos.y() - self.tool_points[0].y()
            self._save_undo()
            self._move_selection(dx, dy)
            self.sketched_changed.emit()
            self._find_closed_profiles()
            self._cancel_tool()
    
    def _move_selection(self, dx, dy):
        """Verschiebt alle ausgewählten Elemente"""
        moved = set()
        for line in self.selected_lines:
            for pt in [line.start, line.end]:
                if pt.id not in moved:
                    pt.x += dx
                    pt.y += dy
                    moved.add(pt.id)
        for c in self.selected_circles:
            if c.center.id not in moved:
                c.center.x += dx
                c.center.y += dy
                moved.add(c.center.id)
        self.sketch.solve()
    
    def _handle_copy(self, pos, snap_type):
        """Kopieren: Basispunkt → Zielpunkt (wie Fusion360)"""
        if not self.selected_lines and not self.selected_circles and not self.selected_arcs:
            self.status_message.emit(tr("Select elements first!"))
            return
        
        if self.tool_step == 0:
            # Schritt 1: Basispunkt wählen
            self.tool_points = [pos]
            self.tool_step = 1
            self.status_message.emit(tr("Target point for copy"))
        else:
            # Schritt 2: Kopieren zum Zielpunkt
            dx = pos.x() - self.tool_points[0].x()
            dy = pos.y() - self.tool_points[0].y()
            self._save_undo()
            
            # Neue Elemente erstellen
            new_lines = []
            new_circles = []
            for line in self.selected_lines:
                new_line = self.sketch.add_line(
                    line.start.x + dx, line.start.y + dy,
                    line.end.x + dx, line.end.y + dy,
                    construction=line.construction
                )
                new_lines.append(new_line)
            for c in self.selected_circles:
                new_circle = self.sketch.add_circle(
                    c.center.x + dx, c.center.y + dy,
                    c.radius, construction=c.construction
                )
                new_circles.append(new_circle)
            
            # Neue Elemente auswählen
            self._clear_selection()
            self.selected_lines = new_lines
            self.selected_circles = new_circles
            
            self.sketched_changed.emit()
            self._find_closed_profiles()
            self._cancel_tool()
            self.status_message.emit(tr("Copied: {lines} lines, {circles} circles").format(lines=len(new_lines), circles=len(new_circles)))
    
    def _handle_rotate(self, pos, snap_type):
        """Drehen: Zentrum → Winkel (wie Fusion360)"""
        if not self.selected_lines and not self.selected_circles and not self.selected_arcs:
            self.status_message.emit(tr("Select elements first!"))
            return
        
        if self.tool_step == 0:
            # Schritt 1: Drehzentrum wählen
            self.tool_points = [pos]
            self.tool_step = 1
            self.status_message.emit(tr("Set rotation angle | Tab=Enter degrees"))
        else:
            # Schritt 2: Winkel durch Klick oder Tab bestimmen
            center = self.tool_points[0]
            angle = math.degrees(math.atan2(pos.y() - center.y(), pos.x() - center.x()))
            self._save_undo()
            self._rotate_selection(center, angle)
            self.sketched_changed.emit()
            self._find_closed_profiles()
            self._cancel_tool()
    
    def _rotate_selection(self, center, angle_deg):
        """Rotiert alle ausgewählten Elemente um Zentrum"""
        rad = math.radians(angle_deg)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        rotated = set()
        
        for line in self.selected_lines:
            for pt in [line.start, line.end]:
                if pt.id not in rotated:
                    dx = pt.x - center.x()
                    dy = pt.y - center.y()
                    pt.x = center.x() + dx * cos_a - dy * sin_a
                    pt.y = center.y() + dx * sin_a + dy * cos_a
                    rotated.add(pt.id)
        
        for c in self.selected_circles:
            if c.center.id not in rotated:
                dx = c.center.x - center.x()
                dy = c.center.y - center.y()
                c.center.x = center.x() + dx * cos_a - dy * sin_a
                c.center.y = center.y() + dx * sin_a + dy * cos_a
                rotated.add(c.center.id)
        
        self.sketch.solve()
    
    def _handle_mirror(self, pos, snap_type):
        """Spiegeln: Achse durch 2 Punkte (wie Fusion360)"""
        if not self.selected_lines and not self.selected_circles and not self.selected_arcs:
            self.status_message.emit(tr("Select elements first!"))
            return
        
        if self.tool_step == 0:
            # Schritt 1: Erster Punkt der Spiegelachse
            self.tool_points = [pos]
            self.tool_step = 1
            self.status_message.emit(tr("Second point of mirror axis"))
        else:
            # Schritt 2: Spiegeln
            self._save_undo()
            self._mirror_selection(self.tool_points[0], pos)
            self.sketched_changed.emit()
            self._find_closed_profiles()
            self._cancel_tool()
    
    def _mirror_selection(self, p1, p2):
        """Spiegelt Auswahl an Achse p1-p2 (erstellt Kopie)"""
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.hypot(dx, dy)
        if length < 0.01:
            return
        
        # Normierte Achsenrichtung
        dx, dy = dx / length, dy / length
        
        def mirror_point(px, py):
            """Spiegelt Punkt an Achse"""
            # Projektion auf Achse
            t = (px - p1.x()) * dx + (py - p1.y()) * dy
            proj_x = p1.x() + t * dx
            proj_y = p1.y() + t * dy
            # Gespiegelter Punkt
            return 2 * proj_x - px, 2 * proj_y - py
        
        # Gespiegelte Kopien erstellen
        new_lines = []
        new_circles = []
        
        for line in self.selected_lines:
            sx, sy = mirror_point(line.start.x, line.start.y)
            ex, ey = mirror_point(line.end.x, line.end.y)
            new_line = self.sketch.add_line(sx, sy, ex, ey, construction=line.construction)
            new_lines.append(new_line)
        
        for c in self.selected_circles:
            cx, cy = mirror_point(c.center.x, c.center.y)
            new_circle = self.sketch.add_circle(cx, cy, c.radius, construction=c.construction)
            new_circles.append(new_circle)
        
        # Neue Elemente auswählen
        self._clear_selection()
        self.selected_lines = new_lines
        self.selected_circles = new_circles
        self.status_message.emit(tr("Mirrored: {lines} lines, {circles} circles").format(lines=len(new_lines), circles=len(new_circles)))
    
    def _handle_pattern_linear(self, pos, snap_type):
        """Lineares Muster: Auswahl → Richtung → Anzahl"""
        if not self.selected_lines and not self.selected_circles:
            self.status_message.emit(tr("Select elements first!"))
            return
        
        if self.tool_step == 0:
            # Schritt 1: Startpunkt (Basis)
            self.tool_points = [pos]
            self.tool_step = 1
            # Default-Werte
            self.tool_data['pattern_count'] = 3
            self.tool_data['pattern_spacing'] = 20.0
            self.status_message.emit(tr("Choose direction | Tab=Count/Spacing"))
        elif self.tool_step == 1:
            # Schritt 2: Anwenden
            self._apply_linear_pattern(pos)
    
    def _apply_linear_pattern(self, end_pos):
        """Wendet lineares Muster an"""
        start = self.tool_points[0]
        dx = end_pos.x() - start.x()
        dy = end_pos.y() - start.y()
        
        count = self.tool_data.get('pattern_count', 3)
        
        # Distanz pro Einheit
        total_dist = math.hypot(dx, dy)
        if total_dist < 0.01:
            self._cancel_tool()
            return
        
        # Normierte Richtung
        ux, uy = dx / total_dist, dy / total_dist
        spacing = self.tool_data.get('pattern_spacing', total_dist / (count - 1) if count > 1 else total_dist)
        
        self._save_undo()
        
        # Kopien erstellen (ab Index 1, Index 0 ist Original)
        created_lines = 0
        created_circles = 0
        
        for i in range(1, count):
            offset_x = ux * spacing * i
            offset_y = uy * spacing * i
            
            for line in self.selected_lines:
                self.sketch.add_line(
                    line.start.x + offset_x, line.start.y + offset_y,
                    line.end.x + offset_x, line.end.y + offset_y,
                    construction=line.construction
                )
                created_lines += 1
            
            for c in self.selected_circles:
                self.sketch.add_circle(
                    c.center.x + offset_x, c.center.y + offset_y,
                    c.radius, construction=c.construction
                )
                created_circles += 1
        
        self.sketched_changed.emit()
        self._find_closed_profiles()
        self._cancel_tool()
        self.status_message.emit(tr("Linear pattern: {lines} lines, {circles} circles created").format(lines=created_lines, circles=created_circles))
    
    def _handle_pattern_circular(self, pos, snap_type):
        """Kreisförmiges Muster: Auswahl → Zentrum → Anzahl"""
        if not self.selected_lines and not self.selected_circles:
            self.status_message.emit(tr("Select elements first!"))
            return
        
        if self.tool_step == 0:
            # Schritt 1: Zentrum wählen
            self.tool_points = [pos]
            self.tool_step = 1
            # Default-Werte
            self.tool_data['pattern_count'] = 6
            self.tool_data['pattern_angle'] = 360.0  # Vollkreis
            self.status_message.emit(tr("Center selected | Click=Apply | Tab=Count/Angle"))
        elif self.tool_step == 1:
            # Klick zum Anwenden
            self._apply_circular_pattern()
    
    def _apply_circular_pattern(self):
        """Wendet kreisförmiges Muster an"""
        center = self.tool_points[0]
        count = self.tool_data.get('pattern_count', 6)
        total_angle = self.tool_data.get('pattern_angle', 360.0)
        
        if count < 2:
            self._cancel_tool()
            return
        
        self._save_undo()
        
        # Winkelschritt
        angle_step = math.radians(total_angle / count)
        
        # Kopien erstellen (ab Index 1)
        created_lines = 0
        created_circles = 0
        
        for i in range(1, count):
            angle = angle_step * i
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            
            for line in self.selected_lines:
                # Rotiere Start- und Endpunkt um Zentrum
                sx = center.x() + (line.start.x - center.x()) * cos_a - (line.start.y - center.y()) * sin_a
                sy = center.y() + (line.start.x - center.x()) * sin_a + (line.start.y - center.y()) * cos_a
                ex = center.x() + (line.end.x - center.x()) * cos_a - (line.end.y - center.y()) * sin_a
                ey = center.y() + (line.end.x - center.x()) * sin_a + (line.end.y - center.y()) * cos_a
                
                self.sketch.add_line(sx, sy, ex, ey, construction=line.construction)
                created_lines += 1
            
            for c in self.selected_circles:
                # Rotiere Kreiszentrum um Musterzentrum
                cx = center.x() + (c.center.x - center.x()) * cos_a - (c.center.y - center.y()) * sin_a
                cy = center.y() + (c.center.x - center.x()) * sin_a + (c.center.y - center.y()) * cos_a
                
                self.sketch.add_circle(cx, cy, c.radius, construction=c.construction)
                created_circles += 1
        
        self.sketched_changed.emit()
        self._find_closed_profiles()
        self._cancel_tool()
        self.status_message.emit(tr("Circular pattern: {lines} lines, {circles} circles created").format(lines=created_lines, circles=created_circles))
    
    def _handle_scale(self, pos, snap_type):
        """Skalieren: Zentrum → Faktor (wie Fusion360)"""
        if not self.selected_lines and not self.selected_circles and not self.selected_arcs:
            self.status_message.emit(tr("Select elements first!"))
            return
        
        if self.tool_step == 0:
            # Schritt 1: Skalierungszentrum wählen
            self.tool_points = [pos]
            self.tool_step = 1
            # Berechne initialen Abstand zur Auswahl
            min_dist = float('inf')
            for line in self.selected_lines:
                d = math.hypot(line.start.x - pos.x(), line.start.y - pos.y())
                min_dist = min(min_dist, d)
                d = math.hypot(line.end.x - pos.x(), line.end.y - pos.y())
                min_dist = min(min_dist, d)
            for c in self.selected_circles:
                d = math.hypot(c.center.x - pos.x(), c.center.y - pos.y())
                min_dist = min(min_dist, d)
            self.tool_data['base_dist'] = max(min_dist, 10)  # Mindestens 10
            self.status_message.emit(tr("Scale factor | Tab=Enter factor"))
        else:
            # Schritt 2: Faktor durch Abstand oder Tab
            center = self.tool_points[0]
            current_dist = math.hypot(pos.x() - center.x(), pos.y() - center.y())
            base_dist = self.tool_data.get('base_dist', 1)
            factor = current_dist / base_dist if base_dist > 0.01 else 1.0
            
            if factor > 0.01:
                self._save_undo()
                self._scale_selection(center, factor)
                self.sketched_changed.emit()
                self._find_closed_profiles()
            self._cancel_tool()
    
    def _scale_selection(self, center, factor):
        """Skaliert alle ausgewählten Elemente vom Zentrum aus"""
        scaled = set()
        
        for line in self.selected_lines:
            for pt in [line.start, line.end]:
                if pt.id not in scaled:
                    pt.x = center.x() + (pt.x - center.x()) * factor
                    pt.y = center.y() + (pt.y - center.y()) * factor
                    scaled.add(pt.id)
        
        for c in self.selected_circles:
            if c.center.id not in scaled:
                c.center.x = center.x() + (c.center.x - center.x()) * factor
                c.center.y = center.y() + (c.center.y - center.y()) * factor
                scaled.add(c.center.id)
            # Radius auch skalieren
            c.radius *= factor
        
        self.sketch.solve()
        self._find_closed_profiles()
    
    def _handle_trim(self, pos, snap_type):
        line = self._find_line_at(pos)
        if not line: self.status_message.emit(tr("No line found")); return
        intersections = []
        for other in self.sketch.lines:
            if other == line: continue
            inter = self._line_intersection(line, other)
            if inter:
                t = self._point_on_line_t(line, inter)
                if 0.01 < t < 0.99: intersections.append((t, inter))
        if not intersections:
            self._save_undo()
            self.sketch.delete_line(line)
            self.sketched_changed.emit()
            self._find_closed_profiles()
            return
        intersections.sort()
        click_t = self._point_on_line_t(line, pos)
        self._save_undo()
        prev_t = 0.0
        for i, (t, _) in enumerate(intersections):
            if click_t < t:
                if prev_t > 0.01:
                    pt1 = self._point_at_t(line, prev_t)
                    self.sketch.add_line(line.start.x, line.start.y, pt1.x(), pt1.y())
                if t < 0.99:
                    pt2 = self._point_at_t(line, t)
                    self.sketch.add_line(pt2.x(), pt2.y(), line.end.x, line.end.y)
                self.sketch.delete_line(line)
                self.sketched_changed.emit()
                self._find_closed_profiles()
                return
            prev_t = t
        pt = self._point_at_t(line, prev_t)
        self.sketch.add_line(line.start.x, line.start.y, pt.x(), pt.y())
        self.sketch.delete_line(line)
        self.sketched_changed.emit()
        self._find_closed_profiles()
    
    def _handle_extend(self, pos, snap_type):
        line = self._find_line_at(pos)
        if not line: self.status_message.emit(tr("No line found")); return
        click_t = self._point_on_line_t(line, pos)
        extend_start = click_t < 0.5
        best_inter, best_t = None, float('inf') if not extend_start else float('-inf')
        for other in self.sketch.lines:
            if other == line: continue
            inter = self._line_intersection_extended(line, other)
            if inter:
                t = self._point_on_line_t(line, inter)
                if extend_start and t < 0 and t > best_t: best_t, best_inter = t, inter
                elif not extend_start and t > 1 and t < best_t: best_t, best_inter = t, inter
        if best_inter:
            self._save_undo()
            if extend_start: line.start.x, line.start.y = best_inter.x(), best_inter.y()
            else: line.end.x, line.end.y = best_inter.x(), best_inter.y()
            self.sketched_changed.emit()
            self._find_closed_profiles()
        else: self.status_message.emit(tr("No extension possible"))
    
    def _line_intersection_extended(self, l1, l2):
        x1, y1, x2, y2 = l1.start.x, l1.start.y, l1.end.x, l1.end.y
        x3, y3, x4, y4 = l2.start.x, l2.start.y, l2.end.x, l2.end.y
        d = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
        if abs(d) < 1e-10: return None
        t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / d
        s = -((x1-x2)*(y1-y3) - (y1-y2)*(x1-x3)) / d
        if 0 <= s <= 1: return QPointF(x1 + t*(x2-x1), y1 + t*(y2-y1))
        return None
    
    def _point_on_line_t(self, line, pos):
        dx, dy = line.end.x-line.start.x, line.end.y-line.start.y
        l2 = dx*dx + dy*dy
        if l2 < 1e-10: return 0
        return ((pos.x()-line.start.x)*dx + (pos.y()-line.start.y)*dy) / l2
    
    def _point_at_t(self, line, t):
        return QPointF(line.start.x + t*(line.end.x-line.start.x), line.start.y + t*(line.end.y-line.start.y))
    
    def _find_connected_profile(self, start_line):
        """Findet alle zusammenhängenden Linien die ein Profil bilden"""
        TOL = 0.5
        
        def pt_match(p1, p2):
            return math.hypot(p1[0] - p2[0], p1[1] - p2[1]) < TOL
        
        def line_endpoints(l):
            return [(l.start.x, l.start.y), (l.end.x, l.end.y)]
        
        # Sammle alle nicht-Konstruktionslinien
        all_lines = [l for l in self.sketch.lines if not l.construction]
        if start_line not in all_lines:
            return [start_line]
        
        # Finde zusammenhängende Linien via BFS
        profile = [start_line]
        used = {id(start_line)}
        
        changed = True
        while changed:
            changed = False
            for line in all_lines:
                if id(line) in used:
                    continue
                
                # Prüfe ob diese Linie an eine Linie im Profil anschließt
                line_pts = line_endpoints(line)
                for profile_line in profile:
                    profile_pts = line_endpoints(profile_line)
                    for lp in line_pts:
                        for pp in profile_pts:
                            if pt_match(lp, pp):
                                profile.append(line)
                                used.add(id(line))
                                changed = True
                                break
                        if id(line) in used:
                            break
                    if id(line) in used:
                        break
        
        return profile
    
    def _polygon_to_lines(self, shapely_polygon):
        """Konvertiert ein Shapely Polygon zu Pseudo-Line Objekten für Offset"""
        from collections import namedtuple
        
        # Erstelle einfache Pseudo-Line Struktur
        PseudoPoint = namedtuple('PseudoPoint', ['x', 'y'])
        PseudoLine = namedtuple('PseudoLine', ['start', 'end'])
        
        coords = list(shapely_polygon.exterior.coords)
        lines = []
        
        for i in range(len(coords) - 1):
            p1 = coords[i]
            p2 = coords[i + 1]
            lines.append(PseudoLine(
                start=PseudoPoint(x=p1[0], y=p1[1]),
                end=PseudoPoint(x=p2[0], y=p2[1])
            ))
        
        return lines
    
    def _compute_offset_lines(self, profile_lines, distance, direction_outward=True):
        """
        Berechnet Offset-Linien für ein Profil.
        
        Args:
            profile_lines: Liste von Linien die das Profil bilden
            distance: Offset-Abstand (positiv = nach außen, negativ = nach innen)
            direction_outward: Wird ignoriert - Richtung wird durch Vorzeichen von distance bestimmt
        
        Returns:
            Liste von (x1, y1, x2, y2, orig_line) Tupeln
        """
        if not profile_lines:
            return []
        
        # Berechne Zentrum des Profils
        cx, cy = 0, 0
        count = 0
        for line in profile_lines:
            cx += line.start.x + line.end.x
            cy += line.start.y + line.end.y
            count += 2
        if count == 0:
            return []
        cx /= count
        cy /= count
        
        offset_lines = []
        for line in profile_lines:
            dx = line.end.x - line.start.x
            dy = line.end.y - line.start.y
            length = math.hypot(dx, dy)
            if length < 0.01:
                continue
            
            # Normale berechnen (senkrecht zur Linie)
            nx, ny = -dy/length, dx/length
            
            # Bestimme ob diese Normale nach außen (weg vom Zentrum) zeigt
            mid_x = (line.start.x + line.end.x) / 2
            mid_y = (line.start.y + line.end.y) / 2
            
            # Vektor vom Zentrum zur Linienmitte
            to_center_x = cx - mid_x
            to_center_y = cy - mid_y
            
            # Wenn Normale zum Zentrum zeigt, umkehren
            dot = nx * to_center_x + ny * to_center_y
            if dot > 0:
                # Normale zeigt zum Zentrum, also umkehren für "nach außen"
                nx, ny = -nx, -ny
            
            # Jetzt zeigt (nx, ny) immer nach außen
            # Positiver distance = nach außen, negativer = nach innen
            d = distance
            
            x1 = line.start.x + nx * d
            y1 = line.start.y + ny * d
            x2 = line.end.x + nx * d
            y2 = line.end.y + ny * d
            
            offset_lines.append((x1, y1, x2, y2, line))
        
        # Ecken verbinden (Linien verlängern/trimmen)
        if len(offset_lines) > 1:
            offset_lines = self._connect_offset_corners(offset_lines)
        
        return offset_lines
    
    def _connect_offset_corners(self, offset_lines):
        """Verbindet Offset-Linien an den Ecken"""
        TOL = 0.5
        
        def pt_match(x1, y1, x2, y2):
            return math.hypot(x1 - x2, y1 - y2) < TOL
        
        def line_intersection(l1, l2):
            """Berechnet Schnittpunkt zweier Linien (unendlich verlängert)"""
            x1, y1, x2, y2, _ = l1
            x3, y3, x4, y4, _ = l2
            
            denom = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
            if abs(denom) < 1e-10:
                return None
            
            t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / denom
            
            px = x1 + t*(x2-x1)
            py = y1 + t*(y2-y1)
            return (px, py)
        
        result = list(offset_lines)
        
        # Für jedes Paar von Linien die sich berühren sollten
        for i in range(len(result)):
            x1, y1, x2, y2, orig1 = result[i]
            
            for j in range(len(result)):
                if i == j:
                    continue
                
                x3, y3, x4, y4, orig2 = result[j]
                
                # Prüfe ob die Original-Linien verbunden waren
                orig_connected = False
                for p1 in [(orig1.start.x, orig1.start.y), (orig1.end.x, orig1.end.y)]:
                    for p2 in [(orig2.start.x, orig2.start.y), (orig2.end.x, orig2.end.y)]:
                        if pt_match(p1[0], p1[1], p2[0], p2[1]):
                            orig_connected = True
                            break
                    if orig_connected:
                        break
                
                if orig_connected:
                    # Finde Schnittpunkt und verbinde
                    intersection = line_intersection(result[i], result[j])
                    if intersection:
                        px, py = intersection
                        
                        # Update Endpunkte
                        # Finde welcher Endpunkt am nächsten zum Schnittpunkt ist
                        d1_start = math.hypot(x1 - px, y1 - py)
                        d1_end = math.hypot(x2 - px, y2 - py)
                        d2_start = math.hypot(x3 - px, y3 - py)
                        d2_end = math.hypot(x4 - px, y4 - py)
                        
                        # Update Linie i
                        if d1_start < d1_end:
                            result[i] = (px, py, x2, y2, orig1)
                        else:
                            result[i] = (x1, y1, px, py, orig1)
                        
                        # Update Linie j
                        if d2_start < d2_end:
                            result[j] = (px, py, x4, y4, orig2)
                        else:
                            result[j] = (x3, y3, px, py, orig2)
        
        return result
    
    def _handle_offset(self, pos, snap_type):
        """
        Offset-Tool (wie Fusion360):
        1. Klick auf Element → Sofort Vorschau mit Standard-Offset
        2. Tab → Wert eingeben → Vorschau aktualisiert live  
        3. Enter/Klick → Anwenden
        
        Positiver Offset = nach außen (größer)
        Negativer Offset = nach innen (kleiner)
        """
        
        # Schritt 1: Element auswählen
        if self.tool_step == 0:
            # Prüfe Kreis zuerst
            circle = self._find_circle_at(pos)
            if circle:
                self.offset_profile = None
                self.tool_data['offset_circle'] = circle
                self.tool_data['offset_type'] = 'circle'
                # Richtung basierend auf Klickposition
                dist = math.hypot(pos.x() - circle.center.x, pos.y() - circle.center.y)
                self.tool_data['offset_outward'] = dist > circle.radius
                self.tool_step = 1
                self._show_dimension_input()
                self._update_offset_preview()
                direction = "außen" if self.tool_data['offset_outward'] else "innen"
                self.status_message.emit(tr("Circle offset ({dir}): {d}mm | Tab=Value | Enter=Apply").format(dir=tr(direction), d=f"{self.offset_distance:.1f}"))
                return
            
            line = self._find_line_at(pos)
            if line:
                self.offset_profile = self._find_connected_profile(line)
                self.tool_data['offset_type'] = 'profile'
                self._start_offset_preview()
                return
            
            face = self._find_face_at(pos)
            if face:
                face_type = face[0]
                if face_type == 'lines':
                    self.offset_profile = face[1]
                elif face_type == 'polygon':
                    self.offset_profile = self._polygon_to_lines(face[1])
                else:
                    self.offset_profile = None
                
                if self.offset_profile:
                    self.tool_data['offset_type'] = 'profile'
                    self._start_offset_preview()
                    return
            
            self.status_message.emit(tr("Click on line, circle or face | Tab=Distance"))
        
        # Schritt 2: Bestätigen mit Klick
        elif self.tool_step == 1:
            self._apply_offset()
    
    def _offset_circle(self, circle, click_pos):
        """Offset für Kreis - sofort anwenden (legacy, wird nicht mehr verwendet)"""
        dist = math.hypot(click_pos.x() - circle.center.x, click_pos.y() - circle.center.y)
        
        # Positiver offset = größer (klick außen), negativer = kleiner (klick innen)
        if dist > circle.radius:
            new_r = circle.radius + self.offset_distance
        else:
            new_r = circle.radius - self.offset_distance
        
        if new_r > 0.01:
            self._save_undo()
            self.sketch.add_circle(circle.center.x, circle.center.y, new_r)
            self.sketched_changed.emit()
            self._find_closed_profiles()
            self.status_message.emit(tr("Circle offset: R={radius}mm").format(radius=f"{new_r:.2f}"))
    
    def _start_offset_preview(self):
        """Startet Offset-Preview und zeigt DimensionInput"""
        self.tool_step = 1
        self._show_dimension_input()
        self._update_offset_preview()
        self.status_message.emit(tr("Offset: {dist}mm | Tab=Change | Enter/Click=Apply | Esc=Cancel").format(dist=f"{self.offset_distance:+.2f}"))
    
    def _update_offset_preview(self):
        """Aktualisiert die Offset-Vorschau basierend auf offset_distance"""
        offset_type = self.tool_data.get('offset_type', 'profile')
        
        if offset_type == 'circle':
            # Kreis-Preview
            circle = self.tool_data.get('offset_circle')
            if circle:
                outward = self.tool_data.get('offset_outward', True)
                if outward:
                    new_r = circle.radius + self.offset_distance
                else:
                    new_r = circle.radius - self.offset_distance
                
                if new_r > 0.01:
                    # Preview als Pseudo-Liniensegmente (Kreis als Polygon)
                    self.offset_preview_lines = []
                    segments = 64
                    for i in range(segments):
                        a1 = 2 * math.pi * i / segments
                        a2 = 2 * math.pi * (i + 1) / segments
                        x1 = circle.center.x + new_r * math.cos(a1)
                        y1 = circle.center.y + new_r * math.sin(a1)
                        x2 = circle.center.x + new_r * math.cos(a2)
                        y2 = circle.center.y + new_r * math.sin(a2)
                        self.offset_preview_lines.append((x1, y1, x2, y2))
                else:
                    self.offset_preview_lines = []
            else:
                self.offset_preview_lines = []
        else:
            # Profil-Preview
            if not self.offset_profile:
                self.offset_preview_lines = []
                return
            
            # Berechne Offset-Linien
            offset_data = self._compute_offset_lines(self.offset_profile, self.offset_distance)
            
            self.offset_preview_lines = []
            for x1, y1, x2, y2, _ in offset_data:
                self.offset_preview_lines.append((x1, y1, x2, y2))
        
        self.update()
    
    def _apply_offset(self):
        """Wendet den aktuellen Offset an"""
        offset_type = self.tool_data.get('offset_type', 'profile')
        
        if offset_type == 'circle':
            circle = self.tool_data.get('offset_circle')
            if circle:
                outward = self.tool_data.get('offset_outward', True)
                if outward:
                    new_r = circle.radius + self.offset_distance
                else:
                    new_r = circle.radius - self.offset_distance
                
                if new_r > 0.01:
                    self._save_undo()
                    self.sketch.add_circle(circle.center.x, circle.center.y, new_r)
                    self.sketched_changed.emit()
                    self._find_closed_profiles()
                    self.status_message.emit(tr("Circle offset: R={radius}mm | Next element").format(radius=f"{new_r:.1f}"))
        else:
            if not self.offset_profile:
                self._cancel_tool()
                return
            
            self._save_undo()
            
            # Berechne finale Offset-Linien
            offset_data = self._compute_offset_lines(self.offset_profile, self.offset_distance)
            
            # Erstelle neue Linien
            created = 0
            for x1, y1, x2, y2, _ in offset_data:
                if math.hypot(x2-x1, y2-y1) > 0.01:
                    self.sketch.add_line(x1, y1, x2, y2)
                    created += 1
            
            self.sketched_changed.emit()
            self._find_closed_profiles()
            self.status_message.emit(tr("Offset applied ({count} lines) | Next element").format(count=created))
        
        # Reset
        self.offset_profile = None
        self.offset_preview_lines = []
        self.tool_step = 0
        self.tool_data = {}
        self.dim_input.hide()
        self.dim_input_active = False
    
    def _handle_fillet_2d(self, pos, snap_type):
        """Fillet: Klicke auf eine Ecke (wo zwei Linien sich treffen)"""
        r = self.snap_radius / self.view_scale
        
        # Suche Ecken (wo zwei Linien sich treffen)
        for i, l1 in enumerate(self.sketch.lines):
            for l2 in self.sketch.lines[i+1:]:
                # Prüfe alle Punkt-Kombinationen
                corners = [
                    (l1.start, l1.end, l2.start, l2.end, 'start', 'start'),
                    (l1.start, l1.end, l2.end, l2.start, 'start', 'end'),
                    (l1.end, l1.start, l2.start, l2.end, 'end', 'start'),
                    (l1.end, l1.start, l2.end, l2.start, 'end', 'end'),
                ]
                
                for corner1, other1, corner2, other2, attr1, attr2 in corners:
                    # Sind die Eckpunkte zusammen?
                    if corner1 is corner2 or math.hypot(corner1.x - corner2.x, corner1.y - corner2.y) < 1.0:
                        # Ist der Klick nah an dieser Ecke?
                        if math.hypot(corner1.x - pos.x(), corner1.y - pos.y()) < r:
                            self._save_undo()
                            success = self._create_fillet_v2(l1, l2, corner1, other1, other2, attr1, attr2, self.fillet_radius)
                            if success:
                                self.sketched_changed.emit()
                                self._find_closed_profiles()
                                self.update()
                            return
        
        self.status_message.emit(tr("No corner found") + " | " + tr("Tab=Change radius"))
    
    def _create_fillet_v2(self, l1, l2, corner, other1, other2, attr1, attr2, radius):
        """
        Erstellt ein Fillet zwischen zwei Linien.
        corner: der gemeinsame Eckpunkt
        other1/other2: die anderen Endpunkte der Linien
        attr1/attr2: 'start' oder 'end' - welcher Punkt der Eckpunkt ist
        """
        from sketcher.geometry import Point2D
        
        # Richtungsvektoren VON der Ecke WEG
        d1 = (other1.x - corner.x, other1.y - corner.y)
        d2 = (other2.x - corner.x, other2.y - corner.y)
        
        # Normalisieren
        len1 = math.hypot(d1[0], d1[1])
        len2 = math.hypot(d2[0], d2[1])
        if len1 < 0.01 or len2 < 0.01:
            self.status_message.emit(tr("Lines too short"))
            return False
        
        d1 = (d1[0]/len1, d1[1]/len1)
        d2 = (d2[0]/len2, d2[1]/len2)
        
        # Winkel zwischen den Linien (Innenwinkel)
        dot = d1[0]*d2[0] + d1[1]*d2[1]
        dot = max(-1, min(1, dot))  # Clamp für acos
        angle_between = math.acos(dot)  # Winkel in Radiant
        
        if angle_between < 0.01 or angle_between > math.pi - 0.01:
            self.status_message.emit(tr("Lines almost parallel"))
            return False
        
        # Distanz vom Eckpunkt zu den Tangentenpunkten
        half_angle = angle_between / 2
        tan_dist = radius / math.tan(half_angle)
        
        # Prüfe ob die Linien lang genug sind
        if tan_dist > len1 * 0.9 or tan_dist > len2 * 0.9:
            self.status_message.emit(tr("Radius too large (max ~{max}mm)").format(max=f"{min(len1, len2) * 0.9 * math.tan(half_angle):.1f}"))
            return False
        
        # Tangentenpunkte auf den Linien
        t1_x = corner.x + d1[0] * tan_dist
        t1_y = corner.y + d1[1] * tan_dist
        t2_x = corner.x + d2[0] * tan_dist
        t2_y = corner.y + d2[1] * tan_dist
        
        # Bogenzentrum: liegt auf der Winkelhalbierenden
        bisect = (d1[0] + d2[0], d1[1] + d2[1])
        bisect_len = math.hypot(bisect[0], bisect[1])
        if bisect_len < 0.001:
            return False
        bisect = (bisect[0]/bisect_len, bisect[1]/bisect_len)
        
        center_dist = radius / math.sin(half_angle)
        center_x = corner.x + bisect[0] * center_dist
        center_y = corner.y + bisect[1] * center_dist
        
        # WICHTIG: Bei geteilten Punkten müssen wir neue Punkte erstellen!
        # Prüfe ob die Linien denselben Eckpunkt teilen
        l1_corner = l1.start if attr1 == 'start' else l1.end
        l2_corner = l2.start if attr2 == 'start' else l2.end
        
        if l1_corner is l2_corner:
            # Geteilter Punkt - erstelle neue separate Punkte
            new_pt1 = Point2D(t1_x, t1_y)
            new_pt2 = Point2D(t2_x, t2_y)
            self.sketch.points.append(new_pt1)
            self.sketch.points.append(new_pt2)
            
            # Linien mit neuen Punkten aktualisieren
            if attr1 == 'start':
                l1.start = new_pt1
            else:
                l1.end = new_pt1
                
            if attr2 == 'start':
                l2.start = new_pt2
            else:
                l2.end = new_pt2
                
            # Alten geteilten Punkt aus points entfernen (wenn nicht mehr verwendet)
            # (Wir lassen ihn erstmal, cleanup passiert später)
        else:
            # Nicht geteilte Punkte - direkt modifizieren
            if attr1 == 'start':
                l1.start.x, l1.start.y = t1_x, t1_y
            else:
                l1.end.x, l1.end.y = t1_x, t1_y
                
            if attr2 == 'start':
                l2.start.x, l2.start.y = t2_x, t2_y
            else:
                l2.end.x, l2.end.y = t2_x, t2_y
        
        # Bogenwinkel berechnen
        angle1 = math.degrees(math.atan2(t1_y - center_y, t1_x - center_x))
        angle2 = math.degrees(math.atan2(t2_y - center_y, t2_x - center_x))
        
        # Bogen erstellen (von t1 nach t2, kürzester Weg)
        self.sketch.add_arc(center_x, center_y, radius, angle1, angle2)
        
        self.status_message.emit(tr("Fillet R={radius}mm created").format(radius=f"{radius:.1f}"))
        return True
    
    def _handle_chamfer_2d(self, pos, snap_type):
        """Chamfer: Klicke auf eine Ecke (wo zwei Linien sich treffen)"""
        r = self.snap_radius / self.view_scale
        
        # Suche Ecken (wo zwei Linien sich treffen)
        for i, l1 in enumerate(self.sketch.lines):
            for l2 in self.sketch.lines[i+1:]:
                # Prüfe alle Punkt-Kombinationen
                corners = [
                    (l1.start, l1.end, l2.start, l2.end, 'start', 'start'),
                    (l1.start, l1.end, l2.end, l2.start, 'start', 'end'),
                    (l1.end, l1.start, l2.start, l2.end, 'end', 'start'),
                    (l1.end, l1.start, l2.end, l2.start, 'end', 'end'),
                ]
                
                for corner1, other1, corner2, other2, attr1, attr2 in corners:
                    # Sind die Eckpunkte zusammen?
                    if corner1 is corner2 or math.hypot(corner1.x - corner2.x, corner1.y - corner2.y) < 1.0:
                        # Ist der Klick nah an dieser Ecke?
                        if math.hypot(corner1.x - pos.x(), corner1.y - pos.y()) < r:
                            self._save_undo()
                            success = self._create_chamfer_v2(l1, l2, corner1, other1, other2, attr1, attr2, self.chamfer_distance)
                            if success:
                                self.sketched_changed.emit()
                                self._find_closed_profiles()
                                self.update()
                            return
        
        self.status_message.emit(tr("No corner found") + " | " + tr("Tab=Change length"))
    
    def _create_chamfer_v2(self, l1, l2, corner, other1, other2, attr1, attr2, dist):
        """
        Erstellt eine Fase zwischen zwei Linien.
        corner: der gemeinsame Eckpunkt
        other1/other2: die anderen Endpunkte der Linien
        attr1/attr2: 'start' oder 'end' - welcher Punkt der Eckpunkt ist
        """
        from sketcher.geometry import Point2D
        
        # Richtungsvektoren VON der Ecke WEG
        d1 = (other1.x - corner.x, other1.y - corner.y)
        d2 = (other2.x - corner.x, other2.y - corner.y)
        
        # Normalisieren
        len1 = math.hypot(d1[0], d1[1])
        len2 = math.hypot(d2[0], d2[1])
        if len1 < 0.01 or len2 < 0.01:
            self.status_message.emit(tr("Lines too short"))
            return False
        
        d1 = (d1[0]/len1, d1[1]/len1)
        d2 = (d2[0]/len2, d2[1]/len2)
        
        # Prüfe ob die Linien lang genug sind
        if dist > len1 * 0.9 or dist > len2 * 0.9:
            self.status_message.emit(tr("Chamfer too large (max ~{max}mm)").format(max=f"{min(len1, len2) * 0.9:.1f}"))
            return False
        
        # Neue Endpunkte (wo die Fase anfängt)
        c1_x = corner.x + d1[0] * dist
        c1_y = corner.y + d1[1] * dist
        c2_x = corner.x + d2[0] * dist
        c2_y = corner.y + d2[1] * dist
        
        # WICHTIG: Bei geteilten Punkten müssen wir neue Punkte erstellen!
        l1_corner = l1.start if attr1 == 'start' else l1.end
        l2_corner = l2.start if attr2 == 'start' else l2.end
        
        if l1_corner is l2_corner:
            # Geteilter Punkt - erstelle neue separate Punkte
            new_pt1 = Point2D(c1_x, c1_y)
            new_pt2 = Point2D(c2_x, c2_y)
            self.sketch.points.append(new_pt1)
            self.sketch.points.append(new_pt2)
            
            # Linien mit neuen Punkten aktualisieren
            if attr1 == 'start':
                l1.start = new_pt1
            else:
                l1.end = new_pt1
                
            if attr2 == 'start':
                l2.start = new_pt2
            else:
                l2.end = new_pt2
        else:
            # Nicht geteilte Punkte - direkt modifizieren
            if attr1 == 'start':
                l1.start.x, l1.start.y = c1_x, c1_y
            else:
                l1.end.x, l1.end.y = c1_x, c1_y
                
            if attr2 == 'start':
                l2.start.x, l2.start.y = c2_x, c2_y
            else:
                l2.end.x, l2.end.y = c2_x, c2_y
        
        # Fase-Linie hinzufügen
        self.sketch.add_line(c1_x, c1_y, c2_x, c2_y)
        
        self.status_message.emit(tr("Chamfer L={length}mm created").format(length=f"{dist:.1f}"))
        return True
    
    def _handle_dimension(self, pos, snap_type):
        line = self._find_line_at(pos)
        if line:
            val, ok = QInputDialog.getDouble(self, "Länge", "Länge (mm):", line.length, 0.01, 10000, 2)
            if ok:
                self._save_undo()
                self.sketch.add_length(line, val)
                result = self.sketch.solve()
                self.sketched_changed.emit()
                self._find_closed_profiles()
                self.update()
                if hasattr(result, 'success') and result.success:
                    self.status_message.emit(tr("Length {val}mm set (DOF: {dof})").format(val=f"{val:.1f}", dof=getattr(result, "dof", -1)))
            return
        circle = self._find_circle_at(pos)
        if circle:
            val, ok = QInputDialog.getDouble(self, "Radius", "Radius (mm):", circle.radius, 0.01, 10000, 2)
            if ok:
                self._save_undo()
                self.sketch.add_radius(circle, val)
                result = self.sketch.solve()
                self.sketched_changed.emit()
                self._find_closed_profiles()
                self.update()
                if hasattr(result, 'success') and result.success:
                    self.status_message.emit(tr("Radius {val}mm set (DOF: {dof})").format(val=f"{val:.1f}", dof=getattr(result, "dof", -1)))
            return
        self.status_message.emit(tr("Select first line") + "/" + tr("Circle"))
    
    def _handle_dimension_angle(self, pos, snap_type):
        line = self._find_line_at(pos)
        if not line: self.status_message.emit(tr("Select first line")); return
        if self.tool_step == 0:
            self.tool_data['line1'] = line; self.tool_step = 1
            self.status_message.emit(tr("Select second line"))
        else:
            l1 = self.tool_data.get('line1')
            if l1 and line != l1:
                current = abs(l1.angle - line.angle)
                if current > 180: current = 360 - current
                val, ok = QInputDialog.getDouble(self, "Winkel", "Winkel (°):", current, 0, 180, 2)
                if ok:
                    self._save_undo()
                    self.sketch.add_angle(l1, line, val)
                    result = self.sketch.solve()
                    self.sketched_changed.emit()
                    self._find_closed_profiles()
                    self.update()
                    if hasattr(result, 'success') and result.success:
                        self.status_message.emit(tr("Angle {val}° set (DOF: {dof})").format(val=f"{val:.1f}", dof=getattr(result, "dof", -1)))
            self._cancel_tool()
    
    def _handle_horizontal(self, pos, snap_type):
        line = self._find_line_at(pos)
        if line:
            self._save_undo()
            # Automatisch nahe Punkte vereinen (wie Fusion360)
            self._merge_nearby_endpoints(line)
            self.sketch.add_horizontal(line)
            result = self.sketch.solve()
            self.sketched_changed.emit()
            self._find_closed_profiles()
            self.update()
            if hasattr(result, 'success') and result.success:
                self.status_message.emit(tr("Horizontal constraint applied (DOF: {dof})").format(dof=getattr(result, "dof", -1)))
            else:
                self.status_message.emit(tr("Horizontal constraint added"))
        else: self.status_message.emit(tr("Select first line"))
    
    def _handle_vertical(self, pos, snap_type):
        line = self._find_line_at(pos)
        if line:
            self._save_undo()
            # Automatisch COINCIDENT Constraints für nahe Punkte hinzufügen
            self._ensure_coincident_for_line(line)
            self.sketch.add_vertical(line)
            result = self.sketch.solve()
            self.sketched_changed.emit()
            self._find_closed_profiles()
            self.update()
            if hasattr(result, 'success') and result.success:
                self.status_message.emit(tr("Vertical constraint applied (DOF: {dof})").format(dof=getattr(result, "dof", -1)))
            else:
                self.status_message.emit(tr("Vertical constraint added"))
        else: self.status_message.emit(tr("Select first line"))
    
    def _ensure_coincident_for_line(self, line, tolerance=1.0):
        """Alte Funktion - verwende _merge_nearby_endpoints stattdessen"""
        self._merge_nearby_endpoints(line, tolerance)
    
    def _merge_nearby_endpoints(self, line, tolerance=1.0):
        """
        Vereint nahe Punkte mit existierenden Punkten (wie Fusion360).
        Ersetzt Linien-Endpunkte durch existierende Punkte wenn sie nah genug sind.
        """
        for attr in ['start', 'end']:
            pt = getattr(line, attr)
            
            # Suche nahe Punkte in anderen Linien
            for other_line in self.sketch.lines:
                if other_line == line:
                    continue
                    
                for other_attr in ['start', 'end']:
                    other_pt = getattr(other_line, other_attr)
                    
                    if pt is other_pt:
                        continue  # Bereits der gleiche Punkt
                    
                    dist = math.hypot(pt.x - other_pt.x, pt.y - other_pt.y)
                    
                    if dist < tolerance and dist > 0.001:
                        # Nahe Punkte gefunden - Punkt ersetzen!
                        setattr(line, attr, other_pt)
                        
                        # Auch in sketch.points bereinigen
                        if pt in self.sketch.points:
                            self.sketch.points.remove(pt)
                        
                        # Fertig für diesen Endpunkt
                        break
    
    def _handle_parallel(self, pos, snap_type):
        line = self._find_line_at(pos)
        if not line: self.status_message.emit(tr("Select first line")); return
        if self.tool_step == 0:
            self.tool_data['line1'] = line; self.tool_step = 1
            self.status_message.emit(tr("Select second line"))
        else:
            l1 = self.tool_data.get('line1')
            if l1 and line != l1:
                self._save_undo()
                self.sketch.add_parallel(l1, line)
                result = self.sketch.solve()
                self.sketched_changed.emit()
                self._find_closed_profiles()
                self.update()
                if hasattr(result, 'success') and result.success:
                    self.status_message.emit(tr("Parallel constraint applied (DOF: {dof})").format(dof=getattr(result, "dof", -1)))
            self._cancel_tool()
    
    def _handle_perpendicular(self, pos, snap_type):
        line = self._find_line_at(pos)
        if not line: self.status_message.emit(tr("Select first line")); return
        if self.tool_step == 0:
            self.tool_data['line1'] = line; self.tool_step = 1
            self.status_message.emit(tr("Select second line"))
        else:
            l1 = self.tool_data.get('line1')
            if l1 and line != l1:
                self._save_undo()
                self.sketch.add_perpendicular(l1, line)
                result = self.sketch.solve()
                self.sketched_changed.emit()
                self._find_closed_profiles()
                self.update()
                if hasattr(result, 'success') and result.success:
                    self.status_message.emit(tr("Perpendicular constraint applied (DOF: {dof})").format(dof=getattr(result, "dof", -1)))
            self._cancel_tool()
    
    def _handle_equal(self, pos, snap_type):
        line = self._find_line_at(pos)
        if not line: self.status_message.emit(tr("Select first line")); return
        if self.tool_step == 0:
            self.tool_data['line1'] = line; self.tool_step = 1
            self.status_message.emit(tr("Select second line"))
        else:
            l1 = self.tool_data.get('line1')
            if l1 and line != l1:
                self._save_undo()
                self.sketch.add_equal_length(l1, line)
                result = self.sketch.solve()
                self.sketched_changed.emit()
                self._find_closed_profiles()
                self.update()
                if hasattr(result, 'success') and result.success:
                    self.status_message.emit(tr("Equal constraint applied (DOF: {dof})").format(dof=getattr(result, "dof", -1)))
            self._cancel_tool()
    
    def _handle_concentric(self, pos, snap_type):
        circle = self._find_circle_at(pos)
        if not circle: self.status_message.emit(tr("Select first circle")); return
        if self.tool_step == 0:
            self.tool_data['circle1'] = circle; self.tool_step = 1
            self.status_message.emit(tr("Select second circle"))
        else:
            c1 = self.tool_data.get('circle1')
            if c1 and circle != c1:
                self._save_undo()
                circle.center.x, circle.center.y = c1.center.x, c1.center.y
                result = self.sketch.solve()
                self.sketched_changed.emit()
                self._find_closed_profiles()
                self.update()
                if hasattr(result, 'success') and result.success:
                    self.status_message.emit(tr("Concentric constraint applied (DOF: {dof})").format(dof=getattr(result, "dof", -1)))
            self._cancel_tool()
    
    def _handle_tangent(self, pos, snap_type):
        """Tangent Constraint: Linie tangential an Kreis oder Kreis tangential an Kreis"""
        line = self._find_line_at(pos)
        circle = self._find_circle_at(pos)
        
        if self.tool_step == 0:
            if line:
                self.tool_data['elem1'] = ('line', line)
                self.tool_step = 1
                self.status_message.emit(tr("Line selected - now select circle"))
            elif circle:
                self.tool_data['elem1'] = ('circle', circle)
                self.tool_step = 1
                self.status_message.emit(tr("Circle selected - now select line or circle"))
            else:
                self.status_message.emit(tr("Select line or circle"))
        else:
            elem1_type, elem1 = self.tool_data.get('elem1', (None, None))
            
            if elem1_type == 'line' and circle:
                # Linie tangential an Kreis machen
                self._save_undo()
                self._make_line_tangent_to_circle(elem1, circle)
                result = self.sketch.solve()
                self.sketched_changed.emit()
                self._find_closed_profiles()
                self.update()
                self.status_message.emit(tr("Tangent constraint applied"))
            elif elem1_type == 'circle' and line:
                # Linie tangential an Kreis machen
                self._save_undo()
                self._make_line_tangent_to_circle(line, elem1)
                result = self.sketch.solve()
                self.sketched_changed.emit()
                self._find_closed_profiles()
                self.update()
                self.status_message.emit(tr("Tangent constraint applied"))
            elif elem1_type == 'circle' and circle and circle != elem1:
                # Zwei Kreise tangential machen
                self._save_undo()
                self._make_circles_tangent(elem1, circle)
                result = self.sketch.solve()
                self.sketched_changed.emit()
                self._find_closed_profiles()
                self.update()
                self.status_message.emit(tr("Circles tangent"))
            else:
                self.status_message.emit(tr("Invalid combination"))
            
            self._cancel_tool()
    
    def _make_line_tangent_to_circle(self, line, circle):
        """Macht eine Linie tangential zu einem Kreis"""
        # Berechne den nächsten Punkt auf der Linie zum Kreismittelpunkt
        cx, cy = circle.center.x, circle.center.y
        x1, y1 = line.start.x, line.start.y
        x2, y2 = line.end.x, line.end.y
        
        # Linienrichtung
        dx, dy = x2 - x1, y2 - y1
        line_len = math.hypot(dx, dy)
        if line_len < 0.001:
            return
        
        # Projektion des Kreismittelpunkts auf die Linie
        t = ((cx - x1) * dx + (cy - y1) * dy) / (line_len * line_len)
        t = max(0, min(1, t))  # Auf Liniensegment begrenzen
        
        # Nächster Punkt auf der Linie
        px, py = x1 + t * dx, y1 + t * dy
        
        # Aktuelle Distanz zum Kreis
        dist = math.hypot(px - cx, py - cy)
        
        if dist < 0.001:
            return
        
        # Verschiebe die Linie so dass sie tangential ist
        # Richtung vom Mittelpunkt zum nächsten Punkt
        nx, ny = (px - cx) / dist, (py - cy) / dist
        
        # Zielabstand = Radius
        offset = circle.radius - dist
        
        # Verschiebe beide Endpunkte
        line.start.x += nx * offset
        line.start.y += ny * offset
        line.end.x += nx * offset
        line.end.y += ny * offset
    
    def _make_circles_tangent(self, c1, c2):
        """Macht zwei Kreise tangential (berührend)"""
        cx1, cy1, r1 = c1.center.x, c1.center.y, c1.radius
        cx2, cy2, r2 = c2.center.x, c2.center.y, c2.radius
        
        # Aktuelle Distanz
        dist = math.hypot(cx2 - cx1, cy2 - cy1)
        if dist < 0.001:
            return
        
        # Richtung von c1 nach c2
        dx, dy = (cx2 - cx1) / dist, (cy2 - cy1) / dist
        
        # Zieldistanz (außen tangent)
        target_dist = r1 + r2
        
        # Verschiebe c2
        c2.center.x = cx1 + dx * target_dist
        c2.center.y = cy1 + dy * target_dist
    
    def _handle_pattern_linear(self, pos, snap_type):
        if not self.selected_lines and not self.selected_circles and not self.selected_arcs:
            self.status_message.emit(tr("Select elements first!")); return
        try:
            from gui.generators import PatternDialog
            dialog = PatternDialog("linear", self)
            if dialog.exec():
                params = dialog.get_params()
                self._save_undo()
                angle_rad = math.radians(params["angle"])
                dx, dy = math.cos(angle_rad) * params["spacing"], math.sin(angle_rad) * params["spacing"]
                for i in range(1, params["count"]):
                    ox, oy = dx * i, dy * i
                    for line in self.selected_lines:
                        self.sketch.add_line(line.start.x+ox, line.start.y+oy, line.end.x+ox, line.end.y+oy, construction=line.construction)
                    for circle in self.selected_circles:
                        self.sketch.add_circle(circle.center.x+ox, circle.center.y+oy, circle.radius, construction=circle.construction)
                self.sketched_changed.emit()
                self._find_closed_profiles()
                self._cancel_tool()
        except: pass
    
    def _handle_pattern_circular(self, pos, snap_type):
        if not self.selected_lines and not self.selected_circles and not self.selected_arcs:
            self.status_message.emit(tr("Select elements first!")); return
        if self.tool_step == 0:
            self.tool_points = [pos]; self.tool_step = 1
            self.status_message.emit(tr("Center selected - click for dialog")); return
        try:
            from gui.generators import PatternDialog
            center = self.tool_points[0]
            dialog = PatternDialog("circular", self)
            if dialog.exec():
                params = dialog.get_params()
                self._save_undo()
                for i in range(1, params["count"]):
                    angle = math.radians(params["total_angle"] * i / params["count"])
                    cos_a, sin_a = math.cos(angle), math.sin(angle)
                    for line in self.selected_lines:
                        dx1, dy1 = line.start.x - center.x(), line.start.y - center.y()
                        dx2, dy2 = line.end.x - center.x(), line.end.y - center.y()
                        self.sketch.add_line(center.x()+dx1*cos_a-dy1*sin_a, center.y()+dx1*sin_a+dy1*cos_a,
                                            center.x()+dx2*cos_a-dy2*sin_a, center.y()+dx2*sin_a+dy2*cos_a, construction=line.construction)
                    for circle in self.selected_circles:
                        dx, dy = circle.center.x - center.x(), circle.center.y - center.y()
                        self.sketch.add_circle(center.x()+dx*cos_a-dy*sin_a, center.y()+dx*sin_a+dy*cos_a, circle.radius, construction=circle.construction)
                self.sketched_changed.emit()
                self._find_closed_profiles()
        except: pass
        self._cancel_tool()
    
    def _handle_gear(self, pos, snap_type):
        try:
            from gui.generators import GearDialog, generate_simple_gear
            dialog = GearDialog(self)
            if dialog.exec():
                params = dialog.get_params()
                self._save_undo()
                points = generate_simple_gear(params.teeth, params.module, (pos.x(), pos.y()))
                self.sketch.add_polygon(points, closed=True)
                if params.center_hole > 0:
                    self.sketch.add_circle(pos.x(), pos.y(), params.center_hole / 2)
                self.sketch.solve()
                self.sketched_changed.emit()
                self._find_closed_profiles()
        except: pass
    
    def _handle_star(self, pos, snap_type):
        try:
            from gui.generators import StarDialog, generate_star
            dialog = StarDialog(self)
            if dialog.exec():
                points_count, outer_r, inner_r = dialog.get_params()
                self._save_undo()
                points = generate_star(points_count, outer_r, inner_r, (pos.x(), pos.y()))
                self.sketch.add_polygon(points, closed=True)
                self.sketch.solve()
                self.sketched_changed.emit()
                self._find_closed_profiles()
        except: pass
    
    def _handle_nut(self, pos, snap_type):
        """Erstellt eine Sechskant-Muttern-Aussparung (M2-M14) mit Schraubenloch - 2 Schritte wie Polygon"""
        if self.tool_step == 0:
            # Schritt 1: Position setzen
            self.tool_points = [pos]
            self.tool_step = 1
            size_name = self.nut_size_names[self.nut_size_index]
            self.status_message.emit(f"{size_name} " + tr("Nut") + " | " + tr("Rotate with mouse | Click to place"))
        else:
            # Schritt 2: Rotation bestimmen und erstellen
            center = self.tool_points[0]
            rotation_angle = math.atan2(pos.y() - center.y(), pos.x() - center.x())
            
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
            self._cancel_tool()
    
    def _handle_text(self, pos, snap_type):
        text, ok = QInputDialog.getText(self, "Text", "Text eingeben:")
        if ok and text:
            self._save_undo()
            self.sketch.add_rectangle(pos.x(), pos.y(), len(text) * 6, 10)
            self.status_message.emit(tr("Text") + f" '{text}' (" + tr("placeholder") + ")")
            self.sketched_changed.emit()
            self._find_closed_profiles()
    
    def _handle_point(self, pos, snap_type):
        """Erstellt einen Konstruktionspunkt"""
        self._save_undo()
        self.sketch.add_point(pos.x(), pos.y(), construction=self.construction_mode)
        self.sketched_changed.emit()
        self.status_message.emit(tr("Point") + f" ({pos.x():.1f}, {pos.y():.1f})")
    
    def _apply_constraint(self, ctype):
        if not self.selected_lines: return
        self._save_undo()
        for l in self.selected_lines:
            if ctype == 'horizontal': self.sketch.add_horizontal(l)
            elif ctype == 'vertical': self.sketch.add_vertical(l)
        self.sketch.solve()
        self.sketched_changed.emit()
        self.update()
    
