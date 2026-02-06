"""
Surface Texture Panel - UI für Flächen-Texturierung.

Ermöglicht:
- Auswahl des Textur-Typs
- Einstellung der Parameter (Scale, Depth, Rotation)
- Live-Preview aktivieren/deaktivieren
- Anwenden oder Abbrechen
"""

from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QDoubleSpinBox, QCheckBox, QPushButton,
    QGroupBox, QSlider, QFileDialog, QStackedWidget
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont

from loguru import logger

try:
    from i18n import tr
except ImportError:
    def tr(s): return s


class SurfaceTexturePanel(QFrame):
    """
    Input-Panel für Surface Texture Feature.

    Folgt dem UX-Pattern von ShellInputPanel/SweepInputPanel.
    Zeigt Textur-Typ, Parameter und Preview-Option.
    """

    # Signals
    texture_applied = Signal(dict)      # Emittiert Textur-Konfiguration
    preview_requested = Signal(dict)    # Für Live-Preview
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._face_count = 0

        self.setMinimumWidth(520)
        self.setMinimumHeight(480)

        self._setup_style()
        self._setup_ui()
        
        # Sicherstellen, dass das richtige Typ-Panel angezeigt wird
        self._on_type_changed(self.type_combo.currentText())

        # WICHTIG: Panel beim Start verstecken
        self.hide()

    def _setup_style(self):
        """Konsistenter Style via DesignTokens — Single Source of Truth."""
        from gui.design_tokens import DesignTokens
        self.setStyleSheet(DesignTokens.stylesheet_panel())

    def _setup_ui(self):
        """Erstellt die UI-Elemente."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        # Header
        header = QLabel(tr("Surface Texture"))
        header.setStyleSheet("font-size: 14px; font-weight: bold; color: #0078d4;")
        main_layout.addWidget(header)

        # Face Count Info
        self.face_info = QLabel(tr("0 Faces selected"))
        self.face_info.setStyleSheet("color: #888; font-size: 11px;")
        main_layout.addWidget(self.face_info)

        # === Textur-Typ ===
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel(tr("Type:")))

        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "Ripple",      # Wellen/Rillen
            "Honeycomb",   # Waben
            "Diamond",     # Rauten
            "Knurl",       # Rändel
            "Crosshatch",  # Kreuzschraffur
            "Voronoi",     # Organisch
            "Custom",      # Benutzerdefiniert
        ])
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        type_layout.addWidget(self.type_combo)
        type_layout.addStretch()
        main_layout.addLayout(type_layout)

        # === Common Parameters ===
        params_group = QGroupBox(tr("Parameters"))
        params_layout = QFormLayout(params_group)
        params_layout.setSpacing(8)
        params_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Scale
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.1, 20.0)
        self.scale_spin.setValue(2.0)
        self.scale_spin.setSuffix(" mm")
        self.scale_spin.setDecimals(1)
        self.scale_spin.setMinimumWidth(120)
        self.scale_spin.valueChanged.connect(self._emit_preview)
        params_layout.addRow(tr("Scale:"), self.scale_spin)

        # Depth (default 1mm für bessere Sichtbarkeit in Preview)
        self.depth_spin = QDoubleSpinBox()
        self.depth_spin.setRange(0.05, 5.0)
        self.depth_spin.setValue(1.0)
        self.depth_spin.setSuffix(" mm")
        self.depth_spin.setDecimals(2)
        self.depth_spin.setMinimumWidth(120)
        self.depth_spin.valueChanged.connect(self._emit_preview)
        params_layout.addRow(tr("Depth:"), self.depth_spin)

        # Rotation
        self.rotation_spin = QDoubleSpinBox()
        self.rotation_spin.setRange(0, 360)
        self.rotation_spin.setValue(0)
        self.rotation_spin.setSuffix(" deg")
        self.rotation_spin.setDecimals(0)
        self.rotation_spin.setMinimumWidth(120)
        self.rotation_spin.valueChanged.connect(self._emit_preview)
        params_layout.addRow(tr("Rotation:"), self.rotation_spin)

        # Invert
        self.invert_check = QCheckBox(tr("Invert"))
        self.invert_check.stateChanged.connect(self._emit_preview)
        params_layout.addRow("", self.invert_check)

        # Solid Base (3D-Druck Sicherheit)
        self.solid_base_check = QCheckBox(tr("Solid Base (No Holes)"))
        self.solid_base_check.setChecked(True)
        self.solid_base_check.setToolTip(tr("Ensures texture only adds material (no holes). Required for top surfaces in 3D printing."))
        self.solid_base_check.stateChanged.connect(self._emit_preview)
        params_layout.addRow("", self.solid_base_check)

        main_layout.addWidget(params_group)

        # === Type-Specific Parameters (Stacked Widget) ===
        self.type_params_stack = QStackedWidget()
        self.type_params_stack.setMinimumHeight(180)  # Mindesthöhe für Type-Parameter
        self._setup_type_params()
        main_layout.addWidget(self.type_params_stack)
        main_layout.addStretch()  # Stretch damit Buttons unten bleiben

        # === Preview Checkbox (TODO: Nicht implementiert - ausgeblendet) ===
        self.preview_check = QCheckBox(tr("Live Preview"))
        self.preview_check.setChecked(False)
        self.preview_check.stateChanged.connect(self._emit_preview)
        # main_layout.addWidget(self.preview_check)  # Ausgeblendet bis implementiert

        # === Buttons ===
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton(tr("Cancel"))
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)

        self.apply_btn = QPushButton(tr("Apply"))
        self.apply_btn.setObjectName("applyBtn")
        self.apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(self.apply_btn)

        main_layout.addLayout(btn_layout)

    def _setup_type_params(self):
        """Erstellt typ-spezifische Parameter-Widgets."""
        # Ripple
        ripple_widget = QWidget()
        ripple_layout = QFormLayout(ripple_widget)
        ripple_layout.setSpacing(6)
        
        self.ripple_wave_count = QDoubleSpinBox()
        self.ripple_wave_count.setRange(1, 20)
        self.ripple_wave_count.setValue(5)
        self.ripple_wave_count.setDecimals(0)
        self.ripple_wave_count.setMinimumWidth(140)
        self.ripple_wave_count.valueChanged.connect(self._emit_preview)
        ripple_layout.addRow(tr("Wave Count:"), self.ripple_wave_count)

        self.ripple_wave_shape = QComboBox()
        self.ripple_wave_shape.addItems(["sine", "triangle", "square"])
        self.ripple_wave_shape.setMinimumWidth(140)
        self.ripple_wave_shape.currentTextChanged.connect(self._emit_preview)
        ripple_layout.addRow(tr("Wave Shape:"), self.ripple_wave_shape)

        self.ripple_print_safe = QCheckBox(tr("3D Print Safe"))
        self.ripple_print_safe.setChecked(True)
        self.ripple_print_safe.setToolTip(tr("Optimiert Profil für 3D-Druck (keine Überhänge >45°, Sockel)"))
        self.ripple_print_safe.stateChanged.connect(self._emit_preview)
        ripple_layout.addRow("", self.ripple_print_safe)

        # Wellenbreite (Pitch) für konsistente Ripples unabhängig von Flächengröße
        self.ripple_wave_width = QDoubleSpinBox()
        self.ripple_wave_width.setRange(0.0, 10.0)  # 0.0 erlaubt für "auto"
        self.ripple_wave_width.setValue(0.0)  # 0 = automatisch (wave_count verwenden)
        self.ripple_wave_width.setSuffix(" mm")
        self.ripple_wave_width.setDecimals(2)
        self.ripple_wave_width.setMinimumWidth(140)
        self.ripple_wave_width.setToolTip(tr("Width of each ripple wave. 0 = auto (uses wave count)."))
        self.ripple_wave_width.valueChanged.connect(self._emit_preview)
        ripple_layout.addRow(tr("Wave Width:"), self.ripple_wave_width)
        
        # Mindestgröße für Ripple-Widget setzen
        ripple_widget.setMinimumHeight(200)

        self.type_params_stack.addWidget(ripple_widget)

        # Honeycomb
        honeycomb_widget = QWidget()
        honeycomb_layout = QFormLayout(honeycomb_widget)
        self.honeycomb_cell_size = QDoubleSpinBox()
        self.honeycomb_cell_size.setRange(0.5, 10.0)
        self.honeycomb_cell_size.setValue(3.0)
        self.honeycomb_cell_size.setSuffix(" mm")
        self.honeycomb_cell_size.valueChanged.connect(self._emit_preview)
        honeycomb_layout.addRow(tr("Cell Size:"), self.honeycomb_cell_size)
        honeycomb_widget.setMinimumHeight(100)
        self.type_params_stack.addWidget(honeycomb_widget)

        # Diamond
        diamond_widget = QWidget()
        diamond_layout = QFormLayout(diamond_widget)
        self.diamond_aspect = QDoubleSpinBox()
        self.diamond_aspect.setRange(0.5, 2.0)
        self.diamond_aspect.setValue(1.0)
        self.diamond_aspect.valueChanged.connect(self._emit_preview)
        diamond_layout.addRow(tr("Aspect Ratio:"), self.diamond_aspect)
        diamond_widget.setMinimumHeight(100)
        self.type_params_stack.addWidget(diamond_widget)

        # Knurl
        knurl_widget = QWidget()
        knurl_layout = QFormLayout(knurl_widget)
        self.knurl_pitch = QDoubleSpinBox()
        self.knurl_pitch.setRange(0.5, 5.0)
        self.knurl_pitch.setValue(1.0)
        self.knurl_pitch.setSuffix(" mm")
        self.knurl_pitch.valueChanged.connect(self._emit_preview)
        knurl_layout.addRow(tr("Pitch:"), self.knurl_pitch)
        self.knurl_angle = QDoubleSpinBox()
        self.knurl_angle.setRange(15, 60)
        self.knurl_angle.setValue(30)
        self.knurl_angle.setSuffix(" deg")
        self.knurl_angle.valueChanged.connect(self._emit_preview)
        knurl_layout.addRow(tr("Angle:"), self.knurl_angle)
        knurl_widget.setMinimumHeight(140)
        self.type_params_stack.addWidget(knurl_widget)

        # Crosshatch
        crosshatch_widget = QWidget()
        crosshatch_layout = QFormLayout(crosshatch_widget)
        self.crosshatch_spacing = QDoubleSpinBox()
        self.crosshatch_spacing.setRange(0.5, 5.0)
        self.crosshatch_spacing.setValue(1.0)
        self.crosshatch_spacing.setSuffix(" mm")
        self.crosshatch_spacing.valueChanged.connect(self._emit_preview)
        crosshatch_layout.addRow(tr("Line Spacing:"), self.crosshatch_spacing)
        crosshatch_widget.setMinimumHeight(100)
        self.type_params_stack.addWidget(crosshatch_widget)

        # Voronoi
        voronoi_widget = QWidget()
        voronoi_layout = QFormLayout(voronoi_widget)
        self.voronoi_cells = QDoubleSpinBox()
        self.voronoi_cells.setRange(5, 100)
        self.voronoi_cells.setValue(20)
        self.voronoi_cells.setDecimals(0)
        self.voronoi_cells.valueChanged.connect(self._emit_preview)
        voronoi_layout.addRow(tr("Cell Count:"), self.voronoi_cells)
        self.voronoi_randomness = QDoubleSpinBox()
        self.voronoi_randomness.setRange(0, 1)
        self.voronoi_randomness.setValue(0.5)
        self.voronoi_randomness.setDecimals(2)
        self.voronoi_randomness.valueChanged.connect(self._emit_preview)
        voronoi_layout.addRow(tr("Randomness:"), self.voronoi_randomness)
        voronoi_widget.setMinimumHeight(140)
        self.type_params_stack.addWidget(voronoi_widget)

        # Custom (Heightmap)
        custom_widget = QWidget()
        custom_layout = QFormLayout(custom_widget)
        self.custom_path_label = QLabel(tr("No file selected"))
        self.custom_path_label.setStyleSheet("color: #888;")
        custom_layout.addRow(tr("Heightmap:"), self.custom_path_label)
        self.custom_browse_btn = QPushButton(tr("Browse..."))
        self.custom_browse_btn.clicked.connect(self._browse_heightmap)
        custom_layout.addRow("", self.custom_browse_btn)
        self._custom_path = ""
        custom_widget.setMinimumHeight(120)
        self.type_params_stack.addWidget(custom_widget)

    def _on_type_changed(self, text: str):
        """Wechselt die typ-spezifischen Parameter."""
        type_index = {
            "Ripple": 0,
            "Honeycomb": 1,
            "Diamond": 2,
            "Knurl": 3,
            "Crosshatch": 4,
            "Voronoi": 5,
            "Custom": 6,
        }.get(text, 0)

        self.type_params_stack.setCurrentIndex(type_index)
        self._emit_preview()

    def _browse_heightmap(self):
        """Öffnet Dateiauswahl für Custom Heightmap."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Select Heightmap"),
            "",
            "Images (*.png *.jpg *.bmp *.tif);;All Files (*.*)"
        )
        if path:
            self._custom_path = path
            # Nur Dateiname anzeigen
            import os
            self.custom_path_label.setText(os.path.basename(path))
            self._emit_preview()

    def _emit_preview(self):
        """Sendet Preview-Signal wenn aktiviert."""
        if self.preview_check.isChecked():
            self.preview_requested.emit(self.get_config())

    def _on_apply(self):
        """Apply-Button geklickt."""
        if self._face_count == 0:
            logger.warning("Keine Faces selektiert für Textur")
            return

        config = self.get_config()
        logger.info(f"Surface Texture anwenden: {config['texture_type']}, "
                   f"Scale={config['scale']}mm, Depth={config['depth']}mm")
        self.texture_applied.emit(config)

    def _on_cancel(self):
        """Cancel-Button geklickt."""
        self.cancelled.emit()

    def get_config(self) -> dict:
        """Gibt die aktuelle Textur-Konfiguration zurück."""
        texture_type = self.type_combo.currentText().lower()

        config = {
            "texture_type": texture_type,
            "scale": self.scale_spin.value(),
            "depth": self.depth_spin.value(),
            "rotation": self.rotation_spin.value(),
            "invert": self.invert_check.isChecked(),
            "solid_base": self.solid_base_check.isChecked(),
            "type_params": self._get_type_params(texture_type),
        }

        return config

    def _get_type_params(self, texture_type: str) -> dict:
        """Gibt typ-spezifische Parameter zurück."""
        if texture_type == "ripple":
            wave_width = self.ripple_wave_width.value()
            return {
                "wave_count": int(self.ripple_wave_count.value()),
                "wave_shape": self.ripple_wave_shape.currentText(),
                "print_safe": self.ripple_print_safe.isChecked(),
                "wave_width": wave_width if wave_width > 0 else None,  # None = automatisch
            }
        elif texture_type == "honeycomb":
            return {
                "cell_size": self.honeycomb_cell_size.value(),
                "wall_thickness": 0.5,
            }
        elif texture_type == "diamond":
            return {
                "aspect_ratio": self.diamond_aspect.value(),
                "pyramid_height": 0.3,
            }
        elif texture_type == "knurl":
            return {
                "pitch": self.knurl_pitch.value(),
                "angle": self.knurl_angle.value(),
            }
        elif texture_type == "crosshatch":
            return {
                "line_spacing": self.crosshatch_spacing.value(),
                "line_depth": 0.3,
            }
        elif texture_type == "voronoi":
            return {
                "cell_count": int(self.voronoi_cells.value()),
                "randomness": self.voronoi_randomness.value(),
                "edge_width": 0.3,
                "seed": 42,
            }
        elif texture_type == "custom":
            return {
                "heightmap_path": self._custom_path,
            }
        else:
            return {}

    def set_face_count(self, count: int):
        """Aktualisiert die Face-Anzahl Anzeige."""
        self._face_count = count
        if count == 0:
            self.face_info.setText(tr("No faces selected - click on faces"))
            self.face_info.setStyleSheet("color: #ff6b6b;")
            self.apply_btn.setEnabled(False)
        elif count == 1:
            self.face_info.setText(tr("1 Face selected"))
            self.face_info.setStyleSheet("color: #6bff6b;")
            self.apply_btn.setEnabled(True)
        else:
            self.face_info.setText(tr(f"{count} Faces selected"))
            self.face_info.setStyleSheet("color: #6bff6b;")
            self.apply_btn.setEnabled(True)

    def reset(self):
        """Setzt das Panel auf Standardwerte zurück."""
        self._face_count = 0
        self.type_combo.setCurrentIndex(0)
        self.scale_spin.setValue(2.0)
        self.depth_spin.setValue(1.0)
        self.rotation_spin.setValue(0)
        self.invert_check.setChecked(False)
        self.preview_check.setChecked(False)
        self._custom_path = ""
        self.custom_path_label.setText(tr("No file selected"))
        self.set_face_count(0)

    def show_at(self, viewport):
        """Positioniert das Panel am Viewport."""
        # Rechts unten im Viewport
        if viewport and hasattr(viewport, 'geometry'):
            vp_rect = viewport.geometry()
            panel_w = self.width()
            panel_h = self.height()

            # Rechts unten mit etwas Abstand
            x = vp_rect.right() - panel_w - 20
            y = vp_rect.bottom() - panel_h - 20

            self.move(x, y)

        self.show()
        self.raise_()
