"""
MashCad - Post-BREP Optimizer V3
=================================

Reduziert die Anzahl der Faces in einem BREP durch:
1. Analyse der Face-Geometrie (planar, zylindrisch, sphärisch, etc.)
2. Clustering von benachbarten Faces mit gleicher Geometrie
3. **NEU V3**: Mesh-basierte Primitiv-Erkennung (vor BREP-Konvertierung)
4. **NEU**: NURBS-Fitting für organische Freiformflächen
5. Ersetzen von Face-Gruppen durch einzelne analytische Surfaces
"""

import numpy as np
from typing import Optional, List, Dict, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum, auto
from loguru import logger
try:
    from scipy.optimize import minimize, least_squares
    from scipy.spatial import ConvexHull
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    logger.warning("Scipy nicht verfügbar (Optimierung eingeschränkt)")

try:
    from sklearn.decomposition import PCA
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    logger.warning("Sklearn nicht verfügbar (PCA eingeschränkt)")

try:
    from OCP.TopoDS import TopoDS, TopoDS_Shape, TopoDS_Face, TopoDS_Edge, TopoDS_Solid, TopoDS_Shell, TopoDS_Compound, TopoDS_Wire
    from OCP.TopExp import TopExp_Explorer, TopExp
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX, TopAbs_WIRE
    from OCP.BRep import BRep_Tool, BRep_Builder
    from OCP.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
    from OCP.GeomAbs import (
        GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Sphere,
        GeomAbs_Cone, GeomAbs_Torus, GeomAbs_BSplineSurface,
        GeomAbs_BezierSurface, GeomAbs_SurfaceOfRevolution,
        GeomAbs_SurfaceOfExtrusion, GeomAbs_OtherSurface, GeomAbs_C2
    )
    from OCP.TopTools import TopTools_IndexedMapOfShape, TopTools_IndexedDataMapOfShapeListOfShape
    from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax3, gp_Ax2, gp_Pln, gp_Circ, gp_Ax1
    from OCP.Geom import Geom_Plane, Geom_CylindricalSurface, Geom_SphericalSurface, Geom_BSplineSurface
    from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeFace, BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid,
        BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    )
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Face, ShapeFix_Shell, ShapeFix_Solid
    from OCP.BRepTools import BRepTools
    from OCP.ShapeAnalysis import ShapeAnalysis_Surface
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeSphere
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
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
    fitted_params: Dict = field(default_factory=dict)
    error: float = 0.0


@dataclass
class CylinderFit:
    """Ergebnis eines Zylinder-Fits."""
    center: np.ndarray      # Punkt auf der Achse
    axis: np.ndarray        # Achsenrichtung (normalisiert)
    radius: float           # Radius
    height: float           # Höhe entlang Achse
    error: float            # RMS Fehler
    inlier_ratio: float     # Anteil der Punkte innerhalb Toleranz


@dataclass
class SphereFit:
    """Ergebnis eines Kugel-Fits."""
    center: np.ndarray      # Zentrum
    radius: float           # Radius
    error: float            # RMS Fehler
    inlier_ratio: float     # Anteil der Punkte innerhalb Toleranz


class PrimitiveDetector:
    """
    Erkennt analytische Primitive (Zylinder, Kugel) aus planaren Dreiecks-Gruppen.

    Algorithmus für Zylinder:
    1. Sammle alle Normalen der planaren Faces
    2. Finde gemeinsame Achse via PCA (Normalen rotieren um Achse)
    3. Fitte Radius via Median-Abstand zur Achse
    4. Validiere Fit-Qualität

    Algorithmus für Kugel:
    1. Sammle alle Vertices
    2. Algebraischer Fit: (x-cx)² + (y-cy)² + (z-cz)² = r²
    3. Validiere Fit-Qualität
    """

    def __init__(
        self,
        cylinder_tolerance: float = 0.5,    # mm - max Abweichung für Zylinder
        sphere_tolerance: float = 0.5,       # mm - max Abweichung für Kugel
        min_inlier_ratio: float = 0.85,      # Min 85% Inlier für gültigen Fit
        min_faces: int = 6                   # Min Faces für Primitiv-Erkennung
    ):
        self.cyl_tol = cylinder_tolerance
        self.sphere_tol = sphere_tolerance
        self.min_inlier = min_inlier_ratio
        self.min_faces = min_faces

    def detect_cylinder(
        self,
        points: np.ndarray,
        normals: Optional[np.ndarray] = None
    ) -> Optional[CylinderFit]:
        """
        Erkennt Zylinder aus Punktwolke.

        Methode: Direkter geometrischer Fit ohne Normalen-Abhängigkeit.
        1. PCA auf Punkte um Hauptachse zu finden
        2. Berechne Radius als Median-Abstand zur Achse
        3. Validiere durch Inlier-Ratio

        Args:
            points: Nx3 Array von Punkten
            normals: Optional - wird für Achsen-Validierung verwendet

        Returns:
            CylinderFit oder None wenn kein Zylinder erkannt
        """
        if len(points) < 10:
            return None

        if not HAS_SKLEARN:
            return None

        try:
            # Schritt 1: Finde Achse via PCA auf Punkten
            # Bei einem Zylinder ist die größte Varianz entlang der Achse
            centroid = np.mean(points, axis=0)
            centered = points - centroid

            pca = PCA(n_components=3)
            pca.fit(centered)

            # Erste Hauptkomponente = Achsenrichtung (größte Varianz)
            axis = pca.components_[0]
            axis = axis / np.linalg.norm(axis)

            # Prüfe ob die Varianz stark in einer Richtung ist (elongierter Shape)
            variances = pca.explained_variance_ratio_
            if variances[0] < 0.5:  # Nicht stark elongiert
                # Versuche andere Strategie: Kreuz-Produkt der Normalen
                if normals is not None and len(normals) > 5:
                    # Normalen sollten in einer Ebene liegen, die die Achse enthält
                    pca_n = PCA(n_components=3)
                    pca_n.fit(normals)
                    # Kleinste Varianz = Richtung senkrecht zur Normalen-Ebene = Achse
                    axis = pca_n.components_[2]
                    axis = axis / np.linalg.norm(axis)

            # Schritt 2: Berechne Radius
            # Abstand jedes Punktes zur Achse
            point_to_centroid = points - centroid
            proj_lengths = np.dot(point_to_centroid, axis)
            proj_on_axis = np.outer(proj_lengths, axis)
            radial_vectors = point_to_centroid - proj_on_axis
            distances = np.linalg.norm(radial_vectors, axis=1)

            # Robuster Radius via Median
            radius = np.median(distances)

            if radius < 0.1 or radius > 500:  # Unrealistische Werte
                return None

            # Schritt 3: Prüfe ob Punkte tatsächlich auf Zylindermantel liegen
            # Für echten Zylinder sollte die Distanz-Streuung klein sein
            dist_std = np.std(distances)
            if dist_std > radius * 0.3:  # Mehr als 30% Streuung
                return None

            # Schritt 4: Berechne Höhe
            height = proj_lengths.max() - proj_lengths.min()

            if height < 0.1:  # Zu flach
                return None

            # Schritt 5: Validiere Fit
            errors = np.abs(distances - radius)
            rms_error = np.sqrt(np.mean(errors**2))
            inlier_ratio = np.mean(errors < self.cyl_tol)

            if inlier_ratio < self.min_inlier:
                return None

            # Zusätzliche Validierung: Verhältnis Height/Radius
            # Ein Zylinder sollte nicht extrem flach sein (dann eher Disk)
            if height < radius * 0.1:
                return None

            return CylinderFit(
                center=centroid,
                axis=axis,
                radius=radius,
                height=height,
                error=rms_error,
                inlier_ratio=inlier_ratio
            )

        except Exception as e:
            logger.debug(f"Zylinder-Erkennung fehlgeschlagen: {e}")
            return None

    def detect_sphere(self, points: np.ndarray) -> Optional[SphereFit]:
        """
        Erkennt Kugel aus Punktwolke via algebraischem Fit.

        Methode: Löse überbestimmtes System
        x² + y² + z² = 2*cx*x + 2*cy*y + 2*cz*z + (r² - cx² - cy² - cz²)

        Args:
            points: Nx3 Array von Punkten

        Returns:
            SphereFit oder None wenn keine Kugel erkannt
        """
        if len(points) < 10:
            return None

        try:
            # Least Squares Setup
            A = np.column_stack([
                2 * points,
                np.ones(len(points))
            ])
            b = np.sum(points**2, axis=1)

            # Solve
            result, residuals, rank, s = np.linalg.lstsq(A, b, rcond=None)
            cx, cy, cz, d = result

            center = np.array([cx, cy, cz])
            radius_sq = d + cx**2 + cy**2 + cz**2

            if radius_sq <= 0:
                return None

            radius = np.sqrt(radius_sq)

            if radius < 0.1 or radius > 1000:  # Unrealistisch
                return None

            # Validiere Fit
            distances = np.linalg.norm(points - center, axis=1)
            errors = np.abs(distances - radius)
            rms_error = np.sqrt(np.mean(errors**2))
            inlier_ratio = np.mean(errors < self.sphere_tol)

            if inlier_ratio < self.min_inlier:
                return None

            return SphereFit(
                center=center,
                radius=radius,
                error=rms_error,
                inlier_ratio=inlier_ratio
            )

        except Exception:
            return None

    def refine_cylinder_fit(
        self,
        points: np.ndarray,
        initial: CylinderFit
    ) -> CylinderFit:
        """
        Verfeinert Zylinder-Fit via Levenberg-Marquardt.
        """
        if not HAS_SCIPY:
            return initial

        def residual(params):
            cx, cy, cz, ax, ay, az, r = params
            center = np.array([cx, cy, cz])
            axis = np.array([ax, ay, az])
            axis = axis / (np.linalg.norm(axis) + 1e-10)

            point_to_center = points - center
            proj = np.outer(np.dot(point_to_center, axis), axis)
            radial = point_to_center - proj
            distances = np.linalg.norm(radial, axis=1)

            return distances - r

        x0 = [
            *initial.center,
            *initial.axis,
            initial.radius
        ]

        try:
            result = least_squares(residual, x0, method='lm', max_nfev=100)
            cx, cy, cz, ax, ay, az, r = result.x

            center = np.array([cx, cy, cz])
            axis = np.array([ax, ay, az])
            axis = axis / np.linalg.norm(axis)

            # Neuberechnung der Metriken
            point_to_center = points - center
            proj = np.outer(np.dot(point_to_center, axis), axis)
            radial = point_to_center - proj
            distances = np.linalg.norm(radial, axis=1)

            errors = np.abs(distances - r)
            rms_error = np.sqrt(np.mean(errors**2))
            inlier_ratio = np.mean(errors < self.cyl_tol)

            # Höhe
            projections = np.dot(point_to_center, axis)
            height = projections.max() - projections.min()

            return CylinderFit(
                center=center,
                axis=axis,
                radius=abs(r),
                height=height,
                error=rms_error,
                inlier_ratio=inlier_ratio
            )
        except Exception:
            return initial


class NURBSFitter:
    """
    Fittet B-Spline (NURBS) Surfaces auf Punktwolken.

    Für organische/Freiform-Flächen die nicht durch analytische
    Primitive (Plane, Cylinder, Sphere) abgebildet werden können.
    """

    def __init__(
        self,
        grid_size: int = 15,          # Auflösung des UV-Grids
        degree: int = 3,               # B-Spline Grad
        tolerance: float = 0.1         # Fitting-Toleranz in mm
    ):
        self.grid_size = grid_size
        self.degree = degree
        self.tolerance = tolerance

    def fit_bspline(
        self,
        points: np.ndarray,
        normals: Optional[np.ndarray] = None
    ) -> Optional[Tuple['Geom_BSplineSurface', float]]:
        """
        Fittet B-Spline Surface auf Punktwolke.

        Args:
            points: Nx3 Array von Punkten
            normals: Optional Nx3 Array von Normalen

        Returns:
            Tuple von (Geom_BSplineSurface, Fitting-Fehler) oder None
        """
        if not HAS_OCP:
            return None

        if len(points) < 9:  # Min 3x3 Grid
            return None

        try:
            # Schritt 1: Projiziere Punkte auf lokales UV-Grid
            grid_points = self._project_to_grid(points, normals)

            if grid_points is None:
                return None

            # Schritt 2: Erstelle TColgp_Array2OfPnt
            n = self.grid_size
            pnt_array = TColgp_Array2OfPnt(1, n, 1, n)

            for i in range(n):
                for j in range(n):
                    pt = grid_points[i, j]
                    pnt_array.SetValue(i + 1, j + 1, gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2])))

            # Schritt 3: B-Spline Fitting
            fitter = GeomAPI_PointsToBSplineSurface(
                pnt_array,
                self.degree,      # DegMin
                8,                # DegMax
                GeomAbs_C2,       # Kontinuität
                self.tolerance    # Toleranz
            )

            if not fitter.IsDone():
                logger.debug("  B-Spline Fitting fehlgeschlagen")
                return None

            surface = fitter.Surface()

            # Schritt 4: Berechne Fitting-Fehler
            error = self._compute_fitting_error(points, surface)

            return surface, error

        except Exception as e:
            logger.debug(f"  NURBS Fitting Fehler: {e}")
            return None

    def _project_to_grid(
        self,
        points: np.ndarray,
        normals: Optional[np.ndarray]
    ) -> Optional[np.ndarray]:
        """
        Projiziert unstrukturierte Punkte auf reguläres UV-Grid.

        Verwendet PCA für lokales Koordinatensystem.
        """
        if not HAS_SKLEARN:
            return None

        try:
            # PCA für lokales 2D Koordinatensystem
            pca = PCA(n_components=2)
            uv = pca.fit_transform(points)

            # Grid-Grenzen
            u_min, u_max = uv[:, 0].min(), uv[:, 0].max()
            v_min, v_max = uv[:, 1].min(), uv[:, 1].max()

            # Etwas Padding
            u_pad = (u_max - u_min) * 0.02
            v_pad = (v_max - v_min) * 0.02
            u_min -= u_pad
            u_max += u_pad
            v_min -= v_pad
            v_max += v_pad

            n = self.grid_size
            grid = np.zeros((n, n, 3))

            for i in range(n):
                for j in range(n):
                    u = u_min + (u_max - u_min) * i / (n - 1)
                    v = v_min + (v_max - v_min) * j / (n - 1)

                    # Finde nächsten Punkt (gewichtet)
                    distances = np.sqrt((uv[:, 0] - u)**2 + (uv[:, 1] - v)**2)

                    # Inverse Distance Weighting
                    weights = 1.0 / (distances + 1e-10)
                    weights = weights / weights.sum()

                    # Gewichteter Mittelwert der nächsten Punkte
                    grid[i, j] = np.sum(points * weights[:, np.newaxis], axis=0)

            return grid

        except Exception as e:
            logger.debug(f"  Grid-Projektion fehlgeschlagen: {e}")
            return None

    def _compute_fitting_error(
        self,
        points: np.ndarray,
        surface: 'Geom_BSplineSurface'
    ) -> float:
        """Berechnet RMS-Fehler des Surface-Fits."""
        try:
            from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf

            errors = []
            # Sample subset für Performance
            sample_indices = np.random.choice(
                len(points),
                min(100, len(points)),
                replace=False
            )

            for idx in sample_indices:
                pt = points[idx]
                pnt = gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2]))

                projector = GeomAPI_ProjectPointOnSurf(pnt, surface)
                if projector.NbPoints() > 0:
                    dist = projector.LowerDistance()
                    errors.append(dist)

            if errors:
                return np.sqrt(np.mean(np.array(errors)**2))
            return float('inf')

        except Exception:
            return float('inf')


class BRepOptimizer:
    """
    Optimiert BREP durch Face-Reduktion.

    Strategie:
    1. Analysiere alle Faces (Typ, Parameter)
    2. Baue Nachbarschafts-Graph
    3. Clustere benachbarte Faces mit gleicher Geometrie
    4. **NEU**: Erkenne Zylinder/Kugeln in planaren Face-Gruppen
    5. **NEU**: Fitte NURBS auf verbleibende Freiform-Gruppen
    6. Erstelle optimiertes BREP mit analytischen Surfaces
    """

    def __init__(
        self,
        plane_tolerance: float = 0.01,      # mm - für Plane-Merging
        cylinder_tolerance: float = 1.0,    # mm - für Zylinder-Erkennung (höher für Mesh-Daten)
        sphere_tolerance: float = 1.0,      # mm - für Kugel-Erkennung (höher für Mesh-Daten)
        angle_tolerance: float = 1.0,       # Grad - für Normalen-Vergleich
        min_cluster_size: int = 3,          # Min Faces pro Cluster
        min_inlier_ratio: float = 0.80,     # 80% Inlier für Primitiv-Erkennung
        use_primitive_detection: bool = True,   # Zylinder/Kugel-Erkennung
        use_nurbs_fallback: bool = True,    # NURBS für Freiformflächen
        aggressive_mode: bool = False       # Aggressivere Reduktion
    ):
        self.plane_tol = plane_tolerance
        self.cylinder_tol = cylinder_tolerance
        self.sphere_tol = sphere_tolerance
        self.angle_tol = np.radians(angle_tolerance)
        self.min_cluster_size = min_cluster_size
        self.min_inlier_ratio = min_inlier_ratio
        self.use_primitive_detection = use_primitive_detection
        self.use_nurbs = use_nurbs_fallback
        self.aggressive = aggressive_mode

        # Sub-Module
        self.primitive_detector = PrimitiveDetector(
            cylinder_tolerance=cylinder_tolerance,
            sphere_tolerance=sphere_tolerance,
            min_inlier_ratio=min_inlier_ratio
        )
        self.nurbs_fitter = NURBSFitter()

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
            'cylinders_detected': 0,
            'spheres_merged': 0,
            'spheres_detected': 0,
            'nurbs_fitted': 0
        }

        logger.info("=== BREP Optimizer V2 ===")

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

        # 4. Finde Cluster (bestehende analytische Surfaces)
        logger.info("Finde Face-Cluster...")
        clusters = self._find_clusters(face_infos)
        stats['clusters_found'] = len(clusters)
        logger.info(f"  {len(clusters)} Cluster gefunden")

        # 5. NEU: Erkenne Zylinder/Kugeln in planaren Face-Gruppen
        if self.use_primitive_detection:
            logger.info("Erkenne Primitive in planaren Gruppen...")
            detected = self._detect_primitives_in_planar_groups(face_infos, faces_map)
            stats['cylinders_detected'] = detected.get('cylinders', 0)
            stats['spheres_detected'] = detected.get('spheres', 0)

        # Cluster-Statistik
        for cluster in clusters:
            if cluster.surface_type == SurfaceType.PLANE:
                stats['planes_merged'] += len(cluster.face_indices)
            elif cluster.surface_type == SurfaceType.CYLINDER:
                stats['cylinders_merged'] += len(cluster.face_indices)
            elif cluster.surface_type == SurfaceType.SPHERE:
                stats['spheres_merged'] += len(cluster.face_indices)

        # 6. Ersetze erkannte Zylinder durch echte Zylinderflächen
        if self.use_primitive_detection and detected.get('_cylinder_fits'):
            logger.info("Ersetze planare Faces durch Zylinderflächen...")
            shape = self._replace_with_cylinders(
                shape, faces_map, face_infos, detected['_cylinder_fits']
            )
            # Aktualisiere faces_map nach Ersetzung
            faces_map = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(shape, TopAbs_FACE, faces_map)

        # 7. Wende UnifySameDomain mit optimierten Toleranzen an
        logger.info("Wende UnifySameDomain an...")
        optimized = self._apply_unify(shape, clusters, face_infos)

        if optimized is not None:
            # Zähle Faces nach Optimierung
            faces_map_after = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(optimized, TopAbs_FACE, faces_map_after)
            stats['faces_after'] = faces_map_after.Extent()

            # 7. Wenn noch zu viele Faces: Versuche NURBS für große Cluster
            if self.use_nurbs and stats['faces_after'] > 500:
                logger.info("Versuche NURBS-Fitting für große planare Gruppen...")
                # TODO: NURBS-Replacement in zukünftiger Version

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

    def _detect_primitives_in_planar_groups(
        self,
        face_infos: List[FaceInfo],
        faces_map: 'TopTools_IndexedMapOfShape'
    ) -> Dict[str, int]:
        """
        Erkennt Zylinder/Kugeln in Gruppen von planaren Faces.

        Bei Mesh-Konvertierung werden Zylinder oft als viele kleine
        planare Dreiecke approximiert. Diese Methode erkennt solche Muster.

        Strategie:
        1. Finde zusammenhängende planare Gruppen
        2. Analysiere Normalen-Verteilung: Bei Zylindern rotieren Normalen um Achse
        3. Fitte geometrisch auf extrahierte Punkte
        """
        result = {'cylinders': 0, 'spheres': 0}

        # Finde zusammenhängende Gruppen von planaren Faces
        planar_indices = [
            i for i, fi in enumerate(face_infos)
            if fi.surface_type == SurfaceType.PLANE
        ]

        if len(planar_indices) < 6:
            return result

        # Gruppiere planare Faces nach Nachbarschaft
        visited = set()
        groups = []

        for start_idx in planar_indices:
            if start_idx in visited:
                continue

            # BFS für zusammenhängende Gruppe
            group = []
            queue = [start_idx]

            while queue:
                idx = queue.pop(0)
                if idx in visited:
                    continue
                if face_infos[idx].surface_type != SurfaceType.PLANE:
                    continue

                visited.add(idx)
                group.append(idx)

                # Nur planare Nachbarn hinzufügen
                for neighbor in face_infos[idx].neighbors:
                    if neighbor not in visited and neighbor in planar_indices:
                        queue.append(neighbor)

            if len(group) >= 6:  # Min 6 Faces für Primitiv
                groups.append(group)

        logger.debug(f"  {len(groups)} planare Gruppen mit >= 6 Faces gefunden")

        # PHASE 1: Zylinder/Kugel-Erkennung auf ORIGINALEN verbundenen Gruppen
        # (Vor Sub-Segmentierung, weil Zylinder-Normalen radial variieren)
        groups.sort(key=len, reverse=True)

        for group in groups:
            if len(group) < 6:
                continue

            # Extrahiere Punkte und Normalen aus der Gruppe
            points, normals = self._extract_points_from_faces(
                [face_infos[i].face for i in group]
            )

            if len(points) < 10:
                continue

            # Analysiere Normalen-Verteilung
            # Bei Zylinder: Normalen zeigen radial nach außen → 2D Varianz hoch
            # Bei Ebene: Alle Normalen gleich → niedrige Varianz
            # Bei Kugel: Normalen zeigen radial von Center → 3D Varianz hoch
            if len(normals) > 5:
                normal_variance = np.var(normals, axis=0).sum()

                # Nur wenn signifikante Normalen-Variation
                if normal_variance < 0.01:
                    continue  # Wahrscheinlich eine große Ebene

            # Versuche Zylinder-Fit zuerst (häufiger als Kugel)
            cyl_fit = self.primitive_detector.detect_cylinder(points, normals)

            if cyl_fit is not None:
                # Zusätzliche Validierung: Mindest-Größe
                if cyl_fit.radius >= 0.5 and cyl_fit.height >= 0.5:
                    logger.info(f"    Zylinder erkannt ({len(group)} Faces): "
                               f"R={cyl_fit.radius:.2f}mm, H={cyl_fit.height:.2f}mm, "
                               f"Error={cyl_fit.error:.3f}mm, Inlier={cyl_fit.inlier_ratio:.1%}")

                    # Verfeinere Fit
                    refined = self.primitive_detector.refine_cylinder_fit(points, cyl_fit)
                    if refined.error < cyl_fit.error:
                        cyl_fit = refined
                        logger.debug(f"      Refined: Error={cyl_fit.error:.3f}mm")

                    result['cylinders'] += 1

                    # Markiere Faces als CYLINDER
                    for idx in group:
                        face_infos[idx].surface_type = SurfaceType.CYLINDER
                        face_infos[idx].axis = cyl_fit.axis
                        face_infos[idx].center = cyl_fit.center
                        face_infos[idx].radius = cyl_fit.radius

                    continue  # Nächste Gruppe

            # Versuche Kugel-Fit
            sphere_fit = self.primitive_detector.detect_sphere(points)

            if sphere_fit is not None:
                # Validierung: Realistische Größe
                if 0.5 <= sphere_fit.radius <= 100:
                    logger.info(f"    Kugel erkannt ({len(group)} Faces): "
                               f"R={sphere_fit.radius:.2f}mm, "
                               f"Error={sphere_fit.error:.3f}mm, Inlier={sphere_fit.inlier_ratio:.1%}")

                    result['spheres'] += 1

                    # Markiere Faces als SPHERE
                    for idx in group:
                        face_infos[idx].surface_type = SurfaceType.SPHERE
                        face_infos[idx].center = sphere_fit.center
                        face_infos[idx].radius = sphere_fit.radius

        # PHASE 2: Lokale Zylinder-Suche in großen Gruppen
        # DEAKTIVIERT: Verursacht mehr Probleme als sie löst bei Mesh-Daten
        # Die triangulierte Mesh-Struktur macht es sehr schwer, echte Zylinder
        # von falschen Positiven zu unterscheiden.
        #
        # TODO: Besserer Ansatz in Zukunft:
        # - Curvature-basierte Segmentierung
        # - Oder manuelle Zylinder-Annotation durch User

        all_cylinder_fits = []
        result['_cylinder_fits'] = all_cylinder_fits

        # Info über große Gruppen die übersprungen werden
        large_groups = [g for g in groups if len(g) > 500]
        if large_groups:
            total_faces = sum(len(g) for g in large_groups)
            logger.info(f"    {len(large_groups)} große planare Gruppen ({total_faces} Faces) - "
                       f"lokale Zylinder-Suche deaktiviert")

        return result

    def _find_local_cylinders(
        self,
        group: List[int],
        face_infos: List[FaceInfo]
    ) -> List[Tuple[List[int], CylinderFit]]:
        """
        Sucht lokale zylindrische Regionen via Region Growing.

        Neue Strategie (statt RANSAC):
        1. Finde Seed-Faces mit hoher lokaler Normalen-Variation (Indikator für Krümmung)
        2. Wachse Region von Seeds aus
        3. Fitte Zylinder auf gewachsene Regionen
        4. Validiere geometrisch
        """
        found = []
        used = set()
        group_set = set(group)

        # Sammle Geometrie-Daten für alle Faces
        face_data = {}  # idx -> (centroid, normal)
        for idx in group:
            if face_infos[idx].normal is None:
                continue

            face = face_infos[idx].face
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, props)
            center = props.CentreOfMass()
            centroid = np.array([center.X(), center.Y(), center.Z()])

            face_data[idx] = (centroid, face_infos[idx].normal)

        if len(face_data) < 20:
            return found

        # Berechne lokale Normalen-Variation für jedes Face
        # Faces mit hoher Variation in der Nachbarschaft sind Kandidaten für Zylinder
        curvature_candidates = []

        for idx in group:
            if idx not in face_data:
                continue

            # Sammle Nachbar-Normalen
            neighbor_normals = []
            for n_idx in face_infos[idx].neighbors:
                if n_idx in face_data:
                    neighbor_normals.append(face_data[n_idx][1])

            if len(neighbor_normals) < 2:
                continue

            # Berechne Normalen-Variation
            neighbor_normals = np.array(neighbor_normals)
            my_normal = face_data[idx][1]

            # Dot products mit Nachbarn
            dots = np.dot(neighbor_normals, my_normal)
            variation = 1.0 - np.mean(dots)  # Höher = mehr Krümmung

            # Zylinder-Kandidaten haben moderate Variation (nicht 0, nicht 1)
            if 0.05 < variation < 0.5:
                curvature_candidates.append((idx, variation))

        # Sortiere nach Variation (mittlere Werte bevorzugen)
        curvature_candidates.sort(key=lambda x: abs(x[1] - 0.15))

        logger.debug(f"      {len(curvature_candidates)} Krümmungs-Kandidaten gefunden")

        # Region Growing von den besten Kandidaten
        for seed_idx, _ in curvature_candidates[:50]:  # Max 50 Seeds probieren
            if seed_idx in used:
                continue

            # Wachse Region
            region = self._grow_cylinder_region(seed_idx, group_set, face_data, face_infos, used)

            if len(region) < 15:  # Min 15 Faces für Zylinder
                continue

            # Extrahiere Geometrie
            centroids = np.array([face_data[i][0] for i in region])
            normals = np.array([face_data[i][1] for i in region])

            # Fitte Zylinder
            cyl = self._fit_cylinder_ransac(centroids, normals)
            if cyl is None:
                continue

            # Validierung
            if not self._validate_cylinder(cyl, centroids, normals, region):
                continue

            # Erstelle CylinderFit
            cyl_fit = CylinderFit(
                center=cyl['center'],
                axis=cyl['axis'],
                radius=cyl['radius'],
                height=cyl['height'],
                error=cyl.get('error', 0.5),
                inlier_ratio=len(region) / len(face_data)
            )

            found.append((list(region), cyl_fit))
            used.update(region)

            if len(found) >= 20:  # Max 20 Zylinder
                break

        return found

    def _grow_cylinder_region(
        self,
        seed: int,
        group_set: set,
        face_data: dict,
        face_infos: List[FaceInfo],
        used: set
    ) -> set:
        """Wächst Region von Seed für potentiellen Zylinder."""
        region = {seed}
        to_check = set(face_infos[seed].neighbors) & group_set - used

        seed_centroid, seed_normal = face_data[seed]
        region_normals = [seed_normal]

        max_region_size = 200

        while to_check and len(region) < max_region_size:
            best_candidate = None
            best_score = -1

            for candidate in list(to_check):
                if candidate in used or candidate in region:
                    to_check.discard(candidate)
                    continue
                if candidate not in face_data:
                    to_check.discard(candidate)
                    continue

                c_centroid, c_normal = face_data[candidate]

                # Score: Bevorzuge Faces die...
                # 1. Nahe an der Region sind (connected)
                # 2. Normalen haben die zur "Rotation" passen

                # Prüfe Normalen-Konsistenz mit Region
                region_avg_normal = np.mean(region_normals, axis=0)
                region_avg_normal = region_avg_normal / (np.linalg.norm(region_avg_normal) + 1e-10)

                dot = np.dot(c_normal, region_avg_normal)

                # Für Zylinder: Normalen sollten leicht variieren (nicht gleich, nicht orthogonal)
                # Idealer Bereich: dot zwischen 0.5 und 0.98
                if 0.3 < dot < 0.99:
                    # Score basierend auf wie gut der Winkel zur Zylinder-Krümmung passt
                    score = 1.0 - abs(dot - 0.8)  # Optimal bei ~37° Unterschied
                    if score > best_score:
                        best_score = score
                        best_candidate = candidate

            if best_candidate is None:
                break

            region.add(best_candidate)
            region_normals.append(face_data[best_candidate][1])
            to_check.discard(best_candidate)

            # Füge Nachbarn des neuen Face hinzu
            new_neighbors = set(face_infos[best_candidate].neighbors) & group_set - region - used
            to_check.update(new_neighbors)

        return region

    def _validate_cylinder(
        self,
        cyl: dict,
        centroids: np.ndarray,
        normals: np.ndarray,
        region: set
    ) -> bool:
        """Validiert ob der gefittete Zylinder plausibel ist."""
        radius = cyl['radius']
        height = cyl['height']
        error = cyl.get('error', 1.0)

        # 1. Radius: 1.5mm - 15mm (typische Bohrungen/Pins)
        if radius < 1.5 or radius > 15:
            return False

        # 2. Höhe mindestens so groß wie Radius
        if height < radius * 0.3:
            return False

        # 3. Fit-Fehler max 25% des Radius
        if error > radius * 0.25:
            return False

        # 4. Geometrische Konsistenz - Punkte auf Zylindermantel
        axis = cyl['axis']
        center = cyl['center']

        to_center = centroids - center
        proj = np.outer(np.dot(to_center, axis), axis)
        radial = to_center - proj
        distances = np.linalg.norm(radial, axis=1)

        radius_errors = np.abs(distances - radius)
        if np.mean(radius_errors) > max(1.0, radius * 0.15):
            return False

        return True

    def _fit_cylinder_ransac(
        self,
        centroids: np.ndarray,
        normals: np.ndarray
    ) -> Optional[dict]:
        """
        Fittet Zylinder auf Zentroide und Normalen.

        Strategie: Nutze Normalen um Achse zu finden, validiere durch Geometrie.
        Bei Mesh-Daten sind Normalen oft ungenau, daher lockere Normalen-Checks.
        """
        if len(centroids) < 5:
            return None

        if not HAS_SKLEARN:
            return None

        try:
            # Methode 1: Achse aus Normalen-PCA
            # Bei Zylinder zeigen Normalen senkrecht zur Achse
            pca_n = PCA(n_components=3)
            pca_n.fit(normals)
            variances = pca_n.explained_variance_ratio_

            axis = None

            # Wenn Normalen-Varianz eine klare Achse zeigt
            if variances[2] < 0.25:  # Lockerer Schwellwert für Mesh-Daten
                axis = pca_n.components_[2]
                axis = axis / np.linalg.norm(axis)

                # Prüfe ob Normalen überwiegend senkrecht zur Achse
                dots = np.abs(np.dot(normals, axis))
                mean_dot = np.mean(dots)
                if mean_dot > 0.5:  # Sehr locker für Mesh-Daten
                    axis = None  # Achse aus Normalen nicht brauchbar

            # Methode 2: Fallback - Achse aus Punkt-Verteilung
            if axis is None:
                pca_p = PCA(n_components=3)
                pca_p.fit(centroids)

                # Bei Zylinder: größte Varianz entlang Achse
                axis = pca_p.components_[0]
                axis = axis / np.linalg.norm(axis)

            # Zentrum auf Achse
            center = np.mean(centroids, axis=0)

            # Radius: Abstand der Zentroide zur Achse
            to_center = centroids - center
            proj = np.outer(np.dot(to_center, axis), axis)
            radial = to_center - proj
            distances = np.linalg.norm(radial, axis=1)

            radius = np.median(distances)
            radius_std = np.std(distances)

            # WICHTIGSTE VALIDIERUNG: Geometrische Konsistenz
            # Bei echtem Zylinder sollten alle Punkte gleichen Abstand zur Achse haben
            if radius_std > radius * 0.30:  # Max 30% Streuung
                return None

            # Höhe
            projections = np.dot(to_center, axis)
            height = projections.max() - projections.min()

            # Höhe sollte signifikant sein
            if height < 1.0:  # Min 1mm Höhe
                return None

            return {
                'center': center,
                'axis': axis,
                'radius': radius,
                'height': height,
                'error': radius_std
            }

        except Exception:
            return None

    def _get_cylinder_inliers(
        self,
        points: np.ndarray,
        center: np.ndarray,
        axis: np.ndarray,
        radius: float,
        threshold: float
    ) -> np.ndarray:
        """Findet Punkte die auf dem Zylinder liegen."""
        to_center = points - center
        proj = np.outer(np.dot(to_center, axis), axis)
        radial = to_center - proj
        distances = np.linalg.norm(radial, axis=1)

        # Inlier = Abstand zur Zylinderoberfläche < threshold
        errors = np.abs(distances - radius)
        return errors < threshold

    def _grow_region_for_cylinder(
        self,
        seed: int,
        group: List[int],
        face_infos: List[FaceInfo],
        used: set
    ) -> List[int]:
        """Wächst Region von Seed-Face für potentiellen Zylinder."""
        group_set = set(group)
        region = [seed]
        candidates = set(face_infos[seed].neighbors) & group_set - used

        # Sammle initiale Geometrie
        seed_normal = face_infos[seed].normal
        if seed_normal is None:
            return region

        max_size = 150

        while candidates and len(region) < max_size:
            best = None
            best_score = -1

            for c in list(candidates):
                if c in used or c in region:
                    candidates.discard(c)
                    continue

                c_normal = face_infos[c].normal
                if c_normal is None:
                    candidates.discard(c)
                    continue

                # Score: Bevorzuge Faces mit ähnlich großem Normalen-Unterschied
                # (konsistent mit zylindrischer Krümmung)
                region_normals = [face_infos[r].normal for r in region
                                 if face_infos[r].normal is not None]

                if region_normals:
                    # Prüfe ob neue Normale in die "Rotations-Richtung" passt
                    avg_normal = np.mean(region_normals, axis=0)
                    dot = np.abs(np.dot(c_normal, avg_normal))

                    # Nicht zu ähnlich (Ebene) und nicht zu unterschiedlich (anderes Primitiv)
                    if 0.3 < dot < 0.95:
                        score = 1.0 - abs(dot - 0.7)  # Optimal bei ~45° Unterschied
                        if score > best_score:
                            best_score = score
                            best = c

            if best is None:
                break

            region.append(best)
            candidates.discard(best)
            candidates.update(set(face_infos[best].neighbors) & group_set - set(region) - used)

        return region

    def _extract_points_from_faces(
        self,
        faces: List['TopoDS_Face']
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Extrahiert Punkte und Normalen aus einer Liste von Faces.
        """
        points = []
        normals = []

        for face in faces:
            # Hole Vertices des Faces
            exp = TopExp_Explorer(face, TopAbs_VERTEX)
            face_points = []

            while exp.More():
                vertex = TopoDS.Vertex_s(exp.Current())
                pnt = BRep_Tool.Pnt_s(vertex)
                face_points.append([pnt.X(), pnt.Y(), pnt.Z()])
                exp.Next()

            if face_points:
                points.extend(face_points)

                # Normale aus Surface-Adaptor
                adaptor = BRepAdaptor_Surface(face)
                u_mid = (adaptor.FirstUParameter() + adaptor.LastUParameter()) / 2
                v_mid = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2

                try:
                    pnt = gp_Pnt()
                    d1u = gp_Vec()
                    d1v = gp_Vec()
                    adaptor.D1(u_mid, v_mid, pnt, d1u, d1v)
                    normal = d1u.Crossed(d1v)
                    if normal.Magnitude() > 1e-10:
                        normal.Normalize()
                        n = [normal.X(), normal.Y(), normal.Z()]
                        # Eine Normale pro Face-Punkt
                        normals.extend([n] * len(face_points))
                except Exception:
                    # Fallback: Aus Plane
                    if adaptor.GetType() == GeomAbs_Plane:
                        plane = adaptor.Plane()
                        d = plane.Axis().Direction()
                        n = [d.X(), d.Y(), d.Z()]
                        normals.extend([n] * len(face_points))

        points = np.array(points) if points else np.array([]).reshape(0, 3)
        normals = np.array(normals) if normals else np.array([]).reshape(0, 3)

        # Dedupliziere Punkte (Vertices werden mehrfach gezählt)
        if len(points) > 0:
            unique_points, indices = np.unique(
                np.round(points, decimals=6),
                axis=0,
                return_index=True
            )
            points = points[indices]
            if len(normals) > 0:
                normals = normals[indices]

        return points, normals

    def _subsegment_by_normals(
        self,
        group: List[int],
        face_infos: List[FaceInfo]
    ) -> List[List[int]]:
        """
        Unterteilt eine große Gruppe in kleinere Sub-Gruppen basierend auf Normalen.

        Für Zylinder: Faces deren Normalen in einer Ebene rotieren bilden eine Gruppe.
        Für Ebenen: Faces mit gleicher Normale bilden eine Gruppe.
        """
        from scipy.cluster.hierarchy import fcluster, linkage

        if len(group) < 10:
            return [group]

        # Sammle Normalen
        normals = []
        for idx in group:
            if face_infos[idx].normal is not None:
                normals.append(face_infos[idx].normal)
            else:
                # Berechne Normale aus Face
                adaptor = BRepAdaptor_Surface(face_infos[idx].face)
                if adaptor.GetType() == GeomAbs_Plane:
                    plane = adaptor.Plane()
                    d = plane.Axis().Direction()
                    normals.append([d.X(), d.Y(), d.Z()])
                else:
                    normals.append([0, 0, 1])  # Fallback

        normals = np.array(normals)

        if len(normals) < 10:
            return [group]

        try:
            # Hierarchisches Clustering auf Normalen
            # Verwende Winkel-basierte Distanz
            Z = linkage(normals, method='ward')

            # Finde optimale Cluster-Anzahl durch Elbow-Methode
            # oder verwende feste Schwelle
            max_clusters = min(50, len(group) // 10)

            # Cluster mit Distanz-Schwelle
            threshold = 0.5  # Entspricht ca. 30° Winkelunterschied
            labels = fcluster(Z, threshold, criterion='distance')

            # Gruppiere nach Labels
            sub_groups = {}
            for i, label in enumerate(labels):
                if label not in sub_groups:
                    sub_groups[label] = []
                sub_groups[label].append(group[i])

            # Filtere kleine Gruppen
            result = [g for g in sub_groups.values() if len(g) >= 6]

            if not result:
                return [group]

            return result

        except Exception as e:
            logger.debug(f"Sub-Segmentierung fehlgeschlagen: {e}")
            return [group]

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

    def _replace_with_cylinders(
        self,
        shape: 'TopoDS_Shape',
        faces_map: 'TopTools_IndexedMapOfShape',
        face_infos: List[FaceInfo],
        cylinder_fits: List[Tuple[List[int], CylinderFit]]
    ) -> 'TopoDS_Shape':
        """
        Ersetzt Gruppen von planaren Faces durch echte Zylinderflächen.

        Args:
            shape: Original Shape
            faces_map: Map der Faces
            face_infos: Face-Informationen
            cylinder_fits: Liste von (face_indices, CylinderFit)

        Returns:
            Neues Shape mit Zylinderflächen
        """
        if not cylinder_fits:
            logger.debug("  Keine Zylinder-Fits vorhanden")
            return shape

        logger.info(f"  Verarbeite {len(cylinder_fits)} Zylinder-Fits...")

        try:
            # Sammle alle zu ersetzenden Face-Indizes
            faces_to_remove = set()
            new_cylinder_faces = []
            failed_cylinders = 0

            for i, (cyl_faces, cyl_fit) in enumerate(cylinder_fits):
                logger.debug(f"  Zylinder {i+1}: {len(cyl_faces)} Faces, R={cyl_fit.radius:.2f}mm")

                if len(cyl_faces) < 10:
                    logger.debug(f"    Übersprungen: Zu wenige Faces ({len(cyl_faces)} < 10)")
                    continue

                faces_to_remove.update(cyl_faces)

                # Erstelle Zylinderfläche
                cyl_face = self._create_cylinder_face(cyl_faces, cyl_fit, face_infos)
                if cyl_face is not None:
                    new_cylinder_faces.append(cyl_face)
                else:
                    failed_cylinders += 1
                    # Entferne Faces nicht wenn Erstellung fehlschlägt
                    faces_to_remove -= set(cyl_faces)

            logger.info(f"  {len(new_cylinder_faces)} Zylinder erfolgreich, {failed_cylinders} fehlgeschlagen")

            if not new_cylinder_faces:
                logger.warning("  Keine Zylinder-Faces erstellt - behalte Original")
                return shape

            logger.info(f"  {len(new_cylinder_faces)} Zylinder-Faces erstellt, "
                       f"{len(faces_to_remove)} planare Faces werden entfernt")

            # Erstelle neues Shape mit Sewing
            sewer = BRepBuilderAPI_Sewing(0.1)  # Toleranz

            # Füge alle Original-Faces hinzu, außer die zu ersetzenden
            for i in range(1, faces_map.Extent() + 1):
                face_idx = i - 1
                if face_idx not in faces_to_remove:
                    face = TopoDS.Face_s(faces_map.FindKey(i))
                    sewer.Add(face)

            # Füge neue Zylinder-Faces hinzu
            for cyl_face in new_cylinder_faces:
                sewer.Add(cyl_face)

            sewer.Perform()
            sewed = sewer.SewedShape()

            if sewed.IsNull():
                logger.warning("  Sewing nach Zylinder-Ersetzung fehlgeschlagen")
                return shape

            # Versuche Solid zu erstellen
            shape_type = sewed.ShapeType()

            if shape_type == TopAbs_FACE:
                return shape  # Nur ein Face, Original behalten

            from OCP.TopAbs import TopAbs_SHELL, TopAbs_SOLID, TopAbs_COMPOUND

            if shape_type == TopAbs_SHELL:
                shell = TopoDS.Shell_s(sewed)
                solid_builder = BRepBuilderAPI_MakeSolid(shell)
                if solid_builder.IsDone():
                    return solid_builder.Solid()
                return sewed

            if shape_type == TopAbs_COMPOUND:
                return sewed

            return sewed

        except Exception as e:
            logger.warning(f"  Zylinder-Ersetzung fehlgeschlagen: {e}")
            return shape

    def _create_cylinder_face(
        self,
        face_indices: List[int],
        cyl_fit: CylinderFit,
        face_infos: List[FaceInfo]
    ) -> Optional['TopoDS_Face']:
        """
        Erstellt eine Zylinderfläche aus den gefitteten Parametern.
        """
        try:
            # Parameter
            center = cyl_fit.center
            axis = cyl_fit.axis
            radius = cyl_fit.radius

            logger.debug(f"    Erstelle Zylinder: center={center}, axis={axis}, R={radius:.2f}")

            # Sammle alle Boundary-Punkte
            boundary_points = []
            for idx in face_indices:
                face = face_infos[idx].face
                exp = TopExp_Explorer(face, TopAbs_VERTEX)
                while exp.More():
                    vertex = TopoDS.Vertex_s(exp.Current())
                    pnt = BRep_Tool.Pnt_s(vertex)
                    boundary_points.append([pnt.X(), pnt.Y(), pnt.Z()])
                    exp.Next()

            if len(boundary_points) < 3:
                logger.debug(f"    Zu wenige Boundary-Punkte: {len(boundary_points)}")
                return None

            boundary_points = np.array(boundary_points)
            # Dedupliziere Punkte
            boundary_points = np.unique(np.round(boundary_points, decimals=5), axis=0)

            logger.debug(f"    {len(boundary_points)} eindeutige Boundary-Punkte")

            # Berechne V Bounds (Projektion auf Achse)
            to_center = boundary_points - center
            proj = np.dot(to_center, axis)
            v_min_rel, v_max_rel = proj.min(), proj.max()

            # Die Basis des Zylinders sollte am unteren Ende liegen
            # center ist der Schwerpunkt, also müssen wir die Basis berechnen
            base_point = center + axis * v_min_rel

            logger.debug(f"    V-Range relativ: {v_min_rel:.2f} bis {v_max_rel:.2f}")

            # Finde lokale X/Y Achsen senkrecht zur Zylinderachse
            z_axis = axis
            if abs(z_axis[2]) < 0.9:
                x_axis = np.cross(z_axis, [0, 0, 1])
            else:
                x_axis = np.cross(z_axis, [1, 0, 0])
            x_axis = x_axis / np.linalg.norm(x_axis)
            y_axis = np.cross(z_axis, x_axis)

            # Berechne Winkel für jeden Punkt
            radial = to_center - np.outer(proj, axis)
            x_comp = np.dot(radial, x_axis)
            y_comp = np.dot(radial, y_axis)
            angles = np.arctan2(y_comp, x_comp)

            # Sortiere Winkel und finde den tatsächlichen Bereich
            sorted_angles = np.sort(angles)

            # Finde die größte Lücke in den Winkeln
            angle_diffs = np.diff(sorted_angles)
            # Berücksichtige auch die Lücke zwischen letztem und erstem Winkel
            wrap_diff = (2 * np.pi) - (sorted_angles[-1] - sorted_angles[0])
            max_gap = max(wrap_diff, np.max(angle_diffs) if len(angle_diffs) > 0 else 0)

            # Wenn die größte Lücke klein ist (< 30°), ist es ein fast vollständiger Zylinder
            if max_gap < np.radians(30):
                # Vollständiger Zylinder: 0 bis 2*pi
                u_min = 0.0
                u_max = 2 * np.pi
                logger.debug(f"    Vollständiger Zylinder (Lücke={np.degrees(max_gap):.1f}°)")
            elif wrap_diff > np.max(angle_diffs) if len(angle_diffs) > 0 else True:
                # Größte Lücke ist am Wrap-Around -> normaler Bereich
                u_min = sorted_angles[0]
                u_max = sorted_angles[-1]
            else:
                # Größte Lücke ist irgendwo in der Mitte -> Winkel umspannt 0
                gap_idx = np.argmax(angle_diffs)
                u_min = sorted_angles[gap_idx + 1]
                u_max = sorted_angles[gap_idx] + 2 * np.pi

            logger.debug(f"    U-Range: {np.degrees(u_min):.1f}° bis {np.degrees(u_max):.1f}°")

            # Erstelle OCP Zylinder mit Basis am unteren Ende
            gp_base = gp_Pnt(float(base_point[0]), float(base_point[1]), float(base_point[2]))
            gp_axis = gp_Dir(float(axis[0]), float(axis[1]), float(axis[2]))
            gp_xdir = gp_Dir(float(x_axis[0]), float(x_axis[1]), float(x_axis[2]))

            # Ax3 mit definierter X-Richtung für konsistente U-Parameter
            ax3 = gp_Ax3(gp_base, gp_axis, gp_xdir)
            cylinder_surface = Geom_CylindricalSurface(ax3, float(radius))

            # V-Parameter sind jetzt relativ zur Basis (0 bis height)
            v_min = 0.0
            v_max = v_max_rel - v_min_rel  # = Höhe

            # Erweitere Bounds leicht für bessere Überlappung
            v_margin = v_max * 0.01
            u_margin = 0.05  # ~3°

            logger.debug(f"    MakeFace: U=[{u_min:.3f}, {u_max:.3f}], V=[{v_min:.3f}, {v_max:.3f}]")

            face_builder = BRepBuilderAPI_MakeFace(
                cylinder_surface,
                float(u_min - u_margin), float(u_max + u_margin),
                float(v_min - v_margin), float(v_max + v_margin),
                1e-6
            )

            if face_builder.IsDone():
                logger.debug(f"    Zylinder-Face erfolgreich erstellt")
                return face_builder.Face()
            else:
                error = face_builder.Error()
                logger.debug(f"    MakeFace fehlgeschlagen, Error-Code: {error}")
                return None

        except Exception as e:
            logger.warning(f"    Zylinder-Face Erstellung fehlgeschlagen: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None

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
