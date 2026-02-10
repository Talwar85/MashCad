"""
Getting Started Overlay - centered in the viewport for new users.
Disappears on first action click or dismiss.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QRect, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QPainterPath, QPolygonF

from i18n import tr
from config.recent_files import get_recent_files


class _IconWidget(QWidget):
    """Paints a small symbolic icon for each action type."""

    def __init__(self, icon_type: str, accent: str, parent=None):
        super().__init__(parent)
        self._type = icon_type
        self._accent = QColor(accent)
        self.setFixedSize(36, 36)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self._accent, 2.0)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        cx, cy = 18, 18

        if self._type == "sketch":
            # Pencil + square sketch symbol
            p.drawRect(QRectF(6, 6, 20, 20))
            p.drawLine(10, 22, 22, 10)
            p.setBrush(self._accent)
            p.drawEllipse(QPointF(22, 10), 2.5, 2.5)

        elif self._type == "primitive":
            # Isometric box
            pts_top = QPolygonF([
                QPointF(18, 6), QPointF(30, 12),
                QPointF(18, 18), QPointF(6, 12),
            ])
            p.setBrush(QColor(self._accent.red(), self._accent.green(), self._accent.blue(), 40))
            p.drawPolygon(pts_top)
            # Left face
            pts_left = QPolygonF([
                QPointF(6, 12), QPointF(18, 18),
                QPointF(18, 30), QPointF(6, 24),
            ])
            p.setBrush(QColor(self._accent.red(), self._accent.green(), self._accent.blue(), 25))
            p.drawPolygon(pts_left)
            # Right face
            pts_right = QPolygonF([
                QPointF(18, 18), QPointF(30, 12),
                QPointF(30, 24), QPointF(18, 30),
            ])
            p.setBrush(QColor(self._accent.red(), self._accent.green(), self._accent.blue(), 55))
            p.drawPolygon(pts_right)

        elif self._type == "mesh":
            # Triangle mesh / wireframe
            p.drawLine(8, 28, 18, 6)
            p.drawLine(18, 6, 28, 28)
            p.drawLine(8, 28, 28, 28)
            # Inner edges (mesh feel)
            p.setPen(QPen(self._accent, 1.2))
            p.drawLine(13, 17, 23, 17)
            p.drawLine(13, 17, 8, 28)
            p.drawLine(23, 17, 28, 28)
            p.drawLine(18, 6, 18, 17)
            # Vertices
            p.setBrush(self._accent)
            for pt in [(8, 28), (18, 6), (28, 28), (13, 17), (23, 17), (18, 17)]:
                p.drawEllipse(QPointF(*pt), 1.8, 1.8)

        p.end()


class GettingStartedOverlay(QWidget):
    """Transparent overlay centered in the viewport with quick-start actions."""
    action_triggered = Signal(str)
    recent_file_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_TranslucentBackground)
        recent_count = min(len(get_recent_files()), 3)
        height = 280 + (recent_count * 28 + 40 if recent_count > 0 else 0)
        self.setFixedSize(320, height)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("background: transparent;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        card = QWidget(self)
        card.setStyleSheet("""
            QWidget#gsCard {
                background: rgba(20, 24, 34, 235);
                border: 1px solid rgba(55, 65, 85, 200);
                border-radius: 14px;
            }
        """)
        card.setObjectName("gsCard")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(24, 20, 24, 24)
        card_lay.setSpacing(4)

        # Header row with title + close button
        header = QHBoxLayout()
        header.setSpacing(0)

        title = QLabel("MashCAD")
        title.setStyleSheet("""
            color: #d0d8ea;
            font-size: 18px;
            font-weight: 700;
            font-family: 'Segoe UI';
            background: transparent;
            border: none;
        """)
        header.addWidget(title)
        header.addStretch()

        btn_close = QPushButton("\u2715")
        btn_close.setFixedSize(24, 24)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 12px;
                color: #555;
                font-size: 14px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 15);
                color: #aaa;
            }
        """)
        btn_close.clicked.connect(self.hide)
        header.addWidget(btn_close)

        card_lay.addLayout(header)

        subtitle = QLabel(tr("Start by creating a sketch or adding a primitive."))
        subtitle.setAlignment(Qt.AlignLeft)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("""
            color: #5a6170;
            font-size: 11px;
            background: transparent;
            border: none;
            margin-bottom: 12px;
        """)
        card_lay.addWidget(subtitle)

        # Action buttons with icons
        for label, action_id, accent, icon_type in [
            (tr("New Sketch"), "new_sketch", "#3b82f6", "sketch"),
            (tr("Add Primitive"), "primitive_box", "#10b981", "primitive"),
            (tr("Import Mesh"), "import_mesh", "#8b5cf6", "mesh"),
        ]:
            row = QWidget()
            row.setCursor(Qt.PointingHandCursor)
            row.setFixedHeight(52)
            row.setStyleSheet(f"""
                QWidget#gsRow {{
                    background: rgba(255, 255, 255, 4);
                    border: 1px solid rgba(255, 255, 255, 6);
                    border-left: 3px solid transparent;
                    border-radius: 10px;
                }}
                QWidget#gsRow:hover {{
                    background: rgba(255, 255, 255, 8);
                    border-left: 3px solid {accent};
                }}
            """)
            row.setObjectName("gsRow")

            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(10, 6, 14, 6)
            row_lay.setSpacing(12)

            icon = _IconWidget(icon_type, accent)
            row_lay.addWidget(icon)

            text_col = QVBoxLayout()
            text_col.setSpacing(1)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"""
                color: #d4d8e4;
                font-size: 13px;
                font-weight: 600;
                background: transparent;
                border: none;
            """)
            text_col.addWidget(lbl)

            hints = {
                "new_sketch": tr("Draw 2D profiles, then extrude to 3D"),
                "primitive_box": tr("Box, Cylinder, Sphere, Cone"),
                "import_mesh": tr("Load STL, OBJ, PLY files"),
            }
            desc = QLabel(hints.get(action_id, ""))
            desc.setStyleSheet("""
                color: #4a5060;
                font-size: 10px;
                background: transparent;
                border: none;
            """)
            text_col.addWidget(desc)
            row_lay.addLayout(text_col, 1)

            # Make entire row clickable via overlay button
            click_btn = QPushButton(row)
            click_btn.setStyleSheet("background: transparent; border: none;")
            click_btn.setCursor(Qt.PointingHandCursor)
            click_btn.clicked.connect(lambda checked=False, a=action_id: self._on_click(a))

            card_lay.addWidget(row)

        # Recent files section
        recent = get_recent_files()
        if recent:
            import os
            sep = QLabel()
            sep.setFixedHeight(1)
            sep.setStyleSheet("background: rgba(255, 255, 255, 8); border: none; margin: 4px 0;")
            card_lay.addWidget(sep)

            recent_label = QLabel(tr("Recent"))
            recent_label.setStyleSheet("color: #4a5060; font-size: 10px; font-weight: 600; background: transparent; border: none; margin-top: 2px;")
            card_lay.addWidget(recent_label)

            for file_path in recent[:3]:
                fname = os.path.basename(file_path)
                btn = QPushButton(fname)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setToolTip(file_path)
                btn.setStyleSheet("""
                    QPushButton {
                        background: transparent;
                        border: none;
                        color: #6a7080;
                        font-size: 11px;
                        text-align: left;
                        padding: 3px 10px;
                    }
                    QPushButton:hover {
                        color: #a0a8b8;
                    }
                """)
                btn.clicked.connect(lambda checked=False, p=file_path: self._on_recent_click(p))
                card_lay.addWidget(btn)

        lay.addWidget(card)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Make invisible click buttons fill their parent rows
        for row in self.findChildren(QWidget, "gsRow"):
            for btn in row.findChildren(QPushButton):
                btn.setGeometry(0, 0, row.width(), row.height())

    def _on_click(self, action_id):
        self.action_triggered.emit(action_id)
        self.hide()

    def _on_recent_click(self, path):
        self.recent_file_requested.emit(path)
        self.hide()

    def center_on_parent(self):
        """Zentriert das Overlay im Parent-Widget."""
        if self.parent():
            pw = self.parent().width()
            ph = self.parent().height()
            x = (pw - self.width()) // 2
            y = (ph - self.height()) // 2 - 20
            self.move(max(0, x), max(0, y))
            self.raise_()
