"""Debug V1 STL Mesh-Struktur."""
from loguru import logger
import sys
import numpy as np

logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | {message}", level="INFO")

import pyvista as pv

# Mesh laden
mesh = pv.read('stl/V1.stl')
print(f"Punkte: {mesh.n_points}")
print(f"Faces: {mesh.n_cells}")
print(f"Bounds: {mesh.bounds}")

# Normalen berechnen
mesh.compute_normals(cell_normals=True, inplace=True)
normals = mesh.cell_data['Normals']

# Finde Faces mit Normale nach oben (Z+)
up_normal = np.array([0, 0, 1])
dots = np.dot(normals, up_normal)
top_faces = np.where(dots > 0.99)[0]
print(f"\nFaces mit Normale nach oben (Z+): {len(top_faces)}")

# Analysiere die Top-Faces
if len(top_faces) > 0:
    faces_array = mesh.faces.reshape(-1, 4)[:, 1:4]
    top_triangles = faces_array[top_faces]

    # Finde alle Punkte der Top-Faces
    top_point_ids = np.unique(top_triangles.flatten())
    top_points = mesh.points[top_point_ids]

    print(f"Punkte in Top-Faces: {len(top_point_ids)}")
    print(f"Z-Koordinaten der Top-Punkte: min={top_points[:, 2].min():.4f}, max={top_points[:, 2].max():.4f}")

    # Prüfe ob alle Top-Punkte auf gleicher Z-Höhe
    z_variance = np.var(top_points[:, 2])
    print(f"Z-Varianz: {z_variance:.6f}")

    if z_variance < 1e-6:
        print("→ Alle Top-Punkte sind koplanar (gut)")
    else:
        print("→ Top-Punkte sind NICHT koplanar (Problem!)")

# Visualisiere die Top-Faces
print("\nErstelle Visualisierung...")
top_mesh = mesh.extract_cells(top_faces)
top_mesh.save('debug_v1_top_faces.vtk')
print("Gespeichert: debug_v1_top_faces.vtk")
