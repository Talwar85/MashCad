"""
Fillet Cylinder Detector V1
============================

Erkennt Fillet-Regionen als Teil-Zylinder und erstellt CYLINDRICAL_SURFACE.

Philosophie:
- Fillets an Kanten sind Teil-Zylinder mit konstantem Radius
- Erkenne Achse und Radius aus der Punktwolke
- Erstelle echte CYLINDRICAL_SURFACE statt generischer NURBS

Krümmungs-Klassifizierung:
- K ≈ 0, H ≈ 0  → Ebene
- K ≈ 0, H ≠ 0  → Zylinder (Fillet!)
- K > 0, H > 0  → Sphäre (Eck-Fillet)
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
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeWire
)
from OCP.Geom import Geom_CylindricalSurface, Geom_SphericalSurface
from OCP.gp import gp_Pnt, gp_Ax3, gp_Dir, gp_Pln, gp_Circ, gp_Ax2
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.Interface import Interface_Static
from OCP.ShapeFix import ShapeFix_Shape

import pyvista as pv
from scipy.sparse import lil_matrix
from scipy.sparse.csgraph import connected_components


@dataclass
class CylinderFit:
    """Ergebnis eines Zylinder-Fits."""
    center: np.ndarray      # Punkt auf der Achse
    axis: np.ndarray        # Achsenrichtung (normalisiert)
    radius: float           # Radius
    height: float           # Höhe entlang der Achse
    error: float            # Mittlerer Abstand zur Zylinderfläche
    inlier_ratio: float     # Anteil der Punkte innerhalb Toleranz
    u_min: float            # Winkel-Start (0..2π)
    u_max: float            # Winkel-Ende
    v_min: float            # Höhe-Start
    v_max: float            # Höhe-Ende


@dataclass
class SphereFit:
    """Ergebnis eines Sphären-Fits."""
    center: np.ndarray
    radius: float
    error: float
    inlier_ratio: float


class FilletPrimitiveFitter:
    """
    Fittet geometrische Primitive (Zylinder, Sphäre) auf Fillet-Regionen.

    Methoden:
    - Zylinder: PCA für Achse + Median für Radius
    - Sphäre: Algebraischer Fit (Vandermonde)
    """

    def __init__(self, tolerance: float = 0.5):
        self.tolerance = tolerance

    def fit_cylinder(self, points: np.ndarray, normals: np.ndarray = None) -> Optional[CylinderFit]:
        """
        Fittet Zylinder auf Punktwolke.

        Methode:
        1. PCA auf Punkte → Achse ist Richtung mit größter Varianz
        2. Projiziere Punkte senkrecht zur Achse
        3. Radius = Median der Abstände
        4. Berechne U/V Bounds für partial cylinder
        """
        if len(points) < 10:
            return None

        try:
            # 1. PCA für Achsenrichtung
            centroid = np.mean(points, axis=0)
            centered = points - centroid

            # SVD für Hauptachsen
            U, S, Vt = np.linalg.svd(centered, full_matrices=False)

            # Die Achse ist die Richtung mit GRÖSSTER Varianz (erste Komponente)
            # Für Zylinder-Punkte: Entlang der Achse größte Streuung
            axis = Vt[0]
            axis = axis / np.linalg.norm(axis)

            # Aber: Wenn es ein Fillet ist, haben wir einen TEIL-Zylinder
            # Die Punkte streuen mehr QUER zur Achse als entlang
            # Daher: Achse ist die Richtung mit KLEINSTER Varianz
            axis = Vt[-1]  # Letzte Komponente = kleinste Varianz
            axis = axis / np.linalg.norm(axis)

            # 2. Projiziere Punkte auf Ebene senkrecht zur Achse
            # und berechne Abstände zur Achse
            proj_along_axis = np.dot(centered, axis)[:, np.newaxis] * axis
            perpendicular = centered - proj_along_axis
            distances = np.linalg.norm(perpendicular, axis=1)

            # 3. Radius = Median der Abstände
            radius = np.median(distances)

            if radius < 0.1:  # Zu klein
                return None

            # 4. Fehler berechnen
            errors = np.abs(distances - radius)
            error = np.mean(errors)
            inlier_ratio = np.mean(errors < self.tolerance)

            if inlier_ratio < 0.7:  # Weniger als 70% Inlier
                return None

            # 5. U/V Bounds für partial cylinder
            # U = Winkel um die Achse (0..2π)
            # V = Position entlang der Achse

            # Baue lokales Koordinatensystem
            # x_local ist senkrecht zur Achse
            if abs(axis[2]) < 0.9:
                x_local = np.cross(axis, [0, 0, 1])
            else:
                x_local = np.cross(axis, [1, 0, 0])
            x_local = x_local / np.linalg.norm(x_local)
            y_local = np.cross(axis, x_local)

            # Berechne Winkel für jeden Punkt
            angles = []
            heights = []
            for p in points:
                rel = p - centroid
                # Projektion auf Achse
                h = np.dot(rel, axis)
                heights.append(h)
                # Projektion senkrecht zur Achse
                perp = rel - h * axis
                if np.linalg.norm(perp) > 1e-6:
                    perp_norm = perp / np.linalg.norm(perp)
                    angle = np.arctan2(np.dot(perp_norm, y_local), np.dot(perp_norm, x_local))
                    angles.append(angle)

            angles = np.array(angles)
            heights = np.array(heights)

            # Handle angle wrap-around
            u_min = np.min(angles)
            u_max = np.max(angles)
            v_min = np.min(heights)
            v_max = np.max(heights)

            # Prüfe ob es ein voller Zylinder ist oder nur ein Teil
            angle_range = u_max - u_min

            return CylinderFit(
                center=centroid,
                axis=axis,
                radius=radius,
                height=v_max - v_min,
                error=error,
                inlier_ratio=inlier_ratio,
                u_min=u_min,
                u_max=u_max,
                v_min=v_min,
                v_max=v_max
            )

        except Exception as e:
            print(f"      Zylinder-Fit Fehler: {e}")
            return None

    def fit_sphere(self, points: np.ndarray) -> Optional[SphereFit]:
        """
        Fittet Kugel auf Punktwolke (algebraischer Fit).

        Gleichung: (x-cx)² + (y-cy)² + (z-cz)² = r²
        """
        if len(points) < 10:
            return None

        try:
            # Algebraischer Fit via Least Squares
            A = np.column_stack([
                2 * points,
                np.ones(len(points))
            ])
            b = np.sum(points**2, axis=1)

            result, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
            cx, cy, cz, d = result
            center = np.array([cx, cy, cz])
            radius = np.sqrt(d + cx**2 + cy**2 + cz**2)

            if radius < 0.1 or radius > 1000:  # Unplausibel
                return None

            # Fehler berechnen
            distances = np.linalg.norm(points - center, axis=1)
            errors = np.abs(distances - radius)
            error = np.mean(errors)
            inlier_ratio = np.mean(errors < self.tolerance)

            if inlier_ratio < 0.7:
                return None

            return SphereFit(
                center=center,
                radius=radius,
                error=error,
                inlier_ratio=inlier_ratio
            )

        except Exception as e:
            return None


class FilletRegionDetector:
    """Erkennt Fillet-Regionen via Krümmungsanalyse."""

    def __init__(
        self,
        curvature_threshold: float = 0.3,  # ~17° zwischen Normalen
        min_region_faces: int = 6
    ):
        self.curvature_threshold = curvature_threshold
        self.min_region_faces = min_region_faces

    def detect(self, mesh: pv.PolyData) -> Tuple[List[dict], np.ndarray]:
        """
        Erkennt Fillet-Regionen und klassifiziert sie.

        Returns:
            (Liste von Regionen, Krümmungs-Array)
        """
        # Normalen berechnen
        if 'Normals' not in mesh.cell_data:
            mesh = mesh.compute_normals(cell_normals=True, point_normals=False)

        # Krümmung berechnen
        curvatures = self._compute_curvatures(mesh)

        # Nachbarschafts-Graph
        adjacency = self._build_adjacency(mesh)

        # Finde zusammenhängende High-Curvature-Regionen
        high_curv_mask = curvatures > self.curvature_threshold
        regions = self._find_connected_regions(mesh, adjacency, curvatures, high_curv_mask)

        return regions, curvatures

    def _compute_curvatures(self, mesh: pv.PolyData) -> np.ndarray:
        """Berechnet diskrete Krümmung (max Winkel zu Nachbarn)."""
        cell_normals = mesh.cell_data['Normals']
        n_cells = mesh.n_cells

        # Edge-zu-Face Mapping
        edge_to_faces = defaultdict(list)
        for i in range(n_cells):
            cell = mesh.get_cell(i)
            pts = cell.point_ids
            for j in range(len(pts)):
                edge = tuple(sorted([pts[j], pts[(j+1) % len(pts)]]))
                edge_to_faces[edge].append(i)

        # Krümmung pro Face
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
                    dot = np.clip(np.dot(my_normal, cell_normals[neighbor_id]), -1, 1)
                    angle = np.arccos(dot)
                    max_angle = max(max_angle, angle)
                curvatures[i] = max_angle

        return curvatures

    def _build_adjacency(self, mesh: pv.PolyData) -> Dict[int, Set[int]]:
        """Baut Nachbarschafts-Graph."""
        edge_to_faces = defaultdict(list)
        for i in range(mesh.n_cells):
            cell = mesh.get_cell(i)
            pts = cell.point_ids
            for j in range(len(pts)):
                edge = tuple(sorted([pts[j], pts[(j+1) % len(pts)]]))
                edge_to_faces[edge].append(i)

        adjacency = defaultdict(set)
        for faces in edge_to_faces.values():
            if len(faces) == 2:
                adjacency[faces[0]].add(faces[1])
                adjacency[faces[1]].add(faces[0])

        return adjacency

    def _find_connected_regions(
        self,
        mesh: pv.PolyData,
        adjacency: Dict[int, Set[int]],
        curvatures: np.ndarray,
        mask: np.ndarray
    ) -> List[dict]:
        """Findet zusammenhängende Regionen."""

        high_ids = np.where(mask)[0]
        if len(high_ids) == 0:
            return []

        # Sparse-Matrix für Connected Components
        id_to_idx = {fid: idx for idx, fid in enumerate(high_ids)}
        n = len(high_ids)
        adj_matrix = lil_matrix((n, n), dtype=np.int8)

        for fid in high_ids:
            idx = id_to_idx[fid]
            for neighbor in adjacency[fid]:
                if neighbor in id_to_idx:
                    adj_matrix[idx, id_to_idx[neighbor]] = 1

        n_components, labels = connected_components(adj_matrix.tocsr(), directed=False)

        # Erstelle Regionen
        regions = []
        for comp_id in range(n_components):
            comp_mask = labels == comp_id
            face_ids = high_ids[comp_mask]

            if len(face_ids) < self.min_region_faces:
                continue

            # Sammle Punkte und Normalen
            all_points = []
            all_normals = []
            for fid in face_ids:
                cell = mesh.get_cell(fid)
                all_points.extend(cell.points)
                all_normals.append(mesh.cell_data['Normals'][fid])

            regions.append({
                'id': len(regions),
                'face_ids': face_ids,
                'points': np.array(all_points),
                'normals': np.array(all_normals),
                'mean_curvature': np.mean(curvatures[face_ids])
            })

        return regions


def create_cylindrical_face(cyl_fit: CylinderFit) -> Optional[TopoDS_Face]:
    """
    Erstellt BREP Face mit CYLINDRICAL_SURFACE.

    Args:
        cyl_fit: Zylinder-Fit Ergebnis

    Returns:
        TopoDS_Face oder None
    """
    try:
        # Koordinatensystem für Zylinder
        origin = gp_Pnt(float(cyl_fit.center[0]),
                       float(cyl_fit.center[1]),
                       float(cyl_fit.center[2]))

        direction = gp_Dir(float(cyl_fit.axis[0]),
                          float(cyl_fit.axis[1]),
                          float(cyl_fit.axis[2]))

        ax3 = gp_Ax3(origin, direction)

        # Zylindrische Surface
        cyl_surface = Geom_CylindricalSurface(ax3, cyl_fit.radius)

        # Bounded Face mit U/V Parametern
        # U = Winkel (0..2π), V = Höhe
        face_builder = BRepBuilderAPI_MakeFace(
            cyl_surface,
            float(cyl_fit.u_min),
            float(cyl_fit.u_max),
            float(cyl_fit.v_min),
            float(cyl_fit.v_max),
            1e-6
        )

        if face_builder.IsDone():
            return face_builder.Face()

        return None

    except Exception as e:
        print(f"      Zylinder-Face Fehler: {e}")
        return None


def convert_with_fillet_detection(stl_path: str, output_path: str) -> bool:
    """
    Konvertiert STL zu STEP mit Fillet-Erkennung als Zylinder.

    Pipeline:
    1. Lade Mesh
    2. Erkenne Fillet-Regionen (hohe Krümmung)
    3. Fitte Zylinder auf Fillet-Regionen
    4. Erstelle CYLINDRICAL_SURFACE für gute Fits
    5. Konvertiere Rest als Dreiecke
    6. Unifiziere planare Faces
    7. Exportiere STEP
    """
    print(f"\n{'='*60}")
    print(f"Fillet-Zylinder-Detektor: {stl_path}")
    print(f"{'='*60}")

    if not Path(stl_path).exists():
        print(f"  Datei nicht gefunden!")
        return False

    # Mesh laden
    mesh = pv.read(stl_path)
    print(f"  Original Mesh: {mesh.n_cells} Faces")

    # Fillet-Detection
    print("\n  [1/6] Erkenne Fillet-Regionen...")
    detector = FilletRegionDetector(curvature_threshold=0.4, min_region_faces=8)
    regions, curvatures = detector.detect(mesh)
    print(f"        → {len(regions)} Regionen erkannt")

    # Primitive Fitting
    print("\n  [2/6] Fitte Zylinder auf Fillet-Regionen...")
    fitter = FilletPrimitiveFitter(tolerance=0.5)

    cylinder_faces = []
    replaced_face_ids = set()

    for region in regions:
        points = region['points']
        normals = region['normals']

        # Versuche Zylinder-Fit
        cyl_fit = fitter.fit_cylinder(points, normals)

        if cyl_fit and cyl_fit.inlier_ratio > 0.75:
            print(f"        Region {region['id']}: Zylinder r={cyl_fit.radius:.2f}mm, "
                  f"error={cyl_fit.error:.3f}, inliers={cyl_fit.inlier_ratio:.1%}")

            # Erstelle CYLINDRICAL_SURFACE
            cyl_face = create_cylindrical_face(cyl_fit)

            if cyl_face is not None:
                cylinder_faces.append(cyl_face)
                replaced_face_ids.update(region['face_ids'])
                print(f"              → CYLINDRICAL_SURFACE erstellt!")
            else:
                print(f"              → Face-Erstellung fehlgeschlagen")
        else:
            if cyl_fit:
                print(f"        Region {region['id']}: Kein guter Fit "
                      f"(inliers={cyl_fit.inlier_ratio:.1%})")
            else:
                print(f"        Region {region['id']}: Fit fehlgeschlagen")

    print(f"        → {len(cylinder_faces)} Zylinder-Faces erstellt")

    # Konvertiere verbleibende Faces
    print("\n  [3/6] Konvertiere verbleibende Faces...")
    remaining_ids = [i for i in range(mesh.n_cells) if i not in replaced_face_ids]
    print(f"        → {len(remaining_ids)} Faces")

    # Sewing
    print("\n  [4/6] Nähe Faces zusammen...")
    sewer = BRepBuilderAPI_Sewing(0.01)

    # Füge Zylinder-Faces hinzu
    for face in cylinder_faces:
        sewer.Add(face)

    # Füge verbleibende Mesh-Faces hinzu
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

    # Unifiziere planare Faces
    print("\n  [5/6] Unifiziere planare Faces...")
    try:
        unifier = ShapeUpgrade_UnifySameDomain(fixed_shape, True, True, False)
        unifier.SetLinearTolerance(0.1)
        unifier.SetAngularTolerance(np.radians(1.0))
        unifier.Build()
        final_shape = unifier.Shape()
    except Exception as e:
        print(f"        → Fehler: {e}")
        final_shape = fixed_shape

    # Zähle finale Faces
    final_face_count = 0
    cyl_count = 0
    explorer = TopExp_Explorer(final_shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        adaptor = BRepAdaptor_Surface(face)
        if adaptor.GetType() == 1:  # GeomAbs_Cylinder
            cyl_count += 1
        final_face_count += 1
        explorer.Next()

    print(f"        → Finale Shape: {final_face_count} Faces ({cyl_count} CYLINDRICAL)")

    # STEP Export
    print(f"\n  [6/6] Exportiere STEP...")
    writer = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214")
    Interface_Static.SetCVal_s("write.step.product.name", Path(stl_path).stem)

    writer.Transfer(final_shape, STEPControl_AsIs)
    status = writer.Write(output_path)

    if status == 1:
        print(f"        → {output_path}")
        print(f"\n  === Ergebnis ===")
        print(f"  Original:     {mesh.n_cells} Faces")
        print(f"  Final:        {final_face_count} Faces")
        print(f"  CYLINDRICAL:  {cyl_count}")
        print(f"  Reduktion:    {100 * (1 - final_face_count / mesh.n_cells):.1f}%")
        return True
    else:
        print(f"        → Export fehlgeschlagen")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Fillet Cylinder Detector V1")
    print("=" * 60)

    Path('step').mkdir(exist_ok=True)

    test_files = [
        ('stl/V1.stl', 'step/V1_fillet_cyl.step'),
        ('stl/V2.stl', 'step/V2_fillet_cyl.step'),
        ('stl/MGN12H_X_Carriage_Lite (1).stl', 'step/MGN12H_fillet_cyl.step'),
    ]

    results = []
    for stl_file, step_file in test_files:
        if Path(stl_file).exists():
            success = convert_with_fillet_detection(stl_file, step_file)
            results.append((Path(stl_file).name, success))
        else:
            print(f"\n{stl_file} nicht gefunden")
            results.append((Path(stl_file).name, False))

    print("\n" + "=" * 60)
    print("ZUSAMMENFASSUNG")
    print("=" * 60)
    for name, success in results:
        status = "✓" if success else "✗"
        print(f"  {status} {name}")
