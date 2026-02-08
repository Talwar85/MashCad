"""
MashCad - TNP Reference Health Panel
=====================================

Zeigt den Zustand aller topologischen Referenzen im aktiven Body.
Statt roher Debug-Zahlen sieht der User:
- Gesamt-Status (Alle Referenzen stabil / X gebrochen)
- Feature-Liste mit Ampel-Status (grün/gelb/rot)
- Detail-Info pro Feature bei Auswahl
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QListWidget, QListWidgetItem, QSizePolicy,
    QPushButton
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QIcon
from loguru import logger
from i18n import tr
from gui.design_tokens import DesignTokens


STATUS_COLORS = {
    'ok': '#2ecc71',
    'fallback': '#f39c12',
    'broken': '#e74c3c',
    'no_refs': '#666666',
}

STATUS_DOTS = {
    'ok': '●',
    'fallback': '●',
    'broken': '●',
    'no_refs': '○',
}

METHOD_LABELS = {
    'index': tr('Index'),
    'direct': tr('Direkt'),
    'history': tr('History'),
    'brepfeat': tr('BRepFeat'),
    'geometric': tr('Geometrisch'),
    'rebuild': tr('Rebuild OK'),
    'unresolved': tr('Nicht gefunden'),
}


class TNPStatsPanel(QWidget):
    """
    Panel zur Anzeige des TNP-Referenz-Gesundheitsstatus.

    Zeigt pro Body:
    - Zusammenfassung (Alle stabil / N gebrochen)
    - Feature-Liste mit Ampel-Status
    - Detail-Info bei Auswahl
    """

    body_pick_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_report = None
        self._picking_active = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # === Title Row (immer sichtbar) ===
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_label = QLabel(tr("Referenzen"))
        title_label.setStyleSheet(f"color: {DesignTokens.COLOR_TEXT_PRIMARY.name()}; font-weight: bold; font-size: 11px;")
        title_row.addWidget(title_label)
        title_row.addStretch()

        self._pick_btn = QPushButton("⊕")
        self._pick_btn.setToolTip(tr("Body im Viewport auswählen"))
        self._pick_btn.setFixedSize(22, 22)
        self._pick_btn.setStyleSheet(f"""
            QPushButton {{
                background: {DesignTokens.COLOR_BG_PANEL.name()};
                color: {DesignTokens.COLOR_TEXT_SECONDARY.name()};
                border: 1px solid {DesignTokens.COLOR_BORDER.name()};
                border-radius: 3px;
                font-size: 14px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background: {DesignTokens.COLOR_BG_ELEVATED.name()};
                color: {DesignTokens.COLOR_PRIMARY.name()};
            }}
            QPushButton:checked {{
                background: {DesignTokens.COLOR_PRIMARY.name()};
                color: #ffffff;
            }}
        """)
        self._pick_btn.setCheckable(True)
        self._pick_btn.clicked.connect(self._on_pick_clicked)
        title_row.addWidget(self._pick_btn)
        layout.addLayout(title_row)

        # === Summary Card ===
        self._summary_frame = QFrame()
        self._summary_frame.setStyleSheet(f"""
            QFrame {{
                background: {DesignTokens.COLOR_BG_ELEVATED.name()};
                border: 1px solid {DesignTokens.COLOR_BORDER.name()};
                border-radius: 4px;
                padding: 8px;
            }}
        """)
        summary_layout = QVBoxLayout(self._summary_frame)
        summary_layout.setContentsMargins(8, 6, 8, 6)
        summary_layout.setSpacing(4)

        body_row = QHBoxLayout()
        self._body_name_label = QLabel("")
        self._body_name_label.setStyleSheet(f"color: {DesignTokens.COLOR_TEXT_SECONDARY.name()}; font-size: 10px; border: none;")
        body_row.addWidget(self._body_name_label)
        body_row.addStretch()
        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet(f"color: {STATUS_COLORS['ok']}; font-size: 14px; border: none;")
        body_row.addWidget(self._status_dot)
        summary_layout.addLayout(body_row)

        self._summary_label = QLabel(tr("Kein Body ausgewählt"))
        self._summary_label.setStyleSheet(f"color: {DesignTokens.COLOR_TEXT_MUTED.name()}; font-size: 10px; border: none;")
        self._summary_label.setWordWrap(True)
        summary_layout.addWidget(self._summary_label)

        self._counts_label = QLabel("")
        self._counts_label.setStyleSheet(f"color: {DesignTokens.COLOR_TEXT_MUTED.name()}; font-size: 10px; border: none;")
        self._counts_label.setVisible(False)
        summary_layout.addWidget(self._counts_label)

        layout.addWidget(self._summary_frame)

        # === Feature List ===
        self._feature_list = QListWidget()
        self._feature_list.setStyleSheet(f"""
            QListWidget {{
                background: {DesignTokens.COLOR_BG_PANEL.name()};
                border: 1px solid {DesignTokens.COLOR_BORDER.name()};
                border-radius: 4px;
                font-size: 11px;
                font-family: 'Segoe UI';
            }}
            QListWidget::item {{
                padding: 4px 6px;
                border-bottom: 1px solid {DesignTokens.COLOR_BORDER.name()};
            }}
            QListWidget::item:selected {{
                background: {DesignTokens.COLOR_BG_ELEVATED.name()};
            }}
            QListWidget::item:hover {{
                background: {DesignTokens.COLOR_BG_ELEVATED.name()};
            }}
        """)
        self._feature_list.currentRowChanged.connect(self._on_feature_selected)
        layout.addWidget(self._feature_list, stretch=1)

        # === Detail Area ===
        self._detail_frame = QFrame()
        self._detail_frame.setStyleSheet(f"""
            QFrame {{
                background: {DesignTokens.COLOR_BG_ELEVATED.name()};
                border: 1px solid {DesignTokens.COLOR_BORDER.name()};
                border-radius: 4px;
                padding: 6px;
            }}
        """)
        detail_layout = QVBoxLayout(self._detail_frame)
        detail_layout.setContentsMargins(8, 6, 8, 6)
        detail_layout.setSpacing(2)

        self._detail_label = QLabel("")
        self._detail_label.setStyleSheet(f"color: {DesignTokens.COLOR_TEXT_SECONDARY.name()}; font-size: 10px; border: none;")
        self._detail_label.setWordWrap(True)
        detail_layout.addWidget(self._detail_label)

        self._detail_frame.setVisible(False)
        layout.addWidget(self._detail_frame)

        # === Placeholder ===
        self._placeholder = QLabel(tr(
            "Kein Body ausgewählt.\n\n"
            "Klicke ⊕ um einen Body\n"
            "im Viewport auszuwählen."
        ))
        self._placeholder.setStyleSheet(f"color: {DesignTokens.COLOR_TEXT_MUTED.name()}; font-style: italic; padding: 20px;")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setWordWrap(True)
        layout.addWidget(self._placeholder)

        self._set_has_data(False)

    def _on_pick_clicked(self, checked: bool):
        if checked:
            self._picking_active = True
            self.body_pick_requested.emit()
        else:
            self._picking_active = False

    def set_picking_active(self, active: bool):
        self._picking_active = active
        self._pick_btn.blockSignals(True)
        self._pick_btn.setChecked(active)
        self._pick_btn.blockSignals(False)

    def _set_has_data(self, has_data: bool):
        self._placeholder.setVisible(not has_data)
        self._summary_frame.setVisible(has_data)
        self._feature_list.setVisible(has_data)

    def update_stats(self, body):
        """
        Aktualisiert das Panel mit dem Health-Report eines Bodies.
        Kompatibel mit dem alten API-Aufruf.
        """
        if body is None:
            self._reset()
            return

        document = getattr(body, '_document', None)
        if document is None:
            self._reset()
            return

        service = getattr(document, '_shape_naming_service', None)
        if service is None:
            self._reset()
            return

        try:
            report = service.get_health_report(body)
            self._display_report(report)
        except Exception as e:
            logger.error(f"TNP Health Report fehlgeschlagen: {e}")
            self._reset()

    def _display_report(self, report: dict):
        self._current_report = report
        has_refs = report['ok'] + report['fallback'] + report['broken'] > 0

        # Body name
        body_name = report.get('body_name', '')
        self._body_name_label.setText(f"▸ {body_name}" if body_name else "")

        # Pick-Modus beenden
        self.set_picking_active(False)

        # Summary
        status = report['status']
        self._status_dot.setStyleSheet(f"color: {STATUS_COLORS.get(status, '#666')}; font-size: 14px; border: none;")

        if not has_refs:
            self._summary_label.setText(tr("Keine Referenzen"))
            self._summary_label.setStyleSheet(f"color: {DesignTokens.COLOR_TEXT_MUTED.name()}; font-size: 10px; border: none;")
            self._counts_label.setVisible(False)
        elif status == 'ok':
            self._summary_label.setText(tr("Alle Referenzen stabil"))
            self._summary_label.setStyleSheet(f"color: {STATUS_COLORS['ok']}; font-size: 10px; border: none;")
            self._counts_label.setVisible(False)
        else:
            parts = []
            if report['broken'] > 0:
                parts.append(f"<span style='color:{STATUS_COLORS['broken']}'>{report['broken']} gebrochen</span>")
            if report['fallback'] > 0:
                parts.append(f"<span style='color:{STATUS_COLORS['fallback']}'>{report['fallback']} Fallback</span>")
            if report['ok'] > 0:
                parts.append(f"<span style='color:{STATUS_COLORS['ok']}'>{report['ok']} OK</span>")
            self._summary_label.setText(" · ".join(parts))
            self._summary_label.setStyleSheet(f"font-size: 10px; border: none;")

        # Feature list
        self._feature_list.blockSignals(True)
        self._feature_list.clear()

        for feat in report['features']:
            feat_status = feat['status']
            dot = STATUS_DOTS.get(feat_status, '○')
            color = STATUS_COLORS.get(feat_status, '#666')

            ref_count = feat['ok'] + feat['fallback'] + feat['broken']
            if feat_status == 'no_refs':
                suffix = ""
            elif feat_status == 'ok':
                suffix = f"  ({ref_count})"
            elif feat_status == 'broken':
                suffix = f"  ({feat['broken']} ✗)"
            else:
                suffix = f"  ({feat['fallback']} ⚠)"

            item = QListWidgetItem(f"{dot}  {feat['name']}{suffix}")
            item.setForeground(QColor(color))
            self._feature_list.addItem(item)

        self._feature_list.blockSignals(False)

        self._detail_frame.setVisible(False)
        self._set_has_data(True)

    def _on_feature_selected(self, row: int):
        if self._current_report is None or row < 0:
            self._detail_frame.setVisible(False)
            return

        features = self._current_report.get('features', [])
        if row >= len(features):
            self._detail_frame.setVisible(False)
            return

        feat = features[row]
        refs = feat.get('refs', [])

        if not refs:
            self._detail_label.setText(tr("Keine topologischen Referenzen"))
            self._detail_frame.setVisible(True)
            return

        lines = [f"<b>{feat['name']}</b> ({feat['type']})"]
        lines.append(f"Referenzen: {len(refs)}  "
                      f"(<span style='color:{STATUS_COLORS['ok']}'>✓{feat['ok']}</span>"
                      f" <span style='color:{STATUS_COLORS['fallback']}'>⚠{feat['fallback']}</span>"
                      f" <span style='color:{STATUS_COLORS['broken']}'>✗{feat['broken']}</span>)")
        lines.append("")

        for ref in refs[:8]:
            dot_color = STATUS_COLORS.get(ref['status'], '#666')
            method = METHOD_LABELS.get(ref['method'], ref['method'])
            lines.append(f"<span style='color:{dot_color}'>●</span> {ref['kind']} → {method}")

        if len(refs) > 8:
            lines.append(f"<i>…+{len(refs) - 8} weitere</i>")

        self._detail_label.setText("<br>".join(lines))
        self._detail_frame.setVisible(True)

    def _reset(self):
        self._current_report = None
        self._feature_list.clear()
        self._detail_frame.setVisible(False)
        self._summary_label.setText(tr("Kein Body ausgewählt"))
        self._summary_label.setStyleSheet(f"color: {DesignTokens.COLOR_TEXT_MUTED.name()}; font-size: 10px; border: none;")
        self._status_dot.setStyleSheet(f"color: #666; font-size: 14px; border: none;")
        self._counts_label.setVisible(False)
        self._set_has_data(False)

    def refresh(self, body):
        """Alias für update_stats()."""
        self.update_stats(body)


class TNPStatsDialog(QWidget):
    """Standalone-Dialog für TNP-Referenz-Status."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TNP References")
        self.setMinimumSize(300, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._stats_panel = TNPStatsPanel(self)
        layout.addWidget(self._stats_panel)

    def update_stats(self, body):
        self._stats_panel.update_stats(body)
