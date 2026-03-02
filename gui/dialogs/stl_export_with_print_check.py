"""
MashCad - STL Export Dialog with Printability Check
====================================================

Enhanced STL export dialog with 3D printability warnings.

Features:
- Tessellation quality settings
- Printability analysis
- Warnings for overhangs, supports, stability
- Link to Print Optimize dialog

Author: Claude (AP 4.1: Export Trust Integration)
Date: 2026-03-02
Branch: feature/tnp5
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QSlider,
    QScrollArea, QWidget, QTextEdit
)
from PySide6.QtCore import Qt, QTimer
from loguru import logger
from gui.design_tokens import DesignTokens
from i18n import tr
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from modeling import Body


# Quality presets: (linear_deflection, angular_tolerance, label)
QUALITY_PRESETS = [
    (0.1,   0.5,  "Draft"),       # ~11° angular, coarse
    (0.05,  0.3,  "Standard"),    # ~17° angular
    (0.01,  0.2,  "Fine"),        # ~11.5° angular, current default
    (0.005, 0.1,  "Ultra"),       # ~5.7° angular, very fine
]


class PrintabilityWarning:
    """A printability warning with severity and message."""

    WARNING = 1
    ERROR = 2
    INFO = 0

    def __init__(self, level: int, message: str, suggestion: str = ""):
        self.level = level
        self.message = message
        self.suggestion = suggestion

    def get_color(self) -> str:
        if self.level == self.ERROR:
            return "#ff6b6b"  # Red
        elif self.level == self.WARNING:
            return "#ffd93d"  # Yellow
        return "#6bcf7f"  # Green


class STLExportWithPrintCheckDialog(QDialog):
    """
    Enhanced STL export dialog with printability warnings.

    Analyzes the part for 3D printing issues before export.
    """

    # Signal emitted when user wants to optimize
    optimize_requested = None  # Will be a Signal if needed

    def __init__(self, bodies: List, triangle_estimator=None, parent=None):
        """
        Args:
            bodies: List of Body objects to export
            triangle_estimator: Optional callable(linear_defl, angular_tol) -> int
            parent: Parent widget
        """
        super().__init__(parent)
        self.bodies = bodies
        self._estimator = triangle_estimator
        self.warnings: List[PrintabilityWarning] = []
        self.metrics_analyzed = False

        self.setWindowTitle(tr("Export STL"))
        self.setMinimumWidth(500)
        self.setMinimumHeight(600)

        self._setup_ui()

        # Run printability analysis after UI is shown
        QTimer.singleShot(100, self._analyze_printability)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content = QWidget()
        content_layout = QVBoxLayout(content)

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
        content_layout.addWidget(qual_group)

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
        content_layout.addWidget(fmt_group)

        # Printability Check (NEW for Phase 4)
        self.print_group = QGroupBox(tr("3D Printability Check"))
        print_layout = QVBoxLayout()

        self.print_status_label = QLabel(tr("Analyzing..."))
        self.print_status_label.setStyleSheet("color: #999; font-style: italic;")
        print_layout.addWidget(self.print_status_label)

        self.print_warnings_text = QTextEdit()
        self.print_warnings_text.setMaximumHeight(150)
        self.print_warnings_text.setReadOnly(True)
        self.print_warnings_text.setVisible(False)
        print_layout.addWidget(self.print_warnings_text)

        # Optimize button (shown if issues detected)
        self.optimize_btn = QPushButton(tr("Optimize for 3D Printing"))
        self.optimize_btn.setVisible(False)
        self.optimize_btn.setObjectName("secondary")
        self.optimize_btn.clicked.connect(self._on_optimize_clicked)
        print_layout.addWidget(self.optimize_btn)

        self.print_group.setLayout(print_layout)
        content_layout.addWidget(self.print_group)

        # Buttons
        btn_layout = QHBoxLayout()
        cancel = QPushButton(tr("Cancel"))
        cancel.clicked.connect(self.reject)

        self.export_btn = QPushButton(tr("Export"))
        self.export_btn.setDefault(True)
        self.export_btn.clicked.connect(self.accept)
        self.export_btn.setObjectName("primary")

        btn_layout.addStretch()
        btn_layout.addWidget(cancel)
        btn_layout.addWidget(self.export_btn)

        content_layout.addSpacing(10)
        content_layout.addLayout(btn_layout)

        scroll.setWidget(content)
        layout.addWidget(scroll)

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

    def _analyze_printability(self):
        """Analyze bodies for printability issues."""
        if not self.bodies:
            self._show_no_issues()
            return

        try:
            from modeling.printability_score import compute_orientation_metrics

            all_warnings = []
            has_issues = False

            for body in self.bodies:
                if not hasattr(body, '_build123d_solid') or body._build123d_solid is None:
                    continue

                try:
                    metrics = compute_orientation_metrics(body._build123d_solid)

                    # Check for issues
                    warnings = self._check_metrics(metrics, body.name)
                    all_warnings.extend(warnings)

                    if warnings:
                        has_issues = True

                except Exception as e:
                    logger.warning(f"Printability analysis failed for {body.name}: {e}")

            self.warnings = all_warnings
            self.metrics_analyzed = True

            if has_issues:
                self._show_warnings(all_warnings)
            else:
                self._show_no_issues()

        except Exception as e:
            logger.warning(f"Printability check failed: {e}")
            self._show_check_failed()

    def _check_metrics(self, metrics, body_name: str) -> List[PrintabilityWarning]:
        """Check orientation metrics for printability issues."""
        warnings = []

        # Overhang check (critical overhangs > 45°)
        if metrics.overhang_ratio > 0.3:
            warnings.append(PrintabilityWarning(
                PrintabilityWarning.ERROR,
                f"{body_name}: {metrics.overhang_ratio*100:.0f}% overhang area",
                tr("Consider rotating the part to reduce overhangs.")
            ))
        elif metrics.overhang_ratio > 0.15:
            warnings.append(PrintabilityWarning(
                PrintabilityWarning.WARNING,
                f"{body_name}: {metrics.overhang_ratio*100:.0f}% overhang area",
                tr("Some support structures may be needed.")
            ))

        # Support volume check
        if metrics.support_volume_estimate_mm3 > 10000:
            warnings.append(PrintabilityWarning(
                PrintabilityWarning.WARNING,
                f"{body_name}: ~{metrics.support_volume_estimate_mm3/1000:.0f} cm³ support material",
                tr("Consider reorienting to reduce supports.")
            ))

        # Stability check
        if metrics.stability_score < 0.5:
            warnings.append(PrintabilityWarning(
                PrintabilityWarning.WARNING,
                f"{body_name}: Low stability score ({metrics.stability_score:.2f})",
                tr("Part may tip over during printing. Use a brim or raft.")
            ))

        # Build height check
        if metrics.build_height_mm > 150:
            warnings.append(PrintabilityWarning(
                PrintabilityWarning.WARNING,
                f"{body_name}: Tall build height ({metrics.build_height_mm:.0f} mm)",
                tr("Consider printing horizontally if possible.")
            ))

        # Base contact check
        if metrics.base_contact_area_mm2 < 100:
            warnings.append(PrintabilityWarning(
                PrintabilityWarning.ERROR,
                f"{body_name}: Small base contact ({metrics.base_contact_area_mm2:.0f} mm²)",
                tr("Add a brim or raft for better adhesion.")
            ))

        return warnings

    def _show_warnings(self, warnings: List[PrintabilityWarning]):
        """Display printability warnings."""
        self.print_status_label.setText(tr("Printability issues detected"))
        self.print_status_label.setStyleSheet("color: #ff6b6b; font-weight: bold;")

        # Build warning text
        text = ""
        for w in warnings:
            icon = "❌" if w.level == PrintabilityWarning.ERROR else "⚠️"
            text += f"{icon} {w.message}\n"
            if w.suggestion:
                text += f"   💡 {w.suggestion}\n"
            text += "\n"

        self.print_warnings_text.setText(text.strip())
        self.print_warnings_text.setVisible(True)
        self.optimize_btn.setVisible(True)

        # Add warning to export button
        self.export_btn.setText(tr("Export Anyway"))

    def _show_no_issues(self):
        """Show no issues found."""
        self.print_status_label.setText(tr("✓ No printability issues detected"))
        self.print_status_label.setStyleSheet("color: #6bcf7f; font-weight: bold;")
        self.print_warnings_text.setVisible(False)
        self.optimize_btn.setVisible(False)
        self.export_btn.setText(tr("Export"))

    def _show_check_failed(self):
        """Show that analysis failed."""
        self.print_status_label.setText(tr("Printability check unavailable"))
        self.print_status_label.setStyleSheet("color: #999; font-style: italic;")
        self.print_warnings_text.setVisible(False)
        self.optimize_btn.setVisible(False)
        self.export_btn.setText(tr("Export"))

    def _on_optimize_clicked(self):
        """User clicked Optimize button - close and open optimize dialog."""
        # Close this dialog first
        self.reject()

        # Open print optimize dialog
        # Note: This is handled by the caller checking the result
        if self.parent():
            try:
                from gui.dialogs.print_optimize_dialog import show_print_optimize_dialog
                # The parent should be MainWindow
                show_print_optimize_dialog(self.parent())
            except Exception as e:
                logger.error(f"Failed to open optimize dialog: {e}")

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

    def has_warnings(self) -> bool:
        """Check if any printability warnings were detected."""
        return len(self.warnings) > 0


def show_stl_export_with_print_check(bodies, triangle_estimator=None, parent=None):
    """
    Show enhanced STL export dialog with printability check.

    Args:
        bodies: List of Body objects to export
        triangle_estimator: Optional callable for triangle count estimation
        parent: Parent widget (usually MainWindow)

    Returns:
        Dialog result code (QDialog.Accepted or Rejected)
    """
    dialog = STLExportWithPrintCheckDialog(bodies, triangle_estimator, parent)
    return dialog.exec()
