"""
FeatureController - UI-Orchestrierung für Feature-Operationen
=============================================================

W17 Paket C (AR-004 Phase-2): Extrahiert Feature-Operations-Logik aus MainWindow.
Zuständig für:
- Extrude Operationen
- Revolve Operationen
- Fillet/Chamfer Operationen
- Shell/Wall Thickness Operationen
- Boolean Operationen
- Pattern Operationen
- Loft/Sweep Operationen

Author: GLM 4.7 (UX/Workflow Delivery Cell)
Date: 2026-02-16
Branch: feature/v1-ux-aiB
"""

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox
from loguru import logger
from typing import Optional, List, Dict, Any, Callable
from enum import Enum, auto

from i18n import tr


class FeatureOperationType(Enum):
    """Typen von Feature-Operationen."""
    EXTRUDE = auto()
    REVOLVE = auto()
    FILLET = auto()
    CHAMFER = auto()
    SHELL = auto()
    BOOLEAN_UNION = auto()
    BOOLEAN_SUBTRACT = auto()
    BOOLEAN_INTERSECT = auto()
    PATTERN_LINEAR = auto()
    PATTERN_CIRCULAR = auto()
    LOFT = auto()
    SWEEP = auto()
    DRAFT = auto()
    HOLE = auto()
    THREAD = auto()


class FeatureController(QObject):
    """
    Controller für Feature-Operationen.
    
    Kapselt alle Feature-bezogenen Operationen und delegiert an MainWindow
    für UI-Interaktionen und tatsächliche Ausführung.
    """
    
    # Signals for UI updates
    operation_started = Signal(str)  # operation_type
    operation_finished = Signal(bool, str, object)  # success, message, result
    operation_cancelled = Signal(str)  # operation_type
    
    def __init__(self, main_window):
        """
        Args:
            main_window: MainWindow Instanz (für UI-Zugriff)
        """
        super().__init__(None)  # QObject Parent ist None, MainWindow wird separat gespeichert
        self._mw = main_window
        self._active_operation = None
        self._operation_state = {}
        
    # ========================================================================
    # Extrude Operations
    # ========================================================================
    
    def start_extrude(self, face_id: Optional[str] = None) -> bool:
        """
        Startet Extrude-Operation für ein Face.
        
        Args:
            face_id: ID des Faces (None = User muss auswählen)
            
        Returns:
            bool: True wenn Operation gestartet wurde
        """
        self._active_operation = FeatureOperationType.EXTRUDE
        self.operation_started.emit("EXTRUDE")
        
        # Delegate to MainWindow
        if hasattr(self._mw, '_start_extrude_impl'):
            return self._mw._start_extrude_impl(face_id)
            
        # Fallback: Status message
        self._mw.statusBar().showMessage(tr("Wählen Sie ein Face zum Extrudieren"))
        return True
        
    def confirm_extrude(self, params: Dict[str, Any]) -> bool:
        """
        Bestätigt Extrude-Operation mit Parametern.
        
        Args:
            params: {'height': float, 'operation': str, 'target_face': Optional[str]}
            
        Returns:
            bool: True wenn Operation erfolgreich
        """
        if self._active_operation != FeatureOperationType.EXTRUDE:
            logger.warning("confirm_extrude called without active EXTRUDE operation")
            return False
            
        try:
            if hasattr(self._mw, '_confirm_extrude_impl'):
                result = self._mw._confirm_extrude_impl(params)
                self.operation_finished.emit(True, tr("Extrude erfolgreich"), result)
                self._active_operation = None
                return True
        except Exception as e:
            logger.exception("Extrude Error")
            self.operation_finished.emit(False, str(e), None)
            return False
            
        return False
        
    def cancel_extrude(self):
        """Bricht Extrude-Operation ab."""
        if self._active_operation == FeatureOperationType.EXTRUDE:
            self.operation_cancelled.emit("EXTRUDE")
            self._active_operation = None
            
            if hasattr(self._mw, '_cancel_extrude_impl'):
                self._mw._cancel_extrude_impl()
                
    # ========================================================================
    # Revolve Operations
    # ========================================================================
    
    def start_revolve(self, face_id: Optional[str] = None) -> bool:
        """
        Startet Revolve-Operation für ein Face.
        
        Args:
            face_id: ID des Faces (None = User muss auswählen)
            
        Returns:
            bool: True wenn Operation gestartet wurde
        """
        self._active_operation = FeatureOperationType.REVOLVE
        self.operation_started.emit("REVOLVE")
        
        if hasattr(self._mw, '_start_revolve_impl'):
            return self._mw._start_revolve_impl(face_id)
            
        self._mw.statusBar().showMessage(tr("Wählen Sie ein Face und Rotationsachse"))
        return True
        
    def confirm_revolve(self, params: Dict[str, Any]) -> bool:
        """
        Bestätigt Revolve-Operation.
        
        Args:
            params: {'angle': float, 'axis': str, 'operation': str}
        """
        if self._active_operation != FeatureOperationType.REVOLVE:
            return False
            
        try:
            if hasattr(self._mw, '_confirm_revolve_impl'):
                result = self._mw._confirm_revolve_impl(params)
                self.operation_finished.emit(True, tr("Revolve erfolgreich"), result)
                self._active_operation = None
                return True
        except Exception as e:
            logger.exception("Revolve Error")
            self.operation_finished.emit(False, str(e), None)
            return False
            
        return False
        
    def cancel_revolve(self):
        """Bricht Revolve-Operation ab."""
        if self._active_operation == FeatureOperationType.REVOLVE:
            self.operation_cancelled.emit("REVOLVE")
            self._active_operation = None
            
            if hasattr(self._mw, '_cancel_revolve_impl'):
                self._mw._cancel_revolve_impl()
                
    # ========================================================================
    # Fillet Operations
    # ========================================================================
    
    def start_fillet(self, body_id: Optional[str] = None) -> bool:
        """
        Startet Fillet-Operation für einen Body.
        
        Args:
            body_id: ID des Bodies (None = User muss auswählen)
        """
        self._active_operation = FeatureOperationType.FILLET
        self.operation_started.emit("FILLET")
        
        if hasattr(self._mw, '_start_fillet_impl'):
            return self._mw._start_fillet_impl(body_id)
            
        self._mw.statusBar().showMessage(tr("Wählen Sie Kanten zum Filletten"))
        return True
        
    def confirm_fillet(self, radius: float, edge_ids: List[str]) -> bool:
        """
        Bestätigt Fillet-Operation.
        
        Args:
            radius: Fillet-Radius
            edge_ids: Liste der Edge-IDs
        """
        if self._active_operation != FeatureOperationType.FILLET:
            return False
            
        try:
            if hasattr(self._mw, '_confirm_fillet_impl'):
                result = self._mw._confirm_fillet_impl(radius, edge_ids)
                self.operation_finished.emit(True, tr("Fillet erfolgreich"), result)
                self._active_operation = None
                return True
        except Exception as e:
            logger.exception("Fillet Error")
            self.operation_finished.emit(False, str(e), None)
            return False
            
        return False
        
    def cancel_fillet(self):
        """Bricht Fillet-Operation ab."""
        if self._active_operation == FeatureOperationType.FILLET:
            self.operation_cancelled.emit("FILLET")
            self._active_operation = None
            
            if hasattr(self._mw, '_cancel_fillet_impl'):
                self._mw._cancel_fillet_impl()
                
    # ========================================================================
    # Shell Operations
    # ========================================================================
    
    def start_shell(self, body_id: Optional[str] = None) -> bool:
        """
        Startet Shell-Operation für einen Body.
        
        Args:
            body_id: ID des Bodies (None = User muss auswählen)
        """
        self._active_operation = FeatureOperationType.SHELL
        self.operation_started.emit("SHELL")
        
        if hasattr(self._mw, '_start_shell_impl'):
            return self._mw._start_shell_impl(body_id)
            
        self._mw.statusBar().showMessage(tr("Wählen Sie Faces zum Entfernen"))
        return True
        
    def confirm_shell(self, thickness: float, face_ids: List[str]) -> bool:
        """
        Bestätigt Shell-Operation.
        
        Args:
            thickness: Wandstärke
            face_ids: Liste der zu entfernenden Face-IDs
        """
        if self._active_operation != FeatureOperationType.SHELL:
            return False
            
        try:
            if hasattr(self._mw, '_confirm_shell_impl'):
                result = self._mw._confirm_shell_impl(thickness, face_ids)
                self.operation_finished.emit(True, tr("Shell erfolgreich"), result)
                self._active_operation = None
                return True
        except Exception as e:
            logger.exception("Shell Error")
            self.operation_finished.emit(False, str(e), None)
            return False
            
        return False
        
    def cancel_shell(self):
        """Bricht Shell-Operation ab."""
        if self._active_operation == FeatureOperationType.SHELL:
            self.operation_cancelled.emit("SHELL")
            self._active_operation = None
            
            if hasattr(self._mw, '_cancel_shell_impl'):
                self._mw._cancel_shell_impl()
                
    # ========================================================================
    # Boolean Operations
    # ========================================================================
    
    def start_boolean(self, operation: str, target_id: Optional[str] = None) -> bool:
        """
        Startet Boolean-Operation.
        
        Args:
            operation: 'union', 'subtract', oder 'intersect'
            target_id: ID des Ziel-Bodies (None = User muss auswählen)
        """
        op_map = {
            'union': FeatureOperationType.BOOLEAN_UNION,
            'subtract': FeatureOperationType.BOOLEAN_SUBTRACT,
            'intersect': FeatureOperationType.BOOLEAN_INTERSECT
        }
        
        if operation not in op_map:
            logger.error(f"Unknown boolean operation: {operation}")
            return False
            
        self._active_operation = op_map[operation]
        self.operation_started.emit(f"BOOLEAN_{operation.upper()}")
        
        if hasattr(self._mw, '_start_boolean_impl'):
            return self._mw._start_boolean_impl(operation, target_id)
            
        self._mw.statusBar().showMessage(tr(f"Wählen Sie Bodies für Boolean {operation}"))
        return True
        
    def confirm_boolean(self, target_id: str, tool_id: str) -> bool:
        """
        Bestätigt Boolean-Operation.
        
        Args:
            target_id: ID des Ziel-Bodies
            tool_id: ID des Tool-Bodies
        """
        if self._active_operation not in [
            FeatureOperationType.BOOLEAN_UNION,
            FeatureOperationType.BOOLEAN_SUBTRACT,
            FeatureOperationType.BOOLEAN_INTERSECT
        ]:
            return False
            
        try:
            if hasattr(self._mw, '_confirm_boolean_impl'):
                result = self._mw._confirm_boolean_impl(target_id, tool_id)
                self.operation_finished.emit(True, tr("Boolean erfolgreich"), result)
                self._active_operation = None
                return True
        except Exception as e:
            logger.exception("Boolean Error")
            self.operation_finished.emit(False, str(e), None)
            return False
            
        return False
        
    def cancel_boolean(self):
        """Bricht Boolean-Operation ab."""
        if self._active_operation in [
            FeatureOperationType.BOOLEAN_UNION,
            FeatureOperationType.BOOLEAN_SUBTRACT,
            FeatureOperationType.BOOLEAN_INTERSECT
        ]:
            self.operation_cancelled.emit("BOOLEAN")
            self._active_operation = None
            
            if hasattr(self._mw, '_cancel_boolean_impl'):
                self._mw._cancel_boolean_impl()
                
    # ========================================================================
    # Pattern Operations
    # ========================================================================
    
    def start_pattern(self, pattern_type: str, body_id: Optional[str] = None) -> bool:
        """
        Startet Pattern-Operation.
        
        Args:
            pattern_type: 'linear' oder 'circular'
            body_id: ID des Bodies (None = User muss auswählen)
        """
        op_map = {
            'linear': FeatureOperationType.PATTERN_LINEAR,
            'circular': FeatureOperationType.PATTERN_CIRCULAR
        }
        
        if pattern_type not in op_map:
            logger.error(f"Unknown pattern type: {pattern_type}")
            return False
            
        self._active_operation = op_map[pattern_type]
        self.operation_started.emit(f"PATTERN_{pattern_type.upper()}")
        
        if hasattr(self._mw, '_start_pattern_impl'):
            return self._mw._start_pattern_impl(pattern_type, body_id)
            
        self._mw.statusBar().showMessage(tr(f"Wählen Sie Parameter für {pattern_type} Pattern"))
        return True
        
    def confirm_pattern(self, params: Dict[str, Any]) -> bool:
        """
        Bestätigt Pattern-Operation.
        
        Args:
            params: Pattern-spezifische Parameter
        """
        if self._active_operation not in [
            FeatureOperationType.PATTERN_LINEAR,
            FeatureOperationType.PATTERN_CIRCULAR
        ]:
            return False
            
        try:
            if hasattr(self._mw, '_confirm_pattern_impl'):
                result = self._mw._confirm_pattern_impl(params)
                self.operation_finished.emit(True, tr("Pattern erfolgreich"), result)
                self._active_operation = None
                return True
        except Exception as e:
            logger.exception("Pattern Error")
            self.operation_finished.emit(False, str(e), None)
            return False
            
        return False
        
    def cancel_pattern(self):
        """Bricht Pattern-Operation ab."""
        if self._active_operation in [
            FeatureOperationType.PATTERN_LINEAR,
            FeatureOperationType.PATTERN_CIRCULAR
        ]:
            self.operation_cancelled.emit("PATTERN")
            self._active_operation = None
            
            if hasattr(self._mw, '_cancel_pattern_impl'):
                self._mw._cancel_pattern_impl()
                
    # ========================================================================
    # Loft/Sweep Operations
    # ========================================================================
    
    def start_loft(self) -> bool:
        """Startet Loft-Operation."""
        self._active_operation = FeatureOperationType.LOFT
        self.operation_started.emit("LOFT")
        
        if hasattr(self._mw, '_start_loft_impl'):
            return self._mw._start_loft_impl()
            
        self._mw.statusBar().showMessage(tr("Wählen Sie Profile für Loft"))
        return True
        
    def confirm_loft(self, profile_ids: List[str]) -> bool:
        """
        Bestätigt Loft-Operation.
        
        Args:
            profile_ids: Liste der Profile-IDs
        """
        if self._active_operation != FeatureOperationType.LOFT:
            return False
            
        try:
            if hasattr(self._mw, '_confirm_loft_impl'):
                result = self._mw._confirm_loft_impl(profile_ids)
                self.operation_finished.emit(True, tr("Loft erfolgreich"), result)
                self._active_operation = None
                return True
        except Exception as e:
            logger.exception("Loft Error")
            self.operation_finished.emit(False, str(e), None)
            return False
            
        return False
        
    def cancel_loft(self):
        """Bricht Loft-Operation ab."""
        if self._active_operation == FeatureOperationType.LOFT:
            self.operation_cancelled.emit("LOFT")
            self._active_operation = None
            
            if hasattr(self._mw, '_cancel_loft_impl'):
                self._mw._cancel_loft_impl()
                
    def start_sweep(self) -> bool:
        """Startet Sweep-Operation."""
        self._active_operation = FeatureOperationType.SWEEP
        self.operation_started.emit("SWEEP")
        
        if hasattr(self._mw, '_start_sweep_impl'):
            return self._mw._start_sweep_impl()
            
        self._mw.statusBar().showMessage(tr("Wählen Sie Profil und Pfad für Sweep"))
        return True
        
    def confirm_sweep(self, profile_id: str, path_id: str) -> bool:
        """
        Bestätigt Sweep-Operation.
        
        Args:
            profile_id: ID des Profil-Faces
            path_id: ID des Pfads (Edge oder Wire)
        """
        if self._active_operation != FeatureOperationType.SWEEP:
            return False
            
        try:
            if hasattr(self._mw, '_confirm_sweep_impl'):
                result = self._mw._confirm_sweep_impl(profile_id, path_id)
                self.operation_finished.emit(True, tr("Sweep erfolgreich"), result)
                self._active_operation = None
                return True
        except Exception as e:
            logger.exception("Sweep Error")
            self.operation_finished.emit(False, str(e), None)
            return False
            
        return False
        
    def cancel_sweep(self):
        """Bricht Sweep-Operation ab."""
        if self._active_operation == FeatureOperationType.SWEEP:
            self.operation_cancelled.emit("SWEEP")
            self._active_operation = None
            
            if hasattr(self._mw, '_cancel_sweep_impl'):
                self._mw._cancel_sweep_impl()
                
    # ========================================================================
    # Utility Methods
    # ========================================================================
    
    def get_active_operation(self) -> Optional[FeatureOperationType]:
        """Gibt aktive Operation zurück."""
        return self._active_operation
        
    def is_operation_active(self) -> bool:
        """Prüft ob eine Operation aktiv ist."""
        return self._active_operation is not None
        
    def cancel_active_operation(self):
        """Bricht aktive Operation ab."""
        if self._active_operation == FeatureOperationType.EXTRUDE:
            self.cancel_extrude()
        elif self._active_operation == FeatureOperationType.REVOLVE:
            self.cancel_revolve()
        elif self._active_operation == FeatureOperationType.FILLET:
            self.cancel_fillet()
        elif self._active_operation == FeatureOperationType.SHELL:
            self.cancel_shell()
        elif self._active_operation in [
            FeatureOperationType.BOOLEAN_UNION,
            FeatureOperationType.BOOLEAN_SUBTRACT,
            FeatureOperationType.BOOLEAN_INTERSECT
        ]:
            self.cancel_boolean()
        elif self._active_operation in [
            FeatureOperationType.PATTERN_LINEAR,
            FeatureOperationType.PATTERN_CIRCULAR
        ]:
            self.cancel_pattern()
        elif self._active_operation == FeatureOperationType.LOFT:
            self.cancel_loft()
        elif self._active_operation == FeatureOperationType.SWEEP:
            self.cancel_sweep()
            
    def cleanup(self):
        """Räumt auf beim Beenden."""
        self.cancel_active_operation()
        self._operation_state.clear()
