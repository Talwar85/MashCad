"""
MashCad - Lattice Dialog
Create beam-based lattice structures for lightweight 3D printing.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QGroupBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
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

        # Cell size
        size_row = QHBoxLayout()
        slbl = QLabel(tr("Cell Size:"))
        slbl.setMinimumWidth(120)
        size_row.addWidget(slbl)
        self.size_input = QLineEdit("5.0")
        sv = QDoubleValidator(1.0, 100.0, 2)
        sv.setNotation(QDoubleValidator.StandardNotation)
        self.size_input.setValidator(sv)
        size_row.addWidget(self.size_input)
        size_row.addWidget(QLabel("mm"))
        param_layout.addLayout(size_row)

        # Beam radius
        beam_row = QHBoxLayout()
        blbl = QLabel(tr("Beam Radius:"))
        blbl.setMinimumWidth(120)
        beam_row.addWidget(blbl)
        self.beam_input = QLineEdit("0.5")
        bv = QDoubleValidator(0.1, 10.0, 2)
        bv.setNotation(QDoubleValidator.StandardNotation)
        self.beam_input.setValidator(bv)
        beam_row.addWidget(self.beam_input)
        beam_row.addWidget(QLabel("mm"))
        param_layout.addLayout(beam_row)

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
        try:
            self.cell_type = self.type_combo.currentText()
            self.cell_size = float(self.size_input.text() or "5.0")
            self.beam_radius = float(self.beam_input.text() or "0.5")

            if self.cell_size <= 0 or self.beam_radius <= 0:
                logger.warning("All values must be > 0")
                return

            if self.beam_radius >= self.cell_size / 2:
                logger.warning("Beam radius must be < cell_size / 2")
                return

            self.accept()
        except ValueError as e:
            logger.error(f"Invalid input: {e}")
