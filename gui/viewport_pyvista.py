"""
MashCad - PyVista 3D Viewport
V3.0: Modular mit Mixins für bessere Wartbarkeit
"""

import math
import numpy as np
from typing import Optional, List, Tuple, Dict, Any
import uuid
from loguru import logger
from gui.geometry_detector import GeometryDetector
import time

# Mixins importieren
from gui.viewport.extrude_mixin import ExtrudeMixin
from gui.viewport.picking_mixin import PickingMixin
from gui.viewport.body_mixin import BodyRenderingMixin
from gui.viewport.transform_mixin_v3 import TransformMixinV3
from gui.viewport.edge_selection_mixin import EdgeSelectionMixin
from gui.viewport.section_view_mixin import SectionViewMixin

from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame, QLabel, QToolButton
from PySide6.QtCore import Qt, Signal, QTimer, QEvent, QPoint
from PySide6.QtGui import QCursor, QColor

# ==================== IMPORTS ====================
HAS_PYVISTA = False
try:
    import pyvista as pv
    from pyvistaqt import QtInteractor
    import vtk 
    HAS_PYVISTA = True
    logger.success("PyVista & VTK erfolgreich geladen.")
except ImportError as e:
    logger.error(f"PyVista Import-Fehler: {e}")

HAS_BUILD123D = False
try:
    import build123d
    HAS_BUILD123D = True
except ImportError:
    pass

HAS_SHAPELY = False
try:
    from shapely.geometry import LineString, Polygon, Point
    from shapely.ops import polygonize, unary_union, triangulate
    HAS_SHAPELY = True
except ImportError:
    pass


class OverlayHomeButton(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText("🏠")
        self.setFixedSize(32, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Standardansicht (Home)")
        self.setStyleSheet("""
            QToolButton {
                background-color: rgba(60, 60, 60, 180);
                color: #e0e0e0;
                border: 1px solid rgba(100, 100, 100, 100);
                border-radius: 4px;
                font-size: 16px;
            }
            QToolButton:hover {
                background-color: rgba(0, 120, 212, 230);
                border: 1px solid #0078d4;
                color: white;
            }
        """)


class PyVistaViewport(QWidget, ExtrudeMixin, PickingMixin, BodyRenderingMixin, TransformMixinV3, EdgeSelectionMixin, SectionViewMixin):
    view_changed = Signal()
    plane_clicked = Signal(str)
    custom_plane_clicked = Signal(tuple, tuple)
    extrude_requested = Signal(list, float, str)
    height_changed = Signal(float)
    face_selected = Signal(int)
    transform_changed = Signal(float, float, float) # für UI-Panel Update
    clicked_3d_point = Signal(int, tuple) # body_id, (x,y,z)
    body_clicked = Signal(str)  # body_id - NEU: Für pending transform mode (Fix 1)
    body_transform_requested = Signal(str, str, object)  # body_id, mode, data
    body_copy_requested = Signal(str, str, object)  # body_id, mode, data - Kopiert Body und transformiert
    body_mirror_requested = Signal(str, str)  # body_id, plane (XY/XZ/YZ)
    mirror_requested = Signal(str)  # body_id - Öffnet Mirror-Dialog
    point_to_point_move = Signal(str, tuple, tuple)  # body_id, start_point, end_point - NEU: Point-to-Point Move
    edge_selection_changed = Signal(int)  # NEU: Anzahl selektierter Kanten für Fillet/Chamfer
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._viewcube_created = False  # VOR _setup_plotter initialisieren

        # NEU: Referenz auf zentrale TransformState (wird später von MainWindow gesetzt)
        self.transform_state = None

        # Dunkler Hintergrund für das Widget selbst
        self.setStyleSheet("background-color: #1e1e1e;")
        self.setAutoFillBackground(True)

        self._setup_ui()
        
        if HAS_PYVISTA:
            self._setup_plotter()
            self._setup_scene()
        
        # State
        self.sketches = []
        self.bodies = {} 
        self.detected_faces = []
        self.active_selection_filter = GeometryDetector.SelectionFilter.ALL
        self.selected_faces = set()
        self.hovered_face = -1
        self.hovered_body_face = None  # (body_id, cell_id, normal, position)
        self.body_face_extrude = None  # Für Extrusion von Body-Flächen
        
        # Modes
        self.plane_select_mode = False
        self.extrude_mode = False

        # Edge Selection Mixin initialisieren
        self._init_edge_selection()

        # Section View Mixin initialisieren
        self._init_section_view()

        self.pending_transform_mode = False  # NEU: Für Body-Highlighting
        self.point_to_point_mode = False  # NEU: Point-to-Point Move (wie Fusion 360)
        self.point_to_point_start = None  # Erster ausgewählter Punkt (x, y, z)
        self.point_to_point_body_id = None  # Body, der verschoben wird
        self.extrude_height = 0.0
        self.extrude_operation = "New Body"  # NEU: Aktuelle Operation für Farbe
        self.is_dragging = False
        self.drag_start_pos = QPoint()
        self.drag_start_height = 0.0

        # ✅ FIX: Track last picked body for sketch targeting
        self._last_picked_body_id = None
        
        # Tracking
        self._sketch_actors = []
        self._body_actors = {}
        self._plane_actors = {}
        self._face_actors = []
        self._preview_actor = None
        self.last_highlighted_plane = None
        self.detector = GeometryDetector()
        self.selected_face_ids = set()
        self.hover_face_id = None
        self.hover_body_id = None  # NEU: Für Body-Highlighting im pending transform mode
        
        self.setFocusPolicy(Qt.StrongFocus)
        
        self.transform_actor = None # Der Actor der gerade transformiert wird
        self.transform_widget = None # Das Gizmo
        self.original_matrix = None # Zum Zurücksetzen
        self._last_pick_time = 0
        self._pick_interval = 0.05 # 2ß Checks pro Sekunde

    def set_selection_mode(self, mode: str):
        """Übersetzt den String-Modus aus dem MainWindow in Detector-Filter."""
        from gui.geometry_detector import GeometryDetector
        
        mapping = {
            "face": GeometryDetector.SelectionFilter.FACE,
            "hole": GeometryDetector.SelectionFilter.HOLE,
            "sketch": GeometryDetector.SelectionFilter.SKETCH,
            "all": GeometryDetector.SelectionFilter.ALL
        }
        # Setzt den aktiven Filter für den Detector
        self.active_selection_filter = mapping.get(mode, GeometryDetector.SelectionFilter.ALL)
        
        # Visuelles Feedback: Hover zurücksetzen
        self._update_hover(-1)
        self.plotter.render()
        
    def _setup_ui(self):
        # Direktes Layout ohne zusätzlichen Frame
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        if not HAS_PYVISTA:
            self.main_layout.addWidget(QLabel("PyVista fehlt! Installiere: pip install pyvista pyvistaqt"))
            return
            
    def on_mouse_move(self, event):
        """CAD-typisches Hover / Preselect"""
        current_time = time.time()
        if (current_time - self._last_pick_time < self._pick_interval):
            return 
            
        self._last_pick_time = current_time

        pos = event.position() if hasattr(event, 'position') else event.pos()
        x, y = int(pos.x()), int(pos.y())

        #ray_origin, ray_dir = self.get_ray_from_click(x, y)

        # WICHTIG: Nutze self.pick statt self.detector.pick
        face_id = self.pick(x, y, selection_filter=self.active_selection_filter) # <-- NEU: x, y übergeben

        if face_id != self.hover_face_id:
            self._update_hover(face_id)
    
    
    def _update_hover(self, face_id):
        """
        Aktualisiert den Hover-Status und zeichnet die Szene neu.
        Nutzt jetzt die optimierte _draw_selectable_faces_from_detector Methode.
        """
        if face_id == getattr(self, 'hover_face_id', -1):
            return

        self.hover_face_id = face_id
        
        # Zeichnen aktualisieren (das kümmert sich jetzt um Hover UND Selection)
        self._draw_selectable_faces_from_detector()
        
    def _set_face_highlight(self, face_id, state):
        face = next(
            (f for f in self.detector.selection_faces if f.id == face_id),
            None
        )
        if not face or not face.display_mesh:
            return

        if state:
            self.add_mesh(
                face.display_mesh,
                name=f"hover_{face_id}",
                opacity=0.4,
                pickable=False
            )
        else:
            self.remove_actor(f"hover_{face_id}")
    
    def _setup_plotter(self):
        self._drag_screen_vector = np.array([1.0, 0.0])
        
        # QtInteractor erstellen
        self.plotter = QtInteractor(self)
        self.plotter.interactor.setStyleSheet("background-color: #262626;")
        self.main_layout.addWidget(self.plotter.interactor)
        
        # --- PERFORMANCE & FIX START ---
        # Hier lag der Absturz. Wir machen das jetzt robust für alle Versionen.
        if hasattr(self.plotter, 'iren'):
            try:
                # Versuch 1: PyVista Style (snake_case) - Wahrscheinlich deine Version
                self.plotter.iren.set_desired_update_rate(60.0)
            except AttributeError:
                try:
                    # Versuch 2: VTK Style (CamelCase) - Fallback
                    self.plotter.iren.SetDesiredUpdateRate(60.0)
                except AttributeError:
                    # Wenn beides fehlt, ist es nicht kritisch, nur weniger optimiert.
                    pass
        
        # Events
        self.plotter.interactor.setMouseTracking(True)
        self.plotter.interactor.installEventFilter(self)
        
        # Kamera-Stil
        self.plotter.enable_trackball_style()

        # --- VISUAL QUALITÄT ---
        # Hintergrund
        self.plotter.set_background('#1e1e1e', top='#2d2d30')
        
        # WICHTIG: FXAA macht Linien unscharf. Für CAD nutzen wir lieber MSAA (Multi-Sampling).
        # Das kostet minimal mehr GPU, sieht aber bei Drahtgittermodellen viel besser aus.
        if hasattr(self.plotter, 'ren_win') and hasattr(self.plotter.ren_win, 'SetMultiSamples'):
            self.plotter.ren_win.SetMultiSamples(4) # 4x oder 8x Glättung
        else:
            # Fallback falls MSAA nicht geht
            try: self.plotter.enable_anti_aliasing('fxaa')
            except: pass
        # --- PERFORMANCE & FIX END ---

        # UI Cleanup: Entferne Standard-Achsen
        try: self.plotter.hide_axes()
        except: pass
        
        # ViewCube Widget
        try:
            widget = self.plotter.add_camera_orientation_widget()
            if widget:
                try:
                    rep = widget.GetRepresentation()
                    if hasattr(rep, 'SetLabelText'):
                        # Beschriftungen setzen
                        labels = ["RECHTS", "LINKS", "HINTEN", "VORNE", "OBEN", "UNTEN"]
                        for i, text in enumerate(labels):
                            rep.SetLabelText(i, text)
                except:
                    pass 
                self._cam_widget = widget
        except Exception as e:
            logger.warning(f"ViewCube creation warning: {e}")
        
        # Home Button Overlay
        self.btn_home = OverlayHomeButton(self)
        self.btn_home.clicked.connect(self._reset_camera_animated)
        self.btn_home.move(20, 20)
        self.btn_home.raise_()
        self.btn_home.show()
        
        self._viewcube_created = True
        
        # Observer für View-Changes
        try:
            if hasattr(self.plotter, 'iren') and self.plotter.iren:
                self.plotter.iren.AddObserver('EndInteractionEvent', lambda o,e: self.view_changed.emit())
        except: pass
    
    def _reset_camera_animated(self):
        self.plotter.view_isometric()
        self.plotter.reset_camera()
        self.view_changed.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Home-Button immer oben links halten
        if hasattr(self, 'btn_home'):
            self.btn_home.move(20, 20)
            self.btn_home.raise_()  # Nach vorne bringen

    def _setup_scene(self):
        self._draw_grid(200)
        self._draw_axes(50)
        self.plotter.camera_position = 'iso'
        self.plotter.reset_camera()
        
    def _calculate_plane_axes(self, normal_vec):
        n = np.array(normal_vec)
        norm = np.linalg.norm(n)
        if norm == 0: return (1,0,0), (0,1,0)
        n = n / norm
        
        if abs(n[2]) > 0.999:
            x_dir = np.array([1.0, 0.0, 0.0])
            y_dir = np.cross(n, x_dir)
            y_dir = y_dir / np.linalg.norm(y_dir)
            x_dir = np.cross(y_dir, n)
        else:
            global_up = np.array([0.0, 0.0, 1.0])
            x_dir = np.cross(global_up, n)
            x_dir = x_dir / np.linalg.norm(x_dir)
            y_dir = np.cross(n, x_dir)
            y_dir = y_dir / np.linalg.norm(y_dir)
            
        # WICHTIG: Dies hat gefehlt!
        return tuple(x_dir), tuple(y_dir)
        
    # start_transform ist jetzt im TransformMixin definiert
        
    def select_body_at(self, x, y):
        """Picking Logik für Bodies"""
        import vtk
        picker = vtk.vtkCellPicker()
        picker.Pick(x, self.plotter.interactor.height()-y, 0, self.plotter.renderer)
        actor = picker.GetActor()
        
        if actor:
            for bid, actors in self._body_actors.items():
                # FIX: Prüfen ob der getroffene Actor zu IRGENDEINEM Teil des Bodies gehört
                for name in actors:
                    if self.plotter.renderer.actors.get(name) == actor:
                        return bid
        return None

    def highlight_body(self, body_id: str):
        """Hebt einen Body farblich hervor (für pending transform mode)"""
        if not body_id or body_id not in self._body_actors:
            return

        # Ändere die Farbe des Body-Meshes zu einem hellen Blau
        mesh_name = f"body_{body_id}_m"
        try:
            actor = self.plotter.renderer.actors.get(mesh_name)
            if actor:
                actor.GetProperty().SetColor(0.4, 0.7, 1.0)  # Helles Blau
                actor.GetProperty().SetOpacity(0.8)
                self.plotter.render()
        except Exception as e:
            logger.debug(f"Konnte Body {body_id} nicht highlighten: {e}")

    def unhighlight_body(self, body_id: str):
        """Entfernt das Highlighting von einem Body"""
        if not body_id or body_id not in self._body_actors:
            return

        # Setze die Farbe zurück auf Standard
        mesh_name = f"body_{body_id}_m"
        try:
            actor = self.plotter.renderer.actors.get(mesh_name)
            if actor:
                # Standard-Farbe (grau)
                actor.GetProperty().SetColor(0.6, 0.6, 0.8)
                actor.GetProperty().SetOpacity(1.0)
                self.plotter.render()
        except Exception as e:
            logger.debug(f"Konnte Body {body_id} nicht unhighlighten: {e}")

    def set_pending_transform_mode(self, active: bool):
        """Aktiviert/deaktiviert den pending transform mode für Body-Highlighting"""
        self.pending_transform_mode = active
        if not active and self.hover_body_id:
            # Highlighting zurücksetzen wenn mode endet
            self.unhighlight_body(self.hover_body_id)
            self.hover_body_id = None
        logger.debug(f"Pending transform mode: {active}")

    def pick_point_on_geometry(self, screen_x: int, screen_y: int, snap_to_vertex: bool = True, log_pick: bool = True):
        """
        Picked einen 3D-Punkt auf der Geometrie (Fusion 360-Style).
        Gibt (body_id, point) zurück oder (None, None) wenn nichts getroffen.

        Args:
            screen_x, screen_y: Screen-Koordinaten
            snap_to_vertex: Wenn True, snapped auf nächstgelegenen Vertex (Fusion-Style)
            log_pick: Wenn False, kein Debug-Logging (für hover performance)

        Returns:
            (body_id, point) oder (None, None)
        """
        import vtk
        import numpy as np

        picker = vtk.vtkCellPicker()
        picker.SetTolerance(0.005)

        # Pick durchführen
        picker.Pick(screen_x, self.plotter.interactor.height() - screen_y, 0, self.plotter.renderer)

        # Prüfe ob etwas getroffen wurde
        actor = picker.GetActor()
        if not actor:
            return None, None

        # Finde Body-ID
        body_id = None
        for bid, actors in self._body_actors.items():
            for name in actors:
                if self.plotter.renderer.actors.get(name) == actor:
                    body_id = bid
                    break
            if body_id:
                break

        if not body_id:
            return None, None

        # Hole den genauen 3D-Punkt
        picked_point = picker.GetPickPosition()
        point = np.array([picked_point[0], picked_point[1], picked_point[2]])

        # SNAP TO VERTEX (Fusion 360-Style)
        if snap_to_vertex:
            mesh_name = f"body_{body_id}_m"
            mesh_actor = self.plotter.renderer.actors.get(mesh_name)
            if mesh_actor:
                mapper = mesh_actor.GetMapper()
                if mapper:
                    polydata = mapper.GetInput()
                    points = polydata.GetPoints()

                    # Finde nächstgelegenen Vertex
                    min_dist = float('inf')
                    nearest_vertex = None
                    snap_threshold = 5.0  # 5 Einheiten max

                    for i in range(points.GetNumberOfPoints()):
                        vertex = np.array(points.GetPoint(i))
                        dist = np.linalg.norm(point - vertex)
                        if dist < min_dist and dist < snap_threshold:
                            min_dist = dist
                            nearest_vertex = vertex

                    if nearest_vertex is not None:
                        point = nearest_vertex
                        if log_pick:  # Nur loggen wenn explizit gewünscht
                            logger.debug(f"Snapped to vertex (dist={min_dist:.2f})")

        point_tuple = (float(point[0]), float(point[1]), float(point[2]))
        if log_pick:  # Nur loggen wenn explizit gewünscht
            logger.debug(f"Picked point: {point_tuple} on body {body_id}")
        return body_id, point_tuple

    def start_point_to_point_mode(self, body_id: str):
        """Startet den Point-to-Point Move Modus für einen Body"""
        self.point_to_point_mode = True
        self.point_to_point_start = None
        self.point_to_point_body_id = body_id
        self.setCursor(Qt.CrossCursor)
        logger.info("Point-to-Point Mode: Wähle Start-Punkt auf Geometrie")

    def cancel_point_to_point_mode(self):
        """Bricht den Point-to-Point Modus ab"""
        self.point_to_point_mode = False
        self.point_to_point_start = None
        self.point_to_point_body_id = None
        self.setCursor(Qt.ArrowCursor)
        # Entferne ALLE Visualisierungen
        self.plotter.remove_actor("p2p_start_marker", render=False)
        self.plotter.remove_actor("p2p_hover_marker", render=False)
        self.plotter.remove_actor("p2p_line", render=True)
        logger.info("Point-to-Point Mode abgebrochen")

    def highlight_edge(self, p1, p2):
        """Zeichnet eine rote Linie (genutzt für Fillet/Chamfer Vorschau)"""
        import uuid
        import pyvista as pv
        
        # Linie erstellen
        line = pv.Line(p1, p2)
        
        # Eindeutigen Namen generieren, damit wir mehrere Linien haben können
        name = f"highlight_{uuid.uuid4()}"
        
        self.plotter.add_mesh(line, color='red', line_width=5, name=name)

    def clear_highlight(self):
        """Entfernt alle Highlight-Linien"""
        # Suche alle Actors, die mit "highlight_" beginnen
        to_remove = [name for name in self.plotter.renderer.actors.keys() if name.startswith("highlight_")]
        
        for name in to_remove:
            self.plotter.remove_actor(name)
            
        # Zur Sicherheit Rendern
        self.plotter.render()
        
    # Transform-Methoden sind jetzt im TransformMixin
    # (start_transform, end_transform, apply_transform_values, etc.)

    def get_current_transform_matrix(self):
        """Gibt die aktuelle Matrix des transformierten Objekts zurück (für Apply)"""
        if hasattr(self, '_transform_controller') and self._transform_controller.state:
            vals = self._transform_controller.get_values()
            # Einfache 4x4 Identity mit Translation
            return [
                [1, 0, 0, vals[0]],
                [0, 1, 0, vals[1]],
                [0, 0, 1, vals[2]],
                [0, 0, 0, 1]
            ]
        return None
        
    def _draw_grid(self, size=200, spacing=10):
        try: self.plotter.remove_actor('grid_main')
        except: pass
        n_lines = int(size/spacing)+1
        lines = []
        h = size/2
        for i in range(n_lines):
            p = -h + i*spacing
            lines.append(pv.Line((-h, p, 0), (h, p, 0)))
            lines.append(pv.Line((p, -h, 0), (p, h, 0)))
        if lines:
            grid = pv.MultiBlock(lines).combine()
            self.plotter.add_mesh(grid, color='#3a3a3a', line_width=1, name='grid_main', pickable=False)
    
    def _cache_drag_direction_for_face_v2(self, face):
        """
        Berechnet den 2D-Bildschirmvektor UND speichert den 3D-Ankerpunkt
        für korrekte Skalierung.
        """
        try:
            # 1. Normale und Zentrum holen
            normal = np.array(face.plane_normal, dtype=float)
            if np.linalg.norm(normal) < 1e-6: normal = np.array([0,0,1], dtype=float)
            
            if face.domain_type == 'body_face':
                 center = np.array(face.plane_origin, dtype=float)
            else:
                 poly = face.shapely_poly
                 c2d = poly.centroid
                 ox, oy, oz = face.plane_origin
                 ux, uy, uz = face.plane_x
                 vx, vy, vz = face.plane_y
                 center = np.array([
                     ox + c2d.x * ux + c2d.y * vx,
                     oy + c2d.x * uy + c2d.y * vy,
                     oz + c2d.x * uz + c2d.y * vz
                 ], dtype=float)

            # WICHTIG: 3D-Punkt für Skalierungsberechnung merken!
            self._drag_anchor_3d = center

            # 2. Vektor im Screen-Space berechnen
            renderer = self.plotter.renderer
            
            def to_screen(pt_3d):
                renderer.SetWorldPoint(pt_3d[0], pt_3d[1], pt_3d[2], 1.0)
                renderer.WorldToDisplay()
                disp = renderer.GetDisplayPoint()
                return np.array([disp[0], disp[1]])

            p1 = to_screen(center)
            p2 = to_screen(center + normal * 10.0) # Testpunkt in Extrude-Richtung
            
            vec = p2 - p1
            # Y-Achsen korrektur (VTK vs Qt)
            vec[1] = -vec[1] 

            length = np.linalg.norm(vec)
            
            if length < 1.0:
                self._drag_screen_vector = np.array([0.0, -1.0])
            else:
                self._drag_screen_vector = vec / length
                
        except Exception as e:
            logger.error(f" {e}")
            self._drag_screen_vector = np.array([0.0, -1.0])
            self._drag_anchor_3d = np.array([0,0,0])

    def _get_pixel_to_world_scale(self, anchor_point_3d):
        """
        Berechnet, wie viele 'Welt-Einheiten' ein Pixel an der Position
        des Objekts entspricht. Löst das Problem 'manchmal schnell, manchmal langsam'.
        """
        if anchor_point_3d is None: return 0.1
        
        try:
            renderer = self.plotter.renderer
            
            # Projektion des Ankerpunkts
            renderer.SetWorldPoint(*anchor_point_3d, 1.0)
            renderer.WorldToDisplay()
            p1_disp = renderer.GetDisplayPoint()
            
            # Wir gehen 100 Pixel zur Seite im Screen Space (beliebiger Wert > 0)
            p2_disp_x = p1_disp[0] + 100.0
            p2_disp_y = p1_disp[1]
            p2_disp_z = p1_disp[2] # Gleiche Tiefe (Z-Buffer Wert) behalten!
            
            # Zurück in World Space
            renderer.SetDisplayPoint(p2_disp_x, p2_disp_y, p2_disp_z)
            renderer.DisplayToWorld()
            world_pt = renderer.GetWorldPoint()
            
            if world_pt[3] != 0:
                p2_world = np.array(world_pt[:3]) / world_pt[3]
            else:
                p2_world = np.array(world_pt[:3])

            # Distanz in Welt-Einheiten
            dist_world = np.linalg.norm(p2_world - anchor_point_3d)
            
            # Faktor: Welt-Einheiten pro Pixel
            # Wenn 100 Pixel = 50mm sind, ist Faktor 0.5
            if dist_world == 0: return 0.1
            return dist_world / 100.0
            
        except Exception:
            return 0.1
    
    def is_body_visible(self, body_id):
        if body_id not in self._body_actors: return False
        try:
            actors = self._body_actors[body_id]
            if not actors: return False
            mesh_name = actors[0] # Wir prüfen Visibility am Mesh
            actor = self.plotter.renderer.actors.get(mesh_name)
            if actor: return bool(actor.GetVisibility())
        except: pass
        return False
        
    def _draw_axes(self, length=50):
        try:
            self.plotter.remove_actor('axis_x_org')
            self.plotter.remove_actor('axis_y_org')
            self.plotter.remove_actor('axis_z_org')
        except: pass
        self.plotter.add_mesh(pv.Line((0,0,0),(length,0,0)), color='#ff4444', line_width=3, name='axis_x_org')
        self.plotter.add_mesh(pv.Line((0,0,0),(0,length,0)), color='#44ff44', line_width=3, name='axis_y_org')
        self.plotter.add_mesh(pv.Line((0,0,0),(0,0,length)), color='#4444ff', line_width=3, name='axis_z_org')

    # ==================== EVENT FILTER ====================
    def eventFilter(self, obj, event):
        if not HAS_PYVISTA: return False
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtWidgets import QApplication
        
        # --- TRANSFORM MODE (Onshape-Style Gizmo V2) ---
        if self.is_transform_active():
            event_type = event.type()
            
            # Nur Mouse-Events haben position()
            if event_type in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseMove):
                pos = event.position() if hasattr(event, 'position') else event.pos()
                screen_pos = (int(pos.x()), int(pos.y()))
                
                if event_type == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                    if self.handle_transform_mouse_press(screen_pos):
                        return True
                        
                elif event_type == QEvent.MouseMove:
                    if self.handle_transform_mouse_move(screen_pos):
                        return True
                        
                elif event_type == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                    if self.handle_transform_mouse_release(screen_pos):
                        return True
                    
            # NEU: ACHSEN-LOCKING (X/Y/Z Keys während Transform)
            elif event_type == QEvent.KeyPress:
                if event.key() == Qt.Key_Escape:
                    self.hide_transform_gizmo()
                    return True

                # Achsen-Lock mit X/Y/Z Keys
                if self.transform_state:
                    if event.key() == Qt.Key_X:
                        # Toggle X-Achsen-Lock
                        if event.modifiers() & Qt.ShiftModifier:
                            # Shift+X = YZ-Ebene (bewege auf Y und Z)
                            self.transform_state.toggle_plane_lock("YZ")
                            # Visueller Indikator
                            if hasattr(self, '_transform_ctrl') and self._transform_ctrl.gizmo:
                                if self.transform_state.plane_lock == "YZ":
                                    self._transform_ctrl.gizmo.show_plane_constraint_indicator("YZ")
                                else:
                                    self._transform_ctrl.gizmo.hide_constraint_indicators()
                            logger.info("Ebenen-Lock: YZ (bewege auf Y und Z)")
                        else:
                            # X = X-Achse
                            self.transform_state.toggle_axis_lock("X")
                            # Visueller Indikator
                            if hasattr(self, '_transform_ctrl') and self._transform_ctrl.gizmo:
                                if self.transform_state.axis_lock == "X":
                                    self._transform_ctrl.gizmo.show_axis_constraint_indicator("X")
                                else:
                                    self._transform_ctrl.gizmo.hide_constraint_indicators()
                            logger.info(f"Achsen-Lock: {'X' if self.transform_state.axis_lock == 'X' else 'Aus'}")
                        return True

                    elif event.key() == Qt.Key_Y:
                        if event.modifiers() & Qt.ShiftModifier:
                            # Shift+Y = XZ-Ebene
                            self.transform_state.toggle_plane_lock("XZ")
                            # Visueller Indikator
                            if hasattr(self, '_transform_ctrl') and self._transform_ctrl.gizmo:
                                if self.transform_state.plane_lock == "XZ":
                                    self._transform_ctrl.gizmo.show_plane_constraint_indicator("XZ")
                                else:
                                    self._transform_ctrl.gizmo.hide_constraint_indicators()
                            logger.info("Ebenen-Lock: XZ (bewege auf X und Z)")
                        else:
                            self.transform_state.toggle_axis_lock("Y")
                            # Visueller Indikator
                            if hasattr(self, '_transform_ctrl') and self._transform_ctrl.gizmo:
                                if self.transform_state.axis_lock == "Y":
                                    self._transform_ctrl.gizmo.show_axis_constraint_indicator("Y")
                                else:
                                    self._transform_ctrl.gizmo.hide_constraint_indicators()
                            logger.info(f"Achsen-Lock: {'Y' if self.transform_state.axis_lock == 'Y' else 'Aus'}")
                        return True

                    elif event.key() == Qt.Key_Z:
                        if event.modifiers() & Qt.ShiftModifier:
                            # Shift+Z = XY-Ebene
                            self.transform_state.toggle_plane_lock("XY")
                            # Visueller Indikator
                            if hasattr(self, '_transform_ctrl') and self._transform_ctrl.gizmo:
                                if self.transform_state.plane_lock == "XY":
                                    self._transform_ctrl.gizmo.show_plane_constraint_indicator("XY")
                                else:
                                    self._transform_ctrl.gizmo.hide_constraint_indicators()
                            logger.info("Ebenen-Lock: XY (bewege auf X und Y)")
                        else:
                            self.transform_state.toggle_axis_lock("Z")
                            # Visueller Indikator
                            if hasattr(self, '_transform_ctrl') and self._transform_ctrl.gizmo:
                                if self.transform_state.axis_lock == "Z":
                                    self._transform_ctrl.gizmo.show_axis_constraint_indicator("Z")
                                else:
                                    self._transform_ctrl.gizmo.hide_constraint_indicators()
                            logger.info(f"Achsen-Lock: {'Z' if self.transform_state.axis_lock == 'Z' else 'Aus'}")
                        return True

                    # NEU: MODALE NUMERISCHE EINGABE (Blender-Style)
                    # Während Drag: Tippe Zahl → Enter zum Anwenden
                    text = event.text()

                    # Ziffern, Dezimalpunkt, Minus-Zeichen
                    if text and (text.isdigit() or text in ['.', '-']):
                        self.transform_state.numeric_input += text
                        self._show_numeric_input_overlay(self.transform_state.numeric_input)
                        logger.debug(f"Numerische Eingabe: {self.transform_state.numeric_input}")
                        return True

                    # Enter: Wert anwenden
                    elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                        if self.transform_state.numeric_input:
                            try:
                                value = float(self.transform_state.numeric_input)
                                self._apply_numeric_transform(value)
                                self.transform_state.numeric_input = ""
                                self._hide_numeric_input_overlay()
                                logger.success(f"Numerischer Wert angewendet: {value}")
                            except ValueError:
                                logger.warning(f"Ungültige Eingabe: {self.transform_state.numeric_input}")
                                self.transform_state.numeric_input = ""
                                self._hide_numeric_input_overlay()
                        return True

                    # Backspace: Letztes Zeichen löschen
                    elif event.key() == Qt.Key_Backspace:
                        if self.transform_state.numeric_input:
                            self.transform_state.numeric_input = self.transform_state.numeric_input[:-1]
                            if self.transform_state.numeric_input:
                                self._show_numeric_input_overlay(self.transform_state.numeric_input)
                            else:
                                self._hide_numeric_input_overlay()
                            logger.debug(f"Numerische Eingabe: {self.transform_state.numeric_input}")
                        return True

        # --- EDGE SELECTION MODE (Fillet/Chamfer) ---
        if self.edge_select_mode:
            if event.type() == QEvent.MouseMove:
                pos = event.position() if hasattr(event, 'position') else event.pos()
                x, y = int(pos.x()), int(pos.y())
                self.handle_edge_mouse_move(x, y)
                return True

            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                pos = event.position() if hasattr(event, 'position') else event.pos()
                x, y = int(pos.x()), int(pos.y())
                is_multi = QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.ShiftModifier)
                if self.handle_edge_click(x, y, is_multi):
                    return True

            if event.type() == QEvent.KeyPress:
                if event.key() == Qt.Key_Escape:
                    self.stop_edge_selection_mode()
                    return True
                # A-Taste: Alle Kanten selektieren
                if event.key() == Qt.Key_A:
                    self.select_all_edges()
                    return True

            return False

        # --- POINT-TO-POINT MOVE MODE (Fusion 360-Style) ---
        if self.point_to_point_mode:
            # Mouse Move: Zeige Hover-Vertex (KEIN LOGGING für Performance)
            if event.type() == QEvent.MouseMove:
                pos = event.position() if hasattr(event, 'position') else event.pos()
                x, y = int(pos.x()), int(pos.y())

                # WICHTIG: log_pick=False für hover (kein Debug-Output bei jedem Frame)
                body_id, point = self.pick_point_on_geometry(x, y, snap_to_vertex=True, log_pick=False)
                if point:
                    # Zeige Hover-Marker (Orange)
                    import pyvista as pv
                    sphere = pv.Sphere(center=point, radius=1.5)
                    self.plotter.remove_actor('p2p_hover_marker', render=False)
                    self.plotter.add_mesh(sphere, color='orange', opacity=0.8, name='p2p_hover_marker')
                else:
                    # Entferne Hover-Marker wenn kein Treffer
                    self.plotter.remove_actor('p2p_hover_marker', render=True)
                return True

            # Mouse Click: Wähle Punkt
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                pos = event.position() if hasattr(event, 'position') else event.pos()
                x, y = int(pos.x()), int(pos.y())

                # WICHTIG: Entferne Hover-Marker BEVOR wir picken (sonst blockt er den Pick!)
                self.plotter.remove_actor('p2p_hover_marker', render=False)

                body_id, point = self.pick_point_on_geometry(x, y)
                if point:
                    if not self.point_to_point_start:
                        # Erster Punkt ausgewählt
                        self.point_to_point_start = point
                        self.point_to_point_body_id = body_id
                        # Visualisiere Start-Punkt (Gelb)
                        import pyvista as pv
                        sphere = pv.Sphere(center=point, radius=2.0)
                        self.plotter.add_mesh(sphere, color='yellow', name='p2p_start_marker')
                        logger.success(f"✅ Start-Punkt gewählt. Jetzt Ziel-Punkt klicken.")
                    else:
                        # Zweiter Punkt ausgewählt - führe Move durch
                        end_point = point
                        logger.info(f"🎯 Point-to-Point Move: Start {self.point_to_point_start} → Ziel {end_point}")
                        # Emittiere Signal für MainWindow
                        self.point_to_point_move.emit(self.point_to_point_body_id, self.point_to_point_start, end_point)
                        # Reset
                        self.cancel_point_to_point_mode()
                return True

            # ESC zum Abbrechen
            if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
                self.cancel_point_to_point_mode()
                return True
            return False

        # --- PLANE SELECT MODE ---
        if self.plane_select_mode:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                pos = event.position() if hasattr(event, 'position') else event.pos()
                self._pick_plane_at_position(int(pos.x()), int(pos.y()))
                return True

            if event.type() == QEvent.MouseMove:
                pos = event.position() if hasattr(event, 'position') else event.pos()
                self._highlight_plane_at_position(int(pos.x()), int(pos.y()))
                return True
            return False

        # --- EXTRUDE MODE LOGIK (NEU) ---
        if self.extrude_mode:
            # Rechtsklick zum Bestätigen
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.RightButton:
                if abs(self.extrude_height) > 0.001:
                    self.confirm_extrusion() 
                    return True
            
            # Enter Taste zum Bestätigen
            if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.confirm_extrusion()
                return True

        # --- MOUSE MOVE ---
        if event.type() == QEvent.MouseMove:
            pos = event.position() if hasattr(event, 'position') else event.pos()
            x, y = int(pos.x()), int(pos.y())

            # Dragging Logik (Extrude Höhe ziehen)
            if self.extrude_mode and getattr(self, 'is_dragging', False):
                delta = self._calculate_extrude_delta(pos)
                self.show_extrude_preview(self.drag_start_height + delta, self.extrude_operation)
                self.height_changed.emit(self.extrude_height)
                return True
            
            # Drag Start erkennen
            elif self.extrude_mode and getattr(self, '_is_potential_drag', False):
                if (pos - self._potential_drag_start).manhattanLength() > 5:
                    self.is_dragging = True
                    self._is_potential_drag = False
                    self.drag_start_pos = self._potential_drag_start
                    self.drag_start_height = self.extrude_height
                    return True
            
            # Normales Hovering (Nur wenn Maus nicht gedrückt oder Drag aktiv)
            elif not (event.buttons() & Qt.LeftButton):
                pos = event.position() if hasattr(event, 'position') else event.pos()
                x, y = int(pos.x()), int(pos.y())

                # NEU: Body-Hover für pending transform mode
                if self.pending_transform_mode:
                    body_id = self.select_body_at(x, y)
                    if body_id != self.hover_body_id:
                        # Altes Highlighting entfernen
                        if self.hover_body_id:
                            self.unhighlight_body(self.hover_body_id)
                        # Neues Highlighting setzen
                        self.hover_body_id = body_id
                        if body_id:
                            self.highlight_body(body_id)
                    return False

                # ÄNDERUNG: Face-Hovering (nur wenn NICHT im pending transform mode)
                hit_id = self.pick(x, y, selection_filter=self.active_selection_filter)
                if hit_id != getattr(self, 'hover_face_id', -1):
                    self._update_hover(hit_id)
            return False

        # --- MOUSE PRESS (Left) ---
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            pos = event.position() if hasattr(event, 'position') else event.pos()
            x, y = int(pos.x()), int(pos.y())

            # NEU (Fix 1): Body-Picking NUR für pending transform mode
            # WICHTIG: Nur wenn MainWindow explizit auf Body-Klick wartet!
            if self.pending_transform_mode:
                body_id = self.select_body_at(x, y)
                if body_id:
                    self.body_clicked.emit(body_id)
                    return True

            # Face-Selection (für Extrude etc.)
            hit_id = self.pick(x, y, selection_filter=self.active_selection_filter)

            if hit_id != -1:
                # Multi-Select mit STRG/Shift
                is_multi = QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.ShiftModifier)
                if not is_multi:
                    self.selected_face_ids.clear()
                    
                # Toggle bei Multi-Select
                if is_multi and hit_id in self.selected_face_ids:
                    self.selected_face_ids.discard(hit_id)
                else:
                    self.selected_face_ids.add(hit_id)
                
                # Extrude Drag vorbereiten
                if self.extrude_mode:
                    self._is_potential_drag = True
                    self._potential_drag_start = pos
                    face = next((f for f in self.detector.selection_faces if f.id == hit_id), None)
                    if face: self._cache_drag_direction_for_face_v2(face)
                
                self._draw_selectable_faces_from_detector()
                
                # NEU: Signal für automatische Operation-Erkennung
                self.face_selected.emit(hit_id)
                return True

        # --- MOUSE RELEASE ---
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if self.extrude_mode:
                self.is_dragging = False
                self._is_potential_drag = False
        
        return False
        #return super().eventFilter(obj, event)
    
    def _handle_3d_click(self, x, y):
        """Erkennt Klick auf 3D Körper und sendet Signal"""
        if not self.bodies: return
        try:
            import vtk
            picker = vtk.vtkCellPicker()
            picker.SetTolerance(0.005)
            picker.Pick(x, self.plotter.interactor.height()-y, 0, self.plotter.renderer)
            
            actor = picker.GetActor()
            if actor:
                body_id = None
                for bid, actors in self._body_actors.items():
                    # FIX: Iteriere über alle Actors des Bodies
                    for name in actors:
                        if self.plotter.renderer.actors.get(name) == actor:
                            body_id = bid
                            break
                    if body_id is not None: break
                
                if body_id is not None:
                    pos = picker.GetPickPosition()
                    self.clicked_3d_point.emit(body_id, pos)
        except Exception as e:
            logger.error(f" {e}")
            
    def _cache_drag_direction_for_face(self, face_idx):
        """Hilfsfunktion um Richtung basierend auf einem Face zu setzen"""
        if face_idx < 0 or face_idx >= len(self.detected_faces): return
        
        face = self.detected_faces[face_idx]
        normal = np.array(face.get('normal', (0,0,1)))
        
        if face.get('type') == 'body_face':
            center = np.array(face.get('center_3d', (0,0,0)))
        else:
            c2 = face['center_2d']
            center = np.array(self._transform_2d_to_3d(c2[0], c2[1], face['normal'], face['origin']))

        # Projektion berechnen (wie vorher in _cache_drag_direction)
        def world_to_display(pt):
            self.plotter.renderer.SetWorldPoint(pt[0], pt[1], pt[2], 1.0)
            self.plotter.renderer.WorldToDisplay()
            d_pt = self.plotter.renderer.GetDisplayPoint()
            height = self.plotter.interactor.height()
            return np.array([d_pt[0], height - d_pt[1]])

        p_start = world_to_display(center)
        p_end = world_to_display(center + normal * 10.0)
        vec = p_end - p_start
        
        if np.linalg.norm(vec) < 0.1:
            self._drag_screen_vector = np.array([1.0, 0.0])
        else:
            self._drag_screen_vector = vec / np.linalg.norm(vec)
            
            
    def _cache_drag_direction(self):
        """Wrapper für Kompatibilität"""
        if self.selected_faces:
            self._cache_drag_direction_for_face(list(self.selected_faces)[0])
    
    def _calculate_extrude_delta(self, current_pos):
        """Berechnet delta mit dynamischer Skalierung."""
        dx = current_pos.x() - self.drag_start_pos.x()
        dy = current_pos.y() - self.drag_start_pos.y()
        mouse_vec = np.array([dx, dy])
        
        # 1. Projektion auf die Zug-Achse (wie viel bewegen wir uns entlang des Pfeils?)
        projection_pixels = np.dot(mouse_vec, self._drag_screen_vector)
        
        # 2. Umrechnung Pixel -> Millimeter
        # Nutze den gespeicherten 3D-Ankerpunkt
        anchor = getattr(self, '_drag_anchor_3d', None)
        scale_factor = self._get_pixel_to_world_scale(anchor)
        
        # Das Resultat sollte sich jetzt "1 zu 1" anfühlen
        return projection_pixels * scale_factor

    # ==================== PICKING ====================
    def _highlight_plane_at_position(self, x, y):
        """
        Kombiniert Standard-Ebenen Highlight mit GeometryDetector Highlight.
        Ersetzt den 'grünen Kreis' durch echte Flächen-Hervorhebung.
        """
        if not self._plane_actors: return
        
        height = self.plotter.interactor.height()
        
        # 1. Standard-Ebenen prüfen (XY, XZ, YZ) - die bleiben wie sie sind
        import vtk
        picker = vtk.vtkPropPicker()
        picker.Pick(x, height-y, 0, self.plotter.renderer)
        actor = picker.GetActor()
        found_std_plane = None
        
        if actor:
            for k, v in self._plane_actors.items():
                if self.plotter.renderer.actors.get(v) == actor: 
                    found_std_plane = k; break
        
        # Standard-Ebenen Highlight setzen
        if found_std_plane != self.last_highlighted_plane:
            self.last_highlighted_plane = found_std_plane
            for k in ['xy','xz','yz']:
                self._set_opacity(k, 0.7 if k == found_std_plane else 0.25)
            self.plotter.render()

        # 2. Wenn keine Standard-Ebene, prüfe auf Body-Flächen via Detector
        # (Nur wenn wir nicht gerade über einer Standardebene hovern)
        new_hover_id = -1
        
        if found_std_plane is None:
            # Nutze die intelligente Pick-Logik
            new_hover_id = self.pick(x, y, selection_filter={"body_face"})
        
        # Nur neu zeichnen wenn sich was geändert hat
        if new_hover_id != getattr(self, 'hover_face_id', -1):
            self.hover_face_id = new_hover_id
            # Nutzt die gleiche Methode wie Extrude -> Blaue Fläche!
            self._draw_selectable_faces_from_detector()
    
    def _draw_plane_hover_highlight(self, pos, normal):
        """Zeichnet Highlight für Body-Fläche im Plane-Select-Modus"""
        self._clear_plane_hover_highlight()
        try:
            center = np.array(pos)
            n = np.array(normal)
            n = n / np.linalg.norm(n) if np.linalg.norm(n) > 0 else np.array([0,0,1])
            
            # Erstelle einen Kreis senkrecht zur Normalen
            radius = 8.0
            if abs(n[2]) < 0.9:
                u = np.cross(n, [0, 0, 1])
            else:
                u = np.cross(n, [1, 0, 0])
            u = u / np.linalg.norm(u)
            v = np.cross(n, u)
            
            points = []
            for i in range(33):
                angle = i * 2 * math.pi / 32
                p = center + radius * (math.cos(angle) * u + math.sin(angle) * v)
                points.append(p)
            
            pts = np.array(points)
            lines = pv.lines_from_points(pts)
            self.plotter.add_mesh(lines, color='lime', line_width=3, name='plane_hover')
            
            # Pfeil für Normale
            arrow = pv.Arrow(start=center, direction=n, scale=10)
            self.plotter.add_mesh(arrow, color='lime', name='plane_hover_arrow')
            
            self.plotter.update()
        except: pass
    
    def _clear_plane_hover_highlight(self):
        """Entfernt Plane-Hover-Highlight"""
        try:
            self.plotter.remove_actor('plane_hover')
        except: pass
        try:
            self.plotter.remove_actor('plane_hover_arrow')
        except: pass

    def _set_opacity(self, key, val):
        try: 
            self.plotter.renderer.actors.get(self._plane_actors[key]).GetProperty().SetOpacity(val)
        except: pass

    def _pick_plane_at_position(self, x, y):
        """
        Wählt die Ebene aus.
        Priorität: 1. Standard-Ebenen, 2. Body-Flächen (via Detector)
        """
        import vtk
        height = self.plotter.interactor.height()
        
        # 1. Standard-Ebenen (XY, XZ, YZ)
        picker = vtk.vtkPropPicker()
        picker.Pick(x, height - y, 0, self.plotter.renderer)
        actor = picker.GetActor()
        
        if actor:
            for name, actor_name in self._plane_actors.items():
                if self.plotter.renderer.actors.get(actor_name) == actor:
                    self.plane_clicked.emit(name)
                    return

        # 2. Body-Flächen via Detector (Das ist die Verbesserung!)
        # Wir nutzen das Ergebnis vom Hover, oder picken neu
        face_id = self.pick(x, y, selection_filter={"body_face"})
        
        if face_id != -1:
            # Face Objekt holen
            face = next((f for f in self.detector.selection_faces if f.id == face_id), None)
            if face:
                logger.info(f"Sketch Plane gewählt: Face {face.id} auf Body {face.owner_id}")

                # Sende Origin und Normal
                self.custom_plane_clicked.emit(
                    face.plane_origin,
                    face.plane_normal
                )

                # Speichere die stabile X-Achse für Schritt 2 (siehe vorherige Antwort)
                self._last_picked_x_dir = face.plane_x

                # ✅ FIX: Speichere auch die Body-ID für korrektes Targeting
                self._last_picked_body_id = face.owner_id
                return

    def _update_detector_for_picking(self):
        """Lädt alle sichtbaren Body-Meshes in den Detector"""
        if not hasattr(self, 'detector'): return
        
        # Detector leeren
        self.detector.clear()
        
        # Nur Bodies laden (Sketches brauchen wir nicht um darauf zu sketchen)
        # Performance Optimization Phase 2.2: Übergebe extrude_mode für Dynamic Priority
        extrude_mode = getattr(self, 'extrude_mode', False)
        for bid, body in self.bodies.items():
            if self.is_body_visible(bid) and 'mesh' in body:
                self.detector.process_body_mesh(bid, body['mesh'], extrude_mode=extrude_mode)
            
   
        
    def _handle_selection_click(self, x, y, is_multi):
        """CAD-Selection über GeometryDetector"""
        ray_o, ray_d = self.get_ray_from_click(x, y)

        # WICHTIG: self.pick nutzen
        face_id = self.pick(
            ray_o,
            ray_d,
            selection_filter=self.active_selection_filter
        )

        if face_id != -1:
            if is_multi:
                # Toggle Selection
                if face_id in self.selected_faces:
                    self.selected_faces.remove(face_id)
                else:
                    self.selected_faces.add(face_id)
            else:
                if face_id not in self.selected_faces:
                    self.selected_faces.clear()
                    self.selected_faces.add(face_id)

            self._draw_selectable_faces()
            self.face_selected.emit(face_id)
            self._cache_drag_direction_for_face(face_id)

        else:
            # Background Click → Deselect
            if not is_multi:
                self.selected_faces.clear()
                self._draw_selectable_faces()

    def _on_face_clicked(self, point, hover_only=False):
        best_dist = float('inf')
        best_idx = -1
        
        for i, face in enumerate(self.detected_faces):
            # Body-Face oder Sketch-Face?
            if face.get('type') == 'body_face':
                c3 = face.get('center_3d', (0, 0, 0))
            else:
                c2 = face['center_2d']
                c3 = self._transform_2d_to_3d(c2[0], c2[1], face['normal'], face['origin'])
            
            dist = math.sqrt(sum((point[k]-c3[k])**2 for k in range(3)))
            if dist < best_dist:
                best_dist = dist
                best_idx = i
        
        if best_idx >= 0 and best_dist < 200:
            if hover_only:
                # Nur neu zeichnen wenn sich hover geändert hat
                if self.hovered_face != best_idx:
                    self.hovered_face = best_idx
                    self._draw_selectable_faces()
            else:
                # Klick: Toggle Auswahl
                if best_idx in self.selected_faces: 
                    self.selected_faces.remove(best_idx)
                else: 
                    self.selected_faces.add(best_idx)
                self._draw_selectable_faces()
                self.face_selected.emit(best_idx)
        elif hover_only and self.hovered_face != -1:
            # Nichts getroffen - hover zurücksetzen
            self.hovered_face = -1
            self._draw_selectable_faces()

    def _transform_2d_to_3d(self, x, y, normal, origin):
        """Wandelt lokale Sketch-Koordinaten in globale 3D-Koordinaten um"""
        ox, oy, oz = origin
        
        # Standard-Berechnung
        ux, uy = self._calculate_plane_axes(normal)
        
        # P_world = Origin + x*U + y*V
        px = ox + x * ux[0] + y * uy[0]
        py = oy + x * ux[1] + y * uy[1]
        pz = oz + x * ux[2] + y * uy[2]
        return (px, py, pz)

    def _apply_boolean_operation(self, new_mesh, operation, target_body_id=None):
        """Führt Boolean Ops durch: Union, Difference, New Body"""
        import vtk
        
        # 1. Neuer Körper
        if operation == "New Body" or not self.bodies or target_body_id is None:
            new_id = max(self.bodies.keys(), default=0) + 1
            self.add_body(new_id, f"Body {new_id}", new_mesh.points, [], color=None)
            # Hinweis: add_body erwartet verts/faces, aber wir können PyVista mesh direkt nutzen wenn wir add_body anpassen
            # Besserer Weg hier: Direkt mesh speichern
            self._add_mesh_as_body(new_id, new_mesh)
            return

        # 2. Bestehenden Körper holen
        # Wir nehmen vereinfacht an, es gibt einen 'aktiven' Körper oder den zuletzt erstellten
        target_id = target_body_id if target_body_id else list(self.bodies.keys())[-1]
        target_mesh = self.bodies[target_id]['mesh']

        try:
            # PyVista Boolean Operations (benötigt triangulierte, saubere Meshes)
            # Sicherstellen, dass alles Dreiecke sind
            if not target_mesh.is_all_triangles: target_mesh = target_mesh.triangulate()
            if not new_mesh.is_all_triangles: new_mesh = new_mesh.triangulate()
            
            result_mesh = None
            
            if operation == "Join":
                result_mesh = target_mesh.boolean_union(new_mesh)
            elif operation == "Cut":
                result_mesh = target_mesh.boolean_difference(new_mesh)
            elif operation == "Intersect":
                result_mesh = target_mesh.boolean_intersection(new_mesh)
                
            if result_mesh and result_mesh.n_points > 0:
                # Körper aktualisieren
                self._add_mesh_as_body(target_id, result_mesh, color=self.bodies[target_id]['color'])
                logger.success(f"Boolean success.")
            else:
                logger.warning("Boolean Operation failed (empty result).")
                # Fallback: Als neuen Körper hinzufügen, damit Arbeit nicht verloren geht
                self._apply_boolean_operation(new_mesh, "New Body")

        except Exception as e:
            logger.error(f" {e}")
            self._apply_boolean_operation(new_mesh, "New Body")
            
    def _add_mesh_as_body(self, bid, mesh, color=None):
        """Interne Hilfsfunktion um ein PyVista Mesh direkt als Body zu speichern"""
        # Alten Actor entfernen
        if bid in self._body_actors:
            for n in self._body_actors[bid]: 
                try: self.plotter.remove_actor(n)
                except: pass
        
        mesh = mesh.clean() # Wichtig für Rendering
        mesh.compute_normals(inplace=True)
        
        col = color or "lightblue"
        n1 = f"body_{bid}_m"
        # PBR (Physically Based Rendering) für Metall-Look
        self.plotter.add_mesh(mesh, color=col, name=n1, show_edges=False, 
                              smooth_shading=True, pbr=True, metallic=0.5, roughness=0.4)
        
        n2 = f"body_{bid}_e"
        edges = mesh.extract_feature_edges(feature_angle=45)
        self.plotter.add_mesh(edges, color="black", line_width=2, name=n2)
        
        self._body_actors[bid] = (n1, n2)
        self.bodies[bid] = {'mesh': mesh, 'color': col}
        self.plotter.render()

    # ==================== PUBLIC API ====================
    def set_plane_select_mode(self, enabled):
        self.plane_select_mode = enabled
        self.last_highlighted_plane = None
        
        # Reset Hover
        self.hover_face_id = -1
        self.selected_face_ids.clear()
        
        if enabled: 
            self._show_selection_planes()
            
            # WICHTIG: Detector mit Geometrie füllen, genau wie beim Extrude!
            # Wir nutzen die Hilfsfunktion, um nicht alles doppelt zu schreiben
            self._update_detector_for_picking()
            
            self.plotter.render()
        else: 
            self._hide_selection_planes()
            # Aufräumen
            self._clear_face_actors()
            self._clear_plane_hover_highlight() # Alte Visualisierung löschen
            self.plotter.render()

    def set_extrude_mode(self, enabled):
        """Aktiviert den Modus und stellt sicher, dass der Detector visualisiert wird."""
        self.extrude_mode = enabled
        
        # Reset Selection beim Start
        if enabled:
            self.selected_face_ids.clear()
            self._drag_screen_vector = np.array([0.0, -1.0]) 
            # Zeichnen anstoßen (initial leer, da nichts selektiert)
            self._draw_selectable_faces_from_detector()
            self.plotter.render()
        else:
            self.selected_face_ids.clear()
            self._clear_face_actors()
            self._clear_preview()
            self.plotter.render()
            
    def get_extrusion_data_for_kernel(self):
        """Gibt die Shapely-Polygone für den Kernel zurück"""
        data = []
        for fid in self.selected_face_ids:
            # FIX: Auch hier 'selection_faces' nutzen
            face = next((f for f in self.detector.selection_faces if f.id == fid), None)
            if face and face.domain_type.startswith('sketch'):
                data.append({
                    'poly': face.shapely_poly,
                    'sketch_id': face.owner_id
                })
        return data
        
    

    def _draw_selectable_faces_from_detector(self):
        """
        PERFORMANCE FIX:
        Zeichnet NUR die aktuell selektierten Flächen und die gehoverte Fläche.
        Zeichnet NICHT mehr alle 60+ Kandidaten als transparente Overlays,
        da dies bei komplexen Modellen extrem laggt.
        """
        if not self.selected_face_ids and getattr(self, 'hover_face_id', -1) == -1 and not self._face_actors:
            return

        self._clear_face_actors()
        
        # 1. Sammle relevante IDs (Selected + Hovered)
        relevant_ids = set(self.selected_face_ids)
        if getattr(self, 'hover_face_id', -1) != -1:
            relevant_ids.add(self.hover_face_id)
            
        if not relevant_ids:
            # Nichts zu tun, Render nur erzwingen um alte zu löschen
            self.plotter.render()
            return
            
        # 2. Nur relevante zeichnen
        for face in self.detector.selection_faces:
            if face.id not in relevant_ids:
                continue
                
            is_selected = face.id in self.selected_face_ids
            is_hovered = face.id == getattr(self, 'hover_face_id', -1)
            
            # Farbe und Transparenz
            if is_selected:
                color = 'orange'
                opacity = 0.8
            elif is_hovered:
                color = '#44aaff' # Hellblau
                opacity = 0.6
            else:
                continue
            
            if face.display_mesh:
                name = f"det_face_{face.id}"

                # Erhöhter Offset gegen Z-Fighting (UX-Improvement: 0.05 → 0.5)
                # User-Problem: "selektierte fläche nicht immer sichtbar"
                offset = np.array(face.plane_normal) * 0.5
                shifted = face.display_mesh.translate(offset, inplace=False)

                self.plotter.add_mesh(
                    shifted,
                    color=color,
                    opacity=opacity,
                    name=name,
                    pickable=False
                )
                self._face_actors.append(name)

            else:
                # Performance Optimization Phase 2.4: Fallback-Highlighting (Wireframe)
                # Wenn display_mesh fehlt, zeichne zumindest den Umriss als Feedback
                logger.debug(f"⚠️ Face {face.id} hat kein display_mesh - nutze Wireframe-Fallback")

                try:
                    # Erstelle einen simplen Marker an der plane_origin
                    center = np.array(face.plane_origin)
                    normal = np.array(face.plane_normal)

                    # Erstelle ein kleines Quad als Highlight
                    if abs(normal[2]) < 0.9:
                        u = np.cross(normal, [0, 0, 1])
                    else:
                        u = np.cross(normal, [1, 0, 0])
                    u = u / np.linalg.norm(u)
                    v = np.cross(normal, u)

                    size = 10.0  # 10mm großes Quad
                    pts = [
                        center + size * (-u - v),
                        center + size * (u - v),
                        center + size * (u + v),
                        center + size * (-u + v),
                    ]

                    import pyvista as pv
                    quad = pv.PolyData(np.array(pts), faces=[4, 0, 1, 2, 3])

                    name = f"det_face_fallback_{face.id}"
                    self.plotter.add_mesh(
                        quad,
                        color=color,
                        opacity=opacity,
                        style='wireframe',  # Wireframe statt Solid
                        line_width=3,
                        name=name,
                        pickable=False
                    )
                    self._face_actors.append(name)

                except Exception as e:
                    logger.warning(f"Konnte Fallback-Highlight nicht zeichnen: {e}")

        self.plotter.render()
        
        
    def set_edge_select_mode(self, enabled):
        """Aktiviert/deaktiviert den Edge-Selection-Modus für Fillet/Chamfer"""
        self.edge_select_mode = getattr(self, 'edge_select_mode', False)
        
        # Wenn wir umschalten
        if enabled != self.edge_select_mode:
            self.edge_select_mode = enabled
            self.selected_edges = getattr(self, 'selected_edges', set())
            
            if enabled:
                # WICHTIG für Face-Picking im Edge-Mode:
                # Wir laden die Body-Faces in den Detector, damit _try_select_loop_from_face_click funktioniert
                self._update_detector_for_picking()
            else:
                self._clear_edge_highlights()

   

    def _highlight_all_edges(self):
        """Zeigt alle Kanten der Bodies als selektierbar an"""
        try:
            for bid, body_data in self.bodies.items():
                mesh = body_data.get('mesh')
                if mesh:
                    edges = mesh.extract_feature_edges(feature_angle=30)
                    name = f"edges_highlight_{bid}"
                    self.plotter.add_mesh(edges, color='yellow', line_width=2, 
                                         name=name, opacity=0.7)
            self.plotter.update()
        except Exception as e:
            logger.error(f" {e}")
    
    def _clear_edge_highlights(self):
        """Entfernt alle Edge-Highlights"""
        try:
            for bid in self.bodies.keys():
                name = f"edges_highlight_{bid}"
                try:
                    self.plotter.remove_actor(name)
                except:
                    pass
            self.plotter.update()
        except:
            pass
            
    def get_ray_from_click(self, x, y):
        """
        Berechnet Ursprung und Richtung für Raycasting an Pixel x,y.
        FIX: Robustere Koordinatenumrechnung für VTK.
        """
        renderer = self.plotter.renderer
        
        # Fenstergröße holen
        w, h = self.plotter.window_size
        
        # WICHTIG: VTK Y-Koordinate ist invertiert (0 ist unten, Qt 0 ist oben)
        # Wir nutzen hier die interactor-Größe, das ist oft genauer als window_size bei eingebetteten Widgets
        if self.plotter.interactor:
            ih = self.plotter.interactor.GetSize()[1]
            y_vtk = ih - y
        else:
            y_vtk = h - y
            
        # 1. Startpunkt (Near Plane)
        renderer.SetDisplayPoint(x, y_vtk, 0)
        renderer.DisplayToWorld()
        start = np.array(renderer.GetWorldPoint()[:3])
        
        # 2. Endpunkt (Far Plane)
        renderer.SetDisplayPoint(x, y_vtk, 1)
        renderer.DisplayToWorld()
        end = np.array(renderer.GetWorldPoint()[:3])
        
        # 3. Richtung
        direction = end - start
        norm = np.linalg.norm(direction)
        if norm > 0:
            direction = direction / norm
            
        return tuple(start), tuple(direction)
        
    def _restore_body_colors(self):
        """Stellt Original-Farben aller Bodies wieder her"""
        # FIX: Variable Anzahl von Actors unterstützen
        for bid, actors in self._body_actors.items():
            try:
                if not actors: continue
                mesh_name = actors[0] # Das erste Element ist immer das Mesh
                
                if mesh_name in self.plotter.renderer.actors:
                    actor = self.plotter.renderer.actors[mesh_name]
                    prop = actor.GetProperty()
                    if bid in self.bodies:
                        col = self.bodies[bid].get('color', (0.6, 0.6, 0.8))
                        prop.SetColor(*col)
                        prop.SetOpacity(1.0)
            except:
                pass
        self.plotter.render()
    
    def _detect_body_faces(self):
        """Erkennt planare Flächen von 3D-Bodies und fügt sie zu detected_faces hinzu"""
        if not self.bodies:
            return
            
        logger.debug(f" Starte Face-Detection für {len(self.bodies)} Bodies...")
        count_before = len(self.detected_faces)
            
        for bid, body_data in self.bodies.items():
            mesh = body_data.get('mesh')
            if mesh is None: continue
            
            try:
                # Prüfen ob Mesh Zellen hat
                if mesh.n_cells == 0:
                    logger.debug(f" Body {bid} hat keine Zellen (Faces).")
                    continue

                # Normalen berechnen falls nötig
                if 'Normals' not in mesh.cell_data:
                    mesh.compute_normals(cell_normals=True, inplace=True)
                
                cell_normals = mesh.cell_data.get('Normals')
                if cell_normals is None or len(cell_normals) == 0:
                    logger.debug(f" Keine Normalen für Body {bid} gefunden.")
                    continue
                
                # Gruppiere Zellen nach Normale (für planare Flächen)
                face_groups = {}  # normal_key -> list of cell_ids
                
                # Numpy-Optimierung für Geschwindigkeit
                import numpy as np
                rounded_normals = np.round(cell_normals, 2)
                
                # Wir iterieren über Indizes, das ist sicherer
                for cell_id in range(mesh.n_cells):
                    # Tuple als Key für Dictionary
                    nkey = tuple(rounded_normals[cell_id])
                    if nkey not in face_groups:
                        face_groups[nkey] = []
                    face_groups[nkey].append(cell_id)
                
                # Für jede Gruppe eine selektierbare Fläche erstellen
                for normal_key, cell_ids in face_groups.items():
                    # Berechne Zentrum aus allen Punkten der Zellen
                    # (Vereinfacht: Mittelwert der Zellen-Zentren wäre schneller, aber wir machen es robust)
                    
                    # Schneller Check: Hat die Fläche relevante Größe? (Min 1 Zelle)
                    if not cell_ids: continue

                    # Wir nehmen einfach das Zentrum der ersten Zelle als "Anker" für die Suche,
                    # und berechnen das echte Zentrum später falls nötig.
                    # Für Picking reicht ein qualitatives Zentrum.
                    
                    # Extrahiere Sub-Mesh für genaues Zentrum
                    # Das kann langsam sein bei High-Poly, aber notwendig für präzises Extrude-Handle
                    try:
                        # Hole Punkte der Zellen direkt
                        # Optimierung: Nur von jeder 10. Zelle den Mittelpunkt nehmen für Speed
                        sample_step = max(1, len(cell_ids) // 50)
                        sample_centers = []
                        
                        for i in range(0, len(cell_ids), sample_step):
                            cell = mesh.get_cell(cell_ids[i])
                            pts = cell.points
                            if len(pts) > 0:
                                sample_centers.append(np.mean(pts, axis=0))
                        
                        if not sample_centers: continue
                        
                        center_3d = np.mean(sample_centers, axis=0)
                        
                        # Fläche registrieren
                        self.detected_faces.append({
                            'type': 'body_face',
                            'body_id': bid,
                            'cell_ids': cell_ids,
                            'normal': normal_key,
                            'center_3d': tuple(center_3d),
                            'center_2d': (center_3d[0], center_3d[1]), # Dummy für API Kompatibilität
                            'origin': tuple(center_3d),
                            'mesh': mesh
                        })
                    except Exception as e:
                         logger.debug(f" Fehler bei Face-Gruppe {normal_key}: {e}")

            except Exception as e:
                logger.debug(f" Body face detection error for body {bid}: {e}")
                import traceback
                traceback.print_exc()

        added = len(self.detected_faces) - count_before
        logger.debug(f" Detection fertig. {added} Body-Faces gefunden.")

    def set_sketches(self, sketches):
        """
        Zeichnet 2D-Sketches im 3D-Raum (Batch-Rendering V2.1 - Fix).
        """
        self.sketches = list(sketches)
        if not HAS_PYVISTA: return
        
        # 1. Alte Sketch-Actors entfernen
        for n in self._sketch_actors:
            try: self.plotter.remove_actor(n)
            except: pass
        self._sketch_actors.clear()
        
        # 2. Sketches rendern
        for s, visible in self.sketches:
            if visible: 
                self._render_sketch_batched(s)
        
        self.plotter.render()

    def _render_sketch_batched(self, s):
        """
        Kombiniert Geometrie zu einem Mesh (High-Performance).
        FIX: Nutzt explizit 'lines=' für PolyData.
        """
        sid = getattr(s, 'id', id(s))
        norm = tuple(getattr(s, 'plane_normal', (0,0,1)))
        orig = getattr(s, 'plane_origin', (0,0,0))
        
        # Caching der Achsen
        cached_x = getattr(s, 'plane_x_dir', None)
        cached_y = getattr(s, 'plane_y_dir', None)
        
        if cached_x and cached_y:
            ux, uy, uz = cached_x
            vx, vy, vz = cached_y
            ox, oy, oz = orig
        else:
            (ux, uy, uz), (vx, vy, vz) = self._calculate_plane_axes(norm)
            ox, oy, oz = orig

        # Listen für Punkte: Immer [Start, End, Start, End, ...]
        reg_points = []
        const_points = []
        
        def to_3d(lx, ly):
            return (
                ox + lx * ux + ly * vx,
                oy + lx * uy + ly * vy,
                oz + lx * uz + ly * vz
            )

        # --- 1. Linien ---
        for l in getattr(s, 'lines', []):
            p1 = to_3d(l.start.x, l.start.y)
            p2 = to_3d(l.end.x, l.end.y)
            target = const_points if getattr(l, 'construction', False) else reg_points
            target.extend([p1, p2])

        # --- Helper für Kurven ---
        def add_poly_segments(points_2d_list, is_const):
            target = const_points if is_const else reg_points
            # Wandle 2D Punkte in 3D Linien-Segmente um
            pts_3d = [to_3d(p[0], p[1]) for p in points_2d_list]
            for i in range(len(pts_3d) - 1):
                target.append(pts_3d[i])
                target.append(pts_3d[i+1])

        # --- 2. Kreise ---
        for c in getattr(s, 'circles', []):
            pts = []
            steps = 64
            for j in range(steps + 1):
                angle = j * 2 * math.pi / steps
                lx = c.center.x + c.radius * math.cos(angle)
                ly = c.center.y + c.radius * math.sin(angle)
                pts.append((lx, ly))
            add_poly_segments(pts, getattr(c, 'construction', False))

        # --- 3. Bögen (Arcs) ---
        for arc in getattr(s, 'arcs', []):
            pts = []
            start, end = arc.start_angle, arc.end_angle
            sweep = end - start
            if sweep < 0.1: sweep += 360
            steps = max(12, int(sweep / 5))
            
            for j in range(steps + 1):
                t = math.radians(start + sweep * (j / steps))
                lx = arc.center.x + arc.radius * math.cos(t)
                ly = arc.center.y + arc.radius * math.sin(t)
                pts.append((lx, ly))
            add_poly_segments(pts, getattr(arc, 'construction', False))
            
        # --- 4. Splines ---
        for spline in getattr(s, 'splines', []):
            pts_2d = []
            # Versuche Punkte zu holen
            if hasattr(spline, 'get_curve_points'):
                 pts_2d = spline.get_curve_points(segments_per_span=10)
            elif hasattr(spline, 'to_lines'):
                 lines = spline.to_lines(segments_per_span=10)
                 if lines:
                     pts_2d.append((lines[0].start.x, lines[0].start.y))
                     for l in lines: pts_2d.append((l.end.x, l.end.y))
            
            if len(pts_2d) > 1:
                add_poly_segments(pts_2d, getattr(spline, 'construction', False))

        # --- BATCH MESH ERSTELLEN (FIXED) ---
        def create_lines_mesh(point_list):
            if not point_list: return None
            points = np.array(point_list)
            n_segments = len(point_list) // 2
            
            # Zellen-Array für VTK Lines: [AnzahlPunkte, Index1, Index2, AnzahlPunkte, ...]
            # Da es Liniensegmente sind, ist AnzahlPunkte immer 2.
            cells = np.full((n_segments, 3), 2, dtype=int)
            cells[:, 1] = np.arange(0, len(point_list), 2)
            cells[:, 2] = np.arange(1, len(point_list), 2)
            
            # WICHTIG: 'lines=' Parameter verwenden, nicht positionales Argument!
            return pv.PolyData(points, lines=cells.flatten())

        # Actors hinzufügen
        if reg_points:
            mesh = create_lines_mesh(reg_points)
            name = f"sketch_{sid}_reg"
            self.plotter.add_mesh(mesh, color='#4d94ff', line_width=3, name=name, pickable=False)
            self._sketch_actors.append(name)
            
        if const_points:
            mesh = create_lines_mesh(const_points)
            name = f"sketch_{sid}_const"
            self.plotter.add_mesh(mesh, color='gray', line_width=1, name=name, pickable=False, opacity=0.6)
            self._sketch_actors.append(name)

    def add_body(self, bid, name, mesh_obj=None, edge_mesh_obj=None, color=None, 
                 verts=None, faces=None, normals=None, edges=None, edge_lines=None):
        """
        Fügt einen Körper hinzu. 
        FIX: Erkennt automatisch Legacy-Listen-Aufrufe und verhindert den 'point_data' Crash.
        """
        if not HAS_PYVISTA: return
        
        # === AUTO-FIX: Argumente verschieben ===
        # Wenn main_window eine Liste als 3. Argument übergibt, landete sie in mesh_obj.
        # Das verursacht den Absturz. Wir fangen das hier ab.
        if isinstance(mesh_obj, list):
            verts = mesh_obj          # Die Liste sind eigentlich Vertices
            faces = edge_mesh_obj     # Das nächste Argument sind Faces
            # mesh_obj muss None sein, damit wir unten in den richtigen Pfad (B) laufen
            mesh_obj = None           
            edge_mesh_obj = None

        # Alten Actor entfernen (Cleanup) - MAXIMAL AGGRESSIV
        n_mesh_old = f"body_{bid}_m"
        n_edge_old = f"body_{bid}_e"
        
        # METHODE 1: Direkt aus VTK Renderer Collection entfernen
        # Das ist der zuverlässigste Weg, unabhängig von PyVista's Dictionary
        try:
            vtk_renderer = self.plotter.renderer
            actors_collection = vtk_renderer.GetActors()
            actors_collection.InitTraversal()
            actors_to_remove = []
            
            for i in range(actors_collection.GetNumberOfItems()):
                actor = actors_collection.GetNextActor()
                if actor:
                    actors_to_remove.append(actor)

            # Jetzt die markierten Actors entfernen
            # (Wir entfernen ALLE und fügen sie dann neu hinzu, außer die body_bid Actors)
            for actor in actors_to_remove:
                # Prüfe ob dieser Actor zu unserem Body gehört
                # PyVista speichert den Namen im actors Dictionary
                actor_name = None
                for name, a in self.plotter.renderer.actors.items():
                    if a is actor:
                        actor_name = name
                        break

                # WICHTIG: Gizmo-Actors NICHT entfernen!
                if actor_name and actor_name.startswith(f"body_{bid}"):
                    # UserTransform zurücksetzen NUR für Body-Actors
                    actor.SetUserTransform(None)
                    vtk_renderer.RemoveActor(actor)
                    logger.debug(f"VTK: Actor '{actor_name}' aus Renderer entfernt")
        except Exception as e:
            logger.warning(f"VTK Cleanup fehlgeschlagen: {e}")
        
        # METHODE 2: PyVista Dictionary bereinigen
        for old_name in [n_mesh_old, n_edge_old]:
            try:
                if old_name in self.plotter.renderer.actors:
                    # Aus PyVista Dictionary entfernen
                    del self.plotter.renderer.actors[old_name]
                    logger.debug(f"PyVista Dict: '{old_name}' entfernt")
            except Exception as e:
                pass
        
        # METHODE 3: Standard PyVista API als Fallback
        for old_name in [n_mesh_old, n_edge_old]:
            try:
                self.plotter.remove_actor(old_name)
            except:
                pass
        
        # Aus der internen Liste entfernen
        if bid in self._body_actors:
            for n in self._body_actors[bid]: 
                try: 
                    self.plotter.remove_actor(n)
                except: 
                    pass
            del self._body_actors[bid]
        
        # KRITISCH: Erzwinge Render nach dem Cleanup um sicherzustellen
        # dass der alte Actor wirklich weg ist bevor wir den neuen hinzufügen
        self.plotter.render()
        
        actors_list = []
        if color is None: 
            col_rgb = (0.5, 0.5, 0.5)
        elif isinstance(color, str): 
            # Wandelt "red", "blue" etc. in (1.0, 0.0, 0.0) um
            c = QColor(color)
            col_rgb = (c.redF(), c.greenF(), c.blueF())
        else: 
            # Ist schon Liste/Tuple
            col_rgb = tuple(color)
        try:
            # === PFAD A: Modernes PyVista Objekt ===
            if mesh_obj is not None:
                n_mesh = f"body_{bid}_m"
                has_normals = "Normals" in mesh_obj.point_data
                
                # DEBUG: Mesh-Koordinaten loggen
                bounds = mesh_obj.bounds
                center = mesh_obj.center
                logger.debug(f"Füge Mesh hinzu: {n_mesh}, {mesh_obj.n_points} Punkte")
                logger.debug(f"  Mesh bounds: X({bounds[0]:.1f} to {bounds[1]:.1f}), Y({bounds[2]:.1f} to {bounds[3]:.1f}), Z({bounds[4]:.1f} to {bounds[5]:.1f})")
                logger.debug(f"  Mesh center: ({center[0]:.1f}, {center[1]:.1f}, {center[2]:.1f})")
                
                self.plotter.add_mesh(mesh_obj, color=col_rgb, name=n_mesh, show_edges=False, 
                                      smooth_shading=has_normals, pbr=not has_normals, 
                                      metallic=0.1, roughness=0.6, pickable=True)
                
                # Explizit sichtbar machen
                if n_mesh in self.plotter.renderer.actors:
                    self.plotter.renderer.actors[n_mesh].SetVisibility(True)
                    logger.debug(f"Actor '{n_mesh}' sichtbar gesetzt")
                    
                actors_list.append(n_mesh)
                
                if edge_mesh_obj is not None:
                    n_edge = f"body_{bid}_e"
                    logger.debug(f"Füge Edges hinzu: {n_edge}, {edge_mesh_obj.n_lines} Linien")
                    self.plotter.add_mesh(edge_mesh_obj, color="black", line_width=2, name=n_edge, pickable=False)
                    actors_list.append(n_edge)
                
                self.bodies[bid] = {'mesh': mesh_obj, 'color': col_rgb}

            # === PFAD B: Legacy Listen (Verts/Faces) ===
            elif verts and faces:
                import numpy as np
                import pyvista as pv
                v = np.array(verts, dtype=np.float32)
                f = []
                for face in faces: f.extend([len(face)] + list(face))
                mesh = pv.PolyData(v, np.array(f, dtype=np.int32))
                
                if normals:
                    try:
                        n = np.array(normals, dtype=np.float32)
                        if len(n) == len(v): mesh.point_data["Normals"] = n
                    except: pass
                
                n_mesh = f"body_{bid}_m"
                self.plotter.add_mesh(mesh, color=col_rgb, name=n_mesh, show_edges=False, smooth_shading=True, pickable=True)
                
                if n_mesh in self.plotter.renderer.actors:
                    self.plotter.renderer.actors[n_mesh].SetVisibility(True)
                    
                actors_list.append(n_mesh)
                self.bodies[bid] = {'mesh': mesh, 'color': col_rgb}
                
            self._body_actors[bid] = tuple(actors_list)
            
            # WICHTIG: Erzwinge Render nach dem Hinzufügen
            self.plotter.render()
            
        except Exception as e:
            logger.error(f"add_body error: {e}")

    def set_body_visibility(self, body_id, visible):
        if body_id not in self._body_actors: return
        try:
            # FIX: Iteriere über alle Actors (Mesh, Edges, OCP-Lines...)
            actors = self._body_actors[body_id]
            for name in actors:
                if name in self.plotter.renderer.actors:
                    self.plotter.renderer.actors[name].SetVisibility(visible)
            self.plotter.render()
        except: pass
    
    def set_all_bodies_visible(self, visible):
        """Setzt alle Bodies sichtbar/unsichtbar"""
        for body_id in self._body_actors:
            try:
                m, e = self._body_actors[body_id]
                self.plotter.renderer.actors[m].SetVisibility(visible)
                self.plotter.renderer.actors[e].SetVisibility(visible)
            except: pass
        self.plotter.render()

    def clear_bodies(self):
        for names in self._body_actors.values():
            for n in names: 
                try: self.plotter.remove_actor(n)
                except: pass
        self._body_actors.clear(); self.bodies.clear(); self.plotter.render()

    def get_body_mesh(self, body_id):
        if body_id in self.bodies: return self.bodies[body_id]['mesh']
        return None

    def get_selected_faces(self):
        return [self.detected_faces[i] for i in self.selected_faces if i < len(self.detected_faces)]

    def get_extrusion_data(self, face_idx, height):
        if face_idx < 0 or face_idx >= len(self.detected_faces): 
            return [], []
        
        face = self.detected_faces[face_idx]
        
        # Body-Face oder Sketch-Face?
        if face.get('type') == 'body_face':
            return self._calculate_body_face_extrusion(face, height)
        else:
            return self._calculate_extrusion_geometry(face, height)

    def _calculate_extrusion_geometry(self, face, height):
        if not HAS_SHAPELY: return [], []
        poly = face.get('shapely_poly')
        if not poly: return [], []
        normal = face['normal']; origin = face['origin']
        try:
            tris = triangulate(poly)
            valid_tris = [t for t in tris if poly.contains(t.centroid)]
        except: return [], []
        verts = []; faces = []; v_map = {}
        def add(x,y,z):
            k = (round(x,4), round(y,4), round(z,4))
            if k in v_map: return v_map[k]
            idx = len(verts); verts.append((x,y,z)); v_map[k] = idx; return idx
        def trans(x,y,h): return self._transform_2d_to_3d(x,y,normal,origin)
        def trans_h(x,y,h):
            p = self._transform_2d_to_3d(x,y,normal,origin)
            nx, ny, nz = normal
            return (p[0]+nx*h, p[1]+ny*h, p[2]+nz*h)

        for t in valid_tris:
            xx, yy = t.exterior.coords.xy
            p = list(zip(xx[:3], yy[:3]))
            b = [add(*trans(x,y,0)) for x,y in p]
            t_Idx = [add(*trans_h(x,y,height)) for x,y in p]
            if height > 0:
                faces.append((b[0], b[2], b[1])); faces.append((t_Idx[0], t_Idx[1], t_Idx[2]))
            else:
                faces.append((b[0], b[1], b[2])); faces.append((t_Idx[0], t_Idx[2], t_Idx[1]))

        rings = [poly.exterior] + list(poly.interiors)
        for ring in rings:
            pts = list(ring.coords)
            for i in range(len(pts)-1):
                x1,y1 = pts[i]; x2,y2 = pts[i+1]
                b1 = add(*trans(x1,y1,0)); b2 = add(*trans(x2,y2,0))
                t1 = add(*trans_h(x1,y1,height)); t2 = add(*trans_h(x2,y2,height))
                if height > 0:
                    faces.append((b1, b2, t2)); faces.append((b1, t2, t1))
                else:
                    faces.append((b1, t1, t2)); faces.append((b1, t2, b2))
        return verts, faces

    def _detect_faces(self):
        """
        Erkennt Flächen aus Sketches für 3D-Extrusion.
        FIX: Nutzt Randpunkte statt Zentroiden als Selektor, um "Loch-Probleme" zu vermeiden.
        """
        self.detected_faces = []
        if not HAS_SHAPELY: return
        
        from shapely.ops import polygonize, unary_union
        from shapely.geometry import LineString, Polygon
        
        def rnd(val): return round(val, 5)
            
        for s, vis in self.sketches:
            if not vis: continue
            norm = tuple(getattr(s, 'plane_normal', (0,0,1)))
            orig = getattr(s, 'plane_origin', (0,0,0))
            
            all_segments = []
            
            # --- Geometrie sammeln (Identisch wie zuvor) ---
            for l in getattr(s, 'lines', []):
                if not getattr(l, 'construction', False):
                    all_segments.append(LineString([(rnd(l.start.x), rnd(l.start.y)), (rnd(l.end.x), rnd(l.end.y))]))
            
            for arc in getattr(s, 'arcs', []):
                if not getattr(arc, 'construction', False):
                    pts = []
                    start, end = arc.start_angle, arc.end_angle
                    sweep = end - start
                    if sweep < 0.1: sweep += 360
                    steps = max(12, int(sweep / 5))
                    for i in range(steps + 1):
                        t = math.radians(start + sweep * (i / steps))
                        x = arc.center.x + arc.radius * math.cos(t)
                        y = arc.center.y + arc.radius * math.sin(t)
                        pts.append((rnd(x), rnd(y)))
                    if len(pts) >= 2: all_segments.append(LineString(pts))

            for c in getattr(s, 'circles', []):
                if not getattr(c, 'construction', False):
                    pts = []
                    for i in range(65):
                        angle = i * 2 * math.pi / 64
                        x = c.center.x + c.radius * math.cos(angle)
                        y = c.center.y + c.radius * math.sin(angle)
                        pts.append((rnd(x), rnd(y)))
                    all_segments.append(LineString(pts))
            
            for spline in getattr(s, 'splines', []):
                if not getattr(spline, 'construction', False):
                     # ... Spline logic (wie gehabt) ...
                     pass 

            # --- Polygonize & Daten speichern ---
            if all_segments:
                try:
                    merged = unary_union(all_segments)
                    for poly in polygonize(merged):
                        if poly.is_valid and poly.area > 0.01:
                            # FIX: Wähle einen Punkt auf dem RAND statt im Zentrum.
                            # Das Zentrum eines "Donuts" läge im Loch -> Falsche Auswahl.
                            # Der Randpunkt ist eindeutig Teil der Außenform.
                            pt = poly.exterior.coords[0]
                            
                            self.detected_faces.append({
                                'shapely_poly': poly,
                                'coords': list(poly.exterior.coords),
                                'normal': norm,
                                'origin': orig,
                                'sketch': s,
                                'center_2d': (pt[0], pt[1]) # HIER IST DER FIX
                            })
                except Exception as e:
                    logger.error(f" {e}")
        
        # Sortieren: Kleine Flächen zuerst
        self.detected_faces.sort(key=lambda x: x['shapely_poly'].area)
    
    def _compute_atomic_regions_from_polygons(self, polygons):
        """
        Berechnet alle atomaren (nicht weiter teilbaren) Regionen 
        aus einer Liste von überlappenden Polygonen.
        
        Beispiel: 4 überlappende Kreise → 9 atomare Regionen
        """
        if not polygons:
            return []
        if len(polygons) == 1:
            return polygons
        
        from shapely.geometry import Polygon, MultiPolygon
        
        n = len(polygons)
        
        # Für jede mögliche Kombination von Polygonen berechnen wir die Region,
        # die IN allen Polygonen der Kombination liegt, aber NICHT in anderen.
        
        # Effizienterer Ansatz: Iterativ aufbauen
        # Start mit dem ersten Polygon, dann mit jedem weiteren schneiden/subtrahieren
        
        atomic = []
        
        # Methode: Für jedes Polygon berechne die Teile die:
        # - nur in diesem Polygon sind
        # - in diesem UND anderen sind (Schnittmengen)
        
        # Wir verwenden einen "overlay" Ansatz
        all_regions = []
        
        # Initialisiere mit dem ersten Polygon
        current_regions = [{'poly': polygons[0], 'inside': {0}}]
        
        for i in range(1, n):
            new_poly = polygons[i]
            next_regions = []
            
            for region in current_regions:
                poly = region['poly']
                inside_set = region['inside']
                
                if not poly.is_valid or poly.is_empty:
                    continue
                
                try:
                    # Teil der Region der AUCH im neuen Polygon ist
                    intersection = poly.intersection(new_poly)
                    # Teil der Region der NICHT im neuen Polygon ist
                    difference = poly.difference(new_poly)
                    
                    # Intersection hinzufügen (ist in allen bisherigen + dem neuen)
                    if intersection.is_valid and not intersection.is_empty:
                        for p in self._extract_polygons(intersection):
                            if p.area > 0.01:
                                next_regions.append({
                                    'poly': p, 
                                    'inside': inside_set | {i}
                                })
                    
                    # Difference hinzufügen (ist nur in den bisherigen)
                    if difference.is_valid and not difference.is_empty:
                        for p in self._extract_polygons(difference):
                            if p.area > 0.01:
                                next_regions.append({
                                    'poly': p, 
                                    'inside': inside_set.copy()
                                })
                except Exception as e:
                    # Bei Fehler: Region beibehalten
                    next_regions.append(region)
            
            # Auch den Teil des neuen Polygons der in KEINER bisherigen Region war
            try:
                remaining = new_poly
                for region in current_regions:
                    if region['poly'].is_valid:
                        remaining = remaining.difference(region['poly'])
                
                if remaining.is_valid and not remaining.is_empty:
                    for p in self._extract_polygons(remaining):
                        if p.area > 0.01:
                            next_regions.append({
                                'poly': p, 
                                'inside': {i}
                            })
            except:
                pass
            
            current_regions = next_regions
        
        # Extrahiere nur die Polygone
        result = [r['poly'] for r in current_regions if r['poly'].is_valid and r['poly'].area > 0.01]
        
        # Deduplizierung
        final = []
        for poly in result:
            is_dup = False
            for existing in final:
                try:
                    # Wenn fast identisch (symmetrische Differenz sehr klein)
                    sym_diff = poly.symmetric_difference(existing)
                    if sym_diff.area < min(poly.area, existing.area) * 0.05:
                        is_dup = True
                        break
                except:
                    pass
            if not is_dup:
                final.append(poly)
        
        return final
    
    def _extract_polygons(self, geom):
        """Extrahiert alle Polygone aus einer Shapely Geometrie"""
        from shapely.geometry import Polygon, MultiPolygon, GeometryCollection
        
        if geom.is_empty:
            return []
        if geom.geom_type == 'Polygon':
            return [geom]
        elif geom.geom_type == 'MultiPolygon':
            return list(geom.geoms)
        elif geom.geom_type == 'GeometryCollection':
            result = []
            for g in geom.geoms:
                result.extend(self._extract_polygons(g))
            return result
        return []
    
    def show_extrude_preview(self, height, operation="New Body"):
        """Erzeugt die 3D-Vorschau mit operation-basierter Farbe."""
        self._clear_preview()
        self.extrude_height = height
        
        # FIX: Crash verhindert. Prüfung auf selection_faces statt faces
        if not self.selected_face_ids or abs(height) < 0.1: return

        try:
            preview_meshes = []
            for fid in self.selected_face_ids:
                # FIX: Hier hieß es vorher self.detector.faces -> Jetzt self.detector.selection_faces
                face = next((f for f in self.detector.selection_faces if f.id == fid), None)
                
                if face and face.display_mesh:
                    normal = np.array(face.plane_normal)
                    # Extrudiere das vorhandene Display-Mesh entlang der Normalen
                    # capping=True schließt den Körper (oben/unten)
                    p_mesh = face.display_mesh.extrude(normal * height, capping=True)
                    preview_meshes.append(p_mesh)

            if preview_meshes:
                # Meshes verschmelzen für Performance
                combined = preview_meshes[0]
                for i in range(1, len(preview_meshes)):
                    combined = combined.merge(preview_meshes[i])
                
                # Farbe basierend auf Operation (nicht mehr auf Vorzeichen)
                op_colors = {
                    "New Body": '#6699ff',  # Blau
                    "Join": '#66ff66',      # Grün  
                    "Cut": '#ff6666',       # Rot
                    "Intersect": '#ffaa66'  # Orange
                }
                col = op_colors.get(operation, '#6699ff')
                
                self.plotter.add_mesh(combined, color=col, opacity=0.5, name='prev', pickable=False)
                self._preview_actor = 'prev'
                self.plotter.render()
        except Exception as e:
            logger.error(f" {e}")
    
    def _calculate_body_face_extrusion(self, face, height):
        """Berechnet vollständige Extrusion für eine Body-Fläche inkl. Seitenwände"""
        try:
            mesh = face.get('mesh')
            cell_ids = face.get('cell_ids', [])
            normal = np.array(face.get('normal', (0,0,1)))
            
            if mesh is None or not cell_ids:
                return [], []
            
            # Normalisiere
            norm_len = np.linalg.norm(normal)
            n = normal / norm_len if norm_len > 0 else np.array([0,0,1])
            
            # Extrahiere Fläche
            face_mesh = mesh.extract_cells(cell_ids)
            
            # Finde Randkanten der Fläche
            edges = face_mesh.extract_feature_edges(
                boundary_edges=True, 
                feature_edges=False, 
                manifold_edges=False
            )
            
            # Wenn keine Kanten gefunden, nutze alle Kanten
            if edges.n_points == 0:
                edges = face_mesh.extract_all_edges()
            
            # Sammle Randpunkte
            edge_points = edges.points if edges.n_points > 0 else face_mesh.points
            
            verts = []
            faces = []
            v_map = {}
            
            def add_vert(p):
                """Fügt Vertex hinzu, vermeidet Duplikate"""
                key = (round(p[0], 4), round(p[1], 4), round(p[2], 4))
                if key in v_map:
                    return v_map[key]
                idx = len(verts)
                verts.append(tuple(p))
                v_map[key] = idx
                return idx
            
            # Bottom-Fläche (Original-Geometrie)
            for i in range(face_mesh.n_cells):
                cell = face_mesh.get_cell(i)
                pts = cell.points
                if len(pts) >= 3:
                    indices = [add_vert(p) for p in pts]
                    if height > 0:
                        faces.append(tuple(reversed(indices)))  # Normale nach unten
                    else:
                        faces.append(tuple(indices))
            
            # Top-Fläche (extrudiert)
            for i in range(face_mesh.n_cells):
                cell = face_mesh.get_cell(i)
                pts = cell.points
                if len(pts) >= 3:
                    top_pts = [p + n * height for p in pts]
                    indices = [add_vert(p) for p in top_pts]
                    if height > 0:
                        faces.append(tuple(indices))  # Normale nach oben
                    else:
                        faces.append(tuple(reversed(indices)))
            
            # Seitenwände aus Randkanten
            if edges.n_lines > 0:
                lines = edges.lines
                i = 0
                while i < len(lines):
                    n_pts_line = lines[i]
                    if n_pts_line >= 2:
                        for j in range(n_pts_line - 1):
                            p1 = edge_points[lines[i + 1 + j]]
                            p2 = edge_points[lines[i + 2 + j]]
                            
                            # 4 Punkte für Quad: bottom1, bottom2, top2, top1
                            b1 = add_vert(p1)
                            b2 = add_vert(p2)
                            t1 = add_vert(p1 + n * height)
                            t2 = add_vert(p2 + n * height)
                            
                            # Zwei Dreiecke für das Quad
                            if height > 0:
                                faces.append((b1, b2, t2))
                                faces.append((b1, t2, t1))
                            else:
                                faces.append((b1, t1, t2))
                                faces.append((b1, t2, b2))
                    i += n_pts_line + 1
            else:
                # Fallback: Nutze alle Kanten des Meshes
                for i in range(face_mesh.n_cells):
                    cell = face_mesh.get_cell(i)
                    pts = cell.points
                    n_cell_pts = len(pts)
                    for j in range(n_cell_pts):
                        p1 = pts[j]
                        p2 = pts[(j + 1) % n_cell_pts]
                        
                        b1 = add_vert(p1)
                        b2 = add_vert(p2)
                        t1 = add_vert(p1 + n * height)
                        t2 = add_vert(p2 + n * height)
                        
                        if height > 0:
                            faces.append((b1, b2, t2))
                            faces.append((b1, t2, t1))
                        else:
                            faces.append((b1, t1, t2))
                            faces.append((b1, t2, b2))
            
            return verts, faces
            
        except Exception as e:
            logger.error(f" {e}")
            import traceback
            traceback.print_exc()
            return [], []

    def confirm_extrusion(self, operation="New Body"):
        """Bestätigt Extrusion und sendet Signal (wird von Enter/Rechtsklick gerufen)"""
        # 1. Daten sichern
        faces = list(self.selected_face_ids)
        height = self.extrude_height
        
        # 2. Aufräumen
        self._clear_preview()
        self.set_extrude_mode(False)
        self.set_all_bodies_visible(True) # Bodies wieder sichtbar machen
        
        # 3. Validierung & Senden
        if not faces:
            return
        if abs(height) < 0.001:
            return

        # Special Case: -1 (Legacy Body Face Selection) entfernen falls vorhanden
        if -1 in faces: faces.remove(-1)
        
        if faces:
            # Wir senden nur die IDs, das Main Window holt sich die Daten aus dem Detector
            self.extrude_requested.emit(list(faces), height, operation)
    
   

    def pick(self, x, y, selection_filter=None):
        """
        Präzises Picking mittels vtkCellPicker (Hardware-gestützt).
        Löst das Problem, dass falsche/verdeckte Flächen gewählt werden.
        """
        if not hasattr(self, 'detector'): return -1
        
        # Lazy Import
        if selection_filter is None:
             from gui.geometry_detector import GeometryDetector
             selection_filter = GeometryDetector.SelectionFilter.ALL

        # --- 1. BODY FACES (Hardware Picking) ---
        # Wir fragen VTK: Was sieht die Kamera an Pixel x,y?
        if "body_face" in selection_filter:
            import vtk
            picker = vtk.vtkCellPicker()
            picker.SetTolerance(0.005) # Sehr genau
            
            # Wichtig: VTK Y-Koordinate ist invertiert
            height = self.plotter.interactor.height()
            picker.Pick(x, height - y, 0, self.plotter.renderer)
            
            cell_id = picker.GetCellId()
            
            if cell_id != -1:
                # Wir haben etwas getroffen! Position holen.
                pos = np.array(picker.GetPickPosition())
                normal = np.array(picker.GetPickNormal())
                
                # Jetzt suchen wir im Detector, welche logische Fläche zu diesem Punkt passt.
                # Wir suchen die Fläche, die:
                # 1. Zum selben Body gehört (oder wir prüfen nur Distanz)
                # 2. Den Punkt 'pos' enthält (Distanz < Toleranz)
                # 3. Eine ähnliche Normale hat
                
                best_face = None
                best_dist = float('inf')
                
                for face in self.detector.selection_faces:
                    if face.domain_type != "body_face": continue
                    
                    # Distanz des Pick-Punkts zur Ebene der Fläche
                    dist_plane = abs(np.dot(pos - np.array(face.plane_origin), np.array(face.plane_normal)))
                    
                    # Normale vergleichen (Dot Product > 0.9 bedeutet fast parallel)
                    dot_normal = np.dot(normal, np.array(face.plane_normal))
                    
                    if dist_plane < 1.0 and dot_normal > 0.8:
                        # Prüfen, ob der Punkt auch wirklich nahe am Zentrum/Mesh liegt
                        # Einfache Distanz ist hier oft gut genug, da wir den exakten Klickpunkt haben
                        dist_center = np.linalg.norm(pos - np.array(face.plane_origin))
                        if dist_center < best_dist:
                            best_dist = dist_center
                            best_face = face
                
                if best_face:
                    return best_face.id

        # --- 2. SKETCH FACES (Analytisches Picking) ---
        # Sketches haben kein Mesh im CellPicker, daher hier weiter mathematisch
        # Aber nur, wenn wir kein Body-Face getroffen haben (oder Sketches bevorzugt sind)
        
        # Ray für Sketch-Berechnung
        ray_origin, ray_dir = self.get_ray_from_click(x, y)
        ray_start = np.array(ray_origin)
        
        hits = []
        for face in self.detector.selection_faces:
            if face.domain_type.startswith("sketch") and face.domain_type in selection_filter:
                hit = self.detector._intersect_ray_plane(ray_origin, ray_dir, face.plane_origin, face.plane_normal)
                if hit is None: continue
                
                # Prüfen ob Punkt im 2D-Polygon liegt
                proj_x, proj_y = self.detector._project_point_2d(hit, face.plane_origin, face.plane_x, face.plane_y)
                
                # Performance: Erst Bounding Box Check im 2D
                minx, miny, maxx, maxy = face.shapely_poly.bounds
                if not (minx <= proj_x <= maxx and miny <= proj_y <= maxy):
                    continue
                    
                if face.shapely_poly.contains(Point(proj_x, proj_y)):
                    dist = np.linalg.norm(np.array(hit) - ray_start)
                    hits.append((face.pick_priority, dist, face.id))

        if hits:
            hits.sort(key=lambda h: (-h[0], h[1]))
            return hits[0][2]

        return -1
        
    def _pick_body_face(self, x, y):
        """Versucht eine planare Fläche auf einem 3D-Körper zu finden"""
        cell_picker = vtk.vtkCellPicker()
        cell_picker.SetTolerance(0.005) # Etwas strikter
        cell_picker.Pick(x, self.plotter.interactor.height()-y, 0, self.plotter.renderer)
        
        if cell_picker.GetCellId() != -1:
            # ... (Body ID Logik wie bisher) ...
            
            if body_id is not None:
                normal = list(cell_picker.GetPickNormal())
                pos = cell_picker.GetPickPosition()
                
                # BEREINIGUNG: Fast-Nullen und Fast-Einsen glätten
                # Das verhindert Floating-Point Fehler bei geraden Flächen
                for i in range(3):
                    if abs(normal[i]) < 0.001: normal[i] = 0.0
                    if abs(normal[i] - 1.0) < 0.001: normal[i] = 1.0
                    if abs(normal[i] + 1.0) < 0.001: normal[i] = -1.0
                
                # Signal senden
                self.custom_plane_clicked.emit(tuple(pos), tuple(normal))
                
                # NEU: Visualisierung der gewählten Ebene (optional)
                self._draw_plane_hover_highlight(pos, normal)
                return True
        return False
    
    def _hover_body_face(self, x, y):
        """Hebt Body-Flächen beim Hover hervor"""
        if not self.bodies: return
            
        try:
            import vtk
            cell_picker = vtk.vtkCellPicker()
            cell_picker.SetTolerance(0.01)
            height = self.plotter.interactor.height()
            
            picked = cell_picker.Pick(x, height - y, 0, self.plotter.renderer)
            cell_id = cell_picker.GetCellId()
            
            if picked and cell_id != -1:
                actor = cell_picker.GetActor()
                if actor is None or not actor.GetVisibility():
                    if self.hovered_body_face is not None:
                        self.hovered_body_face = None
                        self._clear_body_face_highlight()
                    return
                
                body_id = None
                # FIX: Suche Body ID flexibel
                for bid, actors in self._body_actors.items():
                    for name in actors:
                        if name in self.plotter.renderer.actors:
                            body_actor = self.plotter.renderer.actors[name]
                            if body_actor is actor:
                                body_id = bid
                                break
                    if body_id: break
                
                if body_id is not None:
                    normal = cell_picker.GetPickNormal()
                    pos = cell_picker.GetPickPosition()
                    
                    new_hover = (body_id, cell_id, tuple(normal), tuple(pos))
                    if self.hovered_body_face != new_hover:
                        self.hovered_body_face = new_hover
                        self._draw_body_face_highlight(pos, normal)
                    return
            
            if self.hovered_body_face is not None:
                self.hovered_body_face = None
                self._clear_body_face_highlight()
                
        except Exception:
            pass
    
    def _draw_body_face_highlight(self, pos, normal):
        """Zeichnet Highlight auf gehoverter Body-Fläche"""
        self._clear_body_face_highlight()
        try:
            center = np.array(pos)
            n = np.array(normal)
            norm_len = np.linalg.norm(n)
            if norm_len > 0:
                n = n / norm_len
            else:
                n = np.array([0, 0, 1])
            
            # Erstelle einen Kreis senkrecht zur Normalen
            radius = 5.0
            
            # Finde zwei Vektoren senkrecht zur Normalen
            if abs(n[2]) < 0.9:
                u = np.cross(n, [0, 0, 1])
            else:
                u = np.cross(n, [1, 0, 0])
            u = u / np.linalg.norm(u)
            v = np.cross(n, u)
            
            # Kreis-Punkte
            points = []
            for i in range(33):
                angle = i * 2 * math.pi / 32
                p = center + radius * (math.cos(angle) * u + math.sin(angle) * v)
                points.append(p)
            
            # Als Linie zeichnen
            pts = np.array(points)
            lines = pv.lines_from_points(pts)
            self.plotter.add_mesh(lines, color='cyan', line_width=4, name='body_face_highlight')
            
            # Normale als Pfeil (zeigt Extrude-Richtung)
            arrow_end = center + n * 8
            arrow = pv.Arrow(start=center, direction=n, scale=8)
            self.plotter.add_mesh(arrow, color='cyan', name='body_face_arrow')
            
            self.plotter.update()
        except Exception as e:
            logger.error(f" {e}")
    
    def _clear_body_face_highlight(self):
        """Entfernt Body-Face-Highlight"""
        try:
            self.plotter.remove_actor('body_face_highlight')
        except: pass
        try:
            self.plotter.remove_actor('body_face_arrow')
        except: pass
        try:
            self.plotter.update()
        except: pass
    
    def _click_body_face(self):
        """Klick auf Body-Face - bereitet Extrusion vor"""
        if self.hovered_body_face is None:
            return
        
        body_id, cell_id, normal, pos = self.hovered_body_face
        
        # Speichere die Flächen-Daten für Extrusion
        # Wir erstellen ein "detected_face" aus der Body-Fläche
        self.body_face_extrude = {
            'body_id': body_id,
            'cell_id': cell_id,
            'normal': normal,
            'origin': pos,
            'mesh': self.bodies.get(body_id, {}).get('mesh')
        }
        
        # Markiere als ausgewählt
        self.selected_faces.clear()
        self.selected_faces.add(-1)  # Special marker für Body-Face
        
        logger.info(f"Body face selected: body={body_id}, normal={normal}, pos={pos}")
        
        # Zeige Preview
        self._draw_body_face_selection(pos, normal)
    
    def _draw_body_face_selection(self, pos, normal):
        """Zeichnet Auswahl-Highlight auf Body-Face"""
        try:
            center = np.array(pos)
            n = np.array(normal)
            n = n / np.linalg.norm(n) if np.linalg.norm(n) > 0 else np.array([0,0,1])
            
            # Größerer Kreis für Auswahl
            radius = 8.0
            if abs(n[2]) < 0.9:
                u = np.cross(n, [0, 0, 1])
            else:
                u = np.cross(n, [1, 0, 0])
            u = u / np.linalg.norm(u)
            v = np.cross(n, u)
            
            points = []
            for i in range(33):
                angle = i * 2 * math.pi / 32
                p = center + radius * (math.cos(angle) * u + math.sin(angle) * v)
                points.append(p)
            
            pts = np.array(points)
            lines = pv.lines_from_points(pts)
            self.plotter.add_mesh(lines, color='orange', line_width=4, name='body_face_selection')
            self.plotter.update()
        except:
            pass
    
    def _clear_preview(self):
        if self._preview_actor: 
            try: self.plotter.remove_actor(self._preview_actor)
            except: pass; self._preview_actor=None

    def _draw_selectable_faces(self):
        """Zeichnet NUR die gehoverte und ausgewählte Flächen - nicht alle"""
        self._clear_face_actors()
        
        for i, face in enumerate(self.detected_faces):
            is_selected = i in self.selected_faces
            is_hovered = i == self.hovered_face
            
            # Nur zeichnen wenn selected oder hovered!
            if not is_selected and not is_hovered:
                continue
            
            if is_selected: 
                col = 'orange'
                op = 0.7
            else:  # hovered
                col = '#44aaff'
                op = 0.5
            
            # Body-Face oder Sketch-Face?
            if face.get('type') == 'body_face':
                self._draw_body_face_overlay(i, face, col, op)
            else:
                # Sketch-Face
                v, f = self.get_extrusion_data(i, 0)
                if v:
                    vv = np.array(v, dtype=np.float32)
                    ff = []
                    for x in f: ff.extend([3]+list(x))
                    mesh = pv.PolyData(vv, np.array(ff, dtype=np.int32))
                    n = f"face_{i}"
                    self.plotter.add_mesh(mesh, color=col, opacity=op, name=n, pickable=True)
                    self._face_actors.append(n)
        
        self.plotter.update()
    
    def _draw_body_face_overlay(self, face_idx, face, color, opacity):
        """Zeichnet Overlay für eine Body-Fläche"""
        try:
            mesh = face.get('mesh')
            cell_ids = face.get('cell_ids', [])
            
            if mesh is None or not cell_ids:
                return
            
            # Extrahiere nur die Zellen dieser Fläche
            face_mesh = mesh.extract_cells(cell_ids)
            
            n = f"face_{face_idx}"
            self.plotter.add_mesh(face_mesh, color=color, opacity=opacity, 
                                  name=n, pickable=True, show_edges=False)
            self._face_actors.append(n)
        except Exception as e:
            logger.error(f" {e}")

    def _clear_face_actors(self):
        for n in self._face_actors:
            try: self.plotter.remove_actor(n)
            except: pass
        self._face_actors.clear()

    def _render_sketch(self, s):
        norm = tuple(getattr(s,'plane_normal',(0,0,1)))
        orig = getattr(s,'plane_origin',(0,0,0))
        
        # FIX: Wenn wir eine gespeicherte X-Achse haben, NUTZEN wir sie!
        # Das verhindert, dass die Skizze sich dreht.
        cached_x = getattr(s, 'plane_x_dir', None)
        cached_y = getattr(s, 'plane_y_dir', None)
        
        sid = getattr(s,'id',id(s))
        
        # Lokale Funktion mit Closure über Koordinatensystem
        def t3d(x, y): 
            if cached_x and cached_y:
                # Exakte Transformation: P = Origin + x*X_Axis + y*Y_Axis
                px = orig[0] + x * cached_x[0] + y * cached_y[0]
                py = orig[1] + x * cached_x[1] + y * cached_y[1]
                pz = orig[2] + x * cached_x[2] + y * cached_y[2]
                return (px, py, pz)
            else:
                # Fallback zur alten Berechnung (Raten)
                return self._transform_2d_to_3d(x, y, norm, orig)
        
        # Linien
        for i,l in enumerate(getattr(s,'lines',[])):
            col = 'gray' if getattr(l,'construction',False) else '#4d94ff'
            self.plotter.add_mesh(pv.Line(t3d(l.start.x,l.start.y), t3d(l.end.x,l.end.y)), color=col, line_width=3, name=f"s_{sid}_l_{i}")
            self._sketch_actors.append(f"s_{sid}_l_{i}")
            
        # Kreise
        for i,c in enumerate(getattr(s,'circles',[])):
            pts = [t3d(c.center.x+c.radius*math.cos(j*6.28/64), c.center.y+c.radius*math.sin(j*6.28/64)) for j in range(65)]
            col = 'gray' if getattr(c,'construction',False) else '#4d94ff'
            self.plotter.add_mesh(pv.lines_from_points(np.array(pts)), color=col, line_width=3, name=f"s_{sid}_c_{i}")
            self._sketch_actors.append(f"s_{sid}_c_{i}")
            
        # Arcs (Neu: Bessere Darstellung)
        for i, arc in enumerate(getattr(s, 'arcs', [])):
            col = 'gray' if getattr(arc,'construction',False) else '#4d94ff'
            pts = []
            start = arc.start_angle
            end = arc.end_angle
            sweep = end - start
            if sweep < 0.1: sweep += 360
            steps = 32
            for j in range(steps+1):
                t = math.radians(start + sweep * (j/steps))
                x = arc.center.x + arc.radius * math.cos(t)
                y = arc.center.y + arc.radius * math.sin(t)
                pts.append(t3d(x, y))
            if len(pts) > 1:
                self.plotter.add_mesh(pv.lines_from_points(np.array(pts)), color=col, line_width=3, name=f"s_{sid}_a_{i}")
                self._sketch_actors.append(f"s_{sid}_a_{i}")
                
        # Splines (Neu!)
        for i, spline in enumerate(getattr(s, 'splines', [])):
            col = 'gray' if getattr(spline,'construction',False) else '#4d94ff'
            pts_2d = []
            # Punkte holen
            if hasattr(spline, 'get_curve_points'):
                 pts_2d = spline.get_curve_points(segments_per_span=10)
            elif hasattr(spline, 'to_lines'):
                 lines = spline.to_lines(segments_per_span=10)
                 if lines:
                     pts_2d.append((lines[0].start.x, lines[0].start.y))
                     for l in lines: pts_2d.append((l.end.x, l.end.y))
            
            if len(pts_2d) > 1:
                pts_3d = [t3d(p[0], p[1]) for p in pts_2d]
                self.plotter.add_mesh(pv.lines_from_points(np.array(pts_3d)), color=col, line_width=3, name=f"s_{sid}_sp_{i}")
                self._sketch_actors.append(f"s_{sid}_sp_{i}")

    def _show_selection_planes(self):
        sz = 150; op = 0.25
        self.plotter.add_mesh(pv.Plane(center=(0,0,0), direction=(0,0,1), i_size=sz, j_size=sz), color='blue', opacity=op, name='xy', pickable=True)
        self.plotter.add_mesh(pv.Plane(center=(0,0,0), direction=(0,1,0), i_size=sz, j_size=sz), color='green', opacity=op, name='xz', pickable=True)
        self.plotter.add_mesh(pv.Plane(center=(0,0,0), direction=(1,0,0), i_size=sz, j_size=sz), color='red', opacity=op, name='yz', pickable=True)
        self._plane_actors = {'xy':'xy','xz':'xz','yz':'yz'}

    def _hide_selection_planes(self):
        for n in ['xy','xz','yz']: 
            try: self.plotter.remove_actor(n)
            except: pass
        self._plane_actors.clear()

    def set_view(self, view_name):
        """Setzt eine Standardansicht"""
        if not HAS_PYVISTA:
            return
        
        views = {
            'iso': 'iso',
            'top': 'xy',
            'front': 'xz', 
            'right': 'yz',
            'back': '-xz',
            'left': '-yz',
            'bottom': '-xy'
        }
        
        if view_name in views:
            try:
                self.plotter.view_vector(views[view_name])
                self.plotter.reset_camera()
                self.view_changed.emit()
            except:
                # Fallback
                if view_name == 'iso':
                    self.plotter.view_isometric()
                elif view_name == 'top':
                    self.plotter.view_xy()
                elif view_name == 'front':
                    self.plotter.view_xz()
                elif view_name == 'right':
                    self.plotter.view_yz()
                self.plotter.reset_camera()
                self.view_changed.emit()

    # ==================== MODALE NUMERISCHE EINGABE ====================
    def _show_numeric_input_overlay(self, text: str):
        """Zeigt Floating-Label für numerische Eingabe während Transform"""
        from PySide6.QtWidgets import QLabel
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QCursor

        # Entferne altes Overlay (falls vorhanden)
        self._hide_numeric_input_overlay()

        # Erstelle neues Label
        self._numeric_overlay = QLabel(f"Value: {text}", self)
        self._numeric_overlay.setStyleSheet("""
            QLabel {
                background: rgba(0, 120, 212, 220);
                color: white;
                padding: 8px 12px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                border: 2px solid rgba(255, 255, 255, 100);
            }
        """)
        self._numeric_overlay.setWindowFlags(Qt.ToolTip)  # Bleibt über allem
        self._numeric_overlay.adjustSize()

        # Position nahe Cursor (leicht versetzt nach rechts unten)
        cursor_pos = QCursor.pos()
        overlay_pos = self.mapFromGlobal(cursor_pos)
        self._numeric_overlay.move(overlay_pos.x() + 20, overlay_pos.y() + 20)
        self._numeric_overlay.show()

        logger.debug(f"Numeric overlay shown: {text}")

    def _hide_numeric_input_overlay(self):
        """Versteckt Floating-Label für numerische Eingabe"""
        if hasattr(self, '_numeric_overlay') and self._numeric_overlay:
            self._numeric_overlay.deleteLater()
            self._numeric_overlay = None

    def _apply_numeric_transform(self, value: float):
        """
        Wendet numerischen Wert auf aktiven Transform an.

        Verhalten basierend auf Modus:
        - Move: Bewegt um 'value' Einheiten (auf gesperrter Achse falls aktiv)
        - Rotate: Rotiert um 'value' Grad
        - Scale: Skaliert mit Faktor 'value'
        """
        if not self.transform_state or not self.transform_state.active_body_id:
            logger.warning("Kein aktiver Transform - numerischer Wert ignoriert")
            return

        mode = self.transform_state.mode
        body_id = self.transform_state.active_body_id

        # Bestimme Transform-Data basierend auf Modus
        if mode == "move":
            # Move: Nutze axis_lock falls vorhanden
            axis_lock = self.transform_state.axis_lock

            if axis_lock == "X":
                translation = [value, 0, 0]
            elif axis_lock == "Y":
                translation = [0, value, 0]
            elif axis_lock == "Z":
                translation = [0, 0, value]
            else:
                # Kein Lock: Bewege entlang Kamera-Blickrichtung (oder X als Default)
                logger.warning("Keine Achse gesperrt - verwende X-Achse als Default")
                translation = [value, 0, 0]

            data = {"translation": translation}
            logger.info(f"Move mit numerischem Wert: {translation}")

        elif mode == "rotate":
            # Rotate: Winkel in Grad
            axis_lock = self.transform_state.axis_lock or "Z"  # Default Z-Achse
            data = {"axis": axis_lock, "angle": value}
            logger.info(f"Rotate um {value}° auf {axis_lock}-Achse")

        elif mode == "scale":
            # Scale: Faktor (1.0 = keine Änderung)
            if value <= 0:
                logger.error("Scale-Faktor muss > 0 sein")
                return
            data = {"factor": value}
            logger.info(f"Scale mit Faktor {value}")

        else:
            logger.error(f"Unbekannter Transform-Modus: {mode}")
            return

        # Emittiere Transform-Signal
        self.body_transform_requested.emit(body_id, mode, data)

        # Reset Transform-State
        self.transform_state.reset()
        self.hide_transform_gizmo()

    def update(self): self.plotter.update(); super().update()


def create_viewport(parent=None):
    return PyVistaViewport(parent) if HAS_PYVISTA else QWidget(parent)