"""
MashCad - TNP Statistics Panel
==============================

Zeigt Statistiken zur Topological Naming Problem (TNP) Auflösung.
Hilft Benutzern zu verstehen, wie zuverlässig Feature-Referenzen sind.

Verwendung:
    panel = TNPStatsPanel(parent)
    panel.update_stats(body)  # Body mit TNPTracker
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QFrame, QGroupBox, QGridLayout
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from loguru import logger
from i18n import tr


class TNPStatsPanel(QWidget):
    """
    Panel zur Anzeige von TNP (Topological Naming Problem) Statistiken.

    Zeigt:
    - Gesamterfolgsrate der Referenz-Auflösung
    - Auflösungen nach Strategie (History, Hash, Geometrie)
    - Anzahl fehlgeschlagener Auflösungen
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Erstellt das UI-Layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Header
        header = QLabel(tr("TNP Reference Statistics"))
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(11)
        header.setFont(header_font)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Erfolgsrate-Anzeige
        success_group = QFrame()
        success_group.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        success_group.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #454545;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        success_layout = QVBoxLayout(success_group)

        self._success_label = QLabel(tr("Success Rate: ---%%"))
        self._success_label.setStyleSheet("font-size: 14px; color: #ffffff;")
        self._success_label.setAlignment(Qt.AlignCenter)
        success_layout.addWidget(self._success_label)

        self._success_bar = QProgressBar()
        self._success_bar.setRange(0, 100)
        self._success_bar.setValue(0)
        self._success_bar.setTextVisible(False)
        self._success_bar.setFixedHeight(8)
        self._success_bar.setStyleSheet("""
            QProgressBar {
                background-color: #3d3d3d;
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #107c10;
                border-radius: 4px;
            }
        """)
        success_layout.addWidget(self._success_bar)

        layout.addWidget(success_group)

        # Strategie-Details
        strategy_group = QGroupBox(tr("Resolution Strategies"))
        strategy_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #454545;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        strategy_layout = QGridLayout(strategy_group)
        strategy_layout.setSpacing(8)

        # Strategie-Labels
        strategies = [
            (tr("History"), "#0078d4", "history_success"),
            (tr("Hash"), "#9b59b6", "hash_success"),
            (tr("Geometry"), "#f39c12", "geometry_success"),
            (tr("Failed"), "#d13438", "failed"),
        ]

        self._strategy_labels = {}
        for i, (name, color, key) in enumerate(strategies):
            # Farbiger Punkt
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 12px;")
            strategy_layout.addWidget(dot, i, 0)

            # Name
            name_label = QLabel(name)
            name_label.setStyleSheet("color: #cccccc;")
            strategy_layout.addWidget(name_label, i, 1)

            # Wert
            value_label = QLabel("0")
            value_label.setStyleSheet("color: #ffffff; font-weight: bold;")
            value_label.setAlignment(Qt.AlignRight)
            strategy_layout.addWidget(value_label, i, 2)
            self._strategy_labels[key] = value_label

        layout.addWidget(strategy_group)

        # Total-Anzeige
        total_layout = QHBoxLayout()
        total_label = QLabel(tr("Total:"))
        total_label.setStyleSheet("color: #aaaaaa;")
        self._total_label = QLabel(tr("0 Resolutions"))
        self._total_label.setStyleSheet("color: #ffffff;")
        total_layout.addWidget(total_label)
        total_layout.addStretch()
        total_layout.addWidget(self._total_label)
        layout.addLayout(total_layout)

        # Platzhalter-Nachricht
        self._placeholder = QLabel(tr("No statistics available.\nPerform operations to collect data."))
        self._placeholder.setStyleSheet("color: #888888; font-style: italic;")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setWordWrap(True)
        layout.addWidget(self._placeholder)

        layout.addStretch()

        # Initial state
        self._update_visibility(False)

    def _update_visibility(self, has_data: bool):
        """Zeigt/versteckt die Statistik-Widgets basierend auf Datenverfügbarkeit."""
        self._placeholder.setVisible(not has_data)

    def update_stats(self, body):
        """
        Aktualisiert die Anzeige mit Statistiken vom Body's TNPTracker.

        Args:
            body: Body-Objekt mit _tnp_tracker Attribut
        """
        if body is None:
            self._reset_stats()
            return

        # TNP Tracker holen
        tracker = getattr(body, '_tnp_tracker', None)
        if tracker is None:
            self._reset_stats()
            return

        try:
            stats = tracker.get_statistics()
            # Füge Referenz-Anzahl hinzu (zeigt dass etwas getrackt wird)
            ref_count = len(tracker._references) if hasattr(tracker, '_references') else 0
            stats['tracked_references'] = ref_count
            self._display_stats(stats)
        except Exception as e:
            logger.error(f"Fehler beim Lesen der TNP-Statistiken: {e}")
            self._reset_stats()

    def _display_stats(self, stats: dict):
        """Zeigt die Statistiken an."""
        total = stats.get("total", 0)

        if total == 0:
            self._update_visibility(False)
            return

        self._update_visibility(True)

        # Erfolgsrate
        success_rate = stats.get("success_rate", 0)
        self._success_label.setText(f"{tr('Success Rate:')} {success_rate:.1f}%")
        self._success_bar.setValue(int(success_rate))

        # Farbe der Progress-Bar basierend auf Erfolgsrate
        if success_rate >= 90:
            color = "#107c10"  # Grün
        elif success_rate >= 70:
            color = "#f39c12"  # Orange
        else:
            color = "#d13438"  # Rot

        self._success_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #3d3d3d;
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 4px;
            }}
        """)

        # Strategie-Werte
        for key, label in self._strategy_labels.items():
            value = stats.get(key, 0)
            label.setText(str(value))

        # Total
        self._total_label.setText(f"{total} {tr('Resolutions')}")

    def _reset_stats(self):
        """Setzt alle Statistik-Anzeigen zurück."""
        self._success_label.setText(tr("Success Rate: ---%%"))
        self._success_bar.setValue(0)

        for label in self._strategy_labels.values():
            label.setText("0")

        self._total_label.setText(tr("0 Resolutions"))
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
        self.setWindowTitle("TNP Statistiken")
        self.setMinimumSize(300, 400)

        layout = QVBoxLayout(self)
        self._stats_panel = TNPStatsPanel(self)
        layout.addWidget(self._stats_panel)

    def update_stats(self, body):
        """Aktualisiert die Statistiken."""
        self._stats_panel.update_stats(body)
