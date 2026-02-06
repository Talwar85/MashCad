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

from i18n import tr
from gui.design_tokens import DesignTokens  # NEU: Single Source of Truth für Styling

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
    bodies_visibility_toggled = Signal(bool)  # Legacy (für Kompatibilität)
    bodies_visibility_state_changed = Signal(int)  # 0=normal, 1=xray, 2=hidden
    operation_changed = Signal(str)  # NEU: Signal wenn Operation geändert wird
    to_face_requested = Signal()  # "Extrude to Face" Modus anfordern

    # Visibility States
    VIS_NORMAL = 0   # 100% sichtbar
    VIS_XRAY = 1     # 20% transparent (X-Ray)
    VIS_HIDDEN = 2   # Komplett versteckt

    def __init__(self, parent=None):
        super().__init__(parent)
        self._height = 0.0
        self._bodies_hidden = False
        self._visibility_state = 0  # 0=normal, 1=xray, 2=hidden
        self._direction = 1  # 1 or -1
        self._current_operation = "New Body"
        self.setMinimumWidth(560)  # Breiter für bessere Lesbarkeit
        self.setFixedHeight(65)

        # DesignTokens für konsistentes Styling
        self.setStyleSheet(DesignTokens.stylesheet_panel())
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)
        
        self.label = QLabel(tr("Extrude:"))
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
        # Store internal keys as item data for comparison, display translated text
        for key in ["New Body", "Join", "Cut", "Intersect"]:
            self.op_combo.addItem(tr(key), key)
        self.op_combo.currentIndexChanged.connect(self._on_operation_changed_idx)
        layout.addWidget(self.op_combo)

        # Flip Direction Button
        self.flip_btn = QPushButton("⇅")
        self.flip_btn.setToolTip(tr("Flip direction (F)"))
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
        self.to_face_btn.setToolTip(tr("Extrude to face (T)"))
        self.to_face_btn.setFixedSize(50, 32)
        self.to_face_btn.setCheckable(True)
        self.to_face_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a3a; border: 1px solid #4a4a4a;
                border-radius: 3px; color: #ccc; font-size: 12px;
            }
            QPushButton:hover { background: #4a4a4a; color: #fff; }
            QPushButton:checked { background: #0078d4; border-color: #0078d4; color: #fff; }
        """)
        self.to_face_btn.clicked.connect(self._on_to_face_clicked)
        layout.addWidget(self.to_face_btn)

        self.btn_vis = QPushButton("👁")
        self.btn_vis.setCheckable(False)  # 3-Stufen-Toggle statt an/aus
        self.btn_vis.setFixedWidth(35)
        self.btn_vis.setToolTip(tr("Bodies visible (click → X-Ray)"))
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
        
    def _on_operation_changed_idx(self, index: int):
        """Aktualisiert Farb-Indikator und emittiert Signal"""
        # Get internal key from itemData
        op_key = self.op_combo.itemData(index)
        if op_key is None:
            op_key = self.op_combo.currentText()  # Fallback
        self._current_operation = op_key
        colors = {
            "New Body": "#6699ff",  # Blau
            "Join": "#66ff66",      # Grün
            "Cut": "#ff6666",       # Rot
            "Intersect": "#ffaa66"  # Orange
        }
        self.op_indicator.setStyleSheet(f"color: {colors.get(op_key, '#6699ff')}; font-size: 16px;")

        # Tooltip-Warnung für Boolean Operations
        if op_key in ["Join", "Cut", "Intersect"]:
            self.op_combo.setToolTip(
                tr("⚠️ Boolean operations may fail on complex geometry.\n"
                   "Tip: 'New Body' is safer - bodies can be combined later.")
            )
        else:
            self.op_combo.setToolTip(tr("Creates a new independent body (recommended)"))

        self.operation_changed.emit(op_key)
        
    def set_suggested_operation(self, operation: str):
        """Setzt die vorgeschlagene Operation automatisch"""
        # Use findData to search by internal key, not translated text
        idx = self.op_combo.findData(operation)
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
        # Return internal key, not translated text
        data = self.op_combo.currentData()
        return data if data else self.op_combo.currentText()
    
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
            self.label.setText(tr("Extrude → Face:"))
        else:
            self.set_to_face_mode(False)

    def set_to_face_mode(self, active: bool):
        self.to_face_btn.setChecked(active)
        self.height_input.setEnabled(not active)
        self.label.setText(tr("Extrude → Face:") if active else tr("Extrude:"))

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
        # Visibility State zurücksetzen
        self._visibility_state = 0
        self.btn_vis.setText("👁")
        self.btn_vis.setToolTip(tr("Bodies visible (click → X-Ray)"))
        self.to_face_btn.setChecked(False)
        self.label.setText(tr("Extrude:"))

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
        """3-Stufen Toggle: Normal → X-Ray → Versteckt → Normal"""
        self._visibility_state = (self._visibility_state + 1) % 3

        # Button-Aussehen und Tooltip aktualisieren
        icons = ["👁", "👁‍🗨", "🚫"]  # Normal, X-Ray, Hidden
        tooltips = [
            tr("Bodies visible (click → X-Ray)"),
            tr("X-Ray mode active (click → Hide)"),
            tr("Bodies hidden (click → Visible)")
        ]
        self.btn_vis.setText(icons[self._visibility_state])
        self.btn_vis.setToolTip(tooltips[self._visibility_state])

        # Neues Signal mit State
        self.bodies_visibility_state_changed.emit(self._visibility_state)

        # Legacy-Signal (für Kompatibilität)
        self._bodies_hidden = (self._visibility_state == self.VIS_HIDDEN)
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
        
        self.setMinimumWidth(420)
        self.setFixedHeight(75)

        self.setStyleSheet(DesignTokens.stylesheet_panel())
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        self.label = QLabel(tr("Fillet:"))
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
        self.edge_count_label = QLabel(tr("0 edges"))
        self.edge_count_label.setStyleSheet("""
            color: #888;
            font-size: 12px;
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
        self.label.setText(tr("Fillet:") if mode == "fillet" else tr("Chamfer:"))
        # Kantenanzahl zurücksetzen
        self.update_edge_count(0)

    def update_edge_count(self, count: int):
        """Aktualisiert die Anzeige der ausgewählten Kanten."""
        if count == 0:
            self.edge_count_label.setText(tr("No edges"))
            self.edge_count_label.setStyleSheet("""
                color: #ff6666;
                font-size: 12px;
                font-weight: normal;
                border: none;
                padding-left: 5px;
            """)
        elif count == 1:
            self.edge_count_label.setText(tr("1 edge"))
            self.edge_count_label.setStyleSheet("""
                color: #66ff66;
                font-size: 12px;
                font-weight: normal;
                border: none;
                padding-left: 5px;
            """)
        else:
            self.edge_count_label.setText(tr("{count} edges").format(count=count))
            self.edge_count_label.setStyleSheet("""
                color: #66ff66;
                font-size: 12px;
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

        self.setMinimumWidth(450)
        self.setFixedHeight(75)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # Label
        self.label = QLabel(tr("Shell:"))
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
        self.face_count_label = QLabel(tr("0 openings"))
        self.face_count_label.setStyleSheet("""
            color: #888;
            font-size: 12px;
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
            self.face_count_label.setText(tr("No opening"))
            self.face_count_label.setStyleSheet("""
                color: #ffaa00;
                font-size: 12px;
                font-weight: normal;
                border: none;
                padding-left: 5px;
            """)
        elif count == 1:
            self.face_count_label.setText(tr("1 opening"))
            self.face_count_label.setStyleSheet("""
                color: #66ff66;
                font-size: 12px;
                font-weight: normal;
                border: none;
                padding-left: 5px;
            """)
        else:
            self.face_count_label.setText(tr("{count} openings").format(count=count))
            self.face_count_label.setStyleSheet("""
                color: #66ff66;
                font-size: 12px;
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
    profile_cleared = Signal()  # Profil-Auswahl entfernt
    path_cleared = Signal()  # Pfad-Auswahl entfernt

    def __init__(self, parent=None):
        super().__init__(parent)
        self._profile_data = None
        self._path_data = None
        self._operation = "New Body"
        self._is_frenet = False

        self.setMinimumWidth(700)
        self.setFixedHeight(80)  # Höher für bessere Lesbarkeit

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(12)

        # Label
        self.label = QLabel(tr("Sweep:"))
        layout.addWidget(self.label)

        # Profile status with clear button
        profile_container = QWidget()
        profile_container.setStyleSheet("background: transparent; border: none;")
        profile_layout = QHBoxLayout(profile_container)
        profile_layout.setContentsMargins(0, 0, 0, 0)
        profile_layout.setSpacing(4)

        self.profile_status = QLabel(tr("⬜ Profile"))
        self.profile_status.setStyleSheet("""
            color: #ffaa00;
            font-size: 12px;
            font-weight: normal;
            border: none;
        """)
        profile_layout.addWidget(self.profile_status)

        self.profile_clear_btn = QPushButton("×")
        self.profile_clear_btn.setFixedSize(16, 16)
        self.profile_clear_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888;
                border: none;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #ff6666;
            }
        """)
        self.profile_clear_btn.setToolTip(tr("Clear profile selection"))
        self.profile_clear_btn.clicked.connect(self._on_profile_clear_clicked)
        self.profile_clear_btn.hide()  # Initially hidden
        profile_layout.addWidget(self.profile_clear_btn)
        layout.addWidget(profile_container)

        # Path status with clear button
        path_container = QWidget()
        path_container.setStyleSheet("background: transparent; border: none;")
        path_layout = QHBoxLayout(path_container)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(2)

        self.path_status = QLabel(tr("⬜ Path"))
        self.path_status.setStyleSheet("""
            color: #ffaa00;
            font-size: 12px;
            font-weight: normal;
            border: none;
        """)
        path_layout.addWidget(self.path_status)

        self.path_clear_btn = QPushButton("×")
        self.path_clear_btn.setFixedSize(16, 16)
        self.path_clear_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888;
                border: none;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #ff6666;
            }
        """)
        self.path_clear_btn.setToolTip(tr("Clear path selection"))
        self.path_clear_btn.clicked.connect(self._on_path_clear_clicked)
        self.path_clear_btn.hide()  # Initially hidden
        path_layout.addWidget(self.path_clear_btn)
        layout.addWidget(path_container)

        # Sketch Path button
        self.sketch_path_btn = QPushButton(tr("Sketch"))
        self.sketch_path_btn.setToolTip(tr("Select path from sketch (arc/line/spline)"))
        self.sketch_path_btn.setFixedWidth(55)
        self.sketch_path_btn.clicked.connect(lambda: self.sketch_path_requested.emit())
        layout.addWidget(self.sketch_path_btn)

        # Frenet checkbox
        self.frenet_check = QCheckBox(tr("Frenet"))
        self.frenet_check.setToolTip(tr("Twist along path"))
        self.frenet_check.stateChanged.connect(self._on_frenet_changed)
        layout.addWidget(self.frenet_check)

        # Twist angle
        from PySide6.QtGui import QDoubleValidator
        twist_lbl = QLabel(tr("Twist:"))
        twist_lbl.setStyleSheet("font-weight: normal; font-size: 12px; border: none;")
        layout.addWidget(twist_lbl)
        self.twist_input = QLineEdit("0")
        self.twist_input.setFixedWidth(55)
        self.twist_input.setStyleSheet(
            "background: #1e1e1e; color: #fff; border: 1px solid #555; "
            "border-radius: 4px; padding: 5px; font-size: 12px;"
        )
        tv = QDoubleValidator(-3600, 3600, 1)
        tv.setNotation(QDoubleValidator.StandardNotation)
        self.twist_input.setValidator(tv)
        self.twist_input.setToolTip(tr("Twist angle in degrees along path"))
        layout.addWidget(self.twist_input)

        # Scale
        scale_lbl = QLabel(tr("Scale:"))
        scale_lbl.setStyleSheet("font-weight: normal; font-size: 12px; border: none;")
        layout.addWidget(scale_lbl)
        self.scale_start_input = QLineEdit("1.0")
        self.scale_start_input.setFixedWidth(50)
        self.scale_start_input.setStyleSheet(
            "background: #1e1e1e; color: #fff; border: 1px solid #555; "
            "border-radius: 4px; padding: 5px; font-size: 12px;"
        )
        sv = QDoubleValidator(0.01, 100, 2)
        sv.setNotation(QDoubleValidator.StandardNotation)
        self.scale_start_input.setValidator(sv)
        self.scale_start_input.setToolTip(tr("Scale at path start"))
        layout.addWidget(self.scale_start_input)

        arrow_lbl = QLabel("→")
        arrow_lbl.setStyleSheet("font-weight: normal; font-size: 14px; border: none;")
        layout.addWidget(arrow_lbl)

        self.scale_end_input = QLineEdit("1.0")
        self.scale_end_input.setFixedWidth(50)
        self.scale_end_input.setStyleSheet(
            "background: #1e1e1e; color: #fff; border: 1px solid #555; "
            "border-radius: 4px; padding: 5px; font-size: 12px;"
        )
        self.scale_end_input.setValidator(sv)
        self.scale_end_input.setToolTip(tr("Scale at path end"))
        layout.addWidget(self.scale_end_input)

        # Operation combo
        self.operation_combo = QComboBox()
        # Store internal keys as item data for comparison, display translated text
        for key in ["New Body", "Join", "Cut", "Intersect"]:
            self.operation_combo.addItem(tr(key), key)
        self.operation_combo.setFixedWidth(110)
        self.operation_combo.currentIndexChanged.connect(self._on_operation_changed_idx)
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
        self.profile_status.setText(tr("✅ Profile"))
        self.profile_status.setStyleSheet("""
            color: #66ff66;
            font-size: 12px;
            font-weight: normal;
            border: none;
        """)
        self.profile_clear_btn.show()
        self._update_ok_button()

    def clear_profile(self):
        """Löscht das Profil."""
        self._profile_data = None
        self.profile_status.setText(tr("⬜ Profile"))
        self.profile_status.setStyleSheet("""
            color: #ffaa00;
            font-size: 12px;
            font-weight: normal;
            border: none;
        """)
        self.profile_clear_btn.hide()
        self._update_ok_button()

    def set_path(self, path_data: dict):
        """Setzt den Pfad für den Sweep."""
        self._path_data = path_data
        self.path_status.setText(tr("✅ Path"))
        self.path_status.setStyleSheet("""
            color: #66ff66;
            font-size: 12px;
            font-weight: normal;
            border: none;
        """)
        self.path_clear_btn.show()
        self._update_ok_button()

    def clear_path(self):
        """Löscht den Pfad."""
        self._path_data = None
        self.path_status.setText(tr("⬜ Path"))
        self.path_status.setStyleSheet("""
            color: #ffaa00;
            font-size: 12px;
            font-weight: normal;
            border: none;
        """)
        self.path_clear_btn.hide()
        self._update_ok_button()

    def get_profile_data(self) -> dict:
        """Gibt die Profil-Daten zurück."""
        return self._profile_data

    def get_path_data(self) -> dict:
        """Gibt die Pfad-Daten zurück."""
        return self._path_data

    def get_operation(self) -> str:
        """Gibt die gewählte Operation zurück."""
        # Return internal key, not translated text
        data = self.operation_combo.currentData()
        return data if data else self.operation_combo.currentText()

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

    def _on_operation_changed_idx(self, index: int):
        """Callback bei Änderung der Operation."""
        # Get internal key from itemData
        op_key = self.operation_combo.itemData(index)
        if op_key is None:
            op_key = self.operation_combo.currentText()  # Fallback
        self._operation = op_key
        self.operation_changed.emit(op_key)

    def _confirm(self):
        """Bestätigt die Operation."""
        self.confirmed.emit()

    def _cancel(self):
        """Bricht die Operation ab."""
        self.cancelled.emit()

    def _on_profile_clear_clicked(self):
        """Callback beim Klick auf Profil-Clear-Button."""
        self.clear_profile()
        self.profile_cleared.emit()

    def _on_path_clear_clicked(self):
        """Callback beim Klick auf Pfad-Clear-Button."""
        self.clear_path()
        self.path_cleared.emit()

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

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 5, 10, 5)
        main_layout.setSpacing(5)

        # Top row: Label, Profile count, Add button
        top_row = QHBoxLayout()

        self.label = QLabel(tr("Loft:"))
        top_row.addWidget(self.label)

        self.profile_count_label = QLabel(tr("0 profiles"))
        self.profile_count_label.setStyleSheet("""
            color: #ffaa00;
            font-size: 12px;
            font-weight: normal;
            border: none;
        """)
        self.profile_count_label.setMinimumWidth(80)
        top_row.addWidget(self.profile_count_label)

        self.add_profile_btn = QPushButton(tr("+ Profile"))
        self.add_profile_btn.setStyleSheet("background: #3a3a3a; font-size: 10px;")
        self.add_profile_btn.clicked.connect(self._on_add_profile)
        top_row.addWidget(self.add_profile_btn)

        # Ruled checkbox
        self.ruled_check = QCheckBox(tr("Ruled"))
        self.ruled_check.setToolTip(tr("Straight lines instead of smooth transitions"))
        self.ruled_check.stateChanged.connect(self._on_ruled_changed)
        top_row.addWidget(self.ruled_check)

        # Operation combo
        self.operation_combo = QComboBox()
        # Store internal keys as item data for comparison, display translated text
        for key in ["New Body", "Join", "Cut", "Intersect"]:
            self.operation_combo.addItem(tr(key), key)
        self.operation_combo.setFixedWidth(90)
        self.operation_combo.currentIndexChanged.connect(self._on_operation_changed_idx)
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
        self.profile_info = QLabel(tr("Select faces on different Z-planes"))
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
        # Return internal key, not translated text
        data = self.operation_combo.currentData()
        return data if data else self.operation_combo.currentText()

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
            self.profile_count_label.setText(tr("0 profiles"))
            self.profile_count_label.setStyleSheet("""
                color: #ffaa00;
                font-size: 12px;
                font-weight: normal;
                border: none;
            """)
        elif count == 1:
            z_info = self._get_z_info(self._profiles[0])
            self.profile_count_label.setText(tr("1 profile ({z_info})").format(z_info=z_info))
            self.profile_count_label.setStyleSheet("""
                color: #ffaa00;
                font-size: 12px;
                font-weight: normal;
                border: none;
            """)
        else:
            z_min = min(self._get_z(p) for p in self._profiles)
            z_max = max(self._get_z(p) for p in self._profiles)
            self.profile_count_label.setText(tr("{count} profiles (Z: {z_min:.0f}-{z_max:.0f})").format(count=count, z_min=z_min, z_max=z_max))
            self.profile_count_label.setStyleSheet("""
                color: #66ff66;
                font-size: 12px;
                font-weight: normal;
                border: none;
            """)

        # OK button enabled only with 2+ profiles
        self.ok_btn.setEnabled(count >= 2)

        # Info label
        if count < 2:
            self.profile_info.setText(tr("Select at least {n} more face(s)").format(n=2 - count))
        else:
            self.profile_info.setText(tr("Ready to loft ({count} profiles)").format(count=count))

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

    def _on_operation_changed_idx(self, index: int):
        """Callback bei Änderung der Operation."""
        # Get internal key from itemData
        op_key = self.operation_combo.itemData(index)
        if op_key is None:
            op_key = self.operation_combo.currentText()  # Fallback
        self._operation = op_key
        self.operation_changed.emit(op_key)

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
        self.setFixedHeight(75)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # Mode-Auswahl
        self.mode_combo = QComboBox()
        # Store internal keys as item data for comparison, display translated text
        for key in ["Move", "Rotate", "Scale"]:
            self.mode_combo.addItem(tr(key), key)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed_idx)
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
        self.grid_combo.setToolTip(tr("Grid (Ctrl+Drag)"))
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

    def _on_mode_changed_idx(self, index: int):
        """Mode-Wechsel"""
        # Get internal key from itemData
        mode_key = self.mode_combo.itemData(index)
        if mode_key is None:
            mode_key = self.mode_combo.currentText()  # Fallback
        mode = mode_key.lower()
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

        self.main_label = QLabel(tr("Hint"))
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


class RevolveInputPanel(QFrame):
    """Input panel for interactive Revolve operation (Fusion-Style)."""

    angle_changed = Signal(float)
    axis_changed = Signal(tuple)
    direction_flipped = Signal()
    operation_changed = Signal(str)
    confirmed = Signal()
    cancelled = Signal()

    AXIS_MAP = {
        'X': (1, 0, 0),
        'Y': (0, 1, 0),
        'Z': (0, 0, 1),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 360.0
        self._axis = (0, 1, 0)
        self._direction = 1
        self._current_operation = "New Body"

        self.setMinimumWidth(580)
        self.setFixedHeight(75)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Revolve:"))

        # Axis toggle buttons
        layout.addWidget(QLabel("Achse"))
        self._axis_buttons = {}
        for axis_name in ('X', 'Y', 'Z'):
            btn = QPushButton(axis_name)
            btn.setCheckable(True)
            btn.setFixedSize(32, 32)
            btn.clicked.connect(lambda checked, a=axis_name: self._on_axis_clicked(a))
            layout.addWidget(btn)
            self._axis_buttons[axis_name] = btn
        self._axis_buttons['Y'].setChecked(True)

        # Angle input
        self.angle_input = ActionSpinBox()
        self.angle_input.setRange(0.1, 360.0)
        self.angle_input.setDecimals(1)
        self.angle_input.setSuffix(" deg")
        self.angle_input.setValue(360.0)
        self.angle_input.valueChanged.connect(self._on_angle_changed)
        self.angle_input.enterPressed.connect(self._confirm)
        self.angle_input.escapePressed.connect(self.cancelled.emit)
        layout.addWidget(self.angle_input)

        # Flip direction button
        self.flip_btn = QPushButton("⇅")
        self.flip_btn.setToolTip(tr("Flip direction (F)"))
        self.flip_btn.setFixedSize(32, 32)
        self.flip_btn.clicked.connect(self._flip_direction)
        layout.addWidget(self.flip_btn)

        # Operation combo with color indicator
        self.op_indicator = QLabel("●")
        self.op_indicator.setFixedWidth(16)
        self.op_indicator.setStyleSheet("color: #6699ff; font-size: 16px;")
        layout.addWidget(self.op_indicator)

        self.op_combo = QComboBox()
        # Store internal keys as item data for comparison, display translated text
        for key in ["New Body", "Join", "Cut", "Intersect"]:
            self.op_combo.addItem(tr(key), key)
        self.op_combo.currentIndexChanged.connect(self._on_operation_changed_idx)
        layout.addWidget(self.op_combo)

        # OK / Cancel
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setStyleSheet("background: #0078d4; color: white; border: none;")
        self.btn_ok.clicked.connect(self._confirm)
        layout.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("X")
        self.btn_cancel.setFixedWidth(30)
        self.btn_cancel.setStyleSheet("background: #d83b01; color: white; border: none;")
        self.btn_cancel.clicked.connect(self.cancelled.emit)
        layout.addWidget(self.btn_cancel)

        self.hide()

    def _on_axis_clicked(self, axis_name):
        self._direction = 1
        for name, btn in self._axis_buttons.items():
            btn.setChecked(name == axis_name)
        self._axis = self.AXIS_MAP[axis_name]
        self.axis_changed.emit(self._axis)

    def _flip_direction(self):
        self._direction *= -1
        self._axis = tuple(-v for v in self._axis)
        self.direction_flipped.emit()

    def _on_angle_changed(self, value):
        self._angle = value
        self.angle_changed.emit(value)

    def _on_operation_changed_idx(self, index: int):
        # Get internal key from itemData
        op_key = self.op_combo.itemData(index)
        if op_key is None:
            op_key = self.op_combo.currentText()  # Fallback
        self._current_operation = op_key
        colors = {
            "New Body": "#6699ff", "Join": "#66ff66",
            "Cut": "#ff6666", "Intersect": "#ffaa66"
        }
        self.op_indicator.setStyleSheet(f"color: {colors.get(op_key, '#6699ff')}; font-size: 16px;")
        self.operation_changed.emit(op_key)

    def _confirm(self):
        self._angle = self.angle_input.value()
        self.confirmed.emit()

    def get_angle(self) -> float:
        return self.angle_input.value()

    def set_angle(self, value: float):
        self.angle_input.blockSignals(True)
        self.angle_input.setValue(value)
        self.angle_input.blockSignals(False)
        self._angle = value

    def get_axis(self) -> tuple:
        return self._axis

    def set_axis(self, axis_name: str):
        if axis_name in self._axis_buttons:
            self._on_axis_clicked(axis_name)

    def get_operation(self) -> str:
        # Return internal key, not translated text
        data = self.op_combo.currentData()
        return data if data else self.op_combo.currentText()

    def set_operation(self, op: str):
        # Use findData to search by internal key, not translated text
        idx = self.op_combo.findData(op)
        if idx >= 0:
            self.op_combo.setCurrentIndex(idx)

    def reset(self):
        self._angle = 360.0
        self._direction = 1
        self.angle_input.blockSignals(True)
        self.angle_input.setValue(360.0)
        self.angle_input.blockSignals(False)
        self._on_axis_clicked('Y')
        self.op_combo.setCurrentIndex(0)

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


class OffsetPlaneInputPanel(QFrame):
    """Input panel for interactive Offset Plane creation."""

    offset_changed = Signal(float)
    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._offset = 0.0

        self.setMinimumWidth(450)
        self.setFixedHeight(75)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
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


class HoleInputPanel(QFrame):
    """Input panel for interactive Hole placement (Fusion-style)."""

    diameter_changed = Signal(float)
    depth_changed = Signal(float)
    hole_type_changed = Signal(str)
    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._diameter = 8.0
        self._depth = 0.0  # 0 = through all

        self.setMinimumWidth(560)
        self.setFixedHeight(75)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        layout.addWidget(QLabel(tr("Hole:")))

        # Hole type
        self.type_combo = QComboBox()
        # Store internal keys as item data for comparison, display translated text
        for key in ["Simple", "Counterbore", "Countersink"]:
            self.type_combo.addItem(tr(key), key)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed_idx)
        layout.addWidget(self.type_combo)

        # Diameter
        layout.addWidget(QLabel("\u2300"))
        self.diameter_input = ActionSpinBox()
        self.diameter_input.setRange(0.1, 500.0)
        self.diameter_input.setDecimals(2)
        self.diameter_input.setSuffix(" mm")
        self.diameter_input.setValue(8.0)
        self.diameter_input.valueChanged.connect(self._on_diameter_changed)
        self.diameter_input.enterPressed.connect(self._confirm)
        self.diameter_input.escapePressed.connect(self.cancelled.emit)
        layout.addWidget(self.diameter_input)

        # Depth
        layout.addWidget(QLabel(tr("Depth:")))
        self.depth_input = ActionSpinBox()
        self.depth_input.setRange(0.0, 10000.0)
        self.depth_input.setDecimals(2)
        self.depth_input.setSuffix(" mm")
        self.depth_input.setValue(0.0)
        self.depth_input.setSpecialValueText(tr("Through All"))
        self.depth_input.valueChanged.connect(self._on_depth_changed)
        self.depth_input.enterPressed.connect(self._confirm)
        self.depth_input.escapePressed.connect(self.cancelled.emit)
        layout.addWidget(self.depth_input)

        # OK / Cancel
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setStyleSheet("background: #ff8800; color: #000; border: none; font-weight: bold;")
        self.btn_ok.clicked.connect(self._confirm)
        layout.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("X")
        self.btn_cancel.setFixedWidth(35)
        self.btn_cancel.setStyleSheet("background: #d83b01; color: white; border: none;")
        self.btn_cancel.clicked.connect(self.cancelled.emit)
        layout.addWidget(self.btn_cancel)

        self.hide()

    def _on_type_changed_idx(self, index: int):
        # Get internal key from itemData
        type_key = self.type_combo.itemData(index)
        if type_key is None:
            type_key = self.type_combo.currentText()
        self.hole_type_changed.emit(type_key.lower())

    def _on_diameter_changed(self, value):
        self._diameter = value
        self.diameter_changed.emit(value)

    def _on_depth_changed(self, value):
        self._depth = value
        self.depth_changed.emit(value)

    def _confirm(self):
        self._diameter = self.diameter_input.value()
        self._depth = self.depth_input.value()
        self.confirmed.emit()

    def get_diameter(self) -> float:
        return self.diameter_input.value()

    def get_depth(self) -> float:
        return self.depth_input.value()

    def get_hole_type(self) -> str:
        # Return internal key, not translated text
        data = self.type_combo.currentData()
        return (data if data else self.type_combo.currentText()).lower()

    def reset(self):
        self._diameter = 8.0
        self._depth = 0.0
        self.diameter_input.blockSignals(True)
        self.diameter_input.setValue(8.0)
        self.diameter_input.blockSignals(False)
        self.depth_input.blockSignals(True)
        self.depth_input.setValue(0.0)
        self.depth_input.blockSignals(False)
        self.type_combo.setCurrentIndex(0)

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


class DraftInputPanel(QFrame):
    """Input panel for interactive Draft (Entformungsschräge) — Fusion-style."""

    angle_changed = Signal(float)
    axis_changed = Signal(str)
    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 5.0
        self._pull_axis = "Z"
        self._selected_face_count = 0

        self.setMinimumWidth(520)
        self.setFixedHeight(75)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Draft:"))

        # Face count indicator
        self.face_label = QLabel("0 Faces")
        self.face_label.setStyleSheet("color: #aaa; font-size: 12px; border: none;")
        layout.addWidget(self.face_label)

        # Angle
        layout.addWidget(QLabel("\u2220"))
        self.angle_input = ActionSpinBox()
        self.angle_input.setRange(0.1, 89.0)
        self.angle_input.setDecimals(1)
        self.angle_input.setSuffix("\u00b0")
        self.angle_input.setValue(5.0)
        self.angle_input.valueChanged.connect(self._on_angle_changed)
        self.angle_input.enterPressed.connect(self._confirm)
        self.angle_input.escapePressed.connect(self.cancelled.emit)
        layout.addWidget(self.angle_input)

        # Pull direction axis buttons
        layout.addWidget(QLabel("Pull:"))
        self._axis_btns = {}
        for axis in ["X", "Y", "Z"]:
            btn = QPushButton(axis)
            btn.setCheckable(True)
            btn.setFixedSize(32, 28)
            btn.clicked.connect(lambda checked, a=axis: self._set_axis(a))
            self._axis_btns[axis] = btn
            layout.addWidget(btn)
        self._axis_btns["Z"].setChecked(True)

        # OK / Cancel
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setStyleSheet("background: #e8a030; color: #000; border: none; font-weight: bold;")
        self.btn_ok.clicked.connect(self._confirm)
        layout.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("X")
        self.btn_cancel.setFixedWidth(35)
        self.btn_cancel.setStyleSheet("background: #d83b01; color: white; border: none;")
        self.btn_cancel.clicked.connect(self.cancelled.emit)
        layout.addWidget(self.btn_cancel)

        self.hide()

    def _set_axis(self, axis):
        self._pull_axis = axis
        for a, btn in self._axis_btns.items():
            btn.setChecked(a == axis)
        self.axis_changed.emit(axis)

    def _on_angle_changed(self, value):
        self._angle = value
        self.angle_changed.emit(value)

    def _confirm(self):
        self._angle = self.angle_input.value()
        self.confirmed.emit()

    def get_angle(self) -> float:
        return self.angle_input.value()

    def get_pull_direction(self) -> tuple:
        axis_map = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}
        return axis_map.get(self._pull_axis, (0, 0, 1))

    def set_face_count(self, count: int):
        self._selected_face_count = count
        self.face_label.setText(f"{count} Face{'s' if count != 1 else ''}")

    def reset(self):
        self._angle = 5.0
        self._pull_axis = "Z"
        self._selected_face_count = 0
        self.angle_input.blockSignals(True)
        self.angle_input.setValue(5.0)
        self.angle_input.blockSignals(False)
        self._set_axis("Z")
        self.face_label.setText("0 Faces")

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


class SplitInputPanel(QFrame):
    """Input panel for interactive Split Body — PrusaSlicer-style."""

    plane_changed = Signal(str)
    position_changed = Signal(float)
    angle_changed = Signal(float)
    keep_changed = Signal(str)
    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._plane = "XY"
        self._position = 0.0
        self._angle = 0.0
        self._keep = "above"

        self.setMinimumWidth(640)
        self.setFixedHeight(75)

        self.setStyleSheet("""
            QFrame {
                background: #2d2d30;
                border: 2px solid #5599dd;
                border-radius: 8px;
            }
            QLabel { color: #fff; font-weight: bold; border: none; font-size: 12px; }
            QDoubleSpinBox {
                background: #1e1e1e; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 6px 8px; font-weight: bold; font-size: 13px;
            }
            QPushButton {
                background: #444; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 5px 10px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background: #555; border-color: #777; }
            QPushButton:checked { background: #5599dd; color: #000; border-color: #5599dd; }
            QComboBox {
                background: #1e1e1e; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 4px; font-size: 12px;
            }
            QComboBox QAbstractItemView {
                background: #1e1e1e; color: #fff; selection-background-color: #0078d4; border: 1px solid #555;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Split:"))

        # Plane buttons
        self._plane_btns = {}
        for plane in ["XY", "XZ", "YZ"]:
            btn = QPushButton(plane)
            btn.setCheckable(True)
            btn.setFixedSize(36, 28)
            btn.clicked.connect(lambda checked, p=plane: self._set_plane(p))
            self._plane_btns[plane] = btn
            layout.addWidget(btn)
        self._plane_btns["XY"].setChecked(True)

        # Position
        layout.addWidget(QLabel("Pos:"))
        self.pos_input = ActionSpinBox()
        self.pos_input.setRange(-1000.0, 1000.0)
        self.pos_input.setDecimals(2)
        self.pos_input.setSuffix(" mm")
        self.pos_input.setValue(0.0)
        self.pos_input.setSingleStep(1.0)
        self.pos_input.valueChanged.connect(self._on_pos_changed)
        self.pos_input.enterPressed.connect(self._confirm)
        self.pos_input.escapePressed.connect(self.cancelled.emit)
        layout.addWidget(self.pos_input)

        # Angle
        layout.addWidget(QLabel(tr("Angle:")))
        self.angle_input = ActionSpinBox()
        self.angle_input.setRange(-89.0, 89.0)
        self.angle_input.setDecimals(1)
        self.angle_input.setSuffix("°")
        self.angle_input.setValue(0.0)
        self.angle_input.setSingleStep(5.0)
        self.angle_input.valueChanged.connect(self._on_angle_changed)
        self.angle_input.enterPressed.connect(self._confirm)
        self.angle_input.escapePressed.connect(self.cancelled.emit)
        layout.addWidget(self.angle_input)

        # Keep side
        layout.addWidget(QLabel(tr("Keep:")))
        self.keep_combo = QComboBox()
        # Store internal keys as item data for comparison, display translated text
        for key in ["Above", "Below", "Both"]:
            self.keep_combo.addItem(tr(key), key)
        self.keep_combo.currentIndexChanged.connect(self._on_keep_changed_idx)
        self.keep_combo.setFixedWidth(80)
        layout.addWidget(self.keep_combo)

        # OK / Cancel
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setStyleSheet("background: #5599dd; color: #000; border: none; font-weight: bold;")
        self.btn_ok.clicked.connect(self._confirm)
        layout.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("X")
        self.btn_cancel.setFixedWidth(35)
        self.btn_cancel.setStyleSheet("background: #d83b01; color: white; border: none;")
        self.btn_cancel.clicked.connect(self.cancelled.emit)
        layout.addWidget(self.btn_cancel)

        self.hide()

    def _set_plane(self, plane):
        self._plane = plane
        for p, btn in self._plane_btns.items():
            btn.setChecked(p == plane)
        self.plane_changed.emit(plane)

    def _on_pos_changed(self, value):
        self._position = value
        self.position_changed.emit(value)

    def _on_angle_changed(self, value):
        self._angle = value
        self.angle_changed.emit(value)

    def _on_keep_changed_idx(self, index: int):
        # Get internal key from itemData
        keep_key = self.keep_combo.itemData(index)
        if keep_key is None:
            keep_key = self.keep_combo.currentText()
        self._keep = keep_key.lower()
        self.keep_changed.emit(self._keep)

    def _confirm(self):
        self._position = self.pos_input.value()
        self.confirmed.emit()

    def get_plane(self) -> str:
        return self._plane

    def get_position(self) -> float:
        return self.pos_input.value()

    def set_position(self, value: float):
        self.pos_input.blockSignals(True)
        self.pos_input.setValue(value)
        self.pos_input.blockSignals(False)
        self._position = value

    def get_angle(self) -> float:
        return self.angle_input.value()

    def get_keep_side(self) -> str:
        return self._keep

    def reset(self):
        self._plane = "XY"
        self._position = 0.0
        self._angle = 0.0
        self._keep = "above"
        self.pos_input.blockSignals(True)
        self.pos_input.setValue(0.0)
        self.pos_input.blockSignals(False)
        self.angle_input.blockSignals(True)
        self.angle_input.setValue(0.0)
        self.angle_input.blockSignals(False)
        self._set_plane("XY")
        self.keep_combo.setCurrentText("Above")

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



class PatternInputPanel(QFrame):
    """
    Input panel for Pattern/Array operations (CAD-Style).

    Features:
    - Linear Pattern: N copies along an axis with spacing
    - Circular Pattern: N copies rotated around an axis
    - Live preview while adjusting parameters
    """

    # Signals
    parameters_changed = Signal(dict)  # Emitted when any parameter changes
    confirmed = Signal()
    cancelled = Signal()
    center_pick_requested = Signal()  # Emitted when user wants to pick custom center

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target_body = None
        self._pattern_type = "linear"  # "linear" or "circular"

        self.setMinimumWidth(500)
        self.setFixedHeight(70)

        self.setStyleSheet("""
            QFrame {
                background: #2d2d30;
                border: 2px solid #0078d4;
                border-radius: 8px;
            }
            QLabel { color: #fff; font-weight: bold; border: none; font-size: 12px; }
            QDoubleSpinBox, QSpinBox {
                background: #1e1e1e; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 3px; font-weight: bold; font-size: 12px;
            }
            QComboBox {
                background: #1e1e1e; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 3px; min-width: 60px;
            }
            QComboBox QAbstractItemView {
                background: #1e1e1e; color: #fff; selection-background-color: #0078d4; border: 1px solid #555;
            }
            QPushButton {
                background: #444; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 5px 8px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background: #555; }
            QPushButton:checked { background: #0078d4; border-color: #0078d4; }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)

        # Pattern Type Toggle
        self.linear_btn = QPushButton("Linear")
        self.linear_btn.setCheckable(True)
        self.linear_btn.setChecked(True)
        self.linear_btn.clicked.connect(lambda: self._set_pattern_type("linear"))
        layout.addWidget(self.linear_btn)

        self.circular_btn = QPushButton("Circular")
        self.circular_btn.setCheckable(True)
        self.circular_btn.clicked.connect(lambda: self._set_pattern_type("circular"))
        layout.addWidget(self.circular_btn)

        # Separator
        sep = QLabel("|")
        sep.setStyleSheet("color: #555; font-weight: normal;")
        layout.addWidget(sep)

        # Count
        layout.addWidget(QLabel("Count:"))
        from PySide6.QtWidgets import QSpinBox
        self.count_spin = QSpinBox()
        self.count_spin.setRange(2, 100)
        self.count_spin.setValue(3)
        self.count_spin.valueChanged.connect(self._emit_parameters)
        layout.addWidget(self.count_spin)

        # Linear: Spacing
        self.spacing_label = QLabel("Spacing:")
        layout.addWidget(self.spacing_label)
        self.spacing_spin = QDoubleSpinBox()
        self.spacing_spin.setRange(0.1, 10000)
        self.spacing_spin.setValue(10.0)
        self.spacing_spin.setSuffix(" mm")
        self.spacing_spin.setDecimals(2)
        self.spacing_spin.valueChanged.connect(self._emit_parameters)
        layout.addWidget(self.spacing_spin)

        # Circular: Angle
        self.angle_label = QLabel(tr("Angle:"))
        self.angle_label.hide()
        layout.addWidget(self.angle_label)
        self.angle_spin = QDoubleSpinBox()
        self.angle_spin.setRange(1, 360)
        self.angle_spin.setValue(360)
        self.angle_spin.setSuffix("°")
        self.angle_spin.setDecimals(1)
        self.angle_spin.valueChanged.connect(self._emit_parameters)
        self.angle_spin.hide()
        layout.addWidget(self.angle_spin)

        # Circular: Center Selection
        self.center_label = QLabel(tr("Center:"))
        self.center_label.hide()
        layout.addWidget(self.center_label)
        self.center_combo = QComboBox()
        # Store internal keys as item data for comparison, display translated text
        for key in ["Body Center", "Origin (0,0,0)", "Custom..."]:
            self.center_combo.addItem(tr(key), key)
        self.center_combo.currentIndexChanged.connect(self._on_center_changed_idx)
        self.center_combo.hide()
        layout.addWidget(self.center_combo)

        # Custom center coordinates (hidden by default)
        self._custom_center = (0.0, 0.0, 0.0)

        # Axis
        layout.addWidget(QLabel(tr("Axis:")))
        self.axis_combo = QComboBox()
        self.axis_combo.addItems(["X", "Y", "Z"])
        self.axis_combo.currentTextChanged.connect(self._emit_parameters)
        layout.addWidget(self.axis_combo)

        # Stretch
        layout.addStretch()

        # OK Button
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setStyleSheet("background: #0078d4; border: none; min-width: 50px;")
        self.ok_btn.clicked.connect(self._confirm)
        layout.addWidget(self.ok_btn)

        # Cancel Button
        self.cancel_btn = QPushButton("✕")
        self.cancel_btn.setFixedWidth(30)
        self.cancel_btn.setStyleSheet("background: #d83b01; border: none;")
        self.cancel_btn.clicked.connect(self._cancel)
        layout.addWidget(self.cancel_btn)

        self.hide()

    def _set_pattern_type(self, ptype: str):
        """Switch between linear and circular pattern."""
        self._pattern_type = ptype

        # Update button states
        self.linear_btn.setChecked(ptype == "linear")
        self.circular_btn.setChecked(ptype == "circular")

        # Show/hide relevant controls
        if ptype == "linear":
            self.spacing_label.show()
            self.spacing_spin.show()
            self.angle_label.hide()
            self.angle_spin.hide()
            self.center_label.hide()
            self.center_combo.hide()
        else:
            self.spacing_label.hide()
            self.spacing_spin.hide()
            self.angle_label.show()
            self.angle_spin.show()
            self.center_label.show()
            self.center_combo.show()

        self._emit_parameters()

    def _on_center_changed_idx(self, index: int):
        """Handle center selection change."""
        # Get internal key from itemData
        center_key = self.center_combo.itemData(index)
        if center_key is None:
            center_key = self.center_combo.currentText()
        if center_key == "Custom...":
            # Emit signal to request point selection in viewport
            self.center_pick_requested.emit()
        self._emit_parameters()

    def _emit_parameters(self):
        """Emit current parameters for live preview."""
        params = self.get_pattern_data()
        if params:
            self.parameters_changed.emit(params)

    def _confirm(self):
        self.confirmed.emit()

    def _cancel(self):
        self.cancelled.emit()

    def set_target_body(self, body):
        self._target_body = body

    def get_target_body(self):
        return self._target_body

    def get_pattern_data(self) -> dict:
        """Returns the current pattern configuration."""
        if self._pattern_type == "linear":
            return {
                "type": "linear",
                "count": self.count_spin.value(),
                "spacing": self.spacing_spin.value(),
                "axis": self.axis_combo.currentText()
            }
        else:
            # Determine center mode - use internal key from itemData
            center_key = self.center_combo.currentData()
            if center_key is None:
                center_key = self.center_combo.currentText()
            if center_key == "Origin (0,0,0)":
                center_mode = "origin"
                center = (0.0, 0.0, 0.0)
            elif center_key == "Custom...":
                center_mode = "custom"
                center = self._custom_center
            else:  # "Body Center"
                center_mode = "body_center"
                center = None  # Will be computed from body

            return {
                "type": "circular",
                "count": self.count_spin.value(),
                "angle": self.angle_spin.value(),
                "axis": self.axis_combo.currentText(),
                "full_circle": self.angle_spin.value() >= 360,
                "center_mode": center_mode,
                "center": center
            }

    def set_custom_center(self, x: float, y: float, z: float):
        """Set a custom center point (from viewport pick)."""
        self._custom_center = (x, y, z)
        # Update combo to show custom selection
        self.center_combo.setCurrentText("Custom...")
        self._emit_parameters()

    def reset(self):
        """Reset to default values."""
        self._pattern_type = "linear"
        self.linear_btn.setChecked(True)
        self.circular_btn.setChecked(False)
        self.count_spin.setValue(3)
        self.spacing_spin.setValue(10.0)
        self.angle_spin.setValue(360)
        self.axis_combo.setCurrentText("X")
        self._set_pattern_type("linear")

    def show_at(self, pos_widget):
        """Show panel centered at bottom of viewport."""
        self.show()
        self.raise_()
        if pos_widget:
            parent = pos_widget.parent() if pos_widget.parent() else pos_widget
            x = (parent.width() - self.width()) // 2
            y = parent.height() - self.height() - 50
            if y < 0:
                y = 50
            self.move(x, y)


class NSidedPatchInputPanel(QFrame):
    """
    Input panel for N-Sided Patch operations.
    Uses edge selection mode (like Fillet/Chamfer) to select boundary edges.
    """

    # Signals
    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target_body = None
        self._degree = 3
        self._tangent = True

        self.setMinimumWidth(420)
        self.setFixedHeight(75)

        self.setStyleSheet("""
            QFrame {
                background: #2d2d30;
                border: 2px solid #0078d4;
                border-radius: 8px;
            }
            QLabel { color: #fff; font-weight: bold; border: none; font-size: 12px; }
            QSpinBox {
                background: #1e1e1e; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 3px; font-weight: bold; font-size: 12px;
                min-width: 50px;
            }
            QCheckBox { color: #fff; font-size: 12px; }
            QPushButton {
                background: #444; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 5px 8px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background: #555; }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # Label
        self.label = QLabel("N-Sided Patch:")
        layout.addWidget(self.label)

        # Edge count display
        self.edge_count_label = QLabel("0 Edges")
        self.edge_count_label.setStyleSheet("""
            color: #ff6666;
            font-size: 12px;
            font-weight: normal;
            border: none;
            padding-left: 5px;
        """)
        self.edge_count_label.setMinimumWidth(70)
        layout.addWidget(self.edge_count_label)

        # Degree
        layout.addWidget(QLabel("Degree:"))
        from PySide6.QtWidgets import QSpinBox
        self.degree_spin = QSpinBox()
        self.degree_spin.setRange(2, 6)
        self.degree_spin.setValue(3)
        layout.addWidget(self.degree_spin)

        # Tangent checkbox
        self.tangent_check = QCheckBox("G1")
        self.tangent_check.setChecked(True)
        self.tangent_check.setToolTip("Match tangency with adjacent faces")
        layout.addWidget(self.tangent_check)

        layout.addStretch()

        # OK Button
        self.ok_btn = QPushButton("Fill")
        self.ok_btn.setStyleSheet("background: #0078d4; border: none; min-width: 50px;")
        self.ok_btn.clicked.connect(self._confirm)
        layout.addWidget(self.ok_btn)

        # Cancel Button
        self.cancel_btn = QPushButton("✕")
        self.cancel_btn.setFixedWidth(30)
        self.cancel_btn.setStyleSheet("background: #d83b01; border: none;")
        self.cancel_btn.clicked.connect(self._cancel)
        layout.addWidget(self.cancel_btn)

        self.hide()

    def _confirm(self):
        self.confirmed.emit()

    def _cancel(self):
        self.cancelled.emit()

    def set_target_body(self, body):
        self._target_body = body

    def get_target_body(self):
        return self._target_body

    def update_edge_count(self, count: int):
        """Update edge count display."""
        if count < 3:
            self.edge_count_label.setText(f"{count} Edges (min 3)")
            self.edge_count_label.setStyleSheet("""
                color: #ff6666;
                font-size: 12px;
                font-weight: normal;
                border: none;
            """)
            self.ok_btn.setEnabled(False)
        else:
            self.edge_count_label.setText(f"{count} Edges")
            self.edge_count_label.setStyleSheet("""
                color: #66ff66;
                font-size: 12px;
                font-weight: normal;
                border: none;
            """)
            self.ok_btn.setEnabled(True)

    def get_degree(self) -> int:
        return self.degree_spin.value()

    def get_tangent(self) -> bool:
        return self.tangent_check.isChecked()

    def reset(self):
        """Reset to default values."""
        self.degree_spin.setValue(3)
        self.tangent_check.setChecked(True)
        self.update_edge_count(0)

    def show_at(self, pos_widget):
        """Show panel centered at bottom of viewport."""
        self.show()
        self.raise_()
        if pos_widget:
            parent = pos_widget.parent() if pos_widget.parent() else pos_widget
            x = (parent.width() - self.width()) // 2
            y = parent.height() - self.height() - 50
            if y < 0:
                y = 50
            self.move(x, y)


class LatticeInputPanel(QFrame):
    """
    Input panel for Lattice/Gitterstruktur operations.
    Allows body selection from viewport and inline parameter editing.
    """

    # Signals
    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target_body = None

        self.setMinimumWidth(580)
        self.setFixedHeight(70)

        self.setStyleSheet("""
            QFrame {
                background: #2d2d30;
                border: 2px solid #0078d4;
                border-radius: 8px;
            }
            QLabel { color: #fff; font-weight: bold; border: none; font-size: 12px; }
            QDoubleSpinBox, QSpinBox {
                background: #1e1e1e; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 3px; font-weight: bold; font-size: 12px;
            }
            QComboBox {
                background: #1e1e1e; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 3px; min-width: 100px;
            }
            QPushButton {
                background: #444; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 5px 8px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background: #555; }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)

        # Label
        layout.addWidget(QLabel(tr("Lattice:")))

        # Cell Type
        layout.addWidget(QLabel(tr("Type:")))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["BCC", "FCC", "Octet", "Diamond"])  # Technical terms, not translated
        layout.addWidget(self.type_combo)

        # Cell Size
        layout.addWidget(QLabel(tr("Cell:")))
        self.cell_spin = QDoubleSpinBox()
        self.cell_spin.setRange(1.0, 100.0)
        self.cell_spin.setValue(5.0)
        self.cell_spin.setSuffix(" mm")
        self.cell_spin.setDecimals(1)
        layout.addWidget(self.cell_spin)

        # Beam Radius
        layout.addWidget(QLabel(tr("Beam:")))
        self.beam_spin = QDoubleSpinBox()
        self.beam_spin.setRange(0.1, 10.0)
        self.beam_spin.setValue(0.5)
        self.beam_spin.setSuffix(" mm")
        self.beam_spin.setDecimals(2)
        layout.addWidget(self.beam_spin)

        # Shell Thickness
        layout.addWidget(QLabel("Shell:"))
        self.shell_spin = QDoubleSpinBox()
        self.shell_spin.setRange(0.0, 50.0)
        self.shell_spin.setValue(1.0)
        self.shell_spin.setSuffix(" mm")
        self.shell_spin.setDecimals(1)
        self.shell_spin.setToolTip("0 = no shell, >0 = preserve outer wall")
        layout.addWidget(self.shell_spin)

        # Stretch
        layout.addStretch()

        # OK Button
        self.ok_btn = QPushButton("Generate")
        self.ok_btn.setStyleSheet("background: #0078d4; border: none; min-width: 100px;")
        self.ok_btn.clicked.connect(self._confirm)
        layout.addWidget(self.ok_btn)

        # Cancel Button
        self.cancel_btn = QPushButton("✕")
        self.cancel_btn.setFixedWidth(30)
        self.cancel_btn.setStyleSheet("background: #d83b01; border: none;")
        self.cancel_btn.clicked.connect(self._cancel)
        layout.addWidget(self.cancel_btn)

        self.hide()

    def set_target_body(self, body):
        """Set the target body for lattice generation."""
        self._target_body = body

    def get_target_body(self):
        return self._target_body

    def get_parameters(self) -> dict:
        """Return current lattice parameters."""
        return {
            "cell_type": self.type_combo.currentText(),
            "cell_size": self.cell_spin.value(),
            "beam_radius": self.beam_spin.value(),
            "shell_thickness": self.shell_spin.value(),
        }

    def reset(self):
        """Reset to default values."""
        self.type_combo.setCurrentIndex(0)
        self.cell_spin.setValue(5.0)
        self.beam_spin.setValue(0.5)
        self.shell_spin.setValue(1.0)

    def _confirm(self):
        self.confirmed.emit()

    def _cancel(self):
        self.cancelled.emit()

    def show_at(self, pos_widget):
        """Show panel centered at bottom of viewport."""
        self.show()
        self.raise_()
        if pos_widget:
            parent = pos_widget.parent() if pos_widget.parent() else pos_widget
            x = (parent.width() - self.width()) // 2
            y = parent.height() - self.height() - 50
            if y < 0:
                y = 50
            self.move(x, y)


# ISO metric coarse threads: (nominal_dia, pitch)
METRIC_THREADS_PANEL = {
    "M3": (3.0, 0.5),
    "M4": (4.0, 0.7),
    "M5": (5.0, 0.8),
    "M6": (6.0, 1.0),
    "M8": (8.0, 1.25),
    "M10": (10.0, 1.5),
    "M12": (12.0, 1.75),
    "M16": (16.0, 2.0),
    "M20": (20.0, 2.5),
    "M24": (24.0, 3.0),
}


class ThreadInputPanel(QFrame):
    """Input panel for interactive Thread placement on cylindrical faces (Fusion-style)."""

    diameter_changed = Signal(float)
    pitch_changed = Signal(float)
    depth_changed = Signal(float)
    thread_type_changed = Signal(str)  # "external" or "internal"
    tolerance_changed = Signal(float)
    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._diameter = 10.0
        self._pitch = 1.5
        self._depth = 20.0
        self._thread_type = "external"
        self._tolerance_offset = 0.0
        self._detected_diameter = None  # Auto-detected from cylindrical face

        self.setMinimumWidth(680)
        self.setFixedHeight(75)

        self.setStyleSheet("""
            QFrame {
                background: #2d2d30;
                border: 2px solid #00aaff;
                border-radius: 8px;
            }
            QLabel { color: #fff; font-weight: bold; border: none; font-size: 12px; }
            QDoubleSpinBox {
                background: #1e1e1e; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 6px 8px; font-weight: bold; font-size: 13px;
            }
            QComboBox {
                background: #1e1e1e; border: 1px solid #555;
                border-radius: 4px; color: #fff; padding: 4px; min-width: 80px;
            }
            QPushButton {
                background: #444; color: #fff; border: 1px solid #555;
                border-radius: 4px; padding: 5px 12px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background: #555; border-color: #777; }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        layout.addWidget(QLabel(tr("Thread:")))

        # Thread type (External/Internal)
        self.type_combo = QComboBox()
        # Store internal keys as item data for comparison, display translated text
        for key in ["External", "Internal"]:
            self.type_combo.addItem(tr(key), key)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed_idx)
        layout.addWidget(self.type_combo)

        # Size preset
        self.size_combo = QComboBox()
        self.size_combo.addItem("Custom")
        for name in METRIC_THREADS_PANEL:
            self.size_combo.addItem(name)
        self.size_combo.setCurrentText("M10")
        self.size_combo.currentTextChanged.connect(self._on_preset_changed)
        layout.addWidget(self.size_combo)

        # Diameter
        layout.addWidget(QLabel("\u2300"))  # ⌀
        self.diameter_input = ActionSpinBox()
        self.diameter_input.setRange(0.5, 500.0)
        self.diameter_input.setDecimals(2)
        self.diameter_input.setSuffix(" mm")
        self.diameter_input.setValue(10.0)
        self.diameter_input.valueChanged.connect(self._on_diameter_changed)
        self.diameter_input.enterPressed.connect(self._confirm)
        self.diameter_input.escapePressed.connect(self.cancelled.emit)
        layout.addWidget(self.diameter_input)

        # Pitch
        layout.addWidget(QLabel("P:"))
        self.pitch_input = ActionSpinBox()
        self.pitch_input.setRange(0.1, 10.0)
        self.pitch_input.setDecimals(2)
        self.pitch_input.setSuffix(" mm")
        self.pitch_input.setValue(1.5)
        self.pitch_input.valueChanged.connect(self._on_pitch_changed)
        self.pitch_input.enterPressed.connect(self._confirm)
        self.pitch_input.escapePressed.connect(self.cancelled.emit)
        layout.addWidget(self.pitch_input)

        # Depth
        layout.addWidget(QLabel(tr("Depth:")))
        self.depth_input = ActionSpinBox()
        self.depth_input.setRange(0.1, 10000.0)
        self.depth_input.setDecimals(2)
        self.depth_input.setSuffix(" mm")
        self.depth_input.setValue(20.0)
        self.depth_input.valueChanged.connect(self._on_depth_changed)
        self.depth_input.enterPressed.connect(self._confirm)
        self.depth_input.escapePressed.connect(self.cancelled.emit)
        layout.addWidget(self.depth_input)

        # Tolerance offset
        layout.addWidget(QLabel("Tol:"))
        self.tolerance_input = ActionSpinBox()
        self.tolerance_input.setRange(-1.0, 1.0)
        self.tolerance_input.setDecimals(3)
        self.tolerance_input.setSuffix(" mm")
        self.tolerance_input.setValue(0.0)
        self.tolerance_input.valueChanged.connect(self._on_tolerance_changed)
        self.tolerance_input.enterPressed.connect(self._confirm)
        self.tolerance_input.escapePressed.connect(self.cancelled.emit)
        layout.addWidget(self.tolerance_input)

        # OK / Cancel
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setStyleSheet("background: #00aaff; color: #000; border: none; font-weight: bold;")
        self.btn_ok.clicked.connect(self._confirm)
        layout.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("X")
        self.btn_cancel.setFixedWidth(35)
        self.btn_cancel.setStyleSheet("background: #d83b01; color: white; border: none;")
        self.btn_cancel.clicked.connect(self.cancelled.emit)
        layout.addWidget(self.btn_cancel)

        self.hide()

    def _on_type_changed_idx(self, index: int):
        # Get internal key from itemData
        type_key = self.type_combo.itemData(index)
        if type_key is None:
            type_key = self.type_combo.currentText()
        self._thread_type = type_key.lower()
        self.thread_type_changed.emit(self._thread_type)

    def _on_preset_changed(self, text):
        if text in METRIC_THREADS_PANEL:
            dia, pitch = METRIC_THREADS_PANEL[text]
            self.diameter_input.blockSignals(True)
            self.diameter_input.setValue(dia)
            self.diameter_input.blockSignals(False)
            self._diameter = dia
            self.pitch_input.blockSignals(True)
            self.pitch_input.setValue(pitch)
            self.pitch_input.blockSignals(False)
            self._pitch = pitch
            self.diameter_changed.emit(dia)
            self.pitch_changed.emit(pitch)

    def _on_diameter_changed(self, value):
        self._diameter = value
        self.diameter_changed.emit(value)

    def _on_pitch_changed(self, value):
        self._pitch = value
        self.pitch_changed.emit(value)

    def _on_depth_changed(self, value):
        self._depth = value
        self.depth_changed.emit(value)

    def _on_tolerance_changed(self, value):
        self._tolerance_offset = value
        self.tolerance_changed.emit(value)

    def _confirm(self):
        self._diameter = self.diameter_input.value()
        self._pitch = self.pitch_input.value()
        self._depth = self.depth_input.value()
        self._tolerance_offset = self.tolerance_input.value()
        self.confirmed.emit()

    def get_diameter(self) -> float:
        return self.diameter_input.value()

    def get_pitch(self) -> float:
        return self.pitch_input.value()

    def get_depth(self) -> float:
        return self.depth_input.value()

    def get_thread_type(self) -> str:
        return self._thread_type

    def get_tolerance_offset(self) -> float:
        return self.tolerance_input.value()

    def set_detected_diameter(self, diameter: float):
        """Set diameter from auto-detected cylindrical face."""
        self._detected_diameter = diameter
        # Find closest metric thread
        closest = None
        min_diff = float('inf')
        for name, (dia, pitch) in METRIC_THREADS_PANEL.items():
            diff = abs(dia - diameter)
            if diff < min_diff:
                min_diff = diff
                closest = name

        if closest and min_diff < 1.0:
            # Close enough to a standard size
            self.size_combo.setCurrentText(closest)
        else:
            # Custom diameter
            self.size_combo.setCurrentText("Custom")
            self.diameter_input.blockSignals(True)
            self.diameter_input.setValue(diameter)
            self.diameter_input.blockSignals(False)
            self._diameter = diameter

    def reset(self):
        self._diameter = 10.0
        self._pitch = 1.5
        self._depth = 20.0
        self._tolerance_offset = 0.0
        self._detected_diameter = None
        self.diameter_input.blockSignals(True)
        self.diameter_input.setValue(10.0)
        self.diameter_input.blockSignals(False)
        self.pitch_input.blockSignals(True)
        self.pitch_input.setValue(1.5)
        self.pitch_input.blockSignals(False)
        self.depth_input.blockSignals(True)
        self.depth_input.setValue(20.0)
        self.depth_input.blockSignals(False)
        self.tolerance_input.blockSignals(True)
        self.tolerance_input.setValue(0.0)
        self.tolerance_input.blockSignals(False)
        self.type_combo.setCurrentIndex(0)
        self.size_combo.setCurrentText("M10")

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