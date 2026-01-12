"""
MashCad - Transform Controller
Steuert Transform-Operationen mit Gizmo, Maus-Interaktion und Live-Preview
"""

import numpy as np
from typing import Optional, Tuple, Callable
from dataclasses import dataclass
from loguru import logger

try:
    import vtk
    HAS_VTK = True
except ImportError:
    HAS_VTK = False
    vtk = None

from PySide6.QtCore import QObject, Signal

from .transform_gizmo import TransformGizmo, GizmoMode, GizmoAxis


@dataclass
class TransformState:
    """Speichert den Zustand einer laufenden Transformation"""
    body_id: str
    mode: GizmoMode
    start_center: np.ndarray
    current_center: np.ndarray
    
    # Für Move
    total_translation: np.ndarray = None
    
    # Für Rotate
    total_rotation: np.ndarray = None  # [rx, ry, rz] in Grad
    
    # Für Scale
    total_scale: np.ndarray = None  # [sx, sy, sz]
    
    def __post_init__(self):
        if self.total_translation is None:
            self.total_translation = np.array([0.0, 0.0, 0.0])
        if self.total_rotation is None:
            self.total_rotation = np.array([0.0, 0.0, 0.0])
        if self.total_scale is None:
            self.total_scale = np.array([1.0, 1.0, 1.0])


class TransformController(QObject):
    """
    Controller für 3D Transform-Operationen.
    
    Verbindet Gizmo, Maus-Events und Body-Transformationen.
    
    Signals:
        transform_started: Wenn eine Transformation beginnt
        transform_updated: Wenn sich Werte ändern (x, y, z)
        transform_finished: Wenn Transformation abgeschlossen
        transform_cancelled: Wenn abgebrochen
    """
    
    transform_started = Signal(str, str)  # body_id, mode
    transform_updated = Signal(float, float, float)  # x, y, z values
    transform_finished = Signal(str, object)  # body_id, final_transform
    transform_cancelled = Signal()
    
    def __init__(self, viewport):
        super().__init__()
        self.viewport = viewport
        self.plotter = viewport.plotter
        
        # Gizmo erstellen
        self.gizmo = TransformGizmo(self.plotter)
        
        # Aktueller Zustand
        self.state: Optional[TransformState] = None
        self._is_dragging = False
        self._drag_start_pos: Optional[np.ndarray] = None
        self._drag_start_screen: Optional[Tuple[int, int]] = None
        
        # Callbacks für Body-Zugriff
        self._get_body_center: Optional[Callable] = None
        self._get_body_mesh: Optional[Callable] = None
        self._apply_body_transform: Optional[Callable] = None
        
        # Ghost-Preview
        self._ghost_actor_name: Optional[str] = None
        self._original_mesh = None
        
    def set_callbacks(self, get_center: Callable, get_mesh: Callable, apply_transform: Callable):
        """Setzt die Callbacks für Body-Operationen"""
        self._get_body_center = get_center
        self._get_body_mesh = get_mesh
        self._apply_body_transform = apply_transform
        
    # ==================== PUBLIC API ====================
    
    def start_transform(self, body_id: str, mode: str):
        """
        Startet eine neue Transformation.
        
        Args:
            body_id: ID des zu transformierenden Bodies
            mode: "move", "rotate" oder "scale"
        """
        # Alte Transformation beenden
        if self.state:
            self.cancel_transform()
            
        # Mode konvertieren
        gizmo_mode = {
            "move": GizmoMode.MOVE,
            "rotate": GizmoMode.ROTATE,
            "scale": GizmoMode.SCALE
        }.get(mode, GizmoMode.MOVE)
        
        # Zentrum des Bodies holen
        if self._get_body_center:
            center = self._get_body_center(body_id)
        else:
            center = np.array([0.0, 0.0, 0.0])
            
        # Zustand erstellen
        self.state = TransformState(
            body_id=body_id,
            mode=gizmo_mode,
            start_center=center.copy(),
            current_center=center.copy()
        )
        
        # Ghost-Preview erstellen
        self._create_ghost_preview(body_id)
        
        # Gizmo anzeigen
        self.gizmo.show(center, gizmo_mode)
        
        logger.info(f"Transform gestartet: {mode} auf Body {body_id}")
        self.transform_started.emit(body_id, mode)
        
    def cancel_transform(self):
        """Bricht die aktuelle Transformation ab"""
        if not self.state:
            return
        
        body_id = self.state.body_id
        
        # Actor-Transforms zurücksetzen (wichtig!)
        self._reset_actor_transforms(body_id)
            
        # Ghost entfernen
        self._remove_ghost_preview()
        
        # Gizmo verstecken
        self.gizmo.hide()
        
        # Zustand zurücksetzen
        self.state = None
        self._is_dragging = False
        
        logger.info("Transform abgebrochen")
        self.transform_cancelled.emit()
        
    def apply_transform(self) -> bool:
        """
        Wendet die aktuelle Transformation an.
        
        Returns:
            True wenn erfolgreich
        """
        if not self.state:
            return False
            
        # Transform-Daten sammeln
        if self.state.mode == GizmoMode.MOVE:
            transform_data = {
                "type": "move",
                "translation": self.state.total_translation.tolist()
            }
        elif self.state.mode == GizmoMode.ROTATE:
            transform_data = {
                "type": "rotate",
                "rotation": self.state.total_rotation.tolist(),
                "pivot": self.state.start_center.tolist()
            }
        elif self.state.mode == GizmoMode.SCALE:
            transform_data = {
                "type": "scale",
                "scale": self.state.total_scale.tolist(),
                "pivot": self.state.start_center.tolist()
            }
        else:
            return False
            
        body_id = self.state.body_id
        
        # WICHTIG: Actor-Transforms zurücksetzen BEVOR neues Mesh gerendert wird
        # Sonst wird die Transform doppelt angewendet
        self._reset_actor_transforms(body_id)
        
        # Ghost entfernen
        self._remove_ghost_preview()
        
        # Gizmo verstecken
        self.gizmo.hide()
        
        # Transform anwenden (ruft main_window auf, die das Build123d Solid transformiert)
        if self._apply_body_transform:
            success = self._apply_body_transform(body_id, transform_data)
        else:
            success = False
            
        # Zustand zurücksetzen
        self.state = None
        self._is_dragging = False
        
        if success:
            logger.success(f"Transform angewendet auf Body {body_id}")
            self.transform_finished.emit(body_id, transform_data)
        else:
            logger.error("Transform fehlgeschlagen")
            
        return success
        
    def set_values(self, x: float, y: float, z: float):
        """
        Setzt die Transform-Werte direkt (z.B. aus Input-Panel).
        """
        if not self.state:
            return
            
        if self.state.mode == GizmoMode.MOVE:
            self.state.total_translation = np.array([x, y, z])
            self.state.current_center = self.state.start_center + self.state.total_translation
            
        elif self.state.mode == GizmoMode.ROTATE:
            self.state.total_rotation = np.array([x, y, z])
            
        elif self.state.mode == GizmoMode.SCALE:
            self.state.total_scale = np.array([x, y, z])
            
        # Preview und Gizmo aktualisieren
        self._update_preview()
        
        if self.state.mode == GizmoMode.MOVE:
            self.gizmo.update_position(self.state.current_center)
            
    def get_values(self) -> Tuple[float, float, float]:
        """Gibt die aktuellen Transform-Werte zurück"""
        if not self.state:
            return (0.0, 0.0, 0.0)
            
        if self.state.mode == GizmoMode.MOVE:
            return tuple(self.state.total_translation)
        elif self.state.mode == GizmoMode.ROTATE:
            return tuple(self.state.total_rotation)
        elif self.state.mode == GizmoMode.SCALE:
            return tuple(self.state.total_scale)
            
        return (0.0, 0.0, 0.0)
        
    # ==================== MOUSE EVENTS ====================
    
    def on_mouse_press(self, pos: Tuple[int, int], button: int) -> bool:
        """
        Verarbeitet Mausklick.
        
        Returns:
            True wenn das Event konsumiert wurde
        """
        if not self.state or button != 1:  # Nur Linksklick
            return False
            
        # Ray von Mausposition
        ray_origin, ray_dir = self._get_ray_from_screen(pos)
        
        if ray_origin is None:
            return False
        
        # Prüfen ob Gizmo getroffen
        hit_axis = self.gizmo.pick(ray_origin, ray_dir)
        
        if hit_axis != GizmoAxis.NONE:
            # Drag starten
            self._is_dragging = True
            self._drag_start_screen = pos
            self._drag_start_pos = self._project_to_constraint(ray_origin, ray_dir, hit_axis)
            self.gizmo.set_active(hit_axis)
            logger.debug(f"Transform Drag gestartet: Achse={hit_axis.name}")
            return True
            
        return False
        
    def on_mouse_move(self, pos: Tuple[int, int]) -> bool:
        """
        Verarbeitet Mausbewegung.
        
        Returns:
            True wenn das Event konsumiert wurde
        """
        if not self.state:
            return False
            
        ray_origin, ray_dir = self._get_ray_from_screen(pos)
        
        if ray_origin is None:
            return False
        
        if self._is_dragging:
            # Drag fortsetzen
            current_pos = self._project_to_constraint(
                ray_origin, ray_dir, self.gizmo.active_axis
            )
            
            if current_pos is not None and self._drag_start_pos is not None:
                delta = current_pos - self._drag_start_pos
                
                # Nur updaten wenn signifikantes Delta
                if np.linalg.norm(delta) > 0.001:
                    self._apply_drag_delta(delta)
                    self._drag_start_pos = current_pos
                
            return True
        else:
            # Hover-Check
            hit_axis = self.gizmo.pick(ray_origin, ray_dir)
            self.gizmo.set_hover(hit_axis)
            
        return False
        
    def on_mouse_release(self, pos: Tuple[int, int], button: int) -> bool:
        """
        Verarbeitet Maus-Loslassen.
        
        Returns:
            True wenn das Event konsumiert wurde
        """
        if not self.state or button != 1:
            return False
            
        if self._is_dragging:
            self._is_dragging = False
            self._drag_start_pos = None
            self._drag_start_screen = None
            self.gizmo.set_active(GizmoAxis.NONE)
            logger.debug("Transform Drag beendet")
            return True
            
        return False
        
    # ==================== PRIVATE METHODS ====================
    
    def _get_ray_from_screen(self, screen_pos: Tuple[int, int]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Berechnet den Ray von einer Bildschirmposition"""
        try:
            x, y = screen_pos
            
            # Renderer und Kamera holen
            renderer = self.plotter.renderer
            camera = renderer.GetActiveCamera()
            
            # Bildschirmhöhe für Y-Inversion
            height = self.plotter.interactor.height()
            y_flipped = height - y
            
            # World-Koordinaten am Near und Far Plane
            renderer.SetDisplayPoint(x, y_flipped, 0)  # Near
            renderer.DisplayToWorld()
            near_point = np.array(renderer.GetWorldPoint()[:3])
            
            renderer.SetDisplayPoint(x, y_flipped, 1)  # Far
            renderer.DisplayToWorld()
            far_point = np.array(renderer.GetWorldPoint()[:3])
            
            # Ray-Richtung
            direction = far_point - near_point
            direction = direction / np.linalg.norm(direction)
            
            return near_point, direction
            
        except Exception as e:
            logger.warning(f"Ray-Berechnung fehlgeschlagen: {e}")
            return None, None
            
    def _project_to_constraint(self, ray_origin: np.ndarray, ray_dir: np.ndarray, 
                                axis: GizmoAxis) -> Optional[np.ndarray]:
        """Projiziert den Ray auf die Constraint-Achse oder -Ebene"""
        if axis == GizmoAxis.NONE:
            return None
            
        # Prüfe ob es eine Achsen- oder Ebenen-Constraint ist
        direction = self.gizmo.get_constraint_direction()
        
        if direction is not None:
            # Achsen-Constraint: Projiziere auf Linie
            return self._ray_line_closest_point(
                ray_origin, ray_dir,
                self.state.current_center, direction
            )
        else:
            # Ebenen-Constraint: Projiziere auf Ebene
            plane = self.gizmo.get_constraint_plane()
            if plane:
                return self._ray_plane_intersection(ray_origin, ray_dir, plane[0], plane[1])
                
        return None
        
    def _ray_line_closest_point(self, ray_origin: np.ndarray, ray_dir: np.ndarray,
                                 line_point: np.ndarray, line_dir: np.ndarray) -> np.ndarray:
        """Findet den nächsten Punkt auf einer Linie zum Ray"""
        # Normalisieren
        ray_dir = ray_dir / np.linalg.norm(ray_dir)
        line_dir = line_dir / np.linalg.norm(line_dir)
        
        # Vektor zwischen Punkten
        w = ray_origin - line_point
        
        a = np.dot(ray_dir, ray_dir)
        b = np.dot(ray_dir, line_dir)
        c = np.dot(line_dir, line_dir)
        d = np.dot(ray_dir, w)
        e = np.dot(line_dir, w)
        
        denom = a * c - b * b
        if abs(denom) < 1e-10:
            # Linien parallel
            return line_point
            
        t = (b * e - c * d) / denom
        s = (a * e - b * d) / denom
        
        # Punkt auf der Constraint-Linie
        return line_point + s * line_dir
        
    def _ray_plane_intersection(self, ray_origin: np.ndarray, ray_dir: np.ndarray,
                                 plane_point: np.ndarray, plane_normal: np.ndarray) -> Optional[np.ndarray]:
        """Berechnet den Schnittpunkt von Ray und Ebene"""
        denom = np.dot(ray_dir, plane_normal)
        if abs(denom) < 1e-10:
            return None
            
        t = np.dot(plane_point - ray_origin, plane_normal) / denom
        if t < 0:
            return None
            
        return ray_origin + t * ray_dir
        
    def _apply_drag_delta(self, delta: np.ndarray):
        """Wendet ein Drag-Delta auf die Transformation an"""
        if not self.state:
            return
            
        axis = self.gizmo.active_axis
        
        if self.state.mode == GizmoMode.MOVE:
            # Delta zur Translation addieren - NUR auf der aktiven Achse
            if axis == GizmoAxis.X:
                self.state.total_translation[0] += delta[0]
            elif axis == GizmoAxis.Y:
                self.state.total_translation[1] += delta[1]
            elif axis == GizmoAxis.Z:
                self.state.total_translation[2] += delta[2]
            elif axis in [GizmoAxis.XY, GizmoAxis.XZ, GizmoAxis.YZ, GizmoAxis.ALL]:
                self.state.total_translation += delta
                
            self.state.current_center = self.state.start_center + self.state.total_translation
            self.gizmo.update_position(self.state.current_center)
            
        elif self.state.mode == GizmoMode.ROTATE:
            # Delta als Winkeländerung interpretieren
            sensitivity = 0.5  # Grad pro Pixel/Unit
            if axis == GizmoAxis.X:
                self.state.total_rotation[0] += delta[1] * sensitivity
            elif axis == GizmoAxis.Y:
                self.state.total_rotation[1] += delta[0] * sensitivity
            elif axis == GizmoAxis.Z:
                self.state.total_rotation[2] += delta[0] * sensitivity
                
        elif self.state.mode == GizmoMode.SCALE:
            # Delta als Scale-Faktor
            sensitivity = 0.01
            if axis == GizmoAxis.X:
                self.state.total_scale[0] += delta[0] * sensitivity
            elif axis == GizmoAxis.Y:
                self.state.total_scale[1] += delta[1] * sensitivity
            elif axis == GizmoAxis.Z:
                self.state.total_scale[2] += delta[2] * sensitivity
            elif axis == GizmoAxis.ALL:
                uniform = np.linalg.norm(delta) * sensitivity
                self.state.total_scale += uniform
                
            # Scale nicht negativ werden lassen
            self.state.total_scale = np.maximum(self.state.total_scale, 0.01)
            
        # Preview aktualisieren
        self._update_preview()
        
        # Signal für UI-Update
        vals = self.get_values()
        self.transform_updated.emit(vals[0], vals[1], vals[2])
        
    def _create_ghost_preview(self, body_id: str):
        """Erstellt eine transparente Kopie des Bodies als Ghost"""
        if not self._get_body_mesh:
            return
            
        mesh = self._get_body_mesh(body_id)
        if mesh is None:
            return
            
        self._original_mesh = mesh.copy()
        
        # Ghost rendern (transparent, Wireframe)
        self._ghost_actor_name = f"transform_ghost_{body_id}"
        self.plotter.add_mesh(
            self._original_mesh,
            color="#AAAAAA",
            opacity=0.3,
            style="wireframe",
            name=self._ghost_actor_name,
            pickable=False
        )
        
    def _remove_ghost_preview(self):
        """Entfernt den Ghost-Preview"""
        if self._ghost_actor_name:
            try:
                self.plotter.remove_actor(self._ghost_actor_name)
            except:
                pass
            self._ghost_actor_name = None
        self._original_mesh = None
        
    def _update_preview(self):
        """Aktualisiert die visuelle Preview der Transformation"""
        if not self.state:
            return
            
        body_id = self.state.body_id
        
        try:
            # ALLE Body-Actors finden und bewegen (Mesh + Edges)
            if body_id in self.viewport._body_actors:
                actors = self.viewport._body_actors[body_id]
                
                for actor_name in actors:
                    actor = self.plotter.renderer.actors.get(actor_name)
                    if not actor:
                        continue
                        
                    if self.state.mode == GizmoMode.MOVE:
                        # Translation relativ zur Startposition
                        t = self.state.total_translation
                        
                        # WICHTIG: Neues Transform-Objekt erstellen
                        # (nicht akkumulieren, sondern absolut setzen)
                        transform = vtk.vtkTransform()
                        transform.Identity()
                        transform.Translate(t[0], t[1], t[2])
                        actor.SetUserTransform(transform)
                        
                    elif self.state.mode == GizmoMode.ROTATE:
                        r = self.state.total_rotation
                        pivot = self.state.start_center
                        transform = vtk.vtkTransform()
                        transform.Identity()
                        transform.Translate(pivot[0], pivot[1], pivot[2])
                        transform.RotateX(r[0])
                        transform.RotateY(r[1])
                        transform.RotateZ(r[2])
                        transform.Translate(-pivot[0], -pivot[1], -pivot[2])
                        actor.SetUserTransform(transform)
                        
                    elif self.state.mode == GizmoMode.SCALE:
                        s = self.state.total_scale
                        pivot = self.state.start_center
                        transform = vtk.vtkTransform()
                        transform.Identity()
                        transform.Translate(pivot[0], pivot[1], pivot[2])
                        transform.Scale(s[0], s[1], s[2])
                        transform.Translate(-pivot[0], -pivot[1], -pivot[2])
                        actor.SetUserTransform(transform)
                        
            self.plotter.render()
            
        except Exception as e:
            logger.warning(f"Preview-Update fehlgeschlagen: {e}")
            
    def _reset_actor_transforms(self, body_id: str):
        """Setzt alle Actor-Transforms zurück (für Cancel)"""
        try:
            if body_id in self.viewport._body_actors:
                actors = self.viewport._body_actors[body_id]
                for actor_name in actors:
                    actor = self.plotter.renderer.actors.get(actor_name)
                    if actor:
                        actor.SetUserTransform(None)
            self.plotter.render()
        except Exception as e:
            logger.warning(f"Reset fehlgeschlagen: {e}")
