"""Debug V1.stl Validierungsfehler."""
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="DEBUG")

from meshconverter.hybrid_mesh_converter import HybridMeshConverter
from meshconverter.mesh_converter_v10 import MeshLoader, LoadStatus, ConversionStatus

print("=" * 60)
print("DEBUG V1.stl")
print("=" * 60)

# Mesh laden
load_result = MeshLoader.load('stl/V1.stl', repair=True)
mesh = load_result.mesh

print(f"Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

# Konvertieren mit Debug
converter = HybridMeshConverter()

# Normalen berechnen
if 'Normals' not in mesh.cell_data:
    mesh.compute_normals(cell_normals=True, inplace=True)

# Zylinder erkennen
cylinders = converter._detect_cylinders(mesh)
print(f"\n{len(cylinders)} Zylinder erkannt:")
for i, cyl in enumerate(cylinders):
    print(f"  Zylinder {i+1}: r={cyl['radius']:.2f}mm, h={cyl['height']:.2f}mm, "
          f"error={cyl['error']:.3f}mm, {len(cyl['cell_ids'])} Cells")

# Vertices und Edge-Map
vertices = converter._create_vertex_pool(mesh)
edge_map = converter._create_edge_map(mesh, vertices)

print(f"\n{len(edge_map)} unique Edges")

# Test: Erstelle Zylinder-Face für jeden erkannten Zylinder
print("\nZylinder-Face Erstellung:")
for i, cyl in enumerate(cylinders):
    face = converter._create_cylinder_face_with_boundary(cyl, mesh, vertices, edge_map)
    if face is not None:
        print(f"  Zylinder {i+1}: OK")
    else:
        face = converter._create_cylinder_face(cyl)
        if face is not None:
            print(f"  Zylinder {i+1}: OK (Fallback)")
        else:
            print(f"  Zylinder {i+1}: FEHLER")

# Vollständige Konvertierung
print("\nVollständige Konvertierung:")
result = converter.convert(mesh)
print(f"Status: {result.status.name}")
print(f"Stats: {result.stats}")
if result.message:
    print(f"Message: {result.message}")

# Wenn Solid vorhanden, prüfe Details
if result.solid is not None:
    from OCP.BRepCheck import BRepCheck_Analyzer, BRepCheck_Status
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE

    analyzer = BRepCheck_Analyzer(result.solid)
    print(f"\nBRepCheck_Analyzer.IsValid(): {analyzer.IsValid()}")

    # Prüfe Faces
    exp = TopExp_Explorer(result.solid, TopAbs_FACE)
    face_idx = 0
    while exp.More():
        face = exp.Current()
        face_status = analyzer.Result(face)
        if face_status:
            # Check status
            status_list = face_status.Status()
            if status_list.Size() > 0:
                first_status = status_list.First()
                if first_status != BRepCheck_Status.BRepCheck_NoError:
                    print(f"  Face {face_idx}: Status = {first_status}")
        face_idx += 1
        exp.Next()

    print(f"\n{face_idx} Faces in Solid")
