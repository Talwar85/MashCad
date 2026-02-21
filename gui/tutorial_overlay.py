"""
MashCAD - Tutorial Overlay System
==================================

Phase 2: UX-001 - Interactive Tutorial System

Bietet interaktive Tutorials mit:
- Highlighting von UI-Elementen
- Schritt-für-Schritt Anleitungen
- Tooltips und Erklärungen
- Fortschritts-Tracking

Usage:
    from gui.tutorial_overlay import TutorialOverlay, TutorialStep
    
    tutorial = TutorialOverlay(main_window)
    tutorial.add_step(TutorialStep(
        target_widget=sketch_button,
        title="Sketch erstellen",
        text="Klicken Sie hier um eine neue Skizze zu erstellen.",
        position="bottom"
    ))
    tutorial.start()

Author: Kimi (UX-001 Implementation)
Date: 2026-02-19
Branch: feature/v1-ux-aiB
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QFrame, QGraphicsDropShadowEffect,
    QApplication, QToolTip
)
from PySide6.QtCore import Qt, QRect, QPoint, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QPolygon
from loguru import logger
from typing import List, Optional, Callable
from dataclasses import dataclass

from i18n import tr


@dataclass
class TutorialStep:
    """
    Ein Schritt im Tutorial.
    
    Attributes:
        target_widget: Widget das hervorgehoben werden soll (None für allgemeine Info)
        title: Titel des Schritts
        text: Erklärender Text
        position: Position des Tooltips ("top", "bottom", "left", "right", "center")
        action_text: Text für die Action-Button (default: "Weiter")
        can_skip: Ob dieser Schritt übersprungen werden kann
        validate: Optional Callback zur Validierung (muss True zurückgeben)
    """
    target_widget: Optional[QWidget]
    title: str
    text: str
    position: str = "bottom"
    action_text: str = "Weiter →"
    can_skip: bool = True
    validate: Optional[Callable] = None


class HighlightWidget(QFrame):
    """Widget zur Hervorhebung eines Ziel-Widgets."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.target_rect = QRect()
        self.padding = 8
        
    def set_target(self, widget: QWidget):
        """Setzt das Ziel-Widget für die Hervorhebung."""
        if widget:
            # Position relativ zum Parent
            pos = widget.mapTo(self.parent(), QPoint(0, 0))
            self.target_rect = QRect(pos, widget.size())
            self.target_rect.adjust(-self.padding, -self.padding, 
                                   self.padding, self.padding)
        else:
            self.target_rect = QRect()
        self.update()
        
    def paintEvent(self, event):
        """Zeichnet den Highlight-Rahmen."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Halbtransparenter Hintergrund
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        
        if self.target_rect.isValid():
            # Ausschnitt für das Ziel-Widget (transparent)
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(self.target_rect, Qt.transparent)
            
            # Zurück zur normalen Komposition
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            
            # Rahmen um das Ziel
            pen = QPen(QColor("#2196F3"), 3)
            painter.setPen(pen)
            painter.drawRoundedRect(self.target_rect, 8, 8)
            
            # Glow-Effekt
            glow_pen = QPen(QColor("#2196F3"), 8)
            glow_pen.setStyle(Qt.DotLine)
            painter.setPen(glow_pen)
            glow_rect = self.target_rect.adjusted(-4, -4, 4, 4)
            painter.drawRoundedRect(glow_rect, 10, 10)
        
        painter.end()


class TutorialTooltip(QFrame):
    """Tooltip-Widget für Tutorial-Schritte."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Shadow-Effekt
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
        
        # Styling
        self.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 12px;
                border: 2px solid #2196F3;
            }
            QLabel {
                background: transparent;
            }
        """)
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Erstellt die UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Titel
        self.title_label = QLabel()
        self.title_label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #2196F3;
        """)
        layout.addWidget(self.title_label)
        
        # Text
        self.text_label = QLabel()
        self.text_label.setWordWrap(True)
        self.text_label.setMinimumWidth(250)
        self.text_label.setStyleSheet("font-size: 13px; color: #333;")
        layout.addWidget(self.text_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.skip_btn = QPushButton(tr("Überspringen"))
        self.skip_btn.setFlat(True)
        self.skip_btn.setStyleSheet("color: #999;")
        btn_layout.addWidget(self.skip_btn)
        
        btn_layout.addStretch()
        
        self.back_btn = QPushButton(tr("← Zurück"))
        btn_layout.addWidget(self.back_btn)
        
        self.next_btn = QPushButton()
        self.next_btn.setObjectName("primary")
        self.next_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        btn_layout.addWidget(self.next_btn)
        
        layout.addLayout(btn_layout)
        
        # Progress
        self.progress_label = QLabel()
        self.progress_label.setStyleSheet("color: #999; font-size: 11px;")
        self.progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_label)
        
    def set_content(self, step: TutorialStep, step_num: int, total_steps: int):
        """Setzt den Content für einen Schritt."""
        self.title_label.setText(step.title)
        self.text_label.setText(step.text)
        self.next_btn.setText(step.action_text)
        self.skip_btn.setVisible(step.can_skip)
        self.progress_label.setText(tr(f"Schritt {step_num} von {total_steps}"))
        
        # Mindestgröße anpassen
        self.adjustSize()
        
    def position_at(self, target_rect: QRect, position: str):
        """Positioniert den Tooltip relativ zum Ziel."""
        margin = 15
        
        if position == "bottom":
            x = target_rect.center().x() - self.width() // 2
            y = target_rect.bottom() + margin
        elif position == "top":
            x = target_rect.center().x() - self.width() // 2
            y = target_rect.top() - self.height() - margin
        elif position == "right":
            x = target_rect.right() + margin
            y = target_rect.center().y() - self.height() // 2
        elif position == "left":
            x = target_rect.left() - self.width() - margin
            y = target_rect.center().y() - self.height() // 2
        else:  # center
            x = target_rect.center().x() - self.width() // 2
            y = target_rect.center().y() - self.height() // 2
        
        # Bildschirmgrenzen prüfen
        screen = QApplication.primaryScreen().geometry()
        x = max(10, min(x, screen.width() - self.width() - 10))
        y = max(10, min(y, screen.height() - self.height() - 10))
        
        self.move(x, y)


class TutorialOverlay(QWidget):
    """
    Tutorial Overlay für interaktive Anleitungen.
    
    Bietet:
    - Step-by-step Tutorials
    - Widget-Highlighting
    - Tooltips mit Erklärungen
    - Fortschritts-Tracking
    """
    
    def __init__(self, parent=None):
        """
        Args:
            parent: Parent Widget (normalerweise MainWindow)
        """
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.steps: List[TutorialStep] = []
        self.current_step = 0
        self.is_running = False
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Erstellt die UI."""
        self.resize(self.parent().size() if self.parent() else QSize(800, 600))
        
        # Highlight-Widget
        self.highlight = HighlightWidget(self)
        self.highlight.resize(self.size())
        
        # Tooltip
        self.tooltip = TutorialTooltip(self)
        
        # Button-Connections
        self.tooltip.next_btn.clicked.connect(self._next_step)
        self.tooltip.back_btn.clicked.connect(self._prev_step)
        self.tooltip.skip_btn.clicked.connect(self._skip_tutorial)
        
    def add_step(self, step: TutorialStep):
        """Fügt einen Schritt zum Tutorial hinzu."""
        self.steps.append(step)
        
    def add_steps(self, steps: List[TutorialStep]):
        """Fügt mehrere Schritte hinzu."""
        self.steps.extend(steps)
        
    def start(self):
        """Startet das Tutorial."""
        if not self.steps:
            logger.warning("Cannot start tutorial: no steps defined")
            return
            
        self.current_step = 0
        self.is_running = True
        self.show()
        self.highlight.show()
        self.tooltip.show()
        
        self._show_current_step()
        logger.info(f"Tutorial started with {len(self.steps)} steps")
        
    def stop(self):
        """Stoppt das Tutorial."""
        self.is_running = False
        self.hide()
        self.highlight.hide()
        self.tooltip.hide()
        logger.info("Tutorial stopped")
        
    def _show_current_step(self):
        """Zeigt den aktuellen Schritt an."""
        if not (0 <= self.current_step < len(self.steps)):
            self._finish_tutorial()
            return
            
        step = self.steps[self.current_step]
        
        # Highlight aktualisieren
        if step.target_widget:
            self.highlight.set_target(step.target_widget)
            self.highlight.show()
            
            # Tooltip positionieren
            target_rect = step.target_widget.geometry()
            target_rect.moveTo(
                step.target_widget.mapTo(self, QPoint(0, 0))
            )
            self.tooltip.position_at(target_rect, step.position)
        else:
            self.highlight.hide()
            # Zentrieren
            self.tooltip.move(
                (self.width() - self.tooltip.width()) // 2,
                (self.height() - self.tooltip.height()) // 2
            )
        
        # Content setzen
        self.tooltip.set_content(step, self.current_step + 1, len(self.steps))
        
        # Button-States
        self.tooltip.back_btn.setEnabled(self.current_step > 0)
        
        # Animation
        self._animate_tooltip_in()
        
    def _animate_tooltip_in(self):
        """Animiert den Tooltip-Einblendung."""
        anim = QPropertyAnimation(self.tooltip, b"windowOpacity")
        anim.setDuration(200)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        
    def _next_step(self):
        """Geht zum nächsten Schritt."""
        step = self.steps[self.current_step]
        
        # Validierung
        if step.validate and not step.validate():
            return
        
        self.current_step += 1
        self._show_current_step()
        
    def _prev_step(self):
        """Geht zum vorherigen Schritt."""
        if self.current_step > 0:
            self.current_step -= 1
            self._show_current_step()
            
    def _skip_tutorial(self):
        """Überspringt das Tutorial."""
        reply = QMessageBox.question(
            self,
            tr("Tutorial überspringen"),
            tr("Möchten Sie das Tutorial wirklich überspringen?"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.stop()
            
    def _finish_tutorial(self):
        """Beendet das Tutorial erfolgreich."""
        from PySide6.QtWidgets import QMessageBox
        
        QMessageBox.information(
            self,
            tr("Tutorial abgeschlossen! 🎉"),
            tr("Sie haben das Tutorial erfolgreich abgeschlossen!")
        )
        
        self.stop()
        
    def resizeEvent(self, event):
        """Behandelt Größenänderungen."""
        super().resizeEvent(event)
        self.highlight.resize(self.size())
        if self.is_running:
            self._show_current_step()
            
    def keyPressEvent(self, event):
        """Behandelt Tastendrücke."""
        if event.key() == Qt.Key_Escape:
            self._skip_tutorial()
        elif event.key() == Qt.Key_Right or event.key() == Qt.Key_Space:
            self._next_step()
        elif event.key() == Qt.Key_Left:
            self._prev_step()
        else:
            super().keyPressEvent(event)


def create_basic_sketch_tutorial(main_window) -> TutorialOverlay:
    """
    Erstellt ein Basis-Tutorial für das Erstellen eines Sketches.
    
    Args:
        main_window: Das MainWindow
        
    Returns:
        TutorialOverlay mit konfiguriertem Tutorial
    """
    tutorial = TutorialOverlay(main_window)
    
    # Schritt 1: Sketch-Button
    if hasattr(main_window, 'sketch_btn'):
        tutorial.add_step(TutorialStep(
            target_widget=main_window.sketch_btn,
            title=tr("Skizze erstellen"),
            text=tr("Klicken Sie hier um eine neue Skizze zu erstellen. "
                   "Wählen Sie dann die XY-Ebene."),
            position="bottom"
        ))
    
    # Schritt 2: Rechteck-Werkzeug
    if hasattr(main_window, 'rect_tool_btn'):
        tutorial.add_step(TutorialStep(
            target_widget=main_window.rect_tool_btn,
            title=tr("Rechteck zeichnen"),
            text=tr("Wählen Sie das Rechteck-Werkzeug und ziehen Sie "
                   "ein Rechteck auf der Arbeitsfläche."),
            position="right"
        ))
    
    # Schritt 3: Bemaßung
    if hasattr(main_window, 'dimension_tool_btn'):
        tutorial.add_step(TutorialStep(
            target_widget=main_window.dimension_tool_btn,
            title=tr("Bemaßen"),
            text=tr("Wählen Sie das Bemaßungs-Werkzeug und klicken Sie "
                   "auf eine Linie um ihre Länge festzulegen."),
            position="right"
        ))
    
    # Schritt 4: Fertig stellen
    tutorial.add_step(TutorialStep(
        target_widget=None,
        title=tr("Sketch fertigstellen"),
        text=tr("Drücken Sie 'Fertig stellen' oder Escape um den Sketch-Editor zu schließen "
               "und zurück zur 3D-Ansicht zu gelangen."),
        position="center",
        action_text=tr("Fertig 🎉")
    ))
    
    return tutorial


# Import QMessageBox für _skip_tutorial
from PySide6.QtWidgets import QMessageBox
