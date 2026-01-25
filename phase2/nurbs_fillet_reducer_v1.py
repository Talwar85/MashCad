"""
NURBS Fillet Reducer V1
========================

Reduziert Mesh-Faces durch NURBS-Fitting auf Fillet/Chamfer-Regionen.

Algorithmus:
1. Berechne diskrete Krümmung für jedes Mesh-Face
2. Finde zusammenhängende Regionen hoher Krümmung (Connected Components)
3. Fitte B-Spline Surface auf jede Region
4. Ersetze viele Dreieck-Faces mit einer NURBS-Surface

Erwartetes Ergebnis:
- Verrundungen: 50-100 Triangles → 1 NURBS Surface
- Fasen: 10-30 Triangles → 1 Planar Surface
"""

import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from collections import defaultdict

# OCP Imports
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
from OCP.TopoDS import TopoDS, TopoDS_Shape, TopoDS_Face, TopoDS_Compound
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeFace
from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
from OCP.TColgp import TColgp_Array2OfPnt
from OCP.gp import gp_Pnt
from OCP.GeomAbs import GeomAbs_C2

import pyvista as pv
from scipy.sparse import lil_matrix
from scipy.sparse.csgraph import connected_components


@dataclass
class FilletRegion:
    """Eine zusammenhängende Fillet/Chamfer-Region."""
    region_id: int
    face_ids: np.ndarray        # Indices im Original-Mesh
    points: np.ndarray          # Alle Punkte der Region
    centroid: np.ndarray        # Schwerpunkt
    mean_curvature: float       # Mittlere Krümmung
    max_curvature: float        # Maximale Krümmung
    is_fillet: bool             # True = Rundung, False = Fase


class MeshFilletDetector:
    """
    Erkennt Fillet/Chamfer-Regionen in einem Mesh.

    Nutzt Krümmungsanalyse und Connected-Component-Clustering.
    """

    def __init__(
        self,
        curvature_threshold: float = 0.5,     # ~29° zwischen Nachbar-Normalen
        min_region_faces: int = 5,             # Minimum Faces pro Region
        neighbor_angle_tolerance: float = 0.3  # Für Nachbar-Klassifikation
    ):
        self.curvature_threshold = curvature_threshold
        self.min_region_faces = min_region_faces
        self.neighbor_tolerance = neighbor_angle_tolerance

    def detect(self, mesh: pv.PolyData) -> Tuple[List[FilletRegion], np.ndarray]:
        """
        Erkennt Fillet-Regionen im Mesh.

        Returns:
            (Liste von FilletRegion, Krümmungs-Array)
        """
        print(f"    Analysiere {mesh.n_cells} Faces...")

        # 1. Berechne Krümmung pro Face
        curvatures = self._compute_face_curvatures(mesh)

        # 2. Finde Nachbarschafts-Graph
        adjacency = self._build_adjacency(mesh)

        # 3. Finde Connected Components unter hoher Krümmung
        high_curv_mask = curvatures > self.curvature_threshold
        regions = self._find_connected_regions(mesh, adjacency, curvatures, high_curv_mask)

        # 4. Filter kleine Regionen
        regions = [r for r in regions if len(r.face_ids) >= self.min_region_faces]

        return regions, curvatures

    def _compute_face_curvatures(self, mesh: pv.PolyData) -> np.ndarray:
        """Berechnet diskrete Krümmung für jedes Face."""

        # Normalen berechnen
        if 'Normals' not in mesh.cell_data:
            mesh = mesh.compute_normals(cell_normals=True, point_normals=False)

        cell_normals = mesh.cell_data['Normals']
        n_cells = mesh.n_cells

        # Baue Nachbarschafts-Lookup
        edge_to_faces = defaultdict(list)

        for i in range(n_cells):
            cell = mesh.get_cell(i)
            pts = cell.point_ids

            # Alle Kanten des Faces
            for j in range(len(pts)):
                edge = tuple(sorted([pts[j], pts[(j+1) % len(pts)]]))
                edge_to_faces[edge].append(i)

        # Berechne Krümmung als max Winkel zu Nachbarn
        curvatures = np.zeros(n_cells)

        for i in range(n_cells):
            cell = mesh.get_cell(i)
            pts = cell.point_ids

            neighbor_ids = set()
            for j in range(len(pts)):
                edge = tuple(sorted([pts[j], pts[(j+1) % len(pts)]]))
                for face_id in edge_to_faces[edge]:
                    if face_id != i:
                        neighbor_ids.add(face_id)

            if neighbor_ids:
                my_normal = cell_normals[i]
                max_angle = 0.0

                for neighbor_id in neighbor_ids:
                    neighbor_normal = cell_normals[neighbor_id]
                    dot = np.clip(np.dot(my_normal, neighbor_normal), -1, 1)
                    angle = np.arccos(dot)
                    max_angle = max(max_angle, angle)

                curvatures[i] = max_angle

        return curvatures

    def _build_adjacency(self, mesh: pv.PolyData) -> Dict[int, Set[int]]:
        """Baut Nachbarschafts-Graph (Face-zu-Face über Edges)."""

        edge_to_faces = defaultdict(list)
        n_cells = mesh.n_cells

        for i in range(n_cells):
            cell = mesh.get_cell(i)
            pts = cell.point_ids

            for j in range(len(pts)):
                edge = tuple(sorted([pts[j], pts[(j+1) % len(pts)]]))
                edge_to_faces[edge].append(i)

        adjacency = defaultdict(set)

        for edge, faces in edge_to_faces.items():
            if len(faces) == 2:
                adjacency[faces[0]].add(faces[1])
                adjacency[faces[1]].add(faces[0])

        return adjacency

    def _find_connected_regions(
        self,
        mesh: pv.PolyData,
        adjacency: Dict[int, Set[int]],
        curvatures: np.ndarray,
        high_curv_mask: np.ndarray
    ) -> List[FilletRegion]:
        """Findet zusammenhängende Regionen hoher Krümmung."""

        high_curv_ids = np.where(high_curv_mask)[0]

        if len(high_curv_ids) == 0:
            return []

        # Baue Sparse-Adjazenz-Matrix nur für High-Curvature-Faces
        id_to_idx = {face_id: idx for idx, face_id in enumerate(high_curv_ids)}
        n = len(high_curv_ids)

        adj_matrix = lil_matrix((n, n), dtype=np.int8)

        for face_id in high_curv_ids:
            idx = id_to_idx[face_id]
            for neighbor_id in adjacency[face_id]:
                if neighbor_id in id_to_idx:
                    neighbor_idx = id_to_idx[neighbor_id]
                    adj_matrix[idx, neighbor_idx] = 1
                    adj_matrix[neighbor_idx, idx] = 1

        # Connected Components
        n_components, labels = connected_components(adj_matrix.tocsr(), directed=False)

        # Erstelle Regionen
        regions = []
        cell_normals = mesh.cell_data.get('Normals')

        for comp_id in range(n_components):
            comp_mask = labels == comp_id
            comp_indices = np.where(comp_mask)[0]
            face_ids = high_curv_ids[comp_indices]

            if len(face_ids) < self.min_region_faces:
                continue

            # Sammle Punkte
            all_points = []
            for fid in face_ids:
                cell = mesh.get_cell(fid)
                all_points.extend(cell.points)

            points = np.array(all_points)
            centroid = np.mean(points, axis=0)

            region_curvatures = curvatures[face_ids]

            regions.append(FilletRegion(
                region_id=len(regions),
                face_ids=face_ids,
                points=points,
                centroid=centroid,
                mean_curvature=np.mean(region_curvatures),
                max_curvature=np.max(region_curvatures),
                is_fillet=np.mean(region_curvatures) > 0.8  # ~46°
            ))

        return regions


class NURBSRegionFitter:
    """Fittet NURBS-Surfaces auf Fillet-Regionen."""

    def __init__(
        self,
        max_grid_size: int = 20,
        tolerance: float = 0.3,
        min_points: int = 16
    ):
        self.max_grid_size = max_grid_size
        self.tolerance = tolerance
        self.min_points = min_points

    def fit_region(self, region: FilletRegion) -> Optional[TopoDS_Face]:
        """
        Fittet B-Spline Surface auf Region.

        Returns:
            TopoDS_Face mit B-Spline oder None
        """
        points = region.points

        if len(points) < self.min_points:
            return None

        # Entferne Duplikate
        unique_points = np.unique(points, axis=0)

        if len(unique_points) < self.min_points:
            return None

        try:
            # Projiziere auf Grid
            grid_points = self._project_to_grid(unique_points)

            if grid_points is None:
                return None

            # Erstelle OCP Array
            n_u, n_v = grid_points.shape[:2]
            pnt_array = TColgp_Array2OfPnt(1, n_u, 1, n_v)

            for i in range(n_u):
                for j in range(n_v):
                    pt = grid_points[i, j]
                    pnt_array.SetValue(
                        i + 1, j + 1,
                        gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2]))
                    )

            # Fitte B-Spline
            fitter = GeomAPI_PointsToBSplineSurface(
                pnt_array,
                3,           # DegMin
                8,           # DegMax
                GeomAbs_C2,  # Continuity
                self.tolerance
            )

            if fitter.IsDone():
                surface = fitter.Surface()
                face_builder = BRepBuilderAPI_MakeFace(surface, self.tolerance)

                if face_builder.IsDone():
                    return face_builder.Face()

            return None

        except Exception as e:
            print(f"      NURBS-Fitting Fehler: {e}")
            return None

    def _project_to_grid(self, points: np.ndarray) -> Optional[np.ndarray]:
        """Projiziert Punkte auf reguläres UV-Grid."""

        if len(points) < 9:
            return None

        # PCA für lokales Koordinatensystem
        centroid = np.mean(points, axis=0)
        centered = points - centroid

        U, S, Vt = np.linalg.svd(centered, full_matrices=False)

        u_dir = Vt[0]
        v_dir = Vt[1]

        # UV-Koordinaten
        uv = np.column_stack([
            np.dot(centered, u_dir),
            np.dot(centered, v_dir)
        ])

        # Grid-Größe
        grid_size = min(self.max_grid_size, max(4, int(np.sqrt(len(points) / 2))))

        u_min, u_max = uv[:, 0].min(), uv[:, 0].max()
        v_min, v_max = uv[:, 1].min(), uv[:, 1].max()

        if (u_max - u_min) < 1e-6 or (v_max - v_min) < 1e-6:
            return None

        grid = np.zeros((grid_size, grid_size, 3))

        for i in range(grid_size):
            for j in range(grid_size):
                u = u_min + (u_max - u_min) * i / (grid_size - 1)
                v = v_min + (v_max - v_min) * j / (grid_size - 1)

                # Gewichteter Nächste-Nachbarn-Lookup
                distances = np.sqrt((uv[:, 0] - u)**2 + (uv[:, 1] - v)**2)

                # K-nächste Nachbarn für Interpolation
                k = min(4, len(points))
                nearest_indices = np.argpartition(distances, k)[:k]
                nearest_distances = distances[nearest_indices]
                nearest_points = points[nearest_indices]

                # Inverse Distance Weighting
                weights = 1.0 / (nearest_distances + 1e-10)
                weights /= weights.sum()

                grid[i, j] = np.sum(nearest_points * weights[:, np.newaxis], axis=0)

        return grid


def analyze_and_reduce(stl_path: str, output_prefix: str = None):
    """
    Analysiert STL und zeigt potentielle NURBS-Reduktion.

    Args:
        stl_path: Pfad zur STL-Datei
        output_prefix: Prefix für Output-Dateien (optional)
    """
    print(f"\n=== Analysiere {stl_path} ===")

    if not Path(stl_path).exists():
        print(f"  Datei nicht gefunden!")
        return

    # Mesh laden
    mesh = pv.read(stl_path)
    print(f"  Original: {mesh.n_cells} Faces")

    # Fillet-Detection
    detector = MeshFilletDetector(
        curvature_threshold=0.5,   # ~29° zwischen Normalen
        min_region_faces=10         # Mindestens 10 Faces pro Region
    )

    regions, curvatures = detector.detect(mesh)

    print(f"\n  Erkannte Regionen: {len(regions)}")

    # NURBS-Fitting
    fitter = NURBSRegionFitter(max_grid_size=15, tolerance=0.3)

    nurbs_faces = []
    total_replaced_faces = 0

    for region in regions:
        region_type = "FILLET" if region.is_fillet else "CHAMFER"
        print(f"\n    Region {region.region_id} ({region_type}):")
        print(f"      Faces: {len(region.face_ids)}")
        print(f"      Krümmung: mean={region.mean_curvature:.2f}, max={region.max_curvature:.2f}")
        print(f"      Punkte: {len(region.points)}")

        # NURBS-Fitting versuchen
        nurbs_face = fitter.fit_region(region)

        if nurbs_face is not None:
            nurbs_faces.append(nurbs_face)
            total_replaced_faces += len(region.face_ids)
            print(f"      → NURBS-Fit erfolgreich! ({len(region.face_ids)} Faces → 1 NURBS)")
        else:
            print(f"      → NURBS-Fit fehlgeschlagen")

    # Statistik
    low_curv_faces = np.sum(curvatures <= 0.5)

    print(f"\n  === Zusammenfassung ===")
    print(f"  Original Faces:       {mesh.n_cells}")
    print(f"  Niedrige Krümmung:    {low_curv_faces} (bleiben als Dreiecke)")
    print(f"  Fillet-Regionen:      {len(regions)}")
    print(f"  Durch NURBS ersetzt:  {total_replaced_faces} → {len(nurbs_faces)}")
    print(f"  Potentielle Faces:    {low_curv_faces + len(nurbs_faces)}")
    print(f"  Reduktion:            {100 * (1 - (low_curv_faces + len(nurbs_faces)) / mesh.n_cells):.1f}%")

    return regions, nurbs_faces, curvatures


def convert_to_step(stl_path: str, output_path: str):
    """
    Konvertiert STL zu STEP mit NURBS für Fillet-Regionen.

    Pipeline:
    1. Lade Mesh
    2. Erkenne Fillet-Regionen
    3. Fitte NURBS auf Fillet-Regionen
    4. Konvertiere Rest als planare Faces
    5. Nähe alles zusammen
    6. Exportiere als STEP
    """
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeSolid
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCP.Interface import Interface_Static
    from OCP.ShapeFix import ShapeFix_Shape

    print(f"\n{'='*60}")
    print(f"Konvertiere {stl_path} → {output_path}")
    print(f"{'='*60}")

    if not Path(stl_path).exists():
        print(f"  Datei nicht gefunden!")
        return False

    # Mesh laden
    mesh = pv.read(stl_path)
    print(f"  Original Mesh: {mesh.n_cells} Faces")

    # Fillet-Detection
    print("\n  [1/5] Erkenne Fillet-Regionen...")
    detector = MeshFilletDetector(
        curvature_threshold=0.5,
        min_region_faces=10
    )
    regions, curvatures = detector.detect(mesh)
    print(f"        → {len(regions)} Regionen erkannt")

    # NURBS-Fitting
    print("\n  [2/5] Fitte NURBS auf Fillet-Regionen...")
    fitter = NURBSRegionFitter(max_grid_size=15, tolerance=0.3)

    nurbs_faces = []
    replaced_face_ids = set()

    for region in regions:
        nurbs_face = fitter.fit_region(region)
        if nurbs_face is not None:
            nurbs_faces.append(nurbs_face)
            replaced_face_ids.update(region.face_ids)
            print(f"        Region {region.region_id}: {len(region.face_ids)} → 1 NURBS")

    print(f"        → {len(nurbs_faces)} NURBS-Faces erstellt")

    # Konvertiere verbleibende Mesh-Faces
    print("\n  [3/5] Konvertiere verbleibende Faces...")

    remaining_ids = [i for i in range(mesh.n_cells) if i not in replaced_face_ids]
    print(f"        → {len(remaining_ids)} Faces zu konvertieren")

    # Sewing für alle Faces
    print("\n  [4/5] Nähe Faces zusammen...")
    sewer = BRepBuilderAPI_Sewing(0.01)  # 10µm Toleranz

    # Füge NURBS-Faces hinzu
    for face in nurbs_faces:
        sewer.Add(face)

    # Füge verbleibende Mesh-Faces als Dreiecke hinzu
    for face_id in remaining_ids:
        cell = mesh.get_cell(face_id)
        pts = cell.points

        if len(pts) >= 3:
            try:
                polygon = BRepBuilderAPI_MakePolygon()
                for pt in pts:
                    polygon.Add(gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2])))
                polygon.Close()

                if polygon.IsDone():
                    face_builder = BRepBuilderAPI_MakeFace(polygon.Wire())
                    if face_builder.IsDone():
                        sewer.Add(face_builder.Face())
            except:
                pass

    sewer.Perform()
    sewn_shape = sewer.SewedShape()

    if sewn_shape.IsNull():
        print("        → Sewing fehlgeschlagen!")
        return False

    # Shape reparieren
    fixer = ShapeFix_Shape(sewn_shape)
    fixer.Perform()
    fixed_shape = fixer.Shape()

    # UnifySameDomain für zusätzliche Reduktion
    print("\n  [4.5/5] Unifiziere planare Faces...")
    try:
        unifier = ShapeUpgrade_UnifySameDomain(fixed_shape, True, True, False)
        unifier.SetLinearTolerance(0.1)
        unifier.SetAngularTolerance(np.radians(1.0))
        unifier.Build()
        final_shape = unifier.Shape()
    except Exception as e:
        print(f"        → Unification fehlgeschlagen: {e}")
        final_shape = fixed_shape

    # Zähle finale Faces
    final_face_count = 0
    explorer = TopExp_Explorer(final_shape, TopAbs_FACE)
    while explorer.More():
        final_face_count += 1
        explorer.Next()

    print(f"        → Finale Shape: {final_face_count} Faces")

    # STEP Export
    print(f"\n  [5/5] Exportiere STEP...")
    writer = STEPControl_Writer()

    # STEP Parameter
    Interface_Static.SetCVal_s("write.step.schema", "AP214")
    Interface_Static.SetCVal_s("write.step.product.name", Path(stl_path).stem)

    writer.Transfer(final_shape, STEPControl_AsIs)

    status = writer.Write(output_path)

    if status == 1:  # IFSelect_RetDone
        print(f"        → STEP erfolgreich exportiert: {output_path}")
        print(f"\n  === Ergebnis ===")
        print(f"  Original:  {mesh.n_cells} Faces")
        print(f"  Final:     {final_face_count} Faces")
        print(f"  Reduktion: {100 * (1 - final_face_count / mesh.n_cells):.1f}%")
        return True
    else:
        print(f"        → STEP Export fehlgeschlagen (Status: {status})")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("NURBS Fillet Reducer V1 - STEP Export Test")
    print("=" * 60)

    # Test mit allen verfügbaren Dateien
    test_files = [
        ('stl/V1.stl', 'step/V1_nurbs.step'),
        ('stl/V2.stl', 'step/V2_nurbs.step'),
        ('stl/MGN12H.stl', 'step/MGN12H_nurbs.step'),
    ]

    # Stelle sicher dass step-Ordner existiert
    Path('step').mkdir(exist_ok=True)

    results = []
    for stl_file, step_file in test_files:
        if Path(stl_file).exists():
            success = convert_to_step(stl_file, step_file)
            results.append((stl_file, step_file, success))
        else:
            print(f"\n{stl_file} nicht gefunden")
            results.append((stl_file, step_file, False))

    print("\n" + "=" * 60)
    print("ZUSAMMENFASSUNG")
    print("=" * 60)
    for stl, step, success in results:
        status = "✓" if success else "✗"
        print(f"  {status} {stl} → {step}")
