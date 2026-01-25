"""
Debug: Warum funktioniert die Segmentierung nicht bei verrunden.stl?
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import pyvista as pv
from collections import defaultdict
from scipy.sparse import lil_matrix
from scipy.sparse.csgraph import connected_components


def debug_segmentation(stl_path: str):
    """Analysiert die Mesh-Segmentierung im Detail."""

    print("=" * 60)
    print(f"Debug Segmentierung: {Path(stl_path).name}")
    print("=" * 60)

    mesh = pv.read(stl_path)
    print(f"Mesh: {mesh.n_cells} Faces, {mesh.n_points} Vertices")

    mesh = mesh.compute_normals(cell_normals=True)
    normals = mesh.cell_data['Normals']

    # Edge-Face Map
    edge_to_faces = defaultdict(list)
    for face_id in range(mesh.n_cells):
        cell = mesh.get_cell(face_id)
        pts = cell.point_ids
        for i in range(len(pts)):
            edge = tuple(sorted([pts[i], pts[(i + 1) % len(pts)]]))
            edge_to_faces[edge].append(face_id)

    print(f"\nKanten gesamt: {len(edge_to_faces)}")

    # Analysiere alle Kanten
    manifold_edges = 0
    boundary_edges = 0
    non_manifold_edges = 0

    for edge, faces in edge_to_faces.items():
        if len(faces) == 1:
            boundary_edges += 1
        elif len(faces) == 2:
            manifold_edges += 1
        else:
            non_manifold_edges += 1

    print(f"  Manifold (2 Faces): {manifold_edges}")
    print(f"  Boundary (1 Face):  {boundary_edges}")
    print(f"  Non-manifold (>2):  {non_manifold_edges}")

    # Teste verschiedene Thresholds
    thresholds = [30, 40, 50, 60, 70, 80, 90]

    print("\nRegionen bei verschiedenen Sharp-Edge-Thresholds:")
    print("-" * 50)

    for threshold in thresholds:
        sharp_threshold = np.radians(threshold)

        # Finde scharfe Kanten
        sharp_edges = set()
        for edge, face_ids in edge_to_faces.items():
            if len(face_ids) != 2:
                sharp_edges.add(edge)
                continue

            f1, f2 = face_ids
            n1, n2 = normals[f1], normals[f2]
            dot = np.clip(np.dot(n1, n2), -1, 1)
            angle = np.arccos(dot)

            if angle > sharp_threshold:
                sharp_edges.add(edge)

        # Segmentiere
        n_faces = mesh.n_cells
        adjacency = lil_matrix((n_faces, n_faces), dtype=np.int8)

        for edge, face_ids in edge_to_faces.items():
            if len(face_ids) == 2 and edge not in sharp_edges:
                f1, f2 = face_ids
                adjacency[f1, f2] = 1
                adjacency[f2, f1] = 1

        n_components, labels = connected_components(
            adjacency.tocsr(), directed=False, return_labels=True
        )

        # Zähle Faces pro Region
        region_sizes = []
        for label_id in range(n_components):
            size = np.sum(labels == label_id)
            region_sizes.append(size)

        region_sizes.sort(reverse=True)

        print(f"  {threshold}°: {len(sharp_edges):3d} scharfe Kanten → "
              f"{n_components:2d} Regionen "
              f"(Größen: {region_sizes[:5]}{'...' if len(region_sizes) > 5 else ''})")

    # Für den besten Threshold (der ~6 Hauptflächen + 5 Fillets = 11 Regionen gibt)
    print("\n" + "=" * 60)
    print("Detail-Analyse bei 80° Threshold:")
    print("=" * 60)

    sharp_threshold = np.radians(80)
    sharp_edges = set()
    sharp_edge_angles = []

    for edge, face_ids in edge_to_faces.items():
        if len(face_ids) != 2:
            continue

        f1, f2 = face_ids
        n1, n2 = normals[f1], normals[f2]
        dot = np.clip(np.dot(n1, n2), -1, 1)
        angle = np.arccos(dot)

        if angle > sharp_threshold:
            sharp_edges.add(edge)
            sharp_edge_angles.append(np.degrees(angle))

    print(f"Scharfe Kanten (>80°): {len(sharp_edges)}")
    if sharp_edge_angles:
        print(f"Winkel-Range: {min(sharp_edge_angles):.1f}° - {max(sharp_edge_angles):.1f}°")

    # Segmentierung
    n_faces = mesh.n_cells
    adjacency = lil_matrix((n_faces, n_faces), dtype=np.int8)

    soft_edges_count = 0
    for edge, face_ids in edge_to_faces.items():
        if len(face_ids) == 2 and edge not in sharp_edges:
            f1, f2 = face_ids
            adjacency[f1, f2] = 1
            adjacency[f2, f1] = 1
            soft_edges_count += 1

    print(f"Weiche Kanten (Verbindungen): {soft_edges_count}")

    n_components, labels = connected_components(
        adjacency.tocsr(), directed=False, return_labels=True
    )

    print(f"\nRegionen: {n_components}")
    for label_id in range(min(n_components, 15)):
        face_ids = np.where(labels == label_id)[0]
        size = len(face_ids)

        # Analysiere diese Region
        region_normals = normals[face_ids]
        avg_normal = np.mean(region_normals, axis=0)
        avg_normal = avg_normal / np.linalg.norm(avg_normal)

        # Varianz der Normalen
        dots = np.dot(region_normals, avg_normal)
        normal_variance = 1 - np.mean(dots)

        if normal_variance < 0.01:
            region_type = "PLANAR"
        elif normal_variance < 0.2:
            region_type = "CURVED (Fillet?)"
        else:
            region_type = "MIXED"

        print(f"  Region {label_id}: {size:3d} Faces, "
              f"Normal-Varianz={normal_variance:.4f} → {region_type}")


if __name__ == "__main__":
    stl_dir = Path(__file__).parent.parent / "stl"

    for stl_file in ["verrunden.stl", "fase.stl"]:
        path = stl_dir / stl_file
        if path.exists():
            debug_segmentation(str(path))
            print("\n\n")
