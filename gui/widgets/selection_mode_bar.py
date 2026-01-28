"""
MashCad - Selection Mode Bar Widget
Figma-Style Buttons für Vertex/Edge/Face/Body Selektion im Viewport.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QButtonGroup
from PySide6.QtCore import Signal


class SelectionModeBar(QWidget):
    """Floating Selection Mode Bar für den Viewport."""

    mode_changed = Signal(str)  # "vertex", "edge", "face", "body"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._buttons = {}

        modes = [
            ("vertex", "● Vertex"),
            ("edge", "— Edge"),
            ("face", "□ Face"),
            ("body", "⬡ Body"),
        ]

        for mode_id, label in modes:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(38, 38, 38, 0.95);
                    border: 1px solid #404040;
                    border-radius: 4px;
                    padding: 6px 12px;
                    color: #d4d4d4;
                    font-size: 12px;
                    font-family: 'Segoe UI', sans-serif;
                }
                QPushButton:hover {
                    background: #404040;
                    border-color: #525252;
                }
                QPushButton:checked {
                    background: #2563eb;
                    border-color: #2563eb;
                    color: white;
                }
            """)
            btn.clicked.connect(lambda checked, m=mode_id: self._on_mode_clicked(m))

            self._button_group.addButton(btn)
            self._buttons[mode_id] = btn
            layout.addWidget(btn)

        # Default: Body mode
        self._buttons["body"].setChecked(True)
        self._current_mode = "body"

    def _on_mode_clicked(self, mode_id: str):
        """Handler für Mode-Button Klick."""
        self._current_mode = mode_id
        self.mode_changed.emit(mode_id)

    def set_mode(self, mode_id: str):
        """Setzt den aktuellen Mode programmatisch."""
        if mode_id in self._buttons:
            self._buttons[mode_id].setChecked(True)
            self._current_mode = mode_id

    def current_mode(self) -> str:
        """Gibt den aktuellen Mode zurück."""
        return self._current_mode
