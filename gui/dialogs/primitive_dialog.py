"""
MashCad - Primitive Dialog
Create Box, Cylinder, Sphere, Cone as new bodies.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QGroupBox, QStackedWidget
)
from PySide6.QtGui import QDoubleValidator
from loguru import logger
from gui.design_tokens import DesignTokens
from i18n import tr


def _num_row(label_text, default, parent_layout, unit="mm", min_val=0.1, max_val=10000):
    """Create a labeled number input row, return the QLineEdit."""
    row = QHBoxLayout()
    lbl = QLabel(label_text)
    lbl.setMinimumWidth(100)
    row.addWidget(lbl)
    inp = QLineEdit(str(default))
    v = QDoubleValidator(min_val, max_val, 3)
    v.setNotation(QDoubleValidator.StandardNotation)
    inp.setValidator(v)
    row.addWidget(inp)
    row.addWidget(QLabel(unit))
    parent_layout.addLayout(row)
    return inp


class PrimitiveDialog(QDialog):
    """Dialog to create primitive solids: Box, Cylinder, Sphere, Cone."""

    def __init__(self, primitive_type="box", parent=None):
        super().__init__(parent)
        self.primitive_type = primitive_type
        titles = {"box": tr("Box"), "cylinder": tr("Cylinder"), "sphere": tr("Sphere"), "cone": tr("Cone")}
        self.setWindowTitle(f"{tr('Create')} {titles.get(primitive_type, tr('Primitive'))}")
        self.setMinimumWidth(380)
        self.setStyleSheet(DesignTokens.stylesheet_dialog())
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Type selector
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel(tr("Type:")))
        self.type_combo = QComboBox()
        self.type_combo.addItems([tr("Box"), tr("Cylinder"), tr("Sphere"), tr("Cone")])
        type_map = {"box": 0, "cylinder": 1, "sphere": 2, "cone": 3}
        self.type_combo.setCurrentIndex(type_map.get(self.primitive_type, 0))
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_row.addWidget(self.type_combo)
        type_row.addStretch()
        layout.addLayout(type_row)

        # Stacked parameter pages
        self.stack = QStackedWidget()

        # Page 0: Box
        box_page = QGroupBox(tr("Box Parameters"))
        box_layout = QVBoxLayout()
        self.box_length = _num_row(tr("Length:"), 20, box_layout)
        self.box_width = _num_row(tr("Width:"), 20, box_layout)
        self.box_height = _num_row(tr("Height:"), 20, box_layout)
        box_page.setLayout(box_layout)
        self.stack.addWidget(box_page)

        # Page 1: Cylinder
        cyl_page = QGroupBox(tr("Cylinder Parameters"))
        cyl_layout = QVBoxLayout()
        self.cyl_radius = _num_row(tr("Radius:"), 10, cyl_layout)
        self.cyl_height = _num_row(tr("Height:"), 30, cyl_layout)
        cyl_page.setLayout(cyl_layout)
        self.stack.addWidget(cyl_page)

        # Page 2: Sphere
        sph_page = QGroupBox(tr("Sphere Parameters"))
        sph_layout = QVBoxLayout()
        self.sph_radius = _num_row(tr("Radius:"), 10, sph_layout)
        sph_page.setLayout(sph_layout)
        self.stack.addWidget(sph_page)

        # Page 3: Cone
        cone_page = QGroupBox(tr("Cone Parameters"))
        cone_layout = QVBoxLayout()
        self.cone_bottom_radius = _num_row(tr("Bottom Radius:"), 10, cone_layout)
        self.cone_top_radius = _num_row(tr("Top Radius:"), 0, cone_layout, min_val=0.0)
        self.cone_height = _num_row(tr("Height:"), 20, cone_layout)
        cone_page.setLayout(cone_layout)
        self.stack.addWidget(cone_page)

        self.stack.setCurrentIndex(type_map.get(self.primitive_type, 0))
        layout.addWidget(self.stack)

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

    def _on_type_changed(self, index):
        self.stack.setCurrentIndex(index)

    def _on_create(self):
        try:
            idx = self.type_combo.currentIndex()
            self.result_type = ["box", "cylinder", "sphere", "cone"][idx]

            if self.result_type == "box":
                self.length = float(self.box_length.text() or "20")
                self.width = float(self.box_width.text() or "20")
                self.height = float(self.box_height.text() or "20")
                if self.length <= 0 or self.width <= 0 or self.height <= 0:
                    logger.warning("All dimensions must be > 0")
                    return
            elif self.result_type == "cylinder":
                self.radius = float(self.cyl_radius.text() or "10")
                self.height = float(self.cyl_height.text() or "30")
                if self.radius <= 0 or self.height <= 0:
                    logger.warning("Radius and height must be > 0")
                    return
            elif self.result_type == "sphere":
                self.radius = float(self.sph_radius.text() or "10")
                if self.radius <= 0:
                    logger.warning("Radius must be > 0")
                    return
            elif self.result_type == "cone":
                self.bottom_radius = float(self.cone_bottom_radius.text() or "10")
                self.top_radius = float(self.cone_top_radius.text() or "0")
                self.height = float(self.cone_height.text() or "20")
                if self.bottom_radius <= 0 or self.top_radius < 0 or self.height <= 0:
                    logger.warning("Invalid cone dimensions")
                    return

            self.accept()
        except ValueError as e:
            logger.error(f"Invalid input: {e}")
