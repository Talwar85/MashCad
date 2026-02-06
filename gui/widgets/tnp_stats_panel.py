"""
MashCad - TNP v4.0 Statistics Panel
===================================

Zeigt Echtzeit-Statistiken zum TNP v4.0 ShapeNamingSystem.
Hilft beim Debugging und Verständnis der Shape-Registry.

Verwendung:
    panel = TNPStatsPanel(parent)
    panel.update_stats(body)  # Body aus einem Document mit ShapeNamingService
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QFrame, QGroupBox, QGridLayout,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from loguru import logger
from i18n import tr


class TNPStatsPanel(QWidget):
    """
    Panel zur Anzeige von TNP v4.0 Statistiken.

    Zeigt:
    - Gesamtstatistiken (Shapes, Operations, Features)
    - Verteilung nach Shape-Typ (Edges, Faces, Vertices)
    - Letzte Operationen
    - Feature-Registry Status
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Erstellt das UI-Layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # === Header ===
        header = QLabel(tr("TNP v4.0 Shape Registry"))
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(12)
        header.setFont(header_font)
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("color: #ffffff; padding: 5px;")
        layout.addWidget(header)

        # === Status Card ===
        status_card = self._create_card()
        status_layout = QVBoxLayout(status_card)
        status_layout.setSpacing(8)

        # Registry Status
        status_header = QLabel(tr("Registry Status"))
        status_header.setStyleSheet("font-weight: bold; color: #cccccc;")
        status_layout.addWidget(status_header)

        self._status_grid = QGridLayout()
        self._status_grid.setSpacing(6)

        self._status_labels = {}
        status_items = [
            ("total_shapes", tr("Total Shapes"), "#4a9eff"),
            ("operations", tr("Operations"), "#9b59b6"),
            ("features", tr("Features"), "#2ecc71"),
            ("edges", tr("Edges Tracked"), "#f39c12"),
            ("faces", tr("Faces Tracked"), "#e74c3c"),
        ]

        for i, (key, label, color) in enumerate(status_items):
            # Label
            name_label = QLabel(f"{label}:")
            name_label.setStyleSheet("color: #aaaaaa;")
            self._status_grid.addWidget(name_label, i, 0)

            # Wert
            value_label = QLabel("0")
            value_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 14px;")
            value_label.setAlignment(Qt.AlignRight)
            self._status_grid.addWidget(value_label, i, 1)
            self._status_labels[key] = value_label

        status_layout.addLayout(self._status_grid)
        layout.addWidget(status_card)

        # === Last Operation Card ===
        op_card = self._create_card()
        op_layout = QVBoxLayout(op_card)
        op_layout.setSpacing(8)

        op_header = QLabel(tr("Last Operation"))
        op_header.setStyleSheet("font-weight: bold; color: #cccccc;")
        op_layout.addWidget(op_header)

        self._last_op_label = QLabel(tr("No operations yet"))
        self._last_op_label.setStyleSheet("color: #888888; font-style: italic;")
        self._last_op_label.setWordWrap(True)
        op_layout.addWidget(self._last_op_label)

        layout.addWidget(op_card)

        # === Feature Registry Card ===
        feature_card = self._create_card()
        feature_layout = QVBoxLayout(feature_card)
        feature_layout.setSpacing(8)

        feature_header = QLabel(tr("Feature Registry"))
        feature_header.setStyleSheet("font-weight: bold; color: #cccccc;")
        feature_layout.addWidget(feature_header)

        self._feature_list = QLabel(tr("No features registered"))
        self._feature_list.setStyleSheet("color: #888888;")
        self._feature_list.setWordWrap(True)
        feature_layout.addWidget(self._feature_list)

        layout.addWidget(feature_card)

        # === Placeholder (wenn keine Daten) ===
        self._placeholder = QLabel(tr(
            "No TNP v4.0 data available.\n\n"
            "The ShapeNamingService is initialized when:\n"
            "• A project is created/loaded\n"
            "• Features are added to bodies"
        ))
        self._placeholder.setStyleSheet("color: #666666; font-style: italic; padding: 20px;")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setWordWrap(True)
        layout.addWidget(self._placeholder)

        layout.addStretch()

        # Initial state
        self._update_visibility(False)

    def _create_card(self):
        """Erstellt eine Style-Card."""
        card = QFrame()
        card.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        card.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border: 1px solid #3d3d3d;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        return card

    def _update_visibility(self, has_data: bool):
        """Zeigt/versteckt die Statistik-Widgets basierend auf Datenverfügbarkeit."""
        self._placeholder.setVisible(not has_data)

    def update_stats(self, body):
        """
        Aktualisiert die Anzeige mit Statistiken vom Body's Document ShapeNamingService.

        Args:
            body: Body-Objekt mit _document._shape_naming_service
        """
        if body is None:
            self._reset_stats()
            return

        # TNP v4.0: ShapeNamingService vom Document holen
        document = getattr(body, '_document', None)
        if document is None:
            self._reset_stats()
            return

        service = getattr(document, '_shape_naming_service', None)
        if service is None:
            self._reset_stats()
            return

        try:
            stats = service.get_stats()
            last_op = service.get_last_operation()
            self._display_stats(stats, last_op, service)
        except Exception as e:
            logger.error(f"Fehler beim Lesen der TNP-Statistiken: {e}")
            self._reset_stats()

    def _display_stats(self, stats: dict, last_op, service):
        """Zeigt die Statistiken an."""
        total_shapes = stats.get('total_shapes', 0)

        if total_shapes == 0:
            self._update_visibility(False)
            return

        self._update_visibility(True)

        # Status-Werte
        for key, label in self._status_labels.items():
            value = stats.get(key, 0)
            label.setText(str(value))

        # Letzte Operation
        if last_op:
            op_text = f"""
<b>Type:</b> {last_op.operation_type}<br>
<b>Feature:</b> {last_op.feature_id[:16]}...<br>
<b>Inputs:</b> {len(last_op.input_shape_ids)} shapes<br>
<b>Outputs:</b> {len(last_op.output_shape_ids)} shapes
"""
            self._last_op_label.setText(op_text)
            self._last_op_label.setStyleSheet("color: #cccccc;")
        else:
            self._last_op_label.setText(tr("No operations recorded"))
            self._last_op_label.setStyleSheet("color: #888888; font-style: italic;")

        # Feature Liste (die letzten 5)
        features = list(service._by_feature.keys()) if hasattr(service, '_by_feature') else []
        if features:
            feature_text = "<br>".join([
                f"• <code>{f[:20]}...</code>" 
                for f in features[-5:]
            ])
            if len(features) > 5:
                feature_text += f"<br><i>...and {len(features) - 5} more</i>"
            self._feature_list.setText(feature_text)
            self._feature_list.setStyleSheet("color: #cccccc; font-family: monospace;")
        else:
            self._feature_list.setText(tr("No features registered"))
            self._feature_list.setStyleSheet("color: #888888;")

    def _reset_stats(self):
        """Setzt alle Statistik-Anzeigen zurück."""
        for label in self._status_labels.values():
            label.setText("0")

        self._last_op_label.setText(tr("No operations yet"))
        self._last_op_label.setStyleSheet("color: #888888; font-style: italic;")

        self._feature_list.setText(tr("No features registered"))
        self._feature_list.setStyleSheet("color: #888888;")

        self._update_visibility(False)

    def refresh(self, body):
        """Alias für update_stats() zur Konsistenz."""
        self.update_stats(body)


class TNPStatsDialog(QWidget):
    """
    Standalone-Dialog für detaillierte TNP-Statistiken.

    Kann als separates Fenster oder als Dock-Widget verwendet werden.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TNP v4.0 Statistics")
        self.setMinimumSize(350, 450)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._stats_panel = TNPStatsPanel(self)
        layout.addWidget(self._stats_panel)

    def update_stats(self, body):
        """Aktualisiert die Statistiken."""
        self._stats_panel.update_stats(body)
