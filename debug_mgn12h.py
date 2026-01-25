"""Debug MGN12H_X_Carriage - warum nur 7 Faces?"""
from loguru import logger
import sys
import numpy as np

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="DEBUG")

import pyvista as pv

# Mesh laden
mesh = pv.read('stl/MGN12H_X_Carriage_Lite (1).stl')
print(f"Punkte: {mesh.n_points}")
print(f"Faces: {mesh.n_cells}")
print(f"Bounds: {mesh.bounds}")

# Normalen berechnen
mesh.compute_normals(cell_normals=True, inplace=True)
normals = mesh.cell_data['Normals']

# Unique Normalen-Richtungen
unique_normals = np.unique(normals.round(3), axis=0)
print(f"Unique Normalen (gerundet): {len(unique_normals)}")

# Haupt-Richtungen analysieren
print("\nHaupt-Normalen-Richtungen:")
for i, n in enumerate(unique_normals[:20]):
    count = np.sum(np.all(np.abs(normals - n) < 0.01, axis=1))
    print(f"  {i+1}. {n} - {count} Faces")

# Das Problem: Bei 1° Toleranz wird ALLES gemerged wenn fast alle Normalen gleich sind!
# Prüfe ob das ein sehr flaches Teil ist
z_range = mesh.bounds[5] - mesh.bounds[4]
xy_area = (mesh.bounds[1] - mesh.bounds[0]) * (mesh.bounds[3] - mesh.bounds[2])
print(f"\nZ-Range: {z_range:.2f}mm")
print(f"XY-Area: {xy_area:.2f}mm²")
print(f"Aspect Ratio (XY/Z): {xy_area/z_range:.1f}")

# Konvertiere ohne UnifySameDomain
print("\n=== Test ohne UnifySameDomain ===")
from meshconverter.hybrid_mesh_converter import HybridMeshConverter
from meshconverter.mesh_converter_v10 import MeshLoader

load_result = MeshLoader.load('stl/MGN12H_X_Carriage_Lite (1).stl', repair=True)

# Mit sehr strenger Toleranz
converter = HybridMeshConverter(
    unify_angular_tolerance=0.1  # Nur 0.1° - quasi kein Merging
)
result = converter.convert(load_result.mesh)
print(f"Status: {result.status.name}")
print(f"Faces nach Unify: {result.stats.get('faces_after_unify', '?')}")
print(f"Faces erstellt: {result.stats.get('faces_created', '?')}")
