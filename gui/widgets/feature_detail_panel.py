"""
MashCad - Feature Detail Panel
===============================

Zeigt detaillierte Informationen zum ausgewählten Feature im Browser-Tree:
- Geometry-Delta (Volume, Faces, Edges vor/nach)
- Edge-Referenzen mit TNP-Status
- TNP Resolution-Qualität

Wird über Browser-Signal feature_selected angesteuert.
"""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

from loguru import logger
from i18n import tr
from gui.design_tokens import DesignTokens


_STATUS_ICONS = {
    "OK": ("●", "#22c55e"),
    "SUCCESS": ("●", "#22c55e"),
    "WARNING": ("●", "#f59e0b"),
    "ERROR": ("●", "#ef4444"),
    "SUPPRESSED": ("○", "#666"),
    "ROLLED_BACK": ("○", "#444"),
}


class FeatureDetailPanel(QFrame):
    """Panel mit Detail-Informationen zum ausgewählten Feature.

    Signals:
        highlight_edges_requested(list): Edge-Indices zum Highlighten im Viewport.
    """

    highlight_edges_requested = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {DesignTokens.COLOR_BG_PANEL.name()};
                border-top: 1px solid {DesignTokens.COLOR_BORDER.name()};
            }}
            QLabel {{
                color: {DesignTokens.COLOR_TEXT_PRIMARY.name() if hasattr(DesignTokens, 'COLOR_TEXT_PRIMARY') else '#ccc'};
                font-size: 10px;
                background: transparent;
                border: none;
            }}
        """)
        self._current_feature = None
        self._current_body = None
        self._current_doc = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Title
        self._title = QLabel(tr("Feature Details"))
        self._title.setStyleSheet("font-weight: bold; font-size: 11px;")
        layout.addWidget(self._title)

        # Status
        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        # Geometry Section
        self._geo_header = QLabel(f"── {tr('Geometrie')} ──")
        self._geo_header.setStyleSheet("color: #888; font-size: 9px; margin-top: 4px;")
        layout.addWidget(self._geo_header)

        self._geo_volume = QLabel("")
        self._geo_faces = QLabel("")
        self._geo_edges = QLabel("")
        layout.addWidget(self._geo_volume)
        layout.addWidget(self._geo_faces)
        layout.addWidget(self._geo_edges)

        # Edge References Section
        self._edge_header = QLabel(f"── {tr('Kanten-Referenzen')} ──")
        self._edge_header.setStyleSheet("color: #888; font-size: 9px; margin-top: 4px;")
        layout.addWidget(self._edge_header)

        self._edge_scroll = QScrollArea()
        self._edge_scroll.setWidgetResizable(True)
        self._edge_scroll.setMaximumHeight(120)
        self._edge_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._edge_content = QWidget()
        self._edge_layout = QVBoxLayout(self._edge_content)
        self._edge_layout.setContentsMargins(0, 0, 0, 0)
        self._edge_layout.setSpacing(1)
        self._edge_scroll.setWidget(self._edge_content)
        layout.addWidget(self._edge_scroll)

        # TNP Section
        self._tnp_header = QLabel(f"── {tr('TNP Resolution')} ──")
        self._tnp_header.setStyleSheet("color: #888; font-size: 9px; margin-top: 4px;")
        layout.addWidget(self._tnp_header)

        self._tnp_method = QLabel("")
        self._tnp_quality = QLabel("")
        layout.addWidget(self._tnp_method)
        layout.addWidget(self._tnp_quality)

        # Actions
        btn_row = QHBoxLayout()
        self._btn_show_edges = QPushButton(tr("Kanten anzeigen"))
        self._btn_show_edges.setFixedHeight(22)
        self._btn_show_edges.setStyleSheet(
            "QPushButton { background: #333; color: #ccc; border: 1px solid #555; border-radius: 3px; font-size: 10px; padding: 2px 8px; }"
            "QPushButton:hover { background: #444; color: white; }"
        )
        self._btn_show_edges.clicked.connect(self._on_show_edges)
        btn_row.addWidget(self._btn_show_edges)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()

        # Initial: Alles verstecken bis Feature ausgewählt
        self._hide_all_sections()

    def _hide_all_sections(self):
        self._status_label.hide()
        self._geo_header.hide()
        self._geo_volume.hide()
        self._geo_faces.hide()
        self._geo_edges.hide()
        self._edge_header.hide()
        self._edge_scroll.hide()
        self._tnp_header.hide()
        self._tnp_method.hide()
        self._tnp_quality.hide()
        self._btn_show_edges.hide()

    def show_feature(self, feature, body=None, doc=None):
        """Zeigt Details für das ausgewählte Feature."""
        self._current_feature = feature
        self._current_body = body
        self._current_doc = doc

        if feature is None:
            self._title.setText(tr("Feature Details"))
            self._hide_all_sections()
            return

        self._title.setText(feature.name)

        # Status
        status = getattr(feature, "status", "OK") or "OK"
        icon, color = _STATUS_ICONS.get(status, ("●", "#888"))
        msg = getattr(feature, "status_message", "") or ""
        status_text = f"{icon} {status}"
        if msg:
            status_text += f"  —  {msg[:80]}"
        self._status_label.setText(status_text)
        self._status_label.setStyleSheet(f"color: {color}; font-size: 10px; border: none; background: transparent;")
        self._status_label.show()

        # Geometry Delta
        gd = getattr(feature, '_geometry_delta', None)
        if gd:
            vol_before = gd.get("volume_before", 0)
            vol_after = gd.get("volume_after", 0)
            vol_pct = gd.get("volume_pct", 0)
            if vol_before > 0 and vol_pct != 0:
                sign = "+" if vol_pct > 0 else ""
                self._geo_volume.setText(f"Volume: {vol_before:.0f} → {vol_after:.0f} mm³ ({sign}{vol_pct:.1f}%)")
            elif vol_before == 0 and vol_after > 0:
                self._geo_volume.setText(f"Volume: {vol_after:.0f} mm³ ({tr('neu')})")
            else:
                self._geo_volume.setText(f"Volume: {tr('unverändert')}")

            fd = gd.get("faces_delta", 0)
            self._geo_faces.setText(
                f"{tr('Flächen')}: {gd.get('faces_before', '?')} → {gd.get('faces_after', '?')} ({'+' if fd > 0 else ''}{fd})"
            )
            ed = gd.get("edges_delta", 0)
            self._geo_edges.setText(
                f"{tr('Kanten')}: {gd.get('edges_before', '?')} → {gd.get('edges_after', '?')} ({'+' if ed > 0 else ''}{ed})"
            )
            self._geo_header.show()
            self._geo_volume.show()
            self._geo_faces.show()
            self._geo_edges.show()
        else:
            self._geo_header.hide()
            self._geo_volume.hide()
            self._geo_faces.hide()
            self._geo_edges.hide()

        # Edge References
        edge_indices = getattr(feature, 'edge_indices', None)
        has_edges = edge_indices and len(edge_indices) > 0
        if has_edges:
            self._show_edge_references(feature, body)
            self._edge_header.show()
            self._edge_scroll.show()
            self._btn_show_edges.show()
        else:
            self._edge_header.hide()
            self._edge_scroll.hide()
            self._btn_show_edges.hide()

        # TNP Section
        if doc and hasattr(doc, '_shape_naming_service') and body:
            self._show_tnp_section(feature, body, doc)
        else:
            self._tnp_header.hide()
            self._tnp_method.hide()
            self._tnp_quality.hide()

    def _show_edge_references(self, feature, body):
        """Zeigt Edge-Referenzen mit Index und Länge."""
        # Alte Labels entfernen
        while self._edge_layout.count():
            item = self._edge_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        edge_indices = feature.edge_indices or []
        solid = body._build123d_solid if body else None
        all_edges = list(solid.edges()) if solid else []

        for idx in edge_indices[:12]:  # Max 12 anzeigen
            if 0 <= idx < len(all_edges):
                e = all_edges[idx]
                try:
                    c = e.center()
                    length = float(e.length)
                    text = f"● Edge[{idx}]: L={length:.1f}mm  ({c.X:.1f}, {c.Y:.1f}, {c.Z:.1f})"
                    color = "#22c55e"
                except Exception:
                    text = f"● Edge[{idx}]: {tr('Fehler beim Lesen')}"
                    color = "#f59e0b"
            else:
                text = f"✕ Edge[{idx}]: {tr('UNGÜLTIG')} (max={len(all_edges) - 1})"
                color = "#ef4444"

            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {color}; font-size: 9px; font-family: Consolas, monospace; border: none; background: transparent;")
            self._edge_layout.addWidget(lbl)

        if len(edge_indices) > 12:
            more = QLabel(f"  +{len(edge_indices) - 12} {tr('weitere')}")
            more.setStyleSheet("color: #666; font-size: 9px; border: none; background: transparent;")
            self._edge_layout.addWidget(more)

    def _show_tnp_section(self, feature, body, doc):
        """Zeigt TNP Resolution-Details für dieses Feature."""
        try:
            report = doc._shape_naming_service.get_health_report(body)
        except Exception:
            self._tnp_header.hide()
            self._tnp_method.hide()
            self._tnp_quality.hide()
            return

        # Finde Feature im Report
        feat_report = None
        feat_id = getattr(feature, 'id', None)
        feat_name = feature.name
        for fr in report.get("features", []):
            if fr.get("feature_id") == feat_id or fr.get("feature_name") == feat_name:
                feat_report = fr
                break

        if not feat_report:
            self._tnp_header.hide()
            self._tnp_method.hide()
            self._tnp_quality.hide()
            return

        # Resolution-Methoden aus Refs
        methods = set()
        ok_count = int(feat_report.get("ok", 0))
        fallback_count = int(feat_report.get("fallback", 0))
        broken_count = int(feat_report.get("broken", 0))
        total = ok_count + fallback_count + broken_count

        for ref in feat_report.get("refs", []):
            m = ref.get("method", "")
            if m:
                methods.add(m)

        method_str = ", ".join(sorted(methods)) if methods else tr("keine")
        self._tnp_method.setText(f"{tr('Methode')}: {method_str}")
        self._tnp_method.show()

        # Qualitäts-Dots
        if total > 0:
            quality_pct = (ok_count / total) * 100
            dots_ok = "●" * ok_count
            dots_fb = "●" * fallback_count
            dots_br = "●" * broken_count
            parts = []
            if dots_ok:
                parts.append(f'<span style="color:#22c55e">{dots_ok}</span>')
            if dots_fb:
                parts.append(f'<span style="color:#f59e0b">{dots_fb}</span>')
            if dots_br:
                parts.append(f'<span style="color:#ef4444">{dots_br}</span>')
            dot_html = " ".join(parts)
            self._tnp_quality.setText(f"{tr('Qualität')}: {dot_html} {quality_pct:.0f}%")
            self._tnp_quality.setTextFormat(Qt.RichText)
        else:
            self._tnp_quality.setText(f"{tr('Qualität')}: {tr('keine Referenzen')}")
        self._tnp_quality.show()
        self._tnp_header.show()

    def _on_show_edges(self):
        """Emittet Signal zum Highlighten der Feature-Kanten im Viewport."""
        if self._current_feature:
            indices = getattr(self._current_feature, 'edge_indices', None) or []
            if indices:
                self.highlight_edges_requested.emit(list(indices))

    def clear(self):
        """Räumt das Panel auf."""
        self.show_feature(None)
