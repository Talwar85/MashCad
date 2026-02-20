"""
MashCAD - Constraint Diagnostics Dialog
=======================================

Phase 2: SU-002 + SU-003 - Constraint Diagnostik UI

Zeigt detaillierte Constraint-Diagnosen an mit:
- Visualisierung von Under/Over-Constrained Status
- Konflikt-Anzeige mit Lösungsvorschlägen
- Constraint-Vorschläge für unterbestimmte Sketches
- DOF-Anzeige und Redundanz-Erkennung

Sprint 2 Enhancement:
- Neue API mit ConstraintDiagnosticsResult
- Verbesserte DOF-Berechnung
- Redundante Constraints mit Entfern-Option
- Konflikte mit Details und Auto-Fix
- Vorschläge mit Hinzufügen-Option

Usage:
    from gui.dialogs.constraint_diagnostics_dialog import ConstraintDiagnosticsDialog
    
    dlg = ConstraintDiagnosticsDialog(sketch, parent=self)
    dlg.exec()

Author: Kimi (SU-002/SU-003 Implementation)
Date: 2026-02-19
Updated: 2026-02-20 (Sprint 2 Enhancement)
Branch: feature/v1-roadmap-execution
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTreeWidget, QTreeWidgetItem, QTabWidget,
    QGroupBox, QTextEdit, QProgressBar, QSplitter,
    QHeaderView, QWidget, QScrollArea, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor, QFont, QIcon
from loguru import logger
from typing import Optional, List

# Neue API importieren
from sketcher.constraint_diagnostics import (
    # Neue API (Sprint 2)
    analyze_constraint_state,
    detect_redundant_constraints,
    detect_conflicting_constraints,
    suggest_missing_constraints,
    ConstraintDiagnosticsResult,
    ConstraintInfo,
    ConflictInfo,
    SuggestionInfo,
    ConflictSeverity,
    ConstraintDiagnosisType,
    # SU-003: Enhanced Conflict Explanations
    ConflictExplanationTemplates,
    get_conflict_explanation,
    format_conflict_explanation,
    # Legacy API für Rückwärtskompatibilität
    ConstraintDiagnostics,
    ConstraintDiagnosis,
    ConstraintConflict,
    ConstraintSuggestion
)
from sketcher.constraints import (
    Constraint, ConstraintStatus, ConstraintType, ConstraintPriority,
    make_fixed, make_horizontal, make_vertical, make_length,
    make_radius, make_coincident, make_tangent
)
from sketcher.geometry import Point2D, Line2D, Circle2D
from gui.design_tokens import DesignTokens
from i18n import tr


class ConstraintDiagnosticsDialog(QDialog):
    """
    Dialog zur Anzeige von Constraint-Diagnosen.
    
    Bietet:
    - Übersicht über Constraint-Status mit Farb-Indikator
    - DOF-Anzeige (Degrees of Freedom)
    - Detaillierte Konflikt-Anzeige
    - Redundante Constraints mit Entfern-Option
    - Vorschläge für fehlende Constraints mit Hinzufügen-Option
    - Direkte Aktionen zur Problembehebung
    
    Signals:
        constraints_changed: Wird emittiert wenn Constraints geändert wurden
    """
    
    constraints_changed = Signal()
    
    def __init__(self, sketch, parent=None, auto_diagnose: bool = True):
        """
        Args:
            sketch: Das zu diagnostizierende Sketch
            parent: Parent Widget
            auto_diagnose: Ob Diagnose automatisch gestartet werden soll
        """
        super().__init__(parent)
        self.sketch = sketch
        self.diagnosis: ConstraintDiagnosticsResult = None
        self._removed_constraints: List[Constraint] = []
        self._added_constraints: List[Constraint] = []
        self._setup_ui()
        
        if auto_diagnose:
            self.run_diagnosis()
            
    def _setup_ui(self):
        """Erstellt die UI."""
        self.setWindowTitle(tr("Constraint-Diagnose"))
        self.setMinimumWidth(700)
        self.setMinimumHeight(600)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header mit Status-Indikator
        self._create_header(layout)
        
        # Tabs für verschiedene Ansichten
        self._create_tabs(layout)
        
        # Buttons
        self._create_buttons(layout)
        
        # Styling
        self.setStyleSheet(DesignTokens.stylesheet_dialog())
        
    def _create_header(self, layout):
        """Erstellt den Header-Bereich mit Status-Indikator."""
        header = QHBoxLayout()
        
        # Status-Indikator (großer farbiger Kreis)
        self.status_indicator = QLabel()
        self.status_indicator.setFixedSize(80, 80)
        self.status_indicator.setAlignment(Qt.AlignCenter)
        header.addWidget(self.status_indicator)
        
        # Status Info
        info_layout = QVBoxLayout()
        
        self.status_title = QLabel(tr("Diagnose wird durchgeführt..."))
        self.status_title.setStyleSheet("font-size: 20px; font-weight: bold;")
        info_layout.addWidget(self.status_title)
        
        self.status_message = QLabel("")
        self.status_message.setStyleSheet("color: #666; font-size: 13px;")
        self.status_message.setWordWrap(True)
        info_layout.addWidget(self.status_message)
        
        # DOF Anzeige (verbessert)
        self.dof_frame = QFrame()
        self.dof_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 8px;
                padding: 8px;
            }
            QLabel {
                background: transparent;
            }
        """)
        dof_layout = QHBoxLayout(self.dof_frame)
        dof_layout.setSpacing(20)
        
        # Variablen
        vars_group = QVBoxLayout()
        self.vars_value = QLabel("-")
        self.vars_value.setStyleSheet("font-family: monospace; font-size: 18px; font-weight: bold; color: #495057;")
        self.vars_label = QLabel(tr("Variablen"))
        self.vars_label.setStyleSheet("font-size: 11px; color: #6c757d;")
        vars_group.addWidget(self.vars_value, alignment=Qt.AlignCenter)
        vars_group.addWidget(self.vars_label, alignment=Qt.AlignCenter)
        dof_layout.addLayout(vars_group)
        
        # Trenner
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet("color: #dee2e6;")
        dof_layout.addWidget(sep1)
        
        # Constraints
        constr_group = QVBoxLayout()
        self.constraints_value = QLabel("-")
        self.constraints_value.setStyleSheet("font-family: monospace; font-size: 18px; font-weight: bold; color: #495057;")
        self.constraints_label = QLabel(tr("Constraints"))
        self.constraints_label.setStyleSheet("font-size: 11px; color: #6c757d;")
        constr_group.addWidget(self.constraints_value, alignment=Qt.AlignCenter)
        constr_group.addWidget(self.constraints_label, alignment=Qt.AlignCenter)
        dof_layout.addLayout(constr_group)
        
        # Trenner
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color: #dee2e6;")
        dof_layout.addWidget(sep2)
        
        # DOF
        dof_group = QVBoxLayout()
        self.dof_value = QLabel("-")
        self.dof_value.setStyleSheet("font-family: monospace; font-size: 18px; font-weight: bold;")
        self.dof_label = QLabel(tr("Freiheitsgrade"))
        self.dof_label.setStyleSheet("font-size: 11px; color: #6c757d;")
        dof_group.addWidget(self.dof_value, alignment=Qt.AlignCenter)
        dof_group.addWidget(self.dof_label, alignment=Qt.AlignCenter)
        dof_layout.addLayout(dof_group)
        
        info_layout.addWidget(self.dof_frame)
        header.addLayout(info_layout, stretch=1)
        
        layout.addLayout(header)
        
        # Trennlinie
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #dee2e6;")
        line.setFixedHeight(1)
        layout.addWidget(line)
        
    def _create_tabs(self, layout):
        """Erstellt die Tabs."""
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #dee2e6;
                border-radius: 8px;
                background: white;
            }
            QTabBar::tab {
                padding: 8px 16px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: white;
                border-bottom: 2px solid #0078d4;
            }
        """)
        
        # Tab 1: Übersicht
        self.overview_tab = self._create_overview_tab()
        self.tabs.addTab(self.overview_tab, tr("Übersicht"))
        
        # Tab 2: Konflikte (bei Over-Constrained)
        self.conflicts_tab = self._create_conflicts_tab()
        self.tabs.addTab(self.conflicts_tab, tr("Konflikte"))
        
        # Tab 3: Redundante Constraints
        self.redundant_tab = self._create_redundant_tab()
        self.tabs.addTab(self.redundant_tab, tr("Redundante"))
        
        # Tab 4: Vorschläge (bei Under-Constrained)
        self.suggestions_tab = self._create_suggestions_tab()
        self.tabs.addTab(self.suggestions_tab, tr("Vorschläge"))
        
        # Tab 5: Details
        self.details_tab = self._create_details_tab()
        self.tabs.addTab(self.details_tab, tr("Details"))
        
        layout.addWidget(self.tabs, stretch=1)
        
    def _create_overview_tab(self) -> QWidget:
        """Erstellt den Übersichts-Tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)
        
        # Status-Visualisierung (große Anzeige)
        self.status_visual = QFrame()
        self.status_visual.setMinimumHeight(120)
        self.status_visual.setStyleSheet("""
            QFrame {
                border-radius: 12px;
                background-color: #f8f9fa;
            }
        """)
        status_layout = QVBoxLayout(self.status_visual)
        
        self.status_big_icon = QLabel()
        self.status_big_icon.setAlignment(Qt.AlignCenter)
        self.status_big_icon.setStyleSheet("font-size: 48px;")
        status_layout.addWidget(self.status_big_icon)
        
        self.status_big_text = QLabel(tr("Warte auf Diagnose..."))
        self.status_big_text.setAlignment(Qt.AlignCenter)
        self.status_big_text.setStyleSheet("font-size: 24px; font-weight: bold;")
        status_layout.addWidget(self.status_big_text)
        
        self.status_sub_text = QLabel("")
        self.status_sub_text.setAlignment(Qt.AlignCenter)
        self.status_sub_text.setStyleSheet("font-size: 14px; color: #6c757d;")
        status_layout.addWidget(self.status_sub_text)
        
        layout.addWidget(self.status_visual)
        
        # Beschreibung
        self.overview_description = QTextEdit()
        self.overview_description.setReadOnly(True)
        self.overview_description.setMaximumHeight(180)
        self.overview_description.setStyleSheet("""
            QTextEdit {
                border: 1px solid #e9ecef;
                border-radius: 8px;
                padding: 10px;
                background: #f8f9fa;
            }
        """)
        layout.addWidget(self.overview_description)
        
        # Zusammenfassung
        self.summary_group = QGroupBox(tr("Zusammenfassung"))
        self.summary_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        summary_layout = QVBoxLayout(self.summary_group)
        
        self.summary_list = QLabel(tr("Führen Sie die Diagnose durch..."))
        self.summary_list.setWordWrap(True)
        self.summary_list.setStyleSheet("padding: 5px;")
        summary_layout.addWidget(self.summary_list)
        
        layout.addWidget(self.summary_group)
        layout.addStretch()
        
        return tab
        
    def _create_conflicts_tab(self) -> QWidget:
        """Erstellt den Konflikte-Tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)
        
        # Info
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background-color: #fff3cd;
                border: 1px solid #ffc107;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        info_layout = QHBoxLayout(info_frame)
        info_icon = QLabel("⚠")
        info_icon.setStyleSheet("font-size: 20px;")
        info_layout.addWidget(info_icon)
        info_text = QLabel(tr("Diese Constraints stehen im Widerspruch zueinander und müssen behoben werden."))
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text, stretch=1)
        layout.addWidget(info_frame)
        
        # Konflikte-Tree
        self.conflicts_tree = QTreeWidget()
        self.conflicts_tree.setHeaderLabels([
            tr("Schwere"), tr("Konflikt"), tr("Beschreibung"), tr("Lösung")
        ])
        self.conflicts_tree.setColumnWidth(0, 80)
        self.conflicts_tree.setColumnWidth(1, 150)
        self.conflicts_tree.setColumnWidth(2, 250)
        self.conflicts_tree.header().setStretchLastSection(True)
        self.conflicts_tree.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
            QTreeWidget::item {
                padding: 5px;
            }
        """)
        self.conflicts_tree.itemDoubleClicked.connect(self._on_conflict_double_clicked)
        
        layout.addWidget(self.conflicts_tree)
        
        # Quick-Actions
        actions_group = QGroupBox(tr("Schnelle Aktionen"))
        actions_layout = QHBoxLayout(actions_group)
        
        self.auto_resolve_btn = QPushButton(tr("🔧 Automatisch lösen"))
        self.auto_resolve_btn.setToolTip(tr("Versucht, lösbare Konflikte automatisch zu beheben"))
        self.auto_resolve_btn.clicked.connect(self._auto_resolve_conflicts)
        actions_layout.addWidget(self.auto_resolve_btn)
        
        actions_layout.addStretch()
        layout.addWidget(actions_group)
        
        return tab
        
    def _create_redundant_tab(self) -> QWidget:
        """Erstellt den Tab für redundante Constraints."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)
        
        # Info
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background-color: #e7f3ff;
                border: 1px solid #0078d4;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        info_layout = QHBoxLayout(info_frame)
        info_icon = QLabel("ℹ")
        info_icon.setStyleSheet("font-size: 20px;")
        info_layout.addWidget(info_icon)
        info_text = QLabel(tr("Redundante Constraints sind überflüssig und können entfernt werden."))
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text, stretch=1)
        layout.addWidget(info_frame)
        
        # Redundante-Tree
        self.redundant_tree = QTreeWidget()
        self.redundant_tree.setHeaderLabels([
            tr("Typ"), tr("Elemente"), tr("Grund"), tr("Aktion")
        ])
        self.redundant_tree.setColumnWidth(0, 120)
        self.redundant_tree.setColumnWidth(1, 180)
        self.redundant_tree.setColumnWidth(2, 250)
        self.redundant_tree.header().setStretchLastSection(True)
        self.redundant_tree.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
        """)
        self.redundant_tree.itemDoubleClicked.connect(self._on_redundant_double_clicked)
        
        layout.addWidget(self.redundant_tree)
        
        # Actions
        actions_group = QGroupBox(tr("Aktionen"))
        actions_layout = QHBoxLayout(actions_group)
        
        self.remove_selected_btn = QPushButton(tr("🗑 Ausgewählte entfernen"))
        self.remove_selected_btn.clicked.connect(self._remove_selected_redundant)
        actions_layout.addWidget(self.remove_selected_btn)
        
        self.remove_all_redundant_btn = QPushButton(tr("🗑 Alle entfernen"))
        self.remove_all_redundant_btn.clicked.connect(self._remove_all_redundant)
        actions_layout.addWidget(self.remove_all_redundant_btn)
        
        actions_layout.addStretch()
        layout.addWidget(actions_group)
        
        return tab
        
    def _create_suggestions_tab(self) -> QWidget:
        """Erstellt den Vorschläge-Tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)
        
        # Info
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background-color: #d4edda;
                border: 1px solid #28a745;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        info_layout = QHBoxLayout(info_frame)
        info_icon = QLabel("💡")
        info_icon.setStyleSheet("font-size: 20px;")
        info_layout.addWidget(info_icon)
        info_text = QLabel(tr("Diese Constraints werden vorgeschlagen, um das Sketch vollständig zu bestimmen."))
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text, stretch=1)
        layout.addWidget(info_frame)
        
        # Vorschläge-Tree
        self.suggestions_tree = QTreeWidget()
        self.suggestions_tree.setHeaderLabels([
            tr("Priorität"), tr("Typ"), tr("Elemente"), tr("Begründung"), tr("DOF-Reduktion")
        ])
        self.suggestions_tree.setColumnWidth(0, 80)
        self.suggestions_tree.setColumnWidth(1, 100)
        self.suggestions_tree.setColumnWidth(2, 150)
        self.suggestions_tree.setColumnWidth(3, 250)
        self.suggestions_tree.setColumnWidth(4, 80)
        self.suggestions_tree.header().setStretchLastSection(False)
        self.suggestions_tree.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
        """)
        self.suggestions_tree.itemDoubleClicked.connect(self._on_suggestion_double_clicked)
        
        layout.addWidget(self.suggestions_tree)
        
        # Anwenden-Buttons
        actions_group = QGroupBox(tr("Aktionen"))
        actions_layout = QHBoxLayout(actions_group)
        
        self.add_selected_btn = QPushButton(tr("➕ Ausgewählte hinzufügen"))
        self.add_selected_btn.clicked.connect(self._add_selected_suggestions)
        actions_layout.addWidget(self.add_selected_btn)
        
        self.add_auto_btn = QPushButton(tr("🤖 Auto-hinzufügbar"))
        self.add_auto_btn.setToolTip(tr("Fügt alle automatisch hinzufügbaren Constraints hinzu"))
        self.add_auto_btn.clicked.connect(self._add_auto_suggestions)
        actions_layout.addWidget(self.add_auto_btn)
        
        self.add_critical_btn = QPushButton(tr("⚠ Kritische hinzufügen"))
        self.add_critical_btn.clicked.connect(self._add_critical_suggestions)
        actions_layout.addWidget(self.add_critical_btn)
        
        actions_layout.addStretch()
        layout.addWidget(actions_group)
        
        return tab
        
    def _create_details_tab(self) -> QWidget:
        """Erstellt den Details-Tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Raw Report
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setFont(QFont("Consolas", 10))
        self.details_text.setStyleSheet("""
            QTextEdit {
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
        """)
        layout.addWidget(self.details_text)
        
        return tab
        
    def _create_buttons(self, layout):
        """Erstellt die Button-Leiste."""
        btn_layout = QHBoxLayout()
        
        # Änderungen-Info
        self.changes_label = QLabel("")
        self.changes_label.setStyleSheet("color: #6c757d; font-style: italic;")
        btn_layout.addWidget(self.changes_label)
        
        btn_layout.addStretch()
        
        # Re-run Button
        self.rerun_btn = QPushButton(tr("🔄 Neu diagnose"))
        self.rerun_btn.clicked.connect(self.run_diagnosis)
        btn_layout.addWidget(self.rerun_btn)
        
        # Apply Button (nur wenn Änderungen vorhanden)
        self.apply_btn = QPushButton(tr("✓ Anwenden"))
        self.apply_btn.setObjectName("primary")
        self.apply_btn.clicked.connect(self._apply_changes)
        self.apply_btn.setVisible(False)
        btn_layout.addWidget(self.apply_btn)
        
        # Close Button
        close_btn = QPushButton(tr("Schließen"))
        close_btn.clicked.connect(self._on_close)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
    def run_diagnosis(self):
        """Führt die Diagnose durch."""
        logger.debug("Running constraint diagnosis")
        
        self.status_title.setText(tr("Diagnose wird durchgeführt..."))
        self.status_message.setText("")
        
        # Diagnose mit neuer API
        self.diagnosis = analyze_constraint_state(self.sketch)
        
        # UI aktualisieren
        self._update_ui()
        
    def _update_ui(self):
        """Aktualisiert die UI mit Diagnose-Ergebnissen."""
        if not self.diagnosis:
            return
        
        d = self.diagnosis
        
        # Header aktualisieren
        self._update_header(d)
        
        # Tabs aktualisieren
        self._update_overview(d)
        self._update_conflicts(d)
        self._update_redundant(d)
        self._update_suggestions(d)
        self._update_details(d)
        
        # Tab-Visibility basierend auf Diagnose
        self._update_tab_visibility(d)
        
    def _update_header(self, d: ConstraintDiagnosticsResult):
        """Aktualisiert den Header mit Status-Indikator."""
        # Status-Konfiguration
        status_config = {
            ConstraintDiagnosisType.FULLY_CONSTRAINED: {
                'icon': '✓', 'color': '#28a745', 'bg': '#d4edda',
                'title': tr("Vollständig bestimmt"),
                'sub': tr("Alle Freiheitsgrade sind eingeschränkt")
            },
            ConstraintDiagnosisType.UNDER_CONSTRAINED: {
                'icon': '⚠', 'color': '#ffc107', 'bg': '#fff3cd',
                'title': tr("Unterbestimmt"),
                'sub': tr("Weitere Constraints erforderlich")
            },
            ConstraintDiagnosisType.OVER_CONSTRAINED: {
                'icon': '✗', 'color': '#dc3545', 'bg': '#f8d7da',
                'title': tr("Überbestimmt"),
                'sub': tr("Widersprüchliche Constraints gefunden")
            },
            ConstraintDiagnosisType.INCONSISTENT: {
                'icon': '✗', 'color': '#dc3545', 'bg': '#f8d7da',
                'title': tr("Inkonsistent"),
                'sub': tr("Ungültige Constraints gefunden")
            }
        }
        
        config = status_config.get(d.diagnosis_type, {
            'icon': '?', 'color': '#6c757d', 'bg': '#f8f9fa',
            'title': tr("Unbekannt"),
            'sub': ""
        })
        
        # Status-Indikator
        self.status_indicator.setText(config['icon'])
        self.status_indicator.setStyleSheet(f"""
            background-color: {config['bg']};
            color: {config['color']};
            border-radius: 40px;
            font-size: 40px;
            font-weight: bold;
            border: 3px solid {config['color']};
        """)
        
        self.status_title.setText(config['title'])
        self.status_title.setStyleSheet(f"color: {config['color']}; font-size: 20px; font-weight: bold;")
        self.status_message.setText(d.message)
        
        # DOF Labels
        self.vars_value.setText(str(d.total_variables))
        self.constraints_value.setText(str(d.total_constraints))
        
        # DOF mit Farbe
        dof_color = '#28a745' if d.degrees_of_freedom == 0 else '#ffc107' if d.degrees_of_freedom < 5 else '#dc3545'
        self.dof_value.setText(str(d.degrees_of_freedom))
        self.dof_value.setStyleSheet(f"font-family: monospace; font-size: 18px; font-weight: bold; color: {dof_color};")
        
    def _update_overview(self, d: ConstraintDiagnosticsResult):
        """Aktualisiert den Übersichts-Tab."""
        # Status-Visual
        status_icons = {
            ConstraintDiagnosisType.FULLY_CONSTRAINED: "✅",
            ConstraintDiagnosisType.UNDER_CONSTRAINED: "⚠️",
            ConstraintDiagnosisType.OVER_CONSTRAINED: "❌",
            ConstraintDiagnosisType.INCONSISTENT: "❌"
        }
        
        status_texts = {
            ConstraintDiagnosisType.FULLY_CONSTRAINED: tr("VOLLSTÄNDIG BESTIMMT"),
            ConstraintDiagnosisType.UNDER_CONSTRAINED: tr("UNTERBESTIMMT"),
            ConstraintDiagnosisType.OVER_CONSTRAINED: tr("ÜBERBESTIMMT"),
            ConstraintDiagnosisType.INCONSISTENT: tr("INKONSISTENT")
        }
        
        self.status_big_icon.setText(status_icons.get(d.diagnosis_type, "❓"))
        self.status_big_text.setText(status_texts.get(d.diagnosis_type, tr("UNBEKANNT")))
        self.status_sub_text.setText(d.message)
        
        # Beschreibung
        self.overview_description.setText(d.to_user_report())
        
        # Zusammenfassung
        summary_parts = []
        if d.is_under_constrained:
            summary_parts.append(f"• {d.degrees_of_freedom} Freiheitsgrade verbleibend")
            summary_parts.append(f"• {len(d.suggested_constraints)} Vorschläge verfügbar")
            auto_addable = sum(1 for s in d.suggested_constraints if s.auto_addable)
            if auto_addable > 0:
                summary_parts.append(f"• {auto_addable} automatisch hinzufügbar")
        elif d.is_over_constrained:
            summary_parts.append(f"• {len(d.conflicting_constraints)} Konflikt(e) gefunden")
            summary_parts.append(f"• {len(d.redundant_constraints)} redundante Constraints")
            auto_fixable = sum(1 for c in d.conflicting_constraints if c.auto_fixable)
            if auto_fixable > 0:
                summary_parts.append(f"• {auto_fixable} automatisch lösbar")
        elif d.is_inconsistent:
            summary_parts.append(f"• {len(d.invalid_constraints)} ungültige Constraints")
        
        self.summary_list.setText("\n".join(summary_parts) if summary_parts else tr("Keine Probleme gefunden"))
        
    def _update_conflicts(self, d: ConstraintDiagnosticsResult):
        """Aktualisiert den Konflikte-Tab mit SU-003 Enhanced Explanations."""
        self.conflicts_tree.clear()
        
        for conflict in d.conflicting_constraints:
            item = QTreeWidgetItem(self.conflicts_tree)
            
            # Severity
            severity_icons = {
                ConflictSeverity.CRITICAL: "🔴",
                ConflictSeverity.HIGH: "🟠",
                ConflictSeverity.MEDIUM: "🟡",
                ConflictSeverity.LOW: "🟢"
            }
            item.setText(0, severity_icons.get(conflict.severity, "⚪"))
            item.setText(1, conflict.conflict_type)
            item.setText(2, conflict.explanation)
            item.setText(3, conflict.suggested_resolution)
            
            # SU-003: Erweiterte Daten speichern
            item.setData(0, Qt.UserRole, conflict)
            
            # SU-003: Resolution Steps als Tooltip
            if hasattr(conflict, 'resolution_steps') and conflict.resolution_steps:
                steps_text = "\n".join(f"• {step}" for step in conflict.resolution_steps)
                item.setToolTip(2, f"<b>Lösungsschritte:</b><br>{steps_text}")
            
            # SU-003: Affected Geometry anzeigen
            if hasattr(conflict, 'affected_geometry') and conflict.affected_geometry:
                geo_text = ", ".join(conflict.affected_geometry[:3])
                if len(conflict.affected_geometry) > 3:
                    geo_text += f" (+{len(conflict.affected_geometry) - 3})"
                item.setToolTip(1, f"Betroffene Geometrie: {geo_text}")
            
            # Severity-Farbe
            if conflict.severity == ConflictSeverity.CRITICAL:
                item.setBackground(1, QColor("#f8d7da"))
            elif conflict.severity == ConflictSeverity.HIGH:
                item.setBackground(1, QColor("#fff3cd"))
                
    def _update_redundant(self, d: ConstraintDiagnosticsResult):
        """Aktualisiert den Redundante-Tab."""
        self.redundant_tree.clear()
        
        for rc in d.redundant_constraints:
            item = QTreeWidgetItem(self.redundant_tree)
            item.setText(0, rc.constraint.type.name)
            item.setText(1, ", ".join(rc.entity_ids))
            item.setText(2, rc.redundancy_reason)
            item.setText(3, tr("Doppelklick zum Entfernen"))
            
            # Constraint speichern
            item.setData(0, Qt.UserRole, rc.constraint)
            
            # Styling
            item.setBackground(0, QColor("#e7f3ff"))
            
    def _update_suggestions(self, d: ConstraintDiagnosticsResult):
        """Aktualisiert den Vorschläge-Tab."""
        self.suggestions_tree.clear()
        
        # Sortiere nach Priorität
        priority_order = {
            ConstraintPriority.CRITICAL: 0,
            ConstraintPriority.HIGH: 1,
            ConstraintPriority.MEDIUM: 2,
            ConstraintPriority.LOW: 3,
            ConstraintPriority.REFERENCE: 4
        }
        
        sorted_suggestions = sorted(
            d.suggested_constraints,
            key=lambda s: priority_order.get(s.priority, 5)
        )
        
        for suggestion in sorted_suggestions:
            item = QTreeWidgetItem(self.suggestions_tree)
            
            # Priorität
            priority_icons = {
                ConstraintPriority.CRITICAL: "🔴",
                ConstraintPriority.HIGH: "🟠",
                ConstraintPriority.MEDIUM: "🟡",
                ConstraintPriority.LOW: "🟢",
                ConstraintPriority.REFERENCE: "⚪"
            }
            item.setText(0, priority_icons.get(suggestion.priority, "⚪"))
            item.setText(1, suggestion.constraint_type.name)
            item.setText(2, ", ".join(suggestion.entity_ids[:3]))  # Max 3 anzeigen
            item.setText(3, suggestion.reason)
            item.setText(4, f"-{suggestion.dof_reduction}")
            
            # Auto-addable indicator
            if suggestion.auto_addable:
                item.setText(3, suggestion.reason + " [Auto]")
                
            # Suggestion speichern
            item.setData(0, Qt.UserRole, suggestion)
            
            # Prioritäts-Farbe
            if suggestion.priority == ConstraintPriority.CRITICAL:
                item.setBackground(1, QColor("#f8d7da"))
            elif suggestion.priority == ConstraintPriority.HIGH:
                item.setBackground(1, QColor("#fff3cd"))
                
    def _update_details(self, d: ConstraintDiagnosticsResult):
        """Aktualisiert den Details-Tab."""
        details = []
        details.append("=" * 60)
        details.append("CONSTRAINT DIAGNOSTICS REPORT")
        details.append("=" * 60)
        details.append("")
        details.append(f"Diagnosis Type: {d.diagnosis_type.name}")
        details.append(f"Status: {d.status.name}")
        details.append(f"Degrees of Freedom: {d.degrees_of_freedom}")
        details.append(f"Total Variables: {d.total_variables}")
        details.append(f"Total Constraints: {d.total_constraints}")
        details.append("")
        
        if d.redundant_constraints:
            details.append("-" * 40)
            details.append("REDUNDANT CONSTRAINTS:")
            details.append("-" * 40)
            for rc in d.redundant_constraints:
                details.append(f"  - {rc.constraint.type.name}: {rc.redundancy_reason}")
            details.append("")
        
        if d.conflicting_constraints:
            details.append("-" * 40)
            details.append("CONFLICTS:")
            details.append("-" * 40)
            for cc in d.conflicting_constraints:
                details.append(f"  [{cc.severity.value}] {cc.conflict_type}")
                details.append(f"      {cc.explanation}")
                details.append(f"      Solution: {cc.suggested_resolution}")
            details.append("")
        
        if d.suggested_constraints:
            details.append("-" * 40)
            details.append("SUGGESTIONS:")
            details.append("-" * 40)
            for sc in d.suggested_constraints:
                details.append(f"  [{sc.priority.name}] {sc.constraint_type.name}")
                details.append(f"      Entities: {sc.entity_ids}")
                details.append(f"      Reason: {sc.reason}")
                details.append(f"      DOF Reduction: {sc.dof_reduction}")
            details.append("")
        
        if d.invalid_constraints:
            details.append("-" * 40)
            details.append("INVALID CONSTRAINTS:")
            details.append("-" * 40)
            for c, error in d.invalid_constraints:
                details.append(f"  - {c.type.name}: {error}")
            details.append("")
        
        details.append("=" * 60)
        details.append(d.to_user_report())
        
        self.details_text.setPlainText("\n".join(details))
        
    def _update_tab_visibility(self, d: ConstraintDiagnosticsResult):
        """Aktualisiert Tab-Sichtbarkeit basierend auf Diagnose."""
        conflicts_idx = self.tabs.indexOf(self.conflicts_tab)
        redundant_idx = self.tabs.indexOf(self.redundant_tab)
        suggestions_idx = self.tabs.indexOf(self.suggestions_tab)
        
        # Konflikte-Tab
        show_conflicts = len(d.conflicting_constraints) > 0
        self.tabs.setTabVisible(conflicts_idx, show_conflicts)
        
        # Redundante-Tab
        show_redundant = len(d.redundant_constraints) > 0
        self.tabs.setTabVisible(redundant_idx, show_redundant)
        
        # Vorschläge-Tab
        show_suggestions = d.is_under_constrained and len(d.suggested_constraints) > 0
        self.tabs.setTabVisible(suggestions_idx, show_suggestions)
        
        # Tab-Badges mit Anzahl
        if show_conflicts:
            self.tabs.setTabText(conflicts_idx, tr("Konflikte") + f" ({len(d.conflicting_constraints)})")
        if show_redundant:
            self.tabs.setTabText(redundant_idx, tr("Redundante") + f" ({len(d.redundant_constraints)})")
        if show_suggestions:
            self.tabs.setTabText(suggestions_idx, tr("Vorschläge") + f" ({len(d.suggested_constraints)})")
            
    def _update_changes_label(self):
        """Aktualisiert die Änderungen-Anzeige."""
        added = len(self._added_constraints)
        removed = len(self._removed_constraints)
        
        parts = []
        if added > 0:
            parts.append(f"+{added} hinzugefügt")
        if removed > 0:
            parts.append(f"-{removed} entfernt")
        
        if parts:
            self.changes_label.setText(tr("Änderungen: ") + ", ".join(parts))
            self.apply_btn.setVisible(True)
        else:
            self.changes_label.setText("")
            self.apply_btn.setVisible(False)
            
    # === Action Handlers ===
    
    def _on_conflict_double_clicked(self, item, column):
        """SU-003: Handler für Doppelklick auf Konflikt mit erweiterten Details."""
        conflict = item.data(0, Qt.UserRole)
        if conflict and isinstance(conflict, ConflictInfo):
            # SU-003: Erweiterte Konflikt-Details anzeigen
            self._show_conflict_details_dialog(conflict)
    
    def _show_conflict_details_dialog(self, conflict: ConflictInfo):
        """
        SU-003: Zeigt einen erweiterten Konflikt-Details-Dialog.
        
        Zeigt:
        - Detaillierte Erklärung
        - Schritt-für-Schritt-Lösungsvorschläge
        - Betroffene Geometrie
        - Auto-Resolve Option (falls verfügbar)
        """
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QTextEdit, QFrame, QScrollArea, QWidget
        )
        
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Konflikt-Details"))
        dlg.setMinimumWidth(500)
        dlg.setMinimumHeight(400)
        
        layout = QVBoxLayout(dlg)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header mit Severity
        header_layout = QHBoxLayout()
        
        severity_icons = {
            ConflictSeverity.CRITICAL: ("🔴", "#dc3545"),
            ConflictSeverity.HIGH: ("🟠", "#fd7e14"),
            ConflictSeverity.MEDIUM: ("🟡", "#ffc107"),
            ConflictSeverity.LOW: ("🟢", "#28a745")
        }
        icon, color = severity_icons.get(conflict.severity, ("⚪", "#6c757d"))
        
        severity_label = QLabel(icon)
        severity_label.setStyleSheet(f"font-size: 32px;")
        header_layout.addWidget(severity_label)
        
        title_layout = QVBoxLayout()
        type_label = QLabel(conflict.conflict_type)
        type_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {color};")
        title_layout.addWidget(type_label)
        
        severity_text = QLabel(f"Schweregrad: {conflict.severity.value.upper()}")
        severity_text.setStyleSheet("color: #6c757d; font-size: 12px;")
        title_layout.addWidget(severity_text)
        
        header_layout.addLayout(title_layout, stretch=1)
        layout.addLayout(header_layout)
        
        # Trennlinie
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setStyleSheet("background-color: #dee2e6;")
        layout.addWidget(line1)
        
        # Erklärung
        explanation_group = QLabel("<b>📝 Erklärung</b>")
        explanation_group.setStyleSheet("font-size: 14px;")
        layout.addWidget(explanation_group)
        
        explanation_text = QTextEdit()
        explanation_text.setReadOnly(True)
        explanation_text.setPlainText(conflict.explanation)
        explanation_text.setMaximumHeight(120)
        explanation_text.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        layout.addWidget(explanation_text)
        
        # SU-003: Resolution Steps
        if hasattr(conflict, 'resolution_steps') and conflict.resolution_steps:
            steps_group = QLabel("<b>🔧 Lösungsschritte</b>")
            steps_group.setStyleSheet("font-size: 14px;")
            layout.addWidget(steps_group)
            
            steps_container = QWidget()
            steps_layout = QVBoxLayout(steps_container)
            steps_layout.setSpacing(5)
            steps_layout.setContentsMargins(10, 5, 10, 5)
            steps_container.setStyleSheet("""
                QWidget {
                    background-color: #d4edda;
                    border: 1px solid #28a745;
                    border-radius: 8px;
                }
            """)
            
            for i, step in enumerate(conflict.resolution_steps, 1):
                step_label = QLabel(f"{i}. {step}")
                step_label.setWordWrap(True)
                step_label.setStyleSheet("background: transparent; padding: 3px;")
                steps_layout.addWidget(step_label)
            
            layout.addWidget(steps_container)
        
        # SU-003: Affected Geometry
        if hasattr(conflict, 'affected_geometry') and conflict.affected_geometry:
            geo_group = QLabel("<b>📍 Betroffene Geometrie</b>")
            geo_group.setStyleSheet("font-size: 14px;")
            layout.addWidget(geo_group)
            
            geo_text = ", ".join(conflict.affected_geometry)
            geo_label = QLabel(geo_text)
            geo_label.setWordWrap(True)
            geo_label.setStyleSheet("""
                QLabel {
                    background-color: #e7f3ff;
                    border: 1px solid #0078d4;
                    border-radius: 8px;
                    padding: 8px;
                }
            """)
            layout.addWidget(geo_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        # SU-003: Auto-Resolve Button (falls verfügbar)
        if conflict.auto_fixable and conflict.constraints:
            auto_resolve_btn = QPushButton(tr("🔧 Automatisch lösen"))
            auto_resolve_btn.setObjectName("primary")
            auto_resolve_btn.clicked.connect(lambda: self._auto_resolve_single_conflict(conflict, dlg))
            btn_layout.addWidget(auto_resolve_btn)
        
        close_btn = QPushButton(tr("Schließen"))
        close_btn.clicked.connect(dlg.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        # Styling
        dlg.setStyleSheet(DesignTokens.stylesheet_dialog())
        
        dlg.exec()
    
    def _auto_resolve_single_conflict(self, conflict: ConflictInfo, parent_dialog):
        """SU-003: Löst einen einzelnen Konflikt automatisch."""
        if conflict.constraints:
            # Entferne den letzten Constraint im Konflikt
            constraint_to_remove = conflict.constraints[-1]
            self._remove_constraint(constraint_to_remove, None)
            parent_dialog.accept()
            self.run_diagnosis()
            QMessageBox.information(
                self,
                tr("Auto-Lösung"),
                tr(f"Constraint '{constraint_to_remove.type.name}' wurde entfernt")
            )
            
    def _on_redundant_double_clicked(self, item, column):
        """Handler für Doppelklick auf redundanten Constraint."""
        constraint = item.data(0, Qt.UserRole)
        if constraint:
            self._remove_constraint(constraint, item)
            
    def _on_suggestion_double_clicked(self, item, column):
        """Handler für Doppelklick auf Vorschlag."""
        suggestion = item.data(0, Qt.UserRole)
        if suggestion and isinstance(suggestion, SuggestionInfo):
            self._add_suggestion(suggestion, item)
            
    def _auto_resolve_conflicts(self):
        """Versucht automatisch Konflikte zu lösen."""
        if not self.diagnosis:
            return
        
        resolved = 0
        for conflict in self.diagnosis.conflicting_constraints:
            if conflict.auto_fixable:
                # Entferne den letzten Constraint im Konflikt
                if conflict.constraints:
                    constraint_to_remove = conflict.constraints[-1]
                    self._remove_constraint(constraint_to_remove, None)
                    resolved += 1
        
        if resolved > 0:
            QMessageBox.information(
                self,
                tr("Auto-Lösung"),
                tr(f"{resolved} Konflikt(e) automatisch gelöst")
            )
            self.run_diagnosis()
        else:
            QMessageBox.information(
                self,
                tr("Auto-Lösung"),
                tr("Keine automatisch lösbaren Konflikte gefunden")
            )
            
    def _remove_selected_redundant(self):
        """Entfernt ausgewählte redundante Constraints."""
        selected = self.redundant_tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, tr("Hinweis"), tr("Bitte wählen Sie Constraints zum Entfernen aus"))
            return
        
        for item in selected:
            constraint = item.data(0, Qt.UserRole)
            if constraint:
                self._remove_constraint(constraint, item)
                
    def _remove_all_redundant(self):
        """Entfernt alle redundanten Constraints."""
        if not self.diagnosis or not self.diagnosis.redundant_constraints:
            return
        
        count = len(self.diagnosis.redundant_constraints)
        reply = QMessageBox.question(
            self,
            tr("Bestätigung"),
            tr(f"{count} redundante Constraint(s) entfernen?"),
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            for rc in self.diagnosis.redundant_constraints[:]:  # Copy list
                self._remove_constraint(rc.constraint, None)
            self.run_diagnosis()
            
    def _add_selected_suggestions(self):
        """Fügt ausgewählte Vorschläge hinzu."""
        selected = self.suggestions_tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, tr("Hinweis"), tr("Bitte wählen Sie Vorschläge zum Hinzufügen aus"))
            return
        
        for item in selected:
            suggestion = item.data(0, Qt.UserRole)
            if suggestion:
                self._add_suggestion(suggestion, item)
                
    def _add_auto_suggestions(self):
        """Fügt alle automatisch hinzufügbaren Vorschläge hinzu."""
        if not self.diagnosis:
            return
        
        auto_suggestions = [s for s in self.diagnosis.suggested_constraints if s.auto_addable]
        
        if not auto_suggestions:
            QMessageBox.information(self, tr("Hinweis"), tr("Keine automatisch hinzufügbaren Vorschläge"))
            return
        
        for suggestion in auto_suggestions:
            self._add_suggestion(suggestion, None)
        
        self.run_diagnosis()
        
    def _add_critical_suggestions(self):
        """Fügt alle kritischen Vorschläge hinzu."""
        if not self.diagnosis:
            return
        
        critical = [s for s in self.diagnosis.suggested_constraints 
                   if s.priority == ConstraintPriority.CRITICAL]
        
        if not critical:
            QMessageBox.information(self, tr("Hinweis"), tr("Keine kritischen Vorschläge"))
            return
        
        for suggestion in critical:
            self._add_suggestion(suggestion, None)
        
        self.run_diagnosis()
        
    def _remove_constraint(self, constraint: Constraint, item):
        """Entfernt einen Constraint aus dem Sketch."""
        if constraint in self.sketch.constraints:
            self.sketch.constraints.remove(constraint)
            self._removed_constraints.append(constraint)
            if item:
                self.redundant_tree.takeTopLevelItem(self.redundant_tree.indexOfTopLevelItem(item))
            self._update_changes_label()
            
    def _add_suggestion(self, suggestion: SuggestionInfo, item):
        """Fügt einen vorgeschlagenen Constraint zum Sketch hinzu."""
        try:
            # Erstelle Constraint basierend auf Typ
            new_constraint = None
            
            if suggestion.constraint_type == ConstraintType.FIXED:
                if suggestion.entities and isinstance(suggestion.entities[0], Point2D):
                    new_constraint = make_fixed(suggestion.entities[0])
                    
            elif suggestion.constraint_type == ConstraintType.HORIZONTAL:
                if suggestion.entities:
                    entity = suggestion.entities[0]
                    if isinstance(entity, Line2D):
                        new_constraint = make_horizontal(entity)
                    elif len(suggestion.entities) >= 2 and isinstance(entity, Point2D):
                        # Horizontale Linie zwischen zwei Punkten - nicht direkt unterstützt
                        pass
                        
            elif suggestion.constraint_type == ConstraintType.VERTICAL:
                if suggestion.entities:
                    entity = suggestion.entities[0]
                    if isinstance(entity, Line2D):
                        new_constraint = make_vertical(entity)
                        
            elif suggestion.constraint_type == ConstraintType.LENGTH:
                if suggestion.entities and isinstance(suggestion.entities[0], Line2D):
                    line = suggestion.entities[0]
                    new_constraint = make_length(line, line.length)
                    
            elif suggestion.constraint_type == ConstraintType.RADIUS:
                if suggestion.entities and isinstance(suggestion.entities[0], (Circle2D,)):
                    circle = suggestion.entities[0]
                    new_constraint = make_radius(circle, circle.radius)
                    
            elif suggestion.constraint_type == ConstraintType.TANGENT:
                if len(suggestion.entities) >= 2:
                    new_constraint = make_tangent(suggestion.entities[0], suggestion.entities[1])
                    
            elif suggestion.constraint_type == ConstraintType.COINCIDENT:
                if len(suggestion.entities) >= 2:
                    if isinstance(suggestion.entities[0], Point2D) and isinstance(suggestion.entities[1], Point2D):
                        new_constraint = make_coincident(suggestion.entities[0], suggestion.entities[1])
            
            if new_constraint:
                self.sketch.constraints.append(new_constraint)
                self._added_constraints.append(new_constraint)
                if item:
                    self.suggestions_tree.takeTopLevelItem(self.suggestions_tree.indexOfTopLevelItem(item))
                self._update_changes_label()
                logger.info(f"Added constraint: {new_constraint}")
            else:
                logger.warning(f"Could not create constraint for suggestion: {suggestion.constraint_type}")
                
        except Exception as e:
            logger.error(f"Error adding suggestion: {e}")
            QMessageBox.warning(self, tr("Fehler"), tr(f"Constraint konnte nicht hinzugefügt werden: {e}"))
            
    def _apply_changes(self):
        """Wendet alle Änderungen an."""
        self.constraints_changed.emit()
        self._added_constraints.clear()
        self._removed_constraints.clear()
        self._update_changes_label()
        self.run_diagnosis()
        
    def _on_close(self):
        """Handler für Schließen."""
        if self._added_constraints or self._removed_constraints:
            reply = QMessageBox.question(
                self,
                tr("Ungespeicherte Änderungen"),
                tr("Änderungen verwerfen?"),
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Yes:
                # Änderungen verwerfen - Sketch zurücksetzen
                for c in self._added_constraints:
                    if c in self.sketch.constraints:
                        self.sketch.constraints.remove(c)
                for c in self._removed_constraints:
                    if c not in self.sketch.constraints:
                        self.sketch.constraints.append(c)
        
        self.accept()


def show_constraint_diagnostics(sketch, parent=None) -> Optional[ConstraintDiagnosticsResult]:
    """
    Convenience-Funktion zum Anzeigen der Constraint-Diagnose.
    
    Returns:
        ConstraintDiagnosticsResult oder None
    """
    dlg = ConstraintDiagnosticsDialog(sketch, parent)
    dlg.exec()
    return dlg.diagnosis
