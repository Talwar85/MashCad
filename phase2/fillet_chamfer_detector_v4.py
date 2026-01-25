"""
Fillet & Chamfer Detector V4
============================

Krümmungsbasierter Ansatz für Fillets:
- Hauptflächen haben NIEDRIGE Krümmung (flach)
- Fillets haben HOHE Krümmung (gekrümmt)
- Chamfers haben NIEDRIGE Krümmung aber sind SCHRÄG zu Hauptflächen

Algorithmus:
1. Berechne diskrete Krümmung pro Vertex
2. Klassifiziere Vertices: Flach vs Gekrümmt
3. Propagiere zu Faces
4. Segmentiere basierend auf Krümmungsklasse
5. Klassifiziere Regionen
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


class FilletChamferDetectorV4:
    """
    Krümmungsbasierter Fillet/Chamfer Detector.
    """

    def __init__(
        self,
        curvature_threshold: float = 0.02,  # Krümmungs-Schwelle für "gekrümmt"
        min_region_faces: int = 3,
        plane_tolerance: float = 0.5,
        cylinder_tolerance: float = 2.0
    ):
        self.curv_threshold = curvature_threshold
        self.min_faces = min_region_faces
        self.plane_tol = plane_tolerance
        self.cyl_tol = cylinder_tolerance

    def detect(self, mesh: pv.PolyData) -> Tuple[List[FilletRegion], List[ChamferRegion]]:
        """Erkennt Fillets und Chamfers."""

        print("    [1/7] Berechne Mesh-Strukturen...")

        if 'Normals' not in mesh.cell_data:
            mesh = mesh.compute_normals(cell_normals=True, point_normals=True)

        cell_normals = mesh.cell_data['Normals']
        point_normals = mesh.point_data.get('Normals')

        if point_normals is None:
            mesh = mesh.compute_normals(point_normals=True)
            point_normals = mesh.point_data['Normals']

        edge_to_faces = self._build_edge_face_map(mesh)

        # Schritt 1: Berechne Krümmung pro Vertex
        print("    [2/7] Berechne Vertex-Krümmung...")
        vertex_curvature = self._compute_vertex_curvature(mesh, point_normals)

        curv_stats = f"min={np.min(vertex_curvature):.4f}, max={np.max(vertex_curvature):.4f}, mean={np.mean(vertex_curvature):.4f}"
        print(f"          → {curv_stats}")

        # Schritt 2: Klassifiziere Vertices
        print("    [3/7] Klassifiziere Vertices...")
        is_curved_vertex = vertex_curvature > self.curv_threshold
        curved_count = np.sum(is_curved_vertex)
        print(f"          → {curved_count}/{len(vertex_curvature)} gekrümmte Vertices")

        # Schritt 3: Propagiere zu Faces
        print("    [4/7] Klassifiziere Faces nach Krümmung...")
        face_curvature = self._compute_face_curvature(mesh, vertex_curvature)
        is_curved_face = face_curvature > self.curv_threshold
        curved_faces = np.sum(is_curved_face)
        print(f"          → {curved_faces}/{mesh.n_cells} gekrümmte Faces")

        # Schritt 4: Segmentiere FLACHE Faces (Hauptflächen + Chamfers)
        print("    [5/7] Segmentiere flache Regionen...")
        flat_face_ids = set(np.where(~is_curved_face)[0])
        flat_regions = self._segment_faces(mesh, flat_face_ids, edge_to_faces, cell_normals)
        print(f"          → {len(flat_regions)} flache Regionen")

        # Schritt 5: Segmentiere GEKRÜMMTE Faces (Fillets)
        print("    [6/7] Segmentiere gekrümmte Regionen...")
        curved_face_ids = set(np.where(is_curved_face)[0])
        curved_regions = self._segment_faces(mesh, curved_face_ids, edge_to_faces, cell_normals,
                                             angle_threshold=30.0)  # Höherer Threshold für Fillets
        print(f"          → {len(curved_regions)} gekrümmte Regionen")

        # Schritt 6: Klassifiziere Regionen
        print("    [7/7] Klassifiziere Regionen...")

        # Berechne Flächeninhalte
        mesh_with_areas = mesh.compute_cell_sizes()
        areas = mesh_with_areas.cell_data['Area']
        total_area = np.sum(areas)

        fillets = []
        chamfers = []
        main_faces = []

        # Klassifiziere flache Regionen
        for region in flat_regions:
            if len(region) < self.min_faces:
                continue

            region_area = sum(areas[fid] for fid in region)
            area_ratio = region_area / total_area

            plane_fit = self._fit_plane(mesh, region)

            if plane_fit is None:
                continue

            # Große flache Regionen = Hauptflächen
            if area_ratio > 0.05:  # > 5% der Gesamtfläche
                main_faces.append({
                    'face_ids': region,
                    'normal': plane_fit['normal'],
                    'area': region_area
                })
            else:
                # Kleine flache Regionen könnten Chamfers sein
                if plane_fit['error'] < self.plane_tol:
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

        # Klassifiziere gekrümmte Regionen als Fillets
        for region in curved_regions:
            if len(region) < self.min_faces:
                continue

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
                print(f"          Fillet: r={fillet.radius:.2f}mm, arc={np.degrees(fillet.arc_angle):.1f}°, {len(region)} faces")

        print(f"    Ergebnis: {len(main_faces)} Hauptflächen, {len(fillets)} Fillets, {len(chamfers)} Chamfers")

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

    def _compute_vertex_curvature(
        self,
        mesh: pv.PolyData,
        point_normals: np.ndarray
    ) -> np.ndarray:
        """
        Berechnet diskrete Krümmung pro Vertex.

        Methode: Mittlere Normalenabweichung zu Nachbarn
        """

        n_vertices = mesh.n_points
        curvature = np.zeros(n_vertices)

        # Baue Vertex-Nachbarschaft
        vertex_neighbors = defaultdict(set)
        for face_id in range(mesh.n_cells):
            cell = mesh.get_cell(face_id)
            pts = cell.point_ids
            for i in range(len(pts)):
                v1 = pts[i]
                v2 = pts[(i + 1) % len(pts)]
                vertex_neighbors[v1].add(v2)
                vertex_neighbors[v2].add(v1)

        # Berechne Krümmung als Normalen-Varianz
        for v_id in range(n_vertices):
            neighbors = vertex_neighbors[v_id]
            if len(neighbors) < 2:
                continue

            v_normal = point_normals[v_id]
            neighbor_normals = [point_normals[n] for n in neighbors]

            # Mittlerer Winkel zu Nachbar-Normalen
            angles = []
            for n_normal in neighbor_normals:
                dot = np.clip(np.dot(v_normal, n_normal), -1, 1)
                angle = np.arccos(dot)
                angles.append(angle)

            curvature[v_id] = np.mean(angles)

        return curvature

    def _compute_face_curvature(
        self,
        mesh: pv.PolyData,
        vertex_curvature: np.ndarray
    ) -> np.ndarray:
        """Berechnet mittlere Krümmung pro Face."""

        face_curvature = np.zeros(mesh.n_cells)

        for face_id in range(mesh.n_cells):
            cell = mesh.get_cell(face_id)
            pts = cell.point_ids
            curv_values = [vertex_curvature[p] for p in pts]
            face_curvature[face_id] = np.mean(curv_values)

        return face_curvature

    def _segment_faces(
        self,
        mesh: pv.PolyData,
        face_ids: Set[int],
        edge_to_faces: Dict[Tuple[int, int], List[int]],
        cell_normals: np.ndarray,
        angle_threshold: float = 15.0
    ) -> List[Set[int]]:
        """Segmentiert eine Menge von Faces in zusammenhängende Regionen."""

        if not face_ids:
            return []

        angle_rad = np.radians(angle_threshold)

        # Erstelle Adjacency nur für die gegebenen Faces
        face_list = list(face_ids)
        face_to_idx = {f: i for i, f in enumerate(face_list)}
        n = len(face_list)

        adjacency = lil_matrix((n, n), dtype=np.int8)

        for edge, faces in edge_to_faces.items():
            if len(faces) != 2:
                continue

            f1, f2 = faces
            if f1 not in face_ids or f2 not in face_ids:
                continue

            # Prüfe Normalen-Ähnlichkeit
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
            if len(region) >= self.min_faces:
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

    detector = FilletChamferDetectorV4(
        curvature_threshold=0.05,  # ~3° Normalenabweichung
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
                  f"Faces={len(f.face_ids)}, "
                  f"Error={f.fit_error:.2f}mm")

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
    print("Fillet & Chamfer Detector V4 (Krümmungsbasiert)")
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
