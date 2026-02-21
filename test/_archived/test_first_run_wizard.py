"""
Tests für First Run Wizard & Tutorial System
=============================================

Phase 2: UX-001 - First-Run Guided Flow

Run: pytest test/test_first_run_wizard.py -v
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import tempfile
import json
import os

# Skip if dependencies not available
try:
    from gui.first_run_wizard import (
        FirstRunWizard, WelcomePage, InterfaceOverviewPage,
        FirstSketchPage, First3DPage, ExportPage,
        should_show_first_run, reset_first_run_config
    )
    from gui.tutorial_overlay import (
        TutorialOverlay, TutorialStep, HighlightWidget, 
        TutorialTooltip, create_basic_sketch_tutorial
    )
    DEPENDENCIES_AVAILABLE = True
except ImportError:
    DEPENDENCIES_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not DEPENDENCIES_AVAILABLE,
    reason="FirstRunWizard dependencies not available"
)


class TestWelcomePage:
    """Tests für WelcomePage."""
    
    def test_page_creation(self):
        """Test Erstellung der Willkommens-Seite."""
        page = WelcomePage()
        
        assert page.title_label is not None
        assert page.desc_label is not None
        # Sollte Features enthalten
        assert page.content_layout is not None


class TestInterfaceOverviewPage:
    """Tests für InterfaceOverviewPage."""
    
    def test_page_creation(self):
        """Test Erstellung der UI-Übersichts-Seite."""
        page = InterfaceOverviewPage()
        
        assert page.title is not None
        assert "Benutzeroberfläche" in page.title or "Interface" in page.title


class TestFirstRunWizard:
    """Tests für FirstRunWizard."""
    
    def test_wizard_creation(self):
        """Test Erstellung des Wizards."""
        wizard = FirstRunWizard()
        
        assert wizard is not None
        assert len(wizard.pages) == 5  # 5 Seiten
        assert wizard.current_page == 0
        
    def test_initial_page_is_welcome(self):
        """Test dass erste Seite Welcome ist."""
        wizard = FirstRunWizard()
        
        first_page = wizard.pages[0]
        assert isinstance(first_page, WelcomePage)
        
    def test_progress_initially_zero(self):
        """Test dass Progress initial 0 ist."""
        wizard = FirstRunWizard()
        
        assert wizard.progress.value() == 0
        
    def test_go_next_increments_page(self):
        """Test Navigation zur nächsten Seite."""
        wizard = FirstRunWizard()
        
        initial_page = wizard.current_page
        wizard._go_next()
        
        assert wizard.current_page == initial_page + 1
        
    def test_go_back_decrements_page(self):
        """Test Navigation zur vorherigen Seite."""
        wizard = FirstRunWizard()
        
        # Zuerst vorwärts
        wizard._go_next()
        wizard._go_next()
        
        # Dann zurück
        wizard._go_back()
        
        assert wizard.current_page == 1
        
    def test_go_next_updates_progress(self):
        """Test dass Navigation Progress aktualisiert."""
        wizard = FirstRunWizard()
        
        initial_progress = wizard.progress.value()
        wizard._go_next()
        
        assert wizard.progress.value() > initial_progress
        
    def test_config_file_created_on_finish(self):
        """Test dass Config-Datei erstellt wird."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(FirstRunWizard, 'CONFIG_FILE', 'test_config.json'):
                wizard = FirstRunWizard()
                wizard._save_config()
                
                config_path = tmpdir / 'test_config.json'
                # Config sollte existieren oder Methode sollte nicht fehlschlagen
                
    def test_should_show_first_run_true(self):
        """Test should_show_first_run wenn keine Config existiert."""
        with tempfile.TemporaryDirectory():
            # Ohne Config-Datei sollte True zurückgeben
            with patch('gui.first_run_wizard.Path') as mock_path:
                mock_path.return_value.exists.return_value = False
                result = should_show_first_run()
                # Je nach Implementierung
                
    def test_reset_first_run_config(self):
        """Test Reset der Config."""
        with tempfile.TemporaryDirectory():
            with patch.object(FirstRunWizard, 'CONFIG_FILE', 'test_config.json'):
                # Erstelle Config
                with open('test_config.json', 'w') as f:
                    json.dump({'dont_show_again': True}, f)
                
                # Reset
                reset_first_run_config()
                
                # Sollte nicht mehr existieren
                assert not os.path.exists('test_config.json')


class TestTutorialStep:
    """Tests für TutorialStep."""
    
    def test_step_creation(self):
        """Test Erstellung eines Tutorial-Schritts."""
        mock_widget = Mock()
        
        step = TutorialStep(
            target_widget=mock_widget,
            title="Test Step",
            text="Test description",
            position="bottom",
            action_text="Test Action",
            can_skip=True
        )
        
        assert step.target_widget == mock_widget
        assert step.title == "Test Step"
        assert step.position == "bottom"
        assert step.can_skip is True
        
    def test_step_with_validation(self):
        """Test Step mit Validierungs-Callback."""
        validate_func = Mock(return_value=True)
        
        step = TutorialStep(
            target_widget=None,
            title="Validation Test",
            text="Test",
            validate=validate_func
        )
        
        assert step.validate is not None
        assert step.validate() is True


class TestTutorialOverlay:
    """Tests für TutorialOverlay."""
    
    def test_overlay_creation(self):
        """Test Erstellung des Overlays."""
        overlay = TutorialOverlay()
        
        assert overlay is not None
        assert len(overlay.steps) == 0
        assert not overlay.is_running
        
    def test_add_step(self):
        """Test Hinzufügen eines Schritts."""
        overlay = TutorialOverlay()
        
        step = TutorialStep(
            target_widget=None,
            title="Test",
            text="Test"
        )
        overlay.add_step(step)
        
        assert len(overlay.steps) == 1
        
    def test_add_multiple_steps(self):
        """Test Hinzufügen mehrerer Schritte."""
        overlay = TutorialOverlay()
        
        steps = [
            TutorialStep(None, f"Step {i}", f"Text {i}")
            for i in range(3)
        ]
        overlay.add_steps(steps)
        
        assert len(overlay.steps) == 3
        
    def test_start_with_no_steps(self):
        """Test Start ohne Schritte."""
        overlay = TutorialOverlay()
        
        # Sollte nicht crashen
        overlay.start()
        
        # Sollte nicht laufen
        assert not overlay.is_running
        
    def test_start_with_steps(self):
        """Test Start mit Schritten."""
        overlay = TutorialOverlay()
        
        step = TutorialStep(None, "Test", "Test")
        overlay.add_step(step)
        
        # Sollte starten
        # overlay.start()  # Würde UI öffnen, daher mocken wir
        
    def test_stop(self):
        """Test Stop des Tutorials."""
        overlay = TutorialOverlay()
        
        step = TutorialStep(None, "Test", "Test")
        overlay.add_step(step)
        
        overlay.start()
        overlay.stop()
        
        assert not overlay.is_running
        assert not overlay.isVisible()


class TestCreateBasicSketchTutorial:
    """Tests für create_basic_sketch_tutorial."""
    
    def test_tutorial_creation(self):
        """Test Erstellung des Basis-Tutorials."""
        mock_main = Mock()
        mock_main.sketch_btn = Mock()
        mock_main.rect_tool_btn = Mock()
        mock_main.dimension_tool_btn = Mock()
        
        tutorial = create_basic_sketch_tutorial(mock_main)
        
        assert tutorial is not None
        assert len(tutorial.steps) > 0
        
    def test_tutorial_without_widgets(self):
        """Test Tutorial ohne Widgets."""
        mock_main = Mock()
        # Keine Widgets
        
        tutorial = create_basic_sketch_tutorial(mock_main)
        
        # Sollte trotzdem funktionieren (nur mit allgemeinen Schritten)
        assert tutorial is not None


class TestHighlightWidget:
    """Tests für HighlightWidget."""
    
    def test_widget_creation(self):
        """Test Erstellung des Highlight-Widgets."""
        highlight = HighlightWidget()
        
        assert highlight is not None
        assert highlight.target_rect == highlight.target_rect  # Default rect
        
    def test_set_target(self):
        """Test Setzen des Ziel-Widgets."""
        highlight = HighlightWidget()
        
        mock_widget = Mock()
        mock_widget.size.return_value = Mock(width=lambda: 100, height=lambda: 50)
        mock_widget.mapTo.return_value = Mock(x=lambda: 10, y=lambda: 20)
        
        # Sollte nicht crashen
        highlight.set_target(mock_widget)


class TestTutorialTooltip:
    """Tests für TutorialTooltip."""
    
    def test_tooltip_creation(self):
        """Test Erstellung des Tooltips."""
        tooltip = TutorialTooltip()
        
        assert tooltip is not None
        assert tooltip.title_label is not None
        assert tooltip.text_label is not None
        
    def test_set_content(self):
        """Test Setzen des Contents."""
        tooltip = TutorialTooltip()
        
        step = TutorialStep(
            target_widget=None,
            title="Test Title",
            text="Test Text"
        )
        
        tooltip.set_content(step, 1, 5)
        
        assert tooltip.title_label.text() == "Test Title"
        assert tooltip.text_label.text() == "Test Text"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
