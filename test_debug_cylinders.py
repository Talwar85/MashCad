"""Debug Zylinder-Erkennung."""
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="DEBUG")

from meshconverter.direct_mesh_converter import DirectMeshConverter
from meshconverter.mesh_converter_v10 import MeshLoader
from meshconverter.brep_optimizer import optimize_brep

# Teste nur MGN12H
print("Lade MGN12H...")
load_result = MeshLoader.load('stl/MGN12H_X_Carriage_Lite (1).stl', repair=True)
print(f"Mesh: {load_result.mesh.n_points} Punkte, {load_result.mesh.n_cells} Faces")

print("\nKonvertiere zu BREP...")
converter = DirectMeshConverter(unify_faces=False)
result = converter.convert(load_result.mesh)
print(f"Status: {result.status.name}")

if result.solid:
    print("\nOptimiere BREP...")
    optimized, stats = optimize_brep(result.solid)
    print(f"\nFaces: {stats['faces_before']} → {stats['faces_after']}")
    print(f"Zylinder: {stats['cylinders_detected']}")
