"""
MashCad - Viewport Extrude Mixin
Extrusion-bezogene Methoden für den 3D Viewport
"""

import numpy as np
from loguru import logger


class ExtrudeMixin:
    """Mixin mit allen Extrude-bezogenen Methoden"""
    
    def set_extrude_mode(self, enabled):
        """
        Aktiviert den Extrude-Modus und initialisiert den Detector.

        UX-IMPROVEMENT: X-Ray Vision (Bodies werden halbtransparent)
        User-Problem: "muss oft erst den körper unsichtbar machen um fläche zu selektieren"
        Lösung: Bodies automatisch 70% transparent → kein manuelles Unsichtbar-Machen!

        FIX: _body_actors ist Dict[str, tuple[str]] (actor names), NICHT Dict mit mesh_actor key
        """
        self.extrude_mode = enabled

        if enabled:
            self.selected_face_ids.clear()
            self._drag_screen_vector = np.array([0.0, -1.0])

            # X-RAY VISION: Bodies halbtransparent machen
            logger.debug(f"🔍 X-Ray Vision: Aktiviere für {len(self._body_actors)} Bodies")
            for body_id, actor_names in self._body_actors.items():
                # actor_names ist ein Tuple wie ("body_xyz_m", "body_xyz_e")
                # Erstes Element ist immer der Mesh-Actor
                if not actor_names:
                    logger.debug(f"⚠️ Body {body_id}: Keine Actors gefunden")
                    continue

                mesh_actor_name = actor_names[0]  # "body_{id}_m"

                # Actor aus Renderer holen
                if mesh_actor_name in self.plotter.renderer.actors:
                    mesh_actor = self.plotter.renderer.actors[mesh_actor_name]
                    try:
                        # 30% opacity = gut sichtbar aber Face-Picking möglich
                        mesh_actor.GetProperty().SetOpacity(0.3)
                        logger.debug(f"✅ Body {body_id}: X-Ray Mode aktiviert (30% opacity)")
                    except Exception as e:
                        logger.warning(f"❌ Konnte Opacity nicht setzen für {body_id}: {e}")
                else:
                    logger.debug(f"⚠️ Actor {mesh_actor_name} nicht in Renderer gefunden")

            # Performance Optimization Phase 2.3: Display-Mesh Force-Refresh
            # Lade Detector neu mit extrude_mode=True, um Bodies mit höherer Pick-Priority zu laden
            logger.debug("🔄 Force-Refresh: Lade Detector neu mit Extrude-Mode Priority")
            self._load_detector_mesh_data()

            self._draw_selectable_faces_from_detector()
            self.plotter.render()
        else:
            self.selected_face_ids.clear()
            self._clear_face_actors()
            self._clear_preview()

            # X-RAY VISION: Bodies zurück zu normal (90% opacity)
            logger.debug(f"🔍 X-Ray Vision: Deaktiviere für {len(self._body_actors)} Bodies")
            for body_id, actor_names in self._body_actors.items():
                if not actor_names:
                    continue

                mesh_actor_name = actor_names[0]  # "body_{id}_m"

                if mesh_actor_name in self.plotter.renderer.actors:
                    mesh_actor = self.plotter.renderer.actors[mesh_actor_name]
                    try:
                        mesh_actor.GetProperty().SetOpacity(0.9)
                        logger.debug(f"✅ Body {body_id}: X-Ray Mode deaktiviert (90% opacity)")
                    except Exception as e:
                        logger.warning(f"❌ Konnte Opacity nicht zurücksetzen für {body_id}: {e}")

            self.plotter.render()
            
    def get_extrusion_data_for_kernel(self):
        """Gibt die Shapely-Polygone für den Kernel zurück"""
        data = []
        for fid in self.selected_face_ids:
            face = next((f for f in self.detector.selection_faces if f.id == fid), None)
            if face and face.domain_type.startswith('sketch'):
                data.append({
                    'poly': face.shapely_poly,
                    'sketch_id': face.owner_id
                })
        return data
    
    def show_extrude_preview(self, height, operation="New Body"):
        """Erzeugt die 3D-Vorschau der Extrusion mit operation-basierter Farbe."""
        self._clear_preview()
        self.extrude_height = height
        
        if not self.selected_face_ids or abs(height) < 0.1:
            return

        try:
            preview_meshes = []
            for fid in self.selected_face_ids:
                face = next((f for f in self.detector.selection_faces if f.id == fid), None)
                
                if face and face.display_mesh:
                    normal = np.array(face.plane_normal)
                    p_mesh = face.display_mesh.extrude(normal * height, capping=True)
                    preview_meshes.append(p_mesh)

            if preview_meshes:
                combined = preview_meshes[0]
                for i in range(1, len(preview_meshes)):
                    combined = combined.merge(preview_meshes[i])
                
                # Farbe basierend auf Operation
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
            logger.error(f"Preview error: {e}")
    
    def confirm_extrusion(self, operation="New Body"):
        """Bestätigt Extrusion und sendet Signal"""
        faces = list(self.selected_face_ids)
        height = self.extrude_height
        
        self._clear_preview()
        self.set_extrude_mode(False)
        self.set_all_bodies_visible(True)
        
        if not faces or abs(height) < 0.001:
            return

        if -1 in faces:
            faces.remove(-1)
        
        if faces:
            self.extrude_requested.emit(list(faces), height, operation)
    
    def _cache_drag_direction_for_face_v2(self, face):
        """
        Berechnet den 2D-Bildschirmvektor und speichert den 3D-Ankerpunkt
        für korrekte Skalierung.
        """
        try:
            normal = np.array(face.plane_normal, dtype=float)
            if np.linalg.norm(normal) < 1e-6:
                normal = np.array([0, 0, 1], dtype=float)
            
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

            self._drag_anchor_3d = center

            renderer = self.plotter.renderer
            
            def to_screen(pt_3d):
                renderer.SetWorldPoint(pt_3d[0], pt_3d[1], pt_3d[2], 1.0)
                renderer.WorldToDisplay()
                disp = renderer.GetDisplayPoint()
                return np.array([disp[0], disp[1]])

            p1 = to_screen(center)
            p2 = to_screen(center + normal * 10.0)
            
            vec = p2 - p1
            vec[1] = -vec[1]  # Y-Achsen Korrektur

            length = np.linalg.norm(vec)
            
            if length < 1.0:
                self._drag_screen_vector = np.array([0.0, -1.0])
            else:
                self._drag_screen_vector = vec / length
                
        except Exception as e:
            logger.error(f"Drag direction error: {e}")
            self._drag_screen_vector = np.array([0.0, -1.0])
            self._drag_anchor_3d = np.array([0, 0, 0])

    def _get_pixel_to_world_scale(self, anchor_point_3d):
        """
        Berechnet, wie viele Welt-Einheiten ein Pixel entspricht.
        """
        if anchor_point_3d is None:
            return 0.1
        
        try:
            renderer = self.plotter.renderer
            
            renderer.SetWorldPoint(*anchor_point_3d, 1.0)
            renderer.WorldToDisplay()
            p1_disp = renderer.GetDisplayPoint()
            
            p2_disp_x = p1_disp[0] + 100.0
            p2_disp_y = p1_disp[1]
            p2_disp_z = p1_disp[2]
            
            renderer.SetDisplayPoint(p2_disp_x, p2_disp_y, p2_disp_z)
            renderer.DisplayToWorld()
            world_pt = renderer.GetWorldPoint()
            
            if world_pt[3] != 0:
                p2_world = np.array(world_pt[:3]) / world_pt[3]
            else:
                p2_world = np.array(world_pt[:3])

            dist_world = np.linalg.norm(p2_world - anchor_point_3d)
            
            if dist_world == 0:
                return 0.1
            return dist_world / 100.0
            
        except Exception:
            return 0.1
    
    def _calculate_extrude_delta(self, current_pos):
        """Berechnet delta mit dynamischer Skalierung."""
        dx = current_pos.x() - self.drag_start_pos.x()
        dy = current_pos.y() - self.drag_start_pos.y()
        mouse_vec = np.array([dx, dy])
        
        projection_pixels = np.dot(mouse_vec, self._drag_screen_vector)
        
        anchor = getattr(self, '_drag_anchor_3d', None)
        scale_factor = self._get_pixel_to_world_scale(anchor)
        
        return projection_pixels * scale_factor

    def _clear_preview(self):
        """Entfernt die Extrude-Vorschau"""
        if self._preview_actor:
            try:
                self.plotter.remove_actor(self._preview_actor)
            except:
                pass
            self._preview_actor = None
