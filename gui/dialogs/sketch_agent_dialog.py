"""
Sketch Agent Dialog - UI für den generativen CAD-Agenten
Styled to match SectionViewPanel (DesignTokens).
"""

from typing import Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QSpinBox, QPushButton, QProgressBar,
    QTextEdit, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QThread
from loguru import logger

from i18n import tr
from gui.design_tokens import DesignTokens


class SketchAgentWorker(QThread):
    """Background-Worker für Part-Generierung."""
    finished = Signal(object)
    progress = Signal(str)

    def __init__(self, agent, complexity: str, seed: int):
        super().__init__()
        self.agent = agent
        self.complexity = complexity
        self.seed = seed

    def run(self):
        try:
            self.progress.emit(tr("Generating part..."))
            import random
            if self.seed is not None:
                random.seed(self.seed)

            result = self.agent.generate_part(complexity=self.complexity)

            if result.metadata is None:
                result.metadata = {}
            result.metadata['used_seed'] = self.seed

            self.finished.emit(result)
        except Exception as e:
            logger.error(f"[SketchAgentWorker] {e}")
            from sketching.core.result_types import PartResult
            error_result = PartResult(
                success=False,
                solid=None,
                operations=[],
                duration_ms=0,
                error=str(e),
                metadata={'used_seed': self.seed}
            )
            self.finished.emit(error_result)


class SketchAgentDialog(QDialog):
    """Dialog für Sketch Agent Part-Generierung."""

    def __init__(self, document, viewport, parent=None):
        super().__init__(parent)
        self.document = document
        self.viewport = viewport
        self.agent = None
        self.worker = None

        self._setup_ui()
        self._create_agent()

    def _create_agent(self):
        try:
            from sketching import create_agent
            self.agent = create_agent(
                document=self.document,
                mode="adaptive",
                headless=True,
                seed=None
            )
            logger.info("[SketchAgentDialog] Agent mit Document erstellt")
        except ImportError as e:
            logger.error(f"[SketchAgentDialog] Import fehlgeschlagen: {e}")
            self.status_label.setText(tr("Agent not available"))

    def _setup_ui(self):
        self.setWindowTitle(tr("Sketch Agent"))
        self.setMinimumWidth(360)
        self.setMaximumWidth(440)
        self.resize(400, 420)
        self.setModal(True)
        self.setStyleSheet(DesignTokens.stylesheet_dialog())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # --- Header ---
        header = QHBoxLayout()
        header.setSpacing(8)

        title = QLabel(tr("Sketch Agent"))
        title.setStyleSheet(f"""
            font-size: 14px;
            font-weight: 600;
            color: {DesignTokens.COLOR_TEXT_PRIMARY.name()};
        """)
        header.addWidget(title)

        self.status_label = QLabel(tr("Ready"))
        self.status_label.setStyleSheet(f"color: {DesignTokens.COLOR_TEXT_MUTED.name()}; font-size: 12px;")
        header.addWidget(self.status_label)
        header.addStretch()
        layout.addLayout(header)

        # --- Settings Grid ---
        from PySide6.QtWidgets import QFormLayout
        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["adaptive", "random", "guided"])
        form.addRow(tr("Mode:"), self.mode_combo)

        self.complexity_combo = QComboBox()
        self.complexity_combo.addItems(["simple", "medium", "complex"])
        self.complexity_combo.setCurrentText("simple")
        form.addRow(tr("Complexity:"), self.complexity_combo)

        seed_row = QHBoxLayout()
        seed_row.setSpacing(6)
        self.random_seed_cb = QCheckBox(tr("Random"))
        self.random_seed_cb.setChecked(True)
        seed_row.addWidget(self.random_seed_cb)
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(42)
        self.seed_spin.setEnabled(False)
        self.random_seed_cb.toggled.connect(lambda checked: self.seed_spin.setEnabled(not checked))
        seed_row.addWidget(self.seed_spin, 1)
        form.addRow("Seed:", seed_row)

        layout.addLayout(form)

        self.add_to_doc_cb = QCheckBox(tr("Add to document"))
        self.add_to_doc_cb.setChecked(True)
        layout.addWidget(self.add_to_doc_cb)

        # --- Progress ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # --- Result ---
        self.result_info = QTextEdit()
        self.result_info.setMinimumHeight(60)
        self.result_info.setReadOnly(True)
        self.result_info.setVisible(False)
        layout.addWidget(self.result_info, 1)

        # --- Buttons ---
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.generate_btn = QPushButton(tr("Generate"))
        self.generate_btn.setObjectName("primary")
        self.generate_btn.clicked.connect(self._on_generate)
        btn_row.addWidget(self.generate_btn)

        self.close_btn = QPushButton(tr("Close"))
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.close_btn)

        layout.addLayout(btn_row)

    def _on_generate(self):
        if not self.agent:
            self.status_label.setText(tr("Agent not available"))
            return

        self.generate_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText(tr("Generating..."))
        self.result_info.clear()
        self.result_info.setVisible(False)

        import random
        if self.random_seed_cb.isChecked():
            seed = None
            current_random_seed = random.randint(0, 999999)
        else:
            seed = self.seed_spin.value()
            current_random_seed = seed
            random.seed(seed)

        complexity = self.complexity_combo.currentText()
        self.worker = SketchAgentWorker(self.agent, complexity, current_random_seed)
        self.worker.finished.connect(self._on_finished)
        self.worker.progress.connect(self.status_label.setText)
        self.worker.start()

    def _on_finished(self, result):
        self.progress_bar.setVisible(False)
        self.generate_btn.setEnabled(True)
        self.result_info.setVisible(True)

        if result.success:
            self.status_label.setText(tr("Done"))
            self.status_label.setStyleSheet(f"color: {DesignTokens.COLOR_SUCCESS.name()}; font-size: 12px;")

            used_seed = result.metadata.get('used_seed', '?')

            info = f"""<b>{tr("Success")}</b><br>
Faces: {result.face_count}<br>
Volume: {result.volume:.2f} mm³<br>
{tr("Duration")}: {result.duration_ms:.1f} ms<br>
Seed: {used_seed}<br>
{tr("Operations")}: {", ".join(result.operations)}"""
            self.result_info.setHtml(info)

            if self.random_seed_cb.isChecked() and isinstance(used_seed, int):
                self.seed_spin.setValue(used_seed)

            if self.add_to_doc_cb.isChecked() and result.solid:
                self._add_to_document(result.solid)
        else:
            self.status_label.setText(tr("Error"))
            self.status_label.setStyleSheet(f"color: {DesignTokens.COLOR_ERROR.name()}; font-size: 12px;")
            self.result_info.setPlainText(f"{tr('Error')}: {result.error}")

    def _add_to_document(self, solid):
        try:
            body_name = getattr(solid, 'metadata', {}).get('body_name', 'AgentBody')
            logger.success(f"[SketchAgentDialog] Body '{body_name}' bereits im Document")

            if self.viewport:
                if hasattr(self.parent(), 'browser'):
                    self.parent().browser.refresh()

                if hasattr(self.viewport, 'plotter'):
                    from gui.viewport.render_queue import request_render
                    request_render(self.viewport.plotter, immediate=True)
                elif hasattr(self.viewport, 'update'):
                    self.viewport.update()

        except Exception as e:
            logger.error(f"[SketchAgentDialog] Update fehlgeschlagen: {e}")
            self.status_label.setText(f"{tr('Error')}: {e}")


def show_sketch_agent_dialog(document, viewport, parent=None):
    """Zeigt den SketchAgent Dialog."""
    dialog = SketchAgentDialog(document, viewport, parent)
    dialog.exec()
    return dialog
