"""
MashCad - Wall Thickness Analysis Dialog
Analyze and visualize wall thickness for 3D printing validation.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGroupBox, QTextEdit, QProgressBar
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from loguru import logger
from gui.design_tokens import DesignTokens
from i18n import tr


class WallThicknessDialog(QDialog):
    """Dialog to analyze wall thickness and show results."""

    def __init__(self, body, parent=None):
        super().__init__(parent)
        self.body = body
        self.result = None
        self.setWindowTitle(f"{tr('Wall Thickness Analysis')} - {body.name}")
        self.setMinimumWidth(500)
        self.setMinimumHeight(350)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Parameters
        param_group = QGroupBox(tr("Parameters"))
        param_layout = QVBoxLayout()

        thresh_row = QHBoxLayout()
        lbl = QLabel(tr("Minimum Thickness:"))
        lbl.setMinimumWidth(140)
        thresh_row.addWidget(lbl)
        self.threshold_input = QLineEdit("0.8")
        v = QDoubleValidator(0.1, 50.0, 2)
        v.setNotation(QDoubleValidator.StandardNotation)
        self.threshold_input.setValidator(v)
        thresh_row.addWidget(self.threshold_input)
        thresh_row.addWidget(QLabel("mm"))
        param_layout.addLayout(thresh_row)

        # Presets
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel(tr("Preset:")))
        for name, val in [("FDM", "0.8"), ("SLA", "0.5"), ("SLS", "0.7"), ("MJF", "0.6")]:
            btn = QPushButton(name)
            btn.setFixedWidth(50)
            btn.clicked.connect(lambda checked, v=val: self.threshold_input.setText(v))
            preset_row.addWidget(btn)
        preset_row.addStretch()
        param_layout.addLayout(preset_row)

        param_group.setLayout(param_layout)
        layout.addWidget(param_group)

        # Analyze button
        self.analyze_btn = QPushButton(tr("Analyze"))
        self.analyze_btn.clicked.connect(self._on_analyze)
        self.analyze_btn.setObjectName("primary")
        layout.addWidget(self.analyze_btn)

        # Results
        result_group = QGroupBox(tr("Results"))
        result_layout = QVBoxLayout()

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet(
            "background: #1e1e1e; color: #ddd; border: 1px solid #3f3f46; "
            "border-radius: 4px; font-family: Consolas, monospace; font-size: 12px;"
        )
        self.result_text.setPlainText(tr("Click 'Analyze' to start."))
        result_layout.addWidget(self.result_text)

        result_group.setLayout(result_layout)
        layout.addWidget(result_group)

        # Close
        btn_layout = QHBoxLayout()
        close_btn = QPushButton(tr("Close"))
        close_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self.setStyleSheet(DesignTokens.stylesheet_dialog())

    def _on_analyze(self):
        solid = self.body._build123d_solid
        if solid is None:
            self.result_text.setPlainText(tr("No solid geometry on this body."))
            return

        try:
            threshold = float(self.threshold_input.text() or "0.8")
        except ValueError:
            threshold = 0.8

        self.result_text.setPlainText(tr("Analyzing..."))
        self.analyze_btn.setEnabled(False)
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            from modeling.wall_thickness_analyzer import WallThicknessAnalyzer
            self.result = WallThicknessAnalyzer.analyze(solid, threshold)

            lines = []
            if self.result.ok:
                lines.append(f"STATUS: OK")
                color = "#4ec9b0"
            else:
                lines.append(f"STATUS: THIN WALLS DETECTED")
                color = "#f44747"

            lines.append(f"")
            lines.append(f"Min thickness:  {self.result.min_thickness:.3f} mm")
            lines.append(f"Threshold:      {threshold:.1f} mm")
            lines.append(f"Total faces:    {self.result.total_faces}")
            lines.append(f"Thin faces:     {len(self.result.thin_face_indices)}")

            if self.result.thin_face_indices:
                lines.append(f"")
                lines.append(f"Thin face indices: {self.result.thin_face_indices[:20]}")
                if len(self.result.thin_face_indices) > 20:
                    lines.append(f"  ... and {len(self.result.thin_face_indices) - 20} more")

            self.result_text.setPlainText("\n".join(lines))
            self.result_text.setStyleSheet(
                f"background: #1e1e1e; color: {color}; border: 1px solid #3f3f46; "
                "border-radius: 4px; font-family: Consolas, monospace; font-size: 12px;"
            )

        except Exception as e:
            self.result_text.setPlainText(f"Analysis error: {e}")
            logger.error(f"Wall thickness analysis failed: {e}")

        self.analyze_btn.setEnabled(True)
