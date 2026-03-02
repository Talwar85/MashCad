"""
Smoke Tests fÃ¼r Live Preview Features

Einfache Tests die prÃ¼fen ob die Features geladen werden kÃ¶nnen und grundlegende FunktionalitÃ¤t haben.
"""

import pytest


def test_feature_preview_mixin_imports():
    """Testet dass das FeaturePreviewMixin importiert werden kann."""
    from gui.viewport.feature_preview_mixin import FeaturePreviewMixin
    assert FeaturePreviewMixin is not None

    assert hasattr(FeaturePreviewMixin, 'set_shell_mode')
    assert hasattr(FeaturePreviewMixin, 'update_shell_preview')
    assert hasattr(FeaturePreviewMixin, 'update_fillet_preview')
    assert hasattr(FeaturePreviewMixin, 'update_chamfer_preview')
    assert hasattr(FeaturePreviewMixin, '_clear_shell_preview')
    assert hasattr(FeaturePreviewMixin, '_clear_fillet_preview')
    assert hasattr(FeaturePreviewMixin, '_clear_chamfer_preview')
    assert hasattr(FeaturePreviewMixin, 'clear_all_feature_previews')


def test_live_preview_methods_are_available_without_flags():
    """Testet dass der Live-Preview-Pfad nicht mehr von Feature-Flags abhÃ¤ngt."""
    from gui.main_window import MainWindow

    assert hasattr(MainWindow, '_request_live_preview')
    assert hasattr(MainWindow, '_execute_live_preview')
    assert hasattr(MainWindow, '_execute_shell_live_preview')
    assert hasattr(MainWindow, '_execute_fillet_live_preview')
    assert hasattr(MainWindow, '_execute_chamfer_live_preview')


def test_feature_preview_mixin_in_viewport():
    """Testet dass FeaturePreviewMixin im Viewport integriert ist."""
    from gui.viewport_pyvista import PyVistaViewport

    assert hasattr(PyVistaViewport, 'set_shell_mode')
    assert hasattr(PyVistaViewport, 'update_shell_preview')
    assert hasattr(PyVistaViewport, 'update_fillet_preview')
    assert hasattr(PyVistaViewport, 'update_chamfer_preview')
    assert hasattr(PyVistaViewport, 'clear_all_feature_previews')


def test_shell_handler_in_feature_dialogs():
    """Testet dass der Shell Handler in FeatureDialogsMixin existiert."""
    from gui.feature_dialogs import FeatureDialogsMixin

    assert hasattr(FeatureDialogsMixin, '_on_shell_thickness_changed')
    assert hasattr(FeatureDialogsMixin, '_stop_shell_mode')


def test_fillet_handler_in_tool_operations():
    """Testet dass der Fillet/Chamfer Handler in MainWindow existiert."""
    from gui.main_window import MainWindow

    assert hasattr(MainWindow, '_on_fillet_radius_changed')
    assert hasattr(MainWindow, '_on_fillet_cancelled')


def test_shell_panel_has_signal():
    """Testet dass ShellInputPanel das thickness_changed Signal hat."""
    from gui.input_panels import ShellInputPanel

    assert hasattr(ShellInputPanel, 'thickness_changed')


def test_fillet_panel_has_signal():
    """Testet dass FilletChamferPanel das radius_changed Signal hat."""
    from gui.input_panels import FilletChamferPanel

    assert hasattr(FilletChamferPanel, 'radius_changed')


def test_preview_debounce_settings():
    """Testet dass die verbleibende Preview-Konfiguration existiert."""
    from config.feature_flags import FEATURE_SETTINGS

    assert 'preview_debounce_ms' in FEATURE_SETTINGS
    assert FEATURE_SETTINGS['preview_debounce_ms'] > 0


def test_is_enabled_function():
    """Testet die is_enabled Funktion fÃ¼r verbleibende Preview-Optionen."""
    from config.feature_flags import is_enabled

    assert is_enabled('normal_map_preview') is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
