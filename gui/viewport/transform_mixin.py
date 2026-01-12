"""
MashCad - Viewport Transform Mixin
Integriert das neue TransformGizmo-System in den Viewport
"""

import numpy as np
from loguru import logger
from PySide6.QtCore import Signal

from .transform_controller import TransformController


class TransformMixin:
    """
    Mixin für Transform-Operationen im Viewport.
    
    Verwendet das neue TransformGizmo-System für professionelle
    Move/Rotate/Scale Operationen.
    """
    
    # Signals (werden in viewport_pyvista.py definiert)
    # transform_changed = Signal(float, float, float)
    
    def _init_transform_system(self):
        """Initialisiert das Transform-System. Aufrufen in __init__"""
        self._transform_controller = TransformController(self)
        
        # Callbacks setzen
        self._transform_controller.set_callbacks(
            get_center=self._get_body_center,
            get_mesh=self._get_body_mesh_for_transform,
            apply_transform=self._apply_body_transform
        )
        
        # Signals verbinden
        self._transform_controller.transform_updated.connect(self._on_transform_updated)
        
    def start_transform(self, body_id: str, mode: str):
        """
        Startet eine Transform-Operation.
        
        Args:
            body_id: ID des Bodies
            mode: "move", "rotate" oder "scale"
        """
        if not hasattr(self, '_transform_controller'):
            self._init_transform_system()
            
        self._transform_controller.start_transform(body_id, mode)
        
    def end_transform(self):
        """Beendet/Bricht die aktuelle Transform-Operation ab"""
        if hasattr(self, '_transform_controller'):
            self._transform_controller.cancel_transform()
            
    def apply_transform_values(self, x: float, y: float, z: float, mode: str):
        """
        Setzt Transform-Werte direkt (z.B. aus Input-Panel).
        
        Args:
            x, y, z: Die Werte (Translation/Rotation/Scale je nach Mode)
            mode: "move", "rotate" oder "scale"
        """
        if hasattr(self, '_transform_controller') and self._transform_controller.state:
            self._transform_controller.set_values(x, y, z)
            
    def confirm_transform(self) -> bool:
        """
        Bestätigt die aktuelle Transformation.
        
        Returns:
            True wenn erfolgreich
        """
        if hasattr(self, '_transform_controller'):
            return self._transform_controller.apply_transform()
        return False
        
    def _handle_transform_mouse_press(self, event) -> bool:
        """
        Verarbeitet Mausklick für Transform.
        
        Returns:
            True wenn das Event vom Transform-System konsumiert wurde
        """
        if not hasattr(self, '_transform_controller'):
            return False
            
        if self._transform_controller.state:
            pos = event.position() if hasattr(event, 'position') else event.pos()
            screen_pos = (int(pos.x()), int(pos.y()))
            return self._transform_controller.on_mouse_press(screen_pos, 1)  # Linksklick
            
        return False
        
    def _handle_transform_mouse_move(self, event) -> bool:
        """
        Verarbeitet Mausbewegung für Transform.
        
        Returns:
            True wenn das Event vom Transform-System konsumiert wurde
        """
        if not hasattr(self, '_transform_controller'):
            return False
            
        if self._transform_controller.state:
            pos = event.position() if hasattr(event, 'position') else event.pos()
            screen_pos = (int(pos.x()), int(pos.y()))
            return self._transform_controller.on_mouse_move(screen_pos)
            
        return False
        
    def _handle_transform_mouse_release(self, event) -> bool:
        """
        Verarbeitet Maus-Loslassen für Transform.
        
        Returns:
            True wenn das Event vom Transform-System konsumiert wurde
        """
        if not hasattr(self, '_transform_controller'):
            return False
            
        if self._transform_controller.state:
            pos = event.position() if hasattr(event, 'position') else event.pos()
            screen_pos = (int(pos.x()), int(pos.y()))
            return self._transform_controller.on_mouse_release(screen_pos, 1)
            
        return False
        
    # ==================== CALLBACKS ====================
    
    def _get_body_center(self, body_id: str) -> np.ndarray:
        """Gibt das Zentrum eines Bodies zurück"""
        try:
            if body_id in self._body_actors:
                actors = self._body_actors[body_id]
                if actors:
                    mesh_name = actors[0]
                    actor = self.plotter.renderer.actors.get(mesh_name)
                    if actor:
                        bounds = actor.GetBounds()
                        center = np.array([
                            (bounds[0] + bounds[1]) / 2,
                            (bounds[2] + bounds[3]) / 2,
                            (bounds[4] + bounds[5]) / 2
                        ])
                        return center
        except Exception as e:
            logger.warning(f"Konnte Body-Zentrum nicht ermitteln: {e}")
            
        return np.array([0.0, 0.0, 0.0])
        
    def _get_body_mesh_for_transform(self, body_id: str):
        """Gibt das Mesh eines Bodies für die Preview zurück"""
        try:
            if body_id in self._body_actors:
                actors = self._body_actors[body_id]
                if actors:
                    mesh_name = actors[0]
                    actor = self.plotter.renderer.actors.get(mesh_name)
                    if actor:
                        mapper = actor.GetMapper()
                        if mapper:
                            return mapper.GetInput()
        except Exception as e:
            logger.warning(f"Konnte Body-Mesh nicht holen: {e}")
            
        return None
        
    def _apply_body_transform(self, body_id: str, transform_data: dict) -> bool:
        """
        Wendet eine Transformation auf einen Body an.
        
        Args:
            body_id: ID des Bodies
            transform_data: Dict mit type, translation/rotation/scale, pivot
            
        Returns:
            True wenn erfolgreich
        """
        try:
            transform_type = transform_data.get("type")
            
            if transform_type == "move":
                translation = transform_data.get("translation", [0, 0, 0])
                return self._apply_move(body_id, translation)
                
            elif transform_type == "rotate":
                rotation = transform_data.get("rotation", [0, 0, 0])
                pivot = transform_data.get("pivot", [0, 0, 0])
                return self._apply_rotation(body_id, rotation, pivot)
                
            elif transform_type == "scale":
                scale = transform_data.get("scale", [1, 1, 1])
                pivot = transform_data.get("pivot", [0, 0, 0])
                return self._apply_scale(body_id, scale, pivot)
                
        except Exception as e:
            logger.error(f"Transform fehlgeschlagen: {e}")
            
        return False
        
    def _apply_move(self, body_id: str, translation: list) -> bool:
        """Wendet eine Verschiebung an"""
        # Hier muss der Body im Modell transformiert werden
        # Das sollte über main_window gehen
        if hasattr(self, 'body_transform_requested'):
            self.body_transform_requested.emit(body_id, "move", translation)
            return True
        return False
        
    def _apply_rotation(self, body_id: str, rotation: list, pivot: list) -> bool:
        """Wendet eine Rotation an"""
        if hasattr(self, 'body_transform_requested'):
            self.body_transform_requested.emit(body_id, "rotate", {"rotation": rotation, "pivot": pivot})
            return True
        return False
        
    def _apply_scale(self, body_id: str, scale: list, pivot: list) -> bool:
        """Wendet eine Skalierung an"""
        if hasattr(self, 'body_transform_requested'):
            self.body_transform_requested.emit(body_id, "scale", {"scale": scale, "pivot": pivot})
            return True
        return False
        
    def _on_transform_updated(self, x: float, y: float, z: float):
        """Callback wenn sich Transform-Werte ändern"""
        if hasattr(self, 'transform_changed'):
            self.transform_changed.emit(x, y, z)


    def get_current_transform_matrix(self):
        """Gibt die aktuelle Matrix des transformierten Objekts zurück"""
        if self.transform_actor:
            vtk_mat = self.transform_actor.GetMatrix()
            mat = []
            for i in range(4):
                row = []
                for j in range(4):
                    row.append(vtk_mat.GetElement(i, j))
                mat.append(row)
            return mat
        return None
        
    def select_body_at(self, x, y):
        """Picking Logik für Bodies"""
        if not HAS_VTK:
            return None
            
        picker = vtk.vtkCellPicker()
        picker.Pick(x, self.plotter.interactor.height() - y, 0, self.plotter.renderer)
        actor = picker.GetActor()
        
        if actor:
            for bid, actors in self._body_actors.items():
                for name in actors:
                    if self.plotter.renderer.actors.get(name) == actor:
                        return bid
        return None

    def highlight_edge(self, p1, p2):
        """Zeichnet eine rote Linie (für Fillet/Chamfer Vorschau)"""
        import uuid
        import pyvista as pv
        
        line = pv.Line(p1, p2)
        name = f"highlight_{uuid.uuid4()}"
        self.plotter.add_mesh(line, color='red', line_width=5, name=name)

    def clear_highlight(self):
        """Entfernt alle Highlight-Linien"""
        to_remove = [
            name for name in self.plotter.renderer.actors.keys() 
            if name.startswith("highlight_")
        ]
        
        for name in to_remove:
            self.plotter.remove_actor(name)
            
        self.plotter.render()
