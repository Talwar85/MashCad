"""
Pinpoint WHY _build_brepfeat_history_mappings returns 0 mappings.

Key question: Generated edges from BRepFeat - do they exist in result_solid?
And is the shape_type filtering rejecting them?
"""
import sys, os
sys.path.append(os.getcwd())

from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeEdge
from OCP.gp import gp_Pnt, gp_Vec, gp_Dir
from OCP.GC import GC_MakeSegment
from OCP.TopExp import TopExp_Explorer, TopExp
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX
from OCP.BRepFeat import BRepFeat_MakePrism
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_IndexedMapOfShape
import OCP.BRepGProp as BRepGProp_mod
from OCP.GProp import GProp_GProps

type_names = {
    0: 'COMPOUND', 1: 'COMPSOLID', 2: 'SOLID', 3: 'SHELL',
    4: 'FACE', 5: 'WIRE', 6: 'EDGE', 7: 'VERTEX', 8: 'SHAPE'
}

def make_rect_face(w, h):
    p1, p2, p3, p4 = gp_Pnt(0,0,0), gp_Pnt(w,0,0), gp_Pnt(w,h,0), gp_Pnt(0,h,0)
    edges = [BRepBuilderAPI_MakeEdge(GC_MakeSegment(a, b).Value()).Edge()
             for a, b in [(p1,p2),(p2,p3),(p3,p4),(p4,p1)]]
    mw = BRepBuilderAPI_MakeWire(edges[0], edges[1], edges[2], edges[3])
    return BRepBuilderAPI_MakeFace(mw.Wire()).Face()

def iter_list(shape_list):
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

# === Setup ===
face = make_rect_face(20, 30)
prism = BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, 10))
prism.Build()
base_solid = prism.Shape()

# Find top face
face_map = TopTools_IndexedMapOfShape()
TopExp.MapShapes_s(base_solid, TopAbs_FACE, face_map)
top_face = None
for i in range(1, face_map.Extent() + 1):
    f = TopoDS.Face_s(face_map.FindKey(i))
    props = GProp_GProps()
    BRepGProp_mod.BRepGProp.SurfaceProperties_s(f, props)
    if props.CentreOfMass().Z() > 9.0:
        top_face = f

# BRepFeat
feat = BRepFeat_MakePrism(base_solid, top_face, top_face, gp_Dir(0, 0, 1), 1, True)
feat.Perform(5.0)
result_solid = feat.Shape()

# === Result maps ===
result_edge_map = TopTools_IndexedMapOfShape()
TopExp.MapShapes_s(result_solid, TopAbs_EDGE, result_edge_map)
result_face_map = TopTools_IndexedMapOfShape()
TopExp.MapShapes_s(result_solid, TopAbs_FACE, result_face_map)
print(f"Result: {result_face_map.Extent()} faces, {result_edge_map.Extent()} edges")

# === Critical test: each top-face edge's Generated output ===
print("\n--- Generated outputs for top face boundary edges ---")
exp = TopExp_Explorer(top_face, TopAbs_EDGE)
idx = 0
while exp.More():
    edge = TopoDS.Edge_s(exp.Current())
    
    # Check Modified and Generated
    mod_list = iter_list(feat.Modified(edge))
    gen_list = iter_list(feat.Generated(edge))
    
    print(f"\n  TopEdge {idx}:")
    print(f"    Modified: {len(mod_list)} items")
    for m in mod_list:
        st = m.ShapeType()
        in_edges = result_edge_map.Contains(m) if st == TopAbs_EDGE else False
        in_faces = result_face_map.Contains(m) if st == TopAbs_FACE else False
        print(f"      -> type={type_names.get(int(st), '?')} in_edges={in_edges} in_faces={in_faces}")
    
    print(f"    Generated: {len(gen_list)} items")
    for g in gen_list:
        st = g.ShapeType()
        in_edges = result_edge_map.Contains(g) if st == TopAbs_EDGE else False
        in_faces = result_face_map.Contains(g) if st == TopAbs_FACE else False
        # Check if it could pass the shape_type filter
        # In _build_brepfeat_history_mappings, source is EDGE, expected is TopAbs_EDGE
        # If Generated returns a FACE, it would be filtered out!
        print(f"      -> type={type_names.get(int(st), '?')} in_edges={in_edges} in_faces={in_faces}")
    
    # Also try Reversed
    mod_rev = iter_list(feat.Modified(edge.Reversed()))
    gen_rev = iter_list(feat.Generated(edge.Reversed()))
    if mod_rev or gen_rev:
        print(f"    Reversed: Modified={len(mod_rev)} Generated={len(gen_rev)}")
        for r in mod_rev + gen_rev:
            st = r.ShapeType()
            print(f"      -> type={type_names.get(int(st), '?')}")
    
    exp.Next()
    idx += 1

# === Check the Face itself ===
print(f"\n--- Top face history ---")
print(f"  IsDeleted: {feat.IsDeleted(top_face)}")
mod_face = iter_list(feat.Modified(top_face))
gen_face = iter_list(feat.Generated(top_face))
print(f"  Modified: {len(mod_face)}")
print(f"  Generated: {len(gen_face)}")
for g in gen_face:
    st = g.ShapeType()
    in_faces = result_face_map.Contains(g) if st == TopAbs_FACE else False
    print(f"    -> type={type_names.get(int(st), '?')} in_faces={in_faces}")
