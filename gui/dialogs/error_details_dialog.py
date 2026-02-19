"""
MashCAD - Error Details Dialog
==============================

Phase 2: CH-008 - Fehlerdiagnostik im UI verbessern

Zeigt detaillierte Fehlerinformationen mit Erklärungen und
"Next Action" Vorschlägen in einer benutzerfreundlichen UI.

Usage:
    from gui.dialogs.error_details_dialog import ErrorDetailsDialog
    from modeling.error_diagnostics import ErrorDiagnostics
    
    # Nach einem Fehler
    explanation = ErrorDiagnostics.explain(error_code, context)
    dlg = ErrorDetailsDialog(explanation, parent=self)
    dlg.exec()

Author: Kimi (CH-008 Implementation)
Date: 2026-02-19
Branch: feature/v1-ux-aiB
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTextEdit, QScrollArea, QWidget,
    QFrame, QListWidget, QListWidgetItem, QCheckBox,
    QTabWidget, QSizePolicy, QSpacerItem
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QColor
from loguru import logger

from modeling.error_diagnostics import ErrorExplanation, ErrorSeverity, ErrorCategory
from gui.design_tokens import DesignTokens
from i18n import tr


class ErrorDetailsDialog(QDialog):
    """
    Dialog zur Anzeige detaillierter Fehlerinformationen.
    
    Zeigt:
    - Klare Fehlerüberschrift
    - Verständliche Erklärung
    - Schritt-für-Schritt Lösungsvorschläge
    - Technische Details (optional)
    - Auto-Fix Option (falls verfügbar)
    """
    
    def __init__(self, explanation: ErrorExplanation, parent=None, show_auto_fix: bool = True):
        """
        Args:
            explanation: ErrorExplanation vom ErrorDiagnostics
            parent: Parent Widget
            show_auto_fix: Ob Auto-Fix Button angezeigt werden soll
        """
        super().__init__(parent)
        self.explanation = explanation
        self.show_auto_fix = show_auto_fix
        self.auto_fix_clicked = False
        self._setup_ui()
        
    def _setup_ui(self):
        """Erstellt die UI."""
        # Fenster-Eigenschaften
        self.setWindowTitle(tr("Fehlerdetails"))
        self.setMinimumWidth(550)
        self.setMinimumHeight(500)
        
        # Haupt-Layout
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header mit Icon und Titel
        self._create_header(layout)
        
        # Tabs für verschiedene Detail-Level
        self._create_content_tabs(layout)
        
        # Action Buttons
        self._create_buttons(layout)
        
        # Styling
        self.setStyleSheet(self._get_stylesheet())
        
    def _create_header(self, layout):
        """Erstellt den Header-Bereich."""
        header = QHBoxLayout()
        
        # Severity Icon
        self.severity_icon = QLabel()
        self.severity_icon.setFixedSize(48, 48)
        self.severity_icon.setAlignment(Qt.AlignCenter)
        self._set_severity_icon()
        header.addWidget(self.severity_icon)
        
        # Titel und Kategorie
        title_layout = QVBoxLayout()
        
        self.title_label = QLabel(self.explanation.title)
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        title_layout.addWidget(self.title_label)
        
        category_text = self._get_category_display()
        self.category_label = QLabel(category_text)
        self.category_label.setStyleSheet("color: #666; font-size: 11px;")
        title_layout.addWidget(self.category_label)
        
        header.addLayout(title_layout, stretch=1)
        layout.addLayout(header)
        
        # Trennlinie
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #ddd;")
        layout.addWidget(line)
        
    def _create_content_tabs(self, layout):
        """Erstellt den Tab-Container."""
        self.tabs = QTabWidget()
        
        # Tab 1: Erklärung & Lösung
        self.tabs.addTab(self._create_explanation_tab(), tr("Erklärung & Lösung"))
        
        # Tab 2: Technische Details
        if self.explanation.technical_details:
            self.tabs.addTab(self._create_technical_tab(), tr("Technische Details"))
        
        layout.addWidget(self.tabs, stretch=1)
        
    def _create_explanation_tab(self) -> QWidget:
        """Erstellt den Erklärungs-Tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)
        
        # Beschreibung
        desc_group = QFrame()
        desc_group.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-radius: 8px;
                padding: 5px;
            }
        """)
        desc_layout = QVBoxLayout(desc_group)
        
        desc_label = QLabel(self.explanation.description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("font-size: 13px; line-height: 1.5;")
        desc_layout.addWidget(desc_label)
        
        layout.addWidget(desc_group)
        
        # Auto-Fix Hinweis (falls verfügbar)
        if self.explanation.can_auto_fix and self.show_auto_fix:
            auto_fix_frame = self._create_auto_fix_frame()
            layout.addWidget(auto_fix_frame)
        
        # Next Actions
        actions_group = QFrame()
        actions_group.setStyleSheet("""
            QFrame {
                background-color: #e8f4f8;
                border-left: 4px solid #2196F3;
                border-radius: 4px;
            }
        """)
        actions_layout = QVBoxLayout(actions_group)
        
        actions_title = QLabel(tr("💡 Empfohlene Schritte:"))
        actions_title.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        actions_layout.addWidget(actions_title)
        
        for i, action in enumerate(self.explanation.next_actions, 1):
            action_label = QLabel(f"{i}. {action}")
            action_label.setWordWrap(True)
            action_label.setStyleSheet("margin-left: 10px; margin-top: 3px;")
            actions_layout.addWidget(action_label)
        
        layout.addWidget(actions_group)
        
        # Kontext-Info (falls vorhanden)
        if self.explanation.context:
            context_frame = self._create_context_frame()
            if context_frame:
                layout.addWidget(context_frame)
        
        layout.addStretch()
        return tab
        
    def _create_technical_tab(self) -> QWidget:
        """Erstellt den Technische-Details-Tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Error Code
        code_label = QLabel(f"<b>Error Code:</b> {self.explanation.error_code}")
        layout.addWidget(code_label)
        
        # Severity
        severity_label = QLabel(f"<b>Schweregrad:</b> {self.explanation.severity.value}")
        layout.addWidget(severity_label)
        
        # Kategorie
        category_label = QLabel(f"<b>Kategorie:</b> {self.explanation.category.value}")
        layout.addWidget(category_label)
        
        layout.addSpacing(10)
        
        # Technische Details
        tech_label = QLabel("<b>Technische Details:</b>")
        layout.addWidget(tech_label)
        
        tech_text = QTextEdit()
        tech_text.setReadOnly(True)
        tech_text.setPlainText(self.explanation.technical_details)
        tech_text.setMaximumHeight(150)
        layout.addWidget(tech_text)
        
        # Kontext-Daten (JSON-ähnlich)
        if self.explanation.context:
            layout.addSpacing(10)
            context_label = QLabel("<b>Kontext:</b>")
            layout.addWidget(context_label)
            
            context_text = QTextEdit()
            context_text.setReadOnly(True)
            # Filtere nicht-serialisierbare Objekte
            safe_context = {}
            for k, v in self.explanation.context.items():
                if isinstance(v, (str, int, float, bool, list, dict)):
                    safe_context[k] = v
                else:
                    safe_context[k] = str(v)
            
            import json
            context_text.setPlainText(json.dumps(safe_context, indent=2, default=str))
            layout.addWidget(context_text)
        
        layout.addStretch()
        return tab
        
    def _create_auto_fix_frame(self) -> QFrame:
        """Erstellt den Auto-Fix Hinweis-Bereich."""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #e8f5e9;
                border-left: 4px solid #4CAF50;
                border-radius: 4px;
                padding: 10px;
            }
        """)
        layout = QHBoxLayout(frame)
        
        icon_label = QLabel("🔧")
        icon_label.setStyleSheet("font-size: 20px;")
        layout.addWidget(icon_label)
        
        text_layout = QVBoxLayout()
        
        fix_title = QLabel(tr("Automatische Behebung verfügbar"))
        fix_title.setStyleSheet("font-weight: bold;")
        text_layout.addWidget(fix_title)
        
        fix_desc = QLabel(self.explanation.auto_fix_action)
        text_layout.addWidget(fix_desc)
        
        layout.addLayout(text_layout, stretch=1)
        
        self.auto_fix_btn = QPushButton(tr("Auto-Fix anwenden"))
        self.auto_fix_btn.setObjectName("success")
        self.auto_fix_btn.clicked.connect(self._on_auto_fix)
        layout.addWidget(self.auto_fix_btn)
        
        return frame
        
    def _create_context_frame(self) -> Optional[QFrame]:
        """Erstellt Kontext-Info Frame falls relevante Daten vorhanden."""
        context = self.explanation.context
        
        # Extrahiere relevante Info
        info_parts = []
        
        if 'feature_name' in context:
            info_parts.append(f"<b>Feature:</b> {context['feature_name']}")
        if 'feature_type' in context:
            info_parts.append(f"<b>Typ:</b> {context['feature_type']}")
        if 'parameter' in context:
            info_parts.append(f"<b>Parameter:</b> {context['parameter']}")
        
        if not info_parts:
            return None
        
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #fff3e0;
                border-left: 4px solid #FF9800;
                border-radius: 4px;
            }
        """)
        layout = QVBoxLayout(frame)
        
        for part in info_parts:
            label = QLabel(part)
            label.setStyleSheet("margin: 2px 0;")
            layout.addWidget(label)
        
        return frame
        
    def _create_buttons(self, layout):
        """Erstellt die Button-Leiste."""
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        # Copy Details Button
        copy_btn = QPushButton(tr("Details kopieren"))
        copy_btn.clicked.connect(self._copy_details)
        btn_layout.addWidget(copy_btn)
        
        # Help Button (falls Docs verfügbar)
        if self.explanation.related_docs:
            help_btn = QPushButton(tr("Hilfe"))
            help_btn.clicked.connect(self._open_help)
            btn_layout.addWidget(help_btn)
        
        # Close Button
        close_btn = QPushButton(tr("Schließen"))
        close_btn.setObjectName("primary")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
    def _set_severity_icon(self):
        """Setzt das Severity-Icon basierend auf dem Schweregrad."""
        styles = {
            ErrorSeverity.INFO: ("ℹ️", "#e3f2fd", "#1976d2"),
            ErrorSeverity.WARNING: ("⚠️", "#fff3e0", "#f57c00"),
            ErrorSeverity.RECOVERABLE: ("⚠️", "#fff3e0", "#f57c00"),
            ErrorSeverity.CRITICAL: ("✗", "#ffebee", "#c62828"),
        }
        
        icon, bg_color, fg_color = styles.get(
            self.explanation.severity, 
            ("✗", "#ffebee", "#c62828")
        )
        
        self.severity_icon.setText(icon)
        self.severity_icon.setStyleSheet(f"""
            background-color: {bg_color};
            color: {fg_color};
            border-radius: 24px;
            font-size: 24px;
            font-weight: bold;
        """)
        
    def _get_category_display(self) -> str:
        """Formatiert die Kategorie für die Anzeige."""
        category_names = {
            ErrorCategory.GEOMETRY: tr("Geometrie-Fehler"),
            ErrorCategory.TOPOLOGY: tr("Topologie-Fehler"),
            ErrorCategory.CONSTRAINT: tr("Constraint-Problem"),
            ErrorCategory.REFERENCE: tr("Referenz-Fehler"),
            ErrorCategory.PARAMETER: tr("Parameter-Fehler"),
            ErrorCategory.OPERATION: tr("Operations-Fehler"),
            ErrorCategory.DEPENDENCY: tr("Abhängigkeits-Fehler"),
            ErrorCategory.IMPORT_EXPORT: tr("Import/Export-Fehler"),
            ErrorCategory.SYSTEM: tr("System-Fehler"),
            ErrorCategory.UNKNOWN: tr("Unbekannter Fehler"),
        }
        return category_names.get(
            self.explanation.category, 
            self.explanation.category.value
        )
        
    def _on_auto_fix(self):
        """Handler für Auto-Fix Button."""
        self.auto_fix_clicked = True
        self.accept()
        
    def _copy_details(self):
        """Kopiert Fehlerdetails in die Zwischenablage."""
        from PySide6.QtWidgets import QApplication
        
        text = f"""Error: {self.explanation.error_code}
Title: {self.explanation.title}
Description: {self.explanation.description}
Severity: {self.explanation.severity.value}
Category: {self.explanation.category.value}

Next Actions:
"""
        for i, action in enumerate(self.explanation.next_actions, 1):
            text += f"{i}. {action}\n"
        
        if self.explanation.technical_details:
            text += f"\nTechnical: {self.explanation.technical_details}\n"
        
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        
        # Visuelles Feedback
        btn = self.sender()
        original_text = btn.text()
        btn.setText(tr("Kopiert!"))
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, lambda: btn.setText(original_text))
        
    def _open_help(self):
        """Öffnet Hilfe-Dokumentation."""
        # TODO: Implementiere Hilfe-System Integration
        logger.info(f"Help requested for error: {self.explanation.error_code}")
        
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            tr("Hilfe"),
            tr("Dokumentation wird in einem zukünftigen Update verfügbar sein.")
        )
        
    def _get_stylesheet(self) -> str:
        """Gibt das Stylesheet zurück."""
        return """
            QDialog {
                background-color: #ffffff;
            }
            QTabWidget::pane {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: #fafafa;
            }
            QTabBar::tab {
                padding: 8px 16px;
                margin-right: 2px;
                border: 1px solid #ddd;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                background-color: #f5f5f5;
            }
            QTabBar::tab:selected {
                background-color: #fafafa;
                border-bottom: 2px solid #2196F3;
            }
            QPushButton#primary {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton#primary:hover {
                background-color: #1976D2;
            }
            QPushButton#success {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton#success:hover {
                background-color: #45a049;
            }
        """


class ErrorToast(QWidget):
    """
    Kurze Fehler-Meldung als Toast/Popup.
    
    Für einfache Fehler die schnell angezeigt werden sollen
    ohne den vollen Details-Dialog.
    """
    
    def __init__(self, explanation: ErrorExplanation, parent=None, auto_hide_ms: int = 5000):
        super().__init__(parent)
        self.explanation = explanation
        self.auto_hide_ms = auto_hide_ms
        self._setup_ui()
        
    def _setup_ui(self):
        """Erstellt die UI."""
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)
        
        # Icon
        icon_label = QLabel(self._get_icon())
        icon_label.setStyleSheet("font-size: 18px;")
        layout.addWidget(icon_label)
        
        # Text
        text_layout = QVBoxLayout()
        
        title = QLabel(self.explanation.title)
        title.setStyleSheet("font-weight: bold;")
        text_layout.addWidget(title)
        
        desc = QLabel(self.explanation.description[:100] + "..." 
                     if len(self.explanation.description) > 100 
                     else self.explanation.description)
        desc.setWordWrap(True)
        text_layout.addWidget(desc)
        
        layout.addLayout(text_layout, stretch=1)
        
        # Details Button
        details_btn = QPushButton(tr("Details"))
        details_btn.setFlat(True)
        details_btn.clicked.connect(self._show_details)
        layout.addWidget(details_btn)
        
        # Styling basierend auf Severity
        self._apply_styling()
        
        # Auto-hide
        if self.auto_hide_ms > 0:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(self.auto_hide_ms, self.hide)
            
    def _get_icon(self) -> str:
        """Gibt das passende Icon zurück."""
        icons = {
            ErrorSeverity.INFO: "ℹ️",
            ErrorSeverity.WARNING: "⚠️",
            ErrorSeverity.RECOVERABLE: "⚠️",
            ErrorSeverity.CRITICAL: "✗",
        }
        return icons.get(self.explanation.severity, "✗")
        
    def _apply_styling(self):
        """Wendet Styling basierend auf Severity an."""
        colors = {
            ErrorSeverity.INFO: ("#e3f2fd", "#1976d2", "#bbdefb"),
            ErrorSeverity.WARNING: ("#fff3e0", "#f57c00", "#ffe0b2"),
            ErrorSeverity.RECOVERABLE: ("#fff3e0", "#f57c00", "#ffe0b2"),
            ErrorSeverity.CRITICAL: ("#ffebee", "#c62828", "#ffcdd2"),
        }
        
        bg, fg, border = colors.get(
            self.explanation.severity,
            ("#ffebee", "#c62828", "#ffcdd2")
        )
        
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                color: {fg};
                border: 2px solid {border};
                border-radius: 8px;
            }}
            QPushButton {{
                color: {fg};
                border: 1px solid {border};
                padding: 4px 8px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {border};
            }}
        """)
        
    def _show_details(self):
        """Zeigt den vollen Details-Dialog."""
        self.hide()
        dlg = ErrorDetailsDialog(self.explanation, self.parent())
        dlg.exec()


def show_error_dialog(
    error_code: str,
    context: dict = None,
    parent=None,
    show_auto_fix: bool = True
) -> tuple:
    """
    Convenience-Funktion zum Anzeigen eines Error-Dialogs.
    
    Returns:
        (accepted, auto_fix_clicked)
    """
    from modeling.error_diagnostics import ErrorDiagnostics
    
    explanation = ErrorDiagnostics.explain(error_code, context)
    dlg = ErrorDetailsDialog(explanation, parent, show_auto_fix)
    
    result = dlg.exec()
    return (result == QDialog.Accepted, dlg.auto_fix_clicked)
