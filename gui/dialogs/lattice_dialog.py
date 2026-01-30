"""
MashCad - Lattice Dialog
Create beam-based lattice structures for lightweight 3D printing.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QGroupBox
)
from PySide6.QtCore import Qt
from loguru import logger
from gui.design_tokens import DesignTokens
from i18n import tr


class LatticeDialog(QDialog):
    """Dialog to configure lattice generation parameters."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Lattice Structure"))
        self.setMinimumWidth(420)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Cell type
        type_group = QGroupBox(tr("Cell Type"))
        type_layout = QVBoxLayout()

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel(tr("Type:")))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["BCC", "FCC", "Octet", "Diamond"])
        type_row.addWidget(self.type_combo)
        type_row.addStretch()
        type_layout.addLayout(type_row)

        # Description
        self.desc_label = QLabel("")
        self.desc_label.setStyleSheet("color: #999; font-size: 11px; font-style: italic;")
        self.desc_label.setWordWrap(True)
        type_layout.addWidget(self.desc_label)
        self.type_combo.currentIndexChanged.connect(self._update_description)

        type_group.setLayout(type_layout)
        layout.addWidget(type_group)

        # Parameters
        param_group = QGroupBox(tr("Parameters"))
        param_layout = QVBoxLayout()

        # Regex-Validator der sowohl Komma als auch Punkt akzeptiert
        from PySide6.QtGui import QRegularExpressionValidator
        from PySide6.QtCore import QRegularExpression
        # Erlaubt: 0, 1.5, 1,5, 10.25, 10,25 etc.
        decimal_regex = QRegularExpression(r"^\d+([.,]\d*)?$")
        decimal_validator = QRegularExpressionValidator(decimal_regex)

        # Cell size
        size_row = QHBoxLayout()
        slbl = QLabel(tr("Cell Size:"))
        slbl.setMinimumWidth(120)
        size_row.addWidget(slbl)
        self.size_input = QLineEdit("5.0")
        self.size_input.setValidator(decimal_validator)
        self.size_input.setPlaceholderText("1.0 - 100.0")
        size_row.addWidget(self.size_input)
        size_row.addWidget(QLabel("mm"))
        param_layout.addLayout(size_row)

        # Beam radius
        beam_row = QHBoxLayout()
        blbl = QLabel(tr("Beam Radius:"))
        blbl.setMinimumWidth(120)
        beam_row.addWidget(blbl)
        self.beam_input = QLineEdit("0.5")
        self.beam_input.setValidator(decimal_validator)
        self.beam_input.setPlaceholderText("0.1 - 10.0")
        beam_row.addWidget(self.beam_input)
        beam_row.addWidget(QLabel("mm"))
        param_layout.addLayout(beam_row)

        # Shell thickness
        shell_row = QHBoxLayout()
        shlbl = QLabel(tr("Shell Thickness:"))
        shlbl.setMinimumWidth(120)
        shell_row.addWidget(shlbl)
        self.shell_input = QLineEdit("1.0")
        self.shell_input.setValidator(decimal_validator)
        self.shell_input.setPlaceholderText("0 - 50.0")
        shell_row.addWidget(self.shell_input)
        shell_row.addWidget(QLabel("mm"))
        param_layout.addLayout(shell_row)

        shell_hint = QLabel(tr("0 = no shell (lattice only), >0 = preserve outer wall"))
        shell_hint.setStyleSheet("color: #999; font-size: 10px;")
        param_layout.addWidget(shell_hint)

        param_group.setLayout(param_layout)
        layout.addWidget(param_group)

        # Warning
        warn = QLabel(tr("Note: Large bodies with small cells may be slow to compute."))
        warn.setStyleSheet("color: #d4a017; font-size: 11px;")
        warn.setWordWrap(True)
        layout.addWidget(warn)

        # Buttons
        btn_layout = QHBoxLayout()
        cancel = QPushButton(tr("Cancel"))
        cancel.clicked.connect(self.reject)

        create = QPushButton(tr("Generate"))
        create.setDefault(True)
        create.clicked.connect(self._on_create)
        create.setObjectName("primary")

        btn_layout.addStretch()
        btn_layout.addWidget(cancel)
        btn_layout.addWidget(create)
        layout.addSpacing(10)
        layout.addLayout(btn_layout)

        self.setStyleSheet(DesignTokens.stylesheet_dialog())
        self._update_description(0)

    def _update_description(self, index):
        descs = [
            tr("Body-Centered Cubic: 8 struts to center. Good balance of strength and weight."),
            tr("Face-Centered Cubic: 12 struts per cell. Higher stiffness."),
            tr("Octet Truss: FCC + cross braces. Very high stiffness-to-weight ratio."),
            tr("Diamond: Tetrahedral connections. More flexible, good for energy absorption."),
        ]
        self.desc_label.setText(descs[index] if index < len(descs) else "")

    def _on_create(self):
        from PySide6.QtWidgets import QMessageBox
        import math

        def parse_float(text, default):
            """Parse float mit Komma oder Punkt als Dezimaltrenner."""
            if not text:
                return default
            # Ersetze Komma durch Punkt für float()
            return float(text.replace(",", "."))

        try:
            self.cell_type = self.type_combo.currentText()
            self.cell_size = parse_float(self.size_input.text(), 5.0)
            self.beam_radius = parse_float(self.beam_input.text(), 0.5)
            self.shell_thickness = parse_float(self.shell_input.text(), 0.0)

            # Wertbereichs-Validierung
            if self.cell_size < 1.0 or self.cell_size > 100.0:
                QMessageBox.warning(self, tr("Invalid Input"),
                    tr(f"Cell Size must be between 1.0 and 100.0 mm.\nEntered: {self.cell_size}"))
                return

            if self.beam_radius < 0.1 or self.beam_radius > 10.0:
                QMessageBox.warning(self, tr("Invalid Input"),
                    tr(f"Beam Radius must be between 0.1 and 10.0 mm.\nEntered: {self.beam_radius}"))
                return

            if self.shell_thickness < 0 or self.shell_thickness > 50.0:
                QMessageBox.warning(self, tr("Invalid Input"),
                    tr(f"Shell Thickness must be between 0 and 50.0 mm.\nEntered: {self.shell_thickness}"))
                return

            # Bei BCC ist kürzeste Beam-Länge ~0.866 * cell_size (Diagonale)
            min_beam_length = 0.5 * math.sqrt(3) * self.cell_size
            max_sensible_radius = min_beam_length / 4

            if self.beam_radius >= self.cell_size / 2:
                QMessageBox.warning(
                    self, tr("Invalid Input"),
                    tr("Beam radius must be < cell_size / 2.\n"
                       f"Maximum: {self.cell_size / 2:.1f}mm")
                )
                return

            if self.beam_radius > max_sensible_radius:
                reply = QMessageBox.question(
                    self, tr("Large Beam Radius"),
                    tr(f"Beam radius ({self.beam_radius}mm) is very large relative to "
                       f"cell size ({self.cell_size}mm).\n\n"
                       f"Recommended maximum: {max_sensible_radius:.1f}mm\n\n"
                       f"Large beams may result in a nearly solid structure "
                       f"instead of a visible lattice.\n\n"
                       f"Continue anyway?"),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return

            self.accept()
        except ValueError as e:
            logger.error(f"Invalid input: {e}")
