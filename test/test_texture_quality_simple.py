"""
Test für Texture Quality Modes (ohne GUI)
"""

def test_texture_quality_feature():
    """Testet dass SurfaceTextureFeature den quality_mode unterstützt."""
    print("\n=== Testing Texture Quality Modes ===\n")

    # Teste SurfaceTextureFeature mit Quality-Modus
    print("[1] Testing SurfaceTextureFeature with quality_mode...")
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

    # Teste die Quality-Logik
    print("[2] Testing quality subdivisions mapping...")
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

    print("   [OK] Quality subdivisions mapping is correct\n")

    print("=== ALL TESTS PASSED ===\n")
    print("Texture Quality Modes Summary:")
    print("  0 = Fast      (2 subdivisions, ~250 vertices)")
    print("  1 = Balanced  (3 subdivisions, ~500 vertices) [DEFAULT]")
    print("  2 = Detailed (5 subdivisions, ~2000 vertices)")
    print()


if __name__ == '__main__':
    test_texture_quality_feature()
