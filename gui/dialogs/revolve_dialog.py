"""
MashCad - Revolve Dialog
Revolve sketch profile around an axis.
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
from gui.dialogs.feature_edit_dialogs import _get_operation_key, _get_translated_operations


class RevolveDialog(QDialog):
    """Dialog fuer Revolve-Feature: Achse + Winkel + Operation"""

    def __init__(self, sketches, parent=None):
        """
        Args:
            sketches: Liste verfuegbarer Sketches
        """
        super().__init__(parent)
        self.sketches = sketches
        self.setWindowTitle(tr("Revolve"))
        self.setMinimumWidth(400)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Sketch selector
        sketch_group = QGroupBox(tr("Profile"))
        sketch_layout = QVBoxLayout()

        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Sketch:")))
        self.sketch_combo = QComboBox()
        for s in self.sketches:
            self.sketch_combo.addItem(s.name, s)
        row.addWidget(self.sketch_combo)
        sketch_layout.addLayout(row)

        sketch_group.setLayout(sketch_layout)
        layout.addWidget(sketch_group)

        # Revolve parameters
        param_group = QGroupBox(tr("Revolve Parameters"))
        param_layout = QVBoxLayout()

        # Axis
        axis_row = QHBoxLayout()
        axis_row.addWidget(QLabel(tr("Axis:")))
        self.axis_combo = QComboBox()
        self.axis_combo.addItems(["X", "Y", "Z"])
        self.axis_combo.setCurrentText("Y")
        axis_row.addWidget(self.axis_combo)
        axis_row.addStretch()
        param_layout.addLayout(axis_row)

        # Angle
        angle_row = QHBoxLayout()
        label = QLabel(tr("Angle:"))
        label.setMinimumWidth(100)
        angle_row.addWidget(label)
        self.angle_input = QLineEdit("360")
        validator = QDoubleValidator(0.1, 360.0, 2)
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.angle_input.setValidator(validator)
        angle_row.addWidget(self.angle_input)
        angle_row.addWidget(QLabel("deg"))
        param_layout.addLayout(angle_row)

        # Operation
        op_row = QHBoxLayout()
        op_row.addWidget(QLabel(tr("Operation:")))
        self.op_combo = QComboBox()
        self.op_combo.addItems(_get_translated_operations())
        op_row.addWidget(self.op_combo)
        op_row.addStretch()
        param_layout.addLayout(op_row)

        param_group.setLayout(param_layout)
        layout.addWidget(param_group)

        # Buttons
        button_layout = QHBoxLayout()
        cancel_btn = QPushButton(tr("Cancel"))
        cancel_btn.clicked.connect(self.reject)

        apply_btn = QPushButton(tr("Revolve"))
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._on_apply)
        apply_btn.setObjectName("primary")

        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(apply_btn)
        layout.addSpacing(20)
        layout.addLayout(button_layout)

        # Dark theme
        self.setStyleSheet(DesignTokens.stylesheet_dialog())

    def _on_apply(self):
        try:
            self.angle = float(self.angle_input.text() or "360")
            if self.angle <= 0 or self.angle > 360:
                logger.warning("Angle must be 0-360")
                return

            axis_map = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}
            self.axis = axis_map[self.axis_combo.currentText()]
            self.sketch = self.sketch_combo.currentData()
            self.operation = _get_operation_key(self.op_combo.currentText())

            if not self.sketch:
                logger.warning("No sketch selected")
                return

            self.accept()
        except ValueError as e:
            logger.error(f"Invalid input: {e}")
