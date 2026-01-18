"""
MashCad - Edge Selection Mixin V7.0 (Stable & Fast)
Fix: Detector-Update beim Start (löst das "keine Flächen"-Problem)
Fix: Caching gegen Flackern
"""

import numpy as np
from typing import Optional, List, Dict, Set, Tuple, Callable
from dataclasses import dataclass
from loguru import logger

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False


# ==================== Datenstrukturen ====================

@dataclass
class SelectableEdge:
    """Repräsentiert eine selektierbare Kante."""
    id: int
    body_id: str
    build123d_edge: object
    center: Tuple[float, float, float]
    line_mesh: object
    length: float = 0.0


# ==================== Farbkonstanten ====================

EDGE_COLORS = {
    "normal": "#CCCCCC",      # Hellgrau
    "hover": "#00FFFF",       # Cyan (Neon)
    "selected": "#FFaa00",    # Orange/Gold
    "failed": "#FF0000",      # Rot
}

class EdgeSelectionMixin:
    """
    Mixin für PyVistaViewport zur interaktiven Kantenauswahl.
    """

    def _init_edge_selection(self):
        self.edge_select_mode: bool = False
        self._edge_selection_body_id: Optional[str] = None
        self._selectable_edges: List[SelectableEdge] = []
        self._selected_edge_ids: Set[int] = set()
        
        # State für Hover
        self._hovered_edge_id: int = -1
        self._hovered_loop_ids: Set[int] = set()
        
        # Caching gegen Flackern
        self._last_hovered_face_id: int = -1 
        
        self._edge_actors: List[str] = []
        self._edge_counter: int = 0
        
        if not hasattr(self, '_get_body_by_id'):
            self._get_body_by_id: Optional[Callable] = None
        
        self._line_width_normal = 4.0
        self._line_width_hover = 7.0

    def set_edge_selection_callbacks(self, get_body_by_id: Callable):
        self._get_body_by_id = get_body_by_id

    # ==================== Mode Management ====================

    def start_edge_selection_mode(self, body_id: str):
        if not HAS_PYVISTA: return
        self._init_edge_selection() 
        
        self.edge_select_mode = True
        self._edge_selection_body_id = body_id
        
        if hasattr(self, 'set_pending_transform_mode'):
            self.set_pending_transform_mode(False)

        # Detector aktualisieren
        if hasattr(self, '_update_detector_for_picking'):
            self._update_detector_for_picking()

        # Kanten laden
        self._extract_edges_from_body(body_id)
        
        # WICHTIG: Hier einmalig alte Actors löschen, bevor wir neu zeichnen
        self._clear_edge_actors()
        
        # Zeichnen (erstellt die Actors initial)
        self._draw_edges_modern()
        
        from PySide6.QtCore import Qt
        self.setCursor(Qt.PointingHandCursor)
        self.plotter.render()
        
        logger.info(f"Fillet Mode: {len(self._selectable_edges)} Kanten bereit.")

    def stop_edge_selection_mode(self):
        self.edge_select_mode = False
        self._edge_selection_body_id = None
        self._clear_edge_actors()
        self._selectable_edges.clear()
        self._selected_edge_ids.clear()
        self._hovered_edge_id = -1
        self._hovered_loop_ids.clear()
        self._last_hovered_face_id = -1
        
        from PySide6.QtCore import Qt
        self.setCursor(Qt.ArrowCursor)
        
        if hasattr(self, 'plotter'): self.plotter.render()

    # ==================== Extraction ====================

    def _extract_edges_from_body(self, body_id: str):
        self._selectable_edges.clear()
        self._edge_counter = 0

        if not self._get_body_by_id: return
        body = self._get_body_by_id(body_id)
        if not body: return
        
        solid = getattr(body, '_build123d_solid', None)
        if not solid: return

        try:
            for edge in solid.edges():
                try:
                    line_mesh = self._create_edge_polyline(edge)
                    if line_mesh:
                        sel_edge = SelectableEdge(
                            id=self._edge_counter,
                            body_id=body_id,
                            build123d_edge=edge,
                            center=edge.center().to_tuple(),
                            line_mesh=line_mesh,
                            length=getattr(edge, 'length', 0.0)
                        )
                        self._selectable_edges.append(sel_edge)
                        self._edge_counter += 1
                except: continue
        except Exception as e:
            logger.error(f"Extraction Error: {e}")

    def _create_edge_polyline(self, edge) -> Optional[object]:
        try:
            from build123d import GeomType
            try: is_line = edge.geom_type() == GeomType.LINE
            except: is_line = False
            resolution = 2 if is_line else 32
            
            points = []
            for t in np.linspace(0, 1, resolution):
                pt = edge.position_at(t)
                points.append([pt.X, pt.Y, pt.Z])
            
            if len(points) < 2: return None
            return pv.lines_from_points(np.array(points))
        except: return None

    # ==================== Visualisierung ====================

    def _draw_edges_modern(self):
        """
        Zeichnet Kanten oder aktualisiert deren Status.
        PERFORMANCE-FIX: Nutzt Property-Updates statt Löschen/Neu-Erstellen.
        Verhindert das Flackern bei Mausbewegungen.
        """
        # HINWEIS: self._clear_edge_actors() HIER ENTFERNT! 
        # Wir wollen existierende Actors behalten und nur updaten.

        for edge in self._selectable_edges:
            name = f"edge_line_{edge.id}"
            
            # 1. Status bestimmen
            is_sel = edge.id in self._selected_edge_ids
            is_hov = edge.id == self._hovered_edge_id
            is_loop = edge.id in self._hovered_loop_ids
            
            # 2. Visuelle Parameter festlegen
            if is_sel:
                col = EDGE_COLORS["selected"]
                width = self._line_width_hover
                prio = 10
            elif is_hov or is_loop: 
                col = EDGE_COLORS["hover"]
                width = self._line_width_hover
                prio = 10
            else:
                col = EDGE_COLORS["normal"]
                width = self._line_width_normal
                prio = 1 # Niedrige Prio, damit selektierte darüber liegen
            
            # 3. Actor holen oder erstellen
            actor = self.plotter.renderer.actors.get(name)
            
            if actor:
                # A. UPDATE (Schnell & Flackerfrei)
                prop = actor.GetProperty()
                
                # Farbe setzen
                rgb = pv.Color(col).float_rgb
                prop.SetColor(rgb)
                prop.SetLineWidth(width)
                
                # Tiefen-Offset aktualisieren (damit Selektiertes "vorne" ist)
                self._set_actor_on_top(name, prio)
                
            else:
                # B. NEU ERSTELLEN (Nur beim ersten Aufruf)
                self.plotter.add_mesh(
                    edge.line_mesh,
                    color=col,
                    opacity=1.0,
                    line_width=width,
                    render_lines_as_tubes=True,
                    lighting=False, # Neon-Effekt
                    name=name,
                    pickable=True
                )
                self._edge_actors.append(name)
                self._set_actor_on_top(name, prio)

    def _set_actor_on_top(self, name, priority=1):
        try:
            actor = self.plotter.renderer.actors.get(name)
            if actor:
                mapper = actor.GetMapper()
                mapper.SetResolveCoincidentTopologyToPolygonOffset()
                offset = -5 * priority
                mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(offset, offset)
        except: pass

    def _clear_edge_actors(self):
        for name in self._edge_actors:
            try: self.plotter.remove_actor(name)
            except: pass
        self._edge_actors.clear()

    # ==================== Picking & Logic ====================

    def pick_edge(self, x, y) -> int:
        """Versucht präzise eine einzelne Linie zu treffen."""
        if not self._selectable_edges: return -1
        import vtk
        picker = vtk.vtkPropPicker()
        picker.Pick(x, self.plotter.interactor.height() - y, 0, self.plotter.renderer)
        actor = picker.GetActor()
        
        if actor:
            for edge in self._selectable_edges:
                if self.plotter.renderer.actors.get(f"edge_line_{edge.id}") == actor:
                    return edge.id
        return -1

    def _get_loop_ids_for_face(self, face_id: int) -> Set[int]:
        """
        Berechnet die Loop-Kanten für eine gegebene Face-ID.
        Wird nur aufgerufen, wenn sich die Face-ID ändert.
        """
        if not hasattr(self, 'detector'): return set()
        
        face = next((f for f in self.detector.selection_faces if f.id == face_id), None)
        if not face or face.domain_type != 'body_face': return set()
        
        face_origin = np.array(face.plane_origin)
        face_normal = np.array(face.plane_normal)
        
        found_ids = set()
        tolerance = 0.5 # mm Toleranz
        
        # Geometrischer Check: Welche Kanten liegen in der Ebene der Fläche?
        for sel_edge in self._selectable_edges:
            edge_center = np.array(sel_edge.center)
            vec = edge_center - face_origin
            dist_to_plane = abs(np.dot(vec, face_normal))
            
            if dist_to_plane < tolerance:
                found_ids.add(sel_edge.id)
                
        return found_ids

    def handle_edge_mouse_move(self, x, y):
        """
        Optimierter Handler gegen Flackern.
        """
        if not self.edge_select_mode: return False
        
        # 1. Kante direkt getroffen?
        eid = self.pick_edge(x, y)
        
        # 2. Wenn Kante getroffen: Loop-Logik überspringen
        if eid != -1:
            self._hovered_loop_ids.clear()
            self._last_hovered_face_id = -1
            
            if eid != self._hovered_edge_id:
                self._hovered_edge_id = eid
                self._draw_edges_modern()
                self.plotter.render()
            return True
            
        # 3. Keine Kante: Prüfe Fläche (Loop Preview)
        self._hovered_edge_id = -1
        
        if hasattr(self, 'pick'):
            # Pick Face (schnell via VTK)
            face_id = self.pick(x, y, selection_filter={"body_face"})
            
            # CACHING: Nur neu berechnen, wenn wir auf einer NEUEN Fläche sind
            if face_id != self._last_hovered_face_id:
                self._last_hovered_face_id = face_id
                
                if face_id != -1:
                    # Neue Fläche -> Loop berechnen
                    self._hovered_loop_ids = self._get_loop_ids_for_face(face_id)
                else:
                    # Leerraum -> Loop löschen
                    self._hovered_loop_ids.clear()
                
                # Nur hier neu zeichnen!
                self._draw_edges_modern()
                self.plotter.render()
                
        return True

    def handle_edge_click(self, x, y, is_multi) -> bool:
        if not self.edge_select_mode: return False
        
        # A. Klick auf einzelne Kante
        if self._hovered_edge_id != -1:
            eid = self._hovered_edge_id
            if eid in self._selected_edge_ids:
                self._selected_edge_ids.remove(eid)
            else:
                if not is_multi: self._selected_edge_ids.clear()
                self._selected_edge_ids.add(eid)
            
            self._draw_edges_modern()
            if hasattr(self, 'edge_selection_changed'):
                self.edge_selection_changed.emit(len(self._selected_edge_ids))
            self.plotter.render()
            return True
            
        # B. Klick auf Fläche (Loop)
        elif self._hovered_loop_ids:
            if not is_multi: self._selected_edge_ids.clear()
            
            for eid in self._hovered_loop_ids:
                self._selected_edge_ids.add(eid)
                
            logger.info(f"Loop Select: {len(self._hovered_loop_ids)} Kanten markiert.")
                
            self._draw_edges_modern()
            if hasattr(self, 'edge_selection_changed'):
                self.edge_selection_changed.emit(len(self._selected_edge_ids))
            self.plotter.render()
            return True
            
        return False
    
    

    # ==================== Getter ====================

    def get_selected_edges(self):
        return [e.build123d_edge for e in self._selectable_edges if e.id in self._selected_edge_ids]
    
    def get_selected_edge_ids(self) -> Set[int]:
        return self._selected_edge_ids.copy()

    def get_edge_selectors(self):
        return [e.center for e in self._selectable_edges if e.id in self._selected_edge_ids]

    def select_all_edges(self):
        self._selected_edge_ids = {e.id for e in self._selectable_edges}
        self._draw_edges_modern()
        if hasattr(self, 'edge_selection_changed'):
            self.edge_selection_changed.emit(len(self._selected_edge_ids))
        self.plotter.render()