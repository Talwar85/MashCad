"""
MashCad - STL Export Dialog
Configure tessellation quality, format, and units for STL export.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QSlider, QCheckBox
)
from PySide6.QtCore import Qt
from loguru import logger
from gui.design_tokens import DesignTokens
from i18n import tr


# Quality presets: (linear_deflection, angular_tolerance, label)
QUALITY_PRESETS = [
    (0.1,   0.5,  "Draft"),       # ~11° angular, coarse
    (0.05,  0.3,  "Standard"),    # ~17° angular
    (0.01,  0.2,  "Fine"),        # ~11.5° angular, current default
    (0.005, 0.1,  "Ultra"),       # ~5.7° angular, very fine
]


class STLExportDialog(QDialog):
    """Dialog to configure STL export parameters."""

    def __init__(self, triangle_estimator=None, parent=None):
        """
        Args:
            triangle_estimator: Optional callable(linear_defl, angular_tol) -> int
                                that estimates triangle count for preview.
        """
        super().__init__(parent)
        self._estimator = triangle_estimator
        self.setWindowTitle(tr("Export STL"))
        self.setMinimumWidth(400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Quality
        qual_group = QGroupBox(tr("Tessellation Quality"))
        qual_layout = QVBoxLayout()

        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setRange(0, 3)
        self.quality_slider.setValue(2)  # Fine = current default
        self.quality_slider.setTickPosition(QSlider.TicksBelow)
        self.quality_slider.setTickInterval(1)
        self.quality_slider.valueChanged.connect(self._on_quality_changed)

        labels_row = QHBoxLayout()
        for preset in QUALITY_PRESETS:
            lbl = QLabel(tr(preset[2]))
            lbl.setAlignment(Qt.AlignCenter)
            labels_row.addWidget(lbl)

        self.quality_info = QLabel("")
        self.quality_info.setStyleSheet("color: #999; font-size: 11px; font-style: italic;")

        qual_layout.addWidget(self.quality_slider)
        qual_layout.addLayout(labels_row)
        qual_layout.addWidget(self.quality_info)
        qual_group.setLayout(qual_layout)
        layout.addWidget(qual_group)

        # Format
        fmt_group = QGroupBox(tr("Format"))
        fmt_layout = QVBoxLayout()

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel(tr("File Type:")))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Binary STL", "ASCII STL"])
        type_row.addWidget(self.format_combo)
        type_row.addStretch()
        fmt_layout.addLayout(type_row)

        unit_row = QHBoxLayout()
        unit_row.addWidget(QLabel(tr("Units:")))
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["mm", "inch"])
        unit_row.addWidget(self.unit_combo)
        unit_row.addStretch()
        fmt_layout.addLayout(unit_row)

        fmt_group.setLayout(fmt_layout)
        layout.addWidget(fmt_group)

        # Buttons
        btn_layout = QHBoxLayout()
        cancel = QPushButton(tr("Cancel"))
        cancel.clicked.connect(self.reject)

        export_btn = QPushButton(tr("Export"))
        export_btn.setDefault(True)
        export_btn.clicked.connect(self.accept)
        export_btn.setObjectName("primary")

        btn_layout.addStretch()
        btn_layout.addWidget(cancel)
        btn_layout.addWidget(export_btn)
        layout.addSpacing(10)
        layout.addLayout(btn_layout)

        self.setStyleSheet(DesignTokens.stylesheet_dialog())
        self._on_quality_changed(self.quality_slider.value())

    def _on_quality_changed(self, index):
        linear, angular, name = QUALITY_PRESETS[index]
        info = f"{tr(name)} — {tr('Linear Deflection')}: {linear} mm, {tr('Angular')}: {angular} rad"
        if self._estimator:
            try:
                count = self._estimator(linear, angular)
                info += f" — ~{count:,} {tr('triangles')}"
            except Exception:
                pass
        self.quality_info.setText(info)

    @property
    def linear_deflection(self):
        return QUALITY_PRESETS[self.quality_slider.value()][0]

    @property
    def angular_tolerance(self):
        return QUALITY_PRESETS[self.quality_slider.value()][1]

    @property
    def is_binary(self):
        return self.format_combo.currentIndex() == 0

    @property
    def scale_factor(self):
        """Returns scale factor: 1.0 for mm, 1/25.4 for inch."""
        return 1.0 if self.unit_combo.currentIndex() == 0 else 1.0 / 25.4
