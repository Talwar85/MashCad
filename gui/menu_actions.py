"""
MashCAD Menu Actions Module
===========================

Extracted from main_window.py (AR-004: Phase 1 Split).

This module contains menu-related actions and handlers as a mixin class.
Maintains backward compatibility by being imported into MainWindow.

Usage:
    class MainWindow(MenuActionsMixin, QMainWindow):
        pass
"""

import os
from typing import Optional, List, TYPE_CHECKING

from loguru import logger
from PySide6.QtWidgets import (
    QFileDialog, QMessageBox, QDialog, QProgressDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence

if TYPE_CHECKING:
    from modeling import Document, Body
    from gui.browser import ProjectBrowser


class MenuActionsMixin:
    """
    Mixin class containing menu-related actions for MainWindow.
    
    This class provides:
    - File menu actions (new, open, save, export, import)
    - Edit menu actions (undo, redo, parameters)
    - Help menu actions (about, language)
    - Recent files management
    
    All methods assume they are called within a MainWindow context
    and access MainWindow attributes via `self`.
    """
    
    # =========================================================================
    # File Menu Actions
    # =========================================================================
    
    def _new_project(self):
        """Create a new empty project."""
        from modeling import Document
        
        self.document = Document("Projekt1")
        self._setup_tnp_debug_callback()  # TNP v4.0: Callback neu registrieren
        self.browser.set_document(self.document)
        self._set_mode("3d")
        self._current_project_path = None
        self.setWindowTitle("MashCAD")
        logger.info("Neues Projekt erstellt")
    
    def _save_project(self):
        """Save the current project."""
        # If path is known, save directly
        if hasattr(self, '_current_project_path') and self._current_project_path:
            self._do_save_project(self._current_project_path)
        else:
            self._save_project_as()
    
    def _save_project_as(self):
        """Save the project with a new name."""
        from i18n import tr
        
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Projekt speichern"),
            "",
            "MashCAD Project (*.mshcad);;All Files (*)"
        )
        if path:
            self._do_save_project(path)
    
    def _do_save_project(self, path: str):
        """Execute the actual save operation."""
        from i18n import tr
        from config.recent_files import add_recent_file
        
        try:
            if self.document.save_project(path):
                self._current_project_path = path
                self.setWindowTitle(f"MashCAD - {os.path.basename(path)}")
                add_recent_file(path)
                self._update_recent_files_menu()
                logger.success(f"Projekt gespeichert: {path}")
            else:
                QMessageBox.critical(self, "Fehler", "Projekt konnte nicht gespeichert werden.")
        except Exception as e:
            logger.error(f"Fehler beim Speichern: {e}")
            QMessageBox.critical(self, "Fehler", f"Speichern fehlgeschlagen:\n{e}")
    
    def _open_project(self):
        """Open an existing project."""
        from i18n import tr
        from config.recent_files import add_recent_file
        
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Projekt öffnen"),
            "",
            "MashCAD Project (*.mshcad);;All Files (*)"
        )
        if not path:
            return
        
        self._load_project_from_path(path)
    
    def _load_project_from_path(self, path: str):
        """Load a project from the given path."""
        from modeling import Document
        from config.recent_files import add_recent_file
        
        try:
            doc = Document.load_project(path)
            if doc:
                # Replace old document
                self.document = doc
                self._setup_tnp_debug_callback()  # TNP v4.0: Re-register callback
                self._current_project_path = path
                
                # Update UI
                self.browser.set_document(doc)
                self.browser.refresh()
                
                # Update viewport - direct call for immediate update
                self._update_viewport_all_impl()
                
                # Update sketches in viewport
                self.viewport_3d.set_sketches(self.browser.get_visible_sketches())
                
                # Set active sketch
                if doc.active_sketch:
                    self.active_sketch = doc.active_sketch
                    self.sketch_editor.sketch = doc.active_sketch
                
                self.setWindowTitle(f"MashCAD - {os.path.basename(path)}")
                
                # Render construction planes
                self._render_construction_planes()
                
                # Update TNP stats
                self._update_tnp_stats()
                
                add_recent_file(path)
                self._update_recent_files_menu()
                logger.success(f"Projekt geladen: {path}")
            else:
                QMessageBox.critical(self, "Fehler", "Projekt konnte nicht geladen werden.")
        except Exception as e:
            logger.error(f"Fehler beim Laden: {e}")
            QMessageBox.critical(self, "Fehler", f"Laden fehlgeschlagen:\n{e}")
    
    def _update_recent_files_menu(self):
        """Update the recent files submenu."""
        from i18n import tr
        from config.recent_files import get_recent_files
        
        self._recent_menu.clear()
        recent = get_recent_files()
        if not recent:
            action = self._recent_menu.addAction(tr("No recent files"))
            action.setEnabled(False)
            return
        for path in recent:
            display = os.path.basename(path)
            action = self._recent_menu.addAction(display)
            action.setToolTip(path)
            action.triggered.connect(lambda checked=False, p=path: self._open_recent_file(p))
    
    def _open_recent_file(self, path: str):
        """Open a recent project file."""
        if not os.path.exists(path):
            logger.warning(f"Datei nicht gefunden: {path}")
            self._update_recent_files_menu()
            return
        self._load_project_from_path(path)
    
    # =========================================================================
    # Export Actions
    # =========================================================================
    
    def _export_stl(self):
        """STL Export with Quality-Dialog and Surface Texture Support."""
        from i18n import tr
        from PySide6.QtWidgets import QDialog
        from gui.dialogs.stl_export_dialog import STLExportDialog
        
        bodies = self._get_export_candidates()
        if not bodies:
            logger.warning("Keine sichtbaren Körper zum Exportieren.")
            return
        
        # Show export settings dialog
        dlg = STLExportDialog(parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        
        linear_defl = dlg.linear_deflection
        angular_tol = dlg.angular_tolerance
        is_binary = dlg.is_binary
        scale = dlg.scale_factor
        
        path, _ = QFileDialog.getSaveFileName(self, tr("STL exportieren"), "", "STL Files (*.stl)")
        if not path:
            return
        
        # PERFORMANCE Phase 6: Async export for large meshes
        estimated_complexity = len(bodies) * (1.0 / max(0.01, linear_defl))
        use_async = estimated_complexity > 100 or len(bodies) > 3
        
        if use_async:
            self._export_stl_async(bodies, path, linear_defl, angular_tol, is_binary, scale)
            return
        
        self._export_stl_sync(bodies, path, linear_defl, angular_tol, is_binary, scale, dlg.quality_slider.value())
    
    def _export_stl_sync(self, bodies, filepath, linear_defl, angular_tol, is_binary, scale, quality_value):
        """Synchronous STL export."""
        try:
            import pyvista as pv
            import numpy as np
            from modeling.surface_texture_feature import SurfaceTextureFeature
            from config.feature_flags import is_enabled
            
            HAS_TEXTURE_EXPORT = is_enabled("texture_export")
            HAS_BUILD123D = True  # Assume available
            
            merged_polydata = None
            texture_applied_count = 0
            
            for body in bodies:
                mesh_to_add = None
                
                # Check for SurfaceTextureFeatures
                has_textures = HAS_TEXTURE_EXPORT and any(
                    isinstance(f, SurfaceTextureFeature) and not f.suppressed
                    for f in getattr(body, 'features', [])
                )
                
                if has_textures and HAS_BUILD123D and hasattr(body, '_build123d_solid') and body._build123d_solid:
                    try:
                        from modeling.textured_tessellator import TexturedTessellator
                        from modeling.texture_exporter import apply_textures_to_body
                        
                        logger.info(f"Tesselliere '{body.name}' mit Textur-Mapping...")
                        mesh, face_mappings = TexturedTessellator.tessellate_with_face_map(
                            body._build123d_solid,
                            quality=linear_defl,
                            angular_tolerance=angular_tol
                        )
                        
                        if mesh is not None:
                            mesh, results = apply_textures_to_body(mesh, body, face_mappings)
                            
                            for result in results:
                                if result.status == "error":
                                    logger.error(f"Textur-Fehler: {result.message}")
                                elif result.status == "warning":
                                    logger.warning(f"Textur-Warnung: {result.message}")
                                elif result.status == "success":
                                    texture_applied_count += 1
                            
                            mesh_to_add = mesh
                    except Exception as e:
                        logger.warning(f"Texture-Export für '{body.name}' fehlgeschlagen: {e}")
                        has_textures = False
                
                # Standard tessellation
                if mesh_to_add is None and HAS_BUILD123D and hasattr(body, '_build123d_solid') and body._build123d_solid:
                    try:
                        from modeling.cad_tessellator import CADTessellator
                        verts, faces_tris = CADTessellator.tessellate_for_export(
                            body._build123d_solid,
                            linear_deflection=linear_defl,
                            angular_tolerance=angular_tol
                        )
                        if verts and faces_tris:
                            faces = []
                            for t in faces_tris:
                                faces.extend([3] + list(t))
                            mesh_to_add = pv.PolyData(np.array(verts), np.array(faces))
                    except Exception as e:
                        logger.warning(f"Build123d Tessellierung fehlgeschlagen: {e}")
                
                if mesh_to_add is None:
                    mesh_to_add = self.viewport_3d.get_body_mesh(body.id)
                
                if mesh_to_add:
                    if merged_polydata is None:
                        merged_polydata = mesh_to_add
                    else:
                        merged_polydata = merged_polydata.merge(mesh_to_add)
            
            if merged_polydata:
                # Apply unit scaling if needed
                if abs(scale - 1.0) > 1e-6:
                    merged_polydata.points *= scale
                
                merged_polydata.save(filepath, binary=is_binary)
                qual_name = ["Draft", "Standard", "Fine", "Ultra"][quality_value]
                if texture_applied_count > 0:
                    logger.success(f"STL gespeichert: {filepath} ({qual_name}, {texture_applied_count} Texturen)")
                else:
                    n_tri = merged_polydata.n_cells
                    logger.success(f"STL gespeichert: {filepath} ({qual_name}, {n_tri:,} Dreiecke)")
            else:
                logger.error("Konnte keine Mesh-Daten generieren.")
                
        except Exception as e:
            logger.error(f"STL Export Fehler: {e}")
            import traceback
            traceback.print_exc()
    
    def _export_stl_async(self, bodies, filepath, linear_defl, angular_tol, is_binary, scale):
        """Async STL Export with Progress-Dialog (Phase 6)."""
        from gui.workers.export_worker import STLExportWorker
        
        # Create progress dialog
        progress = QProgressDialog(
            "Exportiere STL...",
            "Abbrechen",
            0, 100,
            self
        )
        progress.setWindowTitle("STL Export")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        
        # Create worker
        self._stl_export_worker = STLExportWorker(
            bodies, filepath, linear_defl, angular_tol, is_binary, scale
        )
        
        # Connect signals
        self._stl_export_worker.progress.connect(progress.setValue)
        self._stl_export_worker.finished.connect(lambda: self._on_stl_export_finished(progress, filepath))
        self._stl_export_worker.error.connect(lambda msg: self._on_stl_export_error(progress, msg))
        progress.canceled.connect(self._stl_export_worker.cancel)
        
        # Start export
        self._stl_export_worker.start()
    
    def _on_stl_export_finished(self, progress, filepath):
        """Handle STL export completion."""
        progress.close()
        logger.success(f"STL gespeichert: {filepath}")
        self._stl_export_worker = None
    
    def _on_stl_export_error(self, progress, message):
        """Handle STL export error."""
        progress.close()
        logger.error(f"STL Export Fehler: {message}")
        QMessageBox.critical(self, "Export Fehler", message)
        self._stl_export_worker = None
    
    def _export_step(self):
        """STEP Export."""
        from i18n import tr
        from gui.workers.export_worker import STEPExportWorker
        
        bodies = self._get_export_candidates()
        if not bodies:
            logger.warning("Keine sichtbaren Körper zum Exportieren.")
            return
        
        path, _ = QFileDialog.getSaveFileName(self, tr("STEP exportieren"), "", "STEP Files (*.step *.stp)")
        if not path:
            return
        
        # Use async export
        progress = QProgressDialog(
            "Exportiere STEP...",
            "Abbrechen",
            0, 100,
            self
        )
        progress.setWindowTitle("STEP Export")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        
        self._step_export_worker = STEPExportWorker(bodies, path)
        self._step_export_worker.progress.connect(progress.setValue)
        self._step_export_worker.finished.connect(lambda: self._on_step_export_finished(progress, path))
        self._step_export_worker.error.connect(lambda msg: self._on_step_export_error(progress, msg))
        progress.canceled.connect(self._step_export_worker.cancel)
        self._step_export_worker.start()
    
    def _on_step_export_finished(self, progress, filepath):
        """Handle STEP export completion."""
        progress.close()
        logger.success(f"STEP gespeichert: {filepath}")
        self._step_export_worker = None
    
    def _on_step_export_error(self, progress, message):
        """Handle STEP export error."""
        progress.close()
        logger.error(f"STEP Export Fehler: {message}")
        QMessageBox.critical(self, "Export Fehler", message)
        self._step_export_worker = None
    
    def _export_3mf(self):
        """3MF Export via ExportController."""
        if hasattr(self, 'export_controller'):
            self.export_controller.export_3mf()
        else:
            logger.warning("ExportController nicht verfügbar")
    
    def _export_svg(self):
        """Export visible bodies as SVG."""
        from i18n import tr
        
        bodies = self._get_export_candidates()
        if not bodies:
            logger.warning("Keine sichtbaren Körper zum Exportieren.")
            return
        
        path, _ = QFileDialog.getSaveFileName(self, tr("SVG exportieren"), "", "SVG Files (*.svg)")
        if not path:
            return
        
        try:
            # Get projection from viewport
            if hasattr(self.viewport_3d, 'export_svg'):
                self.viewport_3d.export_svg(bodies, path)
                logger.success(f"SVG gespeichert: {path}")
            else:
                logger.warning("SVG Export nicht verfügbar")
        except Exception as e:
            logger.error(f"SVG Export Fehler: {e}")
    
    # =========================================================================
    # Import Actions
    # =========================================================================
    
    def _import_step(self):
        """Import STEP file as new body."""
        from i18n import tr
        
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("STEP importieren"),
            "",
            "STEP Files (*.step *.stp);;All Files (*)"
        )
        if not path:
            return
        
        try:
            from modeling.step_io import import_step
            
            progress = QProgressDialog(
                "Importiere STEP...",
                "Abbrechen",
                0, 100,
                self
            )
            progress.setWindowTitle("STEP Import")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(10)
            
            bodies = import_step(path, self.document)
            
            progress.setValue(90)
            
            if bodies:
                self.browser.refresh()
                self._update_viewport_all_impl()
                logger.success(f"STEP importiert: {path} ({len(bodies)} Körper)")
            else:
                logger.warning("Keine Körper aus STEP-Datei importiert")
            
            progress.close()
            
        except Exception as e:
            logger.error(f"STEP Import Fehler: {e}")
            QMessageBox.critical(self, "Import Fehler", f"STEP Import fehlgeschlagen:\n{e}")

    def _import_cadquery_script(self):
        """Import CadQuery/Build123d script as new body."""
        from i18n import tr

        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("CadQuery Script importieren"),
            "",
            "Python Files (*.py);;All Files (*)"
        )
        if not path:
            return

        try:
            from modeling.cadquery_importer import CadQueryImporter
            from modeling import Body

            progress = QProgressDialog(
                "Importiere CadQuery Script...",
                "Abbrechen",
                0, 100,
                self
            )
            progress.setWindowTitle("CadQuery Import")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(10)

            importer = CadQueryImporter(self.document)
            result = importer.execute_script(path)

            progress.setValue(50)

            if result.success and result.solids:
                # Create bodies from solids
                for solid in result.solids:
                    body = Body.from_solid(solid, name=result.name, document=self.document)
                    self.document.add_body(body)

                progress.setValue(90)

                self.browser.refresh()
                self._update_viewport_all_impl()
                logger.success(f"CadQuery Script importiert: {path} ({len(result.solids)} Körper)")

                if result.warnings:
                    for warning in result.warnings:
                        logger.warning(f"CadQuery: {warning}")
            else:
                if result.errors:
                    error_msg = "\n".join(result.errors)
                    logger.error(f"CadQuery Import Fehler: {error_msg}")
                    QMessageBox.critical(self, "Import Fehler", f"Script fehlgeschlagen:\n{error_msg}")
                else:
                    logger.warning("Keine Körper aus Script generiert")
                    QMessageBox.information(self, "Import", "Script wurde ausgeführt aber keine Körper generiert.")

            progress.close()

        except Exception as e:
            logger.error(f"CadQuery Import Fehler: {e}")
            QMessageBox.critical(self, "Import Fehler", f"CadQuery Import fehlgeschlagen:\n{e}")

    def _import_svg(self):
        """Import SVG as sketch geometry."""
        from i18n import tr
        
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("SVG importieren"),
            "",
            "SVG Files (*.svg);;All Files (*)"
        )
        if not path:
            return
        
        try:
            # Import into active sketch or create new one
            if self.active_sketch:
                sketch = self.active_sketch
            else:
                # Create new sketch
                sketch = self.document.new_sketch("SVG Import")
                self.active_sketch = sketch
            
            # Parse SVG and add geometry
            # NOTE: svg_import module not yet implemented - placeholder for future SVG parsing
            logger.warning(f"SVG Import noch nicht implementiert: {path}")
            QMessageBox.information(
                self,
                tr("Nicht implementiert"),
                tr("SVG Import wird in einer zukünftigen Version verfügbar sein.")
            )
            return
            
            # Update UI
            if hasattr(self, 'sketch_editor'):
                self.sketch_editor.request_update()
            self.browser.refresh()
            
            logger.success(f"SVG importiert: {path}")
            
        except Exception as e:
            logger.error(f"SVG Import Fehler: {e}")
            QMessageBox.critical(self, "Import Fehler", f"SVG Import fehlgeschlagen:\n{e}")
    
    def _import_mesh_dialog(self):
        """Import STL/OBJ files as new body."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Mesh importieren",
            "",
            "Mesh Files (*.stl *.obj *.ply);;All Files (*.*)"
        )
        
        if not path:
            return
        
        try:
            import pyvista as pv
            
            # Load file
            mesh = pv.read(path)
            
            if not mesh or mesh.n_cells == 0:
                logger.warning("Fehler: Leeres Mesh oder ungültiges Format.")
                return
            
            # Create new body
            filename = os.path.basename(path)
            new_body = self.document.new_body(name=filename)
            
            # Assign mesh directly (as VTK object)
            new_body.vtk_mesh = mesh
            
            # Update viewport
            self.viewport_3d.add_body(
                bid=new_body.id,
                name=new_body.name,
                mesh_obj=mesh,
                color=(0.7, 0.7, 0.7)
            )
            
            # Update browser
            self.browser.refresh()
            
            logger.info(f"Importiert: {filename} ({mesh.n_cells} Faces)")
            
        except Exception as e:
            logger.error(f"Import fehlgeschlagen: {e}")
    
    # =========================================================================
    # Edit Menu Actions
    # =========================================================================
    
    def _smart_undo(self):
        """
        Smart Undo: Prioritizes Sketch-Editor Undo when active.
        
        If in sketch mode: Calls sketch_editor.undo()
        Otherwise: Calls 3D undo_stack.undo()
        """
        if self.mode == "sketch" and hasattr(self, 'sketch_editor') and self.sketch_editor:
            self.sketch_editor.undo()
            logger.debug("Smart Undo: Sketch-Editor")
        else:
            if self.undo_stack.canUndo():
                self.undo_stack.undo()
                self._update_tnp_stats()
                logger.debug("Smart Undo: 3D UndoStack")
    
    def _smart_redo(self):
        """
        Smart Redo: Prioritizes Sketch-Editor Redo when active.
        
        If in sketch mode: Calls sketch_editor.redo()
        Otherwise: Calls 3D undo_stack.redo()
        """
        if self.mode == "sketch" and hasattr(self, 'sketch_editor') and self.sketch_editor:
            self.sketch_editor.redo()
            logger.debug("Smart Redo: Sketch-Editor")
        else:
            if self.undo_stack.canRedo():
                self.undo_stack.redo()
                self._update_tnp_stats()
                logger.debug("Smart Redo: 3D UndoStack")
    
    def _show_parameters_dialog(self):
        """Open the parameter dialog."""
        from core.parameters import get_parameters
        from gui.parameter_dialog import ParameterDialog
        
        params = get_parameters()
        dialog = ParameterDialog(params, self)
        dialog.parameters_changed.connect(self._on_parameters_changed)
        dialog.exec_()
    
    def _on_parameters_changed(self):
        """React to parameter changes — re-solve constraints with formulas."""
        from sketcher.constraints import resolve_constraint_value
        
        # 1. Update all sketches with formula constraints
        if hasattr(self, 'document') and self.document:
            for sketch in getattr(self.document, 'sketches', []):
                needs_solve = False
                for c in sketch.constraints:
                    if c.formula:
                        resolve_constraint_value(c)
                        needs_solve = True
                if needs_solve:
                    sketch.solve()
        
        # 2. Update sketch editor
        if hasattr(self, 'sketch_editor') and self.sketch_editor:
            self.sketch_editor.request_update()
        
        # 3. Update 3D features with formulas
        if hasattr(self, 'document') and self.document:
            for body in getattr(self.document, 'bodies', []):
                if self._resolve_feature_formulas(body):
                    body._rebuild()
                    body.invalidate_mesh()
        
        logger.info("Parameter aktualisiert — Constraints und Features neu berechnet")
    
    def _resolve_feature_formulas(self, body) -> bool:
        """Resolve feature formulas. Returns True if something changed."""
        from core.parameters import get_parameters
        
        params = get_parameters()
        if not params:
            return False
        
        changed = False
        for feat in getattr(body, 'features', []):
            # Check all *_formula fields
            for attr in dir(feat):
                if attr.endswith('_formula'):
                    formula = getattr(feat, attr, None)
                    if formula:
                        value_attr = attr[:-8]  # Remove '_formula'
                        try:
                            params.set("__resolve__", formula)
                            try:
                                val = params.get("__resolve__")
                                if val is not None and getattr(feat, value_attr, None) != val:
                                    setattr(feat, value_attr, val)
                                    changed = True
                            finally:
                                try:
                                    params.delete("__resolve__")
                                except Exception:
                                    pass
                        except Exception as e:
                            logger.warning(f"Feature-Formel '{formula}' für {value_attr} fehlgeschlagen: {e}")
        return changed
    
    # =========================================================================
    # Help Menu Actions
    # =========================================================================
    
    def _change_language(self):
        """Change language — saves and shows restart hint."""
        from gui.language_dialog import ask_language_switch
        from i18n import get_language
        
        old_lang = get_language()
        chosen = ask_language_switch(self)
        if chosen and chosen != old_lang:
            QMessageBox.information(
                self,
                "Language Changed" if chosen == "en" else "Sprache geändert",
                "Please restart MashCAD to apply the new language."
                if chosen == "en" else
                "Bitte starte MashCAD neu, um die neue Sprache zu übernehmen."
            )
    
    def _show_about(self):
        """Show About dialog."""
        from i18n import tr
        from config.version import APP_NAME, VERSION, COPYRIGHT
        
        QMessageBox.about(self, tr("Über MashCad"),
            f"<h2>{APP_NAME}</h2>"
            f"<p>Version {VERSION}</p>"
            f"<p>Schlankes parametrisches CAD für 3D-Druck</p>"
            f"<p>{COPYRIGHT}</p>"
            f"<p><b>Features:</b></p>"
            f"<ul>"
            f"<li>2D Sketch mit Constraints</li>"
            f"<li>3D Extrusion</li>"
            f"<li>PyVista/VTK Rendering</li>"
            f"</ul>"
        )
    
    def _start_tutorial(self):
        """Start the complete workflow tutorial for beginners."""
        from gui.tutorial_complete_workflow import start_complete_tutorial
        self._tutorial = start_complete_tutorial(self)
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _get_export_candidates(self) -> List:
        """Get list of bodies eligible for export."""
        candidates = []
        
        # Get visible bodies from browser
        if hasattr(self, 'browser'):
            for body in getattr(self.document, 'bodies', []):
                if self.browser.body_visibility.get(body.id, True):
                    candidates.append(body)
        
        return candidates


# =============================================================================
# Backward Compatibility Exports
# =============================================================================

# These exports allow direct import of functions for testing
__all__ = [
    'MenuActionsMixin',
]
