"""
MashCad - N-Sided Patch Dialog
Create a smooth surface filling N boundary edges (xNURBS alternative).
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGroupBox, QCheckBox, QSpinBox, QTextEdit
)
from PySide6.QtGui import QDoubleValidator
from loguru import logger
from gui.design_tokens import DesignTokens
from i18n import tr


class NSidedPatchDialog(QDialog):
    """Dialog to configure N-Sided Patch parameters."""

    def __init__(self, body, viewport, parent=None):
        super().__init__(parent)
        self.body = body
        self.viewport = viewport
        self.selected_edges = []
        self.setWindowTitle(tr("N-Sided Patch"))
        self.setMinimumWidth(450)
        self.setMinimumHeight(350)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Edge selection
        sel_group = QGroupBox(tr("Edge Selection"))
        sel_layout = QVBoxLayout()

        sel_layout.addWidget(QLabel(
            tr("Select boundary edges in the viewport, then click 'Fill'.")
        ))

        self.edge_count_label = QLabel(tr("Selected edges: 0"))
        sel_layout.addWidget(self.edge_count_label)

        sel_group.setLayout(sel_layout)
        layout.addWidget(sel_group)

        # Parameters
        param_group = QGroupBox(tr("Parameters"))
        param_layout = QVBoxLayout()

        # Degree
        deg_row = QHBoxLayout()
        dlbl = QLabel(tr("Surface Degree:"))
        dlbl.setMinimumWidth(140)
        deg_row.addWidget(dlbl)
        self.degree_spin = QSpinBox()
        self.degree_spin.setRange(2, 6)
        self.degree_spin.setValue(3)
        deg_row.addWidget(self.degree_spin)
        deg_row.addStretch()
        param_layout.addLayout(deg_row)

        # Tangency
        self.tangent_check = QCheckBox(tr("Match tangency (G1) with adjacent faces"))
        self.tangent_check.setChecked(True)
        param_layout.addWidget(self.tangent_check)

        param_group.setLayout(param_layout)
        layout.addWidget(param_group)

        # Fill button
        fill_btn = QPushButton(tr("Fill"))
        fill_btn.clicked.connect(self._on_fill)
        fill_btn.setObjectName("primary")
        layout.addWidget(fill_btn)

        # Results
        result_group = QGroupBox(tr("Results"))
        result_layout = QVBoxLayout()
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(80)
        self.result_text.setStyleSheet(
            "background: #1e1e1e; color: #ddd; border: 1px solid #3f3f46; "
            "border-radius: 4px; font-family: Consolas, monospace; font-size: 12px;"
        )
        result_layout.addWidget(self.result_text)
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)

        # Close
        btn_layout = QHBoxLayout()
        close_btn = QPushButton(tr("Close"))
        close_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self.setStyleSheet(DesignTokens.stylesheet_dialog())

    def set_selected_edges(self, edges):
        """Update selected edge count from viewport."""
        self.selected_edges = edges
        self.edge_count_label.setText(f"{tr('Selected edges')}: {len(edges)}")

    def _on_fill(self):
        solid = self.body._build123d_solid
        if solid is None:
            self.result_text.setPlainText(tr("No solid geometry on this body."))
            return

        if len(self.selected_edges) < 3:
            self.result_text.setPlainText(
                tr("Select at least 3 boundary edges.")
            )
            return

        self.result_text.setPlainText(tr("Computing..."))
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            from modeling.nsided_patch import NSidedPatch

            result = NSidedPatch.fill_edges(
                self.selected_edges,
                tangent_faces=NSidedPatch._find_adjacent_faces(
                    solid, self.selected_edges
                ) if self.tangent_check.isChecked() else None,
                degree=self.degree_spin.value(),
            )

            if result is not None:
                self.result_text.setPlainText(
                    f"N-Sided Patch {tr('created successfully')}.\n"
                    f"{tr('Edges')}: {len(self.selected_edges)}, "
                    f"{tr('Degree')}: {self.degree_spin.value()}"
                )
                self.patch_result = result
            else:
                self.result_text.setPlainText(tr("Patch creation failed."))

        except Exception as e:
            self.result_text.setPlainText(f"{tr('Error')}: {e}")
            logger.error(f"N-Sided Patch dialog error: {e}")
