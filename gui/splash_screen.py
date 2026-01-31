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

        # Logo laden (enthält bereits "MashCAD" Text)
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logo_path = os.path.join(base_path, "app.png")
        if os.path.exists(logo_path):
            logo = QPixmap(logo_path)
            if not logo.isNull():
                # Logo größer skalieren - Breite 320px
                logo_width = 320
                scaled_logo = logo.scaledToWidth(logo_width, Qt.SmoothTransformation)
                logo_x = (600 - scaled_logo.width()) // 2
                logo_y = 60

                # Subtiler Glow hinter dem Logo
                glow_center = QPointF(300, logo_y + scaled_logo.height() / 2)
                glow = QRadialGradient(glow_center, scaled_logo.width() * 0.5)
                glow.setColorAt(0, QColor(80, 160, 220, 40))
                glow.setColorAt(0.5, QColor(60, 130, 200, 15))
                glow.setColorAt(1, QColor(40, 100, 180, 0))
                painter.setPen(Qt.NoPen)
                painter.setBrush(glow)
                painter.drawEllipse(glow_center, scaled_logo.width() * 0.6, scaled_logo.height() * 0.8)

                # Logo zeichnen
                painter.drawPixmap(logo_x, logo_y, scaled_logo)

        # Tagline (unter dem Logo)
        font_tag = QFont("Segoe UI", 12)
        painter.setFont(font_tag)
        painter.setPen(QColor(140, 150, 170))
        painter.drawText(QRect(0, 210, 600, 30), Qt.AlignCenter, "Parametric CAD for 3D Printing")

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
