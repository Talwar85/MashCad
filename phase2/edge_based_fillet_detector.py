"""
Edge-Based Fillet & Chamfer Detector V1
========================================

Erkennt Fillets und Chamfers als KANTEN-Features statt Regionen.

Philosophie:
- Fillets sind zylindrische Streifen ENTLANG von Kanten
- Chamfers sind planare Streifen ENTLANG von Kanten
- Die Kanten-Richtung definiert die Zylinder-Achse

Algorithmus:
1. Finde "Feature-Kanten" (wo sich Flächennormalen stark ändern)
2. Für jede Feature-Kante: Analysiere angrenzende Dreiecke
3. Wenn Dreiecke einen zylindrischen Streifen bilden → Fillet
4. Wenn Dreiecke einen planaren Streifen bilden → Chamfer
5. Extrahiere Geometrie-Parameter (Achse, Radius, Bounds)
6. Erstelle analytische Surfaces
"""

import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict

# OCP Imports
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS, TopoDS_Face
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakePolygon
)
from OCP.Geom import Geom_CylindricalSurface
from OCP.gp import gp_Pnt, gp_Ax3, gp_Dir
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.Interface import Interface_Static
from OCP.ShapeFix import ShapeFix_Shape

import pyvista as pv
from scipy.sparse import lil_matrix
from scipy.sparse.csgraph import connected_components


@dataclass
class FeatureEdge:
    """Eine Feature-Kante (scharfe Kante zwischen zwei Regionen)."""
    edge_id: int
    vertex_ids: Tuple[int, int]      # Die zwei Vertices der Kante
    start_point: np.ndarray          # 3D Position Start
    end_point: np.ndarray            # 3D Position Ende
    direction: np.ndarray            # Normalisierte Richtung
    length: float
    dihedral_angle: float            # Winkel zwischen angrenzenden Faces
    adjacent_face_ids: List[int]     # Angrenzende Mesh-Faces


@dataclass
class FilletStrip:
    """Ein erkannter Fillet-Streifen entlang einer Kante."""
    edge: FeatureEdge
    face_ids: Set[int]               # Mesh-Faces die zum Fillet gehören
    axis: np.ndarray                 # Zylinder-Achse (≈ Kanten-Richtung)
    axis_point: np.ndarray           # Punkt auf der Achse
    radius: float                    # Fillet-Radius
    arc_angle: float                 # Bogenwinkel (typisch ~90°)
    fit_error: float                 # Mittlerer Fit-Fehler
    # UV-Bounds für CYLINDRICAL_SURFACE
    u_min: float
    u_max: float
    v_min: float
    v_max: float


@dataclass
class ChamferStrip:
    """Ein erkannter Chamfer-Streifen entlang einer Kante."""
    edge: FeatureEdge
    face_ids: Set[int]
    normal: np.ndarray               # Normale der Chamfer-Ebene
    plane_point: np.ndarray          # Punkt auf der Ebene
    width: float                     # Chamfer-Breite
    fit_error: float


class EdgeBasedFeatureDetector:
    """
    Erkennt Fillets und Chamfers basierend auf Kanten-Analyse.
    """

    def __init__(
        self,
        min_dihedral_angle: float = 20.0,   # Grad - Minimum für Feature-Kante
        max_dihedral_angle: float = 160.0,  # Grad - Maximum (>160° = fast flach)
        fillet_angle_tolerance: float = 10.0,  # Grad - Toleranz für Fillet-Erkennung
        min_strip_faces: int = 4,           # Minimum Faces pro Strip
        cylinder_fit_tolerance: float = 0.5  # mm - Toleranz für Zylinder-Fit
    ):
        self.min_dihedral = np.radians(min_dihedral_angle)
        self.max_dihedral = np.radians(max_dihedral_angle)
        self.fillet_tol = np.radians(fillet_angle_tolerance)
        self.min_strip_faces = min_strip_faces
        self.cyl_tolerance = cylinder_fit_tolerance

    def detect(self, mesh: pv.PolyData) -> Tuple[List[FilletStrip], List[ChamferStrip]]:
        """
        Erkennt Fillets und Chamfers im Mesh.

        Returns:
            (Liste von FilletStrips, Liste von ChamferStrips)
        """
        print("    [1/4] Berechne Mesh-Strukturen...")

        # Normalen berechnen
        if 'Normals' not in mesh.cell_data:
            mesh = mesh.compute_normals(cell_normals=True, point_normals=False)

        cell_normals = mesh.cell_data['Normals']

        # Baue Edge-zu-Face Mapping
        edge_to_faces = self._build_edge_face_map(mesh)

        # Finde Feature-Kanten
        print("    [2/4] Finde Feature-Kanten...")
        feature_edges = self._find_feature_edges(mesh, edge_to_faces, cell_normals)
        print(f"          → {len(feature_edges)} Feature-Kanten gefunden")

        # Gruppiere Feature-Kanten zu Streifen
        print("    [3/4] Analysiere Fillet-Streifen...")
        fillets = []
        chamfers = []

        # Für jede Feature-Kante: Suche den Fillet/Chamfer-Streifen
        processed_edges = set()

        for edge in feature_edges:
            if edge.edge_id in processed_edges:
                continue

            # Finde zusammenhängende Streifen entlang dieser Kante
            strip_result = self._analyze_edge_strip(mesh, edge, feature_edges,
                                                     edge_to_faces, cell_normals)

            if strip_result is not None:
                if isinstance(strip_result, FilletStrip):
                    fillets.append(strip_result)
                    print(f"          Fillet: r={strip_result.radius:.2f}mm, "
                          f"{len(strip_result.face_ids)} faces, error={strip_result.fit_error:.3f}")
                elif isinstance(strip_result, ChamferStrip):
                    chamfers.append(strip_result)
                    print(f"          Chamfer: w={strip_result.width:.2f}mm, "
                          f"{len(strip_result.face_ids)} faces")

                # Markiere verarbeitete Kanten
                processed_edges.add(edge.edge_id)

        print(f"    [4/4] Ergebnis: {len(fillets)} Fillets, {len(chamfers)} Chamfers")

        return fillets, chamfers

    def _build_edge_face_map(self, mesh: pv.PolyData) -> Dict[Tuple[int, int], List[int]]:
        """Baut Mapping von Kanten zu angrenzenden Faces."""
        edge_to_faces = defaultdict(list)

        for face_id in range(mesh.n_cells):
            cell = mesh.get_cell(face_id)
            pts = cell.point_ids

            for i in range(len(pts)):
                # Kante als sortiertes Tupel (damit (a,b) == (b,a))
                edge = tuple(sorted([pts[i], pts[(i + 1) % len(pts)]]))
                edge_to_faces[edge].append(face_id)

        return edge_to_faces

    def _find_feature_edges(
        self,
        mesh: pv.PolyData,
        edge_to_faces: Dict[Tuple[int, int], List[int]],
        cell_normals: np.ndarray
    ) -> List[FeatureEdge]:
        """Findet alle Feature-Kanten (scharfe Kanten zwischen Flächen)."""

        feature_edges = []
        edge_id = 0

        for edge, face_ids in edge_to_faces.items():
            # Nur Kanten mit genau 2 angrenzenden Faces
            if len(face_ids) != 2:
                continue

            f1, f2 = face_ids
            n1, n2 = cell_normals[f1], cell_normals[f2]

            # Berechne Diederwinkel
            dot = np.clip(np.dot(n1, n2), -1, 1)
            dihedral_angle = np.arccos(dot)

            # Ist es eine Feature-Kante?
            if self.min_dihedral <= dihedral_angle <= self.max_dihedral:
                v1, v2 = edge
                p1 = mesh.points[v1]
                p2 = mesh.points[v2]

                direction = p2 - p1
                length = np.linalg.norm(direction)
                if length > 1e-6:
                    direction = direction / length

                feature_edges.append(FeatureEdge(
                    edge_id=edge_id,
                    vertex_ids=edge,
                    start_point=p1,
                    end_point=p2,
                    direction=direction,
                    length=length,
                    dihedral_angle=dihedral_angle,
                    adjacent_face_ids=face_ids
                ))
                edge_id += 1

        return feature_edges

    def _analyze_edge_strip(
        self,
        mesh: pv.PolyData,
        start_edge: FeatureEdge,
        all_feature_edges: List[FeatureEdge],
        edge_to_faces: Dict[Tuple[int, int], List[int]],
        cell_normals: np.ndarray
    ) -> Optional[FilletStrip | ChamferStrip]:
        """
        Analysiert den Streifen entlang einer Feature-Kante.

        Sucht nach zusammenhängenden Faces die einen Fillet oder Chamfer bilden.
        """

        # Sammle alle Faces die zu diesem Feature-Streifen gehören
        strip_faces = set(start_edge.adjacent_face_ids)

        # Erweitere den Streifen durch Nachbar-Faces mit ähnlicher Geometrie
        strip_faces = self._expand_strip(mesh, strip_faces, edge_to_faces,
                                         cell_normals, start_edge.direction)

        if len(strip_faces) < self.min_strip_faces:
            return None

        # Sammle alle Punkte des Streifens
        strip_points = []
        for face_id in strip_faces:
            cell = mesh.get_cell(face_id)
            strip_points.extend(cell.points)

        strip_points = np.array(strip_points)

        # Versuche Zylinder-Fit (für Fillet)
        fillet = self._try_cylinder_fit(strip_points, start_edge, strip_faces)

        if fillet is not None and fillet.fit_error < self.cyl_tolerance:
            return fillet

        # Versuche Plane-Fit (für Chamfer)
        chamfer = self._try_plane_fit(strip_points, start_edge, strip_faces)

        if chamfer is not None:
            return chamfer

        return None

    def _expand_strip(
        self,
        mesh: pv.PolyData,
        initial_faces: Set[int],
        edge_to_faces: Dict[Tuple[int, int], List[int]],
        cell_normals: np.ndarray,
        strip_direction: np.ndarray
    ) -> Set[int]:
        """
        Erweitert den Streifen durch benachbarte Faces.

        Fügt Faces hinzu, die:
        1. Benachbart sind (teilen eine Kante)
        2. Ähnliche Krümmungscharakteristik haben
        3. "Quer" zur Strip-Richtung liegen
        """

        strip_faces = set(initial_faces)
        faces_to_check = list(initial_faces)

        while faces_to_check:
            current_face = faces_to_check.pop()
            cell = mesh.get_cell(current_face)
            pts = cell.point_ids

            # Prüfe alle Nachbarn
            for i in range(len(pts)):
                edge = tuple(sorted([pts[i], pts[(i + 1) % len(pts)]]))
                neighbors = edge_to_faces.get(edge, [])

                for neighbor_id in neighbors:
                    if neighbor_id in strip_faces:
                        continue

                    # Prüfe ob Nachbar zum Strip gehört
                    if self._should_include_in_strip(
                        mesh, current_face, neighbor_id,
                        cell_normals, strip_direction
                    ):
                        strip_faces.add(neighbor_id)
                        faces_to_check.append(neighbor_id)

        return strip_faces

    def _should_include_in_strip(
        self,
        mesh: pv.PolyData,
        current_face: int,
        neighbor_face: int,
        cell_normals: np.ndarray,
        strip_direction: np.ndarray
    ) -> bool:
        """Prüft ob ein Nachbar-Face zum Fillet-Strip gehört."""

        n1 = cell_normals[current_face]
        n2 = cell_normals[neighbor_face]

        # Normalen-Änderung sollte moderat sein (nicht zu scharf, nicht zu flach)
        dot = np.clip(np.dot(n1, n2), -1, 1)
        angle = np.arccos(dot)

        # Für Fillets: Normalen ändern sich gleichmäßig
        if angle < np.radians(5):   # Zu flach - planare Region
            return False
        if angle > np.radians(45):  # Zu scharf - andere Feature-Kante
            return False

        return True

    def _try_cylinder_fit(
        self,
        points: np.ndarray,
        edge: FeatureEdge,
        face_ids: Set[int]
    ) -> Optional[FilletStrip]:
        """
        Versucht einen Zylinder auf die Strip-Punkte zu fitten.

        Die Zylinder-Achse sollte parallel zur Kanten-Richtung sein.
        """

        if len(points) < 10:
            return None

        try:
            # Entferne Duplikate
            unique_points = np.unique(points, axis=0)

            if len(unique_points) < 10:
                return None

            # Die Achse ist die Kanten-Richtung
            axis = edge.direction

            # Zentriere Punkte
            centroid = np.mean(unique_points, axis=0)

            # Projiziere Punkte auf Ebene senkrecht zur Achse
            # und berechne Abstände zur Achse
            centered = unique_points - centroid
            proj_along_axis = np.dot(centered, axis)[:, np.newaxis] * axis
            perpendicular = centered - proj_along_axis
            distances = np.linalg.norm(perpendicular, axis=1)

            # Radius = Median der Abstände
            radius = np.median(distances)

            if radius < 0.1 or radius > 100:  # Unplausibel
                return None

            # Fehler berechnen
            errors = np.abs(distances - radius)
            fit_error = np.mean(errors)

            # Berechne UV-Bounds
            # U = Winkel um die Achse
            # V = Position entlang der Achse

            # Lokales Koordinatensystem
            if abs(axis[2]) < 0.9:
                x_local = np.cross(axis, [0, 0, 1])
            else:
                x_local = np.cross(axis, [1, 0, 0])
            x_local = x_local / np.linalg.norm(x_local)
            y_local = np.cross(axis, x_local)

            angles = []
            heights = []
            for p in unique_points:
                rel = p - centroid
                h = np.dot(rel, axis)
                heights.append(h)

                perp = rel - h * axis
                if np.linalg.norm(perp) > 1e-6:
                    perp_norm = perp / np.linalg.norm(perp)
                    angle = np.arctan2(np.dot(perp_norm, y_local),
                                      np.dot(perp_norm, x_local))
                    angles.append(angle)

            if not angles:
                return None

            angles = np.array(angles)
            heights = np.array(heights)

            # Handle angle wrap-around for partial cylinders
            angles_sorted = np.sort(angles)
            gaps = np.diff(angles_sorted)
            max_gap_idx = np.argmax(gaps)

            if gaps[max_gap_idx] > np.pi:
                # Es gibt eine große Lücke - partial cylinder
                u_min = angles_sorted[max_gap_idx + 1]
                u_max = angles_sorted[max_gap_idx] + 2 * np.pi
            else:
                u_min = np.min(angles)
                u_max = np.max(angles)

            arc_angle = u_max - u_min

            # Fillet-typische arc_angle ist ~90° (π/2)
            if arc_angle < np.radians(30) or arc_angle > np.radians(180):
                return None

            return FilletStrip(
                edge=edge,
                face_ids=face_ids,
                axis=axis,
                axis_point=centroid,
                radius=radius,
                arc_angle=arc_angle,
                fit_error=fit_error,
                u_min=u_min,
                u_max=u_max,
                v_min=np.min(heights),
                v_max=np.max(heights)
            )

        except Exception as e:
            return None

    def _try_plane_fit(
        self,
        points: np.ndarray,
        edge: FeatureEdge,
        face_ids: Set[int]
    ) -> Optional[ChamferStrip]:
        """Versucht eine Ebene auf die Strip-Punkte zu fitten (für Chamfers)."""

        if len(points) < 6:
            return None

        try:
            unique_points = np.unique(points, axis=0)

            # SVD für Plane-Fit
            centroid = np.mean(unique_points, axis=0)
            centered = unique_points - centroid

            U, S, Vt = np.linalg.svd(centered, full_matrices=False)
            normal = Vt[-1]  # Normale ist kleinste Singulärwert-Richtung

            # Fehler berechnen
            distances = np.abs(np.dot(centered, normal))
            fit_error = np.mean(distances)

            if fit_error > 0.5:  # Zu schlecht für Chamfer
                return None

            # Breite berechnen (senkrecht zur Kanten-Richtung)
            perp_to_edge = np.cross(edge.direction, normal)
            if np.linalg.norm(perp_to_edge) > 1e-6:
                perp_to_edge = perp_to_edge / np.linalg.norm(perp_to_edge)
                widths = np.dot(centered, perp_to_edge)
                width = np.max(widths) - np.min(widths)
            else:
                width = 0

            return ChamferStrip(
                edge=edge,
                face_ids=face_ids,
                normal=normal,
                plane_point=centroid,
                width=width,
                fit_error=fit_error
            )

        except Exception:
            return None


def create_fillet_face(fillet: FilletStrip) -> Optional[TopoDS_Face]:
    """Erstellt ein BREP Face mit CYLINDRICAL_SURFACE für einen Fillet."""

    try:
        origin = gp_Pnt(float(fillet.axis_point[0]),
                       float(fillet.axis_point[1]),
                       float(fillet.axis_point[2]))

        direction = gp_Dir(float(fillet.axis[0]),
                          float(fillet.axis[1]),
                          float(fillet.axis[2]))

        ax3 = gp_Ax3(origin, direction)

        cyl_surface = Geom_CylindricalSurface(ax3, fillet.radius)

        face_builder = BRepBuilderAPI_MakeFace(
            cyl_surface,
            float(fillet.u_min),
            float(fillet.u_max),
            float(fillet.v_min),
            float(fillet.v_max),
            1e-6
        )

        if face_builder.IsDone():
            return face_builder.Face()

        return None

    except Exception as e:
        print(f"      Fillet-Face Fehler: {e}")
        return None


def convert_with_edge_detection(stl_path: str, output_path: str) -> bool:
    """
    Konvertiert STL zu STEP mit kanten-basierter Fillet-Erkennung.
    """
    print(f"\n{'='*60}")
    print(f"Edge-Based Fillet Detector: {stl_path}")
    print(f"{'='*60}")

    if not Path(stl_path).exists():
        print(f"  Datei nicht gefunden!")
        return False

    mesh = pv.read(stl_path)
    print(f"  Original Mesh: {mesh.n_cells} Faces")

    # Feature-Detection
    print("\n  [1/5] Erkenne Fillets und Chamfers...")
    detector = EdgeBasedFeatureDetector(
        min_dihedral_angle=25.0,
        max_dihedral_angle=155.0,
        min_strip_faces=6,
        cylinder_fit_tolerance=0.8
    )

    fillets, chamfers = detector.detect(mesh)
    print(f"        → {len(fillets)} Fillets, {len(chamfers)} Chamfers erkannt")

    # Erstelle Fillet-Faces
    print("\n  [2/5] Erstelle Zylinder-Faces für Fillets...")
    fillet_faces = []
    replaced_face_ids = set()

    for i, fillet in enumerate(fillets):
        face = create_fillet_face(fillet)
        if face is not None:
            fillet_faces.append(face)
            replaced_face_ids.update(fillet.face_ids)
            print(f"        Fillet {i}: r={fillet.radius:.2f}mm → CYLINDRICAL_SURFACE")
        else:
            print(f"        Fillet {i}: Face-Erstellung fehlgeschlagen")

    print(f"        → {len(fillet_faces)} Zylinder-Faces erstellt")

    # Konvertiere verbleibende Faces
    print("\n  [3/5] Konvertiere verbleibende Faces...")
    remaining_ids = [i for i in range(mesh.n_cells) if i not in replaced_face_ids]
    print(f"        → {len(remaining_ids)} Faces")

    # Sewing
    print("\n  [4/5] Nähe und unifiziere...")
    sewer = BRepBuilderAPI_Sewing(0.01)

    for face in fillet_faces:
        sewer.Add(face)

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

    # Reparieren und unifizieren
    fixer = ShapeFix_Shape(sewn_shape)
    fixer.Perform()
    fixed_shape = fixer.Shape()

    try:
        unifier = ShapeUpgrade_UnifySameDomain(fixed_shape, True, True, False)
        unifier.SetLinearTolerance(0.1)
        unifier.SetAngularTolerance(np.radians(1.0))
        unifier.Build()
        final_shape = unifier.Shape()
    except Exception as e:
        print(f"        → Unification Fehler: {e}")
        final_shape = fixed_shape

    # Zähle Faces und Surface-Typen
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

    print(f"        → {final_face_count} Faces ({cyl_count} CYLINDRICAL)")

    # STEP Export
    print(f"\n  [5/5] Exportiere STEP...")
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
    print("Edge-Based Fillet & Chamfer Detector V1")
    print("=" * 60)

    Path('step').mkdir(exist_ok=True)

    test_files = [
        ('stl/V1.stl', 'step/V1_edge_fillet.step'),
        ('stl/V2.stl', 'step/V2_edge_fillet.step'),
        ('stl/MGN12H_X_Carriage_Lite (1).stl', 'step/MGN12H_edge_fillet.step'),
    ]

    results = []
    for stl_file, step_file in test_files:
        if Path(stl_file).exists():
            success = convert_with_edge_detection(stl_file, step_file)
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
