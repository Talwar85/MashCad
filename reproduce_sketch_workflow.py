
import sys
import os
import math
from loguru import logger

# Context
sys.path.append(os.getcwd())

# Mock environment
from modeling import Body
from modeling.tnp_system import ShapeNamingService
from modeling.features.fillet_chamfer import FilletFeature
from config.feature_flags import set_flag

# Import OCP
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeEdge
from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Pln
from OCP.GC import GC_MakeSegment
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.TopoDS import TopoDS
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE

# Enable Flags
set_flag("tnp_debug_logging", True)
set_flag("tnp_v4", True)

class MockDocument:
    def __init__(self):
        self._shape_naming_service = ShapeNamingService()
        # self.history_manager = HistoryManager() # Removed
        self.feature_manager = self
        self.features = []

def make_rectangle_face(w, h):
    # Rectangle centered at 38, 56?
    # Log: origin=(38.0, 56.0, 0.0), x_dir=(0, -1, 0)...
    # Let's simple start at 0,0 for reproducibility unless coordinates matter for hash
    # Log geometry hash varies, so coordinates matter.
    # But for history tracking mechanics, strict equality matters.
    
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

def run_reproduction():
    logger.info("=== Sketch Workflow Reproduction ===")
    
    doc = MockDocument()
    body = Body("TestBody")
    body._document = doc
    tnp = doc._shape_naming_service
    
    # 1. Simulate Extrude (Base)
    logger.info("--- Step 1: Simulate Extrude ---")
    face = make_rectangle_face(20, 30)
    prism = BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, 10))
    prism.Build()
    base_solid = prism.Shape()
    
    # Manually register base solid
    logger.info("Registering Base Solid...")
    
    # Register Faces
    expl = TopExp_Explorer(base_solid, TopAbs_FACE)
    idx = 0
    while expl.More():
        f = expl.Current()
        tnp.register_shape(f, "FACE", "Extrude1", idx)
        expl.Next()
        idx += 1
        
    # Register Edges
    expl = TopExp_Explorer(base_solid, TopAbs_EDGE)
    idx = 0
    while expl.More():
        e = expl.Current()
        tnp.register_shape(e, "EDGE", "Extrude1", idx)
        expl.Next()
        idx += 1
        
    logger.info(f"Registry: {len(tnp._shapes)} shapes")
    
    # 2. Push/Pull
    logger.info("--- Step 2: Push/Pull ---")
    
    # Find Top Face (Z=10)
    from modeling.topology_indexing import iter_faces_with_indices
    target_face = None
    target_face_id = None
    
    # Use internal topology helper to ensure we match app logic
    face_map = []
    for f in iter_faces_with_indices(base_solid):
        # f is (index, face_obj)
        # Wait, iter_faces_with_indices returns iterator of (index, Face)
        # build123d Face wrapper
        b3d_face = f[1]
        if b3d_face.center().Z > 9.0:
            target_face = b3d_face
            break
            
    if not target_face:
        logger.error("Top Face not found!")
        return

    logger.info(f"Target Face found: {target_face}")
    
    # Resolve ID
    # find_shape_id_by_face expects a build123d object to use .center()
    target_face_id = tnp.find_shape_id_by_face(target_face)
    logger.info(f"Target Face ID: {target_face_id}")
    
    if not target_face_id:
        logger.warning(f"Face ID not found! Target Face Center: {target_face.center()}")
        logger.warning("Dumping Registry Candidates:")
        for uuid, record in tnp._shapes.items():
            if record.shape_id.shape_type == "FACE": # Check enum or string?
                 # ShapeType is enum.
                 pass
        
        # Iterate spatial index
        from modeling.tnp_system import ShapeType
        for pos, sid in tnp._spatial_index[ShapeType.FACE]:
            logger.info(f"  Candidate: {sid.uuid} at {pos}")
            
        return

    # Execute BRepFeat_MakePrism manually
    logger.info("Executing BRepFeat_MakePrism...")
    
    # Extract native face
    native_face = target_face.wrapped
    
    # Create Prism
    from OCP.BRepFeat import BRepFeat_MakePrism
    
    # We need the Shape object (base_solid)
    feat = BRepFeat_MakePrism(base_solid, native_face, native_face, 1, 0, 0) # fuse=1, modify=0?
    # Arguments: (S, Pbase, Pne, Fuse, Modify)
    # 1=Fuse, 0=Modify?
    # Let's check constructor signature or assume standard usage
    # Actually simpler usage: Init(S, Pbase, ...)
    
    feat = BRepFeat_MakePrism(base_solid, native_face, native_face, 1, 0, 1) # modify=1?
    # Wait, BRepFeat_MakePrism usage is complex.
    # Let's use BRepPrimAPI_MakePrism on the face and Fuse it?
    # No, we want to test BRepFeat HISTORY tracking.
    
    # Simpler: MakePrism from TopoDS_Shape (Face)
    # But BRepFeat maintains history relative to the Base Shape.
    
    # Let's try to pass the face and vector.
    feat.Perform(gp_Vec(0, 0, 5))
    
    if not feat.IsDone():
        logger.error("BRepFeat failed")
        return
        
    result_solid = feat.Shape()
    
    # Track History using TNP System
    logger.info("Tracking History...")
    
    # Inputs: List of (ShapeID, Shape)
    inputs = [(target_face_id, native_face)] # We pass the native face used for operation
    
    try:
        tnp.track_brepfeat_operation(
            feature_id="PushPull1",
            operation=feat, # The BRepFeat object with history
            original_solid=base_solid,
            result_solid=result_solid,
            inputs=inputs
        )
        logger.info("Tracking Successful")
    except Exception as e:
        logger.exception(f"Tracking Failed: {e}")

    # 3. Fillet (Simulated)
    # We check if edges of the NEW solid can be resolved.
    logger.info("--- Step 3: Check Result Edges for Fillet ---")
    
    # Find edges at top (Z=15)
    expl = TopExp_Explorer(result_solid, TopAbs_EDGE)
    count = 0
    resolved = 0
    while expl.More():
        e = expl.Current()
        # Check Z
        import OCP.BRepGProp as BRepGProp
        from OCP.GProp import GProp_GProps
        props = GProp_GProps()
        BRepGProp.BRepGProp_LinearProperties(e, props)
        z = props.CentreOfMass().Z
        
        if z > 14.0:
            count += 1
            # Try resolve
            sid = tnp.find_shape_id_by_edge(e)
            if sid:
                resolved += 1
                logger.info(f"Resolved Top Edge: {sid.uuid}")
            else:
                logger.warning(f"Unresolved Top Edge at Z={z}")
                
        expl.Next()
        
    logger.info(f"Top Edges: {count}, Resolved: {resolved}")
    if resolved < count:
        logger.error("Fillet would fail! Unresolved edges.")


if __name__ == "__main__":
    run_reproduction()
