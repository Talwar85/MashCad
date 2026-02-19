"""
Export Preflight Dialog
=======================

Zeigt Export-Validierungs-Ergebnisse an und erlaubt dem User
zu entscheiden ob trotz Warnungen exportiert werden soll.

Phase 1: Export Foundation (PR-002)

Usage:
    from gui.dialogs.export_preflight_dialog import ExportPreflightDialog
    from modeling.export_validator import ExportValidator
    
    result = ExportValidator.validate_for_export(solid)
    dlg = ExportPreflightDialog(result, parent=self)
    if dlg.exec() == QDialog.Accepted:
        # User will trotzdem exportieren
        do_export()

Author: Kimi (Phase 1 Implementation)
Date: 2026-02-19
Branch: feature/v1-ux-aiB
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTreeWidget, QTreeWidgetItem,
    QGroupBox, QTextEdit, QCheckBox, QSpacerItem,
    QSizePolicy, QHeaderView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from loguru import logger

from modeling.export_validator import ValidationSeverity, ValidationCheckType
from gui.design_tokens import DesignTokens
from i18n import tr


class ExportPreflightDialog(QDialog):
    """
    Dialog zur Anzeige von Export-Validierungs-Ergebnissen.
    
    Zeigt Errors, Warnings und Infos in einer übersichtlichen
    Baumstruktur an und erlaubt dem User den Export trotzdem
    zu starten (bei non-critical Issues).
    """
    
    def __init__(self, validation_result, parent=None, export_format="STL"):
        """
        Args:
            validation_result: ValidationResult vom ExportValidator
            parent: Parent Widget
            export_format: Name des Export-Formats für den Titel
        """
        super().__init__(parent)
        self.result = validation_result
        self.export_format = export_format
        self._setup_ui()
        self._populate_data()
        
    def _setup_ui(self):
        """Erstellt die UI."""
        # Titel basierend auf Status
        if not self.result.is_valid:
            title = tr("Export blockiert - Kritische Probleme gefunden")
        elif not self.result.is_printable:
            title = tr("Export Warnung - 3D-Druck könnte problematisch sein")
        else:
            title = tr("Export Prüfung")
        
        self.setWindowTitle(title)
        self.setMinimumWidth(550)
        self.setMinimumHeight(450)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Status Header
        self._create_status_header(layout)
        
        # Zusammenfassung
        self._create_summary_box(layout)
        
        # Issues Tree
        self._create_issues_tree(layout)
        
        # Detail View
        self._create_detail_view(layout)
        
        # Buttons
        self._create_buttons(layout)
        
        # Styling
        self.setStyleSheet(DesignTokens.stylesheet_dialog())
        
    def _create_status_header(self, layout):
        """Erstellt den Status-Header mit Icon."""
        header_layout = QHBoxLayout()
        
        # Status Icon
        self.status_icon = QLabel()
        self.status_icon.setFixedSize(48, 48)
        self.status_icon.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(self.status_icon)
        
        # Status Text
        self.status_label = QLabel()
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        header_layout.addWidget(self.status_label, stretch=1)
        
        layout.addLayout(header_layout)
        
    def _create_summary_box(self, layout):
        """Erstellt die Zusammenfassungs-Box."""
        group = QGroupBox(tr("Zusammenfassung"))
        group_layout = QVBoxLayout(group)
        
        # Status Zeilen
        self.summary_closed = QLabel()
        self.summary_bounds = QLabel()
        self.summary_degenerate = QLabel()
        
        group_layout.addWidget(self.summary_closed)
        group_layout.addWidget(self.summary_bounds)
        group_layout.addWidget(self.summary_degenerate)
        
        layout.addWidget(group)
        
    def _create_issues_tree(self, layout):
        """Erstellt den Issues Tree."""
        group = QGroupBox(tr("Gefundene Probleme"))
        group_layout = QVBoxLayout(group)
        
        self.issues_tree = QTreeWidget()
        self.issues_tree.setHeaderLabels([tr("Typ"), tr("Problem"), tr("Vorschlag")])
        self.issues_tree.setColumnWidth(0, 100)
        self.issues_tree.setColumnWidth(1, 250)
        self.issues_tree.setColumnWidth(2, 200)
        self.issues_tree.header().setStretchLastSection(True)
        self.issues_tree.itemSelectionChanged.connect(self._on_issue_selected)
        
        group_layout.addWidget(self.issues_tree)
        layout.addWidget(group, stretch=1)
        
    def _create_detail_view(self, layout):
        """Erstellt die Detail-Ansicht."""
        self.detail_group = QGroupBox(tr("Details"))
        detail_layout = QVBoxLayout(self.detail_group)
        
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMaximumHeight(80)
        self.detail_text.setStyleSheet("""
            QTextEdit {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        
        detail_layout.addWidget(self.detail_text)
        layout.addWidget(self.detail_group)
        
    def _create_buttons(self, layout):
        """Erstellt die Buttons."""
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        # Cancel Button
        self.cancel_btn = QPushButton(tr("Abbrechen"))
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        # Export Anyway Button (nur bei Warnings)
        self.export_btn = QPushButton(tr("Trotzdem exportieren"))
        self.export_btn.setObjectName("primary")
        self.export_btn.clicked.connect(self.accept)
        self.export_btn.setVisible(False)  # Default hidden
        btn_layout.addWidget(self.export_btn)
        
        # OK Button (nur wenn valid)
        self.ok_btn = QPushButton(tr("Exportieren"))
        self.ok_btn.setObjectName("primary")
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setVisible(False)  # Default hidden
        btn_layout.addWidget(self.ok_btn)
        
        layout.addLayout(btn_layout)
        
    def _populate_data(self):
        """Füllt die UI mit Validierungs-Daten."""
        # Status Icon und Text
        if not self.result.is_valid:
            # Rot - Blockiert
            self.status_icon.setText("✗")
            self.status_icon.setStyleSheet("""
                background-color: #fee;
                border-radius: 24px;
                color: #c00;
                font-size: 24px;
                font-weight: bold;
            """)
            self.status_label.setText(tr("Export kann nicht durchgeführt werden"))
            self.status_label.setStyleSheet("color: #c00; font-size: 14px; font-weight: bold;")
            self.cancel_btn.setText(tr("Schließen"))
            
        elif not self.result.is_printable:
            # Gelb - Warnung
            self.status_icon.setText("⚠")
            self.status_icon.setStyleSheet("""
                background-color: #ffeaa7;
                border-radius: 24px;
                color: #d63031;
                font-size: 24px;
                font-weight: bold;
            """)
            self.status_label.setText(tr("Export möglich aber problematisch für 3D-Druck"))
            self.status_label.setStyleSheet("color: #d63031; font-size: 14px; font-weight: bold;")
            self.export_btn.setVisible(True)
            
        else:
            # Grün - OK
            self.status_icon.setText("✓")
            self.status_icon.setStyleSheet("""
                background-color: #efe;
                border-radius: 24px;
                color: #0a0;
                font-size: 24px;
                font-weight: bold;
            """)
            self.status_label.setText(tr("Keine Probleme gefunden"))
            self.status_label.setStyleSheet("color: #0a0; font-size: 14px; font-weight: bold;")
            self.ok_btn.setVisible(True)
        
        # Zusammenfassung
        closed_text = "✓ Geschlossenes Volumen" if self.result.is_closed else "✗ Offenes Volumen"
        self.summary_closed.setText(closed_text)
        self.summary_closed.setStyleSheet(
            "color: #0a0;" if self.result.is_closed else "color: #c00;"
        )
        
        bounds_text = "✓ Keine offenen Kanten" if not self.result.has_free_bounds else "⚠ Offene Kanten vorhanden"
        self.summary_bounds.setText(bounds_text)
        self.summary_bounds.setStyleSheet(
            "color: #0a0;" if not self.result.has_free_bounds else "color: #d63031;"
        )
        
        if self.result.has_degenerate_faces:
            self.summary_degenerate.setText("✗ Degenerierte Faces gefunden")
            self.summary_degenerate.setStyleSheet("color: #c00;")
        else:
            self.summary_degenerate.setText("✓ Keine degenerierten Faces")
            self.summary_degenerate.setStyleSheet("color: #0a0;")
        
        # Issues Tree
        errors = self.result.get_errors()
        warnings = self.result.get_warnings()
        infos = self.result.get_info()
        
        # Error Node
        if errors:
            error_node = QTreeWidgetItem(self.issues_tree, [tr("Fehler"), f"{len(errors)}x", ""])
            error_node.setBackground(0, QColor("#fee"))
            error_node.setForeground(0, QColor("#c00"))
            for issue in errors:
                self._add_issue_item(error_node, issue)
            error_node.setExpanded(True)
        
        # Warning Node
        if warnings:
            warning_node = QTreeWidgetItem(self.issues_tree, [tr("Warnungen"), f"{len(warnings)}x", ""])
            warning_node.setBackground(0, QColor("#ffeaa7"))
            warning_node.setForeground(0, QColor("#d63031"))
            for issue in warnings:
                self._add_issue_item(warning_node, issue)
            warning_node.setExpanded(True)
        
        # Info Node
        if infos:
            info_node = QTreeWidgetItem(self.issues_tree, [tr("Informationen"), f"{len(infos)}x", ""])
            info_node.setBackground(0, QColor("#e3f2fd"))
            for issue in infos:
                self._add_issue_item(info_node, issue)
        
        if not errors and not warnings and not infos:
            item = QTreeWidgetItem(self.issues_tree, [tr("Keine Probleme"), "", ""])
            item.setForeground(0, QColor("#0a0"))
        
        self.issues_tree.expandAll()
        
    def _add_issue_item(self, parent, issue):
        """Fügt ein Issue-Item zum Tree hinzu."""
        item = QTreeWidgetItem(parent, [
            issue.check_type.value,
            issue.message,
            issue.suggestion or ""
        ])
        
        # Farbe basierend auf Severity
        if issue.severity == ValidationSeverity.ERROR:
            item.setForeground(1, QColor("#c00"))
        elif issue.severity == ValidationSeverity.WARNING:
            item.setForeground(1, QColor("#d63031"))
        
        # Speichere Issue für Detail-Ansicht
        item.setData(0, Qt.UserRole, issue)
        
    def _on_issue_selected(self):
        """Handler für Issue-Auswahl."""
        items = self.issues_tree.selectedItems()
        if not items:
            self.detail_text.clear()
            return
        
        item = items[0]
        issue = item.data(0, Qt.UserRole)
        
        if issue:
            detail = f"<b>{issue.check_type.value.upper()}</b><br>"
            detail += f"{issue.message}<br>"
            if issue.suggestion:
                detail += f"<br><i>💡 {issue.suggestion}</i>"
            if issue.entity_id:
                detail += f"<br><small>Entity: {issue.entity_id}</small>"
            if issue.location:
                detail += f"<br><small>Position: {issue.location}</small>"
            
            self.detail_text.setHtml(detail)
        else:
            self.detail_text.clear()


class QuickValidationIndicator(QLabel):
    """
    Kleines Status-Widget für schnelle Validierungs-Anzeige.
    
    Kann in Toolbars oder Panels eingebaut werden.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                border-radius: 12px;
                background-color: #eee;
            }
        """)
        self.setToolTip(tr("Export-Status: Nicht geprüft"))
        self._status = "unknown"
        
    def set_validating(self):
        """Zeigt Validierung läuft an."""
        self.setText("⟳")
        self.setStyleSheet("""
            QLabel {
                border-radius: 12px;
                background-color: #e3f2fd;
                color: #1976d2;
            }
        """)
        self.setToolTip(tr("Export-Status: Prüfung läuft..."))
        self._status = "validating"
        
    def set_valid(self):
        """Zeigt valides Ergebnis an."""
        self.setText("✓")
        self.setStyleSheet("""
            QLabel {
                border-radius: 12px;
                background-color: #efe;
                color: #0a0;
                font-weight: bold;
            }
        """)
        self.setToolTip(tr("Export-Status: OK - Bereit für Export"))
        self._status = "valid"
        
    def set_warning(self):
        """Zeigt Warnung an."""
        self.setText("⚠")
        self.setStyleSheet("""
            QLabel {
                border-radius: 12px;
                background-color: #ffeaa7;
                color: #d63031;
                font-weight: bold;
            }
        """)
        self.setToolTip(tr("Export-Status: Warnungen - Export möglich aber problematisch"))
        self._status = "warning"
        
    def set_error(self):
        """Zeigt Fehler an."""
        self.setText("✗")
        self.setStyleSheet("""
            QLabel {
                border-radius: 12px;
                background-color: #fee;
                color: #c00;
                font-weight: bold;
            }
        """)
        self.setToolTip(tr("Export-Status: Fehler - Export blockiert"))
        self._status = "error"
        
    def update_from_result(self, result):
        """Aktualisiert basierend auf ValidationResult."""
        if not result.is_valid:
            self.set_error()
        elif not result.is_printable:
            self.set_warning()
        else:
            self.set_valid()
            
    @property
    def status(self):
        """Aktueller Status."""
        return self._status
