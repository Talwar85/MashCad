"""
ExportController - UI-Orchestrierung für Export/Import Workflows
=================================================================

Phase 1 Update (PR-001): Integriert ExportKernel API für vereinheitlichten Export.

W17 Paket C (AR-004 Phase-2): Extrahiert Export/Import-Logik aus MainWindow.
Zuständig für:
- STL Export (sync/async) mit Pre-flight Validierung
- STEP Export/Import
- SVG Export/Import
- Mesh Import (STL, OBJ, etc.)

Author: GLM 4.7 (UX/Workflow Delivery Cell) + Kimi (Phase 1 Integration)
Date: 2026-02-19
Branch: feature/v1-ux-aiB
"""

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QFileDialog, QMessageBox
from loguru import logger
from pathlib import Path
from typing import List, Optional, Callable, Any

from i18n import tr


class STLExportWorker(QThread):
    """Worker thread for async STL export."""
    finished = Signal(bool, str)  # success, message
    progress = Signal(str)
    
    def __init__(self, parent, export_func, bodies, filepath, options):
        super().__init__(parent)
        self.export_func = export_func
        self.bodies = bodies
        self.filepath = filepath
        self.options = options
        
    def run(self):
        try:
            self.progress.emit(tr("Exportiere STL..."))
            result = self.export_func(self.bodies, self.filepath, self.options)
            if result.success:
                msg = tr(f"STL Export erfolgreich: {result.triangle_count:,} Dreiecke")
                self.finished.emit(True, msg)
            else:
                self.finished.emit(False, tr(f"STL Export fehlgeschlagen: {result.error_message}"))
        except Exception as e:
            logger.exception("STL Export Error")
            self.finished.emit(False, str(e))


class ExportController(QObject):
    """
    Controller für Export/Import Operationen.
    
    Kapselt alle Export/Import-Workflows und nutzt die neue ExportKernel API
    für vereinheitlichte Export-Operationen.
    """
    
    # Signals for UI updates
    export_started = Signal(str)  # format
    export_finished = Signal(bool, str)  # success, message
    import_started = Signal(str)  # format
    import_finished = Signal(bool, str, object)  # success, message, result
    validation_warnings = Signal(list)  # list of validation issues
    
    def __init__(self, main_window):
        """
        Args:
            main_window: MainWindow Instanz (für UI-Zugriff)
        """
        super().__init__(None)
        self._mw = main_window
        self._current_worker = None
        
    def export_stl(self, bodies: Optional[List] = None, show_options_dialog: bool = True) -> bool:
        """
        Exportiert Bodies als STL mit Pre-flight Validierung.
        
        Args:
            bodies: Liste der zu exportierenden Bodies (None = alle sichtbaren)
            show_options_dialog: True um Export-Dialog zu zeigen
            
        Returns:
            bool: True wenn Export gestartet/war erfolgreich
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
        
        # Importiere ExportKernel
        try:
            from modeling.export_kernel import ExportKernel, ExportOptions, ExportQuality
            from modeling.export_validator import ExportValidator
        except ImportError as e:
            logger.error(f"ExportKernel nicht verfügbar: {e}")
            QMessageBox.critical(None, tr("Export Fehler"), tr("Export-Modul nicht verfügbar."))
            return False
        
        # Erstelle Default-Optionen
        options = ExportOptions(
            format=ExportFormat.STL,
            quality=ExportQuality.FINE,
            binary=True,
            scale=1.0
        )
        
        # Zeige Export-Dialog wenn gewünscht
        if show_options_dialog:
            from gui.dialogs.stl_export_dialog import STLExportDialog
            dlg = STLExportDialog(parent=self._mw)
            if dlg.exec() != QFileDialog.Accepted:
                return False
            
            # Übernehme Optionen aus Dialog
            options.linear_deflection = dlg.linear_deflection
            options.angular_tolerance = dlg.angular_tolerance
            options.binary = dlg.is_binary
            options.scale = dlg.scale_factor
            
            # Map quality slider to enum
            quality_map = [ExportQuality.DRAFT, ExportQuality.STANDARD, 
                          ExportQuality.FINE, ExportQuality.ULTRA]
            options.quality = quality_map[dlg.quality_slider.value()]
        
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
        
        # PR-010: Printability Trust Gate Check
        gate_result = self._run_printability_gate_check(bodies)
        if gate_result is not None:
            from modeling.printability_gate import GateStatus
            
            if gate_result.status == GateStatus.FAIL:
                # Export blockiert - zeige Dialog
                self._show_printability_preflight_dialog(gate_result)
                return False
            elif gate_result.status == GateStatus.WARN:
                # Warnung - zeige Dialog mit Override-Option
                if not self._show_printability_preflight_dialog(gate_result):
                    return False
            # PASS: Export fortsetzen
        
        # Pre-flight Validierung (legacy)
        validation_issues = self._run_preflight_validation(bodies)
        if validation_issues:
            self.validation_warnings.emit(validation_issues)
            
            # Zeige Warnungen falls kritische Issues (nur wenn Gate nicht aktiv)
            if gate_result is None:
                critical_issues = [i for i in validation_issues
                                 if i.severity.value == "error"]
                if critical_issues:
                    msg = tr("Kritische Probleme gefunden:\n\n")
                    for issue in critical_issues[:5]:
                        msg += f"• {issue.message}\n"
                    msg += tr("\nTrotzdem exportieren?")
                    
                    reply = QMessageBox.warning(
                        self._mw,
                        tr("Export Validierung"),
                        msg,
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if reply != QMessageBox.Yes:
                        return False
        
        self.export_started.emit("STL")
        
        # Async Export
        self._export_stl_async(bodies, filepath, options)
        return True
        
    def _run_preflight_validation(self, bodies: List) -> List:
        """
        Führt Pre-flight Validierung durch.
        
        Returns:
            Liste von ValidationIssues
        """
        try:
            from modeling.export_validator import ExportValidator, ValidationOptions
            
            all_issues = []
            for body in bodies:
                solid = getattr(body, '_build123d_solid', None)
                if solid is not None:
                    options = ValidationOptions(
                        check_manifold=True,
                        check_free_bounds=True,
                        check_degenerate=True,
                        check_normals=False
                    )
                    result = ExportValidator.validate_for_export(solid, options)
                    all_issues.extend(result.issues)
            
            return all_issues
            
        except Exception as e:
            logger.warning(f"Preflight validation failed: {e}")
            return []
    
    def _run_printability_gate_check(self, bodies: List) -> Optional['GateResult']:
        """
        Führt Printability Trust Gate Check durch (PR-010).
        
        Returns:
            GateResult oder None wenn Gate deaktiviert/Fehler
        """
        try:
            from config.feature_flags import is_enabled
            
            # Skip wenn Feature deaktiviert
            if not is_enabled("printability_trust_gate"):
                logger.debug("Printability Trust Gate deaktiviert")
                return None
            
            from modeling.printability_gate import PrintabilityGate, GateStatus
            
            gate = PrintabilityGate()
            
            # Check alle Bodies
            worst_result = None
            for body in bodies:
                solid = getattr(body, '_build123d_solid', None)
                if solid is not None:
                    result = gate.check(solid)
                    if worst_result is None or result.score.overall_score < worst_result.score.overall_score:
                        worst_result = result
            
            return worst_result
            
        except Exception as e:
            logger.warning(f"Printability gate check failed: {e}")
            return None
    
    def _show_printability_preflight_dialog(self, gate_result: 'GateResult') -> bool:
        """
        Zeigt den Printability Preflight Dialog.
        
        Returns:
            True wenn Export fortgesetzt werden soll
        """
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QScrollArea, QWidget
        from PySide6.QtCore import Qt
        from modeling.printability_gate import GateStatus
        
        dialog = QDialog(self._mw)
        dialog.setWindowTitle(tr("Printability Check"))
        dialog.setMinimumSize(500, 400)
        
        layout = QVBoxLayout(dialog)
        
        # Header mit Score
        score = gate_result.score
        header = QLabel(
            f"<h2>{score.get_grade()} - Score: {score.overall_score}/100</h2>"
            f"<p>{gate_result.get_summary()}</p>"
        )
        layout.addWidget(header)
        
        # Score Details
        details = QLabel(
            f"<b>Kategorie-Scores:</b><br>"
            f"• Manifold: {score.manifold_score}/100<br>"
            f"• Normalen: {score.normals_score}/100<br>"
            f"• Wandstärke: {score.wall_thickness_score}/100<br>"
            f"• Überhänge: {score.overhang_score}/100"
        )
        layout.addWidget(details)
        
        # Issues falls vorhanden
        if gate_result.blocking_issues or gate_result.warning_issues:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll_widget = QWidget()
            scroll_layout = QVBoxLayout(scroll_widget)
            
            if gate_result.blocking_issues:
                scroll_layout.addWidget(QLabel("<b>Blockierende Probleme:</b>"))
                for issue in gate_result.blocking_issues[:10]:
                    icon = "🔴" if issue.severity.value == "critical" else "🟠"
                    issue_label = QLabel(f"{icon} {issue.message}")
                    issue_label.setWordWrap(True)
                    scroll_layout.addWidget(issue_label)
            
            if gate_result.warning_issues:
                scroll_layout.addWidget(QLabel("<b>Warnungen:</b>"))
                for issue in gate_result.warning_issues[:10]:
                    issue_label = QLabel(f"🟡 {issue.message}")
                    issue_label.setWordWrap(True)
                    scroll_layout.addWidget(issue_label)
            
            scroll.setWidget(scroll_widget)
            layout.addWidget(scroll)
        
        # Buttons
        button_layout = QVBoxLayout()
        
        if gate_result.status == GateStatus.FAIL:
            # Export blockiert
            msg = QLabel(tr("<b>Export ist blockiert aufgrund kritischer Probleme.</b>"))
            msg.setStyleSheet("color: red;")
            layout.addWidget(msg)
            
            close_btn = QPushButton(tr("Schließen"))
            close_btn.clicked.connect(dialog.reject)
            button_layout.addWidget(close_btn)
        elif gate_result.status == GateStatus.WARN:
            # Warnung - Export mit Bestätigung möglich
            msg = QLabel(tr("Export mit Warnungen möglich. Trotzdem exportieren?"))
            msg.setStyleSheet("color: orange;")
            layout.addWidget(msg)
            
            export_btn = QPushButton(tr("Trotzdem exportieren"))
            export_btn.clicked.connect(dialog.accept)
            button_layout.addWidget(export_btn)
            
            cancel_btn = QPushButton(tr("Abbrechen"))
            cancel_btn.clicked.connect(dialog.reject)
            button_layout.addWidget(cancel_btn)
        else:
            # PASS
            ok_btn = QPushButton(tr("Exportieren"))
            ok_btn.clicked.connect(dialog.accept)
            button_layout.addWidget(ok_btn)
            
            cancel_btn = QPushButton(tr("Abbrechen"))
            cancel_btn.clicked.connect(dialog.reject)
            button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        return dialog.exec() == QDialog.Accepted
        
    def _export_stl_async(self, bodies, filepath, options):
        """Startet asynchronen STL Export über ExportKernel."""
        try:
            from modeling.export_kernel import ExportKernel
            
            # Get export function from ExportKernel
            export_func = ExportKernel.export_bodies
            
            self._current_worker = STLExportWorker(
                self, export_func, bodies, filepath, options
            )
            self._current_worker.finished.connect(self._on_export_finished)
            self._current_worker.start()
            
        except Exception as e:
            logger.exception("Failed to start async export")
            self._on_export_finished(False, str(e))
        
    def _on_export_finished(self, success: bool, message: str):
        """Handler für Export-Fertigstellung."""
        self._current_worker = None
        self.export_finished.emit(success, message)
        
        if success:
            self._mw.statusBar().showMessage(message, 5000)
        else:
            QMessageBox.warning(None, tr("Export Fehler"), message)
            
    def export_step(self) -> bool:
        """
        Exportiert als STEP mit Pre-flight Validierung.
        
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
        
        # Pre-flight Validierung
        validation_issues = self._run_preflight_validation(bodies)
        if validation_issues:
            self.validation_warnings.emit(validation_issues)
        
        filepath, _ = QFileDialog.getSaveFileName(
            self._mw,
            tr("Export als STEP"),
            "",
            "STEP Files (*.stp *.step)"
        )
        
        if not filepath:
            return False
        
        try:
            from modeling.export_kernel import ExportKernel, ExportOptions, ExportFormat
            
            options = ExportOptions(format=ExportFormat.STEP)
            result = ExportKernel.export_bodies(bodies, filepath, options)
            
            if result.success:
                self._mw.statusBar().showMessage(
                    tr(f"STEP Export erfolgreich: {result.file_size_kb:.1f} KB"), 
                    5000
                )
                return True
            else:
                QMessageBox.warning(
                    None, 
                    tr("Export Fehler"), 
                    result.error_message
                )
                return False
                
        except ImportError as e:
            logger.error(f"ExportKernel nicht verfügbar: {e}")
            QMessageBox.critical(None, tr("Export Fehler"), tr("Export-Modul nicht verfügbar."))
            return False
        except Exception as e:
            logger.exception("STEP Export Error")
            QMessageBox.warning(None, tr("Export Fehler"), str(e))
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
        
    def cleanup(self):
        """Räumt auf beim Beenden."""
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.terminate()
            self._current_worker.wait(1000)
            self._current_worker = None
