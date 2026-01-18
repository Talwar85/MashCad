"""
MashCad - Edge Selection Mixin
Interaktive Kantenauswahl für Fillet/Chamfer-Operationen

Features:
- Extraktion von B-Rep Kanten aus build123d Solids
- Tube-basierte Visualisierung für bessere Pickability
- Hover- und Selection-States mit Farbcodierung
- Ray-Casting für präzise Kantenauswahl
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

try:
    from PySide6.QtCore import Signal
    HAS_QT = True
except ImportError:
    HAS_QT = False


# ==================== Datenstrukturen ====================

@dataclass
class SelectableEdge:
    """
    Repräsentiert eine B-Rep Kante, die ausgewählt werden kann.

    Attributes:
        id: Eindeutige ID innerhalb der Session
        body_id: ID des zugehörigen Bodies
        build123d_edge: Referenz auf das build123d Edge-Objekt
        center: Mittelpunkt der Kante (für Proximity-Matching)
        start_point: Startpunkt der Kante
        end_point: Endpunkt der Kante
        edge_type: 'linear', 'circular', oder 'curve'
        tube_mesh: PyVista Tube-Geometrie für Picking
        length: Länge der Kante
    """
    id: int
    body_id: str
    build123d_edge: object
    center: Tuple[float, float, float]
    start_point: Tuple[float, float, float]
    end_point: Tuple[float, float, float]
    edge_type: str
    tube_mesh: object
    length: float = 0.0


# ==================== Farbkonstanten ====================

EDGE_COLORS = {
    "normal": "#555555",      # Dunkelgrau für nicht-selektierte Kanten
    "hover": "#FFFF00",       # Gelb für Hover
    "selected": "#FF6600",    # Orange für selektierte Kanten
    "failed": "#FF0000",      # Rot für fehlgeschlagene Kanten
}

EDGE_OPACITIES = {
    "normal": 0.5,
    "hover": 1.0,
    "selected": 1.0,
    "failed": 1.0,
}


# ==================== Mixin-Klasse ====================

class EdgeSelectionMixin:
    """
    Mixin für PyVistaViewport zur interaktiven Kantenauswahl.

    Verwendung:
        class PyVistaViewport(QWidget, ..., EdgeSelectionMixin):
            ...

    Muss folgende Methoden/Attribute vom Host bereitstellen:
        - self.plotter: PyVista Plotter
        - self.get_ray_from_click(x, y): Ray-Casting Methode
        - self._get_body_by_id(body_id): Body-Lookup Callback
    """

    # ==================== Initialisierung ====================

    def _init_edge_selection(self):
        """
        Initialisiert das Edge-Selection-System.
        Muss im __init__ des Viewports aufgerufen werden.
        """
        self.edge_select_mode: bool = False
        self._edge_selection_body_id: Optional[str] = None
        self._selectable_edges: List[SelectableEdge] = []
        self._selected_edge_ids: Set[int] = set()
        self._hovered_edge_id: int = -1
        self._edge_actors: List[str] = []
        self._edge_counter: int = 0
        self._get_body_by_id: Optional[Callable] = None

        # Tube-Parameter
        self._edge_tube_radius: float = 1.5  # mm
        self._edge_tube_sides: int = 12
        self._edge_sample_resolution: int = 20

        logger.debug("Edge selection system initialized")

    def set_edge_selection_callbacks(self, get_body_by_id: Callable):
        """
        Setzt Callbacks für Body-Lookup.

        Args:
            get_body_by_id: Funktion die body_id -> Body Objekt mappt
        """
        self._get_body_by_id = get_body_by_id

    # ==================== Mode Management ====================

    def start_edge_selection_mode(self, body_id: str):
        """
        Startet den Kantenauswahl-Modus für einen bestimmten Body.

        Extrahiert alle B-Rep Kanten und erstellt pickbare Tube-Geometrie.

        Args:
            body_id: ID des Bodies dessen Kanten ausgewählt werden sollen
        """
        if not HAS_PYVISTA:
            logger.error("PyVista nicht verfügbar")
            return

        # Sicherstellen dass edge selection initialisiert ist
        if not hasattr(self, '_selectable_edges'):
            self._init_edge_selection()

        self.edge_select_mode = True
        self._edge_selection_body_id = body_id
        self._selected_edge_ids.clear()
        self._hovered_edge_id = -1

        # Kanten extrahieren und visualisieren
        self._extract_edges_from_body(body_id)
        self._draw_edge_tubes()

        logger.info(f"Edge selection gestartet: Body {body_id}, {len(self._selectable_edges)} Kanten")

    def stop_edge_selection_mode(self):
        """
        Beendet den Kantenauswahl-Modus und räumt auf.
        """
        self.edge_select_mode = False
        self._edge_selection_body_id = None
        self._clear_edge_actors()
        self._selectable_edges.clear()
        self._selected_edge_ids.clear()
        self._hovered_edge_id = -1

        if hasattr(self, 'plotter') and self.plotter:
            self.plotter.render()

        logger.debug("Edge selection beendet")

    def is_edge_select_active(self) -> bool:
        """Prüft ob Kantenauswahl aktiv ist."""
        return getattr(self, 'edge_select_mode', False)

    # ==================== Edge Extraction ====================

    def _extract_edges_from_body(self, body_id: str):
        """
        Extrahiert topologische Kanten aus dem build123d Solid.

        WICHTIG: Verwendet body._build123d_solid.edges(), NICHT Mesh-Feature-Edges.
        Dies stellt sicher, dass wir die echten B-Rep Kanten bekommen.
        """
        self._selectable_edges.clear()
        self._edge_counter = 0

        if not self._get_body_by_id:
            logger.error("Body-Lookup Callback nicht gesetzt")
            return

        body = self._get_body_by_id(body_id)
        if not body:
            logger.warning(f"Body {body_id} nicht gefunden")
            return

        if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
            logger.warning(f"Body {body_id} hat kein build123d Solid")
            return

        solid = body._build123d_solid

        try:
            for edge in solid.edges():
                try:
                    # Kanten-Geometrie extrahieren
                    center = edge.center()
                    start = edge.position_at(0)
                    end = edge.position_at(1)
                    length = edge.length

                    # Kanten-Typ klassifizieren
                    edge_type = self._classify_edge(edge)

                    # Tube-Mesh für Picking erstellen
                    tube_mesh = self._create_edge_tube(edge)

                    sel_edge = SelectableEdge(
                        id=self._edge_counter,
                        body_id=body_id,
                        build123d_edge=edge,
                        center=(center.X, center.Y, center.Z),
                        start_point=(start.X, start.Y, start.Z),
                        end_point=(end.X, end.Y, end.Z),
                        edge_type=edge_type,
                        tube_mesh=tube_mesh,
                        length=length
                    )
                    self._selectable_edges.append(sel_edge)
                    self._edge_counter += 1

                except Exception as e:
                    logger.debug(f"Kante konnte nicht verarbeitet werden: {e}")
                    continue

            logger.debug(f"Extrahierte {len(self._selectable_edges)} Kanten aus Body {body_id}")

        except Exception as e:
            logger.error(f"Kantenextraktion fehlgeschlagen: {e}")

    def _classify_edge(self, edge) -> str:
        """
        Klassifiziert den Kantentyp.

        Returns:
            'linear', 'circular', oder 'curve'
        """
        try:
            from build123d import GeomType
            geom_type = edge.geom_type()

            if geom_type == GeomType.LINE:
                return "linear"
            elif geom_type == GeomType.CIRCLE:
                return "circular"
            else:
                return "curve"
        except:
            return "curve"

    def _create_edge_tube(self, edge, resolution: int = None) -> object:
        """
        Erstellt Tube-Geometrie aus einer Kante für bessere Pickability.

        Args:
            edge: build123d Edge
            resolution: Anzahl Sampling-Punkte (default: self._edge_sample_resolution)

        Returns:
            PyVista Tube PolyData oder None bei Fehler
        """
        if resolution is None:
            resolution = self._edge_sample_resolution

        try:
            # Punkte entlang der Kante samplen
            points = []
            for t in np.linspace(0, 1, resolution):
                try:
                    pt = edge.position_at(t)
                    points.append([pt.X, pt.Y, pt.Z])
                except:
                    pass

            if len(points) < 2:
                return None

            points = np.array(points)

            # Polyline erstellen
            n_pts = len(points)
            cells = []
            for i in range(n_pts - 1):
                cells.extend([2, i, i + 1])

            polyline = pv.PolyData(points, lines=cells)

            # Tube mit fixem Radius erstellen
            # Radius basierend auf Kantenlänge anpassen (min 0.5, max 2.0)
            edge_length = edge.length if hasattr(edge, 'length') else 10.0
            tube_radius = max(0.5, min(2.0, edge_length * 0.05))

            tube = polyline.tube(radius=tube_radius, n_sides=self._edge_tube_sides)

            return tube

        except Exception as e:
            logger.debug(f"Tube-Erstellung fehlgeschlagen: {e}")
            # Fallback: Einfache Linie
            try:
                start = edge.position_at(0)
                end = edge.position_at(1)
                return pv.Line([start.X, start.Y, start.Z], [end.X, end.Y, end.Z])
            except:
                return None

    # ==================== Visualisierung ====================

    def _draw_edge_tubes(self):
        """
        Zeichnet alle Kanten-Tubes mit entsprechenden Farben.
        """
        self._clear_edge_actors()

        for edge in self._selectable_edges:
            if edge.tube_mesh is None:
                continue

            # Farbe und Opacity basierend auf State
            if edge.id in self._selected_edge_ids:
                color = EDGE_COLORS["selected"]
                opacity = EDGE_OPACITIES["selected"]
            elif edge.id == self._hovered_edge_id:
                color = EDGE_COLORS["hover"]
                opacity = EDGE_OPACITIES["hover"]
            else:
                color = EDGE_COLORS["normal"]
                opacity = EDGE_OPACITIES["normal"]

            actor_name = f"edge_tube_{edge.id}"

            try:
                self.plotter.add_mesh(
                    edge.tube_mesh,
                    color=color,
                    opacity=opacity,
                    name=actor_name,
                    pickable=True,
                    smooth_shading=True
                )

                # Z-Fighting verhindern
                self._set_edge_depth_offset(actor_name)
                self._edge_actors.append(actor_name)

            except Exception as e:
                logger.debug(f"Fehler beim Hinzufügen von Edge Actor: {e}")

        if hasattr(self, 'plotter') and self.plotter:
            self.plotter.render()

    def _set_edge_depth_offset(self, actor_name: str):
        """
        Setzt Depth-Offset für Edge-Actor um Z-Fighting zu vermeiden.
        """
        try:
            actor = self.plotter.renderer.actors.get(actor_name)
            if actor:
                mapper = actor.GetMapper()
                if mapper:
                    mapper.SetResolveCoincidentTopologyToPolygonOffset()
                    mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-5, -5)
        except:
            pass

    def _clear_edge_actors(self):
        """
        Entfernt alle Edge-Visualisierungs-Actors.
        """
        for name in self._edge_actors:
            try:
                self.plotter.remove_actor(name)
            except:
                pass
        self._edge_actors.clear()

    def _update_edge_colors(self):
        """
        Aktualisiert Edge-Actor Farben basierend auf aktuellem State.
        Effizienter als komplettes Neuzeichnen.
        """
        for edge in self._selectable_edges:
            actor_name = f"edge_tube_{edge.id}"

            try:
                actor = self.plotter.renderer.actors.get(actor_name)
                if not actor:
                    continue

                prop = actor.GetProperty()

                if edge.id in self._selected_edge_ids:
                    color = pv.Color(EDGE_COLORS["selected"]).float_rgb
                    opacity = EDGE_OPACITIES["selected"]
                elif edge.id == self._hovered_edge_id:
                    color = pv.Color(EDGE_COLORS["hover"]).float_rgb
                    opacity = EDGE_OPACITIES["hover"]
                else:
                    color = pv.Color(EDGE_COLORS["normal"]).float_rgb
                    opacity = EDGE_OPACITIES["normal"]

                prop.SetColor(*color)
                prop.SetOpacity(opacity)

            except Exception as e:
                logger.debug(f"Fehler beim Aktualisieren von Edge {edge.id}: {e}")

        if hasattr(self, 'plotter') and self.plotter:
            self.plotter.render()

    def mark_edge_as_failed(self, edge_id: int):
        """
        Markiert eine Kante als fehlgeschlagen (rot).
        Wird verwendet wenn Fillet/Chamfer auf dieser Kante nicht angewendet werden konnte.
        """
        actor_name = f"edge_tube_{edge_id}"
        try:
            actor = self.plotter.renderer.actors.get(actor_name)
            if actor:
                prop = actor.GetProperty()
                prop.SetColor(*pv.Color(EDGE_COLORS["failed"]).float_rgb)
                prop.SetOpacity(EDGE_OPACITIES["failed"])
                self.plotter.render()
        except:
            pass

    # ==================== Picking ====================

    def pick_edge(self, screen_x: int, screen_y: int) -> int:
        """
        Führt Kanten-Picking an Bildschirmposition durch.

        Verwendet Ray-Casting gegen Tube-Meshes.

        Args:
            screen_x: X-Koordinate (Pixel)
            screen_y: Y-Koordinate (Pixel)

        Returns:
            Edge ID oder -1 wenn kein Treffer
        """
        if not self._selectable_edges:
            return -1

        if not hasattr(self, 'get_ray_from_click'):
            logger.error("get_ray_from_click Methode nicht verfügbar")
            return -1

        try:
            ray_origin, ray_dir = self.get_ray_from_click(screen_x, screen_y)
        except Exception as e:
            logger.debug(f"Ray-Casting Fehler: {e}")
            return -1

        ray_origin = np.array(ray_origin)
        ray_dir = np.array(ray_dir)
        ray_end = ray_origin + ray_dir * 100000  # Langer Ray

        best_id = -1
        best_dist = float('inf')

        for edge in self._selectable_edges:
            if edge.tube_mesh is None:
                continue

            try:
                # Ray-Trace gegen Tube-Mesh
                points, _ = edge.tube_mesh.ray_trace(ray_origin, ray_end)

                if len(points) > 0:
                    # Distanz zum nächsten Trefferpunkt
                    dist = np.linalg.norm(points[0] - ray_origin)
                    if dist < best_dist:
                        best_dist = dist
                        best_id = edge.id

            except Exception as e:
                # Fallback: Proximity zu Edge-Center
                try:
                    center = np.array(edge.center)
                    # Punkt-zu-Strahl Distanz
                    v = center - ray_origin
                    t = np.dot(v, ray_dir)
                    closest = ray_origin + t * ray_dir
                    dist_to_edge = np.linalg.norm(center - closest)

                    # Nur wenn sehr nah (< 10mm)
                    if dist_to_edge < 10.0 and t > 0:
                        dist_from_cam = t
                        if dist_from_cam < best_dist:
                            best_dist = dist_from_cam
                            best_id = edge.id
                except:
                    pass

        return best_id

    # ==================== Event Handling ====================

    def handle_edge_mouse_move(self, screen_x: int, screen_y: int) -> bool:
        """
        Behandelt Mausbewegung im Edge-Selection Modus.
        Aktualisiert Hover-State.

        Returns:
            True wenn Event verarbeitet wurde
        """
        if not self.edge_select_mode:
            return False

        new_hover = self.pick_edge(screen_x, screen_y)

        if new_hover != self._hovered_edge_id:
            self._hovered_edge_id = new_hover
            self._update_edge_colors()

        return True

    def handle_edge_click(self, screen_x: int, screen_y: int, is_multi: bool) -> bool:
        """
        Behandelt Klick im Edge-Selection Modus.
        Toggled Auswahl der Kante.

        Args:
            screen_x: X-Koordinate
            screen_y: Y-Koordinate
            is_multi: True wenn Ctrl/Shift gedrückt (Multi-Select)

        Returns:
            True wenn Event verarbeitet wurde
        """
        if not self.edge_select_mode:
            return False

        edge_id = self.pick_edge(screen_x, screen_y)

        if edge_id != -1:
            # Toggle-Auswahl
            if edge_id in self._selected_edge_ids:
                self._selected_edge_ids.discard(edge_id)
            else:
                self._selected_edge_ids.add(edge_id)

            self._update_edge_colors()

            # Signal emittieren für UI-Update
            if hasattr(self, 'edge_selection_changed'):
                self.edge_selection_changed.emit(len(self._selected_edge_ids))

            logger.debug(f"Edge {edge_id} {'deselektiert' if edge_id not in self._selected_edge_ids else 'selektiert'}, Total: {len(self._selected_edge_ids)}")

            return True

        return False

    # ==================== Selection Accessors ====================

    def get_selected_edges(self) -> List[object]:
        """
        Gibt die build123d Edge-Objekte für alle selektierten Kanten zurück.
        """
        return [
            edge.build123d_edge
            for edge in self._selectable_edges
            if edge.id in self._selected_edge_ids
        ]

    def get_selected_edge_ids(self) -> Set[int]:
        """
        Gibt die IDs aller selektierten Kanten zurück.
        """
        return self._selected_edge_ids.copy()

    def get_selected_edge_count(self) -> int:
        """
        Gibt die Anzahl selektierter Kanten zurück.
        """
        return len(self._selected_edge_ids)

    def get_edge_selectors(self) -> List[Tuple[float, float, float]]:
        """
        Gibt Center-Points als Selektoren für Feature-Speicherung zurück.
        Verwendet für persistente Kanten-Referenzen.
        """
        return [
            edge.center
            for edge in self._selectable_edges
            if edge.id in self._selected_edge_ids
        ]

    def select_all_edges(self):
        """
        Selektiert alle verfügbaren Kanten.
        Nützlich für "Alle Kanten abrunden".
        """
        self._selected_edge_ids = {edge.id for edge in self._selectable_edges}
        self._update_edge_colors()

        if hasattr(self, 'edge_selection_changed'):
            self.edge_selection_changed.emit(len(self._selected_edge_ids))

    def deselect_all_edges(self):
        """
        Deselektiert alle Kanten.
        """
        self._selected_edge_ids.clear()
        self._update_edge_colors()

        if hasattr(self, 'edge_selection_changed'):
            self.edge_selection_changed.emit(0)
