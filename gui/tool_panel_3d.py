import os
from i18n import tr # Import hinzufügen

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QToolButton, QGroupBox,
                               QGridLayout, QLabel, QScrollArea, QFrame, QSizePolicy)
from PySide6.QtCore import QSize, Qt, Signal
from gui.widgets.collapsible_section import CollapsibleSection

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
        
        # --- Primitives ---
        self._add_group("Primitives", [
            (tr("Box"), tr("Create box primitive"), "primitive_box"),
            (tr("Cylinder"), tr("Create cylinder primitive"), "primitive_cylinder"),
            (tr("Sphere"), tr("Create sphere primitive"), "primitive_sphere"),
            (tr("Cone"), tr("Create cone primitive"), "primitive_cone"),
        ], grid=True, expanded=True)

        # --- Sketch & Base ---
        self._add_group("Sketch & Base", [
            (tr("New Sketch"), tr("New Sketch (S)"), "new_sketch"),
            (tr("Offset Plane..."), tr("Create offset construction plane"), "offset_plane"),
            (tr("Extrude..."), tr("Extrude (E)"), "extrude"),
            (tr("Revolve..."), tr("Revolve sketch around axis"), "revolve"),
        ], expanded=True)

        # --- Modify ---
        self._add_group(tr("Modify"), [
            (tr("Fillet"), "fillet"),
            (tr("Chamfer"), "chamfer"),
            (tr("Hole..."), tr("Create hole (simple/counterbore/countersink)"), "hole"),
            (tr("Draft..."), tr("Add draft/taper angle to faces"), "draft"),
            (tr("Split Body..."), tr("Split body along a plane"), "split_body"),         
            (tr("Shell"), tr("Hollow out solid"), "shell"),
            (tr("Sweep"), tr("Sweep profile along path"), "sweep"),
            (tr("Loft"), tr("Loft between profiles"), "loft"),
            (tr("Surface Texture"), tr("Apply texture to faces (3D print)"), "surface_texture"),
            (tr("N-Sided Patch"), tr("Fill N-sided boundary with smooth surface"), "nsided_patch"),
            (tr("Lattice"), tr("Generate lattice structure for lightweight parts"), "lattice"),           
        ])

        # --- Transform ---
        self._add_group("Transform", [
            (tr("Move"), tr("Move"), "move_body"),
            (tr("Rotate"), tr("Rotate"), "rotate_body"),
            (tr("Scale"), tr("Scale"), "scale_body"),
            (tr("Mirror"), tr("Mirror"), "mirror_body"),
            (tr("Copy"), tr("Copy"), "copy_body"),
            ("Point Move", "Point-to-Point Move (wie Fusion 360)", "point_to_point_move"),
        ], grid=True)

        # --- Boolean ---
        self._add_group("Boolean", [
            (tr("Union") if tr("Union") != "Union" else "Union", "boolean_union"),
            (tr("Cut") if tr("Cut") != "Cut" else "Cut", "boolean_cut"),
            (tr("Intersect") if tr("Intersect") != "Intersect" else "Intersect", "boolean_intersect"),
        ])

      
        # --- Inspect ---
        self._add_group("Inspect", [
            ("Section View", "Schnittansicht", "section_view"),
            ("Check Geometry", "Validate and heal geometry", "geometry_check"),
            (tr("Surface Analysis"), tr("Curvature, draft angle, zebra stripes"), "surface_analysis"),
            (tr("Mesh Repair"), tr("Diagnose and repair geometry"), "mesh_repair"),
            (tr("Wall Thickness"), tr("Analyze wall thickness for 3D printing"), "wall_thickness"),
            (tr("Measure") if tr("Measure") != "Measure" else "Measure", "measure"),
        ])

        # --- Import/Export ---
        self._add_group(tr("File"), [
            (tr("Import Mesh") if tr("Import Mesh") != "Import Mesh" else "Import Mesh", "Lade STL/OBJ Datei", "import_mesh"),
            (tr("Convert Mesh to CAD"), "Konvertiert Mesh zu Solid (BREP)", "convert_to_brep"),
            (tr("Export STL..."), "export_stl"),
            ("Export STEP...", "export_step"),

        ])

        # --- Advanced (Phase 6) ---
        self._add_group(tr("Geht nicht"), [
            (tr("PushPull"), tr("Extrude face along its normal"), "pushpull"),
            (tr("Thread..."), tr("Create thread (metric/UNC)"), "thread"),
        ])
        
        self.layout.addStretch()
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    def _add_group(self, title, buttons, grid=False, expanded=False):
        section = CollapsibleSection(title, expanded=expanded)

        if grid:
            from PySide6.QtWidgets import QWidget as _QW
            grid_widget = _QW()
            lay = QGridLayout(grid_widget)
            lay.setSpacing(4)
            lay.setContentsMargins(0, 0, 0, 0)
        else:
            lay = None

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
                section.content_layout.addWidget(btn)

        if grid:
            section.content_layout.addWidget(grid_widget)

        self.layout.addWidget(section)

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