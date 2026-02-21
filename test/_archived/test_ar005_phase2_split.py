"""
Test AR-005 Phase 2 Split
=========================

Tests for the extracted mixin modules from main_window.py:
- SketchMixin (gui/sketch_operations.py)
- FeatureMixin (gui/feature_operations.py)
- ViewportMixin (gui/viewport_operations.py)
- ToolMixin (gui/tool_operations.py)

Minimum 20 test cases covering:
- Mixin instantiation
- Method signature compatibility
- MainWindow integration
"""

import pytest
import sys
import os
from unittest.mock import Mock, MagicMock, patch, PropertyMock

# Add project root to path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


# =============================================================================
# Test Mixin Imports
# =============================================================================

class TestMixinImports:
    """Test that all mixins can be imported correctly."""
    
    def test_import_sketch_mixin(self):
        """Test SketchMixin can be imported."""
        from gui.sketch_operations import SketchMixin
        assert SketchMixin is not None
    
    def test_import_feature_mixin(self):
        """Test FeatureMixin can be imported."""
        from gui.feature_operations import FeatureMixin
        assert FeatureMixin is not None
    
    def test_import_viewport_mixin(self):
        """Test ViewportMixin can be imported."""
        from gui.viewport_operations import ViewportMixin
        assert ViewportMixin is not None
    
    def test_import_tool_mixin(self):
        """Test ToolMixin can be imported."""
        from gui.tool_operations import ToolMixin
        assert ToolMixin is not None


# =============================================================================
# Test SketchMixin
# =============================================================================

class TestSketchMixin:
    """Test SketchMixin methods and signatures."""
    
    def test_sketch_mixin_has_new_sketch(self):
        """Test SketchMixin has _new_sketch method."""
        from gui.sketch_operations import SketchMixin
        assert hasattr(SketchMixin, '_new_sketch')
        assert callable(getattr(SketchMixin, '_new_sketch'))
    
    def test_sketch_mixin_has_create_sketch_at(self):
        """Test SketchMixin has _create_sketch_at method."""
        from gui.sketch_operations import SketchMixin
        assert hasattr(SketchMixin, '_create_sketch_at')
        assert callable(getattr(SketchMixin, '_create_sketch_at'))
    
    def test_sketch_mixin_has_finish_sketch(self):
        """Test SketchMixin has _finish_sketch method."""
        from gui.sketch_operations import SketchMixin
        assert hasattr(SketchMixin, '_finish_sketch')
        assert callable(getattr(SketchMixin, '_finish_sketch'))
    
    def test_sketch_mixin_has_offset_plane_methods(self):
        """Test SketchMixin has offset plane workflow methods."""
        from gui.sketch_operations import SketchMixin
        assert hasattr(SketchMixin, '_start_offset_plane')
        assert hasattr(SketchMixin, '_on_offset_plane_confirmed')
        assert hasattr(SketchMixin, '_on_offset_plane_cancelled')
    
    def test_sketch_mixin_has_parametric_rebuild_methods(self):
        """Test SketchMixin has parametric rebuild methods."""
        from gui.sketch_operations import SketchMixin
        assert hasattr(SketchMixin, '_schedule_parametric_rebuild')
        assert hasattr(SketchMixin, '_do_parametric_rebuild')
        assert hasattr(SketchMixin, '_update_bodies_depending_on_sketch')


# =============================================================================
# Test FeatureMixin
# =============================================================================

class TestFeatureMixin:
    """Test FeatureMixin methods and signatures."""
    
    def test_feature_mixin_has_extrude_dialog(self):
        """Test FeatureMixin has _extrude_dialog method."""
        from gui.feature_operations import FeatureMixin
        assert hasattr(FeatureMixin, '_extrude_dialog')
        assert callable(getattr(FeatureMixin, '_extrude_dialog'))
    
    def test_feature_mixin_has_extrude_handlers(self):
        """Test FeatureMixin has extrude event handlers."""
        from gui.feature_operations import FeatureMixin
        assert hasattr(FeatureMixin, '_on_extrude_confirmed')
        assert hasattr(FeatureMixin, '_on_extrude_cancelled')
        assert hasattr(FeatureMixin, '_on_extrude_panel_height_changed')
    
    def test_feature_mixin_has_feature_editing(self):
        """Test FeatureMixin has feature editing methods."""
        from gui.feature_operations import FeatureMixin
        assert hasattr(FeatureMixin, '_edit_feature')
        assert hasattr(FeatureMixin, '_edit_transform_feature')
        assert hasattr(FeatureMixin, '_edit_parametric_feature')
    
    def test_feature_mixin_has_detector_update(self):
        """Test FeatureMixin has _update_detector method."""
        from gui.feature_operations import FeatureMixin
        assert hasattr(FeatureMixin, '_update_detector')
        assert callable(getattr(FeatureMixin, '_update_detector'))
    
    def test_feature_mixin_has_rollback(self):
        """Test FeatureMixin has _on_rollback_changed method."""
        from gui.feature_operations import FeatureMixin
        assert hasattr(FeatureMixin, '_on_rollback_changed')
        assert callable(getattr(FeatureMixin, '_on_rollback_changed'))


# =============================================================================
# Test ViewportMixin
# =============================================================================

class TestViewportMixin:
    """Test ViewportMixin methods and signatures."""
    
    def test_viewport_mixin_has_update_methods(self):
        """Test ViewportMixin has viewport update methods."""
        from gui.viewport_operations import ViewportMixin
        assert hasattr(ViewportMixin, '_trigger_viewport_update')
        assert hasattr(ViewportMixin, '_update_viewport_all')
        assert hasattr(ViewportMixin, '_update_viewport_all_impl')
    
    def test_viewport_mixin_has_camera_controls(self):
        """Test ViewportMixin has camera control methods."""
        from gui.viewport_operations import ViewportMixin
        assert hasattr(ViewportMixin, '_reset_view')
        assert hasattr(ViewportMixin, '_set_view_xy')
        assert hasattr(ViewportMixin, '_set_view_xz')
        assert hasattr(ViewportMixin, '_set_view_yz')
        assert hasattr(ViewportMixin, '_zoom_to_fit')
    
    def test_viewport_mixin_has_section_view(self):
        """Test ViewportMixin has section view methods."""
        from gui.viewport_operations import ViewportMixin
        assert hasattr(ViewportMixin, '_toggle_section_view')
        assert hasattr(ViewportMixin, '_on_section_enabled')
        assert hasattr(ViewportMixin, '_on_section_disabled')
    
    def test_viewport_mixin_has_panel_positioning(self):
        """Test ViewportMixin has panel positioning methods."""
        from gui.viewport_operations import ViewportMixin
        assert hasattr(ViewportMixin, '_position_extrude_panel')
        assert hasattr(ViewportMixin, '_position_transform_panel')
        assert hasattr(ViewportMixin, '_reposition_all_panels')
    
    def test_viewport_mixin_has_mode_switching(self):
        """Test ViewportMixin has mode switching methods."""
        from gui.viewport_operations import ViewportMixin
        assert hasattr(ViewportMixin, '_set_mode')
        assert callable(getattr(ViewportMixin, '_set_mode'))


# =============================================================================
# Test ToolMixin
# =============================================================================

class TestToolMixin:
    """Test ToolMixin methods and signatures."""
    
    def test_tool_mixin_has_3d_action_handler(self):
        """Test ToolMixin has _on_3d_action method."""
        from gui.tool_operations import ToolMixin
        assert hasattr(ToolMixin, '_on_3d_action')
        assert callable(getattr(ToolMixin, '_on_3d_action'))
    
    def test_tool_mixin_has_transform_tools(self):
        """Test ToolMixin has transform tool methods."""
        from gui.tool_operations import ToolMixin
        assert hasattr(ToolMixin, '_start_transform_mode')
        assert hasattr(ToolMixin, '_show_transform_ui')
        assert hasattr(ToolMixin, '_hide_transform_ui')
    
    def test_tool_mixin_has_point_to_point(self):
        """Test ToolMixin has point-to-point move methods."""
        from gui.tool_operations import ToolMixin
        assert hasattr(ToolMixin, '_start_point_to_point_move')
        assert hasattr(ToolMixin, '_on_point_to_point_move')
        assert hasattr(ToolMixin, '_reset_point_to_point_move')
    
    def test_tool_mixin_has_measure_tool(self):
        """Test ToolMixin has measure tool methods."""
        from gui.tool_operations import ToolMixin
        assert hasattr(ToolMixin, '_start_measure_mode')
        assert hasattr(ToolMixin, '_on_measure_point_picked')
        assert hasattr(ToolMixin, '_cancel_measure_mode')
    
    def test_tool_mixin_has_feature_tools(self):
        """Test ToolMixin has feature tool methods."""
        from gui.tool_operations import ToolMixin
        assert hasattr(ToolMixin, '_start_fillet')
        assert hasattr(ToolMixin, '_start_chamfer')
        assert hasattr(ToolMixin, '_start_shell')
        assert hasattr(ToolMixin, '_start_sweep')
        assert hasattr(ToolMixin, '_start_loft')


# =============================================================================
# Test MainWindow Integration
# =============================================================================

class TestMainWindowIntegration:
    """Test that MainWindow properly integrates all mixins."""
    
    def test_main_window_imports(self):
        """Test that MainWindow can be imported with all mixins."""
        from gui.main_window import MainWindow
        assert MainWindow is not None
    
    def test_main_window_has_sketch_methods(self):
        """Test MainWindow has sketch methods from SketchMixin."""
        from gui.main_window import MainWindow
        assert hasattr(MainWindow, '_new_sketch')
        assert hasattr(MainWindow, '_create_sketch_at')
        assert hasattr(MainWindow, '_finish_sketch')
    
    def test_main_window_has_feature_methods(self):
        """Test MainWindow has feature methods from FeatureMixin."""
        from gui.main_window import MainWindow
        assert hasattr(MainWindow, '_extrude_dialog')
        assert hasattr(MainWindow, '_edit_feature')
        assert hasattr(MainWindow, '_on_feature_deleted')
    
    def test_main_window_has_viewport_methods(self):
        """Test MainWindow has viewport methods from ViewportMixin."""
        from gui.main_window import MainWindow
        assert hasattr(MainWindow, '_trigger_viewport_update')
        assert hasattr(MainWindow, '_set_mode')
        assert hasattr(MainWindow, '_reset_view')
    
    def test_main_window_has_tool_methods(self):
        """Test MainWindow has tool methods from ToolMixin."""
        from gui.main_window import MainWindow
        assert hasattr(MainWindow, '_on_3d_action')
        assert hasattr(MainWindow, '_start_transform_mode')
        assert hasattr(MainWindow, '_start_measure_mode')


# =============================================================================
# Test Method Signatures
# =============================================================================

class TestMethodSignatures:
    """Test that method signatures are compatible."""
    
    def test_new_sketch_signature(self):
        """Test _new_sketch has correct signature."""
        from gui.sketch_operations import SketchMixin
        import inspect
        sig = inspect.signature(SketchMixin._new_sketch)
        # Should only have self parameter
        params = list(sig.parameters.keys())
        assert 'self' in params or len(params) == 0  # self is implicit
    
    def test_create_sketch_at_signature(self):
        """Test _create_sketch_at has correct signature."""
        from gui.sketch_operations import SketchMixin
        import inspect
        sig = inspect.signature(SketchMixin._create_sketch_at)
        params = list(sig.parameters.keys())
        assert len(params) >= 3  # self, origin, normal, x_dir_override (optional)
    
    def test_on_3d_action_signature(self):
        """Test _on_3d_action has correct signature."""
        from gui.tool_operations import ToolMixin
        import inspect
        sig = inspect.signature(ToolMixin._on_3d_action)
        params = list(sig.parameters.keys())
        assert len(params) >= 2  # self, action
    
    def test_set_mode_signature(self):
        """Test _set_mode has correct signature."""
        from gui.viewport_operations import ViewportMixin
        import inspect
        sig = inspect.signature(ViewportMixin._set_mode)
        params = list(sig.parameters.keys())
        assert len(params) >= 2  # self, mode


# =============================================================================
# Test No Regression
# =============================================================================

class TestNoRegression:
    """Test that existing functionality is not broken."""
    
    def test_mixin_methods_are_callable(self):
        """Test that all mixin methods are callable."""
        from gui.sketch_operations import SketchMixin
        from gui.feature_operations import FeatureMixin
        from gui.viewport_operations import ViewportMixin
        from gui.tool_operations import ToolMixin
        
        mixins = [SketchMixin, FeatureMixin, ViewportMixin, ToolMixin]
        for mixin in mixins:
            for attr_name in dir(mixin):
                if attr_name.startswith('_') and not attr_name.startswith('__'):
                    attr = getattr(mixin, attr_name)
                    if attr is not None:
                        # Should be callable method
                        assert callable(attr) or isinstance(attr, property), \
                            f"{mixin.__name__}.{attr_name} should be callable"
    
    def test_mixin_docstrings(self):
        """Test that mixins have proper docstrings."""
        from gui.sketch_operations import SketchMixin
        from gui.feature_operations import FeatureMixin
        from gui.viewport_operations import ViewportMixin
        from gui.tool_operations import ToolMixin
        
        assert SketchMixin.__doc__ is not None
        assert FeatureMixin.__doc__ is not None
        assert ViewportMixin.__doc__ is not None
        assert ToolMixin.__doc__ is not None


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
