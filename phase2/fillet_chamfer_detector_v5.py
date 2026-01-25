"""
Fillet & Chamfer Detector V5
============================

Ansatz: Haupt-Normalenrichtungen finden
- Bei einem Quader gibt es 6 Haupt-Normalenrichtungen (±X, ±Y, ±Z)
- Faces die zu einer Hauptrichtung passen = Hauptflächen
- Faces die zu KEINER Hauptrichtung passen = Features (Fillets/Chamfers)

Algorithmus:
1. Clustere alle Face-Normalen
2. Identifiziere die dominanten Cluster (Hauptrichtungen)
3. Klassifiziere Faces: Hauptrichtung vs Feature
4. Segmentiere Feature-Faces
5. Klassifiziere: Planar = Chamfer, Gekrümmt = Fillet
"""

import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from collections import defaultdict

import pyvista as pv
from scipy.spatial.distance import cdist
from scipy.sparse import lil_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.cluster import AgglomerativeClustering


@dataclass
class FilletRegion:
    """Eine erkannte Fillet-Region."""
    face_ids: Set[int]
    axis: np.ndarray
    axis_point: np.ndarray
    radius: float
    arc_angle: float
    fit_error: float
    confidence: float


@dataclass
class ChamferRegion:
    """Eine erkannte Chamfer-Region."""
    face_ids: Set[int]
    normal: np.ndarray
    plane_point: np.ndarray
    width: float
    chamfer_angle: float
    fit_error: float


class FilletChamferDetectorV5:
    """
    Normalen-Clustering basierter Detector.
    """

    def __init__(
        self,
        normal_tolerance: float = 15.0,  # Grad - Toleranz für Haupt-Normal
        min_main_face_ratio: float = 0.02,  # Min 2% der Faces für Hauptrichtung
        min_region_faces: int = 3,
        plane_tolerance: float = 0.5,
        cylinder_tolerance: float = 3.0
    ):
        self.normal_tol = np.radians(normal_tolerance)
        self.main_ratio = min_main_face_ratio
        self.min_faces = min_region_faces
        self.plane_tol = plane_tolerance
        self.cyl_tol = cylinder_tolerance

    def detect(self, mesh: pv.PolyData) -> Tuple[List[FilletRegion], List[ChamferRegion]]:
        """Erkennt Fillets und Chamfers."""

        print("    [1/7] Berechne Mesh-Strukturen...")

        if 'Normals' not in mesh.cell_data:
            mesh = mesh.compute_normals(cell_normals=True, point_normals=False)

        cell_normals = mesh.cell_data['Normals']
        edge_to_faces = self._build_edge_face_map(mesh)

        # Schritt 1: Finde Haupt-Normalenrichtungen durch Clustering
        print("    [2/7] Clustere Normalen...")
        normal_clusters = self._cluster_normals(cell_normals)
        print(f"          → {len(normal_clusters)} Normalen-Cluster gefunden")

        # Schritt 2: Identifiziere Hauptrichtungen (große Cluster)
        print("    [3/7] Identifiziere Hauptrichtungen...")
        n_faces = mesh.n_cells
        min_cluster_size = int(n_faces * self.main_ratio)

        main_directions = []
        for cluster_id, face_ids in normal_clusters.items():
            if len(face_ids) >= min_cluster_size:
                cluster_normals = cell_normals[list(face_ids)]
                avg_normal = np.mean(cluster_normals, axis=0)
                avg_normal = avg_normal / np.linalg.norm(avg_normal)
                main_directions.append({
                    'normal': avg_normal,
                    'face_ids': face_ids,
                    'size': len(face_ids)
                })

        print(f"          → {len(main_directions)} Hauptrichtungen")
        for i, md in enumerate(main_directions):
            print(f"             [{i+1}] {md['size']} Faces, Normal≈{md['normal']}")

        # Schritt 3: Klassifiziere Faces
        print("    [4/7] Klassifiziere Faces...")
        main_face_ids = set()
        for md in main_directions:
            main_face_ids.update(md['face_ids'])

        feature_face_ids = set(range(n_faces)) - main_face_ids
        print(f"          → {len(main_face_ids)} Hauptflächen-Faces, {len(feature_face_ids)} Feature-Faces")

        # Schritt 4: Segmentiere Feature-Faces
        print("    [5/7] Segmentiere Feature-Regionen...")
        feature_regions = self._segment_faces(mesh, feature_face_ids, edge_to_faces)
        print(f"          → {len(feature_regions)} Feature-Regionen")

        # Schritt 5: Klassifiziere Feature-Regionen
        print("    [6/7] Klassifiziere Features...")
        fillets = []
        chamfers = []

        for region in feature_regions:
            if len(region) < self.min_faces:
                continue

            # Versuche Zylinder-Fit (Fillet)
            cyl_fit = self._fit_cylinder(mesh, region, cell_normals)

            if cyl_fit is not None and cyl_fit['error'] < self.cyl_tol:
                fillet = FilletRegion(
                    face_ids=region,
                    axis=cyl_fit['axis'],
                    axis_point=cyl_fit['centroid'],
                    radius=cyl_fit['radius'],
                    arc_angle=cyl_fit['arc_angle'],
                    fit_error=cyl_fit['error'],
                    confidence=max(0, 1 - cyl_fit['error'] / self.cyl_tol)
                )
                fillets.append(fillet)
                print(f"          Fillet: r={fillet.radius:.2f}mm, arc={np.degrees(fillet.arc_angle):.1f}°, {len(region)} faces, err={fillet.fit_error:.2f}")
                continue

            # Versuche Plane-Fit (Chamfer)
            plane_fit = self._fit_plane(mesh, region)

            if plane_fit is not None and plane_fit['error'] < self.plane_tol:
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
                print(f"          Chamfer: w={width:.2f}mm, {len(region)} faces")

        print(f"    [7/7] Ergebnis: {len(fillets)} Fillets, {len(chamfers)} Chamfers")

        return fillets, chamfers

    def _build_edge_face_map(self, mesh: pv.PolyData) -> Dict[Tuple[int, int], List[int]]:
        """Baut Edge-zu-Face Mapping."""
        edge_to_faces = defaultdict(list)

        for face_id in range(mesh.n_cells):
            cell = mesh.get_cell(face_id)
            pts = cell.point_ids
            for i in range(len(pts)):
                edge = tuple(sorted([pts[i], pts[(i + 1) % len(pts)]]))
                edge_to_faces[edge].append(face_id)

        return edge_to_faces

    def _cluster_normals(self, cell_normals: np.ndarray) -> Dict[int, Set[int]]:
        """
        Clustert Face-Normalen mit AgglomerativeClustering.
        """

        n_faces = len(cell_normals)

        # Verwende Winkel-basierte Distanz
        # cos(angle) = dot(n1, n2), also angle = arccos(dot)
        # Für Clustering: Distanz = 1 - |dot| (damit parallele und anti-parallele gleich sind)

        clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=1 - np.cos(self.normal_tol),
            metric='cosine',
            linkage='average'
        )

        labels = clustering.fit_predict(cell_normals)

        # Gruppiere nach Labels
        clusters = defaultdict(set)
        for face_id, label in enumerate(labels):
            clusters[label].add(face_id)

        return clusters

    def _segment_faces(
        self,
        mesh: pv.PolyData,
        face_ids: Set[int],
        edge_to_faces: Dict[Tuple[int, int], List[int]]
    ) -> List[Set[int]]:
        """Segmentiert Faces in zusammenhängende Regionen."""

        if not face_ids:
            return []

        face_list = list(face_ids)
        face_to_idx = {f: i for i, f in enumerate(face_list)}
        n = len(face_list)

        adjacency = lil_matrix((n, n), dtype=np.int8)

        for edge, faces in edge_to_faces.items():
            if len(faces) != 2:
                continue

            f1, f2 = faces
            if f1 in face_ids and f2 in face_ids:
                i1, i2 = face_to_idx[f1], face_to_idx[f2]
                adjacency[i1, i2] = 1
                adjacency[i2, i1] = 1

        n_components, labels = connected_components(
            adjacency.tocsr(), directed=False, return_labels=True
        )

        regions = []
        for label_id in range(n_components):
            indices = np.where(labels == label_id)[0]
            region = {face_list[i] for i in indices}
            regions.append(region)

        return regions

    def _fit_plane(self, mesh: pv.PolyData, face_ids: Set[int]) -> Optional[dict]:
        """Fittet eine Ebene."""

        if len(face_ids) < 1:
            return None

        try:
            points = []
            for fid in face_ids:
                cell = mesh.get_cell(fid)
                points.extend(cell.points)

            points = np.array(points)
            unique_points = np.unique(points, axis=0)

            if len(unique_points) < 3:
                return None

            centroid = np.mean(unique_points, axis=0)
            centered = unique_points - centroid

            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            normal = Vt[-1]

            distances = np.abs(np.dot(centered, normal))
            error = np.mean(distances)

            return {
                'normal': normal,
                'centroid': centroid,
                'error': error
            }

        except Exception:
            return None

    def _fit_cylinder(
        self,
        mesh: pv.PolyData,
        face_ids: Set[int],
        cell_normals: np.ndarray
    ) -> Optional[dict]:
        """Fittet einen Zylinder."""

        if len(face_ids) < 3:
            return None

        try:
            points = []
            normals = []

            for fid in face_ids:
                cell = mesh.get_cell(fid)
                n = cell_normals[fid]
                for pt in cell.points:
                    points.append(pt)
                    normals.append(n)

            points = np.array(points)
            normals = np.array(normals)

            unique_points = np.unique(points, axis=0)
            unique_normals = np.unique(normals, axis=0)

            if len(unique_points) < 6 or len(unique_normals) < 2:
                return None

            from sklearn.decomposition import PCA

            pca = PCA(n_components=3)
            pca.fit(unique_normals)

            axis = pca.components_[-1]

            dots = np.abs(np.dot(unique_normals, axis))
            if np.mean(dots) > 0.5:
                return None

            centroid = np.mean(unique_points, axis=0)
            centered = unique_points - centroid

            proj_along_axis = np.dot(centered, axis)[:, np.newaxis] * axis
            perpendicular = centered - proj_along_axis
            distances = np.linalg.norm(perpendicular, axis=1)

            radius = np.median(distances)

            if radius < 0.3 or radius > 100:
                return None

            errors = np.abs(distances - radius)
            error = np.mean(errors)

            # Bogenwinkel
            if abs(axis[2]) < 0.9:
                x_local = np.cross(axis, [0, 0, 1])
            else:
                x_local = np.cross(axis, [1, 0, 0])
            x_local = x_local / np.linalg.norm(x_local)
            y_local = np.cross(axis, x_local)

            angles = []
            for p in unique_points:
                rel = p - centroid
                h = np.dot(rel, axis)
                perp = rel - h * axis
                if np.linalg.norm(perp) > 1e-6:
                    perp_norm = perp / np.linalg.norm(perp)
                    angle = np.arctan2(
                        np.dot(perp_norm, y_local),
                        np.dot(perp_norm, x_local)
                    )
                    angles.append(angle)

            if len(angles) < 3:
                return None

            angles = np.array(angles)
            angles_sorted = np.sort(angles)
            gaps = np.diff(angles_sorted)
            gaps = np.append(gaps, angles_sorted[0] + 2*np.pi - angles_sorted[-1])
            max_gap = np.max(gaps)
            arc_angle = 2 * np.pi - max_gap

            return {
                'axis': axis,
                'centroid': centroid,
                'radius': radius,
                'arc_angle': arc_angle,
                'error': error
            }

        except Exception:
            return None

    def _compute_region_width(
        self,
        mesh: pv.PolyData,
        face_ids: Set[int],
        plane_fit: dict
    ) -> float:
        """Berechnet die Regions-Breite."""

        points = []
        for fid in face_ids:
            cell = mesh.get_cell(fid)
            points.extend(cell.points)

        points = np.array(points)
        centroid = plane_fit['centroid']
        normal = plane_fit['normal']

        if abs(normal[2]) < 0.9:
            u = np.cross(normal, [0, 0, 1])
        else:
            u = np.cross(normal, [1, 0, 0])
        u = u / np.linalg.norm(u)
        v = np.cross(normal, u)

        centered = points - centroid
        proj_u = np.dot(centered, u)
        proj_v = np.dot(centered, v)

        width_u = np.max(proj_u) - np.min(proj_u)
        width_v = np.max(proj_v) - np.min(proj_v)

        return min(width_u, width_v)


def test_detector(stl_path: str, expected_fillets: int, expected_chamfers: int):
    """Testet den Detector."""

    print("=" * 60)
    print(f"TEST: {Path(stl_path).name}")
    print(f"Erwartet: {expected_fillets} Fillets, {expected_chamfers} Chamfers")
    print("=" * 60)

    if not Path(stl_path).exists():
        print(f"  FEHLER: Datei nicht gefunden!")
        return False

    mesh = pv.read(stl_path)
    print(f"Mesh: {mesh.n_cells} Faces, {mesh.n_points} Vertices")

    detector = FilletChamferDetectorV5(
        normal_tolerance=10.0,  # 10° Toleranz für Hauptrichtungen
        min_main_face_ratio=0.02,  # Min 2% für Hauptrichtung
        min_region_faces=3,
        plane_tolerance=0.5,
        cylinder_tolerance=3.0
    )

    fillets, chamfers = detector.detect(mesh)

    print(f"\nErgebnis:")
    print(f"  Fillets: {len(fillets)}")
    print(f"  Chamfers: {len(chamfers)}")

    if fillets:
        print("\nFillet-Details:")
        for i, f in enumerate(fillets):
            print(f"  [{i+1}] Radius={f.radius:.2f}mm, "
                  f"Arc={np.degrees(f.arc_angle):.1f}°, "
                  f"Faces={len(f.face_ids)}")

    if chamfers:
        print("\nChamfer-Details:")
        for i, c in enumerate(chamfers):
            print(f"  [{i+1}] Width={c.width:.2f}mm, "
                  f"Faces={len(c.face_ids)}")

    fillet_ok = len(fillets) == expected_fillets
    chamfer_ok = len(chamfers) == expected_chamfers

    print(f"\n{'✓' if fillet_ok else '✗'} Fillets: {len(fillets)}/{expected_fillets}")
    print(f"{'✓' if chamfer_ok else '✗'} Chamfers: {len(chamfers)}/{expected_chamfers}")

    return fillet_ok and chamfer_ok


if __name__ == "__main__":
    print("=" * 60)
    print("Fillet & Chamfer Detector V5 (Normalen-Clustering)")
    print("=" * 60)

    stl_dir = Path(__file__).parent.parent / "stl"

    results = []

    # Test verrunden.stl (5 Fillets erwartet)
    r1 = test_detector(str(stl_dir / "verrunden.stl"), expected_fillets=5, expected_chamfers=0)
    results.append(("verrunden.stl", r1))

    print("\n")

    # Test fase.stl (5 Chamfers erwartet)
    r2 = test_detector(str(stl_dir / "fase.stl"), expected_fillets=0, expected_chamfers=5)
    results.append(("fase.stl", r2))

    print("\n" + "=" * 60)
    print("ZUSAMMENFASSUNG")
    print("=" * 60)
    for name, passed in results:
        print(f"  {'✓' if passed else '✗'} {name}")
