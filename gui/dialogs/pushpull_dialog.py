"""
MashCad - PushPull Dialog
Select a face and extrude/offset it along its normal.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGroupBox, QComboBox
)
from PySide6.QtGui import QDoubleValidator
from loguru import logger
from gui.design_tokens import DesignTokens
from i18n import tr


class PushPullDialog(QDialog):
    """Dialog to configure PushPull parameters after face selection."""

    def __init__(self, face_center=None, face_normal=None, parent=None):
        super().__init__(parent)
        self.face_center = face_center
        self.face_normal = face_normal
        self.setWindowTitle(tr("PushPull"))
        self.setMinimumWidth(380)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Face info
        info_group = QGroupBox(tr("Selected Face"))
        info_layout = QVBoxLayout()

        if self.face_center:
            c = self.face_center
            info_layout.addWidget(QLabel(
                f"{tr('Center')}: ({c[0]:.2f}, {c[1]:.2f}, {c[2]:.2f})"
            ))
        if self.face_normal:
            n = self.face_normal
            info_layout.addWidget(QLabel(
                f"{tr('Normal')}: ({n[0]:.3f}, {n[1]:.3f}, {n[2]:.3f})"
            ))

        if not self.face_center:
            info_layout.addWidget(QLabel(tr("No face selected. Click a face in the viewport.")))

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Distance
        param_group = QGroupBox(tr("Parameters"))
        param_layout = QVBoxLayout()

        dist_row = QHBoxLayout()
        dlbl = QLabel(tr("Distance:"))
        dlbl.setMinimumWidth(100)
        dist_row.addWidget(dlbl)
        self.distance_input = QLineEdit("10.0")
        v = QDoubleValidator(-500.0, 500.0, 3)
        v.setNotation(QDoubleValidator.StandardNotation)
        self.distance_input.setValidator(v)
        dist_row.addWidget(self.distance_input)
        dist_row.addWidget(QLabel("mm"))
        param_layout.addLayout(dist_row)

        hint = QLabel(tr("Positive = outward, negative = inward"))
        hint.setStyleSheet("color: #999; font-size: 11px; font-style: italic;")
        param_layout.addWidget(hint)

        param_group.setLayout(param_layout)
        layout.addWidget(param_group)

        # Buttons
        btn_layout = QHBoxLayout()
        cancel = QPushButton(tr("Cancel"))
        cancel.clicked.connect(self.reject)

        apply_btn = QPushButton(tr("Apply"))
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._on_apply)
        apply_btn.setObjectName("primary")

        btn_layout.addStretch()
        btn_layout.addWidget(cancel)
        btn_layout.addWidget(apply_btn)
        layout.addSpacing(10)
        layout.addLayout(btn_layout)

        self.setStyleSheet(DesignTokens.stylesheet_dialog())

    def _on_apply(self):
        try:
            self.distance = float(self.distance_input.text() or "10.0")
            if abs(self.distance) < 0.01:
                logger.warning("Distance too small")
                return
            self.accept()
        except ValueError as e:
            logger.error(f"Invalid distance: {e}")
