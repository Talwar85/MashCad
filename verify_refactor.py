
import sys
import os

print("Verifying refactoring imports...")

try:
    print("\n--- Checking default imports from modeling/__init__.py ---")
    from modeling import Feature, FeatureType, ExtrudeFeature, RevolveFeature, FilletFeature, ChamferFeature, ImportFeature, ConstructionPlane
    print("SUCCESS: Imported base features from modeling package.")
except ImportError as e:
    print(f"FAILURE: Could not import from modeling package: {e}")

try:
    print("\n--- Checking direct submodules ---")
    import modeling.features.base
    import modeling.features.extrude
    import modeling.features.revolve
    import modeling.features.fillet_chamfer
    import modeling.features.import_feature
    import modeling.construction
    print("SUCCESS: Imported submodules directly.")
except ImportError as e:
    print(f"FAILURE: Could not import submodules: {e}")

try:
    print("\n--- Checking GUI Manager imports (Main Window logic) ---")
    from gui.managers.notification_manager import NotificationManager
    from gui.managers.preview_manager import PreviewManager
    from gui.managers.tnp_debug_manager import TNPDebugManager
    print("SUCCESS: Imported GUI managers.")
except ImportError as e:
    print(f"FAILURE: Could not import GUI managers: {e}")

print("\nVerification complete.")
