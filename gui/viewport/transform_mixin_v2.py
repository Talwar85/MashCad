"""
MashCad - Transform Mixin V2 (Onshape-Style)
Integriert das einfache Gizmo in den Viewport
"""

from loguru import logger
from typing import Optional
import numpy as np

from .transform_gizmo_v2 import SimpleTransformController, GizmoAxis


class TransformMixinV2:
    """
    Mixin für Onshape-Style Transform im PyVistaViewport.
    
    Features:
    - Gizmo erscheint automatisch bei Body-Selektion
    - Direktes Drag ohne Bestätigung
    - Live-Preview während Drag
    """
    
    def _init_transform_system(self):
        """Initialisiert das Transform-System"""
        self._transform_ctrl = SimpleTransformController(self)
        self._transform_ctrl.set_callbacks(
            get_body_center=self._get_body_center_for_gizmo,
            apply_transform=self._apply_transform_from_gizmo,
            on_values_changed=self._on_transform_values_changed
        )
        self._transform_enabled = True
        logger.debug("Transform System V2 initialisiert")
        
    def show_transform_gizmo(self, body_id: str, force_refresh: bool = True):
        """Zeigt das Gizmo für einen Body
        
        Args:
            body_id: ID des Bodies
            force_refresh: Bei True wird Gizmo immer neu positioniert
        """
        if not hasattr(self, '_transform_ctrl'):
            self._init_transform_system()
        self._transform_ctrl.select_body(body_id, force_refresh)
        
    def hide_transform_gizmo(self):
        """Versteckt das Gizmo"""
        if hasattr(self, '_transform_ctrl'):
            self._transform_ctrl.deselect()
            
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
            
    def handle_transform_mouse_press(self, screen_pos) -> bool:
        """Verarbeitet Mausklick für Transform. Returns True wenn konsumiert."""
        if not hasattr(self, '_transform_ctrl'):
            return False
        return self._transform_ctrl.on_mouse_press(screen_pos)
        
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
        """Callback: Wendet Transform an (leitet an main_window weiter)"""
        if hasattr(self, 'body_transform_requested'):
            self.body_transform_requested.emit(body_id, mode, data)
            logger.debug(f"Transform Signal gesendet: {mode} auf {body_id}")
            
    def _on_transform_values_changed(self, x: float, y: float, z: float):
        """Callback: Live-Update der Transform-Werte während Drag"""
        if hasattr(self, 'transform_changed'):
            self.transform_changed.emit(x, y, z)
