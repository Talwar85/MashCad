"""
Fillet & Chamfer Detector V2
============================

Korrigierte Logik basierend auf Mesh-Analyse:

Fillets (Verrundungen):
- Sind zylindrische Streifen aus VIELEN kleinen Dreiecken
- Benachbarte Dreiecke haben KLEINE Winkeländerungen (5-30°)
- Die Summe der Winkel über den Streifen ergibt ~90°
- Die Grenzen zum Rest sind SCHARFE Kanten (>60°)

Chamfers (Fasen):
- Sind planare Streifen aus WENIGEN Dreiecken
- Alle Dreiecke haben DIESELBE Normale
- Die Grenzen sind ebenfalls SCHARFE Kanten (~45° typisch)

Algorithmus:
1. Finde SCHARFE Kanten (>45° Diederwinkel) - das sind die Grenzen
2. Gruppiere Faces zwischen scharfen Kanten
3. Für jede Gruppe: Prüfe ob planar (Chamfer) oder gekrümmt (Fillet)
4. Fitte analytische Oberflächen
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
    axis: np.ndarray           # Zylinder-Achse
    axis_point: np.ndarray     # Punkt auf der Achse
    radius: float              # Fillet-Radius
    arc_angle: float           # Bogenwinkel in Radians
    fit_error: float           # Mittlerer Fit-Fehler
    confidence: float          # Konfidenz 0-1


@dataclass
class ChamferRegion:
    """Eine erkannte Chamfer-Region."""
    face_ids: Set[int]
    normal: np.ndarray         # Ebenen-Normale
    plane_point: np.ndarray    # Punkt auf der Ebene
    width: float               # Chamfer-Breite
    chamfer_angle: float       # Chamfer-Winkel (typisch 45°)
    fit_error: float


class FilletChamferDetector:
    """
    Erkennt Fillets und Chamfers basierend auf Region-Segmentierung.
    """

    def __init__(
        self,
        sharp_edge_threshold: float = 45.0,   # Grad - Grenze für scharfe Kanten
        min_region_faces: int = 3,            # Minimum Faces pro Region
        plane_tolerance: float = 0.5,         # mm - Toleranz für Plane-Fit
        cylinder_tolerance: float = 1.0       # mm - Toleranz für Zylinder-Fit
    ):
        self.sharp_threshold = np.radians(sharp_edge_threshold)
        self.min_faces = min_region_faces
        self.plane_tol = plane_tolerance
        self.cyl_tol = cylinder_tolerance

    def detect(self, mesh: pv.PolyData) -> Tuple[List[FilletRegion], List[ChamferRegion]]:
        """
        Erkennt Fillets und Chamfers im Mesh.

        Returns:
            (Liste von FilletRegions, Liste von ChamferRegions)
        """
        print("    [1/5] Berechne Mesh-Strukturen...")

        # Normalen berechnen
        if 'Normals' not in mesh.cell_data:
            mesh = mesh.compute_normals(cell_normals=True, point_normals=False)

        cell_normals = mesh.cell_data['Normals']

        # Baue Edge-zu-Face Mapping
        edge_to_faces = self._build_edge_face_map(mesh)

        # Finde scharfe Kanten
        print("    [2/5] Finde scharfe Kanten (Grenzen)...")
        sharp_edges = self._find_sharp_edges(mesh, edge_to_faces, cell_normals)
        print(f"          → {len(sharp_edges)} scharfe Kanten gefunden")

        # Segmentiere Mesh in Regionen (getrennt durch scharfe Kanten)
        print("    [3/5] Segmentiere Mesh in Regionen...")
        regions = self._segment_by_sharp_edges(mesh, edge_to_faces, cell_normals, sharp_edges)
        print(f"          → {len(regions)} Regionen gefunden")

        # Klassifiziere jede Region
        print("    [4/5] Klassifiziere Regionen...")
        fillets = []
        chamfers = []
        other_count = 0

        for region_faces in regions:
            if len(region_faces) < self.min_faces:
                continue

            # Sammle Punkte und Normalen der Region
            points, normals = self._get_region_geometry(mesh, region_faces, cell_normals)

            # Prüfe ob planar (Chamfer-Kandidat)
            plane_fit = self._fit_plane(points)

            if plane_fit is not None and plane_fit['error'] < self.plane_tol:
                # Es ist eine planare Region
                # Prüfe ob es ein Chamfer ist (hat scharfe Grenzen auf beiden Seiten)
                chamfer = self._create_chamfer_region(
                    mesh, region_faces, plane_fit, sharp_edges, edge_to_faces
                )
                if chamfer is not None:
                    chamfers.append(chamfer)
                    continue

            # Prüfe ob zylindrisch (Fillet-Kandidat)
            cyl_fit = self._fit_cylinder(points, normals)

            if cyl_fit is not None and cyl_fit['error'] < self.cyl_tol:
                fillet = self._create_fillet_region(
                    mesh, region_faces, cyl_fit, sharp_edges
                )
                if fillet is not None:
                    fillets.append(fillet)
                    continue

            other_count += 1

        print(f"    [5/5] Ergebnis: {len(fillets)} Fillets, {len(chamfers)} Chamfers, {other_count} Andere")

        return fillets, chamfers

    def _build_edge_face_map(self, mesh: pv.PolyData) -> Dict[Tuple[int, int], List[int]]:
        """Baut Mapping von Kanten zu angrenzenden Faces."""
        edge_to_faces = defaultdict(list)

        for face_id in range(mesh.n_cells):
            cell = mesh.get_cell(face_id)
            pts = cell.point_ids

            for i in range(len(pts)):
                edge = tuple(sorted([pts[i], pts[(i + 1) % len(pts)]]))
                edge_to_faces[edge].append(face_id)

        return edge_to_faces

    def _find_sharp_edges(
        self,
        mesh: pv.PolyData,
        edge_to_faces: Dict[Tuple[int, int], List[int]],
        cell_normals: np.ndarray
    ) -> Set[Tuple[int, int]]:
        """Findet alle scharfen Kanten (große Diederwinkel)."""

        sharp_edges = set()

        for edge, face_ids in edge_to_faces.items():
            if len(face_ids) != 2:
                # Boundary edge oder Non-Manifold
                sharp_edges.add(edge)
                continue

            f1, f2 = face_ids
            n1, n2 = cell_normals[f1], cell_normals[f2]

            dot = np.clip(np.dot(n1, n2), -1, 1)
            dihedral_angle = np.arccos(dot)

            if dihedral_angle > self.sharp_threshold:
                sharp_edges.add(edge)

        return sharp_edges

    def _segment_by_sharp_edges(
        self,
        mesh: pv.PolyData,
        edge_to_faces: Dict[Tuple[int, int], List[int]],
        cell_normals: np.ndarray,
        sharp_edges: Set[Tuple[int, int]]
    ) -> List[Set[int]]:
        """
        Segmentiert das Mesh in Regionen, getrennt durch scharfe Kanten.

        Verwendet Flood-Fill: Faces die durch NICHT-scharfe Kanten verbunden
        sind, gehören zur selben Region.
        """

        # Baue Adjacency ohne scharfe Kanten
        n_faces = mesh.n_cells
        adjacency = lil_matrix((n_faces, n_faces), dtype=np.int8)

        for edge, face_ids in edge_to_faces.items():
            if len(face_ids) == 2 and edge not in sharp_edges:
                f1, f2 = face_ids
                adjacency[f1, f2] = 1
                adjacency[f2, f1] = 1

        # Connected Components
        n_components, labels = connected_components(
            adjacency.tocsr(),
            directed=False,
            return_labels=True
        )

        # Gruppiere Faces nach Label
        regions = []
        for label_id in range(n_components):
            face_ids = set(np.where(labels == label_id)[0])
            if len(face_ids) >= self.min_faces:
                regions.append(face_ids)

        return regions

    def _get_region_geometry(
        self,
        mesh: pv.PolyData,
        face_ids: Set[int],
        cell_normals: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Sammelt Punkte und Normalen einer Region."""

        points = []
        normals = []

        for face_id in face_ids:
            cell = mesh.get_cell(face_id)
            pts = cell.points
            n = cell_normals[face_id]

            for pt in pts:
                points.append(pt)
                normals.append(n)

        return np.array(points), np.array(normals)

    def _fit_plane(self, points: np.ndarray) -> Optional[dict]:
        """Fittet eine Ebene auf die Punkte."""

        if len(points) < 3:
            return None

        try:
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
        points: np.ndarray,
        normals: np.ndarray
    ) -> Optional[dict]:
        """
        Fittet einen Zylinder auf die Punkte.

        Methode:
        1. PCA auf Normalen → Achse ist Richtung mit kleinster Varianz
        2. Projiziere Punkte auf Ebene senkrecht zur Achse
        3. Fitte Kreis in 2D
        """

        if len(points) < 10:
            return None

        try:
            unique_points = np.unique(points, axis=0)
            if len(unique_points) < 10:
                return None

            # Achse aus Normalen-PCA
            # Für einen Zylinder zeigen alle Normalen senkrecht zur Achse
            # Die Richtung mit der kleinsten Varianz ist die Achse
            from sklearn.decomposition import PCA

            unique_normals = np.unique(normals, axis=0)
            if len(unique_normals) < 3:
                return None

            pca = PCA(n_components=3)
            pca.fit(unique_normals)

            # Die Achse ist die Richtung mit kleinster Varianz in den Normalen
            axis = pca.components_[-1]  # Kleinste Varianz

            # Prüfe ob die Normalen wirklich senkrecht zur Achse stehen
            dots = np.abs(np.dot(unique_normals, axis))
            if np.mean(dots) > 0.3:  # Normalen sollten fast senkrecht sein
                return None

            # Projiziere Punkte auf Ebene senkrecht zur Achse
            centroid = np.mean(unique_points, axis=0)
            centered = unique_points - centroid

            proj_along_axis = np.dot(centered, axis)[:, np.newaxis] * axis
            perpendicular = centered - proj_along_axis
            distances = np.linalg.norm(perpendicular, axis=1)

            # Radius = Median der Abstände
            radius = np.median(distances)

            if radius < 0.5 or radius > 50:  # Plausibilitätsprüfung
                return None

            # Fehler berechnen
            errors = np.abs(distances - radius)
            error = np.mean(errors)

            # Bogenwinkel berechnen
            # Lokales Koordinatensystem
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

            if len(angles) < 5:
                return None

            angles = np.array(angles)

            # Berechne Bogenwinkel (berücksichtige Wrap-Around)
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

        except Exception as e:
            return None

    def _create_chamfer_region(
        self,
        mesh: pv.PolyData,
        face_ids: Set[int],
        plane_fit: dict,
        sharp_edges: Set[Tuple[int, int]],
        edge_to_faces: Dict[Tuple[int, int], List[int]]
    ) -> Optional[ChamferRegion]:
        """Erstellt eine ChamferRegion wenn die Region ein Chamfer ist."""

        # Prüfe ob die Region von scharfen Kanten begrenzt wird
        boundary_sharp_count = 0
        for face_id in face_ids:
            cell = mesh.get_cell(face_id)
            pts = cell.point_ids
            for i in range(len(pts)):
                edge = tuple(sorted([pts[i], pts[(i + 1) % len(pts)]]))
                if edge in sharp_edges:
                    # Prüfe ob die andere Seite NICHT in dieser Region ist
                    neighbors = edge_to_faces.get(edge, [])
                    for n in neighbors:
                        if n not in face_ids:
                            boundary_sharp_count += 1
                            break

        if boundary_sharp_count < 2:  # Mindestens 2 scharfe Grenz-Kanten
            return None

        # Berechne Chamfer-Breite (maximale Ausdehnung der Region)
        all_points = []
        for face_id in face_ids:
            cell = mesh.get_cell(face_id)
            all_points.extend(cell.points)

        all_points = np.array(all_points)

        # Breite in Richtung senkrecht zur Normale
        centroid = plane_fit['centroid']
        normal = plane_fit['normal']

        # Finde 2 Richtungen in der Ebene
        if abs(normal[2]) < 0.9:
            u = np.cross(normal, [0, 0, 1])
        else:
            u = np.cross(normal, [1, 0, 0])
        u = u / np.linalg.norm(u)
        v = np.cross(normal, u)

        centered = all_points - centroid
        proj_u = np.dot(centered, u)
        proj_v = np.dot(centered, v)

        width_u = np.max(proj_u) - np.min(proj_u)
        width_v = np.max(proj_v) - np.min(proj_v)
        width = min(width_u, width_v)  # Chamfer-Breite ist die kleinere Dimension

        # Schätze Chamfer-Winkel (typisch 45°)
        chamfer_angle = 45.0

        return ChamferRegion(
            face_ids=face_ids,
            normal=normal,
            plane_point=centroid,
            width=width,
            chamfer_angle=chamfer_angle,
            fit_error=plane_fit['error']
        )

    def _create_fillet_region(
        self,
        mesh: pv.PolyData,
        face_ids: Set[int],
        cyl_fit: dict,
        sharp_edges: Set[Tuple[int, int]]
    ) -> Optional[FilletRegion]:
        """Erstellt eine FilletRegion wenn die Region ein Fillet ist."""

        arc_angle = cyl_fit['arc_angle']

        # Fillets haben typischerweise 45-135° Bogenwinkel
        if arc_angle < np.radians(20) or arc_angle > np.radians(180):
            return None

        # Konfidenz basierend auf Fit-Error und Bogenwinkel
        error_factor = max(0, 1 - cyl_fit['error'] / self.cyl_tol)
        arc_factor = 1.0 if np.radians(60) < arc_angle < np.radians(120) else 0.7
        confidence = error_factor * arc_factor

        return FilletRegion(
            face_ids=face_ids,
            axis=cyl_fit['axis'],
            axis_point=cyl_fit['centroid'],
            radius=cyl_fit['radius'],
            arc_angle=arc_angle,
            fit_error=cyl_fit['error'],
            confidence=confidence
        )


def test_detector(stl_path: str, expected_fillets: int, expected_chamfers: int):
    """Testet den Detector auf einer STL-Datei."""

    print("=" * 60)
    print(f"TEST: {Path(stl_path).name}")
    print(f"Erwartet: {expected_fillets} Fillets, {expected_chamfers} Chamfers")
    print("=" * 60)

    if not Path(stl_path).exists():
        print(f"  FEHLER: Datei nicht gefunden!")
        return False

    mesh = pv.read(stl_path)
    print(f"Mesh: {mesh.n_cells} Faces, {mesh.n_points} Vertices")

    detector = FilletChamferDetector(
        sharp_edge_threshold=40.0,  # Etwas niedriger für bessere Segmentierung
        min_region_faces=3,
        plane_tolerance=0.3,
        cylinder_tolerance=1.5
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
                  f"Error={f.fit_error:.3f}mm, "
                  f"Conf={f.confidence:.2f}")

    if chamfers:
        print("\nChamfer-Details:")
        for i, c in enumerate(chamfers):
            print(f"  [{i+1}] Width={c.width:.2f}mm, "
                  f"Angle={c.chamfer_angle:.1f}°, "
                  f"Faces={len(c.face_ids)}, "
                  f"Error={c.fit_error:.3f}mm")

    # Bewertung
    fillet_ok = len(fillets) == expected_fillets
    chamfer_ok = len(chamfers) == expected_chamfers

    print(f"\n{'✓' if fillet_ok else '✗'} Fillets: {len(fillets)}/{expected_fillets}")
    print(f"{'✓' if chamfer_ok else '✗'} Chamfers: {len(chamfers)}/{expected_chamfers}")

    return fillet_ok and chamfer_ok


if __name__ == "__main__":
    print("=" * 60)
    print("Fillet & Chamfer Detector V2")
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
