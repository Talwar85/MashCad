"""
MashCad - Viewport Body Rendering Mixin
Body-bezogene Rendering-Methoden für den 3D Viewport
PERFORMANCE: Actor Pooling implementiert (Phase 2)
"""

import numpy as np
from loguru import logger
from typing import Dict, Optional, Tuple
import hashlib

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

from PySide6.QtGui import QColor
from gui.viewport.render_queue import request_render  # Phase 4: Performance
from gui.viewport.section_view_mixin import SectionClipCache  # Phase 5: Section Cache
from config.feature_flags import is_enabled  # Performance Plan Phase 2


class ActorPool:
    """
    PERFORMANCE: Wiederverwendbare VTK Actor Pool.

    Verhindert teures Destroy/Recreate bei Body-Updates.
    Stattdessen wird nur der Mapper aktualisiert.

    Vorteile:
    - Kein VTK Graphics Memory Deallocation/Reallocation
    - Kein Shader-Recompiling
    - ~200-500ms Ersparnis pro Boolean-Operation
    """

    # Class-level pool für alle Viewports
    _mesh_hashes: Dict[str, str] = {}  # actor_name -> mesh_hash

    @classmethod
    def compute_mesh_hash(cls, mesh) -> str:
        """Berechnet schnellen Hash für Mesh-Identität."""
        if mesh is None:
            return "none"
        try:
            # Schneller Hash basierend auf Geometrie-Eigenschaften
            hash_data = f"{mesh.n_points}_{mesh.n_cells}_{mesh.bounds}"
            return hashlib.md5(hash_data.encode()).hexdigest()[:16]
        except Exception:
            return "unknown"

    @classmethod
    def needs_update(cls, actor_name: str, mesh) -> bool:
        """Prüft ob Mesh-Update nötig ist (Hash-Vergleich)."""
        new_hash = cls.compute_mesh_hash(mesh)
        old_hash = cls._mesh_hashes.get(actor_name)

        if old_hash == new_hash:
            return False  # Mesh unverändert

        cls._mesh_hashes[actor_name] = new_hash
        return True

    @classmethod
    def clear_hash(cls, actor_name: str):
        """Entfernt Hash für Actor (bei Löschung)."""
        cls._mesh_hashes.pop(actor_name, None)

    @classmethod
    def clear_all(cls):
        """Leert alle Hashes (bei Clear All)."""
        cls._mesh_hashes.clear()


class BodyRenderingMixin:
    """Mixin mit allen Body-Rendering Methoden"""
    
    def add_body(self, bid, name, mesh_obj=None, edge_mesh_obj=None, color=None,
                 verts=None, faces=None, normals=None, edges=None, edge_lines=None):
        """
        Fügt einen Körper hinzu.
        Erkennt automatisch Legacy-Listen-Aufrufe.

        PERFORMANCE: Actor Pooling - wiederverwendet Actors statt Destroy/Recreate
        """
        if not HAS_PYVISTA:
            return

        # Auto-Fix: Legacy Listen-Aufruf
        if isinstance(mesh_obj, list):
            verts = mesh_obj
            faces = edge_mesh_obj
            mesh_obj = None
            edge_mesh_obj = None

        # PERFORMANCE: Prüfe ob Actor existiert und nur Mapper-Update nötig ist
        n_mesh = f"body_{bid}_m"
        n_edge = f"body_{bid}_e"
        existing_actors = self._body_actors.get(bid, ())

        # Check if we can reuse existing actors (mesh changed check)
        # Phase 2.1: Redundanter Renderer-Check entfernt
        can_reuse_mesh = (n_mesh in existing_actors and mesh_obj is not None)
        can_reuse_edge = (n_edge in existing_actors and edge_mesh_obj is not None)

        # Only remove if we can't reuse
        if bid in self._body_actors and not (can_reuse_mesh or can_reuse_edge):
            for n in self._body_actors[bid]:
                try:
                    self.plotter.remove_actor(n)
                    ActorPool.clear_hash(n)
                except Exception as e:
                    logger.debug(f"[body_mixin] Fehler beim Entfernen des Actors: {e}")
        
        actors_list = []
        # Verbesserte Standardfarbe: Warmes Silber-Grau (wie CAD)
        if color is None:
            col_rgb = (0.72, 0.72, 0.75)  # Silber-Grau statt neutralgrau
        elif isinstance(color, str):
            c = QColor(color)
            col_rgb = (c.redF(), c.greenF(), c.blueF())
        else:
            col_rgb = tuple(color)

        try:
            # Pfad A: Modernes PyVista Objekt
            if mesh_obj is not None:
                has_normals = "Normals" in mesh_obj.point_data
                if not has_normals:
                    try:
                        mesh_obj = mesh_obj.compute_normals(
                            cell_normals=False,
                            point_normals=True,
                            split_vertices=True,
                            feature_angle=30.0,
                            consistent_normals=True,
                            auto_orient_normals=True,
                        )
                        has_normals = True
                    except Exception:
                        pass

                # PERFORMANCE: Actor Pooling - wiederverwendet Actor wenn möglich
                if can_reuse_mesh and ActorPool.needs_update(n_mesh, mesh_obj):
                    # Reuse existing actor - only update mapper (FAST PATH)
                    actor = self.plotter.renderer.actors[n_mesh]
                    mapper = actor.GetMapper()
                    mapper.SetInputData(mesh_obj)
                    mapper.Modified()
                    actor.SetVisibility(True)
                    logger.debug(f"♻️ Actor reused, mapper updated for {bid}: {mesh_obj.n_points} pts")
                    actors_list.append(n_mesh)

                elif can_reuse_mesh and not ActorPool.needs_update(n_mesh, mesh_obj):
                    # Mesh unchanged - skip update entirely (FASTEST PATH)
                    logger.debug(f"⏭️ Mesh unchanged for {bid}, skipping update")
                    actors_list.append(n_mesh)

                else:
                    # No existing actor - create new (SLOW PATH, but unavoidable)
                    self.plotter.add_mesh(
                        mesh_obj, color=col_rgb, name=n_mesh, show_edges=False,
                        smooth_shading=True,
                        pbr=True,
                        metallic=0.05,
                        roughness=0.55,
                        diffuse=0.95,
                        specular=0.5,
                        specular_power=40,
                        pickable=True
                    )

                    if n_mesh in self.plotter.renderer.actors:
                        actor = self.plotter.renderer.actors[n_mesh]
                        actor.SetVisibility(True)
                        face_mapper = actor.GetMapper()
                        face_mapper.SetResolveCoincidentTopologyToPolygonOffset()
                        face_mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(2, 2)
                        # Store hash for future comparisons
                        ActorPool._mesh_hashes[n_mesh] = ActorPool.compute_mesh_hash(mesh_obj)
                        logger.debug(f"🆕 New actor created for {bid}: {mesh_obj.n_points} pts")

                    actors_list.append(n_mesh)

                # Edge mesh handling
                if edge_mesh_obj is not None:
                    # PERFORMANCE: Actor Pooling for edges too
                    if can_reuse_edge and ActorPool.needs_update(n_edge, edge_mesh_obj):
                        # Reuse edge actor — reset properties in case highlighting changed them
                        edge_actor = self.plotter.renderer.actors[n_edge]
                        edge_actor.GetProperty().SetRenderLinesAsTubes(False)
                        edge_actor.GetProperty().SetLineWidth(1.5)
                        edge_actor.GetProperty().SetColor(0.15, 0.15, 0.17)
                        edge_mapper = edge_actor.GetMapper()
                        edge_mapper.SetInputData(edge_mesh_obj)
                        edge_mapper.SetResolveCoincidentTopologyToPolygonOffset()
                        edge_mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-2, -2)
                        edge_mapper.Modified()
                        logger.debug(f"♻️ Edge actor reused for {bid}")

                    elif can_reuse_edge and not ActorPool.needs_update(n_edge, edge_mesh_obj):
                        # Edge unchanged
                        pass

                    else:
                        # Create new edge actor
                        self.plotter.add_mesh(
                            edge_mesh_obj,
                            color=(0.15, 0.15, 0.17),
                            line_width=1.5,
                            name=n_edge,
                            pickable=False,
                            render_lines_as_tubes=False,
                            lighting=False,
                        )

                        # Phase 2.2: Duplicate Mapper SetInputData entfernt
                        if n_edge in self.plotter.renderer.actors:
                            edge_actor = self.plotter.renderer.actors[n_edge]
                            edge_mapper = edge_actor.GetMapper()
                            edge_mapper.SetResolveCoincidentTopologyToPolygonOffset()
                            edge_mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-2, -2)

                    actors_list.append(n_edge)
                
                self.bodies[bid] = {'mesh': mesh_obj, 'color': col_rgb}

                # PERFORMANCE Phase 5: Invalidate section cache for this body
                # (mesh changed, so cached clipped versions are stale)
                SectionClipCache.invalidate_body(bid)
                
                # FIX: Invalidate detected_faces for this body
                # (mesh changed, so face_ids are stale - fixes Push/Pull + Features)
                if hasattr(self, 'detected_faces'):
                    original_count = len(self.detected_faces)
                    self.detected_faces = [
                        f for f in self.detected_faces 
                        if f.get('body_id') != bid
                    ]
                    removed = original_count - len(self.detected_faces)
                    if removed > 0:
                        logger.debug(f"Invalidated {removed} detected_faces for body {bid}")
                
                # FIX: Also invalidate GeometryDetector cache if it has body faces
                # This ensures fresh face detection on next feature operation
                if hasattr(self, 'detector') and hasattr(self.detector, 'selection_faces'):
                    detector_faces_before = len(self.detector.selection_faces)
                    self.detector.selection_faces = [
                        f for f in self.detector.selection_faces
                        if getattr(f, 'owner_id', None) != bid
                    ]
                    removed_detector = detector_faces_before - len(self.detector.selection_faces)
                    if removed_detector > 0:
                        logger.debug(f"Invalidated {removed_detector} detector faces for body {bid}")

                # ✅ FIX: Re-apply Section View if active
                if hasattr(self, '_section_view_enabled') and self._section_view_enabled:
                    logger.debug(f"🔪 Re-applying section clipping to updated body {bid}")
                    # Re-clip this specific body
                    if bid in self._body_actors and self._body_actors[bid]:
                        mesh_actor_name = self._body_actors[bid][0]
                        if mesh_actor_name in self.plotter.renderer.actors:
                            actor = self.plotter.renderer.actors[mesh_actor_name]
                            mapper = actor.GetMapper()

                            # Get plane info
                            plane_origins = {
                                "XY": [0, 0, self._section_position],
                                "YZ": [self._section_position, 0, 0],
                                "XZ": [0, self._section_position, 0]
                            }
                            plane_normals = {
                                "XY": [0, 0, 1],
                                "YZ": [1, 0, 0],
                                "XZ": [0, 1, 0]
                            }
                            origin = plane_origins.get(self._section_plane, [0, 0, self._section_position])
                            normal = plane_normals.get(self._section_plane, [0, 0, 1])
                            if self._section_invert:
                                normal = [-n for n in normal]

                            # Clip the new mesh
                            clipped_mesh = mesh_obj.clip(
                                normal=normal,
                                origin=origin,
                                invert=False
                            )
                            mapper.SetInputData(clipped_mesh)
                            logger.debug(f"✅ Section clipping re-applied to body {bid}")

            # Pfad B: Legacy Listen (Verts/Faces)
            elif verts and faces:
                v = np.array(verts, dtype=np.float32)
                f = []
                for face in faces:
                    f.extend([len(face)] + list(face))
                mesh = pv.PolyData(v, np.array(f, dtype=np.int32))
                
                if normals:
                    try:
                        n = np.array(normals, dtype=np.float32)
                        if len(n) == len(v):
                            mesh.point_data["Normals"] = n
                    except Exception as e:
                        logger.debug(f"[body_mixin] Fehler beim Setzen der Normalen: {e}")
                
                n_mesh = f"body_{bid}_m"
                self.plotter.add_mesh(mesh, color=col_rgb, name=n_mesh, show_edges=False, smooth_shading=True, pickable=True)
                
                if n_mesh in self.plotter.renderer.actors:
                    self.plotter.renderer.actors[n_mesh].SetVisibility(True)
                    
                actors_list.append(n_mesh)
                self.bodies[bid] = {'mesh': mesh, 'color': col_rgb}
                
            self._body_actors[bid] = tuple(actors_list)

            # ✅ CRITICAL: Force render after Mapper update
            # Ensures VTK displays the new mesh immediately
            request_render(self.plotter)

        except Exception as e:
            logger.error(f"Add body error: {e}")

    def set_body_visibility(self, body_id, visible):
        """Setzt die Sichtbarkeit eines Körpers"""
        if body_id not in self._body_actors:
            return
        try:
            actors = self._body_actors[body_id]
            for name in actors:
                if name in self.plotter.renderer.actors:
                    self.plotter.renderer.actors[name].SetVisibility(visible)
            request_render(self.plotter)
        except Exception as e:
            logger.error(f"Set visibility error: {e}")

    def set_all_bodies_visible(self, visible):
        """Setzt Sichtbarkeit aller Körper"""
        for bid in self._body_actors:
            self.set_body_visibility(bid, visible)

    def clear_bodies(self):
        """Entfernt alle Körper"""
        for bid in list(self._body_actors.keys()):
            for name in self._body_actors[bid]:
                try:
                    self.plotter.remove_actor(name)
                    ActorPool.clear_hash(name)  # PERFORMANCE: Clear hash tracking
                except Exception as e:
                    logger.debug(f"[body_mixin] Fehler beim Entfernen des Actors: {e}")
        self._body_actors.clear()
        self.bodies.clear()
        ActorPool.clear_all()  # PERFORMANCE: Clear all hashes





    def get_body_mesh(self, body_id):
        """Gibt das Mesh eines Körpers zurück"""
        if body_id in self.bodies:
            return self.bodies[body_id].get('mesh')
        return None

    def is_body_visible(self, body_id):
        """Prüft ob ein Körper sichtbar ist"""
        if body_id not in self._body_actors:
            return False
        try:
            name = self._body_actors[body_id][0]
            if name in self.plotter.renderer.actors:
                return self.plotter.renderer.actors[name].GetVisibility()
        except Exception as e:
            logger.debug(f"[body_mixin] Fehler beim Prüfen der Sichtbarkeit: {e}")
        return False

    def _restore_body_colors(self):
        """Setzt alle Bodies auf ihre Originalfarbe zurück"""
        for bid, data in self.bodies.items():
            if bid in self._body_actors:
                n_mesh = self._body_actors[bid][0]
                if n_mesh in self.plotter.renderer.actors:
                    actor = self.plotter.renderer.actors[n_mesh]
                    col = data.get('color', (0.5, 0.5, 0.5))
                    actor.GetProperty().SetColor(*col)

    # HINWEIS: Die folgenden Methoden werden von viewport_pyvista.py bereitgestellt (MRO):
    # - _draw_body_face_highlight() -> viewport_pyvista.py:6706
    # - _clear_body_face_highlight() -> viewport_pyvista.py:6773
    # - _clear_face_actors() -> viewport_pyvista.py:7080
    # Diese wurden entfernt (waren Dead Code)

    def _draw_body_face_selection(self, pos, normal):
        """Zeichnet Selection-Highlight für selektierte Body-Fläche"""
        try:
            center = np.array(pos)
            n = np.array(normal)
            norm_len = np.linalg.norm(n)
            if norm_len < 1e-6:
                return
            n = n / norm_len
            
            if abs(n[2]) < 0.9:
                u = np.cross(n, [0, 0, 1])
            else:
                u = np.cross(n, [1, 0, 0])
            u = u / np.linalg.norm(u)
            v = np.cross(n, u)
            
            size = 15.0
            pts = [
                center + size * (-u - v),
                center + size * (u - v),
                center + size * (u + v),
                center + size * (-u + v),
            ]
            
            import pyvista as pv
            quad = pv.PolyData(np.array(pts), faces=[4, 0, 1, 2, 3])
            
            self.plotter.add_mesh(
                quad, color='#ffaa00', opacity=0.5,
                name='body_face_select', pickable=False
            )
            request_render(self.plotter)
            
        except Exception:
            pass

    # HINWEIS: _clear_face_actors() wird von viewport_pyvista.py:7080 bereitgestellt (MRO)
    # Die Methode wurde hier entfernt (war Dead Code)
