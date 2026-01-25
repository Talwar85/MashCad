"""
Fillet & Chamfer Detector V3
============================

Neuer Ansatz basierend auf User-Feedback:
- Wo Fasen/Fillets aufeinandertreffen entstehen "Miter"-Flächen
- Strategie: Erst HAUPTFLÄCHEN finden, dann den REST als Features klassifizieren

Algorithmus:
1. Segmentiere Mesh mit niedrigem Threshold (alle Regionen)
2. Identifiziere HAUPTFLÄCHEN (große planare Regionen)
3. Der REST sind Feature-Regionen (Chamfers, Fillets, Miter)
4. Gruppiere Feature-Regionen nach Nachbarschaft zu gleichen Hauptflächen-Paaren
5. Klassifiziere: Planar = Chamfer, Gekrümmt = Fillet
"""

import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
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


class FilletChamferDetectorV3:
    """
    Erkennt Fillets und Chamfers durch Hauptflächen-Identifikation.
    """

    def __init__(
        self,
        segmentation_threshold: float = 15.0,  # Niedrig für feine Segmentierung
        main_face_min_area_ratio: float = 0.05,  # Min 5% der Gesamtfläche
        plane_tolerance: float = 0.3,
        cylinder_tolerance: float = 1.5
    ):
        self.seg_threshold = np.radians(segmentation_threshold)
        self.main_face_ratio = main_face_min_area_ratio
        self.plane_tol = plane_tolerance
        self.cyl_tol = cylinder_tolerance

    def detect(self, mesh: pv.PolyData) -> Tuple[List[FilletRegion], List[ChamferRegion]]:
        """Erkennt Fillets und Chamfers."""

        print("    [1/6] Berechne Mesh-Strukturen...")

        if 'Normals' not in mesh.cell_data:
            mesh = mesh.compute_normals(cell_normals=True, point_normals=False)

        cell_normals = mesh.cell_data['Normals']

        # Berechne Flächeninhalte
        mesh_with_areas = mesh.compute_cell_sizes()
        areas = mesh_with_areas.cell_data['Area']
        total_area = np.sum(areas)

        edge_to_faces = self._build_edge_face_map(mesh)

        # Schritt 1: Feine Segmentierung
        print("    [2/6] Segmentiere Mesh...")
        regions = self._segment_mesh(mesh, edge_to_faces, cell_normals)
        print(f"          → {len(regions)} Regionen")

        # Schritt 2: Klassifiziere Regionen nach Größe und Planarität
        print("    [3/6] Identifiziere Hauptflächen...")
        main_faces = []
        feature_regions = []

        for region in regions:
            region_area = sum(areas[fid] for fid in region)
            area_ratio = region_area / total_area

            # Prüfe Planarität
            plane_fit = self._fit_plane(mesh, region, cell_normals)

            is_planar = plane_fit is not None and plane_fit['error'] < self.plane_tol
            is_large = area_ratio >= self.main_face_ratio

            if is_planar and is_large:
                main_faces.append({
                    'face_ids': region,
                    'normal': plane_fit['normal'],
                    'centroid': plane_fit['centroid'],
                    'area': region_area
                })
            else:
                feature_regions.append({
                    'face_ids': region,
                    'area': region_area,
                    'plane_fit': plane_fit
                })

        print(f"          → {len(main_faces)} Hauptflächen, {len(feature_regions)} Feature-Regionen")

        # Schritt 3: Analysiere Feature-Regionen
        print("    [4/6] Analysiere Feature-Regionen...")

        # Finde Nachbarschaften zwischen Feature-Regionen und Hauptflächen
        region_neighbors = self._find_region_neighbors(
            mesh, regions, main_faces, feature_regions, edge_to_faces
        )

        # Schritt 4: Gruppiere Feature-Regionen die zum selben Feature gehören
        print("    [5/6] Gruppiere Features...")
        feature_groups = self._group_features(
            feature_regions, region_neighbors, main_faces
        )

        print(f"          → {len(feature_groups)} Feature-Gruppen")

        # Schritt 5: Klassifiziere Features
        print("    [6/6] Klassifiziere Features...")
        fillets = []
        chamfers = []

        for group in feature_groups:
            # Sammle alle Faces der Gruppe
            all_face_ids = set()
            for region_idx in group['region_indices']:
                all_face_ids.update(feature_regions[region_idx]['face_ids'])

            # Versuche Zylinder-Fit (Fillet)
            cyl_fit = self._fit_cylinder(mesh, all_face_ids, cell_normals)

            if cyl_fit is not None and cyl_fit['error'] < self.cyl_tol:
                fillet = FilletRegion(
                    face_ids=all_face_ids,
                    axis=cyl_fit['axis'],
                    axis_point=cyl_fit['centroid'],
                    radius=cyl_fit['radius'],
                    arc_angle=cyl_fit['arc_angle'],
                    fit_error=cyl_fit['error'],
                    confidence=max(0, 1 - cyl_fit['error'] / self.cyl_tol)
                )
                fillets.append(fillet)
                print(f"          Fillet: r={fillet.radius:.2f}mm, {len(all_face_ids)} faces")
                continue

            # Versuche Plane-Fit (Chamfer)
            plane_fit = self._fit_plane(mesh, all_face_ids, cell_normals)

            if plane_fit is not None and plane_fit['error'] < self.plane_tol:
                width = self._compute_chamfer_width(mesh, all_face_ids, plane_fit)
                chamfer = ChamferRegion(
                    face_ids=all_face_ids,
                    normal=plane_fit['normal'],
                    plane_point=plane_fit['centroid'],
                    width=width,
                    chamfer_angle=45.0,  # TODO: berechnen
                    fit_error=plane_fit['error']
                )
                chamfers.append(chamfer)
                print(f"          Chamfer: w={width:.2f}mm, {len(all_face_ids)} faces")

        print(f"    Ergebnis: {len(fillets)} Fillets, {len(chamfers)} Chamfers")

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
        """Segmentiert Mesh in Regionen basierend auf Normalen-Ähnlichkeit."""

        n_faces = mesh.n_cells
        adjacency = lil_matrix((n_faces, n_faces), dtype=np.int8)

        for edge, face_ids in edge_to_faces.items():
            if len(face_ids) != 2:
                continue

            f1, f2 = face_ids
            n1, n2 = cell_normals[f1], cell_normals[f2]

            dot = np.clip(np.dot(n1, n2), -1, 1)
            angle = np.arccos(dot)

            # Verbinde nur wenn Normalen ähnlich genug
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

    def _fit_plane(
        self,
        mesh: pv.PolyData,
        face_ids: Set[int],
        cell_normals: np.ndarray
    ) -> Optional[dict]:
        """Fittet eine Ebene auf die Faces."""

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
        """Fittet einen Zylinder auf die Faces."""

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

            # PCA auf Normalen für Achsen-Richtung
            from sklearn.decomposition import PCA

            pca = PCA(n_components=3)
            pca.fit(unique_normals)

            # Achse = Richtung mit kleinster Varianz in den Normalen
            axis = pca.components_[-1]

            # Prüfe ob Normalen senkrecht zur Achse
            dots = np.abs(np.dot(unique_normals, axis))
            if np.mean(dots) > 0.4:
                return None

            # Berechne Radius
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

    def _find_region_neighbors(
        self,
        mesh: pv.PolyData,
        all_regions: List[Set[int]],
        main_faces: List[dict],
        feature_regions: List[dict],
        edge_to_faces: Dict[Tuple[int, int], List[int]]
    ) -> Dict[int, Set[int]]:
        """
        Findet für jede Feature-Region die benachbarten Hauptflächen.

        Returns:
            Dict von feature_region_idx -> Set von main_face_idx
        """

        # Erstelle Face-zu-Region Mapping
        face_to_main = {}
        for idx, mf in enumerate(main_faces):
            for fid in mf['face_ids']:
                face_to_main[fid] = idx

        face_to_feature = {}
        for idx, fr in enumerate(feature_regions):
            for fid in fr['face_ids']:
                face_to_feature[fid] = idx

        # Finde Nachbarschaften
        neighbors = defaultdict(set)

        for edge, face_ids in edge_to_faces.items():
            if len(face_ids) != 2:
                continue

            f1, f2 = face_ids

            # Feature neben Hauptfläche?
            if f1 in face_to_feature and f2 in face_to_main:
                neighbors[face_to_feature[f1]].add(face_to_main[f2])
            if f2 in face_to_feature and f1 in face_to_main:
                neighbors[face_to_feature[f2]].add(face_to_main[f1])

        return neighbors

    def _group_features(
        self,
        feature_regions: List[dict],
        region_neighbors: Dict[int, Set[int]],
        main_faces: List[dict]
    ) -> List[dict]:
        """
        Gruppiert Feature-Regionen die zum selben Feature gehören.

        Kriterium: Feature-Regionen die dieselben Hauptflächen als Nachbarn haben
        gehören wahrscheinlich zum selben Chamfer/Fillet.
        """

        # Einfacher Ansatz: Jede Feature-Region ist ein Feature
        # (Für komplexere Fälle: Gruppierung nach Nachbar-Hauptflächen)

        groups = []
        for idx, fr in enumerate(feature_regions):
            groups.append({
                'region_indices': [idx],
                'neighbor_mains': region_neighbors.get(idx, set())
            })

        return groups

    def _compute_chamfer_width(
        self,
        mesh: pv.PolyData,
        face_ids: Set[int],
        plane_fit: dict
    ) -> float:
        """Berechnet die Chamfer-Breite."""

        points = []
        for fid in face_ids:
            cell = mesh.get_cell(fid)
            points.extend(cell.points)

        points = np.array(points)
        centroid = plane_fit['centroid']
        normal = plane_fit['normal']

        # Finde 2 Richtungen in der Ebene
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

    detector = FilletChamferDetectorV3(
        segmentation_threshold=10.0,  # Sehr fein
        main_face_min_area_ratio=0.03,  # 3% der Fläche
        plane_tolerance=0.3,
        cylinder_tolerance=2.0
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
    print("Fillet & Chamfer Detector V3")
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
