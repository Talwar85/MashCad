"""
MashCAD - Error Explainer UI Integration
========================================

Phase 2: CH-008 - Fehlerdiagnostik im UI verbessern

UI-Integrations-Modul für das Error Diagnostics Framework.
Bietet einfache Methoden zur Anzeige von Fehlern mit Erklärungen.

Usage:
    from gui.error_explainer import ErrorExplainer
    
    # In MainWindow oder Controller
    self.error_explainer = ErrorExplainer(self)
    
    # Fehler anzeigen
    self.error_explainer.show_error("geometry_non_manifold", context={
        'feature': current_feature
    })
    
    # Oder aus einem Result
    result = some_operation()
    if result.is_error:
        self.error_explainer.show_from_result(result)

Author: Kimi (CH-008 Implementation)
Date: 2026-02-19
Branch: feature/v1-ux-aiB
"""

from typing import Optional, Dict, Any, Callable
from loguru import logger

from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import QObject, Signal

from modeling.error_diagnostics import (
    ErrorDiagnostics, ErrorExplanation, ErrorSeverity
)
from modeling.result_types import OperationResult, ResultStatus
from gui.dialogs.error_details_dialog import ErrorDetailsDialog, ErrorToast


class ErrorExplainer(QObject):
    """
    UI-Integration für Error Diagnostics.
    
    Zentrale Schnittstelle zur Anzeige von Fehlern mit:
    - Kontext-sensitiven Erklärungen
    - "Next Action" Vorschlägen
    - Auto-Fix Optionen
    - Toast-Notifications für einfache Fehler
    - Detail-Dialogen für komplexe Fehler
    
    Signals:
        error_shown: Wird emittet wenn ein Fehler angezeigt wurde
        auto_fix_requested: Wird emittet wenn User Auto-Fix anklickt
    """
    
    error_shown = Signal(str, str)  # error_code, title
    auto_fix_requested = Signal(str, dict)  # error_code, context
    error_dismissed = Signal(str)  # error_code
    
    def __init__(self, parent_widget: QWidget):
        """
        Args:
            parent_widget: Das Parent Widget für Dialoge
        """
        super().__init__()
        self.parent_widget = parent_widget
        self._last_error: Optional[ErrorExplanation] = None
        self._error_history: list = []
        self._auto_fix_handlers: Dict[str, Callable] = {}
        
    def show_error(
        self,
        error_code: str,
        context: Optional[Dict[str, Any]] = None,
        show_as_toast: bool = False,
        allow_auto_fix: bool = True
    ) -> bool:
        """
        Zeigt einen Fehler mit Erklärung an.
        
        Args:
            error_code: Der Error-Code
            context: Zusätzlicher Kontext
            show_as_toast: True für Toast, False für Dialog
            allow_auto_fix: Ob Auto-Fix Button angezeigt werden soll
            
        Returns:
            True wenn User den Dialog bestätigt hat (nicht applicable für Toast)
        """
        try:
            # Erklärung generieren
            explanation = ErrorDiagnostics.explain(error_code, context)
            self._last_error = explanation
            self._error_history.append(explanation)
            
            # Signal emitieren
            self.error_shown.emit(error_code, explanation.title)
            
            # Anzeigen
            if show_as_toast:
                self._show_toast(explanation)
                return True
            else:
                return self._show_dialog(explanation, allow_auto_fix)
                
        except Exception as e:
            logger.exception(f"Failed to show error {error_code}: {e}")
            # Fallback: Einfache Nachricht
            self._show_fallback_error(error_code, str(e))
            return False
            
    def show_from_result(
        self,
        result: OperationResult,
        context: Optional[Dict[str, Any]] = None,
        show_as_toast: bool = False
    ) -> bool:
        """
        Zeigt einen Fehler aus einem OperationResult an.
        
        Args:
            result: Das OperationResult (muss is_error sein)
            context: Zusätzlicher Kontext
            show_as_toast: True für Toast, False für Dialog
            
        Returns:
            True wenn User den Dialog bestätigt hat
        """
        if not result.is_error:
            logger.warning("show_from_result called with non-error result")
            return True
        
        # Extrahiere Error-Code
        error_code = result.details.get('error_code', 'system_unknown')
        
        # Kontext erweitern
        full_context = {
            'result': result,
            'message': result.message,
            'details': result.details,
            **(context or {})
        }
        
        return self.show_error(error_code, full_context, show_as_toast)
        
    def show_warning(
        self,
        message: str,
        title: str = "Warnung",
        details: str = ""
    ):
        """
        Zeigt eine einfache Warnung an.
        
        Args:
            message: Warnmeldung
            title: Titel
            details: Zusätzliche Details
        """
        from PySide6.QtWidgets import QMessageBox
        
        msg_box = QMessageBox(self.parent_widget)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        if details:
            msg_box.setDetailedText(details)
        msg_box.exec()
        
    def show_info(
        self,
        message: str,
        title: str = "Information"
    ):
        """Zeigt eine Info-Nachricht an."""
        from PySide6.QtWidgets import QMessageBox
        
        QMessageBox.information(self.parent_widget, title, message)
        
    def register_auto_fix_handler(
        self,
        error_code: str,
        handler: Callable[[Dict[str, Any]], bool]
    ):
        """
        Registriert einen Handler für Auto-Fix.
        
        Args:
            error_code: Der Error-Code der behandelt wird
            handler: Funktion(context) -> bool (True bei Erfolg)
        """
        self._auto_fix_handlers[error_code] = handler
        logger.debug(f"Registered auto-fix handler for {error_code}")
        
    def try_auto_fix(self, error_code: str, context: Dict[str, Any]) -> bool:
        """
        Versucht automatische Fehlerbehebung.
        
        Args:
            error_code: Der zu behebende Fehler
            context: Kontext-Daten
            
        Returns:
            True wenn Behebung erfolgreich
        """
        if error_code not in self._auto_fix_handlers:
            logger.warning(f"No auto-fix handler registered for {error_code}")
            return False
        
        try:
            handler = self._auto_fix_handlers[error_code]
            success = handler(context)
            
            if success:
                logger.info(f"Auto-fix succeeded for {error_code}")
                self.show_info(
                    tr("Das Problem wurde automatisch behoben."),
                    tr("Erfolg")
                )
            else:
                logger.warning(f"Auto-fix failed for {error_code}")
                self.show_warning(
                    tr("Automatische Behebung fehlgeschlagen. Bitte manuell korrigieren."),
                    tr("Hinweis")
                )
            
            return success
            
        except Exception as e:
            logger.exception(f"Auto-fix handler failed for {error_code}: {e}")
            self.show_warning(
                tr(f"Fehler bei automatischer Behebung: {e}"),
                tr("Fehler")
            )
            return False
            
    def get_last_error(self) -> Optional[ErrorExplanation]:
        """Gibt den zuletzt angezeigten Fehler zurück."""
        return self._last_error
        
    def get_error_history(self) -> list:
        """Gibt die Fehler-Historie zurück."""
        return self._error_history.copy()
        
    def clear_history(self):
        """Löscht die Fehler-Historie."""
        self._error_history.clear()
        self._last_error = None
        
    def _show_dialog(
        self,
        explanation: ErrorExplanation,
        allow_auto_fix: bool
    ) -> bool:
        """Zeigt den Detail-Dialog."""
        dlg = ErrorDetailsDialog(
            explanation,
            self.parent_widget,
            show_auto_fix=allow_auto_fix and explanation.can_auto_fix
        )
        
        result = dlg.exec()
        
        # Prüfe auf Auto-Fix
        if dlg.auto_fix_clicked and explanation.can_auto_fix:
            self.auto_fix_requested.emit(
                explanation.error_code,
                explanation.context
            )
            # Führe Auto-Fix aus falls Handler registriert
            self.try_auto_fix(explanation.error_code, explanation.context)
        
        if result == ErrorDetailsDialog.Accepted:
            self.error_dismissed.emit(explanation.error_code)
            return True
        return False
        
    def _show_toast(self, explanation: ErrorExplanation):
        """Zeigt einen Toast."""
        toast = ErrorToast(explanation, self.parent_widget)
        
        # Positioniere Toast (oben rechts vom Parent)
        parent_geo = self.parent_widget.geometry()
        toast_width = 400
        toast_height = 100
        x = parent_geo.right() - toast_width - 20
        y = parent_geo.top() + 40
        toast.setGeometry(x, y, toast_width, toast_height)
        
        toast.show()
        
    def _show_fallback_error(self, error_code: str, error_message: str):
        """Fallback-Anzeige wenn das Error System selbst fehlschlägt."""
        from PySide6.QtWidgets import QMessageBox
        
        QMessageBox.critical(
            self.parent_widget,
            tr("Fehler"),
            tr(f"Ein Fehler ist aufgetreten: {error_code}\n\n{error_message}")
        )


# =============================================================================
# Global Error Handler Integration
# =============================================================================

class GlobalErrorHandler:
    """
    Globaler Error-Handler für unbehandelte Exceptions.
    
    Fängt Python-Exceptions ab und zeigt sie als benutzerfreundliche
    Fehlermeldungen an.
    """
    
    _instance: Optional['GlobalErrorHandler'] = None
    _explainer: Optional[ErrorExplainer] = None
    
    @classmethod
    def initialize(cls, parent_widget: QWidget):
        """Initialisiert den globalen Error Handler."""
        if cls._instance is None:
            cls._instance = cls()
            cls._explainer = ErrorExplainer(parent_widget)
            
            # Registriere Exception Hook
            import sys
            sys.excepthook = cls._custom_excepthook
            
            logger.info("Global error handler initialized")
            
    @classmethod
    def _custom_excepthook(cls, exc_type, exc_value, exc_traceback):
        """Custom Exception Handler."""
        # Logge den Fehler
        logger.exception("Unhandled exception", 
                        exc_info=(exc_type, exc_value, exc_traceback))
        
        # Zeige benutzerfreundliche Meldung
        if cls._explainer:
            error_code = f"system_{exc_type.__name__.lower()}"
            cls._explainer.show_error(error_code, {
                'exception': exc_value,
                'exception_type': exc_type.__name__,
            })
        else:
            # Fallback
            import traceback
            traceback.print_exception(exc_type, exc_value, exc_traceback)
            
    @classmethod
    def get_explainer(cls) -> Optional[ErrorExplainer]:
        """Gibt den ErrorExplainer zurück."""
        return cls._explainer


# =============================================================================
# Decorator für automatische Error-Behandlung
# =============================================================================

def with_error_handling(
    error_code: str = None,
    context_provider: Callable = None,
    show_dialog: bool = True
):
    """
    Decorator für automatische Error-Behandlung in Funktionen.
    
    Usage:
        @with_error_handling(
            error_code="operation_boolean_failed",
            context_provider=lambda self: {'feature': self.current_feature}
        )
        def do_boolean_operation(self):
            # ... operation ...
            pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Bestimme Error-Code
                code = error_code or f"system_{type(e).__name__.lower()}"
                
                # Sammle Kontext
                context = {'exception': e}
                if context_provider:
                    try:
                        provided = context_provider(*args, **kwargs)
                        context.update(provided)
                    except Exception:
                        pass
                
                # Zeige Fehler
                if GlobalErrorHandler._explainer and show_dialog:
                    GlobalErrorHandler._explainer.show_error(code, context)
                
                # Re-raise für weitere Behandlung
                raise
        return wrapper
    return decorator


# =============================================================================
# Convenience Functions
# =============================================================================

def show_error(
    error_code: str,
    context: dict = None,
    parent=None
) -> bool:
    """Shortcut zum Anzeigen eines Fehlers."""
    if parent is None:
        # Versuche aktives Fenster zu finden
        app = QApplication.instance()
        if app:
            parent = app.activeWindow()
    
    explainer = ErrorExplainer(parent)
    return explainer.show_error(error_code, context)


def show_from_result(result: OperationResult, parent=None) -> bool:
    """Shortcut zum Anzeigen eines Fehlers aus einem Result."""
    if parent is None:
        app = QApplication.instance()
        if app:
            parent = app.activeWindow()
    
    explainer = ErrorExplainer(parent)
    return explainer.show_from_result(result)


# Translation helper
def tr(text: str) -> str:
    """Translation wrapper."""
    try:
        from i18n import tr as i18n_tr
        return i18n_tr(text)
    except ImportError:
        return text
