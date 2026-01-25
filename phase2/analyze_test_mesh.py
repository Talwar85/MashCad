"""
Analysiere die Test-Meshes um die Geometrie zu verstehen.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import pyvista as pv


def analyze_mesh(stl_path: str):
    """Detaillierte Mesh-Analyse."""
    print("=" * 60)
    print(f"Analyse: {Path(stl_path).name}")
    print("=" * 60)

    mesh = pv.read(stl_path)
    print(f"Faces: {mesh.n_cells}")
    print(f"Vertices: {mesh.n_points}")

    # Bounding Box
    bounds = mesh.bounds
    size_x = bounds[1] - bounds[0]
    size_y = bounds[3] - bounds[2]
    size_z = bounds[5] - bounds[4]
    print(f"Bounding Box: {size_x:.2f} x {size_y:.2f} x {size_z:.2f} mm")

    # Normalen
    mesh = mesh.compute_normals(cell_normals=True)
    normals = mesh.cell_data['Normals']

    # Normalen-Verteilung analysieren
    unique_normals = []
    tolerance = 0.1

    for n in normals:
        is_new = True
        for un in unique_normals:
            if np.linalg.norm(n - un) < tolerance:
                is_new = False
                break
        if is_new:
            unique_normals.append(n)

    print(f"Ungefähre Anzahl unterschiedlicher Normalen-Richtungen: {len(unique_normals)}")

    # Face-Größen
    mesh_with_sizes = mesh.compute_cell_sizes()
    areas = mesh_with_sizes.cell_data['Area']
    print(f"Face-Flächen:")
    print(f"  Min: {np.min(areas):.4f} mm²")
    print(f"  Max: {np.max(areas):.4f} mm²")
    print(f"  Mean: {np.mean(areas):.4f} mm²")
    print(f"  Total: {np.sum(areas):.2f} mm²")

    # Kanten-Analyse
    from collections import defaultdict
    edge_to_faces = defaultdict(list)

    for face_id in range(mesh.n_cells):
        cell = mesh.get_cell(face_id)
        pts = cell.point_ids
        for i in range(len(pts)):
            edge = tuple(sorted([pts[i], pts[(i + 1) % len(pts)]]))
            edge_to_faces[edge].append(face_id)

    # Diederwinkel
    dihedral_angles = []
    for edge, face_ids in edge_to_faces.items():
        if len(face_ids) == 2:
            n1 = normals[face_ids[0]]
            n2 = normals[face_ids[1]]
            dot = np.clip(np.dot(n1, n2), -1, 1)
            angle = np.degrees(np.arccos(dot))
            dihedral_angles.append(angle)

    dihedral_angles = np.array(dihedral_angles)

    print(f"\nDiederwinkel-Verteilung:")
    print(f"  Min: {np.min(dihedral_angles):.1f}°")
    print(f"  Max: {np.max(dihedral_angles):.1f}°")
    print(f"  Mean: {np.mean(dihedral_angles):.1f}°")

    # Histogramm
    bins = [0, 5, 10, 20, 30, 45, 60, 90, 120, 150, 180]
    hist, _ = np.histogram(dihedral_angles, bins=bins)
    print(f"\n  Verteilung:")
    for i in range(len(bins)-1):
        if hist[i] > 0:
            print(f"    {bins[i]:3d}° - {bins[i+1]:3d}°: {hist[i]} Kanten")

    # Feature-Kanten (>20° und <160°)
    feature_edges = np.sum((dihedral_angles > 20) & (dihedral_angles < 160))
    print(f"\n  Feature-Kanten (20°-160°): {feature_edges}")

    # Sharp edges (>80°)
    sharp_edges = np.sum(dihedral_angles > 80)
    print(f"  Scharfe Kanten (>80°): {sharp_edges}")

    return mesh


if __name__ == "__main__":
    stl_dir = Path(__file__).parent.parent / "stl"

    for stl_file in ["verrunden.stl", "fase.stl"]:
        path = stl_dir / stl_file
        if path.exists():
            analyze_mesh(str(path))
            print("\n")
