"""
MashCad - Draft/Taper Dialog
Entformungsschraege auf Flaechen anwenden.
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


class DraftDialog(QDialog):
    """Dialog fuer Draft-Feature: Winkel + Richtung"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Draft / Taper"))
        self.setMinimumWidth(380)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        group = QGroupBox(tr("Draft Parameters"))
        group_layout = QVBoxLayout()

        # Angle
        angle_row = QHBoxLayout()
        lbl = QLabel(tr("Draft Angle:"))
        lbl.setMinimumWidth(120)
        angle_row.addWidget(lbl)
        self.angle_input = QLineEdit("5")
        validator = QDoubleValidator(0.1, 89.0, 2)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.angle_input.setValidator(validator)
        angle_row.addWidget(self.angle_input)
        angle_row.addWidget(QLabel("deg"))
        group_layout.addLayout(angle_row)

        # Pull Direction
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel(tr("Pull Direction:")))
        self.dir_combo = QComboBox()
        self.dir_combo.addItems([tr("Z (Up)"), tr("Y (Front)"), tr("X (Right)")])
        dir_row.addWidget(self.dir_combo)
        dir_row.addStretch()
        group_layout.addLayout(dir_row)

        group.setLayout(group_layout)
        layout.addWidget(group)

        info = QLabel(tr("Draft applies taper to all applicable faces."))
        info.setStyleSheet("color: #999; font-style: italic;")
        layout.addWidget(info)

        # Buttons
        button_layout = QHBoxLayout()
        cancel_btn = QPushButton(tr("Cancel"))
        cancel_btn.clicked.connect(self.reject)

        apply_btn = QPushButton(tr("Apply Draft"))
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._on_apply)
        apply_btn.setObjectName("primary")

        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(apply_btn)
        layout.addSpacing(20)
        layout.addLayout(button_layout)

        self.setStyleSheet(DesignTokens.stylesheet_dialog())

    def _on_apply(self):
        try:
            self.draft_angle = float(self.angle_input.text() or "5")
            if self.draft_angle <= 0 or self.draft_angle >= 90:
                logger.warning("Draft angle must be 0-90 degrees")
                return

            dir_map = {
                tr("Z (Up)"): (0, 0, 1),
                tr("Y (Front)"): (0, 1, 0),
                tr("X (Right)"): (1, 0, 0),
            }
            self.pull_direction = dir_map[self.dir_combo.currentText()]
            self.accept()
        except ValueError as e:
            logger.error(f"Invalid input: {e}")
