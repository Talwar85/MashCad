"""Debug V2 Zylinder-Problem."""
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="DEBUG")

from meshconverter.hybrid_mesh_converter import HybridMeshConverter
from meshconverter.mesh_converter_v10 import MeshLoader

print("=" * 60)
print("DEBUG V2 ZYLINDER")
print("=" * 60)

# Mesh laden
load_result = MeshLoader.load('stl/V2.stl', repair=True)
mesh = load_result.mesh

print(f"Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

# Konverter
converter = HybridMeshConverter()

# Normalen
if 'Normals' not in mesh.cell_data:
    mesh.compute_normals(cell_normals=True, inplace=True)

# Zylinder erkennen
cylinders = converter._detect_cylinders(mesh)
print(f"\n{len(cylinders)} Zylinder erkannt:")

for i, cyl in enumerate(cylinders):
    print(f"\n--- Zylinder {i+1} ---")
    print(f"  Radius: {cyl['radius']:.3f} mm")
    print(f"  Height: {cyl['height']:.3f} mm")
    print(f"  Center: {cyl['center']}")
    print(f"  Axis: {cyl['axis']}")
    print(f"  v_min: {cyl['v_min']:.3f}, v_max: {cyl['v_max']:.3f}")
    print(f"  Cells: {len(cyl['cell_ids'])}")
    print(f"  Error: {cyl['error']:.4f} mm")

    # Boundary-Edges finden
    boundary_edges = converter._find_region_boundary_edges(mesh, cyl['cell_ids'])
    print(f"  Boundary-Edges: {len(boundary_edges)}")

    # Edge-Loops
    edge_loops = converter._sort_edges_to_loops(boundary_edges)
    print(f"  Edge-Loops: {len(edge_loops)}")
    for j, loop in enumerate(edge_loops):
        print(f"    Loop {j+1}: {len(loop)} Kanten")

# Versuche Konvertierung ohne Boundary-Methode (nur parametrisch)
print("\n" + "=" * 60)
print("Test: Nur parametrische Zylinder (ohne Mesh-Boundary)")
print("=" * 60)

# Temporär die Boundary-Methode überspringen
original_method = converter._create_cylinder_face_with_boundary
converter._create_cylinder_face_with_boundary = lambda *args, **kwargs: None

result = converter.convert(mesh)
print(f"Status: {result.status.name}")
print(f"Stats: {result.stats}")

# Restore
converter._create_cylinder_face_with_boundary = original_method
