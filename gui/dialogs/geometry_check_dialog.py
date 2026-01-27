"""
MashCad - Geometry Check & Heal Dialog
Validate geometry and auto-heal issues.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QTextEdit, QComboBox
)
from PySide6.QtCore import Qt
from loguru import logger
from gui.design_tokens import DesignTokens
from i18n import tr


class GeometryCheckDialog(QDialog):
    """Dialog to validate and heal body geometry."""

    def __init__(self, body, parent=None):
        super().__init__(parent)
        self.body = body
        self.healed_solid = None
        self.setWindowTitle(f"{tr('Geometry Check')} - {body.name}")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self._setup_ui()
        self._run_validation()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Info
        info = QLabel(f"<b>{self.body.name}</b>")
        info.setStyleSheet("color: #ddd; padding: 8px; background: #1e1e1e; border-radius: 4px;")
        layout.addWidget(info)

        # Validation results
        val_group = QGroupBox(tr("Validation Results"))
        val_layout = QVBoxLayout()
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet(
            "background: #1e1e1e; color: #ddd; border: 1px solid #3f3f46; "
            "border-radius: 4px; font-family: Consolas, monospace; font-size: 12px;"
        )
        val_layout.addWidget(self.result_text)
        val_group.setLayout(val_layout)
        layout.addWidget(val_group)

        # Heal controls
        heal_group = QGroupBox(tr("Auto-Heal"))
        heal_layout = QVBoxLayout()

        strategy_row = QHBoxLayout()
        strategy_row.addWidget(QLabel(tr("Strategy:")))
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems([tr("Combined (Auto)"), tr("Shape Fix"), tr("Solid Fix"), tr("Sewing"), tr("Tolerance")])
        strategy_row.addWidget(self.strategy_combo)
        strategy_row.addStretch()
        heal_layout.addLayout(strategy_row)

        heal_btn = QPushButton(tr("Heal Geometry"))
        heal_btn.clicked.connect(self._on_heal)
        heal_btn.setStyleSheet(
            "QPushButton { background: #d4a017; color: white; border: none; "
            "padding: 8px 20px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #e0b020; }"
        )
        heal_layout.addWidget(heal_btn)

        heal_group.setLayout(heal_layout)
        layout.addWidget(heal_group)

        # Buttons
        btn_layout = QHBoxLayout()
        close_btn = QPushButton(tr("Close"))
        close_btn.clicked.connect(self.reject)

        self.apply_btn = QPushButton(tr("Apply Healed"))
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.accept)
        self.apply_btn.setObjectName("primary")

        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        btn_layout.addWidget(self.apply_btn)
        layout.addLayout(btn_layout)

        # Dark theme
        self.setStyleSheet(DesignTokens.stylesheet_dialog())

    def _run_validation(self):
        """Run geometry validation on the body."""
        solid = self.body._build123d_solid
        if solid is None:
            self.result_text.setPlainText(tr("No solid geometry on this body."))
            return

        try:
            from modeling.geometry_validator import GeometryValidator, ValidationLevel
            result = GeometryValidator.validate_solid(solid, ValidationLevel.FULL)

            lines = []
            lines.append(f"Status: {result.status.value.upper()}")
            lines.append(f"Message: {result.message}")
            if result.details:
                lines.append(f"\nDetails:")
                if isinstance(result.details, dict):
                    for k, v in result.details.items():
                        lines.append(f"  {k}: {v}")
                else:
                    lines.append(f"  {result.details}")
            if result.issues:
                lines.append(f"\nIssues ({len(result.issues)}):")
                for issue in result.issues:
                    lines.append(f"  - {issue}")

            self.result_text.setPlainText("\n".join(lines))

            # Color-code status
            color = {"valid": "#4ec9b0", "warning": "#dcdcaa", "invalid": "#f44747", "error": "#f44747"}
            status_color = color.get(result.status.value, "#ddd")
            self.result_text.setStyleSheet(
                f"background: #1e1e1e; color: {status_color}; border: 1px solid #3f3f46; "
                "border-radius: 4px; font-family: Consolas, monospace; font-size: 12px;"
            )
        except Exception as e:
            self.result_text.setPlainText(f"Validation error: {e}")
            logger.error(f"Geometry validation failed: {e}")

    def _on_heal(self):
        """Attempt to heal the geometry."""
        solid = self.body._build123d_solid
        if solid is None:
            return

        try:
            from modeling.geometry_healer import GeometryHealer, HealingStrategy

            strategy_map = {
                0: HealingStrategy.COMBINED,
                1: HealingStrategy.SHAPE_FIX,
                2: HealingStrategy.SOLID_FIX,
                3: HealingStrategy.SEWING,
                4: HealingStrategy.TOLERANCE,
            }
            strategy = strategy_map.get(self.strategy_combo.currentIndex(), HealingStrategy.COMBINED)

            healed_solid, result = GeometryHealer.heal_solid(solid, strategy)

            lines = [self.result_text.toPlainText(), "", "--- Healing Result ---"]
            lines.append(f"Success: {result.success}")
            lines.append(f"Strategy: {result.strategy_used.name if result.strategy_used else 'None'}")
            lines.append(f"Message: {result.message}")
            if result.changes_made:
                lines.append("Changes:")
                for c in result.changes_made:
                    lines.append(f"  - {c}")

            self.result_text.setPlainText("\n".join(lines))

            if result.success and healed_solid is not None:
                self.healed_solid = healed_solid
                self.apply_btn.setEnabled(True)
                logger.success(f"Geometry healed: {result.message}")
            else:
                logger.warning(f"Healing unsuccessful: {result.message}")
        except Exception as e:
            self.result_text.append(f"\nHealing error: {e}")
            logger.error(f"Geometry healing failed: {e}")
