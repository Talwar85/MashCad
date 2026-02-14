
import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepFeat import BRepFeat_MakePrism
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX
from OCP.gp import gp_Dir
from build123d import Face

def debug_brepfeat_history():
    print("--- Debugging BRepFeat History ---")

    # 1. Create Base Box
    box_maker = BRepPrimAPI_MakeBox(10, 10, 10)
    box_maker.Build()
    base_shape = box_maker.Shape()
    print("Base Shape Created")

    # 2. Find a face to extrude (e.g., top face)
    # We pick the face with normal (0, 0, 1)
    top_face = None
    explorer = TopExp_Explorer(base_shape, TopAbs_FACE)
    while explorer.More():
        face = explorer.Current()
        # Check normal... simplified: just take the last one or something known
        # In a 10x10x10 box at 0,0,0, top face is at z=10
        # Let's just pick face index 5 (usually top in default box creation)
        top_face = face 
        explorer.Next()
    
    if top_face is None:
        print("Error: Could not find face")
        return

    print("Target Face Selected")

    # 3. Setup BRepFeat_MakePrism
    # Simulate Push/Pull Join
    fuse_mode = 1
    direction = gp_Dir(0, 0, 1)
    height = 5.0
    
    prism = BRepFeat_MakePrism()
    # Init(Sbase, Pbase, Skface, Dir, Fuse, Modify)
    # Pbase and Skface are the same here (the base face)
    # IMPORTANT: Skface must be TopoDS_Face, Pbase works as TopoDS_Shape
    from OCP.TopoDS import TopoDS
    prism.Init(base_shape, top_face, TopoDS.Face_s(top_face), direction, fuse_mode, False)
    prism.Perform(height)
    
    if not prism.IsDone():
        print("Error: Prism operation failed")
        return

    result_shape = prism.Shape()
    print("Prism Result Shape Created")

    # 4. Check History using logic similar to _build_history_from_make_shape
    print("\n--- Checking History ---")
    
    mapping_count = 0
    
    # Iterate over all subshapes of base_shape
    for shape_type, type_name in [(TopAbs_FACE, "FACE"), (TopAbs_EDGE, "EDGE"), (TopAbs_VERTEX, "VERTEX")]:
        explorer = TopExp_Explorer(base_shape, shape_type)
        while explorer.More():
            sub_shape = explorer.Current()
            
            # Check Generated
            generated_list = prism.Generated(sub_shape)
            for g in generated_list:
                print(f"[{type_name}] Generated: {g}")
                mapping_count += 1
                
            # Check Modified
            modified_list = prism.Modified(sub_shape)
            for m in modified_list:
                print(f"[{type_name}] Modified: {m}")
                mapping_count += 1
                
            # Check Deleted
            if prism.IsDeleted(sub_shape):
                print(f"[{type_name}] Deleted")
                mapping_count += 1
                
            explorer.Next()

    print(f"\nTotal Mappings Found: {mapping_count}")
    
    if mapping_count == 0:
        print("FAILURE: No history mappings found. This reproduces the user issue.")
    else:
        print("SUCCESS: History mappings found.")

if __name__ == "__main__":
    debug_brepfeat_history()
