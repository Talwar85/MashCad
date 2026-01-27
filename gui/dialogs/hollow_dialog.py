"""
MashCad - Hollow Dialog
Hollow a body with optional drain hole for SLA/SLS 3D printing.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGroupBox, QCheckBox, QComboBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from loguru import logger
from gui.design_tokens import DesignTokens
from i18n import tr


class HollowDialog(QDialog):
    """Dialog to hollow a body with optional drain hole."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Hollow Body"))
        self.setMinimumWidth(400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Wall thickness
        wall_group = QGroupBox(tr("Wall Thickness"))
        wall_layout = QVBoxLayout()

        thick_row = QHBoxLayout()
        lbl = QLabel(tr("Thickness:"))
        lbl.setMinimumWidth(120)
        thick_row.addWidget(lbl)
        self.thickness_input = QLineEdit("2.0")
        v = QDoubleValidator(0.1, 50.0, 2)
        v.setNotation(QDoubleValidator.StandardNotation)
        self.thickness_input.setValidator(v)
        thick_row.addWidget(self.thickness_input)
        thick_row.addWidget(QLabel("mm"))
        wall_layout.addLayout(thick_row)

        wall_group.setLayout(wall_layout)
        layout.addWidget(wall_group)

        # Drain hole
        drain_group = QGroupBox(tr("Drain Hole"))
        drain_layout = QVBoxLayout()

        self.drain_check = QCheckBox(tr("Add drain hole (for resin drainage)"))
        self.drain_check.toggled.connect(self._on_drain_toggled)
        drain_layout.addWidget(self.drain_check)

        dia_row = QHBoxLayout()
        self.dia_label = QLabel(tr("Hole Diameter:"))
        self.dia_label.setMinimumWidth(120)
        dia_row.addWidget(self.dia_label)
        self.drain_dia_input = QLineEdit("3.0")
        dv = QDoubleValidator(0.5, 20.0, 2)
        dv.setNotation(QDoubleValidator.StandardNotation)
        self.drain_dia_input.setValidator(dv)
        dia_row.addWidget(self.drain_dia_input)
        dia_row.addWidget(QLabel("mm"))
        drain_layout.addLayout(dia_row)

        dir_row = QHBoxLayout()
        self.dir_label = QLabel(tr("Direction:"))
        self.dir_label.setMinimumWidth(120)
        dir_row.addWidget(self.dir_label)
        self.dir_combo = QComboBox()
        self.dir_combo.addItems([
            tr("Down (-Z)"), tr("Up (+Z)"),
            tr("Front (-Y)"), tr("Back (+Y)"),
            tr("Left (-X)"), tr("Right (+X)")
        ])
        dir_row.addWidget(self.dir_combo)
        dir_row.addStretch()
        drain_layout.addLayout(dir_row)

        drain_group.setLayout(drain_layout)
        layout.addWidget(drain_group)

        # Initially disable drain inputs
        self._on_drain_toggled(False)

        # Buttons
        btn_layout = QHBoxLayout()
        cancel = QPushButton(tr("Cancel"))
        cancel.clicked.connect(self.reject)

        create = QPushButton(tr("Hollow"))
        create.setDefault(True)
        create.clicked.connect(self._on_create)
        create.setObjectName("primary")

        btn_layout.addStretch()
        btn_layout.addWidget(cancel)
        btn_layout.addWidget(create)
        layout.addSpacing(10)
        layout.addLayout(btn_layout)

        self.setStyleSheet(DesignTokens.stylesheet_dialog())

    def _on_drain_toggled(self, checked):
        self.drain_dia_input.setEnabled(checked)
        self.dia_label.setEnabled(checked)
        self.dir_combo.setEnabled(checked)
        self.dir_label.setEnabled(checked)

    def _on_create(self):
        try:
            self.wall_thickness = float(self.thickness_input.text() or "2.0")
            if self.wall_thickness <= 0:
                logger.warning("Wall thickness must be > 0")
                return

            self.drain_hole = self.drain_check.isChecked()
            self.drain_diameter = float(self.drain_dia_input.text() or "3.0")

            direction_map = {
                0: (0, 0, -1),   # Down
                1: (0, 0, 1),    # Up
                2: (0, -1, 0),   # Front
                3: (0, 1, 0),    # Back
                4: (-1, 0, 0),   # Left
                5: (1, 0, 0),    # Right
            }
            self.drain_direction = direction_map.get(self.dir_combo.currentIndex(), (0, 0, -1))

            self.accept()
        except ValueError as e:
            logger.error(f"Invalid input: {e}")
