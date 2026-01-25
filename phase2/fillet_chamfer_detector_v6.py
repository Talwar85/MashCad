"""
Fillet & Chamfer Detector V6
============================

Kombinierter Ansatz:
- Chamfers: V3 Ansatz (Segmentierung + Plane-Fit) - FUNKTIONIERT
- Fillets: RANSAC-basierte Zylindererkennung - NEU

Für Fillets:
1. RANSAC findet Zylinder in der Punktwolke
2. Jeder gefundene Zylinder ist ein Fillet
3. Faces die zum Zylinder gehören werden markiert
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


class FilletChamferDetectorV6:
    """
    Kombinierter Detector: V3 für Chamfers + RANSAC für Fillets.
    """

    def __init__(
        self,
        segmentation_threshold: float = 10.0,
        main_face_min_area_ratio: float = 0.03,
        plane_tolerance: float = 0.3,
        cylinder_tolerance: float = 2.0,
        ransac_iterations: int = 500,
        ransac_min_inliers: int = 20
    ):
        self.seg_threshold = np.radians(segmentation_threshold)
        self.main_face_ratio = main_face_min_area_ratio
        self.plane_tol = plane_tolerance
        self.cyl_tol = cylinder_tolerance
        self.ransac_iter = ransac_iterations
        self.ransac_min_inliers = ransac_min_inliers

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

        # === PHASE 1: Finde Hauptflächen (große planare Regionen) ===
        print("    [2/6] Segmentiere und finde Hauptflächen...")
        regions = self._segment_mesh(mesh, edge_to_faces, cell_normals)

        main_face_ids = set()
        for region in regions:
            region_area = sum(areas[fid] for fid in region)
            area_ratio = region_area / total_area

            if area_ratio >= self.main_face_ratio:
                plane_fit = self._fit_plane(mesh, region)
                if plane_fit is not None and plane_fit['error'] < self.plane_tol:
                    main_face_ids.update(region)

        feature_face_ids = set(range(mesh.n_cells)) - main_face_ids
        print(f"          → {len(main_face_ids)} Hauptflächen-Faces, {len(feature_face_ids)} Feature-Faces")

        # === PHASE 2: RANSAC Zylinder-Erkennung für Fillets ===
        print("    [3/6] RANSAC Zylinder-Erkennung...")

        # Sammle alle Punkte der Feature-Faces
        feature_points = []
        point_to_faces = defaultdict(set)

        for fid in feature_face_ids:
            cell = mesh.get_cell(fid)
            for pt in cell.points:
                pt_tuple = tuple(pt)
                if pt_tuple not in point_to_faces:
                    feature_points.append(pt)
                point_to_faces[pt_tuple].add(fid)

        feature_points = np.array(feature_points) if feature_points else np.array([]).reshape(0, 3)
        print(f"          → {len(feature_points)} Feature-Punkte")

        fillets = []
        remaining_points = set(range(len(feature_points)))
        used_face_ids = set()

        while len(remaining_points) >= self.ransac_min_inliers:
            # RANSAC für einen Zylinder
            best_cylinder = self._ransac_cylinder(
                feature_points,
                remaining_points,
                cell_normals,
                feature_face_ids - used_face_ids,
                mesh
            )

            if best_cylinder is None:
                break

            # Erstelle Fillet
            fillet = FilletRegion(
                face_ids=best_cylinder['face_ids'],
                axis=best_cylinder['axis'],
                axis_point=best_cylinder['center'],
                radius=best_cylinder['radius'],
                arc_angle=best_cylinder['arc_angle'],
                fit_error=best_cylinder['error'],
                confidence=best_cylinder['inlier_ratio']
            )
            fillets.append(fillet)
            print(f"          Fillet: r={fillet.radius:.2f}mm, arc={np.degrees(fillet.arc_angle):.1f}°, "
                  f"{len(fillet.face_ids)} faces, err={fillet.fit_error:.2f}mm")

            # Entferne verwendete Punkte und Faces
            used_face_ids.update(best_cylinder['face_ids'])
            for fid in best_cylinder['face_ids']:
                cell = mesh.get_cell(fid)
                for pt in cell.points:
                    for i, fp in enumerate(feature_points):
                        if i in remaining_points and np.allclose(fp, pt):
                            remaining_points.discard(i)

        # === PHASE 3: Chamfer-Erkennung für verbleibende Feature-Faces ===
        print("    [4/6] Chamfer-Erkennung...")

        remaining_feature_faces = feature_face_ids - used_face_ids
        chamfer_regions = self._segment_faces(mesh, remaining_feature_faces, edge_to_faces, cell_normals)

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

        print(f"    [5/6] Ergebnis: {len(fillets)} Fillets, {len(chamfers)} Chamfers")

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

    def _segment_mesh(
        self,
        mesh: pv.PolyData,
        edge_to_faces: Dict[Tuple[int, int], List[int]],
        cell_normals: np.ndarray
    ) -> List[Set[int]]:
        """Segmentiert Mesh in Regionen."""
        n_faces = mesh.n_cells
        adjacency = lil_matrix((n_faces, n_faces), dtype=np.int8)

        for edge, face_ids in edge_to_faces.items():
            if len(face_ids) != 2:
                continue
            f1, f2 = face_ids
            n1, n2 = cell_normals[f1], cell_normals[f2]
            dot = np.clip(np.dot(n1, n2), -1, 1)
            angle = np.arccos(dot)
            if angle <= self.seg_threshold:
                adjacency[f1, f2] = 1
                adjacency[f2, f1] = 1

        n_components, labels = connected_components(
            adjacency.tocsr(), directed=False, return_labels=True
        )

        regions = []
        for label_id in range(n_components):
            face_ids = set(np.where(labels == label_id)[0])
            regions.append(face_ids)
        return regions

    def _segment_faces(
        self,
        mesh: pv.PolyData,
        face_ids: Set[int],
        edge_to_faces: Dict[Tuple[int, int], List[int]],
        cell_normals: np.ndarray,
        angle_threshold: float = 15.0
    ) -> List[Set[int]]:
        """Segmentiert eine Teilmenge von Faces."""
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
            angle = np.arccos(dot)
            if angle <= angle_rad:
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

            return {'normal': normal, 'centroid': centroid, 'error': error}
        except Exception:
            return None

    def _ransac_cylinder(
        self,
        all_points: np.ndarray,
        remaining_indices: Set[int],
        cell_normals: np.ndarray,
        candidate_faces: Set[int],
        mesh: pv.PolyData
    ) -> Optional[dict]:
        """
        RANSAC für Zylinder-Erkennung.

        Methode:
        1. Wähle zufällig 2 Punkte → definieren Achse
        2. Wähle zufällig 1 weiteren Punkt → definiert Radius
        3. Zähle Inlier
        4. Wiederhole und behalte bestes Modell
        """

        if len(remaining_indices) < self.ransac_min_inliers:
            return None

        remaining_list = list(remaining_indices)
        points = all_points[remaining_list]

        best_result = None
        best_inliers = 0

        for _ in range(self.ransac_iter):
            if len(points) < 6:
                break

            # Wähle 6 zufällige Punkte
            sample_idx = np.random.choice(len(points), min(6, len(points)), replace=False)
            sample = points[sample_idx]

            # Fitte Zylinder auf Sample
            cyl = self._fit_cylinder_to_points(sample)
            if cyl is None:
                continue

            # Zähle Inlier
            distances = self._point_cylinder_distances(points, cyl['axis'], cyl['center'], cyl['radius'])
            inlier_mask = distances < self.cyl_tol
            n_inliers = np.sum(inlier_mask)

            if n_inliers > best_inliers and n_inliers >= self.ransac_min_inliers:
                # Refit auf allen Inliern
                inlier_points = points[inlier_mask]
                refined_cyl = self._fit_cylinder_to_points(inlier_points)

                if refined_cyl is not None:
                    # Berechne zugehörige Faces
                    face_ids = self._find_cylinder_faces(
                        mesh, candidate_faces, refined_cyl, cell_normals
                    )

                    if len(face_ids) >= 3:
                        refined_cyl['face_ids'] = face_ids
                        refined_cyl['inlier_ratio'] = n_inliers / len(points)
                        best_result = refined_cyl
                        best_inliers = n_inliers

        return best_result

    def _fit_cylinder_to_points(self, points: np.ndarray) -> Optional[dict]:
        """Fittet einen Zylinder auf Punkte."""
        if len(points) < 6:
            return None

        try:
            # PCA für Achsenrichtung
            centroid = np.mean(points, axis=0)
            centered = points - centroid

            U, S, Vt = np.linalg.svd(centered, full_matrices=False)

            # Achse = Richtung mit GRÖSSTER Varianz (längste Ausdehnung)
            axis = Vt[0]

            # Projiziere auf Ebene senkrecht zur Achse
            proj = np.dot(centered, axis)[:, np.newaxis] * axis
            perp = centered - proj
            distances = np.linalg.norm(perp, axis=1)

            radius = np.median(distances)
            if radius < 0.3 or radius > 50:
                return None

            error = np.mean(np.abs(distances - radius))

            # Bogenwinkel
            if abs(axis[2]) < 0.9:
                x_local = np.cross(axis, [0, 0, 1])
            else:
                x_local = np.cross(axis, [1, 0, 0])
            x_local = x_local / np.linalg.norm(x_local)
            y_local = np.cross(axis, x_local)

            angles = []
            for rel in centered:
                h = np.dot(rel, axis)
                p = rel - h * axis
                if np.linalg.norm(p) > 1e-6:
                    pn = p / np.linalg.norm(p)
                    ang = np.arctan2(np.dot(pn, y_local), np.dot(pn, x_local))
                    angles.append(ang)

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

        except Exception:
            return None

    def _point_cylinder_distances(
        self,
        points: np.ndarray,
        axis: np.ndarray,
        center: np.ndarray,
        radius: float
    ) -> np.ndarray:
        """Berechnet Abstände der Punkte zur Zylinderoberfläche."""
        centered = points - center
        proj = np.dot(centered, axis)[:, np.newaxis] * axis
        perp = centered - proj
        distances = np.abs(np.linalg.norm(perp, axis=1) - radius)
        return distances

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

            # Prüfe ob alle Punkte auf dem Zylinder liegen
            distances = self._point_cylinder_distances(
                pts, cylinder['axis'], cylinder['center'], cylinder['radius']
            )

            if np.max(distances) < self.cyl_tol * 2:
                # Zusätzlich: Normale sollte senkrecht zur Achse sein
                face_normal = cell_normals[fid]
                dot = abs(np.dot(face_normal, cylinder['axis']))
                if dot < 0.5:  # < 60° von senkrecht
                    face_ids.add(fid)

        return face_ids

    def _compute_region_width(
        self,
        mesh: pv.PolyData,
        face_ids: Set[int],
        plane_fit: dict
    ) -> float:
        """Berechnet Regions-Breite."""
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

        return min(np.ptp(proj_u), np.ptp(proj_v))


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

    detector = FilletChamferDetectorV6(
        segmentation_threshold=10.0,
        main_face_min_area_ratio=0.03,
        plane_tolerance=0.3,
        cylinder_tolerance=2.0,
        ransac_iterations=500,
        ransac_min_inliers=15
    )

    fillets, chamfers = detector.detect(mesh)

    print(f"\nErgebnis:")
    print(f"  Fillets: {len(fillets)}")
    print(f"  Chamfers: {len(chamfers)}")

    if fillets:
        print("\nFillet-Details:")
        for i, f in enumerate(fillets):
            print(f"  [{i+1}] r={f.radius:.2f}mm, arc={np.degrees(f.arc_angle):.1f}°, "
                  f"{len(f.face_ids)} faces")

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
    print("Fillet & Chamfer Detector V6 (RANSAC Zylinder)")
    print("=" * 60)

    stl_dir = Path(__file__).parent.parent / "stl"

    results = []

    r1 = test_detector(str(stl_dir / "verrunden.stl"), expected_fillets=5, expected_chamfers=0)
    results.append(("verrunden.stl", r1))

    print("\n")

    r2 = test_detector(str(stl_dir / "fase.stl"), expected_fillets=0, expected_chamfers=5)
    results.append(("fase.stl", r2))

    print("\n" + "=" * 60)
    print("ZUSAMMENFASSUNG")
    print("=" * 60)
    for name, passed in results:
        print(f"  {'✓' if passed else '✗'} {name}")
