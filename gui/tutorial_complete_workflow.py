"""
MashCAD - Complete Workflow Tutorial
=====================================

Ein umfassendes Tutorial für absolute Anfänger:
- Navigation im 3D-Raum (Orbit, Zoom, Pan)
- Koordinatensystem (X, Y, Z Achsen)
- Kompletter Workflow: Sketch → 3D → Export
- Speichern & STL-Export für 3D-Druck
- UI-Grundlagen

Ziel: Nach diesem Tutorial kann ein Anfänger:
1. Sich im 3D-Raum bewegen
2. Ein einfaches Teil modellieren
3. Es für den 3D-Druck exportieren
4. Das Projekt speichern

Author: Kimi
Date: 2026-02-19
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QFrame, QGraphicsDropShadowEffect,
    QDockWidget, QProgressBar, QTextEdit, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QColor, QFont
from loguru import logger
from dataclasses import dataclass
from typing import Optional
from enum import Enum

from i18n import tr


class TutorialStepType(Enum):
    INFO = "info"
    NAVIGATION = "navigation"
    CREATE_SKETCH = "create_sketch"
    DRAW_SHAPE = "draw_shape"
    EXTRUDE = "extrude"
    APPLY_FEATURE = "apply_feature"
    SAVE_EXPORT = "save_export"
    COMPLETION = "completion"


@dataclass
class TutorialStep:
    step_type: TutorialStepType
    number: int
    title: str
    instruction: str
    explanation: str
    hint: str
    xp_reward: int
    demo_mode: str = ""  # "orbit", "sketch", "extrude", "chamfer", "export"


class TutorialProgressPanel(QFrame):
    """Panel mit Fortschrittsanzeige."""
    
    step_completed = Signal()
    skip_requested = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(380)
        self._setup_ui()
        
    def _setup_ui(self):
        self.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1a202c,
                    stop: 1 #0d1117
                );
                border-right: 2px solid #2d3748;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        
        # Header
        header = QHBoxLayout()
        logo = QLabel("🎓")
        logo.setStyleSheet("font-size: 28px;")
        header.addWidget(logo)
        
        title = QLabel("MashCAD Lernen")
        title.setStyleSheet("""
            color: #e2e8f0;
            font-size: 18px;
            font-weight: bold;
        """)
        header.addWidget(title)
        header.addStretch()
        
        xp = QLabel("XP")
        xp.setStyleSheet("""
            color: #48bb78;
            font-size: 12px;
            background: #48bb7820;
            padding: 4px 12px;
            border-radius: 12px;
        """)
        header.addWidget(xp)
        layout.addLayout(header)
        
        # Progress Bar
        self.progress_label = QLabel("Schritt 1 von 7")
        self.progress_label.setStyleSheet("color: #718096; font-size: 12px;")
        layout.addWidget(self.progress_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 7)
        self.progress_bar.setValue(1)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #2d3748;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #4299e1,
                    stop: 1 #48bb78
                );
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # Main Content Card
        self.card = QFrame()
        self.card.setStyleSheet("""
            QFrame {
                background-color: #0f1419;
                border: 2px solid #2d3748;
                border-radius: 16px;
            }
        """)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(16)
        
        # Step Number Badge
        self.step_badge = QLabel("1")
        self.step_badge.setFixedSize(48, 48)
        self.step_badge.setAlignment(Qt.AlignCenter)
        self.step_badge.setStyleSheet("""
            QLabel {
                background-color: #4299e1;
                color: white;
                border-radius: 24px;
                font-size: 20px;
                font-weight: bold;
            }
        """)
        card_layout.addWidget(self.step_badge, alignment=Qt.AlignCenter)
        
        # Step Title
        self.step_title = QLabel("Willkommen!")
        self.step_title.setStyleSheet("""
            color: #e2e8f0;
            font-size: 20px;
            font-weight: bold;
        """)
        self.step_title.setAlignment(Qt.AlignCenter)
        self.step_title.setWordWrap(True)
        card_layout.addWidget(self.step_title)
        
        # Step Type Badge
        self.type_badge = QLabel("INFO")
        self.type_badge.setAlignment(Qt.AlignCenter)
        self.type_badge.setStyleSheet("""
            color: #4299e1;
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 1px;
            background: #4299e120;
            padding: 4px 12px;
            border-radius: 8px;
        """)
        card_layout.addWidget(self.type_badge, alignment=Qt.AlignCenter)
        
        # Instruction
        self.instruction = QTextEdit()
        self.instruction.setReadOnly(True)
        self.instruction.setMaximumHeight(120)
        self.instruction.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                border: none;
                color: #e2e8f0;
                font-size: 14px;
                line-height: 1.6;
            }
        """)
        card_layout.addWidget(self.instruction)
        
        # Explanation Box
        self.explanation_frame = QFrame()
        self.explanation_frame.setStyleSheet("""
            QFrame {
                background-color: #1a365d;
                border: 1px solid #2b6cb0;
                border-radius: 8px;
            }
        """)
        exp_layout = QVBoxLayout(self.explanation_frame)
        exp_layout.setContentsMargins(16, 16, 16, 16)
        
        exp_header = QLabel("💡 Warum das wichtig ist:")
        exp_header.setStyleSheet("color: #63b3ed; font-size: 11px; font-weight: bold;")
        exp_layout.addWidget(exp_header)
        
        self.explanation = QLabel()
        self.explanation.setWordWrap(True)
        self.explanation.setStyleSheet("color: #bee3f8; font-size: 12px; line-height: 1.5;")
        exp_layout.addWidget(self.explanation)
        
        card_layout.addWidget(self.explanation_frame)
        
        # Hint Box
        self.hint_frame = QFrame()
        self.hint_frame.setStyleSheet("""
            QFrame {
                background-color: #2d1b1b;
                border: 1px solid #744210;
                border-radius: 8px;
            }
        """)
        hint_layout = QVBoxLayout(self.hint_frame)
        hint_layout.setContentsMargins(16, 16, 16, 16)
        
        hint_header = QLabel("🎯 So geht's:")
        hint_header.setStyleSheet("color: #f6ad55; font-size: 11px; font-weight: bold;")
        hint_layout.addWidget(hint_header)
        
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #fbd38d; font-size: 12px; line-height: 1.5;")
        hint_layout.addWidget(self.hint)
        
        card_layout.addWidget(self.hint_frame)
        
        # Status
        self.status = QLabel("⏳ Warte auf Aktion...")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("""
            color: #fbbf24;
            font-size: 13px;
            background: #fbbf2420;
            padding: 12px;
            border-radius: 8px;
            font-weight: bold;
        """)
        card_layout.addWidget(self.status)
        
        # Manual Confirm Button
        self.confirm_btn = QPushButton("✓ Ich habe es geschafft")
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #48bb78,
                    stop: 1 #38a169
                );
                border: none;
                color: white;
                padding: 14px 28px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #38a169,
                    stop: 1 #2f855a
                );
            }
        """)
        self.confirm_btn.clicked.connect(self.step_completed.emit)
        card_layout.addWidget(self.confirm_btn)
        
        layout.addWidget(self.card)
        
        # Skip Button
        skip = QPushButton("Tutorial überspringen")
        skip.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #4a5568;
                color: #718096;
                padding: 10px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background: #2d3748;
                color: #a0aec0;
            }
        """)
        skip.clicked.connect(self.skip_requested.emit)
        layout.addWidget(skip)
        
        layout.addStretch()
        
    def update_step(self, step: TutorialStep):
        """Aktualisiert die Anzeige für einen Schritt."""
        self.step_badge.setText(str(step.number))
        self.step_title.setText(step.title)
        self.progress_label.setText(f"Schritt {step.number} von 7")
        self.progress_bar.setValue(step.number)
        
        self.instruction.setText(step.instruction)
        self.explanation.setText(step.explanation)
        self.hint.setText(step.hint)
        
        # Type Badge
        type_names = {
            TutorialStepType.INFO: "INFO",
            TutorialStepType.NAVIGATION: "NAVIGATION",
            TutorialStepType.CREATE_SKETCH: "SKIZZE",
            TutorialStepType.DRAW_SHAPE: "ZEICHNEN",
            TutorialStepType.EXTRUDE: "3D",
            TutorialStepType.APPLY_FEATURE: "FEATURE",
            TutorialStepType.SAVE_EXPORT: "EXPORT",
            TutorialStepType.COMPLETION: "ABSCHLUSS"
        }
        self.type_badge.setText(type_names.get(step.step_type, "SCHRITT"))
        
        # Status zurücksetzen
        self.status.setText("⏳ Warte auf Aktion...")
        self.status.setStyleSheet("""
            color: #fbbf24;
            font-size: 13px;
            background: #fbbf2420;
            padding: 12px;
            border-radius: 8px;
            font-weight: bold;
        """)
        
    def show_success(self, xp: int):
        """Zeigt Erfolg an."""
        self.status.setText(f"✅ Geschafft! +{xp} XP")
        self.status.setStyleSheet("""
            color: #48bb78;
            font-size: 13px;
            background: #48bb7820;
            padding: 12px;
            border-radius: 8px;
            font-weight: bold;
        """)


class CompleteWorkflowTutorial(QObject):
    """Das komplette Workflow-Tutorial."""
    
    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.current_step = 0
        self.total_xp = 0
        self.panel = None
        
        self._create_steps()
        
    def _create_steps(self):
        """Erstellt alle 7 Tutorial-Schritte."""
        self.steps = [
            TutorialStep(
                step_type=TutorialStepType.NAVIGATION,
                number=1,
                title="Navigation im 3D-Raum",
                instruction="Lernen Sie, wie Sie sich im 3D-Raum bewegen:\n\n"
                          "🖱️ Mittlere Maustaste gedrückt halten = Ansicht drehen (Orbit)\n"
                          "🖱️ Mausrad = Zoomen (ranzoomen / wegzoomen)\n"
                          "🖱️ Shift + Mittlere Maustaste = Ansicht verschieben (Pan)",
                explanation="Ohne Navigation sind Sie 'blind' im 3D-Raum. "
                          "Diese 3 Bewegungen sind das A und O jedes CAD-Programms.",
                hint="Probieren Sie es aus: Halten Sie die mittlere Maustaste und bewegen Sie die Maus. "
                     "Dreht sich die Ansicht?",
                xp_reward=50,
                demo_mode="orbit"
            ),
            
            TutorialStep(
                step_type=TutorialStepType.CREATE_SKETCH,
                number=2,
                title="Erste Skizze erstellen",
                instruction="Jedes 3D-Modell beginnt mit einer 2D-Skizze:\n\n"
                          "1. Klicken Sie auf 'Neue Skizze'\n"
                          "2. Wählen Sie die XY-Ebene (die blaue Fläche im Koordinatensystem)\n"
                          "3. Der Sketch-Editor öffnet sich automatisch",
                explanation="Eine Skizze ist wie ein Blatt Papier, auf dem Sie zeichnen. "
                          "Die XY-Ebene ist die 'Bodenfläche' - wie ein Blatt auf dem Tisch.",
                hint="Suchen Sie den blauen Button 'Neue Skizze', dann klicken Sie auf die blaue Fläche (XY-Ebene).",
                xp_reward=100,
                demo_mode="sketch"
            ),
            
            TutorialStep(
                step_type=TutorialStepType.DRAW_SHAPE,
                number=3,
                title="Ein Rechteck zeichnen",
                instruction="Zeichnen wir ein einfaches Rechteck:\n\n"
                          "1. Wählen Sie das Rechteck-Werkzeug in der Toolbar\n"
                          "2. Klicken Sie auf den Ursprung (wo die Achsen sich kreuzen)\n"
                          "3. Ziehen Sie die Maus und klicken Sie wieder",
                explanation="Das Grid (das Raster) hilft Ihnen, gerade Linien zu zeichnen. "
                          "Die Maßlinien zeigen Ihnen automatisch die Größe an.",
                hint="Das Rechteck-Werkzeug hat ein Rechteck-Symbol. Es ist in der linken Toolbar.",
                xp_reward=150,
                demo_mode="rectangle"
            ),
            
            TutorialStep(
                step_type=TutorialStepType.EXTRUDE,
                number=4,
                title="Von 2D zu 3D extrudieren",
                instruction="Aus dem flachen Rechteck machen wir einen Körper:\n\n"
                          "1. Klicken Sie 'Fertig stellen' um den Sketch zu schließen\n"
                          "2. Wählen Sie 'Extrudieren' aus der Toolbar\n"
                          "3. Ziehen Sie den Pfeil oder geben Sie 20mm ein\n"
                          "4. Klicken Sie auf OK",
                explanation="'Extrudieren' ist wie Knete durch einen Ausstecher drücken. "
                          "Aus einer flachen Form wird ein fester Körper (Body).",
                hint="Nach 'Fertig stellen' finden Sie 'Extrudieren' im 'Modeling'-Menü oder in der Toolbar.",
                xp_reward=200,
                demo_mode="extrude"
            ),
            
            TutorialStep(
                step_type=TutorialStepType.APPLY_FEATURE,
                number=5,
                title="Kanten brechen (Chamfer)",
                instruction="Machen wir das Teil realistischer:\n\n"
                          "1. Wählen Sie eine Kante der Box (klicken Sie darauf)\n"
                          "2. Wählen Sie 'Chamfer' aus dem Modify-Menü\n"
                          "3. Geben Sie 2mm ein\n"
                          "4. Klicken Sie OK",
                explanation="Chamfer (Fase) bricht scharfe Kanten ab. "
                          "Das sieht realistischer aus und ist besser für den 3D-Druck.",
                hint="Eine Kante ist die Linie zwischen zwei Flächen. Chamfer ist unter 'Modify' → 'Chamfer'.",
                xp_reward=150,
                demo_mode="chamfer"
            ),
            
            TutorialStep(
                step_type=TutorialStepType.SAVE_EXPORT,
                number=6,
                title="Speichern & Exportieren",
                instruction="Speichern Sie Ihr Werk und bereiten Sie es für den 3D-Druck vor:\n\n"
                          "1. Datei → Speichern unter → Geben Sie einen Namen ein (.mashcad)\n"
                          "2. Datei → Exportieren → Als STL\n"
                          "3. Wählen Sie 'Fine' Qualität\n"
                          "4. Speichern Sie die .stl Datei",
                explanation=".mashcad = Ihr Projekt (können Sie später weiter bearbeiten)\n"
                          ".stl = 3D-Druck Datei (nur das Ergebnis, nicht bearbeitbar)",
                hint="STL ist das Standardformat für 3D-Drucker. Exportieren Sie immer als 'Fine' für beste Qualität.",
                xp_reward=200,
                demo_mode="export"
            ),
            
            TutorialStep(
                step_type=TutorialStepType.COMPLETION,
                number=7,
                title="🎉 Geschafft! Was Sie können:",
                instruction="Sie haben gelernt:\n\n"
                          "✅ Navigation: Orbit, Zoom, Pan\n"
                          "✅ Sketch → Extrude → Body Workflow\n"
                          "✅ Features anwenden (Chamfer)\n"
                          "✅ Projekt speichern (.mashcad)\n"
                          "✅ Für 3D-Druck exportieren (.stl)",
                explanation="Sie sind kein Experte, aber Sie haben das Grundgerüst! "
                          "Jetzt können Sie eigene Projekte starten.",
                hint="Nächste Schritte: Probieren Sie 'Fillet' (Abrundung) oder 'Loch' aus. "
                     "Öffnen Sie die Beispiel-Projekte zum Lernen.",
                xp_reward=300
            ),
        ]
        
    def start(self):
        """Startet das Tutorial."""
        self.panel = TutorialProgressPanel()
        self.panel.step_completed.connect(self._next_step)
        self.panel.skip_requested.connect(self._finish)
        
        # Als Dock hinzufügen
        from PySide6.QtWidgets import QDockWidget
        self.dock = QDockWidget("Tutorial", self.mw)
        self.dock.setWidget(self.panel)
        self.dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.dock.setTitleBarWidget(QWidget())
        self.dock.setFixedWidth(400)
        
        self.mw.addDockWidget(Qt.LeftDockWidgetArea, self.dock)
        
        # Ersten Schritt anzeigen
        self._show_step()
        
        logger.info("[Tutorial] Complete Workflow Tutorial gestartet")
        
    def _show_step(self):
        """Zeigt aktuellen Schritt an."""
        if self.current_step >= len(self.steps):
            self._finish()
            return
            
        step = self.steps[self.current_step]
        self.panel.update_step(step)
        
    def _next_step(self):
        """Geht zum nächsten Schritt."""
        # XP hinzufügen
        step = self.steps[self.current_step]
        self.total_xp += step.xp_reward
        self.panel.show_success(step.xp_reward)
        
        # Kurze Pause, dann nächster Schritt
        QTimer.singleShot(1500, self._advance)
        
    def _advance(self):
        """Wechselt tatsächlich zum nächsten Schritt."""
        self.current_step += 1
        self._show_step()
        
    def _finish(self):
        """Beendet das Tutorial."""
        if hasattr(self, 'dock'):
            self.mw.removeDockWidget(self.dock)
            
        # Abschluss-Message
        msg = f"""
        <h2>🎉 Tutorial Abgeschlossen!</h2>
        <p>Sie haben <b>{self.total_xp} XP</b> gesammelt!</p>
        <hr>
        <p><b>Sie können jetzt:</b></p>
        <ul>
            <li>Im 3D-Raum navigieren</li>
            <li>Skizzen erstellen und zu 3D extrudieren</li>
            <li>Features anwenden (Chamfer)</li>
            <li>Projekte speichern und als STL exportieren</li>
        </ul>
        <p><b>Nächste Schritte:</b></p>
        <ul>
            <li>Probieren Sie 'Fillet' (Abrundung) aus</li>
            <li>Erstellen Sie ein Loch mit dem 'Hole' Feature</li>
            <li>Öffnen Sie die Beispiel-Projekte</li>
        </ul>
        <p>Viel Erfolg mit Ihren 3D-Projekten! 🚀</p>
        """
        
        QMessageBox.information(
            self.mw,
            "Tutorial Complete",
            msg
        )
        
        logger.info(f"[Tutorial] Abgeschlossen mit {self.total_xp} XP")


def start_complete_tutorial(main_window):
    """Startet das komplette Workflow-Tutorial."""
    tutorial = CompleteWorkflowTutorial(main_window)
    tutorial.start()
    return tutorial
