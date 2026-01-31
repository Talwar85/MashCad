"""
BREP Cleanup Control Panel
==========================

UI-Panel fuer interaktive BREP-Bereinigung nach STL-Import.

Features:
- Erkannte Features anzeigen (Loecher, Bolzen, Taschen, Fillets)
- Feature-Selektion per Klick
- Merge-Operationen
- Auto-Suggest Optionen

Author: Claude (BREP Cleanup Feature)
Date: 2026-01
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox, QCheckBox,
    QDoubleSpinBox, QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon
from loguru import logger

from typing import List, Optional, Dict, Any


class FeatureListItem(QListWidgetItem):
    """ListWidgetItem fuer Feature-Anzeige mit Icon und Farbe."""

    def __init__(self, feature, feature_idx: int):
        """
        Args:
            feature: DetectedFeature Objekt
            feature_idx: Index in der Feature-Liste
        """
        super().__init__()
        self.feature = feature
        self.feature_idx = feature_idx

        # Text mit Icon und Info
        icon = feature.icon
        name = feature.display_name
        count = len(feature.face_indices)
        params = self._format_params(feature.parameters)

        text = f"{icon} {name}"
        if params:
            text += f" ({params})"
        if count > 1:
            text += f" [{count} Faces]"

        self.setText(text)

        # Farbe setzen
        color = QColor(feature.color_hex)
        self.setForeground(color)

    def _format_params(self, params: Dict[str, Any]) -> str:
        """Formatiert Parameter fuer Anzeige."""
        parts = []

        if "diameter" in params:
            parts.append(f"Ø{params['diameter']:.1f}mm")
        elif "radius" in params:
            parts.append(f"R={params['radius']:.1f}mm")

        if "apex_angle" in params:
            parts.append(f"{params['apex_angle']:.0f}°")

        if "depth" in params:
            parts.append(f"T={params['depth']:.1f}mm")

        return ", ".join(parts)


class BRepCleanupPanel(QWidget):
    """
    Panel zur Steuerung der BREP-Bereinigung.

    Signals:
        feature_selected: Feature ausgewaehlt (feature_idx: int)
        feature_type_selected: Alle Features eines Typs (feature_type: str)
        merge_requested: Merge angefordert
        merge_all_requested: Alle Features mergen
        close_requested: Panel schliessen
        auto_suggest_changed: Auto-Suggest Option geaendert (enabled: bool)
        max_fillet_radius_changed: Max Fillet-Radius geaendert (radius: float)
    """

    feature_selected = Signal(int, bool)  # (feature_idx, additive)
    feature_type_selected = Signal(str)
    merge_requested = Signal()
    merge_all_requested = Signal()
    close_requested = Signal()
    auto_suggest_changed = Signal(bool)
    max_fillet_radius_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Widget-Eigenschaften
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self.setMinimumWidth(320)
        self.setMaximumWidth(380)
        self.setMinimumHeight(500)

        self._features = []
        self._selected_face_count = 0

        self._setup_ui()
        self._setup_style()

    def _setup_ui(self):
        """Erstellt UI-Elemente."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # === Header ===
        header = QHBoxLayout()
        title = QLabel("BREP Cleanup")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)

        layout.addLayout(header)

        # === Feature-Liste ===
        features_group = QGroupBox("Erkannte Features")
        features_layout = QVBoxLayout(features_group)

        self.feature_list = QListWidget()
        self.feature_list.setMinimumHeight(200)
        self.feature_list.itemClicked.connect(self._on_feature_clicked)
        features_layout.addWidget(self.feature_list)

        layout.addWidget(features_group)

        # === Selektion-Info ===
        selection_group = QGroupBox("Selektion")
        selection_layout = QVBoxLayout(selection_group)

        self.selection_label = QLabel("Keine Faces selektiert")
        selection_layout.addWidget(self.selection_label)

        self.face_info_label = QLabel("")
        self.face_info_label.setStyleSheet("color: #888;")
        selection_layout.addWidget(self.face_info_label)

        layout.addWidget(selection_group)

        # === Optionen ===
        options_group = QGroupBox("Optionen")
        options_layout = QVBoxLayout(options_group)

        # Auto-Suggest
        self.auto_suggest_cb = QCheckBox("Auto-Suggest Nachbarn")
        self.auto_suggest_cb.setChecked(True)
        self.auto_suggest_cb.toggled.connect(self.auto_suggest_changed.emit)
        options_layout.addWidget(self.auto_suggest_cb)

        # Feature-Erkennung
        self.feature_detect_cb = QCheckBox("Features erkennen")
        self.feature_detect_cb.setChecked(True)
        options_layout.addWidget(self.feature_detect_cb)

        # Max Fillet-Radius
        fillet_layout = QHBoxLayout()
        fillet_layout.addWidget(QLabel("Max Fillet-Radius:"))
        self.fillet_radius_spin = QDoubleSpinBox()
        self.fillet_radius_spin.setRange(0.1, 50.0)
        self.fillet_radius_spin.setValue(10.0)
        self.fillet_radius_spin.setSuffix(" mm")
        self.fillet_radius_spin.valueChanged.connect(
            self.max_fillet_radius_changed.emit
        )
        fillet_layout.addWidget(self.fillet_radius_spin)
        options_layout.addLayout(fillet_layout)

        layout.addWidget(options_group)

        # === Buttons ===
        button_layout = QHBoxLayout()

        self.merge_btn = QPushButton("Feature Merge")
        self.merge_btn.setEnabled(False)
        self.merge_btn.clicked.connect(self.merge_requested.emit)
        button_layout.addWidget(self.merge_btn)

        self.merge_all_btn = QPushButton("Alle Merge")
        self.merge_all_btn.clicked.connect(self.merge_all_requested.emit)
        button_layout.addWidget(self.merge_all_btn)

        layout.addLayout(button_layout)

        done_btn = QPushButton("Fertig")
        done_btn.clicked.connect(self.close_requested.emit)
        layout.addWidget(done_btn)

        layout.addStretch()

    def _setup_style(self):
        """Setzt Dark Theme Styling."""
        self.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            BRepCleanupPanel {
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
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #666;
            }
            QListWidget {
                background-color: #333333;
                border: 1px solid #555;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid #444;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
            }
            QListWidget::item:hover {
                background-color: #3a3a3a;
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QDoubleSpinBox {
                background-color: #3a3a3a;
                border: 1px solid #555;
                padding: 4px 8px;
                border-radius: 4px;
            }
        """)

    # =========================================================================
    # Public Methods
    # =========================================================================

    def set_features(self, features: List):
        """
        Setzt die erkannten Features.

        Args:
            features: Liste von DetectedFeature Objekten
        """
        self._features = features
        self._update_feature_list()

    def update_selection(self, face_indices: List[int]):
        """
        Aktualisiert Selektion-Anzeige.

        Args:
            face_indices: Liste selektierter Face-Indices
        """
        self._selected_face_count = len(face_indices)

        if self._selected_face_count == 0:
            self.selection_label.setText("Keine Faces selektiert")
            self.face_info_label.setText("")
            self.merge_btn.setEnabled(False)
        else:
            self.selection_label.setText(f"Selektiert: {self._selected_face_count} Faces")
            self.merge_btn.setEnabled(True)

    def update_face_info(self, info: Dict[str, Any]):
        """
        Zeigt Info fuer gehovertes Face.

        Args:
            info: Dict mit Face-Informationen
        """
        if not info:
            self.face_info_label.setText("")
            return

        parts = []

        if "feature_type" in info:
            parts.append(f"{info.get('feature_icon', '')} {info['feature_type']}")

        if "type" in info:
            parts.append(f"Typ: {info['type']}")

        if "diameter" in info:
            parts.append(f"Ø{info['diameter']:.1f}mm")
        elif "radius" in info:
            parts.append(f"R={info['radius']:.1f}mm")

        if "area" in info:
            parts.append(f"Fläche: {info['area']:.1f}mm²")

        self.face_info_label.setText(" | ".join(parts))

    # =========================================================================
    # Internal Methods
    # =========================================================================

    def _update_feature_list(self):
        """Aktualisiert Feature-Liste."""
        self.feature_list.clear()

        # Gruppiere Features nach Typ
        feature_groups: Dict[str, List] = {}
        for idx, feature in enumerate(self._features):
            type_name = feature.feature_type.name
            if type_name not in feature_groups:
                feature_groups[type_name] = []
            feature_groups[type_name].append((idx, feature))

        # Fuege gruppiert hinzu
        for type_name, features in feature_groups.items():
            if len(features) > 1:
                # Header fuer Gruppe
                first_feature = features[0][1]
                header = QListWidgetItem(
                    f"─── {first_feature.icon} {first_feature.display_name} "
                    f"({len(features)}x) ───"
                )
                header.setFlags(Qt.ItemIsEnabled)
                header.setForeground(QColor("#888"))
                self.feature_list.addItem(header)

            for idx, feature in features:
                item = FeatureListItem(feature, idx)
                self.feature_list.addItem(item)

    def _on_feature_clicked(self, item: QListWidgetItem):
        """Handler fuer Feature-Klick."""
        if isinstance(item, FeatureListItem):
            # Ctrl-Key fuer Multiselect
            from PySide6.QtWidgets import QApplication
            modifiers = QApplication.keyboardModifiers()
            additive = bool(modifiers & Qt.ControlModifier)
            self.feature_selected.emit(item.feature_idx, additive)
