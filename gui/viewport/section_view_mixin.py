"""
Section View Mixin für PyVista Viewport

Implementiert Fusion 360-ähnliche Schnittansicht zur Inspektion von Boolean Cuts
und innerer Geometrie.

Features:
- Schnittebenen: XY, YZ, XZ oder custom
- Dynamische Position (Slider)
- Schnittflächen-Highlighting
- Half-View (zeigt nur eine Seite)

Autor: Claude (Section View Feature)
Datum: 2026-01-22
"""

import numpy as np
from loguru import logger


class SectionViewMixin:
    """
    Mixin für Section View / Schnittansicht.

    User-Problem: "ich brauchte für körper noch schnittansicht um besser zu prüfen ob cuts gingen"
    Lösung: Fusion 360-ähnliche Section Analysis mit Schnittebenen-Kontrolle
    """

    def _init_section_view(self):
        """Initialisiert Section View State (wird von Viewport.__init__() aufgerufen)"""
        # Section View State
        self._section_view_enabled = False
        self._section_plane = "XY"  # "XY", "YZ", "XZ", "Custom"
        self._section_position = 0.0  # Position entlang Normalen-Achse
        self._section_show_cut_face = True  # Schnittflächen highlighten
        self._section_invert = False  # Welche Seite angezeigt wird

        # PyVista Plane Widget (für interaktive Kontrolle)
        self._section_plane_widget = None

    def enable_section_view(self, plane: str = "XY", position: float = 0.0):
        """
        Aktiviert Schnittansicht.

        Args:
            plane: "XY", "YZ", "XZ" oder "Custom"
            position: Position der Schnittebene (in mm)
        """
        logger.info(f"🔪 Section View aktiviert: Ebene={plane}, Position={position}mm")

        self._section_view_enabled = True
        self._section_plane = plane
        self._section_position = position

        # Plane-Definitionen
        plane_origins = {
            "XY": [0, 0, position],
            "YZ": [position, 0, 0],
            "XZ": [0, position, 0]
        }

        plane_normals = {
            "XY": [0, 0, 1],  # Z-Achse
            "YZ": [1, 0, 0],  # X-Achse
            "XZ": [0, 1, 0]   # Y-Achse
        }

        origin = plane_origins.get(plane, [0, 0, position])
        normal = plane_normals.get(plane, [0, 0, 1])

        # Invertiere Normal falls gewünscht
        if self._section_invert:
            normal = [-n for n in normal]

        # Wende Clipping auf alle Bodies an
        self._apply_section_clipping(origin, normal)

        # Optional: Zeige Schnittflächen
        if self._section_show_cut_face:
            self._highlight_section_faces(origin, normal)

        self.plotter.render()

    def disable_section_view(self):
        """Deaktiviert Schnittansicht und stellt Bodies wieder her."""
        if not self._section_view_enabled:
            return

        logger.info("🔪 Section View deaktiviert")

        self._section_view_enabled = False

        # Entferne Clipping von allen Bodies
        self._remove_section_clipping()

        # Entferne Schnittflächen-Highlights
        self._remove_section_highlights()

        # ✅ WICHTIG: Force Render nach Wiederherstellung
        self.plotter.render_window.Render()
        self.plotter.render()

    def update_section_position(self, position: float):
        """
        Aktualisiert Position der Schnittebene dynamisch.

        Args:
            position: Neue Position (in mm)
        """
        if not self._section_view_enabled:
            return

        self._section_position = position
        logger.debug(f"🔪 Section Position: {position:.1f}mm")

        # Re-enable mit neuer Position
        self.enable_section_view(self._section_plane, position)

    def toggle_section_invert(self):
        """Invertiert welche Seite der Schnittebene angezeigt wird."""
        self._section_invert = not self._section_invert
        logger.debug(f"🔪 Section Invert: {self._section_invert}")

        if self._section_view_enabled:
            self.enable_section_view(self._section_plane, self._section_position)

    def _apply_section_clipping(self, origin, normal):
        """
        Wendet Clipping-Ebene auf alle Body-Actors an.

        Args:
            origin: Punkt auf der Ebene [x, y, z]
            normal: Normale der Ebene [nx, ny, nz]
        """
        clipped_count = 0

        for body_id, actor_names in self._body_actors.items():
            if not actor_names:
                continue

            mesh_actor_name = actor_names[0]  # Body Mesh Actor

            if mesh_actor_name in self.plotter.renderer.actors:
                actor = self.plotter.renderer.actors[mesh_actor_name]

                try:
                    # ✅ FIX: Hole IMMER das Original-Mesh aus self.bodies (nicht aus Mapper!)
                    # Grund: Mapper könnte bereits geclipptes Mesh enthalten
                    if body_id not in self.bodies:
                        logger.warning(f"⚠️ Body {body_id} nicht in self.bodies gefunden")
                        continue

                    original_mesh = self.bodies[body_id].get('mesh')
                    if not original_mesh:
                        logger.warning(f"⚠️ Body {body_id} hat kein Mesh in self.bodies")
                        continue

                    # Clip mit Plane (erstellt neues Mesh-Objekt, modifiziert Original NICHT)
                    clipped_mesh = original_mesh.clip(
                        normal=normal,
                        origin=origin,
                        invert=False  # Zeige Seite in Richtung Normal
                    )

                    # Update Actor mit geclipptem Mesh
                    mapper = actor.GetMapper()
                    mapper.SetInputData(clipped_mesh)
                    clipped_count += 1
                    logger.debug(f"✅ Body {body_id}: Clipping angewendet")

                except Exception as e:
                    logger.warning(f"⚠️ Clipping fehlgeschlagen für Body {body_id}: {e}")

        logger.info(f"✅ Section Clipping auf {clipped_count} Bodies angewendet")

    def _remove_section_clipping(self):
        """Entfernt Clipping von allen Bodies (stellt Original-Mesh wieder her)."""
        restored_count = 0

        for body_id, actor_names in self._body_actors.items():
            if not actor_names:
                continue

            mesh_actor_name = actor_names[0]

            if mesh_actor_name in self.plotter.renderer.actors:
                actor = self.plotter.renderer.actors[mesh_actor_name]

                try:
                    # ✅ FIX: Hole Original-Mesh direkt aus self.bodies (viewport hat kein document!)
                    if body_id in self.bodies:
                        original_mesh = self.bodies[body_id].get('mesh')
                        if original_mesh:
                            # Reset Mapper mit Original-Mesh
                            mapper = actor.GetMapper()
                            mapper.SetInputData(original_mesh)
                            restored_count += 1
                            logger.debug(f"✅ Body {body_id}: Clipping entfernt, Original-Mesh wiederhergestellt")
                        else:
                            logger.warning(f"⚠️ Body {body_id}: Kein Original-Mesh gefunden in bodies dict")
                    else:
                        logger.warning(f"⚠️ Body {body_id}: Nicht in self.bodies gefunden")

                except Exception as e:
                    logger.warning(f"⚠️ Clipping-Entfernung fehlgeschlagen für Body {body_id}: {e}")

        if restored_count > 0:
            logger.info(f"✅ Section Clipping von {restored_count} Bodies entfernt")
        else:
            logger.error("❌ Kein Body wurde wiederhergestellt!")

    def _highlight_section_faces(self, origin, normal):
        """
        Hebt Schnittflächen hervor (optional).

        Args:
            origin: Schnittebene Origin
            normal: Schnittebene Normal
        """
        import pyvista as pv
        import numpy as np

        # Erstelle eine sichtbare Schnittebene (wie in Fusion 360)
        # Berechne Bounds aller Bodies
        all_bounds = []
        for body_id in self._body_actors.keys():
            if body_id in self.bodies:
                mesh = self.bodies[body_id].get('mesh')
                if mesh:
                    all_bounds.append(mesh.bounds)

        if not all_bounds:
            return

        # Kombiniere Bounds
        combined_bounds = [
            min(b[0] for b in all_bounds),  # xmin
            max(b[1] for b in all_bounds),  # xmax
            min(b[2] for b in all_bounds),  # ymin
            max(b[3] for b in all_bounds),  # ymax
            min(b[4] for b in all_bounds),  # zmin
            max(b[5] for b in all_bounds),  # zmax
        ]

        # Erstelle große Schnittebene
        size = max(
            combined_bounds[1] - combined_bounds[0],
            combined_bounds[3] - combined_bounds[2],
            combined_bounds[5] - combined_bounds[4]
        ) * 1.5

        # Berechne Ebenen-Koordinatensystem
        normal_vec = np.array(normal) / np.linalg.norm(normal)

        # Finde zwei orthogonale Vektoren zur Normalen
        if abs(normal_vec[2]) < 0.9:
            u = np.cross(normal_vec, [0, 0, 1])
        else:
            u = np.cross(normal_vec, [1, 0, 0])
        u = u / np.linalg.norm(u)
        v = np.cross(normal_vec, u)

        # Erstelle Ebene als Quad
        center = np.array(origin)
        corners = [
            center - size * u - size * v,
            center + size * u - size * v,
            center + size * u + size * v,
            center - size * u + size * v,
        ]

        plane_mesh = pv.PolyData(
            np.array(corners),
            faces=[4, 0, 1, 2, 3]
        )

        # Rendere halbtransparente Ebene
        try:
            self.plotter.remove_actor('section_plane_indicator')
        except:
            pass

        self.plotter.add_mesh(
            plane_mesh,
            color='#FF6B00',  # Orange
            opacity=0.15,
            name='section_plane_indicator',
            pickable=False,
            show_edges=True,
            edge_color='#FF6B00',
            line_width=2
        )

        logger.debug("🎨 Schnittebene visualisiert")

    def _remove_section_highlights(self):
        """Entfernt Schnittflächen-Highlights."""
        try:
            self.plotter.remove_actor('section_plane_indicator')
            logger.debug("🎨 Schnittebene-Indicator entfernt")
        except:
            pass

    def get_section_bounds(self):
        """
        Berechnet sinnvolle Bounds für Section-Position-Slider.

        Returns:
            (min, max, default): Bounds in mm
        """
        if not hasattr(self, 'document') or not self.document.bodies:
            return (-100.0, 100.0, 0.0)

        # Berechne Bounding Box aller Bodies
        all_mins = []
        all_maxs = []

        for body in self.document.bodies:
            if body.vtk_mesh:
                bounds = body.vtk_mesh.bounds  # (xmin, xmax, ymin, ymax, zmin, zmax)
                all_mins.append([bounds[0], bounds[2], bounds[4]])
                all_maxs.append([bounds[1], bounds[3], bounds[5]])

        if not all_mins:
            return (-100.0, 100.0, 0.0)

        # Global Min/Max
        global_min = np.min(all_mins, axis=0)
        global_max = np.max(all_maxs, axis=0)

        # Bounds basierend auf Schnittebene
        plane_axis = {
            "XY": 2,  # Z
            "YZ": 0,  # X
            "XZ": 1   # Y
        }

        axis = plane_axis.get(self._section_plane, 2)
        min_pos = global_min[axis]
        max_pos = global_max[axis]
        default_pos = (min_pos + max_pos) / 2.0

        logger.debug(f"📏 Section Bounds: [{min_pos:.1f}, {max_pos:.1f}] mm (default: {default_pos:.1f})")

        return (min_pos, max_pos, default_pos)
