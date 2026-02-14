
import sys
import copy
sys.path.insert(0, 'c:/LiteCad')

from modeling import Document, Body, Sketch
from modeling.features.extrude import ExtrudeFeature, PushPullFeature
from modeling.features.fillet_chamfer import FilletFeature
from modeling.tnp_system import ShapeID, ShapeType
from config.feature_flags import set_flag

# Enable TNP debug logging
set_flag("tnp_debug_logging", True)

def reproduction_scenario():
    print("=== Recreating Extrude -> Push -> Push -> Fillet Undo/Redo Issue ===")
    
    # Setup
    doc = Document("TestDoc")
    body = Body("TestBody", document=doc)
    doc.add_body(body)
    
    sketch = Sketch("Base")
    sketch.add_rectangle(0, 0, 100, 100)
    
    print("\n--- Step 1: Extrude ---")
    feat1 = ExtrudeFeature(sketch=sketch, distance=10.0)
    body.add_feature(feat1)
    # Force build
    _ = body._build123d_solid
    vol1 = body._build123d_solid.volume
    print(f"Volume after Extrude: {vol1}")
    
    print("\n--- Step 2: PushPull (Pull Top Feature) ---")
    # Simulate selecting top face. Top face of 100x100x10 box.
    solid = body._build123d_solid
    top_face = None
    best_z = -float('inf')
    for face in solid.faces():
        center = face.center()
        if center.Z > best_z:
            best_z = center.Z
            top_face = face
            
    feat2 = PushPullFeature(
        distance=10.0, 
        direction=1, 
        operation="Join",
        face_index=None
    )
    # Find index of top face.
    for i, f in enumerate(solid.faces()):
        if f.center().Z > 9.9: # Top face at Z=10
             feat2.face_index = i
             print(f"Selected Face Index {i} for PushPull 1 (Top)")
             break
             
    body.add_feature(feat2)
    _ = body._build123d_solid
    vol2 = body._build123d_solid.volume
    print(f"Volume after PushPull 1: {vol2} (Expected ~110000 -> 100*100*10 + 100*100*10 = 200000?)")
    
    print("\n--- Step 3: PushPull (Pull Side Feature) ---")
    # Pull a side face.
    solid = body._build123d_solid
    for i, f in enumerate(solid.faces()):
        c = f.center()
        # Find face at X=100 (Right side)
        if c.X > 99.0:
             feat3 = PushPullFeature(
                distance=10.0, 
                direction=1, 
                operation="Join",
                face_index=i
             )
             print(f"Selected Face Index {i} for PushPull 2 (Side)")
             break
    
    body.add_feature(feat3)
    _ = body._build123d_solid
    vol3 = body._build123d_solid.volume
    print(f"Volume after PushPull 2: {vol3}")
    
    print("\n--- Step 4: Fillet ---")
    # Fillet an edge.
    feat4 = FilletFeature(
        radius=2.0,
        edge_indices=[0] # Just pick first edge
    )
    body.add_feature(feat4)
    _ = body._build123d_solid
    vol4 = body._build123d_solid.volume
    print(f"Volume after Fillet: {vol4}")
    
    print("\n=== STARTING UNDO ===")
    
    feature_stack = [feat1, feat2, feat3, feat4]
    
    # Undo 4 (Fillet)
    print("Undo Fillet")
    body.features.pop()
    body.invalidate_mesh() 
    body._build123d_solid = None
    _ = body._build123d_solid
    print(f"Volume Undo 1: {body._build123d_solid.volume} (Should be {vol3})")
    
    # Undo 3 (Push Side)
    print("Undo Push Side")
    body.features.pop()
    body.invalidate_mesh()
    body._build123d_solid = None
    _ = body._build123d_solid
    print(f"Volume Undo 2: {body._build123d_solid.volume} (Should be {vol2})")
    
    # Undo 2 (Push Top)
    print("Undo Push Top")
    body.features.pop()
    body.invalidate_mesh()
    body._build123d_solid = None
    _ = body._build123d_solid
    print(f"Volume Undo 3: {body._build123d_solid.volume} (Should be {vol1})")
    
    # Undo 1 (Extrude)
    print("Undo Extrude")
    body.features.pop()
    body.invalidate_mesh()
    body._build123d_solid = None
    
    print("\n=== STARTING REDO ===")
    
    # Redo 1 (Extrude)
    print("Redo Extrude")
    body.add_feature(feat1)
    body.invalidate_mesh()
    body._build123d_solid = None
    _ = body._build123d_solid
    r_vol1 = body._build123d_solid.volume
    print(f"Volume Redo 1: {r_vol1} (Target: {vol1})")
    
    # Redo 2 (Push Top)
    print("Redo Push Top")
    body.add_feature(feat2)
    body.invalidate_mesh()
    body._build123d_solid = None 
    _ = body._build123d_solid
    r_vol2 = body._build123d_solid.volume
    print(f"Volume Redo 2: {r_vol2} (Target: {vol2})")
    if abs(r_vol2 - vol2) > 0.1: print(f"FAIL Redo 2 - Volume Mismatch! Got {r_vol2} vs {vol2}")

    # Redo 3 (Push Side)
    print("Redo Push Side")
    body.add_feature(feat3)
    body.invalidate_mesh()
    body._build123d_solid = None
    _ = body._build123d_solid
    r_vol3 = body._build123d_solid.volume 
    print(f"Volume Redo 3: {r_vol3} (Target: {vol3})")
    if abs(r_vol3 - vol3) > 0.1: print(f"FAIL Redo 3 - Volume Mismatch! Got {r_vol3} vs {vol3}")
    
    # Redo 4 (Fillet)
    print("Redo Fillet")
    body.add_feature(feat4)
    body.invalidate_mesh()
    body._build123d_solid = None
    _ = body._build123d_solid
    r_vol4 = body._build123d_solid.volume
    print(f"Volume Redo 4: {r_vol4} (Target: {vol4})")
    if abs(r_vol4 - vol4) > 0.1: print(f"FAIL Redo 4 - But maybe it fixed itself here?")

if __name__ == "__main__":
    reproduction_scenario()
