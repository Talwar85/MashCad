"""
MashCAD Sketch Operations Module
================================

Extracted from main_window.py (AR-005: Phase 2 Split).

This module contains sketch-related operations as a mixin class.
Maintains backward compatibility by being imported into MainWindow.

Usage:
    class MainWindow(SketchMixin, QMainWindow):
        pass
"""

from typing import TYPE_CHECKING, Optional, Tuple, List
import numpy as np
from loguru import logger

if TYPE_CHECKING:
    from sketcher import Sketch
    from modeling import Document


class SketchMixin:
    """
    Mixin class containing sketch-related operations for MainWindow.
    
    This class provides:
    - Sketch creation and plane selection
    - Offset plane creation workflow
    - Construction plane management
    - Sketch view alignment
    - Parametric rebuild scheduling
    
    All methods assume they are called within a MainWindow context
    and access MainWindow attributes via `self`.
    """
    
    # =========================================================================
    # Sketch Creation
    # =========================================================================
    
    def _new_sketch(self):
        """Start sketch creation by enabling plane selection mode."""
        from i18n import tr
        
        self.viewport_3d.set_plane_select_mode(True)
        logger.info(tr("Wähle Ebene: 1=XY, 2=XZ, 3=YZ oder Klick auf Fläche"))
        self.setFocus()
    
    def _on_plane_selected(self, plane):
        """Handle selection of a standard plane (XY, XZ, YZ)."""
        # DEFINITION: (Origin, Normal, X_Direction)
        plane_defs = {
            'xy': ((0, 0, 0), (0, 0, 1), (1, 0, 0)),
            'xz': ((0, 0, 0), (0, 1, 0), (1, 0, 0)),
            'yz': ((0, 0, 0), (1, 0, 0), (0, 1, 0))
        }
        default = ((0, 0, 0), (0, 0, 1), (1, 0, 0))
        origin, normal, x_dir = plane_defs.get(plane, default)

        # Offset Plane Workflow: Phase 2 starten
        if self._offset_plane_pending:
            self._start_offset_plane_drag(origin, normal)
            return

        self.viewport_3d.set_plane_select_mode(False)
        self._create_sketch_at(origin, normal, x_dir_override=x_dir)
    
    def _on_custom_plane_selected(self, origin, normal):
        """Handle selection of a custom plane (face pick)."""
        # Offset Plane Workflow: Face-Pick → Phase 2 starten
        if self._offset_plane_pending:
            self._start_offset_plane_drag(origin, normal)
            return

        self.viewport_3d.set_plane_select_mode(False)
        x_dir = getattr(self.viewport_3d, '_last_picked_x_dir', None)
        self._create_sketch_at(origin, normal, x_dir)
    
    def _on_browser_plane_selected(self, plane):
        """Handle plane selection from browser."""
        self._on_plane_selected(plane)
    
    def _create_sketch_at(self, origin, normal, x_dir_override=None):
        """Create a new sketch at the specified plane."""
        s = self.document.new_sketch(f"Sketch{len(self.document.sketches)+1}")

        # Berechne Achsen
        if x_dir_override:
            # PERFEKT: Wir haben eine stabile Achse vom Detector
            x_dir = x_dir_override
            # Y berechnen (Kreuzprodukt)
            n_vec = np.array(normal, dtype=np.float64)
            n_vec = n_vec / np.linalg.norm(n_vec) if np.linalg.norm(n_vec) > 0 else np.array([0, 0, 1])
            x_vec = np.array(x_dir, dtype=np.float64)
            x_vec = x_vec / np.linalg.norm(x_vec) if np.linalg.norm(x_vec) > 0 else np.array([1, 0, 0])
            y_vec = np.cross(n_vec, x_vec)
            
            # FIX: Handle parallel vectors - cross product yields zero vector
            y_vec_norm = np.linalg.norm(y_vec)
            if y_vec_norm < 1e-10:
                # x_dir is parallel to normal - recalculate both axes properly
                if abs(n_vec[2]) < 0.9:
                    x_vec = np.cross(n_vec, [0.0, 0.0, 1.0])
                else:
                    x_vec = np.cross(n_vec, [1.0, 0.0, 0.0])
                x_vec = x_vec / np.linalg.norm(x_vec)
                y_vec = np.cross(n_vec, x_vec)
                y_vec = y_vec / np.linalg.norm(y_vec)
                x_dir = tuple(x_vec)
            
            y_dir = tuple(y_vec)
        else:
            # Fallback: Raten (das was bisher Probleme machte)
            x_dir, y_dir = self._calculate_plane_axes(normal)

        # Speichere ALLES im Sketch
        s.plane_origin = origin
        s.plane_normal = normal
        s.plane_x_dir = x_dir  # <--- Das ist der Schlüssel zum Erfolg
        s.plane_y_dir = y_dir

        # ✅ FIX: Speichere Parent-Body für korrektes Targeting
        if hasattr(self.viewport_3d, '_last_picked_body_id') and self.viewport_3d._last_picked_body_id:
            s.parent_body_id = self.viewport_3d._last_picked_body_id
            logger.info(f"✅ Sketch erstellt auf Body: {s.parent_body_id}")
            # Reset after use
            self.viewport_3d._last_picked_body_id = None
        
        # W16 Paket D: Aktiven Sketch setzen (Controller + MainWindow)
        self.active_sketch = s
        if hasattr(self, 'sketch_controller'):
            self.sketch_controller._active_sketch = s
        
        self.sketch_editor.sketch = s
        
        # Bodies als Referenz übergeben (für Snapping auf Kanten)
        self._set_sketch_body_references(origin, normal)
        
        self._set_mode("sketch")
        self.browser.refresh()
    
    def _set_sketch_body_references(self, origin, normal, x_dir_override=None):
        """
        Sammelt Body-Daten und übergibt sie an den SketchEditor.
        FIX: Nutzt set_reference_bodies statt set_background_geometry.
        """
        bodies_data = []
        
        # Alle sichtbaren Körper durchgehen
        for bid, body in self.viewport_3d.bodies.items():
            if not self.viewport_3d.is_body_visible(bid):
                continue
            
            # Mesh holen (PyVista PolyData)
            mesh = self.viewport_3d.get_body_mesh(bid)
            
            if mesh is not None:
                # Farbe holen (oder Default)
                color = body.get('color', (0.6, 0.6, 0.8))
                
                bodies_data.append({
                    'mesh': mesh,
                    'color': color
                })
        
        # WICHTIG: Achsen berechnen, falls nicht übergeben
        if x_dir_override is None:
            x_dir_override, _ = self._calculate_plane_axes(normal)

        # Übergebe an SketchEditor (mit der korrekten Methode!)
        if hasattr(self.sketch_editor, 'set_reference_bodies'):
            self.sketch_editor.set_reference_bodies(
                bodies_data,
                normal,
                origin,
                plane_x=x_dir_override  # Das verhindert die Rotation!
            )

            # Automatische Ansicht-Ausrichtung basierend auf 3D-Kamera
            self._auto_align_sketch_view(normal, x_dir_override)
    
    # =========================================================================
    # Offset Plane Workflow
    # =========================================================================
    
    def _start_offset_plane(self):
        """Startet den interaktiven Offset-Plane-Workflow (Fusion-Style)."""
        from i18n import tr
        
        self._offset_plane_pending = True
        self.viewport_3d.set_plane_select_mode(True)
        self.statusBar().showMessage(tr("Wähle Basisebene: Klick auf Standardebene oder Körperfläche"))
        logger.info("Offset Plane: Wähle Basisebene...")

    def _start_offset_plane_drag(self, origin, normal):
        """Phase 2: Offset einstellen nach Basis-Auswahl."""
        from i18n import tr
        
        self._offset_plane_pending = False
        self.viewport_3d.set_plane_select_mode(False)
        self.viewport_3d.set_offset_plane_mode(True)
        self.viewport_3d.set_offset_plane_base(
            np.array(origin, dtype=float),
            np.array(normal, dtype=float)
        )
        self.offset_plane_panel.reset()
        self.offset_plane_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage(tr("Offset einstellen: Mausdrag oder Zahleneingabe, Enter = bestätigen"))

    def _on_offset_plane_value_changed(self, offset):
        """Panel-Wert geändert → Preview aktualisieren."""
        if self.viewport_3d.offset_plane_mode:
            self.viewport_3d.update_offset_plane_preview(offset)

    def _on_offset_plane_drag(self, offset):
        """Viewport-Drag → Panel-Wert synchronisieren."""
        self.offset_plane_panel.set_offset(offset)

    def _on_offset_plane_confirmed(self):
        """Offset Plane bestätigen und erstellen."""
        from i18n import tr
        from modeling import ConstructionPlane
        
        offset = self.offset_plane_panel.get_offset()
        name = self.offset_plane_panel.get_name()
        origin = self.viewport_3d._offset_plane_base_origin
        normal = self.viewport_3d._offset_plane_base_normal

        if origin is None or normal is None:
            logger.error("Keine Basis für Offset Plane gesetzt")
            self._on_offset_plane_cancelled()
            return

        plane = ConstructionPlane.from_face(
            tuple(origin), tuple(normal), offset, name
        )
        self.document.planes.append(plane)

        self.viewport_3d.set_offset_plane_mode(False)
        self.offset_plane_panel.hide()
        self.browser.refresh()
        self._render_construction_planes()
        self.statusBar().showMessage(f"Plane '{plane.name}' erstellt")
        logger.success(f"Offset Plane erstellt: {plane.name}")

    def _on_offset_plane_cancelled(self):
        """Offset Plane abbrechen."""
        from i18n import tr
        
        self._offset_plane_pending = False
        self.viewport_3d.set_offset_plane_mode(False)
        self.viewport_3d.set_plane_select_mode(False)
        self.offset_plane_panel.hide()
        self.statusBar().showMessage(tr("Versatzebene abgebrochen"))
    
    # =========================================================================
    # Construction Planes
    # =========================================================================
    
    def _render_construction_planes(self):
        """Rendert alle Konstruktionsebenen im Viewport."""
        if hasattr(self, 'viewport_3d') and hasattr(self.document, 'planes'):
            self.viewport_3d.render_construction_planes(self.document.planes)

    def _on_construction_plane_vis_changed(self, plane_id, visible):
        """Browser hat Plane-Sichtbarkeit geändert."""
        if hasattr(self, 'viewport_3d'):
            self.viewport_3d.set_construction_plane_visibility(plane_id, visible)
            self._render_construction_planes()

    def _on_construction_plane_selected(self, cp):
        """Create sketch on a construction plane when clicked in browser."""
        self._create_sketch_at(cp.origin, cp.normal, x_dir_override=cp.x_dir)
    
    # =========================================================================
    # Sketch View Management
    # =========================================================================
    
    def _finish_sketch(self):
        """Beendet den Sketch-Modus und räumt auf."""
        # Body-Referenzen im SketchEditor löschen (Ghost Bodies entfernen)
        if hasattr(self.sketch_editor, 'set_reference_bodies'):
            self.sketch_editor.set_reference_bodies([], (0, 0, 1), (0, 0, 0))

        # DOF-Anzeige ausblenden
        self.mashcad_status_bar.set_dof(0, visible=False)

        # W16 Paket D: Delegation an SketchController
        if hasattr(self, 'sketch_controller'):
            self.sketch_controller.finish_sketch()
        else:
            # Fallback
            self.active_sketch = None
            self._set_mode("3d")
            self.browser.refresh()
            self._trigger_viewport_update()

    def _rotate_sketch_view(self):
        """Rotiert die Sketch-Ansicht um 90°."""
        if hasattr(self.sketch_editor, 'rotate_view'):
            self.sketch_editor.rotate_view()

    def _on_peek_3d(self, show_3d: bool):
        """
        Temporär 3D-Viewport zeigen während Space gedrückt (Peek-Modus).
        W16 Paket D: Delegiert an SketchController.
        """
        from i18n import tr
        
        if hasattr(self, 'sketch_controller'):
            self.sketch_controller.set_peek_3d(show_3d)
        else:
            # Fallback
            self._peek_3d_active = show_3d
            if show_3d:
                self.center_stack.setCurrentIndex(0)
                self.statusBar().showMessage(tr("3D-Vorschau (Space loslassen für Sketch)"), 0)
                self.grabKeyboard()
            else:
                self.center_stack.setCurrentIndex(1)
                self.sketch_editor.setFocus()
                self.statusBar().clearMessage()
                self.releaseKeyboard()

    def _auto_align_sketch_view(self, plane_normal, plane_x):
        """
        Richtet die Sketch-Ansicht automatisch an der 3D-Kamera aus.
        Nutzt die Screen-Projektion der Sketch-Achsen (wie die 3D-Achsen).
        """
        try:
            # Sketch-Ebenen-Achsen in 3D
            n = np.array(plane_normal, dtype=np.float64)
            n = n / np.linalg.norm(n)
            x_dir = np.array(plane_x, dtype=np.float64)
            x_dir = x_dir / np.linalg.norm(x_dir)
            y_dir = np.cross(n, x_dir)
            y_dir = y_dir / np.linalg.norm(y_dir)

            # VTK World-to-Display Projektion
            ren = self.viewport_3d.plotter.renderer

            def world_to_screen(pt):
                """Konvertiert 3D Welt-Koordinate zu 2D Screen-Koordinate."""
                ren.SetWorldPoint(pt[0], pt[1], pt[2], 1.0)
                ren.WorldToDisplay()
                d_pt = ren.GetDisplayPoint()
                return np.array([d_pt[0], d_pt[1]])

            origin_screen = world_to_screen([0, 0, 0])
            x_end_screen = world_to_screen(x_dir * 100)
            y_end_screen = world_to_screen(y_dir * 100)

            # Screen-Vektoren (Y nach oben = positive Richtung)
            # VTK view coords: (0,0) = unten links, Y wächst nach oben
            sx = np.array([x_end_screen[0] - origin_screen[0], x_end_screen[1] - origin_screen[1]])
            sy = np.array([y_end_screen[0] - origin_screen[0], y_end_screen[1] - origin_screen[1]])

            # Normalisiere
            sx_len = np.linalg.norm(sx)
            sy_len = np.linalg.norm(sy)
            if sx_len < 0.001 or sy_len < 0.001:
                logger.debug("[Auto-Align] Achsen zu kurz auf Screen")
                self.sketch_editor.view_rotation = 0
                return
            sx = sx / sx_len
            sy = sy / sy_len

            # Screen "oben" ist (0, 1)
            screen_up = np.array([0.0, 1.0])

            # Winkel zwischen Sketch-Y und Screen-Oben
            dot = np.dot(sy, screen_up)
            dot = np.clip(dot, -1.0, 1.0)
            angle_rad = np.arccos(dot)

            # Kreuzprodukt für Vorzeichen
            cross = sx[0] * screen_up[1] - sx[1] * screen_up[0]
            if cross < 0:
                angle_rad = -angle_rad

            angle_deg = np.degrees(angle_rad)

            # Auf 90° runden (für saubere Ausrichtung)
            rounded_angle = round(angle_deg / 90) * 90

            logger.debug(f"[Auto-Align] Winkel={angle_deg:.1f}°, gerundet={rounded_angle}°")
            self.sketch_editor.view_rotation = rounded_angle

        except Exception as e:
            logger.debug(f"[Auto-Align] Fehler: {e}")
            self.sketch_editor.view_rotation = 0
    
    # =========================================================================
    # Parametric Rebuild
    # =========================================================================
    
    def _on_sketch_changed_refresh_viewport(self):
        """
        Aktualisiert Sketch-Wireframes im 3D-Viewport nach Sketch-Änderungen.
        KRITISCH: Triggert auch Rebuild von Bodies die von diesem Sketch abhängen!
        """
        self.viewport_3d.set_sketches(self.browser.get_visible_sketches())

        # Parametric CAD: Update bodies that depend on this sketch (DEBOUNCED)
        if self.mode == "sketch" and hasattr(self.sketch_editor, 'sketch'):
            self._schedule_parametric_rebuild()

    def _schedule_parametric_rebuild(self):
        """
        Debounced Rebuild für parametrische Updates.
        Wartet 300ms nach der letzten Sketch-Änderung bevor Rebuild getriggert wird.
        """
        if not hasattr(self, '_parametric_rebuild_timer'):
            from PySide6.QtCore import QTimer
            self._parametric_rebuild_timer = QTimer()
            self._parametric_rebuild_timer.setSingleShot(True)
            self._parametric_rebuild_timer.timeout.connect(self._do_parametric_rebuild)

        # Timer neu starten (Debounce)
        self._parametric_rebuild_timer.stop()
        self._parametric_rebuild_timer.start(300)  # 300ms Debounce

    def _do_parametric_rebuild(self):
        """Führt den tatsächlichen parametrischen Rebuild aus."""
        if self.mode == "sketch" and hasattr(self.sketch_editor, 'sketch'):
            self._update_bodies_depending_on_sketch(self.sketch_editor.sketch)

    def _compute_profile_hash(self, feature, sketch) -> str:
        """
        Berechnet einen Hash der für ein Feature relevanten Profile.
        
        Dieser Hash basiert auf:
        - Den Centroids der vom feature.profile_selector referenzierten Profile
        - Den Geometrie-Daten (exterior coords) dieser Profile
        
        WICHTIG: Die Profile werden nach Centroid sortiert, damit die Reihenfolge
        stabil ist und nicht von der internen Sortierung des Sketch-Solvers abhängt.
        
        Args:
            feature: Das Feature (ExtrudeFeature oder RevolveFeature)
            sketch: Der Sketch mit den closed_profiles
            
        Returns:
            Ein Hash-String der relevanten Profile. Leerer String wenn keine Profile gefunden.
        """
        import hashlib
        
        profile_selector = getattr(feature, 'profile_selector', [])
        sketch_profiles = getattr(sketch, 'closed_profiles', [])
        
        if not profile_selector or not sketch_profiles:
            return ""
        
        # Finde die Profile, die zum Selektor passen (ähnlich wie _filter_profiles_by_selector)
        matched_profiles = []
        used_indices = set()
        tolerance = 5.0
        
        for sel_cx, sel_cy in profile_selector:
            best_match_idx = None
            best_match_dist = float('inf')
            
            for i, poly in enumerate(sketch_profiles):
                if i in used_indices:
                    continue
                try:
                    centroid = poly.centroid
                    dist = ((centroid.x - sel_cx) ** 2 + (centroid.y - sel_cy) ** 2) ** 0.5
                    if dist < tolerance and dist < best_match_dist:
                        best_match_dist = dist
                        best_match_idx = i
                except Exception as e:
                    logger.debug(f"[main_window] Profil-Matching Fehler: {e}")
                    continue
            
            if best_match_idx is not None:
                used_indices.add(best_match_idx)
                matched_profiles.append(sketch_profiles[best_match_idx])
        
        if not matched_profiles:
            return ""
        
        # WICHTIG: Sortiere Profile nach Centroid für stabile Reihenfolge
        # Die interne Sortierung des Sketch-Solvers kann sich ändern!
        def profile_sort_key(poly):
            try:
                c = poly.centroid
                return (round(c.x, 6), round(c.y, 6))
            except Exception as e:
                logger.debug(f"[main_window] Fehler beim Profil-Sortieren: {e}")
                return (0.0, 0.0)
        
        matched_profiles = sorted(matched_profiles, key=profile_sort_key)
        
        # Erstelle einen Hash basierend auf den Geometrie-Daten der gematchten Profile
        hasher = hashlib.md5()
        for poly in matched_profiles:
            # Centroid
            c = poly.centroid
            hasher.update(f"centroid:{c.x:.6f},{c.y:.6f};".encode())
            # Area
            hasher.update(f"area:{poly.area:.6f};".encode())
            # Exterior coords (vereinfacht)
            coords = list(poly.exterior.coords)
            for coord in coords[:10]:  # Max 10 Punkte pro Profil (Performance)
                hasher.update(f"{coord[0]:.4f},{coord[1]:.4f};".encode())
        
        return hasher.hexdigest()
    
    def _update_bodies_depending_on_sketch(self, sketch):
        """
        CAD Kernel First: Findet alle Bodies mit Features die von diesem Sketch
        abhängen und triggert Rebuild.
        
        OPTIMIERT: Prüft ob sich die tatsächlich verwendeten Profile geändert haben.
        Wenn nur neue Profile hinzugefügt wurden (ohne die verwendeten zu ändern),
        wird kein Rebuild durchgeführt.

        WICHTIG: Keine precalculated_polys Updates mehr!
        Profile werden beim Rebuild direkt aus dem Sketch abgeleitet.

        Args:
            sketch: Der geänderte Sketch
        """
        if not sketch:
            return

        from modeling import ExtrudeFeature, RevolveFeature

        sketch_id = getattr(sketch, 'id', None)
        bodies_to_rebuild = []
        skipped_bodies = []

        for body in self.document.bodies:
            needs_rebuild = False
            body_uses_sketch = False
            
            for feature in body.features:
                # ExtrudeFeature oder RevolveFeature mit diesem Sketch?
                if isinstance(feature, (ExtrudeFeature, RevolveFeature)):
                    # Vergleiche sowohl per Objekt-Identität ALS AUCH per ID (für geladene Projekte)
                    feature_sketch = feature.sketch
                    is_same_sketch = (
                        feature_sketch is sketch or
                        (feature_sketch and sketch_id and getattr(feature_sketch, 'id', None) == sketch_id)
                    )

                    if is_same_sketch:
                        body_uses_sketch = True
                        # OPTIMIERUNG: Prüfe ob sich die verwendeten Profile wirklich geändert haben
                        current_hash = self._compute_profile_hash(feature, sketch)
                        stored_hash = getattr(feature, '_profile_hash', None)
                        
                        if current_hash != stored_hash:
                            # Profile haben sich geändert oder Hash wurde noch nie gesetzt
                            feature._profile_hash = current_hash
                            needs_rebuild = True
                            # Nur loggen wenn sich wirklich etwas geändert hat (nicht beim ersten Mal)
                            if stored_hash is not None:
                                logger.debug(f"[PARAMETRIC] Profile changed for '{body.name}'/{feature.name}")
                        # else: Profile unverändert - kein Logging (zu chatty)
            
            if needs_rebuild and body not in bodies_to_rebuild:
                bodies_to_rebuild.append(body)
            elif body_uses_sketch and not needs_rebuild:
                skipped_bodies.append(body.name)

        # Rebuild alle betroffenen Bodies
        # CAD KERNEL FIRST: Profile werden beim Rebuild aus dem Sketch abgeleitet!
        if bodies_to_rebuild:
            logger.info(f"[PARAMETRIC] Rebuilding {len(bodies_to_rebuild)} body/bodies, skipped {len(skipped_bodies)} (profiles unchanged)")

        for body in bodies_to_rebuild:
            try:
                from modeling.cad_tessellator import CADTessellator
                CADTessellator.notify_body_changed()
                body._rebuild()
                self._update_body_from_build123d(body, body._build123d_solid)
                logger.info(f"[PARAMETRIC] Rebuilt body '{body.name}' after sketch change")
            except Exception as e:
                logger.error(f"[PARAMETRIC] Rebuild failed for '{body.name}': {e}")
    
    def _on_solver_dof_updated(self, success: bool, message: str, dof: float):
        """
        Wird aufgerufen wenn der Sketcher-Solver fertig ist.
        Aktualisiert die DOF-Anzeige in der Statusleiste.
        """
        # DOF in Integer konvertieren (kommt als float vom Signal)
        dof_int = int(dof) if dof >= 0 else -1

        # StatusBar aktualisieren (nur im Sketch-Modus sichtbar)
        is_sketch_mode = self.mode == "sketch"
        self.mashcad_status_bar.set_dof(dof_int, visible=is_sketch_mode)
    
    # =========================================================================
    # Sketch Tool Selection
    # =========================================================================
    
    def _on_sketch_tool_selected(self, tool_name: str):
        """Verarbeitet Tool-Auswahl aus dem Sketch-ToolPanel"""
        from gui.sketch_tools import SketchTool
        
        tool_map = {
            # Draw tools
            'line': SketchTool.LINE,
            'rectangle': SketchTool.RECTANGLE,
            'circle': SketchTool.CIRCLE,
            'ellipse': SketchTool.ELLIPSE,
            'polygon': SketchTool.POLYGON,
            'arc_3point': SketchTool.ARC_3POINT,
            'slot': SketchTool.SLOT,
            'spline': SketchTool.SPLINE,
            'point': SketchTool.POINT,
            'project': SketchTool.PROJECT,
            # Shapes
            'gear': SketchTool.GEAR,
            'star': SketchTool.STAR,
            'nut': SketchTool.NUT,
            'text': SketchTool.TEXT,
            # Modify tools
            'select': SketchTool.SELECT,
            'move': SketchTool.MOVE,
            'copy': SketchTool.COPY,
            'rotate': SketchTool.ROTATE,
            'mirror': SketchTool.MIRROR,
            'scale': SketchTool.SCALE,
            'trim': SketchTool.TRIM,
            'offset': SketchTool.OFFSET,
            'fillet_2d': SketchTool.FILLET_2D,
            'chamfer_2d': SketchTool.CHAMFER_2D,
            # Patterns
            'pattern_linear': SketchTool.PATTERN_LINEAR,
            'pattern_circular': SketchTool.PATTERN_CIRCULAR,
            # Constraints
            'dimension': SketchTool.DIMENSION,
            'dimension_angle': SketchTool.DIMENSION_ANGLE,
            'horizontal': SketchTool.HORIZONTAL,
            'vertical': SketchTool.VERTICAL,
            'parallel': SketchTool.PARALLEL,
            'perpendicular': SketchTool.PERPENDICULAR,
            'equal': SketchTool.EQUAL,
            'concentric': SketchTool.CONCENTRIC,
            'tangent': SketchTool.TANGENT,
        }
        if tool_name in tool_map:
            self.sketch_editor.set_tool(tool_map[tool_name])
        else:
            logger.warning(f"Unknown sketch tool: {tool_name}")
