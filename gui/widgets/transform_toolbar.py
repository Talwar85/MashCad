"""
MashCad - Transform Toolbar Widget
Floating vertical toolbar for Move/Rotate/Scale/PointMove operations.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QColor, QPainter, QBrush, QPen, QPainterPath


class TransformToolbar(QWidget):
    """Floating vertical toolbar for Move/Rotate/Scale/PointMove, positioned on the right edge of the viewport."""

    action_triggered = Signal(str)

    _ACTIONS = [
        ("move_body",           "⬚",  "#2563eb", "Move (G)"),
        ("rotate_body",         "↻",  "#22c55e", "Rotate (R)"),
        ("scale_body",          "⇔",  "#f59e0b", "Scale (S)"),
        ("point_to_point_move", "⤞",  "#a855f7", "Point Move"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons = {}
        self._active_action = None
        self._setup_ui()

    def _setup_ui(self):
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        for action_name, icon_char, color, tooltip in self._ACTIONS:
            btn = QPushButton(icon_char)
            btn.setFixedSize(42, 42)
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(self._button_style(color, active=False))
            btn.clicked.connect(lambda checked=False, a=action_name: self._on_clicked(a))
            layout.addWidget(btn)
            self._buttons[action_name] = btn

        self.setFixedSize(42 + 16, (42 * 4) + (6 * 3) + 16)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, float(self.width()), float(self.height()), 12.0, 12.0)
        painter.fillPath(path, QBrush(QColor(26, 26, 26, 235)))
        painter.end()

    @staticmethod
    def _button_style(color, active=False):
        hover = QColor(color).lighter(130).name()
        pressed = QColor(color).lighter(150).name()
        border = "2px solid {}".format(QColor(color).lighter(160).name()) if active else "2px solid transparent"
        return """
            QPushButton {{
                background: {bg};
                color: #ffffff;
                border: {border};
                border-radius: 10px;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {hover};
            }}
            QPushButton:pressed {{
                background: {pressed};
                border: 2px solid #ffffff;
            }}
        """.format(bg=color, border=border, hover=hover, pressed=pressed)

    def _on_clicked(self, action_name):
        self.set_active(action_name)
        self.action_triggered.emit(action_name)

    def set_active(self, action_name):
        self._active_action = action_name
        color_map = {a[0]: a[2] for a in self._ACTIONS}
        for name, btn in self._buttons.items():
            btn.setStyleSheet(self._button_style(color_map[name], active=(name == action_name)))

    def clear_active(self):
        self._active_action = None
        color_map = {a[0]: a[2] for a in self._ACTIONS}
        for name, btn in self._buttons.items():
            btn.setStyleSheet(self._button_style(color_map[name], active=False))
