"""
Section View Control Panel

UI-Panel zur Steuerung der Schnittansicht (wie Fusion 360 Section Analysis).

Autor: Claude (Section View Feature)
Datum: 2026-01-22
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QComboBox, QCheckBox, QGroupBox
)
from PySide6.QtCore import Qt, Signal
from loguru import logger


class SectionViewPanel(QWidget):
    """
    Panel zur Steuerung der Schnittansicht.

    Signals:
        section_enabled: Schnittansicht aktiviert (plane: str, position: float)
        section_disabled: Schnittansicht deaktiviert
        section_position_changed: Position geändert (position: float)
        section_plane_changed: Ebene geändert (plane: str)
        section_invert_toggled: Seitenansicht invertiert
    """

    section_enabled = Signal(str, float)  # plane, position
    section_disabled = Signal()
    section_position_changed = Signal(float)
    section_plane_changed = Signal(str)
    section_invert_toggled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_active = False

        # ✅ FIX: Widget-Eigenschaften setzen für Sichtbarkeit
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        # Feste Größe für bessere Sichtbarkeit
        self.setMinimumWidth(300)
        self.setMaximumWidth(350)
        self.setMinimumHeight(400)

        # Styling - Dark Theme für alle Widgets
        self.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            SectionViewPanel {
                border: 2px solid #0078d4;
                border-radius: 8px;
            }
            QGroupBox {
                background-color: #333333;
                border: 1px solid #555;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 8px;
                font-weight: bold;
                font-size: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 5px;
                color: #aaa;
            }
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:checked {
                background-color: #0078d4;
                border-color: #0078d4;
            }
            QComboBox {
                background-color: #3a3a3a;
                border: 1px solid #555;
                padding: 8px 12px;
                border-radius: 4px;
                min-width: 150px;
                font-size: 12px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #2b2b2b;
                color: #fff;
                selection-background-color: #0078d4;
                border: 1px solid #555;
                padding: 4px;
            }
            QCheckBox {
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QSlider::groove:horizontal {
                background: #3a3a3a;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #0078d4;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            QLabel {
                font-size: 12px;
            }
        """)

        self._setup_ui()

    def _setup_ui(self):
        """Erstellt UI-Elemente."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # === Header ===
        header_layout = QHBoxLayout()
        title = QLabel("🔪 Schnittansicht")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.toggle_button = QPushButton("Aktivieren")
        self.toggle_button.setCheckable(True)
        self.toggle_button.clicked.connect(self._on_toggle_clicked)
        header_layout.addWidget(self.toggle_button)

        layout.addLayout(header_layout)

        # === Plane Selection ===
        plane_group = QGroupBox("Schnittebene")
        plane_layout = QVBoxLayout(plane_group)

        self.plane_combo = QComboBox()
        self.plane_combo.addItems(["XY (Horizontal)", "YZ (Vertikal - Seite)", "XZ (Vertikal - Front)"])
        self.plane_combo.currentIndexChanged.connect(self._on_plane_changed)
        plane_layout.addWidget(self.plane_combo)

        layout.addWidget(plane_group)

        # === Position Control ===
        position_group = QGroupBox("Position")
        position_layout = QVBoxLayout(position_group)

        self.position_label = QLabel("Position: 0.0 mm")
        position_layout.addWidget(self.position_label)

        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setMinimum(-1000)
        self.position_slider.setMaximum(1000)
        self.position_slider.setValue(0)
        self.position_slider.setEnabled(False)
        self.position_slider.valueChanged.connect(self._on_slider_changed)
        position_layout.addWidget(self.position_slider)

        # Slider Scale Info
        scale_label = QLabel("Tipp: Scrolle für feine Anpassung")
        scale_label.setStyleSheet("color: gray; font-size: 10px;")
        position_layout.addWidget(scale_label)

        layout.addWidget(position_group)

        # === Options ===
        options_group = QGroupBox("Optionen")
        options_layout = QVBoxLayout(options_group)

        self.invert_checkbox = QCheckBox("Seite invertieren")
        self.invert_checkbox.setEnabled(False)
        self.invert_checkbox.toggled.connect(self._on_invert_toggled)
        options_layout.addWidget(self.invert_checkbox)

        self.highlight_checkbox = QCheckBox("Schnittflächen hervorheben")
        self.highlight_checkbox.setChecked(True)
        self.highlight_checkbox.setEnabled(False)
        options_layout.addWidget(self.highlight_checkbox)

        layout.addWidget(options_group)

        # === Help Text ===
        help_text = QLabel(
            "<b>Anwendung:</b><br>"
            "1. Aktivieren → wähle Schnittebene<br>"
            "2. Schiebe Position-Slider<br>"
            "3. Prüfe Boolean Cuts und innere Geometrie<br><br>"
            "<b>Shortcuts:</b><br>"
            "• <b>Strg+Shift+S</b>: Toggle Section View"
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("background: #1e1e1e; padding: 10px; border-radius: 4px; font-size: 11px; color: #aaa;")
        layout.addWidget(help_text)

        layout.addStretch()

    def _on_toggle_clicked(self, checked):
        """Toggle Section View."""
        self._is_active = checked

        if checked:
            self.toggle_button.setText("Deaktivieren")
            self.position_slider.setEnabled(True)
            self.invert_checkbox.setEnabled(True)
            self.highlight_checkbox.setEnabled(True)

            # Emit Enable mit aktueller Plane & Position
            plane = self._get_current_plane()
            position = self._get_slider_position()

            logger.info(f"🔪 Section View aktiviert: {plane} @ {position:.1f}mm")
            self.section_enabled.emit(plane, position)

        else:
            self.toggle_button.setText("Aktivieren")
            self.position_slider.setEnabled(False)
            self.invert_checkbox.setEnabled(False)
            self.highlight_checkbox.setEnabled(False)

            logger.info("🔪 Section View deaktiviert")
            self.section_disabled.emit()

    def _on_plane_changed(self, index):
        """Schnittebene wurde geändert."""
        if not self._is_active:
            return

        plane = self._get_current_plane()
        logger.debug(f"🔪 Plane geändert: {plane}")
        self.section_plane_changed.emit(plane)

        # Re-enable mit neuer Plane
        position = self._get_slider_position()
        self.section_enabled.emit(plane, position)

    def _on_slider_changed(self, value):
        """Slider-Position wurde geändert."""
        position = self._get_slider_position()
        self.position_label.setText(f"Position: {position:.1f} mm")

        if self._is_active:
            self.section_position_changed.emit(position)

    def _on_invert_toggled(self, checked):
        """Seite invertieren."""
        if self._is_active:
            logger.debug(f"🔪 Invert toggled: {checked}")
            self.section_invert_toggled.emit()

    def _get_current_plane(self) -> str:
        """Gibt aktuell gewählte Ebene zurück."""
        index = self.plane_combo.currentIndex()
        planes = ["XY", "YZ", "XZ"]
        return planes[index]

    def _get_slider_position(self) -> float:
        """Konvertiert Slider-Value zu Position in mm."""
        # Slider: -1000 bis +1000 → -100mm bis +100mm (10:1 ratio)
        return self.position_slider.value() / 10.0

    def set_slider_bounds(self, min_pos: float, max_pos: float, default_pos: float):
        """
        Setzt Slider-Bounds basierend auf Geometrie.

        Args:
            min_pos: Minimum Position (mm)
            max_pos: Maximum Position (mm)
            default_pos: Default Position (mm)
        """
        # Slider arbeitet in 0.1mm Schritten (10x multipliziert)
        self.position_slider.setMinimum(int(min_pos * 10))
        self.position_slider.setMaximum(int(max_pos * 10))
        self.position_slider.setValue(int(default_pos * 10))

        logger.debug(f"📏 Slider Bounds: [{min_pos:.1f}, {max_pos:.1f}] mm")
