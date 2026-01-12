"""
MashCad - Transform Gizmo V2 (Onshape-Style)
Einfaches, direktes Gizmo das sofort bei Body-Selektion erscheint
"""

import numpy as np
from typing import Optional, Tuple, List
from enum import Enum, auto
from dataclasses import dataclass
from loguru import logger

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False
    pv = None

try:
    import vtk
    HAS_VTK = True
except ImportError:
    HAS_VTK = False
    vtk = None


class GizmoAxis(Enum):
    """Aktive Achse für Transformation"""
    NONE = auto()
    X = auto()
    Y = auto()
    Z = auto()


# Farben
COLORS = {
    GizmoAxis.X: "#E63946",      # Rot
    GizmoAxis.Y: "#2A9D8F",      # Grün/Teal  
    GizmoAxis.Z: "#457B9D",      # Blau
    "hover": "#FFD700",          # Gold bei Hover
    "center": "#FFFFFF",         # Weiß für Zentrum
}


class SimpleTransformGizmo:
    """
    Einfaches Transform-Gizmo im Onshape-Style.
    
    - Erscheint automatisch bei Body-Selektion
    - 3 Pfeile für X/Y/Z
    - Direktes Drag ohne Bestätigung
    """
    
    def __init__(self, plotter):
        self.plotter = plotter
        self.visible = False
        self.center = np.array([0.0, 0.0, 0.0])
        
        # Geometrie-Parameter (werden dynamisch angepasst)
        self._arrow_length = 30.0
        self._arrow_radius = 1.5
        self._tip_length = 8.0
        self._tip_radius = 3.0
        
        # Actor-Namen
        self._actor_names: List[str] = []
        
        # Picking-Geometrien (für Ray-Test)
        self._pick_meshes = {}
        
        # Zustand
        self.hovered_axis = GizmoAxis.NONE
        self.active_axis = GizmoAxis.NONE
        
        # Für schnelles Verschieben: Transform-Offset
        self._transform_offset = np.array([0.0, 0.0, 0.0])
        
    def show(self, center: np.ndarray, body_size: float = None):
        """Zeigt das Gizmo an der Position
        
        Args:
            center: Position des Gizmos
            body_size: Optionale Body-Größe für Skalierung
        """
        self.hide()
        self.center = np.array(center, dtype=float)
        self._transform_offset = np.array([0.0, 0.0, 0.0])
        self.visible = True
        
        # Größe anpassen basierend auf Body-Größe oder Kamera
        if body_size and body_size > 0:
            # Pfeil = ca. 50% der Body-Größe
            self._arrow_length = max(body_size * 0.5, 10.0)
        else:
            # Fallback: Kamera-Distanz
            try:
                cam_pos = np.array(self.plotter.camera.position)
                distance = np.linalg.norm(cam_pos - self.center)
                self._arrow_length = max(distance * 0.15, 10.0)
            except:
                self._arrow_length = 30.0
                
        # Proportionen anpassen
        self._arrow_radius = self._arrow_length * 0.05
        self._tip_length = self._arrow_length * 0.25
        self._tip_radius = self._arrow_length * 0.1
        
        self._create_arrows()
        self.plotter.render()
        
    def hide(self):
        """Versteckt das Gizmo"""
        for name in self._actor_names:
            try:
                self.plotter.remove_actor(name)
            except:
                pass
        self._actor_names.clear()
        self._pick_meshes.clear()
        self.visible = False
        self.hovered_axis = GizmoAxis.NONE
        self.active_axis = GizmoAxis.NONE
        self._transform_offset = np.array([0.0, 0.0, 0.0])
        
    def move_to(self, new_center: np.ndarray):
        """Bewegt das Gizmo zu einer neuen Position (schnell via UserTransform)"""
        if not self.visible:
            return
            
        # Delta vom Original-Zentrum berechnen
        self._transform_offset = np.array(new_center) - self.center
        
        # Alle Actors mit UserTransform verschieben (schnell!)
        transform = vtk.vtkTransform()
        transform.Translate(self._transform_offset[0], self._transform_offset[1], self._transform_offset[2])
        
        for name in self._actor_names:
            try:
                actor = self.plotter.renderer.actors.get(name)
                if actor:
                    actor.SetUserTransform(transform)
            except:
                pass
                
        # Pick-Meshes müssen auch aktualisiert werden
        # (Aber nur für Picking, nicht für Rendering)
        
    def get_current_center(self) -> np.ndarray:
        """Gibt das aktuelle Zentrum zurück (inkl. Offset)"""
        return self.center + self._transform_offset
        
    def pick(self, ray_origin: np.ndarray, ray_dir: np.ndarray) -> GizmoAxis:
        """Prüft ob ein Ray das Gizmo trifft"""
        if not self.visible:
            return GizmoAxis.NONE
            
        best_axis = GizmoAxis.NONE
        best_dist = float('inf')
        
        # Ray muss um den Offset verschoben werden (oder Meshes)
        adjusted_origin = ray_origin - self._transform_offset
        
        for axis, mesh in self._pick_meshes.items():
            try:
                points, _ = mesh.ray_trace(adjusted_origin, adjusted_origin + ray_dir * 10000)
                if len(points) > 0:
                    dist = np.linalg.norm(points[0] - adjusted_origin)
                    if dist < best_dist:
                        best_dist = dist
                        best_axis = axis
            except:
                pass
                
        return best_axis
        
    def set_hover(self, axis: GizmoAxis):
        """Setzt die Hover-Hervorhebung"""
        if axis == self.hovered_axis:
            return
        self.hovered_axis = axis
        self._update_colors()
        
    def set_active(self, axis: GizmoAxis):
        """Setzt die aktive Achse"""
        self.active_axis = axis
        self._update_colors()
        
    def get_axis_direction(self, axis: GizmoAxis) -> Optional[np.ndarray]:
        """Gibt die Richtung einer Achse zurück"""
        if axis == GizmoAxis.X:
            return np.array([1.0, 0.0, 0.0])
        elif axis == GizmoAxis.Y:
            return np.array([0.0, 1.0, 0.0])
        elif axis == GizmoAxis.Z:
            return np.array([0.0, 0.0, 1.0])
        return None
        
    # ==================== PRIVATE ====================
    
    def _create_arrows(self):
        """Erstellt die 3 Achsen-Pfeile"""
        axes = [
            (GizmoAxis.X, [1, 0, 0], COLORS[GizmoAxis.X]),
            (GizmoAxis.Y, [0, 1, 0], COLORS[GizmoAxis.Y]),
            (GizmoAxis.Z, [0, 0, 1], COLORS[GizmoAxis.Z]),
        ]
        
        for axis, direction, color in axes:
            self._create_arrow(axis, direction, color)
            
    def _create_arrow(self, axis: GizmoAxis, direction: List[float], color: str):
        """Erstellt einen Pfeil für eine Achse"""
        dir_vec = np.array(direction, dtype=float)
        
        # Schaft (Zylinder)
        shaft_center = self.center + dir_vec * (self._arrow_length / 2)
        shaft = pv.Cylinder(
            center=shaft_center,
            direction=dir_vec,
            radius=self._arrow_radius,
            height=self._arrow_length
        )
        
        # Spitze (Kegel)
        tip_center = self.center + dir_vec * (self._arrow_length + self._tip_length / 2)
        tip = pv.Cone(
            center=tip_center,
            direction=dir_vec,
            height=self._tip_length,
            radius=self._tip_radius,
            resolution=20
        )
        
        # Kombinieren für Picking
        combined = shaft + tip
        self._pick_meshes[axis] = combined
        
        # Rendern
        name_shaft = f"gizmo_{axis.name}_shaft"
        name_tip = f"gizmo_{axis.name}_tip"
        
        actor_shaft = self.plotter.add_mesh(
            shaft, color=color, name=name_shaft, pickable=False,
            ambient=1.0, diffuse=0.0  # Voll beleuchtet, unabhängig von Licht
        )
        actor_tip = self.plotter.add_mesh(
            tip, color=color, name=name_tip, pickable=False,
            ambient=1.0, diffuse=0.0
        )
        
        # WICHTIG: Depth-Test deaktivieren damit Gizmo IMMER sichtbar ist
        for actor in [actor_shaft, actor_tip]:
            if actor:
                try:
                    prop = actor.GetProperty()
                    # Immer im Vordergrund rendern
                    actor.SetPickable(False)
                    # Polygon Offset für Z-Fighting
                    actor.GetMapper().SetResolveCoincidentTopologyToPolygonOffset()
                    actor.GetMapper().SetRelativeCoincidentTopologyPolygonOffsetParameters(-2, -2)
                except:
                    pass
                    
        self._actor_names.extend([name_shaft, name_tip])
        
    def _update_colors(self):
        """Aktualisiert die Farben basierend auf Hover/Active"""
        for axis in [GizmoAxis.X, GizmoAxis.Y, GizmoAxis.Z]:
            if axis == self.active_axis:
                color = COLORS["hover"]
            elif axis == self.hovered_axis:
                color = COLORS["hover"]
            else:
                color = COLORS[axis]
                
            for suffix in ["_shaft", "_tip"]:
                name = f"gizmo_{axis.name}{suffix}"
                try:
                    actor = self.plotter.renderer.actors.get(name)
                    if actor:
                        actor.GetProperty().SetColor(pv.Color(color).float_rgb)
                except:
                    pass
                    
        self.plotter.render()


@dataclass
class DragState:
    """Zustand während eines Drag-Vorgangs"""
    body_id: str
    axis: GizmoAxis
    start_center: np.ndarray
    start_point: np.ndarray
    

class SimpleTransformController:
    """
    Controller für Onshape-Style Transforms.
    
    Workflow:
    1. Body selektieren → Gizmo erscheint
    2. Pfeil ziehen → Body bewegt sich live
    3. Loslassen → Transform wird angewendet
    """
    
    def __init__(self, viewport):
        self.viewport = viewport
        self.plotter = viewport.plotter
        
        # Gizmo
        self.gizmo = SimpleTransformGizmo(self.plotter)
        
        # Aktueller Body
        self.selected_body_id: Optional[str] = None
        
        # Drag-Zustand
        self.drag_state: Optional[DragState] = None
        self.is_dragging = False
        
        # Total Translation während Drag
        self._total_translation = np.array([0.0, 0.0, 0.0])
        
        # Screen-Positionen für Delta-Berechnung
        self._drag_start_screen = (0, 0)
        self._drag_last_screen = (0, 0)
        
        # Callbacks
        self._get_body_center = None
        self._apply_transform = None
        
    def set_callbacks(self, get_body_center, apply_transform):
        """Setzt die Callbacks für Body-Operationen"""
        self._get_body_center = get_body_center
        self._apply_transform = apply_transform
        
    def select_body(self, body_id: str, force_refresh: bool = False):
        """Selektiert einen Body und zeigt das Gizmo
        
        Args:
            body_id: ID des Bodies
            force_refresh: Gizmo neu positionieren auch wenn Body gleich
        """
        # Bei force_refresh oder neuem Body: Gizmo neu erstellen
        if body_id != self.selected_body_id or force_refresh or not self.gizmo.visible:
            self.selected_body_id = body_id
            self._total_translation = np.array([0.0, 0.0, 0.0])
            
            if self._get_body_center:
                center = self._get_body_center(body_id)
                if center is not None:
                    # Body-Größe berechnen
                    body_size = self._get_body_size(body_id)
                    self.gizmo.show(center, body_size)
                    logger.debug(f"Gizmo gezeigt für Body {body_id}, Größe={body_size:.1f}")
                
    def _get_body_size(self, body_id: str) -> float:
        """Berechnet die ungefähre Größe eines Bodies"""
        try:
            if body_id in self.viewport._body_actors:
                actors = self.viewport._body_actors[body_id]
                if actors:
                    actor_name = actors[0]
                    actor = self.plotter.renderer.actors.get(actor_name)
                    if actor:
                        bounds = actor.GetBounds()
                        # Größte Dimension
                        size_x = bounds[1] - bounds[0]
                        size_y = bounds[3] - bounds[2]
                        size_z = bounds[5] - bounds[4]
                        return max(size_x, size_y, size_z)
        except:
            pass
        return 50.0  # Fallback
                
    def deselect(self):
        """Hebt die Selektion auf"""
        self.selected_body_id = None
        self.gizmo.hide()
        self.drag_state = None
        self.is_dragging = False
        self._total_translation = np.array([0.0, 0.0, 0.0])
        
    def on_mouse_press(self, screen_pos: Tuple[int, int]) -> bool:
        """Verarbeitet Mausklick. Returns True wenn konsumiert."""
        if not self.gizmo.visible:
            return False
            
        ray_origin, ray_dir = self._get_ray(screen_pos)
        if ray_origin is None:
            return False
            
        axis = self.gizmo.pick(ray_origin, ray_dir)
        
        if axis != GizmoAxis.NONE:
            self.is_dragging = True
            self.gizmo.set_active(axis)
            
            # Screen-Position speichern für Delta-Berechnung
            self._drag_start_screen = screen_pos
            self._drag_last_screen = screen_pos
            
            self.drag_state = DragState(
                body_id=self.selected_body_id,
                axis=axis,
                start_center=self.gizmo.get_current_center().copy(),
                start_point=self.gizmo.get_current_center().copy()  # Nicht mehr verwendet
            )
            
            logger.debug(f"Drag gestartet: Achse {axis.name}")
            return True
            
        return False
        
    def on_mouse_move(self, screen_pos: Tuple[int, int]) -> bool:
        """Verarbeitet Mausbewegung. Returns True wenn konsumiert."""
        if not self.gizmo.visible:
            return False
            
        ray_origin, ray_dir = self._get_ray(screen_pos)
        if ray_origin is None:
            return False
            
        if self.is_dragging and self.drag_state:
            # Screen-Delta berechnen
            dx_screen = screen_pos[0] - self._drag_last_screen[0]
            dy_screen = screen_pos[1] - self._drag_last_screen[1]
            self._drag_last_screen = screen_pos
            
            # Achsen-Richtung holen
            axis_dir = self.gizmo.get_axis_direction(self.drag_state.axis)
            if axis_dir is None:
                return True
            
            # Kamera-basierte Projektion:
            # Projiziere die 3D-Achse auf den Bildschirm und berechne
            # wie sich Screen-Bewegung auf 3D-Bewegung übersetzt
            try:
                renderer = self.plotter.renderer
                center = self.gizmo.get_current_center()
                
                # Zentrum in Screen-Koordinaten
                renderer.SetWorldPoint(center[0], center[1], center[2], 1.0)
                renderer.WorldToDisplay()
                center_screen = np.array(renderer.GetDisplayPoint()[:2])
                
                # Punkt auf der Achse in Screen-Koordinaten
                axis_point = center + axis_dir * 100  # 100 units entlang Achse
                renderer.SetWorldPoint(axis_point[0], axis_point[1], axis_point[2], 1.0)
                renderer.WorldToDisplay()
                axis_screen = np.array(renderer.GetDisplayPoint()[:2])
                
                # Screen-Richtung der Achse
                screen_axis_dir = axis_screen - center_screen
                screen_axis_len = np.linalg.norm(screen_axis_dir)
                
                if screen_axis_len > 1:
                    screen_axis_dir = screen_axis_dir / screen_axis_len
                    
                    # Dot-Product: wie viel der Screen-Bewegung geht entlang der Achse
                    screen_movement = np.array([dx_screen, -dy_screen])  # Y invertiert
                    movement_along_axis = np.dot(screen_movement, screen_axis_dir)
                    
                    # In 3D-Bewegung umrechnen
                    # Sensitivity: 100 screen pixels = 100 world units / screen_axis_len
                    sensitivity = 100.0 / screen_axis_len
                    delta_3d = axis_dir * movement_along_axis * sensitivity
                else:
                    # Achse zeigt direkt auf Kamera - keine Bewegung möglich
                    delta_3d = np.array([0.0, 0.0, 0.0])
                    
            except Exception as e:
                logger.warning(f"Projektion fehlgeschlagen: {e}")
                # Fallback
                delta_3d = np.array([0.0, 0.0, 0.0])
            
            # Total Translation updaten
            self._total_translation += delta_3d
            
            # Neue Zentrum-Position
            new_center = self.gizmo.center + self._total_translation
            
            # Gizmo und Body bewegen
            self.gizmo.move_to(new_center)
            self._move_body_preview(self.drag_state.body_id, self._total_translation)
            
            self.plotter.render()
                    
            return True
        else:
            # Hover
            axis = self.gizmo.pick(ray_origin, ray_dir)
            self.gizmo.set_hover(axis)
            
        return False
        
    def on_mouse_release(self, screen_pos: Tuple[int, int]) -> bool:
        """Verarbeitet Maus-Loslassen. Returns True wenn konsumiert."""
        if not self.is_dragging or not self.drag_state:
            return False
            
        total_delta = self._total_translation.copy()
        body_id = self.drag_state.body_id
        
        logger.debug(f"Mouse release: total_delta={total_delta}")
        
        # WICHTIG: UserTransform NICHT zurücksetzen!
        # Das neue Mesh von Build123d ersetzt den Actor sowieso komplett.
        # Wenn wir hier resetten, springt der Body kurz zurück bevor das neue Mesh da ist.
        
        # Gizmo verstecken
        self.gizmo.hide()
        
        # Transform anwenden (Build123d)
        if self._apply_transform and np.linalg.norm(total_delta) > 0.001:
            logger.debug(f"Applying transform: {total_delta.tolist()}")
            self._apply_transform(
                body_id,
                "move",
                total_delta.tolist()
            )
            logger.info(f"Move angewendet: ({total_delta[0]:.1f}, {total_delta[1]:.1f}, {total_delta[2]:.1f})")
        else:
            logger.debug("Keine signifikante Bewegung - Gizmo wieder anzeigen")
            # Kein signifikanter Move - Body zurücksetzen und Gizmo anzeigen
            self._reset_body_preview(body_id)
            if self._get_body_center:
                center = self._get_body_center(body_id)
                if center is not None:
                    body_size = self._get_body_size(body_id)
                    self.gizmo.show(center, body_size)
            
        # Cleanup
        self.is_dragging = False
        self.gizmo.set_active(GizmoAxis.NONE)
        self.drag_state = None
        self._total_translation = np.array([0.0, 0.0, 0.0])
        
        return True
    
    def _reset_body_preview(self, body_id: str):
        """Setzt Actor-Transforms zurück (ohne render!)"""
        if body_id not in self.viewport._body_actors:
            return
            
        for actor_name in self.viewport._body_actors[body_id]:
            try:
                actor = self.plotter.renderer.actors.get(actor_name)
                if actor:
                    actor.SetUserTransform(None)
            except:
                pass
        # KEIN render() hier - das passiert nach dem Mesh-Update
        
    # ==================== PRIVATE ====================
    
    def _get_ray(self, screen_pos: Tuple[int, int]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Berechnet Ray aus Bildschirmposition"""
        try:
            x, y = screen_pos
            renderer = self.plotter.renderer
            height = self.plotter.interactor.height()
            y_flipped = height - y
            
            renderer.SetDisplayPoint(x, y_flipped, 0)
            renderer.DisplayToWorld()
            near = np.array(renderer.GetWorldPoint()[:3])
            
            renderer.SetDisplayPoint(x, y_flipped, 1)
            renderer.DisplayToWorld()
            far = np.array(renderer.GetWorldPoint()[:3])
            
            direction = far - near
            direction = direction / np.linalg.norm(direction)
            
            return near, direction
        except:
            return None, None
            
    def _project_to_axis(self, ray_origin: np.ndarray, ray_dir: np.ndarray, 
                          axis: GizmoAxis) -> Optional[np.ndarray]:
        """Projiziert einen Ray auf eine Achse"""
        axis_dir = self.gizmo.get_axis_direction(axis)
        if axis_dir is None:
            return None
            
        line_point = self.gizmo.get_current_center()
        
        w = ray_origin - line_point
        a = np.dot(ray_dir, ray_dir)
        b = np.dot(ray_dir, axis_dir)
        c = np.dot(axis_dir, axis_dir)
        d = np.dot(ray_dir, w)
        e = np.dot(axis_dir, w)
        
        denom = a * c - b * b
        if abs(denom) < 1e-10:
            return None
            
        t = (b * d - a * e) / denom
        
        return line_point + t * axis_dir
        
    def _move_body_preview(self, body_id: str, delta: np.ndarray):
        """Bewegt Body-Actors für Preview (via UserTransform)"""
        if body_id not in self.viewport._body_actors:
            return
            
        transform = vtk.vtkTransform()
        transform.Translate(delta[0], delta[1], delta[2])
        
        for actor_name in self.viewport._body_actors[body_id]:
            try:
                actor = self.plotter.renderer.actors.get(actor_name)
                if actor:
                    actor.SetUserTransform(transform)
            except:
                pass
