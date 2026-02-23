"""
MashCAD Feature Dialogs Module
================================

Extracted from main_window.py (AR-005 EXTENDED).

This module contains feature-related dialog operations as a mixin class.
Maintains backward compatibility by being imported into MainWindow.

Usage:
    class MainWindow(FeatureDialogsMixin, QMainWindow):
        pass
"""

from typing import TYPE_CHECKING, Optional, List, Dict, Any, Tuple
import numpy as np
from loguru import logger

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

if TYPE_CHECKING:
    from modeling import Body, Document
    from gui.main_window import MainWindow


class FeatureDialogsMixin:
    """
    Mixin class containing feature-related dialog operations for MainWindow.
    
    This class provides:
    - Pattern operations
    - Shell operations
    - Texture operations
    - Sweep operations
    - Loft operations
    - Component operations
    - BREP cleanup operations
    - TNP operations
    
    All methods assume they are called within a MainWindow context
    and access MainWindow attributes via `self`.
    """
    
    # =========================================================================
    # Pattern Operations
    # =========================================================================
    
    def _create_pattern(self):
        """
        Startet den Pattern-Workflow.
        """
        from i18n import tr
        
        self._pattern_mode = True
        self._pending_pattern_mode = True
        self.viewport_3d.setCursor(Qt.CrossCursor)
        self.statusBar().showMessage(tr("Wähle Body für Pattern"))
        logger.info("Pattern: Klicke auf einen Body")

    def _get_body_center(self, body) -> tuple:
        """Berechnet das Zentrum eines Bodies aus Bounding Box."""
        if hasattr(body, '_build123d_solid') and body._build123d_solid:
            try:
                bbox = body._build123d_solid.bounding_box()
                return ((bbox.min.X + bbox.max.X) / 2,
                        (bbox.min.Y + bbox.max.Y) / 2,
                        (bbox.min.Z + bbox.max.Z) / 2)
            except Exception:
                pass
        
        mesh = self.viewport_3d.get_body_mesh(body.id)
        if mesh:
            center = mesh.center
            return (center[0], center[1], center[2])
        
        return (0, 0, 0)

    def _duplicate_body(self, body, new_name: str):
        """Erstellt eine Kopie eines Bodies mit transformiertem Solid."""
        from modeling import Body
        from modeling.cad_tessellator import CADTessellator
        
        new_body = Body(name=new_name, document=self.document)
        
        if hasattr(body, '_build123d_solid') and body._build123d_solid:
            from build123d import Location
            new_body._build123d_solid = body._build123d_solid.moved(Location((0, 0, 0)))
            CADTessellator.notify_body_changed()
        
        return new_body

    def _on_body_clicked_for_pattern(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body für Pattern angeklickt wird."""
        self._pending_pattern_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        
        body = self.document.find_body_by_id(body_id)
        if body:
            self._activate_pattern_for_body(body)

    def _activate_pattern_for_body(self, body):
        """Aktiviert Pattern-Modus für einen Body."""
        self._pattern_mode = True
        self._pattern_target_body = body
        self.pattern_panel.reset()
        self.pattern_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage("Pattern: Parameter einstellen")

    def _on_pattern_parameters_changed(self, params: dict):
        """Handler für Live-Preview wenn Parameter geändert werden."""
        self._update_pattern_preview(params)

    def _update_pattern_preview(self, params: dict):
        """Generiert/aktualisiert Pattern-Preview."""
        if not self._pattern_target_body:
            return
        # Preview handled by viewport

    def _clear_pattern_preview(self):
        """Entfernt Pattern-Preview."""
        if hasattr(self.viewport_3d, 'clear_pattern_preview'):
            self.viewport_3d.clear_pattern_preview()

    def _on_pattern_confirmed(self):
        """Handler wenn Pattern bestätigt wird."""
        if not self._pattern_target_body:
            return
        
        params = self.pattern_panel.get_parameters()
        self._execute_pattern(self._pattern_target_body, params)
        self._stop_pattern_mode()

    def _on_pattern_cancelled(self):
        """Handler wenn Pattern abgebrochen wird."""
        self._stop_pattern_mode()

    def _on_pattern_center_pick_requested(self):
        """Handler wenn User Custom Center auswählen will."""
        self._pattern_center_pick_mode = True
        self.viewport_3d.set_center_pick_mode(True)
        self.statusBar().showMessage("Klicke auf das gewünschte Zentrum")

    def _on_pattern_center_picked(self, point: tuple):
        """Handler wenn ein Zentrum-Punkt gepickt wurde."""
        self._pattern_center_pick_mode = False
        self.viewport_3d.set_center_pick_mode(False)
        self.pattern_panel.set_custom_center(point)
        self.statusBar().showMessage(f"Zentrum gesetzt auf ({point[0]:.1f}, {point[1]:.1f}, {point[2]:.1f})")

    def _execute_pattern(self, body, params: dict):
        """Führt Pattern aus und erstellt die Bodies."""
        from modeling import PatternFeature
        from gui.commands.feature_commands import AddFeatureCommand
        
        pattern_type = params.get('type', 'linear')
        count = params.get('count', 3)
        spacing = params.get('spacing', 10.0)
        
        feature = PatternFeature(
            pattern_type=pattern_type,
            count=count,
            spacing=spacing,
            **params
        )
        
        cmd = AddFeatureCommand(body, feature, self, description=f"Pattern {pattern_type}")
        self.undo_stack.push(cmd)
        
        self.browser.refresh()
        self._update_viewport_all()
        logger.success(f"Pattern erstellt: {count} Kopien")

    def _stop_pattern_mode(self):
        """Beendet den Pattern-Modus."""
        self._pattern_mode = False
        self._pattern_target_body = None
        self._pending_pattern_mode = False
        self._pattern_center_pick_mode = False
        self.pattern_panel.hide()
        self._clear_pattern_preview()
        self.statusBar().clearMessage()
    
    # =========================================================================
    # Shell Operations
    # =========================================================================
    
    def _on_body_clicked_for_shell(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body für Shell angeklickt wird."""
        self._pending_shell_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)

        body = self.document.find_body_by_id(body_id)
        if body:
            self._activate_shell_for_body(body)

    def _on_body_clicked_for_fillet(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body für Fillet/Chamfer angeklickt wird."""
        # Check which mode is pending
        if hasattr(self, '_pending_fillet_mode') and self._pending_fillet_mode:
            self._pending_fillet_mode = False
            mode = 'fillet'
        elif hasattr(self, '_pending_chamfer_mode') and self._pending_chamfer_mode:
            self._pending_chamfer_mode = False
            mode = 'chamfer'
        else:
            return  # No fillet/chamfer pending

        self.viewport_3d.setCursor(Qt.ArrowCursor)

        body = self.document.find_body_by_id(body_id)
        if body:
            # Import here to avoid circular import
            from gui.tool_operations import ToolMixin
            # Call the activate method - need to access it through self
            if hasattr(self, '_activate_fillet_chamfer_for_body'):
                self._activate_fillet_chamfer_for_body(body, mode)

    def _activate_shell_for_body(self, body):
        """Aktiviert Shell-Modus für einen Body."""
        from i18n import tr
        
        self._shell_mode = True
        self._shell_target_body = body
        self._shell_opening_faces = []
        self._shell_opening_face_shape_ids = []
        self._shell_opening_face_indices = []
        
        self.shell_panel.reset()
        self.shell_panel.show_at(self.viewport_3d)
        self.viewport_3d.set_shell_mode(True)
        
        self.statusBar().showMessage(tr("Shell: Wähle Öffnungs-Flächen"))
        logger.info(f"Shell-Modus für '{body.name}' - Flächen anklicken")

    def _on_face_selected_for_shell(self, face_id):
        """Handler wenn eine Fläche für Shell selektiert wird."""
        if not self._shell_mode:
            return
        # Toggle face selection
        if face_id in self._shell_opening_faces:
            self._shell_opening_faces.remove(face_id)
        else:
            self._shell_opening_faces.append(face_id)
        
        self.shell_panel.set_opening_count(len(self._shell_opening_faces))

    def _on_shell_confirmed(self):
        """Handler wenn Shell bestätigt wird."""
        if not self._shell_target_body:
            return
        
        from modeling import ShellFeature
        from gui.commands.feature_commands import AddFeatureCommand
        
        thickness = self.shell_panel.get_thickness()
        
        feature = ShellFeature(
            thickness=thickness,
            opening_faces=self._shell_opening_faces,
            opening_face_indices=self._shell_opening_face_indices
        )
        
        cmd = AddFeatureCommand(self._shell_target_body, feature, self, description="Shell")
        self.undo_stack.push(cmd)
        
        self.browser.refresh()
        self._update_viewport_all()
        logger.success(f"Shell mit {thickness}mm erstellt")
        
        self._stop_shell_mode()

    def _on_shell_thickness_changed(self, thickness: float):
        """Handler wenn Shell-Dicke geändert wird."""
        if hasattr(self.viewport_3d, 'update_shell_preview'):
            # Setze target body ID für Preview
            if hasattr(self.viewport_3d, '_shell_target_body_id'):
                self.viewport_3d._shell_target_body_id = self._shell_target_body.id if self._shell_target_body else None
            self.viewport_3d.update_shell_preview(thickness, self._shell_opening_faces)

    def _on_shell_cancelled(self):
        """Bricht die Shell-Operation ab."""
        self._stop_shell_mode()

    def _stop_shell_mode(self):
        """Beendet den Shell-Modus und räumt auf."""
        self._shell_mode = False
        self._shell_target_body = None
        self._shell_opening_faces = []
        self._shell_opening_face_shape_ids = []
        self._shell_opening_face_indices = []

        # Preview entfernen
        if hasattr(self.viewport_3d, 'clear_all_feature_previews'):
            self.viewport_3d.clear_all_feature_previews()

        self.viewport_3d.set_shell_mode(False)
        self.shell_panel.hide()
        self.statusBar().clearMessage()
    
    # =========================================================================
    # Texture Operations
    # =========================================================================
    
    def _on_body_clicked_for_texture(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body für Texture angeklickt wird."""
        self._pending_texture_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        
        body = self.document.find_body_by_id(body_id)
        if body:
            self._activate_texture_for_body(body)

    def _on_texture_face_selected(self, count: int):
        """Callback wenn Texture-Faces im Viewport selektiert werden."""
        if hasattr(self, 'texture_panel') and self.texture_panel.isVisible():
            self.texture_panel.set_selected_face_count(count)

    def _on_texture_applied(self, config: dict):
        """Handler wenn Textur angewendet wird."""
        if not self._texture_target_body:
            return
        
        from modeling import SurfaceTextureFeature
        from gui.commands.feature_commands import AddFeatureCommand
        
        feature = SurfaceTextureFeature(
            texture_type=config.get('type', 'knurl'),
            scale=config.get('scale', 1.0),
            depth=config.get('depth', 0.5),
            **config
        )
        
        cmd = AddFeatureCommand(self._texture_target_body, feature, self, description="Texture")
        self.undo_stack.push(cmd)
        
        self.browser.refresh()
        self._update_viewport_all()
        logger.success("Textur angewendet")
        
        self._stop_texture_mode()

    def _on_texture_preview_requested(self, config: dict):
        """Handler wenn Textur-Preview angefordert wird."""
        if self._texture_target_body:
            self._request_live_preview('texture', {'body': self._texture_target_body, **config})

    def _on_texture_cancelled(self):
        """Bricht die Textur-Operation ab."""
        self._stop_texture_mode()

    def _stop_texture_mode(self):
        """Beendet den Texture-Modus und räumt auf."""
        self._texture_mode = False
        self._texture_target_body = None
        self._pending_texture_mode = False
        self.texture_panel.hide()
        self.statusBar().clearMessage()
    
    # =========================================================================
    # Sweep Operations
    # =========================================================================
    
    def _on_face_selected_for_sweep(self, face_id):
        """Handler wenn eine Fläche für Sweep selektiert wird."""
        if not self._sweep_mode or self._sweep_phase != 'profile':
            return
        
        # Store profile data
        self._sweep_profile_data = {'face_id': face_id}
        self.sweep_panel.set_profile_selected(True)
        self._highlight_sweep_profile(self._sweep_profile_data)
        
        # Switch to path phase
        self._sweep_phase = 'path'
        self.statusBar().showMessage("Sweep: Pfad wählen")

    def _on_edge_selected_for_sweep(self, edges: list):
        """Handler wenn Kanten für Sweep-Pfad selektiert werden."""
        if not self._sweep_mode or self._sweep_phase != 'path':
            return
        
        # Store path data
        self._sweep_path_data = {'edges': edges}
        self.sweep_panel.set_path_selected(True)
        self._highlight_sweep_path(self._sweep_path_data)
        
        self.statusBar().showMessage("Sweep: Enter zum Bestätigen")

    def _on_sweep_confirmed(self):
        """Handler wenn Sweep bestätigt wird."""
        if not self._sweep_profile_data or not self._sweep_path_data:
            logger.warning("Sweep: Profil und Pfad erforderlich")
            return
        
        from modeling import SweepFeature
        from gui.commands.feature_commands import AddFeatureCommand
        
        body = self._get_active_body()
        if not body:
            body = self.document.new_body()
        
        feature = SweepFeature(
            profile=self._sweep_profile_data,
            path=self._sweep_path_data,
            operation=self.sweep_panel.get_operation()
        )
        
        cmd = AddFeatureCommand(body, feature, self, description="Sweep")
        self.undo_stack.push(cmd)
        
        self.browser.refresh()
        self._update_viewport_all()
        logger.success("Sweep erstellt")
        
        self._stop_sweep_mode()

    def _on_sweep_cancelled(self):
        """Bricht die Sweep-Operation ab."""
        self._stop_sweep_mode()

    def _on_sweep_profile_cleared(self):
        """Handler wenn Profil-Auswahl entfernt wird."""
        self._sweep_profile_data = None
        self._sweep_phase = 'profile'
        self._clear_sweep_highlight('profile')
        self.sweep_panel.set_profile_selected(False)

    def _on_sweep_path_cleared(self):
        """Handler wenn Pfad-Auswahl entfernt wird."""
        self._sweep_path_data = None
        self._sweep_phase = 'path' if self._sweep_profile_data else 'profile'
        self._clear_sweep_highlight('path')
        self.sweep_panel.set_path_selected(False)

    def _clear_sweep_highlight(self, element_type: str, render: bool = True):
        """Entfernt das Sweep-Highlight für Profil oder Pfad."""
        if hasattr(self.viewport_3d, 'clear_sweep_highlight'):
            self.viewport_3d.clear_sweep_highlight(element_type, render)

    def _highlight_sweep_profile(self, profile_data: dict):
        """Highlightet das ausgewählte Sweep-Profil im Viewport."""
        if hasattr(self.viewport_3d, 'highlight_sweep_profile'):
            self.viewport_3d.highlight_sweep_profile(profile_data)

    def _highlight_sweep_path(self, path_data: dict):
        """Highlightet den ausgewählten Sweep-Pfad im Viewport."""
        if hasattr(self.viewport_3d, 'highlight_sweep_path'):
            self.viewport_3d.highlight_sweep_path(path_data)

    def _on_sketch_path_clicked(self, sketch_id: str, geom_type: str, index: int):
        """Handler wenn Sketch-Element für Sweep-Pfad geklickt wird."""
        if not self._sweep_mode or self._sweep_phase != 'path':
            return
        
        # Store path data from sketch
        sketch = next((s for s in self.document.get_all_sketches() if s.id == sketch_id), None)
        if sketch:
            self._sweep_path_data = {
                'sketch_id': sketch_id,
                'geom_type': geom_type,
                'index': index
            }
            self.sweep_panel.set_path_selected(True)
            self._highlight_sweep_path(self._sweep_path_data)

    def _on_sweep_sketch_path_requested(self):
        """Handler wenn User Sketch-Pfad auswählen will."""
        from i18n import tr
        
        self.statusBar().showMessage(tr("Klicke auf Sketch-Element für Pfad"))
        # Viewport handles the actual picking

    def _stop_sweep_mode(self):
        """Beendet den Sweep-Modus und räumt auf."""
        self._sweep_mode = False
        self._sweep_phase = None
        self._sweep_profile_data = None
        self._sweep_path_data = None
        self._sweep_profile_shape_id = None
        self._sweep_profile_face_index = None
        self._sweep_profile_geometric_selector = None
        self.viewport_3d.set_sweep_mode(False)
        self.sweep_panel.hide()
        self._clear_sweep_highlight('profile', render=False)
        self._clear_sweep_highlight('path', render=False)
        self.statusBar().clearMessage()
    
    # =========================================================================
    # Loft Operations
    # =========================================================================
    
    def _on_loft_add_profile(self):
        """Handler wenn weiteres Loft-Profil hinzugefügt werden soll."""
        from i18n import tr
        
        self.statusBar().showMessage(tr("Wähle nächstes Profil"))
        # Viewport handles the actual picking

    def _on_face_selected_for_loft(self, face_id):
        """Handler wenn eine Fläche für Loft selektiert wird."""
        if not self._loft_mode:
            return
        
        # Add profile
        profile_data = {'face_id': face_id}
        self._loft_profiles.append(profile_data)
        
        # Update UI
        self.loft_panel.set_profile_count(len(self._loft_profiles))
        self._highlight_loft_profile(profile_data, len(self._loft_profiles) - 1)
        
        # Update preview if we have enough profiles
        if len(self._loft_profiles) >= 2:
            self._update_loft_preview()

    def _on_loft_confirmed(self):
        """Handler wenn Loft bestätigt wird."""
        if len(self._loft_profiles) < 2:
            logger.warning("Loft: Mindestens 2 Profile erforderlich")
            return
        
        from modeling import LoftFeature
        from gui.commands.feature_commands import AddFeatureCommand
        
        body = self._get_active_body()
        if not body:
            body = self.document.new_body()
        
        feature = LoftFeature(
            profiles=self._loft_profiles,
            operation=self.loft_panel.get_operation(),
            ruled=self.loft_panel.is_ruled()
        )
        
        cmd = AddFeatureCommand(body, feature, self, description="Loft")
        self.undo_stack.push(cmd)
        
        self.browser.refresh()
        self._update_viewport_all()
        logger.success("Loft erstellt")
        
        self._stop_loft_mode()

    def _on_loft_cancelled(self):
        """Bricht die Loft-Operation ab."""
        self._stop_loft_mode()

    def _stop_loft_mode(self):
        """Beendet den Loft-Modus und räumt auf."""
        self._loft_mode = False
        self._loft_profiles = []
        self.viewport_3d.set_loft_mode(False)
        self.loft_panel.hide()
        self._clear_loft_highlights()
        self._clear_loft_preview()
        self.statusBar().clearMessage()

    def _clear_loft_highlights(self):
        """Entfernt alle Loft-Profile-Highlights."""
        if hasattr(self.viewport_3d, 'clear_loft_highlights'):
            self.viewport_3d.clear_loft_highlights()

    def _clear_loft_preview(self):
        """Entfernt die Loft-Preview."""
        if hasattr(self.viewport_3d, 'clear_loft_preview'):
            self.viewport_3d.clear_loft_preview()

    def _highlight_loft_profile(self, profile_data: dict, profile_index: int):
        """Highlightet ein Loft-Profil im Viewport."""
        if hasattr(self.viewport_3d, 'highlight_loft_profile'):
            self.viewport_3d.highlight_loft_profile(profile_data, profile_index)

    def _update_loft_preview(self):
        """Zeigt eine Preview des Loft-Ergebnisses."""
        if hasattr(self.viewport_3d, 'update_loft_preview'):
            self.viewport_3d.update_loft_preview(self._loft_profiles)
    
    # =========================================================================
    # BREP Cleanup Operations
    # =========================================================================
    
    def _toggle_brep_cleanup(self):
        """Startet BREP Cleanup Modus."""
        from i18n import tr
        
        self._pending_brep_cleanup_mode = True
        self.viewport_3d.setCursor(Qt.CrossCursor)
        self.statusBar().showMessage(tr("Wähle Body für BREP Cleanup"))
        logger.info("BREP Cleanup: Klicke auf einen Body")

    def _on_body_clicked_for_brep_cleanup(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body angeklickt wird."""
        self._pending_brep_cleanup_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        
        body = self.document.find_body_by_id(body_id)
        if body:
            self._activate_brep_cleanup_for_body(body)

    def _activate_brep_cleanup_for_body(self, body):
        """Startet BREP Cleanup fuer einen Body."""
        from modeling.brep_face_analyzer import BRepFaceAnalyzer
        
        self._brep_cleanup_body = body
        
        # Analyze faces
        if body._build123d_solid:
            analyzer = BRepFaceAnalyzer()
            result = analyzer.analyze(body._build123d_solid)
            # Show results in panel
            logger.info(f"BREP Cleanup: {len(result.features)} Features erkannt")

    def _close_brep_cleanup(self):
        """Schliesst BREP Cleanup Modus."""
        self._brep_cleanup_body = None
        self._pending_brep_cleanup_mode = False

    def _on_brep_cleanup_feature_selected(self, feature_idx: int, additive: bool = False):
        """Feature im Panel ausgewaehlt."""
        pass

    def _on_brep_cleanup_merge(self):
        """Merge-Button geklickt."""
        logger.info("BREP Merge ausgeführt")

    def _on_brep_cleanup_merge_all(self):
        """Alle-Merge-Button geklickt."""
        logger.info("BREP Merge All ausgeführt")
    
    # =========================================================================
    # TNP Operations
    # =========================================================================
    
    def _on_tnp_body_pick_requested(self):
        """User hat den Pick-Button im TNP-Panel geklickt."""
        self._pending_tnp_pick_mode = True
        self.viewport_3d.setCursor(Qt.CrossCursor)
        self.statusBar().showMessage("Wähle Body für TNP-Analyse")

    def _on_body_clicked_for_tnp(self, body_id: str):
        """Body wurde im Viewport für TNP-Panel ausgewählt."""
        self._pending_tnp_pick_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        
        body = self.document.find_body_by_id(body_id)
        if body:
            self._update_tnp_stats(body)

    def _solid_signature_safe(self, body) -> dict:
        """Erzeugt einen Geometry-Fingerprint (volume, faces, edges) oder None."""
        try:
            if not body or not getattr(body, '_build123d_solid', None):
                return None
            solid = body._build123d_solid
            return {
                'volume': float(solid.volume),
                'faces': len(list(solid.faces())),
                'edges': len(list(solid.edges())),
            }
        except Exception:
            return None

    def _update_tnp_stats(self, body=None):
        """Aktualisiert TNP-Statistiken im Panel."""
        if not hasattr(self, 'tnp_stats_panel'):
            return
        
        if body:
            signature = self._solid_signature_safe(body)
            if signature:
                self.tnp_stats_panel.set_body_stats(
                    body.name,
                    signature['faces'],
                    signature['edges'],
                    signature['volume']
                )
    
    # =========================================================================
    # Component Operations
    # =========================================================================
    
    def _on_component_activated(self, component):
        """Handler wenn eine Component aktiviert wird."""
        logger.info(f"Component aktiviert: {component.name}")
        self.document.set_active_component(component)
        self.browser.refresh()
        self._update_viewport_all()

    def _on_component_created(self, parent_component, new_component):
        """Handler wenn eine neue Component erstellt wird."""
        logger.info(f"Component erstellt: {new_component.name}")
        self.browser.refresh()

    def _on_component_deleted(self, component):
        """Handler wenn eine Component gelöscht wird."""
        logger.info(f"Component gelöscht: {component.name}")
        self.browser.refresh()
        self._update_viewport_all()

    def _on_component_renamed(self, component, new_name):
        """Handler wenn eine Component umbenannt wird."""
        logger.info(f"Component umbenannt: {new_name}")
        self.browser.refresh()

    def _on_component_vis_changed(self, component_id: str, visible: bool):
        """Handler wenn Component-Sichtbarkeit geändert wird."""
        self._trigger_viewport_update()

    def _on_body_moved_to_component(self, body, source_comp, target_comp):
        """Handler wenn ein Body zwischen Components verschoben wird."""
        logger.info(f"Body '{body.name}' verschoben")
        self.browser.refresh()

    def _on_sketch_moved_to_component(self, sketch, source_comp, target_comp):
        """Handler wenn ein Sketch zwischen Components verschoben wird."""
        logger.info(f"Sketch '{sketch.name}' verschoben")
        self.browser.refresh()
    
    # =========================================================================
    # Transform Operations
    # =========================================================================
    
    def _move_body(self):
        """Startet Move-Modus für ausgewählten Body."""
        body = self._get_active_body()
        if body:
            self._show_transform_ui(body.id, body.name, 'move')

    def _scale_body(self):
        """Startet Scale-Modus für ausgewählten Body."""
        body = self._get_active_body()
        if body:
            self._show_transform_ui(body.id, body.name, 'scale')

    def _rotate_body(self):
        """Startet Rotate-Modus für ausgewählten Body."""
        body = self._get_active_body()
        if body:
            self._show_transform_ui(body.id, body.name, 'rotate')

    def _copy_body(self):
        """Kopiert den aktiven Body als neuen Body."""
        body = self._get_active_body()
        if not body:
            return
        
        from modeling import Body
        from modeling.cad_tessellator import CADTessellator
        
        new_body = Body(name=f"{body.name}_copy", document=self.document)
        
        if hasattr(body, '_build123d_solid') and body._build123d_solid:
            from build123d import Location
            new_body._build123d_solid = body._build123d_solid.moved(Location((0, 0, 0)))
            CADTessellator.notify_body_changed()
            self._update_body_from_build123d(new_body, new_body._build123d_solid)
        
        self.document.add_body(new_body)
        self.browser.refresh()
        self._update_viewport_all()
        logger.success(f"Body kopiert: {new_body.name}")

    def _mirror_body(self):
        """Startet Mirror-Dialog für ausgewählten Body."""
        body = self._get_active_body()
        if body:
            self._show_mirror_dialog(body.id)
    
    # =========================================================================
    # Copy Operations
    # =========================================================================
    
    def _on_body_copy_requested(self, body_id: str, mode: str, data):
        """
        Handler für Copy+Transform (Shift+Drag).
        Kopiert den Body und wendet dann den Transform an.
        """
        logger.debug(f"Copy requested: {mode} on {body_id}")
        logger.debug(f"   data: {data}")
        
        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.error(f"Body {body_id} nicht gefunden für Copy")
            return
        
        try:
            from build123d import Location, Axis
            from modeling.cad_tessellator import CADTessellator
            from modeling import Body
            
            new_body = Body(name=f"{body.name}_copy", document=self.document)
            
            if hasattr(body, '_build123d_solid') and body._build123d_solid:
                new_body._build123d_solid = body._build123d_solid.moved(Location((0, 0, 0)))
                CADTessellator.notify_body_changed()
                
                if mode == "move":
                    if isinstance(data, list):
                        dx, dy, dz = data
                    else:
                        dx, dy, dz = data.get("translation", [0, 0, 0])
                    new_body._build123d_solid = new_body._build123d_solid.moved(Location((dx, dy, dz)))
                    logger.success(f"Copy+Move ({dx:.2f}, {dy:.2f}, {dz:.2f}) → {new_body.name}")
                    
                elif mode == "rotate":
                    if isinstance(data, dict):
                        axis_name = data.get("axis", "Z")
                        angle = data.get("angle", 0)
                    else:
                        axis_name, angle = "Z", 0
                    axis_map = {"X": Axis.X, "Y": Axis.Y, "Z": Axis.Z}
                    axis = axis_map.get(axis_name, Axis.Z)
                    new_body._build123d_solid = new_body._build123d_solid.rotated(axis, angle)
                    logger.success(f"Copy+Rotate ({axis_name}, {angle:.1f}°) → {new_body.name}")
                    
                elif mode == "scale":
                    if isinstance(data, dict):
                        factor = data.get("factor", 1.0)
                    else:
                        factor = 1.0
                    new_body._build123d_solid = new_body._build123d_solid.scaled(factor)
                    logger.success(f"Copy+Scale ({factor:.2f}) → {new_body.name}")
                
                self._update_body_from_build123d(new_body, new_body._build123d_solid)
                self.document.add_body(new_body, set_active=False)
                self.browser.refresh()
                
                if hasattr(self.viewport_3d, 'show_transform_gizmo'):
                    self.viewport_3d.show_transform_gizmo(new_body.id)
                    
        except Exception as e:
            logger.exception(f"Copy+Transform Error: {e}")
    
    def _on_body_mirror_requested(self, body_id: str, plane: str):
        """Handler für Mirror-Operation."""
        logger.debug(f"Mirror requested: {plane} auf {body_id}")
        
        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.error(f"Body {body_id} nicht gefunden für Mirror")
            return
        
        try:
            from build123d import Plane as B123Plane, mirror as b123d_mirror
            from modeling.cad_tessellator import CADTessellator
            
            if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
                logger.error("Build123d nicht verfügbar für Mirror")
                return
            
            CADTessellator.notify_body_changed()
            
            plane_map = {"XY": B123Plane.XY, "XZ": B123Plane.XZ, "YZ": B123Plane.YZ}
            mirror_plane = plane_map.get(plane.upper(), B123Plane.XY)
            
            body._build123d_solid = b123d_mirror(body._build123d_solid, about=mirror_plane)
            logger.success(f"Mirror ({plane}) auf {body.name}")
            
            self._update_body_from_build123d(body, body._build123d_solid)
            
            if hasattr(self.viewport_3d, 'show_transform_gizmo'):
                self.viewport_3d.show_transform_gizmo(body_id)
            self.browser.refresh()
            
        except Exception as e:
            logger.exception(f"Mirror Error: {e}")
    
    # =========================================================================
    # Body Operations
    # =========================================================================
    
    def _on_background_clicked(self):
        """Handler for background click in Viewport -> Deselect Body"""
        if hasattr(self.viewport_3d, 'clear_selection'):
            self.viewport_3d.clear_selection()

    def _on_create_sketch_requested(self, face_id: int):
        """Handler for Context Menu -> Create Sketch"""
        # Create sketch on clicked face
        logger.info(f"Create Sketch on face {face_id}")

    def _on_batch_retry_rebuild(self, problem_features):
        """Handler für Batch-Rebuild von Problem-Features."""
        logger.info(f"Batch Rebuild: {len(problem_features)} Features")
        for feature, body in problem_features:
            try:
                feature._rebuild(body)
                logger.success(f"Feature '{feature.name}' neu erstellt")
            except Exception as e:
                logger.error(f"Rebuild fehlgeschlagen: {e}")
        
        self.browser.refresh()
        self._update_viewport_all()

    def _on_batch_open_diagnostics(self, problem_features):
        """Handler für Batch-Diagnostics."""
        logger.info(f"Diagnostics für {len(problem_features)} Features")

    def _on_batch_isolate_bodies(self, bodies):
        """Handler für Body-Isolation."""
        # Hide all bodies except selected
        for body in self.document.get_all_bodies():
            visible = body in bodies
            self.viewport_3d.set_body_visible(body.id, visible)
        self._trigger_viewport_update()

    def _on_batch_unhide_bodies(self, bodies):
        """Handler für Batch-Unhide."""
        for body in bodies:
            self.viewport_3d.set_body_visible(body.id, True)
        self._trigger_viewport_update()

    def _on_batch_focus_features(self, feature_body_pairs):
        """Handler für Feature-Focus."""
        logger.info(f"Focus auf {len(feature_body_pairs)} Features")

    def _on_recovery_action_requested(self, action, feature):
        """Handler für Recovery-Actions."""
        logger.info(f"Recovery action '{action}' für Feature '{feature.name}'")

    def _on_edit_feature_requested(self, feature):
        """Handler für Edit Feature Request."""
        body = self._get_active_body()
        if body:
            self._edit_parametric_feature(feature, body, 'unknown')

    def _on_rebuild_feature_requested(self, feature):
        """Handler für Rebuild Feature Request."""
        body = self._get_active_body()
        if body and hasattr(feature, '_rebuild'):
            try:
                feature._rebuild(body)
                self._update_body_from_build123d(body, body._build123d_solid)
                self.browser.refresh()
                self._update_viewport_all()
                logger.success(f"Feature '{feature.name}' neu erstellt")
            except Exception as e:
                logger.error(f"Rebuild fehlgeschlagen: {e}")

    def _on_delete_feature_requested(self, feature):
        """Handler für Delete Feature Request."""
        body = self._get_active_body()
        if body:
            self._on_feature_deleted(feature, body)

    def _on_highlight_edges_requested(self, edge_indices):
        """Handler für Edge-Highlight."""
        if hasattr(self.viewport_3d, 'highlight_edges'):
            self.viewport_3d.highlight_edges(edge_indices)

    def _on_projection_preview_requested(self, edge_tuple, projection_type):
        """Handler für Projection-Preview."""
        if hasattr(self.viewport_3d, 'show_projection_preview'):
            self.viewport_3d.show_projection_preview(edge_tuple, projection_type)

    def _on_projection_preview_cleared(self):
        """Handler wenn Projection-Preview gelöscht wird."""
        if hasattr(self.viewport_3d, 'clear_projection_preview'):
            self.viewport_3d.clear_projection_preview()
    
    # =========================================================================
    # Viewport Body Click Handler
    # =========================================================================
    
    def _on_viewport_body_clicked(self, body_id: str):
        """
        Handler für Body-Klick im Viewport.
        Unterstützt verschiedene Pending-Modi.
        """
        from PySide6.QtCore import Qt
        from i18n import tr
        
        # Prüfe auf verschiedene Pending-Modi
        if getattr(self, '_pending_split_mode', False):
            self._pending_split_mode = False
            self.viewport_3d.setCursor(Qt.ArrowCursor)
            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(False)
            self._on_split_body_clicked(body_id)
            return

        if getattr(self, '_pending_fillet_mode', False):
            self._on_body_clicked_for_fillet(body_id)
            return

        if getattr(self, '_pending_thread_mode', False):
            self._on_body_clicked_for_thread(body_id)
            return

        if getattr(self, '_pending_brep_cleanup_mode', False):
            self._on_body_clicked_for_brep_cleanup(body_id)
            return

        if getattr(self, '_pending_shell_mode', False):
            self._on_body_clicked_for_shell(body_id)
            return

        if getattr(self, '_pending_texture_mode', False):
            self._on_body_clicked_for_texture(body_id)
            return

        if getattr(self, '_pending_mesh_convert_mode', False):
            self._on_body_clicked_for_mesh_convert(body_id)
            return

        if getattr(self, '_pending_pattern_mode', False):
            self._on_body_clicked_for_pattern(body_id)
            return

        if getattr(self, '_pending_lattice_mode', False):
            self._on_body_clicked_for_lattice(body_id)
            return

        if getattr(self, '_pending_nsided_patch_mode', False):
            self._on_body_clicked_for_nsided_patch(body_id)
            return

        if getattr(self, '_pending_wall_thickness_mode', False):
            self._on_body_clicked_for_wall_thickness(body_id)
            return

        if getattr(self, '_pending_tnp_pick_mode', False):
            self._on_body_clicked_for_tnp(body_id)
            return

        # Transform Pending Mode
        if not getattr(self, '_pending_transform_mode', None):
            return

        body = self.document.find_body_by_id(body_id)
        if not body:
            logger.warning(f"Body {body_id} nicht gefunden")
            return

        mode = self._pending_transform_mode
        self._pending_transform_mode = None
        self.viewport_3d.setCursor(Qt.ArrowCursor)

        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        # Point-to-Point Move
        if mode == "point_to_point":
            if hasattr(self.viewport_3d, 'start_point_to_point_mode'):
                self.viewport_3d.start_point_to_point_mode(body.id)
                logger.success(f"Point-to-Point Move für {body.name}: Wähle Start-Punkt, dann Ziel-Punkt")
                if hasattr(self, "p2p_panel"):
                    self._p2p_body_id = body.id
                    self.p2p_panel.reset()
                    self.p2p_panel.set_body(body.name)
                    self.p2p_panel.set_status(tr("Pick start point"))
                    self.p2p_panel.show_at(self.viewport_3d)
                self._p2p_repick_body = False
            return

        # Normaler Transform-Modus
        self._transform_mode = mode
        self._active_transform_body = body
        self._show_transform_ui(body.id, body.name, mode)
        logger.success(f"{mode.capitalize()}: {body.name} - Ziehe am Gizmo oder Tab für Eingabe")
    
    # =========================================================================
    # Selection Mode
    # =========================================================================
    
    def set_selection_mode(self, mode):
        """Setzt den Selection-Modus."""
        from gui.geometry_detector import GeometryDetector
        
        if hasattr(self.viewport_3d, 'set_selection_mode'):
            self.viewport_3d.set_selection_mode(mode)


# =============================================================================
# Backward Compatibility Exports
# =============================================================================

__all__ = [
    'FeatureDialogsMixin',
]
