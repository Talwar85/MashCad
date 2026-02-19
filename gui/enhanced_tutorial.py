"""
MashCAD - Enhanced Interactive Tutorial
=======================================

Visuell ansprechender Tutorial-Modus mit:
- Dunklem Theme (passend zur App)
- Live-Demos via VisualSketchAgent
- Animationen und visuellen Effekten
- Interaktiven Elementen statt nur Text
- Screenshot-ähnlichen Vorschauen

Usage:
    from gui.enhanced_tutorial import EnhancedTutorial
    tutorial = EnhancedTutorial(main_window)
    tutorial.start()

Author: Kimi
Date: 2026-02-19
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QStackedWidget, QWidget, QProgressBar,
    QFrame, QGraphicsDropShadowEffect, QApplication,
    QGraphicsOpacityEffect, QSplitter, QTextEdit
)
from PySide6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QSize, 
    QTimer, QParallelAnimationGroup, QPoint
)
from PySide6.QtGui import QColor, QFont, QPixmap, QPainter, QBrush, QLinearGradient
from loguru import logger
from typing import Optional, Callable, List
from dataclasses import dataclass
from enum import Enum

from gui.design_tokens import DesignTokens
from i18n import tr


class TutorialStepType(Enum):
    """Typ eines Tutorial-Schritts."""
    INFO = "info"           # Nur Information
    DEMO = "demo"           # Live-Demo mit Agent
    INTERACTIVE = "interactive"  # Benutzer muss etwas tun
    PREVIEW = "preview"     # Zeigt Vorschau/Screenshot


@dataclass
class TutorialStep:
    """Ein Schritt im Tutorial."""
    step_type: TutorialStepType
    title: str
    subtitle: str
    description: str
    icon: str  # Emoji oder Symbol
    accent_color: str  # Hex-Farbe
    demo_action: Optional[Callable] = None  # Für DEMO-Typ
    validation: Optional[Callable] = None   # Für INTERACTIVE-Typ
    preview_widget: Optional[QWidget] = None  # Für PREVIEW-Typ


class VisualDemoWidget(QFrame):
    """Widget für Live-Demo-Vorschau mit animierten Elementen."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(400, 300)
        self.setStyleSheet("""
            QFrame {
                background-color: #1a1d29;
                border: 2px solid #2d3748;
                border-radius: 12px;
            }
        """)
        
        # Demo-Elemente
        self._setup_demo_elements()
        
    def _setup_demo_elements(self):
        """Erstellt die Demo-UI-Elemente."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Toolbar Simulation
        toolbar = QFrame()
        toolbar.setFixedHeight(40)
        toolbar.setStyleSheet("""
            QFrame {
                background-color: #2d3748;
                border-radius: 6px;
            }
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setSpacing(8)
        toolbar_layout.setContentsMargins(10, 5, 10, 5)
        
        # Toolbar Buttons
        for icon, tooltip in [("📝", "Sketch"), ("📦", "Extrude"), ("🔧", "Fillet")]:
            btn = QLabel(icon)
            btn.setStyleSheet("font-size: 16px;")
            toolbar_layout.addWidget(btn)
        
        toolbar_layout.addStretch()
        layout.addWidget(toolbar)
        
        # Viewport Simulation
        self.viewport = QFrame()
        self.viewport.setStyleSheet("""
            QFrame {
                background: qradialgradient(
                    cx: 0.5, cy: 0.5, radius: 0.8,
                    stop: 0 #2d3748,
                    stop: 1 #1a1d29
                );
                border-radius: 8px;
                border: 1px solid #3d4758;
            }
        """)
        viewport_layout = QVBoxLayout(self.viewport)
        
        # Grid pattern overlay
        self.grid_label = QLabel()
        self.grid_label.setStyleSheet("""
            background: transparent;
            border: none;
        """)
        viewport_layout.addWidget(self.grid_label)
        
        layout.addWidget(self.viewport, stretch=1)
        
        # Status Bar
        self.status = QLabel(tr("Bereit..."))
        self.status.setStyleSheet("""
            color: #718096;
            font-size: 11px;
            padding: 5px;
        """)
        layout.addWidget(self.status)
        
    def animate_sketch_creation(self):
        """Animiert die Sketch-Erstellung."""
        self.status.setText(tr("📝 Erstelle Sketch..."))
        self.status.setStyleSheet("color: #4299e1; font-size: 11px;")
        
        # Simulierte Animation
        self._animate_element("sketch")
        
    def animate_extrude(self):
        """Animiert die Extrusion."""
        self.status.setText(tr("📦 Extrudiere..."))
        self.status.setStyleSheet("color: #48bb78; font-size: 11px;")
        self._animate_element("extrude")
        
    def animate_complete(self):
        """Zeigt fertiges Ergebnis."""
        self.status.setText(tr("✅ Fertig!"))
        self.status.setStyleSheet("color: #48bb78; font-size: 11px; font-weight: bold;")
        
    def _animate_element(self, element_type: str):
        """Interne Animations-Logik."""
        # Hier könnte echte OpenGL-Visualisierung sein
        # Aktuell: CSS-basierte Simulation
        pass


class TutorialCard(QFrame):
    """Eine Tutorial-Karte mit animierten Übergängen."""
    
    def __init__(self, step: TutorialStep, parent=None):
        super().__init__(parent)
        self.step = step
        self._setup_ui()
        self._apply_styling()
        
    def _setup_ui(self):
        """Erstellt die UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)
        
        # Icon mit Glow-Effekt
        icon_frame = QFrame()
        icon_frame.setFixedSize(80, 80)
        icon_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {self.step.accent_color}20;
                border: 2px solid {self.step.accent_color};
                border-radius: 40px;
            }}
        """)
        icon_layout = QVBoxLayout(icon_frame)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        
        icon_label = QLabel(self.step.icon)
        icon_label.setStyleSheet(f"""
            font-size: 36px;
            background: transparent;
        """)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_layout.addWidget(icon_label)
        
        # Glow-Effekt
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(self.step.accent_color))
        shadow.setOffset(0, 0)
        icon_frame.setGraphicsEffect(shadow)
        
        layout.addWidget(icon_frame, alignment=Qt.AlignCenter)
        
        # Titel
        title = QLabel(self.step.title)
        title.setStyleSheet("""
            font-size: 28px;
            font-weight: bold;
            color: #e2e8f0;
            background: transparent;
        """)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Subtitle
        subtitle = QLabel(self.step.subtitle)
        subtitle.setStyleSheet(f"""
            font-size: 14px;
            color: {self.step.accent_color};
            font-weight: 600;
            background: transparent;
        """)
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        
        # Beschreibung
        desc = QLabel(self.step.description)
        desc.setWordWrap(True)
        desc.setStyleSheet("""
            font-size: 13px;
            color: #a0aec0;
            line-height: 1.6;
            background: transparent;
            padding: 10px 20px;
        """)
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)
        
        # Demo/Preview Bereich (falls vorhanden)
        if self.step.step_type == TutorialStepType.DEMO:
            self.demo_widget = VisualDemoWidget()
            layout.addWidget(self.demo_widget, alignment=Qt.AlignCenter)
        elif self.step.preview_widget:
            layout.addWidget(self.step.preview_widget, alignment=Qt.AlignCenter)
            
        layout.addStretch()
        
    def _apply_styling(self):
        """Wendet das Dark Theme Styling an."""
        self.setStyleSheet("""
            TutorialCard {
                background-color: #1a202c;
                border: 1px solid #2d3748;
                border-radius: 16px;
            }
        """)
        
        # Fade-In Animation
        self.opacity_effect = QGraphicsOpacityEffect()
        self.opacity_effect.setOpacity(0)
        self.setGraphicsEffect(self.opacity_effect)
        
        self.fade_in = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_in.setDuration(400)
        self.fade_in.setStartValue(0)
        self.fade_in.setEndValue(1)
        self.fade_in.setEasingCurve(QEasingCurve.OutCubic)
        
    def play_animation(self):
        """Spielt die Eintrittsanimation ab."""
        self.fade_in.start()
        
        # Demo-Animation starten wenn vorhanden
        if hasattr(self, 'demo_widget') and self.step.demo_action:
            QTimer.singleShot(500, self.step.demo_action)


class EnhancedTutorial(QDialog):
    """
    Verbesserter Tutorial-Dialog mit visuellen Effekten und Live-Demos.
    """
    
    def __init__(self, main_window=None, document=None, viewport=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.document = document
        self.viewport = viewport
        self.current_step = 0
        self.total_steps = 0
        
        self._setup_ui()
        self._create_steps()
        
    def _setup_ui(self):
        """Erstellt die Haupt-UI."""
        self.setWindowTitle(tr("MashCAD Tutorial"))
        self.setMinimumSize(900, 700)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint)
        
        # Dark Theme
        self.setStyleSheet("""
            QDialog {
                background-color: #0f1419;
            }
            QLabel {
                background: transparent;
            }
        """)
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Linke Seite: Navigation & Fortschritt
        left_panel = self._create_left_panel()
        main_layout.addWidget(left_panel, 1)
        
        # Rechte Seite: Content
        right_panel = self._create_right_panel()
        main_layout.addWidget(right_panel, 3)
        
    def _create_left_panel(self) -> QWidget:
        """Erstellt das linke Navigations-Panel."""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #1a202c;
                border-right: 1px solid #2d3748;
            }
        """)
        panel.setFixedWidth(260)
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        
        # Logo/Titel
        title = QLabel("🎓 MashCAD")
        title.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: #e2e8f0;
        """)
        layout.addWidget(title)
        
        subtitle = QLabel(tr("Interactive Tutorial"))
        subtitle.setStyleSheet("color: #718096; font-size: 12px;")
        layout.addWidget(subtitle)
        
        # Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #2d3748;")
        layout.addWidget(sep)
        
        # Fortschritts-Label
        self.progress_label = QLabel(tr("Schritt 1 von 5"))
        self.progress_label.setStyleSheet("color: #a0aec0; font-size: 12px;")
        layout.addWidget(self.progress_label)
        
        # Fortschritts-Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #2d3748;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #4299e1,
                    stop: 1 #48bb78
                );
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # Schritt-Liste
        layout.addSpacing(20)
        self.step_list = QVBoxLayout()
        self.step_list.setSpacing(8)
        layout.addLayout(self.step_list)
        
        layout.addStretch()
        
        # Skip Button
        skip_btn = QPushButton(tr("Tutorial überspringen →"))
        skip_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #4a5568;
                color: #718096;
                padding: 10px 16px;
                border-radius: 8px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2d3748;
                color: #a0aec0;
            }
        """)
        skip_btn.clicked.connect(self.reject)
        layout.addWidget(skip_btn)
        
        return panel
        
    def _create_right_panel(self) -> QWidget:
        """Erstellt das rechte Content-Panel."""
        panel = QFrame()
        panel.setStyleSheet("background-color: #0f1419;")
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        # Stacked Widget für die Schritte
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, stretch=1)
        
        # Navigation Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)
        
        self.back_btn = QPushButton(tr("← Zurück"))
        self.back_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #4a5568;
                color: #a0aec0;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #2d3748;
            }
            QPushButton:disabled {
                color: #4a5568;
                border-color: #2d3748;
            }
        """)
        self.back_btn.clicked.connect(self._go_back)
        btn_layout.addWidget(self.back_btn)
        
        btn_layout.addStretch()
        
        self.next_btn = QPushButton(tr("Weiter →"))
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
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #3182ce,
                    stop: 1 #2c5282
                );
            }
        """)
        self.next_btn.clicked.connect(self._go_next)
        btn_layout.addWidget(self.next_btn)
        
        self.finish_btn = QPushButton(tr("🎉 Fertig!"))
        self.finish_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #48bb78,
                    stop: 1 #38a169
                );
                border: none;
                color: white;
                padding: 12px 32px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #38a169,
                    stop: 1 #2f855a
                );
            }
        """)
        self.finish_btn.clicked.connect(self._finish)
        self.finish_btn.hide()
        btn_layout.addWidget(self.finish_btn)
        
        layout.addLayout(btn_layout)
        
        return panel
        
    def _create_steps(self):
        """Erstellt alle Tutorial-Schritte."""
        steps = [
            TutorialStep(
                step_type=TutorialStepType.INFO,
                title=tr("Willkommen bei MashCAD"),
                subtitle=tr("Ihr parametrischer 3D-CAD-Designer"),
                description=tr(
                    "In den nächsten Minuten lernen Sie die Grundlagen kennen: "
                    "Skizzen erstellen, 3D-Körper extrudieren und für den 3D-Druck exportieren."
                ),
                icon="🚀",
                accent_color="#4299e1"
            ),
            TutorialStep(
                step_type=TutorialStepType.DEMO,
                title=tr("Erste Skizze"),
                subtitle=tr("Jedes 3D-Modell beginnt mit 2D"),
                description=tr(
                    "Sehen Sie, wie einfach es ist, eine parametrische Skizze zu erstellen. "
                    "Verwenden Sie Constraints für präzise geometrische Beziehungen."
                ),
                icon="📝",
                accent_color="#9f7aea",
                demo_action=self._demo_sketch_creation
            ),
            TutorialStep(
                step_type=TutorialStepType.DEMO,
                title=tr("Von 2D zu 3D"),
                subtitle=tr("Extrusion & Features"),
                description=tr(
                    "Wandeln Sie Ihre Skizze mit einem Klick in einen 3D-Körper um. "
                    "Fügen Sie anschließend Features wie Bohrungen oder Abrundungen hinzu."
                ),
                icon="📦",
                accent_color="#48bb78",
                demo_action=self._demo_extrude
            ),
            TutorialStep(
                step_type=TutorialStepType.PREVIEW,
                title=tr("Bemaßung & Constraints"),
                subtitle=tr("Parametrisches Design"),
                description=tr(
                    "Ändern Sie Maße jederzeit - das Modell passt sich automatisch an. "
                    "Nutzen Sie Constraints für intelligente geometrische Beziehungen."
                ),
                icon="📐",
                accent_color="#ed8936"
            ),
            TutorialStep(
                step_type=TutorialStepType.INFO,
                title=tr("Bereit zum Start!"),
                subtitle=tr("Sie haben die Grundlagen gelernt"),
                description=tr(
                    "Sie können jetzt Ihre eigenen 3D-Modelle erstellen. "
                    "Nutzen Sie den Sketch-Agent für Inspiration oder starten Sie selbst."
                ),
                icon="🎉",
                accent_color="#38b2ac"
            ),
        ]
        
        self.total_steps = len(steps)
        
        for i, step in enumerate(steps):
            card = TutorialCard(step)
            self.stack.addWidget(card)
            self._add_step_indicator(i, step)
            
    def _add_step_indicator(self, index: int, step: TutorialStep):
        """Fügt einen Schritt-Indikator zum linken Panel hinzu."""
        indicator = QFrame()
        indicator.setFixedHeight(40)
        
        layout = QHBoxLayout(indicator)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)
        
        # Nummer oder Icon
        num_label = QLabel(step.icon)
        num_label.setStyleSheet(f"""
            font-size: 16px;
            background: transparent;
        """)
        layout.addWidget(num_label)
        
        # Titel
        title = QLabel(step.title)
        title.setStyleSheet("""
            color: #718096;
            font-size: 13px;
            background: transparent;
        """)
        layout.addWidget(title, stretch=1)
        
        # Status-Indikator
        status = QLabel("○")
        status.setObjectName(f"step_status_{index}")
        status.setStyleSheet(f"""
            color: {step.accent_color};
            font-size: 12px;
            background: transparent;
        """)
        layout.addWidget(status)
        
        self.step_list.addWidget(indicator)
        
    def _demo_sketch_creation(self):
        """Demo: Skizze erstellen (simuliert oder mit Agent)."""
        current_widget = self.stack.currentWidget()
        if hasattr(current_widget, 'demo_widget'):
            demo = current_widget.demo_widget
            demo.animate_sketch_creation()
            
            # Wenn Agent verfügbar, echte Demo im Viewport
            if self.main_window and hasattr(self.main_window, '_run_agent_demo'):
                QTimer.singleShot(1000, self._run_sketch_demo_with_agent)
            
    def _demo_extrude(self):
        """Demo: Extrudieren (simuliert)."""
        current_widget = self.stack.currentWidget()
        if hasattr(current_widget, 'demo_widget'):
            current_widget.demo_widget.animate_extrude()
            
    def _run_sketch_demo_with_agent(self):
        """Führt eine echte Demo mit dem Sketch Agent durch."""
        try:
            from sketching.visual.visual_agent import VisualSketchAgent
            
            if not self.viewport or not self.document:
                return
                
            agent = VisualSketchAgent(
                viewport=self.viewport,
                mode="tutorial",
                seed=42
            )
            
            # Einfache Demo-Skizze erstellen
            result = agent.generate_part_visual(complexity="simple")
            
            if result.success:
                logger.info("[Tutorial] Agent-Demo erfolgreich")
            else:
                logger.warning(f"[Tutorial] Agent-Demo fehlgeschlagen: {result.error}")
                
        except ImportError:
            logger.debug("[Tutorial] VisualSketchAgent nicht verfügbar")
        except Exception as e:
            logger.error(f"[Tutorial] Agent-Demo Fehler: {e}")
            
    def _go_next(self):
        """Nächster Schritt."""
        if self.current_step < self.total_steps - 1:
            self.current_step += 1
            self._update_view()
            
    def _go_back(self):
        """Vorheriger Schritt."""
        if self.current_step > 0:
            self.current_step -= 1
            self._update_view()
            
    def _update_view(self):
        """Aktualisiert die Anzeige."""
        self.stack.setCurrentIndex(self.current_step)
        
        # Aktuelle Karte animieren
        current_card = self.stack.currentWidget()
        if isinstance(current_card, TutorialCard):
            current_card.play_animation()
        
        # Fortschritt aktualisieren
        progress = int((self.current_step / (self.total_steps - 1)) * 100)
        self.progress_bar.setValue(progress)
        self.progress_label.setText(
            tr(f"Schritt {self.current_step + 1} von {self.total_steps}")
        )
        
        # Buttons aktualisieren
        self.back_btn.setEnabled(self.current_step > 0)
        is_last = self.current_step == self.total_steps - 1
        self.next_btn.setVisible(not is_last)
        self.finish_btn.setVisible(is_last)
        
        # Step-Indikatoren aktualisieren
        for i in range(self.total_steps):
            status = self.findChild(QLabel, f"step_status_{i}")
            if status:
                if i == self.current_step:
                    status.setText("●")
                    status.setStyleSheet("color: #48bb78; font-size: 14px;")
                elif i < self.current_step:
                    status.setText("✓")
                    status.setStyleSheet("color: #48bb78; font-size: 12px;")
                else:
                    status.setText("○")
                    status.setStyleSheet("color: #4a5568; font-size: 12px;")
                    
    def _finish(self):
        """Tutorial beenden."""
        logger.info("Enhanced tutorial completed")
        self.accept()
        
    def start(self):
        """Startet das Tutorial."""
        self._update_view()
        self.show()
        
    def exec(self):
        """Zeigt den Dialog modal an."""
        self._update_view()
        return super().exec()


def show_enhanced_tutorial(main_window=None, document=None, viewport=None):
    """
    Zeigt das verbesserte Tutorial an.
    
    Usage:
        from gui.enhanced_tutorial import show_enhanced_tutorial
        show_enhanced_tutorial(main_window, document, viewport)
    """
    tutorial = EnhancedTutorial(main_window, document, viewport)
    return tutorial.exec()
