"""
MashCAD - Tutorial Manager
==========================

Phase 2: UX-001 - First-Run Guided Flow

Zentraler Manager für das Tutorial-System:
- Verwaltet Tutorial-Fortschritt
- Prüft Abschluss-Bedingungen
- Speichert Status in Settings

Usage:
    from gui.tutorial_manager import TutorialManager, TutorialStepData
    
    manager = TutorialManager(main_window)
    manager.start_tutorial()
    
Author: Kimi (UX-001 Implementation)
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

from dataclasses import dataclass, field
from typing import Optional, Callable, List, Dict, Any
from PySide6.QtCore import QObject, Signal, QRect, QTimer, QSettings
from PySide6.QtWidgets import QWidget
from loguru import logger
from pathlib import Path
import json

from i18n import tr


@dataclass
class TutorialStepData:
    """
    Daten-Klasse für einen Tutorial-Schritt.
    
    Attributes:
        step_id: Eindeutige ID für den Schritt
        title: Titel des Schritts
        description: Detaillierte Beschreibung
        target_area: Optional QRect für Highlight-Bereich
        action_required: Was der Nutzer tun soll
        action_check: Callable das True zurückgibt wenn Aktion abgeschlossen
        hints: Zusätzliche Hinweise
        auto_advance: Automatisch weiter wenn Aktion abgeschlossen
    """
    step_id: str
    title: str
    description: str
    target_area: Optional[QRect] = None
    action_required: str = ""
    action_check: Optional[Callable[[], bool]] = None
    hints: List[str] = field(default_factory=list)
    auto_advance: bool = False
    
    def is_completed(self) -> bool:
        """Prüft ob dieser Schritt abgeschlossen ist."""
        if self.action_check is None:
            return False
        try:
            return self.action_check()
        except Exception as e:
            logger.warning(f"Action check failed for step {self.step_id}: {e}")
            return False


# Definiere die 5 Tutorial-Schritte
def create_tutorial_steps(main_window) -> List[TutorialStepData]:
    """
    Erstellt die 5-Schritt Tutorial-Definition.
    
    Schritte:
    1. Welcome - Einführung in MashCAD
    2. Sketch Basics - Rechteck erstellen, Bemaßung hinzufügen
    3. Extrude - Sketch zu 3D-Körper konvertieren
    4. Modify - Fillet zu Kanten hinzufügen
    5. Export - Als STL für 3D-Druck exportieren
    """
    steps = []
    
    # Schritt 1: Welcome
    steps.append(TutorialStepData(
        step_id="welcome",
        title=tr("Willkommen bei MashCAD!"),
        description=tr(
            "MashCAD ist ein parametrisches 3D-CAD-Programm für den 3D-Druck. "
            "In diesem Tutorial lernen Sie die Grundlagen in etwa 10 Minuten."
        ),
        action_required=tr("Klicken Sie auf 'Weiter' um zu beginnen."),
        hints=[
            tr("💡 Alle Aktionen können rückgängig gemacht werden (Strg+Z)"),
            tr("💡 Speichern Sie regelmäßig mit Strg+S"),
        ],
        auto_advance=False
    ))
    
    # Schritt 2: Sketch Basics
    steps.append(TutorialStepData(
        step_id="sketch_basics",
        title=tr("Skizze erstellen"),
        description=tr(
            "Jedes 3D-Modell beginnt mit einer 2D-Skizze. "
            "Sie werden ein Rechteck zeichnen und bemaßen."
        ),
        action_required=tr(
            "1. Klicken Sie auf 'Neue Skizze' in der Werkzeugleiste\n"
            "2. Wählen Sie die XY-Ebene\n"
            "3. Zeichnen Sie ein Rechteck mit dem Rechteck-Werkzeug\n"
            "4. Fügen Sie eine Bemaßung hinzu"
        ),
        action_check=lambda: _check_sketch_created(main_window),
        hints=[
            tr("💡 Das Rechteck-Werkzeug finden Sie in der Sketch-Werkzeugleiste"),
            tr("💡 Mit 'D' können Sie schnell eine Bemaßung hinzufügen"),
        ],
        auto_advance=False
    ))
    
    # Schritt 3: Extrude
    steps.append(TutorialStepData(
        step_id="extrude",
        title=tr("Zu 3D extrudieren"),
        description=tr(
            "Die Extrusion wandelt Ihre 2D-Skizze in einen 3D-Körper um."
        ),
        action_required=tr(
            "1. Schließen Sie den Sketch-Editor mit 'Fertig stellen'\n"
            "2. Wählen Sie 'Extrudieren' in der 3D-Werkzeugleiste\n"
            "3. Geben Sie eine Tiefe ein (z.B. 10 mm)\n"
            "4. Bestätigen Sie mit OK"
        ),
        action_check=lambda: _check_body_created(main_window),
        hints=[
            tr("💡 Die Extrusionstiefe kann später geändert werden"),
            tr("💡 Sie können auch in beide Richtungen extrudieren"),
        ],
        auto_advance=False
    ))
    
    # Schritt 4: Modify (Fillet)
    steps.append(TutorialStepData(
        step_id="modify_fillet",
        title=tr("Kanten abrunden"),
        description=tr(
            "Fillet (Abrundung) macht scharfe Kanten zu runden Übergängen. "
            "Dies ist wichtig für druckbare Teile."
        ),
        action_required=tr(
            "1. Wählen Sie eine oder mehrere Kanten im 3D-Modell\n"
            "2. Klicken Sie auf 'Fillet' in der Werkzeugleiste\n"
            "3. Geben Sie einen Radius ein (z.B. 2 mm)\n"
            "4. Bestätigen Sie mit OK"
        ),
        action_check=lambda: _check_fillet_applied(main_window),
        hints=[
            tr("💡 Fillets verbessern die Druckbarkeit erheblich"),
            tr("💡 Halten Sie Strg gedrückt um mehrere Kanten zu wählen"),
        ],
        auto_advance=False
    ))
    
    # Schritt 5: Export
    steps.append(TutorialStepData(
        step_id="export",
        title=tr("Für 3D-Druck exportieren"),
        description=tr(
            "Exportieren Sie Ihr Modell als STL-Datei für den 3D-Druck."
        ),
        action_required=tr(
            "1. Wählen Sie 'Datei' → 'Exportieren' → 'Als STL'\n"
            "2. Wählen Sie die Qualität (Fine empfohlen)\n"
            "3. Speichern Sie die Datei"
        ),
        action_check=lambda: _check_export_completed(main_window),
        hints=[
            tr("💡 STL ist das Standardformat für die meisten Slicer"),
            tr("💡 Für mehr Details wählen Sie 'Fine' oder 'Ultra'"),
        ],
        auto_advance=False
    ))
    
    return steps


# Helper-Funktionen für Action-Checks
def _check_sketch_created(main_window) -> bool:
    """Prüft ob eine Skizze mit Geometrie erstellt wurde."""
    try:
        if hasattr(main_window, 'browser') and main_window.browser:
            # Prüfe ob Sketches existieren
            if hasattr(main_window.browser, 'sketches'):
                for sketch in main_window.browser.sketches.values():
                    if hasattr(sketch, 'geometry') and len(sketch.geometry) > 0:
                        return True
        return False
    except Exception as e:
        logger.debug(f"Sketch check failed: {e}")
        return False


def _check_body_created(main_window) -> bool:
    """Prüft ob ein 3D-Körper erstellt wurde."""
    try:
        if hasattr(main_window, 'browser') and main_window.browser:
            # Prüfe ob Bodies existieren
            if hasattr(main_window.browser, 'bodies'):
                return len(main_window.browser.bodies) > 0
        return False
    except Exception as e:
        logger.debug(f"Body check failed: {e}")
        return False


def _check_fillet_applied(main_window) -> bool:
    """Prüft ob ein Fillet angewendet wurde."""
    try:
        if hasattr(main_window, 'browser') and main_window.browser:
            # Prüfe Feature-Historie auf Fillet
            if hasattr(main_window.browser, 'features'):
                for feature in main_window.browser.features:
                    if hasattr(feature, 'type') and 'fillet' in feature.type.lower():
                        return True
        return False
    except Exception as e:
        logger.debug(f"Fillet check failed: {e}")
        return False


def _check_export_completed(main_window) -> bool:
    """Prüft ob ein Export durchgeführt wurde."""
    try:
        settings = QSettings("MashCAD", "Tutorial")
        return settings.value("last_export_completed", False, type=bool)
    except Exception as e:
        logger.debug(f"Export check failed: {e}")
        return False


class TutorialManager(QObject):
    """
    Zentraler Manager für das Tutorial-System.
    
    Signale:
        step_changed: Aktueller Schritt hat sich geändert
        step_completed: Schritt wurde abgeschlossen
        tutorial_completed: Gesamtes Tutorial wurde abgeschlossen
        progress_updated: Fortschritt hat sich geändert (0-100)
    """
    
    # Signale
    step_changed = Signal(int)  # step_index
    step_completed = Signal(str)  # step_id
    tutorial_completed = Signal()
    progress_updated = Signal(int)  # percentage
    
    # Settings-Key
    SETTINGS_KEY = "tutorial_progress"
    COMPLETED_KEY = "tutorial_completed"
    
    def __init__(self, main_window: QWidget = None, parent: QObject = None):
        super().__init__(parent)
        self.main_window = main_window
        self._current_step = 0
        self._steps: List[TutorialStepData] = []
        self._is_active = False
        self._completion_timer = QTimer(self)
        self._completion_timer.timeout.connect(self._check_step_completion)
        self._completion_timer.setInterval(500)  # Check every 500ms
        
        # Load saved progress
        self._load_progress()
        
    @property
    def current_step_index(self) -> int:
        """Aktueller Schritt-Index (0-basiert)."""
        return self._current_step
    
    @property
    def current_step(self) -> Optional[TutorialStepData]:
        """Aktueller Tutorial-Schritt."""
        if 0 <= self._current_step < len(self._steps):
            return self._steps[self._current_step]
        return None
    
    @property
    def total_steps(self) -> int:
        """Gesamtanzahl der Schritte."""
        return len(self._steps)
    
    @property
    def is_active(self) -> bool:
        """Ob das Tutorial gerade aktiv ist."""
        return self._is_active
    
    def initialize(self):
        """Initialisiert das Tutorial mit den Schritten."""
        self._steps = create_tutorial_steps(self.main_window)
        logger.info(f"Tutorial initialized with {len(self._steps)} steps")
    
    def start_tutorial(self):
        """Startet das Tutorial vom ersten Schritt."""
        if not self._steps:
            self.initialize()
        
        self._current_step = 0
        self._is_active = True
        self._completion_timer.start()
        
        self.step_changed.emit(self._current_step)
        self._update_progress()
        
        logger.info("Tutorial started")
    
    def resume_tutorial(self):
        """Setzt das Tutorial fort (von gespeichertem Stand)."""
        if not self._steps:
            self.initialize()
        
        self._is_active = True
        self._completion_timer.start()
        
        self.step_changed.emit(self._current_step)
        self._update_progress()
        
        logger.info(f"Tutorial resumed at step {self._current_step}")
    
    def next_step(self) -> bool:
        """
        Geht zum nächsten Schritt.
        
        Returns:
            True wenn erfolgreich, False wenn bereits am Ende
        """
        if self._current_step < len(self._steps) - 1:
            # Mark current step as completed
            if self.current_step:
                self.step_completed.emit(self.current_step.step_id)
            
            self._current_step += 1
            self._save_progress()
            
            self.step_changed.emit(self._current_step)
            self._update_progress()
            
            logger.debug(f"Advanced to step {self._current_step}")
            return True
        else:
            # Tutorial completed
            self.complete_tutorial()
            return False
    
    def previous_step(self) -> bool:
        """
        Geht zum vorherigen Schritt.
        
        Returns:
            True wenn erfolgreich, False wenn bereits am Anfang
        """
        if self._current_step > 0:
            self._current_step -= 1
            self._save_progress()
            
            self.step_changed.emit(self._current_step)
            self._update_progress()
            
            logger.debug(f"Returned to step {self._current_step}")
            return True
        return False
    
    def go_to_step(self, step_id: str) -> bool:
        """
        Springt zu einem bestimmten Schritt.
        
        Args:
            step_id: Die ID des Zielschritts
            
        Returns:
            True wenn Schritt gefunden, False sonst
        """
        for i, step in enumerate(self._steps):
            if step.step_id == step_id:
                self._current_step = i
                self._save_progress()
                
                self.step_changed.emit(self._current_step)
                self._update_progress()
                
                logger.debug(f"Jumped to step {step_id}")
                return True
        return False
    
    def complete_tutorial(self):
        """Markiert das Tutorial als abgeschlossen."""
        self._is_active = False
        self._completion_timer.stop()
        
        # Save completion state
        settings = QSettings("MashCAD", "Tutorial")
        settings.setValue(self.COMPLETED_KEY, True)
        settings.sync()
        
        self.tutorial_completed.emit()
        logger.info("Tutorial completed!")
    
    def skip_tutorial(self):
        """Überspringt das Tutorial (kann später fortgesetzt werden)."""
        self._is_active = False
        self._completion_timer.stop()
        self._save_progress()
        
        logger.info("Tutorial skipped")
    
    def reset_tutorial(self):
        """Setzt das Tutorial zurück (für Testing oder Neustart)."""
        self._current_step = 0
        self._is_active = False
        self._completion_timer.stop()
        
        # Clear saved progress
        settings = QSettings("MashCAD", "Tutorial")
        settings.remove(self.SETTINGS_KEY)
        settings.remove(self.COMPLETED_KEY)
        settings.sync()
        
        logger.info("Tutorial reset")
    
    def is_completed(self) -> bool:
        """Prüft ob das Tutorial bereits abgeschlossen wurde."""
        settings = QSettings("MashCAD", "Tutorial")
        return settings.value(self.COMPLETED_KEY, False, type=bool)
    
    def get_progress(self) -> int:
        """
        Gibt den Fortschritt in Prozent zurück.
        
        Returns:
            0-100 Prozent
        """
        if not self._steps:
            return 0
        return int((self._current_step + 1) / len(self._steps) * 100)
    
    def _update_progress(self):
        """Aktualisiert den Fortschritt."""
        progress = self.get_progress()
        self.progress_updated.emit(progress)
    
    def _check_step_completion(self):
        """Prüft periodisch ob der aktuelle Schritt abgeschlossen ist."""
        if not self._is_active or not self.current_step:
            return
        
        if self.current_step.auto_advance and self.current_step.is_completed():
            logger.debug(f"Step {self.current_step.step_id} auto-completed")
            self.next_step()
    
    def _save_progress(self):
        """Speichert den aktuellen Fortschritt."""
        settings = QSettings("MashCAD", "Tutorial")
        settings.setValue(self.SETTINGS_KEY, self._current_step)
        settings.sync()
    
    def _load_progress(self):
        """Lädt den gespeicherten Fortschritt."""
        settings = QSettings("MashCAD", "Tutorial")
        self._current_step = settings.value(self.SETTINGS_KEY, 0, type=int)


# Singleton-Instanz
_tutorial_manager: Optional[TutorialManager] = None


def get_tutorial_manager(main_window=None) -> TutorialManager:
    """
    Gibt die Singleton-Instanz des TutorialManagers zurück.
    
    Args:
        main_window: Optional das MainWindow (nur beim ersten Aufruf nötig)
        
    Returns:
        TutorialManager Instanz
    """
    global _tutorial_manager
    if _tutorial_manager is None:
        _tutorial_manager = TutorialManager(main_window)
    return _tutorial_manager


def reset_tutorial_manager():
    """Setzt die Singleton-Instanz zurück (für Tests)."""
    global _tutorial_manager
    if _tutorial_manager:
        _tutorial_manager._completion_timer.stop()
    _tutorial_manager = None
