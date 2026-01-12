"""
MashCad - Transform Gizmo
Professionelles 3D-Gizmo für Move/Rotate/Scale Operationen
Fusion360-Style mit Achsen-Pfeilen und Constraint-System
"""

import numpy as np
import pyvista as pv
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, Tuple, List
from loguru import logger


class GizmoMode(Enum):
    """Gizmo-Betriebsmodus"""
    MOVE = auto()
    ROTATE = auto()
    SCALE = auto()


class GizmoAxis(Enum):
    """Welche Achse/Ebene ist aktiv"""
    NONE = auto()
    X = auto()
    Y = auto()
    Z = auto()
    XY = auto()
    XZ = auto()
    YZ = auto()
    ALL = auto()  # Freie Bewegung / Uniform Scale


@dataclass
class GizmoColors:
    """Farbschema für das Gizmo"""
    x_axis: str = "#E63946"      # Rot
    y_axis: str = "#2A9D8F"      # Grün/Teal
    z_axis: str = "#457B9D"      # Blau
    hover: str = "#FFD700"       # Gold
    selected: str = "#FFFFFF"    # Weiß
    plane_alpha: float = 0.3     # Transparenz für Ebenen-Handles


class TransformGizmo:
    """
    3D Transform Gizmo mit Achsen-Pfeilen und Ebenen-Handles.
    
    Features:
    - Achsen-Pfeile für X/Y/Z Bewegung
    - Ebenen-Quadrate für XY/XZ/YZ Bewegung
    - Zentrale Kugel für freie Bewegung
    - Hover-Highlight
    - Konstante Bildschirmgröße
    """
    
    def __init__(self, plotter: pv.Plotter):
        self.plotter = plotter
        self.colors = GizmoColors()
        self.mode = GizmoMode.MOVE
        
        # Position und Größe
        self.center = np.array([0.0, 0.0, 0.0])
        self.base_size = 30.0  # Basis-Größe in World-Units
        self._current_size = self.base_size
        
        # Aktiver Zustand
        self.visible = False
        self.hovered_axis = GizmoAxis.NONE
        self.active_axis = GizmoAxis.NONE
        
        # Actor-Namen für Cleanup
        self._actor_names: List[str] = []
        
        # Geometrie-Cache für Picking
        self._pick_geometries = {}
        
    def show(self, center: np.ndarray, mode: GizmoMode = GizmoMode.MOVE):
        """Zeigt das Gizmo an der gegebenen Position"""
        self.hide()  # Altes Gizmo entfernen
        
        self.center = np.array(center)
        self.mode = mode
        self.visible = True
        
        # Größe basierend auf Camera-Distanz berechnen
        self._update_size()
        
        # Gizmo-Teile erstellen
        if mode == GizmoMode.MOVE:
            self._create_move_gizmo()
        elif mode == GizmoMode.ROTATE:
            self._create_rotate_gizmo()
        elif mode == GizmoMode.SCALE:
            self._create_scale_gizmo()
            
        self.plotter.render()
        
    def hide(self):
        """Versteckt das Gizmo"""
        for name in self._actor_names:
            try:
                self.plotter.remove_actor(name)
            except:
                pass
        self._actor_names.clear()
        self._pick_geometries.clear()
        self.visible = False
        self.hovered_axis = GizmoAxis.NONE
        self.active_axis = GizmoAxis.NONE
        
    def set_hover(self, axis: GizmoAxis):
        """Setzt die Hover-Hervorhebung"""
        if axis == self.hovered_axis:
            return
        self.hovered_axis = axis
        self._update_colors()
        
    def set_active(self, axis: GizmoAxis):
        """Setzt die aktive Achse (während Drag)"""
        self.active_axis = axis
        self._update_colors()
        
    def pick(self, ray_origin: np.ndarray, ray_dir: np.ndarray) -> GizmoAxis:
        """
        Prüft welches Gizmo-Element vom Ray getroffen wird.
        
        Returns:
            GizmoAxis die getroffen wurde, oder NONE
        """
        if not self.visible:
            return GizmoAxis.NONE
            
        closest_axis = GizmoAxis.NONE
        closest_dist = float('inf')
        
        # Prüfe alle Pick-Geometrien
        for axis, geometry in self._pick_geometries.items():
            hit_point = self._ray_mesh_intersection(ray_origin, ray_dir, geometry)
            if hit_point is not None:
                dist = np.linalg.norm(hit_point - ray_origin)
                if dist < closest_dist:
                    closest_dist = dist
                    closest_axis = axis
                    
        return closest_axis
        
    def get_constraint_direction(self) -> Optional[np.ndarray]:
        """Gibt die Constraint-Richtung für die aktive Achse zurück"""
        axis = self.active_axis if self.active_axis != GizmoAxis.NONE else self.hovered_axis
        
        if axis == GizmoAxis.X:
            return np.array([1.0, 0.0, 0.0])
        elif axis == GizmoAxis.Y:
            return np.array([0.0, 1.0, 0.0])
        elif axis == GizmoAxis.Z:
            return np.array([0.0, 0.0, 1.0])
        elif axis == GizmoAxis.XY:
            return None  # Ebene, nicht Linie
        elif axis == GizmoAxis.XZ:
            return None
        elif axis == GizmoAxis.YZ:
            return None
        return None
        
    def get_constraint_plane(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Gibt die Constraint-Ebene (Punkt, Normal) für die aktive Achse zurück"""
        axis = self.active_axis if self.active_axis != GizmoAxis.NONE else self.hovered_axis
        
        if axis == GizmoAxis.XY:
            return (self.center, np.array([0.0, 0.0, 1.0]))
        elif axis == GizmoAxis.XZ:
            return (self.center, np.array([0.0, 1.0, 0.0]))
        elif axis == GizmoAxis.YZ:
            return (self.center, np.array([1.0, 0.0, 0.0]))
        elif axis == GizmoAxis.ALL:
            # Ebene senkrecht zur Kamera
            cam_pos = np.array(self.plotter.camera_position[0])
            normal = cam_pos - self.center
            normal = normal / np.linalg.norm(normal)
            return (self.center, normal)
        return None
        
    def update_position(self, new_center: np.ndarray):
        """Aktualisiert die Gizmo-Position während des Drags"""
        if not self.visible:
            return
        
        # EINFACHER: Gizmo komplett neu erstellen an neuer Position
        # Das ist sicherer als Actors zu verschieben
        old_mode = self.mode
        old_active = self.active_axis
        old_hover = self.hovered_axis
        
        self.hide()
        self.show(new_center, old_mode)
        
        # Zustand wiederherstellen
        self.active_axis = old_active
        self.hovered_axis = old_hover
        self._update_colors()
            
    # ==================== PRIVATE METHODS ====================
    
    def _update_size(self):
        """Berechnet die Gizmo-Größe basierend auf Camera-Distanz"""
        try:
            cam_pos = np.array(self.plotter.camera_position[0])
            dist = np.linalg.norm(cam_pos - self.center)
            # Konstante Bildschirmgröße: Größer wenn weiter weg
            self._current_size = dist * 0.15  # ~15% der Kamera-Distanz
            self._current_size = max(5.0, min(200.0, self._current_size))  # Clamp
        except:
            self._current_size = self.base_size
            
    def _create_move_gizmo(self):
        """Erstellt das Move-Gizmo mit Pfeilen"""
        size = self._current_size
        
        # Achsen-Pfeile
        self._create_arrow(GizmoAxis.X, [1, 0, 0], self.colors.x_axis, size)
        self._create_arrow(GizmoAxis.Y, [0, 1, 0], self.colors.y_axis, size)
        self._create_arrow(GizmoAxis.Z, [0, 0, 1], self.colors.z_axis, size)
        
        # Ebenen-Handles (kleine Quadrate)
        self._create_plane_handle(GizmoAxis.XY, size * 0.3)
        self._create_plane_handle(GizmoAxis.XZ, size * 0.3)
        self._create_plane_handle(GizmoAxis.YZ, size * 0.3)
        
        # Zentrale Kugel für freie Bewegung
        self._create_center_sphere(size * 0.12)
        
    def _create_rotate_gizmo(self):
        """Erstellt das Rotate-Gizmo mit Ringen"""
        size = self._current_size
        
        # Rotations-Ringe
        self._create_rotation_ring(GizmoAxis.X, [1, 0, 0], self.colors.x_axis, size)
        self._create_rotation_ring(GizmoAxis.Y, [0, 1, 0], self.colors.y_axis, size)
        self._create_rotation_ring(GizmoAxis.Z, [0, 0, 1], self.colors.z_axis, size)
        
    def _create_scale_gizmo(self):
        """Erstellt das Scale-Gizmo mit Box-Handles"""
        size = self._current_size
        
        # Achsen-Handles (Würfel an den Enden)
        self._create_scale_handle(GizmoAxis.X, [1, 0, 0], self.colors.x_axis, size)
        self._create_scale_handle(GizmoAxis.Y, [0, 1, 0], self.colors.y_axis, size)
        self._create_scale_handle(GizmoAxis.Z, [0, 0, 1], self.colors.z_axis, size)
        
        # Zentrale Box für Uniform Scale
        self._create_center_cube(size * 0.15)
        
    def _create_arrow(self, axis: GizmoAxis, direction: List[float], color: str, length: float):
        """Erstellt einen einzelnen Pfeil (Stiel + Spitze) - IMMER im Vordergrund"""
        dir_vec = np.array(direction, dtype=float)
        
        # Stiel (Zylinder)
        shaft_length = length * 0.75
        shaft_radius = length * 0.025
        shaft = pv.Cylinder(
            center=self.center + dir_vec * shaft_length / 2,
            direction=dir_vec,
            radius=shaft_radius,
            height=shaft_length
        )
        
        # Spitze (Kegel)
        tip_length = length * 0.25
        tip_radius = length * 0.07
        tip_center = self.center + dir_vec * (shaft_length + tip_length / 2)
        tip = pv.Cone(
            center=tip_center,
            direction=dir_vec,
            height=tip_length,
            radius=tip_radius,
            resolution=20
        )
        
        # Kombinieren für Picking
        combined = shaft + tip
        self._pick_geometries[axis] = combined
        
        # Rendern mit Depth-Test AUS (immer im Vordergrund)
        name_shaft = f"gizmo_{axis.name}_shaft"
        name_tip = f"gizmo_{axis.name}_tip"
        
        # render_points_as_spheres=False und andere Optionen für Vordergrund
        actor_shaft = self.plotter.add_mesh(
            shaft, color=color, name=name_shaft, pickable=False,
            render_points_as_spheres=False
        )
        actor_tip = self.plotter.add_mesh(
            tip, color=color, name=name_tip, pickable=False,
            render_points_as_spheres=False
        )
        
        # Depth-Test deaktivieren für diese Actors
        try:
            for actor in [actor_shaft, actor_tip]:
                if actor:
                    prop = actor.GetProperty()
                    if prop:
                        prop.SetAmbient(1.0)  # Voll beleuchtet
                        prop.SetDiffuse(0.0)
                        # Depth-Test aus (Objekt immer sichtbar)
                        actor.GetMapper().SetResolveCoincidentTopologyToPolygonOffset()
                        actor.GetMapper().SetRelativeCoincidentTopologyPolygonOffsetParameters(-1, -1)
        except:
            pass
        
        self._actor_names.extend([name_shaft, name_tip])
        
    def _create_plane_handle(self, axis: GizmoAxis, size: float):
        """Erstellt ein Ebenen-Handle (kleines Quadrat)"""
        offset = size * 1.5  # Abstand vom Zentrum
        
        if axis == GizmoAxis.XY:
            # Quadrat in XY-Ebene
            points = np.array([
                self.center + [offset, offset, 0],
                self.center + [offset + size, offset, 0],
                self.center + [offset + size, offset + size, 0],
                self.center + [offset, offset + size, 0],
            ])
            color = "#FFFF00"  # Gelb für XY
        elif axis == GizmoAxis.XZ:
            points = np.array([
                self.center + [offset, 0, offset],
                self.center + [offset + size, 0, offset],
                self.center + [offset + size, 0, offset + size],
                self.center + [offset, 0, offset + size],
            ])
            color = "#FF00FF"  # Magenta für XZ
        elif axis == GizmoAxis.YZ:
            points = np.array([
                self.center + [0, offset, offset],
                self.center + [0, offset + size, offset],
                self.center + [0, offset + size, offset + size],
                self.center + [0, offset, offset + size],
            ])
            color = "#00FFFF"  # Cyan für YZ
        else:
            return
            
        # Quad erstellen
        faces = np.array([[4, 0, 1, 2, 3]])
        quad = pv.PolyData(points, faces)
        
        self._pick_geometries[axis] = quad
        
        name = f"gizmo_{axis.name}_plane"
        self.plotter.add_mesh(
            quad, color=color, opacity=self.colors.plane_alpha,
            name=name, pickable=False
        )
        self._actor_names.append(name)
        
    def _create_center_sphere(self, radius: float):
        """Erstellt die zentrale Kugel für freie Bewegung - IMMER im Vordergrund"""
        sphere = pv.Sphere(radius=radius, center=self.center)
        self._pick_geometries[GizmoAxis.ALL] = sphere
        
        name = "gizmo_center"
        actor = self.plotter.add_mesh(
            sphere, color="#FFFFFF", name=name, pickable=False,
            opacity=0.9
        )
        
        # Im Vordergrund rendern
        try:
            if actor:
                prop = actor.GetProperty()
                if prop:
                    prop.SetAmbient(1.0)
                    prop.SetDiffuse(0.0)
                actor.GetMapper().SetResolveCoincidentTopologyToPolygonOffset()
                actor.GetMapper().SetRelativeCoincidentTopologyPolygonOffsetParameters(-2, -2)
        except:
            pass
            
        self._actor_names.append(name)
        
    def _create_center_cube(self, size: float):
        """Erstellt den zentralen Würfel für Uniform Scale"""
        cube = pv.Cube(center=self.center, x_length=size, y_length=size, z_length=size)
        self._pick_geometries[GizmoAxis.ALL] = cube
        
        name = "gizmo_center"
        self.plotter.add_mesh(cube, color="#AAAAAA", name=name, pickable=False)
        self._actor_names.append(name)
        
    def _create_rotation_ring(self, axis: GizmoAxis, normal: List[float], color: str, radius: float):
        """Erstellt einen Rotations-Ring"""
        # Ring als Torus mit kleinem Innenradius
        ring = pv.Disc(center=self.center, normal=normal, inner=radius * 0.9, outer=radius)
        
        self._pick_geometries[axis] = ring
        
        name = f"gizmo_{axis.name}_ring"
        self.plotter.add_mesh(ring, color=color, name=name, pickable=False)
        self._actor_names.append(name)
        
    def _create_scale_handle(self, axis: GizmoAxis, direction: List[float], color: str, length: float):
        """Erstellt einen Scale-Handle (Linie + Würfel am Ende)"""
        dir_vec = np.array(direction, dtype=float)
        
        # Linie
        line = pv.Line(self.center, self.center + dir_vec * length)
        
        # Würfel am Ende
        cube_size = length * 0.1
        cube_center = self.center + dir_vec * length
        cube = pv.Cube(center=cube_center, x_length=cube_size, y_length=cube_size, z_length=cube_size)
        
        combined = line + cube
        self._pick_geometries[axis] = combined
        
        name_line = f"gizmo_{axis.name}_line"
        name_cube = f"gizmo_{axis.name}_cube"
        
        self.plotter.add_mesh(line, color=color, line_width=2, name=name_line, pickable=False)
        self.plotter.add_mesh(cube, color=color, name=name_cube, pickable=False)
        
        self._actor_names.extend([name_line, name_cube])
        
    def _update_colors(self):
        """Aktualisiert die Farben basierend auf Hover/Active Status"""
        # Sammle welche Achsen highlighted werden sollen
        highlight_axes = set()
        
        if self.active_axis != GizmoAxis.NONE:
            highlight_axes.add(self.active_axis)
        elif self.hovered_axis != GizmoAxis.NONE:
            highlight_axes.add(self.hovered_axis)
            
        # Update alle Actor-Farben
        for name in self._actor_names:
            try:
                actor = self.plotter.renderer.actors.get(name)
                if not actor:
                    continue
                    
                # Bestimme welche Achse dieser Actor repräsentiert
                axis = None
                for ax in GizmoAxis:
                    if ax.name in name:
                        axis = ax
                        break
                        
                if axis in highlight_axes:
                    # Highlight
                    color = self.colors.selected if self.active_axis != GizmoAxis.NONE else self.colors.hover
                else:
                    # Normal
                    if "X" in name:
                        color = self.colors.x_axis
                    elif "Y" in name:
                        color = self.colors.y_axis
                    elif "Z" in name:
                        color = self.colors.z_axis
                    else:
                        color = "#AAAAAA"
                        
                # Farbe setzen
                prop = actor.GetProperty()
                if prop:
                    # Hex zu RGB
                    r = int(color[1:3], 16) / 255
                    g = int(color[3:5], 16) / 255
                    b = int(color[5:7], 16) / 255
                    prop.SetColor(r, g, b)
                    
            except Exception as e:
                pass
                
        self.plotter.render()
        
    def _ray_mesh_intersection(self, ray_origin: np.ndarray, ray_dir: np.ndarray, 
                                mesh: pv.PolyData) -> Optional[np.ndarray]:
        """Berechnet den Schnittpunkt eines Rays mit einem Mesh"""
        try:
            # Verwende PyVista's ray_trace
            points, _ = mesh.ray_trace(ray_origin, ray_origin + ray_dir * 10000)
            if len(points) > 0:
                return points[0]
        except:
            pass
        return None
