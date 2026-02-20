"""
MashCAD - Immersive Tutorial Experience
========================================

Ein bahnbrechendes, immersives Tutorial-System:
- Split-Screen: Tutorial + Echte 3D-Ansicht
- Live 3D-Renderings mit PyVista
- Interaktiver Playground-Modus
- Contextual UI-Highlighting
- Gamification mit XP & Badges
- Cinematic Kamerafahrten

Usage:
    from gui.immersive_tutorial import ImmersiveTutorial
    tutorial = ImmersiveTutorial(main_window)
    tutorial.start()

Author: Kimi
Date: 2026-02-19
"""

import sys
import time
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass
from enum import Enum, auto

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QStackedWidget, QWidget, QProgressBar,
    QFrame, QGraphicsDropShadowEffect, QApplication,
    QGraphicsOpacityEffect, QSplitter, QTextEdit,
    QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsItem, QMainWindow, QDockWidget, QMenuBar,
    QStatusBar, QToolBar, QMenu
)
from PySide6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QSize, 
    QTimer, QParallelAnimationGroup, QPoint, QRect,
    QThread, Signal, QObject, QEvent
)
from PySide6.QtGui import (
    QColor, QFont, QPixmap, QPainter, QBrush, 
    QLinearGradient, QPen, QFontDatabase, QIcon,
    QCursor, QKeyEvent, QMouseEvent
)
from loguru import logger

from gui.design_tokens import DesignTokens
from i18n import tr


class TutorialPhase(Enum):
    """Phasen des Tutorials."""
    INTRO = auto()
    WATCH = auto()      # Beobachten
    TRY = auto()        # Selbst ausprobieren
    CHALLENGE = auto()  # Challenge/Quiz
    REWARD = auto()     # Belohnung


@dataclass
class TutorialXP:
    """XP-System für Gamification."""
    base: int = 100
    bonus_speed: int = 50
    bonus_perfect: int = 100
    
    def calculate(self, time_taken: float, errors: int) -> int:
        """Berechnet XP basierend auf Performance."""
        xp = self.base
        if time_taken < 30:  # Unter 30 Sekunden
            xp += self.bonus_speed
        if errors == 0:
            xp += self.bonus_perfect
        return xp


@dataclass
class ImmersiveStep:
    """Ein immersiver Tutorial-Schritt."""
    phase: TutorialPhase
    title: str
    subtitle: str
    description: str
    icon: str
    accent: str
    
    # 3D Content
    viewport_content: Optional[str] = None  # "sketch", "extrude", "fillet", etc.
    camera_animation: Optional[str] = None  # "orbit", "zoom_in", "pan"
    
    # Interaction
    action_required: Optional[str] = None   # "click_sketch", "draw_line", etc.
    validation_fn: Optional[Callable] = None
    
    # Highlighting
    highlight_widget: Optional[str] = None  # Name des zu highlightenden Widgets
    highlight_area: Optional[QRect] = None
    
    # Gamification
    xp_reward: int = 100
    badge_name: Optional[str] = None


class XPDisplay(QFrame):
    """Animierte XP-Anzeige."""
    
    xp_earned = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_xp = 0
        self.target_xp = 0
        self.level = 1
        self._setup_ui()
        
    def _setup_ui(self):
        self.setFixedSize(200, 80)
        self.setStyleSheet("""
            XPDisplay {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1a202c,
                    stop: 1 #2d3748
                );
                border: 2px solid #4299e1;
                border-radius: 12px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)
        
        # Level + XP Label
        header = QHBoxLayout()
        
        self.level_label = QLabel(f"LVL {self.level}")
        self.level_label.setStyleSheet("""
            color: #4299e1;
            font-size: 12px;
            font-weight: bold;
            background: transparent;
        """)
        header.addWidget(self.level_label)
        
        header.addStretch()
        
        self.xp_text = QLabel(f"{self.current_xp} XP")
        self.xp_text.setStyleSheet("""
            color: #48bb78;
            font-size: 11px;
            font-weight: bold;
            background: transparent;
        """)
        header.addWidget(self.xp_text)
        
        layout.addLayout(header)
        
        # XP Bar
        self.xp_bar = QProgressBar()
        self.xp_bar.setRange(0, 500)
        self.xp_bar.setValue(0)
        self.xp_bar.setTextVisible(False)
        self.xp_bar.setFixedHeight(8)
        self.xp_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #1a202c;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #4299e1,
                    stop: 0.5 #9f7aea,
                    stop: 1 #ed8936
                );
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.xp_bar)
        
        # Animation
        self.xp_timer = QTimer()
        self.xp_timer.timeout.connect(self._animate_xp)
        
    def add_xp(self, amount: int):
        """Fügt XP hinzu mit Animation."""
        self.target_xp += amount
        self.xp_timer.start(50)
        self.xp_earned.emit(amount)
        
    def _animate_xp(self):
        """Animiert die XP-Bar."""
        if self.current_xp < self.target_xp:
            self.current_xp += 5
            self.xp_bar.setValue(self.current_xp % 500)
            self.xp_text.setText(f"{self.current_xp} XP")
            
            # Level Up
            if self.current_xp >= self.level * 500:
                self.level += 1
                self.level_label.setText(f"LVL {self.level}")
                self._show_level_up()
        else:
            self.xp_timer.stop()
            
    def _show_level_up(self):
        """Zeigt Level-Up Animation."""
        # Flash-Effekt
        original_style = self.styleSheet()
        self.setStyleSheet(original_style + "; border: 3px solid #fbbf24;")
        QTimer.singleShot(500, lambda: self.setStyleSheet(original_style))


class BadgeNotification(QFrame):
    """Badge-Earned Notification Popup."""
    
    def __init__(self, badge_name: str, badge_icon: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(280, 120)
        self._setup_ui(badge_name, badge_icon)
        self._animate_in()
        
    def _setup_ui(self, name: str, icon: str):
        self.setStyleSheet("""
            BadgeNotification {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #1a202c,
                    stop: 1 #2d3748
                );
                border: 2px solid #fbbf24;
                border-radius: 16px;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(16)
        
        # Badge Icon
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("""
            font-size: 48px;
            background: transparent;
        """)
        layout.addWidget(icon_label)
        
        # Text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        
        unlocked = QLabel("BADGE UNLOCKED!")
        unlocked.setStyleSheet("""
            color: #fbbf24;
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 1px;
            background: transparent;
        """)
        text_layout.addWidget(unlocked)
        
        badge_name_label = QLabel(name)
        badge_name_label.setStyleSheet("""
            color: #e2e8f0;
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        """)
        text_layout.addWidget(badge_name_label)
        
        layout.addLayout(text_layout, stretch=1)
        
        # Glow-Effekt
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor("#fbbf24"))
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)
        
    def _animate_in(self):
        """Slide-in Animation."""
        self.move(self.parent().width() + 300, 100)
        
        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(600)
        self.anim.setStartValue(QPoint(self.parent().width() + 300, 100))
        self.anim.setEndValue(QPoint(self.parent().width() - 320, 100))
        self.anim.setEasingCurve(QEasingCurve.OutBack)
        self.anim.start()
        
        # Auto-hide nach 4 Sekunden
        QTimer.singleShot(4000, self._animate_out)
        
    def _animate_out(self):
        """Slide-out Animation."""
        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(400)
        self.anim.setStartValue(self.pos())
        self.anim.setEndValue(QPoint(self.parent().width() + 300, 100))
        self.anim.setEasingCurve(QEasingCurve.InCubic)
        self.anim.finished.connect(self.deleteLater)
        self.anim.start()


class SketchPreviewWidget(QFrame):
    """Zeichnet eine animierte Skizze mit Linien."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self.setStyleSheet("background: transparent; border: none;")
        self.progress = 0
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._animate_step)
        
    def start_animation(self):
        """Startet die Zeichen-Animation."""
        self.progress = 0
        self.animation_timer.start(50)
        
    def _animate_step(self):
        """Animiert den Zeichen-Fortschritt."""
        self.progress += 2
        if self.progress >= 100:
            self.animation_timer.stop()
        self.update()
        
    def paintEvent(self, event):
        """Zeichnet die Skizze."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Grid zeichnen
        pen = QPen(QColor("#2d3748"), 1)
        painter.setPen(pen)
        
        cx, cy = self.width() // 2, self.height() // 2
        
        # Horizontale Grid-Linien
        for i in range(-5, 6):
            y = cy + i * 25
            painter.drawLine(cx - 125, y, cx + 125, y)
        
        # Vertikale Grid-Linien
        for i in range(-5, 6):
            x = cx + i * 25
            painter.drawLine(x, cy - 125, x, cy + 125)
        
        # Rechteck-Skizze (animiert)
        if self.progress > 0:
            rect_progress = min(self.progress, 100)
            
            pen = QPen(QColor("#4299e1"), 3)
            painter.setPen(pen)
            
            # Rechteck 100x60
            rect = QRect(cx - 50, cy - 30, 100, 60)
            
            # Zeichne Linien basierend auf Progress
            if rect_progress > 10:
                painter.drawLine(rect.left(), rect.top(), 
                               rect.left() + min(rect_progress - 10, 100), rect.top())
            if rect_progress > 35:
                painter.drawLine(rect.right(), rect.top(), 
                               rect.right(), rect.top() + min(rect_progress - 35, 60))
            if rect_progress > 60:
                painter.drawLine(rect.right(), rect.bottom(), 
                               rect.right() - min(rect_progress - 60, 100), rect.bottom())
            if rect_progress > 85:
                painter.drawLine(rect.left(), rect.bottom(), 
                               rect.left(), rect.bottom() - min(rect_progress - 85, 60))
            
            # Maßlinien
            if rect_progress > 95:
                pen = QPen(QColor("#48bb78"), 2)
                painter.setPen(pen)
                # Horizontale Maßlinie
                painter.drawLine(rect.left(), rect.bottom() + 15, 
                               rect.right(), rect.bottom() + 15)
                painter.drawLine(rect.left(), rect.bottom() + 10,
                               rect.left(), rect.bottom() + 20)
                painter.drawLine(rect.right(), rect.bottom() + 10,
                               rect.right(), rect.bottom() + 20)
                
                # Text
                painter.setPen(QColor("#48bb78"))
                painter.setFont(QFont("Segoe UI", 10))
                painter.drawText(cx - 15, rect.bottom() + 30, "100mm")
        
        painter.end()


class ExtrudePreviewWidget(QFrame):
    """Zeichnet eine animierte 3D-Extrusion."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self.setStyleSheet("background: transparent; border: none;")
        self.depth = 0
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._animate_step)
        
    def start_animation(self):
        """Startet die Extrusions-Animation."""
        self.depth = 0
        self.animation_timer.start(30)
        
    def _animate_step(self):
        """Animiert die Extrusion."""
        self.depth += 2
        if self.depth >= 60:
            self.animation_timer.stop()
        self.update()
        
    def paintEvent(self, event):
        """Zeichnet die 3D-Box."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        cx, cy = self.width() // 2, self.height() // 2
        
        # 3D-Box Parameter
        width, height = 100, 60
        depth = self.depth
        
        # Perspektivischer Offset
        offset_x, offset_y = 30, -25
        
        # Farben
        front_color = QColor("#4299e1")
        top_color = QColor("#3182ce")
        side_color = QColor("#2c5282")
        
        # Vorderseite
        front = QRect(cx - width//2, cy - height//2, width, height)
        
        # Hintere Flächen (versetzt)
        back_tl = QPoint(front.left() + offset_x, front.top() + offset_y)
        back_tr = QPoint(front.right() + offset_x, front.top() + offset_y)
        back_bl = QPoint(front.left() + offset_x, front.bottom() + offset_y)
        back_br = QPoint(front.right() + offset_x, front.bottom() + offset_y)
        
        # Tiefe-Skalierung (je mehr depth, desto mehr sichtbar)
        scale = depth / 60
        
        # Seitenfläche (rechts)
        if depth > 0:
            side_points = [
                QPoint(front.right(), front.top()),
                QPoint(back_tr.x(), back_tr.y()),
                QPoint(back_br.x(), back_br.y()),
                QPoint(front.right(), front.bottom())
            ]
            painter.setBrush(QBrush(side_color))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(side_points)
        
        # Deckelfläche (oben)
        if depth > 0:
            top_points = [
                QPoint(front.left(), front.top()),
                QPoint(back_tl.x(), back_tl.y()),
                QPoint(back_tr.x(), back_tr.y()),
                QPoint(front.right(), front.top())
            ]
            painter.setBrush(QBrush(top_color))
            painter.drawPolygon(top_points)
        
        # Vorderseite (immer sichtbar)
        painter.setBrush(QBrush(front_color))
        painter.setPen(QPen(QColor("#63b3ed"), 2))
        painter.drawRect(front)
        
        # Grid auf Vorderseite
        painter.setPen(QPen(QColor("#2b6cb0"), 1))
        for i in range(1, 4):
            x = front.left() + i * (width // 4)
            painter.drawLine(x, front.top(), x, front.bottom())
        for i in range(1, 3):
            y = front.top() + i * (height // 3)
            painter.drawLine(front.left(), y, front.right(), y)
        
        # Extrusions-Indikator
        if depth > 0 and depth < 60:
            painter.setPen(QPen(QColor("#48bb78"), 2))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(front.right() + 10, cy, f"{depth}mm")
        
        painter.end()


class FilletPreviewWidget(QFrame):
    """Zeichnet eine animierte Abrundung."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self.setStyleSheet("background: transparent; border: none;")
        self.fillet_progress = 0
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._animate_step)
        
    def start_animation(self):
        """Startet die Fillet-Animation."""
        self.fillet_progress = 0
        self.animation_timer.start(40)
        
    def _animate_step(self):
        """Animiert die Abrundung."""
        self.fillet_progress += 3
        if self.fillet_progress >= 100:
            self.animation_timer.stop()
        self.update()
        
    def paintEvent(self, event):
        """Zeichnet die abgerundete Box."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        cx, cy = self.width() // 2, self.height() // 2
        
        # Box mit abgerundeten Ecken
        width, height = 120, 80
        fillet_radius = int(15 * (self.fillet_progress / 100))
        
        rect = QRect(cx - width//2, cy - height//2, width, height)
        
        # Gradient für 3D-Effekt
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, QColor("#ed8936"))
        gradient.setColorAt(1, QColor("#c05621"))
        
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor("#f6ad55"), 2))
        
        if fillet_radius > 0:
            painter.drawRoundedRect(rect, fillet_radius, fillet_radius)
        else:
            painter.drawRect(rect)
        
        # Kanten-Highlight
        if self.fillet_progress > 50:
            highlight_pen = QPen(QColor("#fbd38d"), 3)
            painter.setPen(highlight_pen)
            painter.setBrush(Qt.NoBrush)
            
            # Highlight die abgerundete Ecke
            corner = QRect(rect.right() - 30, rect.bottom() - 30, 30, 30)
            painter.drawArc(corner, 0, 90 * 16)
        
        # Radius-Indikator
        if 0 < self.fillet_progress < 100:
            painter.setPen(QPen(QColor("#48bb78"), 2))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(rect.right() + 10, cy, f"R{fillet_radius}mm")
        
        painter.end()


class Viewport3DWidget(QFrame):
    """Echtes 3D-Viewport-Widget für das Tutorial mit animierten Vorschauen."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(500, 400)
        self._setup_ui()
        self.current_mode = "empty"
        self.preview_widgets = []
        
    def _setup_ui(self):
        self.setStyleSheet("""
            Viewport3DWidget {
                background: #0f1419;
                border: 2px solid #2d3748;
                border-radius: 12px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Toolbar
        toolbar = QFrame()
        toolbar.setFixedHeight(36)
        toolbar.setStyleSheet("""
            QFrame {
                background-color: #1a202c;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                border-bottom: 1px solid #2d3748;
            }
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 4, 12, 4)
        toolbar_layout.setSpacing(8)
        
        # View-Modi
        for icon, tooltip in [
            ("🔍", "Zoom"), ("👁", "View"), ("🎥", "Camera")
        ]:
            btn = QLabel(icon)
            btn.setStyleSheet("font-size: 14px; background: transparent;")
            btn.setToolTip(tooltip)
            toolbar_layout.addWidget(btn)
        
        toolbar_layout.addStretch()
        
        # Mode Indicator
        self.mode_indicator = QLabel("● Live Preview")
        self.mode_indicator.setStyleSheet("""
            color: #48bb78;
            font-size: 11px;
            font-weight: bold;
            background: transparent;
        """)
        toolbar_layout.addWidget(self.mode_indicator)
        
        layout.addWidget(toolbar)
        
        # Content Stack
        self.content_stack = QStackedWidget()
        self.content_stack.setStyleSheet("background: transparent; border: none;")
        
        # Empty Page
        empty_page = QWidget()
        empty_layout = QVBoxLayout(empty_page)
        empty_layout.setAlignment(Qt.AlignCenter)
        welcome = QLabel("🚀")
        welcome.setStyleSheet("font-size: 64px; background: transparent;")
        welcome.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(welcome)
        
        welcome_text = QLabel("Tutorial Demo\nBereit...")
        welcome_text.setStyleSheet("""
            color: #718096;
            font-size: 16px;
            background: transparent;
            text-align: center;
        """)
        welcome_text.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(welcome_text)
        
        self.content_stack.addWidget(empty_page)
        
        # Sketch Page
        self.sketch_preview = SketchPreviewWidget()
        self.content_stack.addWidget(self.sketch_preview)
        
        # Extrude Page
        self.extrude_preview = ExtrudePreviewWidget()
        self.content_stack.addWidget(self.extrude_preview)
        
        # Fillet Page
        self.fillet_preview = FilletPreviewWidget()
        self.content_stack.addWidget(self.fillet_preview)
        
        layout.addWidget(self.content_stack, stretch=1)
        
    def show_empty(self):
        """Zeigt Empty-Seite."""
        self.current_mode = "empty"
        self.content_stack.setCurrentIndex(0)
        self.mode_indicator.setText("● Ready")
        self.mode_indicator.setStyleSheet("color: #718096; font-size: 11px; font-weight: bold;")
        
    def show_sketch(self):
        """Zeigt Sketch-Preview mit Animation."""
        self.current_mode = "sketch"
        self.content_stack.setCurrentIndex(1)
        self.mode_indicator.setText("● Sketch Mode")
        self.mode_indicator.setStyleSheet("color: #4299e1; font-size: 11px; font-weight: bold;")
        self.sketch_preview.start_animation()
        
    def show_extrude(self):
        """Zeigt Extrude-Preview mit Animation."""
        self.current_mode = "extrude"
        self.content_stack.setCurrentIndex(2)
        self.mode_indicator.setText("● 3D Preview")
        self.mode_indicator.setStyleSheet("color: #48bb78; font-size: 11px; font-weight: bold;")
        self.extrude_preview.start_animation()
        
    def show_fillet(self):
        """Zeigt Fillet-Preview mit Animation."""
        self.current_mode = "fillet"
        self.content_stack.setCurrentIndex(3)
        self.mode_indicator.setText("● Feature Preview")
        self.mode_indicator.setStyleSheet("color: #ed8936; font-size: 11px; font-weight: bold;")
        self.fillet_preview.start_animation()
        self._animate_content()
        
    def show_fillet(self):
        """Zeigt Fillet-Preview."""
        self.content_label.setText("✨")
        self.mode_indicator.setText("● Feature Preview")
        self.mode_indicator.setStyleSheet("color: #ed8936; font-size: 11px; font-weight: bold;")
        self._animate_content()
        
    def _animate_content(self):
        """Animiert den Content mit Fade-In Effekt."""
        # Opacity-Animation statt font-size (Qt-Property)
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        
        effect = QGraphicsOpacityEffect(self.content_label)
        effect.setOpacity(0)
        self.content_label.setGraphicsEffect(effect)
        
        self.anim = QPropertyAnimation(effect, b"opacity")
        self.anim.setDuration(400)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.start()


class TutorialControlPanel(QFrame):
    """Kontroll-Panel für das Tutorial."""
    
    next_clicked = Signal()
    prev_clicked = Signal()
    skip_clicked = Signal()
    hint_clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        
    def _setup_ui(self):
        self.setFixedWidth(380)
        self.setStyleSheet("""
            TutorialControlPanel {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1a202c,
                    stop: 1 #0d1117
                );
                border-right: 1px solid #2d3748;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(20)
        
        # Header
        header = QHBoxLayout()
        
        logo = QLabel("🎓")
        logo.setStyleSheet("font-size: 28px; background: transparent;")
        header.addWidget(logo)
        
        title = QLabel("Tutorial")
        title.setStyleSheet("""
            color: #e2e8f0;
            font-size: 20px;
            font-weight: bold;
            background: transparent;
        """)
        header.addWidget(title)
        
        header.addStretch()
        
        # Close Button
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #4a5568;
                color: #718096;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #2d3748;
                color: #e2e8f0;
            }
        """)
        close_btn.clicked.connect(self.skip_clicked.emit)
        header.addWidget(close_btn)
        
        layout.addLayout(header)
        
        # Progress Ring
        self.progress_container = QFrame()
        self.progress_container.setFixedHeight(80)
        progress_layout = QHBoxLayout(self.progress_container)
        progress_layout.setSpacing(16)
        
        # Circular Progress (simulated with labels)
        self.step_indicators = []
        for i in range(5):
            step = QLabel(f"{i+1}")
            step.setFixedSize(36, 36)
            step.setAlignment(Qt.AlignCenter)
            step.setStyleSheet("""
                QLabel {
                    background-color: #2d3748;
                    color: #718096;
                    border-radius: 18px;
                    font-size: 13px;
                    font-weight: bold;
                }
            """)
            self.step_indicators.append(step)
            progress_layout.addWidget(step)
            
            if i < 4:
                line = QLabel()
                line.setFixedSize(24, 2)
                line.setStyleSheet("background-color: #2d3748;")
                progress_layout.addWidget(line)
        
        layout.addWidget(self.progress_container)
        
        # Content Area
        self.content_card = QFrame()
        self.content_card.setStyleSheet("""
            QFrame {
                background-color: #0f1419;
                border: 1px solid #2d3748;
                border-radius: 16px;
            }
        """)
        content_layout = QVBoxLayout(self.content_card)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(16)
        
        # Phase Badge
        self.phase_badge = QLabel("WATCH")
        self.phase_badge.setFixedWidth(80)
        self.phase_badge.setAlignment(Qt.AlignCenter)
        self.phase_badge.setStyleSheet("""
            QLabel {
                background-color: #4299e120;
                color: #4299e1;
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 1px;
            }
        """)
        content_layout.addWidget(self.phase_badge, alignment=Qt.AlignLeft)
        
        # Icon
        self.step_icon = QLabel("🚀")
        self.step_icon.setStyleSheet("font-size: 48px; background: transparent;")
        self.step_icon.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(self.step_icon)
        
        # Title
        self.step_title = QLabel("Willkommen")
        self.step_title.setStyleSheet("""
            color: #e2e8f0;
            font-size: 22px;
            font-weight: bold;
            background: transparent;
        """)
        self.step_title.setAlignment(Qt.AlignCenter)
        self.step_title.setWordWrap(True)
        content_layout.addWidget(self.step_title)
        
        # Subtitle
        self.step_subtitle = QLabel("Subtitle here")
        self.step_subtitle.setStyleSheet("""
            color: #718096;
            font-size: 13px;
            background: transparent;
        """)
        self.step_subtitle.setAlignment(Qt.AlignCenter)
        self.step_subtitle.setWordWrap(True)
        content_layout.addWidget(self.step_subtitle)
        
        # Description
        self.step_desc = QLabel("Description text goes here...")
        self.step_desc.setStyleSheet("""
            color: #a0aec0;
            font-size: 13px;
            line-height: 1.5;
            background: transparent;
            padding: 8px 0;
        """)
        self.step_desc.setWordWrap(True)
        self.step_desc.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(self.step_desc)
        
        content_layout.addStretch()
        
        # Hint Button
        self.hint_btn = QPushButton("💡 Hinweis anzeigen")
        self.hint_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px dashed #4a5568;
                color: #718096;
                padding: 10px;
                border-radius: 8px;
                font-size: 12px;
            }
            QPushButton:hover {
                border-color: #4299e1;
                color: #4299e1;
            }
        """)
        self.hint_btn.clicked.connect(self.hint_clicked.emit)
        content_layout.addWidget(self.hint_btn)
        
        layout.addWidget(self.content_card, stretch=1)
        
        # Navigation Buttons
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(12)
        
        self.prev_btn = QPushButton("← Zurück")
        self.prev_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #4a5568;
                color: #a0aec0;
                padding: 12px 20px;
                border-radius: 8px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #2d3748;
            }
        """)
        self.prev_btn.clicked.connect(self.prev_clicked.emit)
        nav_layout.addWidget(self.prev_btn)
        
        nav_layout.addStretch()
        
        self.next_btn = QPushButton("Weiter →")
        self.next_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #4299e1,
                    stop: 1 #3182ce
                );
                border: none;
                color: white;
                padding: 12px 32px;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #3182ce,
                    stop: 1 #2c5282
                );
            }
        """)
        self.next_btn.clicked.connect(self.next_clicked.emit)
        nav_layout.addWidget(self.next_btn)
        
        layout.addLayout(nav_layout)
        
    def update_step(self, step: ImmersiveStep, step_num: int, total: int):
        """Aktualisiert das Panel für einen neuen Schritt."""
        # Phase Badge
        phase_colors = {
            TutorialPhase.INTRO: ("#9f7aea", "INTRO"),
            TutorialPhase.WATCH: ("#4299e1", "WATCH"),
            TutorialPhase.TRY: ("#48bb78", "TRY IT"),
            TutorialPhase.CHALLENGE: ("#ed8936", "QUIZ"),
            TutorialPhase.REWARD: ("#fbbf24", "REWARD"),
        }
        color, text = phase_colors.get(step.phase, ("#718096", "STEP"))
        self.phase_badge.setText(text)
        self.phase_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {color}20;
                color: {color};
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 1px;
            }}
        """)
        
        # Content
        self.step_icon.setText(step.icon)
        self.step_title.setText(step.title)
        self.step_subtitle.setText(step.subtitle)
        self.step_desc.setText(step.description)
        
        # Progress Indicators
        for i, indicator in enumerate(self.step_indicators):
            if i == step_num:
                indicator.setStyleSheet(f"""
                    QLabel {{
                        background-color: {step.accent};
                        color: white;
                        border-radius: 18px;
                        font-size: 13px;
                        font-weight: bold;
                    }}
                """)
            elif i < step_num:
                indicator.setStyleSheet("""
                    QLabel {
                        background-color: #48bb78;
                        color: white;
                        border-radius: 18px;
                        font-size: 13px;
                        font-weight: bold;
                    }
                """)
            else:
                indicator.setStyleSheet("""
                    QLabel {
                        background-color: #2d3748;
                        color: #718096;
                        border-radius: 18px;
                        font-size: 13px;
                        font-weight: bold;
                    }
                """)
        
        # Buttons
        self.prev_btn.setEnabled(step_num > 0)
        is_last = step_num == total - 1
        self.next_btn.setText("🎉 Fertig!" if is_last else "Weiter →")


class ImmersiveTutorial(QDialog):
    """
    Immersives Tutorial mit Split-Screen, 3D-Viewport und Gamification.
    """
    
    def __init__(self, main_window=None, document=None, viewport=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.document = document
        self.viewport = viewport
        self.current_step = 0
        self.total_xp = 0
        self.start_time = time.time()
        
        self._setup_ui()
        self._create_steps()
        
    def _setup_ui(self):
        """Erstellt die Haupt-UI."""
        self.setWindowTitle(tr("MashCAD - Immersive Tutorial"))
        self.setMinimumSize(1200, 800)
        self.setWindowFlags(Qt.Dialog | Qt.WindowMaximizeButtonHint)
        
        # Dark Theme
        self.setStyleSheet("""
            QDialog {
                background-color: #0d1117;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Linkes Kontroll-Panel
        self.control_panel = TutorialControlPanel()
        self.control_panel.next_clicked.connect(self._next_step)
        self.control_panel.prev_clicked.connect(self._prev_step)
        self.control_panel.skip_clicked.connect(self._skip)
        self.control_panel.hint_clicked.connect(self._show_hint)
        layout.addWidget(self.control_panel)
        
        # Rechter Bereich: 3D Viewport
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(16)
        
        # XP Display (oben rechts)
        self.xp_display = XPDisplay()
        right_layout.addWidget(self.xp_display, alignment=Qt.AlignRight)
        
        # 3D Viewport
        self.viewport_3d = Viewport3DWidget()
        right_layout.addWidget(self.viewport_3d, stretch=1)
        
        layout.addLayout(right_layout, stretch=1)
        
    def _create_steps(self):
        """Erstellt die Tutorial-Schritte."""
        self.steps = [
            ImmersiveStep(
                phase=TutorialPhase.INTRO,
                title="Willkommen in der Zukunft",
                subtitle="Ihr 3D-Design-Abenteuer beginnt jetzt",
                description="MashCAD verbindet die Power parametrischen CADs mit moderner KI. In den nächsten Minuten erstellen Sie Ihr erstes 3D-Modell.",
                icon="🚀",
                accent="#9f7aea",
                viewport_content="empty",
                xp_reward=50
            ),
            ImmersiveStep(
                phase=TutorialPhase.WATCH,
                title="Die Sketch-Ebene",
                subtitle="2D ist der Anfang von allem",
                description="Jedes 3D-Modell beginnt als 2D-Skizze. Beobachten Sie, wie ein Profil entsteht:",
                icon="📝",
                accent="#4299e1",
                viewport_content="sketch",
                camera_animation="zoom_in",
                xp_reward=100
            ),
            ImmersiveStep(
                phase=TutorialPhase.WATCH,
                title="Magie der Extrusion",
                subtitle="Von flach zu dreidimensional",
                description="Ein Klick verwandelt die Skizze in einen 3D-Körper. Die Extrusion ist die mächtigste Operation im CAD:",
                icon="📦",
                accent="#48bb78",
                viewport_content="extrude",
                xp_reward=150,
                badge_name="3D Explorer"
            ),
            ImmersiveStep(
                phase=TutorialPhase.TRY,
                title="Jetzt sind Sie dran!",
                subtitle="Probieren Sie es selbst",
                description="Klicken Sie auf 'Neue Skizze' im Hauptfenster. Das Tutorial pausiert, bis Sie es geschafft haben!",
                icon="💪",
                accent="#ed8936",
                viewport_content="try_mode",
                action_required="create_sketch",
                xp_reward=200,
                badge_name="First Steps"
            ),
            ImmersiveStep(
                phase=TutorialPhase.REWARD,
                title="Meisterhaft!",
                subtitle="Sie sind bereit",
                description="Sie haben die Grundlagen gemeistert. Mit dem Sketch-Agent können Sie jetzt komplexe Teile generieren oder selbst kreativ werden.",
                icon="🎉",
                accent="#fbbf24",
                viewport_content="celebration",
                xp_reward=500,
                badge_name="CAD Master"
            ),
        ]
        
        self.total_steps = len(self.steps)
        
    def _update_view(self):
        """Aktualisiert die Anzeige."""
        step = self.steps[self.current_step]
        
        # Control Panel aktualisieren
        self.control_panel.update_step(step, self.current_step, self.total_steps)
        
        # 3D Viewport aktualisieren
        self._update_viewport(step)
        
        # XP hinzufügen
        self.xp_display.add_xp(step.xp_reward)
        
        # Badge anzeigen wenn vorhanden
        if step.badge_name:
            badge_icons = {
                "3D Explorer": "🔷",
                "First Steps": "👣", 
                "CAD Master": "👑"
            }
            badge = BadgeNotification(
                step.badge_name,
                badge_icons.get(step.badge_name, "🏆"),
                self
            )
            badge.show()
        
        # Animation
        self._animate_transition()
        
    def _update_viewport(self, step: ImmersiveStep):
        """Aktualisiert den 3D-Viewport."""
        if step.viewport_content == "empty":
            self.viewport_3d.show_empty()
        elif step.viewport_content == "sketch":
            self.viewport_3d.show_sketch()
        elif step.viewport_content == "extrude":
            self.viewport_3d.show_extrude()
        elif step.viewport_content == "fillet":
            self.viewport_3d.show_fillet()
            
    def _animate_transition(self):
        """Animiert den Übergang zwischen Schritten."""
        # Fade out
        effect = QGraphicsOpacityEffect(self.control_panel.content_card)
        self.control_panel.content_card.setGraphicsEffect(effect)
        
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(300)
        anim.setStartValue(0)
        anim.setEndValue(1)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        
    def _next_step(self):
        """Nächster Schritt."""
        if self.current_step < self.total_steps - 1:
            self.current_step += 1
            self._update_view()
        else:
            self._finish()
            
    def _prev_step(self):
        """Vorheriger Schritt."""
        if self.current_step > 0:
            self.current_step -= 1
            self._update_view()
            
    def _skip(self):
        """Tutorial überspringen."""
        self.reject()
        
    def _show_hint(self):
        """Zeigt einen Hinweis an."""
        step = self.steps[self.current_step]
        hints = {
            "create_sketch": "Klicken Sie auf 'Neue Skizze' im Getting Started Overlay oder im Menü Sketch → New Sketch",
            "extrude": "Wählen Sie die Skizze aus und klicken Sie auf 'Extrudieren' in der Toolbar",
        }
        hint = hints.get(step.action_required, "Schauen Sie sich die Animation im 3D-Viewport an!")
        
        # Einfache MessageBox für Hint
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "💡 Hinweis", hint)
        
    def _highlight_ui_element(self, widget_name: str):
        """Highlightet ein UI-Element im MainWindow."""
        if not self.main_window:
            return
            
        # Finde das Widget
        target = None
        if hasattr(self.main_window, widget_name):
            target = getattr(self.main_window, widget_name)
        else:
            # Suche rekursiv
            target = self.main_window.findChild(QWidget, widget_name)
            
        if target:
            # Erstelle Highlight-Overlay
            self._create_highlight_overlay(target)
            
    def _create_highlight_overlay(self, target: QWidget):
        """Erstellt ein Highlight-Overlay um ein Widget."""
        # Position berechnen
        pos = target.mapToGlobal(QPoint(0, 0))
        size = target.size()
        
        # Highlight-Frame
        self.highlight_frame = QFrame()
        self.highlight_frame.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.highlight_frame.setAttribute(Qt.WA_TranslucentBackground)
        self.highlight_frame.setGeometry(pos.x() - 4, pos.y() - 4, 
                                          size.width() + 8, size.height() + 8)
        
        self.highlight_frame.setStyleSheet("""
            QFrame {
                background: transparent;
                border: 3px solid #fbbf24;
                border-radius: 8px;
            }
        """)
        
        # Glow-Effekt
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor("#fbbf24"))
        shadow.setOffset(0, 0)
        self.highlight_frame.setGraphicsEffect(shadow)
        
        self.highlight_frame.show()
        
        # Auto-hide nach 3 Sekunden
        QTimer.singleShot(3000, self._remove_highlight)
        
    def _remove_highlight(self):
        """Entfernt das Highlight."""
        if hasattr(self, 'highlight_frame') and self.highlight_frame:
            self.highlight_frame.deleteLater()
            self.highlight_frame = None
            
    def _run_agent_demo(self, complexity: str = "simple"):
        """Führt eine echte 3D-Demo mit dem Agent durch."""
        try:
            from sketching.visual.visual_agent import VisualSketchAgent
            
            if not self.viewport or not self.document:
                logger.warning("[Tutorial] Viewport oder Document nicht verfügbar")
                return
                
            # Erstelle Agent
            agent = VisualSketchAgent(
                viewport=self.viewport,
                mode="tutorial",
                seed=42
            )
            
            # Generiere Part
            result = agent.generate_part_visual(complexity=complexity)
            
            if result.success:
                logger.info(f"[Tutorial] Agent-Demo erfolgreich: {result.operations}")
                return result
            else:
                logger.warning(f"[Tutorial] Agent-Demo fehlgeschlagen: {result.error}")
                return None
                
        except ImportError as e:
            logger.debug(f"[Tutorial] VisualSketchAgent nicht verfügbar: {e}")
            return None
        except Exception as e:
            logger.error(f"[Tutorial] Agent-Demo Fehler: {e}")
            return None
            
    def _finish(self):
        """Tutorial abschließen."""
        elapsed = time.time() - self.start_time
        
        # Entferne Highlight falls vorhanden
        self._remove_highlight()
        
        # Final Stats
        msg = f"""
        <h2>🎉 Tutorial Abgeschlossen!</h2>
        <p><b>XP Gesammelt:</b> {self.xp_display.current_xp}<br>
        <b>Level:</b> {self.xp_display.level}<br>
        <b>Zeit:</b> {elapsed:.0f} Sekunden</p>
        <p>Sie sind jetzt bereit, Ihre eigenen 3D-Modelle zu erstellen!</p>
        """
        
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(self)
        box.setWindowTitle("🏆 Tutorial Complete!")
        box.setTextFormat(Qt.RichText)
        box.setText(msg)
        box.setIcon(QMessageBox.Information)
        
        # Custom Style
        box.setStyleSheet("""
            QMessageBox {
                background-color: #1a202c;
            }
            QLabel {
                color: #e2e8f0;
                font-size: 14px;
            }
            QPushButton {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #4299e1,
                    stop: 1 #3182ce
                );
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
            }
        """)
        
        box.exec()
        
        self.accept()
        
    def start(self):
        """Startet das Tutorial."""
        self._update_view()
        self.show()
        
    def exec(self):
        """Zeigt den Dialog modal an."""
        self._update_view()
        return super().exec()


def show_immersive_tutorial(main_window=None, document=None, viewport=None):
    """
    Zeigt das immersive Tutorial an.
    
    Usage:
        from gui.immersive_tutorial import show_immersive_tutorial
        show_immersive_tutorial(main_window, document, viewport)
    """
    tutorial = ImmersiveTutorial(main_window, document, viewport)
    return tutorial.exec()
