"""
MashCad - Transform Input Panel
Zeigt aktuelle Transform-Werte und ermöglicht numerische Eingabe
Ähnlich dem Precision-Input im Sketch-Editor
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFrame, QComboBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator, QKeyEvent
from loguru import logger


class TransformInputPanel(QWidget):
    """
    Kompaktes Panel für Transform-Eingabe.
    Zeigt aktuelle Werte und erlaubt numerische Eingabe.
    
    Erscheint automatisch wenn Body selektiert wird.
    """
    
    # Signale
    transform_confirmed = Signal(str, object)  # mode, data
    transform_cancelled = Signal()
    mode_changed = Signal(str)  # "move", "rotate", "scale"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_mode = "move"
        self._setup_ui()
        self._connect_signals()
        
    def _setup_ui(self):
        """Erstellt die UI"""
        self.setMinimumHeight(55)
        self.setMinimumWidth(700)
        self.setStyleSheet("""
            QWidget {
                background-color: #2d2d30;
                color: #e0e0e0;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #3c3c3c;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 5px 8px;
                min-width: 70px;
                max-width: 90px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #0078d4;
            }
            QPushButton {
                background-color: #0078d4;
                border: none;
                border-radius: 3px;
                padding: 6px 15px;
                min-width: 70px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1084d8;
            }
            QPushButton#cancelBtn {
                background-color: #555;
            }
            QPushButton#cancelBtn:hover {
                background-color: #666;
            }
            QComboBox {
                background-color: #3c3c3c;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 5px 10px;
                min-width: 90px;
                font-size: 12px;
            }
            QLabel {
                color: #aaa;
                font-size: 12px;
            }
            QLabel#modeLabel {
                font-weight: bold;
                color: #e0e0e0;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)
        
        # Mode-Auswahl
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Move", "Rotate", "Scale"])
        self.mode_combo.setToolTip("Transform-Modus (G/R/S)")
        layout.addWidget(self.mode_combo)
        
        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet("background-color: #555;")
        layout.addWidget(sep1)
        
        # X-Eingabe
        self.x_label = QLabel("X:")
        self.x_label.setStyleSheet("color: #E63946; font-weight: bold;")
        layout.addWidget(self.x_label)
        
        self.x_input = QLineEdit("0.0")
        self.x_input.setValidator(QDoubleValidator(-99999, 99999, 3))
        self.x_input.setAlignment(Qt.AlignRight)
        layout.addWidget(self.x_input)
        
        # Y-Eingabe
        self.y_label = QLabel("Y:")
        self.y_label.setStyleSheet("color: #2A9D8F; font-weight: bold;")
        layout.addWidget(self.y_label)
        
        self.y_input = QLineEdit("0.0")
        self.y_input.setValidator(QDoubleValidator(-99999, 99999, 3))
        self.y_input.setAlignment(Qt.AlignRight)
        layout.addWidget(self.y_input)
        
        # Z-Eingabe
        self.z_label = QLabel("Z:")
        self.z_label.setStyleSheet("color: #457B9D; font-weight: bold;")
        layout.addWidget(self.z_label)
        
        self.z_input = QLineEdit("0.0")
        self.z_input.setValidator(QDoubleValidator(-99999, 99999, 3))
        self.z_input.setAlignment(Qt.AlignRight)
        layout.addWidget(self.z_input)
        
        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("background-color: #555;")
        layout.addWidget(sep2)
        
        # Buttons
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setToolTip("Transform anwenden (Enter)")
        layout.addWidget(self.apply_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setToolTip("Abbrechen (Esc)")
        layout.addWidget(self.cancel_btn)
        
        # Hilfe-Label
        self.help_label = QLabel("Tab: Nächstes Feld | Enter: Anwenden | Esc: Abbrechen")
        self.help_label.setStyleSheet("color: #777; font-size: 10px;")
        layout.addWidget(self.help_label)
        
        layout.addStretch()
        
    def _connect_signals(self):
        """Verbindet Signale"""
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self.apply_btn.clicked.connect(self._on_apply)
        self.cancel_btn.clicked.connect(self._on_cancel)
        
        # Enter in Eingabefeldern
        for inp in [self.x_input, self.y_input, self.z_input]:
            inp.returnPressed.connect(self._on_apply)
            
    def _on_mode_changed(self, mode_text: str):
        """Handler für Mode-Änderung"""
        mode = mode_text.lower()
        self.current_mode = mode
        self.mode_changed.emit(mode)
        self._update_labels()
        self.reset_values()
        
    def _update_labels(self):
        """Aktualisiert Labels basierend auf Modus"""
        if self.current_mode == "move":
            self.x_label.setText("ΔX:")
            self.y_label.setText("ΔY:")
            self.z_label.setText("ΔZ:")
        elif self.current_mode == "rotate":
            self.x_label.setText("Rx:")
            self.y_label.setText("Ry:")
            self.z_label.setText("Rz:")
        elif self.current_mode == "scale":
            self.x_label.setText("Sx:")
            self.y_label.setText("Sy:")
            self.z_label.setText("Sz:")
            
    def _on_apply(self):
        """Wendet Transform an"""
        try:
            x = float(self.x_input.text() or "0")
            y = float(self.y_input.text() or "0")
            z = float(self.z_input.text() or "0")
            
            if self.current_mode == "move":
                data = [x, y, z]
            elif self.current_mode == "rotate":
                # Für Rotate: Wir nehmen die Achse mit dem größten Wert
                if abs(x) >= abs(y) and abs(x) >= abs(z):
                    data = {"axis": "X", "angle": x}
                elif abs(y) >= abs(x) and abs(y) >= abs(z):
                    data = {"axis": "Y", "angle": y}
                else:
                    data = {"axis": "Z", "angle": z}
            elif self.current_mode == "scale":
                # Uniform Scale (Durchschnitt)
                avg = (x + y + z) / 3 if (x + y + z) != 0 else 1.0
                data = {"factor": avg if avg > 0 else 1.0}
            else:
                data = [x, y, z]
                
            self.transform_confirmed.emit(self.current_mode, data)
            
        except ValueError as e:
            logger.warning(f"Ungültige Eingabe: {e}")
            
    def _on_cancel(self):
        """Bricht Transform ab"""
        self.transform_cancelled.emit()
        self.reset_values()
        
    def reset_values(self):
        """Setzt alle Werte zurück"""
        default = "0.0" if self.current_mode != "scale" else "1.0"
        self.x_input.setText(default)
        self.y_input.setText(default)
        self.z_input.setText(default)
        
    def set_values(self, x: float, y: float, z: float):
        """Setzt die angezeigten Werte (für Live-Update während Drag)"""
        self.x_input.setText(f"{x:.2f}")
        self.y_input.setText(f"{y:.2f}")
        self.z_input.setText(f"{z:.2f}")
        
    def set_mode(self, mode: str):
        """Setzt den Modus programmatisch"""
        mode_map = {"move": 0, "rotate": 1, "scale": 2}
        if mode.lower() in mode_map:
            self.mode_combo.setCurrentIndex(mode_map[mode.lower()])
            
    def focus_input(self):
        """Fokussiert das X-Eingabefeld (für Tab-Aktivierung)"""
        self.x_input.setFocus()
        self.x_input.selectAll()
        
    def keyPressEvent(self, event: QKeyEvent):
        """Keyboard-Handler"""
        if event.key() == Qt.Key_Escape:
            self._on_cancel()
        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            self._on_apply()
        elif event.key() == Qt.Key_G:
            self.set_mode("move")
        elif event.key() == Qt.Key_R:
            self.set_mode("rotate")
        elif event.key() == Qt.Key_S:
            self.set_mode("scale")
        else:
            super().keyPressEvent(event)


class SelectionInfoWidget(QWidget):
    """
    Zeigt Info über die aktuelle Selektion.
    Erscheint oben links im Viewport.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        
    def _setup_ui(self):
        self.setFixedSize(200, 30)
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(45, 45, 48, 200);
                border-radius: 5px;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 11px;
                padding: 5px;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        
        self.icon_label = QLabel("🔲")
        layout.addWidget(self.icon_label)
        
        self.name_label = QLabel("Kein Body selektiert")
        layout.addWidget(self.name_label)
        
        layout.addStretch()
        
    def set_selection(self, body_name: str = None, body_count: int = 0):
        """Aktualisiert die Anzeige"""
        if body_name:
            self.icon_label.setText("📦")
            if body_count > 1:
                self.name_label.setText(f"{body_name} (+{body_count-1})")
            else:
                self.name_label.setText(body_name)
            self.show()
        else:
            self.icon_label.setText("🔲")
            self.name_label.setText("Kein Body selektiert")
            
    def clear_selection(self):
        """Leert die Selektion"""
        self.set_selection(None)


class CenterHintWidget(QWidget):
    """
    Großer, zentraler Hinweis-Text der automatisch ausgeblendet wird.
    Für wichtige Statusmeldungen wie "Wähle einen Body" oder "Move aktiv".
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._timer = None
        
    def _setup_ui(self):
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 120, 212, 220);
                border-radius: 10px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 20)
        
        self.icon_label = QLabel("🎯")
        self.icon_label.setStyleSheet("font-size: 32px; color: white;")
        self.icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.icon_label)
        
        self.main_label = QLabel("Hinweis")
        self.main_label.setStyleSheet("""
            font-size: 18px; 
            font-weight: bold; 
            color: white;
        """)
        self.main_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.main_label)
        
        self.sub_label = QLabel("")
        self.sub_label.setStyleSheet("font-size: 12px; color: rgba(255,255,255,180);")
        self.sub_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.sub_label)
        
        self.adjustSize()
        self.hide()
        
    def show_hint(self, main_text: str, sub_text: str = "", icon: str = "🎯", 
                  duration_ms: int = 3000, color: str = None):
        """
        Zeigt einen zentralen Hinweis.
        
        Args:
            main_text: Haupttext (groß)
            sub_text: Untertext (klein)
            icon: Emoji-Icon
            duration_ms: Anzeigedauer in ms (0 = dauerhaft)
            color: Hintergrundfarbe (optional)
        """
        self.icon_label.setText(icon)
        self.main_label.setText(main_text)
        self.sub_label.setText(sub_text)
        self.sub_label.setVisible(bool(sub_text))
        
        if color:
            self.setStyleSheet(f"""
                QWidget {{
                    background-color: {color};
                    border-radius: 10px;
                }}
            """)
        else:
            self.setStyleSheet("""
                QWidget {
                    background-color: rgba(0, 120, 212, 220);
                    border-radius: 10px;
                }
            """)
        
        self.adjustSize()
        
        # Zentrieren im Parent
        if self.parent():
            parent_rect = self.parent().rect()
            x = (parent_rect.width() - self.width()) // 2
            y = (parent_rect.height() - self.height()) // 2 - 50  # Etwas höher
            self.move(x, y)
        
        self.show()
        self.raise_()
        
        # Auto-Hide nach duration
        if duration_ms > 0:
            from PySide6.QtCore import QTimer
            if self._timer:
                self._timer.stop()
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self.hide)
            self._timer.start(duration_ms)
            
    def show_action_hint(self, action: str, details: str = ""):
        """Zeigt Hinweis für eine Aktion"""
        icons = {
            "select": "👆",
            "move": "↔️",
            "rotate": "🔄",
            "scale": "📐",
            "copy": "📋",
            "mirror": "🪞",
            "success": "✅",
            "error": "❌",
            "info": "ℹ️",
        }
        icon = icons.get(action.lower(), "🎯")
        self.show_hint(action, details, icon)
        
    def hide_hint(self):
        """Versteckt den Hinweis"""
        if self._timer:
            self._timer.stop()
        self.hide()
