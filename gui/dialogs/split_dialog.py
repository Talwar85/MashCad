"""
MashCad - Split Body Dialog
Koerper entlang einer Ebene teilen.
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


class SplitDialog(QDialog):
    """Dialog fuer Split-Feature: Ebene + Seite"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Split Body"))
        self.setMinimumWidth(400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        group = QGroupBox(tr("Split Plane"))
        group_layout = QVBoxLayout()

        # Plane selection
        plane_row = QHBoxLayout()
        plane_row.addWidget(QLabel(tr("Plane:")))
        self.plane_combo = QComboBox()
        self.plane_combo.addItems(["XY (Top)", "XZ (Front)", "YZ (Right)", "Custom"])
        self.plane_combo.currentTextChanged.connect(self._on_plane_changed)
        plane_row.addWidget(self.plane_combo)
        plane_row.addStretch()
        group_layout.addLayout(plane_row)

        # Offset
        offset_row = QHBoxLayout()
        lbl = QLabel(tr("Offset:"))
        lbl.setMinimumWidth(100)
        offset_row.addWidget(lbl)
        self.offset_input = QLineEdit("0")
        self.offset_input.setValidator(QDoubleValidator(-1000, 1000, 3))
        offset_row.addWidget(self.offset_input)
        offset_row.addWidget(QLabel("mm"))
        group_layout.addLayout(offset_row)

        # Keep side
        keep_row = QHBoxLayout()
        keep_row.addWidget(QLabel(tr("Keep:")))
        self.keep_combo = QComboBox()
        self.keep_combo.addItems([tr("Above"), tr("Below")])
        keep_row.addWidget(self.keep_combo)
        keep_row.addStretch()
        group_layout.addLayout(keep_row)

        group.setLayout(group_layout)
        layout.addWidget(group)

        # Buttons
        button_layout = QHBoxLayout()
        cancel_btn = QPushButton(tr("Cancel"))
        cancel_btn.clicked.connect(self.reject)

        apply_btn = QPushButton(tr("Split"))
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._on_apply)
        apply_btn.setObjectName("primary")

        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(apply_btn)
        layout.addSpacing(20)
        layout.addLayout(button_layout)

        self.setStyleSheet(DesignTokens.stylesheet_dialog())

    def _on_plane_changed(self, text):
        # Could enable custom plane inputs here
        pass

    def _on_apply(self):
        try:
            offset = float(self.offset_input.text() or "0")

            plane_map = {
                "XY (Top)": ((0, 0, offset), (0, 0, 1)),
                "XZ (Front)": ((0, offset, 0), (0, 1, 0)),
                "YZ (Right)": ((offset, 0, 0), (1, 0, 0)),
                "Custom": ((0, 0, offset), (0, 0, 1)),
            }
            origin, normal = plane_map[self.plane_combo.currentText()]
            self.plane_origin = origin
            self.plane_normal = normal
            self.keep_side = self.keep_combo.currentText().lower()

            self.accept()
        except ValueError as e:
            logger.error(f"Invalid input: {e}")
