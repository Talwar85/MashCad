"""Debug V2: Korrekter Zylinder-Fit für Fillet-Streifen"""
import numpy as np
from pathlib import Path
import pyvista as pv
from collections import defaultdict
from scipy.sparse import lil_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.cluster import AgglomerativeClustering
from scipy.optimize import least_squares


def fit_circle_2d(points_2d):
    """
    Fittet einen Kreis auf 2D-Punkte.

    Methode: Algebraischer Fit (schnell)
    Gleichung: (x-cx)² + (y-cy)² = r²
    Umgeformt: x² + y² = 2*cx*x + 2*cy*y + (r² - cx² - cy²)
    """
    x = points_2d[:, 0]
    y = points_2d[:, 1]

    # Least Squares: A * [cx, cy, d]^T = b
    # wo d = r² - cx² - cy²
    A = np.column_stack([2*x, 2*y, np.ones(len(x))])
    b = x**2 + y**2

    result, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy, d = result

    r = np.sqrt(d + cx**2 + cy**2)
    center = np.array([cx, cy])

    # Fehler berechnen
    distances = np.sqrt((x - cx)**2 + (y - cy)**2)
    error = np.mean(np.abs(distances - r))

    return center, r, error


def fit_cylinder_properly(points_3d):
    """
    Korrekter Zylinder-Fit für Fillet-Streifen.

    1. Finde Achsen-Richtung (PCA)
    2. Projiziere Punkte auf Ebene senkrecht zur Achse
    3. Fitte Kreis in 2D → Zentrum und Radius
    4. Transformiere Zentrum zurück in 3D
    """
    # 1. Achsen-Richtung via PCA
    centroid = np.mean(points_3d, axis=0)
    centered = points_3d - centroid

    U, S, Vt = np.linalg.svd(centered, full_matrices=False)
    axis = Vt[0]  # Richtung mit größter Varianz (entlang des Streifens)

    # 2. Lokales Koordinatensystem
    if abs(axis[2]) < 0.9:
        x_local = np.cross(axis, [0, 0, 1])
    else:
        x_local = np.cross(axis, [1, 0, 0])
    x_local = x_local / np.linalg.norm(x_local)
    y_local = np.cross(axis, x_local)

    # 3. Projiziere Punkte auf die Ebene (x_local, y_local)
    points_2d = np.column_stack([
        np.dot(centered, x_local),
        np.dot(centered, y_local)
    ])

    # 4. Fitte Kreis in 2D
    try:
        center_2d, radius, error_2d = fit_circle_2d(points_2d)
    except Exception as e:
        return None

    if radius < 0.5 or radius > 100:
        return None

    # 5. Transformiere Zentrum zurück in 3D
    center_offset = center_2d[0] * x_local + center_2d[1] * y_local
    axis_point = centroid + center_offset

    # 6. Berechne 3D Fehler
    axis_to_points = points_3d - axis_point
    proj_along_axis = np.dot(axis_to_points, axis)[:, np.newaxis] * axis
    perp = axis_to_points - proj_along_axis
    distances = np.linalg.norm(perp, axis=1)
    error_3d = np.mean(np.abs(distances - radius))

    # 7. Bogenwinkel
    angles = []
    for i, p in enumerate(points_3d):
        rel = p - axis_point
        h = np.dot(rel, axis)
        perp_vec = rel - h * axis
        if np.linalg.norm(perp_vec) > 1e-6:
            pn = perp_vec / np.linalg.norm(perp_vec)
            angle = np.arctan2(np.dot(pn, y_local), np.dot(pn, x_local))
            angles.append(angle)

    if len(angles) < 3:
        return None

    angles = np.array(angles)
    angles_sorted = np.sort(angles)
    gaps = np.diff(angles_sorted)
    gaps = np.append(gaps, angles_sorted[0] + 2*np.pi - angles_sorted[-1])
    arc_angle = 2*np.pi - np.max(gaps)

    return {
        'axis': axis,
        'axis_point': axis_point,
        'radius': radius,
        'arc_angle': arc_angle,
        'error': error_3d,
        'error_2d': error_2d
    }


def debug_fillet_detection(stl_path: str):
    print("=" * 60)
    print(f"Debug V2: {Path(stl_path).name}")
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
            points = []
            for fid in cluster_faces:
                cell = mesh.get_cell(fid)
                points.extend(cell.points)
            points = np.unique(np.array(points), axis=0)

            centroid = np.mean(points, axis=0)
            centered = points - centroid
            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            plane_error = np.mean(np.abs(np.dot(centered, Vt[-1])))

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
        plane_error = np.mean(np.abs(np.dot(centered, Vt[-1])))
        print(f"  Plane-Fit: error={plane_error:.4f}mm")

        # Korrekter Zylinder-Fit
        cyl = fit_cylinder_properly(points)
        if cyl:
            print(f"  Zylinder-Fit: radius={cyl['radius']:.2f}mm, error={cyl['error']:.4f}mm")
            print(f"  Bogenwinkel: {np.degrees(cyl['arc_angle']):.1f}°")

            if cyl['error'] < plane_error * 0.8 and cyl['error'] < 3.0:
                print(f"  → FILLET (cyl_err < plane_err * 0.8)")
            elif cyl['error'] < 3.0 and cyl['radius'] > 1.0:
                print(f"  → FILLET (radius plausibel)")
            else:
                print(f"  → CHAMFER (plane besser)")
        else:
            print(f"  Zylinder-Fit: FEHLGESCHLAGEN")
            print(f"  → CHAMFER")


if __name__ == "__main__":
    stl_dir = Path(__file__).parent.parent / "stl"
    debug_fillet_detection(str(stl_dir / "verrunden.stl"))
