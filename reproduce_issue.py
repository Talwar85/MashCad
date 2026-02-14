
import sys
import os
from loguru import logger
import math

# Ensure local imports work
sys.path.append(os.getcwd())

from modeling import Body
from modeling.tnp_system import ShapeNamingService, ShapeType, ShapeID
from config.feature_flags import set_flag

# OCP imports
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeEdge
from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax2
from OCP.GC import GC_MakeSegment
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
from OCP.BRepFeat import BRepFeat_MakePrism
from OCP.TopoDS import TopoDS

# --- Helpers (Mocking ocp_test_utils without pytest) ---

def make_rect_face(w, h):
    p1 = gp_Pnt(0, 0, 0)
    p2 = gp_Pnt(w, 0, 0)
    p3 = gp_Pnt(w, h, 0)
    p4 = gp_Pnt(0, h, 0)
    
    seg1 = GC_MakeSegment(p1, p2).Value()
    seg2 = GC_MakeSegment(p2, p3).Value()
    seg3 = GC_MakeSegment(p3, p4).Value()
    seg4 = GC_MakeSegment(p4, p1).Value()
    
    edge1 = BRepBuilderAPI_MakeEdge(seg1).Edge()
    edge2 = BRepBuilderAPI_MakeEdge(seg2).Edge()
    edge3 = BRepBuilderAPI_MakeEdge(seg3).Edge()
    edge4 = BRepBuilderAPI_MakeEdge(seg4).Edge()
    
    mw = BRepBuilderAPI_MakeWire(edge1, edge2, edge3, edge4)
    mf = BRepBuilderAPI_MakeFace(mw.Wire())
    return mf.Face()

def register_full_solid(service: ShapeNamingService, solid, feature_id):
    # Register Faces
    expl = TopExp_Explorer(solid, TopAbs_FACE)
    idx = 0
    while expl.More():
        f = expl.Current()
        # Ensure we pass geometry data to ensure uniqueness/hash
        service.register_shape(f, ShapeType.FACE, feature_id, idx)
        expl.Next()
        idx += 1
        
    # Register Edges
    expl = TopExp_Explorer(solid, TopAbs_EDGE)
    idx = 0
    while expl.More():
        e = expl.Current()
        service.register_shape(e, ShapeType.EDGE, feature_id, idx)
        expl.Next()
        idx += 1

def find_top_face(solid, z_threshold):
    expl = TopExp_Explorer(solid, TopAbs_FACE)
    best_face = None
    max_z = -float('inf')
    
    import OCP.BRepGProp as BRepGProp
    from OCP.GProp import GProp_GProps
    
    while expl.More():
        f = expl.Current()
        props = GProp_GProps()
        BRepGProp.BRepGProp.SurfaceProperties_s(f, props)
        z = props.CentreOfMass().Z()
        
        if z > max_z:
            max_z = z
            best_face = f
        expl.Next()
    
    if max_z > z_threshold:
        return best_face
    return None

def find_top_edges(solid, z_threshold):
    expl = TopExp_Explorer(solid, TopAbs_EDGE)
    edges = []
    
    import OCP.BRepGProp as BRepGProp
    from OCP.GProp import GProp_GProps
    
    while expl.More():
        e = expl.Current()
        props = GProp_GProps()
        BRepGProp.BRepGProp.LinearProperties_s(e, props)
        z = props.CentreOfMass().Z()
        
        if z > z_threshold:
            edges.append(e)
        expl.Next()
    return edges

# --- Reproduction Script ---

def start_repro():
    logger.info("=== Starting TNP Reproduction (Standalone) ===")
    
    # 1. Init
    from build123d import Face
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")
    set_flag("tnp_v4", True)
    set_flag("tnp_debug_logging", True)
    
    tnp = ShapeNamingService()
    
    # 2. Sketch -> Extrude
    logger.info("--- Step 1: Extrude ---")
    face = make_rect_face(20, 30)
    
    prism = BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, 10))
    prism.Build()
    base_solid = prism.Shape()
    
    # Register Result
    register_full_solid(tnp, base_solid, "Extrude1")
    logger.info(f"Registry after Extrude: {len(tnp._shapes)} shapes")
    
    # 3. Push/Pull (BRepFeat)
    logger.info("--- Step 2: Push/Pull ---")
    
    target_face = find_top_face(base_solid, 9.0)
    if not target_face:
        logger.error("Top Face not found!")
        return
        
    # Check ID or Register
    # Use find_shape_id_by_shape (generic OCP version)
    target_face_id = tnp.find_shape_id_by_shape(target_face, require_exact=True)
    
    if not target_face_id:
        logger.warning("Target Face Not Found. Registering explicitly (Simulating Selection)...")
        # In GUI, selection would rely on hash/geometric match.
        # Let's try find_shape_id_by_face (legacy/geometric) if exact fails?
        # But here we assume registration happened in Step 1.
        # If exact match fails, it implies `base_solid` faces are different instances than `target_face`?
        # `find_top_face` iterates `base_solid`, so they should be Same.
        
        # Let's double check why it failed in previous run.
        # Previous run used `build123d` wrapper. Here we use pure OCP.
        
        # We will forcefuly register if missing to proceed with BRepFeat test.
        target_face_id = tnp.register_shape(target_face, ShapeType.FACE, "Extrude1", 999) # 999 = ad-hoc index
    
    logger.info(f"Target Face ID: {target_face_id.uuid}")
    
    # Prepare BRepFeat
    # BRepFeat_MakePrism Init(S, Pbase, Pne, Fuse, Modify)
    # S = Base Shape
    # Pbase = Basis Face
    # Pne = Sketch Face (here same as basis face for PushPull)
    
    logger.info("Executing BRepFeat...")
    # Make sure we use TopoDS_Face
    native_face = TopoDS.Face_s(target_face)
    wrapped_face = Face(native_face)
    
    # Initialize BRepFeat
    # 1 = Fuse, 0 = Modify/New?
    # According to docs: Init(S, Pbase, Pne, Fuse, Modify)
    # We want Fuse to base.
    # Init(Sbase, Pbase, Skface, Direction, Fuse, Modify)
    dir_vec = gp_Dir(0, 0, 1)
    feat = BRepFeat_MakePrism(base_solid, native_face, native_face, dir_vec, 1, True)
    
    feat.Perform(5.0)
    
    if not feat.IsDone():
        logger.error("BRepFeat Failed")
        return
        
    result_solid = feat.Shape()
    
    result_solid = feat.Shape()
    
    # Inspect OCCT History manually
    logger.info("INSPECTING OCCT HISTORY:")
    mod_list = feat.Modified(native_face)
    logger.info(f"Modified(native_face): {mod_list.Size()} items")
    if mod_list.Size() > 0:
        it = mod_list.Iterator() # Wait, ListOfShape might be iterable directly in python? 
        # But let's check basic size first.
        pass

    gen_list = feat.Generated(native_face)
    logger.info(f"Generated(native_face): {gen_list.Size()} items")

    # Track History
    logger.info("Tracking History...")
    inputs = [(target_face_id, native_face)]
    
    try:
        tnp.track_brepfeat_operation(
            feature_id="PushPull1",
            source_solid=base_solid,
            result_solid=result_solid,
            modified_face=wrapped_face,
            direction=(0.0, 0.0, 1.0),
            distance=5.0,
            occt_history=feat
        )
        logger.info("Tracking API Call Successful")
    except Exception as e:
        logger.exception(f"Tracking API Failed: {e}")
        return

    # 4. Verification: Fillet Candidates
    logger.info("--- Step 3: Verify Fillet Candidates ---")
    
    top_edges = find_top_edges(result_solid, 14.0)
    logger.info(f"Found {len(top_edges)} top edges (Z > 14.0)")
    
    resolved_count = 0
    for e in top_edges:
        sid = tnp.find_shape_id_by_shape(e)
        if sid:
            resolved_count += 1
            # logger.info(f"Resolved: {sid.uuid}")
        else:
            logger.warning("Unresolved Top Edge!")
            
    logger.info(f"Resolved: {resolved_count}/{len(top_edges)}")
    
    if resolved_count < len(top_edges):
        logger.error("FAILURE: Some edges lost history!")
        # Dump History for one unresolved edge?
        # We can inspect `modeling/tnp_system.py` logs.
    else:
        logger.info("SUCCESS: All edges resolved!")

if __name__ == "__main__":
    start_repro()
