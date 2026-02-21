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
    QGroupBox, QFileDialog, QStackedWidget
)
from PySide6.QtCore import Signal, QPoint

from loguru import logger
from gui.design_tokens import DesignTokens

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

        self.setMinimumWidth(360)
        self.setMaximumWidth(520)
        self.setMinimumHeight(440)

        self._setup_style()
        self._setup_ui()
        
        # Sicherstellen, dass das richtige Typ-Panel angezeigt wird
        self._on_type_changed(self.type_combo.currentText())

        # WICHTIG: Panel beim Start verstecken
        self.hide()

    def _setup_style(self):
        """Konsistenter Style via DesignTokens — Single Source of Truth."""
        self.setStyleSheet(DesignTokens.stylesheet_panel())

    def _setup_ui(self):
        """Erstellt die UI-Elemente."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        title = QLabel(tr("Texture:"))
        title.setObjectName("panelTitle")
        header_row.addWidget(title)

        self.face_info = QLabel(tr("No faces selected"))
        self.face_info.setStyleSheet(
            f"color: {DesignTokens.COLOR_TEXT_MUTED.name()}; font-size: 11px; border: none;"
        )
        header_row.addWidget(self.face_info)
        header_row.addStretch()

        self.close_btn = QPushButton("X")
        self.close_btn.setObjectName("danger")
        self.close_btn.clicked.connect(self._on_cancel)
        header_row.addWidget(self.close_btn)

        main_layout.addLayout(header_row)

        # === Textur-Typ ===
        type_layout = QHBoxLayout()
        type_layout.setSpacing(8)
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
        main_layout.addLayout(type_layout)

        # === Quality Mode ===
        quality_layout = QHBoxLayout()
        quality_layout.setSpacing(8)
        quality_layout.addWidget(QLabel(tr("Quality:")))

        self.quality_combo = QComboBox()
        self.quality_combo.addItems([
            tr("Fast"),
            tr("Balanced"),
            tr("Detailed"),
        ])
        self.quality_combo.setCurrentIndex(1)  # Default: Balanced
        self.quality_combo.currentIndexChanged.connect(self._on_quality_changed)
        self.quality_combo.setMinimumWidth(140)
        quality_layout.addWidget(self.quality_combo)
        quality_layout.addStretch()
        main_layout.addLayout(quality_layout)

        # Quality-Info Label
        self.quality_info = QLabel()
        self.quality_info.setStyleSheet(
            f"color: {DesignTokens.COLOR_TEXT_MUTED.name()}; font-size: 10px; border: none; padding: 2px;"
        )
        self.quality_info.setWordWrap(True)
        main_layout.addWidget(self.quality_info)

        # Initiale Quality-Info setzen
        self._update_quality_info(1)

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
        self.type_params_stack.setMinimumHeight(160)
        self._setup_type_params()
        main_layout.addWidget(self.type_params_stack)
        main_layout.addStretch()

        # Live preview ist aktuell optional/deaktiviert.
        self.preview_check = QCheckBox(tr("Live Preview"))
        self.preview_check.setChecked(False)
        self.preview_check.stateChanged.connect(self._emit_preview)

        # === Buttons ===
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch()

        self.apply_btn = QPushButton(tr("Apply"))
        self.apply_btn.setObjectName("primary")
        self.apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(self.apply_btn)

        self.cancel_btn = QPushButton("X")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)

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
        self.custom_path_label.setStyleSheet(
            f"color: {DesignTokens.COLOR_TEXT_MUTED.name()}; border: none;"
        )
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

    def _on_quality_changed(self, index: int):
        """Handler wenn Quality-Modus geändert wird."""
        self._update_quality_info(index)
        self._emit_preview()

    def _update_quality_info(self, index: int):
        """Aktualisiert die Quality-Info basierend auf dem ausgewählten Modus."""
        quality_texts = {
            0: tr("Fast preview - Low detail, good for quick adjustments"),
            1: tr("Balanced - Good quality with reasonable performance (Default)"),
            2: tr("Detailed - High quality, slower preview"),
        }

        self.quality_info.setText(quality_texts.get(index, ""))

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

        # Quality-Modus bestimmen
        quality_mode = self.quality_combo.currentIndex()  # 0=Fast, 1=Balanced, 2=Detailed

        config = {
            "texture_type": texture_type,
            "scale": self.scale_spin.value(),
            "depth": self.depth_spin.value(),
            "rotation": self.rotation_spin.value(),
            "invert": self.invert_check.isChecked(),
            "solid_base": self.solid_base_check.isChecked(),
            "quality_mode": quality_mode,  # 0=Fast, 1=Balanced, 2=Detailed
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
            self.face_info.setStyleSheet(
                f"color: {DesignTokens.COLOR_ERROR.name()}; font-size: 11px; border: none;"
            )
            self.apply_btn.setEnabled(False)
        elif count == 1:
            self.face_info.setText(tr("1 Face selected"))
            self.face_info.setStyleSheet(
                f"color: {DesignTokens.COLOR_SUCCESS.name()}; font-size: 11px; border: none;"
            )
            self.apply_btn.setEnabled(True)
        else:
            self.face_info.setText(tr("{count} Faces selected").format(count=count))
            self.face_info.setStyleSheet(
                f"color: {DesignTokens.COLOR_SUCCESS.name()}; font-size: 11px; border: none;"
            )
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
        """Positioniert das Panel rechts mittig am Viewport (InputPanel-Standard)."""
        self.show()
        self.raise_()
        self._position_right_mid(viewport)

    def _position_right_mid(self, pos_widget):
        parent = self.parent() or pos_widget
        if parent is None:
            return

        if pos_widget is None:
            area_x, area_y, area_w, area_h = 0, 0, parent.width(), parent.height()
        elif pos_widget.parent() is parent:
            geom = pos_widget.geometry()
            area_x, area_y, area_w, area_h = geom.x(), geom.y(), geom.width(), geom.height()
        else:
            top_left = pos_widget.mapTo(parent, QPoint(0, 0))
            area_x, area_y, area_w, area_h = top_left.x(), top_left.y(), pos_widget.width(), pos_widget.height()

        self.adjustSize()
        margin = 12
        x = area_x + area_w - self.width() - margin
        y = area_y + (area_h - self.height()) // 2

        tp = getattr(parent, "transform_panel", None)
        if tp and tp.isVisible():
            x = min(x, tp.x() - self.width() - margin)
            y = tp.y() + (tp.height() - self.height()) // 2

        tb = getattr(parent, "transform_toolbar", None)
        if tb and tb.isVisible():
            tb_pos = tb.mapTo(parent, QPoint(0, 0))
            x = min(x, tb_pos.x() - self.width() - margin)

        x = max(area_x + margin, min(x, area_x + area_w - self.width() - margin))
        y = max(area_y + margin, min(y, area_y + area_h - self.height() - margin))

        self.move(x, y)
        self.raise_()
