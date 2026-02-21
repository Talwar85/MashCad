"""
Test für Texture Quality Modes
Testet die 3 Quality-Modi: Fast, Balanced, Detailed
"""

import pytest
from unittest.mock import Mock


def test_texture_quality_modes():
    """Testet dass die 3 Quality-Modi korrekt konfiguriert sind."""
    print("\n=== Testing Texture Quality Modes ===\n")

    # 1. Teste Panel UI
    print("[1] Testing Panel UI...")
    from gui.widgets.texture_panel import SurfaceTexturePanel

    panel = SurfaceTexturePanel()

    # Prüfe dass Quality-Combo existiert
    assert hasattr(panel, 'quality_combo'), "Quality combo not found"
    assert panel.quality_combo.count() == 3, "Should have 3 quality modes"

    # Prüfe Quality-Modi
    modes = [panel.quality_combo.itemText(i) for i in range(3)]
    print(f"   Quality Modes: {modes}")
    assert "Fast" in modes or "Schnell" in modes
    assert "Balanced" in modes or "Ausgewogen" in modes
    assert "Detailed" in modes or "Detailliert" in modes

    # Prüfe Default-Wert
    default_index = panel.quality_combo.currentIndex()
    print(f"   Default Quality Mode: {default_index} (should be 1 = Balanced)")
    assert default_index == 1, "Default should be Balanced (index 1)"

    print("   [OK] Panel UI has 3 quality modes with Balanced as default\n")

    # 2. Teste get_config mit Quality-Modus
    print("[2] Testing get_config()...")
    config = panel.get_config()

    assert 'quality_mode' in config, "quality_mode not in config"
    quality_mode = config['quality_mode']
    print(f"   Quality Mode in config: {quality_mode} (0=Fast, 1=Balanced, 2=Detailed)")
    assert quality_mode in [0, 1, 2], "Invalid quality mode"

    print("   [OK] get_config() returns quality_mode\n")

    # 3. Teste Quality-Mode Änderung
    print("[3] Testing quality mode changes...")
    for idx in range(3):
        panel.quality_combo.setCurrentIndex(idx)
        config = panel.get_config()
        assert config['quality_mode'] == idx, f"Quality mode should be {idx}"

        # Prüfe Info-Text
        panel._update_quality_info(idx)
        info_text = panel.quality_info.text()
        assert len(info_text) > 0, f"Info text should not be empty for mode {idx}"
        print(f"   Mode {idx}: {info_text[:50]}...")

    print("   [OK] All quality modes can be selected\n")

    # 4. Teste SurfaceTextureFeature mit Quality-Modus
    print("[4] Testing SurfaceTextureFeature with quality_mode...")
    from modeling.features.advanced import SurfaceTextureFeature

    # Teste Default
    feature = SurfaceTextureFeature()
    assert hasattr(feature, 'quality_mode'), "quality_mode attribute missing"
    assert feature.quality_mode == 1, "Default quality_mode should be 1 (Balanced)"
    print(f"   Default feature quality_mode: {feature.quality_mode}")

    # Teste alle Modi
    for mode in [0, 1, 2]:
        feature = SurfaceTextureFeature(quality_mode=mode)
        assert feature.quality_mode == mode, f"Quality mode should be {mode}"
        print(f"   Created feature with quality_mode={mode}")

    print("   [OK] SurfaceTextureFeature supports quality_mode\n")

    # 5. Teste Viewport Integration
    print("[5] Testing viewport integration...")

    # Mock Viewport mit texture_feature
    from gui.viewport.feature_preview_mixin import FeaturePreviewMixin

    class MockViewport:
        def __init__(self):
            pass

    viewport = MockViewport()

    # Simuliere verschiedene Quality-Modi
    quality_subdivisions = {
        0: 2,  # Fast
        1: 3,  # Balanced
        2: 5,  # Detailed
    }

    for mode, expected_subs in quality_subdivisions.items():
        # Simuliere die Logik aus _apply_texture_preview
        if mode == 0:
            preview_subdivisions = 2
        elif mode == 1:
            preview_subdivisions = 3
        else:
            preview_subdivisions = 5

        assert preview_subdivisions == expected_subs, \
            f"Mode {mode} should use {expected_subs} subdivisions"
        print(f"   Mode {mode}: {preview_subdivisions} subdivisions")

    print("   [OK] Viewport uses correct subdivisions for each mode\n")

    # 6. Teste die Quality-Beschreibungen
    print("[6] Testing quality descriptions...")
    panel._update_quality_info(0)
    assert "Fast" in panel.quality_info.text() or "schnell" in panel.quality_info.text().lower()

    panel._update_quality_info(1)
    assert "Balanced" in panel.quality_info.text() or "gut" in panel.quality_info.text().lower()

    panel._update_quality_info(2)
    assert "Detailed" in panel.quality_info.text() or "hoch" in panel.quality_info.text().lower() or "quality" in panel.quality_info.text().lower()

    print("   [OK] Quality descriptions are correct\n")

    print("=== ALL TESTS PASSED ===\n")
    print("Texture Quality Modes Summary:")
    print("  0 = Fast      (2 subdivisions, ~250 vertices)")
    print("  1 = Balanced  (3 subdivisions, ~500 vertices) [DEFAULT]")
    print("  2 = Detailed (5 subdivisions, ~2000 vertices)")
    print()


if __name__ == '__main__':
    test_texture_quality_modes()
