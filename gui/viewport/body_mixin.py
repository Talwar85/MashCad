"""
MashCad - Viewport Body Rendering Mixin
Body-bezogene Rendering-Methoden für den 3D Viewport
"""

import numpy as np
from loguru import logger

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

from PySide6.QtGui import QColor


class BodyRenderingMixin:
    """Mixin mit allen Body-Rendering Methoden"""
    
    def add_body(self, bid, name, mesh_obj=None, edge_mesh_obj=None, color=None, 
                 verts=None, faces=None, normals=None, edges=None, edge_lines=None):
        """
        Fügt einen Körper hinzu. 
        Erkennt automatisch Legacy-Listen-Aufrufe.
        """
        if not HAS_PYVISTA:
            return
        
        # Auto-Fix: Legacy Listen-Aufruf
        if isinstance(mesh_obj, list):
            verts = mesh_obj
            faces = edge_mesh_obj
            mesh_obj = None
            edge_mesh_obj = None

        # Alten Actor entfernen
        if bid in self._body_actors:
            for n in self._body_actors[bid]: 
                try:
                    self.plotter.remove_actor(n)
                except:
                    pass
        
        actors_list = []
        if color is None:
            col_rgb = (0.5, 0.5, 0.5)
        elif isinstance(color, str):
            c = QColor(color)
            col_rgb = (c.redF(), c.greenF(), c.blueF())
        else:
            col_rgb = tuple(color)
            
        try:
            # Pfad A: Modernes PyVista Objekt
            if mesh_obj is not None:
                n_mesh = f"body_{bid}_m"
                has_normals = "Normals" in mesh_obj.point_data
                
                self.plotter.add_mesh(
                    mesh_obj, color=col_rgb, name=n_mesh, show_edges=False,
                    smooth_shading=has_normals, pbr=not has_normals,
                    metallic=0.1, roughness=0.6, pickable=True
                )

                if n_mesh in self.plotter.renderer.actors:
                    actor = self.plotter.renderer.actors[n_mesh]
                    actor.SetVisibility(True)

                    # ✅ CRITICAL FIX: Explizit Mapper mit neuem Mesh aktualisieren
                    # Problem: PyVista's add_mesh() könnte altes Mesh im Mapper cachen
                    # Lösung: Force-Update des VTK Mappers nach Boolean Operations
                    mapper = actor.GetMapper()
                    mapper.SetInputData(mesh_obj)
                    mapper.Modified()  # VTK Update-Signal
                    logger.debug(f"✅ Mapper explizit aktualisiert für Body {bid}: {mesh_obj.n_points} Punkte")

                actors_list.append(n_mesh)
                
                if edge_mesh_obj is not None:
                    n_edge = f"body_{bid}_e"
                    self.plotter.add_mesh(edge_mesh_obj, color="black", line_width=2, name=n_edge, pickable=False)

                    # ✅ Force-Update Edge Mapper too
                    if n_edge in self.plotter.renderer.actors:
                        edge_actor = self.plotter.renderer.actors[n_edge]
                        edge_mapper = edge_actor.GetMapper()
                        edge_mapper.SetInputData(edge_mesh_obj)
                        edge_mapper.Modified()

                    actors_list.append(n_edge)
                
                self.bodies[bid] = {'mesh': mesh_obj, 'color': col_rgb}

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
                    except:
                        pass
                
                n_mesh = f"body_{bid}_m"
                self.plotter.add_mesh(mesh, color=col_rgb, name=n_mesh, show_edges=False, smooth_shading=True, pickable=True)
                
                if n_mesh in self.plotter.renderer.actors:
                    self.plotter.renderer.actors[n_mesh].SetVisibility(True)
                    
                actors_list.append(n_mesh)
                self.bodies[bid] = {'mesh': mesh, 'color': col_rgb}
                
            self._body_actors[bid] = tuple(actors_list)

            # ✅ CRITICAL: Force render after Mapper update
            # Ensures VTK displays the new mesh immediately
            self.plotter.render()

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
            self.plotter.render()
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
                except:
                    pass
        self._body_actors.clear()
        self.bodies.clear()

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
        except:
            pass
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

    def _draw_body_face_highlight(self, pos, normal):
        """Zeichnet Highlight auf gehoverter Body-Fläche"""
        self._clear_body_face_highlight()
        try:
            center = np.array(pos)
            n = np.array(normal)
            norm_len = np.linalg.norm(n)
            if norm_len < 1e-6:
                return
            n = n / norm_len
            
            # Orthogonale Vektoren berechnen
            if abs(n[2]) < 0.9:
                u = np.cross(n, [0, 0, 1])
            else:
                u = np.cross(n, [1, 0, 0])
            u = u / np.linalg.norm(u)
            v = np.cross(n, u)
            
            # Quadrat erstellen
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
                quad, color='#00aaff', opacity=0.4,
                name='body_face_hover', pickable=False
            )
            self.plotter.render()
            
        except Exception as e:
            logger.debug(f"Draw highlight error: {e}")

    def _clear_body_face_highlight(self):
        """Entfernt das Body-Face Highlight"""
        try:
            self.plotter.remove_actor('body_face_hover')
        except:
            pass

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
            self.plotter.render()
            
        except Exception:
            pass

    def _clear_face_actors(self):
        """Entfernt alle Face-Overlay Actors"""
        for actor in self._face_actors:
            try:
                self.plotter.remove_actor(actor)
            except:
                pass
        self._face_actors.clear()
