"""
MashCad - Operation Summary Widget
===================================

Zeigt nach jeder Kernel-Operation (Chamfer, Fillet, Boolean, Extrude, Shell, ...)
eine kompakte Zusammenfassung mit Geometry-Deltas.

Ziel: Beweisbare Transparenz statt blindes Vertrauen.

Beispiel (Erfolg):
    ✓ Chamfer D=0.8mm
    Volume: 20160 → 19847 mm³ (−1.6%)
    Flächen: 6 → 10 (+4)  |  Kanten: 12 → 20 (+8)

Beispiel (Warnung):
    ⚠ Fillet R=0.5mm — 2/4 Kanten bearbeitet
    Volume: UNVERÄNDERT
"""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont

from i18n import tr


# Farbpalette konsistent mit DesignTokens / notification.py
_COLORS = {
    "success": "#22c55e",
    "warning": "#f59e0b",
    "error": "#ef4444",
    "info": "#60a5fa",
    "bg": "#1e1e1e",
    "border": "#333",
    "text": "#e0e0e0",
    "text_dim": "#888",
    "text_value": "#ccc",
}


class OperationSummaryWidget(QFrame):
    """Kompaktes Overlay das nach Kernel-Operationen Geometry-Deltas zeigt.

    Wird vom MainWindow nach jeder Operation mit show_summary() aufgerufen.
    Verschwindet automatisch nach 5 Sekunden.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(320)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._anim = QPropertyAnimation(self, b"pos")
        self._target_pos = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._close_anim)

        self._setup_ui()

    def _setup_ui(self):
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(12, 10, 12, 10)
        self._main_layout.setSpacing(4)

        # Header-Zeile (Icon + Titel + Close)
        header = QHBoxLayout()
        header.setSpacing(8)
        self._icon_label = QLabel("✓")
        self._icon_label.setFixedWidth(20)
        header.addWidget(self._icon_label)

        self._title_label = QLabel("")
        self._title_label.setWordWrap(True)
        header.addWidget(self._title_label, 1)

        btn_close = QPushButton("✕")
        btn_close.setFlat(True)
        btn_close.setFixedSize(20, 20)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self._close_anim)
        btn_close.setStyleSheet("color: #666; border: none; background: transparent;")
        header.addWidget(btn_close)
        self._main_layout.addLayout(header)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #333;")
        sep.setFixedHeight(1)
        self._main_layout.addWidget(sep)

        # Metriken-Bereich
        self._volume_label = QLabel("")
        self._faces_edges_label = QLabel("")
        self._extra_label = QLabel("")
        self._progress_label = QLabel("")

        for lbl in (self._volume_label, self._faces_edges_label, self._extra_label, self._progress_label):
            lbl.setWordWrap(True)
            self._main_layout.addWidget(lbl)

        self._extra_label.hide()
        self._progress_label.hide()

    def _apply_style(self, accent_color: str):
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {_COLORS['bg']};
                border: 1px solid {_COLORS['border']};
                border-left: 4px solid {accent_color};
                border-radius: 4px;
            }}
            QLabel {{
                border: none;
                background: transparent;
                color: {_COLORS['text']};
                font-family: Segoe UI, sans-serif;
                font-size: 11px;
            }}
        """)
        self._icon_label.setStyleSheet(
            f"font-size: 16px; color: {accent_color}; font-weight: bold; border: none; background: transparent;"
        )
        self._title_label.setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {_COLORS['text']}; border: none; background: transparent;"
        )

    def show_summary(self, operation_name: str, pre_sig: dict, post_sig: dict,
                     feature=None, parent_widget=None):
        """Zeigt Operation-Summary an.

        Args:
            operation_name: z.B. "Chamfer D=0.8mm"
            pre_sig: {'volume': float, 'faces': int, 'edges': int} vor Operation
            post_sig: dito nach Operation
            feature: Optional Feature-Objekt für Status/Edge-Info
            parent_widget: Widget für Positionierung (z.B. MainWindow)
        """
        # Status ermitteln
        status = getattr(feature, "status", "OK") if feature else "OK"
        is_error = status == "ERROR"
        is_warning = status == "WARNING"

        if is_error:
            accent = _COLORS["error"]
            icon = "✕"
        elif is_warning:
            accent = _COLORS["warning"]
            icon = "⚠"
        else:
            accent = _COLORS["success"]
            icon = "✓"

        self._apply_style(accent)
        self._icon_label.setText(icon)
        self._title_label.setText(operation_name)

        # Volume Delta
        pre_vol = pre_sig.get("volume", 0)
        post_vol = post_sig.get("volume", 0)
        if pre_vol > 1e-12:
            vol_pct = ((post_vol - pre_vol) / pre_vol) * 100.0
            vol_changed = abs(vol_pct) > 0.01
        else:
            vol_pct = 0.0
            vol_changed = False

        if vol_changed:
            sign = "+" if vol_pct > 0 else ""
            self._volume_label.setText(
                f"Volume: {pre_vol:.0f} → {post_vol:.0f} mm³ ({sign}{vol_pct:.1f}%)"
            )
        else:
            warn = "  ⚠" if not is_error else ""
            self._volume_label.setText(f"Volume: {tr('unverändert')}{warn}")
        self._volume_label.setStyleSheet(
            f"color: {_COLORS['text_dim'] if not vol_changed else _COLORS['text_value']}; "
            f"font-size: 11px; border: none; background: transparent;"
        )

        # Faces/Edges Delta
        face_d = post_sig.get("faces", 0) - pre_sig.get("faces", 0)
        edge_d = post_sig.get("edges", 0) - pre_sig.get("edges", 0)
        parts = []
        if face_d != 0:
            parts.append(f"{tr('Flächen')}: {pre_sig.get('faces', 0)} → {post_sig.get('faces', 0)} ({'+' if face_d > 0 else ''}{face_d})")
        if edge_d != 0:
            parts.append(f"{tr('Kanten')}: {pre_sig.get('edges', 0)} → {post_sig.get('edges', 0)} ({'+' if edge_d > 0 else ''}{edge_d})")
        if parts:
            self._faces_edges_label.setText("  |  ".join(parts))
            self._faces_edges_label.show()
        else:
            self._faces_edges_label.setText(f"{tr('Flächen')}/{tr('Kanten')}: {tr('unverändert')}")
            self._faces_edges_label.show()
        self._faces_edges_label.setStyleSheet(
            f"color: {_COLORS['text_dim']}; font-size: 10px; border: none; background: transparent;"
        )

        # Extra-Info (Edge-Erfolgsrate bei Chamfer/Fillet)
        edge_info = ""
        if feature:
            gd = getattr(feature, '_geometry_delta', None)
            if gd:
                edges_ok = gd.get("edges_ok")
                edges_total = gd.get("edges_total")
                if edges_total is not None and edges_total > 0:
                    if edges_ok is not None and edges_ok < edges_total:
                        edge_info = f"⚠ {edges_ok}/{edges_total} {tr('Kanten bearbeitet')}"
                    elif edges_ok is not None:
                        edge_info = f"{edges_ok}/{edges_total} {tr('Kanten bearbeitet')}"

            # Hint aus status_details
            details = getattr(feature, "status_details", {}) or {}
            hint = details.get("hint", "")
            if hint and is_error:
                edge_info = f"{edge_info}\n{hint}" if edge_info else hint

        if edge_info:
            self._extra_label.setText(edge_info)
            self._extra_label.setStyleSheet(
                f"color: {accent}; font-size: 10px; border: none; background: transparent;"
            )
            self._extra_label.show()
        else:
            self._extra_label.hide()

        # Erfolgsrate-Bar
        if feature and not is_error:
            gd = getattr(feature, '_geometry_delta', None)
            if gd and gd.get("edges_total") and gd["edges_total"] > 0:
                rate = (gd.get("edges_ok", gd["edges_total"]) / gd["edges_total"]) * 100
                filled = int(rate / 10)
                bar = "▰" * filled + "▱" * (10 - filled)
                self._progress_label.setText(f"{bar} {rate:.0f}%")
                self._progress_label.setStyleSheet(
                    f"color: {accent}; font-size: 10px; border: none; background: transparent;"
                )
                self._progress_label.show()
            else:
                self._progress_label.hide()
        else:
            self._progress_label.hide()

        # Positionierung
        self.adjustSize()
        if parent_widget:
            pw_pos = parent_widget.mapToGlobal(QPoint(0, 0))
            pw_size = parent_widget.size()
            x = pw_pos.x() + pw_size.width() - self.width() - 20
            y = pw_pos.y() + pw_size.height() - self.height() - 40
            target = QPoint(x, y)
        else:
            target = QPoint(100, 100)

        self._target_pos = target
        start = QPoint(target.x(), target.y() + 20)
        self.move(start)
        self.show()
        self.raise_()

        self._anim.stop()
        self._anim.setDuration(250)
        self._anim.setStartValue(start)
        self._anim.setEndValue(target)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()

        # Auto-Close
        duration = 6000 if is_error else 4000
        self._timer.start(duration)

    def _close_anim(self):
        if not self._target_pos:
            self.hide()
            return
        end = QPoint(self._target_pos.x(), self._target_pos.y() + 20)
        self._anim.stop()
        self._anim.setDuration(200)
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(end)
        try:
            self._anim.finished.disconnect()
        except RuntimeError:
            pass
        self._anim.finished.connect(self.hide)
        self._anim.start()
