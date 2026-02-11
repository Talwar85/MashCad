import os
from i18n import tr # Import hinzufügen

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QGroupBox,
                               QGridLayout, QLabel, QScrollArea, QFrame, QSizePolicy, QSlider)
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from gui.widgets.collapsible_section import CollapsibleSection
from gui.design_tokens import DesignTokens


class ClickableHoverWidget(QFrame):
    """Widget mit Hover-Effekt und Click-Handler."""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hovered = False
        self._update_style()
        self.setCursor(Qt.PointingHandCursor)

    def _update_style(self):
        bg = DesignTokens.COLOR_BG_ELEVATED.name() if self._hovered else "transparent"
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

    _SYNONYMS = {
        "round": "fillet", "abrunden": "fillet", "radius": "fillet",
        "bevel": "chamfer", "fase": "chamfer",
        "hollow": "shell", "aushöhlen": "shell",
        "taper": "draft", "schräge": "draft",
        "duplicate": "copy", "duplizieren": "copy", "kopieren": "copy",
        "schneiden": "cut", "subtract": "cut",
        "vereinen": "union", "combine": "union",
        "messen": "measure", "distance": "measure", "abstand": "measure",
        "drehen": "revolve", "rotate": "revolve",
        "importieren": "import", "laden": "import",
        "exportieren": "export", "speichern": "export",
        "drucken": "export stl", "printing": "export stl",
        "gewinde": "thread", "screw": "thread",
        "bohrung": "hole", "bohren": "hole",
        "spiegel": "mirror", "spiegeln": "mirror",
        "muster": "pattern",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(180)
        bg = DesignTokens.COLOR_BG_PANEL.name()
        elevated = DesignTokens.COLOR_BG_ELEVATED.name()
        txt = DesignTokens.COLOR_TEXT_PRIMARY.name()
        p = DesignTokens.COLOR_PRIMARY.name()
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                color: {txt};
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }}
            QToolButton {{
                background: transparent;
                border: none;
                border-radius: 4px;
                color: {txt};
                padding: 8px 16px;
                text-align: left;
                font-size: 13px;
            }}
            QToolButton:hover {{
                background: {elevated};
            }}
            QToolButton:pressed {{
                background: {p};
                color: white;
            }}
        """)
        self._all_sections = []
        self._all_tool_widgets = []
        self._beginner_mode = False
        self._advanced_section_titles = {"Advanced", "Inspect"}
        self._setup_ui()
        
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Filter + Beginner (like ToolPanel finish button style) ---
        from PySide6.QtWidgets import QLineEdit
        top_container = QWidget()
        top_container.setStyleSheet(f"background: {DesignTokens.COLOR_BG_PANEL.name()};")
        top_lay = QVBoxLayout(top_container)
        top_lay.setContentsMargins(8, 6, 8, 6)
        top_lay.setSpacing(4)

        self._search_field = QLineEdit()
        self._search_field.setFocusPolicy(Qt.ClickFocus)
        self._search_field.setPlaceholderText(tr("Filter..."))
        self._search_field.setClearButtonEnabled(True)
        self._search_field.setStyleSheet(f"""
            QLineEdit {{
                background: {DesignTokens.COLOR_BG_INPUT.name()};
                color: {DesignTokens.COLOR_TEXT_PRIMARY.name()};
                border: 1px solid {DesignTokens.COLOR_BORDER.name()};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.COLOR_PRIMARY.name()};
            }}
        """)
        self._search_field.textChanged.connect(self._on_search_changed)
        top_lay.addWidget(self._search_field)

        self._btn_beginner = QToolButton()
        self._btn_beginner.setText(tr("☆ Beginner"))
        self._btn_beginner.setCheckable(True)
        self._btn_beginner.setChecked(False)
        self._btn_beginner.setCursor(Qt.PointingHandCursor)
        self._btn_beginner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_beginner.setStyleSheet(f"""
            QToolButton {{
                background: {DesignTokens.COLOR_BG_ELEVATED.name()};
                border: 1px solid {DesignTokens.COLOR_BORDER.name()};
                border-radius: 4px;
                color: {DesignTokens.COLOR_TEXT_MUTED.name()};
                padding: 4px 8px;
                font-size: 11px;
            }}
            QToolButton:checked {{
                background: {DesignTokens.COLOR_PRIMARY.name()};
                color: white;
                border-color: {DesignTokens.COLOR_PRIMARY.name()};
            }}
            QToolButton:hover:!checked {{
                background: #525252;
            }}
        """)
        self._btn_beginner.clicked.connect(lambda checked: self._set_mode(checked))
        top_lay.addWidget(self._btn_beginner)

        main_layout.addWidget(top_container)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")

        self.layout = QVBoxLayout(content_widget)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(10)

        # --- Primitives ---
        self._add_group("Primitives", [
            (tr("Box"), tr("Create a parametric box\nDefine dimensions in dialog\nConfirm: OK"), "primitive_box"),
            (tr("Cylinder"), tr("Create a parametric cylinder\nDefine radius and height\nConfirm: OK"), "primitive_cylinder"),
            (tr("Sphere"), tr("Create a parametric sphere\nDefine radius\nConfirm: OK"), "primitive_sphere"),
            (tr("Cone"), tr("Create a parametric cone\nDefine radii and height\nConfirm: OK"), "primitive_cone"),
        ],  expanded=False)

        # --- Modeling ---
        self._add_group("Modeling", [
            (tr("New Sketch"), tr("Start a new 2D sketch\nSelect a plane or face\nDraw profiles, then extrude to 3D"), "new_sketch", "N"),
            (tr("Offset Plane..."), tr("Create an offset construction plane\nSelect reference plane, set distance\nConfirm: OK"), "offset_plane"),
            (tr("Extrude..."), tr("Extrude a closed sketch profile to 3D\nSelect: closed profile\nConfirm: Enter or Finish button"), "extrude", "E"),
            (tr("Revolve..."), tr("Revolve profile around an axis\nSelect: profile + axis edge\nConfirm: Finish button"), "revolve"),
            (tr("Sweep"), tr("Sweep a profile along a path\nSelect: profile face + path edge\nConfirm: Finish button"), "sweep"),
            (tr("Loft"), tr("Create shape between multiple profiles\nSelect: 2+ profile faces\nConfirm: Finish button"), "loft"),
        ], expanded=True, highlight_first=True)

        # --- Modify ---
        self._add_group(tr("Modify"), [
            (tr("Fillet"), tr("Round edges with a radius\nSelect: one or more edges\nConfirm: Enter or Finish · Esc: cancel"), "fillet"),
            (tr("Chamfer"), tr("Bevel edges at a distance\nSelect: one or more edges\nConfirm: Enter or Finish · Esc: cancel"), "chamfer"),
            (tr("Hole..."), tr("Create hole in a face\nSelect: planar face, set diameter/depth\nConfirm: OK"), "hole"),
            (tr("Draft..."), tr("Add draft/taper angle to faces\nSelect: faces to draft\nConfirm: OK"), "draft"),
            (tr("Split Body..."), tr("Split a body along a plane\nSelect: body, choose plane\nConfirm: OK"), "split_body"),
            (tr("Shell"), tr("Hollow out a solid body\nSelect: face to open, set wall thickness\nConfirm: Finish"), "shell"),
            (tr("Surface Texture"), tr("Apply texture to faces for 3D printing\nSelect: body, choose texture type\nConfirm: Apply"), "surface_texture"),
            (tr("N-Sided Patch"), tr("Fill boundary with smooth surface\nSelect: boundary edges\nConfirm: OK"), "nsided_patch"),
            (tr("Lattice"), tr("Generate lattice structure\nSelect: body to lattice\nConfirm: OK"), "lattice"),
            (tr("Mirror"), tr("Mirror a body across a plane\nSelect: body (auto-mirrors)\nShortcut: M"), "mirror_body", "M"),
            (tr("Copy"), tr("Duplicate the selected body\nSelect: body to copy\nShortcut: D"), "copy_body", "D"),
            (tr("Pattern"), tr("Create linear or circular pattern\nSelect: body, set count/spacing\nConfirm: Finish"), "pattern"),
        ])

        # --- Boolean ---
        self._add_group("Boolean", [
            (tr("Union"), tr("Combine two bodies into one\nSelect: two bodies in dialog\nConfirm: OK"), "boolean_union"),
            (tr("Cut"), tr("Subtract one body from another\nSelect: target + tool body\nConfirm: OK"), "boolean_cut"),
            (tr("Intersect"), tr("Keep only overlapping volume\nSelect: two bodies\nConfirm: OK"), "boolean_intersect"),
        ])

        # --- Inspect ---
        self._add_group("Inspect", [
            (tr("Section View"), tr("Cut through body to inspect inside\nAdjust position with slider\nToggle: click again to close"), "section_view"),
            (tr("Check Geometry"), tr("Find invalid topology\nSelect: body to check\nShows: errors + repair options"), "geometry_check"),
            (tr("Surface Analysis"), tr("Visualize curvature and draft angles\nSelect: body to analyze\nModes: curvature, zebra, draft"), "surface_analysis"),
            (tr("Mesh Repair"), tr("Fix mesh errors and gaps\nSelect: mesh body\nAuto-repair + manual tools"), "mesh_repair"),
            (tr("Wall Thickness"), tr("Check wall thickness for 3D printing\nSelect: body\nShows: thin areas in red"), "wall_thickness"),
            (tr("Measure"), tr("Measure distances, angles, areas\nClick: two points or edges\nResult shown in panel"), "measure"),
            (tr("BREP Cleanup"), tr("Cleanup after mesh→BREP conversion\nMerge co-planar faces\nImproves fillet/chamfer quality"), "brep_cleanup"),
        ])

        # --- File ---
        self._add_group(tr("File"), [
            (tr("Import Mesh"), tr("Load STL, OBJ, PLY file\nSelect file in dialog\nMesh appears in viewport"), "import_mesh"),
            (tr("Convert Mesh to CAD"), tr("Convert mesh to parametric solid\nSelect: mesh body\nEnables CAD operations on imported meshes"), "convert_to_brep"),
            (tr("Export STL..."), tr("Export body as STL for 3D printing\nSelect: body or export all\nChoose resolution in dialog"), "export_stl"),
            (tr("Export STEP..."), tr("Export as STEP for CAD exchange\nIndustry-standard format\nPreserves parametric data"), "export_step"),
        ])

        # --- Advanced ---
        self._add_group("Advanced", [
            (tr("Sketch Agent"), tr("Generate parts with AI\nChoose complexity and seed\nGenerates parametric CAD parts"), "sketch_agent"),
            (tr("Thread..."), tr("Create thread on cylindrical face\nSelect: cylindrical face\nSet: metric/UNC, pitch, depth"), "thread"),
        ])
        
        self.layout.addStretch()
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    def _add_quick_actions(self):
        """Non-collapsible Quick Actions section for common tasks."""
        qa_frame = QWidget()
        qa_frame.setObjectName("quickActions")
        qa_frame.setStyleSheet("background: transparent;")
        qa_lay = QVBoxLayout(qa_frame)
        qa_lay.setContentsMargins(8, 2, 8, 8)
        qa_lay.setSpacing(4)

        header = QLabel(tr("Quick Actions"))
        header.setStyleSheet(f"""
            color: {DesignTokens.COLOR_TEXT_MUTED.name()};
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.5px;
            padding: 4px 8px;
        """)
        qa_lay.addWidget(header)

        grid_widget = QWidget()
        grid_lay = QGridLayout(grid_widget)
        grid_lay.setSpacing(4)
        grid_lay.setContentsMargins(0, 0, 0, 0)

        qa_items = [
            (tr("New Sketch"), "new_sketch"),
            (tr("Extrude"), "extrude"),
            (tr("Fillet"), "fillet"),
            (tr("Measure"), "measure"),
            (tr("Export STL"), "export_stl"),
            (tr("Import Mesh"), "import_mesh"),
        ]

        p = DesignTokens.COLOR_PRIMARY.name()
        for i, (label, action) in enumerate(qa_items):
            btn = QToolButton()
            btn.setText(label)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QToolButton {{
                    text-align: center;
                    font-weight: 500;
                    font-size: 12px;
                    background: rgba(37, 99, 235, 0.08);
                    border: 1px solid rgba(37, 99, 235, 0.15);
                    border-radius: 4px;
                    padding: 7px 4px;
                    color: #d4d4d4;
                }}
                QToolButton:hover {{
                    background: rgba(37, 99, 235, 0.18);
                    border-color: {p};
                    color: white;
                }}
                QToolButton:pressed {{
                    background: {p};
                    color: white;
                }}
            """)
            btn.clicked.connect(lambda checked=False, a=action: self.action_triggered.emit(a))
            grid_lay.addWidget(btn, i // 2, i % 2)

        qa_lay.addWidget(grid_widget)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {DesignTokens.COLOR_BORDER.name()};")
        qa_lay.addWidget(sep)

        self.layout.addWidget(qa_frame)
        self._quick_actions_frame = qa_frame

    def _on_search_changed(self, text: str):
        """Filter tools across all sections by search text."""
        query = text.strip().lower()

        resolved = self._SYNONYMS.get(query, "") if query else ""

        for section, tool_widgets in zip(self._all_sections, self._all_tool_widgets):
            visible_count = 0
            for widget, search_text in tool_widgets:
                if not query:
                    widget.setVisible(True)
                    visible_count += 1
                else:
                    match = (query in search_text) or (resolved != "" and resolved in search_text)
                    widget.setVisible(bool(match))
                    if match:
                        visible_count += 1

            if query:
                section.setVisible(visible_count > 0)
                if visible_count > 0:
                    section.set_expanded(True)
            else:
                section.setVisible(True)
                self._apply_mode_filter()

    def _set_mode(self, beginner: bool):
        """Switch between Beginner and All mode."""
        self._beginner_mode = beginner
        self._btn_beginner.setChecked(beginner)
        self._apply_mode_filter()

    def _apply_mode_filter(self):
        """Show/hide sections based on beginner mode."""
        if not self._search_field.text().strip():
            for section in self._all_sections:
                if self._beginner_mode and section._title in self._advanced_section_titles:
                    section.setVisible(False)
                else:
                    section.setVisible(True)

    def _add_group(self, title, buttons, icon=None, grid=False, expanded=False, highlight_first=False):
        section = CollapsibleSection(title, icon=icon, expanded=expanded)

        if grid:
            from PySide6.QtWidgets import QWidget as _QW
            grid_widget = _QW()
            lay = QGridLayout(grid_widget)
            lay.setSpacing(4)
            lay.setContentsMargins(0, 0, 0, 0)
        else:
            lay = None

        section_tools = []

        for i, btn_data in enumerate(buttons):
            shortcut = None
            if len(btn_data) == 4:
                label, tip, action, shortcut = btn_data
            elif len(btn_data) == 3:
                label, tip, action = btn_data
            else:
                label, action = btn_data
                tip = None

            is_highlighted = highlight_first and i == 0
            btn = self._create_btn(label, action, shortcut if not grid else None, for_grid=grid, highlight=is_highlighted)
            if tip:
                btn.setToolTip(tip)

            search_text = f"{label} {action} {tip or ''}".lower()
            section_tools.append((btn, search_text))

            if grid:
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

        self._all_sections.append(section)
        self._all_tool_widgets.append(section_tools)
        self.layout.addWidget(section)

    def _create_btn(self, text, action_name, shortcut=None, for_grid=False, highlight=False):
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
            if highlight:
                label.setStyleSheet("color: #60a5fa; font-size: 13px; font-weight: 600;")
                container.setStyleSheet(f"""
                    QFrame {{
                        background: #2563eb18;
                        border-left: 2px solid #2563eb;
                        border-radius: 4px;
                    }}
                    QFrame:hover {{
                        background: {DesignTokens.COLOR_BG_ELEVATED.name()};
                    }}
                """)
            else:
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