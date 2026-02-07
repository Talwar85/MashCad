"""
Section View Control Panel

Compact floating panel for section view control.
Styled to match other InputPanels.
"""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QPoint

from i18n import tr
from gui.design_tokens import DesignTokens


class SectionViewPanel(QFrame):
    """
    Panel for section view control.

    Signals:
        section_enabled: emitted when section view is enabled (plane: str, position: float)
        section_disabled: emitted when section view is disabled
        section_position_changed: emitted on position change (position: float)
        section_plane_changed: emitted when plane changes (plane: str)
        section_invert_toggled: emitted when invert toggled
        close_requested: emitted when panel should be closed
    """

    section_enabled = Signal(str, float)
    section_disabled = Signal()
    section_position_changed = Signal(float)
    section_plane_changed = Signal(str)
    section_invert_toggled = Signal()
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_active = False
        self._plane = "XY"
        self._user_moved = False
        self._drag_active = False
        self._drag_offset = QPoint()
        self._drag_handle_height = 34

        self.setMinimumWidth(320)
        self.setMaximumWidth(420)
        self.setMinimumHeight(170)
        self.setStyleSheet(DesignTokens.stylesheet_panel())

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.title_label = QLabel(tr("Section:"))
        self.title_label.setObjectName("panelTitle")
        header.addWidget(self.title_label)

        self.status_label = QLabel(tr("Inactive"))
        self.status_label.setStyleSheet("color: #a3a3a3; font-size: 12px; border: none;")
        header.addWidget(self.status_label)
        header.addStretch()

        self.toggle_button = QPushButton(tr("Off"))
        self.toggle_button.setCheckable(True)
        self.toggle_button.setObjectName("toggle")
        self.toggle_button.clicked.connect(self._on_toggle_clicked)
        header.addWidget(self.toggle_button)

        self.close_button = QPushButton("X")
        self.close_button.setObjectName("danger")
        self.close_button.clicked.connect(self.close_requested.emit)
        header.addWidget(self.close_button)

        layout.addLayout(header)

        # Plane row
        plane_row = QHBoxLayout()
        plane_row.setSpacing(6)
        plane_row.addWidget(QLabel(tr("Plane:")))
        self._plane_buttons = {}
        for plane in ["XY", "YZ", "XZ"]:
            btn = QPushButton(plane)
            btn.setCheckable(True)
            btn.setObjectName("toggle")
            btn.clicked.connect(lambda checked, p=plane: self._set_plane(p))
            self._plane_buttons[plane] = btn
            plane_row.addWidget(btn)
        self._plane_buttons["XY"].setChecked(True)
        plane_row.addStretch()
        layout.addLayout(plane_row)

        # Position row
        pos_header = QHBoxLayout()
        pos_header.setSpacing(6)
        pos_header.addWidget(QLabel(tr("Position:")))
        self.position_label = QLabel("0.0 mm")
        self.position_label.setStyleSheet("color: #a3a3a3; font-size: 12px; border: none;")
        pos_header.addWidget(self.position_label)
        pos_header.addStretch()
        layout.addLayout(pos_header)

        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setMinimum(-1000)
        self.position_slider.setMaximum(1000)
        self.position_slider.setValue(0)
        self.position_slider.setEnabled(False)
        self.position_slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self.position_slider)

        # Options row
        opts = QHBoxLayout()
        opts.setSpacing(8)
        self.invert_checkbox = QCheckBox(tr("Invert"))
        self.invert_checkbox.setEnabled(False)
        self.invert_checkbox.toggled.connect(self._on_invert_toggled)
        opts.addWidget(self.invert_checkbox)

        self.highlight_checkbox = QCheckBox(tr("Highlight"))
        self.highlight_checkbox.setChecked(True)
        self.highlight_checkbox.setEnabled(False)
        opts.addWidget(self.highlight_checkbox)

        opts.addStretch()
        layout.addLayout(opts)

    def _set_plane(self, plane: str):
        self._plane = plane
        for p, btn in self._plane_buttons.items():
            btn.setChecked(p == plane)
        if self._is_active:
            self.section_plane_changed.emit(plane)
            self.section_enabled.emit(plane, self._get_slider_position())

    def _on_toggle_clicked(self, checked: bool):
        self._is_active = checked
        if checked:
            self.toggle_button.setText(tr("On"))
            self.status_label.setText(tr("Active"))
            self.position_slider.setEnabled(True)
            self.invert_checkbox.setEnabled(True)
            self.highlight_checkbox.setEnabled(True)
            self.section_enabled.emit(self._plane, self._get_slider_position())
        else:
            self.toggle_button.setText(tr("Off"))
            self.status_label.setText(tr("Inactive"))
            self.position_slider.setEnabled(False)
            self.invert_checkbox.setEnabled(False)
            self.highlight_checkbox.setEnabled(False)
            self.section_disabled.emit()

    def _on_slider_changed(self, value: int):
        position = self._get_slider_position()
        self.position_label.setText(f"{position:.1f} mm")
        if self._is_active:
            self.section_position_changed.emit(position)

    def _on_invert_toggled(self, checked: bool):
        if self._is_active:
            self.section_invert_toggled.emit()

    def _get_slider_position(self) -> float:
        return self.position_slider.value() / 10.0

    def set_slider_bounds(self, min_pos: float, max_pos: float, default_pos: float):
        if min_pos == max_pos:
            min_pos -= 1.0
            max_pos += 1.0
        self.position_slider.setMinimum(int(min_pos * 10))
        self.position_slider.setMaximum(int(max_pos * 10))
        self.position_slider.setValue(int(default_pos * 10))
        self.position_label.setText(f"{default_pos:.1f} mm")

    def show_at(self, pos_widget):
        self.show()
        self.raise_()
        self._position_right_mid(pos_widget)

    def _position_right_mid(self, pos_widget):
        parent = self.parent() or pos_widget
        if parent is None:
            return

        if pos_widget is None:
            area_x, area_y, area_w, area_h = 0, 0, parent.width(), parent.height()
        elif pos_widget.parent() is parent:
            geom = pos_widget.geometry()
            area_x, area_y, area_w, area_h = geom.x(), geom.y(), geom.width(), geom.height()
        else:
            top_left = pos_widget.mapTo(parent, QPoint(0, 0))
            area_x, area_y, area_w, area_h = top_left.x(), top_left.y(), pos_widget.width(), pos_widget.height()

        self.adjustSize()
        margin = 12
        x = area_x + area_w - self.width() - margin
        y = area_y + (area_h - self.height()) // 2

        tp = getattr(parent, "transform_panel", None)
        if tp and tp.isVisible():
            x = min(x, tp.x() - self.width() - margin)
            y = tp.y() + (tp.height() - self.height()) // 2

        tb = getattr(parent, "transform_toolbar", None)
        if tb and tb.isVisible():
            tb_pos = tb.mapTo(parent, QPoint(0, 0))
            x = min(x, tb_pos.x() - self.width() - margin)

        x = max(area_x + margin, min(x, area_x + area_w - self.width() - margin))
        y = max(area_y + margin, min(y, area_y + area_h - self.height() - margin))

        self.move(x, y)
        self.raise_()

    def clamp_to_parent(self):
        parent = self.parent()
        if parent is None:
            return
        margin = 8
        max_x = parent.width() - self.width() - margin
        max_y = parent.height() - self.height() - margin
        x = max(margin, min(self.x(), max_x))
        y = max(margin, min(self.y(), max_y))
        self.move(x, y)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.pos().y() <= self._drag_handle_height:
            child = self.childAt(event.pos())
            if child and child != self and child.metaObject().className() in ("QPushButton", "QSlider", "QCheckBox"):
                return super().mousePressEvent(event)
            self._drag_active = True
            self._drag_offset = event.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_active:
            parent = self.parent()
            if parent:
                new_pos = self.mapToParent(event.pos() - self._drag_offset)
                self.move(new_pos)
                self.clamp_to_parent()
                self._user_moved = True
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_active = False
            event.accept()
            return
        super().mouseReleaseEvent(event)
