import sys
import os

# Pfad zu LiteCad hinzufügen
sys.path.append(os.getcwd())

from modeling import Body
from modeling.features.advanced import PrimitiveFeature
from modeling.features.extrude import PushPullFeature
from build123d import Box

# Mocking PrimitiveFeature because create_solid seems missing in source
class MockPrimitiveFeature(PrimitiveFeature):
    def create_solid(self):
        # Einfache Box für Testzwecke
        return Box(10, 10, 10)

def get_volume(body):
    if hasattr(body, "volume") and body.volume is not None:
        return body.volume
    if hasattr(body, "_build123d_solid") and body._build123d_solid:
        if hasattr(body._build123d_solid, "volume"):
            return body._build123d_solid.volume
    if hasattr(body, "vtk_mesh") and body.vtk_mesh:
        return body.vtk_mesh.volume
    return 0.0

class MockDoc:
    def __init__(self):
        from modeling.tnp_system import ShapeNamingService
        self._shape_naming_service = ShapeNamingService()

def reproduce():
    print("--- Starting PushPull Reproduction ---")
    body = Body("TestBody")
    body._document = MockDoc()
    
    # 1. Base Feature (Mock Box)
    pf = MockPrimitiveFeature(primitive_type="Box", name="BaseBox")
    body.add_feature(pf)
    
    # Force rebuild to ensure solid is created
    body._rebuild()
    
    v1 = get_volume(body)
    print(f"Volume after BaseBox: {v1:.2f}")
    
    if v1 <= 0:
        print("CRITICAL: Base volume is 0. Aborting.")
        return

    # 3. PushPull (Join on Top Face)
    push_feature = PushPullFeature(
        face_index=5, 
        distance=5, 
        operation="Join", 
        name="PushPull_Join"
    )
    push_feature.face_index = 5
    
    print("\n--- Applying PushPull (Join +5mm) ---")
    body.add_feature(push_feature)
    
    try:
        v2 = get_volume(body)
        print(f"Volume after PushPull: {v2:.2f}")
        
        if v2 > v1:
            print("SUCCESS: Volume increased!")
        elif v2 == v1:
            print("FAILURE: Volume did not change (PushPull ignored?)")
        else:
            print(f"FAILURE: Volume decreased? ({v2:.2f})")
    except Exception as e:
        print(f"CRITICAL ERROR during PushPull Join: {e}")

    # 4. PushPull (Cut)
    pull_feature = PushPullFeature(
        face_index=5,
        distance=2,
        operation="Cut",
        direction=-1,
        name="PushPull_Cut"
    )
    pull_feature.face_index = 5
    
    print("\n--- Applying PushPull (Cut -2mm) ---")
    body.add_feature(pull_feature)
    
    try:
        v3 = get_volume(body)
        print(f"Volume after PushPull Cut: {v3:.2f}")

        if v3 < v2:
            print("SUCCESS: Volume decreased!")
        else:
            print(f"FAILURE: Volume did not decrease. ({v3} >= {v2})")
    except Exception as e:
        print(f"CRITICAL ERROR during PushPull Cut: {e}")

if __name__ == "__main__":
    reproduce()
