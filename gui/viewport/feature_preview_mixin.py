"""
MashCad - Feature Preview Mixin
Live preview methods for Shell, Fillet, and Chamfer operations.

Provides VTK-based live preview similar to ExtrudeMixin.show_extrude_preview().
During slider movement, shows a preview of the operation result without
expensive kernel operations.
"""

import numpy as np
from loguru import logger
from typing import Optional, List, Tuple, Dict

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

from gui.viewport.render_queue import request_render


class FeaturePreviewMixin:
    """
    Mixin für PyVistaViewport mit Live-Preview-Methoden für Features.

    Enthält:
    - Shell thickness preview
    - Fillet radius preview
    - Chamfer size preview
    """

    def _init_feature_preview(self):
        """Initialisiert Feature-Preview-State."""
        self._shell_preview_actor = None
        self._fillet_preview_actors = []
        self._chamfer_preview_actors = []
        self._shell_preview_thickness = 0.0
        self._fillet_preview_radius = 0.0
        self._chamfer_preview_distance = 0.0

    # ========================================================================
    # Shell Live Preview
    # ========================================================================

    def set_shell_mode(self, enabled: bool):
        """
        Aktiviert/deaktiviert Shell-Modus.

        Args:
            enabled: True um Shell-Modus zu aktivieren
        """
        if enabled:
            self._init_feature_preview()
            self._shell_mode = True
            logger.debug("Shell-Modus aktiviert")
        else:
            self._shell_mode = getattr(self, '_shell_mode', False)
            if self._shell_mode:
                self._clear_shell_preview()
                self._shell_mode = False
                logger.debug("Shell-Modus deaktiviert")

    def update_shell_preview(self, thickness: float, opening_faces: list = None):
        """
        Aktualisiert die Shell-Vorschau basierend auf der Wandstärke.

        Args:
            thickness: Wandstärke in mm
            opening_faces: Liste der Öffnungs-Flächen (optional)
        """
        if not HAS_PYVISTA:
            return

        try:
            from config.feature_flags import is_enabled
            if not is_enabled("live_preview_shell"):
                return

            self._shell_preview_thickness = thickness

            # Alte Preview entfernen
            self._clear_shell_preview()

            # Preview-Qualität setzen (live vs final)
            if hasattr(self, '_preview_quality'):
                self._preview_quality = "live"

            # Vorschau generieren
            self._generate_shell_preview(thickness, opening_faces)

            request_render(self.plotter)

        except Exception as e:
            logger.debug(f"Shell Preview Error: {e}")

    def _generate_shell_preview(self, thickness: float, opening_faces: list = None):
        """
        Generiert die VTK-Mesh-Preview für Shell-Operation.

        Uses a visual approximation by creating an offset mesh along face normals.
        This is fast and gives good visual feedback without kernel operation.

        Args:
            thickness: Wandstärke in mm (positiv = Verdickung nach außen)
            opening_faces: Liste der Öffnungs-Flächen (optional)
        """
        if not hasattr(self, 'bodies') or not self.bodies:
            return

        try:
            # Hole den aktiven Body (aus dem Shell-Kontext)
            target_body_id = None
            if hasattr(self, '_shell_target_body_id'):
                target_body_id = self._shell_target_body_id
            elif hasattr(self, '_edge_selection_body_id'):
                target_body_id = self._edge_selection_body_id

            if not target_body_id or target_body_id not in self.bodies:
                return

            body_data = self.bodies[target_body_id]
            mesh = body_data.get('mesh')

            if mesh is None:
                return

            # Kopie erstellen für Preview
            preview_mesh = mesh.copy()

            # Wende Offset an entlang der Normalen (simuliert Shell-Verdickung)
            # Dies ist eine visuelle Approximation, keine echte Kernel-Operation!
            normals = preview_mesh.point_data.get('Normals')

            if normals is not None:
                # Offset entlang Normalen
                preview_mesh.points = preview_mesh.points + normals * thickness
            else:
                # Fallback: Berechne Normalen
                preview_mesh.compute_normals(inplace=True)
                normals = preview_mesh.point_data.get('Normals')
                if normals is not None:
                    preview_mesh.points = preview_mesh.points + normals * thickness

            # Normalen neu berechnen für korrektes Shading
            preview_mesh.compute_normals(inplace=True)

            # Farbe basierend auf Dicke (Grün = positiv, Rot = negativ)
            color = '#66ff66' if thickness >= 0 else '#ff6666'
            opacity = 0.4  # Transparenz für Preview

            # Preview-Mesh hinzufügen
            self.plotter.add_mesh(
                preview_mesh,
                color=color,
                opacity=opacity,
                name='shell_preview',
                pickable=False,
                smooth_shading=True,
                specular=0.3
            )

            self._shell_preview_actor = 'shell_preview'
            logger.debug(f"Shell Preview: thickness={thickness}mm")

        except Exception as e:
            logger.debug(f"Shell Preview Generation Error: {e}")

    def _clear_shell_preview(self):
        """Entfernt die Shell-Preview."""
        try:
            if self._shell_preview_actor:
                self.plotter.remove_actor(self._shell_preview_actor)
                self._shell_preview_actor = None
        except Exception as e:
            logger.debug(f"Clear Shell Preview Error: {e}")

    # ========================================================================
    # Fillet Live Preview
    # ========================================================================

    def update_fillet_preview(self, radius: float):
        """
        Aktualisiert die Fillet-Vorschau basierend auf dem Radius.

        Args:
            radius: Fillet-Radius in mm
        """
        if not HAS_PYVISTA:
            return

        try:
            from config.feature_flags import is_enabled
            if not is_enabled("live_preview_fillet"):
                return

            self._fillet_preview_radius = radius

            # Alte Preview entfernen
            self._clear_fillet_preview()

            # Preview-Qualität setzen
            if hasattr(self, '_preview_quality'):
                self._preview_quality = "live"

            # Vorschau generieren
            self._generate_fillet_preview(radius)

            request_render(self.plotter)

        except Exception as e:
            logger.debug(f"Fillet Preview Error: {e}")

    def _generate_fillet_preview(self, radius: float):
        """
        Generiert die VTK-Mesh-Preview für Fillet-Operation.

        Creates tube geometry along selected edges to visualize fillets.
        This is a visual approximation - actual fillets require kernel operation.

        Args:
            radius: Fillet-Radius in mm
        """
        if not hasattr(self, '_selected_edge_ids'):
            return

        try:
            # Hole selektierte Kanten
            selected_ids = list(self._selected_edge_ids)

            if not selected_ids:
                return

            # Hole SelectableEdge-Objekte
            if not hasattr(self, '_selectable_edges'):
                return

            selected_edges = [e for e in self._selectable_edges if e.id in selected_ids]

            if not selected_edges:
                return

            # Für jede Kante einen Tubus erstellen (simuliert Fillet)
            for i, edge in enumerate(selected_edges):
                try:
                    # Punkte der Kante
                    if hasattr(edge, 'points') and edge.points is not None:
                        points = edge.points
                    elif hasattr(edge, 'line_mesh') and edge.line_mesh is not None:
                        # Aus LineMesh extrahieren
                        line_mesh = edge.line_mesh
                        points = line_mesh.points
                    else:
                        # Fallback: Nur Zentrumspunkt
                        center = edge.center
                        points = np.array([
                            [center[0] - edge.length/2, center[1], center[2]],
                            [center[0] + edge.length/2, center[1], center[2]]
                        ])

                    # Erstelle Tube entlang der Kante
                    if len(points) >= 2:
                        tube = pv.Line(points[0], points[-1])
                        tube = tube.tube(radius=radius, n_sides=12)

                        actor_name = f'fillet_preview_{i}'
                        self.plotter.add_mesh(
                            tube,
                            color='#ffaa00',  # Orange/Gold
                            opacity=0.6,
                            name=actor_name,
                            pickable=False,
                            smooth_shading=True
                        )

                        self._fillet_preview_actors.append(actor_name)

                except Exception as e:
                    logger.debug(f"Fillet Preview Edge Error: {e}")

            logger.debug(f"Fillet Preview: {len(selected_edges)} edges, radius={radius}mm")

        except Exception as e:
            logger.debug(f"Fillet Preview Generation Error: {e}")

    def _clear_fillet_preview(self):
        """Entfernt die Fillet-Preview."""
        try:
            for actor_name in self._fillet_preview_actors:
                self.plotter.remove_actor(actor_name)
            self._fillet_preview_actors.clear()
        except Exception as e:
            logger.debug(f"Clear Fillet Preview Error: {e}")

    # ========================================================================
    # Chamfer Live Preview
    # ========================================================================

    def update_chamfer_preview(self, distance: float):
        """
        Aktualisiert die Chamfer-Vorschau basierend auf dem Abstand.

        Args:
            distance: Chamfer-Abstand in mm
        """
        if not HAS_PYVISTA:
            return

        try:
            from config.feature_flags import is_enabled
            if not is_enabled("live_preview_chamfer"):
                return

            self._chamfer_preview_distance = distance

            # Alte Preview entfernen
            self._clear_chamfer_preview()

            # Preview-Qualität setzen
            if hasattr(self, '_preview_quality'):
                self._preview_quality = "live"

            # Vorschau generieren
            self._generate_chamfer_preview(distance)

            request_render(self.plotter)

        except Exception as e:
            logger.debug(f"Chamfer Preview Error: {e}")

    def _generate_chamfer_preview(self, distance: float):
        """
        Generiert die VTK-Mesh-Preview für Chamfer-Operation.

        Creates tapered tube geometry along selected edges to visualize chamfers.
        This is a visual approximation - actual chamfers require kernel operation.

        Args:
            distance: Chamfer-Abstand in mm
        """
        if not hasattr(self, '_selected_edge_ids'):
            return

        try:
            # Hole selektierte Kanten
            selected_ids = list(self._selected_edge_ids)

            if not selected_ids:
                return

            # Hole SelectableEdge-Objekte
            if not hasattr(self, '_selectable_edges'):
                return

            selected_edges = [e for e in self._selectable_edges if e.id in selected_ids]

            if not selected_edges:
                return

            # Für jede Kante einen konischen Tubus erstellen (simuliert Chamfer)
            for i, edge in enumerate(selected_edges):
                try:
                    # Punkte der Kante
                    if hasattr(edge, 'points') and edge.points is not None:
                        points = edge.points
                    elif hasattr(edge, 'line_mesh') and edge.line_mesh is not None:
                        # Aus LineMesh extrahieren
                        line_mesh = edge.line_mesh
                        points = line_mesh.points
                    else:
                        # Fallback: Nur Zentrumspunkt
                        center = edge.center
                        points = np.array([
                            [center[0] - edge.length/2, center[1], center[2]],
                            [center[0] + edge.length/2, center[1], center[2]]
                        ])

                    # Erstelle Tube mit verjüngtem Radius (simuliert 45° Chamfer)
                    if len(points) >= 2:
                        tube = pv.Line(points[0], points[-1])
                        # Chamfer: Radius nimmt ab (tapered)
                        tube = tube.tube(radius=distance * 0.7, n_sides=8)

                        actor_name = f'chamfer_preview_{i}'
                        self.plotter.add_mesh(
                            tube,
                            color='#ff6600',  # Orange-Rot
                            opacity=0.6,
                            name=actor_name,
                            pickable=False,
                            smooth_shading=False  # Flach für Chamfer-Look
                        )

                        self._chamfer_preview_actors.append(actor_name)

                except Exception as e:
                    logger.debug(f"Chamfer Preview Edge Error: {e}")

            logger.debug(f"Chamfer Preview: {len(selected_edges)} edges, distance={distance}mm")

        except Exception as e:
            logger.debug(f"Chamfer Preview Generation Error: {e}")

    def _clear_chamfer_preview(self):
        """Entfernt die Chamfer-Preview."""
        try:
            for actor_name in self._chamfer_preview_actors:
                self.plotter.remove_actor(actor_name)
            self._chamfer_preview_actors.clear()
        except Exception as e:
            logger.debug(f"Clear Chamfer Preview Error: {e}")

    # ========================================================================
    # Cleanup
    # ========================================================================

    def clear_all_feature_previews(self):
        """Entfernt alle Feature-Previews."""
        self._clear_shell_preview()
        self._clear_fillet_preview()
        self._clear_chamfer_preview()
