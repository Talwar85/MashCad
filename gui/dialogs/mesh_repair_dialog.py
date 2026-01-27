"""
MashCad - Mesh Repair Dialog
Diagnose and repair geometry issues.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGroupBox, QTextEdit, QCheckBox
)
from PySide6.QtGui import QDoubleValidator
from loguru import logger
from gui.design_tokens import DesignTokens
from i18n import tr


class MeshRepairDialog(QDialog):
    """Dialog for geometry repair and ShrinkWrap."""

    def __init__(self, body, parent=None):
        super().__init__(parent)
        self.body = body
        self.repaired_solid = None
        self.setWindowTitle(f"{tr('Mesh Repair')} - {body.name}")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Diagnose
        diag_group = QGroupBox(tr("Diagnose"))
        diag_layout = QVBoxLayout()

        diag_btn = QPushButton(tr("Run Diagnosis"))
        diag_btn.clicked.connect(self._on_diagnose)
        diag_layout.addWidget(diag_btn)

        self.diag_text = QTextEdit()
        self.diag_text.setReadOnly(True)
        self.diag_text.setMaximumHeight(80)
        self.diag_text.setStyleSheet(
            "background: #1e1e1e; color: #ddd; border: 1px solid #3f3f46; "
            "border-radius: 4px; font-family: Consolas, monospace; font-size: 12px;"
        )
        diag_layout.addWidget(self.diag_text)

        diag_group.setLayout(diag_layout)
        layout.addWidget(diag_group)

        # Repair options
        repair_group = QGroupBox(tr("Repair"))
        repair_layout = QVBoxLayout()

        # Tolerance
        tol_row = QHBoxLayout()
        tlbl = QLabel(tr("Sew Tolerance:"))
        tlbl.setMinimumWidth(130)
        tol_row.addWidget(tlbl)
        self.tol_input = QLineEdit("0.001")
        v = QDoubleValidator(0.0001, 1.0, 4)
        v.setNotation(QDoubleValidator.StandardNotation)
        self.tol_input.setValidator(v)
        tol_row.addWidget(self.tol_input)
        tol_row.addWidget(QLabel("mm"))
        repair_layout.addLayout(tol_row)

        # Options
        self.fix_solid_check = QCheckBox(tr("Fix solid topology"))
        self.fix_solid_check.setChecked(True)
        repair_layout.addWidget(self.fix_solid_check)

        self.unify_check = QCheckBox(tr("Unify same-domain faces"))
        self.unify_check.setChecked(True)
        repair_layout.addWidget(self.unify_check)

        # Repair button
        repair_btn_row = QHBoxLayout()
        repair_btn = QPushButton(tr("Repair"))
        repair_btn.clicked.connect(self._on_repair)
        repair_btn.setObjectName("primary")
        repair_btn_row.addWidget(repair_btn)

        shrinkwrap_btn = QPushButton(tr("ShrinkWrap"))
        shrinkwrap_btn.clicked.connect(self._on_shrinkwrap)
        repair_btn_row.addWidget(shrinkwrap_btn)
        repair_layout.addLayout(repair_btn_row)

        repair_group.setLayout(repair_layout)
        layout.addWidget(repair_group)

        # Results
        result_group = QGroupBox(tr("Results"))
        result_layout = QVBoxLayout()
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet(
            "background: #1e1e1e; color: #ddd; border: 1px solid #3f3f46; "
            "border-radius: 4px; font-family: Consolas, monospace; font-size: 12px;"
        )
        result_layout.addWidget(self.result_text)
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)

        # Buttons
        btn_layout = QHBoxLayout()
        apply_btn = QPushButton(tr("Apply Repair"))
        apply_btn.clicked.connect(self._on_apply)
        close_btn = QPushButton(tr("Close"))
        close_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(apply_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self.setStyleSheet(DesignTokens.stylesheet_dialog())

    def _on_diagnose(self):
        solid = self.body._build123d_solid
        if solid is None:
            self.diag_text.setPlainText(tr("No solid geometry on this body."))
            return

        from modeling.mesh_repair import MeshRepair
        result = MeshRepair.diagnose(solid)
        color = "#4ec9b0" if result.success else "#f44747"
        self.diag_text.setPlainText(result.message)
        self.diag_text.setStyleSheet(
            f"background: #1e1e1e; color: {color}; border: 1px solid #3f3f46; "
            "border-radius: 4px; font-family: Consolas, monospace; font-size: 12px;"
        )

    def _on_repair(self):
        solid = self.body._build123d_solid
        if solid is None:
            self.result_text.setPlainText(tr("No solid geometry on this body."))
            return

        self.result_text.setPlainText(tr("Repairing..."))
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            tol = float(self.tol_input.text() or "0.001")
        except ValueError:
            tol = 0.001

        from modeling.mesh_repair import MeshRepair
        result = MeshRepair.repair(
            solid,
            sew_tolerance=tol,
            fix_solid=self.fix_solid_check.isChecked(),
            unify_faces=self.unify_check.isChecked(),
        )

        self.result_text.setPlainText(result.message)
        if result.repaired_solid:
            self.repaired_solid = result.repaired_solid

    def _on_shrinkwrap(self):
        solid = self.body._build123d_solid
        if solid is None:
            self.result_text.setPlainText(tr("No solid geometry on this body."))
            return

        self.result_text.setPlainText(tr("ShrinkWrap running..."))
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        from modeling.mesh_repair import MeshRepair
        result = MeshRepair.shrinkwrap(solid)

        self.result_text.setPlainText(result.message)
        if result.repaired_solid:
            self.repaired_solid = result.repaired_solid

    def _on_apply(self):
        if self.repaired_solid is None:
            self.result_text.setPlainText(tr("No repair result to apply."))
            return
        self.accept()
