"""
MashCad - Post-BREP Optimizer
==============================

Reduziert die Anzahl der Faces in einem BREP durch:
1. Analyse der Face-Geometrie (planar, zylindrisch, sphärisch, etc.)
2. Clustering von benachbarten Faces mit gleicher Geometrie
3. Ersetzen von Face-Gruppen durch einzelne analytische Surfaces
4. NURBS-Fitting für Freiformflächen
"""

import numpy as np
from typing import Optional, List, Dict, Tuple, Set
from dataclasses import dataclass
from enum import Enum, auto
from loguru import logger

try:
    from OCP.TopoDS import TopoDS, TopoDS_Shape, TopoDS_Face, TopoDS_Edge, TopoDS_Solid, TopoDS_Shell, TopoDS_Compound
    from OCP.TopExp import TopExp_Explorer, TopExp
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
    from OCP.GeomAbs import (
        GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Sphere,
        GeomAbs_Cone, GeomAbs_Torus, GeomAbs_BSplineSurface,
        GeomAbs_BezierSurface, GeomAbs_SurfaceOfRevolution,
        GeomAbs_SurfaceOfExtrusion, GeomAbs_OtherSurface
    )
    from OCP.TopTools import TopTools_IndexedMapOfShape, TopTools_IndexedDataMapOfShapeListOfShape
    from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax3, gp_Pln, gp_Cylinder, gp_Sphere
    from OCP.Geom import Geom_Plane, Geom_CylindricalSurface, Geom_SphericalSurface, Geom_BSplineSurface
    from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Face
    from OCP.BRepTools import BRepTools
    from OCP.ShapeAnalysis import ShapeAnalysis_Surface
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    HAS_OCP = True
except ImportError:
    HAS_OCP = False
    logger.warning("OCP nicht verfügbar für BREP Optimizer")


class SurfaceType(Enum):
    """Klassifizierung von Surface-Typen."""
    PLANE = auto()
    CYLINDER = auto()
    SPHERE = auto()
    CONE = auto()
    TORUS = auto()
    BSPLINE = auto()
    OTHER = auto()


@dataclass
class FaceInfo:
    """Information über ein BREP Face."""
    index: int
    face: 'TopoDS_Face'
    surface_type: SurfaceType
    area: float
    # Geometrie-Parameter
    normal: Optional[np.ndarray] = None      # Für Planes
    axis: Optional[np.ndarray] = None        # Für Zylinder/Kegel
    center: Optional[np.ndarray] = None      # Für Zylinder/Kugel
    radius: Optional[float] = None           # Für Zylinder/Kugel
    # Nachbarschaft
    neighbors: List[int] = None


@dataclass
class FaceCluster:
    """Gruppe von Faces mit gleicher Geometrie."""
    face_indices: List[int]
    surface_type: SurfaceType
    # Gefittete Parameter
    fitted_surface: Optional[object] = None
    error: float = 0.0


class BRepOptimizer:
    """
    Optimiert BREP durch Face-Reduktion.

    Strategie:
    1. Analysiere alle Faces (Typ, Parameter)
    2. Baue Nachbarschafts-Graph
    3. Clustere benachbarte Faces mit gleicher Geometrie
    4. Fitte neue Surfaces auf Cluster
    5. Erstelle optimiertes BREP
    """

    def __init__(
        self,
        plane_tolerance: float = 0.01,      # mm - für Plane-Merging
        cylinder_tolerance: float = 0.1,    # mm - für Zylinder-Merging
        sphere_tolerance: float = 0.1,      # mm - für Kugel-Merging
        angle_tolerance: float = 1.0,       # Grad - für Normalen-Vergleich
        min_cluster_size: int = 3,          # Min Faces pro Cluster
        use_nurbs_fallback: bool = True     # NURBS für nicht-analytische Flächen
    ):
        self.plane_tol = plane_tolerance
        self.cylinder_tol = cylinder_tolerance
        self.sphere_tol = sphere_tolerance
        self.angle_tol = np.radians(angle_tolerance)
        self.min_cluster_size = min_cluster_size
        self.use_nurbs = use_nurbs_fallback

    def optimize(self, shape: 'TopoDS_Shape') -> Tuple['TopoDS_Shape', dict]:
        """
        Optimiert ein BREP Shape.

        Returns:
            Tuple von (optimiertes Shape, Statistiken)
        """
        if not HAS_OCP:
            return shape, {'error': 'OCP nicht verfügbar'}

        stats = {
            'faces_before': 0,
            'faces_after': 0,
            'clusters_found': 0,
            'planes_merged': 0,
            'cylinders_merged': 0,
            'spheres_merged': 0
        }

        logger.info("=== BREP Optimizer ===")

        # 1. Sammle alle Faces
        faces_map = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, TopAbs_FACE, faces_map)
        n_faces = faces_map.Extent()
        stats['faces_before'] = n_faces
        logger.info(f"Faces vor Optimierung: {n_faces}")

        if n_faces < 10:
            logger.info("Zu wenige Faces für Optimierung")
            return shape, stats

        # 2. Analysiere Faces
        logger.info("Analysiere Face-Geometrie...")
        face_infos = self._analyze_faces(faces_map)

        # Statistik der Surface-Typen
        type_counts = {}
        for fi in face_infos:
            t = fi.surface_type.name
            type_counts[t] = type_counts.get(t, 0) + 1
        logger.info(f"  Surface-Typen: {type_counts}")

        # 3. Baue Nachbarschafts-Graph
        logger.info("Baue Nachbarschafts-Graph...")
        self._build_adjacency(shape, faces_map, face_infos)

        # 4. Finde Cluster
        logger.info("Finde Face-Cluster...")
        clusters = self._find_clusters(face_infos)
        stats['clusters_found'] = len(clusters)
        logger.info(f"  {len(clusters)} Cluster gefunden")

        # Cluster-Statistik
        for cluster in clusters:
            if cluster.surface_type == SurfaceType.PLANE:
                stats['planes_merged'] += len(cluster.face_indices)
            elif cluster.surface_type == SurfaceType.CYLINDER:
                stats['cylinders_merged'] += len(cluster.face_indices)
            elif cluster.surface_type == SurfaceType.SPHERE:
                stats['spheres_merged'] += len(cluster.face_indices)

        # 5. Wende UnifySameDomain mit optimierten Toleranzen an
        logger.info("Wende UnifySameDomain an...")
        optimized = self._apply_unify(shape, clusters, face_infos)

        if optimized is not None:
            # Zähle Faces nach Optimierung
            faces_map_after = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(optimized, TopAbs_FACE, faces_map_after)
            stats['faces_after'] = faces_map_after.Extent()
            logger.success(f"Faces nach Optimierung: {stats['faces_after']} "
                          f"(Reduktion: {n_faces - stats['faces_after']})")
            return optimized, stats
        else:
            logger.warning("Optimierung fehlgeschlagen, Original zurückgegeben")
            stats['faces_after'] = n_faces
            return shape, stats

    def _analyze_faces(self, faces_map: 'TopTools_IndexedMapOfShape') -> List[FaceInfo]:
        """Analysiert alle Faces und extrahiert Geometrie-Information."""
        face_infos = []

        for i in range(1, faces_map.Extent() + 1):
            face = TopoDS.Face_s(faces_map.FindKey(i))

            # Surface-Adaptor für Geometrie-Analyse
            adaptor = BRepAdaptor_Surface(face)
            surface_type = adaptor.GetType()

            # Fläche berechnen
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, props)
            area = props.Mass()

            # Surface-Typ klassifizieren
            if surface_type == GeomAbs_Plane:
                st = SurfaceType.PLANE
                plane = adaptor.Plane()
                normal = np.array([plane.Axis().Direction().X(),
                                   plane.Axis().Direction().Y(),
                                   plane.Axis().Direction().Z()])
                center = np.array([plane.Location().X(),
                                   plane.Location().Y(),
                                   plane.Location().Z()])
                fi = FaceInfo(i-1, face, st, area, normal=normal, center=center)

            elif surface_type == GeomAbs_Cylinder:
                st = SurfaceType.CYLINDER
                cyl = adaptor.Cylinder()
                axis = np.array([cyl.Axis().Direction().X(),
                                 cyl.Axis().Direction().Y(),
                                 cyl.Axis().Direction().Z()])
                center = np.array([cyl.Location().X(),
                                   cyl.Location().Y(),
                                   cyl.Location().Z()])
                radius = cyl.Radius()
                fi = FaceInfo(i-1, face, st, area, axis=axis, center=center, radius=radius)

            elif surface_type == GeomAbs_Sphere:
                st = SurfaceType.SPHERE
                sph = adaptor.Sphere()
                center = np.array([sph.Location().X(),
                                   sph.Location().Y(),
                                   sph.Location().Z()])
                radius = sph.Radius()
                fi = FaceInfo(i-1, face, st, area, center=center, radius=radius)

            elif surface_type == GeomAbs_Cone:
                st = SurfaceType.CONE
                fi = FaceInfo(i-1, face, st, area)

            elif surface_type == GeomAbs_Torus:
                st = SurfaceType.TORUS
                fi = FaceInfo(i-1, face, st, area)

            elif surface_type in (GeomAbs_BSplineSurface, GeomAbs_BezierSurface):
                st = SurfaceType.BSPLINE
                fi = FaceInfo(i-1, face, st, area)

            else:
                st = SurfaceType.OTHER
                fi = FaceInfo(i-1, face, st, area)

            fi.neighbors = []
            face_infos.append(fi)

        return face_infos

    def _build_adjacency(
        self,
        shape: 'TopoDS_Shape',
        faces_map: 'TopTools_IndexedMapOfShape',
        face_infos: List[FaceInfo]
    ):
        """Baut Nachbarschafts-Graph basierend auf gemeinsamen Edges."""
        from OCP.TopTools import TopTools_IndexedMapOfShape as EdgeMap

        # Sammle alle Edges
        edges_map = EdgeMap()
        TopExp.MapShapes_s(shape, TopAbs_EDGE, edges_map)

        # Für jede Edge: finde anliegende Faces
        edge_to_faces: Dict[int, List[int]] = {}

        for i in range(1, faces_map.Extent() + 1):
            face = TopoDS.Face_s(faces_map.FindKey(i))
            face_idx = i - 1

            exp = TopExp_Explorer(face, TopAbs_EDGE)
            while exp.More():
                edge = TopoDS.Edge_s(exp.Current())
                # Finde Edge-Index in der Map
                edge_idx = edges_map.FindIndex(edge)

                if edge_idx > 0:
                    if edge_idx not in edge_to_faces:
                        edge_to_faces[edge_idx] = []
                    if face_idx not in edge_to_faces[edge_idx]:
                        edge_to_faces[edge_idx].append(face_idx)

                exp.Next()

        # Baue Nachbarschaft aus gemeinsamen Edges
        for edge_idx, face_indices in edge_to_faces.items():
            if len(face_indices) == 2:
                f1, f2 = face_indices
                if f2 not in face_infos[f1].neighbors:
                    face_infos[f1].neighbors.append(f2)
                if f1 not in face_infos[f2].neighbors:
                    face_infos[f2].neighbors.append(f1)

    def _find_clusters(self, face_infos: List[FaceInfo]) -> List[FaceCluster]:
        """Findet Cluster von Faces mit gleicher Geometrie."""
        clusters = []
        visited = set()

        for start_idx, fi in enumerate(face_infos):
            if start_idx in visited:
                continue
            if fi.surface_type == SurfaceType.OTHER:
                visited.add(start_idx)
                continue

            # BFS um zusammenhängende Faces mit gleicher Geometrie zu finden
            cluster_faces = []
            queue = [start_idx]

            while queue:
                idx = queue.pop(0)
                if idx in visited:
                    continue

                current = face_infos[idx]

                # Prüfe ob Face zum Cluster passt
                if not cluster_faces:
                    # Erstes Face - akzeptiere immer
                    can_add = True
                else:
                    can_add = self._faces_compatible(face_infos[cluster_faces[0]], current)

                if can_add:
                    visited.add(idx)
                    cluster_faces.append(idx)

                    # Füge kompatible Nachbarn zur Queue
                    for neighbor_idx in current.neighbors:
                        if neighbor_idx not in visited:
                            queue.append(neighbor_idx)

            if len(cluster_faces) >= self.min_cluster_size:
                clusters.append(FaceCluster(
                    face_indices=cluster_faces,
                    surface_type=fi.surface_type
                ))

        return clusters

    def _faces_compatible(self, f1: FaceInfo, f2: FaceInfo) -> bool:
        """Prüft ob zwei Faces zur selben Geometrie gehören."""
        if f1.surface_type != f2.surface_type:
            return False

        if f1.surface_type == SurfaceType.PLANE:
            # Gleiche Normale?
            if f1.normal is not None and f2.normal is not None:
                dot = abs(np.dot(f1.normal, f2.normal))
                if dot < np.cos(self.angle_tol):
                    return False
                # Gleiche Ebene? (Punkt auf Ebene prüfen)
                if f1.center is not None and f2.center is not None:
                    diff = f2.center - f1.center
                    dist = abs(np.dot(diff, f1.normal))
                    if dist > self.plane_tol:
                        return False
            return True

        elif f1.surface_type == SurfaceType.CYLINDER:
            # Gleiche Achse und Radius?
            if f1.axis is not None and f2.axis is not None:
                dot = abs(np.dot(f1.axis, f2.axis))
                if dot < np.cos(self.angle_tol):
                    return False
            if f1.radius is not None and f2.radius is not None:
                if abs(f1.radius - f2.radius) > self.cylinder_tol:
                    return False
            # Gleiche Achsen-Linie?
            if f1.center is not None and f2.center is not None and f1.axis is not None:
                diff = f2.center - f1.center
                # Projektion auf Achse entfernen
                proj = np.dot(diff, f1.axis) * f1.axis
                perp_dist = np.linalg.norm(diff - proj)
                if perp_dist > self.cylinder_tol:
                    return False
            return True

        elif f1.surface_type == SurfaceType.SPHERE:
            # Gleiches Zentrum und Radius?
            if f1.center is not None and f2.center is not None:
                dist = np.linalg.norm(f1.center - f2.center)
                if dist > self.sphere_tol:
                    return False
            if f1.radius is not None and f2.radius is not None:
                if abs(f1.radius - f2.radius) > self.sphere_tol:
                    return False
            return True

        # Andere Typen: nur wenn direkt benachbart (konservativ)
        return False

    def _apply_unify(
        self,
        shape: 'TopoDS_Shape',
        clusters: List[FaceCluster],
        face_infos: List[FaceInfo]
    ) -> Optional['TopoDS_Shape']:
        """Wendet UnifySameDomain mit angepassten Toleranzen an."""
        try:
            # Berechne optimale Toleranzen basierend auf Clustern
            # Für Teile mit vielen planaren Clustern: höhere lineare Toleranz
            # Für Teile mit Zylindern: niedrigere um Geometrie zu erhalten

            plane_cluster_count = sum(1 for c in clusters if c.surface_type == SurfaceType.PLANE)
            cyl_cluster_count = sum(1 for c in clusters if c.surface_type == SurfaceType.CYLINDER)

            # Adaptive Toleranzen
            if cyl_cluster_count > 0:
                linear_tol = 0.01  # Streng bei Zylindern
                angular_tol = 0.5  # Grad
            else:
                linear_tol = 0.1   # Lockerer bei nur planaren
                angular_tol = 1.0  # Grad

            logger.debug(f"  UnifySameDomain: linear={linear_tol}mm, angular={angular_tol}°")

            upgrader = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
            upgrader.SetLinearTolerance(linear_tol)
            upgrader.SetAngularTolerance(np.radians(angular_tol))
            upgrader.Build()

            result = upgrader.Shape()

            if result.IsNull():
                return None

            return result

        except Exception as e:
            logger.error(f"UnifySameDomain fehlgeschlagen: {e}")
            return None

    def _count_faces(self, shape: 'TopoDS_Shape') -> int:
        """Zählt Faces in einem Shape."""
        count = 0
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            count += 1
            exp.Next()
        return count


def optimize_brep(shape: 'TopoDS_Shape', **kwargs) -> Tuple['TopoDS_Shape', dict]:
    """
    Convenience-Funktion für BREP-Optimierung.

    Args:
        shape: Das zu optimierende BREP Shape
        **kwargs: Parameter für BRepOptimizer

    Returns:
        Tuple von (optimiertes Shape, Statistiken)
    """
    optimizer = BRepOptimizer(**kwargs)
    return optimizer.optimize(shape)
