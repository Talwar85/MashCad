"""
MashCAD - Constraint Diagnostics Dialog
=======================================

Phase 2: SU-002 + SU-003 - Constraint Diagnostik UI

Zeigt detaillierte Constraint-Diagnosen an mit:
- Visualisierung von Under/Over-Constrained Status
- Konflikt-Anzeige mit Lösungsvorschlägen
- Constraint-Vorschläge für unterbestimmte Sketches

Usage:
    from gui.dialogs.constraint_diagnostics_dialog import ConstraintDiagnosticsDialog
    
    dlg = ConstraintDiagnosticsDialog(sketch, parent=self)
    dlg.exec()

Author: Kimi (SU-002/SU-003 Implementation)
Date: 2026-02-19
Branch: feature/v1-ux-aiB
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTreeWidget, QTreeWidgetItem, QTabWidget,
    QGroupBox, QTextEdit, QProgressBar, QSplitter,
    QHeaderView, QWidget, QScrollArea, QFrame
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont
from loguru import logger

from sketcher.constraint_diagnostics import (
    ConstraintDiagnostics, ConstraintDiagnosis, ConstraintDiagnosisType,
    ConstraintConflict, ConstraintSuggestion
)
from sketcher.constraints import ConstraintStatus, ConstraintType, ConstraintPriority
from gui.design_tokens import DesignTokens
from i18n import tr


class ConstraintDiagnosticsDialog(QDialog):
    """
    Dialog zur Anzeige von Constraint-Diagnosen.
    
    Bietet:
    - Übersicht über Constraint-Status
    - Detaillierte Konflikt-Anzeige
    - Vorschläge für fehlende Constraints
    - Direkte Aktionen zur Problembehebung
    """
    
    def __init__(self, sketch, parent=None, auto_diagnose: bool = True):
        """
        Args:
            sketch: Das zu diagnostizierende Sketch
            parent: Parent Widget
            auto_diagnose: Ob Diagnose automatisch gestartet werden soll
        """
        super().__init__(parent)
        self.sketch = sketch
        self.diagnosis: ConstraintDiagnosis = None
        self._setup_ui()
        
        if auto_diagnose:
            self.run_diagnosis()
            
    def _setup_ui(self):
        """Erstellt die UI."""
        self.setWindowTitle(tr("Constraint-Diagnose"))
        self.setMinimumWidth(650)
        self.setMinimumHeight(550)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header mit Status
        self._create_header(layout)
        
        # Tabs für verschiedene Ansichten
        self._create_tabs(layout)
        
        # Buttons
        self._create_buttons(layout)
        
        # Styling
        self.setStyleSheet(DesignTokens.stylesheet_dialog())
        
    def _create_header(self, layout):
        """Erstellt den Header-Bereich."""
        header = QHBoxLayout()
        
        # Status Icon
        self.status_icon = QLabel()
        self.status_icon.setFixedSize(64, 64)
        self.status_icon.setAlignment(Qt.AlignCenter)
        header.addWidget(self.status_icon)
        
        # Status Info
        info_layout = QVBoxLayout()
        
        self.status_title = QLabel(tr("Diagnose wird durchgeführt..."))
        self.status_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        info_layout.addWidget(self.status_title)
        
        self.status_message = QLabel("")
        self.status_message.setStyleSheet("color: #666;")
        info_layout.addWidget(self.status_message)
        
        # DOF Anzeige
        self.dof_frame = QFrame()
        self.dof_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border-radius: 8px;
                padding: 5px;
            }
        """)
        dof_layout = QHBoxLayout(self.dof_frame)
        
        self.vars_label = QLabel("Vars: -")
        self.constraints_label = QLabel("Constraints: -")
        self.dof_label = QLabel("DOF: -")
        
        for label in [self.vars_label, self.constraints_label, self.dof_label]:
            label.setStyleSheet("font-family: monospace; font-size: 12px;")
            dof_layout.addWidget(label)
        
        info_layout.addWidget(self.dof_frame)
        header.addLayout(info_layout, stretch=1)
        
        layout.addLayout(header)
        
        # Trennlinie
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #ddd;")
        layout.addWidget(line)
        
    def _create_tabs(self, layout):
        """Erstellt die Tabs."""
        self.tabs = QTabWidget()
        
        # Tab 1: Übersicht
        self.overview_tab = self._create_overview_tab()
        self.tabs.addTab(self.overview_tab, tr("Übersicht"))
        
        # Tab 2: Konflikte (nur bei Over-Constrained)
        self.conflicts_tab = self._create_conflicts_tab()
        self.tabs.addTab(self.conflicts_tab, tr("Konflikte"))
        
        # Tab 3: Vorschläge (nur bei Under-Constrained)
        self.suggestions_tab = self._create_suggestions_tab()
        self.tabs.addTab(self.suggestions_tab, tr("Vorschläge"))
        
        # Tab 4: Details
        self.details_tab = self._create_details_tab()
        self.tabs.addTab(self.details_tab, tr("Details"))
        
        layout.addWidget(self.tabs, stretch=1)
        
    def _create_overview_tab(self) -> QWidget:
        """Erstellt den Übersichts-Tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Status-Visualisierung
        self.status_visual = QFrame()
        self.status_visual.setFixedHeight(100)
        self.status_visual.setStyleSheet("""
            QFrame {
                border-radius: 8px;
                background-color: #f5f5f5;
            }
        """)
        status_layout = QVBoxLayout(self.status_visual)
        
        self.status_big_text = QLabel(tr("Warte auf Diagnose..."))
        self.status_big_text.setAlignment(Qt.AlignCenter)
        self.status_big_text.setStyleSheet("font-size: 24px; font-weight: bold;")
        status_layout.addWidget(self.status_big_text)
        
        layout.addWidget(self.status_visual)
        
        # Beschreibung
        self.overview_description = QTextEdit()
        self.overview_description.setReadOnly(True)
        self.overview_description.setMaximumHeight(150)
        layout.addWidget(self.overview_description)
        
        # Zusammenfassung
        self.summary_group = QGroupBox(tr("Zusammenfassung"))
        summary_layout = QVBoxLayout(self.summary_group)
        
        self.summary_list = QLabel(tr("Führen Sie die Diagnose durch..."))
        self.summary_list.setWordWrap(True)
        summary_layout.addWidget(self.summary_list)
        
        layout.addWidget(self.summary_group)
        layout.addStretch()
        
        return tab
        
    def _create_conflicts_tab(self) -> QWidget:
        """Erstellt den Konflikte-Tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        info = QLabel(tr("Diese Constraints stehen im Widerspruch zueinander:"))
        info.setWordWrap(True)
        layout.addWidget(info)
        
        # Konflikte-Tree
        self.conflicts_tree = QTreeWidget()
        self.conflicts_tree.setHeaderLabels([
            tr("Konflikt"), tr("Beschreibung"), tr("Lösung")
        ])
        self.conflicts_tree.setColumnWidth(0, 150)
        self.conflicts_tree.setColumnWidth(1, 250)
        self.conflicts_tree.header().setStretchLastSection(True)
        
        layout.addWidget(self.conflicts_tree)
        
        # Quick-Actions
        actions_group = QGroupBox(tr("Schnelle Aktionen"))
        actions_layout = QHBoxLayout(actions_group)
        
        self.remove_redundant_btn = QPushButton(tr("Redundante entfernen"))
        self.remove_redundant_btn.clicked.connect(self._remove_redundant)
        actions_layout.addWidget(self.remove_redundant_btn)
        
        self.auto_resolve_btn = QPushButton(tr("Auto-Lösen"))
        self.auto_resolve_btn.clicked.connect(self._auto_resolve)
        actions_layout.addWidget(self.auto_resolve_btn)
        
        actions_layout.addStretch()
        layout.addWidget(actions_group)
        
        return tab
        
    def _create_suggestions_tab(self) -> QWidget:
        """Erstellt den Vorschläge-Tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        info = QLabel(tr("Folgende Constraints werden vorgeschlagen, um das Sketch vollständig zu bestimmen:"))
        info.setWordWrap(True)
        layout.addWidget(info)
        
        # Vorschläge-Tree
        self.suggestions_tree = QTreeWidget()
        self.suggestions_tree.setHeaderLabels([
            tr("Typ"), tr("Elemente"), tr("Begründung"), tr("Priorität")
        ])
        self.suggestions_tree.setColumnWidth(0, 120)
        self.suggestions_tree.setColumnWidth(1, 150)
        self.suggestions_tree.setColumnWidth(2, 250)
        self.suggestions_tree.header().setStretchLastSection(True)
        
        layout.addWidget(self.suggestions_tree)
        
        # Anwenden-Buttons
        actions_group = QGroupBox(tr("Aktionen"))
        actions_layout = QHBoxLayout(actions_group)
        
        self.apply_all_btn = QPushButton(tr("Alle anwenden"))
        self.apply_all_btn.clicked.connect(self._apply_all_suggestions)
        actions_layout.addWidget(self.apply_all_btn)
        
        self.apply_critical_btn = QPushButton(tr("Nur Kritische"))
        self.apply_critical_btn.clicked.connect(self._apply_critical_suggestions)
        actions_layout.addWidget(self.apply_critical_btn)
        
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
        layout.addWidget(self.details_text)
        
        return tab
        
    def _create_buttons(self, layout):
        """Erstellt die Button-Leiste."""
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        # Re-run Button
        self.rerun_btn = QPushButton(tr("Neu diagnose"))
        self.rerun_btn.clicked.connect(self.run_diagnosis)
        btn_layout.addWidget(self.rerun_btn)
        
        # Close Button
        close_btn = QPushButton(tr("Schließen"))
        close_btn.setObjectName("primary")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
    def run_diagnosis(self):
        """Führt die Diagnose durch."""
        logger.debug("Running constraint diagnosis")
        
        self.status_title.setText(tr("Diagnose wird durchgeführt..."))
        self.status_message.setText("")
        
        # Diagnose
        self.diagnosis = ConstraintDiagnostics.diagnose(self.sketch)
        
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
        self._update_suggestions(d)
        self._update_details(d)
        
        # Tab-Visibility basierend auf Diagnose
        self._update_tab_visibility(d)
        
    def _update_header(self, d: ConstraintDiagnosis):
        """Aktualisiert den Header."""
        # Status-Icon und Farbe
        status_config = {
            ConstraintDiagnosisType.FULLY_CONSTRAINED: {
                'icon': '✓', 'color': '#4CAF50', 'bg': '#E8F5E9',
                'title': tr("Vollständig bestimmt")
            },
            ConstraintDiagnosisType.UNDER_CONSTRAINED: {
                'icon': '⚠', 'color': '#FF9800', 'bg': '#FFF3E0',
                'title': tr("Unterbestimmt")
            },
            ConstraintDiagnosisType.OVER_CONSTRAINED: {
                'icon': '✗', 'color': '#F44336', 'bg': '#FFEBEE',
                'title': tr("Überbestimmt")
            },
            ConstraintDiagnosisType.INCONSISTENT: {
                'icon': '✗', 'color': '#F44336', 'bg': '#FFEBEE',
                'title': tr("Inkonsistent")
            }
        }
        
        config = status_config.get(d.diagnosis_type, status_config[ConstraintDiagnosisType.UNKNOWN])
        
        self.status_icon.setText(config['icon'])
        self.status_icon.setStyleSheet(f"""
            background-color: {config['bg']};
            color: {config['color']};
            border-radius: 32px;
            font-size: 32px;
            font-weight: bold;
        """)
        
        self.status_title.setText(config['title'])
        self.status_title.setStyleSheet(f"color: {config['color']}; font-size: 18px; font-weight: bold;")
        self.status_message.setText(d.message)
        
        # DOF Labels
        self.vars_label.setText(f"Vars: {d.total_variables}")
        self.constraints_label.setText(f"Constraints: {d.total_constraints}")
        self.dof_label.setText(f"DOF: {d.dof}")
        
    def _update_overview(self, d: ConstraintDiagnosis):
        """Aktualisiert den Übersichts-Tab."""
        # Status-Visual
        status_texts = {
            ConstraintDiagnosisType.FULLY_CONSTRAINED: tr("✓ VOLLSTÄNDIG"),
            ConstraintDiagnosisType.UNDER_CONSTRAINED: tr("⚠ UNTERBESTIMMT"),
            ConstraintDiagnosisType.OVER_CONSTRAINED: tr("✗ ÜBERBESTIMMT"),
            ConstraintDiagnosisType.INCONSISTENT: tr("✗ INKONSISTENT")
        }
        self.status_big_text.setText(status_texts.get(d.diagnosis_type, tr("? UNBEKANNT")))
        
        # Beschreibung
        self.overview_description.setText(d.to_user_report())
        
        # Zusammenfassung
        summary_parts = []
        if d.is_under_constrained:
            summary_parts.append(f"• {d.missing_constraint_count} Freiheitsgrade fehlen")
            summary_parts.append(f"• {len(d.suggestions)} Vorschläge verfügbar")
        elif d.is_over_constrained:
            summary_parts.append(f"• {len(d.conflicts)} Konflikt(e) gefunden")
            summary_parts.append(f"• {len(d.redundant_constraints)} redundante Constraints")
        elif d.is_inconsistent:
            summary_parts.append(f"• {len(d.invalid_constraints)} ungültige Constraints")
        
        self.summary_list.setText("\n".join(summary_parts) if summary_parts else tr("Keine Probleme gefunden"))
        
    def _update_conflicts(self, d: ConstraintDiagnosis):
        """Aktualisiert den Konflikte-Tab."""
        self.conflicts_tree.clear()
        
        for conflict in d.conflicts:
            item = QTreeWidgetItem(self.conflicts_tree)
            item.setText(0, conflict.conflict_type)
            item.setText(1, conflict.explanation)
            item.setText(2, conflict.suggested_resolution)
            
            # Severity-Farbe
            if conflict.severity == ConstraintPriority.CRITICAL:
                item.setBackground(0, QColor("#FFEBEE"))
            elif conflict.severity == ConstraintPriority.HIGH:
                item.setBackground(0, QColor("#FFF3E0"))
        
        # Redundante Constraints
        for constraint in d.redundant_constraints:
            item = QTreeWidgetItem(self.conflicts_tree)
            item.setText(0, tr("REDUNDANT"))
            item.setText(1, f"{constraint.type.name}: {constraint}")
            item.setText(2, tr("Kann entfernt werden"))
            item.setBackground(0, QColor("#E3F2FD"))
            
    def _update_suggestions(self, d: ConstraintDiagnosis):
        """Aktualisiert den Vorschläge-Tab."""
        self.suggestions_tree.clear()
        
        # Sortiere nach Priorität
        sorted_suggestions = sorted(
            d.suggestions,
            key=lambda s: s.priority.value,
            reverse=True
        )
        
        for suggestion in sorted_suggestions:
            item = QTreeWidgetItem(self.suggestions_tree)
            item.setText(0, suggestion.constraint_type.name)
            item.setText(1, ", ".join(str(e) for e in suggestion.entities))
            item.setText(2, suggestion.reason)
            item.setText(3, suggestion.priority.name)
            
            # Prioritäts-Farbe
            if suggestion.priority == ConstraintPriority.CRITICAL:
                item.setBackground(3, QColor("#FFEBEE"))
            elif suggestion.priority == ConstraintPriority.HIGH:
                item.setBackground(3, QColor("#FFF3E0"))
                
    def _update_details(self, d: ConstraintDiagnosis):
        """Aktualisiert den Details-Tab."""
        self.details_text.setPlainText(d.detailed_report)
        
    def _update_tab_visibility(self, d: ConstraintDiagnosis):
        """Aktualisiert Tab-Sichtbarkeit basierend auf Diagnose."""
        # Finde Tab-Indizes
        conflicts_idx = self.tabs.indexOf(self.conflicts_tab)
        suggestions_idx = self.tabs.indexOf(self.suggestions_tab)
        
        # Konflikte-Tab nur bei Over-Constrained oder Inconsistent
        show_conflicts = d.is_over_constrained or (d.is_inconsistent and d.conflicts)
        self.tabs.setTabVisible(conflicts_idx, show_conflicts)
        
        # Vorschläge-Tab nur bei Under-Constrained
        show_suggestions = d.is_under_constrained and d.suggestions
        self.tabs.setTabVisible(suggestions_idx, show_suggestions)
        
    def _remove_redundant(self):
        """Entfernt redundante Constraints."""
        if not self.diagnosis:
            return
        
        # TODO: Implementieren
        logger.info(f"Would remove {len(self.diagnosis.redundant_constraints)} redundant constraints")
        
    def _auto_resolve(self):
        """Versucht automatisch Konflikte zu lösen."""
        if not self.diagnosis:
            return
        
        # TODO: Implementieren
        logger.info("Auto-resolve requested")
        
    def _apply_all_suggestions(self):
        """Wendet alle Vorschläge an."""
        if not self.diagnosis:
            return
        
        # TODO: Implementieren
        logger.info(f"Would apply {len(self.diagnosis.suggestions)} suggestions")
        
    def _apply_critical_suggestions(self):
        """Wendet nur kritische Vorschläge an."""
        if not self.diagnosis:
            return
        
        critical = [s for s in self.diagnosis.suggestions 
                   if s.priority == ConstraintPriority.CRITICAL]
        logger.info(f"Would apply {len(critical)} critical suggestions")


def show_constraint_diagnostics(sketch, parent=None):
    """
    Convenience-Funktion zum Anzeigen der Constraint-Diagnose.
    
    Returns:
        ConstraintDiagnosis oder None
    """
    dlg = ConstraintDiagnosticsDialog(sketch, parent)
    dlg.exec()
    return dlg.diagnosis
