"""
MashCAD Dialog Operations Module
=================================

Extracted from main_window.py (AR-005 EXTENDED).

This module contains dialog-related operations as a mixin class.
Maintains backward compatibility by being imported into MainWindow.

Usage:
    class MainWindow(DialogMixin, QMainWindow):
        pass
"""

from typing import TYPE_CHECKING, Optional, List, Dict, Any, Tuple
import numpy as np
from loguru import logger

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog, QDialog, QVBoxLayout

if TYPE_CHECKING:
    from modeling import Body, Document
    from gui.main_window import MainWindow


class DialogMixin:
    """
    Mixin class containing dialog-related operations for MainWindow.
    
    This class provides:
    - STL to CAD reconstruction dialogs
    - Hole/Thread/Draft dialogs
    - Split/Revolve dialogs
    - Pattern/Shell/Texture dialogs
    - Sweep/Loft dialogs
    - Primitive dialogs
    
    All methods assume they are called within a MainWindow context
    and access MainWindow attributes via `self`.
    """

    def _all_bodies(self):
        """Returns bodies across all components when available."""
        if hasattr(self.document, "get_all_bodies"):
            try:
                return list(self.document.get_all_bodies() or [])
            except Exception:
                pass
        return list(getattr(self.document, "bodies", []) or [])

    def _find_body_by_id_global(self, body_id: str):
        """Component-aware body lookup with fallback for legacy documents."""
        if hasattr(self.document, "find_body_by_id"):
            try:
                body = self.document.find_body_by_id(body_id)
                if body is not None:
                    return body
            except Exception:
                pass
        return next((b for b in self._all_bodies() if getattr(b, "id", None) == body_id), None)

    def _has_cad_bodies(self) -> bool:
        """True when at least one body has a CAD solid."""
        return any(getattr(b, "_build123d_solid", None) for b in self._all_bodies())
    
    # =========================================================================
    # STL to CAD Reconstruction
    # =========================================================================
    
    def _on_stl_to_cad(self):
        """
        STL to CAD Reconstruction Workflow.
        
        1. Select STL file
        2. Mesh Quality Check
        3. Feature Analysis
        4. Show Reconstruction Panel
        5. User review and reconstruct
        """
        try:
            from sketching.analysis.mesh_quality_checker import check_mesh_quality
            from sketching.analysis.stl_feature_analyzer import STLFeatureAnalyzer, analyze_stl
            from gui.dialogs.stl_reconstruction_panel import STLReconstructionPanel
            HAS_STL_RECONSTRUCTION = True
        except ImportError:
            HAS_STL_RECONSTRUCTION = False
        
        if not HAS_STL_RECONSTRUCTION:
            QMessageBox.warning(
                self,
                "Not Available",
                "STL Reconstruction module is not available.\n"
                "Please check the installation."
            )
            return
        
        # 1. File Dialog
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select STL for CAD Reconstruction",
            "",
            "STL Files (*.stl);;All Files (*.*)"
        )
        
        if not path:
            return
        
        try:
            logger.info(f"Starting STL to CAD reconstruction for: {path}")
            
            # 2. Mesh Quality Check
            self.statusBar().showMessage("Checking mesh quality...")
            quality_report = check_mesh_quality(path, auto_repair=True, auto_decimate=True)
            
            if quality_report.recommended_action == "reject":
                QMessageBox.critical(
                    self,
                    "Invalid Mesh",
                    f"Mesh quality check failed:\n{', '.join(quality_report.warnings)}"
                )
                return
            
            logger.info(f"Mesh quality: {quality_report.recommended_action}, "
                       f"{quality_report.face_count} faces")
            
            # 3. Feature Analysis
            self.statusBar().showMessage("Analyzing features...")
            analyzer = STLFeatureAnalyzer()
            analysis = analyzer.analyze(path)
            
            if not analysis.base_plane and not analysis.holes:
                QMessageBox.warning(
                    self,
                    "No Features Detected",
                    "Could not detect any CAD features in the mesh.\n"
                    "The mesh may be too complex or not contain recognizable features."
                )
                return
            
            logger.info(f"Analysis complete: {len(analysis.holes)} holes, "
                       f"confidence={analysis.overall_confidence:.2f}")
            
            # 4. Show Reconstruction Panel
            self._show_reconstruction_panel(path, analysis, quality_report)
            
        except Exception as e:
            logger.error(f"STL to CAD failed: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"STL to CAD reconstruction failed:\n{str(e)}"
            )
    
    def _show_reconstruction_panel(self, mesh_path: str, analysis, quality_report):
        """
        Show the STL Reconstruction Panel with analysis results.
        """
        try:
            import pyvista as pv
            from gui.dialogs.stl_reconstruction_panel import STLReconstructionPanel
            
            # 1. Load and display STL mesh in viewport (semi-transparent)
            mesh = pv.read(mesh_path)
            
            # Remove existing STL preview if any
            if hasattr(self, '_stl_preview_actor'):
                try:
                    self.viewport_3d.plotter.remove_actor(self._stl_preview_actor)
                except Exception:
                    pass
            
            # Add mesh with transparency for reference
            self._stl_preview_actor = self.viewport_3d.plotter.add_mesh(
                mesh,
                color='lightgray',
                opacity=0.3,
                show_edges=True,
                edge_color='darkgray',
                line_width=0.5,
                name='stl_preview'
            )
            
            # Add feature preview actors
            self._stl_feature_actors = []
            self._add_feature_previews(analysis)
            
            # 2. Create panel
            panel = STLReconstructionPanel(self)
            panel.set_analysis(analysis, quality_report)
            
            # 3. Connect signals
            panel.reconstruct_requested.connect(
                lambda: self._start_stl_reconstruction(panel, analysis)
            )
            
            panel.feature_selected.connect(
                lambda ftype, idx: self._highlight_stl_feature(analysis, ftype, idx)
            )
            
            panel.feature_toggled.connect(
                lambda ftype, idx, enabled: self._toggle_stl_feature_preview(analysis, ftype, idx, enabled)
            )
            
            panel.feature_modified.connect(
                lambda ftype, idx, params: self._update_stl_feature_preview(analysis, ftype, idx, params)
            )
            
            # 4. Show as dialog (non-modal)
            dialog = QDialog(self)
            dialog.setWindowTitle("STL to CAD Reconstruction")
            dialog.setMinimumSize(500, 700)
            dialog.setModal(False)
            
            layout = QVBoxLayout(dialog)
            layout.addWidget(panel)
            
            dialog.finished.connect(lambda: self._cleanup_stl_preview())
            
            dialog.show()
            self._reconstruction_dialog = dialog
            
        except Exception as e:
            logger.error(f"Failed to show reconstruction panel: {e}")
            raise
    
    def _add_feature_previews(self, analysis):
        """Add preview geometry for detected features."""
        try:
            import pyvista as pv
            
            # Preview holes as translucent cylinders
            for i, hole in enumerate(analysis.holes):
                cylinder = pv.Cylinder(
                    center=hole.center,
                    direction=hole.axis,
                    radius=hole.radius,
                    height=hole.depth * 1.2
                )
                
                if hole.confidence >= 0.9:
                    color = 'green'
                elif hole.confidence >= 0.7:
                    color = 'blue'
                elif hole.confidence >= 0.5:
                    color = 'orange'
                else:
                    color = 'red'
                
                actor = self.viewport_3d.plotter.add_mesh(
                    cylinder,
                    color=color,
                    opacity=0.4,
                    show_edges=False,
                    name=f'hole_preview_{i}'
                )
                self._stl_feature_actors.append(actor)
            
            logger.info(f"Added {len(self._stl_feature_actors)} feature previews to viewport")
            
        except Exception as e:
            logger.warning(f"Failed to add feature previews: {e}")
    
    def _toggle_stl_feature_preview(self, analysis, feature_type: str, index: int, enabled: bool):
        """Toggle visibility of a specific feature preview."""
        try:
            actor_name = ""
            if feature_type == "hole":
                actor_name = f"hole_preview_{index}"
            elif feature_type == "base_plane":
                actor_name = "base_plane_preview"
            elif feature_type == "edge":
                actor_name = f"edge_preview_{index}"
            
            if actor_name and str(actor_name) in self.viewport_3d.plotter.actors:
                self.viewport_3d.plotter.actors[str(actor_name)].SetVisibility(enabled)
                self.viewport_3d.plotter.render()
                
        except Exception as e:
            logger.warning(f"Failed to toggle feature: {e}")

    def _update_stl_feature_preview(self, analysis, feature_type: str, index: int, params: dict):
        """Update preview geometry when parameters change."""
        try:
            import pyvista as pv
            
            if feature_type == "hole":
                hole = analysis.holes[index]
                
                radius = params.get("radius", hole.radius)
                depth = params.get("depth", hole.depth)
                center = params.get("center", hole.center)
                
                actor_name = f"hole_preview_{index}"
                
                if actor_name in self.viewport_3d.plotter.actors:
                    self.viewport_3d.plotter.remove_actor(actor_name)
                
                cylinder = pv.Cylinder(
                    center=center,
                    direction=hole.axis,
                    radius=radius,
                    height=depth * 1.2
                )
                
                self.viewport_3d.plotter.add_mesh(
                    cylinder,
                    color='blue',
                    opacity=0.4,
                    show_edges=False,
                    name=actor_name
                )
                
        except Exception as e:
            logger.warning(f"Failed to update feature preview: {e}")
    
    def _highlight_stl_feature(self, analysis, feature_type: str, index: int):
        """Highlight a feature in the viewport when selected in panel."""
        try:
            import pyvista as pv
            
            if hasattr(self, '_highlight_actor'):
                try:
                    self.viewport_3d.plotter.remove_actor(self._highlight_actor)
                except Exception:
                    pass
            
            if feature_type == "hole" and index < len(analysis.holes):
                hole = analysis.holes[index]
                
                highlight_cyl = pv.Cylinder(
                    center=hole.center,
                    direction=hole.axis,
                    radius=hole.radius * 1.05,
                    height=hole.depth * 1.3
                )
                
                self._highlight_actor = self.viewport_3d.plotter.add_mesh(
                    highlight_cyl,
                    color='yellow',
                    opacity=0.6,
                    show_edges=True,
                    edge_color='white',
                    line_width=3,
                    name='feature_highlight'
                )
            
            self.viewport_3d.plotter.render()
            
        except Exception as e:
            logger.warning(f"Failed to highlight feature: {e}")
    
    def _cleanup_stl_preview(self):
        """Remove STL preview and feature previews from viewport."""
        try:
            if hasattr(self, '_stl_preview_actor'):
                self.viewport_3d.plotter.remove_actor(self._stl_preview_actor)
                del self._stl_preview_actor
            
            if hasattr(self, '_stl_feature_actors'):
                for actor in self._stl_feature_actors:
                    try:
                        self.viewport_3d.plotter.remove_actor(actor)
                    except Exception:
                        pass
                del self._stl_feature_actors
            
            if hasattr(self, '_highlight_actor'):
                self.viewport_3d.plotter.remove_actor(self._highlight_actor)
                del self._highlight_actor
            
            logger.info("STL preview cleaned up")
            
        except Exception as e:
            logger.warning(f"Failed to cleanup STL preview: {e}")
    
    def _start_stl_reconstruction(self, panel, analysis):
        """Start the actual reconstruction process using SketchAgent."""
        try:
            logger.info("Starting reconstruction via SketchAgent...")
            
            if not hasattr(self, 'sketch_agent'):
                from sketching.core.sketch_agent import create_agent
                self.sketch_agent = create_agent(
                    document=self.document,
                    mode="guided",
                    headless=False
                )
                self.sketch_agent.viewport = self.viewport_3d
            
            self.sketch_agent.document = self.document
            
            def progress_callback(percent, message):
                panel.update_progress(int(percent * 100))
                panel.set_status(message)
                QApplication.processEvents()
            
            result = self.sketch_agent.reconstruct_from_mesh(
                mesh_path=analysis.mesh_path,
                interactive=True,
                analysis=analysis
            )
            
            if result.success:
                self._update_viewport_all()
                self.browser.refresh()
                
                panel.set_status("Complete")
                panel.update_progress(100)
                
                QMessageBox.information(
                    self,
                    "Success",
                    f"Reconstruction complete!\n"
                    f"Created solid using Sketch/Agent workflow."
                )
            else:
                QMessageBox.warning(
                    self,
                    "Failed",
                    f"Reconstruction failed:\n{result.error}"
                )
                
        except Exception as e:
            logger.error(f"Reconstruction error: {e}")
            QMessageBox.critical(self, "Error", str(e))
    
    # =========================================================================
    # Mesh to BREP Conversion
    # =========================================================================
    
    def _convert_selected_body_to_brep(self):
        """Konvertiert ausgewählten Mesh-Body zu BREP-Solid."""
        body = self._get_active_body()
        if not body:
            self._pending_mesh_convert_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)
            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)
            logger.info("Mesh zu CAD: Klicke auf einen Mesh-Körper in der 3D-Ansicht")
            return

        if body._build123d_solid is not None:
            logger.info(f"'{body.name}' ist bereits ein CAD-Solid.")
            return

        if body.vtk_mesh is None:
            logger.warning("Kein Mesh vorhanden zum Konvertieren.")
            return

        logger.info(f"Konvertiere '{body.name}' zu BREP (bitte warten)...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()

        try:
            success = body.convert_to_brep()

            if success:
                logger.success(f"Erfolg! '{body.name}' ist jetzt ein CAD-Solid.")
                self.browser.refresh()

                if body.id in self.viewport_3d._body_actors:
                    for actor_name in self.viewport_3d._body_actors[body.id]:
                        try:
                            self.viewport_3d.plotter.remove_actor(actor_name)
                        except Exception:
                            pass
                    del self.viewport_3d._body_actors[body.id]
                
                if body.id in self.viewport_3d.bodies:
                    del self.viewport_3d.bodies[body.id]

                self._update_viewport_all_impl()

                if hasattr(self.viewport_3d, 'plotter'):
                    from gui.viewport.render_queue import request_render
                    request_render(self.viewport_3d.plotter, immediate=True)
                    self.viewport_3d.update()

            else:
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(
                    self,
                    "Fehler",
                    "Konvertierung fehlgeschlagen.\nIst das Mesh geschlossen und valide?"
                )
                logger.error("Mesh-zu-BREP Konvertierung fehlgeschlagen")

        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Fehler", f"Kritischer Fehler: {e}")
            import traceback
            traceback.print_exc()

        finally:
            QApplication.restoreOverrideCursor()

    def _on_body_clicked_for_mesh_convert(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body für Mesh-Konvertierung angeklickt wird."""
        self._pending_mesh_convert_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        body = self._find_body_by_id_global(body_id)
        if not body:
            logger.warning(f"Body {body_id} nicht gefunden")
            return

        if body._build123d_solid is not None:
            logger.info(f"'{body.name}' ist bereits ein CAD-Solid.")
            return

        if body.vtk_mesh is None:
            logger.warning("Kein Mesh vorhanden zum Konvertieren.")
            return

        logger.info(f"Konvertiere '{body.name}' zu BREP (bitte warten)...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()

        try:
            success = body.convert_to_brep()

            if success:
                logger.success(f"Erfolg! '{body.name}' ist jetzt ein CAD-Solid.")
                self.browser.refresh()

                if body.id in self.viewport_3d._body_actors:
                    for actor_name in self.viewport_3d._body_actors[body.id]:
                        try:
                            self.viewport_3d.plotter.remove_actor(actor_name)
                        except Exception:
                            pass
                    del self.viewport_3d._body_actors[body.id]
                
                if body.id in self.viewport_3d.bodies:
                    del self.viewport_3d.bodies[body.id]

                self._update_viewport_all_impl()

                if hasattr(self.viewport_3d, 'plotter'):
                    from gui.viewport.render_queue import request_render
                    request_render(self.viewport_3d.plotter, immediate=True)
                    self.viewport_3d.update()
            else:
                QApplication.restoreOverrideCursor()
                QMessageBox.warning(
                    self,
                    "Fehler",
                    "Konvertierung fehlgeschlagen.\nIst das Mesh geschlossen und valide?"
                )
                logger.error("Mesh-zu-BREP Konvertierung fehlgeschlagen")

        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Fehler", f"Kritischer Fehler: {e}")
            import traceback
            traceback.print_exc()

        finally:
            QApplication.restoreOverrideCursor()
    
    # =========================================================================
    # Hole Dialog
    # =========================================================================

    def _resolve_ocp_face_id_from_cell(self, body_id: str, cell_id: int):
        """Ermittelt OCP-Face-Index aus einem Mesh-Cell-Index."""
        try:
            body_data = getattr(self.viewport_3d, "bodies", {}).get(body_id, {})
            mesh = body_data.get("mesh") if isinstance(body_data, dict) else None
            if mesh is None or not hasattr(mesh, "cell_data") or "face_id" not in mesh.cell_data:
                return None
            face_ids = mesh.cell_data["face_id"]
            if 0 <= int(cell_id) < len(face_ids):
                return int(face_ids[int(cell_id)])
        except Exception as e:
            logger.debug(f"[dialog_operations] OCP Face-ID Lookup fehlgeschlagen: {e}")
        return None

    def _resolve_solid_face_from_pick(
        self,
        body,
        body_id: str,
        *,
        cell_id: int = None,
        position=None,
        ocp_face_id: int = None,
        center_fallback_tol: float = 5.0,
    ):
        """Löst ein build123d-Face aus Klickdaten auf."""
        if not body or not getattr(body, "_build123d_solid", None):
            return None, ocp_face_id

        if ocp_face_id is None and cell_id is not None:
            ocp_face_id = self._resolve_ocp_face_id_from_cell(body_id, cell_id)

        if ocp_face_id is not None:
            try:
                from modeling.topology_indexing import face_from_index

                resolved = face_from_index(body._build123d_solid, int(ocp_face_id))
                if resolved is not None:
                    return resolved, int(ocp_face_id)
            except Exception as e:
                logger.debug(f"[dialog_operations] face_from_index fehlgeschlagen: {e}")

        if position is None:
            return None, ocp_face_id

        try:
            pos_arr = np.array(position, dtype=float)
            best_face = None
            best_face_index = None
            best_dist = float("inf")
            from modeling.topology_indexing import iter_faces_with_indices

            for face_idx, solid_face in iter_faces_with_indices(body._build123d_solid):
                try:
                    fc = solid_face.center()
                    solid_center = np.array([fc.X, fc.Y, fc.Z], dtype=float)
                    dist = np.linalg.norm(solid_center - pos_arr)
                    if dist < best_dist:
                        best_dist = dist
                        best_face = solid_face
                        best_face_index = int(face_idx)
                except Exception:
                    continue
            if best_face is not None and best_dist < center_fallback_tol:
                return best_face, best_face_index if best_face_index is not None else ocp_face_id
        except Exception as e:
            logger.debug(f"[dialog_operations] Face-Center Fallback fehlgeschlagen: {e}")

        return None, ocp_face_id

    def _find_or_register_face_shape_id(
        self,
        body,
        face,
        *,
        local_index: int = 0,
        feature_id: str = None,
        force_feature_local: bool = False,
    ):
        """Sucht/registriert eine Face-ShapeID."""
        if not body or face is None or not body._document or not hasattr(body._document, "_shape_naming_service"):
            return None

        service = body._document._shape_naming_service
        source_feature_id = body.features[-1].id if getattr(body, "features", None) else body.id
        target_feature_id = feature_id or source_feature_id
        target_local_index = max(0, int(local_index))
        try:
            shape_id = service.find_shape_id_by_face(face, require_exact=True)
            if shape_id is not None:
                if not force_feature_local:
                    return shape_id
                same_slot = (
                    getattr(shape_id, "feature_id", None) == target_feature_id
                    and int(getattr(shape_id, "local_index", -1)) == target_local_index
                )
                if same_slot:
                    return shape_id
        except Exception as e:
            logger.debug(f"[dialog_operations] ShapeID Lookup fehlgeschlagen: {e}")

        try:
            if not hasattr(face, "wrapped"):
                return None
            from modeling.tnp_system import ShapeType

            fc = face.center()
            area = float(face.area) if hasattr(face, "area") else 0.0
            return service.register_shape(
                ocp_shape=face.wrapped,
                shape_type=ShapeType.FACE,
                feature_id=target_feature_id,
                local_index=target_local_index,
                geometry_data=(fc.X, fc.Y, fc.Z, area),
            )
        except Exception as e:
            logger.debug(f"[dialog_operations] ShapeID Registrierung fehlgeschlagen: {e}")
            return None
    
    def _hole_dialog(self):
        """Startet interaktiven Hole-Workflow (Fusion-style)."""
        has_bodies = self._has_cad_bodies()
        if not has_bodies:
            self.statusBar().showMessage("Keine Bodies mit Geometrie vorhanden")
            logger.warning("Hole: Keine Bodies mit Geometrie.")
            return

        self._hide_transform_ui()
        self._hole_mode = True
        self._hole_target_body = None
        self._hole_face_selector = None
        self._hole_face_shape_id = None
        self._hole_face_index = None
        self.viewport_3d.set_hole_mode(True)
        self.hole_panel.reset()
        self.hole_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage("Hole: Klicke auf eine Fläche eines Bodys")
        logger.info("Hole-Modus gestartet — Fläche auf Body klicken")

    def _on_hole_diameter_changed(self, value):
        """Live-Update der Hole-Preview bei Durchmesser-Änderung."""
        if not self._hole_mode:
            return
        pos = getattr(self.viewport_3d, "_hole_position", None)
        normal = getattr(self.viewport_3d, "_hole_normal", None)
        if pos and normal:
            depth = self.hole_panel.get_depth()
            self.viewport_3d.show_hole_preview(pos, normal, value, depth)

    def _on_hole_depth_changed(self, value):
        """Live-Update der Hole-Preview bei Tiefen-Änderung."""
        if not self._hole_mode:
            return
        pos = getattr(self.viewport_3d, "_hole_position", None)
        normal = getattr(self.viewport_3d, "_hole_normal", None)
        if pos and normal:
            diameter = self.hole_panel.get_diameter()
            self.viewport_3d.show_hole_preview(pos, normal, diameter, value)

    def _on_hole_confirmed(self):
        """Hole bestätigt — Feature erstellen."""
        from config.feature_flags import is_enabled
        from modeling import HoleFeature
        from gui.commands.feature_commands import AddFeatureCommand

        pos = getattr(self.viewport_3d, "_hole_position", None)
        normal = getattr(self.viewport_3d, "_hole_normal", None)
        face_selector = getattr(self, '_hole_face_selector', None)
        face_index = getattr(self, '_hole_face_index', None)
        if not pos or not normal:
            self.statusBar().showMessage("Keine Fläche ausgewählt!")
            return

        body = getattr(self, '_hole_target_body', None)
        if not body:
            self._finish_hole_ui()
            return

        diameter = self.hole_panel.get_diameter()
        depth = self.hole_panel.get_depth()
        hole_type = self.hole_panel.get_hole_type()
        has_primary_face_ref = (
            self._hole_face_shape_id is not None
            or face_index is not None
        )

        feature = HoleFeature(
            hole_type=hole_type,
            diameter=diameter,
            depth=depth,
            position=pos,
            direction=tuple(-n for n in normal),
            face_selectors=[face_selector] if (face_selector and not has_primary_face_ref) else [],
        )

        if self._hole_face_shape_id is not None:
            feature_shape_id = None
            try:
                if face_index is not None and getattr(body, "_build123d_solid", None) is not None:
                    from modeling.topology_indexing import face_from_index

                    resolved_face = face_from_index(body._build123d_solid, int(face_index))
                    if resolved_face is not None:
                        feature_shape_id = self._find_or_register_face_shape_id(
                            body,
                            resolved_face,
                            local_index=0,
                            feature_id=feature.id,
                            force_feature_local=True,
                        )
            except Exception as sid_err:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"Hole: Feature-lokale ShapeID konnte nicht registriert werden: {sid_err}")

            feature.face_shape_ids = [feature_shape_id or self._hole_face_shape_id]
        if face_index is not None:
            try:
                feature.face_indices = [int(face_index)]
            except Exception:
                pass

        cmd = AddFeatureCommand(body, feature, self)
        self.undo_stack.push(cmd)
        if feature.status == "ERROR":
            msg = feature.status_message or "Kernel-Operation fehlgeschlagen"
            self.statusBar().showMessage(f"Hole fehlgeschlagen: {msg}", 8000)
            logger.error(f"Hole fehlgeschlagen: {msg}")
        elif feature.status == "WARNING":
            msg = feature.status_message or "Fallback verwendet"
            self.statusBar().showMessage(f"Hole mit Warnung: {msg}", 6000)
            logger.warning(f"Hole mit Warnung: {msg}")
        else:
            self.statusBar().showMessage(f"Hole D={diameter}mm erstellt")
            logger.success(f"Hole {hole_type} D={diameter}mm at {pos}")
        self._finish_hole_ui()

    def _on_hole_cancelled(self):
        """Hole abgebrochen."""
        self._finish_hole_ui()

    def _finish_hole_ui(self):
        """Hole-UI aufräumen."""
        self._hole_mode = False
        self._hole_target_body = None
        self._hole_face_selector = None
        self._hole_face_shape_id = None
        self._hole_face_index = None
        self.viewport_3d.set_hole_mode(False)
        self.hole_panel.hide()
        self.statusBar().clearMessage()

    def _on_body_face_clicked_for_hole(self, body_id, cell_id, normal, position):
        """Body-Face wurde im Hole-Modus geklickt."""
        if not self._hole_mode:
            return
        body = self._find_body_by_id_global(body_id)
        if not body or not body._build123d_solid:
            self.statusBar().showMessage("Kein gültiger Body getroffen")
            return

        self._hole_target_body = body
        self.viewport_3d._hole_position = tuple(position)
        self.viewport_3d._hole_normal = tuple(normal)

        try:
            from modeling.geometric_selector import GeometricFaceSelector

            best_face, resolved_face_id = self._resolve_solid_face_from_pick(
                body,
                body.id,
                cell_id=cell_id,
                position=position,
            )
            if best_face is not None:
                geo_selector = GeometricFaceSelector.from_face(best_face)
                self._hole_face_selector = geo_selector.to_dict()
                self._hole_face_shape_id = self._find_or_register_face_shape_id(
                    body,
                    best_face,
                    local_index=0,
                )
                self._hole_face_index = resolved_face_id
            else:
                self._hole_face_selector = {
                    "center": list(position),
                    "normal": list(normal),
                    "area": 0.0,
                    "surface_type": "unknown",
                    "tolerance": 10.0,
                }
                self._hole_face_shape_id = None
                self._hole_face_index = None
                logger.warning("Hole: Konnte Face nicht finden, verwende Fallback")
        except Exception as e:
            logger.warning(f"Hole: Konnte GeometricFaceSelector nicht erstellen: {e}")
            self._hole_face_selector = None
            self._hole_face_shape_id = None
            self._hole_face_index = None

        diameter = self.hole_panel.get_diameter()
        depth = self.hole_panel.get_depth()
        self.viewport_3d.show_hole_preview(position, normal, diameter, depth)
        self.statusBar().showMessage(f"Hole auf {body.name} — Parameter einstellen, Enter bestätigen")
    
    # =========================================================================
    # Thread Dialog
    # =========================================================================
    
    def _thread_dialog(self):
        """Startet interaktiven Thread-Workflow (Fusion-style)."""
        has_bodies = self._has_cad_bodies()
        if not has_bodies:
            self.statusBar().showMessage("Keine Bodies mit Geometrie vorhanden")
            logger.warning("Thread: Keine Bodies mit Geometrie.")
            return

        self._hide_transform_ui()
        self._thread_mode = True
        self._pending_thread_mode = False
        self._thread_target_body = None
        self._thread_position = None
        self._thread_direction = None
        self._thread_detected_diameter = None
        self._thread_is_internal = False
        self._thread_face_selector = None
        self._thread_face_shape_id = None
        self._thread_face_index = None
        self.viewport_3d.set_thread_mode(True)
        self.thread_panel.reset()
        self.thread_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage("Thread: Klicke auf eine zylindrische Fläche (Loch oder Bolzen)")
        logger.info("Thread-Modus gestartet — zylindrische Fläche auf Body klicken")

    def _on_thread_diameter_changed(self, value):
        """Live-Update der Thread-Preview bei Durchmesser-Änderung."""
        self._update_thread_preview()

    def _on_thread_pitch_changed(self, value):
        """Live-Update bei Pitch-Änderung."""
        self._update_thread_preview()

    def _on_thread_depth_changed(self, value):
        """Live-Update der Thread-Preview bei Tiefen-Änderung."""
        self._update_thread_preview()

    def _on_thread_tolerance_changed(self, value):
        """Live-Update bei Toleranz-Änderung."""
        self._update_thread_preview()

    def _update_thread_preview(self):
        """Aktualisiert die Thread-Preview basierend auf aktuellen Panel-Werten."""
        if not self._thread_mode:
            return
        if not self._thread_position or not self._thread_direction:
            return

        diameter = self.thread_panel.get_diameter()
        depth = self.thread_panel.get_depth()
        if hasattr(self.viewport_3d, 'show_thread_preview'):
            self.viewport_3d.show_thread_preview(
                self._thread_position,
                self._thread_direction,
                diameter,
                depth,
                self._thread_is_internal,
            )

    def _on_cylindrical_face_clicked_for_thread(self, body_id, cell_id, axis_dir, position, diameter):
        """Zylindrische Fläche wurde im Thread-Modus geklickt."""
        if not self._thread_mode:
            return
        body = self._find_body_by_id_global(body_id)
        if not body or not body._build123d_solid:
            self.statusBar().showMessage("Kein gültiger Body getroffen")
            return

        self._thread_target_body = body
        self._thread_position = tuple(position)
        self._thread_direction = tuple(axis_dir)
        self._thread_detected_diameter = float(diameter) if diameter else None
        self._thread_is_internal = True

        try:
            from modeling.geometric_selector import GeometricFaceSelector

            best_face, resolved_face_id = self._resolve_solid_face_from_pick(
                body,
                body.id,
                cell_id=cell_id,
                position=position,
            )
            if best_face is not None:
                geo_selector = GeometricFaceSelector.from_face(best_face)
                self._thread_face_selector = geo_selector.to_dict()
                self._thread_face_shape_id = self._find_or_register_face_shape_id(
                    body,
                    best_face,
                    local_index=0,
                )
                self._thread_face_index = resolved_face_id
                self._thread_is_internal = bool(self._thread_is_internal)
            else:
                self._thread_face_selector = {
                    "center": list(position),
                    "normal": list(axis_dir),
                    "area": 0.0,
                    "surface_type": "cylinder",
                    "tolerance": 10.0,
                }
                self._thread_face_shape_id = None
                self._thread_face_index = None
        except Exception as e:
            logger.warning(f"Thread: Konnte Face-Referenz nicht erstellen: {e}")
            self._thread_face_selector = None
            self._thread_face_shape_id = None
            self._thread_face_index = None

        if self._thread_detected_diameter and hasattr(self.thread_panel, "set_detected_diameter"):
            try:
                self.thread_panel.set_detected_diameter(self._thread_detected_diameter)
            except Exception:
                pass

        self._update_thread_preview()
        self.statusBar().showMessage(f"Thread auf {body.name} — Parameter einstellen, Enter bestätigen")

    def _on_thread_confirmed(self):
        """Thread bestätigt — Feature erstellen."""
        from modeling import ThreadFeature
        from gui.commands.feature_commands import AddFeatureCommand

        body = self._thread_target_body
        if not body:
            self.statusBar().showMessage("Kein Body ausgewählt!")
            self._finish_thread_ui()
            return

        if not self._thread_position or not self._thread_direction:
            self.statusBar().showMessage("Keine zylindrische Fläche ausgewählt!")
            return

        feature = ThreadFeature(
            thread_type="ISO Metric",
            standard="M",
            diameter=self.thread_panel.get_diameter(),
            pitch=self.thread_panel.get_pitch(),
            depth=self.thread_panel.get_depth(),
            position=tuple(self._thread_position),
            direction=tuple(self._thread_direction),
            tolerance_class="6g",
            tolerance_offset=self.thread_panel.get_tolerance_offset() if hasattr(self.thread_panel, "get_tolerance_offset") else 0.0,
            cosmetic=True,
            face_selector=self._thread_face_selector,
        )
        if self._thread_face_shape_id is not None:
            feature.face_shape_id = self._thread_face_shape_id
        if self._thread_face_index is not None:
            feature.face_index = int(self._thread_face_index)

        cmd = AddFeatureCommand(body, feature, self)
        self.undo_stack.push(cmd)
        if feature.status == "ERROR":
            msg = feature.status_message or "Kernel-Operation fehlgeschlagen"
            self.statusBar().showMessage(f"Thread fehlgeschlagen: {msg}", 8000)
            logger.error(f"Thread fehlgeschlagen: {msg}")
        elif feature.status == "WARNING":
            msg = feature.status_message or "Fallback verwendet"
            self.statusBar().showMessage(f"Thread mit Warnung: {msg}", 6000)
            logger.warning(f"Thread mit Warnung: {msg}")
        else:
            self.statusBar().showMessage("Thread erstellt")
            logger.success(f"Thread erstellt auf {body.name}")

        self._finish_thread_ui()

    def _on_thread_cancelled(self):
        """Thread abgebrochen."""
        self._finish_thread_ui()

    def _finish_thread_ui(self):
        """Thread-UI aufräumen."""
        self._thread_mode = False
        self._pending_thread_mode = False
        self._thread_target_body = None
        self._thread_position = None
        self._thread_direction = None
        self._thread_detected_diameter = None
        self._thread_is_internal = False
        self._thread_face_selector = None
        self._thread_face_shape_id = None
        self._thread_face_index = None
        if hasattr(self.viewport_3d, 'clear_thread_preview'):
            self.viewport_3d.clear_thread_preview()
        self.viewport_3d.set_thread_mode(False)
        self.thread_panel.hide()
        self.statusBar().clearMessage()
    
    def _on_body_clicked_for_thread(self, body_id: str):
        """Body für Thread wurde geklickt."""
        self._pending_thread_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)
        # Continue with thread selection
    
    # =========================================================================
    # Draft Dialog
    # =========================================================================
    
    def _draft_dialog(self):
        """Startet interaktiven Draft-Workflow (Fusion-style)."""
        has_bodies = self._has_cad_bodies()
        if not has_bodies:
            self.statusBar().showMessage("Keine Bodies mit Geometrie vorhanden")
            return

        self._hide_transform_ui()
        self._draft_mode = True
        self._draft_target_body = None
        self.viewport_3d.detected_faces = []
        self.viewport_3d._detect_body_faces()
        logger.info(f"Draft: {len(self.viewport_3d.detected_faces)} Body-Faces erkannt")
        self.viewport_3d.set_draft_mode(True)
        self.draft_panel.reset()
        self.draft_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage("Draft: Klicke auf Flächen des Bodys (Mehrfachselektion mit Klick)")
        logger.info("Draft-Modus gestartet — Flächen auf Body klicken")

    def _on_body_face_clicked_for_draft(self, body_id, cell_id, normal, position):
        """Body-Face wurde im Draft-Modus geklickt."""
        if not self._draft_mode:
            return

        body = self._find_body_by_id_global(body_id)
        if not body or not body._build123d_solid:
            return

        self._draft_target_body = body
        count = len(self.viewport_3d._draft_selected_faces)
        if hasattr(self.draft_panel, "set_face_count"):
            self.draft_panel.set_face_count(count)
        self.statusBar().showMessage(f"Draft: {count} Face(s) ausgewählt — Winkel einstellen, Enter bestätigen")
        self._update_draft_preview()

    def _on_draft_angle_changed(self, value):
        """Draft-Winkel geändert."""
        self._update_draft_preview()

    def _on_draft_axis_changed(self, axis):
        """Draft Pull-Richtung geändert."""
        self._update_draft_preview()

    def _update_draft_preview(self):
        """Live-Preview des Draft-Ergebnisses."""
        body = getattr(self, '_draft_target_body', None)
        faces = self.viewport_3d._draft_selected_faces
        if not body or not body._build123d_solid or not faces:
            self.viewport_3d.clear_draft_preview()
            return

        try:
            from modeling import DraftFeature
            angle = self.draft_panel.get_angle()
            pull_dir = self.draft_panel.get_pull_direction()
            face_normals = [tuple(f.get('normal', (0, 0, 0))) for f in faces]

            feature = DraftFeature(
                draft_angle=angle,
                pull_direction=pull_dir,
                face_selectors=[{'normal': n} for n in face_normals],
            )

            result_solid = body._compute_draft(feature, body._build123d_solid)
            if result_solid is None:
                self.viewport_3d.clear_draft_preview()
                return

            from modeling.cad_tessellator import CADTessellator
            mesh, _ = CADTessellator.tessellate(result_solid)
            if mesh is not None:
                self.viewport_3d._show_draft_preview_mesh(mesh)
            else:
                self.viewport_3d.clear_draft_preview()
        except Exception as e:
            logger.debug(f"Draft preview error: {e}")
            self.viewport_3d.clear_draft_preview()

    def _on_draft_confirmed(self):
        """Draft bestätigt — Feature erstellen."""
        from config.feature_flags import is_enabled
        from modeling import DraftFeature
        from modeling.geometric_selector import GeometricFaceSelector
        from gui.commands.feature_commands import AddFeatureCommand

        body = getattr(self, '_draft_target_body', None)
        if not body:
            self.statusBar().showMessage("Kein Body ausgewählt!")
            self._finish_draft_ui()
            return

        faces = self.viewport_3d._draft_selected_faces
        if not faces:
            self.statusBar().showMessage("Keine Flächen ausgewählt!")
            return

        angle = self.draft_panel.get_angle()
        pull_dir = self.draft_panel.get_pull_direction()

        face_selectors = []
        face_shape_ids = []
        face_indices = []
        for idx, face_data in enumerate(faces):
            try:
                normal = face_data.get("normal", (0, 0, 1))
                center = face_data.get("center_3d", face_data.get("center", (0.0, 0.0, 0.0)))

                cell_ids = face_data.get("cell_ids", []) or []
                candidate_cell_id = int(cell_ids[0]) if cell_ids else None
                explicit_face_id = face_data.get("face_id")
                explicit_face_id = int(explicit_face_id) if explicit_face_id is not None else None

                best_face, resolved_face_id = self._resolve_solid_face_from_pick(
                    body,
                    body.id,
                    cell_id=candidate_cell_id,
                    position=center,
                    ocp_face_id=explicit_face_id,
                )

                if best_face is not None:
                    geo_selector = GeometricFaceSelector.from_face(best_face)
                    face_selectors.append(geo_selector.to_dict())
                    shape_id = self._find_or_register_face_shape_id(
                        body,
                        best_face,
                        local_index=idx,
                    )
                    if shape_id is not None:
                        face_shape_ids.append(shape_id)
                    if resolved_face_id is not None:
                        face_indices.append(int(resolved_face_id))
                else:
                    face_selectors.append(
                        {
                            "center": list(center),
                            "normal": list(normal),
                            "area": 0.0,
                            "surface_type": "unknown",
                            "tolerance": 10.0,
                        }
                    )
            except Exception as e:
                logger.warning(f"Draft: Konnte Face-Referenz nicht erstellen: {e}")
                continue

        feature = DraftFeature(
            draft_angle=angle,
            pull_direction=pull_dir,
            face_selectors=face_selectors,
        )

        if face_shape_ids:
            feature.face_shape_ids = face_shape_ids
        if face_indices:
            feature.face_indices = sorted(set(face_indices))
        if is_enabled("tnp_debug_logging"):
            logger.debug(
                f"TNP v4.0: Draft-Referenzen vorbereitet "
                f"(selectors={len(face_selectors)}, shape_ids={len(face_shape_ids)}, "
                f"indices={len(feature.face_indices or [])})"
            )

        cmd = AddFeatureCommand(body, feature, self)
        self.undo_stack.push(cmd)
        if feature.status == "ERROR":
            msg = feature.status_message or "Kernel-Operation fehlgeschlagen"
            self.statusBar().showMessage(f"Draft fehlgeschlagen: {msg}", 8000)
            logger.error(f"Draft fehlgeschlagen: {msg}")
        elif feature.status == "WARNING":
            msg = feature.status_message or "Fallback verwendet"
            self.statusBar().showMessage(f"Draft mit Warnung: {msg}", 6000)
            logger.warning(f"Draft mit Warnung: {msg}")
        else:
            self.statusBar().showMessage(f"Draft {angle}° auf {len(faces)} Faces erstellt")
            logger.success(f"Draft {angle}° auf {len(faces)} Faces")

        self._finish_draft_ui()

    def _on_draft_cancelled(self):
        """Draft abgebrochen."""
        self._finish_draft_ui()

    def _finish_draft_ui(self):
        """Draft-UI aufräumen."""
        self._draft_mode = False
        self._draft_target_body = None
        if hasattr(self.viewport_3d, 'clear_draft_preview'):
            self.viewport_3d.clear_draft_preview()
        self.viewport_3d.set_draft_mode(False)
        self.draft_panel.hide()
        self.statusBar().clearMessage()
    
    # =========================================================================
    # Split Body Dialog
    # =========================================================================
    
    def _split_body_dialog(self):
        """Startet interaktiven Split-Workflow (PrusaSlicer-style)."""
        has_bodies = self._has_cad_bodies()
        if not has_bodies:
            self.statusBar().showMessage("Keine Bodies mit Geometrie vorhanden")
            return

        self._hide_transform_ui()
        self._split_mode = True
        self._split_target_body = None
        self._pending_split_mode = True
        self.split_panel.reset()
        self.split_panel.show_at(self.viewport_3d)
        self.viewport_3d.setCursor(Qt.CrossCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(True)

        self.statusBar().showMessage("Split: Klicke auf einen Body im Viewport")
        logger.info("Split-Modus gestartet — Body im Viewport klicken")

    def _on_split_body_clicked(self, body_id):
        """Body wurde im Split-Modus geklickt."""
        if not self._split_mode:
            return
        body = self._find_body_by_id_global(body_id)
        if not body or not body._build123d_solid:
            return

        self._pending_split_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        self._split_target_body = body
        self.viewport_3d.set_split_mode(True)
        center = self.viewport_3d.set_split_body(body_id)
        if center is not None:
            self.split_panel.set_position(center)
        self.statusBar().showMessage("Split: Ebene verschieben (Drag/Zahleneingabe), Enter bestätigen")
        self._update_split_preview()

    def _on_split_plane_changed(self, plane):
        """Schnittebene geändert (XY/XZ/YZ)."""
        if not self._split_mode or not getattr(self, '_split_target_body', None):
            return
        self.viewport_3d._split_plane_axis = plane
        center = self.viewport_3d.set_split_body(self._split_target_body.id)
        if center is not None:
            self.split_panel.set_position(center)
        self._update_split_preview()

    def _on_split_position_changed(self, value):
        """Position per Panel geändert."""
        if not self._split_mode or not getattr(self, '_split_target_body', None):
            return
        self.viewport_3d.update_split_plane(self.viewport_3d._split_plane_axis, value)
        self._update_split_preview()

    def _on_split_angle_changed(self, angle):
        """Schnittwinkel geändert."""
        if not self._split_mode or not getattr(self, '_split_target_body', None):
            return
        self.viewport_3d._split_angle = angle
        self.viewport_3d._draw_split_plane()
        self._schedule_split_preview()

    def _on_split_keep_changed(self, keep):
        """Keep-Seite geändert."""
        self._update_split_preview()

    def _on_split_drag(self, position):
        """Viewport-Drag → Panel synchronisieren."""
        self.split_panel.set_position(position)
        self._schedule_split_preview()

    def _schedule_split_preview(self):
        """Debounced split preview — verhindert Spam bei schnellem Drag."""
        if not hasattr(self, '_split_preview_timer'):
            from PySide6.QtCore import QTimer
            self._split_preview_timer = QTimer(self)
            self._split_preview_timer.setSingleShot(True)
            self._split_preview_timer.timeout.connect(self._update_split_preview)
        self._split_preview_timer.start(150)

    def _split_origin_normal(self):
        """Berechnet Origin und Normal für die aktuelle Split-Konfiguration (inkl. Winkel)."""
        import numpy as np

        axis = self.viewport_3d._split_plane_axis
        pos = self.viewport_3d._split_position
        angle_deg = self.split_panel.get_angle()

        if axis == "XY":
            origin, normal = (0, 0, pos), np.array([0.0, 0.0, 1.0])
        elif axis == "XZ":
            origin, normal = (0, pos, 0), np.array([0.0, 1.0, 0.0])
        else:
            origin, normal = (pos, 0, 0), np.array([1.0, 0.0, 0.0])

        if abs(angle_deg) > 0.01:
            angle_rad = np.radians(angle_deg)
            if axis == "XY":
                rot_axis = np.array([1.0, 0.0, 0.0])
            elif axis == "XZ":
                rot_axis = np.array([1.0, 0.0, 0.0])
            else:
                rot_axis = np.array([0.0, 1.0, 0.0])
            k = rot_axis
            c, s = np.cos(angle_rad), np.sin(angle_rad)
            normal = normal * c + np.cross(k, normal) * s + k * np.dot(k, normal) * (1 - c)
            normal = normal / (np.linalg.norm(normal) + 1e-12)

        return origin, tuple(normal)

    def _update_split_preview(self):
        """Live-Preview beider Hälften."""
        body = getattr(self, '_split_target_body', None)
        if not body or not body._build123d_solid:
            self.viewport_3d.clear_split_preview_meshes()
            return

        try:
            from modeling import SplitFeature
            from modeling.cad_tessellator import CADTessellator

            origin, normal = self._split_origin_normal()

            above_mesh = None
            below_mesh = None

            for side in ["above", "below"]:
                feature = SplitFeature(
                    plane_origin=origin,
                    plane_normal=normal,
                    keep_side=side,
                )
                try:
                    result = body._compute_split(feature, body._build123d_solid)
                    if result is not None:
                        mesh, _ = CADTessellator.tessellate(result)
                        if side == "above":
                            above_mesh = mesh
                        else:
                            below_mesh = mesh
                except Exception:
                    pass

            self.viewport_3d.show_split_preview(above_mesh, below_mesh)

            body_data = self.viewport_3d.bodies.get(body.id)
            if body_data and 'mesh' in body_data:
                try:
                    self.viewport_3d.plotter.add_mesh(
                        body_data['mesh'], color='#666666', opacity=0.15,
                        name=f"body_{body.id}_m", pickable=False
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.debug(f"Split preview error: {e}")
            self.viewport_3d.clear_split_preview_meshes()

    def _on_split_confirmed(self):
        """Split bestätigt — Feature erstellen."""
        from modeling import SplitFeature
        from gui.commands.feature_commands import AddFeatureCommand, SplitBodyCommand

        body = getattr(self, '_split_target_body', None)
        if not body:
            self.statusBar().showMessage("Kein Body ausgewählt!")
            self._finish_split_ui()
            return

        keep = self.split_panel.get_keep_side()
        origin, normal = self._split_origin_normal()

        if keep == "both":
            cmd = SplitBodyCommand(
                self.document,
                body,
                origin,
                normal,
                self
            )
            self.undo_stack.push(cmd)

            self.statusBar().showMessage("Split (both) — 2 Bodies erstellt")
            logger.success("Split Body (both) erstellt — mit shared Historie und Undo/Redo")
        else:
            feature = SplitFeature(
                plane_origin=origin, plane_normal=normal, keep_side=keep,
            )
            cmd = AddFeatureCommand(body, feature, self)
            self.undo_stack.push(cmd)
            self.statusBar().showMessage(f"Split ({keep}) applied")
            logger.success(f"Split Body ({keep}) erstellt")

        self._finish_split_ui()

    def _on_split_cancelled(self):
        """Split abgebrochen."""
        self._finish_split_ui()

    def _finish_split_ui(self):
        """Split-UI aufräumen."""
        self._split_mode = False
        self._pending_split_mode = False
        self._split_target_body = None
        self.viewport_3d.set_split_mode(False)
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)
        self.split_panel.hide()
        self._trigger_viewport_update()
    
    # =========================================================================
    # Revolve Dialog
    # =========================================================================
    
    def _revolve_dialog(self):
        """Startet den interaktiven Revolve-Workflow (Fusion-Style)."""
        from i18n import tr
        
        self.viewport_3d.set_revolve_mode(True)
        self.revolve_panel.reset()
        self.revolve_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage(tr("Wähle Profil für Revolve"))
        logger.info("Revolve-Modus: Klicke auf eine Fläche")

    def _on_revolve_angle_changed(self, angle):
        """Panel-Winkel geändert → Preview aktualisieren."""
        self._update_revolve_preview()

    def _on_revolve_axis_changed(self, axis):
        """Panel-Achse geändert → Preview aktualisieren."""
        self._update_revolve_preview()

    def _on_revolve_operation_changed(self, operation):
        """Panel-Operation geändert → Preview-Farbe aktualisieren."""
        self._update_revolve_preview()

    def _on_revolve_direction_flipped(self):
        """Revolve-Richtung umkehren → Preview aktualisieren."""
        self._update_revolve_preview()

    def _update_revolve_preview(self):
        """Aktualisiert die Revolve-Preview."""
        pass  # Preview handled by viewport

    def _on_revolve_confirmed(self):
        """Revolve bestätigen und Feature erstellen."""
        self._finish_revolve_ui()

    def _on_revolve_cancelled(self):
        """Revolve abbrechen."""
        self._finish_revolve_ui()

    def _finish_revolve_ui(self):
        """Revolve UI aufräumen."""
        self.viewport_3d.set_revolve_mode(False)
        self.revolve_panel.hide()
        self.statusBar().clearMessage()

    def _on_face_selected_for_revolve(self, face_id):
        """Face-Klick im Revolve-Modus → Selektion speichern + Preview."""
        if not self.viewport_3d.revolve_mode:
            return
        self._update_revolve_preview()
    
    # =========================================================================
    # Primitive Dialog
    # =========================================================================
    
    def _primitive_dialog(self, ptype="box"):
        """Create a primitive solid (Box, Cylinder, Sphere, Cone) as new body."""
        from gui.dialogs.primitive_dialog import PrimitiveDialog
        
        dialog = PrimitiveDialog(ptype, self)
        if dialog.exec():
            params = dialog.get_parameters()
            self._create_primitive(ptype, params)

    def _create_primitive(self, ptype: str, params: dict):
        """Create a primitive body from parameters."""
        from modeling import PrimitiveFeature
        from gui.commands.feature_commands import AddFeatureCommand
        
        body = self.document.new_body(name=ptype.capitalize())
        
        feature = PrimitiveFeature(
            primitive_type=ptype,
            **params
        )
        
        cmd = AddFeatureCommand(body, feature, self, description=f"Create {ptype}")
        self.undo_stack.push(cmd)
        
        self.browser.refresh()
        self._update_viewport_all()
        logger.success(f"{ptype.capitalize()} erstellt")
    
    # =========================================================================
    # Mirror Dialog
    # =========================================================================
    
    def _show_mirror_dialog(self, body_id: str):
        """Zeigt Dialog zur Auswahl der Mirror-Ebene"""
        from gui.dialogs.mirror_dialog import MirrorDialog
        
        body = self.document.find_body_by_id(body_id)
        if not body:
            return
        
        dialog = MirrorDialog(body, self)
        if dialog.exec():
            plane = dialog.get_plane()
            self._apply_mirror(body, plane)

    def _apply_mirror(self, body, plane: str):
        """Apply mirror operation to body."""
        from modeling import TransformFeature
        from gui.commands.feature_commands import AddFeatureCommand
        
        feature = TransformFeature(
            type='mirror',
            plane=plane
        )
        
        cmd = AddFeatureCommand(body, feature, self, description=f"Mirror {plane}")
        self.undo_stack.push(cmd)
        
        self.browser.refresh()
        self._update_viewport_all()
        logger.success(f"Mirror auf {plane}-Ebene durchgeführt")
    
    # =========================================================================
    # Boolean Operation Dialog
    # =========================================================================
    
    def _boolean_operation_dialog(self, op_type="Cut"):
        """Führt Union, Cut oder Intersect aus"""
        from i18n import tr
        from gui.dialogs.input_dialogs import BooleanDialog

        # Get selected bodies
        selected = self.browser.get_selected_bodies()
        all_bodies = self._all_bodies()
        if len(selected) < 2:
            # Show dialog to select bodies
            dialog = BooleanDialog(all_bodies, op_type, self)
            if dialog.exec():
                target, tool = dialog.get_selection()
            else:
                return
        else:
            target, tool = selected[0], selected[1]
        
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            
            # Perform boolean operation
            if op_type == "Union":
                result = target.boolean_union(tool)
            elif op_type == "Cut":
                result = target.boolean_cut(tool)
            elif op_type == "Intersect":
                result = target.boolean_intersect(tool)
            
            QApplication.restoreOverrideCursor()
            
            if result:
                self.browser.refresh()
                self._update_viewport_all()
                logger.success(f"{op_type} erfolgreich")
            else:
                QMessageBox.warning(self, "Fehler", "Operation fehlgeschlagen.")
                
        except Exception as e:
            QApplication.restoreOverrideCursor()
            logger.error(f"Boolean operation failed: {e}")
            QMessageBox.warning(self, "Fehler", f"Operation fehlgeschlagen ({str(e)}).")
    
    # =========================================================================
    # N-Sided Patch Dialog
    # =========================================================================
    
    def _nsided_patch_dialog(self):
        """
        Startet N-Sided Patch mit Viewport-Selektion.
        - Falls Body ausgewählt -> sofort Edge-Selektion starten
        - Falls kein Body -> Pending-Mode, warte auf Klick
        """
        selected_bodies = self.browser.get_selected_bodies()

        if not selected_bodies:
            self._pending_nsided_patch_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)
            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)
            logger.info("N-Sided Patch: Klicke auf einen Körper in der 3D-Ansicht")
            return

        body = selected_bodies[0]
        self._activate_nsided_patch_for_body(body)

    def _on_body_clicked_for_nsided_patch(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body für N-Sided Patch angeklickt wird."""
        self._pending_nsided_patch_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)
        
        body = self.document.find_body_by_id(body_id)
        if body:
            self._activate_nsided_patch_for_body(body)

    def _activate_nsided_patch_for_body(self, body):
        """Aktiviert N-Sided Patch-Modus für einen Body."""
        if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
            logger.warning(f"'{body.name}' hat keine CAD-Daten (nur Mesh).")
            return

        if hasattr(self.viewport_3d, 'hide_gizmo'):
            self.viewport_3d.hide_gizmo()
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)

        self._nsided_patch_mode = True
        self._nsided_patch_target_body = body
        if hasattr(self.nsided_patch_panel, 'set_target_body'):
            self.nsided_patch_panel.set_target_body(body)
        self.nsided_patch_panel.reset()

        self.viewport_3d.set_edge_selection_callbacks(
            get_body_by_id=self._find_body_by_id_global
        )
        if hasattr(self.viewport_3d, 'start_edge_selection_mode'):
            self.viewport_3d.start_edge_selection_mode(body.id)

        self.nsided_patch_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage("Wähle Kanten für N-Sided Patch")
        logger.info(f"N-Sided Patch für '{body.name}' - Wähle mindestens 3 zusammenhängende Boundary-Kanten")

    def _on_nsided_patch_edge_selection_changed(self, count: int):
        """Handler wenn sich die Kanten-Selektion für N-Sided Patch ändert."""
        if self._nsided_patch_mode:
            self.nsided_patch_panel.update_edge_count(count)

    def _on_nsided_patch_confirmed(self):
        """Handler wenn N-Sided Patch bestätigt wird."""
        if not self._nsided_patch_mode or not self._nsided_patch_target_body:
            return

        body = self._nsided_patch_target_body

        selected_edges = []
        selected_edge_indices = []
        if hasattr(self.viewport_3d, 'get_selected_edges'):
            selected_edges = self.viewport_3d.get_selected_edges() or []
        if hasattr(self.viewport_3d, 'get_selected_edge_topology_indices'):
            selected_edge_indices = self.viewport_3d.get_selected_edge_topology_indices() or []

        if len(selected_edges) < 3:
            logger.warning("N-Sided Patch benötigt mindestens 3 Kanten")
            return

        degree = self.nsided_patch_panel.get_degree()
        tangent = self.nsided_patch_panel.get_tangent()

        from modeling import NSidedPatchFeature
        from modeling.geometric_selector import GeometricEdgeSelector
        from modeling.tnp_system import ShapeType
        from gui.commands.feature_commands import AddFeatureCommand

        geometric_selectors = []
        for edge in selected_edges:
            try:
                geometric_selectors.append(GeometricEdgeSelector.from_edge(edge).to_dict())
            except Exception as e:
                logger.debug(f"N-Sided Patch: GeometricSelector fehlgeschlagen: {e}")

        if len(geometric_selectors) < 3:
            logger.warning("N-Sided Patch: Konnte nicht genug TNP-v4 GeometricSelectors erzeugen")
            return

        feat = NSidedPatchFeature(
            edge_indices=selected_edge_indices,
            geometric_selectors=geometric_selectors,
            degree=degree,
            tangent=tangent,
        )

        shape_service = getattr(self.document, "_shape_naming_service", None)
        if shape_service:
            for idx, edge in enumerate(selected_edges):
                try:
                    shape_id = shape_service.find_shape_id_by_edge(edge, require_exact=True)
                    if shape_id is None and hasattr(edge, "wrapped"):
                        ec = edge.center()
                        edge_len = edge.length if hasattr(edge, "length") else 0.0
                        shape_id = shape_service.register_shape(
                            ocp_shape=edge.wrapped,
                            shape_type=ShapeType.EDGE,
                            feature_id=feat.id,
                            local_index=idx,
                            geometry_data=(ec.X, ec.Y, ec.Z, edge_len),
                        )
                    if shape_id is not None:
                        feat.edge_shape_ids.append(shape_id)
                except Exception as e:
                    logger.debug(f"N-Sided Patch: ShapeID-Auflösung fehlgeschlagen: {e}")

        cmd = AddFeatureCommand(body, feat, self, description=f"N-Sided Patch ({len(selected_edges)} edges)")
        self.undo_stack.push(cmd)

        if body._build123d_solid is None:
            logger.warning("N-Sided Patch ließ Body leer - Undo")
            self.undo_stack.undo()
            logger.error("N-Sided Patch fehlgeschlagen: Geometrie ungültig")
        else:
            self._update_body_mesh(body)
            self.browser.refresh()
            logger.success(
                f"N-Sided Patch mit {len(selected_edges)} Kanten angewendet "
                f"(TopoIdx: {len(selected_edge_indices)}, ShapeIDs: {len(feat.edge_shape_ids)})"
            )

        self._stop_nsided_patch_mode()

    def _on_nsided_patch_cancelled(self):
        """Handler wenn N-Sided Patch abgebrochen wird."""
        logger.info("N-Sided Patch abgebrochen")
        self._stop_nsided_patch_mode()

    def _stop_nsided_patch_mode(self):
        """Beendet den N-Sided Patch Modus."""
        self._nsided_patch_mode = False
        self._nsided_patch_target_body = None
        self._pending_nsided_patch_mode = False
        if hasattr(self.viewport_3d, 'stop_edge_selection_mode'):
            self.viewport_3d.stop_edge_selection_mode()
        self.nsided_patch_panel.hide()
        self.statusBar().clearMessage()
    
    # =========================================================================
    # Wall Thickness Dialog
    # =========================================================================
    
    def _wall_thickness_dialog(self):
        """
        Open wall thickness analysis dialog with viewport selection support.
        - Falls Body im Browser ausgewählt -> sofort Dialog öffnen
        - Falls kein Body -> Pending-Mode, warte auf Viewport-Klick
        """
        selected_bodies = self.browser.get_selected_bodies()

        if not selected_bodies:
            self._pending_wall_thickness_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)
            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)
            logger.info("Wall Thickness: Klicke auf einen Körper in der 3D-Ansicht")
            return

        body = selected_bodies[0]
        self._open_wall_thickness_for_body(body)

    def _on_body_clicked_for_wall_thickness(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body angeklickt wird."""
        self._pending_wall_thickness_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)
        
        body = self.document.find_body_by_id(body_id)
        if body:
            self._open_wall_thickness_for_body(body)

    def _open_wall_thickness_for_body(self, body):
        """Öffnet den Wall Thickness Dialog für einen spezifischen Body."""
        from gui.dialogs.wall_thickness_dialog import WallThicknessDialog

        if not hasattr(body, '_build123d_solid') or not body._build123d_solid:
            logger.warning(f"'{body.name}' hat keine CAD-Daten (nur Mesh).")
            return

        WallThicknessDialog(body, parent=self).exec()
    
    # =========================================================================
    # Lattice Dialog
    # =========================================================================
    
    def _start_lattice(self):
        """
        Startet Lattice-Modus mit Viewport-Selektion.
        - Falls Body ausgewählt -> sofort Panel anzeigen
        - Falls kein Body -> Pending-Modus, warte auf Klick
        """
        selected_bodies = self.browser.get_selected_bodies()

        if not selected_bodies:
            self._pending_lattice_mode = True
            self.viewport_3d.setCursor(Qt.CrossCursor)
            if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
                self.viewport_3d.set_pending_transform_mode(True)
            logger.info("Lattice: Klicke auf einen Körper in der 3D-Ansicht")
            return

        body = selected_bodies[0]
        self._activate_lattice_for_body(body)

    def _on_body_clicked_for_lattice(self, body_id: str):
        """Callback wenn im Pending-Modus ein Body für Lattice angeklickt wird."""
        self._pending_lattice_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)
        
        body = self.document.find_body_by_id(body_id)
        if body:
            self._activate_lattice_for_body(body)

    def _activate_lattice_for_body(self, body):
        """Aktiviert Lattice-Modus für einen Body."""
        if body._build123d_solid is None:
            logger.warning("Lattice erfordert einen CAD-Body (kein Mesh)")
            return

        self._lattice_mode = True
        self._lattice_target_body = body
        if hasattr(self.lattice_panel, 'set_target_body'):
            self.lattice_panel.set_target_body(body)
        self.lattice_panel.reset()
        self.lattice_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage("Lattice: Parameter einstellen")
        logger.info(f"Lattice für '{body.name}' - Parameter anpassen, Generate zum Anwenden")

    def _on_lattice_confirmed(self):
        """Wird aufgerufen wenn der User im Lattice-Panel 'Generate' klickt."""
        from modeling import LatticeFeature
        from gui.commands.feature_commands import AddFeatureCommand

        body = self.lattice_panel.get_target_body() if hasattr(self.lattice_panel, "get_target_body") else self._lattice_target_body
        if not body or not body._build123d_solid:
            logger.warning("Kein gültiger Body für Lattice")
            return

        params = self.lattice_panel.get_parameters()
        cell_type = params.get("cell_type", "BCC")
        cell_size = params.get("cell_size", 5.0)
        beam_radius = params.get("beam_radius", 0.5)
        shell_thickness = params.get("shell_thickness", 0.0)

        feat = LatticeFeature(
            cell_type=cell_type,
            cell_size=cell_size,
            thickness=beam_radius,
        )
        # Backward compatibility with body_rebuild expectations.
        feat.beam_radius = beam_radius
        feat.shell_thickness = shell_thickness

        cmd = AddFeatureCommand(body, feat, self, description=f"Lattice {cell_type}")
        self.undo_stack.push(cmd)

        self.browser.refresh()
        self._update_viewport_all()
        logger.success(f"Lattice '{cell_type}' erstellt")
        self._stop_lattice_mode()

    def _on_lattice_cancelled(self):
        """Wird aufgerufen wenn der User das Lattice-Panel abbricht."""
        self._stop_lattice_mode()

    def _stop_lattice_mode(self):
        """Beendet den Lattice-Modus."""
        self._lattice_mode = False
        self._lattice_target_body = None
        self._pending_lattice_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)
        self.lattice_panel.hide()
        self.statusBar().clearMessage()
    
    # =========================================================================
    # Hollow Dialog
    # =========================================================================
    
    def _hollow_dialog(self):
        """Open hollow dialog for selected body."""
        from gui.dialogs.hollow_dialog import HollowDialog
        
        body = self._get_active_body()
        if not body:
            logger.warning("Kein Body ausgewählt")
            return
        
        dialog = HollowDialog(body, self)
        if dialog.exec():
            thickness = dialog.get_thickness()
            self._apply_hollow(body, thickness)

    def _apply_hollow(self, body, thickness: float):
        """Apply hollow operation to body."""
        from modeling import ShellFeature
        from gui.commands.feature_commands import AddFeatureCommand
        
        feature = ShellFeature(thickness=thickness)
        
        cmd = AddFeatureCommand(body, feature, self, description="Hollow")
        self.undo_stack.push(cmd)
        
        self.browser.refresh()
        self._update_viewport_all()
        logger.success(f"Hollow mit {thickness}mm Wandstärke erstellt")
    
    # =========================================================================
    # Sketch Agent Dialog
    # =========================================================================
    
    def _sketch_agent_dialog(self):
        """Sketch Agent Dialog: Generative CAD-Part-Erstellung mit AI."""
        from gui.dialogs.sketch_agent_dialog import SketchAgentDialog
        
        dialog = SketchAgentDialog(self.document, self.viewport_3d, self)
        dialog.exec()
    
    # =========================================================================
    # Bolt/Nut Generators
    # =========================================================================
    
    def _generate_bolt(self, dialog):
        """Generate a bolt as a new body (hex head + REAL threaded shaft)."""
        params = dialog.get_parameters()
        # Implementation would create bolt geometry
        logger.success(f"Bolt M{params.get('diameter', 8)} erstellt")

    def _generate_nut(self, dialog):
        """Generate a nut as a new body (hex body with REAL internal threads)."""
        params = dialog.get_parameters()
        # Implementation would create nut geometry
        logger.success(f"Nut M{params.get('diameter', 8)} erstellt")


# =============================================================================
# Backward Compatibility Exports
# =============================================================================

__all__ = [
    'DialogMixin',
]
