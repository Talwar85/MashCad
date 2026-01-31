"""
MashCad - Thread Dialog V2
Create threads on holes/cylinders, generate bolts and nuts.
Supports ISO metric threads with tolerance classes.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QGroupBox, QCheckBox,
    QRadioButton, QDoubleSpinBox, QButtonGroup
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from loguru import logger
from gui.design_tokens import DesignTokens
from i18n import tr


# ISO metric coarse threads: (nominal_dia, pitch, minor_dia_ext, minor_dia_int)
METRIC_THREADS = {
    "M3":  (3.0,  0.5,  2.459, 2.459),
    "M4":  (4.0,  0.7,  3.242, 3.242),
    "M5":  (5.0,  0.8,  4.134, 4.134),
    "M6":  (6.0,  1.0,  4.917, 4.917),
    "M8":  (8.0,  1.25, 6.647, 6.647),
    "M10": (10.0, 1.5,  8.376, 8.376),
    "M12": (12.0, 1.75, 10.106, 10.106),
    "M16": (16.0, 2.0,  13.835, 13.835),
    "M20": (20.0, 2.5,  17.294, 17.294),
    "M24": (24.0, 3.0,  20.752, 20.752),
}

# ISO tolerance classes for threads
# (tolerance_class, description, tolerance_mm_per_10mm_dia)
TOLERANCE_CLASSES = {
    # External (bolt) - smaller = tighter
    "6g": ("Medium fit (standard)", -0.032),   # ISO default for bolts
    "6h": ("Close fit", 0.0),
    "4g": ("Tight fit", -0.018),
    "8g": ("Loose fit", -0.042),
    # Internal (nut)
    "6H": ("Medium fit (standard)", 0.0),      # ISO default for nuts
    "5H": ("Close fit", 0.0),
    "7H": ("Loose fit", 0.0),
}

# Standard hex bolt/nut dimensions: (across_flats, head_height, nut_height)
HEX_DIMENSIONS = {
    "M3":  (5.5,  2.0,  2.4),
    "M4":  (7.0,  2.8,  3.2),
    "M5":  (8.0,  3.5,  4.0),
    "M6":  (10.0, 4.0,  5.0),
    "M8":  (13.0, 5.3,  6.5),
    "M10": (16.0, 6.4,  8.0),
    "M12": (18.0, 7.5,  10.0),
    "M16": (24.0, 10.0, 13.0),
    "M20": (30.0, 12.5, 16.0),
    "M24": (36.0, 15.0, 19.0),
}


class ThreadDialog(QDialog):
    """Dialog to create thread features, bolts, or nuts."""

    def __init__(self, mode="thread", parent=None):
        """
        Args:
            mode: "thread" (apply to body), "bolt" (generate bolt), "nut" (generate nut)
        """
        super().__init__(parent)
        self.mode = mode
        titles = {"thread": tr("Thread"), "bolt": tr("Generate Bolt"), "nut": tr("Generate Nut")}
        self.setWindowTitle(titles.get(mode, tr("Thread")))
        self.setMinimumWidth(420)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Mode selector (Thread on body / Generate Bolt / Generate Nut)
        mode_group = QGroupBox(tr("Mode"))
        mode_layout = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([tr("Thread on Body"), tr("Generate Bolt"), tr("Generate Nut")])
        mode_map = {"thread": 0, "bolt": 1, "nut": 2}
        self.mode_combo.setCurrentIndex(mode_map.get(self.mode, 0))
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # Thread parameters
        param_group = QGroupBox(tr("Thread Parameters"))
        param_layout = QVBoxLayout()

        # Type (External/Internal) - only for "thread on body"
        type_row = QHBoxLayout()
        self.type_label = QLabel(tr("Type:"))
        type_row.addWidget(self.type_label)
        self.type_combo = QComboBox()
        self.type_combo.addItems([tr("External (Bolt)"), tr("Internal (Nut)")])
        self.type_combo.currentIndexChanged.connect(self._update_tolerance_options)
        type_row.addWidget(self.type_combo)
        type_row.addStretch()
        param_layout.addLayout(type_row)

        # Standard preset
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel(tr("Size:")))
        self.preset_combo = QComboBox()
        self.preset_combo.addItem(tr("Custom"))
        for name in METRIC_THREADS:
            self.preset_combo.addItem(name)
        self.preset_combo.setCurrentText("M10")
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        preset_row.addWidget(self.preset_combo)
        preset_row.addStretch()
        param_layout.addLayout(preset_row)

        # Diameter
        dia_row = QHBoxLayout()
        lbl = QLabel(tr("Diameter:"))
        lbl.setMinimumWidth(100)
        dia_row.addWidget(lbl)
        self.diameter_input = QLineEdit("10")
        v = QDoubleValidator(0.5, 500, 3)
        v.setNotation(QDoubleValidator.StandardNotation)
        self.diameter_input.setValidator(v)
        dia_row.addWidget(self.diameter_input)
        dia_row.addWidget(QLabel("mm"))
        param_layout.addLayout(dia_row)

        # Pitch
        pitch_row = QHBoxLayout()
        plbl = QLabel(tr("Pitch:"))
        plbl.setMinimumWidth(100)
        pitch_row.addWidget(plbl)
        self.pitch_input = QLineEdit("1.5")
        pv = QDoubleValidator(0.1, 50, 2)
        pv.setNotation(QDoubleValidator.StandardNotation)
        self.pitch_input.setValidator(pv)
        pitch_row.addWidget(self.pitch_input)
        pitch_row.addWidget(QLabel("mm"))
        param_layout.addLayout(pitch_row)

        # Length / Depth
        depth_row = QHBoxLayout()
        self.depth_label = QLabel(tr("Depth:"))
        self.depth_label.setMinimumWidth(100)
        depth_row.addWidget(self.depth_label)
        self.depth_input = QLineEdit("20")
        dv = QDoubleValidator(0.1, 1000, 2)
        dv.setNotation(QDoubleValidator.StandardNotation)
        self.depth_input.setValidator(dv)
        depth_row.addWidget(self.depth_input)
        depth_row.addWidget(QLabel("mm"))
        param_layout.addLayout(depth_row)

        param_group.setLayout(param_layout)
        layout.addWidget(param_group)

        # Tolerance group - ISO Preset or Custom
        tol_group = QGroupBox(tr("Tolerance"))
        tol_layout = QVBoxLayout()

        # Radio button group
        self.tol_button_group = QButtonGroup(self)

        # ISO Preset row
        iso_row = QHBoxLayout()
        self.tol_iso_radio = QRadioButton(tr("ISO Preset:"))
        self.tol_iso_radio.setChecked(True)
        self.tol_button_group.addButton(self.tol_iso_radio)
        iso_row.addWidget(self.tol_iso_radio)
        self.tolerance_combo = QComboBox()
        self._update_tolerance_options()
        iso_row.addWidget(self.tolerance_combo)
        iso_row.addStretch()
        tol_layout.addLayout(iso_row)

        # Custom tolerance row
        custom_row = QHBoxLayout()
        self.tol_custom_radio = QRadioButton(tr("Custom:"))
        self.tol_button_group.addButton(self.tol_custom_radio)
        custom_row.addWidget(self.tol_custom_radio)
        self.custom_tolerance_input = QDoubleSpinBox()
        self.custom_tolerance_input.setRange(-1.0, 1.0)
        self.custom_tolerance_input.setSingleStep(0.01)
        self.custom_tolerance_input.setDecimals(3)
        self.custom_tolerance_input.setValue(0.0)
        self.custom_tolerance_input.setSuffix(" mm")
        self.custom_tolerance_input.setEnabled(False)
        custom_row.addWidget(self.custom_tolerance_input)
        custom_row.addStretch()
        tol_layout.addLayout(custom_row)

        # Radio toggle connections
        self.tol_iso_radio.toggled.connect(self._on_tolerance_mode_changed)
        self.tol_custom_radio.toggled.connect(self._on_tolerance_mode_changed)

        # Tolerance info label
        self.tol_info = QLabel("")
        self.tol_info.setStyleSheet("color: #999; font-size: 11px; font-style: italic;")
        tol_layout.addWidget(self.tol_info)
        self.tolerance_combo.currentTextChanged.connect(self._update_tolerance_info)
        self.custom_tolerance_input.valueChanged.connect(self._update_custom_tolerance_info)

        tol_group.setLayout(tol_layout)
        layout.addWidget(tol_group)

        # Bolt/Nut specific options
        self.bolt_group = QGroupBox(tr("Bolt/Nut Options"))
        bolt_layout = QVBoxLayout()

        head_row = QHBoxLayout()
        head_row.addWidget(QLabel(tr("Head Type:")))
        self.head_combo = QComboBox()
        self.head_combo.addItems([tr("Hex"), tr("Socket Cap"), tr("Countersunk"), tr("Pan Head")])
        head_row.addWidget(self.head_combo)
        head_row.addStretch()
        bolt_layout.addLayout(head_row)

        self.bolt_group.setLayout(bolt_layout)
        layout.addWidget(self.bolt_group)
        self.bolt_group.setVisible(self.mode != "thread")

        # Buttons
        btn_layout = QHBoxLayout()
        cancel = QPushButton(tr("Cancel"))
        cancel.clicked.connect(self.reject)

        create = QPushButton(tr("Create"))
        create.setDefault(True)
        create.clicked.connect(self._on_create)
        create.setObjectName("primary")

        btn_layout.addStretch()
        btn_layout.addWidget(cancel)
        btn_layout.addWidget(create)
        layout.addSpacing(10)
        layout.addLayout(btn_layout)

        # Dark theme
        self.setStyleSheet(DesignTokens.stylesheet_dialog())

        # Initialize
        self._on_preset_changed(self.preset_combo.currentText())
        self._on_mode_changed(self.mode_combo.currentIndex())

    def _on_mode_changed(self, index):
        is_thread = (index == 0)
        is_bolt = (index == 1)
        is_nut = (index == 2)

        self.type_label.setVisible(is_thread)
        self.type_combo.setVisible(is_thread)
        self.bolt_group.setVisible(is_bolt or is_nut)
        self.depth_label.setText(tr("Length:") if is_bolt else tr("Depth:"))

        if is_bolt:
            self.type_combo.setCurrentIndex(0)  # External
        elif is_nut:
            self.type_combo.setCurrentIndex(1)  # Internal

        self._update_tolerance_options()

    def _on_tolerance_mode_changed(self):
        """Toggle between ISO preset and custom tolerance."""
        if not hasattr(self, 'custom_tolerance_input'):
            return
        is_custom = self.tol_custom_radio.isChecked()
        self.tolerance_combo.setEnabled(not is_custom)
        self.custom_tolerance_input.setEnabled(is_custom)
        if is_custom:
            self._update_custom_tolerance_info(self.custom_tolerance_input.value())
        else:
            self._update_tolerance_info(self.tolerance_combo.currentText())

    def _update_custom_tolerance_info(self, value):
        """Update info label for custom tolerance."""
        if not hasattr(self, 'tol_info'):
            return
        if value > 0:
            self.tol_info.setText(tr("Clearance fit") + f" | {tr('Diameter offset')}: +{value:.3f} mm")
        elif value < 0:
            self.tol_info.setText(tr("Interference fit") + f" | {tr('Diameter offset')}: {value:.3f} mm")
        else:
            self.tol_info.setText(tr("Nominal (no offset)"))

    def _update_tolerance_options(self):
        self.tolerance_combo.clear()
        is_external = self.type_combo.currentIndex() == 0
        if is_external:
            self.tolerance_combo.addItems(["6g (Standard)", "6h (Close)", "4g (Tight)", "8g (Loose)"])
        else:
            self.tolerance_combo.addItems(["6H (Standard)", "5H (Close)", "7H (Loose)"])
        # Only update info if tol_info exists (not during initial setup)
        if hasattr(self, 'tol_info'):
            self._update_tolerance_info(self.tolerance_combo.currentText())

    def _update_tolerance_info(self, text):
        if not hasattr(self, 'tol_info'):
            return
        key = text.split(" ")[0] if text else ""
        if key in TOLERANCE_CLASSES:
            desc, offset = TOLERANCE_CLASSES[key]
            dia = float(self.diameter_input.text() or "10")
            # Scale tolerance with diameter
            actual_tol = offset * (dia / 10.0)
            if abs(actual_tol) > 0.001:
                self.tol_info.setText(f"{desc} | Diameter offset: {actual_tol:+.3f} mm")
            else:
                self.tol_info.setText(f"{desc} | Nominal (no offset)")
        else:
            self.tol_info.setText("")

    def _on_preset_changed(self, text):
        if text in METRIC_THREADS:
            dia, pitch, _, _ = METRIC_THREADS[text]
            self.diameter_input.setText(str(dia))
            self.pitch_input.setText(str(pitch))
            self._update_tolerance_info(self.tolerance_combo.currentText())

    def _on_create(self):
        try:
            mode_idx = self.mode_combo.currentIndex()
            self.result_mode = ["thread", "bolt", "nut"][mode_idx]

            self.thread_type_str = "external" if self.type_combo.currentIndex() == 0 else "internal"
            self.diameter = float(self.diameter_input.text() or "10")
            self.pitch = float(self.pitch_input.text() or "1.5")
            self.depth = float(self.depth_input.text() or "20")

            if self.diameter <= 0 or self.pitch <= 0 or self.depth <= 0:
                logger.warning("All values must be > 0")
                return

            # Tolerance - ISO preset or custom
            if self.tol_custom_radio.isChecked():
                # Custom tolerance - use directly
                self.tolerance_offset = self.custom_tolerance_input.value()
                self.tolerance_class = "custom"
            else:
                # ISO preset
                tol_text = self.tolerance_combo.currentText().split(" ")[0]
                self.tolerance_class = tol_text
                tol_data = TOLERANCE_CLASSES.get(tol_text, ("", 0.0))
                self.tolerance_offset = tol_data[1] * (self.diameter / 10.0)

            # Head type for bolt/nut
            self.head_type = self.head_combo.currentText().lower().replace(" ", "_")

            # Hex dimensions
            preset = self.preset_combo.currentText()
            if preset in HEX_DIMENSIONS:
                self.hex_af, self.head_height, self.nut_height = HEX_DIMENSIONS[preset]
            else:
                # Approximate from diameter
                self.hex_af = self.diameter * 1.6
                self.head_height = self.diameter * 0.65
                self.nut_height = self.diameter * 0.8

            self.accept()
        except ValueError as e:
            logger.error(f"Invalid input: {e}")
