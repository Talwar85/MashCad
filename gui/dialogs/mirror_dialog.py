"""
MashCad - Mirror Dialog
Spiegelt Bodies an einer Ebene mit Option für Kopie.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QCheckBox, QRadioButton
)
from PySide6.QtCore import Qt
from loguru import logger
from gui.design_tokens import DesignTokens
from i18n import tr


class MirrorDialog(QDialog):
    """
    Dialog für Mirror-Operation mit Ebenenauswahl.

    Features:
    - Auswahl der Spiegelebene (XY, XZ, YZ)
    - Option: Kopie erstellen oder Original ersetzen
    - Moderne UI mit Dark Theme
    """

    def __init__(self, body, parent=None):
        super().__init__(parent)
        self.body = body
        self.setWindowTitle(f"{tr('Mirror')}: {body.name}")
        self.setMinimumWidth(400)

        self._setup_ui()

    def _setup_ui(self):
        """Erstellt die UI"""
        layout = QVBoxLayout(self)

        # Info-Header
        info = QLabel(f"<b>{tr('Mirror Body')}</b><br>Body: {self.body.name}")
        info.setStyleSheet("color: #ddd; padding: 10px; background: #1e1e1e; border-radius: 4px;")
        layout.addWidget(info)

        # Spiegelebene Auswahl
        plane_group = QGroupBox(tr("Mirror Plane"))
        plane_layout = QVBoxLayout()

        self.plane_xy = QRadioButton("XY " + tr("(mirror across Z)"))
        self.plane_xz = QRadioButton("XZ " + tr("(mirror across Y)"))
        self.plane_yz = QRadioButton("YZ " + tr("(mirror across X)"))

        self.plane_xz.setChecked(True)  # Default: XZ (häufigster Fall)

        plane_layout.addWidget(self.plane_xy)
        plane_layout.addWidget(self.plane_xz)
        plane_layout.addWidget(self.plane_yz)

        # Hinweis
        hint = QLabel(tr("The plane passes through the origin (0, 0, 0)"))
        hint.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        plane_layout.addWidget(hint)

        plane_group.setLayout(plane_layout)
        layout.addWidget(plane_group)

        # Optionen
        options_group = QGroupBox(tr("Options"))
        options_layout = QVBoxLayout()

        self.create_copy = QCheckBox(tr("Create copy (keep original)"))
        self.create_copy.setChecked(False)  # Default: Original ersetzen

        options_layout.addWidget(self.create_copy)
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # Buttons
        button_layout = QHBoxLayout()

        self.cancel_btn = QPushButton(tr("Cancel"))
        self.cancel_btn.clicked.connect(self.reject)

        self.apply_btn = QPushButton(tr("Mirror"))
        self.apply_btn.setDefault(True)
        self.apply_btn.clicked.connect(self.accept)
        self.apply_btn.setObjectName("primary")

        button_layout.addStretch()
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.apply_btn)

        layout.addSpacing(20)
        layout.addLayout(button_layout)

        # Dark Theme
        self.setStyleSheet(DesignTokens.stylesheet_dialog())

    def get_mirror_plane(self) -> str:
        """Gibt die gewählte Spiegelebene zurück."""
        if self.plane_xy.isChecked():
            return "XY"
        elif self.plane_xz.isChecked():
            return "XZ"
        else:
            return "YZ"

    def should_create_copy(self) -> bool:
        """Gibt zurück ob eine Kopie erstellt werden soll."""
        return self.create_copy.isChecked()
