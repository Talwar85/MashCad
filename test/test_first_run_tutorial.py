"""
Tests for UX-001: First-Run Guided Flow

Tests:
- TutorialStepData creation and validation
- TutorialManager step progression
- Completion detection
- Settings persistence
- FirstRunWizard integration

Author: Kimi (UX-001 Implementation)
Date: 2026-02-20
Branch: feature/v1-roadmap-execution
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from PySide6.QtCore import QSettings, QRect, QCoreApplication
from PySide6.QtWidgets import QWidget, QApplication

from gui.tutorial_manager import (
    TutorialStepData,
    TutorialManager,
    create_tutorial_steps,
    get_tutorial_manager,
    reset_tutorial_manager,
)
from gui.first_run_wizard import FirstRunWizard, should_show_first_run, reset_first_run_config
from config.feature_flags import is_enabled, set_flag


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication fixture."""
    app = QCoreApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestTutorialStepData:
    """Tests für TutorialStepData."""
    
    def test_create_step_with_required_fields(self):
        """Test: Schritt mit Pflichtfeldern erstellen."""
        step = TutorialStepData(
            step_id="test_step",
            title="Test Step",
            description="Test description"
        )
        
        assert step.step_id == "test_step"
        assert step.title == "Test Step"
        assert step.description == "Test description"
        assert step.target_area is None
        assert step.action_required == ""
        assert step.action_check is None
        assert step.hints == []
        assert step.auto_advance is False
    
    def test_create_step_with_all_fields(self):
        """Test: Schritt mit allen Feldern erstellen."""
        check_fn = lambda: True
        step = TutorialStepData(
            step_id="full_step",
            title="Full Step",
            description="Full description",
            target_area=QRect(0, 0, 100, 100),
            action_required="Do something",
            action_check=check_fn,
            hints=["Hint1", "Hint2"],
            auto_advance=True
        )
        
        assert step.step_id == "full_step"
        assert step.target_area == QRect(0, 0, 100, 100)
        assert step.action_required == "Do something"
        assert step.action_check == check_fn
        assert len(step.hints) == 2
        assert step.auto_advance is True
    
    def test_is_completed_no_check(self):
        """Test: is_completed gibt False wenn kein Check definiert."""
        step = TutorialStepData(
            step_id="no_check",
            title="No Check",
            description="No check function"
        )
        
        assert step.is_completed() is False
    
    def test_is_completed_with_check_true(self):
        """Test: is_completed gibt True wenn Check True zurückgibt."""
        step = TutorialStepData(
            step_id="check_true",
            title="Check True",
            description="Check returns true",
            action_check=lambda: True
        )
        
        assert step.is_completed() is True
    
    def test_is_completed_with_check_false(self):
        """Test: is_completed gibt False wenn Check False zurückgibt."""
        step = TutorialStepData(
            step_id="check_false",
            title="Check False",
            description="Check returns false",
            action_check=lambda: False
        )
        
        assert step.is_completed() is False
    
    def test_is_completed_exception_handling(self):
        """Test: is_completed gibt False bei Exception."""
        def failing_check():
            raise RuntimeError("Check failed")
        
        step = TutorialStepData(
            step_id="failing_check",
            title="Failing Check",
            description="Check throws exception",
            action_check=failing_check
        )
        
        assert step.is_completed() is False


class TestCreateTutorialSteps:
    """Tests für create_tutorial_steps."""
    
    def test_creates_5_steps(self):
        """Test: Genau 5 Schritte werden erstellt."""
        mock_main_window = Mock()
        steps = create_tutorial_steps(mock_main_window)
        
        assert len(steps) == 5
    
    def test_step_ids_are_unique(self):
        """Test: Alle Schritt-IDs sind eindeutig."""
        mock_main_window = Mock()
        steps = create_tutorial_steps(mock_main_window)
        
        step_ids = [step.step_id for step in steps]
        assert len(step_ids) == len(set(step_ids))
    
    def test_step_order(self):
        """Test: Schritte sind in der richtigen Reihenfolge."""
        mock_main_window = Mock()
        steps = create_tutorial_steps(mock_main_window)
        
        expected_order = ["welcome", "sketch_basics", "extrude", "modify_fillet", "export"]
        actual_order = [step.step_id for step in steps]
        
        assert actual_order == expected_order
    
    def test_all_steps_have_required_fields(self):
        """Test: Alle Schritte haben Pflichtfelder."""
        mock_main_window = Mock()
        steps = create_tutorial_steps(mock_main_window)
        
        for step in steps:
            assert step.step_id, f"Step missing step_id"
            assert step.title, f"Step {step.step_id} missing title"
            assert step.description, f"Step {step.step_id} missing description"
            assert step.action_required, f"Step {step.step_id} missing action_required"


class TestTutorialManager:
    """Tests für TutorialManager."""
    
    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        """Setup für jeden Test."""
        reset_tutorial_manager()
        # Clear any saved settings
        settings = QSettings("MashCAD", "Tutorial")
        settings.remove("tutorial_progress")
        settings.remove("tutorial_completed")
        settings.sync()
        
        yield
        
        reset_tutorial_manager()
    
    def test_initialization(self):
        """Test: TutorialManager initialisiert korrekt."""
        manager = TutorialManager()
        
        assert manager.current_step_index == 0
        assert manager.total_steps == 0
        assert manager.is_active is False
        assert manager.current_step is None
    
    def test_initialize_creates_steps(self):
        """Test: initialize() erstellt Schritte."""
        mock_main_window = Mock()
        manager = TutorialManager(mock_main_window)
        manager.initialize()
        
        assert manager.total_steps == 5
        assert manager.current_step is not None
    
    def test_start_tutorial(self):
        """Test: start_tutorial() startet das Tutorial."""
        manager = TutorialManager()
        manager.initialize()
        
        manager.start_tutorial()
        
        assert manager.is_active is True
        assert manager.current_step_index == 0
    
    def test_next_step_advances(self):
        """Test: next_step() rückt vor."""
        manager = TutorialManager()
        manager.initialize()
        manager.start_tutorial()
        
        result = manager.next_step()
        
        assert result is True
        assert manager.current_step_index == 1
    
    def test_next_step_at_end_completes(self):
        """Test: next_step() am Ende schließt Tutorial ab."""
        manager = TutorialManager()
        manager.initialize()
        manager.start_tutorial()
        
        # Gehe zum letzten Schritt
        for _ in range(4):
            manager.next_step()
        
        # Am Ende sollte False zurückgegeben werden
        result = manager.next_step()
        
        assert result is False
        assert manager.is_active is False
    
    def test_previous_step_goes_back(self):
        """Test: previous_step() geht zurück."""
        manager = TutorialManager()
        manager.initialize()
        manager.start_tutorial()
        manager.next_step()
        
        result = manager.previous_step()
        
        assert result is True
        assert manager.current_step_index == 0
    
    def test_previous_step_at_start(self):
        """Test: previous_step() am Anfang gibt False zurück."""
        manager = TutorialManager()
        manager.initialize()
        manager.start_tutorial()
        
        result = manager.previous_step()
        
        assert result is False
        assert manager.current_step_index == 0
    
    def test_go_to_step_by_id(self):
        """Test: go_to_step() springt zu Schritt."""
        manager = TutorialManager()
        manager.initialize()
        manager.start_tutorial()
        
        result = manager.go_to_step("extrude")
        
        assert result is True
        assert manager.current_step.step_id == "extrude"
    
    def test_go_to_step_invalid_id(self):
        """Test: go_to_step() mit ungültiger ID gibt False zurück."""
        manager = TutorialManager()
        manager.initialize()
        manager.start_tutorial()
        
        result = manager.go_to_step("invalid_step")
        
        assert result is False
    
    def test_get_progress(self):
        """Test: get_progress() gibt korrekten Prozentwert zurück."""
        manager = TutorialManager()
        manager.initialize()
        
        # Schritt 0 von 5 = 20%
        manager.start_tutorial()
        assert manager.get_progress() == 20
        
        # Schritt 1 von 5 = 40%
        manager.next_step()
        assert manager.get_progress() == 40
        
        # Schritt 4 von 5 = 100%
        manager.next_step()
        manager.next_step()
        manager.next_step()
        manager.next_step()
        assert manager.get_progress() == 100
    
    def test_complete_tutorial(self):
        """Test: complete_tutorial() markiert als abgeschlossen."""
        manager = TutorialManager()
        manager.initialize()
        manager.start_tutorial()
        
        manager.complete_tutorial()
        
        assert manager.is_completed() is True
        assert manager.is_active is False
    
    def test_skip_tutorial(self):
        """Test: skip_tutorial() speichert Fortschritt."""
        manager = TutorialManager()
        manager.initialize()
        manager.start_tutorial()
        manager.next_step()
        
        manager.skip_tutorial()
        
        assert manager.is_active is False
        assert manager.current_step_index == 1  # Progress saved
    
    def test_reset_tutorial(self):
        """Test: reset_tutorial() setzt alles zurück."""
        manager = TutorialManager()
        manager.initialize()
        manager.start_tutorial()
        manager.complete_tutorial()
        
        manager.reset_tutorial()
        
        assert manager.current_step_index == 0
        assert manager.is_active is False
        assert manager.is_completed() is False
    
    def test_progress_signal_emitted(self):
        """Test: progress_updated Signal wird gesendet."""
        manager = TutorialManager()
        manager.initialize()
        
        with patch.object(manager, 'progress_updated') as mock_signal:
            manager.progress_updated = Mock()
            manager.start_tutorial()
            
            manager.progress_updated.emit.assert_called()
    
    def test_step_changed_signal_emitted(self):
        """Test: step_changed Signal wird gesendet."""
        manager = TutorialManager()
        manager.initialize()
        
        with patch.object(manager, 'step_changed') as mock_signal:
            manager.step_changed = Mock()
            manager.start_tutorial()
            
            manager.step_changed.emit.assert_called_with(0)


class TestTutorialManagerPersistence:
    """Tests für TutorialManager Persistenz."""
    
    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        """Setup für jeden Test."""
        reset_tutorial_manager()
        settings = QSettings("MashCAD", "Tutorial")
        settings.clear()
        settings.sync()
        
        yield
        
        reset_tutorial_manager()
        settings = QSettings("MashCAD", "Tutorial")
        settings.clear()
        settings.sync()
    
    def test_progress_saved_on_next_step(self):
        """Test: Fortschritt wird bei next_step gespeichert."""
        manager = TutorialManager()
        manager.initialize()
        manager.start_tutorial()
        manager.next_step()
        
        # Neuer Manager sollte den gespeicherten Fortschritt laden
        reset_tutorial_manager()
        new_manager = TutorialManager()
        
        assert new_manager.current_step_index == 1
    
    def test_completion_persisted(self):
        """Test: Abschluss wird persistiert."""
        manager = TutorialManager()
        manager.initialize()
        manager.start_tutorial()
        manager.complete_tutorial()
        
        # Neuer Manager sollte als abgeschlossen geladen werden
        reset_tutorial_manager()
        new_manager = TutorialManager()
        
        assert new_manager.is_completed() is True


class TestTutorialManagerSingleton:
    """Tests für Singleton-Pattern."""
    
    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        """Setup für jeden Test."""
        reset_tutorial_manager()
        yield
        reset_tutorial_manager()
    
    def test_get_tutorial_manager_returns_singleton(self):
        """Test: get_tutorial_manager gibt Singleton zurück."""
        manager1 = get_tutorial_manager()
        manager2 = get_tutorial_manager()
        
        assert manager1 is manager2
    
    def test_reset_tutorial_manager_clears_singleton(self):
        """Test: reset_tutorial_manager löscht Singleton."""
        manager1 = get_tutorial_manager()
        reset_tutorial_manager()
        manager2 = get_tutorial_manager()
        
        assert manager1 is not manager2


class TestFirstRunWizardIntegration:
    """Tests für FirstRunWizard Integration."""
    
    @pytest.fixture(autouse=True)
    def setup(self, qapp, tmp_path):
        """Setup für jeden Test."""
        # Reset first-run config
        reset_first_run_config()
        reset_tutorial_manager()
        
        # Clear settings
        settings = QSettings("MashCAD", "Tutorial")
        settings.clear()
        settings.sync()
        
        yield
        
        reset_first_run_config()
        reset_tutorial_manager()
    
    def test_feature_flag_enabled(self):
        """Test: first_run_tutorial Feature Flag ist aktiviert."""
        assert is_enabled("first_run_tutorial") is True
    
    def test_wizard_has_tutorial_button(self, qapp):
        """Test: Wizard hat Tutorial-Button auf der letzten Seite."""
        wizard = FirstRunWizard()
        
        assert hasattr(wizard, 'tutorial_btn')
        assert wizard.tutorial_btn is not None
    
    def test_wizard_tutorial_button_visible_on_last_page(self, qapp):
        """Test: Tutorial-Button ist auf der letzten Seite sichtbar."""
        wizard = FirstRunWizard()
        wizard.show()
        
        # Gehe zur letzten Seite
        for _ in range(len(wizard.pages) - 1):
            wizard._go_next()
        
        # Prüfe ob der Button nicht explizit versteckt ist
        assert not wizard.tutorial_btn.isHidden()
    
    def test_wizard_tutorial_button_hidden_on_first_page(self, qapp):
        """Test: Tutorial-Button ist auf der ersten Seite versteckt."""
        wizard = FirstRunWizard()
        
        assert not wizard.tutorial_btn.isVisible()
    
    def test_tutorial_button_sets_flag(self, qapp):
        """Test: Tutorial-Button setzt das Flag."""
        wizard = FirstRunWizard()
        
        # Gehe zur letzten Seite
        for _ in range(len(wizard.pages) - 1):
            wizard._go_next()
        
        wizard._start_tutorial_and_finish()
        
        assert wizard.should_start_tutorial() is True
    
    def test_finish_without_tutorial(self, qapp):
        """Test: Finish ohne Tutorial startet kein Tutorial."""
        wizard = FirstRunWizard()
        
        wizard._finish()
        
        assert wizard.should_start_tutorial() is False


class TestFirstRunWizardPersistence:
    """Tests für FirstRunWizard Persistenz."""
    
    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        """Setup für jeden Test."""
        reset_first_run_config()
        yield
        reset_first_run_config()
    
    def test_should_show_first_run_default(self):
        """Test: should_show_first_run gibt True zurück wenn keine Config existiert."""
        reset_first_run_config()
        
        assert should_show_first_run() is True
    
    def test_dont_show_again_persisted(self, qapp):
        """Test: 'Nicht mehr anzeigen' wird persistiert."""
        wizard = FirstRunWizard()
        wizard.skip_checkbox.setChecked(True)
        wizard._save_config()
        
        assert should_show_first_run() is False
    
    def test_reset_first_run_config(self, qapp):
        """Test: reset_first_run_config löscht Config."""
        wizard = FirstRunWizard()
        wizard.skip_checkbox.setChecked(True)
        wizard._save_config()
        
        reset_first_run_config()
        
        assert should_show_first_run() is True


class TestTutorialStepHighlighting:
    """Tests für Tutorial Schritt-Highlighting."""
    
    def test_step_with_target_area(self):
        """Test: Schritt kann Zielbereich haben."""
        rect = QRect(10, 20, 100, 50)
        step = TutorialStepData(
            step_id="highlight_step",
            title="Highlight Step",
            description="Step with target area",
            target_area=rect
        )
        
        assert step.target_area == rect
        assert step.target_area.x() == 10
        assert step.target_area.y() == 20
        assert step.target_area.width() == 100
        assert step.target_area.height() == 50
    
    def test_step_without_target_area(self):
        """Test: Schritt ohne Zielbereich hat None."""
        step = TutorialStepData(
            step_id="no_highlight",
            title="No Highlight",
            description="Step without target area"
        )
        
        assert step.target_area is None


class TestAutoAdvance:
    """Tests für Auto-Advance Feature."""
    
    @pytest.fixture(autouse=True)
    def setup(self, qapp):
        """Setup für jeden Test."""
        reset_tutorial_manager()
        settings = QSettings("MashCAD", "Tutorial")
        settings.clear()
        settings.sync()
        yield
        reset_tutorial_manager()
    
    def test_auto_advance_step(self):
        """Test: Schritt mit auto_advance=True kann automatisch weitergehen."""
        completed = False
        
        def check_completed():
            return completed
        
        step = TutorialStepData(
            step_id="auto_step",
            title="Auto Step",
            description="Auto-advancing step",
            action_check=check_completed,
            auto_advance=True
        )
        
        assert step.auto_advance is True
        assert step.is_completed() is False
        
        completed = True
        assert step.is_completed() is True
    
    def test_manual_step_does_not_auto_advance(self):
        """Test: Schritt ohne auto_advance geht nicht automatisch weiter."""
        step = TutorialStepData(
            step_id="manual_step",
            title="Manual Step",
            description="Manual step",
            action_check=lambda: True,
            auto_advance=False
        )
        
        assert step.auto_advance is False
        assert step.is_completed() is True  # Check returns True


# Run tests with: pytest test/test_first_run_tutorial.py -v
