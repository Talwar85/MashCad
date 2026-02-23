"""
MashCAD Feature Operations Module
=================================

Extracted from main_window.py (AR-005: Phase 2 Split).

This module contains feature-related operations as a mixin class.
Maintains backward compatibility by being imported into MainWindow.

Usage:
    class MainWindow(FeatureMixin, QMainWindow):
        pass
"""

from typing import TYPE_CHECKING, Optional, List, Dict, Any, Tuple
import numpy as np
from loguru import logger

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

if TYPE_CHECKING:
    from modeling import Body, Feature, ExtrudeFeature, FilletFeature, ChamferFeature
    from sketcher import Sketch


class FeatureMixin:
    """
    Mixin class containing feature-related operations for MainWindow.
    
    This class provides:
    - Extrude dialog and operations
    - Fillet/Chamfer operations
    - Shell operations
    - Revolve operations
    - Feature editing and deletion
    - Feature tree operations
    
    All methods assume they are called within a MainWindow context
    and access MainWindow attributes via `self`.
    """
    
    # =========================================================================
    # Extrude Operations
    # =========================================================================
    
    def _extrude_dialog(self):
        """Startet den Extrude-Modus."""
        from i18n import tr
        
        # 1. Detector leeren und füllen
        self._update_detector()

        if not self.viewport_3d.detector.selection_faces:
            logger.error("Keine geschlossenen Flächen gefunden!", 3000)
            return

        # Transform-Panel verstecken
        self._hide_transform_ui()

        # 2. Modus aktivieren
        self.viewport_3d.set_extrude_mode(True)
        self.viewport_3d.set_selection_mode("face")

        # 3. Panel anzeigen UND nach vorne bringen
        self.extrude_panel.reset()
        self.extrude_panel.setVisible(True)
        self.extrude_panel.show()
        
        # FIX PROBLEM 1: Panel Positionierung verzögern!
        # Qt braucht ein paar Millisekunden, um die Breite des Panels zu berechnen.
        # Ohne Timer ist width() oft 0 oder falsch, daher landet es oben.
        QTimer.singleShot(10, self._position_extrude_panel)
        
        logger.info("Fläche wählen und ziehen. Bestätigen mit Enter oder Rechtsklick.")

    def _on_viewport_height_changed(self, h):
        """Wird aufgerufen wenn sich die Höhe durch Maus-Drag ändert"""
        # Update das Input-Panel mit dem aktuellen Wert
        self.extrude_panel.set_height(h)
        
        # Dynamische Operation-Anpassung für Body-Faces
        self._update_operation_from_height(h)
    
    def _update_operation_from_height(self, height):
        """
        Passt die Operation dynamisch an die Extrusionsrichtung an.
        - Positive Höhe (weg von Oberfläche) = Join
        - Negative Höhe (in Oberfläche) = Cut
        """
        # Nur wenn im Extrude-Modus und Faces ausgewählt
        if not self.viewport_3d.extrude_mode:
            return
            
        if not self.viewport_3d.selected_face_ids:
            return
        
        # Prüfe ob es sich um Body-Faces handelt
        face_id = next(iter(self.viewport_3d.selected_face_ids))
        face = next((f for f in self.viewport_3d.detector.selection_faces if f.id == face_id), None)
        
        if not face:
            return
            
        # Nur für Body-Faces automatisch anpassen
        if face.domain_type.startswith('body'):
            # Body-Face: Positive Höhe = raus aus Body = Join
            #           Negative Höhe = in Body hinein = Cut
            if height >= 0:
                suggested = "Join"
            else:
                suggested = "Cut"
            
            current = self.extrude_panel.get_operation()
            if current != suggested and current in ["Join", "Cut"]:
                self.extrude_panel.set_suggested_operation(suggested)
    
    def _on_extrude_panel_height_changed(self, height):
        """Live-Vorschau wenn Wert im Panel geändert wird"""
        if hasattr(self.viewport_3d, 'show_extrude_preview'):
            operation = self.extrude_panel.get_operation()
            self.viewport_3d.extrude_operation = operation  # Sync
            self.viewport_3d.show_extrude_preview(height, operation)
    
    def _on_extrude_operation_changed(self, operation):
        """Wird aufgerufen wenn die Operation im Panel geändert wird"""
        # Operation im Viewport speichern für Drag-Farbe
        self.viewport_3d.extrude_operation = operation
        
        height = self.extrude_panel.get_height()
        if hasattr(self.viewport_3d, 'show_extrude_preview'):
            self.viewport_3d.show_extrude_preview(height, operation)
    
    def _on_to_face_requested(self):
        """User hat 'To Face' im Panel geklickt — Ziel-Pick aktivieren."""
        if not self.viewport_3d.extrude_mode:
            return
        self.viewport_3d._to_face_picking = True
        self.viewport_3d.setCursor(Qt.CrossCursor)
        self.statusBar().showMessage("Zielfläche auswählen...", 0)

    def _on_target_face_selected(self, target_face_id):
        """Ziel-Face für 'Extrude to Face' wurde gepickt."""
        height = self.viewport_3d.calculate_to_face_height(target_face_id)
        if abs(height) < 0.001:
            self.statusBar().showMessage("Zielfläche liegt auf gleicher Ebene", 3000)
            self.extrude_panel.set_to_face_mode(False)
            return

        self.extrude_panel.set_to_face_height(height)
        operation = self.extrude_panel.get_operation()
        self.viewport_3d.show_extrude_preview(height, operation)
        self.statusBar().showMessage(f"Extrude bis Fläche: {height:.2f} mm", 3000)

    def _on_face_selected_for_extrude(self, face_id):
        """
        Automatische Operation-Erkennung wenn eine Fläche ausgewählt wird.
        Auch für Shell-Mode verwendet.
        """
        # Shell-Mode hat Priorität (Phase 6)
        if getattr(self, '_shell_mode', False):
            self._on_face_selected_for_shell(face_id)
            return

        # Sweep-Profil-Phase (Phase 6)
        if getattr(self, '_sweep_mode', False) and getattr(self, '_sweep_phase', None) == 'profile':
            self._on_face_selected_for_sweep(face_id)
            return

        # Loft-Mode (Phase 6)
        if getattr(self, '_loft_mode', False):
            self._on_face_selected_for_loft(face_id)
            return

        # Revolve-Mode: Face-Pick → Preview anzeigen
        if self.viewport_3d.revolve_mode:
            self._on_face_selected_for_revolve(face_id)
            return

        if not self.viewport_3d.extrude_mode:
            return

        # Height zurücksetzen bei Face-Wechsel (verhindert Akkumulation)
        self.extrude_panel.height_input.blockSignals(True)
        self.extrude_panel._height = 0.0
        self.extrude_panel.height_input.setValue(0.0)
        self.extrude_panel.height_input.blockSignals(False)

        # Finde die selektierte Fläche
        face = next((f for f in self.viewport_3d.detector.selection_faces if f.id == face_id), None)
        if not face:
            return

        # Body-Face: Start mit "Join" (positive Extrusion = Material hinzufügen)
        # Die dynamische Anpassung erfolgt in _update_operation_from_height
        if face.domain_type.startswith('body'):
            self.extrude_panel.set_suggested_operation("Join")
            return

        # Sketch-Face: Prüfe ob auf einem Body
        if face.domain_type.startswith('sketch'):
            suggested_op = self._detect_extrude_operation(face)
            self.extrude_panel.set_suggested_operation(suggested_op)
    
    def _detect_extrude_operation(self, sketch_face) -> str:
        """
        Erkennt automatisch welche Operation sinnvoll ist.
        Returns: "New Body", "Join", oder "Cut"
        """
        # Wenn keine Bodies existieren -> New Body
        if not self.document.bodies:
            return "New Body"
        
        # Hole die Ebene der Sketch-Fläche
        face_origin = np.array(sketch_face.plane_origin)
        face_normal = np.array(sketch_face.plane_normal)
        
        # Prüfe für jeden sichtbaren Body ob die Fläche darauf liegt
        for body in self.document.bodies:
            if not self.viewport_3d.is_body_visible(body.id):
                continue
                
            mesh = self.viewport_3d.get_body_mesh(body.id)
            if mesh is None:
                continue
            
            # Prüfe ob ein Punkt der Sketch-Fläche nahe am Body ist
            # Nutze das Zentrum des Sketch-Polygons
            if sketch_face.shapely_poly:
                centroid = sketch_face.shapely_poly.centroid
                # Transformiere 2D Zentrum zu 3D
                ox, oy, oz = sketch_face.plane_origin
                ux, uy, uz = sketch_face.plane_x
                vx, vy, vz = sketch_face.plane_y
                center_3d = np.array([
                    ox + centroid.x * ux + centroid.y * vx,
                    oy + centroid.x * uy + centroid.y * vy,
                    oz + centroid.x * uz + centroid.y * vz
                ])
                
                # Finde nächsten Punkt auf dem Body
                try:
                    closest_idx = mesh.find_closest_point(center_3d)
                    closest_pt = mesh.points[closest_idx]
                    distance = np.linalg.norm(closest_pt - center_3d)
                    
                    # Wenn sehr nah (< 1mm), liegt die Fläche auf dem Body
                    if distance < 1.0:
                        # Ray-Cast in Normalenrichtung um zu prüfen ob wir "ins" Body zeigen
                        # Vereinfacht: Wenn nah, ist es wahrscheinlich Join oder Cut
                        # Positives Extrudieren = Join, Negatives = Cut
                        return "Join"  # Default: Join, User kann auf Cut wechseln
                        
                except Exception:
                    pass
        
        # Kein Body in der Nähe -> New Body
        return "New Body"
    
    def _on_extrude_confirmed(self):
        """Wird aufgerufen, wenn im Panel OK oder Enter gedrückt wurde"""
        height = self.extrude_panel.get_height()
        operation = self.extrude_panel.get_operation()
        
        # Wir übergeben None für die Indizes, da _on_extrusion_finished 
        # jetzt direkt den Detector im Viewport abfragt.
        self._on_extrusion_finished(None, height, operation)
    
    def _on_extrude_cancelled(self):
        """Extrude abgebrochen"""
        from i18n import tr
        
        self.viewport_3d.set_extrude_mode(False)
        self.extrude_panel.setVisible(False)
        if hasattr(self.viewport_3d, 'detector'):
            self.viewport_3d.detector.clear()
        self.viewport_3d.selected_face_ids.clear()
        self.viewport_3d.hover_face_id = -1
        self.viewport_3d._draw_selectable_faces_from_detector()
        # ASSEMBLY FIX: Viewport komplett neu rendern damit inactive Components
        # ihre korrekte Transparenz behalten (statt set_all_bodies_opacity(1.0))
        self._update_viewport_all_impl()
        logger.info(tr("Extrude abgebrochen"), 2000)
    
    def _on_toggle_bodies_visibility(self, hide: bool):
        """Legacy Handler - wird von bodies_visibility_state_changed ersetzt"""
        # Wird noch für Kompatibilität aufgerufen, eigentliche Logik in _on_bodies_visibility_state_changed
        pass

    def _on_bodies_visibility_state_changed(self, state: int):
        """
        3-Stufen Visibility Toggle:
        0 = Normal (mit Component-Transparenz)
        1 = X-Ray (20% transparent)
        2 = Versteckt (komplett unsichtbar)
        """
        if state == 0:  # Normal - respektiert inactive Component Transparenz
            # ASSEMBLY FIX: Viewport komplett neu rendern damit inactive Components
            # ihre korrekte Transparenz bekommen (nicht alle auf 1.0 setzen!)
            self._update_viewport_all_impl()
        elif state == 1:  # X-Ray
            self.viewport_3d.set_all_bodies_visible(True)
            self.viewport_3d.set_all_bodies_opacity(0.2)
        else:  # state == 2: Versteckt
            self.viewport_3d.set_all_bodies_visible(False)

        # Detector aktualisieren
        if self.viewport_3d.extrude_mode:
            self._update_detector()
            self.viewport_3d._draw_selectable_faces_from_detector()

    def _update_detector(self):
        """
        Lädt ALLE sichtbaren Geometrien in den Detector.
        """
        if not hasattr(self.viewport_3d, 'detector'):
            return
        
        self.viewport_3d.detector.clear()
        
        # A) Sketches verarbeiten
        visible_sketches = self.browser.get_visible_sketches()

        for sketch_info in visible_sketches:
            # Backward-compatible: 2- oder 3-Tupel
            if len(sketch_info) == 3:
                sketch, visible, is_inactive = sketch_info
            else:
                sketch, visible = sketch_info

            if visible:
                x_dir = getattr(sketch, 'plane_x_dir', None)
                y_dir = getattr(sketch, 'plane_y_dir', None)
                
                # Fallback Berechnung falls Achsen fehlen (bei alten Projekten)
                if x_dir is None:
                    x_dir, y_dir = self.viewport_3d._calculate_plane_axes(sketch.plane_normal)
                
                self.viewport_3d.detector.process_sketch(
                    sketch, 
                    sketch.plane_origin, 
                    sketch.plane_normal, 
                    x_dir,
                    y_dir 
                )
        
        # B) Body-Flächen verarbeiten (NUR sichtbare!)
        # Performance Optimization Phase 2.2: Übergebe extrude_mode für Dynamic Priority
        # WICHTIG: get_all_bodies() statt .bodies - letzteres nur für aktive Component!
        extrude_mode = getattr(self.viewport_3d, 'extrude_mode', False)
        for body in self.document.get_all_bodies():
            if self.viewport_3d.is_body_visible(body.id):
                mesh = self.viewport_3d.get_body_mesh(body.id)
                if mesh:
                    # FIX: B-Rep face_info übergeben für korrekte Normalen
                    face_info = getattr(body, 'face_info', None)
                    self.viewport_3d.detector.process_body_mesh(
                        body.id, mesh, extrude_mode=extrude_mode, face_info=face_info
                    )

        count = len(self.viewport_3d.detector.selection_faces)
        if count == 0:
            logger.warning("Keine geschlossenen Flächen erkannt!")
    
    def _get_plane_from_sketch(self, sketch):
        """Erstellt ein build123d Plane Objekt aus den Sketch-Metadaten"""
        from build123d import Plane, Vector
        return Plane(
            origin=Vector(sketch.plane_origin),
            z_dir=Vector(sketch.plane_normal),
            x_dir=Vector(sketch.plane_x_dir)
        )
    
    def _on_extrusion_finished(self, face_indices, height, operation="New Body"):
        """
        Erstellt die finale Geometrie.
        FIX V2: Robustes Targeting. Verhindert "Cut All" Katastrophen.
        Wählt IMMER nur einen Ziel-Körper aus (den passendsten), anstatt alle zu schneiden.
        """
        from i18n import tr
        from modeling import ExtrudeFeature
        from gui.commands.feature_commands import AddFeatureCommand
        
        # Debounce
        if getattr(self, '_is_processing_extrusion', False):
            return
        self._is_processing_extrusion = True

        try:
            # 1. Daten sammeln
            # Nutze face_indices aus dem Signal wenn vorhanden, sonst selected_face_ids
            face_ids = face_indices if face_indices else list(self.viewport_3d.selected_face_ids)

            selection_data = []
            for fid in face_ids:
                face = next((f for f in self.viewport_3d.detector.selection_faces if f.id == fid), None)
                if face:
                    selection_data.append(face)

            if not selection_data:
                logger.warning(tr("Nichts selektiert."))
                return

            first_face = selection_data[0]

            # Fall A: Sketch-Extrusion
            if first_face.domain_type.startswith('sketch'):
                try:
                    source_id = first_face.owner_id
                    # WICHTIG: get_all_sketches() statt .sketches - letzteres nur für aktive Component!
                    target_sketch = next((s for s in self.document.get_all_sketches() if s.id == source_id), None)
                    polys = [f.shapely_poly for f in selection_data]

                    # --- TARGETING LOGIK (STRIKT) ---
                    target_bodies = []
                    
                    # 1. User hat explizit einen Body im Browser selektiert?
                    active_body = self._get_active_body()
                    browser_selection = self.browser.tree.selectedItems()
                    has_explicit_selection = len(browser_selection) > 0

                    if operation == "New Body":
                        # Immer neuer Körper
                        target_bodies = [self.document.new_body()]
                        
                    elif has_explicit_selection and active_body:
                        # Explizite Wahl gewinnt immer
                        target_bodies = [active_body]
                        
                    else:
                        # AUTO-DETECTION
                        # ✅ FIX: Operation-aware targeting
                        # - Join: Use parent body (adding to same body)
                        # - Cut: Use intersecting body (cutting whatever the volume hits)

                        if operation == "Join":
                            # Join sollte den Parent-Body nutzen (Material hinzufügen)
                            if hasattr(target_sketch, 'parent_body_id') and target_sketch.parent_body_id:
                                # WICHTIG: find_body_by_id durchsucht alle Components!
                                parent_body = self.document.find_body_by_id(target_sketch.parent_body_id)
                                if parent_body:
                                    target_bodies = [parent_body]
                                    logger.info(f"🎯 Join: Nutze Parent-Body '{parent_body.name}'")

                        # Für Cut/Intersect: Finde Body der mit Extrusion-Volumen überlappt
                        if not target_bodies:
                            priority_body = self._find_body_closest_to_sketch(target_sketch, selection_data)

                            if priority_body:
                                target_bodies = [priority_body]
                                logger.info(f"🎯 Auto-Target: Nutze nächsten Body '{priority_body.name}' (Proximity)")
                            else:
                                # Fallback: Wenn wir wirklich nichts finden (z.B. Skizze weit im Raum),
                                # nehmen wir bei Join/Cut lieber den letzten Körper als gar keinen oder alle.
                                # WICHTIG: get_all_bodies() statt .bodies - letzteres nur für aktive Component!
                                all_bodies = self.document.get_all_bodies()
                                if all_bodies and operation != "New Body":
                                    target_bodies = [all_bodies[-1]]
                                    logger.info(f"⚠️ Targeting Fallback: Nutze '{target_bodies[0].name}'")

                    if not target_bodies and operation == "Cut":
                        logger.warning("Kein Ziel-Körper gefunden. Bitte Körper im Browser auswählen.")
                        return

                    # --- FEATURE ANWENDEN ---
                    success_count = 0

                    # CAD KERNEL FIRST: Finde die passenden Profile in sketch.closed_profiles
                    # und speichere DEREN Centroids (nicht die aus der UI-Auswahl!)
                    # Das garantiert dass die Centroids beim Rebuild übereinstimmen.
                    # Profile kommen NUR aus: 1) SketchEditor-Detection, 2) Laden aus Datei
                    sketch_profiles = getattr(target_sketch, 'closed_profiles', [])
                    profile_selector = []

                    for sel_poly in polys:
                        try:
                            sel_centroid = sel_poly.centroid
                            sel_cx, sel_cy = sel_centroid.x, sel_centroid.y
                            sel_area = sel_poly.area

                            # Finde das passende Profil in sketch.closed_profiles
                            best_match = None
                            best_dist = float('inf')

                            for sketch_poly in sketch_profiles:
                                sk_centroid = sketch_poly.centroid
                                sk_cx, sk_cy = sk_centroid.x, sk_centroid.y
                                sk_area = sketch_poly.area

                                # Centroid-Distanz
                                import math
                                dist = math.hypot(sel_cx - sk_cx, sel_cy - sk_cy)

                                # Area-Check (innerhalb 20% Toleranz)
                                area_diff = abs(sel_area - sk_area) / max(sel_area, sk_area, 1)

                                if dist < best_dist and area_diff < 0.2:
                                    best_dist = dist
                                    best_match = (sk_cx, sk_cy)

                            if best_match:
                                profile_selector.append(best_match)
                                logger.debug(f"[EXTRUDE] Matched selection ({sel_cx:.2f}, {sel_cy:.2f}) → sketch ({best_match[0]:.2f}, {best_match[1]:.2f})")
                            else:
                                # Kein Match gefunden - Fehler!
                                logger.error(f"[EXTRUDE] No match in sketch.closed_profiles for ({sel_cx:.2f}, {sel_cy:.2f})")
                                logger.error(f"[EXTRUDE] Verfügbare Profile: {[(p.centroid.x, p.centroid.y) for p in sketch_profiles]}")
                        except Exception as e:
                            logger.warning(f"Profile-Matching fehlgeschlagen: {e}")

                    # CAD KERNEL FIRST: Wenn Auswahl getroffen aber kein Match → Abbruch!
                    if polys and not profile_selector:
                        logger.error(f"[EXTRUDE] Matching fehlgeschlagen! {len(polys)} selektiert, 0 gematcht. Abbruch.")
                        self._on_extrude_cancelled()
                        return

                    for body in target_bodies:
                        feature = ExtrudeFeature(
                            sketch=target_sketch,
                            distance=height,
                            operation=operation,
                            profile_selector=profile_selector,  # CAD Kernel First!
                            precalculated_polys=polys,  # Nur für Push/Pull (sketchless)
                            plane_origin=getattr(target_sketch, 'plane_origin', (0, 0, 0)),
                            plane_normal=getattr(target_sketch, 'plane_normal', (0, 0, 1)),
                            plane_x_dir=getattr(target_sketch, 'plane_x_dir', None),
                            plane_y_dir=getattr(target_sketch, 'plane_y_dir', None),
                        )
                        
                        # Initialen Profile-Hash setzen für Performance-Optimierung
                        # (verhindert unnötige Rebuilds wenn sich der Sketch ändert)
                        feature._profile_hash = self._compute_profile_hash(feature, target_sketch)

                        try:
                            cmd = AddFeatureCommand(
                                body, feature, self,
                                description=f"Extrude ({operation})"
                            )
                            self.undo_stack.push(cmd)  
                            
                            # Safety Check: Hat die Operation den Body zerstört?
                            if hasattr(body, 'vtk_mesh') and (body.vtk_mesh is None or body.vtk_mesh.n_points == 0):
                                logger.warning(f"Operation ließ Body '{body.name}' verschwinden (Invalid Result). Undo.")
                                self.undo_stack.undo()
                            else:
                                success_count += 1
                        except Exception as e:
                            logger.error(f"Extrude-Feature fehlgeschlagen: {e}")
                            # Auto-Undo bei Fehler
                            self.undo_stack.undo()

                    if success_count > 0:
                        self._finish_extrusion_ui(success=True)
                        logger.success(f"Extrude: {success_count} Body/ies erstellt/geändert")

                except Exception as e:
                    logger.error(f"Extrusion fehlgeschlagen: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    self._is_processing_extrusion = False
                return

            # Fall B: Body-Face Extrusion (Push/Pull)
            elif first_face.domain_type.startswith('body'):
                try:
                    self._extrude_body_face_build123d(selection_data, height, operation)
                    self._finish_extrusion_ui(success=True)
                except Exception as e:
                    logger.error(f"Body-Face Extrusion fehlgeschlagen: {e}")
                finally:
                    self._is_processing_extrusion = False
                return

        except Exception as e:
            logger.error(f"Extrusion fehlgeschlagen: {e}")
        finally:
            self._is_processing_extrusion = False
    
    def _find_body_closest_to_sketch(self, sketch, faces):
        """
        Findet den Body, der am nächsten zur Sketch-Ebene liegt.
        Wichtig für Auto-Targeting bei Cut/Join.
        """
        import math
        
        if not sketch:
            return None
            
        # Sketch-Zentrum in 3D
        sketch_origin = np.array(sketch.plane_origin)
        sketch_normal = np.array(sketch.plane_normal)
        
        best_body = None
        best_distance = float('inf')
        
        for body in self.document.get_all_bodies():
            if not self.viewport_3d.is_body_visible(body.id):
                continue
                
            mesh = self.viewport_3d.get_body_mesh(body.id)
            if mesh is None or mesh.n_points == 0:
                continue
            
            # Distanz vom Sketch-Ursprung zum Body-Mittelpunkt
            body_center = mesh.center
            distance = np.linalg.norm(body_center - sketch_origin)
            
            # Projiziere auf Sketch-Normale für "über/unter" Information
            to_body = body_center - sketch_origin
            normal_dist = np.dot(to_body, sketch_normal)
            
            # Bevorzuge Bodies die "vor" dem Sketch liegen (positive Normale)
            # aber nimm den nächsten wenn keiner vor liegt
            if normal_dist >= 0 and distance < best_distance:
                best_distance = distance
                best_body = body
            elif normal_dist < 0 and best_body is None:
                best_body = body
                
        return best_body
    
    def _finish_extrusion_ui(self, success=True, msg=""):
        """Hilfsfunktion zum Aufräumen der UI"""
        self.viewport_3d.set_extrude_mode(False)
        self.extrude_panel.setVisible(False)
        if hasattr(self.viewport_3d, 'detector'):
            self.viewport_3d.detector.clear()
        self.viewport_3d.selected_face_ids.clear()
        self.viewport_3d.hover_face_id = -1
        self.viewport_3d._draw_selectable_faces_from_detector()
        self._update_viewport_all_impl()
        self.browser.refresh()
    
    # =========================================================================
    # Feature Editing
    # =========================================================================
    
    def _delete_selected(self):
        """Löscht alle ausgewählten Bodies."""
        selected = self.browser.get_selected_bodies()
        if selected:
            for body in selected:
                self.browser._del_body(body)

    def _edit_feature(self, d): 
        """
        Wird aufgerufen durch Doppelklick im Browser.
        FIX: Lädt jetzt auch die Referenz-Geometrie für den Hintergrund!
        """
        if d[0] == 'sketch':
            sketch = d[1]
            self.active_sketch = sketch
            self.sketch_editor.sketch = sketch
            
            # 1. Gespeicherte Achsen holen (oder Fallback berechnen)
            origin = sketch.plane_origin
            normal = sketch.plane_normal
            x_dir = getattr(sketch, 'plane_x_dir', None)
            
            if x_dir is None:
                # Fallback für alte Skizzen ohne gespeicherte X-Achse
                x_dir, _ = self._calculate_plane_axes(normal)

            # 2. Hintergrund-Referenzen laden (LÖST PROBLEM 2)
            # Wir übergeben explizit x_dir, damit der Hintergrund nicht verdreht ist
            self._set_sketch_body_references(origin, normal, x_dir)
            
            # 3. Modus wechseln
            self._set_mode("sketch")
            
            # 4. Statusmeldung
            logger.success(f"Bearbeite Skizze: {sketch.name}")

        elif d[0] == 'feature':
            feature = d[1]
            body = d[2]

            from modeling import (TransformFeature, ExtrudeFeature, FilletFeature,
                                  ChamferFeature, ShellFeature, RevolveFeature, FeatureType)
            if isinstance(feature, TransformFeature) or feature.type == FeatureType.TRANSFORM:
                self._edit_transform_feature(feature, body)
            elif isinstance(feature, ExtrudeFeature):
                self._edit_parametric_feature(feature, body, 'extrude')
            elif isinstance(feature, FilletFeature):
                self._edit_parametric_feature(feature, body, 'fillet')
            elif isinstance(feature, ChamferFeature):
                self._edit_parametric_feature(feature, body, 'chamfer')
            elif isinstance(feature, ShellFeature):
                self._edit_parametric_feature(feature, body, 'shell')
            elif isinstance(feature, RevolveFeature):
                self._edit_parametric_feature(feature, body, 'revolve')
            else:
                logger.info(f"Feature '{feature.name}' kann nicht editiert werden (Typ: {feature.type})")

    def _edit_transform_feature(self, feature, body):
        """
        Öffnet den Transform-Edit-Dialog und aktualisiert den Body nach Änderung.
        """
        from gui.dialogs.transform_edit_dialog import TransformEditDialog
        from gui.commands.feature_commands import EditFeatureCommand

        # Speichere alte Daten für Undo
        old_data = feature.data.copy()

        dialog = TransformEditDialog(feature, body, self)

        if dialog.exec():
            # Feature wurde geändert
            new_data = feature.data.copy()

            # Push to Undo Stack
            cmd = EditFeatureCommand(body, feature, old_data, new_data, self)
            self.undo_stack.push(cmd)

            logger.success(f"Transform-Feature '{feature.name}' aktualisiert (Undo: Ctrl+Z)")

    def _edit_parametric_feature(self, feature, body, feature_type: str):
        """
        Generischer Edit-Dialog fuer parametrische Features.
        Unterstuetzt: extrude, fillet, chamfer, shell
        """
        from gui.commands.feature_commands import EditFeatureCommand

        # Alte Daten sichern
        if feature_type == 'extrude':
            from gui.dialogs.feature_edit_dialogs import ExtrudeEditDialog
            old_data = {
                'distance': feature.distance,
                'direction': feature.direction,
                'operation': feature.operation,
            }
            dialog = ExtrudeEditDialog(feature, body, self)
        elif feature_type == 'fillet':
            from gui.dialogs.feature_edit_dialogs import FilletEditDialog
            old_data = {'radius': feature.radius}
            dialog = FilletEditDialog(feature, body, self)
        elif feature_type == 'chamfer':
            from gui.dialogs.feature_edit_dialogs import ChamferEditDialog
            old_data = {'distance': feature.distance}
            dialog = ChamferEditDialog(feature, body, self)
        elif feature_type == 'shell':
            from gui.dialogs.feature_edit_dialogs import ShellEditDialog
            old_data = {'thickness': feature.thickness}
            dialog = ShellEditDialog(feature, body, self)
        elif feature_type == 'revolve':
            from gui.dialogs.feature_edit_dialogs import RevolveEditDialog
            old_data = {'angle': feature.angle, 'axis': feature.axis, 'operation': feature.operation}
            dialog = RevolveEditDialog(feature, body, self)
        elif feature_type == 'loft':
            from gui.dialogs.feature_edit_dialogs import LoftEditDialog
            old_data = {
                'ruled': feature.ruled,
                'operation': feature.operation,
                'start_continuity': feature.start_continuity,
                'end_continuity': feature.end_continuity
            }
            dialog = LoftEditDialog(feature, body, self)
        elif feature_type == 'sweep':
            from gui.dialogs.feature_edit_dialogs import SweepEditDialog
            old_data = {
                'operation': feature.operation,
                'is_frenet': feature.is_frenet,
                'twist_angle': feature.twist_angle
            }
            dialog = SweepEditDialog(feature, body, self)
        else:
            logger.warning(f"Unbekannter Feature-Typ: {feature_type}")
            return

        if dialog.exec():
            # Neue Daten nach Dialog-Aenderung
            if feature_type == 'extrude':
                new_data = {
                    'distance': feature.distance,
                    'direction': feature.direction,
                    'operation': feature.operation,
                }
            elif feature_type == 'fillet':
                new_data = {'radius': feature.radius}
            elif feature_type == 'chamfer':
                new_data = {'distance': feature.distance}
            elif feature_type == 'shell':
                new_data = {'thickness': feature.thickness}
            elif feature_type == 'revolve':
                new_data = {'angle': feature.angle, 'axis': feature.axis, 'operation': feature.operation}
            elif feature_type == 'loft':
                new_data = {
                    'ruled': feature.ruled,
                    'operation': feature.operation,
                    'start_continuity': feature.start_continuity,
                    'end_continuity': feature.end_continuity
                }
            elif feature_type == 'sweep':
                new_data = {
                    'operation': feature.operation,
                    'is_frenet': feature.is_frenet,
                    'twist_angle': feature.twist_angle
                }

            cmd = EditFeatureCommand(body, feature, old_data, new_data, self)
            self.undo_stack.push(cmd)
            logger.success(f"Feature '{feature.name}' aktualisiert (Undo: Ctrl+Z)")

    def _on_feature_deleted(self, feature, body):
        """
        Handler fuer Feature-Loeschung aus dem Browser.
        Warnt bei abhaengigen Features, triggert Rebuild.
        """
        from gui.commands.feature_commands import DeleteFeatureCommand
        from modeling import FilletFeature, ChamferFeature, ShellFeature

        logger.info(f"Lösche Feature '{feature.name}' aus {body.name}...")

        # Abhaengigkeits-Check: Features die NACH diesem kommen und davon abhaengen koennten
        feature_index = body.features.index(feature) if feature in body.features else 0
        dependent_features = []
        for f in body.features[feature_index + 1:]:
            if isinstance(f, (FilletFeature, ChamferFeature, ShellFeature)):
                dependent_features.append(f.name)

        if dependent_features:
            deps_str = ", ".join(dependent_features)
            reply = QMessageBox.question(
                self,
                "Feature loeschen?",
                f"'{feature.name}' wird von nachfolgenden Features verwendet:\n"
                f"{deps_str}\n\n"
                f"Diese Features koennten nach dem Loeschen fehlschlagen.\n"
                f"Trotzdem loeschen?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        # Push to Undo Stack
        cmd = DeleteFeatureCommand(body, feature, feature_index, self)
        self.undo_stack.push(cmd)

        logger.success(f"Feature '{feature.name}' gelöscht (Undo: Ctrl+Z)")
    
    def _on_feature_selected(self, data):
        """Wird aufgerufen wenn ein Feature im Tree ausgewählt wird"""
        if data[0] == 'feature':
            feature = data[1]
            body = data[2]

            # Feature im Viewport hervorheben
            if hasattr(self.viewport_3d, 'highlight_feature'):
                self.viewport_3d.highlight_feature(body, feature)

            # Feature-Details im Panel anzeigen
            if hasattr(self, 'feature_detail_panel'):
                self.feature_detail_panel.show_feature(feature, body)

    def _edit_feature(self, data):
        """Wird aufgerufen wenn ein Feature per Doppelklick bearbeitet werden soll."""
        if not data or data[0] != 'feature':
            return

        feature = data[1]
        body = data[2]

        # CadQueryFeature: Öffne Script Editor
        from modeling.features.cadquery_feature import CadQueryFeature
        if isinstance(feature, CadQueryFeature):
            self._edit_cadquery_feature(feature, body)
            return

        # SketchFeature: Öffne Sketch Editor
        # ExtrudeFeature mit Sketch: Öffne Sketch Editor
        # TODO: Andere Feature-Typen implementieren

    def _edit_cadquery_feature(self, feature, body):
        """Öffne den CadQuery Script Editor mit dem Feature-Script."""
        from gui.cadquery_editor_dialog import CadQueryEditorDialog
        from modeling.cadquery_importer import CadQueryImporter
        from gui.design_tokens import DesignTokens

        try:
            # Create dialog with auto_execute enabled for live parameter updates
            dialog = CadQueryEditorDialog(self.document, parent=self, auto_execute=True)

            # Lade das Script aus dem Feature
            if feature.script:
                dialog.set_script(feature.script)
            else:
                # Fallback: Versuche aus Source-File zu laden
                if feature.source_file:
                    try:
                        from pathlib import Path
                        script_path = Path(__file__).parent.parent / "examples" / "cadquery_examples" / feature.source_file
                        if script_path.exists():
                            dialog.set_script(script_path.read_text(encoding='utf-8'))
                    except:
                        pass

            # Überschreibe das execute-Verhalten um das Feature zu aktualisieren
            original_execute = dialog._execute_script

            def execute_and_update():
                """Führe Script aus und aktualisiere das Feature."""
                from modeling import BodyTransaction
                from modeling.result_types import OperationResult

                code = dialog.editor.toPlainText()
                script_source = dialog.current_file.name if dialog.current_file else feature.source_file

                # Clear error display
                dialog.error_label.setVisible(False)
                dialog.error_label.setText("")
                dialog.error_label.setStyleSheet("")

                # Execute
                importer = CadQueryImporter(self.document)
                result = importer.execute_code(code, source=script_source)

                if result.success and result.solids:
                    # Use transaction for undo/redo support
                    with BodyTransaction(body, f"Edit CadQuery Feature: {feature.name}") as txn:
                        # Update the feature's script
                        feature.script = code
                        feature.source_file = script_source
                        # Update parameters
                        from modeling.features.cadquery_feature import extract_parameters_from_script
                        feature.parameters = extract_parameters_from_script(code)

                        # Update the solid
                        if len(result.solids) > 0:
                            body._build123d_solid = result.solids[0]
                            body.invalidate_mesh()

                        txn.commit()

                    # Refresh UI
                    self.browser.refresh()
                    self._update_viewport_all_impl()

                    dialog._show_success(f"Feature updated: {len(result.solids)} body(s)")
                    dialog.accept()  # Close dialog on success

                elif result.success:
                    dialog._show_warning("No solids were generated from the script")
                else:
                    error_text = "\n".join(result.errors)
                    dialog._show_error(f"Execution failed:\n{error_text}")

            # Replace the execute method
            dialog._execute_script = execute_and_update

            # Block the script_executed signal (we handle execution directly)
            dialog.script_executed.block = True

            dialog.exec()

        except Exception as e:
            logger.error(f"Fehler beim Öffnen des CadQuery Editors: {e}")

    # =========================================================================
    # Rollback
    # =========================================================================
    
    def _on_rollback_changed(self, body, value):
        """Handle rollback slider change - rebuild body up to given feature index."""
        from modeling.cad_tessellator import CADTessellator
        
        n = len(body.features)
        rebuild_up_to = value if value < n else None
        body.rollback_index = rebuild_up_to

        CADTessellator.notify_body_changed()

        def _on_rebuild_progress(current, total, name):
            self.statusBar().showMessage(f"Rebuild {current + 1}/{total}: {name}")
            QApplication.processEvents()

        body._rebuild(rebuild_up_to=rebuild_up_to, progress_callback=_on_rebuild_progress if n >= 5 else None)
        self._update_body_from_build123d(body, body._build123d_solid)
        self.browser.refresh()
        self.browser.show_rollback_bar(body)
        self.statusBar().showMessage(f"Rollback: {value}/{n} Features")

    def _on_body_deleted(self, body_id: str):
        """Handle body deletion - remove from viewport."""
        # Remove body actors from viewport
        if hasattr(self.viewport_3d, 'clear_bodies'):
            self.viewport_3d.clear_bodies(only_body_id=body_id)
        # Full viewport refresh
        self._update_viewport_all_impl()

    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _get_active_body(self):
        """Hilfsfunktion: Gibt den aktuell im Browser ausgewählten Body zurück"""
        selected = self.browser.get_selected_bodies()
        return selected[0] if selected else None
    
    def _extrude_body_face_build123d(self, face_data, height, operation):
        """
        Extrudiert eine Body-Fläche mit build123d (Push/Pull).
        """
        # Placeholder - implementation would be extensive
        # This is extracted from main_window.py for modularity
        pass
