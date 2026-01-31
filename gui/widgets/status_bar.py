"""
MashCad - Status Bar Widget
Moderne Statusleiste nach Figma-Design mit Koordinaten, Tool-Info, Grid und Zoom.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt


class MashCadStatusBar(QWidget):
    """Statusleiste unten im Hauptfenster."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet("""
            QWidget {
                background: #262626;
                border-top: 1px solid #404040;
            }
            QLabel {
                color: #a3a3a3;
                font-size: 11px;
                font-family: 'Segoe UI', sans-serif;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        # === Left: Status Indicator ===
        left_container = QWidget()
        left_layout = QHBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.status_dot = QLabel("\u25cf")  # ●
        self.status_dot.setStyleSheet("color: #22c55e; font-size: 10px;")
        left_layout.addWidget(self.status_dot)

        self.status_text = QLabel("Bereit")
        left_layout.addWidget(self.status_text)

        layout.addWidget(left_container)

        # Separator
        layout.addWidget(self._create_separator())

        # === Tool Indicator ===
        self.tool_label = QLabel("")
        layout.addWidget(self.tool_label)

        layout.addStretch()

        # === Center: Coordinates ===
        self.coord_label = QLabel("X: 0.00   Y: 0.00   Z: 0.00")
        self.coord_label.setStyleSheet("color: #d4d4d4; font-family: 'Consolas', monospace;")
        layout.addWidget(self.coord_label)

        layout.addStretch()

        # === Right: Grid, Mode, Zoom ===
        self.grid_label = QLabel("Grid: 10mm")
        layout.addWidget(self.grid_label)

        layout.addWidget(self._create_separator())

        self.mode_label = QLabel("Modus: 3D")
        layout.addWidget(self.mode_label)

        layout.addWidget(self._create_separator())

        # DOF Badge (nur im Sketch-Modus sichtbar)
        self.dof_badge = QLabel("")
        self.dof_badge.setStyleSheet("""
            background: #404040;
            border-radius: 4px;
            padding: 2px 8px;
            color: #d4d4d4;
        """)
        self.dof_badge.setVisible(False)
        layout.addWidget(self.dof_badge)

        self._dof_separator = self._create_separator()
        self._dof_separator.setVisible(False)
        layout.addWidget(self._dof_separator)

        self.zoom_badge = QLabel("100%")
        self.zoom_badge.setStyleSheet("""
            background: #404040;
            border-radius: 4px;
            padding: 2px 8px;
            color: #d4d4d4;
        """)
        layout.addWidget(self.zoom_badge)

    def _create_separator(self):
        """Erstellt einen vertikalen Separator."""
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedWidth(1)
        sep.setFixedHeight(16)
        sep.setStyleSheet("background: #404040;")
        return sep

    def update_coordinates(self, x: float, y: float, z: float):
        """Aktualisiert die Koordinatenanzeige."""
        self.coord_label.setText(f"X: {x:.2f}   Y: {y:.2f}   Z: {z:.2f}")

    def set_tool(self, tool_name: str):
        """Setzt das aktive Tool."""
        if tool_name:
            self.tool_label.setText(f"Werkzeug: {tool_name}")
            self.tool_label.setVisible(True)
        else:
            self.tool_label.setText("")
            self.tool_label.setVisible(False)

    def set_mode(self, mode: str):
        """Setzt den aktuellen Modus (2D/3D)."""
        self.mode_label.setText(f"Modus: {mode}")

    def set_status(self, status: str, is_error: bool = False):
        """Setzt den Status-Text und -Farbe."""
        self.status_text.setText(status)
        if is_error:
            self.status_dot.setStyleSheet("color: #ef4444; font-size: 10px;")
        else:
            self.status_dot.setStyleSheet("color: #22c55e; font-size: 10px;")

    def set_grid(self, grid_size: float):
        """Setzt die Grid-Anzeige."""
        self.grid_label.setText(f"Grid: {grid_size:.0f}mm")

    def set_zoom(self, zoom_percent: int):
        """Setzt die Zoom-Anzeige."""
        self.zoom_badge.setText(f"{zoom_percent}%")

    def set_dof(self, dof: int, visible: bool = True):
        """
        Setzt die DOF-Anzeige (Degrees of Freedom).

        Args:
            dof: Anzahl der Freiheitsgrade (-1 = Fehler/unbekannt)
            visible: Ob das Badge sichtbar sein soll (False im 3D-Modus)
        """
        self.dof_badge.setVisible(visible)
        self._dof_separator.setVisible(visible)

        if not visible:
            return

        if dof < 0:
            # Fehler oder unbekannt
            self.dof_badge.setText("DOF: ?")
            self.dof_badge.setStyleSheet("""
                background: #404040;
                border-radius: 4px;
                padding: 2px 8px;
                color: #a3a3a3;
            """)
        elif dof == 0:
            # Fully Constrained - Grün
            self.dof_badge.setText("Fully Constrained")
            self.dof_badge.setStyleSheet("""
                background: #166534;
                border-radius: 4px;
                padding: 2px 8px;
                color: #22c55e;
            """)
        else:
            # Under-Constrained - Gelb/Orange
            self.dof_badge.setText(f"DOF: {dof}")
            self.dof_badge.setStyleSheet("""
                background: #854d0e;
                border-radius: 4px;
                padding: 2px 8px;
                color: #eab308;
            """)
