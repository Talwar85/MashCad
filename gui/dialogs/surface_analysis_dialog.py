"""
MashCad - Surface Analysis Dialog
Curvature, Draft Angle, and Zebra Stripe analysis with live viewport coloring.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QGroupBox, QTextEdit, QSlider
)
from PySide6.QtCore import Qt
from loguru import logger
from gui.design_tokens import DesignTokens
from i18n import tr


class SurfaceAnalysisDialog(QDialog):
    """Dialog for surface analysis with live viewport preview."""

    def __init__(self, body, viewport, parent=None):
        super().__init__(parent)
        self.body = body
        self.viewport = viewport
        self.setWindowTitle(f"{tr('Surface Analysis')} - {body.name}")
        self.setMinimumWidth(450)
        self.setMinimumHeight(350)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Analysis type
        type_group = QGroupBox(tr("Analysis Type"))
        type_layout = QVBoxLayout()

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel(tr("Mode:")))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            tr("Curvature (Mean)"),
            tr("Curvature (Gaussian)"),
            tr("Curvature (Max)"),
            tr("Curvature (Min)"),
            tr("Draft Angle"),
            tr("Zebra Stripes"),
        ])
        type_row.addWidget(self.mode_combo)
        type_row.addStretch()
        type_layout.addLayout(type_row)

        # Draft angle pull direction
        self.pull_row = QHBoxLayout()
        self.pull_label = QLabel(tr("Pull Direction:"))
        self.pull_row.addWidget(self.pull_label)
        self.pull_combo = QComboBox()
        self.pull_combo.addItems([
            "Z (Up)", "Y (Front)", "X (Right)",
            "-Z (Down)", "-Y (Back)", "-X (Left)"
        ])
        self.pull_row.addWidget(self.pull_combo)
        self.pull_row.addStretch()
        type_layout.addLayout(self.pull_row)

        # Zebra stripe count
        self.stripe_row = QHBoxLayout()
        self.stripe_label = QLabel(tr("Stripe Count:"))
        self.stripe_row.addWidget(self.stripe_label)
        self.stripe_slider = QSlider(Qt.Horizontal)
        self.stripe_slider.setRange(5, 60)
        self.stripe_slider.setValue(20)
        self.stripe_count_label = QLabel("20")
        self.stripe_slider.valueChanged.connect(
            lambda v: self.stripe_count_label.setText(str(v))
        )
        self.stripe_row.addWidget(self.stripe_slider)
        self.stripe_row.addWidget(self.stripe_count_label)
        type_layout.addLayout(self.stripe_row)

        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        type_group.setLayout(type_layout)
        layout.addWidget(type_group)

        # Apply button
        apply_btn = QPushButton(tr("Apply Analysis"))
        apply_btn.clicked.connect(self._on_apply)
        apply_btn.setObjectName("primary")
        layout.addWidget(apply_btn)

        # Results
        result_group = QGroupBox(tr("Results"))
        result_layout = QVBoxLayout()
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(100)
        self.result_text.setStyleSheet(
            "background: #1e1e1e; color: #ddd; border: 1px solid #3f3f46; "
            "border-radius: 4px; font-family: Consolas, monospace; font-size: 12px;"
        )
        result_layout.addWidget(self.result_text)
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)

        # Buttons
        btn_layout = QHBoxLayout()
        clear_btn = QPushButton(tr("Clear Analysis"))
        clear_btn.clicked.connect(self._on_clear)

        close_btn = QPushButton(tr("Close"))
        close_btn.clicked.connect(self._on_close)

        btn_layout.addStretch()
        btn_layout.addWidget(clear_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self.setStyleSheet(DesignTokens.stylesheet_dialog())
        self._on_mode_changed(0)

    def _on_mode_changed(self, index):
        is_draft = (index == 4)
        is_zebra = (index == 5)
        self.pull_label.setVisible(is_draft)
        self.pull_combo.setVisible(is_draft)
        self.stripe_label.setVisible(is_zebra)
        self.stripe_slider.setVisible(is_zebra)
        self.stripe_count_label.setVisible(is_zebra)

    def _on_apply(self):
        solid = self.body._build123d_solid
        mesh = self.viewport.get_body_mesh(self.body.id)
        if solid is None or mesh is None:
            self.result_text.setPlainText(tr("No solid geometry on this body."))
            return

        from modeling.surface_analyzer import SurfaceAnalyzer

        mode = self.mode_combo.currentIndex()
        result = None

        if mode <= 3:
            # Curvature
            curv_types = ["mean", "gauss", "maximum", "minimum"]
            result = SurfaceAnalyzer.curvature_analysis(solid, mesh, curv_types[mode])
        elif mode == 4:
            # Draft angle
            pull_map = {
                0: (0, 0, 1), 1: (0, 1, 0), 2: (1, 0, 0),
                3: (0, 0, -1), 4: (0, -1, 0), 5: (-1, 0, 0),
            }
            pull = pull_map.get(self.pull_combo.currentIndex(), (0, 0, 1))
            result = SurfaceAnalyzer.draft_angle_analysis(solid, mesh, pull)
        elif mode == 5:
            # Zebra
            result = SurfaceAnalyzer.zebra_stripes(mesh, stripe_count=self.stripe_slider.value())

        if result and result.scalars is not None:
            self.viewport.show_scalar_analysis(
                self.body.id, result.scalars,
                scalar_name=result.scalar_name,
                cmap=result.cmap, clim=result.clim,
            )
            self.result_text.setPlainText(result.message)
        else:
            msg = result.message if result else "Analysis returned no data"
            self.result_text.setPlainText(msg)

    def _on_clear(self):
        self.viewport.clear_analysis(self.body.id)
        self.result_text.setPlainText(tr("Analysis cleared."))

    def _on_close(self):
        self.reject()
