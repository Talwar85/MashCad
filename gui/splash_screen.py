"""
MashCAD Splash Screen
Shows loading progress during application startup.
"""

from PySide6.QtWidgets import QSplashScreen, QApplication
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient, QRadialGradient
from PySide6.QtCore import Qt, QRect, QPointF
import os


class MashCADSplash(QSplashScreen):
    """Modern splash screen with progress indicator."""

    def __init__(self):
        # Erstelle ein Pixmap für den Splash (600x380)
        pixmap = QPixmap(600, 380)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Hintergrund mit Gradient
        gradient = QLinearGradient(0, 0, 0, 380)
        gradient.setColorAt(0, QColor(28, 32, 42))
        gradient.setColorAt(1, QColor(18, 22, 32))
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, 600, 380, 12, 12)

        # Subtiler Rahmen
        painter.setPen(QColor(50, 58, 75))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(1, 1, 598, 378, 12, 12)

        # App-Icon laden falls vorhanden
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_path, "app.png")
        if os.path.exists(icon_path):
            icon = QPixmap(icon_path)
            if not icon.isNull():
                # Icon groesser skalieren
                icon_size = 120
                scaled_icon = icon.scaled(icon_size, icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                icon_x = (600 - scaled_icon.width()) // 2
                icon_y = 45

                # Subtiler Glow hinter dem Icon
                glow_center = QPointF(300, icon_y + icon_size / 2)
                glow = QRadialGradient(glow_center, icon_size * 0.8)
                glow.setColorAt(0, QColor(80, 160, 220, 50))
                glow.setColorAt(0.5, QColor(60, 130, 200, 20))
                glow.setColorAt(1, QColor(40, 100, 180, 0))
                painter.setPen(Qt.NoPen)
                painter.setBrush(glow)
                painter.drawEllipse(glow_center, icon_size * 0.9, icon_size * 0.9)

                # Icon zeichnen
                painter.drawPixmap(icon_x, icon_y, scaled_icon)

        # App Name - naeher am Icon
        font_title = QFont("Segoe UI", 38, QFont.Bold)
        painter.setFont(font_title)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(QRect(0, 175, 600, 55), Qt.AlignCenter, "MashCAD")

        # Tagline
        font_tag = QFont("Segoe UI", 11)
        painter.setFont(font_tag)
        painter.setPen(QColor(140, 150, 170))
        painter.drawText(QRect(0, 230, 600, 25), Qt.AlignCenter, "Parametric CAD for 3D Printing")

        # Version
        font_ver = QFont("Segoe UI", 9)
        painter.setFont(font_ver)
        painter.setPen(QColor(90, 100, 120))
        painter.drawText(QRect(0, 350, 585, 20), Qt.AlignRight | Qt.AlignVCenter, "v0.1-alpha")

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
        painter.setPen(QColor(170, 180, 200))
        painter.drawText(QRect(20, 290, 560, 25), Qt.AlignCenter, self._status)

        # Progress Bar Background
        bar_rect = QRect(80, 325, 440, 5)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(45, 50, 60))
        painter.drawRoundedRect(bar_rect, 2, 2)

        # Progress Bar Fill
        if self._progress > 0:
            fill_width = int(440 * self._progress / 100)
            fill_rect = QRect(80, 325, fill_width, 5)

            # Gradient fuer Progress
            progress_gradient = QLinearGradient(80, 0, 520, 0)
            progress_gradient.setColorAt(0, QColor(65, 140, 220))
            progress_gradient.setColorAt(1, QColor(90, 175, 250))
            painter.setBrush(progress_gradient)
            painter.drawRoundedRect(fill_rect, 2, 2)
