"""
MashCad - Print Optimization Dialog
=====================================

Dialog for analyzing and optimizing print orientation.

Features:
- Select body and material
- Analyze printability and generate orientation recommendations
- Preview recommended orientation in viewport
- Apply orientation as Transform feature
- Generate support fins (V1: preview only)

Author: Claude (AP 3.1: Print Optimize Dialog)
Date: 2026-03-02
Branch: feature/tnp5
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar, QTextEdit,
    QFrame, QSizePolicy, QScrollArea
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from loguru import logger
from gui.design_tokens import DesignTokens
from i18n import tr
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from modeling import Body
    from gui.main_window import MainWindow


class PrintOptimizeDialog(QDialog):
    """
    Dialog for print orientation optimization.

    Provides:
    - Body selection
    - Material preset selection
    - Orientation analysis
    - Recommendation display with before/after comparison
    - Preview and apply functionality
    """

    def __init__(self, main_window, parent=None):
        """
        Initialize the print optimization dialog.

        Args:
            main_window: MainWindow instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.main_window = main_window
        self.document = main_window.document
        self.current_body = None
        self.recommendation = None
        self._overlay = None

        self.setWindowTitle(tr("Optimize for 3D Printing"))
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        self._setup_ui()
        self._connect_signals()
        self._load_bodies()
        self._init_overlay()

        # Dark theme
        self.setStyleSheet(DesignTokens.stylesheet_dialog())

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Header section
        self._create_header(layout)

        # Input section
        self._create_input_section(layout)

        # Results section (initially hidden)
        self._create_results_section(layout)

        # Buttons section
        self._create_buttons(layout)

        # Status bar
        self._create_status_bar(layout)

    def _create_header(self, parent_layout):
        """Create the header section."""
        header = QLabel("<b>" + tr("Optimize for 3D Printing") + "</b>")
        header.setStyleSheet("color: #ddd; padding: 10px; background: #1e1e1e; "
                             "border-radius: 4px; margin-bottom: 10px;")
        parent_layout.addWidget(header)

    def _create_input_section(self, parent_layout):
        """Create the input section with body and material selectors."""
        input_group = QGroupBox(tr("Analysis Settings"))
        input_layout = QVBoxLayout()

        # Body selector
        body_layout = QHBoxLayout()
        body_layout.addWidget(QLabel(tr("Body:")))
        self.body_combo = QComboBox()
        self.body_combo.setMinimumWidth(300)
        body_layout.addWidget(self.body_combo)
        body_layout.addStretch()
        input_layout.addLayout(body_layout)

        # Material selector
        material_layout = QHBoxLayout()
        material_layout.addWidget(QLabel(tr("Material:")))
        self.material_combo = QComboBox()
        self.material_combo.addItems(["PLA", "ABS", "PETG", "TPU", "NYLON"])
        self.material_combo.setMinimumWidth(200)
        material_layout.addWidget(self.material_combo)
        material_layout.addStretch()
        input_layout.addLayout(material_layout)

        # Analyze button
        analyze_layout = QHBoxLayout()
        self.analyze_btn = QPushButton(tr("Analyze"))
        self.analyze_btn.setObjectName("primary")
        analyze_layout.addStretch()
        analyze_layout.addWidget(self.analyze_btn)
        input_layout.addLayout(analyze_layout)

        input_group.setLayout(input_layout)
        parent_layout.addWidget(input_group)

    def _create_results_section(self, parent_layout):
        """Create the results section (initially hidden)."""
        results_group = QGroupBox(tr("Results"))
        results_layout = QVBoxLayout()

        # Recommendation label
        self.recommendation_label = QLabel()
        self.recommendation_label.setStyleSheet(
            "color: #4CAF50; font-size: 14px; font-weight: bold; "
            "padding: 10px; background: #1e3a1e; border-radius: 4px; "
            "margin-bottom: 10px;"
        )
        self.recommendation_label.setAlignment(Qt.AlignCenter)
        self.recommendation_label.setText(tr("Click 'Analyze' to begin"))
        results_layout.addWidget(self.recommendation_label)

        # Before/After comparison table
        self.comparison_table = QTableWidget()
        self.comparison_table.setColumnCount(3)
        self.comparison_table.setHorizontalHeaderLabels([tr("Metric"), tr("Before"), tr("After")])
        self.comparison_table.setRowCount(5)
        self.comparison_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.comparison_table.setMaximumHeight(200)
        results_layout.addWidget(self.comparison_table)

        # Table rows
        self._setup_comparison_table()

        # Alternatives section
        alternatives_label = QLabel(tr("Alternative Orientations:"))
        alternatives_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        results_layout.addWidget(alternatives_label)

        self.alternatives_text = QTextEdit()
        self.alternatives_text.setMaximumHeight(80)
        self.alternatives_text.setReadOnly(True)
        results_layout.addWidget(self.alternatives_text)

        # Explanation
        self.explanation_text = QTextEdit()
        self.explanation_text.setMaximumHeight(100)
        self.explanation_text.setReadOnly(True)
        results_layout.addWidget(self.explanation_text)

        results_group.setLayout(results_layout)
        parent_layout.addWidget(results_group)

        # Initially hide results
        results_group.setVisible(False)

        # Store reference
        self.results_group = results_group

    def _setup_comparison_table(self):
        """Setup the before/after comparison table."""
        metrics = [
            tr("Build Height"),
            tr("Support Volume"),
            tr("Overhang Area"),
            tr("Base Contact"),
            tr("Stability Score"),
        ]

        for i, metric in enumerate(metrics):
            self.comparison_table.setItem(i, 0, QTableWidgetItem(metric))

        # Center alignment
        for row in range(self.comparison_table.rowCount()):
            for col in range(self.comparison_table.columnCount()):
                item = self.comparison_table.item(row, col)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)

    def _create_buttons(self, parent_layout):
        """Create the action buttons."""
        button_layout = QHBoxLayout()

        # Preview button
        self.preview_btn = QPushButton(tr("Preview Orientation"))
        self.preview_btn.setEnabled(False)
        button_layout.addWidget(self.preview_btn)

        # Apply button
        self.apply_btn = QPushButton(tr("Apply Orientation"))
        self.apply_btn.setEnabled(False)
        self.apply_btn.setObjectName("primary")
        button_layout.addWidget(self.apply_btn)

        button_layout.addStretch()

        # Cancel button
        self.cancel_btn = QPushButton(tr("Cancel"))
        button_layout.addWidget(self.cancel_btn)

        parent_layout.addSpacing(20)
        parent_layout.addLayout(button_layout)

    def _create_status_bar(self, parent_layout):
        """Create the status bar."""
        status_layout = QHBoxLayout()

        self.status_label = QLabel(tr("Ready"))
        self.status_label.setStyleSheet("color: #999;")
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(200)
        status_layout.addWidget(self.progress_bar)

        parent_layout.addLayout(status_layout)

    def _connect_signals(self):
        """Connect UI signals to slots."""
        self.analyze_btn.clicked.connect(self._on_analyze)
        self.preview_btn.clicked.connect(self._on_preview)
        self.apply_btn.clicked.connect(self._on_apply)
        self.cancel_btn.clicked.connect(self.reject)

    def _init_overlay(self):
        """Create the viewport overlay helper if a viewport is available."""
        viewport = getattr(self.main_window, "viewport_3d", None)
        if viewport is None:
            return
        try:
            from gui.viewport.print_quality_overlay import PrintQualityOverlay

            self._overlay = PrintQualityOverlay(viewport)
        except Exception as e:
            logger.debug(f"Print quality overlay unavailable: {e}")

    def _load_bodies(self):
        """Load available bodies into the combo box."""
        self.body_combo.clear()

        bodies = self._get_bodies()
        if not bodies:
            self.analyze_btn.setEnabled(False)
            self.status_label.setText(tr("No bodies available"))
            return

        for body in bodies:
            self.body_combo.addItem(body.name, body)

        # Select current active body if available
        active = self._get_active_body()
        if active:
            index = self.body_combo.findData(active)
            if index >= 0:
                self.body_combo.setCurrentIndex(index)
            self.current_body = active

    def _get_bodies(self):
        """Get list of available bodies."""
        try:
            if hasattr(self.document, "get_all_bodies"):
                return list(self.document.get_all_bodies() or [])
        except Exception:
            pass
        return list(getattr(self.document, "bodies", []) or [])

    def _get_active_body(self):
        """Get the currently active body."""
        try:
            viewport = getattr(self.main_window, "viewport_3d", None)
            if viewport is None:
                viewport = getattr(self.main_window, "viewport", None)
            if viewport is None:
                return None
            return viewport.get_active_body()
        except Exception:
            return None

    def _on_analyze(self):
        """Run the orientation analysis."""
        body = self.body_combo.currentData()
        if body is None:
            return

        self.current_body = body
        material = self.material_combo.currentText()

        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText(tr("Analyzing..."))

        # Disable buttons during analysis
        self.analyze_btn.setEnabled(False)
        self.preview_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)

        # Run analysis (with slight delay for UI update)
        QTimer.singleShot(100, lambda: self._run_analysis(body, material))

    def _run_analysis(self, body, material):
        """Run the actual orientation analysis."""
        try:
            self._clear_preview_overlay()
            from modeling.print_orientation_optimizer import recommend_orientation

            # Run optimization
            self.recommendation = recommend_orientation(body)

            # Update UI with results
            self._display_results()

            # Enable buttons
            self.preview_btn.setEnabled(True)
            self.apply_btn.setEnabled(True)

            self.status_label.setText(tr("Analysis complete"))

        except Exception as e:
            logger.exception(f"Analysis failed: {e}")
            self.status_label.setText(tr("Analysis failed"))
            self.recommendation_label.setText(tr(f"Error: {e}"))

        finally:
            self.progress_bar.setVisible(False)
            self.analyze_btn.setEnabled(True)

    def _display_results(self):
        """Display the analysis results."""
        if not self.recommendation:
            return

        rec = self.recommendation
        best = rec.best
        orig = rec.original or best

        # Update recommendation label
        if rec.best.score < 0.1:
            score_text = tr("Excellent")
        elif rec.best.score < 0.3:
            score_text = tr("Good")
        elif rec.best.score < 0.5:
            score_text = tr("Fair")
        else:
            score_text = tr("Poor")

        self.recommendation_label.setText(
            f"{tr('Recommended')}: {best.description}\n"
            f"{tr('Score')}: {best.score:.3f} ({score_text})"
        )

        # Update comparison table
        self._update_comparison_table(orig.metrics, best.metrics)

        # Update alternatives
        alternatives = []
        for alt in rec.alternatives[:3]:
            alternatives.append(f"• {alt.description}: score={alt.score:.3f}")

        self.alternatives_text.setText("\n".join(alternatives) if alternatives else tr("No alternatives"))

        # Update explanation
        if rec.explanation:
            self.explanation_text.setText(rec.explanation.get_summary())
        else:
            self.explanation_text.setText(tr("No explanation available."))

        # Show results
        self.results_group.setVisible(True)

    def _update_comparison_table(self, before_metrics, after_metrics):
        """Update the comparison table with metrics."""
        if before_metrics is None or after_metrics is None:
            return

        def format_metric(value, unit, is_better_higher=True):
            """Format a metric value with improvement indicator."""
            if unit == "mm":
                text = f"{value:.1f} mm"
            elif unit == "mm²":
                text = f"{value:.0f} mm²"
            elif unit == "mm³":
                text = f"{value:.0f} mm³"
            else:
                text = f"{value:.2f}"

            # TODO: Add improvement arrows for V1
            return text

        # Build height (lower is better)
        self.comparison_table.setItem(0, 2, QTableWidgetItem(
            format_metric(after_metrics.build_height_mm, "mm")
        ))
        self.comparison_table.setItem(0, 1, QTableWidgetItem(
            format_metric(before_metrics.build_height_mm, "mm")
        ))

        # Support volume (lower is better)
        self.comparison_table.setItem(1, 2, QTableWidgetItem(
            format_metric(after_metrics.support_volume_estimate_mm3, "mm³")
        ))
        self.comparison_table.setItem(1, 1, QTableWidgetItem(
            format_metric(before_metrics.support_volume_estimate_mm3, "mm³")
        ))

        # Overhang area (lower is better)
        self.comparison_table.setItem(2, 2, QTableWidgetItem(
            format_metric(after_metrics.overhang_area_mm2, "mm²")
        ))
        self.comparison_table.setItem(2, 1, QTableWidgetItem(
            format_metric(before_metrics.overhang_area_mm2, "mm²")
        ))

        # Base contact (higher is better)
        self.comparison_table.setItem(3, 2, QTableWidgetItem(
            format_metric(after_metrics.base_contact_area_mm2, "mm²", is_better_higher=False)
        ))
        self.comparison_table.setItem(3, 1, QTableWidgetItem(
            format_metric(before_metrics.base_contact_area_mm2, "mm²", is_better_higher=False)
        ))

        # Stability (higher is better)
        self.comparison_table.setItem(4, 2, QTableWidgetItem(
            f"{after_metrics.stability_score:.2f}"
        ))
        self.comparison_table.setItem(4, 1, QTableWidgetItem(
            f"{before_metrics.stability_score:.2f}"
        ))

    def _on_preview(self):
        """Preview the recommended orientation in the viewport."""
        if not self.recommendation or not self.current_body:
            return

        best = self.recommendation.best

        if self._overlay is None:
            self.status_label.setText(tr("Preview overlay unavailable"))
            return

        fin_proposal = None
        solid = getattr(self.current_body, "_build123d_solid", None)
        if solid is not None:
            try:
                from modeling.print_support_fins import analyze_fins

                preview_angle = abs(float(best.angle_deg))
                if preview_angle >= 40.0:
                    fin_proposal = analyze_fins(solid, orientation_angle_deg=preview_angle)
            except Exception as e:
                logger.debug(f"Fin preview analysis failed: {e}")

        shown = self._overlay.show_preview(
            self.current_body,
            best,
            recommendation=self.recommendation,
            fin_proposal=fin_proposal,
        )

        if shown:
            self.status_label.setText(tr("Preview active"))
            logger.info(f"Preview orientation: {best.description}")
        else:
            self.status_label.setText(tr("Preview failed"))

    def _on_apply(self):
        """Apply the recommended orientation as a Transform feature."""
        if not self.recommendation or not self.current_body:
            return

        best = self.recommendation.best

        try:
            from modeling import TransformFeature
            from gui.commands.feature_commands import AddFeatureCommand

            # Create the rotation feature
            feature = TransformFeature(
                name=f"Print Rotate: {best.description}",
                mode="rotate",
                data={
                    "axis": list(best.axis),  # OCP expects list, not tuple
                    "angle": best.angle_deg,
                    "center": [0.0, 0.0, 0.0]  # Rotate around origin
                }
            )

            # Add feature via command for undo/redo support
            cmd = AddFeatureCommand(
                self.current_body,
                feature,
                self.main_window.undo_stack,
                self.main_window.browser
            )
            cmd.redo()

            # Update viewport
            self.main_window._update_viewport_all_impl()
            self.main_window.browser.refresh()

            logger.info(f"Applied print orientation: {best.description} ({best.angle_deg}°)")
            self.status_label.setText(tr("Orientation applied"))

        except Exception as e:
            logger.exception(f"Failed to apply orientation: {e}")
            self.status_label.setText(tr("Error: {error}").format(error=str(e)))
            return

        # Close dialog
        self.accept()

    def _clear_preview_overlay(self):
        """Clear any active viewport preview overlay."""
        if self._overlay is not None:
            self._overlay.clear()

    def reject(self):
        """Ensure viewport preview state is cleaned up on cancel."""
        self._clear_preview_overlay()
        super().reject()

    def accept(self):
        """Ensure viewport preview state is cleaned up on close."""
        self._clear_preview_overlay()
        super().accept()


def show_print_optimize_dialog(main_window):
    """
    Show the print optimization dialog.

    Args:
        main_window: MainWindow instance

    Returns:
        Dialog result code (QDialog.Accepted or Rejected)
    """
    dialog = PrintOptimizeDialog(main_window, main_window)
    return dialog.exec()
