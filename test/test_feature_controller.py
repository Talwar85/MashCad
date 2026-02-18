"""
FeatureController Tests (W17 Paket C)
=====================================
Validiert dass FeatureController korrekt aus MainWindow extrahiert wurde.

Test-Strategie:
- Behavior-Proof Tests für alle Feature-Operationen
- Operation State Machine (start -> confirm/cancel)
- Delegation an MainWindow
- Aktive Operation Tracking

Author: GLM 4.7 (UX/Workflow Delivery Cell)
Date: 2026-02-16
Branch: feature/v1-ux-aiB
"""

import pytest
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# CRITICAL: QT_OPENGL muss VOR jedem Qt/PyVista Import gesetzt werden
os.environ["QT_OPENGL"] = "software"

from PySide6.QtWidgets import QApplication

# Import controller
sys.path.insert(0, str(Path(__file__).parent.parent / "gui"))
from gui.feature_controller import FeatureController, FeatureOperationType


class MockMainWindow:
    """Mock für MainWindow Tests."""
    
    def __init__(self):
        self.statusBar = MagicMock(return_value=MagicMock())
        

class TestFeatureController:
    """W17 Paket C: FeatureController Behavior Tests."""
    
    @pytest.fixture
    def mock_mw(self):
        """Mock MainWindow Fixture."""
        return MockMainWindow()
        
    @pytest.fixture
    def controller(self, mock_mw):
        """FeatureController Fixture."""
        return FeatureController(mock_mw)
        
    def test_controller_exists(self, controller):
        """
        C-W17-R17: FeatureController existiert und ist initialisiert.
        """
        assert controller is not None
        assert controller._mw is not None
        assert controller._active_operation is None
        assert controller._operation_state == {}
        
    def test_start_extrude_sets_active_operation(self, controller):
        """
        C-W17-R18: start_extrude setzt aktive Operation.
        
        GIVEN: Keine aktive Operation
        WHEN: start_extrude() aufgerufen
        THEN: _active_operation = EXTRUDE, Signal emitted
        """
        signals = []
        controller.operation_started.connect(lambda op: signals.append(op))
        
        result = controller.start_extrude()
        
        assert controller._active_operation == FeatureOperationType.EXTRUDE
        assert "EXTRUDE" in signals
        assert result is True
        
    def test_confirm_extrude_without_active_fails(self, controller):
        """
        C-W17-R19: confirm_extrude ohne aktive Operation schlägt fehl.
        """
        controller._active_operation = None
        
        result = controller.confirm_extrude({'height': 10.0})
        
        assert result is False
        
    def test_confirm_extrude_with_wrong_active_fails(self, controller):
        """
        C-W17-R20: confirm_extrude mit falscher aktiver Operation schlägt fehl.
        """
        controller._active_operation = FeatureOperationType.REVOLVE
        
        result = controller.confirm_extrude({'height': 10.0})
        
        assert result is False
        
    def test_confirm_extrude_delegates_to_mainwindow(self, controller, mock_mw):
        """
        C-W17-R21: confirm_extrude delegiert an MainWindow.
        """
        controller._active_operation = FeatureOperationType.EXTRUDE
        mock_mw._confirm_extrude_impl = MagicMock(return_value="result_body")
        
        signals = []
        controller.operation_finished.connect(
            lambda success, msg, result: signals.append((success, msg))
        )
        
        result = controller.confirm_extrude({'height': 10.0})
        
        assert result is True
        mock_mw._confirm_extrude_impl.assert_called_once()
        assert len(signals) == 1
        assert signals[0][0] is True
        
    def test_cancel_extrude_clears_operation(self, controller):
        """
        C-W17-R22: cancel_extrude löscht aktive Operation.
        """
        controller._active_operation = FeatureOperationType.EXTRUDE
        
        signals = []
        controller.operation_cancelled.connect(lambda op: signals.append(op))
        
        controller.cancel_extrude()
        
        assert controller._active_operation is None
        assert "EXTRUDE" in signals
        
    def test_start_revolve_sets_active_operation(self, controller):
        """
        C-W17-R23: start_revolve setzt aktive Operation.
        """
        signals = []
        controller.operation_started.connect(lambda op: signals.append(op))
        
        result = controller.start_revolve()
        
        assert controller._active_operation == FeatureOperationType.REVOLVE
        assert "REVOLVE" in signals
        
    def test_start_fillet_sets_active_operation(self, controller):
        """
        C-W17-R24: start_fillet setzt aktive Operation.
        """
        signals = []
        controller.operation_started.connect(lambda op: signals.append(op))
        
        result = controller.start_fillet()
        
        assert controller._active_operation == FeatureOperationType.FILLET
        assert "FILLET" in signals
        
    def test_confirm_fillet_with_valid_params(self, controller, mock_mw):
        """
        C-W17-R25: confirm_fillet mit gültigen Parametern.
        """
        controller._active_operation = FeatureOperationType.FILLET
        mock_mw._confirm_fillet_impl = MagicMock(return_value="result")
        
        signals = []
        controller.operation_finished.connect(
            lambda s, m, r: signals.append((s, m))
        )
        
        result = controller.confirm_fillet(2.5, ['edge1', 'edge2'])
        
        assert result is True
        assert len(signals) == 1
        assert signals[0][0] is True
        
    def test_start_shell_sets_active_operation(self, controller):
        """
        C-W17-R26: start_shell setzt aktive Operation.
        """
        signals = []
        controller.operation_started.connect(lambda op: signals.append(op))
        
        result = controller.start_shell()
        
        assert controller._active_operation == FeatureOperationType.SHELL
        assert "SHELL" in signals
        
    def test_start_boolean_sets_correct_operation_type(self, controller):
        """
        C-W17-R27: start_boolean setzt korrekten Operation-Typ.
        """
        test_cases = [
            ('union', FeatureOperationType.BOOLEAN_UNION),
            ('subtract', FeatureOperationType.BOOLEAN_SUBTRACT),
            ('intersect', FeatureOperationType.BOOLEAN_INTERSECT),
        ]
        
        for op_str, expected_type in test_cases:
            controller.start_boolean(op_str)
            assert controller._active_operation == expected_type, f"Failed for {op_str}"
            
    def test_start_boolean_unknown_operation_returns_false(self, controller):
        """
        C-W17-R28: start_boolean mit unbekanntem Typ gibt False zurück.
        """
        result = controller.start_boolean('unknown')
        
        assert result is False
        
    def test_start_pattern_sets_correct_operation_type(self, controller):
        """
        C-W17-R29: start_pattern setzt korrekten Operation-Typ.
        """
        test_cases = [
            ('linear', FeatureOperationType.PATTERN_LINEAR),
            ('circular', FeatureOperationType.PATTERN_CIRCULAR),
        ]
        
        for pattern_type, expected_type in test_cases:
            controller.start_pattern(pattern_type)
            assert controller._active_operation == expected_type
            
    def test_start_pattern_unknown_type_returns_false(self, controller):
        """
        C-W17-R30: start_pattern mit unbekanntem Typ gibt False zurück.
        """
        result = controller.start_pattern('radial')
        
        assert result is False
        
    def test_start_loft_sets_active_operation(self, controller):
        """
        C-W17-R31: start_loft setzt aktive Operation.
        """
        controller.start_loft()
        
        assert controller._active_operation == FeatureOperationType.LOFT
        
    def test_start_sweep_sets_active_operation(self, controller):
        """
        C-W17-R32: start_sweep setzt aktive Operation.
        """
        controller.start_sweep()
        
        assert controller._active_operation == FeatureOperationType.SWEEP
        
    def test_is_operation_active_returns_correct_state(self, controller):
        """
        C-W17-R33: is_operation_active gibt korrekten Zustand zurück.
        """
        assert controller.is_operation_active() is False
        
        controller._active_operation = FeatureOperationType.EXTRUDE
        assert controller.is_operation_active() is True
        
        controller._active_operation = None
        assert controller.is_operation_active() is False
        
    def test_get_active_operation_returns_current(self, controller):
        """
        C-W17-R34: get_active_operation gibt aktuelle Operation zurück.
        """
        assert controller.get_active_operation() is None
        
        controller._active_operation = FeatureOperationType.FILLET
        assert controller.get_active_operation() == FeatureOperationType.FILLET
        
    def test_cancel_active_operation_extrude(self, controller):
        """
        C-W17-R35: cancel_active_operation bricht Extrude ab.
        """
        controller._active_operation = FeatureOperationType.EXTRUDE
        controller.cancel_extrude = MagicMock()
        
        controller.cancel_active_operation()
        
        controller.cancel_extrude.assert_called_once()
        
    def test_cancel_active_operation_fillet(self, controller):
        """
        C-W17-R36: cancel_active_operation bricht Fillet ab.
        """
        controller._active_operation = FeatureOperationType.FILLET
        controller.cancel_fillet = MagicMock()
        
        controller.cancel_active_operation()
        
        controller.cancel_fillet.assert_called_once()
        
    def test_cleanup_clears_all_state(self, controller):
        """
        C-W17-R37: cleanup löscht alle State.
        """
        controller._active_operation = FeatureOperationType.EXTRUDE
        controller._operation_state = {'key': 'value'}
        controller.cancel_active_operation = MagicMock()
        
        controller.cleanup()
        
        controller.cancel_active_operation.assert_called_once()
        assert controller._operation_state == {}
        
    def test_confirm_with_exception_emits_finished_error(self, controller, mock_mw):
        """
        C-W17-R38: Exception in confirm emitted finished mit error.
        """
        controller._active_operation = FeatureOperationType.EXTRUDE
        mock_mw._confirm_extrude_impl = MagicMock(side_effect=RuntimeError("Test Error"))
        
        signals = []
        controller.operation_finished.connect(
            lambda s, m, r: signals.append((s, m))
        )
        
        result = controller.confirm_extrude({'height': 10.0})
        
        assert result is False
        assert len(signals) == 1
        assert signals[0][0] is False
        assert "Test Error" in signals[0][1]
        
    def test_fallback_status_message_on_start(self, controller, mock_mw):
        """
        C-W17-R39: Fallback zeigt Status-Nachricht wenn keine MainWindow Impl.
        """
        controller.start_extrude()
        
        mock_mw.statusBar().showMessage.assert_called_once()
        
    def test_confirm_revolve_with_active_revolve(self, controller, mock_mw):
        """
        C-W17-R40: confirm_revolve mit aktiver REVOLVE Operation.
        """
        controller._active_operation = FeatureOperationType.REVOLVE
        mock_mw._confirm_revolve_impl = MagicMock(return_value="result")
        
        signals = []
        controller.operation_finished.connect(
            lambda s, m, r: signals.append((s, m))
        )
        
        result = controller.confirm_revolve({'angle': 360, 'axis': 'Z'})
        
        assert result is True
        assert len(signals) == 1
        assert signals[0][0] is True


class TestFeatureControllerStateTransitions:
    """W17 Paket C: FeatureController State Machine Tests."""
    
    @pytest.fixture
    def controller(self):
        """Fresh controller for state tests."""
        return FeatureController(MockMainWindow())
        
    def test_extrude_state_transition(self, controller):
        """
        C-W17-R41: Extrude State Machine: None -> EXTRUDE -> None.
        """
        # Initial: None
        assert controller.get_active_operation() is None
        
        # Start: EXTRUDE
        controller.start_extrude()
        assert controller.get_active_operation() == FeatureOperationType.EXTRUDE
        
        # Cancel: None
        controller.cancel_extrude()
        assert controller.get_active_operation() is None
        
    def test_multiple_starts_overwrite(self, controller):
        """
        C-W17-R42: Mehrere start_* überschreiben aktive Operation.
        """
        controller.start_extrude()
        assert controller.get_active_operation() == FeatureOperationType.EXTRUDE
        
        controller.start_revolve()
        assert controller.get_active_operation() == FeatureOperationType.REVOLVE
        
        controller.start_fillet()
        assert controller.get_active_operation() == FeatureOperationType.FILLET
        
    def test_confirm_clears_active(self, controller):
        """
        C-W17-R43: confirm_* löscht aktive Operation.
        """
        # Mock MainWindow mit confirm_impl
        controller._mw._confirm_extrude_impl = MagicMock(return_value="result")
        controller._active_operation = FeatureOperationType.EXTRUDE
        
        controller.confirm_extrude({'height': 10.0})
        
        assert controller.get_active_operation() is None


# Pytest fixture für QApplication
@pytest.fixture(scope="session")
def qt_app():
    """Session-weite QApplication Instanz."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app
