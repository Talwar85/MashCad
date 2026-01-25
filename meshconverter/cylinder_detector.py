"""
MashCad - Cylinder Detector
===========================

Erkennt zylindrische Flächen in einem Mesh und erstellt echte Zylinder-Surfaces.
"""

import numpy as np
from typing import List, Dict, Set, Tuple, Optional
from loguru import logger
from dataclasses import dataclass

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

try:
    from OCP.gp import gp_Pnt, gp_Dir, gp_Ax3, gp_Circ
    from OCP.Geom import Geom_CylindricalSurface
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeEdge
    from OCP.TopoDS import TopoDS_Face
    HAS_OCP = True
except ImportError:
    HAS_OCP = False


@dataclass
class DetectedCylinder:
    """Ein erkannter Zylinder im Mesh."""
    cell_ids: np.ndarray       # Indices der zugehörigen Mesh-Dreiecke
    center: np.ndarray         # Achsen-Zentrum (3D Punkt auf der Achse)
    axis: np.ndarray           # Achsenrichtung (normalisiert)
    radius: float              # Radius in mm
    height: float              # Höhe in mm (min/max entlang Achse)
    v_min: float               # Minimum V-Parameter
    v_max: float               # Maximum V-Parameter
    fit_error: float           # Durchschnittlicher Fitting-Fehler


class CylinderDetector:
    """
    Erkennt zylindrische Flächen in einem Mesh.

    Strategie:
    1. Mesh-Dreiecke nach Normalen-Divergenz gruppieren
    2. Für jede Gruppe: Prüfe ob Zylinder-Fit möglich
    3. Zylinder mit niedrigem Fehler akzeptieren
    """

    def __init__(
        self,
        max_fit_error: float = 0.5,      # mm - maximaler durchschnittlicher Fehler
        min_cylinder_cells: int = 8,     # Minimum Dreiecke für Zylinder
        min_radius: float = 0.5,         # Minimum Radius in mm
        max_radius: float = 1000.0       # Maximum Radius in mm
    ):
        """
        Args:
            max_fit_error: Maximaler Fitting-Fehler für gültigen Zylinder
            min_cylinder_cells: Minimum Anzahl Dreiecke für Zylinder-Erkennung
            min_radius: Minimum Zylinder-Radius
            max_radius: Maximum Zylinder-Radius
        """
        self.max_fit_error = max_fit_error
        self.min_cells = min_cylinder_cells
        self.min_radius = min_radius
        self.max_radius = max_radius

    def detect_cylinders(self, mesh: 'pv.PolyData') -> List[DetectedCylinder]:
        """
        Erkennt alle zylindrischen Flächen im Mesh.

        Args:
            mesh: PyVista PolyData (trianguliert)

        Returns:
            Liste von DetectedCylinder
        """
        if not HAS_PYVISTA:
            return []

        logger.debug("Starte Zylinder-Erkennung...")

        # Normalen berechnen falls nicht vorhanden
        if 'Normals' not in mesh.cell_data:
            mesh.compute_normals(cell_normals=True, inplace=True)

        normals = mesh.cell_data['Normals']
        n_cells = mesh.n_cells

        # 1. Finde "nicht-planare" Regionen
        # Zylinder haben benachbarte Dreiecke mit divergierenden Normalen
        cylinder_candidates = self._find_curved_regions(mesh, normals)
        logger.debug(f"  Gefunden: {len(cylinder_candidates)} gekrümmte Regionen")

        # 2. Für jede Kandidaten-Region: Zylinder-Fit versuchen
        cylinders = []
        for region_cells in cylinder_candidates:
            if len(region_cells) < self.min_cells:
                continue

            cylinder = self._fit_cylinder_to_region(mesh, region_cells)
            if cylinder is not None:
                cylinders.append(cylinder)

        logger.debug(f"  Erkannt: {len(cylinders)} Zylinder")
        return cylinders

    def _find_curved_regions(
        self,
        mesh: 'pv.PolyData',
        normals: np.ndarray
    ) -> List[np.ndarray]:
        """
        Findet Regionen mit divergierenden Normalen (potentielle Zylinder).

        Returns:
            Liste von Cell-ID Arrays
        """
        n_cells = mesh.n_cells

        # Baue Adjacency Map
        adjacency = self._build_cell_adjacency(mesh)

        # Finde planare Regionen (Normalen-Unterschied < 5°)
        # Alles was NICHT planar ist, könnte ein Zylinder sein
        planar_threshold = np.cos(np.radians(5.0))

        visited = set()
        curved_regions = []

        for start_cell in range(n_cells):
            if start_cell in visited:
                continue

            # BFS um Region zu finden
            region_cells = []
            queue = [start_cell]
            is_curved_region = False

            while queue:
                cell_id = queue.pop(0)
                if cell_id in visited:
                    continue

                visited.add(cell_id)
                region_cells.append(cell_id)

                # Prüfe Nachbarn
                for neighbor_id in adjacency.get(cell_id, []):
                    if neighbor_id in visited:
                        continue

                    # Normalen-Unterschied
                    n1 = normals[cell_id]
                    n2 = normals[neighbor_id]
                    dot = np.clip(np.dot(n1, n2), -1.0, 1.0)

                    if dot > planar_threshold:
                        # Gleiche planare Region
                        queue.append(neighbor_id)
                    else:
                        # Gekrümmt - markiere Region
                        is_curved_region = True
                        queue.append(neighbor_id)

            if is_curved_region and len(region_cells) >= self.min_cells:
                curved_regions.append(np.array(region_cells))

        return curved_regions

    def _build_cell_adjacency(self, mesh: 'pv.PolyData') -> Dict[int, List[int]]:
        """Baut Cell-Adjacency-Map (welche Zellen teilen eine Kante)."""
        adjacency: Dict[int, List[int]] = {}
        edge_to_cells: Dict[Tuple[int, int], List[int]] = {}

        faces = mesh.faces.reshape(-1, 4)[:, 1:4]

        for cell_id, face in enumerate(faces):
            for i in range(3):
                v1, v2 = int(face[i]), int(face[(i + 1) % 3])
                edge_key = (min(v1, v2), max(v1, v2))

                if edge_key not in edge_to_cells:
                    edge_to_cells[edge_key] = []
                edge_to_cells[edge_key].append(cell_id)

        # Erstelle Adjacency aus shared Edges
        for edge_key, cells in edge_to_cells.items():
            if len(cells) == 2:
                c1, c2 = cells
                if c1 not in adjacency:
                    adjacency[c1] = []
                if c2 not in adjacency:
                    adjacency[c2] = []
                adjacency[c1].append(c2)
                adjacency[c2].append(c1)

        return adjacency

    def _fit_cylinder_to_region(
        self,
        mesh: 'pv.PolyData',
        cell_ids: np.ndarray
    ) -> Optional[DetectedCylinder]:
        """
        Fittet einen Zylinder auf eine Region.

        Methode:
        1. PCA auf Normalen → Achsenrichtung
        2. Projektion auf Achse → Zentrum und Höhe
        3. Senkrechte Distanzen → Radius
        """
        try:
            # Sammle Punkte und Normalen der Region
            faces = mesh.faces.reshape(-1, 4)[:, 1:4]
            points_list = []
            normals_list = []

            normals_data = mesh.cell_data['Normals']

            for cell_id in cell_ids:
                tri = faces[cell_id]
                for v_idx in tri:
                    points_list.append(mesh.points[v_idx])
                normals_list.append(normals_data[cell_id])

            points = np.array(points_list)
            normals = np.array(normals_list)

            if len(points) < 10:
                return None

            # 1. Achsenrichtung via PCA auf Normalen
            # Für einen Zylinder sind alle Normalen senkrecht zur Achse
            # Die Achse ist die Richtung mit maximaler Varianz der Normalen
            from sklearn.decomposition import PCA

            pca = PCA(n_components=3)
            pca.fit(normals)

            # Die Achse ist die Richtung der KLEINSTEN Varianz
            # (Normalen variieren wenig in Achsenrichtung bei perfektem Zylinder)
            axis = pca.components_[-1]  # Letzte Komponente = kleinste Varianz

            # Normalisieren
            axis = axis / (np.linalg.norm(axis) + 1e-10)

            # 2. Projiziere Punkte auf Achse
            centroid = np.mean(points, axis=0)
            proj = np.dot(points - centroid, axis)
            v_min, v_max = proj.min(), proj.max()
            height = v_max - v_min

            # Zentrum = Centroid
            center = centroid

            # 3. Radius = Median der senkrechten Distanzen zur Achse
            # Punkt-zu-Achse Distanz
            perp = points - centroid - np.outer(proj, axis)
            distances = np.linalg.norm(perp, axis=1)

            radius = np.median(distances)

            # Prüfe Radius-Grenzen
            if radius < self.min_radius or radius > self.max_radius:
                return None

            # 4. Fitting-Fehler berechnen
            errors = np.abs(distances - radius)
            mean_error = np.mean(errors)

            if mean_error > self.max_fit_error:
                return None

            logger.debug(f"    Zylinder erkannt: r={radius:.2f}mm, h={height:.2f}mm, error={mean_error:.3f}mm")

            return DetectedCylinder(
                cell_ids=cell_ids,
                center=center,
                axis=axis,
                radius=radius,
                height=height,
                v_min=v_min,
                v_max=v_max,
                fit_error=mean_error
            )

        except Exception as e:
            logger.debug(f"    Zylinder-Fit fehlgeschlagen: {e}")
            return None

    def create_cylinder_face(
        self,
        cylinder: DetectedCylinder
    ) -> Optional['TopoDS_Face']:
        """
        Erstellt eine BREP-Face für einen erkannten Zylinder.

        Args:
            cylinder: DetectedCylinder

        Returns:
            TopoDS_Face oder None
        """
        if not HAS_OCP:
            return None

        try:
            center = cylinder.center
            axis = cylinder.axis
            radius = cylinder.radius

            # gp_Ax3 für Zylinder-Koordinatensystem
            gp_center = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))
            gp_axis = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))

            # X-Richtung (beliebig, senkrecht zu Achse)
            if abs(axis[2]) < 0.9:
                x_dir = np.cross(axis, [0, 0, 1])
            else:
                x_dir = np.cross(axis, [1, 0, 0])
            x_dir = x_dir / (np.linalg.norm(x_dir) + 1e-10)
            gp_x_dir = gp_Dir(float(x_dir[0]), float(x_dir[1]), float(x_dir[2]))

            ax3 = gp_Ax3(gp_center, gp_axis, gp_x_dir)

            # Zylindrische Surface
            cyl_surface = Geom_CylindricalSurface(ax3, radius)

            # Face mit U/V Bounds
            u_min, u_max = 0.0, 2 * np.pi
            v_min, v_max = cylinder.v_min, cylinder.v_max

            face_builder = BRepBuilderAPI_MakeFace(
                cyl_surface,
                u_min, u_max,
                v_min, v_max,
                1e-6
            )

            if face_builder.IsDone():
                return face_builder.Face()
            else:
                logger.debug("  Zylinder-Face Erstellung fehlgeschlagen")
                return None

        except Exception as e:
            logger.debug(f"  Zylinder-Face Fehler: {e}")
            return None
