"""
CollapsibleSection — Auf/zuklappbare Sektion für Tool-Panels.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QSizePolicy
from PySide6.QtCore import Qt, Signal


class CollapsibleSection(QWidget):
    """Auf/zuklappbare Sektion mit Header-Button und Content-Area."""

    toggled = Signal(bool)

    def __init__(self, title: str, expanded: bool = False, parent=None):
        super().__init__(parent)
        self._expanded = expanded
        self._title = title

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header button
        self._header = QPushButton()
        self._header.setCursor(Qt.PointingHandCursor)
        self._header.setFocusPolicy(Qt.NoFocus)
        self._header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._header.setFixedHeight(28)
        self._header.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-bottom: 1px solid #2a2a2e;
                color: #888;
                font-weight: bold;
                font-size: 10px;
                text-transform: uppercase;
                text-align: left;
                padding: 6px 8px;
            }
            QPushButton:hover {
                background: #2a2a2e;
                color: #ccc;
            }
        """)
        self._header.clicked.connect(self._toggle)
        layout.addWidget(self._header)

        # Content container
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(5, 4, 5, 5)
        self._content_layout.setSpacing(4)
        layout.addWidget(self._content)

        self._update_header()
        self._content.setVisible(self._expanded)

    @property
    def content_layout(self):
        return self._content_layout

    @property
    def content_widget(self):
        return self._content

    def _toggle(self):
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._update_header()
        self.toggled.emit(self._expanded)

    def _update_header(self):
        chevron = "▾" if self._expanded else "▸"
        self._header.setText(f"  {chevron}  {self._title}")

    def set_expanded(self, expanded: bool):
        if self._expanded != expanded:
            self._expanded = expanded
            self._content.setVisible(expanded)
            self._update_header()
