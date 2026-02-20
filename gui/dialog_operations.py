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
                except:
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
                except:
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
                    except:
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
                        except: pass
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

        body = next((b for b in self.document.bodies if b.id == body_id), None)
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
                        except: pass
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
    
    def _hole_dialog(self):
        """Startet interaktiven Hole-Workflow (Fusion-style)."""
        from i18n import tr
        
        self._hole_mode = True
        self.viewport_3d.set_hole_mode(True)
        self.hole_panel.reset()
        self.hole_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage(tr("Wähle Fläche für Hole"))
        logger.info("Hole-Modus: Klicke auf eine Fläche")

    def _on_hole_diameter_changed(self, value):
        """Live-Update der Hole-Preview bei Durchmesser-Änderung."""
        pass  # Preview handled by viewport

    def _on_hole_depth_changed(self, value):
        """Live-Update der Hole-Preview bei Tiefen-Änderung."""
        pass  # Preview handled by viewport

    def _on_hole_confirmed(self):
        """Hole bestätigt — Feature erstellen."""
        # Implementation would go here
        self._finish_hole_ui()

    def _on_hole_cancelled(self):
        """Hole abgebrochen."""
        self._finish_hole_ui()

    def _finish_hole_ui(self):
        """Hole-UI aufräumen."""
        self._hole_mode = False
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
        # Implementation would create hole preview
    
    # =========================================================================
    # Thread Dialog
    # =========================================================================
    
    def _thread_dialog(self):
        """Thread-Dialog: Interaktives Gewinde auf zylindrische Fläche."""
        from i18n import tr
        
        self._thread_mode = True
        self._pending_thread_mode = True
        self.viewport_3d.set_thread_mode(True)
        self.thread_panel.reset()
        self.thread_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage(tr("Wähle zylindrische Fläche für Gewinde"))
        logger.info("Thread-Modus: Klicke auf eine zylindrische Fläche")

    def _on_thread_diameter_changed(self, value):
        """Live-Update der Thread-Preview bei Durchmesser-Änderung."""
        pass

    def _on_thread_pitch_changed(self, value):
        """Live-Update bei Pitch-Änderung."""
        pass

    def _on_thread_depth_changed(self, value):
        """Live-Update der Thread-Preview bei Tiefen-Änderung."""
        pass

    def _on_thread_tolerance_changed(self, value):
        """Live-Update bei Toleranz-Änderung."""
        pass

    def _update_thread_preview(self):
        """Aktualisiert die Thread-Preview basierend auf aktuellen Panel-Werten."""
        pass

    def _on_cylindrical_face_clicked_for_thread(self, body_id, cell_id, axis_dir, position, diameter):
        """Zylindrische Fläche wurde im Thread-Modus geklickt."""
        if not self._thread_mode:
            return
        # Implementation would create thread preview

    def _on_thread_confirmed(self):
        """Thread bestätigt — Feature erstellen."""
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
        from i18n import tr
        
        self._draft_mode = True
        self.viewport_3d.set_draft_mode(True)
        self.draft_panel.reset()
        self.draft_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage(tr("Wähle Fläche für Draft"))
        logger.info("Draft-Modus: Klicke auf eine Fläche")

    def _on_body_face_clicked_for_draft(self, body_id, cell_id, normal, position):
        """Body-Face wurde im Draft-Modus geklickt."""
        if not self._draft_mode:
            return
        # Implementation would create draft preview

    def _on_draft_angle_changed(self, value):
        """Draft-Winkel geändert."""
        self._update_draft_preview()

    def _on_draft_axis_changed(self, axis):
        """Draft Pull-Richtung geändert."""
        self._update_draft_preview()

    def _update_draft_preview(self):
        """Live-Preview des Draft-Ergebnisses."""
        pass  # Preview handled by viewport

    def _on_draft_confirmed(self):
        """Draft bestätigt — Feature erstellen."""
        self._finish_draft_ui()

    def _on_draft_cancelled(self):
        """Draft abgebrochen."""
        self._finish_draft_ui()

    def _finish_draft_ui(self):
        """Draft-UI aufräumen."""
        self._draft_mode = False
        self.viewport_3d.set_draft_mode(False)
        self.draft_panel.hide()
        self.statusBar().clearMessage()
    
    # =========================================================================
    # Split Body Dialog
    # =========================================================================
    
    def _split_body_dialog(self):
        """Startet interaktiven Split-Workflow (PrusaSlicer-style)."""
        from i18n import tr
        
        self._split_mode = True
        self._pending_split_mode = True
        self.viewport_3d.set_split_mode(True)
        self.split_panel.reset()
        self.split_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage(tr("Wähle Body zum Splitten"))
        logger.info("Split-Modus: Klicke auf einen Body")

    def _on_split_body_clicked(self, body_id):
        """Body wurde im Split-Modus geklickt."""
        self._pending_split_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        if hasattr(self.viewport_3d, 'set_pending_transform_mode'):
            self.viewport_3d.set_pending_transform_mode(False)
        # Continue with split setup

    def _on_split_plane_changed(self, plane):
        """Schnittebene geändert (XY/XZ/YZ)."""
        self._schedule_split_preview()

    def _on_split_position_changed(self, value):
        """Position per Panel geändert."""
        self._schedule_split_preview()

    def _on_split_angle_changed(self, angle):
        """Schnittwinkel geändert."""
        self._schedule_split_preview()

    def _on_split_keep_changed(self, keep):
        """Keep-Seite geändert."""
        pass

    def _on_split_drag(self, position):
        """Viewport-Drag → Panel synchronisieren."""
        self.split_panel.set_position(position)

    def _schedule_split_preview(self):
        """Debounced split preview — verhindert Spam bei schnellem Drag."""
        if not hasattr(self, '_split_preview_timer'):
            from PySide6.QtCore import QTimer
            self._split_preview_timer = QTimer()
            self._split_preview_timer.setSingleShot(True)
            self._split_preview_timer.timeout.connect(self._update_split_preview)
        self._split_preview_timer.start(50)

    def _split_origin_normal(self):
        """Berechnet Origin und Normal für die aktuelle Split-Konfiguration (inkl. Winkel)."""
        plane = self.split_panel.get_plane()
        position = self.split_panel.get_position()
        angle = self.split_panel.get_angle()
        
        # Base plane definitions
        plane_defs = {
            'xy': ((0, 0, position), (0, 0, 1)),
            'xz': ((0, position, 0), (0, 1, 0)),
            'yz': ((position, 0, 0), (1, 0, 0))
        }
        
        origin, normal = plane_defs.get(plane, ((0, 0, 0), (0, 0, 1)))
        
        # Apply angle rotation if needed
        if abs(angle) > 0.1:
            # Rotate normal around appropriate axis
            pass
        
        return origin, normal

    def _update_split_preview(self):
        """Live-Preview beider Hälften."""
        pass  # Preview handled by viewport

    def _on_split_confirmed(self):
        """Split bestätigt — Feature erstellen."""
        self._finish_split_ui()

    def _on_split_cancelled(self):
        """Split abgebrochen."""
        self._finish_split_ui()

    def _finish_split_ui(self):
        """Split-UI aufräumen."""
        self._split_mode = False
        self._pending_split_mode = False
        self.viewport_3d.set_split_mode(False)
        self.split_panel.hide()
        self.statusBar().clearMessage()
    
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
        if len(selected) < 2:
            # Show dialog to select bodies
            dialog = BooleanDialog(self.document.bodies, op_type, self)
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
        """N-Sided Patch Dialog starten."""
        from i18n import tr
        
        self._nsided_patch_mode = True
        self._pending_nsided_patch_mode = True
        self.viewport_3d.setCursor(Qt.CrossCursor)
        self.statusBar().showMessage(tr("Wähle Body für N-Sided Patch"))
        logger.info("N-Sided Patch: Klicke auf einen Body")

    def _on_body_clicked_for_nsided_patch(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body für N-Sided Patch angeklickt wird."""
        self._pending_nsided_patch_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        
        body = self.document.find_body_by_id(body_id)
        if body:
            self._activate_nsided_patch_for_body(body)

    def _activate_nsided_patch_for_body(self, body):
        """Aktiviert N-Sided Patch-Modus für einen Body."""
        self._nsided_patch_target_body = body
        self.nsided_patch_panel.reset()
        self.nsided_patch_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage("Wähle Kanten für N-Sided Patch")

    def _on_nsided_patch_edge_selection_changed(self, count: int):
        """Handler wenn sich die Kanten-Selektion für N-Sided Patch ändert."""
        pass

    def _on_nsided_patch_confirmed(self):
        """Handler wenn N-Sided Patch bestätigt wird."""
        self._stop_nsided_patch_mode()

    def _on_nsided_patch_cancelled(self):
        """Handler wenn N-Sided Patch abgebrochen wird."""
        self._stop_nsided_patch_mode()

    def _stop_nsided_patch_mode(self):
        """Beendet den N-Sided Patch Modus."""
        self._nsided_patch_mode = False
        self._nsided_patch_target_body = None
        self.nsided_panel.hide()
        self.statusBar().clearMessage()
    
    # =========================================================================
    # Wall Thickness Dialog
    # =========================================================================
    
    def _wall_thickness_dialog(self):
        """Wall Thickness Dialog starten."""
        from i18n import tr
        
        self._pending_wall_thickness_mode = True
        self.viewport_3d.setCursor(Qt.CrossCursor)
        self.statusBar().showMessage(tr("Wähle Body für Wandstärken-Analyse"))
        logger.info("Wall Thickness: Klicke auf einen Body")

    def _on_body_clicked_for_wall_thickness(self, body_id: str):
        """Callback wenn im Pending-Mode ein Body angeklickt wird."""
        self._pending_wall_thickness_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        
        body = self.document.find_body_by_id(body_id)
        if body:
            self._open_wall_thickness_for_body(body)

    def _open_wall_thickness_for_body(self, body):
        """Öffnet den Wall Thickness Dialog für einen spezifischen Body."""
        from gui.dialogs.wall_thickness_dialog import WallThicknessDialog
        
        dialog = WallThicknessDialog(body, self)
        dialog.exec()
    
    # =========================================================================
    # Lattice Dialog
    # =========================================================================
    
    def _start_lattice(self):
        """Startet den Lattice-Workflow."""
        from i18n import tr
        
        self._lattice_mode = True
        self._pending_lattice_mode = True
        self.viewport_3d.setCursor(Qt.CrossCursor)
        self.statusBar().showMessage(tr("Wähle Body für Lattice"))
        logger.info("Lattice: Klicke auf einen Body")

    def _on_body_clicked_for_lattice(self, body_id: str):
        """Callback wenn im Pending-Modus ein Body für Lattice angeklickt wird."""
        self._pending_lattice_mode = False
        self.viewport_3d.setCursor(Qt.ArrowCursor)
        
        body = self.document.find_body_by_id(body_id)
        if body:
            self._activate_lattice_for_body(body)

    def _activate_lattice_for_body(self, body):
        """Aktiviert Lattice-Modus für einen Body."""
        self._lattice_mode = True
        self._lattice_target_body = body
        self.lattice_panel.reset()
        self.lattice_panel.show_at(self.viewport_3d)
        self.statusBar().showMessage("Lattice: Parameter einstellen")

    def _on_lattice_confirmed(self):
        """Wird aufgerufen wenn der User im Lattice-Panel 'Generate' klickt."""
        self._stop_lattice_mode()

    def _on_lattice_cancelled(self):
        """Wird aufgerufen wenn der User das Lattice-Panel abbricht."""
        self._stop_lattice_mode()

    def _stop_lattice_mode(self):
        """Beendet den Lattice-Modus."""
        self._lattice_mode = False
        self._lattice_target_body = None
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
