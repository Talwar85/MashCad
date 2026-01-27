"""
MashCad - Pattern/Array Dialog
Erzeugt Linear oder Circular Patterns (Fusion 360-Style)
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QGroupBox, QRadioButton
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator, QIntValidator
from loguru import logger
from gui.design_tokens import DesignTokens
from i18n import tr


class PatternDialog(QDialog):
    """
    Dialog für Pattern/Array-Features.

    Pattern-Typen:
    - Linear: N Kopien entlang einer Achse mit festem Abstand
    - Circular: N Kopien um ein Zentrum rotiert
    """

    def __init__(self, body, parent=None):
        super().__init__(parent)
        self.body = body
        self.setWindowTitle(f"{tr('Pattern')}: {body.name}")
        self.setMinimumWidth(450)

        self._setup_ui()

    def _setup_ui(self):
        """Erstellt die UI"""
        layout = QVBoxLayout(self)

        # Info-Header
        info = QLabel(f"<b>{tr('Create Pattern')}</b><br>Body: {self.body.name}")
        info.setStyleSheet("color: #ddd; padding: 10px; background: #1e1e1e; border-radius: 4px;")
        layout.addWidget(info)

        # Pattern-Typ Auswahl
        type_group = QGroupBox(tr("Pattern Type"))
        type_layout = QHBoxLayout()

        self.linear_radio = QRadioButton(tr("Linear"))
        self.linear_radio.setChecked(True)
        self.linear_radio.toggled.connect(self._on_type_changed)

        self.circular_radio = QRadioButton(tr("Circular"))

        type_layout.addWidget(self.linear_radio)
        type_layout.addWidget(self.circular_radio)
        type_layout.addStretch()

        type_group.setLayout(type_layout)
        layout.addWidget(type_group)

        # Linear Pattern Settings
        self.linear_group = QGroupBox(tr("Linear Pattern Settings"))
        linear_layout = QVBoxLayout()

        # Count
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel(tr("Count:")))
        self.linear_count = QLineEdit("3")
        self.linear_count.setValidator(QIntValidator(2, 100))
        count_layout.addWidget(self.linear_count)
        linear_layout.addLayout(count_layout)

        # Spacing
        spacing_layout = QHBoxLayout()
        spacing_layout.addWidget(QLabel(tr("Spacing (mm):")))
        self.linear_spacing = QLineEdit("10.0")
        self.linear_spacing.setValidator(QDoubleValidator(0.01, 10000, 2))
        spacing_layout.addWidget(self.linear_spacing)
        linear_layout.addLayout(spacing_layout)

        # Axis
        axis_layout = QHBoxLayout()
        axis_layout.addWidget(QLabel(tr("Axis:")))
        self.linear_axis = QComboBox()
        self.linear_axis.addItems(["X", "Y", "Z"])
        axis_layout.addWidget(self.linear_axis)
        axis_layout.addStretch()
        linear_layout.addLayout(axis_layout)

        self.linear_group.setLayout(linear_layout)
        layout.addWidget(self.linear_group)

        # Circular Pattern Settings
        self.circular_group = QGroupBox(tr("Circular Pattern Settings"))
        circular_layout = QVBoxLayout()

        # Count
        count_layout2 = QHBoxLayout()
        count_layout2.addWidget(QLabel(tr("Count:")))
        self.circular_count = QLineEdit("8")
        self.circular_count.setValidator(QIntValidator(2, 100))
        count_layout2.addWidget(self.circular_count)
        circular_layout.addLayout(count_layout2)

        # Axis
        axis_layout2 = QHBoxLayout()
        axis_layout2.addWidget(QLabel(tr("Rotation Axis:")))
        self.circular_axis = QComboBox()
        self.circular_axis.addItems(["X", "Y", "Z"])
        self.circular_axis.setCurrentText("Z")
        axis_layout2.addWidget(self.circular_axis)
        axis_layout2.addStretch()
        circular_layout.addLayout(axis_layout2)

        # Full Circle Option
        full_circle_layout = QHBoxLayout()
        full_circle_layout.addWidget(QLabel(tr("Full Circle (360°):")))
        self.full_circle_check = QComboBox()
        self.full_circle_check.addItems(["Yes", "No"])
        full_circle_layout.addWidget(self.full_circle_check)
        full_circle_layout.addStretch()
        circular_layout.addLayout(full_circle_layout)

        # Angle (only if not full circle)
        angle_layout = QHBoxLayout()
        angle_layout.addWidget(QLabel(tr("Angle (°):")))
        self.circular_angle = QLineEdit("45.0")
        self.circular_angle.setValidator(QDoubleValidator(-360, 360, 2))
        angle_layout.addWidget(self.circular_angle)
        circular_layout.addLayout(angle_layout)

        self.circular_group.setLayout(circular_layout)
        layout.addWidget(self.circular_group)
        self.circular_group.hide()  # Initial versteckt

        # Buttons
        button_layout = QHBoxLayout()

        self.cancel_btn = QPushButton(tr("Cancel"))
        self.cancel_btn.clicked.connect(self.reject)

        self.apply_btn = QPushButton(tr("Create Pattern"))
        self.apply_btn.setDefault(True)
        self.apply_btn.clicked.connect(self._on_apply)
        self.apply_btn.setObjectName("primary")

        button_layout.addStretch()
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.apply_btn)

        layout.addSpacing(20)
        layout.addLayout(button_layout)

        # Dark Theme
        self.setStyleSheet(DesignTokens.stylesheet_dialog())

    def _on_type_changed(self, checked: bool):
        """Handler wenn Pattern-Typ gewechselt wird"""
        if checked:  # Linear selected
            self.linear_group.show()
            self.circular_group.hide()
        else:  # Circular selected
            self.linear_group.hide()
            self.circular_group.show()

    def _on_apply(self):
        """Validiert und schließt Dialog mit Pattern-Daten"""
        try:
            if self.linear_radio.isChecked():
                # Linear Pattern
                count = int(self.linear_count.text() or "3")
                spacing = float(self.linear_spacing.text() or "10.0")
                axis = self.linear_axis.currentText()

                if count < 2:
                    logger.warning("Count muss mindestens 2 sein")
                    return

                if spacing <= 0:
                    logger.warning("Spacing muss > 0 sein")
                    return

                self.pattern_data = {
                    "type": "linear",
                    "count": count,
                    "spacing": spacing,
                    "axis": axis
                }

            else:
                # Circular Pattern
                count = int(self.circular_count.text() or "8")
                axis = self.circular_axis.currentText()
                full_circle = self.full_circle_check.currentText() == "Yes"

                if count < 2:
                    logger.warning("Count muss mindestens 2 sein")
                    return

                if full_circle:
                    # 360° verteilt auf N Kopien
                    angle = 360.0 / count
                else:
                    angle = float(self.circular_angle.text() or "45.0")

                self.pattern_data = {
                    "type": "circular",
                    "count": count,
                    "axis": axis,
                    "angle": angle,
                    "full_circle": full_circle
                }

            logger.info(f"Pattern erstellt: {self.pattern_data}")
            self.accept()

        except ValueError as e:
            logger.error(f"Ungültige Eingabe: {e}")

    def get_pattern_data(self):
        """Gibt Pattern-Daten zurück"""
        return getattr(self, 'pattern_data', None)
