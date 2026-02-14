import sys
import os

sys.path.append(os.getcwd())

from modeling import Body
from modeling.features.advanced import PrimitiveFeature
from modeling.features.extrude import PushPullFeature, ExtrudeFeature
from modeling.features.fillet_chamfer import FilletFeature
from build123d import Box

# Mocking PrimitiveFeature
class MockPrimitiveFeature(PrimitiveFeature):
    def create_solid(self):
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

def reproduce_undo():
    print("--- Starting Undo/Redo Reproduction ---")
    body = Body("UndoTestBody")
    
    # 1. Base Feature
    pf = MockPrimitiveFeature(primitive_type="Box", name="BaseBox")
    body.add_feature(pf)
    body._rebuild()
    print(f"Step 1 (Base): Volume={get_volume(body):.2f}, Faces={len(body.features)}")

    # 2. Push (+5mm)
    push1 = PushPullFeature(face_index=5, distance=5, operation="Join", name="Push1")
    push1.face_index = 5
    body.add_feature(push1)
    body._rebuild()
    print(f"Step 2 (Push1): Volume={get_volume(body):.2f}, Faces={len(body.features)}")

    # 3. Push (+5mm) -> Total +10mm
    push2 = PushPullFeature(face_index=5, distance=5, operation="Join", name="Push2")
    push2.face_index = 5 # Assuming top face is still 5 or tracked
    body.add_feature(push2)
    body._rebuild()
    print(f"Step 3 (Push2): Volume={get_volume(body):.2f}, Faces={len(body.features)}")
    
    vol_after_push2 = get_volume(body)

    fillet = FilletFeature(radius=2.0, name="Fillet1")
    # Try all edges to ensure we hit something
    # or just rely on global edge selection if supported, but here we need indices.
    # We'll try a range of indices to likely hit the top edges.
    fillet.edge_indices = list(range(12)) # Box has 12 edges usually.
    body.add_feature(fillet)
    
    try:
        body._rebuild()
        vol_fillet = get_volume(body)
        print(f"Step 4 (Fillet): Volume={vol_fillet:.2f}")
        
        if vol_fillet < vol_after_push2:
            print("SUCCESS: Fillet reduced volume.")
        else:
             print("WARNING: Fillet did not reduce volume (edges not selected?).")
             
    except Exception as e:
        print(f"Step 4 Failed: {e}")

    # --- UNDO SIMULATION ---
    print("\n--- Simulating UNDO ---")
    
    # Undo Fillet
    print("Undoing Fillet...")
    body.features.pop() # Remove last feature
    body._rebuild()
    vol_undo_1 = get_volume(body)
    print(f"After First Undo: Volume={vol_undo_1:.2f}")
    
    if abs(vol_undo_1 - vol_after_push2) > 0.01:
         print(f"FAILURE: Volume mismatch after undoing Fillet. Expected {vol_after_push2:.2f}, got {vol_undo_1:.2f}")
    else:
         print("SUCCESS: Undo Fillet volume usage matches.")

    # Undo Push2
    print("Undoing Push2...")
    body.features.pop()
    body._rebuild()
    print(f"After Second Undo: Volume={get_volume(body):.2f}")

    # Undo Push1
    print("Undoing Push1...")
    body.features.pop()
    body._rebuild()
    print(f"After Third Undo: Volume={get_volume(body):.2f}")

if __name__ == "__main__":
    reproduce_undo()
