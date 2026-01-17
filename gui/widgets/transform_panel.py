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


class TransformInputPanel(QFrame):
    """
    Kompaktes Panel für Transform-Eingabe.
    Zeigt aktuelle Werte und erlaubt numerische Eingabe.
    
    Erscheint automatisch wenn Body selektiert wird.
    """
    
    # Signale
    transform_confirmed = Signal(str, object)  # mode, data
    transform_cancelled = Signal()
    mode_changed = Signal(str)  # "move", "rotate", "scale"
    grid_size_changed = Signal(float)  # grid_size in mm
    pivot_mode_changed = Signal(str)  # "center", "origin", "cursor"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_mode = "move"
        self.setFrameShape(QFrame.StyledPanel)
        self._setup_ui()
        self._connect_signals()
        
    def _setup_ui(self):
        """Erstellt die UI - Styling wie Extrude-Panel"""
        self.setMinimumHeight(60)
        self.setMinimumWidth(600) 
        self.setMaximumWidth(900)
        self.setFixedHeight(60)
        self.setStyleSheet("""
            QFrame {
                background-color: #2d2d30;
                border: 2px solid #0078d4;
                border-radius: 8px;
            }
            QLabel {
                color: #ffffff;
                font-weight: bold;
                border: none;
                font-size: 12px;
                background: transparent; /* Wichtig gegen Grafikfehler */
            }
            QLineEdit {
                background: #1e1e1e;
                color: #fff;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
                font-weight: bold;
                min-width: 70px; /* Etwas schmaler damit 3 passen */
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #0078d4;
            }
            QPushButton {
                background: #444;
                color: #fff;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 5px 12px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #555;
                border-color: #777;
            }
            QComboBox {
                background: #1e1e1e;
                border: 1px solid #555;
                border-radius: 4px;
                color: #fff;
                padding: 4px;
                min-width: 90px;
            }
        """)
        
        # Alles in EINER Zeile (QHBoxLayout)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 5, 15, 5)
        layout.setSpacing(12)
        
        
        # Mode Auswahl
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Move", "Rotate", "Scale"])
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

        # Grid-Size Konfiguration (Snap to Grid)
        grid_label = QLabel("Grid:")
        grid_label.setToolTip("Grid-Größe für Snap (Ctrl-Taste während Drag)")
        layout.addWidget(grid_label)

        self.grid_size_combo = QComboBox()
        self.grid_size_combo.addItems(["0.1mm", "0.5mm", "1mm", "5mm", "10mm"])
        self.grid_size_combo.setCurrentText("1mm")
        self.grid_size_combo.setToolTip("Ctrl+Drag für Snap-to-Grid")
        self.grid_size_combo.currentTextChanged.connect(self._on_grid_size_changed)
        layout.addWidget(self.grid_size_combo)

        # Separator
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.VLine)
        sep3.setStyleSheet("background-color: #555;")
        layout.addWidget(sep3)

        # Pivot-Point Konfiguration
        pivot_label = QLabel("Pivot:")
        pivot_label.setToolTip("Pivot-Punkt für Rotation und Skalierung")
        layout.addWidget(pivot_label)

        self.pivot_mode_combo = QComboBox()
        self.pivot_mode_combo.addItems(["Body Center", "World Origin", "Cursor"])
        self.pivot_mode_combo.setCurrentText("Body Center")
        self.pivot_mode_combo.setToolTip("Wähle Pivot-Punkt")
        self.pivot_mode_combo.currentTextChanged.connect(self._on_pivot_mode_changed)
        layout.addWidget(self.pivot_mode_combo)

        # Separator
        sep4 = QFrame()
        sep4.setFrameShape(QFrame.VLine)
        sep4.setStyleSheet("background-color: #555;")
        layout.addWidget(sep4)

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

    def _on_grid_size_changed(self, text: str):
        """Handler für Grid-Size Änderung"""
        # Parse Grid-Size (z.B. "1mm" → 1.0)
        try:
            size_str = text.replace("mm", "").strip()
            grid_size = float(size_str)
            logger.info(f"Grid-Size geändert: {grid_size}mm")

            # Emittiere Signal für MainWindow
            self.grid_size_changed.emit(grid_size)
        except ValueError:
            logger.warning(f"Ungültige Grid-Size: {text}")

    def get_grid_size(self) -> float:
        """Gibt aktuelle Grid-Size zurück"""
        text = self.grid_size_combo.currentText()
        size_str = text.replace("mm", "").strip()
        try:
            return float(size_str)
        except ValueError:
            return 1.0  # Default

    def _on_pivot_mode_changed(self, text: str):
        """Handler für Pivot-Mode Änderung"""
        # Map UI-Text zu internem Modus
        mode_map = {
            "Body Center": "center",
            "World Origin": "origin",
            "Cursor": "cursor"
        }
        mode = mode_map.get(text, "center")
        logger.info(f"Pivot-Mode geändert: {mode}")

        # Emittiere Signal für MainWindow
        self.pivot_mode_changed.emit(mode)

    def get_pivot_mode(self) -> str:
        """Gibt aktuellen Pivot-Mode zurück"""
        text = self.pivot_mode_combo.currentText()
        mode_map = {
            "Body Center": "center",
            "World Origin": "origin",
            "Cursor": "cursor"
        }
        return mode_map.get(text, "center")

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


class SelectionInfoWidget(QFrame): # QFrame statt QWidget für Styling
    """Overlay Badge im Viewport"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        
    def _setup_ui(self):
        # Design als schwebende "Pille"
        self.setFixedHeight(32)
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 30, 0.9); /* Halb-transparent */
                border: 1px solid #444;
                border-radius: 16px; /* Pillenform */
            }
            QLabel {
                color: #e0e0e0;
                font-size: 12px;
                background: transparent;
                border: none;
                padding: 0 5px;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        
        self.icon_label = QLabel("📦")
        layout.addWidget(self.icon_label)
        
        self.name_label = QLabel("Selection")
        layout.addWidget(self.name_label)
        
    def set_selection(self, name, count=1):
        if name:
            text = name if count <= 1 else f"{name} (+{count-1})"
            self.name_label.setText(text)
            self.adjustSize()
            self.show()
            self._center_in_parent() # Automatisch positionieren
        else:
            self.hide()
            
    def _center_in_parent(self):
        """Zentriert das Widget oben im Parent (Viewport)"""
        if self.parent():
            # 20px Abstand von oben, mittig zentriert
            x = (self.parent().width() - self.width()) // 2
            self.move(x, 20)
            self.raise_() # In den Vordergrund
            
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
