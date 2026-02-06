"""
MashCad - BREP Face Analyzer
============================

Analysiert BREP-Faces nach Surface-Typ und erkennt Features wie:
- Durchgangs- und Sackloecher
- Aussenzylinder (Bolzen, Wellen)
- Taschen
- Fillets und Chamfers
- Kugeln/Sphaeren
- Konen/Senklocher
- Gewinde

Verwendet OCP/OpenCASCADE fuer praezise Surface-Analyse.

Author: Claude (BREP Cleanup Feature)
Date: 2026-01
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Tuple, Optional, Set, Any
import numpy as np
from loguru import logger

# OCP imports
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import (
    GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Sphere,
    GeomAbs_Cone, GeomAbs_Torus, GeomAbs_BSplineSurface,
    GeomAbs_BezierSurface, GeomAbs_SurfaceOfRevolution,
    GeomAbs_SurfaceOfExtrusion, GeomAbs_OtherSurface
)
from OCP.TopAbs import TopAbs_FORWARD, TopAbs_REVERSED, TopAbs_FACE, TopAbs_EDGE
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopTools import (
    TopTools_IndexedDataMapOfShapeListOfShape,
    TopTools_IndexedMapOfShape
)
from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Shape, TopoDS_Edge
from OCP.BRep import BRep_Tool
from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax1

from modeling.result_types import OperationResult, ResultStatus


# =============================================================================
# Enums
# =============================================================================

class SurfaceType(Enum):
    """OCP Surface-Typen."""
    PLANE = auto()
    CYLINDER = auto()
    SPHERE = auto()
    CONE = auto()
    TORUS = auto()
    BSPLINE = auto()
    BEZIER = auto()
    REVOLUTION = auto()
    EXTRUSION = auto()
    OTHER = auto()


class CylinderClass(Enum):
    """Unterscheidung Innen- vs Aussenzylinder."""
    HOLE = auto()      # Konkav (Loch)
    BOSS = auto()      # Konvex (Bolzen/Welle)
    PARTIAL = auto()   # Teilzylinder (< 360 Grad)


class FeatureType(Enum):
    """Erkannte Feature-Typen."""
    HOLE_THROUGH = auto()
    HOLE_BLIND = auto()
    COUNTERSINK = auto()
    THREAD = auto()
    BOSS_CYLINDER = auto()
    POCKET = auto()
    FILLET = auto()
    CHAMFER = auto()
    SPHERE_CONCAVE = auto()
    SPHERE_CONVEX = auto()
    CONE = auto()
    UNKNOWN = auto()


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class AnalyzedFace:
    """Analysierte Face mit allen geometrischen Informationen."""
    idx: int
    wrapped: TopoDS_Face
    surface_type: SurfaceType
    orientation: int  # TopAbs_FORWARD oder TopAbs_REVERSED

    # Gemeinsame Attribute
    area: float = 0.0
    center: np.ndarray = field(default_factory=lambda: np.zeros(3))

    # Plane-spezifisch
    normal: Optional[np.ndarray] = None

    # Cylinder-spezifisch
    axis: Optional[np.ndarray] = None
    axis_origin: Optional[np.ndarray] = None
    radius: Optional[float] = None
    cylinder_class: Optional[CylinderClass] = None

    # Sphere-spezifisch (verwendet center und radius)

    # Cone-spezifisch (verwendet axis, axis_origin)
    half_angle: Optional[float] = None  # Halber Oeffnungswinkel in Radians

    # Fuer BSpline-Erkennung
    detected_as: Optional[str] = None  # z.B. "BSpline->Cylinder"

    @property
    def is_concave(self) -> bool:
        """True wenn Face nach innen zeigt (Loch, Vertiefung)."""
        return self.orientation == TopAbs_REVERSED


@dataclass
class DetectedFeature:
    """Erkanntes geometrisches Feature."""
    feature_type: FeatureType
    face_indices: List[int]
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    suggested_action: str = ""

    @property
    def display_name(self) -> str:
        """Anzeigename fuer UI."""
        names = {
            FeatureType.HOLE_THROUGH: "Durchgangsloch",
            FeatureType.HOLE_BLIND: "Sackloch",
            FeatureType.COUNTERSINK: "Senkloch",
            FeatureType.THREAD: "Gewinde",
            FeatureType.BOSS_CYLINDER: "Aussenzylinder",
            FeatureType.POCKET: "Tasche",
            FeatureType.FILLET: "Fillet",
            FeatureType.CHAMFER: "Chamfer",
            FeatureType.SPHERE_CONCAVE: "Kugelpfanne",
            FeatureType.SPHERE_CONVEX: "Kugelkopf",
            FeatureType.CONE: "Konus",
            FeatureType.UNKNOWN: "Unbekannt",
        }
        return names.get(self.feature_type, "Unbekannt")

    @property
    def icon(self) -> str:
        """Icon-Symbol fuer UI."""
        icons = {
            FeatureType.HOLE_THROUGH: "○",
            FeatureType.HOLE_BLIND: "◔",
            FeatureType.COUNTERSINK: "◇",
            FeatureType.THREAD: "⚙",
            FeatureType.BOSS_CYLINDER: "●",
            FeatureType.POCKET: "□",
            FeatureType.FILLET: "◠",
            FeatureType.CHAMFER: "∠",
            FeatureType.SPHERE_CONCAVE: "◐",
            FeatureType.SPHERE_CONVEX: "◑",
            FeatureType.CONE: "◇",
            FeatureType.UNKNOWN: "?",
        }
        return icons.get(self.feature_type, "?")

    @property
    def color_hex(self) -> str:
        """Farbe fuer Viewport-Highlighting."""
        colors = {
            FeatureType.HOLE_THROUGH: "#4169E1",     # Blau
            FeatureType.HOLE_BLIND: "#87CEEB",       # Hellblau
            FeatureType.COUNTERSINK: "#9370DB",      # Lila
            FeatureType.THREAD: "#DC143C",           # Rot
            FeatureType.BOSS_CYLINDER: "#32CD32",    # Gruen
            FeatureType.POCKET: "#FFD700",           # Gelb
            FeatureType.FILLET: "#FF69B4",           # Pink
            FeatureType.CHAMFER: "#FFA500",          # Orange
            FeatureType.SPHERE_CONCAVE: "#40E0D0",   # Tuerkis
            FeatureType.SPHERE_CONVEX: "#98FB98",    # Hellgruen
            FeatureType.CONE: "#9370DB",             # Lila
            FeatureType.UNKNOWN: "#808080",          # Grau
        }
        return colors.get(self.feature_type, "#808080")


@dataclass
class AnalysisResult:
    """Gesamtergebnis der BREP-Analyse."""
    faces: List[AnalyzedFace]
    adjacency: Dict[int, List[int]]
    features: List[DetectedFeature]
    face_to_feature: Dict[int, int]  # Face-Index -> Feature-Index


# =============================================================================
# Main Analyzer Class
# =============================================================================

class BRepFaceAnalyzer:
    """
    Analysiert alle Faces eines BREP-Solids.

    Usage:
        analyzer = BRepFaceAnalyzer()
        result = analyzer.analyze(solid)

        for feature in result.features:
            # logger.info(f"{feature.icon} {feature.display_name}: {feature.parameters}")  # Beispiel-Usage in Docstring"
    """

    # Toleranzen
    ANGLE_TOLERANCE = 0.1  # ~6 Grad
    COPLANAR_TOLERANCE = 0.01  # mm
    COAXIAL_TOLERANCE = 0.01  # mm
    MAX_FILLET_RADIUS = 10.0  # mm
    MAX_CHAMFER_WIDTH = 5.0  # mm

    def __init__(self):
        self._faces: List[AnalyzedFace] = []
        self._adjacency: Dict[int, List[int]] = {}
        self._features: List[DetectedFeature] = []

    def analyze(self, solid) -> AnalysisResult:
        """
        Analysiert ein Solid und erkennt alle Features.

        Args:
            solid: Build123d Solid oder TopoDS_Shape

        Returns:
            AnalysisResult mit analysierten Faces und erkannten Features
        """
        self._faces = []
        self._adjacency = {}
        self._features = []

        # Shape extrahieren
        shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

        logger.info("BREP Face Analyzer: Starte Analyse...")

        # 1. Alle Faces analysieren
        self._analyze_all_faces(shape)
        logger.info(f"  {len(self._faces)} Faces analysiert")

        # 2. Adjazenz-Graph bauen
        self._build_adjacency(shape)
        logger.info(f"  Adjazenz-Graph erstellt")

        # Debug: Surface-Typ Statistik
        type_counts = {}
        detected_counts = {}
        for face in self._faces:
            t = face.surface_type.name
            type_counts[t] = type_counts.get(t, 0) + 1
            if face.detected_as:
                detected_counts[face.detected_as] = detected_counts.get(face.detected_as, 0) + 1
        logger.info(f"  Surface-Typen: {type_counts}")
        if detected_counts:
            logger.info(f"  BSpline-Erkennung: {detected_counts}")

        # 3. Features erkennen
        self._detect_all_features()
        logger.info(f"  {len(self._features)} Features erkannt")

        # Face-to-Feature Mapping erstellen
        face_to_feature = {}
        for feat_idx, feat in enumerate(self._features):
            for face_idx in feat.face_indices:
                face_to_feature[face_idx] = feat_idx

        return AnalysisResult(
            faces=self._faces,
            adjacency=self._adjacency,
            features=self._features,
            face_to_feature=face_to_feature
        )

    # =========================================================================
    # Face Analysis
    # =========================================================================

    def _analyze_all_faces(self, shape: TopoDS_Shape):
        """Analysiert alle Faces des Shapes."""
        face_map = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, TopAbs_FACE, face_map)

        for i in range(1, face_map.Extent() + 1):
            face = TopoDS.Face_s(face_map.FindKey(i))
            analyzed = self._analyze_single_face(face, i - 1)
            self._faces.append(analyzed)

    def _analyze_single_face(self, face: TopoDS_Face, idx: int) -> AnalyzedFace:
        """Analysiert eine einzelne Face."""
        adaptor = BRepAdaptor_Surface(face)
        surface_type = self._map_surface_type(adaptor.GetType())
        orientation = face.Orientation()

        # Basis-Info
        analyzed = AnalyzedFace(
            idx=idx,
            wrapped=face,
            surface_type=surface_type,
            orientation=orientation
        )

        # Typ-spezifische Analyse
        if surface_type == SurfaceType.PLANE:
            self._analyze_plane(adaptor, analyzed)
        elif surface_type == SurfaceType.CYLINDER:
            self._analyze_cylinder(adaptor, analyzed)
        elif surface_type == SurfaceType.SPHERE:
            self._analyze_sphere(adaptor, analyzed)
        elif surface_type == SurfaceType.CONE:
            self._analyze_cone(adaptor, analyzed)
        elif surface_type == SurfaceType.TORUS:
            self._analyze_torus(adaptor, analyzed)
        elif surface_type in (SurfaceType.BSPLINE, SurfaceType.OTHER):
            # BSpline/Other: Kruemmungsanalyse um analytischen Typ zu erkennen
            self._analyze_bspline_by_curvature(adaptor, face, analyzed)

        # Flaeche und Center of Mass berechnen (fuer alle Typen)
        try:
            from OCP.BRepGProp import BRepGProp
            from OCP.GProp import GProp_GProps
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, props)
            analyzed.area = props.Mass()

            # Center of Mass als Fallback falls kein Center gesetzt
            if analyzed.center is None:
                com = props.CentreOfMass()
                analyzed.center = np.array([com.X(), com.Y(), com.Z()])
        except Exception as e:
            logger.debug(f"[brep_face_analyzer.py] Fehler: {e}")
            pass

        # Normale am Mittelpunkt berechnen falls nicht gesetzt
        if analyzed.normal is None:
            try:
                u_min, u_max, v_min, v_max = BRep_Tool.Surface_s(face).Bounds(0, 1, 0, 1)
                # Bounds korrekt holen
                from OCP.BRepTools import BRepTools
                u_min, u_max, v_min, v_max = BRepTools.UVBounds_s(face)
                u_mid = (u_min + u_max) / 2
                v_mid = (v_min + v_max) / 2

                pnt = gp_Pnt()
                vec = gp_Vec()
                adaptor.D1(u_mid, v_mid, pnt, gp_Vec(), vec)
                # Normale aus D1 Ableitungen
                d1u = gp_Vec()
                d1v = gp_Vec()
                adaptor.D1(u_mid, v_mid, pnt, d1u, d1v)
                normal_vec = d1u.Crossed(d1v)
                if normal_vec.Magnitude() > 1e-10:
                    normal_vec.Normalize()
                    analyzed.normal = np.array([normal_vec.X(), normal_vec.Y(), normal_vec.Z()])
                    if analyzed.orientation == TopAbs_REVERSED:
                        analyzed.normal = -analyzed.normal
            except Exception as e:
                logger.debug(f"[brep_face_analyzer.py] Fehler: {e}")
                pass

        return analyzed

    def _map_surface_type(self, geom_type) -> SurfaceType:
        """Mappt OCP GeomAbs-Typ auf unser Enum."""
        mapping = {
            GeomAbs_Plane: SurfaceType.PLANE,
            GeomAbs_Cylinder: SurfaceType.CYLINDER,
            GeomAbs_Sphere: SurfaceType.SPHERE,
            GeomAbs_Cone: SurfaceType.CONE,
            GeomAbs_Torus: SurfaceType.TORUS,
            GeomAbs_BSplineSurface: SurfaceType.BSPLINE,
            GeomAbs_BezierSurface: SurfaceType.BEZIER,
            GeomAbs_SurfaceOfRevolution: SurfaceType.REVOLUTION,
            GeomAbs_SurfaceOfExtrusion: SurfaceType.EXTRUSION,
        }
        return mapping.get(geom_type, SurfaceType.OTHER)

    def _analyze_plane(self, adaptor: BRepAdaptor_Surface, analyzed: AnalyzedFace):
        """Analysiert eine planare Face."""
        plane = adaptor.Plane()
        loc = plane.Location()
        normal = plane.Axis().Direction()

        analyzed.center = np.array([loc.X(), loc.Y(), loc.Z()])
        analyzed.normal = np.array([normal.X(), normal.Y(), normal.Z()])

        # Bei REVERSED ist Normale invertiert
        if analyzed.orientation == TopAbs_REVERSED:
            analyzed.normal = -analyzed.normal

    def _analyze_cylinder(self, adaptor: BRepAdaptor_Surface, analyzed: AnalyzedFace):
        """Analysiert eine zylindrische Face."""
        cyl = adaptor.Cylinder()
        axis = cyl.Axis()
        loc = axis.Location()
        direction = axis.Direction()

        analyzed.axis_origin = np.array([loc.X(), loc.Y(), loc.Z()])
        analyzed.axis = np.array([direction.X(), direction.Y(), direction.Z()])
        analyzed.radius = cyl.Radius()
        analyzed.center = analyzed.axis_origin.copy()

        # Klassifizierung: Loch vs Bolzen
        # Bei REVERSED zeigt Normale nach aussen -> Loch
        # Bei FORWARD zeigt Normale nach innen -> Bolzen
        if analyzed.orientation == TopAbs_REVERSED:
            analyzed.cylinder_class = CylinderClass.HOLE
        else:
            analyzed.cylinder_class = CylinderClass.BOSS

    def _analyze_sphere(self, adaptor: BRepAdaptor_Surface, analyzed: AnalyzedFace):
        """Analysiert eine sphaerische Face."""
        sphere = adaptor.Sphere()
        loc = sphere.Location()

        analyzed.center = np.array([loc.X(), loc.Y(), loc.Z()])
        analyzed.radius = sphere.Radius()

    def _analyze_cone(self, adaptor: BRepAdaptor_Surface, analyzed: AnalyzedFace):
        """Analysiert eine konische Face."""
        cone = adaptor.Cone()
        axis = cone.Axis()
        loc = axis.Location()
        direction = axis.Direction()

        analyzed.axis_origin = np.array([loc.X(), loc.Y(), loc.Z()])
        analyzed.axis = np.array([direction.X(), direction.Y(), direction.Z()])
        analyzed.half_angle = cone.SemiAngle()
        analyzed.center = analyzed.axis_origin.copy()

    def _analyze_torus(self, adaptor: BRepAdaptor_Surface, analyzed: AnalyzedFace):
        """Analysiert eine Torus-Face (oft bei variablen Fillets)."""
        torus = adaptor.Torus()
        axis = torus.Axis()
        loc = axis.Location()
        direction = axis.Direction()

        analyzed.axis_origin = np.array([loc.X(), loc.Y(), loc.Z()])
        analyzed.axis = np.array([direction.X(), direction.Y(), direction.Z()])
        analyzed.radius = torus.MinorRadius()  # Fillet-Radius
        analyzed.center = analyzed.axis_origin.copy()

    def _analyze_bspline_by_curvature(self, adaptor: BRepAdaptor_Surface,
                                       face: TopoDS_Face, analyzed: AnalyzedFace):
        """
        Analysiert BSpline-Flaechen mittels Kruemmung.

        Versucht analytische Surface-Typen zu erkennen:
        - Konstante Kruemmung 0 -> PLANE
        - Konstante Kruemmung != 0 in einer Richtung -> CYLINDER
        - Konstante Kruemmung in beide Richtungen -> SPHERE
        """
        try:
            from OCP.BRepLProp import BRepLProp_SLProps
            from OCP.BRepTools import BRepTools

            # UV-Bounds holen
            u_min, u_max, v_min, v_max = BRepTools.UVBounds_s(face)

            # Sample-Punkte fuer Kruemmungsanalyse
            n_samples = 5
            curvatures = []
            points = []

            for i in range(n_samples):
                for j in range(n_samples):
                    u = u_min + (u_max - u_min) * (i + 0.5) / n_samples
                    v = v_min + (v_max - v_min) * (j + 0.5) / n_samples

                    props = BRepLProp_SLProps(adaptor, u, v, 2, 1e-6)

                    if props.IsCurvatureDefined():
                        k1 = props.MaxCurvature()
                        k2 = props.MinCurvature()
                        curvatures.append((k1, k2))

                        pnt = props.Value()
                        points.append(np.array([pnt.X(), pnt.Y(), pnt.Z()]))

            if len(curvatures) < 4:
                return  # Nicht genug Samples

            curvatures = np.array(curvatures)
            points = np.array(points)

            # Mittlere Kruemmungen
            k1_mean = np.mean(curvatures[:, 0])
            k2_mean = np.mean(curvatures[:, 1])
            k1_std = np.std(curvatures[:, 0])
            k2_std = np.std(curvatures[:, 1])

            # Toleranz fuer "konstant"
            tol = 0.01

            # Klassifizierung
            is_k1_const = k1_std < max(tol, abs(k1_mean) * 0.1)
            is_k2_const = k2_std < max(tol, abs(k2_mean) * 0.1)
            is_k1_zero = abs(k1_mean) < tol
            is_k2_zero = abs(k2_mean) < tol

            if is_k1_const and is_k2_const:
                if is_k1_zero and is_k2_zero:
                    # Ebene erkannt
                    analyzed.surface_type = SurfaceType.PLANE
                    analyzed.detected_as = "BSpline->Plane"
                    # Normale aus Kruemmungsanalyse (bereits berechnet)
                    logger.debug(f"Face {analyzed.idx}: BSpline als PLANE erkannt")

                elif is_k1_zero or is_k2_zero:
                    # Zylinder erkannt (eine Kruemmung 0, andere konstant)
                    analyzed.surface_type = SurfaceType.CYLINDER
                    analyzed.detected_as = "BSpline->Cylinder"

                    # Radius aus Kruemmung
                    k_nonzero = k1_mean if abs(k1_mean) > abs(k2_mean) else k2_mean
                    if abs(k_nonzero) > 1e-10:
                        analyzed.radius = abs(1.0 / k_nonzero)

                    # Achse aus Punkten fitten (PCA)
                    if len(points) >= 3:
                        center = np.mean(points, axis=0)
                        analyzed.center = center

                        # Einfache Achsen-Schaetzung via Kovarianz
                        centered = points - center
                        cov = np.cov(centered.T)
                        eigenvalues, eigenvectors = np.linalg.eigh(cov)
                        # Achse = Richtung mit kleinster Varianz (bei Zylinder)
                        analyzed.axis = eigenvectors[:, 0]

                    # Loch vs Boss ueber Orientation
                    if analyzed.orientation == TopAbs_REVERSED:
                        analyzed.cylinder_class = CylinderClass.HOLE
                    else:
                        analyzed.cylinder_class = CylinderClass.BOSS

                    logger.debug(f"Face {analyzed.idx}: BSpline als CYLINDER erkannt (R={analyzed.radius:.2f})")

                elif abs(k1_mean - k2_mean) < tol:
                    # Kugel erkannt (beide Kruemmungen gleich und nicht 0)
                    analyzed.surface_type = SurfaceType.SPHERE
                    analyzed.detected_as = "BSpline->Sphere"
                    if abs(k1_mean) > 1e-10:
                        analyzed.radius = abs(1.0 / k1_mean)
                    analyzed.center = np.mean(points, axis=0)
                    logger.debug(f"Face {analyzed.idx}: BSpline als SPHERE erkannt (R={analyzed.radius:.2f})")

        except Exception as e:
            logger.debug(f"BSpline-Kruemmungsanalyse fehlgeschlagen: {e}")

    # =========================================================================
    # Adjacency Graph
    # =========================================================================

    def _build_adjacency(self, shape: TopoDS_Shape):
        """Baut Adjazenz-Graph ueber gemeinsame Kanten."""
        # Face-Map erstellen
        face_map = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, TopAbs_FACE, face_map)

        # Edge -> Faces Mapping
        edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map)

        # Adjazenz initialisieren
        for i in range(len(self._faces)):
            self._adjacency[i] = []

        # Durch alle Edges iterieren
        for edge_idx in range(1, edge_face_map.Extent() + 1):
            edge = edge_face_map.FindKey(edge_idx)
            face_list = edge_face_map.FindFromIndex(edge_idx)

            # Faces die diese Edge teilen sammeln
            connected_faces = []
            # OCP Listen sind direkt iterierbar in Python
            for shape in face_list:
                face = TopoDS.Face_s(shape)
                face_idx = face_map.FindIndex(face) - 1
                if 0 <= face_idx < len(self._faces):
                    connected_faces.append(face_idx)

            # Bidirektionale Adjazenz eintragen
            for i, f1 in enumerate(connected_faces):
                for f2 in connected_faces[i+1:]:
                    if f2 not in self._adjacency[f1]:
                        self._adjacency[f1].append(f2)
                    if f1 not in self._adjacency[f2]:
                        self._adjacency[f2].append(f1)

    # =========================================================================
    # Feature Detection
    # =========================================================================

    def _detect_all_features(self):
        """Erkennt alle Features im Solid."""
        processed = set()

        # Reihenfolge wichtig: Spezifischere Features zuerst

        # 1. Fillets (kleine Zylinder)
        for face in self._faces:
            if face.idx in processed:
                continue
            if face.surface_type == SurfaceType.CYLINDER:
                feature = self._detect_fillet(face)
                if feature:
                    self._features.append(feature)
                    processed.update(feature.face_indices)

        # 2. Chamfers (schmale Planes zwischen 2 Planes)
        for face in self._faces:
            if face.idx in processed:
                continue
            if face.surface_type == SurfaceType.PLANE:
                feature = self._detect_chamfer(face)
                if feature:
                    self._features.append(feature)
                    processed.update(feature.face_indices)

        # 3. Loecher und Aussenzylinder
        for face in self._faces:
            if face.idx in processed:
                continue
            if face.surface_type == SurfaceType.CYLINDER:
                feature = self._detect_cylinder_feature(face)
                if feature:
                    self._features.append(feature)
                    processed.update(feature.face_indices)

        # 4. Konen/Senklocher
        for face in self._faces:
            if face.idx in processed:
                continue
            if face.surface_type == SurfaceType.CONE:
                feature = self._detect_cone_feature(face)
                if feature:
                    self._features.append(feature)
                    processed.update(feature.face_indices)

        # 5. Kugeln
        for face in self._faces:
            if face.idx in processed:
                continue
            if face.surface_type == SurfaceType.SPHERE:
                feature = self._detect_sphere_feature(face)
                if feature:
                    self._features.append(feature)
                    processed.update(feature.face_indices)

        # 6. Taschen (Planes mit senkrechten Waenden)
        for face in self._faces:
            if face.idx in processed:
                continue
            if face.surface_type == SurfaceType.PLANE:
                feature = self._detect_pocket(face)
                if feature:
                    self._features.append(feature)
                    processed.update(feature.face_indices)

        # 7. Planar-Cluster-Analyse fuer tessellierte Zylinder
        # Wenn alle Faces PLANE sind, versuche zylindrische Muster zu finden
        all_planes = all(f.surface_type == SurfaceType.PLANE for f in self._faces)
        if all_planes and len(self._faces) > 10:
            logger.info("  Alle Faces sind PLANE - starte Planar-Cluster-Analyse...")
            cluster_features = self._detect_planar_cylinder_clusters(processed)
            for feature in cluster_features:
                self._features.append(feature)
                processed.update(feature.face_indices)
            logger.info(f"  {len(cluster_features)} zylindrische Cluster erkannt")

        # 8. Gewinde/Helix (BSplines mit helikalem Verlauf)
        helix_features = self._detect_helix_features(processed)
        for feature in helix_features:
            self._features.append(feature)
            processed.update(feature.face_indices)
        if helix_features:
            logger.info(f"  {len(helix_features)} Helix/Thread-Features erkannt")

    def _detect_helix_features(self, processed: set) -> List[DetectedFeature]:
        """
        Erkennt Gewinde/Helix-Features anhand von BSpline/Bezier-Flächen.

        Tier 3 OCP Feature Audit: Helix-Erkennung via Edge-Sampling.
        Prüft ob Edges auf BSpline-Flächen einen helikalischen Verlauf haben
        (konstanter Radius zur Achse + monotone Z-Komponente).

        Returns:
            Liste erkannter THREAD-Features
        """
        import math
        from OCP.BRepAdaptor import BRepAdaptor_Curve

        features = []

        for face in self._faces:
            if face.idx in processed:
                continue
            if face.surface_type not in (SurfaceType.BSPLINE, SurfaceType.BEZIER):
                continue

            # Edges der Face extrahieren
            explorer = TopExp_Explorer(face.wrapped, TopAbs_EDGE)
            found_helix = False

            while explorer.More() and not found_helix:
                edge = explorer.Current()
                try:
                    curve = BRepAdaptor_Curve(edge)
                    n_samples = 20
                    first = curve.FirstParameter()
                    last = curve.LastParameter()
                    if abs(last - first) < 1e-10:
                        explorer.Next()
                        continue

                    step = (last - first) / (n_samples - 1)
                    points = [curve.Value(first + i * step) for i in range(n_samples)]

                    # Berechne Radius zur Z-Achse und Z-Werte
                    radii = [math.sqrt(p.X()**2 + p.Y()**2) for p in points]
                    z_values = [p.Z() for p in points]

                    mean_radius = np.mean(radii)
                    if mean_radius < 1e-6:
                        explorer.Next()
                        continue

                    radius_std = np.std(radii)

                    # Prüfe: Radius ~ konstant UND Z monoton steigend/fallend
                    z_diffs = [z_values[i+1] - z_values[i] for i in range(len(z_values)-1)]
                    z_monotonic = all(d >= -1e-6 for d in z_diffs) or all(d <= 1e-6 for d in z_diffs)
                    z_range = abs(z_values[-1] - z_values[0])

                    # Helix-Kriterien: Radius-Variation < 10%, Z steigt monoton, Z-Range > 0
                    if radius_std < 0.1 * mean_radius and z_monotonic and z_range > 0.1:
                        features.append(DetectedFeature(
                            feature_type=FeatureType.THREAD,
                            face_indices={face.idx},
                            confidence=0.8,
                            parameters={
                                "radius": float(mean_radius),
                                "pitch": float(z_range),
                                "direction": "up" if z_values[-1] > z_values[0] else "down"
                            }
                        ))
                        found_helix = True
                        logger.debug(f"  Helix erkannt: Face {face.idx}, R={mean_radius:.2f}mm, Pitch={z_range:.2f}mm")
                except Exception as e:
                    logger.debug(f"  Helix-Check fehlgeschlagen für Face {face.idx}: {e}")

                explorer.Next()

        return features

    def _detect_fillet(self, face: AnalyzedFace) -> Optional[DetectedFeature]:
        """Erkennt Fillets (kleine Zylinder zwischen 2 tangenten Flaechen)."""
        if face.surface_type != SurfaceType.CYLINDER:
            return None

        if face.radius is None or face.radius > self.MAX_FILLET_RADIUS:
            return None

        # Nachbarn holen
        neighbors = self._adjacency.get(face.idx, [])
        if len(neighbors) < 2:
            return None

        # Pruefen ob Nachbarn tangent sind
        tangent_neighbors = []
        for n_idx in neighbors:
            neighbor = self._faces[n_idx]
            if self._is_tangent_to_cylinder(face, neighbor):
                tangent_neighbors.append(n_idx)

        # Fillet braucht genau 2 tangente Nachbarn
        if len(tangent_neighbors) != 2:
            return None

        # Die Nachbarn sollten verschiedene Flaechen sein
        n1 = self._faces[tangent_neighbors[0]]
        n2 = self._faces[tangent_neighbors[1]]

        # Wenn beide Nachbarn der gleiche Zylinder sind -> kein Fillet
        if n1.surface_type == SurfaceType.CYLINDER and n2.surface_type == SurfaceType.CYLINDER:
            if self._same_cylinder(n1, n2):
                return None

        return DetectedFeature(
            feature_type=FeatureType.FILLET,
            face_indices=[face.idx],
            parameters={
                "radius": face.radius,
                "area": face.area
            },
            confidence=0.9,
            suggested_action="Zu analytischem Zylinder mergen"
        )

    def _detect_chamfer(self, face: AnalyzedFace) -> Optional[DetectedFeature]:
        """Erkennt Chamfers (45-Grad Flaechen zwischen 2 Planes)."""
        if face.surface_type != SurfaceType.PLANE:
            return None

        neighbors = self._adjacency.get(face.idx, [])

        # Nur Plane-Nachbarn betrachten
        plane_neighbors = [
            n_idx for n_idx in neighbors
            if self._faces[n_idx].surface_type == SurfaceType.PLANE
        ]

        if len(plane_neighbors) != 2:
            return None

        n1 = self._faces[plane_neighbors[0]]
        n2 = self._faces[plane_neighbors[1]]

        # Winkel zu Nachbarn pruefen
        angle1 = self._angle_between_normals(face.normal, n1.normal)
        angle2 = self._angle_between_normals(face.normal, n2.normal)

        # Typische Fase: 45 Grad (+/- 10 Grad) zu beiden Nachbarn
        is_45_deg = (35 < angle1 < 55) and (35 < angle2 < 55)

        if not is_45_deg:
            return None

        # Nachbarn sollten ~90 Grad zueinander sein
        neighbor_angle = self._angle_between_normals(n1.normal, n2.normal)
        if not (80 < neighbor_angle < 100):
            return None

        return DetectedFeature(
            feature_type=FeatureType.CHAMFER,
            face_indices=[face.idx],
            parameters={
                "angle1": angle1,
                "angle2": angle2,
                "area": face.area
            },
            confidence=0.9,
            suggested_action="Zu analytischer Fase mergen"
        )

    def _detect_cylinder_feature(self, face: AnalyzedFace) -> Optional[DetectedFeature]:
        """Erkennt Zylinder-Features (Loecher, Bolzen)."""
        if face.surface_type != SurfaceType.CYLINDER:
            return None

        # Alle zusammenhaengenden Zylinder-Faces mit gleicher Geometrie finden
        related = self._find_related_cylinder_faces(face)

        if face.cylinder_class == CylinderClass.HOLE:
            # Loch-Erkennung: Durchgang vs Sackloch
            has_bottom = self._has_bottom_plane(related)

            if has_bottom:
                feature_type = FeatureType.HOLE_BLIND
            else:
                feature_type = FeatureType.HOLE_THROUGH

            return DetectedFeature(
                feature_type=feature_type,
                face_indices=related,
                parameters={
                    "diameter": face.radius * 2,
                    "radius": face.radius,
                },
                confidence=0.9,
                suggested_action="Zu analytischem Zylinder mergen"
            )

        else:
            # Aussenzylinder (Bolzen/Welle)
            return DetectedFeature(
                feature_type=FeatureType.BOSS_CYLINDER,
                face_indices=related,
                parameters={
                    "diameter": face.radius * 2,
                    "radius": face.radius,
                },
                confidence=0.9,
                suggested_action="Zu analytischem Zylinder mergen"
            )

    def _detect_cone_feature(self, face: AnalyzedFace) -> Optional[DetectedFeature]:
        """Erkennt Konen/Senklocher."""
        if face.surface_type != SurfaceType.CONE:
            return None

        neighbors = self._adjacency.get(face.idx, [])

        # Pruefe ob benachbart zu Zylinder (typisches Senkloch)
        has_cylinder_neighbor = any(
            self._faces[n].surface_type == SurfaceType.CYLINDER
            for n in neighbors
        )

        apex_angle = np.degrees(face.half_angle * 2) if face.half_angle else 0

        # Senkloch: 90 oder 120 Grad Spitzenwinkel + benachbarter Zylinder
        is_countersink = has_cylinder_neighbor and (85 < apex_angle < 125)

        if is_countersink:
            feature_type = FeatureType.COUNTERSINK
        else:
            feature_type = FeatureType.CONE

        return DetectedFeature(
            feature_type=feature_type,
            face_indices=[face.idx],
            parameters={
                "apex_angle": apex_angle,
                "half_angle": np.degrees(face.half_angle) if face.half_angle else 0,
            },
            confidence=0.8 if is_countersink else 0.7,
            suggested_action="Zu analytischem Konus mergen"
        )

    def _detect_sphere_feature(self, face: AnalyzedFace) -> Optional[DetectedFeature]:
        """Erkennt Kugeln (Pfanne vs Kopf)."""
        if face.surface_type != SurfaceType.SPHERE:
            return None

        if face.is_concave:
            feature_type = FeatureType.SPHERE_CONCAVE
        else:
            feature_type = FeatureType.SPHERE_CONVEX

        return DetectedFeature(
            feature_type=feature_type,
            face_indices=[face.idx],
            parameters={
                "radius": face.radius,
                "center": face.center.tolist() if face.center is not None else None,
            },
            confidence=0.9,
            suggested_action="Zu analytischer Kugel mergen"
        )

    def _detect_pocket(self, face: AnalyzedFace) -> Optional[DetectedFeature]:
        """Erkennt Taschen (Plane mit senkrechten Waenden)."""
        if face.surface_type != SurfaceType.PLANE:
            return None

        # Face muss konkav sein (nach innen zeigend)
        if not face.is_concave:
            return None

        neighbors = self._adjacency.get(face.idx, [])

        # Finde senkrechte Nachbar-Planes (Waende)
        walls = []
        for n_idx in neighbors:
            neighbor = self._faces[n_idx]
            if neighbor.surface_type == SurfaceType.PLANE:
                if self._is_perpendicular(face.normal, neighbor.normal):
                    walls.append(n_idx)

        # Tasche braucht min. 3 Waende
        if len(walls) < 3:
            return None

        return DetectedFeature(
            feature_type=FeatureType.POCKET,
            face_indices=[face.idx] + walls,
            parameters={
                "bottom_face": face.idx,
                "wall_faces": walls,
                "wall_count": len(walls),
            },
            confidence=0.7,
            suggested_action="Wandflaechen mergen"
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _is_tangent_to_cylinder(self, cyl: AnalyzedFace, neighbor: AnalyzedFace) -> bool:
        """Prueft ob Nachbar tangent zum Zylinder ist."""
        if neighbor.surface_type == SurfaceType.PLANE:
            # Zylinder-Achse sollte parallel zur Ebene sein
            # -> dot(axis, normal) ~ 0
            if cyl.axis is None or neighbor.normal is None:
                return False
            dot = abs(np.dot(cyl.axis, neighbor.normal))
            return dot < self.ANGLE_TOLERANCE
        return False

    def _same_cylinder(self, f1: AnalyzedFace, f2: AnalyzedFace) -> bool:
        """Prueft ob zwei Faces zum selben Zylinder gehoeren."""
        if f1.surface_type != SurfaceType.CYLINDER or f2.surface_type != SurfaceType.CYLINDER:
            return False

        if f1.radius is None or f2.radius is None:
            return False

        # Gleicher Radius
        if abs(f1.radius - f2.radius) > self.COPLANAR_TOLERANCE:
            return False

        # Koaxial (gleiche Achse)
        if f1.axis is None or f2.axis is None:
            return False

        # Achsen parallel
        dot = abs(np.dot(f1.axis, f2.axis))
        if dot < 1 - self.ANGLE_TOLERANCE:
            return False

        # Achsen auf gleicher Linie
        if f1.axis_origin is None or f2.axis_origin is None:
            return False

        diff = f2.axis_origin - f1.axis_origin
        cross = np.cross(diff, f1.axis)
        dist = np.linalg.norm(cross)

        return dist < self.COAXIAL_TOLERANCE

    def _angle_between_normals(self, n1: np.ndarray, n2: np.ndarray) -> float:
        """Berechnet Winkel zwischen zwei Normalen in Grad."""
        if n1 is None or n2 is None:
            return 0
        dot = np.clip(np.dot(n1, n2), -1.0, 1.0)
        return np.degrees(np.arccos(abs(dot)))

    def _is_perpendicular(self, n1: np.ndarray, n2: np.ndarray) -> bool:
        """Prueft ob zwei Normalen senkrecht zueinander stehen."""
        if n1 is None or n2 is None:
            return False
        angle = self._angle_between_normals(n1, n2)
        return 85 < angle < 95

    def _find_related_cylinder_faces(self, start: AnalyzedFace) -> List[int]:
        """Findet alle zusammenhaengenden Zylinder-Faces mit gleicher Geometrie."""
        if start.surface_type != SurfaceType.CYLINDER:
            return [start.idx]

        related = [start.idx]
        queue = [start.idx]
        visited = {start.idx}

        while queue:
            current_idx = queue.pop(0)
            current = self._faces[current_idx]

            for n_idx in self._adjacency.get(current_idx, []):
                if n_idx in visited:
                    continue

                neighbor = self._faces[n_idx]
                if neighbor.surface_type == SurfaceType.CYLINDER:
                    if self._same_cylinder(current, neighbor):
                        related.append(n_idx)
                        queue.append(n_idx)
                        visited.add(n_idx)

        return related

    def _has_bottom_plane(self, cylinder_faces: List[int]) -> bool:
        """Prueft ob Zylinder-Faces eine Bodenflaeche haben (Sackloch)."""
        for cyl_idx in cylinder_faces:
            for n_idx in self._adjacency.get(cyl_idx, []):
                neighbor = self._faces[n_idx]
                if neighbor.surface_type == SurfaceType.PLANE:
                    cyl = self._faces[cyl_idx]
                    if cyl.axis is not None and neighbor.normal is not None:
                        # Boden ist senkrecht zur Zylinderachse
                        dot = abs(np.dot(cyl.axis, neighbor.normal))
                        if dot > 1 - self.ANGLE_TOLERANCE:
                            return True
        return False

    # =========================================================================
    # Public Helper Methods
    # =========================================================================

    def suggest_related_faces(self, face_idx: int) -> List[int]:
        """
        Schlaegt verwandte Faces vor basierend auf Geometrie.

        Fuer UI: Wenn User auf eine Face klickt, werden alle
        zusammengehoerenden Faces highlighted.
        """
        if face_idx < 0 or face_idx >= len(self._faces):
            return []

        face = self._faces[face_idx]

        if face.surface_type == SurfaceType.CYLINDER:
            return self._find_related_cylinder_faces(face)

        elif face.surface_type == SurfaceType.PLANE:
            # Koplanare Planes finden
            return self._find_coplanar_faces(face)

        elif face.surface_type == SurfaceType.SPHERE:
            # Bei Kugeln: nur diese Face (normalerweise eine)
            return [face_idx]

        return [face_idx]

    def _find_coplanar_faces(self, start: AnalyzedFace) -> List[int]:
        """Findet alle koplanaren Plane-Faces."""
        if start.surface_type != SurfaceType.PLANE:
            return [start.idx]

        related = [start.idx]
        queue = [start.idx]
        visited = {start.idx}

        while queue:
            current_idx = queue.pop(0)
            current = self._faces[current_idx]

            for n_idx in self._adjacency.get(current_idx, []):
                if n_idx in visited:
                    continue

                neighbor = self._faces[n_idx]
                if neighbor.surface_type == SurfaceType.PLANE:
                    if self._are_coplanar(current, neighbor):
                        related.append(n_idx)
                        queue.append(n_idx)
                        visited.add(n_idx)

        return related

    def _are_coplanar(self, f1: AnalyzedFace, f2: AnalyzedFace) -> bool:
        """Prueft ob zwei Planes koplanar sind."""
        if f1.normal is None or f2.normal is None:
            return False

        # Parallele Normalen
        dot = abs(np.dot(f1.normal, f2.normal))
        if dot < 1 - self.ANGLE_TOLERANCE:
            return False

        # Auf gleicher Ebene
        if f1.center is None or f2.center is None:
            return False

        diff = f2.center - f1.center
        dist = abs(np.dot(diff, f1.normal))

        return dist < self.COPLANAR_TOLERANCE

    # =========================================================================
    # Planar Cluster Analysis (fuer tessellierte Zylinder)
    # =========================================================================

    def _detect_planar_cylinder_clusters(self, processed: set) -> List[DetectedFeature]:
        """
        Erkennt zylindrische Features in Gruppen von planaren Faces.

        Tesslierte Zylinder bestehen aus vielen kleinen planaren Faces,
        deren Normalen radial nach innen/aussen zeigen. Diese Methode:
        1. Findet Gruppen von Faces mit radialen Normalen
        2. Fittet einen Zylinder an die Face-Zentren
        3. Klassifiziert als Loch oder Bolzen
        """
        features = []

        # Sammle alle nicht-verarbeiteten planaren Faces
        plane_faces = [
            f for f in self._faces
            if f.surface_type == SurfaceType.PLANE and f.idx not in processed
        ]

        if len(plane_faces) < 6:  # Mindestens 6 Faces fuer einen Zylinder
            return features

        # Gruppiere Faces nach aehnlicher Z-Koordinate (Achsen-Hoehe)
        # um horizontale Loecher zu finden
        for axis_idx, axis_name in enumerate(['Z', 'Y', 'X']):
            axis_features = self._find_cylindrical_clusters_along_axis(
                plane_faces, axis_idx, processed
            )
            features.extend(axis_features)

        return features

    def _find_cylindrical_clusters_along_axis(
        self,
        plane_faces: List[AnalyzedFace],
        axis_idx: int,
        processed: set
    ) -> List[DetectedFeature]:
        """Findet zylindrische Cluster entlang einer bestimmten Achse."""
        features = []

        # Sortiere Faces nach Position entlang der Achse
        axis_positions = {}
        tolerance = 1.0  # mm

        for face in plane_faces:
            if face.idx in processed:
                continue
            if face.center is None or face.normal is None:
                continue

            # Gruppiere nach Achsen-Position
            pos = face.center[axis_idx]
            found_group = False
            for key in axis_positions:
                if abs(key - pos) < tolerance:
                    axis_positions[key].append(face)
                    found_group = True
                    break
            if not found_group:
                axis_positions[pos] = [face]

        # Analysiere jede Gruppe
        for pos, faces_at_height in axis_positions.items():
            if len(faces_at_height) < 4:  # Mindestens 4 Faces
                continue

            # Pruefe ob Normalen radial sind (2D in der Ebene senkrecht zur Achse)
            cylinder_result = self._fit_cylinder_to_faces(faces_at_height, axis_idx)

            if cylinder_result:
                radius, center_2d, is_hole, face_indices = cylinder_result

                # Filtere bereits verarbeitete
                face_indices = [i for i in face_indices if i not in processed]
                if len(face_indices) < 4:
                    continue

                if is_hole:
                    feature_type = FeatureType.HOLE_THROUGH
                else:
                    feature_type = FeatureType.BOSS_CYLINDER

                feature = DetectedFeature(
                    feature_type=feature_type,
                    face_indices=face_indices,
                    parameters={
                        "radius": radius,
                        "diameter": radius * 2,
                        "center": center_2d.tolist(),
                        "axis": ['X', 'Y', 'Z'][axis_idx],
                        "detected_from": "planar_cluster"
                    },
                    confidence=0.7,
                    suggested_action=f"Tessellierter Zylinder (R={radius:.2f}mm)"
                )
                features.append(feature)
                processed.update(face_indices)

        return features

    def _fit_cylinder_to_faces(
        self,
        faces: List[AnalyzedFace],
        axis_idx: int
    ) -> Optional[Tuple[float, np.ndarray, bool, List[int]]]:
        """
        Versucht einen Zylinder an eine Gruppe von Faces zu fitten.

        Returns:
            (radius, center_2d, is_hole, face_indices) oder None
        """
        # Sammle 2D-Punkte (senkrecht zur Achse) und Normalen
        points_2d = []
        normals_2d = []
        face_indices = []

        other_axes = [i for i in range(3) if i != axis_idx]

        for face in faces:
            if face.center is None or face.normal is None:
                continue

            # 2D-Projektion senkrecht zur Achse
            p2d = np.array([face.center[other_axes[0]], face.center[other_axes[1]]])
            n2d = np.array([face.normal[other_axes[0]], face.normal[other_axes[1]]])

            # Normale muss signifikante 2D-Komponente haben
            n2d_len = np.linalg.norm(n2d)
            if n2d_len < 0.3:  # Normale ist hauptsaechlich in Achsenrichtung
                continue

            n2d = n2d / n2d_len
            points_2d.append(p2d)
            normals_2d.append(n2d)
            face_indices.append(face.idx)

        if len(points_2d) < 4:
            return None

        points_2d = np.array(points_2d)
        normals_2d = np.array(normals_2d)

        # Finde Kreismittelpunkt durch Schnitt der Normalenlinien
        # Verwende Least-Squares fuer robustere Loesung
        center_2d = self._find_circle_center_from_normals(points_2d, normals_2d)

        if center_2d is None:
            return None

        # Berechne Radius und pruefe Konsistenz
        radii = np.linalg.norm(points_2d - center_2d, axis=1)
        radius_mean = np.mean(radii)
        radius_std = np.std(radii)

        # Radius muss konsistent sein (< 20% Variation)
        if radius_std > radius_mean * 0.2:
            return None

        # Minimum Radius (< 1mm ist wahrscheinlich kein Feature)
        if radius_mean < 1.0:
            return None

        # Pruefe ob Loch (Normalen zeigen nach aussen) oder Boss (nach innen)
        # Fuer ein Loch: Normale zeigt weg vom Zentrum
        # Fuer einen Boss: Normale zeigt zum Zentrum
        to_center = center_2d - points_2d
        to_center_normalized = to_center / np.linalg.norm(to_center, axis=1, keepdims=True)

        dot_products = np.sum(normals_2d * to_center_normalized, axis=1)
        avg_dot = np.mean(dot_products)

        # Negatives dot = Normalen zeigen weg vom Zentrum = Loch
        is_hole = avg_dot < 0

        return (radius_mean, center_2d, is_hole, face_indices)

    def _find_circle_center_from_normals(
        self,
        points: np.ndarray,
        normals: np.ndarray
    ) -> Optional[np.ndarray]:
        """
        Findet Kreismittelpunkt durch Schnitt der Normalenlinien.

        Verwendet Least-Squares: Jede Normale definiert eine Linie,
        der Mittelpunkt ist der Punkt mit minimalem Abstand zu allen Linien.
        """
        if len(points) < 3:
            return None

        # Fuer jeden Punkt: Linie p + t*n
        # Minimiere sum of squared distances to all lines
        # Equivalent zu: A @ center = b

        n = len(points)
        A = np.zeros((2 * n, 2))
        b = np.zeros(2 * n)

        for i in range(n):
            p = points[i]
            normal = normals[i]

            # Tangente (senkrecht zur Normale)
            tangent = np.array([-normal[1], normal[0]])

            # Bedingung: (center - p) dot tangent = 0
            # => center dot tangent = p dot tangent
            A[2*i] = tangent
            b[2*i] = np.dot(p, tangent)

            # Zweite Bedingung fuer Stabilität (leicht versetzt)
            A[2*i+1] = normal
            b[2*i+1] = np.dot(p, normal)

        try:
            center, residuals, rank, s = np.linalg.lstsq(A, b, rcond=None)
            return center
        except Exception as e:
            logger.debug(f"[brep_face_analyzer.py] Fehler: {e}")
            return None


# =============================================================================
# Convenience Functions
# =============================================================================

def analyze_body(solid) -> AnalysisResult:
    """
    Convenience-Funktion fuer Body-Analyse.

    Usage:
        from modeling.brep_face_analyzer import analyze_body
        result = analyze_body(body._build123d_solid)
    """
    analyzer = BRepFaceAnalyzer()
    return analyzer.analyze(solid)
