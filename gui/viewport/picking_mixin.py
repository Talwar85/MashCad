"""
MashCad - Viewport Picking Mixin
Selection und Picking Methoden für den 3D Viewport

TNP v4.0 Integration:
- Verbindet Viewport-Picking mit ShapeNamingService
- Verwaltet SelectionItems statt nur Integer-IDs
- Ermöglicht persistente Shape-Referenzen über Operationen hinweg

TNP v5.0 Integration:
- Capture SelectionContext bei jeder Shape-Selektion
- Speichert view_direction, selection_point, adjacent_shapes
- Ermöglicht Semantic Matching für bessere Resolution-Rate
"""

import numpy as np
from typing import Optional, List, Tuple, Any
from loguru import logger
from config.tolerances import Tolerances  # Phase 5: Zentralisierte Toleranzen

try:
    import vtk
    HAS_VTK = True
except ImportError:
    HAS_VTK = False

try:
    from shapely.geometry import Point
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False


class PickingMixin:
    """
    Mixin mit allen Picking/Selection Methoden.

    TNP v4.0: Selektionen werden als SelectionItems verwaltet,
    die TNP-ShapeIDs enthalten können. Dies ermöglicht persistente
    Referenzen auf Shapes über Boolean-Operationen hinweg.
    """

    def __init__(self):
        # Unified Selection Manager (TNP v4.0)
        from gui.selection_manager import get_selection_manager
        self.selection_manager = get_selection_manager()

        # Legacy: Selektierte Face-IDs für Abwärtskompatibilität
        self.selected_face_ids: set = set()

        # TNP v5.0: SelectionContext storage (face_id -> SelectionContext)
        self._selection_contexts: dict = {}

    # ========================================================================
    # TNP v5.0: SelectionContext Capture
    # ========================================================================

    def _capture_selection_context(
        self,
        face_id: int,
        pick_position: Tuple[float, float, float],
        screen_x: int,
        screen_y: int
    ) -> Optional['SelectionContext']:
        """
        TNP v5.0: Captures SelectionContext for a picked face.

        Args:
            face_id: The selected face ID
            pick_position: 3D position where the pick occurred
            screen_x: Screen X coordinate
            screen_y: Screen Y coordinate

        Returns:
            SelectionContext or None if capture fails
        """
        try:
            from modeling.tnp_v5 import SelectionContext, ShapeType
        except ImportError:
            # TNP v5.0 not available, return None
            return None

        if not hasattr(self, 'detector') or self.detector is None:
            return None

        face = next((f for f in self.detector.selection_faces if f.id == face_id), None)
        if face is None:
            return None

        # Get view direction from camera
        view_direction = self._get_view_direction()

        # Get adjacent shapes
        adjacent_shapes = self._get_adjacent_face_ids(face_id)

        # Get feature context
        feature_context = self._get_feature_context_for_face(face)

        # Get zoom level
        zoom_level = self._get_zoom_level()

        # Get viewport ID (for multi-viewport setups)
        viewport_id = getattr(self, 'viewport_id', None)

        return SelectionContext(
            shape_id=str(face_id),
            selection_point=tuple(pick_position),
            view_direction=view_direction,
            adjacent_shapes=adjacent_shapes,
            feature_context=feature_context,
            screen_position=(screen_x, screen_y),
            zoom_level=zoom_level,
            viewport_id=viewport_id
        )

    def _get_view_direction(self) -> Tuple[float, float, float]:
        """
        TNP v5.0: Get the current camera view direction.

        Returns:
            Normalized view direction vector (dx, dy, dz)
        """
        try:
            if hasattr(self, 'plotter') and hasattr(self.plotter, 'camera_position'):
                # PyVista camera_position: (position, focal_point, view_up)
                cam_pos = self.plotter.camera_position
                if cam_pos and len(cam_pos) >= 2:
                    position = np.array(cam_pos[0])
                    focal_point = np.array(cam_pos[1])
                    direction = focal_point - position
                    norm = np.linalg.norm(direction)
                    if norm > 0:
                        return tuple(direction / norm)
            return (0, 0, -1)  # Default: looking along -Z
        except Exception as e:
            logger.debug(f"[TNP v5.0] Failed to get view direction: {e}")
            return (0, 0, -1)

    def _get_adjacent_face_ids(self, face_id: int) -> List[int]:
        """
        TNP v5.0: Get IDs of faces adjacent to the selected face.

        Uses geometric proximity to find adjacent faces.

        Args:
            face_id: The selected face ID

        Returns:
            List of adjacent face IDs
        """
        if not hasattr(self, 'detector') or self.detector is None:
            return []

        selected_face = next(
            (f for f in self.detector.selection_faces if f.id == face_id),
            None
        )
        if selected_face is None:
            return []

        adjacent = []
        selected_origin = np.array(selected_face.plane_origin)
        selected_normal = np.array(selected_face.plane_normal)
        tolerance = 1.0  # mm tolerance for adjacency

        for face in self.detector.selection_faces:
            if face.id == face_id:
                continue
            if face.domain_type != selected_face.domain_type:
                continue

            face_origin = np.array(face.plane_origin)
            face_normal = np.array(face.plane_normal)

            # Check proximity: faces are adjacent if centers are close
            dist = np.linalg.norm(face_origin - selected_origin)

            # Additional check: faces might share an edge if centers are close
            # and they're not parallel (or coplanar)
            if dist < tolerance * 10:  # Relatively close
                # Check if faces share geometry (non-parallel normals or coplanar)
                dot = np.dot(selected_normal, face_normal)
                if abs(dot) < 0.9 or abs(dot - 1.0) < 0.1:  # Not parallel OR coplanar
                    adjacent.append(face.id)

        return adjacent

    def _get_feature_context_for_face(self, face) -> str:
        """
        TNP v5.0: Get the feature context for a face.

        Args:
            face: SelectionFace object

        Returns:
            Feature ID or empty string
        """
        # Try to get feature from owner_id
        if hasattr(face, 'owner_id'):
            body_id = face.owner_id
            if hasattr(self, 'bodies') and body_id in self.bodies:
                body_data = self.bodies[body_id]
                if isinstance(body_data, dict):
                    body = body_data.get('body')
                else:
                    body = body_data

                if body and hasattr(body, 'feature_id'):
                    return body.feature_id

        # Check for sketch faces
        if hasattr(face, 'domain_type') and face.domain_type.startswith('sketch'):
            if hasattr(face, 'sketch_id'):
                return f"sketch_{face.sketch_id}"

        return ""  # Empty string = no context

    def _get_zoom_level(self) -> Optional[float]:
        """
        TNP v5.0: Get the current zoom level of the viewport.

        Returns:
            Zoom level factor or None
        """
        try:
            if hasattr(self, 'plotter') and hasattr(self.plotter, 'camera_position'):
                cam_pos = self.plotter.camera_position
                if cam_pos and len(cam_pos) >= 2:
                    position = np.array(cam_pos[0])
                    focal_point = np.array(cam_pos[1])
                    distance = np.linalg.norm(position - focal_point)
                    # Convert to approximate zoom factor (larger distance = lower zoom)
                    if distance > 0:
                        return 1000.0 / distance  # Normalized zoom factor
            return None
        except Exception:
            return None

    def get_selection_context(self, face_id: int) -> Optional['SelectionContext']:
        """
        TNP v5.0: Get the SelectionContext for a face.

        Args:
            face_id: The face ID

        Returns:
            SelectionContext or None if not available
        """
        return self._selection_contexts.get(face_id)

    def store_selection_context(self, face_id: int, context) -> None:
        """
        TNP v5.0: Store a SelectionContext for a face.

        Args:
            face_id: The face ID
            context: SelectionContext to store
        """
        self._selection_contexts[face_id] = context

    def _resolve_body_id_for_actor(self, picked_actor):
        """
        Resolves a body id for a picked VTK actor.

        Supports both identical actor objects and raw/wrapped actor variants
        by falling back to VTK actor address comparison.
        """
        if picked_actor is None:
            return None

        # Reuse viewport-level resolver if available.
        if hasattr(self, "_get_body_id_for_actor"):
            try:
                resolved = self._get_body_id_for_actor(picked_actor)
                if resolved is not None:
                    return resolved
            except Exception:
                pass

        body_actors = getattr(self, "_body_actors", {}) or {}
        renderer = getattr(getattr(self, "plotter", None), "renderer", None)
        renderer_actors = getattr(renderer, "actors", {}) if renderer is not None else {}

        picked_addr = None
        if hasattr(picked_actor, "GetAddressAsString"):
            try:
                picked_addr = picked_actor.GetAddressAsString("")
            except Exception:
                picked_addr = None

        for bid, actor_names in body_actors.items():
            for name in actor_names:
                reg_actor = renderer_actors.get(name)
                if reg_actor is None:
                    continue
                if reg_actor is picked_actor:
                    return bid

                if picked_addr and hasattr(reg_actor, "GetAddressAsString"):
                    try:
                        if reg_actor.GetAddressAsString("") == picked_addr:
                            return bid
                    except Exception:
                        continue

        return None
    
    def pick(self, x, y, selection_filter=None):
        """
        Präzises Picking mittels vtkCellPicker (Hardware-gestützt).
        Löst das Problem, dass falsche/verdeckte Flächen gewählt werden.
        """
        if not hasattr(self, 'detector'):
            return -1
        
        if selection_filter is None:
            from gui.geometry_detector import GeometryDetector
            selection_filter = GeometryDetector.SelectionFilter.ALL

        # --- 1. BODY FACES (Hardware Picking) ---
        if "body_face" in selection_filter and HAS_VTK:
            picker = vtk.vtkCellPicker()
            picker.SetTolerance(Tolerances.PICKER_TOLERANCE)

            height = self.plotter.interactor.height()
            picker.Pick(x, height - y, 0, self.plotter.renderer)

            cell_id = picker.GetCellId()

            if cell_id != -1:
                pos = np.array(picker.GetPickPosition())
                normal = np.array(picker.GetPickNormal())
                picked_actor = picker.GetActor()

                # FIX: Identifiziere welcher Body TATSÄCHLICH gepickt wurde
                # Damit wird verhindert dass Faces von anderen Bodies selektiert werden
                picked_body_id = self._resolve_body_id_for_actor(picked_actor)

                # === METHODE 1: EXAKT via face_id cell_data ===
                # Wenn Body bekannt und Mesh face_id hat → direkte Lookup (keine Heuristik!)
                if picked_body_id is not None and hasattr(self, 'bodies'):
                    body_data = self.bodies.get(picked_body_id)
                    if body_data and 'mesh' in body_data:
                        mesh = body_data['mesh']
                        if mesh is not None and "face_id" in mesh.cell_data:
                            face_ids = mesh.cell_data["face_id"]
                            if 0 <= cell_id < len(face_ids):
                                ocp_face_id = int(face_ids[cell_id])
                                # Finde SelectionFace mit dieser OCP Face-ID
                                for face in self.detector.selection_faces:
                                    if (face.domain_type == "body_face" and
                                        face.owner_id == picked_body_id and
                                        getattr(face, 'ocp_face_id', None) == ocp_face_id):
                                        logger.debug(f"Pick EXAKT: cell_id={cell_id} → ocp_face_id={ocp_face_id} → face.id={face.id}")
                                        return face.id

                # === METHODE 2: FALLBACK - Heuristik (wenn keine face_id) ===
                # Sichtbare Body-IDs vorfiltern
                visible_bodies = None
                if hasattr(self, 'bodies') and hasattr(self, 'is_body_visible'):
                    visible_bodies = {bid for bid in self.bodies if self.is_body_visible(bid)}

                best_face = None
                best_dist = float('inf')

                for face in self.detector.selection_faces:
                    if face.domain_type != "body_face":
                        continue
                    if visible_bodies is not None and face.owner_id not in visible_bodies:
                        continue
                    # FIX: Nur Faces vom gepickten Body berücksichtigen!
                    if picked_body_id is not None and face.owner_id != picked_body_id:
                        continue

                    # Pre-computed numpy arrays (keine Tuple→Array Konvertierung)
                    f_origin = face._np_origin
                    f_normal = face._np_normal

                    dist_plane = abs(np.dot(pos - f_origin, f_normal))
                    dot_normal = np.dot(normal, f_normal)

                    # FIX: abs(dot_normal) erlaubt invertierte Normalen (VTK gibt manchmal invertierte zurück)
                    if dist_plane < 1.0 and abs(dot_normal) > 0.8:
                        dist_center = np.linalg.norm(pos - f_origin)
                        if dist_center < best_dist:
                            best_dist = dist_center
                            best_face = face

                if best_face:
                    logger.debug(f"Pick HEURISTIK: face.id={best_face.id}")
                    return best_face.id

        # --- 2. SKETCH FACES (Analytisches Picking) ---
        ray_origin, ray_dir = self.get_ray_from_click(x, y)
        ray_start = np.array(ray_origin)
        
        hits = []
        for face in self.detector.selection_faces:
            if face.domain_type.startswith("sketch") and face.domain_type in selection_filter:
                hit = self.detector._intersect_ray_plane(ray_origin, ray_dir, face.plane_origin, face.plane_normal)
                if hit is None:
                    continue
                
                proj_x, proj_y = self.detector._project_point_2d(hit, face.plane_origin, face.plane_x, face.plane_y)
                
                minx, miny, maxx, maxy = face.shapely_poly.bounds
                if not (minx <= proj_x <= maxx and miny <= proj_y <= maxy):
                    continue
                    
                if HAS_SHAPELY and face.shapely_poly.contains(Point(proj_x, proj_y)):
                    dist = np.linalg.norm(np.array(hit) - ray_start)
                    hits.append((face.pick_priority, dist, face.id))

        if hits:
            hits.sort(key=lambda h: (-h[0], h[1]))
            return hits[0][2]

        return -1

    def get_ray_from_click(self, x, y):
        """Berechnet einen 3D-Ray aus Bildschirmkoordinaten"""
        renderer = self.plotter.renderer
        height = self.plotter.interactor.height()
        
        # Near point (on near clipping plane)
        renderer.SetDisplayPoint(x, height - y, 0.0)
        renderer.DisplayToWorld()
        near = renderer.GetWorldPoint()
        
        # Far point (on far clipping plane)
        renderer.SetDisplayPoint(x, height - y, 1.0)
        renderer.DisplayToWorld()
        far = renderer.GetWorldPoint()
        
        # Convert to 3D coordinates
        near_pt = np.array(near[:3]) / near[3] if near[3] != 0 else np.array(near[:3])
        far_pt = np.array(far[:3]) / far[3] if far[3] != 0 else np.array(far[:3])
        
        direction = far_pt - near_pt
        direction = direction / np.linalg.norm(direction)
        
        return tuple(near_pt), tuple(direction)

    def _hover_body_face(self, x, y):
        """Hebt Body-Flächen beim Hover hervor"""
        if not self.bodies or not HAS_VTK:
            return
            
        try:
            cell_picker = vtk.vtkCellPicker()
            cell_picker.SetTolerance(Tolerances.PICKER_TOLERANCE_COARSE)
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

                body_id = self._resolve_body_id_for_actor(actor)

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

    def _pick_body_face(self, x, y):
        """Versucht eine planare Fläche auf einem 3D-Körper zu finden"""
        if not HAS_VTK:
            return False
            
        cell_picker = vtk.vtkCellPicker()
        cell_picker.SetTolerance(Tolerances.PICKER_TOLERANCE)
        cell_picker.Pick(x, self.plotter.interactor.height() - y, 0, self.plotter.renderer)
        
        if cell_picker.GetCellId() != -1:
            # Find body ID
            actor = cell_picker.GetActor()
            body_id = self._resolve_body_id_for_actor(actor)
            
            if body_id is not None:
                normal = list(cell_picker.GetPickNormal())
                pos = cell_picker.GetPickPosition()
                
                # Bereinigung: Fast-Nullen und Fast-Einsen glätten
                for i in range(3):
                    if abs(normal[i]) < 0.001:
                        normal[i] = 0.0
                    if abs(normal[i] - 1.0) < 0.001:
                        normal[i] = 1.0
                    if abs(normal[i] + 1.0) < 0.001:
                        normal[i] = -1.0
                
                self._last_picked_face_center = tuple(pos)
                self._last_picked_face_normal = tuple(normal)
                self.custom_plane_clicked.emit(tuple(pos), tuple(normal))
                self._draw_plane_hover_highlight(pos, normal)
                return True
        return False

    def _handle_selection_click(self, x, y, is_multi):
        """
        Verarbeitet einen Klick im Selektionsmodus.

        TNP v4.0: Erzeugt SelectionItems mit ShapeID-Referenzen
        statt nur Integer-IDs zu speichern.

        TNP v5.0: Captured SelectionContext für Semantic Matching
        """
        # Picker mit aktivem Filter aufrufen
        face_id = self.pick(x, y, selection_filter=self.active_selection_filter)

        if face_id != -1:
            # Face-Daten holen für TNP-Lookup
            face = next((f for f in self.detector.selection_faces if f.id == face_id), None)
            if face is None:
                return False

            # TNP v4.0: ShapeID für dieses Face suchen
            shape_uuid = self._get_shape_uuid_for_face(face)

            # Body-ID bestimmen
            body_id = face.owner_id if hasattr(face, 'owner_id') else None
            domain_type = face.domain_type if hasattr(face, 'domain_type') else 'unknown'

            if is_multi:
                # Toggle selection
                is_selected = self.selection_manager.toggle_selection(
                    face_id=face_id,
                    body_id=body_id,
                    domain_type=domain_type,
                    shape_uuid=shape_uuid,
                )
                # Legacy-Set synchronisieren
                if is_selected:
                    self.selected_face_ids.add(face_id)
                else:
                    self.selected_face_ids.discard(face_id)
            else:
                # Single selection
                self.selection_manager.set_single_selection(
                    face_id=face_id,
                    body_id=body_id,
                    domain_type=domain_type,
                    shape_uuid=shape_uuid,
                )
                # Legacy-Set synchronisieren
                self.selected_face_ids.clear()
                self.selected_face_ids.add(face_id)

            # TNP v5.0: Capture SelectionContext
            # Get pick position from VTK picker
            pick_position = (0.0, 0.0, 0.0)
            if HAS_VTK and hasattr(self, 'plotter'):
                try:
                    picker = HAS_VTK and vtk.vtkCellPicker() if HAS_VTK else None
                    if picker:
                        height = self.plotter.interactor.height()
                        picker.Pick(x, height - y, 0, self.plotter.renderer)
                        pos = picker.GetPickPosition()
                        if pos and pos != (0, 0, 0):
                            pick_position = tuple(pos)

                    context = self._capture_selection_context(face_id, pick_position, x, y)
                    if context is not None:
                        self.store_selection_context(face_id, context)
                        logger.debug(f"[TNP v5.0] Captured context for face {face_id}: "
                                   f"point={pick_position}, view={context.view_direction}, "
                                   f"adjacent={len(context.adjacent_shapes)}")
                except Exception as e:
                    logger.debug(f"[TNP v5.0] Failed to capture selection context: {e}")

            # Cache drag direction und Face-Daten für die erste selektierte Fläche
            if self.selected_face_ids:
                first_id = next(iter(self.selected_face_ids))
                face = next((f for f in self.detector.selection_faces if f.id == first_id), None)
                if face:
                    self._cache_drag_direction_for_face_v2(face)
                    # Face-Daten für Offset Plane und andere Face-basierte Features
                    self._last_picked_face_center = face.plane_origin
                    self._last_picked_face_normal = face.plane_normal

            self._draw_selectable_faces_from_detector()
            self.face_selected.emit(face_id)
            return True

        return False

    def _get_shape_uuid_for_face(self, face) -> str:
        """
        TNP v4.0: Sucht die ShapeID.uuid für eine SelectionFace.

        Args:
            face: SelectionFace mit ocp_face_id Attribute

        Returns:
            ShapeID.uuid als String oder None
        """
        if not hasattr(self, 'document') or self.document is None:
            return None

        service = getattr(self.document, '_shape_naming_service', None)
        if service is None:
            return None

        # OCP Face ID aus SelectionFace
        ocp_face_id = getattr(face, 'ocp_face_id', None)
        if ocp_face_id is None:
            return None

        # ShapeID für diese Face suchen
        try:
            # Über Bodies iterieren um die richtige zu finden
            if hasattr(self, 'bodies'):
                body_data = self.bodies.get(face.owner_id)
                if body_data and 'body' in body_data:
                    body = body_data['body']
                    if hasattr(body, '_build123d_solid'):
                        solid = body._build123d_solid
                        # Face per Index holen
                        faces = list(solid.faces())
                        if 0 <= ocp_face_id < len(faces):
                            target_face = faces[ocp_face_id]
                            # ShapeID für diesen Face suchen
                            shape_id = service.find_shape_id_by_shape(target_face.wrapped)
                            if shape_id:
                                logger.debug(f"[TNP] Found ShapeID {shape_id.uuid[:8]}... for face {face.id}")
                                return shape_id.uuid
        except Exception as e:
            logger.debug(f"[TNP] ShapeID lookup failed: {e}")

        return None
