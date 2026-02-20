"""
MashCAD - First Run Wizard
===========================

Phase 2: UX-001 - First-Run Guided Flow

Interaktiver Wizard für neue Nutzer beim ersten Start.
Führt durch:
- Grundlegende Navigation
- Erstes Sketch erstellen
- Erste 3D-Operation
- Export eines druckbaren Teils

Usage:
    from gui.first_run_wizard import FirstRunWizard
    
    wizard = FirstRunWizard(main_window)
    if wizard.should_show():
        wizard.exec()

Author: Kimi (UX-001 Implementation)
Date: 2026-02-19
Branch: feature/v1-ux-aiB
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QStackedWidget, QWidget, QProgressBar,
    QCheckBox, QFrame, QTextEdit, QListWidget, QListWidgetItem,
    QGraphicsDropShadowEffect, QApplication, QMessageBox
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import QColor, QFont, QPixmap
from loguru import logger
from pathlib import Path
import json

from gui.design_tokens import DesignTokens
from i18n import tr


class WizardPage(QWidget):
    """Basis-Klasse für Wizard-Seiten."""
    
    def __init__(self, title: str, description: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.description = description
        self._setup_ui()
        
    def _setup_ui(self):
        """Erstellt die UI der Seite."""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(40, 40, 40, 40)
        
        # Titel
        self.title_label = QLabel(self.title)
        self.title_label.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: #2196F3;
        """)
        layout.addWidget(self.title_label)
        
        # Beschreibung
        self.desc_label = QLabel(self.description)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("font-size: 14px; color: #666;")
        layout.addWidget(self.desc_label)
        
        # Content-Bereich (wird von Unterklassen gefüllt)
        self.content_frame = QFrame()
        self.content_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-radius: 12px;
                border: 1px solid #e0e0e0;
            }
        """)
        self.content_layout = QVBoxLayout(self.content_frame)
        layout.addWidget(self.content_frame, stretch=1)
        
        layout.addStretch()
        
    def get_content_layout(self):
        """Gibt das Content-Layout zurück."""
        return self.content_layout


class WelcomePage(WizardPage):
    """Willkommens-Seite."""
    
    def __init__(self, parent=None):
        super().__init__(
            title=tr("Willkommen bei MashCAD! 🎉"),
            description=tr("Lassen Sie sich in wenigen Minuten durch die Grundlagen führen. "
                          "Sie werden Ihr erstes 3D-Modell erstellen und exportieren."),
            parent=parent
        )
        self._setup_content()
        
    def _setup_content(self):
        """Erstellt den Content."""
        layout = self.get_content_layout()
        
        # Features-Liste
        features = [
            ("✏️", tr("Skizzen erstellen"), tr("Zeichnen Sie 2D-Profile mit Constraints")),
            ("🔷", tr("3D-Modelle extrudieren"), tr("Wandeln Sie Skizzen in 3D-Körper um")),
            ("📐", tr("Bemaßen und positionieren"), tr("Nutzen Sie parametrische Constraints")),
            ("🖨️", tr("Für 3D-Druck exportieren"), tr("Exportieren Sie als STL für den Druck")),
        ]
        
        for icon, title, desc in features:
            feature_frame = QFrame()
            feature_layout = QHBoxLayout(feature_frame)
            
            icon_label = QLabel(icon)
            icon_label.setStyleSheet("font-size: 32px;")
            feature_layout.addWidget(icon_label)
            
            text_layout = QVBoxLayout()
            title_lbl = QLabel(f"<b>{title}</b>")
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet("color: #666;")
            text_layout.addWidget(title_lbl)
            text_layout.addWidget(desc_lbl)
            
            feature_layout.addLayout(text_layout, stretch=1)
            layout.addWidget(feature_frame)
        
        # Dauer-Hinweis
        duration = QLabel(tr("⏱️ Dauer: ca. 5 Minuten"))
        duration.setStyleSheet("color: #2196F3; font-weight: bold; margin-top: 20px;")
        duration.setAlignment(Qt.AlignCenter)
        layout.addWidget(duration)


class InterfaceOverviewPage(WizardPage):
    """Übersicht über die Benutzeroberfläche."""
    
    def __init__(self, parent=None):
        super().__init__(
            title=tr("Die Benutzeroberfläche"),
            description=tr("Lernen Sie die wichtigsten Bereiche der Anwendung kennen."),
            parent=parent
        )
        self._setup_content()
        
    def _setup_content(self):
        """Erstellt den Content."""
        layout = self.get_content_layout()
        
        # UI-Bereiche
        areas = [
            (tr("🎨 Werkzeugleiste"), 
             tr("Links finden Sie Werkzeuge für Sketch, 3D-Features und Ansichten.")),
            (tr("🔲 Viewport"), 
             tr("Die Hauptarbeitsfläche zeigt Ihr 3D-Modell. Zoomen mit Mausrad, drehen mit mittlerer Maustaste.")),
            (tr("📋 Browser-Panel"), 
             tr("Rechts sehen Sie die Feature-Hierarchie, Sketches und Bodies.")),
            (tr("📐 Sketch-Editor"), 
             tr("Öffnet sich automatisch wenn Sie eine Skizze bearbeiten.")),
        ]
        
        for title, desc in areas:
            area_frame = QFrame()
            area_frame.setStyleSheet("""
                QFrame {
                    background-color: white;
                    border-radius: 8px;
                    padding: 10px;
                    margin: 5px;
                }
            """)
            area_layout = QVBoxLayout(area_frame)
            
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
            area_layout.addWidget(title_lbl)
            
            desc_lbl = QLabel(desc)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #666;")
            area_layout.addWidget(desc_lbl)
            
            layout.addWidget(area_frame)


class FirstSketchPage(WizardPage):
    """Seite für erstes Sketch."""
    
    def __init__(self, parent=None):
        super().__init__(
            title=tr("Ihre erste Skizze"),
            description=tr("Jedes 3D-Modell beginnt mit einer 2D-Skizze."),
            parent=parent
        )
        self._setup_content()
        
    def _setup_content(self):
        """Erstellt den Content."""
        layout = self.get_content_layout()
        
        # Schritte
        steps = [
            tr("1. Klicken Sie auf 'Neue Skizze' in der Werkzeugleiste"),
            tr("2. Wählen Sie eine Ebene (XY, YZ oder ZX)"),
            tr("3. Der Sketch-Editor öffnet sich automatisch"),
            tr("4. Zeichnen Sie ein Rechteck mit dem Rechteck-Werkzeug"),
            tr("5. Bemaßen Sie es mit dem Maß-Werkzeug"),
        ]
        
        for step in steps:
            step_lbl = QLabel(step)
            step_lbl.setStyleSheet("""
                padding: 10px;
                background-color: white;
                border-radius: 6px;
                border-left: 4px solid #2196F3;
            """)
            layout.addWidget(step_lbl)
        
        # Tipp
        tip = QLabel(tr("💡 Tipp: Verwenden Sie Constraints (Horizontal, Vertikal, ...) "
                       "statt exakter Maße für flexiblere Modelle."))
        tip.setWordWrap(True)
        tip.setStyleSheet("""
            background-color: #FFF3E0;
            padding: 15px;
            border-radius: 8px;
            color: #E65100;
            margin-top: 20px;
        """)
        layout.addWidget(tip)


class First3DPage(WizardPage):
    """Seite für erste 3D-Operation."""
    
    def __init__(self, parent=None):
        super().__init__(
            title=tr("Von 2D zu 3D"),
            description=tr("Extrudieren Sie Ihre Skizze zu einem 3D-Körper."),
            parent=parent
        )
        self._setup_content()
        
    def _setup_content(self):
        """Erstellt den Content."""
        layout = self.get_content_layout()
        
        # Extrude-Info
        info = QLabel(tr("Die Extrusion ist die wichtigste 3D-Operation:"))
        layout.addWidget(info)
        
        # Vorgehen
        procedure = [
            (tr("Skizze fertigstellen"), 
             tr("Schließen Sie den Sketch-Editor mit 'Fertig stellen'")),
            (tr("Extrude wählen"), 
             tr("Klicken Sie auf 'Extrudieren' in der 3D-Werkzeugleiste")),
            (tr("Tiefe festlegen"), 
             tr("Geben Sie die Extrusions-Tiefe ein (z.B. 10 mm)")),
            (tr("Bestätigen"), 
             tr("Klicken Sie auf 'OK' um die Operation auszuführen")),
        ]
        
        for title, desc in procedure:
            frame = QFrame()
            frame.setStyleSheet("""
                QFrame {
                    background-color: white;
                    border-radius: 8px;
                    padding: 5px;
                }
            """)
            frame_layout = QVBoxLayout(frame)
            
            title_lbl = QLabel(f"<b>{title}</b>")
            frame_layout.addWidget(title_lbl)
            
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet("color: #666;")
            frame_layout.addWidget(desc_lbl)
            
            layout.addWidget(frame)
        
        # Weitere Features
        more = QLabel(tr("Danach können Sie weitere Features anwenden:")
                     + "\n• Bohrungen (Hole)\n• Abrundungen (Fillet)\n• Fasen (Chamfer)")
        more.setStyleSheet("margin-top: 20px;")
        layout.addWidget(more)


class ExportPage(WizardPage):
    """Seite für Export."""
    
    def __init__(self, parent=None):
        super().__init__(
            title=tr("Export für 3D-Druck"),
            description=tr("Das Ziel: Ein druckbares Teil!"),
            parent=parent
        )
        self._setup_content()
        
    def _setup_content(self):
        """Erstellt den Content."""
        layout = self.get_content_layout()
        
        # Export-Info
        info = QLabel(tr("So exportieren Sie Ihr Modell:"))
        layout.addWidget(info)
        
        # Schritte
        steps_frame = QFrame()
        steps_frame.setStyleSheet("background-color: white; border-radius: 8px;")
        steps_layout = QVBoxLayout(steps_frame)
        
        steps = [
            tr("1. Stellen Sie sicher, dass Ihr Modell geschlossen ist (keine Löcher)"),
            tr("2. Wählen Sie 'Datei' → 'Exportieren' → 'Als STL'"),
            tr("3. Wählen Sie die Qualität (Fine für gute Druckqualität)"),
            tr("4. Speichern Sie die .stl-Datei"),
            tr("5. Laden Sie sie in Ihren Slicer (z.B. Cura, PrusaSlicer)"),
        ]
        
        for step in steps:
            lbl = QLabel(step)
            lbl.setStyleSheet("padding: 8px;")
            steps_layout.addWidget(lbl)
        
        layout.addWidget(steps_frame)
        
        # Erfolgs-Meldung
        success = QLabel(tr("🎉 Geschafft! Sie haben Ihr erstes 3D-Modell erstellt!"))
        success.setStyleSheet("""
            background-color: #E8F5E9;
            color: #2E7D32;
            padding: 20px;
            border-radius: 8px;
            font-weight: bold;
            font-size: 16px;
            margin-top: 20px;
        """)
        success.setAlignment(Qt.AlignCenter)
        layout.addWidget(success)


class FirstRunWizard(QDialog):
    """
    First-Run Wizard für neue Nutzer.
    
    Zeigt sich beim ersten Start und führt durch grundlegende Workflows.
    Bietet Option zum Starten des interaktiven Tutorials.
    """
    
    CONFIG_FILE = "first_run_config.json"
    
    def __init__(self, main_window=None, parent=None):
        """
        Args:
            main_window: Referenz zum MainWindow für Integration
            parent: Parent Widget
        """
        super().__init__(parent)
        self.main_window = main_window
        self.current_page = 0
        self._start_tutorial_requested = False
        self._setup_ui()
        self._load_config()
        
    def _setup_ui(self):
        """Erstellt die UI."""
        self.setWindowTitle(tr("MashCAD - Erste Schritte"))
        self.setMinimumSize(800, 600)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        
        # Zentrieren
        if self.parent():
            geo = self.parent().geometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2
            )
        
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Progress Bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #e0e0e0;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
            }
        """)
        layout.addWidget(self.progress)
        
        # Stacked Widget für Seiten
        self.stack = QStackedWidget()
        
        # Seiten hinzufügen
        self.pages = [
            WelcomePage(),
            InterfaceOverviewPage(),
            FirstSketchPage(),
            First3DPage(),
            ExportPage(),
        ]
        
        for page in self.pages:
            self.stack.addWidget(page)
        
        layout.addWidget(self.stack, stretch=1)
        
        # Button-Leiste
        btn_frame = QFrame()
        btn_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border-top: 1px solid #e0e0e0;
            }
        """)
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(20, 15, 20, 15)
        
        # Links: Überspringen-Checkbox
        left_layout = QHBoxLayout()
        self.skip_checkbox = QCheckBox(tr("Nicht mehr anzeigen"))
        left_layout.addWidget(self.skip_checkbox)
        left_layout.addStretch()
        btn_layout.addLayout(left_layout)
        
        btn_layout.addStretch()
        
        # Navigation
        self.back_btn = QPushButton(tr("← Zurück"))
        self.back_btn.clicked.connect(self._go_back)
        self.back_btn.setEnabled(False)
        btn_layout.addWidget(self.back_btn)
        
        self.next_btn = QPushButton(tr("Weiter →"))
        self.next_btn.setObjectName("primary")
        self.next_btn.clicked.connect(self._go_next)
        btn_layout.addWidget(self.next_btn)
        
        self.finish_btn = QPushButton(tr("Fertig 🎉"))
        self.finish_btn.setObjectName("success")
        self.finish_btn.clicked.connect(self._finish)
        self.finish_btn.setVisible(False)
        btn_layout.addWidget(self.finish_btn)
        
        # Tutorial-Buttons (nur auf der letzten Seite sichtbar)
        self.tutorial_btn = QPushButton(tr("Tutorial starten 📚"))
        self.tutorial_btn.setObjectName("tutorial")
        self.tutorial_btn.clicked.connect(self._start_tutorial_and_finish)
        self.tutorial_btn.setVisible(False)
        self.tutorial_btn.setStyleSheet("""
            QPushButton#tutorial {
                background-color: #9C27B0;
                color: white;
                border: none;
            }
            QPushButton#tutorial:hover {
                background-color: #7B1FA2;
            }
        """)
        btn_layout.addWidget(self.tutorial_btn)
        
        layout.addWidget(btn_frame)
        
        # Styling
        self.setStyleSheet("""
            QDialog {
                background-color: white;
            }
            QPushButton {
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton#primary {
                background-color: #2196F3;
                color: white;
                border: none;
            }
            QPushButton#primary:hover {
                background-color: #1976D2;
            }
            QPushButton#success {
                background-color: #4CAF50;
                color: white;
                border: none;
            }
            QPushButton#success:hover {
                background-color: #45a049;
            }
        """)
        
        self._update_buttons()
        
    def _load_config(self):
        """Lädt die Konfiguration."""
        try:
            config_path = Path(self.CONFIG_FILE)
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    self.skip_checkbox.setChecked(config.get('dont_show_again', False))
        except Exception as e:
            logger.warning(f"Failed to load first-run config: {e}")
            
    def _save_config(self):
        """Speichert die Konfiguration."""
        try:
            config = {
                'dont_show_again': self.skip_checkbox.isChecked(),
                'completed': True,
                'last_shown': str(Path.cwd() / self.CONFIG_FILE)
            }
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(config, f)
        except Exception as e:
            logger.warning(f"Failed to save first-run config: {e}")
            
    def should_show(self) -> bool:
        """
        Prüft ob der Wizard angezeigt werden soll.
        
        Returns:
            True wenn der Wizard angezeigt werden soll
        """
        try:
            config_path = Path(self.CONFIG_FILE)
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    return not config.get('dont_show_again', False)
        except Exception:
            pass
        return True
        
    def _go_next(self):
        """Geht zur nächsten Seite."""
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.stack.setCurrentIndex(self.current_page)
            self._update_buttons()
            self._update_progress()
            
    def _go_back(self):
        """Geht zur vorherigen Seite."""
        if self.current_page > 0:
            self.current_page -= 1
            self.stack.setCurrentIndex(self.current_page)
            self._update_buttons()
            self._update_progress()
            
    def _update_buttons(self):
        """Aktualisiert die Button-States."""
        self.back_btn.setEnabled(self.current_page > 0)
        
        is_last = self.current_page == len(self.pages) - 1
        self.next_btn.setVisible(not is_last)
        self.finish_btn.setVisible(is_last)
        
        # Zeige Tutorial-Button auf der letzten Seite
        from config.feature_flags import is_enabled
        self.tutorial_btn.setVisible(is_last and is_enabled("first_run_tutorial"))
        
    def _update_progress(self):
        """Aktualisiert die Progress-Bar."""
        progress = ((self.current_page + 1) / len(self.pages)) * 100
        self.progress.setValue(int(progress))
    
    def _start_tutorial_and_finish(self):
        """Startet das Tutorial und beendet den Wizard."""
        self._start_tutorial_requested = True
        self._finish()
        
    def _finish(self):
        """Beendet den Wizard."""
        self._save_config()
        
        # Starte Tutorial wenn gewünscht (via TutorialManager)
        if self._start_tutorial_requested:
            self._start_interactive_tutorial()
        
        self.accept()
        logger.info("First-run wizard completed")
    
    def _start_interactive_tutorial(self):
        """Startet das interaktive Tutorial über den TutorialManager."""
        try:
            from gui.tutorial_manager import get_tutorial_manager
            from config.feature_flags import is_enabled
            
            if is_enabled("first_run_tutorial"):
                manager = get_tutorial_manager(self.main_window)
                manager.initialize()
                manager.start_tutorial()
                
                # Wenn Main Window eine Start-Methode hat, rufe sie auf
                if self.main_window and hasattr(self.main_window, 'start_guided_tutorial'):
                    self.main_window.start_guided_tutorial()
                logger.info("Guided tutorial started from first-run wizard")
        except Exception as e:
            logger.warning(f"Failed to start interactive tutorial: {e}")
    
    def should_start_tutorial(self) -> bool:
        """Gibt zurück ob das Tutorial gestartet werden soll."""
        return self._start_tutorial_requested
        
    def reject(self):
        """Überschreibt reject um Config zu speichern."""
        self._save_config()
        super().reject()


def should_show_first_run() -> bool:
    """
    Prüft ob der First-Run Wizard angezeigt werden soll.
    
    Returns:
        True wenn angezeigt werden soll
    """
    try:
        config_path = Path(FirstRunWizard.CONFIG_FILE)
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
                return not config.get('dont_show_again', False)
    except Exception:
        pass
    return True


def reset_first_run_config():
    """Setzt die First-Run Config zurück (für Testing)."""
    try:
        config_path = Path(FirstRunWizard.CONFIG_FILE)
        if config_path.exists():
            config_path.unlink()
            logger.info("First-run config reset")
    except Exception as e:
        logger.warning(f"Failed to reset first-run config: {e}")
