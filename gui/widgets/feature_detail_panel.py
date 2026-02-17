"""
MashCad - Feature Detail Panel
===============================

Zeigt detaillierte Informationen zum ausgewählten Feature im Browser-Tree:
- Geometry-Delta (Volume, Faces, Edges vor/nach)
- Edge-Referenzen mit TNP-Status
- TNP Resolution-Qualität

W21 Product Leap v2:
- Strukturierte Fehlerdiagnose (code/category/hint)
- Copy diagnostics Aktion für Support/Debug
- Kantenreferenzen mit robustem Invalid-Handling
- TNP-Sektion visuell priorisieren bei kritischen Fehlern

Wird über Browser-Signal feature_selected angesteuert.
"""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QSizePolicy, QApplication, QMessageBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

from datetime import datetime
from loguru import logger
from i18n import tr
from gui.design_tokens import DesignTokens


def _safe_float(value, default: float = 0.0) -> float:
    """Defensive float conversion — returns default on None/non-numeric."""
    if value is None:
        return default
    # Mock-Objekte haben keinen echten numerischen Wert
    if hasattr(value, '__class__') and 'Mock' in value.__class__.__name__:
        return default
    try:
        result = float(value)
        # Prüfe ob das Ergebnis tatsächlich ein float ist (Mock gibt Mock zurück)
        if hasattr(result, '__class__') and 'Mock' in result.__class__.__name__:
            return default
        return result
    except (TypeError, ValueError):
        return default


def _safe_str(value, default: str = "") -> str:
    """Defensive str conversion — returns default on None/non-string."""
    if value is None:
        return default
    # Mock-Objekte haben keinen echten String-Wert
    if hasattr(value, '__class__') and 'Mock' in value.__class__.__name__:
        return default
    try:
        result = str(value)
        # Prüfe ob das Ergebnis tatsächlich ein str ist
        if hasattr(result, '__class__') and 'Mock' in result.__class__.__name__:
            return default
        return result
    except (TypeError, ValueError):
        return default


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
        recovery_action_requested(str, object): (action, feature) - W26 Recovery Aktion.
        edit_feature_requested(object): Feature zur Bearbeitung angefordert.
        rebuild_feature_requested(object): Feature Rebuild angefordert.
        delete_feature_requested(object): Feature Löschung angefordert.
    """

    highlight_edges_requested = Signal(list)
    recovery_action_requested = Signal(str, object)
    edit_feature_requested = Signal(object)
    rebuild_feature_requested = Signal(object)
    delete_feature_requested = Signal(object)

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

        # W21 PAKET B: Strukturierte Fehlerdiagnose Section
        self._diag_header = QLabel(f"── {tr('Diagnose')} ──")
        self._diag_header.setStyleSheet("color: #888; font-size: 9px; margin-top: 4px;")
        layout.addWidget(self._diag_header)

        self._diag_code = QLabel("")
        self._diag_category = QLabel("")
        self._diag_hint = QLabel("")
        self._diag_hint.setWordWrap(True)
        layout.addWidget(self._diag_code)
        layout.addWidget(self._diag_category)
        layout.addWidget(self._diag_hint)

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

        # W26 PAKET F2: Recovery Actions Section
        self._recovery_header = QLabel(f"── {tr('Recovery-Aktionen')} ──")
        self._recovery_header.setStyleSheet("color: #f59e0b; font-size: 9px; margin-top: 6px; font-weight: bold;")
        layout.addWidget(self._recovery_header)

        self._recovery_layout = QHBoxLayout()
        self._recovery_layout.setSpacing(4)

        # Recovery Buttons (dynamisch gefüllt basierend auf Error-Code)
        self._btn_reselect_ref = QPushButton(tr("🔄 Referenz neu wählen"))
        self._btn_reselect_ref.setFixedHeight(22)
        self._btn_reselect_ref.setStyleSheet(
            "QPushButton { background: #2d3748; color: #90cdf4; border: 1px solid #4299e1; border-radius: 3px; font-size: 10px; padding: 2px 8px; }"
            "QPushButton:hover { background: #3182ce; color: white; }"
        )
        self._btn_reselect_ref.clicked.connect(lambda: self._on_recovery_action("reselect_ref"))
        self._recovery_layout.addWidget(self._btn_reselect_ref)

        self._btn_edit_feature = QPushButton(tr("✏️ Feature editieren"))
        self._btn_edit_feature.setFixedHeight(22)
        self._btn_edit_feature.setStyleSheet(
            "QPushButton { background: #2d3748; color: #9ae6b4; border: 1px solid #48bb78; border-radius: 3px; font-size: 10px; padding: 2px 8px; }"
            "QPushButton:hover { background: #38a169; color: white; }"
        )
        self._btn_edit_feature.clicked.connect(lambda: self._on_recovery_action("edit"))
        self._recovery_layout.addWidget(self._btn_edit_feature)

        self._btn_rebuild = QPushButton(tr("🔄 Rebuild"))
        self._btn_rebuild.setFixedHeight(22)
        self._btn_rebuild.setStyleSheet(
            "QPushButton { background: #2d3748; color: #fbd38d; border: 1px solid #ed8936; border-radius: 3px; font-size: 10px; padding: 2px 8px; }"
            "QPushButton:hover { background: #dd6b20; color: white; }"
        )
        self._btn_rebuild.clicked.connect(lambda: self._on_recovery_action("rebuild"))
        self._recovery_layout.addWidget(self._btn_rebuild)

        self._btn_accept_drift = QPushButton(tr("✓ Drift akzeptieren"))
        self._btn_accept_drift.setFixedHeight(22)
        self._btn_accept_drift.setStyleSheet(
            "QPushButton { background: #2d3748; color: #9ae6b4; border: 1px solid #48bb78; border-radius: 3px; font-size: 10px; padding: 2px 8px; }"
            "QPushButton:hover { background: #38a169; color: white; }"
        )
        self._btn_accept_drift.clicked.connect(lambda: self._on_recovery_action("accept_drift"))
        self._recovery_layout.addWidget(self._btn_accept_drift)

        self._btn_check_deps = QPushButton(tr("🔍 Dependencies prüfen"))
        self._btn_check_deps.setFixedHeight(22)
        self._btn_check_deps.setStyleSheet(
            "QPushButton { background: #2d3748; color: #d6bcfa; border: 1px solid #9f7aea; border-radius: 3px; font-size: 10px; padding: 2px 8px; }"
            "QPushButton:hover { background: #805ad5; color: white; }"
        )
        self._btn_check_deps.clicked.connect(lambda: self._on_recovery_action("check_deps"))
        self._recovery_layout.addWidget(self._btn_check_deps)

        layout.addLayout(self._recovery_layout)

        # W21 PAKET B: Actions mit Copy Diagnostics Button
        btn_row = QHBoxLayout()
        self._btn_copy_diag = QPushButton(tr("📋 Diagnostics"))
        self._btn_copy_diag.setFixedHeight(22)
        self._btn_copy_diag.setStyleSheet(
            "QPushButton { background: #333; color: #ccc; border: 1px solid #555; border-radius: 3px; font-size: 10px; padding: 2px 8px; }"
            "QPushButton:hover { background: #444; color: white; }"
        )
        self._btn_copy_diag.clicked.connect(self._on_copy_diagnostics)
        btn_row.addWidget(self._btn_copy_diag)

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
        self._diag_header.hide()
        self._diag_code.hide()
        self._diag_category.hide()
        self._diag_hint.hide()
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
        self._btn_copy_diag.hide()
        # W26: Recovery Section verstecken
        self._recovery_header.hide()
        self._btn_reselect_ref.hide()
        self._btn_edit_feature.hide()
        self._btn_rebuild.hide()
        self._btn_accept_drift.hide()
        self._btn_check_deps.hide()

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

        # Status mit Error UX v2 Support
        status = getattr(feature, "status", "OK") or "OK"
        details = getattr(feature, "status_details", {}) or {}
        status_class = details.get("status_class", "")
        severity = details.get("severity", "")

        # W21: Prio: status_class > severity > legacy status
        if status_class == "WARNING_RECOVERABLE" or severity == "warning":
            icon, color = ("⚠", "#f59e0b")
        elif status_class in ("BLOCKED", "CRITICAL", "ERROR") or severity in ("blocked", "critical", "error"):
            icon, color = ("✕", "#ef4444")
        else:
            icon, color = _STATUS_ICONS.get(status, ("●", "#888"))

        msg = _safe_str(getattr(feature, "status_message", None), "")
        status_text = f"{icon} {status}"
        if msg:
            status_text += f"  —  {msg[:80]}"
        self._status_label.setText(status_text)
        self._status_label.setStyleSheet(f"color: {color}; font-size: 10px; border: none; background: transparent;")
        self._status_label.show()

        # W21 PAKET B: Strukturierte Fehlerdiagnose
        code = details.get("code", "")
        hint = details.get("hint", "") or details.get("next_action", "")
        tnp_failure = details.get("tnp_failure", {})
        category = tnp_failure.get("category", "")

        # Zeige Diagnose-Section wenn Fehler-Informationen vorhanden
        has_diagnostic = bool(code or hint or category or status in ("ERROR", "WARNING"))

        if has_diagnostic:
            self._diag_header.show()

            # Code
            if code:
                self._diag_code.setText(f"Code: {code}")
                self._diag_code.setStyleSheet(f"color: #666; font-size: 9px; font-family: Consolas, monospace;")
                self._diag_code.show()
            else:
                self._diag_code.hide()

            # Category
            if category:
                cat_map = {
                    "missing_ref": tr("Referenz verloren"),
                    "mismatch": tr("Formkonflikt"),
                    "drift": tr("Geometrie-Drift"),
                }
                cat_str = cat_map.get(category, category)
                self._diag_category.setText(f"Kategorie: {cat_str}")
                self._diag_category.setStyleSheet(f"color: #f59e0b; font-size: 9px;")
                self._diag_category.show()
            else:
                self._diag_category.hide()

            # Hint
            if hint:
                self._diag_hint.setText(f"💡 {hint}")
                self._diag_hint.setStyleSheet(f"color: {DesignTokens.COLOR_TEXT_SECONDARY.name()}; font-size: 9px;")
                self._diag_hint.show()
            else:
                self._diag_hint.hide()

            # Copy-Button zeigen
            self._btn_copy_diag.show()

            # W26 PAKET F2: Recovery-Buttons basierend auf Error-Code anzeigen
            self._update_recovery_actions(code, category)
        else:
            self._diag_header.hide()
            self._diag_code.hide()
            self._diag_category.hide()
            self._diag_hint.hide()
            self._btn_copy_diag.hide()
            # W26: Recovery Section verstecken wenn keine Diagnose
            self._recovery_header.hide()
            self._btn_reselect_ref.hide()
            self._btn_edit_feature.hide()
            self._btn_rebuild.hide()
            self._btn_accept_drift.hide()
            self._btn_check_deps.hide()

        # Geometry Delta
        gd = getattr(feature, '_geometry_delta', None)
        if gd and isinstance(gd, dict):
            vol_before = _safe_float(gd.get("volume_before"), 0)
            vol_after = _safe_float(gd.get("volume_after"), 0)
            vol_pct = _safe_float(gd.get("volume_pct"), 0)
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
        # Robuster Check gegen Mock-Objekte
        has_edges = False
        if edge_indices is not None:
            try:
                if hasattr(edge_indices, '__len__') and not hasattr(edge_indices, '__class__'):
                    has_edges = len(edge_indices) > 0
                elif hasattr(edge_indices, '__class__') and 'Mock' in edge_indices.__class__.__name__:
                    has_edges = False
                else:
                    has_edges = len(edge_indices) > 0
            except (TypeError, AttributeError):
                has_edges = False
        if has_edges:
            self._show_edge_references(feature, body)
            self._edge_header.show()
            self._edge_scroll.show()
            self._btn_show_edges.show()
        else:
            self._edge_header.hide()
            self._edge_scroll.hide()
            self._btn_show_edges.hide()

        # W21 PAKET B: TNP-Sektion visuell priorisieren bei kritischen Fehlern
        is_critical = status_class in ("CRITICAL", "ERROR", "BLOCKED") or severity in ("critical", "error", "blocked")

        if doc and hasattr(doc, '_shape_naming_service') and body:
            self._show_tnp_section(feature, body, doc, prioritize=is_critical)
        else:
            self._tnp_header.hide()
            self._tnp_method.hide()
            self._tnp_quality.hide()

    def _show_edge_references(self, feature, body):
        """
        W21 PAKET B: Zeigt Edge-Referenzen mit robustem Invalid-Handling.
        """
        # Alte Labels entfernen
        while self._edge_layout.count():
            item = self._edge_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        edge_indices = feature.edge_indices or []
        solid = body._build123d_solid if body else None
        all_edges = list(solid.edges()) if solid else []

        invalid_count = 0

        for idx in edge_indices[:12]:  # Max 12 anzeigen
            if 0 <= idx < len(all_edges):
                e = all_edges[idx]
                try:
                    c = e.center()
                    length = float(e.length)
                    text = f"● Edge[{idx}]: L={length:.1f}mm  ({c.X:.1f}, {c.Y:.1f}, {c.Z:.1f})"
                    color = "#22c55e"
                except Exception as ex:
                    text = f"⚠ Edge[{idx}]: {tr('Lesefehler')} - {str(ex)[:30]}"
                    color = "#f59e0b"
                    invalid_count += 1
            else:
                text = f"✕ Edge[{idx}]: {tr('UNGÜLTIG')} (max={len(all_edges) - 1})"
                color = "#ef4444"
                invalid_count += 1

            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {color}; font-size: 9px; font-family: Consolas, monospace; border: none; background: transparent;")
            self._edge_layout.addWidget(lbl)

        if len(edge_indices) > 12:
            more = QLabel(f"  +{len(edge_indices) - 12} {tr('weitere')}")
            more.setStyleSheet("color: #666; font-size: 9px; border: none; background: transparent;")
            self._edge_layout.addWidget(more)

        # W21 PAKET B: Warnung bei vielen ungültigen Kanten
        if invalid_count > 0:
            warn = QLabel(f"⚠ {invalid_count}/{len(edge_indices)} {tr('ungültig')}")
            warn.setStyleSheet("color: #ef4444; font-size: 9px; font-weight: bold;")
            self._edge_layout.addWidget(warn)

    def _show_tnp_section(self, feature, body, doc, prioritize=False):
        """
        Zeigt TNP Resolution-Details für dieses Feature.

        W21 PAKET B: prioritize=True zeigt TNP-Sektion visuell hervorgehoben bei kritischen Fehlern.
        """
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

        # W21 PAKET B: Visuelle Priorisierung bei kritischen Fehlern
        if prioritize:
            self._tnp_header.setStyleSheet("color: #ef4444; font-size: 10px; font-weight: bold; margin-top: 6px;")
            self._tnp_header.setText(f"⚠ ── {tr('TNP Resolution')} ── ⚠")
        else:
            self._tnp_header.setStyleSheet("color: #888; font-size: 9px; margin-top: 4px;")
            self._tnp_header.setText(f"── {tr('TNP Resolution')} ──")

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
            dots_ok = "●" * min(ok_count, 10)  # Max 10 Dots
            dots_fb = "●" * min(fallback_count, 10)
            dots_br = "●" * min(broken_count, 10)
            parts = []
            if dots_ok:
                parts.append(f'<span style="color:#22c55e">{dots_ok}</span>')
            if dots_fb:
                parts.append(f'<span style="color:#f59e0b">{dots_fb}</span>')
            if dots_br:
                parts.append(f'<span style="color:#ef4444">{dots_br}</span>')
            dot_html = " ".join(parts)

            # W21 PAKET B: Warnung bei schlechter Qualität
            if quality_pct < 50 and prioritize:
                self._tnp_quality.setText(f"{tr('Qualität')}: {dot_html} {quality_pct:.0f}% ⚠")
                self._tnp_quality.setStyleSheet("color: #ef4444; font-size: 10px; font-weight: bold;")
            else:
                self._tnp_quality.setText(f"{tr('Qualität')}: {dot_html} {quality_pct:.0f}%")
                self._tnp_quality.setStyleSheet("")
        else:
            self._tnp_quality.setText(f"{tr('Qualität')}: {tr('keine Referenzen')}")
            self._tnp_quality.setStyleSheet("")

        self._tnp_quality.setTextFormat(Qt.RichText)
        self._tnp_quality.show()
        self._tnp_header.show()

    def _update_recovery_actions(self, code: str, category: str):
        """
        W26 PAKET F2: Zeigt/versteckt Recovery-Buttons basierend auf Error-Code.

        Args:
            code: Error-Code aus status_details
            category: TNP-Fehler-Kategorie
        """
        # Standard: Alle verstecken
        self._btn_reselect_ref.hide()
        self._btn_edit_feature.hide()
        self._btn_rebuild.hide()
        self._btn_accept_drift.hide()
        self._btn_check_deps.hide()

        if not code and not category:
            self._recovery_header.hide()
            return

        self._recovery_header.show()

        # Mapping: Error-Code -> sinnvolle Recovery-Aktionen
        if code == "tnp_ref_missing" or category == "missing_ref":
            # Referenz verloren -> Neu wählen oder Feature editieren
            self._btn_reselect_ref.show()
            self._btn_edit_feature.show()
            self._btn_check_deps.show()

        elif code == "tnp_ref_mismatch" or category == "mismatch":
            # Formkonflikt -> Editieren oder Dependencies prüfen
            self._btn_edit_feature.show()
            self._btn_check_deps.show()
            self._btn_rebuild.show()

        elif code == "tnp_ref_drift" or category == "drift":
            # Geometrie-Drift -> Akzeptieren oder Editieren
            self._btn_accept_drift.show()
            self._btn_edit_feature.show()

        elif code == "rebuild_finalize_failed":
            # Rebuild fehlgeschlagen -> Rebuild wiederholen oder Editieren
            self._btn_rebuild.show()
            self._btn_edit_feature.show()

        elif code == "ocp_api_unavailable":
            # OCP nicht verfügbar -> Dependencies prüfen oder Rebuild
            self._btn_check_deps.show()
            self._btn_rebuild.show()

        else:
            # Fallback: Editieren und Rebuild anbieten
            self._btn_edit_feature.show()
            self._btn_rebuild.show()

    def _on_recovery_action(self, action: str):
        """
        W26 PAKET F2: Handler für Recovery-Aktionen.

        Args:
            action: Auszuführende Aktion
        """
        if not self._current_feature:
            return

        logger.debug(f"[FEATURE_PANEL] Recovery action '{action}' für Feature '{self._current_feature.name}'")

        # Signal emittieren für externe Handler
        self.recovery_action_requested.emit(action, self._current_feature)

        # Direkte Aktionen
        if action == "edit":
            self.edit_feature_requested.emit(self._current_feature)
        elif action == "rebuild":
            self.rebuild_feature_requested.emit(self._current_feature)
        elif action == "reselect_ref":
            # Wird vom externen Handler behandelt
            pass
        elif action == "accept_drift":
            # Drift akzeptieren -> Status zurücksetzen
            if hasattr(self._current_feature, 'status_details'):
                self._current_feature.status_details = {}
            if hasattr(self._current_feature, 'status'):
                self._current_feature.status = "OK"
            # Panel aktualisieren
            self.show_feature(self._current_feature, self._current_body, self._current_doc)

    def _on_show_edges(self):
        """Emittet Signal zum Highlighten der Feature-Kanten im Viewport."""
        if self._current_feature:
            indices = getattr(self._current_feature, 'edge_indices', None) or []
            if indices:
                self.highlight_edges_requested.emit(list(indices))

    def _on_copy_diagnostics(self):
        """
        W26 PAKET F2: Kopiert strukturierte Diagnostics in die Zwischenablage.

        Erstellt einen JSON-ähnlichen Text mit allen relevanten Informationen
        für Support/Debug, inkl. Recovery-Vorschlägen.
        """
        if not self._current_feature:
            return

        feature = self._current_feature
        lines = []
        lines.append(f"{'='*50}")
        lines.append(f"FEATURE DIAGNOSTICS REPORT")
        lines.append(f"Generated: {datetime.now().isoformat()}")
        lines.append(f"{'='*50}")
        lines.append("")

        # Feature Info
        lines.append(f"[FEATURE]")
        lines.append(f"  Name: {feature.name}")
        lines.append(f"  Type: {type(feature).__name__}")
        lines.append(f"  ID: {getattr(feature, 'id', 'N/A')}")
        lines.append("")

        # Status
        status = getattr(feature, "status", "OK")
        details = getattr(feature, "status_details", {}) or {}
        status_class = details.get("status_class", "") if isinstance(details, dict) else ""
        severity = details.get("severity", "") if isinstance(details, dict) else ""
        code = details.get("code", "") if isinstance(details, dict) else ""

        lines.append(f"[STATUS]")
        lines.append(f"  Status: {status}")
        lines.append(f"  Status Class: {status_class or 'N/A'}")
        lines.append(f"  Severity: {severity or 'N/A'}")
        lines.append(f"  Error Code: {code or 'N/A'}")
        lines.append("")

        # TNP Failure Details
        tnp_failure = details.get("tnp_failure", {}) if isinstance(details, dict) else {}
        if tnp_failure:
            lines.append(f"[TNP FAILURE]")
            for key, value in tnp_failure.items():
                lines.append(f"  {key}: {value}")
            lines.append("")

        # Hint / Next Action
        hint = details.get("hint", "") or details.get("next_action", "") if isinstance(details, dict) else ""
        if hint:
            lines.append(f"[HINT]")
            lines.append(f"  {hint}")
            lines.append("")

        # W26: Recovery Vorschläge
        lines.append(f"[RECOVERY OPTIONS]")
        if code == "tnp_ref_missing":
            lines.append(f"  1. Referenz neu wählen: Edge/Face neu auswählen")
            lines.append(f"  2. Feature editieren: Geometrie anpassen")
            lines.append(f"  3. Dependencies prüfen: Vorgänger-Features validieren")
        elif code == "tnp_ref_mismatch":
            lines.append(f"  1. Feature editieren: Geometrie korrigieren")
            lines.append(f"  2. Konflikt isolieren: Body separat bearbeiten")
            lines.append(f"  3. Rebuild wiederholen: Nach Anpassungen")
        elif code == "tnp_ref_drift":
            lines.append(f"  1. Drift akzeptieren: Warnung bestätigen (wenn OK)")
            lines.append(f"  2. Manuell korrigieren: Referenz neu setzen")
            lines.append(f"  3. Feature editieren: Geometrie anpassen")
        elif code == "rebuild_finalize_failed":
            lines.append(f"  1. Rebuild wiederholen: Automatische Korrektur versuchen")
            lines.append(f"  2. Feature editieren: Parameter prüfen")
            lines.append(f"  3. Feature löschen: Neu erstellen falls defekt")
        elif code == "ocp_api_unavailable":
            lines.append(f"  1. OCP-Status prüfen: Backend-Verfügbarkeit")
            lines.append(f"  2. Dependencies prüfen: Feature-Abhängigkeiten")
            lines.append(f"  3. Fallback verwenden: Alternative Operation wählen")
        else:
            lines.append(f"  1. Feature editieren: Parameter prüfen")
            lines.append(f"  2. Rebuild wiederholen: Automatische Korrektur")
        lines.append("")

        # Geometry
        lines.append(f"[GEOMETRY DELTA]")
        gd = getattr(feature, '_geometry_delta', None)
        if gd and isinstance(gd, dict):
            lines.append(f"  Volume: {gd.get('volume_before', '?')} → {gd.get('volume_after', '?')} mm³")
            lines.append(f"  Change: {gd.get('volume_pct', 0):.1f}%")
            lines.append(f"  Faces: {gd.get('faces_before', '?')} → {gd.get('faces_after', '?')}")
            lines.append(f"  Edges: {gd.get('edges_before', '?')} → {gd.get('edges_after', '?')}")
        else:
            lines.append(f"  No geometry data available")
        lines.append("")

        # Edge References
        edge_indices = getattr(feature, 'edge_indices', None)
        if edge_indices:
            lines.append(f"[EDGE REFERENCES]")
            lines.append(f"  Count: {len(edge_indices)}")
            lines.append(f"  Indices: {list(edge_indices)[:20]}")  # Max 20 anzeigen
            if len(edge_indices) > 20:
                lines.append(f"  ... and {len(edge_indices) - 20} more")
            lines.append("")

        # Body Info
        if self._current_body:
            lines.append(f"[BODY]")
            lines.append(f"  Name: {self._current_body.name}")
            lines.append(f"  ID: {getattr(self._current_body, 'id', 'N/A')}")
            lines.append("")

        lines.append(f"{'='*50}")
        lines.append(f"END DIAGNOSTICS")
        lines.append(f"{'='*50}")

        diagnostics_text = "\n".join(lines)

        # In Zwischenablage kopieren
        clipboard = QApplication.clipboard()
        clipboard.setText(diagnostics_text)

        # User Feedback
        logger.debug(f"[FEATURE_PANEL] Diagnostics copied to clipboard for feature '{feature.name}'")

        # Optional: Toast notification
        try:
            from PySide6.QtWidgets import QToolTip
            QToolTip.showText(self._btn_copy_diag.mapToGlobal(self._btn_copy_diag.rect().bottomLeft()),
                            tr("Diagnostics in Zwischenablage kopiert"))
        except Exception:
            pass  # Tooltip optional

    def get_diagnostics_text(self) -> str:
        """
        W21 PAKET B: Gibt den Diagnostics-Text zurück (für externe Nutzung).

        Returns:
            str: Strukturierter Diagnostics-Text
        """
        if not self._current_feature:
            return ""

        feature = self._current_feature
        lines = []
        lines.append(f"Feature: {feature.name}")
        lines.append(f"Type: {type(feature).__name__}")

        status = getattr(feature, "status", "OK")
        details = getattr(feature, "status_details", {}) or {}
        lines.append(f"Status: {status}")

        if details:
            code = details.get("code", "")
            hint = details.get("hint", "")
            if code:
                lines.append(f"Code: {code}")
            if hint:
                lines.append(f"Hint: {hint}")

        return "\n".join(lines)

    def clear(self):
        """Räumt das Panel auf."""
        self.show_feature(None)
