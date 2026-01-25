"""
Debug-Test für den Surface Segmenter
"""
import numpy as np
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, level="DEBUG", format="<level>{level: <8}</level> | {message}")

import pyvista as pv

# Lade rechteck.stl
mesh = pv.read("stl/rechteck.stl")
print(f"Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")
print(f"Faces array shape: {mesh.faces.shape}")
print(f"Faces array: {mesh.faces}")
print(f"Is all triangles: {mesh.is_all_triangles}")

# Normalen
mesh.compute_normals(cell_normals=True, inplace=True)
normals = mesh.cell_data['Normals']
print(f"\nNormalen shape: {normals.shape}")
print(f"Normalen:\n{normals}")

# Unique normals (gruppiert nach Richtung)
print("\nUnique Normalen (gerundet):")
unique_normals = np.unique(np.round(normals, 2), axis=0)
for i, n in enumerate(unique_normals):
    count = np.sum(np.all(np.abs(normals - n) < 0.1, axis=1))
    print(f"  {i}: {n} ({count} faces)")

# Test Segmenter
print("\n=== Test Segmenter ===")
from meshconverter.surface_segmenter import SurfaceSegmenter

segmenter = SurfaceSegmenter(angle_tolerance=5.0, min_region_faces=1)
regions = segmenter.segment(mesh)

print(f"\nRegionen: {len(regions)}")
for r in regions:
    print(f"  Region {r.region_id}: {len(r.cell_ids)} cells, area={r.area:.2f}, normal={r.normal}")
    if r.boundary_points is not None:
        print(f"    Boundary: {len(r.boundary_points)} Punkte")
