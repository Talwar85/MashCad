
import sys
import logging
from unittest.mock import MagicMock
import types

# Helper to mock a package and its submodules
def mock_package(name):
    parts = name.split('.')
    parent = None
    for i in range(len(parts)):
        pkg_name = '.'.join(parts[:i+1])
        if pkg_name not in sys.modules:
            m = MagicMock()
            sys.modules[pkg_name] = m
        else:
            m = sys.modules[pkg_name]
        
        if parent:
            setattr(parent, parts[i], m)
        parent = m
    return sys.modules[name]

# Mock OCP structure
ocp = mock_package('OCP')
topo_ds = mock_package('OCP.TopoDS')
top_exp = mock_package('OCP.TopExp')
top_abs = mock_package('OCP.TopAbs')
brep = mock_package('OCP.BRep')
brep_algo_api = mock_package('OCP.BRepAlgoAPI')
brep_builder_api = mock_package('OCP.BRepBuilderAPI')
brep_check = mock_package('OCP.BRepCheck')
brep_adaptor = mock_package('OCP.BRepAdaptor')
top_loc = mock_package('OCP.TopLoc')
gp = mock_package('OCP.gp')
geom = mock_package('OCP.Geom')
geom_api = mock_package('OCP.GeomAPI')
b_rep_tools = mock_package('OCP.BRepTools')
if_select = mock_package('OCP.IFSelect')
step_control = mock_package('OCP.STEPControl')
shape_fix = mock_package('OCP.ShapeFix')
shape_upgrade = mock_package('OCP.ShapeUpgrade')
shape_analysis = mock_package('OCP.ShapeAnalysis')
t_col_gp = mock_package('OCP.TColgp')
b_rep_g_prop = mock_package('OCP.BRepGProp')
g_prop = mock_package('OCP.GProp')
b_rep_prim_api = mock_package('OCP.BRepPrimAPI')

# Fix OCP attributes
ocp.gp.gp_Pnt = MagicMock
ocp.gp.gp_Vec = MagicMock
ocp.gp.gp_Dir = MagicMock
ocp.gp.gp_Ax1 = MagicMock
ocp.gp.gp_Ax2 = MagicMock
ocp.gp.gp_Ax3 = MagicMock
ocp.gp.gp_Pln = MagicMock
ocp.gp.gp_Circ = MagicMock
ocp.gp.gp_Trsf = MagicMock

ocp.TopoDS.TopoDS.Edge_s = MagicMock(return_value=MagicMock())
ocp.TopoDS.TopoDS.Face_s = MagicMock(return_value=MagicMock())
# Allow instance checks
ocp.TopoDS.TopoDS_Shape = type('TopoDS_Shape', (), {})
ocp.TopoDS.TopoDS_Face = type('TopoDS_Face', (ocp.TopoDS.TopoDS_Shape,), {})
ocp.TopoDS.TopoDS_Edge = type('TopoDS_Edge', (ocp.TopoDS.TopoDS_Shape,), {})
ocp.TopoDS.TopoDS_Vertex = type('TopoDS_Vertex', (ocp.TopoDS.TopoDS_Shape,), {})
ocp.TopoDS.TopoDS_Wire = type('TopoDS_Wire', (ocp.TopoDS.TopoDS_Shape,), {})
ocp.TopoDS.TopoDS_Shell = type('TopoDS_Shell', (ocp.TopoDS.TopoDS_Shape,), {})
ocp.TopoDS.TopoDS_Solid = type('TopoDS_Solid', (ocp.TopoDS.TopoDS_Shape,), {})
ocp.TopoDS.TopoDS_Compound = type('TopoDS_Compound', (ocp.TopoDS.TopoDS_Shape,), {})

ocp.TopAbs.TopAbs_FACE = 1
ocp.TopAbs.TopAbs_EDGE = 2
ocp.TopAbs.TopAbs_VERTEX = 3
ocp.TopAbs.TopAbs_WIRE = 4
ocp.TopAbs.TopAbs_SOLID = 5
ocp.TopAbs.TopAbs_COMPOUND = 6

# Mock mrmeshpy
mock_package('mrmeshpy')

# Mock builtins that might be missing
mock_package('shapely.geometry')
mock_package('shapely.ops')

# Mock pyvista
mock_package('pyvista')

# Mock scipy
mock_package('scipy')
mock_package('scipy.spatial')
mock_package('scipy.optimize')

# Mock sklearn
mock_package('sklearn')
mock_package('sklearn.decomposition')

# Mock build123d
mock_package('build123d')

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("TNP")

# Mock generic utils
sys.modules['utils'] = MagicMock()

# Now import the TNP system
# We need to ensure modeling package is importable
import os
sys.path.append(os.getcwd())

# Patch modeling.__init__ to avoid importing everything
import modeling
modeling.Body = MagicMock()
modeling.Document = MagicMock()

from modeling.tnp_system import ShapeNamingService as TNPSystem, ShapeType, ShapeID, OperationRecord

# Patch TNP system to avoid OCP calls during init or registration
TNPSystem._shape_exists_in_solid = MagicMock(return_value=True)

def reproduce():
    print("Initializing TNP System (ShapeNamingService)...")
    tnp = TNPSystem()

    # 1. Create a fake source solid and face
    source_solid = MagicMock()

    source_solid.wrapped = MagicMock()
    
    # Define a face that mocks TopoDS_Face
    class FakeFace:
        def ShapeType(self):
            return ocp.TopAbs.TopAbs_FACE
        def IsSame(self, other):
            return self is other
        def HashCode(self, upper):
            return 12345
            
    face1 = FakeFace()
    face1.wrapped = face1 # Mimic build123d wrapping
    
    # Register the face manually in TNP to simulate previous state
    face_uuid = "face_1234"
    
    # Populate registry manually
    sid = ShapeID(
        uuid=face_uuid,
        shape_type=ShapeType.FACE,
        feature_id="initial_feature",
        local_index=0,
        geometry_hash="hash123"
    )
    # Mocking the record
    class MockRecord:
        def __init__(self):
            self.shape_id = sid
            self.ocp_shape = face1
            self.geometric_signature = {'center': (0,0,0)}

    tnp._shapes[face_uuid] = MockRecord()
    
    print(f"Registered face with UUID: {face_uuid}")

    # 2. Simulate an operation (e.g. Fillet) that modifies this face
    
    result_solid = MagicMock()
    result_solid.wrapped = MagicMock()
    
    # New face in result
    face2 = FakeFace()
    face2.wrapped = face2
    # Different hash to simulate change
    face2.HashCode = lambda u: 67890 
    
    # 3. Setup occt_history to return face2 when asked for face1
    occt_history = MagicMock()
    
    def modified_side_effect(shape):
        if shape is face1:
            return [face2]
        return []
        
    occt_history.Modified = MagicMock(side_effect=modified_side_effect)
    occt_history.Generated = MagicMock(return_value=[])
    occt_history.IsDeleted = MagicMock(return_value=False)

    feature_id = "fillet_1"
    
    print("Running track_brepfeat_operation with HISTORY...")
    try:
        record = tnp.track_brepfeat_operation(
            feature_id=feature_id,
            source_solid=source_solid,
            result_solid=result_solid,
            modified_face=face1, # The face that was modified
            occt_history=occt_history
        )
        
        print(f"Operation recorded: {record}")
        if record:
             print(f"Manual mappings: {record.manual_mappings}")
             print(f"Mapping mode: {record.metadata.get('mapping_mode')}")
        else:
             print("No record returned!")
        
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    reproduce()
