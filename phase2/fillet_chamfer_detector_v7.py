"""
Fillet & Chamfer Detector V7
============================

Verbesserter Ansatz:
1. Finde die 6 Haupt-Achsen (±X, ±Y, ±Z) durch Normalen-Analyse
2. Faces die zu einer Hauptachse gehören = Hauptflächen
3. Rest = Feature-Faces
4. RANSAC für Zylinder (Fillets)
5. Plane-Fit für verbleibende (Chamfers)
"""

import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from collections import defaultdict

import pyvista as pv
from scipy.sparse import lil_matrix
from scipy.sparse.csgraph import connected_components


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


class FilletChamferDetectorV7:
    """
    Detector mit expliziter Hauptachsen-Erkennung.
    """

    def __init__(
        self,
        axis_tolerance: float = 15.0,  # Grad - Toleranz für Hauptachsen
        min_axis_faces: int = 3,
        plane_tolerance: float = 0.5,
        cylinder_tolerance: float = 2.0,
        ransac_iterations: int = 1000
    ):
        self.axis_tol = np.radians(axis_tolerance)
        self.min_axis_faces = min_axis_faces
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

        # === PHASE 1: Finde Hauptachsen ===
        print("    [2/6] Finde Hauptachsen...")
        main_axes = self._find_main_axes(cell_normals)
        print(f"          → {len(main_axes)} Hauptachsen gefunden")
        for i, axis in enumerate(main_axes):
            print(f"             [{i+1}] Normal≈{axis['direction']}, {axis['face_count']} Faces")

        # === PHASE 2: Klassifiziere Faces ===
        print("    [3/6] Klassifiziere Faces...")
        main_face_ids = set()
        for axis_info in main_axes:
            main_face_ids.update(axis_info['face_ids'])

        feature_face_ids = set(range(mesh.n_cells)) - main_face_ids
        print(f"          → {len(main_face_ids)} Hauptflächen-Faces, {len(feature_face_ids)} Feature-Faces")

        # === PHASE 3: RANSAC Zylinder-Erkennung ===
        print("    [4/6] RANSAC Zylinder-Erkennung...")

        fillets = []
        used_face_ids = set()

        # Sammle Feature-Punkte
        feature_points, point_to_faces = self._collect_feature_points(mesh, feature_face_ids)
        print(f"          → {len(feature_points)} Feature-Punkte")

        # Iterativ Zylinder finden
        remaining_faces = feature_face_ids.copy()
        max_fillets = 10  # Safety limit

        while len(remaining_faces) > 10 and len(fillets) < max_fillets:
            cylinder = self._find_best_cylinder(
                mesh, remaining_faces, cell_normals
            )

            if cylinder is None or len(cylinder['face_ids']) < 3:
                break

            fillet = FilletRegion(
                face_ids=cylinder['face_ids'],
                axis=cylinder['axis'],
                axis_point=cylinder['center'],
                radius=cylinder['radius'],
                arc_angle=cylinder['arc_angle'],
                fit_error=cylinder['error'],
                confidence=1 - cylinder['error'] / self.cyl_tol
            )
            fillets.append(fillet)
            print(f"          Fillet: r={fillet.radius:.2f}mm, arc={np.degrees(fillet.arc_angle):.1f}°, "
                  f"{len(fillet.face_ids)} faces, err={fillet.fit_error:.2f}mm")

            remaining_faces -= cylinder['face_ids']
            used_face_ids.update(cylinder['face_ids'])

        # === PHASE 4: Chamfer-Erkennung ===
        print("    [5/6] Chamfer-Erkennung...")

        chamfer_regions = self._segment_faces(mesh, remaining_faces, edge_to_faces, cell_normals)
        chamfers = []

        for region in chamfer_regions:
            if len(region) < 2:
                continue

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

    def _find_main_axes(self, cell_normals: np.ndarray) -> List[dict]:
        """
        Findet die Hauptachsen (±X, ±Y, ±Z) und zugehörige Faces.

        Methode:
        1. Teste alle 6 Achsen-Richtungen
        2. Für jede Richtung: Zähle Faces deren Normale nahe dran ist
        3. Behalte Richtungen mit genug Faces
        """

        canonical_axes = [
            np.array([1, 0, 0]),   # +X
            np.array([-1, 0, 0]),  # -X
            np.array([0, 1, 0]),   # +Y
            np.array([0, -1, 0]),  # -Y
            np.array([0, 0, 1]),   # +Z
            np.array([0, 0, -1])   # -Z
        ]

        main_axes = []

        for axis in canonical_axes:
            # Finde Faces die zu dieser Achse passen
            dots = np.dot(cell_normals, axis)
            # Winkel = arccos(dot), wir wollen dot > cos(tolerance)
            cos_tol = np.cos(self.axis_tol)
            matching_mask = dots > cos_tol
            matching_faces = set(np.where(matching_mask)[0])

            if len(matching_faces) >= self.min_axis_faces:
                # Berechne mittlere Normale der Faces
                mean_normal = np.mean(cell_normals[list(matching_faces)], axis=0)
                mean_normal = mean_normal / np.linalg.norm(mean_normal)

                main_axes.append({
                    'direction': mean_normal,
                    'face_ids': matching_faces,
                    'face_count': len(matching_faces)
                })

        return main_axes

    def _collect_feature_points(
        self,
        mesh: pv.PolyData,
        feature_face_ids: Set[int]
    ) -> Tuple[np.ndarray, Dict]:
        """Sammelt alle Punkte der Feature-Faces."""

        points = []
        point_to_faces = defaultdict(set)

        for fid in feature_face_ids:
            cell = mesh.get_cell(fid)
            for pt in cell.points:
                pt_tuple = tuple(pt)
                if pt_tuple not in point_to_faces:
                    points.append(pt)
                point_to_faces[pt_tuple].add(fid)

        return np.array(points) if points else np.array([]).reshape(0, 3), point_to_faces

    def _find_best_cylinder(
        self,
        mesh: pv.PolyData,
        candidate_faces: Set[int],
        cell_normals: np.ndarray
    ) -> Optional[dict]:
        """
        Findet den besten Zylinder durch RANSAC.
        """

        if len(candidate_faces) < 5:
            return None

        # Sammle Punkte
        points = []
        for fid in candidate_faces:
            cell = mesh.get_cell(fid)
            points.extend(cell.points)
        points = np.unique(np.array(points), axis=0)

        if len(points) < 10:
            return None

        best_cylinder = None
        best_score = 0

        for _ in range(self.ransac_iter):
            # Wähle 6 zufällige Punkte
            if len(points) < 6:
                break

            sample_idx = np.random.choice(len(points), min(6, len(points)), replace=False)
            sample = points[sample_idx]

            # Fitte Zylinder
            cyl = self._fit_cylinder_to_points(sample)
            if cyl is None:
                continue

            # Zähle Inlier (Faces)
            inlier_faces = self._find_cylinder_faces(
                mesh, candidate_faces, cyl, cell_normals
            )

            score = len(inlier_faces)

            if score > best_score and score >= 5:
                # Refit auf Inlier-Punkten
                inlier_points = []
                for fid in inlier_faces:
                    cell = mesh.get_cell(fid)
                    inlier_points.extend(cell.points)
                inlier_points = np.unique(np.array(inlier_points), axis=0)

                refined_cyl = self._fit_cylinder_to_points(inlier_points)
                if refined_cyl is not None:
                    # Finale Faces bestimmen
                    final_faces = self._find_cylinder_faces(
                        mesh, candidate_faces, refined_cyl, cell_normals
                    )
                    if len(final_faces) >= 5:
                        refined_cyl['face_ids'] = final_faces
                        best_cylinder = refined_cyl
                        best_score = len(final_faces)

        return best_cylinder

    def _fit_cylinder_to_points(self, points: np.ndarray) -> Optional[dict]:
        """Fittet Zylinder auf Punkte."""
        if len(points) < 6:
            return None

        try:
            centroid = np.mean(points, axis=0)
            centered = points - centroid

            # SVD für Achse
            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            axis = Vt[0]  # Richtung mit größter Varianz

            # Radius
            proj = np.dot(centered, axis)[:, np.newaxis] * axis
            perp = centered - proj
            distances = np.linalg.norm(perp, axis=1)
            radius = np.median(distances)

            if radius < 0.5 or radius > 50:
                return None

            error = np.mean(np.abs(distances - radius))

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

            if len(angles) < 3:
                return None

            angles = np.array(angles)
            angles_sorted = np.sort(angles)
            gaps = np.diff(angles_sorted)
            gaps = np.append(gaps, angles_sorted[0] + 2*np.pi - angles_sorted[-1])
            arc_angle = 2*np.pi - np.max(gaps)

            return {
                'axis': axis,
                'center': centroid,
                'radius': radius,
                'arc_angle': arc_angle,
                'error': error
            }
        except:
            return None

    def _find_cylinder_faces(
        self,
        mesh: pv.PolyData,
        candidate_faces: Set[int],
        cylinder: dict,
        cell_normals: np.ndarray
    ) -> Set[int]:
        """Findet Faces die zum Zylinder gehören."""
        face_ids = set()

        for fid in candidate_faces:
            cell = mesh.get_cell(fid)
            pts = cell.points

            # Punkte auf Zylinder?
            centered = pts - cylinder['center']
            proj = np.dot(centered, cylinder['axis'])[:, np.newaxis] * cylinder['axis']
            perp = centered - proj
            distances = np.abs(np.linalg.norm(perp, axis=1) - cylinder['radius'])

            if np.max(distances) < self.cyl_tol * 1.5:
                # Normale senkrecht zur Achse?
                dot = abs(np.dot(cell_normals[fid], cylinder['axis']))
                if dot < 0.5:
                    face_ids.add(fid)

        return face_ids

    def _segment_faces(
        self,
        mesh: pv.PolyData,
        face_ids: Set[int],
        edge_to_faces: Dict,
        cell_normals: np.ndarray,
        angle_threshold: float = 20.0
    ) -> List[Set[int]]:
        """Segmentiert Faces in zusammenhängende Regionen."""
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

    detector = FilletChamferDetectorV7(
        axis_tolerance=15.0,
        min_axis_faces=3,
        plane_tolerance=0.5,
        cylinder_tolerance=3.0,
        ransac_iterations=1000
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
    print("Fillet & Chamfer Detector V7 (Hauptachsen + RANSAC)")
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
