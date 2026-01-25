"""Debug: Warum werden Fillets als Chamfers klassifiziert?"""
import numpy as np
from pathlib import Path
import pyvista as pv
from collections import defaultdict
from scipy.sparse import lil_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.cluster import AgglomerativeClustering


def debug_fillet_detection(stl_path: str):
    print("=" * 60)
    print(f"Debug: {Path(stl_path).name}")
    print("=" * 60)

    mesh = pv.read(stl_path)
    mesh = mesh.compute_normals(cell_normals=True)
    cell_normals = mesh.cell_data['Normals']

    # Edge-Face Map
    edge_to_faces = defaultdict(list)
    for face_id in range(mesh.n_cells):
        cell = mesh.get_cell(face_id)
        pts = cell.point_ids
        for i in range(len(pts)):
            edge = tuple(sorted([pts[i], pts[(i + 1) % len(pts)]]))
            edge_to_faces[edge].append(face_id)

    # Flächen
    mesh_with_areas = mesh.compute_cell_sizes()
    areas = mesh_with_areas.cell_data['Area']
    total_area = np.sum(areas)

    # Clustere Normalen
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=1 - np.cos(np.radians(30.0)),
        metric='cosine',
        linkage='average'
    )
    labels = clustering.fit_predict(cell_normals)

    # Gruppiere
    clusters = defaultdict(set)
    for face_id, label in enumerate(labels):
        clusters[label].add(face_id)

    # Finde Hauptflächen
    main_face_ids = set()
    for cluster_faces in clusters.values():
        cluster_area = sum(areas[fid] for fid in cluster_faces)
        if cluster_area / total_area >= 0.02:
            # Prüfe Planarität
            points = []
            for fid in cluster_faces:
                cell = mesh.get_cell(fid)
                points.extend(cell.points)
            points = np.unique(np.array(points), axis=0)

            centroid = np.mean(points, axis=0)
            centered = points - centroid
            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            normal = Vt[-1]
            plane_error = np.mean(np.abs(np.dot(centered, normal)))

            if plane_error < 1.0:
                main_face_ids.update(cluster_faces)

    feature_face_ids = set(range(mesh.n_cells)) - main_face_ids
    print(f"Hauptflächen: {len(main_face_ids)}, Features: {len(feature_face_ids)}")

    # Segmentiere Feature-Faces
    if not feature_face_ids:
        return

    face_list = list(feature_face_ids)
    face_to_idx = {f: i for i, f in enumerate(face_list)}
    n = len(face_list)
    adjacency = lil_matrix((n, n), dtype=np.int8)

    for edge, faces in edge_to_faces.items():
        if len(faces) != 2:
            continue
        f1, f2 = faces
        if f1 not in feature_face_ids or f2 not in feature_face_ids:
            continue

        n1, n2 = cell_normals[f1], cell_normals[f2]
        dot = np.clip(np.dot(n1, n2), -1, 1)
        if np.arccos(dot) <= np.radians(30.0):
            i1, i2 = face_to_idx[f1], face_to_idx[f2]
            adjacency[i1, i2] = 1
            adjacency[i2, i1] = 1

    n_components, labels = connected_components(adjacency.tocsr(), directed=False, return_labels=True)

    print(f"\n{n_components} Feature-Regionen:")
    print("-" * 60)

    for label_id in range(n_components):
        indices = np.where(labels == label_id)[0]
        region = {face_list[i] for i in indices}

        if len(region) < 2:
            continue

        # Sammle Punkte
        points = []
        for fid in region:
            cell = mesh.get_cell(fid)
            points.extend(cell.points)
        points = np.unique(np.array(points), axis=0)

        print(f"\nRegion {label_id+1}: {len(region)} Faces, {len(points)} Punkte")

        # Plane-Fit
        centroid = np.mean(points, axis=0)
        centered = points - centroid
        U, S, Vt = np.linalg.svd(centered, full_matrices=False)
        plane_normal = Vt[-1]
        plane_error = np.mean(np.abs(np.dot(centered, plane_normal)))

        print(f"  Plane-Fit: error={plane_error:.4f}mm")

        # Zylinder-Fit
        try:
            # Achse = Richtung mit größter Varianz
            axis = Vt[0]

            # Radius
            proj = np.dot(centered, axis)[:, np.newaxis] * axis
            perp = centered - proj
            distances = np.linalg.norm(perp, axis=1)
            radius = np.median(distances)

            cyl_error = np.mean(np.abs(distances - radius))

            print(f"  Zylinder-Fit: radius={radius:.2f}mm, error={cyl_error:.4f}mm")

            # Bogenwinkel
            x_local = np.cross(axis, [0, 0, 1]) if abs(axis[2]) < 0.9 else np.cross(axis, [1, 0, 0])
            x_local = x_local / np.linalg.norm(x_local)
            y_local = np.cross(axis, x_local)

            angles = []
            for rel in centered:
                h = np.dot(rel, axis)
                p = rel - h * axis
                if np.linalg.norm(p) > 1e-6:
                    pn = p / np.linalg.norm(p)
                    angles.append(np.arctan2(np.dot(pn, y_local), np.dot(pn, x_local)))

            if angles:
                angles = np.array(angles)
                angles_sorted = np.sort(angles)
                gaps = np.diff(angles_sorted)
                gaps = np.append(gaps, angles_sorted[0] + 2*np.pi - angles_sorted[-1])
                arc_angle = 2*np.pi - np.max(gaps)
                print(f"  Bogenwinkel: {np.degrees(arc_angle):.1f}°")

            # Vergleich
            if cyl_error < plane_error * 0.8:
                print(f"  → FILLET (cyl_err < plane_err * 0.8)")
            else:
                print(f"  → CHAMFER (plane besser oder gleich)")

        except Exception as e:
            print(f"  Zylinder-Fit FEHLER: {e}")


if __name__ == "__main__":
    stl_dir = Path(__file__).parent.parent / "stl"
    debug_fillet_detection(str(stl_dir / "verrunden.stl"))
