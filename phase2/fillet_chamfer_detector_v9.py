"""
Fillet & Chamfer Detector V9
============================

Finaler Ansatz: Finde die GRÖSSTEN PLANAREN Regionen (Hauptflächen)

1. Gruppiere Faces nach ähnlicher Normale (breiter Threshold 30°)
2. Für jede Gruppe: Prüfe Planarität
3. Die größten planaren Gruppen = Hauptflächen
4. Alle anderen Faces = Features
5. RANSAC Zylinder für Fillets
6. Plane-Fit für Chamfers
"""

import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from collections import defaultdict

import pyvista as pv
from scipy.sparse import lil_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.cluster import AgglomerativeClustering


@dataclass
class FilletRegion:
    face_ids: Set[int]
    axis: np.ndarray
    axis_point: np.ndarray
    radius: float
    arc_angle: float
    fit_error: float
    confidence: float


@dataclass
class ChamferRegion:
    face_ids: Set[int]
    normal: np.ndarray
    plane_point: np.ndarray
    width: float
    chamfer_angle: float
    fit_error: float


class FilletChamferDetectorV9:
    """
    Detector: Größte planare Regionen = Hauptflächen, Rest = Features.
    """

    def __init__(
        self,
        min_main_area_ratio: float = 0.02,  # Min 2% für Hauptfläche
        plane_tolerance: float = 1.0,  # Erhöht für Toleranz
        cylinder_tolerance: float = 3.0,
        ransac_iterations: int = 500
    ):
        self.min_main_ratio = min_main_area_ratio
        self.plane_tol = plane_tolerance
        self.cyl_tol = cylinder_tolerance
        self.ransac_iter = ransac_iterations

    def detect(self, mesh: pv.PolyData) -> Tuple[List[FilletRegion], List[ChamferRegion]]:
        """Erkennt Fillets und Chamfers."""

        print("    [1/6] Berechne Mesh-Strukturen...")

        if 'Normals' not in mesh.cell_data:
            mesh = mesh.compute_normals(cell_normals=True, point_normals=False)

        cell_normals = mesh.cell_data['Normals']
        edge_to_faces = self._build_edge_face_map(mesh)

        mesh_with_areas = mesh.compute_cell_sizes()
        areas = mesh_with_areas.cell_data['Area']
        total_area = np.sum(areas)

        # === PHASE 1: Clustere Faces nach Normale ===
        print("    [2/6] Clustere Faces nach Normale...")
        normal_clusters = self._cluster_by_normal(cell_normals, threshold_deg=30.0)
        print(f"          → {len(normal_clusters)} Normalen-Cluster")

        # === PHASE 2: Finde planare Hauptflächen ===
        print("    [3/6] Identifiziere planare Hauptflächen...")

        main_face_ids = set()
        main_regions = []

        for cluster_faces in normal_clusters.values():
            cluster_area = sum(areas[fid] for fid in cluster_faces)
            area_ratio = cluster_area / total_area

            # Nur große Cluster betrachten
            if area_ratio < self.min_main_ratio:
                continue

            # Prüfe Planarität
            plane_fit = self._fit_plane(mesh, cluster_faces)
            if plane_fit is not None and plane_fit['error'] < self.plane_tol:
                main_face_ids.update(cluster_faces)
                main_regions.append({
                    'face_ids': cluster_faces,
                    'normal': plane_fit['normal'],
                    'area': cluster_area
                })
                print(f"          Hauptfläche: {len(cluster_faces)} faces, area={cluster_area:.1f}mm², "
                      f"normal≈{plane_fit['normal']}")

        feature_face_ids = set(range(mesh.n_cells)) - main_face_ids
        print(f"          → {len(main_face_ids)} Hauptflächen-Faces, {len(feature_face_ids)} Feature-Faces")

        # === PHASE 3: Segmentiere Feature-Faces in Regionen ===
        print("    [4/6] Segmentiere Feature-Regionen...")

        feature_regions = self._segment_faces(mesh, feature_face_ids, edge_to_faces, cell_normals, 30.0)
        print(f"          → {len(feature_regions)} Feature-Regionen")

        # === PHASE 4: Klassifiziere jede Region als Fillet oder Chamfer ===
        print("    [5/6] Klassifiziere Regionen...")

        fillets = []
        chamfers = []

        for region in feature_regions:
            if len(region) < 2:
                continue

            # Versuche beide Fits
            plane_fit = self._fit_plane(mesh, region)
            cyl_fit = self._fit_cylinder_to_region(mesh, region, cell_normals)

            plane_error = plane_fit['error'] if plane_fit else float('inf')
            cyl_error = cyl_fit['error'] if cyl_fit else float('inf')

            # Wähle den besseren Fit
            if cyl_fit is not None and cyl_error < self.cyl_tol and cyl_error < plane_error * 0.8:
                # Zylinder ist deutlich besser → Fillet
                fillet = FilletRegion(
                    face_ids=region,
                    axis=cyl_fit['axis'],
                    axis_point=cyl_fit['center'],
                    radius=cyl_fit['radius'],
                    arc_angle=cyl_fit['arc_angle'],
                    fit_error=cyl_fit['error'],
                    confidence=1 - min(1, cyl_fit['error'] / self.cyl_tol)
                )
                fillets.append(fillet)
                print(f"          Fillet: r={fillet.radius:.2f}mm, arc={np.degrees(fillet.arc_angle):.1f}°, "
                      f"{len(region)} faces, err={cyl_error:.2f} (plane_err={plane_error:.2f})")
            elif plane_fit is not None and plane_error < self.plane_tol:
                # Plane ist besser oder Zylinder passt nicht → Chamfer
                width = self._compute_region_width(mesh, region, plane_fit)
                chamfer = ChamferRegion(
                    face_ids=region,
                    normal=plane_fit['normal'],
                    plane_point=plane_fit['centroid'],
                    width=width,
                    chamfer_angle=45.0,
                    fit_error=plane_fit['error']
                )
                chamfers.append(chamfer)
                print(f"          Chamfer: w={width:.2f}mm, {len(region)} faces, err={plane_error:.2f}")

        print(f"    [6/6] Ergebnis: {len(fillets)} Fillets, {len(chamfers)} Chamfers")

        return fillets, chamfers

    def _build_edge_face_map(self, mesh: pv.PolyData) -> Dict[Tuple[int, int], List[int]]:
        edge_to_faces = defaultdict(list)
        for face_id in range(mesh.n_cells):
            cell = mesh.get_cell(face_id)
            pts = cell.point_ids
            for i in range(len(pts)):
                edge = tuple(sorted([pts[i], pts[(i + 1) % len(pts)]]))
                edge_to_faces[edge].append(face_id)
        return edge_to_faces

    def _cluster_by_normal(
        self,
        cell_normals: np.ndarray,
        threshold_deg: float
    ) -> Dict[int, Set[int]]:
        """Clustert Faces nach Normalen-Ähnlichkeit."""

        clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=1 - np.cos(np.radians(threshold_deg)),
            metric='cosine',
            linkage='average'
        )

        labels = clustering.fit_predict(cell_normals)

        clusters = defaultdict(set)
        for face_id, label in enumerate(labels):
            clusters[label].add(face_id)

        return clusters

    def _segment_faces(
        self,
        mesh: pv.PolyData,
        face_ids: Set[int],
        edge_to_faces: Dict,
        cell_normals: np.ndarray,
        angle_threshold: float
    ) -> List[Set[int]]:
        if not face_ids:
            return []

        face_list = list(face_ids)
        face_to_idx = {f: i for i, f in enumerate(face_list)}
        n = len(face_list)
        adjacency = lil_matrix((n, n), dtype=np.int8)
        angle_rad = np.radians(angle_threshold)

        for edge, faces in edge_to_faces.items():
            if len(faces) != 2:
                continue
            f1, f2 = faces
            if f1 not in face_ids or f2 not in face_ids:
                continue

            n1, n2 = cell_normals[f1], cell_normals[f2]
            dot = np.clip(np.dot(n1, n2), -1, 1)
            if np.arccos(dot) <= angle_rad:
                i1, i2 = face_to_idx[f1], face_to_idx[f2]
                adjacency[i1, i2] = 1
                adjacency[i2, i1] = 1

        n_components, labels = connected_components(adjacency.tocsr(), directed=False, return_labels=True)

        regions = []
        for label_id in range(n_components):
            indices = np.where(labels == label_id)[0]
            region = {face_list[i] for i in indices}
            regions.append(region)
        return regions

    def _fit_cylinder_to_region(
        self,
        mesh: pv.PolyData,
        face_ids: Set[int],
        cell_normals: np.ndarray
    ) -> Optional[dict]:
        """
        Korrekter Zylinder-Fit für Fillet-Streifen.

        1. Finde Achsen-Richtung (PCA)
        2. Projiziere Punkte auf Ebene senkrecht zur Achse
        3. Fitte Kreis in 2D → Zentrum und Radius
        4. Transformiere Zentrum zurück in 3D
        """
        if len(face_ids) < 3:
            return None

        points = []
        for fid in face_ids:
            cell = mesh.get_cell(fid)
            points.extend(cell.points)

        points_3d = np.unique(np.array(points), axis=0)

        if len(points_3d) < 6:
            return None

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

        # 4. Fitte Kreis in 2D (algebraischer Fit)
        try:
            x = points_2d[:, 0]
            y = points_2d[:, 1]

            A = np.column_stack([2*x, 2*y, np.ones(len(x))])
            b = x**2 + y**2

            result, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
            cx, cy, d = result

            radius = np.sqrt(d + cx**2 + cy**2)
            center_2d = np.array([cx, cy])

        except Exception:
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
        error = np.mean(np.abs(distances - radius))

        # 7. Bogenwinkel
        angles = []
        for p in points_3d:
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
            'center': axis_point,
            'radius': radius,
            'arc_angle': arc_angle,
            'error': error
        }

    def _fit_cylinder_to_points(self, points: np.ndarray) -> Optional[dict]:
        if len(points) < 6:
            return None

        try:
            centroid = np.mean(points, axis=0)
            centered = points - centroid

            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            axis = Vt[0]

            proj = np.dot(centered, axis)[:, np.newaxis] * axis
            perp = centered - proj
            distances = np.linalg.norm(perp, axis=1)
            radius = np.median(distances)

            if radius < 0.5 or radius > 50:
                return None

            error = np.mean(np.abs(distances - radius))

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

            if len(angles) < 3:
                return None

            angles = np.array(angles)
            angles_sorted = np.sort(angles)
            gaps = np.diff(angles_sorted)
            gaps = np.append(gaps, angles_sorted[0] + 2*np.pi - angles_sorted[-1])
            arc_angle = 2*np.pi - np.max(gaps)

            return {'axis': axis, 'center': centroid, 'radius': radius, 'arc_angle': arc_angle, 'error': error}
        except:
            return None

    def _find_cylinder_faces(
        self,
        mesh: pv.PolyData,
        candidate_faces: Set[int],
        cylinder: dict,
        cell_normals: np.ndarray
    ) -> Set[int]:
        face_ids = set()

        for fid in candidate_faces:
            cell = mesh.get_cell(fid)
            pts = cell.points

            centered = pts - cylinder['center']
            proj = np.dot(centered, cylinder['axis'])[:, np.newaxis] * cylinder['axis']
            perp = centered - proj
            distances = np.abs(np.linalg.norm(perp, axis=1) - cylinder['radius'])

            if np.max(distances) < self.cyl_tol * 1.5:
                dot = abs(np.dot(cell_normals[fid], cylinder['axis']))
                if dot < 0.5:
                    face_ids.add(fid)

        return face_ids

    def _fit_plane(self, mesh: pv.PolyData, face_ids: Set[int]) -> Optional[dict]:
        if len(face_ids) < 1:
            return None
        try:
            points = []
            for fid in face_ids:
                cell = mesh.get_cell(fid)
                points.extend(cell.points)
            points = np.unique(np.array(points), axis=0)
            if len(points) < 3:
                return None

            centroid = np.mean(points, axis=0)
            centered = points - centroid
            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            normal = Vt[-1]
            error = np.mean(np.abs(np.dot(centered, normal)))

            return {'normal': normal, 'centroid': centroid, 'error': error}
        except:
            return None

    def _compute_region_width(self, mesh: pv.PolyData, face_ids: Set[int], plane_fit: dict) -> float:
        points = []
        for fid in face_ids:
            cell = mesh.get_cell(fid)
            points.extend(cell.points)
        points = np.array(points)

        normal = plane_fit['normal']
        u = np.cross(normal, [0, 0, 1]) if abs(normal[2]) < 0.9 else np.cross(normal, [1, 0, 0])
        u = u / np.linalg.norm(u)
        v = np.cross(normal, u)

        centered = points - plane_fit['centroid']
        return min(np.ptp(np.dot(centered, u)), np.ptp(np.dot(centered, v)))


def test_detector(stl_path: str, expected_fillets: int, expected_chamfers: int):
    print("=" * 60)
    print(f"TEST: {Path(stl_path).name}")
    print(f"Erwartet: {expected_fillets} Fillets, {expected_chamfers} Chamfers")
    print("=" * 60)

    if not Path(stl_path).exists():
        print(f"  FEHLER: Datei nicht gefunden!")
        return False

    mesh = pv.read(stl_path)
    print(f"Mesh: {mesh.n_cells} Faces, {mesh.n_points} Vertices")

    detector = FilletChamferDetectorV9(
        min_main_area_ratio=0.02,
        plane_tolerance=1.0,
        cylinder_tolerance=3.0,
        ransac_iterations=500
    )

    fillets, chamfers = detector.detect(mesh)

    print(f"\nErgebnis:")
    print(f"  Fillets: {len(fillets)}")
    print(f"  Chamfers: {len(chamfers)}")

    if fillets:
        print("\nFillet-Details:")
        for i, f in enumerate(fillets):
            print(f"  [{i+1}] r={f.radius:.2f}mm, arc={np.degrees(f.arc_angle):.1f}°, {len(f.face_ids)} faces")

    if chamfers:
        print("\nChamfer-Details:")
        for i, c in enumerate(chamfers):
            print(f"  [{i+1}] w={c.width:.2f}mm, {len(c.face_ids)} faces")

    fillet_ok = len(fillets) == expected_fillets
    chamfer_ok = len(chamfers) == expected_chamfers

    print(f"\n{'✓' if fillet_ok else '✗'} Fillets: {len(fillets)}/{expected_fillets}")
    print(f"{'✓' if chamfer_ok else '✗'} Chamfers: {len(chamfers)}/{expected_chamfers}")

    return fillet_ok and chamfer_ok


if __name__ == "__main__":
    print("=" * 60)
    print("Fillet & Chamfer Detector V9 (Größte planare Regionen)")
    print("=" * 60)

    stl_dir = Path(__file__).parent.parent / "stl"

    r1 = test_detector(str(stl_dir / "verrunden.stl"), 5, 0)
    print("\n")
    r2 = test_detector(str(stl_dir / "fase.stl"), 0, 5)

    print("\n" + "=" * 60)
    print("ZUSAMMENFASSUNG")
    print("=" * 60)
    print(f"  {'✓' if r1 else '✗'} verrunden.stl")
    print(f"  {'✓' if r2 else '✗'} fase.stl")
