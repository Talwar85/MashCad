"""
MashCad - Input Panels
Fixed: TransformPanel Signal Blocking for circular updates.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QDoubleSpinBox, QCheckBox, QComboBox,
    QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QEvent, QPoint, QTimer
from PySide6.QtGui import QFont, QKeyEvent

# --- Hilfsklasse für Enter-Taste ---
class ActionSpinBox(QDoubleSpinBox):
    """Eine SpinBox, die Enter-Tasten verarbeitet"""
    enterPressed = Signal()
    escapePressed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.interpretText() 
            self.enterPressed.emit()
            event.accept()
            return
        if event.key() == Qt.Key_Escape:
            self.escapePressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)

class ExtrudeInputPanel(QFrame):
    """Input panel for extrude operation"""
    
    height_changed = Signal(float)
    direction_flipped = Signal()
    confirmed = Signal()
    cancelled = Signal()
    bodies_visibility_toggled = Signal(bool)
    operation_changed = Signal(str)  # NEU: Signal wenn Operation geändert wird
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._height = 0.0
        self._bodies_hidden = False
        self._direction = 1  # 1 or -1
        self._current_operation = "New Body"
        self.setMinimumWidth(520)
        self.setFixedHeight(60)
        
        self.setStyleSheet("""
            QFrame {
                background-color: #2d2d30;
                border: 2px solid #0078d4;
                border-radius: 8px;
            }
            QLabel { color: #ffffff; font-weight: bold; border: none; font-size: 12px; }
            QComboBox {
                background: #1e1e1e; border: 1px solid #555;
                border-radius: 4px; color: #fff; padding: 4px; min-width: 90px;
            }
            QDoubleSpinBox {
                background: #1e1e1e; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 4px; font-weight: bold; min-width: 90px; font-size: 13px;
            }
            QPushButton {
                background: #444; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 5px 12px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background: #555; border-color: #777; }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 5, 15, 5)
        layout.setSpacing(12)
        
        self.label = QLabel("Extrude:")
        layout.addWidget(self.label)
        
        self.height_input = ActionSpinBox()
        self.height_input.setRange(-99999.0, 99999.0)
        self.height_input.setDecimals(2)
        self.height_input.setSuffix(" mm")
        self.height_input.setValue(0.0)
        
        self.height_input.valueChanged.connect(self._on_height_changed)
        self.height_input.enterPressed.connect(self._confirm)
        self.height_input.escapePressed.connect(self.cancelled.emit)
        
        layout.addWidget(self.height_input)
        
        # Operation mit Farb-Indikator
        self.op_indicator = QLabel("●")
        self.op_indicator.setFixedWidth(20)
        self.op_indicator.setStyleSheet("color: #6699ff; font-size: 16px;")
        layout.addWidget(self.op_indicator)
        
        self.op_combo = QComboBox()
        self.op_combo.addItems(["New Body", "Join", "Cut", "Intersect"])
        self.op_combo.currentTextChanged.connect(self._on_operation_changed)
        layout.addWidget(self.op_combo)

        # Flip Direction Button
        self.flip_btn = QPushButton("⇅")
        self.flip_btn.setToolTip("Richtung umkehren (F)")
        self.flip_btn.setFixedSize(32, 32)
        self.flip_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                border: 1px solid #4a4a4a;
                border-radius: 3px;
                color: #ccc;
                font-size: 16px;
            }
            QPushButton:hover {
                background: #4a4a4a;
                color: #fff;
            }
            QPushButton:pressed {
                background: #0078d4;
            }
        """)
        self.flip_btn.clicked.connect(self._flip_direction)
        layout.addWidget(self.flip_btn)
        
        
        self.btn_vis = QPushButton("👁")
        self.btn_vis.setCheckable(True)
        self.btn_vis.setFixedWidth(35)
        self.btn_vis.clicked.connect(self._toggle_vis)
        layout.addWidget(self.btn_vis)
        
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setStyleSheet("background: #0078d4; color: white; border: none;")
        self.btn_ok.clicked.connect(self._confirm)
        layout.addWidget(self.btn_ok)
        
        self.btn_cancel = QPushButton("X")
        self.btn_cancel.setFixedWidth(35)
        self.btn_cancel.setStyleSheet("background: #d83b01; color: white; border: none;")
        self.btn_cancel.clicked.connect(self.cancelled.emit)
        layout.addWidget(self.btn_cancel)
        
        self.hide()
        
    def _on_operation_changed(self, op_text):
        """Aktualisiert Farb-Indikator und emittiert Signal"""
        self._current_operation = op_text
        colors = {
            "New Body": "#6699ff",  # Blau
            "Join": "#66ff66",      # Grün
            "Cut": "#ff6666",       # Rot
            "Intersect": "#ffaa66"  # Orange
        }
        self.op_indicator.setStyleSheet(f"color: {colors.get(op_text, '#6699ff')}; font-size: 16px;")

        # Tooltip-Warnung für Boolean Operations
        if op_text in ["Join", "Cut", "Intersect"]:
            self.op_combo.setToolTip(
                f"⚠️ {op_text}: Boolean Operations können bei komplexen Geometrien fehlschlagen.\n"
                f"Tipp: 'New Body' ist sicherer - Bodies können später manuell kombiniert werden."
            )
        else:
            self.op_combo.setToolTip("Erstellt einen neuen unabhängigen Body (empfohlen)")

        self.operation_changed.emit(op_text)
        
    def set_suggested_operation(self, operation: str):
        """Setzt die vorgeschlagene Operation automatisch"""
        idx = self.op_combo.findText(operation)
        if idx >= 0:
            self.op_combo.setCurrentIndex(idx)
            
    def get_operation_color(self) -> str:
        """Gibt die Farbe für die aktuelle Operation zurück"""
        colors = {
            "New Body": "#6699ff",
            "Join": "#66ff66", 
            "Cut": "#ff6666",
            "Intersect": "#ffaa66"
        }
        return colors.get(self._current_operation, "#6699ff")

    def set_height(self, h):
        """Setzt den Wert von außen (z.B. durch Ziehen im Viewport)"""
        self.height_input.blockSignals(True)
        self.height_input.setValue(h)
        self.height_input.blockSignals(False)
        self._height = h
        # Richtungssymbol basierend auf Vorzeichen aktualisieren
        self._direction = 1 if h >= 0 else -1

    def get_height(self):
        return self.height_input.value()

    def get_operation(self) -> str:
        return self.op_combo.currentText()
    
    def _flip_direction(self):
        """Invertiert das Vorzeichen des aktuellen Wertes"""
        current_val = self.height_input.value()
        new_val = current_val * -1
        
        # Wir setzen den Wert direkt über die SpinBox, 
        # das löst automatisch _on_height_changed aus.
        self.height_input.setValue(new_val)
        
        # Optional: Signal explizit feuern, falls man sichergehen will
        self.direction_flipped.emit()
        
        
    def reset(self):
        self._height = 0.0
        self.height_input.blockSignals(True)
        self.height_input.setValue(0.0)
        self.height_input.blockSignals(False)
        self.op_combo.setCurrentIndex(0)
        self.btn_vis.setChecked(False)

    def _on_height_changed(self, val):
        self._height = val
        self.height_changed.emit(val)
        
    def _confirm(self):
        # Wir holen den aktuellen Wert direkt aus der Spinbox
        self._height = self.height_input.value()
        # Nur bestätigen, wenn wirklich Geometrie entstehen kann (> 0.001mm)
        if abs(self._height) > 0.001:
            self.confirmed.emit()
        else:
            self.cancelled.emit()

    def _toggle_vis(self):
        self._bodies_hidden = self.btn_vis.isChecked()
        self.bodies_visibility_toggled.emit(self._bodies_hidden)

    def show_at(self, pos_widget):
        self.show()
        self.raise_()
        if pos_widget:
            parent = pos_widget.parent() if pos_widget.parent() else pos_widget
            x = (parent.width() - self.width()) // 2
            y = parent.height() - self.height() - 50 
            self.move(x, y)
            self.height_input.setFocus()
            self.height_input.selectAll()


class FilletChamferPanel(QFrame):
    """Input panel for Fillet/Chamfer operations"""
    
    radius_changed = Signal(float)
    confirmed = Signal()
    cancelled = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._radius = 2.0
        self._mode = "fillet"
        self._target_body = None 
        
        self.setMinimumWidth(350)
        self.setFixedHeight(60)

        self.setStyleSheet("""
            QFrame {
                background: #2d2d30;
                border: 2px solid #0078d4;
                border-radius: 8px;
            }
            QLabel { color: #fff; font-weight: bold; border: none; font-size: 12px; }
            QDoubleSpinBox {
                background: #1e1e1e; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 4px; font-weight: bold; font-size: 13px;
            }
            QPushButton {
                background: #444; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 5px; font-weight: bold;
            }
            QPushButton:hover { background: #555; }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 5, 15, 5)
        layout.setSpacing(10)
        
        self.label = QLabel("Fillet:")
        layout.addWidget(self.label)
        
        self.radius_input = ActionSpinBox()
        self.radius_input.setRange(0.1, 1000.0)
        self.radius_input.setDecimals(2)
        self.radius_input.setSuffix(" mm")
        self.radius_input.setValue(2.0)
        
        self.radius_input.valueChanged.connect(self._on_value_changed)
        self.radius_input.enterPressed.connect(self._confirm)
        self.radius_input.escapePressed.connect(self._cancel)
            
        layout.addWidget(self.radius_input)
        
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setStyleSheet("background: #0078d4; border: none;")
        self.ok_btn.clicked.connect(self._confirm)
        layout.addWidget(self.ok_btn)
        
        self.cancel_btn = QPushButton("X")
        self.cancel_btn.setFixedWidth(30)
        self.cancel_btn.setStyleSheet("background: #d83b01; border: none;")
        self.cancel_btn.clicked.connect(self._cancel)
        layout.addWidget(self.cancel_btn)
        
        self.hide()
    
    def set_target_body(self, body):
        self._target_body = body

    def get_target_body(self):
        return self._target_body

    def set_mode(self, mode: str):
        self._mode = mode
        self.label.setText("Fillet:" if mode == "fillet" else "Chamfer:")
    
    def _on_value_changed(self, value):
        self._radius = value
        self.radius_changed.emit(value)
    
    def _confirm(self):
        self._radius = self.radius_input.value()
        self.confirmed.emit()
    
    def _cancel(self):
        self.cancelled.emit()
    
    def get_radius(self) -> float:
        return self.radius_input.value()
    
    def reset(self):
        self._radius = 2.0
        self.radius_input.blockSignals(True)
        self.radius_input.setValue(2.0)
        self.radius_input.blockSignals(False)
    
    def show_at(self, pos_widget):
        self.show()
        self.raise_()
        
        if pos_widget:
            # Position relativ zum Parent (dem Hauptfenster) berechnen
            parent = pos_widget.parent() if pos_widget.parent() else pos_widget
            
            # X mittig zentrieren
            x = (parent.width() - self.width()) // 2
            
            # Y unten positionieren (mit 50px Abstand vom Rand)
            y = parent.height() - self.height() - 50 
            
            # Sicherheitscheck, damit es nicht oben raus rutscht
            if y < 0: y = 50
            
            self.move(x, y)
            
            # Fokus auf das Eingabefeld setzen (falls vorhanden)
            if hasattr(self, 'height_input'):
                self.height_input.setFocus()
                self.height_input.selectAll()
            elif hasattr(self, 'radius_input'):
                self.radius_input.setFocus()
                self.radius_input.selectAll()
            
            
class TransformPanel(QFrame):
    """
    Einzeiliges Transform-Panel für Move, Rotate, Scale.
    Design identisch zum ExtrudeInputPanel.
    """

    # Signale
    transform_confirmed = Signal(str, object)  # mode, data
    transform_cancelled = Signal()
    mode_changed = Signal(str)  # "move", "rotate", "scale"
    grid_size_changed = Signal(float)
    pivot_mode_changed = Signal(str)

    # Legacy-Signale für Kompatibilität
    values_changed = Signal(float, float, float)  # x, y, z
    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "move"
        self._ignore_signals = False

        self.setMinimumWidth(520)
        self.setFixedHeight(60)

        self.setStyleSheet("""
            QFrame {
                background-color: #2d2d30;
                border: 2px solid #0078d4;
                border-radius: 8px;
            }
            QLabel { color: #ffffff; font-weight: bold; border: none; font-size: 12px; }
            QComboBox {
                background: #1e1e1e; border: 1px solid #555;
                border-radius: 4px; color: #fff; padding: 4px; min-width: 70px;
            }
            QDoubleSpinBox {
                background: #1e1e1e; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 4px; font-weight: bold; min-width: 70px; font-size: 13px;
            }
            QPushButton {
                background: #444; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 5px 12px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background: #555; border-color: #777; }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 5, 15, 5)
        layout.setSpacing(10)

        # Mode-Auswahl
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Move", "Rotate", "Scale"])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        layout.addWidget(self.mode_combo)

        # X Input
        self.x_label = QLabel("X:")
        self.x_label.setStyleSheet("color: #E63946;")
        layout.addWidget(self.x_label)

        self.x_input = ActionSpinBox()
        self.x_input.setRange(-99999, 99999)
        self.x_input.setDecimals(2)
        self.x_input.setValue(0.0)
        self.x_input.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.x_input.enterPressed.connect(self._on_confirm)
        self.x_input.escapePressed.connect(self._on_cancel)
        self.x_input.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self.x_input)

        # Y Input
        self.y_label = QLabel("Y:")
        self.y_label.setStyleSheet("color: #2A9D8F;")
        layout.addWidget(self.y_label)

        self.y_input = ActionSpinBox()
        self.y_input.setRange(-99999, 99999)
        self.y_input.setDecimals(2)
        self.y_input.setValue(0.0)
        self.y_input.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.y_input.enterPressed.connect(self._on_confirm)
        self.y_input.escapePressed.connect(self._on_cancel)
        self.y_input.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self.y_input)

        # Z Input
        self.z_label = QLabel("Z:")
        self.z_label.setStyleSheet("color: #457B9D;")
        layout.addWidget(self.z_label)

        self.z_input = ActionSpinBox()
        self.z_input.setRange(-99999, 99999)
        self.z_input.setDecimals(2)
        self.z_input.setValue(0.0)
        self.z_input.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.z_input.enterPressed.connect(self._on_confirm)
        self.z_input.escapePressed.connect(self._on_cancel)
        self.z_input.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self.z_input)

        # Grid-Size
        self.grid_combo = QComboBox()
        self.grid_combo.addItems(["0.1", "0.5", "1", "5", "10"])
        self.grid_combo.setCurrentText("1")
        self.grid_combo.setToolTip("Grid (Ctrl+Drag)")
        self.grid_combo.currentTextChanged.connect(self._on_grid_changed)
        layout.addWidget(self.grid_combo)

        grid_unit = QLabel("mm")
        grid_unit.setStyleSheet("color: #888;")
        layout.addWidget(grid_unit)

        # OK Button
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setStyleSheet("background: #0078d4; color: white; border: none;")
        self.btn_ok.clicked.connect(self._on_confirm)
        layout.addWidget(self.btn_ok)

        # Cancel Button
        self.btn_cancel = QPushButton("X")
        self.btn_cancel.setFixedWidth(35)
        self.btn_cancel.setStyleSheet("background: #d83b01; color: white; border: none;")
        self.btn_cancel.clicked.connect(self._on_cancel)
        layout.addWidget(self.btn_cancel)

        self.hide()

    def _on_mode_changed(self, text: str):
        """Mode-Wechsel"""
        mode = text.lower()
        self._mode = mode
        self._update_labels()
        self.reset_values()
        self.mode_changed.emit(mode)

    def _update_labels(self):
        """Labels je nach Modus anpassen"""
        if self._mode == "move":
            self.x_label.setText("ΔX:")
            self.y_label.setText("ΔY:")
            self.z_label.setText("ΔZ:")
        elif self._mode == "rotate":
            self.x_label.setText("Rx:")
            self.y_label.setText("Ry:")
            self.z_label.setText("Rz:")
        elif self._mode == "scale":
            self.x_label.setText("Sx:")
            self.y_label.setText("Sy:")
            self.z_label.setText("Sz:")

    def _on_confirm(self):
        """Transform bestätigen"""
        x = self.x_input.value()
        y = self.y_input.value()
        z = self.z_input.value()

        if self._mode == "move":
            data = [x, y, z]
        elif self._mode == "rotate":
            # Achse mit größtem Wert nehmen
            if abs(x) >= abs(y) and abs(x) >= abs(z):
                data = {"axis": "X", "angle": x}
            elif abs(y) >= abs(x) and abs(y) >= abs(z):
                data = {"axis": "Y", "angle": y}
            else:
                data = {"axis": "Z", "angle": z}
        elif self._mode == "scale":
            avg = (x + y + z) / 3 if (x + y + z) != 0 else 1.0
            data = {"factor": avg if avg > 0 else 1.0}
        else:
            data = [x, y, z]

        self.transform_confirmed.emit(self._mode, data)
        self.confirmed.emit()  # Legacy-Signal

    def _on_cancel(self):
        """Transform abbrechen"""
        self.transform_cancelled.emit()
        self.cancelled.emit()  # Legacy-Signal
        self.reset_values()

    def _on_value_changed(self):
        """Wird aufgerufen wenn ein Wert geändert wird"""
        if not self._ignore_signals:
            x = self.x_input.value()
            y = self.y_input.value()
            z = self.z_input.value()
            self.values_changed.emit(x, y, z)

    def _on_grid_changed(self, text: str):
        """Grid-Size geändert"""
        try:
            size = float(text)
            self.grid_size_changed.emit(size)
        except ValueError:
            pass

    def get_grid_size(self) -> float:
        """Aktuelle Grid-Size"""
        try:
            return float(self.grid_combo.currentText())
        except ValueError:
            return 1.0

    def reset_values(self):
        """Werte zurücksetzen"""
        default = 1.0 if self._mode == "scale" else 0.0
        self._ignore_signals = True
        for inp in [self.x_input, self.y_input, self.z_input]:
            inp.blockSignals(True)
            inp.setValue(default)
            inp.blockSignals(False)
        self._ignore_signals = False

    def set_values(self, x: float, y: float, z: float):
        """Werte setzen (für Live-Update während Drag)"""
        self._ignore_signals = True
        self.x_input.blockSignals(True)
        self.x_input.setValue(x)
        self.x_input.blockSignals(False)
        self.y_input.blockSignals(True)
        self.y_input.setValue(y)
        self.y_input.blockSignals(False)
        self.z_input.blockSignals(True)
        self.z_input.setValue(z)
        self.z_input.blockSignals(False)
        self._ignore_signals = False

    def update_values(self, x: float, y: float, z: float):
        """Alias für set_values (Legacy-Kompatibilität)"""
        self.set_values(x, y, z)

    def get_values(self):
        """Gibt aktuelle Werte als Liste zurück"""
        return [self.x_input.value(), self.y_input.value(), self.z_input.value()]

    def set_mode(self, mode: str):
        """Mode programmatisch setzen"""
        mode_map = {"move": 0, "rotate": 1, "scale": 2}
        if mode.lower() in mode_map:
            self.mode_combo.setCurrentIndex(mode_map[mode.lower()])

    def focus_input(self):
        """X-Input fokussieren"""
        self.x_input.setFocus()
        self.x_input.selectAll()

    def show_at(self, pos_widget):
        """Panel anzeigen und positionieren"""
        self.show()
        self.raise_()

        if pos_widget:
            parent = pos_widget.parent() if pos_widget.parent() else pos_widget
            x = (parent.width() - self.width()) // 2
            y = parent.height() - self.height() - 40
            if y < 0:
                y = 50
            self.move(x, y)
            self.x_input.setFocus()
            self.x_input.selectAll()


class CenterHintWidget(QWidget):
    """
    Großer, zentraler Hinweis-Text der automatisch ausgeblendet wird.
    Für wichtige Statusmeldungen wie "Wähle einen Body" oder "Move aktiv".
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = None
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(0, 120, 212, 220);
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 20)

        self.icon_label = QLabel()
        self.icon_label.setStyleSheet("font-size: 32px; color: white;")
        self.icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.icon_label)

        self.main_label = QLabel("Hinweis")
        self.main_label.setStyleSheet("font-size: 18px; font-weight: bold; color: white;")
        self.main_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.main_label)

        self.sub_label = QLabel("")
        self.sub_label.setStyleSheet("font-size: 12px; color: rgba(255,255,255,180);")
        self.sub_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.sub_label)

        self.adjustSize()
        self.hide()

    def show_hint(self, main_text: str, sub_text: str = "", icon: str = "",
                  duration_ms: int = 3000, color: str = None):
        """Zeigt einen zentralen Hinweis."""
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

        if self.parent():
            parent_rect = self.parent().rect()
            x = (parent_rect.width() - self.width()) // 2
            y = (parent_rect.height() - self.height()) // 2 - 50
            self.move(x, y)

        self.show()
        self.raise_()

        if duration_ms > 0:
            if self._timer:
                self._timer.stop()
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self.hide)
            self._timer.start(duration_ms)

    def show_action_hint(self, action: str, details: str = ""):
        """Zeigt Hinweis für eine Aktion"""
        icons = {
            "select": "->",
            "move": "<->",
            "rotate": "(R)",
            "scale": "[S]",
            "copy": "[C]",
            "mirror": "|M|",
            "success": "[OK]",
            "error": "[X]",
            "info": "(i)",
        }
        icon = icons.get(action.lower(), "")
        self.show_hint(action, details, icon)

    def hide_hint(self):
        """Versteckt den Hinweis"""
        if self._timer:
            self._timer.stop()
        self.hide()