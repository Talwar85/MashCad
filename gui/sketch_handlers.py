"""
MashCad - Sketch Handlers Mixin
All _handle_* methods for sketch tools
Extracted from sketch_editor.py for better maintainability
"""

import math
import sys
import os
from loguru import logger
from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import QColor, QTransform, QPainterPath, QFont, QFontMetrics
from PySide6.QtWidgets import (QApplication, QInputDialog, QDialog, QVBoxLayout, 
                               QFormLayout, QLineEdit, QDialogButtonBox, QDoubleSpinBox, 
                               QFontComboBox, QWidget, QLabel, QSpinBox, QCheckBox)

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



try:
    import sketcher.geometry as geometry
except ImportError:
    import geometry


from sketcher.sketch import Sketch

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
    
    def _handle_line(self, pos, snap_type, snap_entity=None):
        """
        Erstellt Linien und nutzt die existierenden Constraint-Methoden des Sketch-Objekts.
        """
        # Schritt 1: Startpunkt setzen
        if self.tool_step == 0:
            self.tool_points = [pos]
            self.tool_step = 1
            self.status_message.emit("Endpunkt wählen | Tab=Länge/Winkel | Rechts=Fertig")
        
        # Schritt 2: Endpunkt setzen und Linie erstellen
        else:
            start = self.tool_points[-1]
            dx = pos.x() - start.x()
            dy = pos.y() - start.y()
            length = math.hypot(dx, dy)

            if length > 0.01:
                self._save_undo()
                
                # Linie erstellen (wie in deinem Original)
                line = self.sketch.add_line(start.x(), start.y(), pos.x(), pos.y(), construction=self.construction_mode)

                # --- A. Auto-Constraints: Horizontal / Vertikal ---
                # Wir nutzen hier deine existierenden Methoden add_horizontal/vertical
                h_tolerance = 3.0
                
                # Nur prüfen, wenn wir nicht explizit an einer Kante snappen (um Konflikte zu vermeiden)
                if snap_type not in [SnapType.EDGE, SnapType.INTERSECTION]:
                    if abs(dy) < h_tolerance and abs(dx) > h_tolerance:
                        if hasattr(self.sketch, 'add_horizontal'):
                            self.sketch.add_horizontal(line)
                            self.status_message.emit("Auto: Horizontal")
                            
                    elif abs(dx) < h_tolerance and abs(dy) > h_tolerance:
                        if hasattr(self.sketch, 'add_vertical'):
                            self.sketch.add_vertical(line)
                            self.status_message.emit("Auto: Vertical")

                # --- B. Auto-Constraints: Verbindungen (Das neue Snapping) ---
                # Statt über alle Linien zu loopen, nutzen wir das snap_entity direkt!
                
                if snap_entity and snap_type == SnapType.EDGE:
                    
                    # 1. Verbindung mit LINIE
                    if hasattr(snap_entity, 'start'): 
                        # Verhindern, dass wir die Linie an sich selbst kleben
                        if snap_entity != line:
                            # Nutze deine existierende Methode!
                            if hasattr(self.sketch, 'add_point_on_line'):
                                self.sketch.add_point_on_line(line.end, snap_entity)
                                self.status_message.emit("Auto: Punkt auf Linie")
                    
                    # 2. Verbindung mit KREIS (Das fehlte vorher!)
                    elif hasattr(snap_entity, 'radius'):
                        # Prüfen ob du add_point_on_circle hast, sonst manuell
                        if hasattr(self.sketch, 'add_point_on_circle'):
                            self.sketch.add_point_on_circle(line.end, snap_entity)
                            self.status_message.emit("Auto: Punkt auf Kreis")
                        else:
                            # Fallback: Direktes Einfügen, falls die Methode fehlt
                            try:
                                from constraints import Constraint, ConstraintType
                                c = Constraint(ConstraintType.POINT_ON_CIRCLE, [line.end, snap_entity])
                                self.sketch.constraints.append(c)
                                self.status_message.emit("Auto: Punkt auf Kreis (Manuell)")
                            except Exception as e:
                                print(f"Konnte Kreis-Constraint nicht erstellen: {e}")

                # --- C. Abschluss ---
                self._solve_async() 
                self._find_closed_profiles()
                self.sketched_changed.emit()
                
                # Poly-Line Modus
                self.tool_points.append(pos)
    
    def _handle_rectangle(self, pos, snap_type):
        """Rechteck mit Modus-Unterstützung (0=2-Punkt, 1=Center) und Auto-Constraints"""
        
        # Berechnung der Geometrie basierend auf dem Modus
        if self.rect_mode == 1:
            # Center-Modus
            if self.tool_step == 0:
                self.tool_points = [pos]
                self.tool_step = 1
                self.status_message.emit(tr("Corner | Tab=Width/Height"))
                return
            else:
                c = self.tool_points[0]
                w = abs(pos.x() - c.x()) * 2
                h = abs(pos.y() - c.y()) * 2
                x = c.x() - w / 2
                y = c.y() - h / 2
        else:
            # 2-Punkt-Modus (Standard)
            if self.tool_step == 0:
                self.tool_points = [pos]
                self.tool_step = 1
                self.status_message.emit(tr("Opposite corner | Tab=Width/Height"))
                return
            else:
                p1, p2 = self.tool_points[0], pos
                x = min(p1.x(), p2.x())
                y = min(p1.y(), p2.y())
                w = abs(p2.x() - p1.x())
                h = abs(p2.y() - p1.y())

        # Erstellung und Bemaßung
        if w > 0.01 and h > 0.01:
            self._save_undo()
            
            # 1. Rechteck erstellen (gibt [Unten, Rechts, Oben, Links] zurück)
            # Hinweis: add_rectangle muss in sketch.py return [l1, l2, l3, l4] haben!
            lines = self.sketch.add_rectangle(x, y, w, h, construction=self.construction_mode)
            
            # 2. Automatische Bemaßung hinzufügen (Constraints)
            # Wir bemaßen die untere Linie (Breite) und die linke Linie (Höhe)
            if lines and len(lines) >= 4:
                # Breite (Index 0 = Unten)
                self.sketch.add_length(lines[0], w)
                # Höhe (Index 3 = Links)
                self.sketch.add_length(lines[3], h)

            # 3. Lösen & Update
            self._solve_async() # Thread start
            self._find_closed_profiles() # Immediate visual feedback (pre-solve)
            self.sketched_changed.emit()
            
        self._cancel_tool()
    
    def _handle_circle(self, pos, snap_type):
        """Kreis mit Modus-Unterstützung (0=Center-Radius, 1=2-Punkt, 2=3-Punkt) und Auto-Constraints"""
        if self.circle_mode == 1:
            # === 2-Punkt-Modus (Durchmesser) ===
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
                    # 1. Kreis erstellen
                    circle = self.sketch.add_circle(cx, cy, r, construction=self.construction_mode)
                    # 2. Radius Constraint hinzufügen
                    self.sketch.add_radius(circle, r)
                    # 3. Solver
                    self._solve_async() # Thread start
                    self._find_closed_profiles() # Immediate visual feedback (pre-solve)
                    self.sketched_changed.emit()
                self._cancel_tool()
                
        elif self.circle_mode == 2:
            # === 3-Punkt-Modus ===
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
                    # 1. Kreis erstellen
                    circle = self.sketch.add_circle(center.x(), center.y(), r, construction=self.construction_mode)
                    # 2. Radius Constraint hinzufügen (fixiert die Größe)
                    self.sketch.add_radius(circle, r)
                    # 3. Solver
                    self._solve_async() # Thread start
                    self._find_closed_profiles() # Immediate visual feedback (pre-solve)
                    self.sketched_changed.emit()
                self._cancel_tool()
                
        else:
            # === Center-Radius-Modus (Standard) ===
            if self.tool_step == 0:
                self.tool_points = [pos]
                self.tool_step = 1
                self.status_message.emit(tr("Radius | Tab=Input"))
            else:
                c = self.tool_points[0]
                r = math.hypot(pos.x()-c.x(), pos.y()-c.y())
                
                if r > 0.01:
                    self._save_undo()
                    # 1. Kreis erstellen
                    circle = self.sketch.add_circle(c.x(), c.y(), r, construction=self.construction_mode)
                    # 2. Radius Constraint hinzufügen
                    self.sketch.add_radius(circle, r)
                    # 3. Solver
                    self._solve_async() # Thread start
                    self._find_closed_profiles() # Immediate visual feedback (pre-solve)
                    self.sketched_changed.emit()
                self._cancel_tool()

    def _calc_circle_3points(self, p1, p2, p3):
        """Berechnet Mittelpunkt und Radius eines Kreises durch 3 Punkte"""
        x1, y1 = p1.x(), p1.y()
        x2, y2 = p2.x(), p2.y()
        x3, y3 = p3.x(), p3.y()
        
        # Determinante für Kollinearitäts-Check
        d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
        if abs(d) < 1e-10:
            return None, 0  # Punkte sind kollinear (liegen auf einer Linie)
        
        # Mittelpunkt berechnen (Umkreisformel)
        ux = ((x1*x1 + y1*y1) * (y2 - y3) + (x2*x2 + y2*y2) * (y3 - y1) + (x3*x3 + y3*y3) * (y1 - y2)) / d
        uy = ((x1*x1 + y1*y1) * (x3 - x2) + (x2*x2 + y2*y2) * (x1 - x3) + (x3*x3 + y3*y3) * (x2 - x1)) / d
        
        # Radius berechnen
        r = math.hypot(x1 - ux, y1 - uy)
        
        return QPointF(ux, uy), r
    
    def _handle_circle_2point(self, pos, snap_type):
        """Separater Handler für reinen 2-Punkt-Modus (falls als eigenes Tool genutzt)"""
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
                circle = self.sketch.add_circle(cx, cy, r, construction=self.construction_mode)
                self.sketch.add_radius(circle, r)  # <--- Constraint
                self.sketch.solve()                # <--- Solve
                self.sketched_changed.emit()
                self._find_closed_profiles()
            self._cancel_tool()
    
    def _handle_polygon(self, pos, snap_type):
        """Erstellt ein parametrisches Polygon"""
        if self.tool_step == 0:
            # Erster Klick: Zentrum
            self.tool_points = [pos]
            self.tool_step = 1
            # Info-Text aktualisieren
            self.status_message.emit(tr("Radius") + f" ({self.polygon_sides} " + tr("sides") + ") | Tab")
        
        else:
            # Zweiter Klick: Radius und Rotation
            c = self.tool_points[0]
            
            # Aktueller Radius und Winkel der Maus
            r = math.hypot(pos.x() - c.x(), pos.y() - c.y())
            angle = math.atan2(pos.y() - c.y(), pos.x() - c.x())
            
            if r > 0.01:
                self._save_undo()
                
                # 1. Parametrisches Polygon erstellen (ruft unsere neue Methode auf)
                lines, const_circle = self.sketch.add_regular_polygon(
                    c.x(), c.y(), r, 
                    self.polygon_sides, 
                    angle_offset=angle, 
                    construction=self.construction_mode
                )
                
                # 2. Radius-Bemaßung hinzufügen
                # Das erlaubt dir, den Radius später per Doppelklick zu ändern!
                self.sketch.add_radius(const_circle, r)
                
                # 3. Lösen
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
                self._find_closed_profiles()
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
        """
        Handler für das Langloch-Werkzeug.
        Ablauf: 
        1. Klick: Startpunkt der Mittellinie
        2. Klick: Endpunkt der Mittellinie
        3. Klick: Radius (Breite) festlegen
        """
        
        # --- Schritt 1: Startpunkt ---
        if self.tool_step == 0:
            self.tool_points = [pos]
            self.tool_step = 1
            self.status_message.emit(tr("Endpoint center line | Tab=Length/Angle"))
            
        # --- Schritt 2: Endpunkt der Mittellinie ---
        elif self.tool_step == 1:
            self.tool_points.append(pos)
            self.tool_step = 2
            self.status_message.emit(tr("Width | Tab=Enter width"))
            
        # --- Schritt 3: Breite/Radius und Erstellung ---
        else:
            p1 = self.tool_points[0]
            p2 = self.tool_points[1]
            
            # Vektor der Mittellinie berechnen
            dx_line = p2.x() - p1.x()
            dy_line = p2.y() - p1.y()
            length = math.hypot(dx_line, dy_line)
            
            # Verhindern von Null-Längen
            if length > 0.01:
                # Radius berechnen (Senkrechter Abstand Maus zur Mittellinie)
                
                # 1. Normalisierter Richtungsvektor der Linie (Einheitsvektor)
                ux = dx_line / length
                uy = dy_line / length
                
                # 2. Normalenvektor dazu (-y, x)
                nx, ny = -uy, ux
                
                # 3. Vektor vom Startpunkt zur Maus
                vx = pos.x() - p1.x()
                vy = pos.y() - p1.y()
                
                # 4. Skalarprodukt mit der Normalen ergibt den Abstand (Radius)
                radius = abs(vx * nx + vy * ny)
                
                # Nur erstellen, wenn Radius sinnvoll ist
                if radius > 0.01:
                    self._save_undo()
                    
                    # A. Robustes Slot erstellen (ruft die Methode in sketch.py auf)
                    # WICHTIG: add_slot muss (center_line, main_arc) zurückgeben!
                    center_line, main_arc = self.sketch.add_slot(
                        p1.x(), p1.y(), p2.x(), p2.y(), radius, 
                        construction=self.construction_mode
                    )
                    
                    # B. Bemaßungen hinzufügen (Constraints)
                    
                    # 1. Länge der Mittellinie fixieren
                    self.sketch.add_length(center_line, length)
                    
                    # 2. Radius (Breite) fixieren
                    self.sketch.add_radius(main_arc, radius)
                    
                    # C. Solver anstoßen
                    # Das rückt alles gerade und aktualisiert Winkel
                    self.sketch.solve()
                    
                    # D. UI Updates
                    self.sketched_changed.emit()
                    self._find_closed_profiles()
                    
            # Werkzeug zurücksetzen
            self._cancel_tool()
    
    
    
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
            logger.error(f"Spline error: {e}")
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
        self._solve_async()
    
    def _handle_copy(self, pos, snap_type):
        """Kopieren: Basispunkt → Zielpunkt (INKLUSIVE CONSTRAINTS)"""
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
            
            # Wir nutzen die Helper-Methode, die jetzt auch Constraints kopiert
            self._copy_selection_with_offset(dx, dy)
            
            self.sketched_changed.emit()
            self._find_closed_profiles()
            self._cancel_tool()

    def _copy_selection_with_offset(self, dx, dy):
        """
        Kopiert Geometrie UND Constraints.
        Wichtig: Constraints werden nur kopiert, wenn ALLE beteiligten Elemente
        mitkopiert wurden (interne Constraints).
        """
        new_lines = []
        new_circles = []
        new_arcs = []
        
        # Mapping: Alte ID -> Neues Objekt (für Constraint-Rekonstruktion)
        # Wir müssen Linien, Kreise UND Punkte mappen
        old_to_new = {}

        # 1. Linien kopieren
        for line in self.selected_lines:
            new_line = self.sketch.add_line(
                line.start.x + dx, line.start.y + dy,
                line.end.x + dx, line.end.y + dy,
                construction=line.construction
            )
            new_lines.append(new_line)
            
            # Mapping speichern
            old_to_new[line.id] = new_line
            old_to_new[line.start.id] = new_line.start
            old_to_new[line.end.id] = new_line.end

        # 2. Kreise kopieren
        for c in self.selected_circles:
            new_circle = self.sketch.add_circle(
                c.center.x + dx, c.center.y + dy,
                c.radius, construction=c.construction
            )
            new_circles.append(new_circle)
            
            old_to_new[c.id] = new_circle
            old_to_new[c.center.id] = new_circle.center

        # 3. Arcs kopieren
        for a in self.selected_arcs:
            new_arc = self.sketch.add_arc(
                a.center.x + dx, a.center.y + dy,
                a.radius, a.start_angle, a.end_angle,
                construction=a.construction
            )
            new_arcs.append(new_arc)
            
            old_to_new[a.id] = new_arc
            old_to_new[a.center.id] = new_arc.center

        # 4. Constraints kopieren (Der wichtige Teil!)
        # Wir durchsuchen alle existierenden Constraints
        constraints_added = 0
        for c in self.sketch.constraints:
            # Prüfen, ob ALLE Entities dieses Constraints in unserer Mapping-Tabelle sind.
            # Das bedeutet, der Constraint bezieht sich nur auf kopierte Elemente (intern).
            # Beispiel: Rechteck-Seitenlänge (intern) -> Kopieren.
            # Beispiel: Abstand Rechteck zu Ursprung (extern) -> Nicht kopieren.
            
            is_internal = True
            if not c.entities: 
                is_internal = False
            
            new_entities = []
            for entity in c.entities:
                if hasattr(entity, 'id') and entity.id in old_to_new:
                    new_entities.append(old_to_new[entity.id])
                else:
                    is_internal = False
                    break
            
            if is_internal:
                # Constraint klonen
                new_c = Constraint(
                    type=c.type,
                    entities=new_entities,
                    value=c.value
                )
                self.sketch.constraints.append(new_c)
                constraints_added += 1

        # Neue Elemente auswählen
        self._clear_selection()
        self.selected_lines = new_lines
        self.selected_circles = new_circles
        self.selected_arcs = new_arcs

        msg = tr("Copied: {l} lines, {c} circles").format(l=len(new_lines), c=len(new_circles))
        if constraints_added > 0:
            msg += f", {constraints_added} constraints"
        self.status_message.emit(msg)
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
        """
        Rotiert Auswahl und entfernt dabei störende H/V Constraints.
        """
        rad = math.radians(angle_deg)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        rotated = set()
        
        # 1. FIX: Störende Constraints entfernen
        # Horizontal/Vertical Constraints verhindern Rotation -> Löschen
        # (Optional könnte man sie durch Perpendicular/Parallel ersetzen, 
        # aber Löschen ist für freie Rotation sicherer)
        constraints_to_remove = []
        
        # IDs der ausgewählten Elemente sammeln
        selected_ids = set()
        for l in self.selected_lines: selected_ids.add(l.id)
        
        for c in self.sketch.constraints:
            if c.type in [ConstraintType.HORIZONTAL, ConstraintType.VERTICAL]:
                # Wenn das Constraint zu einer der rotierten Linien gehört
                if c.entities and c.entities[0].id in selected_ids:
                    constraints_to_remove.append(c)
        
        for c in constraints_to_remove:
            if c in self.sketch.constraints:
                self.sketch.constraints.remove(c)
        
        # 2. Geometrie Rotieren
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
                
        # Auch Arcs rotieren (inkl. Winkel-Update)
        for arc in self.selected_arcs:
            if arc.center.id not in rotated:
                dx = arc.center.x - center.x()
                dy = arc.center.y - center.y()
                arc.center.x = center.x() + dx * cos_a - dy * sin_a
                arc.center.y = center.y() + dx * sin_a + dy * cos_a
                rotated.add(arc.center.id)
            
            # Winkel anpassen
            arc.start_angle += angle_deg
            arc.end_angle += angle_deg
        
        self._solve_async()
    
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
        """
        Lineares Muster: Vollständig interaktiv mit DimensionInput.
        UX: 
        1. User wählt Elemente.
        2. Aktiviert Tool.
        3. Klick definiert Startpunkt -> Mausbewegung definiert Richtung & Abstand (Vorschau).
        4. Tab öffnet Eingabe für präzise Werte.
        """
        # Validierung: Nichts ausgewählt?
        if not self.selected_lines and not self.selected_circles and not self.selected_arcs:
            if hasattr(self, 'show_message'):
                self.show_message("Bitte erst Elemente auswählen!", 2000, QColor(255, 200, 100))
            else:
                self.status_message.emit(tr("Select elements first!"))
            self.set_tool(SketchTool.SELECT) # Auto-Cancel
            return

        # Schritt 0: Startpunkt setzen
        if self.tool_step == 0:
            self.tool_points = [pos]
            self.tool_step = 1

            # Default-Werte initialisieren, falls noch nicht vorhanden
            if 'pattern_count' not in self.tool_data:
                self.tool_data['pattern_count'] = 3
            if 'pattern_spacing' not in self.tool_data:
                self.tool_data['pattern_spacing'] = 20.0
            
            # Richtung initial auf Mausposition (wird in update aktualisiert)
            self.tool_data['pattern_direction'] = (1.0, 0.0)

            # Input anzeigen
            self._show_dimension_input()
            
            msg = tr("Direction/Spacing with Mouse | Tab=Input | Enter=Apply")
            if hasattr(self, 'show_message'):
                self.show_message(msg, 4000)
            else:
                self.status_message.emit(msg)

        # Schritt 1: Anwenden
        elif self.tool_step == 1:
            # Wenn Input aktiv ist und Fokus hat, handlet _on_dim_confirmed das.
            # Wenn User in den Canvas klickt, wenden wir es hier an.
            self._apply_linear_pattern(pos)

    def _show_pattern_linear_input(self):
        """Zeigt DimensionInput für Linear Pattern"""
        count = self.tool_data.get('pattern_count', 3)
        spacing = self.tool_data.get('pattern_spacing', 20.0)
        fields = [("N", "count", float(count), "×"), ("D", "spacing", spacing, "mm")]
        self.dim_input.setup(fields)

        # Position neben Maus
        pos = self.mouse_screen
        x = min(int(pos.x()) + 30, self.width() - self.dim_input.width() - 10)
        y = min(int(pos.y()) - 50, self.height() - self.dim_input.height() - 10)
        self.dim_input.move(max(10, x), max(10, y))
        self.dim_input.show()
        self.dim_input_active = True

    def _apply_linear_pattern(self, end_pos=None):
        """Wendet das lineare Muster final an."""
        start = self.tool_points[0]
        
        # Richtung update, falls Mausposition gegeben
        if end_pos:
            dx = end_pos.x() - start.x()
            dy = end_pos.y() - start.y()
            dist = math.hypot(dx, dy)
            if dist > 1.0: 
                 self.tool_data['pattern_spacing'] = dist
                 self.tool_data['pattern_direction'] = (dx/dist, dy/dist)
        
        count = int(self.tool_data.get('pattern_count', 3))
        spacing = float(self.tool_data.get('pattern_spacing', 20.0))
        ux, uy = self.tool_data.get('pattern_direction', (1.0, 0.0))

        if count < 2: return

        self._save_undo()
        created_count = 0
        
        for i in range(1, count):
            ox, oy = ux * spacing * i, uy * spacing * i
            for l in self.selected_lines:
                self.sketch.add_line(l.start.x + ox, l.start.y + oy, l.end.x + ox, l.end.y + oy, construction=l.construction)
                created_count += 1
            for c in self.selected_circles:
                self.sketch.add_circle(c.center.x + ox, c.center.y + oy, c.radius, construction=c.construction)
                created_count += 1
            for a in self.selected_arcs:
                self.sketch.add_arc(a.center.x + ox, a.center.y + oy, a.radius, a.start_angle, a.end_angle, construction=a.construction)
                created_count += 1

        self.sketched_changed.emit()
        self._find_closed_profiles()
        self.status_message.emit(f"Linear Pattern: {created_count} elements created.")
        self._cancel_tool()

    def _handle_pattern_circular(self, pos, snap_type):
        """Kreisförmiges Muster: Interaktiv mit DimensionInput"""
        if not self.selected_lines and not self.selected_circles and not self.selected_arcs:
            self.status_message.emit(tr("Select elements first!"))
            self.set_tool(SketchTool.SELECT)
            return

        if self.tool_step == 0:
            self.tool_points = [pos]
            self.tool_step = 1
            
            if 'pattern_count' not in self.tool_data:
                self.tool_data['pattern_count'] = 6
            if 'pattern_angle' not in self.tool_data:
                self.tool_data['pattern_angle'] = 360.0
            
            self._show_pattern_circular_input()
            self.status_message.emit(tr("Center selected | Click=Apply | Tab=Count/Angle"))

        elif self.tool_step == 1:
            self._apply_circular_pattern()

    def _show_pattern_circular_input(self):
        count = self.tool_data.get('pattern_count', 6)
        angle = self.tool_data.get('pattern_angle', 360.0)
        fields = [("N", "count", float(count), "x"), ("∠", "angle", angle, "°")]
        self.dim_input.setup(fields)
        
        pos = self.mouse_screen
        x = min(int(pos.x()) + 30, self.width() - self.dim_input.width() - 10)
        y = min(int(pos.y()) - 50, self.height() - self.dim_input.height() - 10)
        self.dim_input.move(max(10, x), max(10, y))
        self.dim_input.show()
        self.dim_input_active = True

    def _apply_circular_pattern(self):
        center = self.tool_points[0]
        count = int(self.tool_data.get('pattern_count', 6))
        total_angle = float(self.tool_data.get('pattern_angle', 360.0))

        if count < 2: return
        self._save_undo()
        
        if abs(total_angle - 360.0) < 0.01:
             step_angle = math.radians(360.0 / count)
        else:
             step_angle = math.radians(total_angle / (count - 1)) if count > 1 else 0

        created_count = 0
        cx, cy = center.x(), center.y()

        for i in range(1, count):
            angle = step_angle * i
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            def rotate_pt(px, py):
                dx, dy = px - cx, py - cy
                return cx + dx*cos_a - dy*sin_a, cy + dx*sin_a + dy*cos_a

            for l in self.selected_lines:
                s = rotate_pt(l.start.x, l.start.y)
                e = rotate_pt(l.end.x, l.end.y)
                self.sketch.add_line(s[0], s[1], e[0], e[1], construction=l.construction)
                created_count += 1
            for c in self.selected_circles:
                cp = rotate_pt(c.center.x, c.center.y)
                self.sketch.add_circle(cp[0], cp[1], c.radius, construction=c.construction)
                created_count += 1
            for a in self.selected_arcs:
                cp = rotate_pt(a.center.x, a.center.y)
                ns = a.start_angle + math.degrees(angle)
                ne = a.end_angle + math.degrees(angle)
                self.sketch.add_arc(cp[0], cp[1], a.radius, ns, ne, construction=a.construction)
                created_count += 1

        self.sketched_changed.emit()
        self._find_closed_profiles()
        self.status_message.emit(f"Circular Pattern: {created_count} elements.")
        self._cancel_tool()
    
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
        
        self._solve_async()
        self._find_closed_profiles()
    
    
    def _handle_trim(self, pos, snap_type, snap_entity=None):
        """
        Intelligentes Trimmen:
        1. Findet Entity unter Maus
        2. Berechnet ALLE Schnittpunkte gegen ALLE anderen Geometrien
        3. Löscht Segment
        """
        # --- Imports Setup ---
        try:
            import sketcher.geometry as geometry
        except ImportError:
            import geometry 
        from sketcher import Point2D, Line2D, Circle2D, Arc2D
        # ---------------------

        # 1. Target bestimmen
        target = snap_entity
        if not target:
            target = self._find_entity_at(pos) # Kein Radius-Parameter mehr!
            
        if not target:
            self.preview_geometry = []
            self.update()
            return

        # 2. Liste aller anderen Entities erstellen (FIX FÜR AttributeError)
        # Wir müssen die Listen manuell zusammenfügen, da self.sketch.entities nicht existiert
        other_entities = []
        other_entities.extend(self.sketch.lines)
        other_entities.extend(self.sketch.circles)
        if hasattr(self.sketch, 'arcs'):
            other_entities.extend(self.sketch.arcs)
        # Punkte ignorieren wir beim Trimmen (man kann Linie nicht an Punkt schneiden ohne Constraint)

        # 3. Alle Schnittpunkte berechnen
        cut_points = []
        
        # Start/Ende des Targets selbst
        if isinstance(target, Line2D):
            cut_points.append((0.0, target.start))
            cut_points.append((1.0, target.end))

        # Loop über die manuell erstellte Liste
        for other in other_entities:
            if other == target: continue 
            
            intersects = []
            try:
                # Dispatching an Geometry-Backend
                if isinstance(target, Line2D) and isinstance(other, Line2D):
                    pt = geometry.line_line_intersection(target, other)
                    if pt: intersects = [pt]
                elif isinstance(target, Circle2D) and isinstance(other, Circle2D):
                    intersects = geometry.circle_circle_intersection(target, other)
                elif isinstance(target, Line2D) and isinstance(other, Circle2D):
                    intersects = geometry.circle_line_intersection(other, target)
                elif isinstance(target, Circle2D) and isinstance(other, Line2D):
                    intersects = geometry.circle_line_intersection(target, other)
                elif isinstance(target, Arc2D) and isinstance(other, Line2D):
                    intersects = geometry.arc_line_intersection(target, other)
                elif isinstance(target, Line2D) and isinstance(other, Arc2D):
                    intersects = geometry.arc_line_intersection(other, target)
                elif isinstance(target, Arc2D) and isinstance(other, Circle2D):
                    intersects = geometry.arc_circle_intersection(target, other)
                elif isinstance(target, Circle2D) and isinstance(other, Arc2D):
                    intersects = geometry.arc_circle_intersection(other, target)
            except Exception:
                continue

            # Validierung der Punkte
            for p in intersects:
                t = geometry.get_param_on_entity(p, target)
                
                if isinstance(target, Line2D):
                    # Toleranz: Nicht exakt auf Start/Ende
                    if 0.001 < t < 0.999:
                        cut_points.append((t, p))
                elif isinstance(target, Circle2D):
                    cut_points.append((t, p))
                elif isinstance(target, Arc2D):
                    cut_points.append((t, p))

        # 4. Sortieren
        cut_points.sort(key=lambda x: x[0])

        # 5. Segment finden
        t_mouse = geometry.get_param_on_entity(Point2D(pos.x(), pos.y()), target)
        segment_to_remove = None
        
        if isinstance(target, Line2D):
            for i in range(len(cut_points) - 1):
                t_start, p_start = cut_points[i]
                t_end, p_end = cut_points[i+1]
                if t_start <= t_mouse <= t_end:
                    segment_to_remove = (p_start, p_end, i, cut_points)
                    break
                    
        elif isinstance(target, Circle2D):
            if not cut_points:
                segment_to_remove = "ALL"
            else:
                first_t, first_p = cut_points[0]
                cut_points_loop = cut_points + [(first_t + 2*math.pi, first_p)]
                
                found = False
                for i in range(len(cut_points_loop) - 1):
                    t_s, p_s = cut_points_loop[i]
                    t_e, p_e = cut_points_loop[i+1]
                    
                    if t_s <= t_mouse <= t_e:
                        segment_to_remove = (p_s, p_e, i, cut_points)
                        found = True
                        break
                    # Wrap-Around Check
                    if t_mouse + 2*math.pi <= t_e:
                         if t_s <= t_mouse + 2*math.pi:
                            segment_to_remove = (p_s, p_e, i, cut_points)
                            found = True
                            break
                            
                if not found and cut_points:
                     segment_to_remove = (cut_points[-1][1], cut_points[0][1], -1, cut_points)

        # 6. Aktion ausführen
        if segment_to_remove:
            self.status_message.emit("Klicken zum Trimmen")
            
            # Vorschau (optional)
            if isinstance(target, Line2D) and segment_to_remove != "ALL":
                self.preview_geometry = [Line2D(segment_to_remove[0], segment_to_remove[1])]

            if QApplication.mouseButtons() & Qt.LeftButton:
                self._save_undo()
                
                # Entfernen (Sicher, ohne .entities Property)
                if target in self.sketch.points: self.sketch.points.remove(target)
                elif target in self.sketch.lines: self.sketch.lines.remove(target)
                elif target in self.sketch.circles: self.sketch.circles.remove(target)
                elif hasattr(self.sketch, 'arcs') and target in self.sketch.arcs: self.sketch.arcs.remove(target)
                
                # Neu erstellen (Was übrig bleibt)
                if isinstance(target, Line2D):
                    for i in range(len(cut_points) - 1):
                        p_start = cut_points[i][1]
                        p_end = cut_points[i+1][1]
                        
                        # Check ob das das gelöschte Segment ist
                        is_removed = (abs(p_start.x - segment_to_remove[0].x) < 1e-5 and 
                                      abs(p_start.y - segment_to_remove[0].y) < 1e-5)
                        
                        if not is_removed and p_start.distance_to(p_end) > 1e-3:
                            self.sketch.add_line(p_start.x, p_start.y, p_end.x, p_end.y)

                elif isinstance(target, Circle2D) and segment_to_remove != "ALL":
                    p_start_remove, p_end_remove, idx, _ = segment_to_remove
                    
                    ang_start = geometry.get_param_on_entity(p_end_remove, target)
                    ang_end = geometry.get_param_on_entity(p_start_remove, target)
                    
                    if ang_end < ang_start: 
                        ang_end += 2*math.pi
                        
                    if abs(ang_end - ang_start) > 1e-4:
                        self.sketch.add_arc(target.center.x, target.center.y, target.radius, ang_start, ang_end)

                self.sketched_changed.emit()
                self._find_closed_profiles()
                self.mouse_buttons = Qt.NoButton
    
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
        """Fillet: Klicke auf eine Ecke. Zeigt Input automatisch an."""
        
        # 1. Input-Feld automatisch anzeigen, wenn noch nicht aktiv
        if not self.dim_input_active:
            self._show_dimension_input()
        
        # Radius aus Input übernehmen (Live-Update)
        if self.dim_input_active:
            # Holen ohne zu sperren, damit Tastatureingaben funktionieren
            vals = self.dim_input.get_values()
            if 'radius' in vals:
                self.fillet_radius = vals['radius']

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
        
        self.status_message.emit(tr("Click corner to fillet") + f" (R={self.fillet_radius:.1f}mm)")

    def _create_fillet_v2(self, l1, l2, corner, other1, other2, attr1, attr2, radius):
        """
        Erstellt ein Fillet mit korrigierter Geometrie und fügt Radius-Constraint hinzu.
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
        
        # Winkel zwischen den Linien
        dot = d1[0]*d2[0] + d1[1]*d2[1]
        dot = max(-1, min(1, dot))
        angle_between = math.acos(dot)
        
        # Geometrie-Check
        half_angle = angle_between / 2
        tan_dist = radius / math.tan(half_angle)
        
        if tan_dist > len1 * 0.99 or tan_dist > len2 * 0.99:
            self.status_message.emit(tr("Radius too large"))
            return False
        
        # Tangentenpunkte (Start/Ende des Bogens)
        t1_x = corner.x + d1[0] * tan_dist
        t1_y = corner.y + d1[1] * tan_dist
        t2_x = corner.x + d2[0] * tan_dist
        t2_y = corner.y + d2[1] * tan_dist
        
        # Bogenzentrum berechnen
        # Das Zentrum liegt auf der Winkelhalbierenden
        bisect = (d1[0] + d2[0], d1[1] + d2[1])
        bisect_len = math.hypot(bisect[0], bisect[1])
        if bisect_len < 0.001: return False
        
        bisect = (bisect[0]/bisect_len, bisect[1]/bisect_len)
        center_dist = radius / math.sin(half_angle)
        
        center_x = corner.x + bisect[0] * center_dist
        center_y = corner.y + bisect[1] * center_dist
        
        # Punkte aktualisieren (Linien verkürzen)
        # Wir müssen neue Punkt-Objekte für die Tangentenpunkte erstellen
        new_pt1 = Point2D(t1_x, t1_y)
        new_pt2 = Point2D(t2_x, t2_y)
        self.sketch.points.append(new_pt1)
        self.sketch.points.append(new_pt2)
        
        if attr1 == 'start': l1.start = new_pt1
        else: l1.end = new_pt1
            
        if attr2 == 'start': l2.start = new_pt2
        else: l2.end = new_pt2
        
        # Winkel für Bogen berechnen
        angle1 = math.degrees(math.atan2(t1_y - center_y, t1_x - center_x))
        angle2 = math.degrees(math.atan2(t2_y - center_y, t2_x - center_x))
        
        # FIX für invertierte Bögen: 
        # Wir wollen immer den kurzen Weg herum gehen (den Innenwinkel)
        diff = angle2 - angle1
        while diff <= -180: diff += 360
        while diff > 180: diff -= 360
        
        # arc erwartet start und end. Wenn diff negativ ist, müssen wir swapen oder sweep anpassen
        # Sketch.add_arc(cx, cy, r, start, end)
        if diff < 0:
            arc = self.sketch.add_arc(center_x, center_y, radius, angle2, angle1)
        else:
            arc = self.sketch.add_arc(center_x, center_y, radius, angle1, angle2)
            
        # CONSTRAINT HINZUFÜGEN: Damit der Radius sichtbar bleibt!
        self.sketch.add_radius(arc, radius)
        
        self.status_message.emit(tr("Fillet R={radius}mm created").format(radius=f"{radius:.1f}"))
        return True

    def _handle_chamfer_2d(self, pos, snap_type):
        """Chamfer: Klicke auf eine Ecke. Zeigt Input automatisch an."""
        
        # 1. Input-Feld automatisch anzeigen
        if not self.dim_input_active:
            self._show_dimension_input()
            
        # Länge aus Input übernehmen
        if self.dim_input_active:
            vals = self.dim_input.get_values()
            if 'length' in vals:
                self.chamfer_distance = vals['length']

        r = self.snap_radius / self.view_scale
        
        for i, l1 in enumerate(self.sketch.lines):
            for l2 in self.sketch.lines[i+1:]:
                corners = [
                    (l1.start, l1.end, l2.start, l2.end, 'start', 'start'),
                    (l1.start, l1.end, l2.end, l2.start, 'start', 'end'),
                    (l1.end, l1.start, l2.start, l2.end, 'end', 'start'),
                    (l1.end, l1.start, l2.end, l2.start, 'end', 'end'),
                ]
                
                for corner1, other1, corner2, other2, attr1, attr2 in corners:
                    if corner1 is corner2 or math.hypot(corner1.x - corner2.x, corner1.y - corner2.y) < 1.0:
                        if math.hypot(corner1.x - pos.x(), corner1.y - pos.y()) < r:
                            self._save_undo()
                            success = self._create_chamfer_v2(l1, l2, corner1, other1, other2, attr1, attr2, self.chamfer_distance)
                            if success:
                                self.sketched_changed.emit()
                                self._find_closed_profiles()
                                self.update()
                            return
        
        self.status_message.emit(tr("Click corner to chamfer") + f" (L={self.chamfer_distance:.1f}mm)")

    def _create_chamfer_v2(self, l1, l2, corner, other1, other2, attr1, attr2, dist):
        """
        Erstellt eine Fase und fügt Längen-Constraint hinzu.
        """
        from sketcher.geometry import Point2D
        
        # Richtungsvektoren
        d1 = (other1.x - corner.x, other1.y - corner.y)
        d2 = (other2.x - corner.x, other2.y - corner.y)
        
        len1 = math.hypot(d1[0], d1[1])
        len2 = math.hypot(d2[0], d2[1])
        if len1 < 0.01 or len2 < 0.01: return False
        
        d1 = (d1[0]/len1, d1[1]/len1)
        d2 = (d2[0]/len2, d2[1]/len2)
        
        if dist > len1 * 0.9 or dist > len2 * 0.9:
            self.status_message.emit(tr("Chamfer too large"))
            return False
        
        # Neue Endpunkte
        c1_x = corner.x + d1[0] * dist
        c1_y = corner.y + d1[1] * dist
        c2_x = corner.x + d2[0] * dist
        c2_y = corner.y + d2[1] * dist
        
        # Neue Punkte erstellen
        new_pt1 = Point2D(c1_x, c1_y)
        new_pt2 = Point2D(c2_x, c2_y)
        self.sketch.points.append(new_pt1)
        self.sketch.points.append(new_pt2)
        
        # Linien anpassen
        if attr1 == 'start': l1.start = new_pt1
        else: l1.end = new_pt1
            
        if attr2 == 'start': l2.start = new_pt2
        else: l2.end = new_pt2
        
        # Fase-Linie hinzufügen
        chamfer_line = self.sketch.add_line(c1_x, c1_y, c2_x, c2_y)
        
        # CONSTRAINT HINZUFÜGEN: Länge der Fase anzeigen
        # Wir berechnen die hypothetische Länge der Fasenlinie (Wurzel(dist^2 + dist^2) bei 90 Grad, 
        # aber hier setzen wir einfach die Distanz an den Schenkeln fest, oder besser:
        # Fusion360 zeigt meist die Schenkellänge an, aber hier haben wir keine "Chamfer Dimension".
        # Wir fügen einfach die Länge der neuen Linie hinzu, damit man sie ändern kann.
        
        # Hinweis: Bei 'Equal Distance' Chamfer ist die Linienlänge = dist * sqrt(2 * (1 - cos(angle))).
        # Das ist kompliziert zu bemaßen. 
        # Besser: Wir fügen KEINE direkte Bemaßung an die schräge Linie an, da das oft krumme Werte sind,
        # SONDERN wir lassen den Nutzer es sehen. 
        # Aber die Anforderung war "sollte er auch hinschreiben".
        # Da wir "Schenkel-Länge" (Distance) eingegeben haben, ist es am intuitivsten, 
        # wenn wir nichts tun ODER eine Bemaßung hinzufügen.
        # Da unsere Constraints aktuell nur "Line Length" können und nicht "Point to Point distance along vector",
        # ist die Länge der Fasenlinie der einzige Wert, den wir anzeigen können.
        
        actual_len = math.hypot(c2_x - c1_x, c2_y - c1_y)
        self.sketch.add_length(chamfer_line, actual_len)
        
        self.status_message.emit(tr("Chamfer created"))
        return True
    
    def _handle_dimension(self, pos, snap_type):
        """Bemaßungstool - Modernisiert (Kein QInputDialog mehr!)"""
        
        # 1. Input-Feld automatisch anzeigen, wenn noch nicht aktiv
        if not self.dim_input_active:
             self._show_dimension_input()
        
        # Werte aus Input holen, falls aktiv
        new_val = None
        if self.dim_input_active:
             vals = self.dim_input.get_values()
             if 'value' in vals: new_val = vals['value']
        
        line = self._find_line_at(pos)
        if line:
            current = line.length
            # Wenn Input bestätigt wurde, anwenden
            if new_val is not None and abs(new_val - current) > 0.001:
                 self._save_undo()
                 self.sketch.add_length(line, new_val)
                 self._solve_async()
                 self.sketched_changed.emit()
                 self._find_closed_profiles()
                 self.status_message.emit(f"Length set to {new_val:.2f}mm")
                 return
            
            # Ansonsten nur anzeigen
            fields = [("Length", "value", current, "mm")]
            self.dim_input.setup(fields)
            
            # Input neben Maus bewegen
            screen_pos = self.mouse_screen
            self.dim_input.move(int(screen_pos.x()) + 20, int(screen_pos.y()) + 20)
            self.dim_input.show()
            self.dim_input.focus_field(0)
            self.dim_input_active = True
            return

        circle = self._find_circle_at(pos)
        if circle:
            current = circle.radius
            if new_val is not None and abs(new_val - current) > 0.001:
                 self._save_undo()
                 self.sketch.add_radius(circle, new_val)
                 self._solve_async()
                 self.sketched_changed.emit()
                 self._find_closed_profiles()
                 self.status_message.emit(f"Radius set to {new_val:.2f}mm")
                 return
            
            fields = [("Radius", "value", current, "mm")]
            self.dim_input.setup(fields)
            screen_pos = self.mouse_screen
            self.dim_input.move(int(screen_pos.x()) + 20, int(screen_pos.y()) + 20)
            self.dim_input.show()
            self.dim_input.focus_field(0)
            self.dim_input_active = True
            return
            
        self.status_message.emit(tr("Select line or circle to dimension"))

    def _handle_project(self, pos, snap_type):
        """
        Projiziert Referenzgeometrie in den Sketch.
        Erstellt Linien, die 'fixed' sind.
        """
        # 1. Haben wir eine Referenzkante unter der Maus?
        edge = getattr(self, 'hovered_ref_edge', None)
        
        if edge:
            x1, y1, x2, y2 = edge
            
            # Prüfen ob Linie schon existiert (um Duplikate zu vermeiden)
            # Das ist wichtig für UX, sonst stackt man 10 Linien übereinander
            for l in self.sketch.lines:
                # Prüfe Endpunkte (ungefähre Gleichheit)
                if (math.hypot(l.start.x - x1, l.start.y - y1) < 0.001 and \
                    math.hypot(l.end.x - x2, l.end.y - y2) < 0.001) or \
                   (math.hypot(l.start.x - x2, l.start.y - y2) < 0.001 and \
                    math.hypot(l.end.x - x1, l.end.y - y1) < 0.001):
                    self.status_message.emit(tr("Geometry already projected"))
                    return

            self._save_undo()
            
            # 2. Linie erstellen
            # Wir nutzen construction mode flag, falls User Hilfslinien projizieren will
            line = self.sketch.add_line(x1, y1, x2, y2, construction=self.construction_mode)
            
            # 3. FIXIEREN!
            # Projizierte Geometrie sollte fixiert sein, da sie an 3D hängt
            self.sketch.add_fixed(line.start)
            self.sketch.add_fixed(line.end)
            # Optional: Wir könnten ein spezielles Flag 'projected' einführen, 
            # aber 'fixed' Punkte reichen für die Logik vorerst.
            
            self.sketched_changed.emit()
            self._find_closed_profiles()
            self.status_message.emit(tr("Edge projected"))
            
        else:
            self.status_message.emit(tr("Hover over a background edge to project"))

            
    def _handle_dimension_angle(self, pos, snap_type):
        """Winkelbemaßung - Modernisiert"""
        line = self._find_line_at(pos)
        if not line: self.status_message.emit(tr("Select first line")); return
        
        if self.tool_step == 0:
            self.tool_data['line1'] = line; self.tool_step = 1
            self.status_message.emit(tr("Select second line"))
        else:
            l1 = self.tool_data.get('line1')
            if l1 and line != l1:
                current_angle = abs(l1.angle - line.angle)
                if current_angle > 180: current_angle = 360 - current_angle
                
                # Check Input
                if not self.dim_input_active:
                     self._show_dimension_input()
                
                new_val = None
                if self.dim_input_active:
                     vals = self.dim_input.get_values()
                     if 'angle' in vals: new_val = vals['angle']
                
                if new_val is not None:
                    self._save_undo()
                    self.sketch.add_angle(l1, line, new_val)
                    self._solve_async()
                    self.sketched_changed.emit()
                    self._find_closed_profiles()
                    self._cancel_tool()
                else:
                    fields = [("Angle", "angle", current_angle, "°")]
                    self.dim_input.setup(fields)
                    screen_pos = self.mouse_screen
                    self.dim_input.move(int(screen_pos.x()) + 20, int(screen_pos.y()) + 20)
                    self.dim_input.show()
                    self.dim_input.focus_field(0)
                    self.dim_input_active = True
    
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
        """
        Perpendicular Constraint mit Pre-Rotation.
        Rotiert die zweite Linie VOR dem Constraint ungefähr senkrecht,
        damit der Solver besser konvergiert und keine Ecken "wegrutschen".
        """
        line = self._find_line_at(pos)
        if not line:
            if hasattr(self, 'show_message'):
                self.show_message("Linie auswählen", 2000)
            else:
                self.status_message.emit(tr("Select first line"))
            return

        if self.tool_step == 0:
            self.tool_data['line1'] = line
            self.tool_step = 1
            if hasattr(self, 'show_message'):
                self.show_message("Zweite Linie auswählen", 2000)
            else:
                self.status_message.emit(tr("Select second line"))
        else:
            l1 = self.tool_data.get('line1')
            if l1 and line != l1:
                self._save_undo()

                # === PRE-ROTATION: Linie 2 ungefähr senkrecht zu Linie 1 rotieren ===
                # Berechne aktuellen Winkel von l1
                dx1 = l1.end.x - l1.start.x
                dy1 = l1.end.y - l1.start.y
                angle1 = math.atan2(dy1, dx1)

                # Berechne aktuellen Winkel von l2
                dx2 = line.end.x - line.start.x
                dy2 = line.end.y - line.start.y
                angle2 = math.atan2(dy2, dx2)
                length2 = math.hypot(dx2, dy2)

                # Zielwinkel: 90° zu l1 (nehme den näheren der beiden Möglichkeiten)
                target_angle_a = angle1 + math.pi / 2
                target_angle_b = angle1 - math.pi / 2

                # Normalisiere Winkel auf [-pi, pi]
                def normalize_angle(a):
                    while a > math.pi: a -= 2 * math.pi
                    while a < -math.pi: a += 2 * math.pi
                    return a

                diff_a = abs(normalize_angle(target_angle_a - angle2))
                diff_b = abs(normalize_angle(target_angle_b - angle2))

                # Wähle den Winkel mit kleinerer Rotation
                target_angle = target_angle_a if diff_a < diff_b else target_angle_b

                # Rotiere l2 um seinen Startpunkt auf den Zielwinkel
                # (nur wenn Abweichung > 5°, um unnötige Änderungen zu vermeiden)
                rotation_needed = abs(normalize_angle(target_angle - angle2))
                if rotation_needed > math.radians(5):
                    new_end_x = line.start.x + length2 * math.cos(target_angle)
                    new_end_y = line.start.y + length2 * math.sin(target_angle)
                    line.end.x = new_end_x
                    line.end.y = new_end_y
                    logger.debug(f"Pre-rotated line by {math.degrees(rotation_needed):.1f}° for perpendicular")

                # Constraint hinzufügen und lösen
                self.sketch.add_perpendicular(l1, line)
                result = self.sketch.solve()
                logger.debug(f"Solver Result: Success={result.success}, Message={result.message}")

                if not result.success:
                    if hasattr(self, 'show_message'):
                        self.show_message(f"Solver: {result.message}", 3000, QColor(255, 150, 100))
                    else:
                        self.status_message.emit(f"Fehler: {result.message}")
                else:
                    if hasattr(self, 'show_message'):
                        self.show_message("Senkrecht-Constraint angewendet", 2000, QColor(100, 255, 100))
                    else:
                        self.status_message.emit(tr("Perpendicular constraint applied (DOF: {dof})").format(dof=getattr(result, "dof", -1)))

                self.sketched_changed.emit()
                self._find_closed_profiles()
                self.update()
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
    
    
    
    def _handle_pattern_circular(self, pos, snap_type):
        """
        Kreisförmiges Muster.
        UX:
        1. Selektion.
        2. Tool aktivieren.
        3. Zentrum wählen (Snap!).
        4. Tab für Anzahl/Winkel.
        """
        if not self.selected_lines and not self.selected_circles and not self.selected_arcs:
            if hasattr(self, 'show_message'):
                self.show_message("Bitte erst Elemente auswählen!", 2000, QColor(255, 200, 100))
            self.set_tool(SketchTool.SELECT)
            return

        if self.tool_step == 0:
            # Zentrum wählen
            self.tool_points = [pos]
            self.tool_step = 1
            
            # Defaults
            if 'pattern_count' not in self.tool_data:
                self.tool_data['pattern_count'] = 6
            if 'pattern_angle' not in self.tool_data:
                self.tool_data['pattern_angle'] = 360.0
            
            self._show_dimension_input()
            
            msg = tr("Center selected | Tab=Count/Angle | Enter=Apply")
            if hasattr(self, 'show_message'):
                self.show_message(msg, 4000)
            else:
                self.status_message.emit(msg)

        elif self.tool_step == 1:
            # Klick im Canvas (woanders als Zentrum) bestätigt auch
            self._apply_circular_pattern()
    
    def _handle_gear(self, pos, snap_type):
        """
        Erweitertes Zahnrad-Tool (Fusion 360 Kompatibel).
        Unterstützt Backlash, Profilverschiebung und Bohrung.
        """
        # --- 1. Dialog Setup ---
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Stirnrad (Spur Gear)"))
        dialog.setFixedWidth(340) # Etwas breiter für mehr Optionen
        dialog.setStyleSheet("""
            QDialog { background-color: #2d2d30; color: #e0e0e0; }
            QLabel, QCheckBox { color: #aaaaaa; }
            QDoubleSpinBox, QSpinBox { 
                background-color: #3e3e42; color: #ffffff; border: 1px solid #555; padding: 4px; 
            }
            QPushButton { background-color: #0078d4; color: white; border: none; padding: 6px; }
            QPushButton:hover { background-color: #1084d8; }
        """)

        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        # --- Standard Parameter ---
        spin_module = QDoubleSpinBox()
        spin_module.setRange(0.1, 50.0)
        spin_module.setValue(2.0)
        spin_module.setSingleStep(0.5)
        spin_module.setSuffix(" mm")

        spin_teeth = QSpinBox()
        spin_teeth.setRange(4, 200)
        spin_teeth.setValue(20)
        
        spin_angle = QDoubleSpinBox()
        spin_angle.setRange(14.5, 30.0)
        spin_angle.setValue(20.0)
        spin_angle.setSuffix(" °")

        # --- Erweiterte Parameter (Wichtig!) ---
        
        # Zahnflankenspiel (Backlash) - Wichtig für 3D Druck
        spin_backlash = QDoubleSpinBox()
        spin_backlash.setRange(0.0, 2.0)
        spin_backlash.setValue(0.15) # Guter Default für 3D Druck
        spin_backlash.setSingleStep(0.05)
        spin_backlash.setSuffix(" mm")
        spin_backlash.setToolTip("Verringert die Zahndicke für Spielraum")

        # Bohrung
        spin_hole = QDoubleSpinBox()
        spin_hole.setRange(0.0, 1000.0)
        spin_hole.setValue(6.0) # Standard Welle
        spin_hole.setSuffix(" mm")

        # Profilverschiebung (x) - Wichtig bei wenig Zähnen (<17)
        spin_shift = QDoubleSpinBox()
        spin_shift.setRange(-1.0, 1.0)
        spin_shift.setValue(0.0)
        spin_shift.setSingleStep(0.1)
        spin_shift.setToolTip("Positiv: Stärkerer Fuß, größerer Durchmesser.\nNötig bei < 17 Zähnen um Unterschnitt zu vermeiden.")

        # Fußrundung (Fillet)
        spin_fillet = QDoubleSpinBox()
        spin_fillet.setRange(0.0, 5.0)
        spin_fillet.setValue(0.5) # Leichte Rundung
        spin_fillet.setSuffix(" mm")

        # Performance
        check_lowpoly = QCheckBox(tr("Vorschau (Low Poly)"))
        check_lowpoly.setChecked(True)

        # Layout bauen
        form.addRow(tr("Modul:"), spin_module)
        form.addRow(tr("Zähne:"), spin_teeth)
        form.addRow(tr("Druckwinkel:"), spin_angle)
        form.addRow(tr("-----------"), QLabel("")) # Trenner
        form.addRow(tr("Bohrung ⌀:"), spin_hole)
        form.addRow(tr("Spiel (Backlash):"), spin_backlash)
        form.addRow(tr("Profilverschiebung:"), spin_shift)
        form.addRow(tr("Fußradius:"), spin_fillet)
        form.addRow("", check_lowpoly)
        
        layout.addLayout(form)
        
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        layout.addWidget(btns)

        # --- Live Vorschau ---
        def update_preview():
            self._remove_preview_elements()
            
            # Parameter dictionary für saubereren Aufruf
            params = {
                'cx': pos.x(), 'cy': pos.y(),
                'module': spin_module.value(),
                'teeth': spin_teeth.value(),
                'pressure_angle': spin_angle.value(),
                'backlash': spin_backlash.value(),
                'hole_diam': spin_hole.value(),
                'profile_shift': spin_shift.value(),
                'fillet': spin_fillet.value(),
                'preview': True,
                'low_poly': check_lowpoly.isChecked()
            }

            self._generate_involute_gear(**params)
            self.sketched_changed.emit()

        # Signale verbinden
        for widget in [spin_module, spin_teeth, spin_angle, spin_backlash, 
                      spin_hole, spin_shift, spin_fillet]:
            widget.valueChanged.connect(update_preview)
        check_lowpoly.toggled.connect(update_preview)

        # Initiale Vorschau
        update_preview()

        if dialog.exec() == QDialog.Accepted:
            self._remove_preview_elements()
            self._save_undo()
            
            # Final Generieren (High Quality)
            params = {
                'cx': pos.x(), 'cy': pos.y(),
                'module': spin_module.value(),
                'teeth': spin_teeth.value(),
                'pressure_angle': spin_angle.value(),
                'backlash': spin_backlash.value(),
                'hole_diam': spin_hole.value(),
                'profile_shift': spin_shift.value(),
                'fillet': spin_fillet.value(),
                'preview': False,
                'low_poly': False # Immer High Quality für Final
            }
            
            self._generate_involute_gear(**params)
            self.sketched_changed.emit()
            self._find_closed_profiles()
            
            info = f"Zahnrad M{spin_module.value()} Z{spin_teeth.value()}"
            if spin_backlash.value() > 0: info += f" B={spin_backlash.value()}"
            self.status_message.emit(tr(info + " erstellt"))
        else:
            self._remove_preview_elements()
            self.sketched_changed.emit()

        self._cancel_tool()

    def _remove_preview_elements(self):
        """Entfernt markierte Vorschau-Elemente"""
        # Listenkopie erstellen, da wir während der Iteration löschen
        lines_to_remove = [l for l in self.sketch.lines if hasattr(l, 'is_preview') and l.is_preview]
        circles_to_remove = [c for c in self.sketch.circles if hasattr(c, 'is_preview') and c.is_preview]
        
        for l in lines_to_remove: 
            if l in self.sketch.lines: self.sketch.lines.remove(l)
        for c in circles_to_remove: 
            if c in self.sketch.circles: self.sketch.circles.remove(c)

    def _generate_involute_gear(self, cx, cy, module, teeth, pressure_angle, 
                              backlash=0.0, hole_diam=0.0, profile_shift=0.0, fillet=0.0,
                              preview=False, low_poly=True):
        """
        Umfassender Generator für Evolventen-Verzahnung.
        Mathematik basiert auf DIN 3960 / Fusion SpurGear Script.
        """
        if teeth < 4: teeth = 4
        
        # --- 1. Basis-Berechnungen (DIN 3960) ---
        alpha = math.radians(pressure_angle)
        
        # Teilkreis (Reference Pitch Circle)
        d = module * teeth
        r = d / 2.0
        
        # Grundkreis (Base Circle) - Hier beginnt die Evolvente
        db = d * math.cos(alpha)
        rb = db / 2.0
        
        # Kopf- und Fußhöhenfaktoren (Standard 1.0 und 1.25)
        # Profilverschiebung (x) ändert diese Durchmesser
        ha = (1.0 + profile_shift) * module  # Addendum (Kopf)
        hf = (1.25 - profile_shift) * module # Dedendum (Fuß)
        
        # Durchmesser
        da = d + 2 * ha # Kopfkreis (Tip)
        df = d - 2 * hf # Fußkreis (Root)
        
        ra = da / 2.0
        rf = df / 2.0
        
        # --- 2. Zahndicke und Backlash ---
        # Die Zahndicke wird am Teilkreis gemessen.
        # Standard: s = p / 2 = (pi * m) / 2
        # Mit Profilverschiebung: s = m * (pi/2 + 2*x*tan(alpha))
        # Mit Backlash: Wir ziehen Backlash ab.
        
        tan_alpha = math.tan(alpha)
        
        # Halber Winkel der Zahndicke am Teilkreis (ohne Backlash)
        # ArcLength = r * angle -> angle = ArcLength / r
        # Dicke s_nom = m * (pi/2 + 2 * profile_shift * tan_alpha)
        s_nom = module * (math.pi/2.0 + 2.0 * profile_shift * tan_alpha)
        
        # Backlash anwenden (Verringert die Dicke)
        s_act = s_nom - backlash
        
        # Winkel im Bogenmaß am Teilkreis für die halbe Zahndicke
        psi = s_act / (2.0 * r) 
        
        # Involute Funktion: inv(alpha) = tan(alpha) - alpha
        inv_alpha = tan_alpha - alpha
        
        # Der Winkel-Offset für den Start der Evolvente (am Grundkreis)
        # Theta_start = psi + inv_alpha
        half_tooth_angle = psi + inv_alpha
        
        # --- 3. Profilberechnung (Eine Flanke) ---
        steps = 3 if low_poly else 8
        flank_points = []
        
        # Wir berechnen Punkte vom Grundkreis (rb) bis Kopfkreis (ra)
        # Achtung: Wenn Fußkreis (rf) < Grundkreis (rb), startet Evolvente erst bei rb.
        # Darunter ist es eine Gerade oder ein Fillet.
        
        start_r = max(rb, rf)
        
        for i in range(steps + 1):
            # Nicht-lineare Verteilung für schönere Kurven an der Basis
            t = i / steps
            radius_at_point = start_r + (ra - start_r) * t
            
            # Winkel phi (Druckwinkel an diesem Radius)
            # cos(phi) = rb / radius
            if radius_at_point < rb: 
                val = 1.0 
            else:
                val = rb / radius_at_point
            
            phi_r = math.acos(min(1.0, max(-1.0, val)))
            inv_phi = math.tan(phi_r) - phi_r
            
            # Winkel theta (Polarkoordinate relativ zur Zahnmitte)
            theta = half_tooth_angle - inv_phi
            flank_points.append((radius_at_point, theta))
            
        # --- 4. Fußbereich (Root / Undercut / Fillet) ---
        # Wenn der Fußkreis kleiner als der Grundkreis ist, müssen wir den Zahn nach unten verlängern.
        # Fusion nutzt hier komplexe Trochoiden für Unterschnitt. Wir nutzen eine radiale Linie + Fillet.
        
        if rf < rb:
            # Einfache Verlängerung: Radial vom Fußkreis zum Start der Evolvente
            # Mit Fillet: Wir runden den Übergang vom Fußkreis zur Flanke ab.
            
            # Winkel am Start der Evolvente
            angle_at_base = flank_points[0][1]
            
            if fillet > 0.01 and not low_poly:
                # Simuliertes Fillet: Ein Punkt zwischen (rf, angle) und (rb, angle)
                # Wir gehen etwas in den Zahnzwischenraum (Winkel wird größer)
                # Zahnlücke Mitte ist bei PI/z. 
                # Das ist zu komplex für schnelles Skripting. 
                # Wir machen eine direkte Linie zum Fußkreis.
                flank_points.insert(0, (rf, angle_at_base))
            else:
                # Harter Übergang
                flank_points.insert(0, (rf, angle_at_base))

        # --- 5. Spiegeln und Zusammenbauen ---
        tooth_poly = []
        
        # Linke Flanke (gespiegelt, Winkel negativ) -> Von Fuß nach Kopf
        # flank_points ist [Fuß ... Kopf]. 
        # Wir brauchen [Fuß ... Kopf] aber mit negativen Winkeln?
        # Nein, für CCW Polygon: 
        # Center -> (Rechte Flanke) -> Tip -> (Linke Flanke) -> Center
        # Aber wir bauen das ganze Rad.
        
        # Strategie: Wir bauen die Punkte für EINEN Zahn (Rechts + Links)
        # und rotieren diesen.
        
        # Linke Flanke (Winkel = -theta). Von Root zu Tip?
        # Sagen wir 0° ist die Zahnmitte.
        # Rechte Flanke ist bei +Theta. Linke bei -Theta.
        # CCW Reihenfolge: Rechte Flanke (Tip->Root) -> Root Arc -> Linke Flanke (Root->Tip) -> Tip Arc
        
        # 1. Rechte Flanke (Außen nach Innen)
        for r, theta in reversed(flank_points):
            tooth_poly.append((r, theta))
            
        # 2. Fußkreis (Verbindung zur linken Flanke im GLEICHEN Zahn ist falsch, das wäre durch den Zahn durch)
        # Wir verbinden zum NÄCHSTEN Zahn über den Fußkreis.
        # Also definieren wir nur das Profil EINES Zahns.
        # Profil: Tip Right -> ... -> Root Right -> (Lücke) -> Root Left -> ... Tip Left
        # Aber das ist schwer zu loopen.
        
        # Einfacher: Ein Zahn besteht aus Linker Flanke (aufsteigend) und Rechter Flanke (absteigend).
        # Linke Flanke (negativer Winkel, von Root nach Tip)
        single_tooth = []
        
        # Linke Flanke (Winkel < 0)
        for r, theta in flank_points:
            single_tooth.append((r, -theta))
            
        # Tip (Verbindung Linke Spitze zu Rechter Spitze)
        # Rechte Flanke (Winkel > 0, von Tip nach Root, also reversed)
        for r, theta in reversed(flank_points):
            single_tooth.append((r, theta))
            
        # Jetzt haben wir: RootLeft -> TipLeft -> TipRight -> RootRight
        
        # --- 6. Rad erstellen ---
        all_world_points = []
        angle_step = (2 * math.pi) / teeth
        
        for i in range(teeth):
            beta = i * angle_step
            cos_b = math.cos(beta)
            sin_b = math.sin(beta)
            
            for r, theta in single_tooth:
                # Polar zu Kartesisch mit Rotation beta
                # Punkt Winkel = theta + beta
                px = cx + r * math.cos(theta + beta)
                py = cy + r * math.sin(theta + beta)
                all_world_points.append(Point2D(px, py))
                
        # --- 7. Zeichnen ---
        lines = []
        circles = []
        
        for i in range(len(all_world_points)):
            p1 = all_world_points[i]
            p2 = all_world_points[(i + 1) % len(all_world_points)]
            
            l = self.sketch.add_line(p1.x, p1.y, p2.x, p2.y)
            if preview: l.is_preview = True
            lines.append(l)

        # Bohrung
        if hole_diam > 0.01:
            h = self.sketch.add_circle(cx, cy, hole_diam / 2.0)
            if preview: h.is_preview = True
            circles.append(h)
            
        # Teilkreis als Konstruktionslinie (Hilfreich)
        if preview and not low_poly:
            pc = self.sketch.add_circle(cx, cy, r, construction=True)
            pc.is_preview = True
            circles.append(pc)

        return lines, circles
    
    def _handle_star(self, pos, snap_type):
        """
        Stern-Werkzeug mit modernem Input.
        """
        if self.tool_step == 0:
            self.tool_points = [pos]
            
            fields = [
                ("Spitzen", "points", 5.0, ""),
                ("R Außen", "r_outer", 50.0, "mm"),
                ("R Innen", "r_inner", 25.0, "mm")
            ]
            self.dim_input.setup(fields)
            
            from PySide6.QtGui import QCursor
            cursor_pos = self.mapFromGlobal(QCursor.pos())
            self.dim_input.move(cursor_pos.x() + 20, cursor_pos.y() + 20)
            self.dim_input.show()
            self.dim_input.focus_field(0)
            
            try: self.dim_input.confirmed.disconnect() 
            except: pass
            
            self.dim_input.confirmed.connect(lambda: self._create_star_geometry())
            self.tool_step = 1

    def _create_star_geometry(self):
        values = self.dim_input.get_values()
        n = int(values.get("points", 5))
        ro = values.get("r_outer", 50.0)
        ri = values.get("r_inner", 25.0)
        
        cx = self.tool_points[0].x()
        cy = self.tool_points[0].y()
        self._save_undo()
        
        points = []
        step = math.pi / n
        
        for i in range(2 * n):
            r = ro if i % 2 == 0 else ri
            angle = i * step - math.pi / 2 # Startet oben
            px = cx + r * math.cos(angle)
            py = cy + r * math.sin(angle)
            points.append((px, py))
            
        for i in range(len(points)):
            p1 = points[i]
            p2 = points[(i + 1) % len(points)]
            self.sketch.add_line(p1[0], p1[1], p2[0], p2[1])
            
        self.dim_input.hide()
        self.sketched_changed.emit()
        self._find_closed_profiles()
        self._cancel_tool()
    

    

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
        """
        Text Tool: Erstellt Vektor-Geometrie aus Text.
        Zeigt einen modernen Dialog zur Auswahl von Font, Text und Größe.
        """
        # --- 1. Custom Dialog erstellen (kein Windows-Standard) ---
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Create Text Profile"))
        dialog.setMinimumWidth(300)
        # Dark Theme Style für den Dialog
        dialog.setStyleSheet("""
            QDialog { background-color: #2d2d30; color: #e0e0e0; }
            QLabel { color: #aaaaaa; }
            QLineEdit, QDoubleSpinBox, QFontComboBox { 
                background-color: #3e3e42; color: #ffffff; border: 1px solid #555; padding: 4px; 
            }
            QPushButton { background-color: #0078d4; color: white; border: none; padding: 6px; }
            QPushButton:hover { background-color: #1084d8; }
        """)
        
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        
        # Inputs
        txt_input = QLineEdit("MashCad")
        font_input = QFontComboBox()
        font_input.setCurrentFont(QFont("Arial"))
        
        size_input = QDoubleSpinBox()
        size_input.setRange(1.0, 1000.0)
        size_input.setValue(10.0)
        size_input.setSuffix(" mm")
        
        form.addRow(tr("Text:"), txt_input)
        form.addRow(tr("Font:"), font_input)
        form.addRow(tr("Height:"), size_input)
        
        layout.addLayout(form)
        
        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        layout.addWidget(btns)
        
        # Dialog ausführen
        if dialog.exec() != QDialog.Accepted:
            self._cancel_tool()
            return
            
        # Werte holen
        text_str = txt_input.text()
        if not text_str: return
        
        selected_font = font_input.currentFont()
        # Wichtig: Outline Strategy für saubere Pfade
        selected_font.setStyleStrategy(QFont.PreferOutline)
        # Größe groß setzen für interne Pfad-Präzision, wir skalieren später
        selected_font.setPointSize(100) 
        
        desired_height = size_input.value()
        
        self._save_undo()
        
        # --- 2. Pfad generieren ---
        path = QPainterPath()
        path.addText(0, 0, selected_font, text_str)
        
        # --- 3. Skalierung berechnen ---
        rect = path.boundingRect()
        if rect.height() > 0.001:
            scale_factor = desired_height / rect.height()
        else:
            scale_factor = 1.0
            
        # Zum Mauszeiger verschieben (Zentriert)
        # Y ist in Qt Screens oft invertiert zu CAD, hier Skizze ist math (Y up) vs Qt (Y down)
        # QPainterPath addText generiert Text Upside-Down wenn wir in Cartesian rendern? 
        # Wir spiegeln Y vorsichtshalber mit scale(s, -s) und verschieben dann.
        
        # Berechnung Offset zum Zentrieren
        center_x = rect.width() * scale_factor / 2
        center_y = rect.height() * scale_factor / 2
        
        # Transform: Skalieren & Spiegeln (damit Text aufrecht steht in math. System)
        transform = QTransform()
        transform.translate(pos.x(), pos.y()) # Zum Klickpunkt
        transform.scale(scale_factor, -scale_factor) # Y Flip für CAD Koordinaten
        transform.translate(-rect.width()/2, rect.height()/2) # Zentrieren relativ zum Ursprung
        
        try:
            polygons = path.toSubpathPolygons(transform)
        except Exception as e:
            logger.error(f"Text path conversion failed: {e}")
            return

        # --- 4. Linien erzeugen ---
        count = 0
        for poly in polygons:
            pts = []
            for p in poly:
                pts.append(Point2D(p.x(), p.y()))
            
            # Punkte verbinden
            for i in range(len(pts) - 1):
                self.sketch.add_line(pts[i].x, pts[i].y, pts[i+1].x, pts[i+1].y)
                count += 1
            # Schließen
            if len(pts) > 2:
                self.sketch.add_line(pts[-1].x, pts[-1].y, pts[0].x, pts[0].y)
                count += 1

        self.sketched_changed.emit()
        self._find_closed_profiles()
        self.status_message.emit(tr(f"Text '{text_str}' created ({count} lines)"))
        self._cancel_tool()
    
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
    
