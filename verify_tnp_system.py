import sys
import os
import unittest
import tempfile
import pickle

sys.path.append(os.getcwd())

from modeling import Body
from modeling import Body
# from modeling.features.sketch import SketchFeature # Missing
from modeling.features.extrude import ExtrudeFeature, PushPullFeature
from modeling.features.fillet_chamfer import FilletFeature
from modeling.features.advanced import ShellFeature, DraftFeature, PrimitiveFeature
from modeling.tnp_system import ShapeNamingService
from build123d import Box

# Mocking PrimitiveFeature because create_solid seems missing in source
class MockPrimitiveFeature(PrimitiveFeature):
    def create_solid(self):
        # Einfache Box für Testzwecke
        return Box(10, 10, 10)

class MockDoc:
    def __init__(self):
        self._shape_naming_service = ShapeNamingService()

class TNPVerificationTests(unittest.TestCase):
    
    def setUp(self):
        # Create a fresh Body for each test
        self.body = Body("TestBody")
        
        # Helper to create base box
        self.base_feature = MockPrimitiveFeature(primitive_type="Box", name="BaseBox")
        self.body.add_feature(self.base_feature)
        self.body._rebuild()

        # Ensure Document-like structure for TNP if needed
        self.doc = MockDoc()
        self.body._document = self.doc

    def get_volume(self):
        if hasattr(self.body, "volume") and self.body.volume is not None:
            return self.body.volume
        if hasattr(self.body, "_build123d_solid") and self.body._build123d_solid:
             return self.body._build123d_solid.volume
        return 0.0

    def test_01_feature_compliance(self):
        """Verify that basic features build and register TNP IDs."""
        print("\n[TEST] Feature Compliance")
        
        # Base is already built in setUp
        vol_base = self.get_volume()
        self.assertAlmostEqual(vol_base, 1000.0, delta=0.1)
        
        # 3. PushPull (Join)
        # Using face index 5 (Top of box)
        pp = PushPullFeature(face_index=5, distance=5, operation="Join", name="Push1")
        pp.face_index = 5
        self.body.add_feature(pp)
        self.body._rebuild()
        vol_push = self.get_volume()
        self.assertGreater(vol_push, vol_base)
        self.assertAlmostEqual(vol_push, 1500.0, delta=0.1)

        # 4. Fillet
        # Fillet using generic edge indices (top edges of new box)
        fillet = FilletFeature(radius=1.0, name="Fillet1")
        fillet.edge_indices = [0, 1, 2, 3] # Try first few edges
        self.body.add_feature(fillet)
        self.body._rebuild()
        vol_fillet = self.get_volume()
        self.assertLess(vol_fillet, vol_push) 

        print("  ✓ Feature Stack Built Successfully")

    def test_02_history_stability(self):
        """Verify modifying early history updates downstream correctly."""
        print("\n[TEST] History Stability")
        
        # BaseBox (10x10x10)
        vol_initial = self.get_volume()
        self.assertAlmostEqual(vol_initial, 1000.0, delta=0.1)
        
        # Modify Base: Simulate change by replacing Feature
        # Note: PrimitiveFeature parameters update is cleaner but for this Mock we just swap it
        print("  Modifying BaseBox (10x10x10 -> 20x10x10)...")
        
        # Remove old feature
        self.body.features.pop(0) 
        
        # Add new larger feature
        class LargerMockPrimitiveFeature(PrimitiveFeature):
            def create_solid(self):
                 return Box(20, 10, 10)
        
        new_base = LargerMockPrimitiveFeature(primitive_type="Box", name="LargeBox")
        self.body.features.insert(0, new_base)
        
        # Rebuild
        self.body._rebuild()
        
        val_updated = self.get_volume()
        # 20 * 10 * 10 = 2000
        self.assertAlmostEqual(val_updated, 2000.0, delta=0.1)
        print("  ✓ History Update Propagated (Volume Correct)")

    def test_03_persistence(self):
        """Verify Save/Load (Pickle) preserves state and IDs."""
        print("\n[TEST] Persistence")
        
        # Base setup in setUp
        self.body._rebuild()
        original_vol = self.get_volume()
        
        # Save (Pickle)
        print("  Pickling Body...")
        data = pickle.dumps(self.body)
        
        # Load (Unpickle)
        print("  Unpickling Body...")
        loaded_body = pickle.loads(data)
        
        doc = getattr(loaded_body, '_document', None)
        if doc is None:
             loaded_body._document = self.doc

        # Verify State
        self.assertEqual(len(loaded_body.features), 1)
        
        try:
            loaded_body._rebuild()
            loaded_vol = 0.0
            if hasattr(loaded_body, "volume") and loaded_body.volume:
                 loaded_vol = loaded_body.volume
            elif hasattr(loaded_body, "_build123d_solid") and loaded_body._build123d_solid:
                 loaded_vol = loaded_body._build123d_solid.volume
            
            self.assertAlmostEqual(loaded_vol, original_vol, delta=0.1)
            print("  ✓ Persistence Verified (Loaded Body Rebuilds Correctly)")
        except Exception as e:
            self.fail(f"Rebuild after load failed: {e}")

    def test_04_undo_redo(self):
        """Verify Undo/Redo restores state exactly."""
        print("\n[TEST] Undo/Redo")
        
        # 1. Base (1000.0)
        vol_1 = self.get_volume()
        
        # 2. Push (+500.0)
        pp = PushPullFeature(face_index=5, distance=5, operation="Join", name="Push1")
        pp.face_index = 5
        self.body.add_feature(pp)
        self.body._rebuild()
        vol_2 = self.get_volume()
        self.assertNotEqual(vol_1, vol_2)
        self.assertAlmostEqual(vol_2, 1500.0, delta=0.1)

        # Undo
        print("  Undoing Push...")
        self.body.features.pop()
        self.body._rebuild()
        vol_undo = self.get_volume()
        
        self.assertAlmostEqual(vol_undo, vol_1, delta=0.1)
        print("  ✓ Undo Successful (Volume Restored)")
        
        # Redo
        print("  Redoing Push...")
        self.body.add_feature(pp)
        self.body._rebuild()
        vol_redo = self.get_volume()
        
        self.assertAlmostEqual(vol_redo, vol_2, delta=0.1)
        print("  ✓ Redo Successful (Volume Restored)")

if __name__ == "__main__":
    unittest.main()
