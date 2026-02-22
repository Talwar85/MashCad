"""Debug script for chamfer failure investigation."""
import sys
sys.path.insert(0, '.')

from modeling import Document, Body, PrimitiveFeature, ExtrudeFeature, ChamferFeature
from modeling.topology_indexing import edge_index_of
from sketcher.sketch import Sketch
from shapely.geometry import Polygon

# Enable debug logging
from config.feature_flags import set_enabled
set_enabled('tnp_debug_logging', True)

# Create doc and body
doc = Document('debug_chamfer')
body = Body('TestBody', document=doc)
doc.add_body(body, set_active=True)

# Add base box
base = PrimitiveFeature(primitive_type='box', length=40.0, width=28.0, height=18.0, name='Base Box')
body.add_feature(base, rebuild=True)
print(f'Base box: solid={body._build123d_solid is not None}')

# Add push/pull (extrude join on face)
solid = body._build123d_solid
faces = list(solid.faces())
print(f'Base solid has {len(faces)} faces, {len(list(solid.edges()))} edges')

# Pick face in +X direction
target_face = max(faces, key=lambda f: float(f.center().X))
face_idx = None
for i, f in enumerate(faces):
    if f.center().X == target_face.center().X:
        face_idx = i
        break
print(f'Target face index: {face_idx}, center: ({target_face.center().X:.2f}, {target_face.center().Y:.2f}, {target_face.center().Z:.2f})')

# Register face shape ID
from modeling.tnp_system import ShapeType
fc = target_face.center()
shape_id = doc._shape_naming_service.register_shape(
    ocp_shape=target_face.wrapped,
    shape_type=ShapeType.FACE,
    feature_id=base.id,
    local_index=face_idx,
    geometry_data=(float(fc.X), float(fc.Y), float(fc.Z), float(target_face.area))
)

# Push/pull join
poly = Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
pp = ExtrudeFeature(
    sketch=None,
    distance=2.0,
    operation='Join',
    face_index=face_idx,
    face_shape_id=shape_id,
    precalculated_polys=[poly],
    name='PushPull'
)
body.add_feature(pp, rebuild=True)
print(f'After PP: solid={body._build123d_solid is not None}, status={pp.status}')

solid = body._build123d_solid
print(f'PP solid has {len(list(solid.faces()))} faces, {len(list(solid.edges()))} edges')

# Get top edges
top_face = max(list(solid.faces()), key=lambda f: float(f.center().Z))
top_edges = list(top_face.edges())
print(f'Top face has {len(top_edges)} edges')

edge_indices = []
for edge in top_edges:
    idx = edge_index_of(solid, edge)
    if idx is not None:
        edge_indices.append(int(idx))
print(f'Top edge indices: {edge_indices[:4]}')

# Try chamfer with debug
chamfer = ChamferFeature(distance=0.8, edge_indices=edge_indices[:4], name='TestChamfer')
body.add_feature(chamfer, rebuild=True)
print(f'Chamfer status: {chamfer.status}')
print(f'Chamfer message: {chamfer.status_message}')
