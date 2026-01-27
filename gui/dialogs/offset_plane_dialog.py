"""
MashCad - Offset Plane Dialog
Create construction planes at an offset from standard planes or body faces.
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


class OffsetPlaneDialog(QDialog):
    """Dialog to create an offset construction plane."""

    def __init__(self, parent=None, face_info=None):
        """
        Args:
            parent: Parent widget
            face_info: Optional dict mit {'center': (x,y,z), 'normal': (x,y,z)}
                       wenn eine Fläche selektiert ist
        """
        super().__init__(parent)
        self.face_info = face_info
        self.setWindowTitle(tr("Offset Plane"))
        self.setMinimumWidth(350)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        group = QGroupBox(tr("Offset Plane"))
        group_layout = QVBoxLayout()

        # Base plane
        base_row = QHBoxLayout()
        lbl = QLabel(tr("Base Plane:"))
        lbl.setMinimumWidth(100)
        base_row.addWidget(lbl)
        self.base_combo = QComboBox()
        items = ["XY", "XZ", "YZ"]
        if self.face_info:
            items.append(tr("Selected Face"))
        self.base_combo.addItems(items)
        if self.face_info:
            self.base_combo.setCurrentIndex(len(items) - 1)
        base_row.addWidget(self.base_combo)
        base_row.addStretch()
        group_layout.addLayout(base_row)

        # Offset
        offset_row = QHBoxLayout()
        olbl = QLabel(tr("Offset:"))
        olbl.setMinimumWidth(100)
        offset_row.addWidget(olbl)
        self.offset_input = QLineEdit("0" if self.face_info else "10")
        validator = QDoubleValidator()
        validator.setNotation(QDoubleValidator.StandardNotation)
        self.offset_input.setValidator(validator)
        offset_row.addWidget(self.offset_input)
        offset_row.addWidget(QLabel("mm"))
        group_layout.addLayout(offset_row)

        # Name
        name_row = QHBoxLayout()
        nlbl = QLabel(tr("Name:"))
        nlbl.setMinimumWidth(100)
        name_row.addWidget(nlbl)
        self.name_input = QLineEdit("")
        self.name_input.setPlaceholderText(tr("auto"))
        name_row.addWidget(self.name_input)
        group_layout.addLayout(name_row)

        group.setLayout(group_layout)
        layout.addWidget(group)

        # Buttons
        btn_layout = QHBoxLayout()
        cancel = QPushButton(tr("Cancel"))
        cancel.clicked.connect(self.reject)

        create = QPushButton(tr("Create"))
        create.setDefault(True)
        create.clicked.connect(self._on_create)
        create.setObjectName("primary")

        btn_layout.addStretch()
        btn_layout.addWidget(cancel)
        btn_layout.addWidget(create)
        layout.addSpacing(20)
        layout.addLayout(btn_layout)

        # Dark theme
        self.setStyleSheet(DesignTokens.stylesheet_dialog())

    def _on_create(self):
        try:
            self.offset = float(self.offset_input.text() or "0")
            self.base = self.base_combo.currentText()
            self.plane_name = self.name_input.text().strip() or None
            self.use_face = (self.face_info is not None and
                             self.base == tr("Selected Face"))
            self.accept()
        except ValueError as e:
            logger.error(f"Invalid offset: {e}")
