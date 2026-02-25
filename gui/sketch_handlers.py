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

from sketcher import Point2D, Line2D, Circle2D, Arc2D, Ellipse2D, Constraint, ConstraintType
from i18n import tr
try:
    from gui.sketch_feedback import (
        format_solver_failure_message,
        format_trim_failure_message,
        format_trim_warning_message,
    )
except ImportError:
    try:
        from sketch_feedback import (
            format_solver_failure_message,
            format_trim_failure_message,
            format_trim_warning_message,
        )
    except ImportError:
        from .sketch_feedback import (
            format_solver_failure_message,
            format_trim_failure_message,
            format_trim_warning_message,
        )

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

    @staticmethod
    def _point_to_angle_deg(center: Point2D, point: Point2D) -> float:
        return math.degrees(math.atan2(point.y - center.y, point.x - center.x))

    def _get_valid_formula_from_dim_input(self, key: str):
        """Gibt nur dann Formeltext zurück, wenn er tatsächlich evaluierbar ist."""
        if not hasattr(self, "dim_input") or self.dim_input is None:
            return None

        try:
            raw = (self.dim_input.get_raw_texts().get(key, "") or "").strip()
        except Exception:
            return None

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

    def _build_trim_preview_geometry(self, target, segment):
        """
        Erstellt eine visuelle Vorschau der zu trimmenden Geometrie.
        """
        if (
            target is None
            or segment is None
            or segment.is_full_delete
            or segment.start_point is None
            or segment.end_point is None
        ):
            return []

        if isinstance(target, Line2D):
            return [Line2D(segment.start_point, segment.end_point)]

        if isinstance(target, Circle2D):
            center = Point2D(target.center.x, target.center.y)
            radius = float(getattr(target, "radius", 0.0))
            if radius <= 1e-9:
                return []

            # WICHTIG: Circle-Trim-Segmente koennen ueber 0/360 laufen.
            # Daher die Winkelrichtung ueber Kernel-Parameter ableiten statt nur atan2.
            try:
                start_rad = float(geometry.get_param_on_entity(segment.start_point, target))
                end_rad = float(geometry.get_param_on_entity(segment.end_point, target))
                start_angle = math.degrees(start_rad)
                end_angle = math.degrees(end_rad)
                if end_angle < start_angle:
                    end_angle += 360.0
            except Exception:
                start_angle = self._point_to_angle_deg(center, segment.start_point)
                end_angle = self._point_to_angle_deg(center, segment.end_point)
                if end_angle < start_angle:
                    end_angle += 360.0

            return [
                Arc2D(
                    center=center,
                    radius=radius,
                    start_angle=start_angle,
                    end_angle=end_angle,
                )
            ]

        if isinstance(target, Arc2D):
            center = Point2D(target.center.x, target.center.y)
            radius = float(getattr(target, "radius", 0.0))
            if radius <= 1e-9:
                return []

            start_angle = self._point_to_angle_deg(center, segment.start_point)
            end_angle = self._point_to_angle_deg(center, segment.end_point)
            return [
                Arc2D(
                    center=center,
                    radius=radius,
                    start_angle=start_angle,
                    end_angle=end_angle,
                )
            ]

        return []

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

    def _begin_constraint_transaction(self):
        """
        Sichert den Sketch-Zustand vor einer Constraint-Operation.
        """
        snapshot = self.sketch.to_dict()
        undo_len_before = len(self.undo_stack) if hasattr(self, "undo_stack") else None
        redo_backup = list(self.redo_stack) if hasattr(self, "redo_stack") else None
        if hasattr(self, "_save_undo"):
            self._save_undo()
        return {
            "snapshot": snapshot,
            "undo_len_before": undo_len_before,
            "redo_backup": redo_backup,
        }

    def _rollback_constraint_transaction(self, tx_state):
        """
        Rollback auf den exakten Vorzustand inkl. Undo/Redo-Konsistenz.
        """
        self.sketch = Sketch.from_dict(tx_state["snapshot"])
        if hasattr(self, "_clear_selection"):
            self._clear_selection()

        undo_len_before = tx_state.get("undo_len_before", None)
        if undo_len_before is not None and hasattr(self, "undo_stack"):
            while len(self.undo_stack) > undo_len_before:
                self.undo_stack.pop()

        redo_backup = tx_state.get("redo_backup", None)
        if redo_backup is not None and hasattr(self, "redo_stack"):
            self.redo_stack = redo_backup

        if hasattr(self, "snapper") and self.snapper and hasattr(self.snapper, "invalidate_intersection_cache"):
            self.snapper.invalidate_intersection_cache()

    def _constraint_result_dof(self, result):
        dof = getattr(result, "dof", None)
        if dof is not None:
            return dof
        try:
            _, _, dof_calc = self.sketch.calculate_dof()
            return dof_calc
        except Exception:
            return 0

    def _emit_constraint_failure(self, result, context: str):
        """
        Einheitliche, erklärbare Fehlerrückmeldung für Constraint-Apply.
        """
        msg = getattr(result, "message", "Constraint-Solver fehlgeschlagen")
        status_name = ""
        if hasattr(self, "_solver_status_name"):
            status_name = self._solver_status_name(result)
        else:
            status_obj = getattr(result, "status", "")
            status_name = getattr(status_obj, "name", status_obj) or ""
        dof = self._constraint_result_dof(result)
        error_code = getattr(result, "error_code", "")

        if hasattr(self, "_emit_solver_feedback"):
            self._emit_solver_feedback(
                success=False,
                message=msg,
                dof=float(dof),
                status_name=status_name,
                error_code=str(error_code or ""),
                context=context,
                show_hud=True,
            )
        else:
            text = format_solver_failure_message(
                status_name,
                msg,
                dof=dof,
                error_code=error_code,
                context=context,
            )
            if hasattr(self, "status_message"):
                self.status_message.emit(text)
            if hasattr(self, "show_message"):
                self.show_message(text, 4000, QColor(255, 90, 90))

    def _after_constraint_change(self):
        if hasattr(self, "_find_closed_profiles"):
            self._find_closed_profiles()
        if hasattr(self, "sketched_changed"):
            self.sketched_changed.emit()
        if hasattr(self, "request_update"):
            self.request_update()
        elif hasattr(self, "update"):
            self.update()

    def _execute_constraint_transaction(
        self,
        mutate_fn,
        *,
        context: str,
        success_status: str = "",
        success_hud: str = "",
        duplicate_message: str = "",
    ):
        """
        Führt Constraint-Mutation + Solve atomar aus:
        - Erfolg: Änderung bleibt bestehen
        - Fehler/No-op: vollständiger Rollback
        """
        tx_state = self._begin_constraint_transaction()

        try:
            applied = mutate_fn()
        except Exception as exc:
            self._rollback_constraint_transaction(tx_state)
            text = f"{context}: {exc}"
            if hasattr(self, "status_message"):
                self.status_message.emit(text)
            if hasattr(self, "show_message"):
                self.show_message(text, 3500, QColor(255, 90, 90))
            logger.error(text)
            self._after_constraint_change()
            return False, None

        if applied is None or applied is False:
            self._rollback_constraint_transaction(tx_state)
            if duplicate_message:
                if hasattr(self, "status_message"):
                    self.status_message.emit(duplicate_message)
                if hasattr(self, "show_message"):
                    self.show_message(duplicate_message, 2200, QColor(255, 190, 90))
            self._after_constraint_change()
            return False, None

        result = self.sketch.solve()
        if not bool(getattr(result, "success", False)):
            self._rollback_constraint_transaction(tx_state)
            self._emit_constraint_failure(result, context=context)
            self._after_constraint_change()
            return False, result

        self._after_constraint_change()
        if success_status and hasattr(self, "status_message"):
            self.status_message.emit(success_status)
        if success_hud and hasattr(self, "show_message"):
            self.show_message(success_hud, 2000, QColor(100, 255, 100))
        return True, result
    
    def _handle_select(self, pos, snap_type):
        if hasattr(self, "_pick_select_hit"):
            hit = self._pick_select_hit(pos)
        else:
            hit = self._find_entity_at(pos)

        if not (QApplication.keyboardModifiers() & Qt.ShiftModifier):
            self._clear_selection()

        if hit:
            if isinstance(hit, Line2D):
                if hit in self.selected_lines:
                    self.selected_lines.remove(hit)
                else:
                    self.selected_lines.append(hit)
            elif isinstance(hit, Circle2D):
                if hit in self.selected_circles:
                    self.selected_circles.remove(hit)
                else:
                    self.selected_circles.append(hit)
            elif isinstance(hit, Arc2D):
                if hit in self.selected_arcs:
                    self.selected_arcs.remove(hit)
                else:
                    self.selected_arcs.append(hit)
            elif isinstance(hit, Point2D):
                if hit in self.selected_points:
                    self.selected_points.remove(hit)
                else:
                    self.selected_points.append(hit)
            elif isinstance(hit, Ellipse2D):
                if hit in self.selected_ellipses:
                    self.selected_ellipses.remove(hit)
                else:
                    self.selected_ellipses.append(hit)
            elif hasattr(hit, "control_points"):
                if hit in self.selected_splines:
                    self.selected_splines.remove(hit)
                else:
                    self.selected_splines.append(hit)

    def _add_point_constraint(self, point, pos, snap_type, snap_entity, new_line):
        """
        Fügt automatisch Constraints für einen Punkt hinzu basierend auf Snap-Info.

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
        entity_optional_types = {SnapType.HORIZONTAL, SnapType.VERTICAL, SnapType.ANGLE_45}
        if snap_entity is None and snap_type not in entity_optional_types:
            return

        # ENDPOINT: COINCIDENT Constraint
        if snap_type == SnapType.ENDPOINT:
            snapped_point = None
            if hasattr(snap_entity, 'start') and hasattr(snap_entity, 'end'):
                # Linie - prüfe welcher Endpunkt näher ist
                dist_start = math.hypot(pos.x() - snap_entity.start.x, pos.y() - snap_entity.start.y)
                dist_end = math.hypot(pos.x() - snap_entity.end.x, pos.y() - snap_entity.end.y)
                snapped_point = snap_entity.start if dist_start < dist_end else snap_entity.end
            elif hasattr(snap_entity, 'x') and hasattr(snap_entity, 'y'):
                # Bereits ein Punkt (z.B. Polyline-Fortsetzung am letzten Endpunkt)
                snapped_point = snap_entity

            if snapped_point and snapped_point != point:
                if hasattr(self.sketch, 'add_coincident'):
                    self.sketch.add_coincident(point, snapped_point)
                    logger.debug(f"Auto: COINCIDENT für {type(snap_entity).__name__}")
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

        # INTERSECTION / VIRTUAL_INTERSECTION: keep point constrained to source geometry
        elif snap_type in (SnapType.INTERSECTION, SnapType.VIRTUAL_INTERSECTION):
            entities = []
            if isinstance(snap_entity, dict):
                entities = list(snap_entity.get("entities") or [])
            elif isinstance(snap_entity, (tuple, list)):
                entities = list(snap_entity)
            elif snap_entity is not None:
                entities = [snap_entity]

            applied = False
            for ent in entities:
                if hasattr(ent, "start") and hasattr(ent, "end"):
                    if hasattr(self.sketch, "add_point_on_line"):
                        self.sketch.add_point_on_line(point, ent)
                        applied = True
                elif hasattr(ent, "center") and hasattr(ent, "radius"):
                    if hasattr(self.sketch, "add_point_on_circle"):
                        self.sketch.add_point_on_circle(point, ent)
                        applied = True
                elif hasattr(ent, "x") and hasattr(ent, "y"):
                    if hasattr(self.sketch, "add_coincident") and ent is not point:
                        self.sketch.add_coincident(point, ent)
                        applied = True

            if applied:
                logger.debug("Auto: INTERSECTION")

        # ORIGIN: lock to sketch origin
        elif snap_type == SnapType.ORIGIN:
            origin_point = None
            for p in getattr(self.sketch, "points", []):
                if abs(float(getattr(p, "x", 1e9))) < 1e-9 and abs(float(getattr(p, "y", 1e9))) < 1e-9:
                    origin_point = p
                    break
            if origin_point is not None and origin_point is not point and hasattr(self.sketch, "add_coincident"):
                self.sketch.add_coincident(point, origin_point)
                logger.debug("Auto: ORIGIN coincident")
            else:
                point.x = 0.0
                point.y = 0.0

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

        # ANGLE_45: geometrische Inferenz fuer den Endpunkt (kein persistenter Constraint)
        elif snap_type == SnapType.ANGLE_45:
            logger.debug("Auto: ANGLE_45")

    def _apply_center_snap_constraint(self, center_point, snap_type, snap_entity):
        """
        Uebertraegt Snap-Information auf einen Kreis-/Polygon-Mittelpunkt.
        """
        if center_point is None or snap_type == SnapType.NONE or snap_entity is None:
            return

        if snap_type == SnapType.ENDPOINT:
            snapped_point = None
            if hasattr(snap_entity, "start") and hasattr(snap_entity, "end"):
                d_start = math.hypot(center_point.x - snap_entity.start.x, center_point.y - snap_entity.start.y)
                d_end = math.hypot(center_point.x - snap_entity.end.x, center_point.y - snap_entity.end.y)
                snapped_point = snap_entity.start if d_start <= d_end else snap_entity.end
            elif hasattr(snap_entity, "x") and hasattr(snap_entity, "y"):
                snapped_point = snap_entity

            if snapped_point and snapped_point is not center_point:
                self.sketch.add_coincident(center_point, snapped_point)
            return

        if snap_type == SnapType.CENTER and hasattr(snap_entity, "center"):
            if snap_entity.center is not center_point:
                self.sketch.add_coincident(center_point, snap_entity.center)
            return

        if snap_type in (SnapType.EDGE, SnapType.PERPENDICULAR, SnapType.PARALLEL):
            if hasattr(snap_entity, "start") and hasattr(snap_entity, "end"):
                self.sketch.add_point_on_line(center_point, snap_entity)
            return

        if snap_type == SnapType.MIDPOINT and hasattr(snap_entity, "start") and hasattr(snap_entity, "end"):
            self.sketch.add_midpoint(center_point, snap_entity)
            return

    def _handle_line(self, pos, snap_type, snap_entity=None):
        """
        Erstellt Linien und nutzt die existierenden Constraint-Methoden des Sketch-Objekts.
        """
        # Schritt 1: Startpunkt setzen
        if self.tool_step == 0:
            self.tool_points = [pos]
            # WICHTIG: Snap-Info für Startpunkt speichern!
            self._line_start_snap = (snap_type, snap_entity)
            self.tool_step = 1
            self.status_message.emit("Endpunkt wählen | Tab=Länge/Winkel | Rechts=Fertig")
        
        # Schritt 2: Endpunkt setzen und Linie erstellen
        else:
            start = self.tool_points[-1]
            is_chained_segment = len(self.tool_points) > 1
            dx = pos.x() - start.x()
            dy = pos.y() - start.y()
            length = math.hypot(dx, dy)

            if length > 0.01:
                self._save_undo()
                
                # Linie erstellen (wie in deinem Original)
                line = self.sketch.add_line(start.x(), start.y(), pos.x(), pos.y(), construction=self.construction_mode)

                # --- A. Auto-Constraints: Horizontal / Vertikal ---
                # DEAKTIVIERT: H/V-Constraints werden nicht mehr automatisch permanent gesetzt.
                # Sie werden nur als Inference/Preview angezeigt (Glyph).
                # Permanente H/V-Constraints nur bei explizitem User-Wunsch (Shift-Lock, etc.)
                # TODO: H/V als Preview/Glyph implementieren, nicht als permanente Constraints
                h_tolerance = self._adaptive_world_tolerance(scale=0.35, min_world=0.05, max_world=2.0)

                # Nur prüfen für Inference-Anzeige, nicht für permanente Constraints
                if (not is_chained_segment) and snap_type not in [
                    SnapType.EDGE,
                    SnapType.INTERSECTION,
                    SnapType.VIRTUAL_INTERSECTION,
                    SnapType.PERPENDICULAR,
                    SnapType.TANGENT,
                    SnapType.ANGLE_45,
                    SnapType.HORIZONTAL,
                    SnapType.VERTICAL,
                    SnapType.PARALLEL,
                ]:
                    if abs(dy) < h_tolerance and abs(dx) > h_tolerance:
                        # H/V nur als Status-Message, nicht als permanenter Constraint
                        self.status_message.emit("Inference: Horizontal")

                    elif abs(dx) < h_tolerance and abs(dy) > h_tolerance:
                        # H/V nur als Status-Message, nicht als permanenter Constraint
                        self.status_message.emit("Inference: Vertical")

                # --- B. Auto-Constraints: Verbindungen (Das neue Snapping) ---
                # DEAKTIVIERT: Auto-Snap-Constraints werden nicht mehr automatisch erstellt.
                # COINCIDENT und POINT_ON_LINE Constraints haben bewirkt, dass bestehende
                # Geometrie "mitgezogen" wird, was nicht gewünscht ist.
                #
                # WICHTIGE REGEL: Auto-Constraints dürfen nur die neu erzeugte Geometrie beeinflussen.
                # Bereits vorhandene Geometrie darf nicht "mitspringen".
                #
                # TODO: Auto-Constraints nur erstellen, wenn:
                # - User explizit snap willt (z.B. mit Modifier-Key)
                # - Solver-Konflikt-Prüfung zeigt, dass bestehende Geometrie nicht beeinflusst wird

                # Polyline-Fortsetzung: Startpunkt des neuen Segments am Ende des vorherigen
                # Das wird durch die Koordinaten gesetzt, kein separater Constraint nötig
                start_snap_type, start_snap_entity = getattr(self, '_line_start_snap', (SnapType.NONE, None))

                # Keine automatischen COINCIDENT/POINT_ON_LINE Constraints mehr
                # User kann explizite Constraints über Constraint-Tools hinzufügen

                # --- C. Abschluss ---
                self._solve_async() 
                self._find_closed_profiles()
                self.sketched_changed.emit()
                
                # Poly-Line Modus
                self.tool_points.append(pos)
                # Für das nächste Segment muss der Start immer am letzten Endpunkt "kleben".
                self._line_start_snap = (SnapType.ENDPOINT, line.end)
    
    def _handle_rectangle(self, pos, snap_type, snap_entity=None):
        """Rectangle with mode support (0=2-point, 1=center) plus persisted snap constraints."""

        first_snap = None
        second_snap = (snap_type, snap_entity, QPointF(pos.x(), pos.y()))

        if self.rect_mode == 1:
            if self.tool_step == 0:
                self.tool_points = [pos]
                self._rect_first_snap = (snap_type, snap_entity, QPointF(pos.x(), pos.y()))
                self.tool_step = 1
                self.status_message.emit(tr("Corner | Tab=Width/Height"))
                return

            c = self.tool_points[0]
            first_snap = getattr(self, "_rect_first_snap", None)
            w = abs(pos.x() - c.x()) * 2
            h = abs(pos.y() - c.y()) * 2
            x = c.x() - w / 2
            y = c.y() - h / 2
        else:
            if self.tool_step == 0:
                self.tool_points = [pos]
                self._rect_first_snap = (snap_type, snap_entity, QPointF(pos.x(), pos.y()))
                self.tool_step = 1
                self.status_message.emit(tr("Opposite corner | Tab=Width/Height"))
                return

            p1, p2 = self.tool_points[0], pos
            first_snap = getattr(self, "_rect_first_snap", None)
            x = min(p1.x(), p2.x())
            y = min(p1.y(), p2.y())
            w = abs(p2.x() - p1.x())
            h = abs(p2.y() - p1.y())

        if w > 0.01 and h > 0.01:
            self._save_undo()
            lines = self.sketch.add_rectangle(x, y, w, h, construction=self.construction_mode)

            if lines and len(lines) >= 4:
                self.sketch.add_length(lines[0], w)
                self.sketch.add_length(lines[3], h)

                # Map click anchors back to closest created corners and persist snap intent.
                corner_points = []
                seen_ids = set()
                for ln in lines:
                    for pt in (ln.start, ln.end):
                        if pt.id not in seen_ids:
                            seen_ids.add(pt.id)
                            corner_points.append(pt)

                def pick_corner(target: QPointF, used_ids: set):
                    best_pt = None
                    best_dist = float("inf")
                    for cp in corner_points:
                        if cp.id in used_ids:
                            continue
                        d = math.hypot(cp.x - target.x(), cp.y - target.y())
                        if d < best_dist:
                            best_dist = d
                            best_pt = cp
                    return best_pt

                used_anchor_ids = set()
                if self.rect_mode == 0 and first_snap is not None:
                    s_type, s_entity, s_pos = first_snap
                    anchor_pt = pick_corner(s_pos, used_anchor_ids)
                    if anchor_pt is not None:
                        self._add_point_constraint(anchor_pt, s_pos, s_type, s_entity, lines[0])
                        used_anchor_ids.add(anchor_pt.id)

                e_type, e_entity, e_pos = second_snap
                end_pt = pick_corner(e_pos, used_anchor_ids)
                if end_pt is not None:
                    self._add_point_constraint(end_pt, e_pos, e_type, e_entity, lines[0])

            self._solve_async()
            self._find_closed_profiles()
            self.sketched_changed.emit()

        if hasattr(self, "_rect_first_snap"):
            del self._rect_first_snap
        self._cancel_tool()

    def _handle_circle(self, pos, snap_type, snap_entity=None):
        """Kreis mit Modus-Unterstuetzung (0=Center-Radius, 1=2-Punkt, 2=3-Punkt)."""
        if self.circle_mode == 1:
            # 2-Punkt-Modus (Durchmesser)
            if self.tool_step == 0:
                self.tool_points = [pos]
                self.tool_step = 1
                self.status_message.emit(tr("Second point (diameter)"))
            else:
                p1, p2 = self.tool_points[0], pos
                cx, cy = (p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2
                r = math.hypot(p2.x() - p1.x(), p2.y() - p1.y()) / 2

                if r > 0.01:
                    self._save_undo()
                    circle = self.sketch.add_circle(cx, cy, r, construction=self.construction_mode)
                    self.sketch.add_radius(circle, r)
                    self._solve_async()
                    self._find_closed_profiles()
                    self.sketched_changed.emit()
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
                    circle = self.sketch.add_circle(center.x(), center.y(), r, construction=self.construction_mode)
                    self.sketch.add_radius(circle, r)
                    self._solve_async()
                    self._find_closed_profiles()
                    self.sketched_changed.emit()
                self._cancel_tool()

        else:
            # Center-Radius-Modus
            if self.tool_step == 0:
                self.tool_points = [pos]
                self._circle_center_snap = (snap_type, snap_entity)
                self.tool_step = 1
                self.status_message.emit(tr("Radius | Tab=Input"))
            else:
                c = self.tool_points[0]
                r = math.hypot(pos.x() - c.x(), pos.y() - c.y())

                if r > 0.01:
                    self._save_undo()
                    circle = self.sketch.add_circle(c.x(), c.y(), r, construction=self.construction_mode)
                    center_snap_type, center_snap_entity = getattr(self, "_circle_center_snap", (SnapType.NONE, None))
                    self._apply_center_snap_constraint(circle.center, center_snap_type, center_snap_entity)
                    self.sketch.add_radius(circle, r)
                    self._solve_async()
                    self._find_closed_profiles()
                    self.sketched_changed.emit()

                if hasattr(self, "_circle_center_snap"):
                    del self._circle_center_snap
                self._cancel_tool()

    def _handle_ellipse(self, pos, snap_type, snap_entity=None):
        """
        Ellipse im Fusion-ähnlichen 3-Schritt-Workflow:
        1) Zentrum
        2) Endpunkt der Hauptachse (Richtung + Major-Radius)
        3) Minor-Radius (senkrecht zur Hauptachse)
        """
        if self.tool_step == 0:
            self.tool_points = [pos]
            self._ellipse_center_snap = (snap_type, snap_entity)
            self.tool_step = 1
            self.status_message.emit(tr("Major axis endpoint | Tab=Major/Angle"))
            return

        if self.tool_step == 1:
            center = self.tool_points[0]
            major_radius = math.hypot(pos.x() - center.x(), pos.y() - center.y())
            if major_radius <= 0.01:
                self.status_message.emit(tr("Major axis too short"))
                return

            self.tool_points.append(pos)
            self.tool_step = 2
            self.status_message.emit(tr("Minor radius | Tab=Minor"))
            return

        center = self.tool_points[0]
        major_end = self.tool_points[1]
        dx = major_end.x() - center.x()
        dy = major_end.y() - center.y()
        major_radius = math.hypot(dx, dy)
        if major_radius <= 0.01:
            self.status_message.emit(tr("Major axis too short"))
            self._cancel_tool()
            return

        ux = dx / major_radius
        uy = dy / major_radius
        vx = -uy
        vy = ux

        rel_x = pos.x() - center.x()
        rel_y = pos.y() - center.y()
        minor_radius = abs(rel_x * vx + rel_y * vy)
        minor_radius = max(0.01, minor_radius)
        angle_deg = math.degrees(math.atan2(uy, ux))

        self._save_undo()
        ellipse = self.sketch.add_ellipse(
            cx=center.x(),
            cy=center.y(),
            major_radius=major_radius,
            minor_radius=minor_radius,
            angle_deg=angle_deg,
            construction=self.construction_mode,
        )
        center_point = ellipse._center_point if hasattr(ellipse, '_center_point') else ellipse.center

        center_snap_type, center_snap_entity = getattr(self, "_ellipse_center_snap", (SnapType.NONE, None))
        self._apply_center_snap_constraint(center_point, center_snap_type, center_snap_entity)

        self._solve_async()
        self._find_closed_profiles()
        self.sketched_changed.emit()

        if hasattr(self, "_ellipse_center_snap"):
            del self._ellipse_center_snap
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
    
    def _handle_polygon(self, pos, snap_type, snap_entity=None):
        """Erstellt ein parametrisches Polygon"""
        if self.tool_step == 0:
            # Erster Klick: Zentrum
            self.tool_points = [pos]
            self._polygon_center_snap = (snap_type, snap_entity)
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
                center_snap_type, center_snap_entity = getattr(self, "_polygon_center_snap", (SnapType.NONE, None))
                self._apply_center_snap_constraint(const_circle.center, center_snap_type, center_snap_entity)
                self.sketch.add_radius(const_circle, r)
                
                # 3. Lösen
                self.sketch.solve()
                self.sketched_changed.emit()
                self._find_closed_profiles()
                
            if hasattr(self, "_polygon_center_snap"):
                del self._polygon_center_snap
            self._cancel_tool()
    
    def _handle_arc_3point(self, pos, snap_type):
        """
        3-Punkt Arc wie Fusion 360:
        - Klick 1: Startpunkt
        - Klick 2: Endpunkt  
        - Klick 3: Durchgangspunkt (definiert Krümmung)
        """
        self.tool_points.append(pos)
        n = len(self.tool_points)
        if n == 1: 
            self.tool_step = 1
            self.status_message.emit(tr("End point"))
        elif n == 2: 
            self.tool_step = 2
            self.status_message.emit(tr("Through point (defines arc curvature)"))
        else:
            # Fusion 360 Reihenfolge: p1=Start, p2=Ende, p3=Durchgang
            p1_start = self.tool_points[0]   # Start
            p2_end = self.tool_points[1]     # Ende
            p3_through = self.tool_points[2] # Durchgangspunkt
            # _calc_arc_3point erwartet: start, through, end
            arc = self._calc_arc_3point(p1_start, p3_through, p2_end)
            if arc:
                self._save_undo()
                self.sketch.add_arc(*arc, construction=self.construction_mode)
                self.sketched_changed.emit()
                self._find_closed_profiles()
            self._cancel_tool()
    
    def _calc_arc_3point(self, p1, p2, p3):
        """
        Berechnet einen Arc durch 3 Punkte: Start, Punkt-auf-Bogen, Ende.
        Der Bogen verläuft von p1 nach p3 und enthält p2.
        """
        import math
        
        # p1 = Start, p2 = Punkt auf Bogen, p3 = Ende
        sx, sy = p1.x(), p1.y()
        mx, my = p2.x(), p2.y()
        ex, ey = p3.x(), p3.y()

        # Berechne Umkreis durch 3 Punkte
        d = 2 * (sx * (my - ey) + mx * (ey - sy) + ex * (sy - my))
        if abs(d) < 1e-10:
            return None
        
        ux = ((sx**2 + sy**2) * (my - ey) + (mx**2 + my**2) * (ey - sy) + (ex**2 + ey**2) * (sy - my)) / d
        uy = ((sx**2 + sy**2) * (ex - mx) + (mx**2 + my**2) * (sx - ex) + (ex**2 + ey**2) * (mx - sx)) / d
        r = math.hypot(sx - ux, sy - uy)
        
        if r < 1e-9:
            return None

        # Winkel der Punkte vom Zentrum aus (roh, -180 bis +180)
        a1 = math.degrees(math.atan2(sy - uy, sx - ux))
        a2 = math.degrees(math.atan2(my - uy, mx - ux))
        a3 = math.degrees(math.atan2(ey - uy, ex - ux))

        # Berechne beide mögliche Bögen (kurz CCW und kurz CW)
        ccw_short = (a3 - a1) % 360
        cw_short = -((a1 - a3) % 360)
        
        def point_on_arc_simple(target, start, span):
            """Prüft ob target auf dem Bogen mit gegebenem span liegt"""
            if abs(span) < 1e-9:
                return abs((target - start) % 360) < 1e-9
            
            rel_target = (target - start) % 360
            span_abs = abs(span)
            
            # Für beide Richtungen: prüfe ob target innerhalb des Spans liegt
            if span > 0:  # CCW
                return rel_target <= span + 1e-9
            else:  # CW
                # Für CW arc: der Bereich ist von start zurück bis start+span
                # d.h. von 0 bis -span im CW-Sinn = von 360-abs(span) bis 360
                return rel_target >= (360 - span_abs) - 1e-9
        
        # Teste kurze Bögen
        if point_on_arc_simple(a2, a1, ccw_short):
            # CCW Bogen - direkt verwenden
            return (ux, uy, r, a1, a1 + ccw_short)
        else:
            # CW Bogen - als positiven Sweep speichern (360 + cw_short)
            # z.B. cw_short = -123.86 -> sweep = 236.14 ist falsch!
            # Wir müssen den kurzen CW als CCW-equivalent speichern
            # Eigentlich wollen wir: sweep = 360 - abs(cw_short) = 236.14? Nein!
            
            # KORREKTUR: Wir invertieren Start/End für CW Bögen
            # Dann wird der Bogen in die andere Richtung gezeichnet
            return (ux, uy, r, a3, a1)  # Vertausche Start/End für CW
    
    def _handle_slot(self, pos, snap_type, snap_entity=None):
        """
        Handler for slot workflow.
        1) Click start of center line
        2) Click end of center line
        3) Click/enter radius
        """

        if self.tool_step == 0:
            self.tool_points = [pos]
            self._slot_start_snap = (snap_type, snap_entity)
            self.tool_step = 1
            self.status_message.emit(tr("Endpoint center line | Tab=Length/Angle"))

        elif self.tool_step == 1:
            self.tool_points.append(pos)
            self._slot_end_snap = (snap_type, snap_entity)
            self.tool_step = 2
            self.status_message.emit(tr("Radius | Tab=Enter radius"))

            logger.info("[SLOT] Step 1->2: Showing radius input panel")
            logger.debug(f"[SLOT] hasattr dim_input: {hasattr(self, 'dim_input')}")

            if hasattr(self, 'dim_input'):
                logger.debug("[SLOT] dim_input exists, setting up radius field")
                self.dim_input.committed_values.clear()
                self.dim_input.unlock_all()
                radius_default = self.live_radius if self.live_radius > 0 else 5.0
                fields = [("R", "radius", radius_default, "mm")]
                self.dim_input.setup(fields)
                pos_screen = self.world_to_screen(pos)
                x = min(int(pos_screen.x()) + 20, self.width() - self.dim_input.width() - 10)
                y = min(int(pos_screen.y()) - 40, self.height() - self.dim_input.height() - 10)
                self.dim_input.move(max(10, x), max(10, y))
                self.dim_input.show()
                self.dim_input.focus_field(0)
                self.dim_input_active = True
                logger.success(f"[SLOT] Radius panel shown at ({x}, {y}), visible={self.dim_input.isVisible()}")
            else:
                logger.error("[SLOT] dim_input NOT FOUND on self!")

        else:
            p1 = self.tool_points[0]
            p2 = self.tool_points[1]

            dx_line = p2.x() - p1.x()
            dy_line = p2.y() - p1.y()
            length = math.hypot(dx_line, dy_line)

            if length > 0.01:
                ux = dx_line / length
                uy = dy_line / length
                nx, ny = -uy, ux
                vx = pos.x() - p1.x()
                vy = pos.y() - p1.y()
                radius = abs(vx * nx + vy * ny)

                if radius > 0.01:
                    self._save_undo()
                    center_line, main_arc = self.sketch.add_slot(
                        p1.x(), p1.y(), p2.x(), p2.y(), radius,
                        construction=self.construction_mode,
                    )

                    self.sketch.add_length(center_line, length)
                    self.sketch.add_radius(main_arc, radius)

                    start_snap_type, start_snap_entity = getattr(self, "_slot_start_snap", (SnapType.NONE, None))
                    end_snap_type, end_snap_entity = getattr(self, "_slot_end_snap", (SnapType.NONE, None))
                    self._add_point_constraint(center_line.start, p1, start_snap_type, start_snap_entity, center_line)
                    self._add_point_constraint(center_line.end, p2, end_snap_type, end_snap_entity, center_line)

                    self.sketch.solve()
                    self.sketched_changed.emit()
                    self._find_closed_profiles()

            if hasattr(self, "_slot_start_snap"):
                del self._slot_start_snap
            if hasattr(self, "_slot_end_snap"):
                del self._slot_end_snap
            self._cancel_tool()

    def _handle_spline(self, pos, snap_type):
        # 3. Capture Snap Data for Constraint Creation
        # We need to store not just the position, but what we snapped to.
        # This allows _finish_spline to create Coincident constraints.
        snapped, s_type, s_entity = self.snap_point(self.mouse_world)
        
        # Store tuple: (position, snap_type, snap_entity)
        if not hasattr(self, 'spline_snap_data'):
            self.spline_snap_data = []
            
        self.spline_snap_data.append((snapped, s_type, s_entity))
        self.tool_points.append(snapped)
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
            
            # Check for closure (if last point is close to first point)
            first_pt = self.tool_points[0]
            last_pt = self.tool_points[-1]
            if len(self.tool_points) > 2 and math.hypot(first_pt.x()-last_pt.x(), first_pt.y()-last_pt.y()) < (self.snap_radius / self.view_scale):
                spline.closed = True
                # Remove last point as it duplicates the first
                self.tool_points.pop()
                if hasattr(self, 'spline_snap_data'):
                    self.spline_snap_data.pop()
            
            # Add points to spline
            for p in self.tool_points:
                spline.add_point(p.x(), p.y())
            
            # Spline zum Sketch hinzufügen
            self.sketch.splines.append(spline)
            
            # Apply Constraints
            if hasattr(self, 'spline_snap_data'):
                for i, (pos, s_type, s_entity) in enumerate(self.spline_snap_data):
                    if i >= len(spline.control_points): break
                    cp = spline.control_points[i]
                    # We can't easily constrain the ControlPoint object itself directly 
                    # because the solver likely expects Point2D objects.
                    # However, BezierSpline.control_points are wrappers around Point2D (cp.point).
                    # So we allow constraining cp.point.
                    if s_entity:
                        self._add_point_constraint(cp.point, pos, s_type, s_entity, spline)
                
                # Cleanup
                del self.spline_snap_data

            # Auch als Linien für Kompatibilität (Export etc.)
            lines = spline.to_lines(segments_per_span=10)
            spline._lines = lines  # Referenz speichern für späteren Update
            
            # We DON'T add these lines to self.sketch.lines anymore if we have native spline support!
            # Adding them causes double rendering and selection issues.
            # But the 'dxf_export' might need them. Let's keep them in spline._lines only.
            
            # Spline auswählen für sofortiges Editing
            self.selected_splines = [spline]
            
            self.sketched_changed.emit()
            self._find_closed_profiles()
            self.status_message.emit(tr("Spline created - drag points/handles to edit"))
        except Exception as e:
            logger.error(f"Spline error: {e}")
        self._cancel_tool()
    
    def _handle_move(self, pos, snap_type, snap_entity=None):
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
        # Reguläre Polygone: Treiberkreis mitbewegen, damit Polygon + Konstruktionskreis konsistent bleiben.
        if hasattr(self, "_collect_driver_circles_for_lines"):
            for driver_circle in self._collect_driver_circles_for_lines(self.selected_lines):
                if driver_circle.center.id not in moved:
                    driver_circle.center.x += dx
                    driver_circle.center.y += dy
                    moved.add(driver_circle.center.id)
        for c in self.selected_circles:
            if c.center.id not in moved:
                c.center.x += dx
                c.center.y += dy
                moved.add(c.center.id)
        self._solve_async()
    
    def _handle_copy(self, pos, snap_type, snap_entity=None):
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

        for c in list(self.sketch.constraints):
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
                    value=c.value,
                    formula=getattr(c, "formula", None),
                    driving=getattr(c, "driving", True),
                    priority=getattr(c, "priority", None),
                    group=getattr(c, "group", None),
                    enabled=getattr(c, "enabled", True),
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
    def _handle_rotate(self, pos, snap_type, snap_entity=None):
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
        # W35-BF: Auch Arcs berÃ¼cksichtigen (kÃ¶nnen H/V Constraints haben)
        for arc in getattr(self, 'selected_arcs', []): selected_ids.add(arc.id)
        
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
    
    def _handle_mirror(self, pos, snap_type, snap_entity=None):
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
        """Spiegelt Auswahl an Achse p1-p2 (erstellt Kopie mit Constraints)"""
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
        new_arcs = []
        old_to_new = {}  # W35-BF: Mapping fÃ¼r Constraint-Kopie
        
        for line in self.selected_lines:
            sx, sy = mirror_point(line.start.x, line.start.y)
            ex, ey = mirror_point(line.end.x, line.end.y)
            new_line = self.sketch.add_line(sx, sy, ex, ey, construction=line.construction)
            new_lines.append(new_line)
            # Mapping fÃ¼r Constraints
            old_to_new[line.id] = new_line
            old_to_new[line.start.id] = new_line.start
            old_to_new[line.end.id] = new_line.end
        
        for c in self.selected_circles:
            cx, cy = mirror_point(c.center.x, c.center.y)
            new_circle = self.sketch.add_circle(cx, cy, c.radius, construction=c.construction)
            new_circles.append(new_circle)
            old_to_new[c.id] = new_circle
            old_to_new[c.center.id] = new_circle.center
        
        # W35-BF: Arcs auch spiegeln
        for arc in getattr(self, 'selected_arcs', []):
            cx, cy = mirror_point(arc.center.x, arc.center.y)
            # Winkel spiegeln (Start/End Angle an Achse gespiegelt)
            # Bei Spiegelung an einer Linie: Winkel werden gespiegelt
            new_arc = self.sketch.add_arc(
                cx, cy, arc.radius,
                -arc.end_angle, -arc.start_angle,  # Winkel gespiegelt
                construction=arc.construction
            )
            new_arcs.append(new_arc)
            old_to_new[arc.id] = new_arc
            old_to_new[arc.center.id] = new_arc.center
        
        # W35-BF: Constraints kopieren (wie bei Copy)
        constraints_added = 0
        for c in list(self.sketch.constraints):
            is_internal = True
            if not c.entities:
                is_internal = False
                continue
            
            new_entities = []
            for entity in c.entities:
                if hasattr(entity, 'id') and entity.id in old_to_new:
                    new_entities.append(old_to_new[entity.id])
                else:
                    is_internal = False
                    break
            
            if is_internal:
                new_c = Constraint(
                    type=c.type,
                    entities=new_entities,
                    value=c.value,
                    formula=getattr(c, "formula", None),
                    driving=getattr(c, "driving", True),
                    priority=getattr(c, "priority", None),
                    group=getattr(c, "group", None),
                    enabled=getattr(c, "enabled", True),
                )
                self.sketch.constraints.append(new_c)
                constraints_added += 1
        
        # Neue Elemente auswÃ¤hlen
        self._clear_selection()
        self.selected_lines = new_lines
        self.selected_circles = new_circles
        self.selected_arcs = new_arcs
        
        msg = tr("Mirrored: {l} lines, {c} circles").format(l=len(new_lines), c=len(new_circles))
        if len(new_arcs) > 0:
            msg += tr(", {a} arcs").format(a=len(new_arcs))
        if constraints_added > 0:
            msg += f", {constraints_added} constraints"
        self.status_message.emit(msg)
    
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
    
    def _handle_scale(self, pos, snap_type, snap_entity=None):
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
        
        # W35-BF: Arcs auch skalieren (Center + Radius)
        for arc in getattr(self, 'selected_arcs', []):
            if arc.center.id not in scaled:
                arc.center.x = center.x() + (arc.center.x - center.x()) * factor
                arc.center.y = center.y() + (arc.center.y - center.y()) * factor
                scaled.add(arc.center.id)
            # Radius skalieren
            arc.radius *= factor
        
        self._solve_async()
        self._find_closed_profiles()
    
    
    def _handle_trim(self, pos, snap_type, snap_entity=None):
        """
        Intelligentes Trimmen:
        1. Findet Entity unter Maus
        2. Berechnet ALLE Schnittpunkte gegen ALLE anderen Geometrien
        3. Löscht Segment

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
            msg = format_trim_failure_message("Kein Ziel gefunden")
            self.status_message.emit(msg)
            if hasattr(self, "show_message"):
                self.show_message(msg, 2200, QColor(255, 140, 90))
            self.request_update()
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
        self.preview_geometry = self._build_trim_preview_geometry(target, segment)

        self.status_message.emit("Klicken zum Trimmen")

        # Ausführen bei Klick
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
    
    def _find_connected_profile(self, start_entity):
        """Findet alle zusammenhängenden Linien UND Arcs die ein Profil bilden"""
        TOL = 0.5
        
        def pt_match(p1, p2):
            return math.hypot(p1[0] - p2[0], p1[1] - p2[1]) < TOL
        
        def entity_endpoints(e):
            """Returns list of (x, y) endpoint tuples for lines and arcs."""
            if hasattr(e, 'start') and hasattr(e, 'end') and not hasattr(e, 'start_angle'):
                # Line2D
                return [(e.start.x, e.start.y), (e.end.x, e.end.y)]
            elif hasattr(e, 'start_angle') and hasattr(e, 'end_angle'):
                # Arc2D
                sp = e.start_point
                ep = e.end_point
                return [(sp.x, sp.y), (ep.x, ep.y)]
            return []
        
        # Sammle alle nicht-Konstruktionslinien UND Arcs
        all_entities = [l for l in self.sketch.lines if not l.construction]
        all_entities += [a for a in self.sketch.arcs if not a.construction]
        
        if start_entity not in all_entities:
            return [start_entity]
        
        # Finde zusammenhängende Entitäten via BFS
        profile = [start_entity]
        used = {id(start_entity)}
        
        changed = True
        while changed:
            changed = False
            for entity in all_entities:
                if id(entity) in used:
                    continue
                
                ent_pts = entity_endpoints(entity)
                for profile_ent in profile:
                    profile_pts = entity_endpoints(profile_ent)
                    for ep in ent_pts:
                        for pp in profile_pts:
                            if pt_match(ep, pp):
                                profile.append(entity)
                                used.add(id(entity))
                                changed = True
                                break
                        if id(entity) in used:
                            break
                    if id(entity) in used:
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
    
    def _compute_offset_data(self, profile_entities, distance, direction_outward=True):
        """
        Berechnet Offset-Daten für ein Profil (Linien UND Arcs).
        
        Args:
            profile_entities: Liste von Linien und Arcs die das Profil bilden
            distance: Offset-Abstand (positiv = nach außen, negativ = nach innen)
        
        Returns:
            Liste von dicts:
              {'type': 'line', 'x1', 'y1', 'x2', 'y2', 'orig': entity}
              {'type': 'arc', 'cx', 'cy', 'radius', 'start_angle', 'end_angle', 'orig': entity}
        """
        if not profile_entities:
            return []
        
        # Berechne Zentrum des Profils
        cx, cy = 0, 0
        count = 0
        for ent in profile_entities:
            if hasattr(ent, 'start') and hasattr(ent, 'end') and not hasattr(ent, 'start_angle'):
                cx += ent.start.x + ent.end.x
                cy += ent.start.y + ent.end.y
                count += 2
            elif hasattr(ent, 'center') and hasattr(ent, 'start_angle'):
                sp = ent.start_point
                ep = ent.end_point
                cx += sp.x + ep.x
                cy += sp.y + ep.y
                count += 2
        if count == 0:
            return []
        cx /= count
        cy /= count
        
        offset_data = []
        for ent in profile_entities:
            if hasattr(ent, 'start') and hasattr(ent, 'end') and not hasattr(ent, 'start_angle'):
                # ---- Line2D ----
                dx = ent.end.x - ent.start.x
                dy = ent.end.y - ent.start.y
                length = math.hypot(dx, dy)
                if length < 0.01:
                    continue
                
                nx, ny = -dy/length, dx/length
                mid_x = (ent.start.x + ent.end.x) / 2
                mid_y = (ent.start.y + ent.end.y) / 2
                to_center_x = cx - mid_x
                to_center_y = cy - mid_y
                dot = nx * to_center_x + ny * to_center_y
                if dot > 0:
                    nx, ny = -nx, -ny
                
                d = distance
                x1 = ent.start.x + nx * d
                y1 = ent.start.y + ny * d
                x2 = ent.end.x + nx * d
                y2 = ent.end.y + ny * d
                offset_data.append({'type': 'line', 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2, 'orig': ent})
            
            elif hasattr(ent, 'center') and hasattr(ent, 'start_angle'):
                # ---- Arc2D ---- concentric offset
                arc_cx, arc_cy = ent.center.x, ent.center.y
                # Determine outward direction: away from profile centroid
                vec_x = arc_cx - cx
                vec_y = arc_cy - cy
                # If center is outside profile centroid, outward = towards center (larger radius)
                # Use midpoint of the arc instead
                mid_param = ent.point_at_parameter(0.5)
                mid_vec_x = mid_param.x - cx
                mid_vec_y = mid_param.y - cy
                # Radial direction at midpoint
                rad_x = mid_param.x - arc_cx
                rad_y = mid_param.y - arc_cy
                # If radial direction points same way as centroid->midpoint, outward = positive radius change
                dot = rad_x * mid_vec_x + rad_y * mid_vec_y
                if dot > 0:
                    new_r = ent.radius + distance
                else:
                    new_r = ent.radius - distance
                
                if new_r > 0.01:
                    offset_data.append({
                        'type': 'arc',
                        'cx': arc_cx, 'cy': arc_cy,
                        'radius': new_r,
                        'start_angle': ent.start_angle,
                        'end_angle': ent.end_angle,
                        'orig': ent
                    })
        
        # Ecken verbinden (nur Linien)
        line_items = [d for d in offset_data if d['type'] == 'line']
        if len(line_items) > 1:
            # Convert to legacy tuple format for _connect_offset_corners
            tuples = [(d['x1'], d['y1'], d['x2'], d['y2'], d['orig']) for d in line_items]
            connected = self._connect_offset_corners(tuples)
            # Write back
            li = 0
            for i, d in enumerate(offset_data):
                if d['type'] == 'line':
                    x1, y1, x2, y2, orig = connected[li]
                    offset_data[i] = {'type': 'line', 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2, 'orig': orig}
                    li += 1
        
        return offset_data

    def _compute_offset_lines(self, profile_lines, distance, direction_outward=True):
        """Legacy wrapper: returns (x1, y1, x2, y2, orig) tuples for backward compat."""
        data = self._compute_offset_data(profile_lines, distance, direction_outward)
        result = []
        for d in data:
            if d['type'] == 'line':
                result.append((d['x1'], d['y1'], d['x2'], d['y2'], d['orig']))
            elif d['type'] == 'arc':
                # Fallback: approximate arc as line from start to end
                arc_r = d['radius']
                sa = math.radians(d['start_angle'])
                ea = math.radians(d['end_angle'])
                x1 = d['cx'] + arc_r * math.cos(sa)
                y1 = d['cy'] + arc_r * math.sin(sa)
                x2 = d['cx'] + arc_r * math.cos(ea)
                y2 = d['cy'] + arc_r * math.sin(ea)
                result.append((x1, y1, x2, y2, d['orig']))
        return result
    
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
        1. Klick auf Element →’ Sofort Vorschau mit Standard-Offset
        2. Tab →’ Wert eingeben →’ Vorschau aktualisiert live  
        3. Enter/Klick →’ Anwenden
        
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
            
            # Prüfe Arc (z.B. Fillet-Bogen)
            arc = self._find_arc_at(pos)
            if arc:
                self.offset_profile = self._find_connected_profile(arc)
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
            # Profil-Preview (lines + arcs)
            if not self.offset_profile:
                self.offset_preview_lines = []
                self._offset_preview_arcs = []
                return
            
            offset_data = self._compute_offset_data(self.offset_profile, self.offset_distance)
            
            self.offset_preview_lines = []
            self._offset_preview_arcs = []
            for d in offset_data:
                if d['type'] == 'line':
                    self.offset_preview_lines.append((d['x1'], d['y1'], d['x2'], d['y2']))
                elif d['type'] == 'arc':
                    self._offset_preview_arcs.append(d)
        
        self.request_update()

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
            
            # Berechne finale Offset-Daten (Linien + Arcs)
            offset_data = self._compute_offset_data(self.offset_profile, self.offset_distance)
            
            # Erstelle neue Geometrie
            created = 0
            for d in offset_data:
                if d['type'] == 'line':
                    if math.hypot(d['x2']-d['x1'], d['y2']-d['y1']) > 0.01:
                        self.sketch.add_line(d['x1'], d['y1'], d['x2'], d['y2'])
                        created += 1
                elif d['type'] == 'arc':
                    if d['radius'] > 0.01:
                        self.sketch.add_arc(
                            d['cx'], d['cy'], d['radius'],
                            d['start_angle'], d['end_angle']
                        )
                        created += 1
            
            self.sketched_changed.emit()
            self._find_closed_profiles()
            self.status_message.emit(tr("Offset applied ({count} elements) | Next element").format(count=created))
        
        # Reset
        self.offset_profile = None
        self.offset_preview_lines = []
        self._offset_preview_arcs = []
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
        # Für konvexe Ecken (wie Rechteck) zeigt d1+d2 nach INNEN
        # Das ist korrekt für Fillets - NICHT negieren!
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

        # Linien verkürzen - neue Endpunkte an den Tangentenpunkten
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

        # Wähle Start/End so dass der Sweep positiv ist (CCW)
        if sweep >= 0:
            start_angle = angle1
            end_angle = angle2
        else:
            # Negativer sweep →’ tausche für positiven Sweep
            start_angle = angle2
            end_angle = angle1

        # Stelle sicher dass end > start (für positiven Sweep im Renderer)
        if end_angle < start_angle:
            end_angle += 360

        arc = self.sketch.add_arc(center_x, center_y, radius, start_angle, end_angle)

        # Radius-Constraint hinzufügen
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
        if self.dim_input_active and hasattr(self.dim_input, "has_errors") and self.dim_input.has_errors():
            self.status_message.emit(getattr(self.dim_input, "_last_validation_error", tr("Ungültiger Wert")))
            return
        
        line = self._find_line_at(pos)
        if line:
            current = line.length
            # Wenn Input bestätigt wurde, anwenden
            if new_val is not None and abs(new_val - current) > 0.001:
                 self._save_undo()
                 constraint = self.sketch.add_length(line, new_val)
                 # Formel-Binding: Rohtext speichern wenn kein reiner Float
                 if constraint:
                     formula = self._get_valid_formula_from_dim_input('value')
                     if formula:
                         constraint.formula = formula
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
                     formula = self._get_valid_formula_from_dim_input('value')
                     if formula:
                         constraint.formula = formula
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
                if self.dim_input_active and hasattr(self.dim_input, "has_errors") and self.dim_input.has_errors():
                    self.status_message.emit(getattr(self.dim_input, "_last_validation_error", tr("Ungültiger Wert")))
                    return
                
                if new_val is not None:
                    self._save_undo()
                    constraint = self.sketch.add_angle(l1, line, new_val)
                    if constraint:
                        formula = self._get_valid_formula_from_dim_input('angle')
                        if formula:
                            constraint.formula = formula
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
        """Tangent Constraint: Linie tangential an Kreis/Arc oder Kreis/Arc tangential aneinander"""
        from loguru import logger
        from PySide6.QtGui import QColor

        # WICHTIG: Für Constraint-Tools brauchen wir die originale Mausposition,
        # nicht die gesnappte Position. Grid-Snap würde sonst die Entity-Suche verhindern.
        original_pos = self.mouse_world

        line = self._find_line_at(original_pos)
        circle = self._find_circle_at(original_pos)
        arc = self._find_arc_at(original_pos)  # Phase: Arc-Support für Tangent

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

            # Validierung: Line-Line ist nicht tangent-fähig
            if elem1_type == 'line' and elem2_type == 'line':
                logger.warning(f"[TANGENT] Line-Line not supported")
                if hasattr(self, 'show_message'):
                    self.show_message(tr("Tangent needs circle or arc!"), 2000, QColor(255, 100, 100))
                self.status_message.emit(tr("Tangent requires at least one circle or arc"))
                self._clear_constraint_highlight()
                self._cancel_tool()
                return

            self._save_undo()

            # Pre-Positionierung für bessere Solver-Konvergenz
            # (Geometrie wird UNGEFÄHR tangent positioniert, dann übernimmt der Constraint)
            if elem1_type == 'line' and elem2_type in ('circle', 'arc'):
                self._make_line_tangent_to_circle(elem1, elem2)
            elif elem2_type == 'line' and elem1_type in ('circle', 'arc'):
                self._make_line_tangent_to_circle(elem2, elem1)
            elif elem1_type in ('circle', 'arc') and elem2_type in ('circle', 'arc'):
                self._make_circles_tangent(elem1, elem2)

            # === ECHTER CONSTRAINT HINZUFÜGEN ===
            constraint = self.sketch.add_tangent(elem1, elem2)

            if constraint:
                logger.info(f"[TANGENT] Constraint created: {elem1_type} →” {elem2_type}")
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

            self._clear_constraint_highlight()  # Visual Feedback zurücksetzen
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
    
    def _handle_gear(self, pos, snap_type, snap_entity=None):
        """
        Erweitertes Zahnrad-Tool (CAD Kompatibel).
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
    

    

    def _handle_nut(self, pos, snap_type, snap_entity=None):
        """Erstellt eine Sechskant-Muttern-Aussparung (M2-M14) mit Schraubenloch - 2 Schritte wie Polygon"""
        if self.tool_step == 0:
            # Schritt 1: Position setzen
            self.tool_points = [pos]
            self._nut_center_snap = (snap_type, snap_entity)
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
            angle_offset = rotation_angle + math.radians(30)
            _, const_circle = self.sketch.add_regular_polygon(
                center.x(), center.y(), hex_radius, 6,
                angle_offset=angle_offset,
                construction=self.construction_mode
            )
            center_snap_type, center_snap_entity = getattr(self, "_nut_center_snap", (SnapType.NONE, None))
            self._apply_center_snap_constraint(const_circle.center, center_snap_type, center_snap_entity)
            self.sketch.add_radius(const_circle, hex_radius)
            hole_circle = self.sketch.add_circle(center.x(), center.y(), hole_radius, construction=self.construction_mode)
            self.sketch.add_radius(hole_circle, hole_radius)
            # W35: Nut Constraint Fix
            # Concentric evaluates center distance dynamically. Coincident binds them completely in the solver.
            self.sketch.add_coincident(const_circle.center, hole_circle.center)
            self.sketch.solve()
            self.sketched_changed.emit()
            self._find_closed_profiles()
            
            # Info anzeigen
            self.status_message.emit(f"{size_name} " + tr("Nut") + f" (SW {sw:.2f}mm, " + tr("Hole") + f" ⌀{screw_diameter + self.nut_tolerance:.2f}mm)")
            if hasattr(self, "_nut_center_snap"):
                del self._nut_center_snap
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

            # Default: 100mm Breite, Höhe aus Aspect Ratio
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
            self._draw_hud(tr("Canvas platziert — Rechtsklick für Optionen"))
            self.set_tool(SketchTool.SELECT)
            self.request_update()

    def _canvas_hit_test(self, world_pos):
        """Prüft ob world_pos innerhalb des Canvas liegt."""
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
        """Aktualisiert Canvas-Position während Drag."""
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
        """Setzt Canvas-Deckkraft (0.0–1.0)."""
        self.canvas_opacity = max(0.0, min(1.0, opacity))
        self.request_update()

    def canvas_set_size(self, width_mm):
        """Setzt Canvas-Breite in mm (Höhe folgt Aspect Ratio)."""
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
        self._draw_hud(tr("Kalibrierung — Punkt 1 von 2 setzen"))
        self.request_update()

    def _canvas_calibration_click(self, world_pos):
        """Verarbeitet einen Klick im Kalibrierungsmodus. Gibt True zurück wenn konsumiert."""
        if not self._canvas_calibrating:
            return False

        self._canvas_calib_points.append(QPointF(world_pos.x(), world_pos.y()))

        if len(self._canvas_calib_points) == 1:
            self.status_message.emit(tr("Kalibrierung: Zweiten Punkt auf dem Bild anklicken"))
            self._draw_hud(tr("Kalibrierung — Punkt 2 von 2 setzen"))
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
    
