"""
MashCad - Transform Gizmo V3 (Full Feature)
Vollständiges Transform-System mit Move, Rotate, Scale, Copy, Mirror

Basiert auf V2, erweitert um:
- Rotate: Ringe um jede Achse
- Scale: Würfel an Achsenenden  
- Copy: Dupliziert Body bei Transform
- Mirror: Spiegelt an XY/XZ/YZ Ebene
"""

import numpy as np
from typing import Optional, Tuple, List, Callable
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


class TransformMode(Enum):
    """Aktiver Transform-Modus"""
    MOVE = auto()
    ROTATE = auto()
    SCALE = auto()


class GizmoAxis(Enum):
    """Aktive Achse für Transformation"""
    NONE = auto()
    X = auto()
    Y = auto()
    Z = auto()
    ALL = auto()  # Für uniform Scale


class GizmoElement(Enum):
    """Welches Gizmo-Element wird angeklickt"""
    NONE = auto()
    ARROW_X = auto()
    ARROW_Y = auto()
    ARROW_Z = auto()
    RING_X = auto()
    RING_Y = auto()
    RING_Z = auto()
    SCALE_X = auto()
    SCALE_Y = auto()
    SCALE_Z = auto()
    SCALE_CENTER = auto()  # Uniform Scale


# Farben
COLORS = {
    GizmoAxis.X: "#E63946",      # Rot
    GizmoAxis.Y: "#2A9D8F",      # Grün/Teal  
    GizmoAxis.Z: "#457B9D",      # Blau
    GizmoAxis.ALL: "#FFFFFF",    # Weiß für Center
    "hover": "#FFD700",          # Gold bei Hover
    "center": "#AAAAAA",         # Grau für Zentrum
}


class FullTransformGizmo:
    """
    Vollständiges Transform-Gizmo mit Move/Rotate/Scale.
    
    Features:
    - Move: Pfeile für X/Y/Z Translation
    - Rotate: Ringe für X/Y/Z Rotation
    - Scale: Würfel für X/Y/Z + Center für Uniform Scale
    - Mode-Switching via Tastatur (G/R/S wie Blender)
    """
    
    def __init__(self, plotter):
        self.plotter = plotter
        self.visible = False
        self.center = np.array([0.0, 0.0, 0.0])
        self.mode = TransformMode.MOVE
        
        # Geometrie-Parameter
        self._size = 30.0  # Basis-Größe
        
        # Actor-Namen nach Typ
        self._move_actors: List[str] = []
        self._rotate_actors: List[str] = []
        self._scale_actors: List[str] = []
        
        # Picking-Geometrien
        self._pick_meshes = {}  # {GizmoElement: mesh}
        
        # Zustand
        self.hovered_element = GizmoElement.NONE
        self.active_element = GizmoElement.NONE
        
        # Transform-Offset für Preview
        self._transform_offset = np.array([0.0, 0.0, 0.0])
        self._rotation_angle = 0.0
        self._scale_factor = np.array([1.0, 1.0, 1.0])

    def _improve_actor_visibility(self, actor_name: str):
        """
        Verbessert die Sichtbarkeit eines Gizmo-Actors (Fix 3).
        Setzt Actor-Properties für bessere Z-Order und Rendering.
        """
        try:
            actor = self.plotter.renderer.actors.get(actor_name)
            if not actor:
                return

            # Verbesserte Linien-Darstellung
            prop = actor.GetProperty()
            prop.SetRenderLinesAsTubes(True)
            prop.SetLineWidth(4)

            # WICHTIG: Immer im Vordergrund rendern (kein Depth-Test)
            # Dies stellt sicher, dass das Gizmo IMMER sichtbar ist
            mapper = actor.GetMapper()
            if mapper:
                # Polygon-Offset für bessere Tiefendarstellung
                mapper.SetResolveCoincidentTopologyToPolygonOffset()
                mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-10, -10)

            # Alternative: Depth-Test komplett deaktivieren (sehr aggressiv)
            # Nur für Gizmo-Elemente sinnvoll, die IMMER sichtbar sein müssen
            try:
                # Setze höchste Render-Priorität
                actor.GetProperty().SetOpacity(1.0)
                # Deaktiviere Depth-Buffering für diesen Actor
                # ACHTUNG: Kann bei einigen VTK-Versionen zu Problemen führen
                if hasattr(mapper, 'SetResolveCoincidentTopologyToOff'):
                    pass  # Nutzen wir Polygon-Offset stattdessen
            except:
                pass

            logger.debug(f"Gizmo-Actor visibility improved: {actor_name}")
        except Exception as e:
            logger.warning(f"Konnte Visibility für {actor_name} nicht verbessern: {e}")

    def set_mode(self, mode: TransformMode):
        """Wechselt den Transform-Modus"""
        if mode == self.mode:
            return
        old_mode = self.mode
        self.mode = mode
        self._update_visibility()
        logger.debug(f"Gizmo Mode: {old_mode.name} → {mode.name}")
        
    def show(self, center: np.ndarray, body_size: float = None):
        """Zeigt das Gizmo an der Position"""
        self.hide()
        self.center = np.array(center, dtype=float)
        self._reset_transforms()
        self.visible = True
        
        # Größe anpassen (Fix: Größer machen, damit Gizmo besser sichtbar ist)
        if body_size and body_size > 0:
            # Mindestens 80% der Body-Größe, aber nicht kleiner als 40 Units
            self._size = max(body_size * 0.8, 40.0)
        else:
            try:
                cam_pos = np.array(self.plotter.camera.position)
                distance = np.linalg.norm(cam_pos - self.center)
                # Größerer Faktor für bessere Sichtbarkeit
                self._size = max(distance * 0.20, 40.0)
            except:
                self._size = 60.0
        
        self._create_all_elements()
        self._update_visibility()
        self.plotter.render()
        
    def hide(self):
        """Versteckt das Gizmo"""
        all_actors = self._move_actors + self._rotate_actors + self._scale_actors
        for name in all_actors:
            try:
                self.plotter.remove_actor(name)
            except:
                pass
        self._move_actors.clear()
        self._rotate_actors.clear()
        self._scale_actors.clear()
        self._pick_meshes.clear()
        self.visible = False
        self.hovered_element = GizmoElement.NONE
        self.active_element = GizmoElement.NONE
        self._reset_transforms()
        
    def _reset_transforms(self):
        """Setzt Transform-Werte zurück"""
        self._transform_offset = np.array([0.0, 0.0, 0.0])
        self._rotation_angle = 0.0
        self._scale_factor = np.array([1.0, 1.0, 1.0])
        
    def move_to(self, new_center: np.ndarray):
        """Bewegt das Gizmo (für Move-Preview)"""
        if not self.visible:
            return
        self._transform_offset = np.array(new_center) - self.center
        transform = vtk.vtkTransform()
        transform.Translate(*self._transform_offset)
        
        all_actors = self._move_actors + self._rotate_actors + self._scale_actors
        for name in all_actors:
            try:
                actor = self.plotter.renderer.actors.get(name)
                if actor:
                    actor.SetUserTransform(transform)
            except:
                pass
                
    def get_current_center(self) -> np.ndarray:
        """Gibt aktuelles Zentrum zurück"""
        return self.center + self._transform_offset
        
    def pick(self, ray_origin: np.ndarray, ray_dir: np.ndarray) -> GizmoElement:
        """Prüft welches Element getroffen wird"""
        if not self.visible:
            return GizmoElement.NONE
            
        best_element = GizmoElement.NONE
        best_dist = float('inf')
        
        # Ray um Offset verschieben
        adjusted_origin = ray_origin - self._transform_offset
        
        # Nur Elemente des aktuellen Modus prüfen
        elements_to_check = self._get_active_elements()
        
        for element in elements_to_check:
            if element not in self._pick_meshes:
                continue
            mesh = self._pick_meshes[element]
            try:
                points, _ = mesh.ray_trace(adjusted_origin, adjusted_origin + ray_dir * 10000)
                if len(points) > 0:
                    dist = np.linalg.norm(points[0] - adjusted_origin)
                    if dist < best_dist:
                        best_dist = dist
                        best_element = element
            except:
                pass
                
        return best_element
        
    def _get_active_elements(self) -> List[GizmoElement]:
        """Gibt die Elemente des aktuellen Modus zurück"""
        if self.mode == TransformMode.MOVE:
            return [GizmoElement.ARROW_X, GizmoElement.ARROW_Y, GizmoElement.ARROW_Z]
        elif self.mode == TransformMode.ROTATE:
            return [GizmoElement.RING_X, GizmoElement.RING_Y, GizmoElement.RING_Z]
        elif self.mode == TransformMode.SCALE:
            return [GizmoElement.SCALE_X, GizmoElement.SCALE_Y, GizmoElement.SCALE_Z, 
                    GizmoElement.SCALE_CENTER]
        return []
        
    def set_hover(self, element: GizmoElement):
        """Setzt Hover-Hervorhebung"""
        if element == self.hovered_element:
            return
        self.hovered_element = element
        self._update_colors()
        
    def set_active(self, element: GizmoElement):
        """Setzt aktives Element"""
        self.active_element = element
        self._update_colors()
        
    def get_axis_from_element(self, element: GizmoElement) -> GizmoAxis:
        """Gibt die Achse für ein Element zurück"""
        axis_map = {
            GizmoElement.ARROW_X: GizmoAxis.X,
            GizmoElement.ARROW_Y: GizmoAxis.Y,
            GizmoElement.ARROW_Z: GizmoAxis.Z,
            GizmoElement.RING_X: GizmoAxis.X,
            GizmoElement.RING_Y: GizmoAxis.Y,
            GizmoElement.RING_Z: GizmoAxis.Z,
            GizmoElement.SCALE_X: GizmoAxis.X,
            GizmoElement.SCALE_Y: GizmoAxis.Y,
            GizmoElement.SCALE_Z: GizmoAxis.Z,
            GizmoElement.SCALE_CENTER: GizmoAxis.ALL,
        }
        return axis_map.get(element, GizmoAxis.NONE)
        
    def get_axis_direction(self, axis: GizmoAxis) -> Optional[np.ndarray]:
        """Gibt Richtungsvektor für Achse zurück"""
        if axis == GizmoAxis.X:
            return np.array([1.0, 0.0, 0.0])
        elif axis == GizmoAxis.Y:
            return np.array([0.0, 1.0, 0.0])
        elif axis == GizmoAxis.Z:
            return np.array([0.0, 0.0, 1.0])
        return None
        
    # ==================== GEOMETRIE ERSTELLEN ====================
    
    def _create_all_elements(self):
        """Erstellt alle Gizmo-Elemente"""
        self._create_move_arrows()
        self._create_rotate_rings()
        self._create_scale_cubes()
        
    def _create_move_arrows(self):
        """Erstellt die Move-Pfeile"""
        axes = [
            (GizmoElement.ARROW_X, [1, 0, 0], COLORS[GizmoAxis.X]),
            (GizmoElement.ARROW_Y, [0, 1, 0], COLORS[GizmoAxis.Y]),
            (GizmoElement.ARROW_Z, [0, 0, 1], COLORS[GizmoAxis.Z]),
        ]
        
        for element, direction, color in axes:
            dir_vec = np.array(direction, dtype=float)
            
            # Schaft
            shaft_len = self._size * 0.7
            shaft_center = self.center + dir_vec * (shaft_len / 2)
            shaft = pv.Cylinder(
                center=shaft_center,
                direction=dir_vec,
                radius=self._size * 0.03,
                height=shaft_len
            )
            
            # Spitze
            tip_len = self._size * 0.25
            tip_center = self.center + dir_vec * (shaft_len + tip_len / 2)
            tip = pv.Cone(
                center=tip_center,
                direction=dir_vec,
                height=tip_len,
                radius=self._size * 0.08,
                resolution=16
            )
            
            # Kombinieren
            arrow = shaft + tip
            name = f"gizmo_arrow_{element.name}"

            self.plotter.add_mesh(arrow, color=color, name=name,
                                  pickable=False, render_lines_as_tubes=True)
            self._improve_actor_visibility(name)  # Fix 3: Bessere Sichtbarkeit
            self._move_actors.append(name)
            self._pick_meshes[element] = arrow
            
    def _create_rotate_rings(self):
        """Erstellt die Rotations-Ringe"""
        axes = [
            (GizmoElement.RING_X, [1, 0, 0], COLORS[GizmoAxis.X]),
            (GizmoElement.RING_Y, [0, 1, 0], COLORS[GizmoAxis.Y]),
            (GizmoElement.RING_Z, [0, 0, 1], COLORS[GizmoAxis.Z]),
        ]
        
        ring_radius = self._size * 0.8
        tube_radius = self._size * 0.025
        
        for element, direction, color in axes:
            # Torus (Ring) erstellen
            ring = pv.ParametricTorus(
                ringradius=ring_radius,
                crosssectionradius=tube_radius
            )
            
            # Rotieren zur richtigen Orientierung
            if direction == [1, 0, 0]:  # X-Ring: rotiert um Y
                ring = ring.rotate_y(90, inplace=False)
            elif direction == [0, 1, 0]:  # Y-Ring: rotiert um X
                ring = ring.rotate_x(90, inplace=False)
            # Z-Ring ist bereits korrekt orientiert
            
            # Verschieben zum Zentrum
            ring = ring.translate(self.center, inplace=False)

            name = f"gizmo_ring_{element.name}"
            self.plotter.add_mesh(ring, color=color, name=name,
                                  pickable=False, opacity=0.8)
            self._improve_actor_visibility(name)  # Fix 3: Bessere Sichtbarkeit
            self._rotate_actors.append(name)
            self._pick_meshes[element] = ring
            
    def _create_scale_cubes(self):
        """Erstellt die Scale-Würfel an den Achsenenden"""
        axes = [
            (GizmoElement.SCALE_X, [1, 0, 0], COLORS[GizmoAxis.X]),
            (GizmoElement.SCALE_Y, [0, 1, 0], COLORS[GizmoAxis.Y]),
            (GizmoElement.SCALE_Z, [0, 0, 1], COLORS[GizmoAxis.Z]),
        ]
        
        cube_size = self._size * 0.12
        
        for element, direction, color in axes:
            dir_vec = np.array(direction, dtype=float)
            cube_center = self.center + dir_vec * self._size * 0.85
            
            cube = pv.Cube(center=cube_center, x_length=cube_size,
                          y_length=cube_size, z_length=cube_size)

            name = f"gizmo_scale_{element.name}"
            self.plotter.add_mesh(cube, color=color, name=name, pickable=False)
            self._improve_actor_visibility(name)  # Fix 3: Bessere Sichtbarkeit
            self._scale_actors.append(name)
            self._pick_meshes[element] = cube

        # Zentrum für Uniform Scale
        center_sphere = pv.Sphere(center=self.center, radius=self._size * 0.08)
        name = "gizmo_scale_center"
        self.plotter.add_mesh(center_sphere, color=COLORS["center"], name=name, pickable=False)
        self._improve_actor_visibility(name)  # Fix 3: Bessere Sichtbarkeit
        self._scale_actors.append(name)
        self._pick_meshes[GizmoElement.SCALE_CENTER] = center_sphere
        
    def _update_visibility(self):
        """Aktualisiert Sichtbarkeit basierend auf Modus"""
        # Move-Actors
        for name in self._move_actors:
            try:
                actor = self.plotter.renderer.actors.get(name)
                if actor:
                    actor.SetVisibility(self.mode == TransformMode.MOVE)
            except:
                pass
                
        # Rotate-Actors
        for name in self._rotate_actors:
            try:
                actor = self.plotter.renderer.actors.get(name)
                if actor:
                    actor.SetVisibility(self.mode == TransformMode.ROTATE)
            except:
                pass
                
        # Scale-Actors
        for name in self._scale_actors:
            try:
                actor = self.plotter.renderer.actors.get(name)
                if actor:
                    actor.SetVisibility(self.mode == TransformMode.SCALE)
            except:
                pass
                
        self.plotter.render()
        
    def _update_colors(self):
        """Aktualisiert Farben basierend auf Hover/Active"""
        element_to_actors = {
            GizmoElement.ARROW_X: [f"gizmo_arrow_{GizmoElement.ARROW_X.name}"],
            GizmoElement.ARROW_Y: [f"gizmo_arrow_{GizmoElement.ARROW_Y.name}"],
            GizmoElement.ARROW_Z: [f"gizmo_arrow_{GizmoElement.ARROW_Z.name}"],
            GizmoElement.RING_X: [f"gizmo_ring_{GizmoElement.RING_X.name}"],
            GizmoElement.RING_Y: [f"gizmo_ring_{GizmoElement.RING_Y.name}"],
            GizmoElement.RING_Z: [f"gizmo_ring_{GizmoElement.RING_Z.name}"],
            GizmoElement.SCALE_X: [f"gizmo_scale_{GizmoElement.SCALE_X.name}"],
            GizmoElement.SCALE_Y: [f"gizmo_scale_{GizmoElement.SCALE_Y.name}"],
            GizmoElement.SCALE_Z: [f"gizmo_scale_{GizmoElement.SCALE_Z.name}"],
            GizmoElement.SCALE_CENTER: ["gizmo_scale_center"],
        }
        
        for element, actor_names in element_to_actors.items():
            axis = self.get_axis_from_element(element)
            
            # Farbe bestimmen
            if element == self.active_element or element == self.hovered_element:
                color = COLORS["hover"]
            else:
                color = COLORS.get(axis, "#888888")
                
            # Auf Actors anwenden
            for name in actor_names:
                try:
                    actor = self.plotter.renderer.actors.get(name)
                    if actor:
                        actor.GetProperty().SetColor(pv.Color(color).float_rgb)
                except:
                    pass
                    
        self.plotter.render()


@dataclass
class TransformState:
    """Zustand während einer Transform-Operation"""
    body_id: str
    mode: TransformMode
    element: GizmoElement
    axis: GizmoAxis
    start_center: np.ndarray
    start_mouse: Tuple[int, int]


class FullTransformController:
    """
    Controller für das erweiterte Transform-System.
    
    Unterstützt:
    - Move (G oder Klick auf Pfeil)
    - Rotate (R oder Klick auf Ring)
    - Scale (S oder Klick auf Würfel)
    - Copy (Shift gedrückt während Transform)
    - Mirror (M + Achse)
    """
    
    def __init__(self, viewport):
        self.viewport = viewport
        self.plotter = viewport.plotter
        self.gizmo = FullTransformGizmo(self.plotter)
        
        # Callbacks
        self._get_body_center: Optional[Callable] = None
        self._apply_transform: Optional[Callable] = None
        self._copy_body: Optional[Callable] = None
        self._mirror_body: Optional[Callable] = None
        self._on_values_changed: Optional[Callable] = None  # Live-Update während Drag
        
        # Zustand
        self.selected_body_id: Optional[str] = None
        self.is_dragging = False
        self.drag_state: Optional[TransformState] = None
        self.copy_mode = False  # Shift gedrückt?
        
        # Akkumulierte Werte
        self._total_translation = np.array([0.0, 0.0, 0.0])
        self._total_rotation = 0.0
        self._total_scale = 1.0
        
        # Screen-Tracking
        self._drag_start_screen = (0, 0)
        self._drag_last_screen = (0, 0)
        
    def set_callbacks(self, get_body_center=None, apply_transform=None,
                     copy_body=None, mirror_body=None, on_values_changed=None):
        """Setzt die Callback-Funktionen"""
        self._get_body_center = get_body_center
        self._apply_transform = apply_transform
        self._copy_body = copy_body
        self._mirror_body = mirror_body
        self._on_values_changed = on_values_changed
        
    def select_body(self, body_id: str, force_refresh: bool = True):
        """Selektiert einen Body und zeigt das Gizmo"""
        if self.selected_body_id == body_id and self.gizmo.visible and not force_refresh:
            return
            
        self.selected_body_id = body_id
        
        if self._get_body_center:
            center = self._get_body_center(body_id)
            if center is not None:
                body_size = self._get_body_size(body_id)
                self.gizmo.show(center, body_size)
                logger.debug(f"Gizmo gezeigt für Body {body_id}, Größe={body_size:.1f}")
                
    def deselect(self):
        """Deselektiert und versteckt Gizmo"""
        self.selected_body_id = None
        self.gizmo.hide()
        self.is_dragging = False
        self.drag_state = None
        
    def set_mode(self, mode: TransformMode):
        """Setzt den Transform-Modus"""
        self.gizmo.set_mode(mode)
        mode_names = {
            TransformMode.MOVE: "Move",
            TransformMode.ROTATE: "Rotate", 
            TransformMode.SCALE: "Scale"
        }
        logger.info(f"Transform Mode: {mode_names.get(mode, mode.name)}")
        
    def _get_body_size(self, body_id: str) -> float:
        """Berechnet Body-Größe für Gizmo-Skalierung"""
        try:
            if body_id in self.viewport._body_actors:
                actors = self.viewport._body_actors[body_id]
                if actors:
                    actor = self.plotter.renderer.actors.get(actors[0])
                    if actor:
                        bounds = actor.GetBounds()
                        size = max(
                            bounds[1] - bounds[0],
                            bounds[3] - bounds[2],
                            bounds[5] - bounds[4]
                        )
                        return size
        except:
            pass
        return 50.0
        
    # ==================== MOUSE HANDLING ====================
    
    def on_mouse_press(self, screen_pos: Tuple[int, int], shift_pressed: bool = False) -> bool:
        """Verarbeitet Mausklick"""
        if not self.gizmo.visible or not self.selected_body_id:
            return False
            
        self.copy_mode = shift_pressed
        
        ray_origin, ray_dir = self._get_ray(screen_pos)
        if ray_origin is None:
            return False
            
        element = self.gizmo.pick(ray_origin, ray_dir)
        
        if element != GizmoElement.NONE:
            self.is_dragging = True
            self.gizmo.set_active(element)
            
            self._total_translation = np.array([0.0, 0.0, 0.0])
            self._total_rotation = 0.0
            self._total_scale = 1.0
            
            self._drag_start_screen = screen_pos
            self._drag_last_screen = screen_pos
            
            axis = self.gizmo.get_axis_from_element(element)
            
            self.drag_state = TransformState(
                body_id=self.selected_body_id,
                mode=self.gizmo.mode,
                element=element,
                axis=axis,
                start_center=self.gizmo.get_current_center().copy(),
                start_mouse=screen_pos
            )
            
            mode_name = self.gizmo.mode.name
            axis_name = axis.name
            logger.debug(f"Drag gestartet: {mode_name} auf Achse {axis_name}")
            return True
            
        return False
        
    def on_mouse_move(self, screen_pos: Tuple[int, int]) -> bool:
        """Verarbeitet Mausbewegung"""
        if not self.gizmo.visible:
            return False
            
        ray_origin, ray_dir = self._get_ray(screen_pos)
        if ray_origin is None:
            return False
            
        if self.is_dragging and self.drag_state:
            dx_screen = screen_pos[0] - self._drag_last_screen[0]
            dy_screen = screen_pos[1] - self._drag_last_screen[1]
            self._drag_last_screen = screen_pos
            
            if self.drag_state.mode == TransformMode.MOVE:
                self._handle_move_drag(dx_screen, dy_screen)
            elif self.drag_state.mode == TransformMode.ROTATE:
                self._handle_rotate_drag(dx_screen, dy_screen)
            elif self.drag_state.mode == TransformMode.SCALE:
                self._handle_scale_drag(dx_screen, dy_screen)
                
            self.plotter.render()
            return True
        else:
            # Hover
            element = self.gizmo.pick(ray_origin, ray_dir)
            self.gizmo.set_hover(element)
            
        return False
        
    def on_mouse_release(self, screen_pos: Tuple[int, int]) -> bool:
        """Verarbeitet Maus-Loslassen"""
        if not self.is_dragging or not self.drag_state:
            return False
            
        body_id = self.drag_state.body_id
        mode = self.drag_state.mode
        
        # Transform zurücksetzen vor Apply
        self._reset_body_preview(body_id)
        
        # Gizmo verstecken
        self.gizmo.hide()
        
        # Transform anwenden
        if self._apply_transform:
            if mode == TransformMode.MOVE:
                if np.linalg.norm(self._total_translation) > 0.001:
                    if self.copy_mode and self._copy_body:
                        # Copy + Move
                        self._copy_body(body_id, "move", self._total_translation.tolist())
                        logger.info(f"Copy+Move: {self._total_translation}")
                    else:
                        self._apply_transform(body_id, "move", self._total_translation.tolist())
                        
            elif mode == TransformMode.ROTATE:
                if abs(self._total_rotation) > 0.1:
                    axis = self.drag_state.axis
                    rotation_data = {"axis": axis.name, "angle": self._total_rotation}
                    if self.copy_mode and self._copy_body:
                        self._copy_body(body_id, "rotate", rotation_data)
                    else:
                        self._apply_transform(body_id, "rotate", rotation_data)
                        
            elif mode == TransformMode.SCALE:
                if abs(self._total_scale - 1.0) > 0.001:
                    scale_data = {"factor": self._total_scale}
                    if self.copy_mode and self._copy_body:
                        self._copy_body(body_id, "scale", scale_data)
                    else:
                        self._apply_transform(body_id, "scale", scale_data)
        
        # Cleanup
        self.is_dragging = False
        self.copy_mode = False
        self.gizmo.set_active(GizmoElement.NONE)
        self.drag_state = None
        
        return True
        
    def _handle_move_drag(self, dx_screen: int, dy_screen: int):
        """Verarbeitet Move-Drag"""
        axis = self.drag_state.axis
        axis_dir = self.gizmo.get_axis_direction(axis)
        if axis_dir is None:
            return
            
        # Screen → World Projektion (wie in V2)
        try:
            renderer = self.plotter.renderer
            center = self.gizmo.get_current_center()
            
            renderer.SetWorldPoint(*center, 1.0)
            renderer.WorldToDisplay()
            center_screen = np.array(renderer.GetDisplayPoint()[:2])
            
            axis_point = center + axis_dir * 100
            renderer.SetWorldPoint(*axis_point, 1.0)
            renderer.WorldToDisplay()
            axis_screen = np.array(renderer.GetDisplayPoint()[:2])
            
            screen_axis_dir = axis_screen - center_screen
            screen_axis_len = np.linalg.norm(screen_axis_dir)
            
            if screen_axis_len > 1:
                screen_axis_dir = screen_axis_dir / screen_axis_len
                screen_movement = np.array([dx_screen, -dy_screen])
                movement_along_axis = np.dot(screen_movement, screen_axis_dir)
                sensitivity = 100.0 / screen_axis_len
                delta_3d = axis_dir * movement_along_axis * sensitivity
            else:
                delta_3d = np.array([0.0, 0.0, 0.0])
                
        except Exception as e:
            logger.warning(f"Move projection failed: {e}")
            delta_3d = np.array([0.0, 0.0, 0.0])
            
        self._total_translation += delta_3d
        
        # Live-Update an UI senden
        if self._on_values_changed:
            self._on_values_changed(
                self._total_translation[0],
                self._total_translation[1],
                self._total_translation[2]
            )
        
        new_center = self.gizmo.center + self._total_translation
        self.gizmo.move_to(new_center)
        self._move_body_preview(self.drag_state.body_id, self._total_translation)
        
    def _handle_rotate_drag(self, dx_screen: int, dy_screen: int):
        """Verarbeitet Rotate-Drag"""
        # Einfache Rotation: Screen-X-Bewegung = Rotation
        sensitivity = 0.5  # Grad pro Pixel
        delta_angle = dx_screen * sensitivity
        self._total_rotation += delta_angle
        
        # Live-Update an UI senden (für Rotate: Winkel auf entsprechender Achse)
        if self._on_values_changed and self.drag_state:
            axis = self.drag_state.axis
            x = self._total_rotation if axis == GizmoAxis.X else 0
            y = self._total_rotation if axis == GizmoAxis.Y else 0
            z = self._total_rotation if axis == GizmoAxis.Z else 0
            self._on_values_changed(x, y, z)
        
        # Preview via VTK Transform
        self._rotate_body_preview(self.drag_state.body_id, 
                                  self.drag_state.axis, 
                                  self._total_rotation)
        
    def _handle_scale_drag(self, dx_screen: int, dy_screen: int):
        """Verarbeitet Scale-Drag"""
        # Screen-X-Bewegung = Scale
        sensitivity = 0.005  # Scale pro Pixel
        delta_scale = dx_screen * sensitivity
        self._total_scale = max(0.1, self._total_scale + delta_scale)
        
        # Preview
        self._scale_body_preview(self.drag_state.body_id, self._total_scale)
        
    # ==================== PREVIEW ====================
    
    def _move_body_preview(self, body_id: str, delta: np.ndarray):
        """Move-Preview via UserTransform"""
        if body_id not in self.viewport._body_actors:
            return
        transform = vtk.vtkTransform()
        transform.Translate(*delta)
        for actor_name in self.viewport._body_actors[body_id]:
            try:
                actor = self.plotter.renderer.actors.get(actor_name)
                if actor:
                    actor.SetUserTransform(transform)
            except:
                pass
                
    def _rotate_body_preview(self, body_id: str, axis: GizmoAxis, angle: float):
        """Rotate-Preview via UserTransform"""
        if body_id not in self.viewport._body_actors:
            return
            
        center = self.gizmo.center
        transform = vtk.vtkTransform()
        transform.Translate(*center)
        
        if axis == GizmoAxis.X:
            transform.RotateX(angle)
        elif axis == GizmoAxis.Y:
            transform.RotateY(angle)
        elif axis == GizmoAxis.Z:
            transform.RotateZ(angle)
            
        transform.Translate(*(-center))
        
        for actor_name in self.viewport._body_actors[body_id]:
            try:
                actor = self.plotter.renderer.actors.get(actor_name)
                if actor:
                    actor.SetUserTransform(transform)
            except:
                pass
                
    def _scale_body_preview(self, body_id: str, factor: float):
        """Scale-Preview via UserTransform"""
        if body_id not in self.viewport._body_actors:
            return
            
        center = self.gizmo.center
        transform = vtk.vtkTransform()
        transform.Translate(*center)
        transform.Scale(factor, factor, factor)
        transform.Translate(*(-center))
        
        for actor_name in self.viewport._body_actors[body_id]:
            try:
                actor = self.plotter.renderer.actors.get(actor_name)
                if actor:
                    actor.SetUserTransform(transform)
            except:
                pass
                
    def _reset_body_preview(self, body_id: str):
        """Setzt Preview zurück"""
        if body_id not in self.viewport._body_actors:
            return
        for actor_name in self.viewport._body_actors[body_id]:
            try:
                actor = self.plotter.renderer.actors.get(actor_name)
                if actor:
                    actor.SetUserTransform(None)
            except:
                pass
                
    def _get_ray(self, screen_pos: Tuple[int, int]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Berechnet Ray aus Screen-Position"""
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
            
    # ==================== MIRROR ====================
    
    def mirror_body(self, body_id: str, plane: str):
        """Spiegelt Body an einer Ebene (XY, XZ, YZ)"""
        if self._mirror_body:
            self._mirror_body(body_id, plane)
            logger.info(f"Mirror {plane} auf Body {body_id}")
