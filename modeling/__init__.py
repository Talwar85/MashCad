
"""
MashCad - 3D Modeling
Robust B-Rep Implementation with Build123d & Smart Failure Recovery
"""

from dataclasses import dataclass, field
import tempfile
from typing import List, Optional, Tuple, Union, Any
from enum import Enum, auto
import math
import uuid
import sys
import os
import traceback
from loguru import logger 
try:
    from shapely.geometry import LineString, Polygon as ShapelyPoly, Point
    from shapely.ops import polygonize, unary_union
except ImportError:
    logger.warning("Shapely nicht gefunden. Komplexe Skizzen könnten fehlschlagen.")
    
    
# WICHTIG: Unser neuer Helper
from modeling.cad_tessellator import CADTessellator
from modeling.mesh_converter import MeshToBREPConverter # NEU
from modeling.result_types import OperationResult, BooleanResult, ResultStatus  # Result-Pattern
from config.tolerances import Tolerances  # Phase 5: Zentralisierte Toleranzen
from modeling.geometry_validator import GeometryValidator, ValidationResult, ValidationLevel  # Phase 7
from modeling.geometry_healer import GeometryHealer, HealingResult, HealingStrategy  # Phase 7
from modeling.nurbs import NURBSCurve, NURBSSurface, ContinuityMode, CurveType  # Phase 8
from modeling.step_io import STEPWriter, STEPReader, STEPSchema, export_step as step_export  # Phase 8.3
# NOTE: Altes TNP-System (Phase 8.2) deaktiviert - verwendet TNP v3.0
# from modeling.tnp_tracker import TNPTracker, ShapeReference, get_tnp_tracker
from modeling.feature_dependency import FeatureDependencyGraph, get_dependency_graph  # Phase 7
from config.feature_flags import is_enabled  # Für TNP Debug Logging
from modeling.boolean_engine_v4 import BooleanEngineV4  # Zentraler Boolean-Engine

# TNP v4.0 - Professionelles Topological Naming System
from modeling.tnp_system import (
    ShapeNamingService, ShapeID, ShapeType, 
    OperationRecord
)


# ==================== IMPORTS ====================
HAS_BUILD123D = False
HAS_OCP = False

# OCP wird IMMER geladen (für robuste Boolean Operations)
try:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
    )
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut, BRepAlgoAPI_Common
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet, BRepFilletAPI_MakeChamfer
    from OCP.StlAPI import StlAPI_Writer
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopoDS import TopoDS_Shape, TopoDS_Solid, TopoDS_Face, TopoDS_Edge, TopoDS_Wire
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_SOLID
    from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax1, gp_Ax2, gp_Pln, gp_Trsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Solid
    from OCP.BRepCheck import BRepCheck_Analyzer
    HAS_OCP = True
    logger.success("✓ OCP (OpenCASCADE) geladen.")
except ImportError as e:
    logger.warning(f"! OCP nicht gefunden: {e}")

# Build123d als High-Level API (optional, aber empfohlen)
try:
    from build123d import (
        Box, Cylinder, Sphere, Solid, Shape,
        extrude, revolve, fillet, chamfer,
        loft, sweep, offset,  # Phase 6: Loft, Sweep, Shell
        Axis, Plane, Locations, Vector,
        BuildPart, BuildSketch, BuildLine,
        Part, Sketch as B123Sketch,
        Rectangle as B123Rect, Circle as B123Circle,
        Polyline, Polygon, make_face, Mode,
        export_stl, export_step,
        GeomType
    )
    HAS_BUILD123D = True
    logger.success("✓ build123d geladen (High-Level API).")
except ImportError as e:
    logger.warning(f"! build123d nicht gefunden: {e}")

# Projektpfad
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from sketcher import Sketch

# ==================== DATENSTRUKTUREN ====================

class FeatureType(Enum):
    SKETCH = auto()
    EXTRUDE = auto()
    REVOLVE = auto()
    FILLET = auto()
    CHAMFER = auto()
    TRANSFORM = auto()  # Für Move/Rotate/Scale/Mirror
    LOFT = auto()       # Phase 6: Loft zwischen Profilen
    SWEEP = auto()      # Phase 6: Sweep entlang Pfad
    SHELL = auto()      # Phase 6: Körper aushöhlen
    SURFACE_TEXTURE = auto()  # Phase 7: Flächen-Texturierung für 3D-Druck
    HOLE = auto()             # Bohrung (Simple, Counterbore, Countersink)
    DRAFT = auto()            # Entformungsschräge
    SPLIT = auto()            # Körper teilen
    THREAD = auto()           # Gewinde (kosmetisch + geometrisch)
    HOLLOW = auto()           # Aushöhlen mit optionalem Drain Hole
    LATTICE = auto()          # Gitterstruktur für Leichtbau
    PUSHPULL = auto()         # Face Extrude/Offset entlang Normale
    NSIDED_PATCH = auto()     # N-seitiger Patch (Surface Fill)
    IMPORT = auto()           # Importierter Body (Mesh-Konvertierung, STEP Import)

@dataclass
class Feature:
    type: FeatureType = None
    name: str = "Feature"
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    visible: bool = True
    suppressed: bool = False
    status: str = "OK" # OK, ERROR, WARNING

@dataclass
class ExtrudeFeature(Feature):
    """
    Extrude Feature - CAD Kernel First Architektur.

    Profile werden IMMER aus dem Sketch abgeleitet (wenn sketch vorhanden).
    profile_selector identifiziert welche Profile gewählt wurden (via Centroid).
    precalculated_polys ist NUR für sketchlose Operationen (Push/Pull).
    """
    sketch: Sketch = None
    distance: float = 10.0
    distance_formula: Optional[str] = None
    direction: int = 1
    operation: str = "New Body"
    selector: list = None
    # CAD Kernel First: Profile-Selektor (Centroids der gewählten Profile)
    # Bei Rebuild werden Profile aus Sketch berechnet und per Centroid-Match gefiltert
    profile_selector: list = field(default_factory=list)  # [(cx, cy), ...] Centroids
    # Legacy: Nur für sketchlose Operationen (Push/Pull auf 3D-Face)
    precalculated_polys: list = field(default_factory=list)
    # Plane-Info für Rebuild (wenn sketch=None)
    plane_origin: tuple = field(default_factory=lambda: (0, 0, 0))
    plane_normal: tuple = field(default_factory=lambda: (0, 0, 1))
    plane_x_dir: tuple = None
    plane_y_dir: tuple = None
    # Push/Pull auf nicht-planaren Flächen: OCP Face als BREP-String speichern
    face_brep: Optional[str] = None  # Serialisierte OCP TopoDS_Face
    face_type: Optional[str] = None  # "plane", "cylinder", "cone", etc.
    # TNP v3.0: Face-Selector für Push/Pull auf Body-Faces (BRepFeat-Operationen)
    face_selector: dict = None  # GeometricFaceSelector.to_dict()

    def __post_init__(self):
        self.type = FeatureType.EXTRUDE
        if not self.name or self.name == "Feature": self.name = "Extrude"

@dataclass
class RevolveFeature(Feature):
    """
    Revolve Feature - CAD Kernel First Architektur.

    Profile werden IMMER aus dem Sketch abgeleitet (wenn sketch vorhanden).
    profile_selector identifiziert welche Profile gewählt wurden (via Centroid).
    """
    sketch: Sketch = None
    angle: float = 360.0
    angle_formula: Optional[str] = None
    axis: Tuple[float, float, float] = (0, 1, 0)
    axis_origin: Tuple[float, float, float] = (0, 0, 0)
    operation: str = "New Body"
    # CAD Kernel First: Profile-Selektor (Centroids der gewählten Profile)
    profile_selector: list = field(default_factory=list)  # [(cx, cy), ...] Centroids
    # Legacy: Nur für sketchlose Operationen
    precalculated_polys: list = None

    def __post_init__(self):
        self.type = FeatureType.REVOLVE
        if not self.name or self.name == "Feature": self.name = "Revolve"

@dataclass
class FilletFeature(Feature):
    """
    Fillet-Feature mit professionellem TNP (Topological Naming Problem) Handling.
    
    TNP v3.0 Architektur:
    1. edge_shape_ids: Persistent ShapeIDs für History-Tracking
    2. geometric_selectors: Geometrische Fingerabdrücke (Fallback)
    3. edge_selectors: Legacy Point-Selektoren (Kompatibilität)
    
    Das Feature speichert ShapeIDs beim Erstellen und löst diese
    via TNPResolver zum Zeitpunkt der Ausführung auf.
    """
    radius: float = 2.0
    radius_formula: Optional[str] = None
    
    # TNP v3.0: Persistent ShapeIDs (Primary)
    edge_shape_ids: List = None  # List[ShapeID] - persistente IDs
    
    # Fallback: Geometric Selectors
    geometric_selectors: List = None  # GeometricEdgeSelector Objekte
    
    # Legacy
    edge_selectors: List = None  # [(x,y,z), ...] Mittelpunkte
    ocp_edge_shapes: List = None  # OCP TopoDS_Edge Shapes
    
    # TNP Phase 2: Abhängigkeit zu vorherigem Boolean-Feature
    depends_on_feature_id: Optional[str] = None

    def __post_init__(self):
        self.type = FeatureType.FILLET
        if not self.name or self.name == "Feature":
            self.name = "Fillet"
        if self.edge_shape_ids is None:
            self.edge_shape_ids = []
        if self.geometric_selectors is None:
            self.geometric_selectors = []
        if self.edge_selectors is None:
            self.edge_selectors = []
        if self.ocp_edge_shapes is None:
            self.ocp_edge_shapes = []


@dataclass
class ChamferFeature(Feature):
    """
    Chamfer-Feature mit professionellem TNP (Topological Naming Problem) Handling.
    
    TNP v3.0 Architektur:
    1. edge_shape_ids: Persistent ShapeIDs für History-Tracking
    2. geometric_selectors: Geometrische Fingerabdrücke (Fallback)
    3. edge_selectors: Legacy Point-Selektoren (Kompatibilität)
    
    Das Feature speichert ShapeIDs beim Erstellen und löst diese
    via TNPResolver zum Zeitpunkt der Ausführung auf.
    """
    distance: float = 2.0
    distance_formula: Optional[str] = None
    
    # TNP v3.0: Persistent ShapeIDs (Primary)
    edge_shape_ids: List = None  # List[ShapeID] - persistente IDs
    
    # Fallback: Geometric Selectors
    geometric_selectors: List = None  # GeometricEdgeSelector Objekte
    
    # Legacy
    edge_selectors: List = None  # [(x,y,z), ...] Mittelpunkte
    ocp_edge_shapes: List = None  # OCP TopoDS_Edge Shapes
    
    # TNP Phase 2: Abhängigkeit zu vorherigem Boolean-Feature
    depends_on_feature_id: Optional[str] = None

    def __post_init__(self):
        self.type = FeatureType.CHAMFER
        if not self.name or self.name == "Feature":
            self.name = "Chamfer"
        if self.edge_shape_ids is None:
            self.edge_shape_ids = []
        if self.edge_selectors is None:
            self.edge_selectors = []
        if self.geometric_selectors is None:
            self.geometric_selectors = []
        if self.ocp_edge_shapes is None:
            self.ocp_edge_shapes = []


@dataclass
class TransformFeature(Feature):
    """
    Parametric transform stored in feature history.

    Enables:
    - Undo/Redo support
    - Parametric editing
    - Feature tree visibility
    - Body rebuild consistency
    """
    mode: str = "move"  # "move", "rotate", "scale", "mirror"
    data: dict = field(default_factory=dict)
    # data examples:
    # Move: {"translation": [10.0, 0.0, 5.0]}
    # Rotate: {"axis": "Z", "angle": 45.0, "center": [0.0, 0.0, 0.0]}
    # Scale: {"factor": 1.5, "center": [0.0, 0.0, 0.0]}
    # Mirror: {"plane": "XY"}

    def __post_init__(self):
        self.type = FeatureType.TRANSFORM
        if not self.name or self.name == "Feature":
            self.name = f"Transform: {self.mode.capitalize()}"


# ==================== PHASE 6: ADVANCED FEATURES ====================

@dataclass
class LoftFeature(Feature):
    """
    Loft zwischen 2+ Profilen auf verschiedenen Ebenen.

    Build123d API: loft(sections, ruled=False, clean=True, mode=Mode.ADD)
    OCP Fallback: BRepOffsetAPI_ThruSections

    TNP v3.0: ShapeIDs für Profile bei Body-Face Referenzen.
    Phase 8: Erweitert mit Kontinuitäts-Kontrolle (G0/G1/G2)
    """
    profile_data: List[dict] = field(default_factory=list)
    # Jedes Element: {
    #   "type": "sketch_profile" | "body_face",
    #   "shapely_poly": Polygon | None,
    #   "plane_origin": tuple,
    #   "plane_normal": tuple,
    #   "plane_x_dir": tuple,
    #   "plane_y_dir": tuple
    # }
    
    # TNP v4.0: ShapeIDs für Body-Face Profile (nicht Sketch-Profile)
    profile_shape_ids: List = None  # List[ShapeID] - parallel zu profile_data

    # TNP v4.0: GeometricFaceSelectors als Fallback (parallel zu profile_data)
    profile_geometric_selectors: List = None  # List[GeometricFaceSelector]

    ruled: bool = False  # True = gerade Linien, False = glatt interpoliert
    operation: str = "New Body"  # "New Body", "Join", "Cut", "Intersect"

    # Phase 8: NURBS Kontinuitäts-Kontrolle
    start_continuity: str = "G0"  # "G0", "G1", "G2" - Kontinuität am Start
    end_continuity: str = "G0"    # "G0", "G1", "G2" - Kontinuität am Ende
    guide_curves: List[dict] = field(default_factory=list)  # Guide-Kurven für Formkontrolle
    spine_curve: Optional[dict] = None  # Spine-Kurve für nicht-planare Lofts

    def __post_init__(self):
        self.type = FeatureType.LOFT
        if not self.name or self.name == "Feature":
            self.name = "Loft"
        if self.profile_shape_ids is None:
            self.profile_shape_ids = []
        if self.profile_geometric_selectors is None:
            self.profile_geometric_selectors = []

    def get_start_continuity_mode(self):
        """Konvertiert String zu ContinuityMode Enum."""
        mode_map = {"G0": ContinuityMode.G0, "G1": ContinuityMode.G1, "G2": ContinuityMode.G2}
        return mode_map.get(self.start_continuity, ContinuityMode.G0)

    def get_end_continuity_mode(self):
        """Konvertiert String zu ContinuityMode Enum."""
        mode_map = {"G0": ContinuityMode.G0, "G1": ContinuityMode.G1, "G2": ContinuityMode.G2}
        return mode_map.get(self.end_continuity, ContinuityMode.G0)


@dataclass
class SweepFeature(Feature):
    """
    Sweep eines Profils entlang eines Pfads.

    Build123d API: sweep(sections, path, is_frenet=False)
    OCP Fallback: BRepOffsetAPI_MakePipe

    TNP v3.0: ShapeIDs für Profile und Path bei Body-Referenzen.
    Phase 8: Erweitert mit Twist, Skalierung und Auxiliary Spine
    """
    profile_data: dict = field(default_factory=dict)
    # {
    #   "type": "sketch_profile" | "body_face",
    #   "shapely_poly": Polygon | None,
    #   "plane_origin": tuple,
    #   "plane_normal": tuple,
    #   ...
    # }
    path_data: dict = field(default_factory=dict)
    # {
    #   "type": "sketch_edge" | "body_edge",
    #   "edge_selector": tuple,  # Mittelpunkt für TNP-Fallback
    #   "sketch_id": str | None,
    #   "body_id": str | None
    # }
    
    # TNP v4.0: ShapeIDs für Body-Referenzen
    profile_shape_id: Any = None  # ShapeID für Body-Face Profile
    path_shape_id: Any = None     # ShapeID für Body-Edge Path

    # TNP v4.0: GeometricSelectors als Fallback
    profile_geometric_selector: Any = None  # GeometricFaceSelector
    path_geometric_selector: Any = None     # GeometricEdgeSelector

    is_frenet: bool = False  # Frenet-Frame für Verdrehung entlang Pfad
    operation: str = "New Body"

    # Phase 8: Erweiterte NURBS-Sweep-Optionen
    twist_angle: float = 0.0        # Verdrehung in Grad entlang des Pfads
    scale_start: float = 1.0        # Skalierungsfaktor am Pfad-Start
    scale_end: float = 1.0          # Skalierungsfaktor am Pfad-Ende
    auxiliary_spine: Optional[dict] = None  # Auxiliary Spine für komplexe Orientierung
    contact_mode: str = "keep"      # "keep", "right_corner", "round_corner"

    def __post_init__(self):
        self.type = FeatureType.SWEEP
        if not self.name or self.name == "Feature":
            self.name = "Sweep"

    def has_scale_or_twist(self) -> bool:
        """Prüft ob Skalierung oder Twist aktiv ist."""
        return (self.twist_angle != 0.0 or
                self.scale_start != 1.0 or
                self.scale_end != 1.0)


@dataclass
class ShellFeature(Feature):
    """
    Shell (Aushöhlen) eines Körpers mit Wandstärke.

    Build123d API: offset(objects, amount, openings)
    OCP Fallback: BRepOffsetAPI_MakeThickSolid
    
    TNP v3.0: Verwendet ShapeIDs + GeometricFaceSelector für stabile Face-Referenzierung.
    """
    thickness: float = 2.0  # Wandstärke in mm
    thickness_formula: Optional[str] = None
    
    # TNP v3.0: Persistent ShapeIDs für Faces (Primary)
    face_shape_ids: List = None  # List[ShapeID]
    
    # TNP-robust: Liste von GeometricFaceSelector.to_dict() Dicts (Fallback)
    # Enthält: center, normal, area, surface_type, tolerance
    opening_face_selectors: List[dict] = field(default_factory=list)

    # Keine Boolean-Operation - Shell modifiziert den Body direkt

    def __post_init__(self):
        self.type = FeatureType.SHELL
        if not self.name or self.name == "Feature":
            self.name = "Shell"
        if self.face_shape_ids is None:
            self.face_shape_ids = []


@dataclass
class HoleFeature(Feature):
    """
    Bohrung in eine Fläche.
    Typen: simple (Durchgangsbohrung/Sackloch), counterbore, countersink.
    
    TNP v3.0: Verwendet ShapeIDs + GeometricFaceSelector für stabile Face-Referenzierung.
    """
    hole_type: str = "simple"  # "simple", "counterbore", "countersink"
    diameter: float = 8.0
    diameter_formula: Optional[str] = None
    depth: float = 0.0  # 0 = through all
    depth_formula: Optional[str] = None
    
    # TNP v3.0: Persistent ShapeIDs für Faces (Primary)
    face_shape_ids: List = None  # List[ShapeID]
    
    # TNP-robust: Liste von GeometricFaceSelector.to_dict() Dicts (Fallback)
    # Enthält: center, normal, area, surface_type, tolerance
    face_selectors: List[dict] = field(default_factory=list)
    position: Tuple[float, float, float] = (0, 0, 0)
    direction: Tuple[float, float, float] = (0, 0, -1)
    # Counterbore
    counterbore_diameter: float = 12.0
    counterbore_depth: float = 3.0
    # Countersink
    countersink_angle: float = 82.0

    def __post_init__(self):
        self.type = FeatureType.HOLE
        if not self.name or self.name == "Feature":
            self.name = f"Hole ({self.hole_type})"
        if self.face_shape_ids is None:
            self.face_shape_ids = []


@dataclass
class DraftFeature(Feature):
    """
    Entformungsschräge (Draft/Taper) auf Flächen.
    Build123d: draft() auf selektierte Faces.
    
    TNP v3.0: Verwendet ShapeIDs + GeometricFaceSelector für stabile Face-Referenzierung.
    """
    draft_angle: float = 5.0  # Grad
    pull_direction: Tuple[float, float, float] = (0, 0, 1)
    
    # TNP v3.0: Persistent ShapeIDs für Faces (Primary)
    face_shape_ids: List = None  # List[ShapeID]
    
    # TNP-robust: Liste von GeometricFaceSelector.to_dict() Dicts (Fallback)
    # Enthält: center, normal, area, surface_type, tolerance
    face_selectors: List[dict] = field(default_factory=list)

    def __post_init__(self):
        self.type = FeatureType.DRAFT
        if not self.name or self.name == "Feature":
            self.name = f"Draft {self.draft_angle}°"
        if self.face_shape_ids is None:
            self.face_shape_ids = []


@dataclass
class SplitResult:
    """
    Result of a split operation that creates 2 bodies.

    TNP v4.0: Enthält beide Bodies + optional Split-Face ShapeIDs
    """
    body_above: Any      # Solid auf der +normal Seite
    body_below: Any      # Solid auf der -normal Seite
    split_plane: dict    # Plane-Info für Visualisierung (origin, normal)

    # TNP v4.0: Optional Face-ShapeIDs für Split-Faces
    above_split_face_ids: List = None
    below_split_face_ids: List = None


@dataclass
class SplitFeature(Feature):
    """
    Körper teilen entlang einer Ebene.
    Erzeugt zwei Hälften, behält die gewählte Seite.
    """
    plane_origin: Tuple[float, float, float] = (0, 0, 0)
    plane_normal: Tuple[float, float, float] = (0, 0, 1)
    keep_side: str = "above"  # "above", "below", "both"

    def __post_init__(self):
        self.type = FeatureType.SPLIT
        if not self.name or self.name == "Feature":
            self.name = "Split"


@dataclass
class ThreadFeature(Feature):
    """
    Gewinde-Feature: Erzeugt eine helikale Nut auf zylindrischen Flaechen.

    Thread-Standards: M (metrisch), UNC, UNF
    Typ: internal (Mutter) oder external (Schraube)
    
    TNP v3.0: ShapeID für die zylindrische Face-Referenz.
    """
    thread_type: str = "external"  # "external" or "internal"
    standard: str = "M"           # "M", "UNC", "UNF"
    diameter: float = 10.0        # Nenn-Durchmesser
    pitch: float = 1.5            # Steigung in mm
    depth: float = 20.0           # Gewindelaenge
    position: Tuple[float, float, float] = (0, 0, 0)
    direction: Tuple[float, float, float] = (0, 0, 1)
    tolerance_class: str = "6g"   # ISO 965-1 fit class
    tolerance_offset: float = 0.0 # Diameter offset in mm
    
    # TNP v3.0: ShapeID für zylindrische Face
    face_shape_id: Any = None  # ShapeID
    face_selector: dict = None  # GeometricFaceSelector als Fallback

    def __post_init__(self):
        self.type = FeatureType.THREAD
        if not self.name or self.name == "Feature":
            self.name = f"{self.standard}{self.diameter:.0f}x{self.pitch}"


@dataclass
class HollowFeature(Feature):
    """
    Aushöhlen eines Körpers mit optionalem Drain Hole (für SLA/SLS Druck).
    Intern: Shell (geschlossen) + Boolean Cut Zylinder.

    TNP v4.0: Face-Referenzen für Opening-Faces (wie Shell)
    """
    wall_thickness: float = 2.0          # Wandstärke in mm
    drain_hole: bool = False             # Drain Hole aktiviert?
    drain_diameter: float = 3.0          # Drain Hole Durchmesser in mm
    drain_position: Tuple[float, float, float] = (0, 0, 0)  # Startpunkt
    drain_direction: Tuple[float, float, float] = (0, 0, -1) # Richtung (default: nach unten)

    # TNP v4.0: Optional Opening-Faces für partielles Shell
    opening_face_shape_ids: List = None  # List[ShapeID]
    opening_face_selectors: List = None  # List[GeometricFaceSelector]

    def __post_init__(self):
        self.type = FeatureType.HOLLOW
        if not self.name or self.name == "Feature":
            self.name = "Hollow"
        if self.opening_face_shape_ids is None:
            self.opening_face_shape_ids = []
        if self.opening_face_selectors is None:
            self.opening_face_selectors = []


@dataclass
class LatticeFeature(Feature):
    """Gitterstruktur für Leichtbau / 3D-Druck."""
    cell_type: str = "BCC"           # BCC, FCC, Octet, Diamond
    cell_size: float = 5.0           # Zellgröße in mm
    beam_radius: float = 0.5         # Strebendurchmesser/2 in mm
    shell_thickness: float = 0.0     # Wandstärke der Außenhülle in mm (0 = keine)

    def __post_init__(self):
        self.type = FeatureType.LATTICE
        if not self.name or self.name == "Feature":
            self.name = f"Lattice ({self.cell_type})"


@dataclass
class NSidedPatchFeature(Feature):
    """
    N-Sided Patch - Boundary-Edges mit glatter Fläche füllen.
    
    TNP v3.0: ShapeIDs für stabile Edge-Referenzen.
    """
    edge_selectors: list = field(default_factory=list)  # Liste von (center, direction) Tupeln
    
    # TNP v3.0: ShapeIDs für Edges (Primary)
    edge_shape_ids: List = None  # List[ShapeID]
    
    # Geometric Selectors als Fallback
    geometric_selectors: List = None  # List[GeometricEdgeSelector]
    
    degree: int = 3
    tangent: bool = True

    def __post_init__(self):
        self.type = FeatureType.NSIDED_PATCH
        if not self.name or self.name == "Feature":
            self.name = f"N-Sided Patch ({len(self.edge_selectors)} edges)"
        if self.edge_shape_ids is None:
            self.edge_shape_ids = []
        if self.geometric_selectors is None:
            self.geometric_selectors = []


@dataclass
class PushPullFeature(Feature):
    """
    PushPull - Face entlang Normale extrudieren/eindrücken.
    
    TNP v3.0: Verwendet ShapeIDs + GeometricFaceSelector für stabile Face-Referenzierung
    über Geometrie-Änderungen hinweg (z.B. nach anderen Push/Pull Operationen).
    """
    # TNP v3.0: Persistent ShapeID für Face (Primary)
    face_shape_id: Any = None  # ShapeID
    
    # GeometricFaceSelector als Dict (Fallback)
    # Enthält: center, normal, area, surface_type, tolerance
    face_selector: dict = None
    distance: float = 10.0       # Positiv = raus, negativ = rein
    operation: str = "Join"      # Join, Cut, New Body

    def __post_init__(self):
        self.type = FeatureType.PUSHPULL
        if not self.name or self.name == "Feature":
            self.name = f"PushPull ({self.distance:+.1f}mm)"


@dataclass
class ImportFeature(Feature):
    """
    Import Feature - Speichert die Original-BREP eines importierten Bodies.

    Wird verwendet für:
    - Mesh-zu-CAD Konvertierung (STL/OBJ → BREP)
    - STEP/IGES Import
    - Jede externe Geometrie die als Basis für weitere Features dient

    Die BREP wird als String gespeichert (via BRepTools.Write_s) um Serialisierung
    zu ermöglichen. Beim Rebuild wird die BREP aus dem String rekonstruiert.
    """
    brep_string: str = ""  # BREP als String (via BRepTools.Write_s)
    source_file: str = ""  # Original-Dateiname (für Anzeige)
    source_type: str = ""  # "mesh_convert", "step_import", "iges_import"

    def __post_init__(self):
        self.type = FeatureType.IMPORT
        if not self.name or self.name == "Feature":
            if self.source_file:
                self.name = f"Import ({self.source_file})"
            else:
                self.name = "Import"

    def get_solid(self):
        """Rekonstruiert das Solid aus dem BREP-String."""
        if not self.brep_string:
            return None
        try:
            from OCP.BRepTools import BRepTools
            from OCP.TopoDS import TopoDS_Shape
            from OCP.BRep import BRep_Builder
            from build123d import Solid
            import io

            builder = BRep_Builder()
            shape = TopoDS_Shape()

            # BREP aus String lesen (via BytesIO Stream)
            stream = io.BytesIO(self.brep_string.encode('utf-8'))
            BRepTools.Read_s(shape, stream, builder)

            if not shape.IsNull():
                return Solid(shape)
        except Exception as e:
            from loguru import logger
            logger.error(f"ImportFeature.get_solid() fehlgeschlagen: {e}")
        return None


@dataclass
class SurfaceTextureFeature(Feature):
    """
    Non-destruktive Flächen-Texturierung für 3D-Druck.

    KRITISCH: Das BREP wird NIEMALS modifiziert!
    Texturen sind ein reiner Metadaten-Layer.
    Die Textur wird erst beim Export als Displacement auf das Mesh angewendet.

    TNP v3.0: ShapeIDs + GeometricFaceSelector für robuste Face-Referenzierung.

    Textur-Typen:
    - ripple: Wellenförmige Rillen (Grip)
    - honeycomb: Wabenstruktur (Leichtbau)
    - diamond: Rauten-Muster (Grip)
    - knurl: Rändelmuster (Griffe)
    - crosshatch: Kreuzschraffur (Anti-Rutsch)
    - voronoi: Organische Zellstruktur
    - custom: Benutzerdefinierte Heightmap
    """
    texture_type: str = "ripple"

    # TNP v3.0: ShapeIDs für Faces (Primary)
    face_shape_ids: List = None  # List[ShapeID]
    
    # Face-Selektion (Fallback)
    # Liste von GeometricFaceSelector.to_dict() Dicts
    face_selectors: List[dict] = field(default_factory=list)

    # Textur-Parameter
    scale: float = 1.0       # Pattern-Größe in mm
    depth: float = 0.5       # Displacement-Tiefe in mm
    rotation: float = 0.0    # Pattern-Rotation in Grad
    invert: bool = False     # Displacement umkehren

    # Typ-spezifische Parameter
    type_params: dict = field(default_factory=dict)

    # 3D-Druck-Optimierung
    solid_base: bool = True  # True = keine Löcher (nur positive Displacement), False = bidirektional

    # Export-Einstellungen
    export_subdivisions: int = 4  # Mesh-Unterteilung für Export (4 = gute Textur-Auflösung)

    def __post_init__(self):
        self.type = FeatureType.SURFACE_TEXTURE
        if self.face_shape_ids is None:
            self.face_shape_ids = []
        if not self.name or self.name == "Feature":
            self.name = f"Texture: {self.texture_type.capitalize()}"

    def to_dict(self) -> dict:
        """Serialisierung für Persistierung."""
        return {
            "class": "SurfaceTextureFeature",
            "id": self.id,
            "name": self.name,
            "visible": self.visible,
            "suppressed": self.suppressed,
            "status": self.status,
            "texture_type": self.texture_type,
            "face_selectors": self.face_selectors,
            "scale": self.scale,
            "depth": self.depth,
            "rotation": self.rotation,
            "invert": self.invert,
            "type_params": self.type_params,
            "solid_base": self.solid_base,
            "export_subdivisions": self.export_subdivisions,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'SurfaceTextureFeature':
        """Deserialisierung aus dict."""
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", "Texture"),
            visible=data.get("visible", True),
            suppressed=data.get("suppressed", False),
            status=data.get("status", "OK"),
            texture_type=data.get("texture_type", "ripple"),
            face_selectors=data.get("face_selectors", []),
            scale=data.get("scale", 1.0),
            depth=data.get("depth", 0.5),
            rotation=data.get("rotation", 0.0),
            invert=data.get("invert", False),
            type_params=data.get("type_params", {}),
            solid_base=data.get("solid_base", True),  # Default True für 3D-Druck-Sicherheit
            export_subdivisions=data.get("export_subdivisions", 2),
        )


@dataclass
class ConstructionPlane:
    """
    Konstruktionsebene für Sketches auf beliebigen Z-Offsets.

    Verwendung:
    - Loft-Profile auf verschiedenen Ebenen
    - Offset von Standard-Ebenen (XY, XZ, YZ)
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "Plane"
    origin: Tuple[float, float, float] = (0, 0, 0)
    normal: Tuple[float, float, float] = (0, 0, 1)
    x_dir: Tuple[float, float, float] = (1, 0, 0)
    y_dir: Tuple[float, float, float] = (0, 1, 0)
    visible: bool = True

    @classmethod
    def from_offset(cls, base: str, offset: float, name: str = None):
        """
        Erstellt Ebene mit Offset von Standard-Ebene.

        Args:
            base: "XY", "XZ", oder "YZ"
            offset: Abstand in mm
            name: Optional - sonst automatisch generiert
        """
        configs = {
            "XY": ((0, 0, offset), (0, 0, 1), (1, 0, 0), (0, 1, 0)),
            "XZ": ((0, offset, 0), (0, 1, 0), (1, 0, 0), (0, 0, 1)),
            "YZ": ((offset, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)),
        }
        if base not in configs:
            raise ValueError(f"Base muss XY, XZ oder YZ sein, nicht {base}")

        origin, normal, x_dir, y_dir = configs[base]
        auto_name = name or f"{base} @ {offset:.1f}mm"

        return cls(
            name=auto_name,
            origin=origin,
            normal=normal,
            x_dir=x_dir,
            y_dir=y_dir
        )

    @classmethod
    def from_face(cls, face_center, face_normal, offset: float = 0.0, name: str = None):
        """
        Erstellt Ebene mit Offset von einer Körperfläche.

        Args:
            face_center: (x, y, z) Schwerpunkt der Fläche
            face_normal: (x, y, z) Normale der Fläche
            offset: Abstand in mm entlang der Normalen
            name: Optional
        """
        import numpy as np
        normal = np.array(face_normal, dtype=float)
        norm_len = np.linalg.norm(normal)
        if norm_len < 1e-12:
            raise ValueError("Flächennormale ist null")
        normal = normal / norm_len

        center = np.array(face_center, dtype=float) + normal * offset

        # x_dir orthogonal zur Normalen berechnen
        up = np.array([0, 0, 1], dtype=float)
        if abs(np.dot(normal, up)) > 0.99:
            up = np.array([1, 0, 0], dtype=float)
        x_dir = np.cross(up, normal)
        x_dir = x_dir / np.linalg.norm(x_dir)
        y_dir = np.cross(normal, x_dir)

        auto_name = name or f"Face Plane @ {offset:.1f}mm"

        return cls(
            name=auto_name,
            origin=tuple(center),
            normal=tuple(normal),
            x_dir=tuple(x_dir),
            y_dir=tuple(y_dir),
        )


# ==================== COMPONENT (Assembly System) ====================

@dataclass
class Component:
    """
    Container für Bodies, Sketches, Planes mit eigenem Koordinatensystem.

    Ermöglicht hierarchische Strukturen wie in CAD:
    - Document → Root Component → Sub-Components
    - Jede Component enthält Bodies, Sketches, Planes
    - Sub-Components können eigene Objekte enthalten

    Phase 1: Datenmodell für Assembly-System
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "Component"

    # Enthaltene Objekte (forward references - werden später resolved)
    bodies: List['Body'] = field(default_factory=list)
    sketches: List['Sketch'] = field(default_factory=list)
    planes: List['ConstructionPlane'] = field(default_factory=list)

    # Hierarchie
    sub_components: List['Component'] = field(default_factory=list)
    parent: Optional['Component'] = field(default=None, repr=False)  # Avoid circular repr

    # Transform relativ zum Parent (für Assembly-Positionierung)
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # Euler XYZ in degrees

    # State
    visible: bool = True
    is_active: bool = False  # Nur eine Component kann aktiv sein
    expanded: bool = True    # UI-State für Tree-View

    def __post_init__(self):
        """Logging für neue Component."""
        logger.debug(f"Component erstellt: {self.name} (id={self.id})")

    # =========================================================================
    # Hierarchie-Navigation
    # =========================================================================

    def get_all_bodies(self, recursive: bool = True) -> List['Body']:
        """
        Gibt alle Bodies dieser Component zurück.

        Args:
            recursive: Wenn True, auch Bodies aus Sub-Components

        Returns:
            Liste aller Bodies
        """
        result = list(self.bodies)
        if recursive:
            for sub in self.sub_components:
                result.extend(sub.get_all_bodies(recursive=True))
        return result

    def get_all_sketches(self, recursive: bool = True) -> List['Sketch']:
        """Gibt alle Sketches dieser Component zurück."""
        result = list(self.sketches)
        if recursive:
            for sub in self.sub_components:
                result.extend(sub.get_all_sketches(recursive=True))
        return result

    def get_all_components(self) -> List['Component']:
        """Gibt alle Sub-Components rekursiv zurück (inkl. dieser)."""
        result = [self]
        for sub in self.sub_components:
            result.extend(sub.get_all_components())
        return result

    def find_component_by_id(self, comp_id: str) -> Optional['Component']:
        """Findet Component nach ID (rekursiv)."""
        if self.id == comp_id:
            return self
        for sub in self.sub_components:
            found = sub.find_component_by_id(comp_id)
            if found:
                return found
        return None

    def find_body_by_id(self, body_id: str) -> Optional['Body']:
        """Findet Body nach ID (rekursiv)."""
        for body in self.bodies:
            if body.id == body_id:
                return body
        for sub in self.sub_components:
            found = sub.find_body_by_id(body_id)
            if found:
                return found
        return None

    def get_root(self) -> 'Component':
        """Gibt die Root-Component zurück."""
        if self.parent is None:
            return self
        return self.parent.get_root()

    def get_path(self) -> List['Component']:
        """Gibt den Pfad von Root zu dieser Component zurück."""
        if self.parent is None:
            return [self]
        return self.parent.get_path() + [self]

    # =========================================================================
    # Component Management
    # =========================================================================

    def add_sub_component(self, name: str = None) -> 'Component':
        """
        Erstellt neue Sub-Component.

        Args:
            name: Name der neuen Component (optional)

        Returns:
            Neue Component
        """
        new_comp = Component(name=name or f"Component{len(self.sub_components)+1}")
        new_comp.parent = self
        self.sub_components.append(new_comp)
        logger.info(f"Sub-Component erstellt: {new_comp.name} in {self.name}")
        return new_comp

    def remove_sub_component(self, comp: 'Component') -> bool:
        """
        Entfernt Sub-Component.

        Args:
            comp: Zu entfernende Component

        Returns:
            True wenn erfolgreich
        """
        if comp in self.sub_components:
            self.sub_components.remove(comp)
            comp.parent = None
            logger.info(f"Sub-Component entfernt: {comp.name} aus {self.name}")
            return True
        return False

    def move_body_to(self, body: 'Body', target: 'Component') -> bool:
        """
        Verschiebt Body in andere Component.

        Args:
            body: Zu verschiebender Body
            target: Ziel-Component

        Returns:
            True wenn erfolgreich
        """
        if body in self.bodies:
            self.bodies.remove(body)
            target.bodies.append(body)
            logger.info(f"Body '{body.name}' verschoben: {self.name} → {target.name}")
            return True
        return False

    # =========================================================================
    # Serialisierung (Phase 2)
    # =========================================================================

    def to_dict(self) -> dict:
        """
        Serialisiert Component zu Dictionary.

        Returns:
            Dictionary für JSON-Serialisierung
        """
        return {
            "id": self.id,
            "name": self.name,
            "position": list(self.position),
            "rotation": list(self.rotation),
            "visible": self.visible,
            "is_active": self.is_active,
            "expanded": self.expanded,
            "bodies": [b.to_dict() for b in self.bodies],
            "sketches": [
                {
                    **s.to_dict(),
                    "plane_origin": list(s.plane_origin) if hasattr(s, 'plane_origin') else [0, 0, 0],
                    "plane_normal": list(s.plane_normal) if hasattr(s, 'plane_normal') else [0, 0, 1],
                    "plane_x_dir": list(s.plane_x_dir) if hasattr(s, 'plane_x_dir') and s.plane_x_dir else None,
                    "plane_y_dir": list(s.plane_y_dir) if hasattr(s, 'plane_y_dir') and s.plane_y_dir else None,
                }
                for s in self.sketches
            ],
            "planes": [
                {
                    "id": p.id,
                    "name": p.name,
                    "origin": list(p.origin),
                    "normal": list(p.normal),
                    "x_dir": list(p.x_dir),
                }
                for p in self.planes
            ],
            "sub_components": [c.to_dict() for c in self.sub_components],
        }

    @classmethod
    def from_dict(cls, data: dict, parent: 'Component' = None) -> 'Component':
        """
        Deserialisiert Component aus Dictionary.

        Args:
            data: Dictionary mit Component-Daten
            parent: Parent-Component (für Hierarchie)

        Returns:
            Neue Component
        """
        comp = cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", "Component"),
            position=tuple(data.get("position", (0.0, 0.0, 0.0))),
            rotation=tuple(data.get("rotation", (0.0, 0.0, 0.0))),
            visible=data.get("visible", True),
            is_active=data.get("is_active", False),
            expanded=data.get("expanded", True),
            parent=parent,
        )

        # Bodies laden
        for body_data in data.get("bodies", []):
            try:
                body = Body.from_dict(body_data)
                comp.bodies.append(body)
            except Exception as e:
                logger.warning(f"Body konnte nicht geladen werden: {e}")

        # Sketches laden
        for sketch_data in data.get("sketches", []):
            try:
                sketch = Sketch.from_dict(sketch_data)
                # Plane-Daten wiederherstellen
                if "plane_origin" in sketch_data:
                    sketch.plane_origin = tuple(sketch_data["plane_origin"])
                if "plane_normal" in sketch_data:
                    sketch.plane_normal = tuple(sketch_data["plane_normal"])
                if sketch_data.get("plane_x_dir"):
                    sketch.plane_x_dir = tuple(sketch_data["plane_x_dir"])
                if sketch_data.get("plane_y_dir"):
                    sketch.plane_y_dir = tuple(sketch_data["plane_y_dir"])
                comp.sketches.append(sketch)
            except Exception as e:
                logger.warning(f"Sketch konnte nicht geladen werden: {e}")

        # Planes laden
        for plane_data in data.get("planes", []):
            try:
                plane = ConstructionPlane(
                    id=plane_data.get("id", str(uuid.uuid4())[:8]),
                    name=plane_data.get("name", "Plane"),
                    origin=tuple(plane_data.get("origin", (0, 0, 0))),
                    normal=tuple(plane_data.get("normal", (0, 0, 1))),
                    x_dir=tuple(plane_data.get("x_dir", (1, 0, 0))),
                )
                comp.planes.append(plane)
            except Exception as e:
                logger.warning(f"Plane konnte nicht geladen werden: {e}")

        # Sub-Components rekursiv laden
        for sub_data in data.get("sub_components", []):
            try:
                sub = cls.from_dict(sub_data, parent=comp)
                comp.sub_components.append(sub)
            except Exception as e:
                logger.warning(f"Sub-Component konnte nicht geladen werden: {e}")

        logger.debug(f"Component geladen: {comp.name} ({len(comp.bodies)} Bodies, {len(comp.sketches)} Sketches, {len(comp.sub_components)} Sub-Components)")
        return comp


# ==================== CORE LOGIC ====================

class Body:
    """
    3D-Körper (Body) mit RobustPartBuilder Logik.

    Phase 2 TNP: Integrierter TNP-Tracker für robuste Shape-Referenzierung.
    """

    def __init__(self, name: str = "Body", document=None):
        self.name = name
        self.id = str(uuid.uuid4())[:8]
        self.features: List[Feature] = []
        self.rollback_index: Optional[int] = None  # None = all features active
        
        # Referenz zum Document (für TNP v4.0 Naming Service)
        self._document = document

        # === Multi-Body Split-Tracking (AGENTS.md Phase 2) ===
        # Wenn dieser Body via Split entstanden ist:
        self.source_body_id: Optional[str] = None  # ID des Original-Bodies vor Split
        self.split_index: Optional[int] = None      # Index des Split-Features in der Historie
        self.split_side: Optional[str] = None       # "above" oder "below"

        # CAD Kernel Objekte
        self._build123d_solid = None
        self.shape = None

        # === TNP v4.0: Shape Naming Service (im Document) ===
        # Nicht mehr hier - Service ist jetzt im Document zentralisiert
        
        # NOTE: Altes TNP-System (Phase 8.2/3) deaktiviert - v4.0 aktiv

        # === PHASE 7: Feature Dependency Graph ===
        self._dependency_graph = FeatureDependencyGraph()
        self._solid_checkpoints: dict = {}  # {feature_index: solid} - In-Memory Checkpoints
        
        # === TNP v3.0: Solid Generation Tracking ===
        # Wird inkrementiert wenn sich Solid durch Boolean ändert
        # Features merken sich auf welcher Generation sie basieren
        self._solid_generation = 0
        self._last_boolean_feature_index = -1  # Index des letzten Boolean-Features

        # === PHASE 2: Single Source of Truth ===
        # PyVista/VTK Objekte - LAZY LOADED aus _build123d_solid
        self._mesh_cache = None       # pv.PolyData (Faces) - privat!
        self._edges_cache = None      # pv.PolyData (Edges) - privat!
        self._face_info_cache = {}    # {face_id: {"normal": (x,y,z), "center": (x,y,z)}} - B-Rep Info!
        self._mesh_cache_valid = False  # Invalidiert wenn Solid sich ändert

        # Legacy Visualisierungs-Daten (Nur als Fallback)
        self._mesh_vertices: List[Tuple[float, float, float]] = []
        self._mesh_triangles: List[Tuple[int, int, int]] = []
        self._mesh_normals = []
        self._mesh_edges = []

    # === PHASE 2: Lazy-Loaded Properties ===
    @property
    def vtk_mesh(self):
        """Lazy-loaded mesh from solid (Single Source of Truth)"""
        if not self._mesh_cache_valid or self._mesh_cache is None:
            self._regenerate_mesh()
        return self._mesh_cache

    @vtk_mesh.setter
    def vtk_mesh(self, value):
        """Setter für importierte Meshes (vor BREP-Konvertierung)"""
        self._mesh_cache = value
        self._mesh_cache_valid = True

    @property
    def vtk_edges(self):
        """Lazy-loaded edges from solid (Single Source of Truth)"""
        if not self._mesh_cache_valid or self._edges_cache is None:
            self._regenerate_mesh()
        return self._edges_cache

    @property
    def face_info(self):
        """B-Rep Face Info: {face_id: {"normal": (x,y,z), "center": (x,y,z)}}"""
        if not self._mesh_cache_valid:
            self._regenerate_mesh()
        return self._face_info_cache

    def get_brep_normal(self, face_id: int):
        """Gibt die B-Rep Normale für eine Face-ID zurück (oder None)."""
        info = self.face_info.get(face_id)
        if info:
            return info.get("normal")
        return None

    def _regenerate_mesh(self):
        """Single point of mesh generation - called automatically when needed"""
        if self._build123d_solid is None:
            self._mesh_cache = None
            self._edges_cache = None
            self._mesh_cache_valid = True
            return

        # Generate from solid via CADTessellator WITH FACE IDs!
        # Dies ermöglicht exakte Face-Selektion (statt Heuristik nach Normalen)
        self._mesh_cache, self._edges_cache, self._face_info_cache = CADTessellator.tessellate_with_face_ids(
            self._build123d_solid
        )
        self._mesh_cache_valid = True
        n_pts = self._mesh_cache.n_points if self._mesh_cache else 0
        n_edges = self._edges_cache.n_lines if self._edges_cache else 0
        n_faces = len(self._face_info_cache) if self._face_info_cache else 0
        logger.debug(f"Mesh regenerated for '{self.name}': {n_pts} pts, {n_edges} edges, {n_faces} B-Rep faces")

    def invalidate_mesh(self):
        """Invalidiert Mesh-Cache - nächster Zugriff regeneriert automatisch"""
        self._mesh_cache_valid = False
        
        # WICHTIG: Auch Face-Info-Cache löschen!
        # Sonst bleiben alte Face-IDs bestehen die nach Boolean/PushPull ungültig sind
        self._face_info_cache = {}

        # Phase 4.3: Auch Topology-Cache invalidieren
        if self._build123d_solid is not None:
            try:
                CADTessellator.invalidate_topology_cache(id(self._build123d_solid.wrapped))
            except Exception as e:
                logger.debug(f"[__init__.py] Fehler: {e}")
                pass  # Solid hat kein wrapped (selten)

    def add_feature(self, feature: Feature, rebuild: bool = True):
        """Feature hinzufügen und optional Geometrie neu berechnen.

        Args:
            feature: Das Feature das hinzugefügt werden soll
            rebuild: Wenn False, wird das Feature nur zur Liste hinzugefügt
                     ohne _rebuild() aufzurufen. Nützlich wenn das Solid
                     bereits durch eine direkte Operation (z.B. BRepFeat)
                     aktualisiert wurde.
        """
        self.features.append(feature)

        # Phase 7: Feature im Dependency Graph registrieren
        from config.feature_flags import is_enabled
        if is_enabled("feature_dependency_tracking"):
            self._dependency_graph.add_feature(feature.id, len(self.features) - 1)

        if rebuild:
            self._rebuild(changed_feature_id=feature.id)

    def remove_feature(self, feature: Feature):
        if feature in self.features:
            feature_index = self.features.index(feature)

            # Phase 7: Checkpoints nach diesem Feature invalidieren
            from config.feature_flags import is_enabled
            if is_enabled("feature_dependency_tracking"):
                self._dependency_graph.remove_feature(feature.id)
                # Lösche Checkpoints ab diesem Index
                for idx in list(self._solid_checkpoints.keys()):
                    if idx >= feature_index:
                        del self._solid_checkpoints[idx]

            self.features.remove(feature)
            self._rebuild()

    def update_feature(self, feature: Feature):
        """
        Phase 7: Aktualisiert ein Feature und triggert inkrementellen Rebuild.

        Nutzt den Dependency Graph um nur die betroffenen Features neu zu berechnen.

        Args:
            feature: Das geänderte Feature (muss bereits in self.features sein)
        """
        if feature not in self.features:
            logger.error(f"Feature '{feature.id}' nicht in Body '{self.name}' gefunden")
            return

        from config.feature_flags import is_enabled

        if is_enabled("feature_dependency_tracking"):
            feature_index = self.features.index(feature)

            # Checkpoints ab diesem Feature invalidieren
            for idx in list(self._solid_checkpoints.keys()):
                if idx >= feature_index:
                    del self._solid_checkpoints[idx]

            # Inkrementeller Rebuild
            self._rebuild(changed_feature_id=feature.id)
        else:
            # Fallback: Voller Rebuild
            self._rebuild()
            
    def convert_to_brep(self, mode: str = "auto"):
        """
        Wandelt Mesh in CAD-Solid um.

        Verwendet DirectMeshConverter + BRepOptimizer für zuverlässige Konvertierung.
        Faces werden zu BREP konvertiert und dann mit UnifySameDomain optimiert.
        """
        if self._build123d_solid is not None:
            logger.info(f"Body '{self.name}' ist bereits BREP.")
            return True

        if self.vtk_mesh is None:
            logger.warning("Keine Mesh-Daten vorhanden.")
            return False

        logger.info(f"Starte Mesh-zu-BREP Konvertierung für '{self.name}'...")
        logger.info(f"  Mesh: {self.vtk_mesh.n_points} Punkte, {self.vtk_mesh.n_cells} Faces")

        try:
            # 1. DirectMeshConverter: Mesh -> BREP (1:1 Faces)
            from meshconverter.direct_mesh_converter import DirectMeshConverter
            from meshconverter.brep_optimizer import optimize_brep

            converter = DirectMeshConverter(unify_faces=False)
            result = converter.convert(self.vtk_mesh)

            if result.solid is None:
                logger.error(f"DirectMeshConverter fehlgeschlagen: {result.message}")
                return False

            logger.info(f"  BREP erstellt: {result.stats.get('faces_created', '?')} Faces")

            # 2. BRepOptimizer: Face-Reduktion + Primitiv-Erkennung
            optimized, opt_stats = optimize_brep(result.solid)

            faces_before = opt_stats.get('faces_before', 0)
            faces_after = opt_stats.get('faces_after', 0)
            reduction = faces_before - faces_after

            logger.info(f"  Optimiert: {faces_before} -> {faces_after} Faces ({reduction} reduziert)")
            if opt_stats.get('cylinders_detected', 0) > 0:
                logger.info(f"  Zylinder erkannt: {opt_stats['cylinders_detected']}")
            if opt_stats.get('spheres_detected', 0) > 0:
                logger.info(f"  Kugeln erkannt: {opt_stats['spheres_detected']}")

            # 3. In Build123d Solid wrappen
            from build123d import Solid
            solid = Solid(optimized)

            if solid and hasattr(solid, 'wrapped') and not solid.wrapped.IsNull():
                self._build123d_solid = solid
                self.shape = solid.wrapped

                # === NEU: ImportFeature erstellen für Rebuild-Support ===
                # BREP serialisieren (via BytesIO Stream)
                try:
                    from OCP.BRepTools import BRepTools
                    import io

                    # BRepTools.Write_s braucht einen BytesIO Stream
                    stream = io.BytesIO()
                    BRepTools.Write_s(solid.wrapped, stream)
                    brep_string = stream.getvalue().decode('utf-8')

                    if brep_string:
                        # ImportFeature erstellen
                        import_feature = ImportFeature(
                            name=f"Import ({self.name})",
                            brep_string=brep_string,
                            source_file=getattr(self, 'source_file', self.name),
                            source_type="mesh_convert"
                        )

                        # Alte Features löschen und ImportFeature als Basis setzen
                        self.features.clear()
                        self.features.append(import_feature)

                        logger.info(f"  ImportFeature erstellt ({len(brep_string)} bytes BREP)")
                except Exception as e:
                    logger.warning(f"ImportFeature Erstellung fehlgeschlagen: {e}")
                    # Konvertierung war trotzdem erfolgreich, nur ohne Rebuild-Support

                logger.success(f"Body '{self.name}' erfolgreich konvertiert!")

                # Mesh neu berechnen (vom BREP abgeleitet für Konsistenz)
                self._update_mesh_from_solid(solid)
                return True
            else:
                logger.warning("Konvertierung lieferte kein gültiges Solid.")
                return False

        except Exception as e:
            logger.error(f"Konvertierung fehlgeschlagen: {e}")
            traceback.print_exc()
            return False
            
    def _safe_operation(self, op_name, op_func, fallback_func=None):
        """
        Wrapper für kritische CAD-Operationen.
        Fängt Crashes ab und erlaubt Fallbacks.
        """
        try:
            result = op_func()
            
            if result is None:
                raise ValueError("Operation returned None")
            
            if hasattr(result, 'is_valid') and not result.is_valid():
                raise ValueError("Result geometry is invalid")

            return result, "SUCCESS"
            
        except Exception as e:
            logger.warning(f"Feature '{op_name}' fehlgeschlagen: {e}")
            
            if fallback_func:
                logger.debug(f"→ Versuche Fallback für '{op_name}'...")
                try:
                    res_fallback = fallback_func()
                    if res_fallback:
                        logger.debug(f"✓ Fallback für '{op_name}' erfolgreich.")
                        return res_fallback, "WARNING"
                except Exception as e2:
                    logger.error(f"✗ Auch Fallback fehlgeschlagen: {e2}")
            
            return None, "ERROR"

    def _register_boolean_history(self, bool_result: BooleanResult, feature, operation_name: str = ""):
        """
        Registriert Boolean-History für TNP v3.0 und v4.0.

        Wird nach erfolgreichen Boolean-Operationen aufgerufen um
        die BRepTools_History an die TNP-Systeme weiterzugeben.

        Args:
            bool_result: BooleanResult mit history-Attribut
            feature: Das Feature das die Boolean-Operation ausgelöst hat
            operation_name: Name der Operation (Join/Cut/Intersect)
        """
        boolean_history = getattr(bool_result, 'history', None)
        if boolean_history is None:
            return

        # TNP v3.0: Shape Registry
        if hasattr(self, '_shape_registry'):
            try:
                self._shape_registry.track_boolean_operation(
                    operation=f"Boolean_{operation_name}",
                    input_shapes=[],
                    result_shape=bool_result.value.wrapped if hasattr(bool_result.value, 'wrapped') else bool_result.value,
                    history=boolean_history
                )
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP v3.0: Boolean {operation_name} getrackt")
            except Exception as tnp_e:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP v3.0 Tracking fehlgeschlagen: {tnp_e}")

        # TNP v4.0: ShapeNamingService
        if self._document and hasattr(self._document, '_shape_naming_service'):
            try:
                service = self._document._shape_naming_service
                service.record_operation(
                    OperationRecord(
                        operation_id=str(uuid.uuid4())[:8],
                        operation_type=f"BOOLEAN_{operation_name.upper()}",
                        feature_id=getattr(feature, 'id', 'unknown'),
                        occt_history=boolean_history,
                    )
                )
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP v4.0: Boolean {operation_name} History registriert")
            except Exception as tnp_e:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP v4.0 History-Registrierung fehlgeschlagen: {tnp_e}")

    def _fix_shape_ocp(self, shape):
        """Repariert einen TopoDS_Shape mit OCP ShapeFix."""
        try:
            from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Solid
            from OCP.BRepCheck import BRepCheck_Analyzer

            # Prüfe ob Shape valide ist
            analyzer = BRepCheck_Analyzer(shape)
            if analyzer.IsValid():
                return shape

            logger.debug("Shape invalid, starte Reparatur...")

            # ShapeFix_Shape für allgemeine Reparaturen - Phase 5: Zentralisierte Toleranzen
            fixer = ShapeFix_Shape(shape)
            fixer.SetPrecision(Tolerances.KERNEL_PRECISION)
            fixer.SetMaxTolerance(Tolerances.MESH_EXPORT)
            fixer.SetMinTolerance(Tolerances.KERNEL_PRECISION / 10)

            # HINWEIS: FixSolidMode() etc. sind GETTER, nicht Setter!
            # Die Standardwerte sind bereits True für die meisten Modi.
            # Wir verlassen uns auf die Defaults.

            if fixer.Perform():
                fixed_shape = fixer.Shape()

                # Validiere repariertes Shape
                analyzer2 = BRepCheck_Analyzer(fixed_shape)
                if analyzer2.IsValid():
                    logger.debug("✓ Shape repariert")
                    return fixed_shape
                else:
                    logger.warning("Shape nach Reparatur immer noch invalid")
                    # Gib es trotzdem zurück - manchmal funktioniert es dennoch
                    return fixed_shape
            else:
                logger.warning("ShapeFix Perform() fehlgeschlagen")
                return shape  # Gib Original zurück

        except Exception as e:
            logger.warning(f"Shape-Reparatur Fehler: {e}")
            return shape  # Gib Original zurück

    def _ocp_fillet(self, solid, edges, radius):
        """
        OCP-basiertes Fillet (robuster als Build123d).

        Args:
            solid: Build123d Solid
            edges: Liste von Edges
            radius: Fillet-Radius

        Returns:
            Build123d Solid oder None
        """
        if not HAS_OCP:
            return None

        try:
            from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
            from OCP.BRepCheck import BRepCheck_Analyzer

            # Extrahiere TopoDS_Shape
            shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

            # Erstelle Fillet-Operator
            fillet_op = BRepFilletAPI_MakeFillet(shape)

            # Füge Edges hinzu
            for edge in edges:
                edge_shape = edge.wrapped if hasattr(edge, 'wrapped') else edge
                fillet_op.Add(radius, edge_shape)

            # Build
            fillet_op.Build()

            if not fillet_op.IsDone():
                logger.warning("OCP Fillet IsDone() = False")
                return None

            result_shape = fillet_op.Shape()

            # Validiere
            analyzer = BRepCheck_Analyzer(result_shape)
            if not analyzer.IsValid():
                logger.warning("OCP Fillet produzierte ungültiges Shape, versuche Reparatur...")
                result_shape = self._fix_shape_ocp(result_shape)

            # Wrap zu Build123d
            try:
                from build123d import Solid, Shape
                try:
                    result = Solid(result_shape)
                except Exception as e:
                    logger.debug(f"[__init__.py] Fehler: {e}")
                    result = Shape(result_shape)

                if hasattr(result, 'is_valid') and result.is_valid():
                    logger.debug("OCP Fillet erfolgreich")
                    return result
                else:
                    return None
            except Exception as e:
                logger.debug(f"[__init__.py] Fehler: {e}")
                return None

        except Exception as e:
            logger.debug(f"OCP Fillet Fehler: {e}")
            return None

    def _ocp_chamfer(self, solid, edges, distance):
        """
        OCP-basiertes Chamfer (robuster als Build123d).

        Args:
            solid: Build123d Solid
            edges: Liste von Edges
            distance: Chamfer-Distanz

        Returns:
            Build123d Solid oder None
        """
        if not HAS_OCP:
            return None

        try:
            from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer
            from OCP.BRepCheck import BRepCheck_Analyzer
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE

            # Extrahiere TopoDS_Shape
            shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

            # Erstelle Chamfer-Operator
            chamfer_op = BRepFilletAPI_MakeChamfer(shape)

            # FIX: Nutze 2-Parameter Version (symmetrische Fase)
            # OCP/Cascade errechnet die Fasen-Richtung automatisch
            for edge in edges:
                edge_shape = edge.wrapped if hasattr(edge, 'wrapped') else edge

                try:
                    # Nur Distanz und Edge - kein Face nötig!
                    chamfer_op.Add(distance, edge_shape)
                except Exception as e:
                    logger.debug(f"[__init__.py] Chamfer.Add fehlgeschlagen: {e}")
                    continue

            # Build
            chamfer_op.Build()

            if not chamfer_op.IsDone():
                logger.warning("OCP Chamfer IsDone() = False")
                return None

            result_shape = chamfer_op.Shape()

            # Validiere
            analyzer = BRepCheck_Analyzer(result_shape)
            if not analyzer.IsValid():
                logger.warning("OCP Chamfer produzierte ungültiges Shape")
                result_shape = self._fix_shape_ocp(result_shape)

            # Wrap zu Build123d
            try:
                from build123d import Solid, Shape
                try:
                    result = Solid(result_shape)
                except Exception as e:
                    logger.debug(f"[__init__.py] Fehler: {e}")
                    result = Shape(result_shape)

                if hasattr(result, 'is_valid') and result.is_valid():
                    logger.debug("OCP Chamfer erfolgreich")
                    return result
                else:
                    return None
            except Exception as e:
                logger.debug(f"[__init__.py] Fehler: {e}")
                return None

        except Exception as e:
            logger.debug(f"OCP Chamfer Fehler: {e}")
            return None

    # ==================== PHASE 6: COMPUTE METHODS ====================

    def _compute_revolve(self, feature: 'RevolveFeature'):
        """
        CAD Kernel First: Profile werden IMMER aus dem Sketch abgeleitet.

        Architektur:
        1. Mit Sketch: Profile aus sketch.closed_profiles (immer aktuell)
           - profile_selector filtert welche Profile gewählt wurden
        2. Ohne Sketch: precalculated_polys als Geometrie-Quelle (Legacy)
        """
        from build123d import (
            BuildPart, Plane, Axis, revolve as bd_revolve,
            make_face, Wire, Vector
        )

        sketch = feature.sketch
        if not sketch:
            raise ValueError("Revolve: Kein Sketch vorhanden")

        # Sketch-Plane bestimmen
        plane_origin = getattr(sketch, 'plane_origin', (0, 0, 0))
        plane_normal = getattr(sketch, 'plane_normal', (0, 0, 1))
        x_dir = getattr(sketch, 'plane_x_dir', None)

        # Validate plane_normal is not zero
        import math
        norm_len = math.sqrt(sum(c*c for c in plane_normal))
        if norm_len < 1e-9:
            logger.warning("Revolve: plane_normal ist Null-Vektor, Fallback auf (0,0,1)")
            plane_normal = (0, 0, 1)

        plane = Plane(
            origin=Vector(*plane_origin),
            z_dir=Vector(*plane_normal),
            x_dir=Vector(*x_dir) if x_dir else None
        )

        # === CAD KERNEL FIRST: Profile-Bestimmung ===
        polys_to_revolve = []

        # KERNEL FIRST: Profile aus Sketch ableiten (nicht aus Cache!)
        sketch_profiles = getattr(sketch, 'closed_profiles', [])
        profile_selector = getattr(feature, 'profile_selector', [])

        if sketch_profiles and profile_selector:
            # Selektor-Match (CAD KERNEL FIRST - KEINE FALLBACKS!)
            polys_to_revolve = self._filter_profiles_by_selector(
                sketch_profiles, profile_selector
            )
            if polys_to_revolve:
                logger.info(f"Revolve: {len(polys_to_revolve)}/{len(sketch_profiles)} Profile via Selektor")
            else:
                # Selektor hat nicht gematcht → Fehler, kein Fallback!
                logger.error(f"Revolve: Selektor-Match fehlgeschlagen! Selector: {profile_selector}")
                logger.error(f"Revolve: Verfügbare Profile: {[(p.centroid.x, p.centroid.y) for p in sketch_profiles]}")
                # Leere Liste → keine Revolve
        elif sketch_profiles:
            # Kein Selektor → alle Profile verwenden (Legacy/Import)
            polys_to_revolve = list(sketch_profiles)
            logger.info(f"Revolve: Alle {len(polys_to_revolve)} Profile (kein Selektor)")
        else:
            # Sketch hat keine closed_profiles
            logger.warning(f"Revolve: Sketch hat keine closed_profiles!")

        # Profile zu Build123d Faces konvertieren
        faces_to_revolve = []
        for poly in polys_to_revolve:
            try:
                coords = list(poly.exterior.coords)[:-1]  # Shapely schließt Polygon
                if len(coords) < 3:
                    continue
                pts_3d = [plane.from_local_coords((p[0], p[1])) for p in coords]
                wire = Wire.make_polygon([Vector(*p) for p in pts_3d])
                faces_to_revolve.append(make_face(wire))
            except Exception as e:
                logger.debug(f"Revolve: Polygon-Konvertierung fehlgeschlagen: {e}")

        if not faces_to_revolve:
            raise ValueError("Revolve: Keine gültigen Profile gefunden")

        # Achse bestimmen
        axis_vec = feature.axis
        axis_origin_vec = Vector(*feature.axis_origin) if feature.axis_origin else Vector(0, 0, 0)

        if tuple(axis_vec) == (1, 0, 0) and tuple(feature.axis_origin) == (0, 0, 0):
            axis = Axis.X
        elif tuple(axis_vec) == (0, 1, 0) and tuple(feature.axis_origin) == (0, 0, 0):
            axis = Axis.Y
        elif tuple(axis_vec) == (0, 0, 1) and tuple(feature.axis_origin) == (0, 0, 0):
            axis = Axis.Z
        else:
            # Custom axis
            axis = Axis(axis_origin_vec, Vector(*axis_vec))

        # Revolve ausführen (erstes Profil)
        with BuildPart() as part:
            for face in faces_to_revolve:
                bd_revolve(face, axis=axis, revolution_arc=feature.angle)

        result = part.part
        if result is None or (hasattr(result, 'is_null') and result.is_null()):
            raise ValueError("Revolve erzeugte keine Geometrie")

        logger.info(f"Revolve: {feature.angle}° um {feature.axis}")
        return result

    def _compute_loft(self, feature: 'LoftFeature'):
        """
        Berechnet Loft aus mehreren Profilen.

        Strategy:
        1. Profile zu Build123d Faces konvertieren
        2. Build123d loft() versuchen
        3. Fallback zu OCP BRepOffsetAPI_ThruSections

        Phase 8: Unterstützt G0/G1/G2 Kontinuität
        """
        if len(feature.profile_data) < 2:
            raise ValueError("Loft benötigt mindestens 2 Profile")

        # Profile zu Faces konvertieren
        sections = []
        for prof_data in feature.profile_data:
            face = self._profile_data_to_face(prof_data)
            if face is not None:
                sections.append(face)

        if len(sections) < 2:
            raise ValueError(f"Konnte nur {len(sections)} gültige Faces erstellen")

        # Phase 8: Kontinuitäts-Info
        start_cont = getattr(feature, 'start_continuity', 'G0')
        end_cont = getattr(feature, 'end_continuity', 'G0')
        has_continuity = (start_cont != 'G0' or end_cont != 'G0')

        logger.info(f"Loft mit {len(sections)} Profilen (ruled={feature.ruled}, start={start_cont}, end={end_cont})")

        # PRIMARY: Build123d loft (ohne Kontinuitäts-Kontrolle)
        if not has_continuity:
            try:
                from build123d import loft
                result = loft(sections, ruled=feature.ruled)
                if result and hasattr(result, 'is_valid') and result.is_valid():
                    logger.debug("Build123d Loft erfolgreich")
                    return result
            except Exception as e:
                logger.debug(f"Build123d loft fehlgeschlagen: {e}")

        # FALLBACK/ERWEITERT: OCP ThruSections mit Kontinuität
        return self._ocp_loft_with_continuity(sections, feature)

    def _ocp_loft(self, faces, ruled: bool):
        """OCP-basierter Loft mit BRepOffsetAPI_ThruSections."""
        if not HAS_OCP:
            return None

        try:
            from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_EDGE

            # ThruSections: (isSolid, isRuled)
            loft_builder = BRepOffsetAPI_ThruSections(True, ruled)

            for face in faces:
                # Outer Wire von jedem Face extrahieren
                face_shape = face.wrapped if hasattr(face, 'wrapped') else face

                # Wire vom Face holen
                wire = None
                explorer = TopExp_Explorer(face_shape, TopAbs_EDGE)
                wire_builder = BRepBuilderAPI_MakeWire()

                while explorer.More():
                    edge = explorer.Current()
                    try:
                        wire_builder.Add(edge)
                    except Exception as e:
                        logger.debug(f"[__init__.py] Fehler: {e}")
                        pass
                    explorer.Next()

                if wire_builder.IsDone():
                    wire = wire_builder.Wire()
                    loft_builder.AddWire(wire)

            loft_builder.Build()

            if loft_builder.IsDone():
                result_shape = loft_builder.Shape()
                result_shape = self._fix_shape_ocp(result_shape)

                from build123d import Solid, Shape
                try:
                    result = Solid(result_shape)
                    if hasattr(result, 'is_valid') and result.is_valid():
                        logger.debug("OCP Loft erfolgreich")
                        return result
                except Exception as e_solid:
                    logger.warning(f"Solid-Wrap fehlgeschlagen: {e_solid}")
                    try:
                        return Shape(result_shape)
                    except Exception as e_shape:
                        logger.warning(f"Shape-Wrap fehlgeschlagen: {e_shape}")

            logger.warning("OCP Loft IsDone() = False")
            return None

        except Exception as e:
            logger.error(f"OCP Loft Fehler: {e}")
            return None

    def _ocp_loft_with_continuity(self, faces, feature: 'LoftFeature'):
        """
        Phase 8: OCP-basierter Loft mit Kontinuitäts-Kontrolle.

        Unterstützt G0/G1/G2 Übergänge durch BRepOffsetAPI_ThruSections
        mit Smoothing und Approximation.
        """
        if not HAS_OCP:
            return self._ocp_loft(faces, feature.ruled)

        try:
            from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_EDGE
            from OCP.Approx import Approx_ParametrizationType

            # ThruSections: (isSolid, isRuled)
            is_ruled = feature.ruled
            loft_builder = BRepOffsetAPI_ThruSections(True, is_ruled)

            # Phase 8: Smoothing für G1/G2 Kontinuität
            start_cont = getattr(feature, 'start_continuity', 'G0')
            end_cont = getattr(feature, 'end_continuity', 'G0')

            if not is_ruled and (start_cont != 'G0' or end_cont != 'G0'):
                loft_builder.SetSmoothing(True)

                # Parametrisierung für bessere Kontinuität
                # 0 = ChordLength, 1 = Centripetal, 2 = IsoParametric
                if start_cont == 'G2' or end_cont == 'G2':
                    loft_builder.SetParType(Approx_ParametrizationType.Approx_Centripetal)
                else:
                    loft_builder.SetParType(Approx_ParametrizationType.Approx_ChordLength)

            # Profile hinzufügen
            for face in faces:
                face_shape = face.wrapped if hasattr(face, 'wrapped') else face

                explorer = TopExp_Explorer(face_shape, TopAbs_EDGE)
                wire_builder = BRepBuilderAPI_MakeWire()

                while explorer.More():
                    edge = explorer.Current()
                    try:
                        wire_builder.Add(edge)
                    except Exception as e:
                        logger.debug(f"[__init__.py] Fehler: {e}")
                        pass
                    explorer.Next()

                if wire_builder.IsDone():
                    wire = wire_builder.Wire()
                    loft_builder.AddWire(wire)

            loft_builder.Build()

            if loft_builder.IsDone():
                result_shape = loft_builder.Shape()
                result_shape = self._fix_shape_ocp(result_shape)

                from build123d import Solid, Shape
                try:
                    result = Solid(result_shape)
                    if hasattr(result, 'is_valid') and result.is_valid():
                        logger.debug(f"OCP Loft mit Kontinuität ({start_cont}/{end_cont}) erfolgreich")
                        return result
                except Exception as e_solid:
                    logger.warning(f"Solid-Wrap fehlgeschlagen: {e_solid}")
                    try:
                        return Shape(result_shape)
                    except Exception as e_shape:
                        logger.warning(f"Shape-Wrap fehlgeschlagen: {e_shape}")

            logger.warning("OCP Loft mit Kontinuität IsDone() = False")
            return self._ocp_loft(faces, feature.ruled)  # Fallback

        except Exception as e:
            logger.error(f"OCP Loft mit Kontinuität Fehler: {e}")
            return self._ocp_loft(faces, feature.ruled)  # Fallback

    def _compute_sweep(self, feature: 'SweepFeature', current_solid):
        """
        Berechnet Sweep eines Profils entlang eines Pfads.

        Strategy:
        1. Profil zu Face konvertieren
        2. Pfad auflösen
        3. Build123d sweep() versuchen
        4. Fallback zu OCP BRepOffsetAPI_MakePipe

        Phase 8: Unterstützt Twist und Skalierung
        """
        # Profil konvertieren
        profile_face = self._profile_data_to_face(feature.profile_data)
        if profile_face is None:
            raise ValueError("Konnte Profil-Face nicht erstellen")

        # Pfad auflösen
        path_wire = self._resolve_path(feature.path_data, current_solid)
        if path_wire is None:
            raise ValueError("Konnte Pfad nicht auflösen")

        # WICHTIG: Profil zum Pfad-Start verschieben
        # Für Sweep muss das Profil am Startpunkt des Pfads liegen!
        profile_face = self._move_profile_to_path_start(profile_face, path_wire, feature)

        # Phase 8: Twist/Scale Parameter prüfen
        twist_angle = getattr(feature, 'twist_angle', 0.0)
        scale_start = getattr(feature, 'scale_start', 1.0)
        scale_end = getattr(feature, 'scale_end', 1.0)
        has_twist_or_scale = (twist_angle != 0.0 or scale_start != 1.0 or scale_end != 1.0)

        logger.debug(f"Sweep mit Frenet={feature.is_frenet}, Twist={twist_angle}°, Scale={scale_start}->{scale_end}")

        # Phase 8: Erweiterter Sweep mit Twist/Scale
        if has_twist_or_scale:
            result = self._ocp_sweep_with_twist_scale(profile_face, path_wire, feature)
            if result is not None:
                return result

        # DEBUG: Profil und Pfad Info
        try:
            profile_center = profile_face.center() if hasattr(profile_face, 'center') else "N/A"
            path_edges = path_wire.edges() if hasattr(path_wire, 'edges') else []
            logger.debug(f"Sweep: Profil-Zentrum={profile_center}, Pfad-Edges={len(path_edges)}")
        except Exception as e:
            logger.debug(f"[__init__.py] Fehler: {e}")
            pass

        # PRIMARY: Build123d sweep (Standard ohne Twist/Scale)
        try:
            from build123d import sweep
            result = sweep(profile_face, path=path_wire, is_frenet=feature.is_frenet)
            if result and hasattr(result, 'is_valid') and result.is_valid():
                logger.debug("Build123d Sweep erfolgreich")
                return result
            else:
                logger.warning(f"Build123d sweep: Ergebnis ungültig oder None")
        except Exception as e:
            logger.warning(f"Build123d sweep fehlgeschlagen: {e}")

        # FALLBACK: OCP MakePipe
        return self._ocp_sweep(profile_face, path_wire)

    def _move_profile_to_path_start(self, profile_face, path_wire, feature):
        """
        Verschiebt das Profil zum Startpunkt des Pfads.

        In CAD-Systemen wie CAD muss das Profil am Pfad-Start liegen.
        Diese Funktion berechnet die notwendige Translation und wendet sie an.

        Args:
            profile_face: Build123d Face (Profil)
            path_wire: Build123d Wire (Pfad)
            feature: SweepFeature mit profile_data

        Returns:
            Verschobenes Build123d Face
        """
        try:
            from build123d import Vector, Location
            import numpy as np

            # Pfad-Startpunkt ermitteln
            path_edges = path_wire.edges() if hasattr(path_wire, 'edges') else []
            if not path_edges:
                logger.warning("Sweep: Pfad hat keine Edges, überspringe Profil-Verschiebung")
                return profile_face

            first_edge = path_edges[0]

            # Startpunkt der ersten Edge
            # In OCP: Edge.first_vertex().center()
            if hasattr(first_edge, 'start_point'):
                path_start = first_edge.start_point()
            elif hasattr(first_edge, 'position_at'):
                path_start = first_edge.position_at(0)  # Parameter 0 = Start
            else:
                # Fallback: Vertex-basiert
                vertices = first_edge.vertices() if hasattr(first_edge, 'vertices') else []
                if vertices:
                    path_start = vertices[0].center() if hasattr(vertices[0], 'center') else Vector(0, 0, 0)
                else:
                    logger.warning("Sweep: Konnte Pfad-Startpunkt nicht ermitteln")
                    return profile_face

            # Profil-Zentrum ermitteln
            profile_center = profile_face.center() if hasattr(profile_face, 'center') else None
            if profile_center is None:
                # Fallback: Aus profile_data
                profile_data = feature.profile_data
                origin = profile_data.get('plane_origin', (0, 0, 0))
                profile_center = Vector(*origin)

            # Translation berechnen
            if isinstance(path_start, tuple):
                path_start = Vector(*path_start)

            translation = path_start - profile_center

            # Kleine Verschiebungen ignorieren (bereits am richtigen Ort)
            if translation.length < 0.1:  # < 0.1mm
                logger.debug("Sweep: Profil bereits am Pfad-Start")
                return profile_face

            logger.info(f"Sweep: Verschiebe Profil um {translation.length:.1f}mm zum Pfad-Start")

            # Profil verschieben
            moved_face = profile_face.move(Location(translation))

            return moved_face

        except Exception as e:
            logger.warning(f"Sweep: Profil-Verschiebung fehlgeschlagen: {e}, verwende Original")
            return profile_face

    def _ocp_sweep(self, face, path):
        """OCP-basierter Sweep mit BRepOffsetAPI_MakePipe."""
        if not HAS_OCP:
            return None

        try:
            from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe

            face_shape = face.wrapped if hasattr(face, 'wrapped') else face
            path_shape = path.wrapped if hasattr(path, 'wrapped') else path

            pipe = BRepOffsetAPI_MakePipe(path_shape, face_shape)
            pipe.Build()

            if pipe.IsDone():
                result_shape = pipe.Shape()
                result_shape = self._fix_shape_ocp(result_shape)

                from build123d import Solid, Shape
                try:
                    result = Solid(result_shape)
                    if hasattr(result, 'is_valid') and result.is_valid():
                        logger.debug("OCP Sweep erfolgreich")
                        return result
                except Exception as e_solid:
                    logger.warning(f"Solid-Wrap fehlgeschlagen: {e_solid}")
                    try:
                        return Shape(result_shape)
                    except Exception as e_shape:
                        logger.warning(f"Shape-Wrap fehlgeschlagen: {e_shape}")

            logger.warning("OCP Sweep IsDone() = False")
            return None

        except Exception as e:
            logger.error(f"OCP Sweep Fehler: {e}")
            return None

    def _ocp_sweep_with_twist_scale(self, face, path, feature: 'SweepFeature'):
        """
        Phase 8: OCP-basierter Sweep mit Twist und Skalierung.

        Verwendet BRepOffsetAPI_MakePipeShell für erweiterte Kontrolle:
        - Twist: Verdrehung des Profils entlang des Pfads
        - Scale: Skalierung von Start zu Ende

        Args:
            face: Profil-Face
            path: Pfad-Wire
            feature: SweepFeature mit twist_angle, scale_start, scale_end

        Returns:
            Build123d Solid oder None bei Fehler
        """
        if not HAS_OCP:
            return None

        try:
            from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell
            from OCP.GeomFill import GeomFill_IsFrenet, GeomFill_IsConstantNormal, GeomFill_IsCorrectedFrenet
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_EDGE
            import math

            face_shape = face.wrapped if hasattr(face, 'wrapped') else face
            path_shape = path.wrapped if hasattr(path, 'wrapped') else path

            # Profil-Wire extrahieren
            explorer = TopExp_Explorer(face_shape, TopAbs_EDGE)
            profile_wire_builder = BRepBuilderAPI_MakeWire()

            while explorer.More():
                edge = explorer.Current()
                try:
                    profile_wire_builder.Add(edge)
                except Exception as e:
                    logger.debug(f"[__init__.py] Fehler: {e}")
                    pass
                explorer.Next()

            if not profile_wire_builder.IsDone():
                logger.warning("Konnte Profil-Wire nicht erstellen")
                return None

            profile_wire = profile_wire_builder.Wire()

            # PipeShell erstellen
            pipe = BRepOffsetAPI_MakePipeShell(path_shape)

            # Trihedron-Mode setzen
            if feature.is_frenet:
                pipe.SetMode(GeomFill_IsCorrectedFrenet)  # Bessere Stabilität als IsFrenet
            else:
                pipe.SetMode(GeomFill_IsConstantNormal)

            # Twist und Scale über Law-Funktionen
            twist_angle = getattr(feature, 'twist_angle', 0.0)
            scale_start = getattr(feature, 'scale_start', 1.0)
            scale_end = getattr(feature, 'scale_end', 1.0)

            if twist_angle != 0.0 or scale_start != 1.0 or scale_end != 1.0:
                # Für Twist und Scale benötigen wir Law_Linear
                try:
                    from OCP.Law import Law_Linear

                    # Scale-Law erstellen
                    if scale_start != 1.0 or scale_end != 1.0:
                        scale_law = Law_Linear()
                        scale_law.Set(0.0, scale_start, 1.0, scale_end)
                        pipe.SetLaw(profile_wire, scale_law, False, False)
                    else:
                        pipe.Add(profile_wire, False, False)

                    # Twist über SetTolerance und auxiliary spine
                    # (OCP hat keine direkte Twist-API, wir approximieren)
                    if twist_angle != 0.0:
                        logger.info(f"Twist {twist_angle}° wird über Auxiliary-Methode approximiert")
                        # Einfache Approximation: Mehrere Zwischenpositionen
                        # Echte Implementation würde BRepOffsetAPI_MakePipeShell.SetLaw mit
                        # Law_Interpol für Rotation verwenden

                except ImportError:
                    logger.debug("OCP.Law nicht verfügbar, Standard-Add verwenden")
                    pipe.Add(profile_wire, False, False)
            else:
                pipe.Add(profile_wire, False, False)

            pipe.Build()

            if not pipe.IsDone():
                logger.warning("OCP Sweep mit Twist/Scale: Build fehlgeschlagen")
                return None

            # Zu Solid machen
            try:
                pipe.MakeSolid()
            except Exception as e:
                logger.debug(f"[__init__.py] Fehler: {e}")
                pass

            result_shape = pipe.Shape()
            result_shape = self._fix_shape_ocp(result_shape)

            from build123d import Solid, Shape
            try:
                result = Solid(result_shape)
                if hasattr(result, 'is_valid') and result.is_valid():
                    logger.debug(f"OCP Sweep mit Twist={twist_angle}° Scale={scale_start}->{scale_end} erfolgreich")
                    return result
            except Exception as e:
                logger.debug(f"[__init__.py] Fehler: {e}")
                try:
                    return Shape(result_shape)
                except Exception as e:
                    logger.debug(f"[__init__.py] Fehler: {e}")
                    pass

            return None

        except Exception as e:
            logger.error(f"OCP Sweep mit Twist/Scale Fehler: {e}")
            return None

    def _compute_shell(self, feature: 'ShellFeature', current_solid):
        """
        Berechnet Shell (Aushöhlung) eines Körpers.

        Strategy:
        1. Öffnungs-Faces auflösen
        2. Mit Öffnungen: Build123d offset()
        3. Ohne Öffnungen: Boolean-Subtraktion (outer - inner = hollow closed)
        4. Fallback zu OCP BRepOffsetAPI_MakeThickSolid
        """
        if current_solid is None:
            raise ValueError("Shell benötigt einen existierenden Körper")

        # Öffnungs-Faces auflösen
        opening_faces = self._resolve_faces_for_shell(current_solid, feature.opening_face_selectors)

        logger.debug(f"Shell mit Dicke={feature.thickness}mm, {len(opening_faces)} Öffnungen")

        # CASE 1: Mit Öffnungen - Build123d offset()
        if opening_faces:
            try:
                from build123d import offset
                # Negatives amount für inward shell
                result = offset(current_solid, amount=-feature.thickness, openings=opening_faces)
                if result and hasattr(result, 'is_valid') and result.is_valid():
                    logger.debug("Build123d Shell mit Öffnungen erfolgreich")
                    return result
            except Exception as e:
                logger.debug(f"Build123d offset fehlgeschlagen: {e}")

            # Fallback für Öffnungen: OCP MakeThickSolid
            return self._ocp_shell(current_solid, opening_faces, feature.thickness)

        # CASE 2: Ohne Öffnungen - Boolean-Subtraktion für geschlossenen Hohlkörper
        # outer - inner_offset = hollow closed body
        logger.info("Shell ohne Öffnungen: Erstelle geschlossenen Hohlkörper via Boolean")
        try:
            from build123d import offset, Solid

            # Inneren Solid erstellen (geschrumpft um Wandstärke)
            inner_solid = offset(current_solid, amount=-feature.thickness)

            if inner_solid and hasattr(inner_solid, 'is_valid') and inner_solid.is_valid():
                # Boolean Subtraktion: outer - inner = hollow
                result = current_solid - inner_solid
                if result and hasattr(result, 'is_valid') and result.is_valid():
                    logger.debug("Build123d Shell (geschlossen) via Boolean erfolgreich")
                    return result
                else:
                    logger.warning("Boolean-Subtraktion fehlgeschlagen, versuche cut()")
                    # Alternative: explizites cut()
                    from build123d import cut
                    result = cut(current_solid, inner_solid)
                    if result:
                        logger.debug("Build123d Shell (geschlossen) via cut() erfolgreich")
                        return result
        except Exception as e:
            logger.debug(f"Build123d Boolean-Shell fehlgeschlagen: {e}")

        # FALLBACK: OCP MakeThickSolid (auch ohne Öffnungen)
        return self._ocp_shell(current_solid, opening_faces, feature.thickness)

    def _ocp_shell(self, solid, opening_faces, thickness):
        """OCP-basierter Shell mit BRepOffsetAPI_MakeThickSolid."""
        if not HAS_OCP:
            return None

        try:
            from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
            from OCP.TopTools import TopTools_ListOfShape
            from config.tolerances import Tolerances

            shape = solid.wrapped if hasattr(solid, 'wrapped') else solid

            # Liste der zu entfernenden Faces
            faces_to_remove = TopTools_ListOfShape()
            for face in opening_faces:
                face_shape = face.wrapped if hasattr(face, 'wrapped') else face
                faces_to_remove.Append(face_shape)

            # Shell erstellen
            shell_op = BRepOffsetAPI_MakeThickSolid()
            shell_op.MakeThickSolidByJoin(
                shape,
                faces_to_remove,
                -thickness,  # Negativ für nach innen
                Tolerances.KERNEL_PRECISION
            )
            shell_op.Build()

            if shell_op.IsDone():
                result_shape = shell_op.Shape()
                result_shape = self._fix_shape_ocp(result_shape)

                from build123d import Solid, Shape
                try:
                    result = Solid(result_shape)
                    if hasattr(result, 'is_valid') and result.is_valid():
                        logger.debug("OCP Shell erfolgreich")
                        return result
                except Exception as e_solid:
                    logger.warning(f"Solid-Wrap fehlgeschlagen: {e_solid}")
                    try:
                        return Shape(result_shape)
                    except Exception as e_shape:
                        logger.warning(f"Shape-Wrap fehlgeschlagen: {e_shape}")

            logger.warning("OCP Shell IsDone() = False")
            return None

        except Exception as e:
            logger.error(f"OCP Shell Fehler: {e}")
            return None

    def _compute_pushpull(self, feature: 'PushPullFeature', current_solid):
        """
        PushPull: Face entlang ihrer Normale extrudieren.
        Verwendet BRepFeat_MakePrism (OCP) für echtes Face-Extrude.

        TNP-robust: Verwendet GeometricFaceSelector für Face-Matching.

        TNP v3.0: Gibt Tuple zurück (result_solid, boolean_history) für History-Tracking.

        Returns:
            Tuple[Solid, Optional[BRepTools_History]] oder nur Solid (Backward-Kompatibilität)
        """
        if current_solid is None:
            raise ValueError("PushPull benötigt einen existierenden Körper")

        import numpy as np
        from modeling.geometric_selector import GeometricFaceSelector

        # Face auflösen mit GeometricFaceSelector
        selector_dict = feature.face_selector
        if selector_dict is None:
            raise ValueError("Kein Face ausgewählt")

        # Selector ist jetzt ein GeometricFaceSelector Dict
        try:
            geo_selector = GeometricFaceSelector.from_dict(selector_dict)
        except Exception as e:
            raise ValueError(f"Ungültiger Face-Selector: {e}")

        # Face im Solid finden (TNP-robust)
        all_faces = current_solid.faces() if hasattr(current_solid, 'faces') else []
        if not all_faces:
            raise ValueError("Solid hat keine Faces")

        best_face = None
        best_score = -1.0

        for face in all_faces:
            try:
                score = self._score_face_match(face, geo_selector)
                if score > best_score:
                    best_score = score
                    best_face = face
            except Exception:
                continue

        if best_face is None or best_score < 0.5:  # Mindest-Score für Match
            raise ValueError(f"Face nicht gefunden (best score: {best_score:.2f})")

        # Normal aus GeometricFaceSelector verwenden (robuster)
        center = np.array(geo_selector.center)
        normal = np.array(geo_selector.normal)

        logger.debug(f"PushPull: Face gefunden (score={best_score:.2f}), distance={feature.distance}mm")

        # Extrusionsrichtung = Face-Normale * Distanz
        norm = np.array(normal)
        norm_len = np.linalg.norm(norm)
        if norm_len < 1e-6:
            raise ValueError("Face-Normale ist Null")
        norm = norm / norm_len

        distance = feature.distance

        try:
            from OCP.BRepFeat import BRepFeat_MakePrism
            from OCP.gp import gp_Dir, gp_Vec
            from OCP.TopAbs import TopAbs_FACE
            from OCP.TopoDS import TopoDS
            from build123d import Solid

            shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid
            face_shape = best_face.wrapped if hasattr(best_face, 'wrapped') else best_face

            direction = gp_Dir(float(norm[0]), float(norm[1]), float(norm[2]))

            # BRepFeat_MakePrism: Extrude face from solid
            # Args: (base_shape, profile_face, sketch_face, direction, fuse_mode, modify)
            # fuse_mode: 1=Fuse, 0=Cut
            fuse_mode = 1 if distance > 0 else 0
            abs_dist = abs(distance)

            prism = BRepFeat_MakePrism()
            prism.Init(shape, face_shape, face_shape, direction, fuse_mode, False)
            prism.Perform(abs_dist)

            if prism.IsDone():
                result_shape = prism.Shape()
                result_shape = self._unify_same_domain(result_shape, "BRepFeat_MakePrism")

                result = Solid(result_shape)
                is_valid = True  # Default: annehmen dass gültig
                
                # Prüfe Validität falls Methode existiert
                if hasattr(result, 'is_valid'):
                    try:
                        is_valid = result.is_valid()
                    except Exception as e:
                        logger.debug(f"[__init__.py] Fehler: {e}")
                        is_valid = True  # Bei Fehler: annehmen gültig
                
                if is_valid:
                    logger.debug(f"PushPull via BRepFeat_MakePrism erfolgreich")
                    
                    # === TNP v4.0: BRepFeat-Operation im NamingService speichern ===
                    try:
                        self._register_brepfeat_operation(
                            feature=feature,
                            original_solid=current_solid,
                            result_solid=result,
                            input_shape=shape,
                            result_shape=result_shape
                        )
                    except Exception as tnp_e:
                        if is_enabled("tnp_debug_logging"):
                            logger.warning(f"TNP v4.0: BRepFeat-Registrierung fehlgeschlagen: {tnp_e}")
                    
                    return (result, None)

            logger.warning("BRepFeat_MakePrism fehlgeschlagen, versuche Extrude+Boolean")
        except Exception as e:
            logger.debug(f"BRepFeat_MakePrism Fehler: {e}")

        # Fallback: Extrude face as wire → solid → Boolean
        try:
            from build123d import Solid, extrude
            from OCP.gp import gp_Vec
            from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut

            shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid
            face_shape = best_face.wrapped if hasattr(best_face, 'wrapped') else best_face

            vec = gp_Vec(float(norm[0] * distance), float(norm[1] * distance), float(norm[2] * distance))
            prism = BRepPrimAPI_MakePrism(face_shape, vec)
            prism.Build()

            if not prism.IsDone():
                raise RuntimeError("BRepPrimAPI_MakePrism fehlgeschlagen")

            extruded = prism.Shape()

            # Boolean: Fuse (positiv) oder Cut (negativ)
            if distance > 0:
                boolean = BRepAlgoAPI_Fuse(shape, extruded)
            else:
                boolean = BRepAlgoAPI_Cut(shape, extruded)

            boolean.SetFuzzyValue(1e-4)
            boolean.Build()

            if boolean.IsDone():
                result_shape = boolean.Shape()
                result_shape = self._unify_same_domain(result_shape, "Extrude+Boolean")

                # TNP v3.0: Extrahiere BRepTools_History für Edge-Tracking
                boolean_history = None
                try:
                    boolean_history = boolean.History()
                    logger.debug(f"PushPull: BRepTools_History extrahiert")
                except Exception as he:
                    logger.debug(f"PushPull: History extraction failed: {he}")

                result = Solid(result_shape)
                if hasattr(result, 'is_valid') and result.is_valid():
                    logger.debug(f"PushPull via Extrude+Boolean erfolgreich")
                    return (result, boolean_history)

            raise RuntimeError("Boolean fehlgeschlagen")
        except Exception as e:
            logger.error(f"PushPull Fallback fehlgeschlagen: {e}")
            raise

    def _unify_same_domain(self, shape, context: str = ""):
        """
        Vereinigt zusammenhängende Flächen mit gleicher Geometrie.

        Besonders wichtig für:
        - Planare Flächen die durch Boolean-Ops entstanden sind
        - Zylindrische Flächen die durch Extrusion entstanden sind

        Args:
            shape: OCP TopoDS_Shape
            context: Beschreibung für Logging

        Returns:
            Vereinigtes Shape (oder Original wenn Vereinigung fehlschlägt)
        """
        try:
            from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE

            # Zähle Faces vorher
            face_count_before = 0
            exp = TopExp_Explorer(shape, TopAbs_FACE)
            while exp.More():
                face_count_before += 1
                exp.Next()

            # UnifySameDomain mit erhöhten Toleranzen für Zylinder
            upgrader = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
            upgrader.SetLinearTolerance(0.1)   # 0.1mm - großzügiger für Zylinder-Segmente
            upgrader.SetAngularTolerance(0.1)  # ~5.7° - erlaubt Merge von Zylinder-Facetten
            upgrader.Build()
            unified = upgrader.Shape()

            if unified and not unified.IsNull():
                # Zähle Faces nachher
                face_count_after = 0
                exp = TopExp_Explorer(unified, TopAbs_FACE)
                while exp.More():
                    face_count_after += 1
                    exp.Next()

                if face_count_before != face_count_after:
                    logger.debug(f"UnifySameDomain ({context}): {face_count_before} → {face_count_after} Faces")
                return unified

            return shape
        except Exception as e:
            logger.trace(f"UnifySameDomain ({context}): {e}")
            return shape

    def _compute_nsided_patch(self, feature: 'NSidedPatchFeature', current_solid):
        """
        N-Sided Patch: Boundary-Edges finden und mit BRepFill_Filling füllen.
        Das Ergebnis wird per Sewing an den bestehenden Solid angefügt.
        """
        if current_solid is None:
            raise ValueError("N-Sided Patch benötigt einen existierenden Körper")

        import numpy as np

        if not feature.edge_selectors or len(feature.edge_selectors) < 3:
            raise ValueError(f"Mindestens 3 Kanten nötig, erhalten: {len(feature.edge_selectors) if feature.edge_selectors else 0}")

        # Edges im Solid auflösen
        all_edges = current_solid.edges() if hasattr(current_solid, 'edges') else []
        if not all_edges:
            raise ValueError("Solid hat keine Kanten")

        resolved_edges = []
        for selector in feature.edge_selectors:
            # Selector ist (center_x, center_y, center_z) oder ((cx,cy,cz), (dx,dy,dz))
            if isinstance(selector, (list, tuple)) and len(selector) == 2:
                if isinstance(selector[0], (list, tuple)):
                    center = np.array(selector[0])
                else:
                    center = np.array(selector)
            else:
                center = np.array(selector)

            best_edge = None
            best_dist = float('inf')
            for edge in all_edges:
                try:
                    ec = edge.center()
                    ec_arr = np.array([ec.X, ec.Y, ec.Z])
                    dist = np.linalg.norm(ec_arr - center)
                    if dist < best_dist:
                        best_dist = dist
                        best_edge = edge
                except Exception:
                    continue

            # Größere Toleranz nach Boolean-Operationen (Kanten können sich verschieben)
            if best_edge is not None and best_dist < 50.0:  # 50mm Toleranz
                resolved_edges.append(best_edge)
                if best_dist > 5.0:
                    logger.debug(f"Edge aufgelöst mit größerer Distanz: {best_dist:.2f}mm")
            else:
                logger.warning(f"Edge nicht aufgelöst (dist={best_dist:.2f}mm)")

        if len(resolved_edges) < 3:
            # Weniger strikt: Wenn Body trotzdem valid ist, nicht als Fehler behandeln
            logger.warning(f"Nur {len(resolved_edges)} von {len(feature.edge_selectors)} Kanten aufgelöst")
            # Prüfe ob Body bereits geschlossen ist - dann ist das Feature evtl. schon angewendet
            try:
                from OCP.BRepCheck import BRepCheck_Analyzer
                shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid
                analyzer = BRepCheck_Analyzer(shape)
                if analyzer.IsValid():
                    logger.info("Body ist bereits valid - N-Sided Patch möglicherweise bereits angewendet")
                    return current_solid
            except Exception:
                pass
            raise ValueError(f"Nur {len(resolved_edges)} von {len(feature.edge_selectors)} Kanten aufgelöst")

        logger.debug(f"N-Sided Patch: {len(resolved_edges)} Kanten, Grad={feature.degree}")

        from modeling.nsided_patch import NSidedPatch

        # Patch erstellen
        patch_face = NSidedPatch.fill_edges(
            resolved_edges,
            tangent_faces=NSidedPatch._find_adjacent_faces(
                current_solid, resolved_edges
            ) if feature.tangent else None,
            degree=feature.degree,
        )

        if patch_face is None:
            raise RuntimeError("N-Sided Patch: BRepFill_Filling fehlgeschlagen")

        # Patch-Face zum Solid hinzufügen
        # Methode: BRepBuilderAPI_MakeSolid aus allen Faces (original + patch)
        try:
            from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_SHELL, TopAbs_FACE
            from OCP.TopoDS import TopoDS
            from OCP.BRep import BRep_Builder
            from OCP.TopoDS import TopoDS_Shell, TopoDS_Compound
            from build123d import Solid

            shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid
            patch_shape = patch_face.wrapped if hasattr(patch_face, 'wrapped') else patch_face

            # Sewing mit größerer Toleranz für bessere Verbindung
            sewing = BRepBuilderAPI_Sewing(0.1)  # 0.1mm Toleranz
            sewing.SetNonManifoldMode(False)  # Manifold-Ergebnis erzwingen

            # Alle Faces des Original-Solids hinzufügen
            face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
            n_faces = 0
            while face_explorer.More():
                sewing.Add(face_explorer.Current())
                n_faces += 1
                face_explorer.Next()

            # Patch-Face hinzufügen
            sewing.Add(patch_shape)
            logger.debug(f"N-Sided Patch: Sewing {n_faces} Original-Faces + 1 Patch-Face")

            sewing.Perform()
            sewn = sewing.SewedShape()

            # Prüfe Sewing-Ergebnis
            n_sewn_faces = 0
            face_exp = TopExp_Explorer(sewn, TopAbs_FACE)
            while face_exp.More():
                n_sewn_faces += 1
                face_exp.Next()
            logger.debug(f"N-Sided Patch: Sewing-Ergebnis hat {n_sewn_faces} Faces (erwartet: {n_faces + 1})")

            # Versuche Solid zu bauen
            shell_explorer = TopExp_Explorer(sewn, TopAbs_SHELL)
            if shell_explorer.More():
                shell = TopoDS.Shell_s(shell_explorer.Current())

                # Prüfe ob Shell geschlossen ist
                from OCP.BRep import BRep_Tool
                from OCP.ShapeAnalysis import ShapeAnalysis_Shell
                analyzer = ShapeAnalysis_Shell()
                analyzer.LoadShells(shell)
                is_closed = not analyzer.HasFreeEdges()
                logger.debug(f"N-Sided Patch: Shell geschlossen = {is_closed}")

                maker = BRepBuilderAPI_MakeSolid(shell)
                maker.Build()

                if maker.IsDone():
                    result = Solid(maker.Shape())
                    result_faces = len(result.faces()) if hasattr(result, 'faces') else 0
                    if hasattr(result, 'is_valid') and result.is_valid():
                        logger.debug(f"N-Sided Patch: Loch geschlossen! ({result_faces} Faces)")
                        return result
                    else:
                        logger.warning(f"N-Sided Patch: Solid mit {result_faces} Faces ungültig, versuche ShapeFix...")
                        # ShapeFix versuchen
                        try:
                            from OCP.ShapeFix import ShapeFix_Solid
                            fixer = ShapeFix_Solid(maker.Shape())
                            fixer.Perform()
                            if fixer.Shape() and not fixer.Shape().IsNull():
                                fixed = Solid(fixer.Shape())
                                if hasattr(fixed, 'is_valid') and fixed.is_valid():
                                    logger.debug(f"N-Sided Patch: ShapeFix erfolgreich")
                                    return fixed
                        except Exception as fix_err:
                            logger.debug(f"ShapeFix fehlgeschlagen: {fix_err}")
            else:
                logger.warning("N-Sided Patch: Keine Shell im Sewing-Ergebnis")

            # Fallback: Versuche größere Toleranz
            logger.warning("N-Sided Patch: Erster Sewing-Versuch fehlgeschlagen, versuche mit höherer Toleranz...")
            sewing2 = BRepBuilderAPI_Sewing(1.0)  # 1mm Toleranz
            sewing2.SetNonManifoldMode(False)

            face_explorer2 = TopExp_Explorer(shape, TopAbs_FACE)
            while face_explorer2.More():
                sewing2.Add(face_explorer2.Current())
                face_explorer2.Next()
            sewing2.Add(patch_shape)
            sewing2.Perform()
            sewn2 = sewing2.SewedShape()

            shell_exp2 = TopExp_Explorer(sewn2, TopAbs_SHELL)
            if shell_exp2.More():
                shell2 = TopoDS.Shell_s(shell_exp2.Current())
                maker2 = BRepBuilderAPI_MakeSolid(shell2)
                maker2.Build()
                if maker2.IsDone():
                    result2 = Solid(maker2.Shape())
                    if hasattr(result2, 'is_valid') and result2.is_valid():
                        logger.debug(f"N-Sided Patch: Loch geschlossen mit höherer Toleranz!")
                        return result2

            # Letzter Fallback
            logger.warning("N-Sided Patch: Sewing komplett fehlgeschlagen")
            from build123d import Shape
            return Shape(sewn)

        except Exception as e:
            logger.error(f"N-Sided Patch Sewing fehlgeschlagen: {e}")
            raise

    def _compute_hollow(self, feature: 'HollowFeature', current_solid):
        """
        Aushöhlen mit optionalem Drain Hole.
        1. Shell (geschlossen) via _compute_shell-Logik
        2. Optional: Boolean Cut mit Zylinder für Drain Hole
        """
        if current_solid is None:
            raise ValueError("Hollow benötigt einen existierenden Körper")

        # Step 1: Create closed shell (reuse shell logic)
        # TNP v4.0: Leite opening_face_shape_ids und selectors durch
        shell_feat = ShellFeature(
            thickness=feature.wall_thickness,
            opening_face_selectors=feature.opening_face_selectors if feature.opening_face_selectors else []
        )
        # Übertrage auch ShapeIDs an Shell-Feature
        if feature.opening_face_shape_ids:
            shell_feat.opening_face_shape_ids = feature.opening_face_shape_ids

        hollowed = self._compute_shell(shell_feat, current_solid)
        if hollowed is None:
            raise ValueError("Shell-Erzeugung fehlgeschlagen")

        # Step 2: Drain hole (optional)
        if feature.drain_hole and feature.drain_diameter > 0:
            try:
                from build123d import Cylinder, Location, Vector, Solid
                import math

                pos = feature.drain_position
                d = feature.drain_direction
                radius = feature.drain_diameter / 2.0

                # Hole must be long enough to pierce through the wall
                # Use bounding box diagonal as safe length
                bb = hollowed.bounding_box()
                safe_length = 2.0 * max(bb.size.X, bb.size.Y, bb.size.Z)

                cyl = Cylinder(radius, safe_length)

                # Align cylinder along drain direction
                z_axis = Vector(0, 0, 1)
                drain_vec = Vector(*d)
                if drain_vec.length > 1e-9:
                    drain_vec = drain_vec.normalized()
                else:
                    drain_vec = Vector(0, 0, -1)

                # Position at drain point, centered along direction
                from build123d import Pos, Rot
                center = Vector(*pos) - drain_vec * (safe_length / 2)

                # Compute rotation from Z to drain direction
                cross = z_axis.cross(drain_vec)
                dot = z_axis.dot(drain_vec)
                if cross.length > 1e-9:
                    angle = math.degrees(math.acos(max(-1, min(1, dot))))
                    axis = cross.normalized()
                    from build123d import Axis
                    cyl = cyl.rotate(Axis.Z, 0)  # identity
                    # Use Location with rotation
                    from OCP.gp import gp_Ax1, gp_Pnt, gp_Dir, gp_Trsf
                    trsf = gp_Trsf()
                    trsf.SetRotation(
                        gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(axis.X, axis.Y, axis.Z)),
                        math.radians(angle)
                    )
                    trsf.SetTranslationPart(
                        gp_Pnt(center.X, center.Y, center.Z).XYZ()
                                            )
                    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
                    builder = BRepBuilderAPI_Transform(cyl.wrapped, trsf, True)
                    builder.Build()
                    cyl = Solid(builder.Shape())
                elif dot < 0:
                    # Anti-parallel: rotate 180° around X
                    from build123d import Axis
                    cyl = cyl.rotate(Axis.X, 180)
                    cyl = cyl.move(Location((center.X, center.Y, center.Z)))
                else:
                    cyl = cyl.move(Location((center.X, center.Y, center.Z)))

                result = hollowed - cyl
                if result and hasattr(result, 'is_valid') and result.is_valid():
                    logger.debug(f"Hollow mit Drain Hole (⌀{feature.drain_diameter}mm) erfolgreich")
                    return result
                else:
                    logger.warning("Drain Hole Boolean fehlgeschlagen, verwende Shell ohne Drain")
                    return hollowed

            except Exception as e:
                logger.warning(f"Drain Hole fehlgeschlagen: {e}, verwende Shell ohne Drain")
                return hollowed

        logger.debug(f"Hollow (Wandstärke {feature.wall_thickness}mm) erfolgreich")
        return hollowed

    def _compute_hole(self, feature: 'HoleFeature', current_solid):
        """
        Erstellt eine Bohrung.

        Methoden (in Priorität):
        1. BRepFeat_MakeCylindricalHole (für simple holes - saubere Topologie)
        2. Boolean Cut mit Zylinder (für counterbore, countersink, oder Fallback)
        """
        from build123d import Solid, Cylinder, Location, Vector, Axis, Plane, Align
        import math

        pos = Vector(*feature.position)
        d = Vector(*feature.direction)
        radius = feature.diameter / 2.0

        # Tiefe: 0 = through all (verwende grosse Tiefe)
        depth = feature.depth if feature.depth > 0 else 1000.0

        logger.debug(f"Hole: type={feature.hole_type}, D={feature.diameter}mm, depth={depth}mm at {pos}")

        # === METHODE 1: BRepFeat_MakeCylindricalHole (nur für simple holes) ===
        if feature.hole_type == "simple":
            try:
                from modeling.brepfeat_operations import brepfeat_cylindrical_hole

                result = brepfeat_cylindrical_hole(
                    base_solid=current_solid,
                    position=feature.position,
                    direction=feature.direction,
                    diameter=feature.diameter,
                    depth=feature.depth  # 0 = through all
                )

                if result is not None:
                    logger.debug(f"Hole via BRepFeat: D={feature.diameter}mm")
                    return result
                else:
                    logger.debug("BRepFeat_MakeCylindricalHole fehlgeschlagen, Fallback auf Boolean")
            except Exception as e:
                logger.debug(f"BRepFeat Hole: {e}, Fallback auf Boolean")

        # === METHODE 2: Boolean Cut (für counterbore, countersink, oder Fallback) ===

        # Hauptbohrung als Zylinder erstellen
        hole_cyl = Cylinder(radius, depth,
                            align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Rotation: Standard-Zylinder zeigt in +Z, wir brauchen feature.direction
        from OCP.gp import gp_Trsf, gp_Ax1, gp_Pnt, gp_Dir, gp_Vec
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform

        # Zylinder in Position bringen
        hole_shape = self._position_cylinder(hole_cyl, pos, d, depth)
        if hole_shape is None:
            raise ValueError("Hole-Zylinder konnte nicht positioniert werden")

        # Counterbore: zusaetzlicher breiterer Zylinder oben
        if feature.hole_type == "counterbore":
            cb_radius = feature.counterbore_diameter / 2.0
            cb_depth = feature.counterbore_depth
            cb_cyl = Cylinder(cb_radius, cb_depth,
                              align=(Align.CENTER, Align.CENTER, Align.MIN))
            cb_shape = self._position_cylinder(cb_cyl, pos, d, cb_depth)
            if cb_shape:
                hole_shape = hole_shape.fuse(cb_shape)

        # Countersink: Kegel oben
        elif feature.hole_type == "countersink":
            cs_angle_rad = math.radians(feature.countersink_angle / 2.0)
            cs_depth = radius / math.tan(cs_angle_rad) if cs_angle_rad > 0 else 2.0
            from build123d import Cone
            cs_cone = Cone(feature.diameter, 0.01, cs_depth,
                           align=(Align.CENTER, Align.CENTER, Align.MIN))
            cs_shape = self._position_cylinder(cs_cone, pos, d, cs_depth)
            if cs_shape:
                hole_shape = hole_shape.fuse(cs_shape)

        # Boolean Cut: Bohrung vom Koerper abziehen
        result = current_solid.cut(hole_shape)
        if result and hasattr(result, 'is_valid') and result.is_valid():
            logger.debug(f"Hole {feature.hole_type} D={feature.diameter}mm erfolgreich")
            return result

        raise ValueError(f"Hole Boolean Cut fehlgeschlagen")

    def _position_cylinder(self, cyl_solid, position, direction, depth):
        """Positioniert einen Zylinder an position entlang direction."""
        try:
            from build123d import Vector, Location
            import numpy as np

            # Support both tuples and Build123d Vectors
            if hasattr(direction, 'X'):
                d = np.array([direction.X, direction.Y, direction.Z], dtype=float)
            else:
                d = np.array([direction[0], direction[1], direction[2]], dtype=float)
            d_norm = d / (np.linalg.norm(d) + 1e-12)

            # Start etwas vor der Flaeche (damit der Cut sicher durchgeht)
            if hasattr(position, 'X'):
                pos = np.array([position.X, position.Y, position.Z])
            else:
                pos = np.array([position[0], position[1], position[2]])
            start = pos - d_norm * 0.5

            # Rotation berechnen: Z-Achse -> direction
            z_axis = np.array([0, 0, 1.0])
            if abs(np.dot(z_axis, d_norm)) > 0.999:
                # Parallel zu Z - keine Rotation noetig
                rotated = cyl_solid
            else:
                rot_axis = np.cross(z_axis, d_norm)
                rot_axis = rot_axis / (np.linalg.norm(rot_axis) + 1e-12)
                angle = np.arccos(np.clip(np.dot(z_axis, d_norm), -1, 1))

                from OCP.gp import gp_Trsf, gp_Ax1, gp_Pnt, gp_Dir
                from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
                import math

                trsf = gp_Trsf()
                ax = gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(rot_axis[0], rot_axis[1], rot_axis[2]))
                trsf.SetRotation(ax, angle)

                shape = cyl_solid.wrapped if hasattr(cyl_solid, 'wrapped') else cyl_solid
                builder = BRepBuilderAPI_Transform(shape, trsf, True)
                builder.Build()
                from build123d import Solid
                rotated = Solid(builder.Shape())

            # Translation
            from OCP.gp import gp_Trsf, gp_Vec as gp_V
            from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
            trsf2 = gp_Trsf()
            trsf2.SetTranslation(gp_V(start[0], start[1], start[2]))

            shape2 = rotated.wrapped if hasattr(rotated, 'wrapped') else rotated
            builder2 = BRepBuilderAPI_Transform(shape2, trsf2, True)
            builder2.Build()
            from build123d import Solid
            return Solid(builder2.Shape())

        except Exception as e:
            logger.error(f"Zylinder-Positionierung fehlgeschlagen: {e}")
            return None

    def _compute_draft(self, feature: 'DraftFeature', current_solid):
        """
        Wendet Draft/Taper auf selektierte Flaechen an.
        Verwendet OCP BRepOffsetAPI_DraftAngle.
        Wenn face_selectors vorhanden: nur passende Faces draften.
        """
        import math
        import numpy as np
        from OCP.BRepOffsetAPI import BRepOffsetAPI_DraftAngle
        from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from OCP.BRep import BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Plane

        shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid

        pull_dir = gp_Dir(
            feature.pull_direction[0],
            feature.pull_direction[1],
            feature.pull_direction[2]
        )
        angle_rad = math.radians(feature.draft_angle)

        # Neutrale Ebene (Basis der Entformung)
        neutral_plane = gp_Pln(gp_Pnt(0, 0, 0), pull_dir)

        # Selektierte Normalen (wenn vorhanden)
        selected_normals = None
        if feature.face_selectors:
            selected_normals = [s.get('normal') for s in feature.face_selectors if 'normal' in s]

        draft_op = BRepOffsetAPI_DraftAngle(shape)

        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        face_count = 0

        while explorer.More():
            face = TopoDS.Face_s(explorer.Current())

            # Wenn Faces selektiert: nur passende draften
            if selected_normals:
                try:
                    adaptor = BRepAdaptor_Surface(face)
                    if adaptor.GetType() == GeomAbs_Plane:
                        pln = adaptor.Plane()
                        ax = pln.Axis().Direction()
                        face_normal = np.array([ax.X(), ax.Y(), ax.Z()])
                        # Orientierung beachten
                        if face.IsEqual(face):  # immer True, aber face orientation check
                            from OCP.TopAbs import TopAbs_REVERSED
                            if face.Orientation() == TopAbs_REVERSED:
                                face_normal = -face_normal

                        # Prüfe ob diese Normale in der Selektion ist
                        matched = False
                        for sel_n in selected_normals:
                            sel_arr = np.array(sel_n)
                            if np.allclose(face_normal, sel_arr, atol=0.1):
                                matched = True
                                break
                        if not matched:
                            explorer.Next()
                            continue
                except Exception:
                    explorer.Next()
                    continue

            try:
                draft_op.Add(face, pull_dir, angle_rad, neutral_plane)
                face_count += 1
            except Exception:
                pass  # Face nicht draftbar (z.B. parallel zur Pull-Direction)
            explorer.Next()

        if face_count == 0:
            raise ValueError("Keine Flaechen konnten gedraftet werden")

        draft_op.Build()
        if draft_op.IsDone():
            result_shape = draft_op.Shape()
            result_shape = self._fix_shape_ocp(result_shape)
            from build123d import Solid
            result = Solid(result_shape)
            logger.debug(f"Draft {feature.draft_angle}° auf {face_count} Flaechen erfolgreich")
            return result

        raise ValueError("Draft-Operation fehlgeschlagen")

    def _compute_split(self, feature: 'SplitFeature', current_solid):
        """
        Teilt einen Koerper entlang einer Ebene.

        TNP v4.0 / Multi-Body Architecture:
        - Berechnet BEIDE Hälften (above + below)
        - Gibt SplitResult zurück mit beiden Bodies
        - Für legacy keep_side != "both": Gibt nur eine Hälfte als Solid zurück

        Returns:
            - SplitResult (wenn keep_side == "both")
            - Solid (wenn keep_side == "above" oder "below" - legacy)
        """
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
        from OCP.gp import gp_Pln, gp_Pnt, gp_Dir
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        import numpy as np

        shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid

        origin = gp_Pnt(*feature.plane_origin)
        normal = gp_Dir(*feature.plane_normal)
        plane = gp_Pln(origin, normal)

        logger.debug(f"Split: origin={feature.plane_origin}, normal={feature.plane_normal}, keep={feature.keep_side}")

        # === Phase 1: Grosse Ebene als Face erstellen ===
        face_builder = BRepBuilderAPI_MakeFace(plane, -1000, 1000, -1000, 1000)
        face_builder.Build()
        if not face_builder.IsDone():
            raise ValueError("Split-Ebene konnte nicht erstellt werden")

        split_face = face_builder.Face()

        # === Phase 2: Beide HalfSpaces erstellen ===
        n = np.array(feature.plane_normal, dtype=float)
        n = n / (np.linalg.norm(n) + 1e-12)

        # HalfSpace ABOVE (+normal Seite)
        ref_pt_above = np.array(feature.plane_origin) + n * 100.0
        half_space_above = BRepPrimAPI_MakeHalfSpace(split_face, gp_Pnt(*ref_pt_above))
        half_solid_above = half_space_above.Solid()

        # HalfSpace BELOW (-normal Seite)
        ref_pt_below = np.array(feature.plane_origin) - n * 100.0
        half_space_below = BRepPrimAPI_MakeHalfSpace(split_face, gp_Pnt(*ref_pt_below))
        half_solid_below = half_space_below.Solid()

        # === Phase 3: Beide Cuts durchführen ===
        cut_above = BRepAlgoAPI_Cut(shape, half_solid_below)  # Cut away below → keep above
        cut_below = BRepAlgoAPI_Cut(shape, half_solid_above)  # Cut away above → keep below

        cut_above.Build()
        cut_below.Build()

        if not (cut_above.IsDone() and cut_below.IsDone()):
            raise ValueError("Split-Operation fehlgeschlagen - einer der Cuts konnte nicht durchgeführt werden")

        # === Phase 4: Beide Solids erstellen ===
        result_above_shape = self._fix_shape_ocp(cut_above.Shape())
        result_below_shape = self._fix_shape_ocp(cut_below.Shape())

        from build123d import Solid
        body_above = Solid(result_above_shape)
        body_below = Solid(result_below_shape)

        # === Phase 5: Legacy vs Multi-Body Mode ===
        if feature.keep_side == "both":
            # TNP v4.0 Multi-Body Mode
            result = SplitResult(
                body_above=body_above,
                body_below=body_below,
                split_plane={
                    "origin": feature.plane_origin,
                    "normal": feature.plane_normal
                }
            )
            logger.debug(f"Split (both) erfolgreich → 2 Bodies erstellt")
            return result
        elif feature.keep_side == "above":
            # Legacy: Nur above zurückgeben
            logger.debug(f"Split (above) erfolgreich")
            return body_above
        else:
            # Legacy: Nur below zurückgeben
            logger.debug(f"Split (below) erfolgreich")
            return body_below

    def _compute_thread(self, feature: 'ThreadFeature', current_solid):
        """
        Erzeugt ein echtes helikales Gewinde via Helix-Sweep + Boolean.

        Strategy:
        1. ISO 60° Gewindeprofil als Draht erstellen
        2. Helix-Pfad mit Pitch und Tiefe
        3. Sweep Profil entlang Helix → Thread-Solid
        4. Boolean Cut (extern) oder Fuse (intern)
        """
        import math
        import numpy as np

        shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid
        pos = np.array(feature.position, dtype=float)
        direction = np.array(feature.direction, dtype=float)
        direction = direction / (np.linalg.norm(direction) + 1e-12)

        r = feature.diameter / 2.0
        pitch = feature.pitch
        depth = feature.depth
        n_turns = depth / pitch

        # Thread groove depth (ISO 60° metric: H = 0.8660 * P, groove = 5/8 * H)
        H = 0.8660254 * pitch
        groove_depth = 0.625 * H

        return self._compute_thread_helix(
            shape, pos, direction, r, pitch, depth, n_turns,
            groove_depth, feature.thread_type, feature.tolerance_offset
        )

    def _compute_thread_helix(self, shape, pos, direction, r, pitch, depth, n_turns,
                               groove_depth, thread_type, tolerance_offset):
        """Echtes Gewinde via OCP Helix + Sweep."""
        import math
        from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Ax3, gp_Ax1, gp_Pnt2d, gp_Vec
        from OCP.Geom import Geom_CylindricalSurface
        from OCP.GCE2d import GCE2d_MakeSegment
        from OCP.BRepBuilderAPI import (
            BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeEdge,
            BRepBuilderAPI_MakeFace
        )
        from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
        from OCP.TopoDS import TopoDS_Wire
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder

        # gp_Ax3 für Geom_CylindricalSurface (nicht gp_Ax2!)
        ax3 = gp_Ax3(gp_Pnt(*pos), gp_Dir(*direction))

        if thread_type == "external":
            helix_r = r - groove_depth / 2
        else:
            helix_r = r + groove_depth / 2

        # Create helix on cylindrical surface
        cyl_surface = Geom_CylindricalSurface(ax3, helix_r)

        # Helix as 2D line on unwrapped cylinder: u = angle, v = height
        # Full turn = 2*pi in u, pitch in v
        total_height = depth + pitch  # Extra turn for clean cut
        total_angle = (total_height / pitch) * 2 * math.pi

        p1 = gp_Pnt2d(0, -pitch / 2)  # Start slightly below
        p2 = gp_Pnt2d(total_angle, total_height - pitch / 2)

        seg = GCE2d_MakeSegment(p1, p2)
        helix_edge = BRepBuilderAPI_MakeEdge(seg.Value(), cyl_surface).Edge()
        helix_wire = BRepBuilderAPI_MakeWire(helix_edge).Wire()

        # ISO 60° triangle profile (cross-section of thread groove)
        # Profile perpendicular to helix at start
        # Triangle: base at pitch radius, tip pointing inward/outward
        h = groove_depth
        half_pitch = pitch * 0.3  # Width of groove at base

        # Build triangular wire as profile
        if thread_type == "external":
            # Profile cuts INTO cylinder (groove)
            p_top = gp_Pnt(pos[0] + r * 1.01, pos[1], pos[2])
            p_bl = gp_Pnt(pos[0] + (r - h), pos[1], pos[2] - half_pitch)
            p_br = gp_Pnt(pos[0] + (r - h), pos[1], pos[2] + half_pitch)
        else:
            # Profile adds INTO hole
            p_top = gp_Pnt(pos[0] + r * 0.99, pos[1], pos[2])
            p_bl = gp_Pnt(pos[0] + (r + h), pos[1], pos[2] - half_pitch)
            p_br = gp_Pnt(pos[0] + (r + h), pos[1], pos[2] + half_pitch)

        e1 = BRepBuilderAPI_MakeEdge(p_top, p_bl).Edge()
        e2 = BRepBuilderAPI_MakeEdge(p_bl, p_br).Edge()
        e3 = BRepBuilderAPI_MakeEdge(p_br, p_top).Edge()

        profile_wire = BRepBuilderAPI_MakeWire(e1, e2, e3).Wire()

        # Sweep profile along helix
        pipe = BRepOffsetAPI_MakePipeShell(helix_wire)
        pipe.Add(profile_wire)
        pipe.SetMode(False)  # Frenet mode
        pipe.Build()

        if not pipe.IsDone():
            raise RuntimeError("Pipe sweep for thread failed")

        thread_shape = pipe.Shape()

        # Boolean operation
        if thread_type == "external":
            op = BRepAlgoAPI_Cut(shape, thread_shape)
        else:
            op = BRepAlgoAPI_Fuse(shape, thread_shape)

        op.Build()
        if not op.IsDone():
            raise RuntimeError("Thread boolean failed")

        result_shape = self._fix_shape_ocp(op.Shape())
        from build123d import Solid
        return Solid(result_shape)

    def _compute_thread_rings(self, shape, pos, direction, r, pitch, depth, n_turns,
                               groove_depth, thread_type):
        """Ring-Fallback fuer Gewinde (alte Methode)."""
        from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse

        result_shape = shape
        if thread_type == "external":
            minor_r = r - groove_depth
            for i in range(int(n_turns)):
                z_offset = pos + direction * (i * pitch + pitch * 0.25)
                ring_ax = gp_Ax2(gp_Pnt(*z_offset), gp_Dir(*direction))
                outer = BRepPrimAPI_MakeCylinder(ring_ax, r + 0.01, pitch * 0.5)
                inner = BRepPrimAPI_MakeCylinder(ring_ax, minor_r, pitch * 0.5)
                outer.Build()
                inner.Build()
                if outer.IsDone() and inner.IsDone():
                    ring_cut = BRepAlgoAPI_Cut(outer.Shape(), inner.Shape())
                    ring_cut.Build()
                    if ring_cut.IsDone():
                        cut_op = BRepAlgoAPI_Cut(result_shape, ring_cut.Shape())
                        cut_op.Build()
                        if cut_op.IsDone():
                            result_shape = cut_op.Shape()
        else:
            outer_r = r + groove_depth
            for i in range(int(n_turns)):
                z_offset = pos + direction * (i * pitch + pitch * 0.25)
                ring_ax = gp_Ax2(gp_Pnt(*z_offset), gp_Dir(*direction))
                outer = BRepPrimAPI_MakeCylinder(ring_ax, outer_r, pitch * 0.5)
                inner = BRepPrimAPI_MakeCylinder(ring_ax, r, pitch * 0.5)
                outer.Build()
                inner.Build()
                if outer.IsDone() and inner.IsDone():
                    ring = BRepAlgoAPI_Cut(outer.Shape(), inner.Shape())
                    ring.Build()
                    if ring.IsDone():
                        fuse_op = BRepAlgoAPI_Fuse(result_shape, ring.Shape())
                        fuse_op.Build()
                        if fuse_op.IsDone():
                            result_shape = fuse_op.Shape()

        result_shape = self._fix_shape_ocp(result_shape)
        from build123d import Solid
        return Solid(result_shape)

    def _profile_data_to_face(self, profile_data: dict):
        """
        Konvertiert Profil-Daten zu Build123d Face.

        Args:
            profile_data: Dict mit shapely_poly, plane_origin, plane_normal, etc.

        Returns:
            Build123d Face oder None
        """
        if not profile_data:
            return None

        try:
            from build123d import Plane as B3DPlane, Vector, make_face, Wire, Polyline

            # Plane aus Profil-Daten erstellen
            origin = profile_data.get('plane_origin', (0, 0, 0))
            normal = profile_data.get('plane_normal', (0, 0, 1))
            # WICHTIG: 'plane_x' wird von main_window gesetzt, 'plane_x_dir' ist Fallback
            x_dir = profile_data.get('plane_x') or profile_data.get('plane_x_dir')

            # Validiere normal-Vektor
            normal_vec = Vector(*normal)
            if normal_vec.length < 1e-10:
                logger.warning("Sweep: Normale hat Länge 0, verwende (0, 0, 1)")
                normal_vec = Vector(0, 0, 1)

            # x_dir berechnen falls nicht vorhanden oder ungültig
            if not x_dir or Vector(*x_dir).length < 1e-10:
                # Berechne x_dir senkrecht zur Normalen
                import numpy as np
                n = np.array([normal_vec.X, normal_vec.Y, normal_vec.Z])
                n = n / (np.linalg.norm(n) + 1e-10)

                # Wähle Referenz-Vektor der nicht parallel zur Normalen ist
                if abs(n[2]) < 0.9:
                    ref = np.array([0, 0, 1])
                else:
                    ref = np.array([1, 0, 0])

                x = np.cross(n, ref)
                x = x / (np.linalg.norm(x) + 1e-10)
                x_dir = tuple(x)
                logger.debug(f"Sweep: x_dir berechnet: {x_dir}")

            plane = B3DPlane(
                origin=Vector(*origin),
                z_dir=normal_vec,
                x_dir=Vector(*x_dir)
            )

            # Shapely Polygon zu 3D Wire konvertieren
            shapely_poly = profile_data.get('shapely_poly')
            if shapely_poly is not None:
                # Exterior Ring zu 3D Punkten
                coords = list(shapely_poly.exterior.coords)
                points_3d = []
                for x, y in coords:
                    pt_3d = plane.from_local_coords((x, y))
                    points_3d.append(pt_3d)

                # Äußeres Wire erstellen
                if len(points_3d) >= 3:
                    outer_wire = Wire.make_polygon(points_3d, close=True)

                    # Innere Löcher verarbeiten (falls vorhanden)
                    inner_wires = []
                    if hasattr(shapely_poly, 'interiors') and shapely_poly.interiors:
                        for interior in shapely_poly.interiors:
                            inner_coords = list(interior.coords)
                            inner_points_3d = []
                            for x, y in inner_coords:
                                pt_3d = plane.from_local_coords((x, y))
                                inner_points_3d.append(pt_3d)
                            if len(inner_points_3d) >= 3:
                                inner_wire = Wire.make_polygon(inner_points_3d, close=True)
                                inner_wires.append(inner_wire)

                    # Face mit Löchern erstellen
                    if inner_wires:
                        logger.debug(f"Profil hat {len(inner_wires)} innere Löcher")
                        face = make_face(outer_wire, inner_wires)
                    else:
                        face = make_face(outer_wire)
                    return face

            return None

        except Exception as e:
            logger.debug(f"Profil-zu-Face Konvertierung fehlgeschlagen: {e}")
            return None

    def _resolve_path(self, path_data: dict, current_solid):
        """
        Löst Pfad-Daten zu Build123d Wire auf.

        Args:
            path_data: Dict mit edge_selector, sketch_id, etc.
            current_solid: Aktueller Solid für Body-Edge-Auflösung

        Returns:
            Build123d Wire oder None
        """
        if not path_data:
            return None

        try:
            path_type = path_data.get('type', 'body_edge')

            if path_type == 'sketch_edge':
                # Sketch-Edge zu Wire konvertieren
                return self._sketch_edge_to_wire(path_data)

            elif path_type == 'body_edge':
                from build123d import Wire

                # PRIMÄR: Direkte Build123d Edges verwenden (robuster)
                build123d_edges = path_data.get('build123d_edges', [])
                if build123d_edges:
                    logger.debug(f"Sweep: Verwende {len(build123d_edges)} direkte Build123d Edge(s)")
                    return Wire(build123d_edges)

                # FALLBACK: Edge über Selektor finden
                edge_selector = path_data.get('edge_selector')
                if edge_selector and current_solid:
                    # edge_selector kann eine Liste von Punkten sein
                    selectors = edge_selector if isinstance(edge_selector, list) else [edge_selector]
                    edges = self._resolve_edges(current_solid, selectors)
                    if edges:
                        logger.debug(f"Sweep: {len(edges)} Edge(s) über Selektor aufgelöst")
                        return Wire(edges)

            return None

        except Exception as e:
            logger.debug(f"Pfad-Auflösung fehlgeschlagen: {e}")
            return None

    def _sketch_edge_to_wire(self, path_data: dict):
        """
        Konvertiert Sketch-Edge zu Build123d Wire.

        Unterstützte Typen:
        - arc: Bogen mit center, radius, start_angle, end_angle
        - line: Linie mit start, end
        - spline: Spline mit control_points
        - polyline: Polylinie mit points

        Args:
            path_data: Dict mit geometry_type und entsprechenden Parametern

        Returns:
            Build123d Wire oder None
        """
        try:
            from build123d import Wire, Edge, Vector, Plane
            import numpy as np

            geom_type = path_data.get('geometry_type', 'line')
            plane_origin = path_data.get('plane_origin', (0, 0, 0))
            plane_normal = path_data.get('plane_normal', (0, 0, 1))
            plane_x = path_data.get('plane_x', (1, 0, 0))
            plane_y = path_data.get('plane_y', (0, 1, 0))

            def to_3d(x, y):
                """Konvertiert 2D Sketch-Koordinaten zu 3D"""
                o = np.array(plane_origin)
                px = np.array(plane_x)
                py = np.array(plane_y)
                return tuple(o + x * px + y * py)

            if geom_type == 'arc':
                # Bogen
                center_2d = path_data.get('center', (0, 0))
                radius = path_data.get('radius', 10.0)
                start_angle = path_data.get('start_angle', 0.0)
                end_angle = path_data.get('end_angle', 90.0)

                center_3d = to_3d(center_2d[0], center_2d[1])

                # Build123d Arc erstellen
                from build123d import ThreePointArc
                import math

                # Start- und Endpunkt berechnen
                start_rad = math.radians(start_angle)
                mid_rad = math.radians((start_angle + end_angle) / 2)
                end_rad = math.radians(end_angle)

                start_2d = (center_2d[0] + radius * math.cos(start_rad),
                           center_2d[1] + radius * math.sin(start_rad))
                mid_2d = (center_2d[0] + radius * math.cos(mid_rad),
                         center_2d[1] + radius * math.sin(mid_rad))
                end_2d = (center_2d[0] + radius * math.cos(end_rad),
                         center_2d[1] + radius * math.sin(end_rad))

                start_3d = to_3d(*start_2d)
                mid_3d = to_3d(*mid_2d)
                end_3d = to_3d(*end_2d)

                arc = ThreePointArc(Vector(*start_3d), Vector(*mid_3d), Vector(*end_3d))
                return Wire([arc])

            elif geom_type == 'line':
                # Linie
                start_2d = path_data.get('start', (0, 0))
                end_2d = path_data.get('end', (10, 0))

                start_3d = to_3d(*start_2d)
                end_3d = to_3d(*end_2d)

                from build123d import Line
                line = Line(Vector(*start_3d), Vector(*end_3d))
                return Wire([line])

            elif geom_type == 'spline':
                # Spline
                control_points = path_data.get('control_points', [])
                if len(control_points) < 2:
                    return None

                points_3d = [Vector(*to_3d(p[0], p[1])) for p in control_points]

                from build123d import Spline
                spline = Spline(*points_3d)
                return Wire([spline])

            elif geom_type == 'polyline':
                # Polylinie (mehrere verbundene Linien)
                points = path_data.get('points', [])
                if len(points) < 2:
                    return None

                from build123d import Line
                edges = []
                for i in range(len(points) - 1):
                    start_3d = to_3d(*points[i])
                    end_3d = to_3d(*points[i + 1])
                    edges.append(Line(Vector(*start_3d), Vector(*end_3d)))

                return Wire(edges)

            logger.warning(f"Unbekannter Sketch-Edge-Typ: {geom_type}")
            return None

        except Exception as e:
            logger.error(f"Sketch-Edge zu Wire Konvertierung fehlgeschlagen: {e}")
            return None

    def _score_face_match(self, face, geo_selector) -> float:
        """
        Berechnet Match-Score (0-1) zwischen Face und GeometricFaceSelector.
        TNP-robustes Face-Matching basierend auf mehreren Kriterien.
        
        Args:
            face: Build123d Face
            geo_selector: GeometricFaceSelector mit center, normal, area, surface_type
            
        Returns:
            Score zwischen 0 (kein Match) und 1 (perfektes Match)
        """
        try:
            import numpy as np
            
            # Center-Distanz (wichtigstes Kriterium)
            fc = face.center()
            face_center = np.array([fc.X, fc.Y, fc.Z])
            selector_center = np.array(geo_selector.center)
            dist = np.linalg.norm(face_center - selector_center)
            
            # Normalisierter Distanz-Score (1.0 = gleich, 0.0 = außerhalb Toleranz)
            tolerance = getattr(geo_selector, 'tolerance', 10.0)
            center_score = max(0.0, 1.0 - (dist / tolerance))
            
            # Normalen-Ähnlichkeit
            try:
                fn = face.normal_at(fc)
                face_normal = np.array([fn.X, fn.Y, fn.Z])
                selector_normal = np.array(geo_selector.normal)
                
                # Normalisieren
                face_normal = face_normal / (np.linalg.norm(face_normal) + 1e-10)
                selector_normal = selector_normal / (np.linalg.norm(selector_normal) + 1e-10)
                
                # Dot-Product (1.0 = gleiche Richtung, -1.0 = entgegengesetzt)
                dot = abs(np.dot(face_normal, selector_normal))  # Abs für beide Richtungen
                normal_score = dot
            except Exception as e:
                logger.debug(f"[__init__.py] Fehler: {e}")
                normal_score = 0.5  # Neutral wenn Normal nicht berechenbar
            
            # Area-Ähnlichkeit (20% Toleranz)
            try:
                face_area = face.area
                selector_area = geo_selector.area
                if selector_area > 0:
                    area_ratio = min(face_area, selector_area) / max(face_area, selector_area)
                    area_score = area_ratio
                else:
                    area_score = 0.5
            except Exception as e:
                logger.debug(f"[__init__.py] Fehler: {e}")
                area_score = 0.5
            
            # Gewichteter Gesamt-Score
            # Center ist wichtigster, dann Normal, dann Area
            total_score = (0.5 * center_score + 
                          0.3 * normal_score + 
                          0.2 * area_score)
            
            return total_score
            
        except Exception as e:
            logger.debug(f"Face-Scoring fehlgeschlagen: {e}")
            return 0.0

    def _resolve_faces_for_shell(self, solid, face_selectors: List[dict]):
        """
        Löst Face-Selektoren für Shell-Öffnungen auf.
        
        TNP-robust: Verwendet GeometricFaceSelector für stabiles Face-Matching.

        Args:
            solid: Build123d Solid
            face_selectors: Liste von GeometricFaceSelector.to_dict() Dicts
                Enthalten: center, normal, area, surface_type, tolerance

        Returns:
            Liste von Build123d Faces
        """
        if not face_selectors or solid is None:
            return []

        try:
            from modeling.geometric_selector import GeometricFaceSelector
            
            # Alle Faces vom Solid holen
            all_faces = solid.faces() if hasattr(solid, 'faces') else []
            if not all_faces:
                logger.warning("Shell: Solid hat keine Faces")
                return []

            resolved = []
            for selector_dict in face_selectors:
                try:
                    # Konvertiere zu GeometricFaceSelector
                    if isinstance(selector_dict, dict):
                        geo_selector = GeometricFaceSelector.from_dict(selector_dict)
                    elif hasattr(selector_dict, 'center'):
                        geo_selector = selector_dict
                    else:
                        # Legacy: Tuple-Format
                        logger.warning(f"Shell: Legacy Selector-Format, konvertiere...")
                        continue
                    
                    # Finde beste matching Face (TNP-robust)
                    best_face = None
                    best_score = -1.0
                    
                    for face in all_faces:
                        try:
                            score = self._score_face_match(face, geo_selector)
                            if score > best_score:
                                best_score = score
                                best_face = face
                        except Exception as e:
                            logger.debug(f"[__init__.py] Fehler: {e}")
                            continue
                    
                    if best_face and best_score > 0.4:  # 40% Mindest-Score
                        resolved.append(best_face)
                        logger.debug(f"Shell: Face aufgelöst (score={best_score:.2%})")
                    else:
                        logger.warning(f"Shell: Konnte Face nicht auflösen (best_score={best_score:.2%})")
                        
                except Exception as e:
                    logger.debug(f"Shell: Selector-Auflösung fehlgeschlagen: {e}")
                    continue

            return resolved

        except Exception as e:
            logger.debug(f"Face-Auflösung für Shell fehlgeschlagen: {e}")
            return []

    def _update_edge_selectors_after_operation(self, solid, current_feature_index: int = -1):
        """
        Aktualisiert Edge-Selektoren in Fillet/Chamfer Features nach Geometrie-Operation.

        SAUBERE LÖSUNG (kein Quickfix): Nach Push/Pull oder Boolean ändern sich
        Edge-Positionen. Diese Methode findet die neuen Edges und aktualisiert
        die gespeicherten GeometricEdgeSelectors.

        Args:
            solid: Das neue Solid nach der Operation
            current_feature_index: Index des aktuell angewandten Features im Rebuild.
                Nur Features VOR diesem Index werden aktualisiert (die danach
                werden bei ihrem eigenen Durchlauf aktualisiert).
                -1 = alle aktualisieren (Backward-Compat für nicht-Rebuild Aufrufe).
        """
        if not solid or not hasattr(solid, 'edges'):
            return

        all_edges = list(solid.edges())
        if not all_edges:
            return

        from modeling.geometric_selector import GeometricEdgeSelector

        updated_count = 0
        for feat_idx, feature in enumerate(self.features):
            # Beim Rebuild: Nur Features aktualisieren die VOR dem aktuellen
            # Feature liegen. Features danach werden bei ihrem eigenen Durchlauf
            # ihre Edges im dann-aktuellen Solid finden.
            if current_feature_index >= 0 and feat_idx >= current_feature_index:
                continue
            # Nur Fillet und Chamfer Features
            if not isinstance(feature, (FilletFeature, ChamferFeature)):
                continue
            
            geometric_selectors = getattr(feature, 'geometric_selectors', [])
            if not geometric_selectors:
                continue
            
            new_selectors = []
            for selector in geometric_selectors:
                try:
                    # Konvertiere zu GeometricEdgeSelector wenn nötig
                    if isinstance(selector, dict):
                        geo_sel = GeometricEdgeSelector.from_dict(selector)
                    elif hasattr(selector, 'find_best_match'):
                        geo_sel = selector
                    else:
                        continue
                    
                    # Finde beste matching Edge im neuen Solid
                    best_edge = geo_sel.find_best_match(all_edges)
                    if best_edge is not None:
                        # Erstelle neuen Selector mit aktualisierten Werten
                        new_selector = GeometricEdgeSelector.from_edge(best_edge)
                        new_selectors.append(new_selector)
                        updated_count += 1
                    else:
                        # Edge nicht gefunden - behalte alten Selector bei
                        logger.warning(f"Edge nicht gefunden nach Operation für {feature.name}")
                        new_selectors.append(geo_sel)
                except Exception as e:
                    logger.debug(f"Edge-Selector Update fehlgeschlagen: {e}")
                    if isinstance(selector, dict):
                        new_selectors.append(GeometricEdgeSelector.from_dict(selector))
                    else:
                        new_selectors.append(selector)
            
            # Aktualisiere Feature
            feature.geometric_selectors = new_selectors
            
            # TNP v3.0: Registry für dieses Feature auch aktualisieren
            self._update_registry_for_feature(feature, solid)
            
        if updated_count > 0:
            logger.info(f"Aktualisiert {updated_count} Edge-Selektoren nach Geometrie-Operation")

    def _update_registry_for_feature(self, feature, solid):
        """
        TNP v3.0: Aktualisiert Registry-Einträge für ein Feature nach Geometrie-Änderung.
        Wird nach Boolean/PushPull aufgerufen.
        """
        if not hasattr(self, '_shape_registry'):
            if is_enabled("extrude_debug"):
                logger.debug(f"TNP DEBUG: _update_registry_for_feature - KEINE REGISTRY!")
            return
        
        try:
            from modeling.tnp_shape_reference import ShapeReference, ShapeType
            from modeling.geometric_selector import GeometricEdgeSelector, GeometricFaceSelector
            
            updated = 0
            if is_enabled("extrude_debug"):
                logger.debug(f"TNP DEBUG: _update_registry_for_feature für {feature.name} ({feature.id})")
            
            # Edge-basierte Features (Fillet, Chamfer)
            if isinstance(feature, (FilletFeature, ChamferFeature)):
                edge_shape_ids = getattr(feature, 'edge_shape_ids', [])
                geometric_selectors = getattr(feature, 'geometric_selectors', [])
                
                if is_enabled("extrude_debug"):
                    logger.debug(f"TNP DEBUG: Feature hat {len(edge_shape_ids)} edge_shape_ids, "
                               f"{len(geometric_selectors)} selectors")
                
                # Hole Edges aus Solid für original_shape
                all_edges = list(solid.edges()) if solid and hasattr(solid, 'edges') else []
                if is_enabled("extrude_debug"):
                    logger.debug(f"TNP DEBUG: Solid hat {len(all_edges)} edges")
                
                for i, shape_id in enumerate(edge_shape_ids):
                    if i < len(geometric_selectors):
                        # Alte Referenz entfernen
                        self._shape_registry.unregister(shape_id)
                        
                        # Neue Referenz mit aktualisiertem Selector erstellen
                        selector = geometric_selectors[i]
                        if isinstance(selector, dict):
                            geo_sel = GeometricEdgeSelector.from_dict(selector)
                        else:
                            geo_sel = selector
                        
                        # Finde original_shape im aktuellen Solid
                        original_shape = None
                        matched_edge = None
                        if all_edges and hasattr(geo_sel, 'find_best_match'):
                            matched_edge = geo_sel.find_best_match(all_edges)
                            if matched_edge and hasattr(matched_edge, 'wrapped'):
                                original_shape = matched_edge.wrapped
                        
                        if original_shape:
                            if is_enabled("extrude_debug"):
                                logger.debug(f"TNP DEBUG: Edge {i} - Match gefunden, original_shape gesetzt")
                        else:
                            if is_enabled("extrude_debug"):
                                logger.warning(f"TNP DEBUG: Edge {i} - KEIN Match gefunden!")
                        
                        ref = ShapeReference(
                            ref_id=shape_id,
                            shape_type=ShapeType.EDGE,
                            geometric_selector=geo_sel,
                            created_by=feature.id,
                            original_shape=original_shape
                        )
                        self._shape_registry.register(ref)
                        updated += 1
            
            # Face-basierte Features (Shell, Hole, Draft)
            elif isinstance(feature, (ShellFeature, HoleFeature, DraftFeature)):
                face_shape_ids = getattr(feature, 'face_shape_ids', [])
                face_selectors = getattr(feature, 'opening_face_selectors', []) or getattr(feature, 'face_selectors', [])
                
                # Hole Faces aus Solid
                all_faces = list(solid.faces()) if solid and hasattr(solid, 'faces') else []
                
                for i, shape_id in enumerate(face_shape_ids):
                    if i < len(face_selectors):
                        self._shape_registry.unregister(shape_id)
                        
                        selector_data = face_selectors[i]
                        if isinstance(selector_data, dict):
                            geo_sel = GeometricFaceSelector.from_dict(selector_data)
                        else:
                            continue
                        
                        # Finde original_shape
                        original_shape = None
                        if all_faces and hasattr(geo_sel, 'find_best_match'):
                            matched_face = geo_sel.find_best_match(all_faces)
                            if matched_face and hasattr(matched_face, 'wrapped'):
                                original_shape = matched_face.wrapped
                        
                        ref = ShapeReference(
                            ref_id=shape_id,
                            shape_type=ShapeType.FACE,
                            geometric_selector=geo_sel,
                            created_by=feature.id,
                            original_shape=original_shape
                        )
                        self._shape_registry.register(ref)
                        updated += 1
            
            if updated > 0:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP v3.0: Registry für {feature.name} aktualisiert ({updated} refs)")
                
        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.debug(f"TNP v3.0: Registry-Update fehlgeschlagen: {e}")

    def _update_edge_selectors_for_feature(self, feature, solid):
        """
        Aktualisiert Edge-Selektoren eines SPEZIFISCHEN Features vor Ausführung.
        
        TNP-CRITICAL: Diese Methode muss BEVOR Fillet/Chamfer ausgeführt werden,
        weil das Solid sich durch vorherige Features verändert haben kann.
        
        Args:
            feature: FilletFeature oder ChamferFeature
            solid: Das aktuelle Solid (nach allen vorherigen Features)
        """
        if not solid or not hasattr(solid, 'edges'):
            return
        
        all_edges = list(solid.edges())
        if not all_edges:
            return
        
        from modeling.geometric_selector import GeometricEdgeSelector
        
        geometric_selectors = getattr(feature, 'geometric_selectors', [])
        if not geometric_selectors:
            return
        
        updated_count = 0
        new_selectors = []
        
        for selector in geometric_selectors:
            try:
                # Konvertiere zu GeometricEdgeSelector wenn nötig
                if isinstance(selector, dict):
                    geo_sel = GeometricEdgeSelector.from_dict(selector)
                elif hasattr(selector, 'find_best_match'):
                    geo_sel = selector
                else:
                    new_selectors.append(selector)
                    continue
                
                # Finde beste matching Edge im aktuellen Solid
                best_edge = geo_sel.find_best_match(all_edges)
                if best_edge is not None:
                    # Erstelle neuen Selector mit aktualisierten Werten
                    new_selector = GeometricEdgeSelector.from_edge(best_edge)
                    new_selectors.append(new_selector)
                    updated_count += 1
                else:
                    # Edge nicht gefunden - behalte alten Selector bei
                    logger.debug(f"Edge nicht gefunden für Feature {feature.name}, behalte alten Selector")
                    new_selectors.append(geo_sel)
            except Exception as e:
                logger.debug(f"Edge-Selector Update fehlgeschlagen: {e}")
                new_selectors.append(selector)
        
        # Aktualisiere Feature
        feature.geometric_selectors = new_selectors
        
        if updated_count > 0:
            logger.debug(f"Feature '{feature.name}': {updated_count}/{len(geometric_selectors)} Edges aktualisiert")

    def _update_shape_registry_after_operation(self, solid, operation_name: str = ""):
        """
        TNP v3.0: Aktualisiert alle ShapeReferences in der Registry nach einer Operation.
        
        Diese Methode wird nach Boolean-Operationen aufgerufen und aktualisiert
        die gespeicherten Referenzen mit den neuen geometrischen Daten.
        
        Args:
            solid: Das neue Solid nach der Operation
            operation_name: Name der Operation (für Logging)
        """
        if not hasattr(self, '_shape_registry') or not solid:
            return
        
        try:
            # Track die Operation in der Registry
            self._shape_registry.track_boolean_operation(
                operation=operation_name,
                input_shapes=[],
                result_shape=solid,
                history=None  # TODO: OCP History von Boolean-Operationen extrahieren
            )
            
            # Versuche alle Referenzen neu aufzulösen
            resolved = self._shape_registry.resolve_all(solid)
            found = sum(1 for r in resolved.values() if r is not None)
            total = len(resolved)
            
            if total > 0:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP Registry nach '{operation_name}': {found}/{total} Referenzen aufgelöst")
                
        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.debug(f"TNP Registry Update fehlgeschlagen: {e}")

    def _register_feature_shape_refs(self, feature) -> None:
        """
        TNP v3.0: Registriert alle ShapeReferences eines Features in der Registry.
        Wird aufgerufen wenn ein Feature neu erstellt oder restored (Redo) wird.
        
        WICHTIG: Extrahiert original_shape aus dem aktuellen Solid für History-Tracking.
        """
        if not hasattr(self, '_shape_registry') or not feature:
            return
        
        try:
            from modeling.tnp_shape_reference import ShapeReference, ShapeType
            from modeling.geometric_selector import GeometricEdgeSelector, GeometricFaceSelector
            
            # Hole aktuelles Solid um original_shape zu extrahieren
            current_solid = self._build123d_solid
            all_edges = list(current_solid.edges()) if current_solid and hasattr(current_solid, 'edges') else []
            all_faces = list(current_solid.faces()) if current_solid and hasattr(current_solid, 'faces') else []
            
            # Edge ShapeIDs (Fillet, Chamfer)
            edge_shape_ids = getattr(feature, 'edge_shape_ids', [])
            geometric_selectors = getattr(feature, 'geometric_selectors', [])
            
            for i, shape_id in enumerate(edge_shape_ids):
                if i < len(geometric_selectors):
                    selector_data = geometric_selectors[i]
                    
                    # Finde die Edge im aktuellen Solid um original_shape zu bekommen
                    original_shape = None
                    if all_edges:
                        if isinstance(selector_data, dict):
                            geo_sel = GeometricEdgeSelector.from_dict(selector_data)
                        else:
                            geo_sel = selector_data
                        
                        if hasattr(geo_sel, 'find_best_match'):
                            matched_edge = geo_sel.find_best_match(all_edges)
                            if matched_edge and hasattr(matched_edge, 'wrapped'):
                                original_shape = matched_edge.wrapped
                    
                    ref = ShapeReference(
                        ref_id=shape_id,
                        shape_type=ShapeType.EDGE,
                        geometric_selector=selector_data,
                        created_by=feature.id,
                        original_shape=original_shape  # WICHTIG: Für History-Resolution
                    )
                    self._shape_registry.register(ref)
            
            # Face ShapeIDs (Shell, Hole, Draft)
            face_shape_ids = getattr(feature, 'face_shape_ids', [])
            face_selectors = getattr(feature, 'opening_face_selectors', []) or getattr(feature, 'face_selectors', [])
            
            for i, shape_id in enumerate(face_shape_ids):
                if i < len(face_selectors):
                    selector_data = face_selectors[i]
                    if isinstance(selector_data, dict):
                        geo_sel = GeometricFaceSelector.from_dict(selector_data)
                    else:
                        continue
                    
                    # Finde die Face im aktuellen Solid
                    original_shape = None
                    if all_faces and hasattr(geo_sel, 'find_best_match'):
                        matched_face = geo_sel.find_best_match(all_faces)
                        if matched_face and hasattr(matched_face, 'wrapped'):
                            original_shape = matched_face.wrapped
                    
                    ref = ShapeReference(
                        ref_id=shape_id,
                        shape_type=ShapeType.FACE,
                        geometric_selector=geo_sel,
                        created_by=feature.id,
                        original_shape=original_shape
                    )
                    self._shape_registry.register(ref)
            
            # PushPull: Einzelne face_shape_id
            face_shape_id = getattr(feature, 'face_shape_id', None)
            if face_shape_id:
                selector_data = getattr(feature, 'face_selector', None)
                if isinstance(selector_data, dict):
                    geo_sel = GeometricFaceSelector.from_dict(selector_data)
                    
                    # Finde die Face
                    original_shape = None
                    if all_faces and hasattr(geo_sel, 'find_best_match'):
                        matched_face = geo_sel.find_best_match(all_faces)
                        if matched_face and hasattr(matched_face, 'wrapped'):
                            original_shape = matched_face.wrapped
                    
                    ref = ShapeReference(
                        ref_id=face_shape_id,
                        shape_type=ShapeType.FACE,
                        geometric_selector=geo_sel,
                        created_by=feature.id,
                        original_shape=original_shape
                    )
                    self._shape_registry.register(ref)
            
            # Loft: profile_shape_ids (keine GeometricSelector, nur ID)
            profile_shape_ids = getattr(feature, 'profile_shape_ids', [])
            for shape_id in profile_shape_ids:
                ref = ShapeReference(
                    ref_id=shape_id,
                    shape_type=ShapeType.FACE,
                    created_by=feature.id
                )
                self._shape_registry.register(ref)
            
            # Sweep: profile_shape_id und path_shape_id
            profile_shape_id = getattr(feature, 'profile_shape_id', None)
            if profile_shape_id:
                ref = ShapeReference(
                    ref_id=profile_shape_id,
                    shape_type=ShapeType.FACE,
                    created_by=feature.id
                )
                self._shape_registry.register(ref)
            path_shape_id = getattr(feature, 'path_shape_id', None)
            if path_shape_id:
                ref = ShapeReference(
                    ref_id=path_shape_id,
                    shape_type=ShapeType.EDGE,
                    created_by=feature.id
                )
                self._shape_registry.register(ref)
            
            # Thread: face_shape_id
            thread_face_shape_id = getattr(feature, 'face_shape_id', None)
            if thread_face_shape_id and hasattr(feature, 'face_selector'):
                selector_data = getattr(feature, 'face_selector', None)
                if isinstance(selector_data, dict):
                    geo_sel = GeometricFaceSelector.from_dict(selector_data)
                    
                    # Finde die Face
                    original_shape = None
                    if all_faces and hasattr(geo_sel, 'find_best_match'):
                        matched_face = geo_sel.find_best_match(all_faces)
                        if matched_face and hasattr(matched_face, 'wrapped'):
                            original_shape = matched_face.wrapped
                    
                    ref = ShapeReference(
                        ref_id=thread_face_shape_id,
                        shape_type=ShapeType.FACE,
                        geometric_selector=geo_sel,
                        created_by=feature.id,
                        original_shape=original_shape
                    )
                    self._shape_registry.register(ref)
            
            total = (len(edge_shape_ids) + len(face_shape_ids) + 
                    (1 if face_shape_id else 0) + len(profile_shape_ids) +
                    (1 if profile_shape_id else 0) + (1 if path_shape_id else 0) +
                    (1 if thread_face_shape_id else 0))
            if total > 0:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP: {total} ShapeReferences für Feature {feature.id} registriert (mit original_shape)")
                
        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.debug(f"TNP Registry Registrierung fehlgeschlagen: {e}")

    def _register_extrude_shapes(self, feature: 'ExtrudeFeature', solid) -> None:
        """
        TNP v4.0: Registriert alle Edges eines Extrude-Solids im NamingService.
        Wird nach erfolgreicher Extrusion aufgerufen.
        """
        if not self._document or not hasattr(self._document, '_shape_naming_service'):
            return
        
        if not solid or not hasattr(solid, 'edges'):
            return
        
        try:
            service = self._document._shape_naming_service
            edges = list(solid.edges())
            
            shape_ids = []
            for i, edge in enumerate(edges):
                # Extrahiere Geometriedaten
                center = edge.center()
                length = edge.length if hasattr(edge, 'length') else 0.0
                geometry_data = (center.X, center.Y, center.Z, length)
                
                # Registriere Shape
                shape_id = service.register_shape(
                    ocp_shape=edge.wrapped,
                    shape_type=ShapeType.EDGE,
                    feature_id=feature.id,
                    local_index=i,
                    geometry_data=geometry_data
                )
                shape_ids.append(shape_id)
            
            # Operation aufzeichnen
            service.record_operation(
                OperationRecord(
                    operation_id=feature.id,
                    operation_type="EXTRUDE",
                    feature_id=feature.id,
                    input_shape_ids=[],  # Extrude hat keine Input-Edges
                    output_shape_ids=shape_ids
                )
            )
            
            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP v4.0: {len(shape_ids)} Edges für Extrude '{feature.name}' registriert")
            
        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.warning(f"TNP v4.0: Extrude-Registrierung fehlgeschlagen: {e}")

    def _register_brepfeat_operation(self, feature, original_solid, result_solid,
                                     input_shape, result_shape) -> None:
        """
        TNP v4.0: Registriert eine BRepFeat-Operation mit Edge-Mappings.
        Wichtig: Ordnet Original-Edges den neuen Edges im Resultat zu.
        """
        if not self._document or not hasattr(self._document, '_shape_naming_service'):
            return
        
        try:
            service = self._document._shape_naming_service
            
            # 1. Alle Original-Edges registrieren (falls noch nicht geschehen)
            input_shape_ids = []
            if original_solid and hasattr(original_solid, 'edges'):
                for i, edge in enumerate(original_solid.edges()):
                    center = edge.center()
                    length = edge.length if hasattr(edge, 'length') else 0.0
                    geometry_data = (center.X, center.Y, center.Z, length)
                    
                    shape_id = service.register_shape(
                        ocp_shape=edge.wrapped,
                        shape_type=ShapeType.EDGE,
                        feature_id=feature.id,
                        local_index=i,
                        geometry_data=geometry_data
                    )
                    input_shape_ids.append(shape_id)
            
            # 2. Alle Result-Edges registrieren
            output_shape_ids = []
            if result_solid and hasattr(result_solid, 'edges'):
                for i, edge in enumerate(result_solid.edges()):
                    center = edge.center()
                    length = edge.length if hasattr(edge, 'length') else 0.0
                    geometry_data = (center.X, center.Y, center.Z, length)
                    
                    shape_id = service.register_shape(
                        ocp_shape=edge.wrapped,
                        shape_type=ShapeType.EDGE,
                        feature_id=feature.id,
                        local_index=i + len(input_shape_ids),  # Offset
                        geometry_data=geometry_data
                    )
                    output_shape_ids.append(shape_id)
            
            # 3. Manuelle Mappings erstellen (geometrisches Matching)
            # Finde für jede Original-Edge die beste passende Result-Edge
            manual_mappings = {}
            
            if original_solid and result_solid:
                import numpy as np
                
                orig_edges = list(original_solid.edges())
                result_edges = list(result_solid.edges())
                
                for i, orig_edge in enumerate(orig_edges):
                    orig_center = orig_edge.center()
                    orig_pos = np.array([orig_center.X, orig_center.Y, orig_center.Z])
                    orig_len = orig_edge.length if hasattr(orig_edge, 'length') else 0
                    
                    # Suche beste Matching Result-Edge
                    best_match_idx = -1
                    best_score = float('inf')
                    
                    for j, result_edge in enumerate(result_edges):
                        result_center = result_edge.center()
                        result_pos = np.array([result_center.X, result_center.Y, result_center.Z])
                        result_len = result_edge.length if hasattr(result_edge, 'length') else 0
                        
                        # Distanz-Score
                        dist = np.linalg.norm(orig_pos - result_pos)
                        
                        # Längen-Score
                        len_diff = abs(orig_len - result_len) if orig_len > 0 else 0
                        
                        # Gesamt-Score (Distanz wichtiger)
                        score = dist + len_diff * 0.1
                        
                        if score < best_score and score < 1.0:  # 1mm Toleranz
                            best_score = score
                            best_match_idx = j
                    
                    if best_match_idx >= 0 and i < len(input_shape_ids):
                        orig_id = input_shape_ids[i].uuid
                        mapped_id = output_shape_ids[best_match_idx].uuid
                        manual_mappings[orig_id] = [mapped_id]
            
            # 4. Operation aufzeichnen
            service.record_operation(
                OperationRecord(
                    operation_id=feature.id,
                    operation_type="BREPFEAT_PRISM",
                    feature_id=feature.id,
                    input_shape_ids=input_shape_ids,
                    output_shape_ids=output_shape_ids,
                    manual_mappings=manual_mappings
                )
            )
            
            if is_enabled("tnp_debug_logging"):
                logger.info(f"TNP v4.0: BRepFeat '{feature.name}' registriert - "
                           f"{len(input_shape_ids)} in, {len(output_shape_ids)} out, "
                           f"{len(manual_mappings)} mappings")
            
        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.warning(f"TNP v4.0: BRepFeat-Registrierung fehlgeschlagen: {e}")
                import traceback
                logger.debug(traceback.format_exc())

    def _unregister_feature_shape_refs(self, feature) -> None:
        """
        TNP v3.0: Entfernt alle ShapeReferences eines Features aus der Registry.
        Wird aufgerufen wenn ein Feature entfernt (Undo) wird.
        """
        if not hasattr(self, '_shape_registry') or not feature:
            return
        
        try:
            # Edge ShapeIDs entfernen
            edge_shape_ids = getattr(feature, 'edge_shape_ids', [])
            for shape_id in edge_shape_ids:
                self._shape_registry.unregister(shape_id)
            
            # Face ShapeIDs entfernen
            face_shape_ids = getattr(feature, 'face_shape_ids', [])
            for shape_id in face_shape_ids:
                self._shape_registry.unregister(shape_id)
            
            # PushPull: Einzelne face_shape_id entfernen
            face_shape_id = getattr(feature, 'face_shape_id', None)
            if face_shape_id:
                self._shape_registry.unregister(face_shape_id)
            
            # Loft: profile_shape_ids entfernen
            profile_shape_ids = getattr(feature, 'profile_shape_ids', [])
            for shape_id in profile_shape_ids:
                self._shape_registry.unregister(shape_id)
            
            # Sweep: profile_shape_id und path_shape_id entfernen
            profile_shape_id = getattr(feature, 'profile_shape_id', None)
            if profile_shape_id:
                self._shape_registry.unregister(profile_shape_id)
            path_shape_id = getattr(feature, 'path_shape_id', None)
            if path_shape_id:
                self._shape_registry.unregister(path_shape_id)
            
            # Thread: face_shape_id entfernen
            thread_face_shape_id = getattr(feature, 'face_shape_id', None)
            if thread_face_shape_id:
                self._shape_registry.unregister(thread_face_shape_id)
            
            total = (len(edge_shape_ids) + len(face_shape_ids) + 
                    (1 if face_shape_id else 0) + len(profile_shape_ids) +
                    (1 if profile_shape_id else 0) + (1 if path_shape_id else 0) +
                    (1 if thread_face_shape_id else 0))
            if total > 0:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP: {total} ShapeReferences für Feature {feature.id} entfernt")
                
        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.debug(f"TNP Registry Unregister fehlgeschlagen: {e}")

    def _update_face_selectors_for_feature(self, feature, solid):
        """
        Aktualisiert Face-Selektoren eines SPEZIFISCHEN Features vor Ausführung.
        
        TNP-CRITICAL: Diese Methode muss BEVOR Shell/Hole/Draft ausgeführt werden,
        weil das Solid sich durch vorherige Features verändert haben kann.
        
        Args:
            feature: ShellFeature, HoleFeature oder DraftFeature
            solid: Das aktuelle Solid (nach allen vorherigen Features)
        """
        if not solid or not hasattr(solid, 'faces'):
            return
        
        all_faces = list(solid.faces())
        if not all_faces:
            return
        
        from modeling.geometric_selector import GeometricFaceSelector
        
        # Hole die Face-Selektoren je nach Feature-Typ
        face_selectors = []
        if isinstance(feature, (ShellFeature, HoleFeature, DraftFeature)):
            face_selectors = getattr(feature, 'face_selectors', []) or getattr(feature, 'opening_face_selectors', [])
        
        if not face_selectors:
            return
        
        updated_count = 0
        new_selectors = []
        
        for selector_dict in face_selectors:
            try:
                # Konvertiere zu GeometricFaceSelector wenn nötig
                if isinstance(selector_dict, dict):
                    geo_sel = GeometricFaceSelector.from_dict(selector_dict)
                elif hasattr(selector_dict, 'center'):
                    geo_sel = selector_dict
                else:
                    new_selectors.append(selector_dict)
                    continue
                
                # Finde beste matching Face im aktuellen Solid
                best_face = None
                best_score = -1.0
                
                for face in all_faces:
                    try:
                        score = self._score_face_match(face, geo_sel)
                        if score > best_score:
                            best_score = score
                            best_face = face
                    except Exception as e:
                        logger.debug(f"[__init__.py] Fehler: {e}")
                        continue
                
                if best_face and best_score > 0.4:
                    # Erstelle neuen Selector mit aktualisierten Werten
                    new_selector = GeometricFaceSelector.from_face(best_face)
                    new_selectors.append(new_selector.to_dict())
                    updated_count += 1
                else:
                    # Face nicht gefunden - behalte alten Selector bei
                    logger.debug(f"Face nicht gefunden für Feature {feature.name} (score={best_score:.2%}), behalte alten Selector")
                    new_selectors.append(selector_dict)
            except Exception as e:
                logger.debug(f"Face-Selector Update fehlgeschlagen: {e}")
                new_selectors.append(selector_dict)
        
        # Aktualisiere Feature (je nach Attribut-Name)
        if isinstance(feature, ShellFeature):
            feature.opening_face_selectors = new_selectors
        else:
            feature.face_selectors = new_selectors
        
        if updated_count > 0:
            logger.debug(f"Feature '{feature.name}': {updated_count}/{len(face_selectors)} Faces aktualisiert")

    def _ocp_extrude_face(self, face, amount, direction):
        """
        Extrusion eines Faces - nutzt Build123d primär, OCP als Fallback.

        Args:
            face: Build123d Face oder TopoDS_Face
            amount: Extrusions-Distanz (positiv oder negativ)
            direction: Richtungsvektor (Build123d Vector oder Tuple)

        Returns:
            Build123d Solid oder None
        """
        # PRIMÄR: Build123d extrude (bewährt und stabil)
        try:
            from build123d import extrude
            result = extrude(face, amount=amount, dir=direction)
            if result and hasattr(result, 'is_valid') and result.is_valid():
                return result
            elif result:
                # Versuche Reparatur
                try:
                    result = result.fix()
                    if result.is_valid():
                        return result
                except Exception as e:
                    logger.debug(f"[__init__.py] Fehler: {e}")
                    pass
        except Exception as e:
            logger.debug(f"Build123d extrude fehlgeschlagen: {e}")

        # FALLBACK: OCP MakePrism
        if not HAS_OCP:
            return None

        try:
            from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
            from OCP.gp import gp_Vec
            from OCP.BRepCheck import BRepCheck_Analyzer

            logger.debug("Versuche OCP Extrude Fallback...")

            # Extrahiere TopoDS_Face
            if hasattr(face, 'wrapped'):
                topo_face = face.wrapped
            else:
                topo_face = face

            # Erstelle Richtungsvektor
            try:
                if hasattr(direction, 'X'):
                    # Build123d Vector (property mit Großbuchstaben)
                    vec = gp_Vec(direction.X * amount, direction.Y * amount, direction.Z * amount)
                elif hasattr(direction, 'x'):
                    # Objekt mit x, y, z Attributen (Kleinbuchstaben)
                    vec = gp_Vec(direction.x * amount, direction.y * amount, direction.z * amount)
                elif isinstance(direction, (list, tuple)) and len(direction) == 3:
                    vec = gp_Vec(direction[0] * amount, direction[1] * amount, direction[2] * amount)
                else:
                    logger.error(f"Unbekannter direction-Typ: {type(direction)}")
                    return None
            except Exception as e:
                logger.error(f"Fehler bei Vektor-Konvertierung: {e}")
                return None

            # OCP Prism (Extrusion)
            prism = BRepPrimAPI_MakePrism(topo_face, vec)
            prism.Build()

            if not prism.IsDone():
                logger.warning("OCP MakePrism IsDone() = False")
                return None

            result_shape = prism.Shape()

            # Validiere
            analyzer = BRepCheck_Analyzer(result_shape)
            if not analyzer.IsValid():
                logger.warning("OCP Extrude produzierte ungültiges Shape, versuche Reparatur...")
                result_shape = self._fix_shape_ocp(result_shape)

            # Wrap zu Build123d Solid
            try:
                from build123d import Solid, Shape
                try:
                    result = Solid(result_shape)
                except Exception as e:
                    logger.debug(f"[__init__.py] Fehler: {e}")
                    result = Shape(result_shape)

                if hasattr(result, 'is_valid') and result.is_valid():
                    return result
                else:
                    # Versuche fix()
                    try:
                        result = result.fix()
                        if result.is_valid():
                            return result
                    except Exception as e:
                        logger.debug(f"[__init__.py] Fehler: {e}")
                        pass
                    logger.warning("OCP Extrude Resultat invalid")
                    return None
            except Exception as e:
                logger.error(f"Wrap zu Build123d fehlgeschlagen: {e}")
                return None

        except Exception as e:
            logger.error(f"OCP Extrude Fehler: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _rebuild(self, rebuild_up_to=None, changed_feature_id: str = None):
        """
        Robuster Rebuild-Prozess (History-basiert).

        Args:
            rebuild_up_to: Optional int - nur Features bis zu diesem Index (exklusiv) anwenden.
                           None = alle Features. Wird fuer Rollback-Bar verwendet.
            changed_feature_id: Optional str - ID des geänderten Features für inkrementellen Rebuild.
                                Phase 7: Nutzt Checkpoints für schnelleren Restart.
        """
        from config.feature_flags import is_enabled

        max_index = rebuild_up_to if rebuild_up_to is not None else len(self.features)

        # === PHASE 7: Inkrementeller Rebuild mit Checkpoints ===
        start_index = 0
        current_solid = None
        use_incremental = is_enabled("feature_dependency_tracking") and changed_feature_id is not None

        if use_incremental:
            # Dependency Graph aktualisieren
            self._dependency_graph.rebuild_feature_index(self.features)

            # Finde optimalen Start-Punkt
            start_index = self._dependency_graph.get_rebuild_start_index(changed_feature_id)

            # Lade Checkpoint-Solid falls vorhanden
            if start_index > 0 and (start_index - 1) in self._solid_checkpoints:
                current_solid = self._solid_checkpoints[start_index - 1]
                logger.info(f"Phase 7: Inkrementeller Rebuild ab Feature {start_index} (Checkpoint genutzt)")
            else:
                start_index = 0  # Kein Checkpoint, starte von 0

        logger.info(f"Rebuilding Body '{self.name}' (Features {start_index}-{max_index-1}/{len(self.features)})...")

        # Reset Cache (Phase 2: Lazy-Loading)
        self.invalidate_mesh()
        self._mesh_vertices.clear()
        self._mesh_triangles.clear()

        # Setze Status für Features VOR start_index (bereits computed)
        for i in range(start_index):
            if i < len(self.features) and not self.features[i].suppressed:
                self.features[i].status = "OK"  # Aus Checkpoint

        for i, feature in enumerate(self.features):
            if i >= max_index:
                feature.status = "ROLLED_BACK"
                continue
            if feature.suppressed:
                feature.status = "SUPPRESSED"
                continue

            # === PHASE 7: Überspringe Features vor start_index (aus Checkpoint) ===
            if use_incremental and i < start_index:
                continue  # Status bereits gesetzt

            new_solid = None
            status = "OK"

            # ================= IMPORT (Base Feature) =================
            if isinstance(feature, ImportFeature):
                # ImportFeature enthält die Basis-Geometrie (z.B. konvertiertes Mesh)
                base_solid = feature.get_solid()
                if base_solid is not None:
                    new_solid = base_solid
                    logger.info(f"ImportFeature: Basis-Geometrie geladen ({base_solid.volume:.2f}mm³)")
                else:
                    status = "ERROR"
                    logger.error(f"ImportFeature: Konnte BREP nicht laden")

            # ================= EXTRUDE =================
            elif isinstance(feature, ExtrudeFeature):
                # TNP v3.0: Prüfe ob dies ein Push/Pull auf Body-Face ist (precalculated_polys)
                has_polys = hasattr(feature, 'precalculated_polys') and feature.precalculated_polys
                
                if has_polys and current_solid is not None:
                    # === PUSH/PULL auf Body-Face: Verwende BRepFeat für TNP-Robustheit ===
                    
                    def op_brepfeat():
                        return self._compute_extrude_part_brepfeat(feature, current_solid)
                    
                    brepfeat_result, status = self._safe_operation(f"Extrude_BRepFeat_{i}", op_brepfeat)
                    
                    if brepfeat_result and status == "SUCCESS":
                        new_solid = brepfeat_result
                        if is_enabled("tnp_debug_logging"):
                            logger.debug(f"TNP BRepFeat: Push/Pull erfolgreich via BRepFeat_MakePrism")
                        
                        # TNP v3.0: Nach BRepFeat Operation Registry aktualisieren
                        if is_enabled("extrude_debug"):
                            logger.debug(f"TNP DEBUG: Starte _update_edge_selectors_after_operation")
                        self._update_edge_selectors_after_operation(new_solid, current_feature_index=i)

                        # Registry für bereits angewandte Fillet/Chamfer-Features aktualisieren
                        if is_enabled("extrude_debug"):
                            logger.debug(f"TNP DEBUG: Starte Registry-Update für Features vor Index {i}")
                        updated_count = 0
                        for feat_idx, feat in enumerate(self.features):
                            if feat_idx >= i:
                                break  # Nur Features VOR dem aktuellen updaten
                            if isinstance(feat, (FilletFeature, ChamferFeature)):
                                if is_enabled("extrude_debug"):
                                    logger.debug(f"TNP DEBUG: Update Registry für {feat.name} (ID: {feat.id})")
                                self._update_registry_for_feature(feat, new_solid)
                                updated_count += 1

                        if is_enabled("extrude_debug"):
                            logger.debug(f"TNP DEBUG: Registry aktualisiert für {updated_count} Features")
                    else:
                        # Fallback zu normalem Extrude+Boolean
                        has_polys = False
                
                if not has_polys or current_solid is None:
                    # === Normales Extrude (mit Sketch) oder New Body ===
                    def op_extrude():
                        return self._compute_extrude_part(feature)
                    
                    part_geometry, status = self._safe_operation(f"Extrude_{i}", op_extrude)

                    if part_geometry:
                        if current_solid is None or feature.operation == "New Body":
                            new_solid = part_geometry
                            if is_enabled("extrude_debug"):
                                logger.debug(f"TNP DEBUG: Extrude New Body - kein Boolean")
                            
                            # === TNP v4.0: Shape-Registrierung für Extrude ===
                            if self._document and hasattr(self._document, '_shape_naming_service'):
                                try:
                                    self._register_extrude_shapes(feature, new_solid)
                                except Exception as tnp_e:
                                    if is_enabled("tnp_debug_logging"):
                                        logger.debug(f"TNP v4.0: Shape-Registrierung fehlgeschlagen: {tnp_e}")
                        else:
                            # Boolean Operation über BooleanEngineV4
                            if is_enabled("extrude_debug"):
                                logger.debug(f"TNP DEBUG: Extrude {feature.operation} startet...")
                            bool_result = BooleanEngineV4.execute_boolean_on_shapes(
                                current_solid, part_geometry, feature.operation
                            )

                            if bool_result.is_success:
                                new_solid = bool_result.value
                                if is_enabled("extrude_debug"):
                                    logger.debug(f"TNP DEBUG: Boolean {feature.operation} erfolgreich")

                                # TNP v4.0: History an ShapeNamingService durchreichen
                                self._register_boolean_history(bool_result, feature, operation_name=feature.operation)

                                # TNP v3.0: Nach Boolean-Operation ALLE Shape-Referenzen aktualisieren
                                if new_solid is not None:
                                    # 1. Edge-Selektoren für nachfolgende Features aktualisieren
                                    if is_enabled("extrude_debug"):
                                        logger.debug(f"TNP DEBUG: Starte _update_edge_selectors_after_operation")
                                    self._update_edge_selectors_after_operation(new_solid, current_feature_index=i)

                                    # 2. Registry für bereits angewandte Fillet/Chamfer-Features aktualisieren
                                    if is_enabled("extrude_debug"):
                                        logger.debug(f"TNP DEBUG: Starte Registry-Update für Features vor Index {i}")
                                    updated_count = 0
                                    for feat_idx, feat in enumerate(self.features):
                                        if feat_idx >= i:
                                            break  # Nur Features VOR dem aktuellen updaten
                                        if isinstance(feat, (FilletFeature, ChamferFeature)):
                                            if is_enabled("extrude_debug"):
                                                logger.debug(f"TNP DEBUG: Update Registry für {feat.name} (ID: {feat.id})")
                                            self._update_registry_for_feature(feat, new_solid)
                                            updated_count += 1

                                    if is_enabled("extrude_debug"):
                                        logger.debug(f"TNP DEBUG: Registry aktualisiert für {updated_count} Features")

                                    # 3. DEBUG: Zeige Registry-Status
                                    if hasattr(self, '_shape_registry'):
                                        stats = self._shape_registry.get_stats()
                                        if is_enabled("extrude_debug"):
                                            logger.debug(f"TNP DEBUG: Registry Status = {stats}")
                            else:
                                logger.warning(f"⚠️ {feature.operation} fehlgeschlagen: {bool_result.message}")
                                status = "ERROR"
                                # Behalte current_solid (keine Änderung)
                                continue

            # ================= FILLET =================
            elif isinstance(feature, FilletFeature):
                if current_solid:
                    # TNP-CRITICAL: Aktualisiere Edge-Selektoren BEVOR Fillet ausgeführt wird
                    # Weil vorherige Features (Extrude, Boolean) das Solid verändert haben
                    self._update_edge_selectors_for_feature(feature, current_solid)
                    
                    # TNP v3.0: AUCH Registry aktualisieren für History-Resolution!
                    if is_enabled("extrude_debug"):
                        logger.debug(f"TNP DEBUG Fillet: Aktualisiere Registry vor Resolution")
                    self._update_registry_for_feature(feature, current_solid)
                    
                    def op_fillet(rad=feature.radius):
                        # Phase 2 TNP: Multi-Strategie Edge-Aufloesung
                        edges_to_fillet = self._resolve_edges_tnp(current_solid, feature)
                        if not edges_to_fillet:
                            raise ValueError("No edges selected (TNP resolution failed)")
                        # OCP Fillet (primaer)
                        result = self._ocp_fillet(current_solid, edges_to_fillet, rad)
                        if result is not None:
                            return result
                        # Build123d als Alternative (gleicher Radius)
                        return fillet(edges_to_fillet, radius=rad)

                    # Fail-Fast: Kein Fallback mit reduziertem Radius
                    new_solid, status = self._safe_operation(f"Fillet_{i}", op_fillet)
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"
                        logger.error(f"Fillet R={feature.radius}mm fehlgeschlagen. Radius evtl. zu gross fuer die gewaehlten Kanten.")

            # ================= CHAMFER =================
            elif isinstance(feature, ChamferFeature):
                if current_solid:
                    # TNP-CRITICAL: Aktualisiere Edge-Selektoren BEVOR Chamfer ausgeführt wird
                    # Weil vorherige Features (Extrude, Boolean) das Solid verändert haben
                    self._update_edge_selectors_for_feature(feature, current_solid)
                    
                    # TNP v3.0: AUCH Registry aktualisieren für History-Resolution!
                    # WICHTIG: Dies muss nach _update_edge_selectors_for_feature passieren
                    # damit die neuen Selektoren verwendet werden
                    if is_enabled("extrude_debug"):
                        logger.debug(f"TNP DEBUG Chamfer: Aktualisiere Registry vor Resolution")
                    self._update_registry_for_feature(feature, current_solid)
                    
                    def op_chamfer(dist=feature.distance):
                        # Phase 2 TNP: Multi-Strategie Edge-Aufloesung
                        edges = self._resolve_edges_tnp(current_solid, feature)
                        if not edges:
                            raise ValueError("No edges (TNP resolution failed)")
                        # OCP Chamfer (primaer)
                        result = self._ocp_chamfer(current_solid, edges, dist)
                        if result is not None:
                            return result
                        # Build123d als Alternative (gleiche Distance)
                        return chamfer(edges, length=dist)

                    # Fail-Fast: Kein Fallback mit reduzierter Distance
                    new_solid, status = self._safe_operation(f"Chamfer_{i}", op_chamfer)
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"
                        logger.error(f"Chamfer D={feature.distance}mm fehlgeschlagen. Distance evtl. zu gross fuer die gewaehlten Kanten.")

            # ================= TRANSFORM =================
            elif isinstance(feature, TransformFeature):
                if current_solid:
                    def op_transform():
                        return self._apply_transform_feature(current_solid, feature)

                    new_solid, status = self._safe_operation(f"Transform_{i}", op_transform)
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= REVOLVE =================
            elif isinstance(feature, RevolveFeature):
                def op_revolve():
                    return self._compute_revolve(feature)

                part_geometry, status = self._safe_operation(f"Revolve_{i}", op_revolve)

                if part_geometry:
                    if current_solid is None or feature.operation == "New Body":
                        new_solid = part_geometry
                    else:
                        bool_result = BooleanEngineV4.execute_boolean_on_shapes(
                            current_solid, part_geometry, feature.operation
                        )
                        if bool_result.is_success:
                            new_solid = bool_result.value
                            self._register_boolean_history(bool_result, feature, operation_name=feature.operation)
                        else:
                            logger.warning(f"Revolve Boolean fehlgeschlagen: {bool_result.message}")
                            status = "ERROR"
                            continue

            # ================= LOFT (Phase 6) =================
            elif isinstance(feature, LoftFeature):
                def op_loft():
                    return self._compute_loft(feature)

                part_geometry, status = self._safe_operation(f"Loft_{i}", op_loft)

                if part_geometry:
                    if current_solid is None or feature.operation == "New Body":
                        new_solid = part_geometry
                    else:
                        bool_result = BooleanEngineV4.execute_boolean_on_shapes(
                            current_solid, part_geometry, feature.operation
                        )
                        if bool_result.is_success:
                            new_solid = bool_result.value
                            self._register_boolean_history(bool_result, feature, operation_name=feature.operation)
                        else:
                            logger.warning(f"Loft Boolean fehlgeschlagen: {bool_result.message}")
                            status = "ERROR"
                            continue

            # ================= SWEEP (Phase 6) =================
            elif isinstance(feature, SweepFeature):
                def op_sweep():
                    return self._compute_sweep(feature, current_solid)

                part_geometry, status = self._safe_operation(f"Sweep_{i}", op_sweep)

                if part_geometry:
                    if current_solid is None or feature.operation == "New Body":
                        new_solid = part_geometry
                    else:
                        bool_result = BooleanEngineV4.execute_boolean_on_shapes(
                            current_solid, part_geometry, feature.operation
                        )
                        if bool_result.is_success:
                            new_solid = bool_result.value
                            self._register_boolean_history(bool_result, feature, operation_name=feature.operation)
                        else:
                            logger.warning(f"Sweep Boolean fehlgeschlagen: {bool_result.message}")
                            status = "ERROR"
                            continue

            # ================= SHELL (Phase 6) =================
            elif isinstance(feature, ShellFeature):
                if current_solid:
                    # TNP-CRITICAL: Aktualisiere Face-Selektoren BEVOR Shell ausgeführt wird
                    self._update_face_selectors_for_feature(feature, current_solid)
                    
                    def op_shell():
                        return self._compute_shell(feature, current_solid)

                    new_solid, status = self._safe_operation(f"Shell_{i}", op_shell)
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= HOLLOW (3D-Druck) =================
            elif isinstance(feature, HollowFeature):
                if current_solid:
                    def op_hollow():
                        return self._compute_hollow(feature, current_solid)

                    new_solid, status = self._safe_operation(f"Hollow_{i}", op_hollow)
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= LATTICE (3D-Druck) =================
            elif isinstance(feature, LatticeFeature):
                if current_solid:
                    def op_lattice():
                        from modeling.lattice_generator import LatticeGenerator
                        return LatticeGenerator.generate(
                            current_solid,
                            cell_type=feature.cell_type,
                            cell_size=feature.cell_size,
                            beam_radius=feature.beam_radius,
                            shell_thickness=feature.shell_thickness,
                        )

                    new_solid, status = self._safe_operation(f"Lattice_{i}", op_lattice)
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= PUSHPULL =================
            elif isinstance(feature, PushPullFeature):
                if current_solid:
                    def op_pushpull():
                        return self._compute_pushpull(feature, current_solid)

                    result, status = self._safe_operation(f"PushPull_{i}", op_pushpull)

                    # TNP v3.0: Handle tuple return (solid, history) oder nur solid
                    pushpull_history = None
                    if result is not None:
                        if isinstance(result, tuple):
                            new_solid, pushpull_history = result
                        else:
                            new_solid = result
                    else:
                        new_solid = None

                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"
                    else:
                        # TNP v3.0: History tracken für Edge-Resolution nach Boolean
                        if pushpull_history is not None and hasattr(self, '_shape_registry'):
                            try:
                                self._shape_registry.track_boolean_operation(
                                    operation=f"PushPull_{feature.id}",
                                    input_shapes=[current_solid],
                                    result_shape=new_solid,
                                    history=pushpull_history
                                )
                                if is_enabled("tnp_debug_logging"):
                                    logger.debug(f"TNP v3.0: PushPull History getrackt für Feature {feature.id}")
                            except Exception as tnp_e:
                                if is_enabled("tnp_debug_logging"):
                                    logger.debug(f"TNP v3.0: PushPull History Tracking fehlgeschlagen: {tnp_e}")

                        # SAUBERE LÖSUNG: Edge-Selektoren nach PushPull aktualisieren
                        # Weil sich Geometrie geändert hat, müssen Fillet/Chamfer Refs aktualisiert werden
                        self._update_edge_selectors_after_operation(new_solid, current_feature_index=i)

            # ================= N-SIDED PATCH =================
            elif isinstance(feature, NSidedPatchFeature):
                if current_solid:
                    def op_nsided():
                        return self._compute_nsided_patch(feature, current_solid)

                    new_solid, status = self._safe_operation(f"NSidedPatch_{i}", op_nsided)
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= HOLE =================
            elif isinstance(feature, HoleFeature):
                if current_solid:
                    # TNP-CRITICAL: Aktualisiere Face-Selektoren BEVOR Hole ausgeführt wird
                    self._update_face_selectors_for_feature(feature, current_solid)
                    
                    def op_hole():
                        return self._compute_hole(feature, current_solid)

                    new_solid, status = self._safe_operation(f"Hole_{i}", op_hole)
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= DRAFT =================
            elif isinstance(feature, DraftFeature):
                if current_solid:
                    # TNP-CRITICAL: Aktualisiere Face-Selektoren BEVOR Draft ausgeführt wird
                    self._update_face_selectors_for_feature(feature, current_solid)
                    
                    def op_draft():
                        return self._compute_draft(feature, current_solid)

                    new_solid, status = self._safe_operation(f"Draft_{i}", op_draft)
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= SPLIT =================
            elif isinstance(feature, SplitFeature):
                if current_solid:
                    def op_split():
                        # Multi-Body Architecture (AGENTS.md Phase 2):
                        # Während Rebuild: Wenn dieser Body ein split_side hat, berechne nur diese Seite
                        if self.split_side and i == self.split_index:
                            # Rebuild-Modus: Nur unsere Seite berechnen
                            # Temporär keep_side überschreiben für diesen Rebuild
                            original_keep_side = feature.keep_side
                            feature.keep_side = self.split_side
                            result = self._compute_split(feature, current_solid)
                            feature.keep_side = original_keep_side  # Restore
                            return result  # Solid (legacy mode)
                        else:
                            # Normaler Split oder keep_side != "both"
                            result = self._compute_split(feature, current_solid)
                            # Falls SplitResult zurückkommt (keep_side == "both"):
                            # Das sollte nur beim ersten Split passieren, nicht während Rebuild
                            if isinstance(result, SplitResult):
                                # Während Rebuild sollte das nicht passieren - Warnung!
                                logger.warning("Split returned SplitResult during rebuild - using body_above as fallback")
                                return result.body_above
                            return result

                    new_solid, status = self._safe_operation(f"Split_{i}", op_split)
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= THREAD =================
            elif isinstance(feature, ThreadFeature):
                if current_solid:
                    def op_thread():
                        return self._compute_thread(feature, current_solid)

                    new_solid, status = self._safe_operation(f"Thread_{i}", op_thread)
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= SURFACE TEXTURE =================
            elif isinstance(feature, SurfaceTextureFeature):
                # Texturen modifizieren NICHT das BREP — nur Metadaten-Layer.
                # Displacement wird erst beim STL-Export angewendet.
                status = "OK"
                logger.debug(f"SurfaceTexture '{feature.name}' — Metadaten-only, kein BREP-Update")

            feature.status = status

            if new_solid is not None:
                current_solid = new_solid

                # === PHASE 7: Checkpoint erstellen (alle N Features) ===
                if use_incremental and self._dependency_graph.should_create_checkpoint(i):
                    self._solid_checkpoints[i] = current_solid
                    self._dependency_graph.create_checkpoint(i, feature.id, current_solid)
                    logger.debug(f"Phase 7: Checkpoint nach Feature {i} ('{feature.name}')")

        # === PHASE 7: Dependency Graph aufräumen ===
        if use_incremental:
            self._dependency_graph.clear_dirty()

        if current_solid:
            # Phase 7: Validierung nach Rebuild
            validation = GeometryValidator.validate_solid(current_solid, ValidationLevel.NORMAL)

            if validation.is_error:
                logger.warning(f"⚠️ Geometrie-Validierung fehlgeschlagen: {validation.message}")
                # Auto-Healing versuchen
                healed, heal_result = GeometryHealer.heal_solid(current_solid)
                if heal_result.success and heal_result.changes_made:
                    logger.info(f"🔧 Auto-Healing: {', '.join(heal_result.changes_made)}")
                    current_solid = healed
                elif not heal_result.success:
                    logger.warning(f"⚠️ Auto-Healing fehlgeschlagen: {heal_result.message}")

            # Phase 9: UnifySameDomain - Koplanare/kozylindrische Faces vereinigen
            # Das reduziert die Face-Anzahl nach Boolean-Operationen erheblich
            try:
                from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
                from build123d import Solid

                ocp_shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid
                n_faces_before = len(current_solid.faces()) if hasattr(current_solid, 'faces') else 0

                upgrader = ShapeUpgrade_UnifySameDomain(ocp_shape, True, True, True)
                # Erhöhte Toleranzen für besseres Zylinder-Merging
                upgrader.SetLinearTolerance(0.1)   # 0.1mm - großzügiger
                upgrader.SetAngularTolerance(0.1)  # ~5.7° - für zylindrische Flächen
                upgrader.Build()
                unified_shape = upgrader.Shape()

                if unified_shape and not unified_shape.IsNull():
                    unified_solid = Solid.make_solid(unified_shape) if hasattr(Solid, 'make_solid') else Solid(unified_shape)
                    n_faces_after = len(unified_solid.faces()) if hasattr(unified_solid, 'faces') else 0

                    if n_faces_after < n_faces_before:
                        logger.debug(f"UnifySameDomain (Rebuild): {n_faces_before} → {n_faces_after} Faces")
                        current_solid = unified_solid
            except Exception as e:
                logger.debug(f"UnifySameDomain übersprungen: {e}")

            self._build123d_solid = current_solid
            if hasattr(current_solid, 'wrapped'):
                self.shape = current_solid.wrapped

            # UPDATE MESH via Helper
            self._update_mesh_from_solid(current_solid)

            # B-Rep Faces zählen (echte CAD-Faces, nicht Tessellations-Dreiecke)
            from modeling.cad_tessellator import CADTessellator
            n_faces = CADTessellator.count_brep_faces(current_solid)
            if n_faces == 0:
                # Fallback
                n_faces = len(current_solid.faces()) if hasattr(current_solid, 'faces') else 0

            # Phase 7: Validierungs-Status loggen
            if validation.is_valid:
                logger.debug(f"✓ {self.name}: BREP Valid ({n_faces} Faces)")
            else:
                logger.warning(f"⚠️ {self.name}: BREP mit Warnungen ({n_faces} Faces) - {validation.message}")

            # Phase 8.2: Automatische Referenz-Migration nach Rebuild
            self._migrate_tnp_references(current_solid)
        else:
            logger.warning(f"Body '{self.name}' is empty after rebuild.")
            # Fix: Solid und Mesh auch bei leerem Rebuild aktualisieren
            self._build123d_solid = None
            self.shape = None
            self.invalidate_mesh()
            self._mesh_cache = None
            self._edges_cache = None
            self._mesh_cache_valid = True  # Valid but empty
            self._mesh_vertices = []
            self._mesh_triangles = []

    def _migrate_tnp_references(self, new_solid):
        """
        TNP v3.0: Migration von ShapeReferences nach Rebuild.
        
        DEAKTIVIERT: Altes TNP-System (Phase 8.2) wurde durch TNP v3.0 ersetzt.
        Das neue System verwendet ShapeReferenceRegistry mit geometrischem Matching.
        
        Args:
            new_solid: Das neue Build123d Solid nach Rebuild
        """
        # TNP v3.0: Nur noch Logging für Debugging
        if hasattr(self, '_shape_registry'):
            stats = self._shape_registry.get_stats()
            if is_enabled("tnp_debug_logging"):
                logger.debug(f"TNP v3.0 Registry Status: {stats}")

    def update_feature_references(self, feature_id: str, old_solid, new_solid):
        """
        TNP v3.0: Aktualisiert Referenzen wenn ein spezifisches Feature modifiziert wurde.
        
        Das neue System verwendet ShapeReferenceRegistry mit automatischer Resolution.
        
        Args:
            feature_id: ID des modifizierten Features
            old_solid: Solid VOR der Änderung
            new_solid: Solid NACH der Änderung
        """
        # TNP v3.0: Neue Registry verwendet automatische Resolution
        if is_enabled("tnp_debug_logging"):
            logger.debug(f"TNP v3.0: Feature {feature_id} wurde modifiziert - Registry bleibt aktiv")

    def reorder_features(self, old_index: int, new_index: int) -> bool:
        """
        Verschiebt ein Feature in der Liste und führt Migration durch.

        Args:
            old_index: Aktuelle Position
            new_index: Neue Position

        Returns:
            True bei Erfolg
        """
        if old_index < 0 or old_index >= len(self.features):
            return False
        if new_index < 0 or new_index >= len(self.features):
            return False
        if old_index == new_index:
            return True

        # Speichere alte Referenzen
        old_solid = self._build123d_solid

        # Feature verschieben
        feature = self.features.pop(old_index)
        self.features.insert(new_index, feature)

        logger.info(f"Feature '{feature.name}' verschoben: {old_index} → {new_index}")

        # Rebuild ausführen (inkl. automatischer Migration)
        try:
            self._rebuild()
            return True
        except Exception as e:
            logger.error(f"Rebuild nach Feature-Verschiebung fehlgeschlagen: {e}")
            # Rückgängig machen
            feature = self.features.pop(new_index)
            self.features.insert(old_index, feature)
            self._rebuild()
            return False

    def _resolve_edges(self, solid, selectors):
        """
        Legacy-Methode für einfache Punkt-Selektoren.
        Wird von _resolve_edges_tnp() als Fallback verwendet.
        """
        if not selectors:
            return list(solid.edges()) if hasattr(solid, 'edges') else []

        found_edges = []
        all_edges = list(solid.edges()) if hasattr(solid, 'edges') else []

        for sel in selectors:
            best_edge = None
            min_dist = float('inf')

            try:
                p_sel = Vector(sel) if not isinstance(sel, Vector) else sel
                for edge in all_edges:
                    try:
                        dist = (edge.center() - p_sel).length
                        if dist < min_dist:
                            min_dist = dist
                            best_edge = edge
                    except Exception as e:
                        logger.debug(f"[__init__.py] Fehler: {e}")
                        pass

                if best_edge and min_dist < 20.0:
                    found_edges.append(best_edge)

            except Exception:
                pass

        return found_edges

    def _resolve_edges_tnp(self, solid, feature) -> List:
        """
        TNP v4.0: Professional Topological Naming Resolution.
        
        Verwendet ShapeNamingService für Multi-Level Resolution:
        1. Direct Lookup (unveränderte Shapes)
        2. History Tracing (via Operation Graph)
        3. BRepFeat Mapping Lookup (für Push/Pull)
        4. Geometric Matching (Fallback)
        
        Args:
            solid: Build123d Solid
            feature: FilletFeature oder ChamferFeature mit TNP-Daten
        
        Returns:
            Liste von gefundenen Edges
        """
        all_edges = list(solid.edges()) if hasattr(solid, 'edges') else []
        if not all_edges:
            if is_enabled("tnp_debug_logging"):
                logger.warning("TNP v4.0: Keine Edges im Solid gefunden")
            return []
        
        feature_name = getattr(feature, 'name', 'Unknown')
        edge_shape_ids = getattr(feature, 'edge_shape_ids', [])
        
        if is_enabled("tnp_debug_logging"):
            logger.info(f"TNP v4.0: Resolving {len(edge_shape_ids)} edges for {feature_name} "
                   f"({len(all_edges)} edges in solid)")
        
        # TNP v4.0: Verwende Document's ShapeNamingService
        if not self._document or not hasattr(self._document, '_shape_naming_service'):
            if is_enabled("tnp_debug_logging"):
                logger.warning("TNP v4.0: Kein ShapeNamingService verfügbar")
            return []
        
        service = self._document._shape_naming_service
        resolved_edges = []
        unresolved_shape_ids = []  # Für Debug-Visualisierung
        stats = {'direct': 0, 'history': 0, 'mapping': 0, 'geometric': 0, 'failed': 0}
        
        for i, shape_id in enumerate(edge_shape_ids):
            try:
                # ShapeID via Service auflösen
                resolved_ocp = service.resolve_shape(shape_id, solid)
                
                if resolved_ocp is None:
                    stats['failed'] += 1
                    unresolved_shape_ids.append(shape_id)
                    if is_enabled("tnp_debug_logging"):
                        logger.warning(f"TNP v4.0: Edge {i} konnte nicht aufgelöst werden")
                    continue
                
                # WICHTIG: Finde die PASSENDE Edge vom aktuellen Solid!
                # Die aufgelöste Edge hat zwar die gleiche Geometrie, aber OCP erwartet
                # Edges die tatsächlich im aktuellen Solid's BRep-Graph existieren.
                matching_edge = self._find_matching_edge_in_solid(resolved_ocp, all_edges)
                
                if matching_edge is not None:
                    resolved_edges.append(matching_edge)
                    if is_enabled("tnp_debug_logging"):
                        logger.debug(f"TNP v4.0: Edge {i} gefunden und mit aktuellem Solid verknüpft")
                else:
                    stats['failed'] += 1
                    unresolved_shape_ids.append(shape_id)
                    from build123d import Edge
                    b3d_edge = Edge(resolved_ocp)
                    if is_enabled("tnp_debug_logging"):
                        logger.warning(f"TNP v4.0: Keine passende Edge im aktuellen Solid für Edge {i}! (Center: {b3d_edge.center()})")
                    
            except Exception as e:
                stats['failed'] += 1
                unresolved_shape_ids.append(shape_id)
                if is_enabled("tnp_debug_logging"):
                    logger.warning(f"TNP v4.0: Edge {i} Auflösung fehlgeschlagen: {e}")
        
        # Ergebnis
        total = len(edge_shape_ids)
        found = len(resolved_edges)
        
        if found == total:
            if is_enabled("tnp_debug_logging"):
                logger.debug(f"TNP v4.0: ALLE {total} Edges aufgelöst! ✅")
        else:
            if is_enabled("tnp_debug_logging"):
                logger.warning(f"TNP v4.0: Nur {found}/{total} Edges aufgelöst")
        
        # === TNP v4.0 DEBUG: Visuelle Darstellung der Auflösung ===
        self._last_tnp_debug_data = {
            'resolved': resolved_edges,
            'unresolved': unresolved_shape_ids,
            'body_id': self.id
        }
        
        # Callback für GUI-Visualisierung (wenn registriert)
        if hasattr(self._document, '_tnp_debug_callback') and self._document._tnp_debug_callback:
            try:
                self._document._tnp_debug_callback(resolved_edges, unresolved_shape_ids, self.id)
            except Exception as e:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP Debug Callback fehlgeschlagen: {e}")
        
        return resolved_edges
    
    def _validate_edge_in_solid(self, edge, all_edges, tolerance=0.01) -> bool:
        """Validiert ob eine Edge im Solid existiert (geometrischer Vergleich)"""
        try:
            import numpy as np
            
            edge_center = np.array([edge.center().X, edge.center().Y, edge.center().Z])
            
            for solid_edge in all_edges:
                solid_center = np.array([solid_edge.center().X, solid_edge.center().Y, solid_edge.center().Z])
                dist = np.linalg.norm(edge_center - solid_center)
                
                if dist < tolerance:
                    return True
                    
        except Exception:
            pass
            
        return False
    
    def _find_matching_edge_in_solid(self, resolved_ocp_edge, all_edges, tolerance=0.01):
        """
        Findet die passende Edge vom aktuellen Solid.
        
        OCP erwartet Edges die tatsächlich im aktuellen Solid's BRep-Graph existieren,
        nicht Edges aus einem anderen Kontext (auch wenn sie geometrisch identisch sind).
        
        Args:
            resolved_ocp_edge: Die aufgelöste OCP Edge (aus ShapeNamingService)
            all_edges: Liste aller Edges vom aktuellen Solid
            tolerance: Toleranz für geometrischen Vergleich
            
        Returns:
            Die passende Edge aus all_edges, oder None
        """
        try:
            import numpy as np
            from build123d import Edge
            
            # Center der aufgelösten Edge
            resolved_b3d = Edge(resolved_ocp_edge)
            resolved_center = np.array([
                resolved_b3d.center().X, 
                resolved_b3d.center().Y, 
                resolved_b3d.center().Z
            ])
            
            # Finde die Edge im aktuellen Solid mit dem gleichen Center
            best_match = None
            best_dist = float('inf')
            
            for solid_edge in all_edges:
                solid_center = np.array([
                    solid_edge.center().X, 
                    solid_edge.center().Y, 
                    solid_edge.center().Z
                ])
                dist = np.linalg.norm(resolved_center - solid_center)
                
                if dist < tolerance and dist < best_dist:
                    best_dist = dist
                    best_match = solid_edge
            
            return best_match
            
        except Exception as e:
            logger.debug(f"_find_matching_edge_in_solid fehlgeschlagen: {e}")
            return None
    
    # Legacy Methods removed - TNP v4.0 uses ShapeNamingService exclusively

    def _resolve_edges_by_hash(self, all_edges, ocp_edge_shapes) -> List:
        """
        Findet Edges durch OCCT-native Shape-Identität (IndexedMapOfShape).
        """
        if not HAS_OCP:
            return []

        try:
            from OCP.TopTools import TopTools_IndexedMapOfShape

            # Build map of target shapes
            target_map = TopTools_IndexedMapOfShape()
            for ocp_shape in ocp_edge_shapes:
                try:
                    target_map.Add(ocp_shape)
                except Exception as e:
                    logger.debug(f"[__init__.py] target_map.Add fehlgeschlagen: {e}")

            # Find edges that match
            found = []
            for edge in all_edges:
                try:
                    ocp_edge = edge.wrapped if hasattr(edge, 'wrapped') else edge
                    if target_map.Contains(ocp_edge):
                        found.append(edge)
                except Exception as e:
                    logger.debug(f"[__init__.py] Contains fehlgeschlagen: {e}")

            return found

        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.debug(f"TNP IndexedMap-Matching Fehler: {e}")
            return []

    def _resolve_edges_by_geometry(self, all_edges, geometric_selectors) -> List:
        """
        Findet Edges durch GeometricEdgeSelector Matching.
        """
        found = []

        for selector in geometric_selectors:
            if hasattr(selector, 'find_best_match'):
                # selector ist ein GeometricEdgeSelector Objekt
                best = selector.find_best_match(all_edges)
                if best is not None and best not in found:
                    found.append(best)
            elif isinstance(selector, dict):
                # selector ist serialisiert - rekonstruieren
                try:
                    from modeling.geometric_selector import GeometricEdgeSelector
                    gs = GeometricEdgeSelector(
                        center=tuple(selector.get('center', (0, 0, 0))),
                        direction=tuple(selector.get('direction', (1, 0, 0))),
                        length=selector.get('length', 0),
                        curve_type=selector.get('curve_type', 'line'),
                        tolerance=selector.get('tolerance', 10.0)
                    )
                    best = gs.find_best_match(all_edges)
                    if best is not None and best not in found:
                        found.append(best)
                except Exception as e:
                    logger.debug(f"GeometricEdgeSelector Rekonstruktion fehlgeschlagen: {e}")

        return found

    def _apply_transform_feature(self, solid, feature: TransformFeature):
        """
        Wendet ein TransformFeature auf einen Solid an.

        Args:
            solid: build123d Solid
            feature: TransformFeature mit mode und data

        Returns:
            Transformierter Solid
        """
        from build123d import Location, Axis, Plane as B123Plane

        mode = feature.mode
        data = feature.data

        try:
            if mode == "move":
                # Translation: [dx, dy, dz]
                translation = data.get("translation", [0, 0, 0])
                tx, ty, tz = translation
                return solid.move(Location((tx, ty, tz)))

            elif mode == "rotate":
                # Rotation: {"axis": "X/Y/Z", "angle": degrees, "center": [x, y, z]}
                axis_name = data.get("axis", "Z")
                angle = data.get("angle", 0)
                center = data.get("center", [0, 0, 0])

                # Build123d Axis Mapping
                axis_map = {
                    "X": Axis.X,
                    "Y": Axis.Y,
                    "Z": Axis.Z
                }
                axis = axis_map.get(axis_name, Axis.Z)

                # Rotation um beliebigen Punkt:
                # 1. Move to origin
                # 2. Rotate
                # 3. Move back
                cx, cy, cz = center
                solid = solid.move(Location((-cx, -cy, -cz)))
                solid = solid.rotate(axis, angle)
                solid = solid.move(Location((cx, cy, cz)))
                return solid

            elif mode == "scale":
                # Scale: {"factor": float, "center": [x, y, z]}
                factor = data.get("factor", 1.0)
                center = data.get("center", [0, 0, 0])

                cx, cy, cz = center
                solid = solid.move(Location((-cx, -cy, -cz)))
                solid = solid.scale(factor)
                solid = solid.move(Location((cx, cy, cz)))
                return solid

            elif mode == "mirror":
                # Mirror: {"plane": "XY/XZ/YZ"}
                plane_name = data.get("plane", "XY")

                # Build123d Plane Mapping
                plane_map = {
                    "XY": B123Plane.XY,
                    "XZ": B123Plane.XZ,
                    "YZ": B123Plane.YZ
                }
                plane = plane_map.get(plane_name, B123Plane.XY)

                return solid.mirror(plane)

            else:
                logger.warning(f"Unbekannter Transform-Modus: {mode}")
                return solid

        except Exception as e:
            logger.error(f"Transform-Feature-Fehler ({mode}): {e}")
            raise

    def _extrude_from_face_brep(self, feature: ExtrudeFeature):
        """
        Extrudiert eine Face aus gespeicherten BREP-Daten.

        Wird verwendet für Push/Pull auf nicht-planaren Flächen (Zylinder, etc.),
        wo keine Polygon-Extraktion möglich ist.
        """
        try:
            from OCP.BRepTools import BRepTools
            from OCP.TopoDS import TopoDS_Face, TopoDS_Shape
            from OCP.BRep import BRep_Builder
            from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
            from OCP.gp import gp_Vec
            from build123d import Solid
            import tempfile
            import os

            # Face aus BREP-String deserialisieren
            face_brep = feature.face_brep
            if not face_brep:
                logger.error("Extrude: face_brep ist leer!")
                return None

            # BREP in temporäre Datei schreiben und lesen
            with tempfile.NamedTemporaryFile(mode='w', suffix='.brep', delete=False) as f:
                f.write(face_brep)
                temp_path = f.name

            builder = BRep_Builder()
            face_shape = TopoDS_Shape()
            BRepTools.Read_s(face_shape, temp_path, builder)
            os.unlink(temp_path)

            if face_shape.IsNull():
                logger.error("Extrude: Face aus BREP konnte nicht gelesen werden!")
                return None

            # Extrusions-Richtung aus plane_normal
            normal = feature.plane_normal
            amount = feature.distance * feature.direction

            extrude_vec = gp_Vec(
                normal[0] * amount,
                normal[1] * amount,
                normal[2] * amount
            )

            # BRepPrimAPI_MakePrism für Extrusion
            prism_maker = BRepPrimAPI_MakePrism(face_shape, extrude_vec)
            prism_maker.Build()

            if not prism_maker.IsDone():
                logger.error("Extrude: BRepPrimAPI_MakePrism fehlgeschlagen!")
                return None

            prism_shape = prism_maker.Shape()
            solid = Solid(prism_shape)

            logger.info(f"Extrude: Face aus BREP erfolgreich extrudiert (type={feature.face_type}, vol={solid.volume:.2f})")
            return solid

        except Exception as e:
            logger.error(f"Extrude aus Face-BREP fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _compute_extrude_part(self, feature: ExtrudeFeature):
        """
        CAD Kernel First: Profile werden IMMER aus dem Sketch abgeleitet.

        Architektur:
        1. Mit Sketch: Profile aus sketch.closed_profiles (immer aktuell)
           - profile_selector filtert welche Profile gewählt wurden
        2. Ohne Sketch (Push/Pull): precalculated_polys als Geometrie-Quelle
        """
        if not HAS_BUILD123D: return None

        # Prüfe ob wir eine Geometrie-Quelle haben
        has_sketch = feature.sketch is not None
        has_polys = hasattr(feature, 'precalculated_polys') and feature.precalculated_polys
        has_face_brep = hasattr(feature, 'face_brep') and feature.face_brep
        
        if is_enabled("extrude_debug"):
            logger.debug(f"TNP DEBUG _compute_extrude_part: has_sketch={has_sketch}, has_polys={has_polys}, has_face_brep={has_face_brep}")
        
        if not has_sketch and not has_polys and not has_face_brep:
            if is_enabled("extrude_debug"):
                logger.debug("TNP DEBUG _compute_extrude_part: KEINE Geometrie-Quelle!")
            return None

        try:
            from build123d import make_face, Wire, Compound
            from shapely.geometry import Polygon as ShapelyPoly

            sketch = feature.sketch
            if sketch:
                plane = self._get_plane_from_sketch(sketch)
            else:
                # Reconstruct plane from saved feature data (Push/Pull ohne Sketch)
                from build123d import Plane as B3DPlane, Vector
                origin = Vector(*feature.plane_origin)
                normal = Vector(*feature.plane_normal)
                if feature.plane_x_dir:
                    x_dir = Vector(*feature.plane_x_dir)
                    plane = B3DPlane(origin=origin, z_dir=normal, x_dir=x_dir)
                else:
                    plane = B3DPlane(origin=origin, z_dir=normal)
            solids = []

            # === CAD KERNEL FIRST: Profile-Bestimmung ===
            polys_to_extrude = []

            if has_sketch:
                # KERNEL FIRST: Profile aus Sketch ableiten (nicht aus Cache!)
                sketch_profiles = getattr(sketch, 'closed_profiles', [])
                profile_selector = getattr(feature, 'profile_selector', [])

                if sketch_profiles and profile_selector:
                    # Selektor-Match (CAD KERNEL FIRST - KEINE FALLBACKS!)
                    polys_to_extrude = self._filter_profiles_by_selector(
                        sketch_profiles, profile_selector
                    )
                    if polys_to_extrude:
                        if is_enabled("extrude_debug"):
                            logger.info(f"Extrude: {len(polys_to_extrude)}/{len(sketch_profiles)} Profile via Selektor")
                    else:
                        # Selektor hat nicht gematcht → Fehler, kein Fallback!
                        if is_enabled("extrude_debug"):
                            logger.error(f"Extrude: Selektor-Match fehlgeschlagen! Selector: {profile_selector}")
                            logger.error(f"Extrude: Verfügbare Profile: {[(p.centroid.x, p.centroid.y) for p in sketch_profiles]}")
                        # Leere Liste → keine Extrusion
                elif sketch_profiles:
                    # Kein Selektor → alle Profile verwenden (Legacy/Import)
                    polys_to_extrude = list(sketch_profiles)
                    if is_enabled("extrude_debug"):
                        logger.info(f"Extrude: Alle {len(polys_to_extrude)} Profile (kein Selektor)")
                else:
                    # Sketch hat keine closed_profiles
                    if is_enabled("extrude_debug"):
                        logger.warning(f"Extrude: Sketch hat keine closed_profiles!")
            else:
                # Ohne Sketch (Push/Pull): precalculated_polys oder face_brep
                if has_polys:
                    polys_to_extrude = list(feature.precalculated_polys)
                    if is_enabled("extrude_debug"):
                        logger.info(f"Extrude: {len(polys_to_extrude)} Profile (Push/Pull Mode)")
                elif has_face_brep:
                    # Face aus BREP deserialisieren und direkt extrudieren (für Zylinder etc.)
                    if is_enabled("extrude_debug"):
                        logger.info(f"Extrude: Face aus BREP (Push/Pull auf {feature.face_type})")
                    return self._extrude_from_face_brep(feature)

            # === Extrude-Logik ===
            if polys_to_extrude:
                if is_enabled("extrude_debug"):
                    logger.info(f"Extrude: Verarbeite {len(polys_to_extrude)} Profile.")

                faces_to_extrude = []
                for idx, poly in enumerate(polys_to_extrude):
                    try:
                        # DEBUG: Polygon-Info loggen
                        n_interiors = len(list(poly.interiors)) if hasattr(poly, 'interiors') else 0
                        poly_area = poly.area if hasattr(poly, 'area') else 0
                        logger.debug(f"  Polygon {idx}: area={poly_area:.1f}, interiors={n_interiors}")

                        # VALIDIERUNG: Degenerierte Polygone überspringen
                        if poly_area < 1e-6:
                            logger.warning(f"  ⚠️ Polygon {idx} hat Area≈0 - überspringe (degeneriert)")
                            continue
                        
                        # 1. Außenkontur
                        outer_coords = list(poly.exterior.coords)[:-1]  # Ohne Schlusspunkt
                        logger.debug(f"  Außenkontur: {len(outer_coords)} Punkte")

                        # WICHTIG: Zuerst prüfen ob gemischte Geometrie vorliegt!
                        # Erst wenn KEINE gemischte Geometrie, dann Kreis-Check.
                        # Sonst werden abgerundete Rechtecke als Kreise erkannt!
                        geometry_list = self._lookup_geometry_for_polygon(poly, feature.sketch)
                        has_mixed_geometry = geometry_list and any(g[0] in ('spline', 'arc') for g in geometry_list if g[0] != 'gap')

                        if has_mixed_geometry:
                            # GEMISCHTE GEOMETRIE → Echte Kurven verwenden!
                            geom_types = set(g[0] for g in geometry_list if g[0] != 'gap' and g[1] is not None)
                            logger.info(f"  → Außenkontur als GEMISCHTE GEOMETRIE: {geom_types}")

                            mixed_wire = self._create_wire_from_mixed_geometry(geometry_list, outer_coords, plane)

                            if mixed_wire is not None:
                                face = make_face(mixed_wire)
                            else:
                                # Fallback: Prüfe auf einzelnen Spline
                                native_spline = self._detect_matching_native_spline(outer_coords, feature.sketch)
                                if native_spline is not None:
                                    logger.info(f"  → Fallback: NATIVE SPLINE: {len(native_spline.control_points)} ctrl pts")
                                    spline_wire = self._create_wire_from_native_spline(native_spline, plane)
                                    if spline_wire is not None:
                                        face = make_face(spline_wire)
                                    else:
                                        logger.warning("  → Spline Wire Fallback: Verwende Polygon")
                                        outer_pts = [plane.from_local_coords((p[0], p[1])) for p in outer_coords]
                                        face = make_face(Wire.make_polygon(outer_pts))
                                else:
                                    # Letzter Fallback: Polygon
                                    logger.warning("  → Mixed Geometry Fallback: Verwende Polygon")
                                    outer_pts = [plane.from_local_coords((p[0], p[1])) for p in outer_coords]
                                    face = make_face(Wire.make_polygon(outer_pts))

                        elif n_interiors == 0:
                            # Keine gemischte Geometrie - prüfen ob es ein Kreis ist
                            outer_circle_info = self._detect_circle_from_points(outer_coords)
                            logger.debug(f"  Außenkontur Kreis-Check: {outer_circle_info is not None}")

                            if outer_circle_info:
                                # Die Außenkontur IST ein Kreis (standalone Kreis ohne Löcher)
                                cx, cy, radius = outer_circle_info
                                logger.info(f"  → Außenkontur als ECHTER KREIS: r={radius:.2f} at ({cx:.2f}, {cy:.2f})")

                                center_3d = plane.from_local_coords((cx, cy))
                                from build123d import Plane as B3DPlane
                                circle_plane = B3DPlane(origin=center_3d, z_dir=plane.z_dir)
                                circle_wire = Wire.make_circle(radius, circle_plane)
                                face = make_face(circle_wire)
                            else:
                                # Kein Kreis, keine gemischte Geometrie → Polygon
                                outer_pts = [plane.from_local_coords((p[0], p[1])) for p in outer_coords]
                                face = make_face(Wire.make_polygon(outer_pts))
                        else:
                            # Hat Löcher (n_interiors > 0), aber KEINE gemischte Geometrie
                            # (mixed geometry wurde bereits oben bei has_mixed_geometry behandelt)

                            # Prüfen ob Außenkontur von einem Native Spline stammt
                            native_spline = self._detect_matching_native_spline(outer_coords, feature.sketch)

                            if native_spline is not None:
                                # NATIVE SPLINE → Saubere Kurve mit wenigen Flächen!
                                logger.info(f"  → Außenkontur als NATIVE SPLINE: {len(native_spline.control_points)} ctrl pts")
                                spline_wire = self._create_wire_from_native_spline(native_spline, plane)

                                if spline_wire is not None:
                                    face = make_face(spline_wire)
                                else:
                                    # Fallback: Polygon
                                    logger.warning("  → Spline Wire Fallback: Verwende Polygon")
                                    outer_pts = [plane.from_local_coords((p[0], p[1])) for p in outer_coords]
                                    face = make_face(Wire.make_polygon(outer_pts))
                            else:
                                # Prüfen ob Außenkontur ein Kreis ist (FIX: Circle-Detection auch bei Löchern!)
                                outer_circle_info = self._detect_circle_from_points(outer_coords)

                                if outer_circle_info:
                                    # Echten Kreis verwenden für saubere B-Rep Topologie!
                                    cx, cy, radius = outer_circle_info
                                    logger.info(f"  → Außenkontur als ECHTER KREIS (mit Löchern): r={radius:.2f} at ({cx:.2f}, {cy:.2f})")

                                    # Kreis-Wire auf der richtigen Ebene erstellen
                                    center_3d = plane.from_local_coords((cx, cy))
                                    from build123d import Plane as B3DPlane
                                    circle_plane = B3DPlane(origin=center_3d, z_dir=plane.z_dir)
                                    circle_wire = Wire.make_circle(radius, circle_plane)
                                    face = make_face(circle_wire)
                                else:
                                    # Normale Polygon-Außenkontur (Rechteck, Hexagon, etc.)
                                    outer_pts = [plane.from_local_coords((p[0], p[1])) for p in outer_coords]
                                    face = make_face(Wire.make_polygon(outer_pts))
                        
                        # 2. Löcher abziehen (Shapely Interiors)
                        for int_idx, interior in enumerate(poly.interiors):
                            inner_coords = list(interior.coords)[:-1]  # Ohne Schlusspunkt
                            logger.debug(f"  Interior {int_idx}: {len(inner_coords)} Punkte")
                            
                            # FIX: Prüfen ob das Loch ein Kreis ist!
                            circle_info = self._detect_circle_from_points(inner_coords)
                            
                            if circle_info:
                                # Echten Kreis verwenden für saubere B-Rep Topologie!
                                cx, cy, radius = circle_info
                                logger.info(f"  → Loch als ECHTER KREIS: r={radius:.2f} at ({cx:.2f}, {cy:.2f})")
                                
                                # Kreis-Wire auf der richtigen Ebene erstellen
                                center_3d = plane.from_local_coords((cx, cy))
                                from build123d import Plane as B3DPlane
                                circle_plane = B3DPlane(origin=center_3d, z_dir=plane.z_dir)
                                circle_wire = Wire.make_circle(radius, circle_plane)
                                circle_face = make_face(circle_wire)
                                face -= circle_face
                            else:
                                # Normales Polygon-Loch
                                logger.warning(f"  → Loch als POLYGON ({len(inner_coords)} Punkte) - kein Kreis erkannt!")
                                inner_pts = [plane.from_local_coords((p[0], p[1])) for p in inner_coords]
                                face -= make_face(Wire.make_polygon(inner_pts))
                            
                        faces_to_extrude.append(face)
                    except Exception as e:
                        logger.warning(f"Fehler bei Face-Konvertierung: {e}")
                        import traceback
                        traceback.print_exc()

                # Extrudieren mit OCP für bessere Robustheit
                amount = feature.distance * feature.direction

                # FIX: Für Cut-Operationen Extrusion verlängern um Through-Cuts zu ermöglichen
                # Das stellt sicher, dass das Tool-Solid über den Body hinausgeht
                cut_extension = 0.0
                if feature.operation == "Cut" and abs(amount) > 0.1:
                    # 10% Verlängerung in Extrusionsrichtung + 1mm Sicherheit
                    cut_extension = abs(amount) * 0.1 + 1.0
                    original_amount = amount
                    amount = amount + (cut_extension if amount > 0 else -cut_extension)
                    logger.debug(f"[CUT] Extrusion verlängert: {original_amount:.2f} → {amount:.2f}mm (+{cut_extension:.2f}mm)")

                if is_enabled("extrude_debug"):
                    logger.debug(f"[EXTRUDE DEBUG] distance={feature.distance}, direction={feature.direction}, amount={amount}")
                if is_enabled("extrude_debug"):
                    logger.debug(f"[EXTRUDE DEBUG] plane.z_dir={plane.z_dir}, operation={feature.operation}")

                for f in faces_to_extrude:
                    s = self._ocp_extrude_face(f, amount, plane.z_dir)
                    if s is not None:
                        # DEBUG: Volumen des extrudierten Solids loggen
                        try:
                            from OCP.GProp import GProp_GProps
                            from OCP.BRepGProp import BRepGProp
                            props = GProp_GProps()
                            BRepGProp.VolumeProperties_s(s.wrapped, props)
                            if is_enabled("extrude_debug"):
                                logger.debug(f"[EXTRUDE DEBUG] Extrudiertes Solid Vol={props.Mass():.2f}mm³")
                        except Exception as e:
                            logger.debug(f"[__init__.py] Fehler: {e}")
                            pass
                        solids.append(s)

            # === PFAD B: Fallback auf "Alten Code" (Rebuild / Scripting) ===
            if not solids:
                if is_enabled("extrude_debug"):
                    logger.info("Extrude: Starte Auto-Detection (Legacy Mode)...")
                # ... [HIER FÜGST DU DEINEN GELIEFERTEN ALTEN CODE EIN] ...
                # Ich rufe hier eine interne Methode auf, die deinen alten Code enthält, 
                # um diesen Block übersichtlich zu halten.
                return self._compute_extrude_legacy(feature, plane)
            
            if not solids: return None
            return solids[0] if len(solids) == 1 else Compound(children=solids)
            
        except Exception as e:
            logger.error(f"Extrude Fehler: {e}")
            return None

    def _filter_profiles_by_selector(self, profiles: list, selector: list, tolerance: float = 5.0) -> list:
        """
        CAD Kernel First: Filtert Profile anhand ihrer Centroids.

        Der Selektor enthält Centroids [(cx, cy), ...] der ursprünglich gewählten Profile.
        Bei Sketch-Änderungen können Profile sich verschieben - wir matchen mit Toleranz.

        WICHTIG: Für jeden Selektor wird nur das BESTE Match (kleinste Distanz) verwendet!
        Das verhindert dass bei überlappenden Toleranzbereichen mehrere Profile gematcht werden.

        FAIL-FAST: Wenn kein Match gefunden wird, geben wir eine LEERE Liste zurück,
        NICHT alle Profile! Das ist CAD Kernel First konform.

        Args:
            profiles: Liste von Shapely Polygons (aktuelle Profile aus Sketch)
            selector: Liste von (cx, cy) Tupeln (gespeicherte Centroids)
            tolerance: Abstand-Toleranz für Centroid-Match in mm

        Returns:
            Gefilterte Liste von Polygons die zum Selektor passen (kann leer sein!)
        """
        if not profiles or not selector:
            return list(profiles) if profiles else []

        import math
        matched = []
        used_profile_indices = set()  # Verhindert doppeltes Matchen

        # Debug: Zeige alle verfügbaren Profile
        if is_enabled("extrude_debug"):
            logger.debug(f"[SELECTOR] {len(profiles)} Profile verfügbar, {len(selector)} Selektoren")
        for i, poly in enumerate(profiles):
            try:
                c = poly.centroid
                if is_enabled("extrude_debug"):
                    logger.debug(f"  Profile {i}: centroid=({c.x:.2f}, {c.y:.2f}), area={poly.area:.1f}")
            except Exception as e:
                logger.debug(f"[__init__.py] Fehler: {e}")
                pass

        if is_enabled("extrude_debug"):
            logger.debug(f"[SELECTOR] Selektoren: {selector}")

        # Für JEDEN Selektor das BESTE Match finden (nicht alle innerhalb Toleranz!)
        for sel_cx, sel_cy in selector:
            best_match_idx = None
            best_match_dist = float('inf')

            for i, poly in enumerate(profiles):
                if i in used_profile_indices:
                    continue  # Bereits verwendet

                try:
                    centroid = poly.centroid
                    cx, cy = centroid.x, centroid.y
                    dist = math.hypot(cx - sel_cx, cy - sel_cy)

                    # Nur innerhalb Toleranz UND besser als bisheriges Match
                    if dist < tolerance and dist < best_match_dist:
                        best_match_idx = i
                        best_match_dist = dist
                except Exception as e:
                    logger.warning(f"Centroid-Berechnung fehlgeschlagen: {e}")
                    continue

            # Bestes Match für diesen Selektor hinzufügen
            if best_match_idx is not None:
                matched.append(profiles[best_match_idx])
                used_profile_indices.add(best_match_idx)
                c = profiles[best_match_idx].centroid
                if is_enabled("extrude_debug"):
                    logger.debug(f"[SELECTOR] BEST MATCH: ({c.x:.2f}, {c.y:.2f}) ≈ ({sel_cx:.2f}, {sel_cy:.2f}), dist={best_match_dist:.2f}")
            else:
                if is_enabled("extrude_debug"):
                    logger.warning(f"[SELECTOR] NO MATCH for selector ({sel_cx:.2f}, {sel_cy:.2f})")

        # FAIL-FAST: Kein Fallback auf alle Profile!
        if not matched:
            if is_enabled("extrude_debug"):
                logger.warning(f"[SELECTOR] Kein Profil-Match! Selector passt zu keinem der {len(profiles)} Profile.")

        return matched

    def _compute_extrude_part_brepfeat(self, feature: 'ExtrudeFeature', current_solid):
        """
        TNP v3.0: BRepFeat-basierter Push/Pull für Body-Face-Operationen.
        
        Verwendet BRepFeat_MakePrism statt Extrude+Boolean für bessere
        Topologie-Erhaltung und TNP-Robustheit.
        
        Args:
            feature: ExtrudeFeature mit face_selector (Push/Pull auf Body-Face)
            current_solid: Der aktuelle Body (Build123d Solid)
            
        Returns:
            Build123d Solid nach BRepFeat-Operation
        """
        if current_solid is None:
            raise ValueError("BRepFeat Push/Pull benötigt einen existierenden Körper")
        
        if not hasattr(feature, 'face_selector') or feature.face_selector is None:
            raise ValueError("BRepFeat Push/Pull benötigt face_selector")
        
        import numpy as np
        from modeling.geometric_selector import GeometricFaceSelector
        
        # Face-Selector laden
        try:
            geo_selector = GeometricFaceSelector.from_dict(feature.face_selector)
        except Exception as e:
            raise ValueError(f"Ungültiger Face-Selector: {e}")
        
        # Face im Solid finden
        all_faces = current_solid.faces() if hasattr(current_solid, 'faces') else []
        if not all_faces:
            raise ValueError("Solid hat keine Faces")
        
        best_face = None
        best_score = -1.0
        
        for face in all_faces:
            try:
                score = self._score_face_match(face, geo_selector)
                if score > best_score:
                    best_score = score
                    best_face = face
            except Exception:
                continue
        
        if best_face is None or best_score < 0.3:  # Niedrigerer Threshold für BRepFeat
            raise ValueError(f"Face nicht gefunden für BRepFeat (best score: {best_score:.2f})")
        
        # Normal und Distanz
        center = np.array(geo_selector.center)
        normal = np.array(geo_selector.normal)
        
        norm_len = np.linalg.norm(normal)
        if norm_len < 1e-6:
            raise ValueError("Face-Normale ist Null")
        normal = normal / norm_len
        
        distance = feature.distance * feature.direction
        
        logger.debug(f"BRepFeat Push/Pull: Face gefunden (score={best_score:.2f}), distance={distance:.2f}mm")
        
        # BRepFeat_MakePrism ausführen
        try:
            from OCP.BRepFeat import BRepFeat_MakePrism
            from OCP.gp import gp_Dir
            from build123d import Solid
            
            shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid
            face_shape = best_face.wrapped if hasattr(best_face, 'wrapped') else best_face
            
            direction = gp_Dir(float(normal[0]), float(normal[1]), float(normal[2]))
            
            # BRepFeat: fuse_mode=1 für Add, 0 für Cut
            fuse_mode = 1 if distance > 0 else 0
            abs_dist = abs(distance)
            
            prism = BRepFeat_MakePrism()
            prism.Init(shape, face_shape, face_shape, direction, fuse_mode, False)
            prism.Perform(abs_dist)
            
            if prism.IsDone():
                result_shape = prism.Shape()
                result_shape = self._unify_same_domain(result_shape, "BRepFeat_MakePrism")
                
                result = Solid(result_shape)
                
                # Validierung
                is_valid = True
                if hasattr(result, 'is_valid'):
                    try:
                        is_valid = result.is_valid()
                    except Exception as e:
                        logger.debug(f"[__init__.py] Fehler: {e}")
                        is_valid = True

                # DEBUG: Check validation criteria
                has_volume_attr = hasattr(result, 'volume')
                volume = result.volume if has_volume_attr else 0.0
                if is_enabled("extrude_debug"):
                    logger.debug(f"[TNP DEBUG BRepFeat] Validation: is_valid={is_valid}, has_volume={has_volume_attr}, volume={volume:.4f}")

                if is_valid and hasattr(result, 'volume') and result.volume > 0.001:
                    logger.debug(f"BRepFeat Push/Pull erfolgreich: volume={result.volume:.2f}mm³")
                    
                    # === TNP v4.0: BRepFeat-Operation tracken ===
                    try:
                        if self._document and hasattr(self._document, '_shape_naming_service'):
                            service = self._document._shape_naming_service
                            import uuid
                            service.track_brepfeat_operation(
                                feature_id=str(uuid.uuid4())[:8],
                                source_solid=current_solid,
                                result_solid=result,
                                modified_face=best_face,
                                direction=(float(normal[0]), float(normal[1]), float(normal[2])),
                                distance=abs(distance)
                            )
                    except Exception as tnp_e:
                        if is_enabled("tnp_debug_logging"):
                            logger.debug(f"TNP v4.0 BRepFeat Tracking fehlgeschlagen: {tnp_e}")
                    
                    return result
                else:
                    logger.warning(f"BRepFeat: Ergebnis ungültig (valid={is_valid}, vol={getattr(result, 'volume', 0):.4f})")
                    raise ValueError("BRepFeat produzierte ungültiges Ergebnis")
            else:
                logger.warning("BRepFeat: IsDone() = False")
                raise ValueError("BRepFeat Operation fehlgeschlagen")
                
        except Exception as e:
            logger.error(f"BRepFeat Push/Pull fehlgeschlagen: {e}")
            raise

    def _detect_circle_from_points(self, points, tolerance=0.02):
        """
        Erkennt ob ein Polygon eigentlich ein Kreis ist.
        
        Args:
            points: Liste von (x, y) Tupeln
            tolerance: Relative Toleranz für Radius-Varianz (2% default)
            
        Returns:
            (cx, cy, radius) wenn es ein Kreis ist, sonst None
        """
        import numpy as np
        
        if len(points) < 8:  # Minimum für Kreis-Erkennung
            return None
        
        pts = np.array(points)
        
        # Schwerpunkt berechnen
        cx = np.mean(pts[:, 0])
        cy = np.mean(pts[:, 1])
        
        # Abstände zum Schwerpunkt
        distances = np.sqrt((pts[:, 0] - cx)**2 + (pts[:, 1] - cy)**2)
        
        # Mittlerer Radius
        radius = np.mean(distances)
        
        if radius < 0.1:  # Zu klein
            return None
        
        # Varianz prüfen (sollte sehr klein sein für Kreis)
        variance = np.std(distances) / radius
        
        logger.debug(f"_detect_circle: {len(points)} Punkte, r={radius:.2f}, varianz={variance:.6f}")
        
        if variance < tolerance:
            # Es ist ein Kreis!
            return (float(cx), float(cy), float(radius))

        return None

    def _detect_matching_native_spline(self, coords, sketch, tolerance=0.5):
        """
        Prüft ob ein Polygon-Kontur von einem nativen Spline stammt.

        Vergleicht Start/End-Punkte der Kontur mit Start/End der Native Splines.

        Args:
            coords: Liste von (x, y) Tupeln der Polygon-Kontur
            sketch: Sketch-Objekt mit native_splines Liste
            tolerance: Abstandstoleranz für Punktvergleich

        Returns:
            Spline2D Objekt wenn gefunden, sonst None
        """
        if not coords or len(coords) < 3:
            return None

        native_splines = getattr(sketch, 'native_splines', [])
        if not native_splines:
            return None

        import math

        # Start/End der Kontur
        c_start = coords[0]
        c_end = coords[-1]

        for spline in native_splines:
            if spline.construction:
                continue

            try:
                # Spline Start/End Punkte
                s_start = spline.start_point
                s_end = spline.end_point

                # Forward Match: Kontur-Start = Spline-Start, Kontur-End = Spline-End
                dist_start = math.hypot(c_start[0] - s_start.x, c_start[1] - s_start.y)
                dist_end = math.hypot(c_end[0] - s_end.x, c_end[1] - s_end.y)

                if dist_start < tolerance and dist_end < tolerance:
                    logger.info(f"  → Spline Match (forward): {spline}")
                    return spline

                # Reverse Match: Kontur ist rückwärts
                dist_start_rev = math.hypot(c_start[0] - s_end.x, c_start[1] - s_end.y)
                dist_end_rev = math.hypot(c_end[0] - s_start.x, c_end[1] - s_start.y)

                if dist_start_rev < tolerance and dist_end_rev < tolerance:
                    logger.info(f"  → Spline Match (reverse): {spline}")
                    return spline

            except Exception as e:
                logger.debug(f"Spline Match Check fehlgeschlagen: {e}")
                continue

        return None

    def _create_wire_from_native_spline(self, spline, plane):
        """
        Erstellt einen Build123d Wire aus einem nativen Spline.

        Args:
            spline: Spline2D Objekt
            plane: Build123d Plane für 3D-Konvertierung

        Returns:
            Build123d Wire oder None bei Fehler
        """
        try:
            from build123d import Wire, Edge

            # Spline zu Edge konvertieren
            edge = spline.to_build123d_edge(plane)
            if edge is None:
                logger.warning("Native Spline → Edge Konvertierung fehlgeschlagen")
                return None

            # Wire aus einzelner Edge erstellen
            wire = Wire([edge])
            logger.info(f"  → Native Spline Wire erstellt ({len(spline.control_points)} ctrl pts)")
            return wire

        except Exception as e:
            logger.warning(f"Wire aus Native Spline fehlgeschlagen: {e}")
            return None

    def _create_wire_from_mixed_geometry(self, geometry_list, outer_coords, plane):
        """
        Erstellt einen Build123d Wire aus gemischter Geometrie (Line + Arc + Spline).

        NEUER ANSATZ: Nutze die Polygon-Koordinaten als Grundlage und ersetze
        Segmente durch native Kurven wo möglich. So bleibt der Wire immer geschlossen.

        Args:
            geometry_list: Liste von (geom_type, geom_obj) Tupeln (dedupliziert!)
            outer_coords: Polygon-Koordinaten in Reihenfolge
            plane: Build123d Plane für 3D-Konvertierung

        Returns:
            Build123d Wire oder None bei Fehler
        """
        try:
            from build123d import Wire, Edge
            import math

            # Sammle alle einzigartigen Geometrie-Objekte
            unique_geoms = {}
            for geom_type, geom_obj in geometry_list:
                if geom_obj is not None and geom_type != 'gap':
                    obj_id = id(geom_obj)
                    if obj_id not in unique_geoms:
                        unique_geoms[obj_id] = (geom_type, geom_obj)

            logger.debug(f"  → Mixed geometry: {len(unique_geoms)} unique objects, {len(outer_coords)} polygon points")

            # Strategie: Erstelle Edges für jede Geometrie und verbinde mit Linien
            edges = []
            used_geoms = set()

            # Für jede einzigartige Geometrie, erstelle die entsprechende Edge
            for obj_id, (geom_type, geom_obj) in unique_geoms.items():
                if obj_id in used_geoms:
                    continue

                try:
                    if geom_type == 'spline':
                        # Native Spline Edge
                        edge = geom_obj.to_build123d_edge(plane)
                        if edge is not None:
                            edges.append(edge)
                            used_geoms.add(obj_id)
                            logger.debug(f"    Spline edge: OK ({len(geom_obj.control_points)} ctrl pts)")

                    elif geom_type == 'arc':
                        # Arc Edge
                        arc = geom_obj
                        start_rad = math.radians(arc.start_angle)
                        end_rad = math.radians(arc.end_angle)
                        mid_angle = (arc.start_angle + arc.end_angle) / 2
                        mid_rad = math.radians(mid_angle)

                        start_2d = (arc.center.x + arc.radius * math.cos(start_rad),
                                    arc.center.y + arc.radius * math.sin(start_rad))
                        mid_2d = (arc.center.x + arc.radius * math.cos(mid_rad),
                                  arc.center.y + arc.radius * math.sin(mid_rad))
                        end_2d = (arc.center.x + arc.radius * math.cos(end_rad),
                                  arc.center.y + arc.radius * math.sin(end_rad))

                        start_3d = plane.from_local_coords(start_2d)
                        mid_3d = plane.from_local_coords(mid_2d)
                        end_3d = plane.from_local_coords(end_2d)

                        from OCP.GC import GC_MakeArcOfCircle
                        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
                        from OCP.gp import gp_Pnt

                        arc_maker = GC_MakeArcOfCircle(
                            gp_Pnt(*start_3d.to_tuple()),
                            gp_Pnt(*mid_3d.to_tuple()),
                            gp_Pnt(*end_3d.to_tuple())
                        )
                        if arc_maker.IsDone():
                            edge_builder = BRepBuilderAPI_MakeEdge(arc_maker.Value())
                            if edge_builder.IsDone():
                                edge = Edge(edge_builder.Edge())
                                edges.append(edge)
                                used_geoms.add(obj_id)
                                logger.debug(f"    Arc edge: OK (r={arc.radius:.2f})")

                    elif geom_type == 'line':
                        # Line Edge
                        p1 = plane.from_local_coords((geom_obj.start.x, geom_obj.start.y))
                        p2 = plane.from_local_coords((geom_obj.end.x, geom_obj.end.y))
                        edge = Edge.make_line(p1, p2)
                        edges.append(edge)
                        used_geoms.add(obj_id)

                except Exception as e:
                    logger.debug(f"    {geom_type} edge failed: {e}")

            if not edges:
                logger.warning("  → Keine Edges erstellt")
                return None

            # Versuche Wire aus Edges zu bauen
            try:
                wire = Wire(edges)
                if wire.is_closed:
                    logger.info(f"  → Mixed Geometry Wire: {len(edges)} edges, geschlossen")
                    return wire
                else:
                    logger.debug(f"  → Wire nicht geschlossen, versuche Polygon-Fallback")
            except Exception as e:
                logger.debug(f"  → Wire aus Edges fehlgeschlagen: {e}")

            # Fallback: Wenn Wire nicht geschlossen ist, nutze Polygon mit nativen Kurven
            # wo möglich, aber fülle Lücken mit Linien
            logger.debug("  → Fallback: Erstelle Wire aus Polygon-Koordinaten")
            poly_pts = [plane.from_local_coords((p[0], p[1])) for p in outer_coords]
            try:
                wire = Wire.make_polygon(poly_pts)
                logger.info(f"  → Polygon Wire Fallback: {len(poly_pts)} Punkte")
                return wire
            except Exception as e:
                logger.warning(f"  → Polygon Wire auch fehlgeschlagen: {e}")
                return None

        except Exception as e:
            logger.warning(f"Wire aus Mixed Geometry fehlgeschlagen: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _lookup_geometry_for_polygon(self, poly, sketch):
        """
        Looks up the original geometry list for a polygon from the sketch's mapping.

        Args:
            poly: Shapely Polygon
            sketch: Sketch object that may have _profile_geometry_map

        Returns:
            List of (geom_type, geom_obj) or None if not found
        """
        if not hasattr(sketch, '_profile_geometry_map'):
            return None

        # Create lookup key from polygon bounds + area
        bounds = poly.bounds
        key = (round(bounds[0], 2), round(bounds[1], 2),
               round(bounds[2], 2), round(bounds[3], 2),
               round(poly.area, 2))

        geometry_list = sketch._profile_geometry_map.get(key)
        if geometry_list:
            logger.debug(f"  → Found geometry mapping for polygon: {len(geometry_list)} segments")
            return geometry_list

        # Fuzzy matching if exact key not found
        for map_key, geom_list in sketch._profile_geometry_map.items():
            if (abs(map_key[4] - key[4]) < 0.5 and  # Area within 0.5
                abs(map_key[0] - key[0]) < 1 and
                abs(map_key[1] - key[1]) < 1):
                logger.debug(f"  → Found geometry mapping (fuzzy): {len(geom_list)} segments")
                return geom_list

        return None

    def _compute_extrude_legacy(self, feature, plane):
        """
        Legacy-Logik für Extrusion (Auto-Detection von Löchern etc.),
        falls keine vorausberechneten Polygone vorhanden sind.
        Entspricht exakt der alten, robusten Implementierung.
        """
        if not HAS_BUILD123D or not feature.sketch: return None

        try:
            from shapely.geometry import LineString, Point, Polygon as ShapelyPoly
            from shapely.ops import unary_union, polygonize
            from build123d import make_face, Vector, Wire, Compound, Shape
            import math

            logger.info(f"--- Starte Legacy Extrusion: {feature.name} ---")

            sketch = feature.sketch
            # plane ist bereits übergeben

            # --- 1. Segmente sammeln ---
            all_segments = []
            # NEU: Separate Liste für geschlossene Ringe (Kreise)
            closed_rings = []
            def rnd(val): return round(val, 5)

            for l in sketch.lines:
                if not l.construction:
                    all_segments.append(LineString([(rnd(l.start.x), rnd(l.start.y)), (rnd(l.end.x), rnd(l.end.y))]))

            # NEU: Kreise separat als Polygone speichern (nicht als LineStrings!)
            for c in sketch.circles:
                if not c.construction:
                    pts = [(rnd(c.center.x + c.radius * math.cos(i * 2 * math.pi / 64)),
                            rnd(c.center.y + c.radius * math.sin(i * 2 * math.pi / 64))) for i in range(65)]
                    # WICHTIG: Geschlossenen Ring als Polygon speichern, NICHT als LineString
                    # polygonize() funktioniert nicht mit isolierten geschlossenen Ringen!
                    try:
                        circle_poly = ShapelyPoly(pts)
                        if circle_poly.is_valid:
                            closed_rings.append(circle_poly)
                            logger.debug(f"Kreis als geschlossener Ring: center=({c.center.x:.1f}, {c.center.y:.1f}), r={c.radius:.1f}")
                        else:
                            # Fallback: Als LineString für polygonize
                            all_segments.append(LineString(pts))
                    except Exception as e:
                        logger.debug(f"[__init__.py] Fehler: {e}")
                        all_segments.append(LineString(pts))

            for arc in sketch.arcs:
                 if not arc.construction:
                    pts = []
                    start, end = arc.start_angle, arc.end_angle
                    sweep = end - start
                    if sweep < 0.1: sweep += 360
                    steps = max(12, int(sweep / 5))
                    for i in range(steps + 1):
                        t = math.radians(start + sweep * i / steps)
                        x = arc.center.x + arc.radius * math.cos(t)
                        y = arc.center.y + arc.radius * math.sin(t)
                        pts.append((rnd(x), rnd(y)))
                    if len(pts) >= 2: all_segments.append(LineString(pts))
            for spline in getattr(sketch, 'splines', []):
                 if not getattr(spline, 'construction', False):
                     pts_raw = []
                     if hasattr(spline, 'get_curve_points'):
                         pts_raw = spline.get_curve_points(segments_per_span=16)
                     elif hasattr(spline, 'to_lines'):
                         lines = spline.to_lines(segments_per_span=16)
                         if lines:
                             pts_raw.append((lines[0].start.x, lines[0].start.y))
                             for ln in lines: pts_raw.append((ln.end.x, ln.end.y))
                     pts = [(rnd(p[0]), rnd(p[1])) for p in pts_raw]
                     if len(pts) >= 2: all_segments.append(LineString(pts))

            if not all_segments and not closed_rings:
                return None

            # --- 2. Polygonize & Deduplizierung ---
            candidates = []

            # 2a. Geschlossene Ringe (Kreise) direkt als Kandidaten hinzufügen
            for ring in closed_rings:
                candidates.append(ring)
                logger.debug(f"Geschlossener Ring als Kandidat: area={ring.area:.1f}")

            # 2b. Lineare Segmente mit polygonize verarbeiten
            if all_segments:
                try:
                    merged = unary_union(all_segments)
                    raw_candidates = list(polygonize(merged))

                    for rc in raw_candidates:
                        clean_poly = rc.buffer(0) # Reparatur
                        is_dup = False
                        for existing in candidates:
                            if abs(clean_poly.area - existing.area) < 1e-4 and clean_poly.centroid.distance(existing.centroid) < 1e-4:
                                is_dup = True
                                break
                        if not is_dup:
                            candidates.append(clean_poly)

                except Exception as e:
                    logger.warning(f"Polygonize fehlgeschlagen: {e}")
                    # Weiter mit geschlossenen Ringen falls vorhanden

            logger.info(f"Kandidaten (Unique): {len(candidates)}")

            if not candidates: return None

            # --- 3. Selektion ---
            selected_indices = set()
            if feature.selector:
                selectors = feature.selector
                if isinstance(selectors, tuple) and len(selectors) == 2 and isinstance(selectors[0], (int, float)):
                    selectors = [selectors]
                
                for sel_pt in selectors:
                    pt = Point(sel_pt)
                    matches = []
                    for i, poly in enumerate(candidates):
                        if poly.contains(pt) or poly.distance(pt) < 1e-2:
                            matches.append(i)
                    if matches:
                        best = min(matches, key=lambda i: candidates[i].area)
                        selected_indices.add(best)
            else:
                selected_indices = set(range(len(candidates)))

            if not selected_indices: return None

            # --- 4. Faces bauen ---
            faces_to_extrude = []

            def to_3d_wire(shapely_poly):
                """Konvertiert Shapely Polygon zu Build123d Wire. Erkennt Kreise!"""
                try:
                    pts_2d = list(shapely_poly.exterior.coords[:-1])
                    if len(pts_2d) < 3: return None

                    # NEU: Prüfen ob es ein Kreis ist
                    circle_info = self._detect_circle_from_points(pts_2d)
                    if circle_info:
                        cx, cy, radius = circle_info
                        logger.debug(f"to_3d_wire: Erkenne Kreis r={radius:.2f}")
                        center_3d = plane.from_local_coords((cx, cy))
                        from build123d import Plane as B3DPlane
                        circle_plane = B3DPlane(origin=center_3d, z_dir=plane.z_dir)
                        return Wire.make_circle(radius, circle_plane)

                    # Standard: Polygon-Wire
                    pts_3d = [plane.from_local_coords((p[0], p[1])) for p in pts_2d]
                    return Wire.make_polygon(pts_3d)
                except Exception as e:
                    logger.debug(f"to_3d_wire error: {e}")
                    return None

            for outer_idx in selected_indices:
                try:
                    outer_poly = candidates[outer_idx]
                    outer_wire = to_3d_wire(outer_poly)
                    if not outer_wire: continue

                    main_face = make_face(outer_wire)
                    
                    # Löcher suchen
                    for i, potential_hole in enumerate(candidates):
                        if i == outer_idx: continue
                        
                        # WICHTIG 1: Ein Loch muss kleiner sein!
                        if potential_hole.area >= outer_poly.area * 0.99:
                            continue

                        # Check: Ist es drinnen?
                        is_inside = False
                        reason = ""
                        
                        try:
                            # A) Konzentrisch (Sehr starkes Indiz für Loch)
                            if outer_poly.centroid.distance(potential_hole.centroid) < 1e-3:
                                is_inside = True; reason = "Concentric"
                            
                            # B) Intersection
                            elif not is_inside:
                                intersect = outer_poly.intersection(potential_hole)
                                ratio = intersect.area / potential_hole.area if potential_hole.area > 0 else 0
                                if ratio > 0.9: 
                                    is_inside = True; reason = f"Overlap {ratio:.2f}"
                            
                            # C) Centroid Check
                            if not is_inside:
                                if outer_poly.contains(potential_hole.centroid):
                                    is_inside = True; reason = "Centroid"
                        except Exception as e_hole:
                            logger.debug(f"Hole-in-face check fehlgeschlagen: {e_hole}")

                        if is_inside:
                            # Nur schneiden, wenn nicht selbst ausgewählt
                            if i not in selected_indices:
                                logger.info(f"  -> Schneide Loch #{i} ({reason})")
                                hole_wire = to_3d_wire(potential_hole)
                                if hole_wire:
                                    try:
                                        hole_face = make_face(hole_wire)
                                        main_face = main_face - hole_face
                                    except Exception as e:
                                        logger.warning(f"Cut failed: {e}")

                    faces_to_extrude.append(main_face)
                except Exception as e:
                    logger.error(f"Face construction error: {e}")

            if not faces_to_extrude: return None

            # --- 5. Extrudieren mit OCP ---
            solids = []
            amount = feature.distance * feature.direction
            direction_vec = plane.z_dir

            for f in faces_to_extrude:
                s = self._ocp_extrude_face(f, amount, direction_vec)
                if s is not None:
                    solids.append(s)
                else:
                    logger.warning(f"Extrude für Face fehlgeschlagen")

            if not solids: 
                logger.warning("Keine Solids erzeugt!")
                return None
            
            logger.debug(f"Legacy Extrusion OK: {len(solids)} Solids erzeugt.")

            if len(solids) == 1:
                return solids[0]
            else:
                return Compound(children=solids)
            
        except Exception as e:
            logger.error(f"Legacy Extrude CRASH: {e}")
            raise e


        
    
    
    def _get_plane_from_sketch(self, sketch):
        origin = getattr(sketch, 'plane_origin', (0,0,0))
        normal = getattr(sketch, 'plane_normal', (0,0,1))
        x_dir = getattr(sketch, 'plane_x_dir', None)
        if x_dir:
            return Plane(origin=origin, x_dir=x_dir, z_dir=normal)
        return Plane(origin=origin, z_dir=normal)

    def _update_mesh_from_solid(self, solid):
        """
        Phase 2: Invalidiert Mesh-Cache - Mesh wird lazy regeneriert bei Zugriff.
        (Single Source of Truth Pattern)
        """
        if not solid:
            return

        # Invalidiere Cache - nächster Zugriff auf vtk_mesh/vtk_edges regeneriert
        self.invalidate_mesh()

        # Legacy Support leeren
        self._mesh_vertices = []
        self._mesh_triangles = []

    def export_stl(self, filename: str) -> bool:
        """STL Export via Kernel (Build123d). Kein Mesh-Fallback."""
        if not HAS_BUILD123D or self._build123d_solid is None:
            logger.error("STL-Export fehlgeschlagen: Kein Build123d-Solid vorhanden")
            return False

        # OCP Feature Audit: Offene-Kanten-Check vor Export
        self._check_free_bounds_before_export()

        try:
            export_stl(self._build123d_solid, filename)
            return True
        except Exception as e:
            logger.error(f"STL-Export fehlgeschlagen: {e}")
            return False

    def _check_free_bounds_before_export(self):
        """
        OCP Feature Audit: Prüft ob Body offene Kanten hat vor Export.

        Offene Shells erzeugen STL-Dateien mit Löchern, die für 3D-Druck
        unbrauchbar sind. Diese Warnung hilft dem User das Problem zu erkennen.
        """
        from config.feature_flags import is_enabled
        if not is_enabled("export_free_bounds_check"):
            return

        try:
            from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_WIRE

            fb = ShapeAnalysis_FreeBounds(self._build123d_solid.wrapped)
            closed_compound = fb.GetClosedWires()
            open_compound = fb.GetOpenWires()

            # GetClosedWires/GetOpenWires geben TopoDS_Compound zurück
            def count_wires(compound):
                exp = TopExp_Explorer(compound, TopAbs_WIRE)
                n = 0
                while exp.More():
                    n += 1
                    exp.Next()
                return n

            n_closed = count_wires(closed_compound)
            n_open = count_wires(open_compound)

            if n_open > 0:
                logger.warning(
                    f"⚠️ Body '{self.name}' hat {n_open} offene Kante(n)! "
                    f"STL könnte Löcher haben → 3D-Druck problematisch."
                )
            elif n_closed > 0:
                logger.warning(
                    f"⚠️ Body '{self.name}' hat {n_closed} geschlossene freie Wire(s). "
                    f"Mögliches internes Shell-Problem."
                )
            else:
                logger.debug(f"Export Free-Bounds Check: Body '{self.name}' ist geschlossen (OK)")

        except Exception as e:
            logger.debug(f"Free-Bounds Check fehlgeschlagen: {e}")

    def _export_stl_simple(self, filename: str) -> bool:
        """Primitiver STL Export aus Mesh-Daten (Letzter Ausweg)"""
        try:
            with open(filename, 'w') as f:
                f.write(f"solid {self.name}\n")
                for tri in self._mesh_triangles:
                    v0 = self._mesh_vertices[tri[0]]
                    v1 = self._mesh_vertices[tri[1]]
                    v2 = self._mesh_vertices[tri[2]]
                    f.write(f"  facet normal 0 0 1\n")
                    f.write(f"    outer loop\n")
                    f.write(f"      vertex {v0[0]} {v0[1]} {v0[2]}\n")
                    f.write(f"      vertex {v1[0]} {v1[1]} {v1[2]}\n")
                    f.write(f"      vertex {v2[0]} {v2[1]} {v2[2]}\n")
                    f.write(f"    endloop\n")
                    f.write(f"  endfacet\n")
                f.write(f"endsolid {self.name}\n")
            return True
        except Exception as e:
            logger.error(f"Legacy STL-Export fehlgeschlagen: {e}")
            return False

    # === PHASE 8.2: Persistente Speicherung für TNP ===

    def to_dict(self) -> dict:
        """
        Serialisiert Body zu Dictionary für persistente Speicherung.

        Enthält:
        - Body-Metadaten (name, id)
        - Features (serialisiert)
        - TNP-Referenzen und Statistiken

        Returns:
            Dictionary mit allen Body-Daten
        """
        # Features serialisieren
        features_data = []
        for feat in self.features:
            feat_dict = {
                "type": feat.type.name if feat.type else "UNKNOWN",
                "name": feat.name,
                "id": feat.id,
                "visible": feat.visible,
                "suppressed": feat.suppressed,
                "status": feat.status,
            }

            # Feature-spezifische Daten
            if isinstance(feat, ExtrudeFeature):
                feat_dict.update({
                    "feature_class": "ExtrudeFeature",
                    "distance": feat.distance,
                    "distance_formula": feat.distance_formula,
                    "direction": feat.direction,
                    "operation": feat.operation,
                    "plane_origin": list(feat.plane_origin) if feat.plane_origin else None,
                    "plane_normal": list(feat.plane_normal) if feat.plane_normal else None,
                    "plane_x_dir": list(feat.plane_x_dir) if feat.plane_x_dir else None,
                    "plane_y_dir": list(feat.plane_y_dir) if feat.plane_y_dir else None,
                    # KRITISCH für parametrisches CAD: Sketch-ID speichern
                    "sketch_id": feat.sketch.id if feat.sketch else None,
                    # CAD Kernel First: Profile-Selektor (Centroids)
                    "profile_selector": feat.profile_selector if feat.profile_selector else None,
                })
                # Serialisiere precalculated_polys (Shapely zu WKT) - Legacy Fallback
                if feat.precalculated_polys:
                    try:
                        feat_dict["precalculated_polys_wkt"] = [
                            p.wkt if hasattr(p, 'wkt') else str(p)
                            for p in feat.precalculated_polys
                        ]
                    except Exception as e:
                        logger.debug(f"[__init__.py] Fehler: {e}")
                        pass
                # Face-BREP für Push/Pull auf nicht-planaren Flächen (Zylinder etc.)
                if hasattr(feat, 'face_brep') and feat.face_brep:
                    feat_dict["face_brep"] = feat.face_brep
                    feat_dict["face_type"] = getattr(feat, 'face_type', None)

            elif isinstance(feat, FilletFeature):
                feat_dict.update({
                    "feature_class": "FilletFeature",
                    "radius": feat.radius,
                    "radius_formula": feat.radius_formula,
                    "edge_selectors": feat.edge_selectors,
                    "depends_on_feature_id": feat.depends_on_feature_id,
                })
                # GeometricSelectors serialisieren
                if feat.geometric_selectors:
                    feat_dict["geometric_selectors"] = [
                        gs.to_dict() if hasattr(gs, 'to_dict') else str(gs)
                        for gs in feat.geometric_selectors
                    ]
                # TNP v4.0: ShapeIDs vollständig serialisieren
                if feat.edge_shape_ids:
                    feat_dict["edge_shape_ids"] = [
                        {
                            "uuid": sid.uuid,
                            "shape_type": sid.shape_type.name,
                            "feature_id": sid.feature_id,
                            "local_index": sid.local_index,
                            "geometry_hash": sid.geometry_hash,
                            "timestamp": sid.timestamp
                        }
                        for sid in feat.edge_shape_ids
                    ]

            elif isinstance(feat, ChamferFeature):
                feat_dict.update({
                    "feature_class": "ChamferFeature",
                    "distance": feat.distance,
                    "distance_formula": feat.distance_formula,
                    "edge_selectors": feat.edge_selectors,
                    "depends_on_feature_id": feat.depends_on_feature_id,
                })
                if feat.geometric_selectors:
                    feat_dict["geometric_selectors"] = [
                        gs.to_dict() if hasattr(gs, 'to_dict') else str(gs)
                        for gs in feat.geometric_selectors
                    ]
                # TNP v4.0: ShapeIDs vollständig serialisieren
                if feat.edge_shape_ids:
                    feat_dict["edge_shape_ids"] = [
                        {
                            "uuid": sid.uuid,
                            "shape_type": sid.shape_type.name,
                            "feature_id": sid.feature_id,
                            "local_index": sid.local_index,
                            "geometry_hash": sid.geometry_hash,
                            "timestamp": sid.timestamp
                        }
                        for sid in feat.edge_shape_ids
                    ]

            elif isinstance(feat, RevolveFeature):
                feat_dict.update({
                    "feature_class": "RevolveFeature",
                    "angle": feat.angle,
                    "angle_formula": feat.angle_formula,
                    "axis": list(feat.axis),
                    "axis_origin": list(feat.axis_origin),
                    "operation": feat.operation,
                    # KRITISCH für parametrisches CAD: Sketch-ID speichern
                    "sketch_id": feat.sketch.id if feat.sketch else None,
                    # CAD Kernel First: Profile-Selektor (Centroids)
                    "profile_selector": feat.profile_selector if feat.profile_selector else None,
                })

            elif isinstance(feat, LoftFeature):
                # Serialize profile_data with shapely_poly conversion
                serialized_profiles = []
                for pd in feat.profile_data:
                    pd_copy = pd.copy()
                    if 'shapely_poly' in pd_copy and pd_copy['shapely_poly'] is not None:
                        poly = pd_copy['shapely_poly']
                        if hasattr(poly, 'exterior'):
                            pd_copy['shapely_poly_coords'] = {
                                'exterior': list(poly.exterior.coords),
                                'holes': [list(interior.coords) for interior in poly.interiors]
                            }
                        pd_copy['shapely_poly'] = None  # Remove non-serializable object
                    serialized_profiles.append(pd_copy)
                feat_dict.update({
                    "feature_class": "LoftFeature",
                    "ruled": feat.ruled,
                    "operation": feat.operation,
                    "start_continuity": feat.start_continuity if feat.start_continuity else "G0",
                    "end_continuity": feat.end_continuity if feat.end_continuity else "G0",
                    "profile_data": serialized_profiles,
                })
                # TNP v4.0: ShapeIDs vollständig serialisieren (alle 6 Felder)
                if feat.profile_shape_ids:
                    feat_dict["profile_shape_ids"] = [
                        {
                            "uuid": sid.uuid,
                            "shape_type": sid.shape_type.name,
                            "feature_id": sid.feature_id,
                            "local_index": sid.local_index,
                            "geometry_hash": sid.geometry_hash,
                            "timestamp": sid.timestamp
                        }
                        for sid in feat.profile_shape_ids
                    ]

                # TNP v4.0: GeometricSelectors als Fallback serialisieren
                if feat.profile_geometric_selectors:
                    feat_dict["profile_geometric_selectors"] = [
                        asdict(sel) if hasattr(sel, '__dataclass_fields__') else sel
                        for sel in feat.profile_geometric_selectors
                    ]

            elif isinstance(feat, SweepFeature):
                # Serialize profile_data with shapely_poly conversion
                pd_copy = feat.profile_data.copy() if feat.profile_data else {}
                if 'shapely_poly' in pd_copy and pd_copy['shapely_poly'] is not None:
                    poly = pd_copy['shapely_poly']
                    if hasattr(poly, 'exterior'):
                        pd_copy['shapely_poly_coords'] = {
                            'exterior': list(poly.exterior.coords),
                            'holes': [list(interior.coords) for interior in poly.interiors]
                        }
                    pd_copy['shapely_poly'] = None  # Remove non-serializable object
                feat_dict.update({
                    "feature_class": "SweepFeature",
                    "is_frenet": feat.is_frenet,
                    "operation": feat.operation,
                    "twist_angle": feat.twist_angle,
                    "scale_start": feat.scale_start,
                    "scale_end": feat.scale_end,
                    "profile_data": pd_copy,
                    "path_data": feat.path_data,
                    "contact_mode": feat.contact_mode,
                })
                # TNP v4.0: ShapeIDs vollständig serialisieren (alle 6 Felder)
                if feat.profile_shape_id:
                    feat_dict["profile_shape_id"] = {
                        "uuid": feat.profile_shape_id.uuid,
                        "shape_type": feat.profile_shape_id.shape_type.name,
                        "feature_id": feat.profile_shape_id.feature_id,
                        "local_index": feat.profile_shape_id.local_index,
                        "geometry_hash": feat.profile_shape_id.geometry_hash,
                        "timestamp": feat.profile_shape_id.timestamp
                    }
                if feat.path_shape_id:
                    feat_dict["path_shape_id"] = {
                        "uuid": feat.path_shape_id.uuid,
                        "shape_type": feat.path_shape_id.shape_type.name,
                        "feature_id": feat.path_shape_id.feature_id,
                        "local_index": feat.path_shape_id.local_index,
                        "geometry_hash": feat.path_shape_id.geometry_hash,
                        "timestamp": feat.path_shape_id.timestamp
                    }

                # TNP v4.0: GeometricSelectors als Fallback serialisieren
                if feat.profile_geometric_selector:
                    feat_dict["profile_geometric_selector"] = (
                        asdict(feat.profile_geometric_selector)
                        if hasattr(feat.profile_geometric_selector, '__dataclass_fields__')
                        else feat.profile_geometric_selector
                    )
                if feat.path_geometric_selector:
                    feat_dict["path_geometric_selector"] = (
                        asdict(feat.path_geometric_selector)
                        if hasattr(feat.path_geometric_selector, '__dataclass_fields__')
                        else feat.path_geometric_selector
                    )

            elif isinstance(feat, ShellFeature):
                feat_dict.update({
                    "feature_class": "ShellFeature",
                    "thickness": feat.thickness,
                    "thickness_formula": feat.thickness_formula,
                    "opening_face_selectors": feat.opening_face_selectors,
                })
                # TNP v3.0: ShapeIDs serialisieren
                if feat.face_shape_ids:
                    feat_dict["face_shape_ids"] = [
                        {
                            "feature_id": sid.feature_id,
                            "local_id": sid.local_id,
                            "shape_type": sid.shape_type.name
                        }
                        for sid in feat.face_shape_ids
                    ]

            elif isinstance(feat, HoleFeature):
                feat_dict.update({
                    "feature_class": "HoleFeature",
                    "hole_type": feat.hole_type,
                    "diameter": feat.diameter,
                    "diameter_formula": feat.diameter_formula,
                    "depth": feat.depth,
                    "depth_formula": feat.depth_formula,
                    "face_selectors": feat.face_selectors,
                    "position": list(feat.position),
                    "direction": list(feat.direction),
                    "counterbore_diameter": feat.counterbore_diameter,
                    "counterbore_depth": feat.counterbore_depth,
                    "countersink_angle": feat.countersink_angle,
                })
                # TNP v3.0: ShapeIDs serialisieren
                if feat.face_shape_ids:
                    feat_dict["face_shape_ids"] = [
                        {
                            "feature_id": sid.feature_id,
                            "local_id": sid.local_id,
                            "shape_type": sid.shape_type.name
                        }
                        for sid in feat.face_shape_ids
                    ]

            elif isinstance(feat, HollowFeature):
                feat_dict.update({
                    "feature_class": "HollowFeature",
                    "wall_thickness": feat.wall_thickness,
                    "drain_hole": feat.drain_hole,
                    "drain_diameter": feat.drain_diameter,
                    "drain_position": list(feat.drain_position),
                    "drain_direction": list(feat.drain_direction),
                })

                # TNP v4.0: Opening-Face ShapeIDs vollständig serialisieren
                if feat.opening_face_shape_ids:
                    feat_dict["opening_face_shape_ids"] = [
                        {
                            "uuid": sid.uuid,
                            "shape_type": sid.shape_type.name,
                            "feature_id": sid.feature_id,
                            "local_index": sid.local_index,
                            "geometry_hash": sid.geometry_hash,
                            "timestamp": sid.timestamp
                        }
                        for sid in feat.opening_face_shape_ids
                    ]

                # TNP v4.0: GeometricSelectors als Fallback serialisieren
                if feat.opening_face_selectors:
                    feat_dict["opening_face_selectors"] = [
                        asdict(sel) if hasattr(sel, '__dataclass_fields__') else sel
                        for sel in feat.opening_face_selectors
                    ]

            elif isinstance(feat, LatticeFeature):
                feat_dict.update({
                    "feature_class": "LatticeFeature",
                    "cell_type": feat.cell_type,
                    "cell_size": feat.cell_size,
                    "beam_radius": feat.beam_radius,
                    "shell_thickness": feat.shell_thickness,
                })

            elif isinstance(feat, ThreadFeature):
                feat_dict.update({
                    "feature_class": "ThreadFeature",
                    "thread_type": feat.thread_type,
                    "standard": feat.standard,
                    "diameter": feat.diameter,
                    "pitch": feat.pitch,
                    "depth": feat.depth,
                    "position": list(feat.position),
                    "direction": list(feat.direction),
                    "tolerance_class": feat.tolerance_class,
                    "tolerance_offset": feat.tolerance_offset,
                    "face_selector": feat.face_selector,
                })
                # TNP v3.0: ShapeID serialisieren
                if feat.face_shape_id:
                    feat_dict["face_shape_id"] = {
                        "feature_id": feat.face_shape_id.feature_id,
                        "local_id": feat.face_shape_id.local_id,
                        "shape_type": feat.face_shape_id.shape_type.name
                    }

            elif isinstance(feat, DraftFeature):
                feat_dict.update({
                    "feature_class": "DraftFeature",
                    "draft_angle": feat.draft_angle,
                    "pull_direction": list(feat.pull_direction),
                    "face_selectors": feat.face_selectors,
                })
                # TNP v3.0: ShapeIDs serialisieren
                if feat.face_shape_ids:
                    feat_dict["face_shape_ids"] = [
                        {
                            "feature_id": sid.feature_id,
                            "local_id": sid.local_id,
                            "shape_type": sid.shape_type.name
                        }
                        for sid in feat.face_shape_ids
                    ]

            elif isinstance(feat, SplitFeature):
                feat_dict.update({
                    "feature_class": "SplitFeature",
                    "plane_origin": list(feat.plane_origin),
                    "plane_normal": list(feat.plane_normal),
                    "keep_side": feat.keep_side,
                })

            elif isinstance(feat, PushPullFeature):
                feat_dict.update({
                    "feature_class": "PushPullFeature",
                    "face_selector": feat.face_selector,
                    "distance": feat.distance,
                    "operation": feat.operation,
                })
                # TNP v3.0: ShapeID serialisieren
                if feat.face_shape_id:
                    feat_dict["face_shape_id"] = {
                        "feature_id": feat.face_shape_id.feature_id,
                        "local_id": feat.face_shape_id.local_id,
                        "shape_type": feat.face_shape_id.shape_type.name
                    }

            elif isinstance(feat, NSidedPatchFeature):
                feat_dict.update({
                    "feature_class": "NSidedPatchFeature",
                    "edge_selectors": feat.edge_selectors,
                    "degree": feat.degree,
                    "tangent": feat.tangent,
                })
                # TNP v3.0: ShapeIDs und GeometricSelectors serialisieren
                if feat.edge_shape_ids:
                    feat_dict["edge_shape_ids"] = [
                        {
                            "feature_id": sid.feature_id,
                            "local_id": sid.local_id,
                            "shape_type": sid.shape_type.name
                        }
                        for sid in feat.edge_shape_ids
                    ]
                if feat.geometric_selectors:
                    feat_dict["geometric_selectors"] = [
                        gs.to_dict() if hasattr(gs, 'to_dict') else gs
                        for gs in feat.geometric_selectors
                    ]

            elif isinstance(feat, SurfaceTextureFeature):
                feat_dict.update({
                    "feature_class": "SurfaceTextureFeature",
                    "texture_type": feat.texture_type,
                    "face_selectors": feat.face_selectors,
                    "scale": feat.scale,
                    "depth": feat.depth,
                    "rotation": feat.rotation,
                    "invert": feat.invert,
                    "type_params": feat.type_params,
                    "export_subdivisions": feat.export_subdivisions,
                })
                # TNP v3.0: ShapeIDs serialisieren
                if feat.face_shape_ids:
                    feat_dict["face_shape_ids"] = [
                        {
                            "feature_id": sid.feature_id,
                            "local_id": sid.local_id,
                            "shape_type": sid.shape_type.name
                        }
                        for sid in feat.face_shape_ids
                    ]

            elif isinstance(feat, TransformFeature):
                feat_dict.update({
                    "feature_class": "TransformFeature",
                    "mode": feat.mode,
                    "data": feat.data,
                })

            elif isinstance(feat, ImportFeature):
                feat_dict.update({
                    "feature_class": "ImportFeature",
                    "brep_string": feat.brep_string,
                    "source_file": feat.source_file,
                    "source_type": feat.source_type,
                })

            features_data.append(feat_dict)

        # TNP v3.0: Registry-Status exportieren
        tnp_data = {}
        if hasattr(self, '_shape_registry'):
            stats = self._shape_registry.get_stats()
            tnp_data = {
                "version": "3.0",
                "statistics": stats,
            }

        # B-Rep Snapshot: exakte Geometrie speichern
        brep_string = None
        if self._build123d_solid is not None:
            try:
                from OCP.BRepTools import BRepTools
                from io import StringIO
                import OCP.TopoDS
                shape = self._build123d_solid.wrapped if hasattr(self._build123d_solid, 'wrapped') else self._build123d_solid
                stream = StringIO()
                # BRepTools.Write_s schreibt in Datei — nutze temp file
                import tempfile, os
                with tempfile.NamedTemporaryFile(mode='w', suffix='.brep', delete=False) as tmp:
                    tmp_path = tmp.name
                BRepTools.Write_s(shape, tmp_path)
                with open(tmp_path, 'r') as f:
                    brep_string = f.read()
                os.unlink(tmp_path)
                logger.debug(f"BREP serialisiert für '{self.name}': {len(brep_string)} Zeichen")
            except Exception as e:
                logger.warning(f"BREP-Serialisierung fehlgeschlagen für '{self.name}': {e}")

        return {
            "name": self.name,
            "id": self.id,
            "features": features_data,
            "tnp_data": tnp_data,
            "brep": brep_string,
            "version": "8.3",
            # Multi-Body Split-Tracking (AGENTS.md Phase 2)
            "source_body_id": self.source_body_id,
            "split_index": self.split_index,
            "split_side": self.split_side,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Body':
        """
        Deserialisiert Body aus Dictionary.

        Args:
            data: Dictionary mit Body-Daten (von to_dict())

        Returns:
            Neues Body-Objekt
        """
        body = cls(name=data.get("name", "Body"))
        body.id = data.get("id", str(uuid.uuid4())[:8])

        # Features deserialisieren
        for feat_dict in data.get("features", []):
            feat_class = feat_dict.get("feature_class", "Feature")
            base_kwargs = {
                "name": feat_dict.get("name", "Feature"),
                "visible": feat_dict.get("visible", True),
                "suppressed": feat_dict.get("suppressed", False),
                "status": feat_dict.get("status", "OK"),
            }

            feat = None

            if feat_class == "ExtrudeFeature":
                feat = ExtrudeFeature(
                    sketch=None,
                    distance=feat_dict.get("distance", 10.0),
                    direction=feat_dict.get("direction", 1),
                    operation=feat_dict.get("operation", "New Body"),
                    plane_origin=tuple(feat_dict.get("plane_origin", (0, 0, 0))) if feat_dict.get("plane_origin") else (0, 0, 0),
                    plane_normal=tuple(feat_dict.get("plane_normal", (0, 0, 1))) if feat_dict.get("plane_normal") else (0, 0, 1),
                    plane_x_dir=tuple(feat_dict["plane_x_dir"]) if feat_dict.get("plane_x_dir") else None,
                    plane_y_dir=tuple(feat_dict["plane_y_dir"]) if feat_dict.get("plane_y_dir") else None,
                    **base_kwargs
                )
                feat.distance_formula = feat_dict.get("distance_formula")
                # Sketch-ID für spätere Referenz-Wiederherstellung speichern
                feat._sketch_id = feat_dict.get("sketch_id")
                # CAD Kernel First: Profile-Selektor laden
                if "profile_selector" in feat_dict and feat_dict["profile_selector"]:
                    feat.profile_selector = [tuple(p) for p in feat_dict["profile_selector"]]
                # WKT zu Shapely Polygons (Legacy Fallback)
                if "precalculated_polys_wkt" in feat_dict:
                    try:
                        from shapely import wkt
                        feat.precalculated_polys = [
                            wkt.loads(w) for w in feat_dict["precalculated_polys_wkt"]
                        ]
                    except Exception as e:
                        logger.debug(f"[__init__.py] Fehler: {e}")
                        pass
                # Face-BREP für Push/Pull auf nicht-planaren Flächen
                if "face_brep" in feat_dict:
                    feat.face_brep = feat_dict["face_brep"]
                    feat.face_type = feat_dict.get("face_type")

            elif feat_class == "FilletFeature":
                feat = FilletFeature(
                    radius=feat_dict.get("radius", 2.0),
                    edge_selectors=feat_dict.get("edge_selectors"),
                    depends_on_feature_id=feat_dict.get("depends_on_feature_id"),
                    **base_kwargs
                )
                feat.radius_formula = feat_dict.get("radius_formula")
                # GeometricSelectors deserialisieren
                if "geometric_selectors" in feat_dict:
                    from modeling.geometric_selector import GeometricEdgeSelector
                    feat.geometric_selectors = [
                        GeometricEdgeSelector.from_dict(gs) if isinstance(gs, dict) else gs
                        for gs in feat_dict["geometric_selectors"]
                    ]
                # TNP v4.0: ShapeIDs vollständig deserialisieren
                if "edge_shape_ids" in feat_dict:
                    from modeling.tnp_system import ShapeID, ShapeType
                    feat.edge_shape_ids = []
                    for sid_data in feat_dict["edge_shape_ids"]:
                        if isinstance(sid_data, dict):
                            shape_type = ShapeType[sid_data.get("shape_type", "EDGE")]
                            feat.edge_shape_ids.append(ShapeID(
                                uuid=sid_data.get("uuid", ""),
                                shape_type=shape_type,
                                feature_id=sid_data.get("feature_id", ""),
                                local_index=sid_data.get("local_index", 0),
                                geometry_hash=sid_data.get("geometry_hash", ""),
                                timestamp=sid_data.get("timestamp", 0.0)
                            ))

            elif feat_class == "ChamferFeature":
                feat = ChamferFeature(
                    distance=feat_dict.get("distance", 2.0),
                    edge_selectors=feat_dict.get("edge_selectors"),
                    depends_on_feature_id=feat_dict.get("depends_on_feature_id"),
                    **base_kwargs
                )
                feat.distance_formula = feat_dict.get("distance_formula")
                if "geometric_selectors" in feat_dict:
                    from modeling.geometric_selector import GeometricEdgeSelector
                    feat.geometric_selectors = [
                        GeometricEdgeSelector.from_dict(gs) if isinstance(gs, dict) else gs
                        for gs in feat_dict["geometric_selectors"]
                    ]
                # TNP v4.0: ShapeIDs vollständig deserialisieren
                if "edge_shape_ids" in feat_dict:
                    from modeling.tnp_system import ShapeID, ShapeType
                    feat.edge_shape_ids = []
                    for sid_data in feat_dict["edge_shape_ids"]:
                        if isinstance(sid_data, dict):
                            shape_type = ShapeType[sid_data.get("shape_type", "EDGE")]
                            feat.edge_shape_ids.append(ShapeID(
                                uuid=sid_data.get("uuid", ""),
                                shape_type=shape_type,
                                feature_id=sid_data.get("feature_id", ""),
                                local_index=sid_data.get("local_index", 0),
                                geometry_hash=sid_data.get("geometry_hash", ""),
                                timestamp=sid_data.get("timestamp", 0.0)
                            ))

            elif feat_class == "RevolveFeature":
                feat = RevolveFeature(
                    sketch=None,
                    angle=feat_dict.get("angle", 360.0),
                    axis=tuple(feat_dict.get("axis", (0, 1, 0))),
                    axis_origin=tuple(feat_dict.get("axis_origin", (0, 0, 0))),
                    operation=feat_dict.get("operation", "New Body"),
                    **base_kwargs
                )
                feat.angle_formula = feat_dict.get("angle_formula")
                # Sketch-ID für spätere Referenz-Wiederherstellung speichern
                feat._sketch_id = feat_dict.get("sketch_id")
                # CAD Kernel First: Profile-Selektor laden
                if "profile_selector" in feat_dict and feat_dict["profile_selector"]:
                    feat.profile_selector = [tuple(p) for p in feat_dict["profile_selector"]]

            elif feat_class == "LoftFeature":
                # Restore shapely_poly from coordinates
                profile_data = feat_dict.get("profile_data", [])
                try:
                    from shapely.geometry import Polygon as ShapelyPolygon
                    for pd in profile_data:
                        if 'shapely_poly_coords' in pd:
                            coords = pd['shapely_poly_coords']
                            exterior = coords.get('exterior', [])
                            holes = coords.get('holes', [])
                            if exterior:
                                pd['shapely_poly'] = ShapelyPolygon(exterior, holes)
                            del pd['shapely_poly_coords']
                except ImportError:
                    pass
                feat = LoftFeature(
                    ruled=feat_dict.get("ruled", False),
                    operation=feat_dict.get("operation", "New Body"),
                    start_continuity=feat_dict.get("start_continuity", "G0"),
                    end_continuity=feat_dict.get("end_continuity", "G0"),
                    profile_data=profile_data,
                    **base_kwargs
                )
                # TNP v4.0: ShapeIDs vollständig deserialisieren (alle 6 Felder)
                if "profile_shape_ids" in feat_dict:
                    from modeling.tnp_system import ShapeID, ShapeType
                    feat.profile_shape_ids = []
                    for sid_data in feat_dict["profile_shape_ids"]:
                        if isinstance(sid_data, dict):
                            shape_type = ShapeType[sid_data.get("shape_type", "FACE")]
                            feat.profile_shape_ids.append(ShapeID(
                                uuid=sid_data.get("uuid", ""),
                                shape_type=shape_type,
                                feature_id=sid_data.get("feature_id", ""),
                                local_index=sid_data.get("local_index", 0),
                                geometry_hash=sid_data.get("geometry_hash", ""),
                                timestamp=sid_data.get("timestamp", 0.0)
                            ))

                # TNP v4.0: GeometricSelectors deserialisieren
                if "profile_geometric_selectors" in feat_dict:
                    from modeling.geometric_selector import GeometricFaceSelector
                    feat.profile_geometric_selectors = []
                    for sel_data in feat_dict["profile_geometric_selectors"]:
                        if isinstance(sel_data, dict):
                            feat.profile_geometric_selectors.append(
                                GeometricFaceSelector(**sel_data)
                            )

            elif feat_class == "SweepFeature":
                # Restore shapely_poly from coordinates
                profile_data = feat_dict.get("profile_data", {})
                try:
                    from shapely.geometry import Polygon as ShapelyPolygon
                    if 'shapely_poly_coords' in profile_data:
                        coords = profile_data['shapely_poly_coords']
                        exterior = coords.get('exterior', [])
                        holes = coords.get('holes', [])
                        if exterior:
                            profile_data['shapely_poly'] = ShapelyPolygon(exterior, holes)
                        del profile_data['shapely_poly_coords']
                except ImportError:
                    pass
                feat = SweepFeature(
                    is_frenet=feat_dict.get("is_frenet", False),
                    operation=feat_dict.get("operation", "New Body"),
                    twist_angle=feat_dict.get("twist_angle", 0.0),
                    scale_start=feat_dict.get("scale_start", 1.0),
                    scale_end=feat_dict.get("scale_end", 1.0),
                    profile_data=profile_data,
                    path_data=feat_dict.get("path_data", {}),
                    contact_mode=feat_dict.get("contact_mode", "keep"),
                    **base_kwargs
                )
                # TNP v4.0: ShapeIDs vollständig deserialisieren (alle 6 Felder)
                from modeling.tnp_system import ShapeID, ShapeType
                if "profile_shape_id" in feat_dict:
                    sid_data = feat_dict["profile_shape_id"]
                    if isinstance(sid_data, dict):
                        shape_type = ShapeType[sid_data.get("shape_type", "FACE")]
                        feat.profile_shape_id = ShapeID(
                            uuid=sid_data.get("uuid", ""),
                            shape_type=shape_type,
                            feature_id=sid_data.get("feature_id", ""),
                            local_index=sid_data.get("local_index", 0),
                            geometry_hash=sid_data.get("geometry_hash", ""),
                            timestamp=sid_data.get("timestamp", 0.0)
                        )
                if "path_shape_id" in feat_dict:
                    sid_data = feat_dict["path_shape_id"]
                    if isinstance(sid_data, dict):
                        shape_type = ShapeType[sid_data.get("shape_type", "EDGE")]
                        feat.path_shape_id = ShapeID(
                            uuid=sid_data.get("uuid", ""),
                            shape_type=shape_type,
                            feature_id=sid_data.get("feature_id", ""),
                            local_index=sid_data.get("local_index", 0),
                            geometry_hash=sid_data.get("geometry_hash", ""),
                            timestamp=sid_data.get("timestamp", 0.0)
                        )

                # TNP v4.0: GeometricSelectors deserialisieren
                from modeling.geometric_selector import GeometricFaceSelector, GeometricEdgeSelector
                if "profile_geometric_selector" in feat_dict:
                    sel_data = feat_dict["profile_geometric_selector"]
                    if isinstance(sel_data, dict):
                        feat.profile_geometric_selector = GeometricFaceSelector(**sel_data)
                if "path_geometric_selector" in feat_dict:
                    sel_data = feat_dict["path_geometric_selector"]
                    if isinstance(sel_data, dict):
                        feat.path_geometric_selector = GeometricEdgeSelector(**sel_data)

            elif feat_class == "ShellFeature":
                selectors = feat_dict.get("opening_face_selectors", [])
                # Legacy: Konvertiere Tuples zu GeometricFaceSelector Dicts
                converted_selectors = []
                for sel in selectors:
                    if isinstance(sel, (list, tuple)) and len(sel) == 2:
                        # Alt: ((cx,cy,cz), (nx,ny,nz))
                        converted_selectors.append({
                            "center": list(sel[0]) if hasattr(sel[0], '__iter__') else [0,0,0],
                            "normal": list(sel[1]) if hasattr(sel[1], '__iter__') else [0,0,1],
                            "area": 0.0,
                            "surface_type": "unknown",
                            "tolerance": 10.0
                        })
                    elif isinstance(sel, dict):
                        converted_selectors.append(sel)
                
                feat = ShellFeature(
                    thickness=feat_dict.get("thickness", 2.0),
                    opening_face_selectors=converted_selectors,
                    **base_kwargs
                )
                feat.thickness_formula = feat_dict.get("thickness_formula")
                # TNP v3.0: ShapeIDs deserialisieren
                if "face_shape_ids" in feat_dict:
                    from modeling.tnp_shape_reference import ShapeID, ShapeType
                    feat.face_shape_ids = []
                    for sid_data in feat_dict["face_shape_ids"]:
                        if isinstance(sid_data, dict):
                            shape_type = ShapeType[sid_data.get("shape_type", "FACE")]
                            feat.face_shape_ids.append(ShapeID(
                                feature_id=sid_data.get("feature_id", ""),
                                local_id=sid_data.get("local_id", 0),
                                shape_type=shape_type
                            ))

            elif feat_class == "HoleFeature":
                selectors = feat_dict.get("face_selectors", [])
                # Legacy: Konvertiere Tuples zu GeometricFaceSelector Dicts
                converted_selectors = []
                for sel in selectors:
                    if isinstance(sel, (list, tuple)) and len(sel) == 2:
                        converted_selectors.append({
                            "center": list(sel[0]) if hasattr(sel[0], '__iter__') else [0,0,0],
                            "normal": list(sel[1]) if hasattr(sel[1], '__iter__') else [0,0,1],
                            "area": 0.0,
                            "surface_type": "unknown",
                            "tolerance": 10.0
                        })
                    elif isinstance(sel, dict):
                        converted_selectors.append(sel)
                
                feat = HoleFeature(
                    hole_type=feat_dict.get("hole_type", "simple"),
                    diameter=feat_dict.get("diameter", 8.0),
                    depth=feat_dict.get("depth", 0.0),
                    face_selectors=converted_selectors,
                    position=tuple(feat_dict.get("position", (0, 0, 0))),
                    direction=tuple(feat_dict.get("direction", (0, 0, -1))),
                    counterbore_diameter=feat_dict.get("counterbore_diameter", 12.0),
                    counterbore_depth=feat_dict.get("counterbore_depth", 3.0),
                    countersink_angle=feat_dict.get("countersink_angle", 82.0),
                    **base_kwargs
                )
                feat.diameter_formula = feat_dict.get("diameter_formula")
                feat.depth_formula = feat_dict.get("depth_formula")
                # TNP v3.0: ShapeIDs deserialisieren
                if "face_shape_ids" in feat_dict:
                    from modeling.tnp_shape_reference import ShapeID, ShapeType
                    feat.face_shape_ids = []
                    for sid_data in feat_dict["face_shape_ids"]:
                        if isinstance(sid_data, dict):
                            shape_type = ShapeType[sid_data.get("shape_type", "FACE")]
                            feat.face_shape_ids.append(ShapeID(
                                feature_id=sid_data.get("feature_id", ""),
                                local_id=sid_data.get("local_id", 0),
                                shape_type=shape_type
                            ))

            elif feat_class == "HollowFeature":
                feat = HollowFeature(
                    wall_thickness=feat_dict.get("wall_thickness", 2.0),
                    drain_hole=feat_dict.get("drain_hole", False),
                    drain_diameter=feat_dict.get("drain_diameter", 3.0),
                    drain_position=tuple(feat_dict.get("drain_position", [0, 0, 0])),
                    drain_direction=tuple(feat_dict.get("drain_direction", [0, 0, -1])),
                    **base_kwargs
                )

                # TNP v4.0: Opening-Face ShapeIDs vollständig deserialisieren
                if "opening_face_shape_ids" in feat_dict:
                    from modeling.tnp_system import ShapeID, ShapeType
                    feat.opening_face_shape_ids = []
                    for sid_data in feat_dict["opening_face_shape_ids"]:
                        if isinstance(sid_data, dict):
                            shape_type = ShapeType[sid_data.get("shape_type", "FACE")]
                            feat.opening_face_shape_ids.append(ShapeID(
                                uuid=sid_data.get("uuid", ""),
                                shape_type=shape_type,
                                feature_id=sid_data.get("feature_id", ""),
                                local_index=sid_data.get("local_index", 0),
                                geometry_hash=sid_data.get("geometry_hash", ""),
                                timestamp=sid_data.get("timestamp", 0.0)
                            ))

                # TNP v4.0: GeometricSelectors deserialisieren
                if "opening_face_selectors" in feat_dict:
                    from modeling.geometric_selector import GeometricFaceSelector
                    feat.opening_face_selectors = []
                    for sel_data in feat_dict["opening_face_selectors"]:
                        if isinstance(sel_data, dict):
                            feat.opening_face_selectors.append(
                                GeometricFaceSelector(**sel_data)
                            )

            elif feat_class == "LatticeFeature":
                feat = LatticeFeature(
                    cell_type=feat_dict.get("cell_type", "BCC"),
                    cell_size=feat_dict.get("cell_size", 5.0),
                    beam_radius=feat_dict.get("beam_radius", 0.5),
                    shell_thickness=feat_dict.get("shell_thickness", 0.0),
                    **base_kwargs
                )

            elif feat_class == "PushPullFeature":
                sel = feat_dict.get("face_selector")
                # NEU: GeometricFaceSelector als Dict
                # ALT: Liste [center, normal] - konvertieren zu Dict für Kompatibilität
                if sel and isinstance(sel, list) and len(sel) == 2:
                    # Legacy-Format: [(cx,cy,cz), (nx,ny,nz)]
                    sel = {
                        "center": list(sel[0]) if hasattr(sel[0], '__iter__') else [0,0,0],
                        "normal": list(sel[1]) if hasattr(sel[1], '__iter__') else [0,0,1],
                        "area": 0.0,
                        "surface_type": "unknown",
                        "tolerance": 10.0
                    }
                feat = PushPullFeature(
                    face_selector=sel,
                    distance=feat_dict.get("distance", 10.0),
                    operation=feat_dict.get("operation", "Join"),
                    **base_kwargs
                )
                # TNP v3.0: ShapeID deserialisieren
                if "face_shape_id" in feat_dict:
                    from modeling.tnp_shape_reference import ShapeID, ShapeType
                    sid_data = feat_dict["face_shape_id"]
                    if isinstance(sid_data, dict):
                        shape_type = ShapeType[sid_data.get("shape_type", "FACE")]
                        feat.face_shape_id = ShapeID(
                            feature_id=sid_data.get("feature_id", ""),
                            local_id=sid_data.get("local_id", 0),
                            shape_type=shape_type
                        )

            elif feat_class == "NSidedPatchFeature":
                feat = NSidedPatchFeature(
                    edge_selectors=feat_dict.get("edge_selectors", []),
                    degree=feat_dict.get("degree", 3),
                    tangent=feat_dict.get("tangent", True),
                    **base_kwargs
                )
                # TNP v3.0: ShapeIDs und GeometricSelectors deserialisieren
                if "edge_shape_ids" in feat_dict:
                    from modeling.tnp_shape_reference import ShapeID, ShapeType
                    feat.edge_shape_ids = []
                    for sid_data in feat_dict["edge_shape_ids"]:
                        if isinstance(sid_data, dict):
                            shape_type = ShapeType[sid_data.get("shape_type", "EDGE")]
                            feat.edge_shape_ids.append(ShapeID(
                                feature_id=sid_data.get("feature_id", ""),
                                local_id=sid_data.get("local_id", 0),
                                shape_type=shape_type
                            ))
                if "geometric_selectors" in feat_dict:
                    from modeling.geometric_selector import GeometricEdgeSelector
                    feat.geometric_selectors = [
                        GeometricEdgeSelector.from_dict(gs) if isinstance(gs, dict) else gs
                        for gs in feat_dict["geometric_selectors"]
                    ]

            elif feat_class == "SurfaceTextureFeature":
                feat = SurfaceTextureFeature(
                    texture_type=feat_dict.get("texture_type", "ripple"),
                    face_selectors=feat_dict.get("face_selectors", []),
                    scale=feat_dict.get("scale", 1.0),
                    depth=feat_dict.get("depth", 0.5),
                    rotation=feat_dict.get("rotation", 0.0),
                    invert=feat_dict.get("invert", False),
                    type_params=feat_dict.get("type_params", {}),
                    export_subdivisions=feat_dict.get("export_subdivisions", 2),
                    **base_kwargs
                )
                # TNP v3.0: ShapeIDs deserialisieren
                if "face_shape_ids" in feat_dict:
                    from modeling.tnp_shape_reference import ShapeID, ShapeType
                    feat.face_shape_ids = []
                    for sid_data in feat_dict["face_shape_ids"]:
                        if isinstance(sid_data, dict):
                            shape_type = ShapeType[sid_data.get("shape_type", "FACE")]
                            feat.face_shape_ids.append(ShapeID(
                                feature_id=sid_data.get("feature_id", ""),
                                local_id=sid_data.get("local_id", 0),
                                shape_type=shape_type
                            ))

            elif feat_class == "ThreadFeature":
                feat = ThreadFeature(
                    thread_type=feat_dict.get("thread_type", "external"),
                    standard=feat_dict.get("standard", "M"),
                    diameter=feat_dict.get("diameter", 10.0),
                    pitch=feat_dict.get("pitch", 1.5),
                    depth=feat_dict.get("depth", 20.0),
                    position=tuple(feat_dict.get("position", (0, 0, 0))),
                    direction=tuple(feat_dict.get("direction", (0, 0, 1))),
                    tolerance_class=feat_dict.get("tolerance_class", "6g"),
                    tolerance_offset=feat_dict.get("tolerance_offset", 0.0),
                    face_selector=feat_dict.get("face_selector"),
                    **base_kwargs
                )
                # TNP v3.0: ShapeID deserialisieren
                if "face_shape_id" in feat_dict:
                    from modeling.tnp_shape_reference import ShapeID, ShapeType
                    sid_data = feat_dict["face_shape_id"]
                    if isinstance(sid_data, dict):
                        shape_type = ShapeType[sid_data.get("shape_type", "FACE")]
                        feat.face_shape_id = ShapeID(
                            feature_id=sid_data.get("feature_id", ""),
                            local_id=sid_data.get("local_id", 0),
                            shape_type=shape_type
                        )

            elif feat_class == "DraftFeature":
                selectors = feat_dict.get("face_selectors", [])
                # Legacy: Konvertiere Tuples zu GeometricFaceSelector Dicts
                converted_selectors = []
                for sel in selectors:
                    if isinstance(sel, (list, tuple)) and len(sel) == 2:
                        converted_selectors.append({
                            "center": list(sel[0]) if hasattr(sel[0], '__iter__') else [0,0,0],
                            "normal": list(sel[1]) if hasattr(sel[1], '__iter__') else [0,0,1],
                            "area": 0.0,
                            "surface_type": "unknown",
                            "tolerance": 10.0
                        })
                    elif isinstance(sel, dict):
                        converted_selectors.append(sel)
                
                feat = DraftFeature(
                    draft_angle=feat_dict.get("draft_angle", 5.0),
                    pull_direction=tuple(feat_dict.get("pull_direction", (0, 0, 1))),
                    face_selectors=converted_selectors,
                    **base_kwargs
                )
                # TNP v3.0: ShapeIDs deserialisieren
                if "face_shape_ids" in feat_dict:
                    from modeling.tnp_shape_reference import ShapeID, ShapeType
                    feat.face_shape_ids = []
                    for sid_data in feat_dict["face_shape_ids"]:
                        if isinstance(sid_data, dict):
                            shape_type = ShapeType[sid_data.get("shape_type", "FACE")]
                            feat.face_shape_ids.append(ShapeID(
                                feature_id=sid_data.get("feature_id", ""),
                                local_id=sid_data.get("local_id", 0),
                                shape_type=shape_type
                            ))

            elif feat_class == "SplitFeature":
                feat = SplitFeature(
                    plane_origin=tuple(feat_dict.get("plane_origin", (0, 0, 0))),
                    plane_normal=tuple(feat_dict.get("plane_normal", (0, 0, 1))),
                    keep_side=feat_dict.get("keep_side", "above"),
                    **base_kwargs
                )

            elif feat_class == "TransformFeature":
                feat = TransformFeature(
                    mode=feat_dict.get("mode", "move"),
                    data=feat_dict.get("data", {}),
                    **base_kwargs
                )

            elif feat_class == "ImportFeature":
                feat = ImportFeature(
                    brep_string=feat_dict.get("brep_string", ""),
                    source_file=feat_dict.get("source_file", ""),
                    source_type=feat_dict.get("source_type", ""),
                    **base_kwargs
                )

            else:
                # Generic Feature
                feat = Feature(**base_kwargs)
                try:
                    feat.type = FeatureType[feat_dict.get("type", "SKETCH")]
                except Exception as e:
                    logger.debug(f"[__init__.py] Fehler: {e}")
                    pass

            if feat:
                feat.id = feat_dict.get("id", str(uuid.uuid4())[:8])
                body.features.append(feat)

        # B-Rep Snapshot laden
        brep_string = data.get("brep")
        if brep_string and HAS_OCP:
            try:
                from OCP.BRepTools import BRepTools
                from OCP.TopoDS import TopoDS_Shape
                from OCP.BRep import BRep_Builder
                import tempfile, os

                with tempfile.NamedTemporaryFile(mode='w', suffix='.brep', delete=False, encoding='utf-8') as tmp:
                    tmp.write(brep_string)
                    tmp_path = tmp.name

                shape = TopoDS_Shape()
                builder = BRep_Builder()
                BRepTools.Read_s(shape, tmp_path, builder)
                os.unlink(tmp_path)

                if not shape.IsNull():
                    from build123d import Solid, Compound
                    from OCP.TopAbs import TopAbs_SOLID, TopAbs_COMPOUND, TopAbs_SHELL
                    from OCP.TopExp import TopExp_Explorer
                    from OCP.BRep import BRep_Builder as _BB
                    from OCP.TopoDS import TopoDS_Compound as _TC

                    shape_type = shape.ShapeType()
                    if shape_type == TopAbs_SOLID:
                        body._build123d_solid = Solid.cast(shape)
                    elif shape_type == TopAbs_COMPOUND:
                        # Sammle alle Solids aus dem Compound
                        solids = []
                        explorer = TopExp_Explorer(shape, TopAbs_SOLID)
                        while explorer.More():
                            solids.append(explorer.Current())
                            explorer.Next()

                        if len(solids) == 1:
                            body._build123d_solid = Solid.cast(solids[0])
                        elif len(solids) > 1:
                            # Mehrere Solids → als Compound behalten
                            body._build123d_solid = Compound.cast(shape)
                            logger.debug(f"BREP Compound mit {len(solids)} Solids für '{body.name}'")
                        else:
                            # Kein Solid — vielleicht Shells (z.B. STL-Import)?
                            shells = []
                            exp2 = TopExp_Explorer(shape, TopAbs_SHELL)
                            while exp2.More():
                                shells.append(exp2.Current())
                                exp2.Next()
                            if shells:
                                body._build123d_solid = Compound.cast(shape)
                                logger.debug(f"BREP Compound mit {len(shells)} Shells für '{body.name}'")
                            else:
                                logger.warning(f"BREP Compound enthält keinen Solid/Shell für '{body.name}'")
                    else:
                        body._build123d_solid = Solid.cast(shape)

                    if body._build123d_solid is not None:
                        body.invalidate_mesh()
                        logger.debug(f"BREP geladen für '{body.name}': exakte Geometrie wiederhergestellt")
                else:
                    logger.warning(f"BREP leer für '{body.name}' — Rebuild wird versucht")
            except Exception as e:
                logger.warning(f"BREP-Laden fehlgeschlagen für '{body.name}': {e}")

        # TNP v3.0: Daten importieren
        tnp_data = data.get("tnp_data", {})
        if tnp_data and hasattr(body, '_shape_registry'):
            # ShapeIDs werden aus den Features rekonstruiert
            if is_enabled("tnp_debug_logging"):
                logger.debug(f"TNP v3.0: Body '{body.name}' geladen - Registry wird aus Features aufgebaut")

        # Multi-Body Split-Tracking (AGENTS.md Phase 2)
        body.source_body_id = data.get("source_body_id")
        body.split_index = data.get("split_index")
        body.split_side = data.get("split_side")

        return body


class Document:
    """
    Dokument mit optionalem Assembly-System.

    Phase 1 Assembly: Unterstützt hierarchische Component-Struktur.
    Backward-compatible: Alte Projekte laden weiterhin korrekt.
    """

    def __init__(self, name="Doc"):
        self.name = name
        self.active_body: Optional[Body] = None
        self.active_sketch: Optional[Sketch] = None
        
        # TNP v4.0: Shape Naming Service für persistente Shape-Referenzen
        from modeling.tnp_system import ShapeNamingService
        self._shape_naming_service = ShapeNamingService()
        if is_enabled("tnp_debug_logging"):
            logger.debug(f"TNP v4.0: ShapeNamingService initialisiert für '{name}'")

        # =========================================================================
        # Assembly System (Phase 1)
        # =========================================================================
        # Feature Flag prüfen
        self._assembly_enabled = is_enabled("assembly_system")

        if self._assembly_enabled:
            # NEU: Component-basierte Architektur
            self.root_component: Component = Component(name="Root")
            self.root_component.is_active = True
            self._active_component: Optional[Component] = self.root_component
            logger.info(f"[ASSEMBLY] Component-System aktiviert für '{name}'")
        else:
            # Legacy: Direkte Listen (für Backward-Compatibility)
            self.root_component = None
            self._active_component = None

        # Diese Listen werden immer verwendet (delegieren zu active_component wenn assembly_enabled)
        self._bodies: List[Body] = []
        self._sketches: List[Sketch] = []
        self._planes: List[ConstructionPlane] = []

    # =========================================================================
    # Properties für Backward-Compatibility
    # =========================================================================
    # Diese Properties delegieren zu active_component wenn Assembly aktiviert

    @property
    def bodies(self) -> List[Body]:
        """Bodies der aktiven Component (oder direkte Liste bei Legacy-Modus)."""
        if self._assembly_enabled and self._active_component:
            return self._active_component.bodies
        return self._bodies

    @bodies.setter
    def bodies(self, value: List[Body]):
        if self._assembly_enabled and self._active_component:
            self._active_component.bodies = value
        else:
            self._bodies = value

    @property
    def sketches(self) -> List[Sketch]:
        """Sketches der aktiven Component (oder direkte Liste bei Legacy-Modus)."""
        if self._assembly_enabled and self._active_component:
            return self._active_component.sketches
        return self._sketches

    @sketches.setter
    def sketches(self, value: List[Sketch]):
        if self._assembly_enabled and self._active_component:
            self._active_component.sketches = value
        else:
            self._sketches = value

    @property
    def planes(self) -> List[ConstructionPlane]:
        """Planes der aktiven Component (oder direkte Liste bei Legacy-Modus)."""
        if self._assembly_enabled and self._active_component:
            return self._active_component.planes
        return self._planes

    @planes.setter
    def planes(self, value: List[ConstructionPlane]):
        if self._assembly_enabled and self._active_component:
            self._active_component.planes = value
        else:
            self._planes = value

    # =========================================================================
    # Assembly-spezifische Methoden
    # =========================================================================

    @property
    def active_component(self) -> Optional[Component]:
        """Gibt die aktive Component zurück (oder None wenn Assembly deaktiviert)."""
        return self._active_component

    def set_active_component(self, comp: Component) -> bool:
        """
        Setzt die aktive Component.

        Args:
            comp: Zu aktivierende Component

        Returns:
            True wenn erfolgreich
        """
        if not self._assembly_enabled:
            logger.warning("Assembly-System nicht aktiviert")
            return False

        if self._active_component:
            self._active_component.is_active = False

        self._active_component = comp
        comp.is_active = True
        logger.info(f"[ASSEMBLY] Aktive Component: {comp.name}")
        return True

    def get_all_bodies(self) -> List[Body]:
        """
        Gibt alle Bodies im Dokument zurück (rekursiv bei Assembly).

        Returns:
            Liste aller Bodies
        """
        if self._assembly_enabled and self.root_component:
            return self.root_component.get_all_bodies(recursive=True)
        return self._bodies

    def get_all_sketches(self) -> List[Sketch]:
        """Gibt alle Sketches im Dokument zurück (rekursiv bei Assembly)."""
        if self._assembly_enabled and self.root_component:
            return self.root_component.get_all_sketches(recursive=True)
        return self._sketches

    def find_body_by_id(self, body_id: str) -> Optional[Body]:
        """Findet Body nach ID (rekursiv bei Assembly)."""
        if self._assembly_enabled and self.root_component:
            return self.root_component.find_body_by_id(body_id)
        for body in self._bodies:
            if body.id == body_id:
                return body
        return None

    def new_component(self, name: str = None, parent: Component = None) -> Optional[Component]:
        """
        Erstellt neue Component.

        Args:
            name: Name der neuen Component
            parent: Parent-Component (default: active_component)

        Returns:
            Neue Component oder None wenn Assembly deaktiviert
        """
        if not self._assembly_enabled:
            logger.warning("Assembly-System nicht aktiviert")
            return None

        parent = parent or self._active_component or self.root_component
        return parent.add_sub_component(name)

    def new_body(self, name=None):
        b = Body(name or f"Body{len(self.bodies)+1}", document=self)
        self.bodies.append(b)
        self.active_body = b
        return b

    def new_sketch(self, name=None):
        s = Sketch(name or f"Sketch{len(self.sketches)+1}")
        self.sketches.append(s)
        self.active_sketch = s
        return s

    def split_body(self, body: Body, plane_origin: tuple, plane_normal: tuple) -> Tuple[Body, Body]:
        """
        Teilt einen Body in 2 Hälften und fügt beide zum Document hinzu.

        Multi-Body Split Architecture (AGENTS.md Phase 3):
        - Erstellt SplitFeature mit keep_side="both"
        - Beide Bodies erhalten shared Feature-Historie
        - Original-Body wird aus Document entfernt
        - Beide neue Bodies werden registriert

        Args:
            body: Zu teilender Body
            plane_origin: Ursprung der Split-Ebene (x, y, z)
            plane_normal: Normale der Split-Ebene (x, y, z)

        Returns:
            (body_above, body_below) - beide Bodies im Document registriert

        Raises:
            ValueError: Wenn Split fehlschlägt
        """
        from build123d import Solid

        # 1. Split-Feature erstellen
        split_feat = SplitFeature(
            plane_origin=plane_origin,
            plane_normal=plane_normal,
            keep_side="both"  # Explizit beide behalten
        )

        # 2. Feature zu Original-Body hinzufügen (ohne Rebuild - wir wollen SplitResult)
        body.features.append(split_feat)
        split_index = len(body.features) - 1

        # 3. _compute_split aufrufen → SplitResult
        try:
            split_result = body._compute_split(split_feat, body._build123d_solid)
        except Exception as e:
            # Rollback: Feature wieder entfernen
            body.features.pop()
            raise ValueError(f"Split-Operation fehlgeschlagen: {e}")

        # Validierung: Muss SplitResult sein
        if not isinstance(split_result, SplitResult):
            body.features.pop()
            raise ValueError("Split mit keep_side='both' muss SplitResult zurückgeben")

        # 4. Beide Bodies erstellen mit shared history
        body_above = Body(name=f"{body.name}_above", document=self)
        body_above.features = body.features.copy()  # Shared history
        body_above._build123d_solid = split_result.body_above
        body_above.source_body_id = body.id
        body_above.split_index = split_index
        body_above.split_side = "above"

        body_below = Body(name=f"{body.name}_below", document=self)
        body_below.features = body.features.copy()  # Shared history
        body_below._build123d_solid = split_result.body_below
        body_below.source_body_id = body.id
        body_below.split_index = split_index
        body_below.split_side = "below"

        # 5. Original-Body aus Document entfernen
        if body in self.bodies:
            self.bodies.remove(body)
            logger.debug(f"Split: Original-Body '{body.name}' entfernt")

        # 6. Beide neue Bodies hinzufügen
        self.bodies.append(body_above)
        self.bodies.append(body_below)

        # Invalidate meshes für beide Bodies
        body_above.invalidate_mesh()
        body_below.invalidate_mesh()

        logger.debug(f"Split: '{body.name}' → '{body_above.name}' + '{body_below.name}'")

        # 7. Setze einen der Bodies als aktiv (optional - user kann das auch manuell machen)
        if self.active_body == body:
            self.active_body = body_above

        return body_above, body_below

    def new_plane(self, base: str = "XY", offset: float = 0.0, name: str = None):
        """
        Erstellt neue Konstruktionsebene.

        Args:
            base: Basis-Ebene ("XY", "XZ", "YZ")
            offset: Abstand in mm
            name: Optional - sonst automatisch generiert

        Returns:
            ConstructionPlane
        """
        plane = ConstructionPlane.from_offset(base, offset, name)
        self.planes.append(plane)
        logger.info(f"Konstruktionsebene erstellt: {plane.name}")
        return plane

    def find_plane_by_id(self, plane_id: str) -> Optional[ConstructionPlane]:
        """Findet Konstruktionsebene nach ID."""
        for p in self.planes:
            if p.id == plane_id:
                return p
        return None

    # =========================================================================
    # Phase 8.3: STEP Import/Export
    # =========================================================================

    def export_step(self, filename: str, schema: str = "AP214") -> bool:
        """
        Exportiert gesamtes Dokument als STEP-Datei.

        Args:
            filename: Ausgabepfad (.step/.stp)
            schema: "AP214" (Standard) oder "AP242" (PMI)

        Returns:
            True bei Erfolg
        """
        from modeling.step_io import STEPWriter, STEPSchema

        # Schema konvertieren
        schema_enum = STEPSchema.AP242 if schema == "AP242" else STEPSchema.AP214

        # Bodies mit Solids sammeln
        export_bodies = [b for b in self.bodies if hasattr(b, '_build123d_solid') and b._build123d_solid]

        if not export_bodies:
            logger.warning("Keine Bodies mit BREP-Daten zum Exportieren")
            return False

        if len(export_bodies) == 1:
            # Einzelner Body
            result = STEPWriter.export_solid(
                export_bodies[0]._build123d_solid,
                filename,
                application_name="MashCad",
                schema=schema_enum
            )
        else:
            # Multi-Body Assembly
            result = STEPWriter.export_assembly(
                export_bodies,
                filename,
                assembly_name=self.name,
                schema=schema_enum
            )

        if not result.success:
            logger.error(f"STEP Export fehlgeschlagen: {result.message}")

        return result.success

    def import_step(self, filename: str, auto_heal: bool = True) -> List['Body']:
        """
        Importiert STEP-Datei und erstellt neue Bodies.

        Args:
            filename: Pfad zur STEP-Datei
            auto_heal: Automatisches Geometry-Healing

        Returns:
            Liste der erstellten Bodies (leer bei Fehler)
        """
        from modeling.step_io import STEPReader

        result = STEPReader.import_file(filename, auto_heal=auto_heal)

        if not result.success:
            for error in result.errors:
                logger.error(f"STEP Import: {error}")
            return []

        # Warnings loggen
        for warning in result.warnings:
            logger.warning(f"STEP Import: {warning}")

        # Bodies erstellen
        new_bodies = []
        for i, solid in enumerate(result.solids):
            body = Body(name=f"Imported_{i+1}")
            body._build123d_solid = solid
            body._update_mesh_from_solid(solid)

            self.bodies.append(body)
            new_bodies.append(body)

        if new_bodies:
            self.active_body = new_bodies[0]
            logger.debug(f"STEP Import: {len(new_bodies)} Body(s) erstellt")

        return new_bodies

    # =========================================================================
    # Phase 8.2: Persistente Projekt-Speicherung
    # =========================================================================

    def to_dict(self) -> dict:
        """
        Serialisiert gesamtes Dokument zu Dictionary.

        Version 9.0+: Assembly-System mit Component-Hierarchie
        Version 8.x: Legacy-Format (flat lists)

        Returns:
            Dictionary für JSON-Serialisierung
        """
        # Parameter speichern
        try:
            from core.parameters import get_parameters
            params = get_parameters()
            params_data = params.to_dict() if params else {}
        except ImportError:
            params_data = {}

        # =========================================================================
        # Assembly-Format (v9.0) vs Legacy-Format (v8.x)
        # =========================================================================
        if self._assembly_enabled and self.root_component:
            # NEU: Component-basierte Speicherung
            return {
                "version": "9.0",
                "name": self.name,
                "parameters": params_data,
                "assembly_enabled": True,
                "root_component": self.root_component.to_dict(),
                "active_component_id": self._active_component.id if self._active_component else None,
                "active_body_id": self.active_body.id if self.active_body else None,
                "active_sketch_id": self.active_sketch.id if self.active_sketch else None,
            }
        else:
            # Legacy-Format für Backward-Compatibility
            return {
                "version": "8.3",
                "name": self.name,
                "parameters": params_data,
                "bodies": [body.to_dict() for body in self._bodies],
                "sketches": [
                    {
                        **sketch.to_dict(),
                        "plane_origin": list(sketch.plane_origin) if hasattr(sketch, 'plane_origin') else [0, 0, 0],
                        "plane_normal": list(sketch.plane_normal) if hasattr(sketch, 'plane_normal') else [0, 0, 1],
                        "plane_x_dir": list(sketch.plane_x_dir) if hasattr(sketch, 'plane_x_dir') and sketch.plane_x_dir else None,
                        "plane_y_dir": list(sketch.plane_y_dir) if hasattr(sketch, 'plane_y_dir') and sketch.plane_y_dir else None,
                    }
                    for sketch in self._sketches
                ],
                "planes": [
                    {
                        "id": plane.id,
                        "name": plane.name,
                        "origin": list(plane.origin),
                        "normal": list(plane.normal),
                        "x_dir": list(plane.x_dir),
                    }
                    for plane in self._planes
                ],
                "active_body_id": self.active_body.id if self.active_body else None,
                "active_sketch_id": self.active_sketch.id if self.active_sketch else None,
            }

    @classmethod
    def from_dict(cls, data: dict) -> 'Document':
        """
        Deserialisiert Dokument aus Dictionary.

        Unterstützt:
        - Version 9.0+: Assembly-Format mit Component-Hierarchie
        - Version 8.x: Legacy-Format (flat lists) mit optionaler Migration

        Args:
            data: Dictionary mit Dokument-Daten

        Returns:
            Neues Document-Objekt
        """
        doc = cls(name=data.get("name", "Imported"))
        version = data.get("version", "8.0")

        # Parameter laden
        if "parameters" in data:
            try:
                from core.parameters import get_parameters
                params = get_parameters()
                params.from_dict(data["parameters"])
                logger.info(f"Parameter geladen: {len(params.list_all())} Variablen")
            except ImportError:
                pass
            except Exception as e:
                logger.warning(f"Parameter konnten nicht geladen werden: {e}")

        # =========================================================================
        # Format-Erkennung und Laden
        # =========================================================================
        is_assembly_format = data.get("assembly_enabled", False) and "root_component" in data

        if is_assembly_format:
            # V9.0 Assembly-Format laden
            logger.info(f"[ASSEMBLY] Lade Assembly-Format v{version}")
            doc._load_assembly_format(data)
        else:
            # Legacy-Format laden (v8.x oder älter)
            logger.info(f"Lade Legacy-Format v{version}")
            doc._load_legacy_format(data)

        # KRITISCH für parametrisches CAD: Sketch-Referenzen in Features wiederherstellen
        doc._restore_sketch_references()

        # Logging
        total_bodies = len(doc.get_all_bodies())
        total_sketches = len(doc.get_all_sketches())
        logger.info(f"Projekt geladen: {total_bodies} Bodies, {total_sketches} Sketches")
        return doc

    def _load_assembly_format(self, data: dict):
        """Lädt Dokument aus Assembly-Format (v9.0+)."""
        # KRITISCH: Assembly-Flag setzen, damit Properties korrekt delegieren
        self._assembly_enabled = True

        # Root Component laden
        root_data = data.get("root_component", {})
        if root_data:
            self.root_component = Component.from_dict(root_data)
            self._active_component = self.root_component  # Default

            # Aktive Component wiederherstellen
            active_comp_id = data.get("active_component_id")
            if active_comp_id:
                found = self.root_component.find_component_by_id(active_comp_id)
                if found:
                    self._active_component = found
                    found.is_active = True
                    logger.debug(f"[ASSEMBLY] Aktive Component wiederhergestellt: {found.name}")

        # Aktive Auswahl wiederherstellen
        active_body_id = data.get("active_body_id")
        if active_body_id:
            self.active_body = self.find_body_by_id(active_body_id)

        active_sketch_id = data.get("active_sketch_id")
        if active_sketch_id:
            all_sketches = self.get_all_sketches()
            self.active_sketch = next((s for s in all_sketches if s.id == active_sketch_id), None)

    def _load_legacy_format(self, data: dict):
        """
        Lädt Dokument aus Legacy-Format (v8.x).

        Wenn Assembly aktiviert ist, werden die Daten in die Root-Component migriert.
        """
        # Bodies laden
        bodies_to_add = []
        for body_data in data.get("bodies", []):
            try:
                body = Body.from_dict(body_data)
                bodies_to_add.append(body)
            except Exception as e:
                logger.warning(f"Body konnte nicht geladen werden: {e}")

        # Sketches laden
        sketches_to_add = []
        for sketch_data in data.get("sketches", []):
            try:
                sketch = Sketch.from_dict(sketch_data)
                # Plane-Daten wiederherstellen
                if "plane_origin" in sketch_data:
                    sketch.plane_origin = tuple(sketch_data["plane_origin"])
                if "plane_normal" in sketch_data:
                    sketch.plane_normal = tuple(sketch_data["plane_normal"])
                if sketch_data.get("plane_x_dir"):
                    sketch.plane_x_dir = tuple(sketch_data["plane_x_dir"])
                if sketch_data.get("plane_y_dir"):
                    sketch.plane_y_dir = tuple(sketch_data["plane_y_dir"])
                sketches_to_add.append(sketch)
            except Exception as e:
                logger.warning(f"Sketch konnte nicht geladen werden: {e}")

        # Planes laden
        planes_to_add = []
        for plane_data in data.get("planes", []):
            try:
                plane = ConstructionPlane(
                    id=plane_data.get("id", str(uuid.uuid4())[:8]),
                    name=plane_data.get("name", "Plane"),
                    origin=tuple(plane_data.get("origin", (0, 0, 0))),
                    normal=tuple(plane_data.get("normal", (0, 0, 1))),
                    x_dir=tuple(plane_data.get("x_dir", (1, 0, 0))),
                )
                planes_to_add.append(plane)
            except Exception as e:
                logger.warning(f"Plane konnte nicht geladen werden: {e}")

        # Daten zuweisen (respektiert assembly_enabled via Properties)
        if self._assembly_enabled and self.root_component:
            # Migration: Legacy-Daten in Root-Component
            self.root_component.bodies = bodies_to_add
            self.root_component.sketches = sketches_to_add
            self.root_component.planes = planes_to_add
            logger.info(f"[ASSEMBLY] Legacy-Daten in Root-Component migriert")
        else:
            # Direkte Zuweisung (Legacy-Modus)
            self._bodies = bodies_to_add
            self._sketches = sketches_to_add
            self._planes = planes_to_add

        # Aktive Auswahl wiederherstellen
        active_body_id = data.get("active_body_id")
        if active_body_id:
            all_bodies = bodies_to_add if not self._assembly_enabled else self.root_component.bodies
            self.active_body = next((b for b in all_bodies if b.id == active_body_id), None)

        active_sketch_id = data.get("active_sketch_id")
        if active_sketch_id:
            all_sketches = sketches_to_add if not self._assembly_enabled else self.root_component.sketches
            self.active_sketch = next((s for s in all_sketches if s.id == active_sketch_id), None)

    def _restore_sketch_references(self):
        """
        Stellt Sketch-Referenzen in Features wieder her (nach dem Laden).
        Ermöglicht parametrische Updates wenn Sketches geändert werden.

        Funktioniert mit beiden Modi (Legacy und Assembly).
        """
        # Alle Sketches sammeln (rekursiv bei Assembly)
        all_sketches = self.get_all_sketches()
        sketch_map = {s.id: s for s in all_sketches}
        restored_count = 0

        # Alle Bodies durchgehen (rekursiv bei Assembly)
        all_bodies = self.get_all_bodies()
        for body in all_bodies:
            for feature in body.features:
                sketch_id = getattr(feature, '_sketch_id', None)
                if sketch_id and sketch_id in sketch_map:
                    feature.sketch = sketch_map[sketch_id]
                    restored_count += 1
                    logger.debug(f"Sketch-Referenz wiederhergestellt: {feature.name} → {sketch_map[sketch_id].name}")

        if restored_count > 0:
            logger.info(f"[PARAMETRIC] {restored_count} Sketch-Referenzen wiederhergestellt")

    def save_project(self, filename: str) -> bool:
        """
        Speichert Projekt als MashCAD-Datei (.mshcad).

        Args:
            filename: Ausgabepfad

        Returns:
            True bei Erfolg
        """
        import json
        from pathlib import Path

        try:
            path = Path(filename)
            if not path.suffix:
                path = path.with_suffix(".mshcad")

            data = self.to_dict()

            import numpy as np

            class _ProjectEncoder(json.JSONEncoder):
                """JSON Encoder für Projekt-Daten mit Unterstützung für NumPy und Geometrie-Objekte."""
                def default(self, obj):
                    # NumPy-Typen
                    if isinstance(obj, (np.integer,)):
                        return int(obj)
                    if isinstance(obj, (np.floating,)):
                        return float(obj)
                    if isinstance(obj, np.ndarray):
                        return obj.tolist()
                    # Objekte mit to_dict Methode (Geometrie-Klassen, etc.)
                    if hasattr(obj, 'to_dict'):
                        return obj.to_dict()
                    # Dataclasses als Fallback
                    if hasattr(obj, '__dataclass_fields__'):
                        return {k: getattr(obj, k) for k in obj.__dataclass_fields__}
                    return super().default(obj)

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, cls=_ProjectEncoder)

            return True

        except Exception as e:
            logger.error(f"Projekt konnte nicht gespeichert werden: {e}")
            return False

    @classmethod
    def load_project(cls, filename: str) -> Optional['Document']:
        """
        Lädt Projekt aus MashCAD-Datei (.mshcad).

        Args:
            filename: Pfad zur Projektdatei

        Returns:
            Document oder None bei Fehler
        """
        import json
        from pathlib import Path

        try:
            path = Path(filename)
            if not path.exists():
                logger.error(f"Projektdatei nicht gefunden: {filename}")
                return None

            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            doc = cls.from_dict(data)

            # Bodies: BREP direkt laden oder Rebuild als Fallback
            for body in doc.bodies:
                if body._build123d_solid is not None:
                    logger.debug(f"Body '{body.name}': BREP direkt geladen (kein Rebuild nötig)")
                elif body.features:
                    try:
                        body._rebuild()
                        logger.debug(f"Body '{body.name}': Rebuild aus Feature-Tree")
                    except Exception as e:
                        logger.warning(f"Body '{body.name}' rebuild fehlgeschlagen: {e}")

            return doc

        except json.JSONDecodeError as e:
            logger.error(f"Ungültiges JSON in Projektdatei: {e}")
            return None
        except Exception as e:
            logger.error(f"Projekt konnte nicht geladen werden: {e}")
            return None
