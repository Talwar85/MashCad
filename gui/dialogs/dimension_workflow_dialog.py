"""
MashCAD - Dimension Workflow Dialog
====================================

Phase 2: SU-008 - Dimensions-Workflow für Einsteiger

Bietet einen geführten Dialog für das Bemaßen von Sketches:
- Schritt-für-Schritt Guide
- Auto-Dimension Funktion
- Vorschlags-Liste mit direkter Anwendung
- Fortschritts-Visualisierung

Usage:
    from gui.dialogs.dimension_workflow_dialog import DimensionWorkflowDialog
    
    dlg = DimensionWorkflowDialog(sketch, parent=self)
    dlg.exec()

Author: Kimi (SU-008 Implementation)
Date: 2026-02-19
Branch: feature/v1-ux-aiB
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTreeWidget, QTreeWidgetItem, QTabWidget,
    QGroupBox, QProgressBar, QComboBox, QSpinBox,
    QHeaderView, QWidget, QFrame, QScrollArea,
    QSizePolicy, QSpacerItem, QMessageBox
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor
from loguru import logger

from sketcher.dimension_workflow import (
    DimensionWorkflow, DimensionGuide, DimensionStrategy,
    DimensionType, DimensionSuggestion, DimensionGuideStep
)
from sketcher.constraints import ConstraintType
from gui.design_tokens import DesignTokens
from i18n import tr


class DimensionWorkflowDialog(QDialog):
    """
    Dialog für den Dimension-Workflow.
    
    Bietet:
    - Guide-Modus für Einsteiger
    - Experten-Modus mit allen Funktionen
    - Auto-Dimension
    - Vorschlags-Verwaltung
    """
    
    def __init__(self, sketch, parent=None, mode: str = "guide"):
        """
        Args:
            sketch: Das Sketch-Objekt
            parent: Parent Widget
            mode: "guide" für Einsteiger, "expert" für erfahrene Nutzer
        """
        super().__init__(parent)
        self.sketch = sketch
        self.mode = mode
        self.workflow = DimensionWorkflow(sketch)
        self.guide = DimensionGuide(sketch)
        self._setup_ui()
        self._refresh_content()
        
    def _setup_ui(self):
        """Erstellt die UI."""
        self.setWindowTitle(tr("Dimension-Workflow"))
        self.setMinimumWidth(700)
        self.setMinimumHeight(600)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        self._create_header(layout)
        
        # Fortschritt
        self._create_progress_section(layout)
        
        # Tabs
        self._create_tabs(layout)
        
        # Buttons
        self._create_buttons(layout)
        
        # Styling
        self.setStyleSheet(DesignTokens.stylesheet_dialog())
        
    def _create_header(self, layout):
        """Erstellt den Header."""
        header = QHBoxLayout()
        
        # Titel
        title_layout = QVBoxLayout()
        
        self.title_label = QLabel(tr("📐 Dimension-Workflow"))
        self.title_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        title_layout.addWidget(self.title_label)
        
        self.subtitle_label = QLabel(tr("Bemaßen Sie Ihr Sketch Schritt für Schritt"))
        self.subtitle_label.setStyleSheet("color: #666;")
        title_layout.addWidget(self.subtitle_label)
        
        header.addLayout(title_layout, stretch=1)
        
        # Modus-Wechsler
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(tr("🎓 Guide-Modus (Empfohlen)"), "guide")
        self.mode_combo.addItem(tr("⚙️ Experten-Modus"), "expert")
        self.mode_combo.setCurrentIndex(0 if self.mode == "guide" else 1)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        header.addWidget(self.mode_combo)
        
        layout.addLayout(header)
        
        # Trennlinie
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #ddd;")
        layout.addWidget(line)
        
    def _create_progress_section(self, layout):
        """Erstellt den Fortschritts-Bereich."""
        self.progress_group = QGroupBox(tr("Fortschritt"))
        progress_layout = QVBoxLayout(self.progress_group)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 4px;
                text-align: center;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 4px;
            }
        """)
        progress_layout.addWidget(self.progress_bar)
        
        # Status Labels
        status_layout = QHBoxLayout()
        
        self.status_total = QLabel(tr("Elemente: 0"))
        self.status_dimensioned = QLabel(tr("Bemaßt: 0"))
        self.status_missing = QLabel(tr("Fehlend: 0"))
        self.status_coverage = QLabel(tr("Abdeckung: 0%"))
        
        for label in [self.status_total, self.status_dimensioned, 
                     self.status_missing, self.status_coverage]:
            label.setStyleSheet("font-family: monospace;")
            status_layout.addWidget(label)
        
        status_layout.addStretch()
        progress_layout.addLayout(status_layout)
        
        layout.addWidget(self.progress_group)
        
    def _create_tabs(self, layout):
        """Erstellt die Tabs."""
        self.tabs = QTabWidget()
        
        # Tab 1: Guide (für Einsteiger)
        self.guide_tab = self._create_guide_tab()
        self.tabs.addTab(self.guide_tab, tr("🎓 Guide"))
        
        # Tab 2: Vorschläge
        self.suggestions_tab = self._create_suggestions_tab()
        self.tabs.addTab(self.suggestions_tab, tr("💡 Vorschläge"))
        
        # Tab 3: Auto-Dimension
        self.auto_tab = self._create_auto_tab()
        self.tabs.addTab(self.auto_tab, tr("⚡ Auto"))
        
        # Tab 4: Status
        self.status_tab = self._create_status_tab()
        self.tabs.addTab(self.status_tab, tr("📊 Status"))
        
        layout.addWidget(self.tabs, stretch=1)
        
    def _create_guide_tab(self) -> QWidget:
        """Erstellt den Guide-Tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Info-Label
        info = QLabel(tr("Folgen Sie diesen Schritten, um Ihr Sketch vollständig zu bemaßen:"))
        info.setWordWrap(True)
        layout.addWidget(info)
        
        # Guide-Steps Tree
        self.guide_tree = QTreeWidget()
        self.guide_tree.setHeaderLabels([
            tr("Nr."), tr("Schritt"), tr("Status"), tr("Aktion")
        ])
        self.guide_tree.setColumnWidth(0, 50)
        self.guide_tree.setColumnWidth(1, 200)
        self.guide_tree.setColumnWidth(2, 100)
        self.guide_tree.header().setStretchLastSection(True)
        self.guide_tree.itemDoubleClicked.connect(self._on_guide_item_activated)
        
        layout.addWidget(self.guide_tree)
        
        # Next Step Button
        self.next_step_btn = QPushButton(tr("➡ Nächster Schritt"))
        self.next_step_btn.setObjectName("primary")
        self.next_step_btn.clicked.connect(self._go_to_next_step)
        layout.addWidget(self.next_step_btn)
        
        return tab
        
    def _create_suggestions_tab(self) -> QWidget:
        """Erstellt den Vorschläge-Tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Filter/Options
        options_layout = QHBoxLayout()
        
        options_layout.addWidget(QLabel(tr("Max. Vorschläge:")))
        self.max_suggestions_spin = QSpinBox()
        self.max_suggestions_spin.setRange(5, 50)
        self.max_suggestions_spin.setValue(10)
        self.max_suggestions_spin.valueChanged.connect(self._refresh_suggestions)
        options_layout.addWidget(self.max_suggestions_spin)
        
        options_layout.addStretch()
        
        self.refresh_btn = QPushButton(tr("🔄 Aktualisieren"))
        self.refresh_btn.clicked.connect(self._refresh_suggestions)
        options_layout.addWidget(self.refresh_btn)
        
        layout.addLayout(options_layout)
        
        # Suggestions Tree
        self.suggestions_tree = QTreeWidget()
        self.suggestions_tree.setHeaderLabels([
            tr("Typ"), tr("Wert"), tr("Priorität"), tr("Begründung"), tr("Konfidenz")
        ])
        self.suggestions_tree.setColumnWidth(0, 100)
        self.suggestions_tree.setColumnWidth(1, 80)
        self.suggestions_tree.setColumnWidth(2, 80)
        self.suggestions_tree.setColumnWidth(3, 250)
        self.suggestions_tree.header().setStretchLastSection(True)
        
        layout.addWidget(self.suggestions_tree)
        
        # Action Buttons
        btn_layout = QHBoxLayout()
        
        self.apply_selected_btn = QPushButton(tr("✓ Ausgewählte anwenden"))
        self.apply_selected_btn.clicked.connect(self._apply_selected_suggestions)
        btn_layout.addWidget(self.apply_selected_btn)
        
        self.apply_all_btn = QPushButton(tr("✓✓ Alle anwenden"))
        self.apply_all_btn.clicked.connect(self._apply_all_suggestions)
        btn_layout.addWidget(self.apply_all_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        return tab
        
    def _create_auto_tab(self) -> QWidget:
        """Erstellt den Auto-Dimension Tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Info
        info = QLabel(tr("Wählen Sie eine Strategie für die automatische Bemaßung:"))
        info.setWordWrap(True)
        layout.addWidget(info)
        
        # Strategie-Auswahl
        strategies_group = QGroupBox(tr("Strategie"))
        strategies_layout = QVBoxLayout(strategies_group)
        
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItem(
            tr("Minimal - Nur notwendigste Dimensionen"), 
            DimensionStrategy.MINIMAL.value
        )
        self.strategy_combo.addItem(
            tr("Vollständig - Alle sinnvollen Dimensionen"),
            DimensionStrategy.FULL.value
        )
        self.strategy_combo.addItem(
            tr("Referenz - Nur Referenz-Dimensionen (nicht treibend)"),
            DimensionStrategy.REFERENCE.value
        )
        strategies_layout.addWidget(self.strategy_combo)
        
        # Strategie-Beschreibung
        self.strategy_desc = QLabel(tr(
            "Minimal: Erstellt nur die unbedingt notwendigen Dimensionen, "
            "um das Sketch zu bestimmen."
        ))
        self.strategy_desc.setWordWrap(True)
        self.strategy_desc.setStyleSheet("color: #666; font-style: italic;")
        strategies_layout.addWidget(self.strategy_desc)
        
        self.strategy_combo.currentIndexChanged.connect(self._update_strategy_desc)
        
        layout.addWidget(strategies_group)
        
        # Vorschau
        preview_group = QGroupBox(tr("Vorschau"))
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_label = QLabel(tr("Klicken Sie 'Vorschau' um zu sehen, "
                                      "welche Dimensionen erstellt werden."))
        self.preview_label.setWordWrap(True)
        preview_layout.addWidget(self.preview_label)
        
        layout.addWidget(preview_group)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.preview_btn = QPushButton(tr("👁 Vorschau"))
        self.preview_btn.clicked.connect(self._preview_auto_dimension)
        btn_layout.addWidget(self.preview_btn)
        
        self.auto_apply_btn = QPushButton(tr("⚡ Auto-Dimension anwenden"))
        self.auto_apply_btn.setObjectName("primary")
        self.auto_apply_btn.clicked.connect(self._apply_auto_dimension)
        btn_layout.addWidget(self.auto_apply_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        layout.addStretch()
        return tab
        
    def _create_status_tab(self) -> QWidget:
        """Erstellt den Status-Tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Status-Details
        self.status_details = QTextEdit()
        self.status_details.setReadOnly(True)
        self.status_details.setFont(QFont("Consolas", 10))
        layout.addWidget(self.status_details)
        
        # Weak Areas
        self.weak_areas_group = QGroupBox(tr("Schwache Bereiche"))
        weak_layout = QVBoxLayout(self.weak_areas_group)
        
        self.weak_areas_label = QLabel(tr("Keine Schwachstellen erkannt"))
        self.weak_areas_label.setWordWrap(True)
        weak_layout.addWidget(self.weak_areas_label)
        
        layout.addWidget(self.weak_areas_group)
        
        return tab
        
    def _create_buttons(self, layout):
        """Erstellt die Button-Leiste."""
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        # Close Button
        close_btn = QPushButton(tr("Schließen"))
        close_btn.setObjectName("primary")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
    def _refresh_content(self):
        """Aktualisiert alle Inhalte."""
        self._refresh_progress()
        self._refresh_guide()
        self._refresh_suggestions()
        self._refresh_status()
        
    def _refresh_progress(self):
        """Aktualisiert den Fortschritt."""
        status = self.workflow.get_dimension_status()
        
        # Progress Bar
        self.progress_bar.setValue(int(status.coverage_percentage))
        
        # Status Labels
        self.status_total.setText(tr(f"Elemente: {status.total_elements}"))
        self.status_dimensioned.setText(tr(f"Bemaßt: {status.dimensioned_count}"))
        self.status_missing.setText(tr(f"Fehlend: {status.missing_count}"))
        self.status_coverage.setText(tr(f"Abdeckung: {status.coverage_percentage:.0f}%"))
        
        # Farbe basierend auf Fortschritt
        if status.coverage_percentage >= 90:
            self.progress_bar.setStyleSheet("""
                QProgressBar::chunk { background-color: #4CAF50; }
            """)
        elif status.coverage_percentage >= 50:
            self.progress_bar.setStyleSheet("""
                QProgressBar::chunk { background-color: #FF9800; }
            """)
        else:
            self.progress_bar.setStyleSheet("""
                QProgressBar::chunk { background-color: #F44336; }
            """)
            
    def _refresh_guide(self):
        """Aktualisiert den Guide-Tab."""
        self.guide_tree.clear()
        
        steps = self.guide.get_all_steps()
        
        for step in steps:
            item = QTreeWidgetItem(self.guide_tree)
            item.setText(0, str(step.step_number))
            item.setText(1, step.title)
            item.setText(2, tr("✓ Erledigt") if step.is_completed else tr("○ Offen"))
            item.setText(3, step.action)
            
            # Farbe basierend auf Status
            if step.is_completed:
                item.setBackground(2, QColor("#E8F5E9"))
                for col in range(4):
                    item.setForeground(col, QColor("#4CAF50"))
            else:
                item.setBackground(2, QColor("#FFF3E0"))
                
            # Speichere Step-Daten
            item.setData(0, Qt.UserRole, step)
            
    def _refresh_suggestions(self):
        """Aktualisiert die Vorschläge."""
        self.suggestions_tree.clear()
        
        max_suggestions = self.max_suggestions_spin.value()
        suggestions = self.workflow.get_dimension_suggestions(max_suggestions)
        
        for suggestion in suggestions:
            item = QTreeWidgetItem(self.suggestions_tree)
            item.setText(0, suggestion.dimension_type.name)
            item.setText(1, f"{suggestion.suggested_value:.2f}" 
                        if suggestion.suggested_value else "-")
            item.setText(2, str(suggestion.priority))
            item.setText(3, suggestion.reason)
            item.setText(4, f"{suggestion.confidence:.0%}")
            
            # Farbe basierend auf Priorität
            if suggestion.priority >= 9:
                item.setBackground(2, QColor("#FFEBEE"))
            elif suggestion.priority >= 7:
                item.setBackground(2, QColor("#FFF3E0"))
                
            # Speichere Suggestion
            item.setData(0, Qt.UserRole, suggestion)
            
    def _refresh_status(self):
        """Aktualisiert den Status-Tab."""
        status = self.workflow.get_dimension_status()
        
        # Detaillierter Report
        report = f"""Dimension-Status Report
{'=' * 50}

Gesamtelemente:     {status.total_elements}
Bemaßt:             {status.dimensioned_count}
Fehlend:            {status.missing_count}
Abdeckung:          {status.coverage_percentage:.1f}%

Status:             {'✓ Vollständig' if status.is_fully_dimensioned else '⚠ Unvollständig'}
"""
        self.status_details.setPlainText(report)
        
        # Schwache Bereiche
        if status.weak_areas:
            self.weak_areas_label.setText("\n".join(f"• {area}" for area in status.weak_areas))
        else:
            self.weak_areas_label.setText(tr("✓ Keine Schwachstellen erkannt"))
            
    def _on_mode_changed(self, index):
        """Handler für Modus-Wechsel."""
        self.mode = self.mode_combo.currentData()
        # In einer vollständigen Implementierung würde hier die UI angepasst
        
    def _update_strategy_desc(self, index):
        """Aktualisiert die Strategie-Beschreibung."""
        strategy = self.strategy_combo.currentData()
        
        descriptions = {
            "minimal": tr("Minimal: Erstellt nur die unbedingt notwendigen Dimensionen."),
            "full": tr("Vollständig: Erstellt alle sinnvollen Dimensionen für maximale Kontrolle."),
            "reference": tr("Referenz: Erstellt Dimensionen als Referenz (nicht treibend).")
        }
        
        self.strategy_desc.setText(descriptions.get(strategy, ""))
        
    def _on_guide_item_activated(self, item, column):
        """Handler für Doppelklick auf Guide-Item."""
        step = item.data(0, Qt.UserRole)
        if step and step.suggestions:
            # Zeige Vorschläge für diesen Schritt
            QMessageBox.information(
                self,
                step.title,
                f"{step.description}\n\n" +
                "Vorschläge:\n" +
                "\n".join(f"• {s.dimension_type.name}: {s.reason}" 
                         for s in step.suggestions[:3])
            )
            
    def _go_to_next_step(self):
        """Springt zum nächsten offenen Schritt."""
        next_step = self.guide.get_next_recommended_step()
        if next_step:
            self.tabs.setCurrentWidget(self.guide_tab)
            # In vollständiger Implementierung: Scrolle zu Item
            QMessageBox.information(
                self,
                tr("Nächster Schritt"),
                f"{next_step.title}\n\n{next_step.description}\n\n"
                f"Aktion: {next_step.action}"
            )
        else:
            QMessageBox.information(
                self,
                tr("Glückwunsch!"),
                tr("Alle Schritte sind abgeschlossen!")
            )
            
    def _apply_selected_suggestions(self):
        """Wendet ausgewählte Vorschläge an."""
        # In vollständiger Implementierung
        logger.info("Apply selected suggestions requested")
        self._refresh_content()
        
    def _apply_all_suggestions(self):
        """Wendet alle Vorschläge an."""
        suggestions = self.workflow.get_dimension_suggestions(100)
        applied = 0
        
        for suggestion in suggestions:
            constraint = suggestion.to_constraint()
            if constraint:
                self.sketch.constraints.append(constraint)
                applied += 1
                
        QMessageBox.information(
            self,
            tr("Vorschläge angewendet"),
            tr(f"{applied} Dimensionen wurden erstellt.")
        )
        
        self._refresh_content()
        
    def _preview_auto_dimension(self):
        """Zeigt Vorschau für Auto-Dimension."""
        strategy_str = self.strategy_combo.currentData()
        strategy = DimensionStrategy(strategy_str)
        
        # Simuliere ohne Anwendung
        suggestions = self.workflow.get_dimension_suggestions(100)
        
        if strategy == DimensionStrategy.MINIMAL:
            count = len([s for s in suggestions if s.priority >= 8])
        else:
            count = len([s for s in suggestions if s.priority >= 5])
            
        self.preview_label.setText(
            tr(f"Strategie '{strategy.value}' würde {count} Dimensionen erstellen.")
        )
        
    def _apply_auto_dimension(self):
        """Wendet Auto-Dimension an."""
        strategy_str = self.strategy_combo.currentData()
        strategy = DimensionStrategy(strategy_str)
        
        constraints = self.workflow.auto_dimension(strategy)
        
        QMessageBox.information(
            self,
            tr("Auto-Dimension abgeschlossen"),
            tr(f"{len(constraints)} Dimensionen wurden erstellt.")
        )
        
        self._refresh_content()


def show_dimension_workflow(sketch, parent=None, mode: str = "guide"):
    """
    Convenience-Funktion zum Anzeigen des Dimension-Workflows.
    
    Returns:
        QDialog.DialogCode
    """
    dlg = DimensionWorkflowDialog(sketch, parent, mode)
    return dlg.exec()
