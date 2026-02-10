"""
MashCad - MeshConverter Dialog
===============================

Async Mesh-to-BREP Konvertierung mit Progress Dialog.

Verhindert UI-Freezing bei grossen Meshes durch QThread-basierte Konvertierung.
Zeigt detaillierten Fortschritt mit Phase, Progress-Bar und Status-Updates.

Features:
- 3 Converter-Strategien (Simple, Current, Perfect)
- Real-time Progress Updates
- Cancel-Support
- Ergebnis-Übersicht (Face-Count, Status)

Author: Claude (MeshConverter Architecture)
Date: 2026-02-10
"""

from typing import Optional, Callable
from pathlib import Path
from loguru import logger

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QComboBox, QFileDialog,
    QGroupBox, QTextEdit, QRadioButton, QButtonGroup
)
from PySide6.QtCore import Qt, QThread, Signal, QMutex, QMutexLocker
from PySide6.QtGui import QFont, QColor

from i18n import tr


class MeshConverterWorker(QThread):
    """
    Background Worker für Mesh-Konvertierung.

    Signals:
        progress: (ProgressUpdate) - Fortschritts-Update
        finished: (ConversionResult) - Konvertierung fertig
        error: (str) - Fehler aufgetreten

    Usage:
        worker = MeshConverterWorker(converter, mesh)
        worker.progress.connect(on_progress)
        worker.finished.connect(on_finished)
        worker.start()
    """

    progress = Signal(object)  # ProgressUpdate
    finished = Signal(object)  # ConversionResult
    error = Signal(str)        # error_message

    def __init__(self, converter, mesh: 'pv.PolyData', parent=None):
        super().__init__(parent)
        self.converter = converter
        self.mesh = mesh
        self._cancelled = False
        self._mutex = QMutex()

    def cancel(self):
        """Bricht die Konvertierung ab."""
        with QMutexLocker(self._mutex):
            self._cancelled = True

    def is_cancelled(self) -> bool:
        """Prüft ob abgebrochen wurde."""
        with QMutexLocker(self._mutex):
            return self._cancelled

    def run(self):
        """Führt Konvertierung im Background-Thread aus."""
        try:
            if self.is_cancelled():
                return

            # Progress Callback Wrapper
            def on_progress(update):
                if not self.is_cancelled():
                    self.progress.emit(update)

            # Konvertierung ausführen
            result = self.converter.convert_async(self.mesh, on_progress)

            if not self.is_cancelled():
                self.finished.emit(result)

        except Exception as e:
            if not self.is_cancelled():
                logger.error(f"MeshConverter fehlgeschlagen: {e}")
                self.error.emit(str(e))


class MeshConverterDialog(QDialog):
    """
    Dialog für Mesh-to-BREP Konvertierung mit Progress Bar.

    Features:
    - Converter-Auswahl (Simple, Current, Perfect)
    - Real-time Progress Updates
    - Phase-Indikator (Laden, Segmentieren, Bauen, etc.)
    - Cancel-Button
    - Ergebnis-Übersicht
    """

    # Signal für Ergebnis
    conversion_completed = Signal(object)  # ConversionResult

    def __init__(self, mesh=None, parent=None):
        super().__init__(parent)
        self.mesh = mesh
        self.worker = None

        self._setup_ui()
        self._update_converter_description()

    def _setup_ui(self):
        """Erstellt UI."""
        self.setWindowTitle(tr("Mesh to BREP Converter"))
        self.setMinimumSize(550, 400)
        self.setStyleSheet("""
            QDialog { background-color: #2d2d30; color: #e0e0e0; }
            QLabel { color: #e0e0e0; }
            QGroupBox {
                color: #e0e0e0;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
            }
            QProgressBar {
                background-color: #3e3e42;
                border: 1px solid #555;
                border-radius: 3px;
                text-align: center;
                color: #e0e0e0;
            }
            QProgressBar::chunk {
                background-color: #0e639c;
                border-radius: 2px;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 3px;
                min-width: 80px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:pressed { background-color: #0d5289; }
            QPushButton:disabled {
                background-color: #3e3e42;
                color: #888;
            }
            QPushButton#cancelBtn { background-color: #c42b1c; }
            QPushButton#cancelBtn:hover { background-color: #d83b2b; }
            QComboBox, QRadioButton {
                background-color: #3c3c3c;
                color: #e0e0e0;
                padding: 4px;
                border: 1px solid #555;
                border-radius: 3px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                border: none;
                width: 12px;
                height: 12px;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: #e0e0e0;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Converter Auswahl
        converter_group = QGroupBox(tr("Converter Strategy"))
        converter_layout = QVBoxLayout()

        # Converter Typen
        self.simple_radio = QRadioButton(tr("Simple (Baseline)"))
        self.simple_radio.setToolTip(
            tr("Einfach, immer zuverlässig. Facettierte Oberfläche.")
        )
        self.simple_radio.setChecked(True)
        self.simple_radio.toggled.connect(self._update_converter_description)
        converter_layout.addWidget(self.simple_radio)

        self.current_radio = QRadioButton(tr("Current (V10/Final)"))
        self.current_radio.setToolTip(
            tr("Bestehende Converter mit Segmentierung und Primitive Fitting.")
        )
        self.current_radio.toggled.connect(self._update_converter_description)
        converter_layout.addWidget(self.current_radio)

        self.perfect_radio = QRadioButton(tr("Perfect (Optimized)"))
        self.perfect_radio.setToolTip(
            tr("Perfektes BREP mit analytischen Surfaces (in Arbeit).")
        )
        self.perfect_radio.toggled.connect(self._update_converter_description)
        converter_layout.addWidget(self.perfect_radio)

        # Current Mode Sub-Auswahl
        current_mode_layout = QHBoxLayout()
        current_mode_layout.addWidget(QLabel(tr("Current Mode:")))
        self.current_mode_combo = QComboBox()
        self.current_mode_combo.addItems(["AUTO", "V10", "FINAL"])
        current_mode_layout.addWidget(self.current_mode_combo)
        current_mode_layout.addStretch()
        converter_layout.addLayout(current_mode_layout)

        converter_group.setLayout(converter_layout)
        layout.addWidget(converter_group)

        # Beschreibung
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("color: #888; font-style: italic; padding: 5px;")
        layout.addWidget(self.description_label)

        # Progress Section
        progress_group = QGroupBox(tr("Conversion Progress"))
        progress_layout = QVBoxLayout()

        # Phase Label
        self.phase_label = QLabel(tr("Ready"))
        self.phase_label.setFont(QFont("Arial", 10, QFont.Bold))
        progress_layout.addWidget(self.phase_label)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        # Detail Label
        self.detail_label = QLabel()
        self.detail_label.setStyleSheet("color: #888;")
        progress_layout.addWidget(self.detail_label)

        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)

        # Log Output
        log_group = QGroupBox(tr("Log"))
        log_layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        log_layout.addWidget(self.log_text)

        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        # Ergebnis Section
        result_group = QGroupBox(tr("Result"))
        result_layout = QHBoxLayout()

        self.result_label = QLabel(tr("No conversion yet"))
        result_layout.addWidget(self.result_label)

        result_group.setLayout(result_layout)
        layout.addWidget(result_group)

        # Buttons
        btn_layout = QHBoxLayout()

        self.convert_btn = QPushButton(tr("Convert"))
        self.convert_btn.clicked.connect(self._start_conversion)
        btn_layout.addWidget(self.convert_btn)

        self.cancel_btn = QPushButton(tr("Cancel"))
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_conversion)
        btn_layout.addWidget(self.cancel_btn)

        btn_layout.addStretch()

        self.close_btn = QPushButton(tr("Close"))
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

    def _update_converter_description(self):
        """Aktualisiert Beschreibung basierend auf Auswahl."""
        if self.simple_radio.isChecked():
            desc = tr(
                "SimpleConverter: Einfach, immer zuverlässig.\n"
                "Strategie: 1:1 Mapping (jedes Dreieck → planares BREP Face).\n"
                "Vorteile: 100% reproduzierbar, vorhersagbare Performance.\n"
                "Nachteile: Facettierte Oberfläche, grössere Dateigrösse."
            )
        elif self.current_radio.isChecked():
            desc = tr(
                "CurrentConverter: Bestehende V10/Final Converter.\n"
                "V10: Segmentierung + Primitive Fitting (Plane, Cylinder, Sphere).\n"
                "Final: Zylinder-erhaltend für STEP Export.\n"
                "Vorteile: Bewährte Algorithmen, gute Qualität."
            )
        else:  # perfect
            desc = tr(
                "PerfectConverter: Perfektes BREP mit analytischen Surfaces.\n"
                "Zylinder mit nur 3 Faces statt hunderten facettierten.\n"
                "Vorteile: Minimale Face-Count, glatte Oberflächen.\n"
                "Status: In Arbeit, BREP Building noch nicht vollständig."
            )

        self.description_label.setText(desc)

    def set_mesh(self, mesh):
        """Setzt das Mesh für die Konvertierung."""
        self.mesh = mesh
        self.result_label.setText(tr("Ready to convert"))

    def _log(self, message: str):
        """Fügt Nachricht zum Log hinzu."""
        self.log_text.append(message)

    def _start_conversion(self):
        """Startet die Konvertierung."""
        if self.mesh is None:
            self.result_label.setText(tr("Error: No mesh loaded"))
            return

        # Converter erstellen basierend auf Auswahl
        try:
            if self.simple_radio.isChecked():
                from meshconverter import SimpleConverter
                converter = SimpleConverter()
            elif self.current_radio.isChecked():
                from meshconverter import CurrentConverter, CurrentMode
                mode_str = self.current_mode_combo.currentText()
                mode = {
                    "AUTO": CurrentMode.AUTO,
                    "V10": CurrentMode.V10,
                    "FINAL": CurrentMode.FINAL,
                }[mode_str]
                converter = CurrentConverter(mode=mode)
            else:  # perfect
                from meshconverter import PerfectConverter, HAS_PERFECT_CONVERTER
                if not HAS_PERFECT_CONVERTER:
                    self.result_label.setText(tr("Error: PerfectConverter not available"))
                    return
                converter = PerfectConverter()

        except ImportError as e:
            self.result_label.setText(tr("Error: {}").format(str(e)))
            return

        # UI aktualisieren
        self.convert_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.close_btn.setEnabled(False)
        self.log_text.clear()
        self.progress_bar.setValue(0)
        self.phase_label.setText(tr("Starting..."))

        # Worker starten
        self.worker = MeshConverterWorker(converter, self.mesh)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self._on_worker_done)
        self.worker.start()

        self._log(f"[INFO] Converter: {converter.name}")
        self._log(f"[INFO] Mesh: {self.mesh.n_points} points, {self.mesh.n_cells} faces")

    def _cancel_conversion(self):
        """Bricht die Konvertierung ab."""
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self._log("[WARN] Conversion cancelled by user")
            self.phase_label.setText(tr("Cancelling..."))

    def _on_progress(self, update):
        """Update bei Fortschritt."""
        # Phase
        phase_name = update.phase.value if hasattr(update.phase, 'value') else str(update.phase)
        self.phase_label.setText(phase_name)

        # Progress Bar
        progress_percent = int(update.progress * 100)
        self.progress_bar.setValue(progress_percent)

        # Message
        self.detail_label.setText(update.message)

        # Log (nur wichtige Messages)
        if update.progress > 0.1:  # Nicht loggen bei jedem kleinen Update
            self._log(f"[{phase_name}] {progress_percent}% - {update.message}")

    def _on_finished(self, result):
        """Wenn Konvertierung fertig."""
        self.progress_bar.setValue(100)

        # Ergebnis anzeigen
        status_text = result.status.value if result.status else "Unknown"
        if result.success:
            self.result_label.setText(
                tr("Success: {faces} faces").format(faces=result.face_count)
            )
            self._log(f"[SUCCESS] {result.message}")
        else:
            self.result_label.setText(
                tr("Status: {status} - {faces} faces").format(
                    status=status_text, faces=result.face_count
                )
            )
            self._log(f"[{status_text}] {result.message}")

        # Signal emittieren
        self.conversion_completed.emit(result)

    def _on_error(self, error_message: str):
        """Bei Fehler."""
        self.result_label.setText(tr("Error: {}").format(error_message))
        self._log(f"[ERROR] {error_message}")
        self.phase_label.setText(tr("Error"))

    def _on_worker_done(self):
        """Wenn Worker fertig (egal ob Erfolg oder Fehler)."""
        self.convert_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.close_btn.setEnabled(True)


def show_meshconverter_dialog(mesh, parent=None) -> Optional['ConversionResult']:
    """
    Zeigt den MeshConverter Dialog modal an.

    Args:
        mesh: PyVista PolyData
        parent: Parent Widget

    Returns:
        ConversionResult oder None wenn abgebrochen
    """
    dialog = MeshConverterDialog(mesh, parent)

    # Ergebnis speichern
    result_holder = {'result': None}

    def on_completed(r):
        result_holder['result'] = r

    dialog.conversion_completed.connect(on_completed)

    # Dialog anzeigen
    dialog.exec()

    return result_holder.get('result')


if __name__ == "__main__":
    # Test
    import sys
    sys.path.insert(0, 'c:/LiteCad')

    from PySide6.QtWidgets import QApplication
    import pyvista as pv

    app = QApplication(sys.argv)

    # Test Mesh laden
    mesh = pv.Cube().triangulate()

    dialog = MeshConverterDialog(mesh)
    dialog.show()

    sys.exit(app.exec())
