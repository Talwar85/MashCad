"""
MashCad - Hole Dialog
Erstellt Bohrungen: Simple, Counterbore, Countersink.
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


class HoleDialog(QDialog):
    """Dialog fuer Hole-Feature: Typ, Durchmesser, Tiefe"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Hole"))
        self.setMinimumWidth(400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Hole Type
        param_group = QGroupBox(tr("Hole Parameters"))
        param_layout = QVBoxLayout()

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel(tr("Type:")))
        self.type_combo = QComboBox()
        self.type_combo.addItems([tr("Simple"), tr("Counterbore"), tr("Countersink")])
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        type_row.addWidget(self.type_combo)
        type_row.addStretch()
        param_layout.addLayout(type_row)

        # Diameter
        dia_row = QHBoxLayout()
        lbl = QLabel(tr("Diameter:"))
        lbl.setMinimumWidth(120)
        dia_row.addWidget(lbl)
        self.diameter_input = QLineEdit("8")
        self.diameter_input.setValidator(QDoubleValidator(0.1, 1000, 2))
        dia_row.addWidget(self.diameter_input)
        dia_row.addWidget(QLabel("mm"))
        param_layout.addLayout(dia_row)

        # Depth
        depth_row = QHBoxLayout()
        lbl2 = QLabel(tr("Depth:"))
        lbl2.setMinimumWidth(120)
        depth_row.addWidget(lbl2)
        self.depth_input = QLineEdit("0")
        self.depth_input.setValidator(QDoubleValidator(0, 1000, 2))
        depth_row.addWidget(self.depth_input)
        depth_row.addWidget(QLabel("mm (0=through)"))
        param_layout.addLayout(depth_row)

        # Counterbore params (hidden by default)
        self.cb_group = QGroupBox("Counterbore")
        cb_layout = QVBoxLayout()

        cb_dia_row = QHBoxLayout()
        cb_dia_row.addWidget(QLabel(tr("CB Diameter:")))
        self.cb_diameter_input = QLineEdit("12")
        self.cb_diameter_input.setValidator(QDoubleValidator(0.1, 1000, 2))
        cb_dia_row.addWidget(self.cb_diameter_input)
        cb_dia_row.addWidget(QLabel("mm"))
        cb_layout.addLayout(cb_dia_row)

        cb_depth_row = QHBoxLayout()
        cb_depth_row.addWidget(QLabel(tr("CB Depth:")))
        self.cb_depth_input = QLineEdit("3")
        self.cb_depth_input.setValidator(QDoubleValidator(0.1, 1000, 2))
        cb_depth_row.addWidget(self.cb_depth_input)
        cb_depth_row.addWidget(QLabel("mm"))
        cb_layout.addLayout(cb_depth_row)

        self.cb_group.setLayout(cb_layout)
        self.cb_group.setVisible(False)

        # Countersink params (hidden by default)
        self.cs_group = QGroupBox("Countersink")
        cs_layout = QVBoxLayout()

        cs_angle_row = QHBoxLayout()
        cs_angle_row.addWidget(QLabel(tr("Angle:")))
        self.cs_angle_input = QLineEdit("82")
        self.cs_angle_input.setValidator(QDoubleValidator(10, 170, 1))
        cs_angle_row.addWidget(self.cs_angle_input)
        cs_angle_row.addWidget(QLabel("deg"))
        cs_layout.addLayout(cs_angle_row)

        self.cs_group.setLayout(cs_layout)
        self.cs_group.setVisible(False)

        param_group.setLayout(param_layout)
        layout.addWidget(param_group)
        layout.addWidget(self.cb_group)
        layout.addWidget(self.cs_group)

        # Info
        info = QLabel(tr("Click on a face to place the hole center."))
        info.setStyleSheet("color: #999; font-style: italic;")
        layout.addWidget(info)

        # Buttons
        button_layout = QHBoxLayout()
        cancel_btn = QPushButton(tr("Cancel"))
        cancel_btn.clicked.connect(self.reject)

        apply_btn = QPushButton(tr("Create Hole"))
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

    def _on_type_changed(self, text):
        self.cb_group.setVisible(text == tr("Counterbore"))
        self.cs_group.setVisible(text == tr("Countersink"))

    def _on_apply(self):
        try:
            self.hole_type = self.type_combo.currentText().lower()
            self.diameter = float(self.diameter_input.text() or "8")
            self.depth = float(self.depth_input.text() or "0")

            if self.diameter <= 0:
                logger.warning("Diameter must be > 0")
                return

            self.counterbore_diameter = float(self.cb_diameter_input.text() or "12")
            self.counterbore_depth = float(self.cb_depth_input.text() or "3")
            self.countersink_angle = float(self.cs_angle_input.text() or "82")

            self.accept()
        except ValueError as e:
            logger.error(f"Invalid input: {e}")
