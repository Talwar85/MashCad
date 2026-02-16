"""
MashCad - Status Bar Widget
Moderne Statusleiste nach Figma-Design mit Koordinaten, Tool-Info, Grid und Zoom.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt
from gui.design_tokens import DesignTokens
from i18n import tr


class MashCadStatusBar(QWidget):
    """Statusleiste unten im Hauptfenster."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        bg = DesignTokens.COLOR_BG_PANEL.name()
        border = DesignTokens.COLOR_BORDER.name()
        muted = DesignTokens.COLOR_TEXT_MUTED.name()
        self.setStyleSheet(f"""
            QWidget {{
                background: {bg};
                border-top: 1px solid {border};
            }}
            QLabel {{
                color: {muted};
                font-size: 11px;
                font-family: 'Segoe UI', sans-serif;
            }}
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
        self.status_dot.setStyleSheet(f"color: {DesignTokens.COLOR_SUCCESS.name()}; font-size: 10px;")
        left_layout.addWidget(self.status_dot)

        self.status_text = QLabel("Bereit")
        left_layout.addWidget(self.status_text)

        layout.addWidget(left_container)

        # Separator
        layout.addWidget(self._create_separator())

        # === Tool Indicator ===
        self.tool_label = QLabel("")
        layout.addWidget(self.tool_label)

        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet(f"color: {DesignTokens.COLOR_TEXT_MUTED.name()}; font-size: 11px; font-style: italic;")
        self.hint_label.setVisible(False)
        layout.addWidget(self.hint_label)

        layout.addStretch()

        # === Center: Coordinates ===
        self.coord_label = QLabel("X: 0.00   Y: 0.00   Z: 0.00")
        self.coord_label.setStyleSheet(f"color: {DesignTokens.COLOR_TEXT_SECONDARY.name()}; font-family: 'Consolas', monospace;")
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
        elevated = DesignTokens.COLOR_BG_ELEVATED.name()
        txt = DesignTokens.COLOR_TEXT_SECONDARY.name()
        self.dof_badge.setStyleSheet(f"""
            background: {elevated};
            border-radius: 4px;
            padding: 2px 8px;
            color: {txt};
        """)
        self.dof_badge.setVisible(False)
        layout.addWidget(self.dof_badge)

        self._dof_separator = self._create_separator()
        self._dof_separator.setVisible(False)
        layout.addWidget(self._dof_separator)

        self.zoom_badge = QLabel("100%")
        self.zoom_badge.setStyleSheet(f"""
            background: {elevated};
            border-radius: 4px;
            padding: 2px 8px;
            color: {txt};
        """)
        layout.addWidget(self.zoom_badge)

        layout.addWidget(self._create_separator())

        # FPS Counter
        self.fps_badge = QLabel("-- FPS")
        self.fps_badge.setStyleSheet(f"""
            background: {elevated};
            border-radius: 4px;
            padding: 2px 8px;
            color: {txt};
            font-family: 'Consolas', monospace;
        """)
        layout.addWidget(self.fps_badge)

        layout.addWidget(self._create_separator())
        
        # Strict Mode Badge (W3)
        self.strict_badge = QLabel("STRICT")
        self.strict_badge.setToolTip(tr("Strict Topology Fallback: No geometric guessing."))
        self.strict_badge.setStyleSheet(f"""
            background: {DesignTokens.COLOR_BG_ELEVATED.name()};
            border: 1px solid {DesignTokens.COLOR_PRIMARY.name()};
            border-radius: 4px;
            padding: 2px 6px;
            color: {DesignTokens.COLOR_PRIMARY.name()};
            font-size: 10px;
            font-weight: bold;
        """)
        self.strict_badge.setVisible(False)
        layout.addWidget(self.strict_badge)

    def _create_separator(self):
        """Erstellt einen vertikalen Separator."""
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedWidth(1)
        sep.setFixedHeight(16)
        sep.setStyleSheet(f"background: {DesignTokens.COLOR_BORDER.name()};")
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
        self.hint_label.setText("")
        self.hint_label.setVisible(False)

    def set_tool_hint(self, tool_name: str, hint: str = ""):
        """Sets tool name with contextual guidance hint."""
        if tool_name:
            self.tool_label.setText(tool_name)
            self.tool_label.setVisible(True)
            self.hint_label.setText(f"— {hint}" if hint else "")
            self.hint_label.setVisible(bool(hint))
        else:
            self.tool_label.setText("")
            self.tool_label.setVisible(False)
            self.hint_label.setText("")
            self.hint_label.setVisible(False)

    def set_mode(self, mode: str):
        """Setzt den aktuellen Modus (2D/3D)."""
        self.mode_label.setText(f"Modus: {mode}")

    def set_status(self, status: str, is_error: bool = False, status_class: str = "", severity: str = ""):
        """
        Setzt den Status-Text und -Farbe.

        W9 Paket D: Error UX v2 - Unterstützt status_class/severity aus Error-Envelope v2.

        Args:
            status: Der Status-Text
            is_error: Legacy Parameter (True = Error, False = Success)
            status_class: status_class aus Error-Envelope v2 (WARNING_RECOVERABLE, BLOCKED, CRITICAL, ERROR)
            severity: severity aus Error-Envelope v2 (warning, blocked, critical, error)
        """
        self.status_text.setText(status)

        # W9: Priorisiere status_class/severity über legacy is_error
        if status_class == "WARNING_RECOVERABLE" or severity == "warning":
            # Gelb für Recoverable Warnings
            self.status_dot.setStyleSheet(f"color: #eab308; font-size: 10px;")  # Gelb
        elif status_class == "BLOCKED" or severity == "blocked":
            # Orange für Blocked
            self.status_dot.setStyleSheet(f"color: #f97316; font-size: 10px;")  # Orange
        elif status_class == "CRITICAL" or severity == "critical":
            # Rot für Critical
            self.status_dot.setStyleSheet(f"color: {DesignTokens.COLOR_ERROR.name()}; font-size: 10px;")
        elif status_class == "ERROR" or severity == "error" or is_error:
            # Rot für Error
            self.status_dot.setStyleSheet(f"color: {DesignTokens.COLOR_ERROR.name()}; font-size: 10px;")
        else:
            # Grün für Success/Ready
            self.status_dot.setStyleSheet(f"color: {DesignTokens.COLOR_SUCCESS.name()}; font-size: 10px;")

    def set_grid(self, grid_size: float):
        """Setzt die Grid-Anzeige."""
        self.grid_label.setText(f"Grid: {grid_size:.0f}mm")

    def set_zoom(self, zoom_percent: int):
        """Setzt die Zoom-Anzeige."""
        self.zoom_badge.setText(f"{zoom_percent}%")

    def update_fps(self, fps: float):
        """Aktualisiert die FPS-Anzeige mit Farbcodierung."""
        elevated = DesignTokens.COLOR_BG_ELEVATED.name()

        if fps < 5:
            # Idle – System rendert nur bei Bedarf (ist korrekt, kein Problem)
            text = "idle"
            color = DesignTokens.COLOR_TEXT_MUTED.name()
        else:
            fps_int = int(round(fps))
            text = f"{fps_int} FPS"
            if fps >= 50:
                color = DesignTokens.COLOR_SUCCESS.name()       # Grün: gut
            elif fps >= 30:
                color = "#eab308"                                # Gelb: ok
            else:
                color = DesignTokens.COLOR_ERROR.name()          # Rot: schlecht

        self.fps_badge.setText(text)
        self.fps_badge.setStyleSheet(f"""
            background: {elevated};
            border-radius: 4px;
            padding: 2px 8px;
            color: {color};
            font-family: 'Consolas', monospace;
        """)

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
            self.dof_badge.setStyleSheet(f"""
                background: {DesignTokens.COLOR_BG_ELEVATED.name()};
                border-radius: 4px;
                padding: 2px 8px;
                color: {DesignTokens.COLOR_TEXT_MUTED.name()};
            """)
        elif dof == 0:
            # Fully Constrained - Grün
            self.dof_badge.setText("Fully Constrained")
            self.dof_badge.setStyleSheet(f"""
                background: {DesignTokens.COLOR_BG_ELEVATED.name()};
                border-radius: 4px;
                padding: 2px 8px;
                color: {DesignTokens.COLOR_SUCCESS.name()};
            """)
        else:
            # Under-Constrained - Gelb/Orange
            self.dof_badge.setText(f"DOF: {dof}")
            self.dof_badge.setStyleSheet(f"""
                background: {DesignTokens.COLOR_BG_ELEVATED.name()};
                border-radius: 4px;
                padding: 2px 8px;
                color: #eab308;  /* Gelb für Under-Constrained */
            """)

    def set_strict_mode(self, active: bool):
        """Enable/Disable Strict Mode badge."""
        self.strict_badge.setVisible(active)
