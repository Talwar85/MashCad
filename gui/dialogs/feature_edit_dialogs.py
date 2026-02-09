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


# ==================== Operation Mapping ====================
# WICHTIG: Operations müssen IMMER als englische Keys gespeichert werden!
# Die UI zeigt übersetzte Strings, aber intern werden englische Keys verwendet.

OPERATION_KEYS = ["New Body", "Join", "Cut", "Intersect"]


def _get_operation_key(translated_text: str) -> str:
    """
    Konvertiert übersetzten Operationstext zurück zum englischen Key.

    Args:
        translated_text: Der übersetzte String (z.B. "Neuer Körper")

    Returns:
        Englischer Key (z.B. "New Body")
    """
    # Erstelle Reverse-Mapping: übersetzt -> englisch
    for key in OPERATION_KEYS:
        if tr(key) == translated_text:
            return key

    # Fallback: Wenn der Text bereits ein englischer Key ist
    if translated_text in OPERATION_KEYS:
        return translated_text

    # Default
    logger.warning(f"Unbekannte Operation '{translated_text}', verwende 'Join'")
    return "Join"


def _get_translated_operations() -> list:
    """Gibt die übersetzten Operationsnamen zurück."""
    return [tr(key) for key in OPERATION_KEYS]


def _set_operation_combo(combo: QComboBox, operation_key: str):
    """
    Setzt die ComboBox auf die richtige übersetzte Operation.

    Args:
        combo: Die QComboBox
        operation_key: Englischer Key (z.B. "New Body")
    """
    translated = tr(operation_key) if operation_key in OPERATION_KEYS else tr("Join")
    combo.setCurrentText(translated)


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


def _add_geometry_delta_section(layout, feature, body, dialog):
    """Fügt Geometry-Delta und Kanten-Info zum Edit-Dialog hinzu."""
    gd = getattr(feature, '_geometry_delta', None)
    edge_indices = getattr(feature, 'edge_indices', None) or []
    face_index = getattr(feature, 'face_index', None)  # Push/Pull Face
    has_content = gd is not None or len(edge_indices) > 0 or face_index is not None

    if not has_content:
        return

    group = QGroupBox(tr("Geometry Info"))
    group_layout = QVBoxLayout()
    group_layout.setSpacing(2)

    # Volume Delta
    if gd:
        vol_before = gd.get("volume_before", 0)
        vol_after = gd.get("volume_after", 0)
        vol_pct = gd.get("volume_pct", 0)

        if vol_before > 0 and vol_pct != 0:
            sign = "+" if vol_pct > 0 else ""
            vol_text = f"Volume: {vol_before:.0f} → {vol_after:.0f} mm³ ({sign}{vol_pct:.1f}%)"
        elif vol_before == 0 and vol_after > 0:
            vol_text = f"Volume: {vol_after:.0f} mm³"
        else:
            vol_text = f"Volume: {tr('unverändert')}"
        vol_label = QLabel(vol_text)
        vol_label.setStyleSheet("color: #ccc; font-size: 10px;")
        group_layout.addWidget(vol_label)

        fd = gd.get("faces_delta", 0)
        ed = gd.get("edges_delta", 0)
        topo_text = (
            f"{tr('Flächen')}: {gd.get('faces_before', '?')} → {gd.get('faces_after', '?')} "
            f"({'+' if fd > 0 else ''}{fd})  |  "
            f"{tr('Kanten')}: {gd.get('edges_before', '?')} → {gd.get('edges_after', '?')} "
            f"({'+' if ed > 0 else ''}{ed})"
        )
        topo_label = QLabel(topo_text)
        topo_label.setStyleSheet("color: #999; font-size: 10px;")
        topo_label.setWordWrap(True)
        group_layout.addWidget(topo_label)

    # Kanten-Liste mit Show-Button
    if edge_indices:
        solid = body._build123d_solid if body else None
        all_edges = list(solid.edges()) if solid else []
        valid_count = sum(1 for idx in edge_indices if 0 <= idx < len(all_edges))
        invalid_count = len(edge_indices) - valid_count

        edge_summary = f"{valid_count}/{len(edge_indices)} {tr('Kanten gültig')}"
        if invalid_count > 0:
            edge_summary += f"  ⚠ {invalid_count} {tr('ungültig')}"

        edge_row = QHBoxLayout()
        edge_label = QLabel(edge_summary)
        color = "#22c55e" if invalid_count == 0 else "#f59e0b"
        edge_label.setStyleSheet(f"color: {color}; font-size: 10px;")
        edge_row.addWidget(edge_label)

        show_btn = QPushButton(tr("Kanten anzeigen"))
        show_btn.setFixedHeight(20)
        show_btn.setStyleSheet(
            "QPushButton { background: #333; color: #ccc; border: 1px solid #555; "
            "border-radius: 3px; font-size: 10px; padding: 1px 8px; }"
            "QPushButton:hover { background: #444; color: white; }"
        )
        show_btn.clicked.connect(lambda: _highlight_edges_in_viewport(dialog._parent_window, body, edge_indices))
        edge_row.addWidget(show_btn)
        group_layout.addLayout(edge_row)

    # Flächen-Info mit Show-Button (Push/Pull)
    if face_index is not None:
        solid = body._build123d_solid if body else None
        all_faces = list(solid.faces()) if solid else []
        is_valid = 0 <= face_index < len(all_faces)

        face_summary = f"Face[{face_index}]"
        if not is_valid:
            face_summary += f"  ⚠ {tr('ungültig')} (max={len(all_faces) - 1})"

        face_row = QHBoxLayout()
        face_label = QLabel(face_summary)
        color = "#22c55e" if is_valid else "#f59e0b"
        face_label.setStyleSheet(f"color: {color}; font-size: 10px;")
        face_row.addWidget(face_label)

        if is_valid:
            show_face_btn = QPushButton(tr("Fläche anzeigen"))
            show_face_btn.setFixedHeight(20)
            show_face_btn.setStyleSheet(
                "QPushButton { background: #333; color: #ccc; border: 1px solid #555; "
                "border-radius: 3px; font-size: 10px; padding: 1px 8px; }"
                "QPushButton:hover { background: #444; color: white; }"
            )
            show_face_btn.clicked.connect(lambda: _highlight_face_in_viewport(dialog._parent_window, body, face_index))
            face_row.addWidget(show_face_btn)

        group_layout.addLayout(face_row)

    group.setLayout(group_layout)
    layout.addWidget(group)


def _highlight_edges_in_viewport(main_window, body, edge_indices):
    """Highlighted die angegebenen Kanten im Viewport."""
    if main_window is None:
        return
    viewport = getattr(main_window, 'viewport_3d', None)
    if viewport is None:
        return
    try:
        viewport.highlight_edges_by_index(body, edge_indices)
    except Exception as e:
        logger.debug(f"Edge-Highlighting fehlgeschlagen: {e}")


def _highlight_face_in_viewport(main_window, body, face_index):
    """Highlighted die angegebene Fläche im Viewport."""
    if main_window is None:
        return
    viewport = getattr(main_window, 'viewport_3d', None)
    if viewport is None:
        return
    try:
        viewport.highlight_face_by_index(body, face_index)
    except Exception as e:
        logger.debug(f"Face-Highlighting fehlgeschlagen: {e}")


def _clear_edge_highlight(main_window):
    """Entfernt Edge-Highlighting beim Schließen des Dialogs."""
    if main_window is None:
        return
    viewport = getattr(main_window, 'viewport_3d', None)
    if viewport is None:
        return
    try:
        viewport.clear_edge_highlight()
    except Exception:
        pass


def _clear_face_highlight(main_window):
    """Entfernt Face-Highlighting beim Schließen des Dialogs."""
    if main_window is None:
        return
    viewport = getattr(main_window, 'viewport_3d', None)
    if viewport is None:
        return
    try:
        viewport.clear_face_highlight()
    except Exception:
        pass


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
    """Edit-Dialog fuer ExtrudeFeature: Distance, Direction, Operation + Geometry-Delta"""

    def __init__(self, feature, body, parent=None):
        super().__init__(parent)
        self.feature = feature
        self.body = body
        self._parent_window = parent
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
        self.op_combo.addItems(_get_translated_operations())
        _set_operation_combo(self.op_combo, feature.operation)
        op_layout.addWidget(self.op_combo)
        op_layout.addStretch()
        group_layout.addLayout(op_layout)

        group.setLayout(group_layout)
        layout.addWidget(group)

        # Geometry Delta Sektion
        _add_geometry_delta_section(layout, feature, body, self)

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
            self.feature.operation = _get_operation_key(self.op_combo.currentText())
            self.accept()
        except ValueError as e:
            logger.error(f"Ungueltige Eingabe: {e}")

    def closeEvent(self, event):
        _clear_face_highlight(self._parent_window)
        super().closeEvent(event)

    def reject(self):
        _clear_face_highlight(self._parent_window)
        super().reject()

    def get_old_data(self):
        return {
            'distance': self.feature.distance,
            'direction': self.feature.direction,
            'operation': self.feature.operation,
        }


class FilletEditDialog(QDialog):
    """Edit-Dialog fuer FilletFeature: Radius + Geometry-Delta + Kanten-Info"""

    def __init__(self, feature, body, parent=None):
        super().__init__(parent)
        self.feature = feature
        self.body = body
        self._parent_window = parent
        self.setWindowTitle(f"Edit {feature.name}")
        self.setMinimumWidth(380)
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
        n_edges = len(getattr(feature, "edge_indices", []) or [])
        if feature.edge_shape_ids:
            n_edges = max(n_edges, len(feature.edge_shape_ids))
        if feature.geometric_selectors:
            n_edges = max(n_edges, len(feature.geometric_selectors))
        edge_info = QLabel(f"Edges: {n_edges}")
        edge_info.setStyleSheet("color: #999; font-size: 11px; font-style: italic;")
        group_layout.addWidget(edge_info)

        group.setLayout(group_layout)
        layout.addWidget(group)

        # Geometry Delta + Kanten-Sektion
        _add_geometry_delta_section(layout, feature, body, self)

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

    def closeEvent(self, event):
        _clear_edge_highlight(self._parent_window)
        super().closeEvent(event)

    def reject(self):
        _clear_edge_highlight(self._parent_window)
        super().reject()


class ChamferEditDialog(QDialog):
    """Edit-Dialog fuer ChamferFeature: Distance + Geometry-Delta + Kanten-Info"""

    def __init__(self, feature, body, parent=None):
        super().__init__(parent)
        self.feature = feature
        self.body = body
        self._parent_window = parent
        self.setWindowTitle(f"Edit {feature.name}")
        self.setMinimumWidth(380)
        self.setStyleSheet(DesignTokens.stylesheet_dialog())

        layout = QVBoxLayout(self)

        info = QLabel(f"<b>{feature.name}</b><br>Body: {body.name}")
        info.setStyleSheet("color: #ddd; padding: 10px; background: #1e1e1e; border-radius: 4px;")
        layout.addWidget(info)

        group = QGroupBox(tr("Chamfer Parameters"))
        group_layout = QVBoxLayout()

        self.distance_input = _create_number_input(tr("Distance:"), group_layout, "mm")
        self.distance_input.setText(str(feature.distance))

        n_edges = len(getattr(feature, "edge_indices", []) or [])
        if feature.edge_shape_ids:
            n_edges = max(n_edges, len(feature.edge_shape_ids))
        if feature.geometric_selectors:
            n_edges = max(n_edges, len(feature.geometric_selectors))
        edge_info = QLabel(f"Edges: {n_edges}")
        edge_info.setStyleSheet("color: #999; font-size: 11px; font-style: italic;")
        group_layout.addWidget(edge_info)

        group.setLayout(group_layout)
        layout.addWidget(group)

        # Geometry Delta + Kanten-Sektion
        _add_geometry_delta_section(layout, feature, body, self)

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

    def closeEvent(self, event):
        _clear_edge_highlight(self._parent_window)
        super().closeEvent(event)

    def reject(self):
        _clear_edge_highlight(self._parent_window)
        super().reject()


class ShellEditDialog(QDialog):
    """Edit-Dialog fuer ShellFeature: Thickness + Geometry-Delta"""

    def __init__(self, feature, body, parent=None):
        super().__init__(parent)
        self.feature = feature
        self.body = body
        self._parent_window = parent
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

        # Geometry Delta Sektion
        _add_geometry_delta_section(layout, feature, body, self)

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
    """Edit-Dialog fuer RevolveFeature: Angle, Axis, Operation + Geometry-Delta"""

    def __init__(self, feature, body, parent=None):
        super().__init__(parent)
        self.feature = feature
        self.body = body
        self._parent_window = parent
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
        self.op_combo.addItems(_get_translated_operations())
        _set_operation_combo(self.op_combo, feature.operation)
        op_layout.addWidget(self.op_combo)
        op_layout.addStretch()
        group_layout.addLayout(op_layout)

        group.setLayout(group_layout)
        layout.addWidget(group)

        # Geometry Delta Sektion
        _add_geometry_delta_section(layout, feature, body, self)

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
            self.feature.operation = _get_operation_key(self.op_combo.currentText())
            self.accept()
        except ValueError as e:
            logger.error(f"Ungueltige Eingabe (Revolve): {e}")


class LoftEditDialog(QDialog):
    """Edit-Dialog fuer LoftFeature: Ruled, Operation, Continuity + Geometry-Delta"""

    def __init__(self, feature, body, parent=None):
        super().__init__(parent)
        self.feature = feature
        self.body = body
        self._parent_window = parent
        self.setWindowTitle(f"Edit {feature.name}")
        self.setMinimumWidth(400)
        self.setStyleSheet(DesignTokens.stylesheet_dialog())

        layout = QVBoxLayout(self)

        info = QLabel(f"<b>{feature.name}</b><br>Body: {body.name}")
        info.setStyleSheet("color: #ddd; padding: 10px; background: #1e1e1e; border-radius: 4px;")
        layout.addWidget(info)

        group = QGroupBox(tr("Loft Parameters"))
        group_layout = QVBoxLayout()

        # Ruled
        ruled_layout = QHBoxLayout()
        ruled_layout.addWidget(QLabel(tr("Ruled:")))
        self.ruled_combo = QComboBox()
        self.ruled_combo.addItems([tr("Smooth"), tr("Ruled")])
        self.ruled_combo.setCurrentIndex(1 if feature.ruled else 0)
        ruled_layout.addWidget(self.ruled_combo)
        ruled_layout.addStretch()
        group_layout.addLayout(ruled_layout)

        # Operation
        op_layout = QHBoxLayout()
        op_layout.addWidget(QLabel(tr("Operation:")))
        self.op_combo = QComboBox()
        self.op_combo.addItems(_get_translated_operations())
        _set_operation_combo(self.op_combo, feature.operation)
        op_layout.addWidget(self.op_combo)
        op_layout.addStretch()
        group_layout.addLayout(op_layout)

        # Continuity
        start_cont_layout = QHBoxLayout()
        start_cont_layout.addWidget(QLabel(tr("Start Continuity:")))
        self.start_cont_combo = QComboBox()
        self.start_cont_combo.addItems(["G0", "G1", "G2"])
        self.start_cont_combo.setCurrentText(feature.start_continuity)
        start_cont_layout.addWidget(self.start_cont_combo)
        start_cont_layout.addStretch()
        group_layout.addLayout(start_cont_layout)

        end_cont_layout = QHBoxLayout()
        end_cont_layout.addWidget(QLabel(tr("End Continuity:")))
        self.end_cont_combo = QComboBox()
        self.end_cont_combo.addItems(["G0", "G1", "G2"])
        self.end_cont_combo.setCurrentText(feature.end_continuity)
        end_cont_layout.addWidget(self.end_cont_combo)
        end_cont_layout.addStretch()
        group_layout.addLayout(end_cont_layout)

        # Profile count
        n_profiles = len(feature.profile_data) if feature.profile_data else 0
        profile_info = QLabel(f"Profiles: {n_profiles}")
        profile_info.setStyleSheet("color: #999; font-size: 11px; font-style: italic;")
        group_layout.addWidget(profile_info)

        group.setLayout(group_layout)
        layout.addWidget(group)

        # Geometry Delta Sektion
        _add_geometry_delta_section(layout, feature, body, self)

        apply_btn = _create_buttons(layout, self)
        apply_btn.clicked.connect(self._on_apply)

    def _on_apply(self):
        try:
            self.feature.ruled = (self.ruled_combo.currentIndex() == 1)
            self.feature.operation = _get_operation_key(self.op_combo.currentText())
            self.feature.start_continuity = self.start_cont_combo.currentText()
            self.feature.end_continuity = self.end_cont_combo.currentText()
            self.accept()
        except Exception as e:
            logger.error(f"Ungueltige Eingabe (Loft): {e}")


class SweepEditDialog(QDialog):
    """Edit-Dialog fuer SweepFeature: Operation, Frenet, Twist + Geometry-Delta"""

    def __init__(self, feature, body, parent=None):
        super().__init__(parent)
        self.feature = feature
        self.body = body
        self._parent_window = parent
        self.setWindowTitle(f"Edit {feature.name}")
        self.setMinimumWidth(400)
        self.setStyleSheet(DesignTokens.stylesheet_dialog())

        layout = QVBoxLayout(self)

        info = QLabel(f"<b>{feature.name}</b><br>Body: {body.name}")
        info.setStyleSheet("color: #ddd; padding: 10px; background: #1e1e1e; border-radius: 4px;")
        layout.addWidget(info)

        group = QGroupBox(tr("Sweep Parameters"))
        group_layout = QVBoxLayout()

        # Operation
        op_layout = QHBoxLayout()
        op_layout.addWidget(QLabel(tr("Operation:")))
        self.op_combo = QComboBox()
        self.op_combo.addItems(_get_translated_operations())
        _set_operation_combo(self.op_combo, feature.operation)
        op_layout.addWidget(self.op_combo)
        op_layout.addStretch()
        group_layout.addLayout(op_layout)

        # Frenet
        frenet_layout = QHBoxLayout()
        frenet_layout.addWidget(QLabel(tr("Frenet Frame:")))
        self.frenet_combo = QComboBox()
        self.frenet_combo.addItems([tr("No"), tr("Yes")])
        self.frenet_combo.setCurrentIndex(1 if getattr(feature, 'is_frenet', False) else 0)
        frenet_layout.addWidget(self.frenet_combo)
        frenet_layout.addStretch()
        group_layout.addLayout(frenet_layout)

        # Twist
        self.twist_input = _create_number_input(tr("Twist:"), group_layout, "deg")
        self.twist_input.setText(str(getattr(feature, 'twist_angle', 0.0)))

        group.setLayout(group_layout)
        layout.addWidget(group)

        # Geometry Delta Sektion
        _add_geometry_delta_section(layout, feature, body, self)

        apply_btn = _create_buttons(layout, self)
        apply_btn.clicked.connect(self._on_apply)

    def _on_apply(self):
        try:
            self.feature.operation = _get_operation_key(self.op_combo.currentText())
            self.feature.is_frenet = (self.frenet_combo.currentIndex() == 1)
            twist = float(self.twist_input.text() or "0")
            self.feature.twist_angle = twist
            self.accept()
        except ValueError as e:
            logger.error(f"Ungueltige Eingabe (Sweep): {e}")
