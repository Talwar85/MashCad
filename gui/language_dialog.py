"""
Language Selection Dialog - shown on first start when no language is configured.
Also reusable from Settings to switch language at runtime.
"""

from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QApplication, QMessageBox
)
from PySide6.QtGui import QFont, QPainter, QColor, QLinearGradient
from PySide6.QtCore import Qt, QSize

from i18n import set_language


class LanguageDialog(QDialog):
    """Frameless dark dialog with two large language buttons."""

    def __init__(self, parent=None, is_first_start=True):
        super().__init__(parent)
        self._selected_language = None
        self._is_first_start = is_first_start

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(480, 260)

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        container = _RoundedContainer(self)
        root.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 32, 36, 32)
        layout.setSpacing(20)

        title = QLabel("Choose your language" if self._is_first_start
                       else "Change Language / Sprache ändern")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Segoe UI", 16, QFont.DemiBold))
        title.setStyleSheet("color: #c8d0e0; background: transparent;")
        layout.addWidget(title)

        subtitle = QLabel("Wähle deine Sprache" if self._is_first_start else "")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setFont(QFont("Segoe UI", 11))
        subtitle.setStyleSheet("color: #8890a4; background: transparent;")
        if self._is_first_start:
            layout.addWidget(subtitle)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(20)

        btn_de = self._make_button("Deutsch", "de")
        btn_en = self._make_button("English", "en")

        btn_row.addWidget(btn_de)
        btn_row.addWidget(btn_en)
        layout.addLayout(btn_row)

    def _make_button(self, label: str, lang: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedSize(QSize(185, 64))
        btn.setFont(QFont("Segoe UI", 15, QFont.DemiBold))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2e3a52, stop:1 #232d40);
                color: #d0d8ea;
                border: 1px solid #3e4c66;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3a4d6e, stop:1 #2c3a54);
                border: 1px solid #518cd8;
                color: #ffffff;
            }
            QPushButton:pressed {
                background: #1e2838;
            }
        """)
        btn.clicked.connect(lambda: self._choose(lang))
        return btn

    def _choose(self, lang: str):
        self._selected_language = lang
        set_language(lang)
        self.accept()

    def selected_language(self) -> Optional[str]:
        return self._selected_language


class _RoundedContainer(QLabel):
    """Dark rounded background matching the splash screen style."""

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0, QColor(28, 32, 42))
        grad.setColorAt(1, QColor(18, 22, 32))
        p.setBrush(grad)
        p.setPen(QColor(50, 58, 75))
        p.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 12, 12)
        p.end()


def ask_language_on_first_start(parent=None) -> Optional[str]:
    """Show the language dialog and return the chosen language code, or None."""
    dlg = LanguageDialog(parent, is_first_start=True)
    if dlg.exec() == QDialog.Accepted:
        return dlg.selected_language()
    return None


def ask_language_switch(parent=None) -> Optional[str]:
    """Show the language dialog for an in-app switch. Returns chosen lang or None."""
    dlg = LanguageDialog(parent, is_first_start=False)
    if dlg.exec() == QDialog.Accepted:
        return dlg.selected_language()
    return None
