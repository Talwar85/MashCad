"""
MashCad - Transform Edit Dialog
Ermöglicht parametrisches Editieren von Transform-Features
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QGroupBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from loguru import logger


class TransformEditDialog(QDialog):
    """
    Dialog zum Editieren von TransformFeature-Parametern.

    Features:
    - Move: Translation [x, y, z]
    - Rotate: Axis + Angle + Center
    - Scale: Factor + Center
    - Mirror: Plane
    """

    def __init__(self, feature, body, parent=None):
        super().__init__(parent)
        self.feature = feature
        self.body = body
        self.setWindowTitle(f"Edit {feature.name}")
        self.setMinimumWidth(400)

        self._setup_ui()
        self._load_current_values()

    def _setup_ui(self):
        """Erstellt die UI basierend auf Transform-Modus"""
        layout = QVBoxLayout(self)

        # Info-Header
        info = QLabel(f"<b>{self.feature.name}</b><br>Body: {self.body.name}")
        info.setStyleSheet("color: #ddd; padding: 10px; background: #1e1e1e; border-radius: 4px;")
        layout.addWidget(info)

        # Mode-spezifische Inputs
        if self.feature.mode == "move":
            self._create_move_inputs(layout)
        elif self.feature.mode == "rotate":
            self._create_rotate_inputs(layout)
        elif self.feature.mode == "scale":
            self._create_scale_inputs(layout)
        elif self.feature.mode == "mirror":
            self._create_mirror_inputs(layout)

        # Buttons
        button_layout = QHBoxLayout()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setDefault(True)
        self.apply_btn.clicked.connect(self._on_apply)
        self.apply_btn.setStyleSheet("""
            QPushButton {
                background: #0078d4;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #1084d8;
            }
        """)

        button_layout.addStretch()
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.apply_btn)

        layout.addSpacing(20)
        layout.addLayout(button_layout)

        # Dark Theme
        self.setStyleSheet("""
            QDialog {
                background: #2d2d30;
            }
            QLabel {
                color: #ddd;
                font-size: 13px;
            }
            QLineEdit {
                background: #1e1e1e;
                color: #ddd;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 6px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #0078d4;
            }
            QComboBox {
                background: #1e1e1e;
                color: #ddd;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton {
                background: #3f3f46;
                color: #ddd;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #505050;
            }
            QGroupBox {
                color: #ddd;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

    def _create_move_inputs(self, layout):
        """Input-Felder für Move (Translation)"""
        group = QGroupBox("Translation")
        group_layout = QVBoxLayout()

        self.move_x = self._create_number_input("X:", group_layout)
        self.move_y = self._create_number_input("Y:", group_layout)
        self.move_z = self._create_number_input("Z:", group_layout)

        group.setLayout(group_layout)
        layout.addWidget(group)

    def _create_rotate_inputs(self, layout):
        """Input-Felder für Rotate"""
        group = QGroupBox("Rotation")
        group_layout = QVBoxLayout()

        # Axis Selector
        axis_layout = QHBoxLayout()
        axis_layout.addWidget(QLabel("Axis:"))
        self.rotate_axis = QComboBox()
        self.rotate_axis.addItems(["X", "Y", "Z"])
        axis_layout.addWidget(self.rotate_axis)
        axis_layout.addStretch()
        group_layout.addLayout(axis_layout)

        # Angle
        self.rotate_angle = self._create_number_input("Angle (°):", group_layout)

        group.setLayout(group_layout)
        layout.addWidget(group)

        # Center (optional, read-only info)
        center_group = QGroupBox("Rotation Center (Body Center)")
        center_layout = QVBoxLayout()
        self.center_info = QLabel("")
        self.center_info.setStyleSheet("color: #999; font-size: 11px;")
        center_layout.addWidget(self.center_info)
        center_group.setLayout(center_layout)
        layout.addWidget(center_group)

    def _create_scale_inputs(self, layout):
        """Input-Felder für Scale"""
        group = QGroupBox("Scale Factor")
        group_layout = QVBoxLayout()

        self.scale_factor = self._create_number_input("Factor:", group_layout)

        info = QLabel("Note: Uniform scaling only (Build123d limitation)")
        info.setStyleSheet("color: #999; font-size: 11px; font-style: italic;")
        group_layout.addWidget(info)

        group.setLayout(group_layout)
        layout.addWidget(group)

    def _create_mirror_inputs(self, layout):
        """Input-Felder für Mirror"""
        group = QGroupBox("Mirror Plane")
        group_layout = QVBoxLayout()

        plane_layout = QHBoxLayout()
        plane_layout.addWidget(QLabel("Plane:"))
        self.mirror_plane = QComboBox()
        self.mirror_plane.addItems(["XY", "XZ", "YZ"])
        plane_layout.addWidget(self.mirror_plane)
        plane_layout.addStretch()

        group_layout.addLayout(plane_layout)
        group.setLayout(group_layout)
        layout.addWidget(group)

    def _create_number_input(self, label_text, parent_layout):
        """Helper: Erstellt Label + QLineEdit für Zahlen"""
        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setMinimumWidth(80)
        row.addWidget(label)

        line_edit = QLineEdit()
        validator = QDoubleValidator()
        validator.setNotation(QDoubleValidator.StandardNotation)
        line_edit.setValidator(validator)
        row.addWidget(line_edit)

        parent_layout.addLayout(row)
        return line_edit

    def _load_current_values(self):
        """Lädt aktuelle Werte aus dem Feature"""
        data = self.feature.data

        if self.feature.mode == "move":
            translation = data.get("translation", [0, 0, 0])
            self.move_x.setText(str(translation[0]))
            self.move_y.setText(str(translation[1]))
            self.move_z.setText(str(translation[2]))

        elif self.feature.mode == "rotate":
            axis = data.get("axis", "Z")
            angle = data.get("angle", 0)
            center = data.get("center", [0, 0, 0])

            self.rotate_axis.setCurrentText(axis)
            self.rotate_angle.setText(str(angle))
            self.center_info.setText(f"Center: ({center[0]:.2f}, {center[1]:.2f}, {center[2]:.2f})")

        elif self.feature.mode == "scale":
            factor = data.get("factor", 1.0)
            self.scale_factor.setText(str(factor))

        elif self.feature.mode == "mirror":
            plane = data.get("plane", "XY")
            self.mirror_plane.setCurrentText(plane)

    def _on_apply(self):
        """Aktualisiert Feature.data mit neuen Werten"""
        try:
            if self.feature.mode == "move":
                x = float(self.move_x.text() or "0")
                y = float(self.move_y.text() or "0")
                z = float(self.move_z.text() or "0")
                self.feature.data["translation"] = [x, y, z]

            elif self.feature.mode == "rotate":
                axis = self.rotate_axis.currentText()
                angle = float(self.rotate_angle.text() or "0")
                self.feature.data["axis"] = axis
                self.feature.data["angle"] = angle
                # Center bleibt unverändert

            elif self.feature.mode == "scale":
                factor = float(self.scale_factor.text() or "1.0")
                if factor <= 0:
                    logger.warning("Scale factor must be > 0")
                    return
                self.feature.data["factor"] = factor

            elif self.feature.mode == "mirror":
                plane = self.mirror_plane.currentText()
                self.feature.data["plane"] = plane

            logger.info(f"Transform-Feature aktualisiert: {self.feature.name}")
            self.accept()

        except ValueError as e:
            logger.error(f"Ungültige Eingabe: {e}")
