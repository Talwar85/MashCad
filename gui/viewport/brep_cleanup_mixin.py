"""
MashCad - BREP Cleanup Viewport Mixin
=====================================

Viewport-Interaktion fuer den BREP Cleanup Modus:
- Face-Hovering mit Tooltips
- Multi-Color Highlighting fuer Feature-Typen
- Face-Selektion mit Auto-Suggest
- Merge-Vorschau

Author: Claude (BREP Cleanup Feature)
Date: 2026-01
"""

import numpy as np
from typing import Optional, List, Dict, Set, Tuple, Any
from loguru import logger

try:
    import vtk
    import pyvista as pv
    HAS_VTK = True
except ImportError:
    HAS_VTK = False

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor

from gui.viewport.render_queue import request_render


class BRepCleanupMixin:
    """
    Mixin fuer BREP Cleanup Interaktion im Viewport.

    Signals (muessen in PyVistaViewport definiert sein):
        brep_cleanup_face_hovered(int, dict)  - Face-Index, Feature-Info
        brep_cleanup_face_selected(int)       - Face-Index
        brep_cleanup_features_changed(list)   - Liste erkannter Features
        brep_cleanup_selection_changed(list)  - Liste selektierter Face-Indices
    """

    # Farben fuer Highlighting
    CLEANUP_COLORS = {
        "hover": "#00FFFF",       # Cyan
        "selected": "#FFAA00",    # Orange
        "suggested": "#90EE90",   # Hellgruen
        "fillet": "#FF69B4",      # Pink
        "hole": "#4169E1",        # Blau
        "boss": "#32CD32",        # Gruen
        "pocket": "#FFD700",      # Gelb
    }

    def _init_brep_cleanup_state(self):
        """Initialisiert Cleanup-State. Wird von __init__ aufgerufen."""
        self._brep_cleanup_mode = False
        self._brep_cleanup_body_id = None
        self._brep_cleanup_analysis = None
        self._brep_cleanup_analyzer = None

        # Selection State
        self._brep_cleanup_selected_faces: Set[int] = set()
        self._brep_cleanup_suggested_faces: Set[int] = set()
        self._brep_cleanup_hovered_face: int = -1

        # Highlight Actors
        self._brep_cleanup_highlight_actors: Dict[str, str] = {}  # name -> actor_name

    # =========================================================================
    # Public API
    # =========================================================================

    def start_brep_cleanup_mode(self, body_id: str) -> bool:
        """
        Startet den BREP Cleanup Modus fuer einen Body.

        Args:
            body_id: ID des zu bearbeitenden Bodies

        Returns:
            True wenn erfolgreich gestartet
        """
        if body_id not in self.bodies:
            logger.error(f"BREP Cleanup: Body {body_id} nicht gefunden")
            return False

        # Body-Objekt holen (kann in dict['body'] oder via Callback sein)
        body_data = self.bodies[body_id]
        body = body_data.get('body') if isinstance(body_data, dict) else body_data

        # Falls kein Body-Objekt gespeichert, versuche ueber Callback
        if body is None and hasattr(self, '_get_body_by_id'):
            body = self._get_body_by_id(body_id)

        if body is None:
            logger.error(f"BREP Cleanup: Body-Objekt fuer {body_id} nicht verfuegbar")
            return False

        if not hasattr(body, '_build123d_solid') or body._build123d_solid is None:
            logger.error(f"BREP Cleanup: Body {body_id} hat kein BREP")
            return False

        logger.info(f"BREP Cleanup: Starte Modus fuer Body {body_id}")

        self._brep_cleanup_mode = True
        self._brep_cleanup_body_id = body_id
        self._brep_cleanup_selected_faces.clear()
        self._brep_cleanup_suggested_faces.clear()
        self._brep_cleanup_hovered_face = -1

        # Body analysieren
        try:
            from modeling.brep_face_analyzer import BRepFaceAnalyzer
            self._brep_cleanup_analyzer = BRepFaceAnalyzer()
            self._brep_cleanup_analysis = self._brep_cleanup_analyzer.analyze(
                body._build123d_solid
            )

            logger.success(
                f"BREP Cleanup: {len(self._brep_cleanup_analysis.faces)} Faces, "
                f"{len(self._brep_cleanup_analysis.features)} Features erkannt"
            )

            # Signal fuer Panel
            if hasattr(self, 'brep_cleanup_features_changed'):
                self.brep_cleanup_features_changed.emit(
                    self._brep_cleanup_analysis.features
                )

            # X-Ray Mode: Body halbtransparent
            self._set_body_transparency(body_id, 0.3)

            # Initial-Highlighting fuer Features
            self._update_brep_cleanup_highlighting()

            return True

        except Exception as e:
            logger.error(f"BREP Cleanup: Analyse fehlgeschlagen: {e}")
            self.stop_brep_cleanup_mode()
            return False

    def stop_brep_cleanup_mode(self):
        """Beendet den BREP Cleanup Modus."""
        if not self._brep_cleanup_mode:
            return

        logger.info("BREP Cleanup: Beende Modus")

        # Highlights entfernen
        self._clear_brep_cleanup_highlights()

        # Body-Transparenz zuruecksetzen
        if self._brep_cleanup_body_id:
            self._set_body_transparency(self._brep_cleanup_body_id, 0.9)

        # State resetten
        self._brep_cleanup_mode = False
        self._brep_cleanup_body_id = None
        self._brep_cleanup_analysis = None
        self._brep_cleanup_selected_faces.clear()
        self._brep_cleanup_suggested_faces.clear()
        self._brep_cleanup_hovered_face = -1

        request_render(self.plotter)

    @property
    def brep_cleanup_active(self) -> bool:
        """True wenn Cleanup-Modus aktiv."""
        return self._brep_cleanup_mode

    def get_brep_cleanup_analysis(self):
        """Gibt aktuelle Analyse zurueck."""
        return self._brep_cleanup_analysis

    def get_brep_cleanup_selected_faces(self) -> List[int]:
        """Gibt Liste selektierter Face-Indices zurueck."""
        return list(self._brep_cleanup_selected_faces)

    def select_feature_by_index(self, feature_idx: int, additive: bool = False):
        """
        Selektiert alle Faces eines Features.

        Args:
            feature_idx: Index in analysis.features
            additive: True = zur Selektion hinzufuegen, False = Selektion ersetzen
        """
        if not self._brep_cleanup_analysis:
            return

        if 0 <= feature_idx < len(self._brep_cleanup_analysis.features):
            feature = self._brep_cleanup_analysis.features[feature_idx]

            # Bei nicht-additivem Modus: vorherige Selektion leeren
            if not additive:
                self._brep_cleanup_selected_faces.clear()

            self._brep_cleanup_selected_faces.update(feature.face_indices)
            self._brep_cleanup_suggested_faces.clear()

            self._update_brep_cleanup_highlighting()

            if hasattr(self, 'brep_cleanup_selection_changed'):
                self.brep_cleanup_selection_changed.emit(
                    list(self._brep_cleanup_selected_faces)
                )

    def select_features_by_type(self, feature_type):
        """
        Selektiert alle Features eines Typs.

        Args:
            feature_type: FeatureType enum
        """
        if not self._brep_cleanup_analysis:
            return

        self._brep_cleanup_selected_faces.clear()

        for feature in self._brep_cleanup_analysis.features:
            if feature.feature_type == feature_type:
                self._brep_cleanup_selected_faces.update(feature.face_indices)

        self._brep_cleanup_suggested_faces.clear()
        self._update_brep_cleanup_highlighting()

        if hasattr(self, 'brep_cleanup_selection_changed'):
            self.brep_cleanup_selection_changed.emit(
                list(self._brep_cleanup_selected_faces)
            )

    def clear_brep_cleanup_selection(self):
        """Leert die Selektion."""
        self._brep_cleanup_selected_faces.clear()
        self._brep_cleanup_suggested_faces.clear()
        self._update_brep_cleanup_highlighting()

        if hasattr(self, 'brep_cleanup_selection_changed'):
            self.brep_cleanup_selection_changed.emit([])

    def execute_brep_cleanup_merge(self) -> bool:
        """
        Fuehrt Merge fuer selektierte Faces aus.

        Returns:
            True wenn erfolgreich
        """
        if not self._brep_cleanup_mode or not self._brep_cleanup_body_id:
            return False

        # Body-Objekt holen (wie in start_brep_cleanup_mode)
        body_data = self.bodies.get(self._brep_cleanup_body_id)
        body = body_data.get('body') if isinstance(body_data, dict) else body_data

        # Falls kein Body-Objekt gespeichert, versuche ueber Callback
        if body is None and hasattr(self, '_get_body_by_id'):
            body = self._get_body_by_id(self._brep_cleanup_body_id)

        if not body or not hasattr(body, '_build123d_solid'):
            logger.error("BREP Cleanup: Body-Objekt nicht gefunden")
            return False

        logger.info(f"BREP Cleanup: Merge fuer {len(self._brep_cleanup_selected_faces)} Faces")

        try:
            from modeling.brep_face_merger import merge_with_transaction
            result = merge_with_transaction(body, self._brep_cleanup_analysis)

            if result.is_success:
                logger.success(f"BREP Cleanup: {result.message}")

                # Viewport neu rendern - Body-Mesh aktualisieren
                self._refresh_body_after_merge(body)

                # Neu analysieren
                self._brep_cleanup_analysis = self._brep_cleanup_analyzer.analyze(
                    body._build123d_solid
                )

                # Selection leeren
                self._brep_cleanup_selected_faces.clear()
                self._brep_cleanup_suggested_faces.clear()

                # Highlights aktualisieren
                self._update_brep_cleanup_highlighting()

                if hasattr(self, 'brep_cleanup_features_changed'):
                    self.brep_cleanup_features_changed.emit(
                        self._brep_cleanup_analysis.features
                    )

                return True
            else:
                logger.error(f"BREP Cleanup: Merge fehlgeschlagen: {result.message}")
                return False

        except Exception as e:
            logger.error(f"BREP Cleanup: Merge-Exception: {e}")
            return False

    # =========================================================================
    # Mouse Event Handlers (aufgerufen von Viewport)
    # =========================================================================

    def _brep_cleanup_handle_hover(self, x: int, y: int):
        """
        Behandelt Hover-Events im Cleanup-Modus.

        Zeigt Tooltip mit Face/Feature-Info.
        """
        if not self._brep_cleanup_mode or not HAS_VTK:
            return

        face_idx = self._pick_brep_face(x, y)

        if face_idx == self._brep_cleanup_hovered_face:
            return  # Keine Aenderung

        self._brep_cleanup_hovered_face = face_idx

        if face_idx >= 0:
            # Face-Info sammeln
            info = self._get_face_info(face_idx)

            if hasattr(self, 'brep_cleanup_face_hovered'):
                self.brep_cleanup_face_hovered.emit(face_idx, info)

        self._update_brep_cleanup_highlighting()

    def _brep_cleanup_handle_click(self, x: int, y: int):
        """
        Behandelt Klick-Events im Cleanup-Modus.

        Selektiert Face und zeigt verwandte Faces.
        """
        if not self._brep_cleanup_mode:
            return

        face_idx = self._pick_brep_face(x, y)

        if face_idx < 0:
            # Klick ins Leere -> Selektion leeren
            self.clear_brep_cleanup_selection()
            return

        # Toggle-Selektion mit Ctrl
        # TODO: Ctrl-Status von Event holen
        if face_idx in self._brep_cleanup_selected_faces:
            self._brep_cleanup_selected_faces.remove(face_idx)
        else:
            self._brep_cleanup_selected_faces.add(face_idx)

            # Auto-Suggest: Verwandte Faces anzeigen
            if self._brep_cleanup_analyzer:
                suggested = self._brep_cleanup_analyzer.suggest_related_faces(face_idx)
                self._brep_cleanup_suggested_faces = set(suggested) - self._brep_cleanup_selected_faces

        self._update_brep_cleanup_highlighting()

        if hasattr(self, 'brep_cleanup_face_selected'):
            self.brep_cleanup_face_selected.emit(face_idx)

        if hasattr(self, 'brep_cleanup_selection_changed'):
            self.brep_cleanup_selection_changed.emit(
                list(self._brep_cleanup_selected_faces)
            )

    def _brep_cleanup_handle_key(self, key: str) -> bool:
        """
        Behandelt Tasten-Events im Cleanup-Modus.

        Returns:
            True wenn Taste verarbeitet wurde
        """
        if not self._brep_cleanup_mode:
            return False

        if key == "Escape":
            self.stop_brep_cleanup_mode()
            return True

        if key == "Return" or key == "Enter":
            # Merge ausfuehren
            self.execute_brep_cleanup_merge()
            return True

        if key == "A":
            # Alle Suggested zur Selektion hinzufuegen
            self._brep_cleanup_selected_faces.update(self._brep_cleanup_suggested_faces)
            self._brep_cleanup_suggested_faces.clear()
            self._update_brep_cleanup_highlighting()

            if hasattr(self, 'brep_cleanup_selection_changed'):
                self.brep_cleanup_selection_changed.emit(
                    list(self._brep_cleanup_selected_faces)
                )
            return True

        return False

    # =========================================================================
    # Internal Methods
    # =========================================================================

    def _pick_brep_face(self, x: int, y: int) -> int:
        """
        Pickt Face im BREP Cleanup Modus.

        Returns:
            Face-Index oder -1 wenn nichts getroffen
        """
        if not HAS_VTK or not self._brep_cleanup_body_id:
            return -1

        # VTK CellPicker verwenden
        picker = vtk.vtkCellPicker()
        picker.SetTolerance(0.01)  # Etwas groessere Toleranz

        height = self.plotter.interactor.height()
        picker.Pick(x, height - y, 0, self.plotter.renderer)

        cell_id = picker.GetCellId()
        if cell_id == -1:
            logger.debug(f"BREP Cleanup Pick: Kein Cell getroffen bei ({x}, {y})")
            return -1

        picked_actor = picker.GetActor()
        if picked_actor is None:
            logger.debug("BREP Cleanup Pick: Kein Actor")
            return -1

        # Im Cleanup-Modus akzeptieren wir jeden getroffenen Body
        # und validieren ueber Position/Normale
        pos = np.array(picker.GetPickPosition())
        normal = np.array(picker.GetPickNormal())

        logger.debug(f"BREP Cleanup Pick: pos={pos}, normal={normal}")

        face_idx = self._find_face_at_position(pos, normal)
        logger.debug(f"BREP Cleanup Pick: Face Index = {face_idx}")

        return face_idx

    def _find_face_at_position(self, pos: np.ndarray, normal: np.ndarray) -> int:
        """Findet Face-Index basierend auf Position und Normale."""
        if not self._brep_cleanup_analysis:
            logger.debug("_find_face_at_position: Keine Analyse vorhanden")
            return -1

        best_idx = -1
        best_score = float('inf')

        for face in self._brep_cleanup_analysis.faces:
            # Score basierend auf Position (Normale optional)
            face_center = face.center
            if face_center is None:
                continue

            # Distanz zum Zentrum
            dist = np.linalg.norm(pos - face_center)

            # Normale-Check falls vorhanden (aber nicht zwingend)
            face_normal = face.normal if face.normal is not None else face.axis
            if face_normal is not None and np.linalg.norm(normal) > 0.1:
                dot = abs(np.dot(normal, face_normal))
                # Bei schlechter Normale-Uebereinstimmung Score erhoehen
                if dot < 0.5:
                    dist *= 2.0  # Penalty

            if dist < best_score:
                best_score = dist
                best_idx = face.idx

        if best_idx >= 0:
            logger.debug(f"_find_face_at_position: Gefunden Face {best_idx} mit Score {best_score:.2f}")
        else:
            logger.debug(f"_find_face_at_position: Kein Face gefunden")

        return best_idx

    def _get_face_info(self, face_idx: int) -> dict:
        """Sammelt Info fuer Tooltip."""
        if not self._brep_cleanup_analysis or face_idx < 0:
            return {}

        if face_idx >= len(self._brep_cleanup_analysis.faces):
            return {}

        face = self._brep_cleanup_analysis.faces[face_idx]
        info = {
            "idx": face_idx,
            "type": face.surface_type.name,
            "area": face.area,
        }

        if face.radius is not None:
            info["radius"] = face.radius
            info["diameter"] = face.radius * 2

        if face.normal is not None:
            info["normal"] = face.normal.tolist()

        # Feature-Info hinzufuegen
        feat_idx = self._brep_cleanup_analysis.face_to_feature.get(face_idx)
        if feat_idx is not None:
            feature = self._brep_cleanup_analysis.features[feat_idx]
            info["feature_type"] = feature.display_name
            info["feature_icon"] = feature.icon
            info["feature_faces"] = len(feature.face_indices)

        return info

    def _update_brep_cleanup_highlighting(self):
        """Aktualisiert alle Highlights im Viewport."""
        if not self._brep_cleanup_mode:
            return

        self._clear_brep_cleanup_highlights()

        # Highlight-Meshes erstellen
        if self._brep_cleanup_analysis:
            # Body-Data aus dict holen
            body_data = self.bodies.get(self._brep_cleanup_body_id)
            if not body_data:
                return

            # Mesh extrahieren (entweder aus dict oder Body-Objekt)
            mesh = None
            if isinstance(body_data, dict):
                mesh = body_data.get('mesh')
            elif hasattr(body_data, 'vtk_mesh'):
                mesh = body_data.vtk_mesh

            if mesh is None:
                return

            # Hover - einzelne Markierung
            if self._brep_cleanup_hovered_face >= 0:
                self._add_face_highlight(
                    self._brep_cleanup_hovered_face,
                    "hover", self.CLEANUP_COLORS["hover"], 0.8
                )

            # Selected - alle selektierten Faces markieren
            for face_idx in self._brep_cleanup_selected_faces:
                self._add_face_highlight(
                    face_idx,
                    f"selected_{face_idx}", self.CLEANUP_COLORS["selected"], 1.0
                )

            # Suggested - vorgeschlagene Faces
            for face_idx in self._brep_cleanup_suggested_faces:
                self._add_face_highlight(
                    face_idx,
                    f"suggested_{face_idx}", self.CLEANUP_COLORS["suggested"], 0.7
                )

        request_render(self.plotter)

    def _add_face_highlight(self, face_idx: int, name: str,
                            color: str, opacity: float):
        """
        Fuegt Highlight fuer eine Face hinzu.

        Zeigt Marker an Face-Zentrum mit groesserem Radius fuer bessere Sichtbarkeit.
        """
        if not self._brep_cleanup_analysis:
            return

        if face_idx >= len(self._brep_cleanup_analysis.faces):
            return

        face = self._brep_cleanup_analysis.faces[face_idx]
        if face.center is None:
            return

        actor_name = f"brep_cleanup_{name}"

        try:
            # Groesse basierend auf Face-Flaeche (aber mindestens 2mm)
            radius = max(2.0, np.sqrt(face.area) * 0.1) if face.area > 0 else 2.0

            # Sphere als Markierung am Face-Center
            sphere = pv.Sphere(radius=radius, center=face.center)
            self.plotter.add_mesh(
                sphere,
                color=color,
                opacity=opacity,
                name=actor_name,
                pickable=False,
                render=False
            )
            self._brep_cleanup_highlight_actors[name] = actor_name
        except Exception as e:
            logger.debug(f"Highlight fehlgeschlagen: {e}")

    def _refresh_body_after_merge(self, body):
        """
        Aktualisiert Body-Visualisierung nach Merge.

        Args:
            body: Body-Objekt mit aktualisiertem _build123d_solid
        """
        try:
            body_id = self._brep_cleanup_body_id

            # Mesh wird lazy regeneriert - vtk_mesh/vtk_edges Properties triggern das
            mesh = body.vtk_mesh
            edges = body.vtk_edges

            if mesh is None:
                logger.warning("BREP Cleanup: Kein Mesh nach Merge")
                return

            # Body im Viewport aktualisieren via add_body (handles reuse)
            if hasattr(self, 'add_body'):
                self.add_body(
                    body_id,
                    body.name,
                    mesh_obj=mesh,
                    edge_mesh_obj=edges
                )
                logger.debug(f"BREP Cleanup: Body {body_id} Visualisierung aktualisiert")

        except Exception as e:
            logger.error(f"BREP Cleanup: Body-Refresh fehlgeschlagen: {e}")

    def _clear_brep_cleanup_highlights(self):
        """Entfernt alle Cleanup-Highlights."""
        for name, actor_name in list(self._brep_cleanup_highlight_actors.items()):
            try:
                self.plotter.remove_actor(actor_name)
            except Exception as e:
                logger.debug(f"[brep_cleanup_mixin] Fehler beim Entfernen des Highlight-Actors: {e}")

        self._brep_cleanup_highlight_actors.clear()

    def _set_body_transparency(self, body_id: str, opacity: float):
        """Setzt Transparenz fuer einen Body."""
        actor_names = self._body_actors.get(body_id, ())
        if not actor_names:
            return

        mesh_actor_name = actor_names[0]  # Erster ist Mesh-Actor
        if mesh_actor_name in self.plotter.renderer.actors:
            actor = self.plotter.renderer.actors[mesh_actor_name]
            try:
                actor.GetProperty().SetOpacity(opacity)
            except Exception as e:
                logger.debug(f"Opacity setzen fehlgeschlagen: {e}")
