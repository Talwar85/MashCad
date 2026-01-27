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
    to_face_requested = Signal()  # "Extrude to Face" Modus anfordern
    
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

        # "To Face" Button
        self.to_face_btn = QPushButton("⬆ To")
        self.to_face_btn.setToolTip("Extrude bis zu Fläche (T)")
        self.to_face_btn.setFixedSize(50, 32)
        self.to_face_btn.setCheckable(True)
        self.to_face_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a; border: 1px solid #4a4a4a;
                border-radius: 3px; color: #ccc; font-size: 11px;
            }
            QPushButton:hover { background: #4a4a4a; color: #fff; }
            QPushButton:checked { background: #0078d4; border-color: #0078d4; color: #fff; }
        """)
        self.to_face_btn.clicked.connect(self._on_to_face_clicked)
        layout.addWidget(self.to_face_btn)

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
        
        
    def _on_to_face_clicked(self):
        if self.to_face_btn.isChecked():
            self.to_face_requested.emit()
            self.height_input.setEnabled(False)
            self.label.setText("Extrude → Face:")
        else:
            self.set_to_face_mode(False)

    def set_to_face_mode(self, active: bool):
        self.to_face_btn.setChecked(active)
        self.height_input.setEnabled(not active)
        self.label.setText("Extrude → Face:" if active else "Extrude:")

    def set_to_face_height(self, h: float):
        """Setzt Höhe aus To-Face Berechnung."""
        self.set_height(h)
        self.set_to_face_mode(False)
        self.height_input.setEnabled(True)

    def reset(self):
        self._height = 0.0
        self.height_input.blockSignals(True)
        self.height_input.setValue(0.0)
        self.height_input.blockSignals(False)
        self.height_input.setEnabled(True)
        self.op_combo.setCurrentIndex(0)
        self.btn_vis.setChecked(False)
        self.to_face_btn.setChecked(False)
        self.label.setText("Extrude:")

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

        # NEU: Kantenanzahl-Anzeige
        self.edge_count_label = QLabel("0 Kanten")
        self.edge_count_label.setStyleSheet("""
            color: #888;
            font-size: 11px;
            font-weight: normal;
            border: none;
            padding-left: 5px;
        """)
        self.edge_count_label.setMinimumWidth(80)
        layout.addWidget(self.edge_count_label)

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
        # Kantenanzahl zurücksetzen
        self.update_edge_count(0)

    def update_edge_count(self, count: int):
        """Aktualisiert die Anzeige der ausgewählten Kanten."""
        if count == 0:
            self.edge_count_label.setText("Keine Kanten")
            self.edge_count_label.setStyleSheet("""
                color: #ff6666;
                font-size: 11px;
                font-weight: normal;
                border: none;
                padding-left: 5px;
            """)
        elif count == 1:
            self.edge_count_label.setText("1 Kante")
            self.edge_count_label.setStyleSheet("""
                color: #66ff66;
                font-size: 11px;
                font-weight: normal;
                border: none;
                padding-left: 5px;
            """)
        else:
            self.edge_count_label.setText(f"{count} Kanten")
            self.edge_count_label.setStyleSheet("""
                color: #66ff66;
                font-size: 11px;
                font-weight: normal;
                border: none;
                padding-left: 5px;
            """)
    
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


# ==================== PHASE 6: SHELL INPUT PANEL ====================

class ShellInputPanel(QFrame):
    """
    Input panel for Shell operation.

    Shows:
    - Thickness spinner (wall thickness)
    - Face count label
    - OK/Cancel buttons
    """

    thickness_changed = Signal(float)
    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thickness = 2.0
        self._target_body = None
        self._opening_faces = []

        self.setMinimumWidth(380)
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

        # Label
        self.label = QLabel("Shell:")
        layout.addWidget(self.label)

        # Thickness input
        self.thickness_input = ActionSpinBox()
        self.thickness_input.setRange(0.1, 100.0)
        self.thickness_input.setDecimals(2)
        self.thickness_input.setSuffix(" mm")
        self.thickness_input.setValue(2.0)

        self.thickness_input.valueChanged.connect(self._on_value_changed)
        self.thickness_input.enterPressed.connect(self._confirm)
        self.thickness_input.escapePressed.connect(self._cancel)

        layout.addWidget(self.thickness_input)

        # Face count label
        self.face_count_label = QLabel("0 Öffnungen")
        self.face_count_label.setStyleSheet("""
            color: #888;
            font-size: 11px;
            font-weight: normal;
            border: none;
            padding-left: 5px;
        """)
        self.face_count_label.setMinimumWidth(90)
        layout.addWidget(self.face_count_label)

        # OK button
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setStyleSheet("background: #0078d4; border: none;")
        self.ok_btn.clicked.connect(self._confirm)
        layout.addWidget(self.ok_btn)

        # Cancel button
        self.cancel_btn = QPushButton("X")
        self.cancel_btn.setFixedWidth(30)
        self.cancel_btn.setStyleSheet("background: #d83b01; border: none;")
        self.cancel_btn.clicked.connect(self._cancel)
        layout.addWidget(self.cancel_btn)

        self.hide()

    def set_target_body(self, body):
        """Setzt den Ziel-Body für die Shell-Operation."""
        self._target_body = body

    def get_target_body(self):
        """Gibt den Ziel-Body zurück."""
        return self._target_body

    def add_opening_face(self, face_selector: tuple):
        """Fügt eine Öffnungs-Fläche hinzu."""
        if face_selector not in self._opening_faces:
            self._opening_faces.append(face_selector)
            self.update_face_count(len(self._opening_faces))

    def remove_opening_face(self, face_selector: tuple):
        """Entfernt eine Öffnungs-Fläche."""
        if face_selector in self._opening_faces:
            self._opening_faces.remove(face_selector)
            self.update_face_count(len(self._opening_faces))

    def clear_opening_faces(self):
        """Löscht alle Öffnungs-Flächen."""
        self._opening_faces.clear()
        self.update_face_count(0)

    def get_opening_faces(self) -> list:
        """Gibt alle Öffnungs-Flächen zurück."""
        return self._opening_faces.copy()

    def get_thickness(self) -> float:
        """Gibt die eingestellte Wandstärke zurück."""
        return self.thickness_input.value()

    def update_face_count(self, count: int):
        """Aktualisiert die Anzeige der ausgewählten Öffnungen."""
        if count == 0:
            self.face_count_label.setText("Keine Öffnung")
            self.face_count_label.setStyleSheet("""
                color: #ffaa00;
                font-size: 11px;
                font-weight: normal;
                border: none;
                padding-left: 5px;
            """)
        elif count == 1:
            self.face_count_label.setText("1 Öffnung")
            self.face_count_label.setStyleSheet("""
                color: #66ff66;
                font-size: 11px;
                font-weight: normal;
                border: none;
                padding-left: 5px;
            """)
        else:
            self.face_count_label.setText(f"{count} Öffnungen")
            self.face_count_label.setStyleSheet("""
                color: #66ff66;
                font-size: 11px;
                font-weight: normal;
                border: none;
                padding-left: 5px;
            """)

    def reset(self):
        """Setzt das Panel zurück."""
        self._target_body = None
        self._opening_faces.clear()
        self.thickness_input.setValue(2.0)
        self.update_face_count(0)

    def _on_value_changed(self, val):
        """Callback bei Änderung der Wandstärke."""
        self._thickness = val
        self.thickness_changed.emit(val)

    def _confirm(self):
        """Bestätigt die Operation."""
        self.confirmed.emit()

    def _cancel(self):
        """Bricht die Operation ab."""
        self.cancelled.emit()

    def show_at(self, pos_widget=None):
        """Zeigt das Panel zentriert unten im Parent-Widget."""
        self.show()
        self.raise_()

        if pos_widget:
            parent = pos_widget.parent() if pos_widget.parent() else pos_widget

            # X mittig zentrieren
            x = (parent.width() - self.width()) // 2

            # Y unten positionieren (mit 50px Abstand vom Rand)
            y = parent.height() - self.height() - 50

            if y < 0:
                y = 50

            self.move(x, y)

            self.thickness_input.setFocus()
            self.thickness_input.selectAll()


class SweepInputPanel(QFrame):
    """
    Input panel for Sweep operation.

    Shows:
    - Profile status (selected/not selected)
    - Path status (selected/not selected)
    - Frenet checkbox (twist along path)
    - Operation dropdown (New Body, Join, Cut, Intersect)
    - OK/Cancel buttons
    """

    confirmed = Signal()
    cancelled = Signal()
    operation_changed = Signal(str)
    sketch_path_requested = Signal()  # Fordert Pfad aus Sketch an

    def __init__(self, parent=None):
        super().__init__(parent)
        self._profile_data = None
        self._path_data = None
        self._operation = "New Body"
        self._is_frenet = False

        self.setMinimumWidth(650)
        self.setFixedHeight(60)

        self.setStyleSheet("""
            QFrame {
                background: #2d2d30;
                border: 2px solid #0078d4;
                border-radius: 8px;
            }
            QLabel { color: #fff; font-weight: bold; border: none; font-size: 12px; }
            QComboBox {
                background: #1e1e1e; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 4px; font-weight: bold; font-size: 11px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background: #1e1e1e; color: #fff; selection-background-color: #0078d4; }
            QCheckBox { color: #fff; font-size: 11px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
            QCheckBox::indicator:unchecked { background: #1e1e1e; border: 1px solid #555; border-radius: 3px; }
            QCheckBox::indicator:checked { background: #0078d4; border: 1px solid #0078d4; border-radius: 3px; }
            QPushButton {
                background: #444; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 5px; font-weight: bold;
            }
            QPushButton:hover { background: #555; }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 5, 15, 5)
        layout.setSpacing(10)

        # Label
        self.label = QLabel("Sweep:")
        layout.addWidget(self.label)

        # Profile status
        self.profile_status = QLabel("⬜ Profil")
        self.profile_status.setStyleSheet("""
            color: #ffaa00;
            font-size: 11px;
            font-weight: normal;
            border: none;
        """)
        self.profile_status.setMinimumWidth(70)
        layout.addWidget(self.profile_status)

        # Path status
        self.path_status = QLabel("⬜ Pfad")
        self.path_status.setStyleSheet("""
            color: #ffaa00;
            font-size: 11px;
            font-weight: normal;
            border: none;
        """)
        self.path_status.setMinimumWidth(70)
        layout.addWidget(self.path_status)

        # Sketch Path button
        self.sketch_path_btn = QPushButton("Sketch")
        self.sketch_path_btn.setToolTip("Pfad aus Sketch wählen (Bogen/Linie/Spline)")
        self.sketch_path_btn.setFixedWidth(55)
        self.sketch_path_btn.clicked.connect(lambda: self.sketch_path_requested.emit())
        layout.addWidget(self.sketch_path_btn)

        # Frenet checkbox
        self.frenet_check = QCheckBox("Frenet")
        self.frenet_check.setToolTip("Verdrehung entlang des Pfads")
        self.frenet_check.stateChanged.connect(self._on_frenet_changed)
        layout.addWidget(self.frenet_check)

        # Twist angle
        from PySide6.QtGui import QDoubleValidator
        twist_lbl = QLabel("Twist:")
        twist_lbl.setStyleSheet("font-weight: normal; font-size: 11px; border: none;")
        layout.addWidget(twist_lbl)
        self.twist_input = QLineEdit("0")
        self.twist_input.setFixedWidth(45)
        self.twist_input.setStyleSheet(
            "background: #1e1e1e; color: #fff; border: 1px solid #555; "
            "border-radius: 4px; padding: 3px; font-size: 11px;"
        )
        tv = QDoubleValidator(-3600, 3600, 1)
        tv.setNotation(QDoubleValidator.StandardNotation)
        self.twist_input.setValidator(tv)
        self.twist_input.setToolTip("Twist angle in degrees along path")
        layout.addWidget(self.twist_input)

        # Scale
        scale_lbl = QLabel("Scale:")
        scale_lbl.setStyleSheet("font-weight: normal; font-size: 11px; border: none;")
        layout.addWidget(scale_lbl)
        self.scale_start_input = QLineEdit("1.0")
        self.scale_start_input.setFixedWidth(35)
        self.scale_start_input.setStyleSheet(
            "background: #1e1e1e; color: #fff; border: 1px solid #555; "
            "border-radius: 4px; padding: 3px; font-size: 11px;"
        )
        sv = QDoubleValidator(0.01, 100, 2)
        sv.setNotation(QDoubleValidator.StandardNotation)
        self.scale_start_input.setValidator(sv)
        self.scale_start_input.setToolTip("Scale at path start")
        layout.addWidget(self.scale_start_input)

        arrow_lbl = QLabel("→")
        arrow_lbl.setStyleSheet("font-weight: normal; font-size: 11px; border: none;")
        layout.addWidget(arrow_lbl)

        self.scale_end_input = QLineEdit("1.0")
        self.scale_end_input.setFixedWidth(35)
        self.scale_end_input.setStyleSheet(
            "background: #1e1e1e; color: #fff; border: 1px solid #555; "
            "border-radius: 4px; padding: 3px; font-size: 11px;"
        )
        self.scale_end_input.setValidator(sv)
        self.scale_end_input.setToolTip("Scale at path end")
        layout.addWidget(self.scale_end_input)

        # Operation combo
        self.operation_combo = QComboBox()
        self.operation_combo.addItems(["New Body", "Join", "Cut", "Intersect"])
        self.operation_combo.setFixedWidth(90)
        self.operation_combo.currentTextChanged.connect(self._on_operation_changed)
        layout.addWidget(self.operation_combo)

        # OK button
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setStyleSheet("background: #0078d4; border: none;")
        self.ok_btn.clicked.connect(self._confirm)
        self.ok_btn.setEnabled(False)  # Disabled until profile and path selected
        layout.addWidget(self.ok_btn)

        # Cancel button
        self.cancel_btn = QPushButton("X")
        self.cancel_btn.setFixedWidth(30)
        self.cancel_btn.setStyleSheet("background: #d83b01; border: none;")
        self.cancel_btn.clicked.connect(self._cancel)
        layout.addWidget(self.cancel_btn)

        self.hide()

    def set_profile(self, profile_data: dict):
        """Setzt das Profil für den Sweep."""
        self._profile_data = profile_data
        self.profile_status.setText("✅ Profil")
        self.profile_status.setStyleSheet("""
            color: #66ff66;
            font-size: 11px;
            font-weight: normal;
            border: none;
        """)
        self._update_ok_button()

    def clear_profile(self):
        """Löscht das Profil."""
        self._profile_data = None
        self.profile_status.setText("⬜ Profil")
        self.profile_status.setStyleSheet("""
            color: #ffaa00;
            font-size: 11px;
            font-weight: normal;
            border: none;
        """)
        self._update_ok_button()

    def set_path(self, path_data: dict):
        """Setzt den Pfad für den Sweep."""
        self._path_data = path_data
        self.path_status.setText("✅ Pfad")
        self.path_status.setStyleSheet("""
            color: #66ff66;
            font-size: 11px;
            font-weight: normal;
            border: none;
        """)
        self._update_ok_button()

    def clear_path(self):
        """Löscht den Pfad."""
        self._path_data = None
        self.path_status.setText("⬜ Pfad")
        self.path_status.setStyleSheet("""
            color: #ffaa00;
            font-size: 11px;
            font-weight: normal;
            border: none;
        """)
        self._update_ok_button()

    def get_profile_data(self) -> dict:
        """Gibt die Profil-Daten zurück."""
        return self._profile_data

    def get_path_data(self) -> dict:
        """Gibt die Pfad-Daten zurück."""
        return self._path_data

    def get_operation(self) -> str:
        """Gibt die gewählte Operation zurück."""
        return self.operation_combo.currentText()

    def is_frenet(self) -> bool:
        """Gibt zurück ob Frenet aktiv ist."""
        return self.frenet_check.isChecked()

    def get_twist_angle(self) -> float:
        """Returns twist angle in degrees."""
        try:
            return float(self.twist_input.text() or "0")
        except ValueError:
            return 0.0

    def get_scale_start(self) -> float:
        """Returns scale factor at path start."""
        try:
            return float(self.scale_start_input.text() or "1.0")
        except ValueError:
            return 1.0

    def get_scale_end(self) -> float:
        """Returns scale factor at path end."""
        try:
            return float(self.scale_end_input.text() or "1.0")
        except ValueError:
            return 1.0

    def reset(self):
        """Setzt das Panel zurück."""
        self._profile_data = None
        self._path_data = None
        self.clear_profile()
        self.clear_path()
        self.frenet_check.setChecked(False)
        self.twist_input.setText("0")
        self.scale_start_input.setText("1.0")
        self.scale_end_input.setText("1.0")
        self.operation_combo.setCurrentIndex(0)

    def _update_ok_button(self):
        """Aktiviert OK nur wenn Profil und Pfad gesetzt sind."""
        enabled = self._profile_data is not None and self._path_data is not None
        self.ok_btn.setEnabled(enabled)

    def _on_frenet_changed(self, state):
        """Callback bei Änderung der Frenet-Option."""
        self._is_frenet = state == Qt.Checked

    def _on_operation_changed(self, operation: str):
        """Callback bei Änderung der Operation."""
        self._operation = operation
        self.operation_changed.emit(operation)

    def _confirm(self):
        """Bestätigt die Operation."""
        self.confirmed.emit()

    def _cancel(self):
        """Bricht die Operation ab."""
        self.cancelled.emit()

    def show_at(self, pos_widget=None):
        """Zeigt das Panel zentriert unten im Parent-Widget."""
        self.show()
        self.raise_()

        if pos_widget:
            parent = pos_widget.parent() if pos_widget.parent() else pos_widget

            x = (parent.width() - self.width()) // 2
            y = parent.height() - self.height() - 50

            if y < 0:
                y = 50

            self.move(x, y)


class LoftInputPanel(QFrame):
    """
    Input panel for Loft operation.

    Shows:
    - Profile list with Z-info
    - Add profile button
    - Ruled/Smooth toggle
    - Operation dropdown
    - OK/Cancel buttons
    """

    confirmed = Signal()
    cancelled = Signal()
    add_profile_requested = Signal()
    operation_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._profiles = []  # List of profile data dicts
        self._operation = "New Body"
        self._ruled = False

        self.setMinimumWidth(480)
        self.setFixedHeight(80)

        self.setStyleSheet("""
            QFrame {
                background: #2d2d30;
                border: 2px solid #0078d4;
                border-radius: 8px;
            }
            QLabel { color: #fff; font-weight: bold; border: none; font-size: 12px; }
            QComboBox {
                background: #1e1e1e; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 4px; font-weight: bold; font-size: 11px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background: #1e1e1e; color: #fff; selection-background-color: #0078d4; }
            QCheckBox { color: #fff; font-size: 11px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
            QCheckBox::indicator:unchecked { background: #1e1e1e; border: 1px solid #555; border-radius: 3px; }
            QCheckBox::indicator:checked { background: #0078d4; border: 1px solid #0078d4; border-radius: 3px; }
            QPushButton {
                background: #444; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 5px; font-weight: bold;
            }
            QPushButton:hover { background: #555; }
            QListWidget {
                background: #1e1e1e; color: #fff; border: 1px solid #555;
                border-radius: 4px; font-size: 10px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 5, 10, 5)
        main_layout.setSpacing(5)

        # Top row: Label, Profile count, Add button
        top_row = QHBoxLayout()

        self.label = QLabel("Loft:")
        top_row.addWidget(self.label)

        self.profile_count_label = QLabel("0 Profile")
        self.profile_count_label.setStyleSheet("""
            color: #ffaa00;
            font-size: 11px;
            font-weight: normal;
            border: none;
        """)
        self.profile_count_label.setMinimumWidth(80)
        top_row.addWidget(self.profile_count_label)

        self.add_profile_btn = QPushButton("+ Profil")
        self.add_profile_btn.setStyleSheet("background: #3a3a3a; font-size: 10px;")
        self.add_profile_btn.clicked.connect(self._on_add_profile)
        top_row.addWidget(self.add_profile_btn)

        # Ruled checkbox
        self.ruled_check = QCheckBox("Ruled")
        self.ruled_check.setToolTip("Gerade Linien statt glatter Übergänge")
        self.ruled_check.stateChanged.connect(self._on_ruled_changed)
        top_row.addWidget(self.ruled_check)

        # Operation combo
        self.operation_combo = QComboBox()
        self.operation_combo.addItems(["New Body", "Join", "Cut", "Intersect"])
        self.operation_combo.setFixedWidth(90)
        self.operation_combo.currentTextChanged.connect(self._on_operation_changed)
        top_row.addWidget(self.operation_combo)

        # OK button
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setStyleSheet("background: #0078d4; border: none;")
        self.ok_btn.clicked.connect(self._confirm)
        self.ok_btn.setEnabled(False)  # Disabled until 2+ profiles
        top_row.addWidget(self.ok_btn)

        # Cancel button
        self.cancel_btn = QPushButton("X")
        self.cancel_btn.setFixedWidth(30)
        self.cancel_btn.setStyleSheet("background: #d83b01; border: none;")
        self.cancel_btn.clicked.connect(self._cancel)
        top_row.addWidget(self.cancel_btn)

        main_layout.addLayout(top_row)

        # Bottom row: Profile info
        self.profile_info = QLabel("Wähle Flächen auf verschiedenen Z-Ebenen")
        self.profile_info.setStyleSheet("""
            color: #888;
            font-size: 10px;
            font-weight: normal;
            border: none;
        """)
        main_layout.addWidget(self.profile_info)

        self.hide()

    def add_profile(self, profile_data: dict):
        """Fügt ein Profil zur Liste hinzu."""
        self._profiles.append(profile_data)
        self._update_ui()

    def remove_profile(self, index: int):
        """Entfernt ein Profil aus der Liste."""
        if 0 <= index < len(self._profiles):
            self._profiles.pop(index)
            self._update_ui()

    def clear_profiles(self):
        """Löscht alle Profile."""
        self._profiles.clear()
        self._update_ui()

    def get_profiles(self) -> list:
        """Gibt alle Profile zurück."""
        return self._profiles.copy()

    def get_operation(self) -> str:
        """Gibt die gewählte Operation zurück."""
        return self.operation_combo.currentText()

    def is_ruled(self) -> bool:
        """Gibt zurück ob Ruled aktiv ist."""
        return self.ruled_check.isChecked()

    def reset(self):
        """Setzt das Panel zurück."""
        self._profiles.clear()
        self.ruled_check.setChecked(False)
        self.operation_combo.setCurrentIndex(0)
        self._update_ui()

    def _update_ui(self):
        """Aktualisiert die UI basierend auf dem aktuellen Zustand."""
        count = len(self._profiles)

        # Profile count label
        if count == 0:
            self.profile_count_label.setText("0 Profile")
            self.profile_count_label.setStyleSheet("""
                color: #ffaa00;
                font-size: 11px;
                font-weight: normal;
                border: none;
            """)
        elif count == 1:
            z_info = self._get_z_info(self._profiles[0])
            self.profile_count_label.setText(f"1 Profil ({z_info})")
            self.profile_count_label.setStyleSheet("""
                color: #ffaa00;
                font-size: 11px;
                font-weight: normal;
                border: none;
            """)
        else:
            z_min = min(self._get_z(p) for p in self._profiles)
            z_max = max(self._get_z(p) for p in self._profiles)
            self.profile_count_label.setText(f"{count} Profile (Z: {z_min:.0f}-{z_max:.0f})")
            self.profile_count_label.setStyleSheet("""
                color: #66ff66;
                font-size: 11px;
                font-weight: normal;
                border: none;
            """)

        # OK button enabled only with 2+ profiles
        self.ok_btn.setEnabled(count >= 2)

        # Info label
        if count < 2:
            self.profile_info.setText(f"Wähle mindestens {2 - count} weitere Fläche(n)")
        else:
            self.profile_info.setText(f"Bereit zum Loft ({count} Profile)")

    def _get_z(self, profile_data: dict) -> float:
        """Extrahiert Z-Koordinate aus Profil-Daten."""
        if 'plane_origin' in profile_data:
            origin = profile_data['plane_origin']
            if isinstance(origin, (list, tuple)) and len(origin) >= 3:
                return origin[2]
        return 0.0

    def _get_z_info(self, profile_data: dict) -> str:
        """Gibt Z-Info String zurück."""
        z = self._get_z(profile_data)
        return f"Z={z:.0f}"

    def _on_add_profile(self):
        """Callback für Add-Profile-Button."""
        self.add_profile_requested.emit()

    def _on_ruled_changed(self, state):
        """Callback bei Änderung der Ruled-Option."""
        self._ruled = state == Qt.Checked

    def _on_operation_changed(self, operation: str):
        """Callback bei Änderung der Operation."""
        self._operation = operation
        self.operation_changed.emit(operation)

    def _confirm(self):
        """Bestätigt die Operation."""
        self.confirmed.emit()

    def _cancel(self):
        """Bricht die Operation ab."""
        self.cancelled.emit()

    def show_at(self, pos_widget=None):
        """Zeigt das Panel zentriert unten im Parent-Widget."""
        self.show()
        self.raise_()

        if pos_widget:
            parent = pos_widget.parent() if pos_widget.parent() else pos_widget

            x = (parent.width() - self.width()) // 2
            y = parent.height() - self.height() - 50

            if y < 0:
                y = 50

            self.move(x, y)


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


class OffsetPlaneInputPanel(QFrame):
    """Input panel for interactive Offset Plane creation."""

    offset_changed = Signal(float)
    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._offset = 0.0

        self.setMinimumWidth(380)
        self.setFixedHeight(60)

        self.setStyleSheet("""
            QFrame {
                background: #2d2d30;
                border: 2px solid #bb88dd;
                border-radius: 8px;
            }
            QLabel { color: #fff; font-weight: bold; border: none; font-size: 12px; }
            QDoubleSpinBox {
                background: #1e1e1e; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 4px; font-weight: bold; font-size: 13px;
            }
            QLineEdit {
                background: #1e1e1e; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 4px; font-size: 12px;
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

        layout.addWidget(QLabel("Offset:"))

        self.offset_input = ActionSpinBox()
        self.offset_input.setRange(-10000.0, 10000.0)
        self.offset_input.setDecimals(2)
        self.offset_input.setSuffix(" mm")
        self.offset_input.setValue(0.0)
        self.offset_input.valueChanged.connect(self._on_value_changed)
        self.offset_input.enterPressed.connect(self._confirm)
        self.offset_input.escapePressed.connect(self._cancel)
        layout.addWidget(self.offset_input)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Name (auto)")
        self.name_input.setMaximumWidth(120)
        layout.addWidget(self.name_input)

        self.ok_btn = QPushButton("OK")
        self.ok_btn.setStyleSheet("background: #bb88dd; color: #000; border: none;")
        self.ok_btn.clicked.connect(self._confirm)
        layout.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("X")
        self.cancel_btn.setFixedWidth(30)
        self.cancel_btn.setStyleSheet("background: #d83b01; border: none;")
        self.cancel_btn.clicked.connect(self._cancel)
        layout.addWidget(self.cancel_btn)

        self.hide()

    def _on_value_changed(self, value):
        self._offset = value
        self.offset_changed.emit(value)

    def _confirm(self):
        self._offset = self.offset_input.value()
        self.confirmed.emit()

    def _cancel(self):
        self.cancelled.emit()

    def get_offset(self) -> float:
        return self.offset_input.value()

    def set_offset(self, value: float):
        self.offset_input.blockSignals(True)
        self.offset_input.setValue(value)
        self.offset_input.blockSignals(False)
        self._offset = value

    def get_name(self):
        text = self.name_input.text().strip()
        return text if text else None

    def reset(self):
        self._offset = 0.0
        self.offset_input.blockSignals(True)
        self.offset_input.setValue(0.0)
        self.offset_input.blockSignals(False)
        self.name_input.clear()

    def show_at(self, pos_widget):
        self.show()
        self.raise_()
        if pos_widget:
            parent = pos_widget.parent() if pos_widget.parent() else pos_widget
            x = (parent.width() - self.width()) // 2
            y = parent.height() - self.height() - 50
            if y < 0:
                y = 50
            self.move(x, y)