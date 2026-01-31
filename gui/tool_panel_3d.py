import os
from i18n import tr # Import hinzufügen

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QGroupBox,
                               QGridLayout, QLabel, QScrollArea, QFrame, QSizePolicy, QSlider)
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from gui.widgets.collapsible_section import CollapsibleSection


class ClickableHoverWidget(QFrame):
    """Widget mit Hover-Effekt und Click-Handler."""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hovered = False
        self._update_style()
        self.setCursor(Qt.PointingHandCursor)

    def _update_style(self):
        bg = "#404040" if self._hovered else "transparent"
        self.setStyleSheet(f"QFrame {{ background: {bg}; border-radius: 4px; }}")

    def enterEvent(self, event):
        self._hovered = True
        self._update_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._update_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

class ToolPanel3D(QWidget):
    action_triggered = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(300)  # Breiter für bessere Lesbarkeit
        self.setStyleSheet("""
            QWidget {
                background-color: #262626;
                color: #d4d4d4;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }
            QToolButton {
                background: transparent;
                border: none;
                border-radius: 4px;
                color: #d4d4d4;
                padding: 8px 16px;
                text-align: left;
                font-size: 13px;
            }
            QToolButton:hover {
                background: #404040;
            }
            QToolButton:pressed {
                background: #2563eb;
                color: white;
            }
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
        
        # --- Primitives (nur Grid-Gruppe) ---
        self._add_group("Primitives", [
            (tr("Box"), tr("Create box primitive"), "primitive_box"),
            (tr("Cylinder"), tr("Create cylinder primitive"), "primitive_cylinder"),
            (tr("Sphere"), tr("Create sphere primitive"), "primitive_sphere"),
            (tr("Cone"), tr("Create cone primitive"), "primitive_cone"),
        ],  expanded=False)

        # --- Modeling ---
        self._add_group("Modeling", [
            (tr("New Sketch"), tr("New Sketch"), "new_sketch", "N"),
            (tr("Offset Plane..."), tr("Create offset construction plane"), "offset_plane"),
            (tr("Extrude..."), tr("Extrude"), "extrude", "E"),
            (tr("Revolve..."), tr("Revolve sketch around axis"), "revolve"),
        ], expanded=True)

        # --- Modify ---
        self._add_group(tr("Modify"), [
            (tr("Fillet"), tr("Round edges"), "fillet"),
            (tr("Chamfer"), tr("Bevel edges"), "chamfer"),
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
            (tr("Move"), tr("Move body"), "move_body", "G"),
            (tr("Rotate"), tr("Rotate body"), "rotate_body", "R"),
            (tr("Scale"), tr("Scale body"), "scale_body"),
            (tr("Mirror"), tr("Mirror body"), "mirror_body", "M"),
            (tr("Copy"), tr("Duplicate body"), "copy_body", "D"),
            ("Point Move", "Point-to-Point Move", "point_to_point_move"),
            (tr("Pattern"), tr("Create linear or circular pattern"), "pattern"),
        ])

        # --- Boolean ---
        self._add_group("Boolean", [
            ("Union", tr("Combine bodies"), "boolean_union"),
            ("Cut", tr("Subtract bodies"), "boolean_cut"),
            ("Intersect", tr("Intersection of bodies"), "boolean_intersect"),
        ])

        # --- Inspect ---
        self._add_group("Inspect", [
            ("Section View", tr("Cut through body to see internal structure"), "section_view"),
            ("Check Geometry", tr("Find and fix invalid topology (open shells, bad faces)"), "geometry_check"),
            (tr("Surface Analysis"), tr("Visualize curvature, draft angles for moldability, zebra stripes for continuity"), "surface_analysis"),
            (tr("Mesh Repair"), tr("Fix mesh errors: gaps, self-intersections, degenerate faces"), "mesh_repair"),
            (tr("Wall Thickness"), tr("Check minimum wall thickness for 3D printing strength"), "wall_thickness"),
            ("Measure", tr("Measure distances, angles, areas"), "measure"),
            (tr("BREP Cleanup"), tr("Merge faces after mesh→BREP conversion (holes, fillets, pockets)"), "brep_cleanup"),
        ])

        # --- File ---
        self._add_group(tr("File"), [
            ("Import Mesh", tr("Load STL/OBJ file"), "import_mesh"),
            (tr("Convert Mesh to CAD"), tr("Convert mesh to solid (BREP)"), "convert_to_brep"),
            (tr("Export STL..."), tr("Export as STL"), "export_stl"),
            ("Export STEP...", tr("Export as STEP"), "export_step"),
        ])

        # --- Advanced ---
        self._add_group("Advanced", [
            (tr("PushPull"), tr("Extrude face along its normal"), "pushpull"),
            (tr("Thread..."), tr("Create thread (metric/UNC)"), "thread"),
        ])
        
        self.layout.addStretch()
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    def _add_group(self, title, buttons, icon=None, grid=False, expanded=False):
        section = CollapsibleSection(title, icon=icon, expanded=expanded)

        if grid:
            from PySide6.QtWidgets import QWidget as _QW
            grid_widget = _QW()
            lay = QGridLayout(grid_widget)
            lay.setSpacing(4)
            lay.setContentsMargins(0, 0, 0, 0)
        else:
            lay = None

        for i, btn_data in enumerate(buttons):
            # Support: (label, action), (label, tip, action), (label, tip, action, shortcut)
            shortcut = None
            if len(btn_data) == 4:
                label, tip, action, shortcut = btn_data
            elif len(btn_data) == 3:
                label, tip, action = btn_data
            else:
                label, action = btn_data
                tip = None

            # Grid mode: use QToolButton, sonst custom Widget
            btn = self._create_btn(label, action, shortcut if not grid else None, for_grid=grid)
            if tip:
                btn.setToolTip(tip)

            if grid:
                # Grid buttons styling
                btn.setStyleSheet("""
                    QToolButton {
                        text-align: center;
                        font-weight: 500;
                        background: #404040;
                        border-radius: 4px;
                        padding: 8px;
                    }
                    QToolButton:hover { background: #525252; }
                    QToolButton:pressed { background: #2563eb; color: white; }
                """)
                lay.addWidget(btn, i // 2, i % 2)
            else:
                section.content_layout.addWidget(btn)

        if grid:
            section.content_layout.addWidget(grid_widget)

        self.layout.addWidget(section)

    def _create_btn(self, text, action_name, shortcut=None, for_grid=False):
        """Erstellt Tool-Button mit optionalem Shortcut-Badge."""
        if for_grid:
            # Grid-Buttons: QToolButton mit zentriertem Text
            btn = QToolButton()
            btn.setText(text)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, a=action_name: self.action_triggered.emit(a))
            return btn
        else:
            # Listen-Buttons: Custom Widget mit links ausgerichtetem Text
            container = ClickableHoverWidget()
            h_layout = QHBoxLayout(container)
            h_layout.setContentsMargins(16, 8, 16, 8)
            h_layout.setSpacing(8)

            label = QLabel(text)
            label.setStyleSheet("color: #d4d4d4; font-size: 13px;")
            h_layout.addWidget(label)

            h_layout.addStretch()

            if shortcut:
                kbd = QLabel(shortcut)
                kbd.setStyleSheet("""
                    background: rgba(64, 64, 64, 0.7);
                    color: #a3a3a3;
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-size: 11px;
                    font-family: 'Consolas', monospace;
                """)
                h_layout.addWidget(kbd)

            container.clicked.connect(lambda a=action_name: self.action_triggered.emit(a))
            return container

class BodyPropertiesPanel(QWidget):
    """Panel für Body-Eigenschaften inkl. Transparenz-Slider (Figma-Style)"""
    opacity_changed = Signal(str, float)  # body_id, opacity (0.0-1.0)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #262626; color: #d4d4d4;")
        self._current_body_id = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)

        self.lbl_info = QLabel("Kein Körper ausgewählt")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet("color: #a3a3a3; font-size: 12px;")
        lay.addWidget(self.lbl_info)

        # --- Transparenz-Slider ---
        opacity_frame = QFrame()
        opacity_frame.setStyleSheet("QFrame { background: #404040; border-radius: 6px; }")
        opacity_lay = QVBoxLayout(opacity_frame)
        opacity_lay.setContentsMargins(12, 10, 12, 10)
        opacity_lay.setSpacing(8)

        opacity_header = QHBoxLayout()
        lbl_trans = QLabel(tr("Transparenz:"))
        lbl_trans.setStyleSheet("color: #d4d4d4; font-size: 12px;")
        opacity_header.addWidget(lbl_trans)
        self.lbl_opacity_value = QLabel("100%")
        self.lbl_opacity_value.setStyleSheet("color: #2563eb; font-weight: bold; font-size: 12px;")
        opacity_header.addStretch()
        opacity_header.addWidget(self.lbl_opacity_value)
        opacity_lay.addLayout(opacity_header)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)  # 0% - 100%
        self.opacity_slider.setValue(100)
        self.opacity_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: none;
                height: 6px;
                background: #525252;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #2563eb;
                border: none;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #3b82f6;
            }
            QSlider::sub-page:horizontal {
                background: #2563eb;
                border-radius: 3px;
            }
        """)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_lay.addWidget(self.opacity_slider)

        lay.addWidget(opacity_frame)
        self.opacity_frame = opacity_frame
        self.opacity_frame.setVisible(False)  # Versteckt wenn kein Body

        # --- Transform Section (Figma-Style) ---
        self.transform_frame = QFrame()
        self.transform_frame.setStyleSheet("QFrame { background: #404040; border-radius: 6px; }")
        transform_lay = QVBoxLayout(self.transform_frame)
        transform_lay.setContentsMargins(12, 10, 12, 10)
        transform_lay.setSpacing(10)

        # Section Header
        transform_header = QLabel("TRANSFORM")
        transform_header.setStyleSheet("""
            color: #a3a3a3;
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.5px;
        """)
        transform_lay.addWidget(transform_header)

        # Position
        self._add_xyz_row(transform_lay, "Position", "pos")

        # Rotation
        self._add_xyz_row(transform_lay, "Rotation", "rot")

        # Scale
        self._add_xyz_row(transform_lay, "Scale", "scale", default_val=1.0)

        lay.addWidget(self.transform_frame)
        self.transform_frame.setVisible(False)

        lay.addStretch()

    def _add_xyz_row(self, parent_layout, label_text, prefix, default_val=0.0):
        """Erstellt eine X/Y/Z Eingabezeile im Figma-Style."""
        from PySide6.QtWidgets import QDoubleSpinBox

        row_widget = QWidget()
        row_layout = QVBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        # Label
        label = QLabel(label_text)
        label.setStyleSheet("color: #d4d4d4; font-size: 11px;")
        row_layout.addWidget(label)

        # X/Y/Z Grid
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(6)

        spinbox_style = """
            QDoubleSpinBox {
                background: #525252;
                border: 1px solid #525252;
                border-radius: 4px;
                padding: 4px 6px;
                color: white;
                font-size: 11px;
            }
            QDoubleSpinBox:focus {
                border-color: #2563eb;
            }
        """

        for i, axis in enumerate(['X', 'Y', 'Z']):
            axis_label = QLabel(axis)
            axis_label.setStyleSheet("color: #737373; font-size: 10px;")
            axis_label.setFixedWidth(12)
            grid_layout.addWidget(axis_label, 0, i * 2)

            spinbox = QDoubleSpinBox()
            spinbox.setRange(-10000, 10000)
            spinbox.setDecimals(2)
            spinbox.setValue(default_val)
            spinbox.setStyleSheet(spinbox_style)
            spinbox.setButtonSymbols(QDoubleSpinBox.NoButtons)
            grid_layout.addWidget(spinbox, 0, i * 2 + 1)

            # Store reference
            setattr(self, f"{prefix}_{axis.lower()}", spinbox)

        row_layout.addWidget(grid_widget)
        parent_layout.addWidget(row_widget)

    def _on_opacity_changed(self, value):
        """Slider geändert"""
        self.lbl_opacity_value.setText(f"{value}%")
        if self._current_body_id:
            opacity = value / 100.0  # 0-100 → 0.0-1.0
            self.opacity_changed.emit(self._current_body_id, opacity)

    def update_body(self, body):
        if hasattr(body, 'name'):
            self._current_body_id = body.id if hasattr(body, 'id') else None

            info = f"<b>{body.name}</b><br>"
            if hasattr(body, 'id'): info += f"ID: {body.id}<br>"

            # Info über Datenstatus
            has_brep = hasattr(body, '_build123d_solid') and body._build123d_solid is not None
            info += f"<br>Typ: {'Parametrisch (BREP)' if has_brep else 'Mesh (Tesselliert)'}"

            if hasattr(body, 'features') and body.features:
                info += f"<br>Features: {len(body.features)}"
            self.lbl_info.setText(info)

            # Opacity-Slider zeigen und Wert setzen
            self.opacity_frame.setVisible(True)
            self.transform_frame.setVisible(True)

            # Lese aktuelle Opacity vom Body (falls gespeichert)
            current_opacity = getattr(body, 'display_opacity', 1.0)
            self.opacity_slider.blockSignals(True)
            self.opacity_slider.setValue(int(current_opacity * 100))
            self.lbl_opacity_value.setText(f"{int(current_opacity * 100)}%")
            self.opacity_slider.blockSignals(False)

    def clear(self):
        self.lbl_info.setText("Kein Körper ausgewählt")
        self._current_body_id = None
        self.opacity_frame.setVisible(False)
        self.transform_frame.setVisible(False)