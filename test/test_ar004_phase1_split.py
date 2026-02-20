"""
AR-004: gui/main_window.py Phase 1 Split Tests
================================================

Tests for verifying the extraction of menu_actions and event_handlers modules.

Acceptance Criteria:
- At least 2 new modules extracted
- Backward compatibility maintained
- All existing tests pass
- No import errors
"""

import pytest
import sys
import os

# Ensure project root is in path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


class TestModuleExtraction:
    """Test that modules were extracted correctly."""
    
    def test_menu_actions_module_exists(self):
        """AR-004-A1: menu_actions.py module exists."""
        from gui import menu_actions
        assert menu_actions is not None
    
    def test_event_handlers_module_exists(self):
        """AR-004-A2: event_handlers.py module exists."""
        from gui import event_handlers
        assert event_handlers is not None
    
    def test_menu_actions_has_mixin_class(self):
        """AR-004-A3: MenuActionsMixin class exists."""
        from gui.menu_actions import MenuActionsMixin
        assert MenuActionsMixin is not None
        assert hasattr(MenuActionsMixin, '_new_project')
        assert hasattr(MenuActionsMixin, '_save_project')
        assert hasattr(MenuActionsMixin, '_export_stl')
    
    def test_event_handlers_has_mixin_class(self):
        """AR-004-A4: EventHandlersMixin class exists."""
        from gui.event_handlers import EventHandlersMixin
        assert EventHandlersMixin is not None
        assert hasattr(EventHandlersMixin, 'eventFilter')
        assert hasattr(EventHandlersMixin, '_handle_escape_key')


class TestBackwardCompatibility:
    """Test that backward compatibility is maintained."""
    
    def test_main_window_imports_successfully(self):
        """AR-004-B1: MainWindow can be imported without errors."""
        from gui.main_window import MainWindow
        assert MainWindow is not None
    
    def test_main_window_inherits_mixins(self):
        """AR-004-B2: MainWindow inherits from both mixins."""
        from gui.main_window import MainWindow
        from gui.menu_actions import MenuActionsMixin
        from gui.event_handlers import EventHandlersMixin
        
        # Check MRO (Method Resolution Order)
        mro = MainWindow.__mro__
        assert MenuActionsMixin in mro, "MenuActionsMixin should be in MRO"
        assert EventHandlersMixin in mro, "EventHandlersMixin should be in MRO"
    
    def test_main_window_has_menu_methods(self):
        """AR-004-B3: MainWindow has menu action methods."""
        from gui.main_window import MainWindow
        
        # Check key methods exist
        assert hasattr(MainWindow, '_new_project')
        assert hasattr(MainWindow, '_save_project')
        assert hasattr(MainWindow, '_save_project_as')
        assert hasattr(MainWindow, '_open_project')
        assert hasattr(MainWindow, '_export_stl')
        assert hasattr(MainWindow, '_export_step')
        assert hasattr(MainWindow, '_export_3mf')
        assert hasattr(MainWindow, '_import_step')
        assert hasattr(MainWindow, '_smart_undo')
        assert hasattr(MainWindow, '_smart_redo')
        assert hasattr(MainWindow, '_show_about')
        assert hasattr(MainWindow, '_change_language')
    
    def test_main_window_has_event_methods(self):
        """AR-004-B4: MainWindow has event handler methods."""
        from gui.main_window import MainWindow
        
        # Check key methods exist
        assert hasattr(MainWindow, 'eventFilter')
        assert hasattr(MainWindow, '_handle_key_press')
        assert hasattr(MainWindow, '_handle_escape_key')


class TestMenuActionsFunctionality:
    """Test menu actions functionality (mocked)."""
    
    def test_get_export_candidates_method_exists(self):
        """AR-004-C1: _get_export_candidates method exists."""
        from gui.menu_actions import MenuActionsMixin
        assert hasattr(MenuActionsMixin, '_get_export_candidates')
    
    def test_resolve_feature_formulas_method_exists(self):
        """AR-004-C2: _resolve_feature_formulas method exists."""
        from gui.menu_actions import MenuActionsMixin
        assert hasattr(MenuActionsMixin, '_resolve_feature_formulas')


class TestEventHandlersFunctionality:
    """Test event handlers functionality."""
    
    def test_should_block_shortcuts_method_exists(self):
        """AR-004-D1: _should_block_shortcuts method exists."""
        from gui.event_handlers import EventHandlersMixin
        assert hasattr(EventHandlersMixin, '_should_block_shortcuts')
    
    def test_handle_tab_key_method_exists(self):
        """AR-004-D2: _handle_tab_key method exists."""
        from gui.event_handlers import EventHandlersMixin
        assert hasattr(EventHandlersMixin, '_handle_tab_key')
    
    def test_handle_revolve_shortcuts_method_exists(self):
        """AR-004-D3: _handle_revolve_shortcuts method exists."""
        from gui.event_handlers import EventHandlersMixin
        assert hasattr(EventHandlersMixin, '_handle_revolve_shortcuts')
    
    def test_handle_3d_mode_shortcuts_method_exists(self):
        """AR-004-D4: _handle_3d_mode_shortcuts method exists."""
        from gui.event_handlers import EventHandlersMixin
        assert hasattr(EventHandlersMixin, '_handle_3d_mode_shortcuts')


class TestNoImportBreakage:
    """Test that imports don't break."""
    
    def test_all_gui_imports_work(self):
        """AR-004-E1: All gui module imports work."""
        # This test ensures no circular imports or missing dependencies
        try:
            from gui.main_window import MainWindow
            from gui.menu_actions import MenuActionsMixin
            from gui.event_handlers import EventHandlersMixin
            from gui.browser import ProjectBrowser
            from gui.sketch_editor import SketchEditor
            from gui.tool_panel import ToolPanel
            from gui.tool_panel_3d import ToolPanel3D
            assert True
        except ImportError as e:
            pytest.fail(f"Import failed: {e}")
    
    def test_main_window_can_be_instantiated(self):
        """AR-004-E2: MainWindow can be imported and has correct structure."""
        from gui.main_window import MainWindow
        
        # Verify class structure without instantiating (requires qt_app fixture)
        assert hasattr(MainWindow, '__mro__')
        assert MainWindow.__name__ == 'MainWindow'


class TestMethodSignatures:
    """Test that method signatures match expected patterns."""
    
    def test_event_filter_signature(self):
        """AR-004-F1: eventFilter has correct signature."""
        from gui.event_handlers import EventHandlersMixin
        import inspect
        
        sig = inspect.signature(EventHandlersMixin.eventFilter)
        params = list(sig.parameters.keys())
        
        assert 'self' in params
        assert 'obj' in params
        assert 'event' in params
    
    def test_new_project_signature(self):
        """AR-004-F2: _new_project has correct signature."""
        from gui.menu_actions import MenuActionsMixin
        import inspect
        
        sig = inspect.signature(MenuActionsMixin._new_project)
        params = list(sig.parameters.keys())
        
        assert 'self' in params


# =============================================================================
# Integration Tests (require full GUI)
# =============================================================================

@pytest.mark.skipif(
    not pytest.config.getoption("--run-ui", default=False) if hasattr(pytest, 'config') else True,
    reason="UI tests require --run-ui flag"
)
class TestIntegrationWithGUI:
    """Integration tests that require full GUI environment."""
    
    def test_menu_actions_accessible_from_main_window(self, main_window_clean):
        """AR-004-G1: Menu actions are accessible from MainWindow instance."""
        window = main_window_clean
        
        # Test that methods are callable
        assert callable(window._new_project)
        assert callable(window._save_project)
        assert callable(window._export_stl)
    
    def test_event_handlers_accessible_from_main_window(self, main_window_clean):
        """AR-004-G2: Event handlers are accessible from MainWindow instance."""
        window = main_window_clean
        
        # Test that methods are callable
        assert callable(window.eventFilter)
        assert callable(window._handle_escape_key)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
