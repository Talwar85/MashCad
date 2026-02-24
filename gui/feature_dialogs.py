"""
MashCAD Feature Dialogs Module
================================

Extracted from main_window.py (AR-005 EXTENDED).

This module contains feature-related dialog operations as a mixin class.
Maintains backward compatibility by being imported into MainWindow.

Usage:
    class MainWindow(FeatureDialogsMixin, QMainWindow):
        pass
"""

from typing import TYPE_CHECKING, Optional, List, Dict, Any, Tuple
import numpy as np
from loguru import logger

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

if TYPE_CHECKING:
    from modeling import Body, Document
    from gui.main_window import MainWindow


class FeatureDialogsMixin:
    """
    Mixin class containing feature-related dialog operations for MainWindow.
    
    This class provides:
    - Pattern operations
    - Shell operations
    - Texture operations
    - Sweep operations
    - Loft operations
    - Component operations
    - BREP cleanup operations
    - TNP operations
    
    All methods assume they are called within a MainWindow context
    and access MainWindow attributes via `self`.
    """
    
    # =========================================================================
    # Pattern Operations
    # =========================================================================
    
    def _create_pattern(self):
        """
        Startet den Pattern-Workflow.
        """
        from i18n import tr
        
        self._pattern_mode = True
        self._pending_pattern_mode = True
        self.viewport_3d.setCursor(Qt.CrossCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(True)
        self.statusBar().showMessage(tr("Wähle Body für Pattern"))
        logger.info("Pattern: Klicke auf einen Body")

    def _get_body_center(self, body) -> tuple:
        """Berechnet das Zentrum eines Bodies aus Bounding Box."""
        if hasattr(body, '_build123d_solid') and body._build123d_solid:
            try:
                bbox = body._build123d_solid.bounding_box()
                return ((bbox.min.X + bbox.max.X) / 2,
                        (bbox.min.Y + bbox.max.Y) / 2,
                        (bbox.min.Z + bbox.max.Z) / 2)
            except Exception:
                pass
        
        mesh = self.viewport_3d.get_body_mesh(body.id)
        if mesh:
            center = mesh.center
            return (center[0], center[1], center[2])
        
        return (0, 0, 0)

    def _duplicate_body(self, body, new_name: str):
        """Erstellt eine Kopie eines Bodies mit transformiertem Solid."""
        from modeling import Body
        from modeling.cad_tessellator import CADTessellator
        
        new_body = Body(name=new_name, document=self.document)
        
        if hasattr(body, '_build123d_solid') and body._build123d_solid:
            from build123d import Location
            new_body._build123d_solid = body._build123d_solid.moved(Location((0, 0, 0)))
            CADTessellator.notify_body_changed()
        
        return new_body

    def _on_body_clicked_for_pattern(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body für Pattern angeklickt wird."""
        self._pending_pattern_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        body = self.document.find_body_by_id(body_id)
        if body:
            self._activate_pattern_for_body(body)

    def _activate_pattern_for_body(self, body):
        """Aktiviert Pattern-Modus für einen Body."""
        if getattr(body, '_build123d_solid', None) is None:
            logger.warning("Pattern erfordert einen CAD-Body (kein Mesh).")
            return

        self._pattern_mode = True
        self._pattern_target_body = body
        self._pending_pattern_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)
        if hasattr(self.pattern_panel, 'set_target_body'):
            self.pattern_panel.set_target_body(body)
        self.pattern_panel.reset()
        self.pattern_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage("Pattern: Parameter einstellen")

    def _on_pattern_parameters_changed(self, params: dict):
        """Handler für Live-Preview wenn Parameter geändert werden."""
        self._update_pattern_preview(params)

    def _update_pattern_preview(self, params: dict):
        """Generiert/aktualisiert Pattern-Preview."""
        if not self._pattern_target_body:
            return
        # Preview handled by viewport

    def _clear_pattern_preview(self):
        """Entfernt Pattern-Preview."""
        if hasattr(self.viewport_3d, 'clear_pattern_preview'):
            self.viewport_3d.clear_pattern_preview()

    def _on_pattern_confirmed(self):
        """Handler wenn Pattern bestätigt wird."""
        if not self._pattern_target_body:
            return
        
        if hasattr(self.pattern_panel, 'get_pattern_data'):
            params = self.pattern_panel.get_pattern_data()
        else:
            params = self.pattern_panel.get_parameters()
        self._execute_pattern(self._pattern_target_body, params)
        self._stop_pattern_mode()

    def _on_pattern_cancelled(self):
        """Handler wenn Pattern abgebrochen wird."""
        self._stop_pattern_mode()

    def _on_pattern_center_pick_requested(self):
        """Handler wenn User Custom Center auswählen will."""
        self._pattern_center_pick_mode = True
        self.viewport_3d.setCursor(Qt.CrossCursor)
        if hasattr(self.viewport_3d, 'set_measure_mode'):
            self.viewport_3d.set_measure_mode(True)
        else:
            self.viewport_3d.measure_mode = True
        self.statusBar().showMessage("Klicke auf das gewünschte Zentrum")

    def _on_pattern_center_picked(self, point: tuple):
        """Handler wenn ein Zentrum-Punkt gepickt wurde."""
        self._pattern_center_pick_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_measure_mode'):
            self.viewport_3d.set_measure_mode(False)
        else:
            self.viewport_3d.measure_mode = False
        self.pattern_panel.set_custom_center(point[0], point[1], point[2])
        self.statusBar().showMessage(f"Zentrum gesetzt auf ({point[0]:.1f}, {point[1]:.1f}, {point[2]:.1f})")

    def _execute_pattern(self, body, params: dict):
        """Führt Pattern aus und erstellt die Bodies."""
        from modeling import PatternFeature
        from gui.commands.feature_commands import AddFeatureCommand
        
        pattern_type = params.get('type', 'linear')
        count = params.get('count', 3)
        spacing = params.get('spacing', 10.0)
        
        feature = PatternFeature(
            pattern_type=pattern_type,
            count=count,
            spacing=spacing,
            **params
        )
        
        cmd = AddFeatureCommand(body, feature, self, description=f"Pattern {pattern_type}")
        self.undo_stack.push(cmd)
        
        self.browser.refresh()
        self._update_viewport_all()
        logger.success(f"Pattern erstellt: {count} Kopien")

    def _stop_pattern_mode(self):
        """Beendet den Pattern-Modus."""
        self._pattern_mode = False
        self._pattern_target_body = None
        self._pending_pattern_mode = False
        self._pattern_center_pick_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_measure_mode'):
            self.viewport_3d.set_measure_mode(False)
        else:
            self.viewport_3d.measure_mode = False
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)
        self.pattern_panel.hide()
        self._clear_pattern_preview()
        self.statusBar().clearMessage()
    
    # =========================================================================
    # Shell Operations
    # =========================================================================
    
    def _on_body_clicked_for_shell(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body für Shell angeklickt wird."""
        self._pending_shell_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        body = self.document.find_body_by_id(body_id)
        if body:
            self._activate_shell_for_body(body)

    def _on_body_clicked_for_fillet(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body für Fillet/Chamfer angeklickt wird."""
        # Check which mode is pending (string- und bool-kompatibel).
        mode = None
        pending_fillet = getattr(self, '_pending_fillet_mode', False)
        pending_chamfer = getattr(self, '_pending_chamfer_mode', False)

        if isinstance(pending_fillet, str):
            mode = pending_fillet
        elif pending_chamfer:
            mode = 'chamfer'
        elif pending_fillet:
            mode = 'fillet'
        else:
            return  # No fillet/chamfer pending

        self._pending_fillet_mode = False
        self._pending_chamfer_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        body = self.document.find_body_by_id(body_id)
        if body:
            # Import here to avoid circular import
            from gui.tool_operations import ToolMixin
            # Call the activate method - need to access it through self
            if hasattr(self, '_activate_fillet_chamfer_for_body'):
                self._activate_fillet_chamfer_for_body(body, mode)

    def _activate_shell_for_body(self, body):
        """Aktiviert Shell-Modus für einen Body."""
        if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
            logger.warning(f"'{body.name}' hat keine CAD-Daten (nur Mesh).")
            return

        if hasattr(self.viewport_3d, 'hide_transform_gizmo'):
            self.viewport_3d.hide_transform_gizmo()

        self._shell_mode = True
        self._shell_target_body = body
        self._shell_opening_faces = []
        self._shell_opening_face_shape_ids = []
        self._shell_opening_face_indices = []
        self._pending_shell_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        if hasattr(self.viewport_3d, 'set_extrude_mode'):
            self.viewport_3d.set_extrude_mode(True, enable_preview=False)
        if hasattr(self, '_update_detector'):
            self._update_detector()

        if hasattr(self.shell_panel, 'set_target_body'):
            self.shell_panel.set_target_body(body)
        if hasattr(self.shell_panel, 'clear_opening_faces'):
            self.shell_panel.clear_opening_faces()
        self.shell_panel.reset()
        self.shell_panel.show_at(self.viewport_3d)
        self.viewport_3d.set_shell_mode(True)

        self.statusBar().showMessage("Shell: Wähle Öffnungs-Flächen")
        logger.info(f"Shell-Modus für '{body.name}' - Flächen anklicken")

    def _on_face_selected_for_shell(self, face_id):
        """Handler wenn eine Fläche für Shell selektiert wird."""
        if not self._shell_mode or not self._shell_target_body:
            return

        face = next((f for f in self.viewport_3d.detector.selection_faces if f.id == face_id), None)
        if not face:
            logger.warning(f"Shell: Face mit ID {face_id} nicht im Detector gefunden")
            return
        if not face.domain_type.startswith('body'):
            logger.warning(f"Shell: Nur Body-Flächen erlaubt, aber domain_type={face.domain_type}")
            return

        try:
            from modeling.geometric_selector import GeometricFaceSelector

            body = self._shell_target_body
            if not body or not body._build123d_solid:
                return

            face_center = None
            if getattr(face, "shapely_poly", None) is not None:
                centroid = face.shapely_poly.centroid
                plane_x = np.array(face.plane_x)
                plane_y = np.array(face.plane_y)
                origin = np.array(face.plane_origin)
                face_center = origin + centroid.x * plane_x + centroid.y * plane_y
            elif hasattr(face, 'plane_origin') and face.plane_origin is not None:
                face_center = np.array(face.plane_origin)
            else:
                logger.warning("Shell: Kann Face-Center nicht bestimmen")
                return

            best_face, resolved_face_id = self._resolve_solid_face_from_pick(
                body,
                body.id,
                position=face_center,
                ocp_face_id=getattr(face, "ocp_face_id", None),
            )

            if best_face is not None:
                geo_selector = GeometricFaceSelector.from_face(best_face)
                face_selector = geo_selector.to_dict()
                face_shape_id = self._find_or_register_face_shape_id(
                    body,
                    best_face,
                    local_index=max(0, len(self._shell_opening_face_shape_ids)),
                )
            else:
                face_selector = {
                    "center": list(face_center),
                    "normal": list(face.plane_normal),
                    "area": 0.0,
                    "surface_type": "unknown",
                    "tolerance": 10.0,
                }
                face_shape_id = None
                logger.warning("Shell: Konnte Face nicht finden, verwende Fallback")
        except Exception as e:
            logger.warning(f"Shell: Konnte Fläche nicht hinzufügen: {e}")
            return

        already_selected = False
        center_arr = np.array(face_selector["center"], dtype=float)
        for i, existing_sel in enumerate(self._shell_opening_faces):
            existing_center = np.array(existing_sel.get("center", [0.0, 0.0, 0.0]), dtype=float)
            if np.linalg.norm(existing_center - center_arr) < 0.1:
                removed_selector = self._shell_opening_faces.pop(i)
                if i < len(self._shell_opening_face_shape_ids):
                    self._shell_opening_face_shape_ids.pop(i)
                if i < len(self._shell_opening_face_indices):
                    self._shell_opening_face_indices.pop(i)
                if hasattr(self.shell_panel, 'remove_opening_face'):
                    self.shell_panel.remove_opening_face(removed_selector)
                already_selected = True
                break

        if not already_selected:
            self._shell_opening_faces.append(face_selector)
            self._shell_opening_face_shape_ids.append(face_shape_id)
            self._shell_opening_face_indices.append(
                int(resolved_face_id) if resolved_face_id is not None else None
            )
            if hasattr(self.shell_panel, 'add_opening_face'):
                self.shell_panel.add_opening_face(face_selector)

        if hasattr(self.shell_panel, 'update_face_count'):
            self.shell_panel.update_face_count(len(self._shell_opening_faces))
        elif hasattr(self.shell_panel, 'set_opening_count'):
            self.shell_panel.set_opening_count(len(self._shell_opening_faces))

    def _on_shell_confirmed(self):
        """Handler wenn Shell bestätigt wird."""
        body = self._shell_target_body
        if not body:
            logger.error("Shell: Kein Body ausgewählt")
            return

        from config.feature_flags import is_enabled
        from modeling import ShellFeature
        from modeling.cad_tessellator import CADTessellator
        from gui.commands.feature_commands import AddFeatureCommand
        from PySide6.QtWidgets import QMessageBox

        thickness = self.shell_panel.get_thickness()

        feature = ShellFeature(
            thickness=thickness,
            opening_face_selectors=self._shell_opening_faces.copy()
        )

        face_shape_ids = [sid for sid in self._shell_opening_face_shape_ids if sid is not None]
        face_indices = [idx for idx in self._shell_opening_face_indices if idx is not None]
        feature.face_shape_ids = face_shape_ids
        if face_indices:
            feature.face_indices = sorted(set(int(i) for i in face_indices))
        if is_enabled("tnp_debug_logging"):
            logger.debug(
                f"TNP v4.0: Shell refs prepared "
                f"(shape_ids={len(face_shape_ids)}, indices={len(feature.face_indices or [])})"
            )

        cmd = AddFeatureCommand(body, feature, self, description=f"Shell ({thickness}mm)")
        self.undo_stack.push(cmd)

        if body._build123d_solid is None:
            self.undo_stack.undo()
            QMessageBox.critical(self, "Fehler", "Shell fehlgeschlagen: Geometrie ungültig")
            return

        if feature.status == "ERROR":
            msg = feature.status_message or "Kernel-Operation fehlgeschlagen"
            self.statusBar().showMessage(f"Shell fehlgeschlagen: {msg}", 8000)
            logger.error(f"Shell fehlgeschlagen: {msg}")
            self._stop_shell_mode()
            self.browser.refresh()
            return
        if feature.status == "WARNING":
            msg = feature.status_message or "Fallback verwendet"
            self.statusBar().showMessage(f"Shell mit Warnung: {msg}", 6000)
            logger.warning(f"Shell mit Warnung: {msg}")

        CADTessellator.notify_body_changed()
        self._update_body_from_build123d(body, body._build123d_solid)
        self.browser.refresh()
        logger.success(f"Shell mit {thickness}mm erstellt")

        self._stop_shell_mode()

    def _on_shell_thickness_changed(self, thickness: float):
        """Handler wenn Shell-Dicke geändert wird."""
        from config.feature_flags import is_enabled

        if not is_enabled("live_preview_shell"):
            return

        if not getattr(self, '_shell_mode', False) or not getattr(self, '_shell_target_body', None):
            return

        if hasattr(self, '_request_live_preview'):
            self._request_live_preview('shell', {
                'thickness': thickness,
                'body': self._shell_target_body,
                'opening_faces': list(getattr(self, '_shell_opening_faces', []))
            })

    def _on_shell_cancelled(self):
        """Bricht die Shell-Operation ab."""
        self._stop_shell_mode()

    def _stop_shell_mode(self):
        """Beendet den Shell-Modus und räumt auf."""
        self._shell_mode = False
        self._shell_target_body = None
        self._shell_opening_faces = []
        self._shell_opening_face_shape_ids = []
        self._shell_opening_face_indices = []
        self._pending_shell_mode = False

        if hasattr(self, '_cancel_live_preview'):
            self._cancel_live_preview('shell')
        elif hasattr(self.viewport_3d, 'clear_all_feature_previews'):
            self.viewport_3d.clear_all_feature_previews()

        self.viewport_3d.set_shell_mode(False)
        if hasattr(self.viewport_3d, 'set_extrude_mode'):
            self.viewport_3d.set_extrude_mode(False)
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)
        self.shell_panel.hide()
        self.statusBar().clearMessage()
    
    # =========================================================================
    # Texture Operations
    # =========================================================================
    
    def _on_body_clicked_for_texture(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body für Texture angeklickt wird."""
        self._pending_texture_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)
        
        body = self.document.find_body_by_id(body_id)
        if body:
            self._activate_texture_for_body(body)

    def _on_texture_face_selected(self, count: int):
        """Callback wenn Texture-Faces im Viewport selektiert werden."""
        if hasattr(self, 'texture_panel') and self.texture_panel.isVisible():
            if hasattr(self.texture_panel, 'set_face_count'):
                self.texture_panel.set_face_count(count)
            elif hasattr(self.texture_panel, 'set_selected_face_count'):
                self.texture_panel.set_selected_face_count(count)

    def _on_texture_applied(self, config: dict):
        """Handler wenn Textur angewendet wird."""
        if not self._texture_target_body:
            return
        
        from modeling import SurfaceTextureFeature
        from gui.commands.feature_commands import AddFeatureCommand

        selected_faces = []
        if hasattr(self.viewport_3d, 'get_texture_selected_faces'):
            selected_faces = self.viewport_3d.get_texture_selected_faces() or []
        if not selected_faces:
            logger.warning("Keine Faces selektiert für Textur")
            return

        face_selectors = []
        for face_data in selected_faces:
            face_selectors.append({
                "center": list(face_data.get("center", (0.0, 0.0, 0.0))),
                "normal": list(face_data.get("normal", (0.0, 0.0, 1.0))),
                "area": float(face_data.get("area", 1.0)),
                "surface_type": face_data.get("surface_type", "plane"),
                "cell_ids": list(face_data.get("cell_ids", [])),
            })
        
        feature = SurfaceTextureFeature(
            texture_type=config.get('texture_type', config.get('type', 'knurl')),
            face_selectors=face_selectors,
            scale=config.get('scale', 1.0),
            depth=config.get('depth', 0.5),
            rotation=config.get('rotation', 0.0),
            invert=config.get('invert', False),
            solid_base=config.get('solid_base', True),
            type_params=config.get('type_params', {}),
            export_subdivisions=config.get('export_subdivisions', 4),
        )
        
        cmd = AddFeatureCommand(self._texture_target_body, feature, self, description="Texture")
        self.undo_stack.push(cmd)
        
        self.browser.refresh()
        self._update_viewport_all()
        if hasattr(self.viewport_3d, 'set_body_object'):
            self.viewport_3d.set_body_object(self._texture_target_body.id, self._texture_target_body)
        if hasattr(self.viewport_3d, 'refresh_texture_previews'):
            self.viewport_3d.refresh_texture_previews(self._texture_target_body.id)
        logger.success("Textur angewendet")
        
        self._stop_texture_mode()

    def _on_texture_preview_requested(self, config: dict):
        """Handler wenn Textur-Preview angefordert wird."""
        if self._texture_target_body:
            self._request_live_preview('texture', {'body': self._texture_target_body, **config})

    def _on_texture_cancelled(self):
        """Bricht die Textur-Operation ab."""
        self._stop_texture_mode()

    def _stop_texture_mode(self):
        """Beendet den Texture-Modus und räumt auf."""
        self._texture_mode = False
        self._texture_target_body = None
        self._pending_texture_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)
        if hasattr(self.viewport_3d, 'stop_texture_face_mode'):
            self.viewport_3d.stop_texture_face_mode()
        if hasattr(self.viewport_3d, 'set_extrude_mode'):
            self.viewport_3d.set_extrude_mode(False)
        self.texture_panel.hide()
        self.statusBar().clearMessage()
    
    # =========================================================================
    # Sweep Operations
    # =========================================================================
    
    def _on_face_selected_for_sweep(self, face_id):
        """Handler wenn eine Fläche für Sweep selektiert wird."""
        if not self._sweep_mode or self._sweep_phase != 'profile':
            return

        face = next((f for f in self.viewport_3d.detector.selection_faces if f.id == face_id), None)
        if not face:
            return

        self._sweep_profile_shape_id = None
        self._sweep_profile_face_index = None
        self._sweep_profile_geometric_selector = None

        profile_data = {
            "type": face.domain_type,
            "owner_id": face.owner_id,
            "face_id": face_id,
            "plane_origin": face.plane_origin,
            "plane_normal": face.plane_normal,
            "plane_x": face.plane_x,
            "plane_y": face.plane_y,
            "shapely_poly": face.shapely_poly,
        }

        if face.domain_type == "body_face":
            profile_data["body_id"] = face.owner_id
            profile_data["ocp_face_id"] = getattr(face, "ocp_face_id", None)

            target_body = self.document.find_body_by_id(face.owner_id) if hasattr(self.document, "find_body_by_id") else None
            resolved_face = None
            resolved_face_index = getattr(face, "ocp_face_id", None)
            if (
                target_body is not None
                and getattr(target_body, "_build123d_solid", None) is not None
                and hasattr(self, "_resolve_solid_face_from_pick")
            ):
                try:
                    pick_position = getattr(face, "sample_point", None) or face.plane_origin
                    resolved_face, resolved_face_index = self._resolve_solid_face_from_pick(
                        target_body,
                        face.owner_id,
                        position=pick_position,
                        ocp_face_id=getattr(face, "ocp_face_id", None),
                    )
                except Exception as e:
                    logger.debug(f"Sweep: Profil-Face Auflösung fehlgeschlagen: {e}")

            if resolved_face_index is not None:
                try:
                    resolved_face_index = int(resolved_face_index)
                    self._sweep_profile_face_index = resolved_face_index
                    profile_data["face_index"] = resolved_face_index
                except Exception:
                    resolved_face_index = None

            if (
                resolved_face is not None
                and target_body is not None
                and hasattr(self, "_find_or_register_face_shape_id")
            ):
                self._sweep_profile_shape_id = self._find_or_register_face_shape_id(
                    target_body,
                    resolved_face,
                    local_index=0,
                )

            has_primary_ref = (
                self._sweep_profile_shape_id is not None
                or self._sweep_profile_face_index is not None
            )
            if resolved_face is not None and not has_primary_ref:
                try:
                    from modeling.geometric_selector import GeometricFaceSelector

                    self._sweep_profile_geometric_selector = GeometricFaceSelector.from_face(resolved_face).to_dict()
                except Exception as e:
                    logger.debug(f"Sweep: Konnte Profil-GeometricSelector nicht erzeugen: {e}")

        self._sweep_profile_data = profile_data
        if hasattr(self.sweep_panel, "set_profile"):
            self.sweep_panel.set_profile(profile_data)
        self._highlight_sweep_profile(profile_data)

        self._sweep_phase = "path"
        if hasattr(self.viewport_3d, "start_sketch_path_mode"):
            self.viewport_3d.start_sketch_path_mode()
        if hasattr(self.viewport_3d, "set_extrude_mode"):
            self.viewport_3d.set_extrude_mode(True, enable_preview=False)
        if hasattr(self, "_update_detector"):
            self._update_detector()

        path_body = None
        if profile_data.get("body_id") and hasattr(self.document, "find_body_by_id"):
            path_body = self.document.find_body_by_id(profile_data["body_id"])
        if path_body is None:
            for candidate in getattr(self.document, "bodies", []):
                if getattr(candidate, "_build123d_solid", None) is not None:
                    path_body = candidate
                    break

        if path_body is not None and hasattr(self.viewport_3d, "set_edge_selection_callbacks"):
            resolver = getattr(self.document, "find_body_by_id", None)
            if resolver is None:
                resolver = lambda bid: next((b for b in getattr(self.document, "bodies", []) if b.id == bid), None)
            self.viewport_3d.set_edge_selection_callbacks(get_body_by_id=resolver)
        if path_body is not None and hasattr(self.viewport_3d, "start_edge_selection_mode"):
            self.viewport_3d.start_edge_selection_mode(path_body.id)

        self.statusBar().showMessage("Sweep: Pfad wählen")

    def _on_edge_selected_for_sweep(self, edges: list):
        """Handler wenn Kanten für Sweep-Pfad selektiert werden."""
        if not self._sweep_mode or self._sweep_phase != 'path':
            return

        if not edges:
            return

        build123d_edges = list(self.viewport_3d.get_selected_edges()) if hasattr(self.viewport_3d, "get_selected_edges") else list(edges)
        edge_indices = self.viewport_3d.get_selected_edge_topology_indices() if hasattr(self.viewport_3d, "get_selected_edge_topology_indices") else []
        edge_indices = edge_indices or []
        path_body_id = getattr(self.viewport_3d, "_edge_selection_body_id", None)

        path_data = {
            "type": "body_edge",
            "body_id": path_body_id,
            "edge_indices": edge_indices,
            "build123d_edges": build123d_edges,
        }

        if not edge_indices:
            try:
                from modeling.geometric_selector import GeometricEdgeSelector

                path_data["path_geometric_selector"] = GeometricEdgeSelector.from_edge(build123d_edges[0]).to_dict()
            except Exception as e:
                logger.debug(f"Sweep: Konnte GeometricEdgeSelector nicht erzeugen: {e}")

        self._sweep_path_data = path_data
        if hasattr(self.sweep_panel, "set_path"):
            self.sweep_panel.set_path(path_data)
        self._highlight_sweep_path(path_data)

        self.statusBar().showMessage("Sweep: Enter zum Bestätigen")

    def _on_sweep_confirmed(self):
        """Handler wenn Sweep bestätigt wird."""
        if not self._sweep_profile_data or not self._sweep_path_data:
            logger.warning("Sweep: Profil und Pfad erforderlich")
            return

        from PySide6.QtWidgets import QMessageBox
        from modeling.cad_tessellator import CADTessellator
        from modeling import SweepFeature, Body
        from gui.commands.feature_commands import AddFeatureCommand, AddBodyCommand

        operation = self.sweep_panel.get_operation() if hasattr(self.sweep_panel, "get_operation") else "New Body"
        is_frenet = self.sweep_panel.is_frenet() if hasattr(self.sweep_panel, "is_frenet") else False
        twist_angle = self.sweep_panel.get_twist_angle() if hasattr(self.sweep_panel, "get_twist_angle") else 0.0
        scale_start = self.sweep_panel.get_scale_start() if hasattr(self.sweep_panel, "get_scale_start") else 1.0
        scale_end = self.sweep_panel.get_scale_end() if hasattr(self.sweep_panel, "get_scale_end") else 1.0

        try:
            feature = SweepFeature(
                profile_data=self._sweep_profile_data,
                path_data=self._sweep_path_data,
                is_frenet=is_frenet,
                operation=operation,
                twist_angle=twist_angle,
                scale_start=scale_start,
                scale_end=scale_end,
            )
            if self._sweep_profile_shape_id is not None:
                feature.profile_shape_id = self._sweep_profile_shape_id
            if self._sweep_profile_face_index is not None:
                feature.profile_face_index = int(self._sweep_profile_face_index)
            if (
                self._sweep_profile_geometric_selector
                and feature.profile_shape_id is None
                and feature.profile_face_index is None
            ):
                feature.profile_geometric_selector = self._sweep_profile_geometric_selector

            path_geo_selector = self._sweep_path_data.get("path_geometric_selector")
            path_edge_indices = self._sweep_path_data.get("edge_indices") or []
            if path_geo_selector and not path_edge_indices:
                feature.path_geometric_selector = path_geo_selector

            is_new_body = operation == "New Body" or not getattr(self.document, "bodies", [])
            if is_new_body:
                target_body = Body(name=f"Sweep_{len(getattr(self.document, 'bodies', [])) + 1}", document=self.document)
                target_body.features.append(feature)
                CADTessellator.notify_body_changed()
                target_body._rebuild()

                if not getattr(target_body, "_build123d_solid", None):
                    raise ValueError("Sweep konnte keinen gültigen Solid erzeugen")

                cmd = AddBodyCommand(self.document, target_body, self, description=f"Sweep ({operation})")
                self.undo_stack.push(cmd)
            else:
                target_body = self._get_active_body()
                if target_body is None:
                    target_body = self.document.bodies[0] if getattr(self.document, "bodies", []) else None
                if target_body is None:
                    raise ValueError("Sweep-Zielkörper konnte nicht bestimmt werden")

                cmd = AddFeatureCommand(target_body, feature, self, description=f"Sweep ({operation})")
                self.undo_stack.push(cmd)

                if not getattr(target_body, "_build123d_solid", None):
                    self.undo_stack.undo()
                    raise ValueError("Sweep konnte keinen gültigen Solid erzeugen")

                if hasattr(self, "_update_body_from_build123d"):
                    self._update_body_from_build123d(target_body, target_body._build123d_solid)

            self._stop_sweep_mode()
            if hasattr(self, "browser"):
                self.browser.refresh()
            if hasattr(self, "_update_viewport_all"):
                self._update_viewport_all()

            logger.success("Sweep erstellt")
        except Exception as e:
            logger.error(f"Sweep fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Fehler", f"Sweep fehlgeschlagen:\n{str(e)}")

    def _on_sweep_cancelled(self):
        """Bricht die Sweep-Operation ab."""
        self._stop_sweep_mode()

    def _on_sweep_profile_cleared(self):
        """Handler wenn Profil-Auswahl entfernt wird."""
        self._sweep_profile_data = None
        self._sweep_phase = 'profile'
        self._clear_sweep_highlight('profile')
        if hasattr(self.sweep_panel, "clear_profile"):
            self.sweep_panel.clear_profile()

    def _on_sweep_path_cleared(self):
        """Handler wenn Pfad-Auswahl entfernt wird."""
        self._sweep_path_data = None
        self._sweep_phase = 'path' if self._sweep_profile_data else 'profile'
        self._clear_sweep_highlight('path')
        if hasattr(self.sweep_panel, "clear_path"):
            self.sweep_panel.clear_path()

    def _clear_sweep_highlight(self, element_type: str, render: bool = True):
        """Entfernt das Sweep-Highlight für Profil oder Pfad."""
        if hasattr(self.viewport_3d, 'clear_sweep_highlight'):
            self.viewport_3d.clear_sweep_highlight(element_type, render)

    def _highlight_sweep_profile(self, profile_data: dict):
        """Highlightet das ausgewählte Sweep-Profil im Viewport."""
        if hasattr(self.viewport_3d, 'highlight_sweep_profile'):
            self.viewport_3d.highlight_sweep_profile(profile_data)

    def _highlight_sweep_path(self, path_data: dict):
        """Highlightet den ausgewählten Sweep-Pfad im Viewport."""
        if hasattr(self.viewport_3d, 'highlight_sweep_path'):
            self.viewport_3d.highlight_sweep_path(path_data)

    def _on_sketch_path_clicked(self, sketch_id: str, geom_type: str, index: int):
        """Handler wenn Sketch-Element für Sweep-Pfad geklickt wird."""
        if not self._sweep_mode or self._sweep_phase != 'path':
            return

        sketches = self.document.get_all_sketches() if hasattr(self.document, "get_all_sketches") else getattr(self.document, "sketches", [])
        sketch = next((s for s in sketches if s.id == sketch_id), None)
        if not sketch:
            return

        geom = None
        if geom_type == "line" and 0 <= index < len(getattr(sketch, "lines", [])):
            geom = sketch.lines[index]
        elif geom_type == "arc" and 0 <= index < len(getattr(sketch, "arcs", [])):
            geom = sketch.arcs[index]
        elif geom_type == "spline" and 0 <= index < len(getattr(sketch, "splines", [])):
            geom = sketch.splines[index]
        if geom is None:
            return

        path_data = {
            "type": "sketch_edge",
            "geometry_type": geom_type,
            "sketch_id": sketch_id,
            "index": index,
            "plane_origin": getattr(sketch, "plane_origin", (0, 0, 0)),
            "plane_normal": getattr(sketch, "plane_normal", (0, 0, 1)),
            "plane_x": getattr(sketch, "plane_x_dir", (1, 0, 0)),
            "plane_y": getattr(sketch, "plane_y_dir", (0, 1, 0)),
        }

        if geom_type == "arc":
            center = getattr(geom, "center", None)
            if center is not None:
                path_data["center"] = (center.x, center.y)
            path_data["radius"] = getattr(geom, "radius", 1.0)
            path_data["start_angle"] = getattr(geom, "start_angle", 0.0)
            path_data["end_angle"] = getattr(geom, "end_angle", 90.0)
        elif geom_type == "line":
            path_data["start"] = (geom.start.x, geom.start.y)
            path_data["end"] = (geom.end.x, geom.end.y)
        elif geom_type == "spline":
            ctrl_pts = getattr(geom, "control_points", None) or getattr(geom, "points", None) or []
            if ctrl_pts and hasattr(ctrl_pts[0], "x") and hasattr(ctrl_pts[0], "y"):
                path_data["control_points"] = [(p.x, p.y) for p in ctrl_pts]
            else:
                path_data["control_points"] = ctrl_pts

        self._sweep_path_data = path_data
        if hasattr(self.sweep_panel, "set_path"):
            self.sweep_panel.set_path(path_data)
        self._highlight_sweep_path(path_data)
        self.statusBar().showMessage("Sweep: Enter zum Bestätigen")

    def _on_sweep_sketch_path_requested(self):
        """Handler wenn User Sketch-Pfad auswählen will."""
        from i18n import tr

        if hasattr(self.viewport_3d, 'start_sketch_path_mode'):
            self.viewport_3d.start_sketch_path_mode()
        self.statusBar().showMessage(tr("Klicke auf Sketch-Element für Pfad"))
        # Viewport handles the actual picking

    def _stop_sweep_mode(self):
        """Beendet den Sweep-Modus und räumt auf."""
        self._sweep_mode = False
        self._sweep_phase = None
        self._sweep_profile_data = None
        self._sweep_path_data = None
        self._sweep_profile_shape_id = None
        self._sweep_profile_face_index = None
        self._sweep_profile_geometric_selector = None
        if hasattr(self.viewport_3d, 'stop_sketch_path_mode'):
            self.viewport_3d.stop_sketch_path_mode()
        if hasattr(self.viewport_3d, 'stop_edge_selection_mode'):
            self.viewport_3d.stop_edge_selection_mode()
        if hasattr(self.viewport_3d, 'set_sweep_mode'):
            self.viewport_3d.set_sweep_mode(False)
        if hasattr(self.viewport_3d, 'set_extrude_mode'):
            self.viewport_3d.set_extrude_mode(False)
        self.sweep_panel.hide()
        self._clear_sweep_highlight('profile', render=False)
        self._clear_sweep_highlight('path', render=False)
        self.statusBar().clearMessage()
    
    # =========================================================================
    # Loft Operations
    # =========================================================================
    
    def _on_loft_add_profile(self):
        """Handler wenn weiteres Loft-Profil hinzugefügt werden soll."""
        from i18n import tr
        
        self.statusBar().showMessage(tr("Wähle nächstes Profil"))
        # Viewport handles the actual picking

    def _on_face_selected_for_loft(self, face_id):
        """Handler wenn eine Fläche für Loft selektiert wird."""
        if not self._loft_mode:
            return

        face = next((f for f in self.viewport_3d.detector.selection_faces if f.id == face_id), None)
        if not face:
            return

        profile_data = {
            "type": face.domain_type,
            "face_id": face_id,
            "plane_origin": face.plane_origin,
            "plane_normal": face.plane_normal,
            "plane_x": face.plane_x,
            "plane_y": face.plane_y,
            "shapely_poly": face.shapely_poly,
        }
        if face.domain_type == "body_face":
            profile_data["body_id"] = face.owner_id
            profile_data["ocp_face_id"] = getattr(face, "ocp_face_id", None)

        self._loft_profiles.append(profile_data)

        if hasattr(self.loft_panel, "add_profile"):
            self.loft_panel.add_profile(profile_data)
        self._highlight_loft_profile(profile_data, len(self._loft_profiles) - 1)

        if len(self._loft_profiles) >= 2:
            self._update_loft_preview()

    def _on_loft_confirmed(self):
        """Handler wenn Loft bestätigt wird."""
        profiles = self.loft_panel.get_profiles() if hasattr(self.loft_panel, "get_profiles") else list(self._loft_profiles)
        if len(profiles) < 2:
            logger.warning("Loft: Mindestens 2 Profile erforderlich")
            return

        from PySide6.QtWidgets import QMessageBox
        from modeling.cad_tessellator import CADTessellator
        from modeling import LoftFeature, Body
        from gui.commands.feature_commands import AddFeatureCommand, AddBodyCommand

        operation = self.loft_panel.get_operation() if hasattr(self.loft_panel, "get_operation") else "New Body"
        ruled = self.loft_panel.is_ruled() if hasattr(self.loft_panel, "is_ruled") else False

        try:
            profiles_sorted = sorted(
                profiles,
                key=lambda p: (
                    p.get("plane_origin", (0, 0, 0))[2]
                    if isinstance(p.get("plane_origin", (0, 0, 0)), (list, tuple))
                    and len(p.get("plane_origin", (0, 0, 0))) >= 3
                    else 0
                ),
            )

            feature = LoftFeature(
                profile_data=profiles_sorted,
                operation=operation,
                ruled=ruled,
            )

            is_new_body = operation == "New Body" or not getattr(self.document, "bodies", [])
            if is_new_body:
                target_body = Body(name=f"Loft_{len(getattr(self.document, 'bodies', [])) + 1}", document=self.document)
                target_body.features.append(feature)
                CADTessellator.notify_body_changed()
                target_body._rebuild()

                if not getattr(target_body, "_build123d_solid", None):
                    raise ValueError("Loft konnte keinen gültigen Solid erzeugen")

                cmd = AddBodyCommand(self.document, target_body, self, description=f"Loft ({operation})")
                self.undo_stack.push(cmd)
            else:
                target_body = self._get_active_body()
                if target_body is None:
                    target_body = self.document.bodies[0] if getattr(self.document, "bodies", []) else None
                if target_body is None:
                    raise ValueError("Loft-Zielkörper konnte nicht bestimmt werden")

                cmd = AddFeatureCommand(target_body, feature, self, description=f"Loft ({operation})")
                self.undo_stack.push(cmd)

                if not getattr(target_body, "_build123d_solid", None):
                    self.undo_stack.undo()
                    raise ValueError("Loft konnte keinen gültigen Solid erzeugen")

                if hasattr(self, "_update_body_from_build123d"):
                    self._update_body_from_build123d(target_body, target_body._build123d_solid)

            self._stop_loft_mode()
            if hasattr(self, "browser"):
                self.browser.refresh()
            if hasattr(self, "_update_viewport_all"):
                self._update_viewport_all()

            logger.success("Loft erstellt")
        except Exception as e:
            logger.error(f"Loft fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Fehler", f"Loft fehlgeschlagen:\n{str(e)}")

    def _on_loft_cancelled(self):
        """Bricht die Loft-Operation ab."""
        self._stop_loft_mode()

    def _stop_loft_mode(self):
        """Beendet den Loft-Modus und räumt auf."""
        self._loft_mode = False
        self._loft_profiles = []
        if hasattr(self.viewport_3d, 'set_loft_mode'):
            self.viewport_3d.set_loft_mode(False)
        if hasattr(self.viewport_3d, 'set_extrude_mode'):
            self.viewport_3d.set_extrude_mode(False)
        self.loft_panel.hide()
        self._clear_loft_highlights()
        self._clear_loft_preview()
        self.statusBar().clearMessage()

    def _clear_loft_highlights(self):
        """Entfernt alle Loft-Profile-Highlights."""
        if hasattr(self.viewport_3d, 'clear_loft_highlights'):
            self.viewport_3d.clear_loft_highlights()

    def _clear_loft_preview(self):
        """Entfernt die Loft-Preview."""
        if hasattr(self.viewport_3d, 'clear_loft_preview'):
            self.viewport_3d.clear_loft_preview()

    def _highlight_loft_profile(self, profile_data: dict, profile_index: int):
        """Highlightet ein Loft-Profil im Viewport."""
        if hasattr(self.viewport_3d, 'highlight_loft_profile'):
            self.viewport_3d.highlight_loft_profile(profile_data, profile_index)

    def _update_loft_preview(self):
        """Zeigt eine Preview des Loft-Ergebnisses."""
        if hasattr(self.viewport_3d, 'update_loft_preview'):
            self.viewport_3d.update_loft_preview(self._loft_profiles)
    
    # =========================================================================
    # BREP Cleanup Operations
    # =========================================================================
    
    def _toggle_brep_cleanup(self):
        """Startet BREP Cleanup Modus."""
        from i18n import tr
        
        self._pending_brep_cleanup_mode = True
        self.viewport_3d.setCursor(Qt.CrossCursor)
        self.statusBar().showMessage(tr("Wähle Body für BREP Cleanup"))
        logger.info("BREP Cleanup: Klicke auf einen Body")

    def _on_body_clicked_for_brep_cleanup(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body angeklickt wird."""
        self._pending_brep_cleanup_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        
        body = self.document.find_body_by_id(body_id)
        if body:
            self._activate_brep_cleanup_for_body(body)

    def _activate_brep_cleanup_for_body(self, body):
        """Startet BREP Cleanup fuer einen Body."""
        from modeling.brep_face_analyzer import BRepFaceAnalyzer
        
        self._brep_cleanup_body = body
        
        # Analyze faces
        if body._build123d_solid:
            analyzer = BRepFaceAnalyzer()
            result = analyzer.analyze(body._build123d_solid)
            # Show results in panel
            logger.info(f"BREP Cleanup: {len(result.features)} Features erkannt")

    def _close_brep_cleanup(self):
        """Schliesst BREP Cleanup Modus."""
        self._brep_cleanup_body = None
        self._pending_brep_cleanup_mode = False

    def _on_brep_cleanup_feature_selected(self, feature_idx: int, additive: bool = False):
        """Feature im Panel ausgewaehlt."""
        pass

    def _on_brep_cleanup_merge(self):
        """Merge-Button geklickt."""
        logger.info("BREP Merge ausgeführt")

    def _on_brep_cleanup_merge_all(self):
        """Alle-Merge-Button geklickt."""
        logger.info("BREP Merge All ausgeführt")
    
    # =========================================================================
    # TNP Operations
    # =========================================================================
    
    def _on_tnp_body_pick_requested(self):
        """User hat den Pick-Button im TNP-Panel geklickt."""
        self._pending_tnp_pick_mode = True
        self.viewport_3d.setCursor(Qt.CrossCursor)
        self.statusBar().showMessage("Wähle Body für TNP-Analyse")

    def _on_body_clicked_for_tnp(self, body_id: str):
        """Body wurde im Viewport für TNP-Panel ausgewählt."""
        self._pending_tnp_pick_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        
        body = self.document.find_body_by_id(body_id)
        if body:
            self._update_tnp_stats(body)

    def _solid_signature_safe(self, body) -> dict:
        """Erzeugt einen Geometry-Fingerprint (volume, faces, edges) oder None."""
        try:
            if not body or not getattr(body, '_build123d_solid', None):
                return None
            solid = body._build123d_solid
            return {
                'volume': float(solid.volume),
                'faces': len(list(solid.faces())),
                'edges': len(list(solid.edges())),
            }
        except Exception:
            return None

    def _update_tnp_stats(self, body=None):
        """Aktualisiert TNP-Statistiken im Panel."""
        if not hasattr(self, 'tnp_stats_panel'):
            return
        
        if body:
            signature = self._solid_signature_safe(body)
            if signature:
                self.tnp_stats_panel.set_body_stats(
                    body.name,
                    signature['faces'],
                    signature['edges'],
                    signature['volume']
                )
    
    # =========================================================================
    # Component Operations
    # =========================================================================
    
    def _on_component_activated(self, component):
        """Handler wenn eine Component aktiviert wird."""
        logger.info(f"Component aktiviert: {component.name}")
        self.document.set_active_component(component)
        self.browser.refresh()
        self._update_viewport_all()

    def _on_component_created(self, parent_component, new_component):
        """Handler wenn eine neue Component erstellt wird."""
        logger.info(f"Component erstellt: {new_component.name}")
        self.browser.refresh()

    def _on_component_deleted(self, component):
        """Handler wenn eine Component gelöscht wird."""
        logger.info(f"Component gelöscht: {component.name}")
        self.browser.refresh()
        self._update_viewport_all()

    def _on_component_renamed(self, component, new_name):
        """Handler wenn eine Component umbenannt wird."""
        logger.info(f"Component umbenannt: {new_name}")
        self.browser.refresh()

    def _on_component_vis_changed(self, component_id: str, visible: bool):
        """Handler wenn Component-Sichtbarkeit geändert wird."""
        self._trigger_viewport_update()

    def _on_body_moved_to_component(self, body, source_comp, target_comp):
        """Handler wenn ein Body zwischen Components verschoben wird."""
        logger.info(f"Body '{body.name}' verschoben")
        self.browser.refresh()

    def _on_sketch_moved_to_component(self, sketch, source_comp, target_comp):
        """Handler wenn ein Sketch zwischen Components verschoben wird."""
        logger.info(f"Sketch '{sketch.name}' verschoben")
        self.browser.refresh()
    
    # =========================================================================
    # Transform Operations
    # =========================================================================
    
    def _move_body(self):
        """Startet Move-Modus für ausgewählten Body."""
        body = self._get_active_body()
        if body:
            self._show_transform_ui(body.id, body.name, 'move')

    def _scale_body(self):
        """Startet Scale-Modus für ausgewählten Body."""
        body = self._get_active_body()
        if body:
            self._show_transform_ui(body.id, body.name, 'scale')

    def _rotate_body(self):
        """Startet Rotate-Modus für ausgewählten Body."""
        body = self._get_active_body()
        if body:
            self._show_transform_ui(body.id, body.name, 'rotate')

    def _clone_body_feature_history(self, source_body, target_body) -> int:
        """
        Klont die Feature-Historie von source_body nach target_body.

        Shape-spezifische Referenzen werden geleert und Dependencies per ID remapped.
        """
        import copy
        import uuid

        source_features = list(getattr(source_body, "features", []) or [])
        if not source_features:
            return 0

        id_map = {}
        cloned_features = []

        for feature in source_features:
            try:
                cloned = copy.deepcopy(feature)
            except Exception as e:
                logger.debug(f"Feature-Kopie fehlgeschlagen, überspringe: {e}")
                continue

            old_id = getattr(cloned, "id", None)
            new_id = str(uuid.uuid4())[:8]
            if old_id:
                id_map[old_id] = new_id
            cloned.id = new_id

            if hasattr(cloned, "status"):
                cloned.status = "OK"
            if hasattr(cloned, "status_message"):
                cloned.status_message = ""
            if hasattr(cloned, "status_details"):
                cloned.status_details = {}

            # Shape-Referenzen nicht 1:1 übernehmen (werden bei Rebuild neu aufgelöst).
            for attr_name in list(vars(cloned).keys()):
                if attr_name.endswith("_shape_id"):
                    setattr(cloned, attr_name, None)
                elif attr_name.endswith("_shape_ids"):
                    value = getattr(cloned, attr_name, None)
                    if isinstance(value, list):
                        setattr(cloned, attr_name, [])
                    elif value is not None:
                        setattr(cloned, attr_name, None)

            cloned_features.append(cloned)

        for feature in cloned_features:
            dep = getattr(feature, "depends_on_feature_id", None)
            if dep in id_map:
                feature.depends_on_feature_id = id_map[dep]
            target_body.add_feature(feature, rebuild=False)

        return len(cloned_features)

    def _copy_body(self):
        """Kopiert den aktiven Body als neuen Body."""
        body = self._get_active_body()
        if not body:
            return
        
        from modeling import Body
        from modeling.cad_tessellator import CADTessellator
        
        new_body = Body(name=f"{body.name}_copy", document=self.document)
        
        if hasattr(body, '_build123d_solid') and body._build123d_solid:
            from build123d import Location
            new_body._build123d_solid = body._build123d_solid.moved(Location((0, 0, 0)))
            CADTessellator.notify_body_changed()
            self._update_body_from_build123d(new_body, new_body._build123d_solid)
        elif getattr(body, "vtk_mesh", None) is not None:
            try:
                new_body.vtk_mesh = body.vtk_mesh.copy(deep=True)
            except Exception:
                pass

        self._clone_body_feature_history(body, new_body)
        
        self.document.add_body(new_body)
        self.browser.refresh()
        self._update_viewport_all()
        logger.success(f"Body kopiert: {new_body.name} ({len(new_body.features)} Features)")

    def _mirror_body(self):
        """Startet Mirror-Dialog für ausgewählten Body."""
        body = self._get_active_body()
        if body:
            self._show_mirror_dialog(body.id)
    
    # =========================================================================
    # Copy Operations
    # =========================================================================
    
    def _on_body_copy_requested(self, body_id: str, mode: str, data):
        """
        Handler für Copy+Transform (Shift+Drag).
        Kopiert den Body und wendet dann den Transform an.
        """
        logger.debug(f"Copy requested: {mode} on {body_id}")
        logger.debug(f"   data: {data}")
        
        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.error(f"Body {body_id} nicht gefunden für Copy")
            return
        
        try:
            from build123d import Location, Axis
            from modeling.cad_tessellator import CADTessellator
            from modeling import Body
            
            new_body = Body(name=f"{body.name}_copy", document=self.document)
            
            if hasattr(body, '_build123d_solid') and body._build123d_solid:
                new_body._build123d_solid = body._build123d_solid.moved(Location((0, 0, 0)))
                CADTessellator.notify_body_changed()
                
                if mode == "move":
                    if isinstance(data, list):
                        dx, dy, dz = data
                    else:
                        dx, dy, dz = data.get("translation", [0, 0, 0])
                    new_body._build123d_solid = new_body._build123d_solid.moved(Location((dx, dy, dz)))
                    logger.success(f"Copy+Move ({dx:.2f}, {dy:.2f}, {dz:.2f}) → {new_body.name}")
                    
                elif mode == "rotate":
                    if isinstance(data, dict):
                        axis_name = data.get("axis", "Z")
                        angle = data.get("angle", 0)
                    else:
                        axis_name, angle = "Z", 0
                    axis_map = {"X": Axis.X, "Y": Axis.Y, "Z": Axis.Z}
                    axis = axis_map.get(axis_name, Axis.Z)
                    new_body._build123d_solid = new_body._build123d_solid.rotated(axis, angle)
                    logger.success(f"Copy+Rotate ({axis_name}, {angle:.1f}°) → {new_body.name}")
                    
                elif mode == "scale":
                    if isinstance(data, dict):
                        factor = data.get("factor", 1.0)
                    else:
                        factor = 1.0
                    new_body._build123d_solid = new_body._build123d_solid.scaled(factor)
                    logger.success(f"Copy+Scale ({factor:.2f}) → {new_body.name}")

                # Feature-Historie mitkopieren (inkl. remap von Feature-IDs).
                self._clone_body_feature_history(body, new_body)
                
                self._update_body_from_build123d(new_body, new_body._build123d_solid)
                self.document.add_body(new_body, set_active=False)
                self.browser.refresh()
                
                if hasattr(self.viewport_3d, 'show_transform_gizmo'):
                    self.viewport_3d.show_transform_gizmo(new_body.id)
                    
        except Exception as e:
            logger.exception(f"Copy+Transform Error: {e}")
    
    def _on_body_mirror_requested(self, body_id: str, plane: str):
        """Handler für Mirror-Operation."""
        logger.debug(f"Mirror requested: {plane} auf {body_id}")
        
        body = next((b for b in self.document.bodies if b.id == body_id), None)
        if not body:
            logger.error(f"Body {body_id} nicht gefunden für Mirror")
            return
        
        try:
            from build123d import Plane as B123Plane, mirror as b123d_mirror
            from modeling.cad_tessellator import CADTessellator
            
            if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
                logger.error("Build123d nicht verfügbar für Mirror")
                return
            
            CADTessellator.notify_body_changed()
            
            plane_map = {"XY": B123Plane.XY, "XZ": B123Plane.XZ, "YZ": B123Plane.YZ}
            mirror_plane = plane_map.get(plane.upper(), B123Plane.XY)
            
            body._build123d_solid = b123d_mirror(body._build123d_solid, about=mirror_plane)
            logger.success(f"Mirror ({plane}) auf {body.name}")
            
            self._update_body_from_build123d(body, body._build123d_solid)
            
            if hasattr(self.viewport_3d, 'show_transform_gizmo'):
                self.viewport_3d.show_transform_gizmo(body_id)
            self.browser.refresh()
            
        except Exception as e:
            logger.exception(f"Mirror Error: {e}")
    
    # =========================================================================
    # Body Operations
    # =========================================================================
    
    def _on_background_clicked(self):
        """Handler for background click in Viewport -> Deselect Body"""
        if hasattr(self.viewport_3d, 'clear_selection'):
            self.viewport_3d.clear_selection()

    def _on_create_sketch_requested(self, face_id: int):
        """Handler for Context Menu -> Create Sketch"""
        # Create sketch on clicked face
        logger.info(f"Create Sketch on face {face_id}")

    def _on_batch_retry_rebuild(self, problem_features):
        """Handler für Batch-Rebuild von Problem-Features."""
        logger.info(f"Batch Rebuild: {len(problem_features)} Features")
        for feature, body in problem_features:
            try:
                feature._rebuild(body)
                logger.success(f"Feature '{feature.name}' neu erstellt")
            except Exception as e:
                logger.error(f"Rebuild fehlgeschlagen: {e}")
        
        self.browser.refresh()
        self._update_viewport_all()

    def _on_batch_open_diagnostics(self, problem_features):
        """Handler für Batch-Diagnostics."""
        logger.info(f"Diagnostics für {len(problem_features)} Features")

    def _on_batch_isolate_bodies(self, bodies):
        """Handler für Body-Isolation."""
        # Hide all bodies except selected
        for body in self.document.get_all_bodies():
            visible = body in bodies
            self.viewport_3d.set_body_visible(body.id, visible)
        self._trigger_viewport_update()

    def _on_batch_unhide_bodies(self, bodies):
        """Handler für Batch-Unhide."""
        for body in bodies:
            self.viewport_3d.set_body_visible(body.id, True)
        self._trigger_viewport_update()

    def _on_batch_focus_features(self, feature_body_pairs):
        """Handler für Feature-Focus."""
        logger.info(f"Focus auf {len(feature_body_pairs)} Features")

    def _on_recovery_action_requested(self, action, feature):
        """Handler für Recovery-Actions."""
        logger.info(f"Recovery action '{action}' für Feature '{feature.name}'")

    def _on_edit_feature_requested(self, feature):
        """Handler für Edit Feature Request."""
        body = self._get_active_body()
        if body:
            self._edit_parametric_feature(feature, body, 'unknown')

    def _on_rebuild_feature_requested(self, feature):
        """Handler für Rebuild Feature Request."""
        body = self._get_active_body()
        if body and hasattr(feature, '_rebuild'):
            try:
                feature._rebuild(body)
                self._update_body_from_build123d(body, body._build123d_solid)
                self.browser.refresh()
                self._update_viewport_all()
                logger.success(f"Feature '{feature.name}' neu erstellt")
            except Exception as e:
                logger.error(f"Rebuild fehlgeschlagen: {e}")

    def _on_delete_feature_requested(self, feature):
        """Handler für Delete Feature Request."""
        body = self._get_active_body()
        if body:
            self._on_feature_deleted(feature, body)

    def _on_highlight_edges_requested(self, edge_indices):
        """Handler für Edge-Highlight."""
        if hasattr(self.viewport_3d, 'highlight_edges'):
            self.viewport_3d.highlight_edges(edge_indices)

    def _on_projection_preview_requested(self, edge_tuple, projection_type):
        """Handler für Projection-Preview."""
        if hasattr(self.viewport_3d, 'show_projection_preview'):
            self.viewport_3d.show_projection_preview(edge_tuple, projection_type)

    def _on_projection_preview_cleared(self):
        """Handler wenn Projection-Preview gelöscht wird."""
        if hasattr(self.viewport_3d, 'clear_projection_preview'):
            self.viewport_3d.clear_projection_preview()
    
    # =========================================================================
    # Viewport Body Click Handler
    # =========================================================================
    
    def _on_viewport_body_clicked(self, body_id: str):
        """
        Handler für Body-Klick im Viewport.
        Unterstützt verschiedene Pending-Modi.
        """
        from PySide6.QtCore import Qt
        from i18n import tr
        
        # Prüfe auf verschiedene Pending-Modi
        if getattr(self, '_pending_split_mode', False):
            self._pending_split_mode = False
            self.viewport_3d.setCursor(Qt.ArrowCursor)
            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(False)
            self._on_split_body_clicked(body_id)
            return

        if getattr(self, '_pending_fillet_mode', False) or getattr(self, '_pending_chamfer_mode', False):
            self._on_body_clicked_for_fillet(body_id)
            return

        if getattr(self, '_pending_thread_mode', False):
            self._on_body_clicked_for_thread(body_id)
            return

        if getattr(self, '_pending_brep_cleanup_mode', False):
            self._on_body_clicked_for_brep_cleanup(body_id)
            return

        if getattr(self, '_pending_shell_mode', False):
            self._on_body_clicked_for_shell(body_id)
            return

        if getattr(self, '_pending_texture_mode', False):
            self._on_body_clicked_for_texture(body_id)
            return

        if getattr(self, '_pending_mesh_convert_mode', False):
            self._on_body_clicked_for_mesh_convert(body_id)
            return

        if getattr(self, '_pending_pattern_mode', False):
            self._on_body_clicked_for_pattern(body_id)
            return

        if getattr(self, '_pending_lattice_mode', False):
            self._on_body_clicked_for_lattice(body_id)
            return

        if getattr(self, '_pending_nsided_patch_mode', False):
            self._on_body_clicked_for_nsided_patch(body_id)
            return

        if getattr(self, '_pending_wall_thickness_mode', False):
            self._on_body_clicked_for_wall_thickness(body_id)
            return

        if getattr(self, '_pending_tnp_pick_mode', False):
            self._on_body_clicked_for_tnp(body_id)
            return

        # Transform Pending Mode
        if not getattr(self, '_pending_transform_mode', None):
            return

        body = self.document.find_body_by_id(body_id)
        if not body:
            logger.warning(f"Body {body_id} nicht gefunden")
            return

        mode = self._pending_transform_mode
        self._pending_transform_mode = None
        self.viewport_3d.setCursor(Qt.ArrowCursor)

        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        # Point-to-Point Move
        if mode == "point_to_point":
            if hasattr(self.viewport_3d, 'start_point_to_point_mode'):
                self.viewport_3d.start_point_to_point_mode(body.id)
                logger.success(f"Point-to-Point Move für {body.name}: Wähle Start-Punkt, dann Ziel-Punkt")
                if hasattr(self, "p2p_panel"):
                    self._p2p_body_id = body.id
                    self.p2p_panel.reset()
                    self.p2p_panel.set_body(body.name)
                    self.p2p_panel.set_status(tr("Pick start point"))
                    self.p2p_panel.show_at(self.viewport_3d)
                self._p2p_repick_body = False
            return

        # Normaler Transform-Modus
        self._transform_mode = mode
        self._active_transform_body = body
        self._show_transform_ui(body.id, body.name, mode)
        logger.success(f"{mode.capitalize()}: {body.name} - Ziehe am Gizmo oder Tab für Eingabe")
    
    # =========================================================================
    # Selection Mode
    # =========================================================================
    
    def set_selection_mode(self, mode):
        """Setzt den Selection-Modus."""
        from gui.geometry_detector import GeometryDetector
        
        if hasattr(self.viewport_3d, 'set_selection_mode'):
            self.viewport_3d.set_selection_mode(mode)


# =============================================================================
# Backward Compatibility Exports
# =============================================================================

__all__ = [
    'FeatureDialogsMixin',
]
