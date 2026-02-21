"""
MashCad - Transform Mixin V3 (Full Feature)
Integriert das erweiterte Gizmo-System mit Move/Rotate/Scale/Copy/Mirror
"""

from loguru import logger
from typing import Optional
import numpy as np

from .transform_gizmo_v3 import FullTransformController, TransformMode, GizmoAxis


class TransformMixinV3:
    """
    Mixin für vollständiges Transform-System im PyVistaViewport.
    
    Features:
    - Move/Rotate/Scale via Gizmo
    - Keyboard Shortcuts: G=Move, R=Rotate, S=Scale, M=Mirror
    - Shift+Drag = Copy+Transform
    - Live-Preview während Drag
    """
    
    def _init_transform_system_v3(self):
        """Initialisiert das erweiterte Transform-System"""
        self._transform_ctrl = FullTransformController(self)
        self._transform_ctrl.set_callbacks(
            get_body_center=self._get_body_center_for_gizmo,
            apply_transform=self._apply_transform_from_gizmo,
            copy_body=self._copy_body_from_gizmo,
            mirror_body=self._mirror_body_from_gizmo,
            on_values_changed=self._on_transform_values_changed
        )
        self._transform_enabled = True
        logger.debug("Transform System V3 initialisiert")
        
    def show_transform_gizmo(self, body_id: str, force_refresh: bool = True):
        """Zeigt das Gizmo für einen Body"""
        if not hasattr(self, '_transform_ctrl'):
            self._init_transform_system_v3()
        self._transform_ctrl.select_body(body_id, force_refresh)
        
    def hide_transform_gizmo(self):
        """Versteckt das Gizmo"""
        if hasattr(self, '_transform_ctrl'):
            self._transform_ctrl.deselect()

    def update_transform_gizmo_position(self):
        """Aktualisiert die Gizmo-Position für den aktuell selektierten Body."""
        if hasattr(self, '_transform_ctrl') and self._transform_ctrl.selected_body_id:
            self._transform_ctrl.select_body(self._transform_ctrl.selected_body_id, force_refresh=True)
            
    def set_transform_mode(self, mode: str):
        """Setzt den Transform-Modus
        
        Args:
            mode: 'move', 'rotate', oder 'scale'
        """
        if not hasattr(self, '_transform_ctrl'):
            return
            
        mode_map = {
            'move': TransformMode.MOVE,
            'rotate': TransformMode.ROTATE,
            'scale': TransformMode.SCALE,
        }
        
        if mode.lower() in mode_map:
            self._transform_ctrl.set_mode(mode_map[mode.lower()])
            
    def is_transform_active(self) -> bool:
        """Prüft ob Gizmo sichtbar ist"""
        if hasattr(self, '_transform_ctrl'):
            return self._transform_ctrl.gizmo.visible
        return False
        
    def is_transform_dragging(self) -> bool:
        """Prüft ob gerade ein Transform-Drag läuft"""
        if hasattr(self, '_transform_ctrl'):
            return self._transform_ctrl.is_dragging
        return False
        
    def get_transform_mode(self) -> Optional[str]:
        """Gibt den aktuellen Transform-Modus zurück"""
        if hasattr(self, '_transform_ctrl'):
            mode = self._transform_ctrl.gizmo.mode
            return mode.name.lower()
        return None
            
    # ==================== EVENT HANDLER ====================
    
    def handle_transform_mouse_press(self, screen_pos, shift_pressed: bool = False) -> bool:
        """Verarbeitet Mausklick für Transform. Returns True wenn konsumiert."""
        if not hasattr(self, '_transform_ctrl'):
            return False
        return self._transform_ctrl.on_mouse_press(screen_pos, shift_pressed)
        
    def handle_transform_mouse_move(self, screen_pos) -> bool:
        """Verarbeitet Mausbewegung für Transform. Returns True wenn konsumiert."""
        if not hasattr(self, '_transform_ctrl'):
            return False
        return self._transform_ctrl.on_mouse_move(screen_pos)
        
    def handle_transform_mouse_release(self, screen_pos) -> bool:
        """Verarbeitet Maus-Loslassen für Transform. Returns True wenn konsumiert."""
        if not hasattr(self, '_transform_ctrl'):
            return False
        return self._transform_ctrl.on_mouse_release(screen_pos)
        
    def handle_transform_key(self, key: str) -> bool:
        """Verarbeitet Tastendruck für Transform-Modus
        
        Args:
            key: 'g'=Move, 'r'=Rotate, 's'=Scale, 'm'=Mirror-Dialog
            
        Returns:
            True wenn Taste konsumiert wurde
        """
        if not hasattr(self, '_transform_ctrl'):
            return False
            
        if not self._transform_ctrl.gizmo.visible:
            return False
            
        key_lower = key.lower()
        
        if key_lower == 'g':
            self._transform_ctrl.set_mode(TransformMode.MOVE)
            return True
        elif key_lower == 'r':
            self._transform_ctrl.set_mode(TransformMode.ROTATE)
            return True
        elif key_lower == 's':
            self._transform_ctrl.set_mode(TransformMode.SCALE)
            return True
        elif key_lower == 'm':
            # Mirror-Dialog öffnen
            self._show_mirror_dialog()
            return True
            
        return False
        
    def _show_mirror_dialog(self):
        """Zeigt Dialog für Mirror-Ebenenauswahl"""
        # Wird von main_window implementiert
        if hasattr(self, 'mirror_requested'):
            body_id = self._transform_ctrl.selected_body_id
            if body_id:
                self.mirror_requested.emit(body_id)
                
    # ==================== CALLBACKS ====================
    
    def _get_body_center_for_gizmo(self, body_id: str) -> Optional[np.ndarray]:
        """Callback: Gibt das Zentrum eines Bodies zurück"""
        try:
            if body_id in self._body_actors:
                actors = self._body_actors[body_id]
                if actors:
                    actor_name = actors[0]
                    actor = self.plotter.renderer.actors.get(actor_name)
                    if actor:
                        bounds = actor.GetBounds()
                        center = np.array([
                            (bounds[0] + bounds[1]) / 2,
                            (bounds[2] + bounds[3]) / 2,
                            (bounds[4] + bounds[5]) / 2
                        ])
                        return center
        except Exception as e:
            logger.warning(f"Body-Zentrum Fehler: {e}")
        return None
        
    def _apply_transform_from_gizmo(self, body_id: str, mode: str, data):
        """Callback: Wendet Transform an"""
        logger.info(f"🎯 _apply_transform_from_gizmo CALLED")
        logger.info(f"   body_id: {body_id}")
        logger.info(f"   mode: {mode}")
        logger.info(f"   data: {data}")

        if hasattr(self, 'body_transform_requested'):
            self.body_transform_requested.emit(body_id, mode, data)
            logger.info(f"✅ Transform Signal EMITTED: {mode} auf {body_id}")
        else:
            logger.error(f"❌ body_transform_requested Signal NICHT VERFÜGBAR!")
            
    def _copy_body_from_gizmo(self, body_id: str, mode: str, data):
        """Callback: Kopiert Body und wendet Transform an"""
        # FIX Bug 1.5: Signal direkt emittieren (hasattr kann bei Qt Signals fehlschlagen)
        try:
            logger.info(f"🚀 _copy_body_from_gizmo CALLED - Emitting signal")
            logger.info(f"   body_id: {body_id}")
            logger.info(f"   mode: {mode}")
            logger.info(f"   data: {data}")
            self.body_copy_requested.emit(body_id, mode, data)
            logger.info(f"✅ Copy+Transform Signal EMITTED: {mode} auf {body_id}")
        except AttributeError as e:
            logger.error(f"❌ body_copy_requested Signal nicht verfügbar: {e}")
            
    def _mirror_body_from_gizmo(self, body_id: str, plane: str):
        """Callback: Spiegelt Body"""
        if hasattr(self, 'body_mirror_requested'):
            self.body_mirror_requested.emit(body_id, plane)
            logger.debug(f"Mirror Signal: {plane} auf {body_id}")
        else:
            logger.warning("body_mirror_requested Signal nicht verfügbar")
            
    def _on_transform_values_changed(self, x: float, y: float, z: float):
        """Callback: Live-Update der Transform-Werte während Drag"""
        if hasattr(self, 'transform_changed'):
            self.transform_changed.emit(x, y, z)

    def update_transform_preview(self, x: float, y: float, z: float):
        """Aktualisiert die Gizmo-Vorschau mit neuen Werten vom Transform-Panel.

        Wird aufgerufen wenn der User Werte im Transform-Panel ändert,
        damit das Gizmo die Vorschau live aktualisiert.
        """
        if not hasattr(self, '_transform_ctrl'):
            return
        try:
            self._transform_ctrl.set_preview_values(x, y, z)
        except AttributeError:
            # Fallback: Gizmo-Controller hat kein set_preview_values
            logger.debug("Transform preview: set_preview_values nicht verfügbar")

    def apply_transform(self):
        """Finalisiert die aktuelle Transform-Operation.

        Wird aufgerufen wenn der User den Transform bestätigt (Enter/OK).
        Wendet die Transformation final an und räumt den Gizmo-State auf.
        """
        if not hasattr(self, '_transform_ctrl'):
            return
        try:
            body_id = self._transform_ctrl.selected_body_id
            if body_id and hasattr(self._transform_ctrl, 'finalize'):
                self._transform_ctrl.finalize()
            elif body_id:
                # Fallback: Gizmo-Position aktualisieren
                self.update_transform_gizmo_position()
        except Exception as e:
            logger.debug(f"Transform apply fehlgeschlagen: {e}")

    def cancel_transform(self):
        """Bricht die aktuelle Transform-Operation ab.

        Stellt den Originalzustand wieder her und versteckt das Gizmo.
        """
        if not hasattr(self, '_transform_ctrl'):
            return
        try:
            if hasattr(self._transform_ctrl, 'cancel'):
                self._transform_ctrl.cancel()
            else:
                self._transform_ctrl.deselect()
            self.render()
        except Exception as e:
            logger.debug(f"Transform cancel fehlgeschlagen: {e}")
