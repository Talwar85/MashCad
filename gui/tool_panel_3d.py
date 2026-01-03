"""
LiteCAD - 3D Tool Panel
Werkzeugleiste für den 3D-Modus (analog zum 2D Sketch ToolPanel)
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QGridLayout, QSpinBox, QDoubleSpinBox,
    QGroupBox, QCheckBox, QSlider, QToolButton, QButtonGroup,
    QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from i18n import tr


class ToolButton3D(QToolButton):
    """Einzelner Werkzeug-Button für 3D-Modus"""
    
    def __init__(self, text: str, shortcut: str = "", tooltip: str = "", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setToolTip(f"{tooltip}\n[{shortcut}]" if shortcut else tooltip)
        self.setCheckable(True)
        self.setMinimumSize(60, 26)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet("""
            QToolButton {
                background: #2d2d30;
                border: 1px solid #3a3a3a;
                border-radius: 2px;
                color: #aaa;
                font-size: 10px;
                padding: 3px 6px;
                text-align: left;
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
            QToolButton:disabled {
                background: #252526;
                color: #555;
                border-color: #333;
            }
        """)


class ToolPanel3D(QFrame):
    """Werkzeug-Panel für den 3D-Modus"""
    
    tool_selected = Signal(str)
    action_triggered = Signal(str)
    
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
            QLabel { 
                color: #888; 
                font-size: 9px; 
            }
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
        """)
        
        self.buttons = {}
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(False)
        
        self._setup_ui()
    
    def _setup_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: #2d2d30;
                width: 6px;
            }
            QScrollBar::handle:vertical {
                background: #555;
                border-radius: 3px;
            }
        """)
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        
        # Titel
        title = QLabel("3D TOOLS")
        title.setFont(QFont("Arial", 9, QFont.Bold))
        title.setStyleSheet("color: #0078d4; padding: 2px 0; border-bottom: 1px solid #3a3a3a;")
        layout.addWidget(title)
        
        # === CREATE ===
        create_group = self._create_group(tr("Create"))
        create_layout = QGridLayout()
        create_layout.setSpacing(3)
        
        tools_create = [
            ("Sketch", "new_sketch", "S", tr("New Sketch")),
            ("Extrude", "extrude", "E", tr("Extrude face")),
            ("Revolve", "revolve", "", tr("Revolve around axis")),
            ("Sweep", "sweep", "", tr("Sweep along path")),
            ("Loft", "loft", "", tr("Loft between profiles")),
            ("Box", "primitive_box", "", tr("Create box")),
            ("Cylinder", "primitive_cylinder", "", tr("Create cylinder")),
            ("Sphere", "primitive_sphere", "", tr("Create sphere")),
        ]
        
        for i, (text, name, shortcut, tooltip) in enumerate(tools_create):
            btn = ToolButton3D(text, shortcut, tooltip)
            btn.clicked.connect(lambda checked, n=name: self._on_action(n))
            self.buttons[name] = btn
            create_layout.addWidget(btn, i // 2, i % 2)
        
        create_group.setLayout(create_layout)
        layout.addWidget(create_group)
        
        # === MODIFY ===
        modify_group = self._create_group(tr("Modify"))
        modify_layout = QGridLayout()
        modify_layout.setSpacing(3)
        
        tools_modify = [
            ("Move", "move_body", "M", tr("Move body")),
            ("Copy", "copy_body", "", tr("Copy body")),
            ("Rotate", "rotate_body", "", tr("Rotate body")),
            ("Mirror", "mirror_body", "", tr("Mirror body")),
            ("Scale", "scale_body", "", tr("Scale body")),
            ("Union", "boolean_union", "", tr("Boolean union")),
            ("Cut", "boolean_cut", "", tr("Boolean cut")),
            ("Intersect", "boolean_intersect", "", tr("Boolean intersect")),
        ]
        
        for i, (text, name, shortcut, tooltip) in enumerate(tools_modify):
            btn = ToolButton3D(text, shortcut, tooltip)
            btn.clicked.connect(lambda checked, n=name: self._on_action(n))
            self.buttons[name] = btn
            modify_layout.addWidget(btn, i // 2, i % 2)
        
        modify_group.setLayout(modify_layout)
        layout.addWidget(modify_group)
        
        # === DETAIL ===
        detail_group = self._create_group(tr("Detail"))
        detail_layout = QGridLayout()
        detail_layout.setSpacing(3)
        
        tools_detail = [
            ("Fillet", "fillet", "F", tr("Fillet edges")),
            ("Chamfer", "chamfer", "", tr("Chamfer edges")),
            ("Shell", "shell", "", tr("Shell body")),
            ("Hole", "hole", "H", tr("Create hole")),
            ("Thread", "thread", "", tr("Add thread")),
            ("Pattern", "pattern", "", tr("Create pattern")),
        ]
        
        for i, (text, name, shortcut, tooltip) in enumerate(tools_detail):
            btn = ToolButton3D(text, shortcut, tooltip)
            btn.clicked.connect(lambda checked, n=name: self._on_action(n))
            self.buttons[name] = btn
            detail_layout.addWidget(btn, i // 2, i % 2)
        
        detail_group.setLayout(detail_layout)
        layout.addWidget(detail_group)
        
        # === INSPECT ===
        inspect_group = self._create_group(tr("Inspect"))
        inspect_layout = QGridLayout()
        inspect_layout.setSpacing(3)
        
        tools_inspect = [
            ("Measure", "measure", "", tr("Measure distance")),
            ("Section", "section", "", tr("Section view")),
        ]
        
        for i, (text, name, shortcut, tooltip) in enumerate(tools_inspect):
            btn = ToolButton3D(text, shortcut, tooltip)
            btn.clicked.connect(lambda checked, n=name: self._on_action(n))
            self.buttons[name] = btn
            inspect_layout.addWidget(btn, i // 2, i % 2)
        
        inspect_group.setLayout(inspect_layout)
        layout.addWidget(inspect_group)
        
        layout.addStretch()
        
        scroll.setWidget(content)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)
    
    def _create_group(self, title: str) -> QGroupBox:
        group = QGroupBox(title)
        return group
    
    def _on_action(self, name: str):
        for btn in self.buttons.values():
            btn.setChecked(False)
        self.action_triggered.emit(name)
    
    def set_tool_enabled(self, name: str, enabled: bool):
        if name in self.buttons:
            self.buttons[name].setEnabled(enabled)
    
    def highlight_tool(self, name: str):
        for n, btn in self.buttons.items():
            btn.setChecked(n == name)


class BodyPropertiesPanel(QFrame):
    """Properties panel for selected 3D bodies"""
    
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
            QLabel { 
                color: #888; 
                font-size: 10px; 
            }
        """)
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        
        title = QLabel("PROPERTIES")
        title.setFont(QFont("Arial", 9, QFont.Bold))
        title.setStyleSheet("color: #0078d4; padding: 2px 0;")
        layout.addWidget(title)
        
        self.info_label = QLabel(tr("No selection"))
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #666; padding: 8px 0;")
        layout.addWidget(self.info_label)
        
        layout.addStretch()
    
    def update_body(self, body):
        if body is None:
            self.info_label.setText(tr("No selection"))
            return
        
        info_text = f"<b>{body.name}</b><br>"
        
        if hasattr(body, '_mesh_vertices'):
            verts = len(body._mesh_vertices)
            faces = len(body._mesh_triangles) if hasattr(body, '_mesh_triangles') else 0
            info_text += f"<br>Vertices: {verts}"
            info_text += f"<br>Faces: {faces}"
        
        if hasattr(body, 'features') and body.features:
            info_text += f"<br><br><b>Features:</b>"
            for f in body.features:
                info_text += f"<br>• {f.name}"
        
        self.info_label.setText(info_text)
    
    def clear(self):
        self.update_body(None)
