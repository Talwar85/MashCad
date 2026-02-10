"""
MashCad - Input Panels
Fixed: TransformPanel Signal Blocking for circular updates.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QDoubleSpinBox, QCheckBox, QComboBox,
    QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QEvent, QPoint, QTimer
from PySide6.QtGui import QFont, QKeyEvent, QRegion, QPainterPath

from i18n import tr
from gui.design_tokens import DesignTokens


class RoundedPanelFrame(QFrame):
    """QFrame with a rounded-rect mask so corners don't show black."""
    _RADIUS = 10

    def resizeEvent(self, event):
        super().resizeEvent(event)
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(),
                            self._RADIUS, self._RADIUS)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

# --- Panel positioning helpers ---
def _panel_area_in_parent(panel: QWidget, pos_widget: QWidget):
    parent = panel.parent() or pos_widget
    if parent is None:
        return None
    if pos_widget is None:
        pos_widget = parent

    if pos_widget is parent:
        return (0, 0, parent.width(), parent.height())

    if pos_widget.parent() is parent:
        geom = pos_widget.geometry()
        return (geom.x(), geom.y(), geom.width(), geom.height())

    top_left = pos_widget.mapTo(parent, QPoint(0, 0))
    return (top_left.x(), top_left.y(), pos_widget.width(), pos_widget.height())


def _position_panel_right_mid(panel: QWidget, pos_widget: QWidget = None, y_offset: int = 0):
    parent = panel.parent() or pos_widget
    if parent is None:
        return

    area = _panel_area_in_parent(panel, pos_widget)
    if area is None:
        return

    panel.adjustSize()
    area_x, area_y, area_w, area_h = area
    margin = 12

    x = area_x + area_w - panel.width() - margin
    y = area_y + (area_h - panel.height()) // 2 + y_offset

    tp = getattr(parent, "transform_panel", None)
    if tp and tp.isVisible():
        x = min(x, tp.x() - panel.width() - margin)
        y = tp.y() + (tp.height() - panel.height()) // 2

    tb = getattr(parent, "transform_toolbar", None)
    if tb and tb.isVisible():
        tb_pos = tb.mapTo(parent, QPoint(0, 0))
        x = min(x, tb_pos.x() - panel.width() - margin)

    x = max(area_x + margin, min(x, area_x + area_w - panel.width() - margin))
    y = max(area_y + margin, min(y, area_y + area_h - panel.height() - margin))

    panel.move(x, y)
    panel.raise_()

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

class ExtrudeInputPanel(RoundedPanelFrame):
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
        self.setMinimumWidth(380)
        self.setMaximumWidth(520)
        self.setMinimumHeight(130)

        # DesignTokens f?r konsistentes Styling
        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.label = QLabel(tr("Extrude:"))
        self.label.setObjectName("panelTitle")
        header.addWidget(self.label)
        header.addStretch()

        # Operation mit Farb-Indikator
        self.op_indicator = QLabel("•")
        self.op_indicator.setFixedWidth(14)
        self.op_indicator.setStyleSheet("color: #8aa0c8; font-size: 14px;")
        header.addWidget(self.op_indicator)

        self.op_combo = QComboBox()
        # Store internal keys as item data for comparison, display translated text
        for key in ["New Body", "Join", "Cut", "Intersect"]:
            self.op_combo.addItem(tr(key), key)
        self.op_combo.currentIndexChanged.connect(self._on_operation_changed_idx)
        header.addWidget(self.op_combo)

        layout.addLayout(header)

        body = QGridLayout()
        body.setHorizontalSpacing(8)
        body.setVerticalSpacing(6)

        dist_label = QLabel(tr("Distance:"))
        body.addWidget(dist_label, 0, 0)

        self.height_input = ActionSpinBox()
        self.height_input.setRange(-99999.0, 99999.0)
        self.height_input.setDecimals(2)
        self.height_input.setSuffix(" mm")
        self.height_input.setValue(0.0)

        self.height_input.valueChanged.connect(self._on_height_changed)
        self.height_input.enterPressed.connect(self._confirm)
        self.height_input.escapePressed.connect(self.cancelled.emit)

        body.addWidget(self.height_input, 0, 1)

        # Flip Direction Button
        self.flip_btn = QPushButton("<->")
        self.flip_btn.setToolTip(tr("Flip direction (F)"))
        self.flip_btn.setObjectName("ghost")
        self.flip_btn.clicked.connect(self._flip_direction)
        body.addWidget(self.flip_btn, 0, 2)

        # "To Face" Button
        self.to_face_btn = QPushButton("To")
        self.to_face_btn.setToolTip(tr("Extrude to face (T)"))
        self.to_face_btn.setCheckable(True)
        self.to_face_btn.setObjectName("toggle")
        self.to_face_btn.clicked.connect(self._on_to_face_clicked)
        body.addWidget(self.to_face_btn, 0, 3)

        body.setColumnStretch(1, 1)
        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)

        self.btn_vis = QPushButton("Vis")
        self.btn_vis.setCheckable(False)  # 3-Stufen-Toggle statt an/aus
        self.btn_vis.setToolTip(tr("Bodies visible (click -> X-Ray)"))
        self.btn_vis.clicked.connect(self._toggle_vis)
        self.btn_vis.setObjectName("ghost")
        actions.addWidget(self.btn_vis)

        actions.addStretch()

        self.btn_ok = QPushButton("OK")
        self.btn_ok.setObjectName("primary")
        self.btn_ok.clicked.connect(self._confirm)
        actions.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("X")
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.clicked.connect(self.cancelled.emit)
        actions.addWidget(self.btn_cancel)

        layout.addLayout(actions)

        self.hide()

    def _on_operation_changed_idx(self, index: int):
        """Aktualisiert Farb-Indikator und emittiert Signal"""
        # Get internal key from itemData
        op_key = self.op_combo.itemData(index)
        if op_key is None:
            op_key = self.op_combo.currentText()  # Fallback
        self._current_operation = op_key
        colors = {
            "New Body": "#8aa0c8",  # Muted blue
            "Join": "#7fa889",      # Muted green
            "Cut": "#c98b8b",       # Muted red
            "Intersect": "#c9a87f"  # Muted orange
        }
        self.op_indicator.setStyleSheet(f"color: {colors.get(op_key, '#8aa0c8')}; font-size: 14px;")

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
            "New Body": "#8aa0c8",
            "Join": "#7fa889", 
            "Cut": "#c98b8b",
            "Intersect": "#c9a87f"
        }
        return colors.get(self._current_operation, "#8aa0c8")

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
        _position_panel_right_mid(self, pos_widget)
        self.height_input.setFocus()
        self.height_input.selectAll()


class FilletChamferPanel(RoundedPanelFrame):
    """Input panel for Fillet/Chamfer operations"""
    
    radius_changed = Signal(float)
    confirmed = Signal()
    cancelled = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._radius = 2.0
        self._mode = "fillet"
        self._target_body = None

        self.setMinimumWidth(340)
        self.setMaximumWidth(420)
        self.setMinimumHeight(120)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.label = QLabel(tr("Fillet:"))
        self.label.setObjectName("panelTitle")
        header.addWidget(self.label)
        header.addStretch()

        # Kantenanzahl-Anzeige
        self.edge_count_label = QLabel(tr("No edges"))
        self.edge_count_label.setStyleSheet("color: #a0a6b0; font-size: 12px; border: none;")
        self.edge_count_label.setMinimumWidth(80)
        header.addWidget(self.edge_count_label)

        layout.addLayout(header)

        body = QGridLayout()
        body.setHorizontalSpacing(8)
        body.setVerticalSpacing(6)

        radius_label = QLabel(tr("Radius:"))
        body.addWidget(radius_label, 0, 0)

        self.radius_input = ActionSpinBox()
        self.radius_input.setRange(0.1, 1000.0)
        self.radius_input.setDecimals(2)
        self.radius_input.setSuffix(" mm")
        self.radius_input.setValue(2.0)

        self.radius_input.valueChanged.connect(self._on_value_changed)
        self.radius_input.enterPressed.connect(self._confirm)
        self.radius_input.escapePressed.connect(self._cancel)

        body.addWidget(self.radius_input, 0, 1)
        body.setColumnStretch(1, 1)
        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()

        self.ok_btn = QPushButton("OK")
        self.ok_btn.setObjectName("primary")
        self.ok_btn.clicked.connect(self._confirm)
        actions.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("X")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.clicked.connect(self._cancel)
        actions.addWidget(self.cancel_btn)

        layout.addLayout(actions)

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
                color: #b07a7a;
                font-size: 12px;
                font-weight: normal;
                border: none;
                padding-left: 5px;
            """)
        elif count == 1:
            self.edge_count_label.setText(tr("1 edge"))
            self.edge_count_label.setStyleSheet("""
                color: #7fa889;
                font-size: 12px;
                font-weight: normal;
                border: none;
                padding-left: 5px;
            """)
        else:
            self.edge_count_label.setText(tr("{count} edges").format(count=count))
            self.edge_count_label.setStyleSheet("""
                color: #7fa889;
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
        _position_panel_right_mid(self, pos_widget)
        if hasattr(self, 'radius_input'):
            self.radius_input.setFocus()
            self.radius_input.selectAll()


# ==================== PHASE 6: SHELL INPUT PANEL ====================

class ShellInputPanel(RoundedPanelFrame):
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

        self.setMinimumWidth(360)
        self.setMaximumWidth(440)
        self.setMinimumHeight(120)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.label = QLabel(tr("Shell:"))
        self.label.setObjectName("panelTitle")
        header.addWidget(self.label)
        header.addStretch()

        self.face_count_label = QLabel(tr("No opening"))
        self.face_count_label.setStyleSheet("color: #a0a6b0; font-size: 12px; border: none;")
        self.face_count_label.setMinimumWidth(90)
        header.addWidget(self.face_count_label)
        layout.addLayout(header)

        body = QGridLayout()
        body.setHorizontalSpacing(8)
        body.setVerticalSpacing(6)

        thickness_label = QLabel(tr("Thickness:"))
        body.addWidget(thickness_label, 0, 0)

        self.thickness_input = ActionSpinBox()
        self.thickness_input.setRange(0.1, 100.0)
        self.thickness_input.setDecimals(2)
        self.thickness_input.setSuffix(" mm")
        self.thickness_input.setValue(2.0)

        self.thickness_input.valueChanged.connect(self._on_value_changed)
        self.thickness_input.enterPressed.connect(self._confirm)
        self.thickness_input.escapePressed.connect(self._cancel)

        body.addWidget(self.thickness_input, 0, 1)
        body.setColumnStretch(1, 1)
        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()

        self.ok_btn = QPushButton("OK")
        self.ok_btn.setObjectName("primary")
        self.ok_btn.clicked.connect(self._confirm)
        actions.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("X")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.clicked.connect(self._cancel)
        actions.addWidget(self.cancel_btn)

        layout.addLayout(actions)

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
                color: #b08a6a;
                font-size: 12px;
                font-weight: normal;
                border: none;
                padding-left: 5px;
            """)
        elif count == 1:
            self.face_count_label.setText(tr("1 opening"))
            self.face_count_label.setStyleSheet("""
                color: #7fa889;
                font-size: 12px;
                font-weight: normal;
                border: none;
                padding-left: 5px;
            """)
        else:
            self.face_count_label.setText(tr("{count} openings").format(count=count))
            self.face_count_label.setStyleSheet("""
                color: #7fa889;
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
        self.show()
        self.raise_()
        _position_panel_right_mid(self, pos_widget)
        self.thickness_input.setFocus()
        self.thickness_input.selectAll()


class SweepInputPanel(RoundedPanelFrame):
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

        self.setMinimumWidth(440)
        self.setMaximumWidth(560)
        self.setMinimumHeight(200)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.label = QLabel(tr("Sweep:"))
        self.label.setObjectName("panelTitle")
        header.addWidget(self.label)
        header.addStretch()

        self.operation_combo = QComboBox()
        # Store internal keys as item data for comparison, display translated text
        for key in ["New Body", "Join", "Cut", "Intersect"]:
            self.operation_combo.addItem(tr(key), key)
        self.operation_combo.currentIndexChanged.connect(self._on_operation_changed_idx)
        header.addWidget(self.operation_combo)
        layout.addLayout(header)

        body = QVBoxLayout()
        body.setSpacing(6)

        # Profile status with clear button
        profile_container = QWidget()
        profile_layout = QHBoxLayout(profile_container)
        profile_layout.setContentsMargins(0, 0, 0, 0)
        profile_layout.setSpacing(6)

        self.profile_status = QLabel(tr("Profile: none"))
        self.profile_status.setStyleSheet("color: #b08a6a; font-size: 12px; border: none;")
        profile_layout.addWidget(self.profile_status)

        self.profile_clear_btn = QPushButton("x")
        self.profile_clear_btn.setFixedSize(18, 18)
        self.profile_clear_btn.setObjectName("ghost")
        self.profile_clear_btn.setToolTip(tr("Clear profile selection"))
        self.profile_clear_btn.clicked.connect(self._on_profile_clear_clicked)
        self.profile_clear_btn.hide()
        profile_layout.addWidget(self.profile_clear_btn)

        # Path status with clear button
        path_container = QWidget()
        path_layout = QHBoxLayout(path_container)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(6)

        self.path_status = QLabel(tr("Path: none"))
        self.path_status.setStyleSheet("color: #b08a6a; font-size: 12px; border: none;")
        path_layout.addWidget(self.path_status)

        self.path_clear_btn = QPushButton("x")
        self.path_clear_btn.setFixedSize(18, 18)
        self.path_clear_btn.setObjectName("ghost")
        self.path_clear_btn.setToolTip(tr("Clear path selection"))
        self.path_clear_btn.clicked.connect(self._on_path_clear_clicked)
        self.path_clear_btn.hide()
        path_layout.addWidget(self.path_clear_btn)

        select_row = QGridLayout()
        select_row.setHorizontalSpacing(12)
        select_row.addWidget(profile_container, 0, 0)
        select_row.addWidget(path_container, 0, 1)
        select_row.setColumnStretch(1, 1)
        body.addLayout(select_row)

        # Sketch Path button + Frenet
        opts_row = QHBoxLayout()
        opts_row.setSpacing(8)
        self.sketch_path_btn = QPushButton(tr("Sketch"))
        self.sketch_path_btn.setToolTip(tr("Select path from sketch (arc/line/spline)"))
        self.sketch_path_btn.setObjectName("ghost")
        self.sketch_path_btn.clicked.connect(lambda: self.sketch_path_requested.emit())
        opts_row.addWidget(self.sketch_path_btn)

        self.frenet_check = QCheckBox(tr("Frenet"))
        self.frenet_check.setToolTip(tr("Twist along path"))
        self.frenet_check.stateChanged.connect(self._on_frenet_changed)
        opts_row.addWidget(self.frenet_check)
        opts_row.addStretch()
        body.addLayout(opts_row)

        # Twist angle
        from PySide6.QtGui import QDoubleValidator
        twist_row = QHBoxLayout()
        twist_row.setSpacing(8)
        twist_lbl = QLabel(tr("Twist:"))
        twist_row.addWidget(twist_lbl)
        self.twist_input = QLineEdit("0")
        tv = QDoubleValidator(-3600, 3600, 1)
        tv.setNotation(QDoubleValidator.StandardNotation)
        self.twist_input.setValidator(tv)
        self.twist_input.setToolTip(tr("Twist angle in degrees along path"))
        twist_row.addWidget(self.twist_input)
        twist_row.addStretch()
        body.addLayout(twist_row)

        # Scale
        scale_row = QHBoxLayout()
        scale_row.setSpacing(6)
        scale_lbl = QLabel(tr("Scale:"))
        scale_row.addWidget(scale_lbl)
        self.scale_start_input = QLineEdit("1.0")
        sv = QDoubleValidator(0.01, 100, 2)
        sv.setNotation(QDoubleValidator.StandardNotation)
        self.scale_start_input.setValidator(sv)
        self.scale_start_input.setToolTip(tr("Scale at path start"))
        scale_row.addWidget(self.scale_start_input)

        arrow_lbl = QLabel(tr("→"))
        scale_row.addWidget(arrow_lbl)

        self.scale_end_input = QLineEdit("1.0")
        self.scale_end_input.setValidator(sv)
        self.scale_end_input.setToolTip(tr("Scale at path end"))
        scale_row.addWidget(self.scale_end_input)
        scale_row.addStretch()
        body.addLayout(scale_row)

        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()

        self.ok_btn = QPushButton("OK")
        self.ok_btn.setObjectName("primary")
        self.ok_btn.clicked.connect(self._confirm)
        self.ok_btn.setEnabled(False)  # Disabled until profile and path selected
        actions.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("X")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.clicked.connect(self._cancel)
        actions.addWidget(self.cancel_btn)

        layout.addLayout(actions)

        self.hide()

    def set_profile(self, profile_data: dict):
        """Setzt das Profil für den Sweep."""
        self._profile_data = profile_data
        self.profile_status.setText(tr("Profile: selected"))
        self.profile_status.setStyleSheet("""
            color: #7fa889;
            font-size: 12px;
            font-weight: normal;
            border: none;
        """)
        self.profile_clear_btn.show()
        self._update_ok_button()

    def clear_profile(self):
        """Löscht das Profil."""
        self._profile_data = None
        self.profile_status.setText(tr("Profile: none"))
        self.profile_status.setStyleSheet("""
            color: #b08a6a;
            font-size: 12px;
            font-weight: normal;
            border: none;
        """)
        self.profile_clear_btn.hide()
        self._update_ok_button()

    def set_path(self, path_data: dict):
        """Setzt den Pfad für den Sweep."""
        self._path_data = path_data
        self.path_status.setText(tr("Path: selected"))
        self.path_status.setStyleSheet("""
            color: #7fa889;
            font-size: 12px;
            font-weight: normal;
            border: none;
        """)
        self.path_clear_btn.show()
        self._update_ok_button()

    def clear_path(self):
        """Löscht den Pfad."""
        self._path_data = None
        self.path_status.setText(tr("Path: none"))
        self.path_status.setStyleSheet("""
            color: #b08a6a;
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
        self.show()
        self.raise_()
        _position_panel_right_mid(self, pos_widget)


class LoftInputPanel(RoundedPanelFrame):
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

        self.setMinimumWidth(420)
        self.setMaximumWidth(560)
        self.setMinimumHeight(170)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.label = QLabel(tr("Loft:"))
        self.label.setObjectName("panelTitle")
        header.addWidget(self.label)

        self.profile_count_label = QLabel(tr("0 profiles"))
        self.profile_count_label.setStyleSheet("color: #b08a6a; font-size: 12px; border: none;")
        self.profile_count_label.setMinimumWidth(80)
        header.addWidget(self.profile_count_label)

        header.addStretch()

        self.operation_combo = QComboBox()
        # Store internal keys as item data for comparison, display translated text
        for key in ["New Body", "Join", "Cut", "Intersect"]:
            self.operation_combo.addItem(tr(key), key)
        self.operation_combo.currentIndexChanged.connect(self._on_operation_changed_idx)
        header.addWidget(self.operation_combo)

        layout.addLayout(header)

        body = QVBoxLayout()
        body.setSpacing(6)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(8)

        self.add_profile_btn = QPushButton(tr("+ Profile"))
        self.add_profile_btn.setObjectName("ghost")
        self.add_profile_btn.clicked.connect(self._on_add_profile)
        controls_row.addWidget(self.add_profile_btn)

        self.ruled_check = QCheckBox(tr("Ruled"))
        self.ruled_check.setToolTip(tr("Straight lines instead of smooth transitions"))
        self.ruled_check.stateChanged.connect(self._on_ruled_changed)
        controls_row.addWidget(self.ruled_check)
        controls_row.addStretch()

        body.addLayout(controls_row)

        self.profile_info = QLabel(tr("Select faces on different Z-planes"))
        self.profile_info.setStyleSheet("color: #a0a6b0; font-size: 11px; border: none;")
        body.addWidget(self.profile_info)

        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()

        self.ok_btn = QPushButton("OK")
        self.ok_btn.setObjectName("primary")
        self.ok_btn.clicked.connect(self._confirm)
        self.ok_btn.setEnabled(False)  # Disabled until 2+ profiles
        actions.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("X")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.clicked.connect(self._cancel)
        actions.addWidget(self.cancel_btn)

        layout.addLayout(actions)

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
                color: #b08a6a;
                font-size: 12px;
                font-weight: normal;
                border: none;
            """)
        elif count == 1:
            z_info = self._get_z_info(self._profiles[0])
            self.profile_count_label.setText(tr("1 profile ({z_info})").format(z_info=z_info))
            self.profile_count_label.setStyleSheet("""
                color: #b08a6a;
                font-size: 12px;
                font-weight: normal;
                border: none;
            """)
        else:
            z_min = min(self._get_z(p) for p in self._profiles)
            z_max = max(self._get_z(p) for p in self._profiles)
            self.profile_count_label.setText(tr("{count} profiles (Z: {z_min:.0f}-{z_max:.0f})").format(count=count, z_min=z_min, z_max=z_max))
            self.profile_count_label.setStyleSheet("""
                color: #7fa889;
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
        self.show()
        self.raise_()
        _position_panel_right_mid(self, pos_widget)


class TransformPanel(RoundedPanelFrame):
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

        self.setMinimumWidth(360)
        self.setMaximumWidth(460)
        self.setMinimumHeight(180)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(tr("Transform:"))
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch()

        # Mode-Auswahl
        self.mode_combo = QComboBox()
        # Store internal keys as item data for comparison, display translated text
        for key in ["Move", "Rotate", "Scale"]:
            self.mode_combo.addItem(tr(key), key)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed_idx)
        header.addWidget(self.mode_combo)

        layout.addLayout(header)

        body = QGridLayout()
        body.setHorizontalSpacing(8)
        body.setVerticalSpacing(6)

        # X Input
        self.x_label = QLabel(tr("X:"))
        body.addWidget(self.x_label, 0, 0)

        self.x_input = ActionSpinBox()
        self.x_input.setRange(-99999, 99999)
        self.x_input.setDecimals(2)
        self.x_input.setValue(0.0)
        self.x_input.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.x_input.enterPressed.connect(self._on_confirm)
        self.x_input.escapePressed.connect(self._on_cancel)
        self.x_input.valueChanged.connect(self._on_value_changed)
        body.addWidget(self.x_input, 0, 1)

        # Y Input
        self.y_label = QLabel(tr("Y:"))
        body.addWidget(self.y_label, 1, 0)

        self.y_input = ActionSpinBox()
        self.y_input.setRange(-99999, 99999)
        self.y_input.setDecimals(2)
        self.y_input.setValue(0.0)
        self.y_input.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.y_input.enterPressed.connect(self._on_confirm)
        self.y_input.escapePressed.connect(self._on_cancel)
        self.y_input.valueChanged.connect(self._on_value_changed)
        body.addWidget(self.y_input, 1, 1)

        # Z Input
        self.z_label = QLabel(tr("Z:"))
        body.addWidget(self.z_label, 2, 0)

        self.z_input = ActionSpinBox()
        self.z_input.setRange(-99999, 99999)
        self.z_input.setDecimals(2)
        self.z_input.setValue(0.0)
        self.z_input.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.z_input.enterPressed.connect(self._on_confirm)
        self.z_input.escapePressed.connect(self._on_cancel)
        self.z_input.valueChanged.connect(self._on_value_changed)
        body.addWidget(self.z_input, 2, 1)

        # Grid-Size
        grid_label = QLabel(tr("Grid:"))
        body.addWidget(grid_label, 3, 0)
        self.grid_combo = QComboBox()
        self.grid_combo.addItems(["0.1", "0.5", "1", "5", "10"])
        self.grid_combo.setCurrentText("1")
        self.grid_combo.setToolTip(tr("Grid (Ctrl+Drag)"))
        self.grid_combo.currentTextChanged.connect(self._on_grid_changed)
        body.addWidget(self.grid_combo, 3, 1)

        grid_unit = QLabel(tr("mm"))
        grid_unit.setStyleSheet("color: #a0a6b0;")
        body.addWidget(grid_unit, 3, 2)

        body.setColumnStretch(1, 1)
        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()

        # OK Button
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setObjectName("primary")
        self.btn_ok.clicked.connect(self._on_confirm)
        actions.addWidget(self.btn_ok)

        # Cancel Button
        self.btn_cancel = QPushButton("X")
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.clicked.connect(self._on_cancel)
        actions.addWidget(self.btn_cancel)

        layout.addLayout(actions)

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
        _position_panel_right_mid(self, pos_widget)
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


class RevolveInputPanel(RoundedPanelFrame):
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

        self.setMinimumWidth(360)
        self.setMaximumWidth(520)
        self.setMinimumHeight(170)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(tr("Revolve:"))
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch()

        self.op_indicator = QLabel("•")
        self.op_indicator.setFixedWidth(14)
        self.op_indicator.setStyleSheet("color: #8aa0c8; font-size: 14px;")
        header.addWidget(self.op_indicator)

        self.op_combo = QComboBox()
        # Store internal keys as item data for comparison, display translated text
        for key in ["New Body", "Join", "Cut", "Intersect"]:
            self.op_combo.addItem(tr(key), key)
        self.op_combo.currentIndexChanged.connect(self._on_operation_changed_idx)
        header.addWidget(self.op_combo)

        layout.addLayout(header)

        body = QVBoxLayout()
        body.setSpacing(6)

        axis_row = QHBoxLayout()
        axis_row.setSpacing(6)
        axis_row.addWidget(QLabel(tr("Axis:")))
        self._axis_buttons = {}
        for axis_name in ('X', 'Y', 'Z'):
            btn = QPushButton(axis_name)
            btn.setCheckable(True)
            btn.setObjectName("toggle")
            btn.clicked.connect(lambda checked, a=axis_name: self._on_axis_clicked(a))
            axis_row.addWidget(btn)
            self._axis_buttons[axis_name] = btn
        self._axis_buttons['Y'].setChecked(True)
        axis_row.addStretch()
        body.addLayout(axis_row)

        angle_row = QHBoxLayout()
        angle_row.setSpacing(8)
        angle_row.addWidget(QLabel(tr("Angle:")))
        self.angle_input = ActionSpinBox()
        self.angle_input.setRange(0.1, 360.0)
        self.angle_input.setDecimals(1)
        self.angle_input.setSuffix(" deg")
        self.angle_input.setValue(360.0)
        self.angle_input.valueChanged.connect(self._on_angle_changed)
        self.angle_input.enterPressed.connect(self._confirm)
        self.angle_input.escapePressed.connect(self.cancelled.emit)
        angle_row.addWidget(self.angle_input)

        self.flip_btn = QPushButton("<->")
        self.flip_btn.setToolTip(tr("Flip direction (F)"))
        self.flip_btn.setObjectName("ghost")
        self.flip_btn.clicked.connect(self._flip_direction)
        angle_row.addWidget(self.flip_btn)
        angle_row.addStretch()
        body.addLayout(angle_row)

        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()

        self.btn_ok = QPushButton("OK")
        self.btn_ok.setObjectName("primary")
        self.btn_ok.clicked.connect(self._confirm)
        actions.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("X")
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.clicked.connect(self.cancelled.emit)
        actions.addWidget(self.btn_cancel)

        layout.addLayout(actions)

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
            "New Body": "#8aa0c8", "Join": "#7fa889",
            "Cut": "#b07a7a", "Intersect": "#c9a87f"
        }
        self.op_indicator.setStyleSheet(f"color: {colors.get(op_key, '#8aa0c8')}; font-size: 16px;")
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
        _position_panel_right_mid(self, pos_widget)


class OffsetPlaneInputPanel(RoundedPanelFrame):
    """Input panel for interactive Offset Plane creation."""

    offset_changed = Signal(float)
    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._offset = 0.0

        self.setMinimumWidth(360)
        self.setMaximumWidth(480)
        self.setMinimumHeight(140)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(tr("Offset Plane:"))
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        body = QGridLayout()
        body.setHorizontalSpacing(8)
        body.setVerticalSpacing(6)

        body.addWidget(QLabel(tr("Offset:")), 0, 0)
        self.offset_input = ActionSpinBox()
        self.offset_input.setRange(-10000.0, 10000.0)
        self.offset_input.setDecimals(2)
        self.offset_input.setSuffix(" mm")
        self.offset_input.setValue(0.0)
        self.offset_input.valueChanged.connect(self._on_value_changed)
        self.offset_input.enterPressed.connect(self._confirm)
        self.offset_input.escapePressed.connect(self._cancel)
        body.addWidget(self.offset_input, 0, 1)

        body.addWidget(QLabel(tr("Name:")), 1, 0)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(tr("Name (auto)"))
        body.addWidget(self.name_input, 1, 1)

        body.setColumnStretch(1, 1)
        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()

        self.ok_btn = QPushButton("OK")
        self.ok_btn.setObjectName("primary")
        self.ok_btn.clicked.connect(self._confirm)
        actions.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("X")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.clicked.connect(self._cancel)
        actions.addWidget(self.cancel_btn)

        layout.addLayout(actions)

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
        _position_panel_right_mid(self, pos_widget)


class HoleInputPanel(RoundedPanelFrame):
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

        self.setMinimumWidth(360)
        self.setMaximumWidth(480)
        self.setMinimumHeight(160)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(tr("Hole:"))
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch()

        # Hole type
        self.type_combo = QComboBox()
        # Store internal keys as item data for comparison, display translated text
        for key in ["Simple", "Counterbore", "Countersink"]:
            self.type_combo.addItem(tr(key), key)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed_idx)
        header.addWidget(self.type_combo)
        layout.addLayout(header)

        body = QGridLayout()
        body.setHorizontalSpacing(8)
        body.setVerticalSpacing(6)

        body.addWidget(QLabel(tr("Diameter:")), 0, 0)
        self.diameter_input = ActionSpinBox()
        self.diameter_input.setRange(0.1, 500.0)
        self.diameter_input.setDecimals(2)
        self.diameter_input.setSuffix(" mm")
        self.diameter_input.setValue(8.0)
        self.diameter_input.valueChanged.connect(self._on_diameter_changed)
        self.diameter_input.enterPressed.connect(self._confirm)
        self.diameter_input.escapePressed.connect(self.cancelled.emit)
        body.addWidget(self.diameter_input, 0, 1)

        body.addWidget(QLabel(tr("Depth:")), 1, 0)
        self.depth_input = ActionSpinBox()
        self.depth_input.setRange(0.0, 10000.0)
        self.depth_input.setDecimals(2)
        self.depth_input.setSuffix(" mm")
        self.depth_input.setValue(0.0)
        self.depth_input.setSpecialValueText(tr("Through All"))
        self.depth_input.valueChanged.connect(self._on_depth_changed)
        self.depth_input.enterPressed.connect(self._confirm)
        self.depth_input.escapePressed.connect(self.cancelled.emit)
        body.addWidget(self.depth_input, 1, 1)

        body.setColumnStretch(1, 1)
        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()

        self.btn_ok = QPushButton("OK")
        self.btn_ok.setObjectName("primary")
        self.btn_ok.clicked.connect(self._confirm)
        actions.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("X")
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.clicked.connect(self.cancelled.emit)
        actions.addWidget(self.btn_cancel)

        layout.addLayout(actions)

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
        _position_panel_right_mid(self, pos_widget)


class DraftInputPanel(RoundedPanelFrame):
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

        self.setMinimumWidth(360)
        self.setMaximumWidth(520)
        self.setMinimumHeight(160)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(tr("Draft:"))
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch()

        # Face count indicator
        self.face_label = QLabel(tr("0 faces"))
        self.face_label.setStyleSheet("color: #a0a6b0; font-size: 12px; border: none;")
        header.addWidget(self.face_label)
        layout.addLayout(header)

        body = QVBoxLayout()
        body.setSpacing(6)

        angle_row = QHBoxLayout()
        angle_row.setSpacing(8)
        angle_row.addWidget(QLabel(tr("Angle:")))
        self.angle_input = ActionSpinBox()
        self.angle_input.setRange(0.1, 89.0)
        self.angle_input.setDecimals(1)
        self.angle_input.setSuffix(" deg")
        self.angle_input.setValue(5.0)
        self.angle_input.valueChanged.connect(self._on_angle_changed)
        self.angle_input.enterPressed.connect(self._confirm)
        self.angle_input.escapePressed.connect(self.cancelled.emit)
        angle_row.addWidget(self.angle_input)
        angle_row.addStretch()
        body.addLayout(angle_row)

        axis_row = QHBoxLayout()
        axis_row.setSpacing(6)
        axis_row.addWidget(QLabel(tr("Pull:")))
        self._axis_btns = {}
        for axis in ["X", "Y", "Z"]:
            btn = QPushButton(axis)
            btn.setCheckable(True)
            btn.setObjectName("toggle")
            btn.clicked.connect(lambda checked, a=axis: self._set_axis(a))
            self._axis_btns[axis] = btn
            axis_row.addWidget(btn)
        if self._pull_axis in self._axis_btns:
            self._axis_btns[self._pull_axis].setChecked(True)
        axis_row.addStretch()
        body.addLayout(axis_row)

        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()

        self.btn_ok = QPushButton("OK")
        self.btn_ok.setObjectName("primary")
        self.btn_ok.clicked.connect(self._confirm)
        actions.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("X")
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.clicked.connect(self._cancel)
        actions.addWidget(self.btn_cancel)

        layout.addLayout(actions)

        self.hide()

    def _on_angle_changed(self, value):
        self._angle = value
        self.angle_changed.emit(value)

    def _confirm(self):
        self._angle = self.angle_input.value()
        self.confirmed.emit()

    def _cancel(self):
        self.cancelled.emit()

    def _set_axis(self, axis: str):
        self._pull_axis = axis
        for name, btn in self._axis_btns.items():
            btn.setChecked(name == axis)
        self.axis_changed.emit(axis)


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
        _position_panel_right_mid(self, pos_widget)


class SplitInputPanel(RoundedPanelFrame):
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

        self.setMinimumWidth(360)
        self.setMaximumWidth(520)
        self.setMinimumHeight(190)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(tr("Split:"))
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        body = QGridLayout()
        body.setHorizontalSpacing(8)
        body.setVerticalSpacing(6)

        body.addWidget(QLabel(tr("Plane:")), 0, 0)
        plane_row = QHBoxLayout()
        plane_row.setSpacing(6)
        self._plane_btns = {}
        for plane in ["XY", "XZ", "YZ"]:
            btn = QPushButton(plane)
            btn.setCheckable(True)
            btn.setObjectName("toggle")
            btn.clicked.connect(lambda checked, p=plane: self._set_plane(p))
            self._plane_btns[plane] = btn
            plane_row.addWidget(btn)
        self._plane_btns["XY"].setChecked(True)
        body.addLayout(plane_row, 0, 1)

        body.addWidget(QLabel(tr("Pos:")), 1, 0)
        self.pos_input = ActionSpinBox()
        self.pos_input.setRange(-1000.0, 1000.0)
        self.pos_input.setDecimals(2)
        self.pos_input.setSuffix(" mm")
        self.pos_input.setValue(0.0)
        self.pos_input.setSingleStep(1.0)
        self.pos_input.valueChanged.connect(self._on_pos_changed)
        self.pos_input.enterPressed.connect(self._confirm)
        self.pos_input.escapePressed.connect(self.cancelled.emit)
        body.addWidget(self.pos_input, 1, 1)

        body.addWidget(QLabel(tr("Angle:")), 2, 0)
        self.angle_input = ActionSpinBox()
        self.angle_input.setRange(-89.0, 89.0)
        self.angle_input.setDecimals(1)
        self.angle_input.setSuffix(" deg")
        self.angle_input.setValue(0.0)
        self.angle_input.setSingleStep(5.0)
        self.angle_input.valueChanged.connect(self._on_angle_changed)
        self.angle_input.enterPressed.connect(self._confirm)
        self.angle_input.escapePressed.connect(self.cancelled.emit)
        body.addWidget(self.angle_input, 2, 1)

        body.addWidget(QLabel(tr("Keep:")), 3, 0)
        self.keep_combo = QComboBox()
        # Store internal keys as item data for comparison, display translated text
        for key in ["Above", "Below", "Both"]:
            self.keep_combo.addItem(tr(key), key)
        self.keep_combo.currentIndexChanged.connect(self._on_keep_changed_idx)
        body.addWidget(self.keep_combo, 3, 1)

        body.setColumnStretch(1, 1)
        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()

        self.btn_ok = QPushButton("OK")
        self.btn_ok.setObjectName("primary")
        self.btn_ok.clicked.connect(self._confirm)
        actions.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("X")
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.clicked.connect(self.cancelled.emit)
        actions.addWidget(self.btn_cancel)

        layout.addLayout(actions)

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
        _position_panel_right_mid(self, pos_widget)



class PatternInputPanel(RoundedPanelFrame):
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

        self.setMinimumWidth(420)
        self.setMaximumWidth(560)
        self.setMinimumHeight(190)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(tr("Pattern:"))
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch()

        self.linear_btn = QPushButton(tr("Linear"))
        self.linear_btn.setCheckable(True)
        self.linear_btn.setChecked(True)
        self.linear_btn.setObjectName("toggle")
        self.linear_btn.clicked.connect(lambda: self._set_pattern_type("linear"))
        header.addWidget(self.linear_btn)

        self.circular_btn = QPushButton(tr("Circular"))
        self.circular_btn.setCheckable(True)
        self.circular_btn.setObjectName("toggle")
        self.circular_btn.clicked.connect(lambda: self._set_pattern_type("circular"))
        header.addWidget(self.circular_btn)

        layout.addLayout(header)

        body = QGridLayout()
        body.setHorizontalSpacing(8)
        body.setVerticalSpacing(6)

        # Count
        body.addWidget(QLabel(tr("Count:")), 0, 0)
        from PySide6.QtWidgets import QSpinBox
        self.count_spin = QSpinBox()
        self.count_spin.setRange(2, 100)
        self.count_spin.setValue(3)
        self.count_spin.valueChanged.connect(self._emit_parameters)
        body.addWidget(self.count_spin, 0, 1)

        # Axis
        body.addWidget(QLabel(tr("Axis:")), 0, 2)
        self.axis_combo = QComboBox()
        self.axis_combo.addItems(["X", "Y", "Z"])
        self.axis_combo.currentTextChanged.connect(self._emit_parameters)
        body.addWidget(self.axis_combo, 0, 3)

        # Linear: Spacing
        self.spacing_label = QLabel(tr("Spacing:"))
        body.addWidget(self.spacing_label, 1, 0)
        self.spacing_spin = QDoubleSpinBox()
        self.spacing_spin.setRange(0.1, 10000)
        self.spacing_spin.setValue(10.0)
        self.spacing_spin.setSuffix(" mm")
        self.spacing_spin.setDecimals(2)
        self.spacing_spin.valueChanged.connect(self._emit_parameters)
        body.addWidget(self.spacing_spin, 1, 1)

        # Circular: Angle
        self.angle_label = QLabel(tr("Angle:"))
        self.angle_label.hide()
        body.addWidget(self.angle_label, 1, 2)
        self.angle_spin = QDoubleSpinBox()
        self.angle_spin.setRange(1, 360)
        self.angle_spin.setValue(360)
        self.angle_spin.setSuffix(" deg")
        self.angle_spin.setDecimals(1)
        self.angle_spin.valueChanged.connect(self._emit_parameters)
        self.angle_spin.hide()
        body.addWidget(self.angle_spin, 1, 3)

        # Circular: Center Selection
        self.center_label = QLabel(tr("Center:"))
        self.center_label.hide()
        body.addWidget(self.center_label, 2, 0)
        self.center_combo = QComboBox()
        # Store internal keys as item data for comparison, display translated text
        for key in ["Body Center", "Origin (0,0,0)", "Custom..."]:
            self.center_combo.addItem(tr(key), key)
        self.center_combo.currentIndexChanged.connect(self._on_center_changed_idx)
        self.center_combo.hide()
        body.addWidget(self.center_combo, 2, 1)

        # Custom center coordinates (hidden by default)
        self._custom_center = (0.0, 0.0, 0.0)

        body.setColumnStretch(1, 1)
        body.setColumnStretch(3, 1)
        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()

        self.ok_btn = QPushButton("OK")
        self.ok_btn.setObjectName("primary")
        self.ok_btn.clicked.connect(self._confirm)
        actions.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("X")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.clicked.connect(self._cancel)
        actions.addWidget(self.cancel_btn)

        layout.addLayout(actions)

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
        _position_panel_right_mid(self, pos_widget)


class NSidedPatchInputPanel(RoundedPanelFrame):
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

        self.setMinimumWidth(360)
        self.setMaximumWidth(520)
        self.setMinimumHeight(160)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.label = QLabel(tr("N-Sided Patch:"))
        self.label.setObjectName("panelTitle")
        header.addWidget(self.label)
        header.addStretch()

        self.edge_count_label = QLabel(tr("0 edges"))
        self.edge_count_label.setStyleSheet("color: #b07a7a; font-size: 12px; border: none;")
        self.edge_count_label.setMinimumWidth(70)
        header.addWidget(self.edge_count_label)

        layout.addLayout(header)

        body = QGridLayout()
        body.setHorizontalSpacing(8)
        body.setVerticalSpacing(6)

        body.addWidget(QLabel(tr("Degree:")), 0, 0)
        from PySide6.QtWidgets import QSpinBox
        self.degree_spin = QSpinBox()
        self.degree_spin.setRange(2, 6)
        self.degree_spin.setValue(3)
        body.addWidget(self.degree_spin, 0, 1)

        self.tangent_check = QCheckBox(tr("G1 (tangent)"))
        self.tangent_check.setChecked(True)
        self.tangent_check.setToolTip(tr("Match tangency with adjacent faces"))
        body.addWidget(self.tangent_check, 1, 0, 1, 2)

        body.setColumnStretch(1, 1)
        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()

        self.ok_btn = QPushButton(tr("Fill"))
        self.ok_btn.setObjectName("primary")
        self.ok_btn.clicked.connect(self._confirm)
        actions.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("X")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.clicked.connect(self._cancel)
        actions.addWidget(self.cancel_btn)

        layout.addLayout(actions)

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
                color: #b07a7a;
                font-size: 12px;
                font-weight: normal;
                border: none;
            """)
            self.ok_btn.setEnabled(False)
        else:
            self.edge_count_label.setText(f"{count} Edges")
            self.edge_count_label.setStyleSheet("""
                color: #7fa889;
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
        _position_panel_right_mid(self, pos_widget)


class LatticeInputPanel(RoundedPanelFrame):
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

        self.setMinimumWidth(360)
        self.setMaximumWidth(520)
        self.setMinimumHeight(190)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(tr("Lattice:"))
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        body = QGridLayout()
        body.setHorizontalSpacing(8)
        body.setVerticalSpacing(6)

        body.addWidget(QLabel(tr("Type:")), 0, 0)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["BCC", "FCC", "Octet", "Diamond"])
        body.addWidget(self.type_combo, 0, 1)

        body.addWidget(QLabel(tr("Cell:")), 1, 0)
        self.cell_spin = QDoubleSpinBox()
        self.cell_spin.setRange(1.0, 100.0)
        self.cell_spin.setValue(5.0)
        self.cell_spin.setSuffix(" mm")
        self.cell_spin.setDecimals(1)
        body.addWidget(self.cell_spin, 1, 1)

        body.addWidget(QLabel(tr("Beam:")), 2, 0)
        self.beam_spin = QDoubleSpinBox()
        self.beam_spin.setRange(0.1, 10.0)
        self.beam_spin.setValue(0.5)
        self.beam_spin.setSuffix(" mm")
        self.beam_spin.setDecimals(2)
        body.addWidget(self.beam_spin, 2, 1)

        body.addWidget(QLabel(tr("Shell:")), 3, 0)
        self.shell_spin = QDoubleSpinBox()
        self.shell_spin.setRange(0.0, 50.0)
        self.shell_spin.setValue(1.0)
        self.shell_spin.setSuffix(" mm")
        self.shell_spin.setDecimals(1)
        self.shell_spin.setToolTip(tr("0 = no shell, >0 = preserve outer wall"))
        body.addWidget(self.shell_spin, 3, 1)

        body.setColumnStretch(1, 1)
        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()

        self.ok_btn = QPushButton(tr("Generate"))
        self.ok_btn.setObjectName("primary")
        self.ok_btn.clicked.connect(self._confirm)
        actions.addWidget(self.ok_btn)

        self.cancel_btn = QPushButton("X")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.clicked.connect(self._cancel)
        actions.addWidget(self.cancel_btn)

        layout.addLayout(actions)

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
        _position_panel_right_mid(self, pos_widget)


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


class ThreadInputPanel(RoundedPanelFrame):
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

        self.setMinimumWidth(360)
        self.setMaximumWidth(520)
        self.setMinimumHeight(210)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(tr("Thread:"))
        title.setObjectName("panelTitle")
        header.addWidget(title)
        header.addStretch()

        # Thread type (External/Internal)
        self.type_combo = QComboBox()
        # Store internal keys as item data for comparison, display translated text
        for key in ["External", "Internal"]:
            self.type_combo.addItem(tr(key), key)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed_idx)
        header.addWidget(self.type_combo)

        # Size preset
        self.size_combo = QComboBox()
        self.size_combo.addItem("Custom")
        for name in METRIC_THREADS_PANEL:
            self.size_combo.addItem(name)
        self.size_combo.setCurrentText("M10")
        self.size_combo.currentTextChanged.connect(self._on_preset_changed)
        header.addWidget(self.size_combo)

        layout.addLayout(header)

        body = QGridLayout()
        body.setHorizontalSpacing(8)
        body.setVerticalSpacing(6)

        body.addWidget(QLabel(tr("Diameter:")), 0, 0)
        self.diameter_input = ActionSpinBox()
        self.diameter_input.setRange(0.5, 500.0)
        self.diameter_input.setDecimals(2)
        self.diameter_input.setSuffix(" mm")
        self.diameter_input.setValue(10.0)
        self.diameter_input.valueChanged.connect(self._on_diameter_changed)
        self.diameter_input.enterPressed.connect(self._confirm)
        self.diameter_input.escapePressed.connect(self.cancelled.emit)
        body.addWidget(self.diameter_input, 0, 1)

        body.addWidget(QLabel(tr("Pitch:")), 1, 0)
        self.pitch_input = ActionSpinBox()
        self.pitch_input.setRange(0.1, 10.0)
        self.pitch_input.setDecimals(2)
        self.pitch_input.setSuffix(" mm")
        self.pitch_input.setValue(1.5)
        self.pitch_input.valueChanged.connect(self._on_pitch_changed)
        self.pitch_input.enterPressed.connect(self._confirm)
        self.pitch_input.escapePressed.connect(self.cancelled.emit)
        body.addWidget(self.pitch_input, 1, 1)

        body.addWidget(QLabel(tr("Depth:")), 2, 0)
        self.depth_input = ActionSpinBox()
        self.depth_input.setRange(0.1, 10000.0)
        self.depth_input.setDecimals(2)
        self.depth_input.setSuffix(" mm")
        self.depth_input.setValue(20.0)
        self.depth_input.valueChanged.connect(self._on_depth_changed)
        self.depth_input.enterPressed.connect(self._confirm)
        self.depth_input.escapePressed.connect(self.cancelled.emit)
        body.addWidget(self.depth_input, 2, 1)

        body.addWidget(QLabel(tr("Tol:")), 3, 0)
        self.tolerance_input = ActionSpinBox()
        self.tolerance_input.setRange(-1.0, 1.0)
        self.tolerance_input.setDecimals(3)
        self.tolerance_input.setSuffix(" mm")
        self.tolerance_input.setValue(0.0)
        self.tolerance_input.valueChanged.connect(self._on_tolerance_changed)
        self.tolerance_input.enterPressed.connect(self._confirm)
        self.tolerance_input.escapePressed.connect(self.cancelled.emit)
        body.addWidget(self.tolerance_input, 3, 1)

        body.setColumnStretch(1, 1)
        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()

        self.btn_ok = QPushButton("OK")
        self.btn_ok.setObjectName("primary")
        self.btn_ok.clicked.connect(self._confirm)
        actions.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("X")
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.clicked.connect(self.cancelled.emit)
        actions.addWidget(self.btn_cancel)

        layout.addLayout(actions)

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
        _position_panel_right_mid(self, pos_widget)


class MeasureInputPanel(RoundedPanelFrame):
    """Input panel for Measure tool (inspect)."""

    pick_point_requested = Signal(int)  # 1 or 2
    clear_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(360)
        self.setMaximumWidth(520)
        self.setMinimumHeight(150)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(tr("Measure:"))
        title.setObjectName("panelTitle")
        header.addWidget(title)

        self.status_label = QLabel(tr("Pick first point"))
        self.status_label.setStyleSheet("color: #a3a3a3; font-size: 12px; border: none;")
        header.addWidget(self.status_label)
        header.addStretch()
        layout.addLayout(header)

        body = QGridLayout()
        body.setHorizontalSpacing(8)
        body.setVerticalSpacing(6)

        body.addWidget(QLabel(tr("P1:")), 0, 0)
        self.p1_edit = QLineEdit()
        self.p1_edit.setReadOnly(True)
        self.p1_edit.setPlaceholderText("-")
        body.addWidget(self.p1_edit, 0, 1)
        self.p1_btn = QPushButton(tr("Pick"))
        self.p1_btn.setObjectName("ghost")
        self.p1_btn.clicked.connect(lambda: self.pick_point_requested.emit(1))
        body.addWidget(self.p1_btn, 0, 2)

        body.addWidget(QLabel(tr("P2:")), 1, 0)
        self.p2_edit = QLineEdit()
        self.p2_edit.setReadOnly(True)
        self.p2_edit.setPlaceholderText("-")
        body.addWidget(self.p2_edit, 1, 1)
        self.p2_btn = QPushButton(tr("Pick"))
        self.p2_btn.setObjectName("ghost")
        self.p2_btn.clicked.connect(lambda: self.pick_point_requested.emit(2))
        body.addWidget(self.p2_btn, 1, 2)

        body.addWidget(QLabel(tr("Distance:")), 2, 0)
        self.dist_edit = QLineEdit()
        self.dist_edit.setReadOnly(True)
        self.dist_edit.setPlaceholderText("-")
        body.addWidget(self.dist_edit, 2, 1, 1, 2)

        body.setColumnStretch(1, 1)
        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.clear_btn = QPushButton(tr("Clear"))
        self.clear_btn.setObjectName("ghost")
        self.clear_btn.clicked.connect(self.clear_requested.emit)
        actions.addWidget(self.clear_btn)
        actions.addStretch()

        self.btn_close = QPushButton("X")
        self.btn_close.setObjectName("danger")
        self.btn_close.clicked.connect(self.close_requested.emit)
        actions.addWidget(self.btn_close)
        layout.addLayout(actions)

        self.hide()

    def set_status(self, text: str):
        self.status_label.setText(text)

    def set_points(self, p1, p2):
        self.p1_edit.setText(self._format_point(p1) if p1 else "")
        self.p2_edit.setText(self._format_point(p2) if p2 else "")

    def set_distance(self, dist):
        self.dist_edit.setText(f"{dist:.2f} mm" if dist is not None else "")

    def reset(self):
        self.set_status(tr("Pick first point"))
        self.set_points(None, None)
        self.set_distance(None)

    def _format_point(self, p):
        return f"{p[0]:.2f}, {p[1]:.2f}, {p[2]:.2f}"

    def show_at(self, pos_widget):
        self.show()
        self.raise_()
        _position_panel_right_mid(self, pos_widget)


class PointToPointMovePanel(RoundedPanelFrame):
    """Input panel for Point-to-Point Move."""

    pick_body_requested = Signal()
    reset_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(360)
        self.setMaximumWidth(520)
        self.setMinimumHeight(150)

        self.setStyleSheet(DesignTokens.stylesheet_panel())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(tr("Point Move:"))
        title.setObjectName("panelTitle")
        header.addWidget(title)

        self.status_label = QLabel(tr("Pick body"))
        self.status_label.setStyleSheet("color: #a3a3a3; font-size: 12px; border: none;")
        header.addWidget(self.status_label)
        header.addStretch()
        layout.addLayout(header)

        body = QGridLayout()
        body.setHorizontalSpacing(8)
        body.setVerticalSpacing(6)

        body.addWidget(QLabel(tr("Body:")), 0, 0)
        self.body_edit = QLineEdit()
        self.body_edit.setReadOnly(True)
        self.body_edit.setPlaceholderText("-")
        body.addWidget(self.body_edit, 0, 1, 1, 2)

        body.addWidget(QLabel(tr("Start:")), 1, 0)
        self.start_edit = QLineEdit()
        self.start_edit.setReadOnly(True)
        self.start_edit.setPlaceholderText("-")
        body.addWidget(self.start_edit, 1, 1, 1, 2)

        body.addWidget(QLabel(tr("Target:")), 2, 0)
        self.target_edit = QLineEdit()
        self.target_edit.setReadOnly(True)
        self.target_edit.setPlaceholderText("-")
        body.addWidget(self.target_edit, 2, 1, 1, 2)

        body.setColumnStretch(1, 1)
        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.pick_body_btn = QPushButton(tr("Pick Body"))
        self.pick_body_btn.setObjectName("ghost")
        self.pick_body_btn.clicked.connect(self.pick_body_requested.emit)
        actions.addWidget(self.pick_body_btn)
        self.reset_btn = QPushButton(tr("Reset"))
        self.reset_btn.setObjectName("ghost")
        self.reset_btn.clicked.connect(self.reset_requested.emit)
        actions.addWidget(self.reset_btn)
        actions.addStretch()

        self.btn_cancel = QPushButton("X")
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.clicked.connect(self.cancel_requested.emit)
        actions.addWidget(self.btn_cancel)
        layout.addLayout(actions)

        self.hide()

    def set_status(self, text: str):
        self.status_label.setText(text)

    def set_body(self, name: str):
        self.body_edit.setText(name or "")

    def set_start_point(self, p):
        self.start_edit.setText(self._format_point(p) if p else "")

    def set_target_point(self, p):
        self.target_edit.setText(self._format_point(p) if p else "")

    def reset(self):
        self.set_body("")
        self.set_start_point(None)
        self.set_target_point(None)
        self.set_status(tr("Pick body"))

    def _format_point(self, p):
        return f"{p[0]:.2f}, {p[1]:.2f}, {p[2]:.2f}"

    def show_at(self, pos_widget):
        self.show()
        self.raise_()
        _position_panel_right_mid(self, pos_widget)
