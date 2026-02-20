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
        from i18n import tr
        
        action_handlers = {
            # Primitives
            'box': lambda: self._primitive_dialog('box'),
            'cylinder': lambda: self._primitive_dialog('cylinder'),
            'sphere': lambda: self._primitive_dialog('sphere'),
            'cone': lambda: self._primitive_dialog('cone'),
            'torus': lambda: self._primitive_dialog('torus'),
            
            # Sketch
            'new_sketch': self._new_sketch,
            'offset_plane': self._start_offset_plane,
            
            # Features
            'extrude': self._extrude_dialog,
            'revolve': self._revolve_dialog,
            'fillet': self._start_fillet,
            'chamfer': self._start_chamfer,
            'shell': self._start_shell,
            'sweep': self._start_sweep,
            'loft': self._start_loft,
            'pattern': self._start_pattern,
            'draft': self._draft_dialog,
            'hole': self._hole_dialog,
            'thread': self._thread_dialog,
            'split': self._split_body_dialog,
            
            # Boolean
            'union': lambda: self._boolean_operation_dialog('Union'),
            'cut': lambda: self._boolean_operation_dialog('Cut'),
            'intersect': lambda: self._boolean_operation_dialog('Intersect'),
            
            # Transform
            'move': lambda: self._start_transform_mode('move'),
            'rotate': lambda: self._start_transform_mode('rotate'),
            'scale': lambda: self._start_transform_mode('scale'),
            'mirror': self._mirror_body,
            'copy': self._copy_body,
            'point_to_point': self._start_point_to_point_move,
            
            # View
            'section_view': self._toggle_section_view,
            'measure': self._start_measure_mode,
            
            # Import/Export
            'import_mesh': self._import_mesh_dialog,
            'import_step': self._import_step,
            'import_svg': self._import_svg,
            'stl_to_cad': self._on_stl_to_cad,
            
            # Special
            'brep_cleanup': self._toggle_brep_cleanup,
            'texture': self._start_texture_mode,
            'lattice': self._start_lattice,
            'nsided_patch': self._nsided_patch_dialog,
        }

        handler = action_handlers.get(action)
        if handler:
            try:
                handler()
            except Exception as e:
                logger.error(f"Aktion '{action}' fehlgeschlagen: {e}")
        else:
            self._show_not_implemented(action)
    
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
        
        self.transform_panel.set_body_name(body_name)
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
        pass  # Wird vom Viewport gehandhabt

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
            self.measure_panel.show_at(self.viewport_3d)
        
        # Viewport in Pick-Modus versetzen
        self.viewport_3d.set_measure_mode(True)
        
        self.statusBar().showMessage("Mess-Modus: Ersten Punkt wählen")
        logger.info("Mess-Modus gestartet")

    def _on_measure_point_picked(self, point):
        """Wird aufgerufen wenn ein Punkt im Measure-Modus gepickt wurde"""
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
        
        if self._measure_points[0] is not None:
            self.measure_panel.set_point(1, self._measure_points[0])
        if self._measure_points[1] is not None:
            self.measure_panel.set_point(2, self._measure_points[1])

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
            self.measure_panel.clear_points()

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
        self._fillet_mode = 'fillet'
        self._fillet_target_body = None
        
        # Prüfe ob Body selektiert
        body = self._get_active_body()
        if body:
            self._activate_fillet_chamfer_for_body(body, 'fillet')
        else:
            self._pending_fillet_mode = True
            self.statusBar().showMessage("Wähle einen Body für Fase")

    def _start_chamfer(self):
        """Startet den Chamfer-Modus."""
        self._fillet_mode = 'chamfer'
        self._fillet_target_body = None
        
        # Prüfe ob Body selektiert
        body = self._get_active_body()
        if body:
            self._activate_fillet_chamfer_for_body(body, 'chamfer')
        else:
            self._pending_chamfer_mode = True
            self.statusBar().showMessage("Wähle einen Body für Fase")

    def _start_fillet_chamfer_mode(self, mode: str):
        """
        Startet Fillet/Chamfer-Modus.
        
        Args:
            mode: "fillet" oder "chamfer"
        """
        self._fillet_mode = mode
        self._fillet_target_body = None
        
        # Edge-Selection im Viewport aktivieren
        self.viewport_3d.set_edge_selection_mode(True)
        
        # Panel vorbereiten
        self.fillet_panel.set_mode(mode)
        self.fillet_panel.reset()
        self.fillet_panel.show_at(self.viewport_3d)
        
        self.statusBar().showMessage(f"{mode.title()}: Kanten wählen")

    def _on_body_clicked_for_fillet(self, body_id: str):
        """Handler wenn Body für Fillet/Chamfer geklickt wird."""
        body = self.document.find_body_by_id(body_id)
        if body:
            self._activate_fillet_chamfer_for_body(body, self._fillet_mode)

    def _activate_fillet_chamfer_for_body(self, body, mode: str):
        """Aktiviert Fillet/Chamfer-Modus für einen Body."""
        self._fillet_target_body = body
        self._fillet_mode = mode
        
        # Edge-Selection aktivieren
        self.viewport_3d.set_edge_selection_mode(True, body.id)
        
        # Panel anzeigen
        self.fillet_panel.set_mode(mode)
        self.fillet_panel.reset()
        self.fillet_panel.show_at(self.viewport_3d)
        
        self.statusBar().showMessage(f"{mode.title()}: Kanten wählen")

    def _on_edge_selection_changed(self, count: int):
        """Handler wenn sich die Kanten-Selektion ändert."""
        if hasattr(self, 'fillet_panel') and self.fillet_panel.isVisible():
            self.fillet_panel.set_edge_count(count)

    def _on_fillet_confirmed(self):
        """Bestätigt Fillet/Chamfer-Operation."""
        if not self._fillet_target_body:
            return
        
        # Implementierung in main_window.py
        pass

    def _on_fillet_radius_changed(self, radius):
        """Handler wenn Fillet-Radius geändert wird."""
        if hasattr(self.viewport_3d, 'update_fillet_preview'):
            self.viewport_3d.update_fillet_preview(radius)

    def _on_fillet_cancelled(self):
        """Bricht Fillet/Chamfer-Operation ab."""
        self._fillet_mode = None
        self._fillet_target_body = None
        
        if hasattr(self.viewport_3d, 'set_edge_selection_mode'):
            self.viewport_3d.set_edge_selection_mode(False)
        
        if hasattr(self, 'fillet_panel'):
            self.fillet_panel.hide()
        
        self.statusBar().clearMessage()

    def _start_shell(self):
        """Startet den Shell-Modus."""
        self._shell_mode = False
        self._shell_target_body = None
        self._shell_opening_faces = []
        
        # Prüfe ob Body selektiert
        body = self._get_active_body()
        if body:
            self._activate_shell_for_body(body)
        else:
            self._pending_shell_mode = True
            self.statusBar().showMessage("Wähle einen Body für Shell")

    def _start_sweep(self):
        """Startet den Sweep-Modus."""
        self._sweep_mode = True
        self._sweep_phase = 'profile'
        self._sweep_profile_data = None
        self._sweep_path_data = None
        
        # Panel anzeigen
        self.sweep_panel.reset()
        self.sweep_panel.show_at(self.viewport_3d)
        
        self.statusBar().showMessage("Sweep: Profil wählen")

    def _start_loft(self):
        """Startet den Loft-Modus."""
        self._loft_mode = True
        self._loft_profiles = []
        
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
            self.statusBar().showMessage("Wähle einen Body für Pattern")

    def _activate_pattern_for_body(self, body):
        """Aktiviert Pattern-Modus für einen Body."""
        self._pattern_mode = True
        self._pattern_target_body = body
        
        # Panel anzeigen
        self.pattern_panel.reset()
        self.pattern_panel.show_at(self.viewport_3d)
        
        self.statusBar().showMessage("Pattern: Parameter einstellen")

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
            self.statusBar().showMessage("Wähle einen Body für Textur")

    def _activate_texture_for_body(self, body):
        """Aktiviert Texture-Modus für einen Body."""
        self._texture_mode = True
        self._texture_target_body = body
        
        # Panel anzeigen
        self.texture_panel.reset()
        self.texture_panel.set_body(body)
        self.texture_panel.show_at(self.viewport_3d)
        
        self.statusBar().showMessage("Textur: Einstellungen wählen")
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def _show_not_implemented(self, feature: str):
        """Zeigt Hinweis für noch nicht implementierte Features"""
        logger.info(f"{feature} - Coming soon!")
    
    def _get_active_body(self):
        """Hilfsfunktion: Gibt den aktuell im Browser ausgewählten Body zurück"""
        if hasattr(self, 'browser'):
            selected = self.browser.get_selected_bodies()
            return selected[0] if selected else None
        return None
