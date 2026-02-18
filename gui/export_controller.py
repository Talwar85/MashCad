"""
ExportController - UI-Orchestrierung für Export/Import Workflows
=================================================================

W17 Paket C (AR-004 Phase-2): Extrahiert Export/Import-Logik aus MainWindow.
Zuständig für:
- STL Export (sync/async)
- STEP Export/Import
- SVG Export/Import
- Mesh Import (STL, OBJ, etc.)

Author: GLM 4.7 (UX/Workflow Delivery Cell)
Date: 2026-02-16
Branch: feature/v1-ux-aiB
"""

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QFileDialog, QMessageBox
from loguru import logger
from pathlib import Path
from typing import List, Optional, Callable

from i18n import tr


class STLExportWorker(QThread):
    """Worker thread for async STL export."""
    finished = Signal(bool, str)  # success, message
    progress = Signal(str)
    
    def __init__(self, parent, export_func, bodies, filepath, linear_defl, angular_tol, is_binary, scale):
        super().__init__(parent)
        self.export_func = export_func
        self.bodies = bodies
        self.filepath = filepath
        self.linear_defl = linear_defl
        self.angular_tol = angular_tol
        self.is_binary = is_binary
        self.scale = scale
        
    def run(self):
        try:
            self.progress.emit(tr("Exportiere STL..."))
            success = self.export_func(
                self.bodies, self.filepath,
                self.linear_defl, self.angular_tol,
                self.is_binary, self.scale
            )
            if success:
                self.finished.emit(True, tr("STL Export erfolgreich"))
            else:
                self.finished.emit(False, tr("STL Export fehlgeschlagen"))
        except Exception as e:
            logger.exception("STL Export Error")
            self.finished.emit(False, str(e))


class ExportController(QObject):
    """
    Controller für Export/Import Operationen.
    
    Kapselt alle Export/Import-Workflows und delegiert an MainWindow
    für UI-Interaktionen.
    """
    
    # Signals for UI updates
    export_started = Signal(str)  # format
    export_finished = Signal(bool, str)  # success, message
    import_started = Signal(str)  # format
    import_finished = Signal(bool, str, object)  # success, message, result
    
    def __init__(self, main_window):
        """
        Args:
            main_window: MainWindow Instanz (für UI-Zugriff)
        """
        super().__init__(None)  # QObject Parent ist None, MainWindow wird separat gespeichert
        self._mw = main_window
        self._current_worker = None
        
    def export_stl(self, bodies: Optional[List] = None) -> bool:
        """
        Exportiert Bodies als STL.
        
        Args:
            bodies: Liste der zu exportierenden Bodies (None = alle sichtbaren)
            
        Returns:
            bool: True wenn Export gestartet wurde
        """
        # Default: alle sichtbaren Bodies
        if bodies is None:
            bodies = self._get_visible_bodies()
            
        if not bodies:
            QMessageBox.warning(
                None, 
                tr("Export Fehler"), 
                tr("Keine sichtbaren Bodies zum Exportieren.")
            )
            return False
            
        # File Dialog
        filepath, _ = QFileDialog.getSaveFileName(
            self._mw,
            tr("Export als STL"),
            "",
            "STL Files (*.stl);;Binary STL (*.stl)"
        )
        
        if not filepath:
            return False
            
        # Ensure .stl extension
        if not filepath.lower().endswith('.stl'):
            filepath += '.stl'
            
        # TODO: Dialog für Export-Optionen (linear_defl, angular_tol, etc.)
        # Für jetzt: Standardwerte
        linear_defl = 0.1
        angular_tol = 0.5
        is_binary = True
        scale = 1.0
        
        self.export_started.emit("STL")
        
        # Async Export
        self._export_stl_async(bodies, filepath, linear_defl, angular_tol, is_binary, scale)
        return True
        
    def _export_stl_async(self, bodies, filepath, linear_defl, angular_tol, is_binary, scale):
        """Startet asynchronen STL Export."""
        # Get export function from MainWindow (fallback implementation)
        export_func = getattr(self._mw, '_export_stl_async_impl', None)
        if export_func is None:
            # Fallback: sync export
            try:
                self._do_stl_export(bodies, filepath, linear_defl, angular_tol, is_binary, scale)
                self.export_finished.emit(True, tr("STL Export erfolgreich"))
            except Exception as e:
                logger.exception("STL Export Error")
                self.export_finished.emit(False, str(e))
            return
            
        self._current_worker = STLExportWorker(
            self, export_func, bodies, filepath,
            linear_defl, angular_tol, is_binary, scale
        )
        self._current_worker.finished.connect(self._on_export_finished)
        self._current_worker.start()
        
    def _on_export_finished(self, success: bool, message: str):
        """Handler für Export-Fertigstellung."""
        self._current_worker = None
        self.export_finished.emit(success, message)
        
        if success:
            self._mw.statusBar().showMessage(tr("STL Export erfolgreich"), 5000)
        else:
            QMessageBox.warning(None, tr("Export Fehler"), message)
            
    def export_step(self) -> bool:
        """
        Exportiert als STEP.
        
        Returns:
            bool: True wenn Export erfolgreich
        """
        bodies = self._get_visible_bodies()
        if not bodies:
            QMessageBox.warning(
                None,
                tr("Export Fehler"),
                tr("Keine sichtbaren Bodies zum Exportieren.")
            )
            return False
            
        filepath, _ = QFileDialog.getSaveFileName(
            self._mw,
            tr("Export als STEP"),
            "",
            "STEP Files (*.stp *.step)"
        )
        
        if not filepath:
            return False
            
        # Delegate to MainWindow implementation
        if hasattr(self._mw, '_export_step_impl'):
            return self._mw._export_step_impl(bodies, filepath)
            
        # Fallback: Info message
        QMessageBox.information(
            None,
            tr("Nicht implementiert"),
            tr("STEP Export wird von MainWindow nicht unterstützt.")
        )
        return False
        
    def export_svg(self) -> bool:
        """
        Exportiert aktiven Sketch als SVG.
        
        Returns:
            bool: True wenn Export erfolgreich
        """
        if not hasattr(self._mw, 'sketch_editor') or not self._mw.sketch_editor:
            QMessageBox.warning(
                None,
                tr("Export Fehler"),
                tr("Kein aktiver Sketch zum Exportieren.")
            )
            return False
            
        filepath, _ = QFileDialog.getSaveFileName(
            self._mw,
            tr("Export als SVG"),
            "",
            "SVG Files (*.svg)"
        )
        
        if not filepath:
            return False
            
        # Delegate to MainWindow or SketchEditor
        if hasattr(self._mw, '_export_svg_impl'):
            return self._mw._export_svg_impl(filepath)
            
        # Fallback: SketchEditor direkt
        try:
            sketch = self._mw.sketch_editor.sketch
            if sketch and hasattr(sketch, 'to_svg'):
                sketch.to_svg(filepath)
                self._mw.statusBar().showMessage(tr("SVG Export erfolgreich"), 5000)
                return True
        except Exception as e:
            logger.exception("SVG Export Error")
            QMessageBox.warning(None, tr("Export Fehler"), str(e))
            
        return False
        
    def import_svg(self) -> bool:
        """
        Importiert SVG als Sketch.
        
        Returns:
            bool: True wenn Import erfolgreich
        """
        filepath, _ = QFileDialog.getOpenFileName(
            self._mw,
            tr("Import SVG"),
            "",
            "SVG Files (*.svg)"
        )
        
        if not filepath:
            return False
            
        self.import_started.emit("SVG")
        
        try:
            # Delegate to MainWindow implementation
            if hasattr(self._mw, '_import_svg_impl'):
                result = self._mw._import_svg_impl(filepath)
                self.import_finished.emit(True, tr("SVG Import erfolgreich"), result)
                return True
                
            # Fallback: Not implemented
            QMessageBox.information(
                self._mw,
                tr("Nicht implementiert"),
                tr("SVG Import wird von MainWindow nicht unterstützt.")
            )
            return False
            
        except Exception as e:
            logger.exception("SVG Import Error")
            self.import_finished.emit(False, str(e), None)
            QMessageBox.warning(None, tr("Import Fehler"), str(e))
            return False
            
    def import_step(self) -> bool:
        """
        Importiert STEP Datei.
        
        Returns:
            bool: True wenn Import erfolgreich
        """
        filepath, _ = QFileDialog.getOpenFileName(
            self._mw,
            tr("Import STEP"),
            "",
            "STEP Files (*.stp *.step)"
        )
        
        if not filepath:
            return False
            
        self.import_started.emit("STEP")
        
        try:
            if hasattr(self._mw, '_import_step_impl'):
                result = self._mw._import_step_impl(filepath)
                self.import_finished.emit(True, tr("STEP Import erfolgreich"), result)
                return True
                
            QMessageBox.information(
                self._mw,
                tr("Nicht implementiert"),
                tr("STEP Import wird von MainWindow nicht unterstützt.")
            )
            return False
            
        except Exception as e:
            logger.exception("STEP Import Error")
            self.import_finished.emit(False, str(e), None)
            QMessageBox.warning(None, tr("Import Fehler"), str(e))
            return False
            
    def import_mesh(self) -> bool:
        """
        Importiert Mesh-Datei (STL, OBJ, etc.).
        
        Returns:
            bool: True wenn Import erfolgreich
        """
        filepath, _ = QFileDialog.getOpenFileName(
            self._mw,
            tr("Import Mesh"),
            "",
            "Mesh Files (*.stl *.obj *.ply *.3mf);;STL Files (*.stl);;OBJ Files (*.obj);;PLY Files (*.ply);;3MF Files (*.3mf)"
        )
        
        if not filepath:
            return False
            
        self.import_started.emit("MESH")
        
        try:
            if hasattr(self._mw, '_import_mesh_impl'):
                result = self._mw._import_mesh_impl(filepath)
                self.import_finished.emit(True, tr("Mesh Import erfolgreich"), result)
                return True
                
            QMessageBox.information(
                self._mw,
                tr("Nicht implementiert"),
                tr("Mesh Import wird von MainWindow nicht unterstützt.")
            )
            return False
            
        except Exception as e:
            logger.exception("Mesh Import Error")
            self.import_finished.emit(False, str(e), None)
            QMessageBox.warning(None, tr("Import Fehler"), str(e))
            return False
            
    def _get_visible_bodies(self) -> List:
        """Holt alle sichtbaren Bodies aus dem Viewport."""
        if not hasattr(self._mw, 'viewport_3d') or not self._mw.viewport_3d:
            return []
            
        bodies = []
        try:
            # Versuche über document zu holen
            if hasattr(self._mw, 'document') and self._mw.document:
                for body in self._mw.document.get_bodies():
                    if hasattr(body, 'visible') and body.visible:
                        bodies.append(body)
        except Exception as e:
            logger.warning(f"Could not get visible bodies: {e}")
            
        return bodies
        
    def _do_stl_export(self, bodies, filepath, linear_defl, angular_tol, is_binary, scale):
        """Synchroner STL Export (Fallback)."""
        # Versuche MainWindow Implementierung
        if hasattr(self._mw, '_export_stl_sync_impl'):
            return self._mw._export_stl_sync_impl(bodies, filepath, linear_defl, angular_tol, is_binary, scale)
            
        # Fallback: Direkter Export
        try:
            import meshio
            import numpy as np
            
            all_vertices = []
            all_faces = []
            vertex_offset = 0
            
            for body in bodies:
                if hasattr(body, '_mesh') and body._mesh:
                    mesh = body._mesh
                    if hasattr(mesh, 'points') and hasattr(mesh, 'cells'):
                        vertices = mesh.points * scale
                        all_vertices.append(vertices)
                        
                        for cell_block in mesh.cells:
                            if cell_block.type == 'triangle':
                                faces = cell_block.data + vertex_offset
                                all_faces.append(faces)
                                
                        vertex_offset += len(vertices)
                        
            if not all_vertices:
                raise ValueError("Keine Mesh-Daten zum Exportieren")
                
            combined_vertices = np.vstack(all_vertices) if all_vertices else np.array([])
            combined_faces = np.vstack(all_faces) if all_faces else np.array([]).reshape(0, 3)
            
            export_mesh = meshio.Mesh(
                points=combined_vertices,
                cells=[('triangle', combined_faces)]
            )
            
            export_mesh.write(filepath, file_format='stl', binary=is_binary)
            return True
            
        except ImportError:
            logger.error("meshio nicht installiert für STL Export")
            return False
        except Exception as e:
            logger.exception("STL Export Error")
            return False
            
    def cleanup(self):
        """Räumt auf beim Beenden."""
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.terminate()
            self._current_worker.wait(1000)
            self._current_worker = None
