"""
MashCad - Tool Panel
Übersichtliche Werkzeugpalette für den Sketcher
"""

import sys
import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIcon, QKeySequence
# Pfad-Hack, falls i18n nicht gefunden wird (optional, je nach Struktur)
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from i18n import tr  # <--- NEU: Import
from gui.design_tokens import DesignTokens

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QGridLayout, QSpinBox, QDoubleSpinBox,
    QGroupBox, QCheckBox, QSlider, QToolButton, QButtonGroup,
    QSizePolicy
)
from gui.widgets.collapsible_section import CollapsibleSection

class ToolButton(QToolButton):
    """Einzelner Werkzeug-Button"""
    
    def __init__(self, text: str, shortcut: str = "", tooltip: str = "", parent=None):
        super().__init__(parent)
        self.setText(text)
        clean_tooltip = tr(tooltip) if tooltip else text
        self.setToolTip(f"{clean_tooltip} [{shortcut}]" if shortcut else clean_tooltip)
        
        self.setCheckable(True)
        self.setMinimumSize(60, 30) # Höhe leicht reduziert für Kompaktheit
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.NoFocus)
        
        p = DesignTokens.COLOR_PRIMARY.name()
        bg = DesignTokens.COLOR_BG_PANEL.name()
        elevated = DesignTokens.COLOR_BG_ELEVATED.name()
        txt = DesignTokens.COLOR_TEXT_PRIMARY.name()
        self.setStyleSheet(f"""
            QToolButton {{
                background-color: {bg};
                border: 1px solid {DesignTokens.COLOR_BORDER.name()};
                border-radius: 3px;
                color: {txt};
                font-family: Segoe UI, sans-serif;
                font-size: 11px;
                padding: 4px;
            }}
            QToolButton:hover {{
                background-color: {elevated};
                border-color: #555;
                color: white;
            }}
            QToolButton:checked {{
                background-color: {p};
                border-color: {p};
                color: white;
            }}
            QToolButton:pressed {{
                background-color: {DesignTokens.COLOR_ACCENT.name()};
            }}
        """)


class ToolPanel(QFrame):
    """Werkzeug-Panel mit allen Sketch-Tools"""

    tool_selected = Signal(str)
    option_changed = Signal(str, object)
    finish_sketch_requested = Signal()  # Signal zum Beenden des Sketches
    rotate_view_requested = Signal()  # Signal zum Drehen der Sketch-Ansicht
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # WICHTIG: Keine harte Obergrenze mehr, damit Text Platz hat
        self.setMinimumWidth(220)
        # self.setMaximumWidth(220) <--- ENTFERNT
        
        bg = DesignTokens.COLOR_BG_PANEL.name()
        txt = DesignTokens.COLOR_TEXT_PRIMARY.name()
        muted = DesignTokens.COLOR_TEXT_MUTED.name()
        border = DesignTokens.COLOR_BORDER.name()
        elevated = DesignTokens.COLOR_BG_ELEVATED.name()
        self.setStyleSheet(f"""
            QFrame {{ 
                background: {bg}; 
                border: none;
            }}
            QLabel {{ color: {txt}; font-size: 11px; font-weight: bold; }}
            QGroupBox {{ 
                border: 1px solid {border}; 
                border-radius: 2px; 
                margin-top: 2ex; 
                font-weight: bold;
                text-transform: uppercase;
                color: {muted};
                font-size: 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 5px; padding: 0 3px; }}
            QSpinBox, QDoubleSpinBox {{
                background: {elevated}; border: 1px solid {border}; color: {txt};
                padding: 4px; border-radius: 2px;
            }}
            QCheckBox {{ color: {txt}; font-size: 11px; spacing: 5px; }}
        """)
        
        self.buttons = {}
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        
        self._setup_ui()
    
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === SKETCH BEENDEN BUTTON (ganz oben, immer sichtbar) ===
        finish_container = QWidget()
        finish_container.setStyleSheet(f"background: {DesignTokens.COLOR_BG_PANEL.name()};")
        finish_layout = QHBoxLayout(finish_container)
        finish_layout.setContentsMargins(8, 8, 8, 8)

        self.btn_finish_sketch = QPushButton("✓ Sketch beenden (Esc)")
        success = DesignTokens.COLOR_SUCCESS.name()
        self.btn_finish_sketch.setStyleSheet(f"""
            QPushButton {{
                background: {success};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 16px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: #16a34a;
            }}
        """)
        self.btn_finish_sketch.setCursor(Qt.PointingHandCursor)
        self.btn_finish_sketch.clicked.connect(self.finish_sketch_requested.emit)
        finish_layout.addWidget(self.btn_finish_sketch)
        main_layout.addWidget(finish_container)

        # Scroll Area Setup
        scroll = QScrollArea()
        scroll.setWidgetResizable(True) # Wichtig: Passt Breite an Inhalt an
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        # WICHTIG: Horizontalen Scrollbalken verbieten
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Vertikalen nur bei Bedarf (wenn Fenster zu klein ist)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(content_widget)
        # Margins und Spacing reduziert für kompaktes Design
        layout.setContentsMargins(6, 6, 6, 6) 
        layout.setSpacing(8) 
        
        # Titel
        title = QLabel(tr("TOOLS"))
        title.setStyleSheet("color: #0078d4; padding-bottom: 5px; border-bottom: 1px solid #333;")
        layout.addWidget(title)
        
        # === ZEICHNEN ===
        draw_group = self._create_group(tr("Draw"), expanded=True)
        draw_container = QWidget()
        draw_layout = QGridLayout(draw_container)
        draw_layout.setContentsMargins(0, 0, 0, 0)
        draw_layout.setSpacing(4)
        
        tools_draw = [
            (f"✎ {tr('Line')}", "line", "L", "Line", 0, 0),
            (f"▭ {tr('Rectangle')}", "rectangle", "R", "Rectangle", 0, 1),
            (f"◯ {tr('Circle')}", "circle", "C", "Circle", 1, 0),
            (f"⬡ {tr('Polygon')}", "polygon", "P", "Polygon", 1, 1),
            (f"◠ {tr('Arc')}", "arc_3point", "A", "Arc", 2, 0),
            (f"El {tr('Ellipse')}", "ellipse", "", "Ellipse", 2, 1),
            (f"⊂⊃ {tr('Slot')}", "slot", "", "Slot", 3, 0),
            (f"~ {tr('Spline')}", "spline", "", "Spline", 3, 1),
            (f"• {tr('Point')}", "point", "", "Point", 4, 0),
            (f"⬅ {tr('Project')}", "project", "P", "Project", 4, 1),
        ]
        
        for text, name, shortcut, key, row, col in tools_draw:
            btn = ToolButton(text, shortcut, tr(key)) 
            btn.clicked.connect(lambda checked, n=name: self._on_tool_clicked(n))
            self.buttons[name] = btn
            self.button_group.addButton(btn)
            draw_layout.addWidget(btn, row, col)
        
        draw_group.content_layout.addWidget(draw_container)
        layout.addWidget(draw_group)
        
        
        # === SHAPES (Sonderformen) ===
        shapes_group = self._create_group(tr("Shapes"))
        shapes_container = QWidget()
        shapes_layout = QGridLayout(shapes_container)
        shapes_layout.setContentsMargins(0, 0, 0, 0)
        shapes_layout.setSpacing(4)
        
        tools_shapes = [
            (f"⚙ {tr('Gear')}", "gear", "", "Gear", 0, 0),
            (f"★ {tr('Star')}", "star", "", "Star", 0, 1),
            (f"⬢ {tr('Nut')}", "nut", "", "Nut", 1, 0),
            (f"A {tr('Text')}", "text", "", "Text", 1, 1),
        ]
        
        for text, name, shortcut, key, row, col in tools_shapes:
            btn = ToolButton(text, shortcut, tr(key))
            btn.clicked.connect(lambda checked, n=name: self._on_tool_clicked(n))
            self.buttons[name] = btn
            self.button_group.addButton(btn)
            shapes_layout.addWidget(btn, row, col)
            
        shapes_group.content_layout.addWidget(shapes_container)
        layout.addWidget(shapes_group)
        
        
        # === BEARBEITEN ===
        edit_group = self._create_group(tr("Modify"), expanded=True)
        edit_container = QWidget()
        edit_layout = QGridLayout(edit_container)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        edit_layout.setSpacing(4)
        
        tools_edit = [
            (f"⬚ {tr('Select')}", "select", "Space", "Select", 0, 0),
            (f"✥ {tr('Move')}", "move", "M", "Move", 0, 1),
            (f"⧉ {tr('Copy')}", "copy", "K", "Copy", 1, 0),
            (f"↻ {tr('Rotate')}", "rotate", "Q", "Rotate", 1, 1),
            (f"⧎ {tr('Mirror')}", "mirror", "I", "Mirror", 2, 0),
            (f"⤢ {tr('Scale')}", "scale", "S", "Scale", 2, 1),
            (f"✂ {tr('Trim')}", "trim", "T", "Trim", 3, 0),
            (f"◐ {tr('Offset')}", "offset", "O", "Offset", 3, 1),
            (f"⌓ {tr('Fillet')}", "fillet_2d", "", "Fillet", 4, 0),
            (f"⌐ {tr('Chamfer')}", "chamfer_2d", "", "Chamfer", 4, 1),
        ]
        
        for text, name, shortcut, key, row, col in tools_edit:
            btn = ToolButton(text, shortcut, tr(key))
            btn.clicked.connect(lambda checked, n=name: self._on_tool_clicked(n))
            self.buttons[name] = btn
            self.button_group.addButton(btn)
            edit_layout.addWidget(btn, row, col)
        
        edit_group.content_layout.addWidget(edit_container)
        layout.addWidget(edit_group)
        
        pattern_group = self._create_group(tr("Patterns"))
        pattern_container = QWidget()
        pattern_layout = QGridLayout(pattern_container)
        pattern_layout.setContentsMargins(0, 0, 0, 0)
        pattern_layout.setSpacing(4)
        
        tools_pattern = [
            (f"⋮⋮⋮ {tr('Linear Pattern')}", "pattern_linear", "", "Linear Pattern", 0, 0),
            (f"⁕ {tr('Circular Pattern')}", "pattern_circular", "", "Circular Pattern", 0, 1),
        ]
        
        for text, name, shortcut, key, row, col in tools_pattern:
            # Tooltip erweitern
            tooltip = tr(key)
            if name == "pattern_linear": tooltip += " (Select -> Drag -> Tab)"
            if name == "pattern_circular": tooltip += " (Select -> Click Center -> Tab)"
            
            btn = ToolButton(text, shortcut, tooltip)
            btn.clicked.connect(lambda checked, n=name: self._on_tool_clicked(n))
            self.buttons[name] = btn
            self.button_group.addButton(btn)
            pattern_layout.addWidget(btn, row, col)
            
        pattern_group.content_layout.addWidget(pattern_container)
        layout.addWidget(pattern_group)


        # === CONSTRAINTS ===
        const_group = self._create_group(tr("Constraints"))
        const_container = QWidget()
        const_layout = QGridLayout(const_container)
        const_layout.setContentsMargins(0, 0, 0, 0)
        const_layout.setSpacing(4)
        
        tools_const = [
            (f"📏 {tr('Dimension')}", "dimension", "D", "Dimension", 0, 0),
            (f"∠ {tr('Angle')}", "dimension_angle", "", "Angle", 0, 1),
            (f"─ {tr('Horizontal')}", "horizontal", "H", "Horizontal", 1, 0),
            (f"│ {tr('Vertical')}", "vertical", "V", "Vertical", 1, 1),
            (f"∥ {tr('Parallel')}", "parallel", "", "Parallel", 2, 0),
            (f"⊥ {tr('Perpendicular')}", "perpendicular", "", "Perpendicular", 2, 1),
            (f"= {tr('Equal')}", "equal", "", "Equal", 3, 0),
            (f"◎ {tr('Concentric')}", "concentric", "", "Concentric", 3, 1),
            (f"⌒ {tr('Tangent')}", "tangent", "", "Tangent", 4, 0),
        ]
        
        for text, name, shortcut, key, row, col in tools_const:
            btn = ToolButton(text, shortcut, tr(key))
            btn.clicked.connect(lambda checked, n=name: self._on_tool_clicked(n))
            self.buttons[name] = btn
            self.button_group.addButton(btn)
            const_layout.addWidget(btn, row, col)
        
        const_group.content_layout.addWidget(const_container)
        layout.addWidget(const_group)

        # === IMPORT/EXPORT ===
        import_group = self._create_group(tr("Import/Export"))
        import_container = QWidget()
        import_layout = QGridLayout(import_container)
        import_layout.setContentsMargins(0, 0, 0, 0)
        import_layout.setSpacing(4)

        tools_import = [
            (f"📥 {tr('DXF Import')}", "import_dxf", "", "Import DXF file", 0, 0),
            (f"📤 {tr('DXF Export')}", "export_dxf", "", "Export to DXF", 0, 1),
            (f"🖼 {tr('Canvas')}", "canvas", "", "Image Reference", 1, 0),
        ]

        for text, name, shortcut, tooltip, row, col in tools_import:
            btn = ToolButton(text, shortcut, tr(tooltip))
            btn.setCheckable(False)  # Import/Export sind keine Toggle-Buttons
            btn.clicked.connect(lambda checked, n=name: self._on_tool_clicked(n))
            self.buttons[name] = btn
            import_layout.addWidget(btn, row, col)

        import_group.content_layout.addWidget(import_container)
        layout.addWidget(import_group)

        # === OPTIONEN ===
        options_group = self._create_group(tr("Settings"))
        options_layout = options_group.content_layout
        options_layout.setSpacing(6)
        
        self.grid_snap_cb = QCheckBox(tr("Grid Snap") + " (G)")
        self.grid_snap_cb.setChecked(True)
        self.grid_snap_cb.setFocusPolicy(Qt.ClickFocus)
        self.grid_snap_cb.toggled.connect(lambda v: self.option_changed.emit("grid_snap", v))
        options_layout.addWidget(self.grid_snap_cb)
        
        self.construction_cb = QCheckBox(tr("Construction") + " (X)")
        self.construction_cb.setFocusPolicy(Qt.ClickFocus)
        self.construction_cb.toggled.connect(lambda v: self.option_changed.emit("construction", v))
        options_layout.addWidget(self.construction_cb)
        
        grid_row = QHBoxLayout()
        grid_row.addWidget(QLabel(tr("Grid") + ":"))
        self.grid_size_spin = QDoubleSpinBox()
        self.grid_size_spin.setRange(0.5, 100)
        self.grid_size_spin.setValue(1)
        self.grid_size_spin.setSuffix(" mm")
        self.grid_size_spin.setFocusPolicy(Qt.ClickFocus)
        self.grid_size_spin.valueChanged.connect(lambda v: self.option_changed.emit("grid_size", v))
        grid_row.addWidget(self.grid_size_spin)
        options_layout.addLayout(grid_row)

        # Snap-Radius Einstellung
        snap_row = QHBoxLayout()
        snap_row.addWidget(QLabel(tr("Snap Radius") + ":"))
        self.snap_radius_spin = QSpinBox()
        self.snap_radius_spin.setRange(5, 50)
        self.snap_radius_spin.setValue(15)
        self.snap_radius_spin.setSuffix(" px")
        self.snap_radius_spin.setFocusPolicy(Qt.ClickFocus)
        self.snap_radius_spin.valueChanged.connect(lambda v: self.option_changed.emit("snap_radius", v))
        snap_row.addWidget(self.snap_radius_spin)
        options_layout.addLayout(snap_row)

        # Ansicht drehen Button
        self.btn_rotate_view = QPushButton(f"↻ {tr('Rotate View')} (Shift+R)")
        self.btn_rotate_view.setStyleSheet("""
            QPushButton {
                background: #3a3a3a;
                color: #ccc;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #4a4a4a;
                border-color: #0078d4;
            }
        """)
        self.btn_rotate_view.setCursor(Qt.PointingHandCursor)
        self.btn_rotate_view.setFocusPolicy(Qt.NoFocus)  # Space soll nicht den Button aktivieren
        self.btn_rotate_view.clicked.connect(self.rotate_view_requested.emit)
        options_layout.addWidget(self.btn_rotate_view)

        layout.addWidget(options_group)
        
        layout.addStretch()
        
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
        
        if "select" in self.buttons:
            self.buttons["select"].setChecked(True)

    def _create_group(self, title: str, expanded: bool = False) -> CollapsibleSection:
        section = CollapsibleSection(title, expanded=expanded)
        return section
    
    def _on_tool_clicked(self, tool_name: str):
        self.tool_selected.emit(tool_name)
    
    def set_tool(self, tool_name: str):
        if tool_name in self.buttons:
            self.buttons[tool_name].setChecked(True)
    
    def set_active_tool(self, tool_name: str):
        self.set_tool(tool_name)
    
    def set_grid_snap(self, enabled: bool):
        self.grid_snap_cb.setChecked(enabled)

    def set_construction(self, enabled: bool):
        self.construction_cb.setChecked(enabled)

    def set_snap_radius(self, radius: int):
        self.snap_radius_spin.setValue(radius)


class PropertiesPanel(QFrame):
    """Eigenschaften-Panel für ausgewählte Elemente"""
    
    property_changed = Signal(str, object)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(140)
        self.setMaximumWidth(200)
        bg = DesignTokens.COLOR_BG_PANEL.name()
        txt = DesignTokens.COLOR_TEXT_PRIMARY.name()
        muted = DesignTokens.COLOR_TEXT_MUTED.name()
        border = DesignTokens.COLOR_BORDER.name()
        elevated = DesignTokens.COLOR_BG_ELEVATED.name()
        self.setStyleSheet(f"""
            QFrame {{ 
                background: {bg}; 
                border-left: 1px solid {border}; 
            }}
            QLabel {{ color: {muted}; font-size: 9px; }}
            QGroupBox {{ 
                color: {muted}; 
                font-size: 9px; 
                font-weight: bold;
                border: 1px solid {border};
                border-radius: 3px;
                margin-top: 6px;
                padding: 4px;
                padding-top: 12px;
                background: {bg};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 6px;
                padding: 0 3px;
            }}
            QDoubleSpinBox, QSpinBox {{
                background: {elevated};
                border: 1px solid {border};
                color: {txt};
                padding: 2px;
                border-radius: 2px;
            }}
        """)
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        
        # Titel
        title = QLabel(tr("PROPERTIES")) # i18n
        title.setFont(QFont("Arial", 9, QFont.Bold))
        title.setStyleSheet(f"color: {DesignTokens.COLOR_PRIMARY.name()}; padding: 2px 0; border-bottom: 1px solid {DesignTokens.COLOR_BORDER.name()};")
        layout.addWidget(title)
        
        # Info
        self.info_label = QLabel(tr("No Selection")) # i18n
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)
        
        # Eigenschaften-Gruppe
        self.props_group = QGroupBox(tr("Details")) # i18n
        self.props_layout = QVBoxLayout()
        self.props_layout.setSpacing(4)
        self.props_group.setLayout(self.props_layout)
        layout.addWidget(self.props_group)
        
        # Koordinaten-Gruppe
        self.coords_group = QGroupBox(tr("Position")) # i18n
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


