"""
MashCAD - True Immersive Tutorial Overlay
==========================================

Ein nicht-blockierendes, kontextuelles Tutorial-System:
- Overlay über der echten App
- Highlightet echte UI-Elemente
- Split-Screen: Anleitung links, echte App rechts
- Kein Modal-Dialog!

Usage:
    from gui.tutorial_overlay_system import TutorialOverlaySystem
    tutorial = TutorialOverlaySystem(main_window)
    tutorial.start()

Author: Kimi
Date: 2026-02-19
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QFrame, QGraphicsDropShadowEffect,
    QApplication, QGraphicsOpacityEffect, QSplitter,
    QMainWindow, QDockWidget, QToolBar, QMenuBar,
    QStatusBar, QSizePolicy
)
from PySide6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QSize, 
    QTimer, QPoint, QRect, Signal, QObject
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from loguru import logger
from typing import Optional, Callable, List
from dataclasses import dataclass
from enum import Enum, auto

from i18n import tr


@dataclass
class TutorialStep:
    """Ein kontextueller Tutorial-Schritt."""
    title: str
    description: str
    target_widget_name: Optional[str] = None  # z.B. "sketch_button"
    target_area: Optional[QRect] = None  # Alternative zu widget_name
    action_text: str = "Weiter"
    show_demo: bool = False


class SpotlightOverlay(QWidget):
    """
    Ein Overlay, das einen Bereich der App hervorhebt.
    Dunkler Hintergrund mit durchsichtigem Loch.
    """
    
    finished = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.target_rect = QRect()
        self.padding = 8
        self.info_widget = None
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Erstellt die UI."""
        self.setStyleSheet("background: transparent;")
        
        # Info-Widget für Beschreibung
        self.info_container = QFrame(self)
        self.info_container.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1a202c,
                    stop: 1 #0d1117
                );
                border: 2px solid #4299e1;
                border-radius: 16px;
            }
        """)
        
        info_layout = QVBoxLayout(self.info_container)
        info_layout.setContentsMargins(24, 20, 24, 20)
        info_layout.setSpacing(12)
        
        # Title
        self.title_label = QLabel()
        self.title_label.setStyleSheet("""
            color: #e2e8f0;
            font-size: 18px;
            font-weight: bold;
            background: transparent;
        """)
        info_layout.addWidget(self.title_label)
        
        # Description
        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("""
            color: #a0aec0;
            font-size: 13px;
            line-height: 1.5;
            background: transparent;
        """)
        info_layout.addWidget(self.desc_label)
        
        # Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
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
                padding: 10px 24px;
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
        self.next_btn.clicked.connect(self.finished.emit)
        btn_layout.addWidget(self.next_btn)
        
        info_layout.addLayout(btn_layout)
        
        # Initial hide
        self.info_container.hide()
        
    def set_target(self, rect: QRect, title: str = "", description: str = ""):
        """Setzt das zu highlightende Ziel."""
        self.target_rect = rect.adjusted(-self.padding, -self.padding, 
                                          self.padding, self.padding)
        self.title_label.setText(title)
        self.desc_label.setText(description)
        
        # Positioniere Info-Widget unter dem Target
        info_x = max(20, min(rect.center().x() - 150, self.width() - 340))
        info_y = min(rect.bottom() + 30, self.height() - 200)
        self.info_container.move(info_x, info_y)
        self.info_container.setFixedWidth(320)
        self.info_container.show()
        
        self.update()
        
    def paintEvent(self, event):
        """Zeichnet das Spotlight."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Dunkler Hintergrund (80% opacity)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 200))
        
        if self.target_rect.isValid():
            # Ausschnitt machen (transparent)
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(self.target_rect, Qt.transparent)
            
            # Zurück zur normalen Komposition
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            
            # Glow-Rahmen um das Target
            pen = QPen(QColor("#4299e1"), 3)
            painter.setPen(pen)
            painter.drawRoundedRect(self.target_rect, 8, 8)
            
            # Äußerer Glow
            glow_pen = QPen(QColor("#4299e1"), 6)
            glow_pen.setStyle(Qt.DotLine)
            painter.setPen(glow_pen)
            painter.drawRoundedRect(
                self.target_rect.adjusted(-4, -4, 4, 4), 10, 10
            )
        
        painter.end()
        
    def showEvent(self, event):
        """Fullscreen über Parent."""
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().showEvent(event)


class TutorialSidePanel(QFrame):
    """
    Ein Seiten-Panel, das neben der App angezeigt wird.
    Nicht blockierend, dockable.
    """
    
    next_clicked = Signal()
    prev_clicked = Signal()
    skip_clicked = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(320)
        self._setup_ui()
        
    def _setup_ui(self):
        self.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1a202c,
                    stop: 1 #0d1117
                );
                border-right: 1px solid #2d3748;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        # Header
        header = QHBoxLayout()
        
        logo = QLabel("🎓")
        logo.setStyleSheet("font-size: 24px; background: transparent;")
        header.addWidget(logo)
        
        title = QLabel("Tutorial")
        title.setStyleSheet("""
            color: #e2e8f0;
            font-size: 18px;
            font-weight: bold;
            background: transparent;
        """)
        header.addWidget(title)
        
        header.addStretch()
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #4a5568;
                color: #718096;
                border-radius: 6px;
            }
            QPushButton:hover {
                background: #2d3748;
                color: #e2e8f0;
            }
        """)
        close_btn.clicked.connect(self.skip_clicked.emit)
        header.addWidget(close_btn)
        
        layout.addLayout(header)
        
        # Progress
        self.progress_label = QLabel("Schritt 1 von 5")
        self.progress_label.setStyleSheet("color: #718096; font-size: 11px;")
        layout.addWidget(self.progress_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #2d3748;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #4299e1,
                    stop: 1 #48bb78
                );
                border-radius: 2px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # Content Card
        self.content_card = QFrame()
        self.content_card.setStyleSheet("""
            QFrame {
                background-color: #0f1419;
                border: 1px solid #2d3748;
                border-radius: 12px;
            }
        """)
        content_layout = QVBoxLayout(self.content_card)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(12)
        
        # Step number
        self.step_number = QLabel("1")
        self.step_number.setFixedSize(40, 40)
        self.step_number.setAlignment(Qt.AlignCenter)
        self.step_number.setStyleSheet("""
            QLabel {
                background-color: #4299e1;
                color: white;
                border-radius: 20px;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        content_layout.addWidget(self.step_number, alignment=Qt.AlignCenter)
        
        # Icon
        self.step_icon = QLabel("🚀")
        self.step_icon.setStyleSheet("font-size: 48px; background: transparent;")
        self.step_icon.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(self.step_icon)
        
        # Title
        self.step_title = QLabel("Willkommen")
        self.step_title.setStyleSheet("""
            color: #e2e8f0;
            font-size: 20px;
            font-weight: bold;
            background: transparent;
        """)
        self.step_title.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(self.step_title)
        
        # Description
        self.step_desc = QLabel("Beschreibung...")
        self.step_desc.setWordWrap(True)
        self.step_desc.setStyleSheet("""
            color: #a0aec0;
            font-size: 13px;
            line-height: 1.5;
            background: transparent;
        """)
        self.step_desc.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(self.step_desc)
        
        layout.addWidget(self.content_card, stretch=1)
        
        # Navigation
        nav_layout = QHBoxLayout()
        
        self.prev_btn = QPushButton("← Zurück")
        self.prev_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #4a5568;
                color: #a0aec0;
                padding: 10px 16px;
                border-radius: 6px;
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
                padding: 10px 24px;
                border-radius: 6px;
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
        
    def update_step(self, step: TutorialStep, step_num: int, total: int):
        """Aktualisiert den Inhalt."""
        self.progress_label.setText(f"Schritt {step_num} von {total}")
        self.progress_bar.setValue(int((step_num / total) * 100))
        
        self.step_number.setText(str(step_num))
        self.step_title.setText(step.title)
        self.step_desc.setText(step.description)
        self.next_btn.setText(step.action_text)
        
        # Icons je nach Schritt
        icons = ["🚀", "📝", "📦", "📐", "🎉"]
        self.step_icon.setText(icons[min(step_num - 1, len(icons) - 1)])
        
        self.prev_btn.setEnabled(step_num > 1)
        
        if step_num == total:
            self.next_btn.setText("🎉 Fertig!")
            self.next_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(
                        x1: 0, y1: 0, x2: 1, y2: 0,
                        stop: 0 #48bb78,
                        stop: 1 #38a169
                    );
                    border: none;
                    color: white;
                    padding: 10px 24px;
                    border-radius: 6px;
                    font-weight: bold;
                }
            """)


class TutorialOverlaySystem(QObject):
    """
    Kontextuelles Tutorial-System, das nicht blockiert.
    
    Nutzt echte UI-Elemente der App + Spotlight-Overlay.
    """
    
    def __init__(self, main_window: QMainWindow):
        super().__init__()
        self.main_window = main_window
        self.current_step = 0
        self.spotlight = None
        self.side_panel = None
        self.highlight_frame = None
        
        self._create_steps()
        
    def _create_steps(self):
        """Erstellt die Tutorial-Schritte."""
        self.steps = [
            TutorialStep(
                title="Willkommen bei MashCAD",
                description="Dieses Tutorial führt Sie durch die Grundlagen. Die App bleibt währenddessen nutzbar.",
                action_text="Los geht's!"
            ),
            TutorialStep(
                title="Erstellen Sie eine Skizze",
                description="Klicken Sie auf die 'Neue Skizze' Schaltfläche in der Werkzeugleiste.",
                target_widget_name="_getting_started_overlay",
                action_text="Ich habe geklickt"
            ),
            TutorialStep(
                title="Zeichnen Sie ein Rechteck",
                description="Im Sketch-Editor: Klicken Sie auf das Rechteck-Werkzeug und ziehen Sie ein Rechteck.",
                action_text="Weiter"
            ),
            TutorialStep(
                title="Extrudieren Sie zu 3D",
                description="Schließen Sie den Sketch und klicken Sie auf 'Extrudieren'.",
                action_text="Weiter"
            ),
            TutorialStep(
                title="Glückwunsch!",
                description="Sie haben Ihr erstes 3D-Modell erstellt. Entdecken Sie jetzt weitere Features!",
                action_text="Tutorial schließen"
            ),
        ]
        
    def start(self):
        """Startet das Tutorial."""
        # Side Panel erstellen
        self.side_panel = TutorialSidePanel()
        self.side_panel.next_clicked.connect(self._next_step)
        self.side_panel.prev_clicked.connect(self._prev_step)
        self.side_panel.skip_clicked.connect(self._finish)
        
        # Als Dock-Widget hinzufügen
        from PySide6.QtWidgets import QDockWidget
        
        self.dock = QDockWidget("Tutorial", self.main_window)
        self.dock.setWidget(self.side_panel)
        self.dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.dock.setTitleBarWidget(QWidget())  # Kein Title Bar
        self.dock.setFixedWidth(340)
        
        # Links docken
        self.main_window.addDockWidget(Qt.LeftDockWidgetArea, self.dock)
        
        # Ersten Schritt anzeigen
        self._update_view()
        
    def _next_step(self):
        """Nächster Schritt."""
        if self.current_step < len(self.steps) - 1:
            self.current_step += 1
            self._update_view()
        else:
            self._finish()
            
    def _prev_step(self):
        """Vorheriger Schritt."""
        if self.current_step > 0:
            self.current_step -= 1
            self._update_view()
            
    def _update_view(self):
        """Aktualisiert die Anzeige."""
        step = self.steps[self.current_step]
        
        # Side Panel aktualisieren
        self.side_panel.update_step(step, self.current_step + 1, len(self.steps))
        
        # Spotlight für Target
        if step.target_widget_name:
            self._highlight_widget(step.target_widget_name)
        else:
            self._clear_highlight()
            
    def _highlight_widget(self, widget_name: str):
        """Highlightet ein Widget in der Haupt-App."""
        # Altes Highlight entfernen
        self._clear_highlight()
        
        # Widget finden
        target = None
        if hasattr(self.main_window, widget_name):
            target = getattr(self.main_window, widget_name)
        else:
            target = self.main_window.findChild(QWidget, widget_name)
            
        if target and target.isVisible():
            # Position berechnen
            global_pos = target.mapToGlobal(QPoint(0, 0))
            parent_pos = self.main_window.mapFromGlobal(global_pos)
            rect = QRect(parent_pos, target.size())
            
            # Spotlight Overlay
            self.spotlight = SpotlightOverlay(self.main_window)
            self.spotlight.set_target(
                rect,
                self.steps[self.current_step].title,
                self.steps[self.current_step].description
            )
            self.spotlight.finished.connect(self._next_step)
            self.spotlight.show()
            
    def _clear_highlight(self):
        """Entfernt das Highlight."""
        if self.spotlight:
            self.spotlight.close()
            self.spotlight.deleteLater()
            self.spotlight = None
            
    def _finish(self):
        """Beendet das Tutorial."""
        self._clear_highlight()
        
        if hasattr(self, 'dock'):
            self.main_window.removeDockWidget(self.dock)
            self.dock.deleteLater()
            
        logger.info("Tutorial beendet")


def start_contextual_tutorial(main_window):
    """
    Startet das kontextuelle Tutorial.
    
    Usage:
        from gui.tutorial_overlay_system import start_contextual_tutorial
        start_contextual_tutorial(main_window)
    """
    tutorial = TutorialOverlaySystem(main_window)
    tutorial.start()
    return tutorial
