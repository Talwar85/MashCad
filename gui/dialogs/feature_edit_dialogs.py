"""
MashCad - Feature Edit Dialogs
Parametrisches Editieren von Features nach Erstellung.

Unterstuetzte Feature-Typen:
- ExtrudeFeature: Distance, Direction, Operation
- FilletFeature: Radius
- ChamferFeature: Distance
- ShellFeature: Thickness
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QGroupBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from loguru import logger
from gui.design_tokens import DesignTokens
from i18n import tr


def _create_number_input(label_text, parent_layout, suffix=""):
    """Helper: Label + QLineEdit fuer Zahlen"""
    row = QHBoxLayout()
    label = QLabel(label_text)
    label.setMinimumWidth(100)
    row.addWidget(label)

    line_edit = QLineEdit()
    validator = QDoubleValidator()
    validator.setNotation(QDoubleValidator.StandardNotation)
    line_edit.setValidator(validator)
    row.addWidget(line_edit)

    if suffix:
        suffix_label = QLabel(suffix)
        suffix_label.setStyleSheet("color: #999;")
        row.addWidget(suffix_label)

    parent_layout.addLayout(row)
    return line_edit


def _create_buttons(layout, dialog):
    """Helper: Cancel + Apply buttons"""
    button_layout = QHBoxLayout()

    cancel_btn = QPushButton(tr("Cancel"))
    cancel_btn.clicked.connect(dialog.reject)

    apply_btn = QPushButton(tr("Apply"))
    apply_btn.setDefault(True)
    apply_btn.setObjectName("primary")

    button_layout.addStretch()
    button_layout.addWidget(cancel_btn)
    button_layout.addWidget(apply_btn)

    layout.addSpacing(20)
    layout.addLayout(button_layout)
    return apply_btn


class ExtrudeEditDialog(QDialog):
    """Edit-Dialog fuer ExtrudeFeature: Distance, Direction, Operation"""

    def __init__(self, feature, body, parent=None):
        super().__init__(parent)
        self.feature = feature
        self.body = body
        self.setWindowTitle(f"Edit {feature.name}")
        self.setMinimumWidth(400)
        self.setStyleSheet(DesignTokens.stylesheet_dialog())

        layout = QVBoxLayout(self)

        # Info-Header
        info = QLabel(f"<b>{feature.name}</b><br>Body: {body.name}")
        info.setStyleSheet("color: #ddd; padding: 10px; background: #1e1e1e; border-radius: 4px;")
        layout.addWidget(info)

        # Parameters
        group = QGroupBox(tr("Extrude Parameters"))
        group_layout = QVBoxLayout()

        self.distance_input = _create_number_input(tr("Distance:"), group_layout, "mm")
        self.distance_input.setText(str(feature.distance))

        # Direction
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel(tr("Direction:")))
        self.dir_combo = QComboBox()
        self.dir_combo.addItems([tr("Normal"), tr("Reverse")])
        self.dir_combo.setCurrentIndex(0 if feature.direction == 1 else 1)
        dir_layout.addWidget(self.dir_combo)
        dir_layout.addStretch()
        group_layout.addLayout(dir_layout)

        # Operation
        op_layout = QHBoxLayout()
        op_layout.addWidget(QLabel(tr("Operation:")))
        self.op_combo = QComboBox()
        self.op_combo.addItems([tr("New Body"), tr("Join"), tr("Cut"), tr("Intersect")])
        self.op_combo.setCurrentText(feature.operation)
        op_layout.addWidget(self.op_combo)
        op_layout.addStretch()
        group_layout.addLayout(op_layout)

        group.setLayout(group_layout)
        layout.addWidget(group)

        apply_btn = _create_buttons(layout, self)
        apply_btn.clicked.connect(self._on_apply)

    def _on_apply(self):
        try:
            distance = float(self.distance_input.text() or "10")
            if distance <= 0:
                logger.warning("Distance must be > 0")
                return
            self.feature.distance = distance
            self.feature.direction = 1 if self.dir_combo.currentIndex() == 0 else -1
            self.feature.operation = self.op_combo.currentText()
            self.accept()
        except ValueError as e:
            logger.error(f"Ungueltige Eingabe: {e}")

    def get_old_data(self):
        return {
            'distance': self.feature.distance,
            'direction': self.feature.direction,
            'operation': self.feature.operation,
        }


class FilletEditDialog(QDialog):
    """Edit-Dialog fuer FilletFeature: Radius"""

    def __init__(self, feature, body, parent=None):
        super().__init__(parent)
        self.feature = feature
        self.body = body
        self.setWindowTitle(f"Edit {feature.name}")
        self.setMinimumWidth(350)
        self.setStyleSheet(DesignTokens.stylesheet_dialog())

        layout = QVBoxLayout(self)

        info = QLabel(f"<b>{feature.name}</b><br>Body: {body.name}")
        info.setStyleSheet("color: #ddd; padding: 10px; background: #1e1e1e; border-radius: 4px;")
        layout.addWidget(info)

        group = QGroupBox(tr("Fillet Parameters"))
        group_layout = QVBoxLayout()

        self.radius_input = _create_number_input(tr("Radius:"), group_layout, "mm")
        self.radius_input.setText(str(feature.radius))

        # Edge count info (read-only)
        n_edges = len(feature.edge_selectors) if feature.edge_selectors else 0
        if feature.geometric_selectors:
            n_edges = max(n_edges, len(feature.geometric_selectors))
        edge_info = QLabel(f"Edges: {n_edges}")
        edge_info.setStyleSheet("color: #999; font-size: 11px; font-style: italic;")
        group_layout.addWidget(edge_info)

        group.setLayout(group_layout)
        layout.addWidget(group)

        apply_btn = _create_buttons(layout, self)
        apply_btn.clicked.connect(self._on_apply)

    def _on_apply(self):
        try:
            radius = float(self.radius_input.text() or "2")
            if radius <= 0:
                logger.warning("Radius must be > 0")
                return
            self.feature.radius = radius
            self.accept()
        except ValueError as e:
            logger.error(f"Ungueltige Eingabe: {e}")


class ChamferEditDialog(QDialog):
    """Edit-Dialog fuer ChamferFeature: Distance"""

    def __init__(self, feature, body, parent=None):
        super().__init__(parent)
        self.feature = feature
        self.body = body
        self.setWindowTitle(f"Edit {feature.name}")
        self.setMinimumWidth(350)
        self.setStyleSheet(DesignTokens.stylesheet_dialog())

        layout = QVBoxLayout(self)

        info = QLabel(f"<b>{feature.name}</b><br>Body: {body.name}")
        info.setStyleSheet("color: #ddd; padding: 10px; background: #1e1e1e; border-radius: 4px;")
        layout.addWidget(info)

        group = QGroupBox(tr("Chamfer Parameters"))
        group_layout = QVBoxLayout()

        self.distance_input = _create_number_input(tr("Distance:"), group_layout, "mm")
        self.distance_input.setText(str(feature.distance))

        n_edges = len(feature.edge_selectors) if feature.edge_selectors else 0
        if feature.geometric_selectors:
            n_edges = max(n_edges, len(feature.geometric_selectors))
        edge_info = QLabel(f"Edges: {n_edges}")
        edge_info.setStyleSheet("color: #999; font-size: 11px; font-style: italic;")
        group_layout.addWidget(edge_info)

        group.setLayout(group_layout)
        layout.addWidget(group)

        apply_btn = _create_buttons(layout, self)
        apply_btn.clicked.connect(self._on_apply)

    def _on_apply(self):
        try:
            distance = float(self.distance_input.text() or "2")
            if distance <= 0:
                logger.warning("Distance must be > 0")
                return
            self.feature.distance = distance
            self.accept()
        except ValueError as e:
            logger.error(f"Ungueltige Eingabe: {e}")


class ShellEditDialog(QDialog):
    """Edit-Dialog fuer ShellFeature: Thickness"""

    def __init__(self, feature, body, parent=None):
        super().__init__(parent)
        self.feature = feature
        self.body = body
        self.setWindowTitle(f"Edit {feature.name}")
        self.setMinimumWidth(350)
        self.setStyleSheet(DesignTokens.stylesheet_dialog())

        layout = QVBoxLayout(self)

        info = QLabel(f"<b>{feature.name}</b><br>Body: {body.name}")
        info.setStyleSheet("color: #ddd; padding: 10px; background: #1e1e1e; border-radius: 4px;")
        layout.addWidget(info)

        group = QGroupBox(tr("Shell Parameters"))
        group_layout = QVBoxLayout()

        self.thickness_input = _create_number_input(tr("Thickness:"), group_layout, "mm")
        self.thickness_input.setText(str(feature.thickness))

        n_faces = len(feature.opening_face_selectors) if feature.opening_face_selectors else 0
        face_info = QLabel(f"Opening faces: {n_faces}")
        face_info.setStyleSheet("color: #999; font-size: 11px; font-style: italic;")
        group_layout.addWidget(face_info)

        group.setLayout(group_layout)
        layout.addWidget(group)

        apply_btn = _create_buttons(layout, self)
        apply_btn.clicked.connect(self._on_apply)

    def _on_apply(self):
        try:
            thickness = float(self.thickness_input.text() or "2")
            if thickness <= 0:
                logger.warning("Thickness must be > 0")
                return
            self.feature.thickness = thickness
            self.accept()
        except ValueError as e:
            logger.error(f"Ungueltige Eingabe (Shell): {e}")


class RevolveEditDialog(QDialog):
    """Edit-Dialog fuer RevolveFeature: Angle, Axis, Operation"""

    def __init__(self, feature, body, parent=None):
        super().__init__(parent)
        self.feature = feature
        self.body = body
        self.setWindowTitle(f"Edit {feature.name}")
        self.setMinimumWidth(400)
        self.setStyleSheet(DesignTokens.stylesheet_dialog())

        layout = QVBoxLayout(self)

        info = QLabel(f"<b>{feature.name}</b><br>Body: {body.name}")
        info.setStyleSheet("color: #ddd; padding: 10px; background: #1e1e1e; border-radius: 4px;")
        layout.addWidget(info)

        group = QGroupBox(tr("Revolve Parameters"))
        group_layout = QVBoxLayout()

        # Axis
        axis_row = QHBoxLayout()
        axis_label = QLabel(tr("Axis:"))
        axis_label.setMinimumWidth(100)
        axis_row.addWidget(axis_label)
        self.axis_combo = QComboBox()
        self.axis_combo.addItems(["X", "Y", "Z"])
        axis_map = {(1, 0, 0): "X", (0, 1, 0): "Y", (0, 0, 1): "Z"}
        current_axis = axis_map.get(tuple(feature.axis), "Y")
        self.axis_combo.setCurrentText(current_axis)
        axis_row.addWidget(self.axis_combo)
        axis_row.addStretch()
        group_layout.addLayout(axis_row)

        # Angle
        self.angle_input = _create_number_input(tr("Angle:"), group_layout, "deg")
        self.angle_input.setText(str(feature.angle))

        # Operation
        op_layout = QHBoxLayout()
        op_layout.addWidget(QLabel(tr("Operation:")))
        self.op_combo = QComboBox()
        self.op_combo.addItems([tr("New Body"), tr("Join"), tr("Cut"), tr("Intersect")])
        self.op_combo.setCurrentText(feature.operation)
        op_layout.addWidget(self.op_combo)
        op_layout.addStretch()
        group_layout.addLayout(op_layout)

        group.setLayout(group_layout)
        layout.addWidget(group)

        apply_btn = _create_buttons(layout, self)
        apply_btn.clicked.connect(self._on_apply)

    def _on_apply(self):
        try:
            angle = float(self.angle_input.text() or "360")
            if angle <= 0 or angle > 360:
                logger.warning("Angle must be 0-360")
                return

            axis_map = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}
            self.feature.angle = angle
            self.feature.axis = axis_map[self.axis_combo.currentText()]
            self.feature.operation = self.op_combo.currentText()
            self.accept()
        except ValueError as e:
            logger.error(f"Ungueltige Eingabe (Revolve): {e}")