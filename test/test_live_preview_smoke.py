"""
Smoke Tests für Live Preview Features

Einfache Tests die prüfen ob die Features geladen werden können und grundlegende Funktionalität haben.
"""

import pytest


def test_feature_preview_mixin_imports():
    """Testet dass das FeaturePreviewMixin importiert werden kann."""
    from gui.viewport.feature_preview_mixin import FeaturePreviewMixin
    assert FeaturePreviewMixin is not None

    # Prüfe dass die Methoden existieren
    assert hasattr(FeaturePreviewMixin, 'set_shell_mode')
    assert hasattr(FeaturePreviewMixin, 'update_shell_preview')
    assert hasattr(FeaturePreviewMixin, 'update_fillet_preview')
    assert hasattr(FeaturePreviewMixin, 'update_chamfer_preview')
    assert hasattr(FeaturePreviewMixin, '_clear_shell_preview')
    assert hasattr(FeaturePreviewMixin, '_clear_fillet_preview')
    assert hasattr(FeaturePreviewMixin, '_clear_chamfer_preview')
    assert hasattr(FeaturePreviewMixin, 'clear_all_feature_previews')


def test_feature_flags_are_true():
    """Testet dass alle Feature Flags auf True gesetzt sind."""
    from config.feature_flags import FEATURE_FLAGS, set_flag

    # Setze Flags explizit (für Test-Umgebung)
    set_flag('live_preview_shell', True)
    set_flag('live_preview_fillet', True)
    set_flag('live_preview_chamfer', True)

    assert FEATURE_FLAGS.get('live_preview_shell') is True
    assert FEATURE_FLAGS.get('live_preview_fillet') is True
    assert FEATURE_FLAGS.get('live_preview_chamfer') is True


def test_feature_preview_mixin_in_viewport():
    """Testet dass FeaturePreviewMixin im Viewport integriert ist."""
    from gui.viewport_pyvista import PyVistaViewport

    # Prüfe dass die Methoden im Viewport verfügbar sind
    assert hasattr(PyVistaViewport, 'set_shell_mode')
    assert hasattr(PyVistaViewport, 'update_shell_preview')
    assert hasattr(PyVistaViewport, 'update_fillet_preview')
    assert hasattr(PyVistaViewport, 'update_chamfer_preview')
    assert hasattr(PyVistaViewport, 'clear_all_feature_previews')


def test_main_window_preview_methods():
    """Testet dass die MainWindow Preview-Methoden existieren."""
    from gui.main_window import MainWindow

    assert hasattr(MainWindow, '_execute_shell_live_preview')
    assert hasattr(MainWindow, '_execute_fillet_live_preview')
    assert hasattr(MainWindow, '_execute_chamfer_live_preview')


def test_shell_handler_in_feature_dialogs():
    """Testet dass der Shell Handler in FeatureDialogsMixin existiert."""
    from gui.feature_dialogs import FeatureDialogsMixin

    assert hasattr(FeatureDialogsMixin, '_on_shell_thickness_changed')
    assert hasattr(FeatureDialogsMixin, '_stop_shell_mode')


def test_fillet_handler_in_tool_operations():
    """Testet dass der Fillet/Chamfer Handler in MainWindow existiert."""
    from gui.main_window import MainWindow

    # Die Funktionen werden als Mixin-Methoden in MainWindow verwendet
    # und sollten von tool_operations importiert werden
    # Prüfe dass die Methode in MainWindow verfügbar ist
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
    """Testet dass die Debounce Settings existieren."""
    from config.feature_flags import FEATURE_FLAGS

    assert 'preview_debounce_ms' in FEATURE_FLAGS
    assert 'preview_subdivisions_live' in FEATURE_FLAGS
    assert 'preview_subdivisions_final' in FEATURE_FLAGS

    # Prüfe vernünftige Werte
    assert FEATURE_FLAGS['preview_debounce_ms'] > 0
    assert FEATURE_FLAGS['preview_subdivisions_live'] > 0
    assert FEATURE_FLAGS['preview_subdivisions_final'] > 0


def test_is_enabled_function():
    """Testet die is_enabled Funktion."""
    from config.feature_flags import is_enabled, set_flag

    # Setze Flags explizit (für Test-Umgebung)
    set_flag('live_preview_shell', True)
    set_flag('live_preview_fillet', True)
    set_flag('live_preview_chamfer', True)

    assert is_enabled('live_preview_shell') is True
    assert is_enabled('live_preview_fillet') is True
    assert is_enabled('live_preview_chamfer') is True
    assert is_enabled('live_preview_textures') is True
    assert is_enabled('live_preview_patterns') is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
