"""
Fillet & Chamfer Detector V8
============================

Flächenbasierter Ansatz:
- Hauptflächen = GROSSE Faces (> threshold)
- Feature-Faces = KLEINE Faces (< threshold)
- Dann: RANSAC für Zylinder (Fillets), Plane-Fit für Rest (Chamfers)

Für Meshes wo Fillets viele kleine Dreiecke haben, ist das effektiv.
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


class FilletChamferDetectorV8:
    """
    Flächenbasierter Detector.
    """

    def __init__(
        self,
        small_face_threshold_ratio: float = 0.01,  # Faces < 1% der mittleren Größe = klein
        min_region_faces: int = 3,
        plane_tolerance: float = 0.5,
        cylinder_tolerance: float = 3.0,
        ransac_iterations: int = 500
    ):
        self.small_ratio = small_face_threshold_ratio
        self.min_faces = min_region_faces
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

        # Berechne Flächeninhalte
        mesh_with_areas = mesh.compute_cell_sizes()
        areas = mesh_with_areas.cell_data['Area']
        total_area = np.sum(areas)
        mean_area = np.mean(areas)
        median_area = np.median(areas)

        print(f"          Flächen: min={np.min(areas):.2f}, median={median_area:.2f}, "
              f"max={np.max(areas):.2f}, total={total_area:.2f} mm²")

        # === PHASE 1: Klassifiziere nach Flächengröße ===
        print("    [2/6] Klassifiziere nach Flächengröße...")

        # Schwellenwert: Faces die viel kleiner als der Median sind = Feature-Faces
        area_threshold = median_area * 0.3  # Faces < 30% des Medians sind "klein"

        large_face_ids = set(np.where(areas >= area_threshold)[0])
        small_face_ids = set(np.where(areas < area_threshold)[0])

        print(f"          Threshold: {area_threshold:.2f} mm²")
        print(f"          → {len(large_face_ids)} große Faces, {len(small_face_ids)} kleine Faces")

        # === Fallback: Wenn keine kleinen Faces, nutze Segmentierung ===
        if len(small_face_ids) < 10:
            print("    [3/6] Fallback: Normalen-basierte Segmentierung...")
            return self._detect_by_segmentation(mesh, cell_normals, edge_to_faces, areas)

        # === PHASE 2: RANSAC Zylinder für kleine Faces ===
        print("    [3/6] RANSAC Zylinder-Erkennung...")

        fillets = []
        remaining_small = small_face_ids.copy()

        while len(remaining_small) > 10:
            cylinder = self._find_best_cylinder(mesh, remaining_small, cell_normals)

            if cylinder is None or len(cylinder['face_ids']) < 5:
                break

            fillet = FilletRegion(
                face_ids=cylinder['face_ids'],
                axis=cylinder['axis'],
                axis_point=cylinder['center'],
                radius=cylinder['radius'],
                arc_angle=cylinder['arc_angle'],
                fit_error=cylinder['error'],
                confidence=1 - min(1, cylinder['error'] / self.cyl_tol)
            )
            fillets.append(fillet)
            print(f"          Fillet: r={fillet.radius:.2f}mm, arc={np.degrees(fillet.arc_angle):.1f}°, "
                  f"{len(fillet.face_ids)} faces")

            remaining_small -= cylinder['face_ids']

        # === PHASE 3: Chamfer-Erkennung für verbleibende kleine Faces ===
        print("    [4/6] Chamfer-Erkennung für verbleibende kleine Faces...")

        chamfer_regions = self._segment_faces(mesh, remaining_small, edge_to_faces, cell_normals, 15.0)
        chamfers = []

        for region in chamfer_regions:
            if len(region) < self.min_faces:
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

        print(f"    [5/6] Ergebnis: {len(fillets)} Fillets, {len(chamfers)} Chamfers")

        return fillets, chamfers

    def _detect_by_segmentation(
        self,
        mesh: pv.PolyData,
        cell_normals: np.ndarray,
        edge_to_faces: Dict,
        areas: np.ndarray
    ) -> Tuple[List[FilletRegion], List[ChamferRegion]]:
        """Fallback: Erkennung durch Segmentierung (wie V3)."""

        total_area = np.sum(areas)

        # Segmentiere mit 10° Threshold
        regions = self._segment_mesh(mesh, edge_to_faces, cell_normals, 10.0)
        print(f"          → {len(regions)} Regionen")

        # Identifiziere Hauptflächen (> 3% der Gesamtfläche + planar)
        main_face_ids = set()
        feature_regions = []

        for region in regions:
            region_area = sum(areas[fid] for fid in region)
            area_ratio = region_area / total_area

            plane_fit = self._fit_plane(mesh, region)
            is_planar = plane_fit is not None and plane_fit['error'] < self.plane_tol

            if area_ratio >= 0.03 and is_planar:
                main_face_ids.update(region)
            else:
                feature_regions.append(region)

        print(f"          → {len(main_face_ids)} Hauptflächen-Faces, {len(feature_regions)} Feature-Regionen")

        # Klassifiziere Feature-Regionen
        fillets = []
        chamfers = []

        for region in feature_regions:
            if len(region) < self.min_faces:
                continue

            # Versuche Zylinder
            cyl = self._fit_cylinder_to_region(mesh, region, cell_normals)
            if cyl is not None and cyl['error'] < self.cyl_tol:
                fillet = FilletRegion(
                    face_ids=region,
                    axis=cyl['axis'],
                    axis_point=cyl['center'],
                    radius=cyl['radius'],
                    arc_angle=cyl['arc_angle'],
                    fit_error=cyl['error'],
                    confidence=1 - min(1, cyl['error'] / self.cyl_tol)
                )
                fillets.append(fillet)
                print(f"          Fillet: r={fillet.radius:.2f}mm, {len(region)} faces")
                continue

            # Versuche Plane
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

        print(f"    [5/6] Ergebnis: {len(fillets)} Fillets, {len(chamfers)} Chamfers")
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

    def _segment_mesh(
        self,
        mesh: pv.PolyData,
        edge_to_faces: Dict,
        cell_normals: np.ndarray,
        angle_threshold: float
    ) -> List[Set[int]]:
        n_faces = mesh.n_cells
        adjacency = lil_matrix((n_faces, n_faces), dtype=np.int8)
        angle_rad = np.radians(angle_threshold)

        for edge, face_ids in edge_to_faces.items():
            if len(face_ids) != 2:
                continue
            f1, f2 = face_ids
            n1, n2 = cell_normals[f1], cell_normals[f2]
            dot = np.clip(np.dot(n1, n2), -1, 1)
            if np.arccos(dot) <= angle_rad:
                adjacency[f1, f2] = 1
                adjacency[f2, f1] = 1

        n_components, labels = connected_components(adjacency.tocsr(), directed=False, return_labels=True)

        regions = []
        for label_id in range(n_components):
            face_ids = set(np.where(labels == label_id)[0])
            regions.append(face_ids)
        return regions

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

    def _find_best_cylinder(
        self,
        mesh: pv.PolyData,
        candidate_faces: Set[int],
        cell_normals: np.ndarray
    ) -> Optional[dict]:
        if len(candidate_faces) < 5:
            return None

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
            if len(points) < 6:
                break

            sample_idx = np.random.choice(len(points), 6, replace=False)
            sample = points[sample_idx]

            cyl = self._fit_cylinder_to_points(sample)
            if cyl is None:
                continue

            inlier_faces = self._find_cylinder_faces(mesh, candidate_faces, cyl, cell_normals)
            score = len(inlier_faces)

            if score > best_score and score >= 5:
                inlier_points = []
                for fid in inlier_faces:
                    cell = mesh.get_cell(fid)
                    inlier_points.extend(cell.points)
                inlier_points = np.unique(np.array(inlier_points), axis=0)

                refined_cyl = self._fit_cylinder_to_points(inlier_points)
                if refined_cyl is not None:
                    final_faces = self._find_cylinder_faces(mesh, candidate_faces, refined_cyl, cell_normals)
                    if len(final_faces) >= 5:
                        refined_cyl['face_ids'] = final_faces
                        best_cylinder = refined_cyl
                        best_score = len(final_faces)

        return best_cylinder

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

    def _fit_cylinder_to_region(
        self,
        mesh: pv.PolyData,
        face_ids: Set[int],
        cell_normals: np.ndarray
    ) -> Optional[dict]:
        points = []
        for fid in face_ids:
            cell = mesh.get_cell(fid)
            points.extend(cell.points)
        points = np.unique(np.array(points), axis=0)
        return self._fit_cylinder_to_points(points)

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

    detector = FilletChamferDetectorV8(
        small_face_threshold_ratio=0.01,
        min_region_faces=2,
        plane_tolerance=0.5,
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
    print("Fillet & Chamfer Detector V8 (Flächenbasiert)")
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
