import os
from i18n import tr # Import hinzufügen

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QToolButton, QGroupBox, 
                               QGridLayout, QLabel, QScrollArea, QFrame, QSizePolicy)
from PySide6.QtCore import QSize, Qt, Signal

class ToolPanel3D(QWidget):
    action_triggered = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Keine Max-Width Einschränkung
        self.setMinimumWidth(220)
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; color: #e0e0e0; font-family: Segoe UI, sans-serif; font-size: 11px; }
            QGroupBox { 
                border: 1px solid #333; 
                border-radius: 2px; 
                margin-top: 2ex; 
                font-weight: bold;
                text-transform: uppercase;
                color: #888;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 5px; padding: 0 3px; }
            QToolButton {
                background-color: #2d2d30;
                border: 1px solid #3e3e3e;
                border-radius: 2px;
                color: #ccc;
                padding: 5px 10px;
                text-align: left;
            }
            QToolButton:hover { background-color: #3e3e42; border-color: #555; color: white; }
            QToolButton:pressed { background-color: #0078d4; border-color: #0078d4; }
        """)
        self._setup_ui()
        
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        # WICHTIG: Horizontalen Scrollbar ausblenden, Widget passt sich Breite an
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        
        self.layout = QVBoxLayout(content_widget)
        # Etwas kompaktere Ränder
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(10) # Reduziert von 15
        
        # --- Sketch & Base ---
        self._add_group("Sketch & Base", [
            (tr("New Sketch"), tr("Press S for new Sketch"), "new_sketch"),
            (tr("Extrude..."), tr("Extrude"), "extrude"),
        ])
        
        # --- Modify ---
        self._add_group(tr("Modify"), [
            (tr("Fillet"), "fillet"),
            (tr("Chamfer"), "chamfer"),
        ])

        # --- Transform ---
        self._add_group("Transform", [
            (tr("Move"), tr("Move"), "move_body"),
            (tr("Rotate"), tr("Rotate"), "rotate_body"),
            (tr("Scale"), tr("Scale"), "scale_body"),
            (tr("Mirror"), tr("Mirror"), "mirror_body"),
            (tr("Copy"), tr("Copy"), "copy_body"),
        ], grid=True)
        
        # --- Boolean ---
        self._add_group("Boolean", [
            (tr("Union") if tr("Union") != "Union" else "Union", "boolean_union"),
            (tr("Cut") if tr("Cut") != "Cut" else "Cut", "boolean_cut"),
            (tr("Intersect") if tr("Intersect") != "Intersect" else "Intersect", "boolean_intersect"),
        ])
        
        # --- Tools ---
        self._add_group(tr("TOOLS"), [
            (tr("Convert Mesh to CAD"), "Konvertiert Mesh zu Solid (BREP)", "convert_to_brep"), 
            (tr("Measure") if tr("Measure") != "Measure" else "Measure", "measure"),
        ])
        
        # --- Import/Export ---
        self._add_group(tr("File"), [
            (tr("Import Mesh") if tr("Import Mesh") != "Import Mesh" else "Import Mesh", "Lade STL/OBJ Datei", "import_mesh"),
            (tr("Export STL..."), "export_stl"),
            ("Export STEP...", "export_step"),
        ])
        
        self.layout.addStretch()
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    def _add_group(self, title, buttons, grid=False):
        group = QGroupBox(title)
        if grid:
            lay = QGridLayout(group)
            lay.setSpacing(4)
            lay.setContentsMargins(5, 10, 5, 5)
        else:
            lay = QVBoxLayout(group)
            lay.setSpacing(4)
            lay.setContentsMargins(5, 10, 5, 5)
            
        for i, btn_data in enumerate(buttons):
            if len(btn_data) == 3:
                label, tip, action = btn_data
            else:
                label, action = btn_data
                tip = None

            btn = self._create_btn(label, action)
            if tip: 
                btn.setToolTip(tip)

            if grid:
                btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
                btn.setStyleSheet("text-align: center; font-weight: bold;")
                lay.addWidget(btn, i // 2, i % 2)
            else:
                lay.addWidget(btn)
                
        self.layout.addWidget(group)

    def _create_btn(self, text, action_name):
        btn = QToolButton()
        btn.setText(text)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda checked=False, a=action_name: self.action_triggered.emit(a))
        return btn

class BodyPropertiesPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #1e1e1e; color: #ccc;")
        lay = QVBoxLayout(self)
        self.lbl_info = QLabel("Kein Körper ausgewählt")
        self.lbl_info.setWordWrap(True)
        lay.addWidget(self.lbl_info)
        lay.addStretch()
        
    def update_body(self, body):
        if hasattr(body, 'name'):
            info = f"<b>{body.name}</b><br>"
            if hasattr(body, 'id'): info += f"ID: {body.id}<br>"
            
            # Info über Datenstatus
            has_brep = hasattr(body, '_build123d_solid') and body._build123d_solid is not None
            info += f"<br>Typ: {'Parametrisch (BREP)' if has_brep else 'Mesh (Tesselliert)'}"
            
            if hasattr(body, 'features') and body.features:
                info += f"<br>Features: {len(body.features)}"
            self.lbl_info.setText(info)
        
    def clear(self):
        self.lbl_info.setText("Kein Körper ausgewählt")