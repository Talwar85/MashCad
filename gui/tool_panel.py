"""
LiteCAD - Tool Panel
Übersichtliche Werkzeugpalette für den Sketcher
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QGridLayout, QSpinBox, QDoubleSpinBox,
    QGroupBox, QCheckBox, QSlider, QToolButton, QButtonGroup,
    QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIcon
from enum import Enum


class ToolCategory(Enum):
    DRAW = "Zeichnen"
    EDIT = "Bearbeiten"
    CONSTRAIN = "Constraints"
    PATTERN = "Muster"
    SPECIAL = "Spezial"


class ToolButton(QToolButton):
    """Einzelner Werkzeug-Button"""
    
    def __init__(self, text: str, shortcut: str = "", tooltip: str = "", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setToolTip(f"{tooltip}\n[{shortcut}]" if shortcut else tooltip)
        self.setCheckable(True)
        self.setMinimumSize(50, 26)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet("""
            QToolButton {
                background: #2d2d30;
                border: 1px solid #3a3a3a;
                border-radius: 2px;
                color: #aaa;
                font-size: 10px;
                padding: 3px;
            }
            QToolButton:hover {
                background: #383838;
                border-color: #4a4a4a;
                color: #ddd;
            }
            QToolButton:checked {
                background: #0e639c;
                border-color: #0e639c;
                color: white;
            }
            QToolButton:pressed {
                background: #094771;
            }
        """)


class ToolPanel(QFrame):
    """Werkzeug-Panel mit allen Sketch-Tools"""
    
    tool_selected = Signal(str)  # Tool-Name
    option_changed = Signal(str, object)  # Option-Name, Wert
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(140)
        self.setMaximumWidth(200)
        self.setStyleSheet("""
            QFrame { 
                background: #1e1e1e; 
                border: none;
                border-right: 1px solid #333; 
            }
            QLabel { color: #888; font-size: 9px; }
            QGroupBox { 
                color: #666; 
                font-size: 9px; 
                font-weight: bold;
                border: 1px solid #333;
                border-radius: 3px;
                margin-top: 6px;
                padding: 4px;
                padding-top: 12px;
                background: #1e1e1e;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 6px;
                padding: 0 3px;
            }
            QSpinBox, QDoubleSpinBox {
                background: #2d2d30;
                border: 1px solid #3a3a3a;
                color: #ccc;
                padding: 2px;
                border-radius: 2px;
            }
            QCheckBox { color: #888; font-size: 9px; }
            QCheckBox::indicator { width: 12px; height: 12px; }
        """)
        
        self.buttons = {}
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        
        # Titel
        title = QLabel("SKETCH TOOLS")
        title.setFont(QFont("Arial", 9, QFont.Bold))
        title.setStyleSheet("color: #0078d4; padding: 2px 0; border-bottom: 1px solid #333;")
        layout.addWidget(title)
        
        # === ZEICHNEN ===
        draw_group = self._create_group("Zeichnen")
        draw_layout = QGridLayout()
        draw_layout.setSpacing(4)
        
        # Konsolidierte Tools (wie Fusion360)
        tools_draw = [
            ("✎ Linie", "line", "L", 0, 0),
            ("▭ Rechteck", "rectangle", "R", 0, 1),
            ("◯ Kreis", "circle", "C", 1, 0),
            ("⬡ Polygon", "polygon", "P", 1, 1),
            ("◠ Bogen", "arc_3point", "A", 2, 0),
            ("⊂⊃ Slot", "slot", "", 2, 1),
            ("~ Spline", "spline", "", 3, 0),
            ("• Punkt", "point", "", 3, 1),
        ]
        
        for text, name, shortcut, row, col in tools_draw:
            btn = ToolButton(text, shortcut, text.split()[1] if len(text.split()) > 1 else text)
            btn.clicked.connect(lambda checked, n=name: self._on_tool_clicked(n))
            self.buttons[name] = btn
            self.button_group.addButton(btn)
            draw_layout.addWidget(btn, row, col)
        
        draw_group.setLayout(draw_layout)
        layout.addWidget(draw_group)
        
        # === BEARBEITEN ===
        edit_group = self._create_group("Bearbeiten")
        edit_layout = QGridLayout()
        edit_layout.setSpacing(4)
        
        tools_edit = [
            ("⬚ Auswahl", "select", "Space", 0, 0),
            ("✥ Verschieben", "move", "M", 0, 1),
            ("⧉ Kopieren", "copy", "K", 1, 0),
            ("↻ Drehen", "rotate", "Q", 1, 1),
            ("⧎ Spiegeln", "mirror", "I", 2, 0),
            ("⤢ Skalieren", "scale", "S", 2, 1),
            ("✂ Trimmen", "trim", "T", 3, 0),
            ("◐ Offset", "offset", "O", 3, 1),
            ("⌓ Verrunden", "fillet_2d", "", 4, 0),
            ("⌐ Fase", "chamfer_2d", "", 4, 1),
        ]
        
        for text, name, shortcut, row, col in tools_edit:
            btn = ToolButton(text, shortcut, text.split()[1] if len(text.split()) > 1 else text)
            btn.clicked.connect(lambda checked, n=name: self._on_tool_clicked(n))
            self.buttons[name] = btn
            self.button_group.addButton(btn)
            edit_layout.addWidget(btn, row, col)
        
        edit_group.setLayout(edit_layout)
        layout.addWidget(edit_group)
        
        # === CONSTRAINTS ===
        const_group = self._create_group("Constraints")
        const_layout = QGridLayout()
        const_layout.setSpacing(4)
        
        tools_const = [
            ("📏 Maß", "dimension", "D", 0, 0),
            ("∠ Winkel", "dimension_angle", "", 0, 1),
            ("─ Horizontal", "horizontal", "H", 1, 0),
            ("│ Vertikal", "vertical", "V", 1, 1),
            ("∥ Parallel", "parallel", "", 2, 0),
            ("⊥ Senkrecht", "perpendicular", "", 2, 1),
            ("= Gleich", "equal", "", 3, 0),
            ("◎ Konzentrisch", "concentric", "", 3, 1),
            ("⌒ Tangent", "tangent", "", 4, 0),
        ]
        
        for text, name, shortcut, row, col in tools_const:
            btn = ToolButton(text, shortcut, text.split()[1] if len(text.split()) > 1 else text)
            btn.clicked.connect(lambda checked, n=name: self._on_tool_clicked(n))
            self.buttons[name] = btn
            self.button_group.addButton(btn)
            const_layout.addWidget(btn, row, col)
        
        const_group.setLayout(const_layout)
        layout.addWidget(const_group)
        
        # === MUSTER ===
        pattern_group = self._create_group("Muster")
        pattern_layout = QGridLayout()
        pattern_layout.setSpacing(4)
        
        tools_pattern = [
            ("▤ Linear", "pattern_linear", "", 0, 0),
            ("◔ Circular", "pattern_circular", "", 0, 1),
        ]
        
        for text, name, shortcut, row, col in tools_pattern:
            btn = ToolButton(text, shortcut, text.split()[1] if len(text.split()) > 1 else text)
            btn.clicked.connect(lambda checked, n=name: self._on_tool_clicked(n))
            self.buttons[name] = btn
            self.button_group.addButton(btn)
            pattern_layout.addWidget(btn, row, col)
        
        pattern_group.setLayout(pattern_layout)
        layout.addWidget(pattern_group)
        
        # === SPEZIAL ===
        special_group = self._create_group("Spezial")
        special_layout = QGridLayout()
        special_layout.setSpacing(4)
        
        tools_special = [
            ("⚙ Zahnrad", "gear", "", 0, 0),
            ("★ Stern", "star", "", 0, 1),
            ("⬡ Mutter", "nut", "N", 1, 0),
            ("T Text", "text", "", 1, 1),
        ]
        
        for text, name, shortcut, row, col in tools_special:
            btn = ToolButton(text, shortcut, text.split()[1] if len(text.split()) > 1 else text)
            btn.clicked.connect(lambda checked, n=name: self._on_tool_clicked(n))
            self.buttons[name] = btn
            self.button_group.addButton(btn)
            special_layout.addWidget(btn, row, col)
        
        special_group.setLayout(special_layout)
        layout.addWidget(special_group)
        
        # === OPTIONEN (nur allgemeine Einstellungen) ===
        # Tool-spezifische Optionen (Rechteck, Kreis, Polygon) sind jetzt
        # in der schwebenden Palette direkt im Editor
        options_group = self._create_group("Einstellungen")
        options_layout = QVBoxLayout()
        options_layout.setSpacing(6)
        
        # Grid Snap
        self.grid_snap_cb = QCheckBox("Grid Snap (G)")
        self.grid_snap_cb.setChecked(True)
        self.grid_snap_cb.setFocusPolicy(Qt.ClickFocus)
        self.grid_snap_cb.toggled.connect(lambda v: self.option_changed.emit("grid_snap", v))
        options_layout.addWidget(self.grid_snap_cb)
        
        # Konstruktion
        self.construction_cb = QCheckBox("Konstruktion (X)")
        self.construction_cb.setFocusPolicy(Qt.ClickFocus)
        self.construction_cb.toggled.connect(lambda v: self.option_changed.emit("construction", v))
        options_layout.addWidget(self.construction_cb)
        
        # Grid-Größe
        grid_row = QHBoxLayout()
        grid_row.addWidget(QLabel("Grid:"))
        self.grid_size_spin = QDoubleSpinBox()
        self.grid_size_spin.setRange(0.5, 100)
        self.grid_size_spin.setValue(1)
        self.grid_size_spin.setSuffix(" mm")
        self.grid_size_spin.setFocusPolicy(Qt.ClickFocus)
        self.grid_size_spin.valueChanged.connect(lambda v: self.option_changed.emit("grid_size", v))
        grid_row.addWidget(self.grid_size_spin)
        options_layout.addLayout(grid_row)
        
        # Kreis-Segmente (für Face-Erkennung Genauigkeit)
        seg_row = QHBoxLayout()
        seg_row.addWidget(QLabel("○ Seg:"))
        self.circle_segments_spin = QSpinBox()
        self.circle_segments_spin.setRange(16, 256)
        self.circle_segments_spin.setValue(64)
        self.circle_segments_spin.setToolTip("Kreis-Segmente für Face-Erkennung\n(mehr = genauer, langsamer)")
        self.circle_segments_spin.setFocusPolicy(Qt.ClickFocus)
        self.circle_segments_spin.valueChanged.connect(lambda v: self.option_changed.emit("circle_segments", v))
        seg_row.addWidget(self.circle_segments_spin)
        options_layout.addLayout(seg_row)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # Stretch am Ende
        layout.addStretch()
        
        # Select als Default
        self.buttons["select"].setChecked(True)
    
    def _create_group(self, title: str) -> QGroupBox:
        group = QGroupBox(title)
        return group
    
    def _on_tool_clicked(self, tool_name: str):
        self.tool_selected.emit(tool_name)
    
    def set_tool(self, tool_name: str):
        """Setzt das aktive Tool von außen"""
        if tool_name in self.buttons:
            self.buttons[tool_name].setChecked(True)
    
    def set_active_tool(self, tool_name: str):
        """Alias für set_tool (Kompatibilität)"""
        self.set_tool(tool_name)
    
    def set_grid_snap(self, enabled: bool):
        self.grid_snap_cb.setChecked(enabled)
    
    def set_construction(self, enabled: bool):
        self.construction_cb.setChecked(enabled)


class PropertiesPanel(QFrame):
    """Eigenschaften-Panel für ausgewählte Elemente"""
    
    property_changed = Signal(str, object)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(140)
        self.setMaximumWidth(200)
        self.setStyleSheet("""
            QFrame { 
                background: #1e1e1e; 
                border-left: 1px solid #333; 
            }
            QLabel { color: #888; font-size: 9px; }
            QGroupBox { 
                color: #666; 
                font-size: 9px; 
                font-weight: bold;
                border: 1px solid #333;
                border-radius: 3px;
                margin-top: 6px;
                padding: 4px;
                padding-top: 12px;
                background: #1e1e1e;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 6px;
                padding: 0 3px;
            }
            QDoubleSpinBox, QSpinBox {
                background: #2d2d30;
                border: 1px solid #3a3a3a;
                color: #ccc;
                padding: 2px;
                border-radius: 2px;
            }
        """)
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        
        # Titel
        title = QLabel("PROPERTIES")
        title.setFont(QFont("Arial", 9, QFont.Bold))
        title.setStyleSheet("color: #0078d4; padding: 2px 0; border-bottom: 1px solid #333;")
        layout.addWidget(title)
        
        # Info
        self.info_label = QLabel("No selection")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)
        
        # Eigenschaften-Gruppe
        self.props_group = QGroupBox("Details")
        self.props_layout = QVBoxLayout()
        self.props_layout.setSpacing(4)
        self.props_group.setLayout(self.props_layout)
        layout.addWidget(self.props_group)
        
        # Koordinaten-Gruppe
        self.coords_group = QGroupBox("Position")
        coords_layout = QGridLayout()
        coords_layout.setSpacing(4)
        
        coords_layout.addWidget(QLabel("X:"), 0, 0)
        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(-10000, 10000)
        self.x_spin.setDecimals(2)
        coords_layout.addWidget(self.x_spin, 0, 1)
        
        coords_layout.addWidget(QLabel("Y:"), 1, 0)
        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(-10000, 10000)
        self.y_spin.setDecimals(2)
        coords_layout.addWidget(self.y_spin, 1, 1)
        
        self.coords_group.setLayout(coords_layout)
        layout.addWidget(self.coords_group)
        
        # Constraints-Liste
        self.constraints_group = QGroupBox("Constraints")
        self.constraints_layout = QVBoxLayout()
        self.constraints_label = QLabel("Keine")
        self.constraints_layout.addWidget(self.constraints_label)
        self.constraints_group.setLayout(self.constraints_layout)
        layout.addWidget(self.constraints_group)
        
        layout.addStretch()
        
        # Initial ausblenden
        self.props_group.hide()
        self.coords_group.hide()
        self.constraints_group.hide()
    
    def update_selection(self, lines: list, circles: list, arcs: list):
        """Aktualisiert die Anzeige basierend auf Auswahl"""
        total = len(lines) + len(circles) + len(arcs)
        
        if total == 0:
            self.info_label.setText("Keine Auswahl")
            self.props_group.hide()
            self.coords_group.hide()
            self.constraints_group.hide()
            return
        
        if total == 1:
            if lines:
                line = lines[0]
                self.info_label.setText(f"Linie\nLänge: {line.length:.2f} mm\nWinkel: {line.angle:.1f}°")
                self.x_spin.setValue(line.start.x)
                self.y_spin.setValue(line.start.y)
                self.coords_group.show()
            elif circles:
                c = circles[0]
                self.info_label.setText(f"Kreis\nRadius: {c.radius:.2f} mm\nDurchmesser: {c.radius*2:.2f} mm")
                self.x_spin.setValue(c.center.x)
                self.y_spin.setValue(c.center.y)
                self.coords_group.show()
            else:
                self.coords_group.hide()
        else:
            self.info_label.setText(f"{total} Elemente ausgewählt\n({len(lines)} Linien, {len(circles)} Kreise)")
            self.coords_group.hide()
        
        self.props_group.show()
    
    def clear(self):
        self.info_label.setText("Keine Auswahl")
        self.props_group.hide()
        self.coords_group.hide()
        self.constraints_group.hide()
