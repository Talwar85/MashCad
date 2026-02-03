"""
MashCad - Edge Selection Mixin V8.0 (Performance Optimized)
Phase 7.1: Batch Rendering + Edge Filtering + Spatial Index

Performance-Probleme in V7:
- 1 Actor pro Kante → 174 Kanten = 174 Actors (LANGSAM)
- Alle Kanten werden gezeigt (auch unsinnige für Fillet)
- Picking iteriert über alle Kanten

Lösungen in V8:
- Batch Rendering: Alle normalen Kanten in EINEM Actor
- Edge Filterung: Nur relevante Kanten für Fillet/Chamfer
- Spatial Index: Schnelles Picking via BoundingBox
"""

import numpy as np
from typing import Optional, List, Dict, Set, Tuple, Callable
from dataclasses import dataclass, field
from loguru import logger

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

from gui.viewport.render_queue import request_render  # Phase 4: Performance


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
    is_convex: bool = True  # True = Außenkante, False = Innenkante
    points: np.ndarray = field(default=None)  # Punkte für Batch-Rendering
    bbox: Tuple[float, float, float, float, float, float] = None  # xmin,xmax,ymin,ymax,zmin,zmax


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
    V8.0: Batch Rendering + Edge Filtering für bessere Performance.
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

        # V8: Batch Rendering State
        self._batch_mesh_normal: Optional[object] = None  # PolyData für alle normalen Kanten
        self._batch_mesh_selected: Optional[object] = None  # PolyData für selektierte Kanten
        self._edge_filter_mode: str = "all"  # "all", "convex", "concave"

    def set_edge_selection_callbacks(self, get_body_by_id: Callable):
        self._get_body_by_id = get_body_by_id

    # ==================== Mode Management ====================

    def start_edge_selection_mode(self, body_id: str, filter_mode: str = "all"):
        """
        V8: Startet Edge-Selection mit optionalem Filter.

        Args:
            body_id: ID des Bodies
            filter_mode: "all" (default), "convex" (Chamfer), "concave" (Fillet)
        """
        if not HAS_PYVISTA:
            return

        try:
            self._init_edge_selection()

            self.edge_select_mode = True
            self._edge_selection_body_id = body_id
            self._edge_filter_mode = filter_mode

            if hasattr(self, 'set_pending_transform_mode'):
                self.set_pending_transform_mode(False)

            # Detector aktualisieren
            if hasattr(self, '_update_detector_for_picking'):
                self._update_detector_for_picking()

            # WICHTIG: Erst alte Actors löschen
            self._clear_edge_actors()

            # Kanten laden (mit Filter)
            self._extract_edges_from_body(body_id)

            n_edges = len(self._selectable_edges)

            # Info über gefilterte Kanten
            filter_info = ""
            if filter_mode == "concave":
                filter_info = " (nur Innenkanten)"
            elif filter_mode == "convex":
                filter_info = " (nur Außenkanten)"

            if n_edges == 0:
                logger.warning(f"Keine Kanten gefunden{filter_info}")
                return

            # V8: Batch-Rendering (statt einzelne Actors)
            self._draw_edges_modern()

            from PySide6.QtCore import Qt
            self.setCursor(Qt.PointingHandCursor)
            request_render(self.plotter)

            logger.info(f"Edge Mode: {n_edges} Kanten{filter_info} (V8 Batch-Rendering)")

        except Exception as e:
            logger.error(f"Edge Selection Mode konnte nicht gestartet werden: {e}")
            import traceback
            traceback.print_exc()
            self.edge_select_mode = False
            self._clear_edge_actors()

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
        
        if hasattr(self, 'plotter'): request_render(self.plotter)

    # ==================== Extraction ====================

    def _extract_edges_from_body(self, body_id: str):
        """
        V8: Extrahiert Kanten mit Konkavitäts-Info und BBox für schnelles Picking.
        """
        self._selectable_edges.clear()
        self._edge_counter = 0

        if not self._get_body_by_id: return
        body = self._get_body_by_id(body_id)
        if not body: return

        solid = getattr(body, '_build123d_solid', None)
        if not solid: return

        # V8: Berechne Konkavität für alle Kanten
        edge_convexity = self._compute_edge_convexity(solid)

        try:
            for i, edge in enumerate(solid.edges()):
                try:
                    # Polyline und Punkte extrahieren
                    points = self._extract_edge_points(edge)
                    if points is None or len(points) < 2:
                        continue

                    # BBox berechnen für schnelles Picking
                    bbox = (
                        points[:, 0].min(), points[:, 0].max(),
                        points[:, 1].min(), points[:, 1].max(),
                        points[:, 2].min(), points[:, 2].max()
                    )

                    # Konkavität aus vorberechneter Map
                    is_convex = edge_convexity.get(i, True)

                    # V8: Filter anwenden
                    if self._edge_filter_mode == "convex" and not is_convex:
                        continue
                    if self._edge_filter_mode == "concave" and is_convex:
                        continue

                    line_mesh = pv.lines_from_points(points)

                    sel_edge = SelectableEdge(
                        id=self._edge_counter,
                        body_id=body_id,
                        build123d_edge=edge,
                        center=edge.center().to_tuple(),
                        line_mesh=line_mesh,
                        length=getattr(edge, 'length', 0.0),
                        is_convex=is_convex,
                        points=points,
                        bbox=bbox
                    )
                    self._selectable_edges.append(sel_edge)
                    self._edge_counter += 1
                except:
                    continue
        except Exception as e:
            logger.error(f"Extraction Error: {e}")

    def _compute_edge_convexity(self, solid) -> Dict[int, bool]:
        """
        V8: Berechnet für jede Kante ob sie konvex (Außenkante) oder konkav (Innenkante) ist.
        Konkave Kanten sind typisch für Fillet, konvexe für Chamfer.
        """
        convexity = {}

        try:
            from OCP.BRepAdaptor import BRepAdaptor_Surface
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
            from OCP.TopoDS import TopoDS

            ocp_shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

            # Map: Edge → anliegende Faces
            edge_faces: Dict[int, List] = {}
            edge_index = 0

            edge_explorer = TopExp_Explorer(ocp_shape, TopAbs_EDGE)
            while edge_explorer.More():
                edge = TopoDS.Edge_s(edge_explorer.Current())
                edge_faces[edge_index] = []

                # Finde Faces die diese Kante teilen
                face_explorer = TopExp_Explorer(ocp_shape, TopAbs_FACE)
                while face_explorer.More():
                    face = TopoDS.Face_s(face_explorer.Current())
                    face_edge_exp = TopExp_Explorer(face, TopAbs_EDGE)
                    while face_edge_exp.More():
                        if face_edge_exp.Current().IsSame(edge):
                            edge_faces[edge_index].append(face)
                            break
                        face_edge_exp.Next()
                    face_explorer.Next()

                edge_index += 1
                edge_explorer.Next()

            # Berechne Konkavität basierend auf Face-Normalen
            for edge_idx, faces in edge_faces.items():
                if len(faces) >= 2:
                    try:
                        # Hole Normalen der beiden Faces am Mittelpunkt der Kante
                        surf1 = BRepAdaptor_Surface(faces[0])
                        surf2 = BRepAdaptor_Surface(faces[1])

                        # Mittelpunkt der UV-Parameter
                        u1 = (surf1.FirstUParameter() + surf1.LastUParameter()) / 2
                        v1 = (surf1.FirstVParameter() + surf1.LastVParameter()) / 2
                        u2 = (surf2.FirstUParameter() + surf2.LastUParameter()) / 2
                        v2 = (surf2.FirstVParameter() + surf2.LastVParameter()) / 2

                        # Normalen berechnen
                        from OCP.GeomLProp import GeomLProp_SLProps
                        props1 = GeomLProp_SLProps(surf1.Surface().Surface(), u1, v1, 1, 0.001)
                        props2 = GeomLProp_SLProps(surf2.Surface().Surface(), u2, v2, 1, 0.001)

                        if props1.IsNormalDefined() and props2.IsNormalDefined():
                            n1 = props1.Normal()
                            n2 = props2.Normal()

                            # Winkel zwischen Normalen
                            dot = n1.X() * n2.X() + n1.Y() * n2.Y() + n1.Z() * n2.Z()

                            # Konvex wenn Normalen "auseinander" zeigen (dot < 0)
                            convexity[edge_idx] = dot < 0.1  # Mit etwas Toleranz
                        else:
                            convexity[edge_idx] = True
                    except:
                        convexity[edge_idx] = True
                else:
                    convexity[edge_idx] = True  # Freie Kante = konvex

        except Exception as e:
            logger.debug(f"Edge convexity calculation failed: {e}")

        return convexity

    def _extract_edge_points(self, edge) -> Optional[np.ndarray]:
        """Extrahiert Punkte einer Kante für Polyline."""
        try:
            edge_length = getattr(edge, 'length', 0.0)
            if edge_length < 0.001:  # < 1 Mikron
                return None

            from build123d import GeomType
            try:
                is_line = edge.geom_type() == GeomType.LINE
            except:
                is_line = False

            # V8: Weniger Punkte bei vielen Kanten
            resolution = 2 if is_line else 16  # Reduziert von 32

            points = []
            for t in np.linspace(0, 1, resolution):
                try:
                    pt = edge.position_at(t)
                    if pt is not None:
                        points.append([pt.X, pt.Y, pt.Z])
                except:
                    continue

            if len(points) < 2:
                return None

            points_arr = np.array(points)

            # Check for degenerate polyline (alle Punkte gleich)
            # WICHTIG: Geschlossene Kurven (Kreise) sind OK - nur prüfen ob ALLE Punkte gleich sind
            if len(points_arr) > 2:
                # Prüfe ob alle Punkte nahezu identisch sind (degeneriert)
                diffs = np.diff(points_arr, axis=0)
                max_diff = np.max(np.abs(diffs))
                if max_diff < 1e-6:
                    return None  # Alle Punkte gleich = degeneriert
            elif np.allclose(points_arr[0], points_arr[-1], atol=1e-6):
                return None  # Nur 2 Punkte und gleich = degeneriert

            return points_arr
        except:
            return None

    # ==================== Visualisierung ====================

    def _draw_edges_modern(self):
        """
        V8: Batch-Rendering für bessere Performance.

        Statt 174 einzelne Actors werden nur 3 erstellt:
        - batch_edges_normal: Alle nicht-selektierten Kanten (1 Actor)
        - batch_edges_selected: Alle selektierten Kanten (1 Actor)
        - edge_hover: Die aktuell gehoverte Kante (1 Actor)
        """
        # Sammle Kanten nach Status
        normal_meshes = []
        selected_meshes = []
        hover_mesh = None

        for edge in self._selectable_edges:
            if edge.line_mesh is None:
                continue

            is_sel = edge.id in self._selected_edge_ids
            is_hov = edge.id == self._hovered_edge_id or edge.id in self._hovered_loop_ids

            if is_hov:
                # Hover hat höchste Priorität - separater Actor
                if hover_mesh is None:
                    hover_mesh = edge.line_mesh.copy()
                else:
                    hover_mesh = hover_mesh.merge(edge.line_mesh)
            elif is_sel:
                selected_meshes.append(edge.line_mesh)
            else:
                normal_meshes.append(edge.line_mesh)

        # 1. Normale Kanten (Batch)
        self._update_batch_actor(
            "batch_edges_normal",
            normal_meshes,
            EDGE_COLORS["normal"],
            self._line_width_normal,
            priority=1
        )

        # 2. Selektierte Kanten (Batch)
        self._update_batch_actor(
            "batch_edges_selected",
            selected_meshes,
            EDGE_COLORS["selected"],
            self._line_width_hover,
            priority=5
        )

        # 3. Hover Kante (Einzeln für schnelles Update)
        if hover_mesh is not None:
            try:
                self.plotter.remove_actor("edge_hover")
            except:
                pass

            self.plotter.add_mesh(
                hover_mesh,
                color=EDGE_COLORS["hover"],
                opacity=1.0,
                line_width=self._line_width_hover,
                render_lines_as_tubes=False,
                lighting=False,
                name="edge_hover",
                pickable=False
            )
            self._set_actor_on_top("edge_hover", 10)
        else:
            try:
                self.plotter.remove_actor("edge_hover")
            except:
                pass

    def _update_batch_actor(self, name: str, meshes: List, color: str, width: float, priority: int):
        """Erstellt oder aktualisiert einen Batch-Actor für mehrere Kanten."""
        # Entferne alten Actor
        try:
            self.plotter.remove_actor(name)
        except:
            pass

        if not meshes:
            return

        # Merge alle Meshes in eines
        try:
            if len(meshes) == 1:
                batch_mesh = meshes[0]
            else:
                batch_mesh = meshes[0].copy()
                for m in meshes[1:]:
                    batch_mesh = batch_mesh.merge(m)

            self.plotter.add_mesh(
                batch_mesh,
                color=color,
                opacity=1.0,
                line_width=width,
                render_lines_as_tubes=False,  # Deaktiviert für Performance
                lighting=False,
                name=name,
                pickable=False  # Picking via BBox, nicht via VTK
            )
            self._set_actor_on_top(name, priority)

            if name not in self._edge_actors:
                self._edge_actors.append(name)

        except Exception as e:
            logger.debug(f"Batch actor creation failed: {e}")

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
        """V8: Entfernt alle Batch-Actors."""
        for name in self._edge_actors:
            try:
                self.plotter.remove_actor(name)
            except:
                pass
        self._edge_actors.clear()

        # Explizit die Batch-Namen entfernen
        for name in ["batch_edges_normal", "batch_edges_selected", "edge_hover"]:
            try:
                self.plotter.remove_actor(name)
            except:
                pass

    def set_edge_filter_mode(self, mode: str):
        """
        V8: Setzt den Kanten-Filter-Modus.

        Args:
            mode: "all" - alle Kanten
                  "convex" - nur Außenkanten (gut für Chamfer)
                  "concave" - nur Innenkanten (gut für Fillet)
        """
        if mode not in ("all", "convex", "concave"):
            mode = "all"

        old_mode = self._edge_filter_mode
        self._edge_filter_mode = mode

        # Nur neu laden wenn Mode sich geändert hat
        if old_mode != mode and self.edge_select_mode and self._edge_selection_body_id:
            logger.info(f"Edge Filter: {mode}")
            self._extract_edges_from_body(self._edge_selection_body_id)
            self._draw_edges_modern()
            request_render(self.plotter)

    # ==================== Picking & Logic ====================

    def pick_edge(self, x, y) -> int:
        """
        V8: Schnelles Edge-Picking via Raycasting + BBox-Test.
        Kein VTK Actor-Picking mehr nötig.
        """
        if not self._selectable_edges:
            return -1

        # Raycast um 3D-Position zu bekommen
        try:
            # Nutze VTK Cell Picker für 3D-Position
            import vtk
            picker = vtk.vtkCellPicker()
            picker.SetTolerance(0.005)
            picker.Pick(x, self.plotter.interactor.height() - y, 0, self.plotter.renderer)

            pick_pos = picker.GetPickPosition()
            if pick_pos == (0, 0, 0):
                return -1

            pick_pos = np.array(pick_pos)

            # Finde nächste Kante via Distanz zum Zentrum
            best_edge_id = -1
            best_dist = float('inf')
            PICK_TOLERANCE = 5.0  # mm

            for edge in self._selectable_edges:
                # Schneller BBox-Check zuerst
                if edge.bbox:
                    xmin, xmax, ymin, ymax, zmin, zmax = edge.bbox
                    margin = PICK_TOLERANCE
                    if (pick_pos[0] < xmin - margin or pick_pos[0] > xmax + margin or
                        pick_pos[1] < ymin - margin or pick_pos[1] > ymax + margin or
                        pick_pos[2] < zmin - margin or pick_pos[2] > zmax + margin):
                        continue  # Außerhalb BBox, skip

                # Distanz zum Zentrum
                center = np.array(edge.center)
                dist = np.linalg.norm(pick_pos - center)

                # Bonus für kürzere Kanten (präziseres Picking)
                if edge.length > 0:
                    dist = dist / (1 + edge.length * 0.01)

                if dist < best_dist and dist < PICK_TOLERANCE * 2:
                    best_dist = dist
                    best_edge_id = edge.id

            return best_edge_id

        except Exception as e:
            logger.debug(f"Edge picking failed: {e}")
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
                request_render(self.plotter)
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
                request_render(self.plotter)
                
        return True

    def handle_edge_click(self, _x, _y, is_multi) -> bool:
        """V8: Click handler - x,y nicht mehr benötigt da Hover-State genutzt wird."""
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
            request_render(self.plotter)
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
            request_render(self.plotter)
            return True
            
        return False
    
    

    # ==================== Getter ====================

    def get_selected_edges(self):
        return [e.build123d_edge for e in self._selectable_edges if e.id in self._selected_edge_ids]
    
    def get_selected_edge_ids(self) -> Set[int]:
        return self._selected_edge_ids.copy()

    def get_edge_selectors(self):
        """Gibt Legacy Point-Selectors zurück (backward-compat)"""
        return [e.center for e in self._selectable_edges if e.id in self._selected_edge_ids]

    def get_selected_edges(self):
        """
        Gibt die echten build123d Edges zurück (für TNP-robuste GeometricSelectors).

        Returns:
            List[build123d.Edge]: Selektierte Edges
        """
        return [e.build123d_edge for e in self._selectable_edges
                if e.id in self._selected_edge_ids and e.build123d_edge is not None]

    def select_all_edges(self):
        self._selected_edge_ids = {e.id for e in self._selectable_edges}
        self._draw_edges_modern()
        if hasattr(self, 'edge_selection_changed'):
            self.edge_selection_changed.emit(len(self._selected_edge_ids))
        request_render(self.plotter)