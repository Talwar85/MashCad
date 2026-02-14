"""
Deep diagnostic: WHY does BRepFeat_MakePrism.Modified() return empty?
We test every sub-shape of source_solid against the history.
"""
import sys, os
sys.path.append(os.getcwd())

from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeEdge
from OCP.gp import gp_Pnt, gp_Vec, gp_Dir
from OCP.GC import GC_MakeSegment
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
from OCP.BRepFeat import BRepFeat_MakePrism
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopExp import TopExp
import OCP.BRepGProp as BRepGProp
from OCP.GProp import GProp_GProps

def face_center(f):
    props = GProp_GProps()
    BRepGProp.BRepGProp.SurfaceProperties_s(f, props)
    c = props.CentreOfMass()
    return f"({c.X():.1f}, {c.Y():.1f}, {c.Z():.1f})"

def edge_center(e):
    props = GProp_GProps()
    BRepGProp.BRepGProp.LinearProperties_s(e, props)
    c = props.CentreOfMass()
    return f"({c.X():.1f}, {c.Y():.1f}, {c.Z():.1f}) L={props.Mass():.1f}"

def make_rect_face(w, h):
    p1, p2, p3, p4 = gp_Pnt(0,0,0), gp_Pnt(w,0,0), gp_Pnt(w,h,0), gp_Pnt(0,h,0)
    edges = [BRepBuilderAPI_MakeEdge(GC_MakeSegment(a, b).Value()).Edge()
             for a, b in [(p1,p2),(p2,p3),(p3,p4),(p4,p1)]]
    mw = BRepBuilderAPI_MakeWire(edges[0], edges[1], edges[2], edges[3])
    return BRepBuilderAPI_MakeFace(mw.Wire()).Face()

def iter_list(shape_list):
    """Convert TopTools_ListOfShape to python list."""
    try:
        return list(shape_list)
    except Exception:
        pass
    try:
        it = shape_list.Iterator()
        result = []
        while it.More():
            result.append(it.Value())
            it.Next()
        return result
    except Exception:
        return []

# === 1. Create base box via Prism ===
face = make_rect_face(20, 30)
prism = BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, 10))
prism.Build()
base_solid = prism.Shape()

# Collect ALL faces of base_solid
face_map = TopTools_IndexedMapOfShape()
TopExp.MapShapes_s(base_solid, TopAbs_FACE, face_map)
print(f"\n=== Base solid has {face_map.Extent()} unique faces ===")

# Find the top face (Z ~ 10)
top_face = None
for i in range(1, face_map.Extent() + 1):
    f = TopoDS.Face_s(face_map.FindKey(i))
    c = face_center(f)
    print(f"  Face {i}: center={c}")
    props = GProp_GProps()
    BRepGProp.BRepGProp.SurfaceProperties_s(f, props)
    if props.CentreOfMass().Z() > 9.0:
        top_face = f
        print(f"    ^ This is the TOP face")

if not top_face:
    print("ERROR: No top face found!")
    sys.exit(1)

# === 2. BRepFeat_MakePrism ===
print(f"\n=== Running BRepFeat_MakePrism (push top face +5mm) ===")
dir_vec = gp_Dir(0, 0, 1)
feat = BRepFeat_MakePrism(base_solid, top_face, top_face, dir_vec, 1, True)
feat.Perform(5.0)

if not feat.IsDone():
    print("ERROR: BRepFeat failed!")
    sys.exit(1)

result_solid = feat.Shape()

# === 3. Test History on EVERY face of the source solid ===
print(f"\n=== Testing Modified() on each source face ===")
for i in range(1, face_map.Extent() + 1):
    f = TopoDS.Face_s(face_map.FindKey(i))
    c = face_center(f)
    
    mod = iter_list(feat.Modified(f))
    gen = iter_list(feat.Generated(f))
    is_deleted = feat.IsDeleted(f)
    
    # Also try Reversed
    mod_rev = iter_list(feat.Modified(f.Reversed()))
    gen_rev = iter_list(feat.Generated(f.Reversed()))
    
    print(f"  Face {i} {c}: Modified={len(mod)} Generated={len(gen)} Deleted={is_deleted} | Rev: Mod={len(mod_rev)} Gen={len(gen_rev)}")

# === 4. Test History on EVERY edge of the source solid ===
print(f"\n=== Testing Modified() on each source edge ===")
edge_map = TopTools_IndexedMapOfShape()
TopExp.MapShapes_s(base_solid, TopAbs_EDGE, edge_map)
print(f"Base solid has {edge_map.Extent()} unique edges")

for i in range(1, edge_map.Extent() + 1):
    e = TopoDS.Edge_s(edge_map.FindKey(i))
    c = edge_center(e)
    
    mod = iter_list(feat.Modified(e))
    gen = iter_list(feat.Generated(e))
    is_deleted = feat.IsDeleted(e)
    
    mod_rev = iter_list(feat.Modified(e.Reversed()))
    gen_rev = iter_list(feat.Generated(e.Reversed()))
    
    status = ""
    if mod: status += f" MOD->{len(mod)}"
    if gen: status += f" GEN->{len(gen)}"
    if mod_rev: status += f" MOD_REV->{len(mod_rev)}"
    if gen_rev: status += f" GEN_REV->{len(gen_rev)}"
    if is_deleted: status += " DELETED"
    if not status: status = " (no history)"
    
    print(f"  Edge {i} {c}:{status}")

# === 5. Check what _collect_brepfeat_history_inputs would find ===
print(f"\n=== Simulating _collect_brepfeat_history_inputs ===")
# This function uses find_shape_id_by_face/edge with require_exact=True
# The issue might be: the shapes found by TopExp_Explorer(modified_face, EDGE)
# might NOT be the same TShape pointers as those in the IndexedMap.
top_face_edges = []
exp = TopExp_Explorer(top_face, TopAbs_EDGE)
while exp.More():
    e = TopoDS.Edge_s(exp.Current())
    top_face_edges.append(e)
    exp.Next()
print(f"  Top face has {len(top_face_edges)} edges (via Explorer)")

# Check if these edges are in the edge_map
for j, e in enumerate(top_face_edges):
    in_map = edge_map.Contains(e)
    c = edge_center(e)
    
    # Also check the SAME edge from the map
    mod = iter_list(feat.Modified(e))
    mod_rev = iter_list(feat.Modified(e.Reversed()))
    
    print(f"  TopFaceEdge {j} {c}: InEdgeMap={in_map} Mod={len(mod)} ModRev={len(mod_rev)}")

print("\n=== DONE ===")
