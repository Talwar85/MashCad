"""
SketchController - UI-Orchestrierung für Sketch-Workflows
=========================================================

W16 Paket D: Extrahiert Sketch-bezogene UI-Orchestrierung aus MainWindow.
Zuständig für:
- Modus-Umschaltung zwischen 3D und Sketch
- Sketch-Enter/Exit Flows
- 3D-Peek (Space) während Sketch
- Sketch-Navigation Hints

Author: GLM 4.7 (UX/Workflow Delivery Cell)
Date: 2026-02-16
Branch: feature/v1-ux-aiB
"""

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QColor
from loguru import logger

from i18n import tr


class SketchController(QObject):
    """
    Controller für Sketch-bezogene UI-Orchestrierung.
    
    Kapselt den Zustandsübergang zwischen 3D-Modus und Sketch-Modus,
    inklusive Peek-3D Funktionalität und Navigation-Hints.
    """
    
    def __init__(self, main_window):
        """
        Args:
            main_window: MainWindow Instanz (für UI-Zugriff)
        """
        super().__init__(main_window)
        self._mw = main_window
        self._peek_3d_active = False
        self._active_sketch = None
        
    @property
    def peek_3d_active(self) -> bool:
        """True wenn 3D-Peek gerade aktiv ist."""
        return self._peek_3d_active
        
    @property
    def active_sketch(self):
        """Aktuell aktiver Sketch oder None."""
        return self._active_sketch
        
    def set_mode(self, mode: str, prev_mode: str = None):
        """
        Wechselt zwischen 3D- und Sketch-Modus.
        
        Args:
            mode: '3d' oder 'sketch'
            prev_mode: Vorheriger Modus (für Transitions-Logik)
        """
        if mode == "3d":
            self._enter_3d_mode()
        else:
            self._enter_sketch_mode(prev_mode)
            
    def _enter_3d_mode(self):
        """UI-Zustand für 3D-Modus einstellen."""
        mw = self._mw
        
        # Stack-Indizes
        mw.tool_stack.setCurrentIndex(0)  # 3D-ToolPanel
        mw.center_stack.setCurrentIndex(0)  # Viewport
        mw.right_stack.setVisible(False)
        
        # Transform-Toolbar
        if hasattr(mw, 'transform_toolbar'):
            mw.transform_toolbar.setVisible(True)
            
        # Status Bar
        if hasattr(mw, 'mashcad_status_bar'):
            mw.mashcad_status_bar.set_mode("3D")
            
    def _enter_sketch_mode(self, prev_mode: str):
        """UI-Zustand für Sketch-Modus einstellen."""
        mw = self._mw
        
        # Stack-Indizes
        mw.tool_stack.setCurrentIndex(1)  # 2D-ToolPanel
        mw.center_stack.setCurrentIndex(1)  # Sketch Editor
        mw.right_stack.setCurrentIndex(1)  # 2D Properties
        mw.right_stack.setVisible(True)
        
        # Transform-Toolbar
        if hasattr(mw, 'transform_toolbar'):
            mw.transform_toolbar.setVisible(False)
            
        # Fokus
        mw.sketch_editor.setFocus()
        
        # Status Bar
        if hasattr(mw, 'mashcad_status_bar'):
            mw.mashcad_status_bar.set_mode("2D")
            
        # Navigation-Hint bei Modus-Wechsel
        if prev_mode != "sketch":
            self._show_sketch_navigation_hint()
            
    def _show_sketch_navigation_hint(self):
        """Zeigt Navigation-Hinweis beim Eintritt in den Sketch-Modus."""
        mw = self._mw
        
        # Status Bar
        nav_hint = tr("Sketch-Navigation: Shift+R dreht Ansicht | Space halten fuer 3D-Peek")
        mw.statusBar().showMessage(nav_hint, 7000)
        
        # Sketch Editor HUD
        if hasattr(mw, "sketch_editor") and hasattr(mw.sketch_editor, "show_message"):
            mw.sketch_editor.show_message(
                tr("Shift+R Ansicht drehen | Space halten fuer 3D-Peek"),
                duration=2600,
                color=QColor(110, 180, 255),
            )
            
    def start_sketch(self, sketch):
        """
        Startet einen Sketch-Editing-Flow.
        
        Args:
            sketch: Sketch-Objekt zum Bearbeiten
        """
        self._active_sketch = sketch
        self.set_mode("sketch", prev_mode="3d")
        
    def finish_sketch(self):
        """Beendet den aktiven Sketch-Editing-Flow."""
        mw = self._mw
        
        # Body-Referenzen löschen
        if hasattr(mw.sketch_editor, 'set_reference_bodies'):
            mw.sketch_editor.set_reference_bodies([], (0,0,1), (0,0,0))
            
        # DOF-Anzeige ausblenden
        if hasattr(mw, 'mashcad_status_bar'):
            mw.mashcad_status_bar.set_dof(0, visible=False)
            
        self._active_sketch = None
        self.set_mode("3d", prev_mode="sketch")
        
        # Browser Refresh
        if hasattr(mw, 'browser'):
            mw.browser.refresh()
            
        # Viewport Update
        if hasattr(mw, '_trigger_viewport_update'):
            mw._trigger_viewport_update()
            
    def set_peek_3d(self, active: bool):
        """
        Aktiviert/Deaktiviert 3D-Peek während Sketch.
        
        Args:
            active: True für 3D-Viewport zeigen, False für zurück zu Sketch
        """
        mw = self._mw
        self._peek_3d_active = active
        
        if active:
            # Zeige 3D-Viewport
            mw.center_stack.setCurrentIndex(0)
            mw.statusBar().showMessage(tr("3D-Vorschau (Space loslassen für Sketch)"), 0)
            # Keyboard-Grab für Key-Events
            mw.grabKeyboard()
        else:
            # Zurück zum Sketch
            mw.center_stack.setCurrentIndex(1)
            mw.sketch_editor.setFocus()
            mw.statusBar().clearMessage()
            # Keyboard-Release
            mw.releaseKeyboard()
            
    def handle_key_release(self, event) -> bool:
        """
        Verarbeitet Key-Release Events für Peek-3D.
        
        Args:
            event: QKeyEvent
            
        Returns:
            bool: True wenn Event verarbeitet wurde
        """
        if self._peek_3d_active:
            if event.key() == Qt.Key_Space and not event.isAutoRepeat():
                self.set_peek_3d(False)
                return True
        return False
        
    def cleanup(self):
        """Räumt auf beim Beenden."""
        if self._peek_3d_active:
            self.set_peek_3d(False)
        self._active_sketch = None
