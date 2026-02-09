"""
MashCad - Sketch Handlers Mixin
All _handle_* methods for sketch tools
Extracted from sketch_editor.py for better maintainability
"""

import math
import sys
import os
from loguru import logger
from PySide6.QtCore import QPointF, Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QTransform, QPainterPath, QFont, QFontMetrics
from PySide6.QtWidgets import (QApplication, QInputDialog, QDialog, QVBoxLayout, 
                               QFormLayout, QLineEdit, QDialogButtonBox, QDoubleSpinBox, 
                               QFontComboBox, QWidget, QLabel, QSpinBox, QCheckBox)

from sketcher import Point2D, Line2D, Circle2D, Arc2D
from i18n import tr
try:
    from gui.sketch_feedback import format_trim_failure_message, format_trim_warning_message
except ImportError:
    try:
        from sketch_feedback import format_trim_failure_message, format_trim_warning_message
    except ImportError:
        from .sketch_feedback import format_trim_failure_message, format_trim_warning_message

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

    def _adaptive_world_tolerance(self, scale: float = 1.0, min_world: float = 0.05, max_world: float = 2.0) -> float:
        """
        Convert screen snap radius to a bounded world tolerance.
        """
        try:
            snap_px = float(getattr(self, "snap_radius", 15))
            view_scale = max(float(getattr(self, "view_scale", 1.0)), 1e-9)
            tol = (snap_px / view_scale) * float(scale)
        except Exception:
            tol = 1.0
        return max(min_world, min(max_world, tol))
    
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

    def _add_point_constraint(self, point, pos, snap_type, snap_entity, new_line):
        """
        FÃ¼gt automatisch Constraints fÃ¼r einen Punkt hinzu basierend auf Snap-Info.

        Args:
            point: Der Point2D der neuen Linie (start oder end)
            pos: Die Snap-Position (QPointF)
            snap_type: SnapType
            snap_entity: Die gesnappte Entity
            new_line: Die neue Linie (um Selbst-Referenz zu vermeiden)
        """
        if snap_type == SnapType.NONE:
            return

        # Einige Inferenz-Snaps (z.B. Horizontal/Vertical) haben bewusst kein target-entity.
        entity_optional_types = {SnapType.HORIZONTAL, SnapType.VERTICAL}
        if snap_entity is None and snap_type not in entity_optional_types:
            return

        # ENDPOINT: COINCIDENT Constraint
        if snap_type == SnapType.ENDPOINT:
            snapped_point = None
            if hasattr(snap_entity, 'start') and hasattr(snap_entity, 'end'):
                # Linie - prÃ¼fe welcher Endpunkt nÃ¤her ist
                dist_start = math.hypot(pos.x() - snap_entity.start.x, pos.y() - snap_entity.start.y)
                dist_end = math.hypot(pos.x() - snap_entity.end.x, pos.y() - snap_entity.end.y)
                snapped_point = snap_entity.start if dist_start < dist_end else snap_entity.end

            if snapped_point and snapped_point != point:
                if hasattr(self.sketch, 'add_coincident'):
                    self.sketch.add_coincident(point, snapped_point)
                    logger.debug(f"Auto: COINCIDENT fÃ¼r {type(snap_entity).__name__}")
                else:
                    # Fallback: Koordinaten direkt setzen
                    point.x = snapped_point.x
                    point.y = snapped_point.y

        # EDGE: POINT_ON_LINE oder POINT_ON_CIRCLE Constraint
        elif snap_type == SnapType.EDGE:
            if hasattr(snap_entity, 'start'):  # Linie
                if snap_entity != new_line:
                    if hasattr(self.sketch, 'add_point_on_line'):
                        self.sketch.add_point_on_line(point, snap_entity)
                        logger.debug(f"Auto: POINT_ON_LINE")
            elif hasattr(snap_entity, 'radius'):  # Kreis
                if hasattr(self.sketch, 'add_point_on_circle'):
                    self.sketch.add_point_on_circle(point, snap_entity)
                    logger.debug(f"Auto: POINT_ON_CIRCLE")

        # CENTER: COINCIDENT mit Kreismittelpunkt
        elif snap_type == SnapType.CENTER:
            if hasattr(snap_entity, 'center'):
                if hasattr(self.sketch, 'add_coincident'):
                    self.sketch.add_coincident(point, snap_entity.center)
                    logger.debug(f"Auto: COINCIDENT mit Center")

        # MIDPOINT: MIDPOINT Constraint (falls vorhanden)
        elif snap_type == SnapType.MIDPOINT:
            if hasattr(snap_entity, 'start') and hasattr(snap_entity, 'end'):
                if hasattr(self.sketch, 'add_midpoint'):
                    self.sketch.add_midpoint(point, snap_entity)
                    logger.debug(f"Auto: MIDPOINT")

        # PERPENDICULAR: Endpunkt auf Referenzlinie + Senkrecht-Constraint
        elif snap_type == SnapType.PERPENDICULAR:
            if hasattr(snap_entity, 'start') and hasattr(snap_entity, 'end'):
                if snap_entity != new_line:
                    if hasattr(self.sketch, 'add_point_on_line'):
                        self.sketch.add_point_on_line(point, snap_entity)
                        logger.debug("Auto: POINT_ON_LINE (PERPENDICULAR)")
                    if hasattr(self.sketch, 'add_perpendicular'):
                        self.sketch.add_perpendicular(new_line, snap_entity)
                        logger.debug("Auto: PERPENDICULAR")

        # TANGENT: Endpunkt auf Kreis/Bogen + Tangenten-Constraint
        elif snap_type == SnapType.TANGENT:
            if hasattr(snap_entity, 'radius'):
                if hasattr(self.sketch, 'add_point_on_circle'):
                    self.sketch.add_point_on_circle(point, snap_entity)
                    logger.debug("Auto: POINT_ON_CIRCLE (TANGENT)")
                if hasattr(self.sketch, 'add_tangent'):
                    self.sketch.add_tangent(new_line, snap_entity)
                    logger.debug("Auto: TANGENT")

        # HORIZONTAL: Linie als horizontal fixieren
        elif snap_type == SnapType.HORIZONTAL:
            if hasattr(self.sketch, 'add_horizontal'):
                self.sketch.add_horizontal(new_line)
                logger.debug("Auto: HORIZONTAL")

        # VERTICAL: Linie als vertikal fixieren
        elif snap_type == SnapType.VERTICAL:
            if hasattr(self.sketch, 'add_vertical'):
                self.sketch.add_vertical(new_line)
                logger.debug("Auto: VERTICAL")

        # PARALLEL: Linie parallel zu Referenzlinie
        elif snap_type == SnapType.PARALLEL:
            if hasattr(snap_entity, 'start') and hasattr(snap_entity, 'end'):
                if snap_entity != new_line and hasattr(self.sketch, 'add_parallel'):
                    self.sketch.add_parallel(new_line, snap_entity)
                    logger.debug("Auto: PARALLEL")

    def _handle_line(self, pos, snap_type, snap_entity=None):
        """
        Erstellt Linien und nutzt die existierenden Constraint-Methoden des Sketch-Objekts.
        """
        # Schritt 1: Startpunkt setzen
        if self.tool_step == 0:
            self.tool_points = [pos]
            # WICHTIG: Snap-Info fÃ¼r Startpunkt speichern!
            self._line_start_snap = (snap_type, snap_entity)
            self.tool_step = 1
            self.status_message.emit("Endpunkt wÃ¤hlen | Tab=LÃ¤nge/Winkel | Rechts=Fertig")
        
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
                h_tolerance = self._adaptive_world_tolerance(scale=0.35, min_world=0.05, max_world=2.0)
                
                # Nur prÃ¼fen, wenn wir nicht explizit an einer Kante snappen (um Konflikte zu vermeiden)
                if snap_type not in [
                    SnapType.EDGE,
                    SnapType.INTERSECTION,
                    SnapType.VIRTUAL_INTERSECTION,
                    SnapType.PERPENDICULAR,
                    SnapType.TANGENT,
                    SnapType.HORIZONTAL,
                    SnapType.VERTICAL,
                    SnapType.PARALLEL,
                ]:
                    if abs(dy) < h_tolerance and abs(dx) > h_tolerance:
                        if hasattr(self.sketch, 'add_horizontal'):
                            self.sketch.add_horizontal(line)
                            self.status_message.emit("Auto: Horizontal")
                            
                    elif abs(dx) < h_tolerance and abs(dy) > h_tolerance:
                        if hasattr(self.sketch, 'add_vertical'):
                            self.sketch.add_vertical(line)
                            self.status_message.emit("Auto: Vertical")

                # --- B. Auto-Constraints: Verbindungen (Das neue Snapping) ---
                # Behandelt sowohl START als auch END der neuen Linie

                # B.1: START-Punkt Constraints (aus gespeicherter Snap-Info)
                start_snap_type, start_snap_entity = getattr(self, '_line_start_snap', (SnapType.NONE, None))
                self._add_point_constraint(line.start, start, start_snap_type, start_snap_entity, line)

                # B.2: END-Punkt Constraints (aktueller Snap)
                self._add_point_constraint(line.end, pos, snap_type, snap_entity, line)

                # --- C. Abschluss ---
                self._solve_async() 
                self._find_closed_profiles()
                self.sketched_changed.emit()
                
                # Poly-Line Modus
                self.tool_points.append(pos)
    
    def _handle_rectangle(self, pos, snap_type):
        """Rechteck mit Modus-UnterstÃ¼tzung (0=2-Punkt, 1=Center) und Auto-Constraints"""
        
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

        # Erstellung und BemaÃŸung
        if w > 0.01 and h > 0.01:
            self._save_undo()

            # 1. Rechteck erstellen (gibt [Unten, Rechts, Oben, Links] zurÃ¼ck)
            # Hinweis: add_rectangle muss in sketch.py return [l1, l2, l3, l4] haben!
            lines = self.sketch.add_rectangle(x, y, w, h, construction=self.construction_mode)

            # 2. Automatische BemaÃŸung hinzufÃ¼gen (Constraints)
            # Wir bemaÃŸen die untere Linie (Breite) und die linke Linie (HÃ¶he)
            if lines and len(lines) >= 4:
                # Breite (Index 0 = Unten)
                self.sketch.add_length(lines[0], w)
                # HÃ¶he (Index 3 = Links)
                self.sketch.add_length(lines[3], h)

            # 3. LÃ¶sen & Update
            self._solve_async() # Thread start
            self._find_closed_profiles() # Immediate visual feedback (pre-solve)
            self.sketched_changed.emit()
            
        self._cancel_tool()
    
    def _handle_circle(self, pos, snap_type):
        """Kreis mit Modus-UnterstÃ¼tzung (0=Center-Radius, 1=2-Punkt, 2=3-Punkt) und Auto-Constraints"""
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
                    # 2. Radius Constraint hinzufÃ¼gen
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
                    # 2. Radius Constraint hinzufÃ¼gen (fixiert die GrÃ¶ÃŸe)
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
                    # 2. Radius Constraint hinzufÃ¼gen
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
        
        # Determinante fÃ¼r KollinearitÃ¤ts-Check
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
        """Separater Handler fÃ¼r reinen 2-Punkt-Modus (falls als eigenes Tool genutzt)"""
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
                
                # 2. Radius-BemaÃŸung hinzufÃ¼gen
                # Das erlaubt dir, den Radius spÃ¤ter per Doppelklick zu Ã¤ndern!
                self.sketch.add_radius(const_circle, r)
                
                # 3. LÃ¶sen
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
        Handler fÃ¼r das Langloch-Werkzeug.
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
            self.status_message.emit(tr("Radius | Tab=Enter radius"))

            # Show dimension input for radius (Phase 8: Auto-show)
            logger.info(f"[SLOT] Step 1â†’2: Showing radius input panel")
            logger.debug(f"[SLOT] hasattr dim_input: {hasattr(self, 'dim_input')}")

            # Clear any previous state and show radius input
            if hasattr(self, 'dim_input'):
                logger.debug(f"[SLOT] dim_input exists, setting up radius field")
                self.dim_input.committed_values.clear()
                self.dim_input.unlock_all()
                radius_default = self.live_radius if self.live_radius > 0 else 5.0
                fields = [("R", "radius", radius_default, "mm")]
                self.dim_input.setup(fields)
                # Position near mouse
                pos_screen = self.world_to_screen(pos)
                x = min(int(pos_screen.x()) + 20, self.width() - self.dim_input.width() - 10)
                y = min(int(pos_screen.y()) - 40, self.height() - self.dim_input.height() - 10)
                self.dim_input.move(max(10, x), max(10, y))
                self.dim_input.show()
                self.dim_input.focus_field(0)
                self.dim_input_active = True
                logger.success(f"[SLOT] Radius panel shown at ({x}, {y}), visible={self.dim_input.isVisible()}")
            else:
                logger.error(f"[SLOT] dim_input NOT FOUND on self!")
            
        # --- Schritt 3: Breite/Radius und Erstellung ---
        else:
            p1 = self.tool_points[0]
            p2 = self.tool_points[1]
            
            # Vektor der Mittellinie berechnen
            dx_line = p2.x() - p1.x()
            dy_line = p2.y() - p1.y()
            length = math.hypot(dx_line, dy_line)
            
            # Verhindern von Null-LÃ¤ngen
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
                    # WICHTIG: add_slot muss (center_line, main_arc) zurÃ¼ckgeben!
                    center_line, main_arc = self.sketch.add_slot(
                        p1.x(), p1.y(), p2.x(), p2.y(), radius, 
                        construction=self.construction_mode
                    )
                    
                    # B. BemaÃŸungen hinzufÃ¼gen (Constraints)
                    
                    # 1. LÃ¤nge der Mittellinie fixieren
                    self.sketch.add_length(center_line, length)
                    
                    # 2. Radius (Breite) fixieren
                    self.sketch.add_radius(main_arc, radius)
                    
                    # C. Solver anstoÃŸen
                    # Das rÃ¼ckt alles gerade und aktualisiert Winkel
                    self.sketch.solve()
                    
                    # D. UI Updates
                    self.sketched_changed.emit()
                    self._find_closed_profiles()
                    
            # Werkzeug zurÃ¼cksetzen
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
            
            # Spline zum Sketch hinzufÃ¼gen
            self.sketch.splines.append(spline)
            
            # Auch als Linien fÃ¼r KompatibilitÃ¤t (Export etc.)
            lines = spline.to_lines(segments_per_span=10)
            spline._lines = lines  # Referenz speichern fÃ¼r spÃ¤teren Update
            
            for line in lines:
                self.sketch.lines.append(line)
                self.sketch.points.append(line.start)
            if lines:
                self.sketch.points.append(lines[-1].end)
            
            # Spline auswÃ¤hlen fÃ¼r sofortiges Editing
            self.selected_splines = [spline]
            
            self.sketched_changed.emit()
            self._find_closed_profiles()
            self.status_message.emit(tr("Spline created - drag points/handles to edit"))
        except Exception as e:
            logger.error(f"Spline error: {e}")
        self._cancel_tool()
    
    def _handle_move(self, pos, snap_type):
        """Verschieben: Basispunkt â†’ Zielpunkt (wie Fusion360)"""
        if not self.selected_lines and not self.selected_circles and not self.selected_arcs:
            self.status_message.emit(tr("Select elements first!"))
            return
        
        if self.tool_step == 0:
            # Schritt 1: Basispunkt wÃ¤hlen
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
        """Verschiebt alle ausgewÃ¤hlten Elemente"""
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
        """Kopieren: Basispunkt â†’ Zielpunkt (INKLUSIVE CONSTRAINTS)"""
        if not self.selected_lines and not self.selected_circles and not self.selected_arcs:
            self.status_message.emit(tr("Select elements first!"))
            return
        
        if self.tool_step == 0:
            # Schritt 1: Basispunkt wÃ¤hlen
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
        
        # Mapping: Alte ID -> Neues Objekt (fÃ¼r Constraint-Rekonstruktion)
        # Wir mÃ¼ssen Linien, Kreise UND Punkte mappen
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
            # PrÃ¼fen, ob ALLE Entities dieses Constraints in unserer Mapping-Tabelle sind.
            # Das bedeutet, der Constraint bezieht sich nur auf kopierte Elemente (intern).
            # Beispiel: Rechteck-SeitenlÃ¤nge (intern) -> Kopieren.
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

        # Neue Elemente auswÃ¤hlen
        self._clear_selection()
        self.selected_lines = new_lines
        self.selected_circles = new_circles
        self.selected_arcs = new_arcs

        msg = tr("Copied: {l} lines, {c} circles").format(l=len(new_lines), c=len(new_circles))
        if constraints_added > 0:
            msg += f", {constraints_added} constraints"
        self.status_message.emit(msg)
    def _handle_rotate(self, pos, snap_type):
        """Drehen: Zentrum â†’ Winkel (wie Fusion360)"""
        if not self.selected_lines and not self.selected_circles and not self.selected_arcs:
            self.status_message.emit(tr("Select elements first!"))
            return
        
        if self.tool_step == 0:
            # Schritt 1: Drehzentrum wÃ¤hlen
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
        Rotiert Auswahl und entfernt dabei stÃ¶rende H/V Constraints.
        """
        rad = math.radians(angle_deg)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        rotated = set()
        
        # 1. FIX: StÃ¶rende Constraints entfernen
        # Horizontal/Vertical Constraints verhindern Rotation -> LÃ¶schen
        # (Optional kÃ¶nnte man sie durch Perpendicular/Parallel ersetzen, 
        # aber LÃ¶schen ist fÃ¼r freie Rotation sicherer)
        constraints_to_remove = []
        
        # IDs der ausgewÃ¤hlten Elemente sammeln
        selected_ids = set()
        for l in self.selected_lines: selected_ids.add(l.id)
        
        for c in self.sketch.constraints:
            if c.type in [ConstraintType.HORIZONTAL, ConstraintType.VERTICAL]:
                # Wenn das Constraint zu einer der rotierten Linien gehÃ¶rt
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
        
        # Neue Elemente auswÃ¤hlen
        self._clear_selection()
        self.selected_lines = new_lines
        self.selected_circles = new_circles
        self.status_message.emit(tr("Mirrored: {lines} lines, {circles} circles").format(lines=len(new_lines), circles=len(new_circles)))
    
    def _handle_pattern_linear(self, pos, snap_type):
        """
        Lineares Muster: VollstÃ¤ndig interaktiv mit DimensionInput.
        UX: 
        1. User wÃ¤hlt Elemente.
        2. Aktiviert Tool.
        3. Klick definiert Startpunkt -> Mausbewegung definiert Richtung & Abstand (Vorschau).
        4. Tab Ã¶ffnet Eingabe fÃ¼r prÃ¤zise Werte.
        """
        # Validierung: Nichts ausgewÃ¤hlt?
        if not self.selected_lines and not self.selected_circles and not self.selected_arcs:
            if hasattr(self, 'show_message'):
                self.show_message("Bitte erst Elemente auswÃ¤hlen!", 2000, QColor(255, 200, 100))
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
        """Zeigt DimensionInput fÃ¼r Linear Pattern"""
        count = self.tool_data.get('pattern_count', 3)
        spacing = self.tool_data.get('pattern_spacing', 20.0)
        fields = [("N", "count", float(count), "Ã—"), ("D", "spacing", spacing, "mm")]
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
        """KreisfÃ¶rmiges Muster: Interaktiv mit DimensionInput"""
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
        fields = [("N", "count", float(count), "x"), ("âˆ ", "angle", angle, "Â°")]
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
        """Skalieren: Zentrum â†’ Faktor (wie Fusion360)"""
        if not self.selected_lines and not self.selected_circles and not self.selected_arcs:
            self.status_message.emit(tr("Select elements first!"))
            return
        
        if self.tool_step == 0:
            # Schritt 1: Skalierungszentrum wÃ¤hlen
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
        """Skaliert alle ausgewÃ¤hlten Elemente vom Zentrum aus"""
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
        3. LÃ¶scht Segment

        Nutzt die extrahierte TrimOperation Klasse.
        """
        # Direkt extrahierte TrimOperation nutzen
        from sketcher.operations import TrimOperation

        # Target bestimmen
        target = snap_entity
        if not target:
            target = self._find_entity_at(pos)

        if not target:
            self.preview_geometry = []
            self.update()
            return

        # TrimOperation nutzen
        trim_op = TrimOperation(self.sketch)
        click_point = Point2D(pos.x(), pos.y())

        result = trim_op.find_segment(target, click_point)

        # Debug: Zeige was gefunden wurde
        logger.info(f"[TRIM] Target: {type(target).__name__}, cut_points: {len(result.cut_points)}")
        if result.success and result.segment:
            seg = result.segment
            logger.info(f"[TRIM] Segment idx={seg.segment_index}, "
                       f"start=({seg.start_point.x:.2f}, {seg.start_point.y:.2f}), "
                       f"end=({seg.end_point.x:.2f}, {seg.end_point.y:.2f}), "
                       f"all_cuts={len(seg.all_cut_points)}")

        if not result.success:
            target_type = type(target).__name__ if target is not None else ""
            msg = format_trim_failure_message(result.error, target_type=target_type)
            self.status_message.emit(msg)
            if hasattr(self, "show_message"):
                self.show_message(msg, 3500, QColor(255, 90, 90))
            logger.warning(f"[TRIM] Failed: {msg}")
            return

        # Preview
        segment = result.segment
        if isinstance(target, Line2D) and segment and not segment.is_full_delete:
            self.preview_geometry = [Line2D(segment.start_point, segment.end_point)]

        self.status_message.emit("Klicken zum Trimmen")

        # AusfÃ¼hren bei Klick
        if QApplication.mouseButtons() & Qt.LeftButton:
            from sketcher.operations.base import ResultStatus

            self._save_undo()
            op_result = trim_op.execute_trim(segment)
            is_warning = getattr(op_result, "status", None) == ResultStatus.WARNING

            if op_result.success:
                if is_warning:
                    target_type = type(target).__name__ if target is not None else ""
                    warn_msg = format_trim_warning_message(op_result.message, target_type=target_type)
                    logger.warning(f"[TRIM] Warning: {warn_msg}")
                    self.status_message.emit(warn_msg)
                    if hasattr(self, "show_message"):
                        self.show_message(warn_msg, 3000, QColor(255, 190, 90))
                else:
                    ok_msg = f"Trim: {op_result.message}"
                    logger.info(f"[TRIM] Success: {op_result.message}")
                    self.status_message.emit(ok_msg)
                if hasattr(self, "_solve_async"):
                    self._solve_async()
                else:
                    self.sketch.solve()
            else:
                target_type = type(target).__name__ if target is not None else ""
                msg = format_trim_failure_message(op_result.message, target_type=target_type)
                self.status_message.emit(msg)
                if hasattr(self, "show_message"):
                    self.show_message(msg, 3500, QColor(255, 90, 90))
                logger.warning(f"[TRIM] Failed: {msg}")

            self.preview_geometry = []
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
        """Findet alle zusammenhÃ¤ngenden Linien die ein Profil bilden"""
        TOL = 0.5
        
        def pt_match(p1, p2):
            return math.hypot(p1[0] - p2[0], p1[1] - p2[1]) < TOL
        
        def line_endpoints(l):
            return [(l.start.x, l.start.y), (l.end.x, l.end.y)]
        
        # Sammle alle nicht-Konstruktionslinien
        all_lines = [l for l in self.sketch.lines if not l.construction]
        if start_line not in all_lines:
            return [start_line]
        
        # Finde zusammenhÃ¤ngende Linien via BFS
        profile = [start_line]
        used = {id(start_line)}
        
        changed = True
        while changed:
            changed = False
            for line in all_lines:
                if id(line) in used:
                    continue
                
                # PrÃ¼fe ob diese Linie an eine Linie im Profil anschlieÃŸt
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
        """Konvertiert ein Shapely Polygon zu Pseudo-Line Objekten fÃ¼r Offset"""
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
        Berechnet Offset-Linien fÃ¼r ein Profil.
        
        Args:
            profile_lines: Liste von Linien die das Profil bilden
            distance: Offset-Abstand (positiv = nach auÃŸen, negativ = nach innen)
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
            
            # Bestimme ob diese Normale nach auÃŸen (weg vom Zentrum) zeigt
            mid_x = (line.start.x + line.end.x) / 2
            mid_y = (line.start.y + line.end.y) / 2
            
            # Vektor vom Zentrum zur Linienmitte
            to_center_x = cx - mid_x
            to_center_y = cy - mid_y
            
            # Wenn Normale zum Zentrum zeigt, umkehren
            dot = nx * to_center_x + ny * to_center_y
            if dot > 0:
                # Normale zeigt zum Zentrum, also umkehren fÃ¼r "nach auÃŸen"
                nx, ny = -nx, -ny
            
            # Jetzt zeigt (nx, ny) immer nach auÃŸen
            # Positiver distance = nach auÃŸen, negativer = nach innen
            d = distance
            
            x1 = line.start.x + nx * d
            y1 = line.start.y + ny * d
            x2 = line.end.x + nx * d
            y2 = line.end.y + ny * d
            
            offset_lines.append((x1, y1, x2, y2, line))
        
        # Ecken verbinden (Linien verlÃ¤ngern/trimmen)
        if len(offset_lines) > 1:
            offset_lines = self._connect_offset_corners(offset_lines)
        
        return offset_lines
    
    def _connect_offset_corners(self, offset_lines):
        """Verbindet Offset-Linien an den Ecken"""
        TOL = 0.5
        
        def pt_match(x1, y1, x2, y2):
            return math.hypot(x1 - x2, y1 - y2) < TOL
        
        def line_intersection(l1, l2):
            """Berechnet Schnittpunkt zweier Linien (unendlich verlÃ¤ngert)"""
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
        
        # FÃ¼r jedes Paar von Linien die sich berÃ¼hren sollten
        for i in range(len(result)):
            x1, y1, x2, y2, orig1 = result[i]
            
            for j in range(len(result)):
                if i == j:
                    continue
                
                x3, y3, x4, y4, orig2 = result[j]
                
                # PrÃ¼fe ob die Original-Linien verbunden waren
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
                        # Finde welcher Endpunkt am nÃ¤chsten zum Schnittpunkt ist
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
        1. Klick auf Element â†’ Sofort Vorschau mit Standard-Offset
        2. Tab â†’ Wert eingeben â†’ Vorschau aktualisiert live  
        3. Enter/Klick â†’ Anwenden
        
        Positiver Offset = nach auÃŸen (grÃ¶ÃŸer)
        Negativer Offset = nach innen (kleiner)
        """
        
        # Schritt 1: Element auswÃ¤hlen
        if self.tool_step == 0:
            # PrÃ¼fe Kreis zuerst
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
                direction = "auÃŸen" if self.tool_data['offset_outward'] else "innen"
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
        
        # Schritt 2: BestÃ¤tigen mit Klick
        elif self.tool_step == 1:
            self._apply_offset()
    
    def _offset_circle(self, circle, click_pos):
        """Offset fÃ¼r Kreis - sofort anwenden (legacy, wird nicht mehr verwendet)"""
        dist = math.hypot(click_pos.x() - circle.center.x, click_pos.y() - circle.center.y)
        
        # Positiver offset = grÃ¶ÃŸer (klick auÃŸen), negativer = kleiner (klick innen)
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

        # Radius aus Input Ã¼bernehmen (Live-Update)
        if self.dim_input_active:
            # Holen ohne zu sperren, damit Tastatureingaben funktionieren
            vals = self.dim_input.get_values()
            if 'radius' in vals:
                self.fillet_radius = vals['radius']

        r = self.snap_radius / self.view_scale

        # Suche Ecken (wo zwei Linien sich treffen)
        for i, l1 in enumerate(self.sketch.lines):
            for l2 in self.sketch.lines[i+1:]:
                # PrÃ¼fe alle Punkt-Kombinationen
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
        Erstellt ein Fillet mit korrigierter Geometrie und fÃ¼gt Radius-Constraint hinzu.

        Geometrie: Der Fillet-Bogen ist tangent zu beiden Linien und hat den angegebenen Radius.
        Das Zentrum liegt auf der Winkelhalbierenden, Abstand = radius / sin(half_angle).
        """
        from sketcher.geometry import Point2D

        # Richtungsvektoren VON der Ecke WEG entlang der Linien
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

        # Winkel zwischen den Linien (immer der kleinere Winkel, 0 bis Ï€)
        dot = d1[0]*d2[0] + d1[1]*d2[1]
        dot = max(-1, min(1, dot))
        angle_between = math.acos(dot)

        # Geometrie-Check
        if angle_between < 0.01 or angle_between > math.pi - 0.01:
            self.status_message.emit(tr("Lines too parallel"))
            return False

        half_angle = angle_between / 2

        # Abstand vom Corner zu den Tangentenpunkten
        tan_dist = radius / math.tan(half_angle)

        if tan_dist > len1 * 0.99 or tan_dist > len2 * 0.99:
            self.status_message.emit(tr("Radius too large"))
            return False

        # Tangentenpunkte auf den Linien
        t1_x = corner.x + d1[0] * tan_dist
        t1_y = corner.y + d1[1] * tan_dist
        t2_x = corner.x + d2[0] * tan_dist
        t2_y = corner.y + d2[1] * tan_dist

        # Winkelhalbierender Vektor (d1 + d2)
        # FÃ¼r konvexe Ecken (wie Rechteck) zeigt d1+d2 nach INNEN
        # Das ist korrekt fÃ¼r Fillets - NICHT negieren!
        bisect_x = d1[0] + d2[0]
        bisect_y = d1[1] + d2[1]
        bisect_len = math.hypot(bisect_x, bisect_y)

        if bisect_len < 0.001:
            self.status_message.emit(tr("Invalid corner geometry"))
            return False

        bisect_x /= bisect_len
        bisect_y /= bisect_len

        # Abstand vom Corner zum Arc-Zentrum
        center_dist = radius / math.sin(half_angle)

        # Arc-Zentrum (jetzt auf der INNENSEITE der Ecke)
        center_x = corner.x + bisect_x * center_dist
        center_y = corner.y + bisect_y * center_dist

        # Linien verkÃ¼rzen - neue Endpunkte an den Tangentenpunkten
        new_pt1 = Point2D(t1_x, t1_y)
        new_pt2 = Point2D(t2_x, t2_y)
        self.sketch.points.append(new_pt1)
        self.sketch.points.append(new_pt2)

        if attr1 == 'start':
            l1.start = new_pt1
        else:
            l1.end = new_pt1

        if attr2 == 'start':
            l2.start = new_pt2
        else:
            l2.end = new_pt2

        # Arc-Winkel berechnen (vom Zentrum aus gesehen)
        angle1 = math.degrees(math.atan2(t1_y - center_y, t1_x - center_x))
        angle2 = math.degrees(math.atan2(t2_y - center_y, t2_x - center_x))

        # Berechne den Sweep von angle1 zu angle2
        sweep = angle2 - angle1
        # Normalisiere auf [-180, 180] um den kurzen Weg zu finden
        while sweep > 180: sweep -= 360
        while sweep < -180: sweep += 360

        # WÃ¤hle Start/End so dass der Sweep positiv ist (CCW)
        if sweep >= 0:
            start_angle = angle1
            end_angle = angle2
        else:
            # Negativer sweep â†’ tausche fÃ¼r positiven Sweep
            start_angle = angle2
            end_angle = angle1

        # Stelle sicher dass end > start (fÃ¼r positiven Sweep im Renderer)
        if end_angle < start_angle:
            end_angle += 360

        arc = self.sketch.add_arc(center_x, center_y, radius, start_angle, end_angle)

        # Radius-Constraint hinzufÃ¼gen
        self.sketch.add_radius(arc, radius)

        self.status_message.emit(tr("Fillet R={radius}mm created").format(radius=f"{radius:.1f}"))
        return True

    def _handle_chamfer_2d(self, pos, snap_type):
        """Chamfer: Klicke auf eine Ecke. Zeigt Input automatisch an."""
        
        # 1. Input-Feld automatisch anzeigen
        if not self.dim_input_active:
            self._show_dimension_input()
            
        # LÃ¤nge aus Input Ã¼bernehmen
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
        Erstellt eine Fase und fÃ¼gt LÃ¤ngen-Constraint hinzu.
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
        
        # Fase-Linie hinzufÃ¼gen
        chamfer_line = self.sketch.add_line(c1_x, c1_y, c2_x, c2_y)
        
        # CONSTRAINT HINZUFÃœGEN: LÃ¤nge der Fase anzeigen
        # Wir berechnen die hypothetische LÃ¤nge der Fasenlinie (Wurzel(dist^2 + dist^2) bei 90 Grad, 
        # aber hier setzen wir einfach die Distanz an den Schenkeln fest, oder besser:
        # Fusion360 zeigt meist die SchenkellÃ¤nge an, aber hier haben wir keine "Chamfer Dimension".
        # Wir fÃ¼gen einfach die LÃ¤nge der neuen Linie hinzu, damit man sie Ã¤ndern kann.
        
        # Hinweis: Bei 'Equal Distance' Chamfer ist die LinienlÃ¤nge = dist * sqrt(2 * (1 - cos(angle))).
        # Das ist kompliziert zu bemaÃŸen. 
        # Besser: Wir fÃ¼gen KEINE direkte BemaÃŸung an die schrÃ¤ge Linie an, da das oft krumme Werte sind,
        # SONDERN wir lassen den Nutzer es sehen. 
        # Aber die Anforderung war "sollte er auch hinschreiben".
        # Da wir "Schenkel-LÃ¤nge" (Distance) eingegeben haben, ist es am intuitivsten, 
        # wenn wir nichts tun ODER eine BemaÃŸung hinzufÃ¼gen.
        # Da unsere Constraints aktuell nur "Line Length" kÃ¶nnen und nicht "Point to Point distance along vector",
        # ist die LÃ¤nge der Fasenlinie der einzige Wert, den wir anzeigen kÃ¶nnen.
        
        actual_len = math.hypot(c2_x - c1_x, c2_y - c1_y)
        self.sketch.add_length(chamfer_line, actual_len)
        
        self.status_message.emit(tr("Chamfer created"))
        return True
    
    def _handle_dimension(self, pos, snap_type):
        """BemaÃŸungstool - Modernisiert (Kein QInputDialog mehr!)"""
        
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
            # Wenn Input bestÃ¤tigt wurde, anwenden
            if new_val is not None and abs(new_val - current) > 0.001:
                 self._save_undo()
                 constraint = self.sketch.add_length(line, new_val)
                 # Formel-Binding: Rohtext speichern wenn kein reiner Float
                 if constraint:
                     raw = self.dim_input.get_raw_texts().get('value', '')
                     try:
                         float(raw.replace(',', '.'))
                     except ValueError:
                         constraint.formula = raw
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
                 constraint = self.sketch.add_radius(circle, new_val)
                 if constraint:
                     raw = self.dim_input.get_raw_texts().get('value', '')
                     try:
                         float(raw.replace(',', '.'))
                     except ValueError:
                         constraint.formula = raw
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
            
            # PrÃ¼fen ob Linie schon existiert (um Duplikate zu vermeiden)
            # Das ist wichtig fÃ¼r UX, sonst stackt man 10 Linien Ã¼bereinander
            for l in self.sketch.lines:
                # PrÃ¼fe Endpunkte (ungefÃ¤hre Gleichheit)
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
            # Projizierte Geometrie sollte fixiert sein, da sie an 3D hÃ¤ngt
            self.sketch.add_fixed(line.start)
            self.sketch.add_fixed(line.end)
            # Optional: Wir kÃ¶nnten ein spezielles Flag 'projected' einfÃ¼hren, 
            # aber 'fixed' Punkte reichen fÃ¼r die Logik vorerst.
            
            self.sketched_changed.emit()
            self._find_closed_profiles()
            self.status_message.emit(tr("Edge projected"))
            
        else:
            self.status_message.emit(tr("Hover over a background edge to project"))

            
    def _handle_dimension_angle(self, pos, snap_type):
        """WinkelbemaÃŸung - Modernisiert"""
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
                    constraint = self.sketch.add_angle(l1, line, new_val)
                    if constraint:
                        raw = self.dim_input.get_raw_texts().get('angle', '')
                        try:
                            float(raw.replace(',', '.'))
                        except ValueError:
                            constraint.formula = raw
                    self._solve_async()
                    self.sketched_changed.emit()
                    self._find_closed_profiles()
                    self._cancel_tool()
                else:
                    fields = [("Angle", "angle", current_angle, "Â°")]
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
            # Automatisch COINCIDENT Constraints fÃ¼r nahe Punkte hinzufÃ¼gen
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
    
    def _ensure_coincident_for_line(self, line, tolerance=None):
        """Alte Funktion - verwende _merge_nearby_endpoints stattdessen"""
        self._merge_nearby_endpoints(line, tolerance)
    
    def _merge_nearby_endpoints(self, line, tolerance=None):
        """
        Vereint nahe Punkte mit existierenden Punkten (wie Fusion360).
        Ersetzt Linien-Endpunkte durch existierende Punkte wenn sie nah genug sind.
        """
        if tolerance is None:
            tolerance = self._adaptive_world_tolerance(scale=0.4, min_world=0.05, max_world=1.5)

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
                        
                        # Fertig fÃ¼r diesen Endpunkt
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
        Rotiert die zweite Linie VOR dem Constraint ungefÃ¤hr senkrecht,
        damit der Solver besser konvergiert und keine Ecken "wegrutschen".
        """
        line = self._find_line_at(pos)
        if not line:
            if hasattr(self, 'show_message'):
                self.show_message("Linie auswÃ¤hlen", 2000)
            else:
                self.status_message.emit(tr("Select first line"))
            return

        if self.tool_step == 0:
            self.tool_data['line1'] = line
            self.tool_step = 1
            if hasattr(self, 'show_message'):
                self.show_message("Zweite Linie auswÃ¤hlen", 2000)
            else:
                self.status_message.emit(tr("Select second line"))
        else:
            l1 = self.tool_data.get('line1')
            if l1 and line != l1:
                self._save_undo()

                # === PRE-ROTATION: Linie 2 ungefÃ¤hr senkrecht zu Linie 1 rotieren ===
                # Berechne aktuellen Winkel von l1
                dx1 = l1.end.x - l1.start.x
                dy1 = l1.end.y - l1.start.y
                angle1 = math.atan2(dy1, dx1)

                # Berechne aktuellen Winkel von l2
                dx2 = line.end.x - line.start.x
                dy2 = line.end.y - line.start.y
                angle2 = math.atan2(dy2, dx2)
                length2 = math.hypot(dx2, dy2)

                # Zielwinkel: 90Â° zu l1 (nehme den nÃ¤heren der beiden MÃ¶glichkeiten)
                target_angle_a = angle1 + math.pi / 2
                target_angle_b = angle1 - math.pi / 2

                # Normalisiere Winkel auf [-pi, pi]
                def normalize_angle(a):
                    while a > math.pi: a -= 2 * math.pi
                    while a < -math.pi: a += 2 * math.pi
                    return a

                diff_a = abs(normalize_angle(target_angle_a - angle2))
                diff_b = abs(normalize_angle(target_angle_b - angle2))

                # WÃ¤hle den Winkel mit kleinerer Rotation
                target_angle = target_angle_a if diff_a < diff_b else target_angle_b

                # Rotiere l2 um seinen Startpunkt auf den Zielwinkel
                # (nur wenn Abweichung > 5Â°, um unnÃ¶tige Ã„nderungen zu vermeiden)
                rotation_needed = abs(normalize_angle(target_angle - angle2))
                if rotation_needed > math.radians(5):
                    new_end_x = line.start.x + length2 * math.cos(target_angle)
                    new_end_y = line.start.y + length2 * math.sin(target_angle)
                    line.end.x = new_end_x
                    line.end.y = new_end_y
                    logger.debug(f"Pre-rotated line by {math.degrees(rotation_needed):.1f}Â° for perpendicular")

                # Constraint hinzufÃ¼gen und lÃ¶sen
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
        """Tangent Constraint: Linie tangential an Kreis/Arc oder Kreis/Arc tangential aneinander"""
        from loguru import logger
        from PySide6.QtGui import QColor

        # WICHTIG: FÃ¼r Constraint-Tools brauchen wir die originale Mausposition,
        # nicht die gesnappte Position. Grid-Snap wÃ¼rde sonst die Entity-Suche verhindern.
        original_pos = self.mouse_world

        line = self._find_line_at(original_pos)
        circle = self._find_circle_at(original_pos)
        arc = self._find_arc_at(original_pos)  # Phase: Arc-Support fÃ¼r Tangent

        logger.debug(f"[TANGENT] Step={self.tool_step}, pos={pos.x():.1f},{pos.y():.1f}, orig={original_pos.x():.1f},{original_pos.y():.1f}")
        logger.debug(f"[TANGENT] Found: line={line is not None}, circle={circle is not None}, arc={arc is not None}")

        if self.tool_step == 0:
            if line:
                self.tool_data['elem1'] = ('line', line)
                self._highlight_constraint_entity(line)  # Visual Feedback
                self.tool_step = 1
                if hasattr(self, 'show_message'):
                    self.show_message(tr("Line selected - click circle or arc"), 3000, QColor(100, 200, 255))
                self.status_message.emit(tr("Line selected - now select circle or arc"))
            elif circle:
                self.tool_data['elem1'] = ('circle', circle)
                self._highlight_constraint_entity(circle)  # Visual Feedback
                self.tool_step = 1
                if hasattr(self, 'show_message'):
                    self.show_message(tr("Circle selected - click line, circle or arc"), 3000, QColor(100, 200, 255))
                self.status_message.emit(tr("Circle selected - now select line, circle or arc"))
            elif arc:
                self.tool_data['elem1'] = ('arc', arc)
                self._highlight_constraint_entity(arc)  # Visual Feedback
                self.tool_step = 1
                if hasattr(self, 'show_message'):
                    self.show_message(tr("Arc selected - click line, circle or arc"), 3000, QColor(100, 200, 255))
                self.status_message.emit(tr("Arc selected - now select line, circle or arc"))
            else:
                if hasattr(self, 'show_message'):
                    self.show_message(tr("Click on line, circle or arc"), 2000, QColor(255, 200, 100))
                self.status_message.emit(tr("Select line, circle or arc"))
        else:
            elem1_type, elem1 = self.tool_data.get('elem1', (None, None))
            elem2 = None  # Die zweite Entity
            elem2_type = None

            logger.debug(f"[TANGENT] Step 1: elem1_type={elem1_type}, line={line}, circle={circle}, arc={arc}")

            # Bestimme elem2 basierend auf was gefunden wurde
            if circle:
                elem2, elem2_type = circle, 'circle'
            elif arc:
                elem2, elem2_type = arc, 'arc'
            elif line:
                elem2, elem2_type = line, 'line'

            # Validierung: elem2 muss existieren und darf nicht elem1 sein
            if elem2 is None or elem2 is elem1:
                logger.warning(f"[TANGENT] Invalid: elem2={elem2}, elem1={elem1}")
                if hasattr(self, 'show_message'):
                    self.show_message(tr("Invalid combination!"), 2000, QColor(255, 100, 100))
                self.status_message.emit(tr("Invalid combination - select different elements"))
                self._clear_constraint_highlight()
                self._cancel_tool()
                return

            # Validierung: Line-Line ist nicht tangent-fÃ¤hig
            if elem1_type == 'line' and elem2_type == 'line':
                logger.warning(f"[TANGENT] Line-Line not supported")
                if hasattr(self, 'show_message'):
                    self.show_message(tr("Tangent needs circle or arc!"), 2000, QColor(255, 100, 100))
                self.status_message.emit(tr("Tangent requires at least one circle or arc"))
                self._clear_constraint_highlight()
                self._cancel_tool()
                return

            self._save_undo()

            # Pre-Positionierung fÃ¼r bessere Solver-Konvergenz
            # (Geometrie wird UNGEFÃ„HR tangent positioniert, dann Ã¼bernimmt der Constraint)
            if elem1_type == 'line' and elem2_type in ('circle', 'arc'):
                self._make_line_tangent_to_circle(elem1, elem2)
            elif elem2_type == 'line' and elem1_type in ('circle', 'arc'):
                self._make_line_tangent_to_circle(elem2, elem1)
            elif elem1_type in ('circle', 'arc') and elem2_type in ('circle', 'arc'):
                self._make_circles_tangent(elem1, elem2)

            # === ECHTER CONSTRAINT HINZUFÃœGEN ===
            constraint = self.sketch.add_tangent(elem1, elem2)

            if constraint:
                logger.info(f"[TANGENT] Constraint created: {elem1_type} â†” {elem2_type}")
                result = self.sketch.solve()
                self.sketched_changed.emit()
                self._find_closed_profiles()
                self.update()
                if hasattr(self, 'show_message'):
                    self.show_message(tr("Tangent applied!"), 2000, QColor(100, 255, 100))
                self.status_message.emit(tr("Tangent constraint applied"))
            else:
                logger.warning(f"[TANGENT] Invalid combination: elem1_type={elem1_type}, line={line is not None}, circle={circle is not None}, arc={arc is not None}")
                if hasattr(self, 'show_message'):
                    self.show_message(tr("Invalid combination!"), 2000, QColor(255, 100, 100))
                self.status_message.emit(tr("Invalid combination - select different elements"))

            self._clear_constraint_highlight()  # Visual Feedback zurÃ¼cksetzen
            self._cancel_tool()
    
    def _make_line_tangent_to_circle(self, line, circle):
        """Macht eine Linie tangential zu einem Kreis"""
        # Berechne den nÃ¤chsten Punkt auf der Linie zum Kreismittelpunkt
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
        
        # NÃ¤chster Punkt auf der Linie
        px, py = x1 + t * dx, y1 + t * dy
        
        # Aktuelle Distanz zum Kreis
        dist = math.hypot(px - cx, py - cy)
        
        if dist < 0.001:
            return
        
        # Verschiebe die Linie so dass sie tangential ist
        # Richtung vom Mittelpunkt zum nÃ¤chsten Punkt
        nx, ny = (px - cx) / dist, (py - cy) / dist
        
        # Zielabstand = Radius
        offset = circle.radius - dist
        
        # Verschiebe beide Endpunkte
        line.start.x += nx * offset
        line.start.y += ny * offset
        line.end.x += nx * offset
        line.end.y += ny * offset
    
    def _make_circles_tangent(self, c1, c2):
        """Macht zwei Kreise tangential (berÃ¼hrend)"""
        cx1, cy1, r1 = c1.center.x, c1.center.y, c1.radius
        cx2, cy2, r2 = c2.center.x, c2.center.y, c2.radius
        
        # Aktuelle Distanz
        dist = math.hypot(cx2 - cx1, cy2 - cy1)
        if dist < 0.001:
            return
        
        # Richtung von c1 nach c2
        dx, dy = (cx2 - cx1) / dist, (cy2 - cy1) / dist
        
        # Zieldistanz (auÃŸen tangent)
        target_dist = r1 + r2
        
        # Verschiebe c2
        c2.center.x = cx1 + dx * target_dist
        c2.center.y = cy1 + dy * target_dist
    
    
    
    def _handle_pattern_circular(self, pos, snap_type):
        """
        KreisfÃ¶rmiges Muster.
        UX:
        1. Selektion.
        2. Tool aktivieren.
        3. Zentrum wÃ¤hlen (Snap!).
        4. Tab fÃ¼r Anzahl/Winkel.
        """
        if not self.selected_lines and not self.selected_circles and not self.selected_arcs:
            if hasattr(self, 'show_message'):
                self.show_message("Bitte erst Elemente auswÃ¤hlen!", 2000, QColor(255, 200, 100))
            self.set_tool(SketchTool.SELECT)
            return

        if self.tool_step == 0:
            # Zentrum wÃ¤hlen
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
            # Klick im Canvas (woanders als Zentrum) bestÃ¤tigt auch
            self._apply_circular_pattern()
    
    def _handle_gear(self, pos, snap_type, snap_entity=None):
        """
        Erweitertes Zahnrad-Tool (CAD Kompatibel).
        UnterstÃ¼tzt Backlash, Profilverschiebung und Bohrung.
        """
        # --- 1. Dialog Setup ---
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Stirnrad (Spur Gear)"))
        dialog.setFixedWidth(340) # Etwas breiter fÃ¼r mehr Optionen
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
        spin_angle.setSuffix(" Â°")

        # --- Erweiterte Parameter (Wichtig!) ---
        
        # Zahnflankenspiel (Backlash) - Wichtig fÃ¼r 3D Druck
        spin_backlash = QDoubleSpinBox()
        spin_backlash.setRange(0.0, 2.0)
        spin_backlash.setValue(0.15) # Guter Default fÃ¼r 3D Druck
        spin_backlash.setSingleStep(0.05)
        spin_backlash.setSuffix(" mm")
        spin_backlash.setToolTip("Verringert die Zahndicke fÃ¼r Spielraum")

        # Bohrung
        spin_hole = QDoubleSpinBox()
        spin_hole.setRange(0.0, 1000.0)
        spin_hole.setValue(6.0) # Standard Welle
        spin_hole.setSuffix(" mm")

        # Profilverschiebung (x) - Wichtig bei wenig ZÃ¤hnen (<17)
        spin_shift = QDoubleSpinBox()
        spin_shift.setRange(-1.0, 1.0)
        spin_shift.setValue(0.0)
        spin_shift.setSingleStep(0.1)
        spin_shift.setToolTip("Positiv: StÃ¤rkerer FuÃŸ, grÃ¶ÃŸerer Durchmesser.\nNÃ¶tig bei < 17 ZÃ¤hnen um Unterschnitt zu vermeiden.")

        # FuÃŸrundung (Fillet)
        spin_fillet = QDoubleSpinBox()
        spin_fillet.setRange(0.0, 5.0)
        spin_fillet.setValue(0.5) # Leichte Rundung
        spin_fillet.setSuffix(" mm")

        # Performance
        check_lowpoly = QCheckBox(tr("Vorschau (Low Poly)"))
        check_lowpoly.setChecked(True)

        # Layout bauen
        form.addRow(tr("Modul:"), spin_module)
        form.addRow(tr("ZÃ¤hne:"), spin_teeth)
        form.addRow(tr("Druckwinkel:"), spin_angle)
        form.addRow(tr("-----------"), QLabel("")) # Trenner
        form.addRow(tr("Bohrung âŒ€:"), spin_hole)
        form.addRow(tr("Spiel (Backlash):"), spin_backlash)
        form.addRow(tr("Profilverschiebung:"), spin_shift)
        form.addRow(tr("FuÃŸradius:"), spin_fillet)
        form.addRow("", check_lowpoly)
        
        layout.addLayout(form)
        
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        layout.addWidget(btns)

        # --- Live Vorschau ---
        def update_preview():
            self._remove_preview_elements()
            
            # Parameter dictionary fÃ¼r saubereren Aufruf
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
                'low_poly': False # Immer High Quality fÃ¼r Final
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
        # Listenkopie erstellen, da wir waehrend der Iteration loeschen
        lines_to_remove = [l for l in self.sketch.lines if hasattr(l, 'is_preview') and l.is_preview]
        circles_to_remove = [c for c in self.sketch.circles if hasattr(c, 'is_preview') and c.is_preview]

        for l in lines_to_remove:
            if l in self.sketch.lines: self.sketch.lines.remove(l)
        for c in circles_to_remove:
            if c in self.sketch.circles: self.sketch.circles.remove(c)

        # Preview-Punkte entfernen, sofern sie nicht mehr referenziert sind
        referenced = set()
        for line in self.sketch.lines:
            referenced.add(id(line.start))
            referenced.add(id(line.end))
        for circle in self.sketch.circles:
            referenced.add(id(circle.center))
        for arc in self.sketch.arcs:
            referenced.add(id(arc.center))

        preview_points = [p for p in self.sketch.points if hasattr(p, 'is_preview') and p.is_preview]
        for p in preview_points:
            if id(p) not in referenced and p in self.sketch.points:
                self.sketch.points.remove(p)

    def _generate_involute_gear(self, cx, cy, module, teeth, pressure_angle, 
                              backlash=0.0, hole_diam=0.0, profile_shift=0.0, fillet=0.0,
                              preview=False, low_poly=True):
        """
        Umfassender Generator fÃ¼r Evolventen-Verzahnung.
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
        
        # Kopf- und FuÃŸhÃ¶henfaktoren (Standard 1.0 und 1.25)
        # Profilverschiebung (x) Ã¤ndert diese Durchmesser
        ha = (1.0 + profile_shift) * module  # Addendum (Kopf)
        hf = (1.25 - profile_shift) * module # Dedendum (FuÃŸ)
        
        # Durchmesser
        da = d + 2 * ha # Kopfkreis (Tip)
        df = d - 2 * hf # FuÃŸkreis (Root)
        
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
        
        # Winkel im BogenmaÃŸ am Teilkreis fÃ¼r die halbe Zahndicke
        psi = s_act / (2.0 * r) 
        
        # Involute Funktion: inv(alpha) = tan(alpha) - alpha
        inv_alpha = tan_alpha - alpha
        
        # Der Winkel-Offset fÃ¼r den Start der Evolvente (am Grundkreis)
        # Theta_start = psi + inv_alpha
        half_tooth_angle = psi + inv_alpha
        # --- 3. Profilberechnung (Eine Flanke) ---
        def _calc_flank_steps(teeth_count, module_size, low_poly_mode):
            # Keep point counts bounded so multiple gears stay responsive.
            base_points = 10 if low_poly_mode else 16  # points per tooth (both flanks)
            pitch_diameter = max(1e-6, module_size * teeth_count)
            size_factor = math.sqrt(pitch_diameter / 40.0)
            size_factor = max(0.8, min(1.3, size_factor))
            points_per_tooth = int(base_points * size_factor)

            # Hard cap total points
            max_total_points = 700 if low_poly_mode else 1400
            max_points_per_tooth = max(6, int(max_total_points / max(1, teeth_count)))
            points_per_tooth = min(points_per_tooth, max_points_per_tooth)

            # points_per_tooth = 2 * (steps + 1)
            steps = max(2 if low_poly_mode else 4, (points_per_tooth // 2) - 1)
            return min(8 if low_poly_mode else 12, steps)

        steps = _calc_flank_steps(teeth, module, low_poly)
        flank_points = []
        # Wir berechnen Punkte vom Grundkreis (rb) bis Kopfkreis (ra)
        # Achtung: Wenn FuÃŸkreis (rf) < Grundkreis (rb), startet Evolvente erst bei rb.
        # Darunter ist es eine Gerade oder ein Fillet.
        
        start_r = max(rb, rf)
        
        for i in range(steps + 1):
            # Nicht-lineare Verteilung fÃ¼r schÃ¶nere Kurven an der Basis
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
            
        # --- 4. FuÃŸbereich (Root / Undercut / Fillet) ---
        # Wenn der FuÃŸkreis kleiner als der Grundkreis ist, mÃ¼ssen wir den Zahn nach unten verlÃ¤ngern.
        # Fusion nutzt hier komplexe Trochoiden fÃ¼r Unterschnitt. Wir nutzen eine radiale Linie + Fillet.
        
        if rf < rb:
            # Einfache VerlÃ¤ngerung: Radial vom FuÃŸkreis zum Start der Evolvente
            # Mit Fillet: Wir runden den Ãœbergang vom FuÃŸkreis zur Flanke ab.
            
            # Winkel am Start der Evolvente
            angle_at_base = flank_points[0][1]
            
            if fillet > 0.01 and not low_poly:
                # Simuliertes Fillet: Ein Punkt zwischen (rf, angle) und (rb, angle)
                # Wir gehen etwas in den Zahnzwischenraum (Winkel wird grÃ¶ÃŸer)
                # ZahnlÃ¼cke Mitte ist bei PI/z. 
                # Das ist zu komplex fÃ¼r schnelles Skripting. 
                # Wir machen eine direkte Linie zum FuÃŸkreis.
                flank_points.insert(0, (rf, angle_at_base))
            else:
                # Harter Ãœbergang
                flank_points.insert(0, (rf, angle_at_base))

        # --- 5. Spiegeln und Zusammenbauen ---
        tooth_poly = []
        
        # Linke Flanke (gespiegelt, Winkel negativ) -> Von FuÃŸ nach Kopf
        # flank_points ist [FuÃŸ ... Kopf]. 
        # Wir brauchen [FuÃŸ ... Kopf] aber mit negativen Winkeln?
        # Nein, fÃ¼r CCW Polygon: 
        # Center -> (Rechte Flanke) -> Tip -> (Linke Flanke) -> Center
        # Aber wir bauen das ganze Rad.
        
        # Strategie: Wir bauen die Punkte fÃ¼r EINEN Zahn (Rechts + Links)
        # und rotieren diesen.
        
        # Linke Flanke (Winkel = -theta). Von Root zu Tip?
        # Sagen wir 0Â° ist die Zahnmitte.
        # Rechte Flanke ist bei +Theta. Linke bei -Theta.
        # CCW Reihenfolge: Rechte Flanke (Tip->Root) -> Root Arc -> Linke Flanke (Root->Tip) -> Tip Arc
        
        # 1. Rechte Flanke (AuÃŸen nach Innen)
        for r, theta in reversed(flank_points):
            tooth_poly.append((r, theta))
            
        # 2. FuÃŸkreis (Verbindung zur linken Flanke im GLEICHEN Zahn ist falsch, das wÃ¤re durch den Zahn durch)
        # Wir verbinden zum NÃ„CHSTEN Zahn Ã¼ber den FuÃŸkreis.
        # Also definieren wir nur das Profil EINES Zahns.
        # Profil: Tip Right -> ... -> Root Right -> (LÃ¼cke) -> Root Left -> ... Tip Left
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
        def _dist_point_line(px, py, ax, ay, bx, by):
            dx = bx - ax
            dy = by - ay
            if abs(dx) < 1e-12 and abs(dy) < 1e-12:
                return math.hypot(px - ax, py - ay)
            t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
            t = max(0.0, min(1.0, t))
            proj_x = ax + t * dx
            proj_y = ay + t * dy
            return math.hypot(px - proj_x, py - proj_y)

        def _rdp(points, eps):
            if len(points) < 3:
                return points
            ax, ay = points[0]
            bx, by = points[-1]
            max_dist = -1.0
            idx = -1
            for i in range(1, len(points) - 1):
                px, py = points[i]
                dist = _dist_point_line(px, py, ax, ay, bx, by)
                if dist > max_dist:
                    max_dist = dist
                    idx = i
            if max_dist <= eps or idx == -1:
                return [points[0], points[-1]]
            left = _rdp(points[:idx + 1], eps)
            right = _rdp(points[idx:], eps)
            return left[:-1] + right

        def _simplify_polyline(points, eps):
            if len(points) < 5:
                return points
            # Remove nearly-duplicate consecutive points
            cleaned = [points[0]]
            for x, y in points[1:]:
                lx, ly = cleaned[-1]
                if math.hypot(x - lx, y - ly) > max(1e-6, eps * 0.2):
                    cleaned.append((x, y))
            if len(cleaned) < 5:
                return cleaned
            simplified = _rdp(cleaned, eps)
            return simplified if len(simplified) >= 4 else cleaned

        # Base tooth in cartesian (beta = 0)
        base_tooth = [(r * math.cos(theta), r * math.sin(theta)) for r, theta in single_tooth]

        # Simplify tooth polyline to reduce total points
        simplify_tol = max(0.02, module * (0.06 if low_poly else 0.03))
        base_tooth = _simplify_polyline(base_tooth, simplify_tol)

        # Cap total points by relaxing tolerance if needed
        max_total_points = 200 if low_poly else 300
        total_points = len(base_tooth) * teeth
        if total_points > max_total_points:
            factor = total_points / max_total_points
            base_tooth = _simplify_polyline(base_tooth, simplify_tol * factor)

        all_world_points = []
        angle_step = (2 * math.pi) / teeth

        for i in range(teeth):
            beta = i * angle_step
            cos_b = math.cos(beta)
            sin_b = math.sin(beta)

            for x, y in base_tooth:
                px = cx + x * cos_b - y * sin_b
                py = cy + x * sin_b + y * cos_b
                all_world_points.append((px, py))

        # --- 7. Zeichnen ---
        lines = []
        circles = []

        point_objs = [Point2D(px, py) for px, py in all_world_points]
        if preview:
            for pt in point_objs:
                pt.is_preview = True

        self.sketch.points.extend(point_objs)

        for i in range(len(point_objs)):
            p1 = point_objs[i]
            p2 = point_objs[(i + 1) % len(point_objs)]
            l = Line2D(p1, p2)
            if preview:
                l.is_preview = True
            lines.append(l)
            self.sketch.lines.append(l)

        self.sketch.invalidate_profiles()

        # Bohrung
        if hole_diam > 0.01:
            h = self.sketch.add_circle(cx, cy, hole_diam / 2.0)
            if preview:
                h.is_preview = True
                h.center.is_preview = True
            circles.append(h)
            
        # Teilkreis als Konstruktionslinie (Hilfreich)
        if preview and not low_poly:
            pc = self.sketch.add_circle(cx, cy, r, construction=True)
            pc.is_preview = True
            pc.center.is_preview = True
            circles.append(pc)

        return lines, circles
    
    def _handle_star(self, pos, snap_type):
        """
        Stern-Werkzeug mit modernem Input.
        """
        if self.tool_step == 0:
            self.tool_points = [pos]
            self.tool_step = 1
            self.status_message.emit(tr("Star") + " | Tab=" + tr("Parameters") + " | Enter=" + tr("Confirm"))
            # Note: Dimension input is now handled by _show_dimension_input()
            # Preview will be shown in the renderer
        else:
            # Click again creates the star
            self._create_star_geometry()

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
            
            # SchlÃ¼sselweite mit Toleranz
            size_name = self.nut_size_names[self.nut_size_index]
            sw = self.nut_sizes[size_name] + self.nut_tolerance
            
            # Schraubendurchmesser aus dem Namen extrahieren (M3 -> 3mm, M2.5 -> 2.5mm)
            screw_diameter = float(size_name[1:])
            hole_radius = (screw_diameter + self.nut_tolerance) / 2
            
            # Sechskant: Radius zum Eckpunkt = SW / sqrt(3)
            hex_radius = sw / math.sqrt(3)
            
            self._save_undo()
            angle_offset = rotation_angle + math.radians(30)
            _, const_circle = self.sketch.add_regular_polygon(
                center.x(), center.y(), hex_radius, 6,
                angle_offset=angle_offset,
                construction=self.construction_mode
            )
            self.sketch.add_radius(const_circle, hex_radius)
            hole_circle = self.sketch.add_circle(center.x(), center.y(), hole_radius, construction=self.construction_mode)
            self.sketch.add_radius(hole_circle, hole_radius)
            self.sketch.add_concentric(const_circle, hole_circle)
            self.sketch.solve()
            self.sketched_changed.emit()
            self._find_closed_profiles()
            
            # Info anzeigen
            self.status_message.emit(f"{size_name} " + tr("Nut") + f" (SW {sw:.2f}mm, " + tr("Hole") + f" âŒ€{screw_diameter + self.nut_tolerance:.2f}mm)")
            self._cancel_tool()
    
    def _handle_text(self, pos, snap_type):
        # Text tool with live preview and view-rotation compensation.
        # --- 1. Dialog ---
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Text erstellen"))
        dialog.setMinimumWidth(300)
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
        
        # Eingabefelder
        txt_input = QLineEdit("Text")
        font_input = QFontComboBox()
        font_input.setCurrentFont(QFont("Arial"))
        
        size_input = QDoubleSpinBox()
        size_input.setRange(1.0, 500.0)
        size_input.setValue(10.0)
        size_input.setSuffix(" mm")
        
        form.addRow(tr("Inhalt:"), txt_input)
        form.addRow(tr("Schriftart:"), font_input)
        form.addRow(tr("Höhe:"), size_input)
        
        layout.addLayout(form)
        
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        layout.addWidget(btns)

        def _build_text_geometry(preview=False):
            text_str = txt_input.text()
            if not text_str:
                return 0

            desired_height = size_input.value()
            if desired_height <= 0:
                return 0

            selected_font = font_input.currentFont()
            selected_font.setPointSize(96)
            selected_font.setStyleStrategy(QFont.PreferOutline)

            path = QPainterPath()
            path.addText(0, 0, selected_font, text_str)
            path = path.simplified()

            rect = path.boundingRect()
            if rect.height() <= 0 or rect.width() <= 0:
                return 0

            scale_factor = desired_height / rect.height()
            polygons = path.toSubpathPolygons(QTransform())
            if not polygons:
                return 0

            cx = rect.x() + rect.width() / 2.0
            cy = rect.y() + rect.height() / 2.0

            view_rot = getattr(self, "view_rotation", 0) or 0
            # Inverse rotation keeps text upright in the rotated view
            rot = -math.radians(view_rot % 360)
            cos_a = math.cos(rot)
            sin_a = math.sin(rot)

            # Preview and final use nearly identical tolerances so both look the same.
            if preview:
                min_seg = max(0.05, desired_height * 0.002)
                simplify_tol = max(0.05, min(0.35, desired_height * 0.006))
                max_pts = max(50, int(180 / max(len(polygons), 1)))
            else:
                min_seg = max(0.05, desired_height * 0.002)
                simplify_tol = max(0.05, min(0.30, desired_height * 0.005))
                max_pts = max(80, int(220 / max(len(polygons), 1)))

            def _dist(a, b):
                return math.hypot(a[0] - b[0], a[1] - b[1])

            def _perp_dist(p, a, b):
                ax, ay = a
                bx, by = b
                px, py = p
                dx = bx - ax
                dy = by - ay
                if dx == 0 and dy == 0:
                    return math.hypot(px - ax, py - ay)
                t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
                projx = ax + t * dx
                projy = ay + t * dy
                return math.hypot(px - projx, py - projy)

            def _rdp(points, eps):
                if len(points) < 3:
                    return points
                a = points[0]
                b = points[-1]
                max_d = 0.0
                idx = -1
                for i in range(1, len(points) - 1):
                    d = _perp_dist(points[i], a, b)
                    if d > max_d:
                        max_d = d
                        idx = i
                if max_d > eps and idx != -1:
                    left = _rdp(points[:idx + 1], eps)
                    right = _rdp(points[idx:], eps)
                    return left[:-1] + right
                return [a, b]

            def _simplify(points, eps, min_seg):
                if not points:
                    return []
                filtered = [points[0]]
                for p in points[1:]:
                    if _dist(p, filtered[-1]) >= min_seg:
                        filtered.append(p)
                if len(filtered) < 3:
                    return filtered
                return _rdp(filtered, eps)

            def _decimate(points, max_pts):
                if len(points) <= max_pts:
                    return points
                step = int(math.ceil(len(points) / float(max_pts)))
                dec = points[::step]
                if len(dec) < 3:
                    return points[:3]
                return dec

            count = 0
            for poly in polygons:
                if poly.count() < 3:
                    continue

                raw = []
                for p in poly:
                    lx = (p.x() - cx) * scale_factor
                    ly = (p.y() - cy) * scale_factor
                    ly = -ly

                    rx = lx * cos_a - ly * sin_a
                    ry = lx * sin_a + ly * cos_a

                    raw.append((pos.x() + rx, pos.y() + ry))

                if len(raw) > 1 and _dist(raw[0], raw[-1]) < min_seg:
                    raw = raw[:-1]

                simp = _simplify(raw, simplify_tol, min_seg)
                simp = _decimate(simp, max_pts)

                if len(simp) < 3:
                    continue

                pts = [Point2D(x, y) for x, y in simp]
                for pt in pts:
                    pt.construction = self.construction_mode
                    if preview:
                        pt.is_preview = True

                self.sketch.points.extend(pts)

                for i in range(len(pts)):
                    p1 = pts[i]
                    p2 = pts[(i + 1) % len(pts)]
                    if math.hypot(p1.x - p2.x, p1.y - p2.y) < min_seg:
                        continue
                    line = Line2D(p1, p2, construction=self.construction_mode)
                    if preview:
                        line.is_preview = True
                    self.sketch.lines.append(line)
                    count += 1

            return count

        preview_timer = QTimer(dialog)
        preview_timer.setSingleShot(True)

        def _update_preview():
            self._remove_preview_elements()
            _build_text_geometry(preview=True)
            self.sketch.invalidate_profiles()
            self.sketched_changed.emit()

        def _schedule_preview():
            preview_timer.stop()
            preview_timer.start(150)

        preview_timer.timeout.connect(_update_preview)
        txt_input.textChanged.connect(_schedule_preview)
        font_input.currentFontChanged.connect(_schedule_preview)
        size_input.valueChanged.connect(_schedule_preview)

        _update_preview()

        if dialog.exec() != QDialog.Accepted:
            preview_timer.stop()
            self._remove_preview_elements()
            self.sketched_changed.emit()
            self._cancel_tool()
            return

        preview_timer.stop()
        self._remove_preview_elements()
        self._save_undo()

        text_str = txt_input.text()
        if not text_str:
            self._cancel_tool()
            return

        count = _build_text_geometry(preview=False)
        self.sketch.invalidate_profiles()
        self.sketched_changed.emit()
        self._find_closed_profiles()
        self.status_message.emit(tr(f"Text '{text_str}' erstellt ({count} Linien)"))
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

    # ==================== CANVAS (Bildreferenz) ====================

    def _handle_canvas(self, pos, snap_type, snap_entity=None):
        """Canvas-Tool: Bild als Hintergrund-Referenz laden und platzieren."""
        from PySide6.QtWidgets import QFileDialog
        from PySide6.QtGui import QPixmap

        if self.tool_step == 0:
            path, _ = QFileDialog.getOpenFileName(
                self, tr("Bildreferenz laden"),
                "",
                tr("Bilder") + " (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;All (*)"
            )
            if not path:
                self.set_tool(SketchTool.SELECT)
                return

            pixmap = QPixmap(path)
            if pixmap.isNull():
                logger.error(f"Bild konnte nicht geladen werden: {path}")
                self.status_message.emit(tr("Fehler: Bild konnte nicht geladen werden"))
                self.set_tool(SketchTool.SELECT)
                return

            self._save_undo()
            self.canvas_image = pixmap
            self.canvas_file_path = path

            # Default: 100mm Breite, HÃ¶he aus Aspect Ratio
            default_width = 100.0
            aspect = pixmap.height() / max(pixmap.width(), 1)
            default_height = default_width * aspect

            # Zentriert auf Klickposition
            self.canvas_world_rect = QRectF(
                pos.x() - default_width / 2,
                pos.y() - default_height / 2,
                default_width,
                default_height
            )
            self.canvas_visible = True

            logger.info(f"Canvas geladen: {path} ({pixmap.width()}x{pixmap.height()}px, {default_width:.0f}x{default_height:.0f}mm)")
            self.status_message.emit(tr("Canvas platziert") + f" ({default_width:.0f}x{default_height:.0f}mm)")
            self._draw_hud(tr("Canvas platziert â€” Rechtsklick fÃ¼r Optionen"))
            self.set_tool(SketchTool.SELECT)
            self.request_update()

    def _canvas_hit_test(self, world_pos):
        """PrÃ¼ft ob world_pos innerhalb des Canvas liegt."""
        if not self.canvas_world_rect or not self.canvas_image:
            return False
        return self.canvas_world_rect.contains(QPointF(world_pos.x(), world_pos.y()))

    def _canvas_start_drag(self, world_pos):
        """Beginnt Canvas-Dragging."""
        if self.canvas_locked or not self._canvas_hit_test(world_pos):
            return False
        self._canvas_dragging = True
        self._canvas_drag_offset = QPointF(
            world_pos.x() - self.canvas_world_rect.x(),
            world_pos.y() - self.canvas_world_rect.y()
        )
        self._save_undo()
        return True

    def _canvas_update_drag(self, world_pos):
        """Aktualisiert Canvas-Position wÃ¤hrend Drag."""
        if not self._canvas_dragging or not self.canvas_world_rect:
            return
        new_x = world_pos.x() - self._canvas_drag_offset.x()
        new_y = world_pos.y() - self._canvas_drag_offset.y()
        self.canvas_world_rect = QRectF(
            new_x, new_y,
            self.canvas_world_rect.width(),
            self.canvas_world_rect.height()
        )
        self.request_update()

    def _canvas_end_drag(self):
        """Beendet Canvas-Dragging."""
        self._canvas_dragging = False

    def canvas_remove(self):
        """Entfernt das Canvas-Bild."""
        self._save_undo()
        self.canvas_image = None
        self.canvas_world_rect = None
        self.canvas_file_path = None
        self._canvas_dragging = False
        logger.info("Canvas entfernt")
        self.request_update()

    def canvas_set_opacity(self, opacity):
        """Setzt Canvas-Deckkraft (0.0â€“1.0)."""
        self.canvas_opacity = max(0.0, min(1.0, opacity))
        self.request_update()

    def canvas_set_size(self, width_mm):
        """Setzt Canvas-Breite in mm (HÃ¶he folgt Aspect Ratio)."""
        if not self.canvas_image or not self.canvas_world_rect:
            return
        aspect = self.canvas_image.height() / max(self.canvas_image.width(), 1)
        cx = self.canvas_world_rect.x() + self.canvas_world_rect.width() / 2
        cy = self.canvas_world_rect.y() + self.canvas_world_rect.height() / 2
        new_h = width_mm * aspect
        self.canvas_world_rect = QRectF(
            cx - width_mm / 2, cy - new_h / 2,
            width_mm, new_h
        )
        self.request_update()

    # --- Kalibrierung (CAD-Style) ---

    def canvas_start_calibration(self):
        """Startet Kalibrierungsmodus: 2 Punkte auf dem Bild klicken, dann reale Distanz eingeben."""
        if not self.canvas_image or not self.canvas_world_rect:
            return
        self._canvas_calibrating = True
        self._canvas_calib_points = []
        self.status_message.emit(tr("Kalibrierung: Ersten Punkt auf dem Bild anklicken"))
        self._draw_hud(tr("Kalibrierung â€” Punkt 1 von 2 setzen"))
        self.request_update()

    def _canvas_calibration_click(self, world_pos):
        """Verarbeitet einen Klick im Kalibrierungsmodus. Gibt True zurÃ¼ck wenn konsumiert."""
        if not self._canvas_calibrating:
            return False

        self._canvas_calib_points.append(QPointF(world_pos.x(), world_pos.y()))

        if len(self._canvas_calib_points) == 1:
            self.status_message.emit(tr("Kalibrierung: Zweiten Punkt auf dem Bild anklicken"))
            self._draw_hud(tr("Kalibrierung â€” Punkt 2 von 2 setzen"))
            self.request_update()
            return True

        if len(self._canvas_calib_points) >= 2:
            p1 = self._canvas_calib_points[0]
            p2 = self._canvas_calib_points[1]
            pixel_dist = math.sqrt((p2.x() - p1.x())**2 + (p2.y() - p1.y())**2)

            if pixel_dist < 0.01:
                self._draw_hud(tr("Punkte zu nah beieinander"))
                self._canvas_calibrating = False
                self._canvas_calib_points = []
                return True

            from PySide6.QtWidgets import QInputDialog
            real_dist, ok = QInputDialog.getDouble(
                self,
                tr("Canvas kalibrieren"),
                tr("Reale Distanz zwischen den Punkten (mm):"),
                value=round(pixel_dist, 2),
                minValue=0.1, maxValue=100000.0, decimals=2
            )

            if ok and real_dist > 0:
                scale_factor = real_dist / pixel_dist
                self._save_undo()

                old_rect = self.canvas_world_rect
                old_cx = old_rect.x() + old_rect.width() / 2
                old_cy = old_rect.y() + old_rect.height() / 2
                new_w = old_rect.width() * scale_factor
                new_h = old_rect.height() * scale_factor
                self.canvas_world_rect = QRectF(
                    old_cx - new_w / 2, old_cy - new_h / 2,
                    new_w, new_h
                )
                logger.info(f"Canvas kalibriert: Faktor {scale_factor:.3f}, {new_w:.1f}x{new_h:.1f}mm")
                self._draw_hud(tr("Canvas kalibriert") + f" ({new_w:.0f}x{new_h:.0f}mm)")
            else:
                self._draw_hud(tr("Kalibrierung abgebrochen"))

            self._canvas_calibrating = False
            self._canvas_calib_points = []
            self.request_update()
            return True

        return False
    
