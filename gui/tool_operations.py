"""
MashCAD Tool Operations Module
===============================

Extracted from main_window.py (AR-005: Phase 2 Split).

This module contains tool-related operations as a mixin class.
Maintains backward compatibility by being imported into MainWindow.

Usage:
    class MainWindow(ToolMixin, QMainWindow):
        pass
"""

from typing import TYPE_CHECKING, Optional, List, Dict, Any
from loguru import logger

from PySide6.QtCore import Qt

if TYPE_CHECKING:
    from modeling import Body
    from gui.sketch_editor import SketchTool


class ToolMixin:
    """
    Mixin class containing tool-related operations for MainWindow.
    
    This class provides:
    - Tool activation/switching
    - Tool-specific handlers
    - Tool state management
    - 3D action handlers
    
    All methods assume they are called within a MainWindow context
    and access MainWindow attributes via `self`.
    """
    
    # =========================================================================
    # 3D Tool Actions
    # =========================================================================
    
    def _on_3d_action(self, action: str):
        """Verarbeitet 3D-Tool-Aktionen"""
        action_handlers = {
            # Primitives (short + prefixed keys from tool_panel_3d)
            'box': lambda: self._primitive_dialog('box'),
            'primitive_box': lambda: self._primitive_dialog('box'),
            'cylinder': lambda: self._primitive_dialog('cylinder'),
            'primitive_cylinder': lambda: self._primitive_dialog('cylinder'),
            'sphere': lambda: self._primitive_dialog('sphere'),
            'primitive_sphere': lambda: self._primitive_dialog('sphere'),
            'cone': lambda: self._primitive_dialog('cone'),
            'primitive_cone': lambda: self._primitive_dialog('cone'),
            'torus': lambda: self._primitive_dialog('torus'),
            
            # Sketch
            'new_sketch': '_new_sketch',
            'offset_plane': '_start_offset_plane',
            
            # Features
            'extrude': '_extrude_dialog',
            'revolve': '_revolve_dialog',
            'fillet': '_start_fillet',
            'chamfer': '_start_chamfer',
            'shell': '_start_shell',
            'sweep': '_start_sweep',
            'loft': '_start_loft',
            'pattern': '_start_pattern',
            'draft': '_draft_dialog',
            'hole': '_hole_dialog',
            'thread': '_thread_dialog',
            'split': '_split_body_dialog',
            'split_body': '_split_body_dialog',
            
            # Boolean (short + prefixed keys from tool_panel_3d)
            'union': lambda: self._boolean_operation_dialog('Union'),
            'boolean_union': lambda: self._boolean_operation_dialog('Union'),
            'cut': lambda: self._boolean_operation_dialog('Cut'),
            'boolean_cut': lambda: self._boolean_operation_dialog('Cut'),
            'intersect': lambda: self._boolean_operation_dialog('Intersect'),
            'boolean_intersect': lambda: self._boolean_operation_dialog('Intersect'),
            
            # Transform (short + prefixed keys from tool_panel_3d)
            'move': lambda: self._start_transform_mode('move'),
            'move_body': lambda: self._start_transform_mode('move'),
            'rotate': lambda: self._start_transform_mode('rotate'),
            'rotate_body': lambda: self._start_transform_mode('rotate'),
            'scale': lambda: self._start_transform_mode('scale'),
            'scale_body': lambda: self._start_transform_mode('scale'),
            'mirror': '_mirror_body',
            'mirror_body': '_mirror_body',
            'copy': '_copy_body',
            'copy_body': '_copy_body',
            'point_to_point': '_start_point_to_point_move',
            'point_to_point_move': '_start_point_to_point_move',
            
            # View / Inspect
            'section_view': '_toggle_section_view',
            'measure': '_start_measure_mode',
            'wall_thickness': '_wall_thickness_dialog',
            
            # Import/Export
            'import_mesh': '_import_mesh_dialog',
            'import_step': '_import_step',
            'import_svg': '_import_svg',
            'stl_to_cad': '_on_stl_to_cad',
            'export_stl': '_export_stl',
            'export_step': '_export_step',
            'convert_to_brep': '_convert_selected_body_to_brep',
            
            # Special (short + prefixed keys from tool_panel_3d)
            'brep_cleanup': '_toggle_brep_cleanup',
            'texture': '_start_texture_mode',
            'surface_texture': '_start_texture_mode',
            'lattice': '_start_lattice',
            'nsided_patch': '_nsided_patch_dialog',
            'sketch_agent': '_sketch_agent_dialog',
        }

        handler_spec = action_handlers.get(action)
        if handler_spec is None:
            logger.warning(f"Aktion '{action}' nicht gefunden")
            return

        if callable(handler_spec):
            handler = handler_spec
        else:
            handler = getattr(self, handler_spec, None)
            if handler is None:
                logger.error(f"Aktion '{action}' fehlgeschlagen: Handler '{handler_spec}' fehlt")
                return

        try:
            handler()
        except Exception as e:
            logger.error(f"Aktion '{action}' fehlgeschlagen: {e}")
    
    # =========================================================================
    # Transform Tools
    # =========================================================================
    
    def _start_transform_mode(self, mode):
        """
        Startet den Transform-Modus für den ausgewählten Body.
        
        Args:
            mode: "move", "rotate" oder "scale"
        """
        body = self._get_active_body()
        if not body:
            # Warte auf Body-Selektion
            self._pending_transform_mode = mode
            self.statusBar().showMessage(f"Wähle einen Body zum {mode.title()}")
            return

        self._show_transform_ui(body.id, body.name, mode)

    def _start_multi_body_transform(self, mode: str, bodies: list):
        """
        Startet Transform-Modus für mehrere Bodies.
        
        Args:
            mode: "move", "rotate" oder "scale"
            bodies: Liste von Body-Objekten
        """
        if not bodies:
            return

        # Zeige Transform-UI für den ersten Body
        first_body = bodies[0]
        self._show_transform_ui(first_body.id, first_body.name, mode)

        # Merke alle Bodies für Multi-Transform
        self._transform_bodies = bodies

    def _show_transform_ui(self, body_id: str, body_name: str, mode: str = None):
        """Zeigt Transform-UI für einen Body"""
        if mode:
            self.transform_panel.set_mode(mode)

        # TransformPanel API changed during refactor; keep compatibility with both variants.
        if hasattr(self.transform_panel, "set_body_name"):
            self.transform_panel.set_body_name(body_name)
        elif hasattr(self.transform_panel, "set_body"):
            self.transform_panel.set_body(body_name)
        else:
            # At least expose the selected body context to the user.
            self.transform_panel.setToolTip(f"Body: {body_name}")
        self.transform_panel.show()
        self._position_transform_panel()
        
        # Gizmo im Viewport aktivieren
        if hasattr(self.viewport_3d, 'show_transform_gizmo'):
            self.viewport_3d.show_transform_gizmo(body_id, mode or 'move')

    def _hide_transform_ui(self):
        """Versteckt Transform-UI und alle interaktiven Panels."""
        if hasattr(self, 'transform_panel'):
            self.transform_panel.hide()
        if hasattr(self.viewport_3d, 'hide_transform_gizmo'):
            self.viewport_3d.hide_transform_gizmo()
        if hasattr(self, 'transform_toolbar'):
            self.transform_toolbar.clear_active()
        self._selected_body_for_transform = None

    def _on_transform_panel_confirmed(self, mode: str, data):
        """Handler wenn Transform im Panel bestätigt wird"""
        body_id = self._get_selected_body_id()
        if not body_id:
            logger.warning("Kein Body selektiert für Transform")
            return

        self._on_body_transform_requested(body_id, mode, data)
        self.transform_panel.reset_values()

    def _on_transform_panel_cancelled(self):
        """Handler wenn Transform abgebrochen wird"""
        self._hide_transform_ui()

    def _on_transform_mode_changed(self, mode: str):
        """Handler wenn Transform-Modus geändert wird"""
        if hasattr(self.viewport_3d, 'set_transform_mode'):
            self.viewport_3d.set_transform_mode(mode)
        mode_to_action = {"move": "move_body", "rotate": "rotate_body", "scale": "scale_body"}
        if mode in mode_to_action:
            self.transform_toolbar.set_active(mode_to_action[mode])

    def _on_grid_size_changed(self, grid_size: float):
        """Handler wenn Grid-Size geändert wird"""
        if hasattr(self.viewport_3d, 'transform_state') and self.viewport_3d.transform_state:
            self.viewport_3d.transform_state.snap_grid_size = grid_size

    def _on_pivot_mode_changed(self, mode: str):
        """Handler wenn Pivot-Mode geändert wird"""
        if hasattr(self.viewport_3d, 'transform_state') and self.viewport_3d.transform_state:
            self.viewport_3d.transform_state.pivot_mode = mode

    def _get_selected_body_id(self) -> str:
        """Gibt ID des aktuell für Transform selektierten Bodies zurück"""
        # Priorität: Explizit selektierter Body
        if hasattr(self, '_selected_body_for_transform') and self._selected_body_for_transform:
            return self._selected_body_for_transform
        
        # Fallback: Aktiver Body aus Browser
        body = self._get_active_body()
        return body.id if body else None

    def _on_transform_values_live_update(self, x: float, y: float, z: float):
        """Handler für Live-Update der Transform-Werte während Drag"""
        if hasattr(self, 'transform_panel') and self.transform_panel and self.transform_panel.isVisible():
            if hasattr(self.transform_panel, 'set_values'):
                self.transform_panel.set_values(x, y, z)
            elif hasattr(self.transform_panel, 'update_values'):
                self.transform_panel.update_values(x, y, z)

    def _on_transform_val_change(self, x, y, z):
        """Live Update vom Panel -> Viewport Actor"""
        if hasattr(self.viewport_3d, 'update_transform_preview'):
            self.viewport_3d.update_transform_preview(x, y, z)

    def _on_viewport_transform_update(self, x, y, z):
        """Live Update vom Viewport Gizmo -> Panel Input Felder"""
        if hasattr(self, 'transform_panel') and self.transform_panel.isVisible():
            self.transform_panel.set_values(x, y, z)

    def _on_transform_confirmed(self):
        """Finalisieren der Transformation"""
        self.transform_panel.hide()
        if hasattr(self.viewport_3d, 'apply_transform'):
            self.viewport_3d.apply_transform()
        self._trigger_viewport_update()

    def _on_transform_cancelled(self):
        """Abbrechen der Transformation"""
        self.transform_panel.hide()
        if hasattr(self.viewport_3d, 'cancel_transform'):
            self.viewport_3d.cancel_transform()
        self._trigger_viewport_update()
    
    # =========================================================================
    # Point-to-Point Move
    # =========================================================================
    
    def _start_point_to_point_move(self):
        """Startet Point-to-Point Move Modus (CAD-Style) - OHNE Body-Selektion möglich"""
        self._p2p_body_id = None
        self._p2p_repick_body = False
        
        # Panel anzeigen (ohne Body)
        self.p2p_panel.reset()
        self.p2p_panel.show_at(self.viewport_3d)
        
        # Ersten Punkt aktivieren
        self.p2p_panel.start_pick(1)
        
        # Viewport in Pick-Modus versetzen
        self.viewport_3d.set_p2p_mode(True)
        
        self.statusBar().showMessage("Point-to-Point: Ersten Punkt wählen")
        logger.info("Point-to-Point Move gestartet")

    def _on_p2p_pick_body_requested(self):
        """Allow re-picking the body for point-to-point move."""
        self._p2p_repick_body = True
        self.viewport_3d.set_p2p_mode(True, pick_body=True)
        self.statusBar().showMessage("Wähle den zu verschiebenden Body")

    def _on_point_to_point_move(self, body_id: str, start_point: tuple, end_point: tuple):
        """
        Führt Point-to-Point Move aus.
        
        Args:
            body_id: ID des zu verschiebenden Bodies
            start_point: Startpunkt (x, y, z)
            end_point: Endpunkt (x, y, z)
        """
        import numpy as np
        
        body = self.document.find_body_by_id(body_id)
        if not body:
            logger.error(f"Body nicht gefunden: {body_id}")
            return

        # Berechne Verschiebungsvektor
        start = np.array(start_point)
        end = np.array(end_point)
        translation = tuple(end - start)

        # Transform anwenden
        self._on_body_transform_requested(body_id, 'move', {'translation': translation})
        
        logger.success(f"Body '{body.name}' verschoben um {translation}")

    def _on_point_to_point_start_picked(self, point: tuple):
        """Handler wenn Startpunkt gepickt wurde."""
        if hasattr(self, "p2p_panel"):
            self.p2p_panel.set_point(1, point)
            self.p2p_panel.start_pick(2)
            self.statusBar().showMessage("Point-to-Point: Zweiten Punkt wählen")

    def _on_point_to_point_cancelled(self):
        """Handler wenn Point-to-Point abgebrochen wurde."""
        if self._p2p_repick_body:
            # War nur Body-Repick, nicht den ganzen Modus beenden
            self._p2p_repick_body = False
            return
        
        self._reset_point_to_point_move()

    def _reset_point_to_point_move(self):
        """Setzt Point-to-Point Move zurück."""
        if getattr(self, "_p2p_body_id", None):
            self.viewport_3d.set_p2p_mode(False)
        
        self._p2p_body_id = None
        self._p2p_repick_body = False
        
        if hasattr(self, "p2p_panel"):
            self.p2p_panel.hide()
            self.p2p_panel.reset()
        
        self.statusBar().clearMessage()

    def _cancel_point_to_point_move(self):
        """Bricht Point-to-Point Move komplett ab."""
        self._pending_transform_mode = None
        self._reset_point_to_point_move()
        logger.info("Point-to-Point Move abgebrochen")
    
    # =========================================================================
    # Measure Tool
    # =========================================================================
    
    def _start_measure_mode(self):
        """Startet den Mess-Modus: 2 Punkte anklicken -> Distanz anzeigen"""
        self._measure_mode = True
        self._measure_points = [None, None]
        
        # Panel anzeigen
        if hasattr(self, 'measure_panel'):
            self.measure_panel.reset()
            self.measure_panel.show_at(self.viewport_3d)
        
        # Viewport in Pick-Modus versetzen
        self.viewport_3d.set_measure_mode(True)
        
        self.statusBar().showMessage("Mess-Modus: Ersten Punkt wählen")
        logger.info("Mess-Modus gestartet")

    def _on_measure_point_picked(self, point):
        """Wird aufgerufen wenn ein Punkt im Measure-Modus gepickt wurde"""
        # Pattern-Center-Pick hat Priorität vor normalem Measure-Workflow.
        if getattr(self, '_pattern_center_pick_mode', False):
            if hasattr(self, '_on_pattern_center_picked'):
                self._on_pattern_center_picked(point)
            return

        import numpy as np
        
        # Ersten Punkt setzen
        if self._measure_points[0] is None:
            self._measure_points[0] = point
            self.statusBar().showMessage("Mess-Modus: Zweiten Punkt wählen")
            
        # Zweiten Punkt setzen und Distanz berechnen
        elif self._measure_points[1] is None:
            self._measure_points[1] = point
            
            # Distanz berechnen
            p1 = np.array(self._measure_points[0])
            p2 = np.array(self._measure_points[1])
            distance = np.linalg.norm(p2 - p1)
            
            # Anzeigen
            if hasattr(self, 'measure_panel'):
                self.measure_panel.set_distance(distance)
                self.measure_panel.set_points(self._measure_points[0], self._measure_points[1])
            
            self._update_measure_visuals()
            self.statusBar().showMessage(f"Distanz: {distance:.3f} mm")
            logger.info(f"Gemessene Distanz: {distance:.3f} mm")

    def _clear_measure_actors(self, render: bool = True):
        """Entfernt alle Mess-Visualisierungen"""
        if hasattr(self, 'viewport_3d'):
            self.viewport_3d.clear_measure_actors(render)

    def _update_measure_visuals(self):
        """Aktualisiert alle Mess-Visualisierungen (Punkte, Linie, Label)."""
        if not hasattr(self, 'viewport_3d') or not hasattr(self, '_measure_points'):
            return
        
        self.viewport_3d.update_measure_visuals(self._measure_points)

    def _update_measure_ui(self):
        """Aktualisiert das Measure-Panel."""
        if not hasattr(self, "measure_panel"):
            return
        
        p1, p2 = self._measure_points
        self.measure_panel.set_points(p1, p2)
        if p1 is not None and p2 is not None:
            import numpy as np
            distance = float(np.linalg.norm(np.array(p2) - np.array(p1)))
            self.measure_panel.set_distance(distance)
        else:
            self.measure_panel.set_distance(None)

    def _on_measure_pick_requested(self, which: int):
        """User wants to re-pick P1 or P2."""
        self._measure_points[which - 1] = None
        self.viewport_3d.set_measure_mode(True)
        self.statusBar().showMessage(f"Wähle Punkt {which}")

    def _clear_measure_points(self):
        """Setzt Mess-Punkte zurück."""
        self._measure_points = [None, None]
        self._clear_measure_actors()
        if hasattr(self, "measure_panel"):
            self.measure_panel.reset()

    def _close_measure_panel(self):
        """Schließt das Measure-Panel."""
        self._cancel_measure_mode()

    def _cancel_measure_mode(self):
        """Bricht den Mess-Modus ab"""
        self._measure_mode = False
        self._clear_measure_points()
        
        if hasattr(self, 'viewport_3d'):
            self.viewport_3d.set_measure_mode(False)
        
        if hasattr(self, "measure_panel"):
            self.measure_panel.hide()
        
        self.statusBar().clearMessage()
        logger.info("Mess-Modus beendet")
    
    # =========================================================================
    # Sketch Tools
    # =========================================================================
    
    def _on_sketch_tool_selected(self, tool_name: str):
        """Verarbeitet Tool-Auswahl aus dem Sketch-ToolPanel"""
        from gui.sketch_tools import SketchTool
        
        tool_map = {
            # Draw tools
            'line': SketchTool.LINE,
            'rectangle': SketchTool.RECTANGLE,
            'circle': SketchTool.CIRCLE,
            'ellipse': SketchTool.ELLIPSE,
            'polygon': SketchTool.POLYGON,
            'arc_3point': SketchTool.ARC_3POINT,
            'slot': SketchTool.SLOT,
            'spline': SketchTool.SPLINE,
            'point': SketchTool.POINT,
            'project': SketchTool.PROJECT,
            # Shapes
            'gear': SketchTool.GEAR,
            'star': SketchTool.STAR,
            'nut': SketchTool.NUT,
            'text': SketchTool.TEXT,
            # Modify tools
            'select': SketchTool.SELECT,
            'move': SketchTool.MOVE,
            'copy': SketchTool.COPY,
            'rotate': SketchTool.ROTATE,
            'mirror': SketchTool.MIRROR,
            'scale': SketchTool.SCALE,
            'trim': SketchTool.TRIM,
            'offset': SketchTool.OFFSET,
            'fillet_2d': SketchTool.FILLET_2D,
            'chamfer_2d': SketchTool.CHAMFER_2D,
            # Patterns
            'pattern_linear': SketchTool.PATTERN_LINEAR,
            'pattern_circular': SketchTool.PATTERN_CIRCULAR,
            # Constraints
            'dimension': SketchTool.DIMENSION,
            'dimension_angle': SketchTool.DIMENSION_ANGLE,
            'horizontal': SketchTool.HORIZONTAL,
            'vertical': SketchTool.VERTICAL,
            'parallel': SketchTool.PARALLEL,
            'perpendicular': SketchTool.PERPENDICULAR,
            'equal': SketchTool.EQUAL,
            'concentric': SketchTool.CONCENTRIC,
            'tangent': SketchTool.TANGENT,
        }
        if tool_name in tool_map:
            self.sketch_editor.set_tool(tool_map[tool_name])
        else:
            logger.warning(f"Unknown sketch tool: {tool_name}")
    
    # =========================================================================
    # Feature Tools
    # =========================================================================
    
    def _start_fillet(self):
        """Startet den Fillet-Modus."""
        self._start_fillet_chamfer_mode("fillet")

    def _start_chamfer(self):
        """Startet den Chamfer-Modus."""
        self._start_fillet_chamfer_mode("chamfer")

    def _start_fillet_chamfer_mode(self, mode: str):
        """
        Startet Fillet/Chamfer-Modus.
        
        Args:
            mode: "fillet" oder "chamfer"
        """
        self._fillet_mode = mode
        self._fillet_target_body = None

        selected_bodies = self.browser.get_selected_bodies() if hasattr(self, 'browser') else []

        # Kein Body selektiert -> Pending-Body-Pick im Viewport aktivieren.
        if not selected_bodies:
            # Legacy + neues Flag robust setzen (FeatureDialogs erwartet beides).
            self._pending_fillet_mode = mode
            self._pending_chamfer_mode = (mode == "chamfer")
            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)
            self.viewport_3d.setCursor(Qt.CrossCursor)
            self.statusBar().showMessage(f"{mode.capitalize()}: Wähle einen Body")
            return

        body = selected_bodies[0]
        self._activate_fillet_chamfer_for_body(body, mode)

    def _resolve_body_for_edge_selection(self, body_id: str):
        """Robuster Body-Lookup für EdgeSelectionMixin."""
        body = None
        if hasattr(self.document, 'find_body_by_id'):
            body = self.document.find_body_by_id(body_id)
        if body is None and hasattr(self.document, 'get_all_bodies'):
            body = next((b for b in self.document.get_all_bodies() if b.id == body_id), None)
        return body

    def _activate_fillet_chamfer_for_body(self, body, mode: str):
        """Aktiviert Fillet/Chamfer-Modus für einen Body."""
        self._fillet_mode = mode
        self._fillet_target_body = body
        self._pending_fillet_mode = False
        self._pending_chamfer_mode = False

        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        # Edge-Selection aktivieren
        if hasattr(self.viewport_3d, 'set_edge_selection_callbacks'):
            self.viewport_3d.set_edge_selection_callbacks(
                get_body_by_id=self._resolve_body_for_edge_selection
            )

        if hasattr(self.viewport_3d, 'start_edge_selection_mode'):
            # Historisch waren alle Kanten selektierbar; "concave only" hat Fillet faktisch deaktiviert.
            self.viewport_3d.start_edge_selection_mode(body.id, "all")
        else:
            logger.warning("Viewport hat keine start_edge_selection_mode Methode")

        # Panel anzeigen
        if hasattr(self.fillet_panel, 'set_target_body'):
            self.fillet_panel.set_target_body(body)
        self.fillet_panel.set_mode(mode)
        self.fillet_panel.reset()
        if hasattr(self.fillet_panel, 'update_edge_count'):
            self.fillet_panel.update_edge_count(0)
        self.fillet_panel.show_at(self.viewport_3d)

        self.statusBar().showMessage(f"{mode.title()}: Kanten wählen")

    def _on_edge_selection_changed(self, count: int):
        """Handler wenn sich die Kanten-Selektion ändert."""
        if hasattr(self, 'fillet_panel') and self.fillet_panel.isVisible():
            if hasattr(self.fillet_panel, 'update_edge_count'):
                self.fillet_panel.update_edge_count(count)
            elif hasattr(self.fillet_panel, 'set_edge_count'):
                self.fillet_panel.set_edge_count(count)

        if getattr(self, '_nsided_patch_mode', False) and hasattr(self, 'nsided_patch_panel'):
            if hasattr(self.nsided_patch_panel, 'update_edge_count'):
                self.nsided_patch_panel.update_edge_count(count)
            elif hasattr(self.nsided_patch_panel, 'set_edge_count'):
                self.nsided_patch_panel.set_edge_count(count)

        if getattr(self, '_sweep_mode', False) and getattr(self, '_sweep_phase', None) == 'path' and count > 0:
            if hasattr(self.viewport_3d, 'get_selected_edges') and hasattr(self, '_on_edge_selected_for_sweep'):
                edges = self.viewport_3d.get_selected_edges() or []
                self._on_edge_selected_for_sweep(edges)

    def _on_fillet_confirmed(self):
        """
        Wendet Fillet/Chamfer über die Feature-Pipeline mit Undo/Redo an.
        """
        from PySide6.QtWidgets import QMessageBox
        from config.feature_flags import is_enabled

        radius = self.fillet_panel.get_radius()
        body = self._fillet_target_body
        mode = getattr(self, '_fillet_mode', 'fillet')
        if body is None and hasattr(self.fillet_panel, 'get_target_body'):
            body = self.fillet_panel.get_target_body()
            self._fillet_target_body = body

        if body is None:
            logger.warning(f"{mode.capitalize()}: Kein Ziel-Body ausgewählt")
            return

        # Selektierte Kanten vom Viewport holen
        edges = self.viewport_3d.get_selected_edges()

        if not edges:
            res = QMessageBox.question(
                self, "Keine Kanten",
                "Keine Kanten ausgewählt. Alle Kanten bearbeiten?",
                QMessageBox.Yes | QMessageBox.No
            )
            if res == QMessageBox.Yes:
                # Alle Kanten nehmen
                edges = list(body._build123d_solid.edges())
            else:
                return

        # Feature erstellen und via Undo-Stack anwenden
        logger.info(f"Wende {mode} auf {len(edges)} Kanten an (r={radius})...")

        try:
            from gui.commands.feature_commands import AddFeatureCommand
            from modeling.geometric_selector import create_geometric_selectors_from_edges
            from modeling.tnp_system import ShapeType

            selected_edge_indices = []
            if hasattr(self.viewport_3d, "get_selected_edge_topology_indices"):
                selected_edge_indices = self.viewport_3d.get_selected_edge_topology_indices() or []
            if not selected_edge_indices and body is not None and hasattr(body, "_build123d_solid") and body._build123d_solid:
                try:
                    all_edges = list(body._build123d_solid.edges())

                    def _is_same_edge(edge_a, edge_b) -> bool:
                        try:
                            wa = edge_a.wrapped if hasattr(edge_a, "wrapped") else edge_a
                            wb = edge_b.wrapped if hasattr(edge_b, "wrapped") else edge_b
                            return wa.IsSame(wb)
                        except Exception:
                            return edge_a is edge_b

                    for edge in edges:
                        for edge_idx, candidate in enumerate(all_edges):
                            if _is_same_edge(candidate, edge):
                                selected_edge_indices.append(edge_idx)
                                break
                except Exception:
                    pass
            selected_edge_indices = sorted(set(int(i) for i in selected_edge_indices))

            # TNP Phase 1: GeometricSelectors erstellen
            # WICHTIG: Nutze die bereits ermittelten `edges` (inkl. "alle Kanten"),
            # nicht nochmal get_selected_edges() aufrufen!
            geometric_selectors = create_geometric_selectors_from_edges(edges)
            if is_enabled("tnp_debug_logging"):
                logger.debug(f"TNP Phase 1: {len(geometric_selectors)} GeometricSelectors erstellt")

            # TNP Phase 2: OCP Edge Shapes speichern
            ocp_edge_shapes = []
            for edge in edges:
                if hasattr(edge, 'wrapped'):
                    ocp_edge_shapes.append(edge.wrapped)

            # TNP Phase 2: Finde vorheriges Boolean-Feature (für History-Lookup)
            depends_on_feature_id = None
            from modeling import ExtrudeFeature
            for feat in reversed(body.features):
                if isinstance(feat, ExtrudeFeature) and feat.operation in ["Join", "Cut", "Intersect"]:
                    depends_on_feature_id = feat.id
                    if is_enabled("tnp_debug_logging"):
                        logger.debug(f"TNP Phase 2: Fillet/Chamfer hängt von Feature {feat.name} ab")
                    break

            # Feature erstellen (ZUERST - damit es eine ID bekommt)
            from modeling import FilletFeature, ChamferFeature

            if mode == "chamfer":
                feature = ChamferFeature(
                    distance=radius,
                    edge_indices=selected_edge_indices,
                    geometric_selectors=geometric_selectors,
                    ocp_edge_shapes=ocp_edge_shapes,
                    depends_on_feature_id=depends_on_feature_id
                )
            else:
                feature = FilletFeature(
                    radius=radius,
                    edge_indices=selected_edge_indices,
                    geometric_selectors=geometric_selectors,
                    ocp_edge_shapes=ocp_edge_shapes,
                    depends_on_feature_id=depends_on_feature_id
                )

            # TNP v4.0: ShapeIDs für ausgewählte Edges finden (nicht neu erstellen!)
            edge_shape_ids = []
            if body._document and hasattr(body._document, '_shape_naming_service'):
                service = body._document._shape_naming_service
                for edge in edges:
                    # Finde existierende ShapeID für diese Edge
                    shape_id = service.find_shape_id_by_edge(edge, require_exact=True)
                    if shape_id:
                        edge_shape_ids.append(shape_id)
                        if is_enabled("tnp_debug_logging"):
                            logger.debug(f"TNP v4.0: ShapeID gefunden für Edge: {shape_id.uuid[:8]}...")
                    else:
                        # Fallback: Edge jetzt registrieren, damit TNP weiterarbeiten kann
                        try:
                            shape_id = service.register_shape(
                                ocp_shape=edge.wrapped,
                                shape_type=ShapeType.EDGE,
                                feature_id=feature.id,
                                local_index=len(edge_shape_ids)
                            )
                            edge_shape_ids.append(shape_id)
                            if is_enabled("tnp_debug_logging"):
                                logger.debug(f"TNP v4.0: Edge registriert (Fallback) {shape_id.uuid[:8]}...")
                        except Exception as e:
                            if is_enabled("tnp_debug_logging"):
                                logger.warning(f"TNP v4.0: Keine ShapeID für Edge gefunden: {e}")
            else:
                if is_enabled("tnp_debug_logging"):
                    logger.warning("TNP v4.0: Kein NamingService verfügbar")

            feature.edge_shape_ids = edge_shape_ids
            if is_enabled("tnp_debug_logging"):
                logger.debug(f"TNP v4.0: {len(edge_shape_ids)} ShapeIDs für Feature {feature.id} gefunden")

            # TNP v4.0: Keine zusätzliche Registrierung nötig
            # ShapeIDs wurden bereits vom Extrude registriert

            # KRITISCH: Verwende AddFeatureCommand für korrektes Undo/Redo!
            # Das ruft body.add_feature() auf, was _rebuild() triggert.
            # Geometry-Snapshot VOR Operation (für Operation Summary)
            _pre_sig = self._solid_signature_safe(body)

            cmd = AddFeatureCommand(body, feature, self, description=f"{mode.capitalize()} R={radius}")
            self.undo_stack.push(cmd)

            # Geometry-Snapshot NACH Operation
            _post_sig = self._solid_signature_safe(body)

            # Prüfe ob Operation erfolgreich war
            if body._build123d_solid is None or (hasattr(body, 'vtk_mesh') and body.vtk_mesh is None):
                logger.warning(f"{mode.capitalize()} ließ Body leer - Undo")
                self.undo_stack.undo()
                QMessageBox.warning(
                    self, "Fehler",
                    f"{mode.capitalize()} fehlgeschlagen: Geometrie ungültig"
                )
                return

            if feature.status == "ERROR":
                msg = feature.status_message or "Kernel-Operation fehlgeschlagen"
                self.statusBar().showMessage(f"{mode.capitalize()} fehlgeschlagen: {msg}", 8000)
                logger.error(f"{mode.capitalize()} fehlgeschlagen: {msg}")
                self._on_fillet_cancelled()
                self.browser.refresh()
                return

            if feature.status == "WARNING":
                msg = feature.status_message or "Fallback verwendet"
                self.statusBar().showMessage(f"{mode.capitalize()} mit Warnung: {msg}", 6000)
                logger.warning(f"{mode.capitalize()} mit Warnung: {msg}")

            # Visualisierung aktualisieren
            from modeling.cad_tessellator import CADTessellator
            CADTessellator.notify_body_changed()
            self._update_body_from_build123d(body, body._build123d_solid)

            # Aufräumen
            self._on_fillet_cancelled()
            self.browser.refresh()

            logger.success(f"{mode.capitalize()} erfolgreich: {len(edges)} Kanten, r={radius}")

        except Exception as e:
            logger.error(f"{mode.capitalize()} fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Fehler", f"{mode.capitalize()} fehlgeschlagen:\n{str(e)}")

    def _on_fillet_radius_changed(self, radius):
        """
        Callback wenn der Radius geändert wird.
        Verwendet das Live-Preview-System für performante Vorschau.
        """
        from config.feature_flags import is_enabled

        if not is_enabled("live_preview_fillet"):
            return

        if not getattr(self, '_fillet_mode', False) or not getattr(self, '_fillet_target_body', None):
            return

        # Request debounced live preview
        if hasattr(self, '_request_live_preview'):
            self._request_live_preview('fillet', {
                'radius': radius,
                'body': self._fillet_target_body,
                'edge_indices': list(getattr(self, '_fillet_edge_indices', [])),
                'mode': getattr(self, '_fillet_mode', 'fillet')
            })

    def _on_fillet_cancelled(self):
        """Bricht die Fillet/Chamfer-Operation ab."""
        if hasattr(self.viewport_3d, 'stop_edge_selection_mode'):
            self.viewport_3d.stop_edge_selection_mode()

        if hasattr(self, 'fillet_panel'):
            self.fillet_panel.hide()

        # Live-Preview abbrechen
        if hasattr(self, '_cancel_live_preview'):
            self._cancel_live_preview('fillet')
        elif hasattr(self.viewport_3d, 'clear_all_feature_previews'):
            self.viewport_3d.clear_all_feature_previews()

        self._fillet_mode = None
        self._fillet_target_body = None
        self._fillet_edge_indices = []
        self._pending_fillet_mode = False
        self._pending_chamfer_mode = False
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)
        self.viewport_3d.setCursor(Qt.ArrowCursor)

        logger.info("Fillet/Chamfer abgebrochen")

    def _start_shell(self):
        """Startet den Shell-Modus."""
        if hasattr(self, '_clear_transient_previews'):
            self._clear_transient_previews(reason="start_shell", clear_interaction_modes=True)

        selected_bodies = self.browser.get_selected_bodies() if hasattr(self, 'browser') else []
        if not selected_bodies:
            self._pending_shell_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)
            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)
            self.statusBar().showMessage("Shell: Wähle einen Body")
            return

        self._activate_shell_for_body(selected_bodies[0])

    def _start_sweep(self):
        """Startet den Sweep-Modus."""
        if hasattr(self.viewport_3d, 'hide_transform_gizmo'):
            self.viewport_3d.hide_transform_gizmo()

        self._sweep_mode = True
        self._sweep_phase = 'profile'
        self._sweep_profile_data = None
        self._sweep_path_data = None
        self._sweep_profile_shape_id = None
        self._sweep_profile_face_index = None
        self._sweep_profile_geometric_selector = None

        # Face picking for profile selection.
        if hasattr(self.viewport_3d, 'set_sweep_mode'):
            self.viewport_3d.set_sweep_mode(True)
        if hasattr(self.viewport_3d, 'set_extrude_mode'):
            self.viewport_3d.set_extrude_mode(True, enable_preview=False)
        if hasattr(self, '_update_detector'):
            self._update_detector()

        # Panel anzeigen
        self.sweep_panel.reset()
        self.sweep_panel.show_at(self.viewport_3d)

        self.statusBar().showMessage("Sweep: Profil wählen")

    def _start_loft(self):
        """Startet den Loft-Modus."""
        if hasattr(self.viewport_3d, 'hide_transform_gizmo'):
            self.viewport_3d.hide_transform_gizmo()

        self._loft_mode = True
        self._loft_profiles = []

        # Face picking for profile selection.
        if hasattr(self.viewport_3d, 'set_loft_mode'):
            self.viewport_3d.set_loft_mode(True)
        if hasattr(self.viewport_3d, 'set_extrude_mode'):
            self.viewport_3d.set_extrude_mode(True, enable_preview=False)
        if hasattr(self, '_update_detector'):
            self._update_detector()

        # Panel anzeigen
        self.loft_panel.reset()
        self.loft_panel.show_at(self.viewport_3d)

        self.statusBar().showMessage("Loft: Profile wählen")

    def _start_pattern(self):
        """Startet den Pattern-Modus."""
        self._pattern_mode = False
        self._pattern_target_body = None
        
        # Prüfe ob Body selektiert
        body = self._get_active_body()
        if body:
            self._activate_pattern_for_body(body)
        else:
            self._pending_pattern_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)
            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)
            self.statusBar().showMessage("Wähle einen Body für Pattern")

    def _start_texture_mode(self):
        """Startet den Texture-Modus."""
        self._texture_mode = False
        self._texture_target_body = None
        
        # Prüfe ob Body selektiert
        body = self._get_active_body()
        if body:
            self._activate_texture_for_body(body)
        else:
            self._pending_texture_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)
            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)
            self.statusBar().showMessage("Wähle einen Body für Textur")

    def _activate_texture_for_body(self, body):
        """Aktiviert Texture-Modus für einen Body."""
        if getattr(body, '_build123d_solid', None) is None:
            logger.warning(f"'{body.name}' hat keine CAD-Daten (nur Mesh).")
            return

        self._texture_mode = True
        self._texture_target_body = body
        self._pending_texture_mode = False

        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        # Face-Picking aktivieren.
        if hasattr(self.viewport_3d, 'set_extrude_mode'):
            self.viewport_3d.set_extrude_mode(True, enable_preview=False)
        if hasattr(self, '_update_detector'):
            self._update_detector()
        if hasattr(self.viewport_3d, 'start_texture_face_mode'):
            self.viewport_3d.start_texture_face_mode(body.id)
        
        # Panel anzeigen
        self.texture_panel.reset()
        if hasattr(self.texture_panel, 'set_body'):
            self.texture_panel.set_body(body)
        self.texture_panel.show_at(self.viewport_3d)
        
        self.statusBar().showMessage("Textur: Einstellungen wählen")

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def _get_active_body(self):
        """Hilfsfunktion: Gibt den aktuell im Browser ausgewählten Body zurück"""
        if hasattr(self, 'browser'):
            selected = self.browser.get_selected_bodies()
            return selected[0] if selected else None
        return None
