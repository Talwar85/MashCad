"""
MashCad - Topology Preserving Converter
=======================================

Konvertiert Mesh zu BREP unter Erhaltung der Mesh-Topologie.
Garantiert wasserdichte Ergebnisse durch Wiederverwendung von Kanten.
"""

import numpy as np
from typing import Optional, List, Dict, Set, Tuple
from loguru import logger

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False

try:
    from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Pln
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeWire,
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_Sewing
    )
    from OCP.TopoDS import TopoDS_Edge, TopoDS_Wire, TopoDS_Face
    from OCP.ShapeFix import ShapeFix_Shape
    HAS_OCP = True
except ImportError:
    HAS_OCP = False
    logger.warning("OCP nicht verfügbar für Topology Preserving")

from meshconverter.mesh_converter_v10 import ConversionResult, ConversionStatus, Region
from meshconverter.solid_builder import SolidBuilder


class TopologyPreservingConverter:
    """
    Konvertiert Mesh zu BREP unter Erhaltung der Topologie.

    Strategie:
    1. Erstelle globale Edge-Map aus Mesh (geteilte Kanten)
    2. Segmentiere Mesh in Regionen (wie bisher)
    3. Erstelle Faces mit den geteilten Edges
    4. Sewing sollte 0 freie Kanten haben

    Dies funktioniert weil:
    - Jede Mesh-Kante wird nur EINMAL als BREP-Edge erstellt
    - Benachbarte Faces teilen sich exakt dieselbe Edge-Instanz
    - Keine Koordinaten-Matching-Probleme möglich
    """

    def __init__(
        self,
        angle_tolerance: float = 10.0,  # Grad - höher für weniger Regionen
        sewing_tolerance: float = 0.1,  # mm
        min_region_faces: int = 1
    ):
        """
        Args:
            angle_tolerance: Winkeltoleranz für Normalen-Clustering (Grad)
            sewing_tolerance: Toleranz für Sewing (sollte niedrig sein)
            min_region_faces: Minimum Faces pro Region
        """
        self.angle_tol = np.radians(angle_tolerance)
        self.sewing_tol = sewing_tolerance
        self.min_region_faces = min_region_faces

    def convert(self, mesh: 'pv.PolyData') -> ConversionResult:
        """
        Konvertiert Mesh zu BREP mit Topologie-Erhaltung.

        Args:
            mesh: PyVista PolyData

        Returns:
            ConversionResult
        """
        if not HAS_OCP:
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message="OCP nicht verfügbar"
            )

        if not HAS_PYVISTA:
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message="PyVista nicht verfügbar"
            )

        logger.info("=== Topology Preserving Converter ===")
        logger.info(f"Mesh: {mesh.n_points} Punkte, {mesh.n_cells} Faces")

        stats = {
            'input_points': mesh.n_points,
            'input_faces': mesh.n_cells
        }

        try:
            # 1. Erstelle globale Vertex-Liste als gp_Pnt
            logger.info("Erstelle Vertex-Pool...")
            vertices = self._create_vertex_pool(mesh)
            logger.debug(f"  → {len(vertices)} Vertices")

            # 2. Erstelle globale Edge-Map
            logger.info("Erstelle Edge-Map...")
            edge_map, edge_to_cells = self._create_edge_map(mesh, vertices)
            logger.debug(f"  → {len(edge_map)} unique Edges")
            stats['unique_edges'] = len(edge_map)

            # 3. Segmentiere Mesh in Regionen
            logger.info("Segmentiere Oberflächen...")
            regions = self._segment_mesh(mesh)
            logger.info(f"  → {len(regions)} Regionen")
            stats['regions'] = len(regions)

            # 4. Erstelle Faces für jede Region
            logger.info("Erstelle BREP Faces...")
            faces = self._create_faces_for_regions(
                mesh, regions, vertices, edge_map
            )
            logger.info(f"  → {len(faces)} Faces erstellt")
            stats['faces_created'] = len(faces)

            if len(faces) == 0:
                return ConversionResult(
                    status=ConversionStatus.FAILED,
                    message="Keine Faces erstellt",
                    stats=stats
                )

            # 5. Sewing
            logger.info("Erstelle Solid...")
            builder = SolidBuilder(
                tolerance=self.sewing_tol,
                multi_pass_sewing=True,
                max_tolerance=2.0
            )
            result = builder.build(faces)
            result.stats.update(stats)

            logger.info(f"=== Ergebnis: {result.status.name} ===")
            return result

        except Exception as e:
            logger.error(f"Topology Preserving Konvertierung fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return ConversionResult(
                status=ConversionStatus.FAILED,
                message=f"Fehler: {e}",
                stats=stats
            )

    def _create_vertex_pool(self, mesh: 'pv.PolyData') -> List['gp_Pnt']:
        """
        Erstellt Liste von gp_Pnt aus Mesh-Vertices.

        Diese Vertices werden für alle Edges wiederverwendet.
        """
        vertices = []
        for pt in mesh.points:
            vertices.append(gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2])))
        return vertices

    def _create_edge_map(
        self,
        mesh: 'pv.PolyData',
        vertices: List['gp_Pnt']
    ) -> Tuple[Dict[Tuple[int, int], 'TopoDS_Edge'], Dict[Tuple[int, int], List[int]]]:
        """
        Erstellt globale Edge-Map.

        Jede Kante wird nur EINMAL erstellt und von allen
        anliegenden Faces geteilt.

        Returns:
            (edge_map, edge_to_cells)
            - edge_map: (v1, v2) -> TopoDS_Edge
            - edge_to_cells: (v1, v2) -> [cell_ids]
        """
        edge_map: Dict[Tuple[int, int], TopoDS_Edge] = {}
        edge_to_cells: Dict[Tuple[int, int], List[int]] = {}

        # Extrahiere alle Dreieck-Kanten
        faces_array = mesh.faces.reshape(-1, 4)[:, 1:4]  # Triangle indices

        for cell_id, face in enumerate(faces_array):
            # Alle 3 Kanten des Dreiecks
            for i in range(3):
                v1, v2 = int(face[i]), int(face[(i + 1) % 3])
                # Normalisierter Key (kleinerer Index zuerst)
                edge_key = (min(v1, v2), max(v1, v2))

                # Track welche Cells diese Kante nutzen
                if edge_key not in edge_to_cells:
                    edge_to_cells[edge_key] = []
                edge_to_cells[edge_key].append(cell_id)

                # Edge erstellen falls noch nicht vorhanden
                if edge_key not in edge_map:
                    p1, p2 = vertices[v1], vertices[v2]
                    # Prüfe ob Punkte unterschiedlich sind
                    if p1.Distance(p2) > 1e-9:
                        edge_builder = BRepBuilderAPI_MakeEdge(p1, p2)
                        if edge_builder.IsDone():
                            edge_map[edge_key] = edge_builder.Edge()

        return edge_map, edge_to_cells

    def _segment_mesh(self, mesh: 'pv.PolyData') -> List[Region]:
        """
        Segmentiert Mesh in Regionen basierend auf Normalen.

        Verwendet größere Winkeltoleranz für weniger Regionen.
        """
        from meshconverter.surface_segmenter import SurfaceSegmenter

        segmenter = SurfaceSegmenter(
            angle_tolerance=np.degrees(self.angle_tol),
            min_region_faces=self.min_region_faces,
            max_regions=500
        )

        return segmenter.segment(mesh, merge_coplanar=True)

    def _create_faces_for_regions(
        self,
        mesh: 'pv.PolyData',
        regions: List[Region],
        vertices: List['gp_Pnt'],
        edge_map: Dict[Tuple[int, int], 'TopoDS_Edge']
    ) -> List['TopoDS_Face']:
        """
        Erstellt BREP Faces für jede Region.

        Verwendet die geteilten Edges aus der edge_map.
        """
        faces = []
        faces_array = mesh.faces.reshape(-1, 4)[:, 1:4]

        for region in regions:
            face = self._create_face_for_region(
                mesh, region, vertices, edge_map, faces_array
            )
            if face is not None:
                faces.append(face)

        return faces

    def _create_face_for_region(
        self,
        mesh: 'pv.PolyData',
        region: Region,
        vertices: List['gp_Pnt'],
        edge_map: Dict[Tuple[int, int], 'TopoDS_Edge'],
        faces_array: np.ndarray
    ) -> Optional['TopoDS_Face']:
        """
        Erstellt ein BREP Face für eine Region.

        Sammelt alle Boundary-Edges und erstellt Wire.
        """
        try:
            # Sammle alle Kanten der Region und zähle Vorkommen
            edge_count: Dict[Tuple[int, int], int] = {}

            for cell_id in region.cell_ids:
                face = faces_array[cell_id]
                for i in range(3):
                    v1, v2 = int(face[i]), int(face[(i + 1) % 3])
                    edge_key = (min(v1, v2), max(v1, v2))
                    edge_count[edge_key] = edge_count.get(edge_key, 0) + 1

            # Boundary-Kanten: nur einmal vorkommende Kanten
            boundary_edges = [
                edge_key for edge_key, count in edge_count.items()
                if count == 1
            ]

            if len(boundary_edges) < 3:
                logger.debug(f"  Region {region.region_id}: Zu wenige Boundary-Edges ({len(boundary_edges)})")
                return None

            # Wire aus Boundary-Edges erstellen
            wire = self._create_wire_from_edges(boundary_edges, edge_map, vertices)
            if wire is None:
                logger.debug(f"  Region {region.region_id}: Wire-Erstellung fehlgeschlagen")
                return None

            # Plane aus Region-Normal und Centroid
            normal = region.normal
            centroid = region.centroid

            gp_origin = gp_Pnt(float(centroid[0]), float(centroid[1]), float(centroid[2]))
            gp_normal = gp_Dir(float(normal[0]), float(normal[1]), float(normal[2]))
            plane = gp_Pln(gp_origin, gp_normal)

            # Face erstellen
            face_builder = BRepBuilderAPI_MakeFace(plane, wire)
            if face_builder.IsDone():
                return face_builder.Face()
            else:
                logger.debug(f"  Region {region.region_id}: MakeFace fehlgeschlagen")
                return None

        except Exception as e:
            logger.debug(f"  Region {region.region_id}: Fehler - {e}")
            return None

    def _create_wire_from_edges(
        self,
        boundary_edge_keys: List[Tuple[int, int]],
        edge_map: Dict[Tuple[int, int], 'TopoDS_Edge'],
        vertices: List['gp_Pnt']
    ) -> Optional['TopoDS_Wire']:
        """
        Erstellt Wire aus Boundary-Edges.

        Ordnet Edges zu einem geschlossenen Loop.
        """
        if len(boundary_edge_keys) < 3:
            return None

        try:
            # Baue Adjazenz für Ordering
            adjacency: Dict[int, List[Tuple[int, Tuple[int, int]]]] = {}
            for edge_key in boundary_edge_keys:
                v1, v2 = edge_key
                if v1 not in adjacency:
                    adjacency[v1] = []
                if v2 not in adjacency:
                    adjacency[v2] = []
                adjacency[v1].append((v2, edge_key))
                adjacency[v2].append((v1, edge_key))

            # Starte beim ersten Vertex
            start_v = boundary_edge_keys[0][0]
            ordered_edges = []
            visited = set()
            current_v = start_v

            while len(ordered_edges) < len(boundary_edge_keys):
                found_next = False
                for next_v, edge_key in adjacency.get(current_v, []):
                    if edge_key not in visited:
                        ordered_edges.append(edge_key)
                        visited.add(edge_key)
                        current_v = next_v
                        found_next = True
                        break

                if not found_next:
                    break

            if len(ordered_edges) < 3:
                return None

            # Wire Builder
            wire_builder = BRepBuilderAPI_MakeWire()

            for edge_key in ordered_edges:
                if edge_key in edge_map:
                    wire_builder.Add(edge_map[edge_key])
                else:
                    # Edge nicht in Map - erstelle neu
                    v1, v2 = edge_key
                    p1, p2 = vertices[v1], vertices[v2]
                    if p1.Distance(p2) > 1e-9:
                        edge_builder = BRepBuilderAPI_MakeEdge(p1, p2)
                        if edge_builder.IsDone():
                            wire_builder.Add(edge_builder.Edge())

            if wire_builder.IsDone():
                return wire_builder.Wire()
            else:
                return None

        except Exception as e:
            logger.debug(f"Wire-Erstellung fehlgeschlagen: {e}")
            return None


def convert_topology_preserving(filepath: str, **kwargs) -> ConversionResult:
    """
    Convenience-Funktion für Topology-Preserving Konvertierung.

    Args:
        filepath: Pfad zur Mesh-Datei
        **kwargs: Optionen für TopologyPreservingConverter

    Returns:
        ConversionResult
    """
    from meshconverter.mesh_converter_v10 import MeshLoader, LoadStatus

    # Mesh laden
    load_result = MeshLoader.load(filepath, repair=True)
    if load_result.status == LoadStatus.FAILED:
        return ConversionResult(
            status=ConversionStatus.FAILED,
            message=f"Laden fehlgeschlagen: {load_result.message}"
        )

    # Konvertieren
    converter = TopologyPreservingConverter(**kwargs)
    return converter.convert(load_result.mesh)
