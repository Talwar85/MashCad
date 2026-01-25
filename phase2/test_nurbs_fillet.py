"""
NURBS-basierter Ansatz für Fillet/Chamfer-Erkennung und Reduktion.

Strategie:
1. Erkenne Regionen mit hoher Krümmung (Filets/Chamfers im Mesh)
2. Fitte B-Spline Surface auf diese Regionen
3. Ersetze viele kleine Dreieck-Faces mit einer NURBS-Surface
"""

import numpy as np
from pathlib import Path
import sys
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

# OCP Imports
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
from OCP.TopoDS import TopoDS, TopoDS_Shape, TopoDS_Face
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRep import BRep_Tool
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeFace
from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
from OCP.TColgp import TColgp_Array2OfPnt
from OCP.gp import gp_Pnt
from OCP.GeomAbs import GeomAbs_C2

import pyvista as pv


@dataclass
class CurvatureRegion:
    """Region mit einheitlicher Krümmung im Mesh."""
    face_ids: np.ndarray       # Indices der zugehörigen Mesh-Faces
    points: np.ndarray         # 3D Punkte
    normals: np.ndarray        # Normalen
    mean_curvature: float      # Mittlere Krümmung
    is_fillet: bool            # Hohe Krümmung = Fillet/Chamfer


class MeshCurvatureAnalyzer:
    """Analysiert Mesh-Krümmung zur Fillet/Chamfer-Erkennung."""

    def __init__(self, curvature_threshold: float = 0.1):
        """
        Args:
            curvature_threshold: Krümmungs-Schwelle für Fillet-Erkennung
        """
        self.threshold = curvature_threshold

    def analyze(self, mesh: pv.PolyData) -> List[CurvatureRegion]:
        """
        Analysiert Mesh und findet Regionen mit hoher Krümmung.

        Returns:
            Liste von CurvatureRegion-Objekten
        """
        # Berechne Krümmung pro Face
        mesh_with_curvature = self._compute_face_curvature(mesh)

        # Clustere Faces nach Krümmung
        regions = self._cluster_by_curvature(mesh_with_curvature)

        return regions

    def _compute_face_curvature(self, mesh: pv.PolyData) -> pv.PolyData:
        """Berechnet diskrete Krümmung für jedes Face."""

        # Normalen berechnen
        mesh = mesh.compute_normals(cell_normals=True, point_normals=True)

        # Krümmung = Änderung der Normalen zwischen benachbarten Faces
        n_cells = mesh.n_cells
        curvatures = np.zeros(n_cells)

        # Finde Nachbarn via Edge-Sharing
        # Vereinfachte Version: Nutze Normalenvariation in lokaler Nachbarschaft
        cell_normals = mesh.cell_data['Normals']

        for i in range(n_cells):
            cell = mesh.get_cell(i)
            point_ids = cell.point_ids

            # Finde benachbarte Faces (teilen mindestens 2 Punkte)
            neighbor_normals = []
            for j in range(n_cells):
                if i == j:
                    continue
                other_cell = mesh.get_cell(j)
                shared = len(set(point_ids) & set(other_cell.point_ids))
                if shared >= 2:  # Shared edge
                    neighbor_normals.append(cell_normals[j])

            if neighbor_normals:
                # Krümmung = maximaler Winkel zu Nachbarn
                my_normal = cell_normals[i]
                angles = []
                for n_normal in neighbor_normals:
                    dot = np.clip(np.dot(my_normal, n_normal), -1, 1)
                    angle = np.arccos(dot)
                    angles.append(angle)
                curvatures[i] = np.max(angles)

        mesh.cell_data['curvature'] = curvatures
        return mesh

    def _cluster_by_curvature(self, mesh: pv.PolyData) -> List[CurvatureRegion]:
        """Clustert Faces nach Krümmung."""

        curvatures = mesh.cell_data['curvature']
        normals = mesh.cell_data['Normals']

        # Finde hohe und niedrige Krümmungs-Regionen
        high_curvature_mask = curvatures > self.threshold

        # Für diesen Test: Einfache Gruppierung
        high_ids = np.where(high_curvature_mask)[0]
        low_ids = np.where(~high_curvature_mask)[0]

        regions = []

        # Hohe Krümmung = Filet-Kandidaten
        if len(high_ids) > 0:
            points = np.array([mesh.get_cell(i).center for i in high_ids])
            region_normals = normals[high_ids]
            regions.append(CurvatureRegion(
                face_ids=high_ids,
                points=points,
                normals=region_normals,
                mean_curvature=np.mean(curvatures[high_ids]),
                is_fillet=True
            ))

        # Niedrige Krümmung = Planare Regionen
        if len(low_ids) > 0:
            points = np.array([mesh.get_cell(i).center for i in low_ids])
            region_normals = normals[low_ids]
            regions.append(CurvatureRegion(
                face_ids=low_ids,
                points=points,
                normals=region_normals,
                mean_curvature=np.mean(curvatures[low_ids]),
                is_fillet=False
            ))

        return regions


class NURBSFitter:
    """Fittet B-Spline Surfaces auf Punktwolken."""

    def __init__(self, grid_size: int = 20, tolerance: float = 0.1):
        self.grid_size = grid_size
        self.tolerance = tolerance

    def fit_bspline_to_points(self, points: np.ndarray) -> Optional[TopoDS_Face]:
        """
        Fittet B-Spline Surface auf Punktwolke.

        Args:
            points: Nx3 Array von 3D Punkten

        Returns:
            TopoDS_Face mit B-Spline Surface oder None
        """
        if len(points) < 9:  # Minimum für 3x3 Grid
            return None

        try:
            # Projiziere Punkte auf reguläres Grid
            grid_points = self._project_to_grid(points)

            if grid_points is None:
                return None

            # Erstelle TColgp_Array2OfPnt
            n_u, n_v = grid_points.shape[:2]
            pnt_array = TColgp_Array2OfPnt(1, n_u, 1, n_v)

            for i in range(n_u):
                for j in range(n_v):
                    pt = grid_points[i, j]
                    pnt_array.SetValue(i + 1, j + 1, gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2])))

            # Fitte B-Spline
            # DegMin=3, DegMax=8, Continuity=GeomAbs_C2, Tolerance
            fitter = GeomAPI_PointsToBSplineSurface(
                pnt_array,
                3,  # DegMin
                8,  # DegMax
                GeomAbs_C2,  # Continuity
                self.tolerance
            )

            if fitter.IsDone():
                surface = fitter.Surface()

                # Erstelle Face
                face_builder = BRepBuilderAPI_MakeFace(surface, self.tolerance)
                if face_builder.IsDone():
                    return face_builder.Face()

            return None

        except Exception as e:
            print(f"  NURBS-Fitting fehlgeschlagen: {e}")
            return None

    def _project_to_grid(self, points: np.ndarray) -> Optional[np.ndarray]:
        """Projiziert unstrukturierte Punkte auf reguläres Grid."""

        if len(points) < 9:
            return None

        # PCA für lokales Koordinatensystem
        centroid = np.mean(points, axis=0)
        centered = points - centroid

        # SVD für Hauptachsen
        U, S, Vt = np.linalg.svd(centered)

        # Projektion auf UV-Ebene (erste zwei Hauptachsen)
        u_dir = Vt[0]
        v_dir = Vt[1]

        uv = np.column_stack([
            np.dot(centered, u_dir),
            np.dot(centered, v_dir)
        ])

        # Grid-Größe basierend auf Punktanzahl
        grid_size = min(self.grid_size, int(np.sqrt(len(points))))
        if grid_size < 3:
            grid_size = 3

        # Grid erstellen
        u_min, u_max = uv[:, 0].min(), uv[:, 0].max()
        v_min, v_max = uv[:, 1].min(), uv[:, 1].max()

        # Füge kleine Marge hinzu
        u_margin = (u_max - u_min) * 0.01
        v_margin = (v_max - v_min) * 0.01

        grid = np.zeros((grid_size, grid_size, 3))

        for i in range(grid_size):
            for j in range(grid_size):
                u = u_min + (u_max - u_min) * i / (grid_size - 1)
                v = v_min + (v_max - v_min) * j / (grid_size - 1)

                # Finde nächsten Punkt
                distances = np.sqrt((uv[:, 0] - u)**2 + (uv[:, 1] - v)**2)
                nearest_idx = np.argmin(distances)
                grid[i, j] = points[nearest_idx]

        return grid


def test_curvature_analysis():
    """Testet Krümmungsanalyse und NURBS-Fitting."""

    print("=== NURBS-basierter Fillet/Chamfer Ansatz ===")
    print()

    # Test-Dateien
    test_files = ['stl/V1.stl', 'stl/V2.stl']

    for stl_file in test_files:
        if not Path(stl_file).exists():
            print(f"  {stl_file} nicht gefunden")
            continue

        print(f"Analysiere {stl_file}...")
        mesh = pv.read(stl_file)
        print(f"  Mesh: {mesh.n_cells} Faces")

        # Krümmungsanalyse
        print("  Berechne Krümmung...")
        analyzer = MeshCurvatureAnalyzer(curvature_threshold=0.3)  # ~17°
        regions = analyzer.analyze(mesh)

        for r in regions:
            region_type = "FILLET" if r.is_fillet else "PLANAR"
            print(f"    {region_type}: {len(r.face_ids)} Faces, Krümmung={r.mean_curvature:.3f}")

        # NURBS-Fitting für Fillet-Regionen
        fillet_regions = [r for r in regions if r.is_fillet]

        if fillet_regions:
            print("  Versuche NURBS-Fitting für Fillet-Regionen...")
            fitter = NURBSFitter(grid_size=10, tolerance=0.5)

            for i, region in enumerate(fillet_regions):
                if len(region.points) >= 9:
                    face = fitter.fit_bspline_to_points(region.points)
                    if face is not None:
                        print(f"    Region {i}: NURBS-Face erfolgreich erstellt!")
                    else:
                        print(f"    Region {i}: NURBS-Fitting fehlgeschlagen")
                else:
                    print(f"    Region {i}: Zu wenige Punkte ({len(region.points)})")

        print()


if __name__ == "__main__":
    test_curvature_analysis()
