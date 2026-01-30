"""
MashCAD Splash Screen
Shows loading progress during application startup.
"""

from PySide6.QtWidgets import QSplashScreen, QApplication
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient
from PySide6.QtCore import Qt, QRect
import os


class MashCADSplash(QSplashScreen):
    """Modern splash screen with progress indicator."""

    def __init__(self):
        # Erstelle ein Pixmap für den Splash (600x350)
        pixmap = QPixmap(600, 350)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Hintergrund mit Gradient
        gradient = QLinearGradient(0, 0, 0, 350)
        gradient.setColorAt(0, QColor(30, 35, 45))
        gradient.setColorAt(1, QColor(20, 25, 35))
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, 600, 350, 15, 15)

        # Rahmen
        painter.setPen(QColor(60, 70, 90))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(1, 1, 598, 348, 15, 15)

        # App-Icon laden falls vorhanden
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_path, "app.png")
        if os.path.exists(icon_path):
            icon = QPixmap(icon_path)
            if not icon.isNull():
                # Icon skalieren und zentriert zeichnen
                scaled_icon = icon.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                icon_x = (600 - scaled_icon.width()) // 2
                painter.drawPixmap(icon_x, 60, scaled_icon)

        # App Name
        font_title = QFont("Segoe UI", 36, QFont.Bold)
        painter.setFont(font_title)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(QRect(0, 170, 600, 50), Qt.AlignCenter, "MashCAD")

        # Tagline
        font_tag = QFont("Segoe UI", 12)
        painter.setFont(font_tag)
        painter.setPen(QColor(150, 160, 180))
        painter.drawText(QRect(0, 220, 600, 25), Qt.AlignCenter, "Parametric CAD for 3D Printing")

        # Version
        font_ver = QFont("Segoe UI", 9)
        painter.setFont(font_ver)
        painter.setPen(QColor(100, 110, 130))
        painter.drawText(QRect(0, 320, 590, 20), Qt.AlignRight | Qt.AlignVCenter, "v0.1-alpha")

        painter.end()

        super().__init__(pixmap)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.SplashScreen)

        self._progress = 0
        self._status = "Starting..."

    def set_progress(self, value: int, status: str = None):
        """Update progress (0-100) and optional status text."""
        self._progress = min(100, max(0, value))
        if status:
            self._status = status
        self.repaint()
        QApplication.processEvents()

    def drawContents(self, painter: QPainter):
        """Override to draw progress bar and status."""
        painter.setRenderHint(QPainter.Antialiasing)

        # Status Text
        font = QFont("Segoe UI", 10)
        painter.setFont(font)
        painter.setPen(QColor(180, 190, 210))
        painter.drawText(QRect(20, 270, 560, 25), Qt.AlignCenter, self._status)

        # Progress Bar Background
        bar_rect = QRect(50, 300, 500, 6)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(50, 55, 65))
        painter.drawRoundedRect(bar_rect, 3, 3)

        # Progress Bar Fill
        if self._progress > 0:
            fill_width = int(500 * self._progress / 100)
            fill_rect = QRect(50, 300, fill_width, 6)

            # Gradient für Progress
            progress_gradient = QLinearGradient(50, 0, 550, 0)
            progress_gradient.setColorAt(0, QColor(70, 140, 220))
            progress_gradient.setColorAt(1, QColor(100, 180, 255))
            painter.setBrush(progress_gradient)
            painter.drawRoundedRect(fill_rect, 3, 3)
