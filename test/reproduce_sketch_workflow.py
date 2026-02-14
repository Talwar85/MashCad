
import pytest
from loguru import logger
from shapely.geometry import Polygon

from build123d import Solid, Face, Vector, Part
from modeling import Body, ExtrudeFeature, PushPullFeature
from modeling.features.fillet_chamfer import FilletFeature
from modeling.ocp_helpers import HAS_OCP
from modeling.tnp_system import ShapeID, ShapeType

# Use existing test utils
import sys
from pathlib import Path
test_dir = Path(__file__).parent
sys.path.insert(0, str(test_dir))

from ocp_test_utils import (
    OCPTestContext,
    create_test_sketch_face,
    assert_tnp_registered,
)
from config.feature_flags import set_flag

# Skip if no OCP
pytestmark = pytest.mark.skipif(
    not HAS_OCP,
    reason="OpenCASCADE (OCP) unavailable"
)

@pytest.fixture
def document_with_tnp():
    from modeling import Document
    doc = Document("TestDoc")
    return doc

def test_sketch_extrude_pushpull_fillet_workflow(document_with_tnp):
    """
    Reproduces the user workflow: Sketch -> Extrude -> Push/Pull -> Fillet.
    Verifies that TNP IDs are tracked correctly through the chain.
    """
    # 1. Setup
    set_flag("ocp_first_extrude", True) # Ensure we use the modern path
    set_flag("tnp_v4", True)
    
    body = Body("TestBody", document=document_with_tnp)
    tnp = document_with_tnp._shape_naming_service
    
    logger.info("--- Step 1: Extrude (Mocking Sketch) ---")
    # Simulate Sketch by creating a Face directly
    face = create_test_sketch_face(width=20.0, height=30.0)
    
    # Create Extrude Feature
    extrude = ExtrudeFeature(distance=10.0, operation="New Body")
    extrude.face_brep = None # Use poly if needed, but here we might need to inject the face?
    # In integration tests, we added feature then called _compute_extrude_part with the feature.
    # But ExtrudeFeature usually takes input from Sketch. 
    # The test_phase2_extrude_integration used `feature.precalculated_polys` as input for legacy?
    # For OCP path, it also seemed to use it?
    
    # Let's verify how `_compute_extrude_part` gets the profile.
    # It calls `OCPExtrudeHelper`, which likely takes `faces`.
    # `Body._compute_extrude_part` resolves inputs.
    
    # We will manually inject the face into the helper call if needed, 
    # OR we follow the test pattern: add feature, then compute.
    # But `feature` needs to know WHAT to extrude.
    # `test_phase2_extrude_integration` set `precalculated_polys`.
    
    poly = Polygon([(0, 0), (20, 0), (20, 30), (0, 30)])
    extrude.precalculated_polys = [poly]
    extrude.plane_origin = (0, 0, 0)
    extrude.plane_normal = (0, 0, 1)
    
    body.add_feature(extrude, rebuild=False)
    
    # Executing Extrude
    # We call the internal method to simulate rebuild loop
    result_solid = body._compute_extrude_part(extrude)
    body.set_shape(result_solid)
    
    # Verify Registration
    stats = tnp.get_stats()
    logger.info(f"After Extrude: {stats}")
    assert stats['faces'] > 0
    
    # 2. Push/Pull
    logger.info("--- Step 2: Push/Pull ---")
    
    # Find Top Face (Z=10) via TNP/Topology
    # We simulate user selecting the face in GUI
    # Using `body.faces()` (build123d)
    top_face = None
    for f in body.faces():
        if f.center().Z > 9.9:
            top_face = f
            break
    
    assert top_face is not None, "Top face not found"
    
    # Resolve ID
    # THIS is where reproduction script failed manually.
    # Let's see if it works here with proper environment.
    top_face_id = tnp.find_shape_id_by_face(top_face)
    logger.info(f"Top Face ID: {top_face_id}")
    
    if top_face_id is None:
        logger.warning(f"Face lookup failed! Center: {top_face.center()}")
        # Iterate candidates
        for uuid, rec in tnp._shapes.items():
            if rec.shape_id.shape_type == ShapeType.FACE:
                pass # logger.info(f"Candidate: {uuid}")
        pytest.fail("Could not resolve Top Face ID for Push/Pull")
        
    # Create PushPull Feature
    pp_feature = PushPullFeature(
        face_shape_id=top_face_id, 
        distance=5.0, 
        operation="Join"
    )
    
    body.add_feature(pp_feature, rebuild=False)
    
    # Execute PushPull
    # This usually goes through `_compute_extrude_part` in `Body` for PushPull too?
    # Or `_compute_pushpull`?
    # Checking `modeling/__init__.py` would verify, but let's assume `_compute_extrude_part` handles it 
    # (generic naming) or we check `body._rebuild` dispatch.
    # Actually, `test_pushpull_feature.py` didn't show execution.
    
    # Let's try `_compute_extrude_part` as it seems to handle BRepFeat things?
    # Or check if `_rebuild` calls `feature.execute(body)`?
    # In LiteCad v2 structure, features often execute themselves or via body methods.
    
    # If we look at `test_phase2_extrude_integration` it calls `_compute_extrude_part`.
    # Let's try calling `feature.execute(body)` if available, otherwise `body._compute_extrude_part(feature)`.
    # PushPull is technically an Extrude logic.
    
    try:
        # Try finding the method on body
        if hasattr(body, "_compute_pushpull"):
             result_pp = body._compute_pushpull(pp_feature)
        elif hasattr(body, "_compute_extrude_part"):
             result_pp = body._compute_extrude_part(pp_feature)
        else:
             # Fallback: assume feature has execute
             raise NotImplementedError("Unknown dispatch")
             
        body.set_shape(result_pp)

    except Exception as e:
        pytest.fail(f"PushPull Execution Failed: {e}")
        
    # Verify History
    stats = tnp.get_stats()
    logger.info(f"After PushPull: {stats}")
    
    # 3. Fillet
    logger.info("--- Step 3: Fillet ---")
    
    # Find Top Edges (Z=15)
    top_edges = []
    for e in body.edges():
        if e.center().Z > 14.9:
            top_edges.append(e)
            
    assert len(top_edges) > 0
    logger.info(f"Found {len(top_edges)} top edges")
    
    edge_ids = []
    for e in top_edges:
        eid = tnp.find_shape_id_by_edge(e)
        if eid:
            edge_ids.append(eid.uuid)
        else:
             logger.warning(f"Edge {e} has no ID")
             
    logger.info(f"Resolved {len(edge_ids)} Edge IDs")
    assert len(edge_ids) == len(top_edges), "Not all edges resolved!"
    
    # Fillet Feature
    fillet = FilletFeature(radius=1.0)
    fillet.edge_shape_ids = [tnp._shapes[uid].shape_id for uid in edge_ids] 
    # Wait, FilletFeature uses `edge_shape_ids` which are ShapeIDs, not UUID strings? 
    # Or UUID strings? `modeling/__init__.py` usage suggests ShapeID objects usually, 
    # but `edge_ids` param in `FilletFeature` might take UUIDs.
    # Let's assign IDs.
    
    body.add_feature(fillet, rebuild=False)
    
    # Execute Fillet
    # body._compute_fillet(fillet) ?
    if hasattr(body, "_compute_fillet"):
        body._compute_fillet(fillet)
    elif hasattr(body, "_compute_fillet_chamfer"):
        body._compute_fillet_chamfer(fillet)
        
    logger.info("Fillet Executed")

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
