
"""
MashCad - 3D Modeling
Robust B-Rep Implementation with Build123d & Smart Failure Recovery
"""

from dataclasses import asdict, dataclass, field
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
# TNP v4.0 ist aktiv - TNP v3.0 Legacy-Systeme wurden durch modernes ShapeNamingService ersetzt
from modeling.feature_dependency import FeatureDependencyGraph, get_dependency_graph  # Phase 7
from config.feature_flags import is_enabled  # Für TNP Debug Logging
from modeling.boolean_engine_v4 import BooleanEngineV4  # Zentraler Boolean-Engine

# TNP v4.0 - Professionelles Topological Naming System
from modeling.tnp_system import (
    ShapeNamingService, ShapeID, ShapeType,
    OperationRecord
)

# OCP-First Migration (Phase 2-3): OCP Helper für Extrude/Fillet/Chamfer
# Revolve/Loft/Sweep/Shell/Hollow nutzen jetzt direktes OCP in _compute_* Methoden
from modeling.ocp_helpers import (
    OCPExtrudeHelper,
    OCPFilletHelper,
    OCPChamferHelper
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


# ==================== HELPER FUNCTIONS ====================

def _solid_metrics(solid):
    """
    Geometry-Fingerprint (volume, faces, edges) eines Solids.

    Args:
        solid: Build123d Solid oder None

    Returns:
        dict mit keys 'volume', 'faces', 'edges' oder None bei Fehler
    """
    if solid is None:
        return None
    try:
        return {
            "volume": float(solid.volume),
            "faces": len(list(solid.faces())),
            "edges": len(list(solid.edges())),
        }
    except Exception:
        return None


# ==================== DATENSTRUKTUREN ====================

class FeatureType(Enum):
    SKETCH = auto()
    EXTRUDE = auto()
    REVOLVE = auto()
    FILLET = auto()
    CHAMFER = auto()
    TRANSFORM = auto()  # Für Move/Rotate/Scale/Mirror
    BOOLEAN = auto()    # Boolean-Operationen (Join, Cut, Common/Intersect)
    PUSHPULL = auto()   # Push/Pull auf Faces (Extrusion von existierenden Flächen)
    PATTERN = auto()    # Pattern (Linear, Circular, Mirror)
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
    NSIDED_PATCH = auto()     # N-seitiger Patch (Surface Fill)
    PRIMITIVE = auto()        # Primitive (Box, Cylinder, Sphere, Cone)
    IMPORT = auto()           # Importierter Body (Mesh-Konvertierung, STEP Import)

@dataclass
class Feature:
    type: FeatureType = None
    name: str = "Feature"
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    visible: bool = True
    suppressed: bool = False
    status: str = "OK" # OK, ERROR, WARNING
    status_message: str = ""
    # Structured status payload for UI/diagnostics (code, refs, hints).
    status_details: dict = field(default_factory=dict)

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
    # TNP v4.0: Push/Pull Face-Referenz (ShapeID primary, Index secondary, Selector fallback)
    face_shape_id: Any = None
    face_index: Optional[int] = None
    face_selector: dict = None  # GeometricFaceSelector als Legacy-Recovery

    # TNP v4.1: Sketch-Edge-Mapping nach Extrusion
    # Mapping von Sketch-Element-IDs zu den generierten 3D-Edge-ShapeIDs
    # Format: {sketch_element_id: edge_shape_uuid, ...}
    # Dies ermöglicht die Rückverfolgung von Sketch-Kanten zu 3D-Edges
    sketch_edge_mappings: dict = field(default_factory=dict)

    def __post_init__(self):
        self.type = FeatureType.EXTRUDE
        if not self.name or self.name == "Feature": self.name = "Extrude"
        if self.face_index is not None:
            try:
                self.face_index = int(self.face_index)
            except Exception:
                self.face_index = None

@dataclass
class RevolveFeature(Feature):
    """
    Revolve Feature - CAD Kernel First Architektur.

    Profile werden IMMER aus dem Sketch abgeleitet (wenn sketch vorhanden).
    profile_selector identifiziert welche Profile gewählt wurden (via Centroid).

    TNP v4.0: Face-Referenz für Push/Pull auf 3D-Faces (konsistent zu ExtrudeFeature).
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

    # TNP v4.0: Face-Referenz für Revolve-Push/Pull (konsistent zu ExtrudeFeature)
    # Ermöglicht Rebuild-Tracking von Faces nach Boolean-Operationen
    face_shape_id: Any = None
    face_index: Optional[int] = None
    face_selector: dict = None  # GeometricFaceSelector als Legacy-Recovery

    def __post_init__(self):
        self.type = FeatureType.REVOLVE
        if not self.name or self.name == "Feature": self.name = "Revolve"

@dataclass
class FilletFeature(Feature):
    """
    Fillet-Feature mit professionellem TNP (Topological Naming Problem) Handling.
    
    TNP v4.0 Architektur:
    1. edge_shape_ids: Persistent ShapeIDs für History-Tracking
    2. edge_indices: Stabile Topologie-Indizes (solid.edges()[idx])
    2. geometric_selectors: Geometrische Fingerabdrücke (Fallback)
    
    Das Feature speichert ShapeIDs beim Erstellen und löst diese
    via TNPResolver zum Zeitpunkt der Ausführung auf.
    """
    radius: float = 2.0
    radius_formula: Optional[str] = None
    
    # TNP v4.0: Persistent ShapeIDs (Primary)
    edge_shape_ids: List = None  # List[ShapeID] - persistente IDs
    edge_indices: List = None    # List[int] - stabile Kantenindizes
    
    # Fallback: Geometric Selectors
    geometric_selectors: List = None  # GeometricEdgeSelector Objekte
    
    ocp_edge_shapes: List = None  # OCP TopoDS_Edge Shapes
    
    # TNP Phase 2: Abhängigkeit zu vorherigem Boolean-Feature
    depends_on_feature_id: Optional[str] = None

    def __post_init__(self):
        self.type = FeatureType.FILLET
        if not self.name or self.name == "Feature":
            self.name = "Fillet"
        if self.edge_shape_ids is None:
            self.edge_shape_ids = []
        if self.edge_indices is None:
            self.edge_indices = []
        if self.geometric_selectors is None:
            self.geometric_selectors = []
        if self.ocp_edge_shapes is None:
            self.ocp_edge_shapes = []


@dataclass
class ChamferFeature(Feature):
    """
    Chamfer-Feature mit professionellem TNP (Topological Naming Problem) Handling.
    
    TNP v4.0 Architektur:
    1. edge_shape_ids: Persistent ShapeIDs für History-Tracking
    2. edge_indices: Stabile Topologie-Indizes (solid.edges()[idx])
    2. geometric_selectors: Geometrische Fingerabdrücke (Fallback)
    
    Das Feature speichert ShapeIDs beim Erstellen und löst diese
    via TNPResolver zum Zeitpunkt der Ausführung auf.
    """
    distance: float = 2.0
    distance_formula: Optional[str] = None
    
    # TNP v4.0: Persistent ShapeIDs (Primary)
    edge_shape_ids: List = None  # List[ShapeID] - persistente IDs
    edge_indices: List = None    # List[int] - stabile Kantenindizes
    
    # Fallback: Geometric Selectors
    geometric_selectors: List = None  # GeometricEdgeSelector Objekte
    
    ocp_edge_shapes: List = None  # OCP TopoDS_Edge Shapes
    
    # TNP Phase 2: Abhängigkeit zu vorherigem Boolean-Feature
    depends_on_feature_id: Optional[str] = None

    def __post_init__(self):
        self.type = FeatureType.CHAMFER
        if not self.name or self.name == "Feature":
            self.name = "Chamfer"
        if self.edge_shape_ids is None:
            self.edge_shape_ids = []
        if self.edge_indices is None:
            self.edge_indices = []
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


@dataclass
class BooleanFeature(Feature):
    """
    Boolean-Feature für professionelle CAD-Operationen.

    Unterützt Union (Join), Cut und Common (Intersect) mit:
    - BooleanEngineV4 Integration (Transaction Safety, Fail-Fast)
    - TNP v4.0 Shape-Tracking für verlässliche Referenzen
    - Tool-Body Referenz (für parametrische Updates)
    - Konfigurierbare Toleranzen

    Beispiel:
        feat = BooleanFeature(
            operation="Cut",
            tool_body_id=cutter_body.id,
            fuzzy_tolerance=0.0001
        )
    """
    # Boolean-Operation-Typ
    operation: str = "Cut"  # "Join" (Union), "Cut" (Subtract), "Common" (Intersect)

    # Tool-Referenz (Body oder direkter Solid)
    tool_body_id: Optional[str] = None  # ID des Tool-Body (für parametrische Updates)
    tool_solid_data: Optional[str] = None  # Serialisierter OCP Solid als Fallback

    # TNP v4.0: Shape-Referenzen für modifizierte Faces/Edges
    modified_shape_ids: List = None  # List[ShapeID] - vom Boolean veränderte Shapes

    # Boolean-Einstellungen
    fuzzy_tolerance: Optional[float] = None  # Custom Toleranz (None = Default)

    # Geometrie-Info für Validation
    expected_volume_change: Optional[float] = None  # Erwartete Volumenänderung

    def __post_init__(self):
        self.type = FeatureType.BOOLEAN
        if not self.name or self.name == "Feature":
            self.name = f"Boolean: {self.operation}"
        if self.modified_shape_ids is None:
            self.modified_shape_ids = []

    def get_operation_type(self) -> str:
        """Gibt den standardisierten Operation-Typ zurück."""
        op_map = {
            "Union": "Join",
            "Fuse": "Join",
            "Add": "Join",
            "Subtract": "Cut",
            "Difference": "Cut",
            "Intersect": "Common",
            "Common": "Common",
            "Intersection": "Common",
        }
        return op_map.get(self.operation, self.operation)

    def validate(self) -> tuple[bool, str]:
        """
        Validiert das Boolean-Feature vor Ausführung.

        Returns:
            (is_valid, error_message)
        """
        if self.operation not in ["Join", "Cut", "Common"]:
            return False, f"Unknown operation: {self.operation}"

        if self.tool_body_id is None and self.tool_solid_data is None:
            return False, "BooleanFeature needs tool_body_id or tool_solid_data"

        return True, ""


@dataclass
class PushPullFeature(Feature):
    """
    PushPull Feature - Interaktive Extrusion von existierenden Body-Faces.

    PushPull ermöglicht:
    - "Pull" (+distance): Material zur Face hinzufügen (Extrusion)
    - "Push" (-distance): Material von der Face entfernen (Cut)

    Arbeitet direkt auf Body-Faces ohne Sketch:
    - Face wird über face_shape_id, face_index oder face_selector referenziert
    - Face-Geometrie wird als Extrusions-Profil verwendet
    - Unterstützt planare und gekrümmte Faces (Zylinder, Kegel, etc.)

    Beispiel:
        feat = PushPullFeature(
            face_index=0,        # Obere Fläche einer Box
            distance=5.0,        # 5mm nach oben ziehen (Pull)
            direction=1          # Normalenrichtung der Face
        )
    """
    # Face-Referenz (welche Face wird extrudiert?)
    face_shape_id: Any = None           # TNP v4.0: Primäre Face-Referenz
    face_index: Optional[int] = None    # Fallback: Face-Index im Solid
    face_selector: dict = None          # GeometricFaceSelector als Legacy-Fallback

    # Extrusions-Parameter
    distance: float = 10.0              # Extrusions-Distanz (+ = Pull, - = Push)
    distance_formula: Optional[str] = None  # Formel für parametrische Distanz
    direction: int = 1                  # 1 = entlang Normal, -1 = entgegen Normal

    # Operation-Typ
    operation: str = "Join"             # "Join" (Pull/Add) oder "Cut" (Push/Remove)

    # Face-Geometrie für Rebuild (wenn Face nach Boolean nicht mehr auffindbar)
    face_brep: Optional[str] = None     # Serialisierte OCP TopoDS_Face
    face_type: Optional[str] = None     # "plane", "cylinder", "cone", etc.

    # Plane-Info für gekrümmte Faces (für Rekonstruktion der Extrusionsrichtung)
    plane_origin: tuple = field(default_factory=lambda: (0, 0, 0))
    plane_normal: tuple = field(default_factory=lambda: (0, 0, 1))
    plane_x_dir: tuple = None
    plane_y_dir: tuple = None

    # Profile als Fallback (wenn Face-BREP nicht verfügbar)
    precalculated_polys: list = field(default_factory=list)

    def __post_init__(self):
        self.type = FeatureType.PUSHPULL
        if not self.name or self.name == "Feature":
            op_name = "Pull" if self.distance >= 0 else "Push"
            self.name = f"PushPull: {op_name}"
        if self.face_index is not None:
            try:
                self.face_index = int(self.face_index)
            except Exception:
                self.face_index = None

    def get_effective_distance(self) -> float:
        """Gibt die effektive Distanz mit Richtung zurück."""
        return self.distance * self.direction

    def is_push(self) -> bool:
        """True wenn Push-Operation (Material entfernen)."""
        return self.get_effective_distance() < 0

    def is_pull(self) -> bool:
        """True wenn Pull-Operation (Material hinzufügen)."""
        return self.get_effective_distance() > 0

    def validate(self) -> tuple[bool, str]:
        """
        Validiert das PushPull-Feature vor Ausführung.

        Returns:
            (is_valid, error_message)
        """
        has_face_ref = (
            self.face_shape_id is not None or
            self.face_index is not None or
            self.face_selector is not None
        )

        if not has_face_ref:
            return False, "PushPullFeature needs face_shape_id, face_index, or face_selector"

        if self.distance == 0:
            return False, "PushPull distance cannot be zero"

        return True, ""


@dataclass
class PatternFeature(Feature):
    """
    Pattern Feature - Lineare, zirkulare und Spiegel-Muster.

    Pattern ermöglicht das mehrfache Wiederholen von Features:
    - Linear Pattern: Reihen in X/Y-Richtung mit Abständen
    - Circular Pattern: Rotation um einen Achsen-Punkt
    - Mirror Pattern: Spiegelung an einer Ebene

    Beispiel:
        # Linear Pattern: 3 Reihen à 5 Elemente, 20mm Abstand
        feat = PatternFeature(
            pattern_type="Linear",
            feature_id="base_feature_123",
            count=5,
            spacing=20.0,
            direction_1=(1, 0, 0),
            direction_2=(0, 1, 0),
            count_2=3
        )
    """
    # Pattern-Typ
    pattern_type: str = "Linear"  # "Linear", "Circular", "Mirror"

    # Feature-Referenz (welches Feature wird wiederholt?)
    feature_id: Optional[str] = None  # ID des zu wiederholenden Features
    feature_indices: List = field(default_factory=list)  # Legacy: Feature-Indizes

    # Linear Pattern Parameter
    count: int = 2                      # Anzahl der Kopien
    spacing: float = 10.0              # Abstand zwischen Kopien
    direction_1: Tuple[float, float, float] = (1, 0, 0)  # Primäre Richtung
    direction_2: Tuple[float, float, float] = (0, 1, 0)  # Sekundäre Richtung (für 2D)
    count_2: Optional[int] = None        # Anzahl in sekundärer Richtung

    # Circular Pattern Parameter
    axis_origin: Tuple[float, float, float] = (0, 0, 0)  # Drehpunkt (für Circular)
    axis_direction: Tuple[float, float, float] = (0, 0, 1)  # Achsenrichtung
    angle: float = 360.0               # Gesamtwinkel (für Circular)

    # Mirror Pattern Parameter
    mirror_plane: Optional[str] = None  # "XY", "XZ", "YZ" oder benutzerdefinierte Ebene
    mirror_origin: Tuple[float, float, float] = (0, 0, 0)
    mirror_normal: Tuple[float, float, float] = (0, 0, 1)

    def __post_init__(self):
        self.type = FeatureType.PATTERN
        if not self.name or self.name == "Feature":
            self.name = f"Pattern: {self.pattern_type}"
        if self.feature_indices is None:
            self.feature_indices = []

    def get_total_instances(self) -> int:
        """Gibt die Gesamtzahl der Instanzen zurück."""
        if self.pattern_type == "Linear":
            if self.count_2:
                return self.count * self.count_2
            return self.count
        elif self.pattern_type == "Circular":
            return self.count
        elif self.pattern_type == "Mirror":
            return 2  # Original + gespiegelt
        return 1

    def validate(self) -> tuple[bool, str]:
        """
        Validiert das Pattern-Feature vor Ausführung.

        Returns:
            (is_valid, error_message)
        """
        if self.pattern_type not in ["Linear", "Circular", "Mirror"]:
            return False, f"Unknown pattern_type: {self.pattern_type}"

        if self.pattern_type == "Linear":
            if self.count < 2:
                return False, "Linear pattern count must be at least 2"
            if self.spacing <= 0:
                return False, "Pattern spacing must be positive"

        elif self.pattern_type == "Circular":
            if self.count < 2:
                return False, "Circular pattern count must be at least 2"

        elif self.pattern_type == "Mirror":
            if not self.mirror_plane:
                return False, "Mirror pattern requires mirror_plane"

        return True, ""


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

    TNP v4.0: ShapeIDs für Profile und Path bei Body-Referenzen.
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
    #   "edge_indices": List[int],  # Topologie-Indizes im Referenz-Body
    #   "sketch_id": str | None,
    #   "body_id": str | None
    # }
    
    # TNP v4.0: ShapeIDs für Body-Referenzen (primary)
    profile_shape_id: Any = None  # ShapeID für Body-Face Profile
    path_shape_id: Any = None     # ShapeID für Body-Edge Path
    profile_face_index: Optional[int] = None  # Topologie-Index für Body-Face Profile

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
        if self.profile_face_index is not None:
            try:
                self.profile_face_index = int(self.profile_face_index)
            except Exception:
                self.profile_face_index = None

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
    # TNP v4.0: Stabile Topologie-Indizes (Secondary)
    face_indices: List = None  # List[int]
    
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
        if self.face_indices is None:
            self.face_indices = []


@dataclass
class HoleFeature(Feature):
    """
    Bohrung in eine Fläche.
    Typen: simple (Durchgangsbohrung/Sackloch), counterbore, countersink.
    
    TNP v4.0: Verwendet ShapeIDs + GeometricFaceSelector für stabile Face-Referenzierung.
    """
    hole_type: str = "simple"  # "simple", "counterbore", "countersink"
    diameter: float = 8.0
    diameter_formula: Optional[str] = None
    depth: float = 0.0  # 0 = through all
    depth_formula: Optional[str] = None
    
    # TNP v4.0: Persistent ShapeIDs für Faces (Primary)
    face_shape_ids: List = None  # List[ShapeID]
    # TNP v4.0: Stabile Topologie-Indizes (Secondary)
    face_indices: List = None  # List[int]
    
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
        if self.face_indices is None:
            self.face_indices = []


@dataclass
class DraftFeature(Feature):
    """
    Entformungsschräge (Draft/Taper) auf Flächen.
    Build123d: draft() auf selektierte Faces.
    
    TNP v4.0: Verwendet ShapeIDs + GeometricFaceSelector für stabile Face-Referenzierung.
    """
    draft_angle: float = 5.0  # Grad
    pull_direction: Tuple[float, float, float] = (0, 0, 1)
    
    # TNP v4.0: Persistent ShapeIDs für Faces (Primary)
    face_shape_ids: List = None  # List[ShapeID]
    # TNP v4.0: Stabile Topologie-Indizes (Secondary)
    face_indices: List = None  # List[int]
    
    # TNP-robust: Liste von GeometricFaceSelector.to_dict() Dicts (Fallback)
    # Enthält: center, normal, area, surface_type, tolerance
    face_selectors: List[dict] = field(default_factory=list)

    def __post_init__(self):
        self.type = FeatureType.DRAFT
        if not self.name or self.name == "Feature":
            self.name = f"Draft {self.draft_angle}°"
        if self.face_shape_ids is None:
            self.face_shape_ids = []
        if self.face_indices is None:
            self.face_indices = []


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
    
    TNP v4.0: ShapeID + Topology-Index für die zylindrische Face-Referenz.
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
    cosmetic: bool = True         # Kosmetisch: nur Helix-Linien im Viewport, echte Geometrie bei Export

    # TNP v4.0: Face-Referenz (ShapeID primary, Index secondary, Selector fallback)
    face_shape_id: Any = None  # ShapeID
    face_index: Optional[int] = None
    face_selector: dict = None  # GeometricFaceSelector als Fallback

    def __post_init__(self):
        self.type = FeatureType.THREAD
        if not self.name or self.name == "Feature":
            self.name = f"{self.standard}{self.diameter:.0f}x{self.pitch}"
        if self.face_index is not None:
            try:
                self.face_index = int(self.face_index)
            except Exception:
                self.face_index = None


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
    opening_face_indices: List = None    # List[int]
    opening_face_selectors: List = None  # List[GeometricFaceSelector]

    def __post_init__(self):
        self.type = FeatureType.HOLLOW
        if not self.name or self.name == "Feature":
            self.name = "Hollow"
        if self.opening_face_shape_ids is None:
            self.opening_face_shape_ids = []
        if self.opening_face_indices is None:
            self.opening_face_indices = []
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
    
    TNP v4.0: ShapeIDs für stabile Edge-Referenzen.
    """
    edge_indices: list = field(default_factory=list)    # Primär: stable edge indices (solid.edges()[idx])
    
    # TNP v4.0: ShapeIDs für Edges (Primary)
    edge_shape_ids: List = None  # List[ShapeID]
    
    # Geometric Selectors als Fallback
    geometric_selectors: List = None  # List[GeometricEdgeSelector]
    
    degree: int = 3
    tangent: bool = True

    def __post_init__(self):
        self.type = FeatureType.NSIDED_PATCH
        if not self.name or self.name == "Feature":
            edge_count = (
                len(self.edge_shape_ids or [])
                or len(self.edge_indices or [])
                or len(self.geometric_selectors or [])
            )
            self.name = f"N-Sided Patch ({edge_count} edges)"
        if self.edge_shape_ids is None:
            self.edge_shape_ids = []
        if self.edge_indices is None:
            self.edge_indices = []
        if self.geometric_selectors is None:
            self.geometric_selectors = []


@dataclass
class PrimitiveFeature(Feature):
    """
    Primitive Feature — Box, Cylinder, Sphere, Cone.

    Speichert die Erstellungs-Parameter, sodass das Solid bei Rebuild
    reproduzierbar ist. Dient als Base-Feature (erstes Feature eines Bodies).
    """
    primitive_type: str = "box"  # "box", "cylinder", "sphere", "cone"
    length: float = 10.0
    width: float = 10.0
    height: float = 10.0
    radius: float = 5.0
    bottom_radius: float = 5.0
    top_radius: float = 0.0

    def __post_init__(self):
        self.type = FeatureType.PRIMITIVE
        if not self.name or self.name == "Feature":
            self.name = f"Primitive ({self.primitive_type.capitalize()})"

    def create_solid(self):
        """
        Erstellt das Build123d Solid aus den Parametern.

        TNP v4.1: Alle build123d Primitive sind native OCP (keine Approximation).
        - Box: 6 Faces
        - Cylinder: 3 Faces (Mantel + 2 Deckflächen)
        - Sphere: 1 Face (Kugelfläche)
        - Cone: 2 Faces (Mantel + Deckfläche)
        """
        try:
            import build123d as bd
            if self.primitive_type == "box":
                # Box: native OCP (6 Faces)
                return bd.Box(self.length, self.width, self.height)
            elif self.primitive_type == "cylinder":
                # Cylinder: native OCP mit build123d (3 Faces)
                # TNP v4.1: bd.Solid.make_cylinder() ist native OCP
                return bd.Solid.make_cylinder(self.radius, self.height)
            elif self.primitive_type == "sphere":
                # Sphere: native OCP (1 Face)
                return bd.Solid.make_sphere(self.radius)
            elif self.primitive_type == "cone":
                # Cone: native OCP (2 Faces)
                # build123d make_cone: (base_radius, top_radius, height)
                return bd.Solid.make_cone(self.bottom_radius, self.top_radius, self.height)
        except Exception as e:
            logger.error(f"PrimitiveFeature.create_solid() failed: {e}")
            import traceback
            traceback.print_exc()
        return None


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

    TNP v4.0: ShapeIDs + Face-Indizes + GeometricFaceSelector.

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
    
    # TNP v4.0: Topology-Indizes (Secondary)
    face_indices: List = None  # List[int]

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
        if self.face_indices is None:
            self.face_indices = []
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
            "status_message": self.status_message,
            "status_details": self.status_details,
            "texture_type": self.texture_type,
            "face_indices": self.face_indices,
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
            status_message=data.get("status_message", ""),
            status_details=data.get("status_details", {}),
            texture_type=data.get("texture_type", "ripple"),
            face_indices=data.get("face_indices", []),
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

        # Kosmetische Gewinde-Linien (Helix-Visualisierung ohne echte Geometrie)
        self._cosmetic_lines_cache = None   # pv.PolyData (Helix-Linien)
        self._cosmetic_lines_valid = False

        # Legacy Visualisierungs-Daten (Nur als Fallback)
        self._mesh_vertices: List[Tuple[float, float, float]] = []
        self._mesh_triangles: List[Tuple[int, int, int]] = []
        self._mesh_normals = []
        self._mesh_edges = []
        # Letzte operationelle Fehlermeldung aus _safe_operation für UI/Feature-Status.
        self._last_operation_error = ""
        self._last_operation_error_details = {}

    @staticmethod
    def _convert_legacy_nsided_edge_selectors(edge_selectors: Optional[List]) -> List[dict]:
        """
        Konvertiert legacy NSided edge_selectors zu GeometricEdgeSelector-Dicts.

        Altes Format:
        - (cx, cy, cz)
        - ((cx, cy, cz), (dx, dy, dz))
        """
        if not edge_selectors:
            return []

        def _as_vec3(value):
            if not isinstance(value, (list, tuple)) or len(value) < 3:
                return None
            try:
                return [float(value[0]), float(value[1]), float(value[2])]
            except Exception:
                return None

        migrated = []
        for selector in edge_selectors:
            center = None
            direction = None

            if isinstance(selector, (list, tuple)):
                if len(selector) == 2 and isinstance(selector[0], (list, tuple)):
                    center = _as_vec3(selector[0])
                    direction = _as_vec3(selector[1])
                else:
                    center = _as_vec3(selector)

            if center is None:
                continue

            if direction is None or abs(direction[0]) + abs(direction[1]) + abs(direction[2]) < 1e-12:
                direction = [1.0, 0.0, 0.0]

            migrated.append({
                "center": center,
                "direction": direction,
                "length": 0.0,
                "curve_type": "unknown",
                "tolerance": 25.0,
            })

        return migrated

    @staticmethod
    def _convert_legacy_edge_selectors(edge_selectors: Optional[List]) -> List[dict]:
        """
        Konvertiert legacy Fillet/Chamfer edge_selectors zu GeometricEdgeSelector-Dicts.

        Altes Format:
        - (cx, cy, cz)
        """
        if not edge_selectors:
            return []

        migrated = []
        for selector in edge_selectors:
            if not isinstance(selector, (list, tuple)) or len(selector) < 3:
                continue
            try:
                center = [float(selector[0]), float(selector[1]), float(selector[2])]
            except Exception:
                continue

            migrated.append({
                "center": center,
                "direction": [1.0, 0.0, 0.0],
                "length": 0.0,
                "curve_type": "unknown",
                "tolerance": 25.0,
            })

        return migrated

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

    @property
    def vtk_cosmetic_lines(self):
        """Lazy-loaded kosmetische Gewinde-Linien (Helix-Visualisierung)."""
        if not self._cosmetic_lines_valid:
            self._regenerate_cosmetic_lines()
        return self._cosmetic_lines_cache

    def _regenerate_cosmetic_lines(self):
        """Erzeugt Helix-Linien für alle kosmetischen ThreadFeatures."""
        self._cosmetic_lines_valid = True
        cosmetic_threads = [f for f in self.features
                            if isinstance(f, ThreadFeature) and f.cosmetic]
        if not cosmetic_threads:
            self._cosmetic_lines_cache = None
            return

        try:
            import numpy as np
            import pyvista as pv
            from build123d import Helix

            all_points = []
            all_lines = []
            offset = 0

            for feat in cosmetic_threads:
                r = feat.diameter / 2.0
                H = 0.8660254 * feat.pitch
                groove_depth = 0.625 * H

                # Zwei Helix-Linien: Innen- und Außenradius des Gewindes
                for radius in [r - groove_depth, r]:
                    helix = Helix(
                        pitch=feat.pitch,
                        height=feat.depth,
                        radius=radius,
                        center=tuple(feat.position),
                        direction=tuple(feat.direction)
                    )
                    # Sample Punkte entlang der Helix
                    n_samples = max(20, int(feat.depth / feat.pitch * 12))
                    pts = []
                    for j in range(n_samples + 1):
                        t = j / n_samples
                        pt = helix.position_at(t)
                        pts.append([pt.X, pt.Y, pt.Z])

                    pts_arr = np.array(pts)
                    n_pts = len(pts_arr)
                    all_points.append(pts_arr)

                    # Polyline: [n_pts, idx0, idx1, ..., idx_n-1]
                    line = [n_pts] + list(range(offset, offset + n_pts))
                    all_lines.extend(line)
                    offset += n_pts

            if all_points:
                points = np.vstack(all_points)
                self._cosmetic_lines_cache = pv.PolyData(points, lines=all_lines)
                logger.debug(f"[COSMETIC] {len(cosmetic_threads)} thread(s) → "
                             f"{points.shape[0]} pts helix lines")
            else:
                self._cosmetic_lines_cache = None
        except Exception as e:
            logger.warning(f"Cosmetic thread lines failed: {e}")
            self._cosmetic_lines_cache = None

    def _get_solid_with_threads(self):
        """Berechnet echte Gewinde auf einer Kopie des Solids (für Export).

        Iteriert über alle kosmetischen ThreadFeatures und wendet
        _compute_thread() auf eine Kopie an. Original bleibt unverändert.
        """
        if self._build123d_solid is None:
            return None

        cosmetic_threads = [f for f in self.features
                            if isinstance(f, ThreadFeature) and f.cosmetic]
        if not cosmetic_threads:
            return self._build123d_solid

        logger.info(f"[EXPORT] Computing {len(cosmetic_threads)} real thread(s) for export...")
        current = self._build123d_solid
        for feat in cosmetic_threads:
            try:
                current = self._compute_thread(feat, current)
                logger.debug(f"[EXPORT] Thread {feat.name} applied")
            except Exception as e:
                logger.warning(f"[EXPORT] Thread {feat.name} failed: {e}")

        return current

    def invalidate_mesh(self):
        """Invalidiert Mesh-Cache - nächster Zugriff regeneriert automatisch"""
        self._mesh_cache_valid = False
        self._cosmetic_lines_valid = False

        # WICHTIG: Auch Face-Info-Cache löschen!
        # Sonst bleiben alte Face-IDs bestehen die nach Boolean ungültig sind
        self._face_info_cache = {}

        # Phase 4.3: Auch Topology-Cache invalidieren
        if self._build123d_solid is not None:
            try:
                CADTessellator.invalidate_topology_cache(id(self._build123d_solid.wrapped))
            except Exception as e:
                logger.debug(f"[__init__.py] Fehler: {e}")
                pass  # Solid hat kein wrapped (selten)

    def request_async_tessellation(self, on_ready=None):
        """
        Phase 9: Startet Tessellation im Hintergrund (Non-Blocking).

        Das Mesh wird asynchron generiert und via Callback zurückgegeben.
        vtk_mesh Property bleibt synchron (für Kompatibilität).

        Args:
            on_ready: Optional callback(body_id, mesh, edges, face_info)
                      Wenn None, wird das Mesh direkt in den Cache geschrieben.
        """
        if not is_enabled("async_tessellation"):
            # Synchroner Fallback
            self._regenerate_mesh()
            return

        if self._build123d_solid is None:
            return

        from gui.workers.tessellation_worker import TessellationWorker

        def _on_mesh_ready(body_id, mesh, edges, face_info):
            """Callback: Mesh ist fertig, in Body-Cache schreiben."""
            self._mesh_cache = mesh
            self._edges_cache = edges
            self._face_info_cache = face_info
            self._mesh_cache_valid = True
            n_pts = mesh.n_points if mesh else 0
            logger.debug(f"Async Mesh ready for '{self.name}': {n_pts} pts")
            if on_ready:
                on_ready(body_id, mesh, edges, face_info)

        worker = TessellationWorker(self.id, self._build123d_solid)
        worker.mesh_ready.connect(_on_mesh_ready)
        # Worker-Referenz halten damit er nicht garbage-collected wird
        self._tessellation_worker = worker
        worker.start()

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

                # TNP v4.0: ShapeID-Registrierung für konvertierte Geometrie
                try:
                    if self._document and hasattr(self._document, '_shape_naming_service'):
                        service = self._document._shape_naming_service
                        if service is not None:
                            feature_id = f"mesh_convert_{self.id}"

                            # Alle Edges registrieren
                            edge_count = service.register_solid_edges(solid, feature_id)

                            # Alle Faces registrieren
                            try:
                                from OCP.TopExp import TopExp_Explorer
                                from OCP.TopAbs import TopAbs_FACE
                                from modeling.tnp_system import ShapeType

                                face_idx = 0
                                explorer = TopExp_Explorer(solid.wrapped, TopAbs_FACE)
                                while explorer.More():
                                    face_shape = explorer.Current()
                                    service.register_shape(
                                        ocp_shape=face_shape,
                                        shape_type=ShapeType.FACE,
                                        feature_id=feature_id,
                                        local_index=face_idx
                                    )
                                    face_idx += 1
                                    explorer.Next()

                                logger.info(f"  [TNP] {edge_count} Edges, {face_idx} Faces registriert")
                            except Exception as e:
                                logger.debug(f"[TNP] Face-Registrierung fehlgeschlagen: {e}")
                except Exception as e:
                    logger.debug(f"[TNP] Registrierung fehlgeschlagen: {e}")

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
            
    @staticmethod
    def _format_index_refs_for_error(label: str, refs, max_items: int = 3) -> str:
        """Formatiert Index-Referenzen kompakt für Fehlermeldungen."""
        if refs is None:
            return ""
        values = refs if isinstance(refs, (list, tuple)) else [refs]
        normalized = []
        for raw in values:
            try:
                idx = int(raw)
            except Exception:
                continue
            if idx >= 0:
                normalized.append(idx)
        if not normalized:
            return ""
        preview = normalized[:max_items]
        suffix = "..." if len(normalized) > max_items else ""
        return f"{label}={preview}{suffix}"

    @staticmethod
    def _format_shape_refs_for_error(label: str, refs, max_items: int = 3) -> str:
        """Formatiert ShapeID-Referenzen kompakt für Fehlermeldungen."""
        if refs is None:
            return ""
        values = refs if isinstance(refs, (list, tuple)) else [refs]
        tokens = []
        for raw in values:
            if raw is None:
                continue
            try:
                raw_uuid = getattr(raw, "uuid", None)
                if raw_uuid:
                    shape_type = getattr(raw, "shape_type", None)
                    shape_name = shape_type.name if hasattr(shape_type, "name") else (str(shape_type) if shape_type else "?")
                    local_index = getattr(raw, "local_index", None)
                    token = f"{shape_name}:{str(raw_uuid)[:8]}"
                    if local_index is not None:
                        token += f"@{local_index}"
                    tokens.append(token)
                    continue
                if isinstance(raw, dict):
                    shape_name = raw.get("shape_type", "?")
                    feature_id = raw.get("feature_id", "?")
                    local_index = raw.get("local_index", raw.get("local_id", "?"))
                    tokens.append(f"{shape_name}:{feature_id}@{local_index}")
            except Exception:
                continue
        if not tokens:
            return ""
        preview = tokens[:max_items]
        suffix = "..." if len(tokens) > max_items else ""
        return f"{label}={preview}{suffix}"

    def _collect_feature_reference_diagnostics(self, feature, max_parts: int = 6) -> str:
        """
        Baut eine kompakte Referenz-Zusammenfassung für Statusmeldungen.

        Wird an Fehlermeldungen angehängt, damit GUI/Tooltip direkt zeigen kann,
        welche Topologie-Referenzen betroffen waren.
        """
        if feature is None:
            return ""

        parts = []

        def _add(part: str) -> None:
            if part:
                parts.append(part)

        # Face-Referenzen
        _add(self._format_index_refs_for_error("face_indices", getattr(feature, "face_indices", None)))
        _add(self._format_index_refs_for_error("opening_face_indices", getattr(feature, "opening_face_indices", None)))
        _add(self._format_index_refs_for_error("face_index", getattr(feature, "face_index", None)))
        _add(self._format_index_refs_for_error("profile_face_index", getattr(feature, "profile_face_index", None)))

        # Edge-Referenzen
        _add(self._format_index_refs_for_error("edge_indices", getattr(feature, "edge_indices", None)))
        path_data = getattr(feature, "path_data", None)
        if isinstance(path_data, dict):
            _add(self._format_index_refs_for_error("path.edge_indices", path_data.get("edge_indices", None)))

        # ShapeID-Referenzen
        _add(self._format_shape_refs_for_error("face_shape_ids", getattr(feature, "face_shape_ids", None)))
        _add(self._format_shape_refs_for_error("opening_face_shape_ids", getattr(feature, "opening_face_shape_ids", None)))
        _add(self._format_shape_refs_for_error("edge_shape_ids", getattr(feature, "edge_shape_ids", None)))
        _add(self._format_shape_refs_for_error("face_shape_id", getattr(feature, "face_shape_id", None)))
        _add(self._format_shape_refs_for_error("profile_shape_id", getattr(feature, "profile_shape_id", None)))
        _add(self._format_shape_refs_for_error("path_shape_id", getattr(feature, "path_shape_id", None)))

        if not parts:
            return ""

        if len(parts) > max_parts:
            hidden = len(parts) - max_parts
            parts = parts[:max_parts]
            parts.append(f"+{hidden} weitere")
        return "; ".join(parts)

    @staticmethod
    def _collect_feature_reference_payload(feature) -> dict:
        """
        Liefert maschinenlesbare Referenzdaten für Status-Details.
        """
        if feature is None:
            return {}

        payload = {}

        def _indices(value):
            values = value if isinstance(value, (list, tuple)) else [value]
            out = []
            for raw in values:
                try:
                    idx = int(raw)
                except Exception:
                    continue
                if idx >= 0:
                    out.append(idx)
            return out

        def _shape_tokens(value):
            values = value if isinstance(value, (list, tuple)) else [value]
            out = []
            for raw in values:
                if raw is None:
                    continue
                try:
                    raw_uuid = getattr(raw, "uuid", None)
                    if raw_uuid:
                        shape_type = getattr(raw, "shape_type", None)
                        shape_name = shape_type.name if hasattr(shape_type, "name") else (str(shape_type) if shape_type else "?")
                        local_index = getattr(raw, "local_index", None)
                        token = f"{shape_name}:{str(raw_uuid)[:8]}"
                        if local_index is not None:
                            token += f"@{local_index}"
                        out.append(token)
                        continue
                    if isinstance(raw, dict):
                        shape_name = raw.get("shape_type", "?")
                        feature_id = raw.get("feature_id", "?")
                        local_index = raw.get("local_index", raw.get("local_id", "?"))
                        out.append(f"{shape_name}:{feature_id}@{local_index}")
                except Exception:
                    continue
            return out

        face_indices = _indices(getattr(feature, "face_indices", None))
        if face_indices:
            payload["face_indices"] = face_indices

        opening_face_indices = _indices(getattr(feature, "opening_face_indices", None))
        if opening_face_indices:
            payload["opening_face_indices"] = opening_face_indices

        face_index = _indices(getattr(feature, "face_index", None))
        if face_index:
            payload["face_index"] = face_index

        profile_face_index = _indices(getattr(feature, "profile_face_index", None))
        if profile_face_index:
            payload["profile_face_index"] = profile_face_index

        edge_indices = _indices(getattr(feature, "edge_indices", None))
        if edge_indices:
            payload["edge_indices"] = edge_indices

        path_data = getattr(feature, "path_data", None)
        if isinstance(path_data, dict):
            path_edge_indices = _indices(path_data.get("edge_indices", None))
            if path_edge_indices:
                payload["path.edge_indices"] = path_edge_indices

        for key in (
            "face_shape_ids",
            "opening_face_shape_ids",
            "edge_shape_ids",
            "face_shape_id",
            "profile_shape_id",
            "path_shape_id",
        ):
            tokens = _shape_tokens(getattr(feature, key, None))
            if tokens:
                payload[key] = tokens

        return payload

    def _build_operation_error_details(
        self,
        *,
        op_name: str,
        code: str,
        message: str,
        feature=None,
        hint: str = "",
        fallback_error: str = "",
    ) -> dict:
        details = {
            "code": code,
            "operation": op_name,
            "message": message,
        }
        refs = self._collect_feature_reference_payload(feature)
        if refs:
            details["refs"] = refs
        if hint:
            details["hint"] = hint
        if fallback_error:
            details["fallback_error"] = fallback_error
        return details

    def _safe_operation(self, op_name, op_func, fallback_func=None, feature=None):
        """
        Wrapper für kritische CAD-Operationen.
        Fängt Crashes ab und erlaubt Fallbacks.
        """
        try:
            self._last_operation_error = ""
            self._last_operation_error_details = {}
            result = op_func()
            
            if result is None:
                raise ValueError("Operation returned None")
            
            if hasattr(result, 'is_valid') and not result.is_valid():
                raise ValueError("Result geometry is invalid")

            return result, "SUCCESS"
            
        except Exception as e:
            err_msg = str(e).strip() or e.__class__.__name__
            ref_diag = self._collect_feature_reference_diagnostics(feature)
            if ref_diag and "refs:" not in err_msg:
                err_msg = f"{err_msg} | refs: {ref_diag}"
            self._last_operation_error = err_msg
            self._last_operation_error_details = self._build_operation_error_details(
                op_name=op_name,
                code="operation_failed",
                message=err_msg,
                feature=feature,
            )
            logger.warning(f"Feature '{op_name}' fehlgeschlagen: {err_msg}")
            
            if fallback_func:
                strict_self_heal = is_enabled("self_heal_strict")
                has_topology_refs = self._feature_has_topological_references(feature) if feature is not None else False
                if strict_self_heal and has_topology_refs:
                    self._last_operation_error = (
                        f"Primärpfad fehlgeschlagen: {err_msg}; "
                        "Strict Self-Heal blockiert Fallback bei Topologie-Referenzen"
                    )
                    self._last_operation_error_details = self._build_operation_error_details(
                        op_name=op_name,
                        code="fallback_blocked_strict",
                        message=self._last_operation_error,
                        feature=feature,
                        hint="Feature neu referenzieren oder Parameter reduzieren.",
                    )
                    logger.error(
                        f"Strict Self-Heal: Fallback für '{op_name}' blockiert "
                        "(Topologie-Referenzen aktiv)."
                    )
                    return None, "ERROR"
                logger.debug(f"→ Versuche Fallback für '{op_name}'...")
                try:
                    res_fallback = fallback_func()
                    if res_fallback:
                        self._last_operation_error = f"Primärpfad fehlgeschlagen: {err_msg}; Fallback wurde verwendet"
                        self._last_operation_error_details = self._build_operation_error_details(
                            op_name=op_name,
                            code="fallback_used",
                            message=self._last_operation_error,
                            feature=feature,
                        )
                        logger.debug(f"✓ Fallback für '{op_name}' erfolgreich.")
                        return res_fallback, "WARNING"
                except Exception as e2:
                    fallback_msg = str(e2).strip() or e2.__class__.__name__
                    self._last_operation_error = (
                        f"Primärpfad fehlgeschlagen: {err_msg}; Fallback fehlgeschlagen: {fallback_msg}"
                    )
                    self._last_operation_error_details = self._build_operation_error_details(
                        op_name=op_name,
                        code="fallback_failed",
                        message=self._last_operation_error,
                        feature=feature,
                        fallback_error=fallback_msg,
                    )
                    logger.error(f"✗ Auch Fallback fehlgeschlagen: {fallback_msg}")
            
            return None, "ERROR"

    def _register_boolean_history(self, bool_result: BooleanResult, feature, operation_name: str = ""):
        """
        Registriert Boolean-History für TNP v4.0.

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

    def _register_fillet_chamfer_history(self, result_solid, history, feature, operation_type: str = "FILLET"):
        """
        Registriert Fillet/Chamfer History für TNP v4.0.

        Phase 12: Nutzt BRepFilletAPI_MakeFillet.History() für präzises Shape-Tracking
        nach Fillet/Chamfer-Operationen.

        Args:
            result_solid: Das resultierende Build123d Solid
            history: BRepTools_History von der Fillet/Chamfer-Operation
            feature: Das FilletFeature/ChamferFeature
            operation_type: "FILLET" oder "CHAMFER"
        """
        if history is None:
            return

        # TNP v4.0: ShapeNamingService
        if self._document and hasattr(self._document, '_shape_naming_service'):
            try:
                service = self._document._shape_naming_service
                service.record_operation(
                    OperationRecord(
                        operation_id=str(uuid.uuid4())[:8],
                        operation_type=operation_type,
                        feature_id=getattr(feature, 'id', 'unknown'),
                        occt_history=history,
                    )
                )
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP v4.0: {operation_type} History registriert")
            except Exception as tnp_e:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP v4.0 {operation_type} History-Registrierung fehlgeschlagen: {tnp_e}")

    @staticmethod
    def _build_history_from_make_shape(make_shape_op, input_shape):
        """
        Baut ein BRepTools_History aus einer BRepBuilderAPI_MakeShape-Operation.

        Phase 12: BRepFilletAPI_MakeFillet/MakeChamfer erben von BRepBuilderAPI_MakeShape
        und haben Generated()/Modified()/IsDeleted() aber kein direktes History().
        Diese Methode konstruiert die History manuell.

        Args:
            make_shape_op: BRepBuilderAPI_MakeShape (z.B. BRepFilletAPI_MakeFillet)
            input_shape: Das Original-Shape vor der Operation

        Returns:
            BRepTools_History mit allen Zuordnungen
        """
        from OCP.BRepTools import BRepTools_History
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX

        history = BRepTools_History()

        for shape_type in (TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX):
            explorer = TopExp_Explorer(input_shape, shape_type)
            while explorer.More():
                sub_shape = explorer.Current()
                try:
                    for s in make_shape_op.Generated(sub_shape):
                        history.AddGenerated(sub_shape, s)
                except Exception:
                    pass
                try:
                    for s in make_shape_op.Modified(sub_shape):
                        history.AddModified(sub_shape, s)
                except Exception:
                    pass
                try:
                    if make_shape_op.IsDeleted(sub_shape):
                        history.Remove(sub_shape)
                except Exception:
                    pass
                explorer.Next()

        return history

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

    def _ocp_fillet(self, solid, edges, radius, extract_history=False):
        """
        OCP-basiertes Fillet (robuster als Build123d).

        Args:
            solid: Build123d Solid
            edges: Liste von Edges
            radius: Fillet-Radius
            extract_history: True → gibt (Solid, History) Tuple zurück für TNP

        Returns:
            Build123d Solid oder None (oder (Solid, History) wenn extract_history=True)
        """
        if not HAS_OCP:
            return (None, None) if extract_history else None

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
                return (None, None) if extract_history else None

            result_shape = fillet_op.Shape()

            # History extrahieren (Phase 12: Batch Fillets TNP-Integration)
            history = None
            if extract_history:
                try:
                    history = self._build_history_from_make_shape(fillet_op, shape)
                    if is_enabled("tnp_debug_logging"):
                        logger.debug(f"Fillet History extrahiert: Gen={history.HasGenerated()}, Mod={history.HasModified()}, Rem={history.HasRemoved()}")
                except Exception as h_e:
                    logger.debug(f"Fillet History-Extraktion fehlgeschlagen: {h_e}")

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
                    return (result, history) if extract_history else result
                else:
                    return (None, None) if extract_history else None
            except Exception as e:
                logger.debug(f"[__init__.py] Fehler: {e}")
                return (None, None) if extract_history else None

        except Exception as e:
            logger.debug(f"OCP Fillet Fehler: {e}")
            return (None, None) if extract_history else None

    def _ocp_chamfer(self, solid, edges, distance, extract_history=False):
        """
        OCP-basiertes Chamfer (robuster als Build123d).

        Args:
            solid: Build123d Solid
            edges: Liste von Edges
            distance: Chamfer-Distanz
            extract_history: True → gibt (Solid, History) Tuple zurück für TNP

        Returns:
            Build123d Solid oder None (oder (Solid, History) wenn extract_history=True)
        """
        if not HAS_OCP:
            return (None, None) if extract_history else None

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
                return (None, None) if extract_history else None

            result_shape = chamfer_op.Shape()

            # History extrahieren (Phase 12: Batch Fillets TNP-Integration)
            history = None
            if extract_history:
                try:
                    history = self._build_history_from_make_shape(chamfer_op, shape)
                    if is_enabled("tnp_debug_logging"):
                        logger.debug(f"Chamfer History extrahiert: Gen={history.HasGenerated()}, Mod={history.HasModified()}, Rem={history.HasRemoved()}")
                except Exception as h_e:
                    logger.debug(f"Chamfer History-Extraktion fehlgeschlagen: {h_e}")

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
                    return (result, history) if extract_history else result
                else:
                    return (None, None) if extract_history else None
            except Exception as e:
                logger.debug(f"[__init__.py] Fehler: {e}")
                return (None, None) if extract_history else None

        except Exception as e:
            logger.debug(f"OCP Chamfer Fehler: {e}")
            return (None, None) if extract_history else None

    # ==================== PHASE 6: COMPUTE METHODS ====================

    def _compute_revolve(self, feature: 'RevolveFeature'):
        """
        OCP-First Revolve mit direktem OpenCASCADE BRepPrimAPI_MakeRevol.

        CAD Kernel First: Profile werden IMMER aus dem Sketch abgeleitet.

        Architektur:
        1. Mit Sketch: Profile aus sketch.closed_profiles (immer aktuell)
           - profile_selector filtert welche Profile gewählt wurden
        2. Ohne Sketch: precalculated_polys als Geometrie-Quelle (Legacy)
        """
        import math
        from build123d import Plane, make_face, Wire, Vector, Solid
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
        from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt

        sketch = feature.sketch
        if not sketch:
            raise ValueError("Revolve: Kein Sketch vorhanden")

        # Sketch-Plane bestimmen
        plane_origin = getattr(sketch, 'plane_origin', (0, 0, 0))
        plane_normal = getattr(sketch, 'plane_normal', (0, 0, 1))
        x_dir = getattr(sketch, 'plane_x_dir', None)

        # Validate plane_normal is not zero
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
                raise ValueError("Revolve: Selektor-Match fehlgeschlagen")
        elif sketch_profiles:
            # Kein Selektor → alle Profile verwenden (Legacy/Import)
            polys_to_revolve = list(sketch_profiles)
            logger.info(f"Revolve: Alle {len(polys_to_revolve)} Profile (kein Selektor)")
        else:
            # Sketch hat keine closed_profiles
            raise ValueError("Revolve: Sketch hat keine closed_profiles")

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

        # Achse bestimmen (OCP gp_Ax1)
        axis_vec = feature.axis
        axis_origin_vec = feature.axis_origin if feature.axis_origin else (0, 0, 0)

        # OCP Achse erstellen
        ocp_origin = gp_Pnt(axis_origin_vec[0], axis_origin_vec[1], axis_origin_vec[2])
        ocp_direction = gp_Dir(axis_vec[0], axis_vec[1], axis_vec[2])
        ocp_axis = gp_Ax1(ocp_origin, ocp_direction)

        # Winkel in Bogenmaß
        angle_rad = math.radians(feature.angle)

        # OCP-First Revolve (alle Faces revolve und Union)
        result_solid = None
        for i, face in enumerate(faces_to_revolve):
            revolve_op = BRepPrimAPI_MakeRevol(face.wrapped, ocp_axis, angle_rad)
            revolve_op.Build()

            if not revolve_op.IsDone():
                raise ValueError(f"Revolve fehlgeschlagen für Face {i+1}/{len(faces_to_revolve)}")

            revolved_shape = revolve_op.Shape()
            revolved = Solid(revolved_shape)

            if result_solid is None:
                result_solid = revolved
            else:
                # Union mehrerer Revolve-Ergebnisse
                result_solid = result_solid.fuse(revolved)

        if result_solid is None or result_solid.is_null():
            raise ValueError("Revolve erzeugte keine Geometrie")

        # TNP-Registration wenn naming_service verfügbar
        if self._document and hasattr(self._document, '_shape_naming_service'):
            try:
                naming_service = self._document._shape_naming_service
                feature_id = getattr(feature, 'id', None) or str(id(feature))

                # Alle Faces registrieren
                from modeling.tnp_system import ShapeType
                from OCP.TopExp import TopExp_Explorer
                from OCP.TopAbs import TopAbs_FACE

                explorer = TopExp_Explorer(result_solid.wrapped, TopAbs_FACE)
                face_idx = 0
                while explorer.More():
                    face_shape = explorer.Current()
                    naming_service.register_shape(
                        ocp_shape=face_shape,
                        shape_type=ShapeType.FACE,
                        feature_id=feature_id,
                        local_index=face_idx
                    )
                    face_idx += 1
                    explorer.Next()

                # Alle Edges registrieren
                naming_service.register_solid_edges(result_solid, feature_id)

                if is_enabled("tnp_debug_logging"):
                    logger.success(f"Revolve TNP: {face_idx} Faces registriert")

            except Exception as e:
                logger.error(f"Revolve TNP Registration fehlgeschlagen: {e}")

        logger.info(f"Revolve: {feature.angle}° um {feature.axis}")
        return result_solid

    def _compute_loft(self, feature: 'LoftFeature'):
        """
        OCP-First Loft mit direktem OpenCASCADE BRepOffsetAPI_ThruSections.

        Phase 8: Unterstützt G0/G1/G2 Kontinuität.
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

        # Kontinuitäts-Info
        start_cont = getattr(feature, 'start_continuity', 'G0')
        end_cont = getattr(feature, 'end_continuity', 'G0')

        logger.info(f"Loft mit {len(sections)} Profilen (ruled={feature.ruled}, start={start_cont}, end={end_cont})")

        # OCP-First Loft
        from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.Approx import Approx_ParametrizationType
        from build123d import Solid

        # ThruSections: (isSolid, isRuled)
        is_ruled = feature.ruled
        loft_builder = BRepOffsetAPI_ThruSections(True, is_ruled)

        # Smoothing für G1/G2 Kontinuität
        if not is_ruled and (start_cont != 'G0' or end_cont != 'G0'):
            loft_builder.SetSmoothing(True)
            # Parametrisierung für bessere Kontinuität
            if start_cont == 'G2' or end_cont == 'G2':
                loft_builder.SetParType(Approx_ParametrizationType.Approx_Centripetal)
            else:
                loft_builder.SetParType(Approx_ParametrizationType.Approx_ChordLength)

        # Loft Hardening - Grad und Gewichtung begrenzen
        if is_enabled("loft_sweep_hardening"):
            loft_builder.SetMaxDegree(8)
            try:
                loft_builder.SetCriteriumWeight(0.4, 0.2, 0.4)
            except Exception:
                pass  # Nicht alle OCP-Versionen unterstützen SetCriteriumWeight

        # Profile hinzufügen (Wires extrahieren)
        for i, face in enumerate(sections):
            face_shape = face.wrapped if hasattr(face, 'wrapped') else face

            explorer = TopExp_Explorer(face_shape, TopAbs_EDGE)
            wire_builder = BRepBuilderAPI_MakeWire()

            while explorer.More():
                edge = explorer.Current()
                try:
                    wire_builder.Add(edge)
                except Exception as e:
                    logger.debug(f"Loft Wire-Builder Fehler: {e}")
                explorer.Next()

            if wire_builder.IsDone():
                wire = wire_builder.Wire()
                loft_builder.AddWire(wire)
            else:
                raise ValueError(f"Loft: Face {i+1} hat keinen gültigen Wire")

        # Loft ausführen
        loft_builder.Build()

        if not loft_builder.IsDone():
            raise ValueError("Loft OCP-Operation fehlgeschlagen: IsDone()=False")

        result_shape = loft_builder.Shape()
        result_shape = self._fix_shape_ocp(result_shape)

        # Zu Build123d Solid wrappen
        result = Solid(result_shape)

        if not result.is_valid():
            raise ValueError("Loft erzeugte keinen gültigen Solid")

        # TNP-Registration wenn naming_service verfügbar
        if self._document and hasattr(self._document, '_shape_naming_service'):
            try:
                naming_service = self._document._shape_naming_service
                feature_id = getattr(feature, 'id', None) or str(id(feature))

                # Alle Faces registrieren
                from modeling.tnp_system import ShapeType
                from OCP.TopAbs import TopAbs_FACE

                explorer = TopExp_Explorer(result_shape, TopAbs_FACE)
                face_idx = 0
                while explorer.More():
                    face_shape = explorer.Current()
                    naming_service.register_shape(
                        ocp_shape=face_shape,
                        shape_type=ShapeType.FACE,
                        feature_id=feature_id,
                        local_index=face_idx
                    )
                    face_idx += 1
                    explorer.Next()

                # Alle Edges registrieren
                naming_service.register_solid_edges(result, feature_id)

                if is_enabled("tnp_debug_logging"):
                    logger.success(f"Loft TNP: {face_idx} Faces registriert")

            except Exception as e:
                logger.error(f"Loft TNP Registration fehlgeschlagen: {e}")

        logger.debug(f"OCP Loft erfolgreich ({start_cont}/{end_cont})")
        return result

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
        profile_face = None
        shape_service = None
        if self._document and hasattr(self._document, '_shape_naming_service'):
            shape_service = self._document._shape_naming_service

        profile_data = feature.profile_data if isinstance(feature.profile_data, dict) else {}
        profile_source_solid = current_solid
        profile_body_id = profile_data.get("body_id")
        if profile_body_id and self._document and hasattr(self._document, "find_body_by_id"):
            try:
                profile_body = self._document.find_body_by_id(profile_body_id)
                if profile_body is not None and getattr(profile_body, "_build123d_solid", None) is not None:
                    profile_source_solid = profile_body._build123d_solid
            except Exception as e:
                logger.debug(f"Sweep: Konnte Profil-Body '{profile_body_id}' nicht laden: {e}")

        profile_face_index = getattr(feature, "profile_face_index", None)
        try:
            profile_face_index = int(profile_face_index) if profile_face_index is not None else None
        except Exception:
            profile_face_index = None
        if profile_face_index is not None and profile_face_index < 0:
            profile_face_index = None
        feature.profile_face_index = profile_face_index

        has_profile_shape_ref = feature.profile_shape_id is not None
        has_topological_profile_refs = bool(has_profile_shape_ref or profile_face_index is not None)

        def _is_same_face(face_a, face_b) -> bool:
            if face_a is None or face_b is None:
                return False
            try:
                wa = face_a.wrapped if hasattr(face_a, "wrapped") else face_a
                wb = face_b.wrapped if hasattr(face_b, "wrapped") else face_b
                return wa.IsSame(wb)
            except Exception:
                return face_a is face_b

        def _persist_profile_shape_id(face_obj) -> None:
            if (
                face_obj is None
                or not shape_service
                or feature.profile_shape_id is not None
                or not hasattr(face_obj, "wrapped")
            ):
                return
            try:
                shape_id = shape_service.find_shape_id_by_face(face_obj)
                if shape_id is None:
                    fc = face_obj.center()
                    area = face_obj.area if hasattr(face_obj, "area") else 0.0
                    shape_id = shape_service.register_shape(
                        ocp_shape=face_obj.wrapped,
                        shape_type=ShapeType.FACE,
                        feature_id=feature.id,
                        local_index=max(0, int(profile_face_index) if profile_face_index is not None else 0),
                        geometry_data=(fc.X, fc.Y, fc.Z, area),
                    )
                if shape_id is not None:
                    feature.profile_shape_id = shape_id
            except Exception as e:
                logger.debug(f"Sweep: Konnte Profil-ShapeID nicht persistieren: {e}")

        profile_face_from_index = None
        if profile_source_solid is not None and profile_face_index is not None:
            try:
                from modeling.topology_indexing import face_from_index

                profile_face_from_index = face_from_index(profile_source_solid, profile_face_index)
                if profile_face_from_index is not None:
                    profile_face = profile_face_from_index
                    _persist_profile_shape_id(profile_face_from_index)
                    if is_enabled("tnp_debug_logging"):
                        logger.debug(f"Sweep: Profil via Face-Index aufgelöst (index={profile_face_index})")
            except Exception as e:
                logger.debug(f"Sweep: Profil-Index Auflösung fehlgeschlagen: {e}")

        profile_face_from_shape = None
        if profile_source_solid is not None and has_profile_shape_ref and shape_service:
            try:
                resolved_ocp, method = shape_service.resolve_shape_with_method(
                    feature.profile_shape_id, profile_source_solid
                )
                if resolved_ocp is not None:
                    from build123d import Face
                    from modeling.topology_indexing import face_index_of

                    profile_face_from_shape = Face(resolved_ocp)
                    resolved_idx = face_index_of(profile_source_solid, profile_face_from_shape)
                    if resolved_idx is not None:
                        feature.profile_face_index = int(resolved_idx)
                    if profile_face is None:
                        profile_face = profile_face_from_shape
                    if is_enabled("tnp_debug_logging"):
                        logger.debug(f"Sweep: Profil via ShapeID aufgelöst (method={method})")
            except Exception as e:
                logger.debug(f"Sweep: Profil-ShapeID Auflösung fehlgeschlagen: {e}")

        if has_profile_shape_ref and profile_face_index is not None:
            if profile_face_from_index is None or profile_face_from_shape is None:
                raise ValueError(
                    "Sweep: Profil-Referenz ist inkonsistent "
                    "(profile_shape_id/profile_face_index). Bitte Profil neu auswählen."
                )
            if not _is_same_face(profile_face_from_index, profile_face_from_shape):
                raise ValueError(
                    "Sweep: Profil-Referenz ist inkonsistent "
                    "(profile_shape_id != profile_face_index). Bitte Profil neu auswählen."
                )
            profile_face = profile_face_from_index

        if profile_face is None and has_topological_profile_refs:
            logger.warning(
                "Sweep: TNP-Profilreferenz konnte nicht aufgelöst werden "
                "(profile_shape_id/profile_face_index). Kein Geometric-Fallback."
            )
            raise ValueError("Sweep: Profil-Referenz ist ungültig. Bitte Profil neu auswählen.")

        # TNP v4.0 Fallback: GeometricFaceSelector (nur wenn keine topologischen Refs vorhanden)
        if profile_face is None and profile_source_solid is not None and feature.profile_geometric_selector:
            try:
                from modeling.geometric_selector import GeometricFaceSelector
                from modeling.topology_indexing import face_index_of

                selectors = [feature.profile_geometric_selector]
                if isinstance(feature.profile_geometric_selector, list):
                    selectors = feature.profile_geometric_selector

                all_faces = list(profile_source_solid.faces()) if hasattr(profile_source_solid, 'faces') else []
                for selector_data in selectors:
                    if isinstance(selector_data, dict):
                        geo_sel = GeometricFaceSelector.from_dict(selector_data)
                    elif hasattr(selector_data, 'find_best_match'):
                        geo_sel = selector_data
                    else:
                        continue

                    best_face = geo_sel.find_best_match(all_faces)
                    if best_face is not None:
                        profile_face = best_face
                        feature.profile_face_index = face_index_of(profile_source_solid, profile_face)
                        _persist_profile_shape_id(profile_face)
                        break
            except Exception as e:
                logger.debug(f"Sweep: Profil über GeometricSelector fehlgeschlagen: {e}")

        # Legacy-Fallback: Profil aus gespeicherten Geometriedaten (Sketch-Profil)
        if profile_face is None:
            profile_face = self._profile_data_to_face(feature.profile_data)
        if profile_face is None:
            raise ValueError("Konnte Profil-Face nicht erstellen")

        # Pfad auflösen
        path_wire = self._resolve_path(feature.path_data, current_solid, feature)
        if path_wire is None:
            raise ValueError("Konnte Pfad nicht auflösen")

        # WICHTIG: Profil zum Pfad-Start verschieben
        # Für Sweep muss das Profil am Startpunkt des Pfads liegen!
        profile_face = self._move_profile_to_path_start(profile_face, path_wire, feature)

        # OCP-First Sweep mit Voranalyse für optimale Methode
        # Keine Fallback-Kaskade - entweder OCP erfolgreich oder Fehler
        twist_angle = getattr(feature, 'twist_angle', 0.0)
        scale_start = getattr(feature, 'scale_start', 1.0)
        scale_end = getattr(feature, 'scale_end', 1.0)
        has_twist_or_scale = (twist_angle != 0.0 or scale_start != 1.0 or scale_end != 1.0)

        logger.debug(f"Sweep OCP-First: Frenet={feature.is_frenet}, Twist={twist_angle}°, Scale={scale_start}->{scale_end}")

        # Voranalyse: Pfad-Komplexität bestimmen
        is_curved_path = self._is_curved_path(path_wire)
        has_spine = hasattr(feature, 'spine') and feature.spine is not None

        # OCP-Importe
        from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe, BRepOffsetAPI_MakePipeShell
        from OCP.GeomFill import GeomFill_IsCorrectedFrenet, GeomFill_IsConstantNormal
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeWire
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_EDGE
        from build123d import Solid

        face_shape = profile_face.wrapped if hasattr(profile_face, 'wrapped') else profile_face
        path_shape = path_wire.wrapped if hasattr(path_wire, 'wrapped') else path_wire

        # Validierung: Shape muss OCP-TopoDS_Shape sein
        if path_shape is None:
            raise ValueError("Sweep: Pfad ist None")
        type_name = type(path_shape).__name__
        if 'TopoDS' not in type_name and path_shape.__class__.__module__ != 'OCP.TopoDS':
            raise ValueError(f"Sweep: Pfad ist kein OCP Shape (Typ: {type_name})")

        # Profil-Wire extrahieren (für MakePipeShell)
        # Versuche build123d outer_wire zuerst, dann OCP Fallback
        profile_wire = None
        if hasattr(profile_face, 'outer_wire'):
            try:
                profile_wire = profile_face.outer_wire()
                if hasattr(profile_wire, 'wrapped'):
                    profile_wire = profile_wire.wrapped
            except Exception as e:
                logger.debug(f"Sweep: outer_wire() fehlgeschlagen: {e}")

        # Fallback: OCP Wire-Building aus Edges
        if profile_wire is None:
            explorer = TopExp_Explorer(face_shape, TopAbs_EDGE)
            profile_wire_builder = BRepBuilderAPI_MakeWire()
            while explorer.More():
                try:
                    profile_wire_builder.Add(explorer.Current())
                except Exception:
                    pass
                explorer.Next()

            if not profile_wire_builder.IsDone():
                raise ValueError("Sweep: Profil-Wire Extraktion fehlgeschlagen")
            profile_wire = profile_wire_builder.Wire()

        # OCP-First: Einziger Pfad mit Methoden-Wahl
        result_shape = None

        # Einfacher Pfad → MakePipe (schneller, zuverlässiger)
        if not is_curved_path and not has_twist_or_scale and not feature.is_frenet and not has_spine:
            logger.debug("Sweep: Verwende MakePipe (einfacher Pfad)")
            pipe_op = BRepOffsetAPI_MakePipe(path_shape, face_shape)
            pipe_op.Build()

            if not pipe_op.IsDone():
                raise ValueError("Sweep MakePipe fehlgeschlagen: IsDone()=False")

            result_shape = pipe_op.Shape()

        # Komplexer Pfad oder Twist/Scale → MakePipeShell
        else:
            logger.debug(f"Sweep: Verwende MakePipeShell (curved={is_curved_path}, frenet={feature.is_frenet}, twist/scale={has_twist_or_scale})")
            pipe_shell = BRepOffsetAPI_MakePipeShell(path_shape)

            # Trihedron-Mode setzen
            if feature.is_frenet:
                pipe_shell.SetMode(GeomFill_IsCorrectedFrenet)
            else:
                pipe_shell.SetMode(GeomFill_IsConstantNormal)

            # Advanced: Twist/Scale mit Law-Funktionen
            if has_twist_or_scale:
                try:
                    from OCP.Law import Law_Linear

                    # Scale-Law erstellen
                    if scale_start != 1.0 or scale_end != 1.0:
                        scale_law = Law_Linear()
                        scale_law.Set(0.0, scale_start, 1.0, scale_end)
                        pipe_shell.SetLaw(profile_wire, scale_law, False, False)
                        logger.debug(f"Sweep: Scale-Law {scale_start}->{scale_end} angewendet")
                    else:
                        pipe_shell.Add(profile_wire, False, False)

                    # Twist wird über Approximation realisiert
                    if twist_angle != 0.0:
                        logger.info(f"Sweep: Twist {twist_angle}° wird approximiert")
                        # Vollständige Twist-Implementierung würde Law_Interpol benötigen
                except ImportError:
                    logger.debug("OCP.Law nicht verfügbar, Standard-Add verwenden")
                    pipe_shell.Add(profile_wire, False, False)
            else:
                pipe_shell.Add(profile_wire, False, False)

            pipe_shell.Build()

            if not pipe_shell.IsDone():
                raise ValueError("Sweep MakePipeShell fehlgeschlagen: IsDone()=False")

            try:
                pipe_shell.MakeSolid()
            except Exception:
                pass  # MakeSolid optional für geschlossene Profile

            result_shape = pipe_shell.Shape()

        # Shape-Fix und Validierung
        result_shape = self._fix_shape_ocp(result_shape)
        result = Solid(result_shape)

        if not result.is_valid():
            raise ValueError("Sweep erzeugte keinen gültigen Solid")

        # TNP-Registration wenn naming_service verfügbar
        if self._document and hasattr(self._document, '_shape_naming_service'):
            try:
                naming_service = self._document._shape_naming_service
                feature_id = getattr(feature, 'id', None) or str(id(feature))

                # Alle Faces registrieren
                from modeling.tnp_system import ShapeType
                from OCP.TopExp import TopExp_Explorer
                from OCP.TopAbs import TopAbs_FACE

                explorer = TopExp_Explorer(result_shape, TopAbs_FACE)
                face_idx = 0
                while explorer.More():
                    ocp_face = explorer.Current()
                    fc = self._get_face_center(ocp_face)
                    area = self._get_face_area(ocp_face)
                    naming_service.register_shape(
                        ocp_shape=ocp_face,
                        shape_type=ShapeType.FACE,
                        feature_id=feature_id,
                        local_index=face_idx,
                        geometry_data=(fc.X, fc.Y, fc.Z, area),
                    )
                    face_idx += 1
                    explorer.Next()

                logger.debug(f"Sweep: {face_idx} Faces registriert")
            except Exception as e:
                logger.debug(f"Sweep TNP-Registration fehlgeschlagen: {e}")

        logger.debug("Sweep OCP-First erfolgreich")
        return result

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

    def _is_curved_path(self, path_wire) -> bool:
        """
        Analysiert ob der Pfad gekrümmt ist (nicht gerade).

        Für OCP-First Sweep: Einfache Pfade können MakePipe verwenden,
        gekrümmte Pfade benötigen MakePipeShell.

        Args:
            path_wire: Build123d Wire

        Returns:
            True wenn gekrümmt, False wenn gerade Linie
        """
        try:
            edges = list(path_wire.edges()) if hasattr(path_wire, 'edges') else []
            if len(edges) == 0:
                return False
            if len(edges) == 1:
                # Einzelne Edge prüfen
                edge = edges[0]
                # Gerade Linie hat gleiche Tangentenrichtung an Start/Ende
                try:
                    start_tangent = edge.tangent_at(0) if hasattr(edge, 'tangent_at') else None
                    end_tangent = edge.tangent_at(1) if hasattr(edge, 'tangent_at') else None
                    if start_tangent and end_tangent:
                        # Winkel zwischen Tangenten
                        dot = (start_tangent.X * end_tangent.X +
                                start_tangent.Y * end_tangent.Y +
                                start_tangent.Z * end_tangent.Z)
                        mag1 = (start_tangent.X**2 + start_tangent.Y**2 + start_tangent.Z**2)**0.5
                        mag2 = (end_tangent.X**2 + end_tangent.Y**2 + end_tangent.Z**2)**0.5
                        if mag1 > 0 and mag2 > 0:
                            cos_angle = dot / (mag1 * mag2)
                            # Parallel wenn cos ~ 1
                            return abs(cos_angle - 1.0) > 0.01
                except Exception:
                    pass
                # Kurven-Typ prüfen
                edge_type = edge.geom_type() if hasattr(edge, 'geom_type') else ''
                return edge_type not in ('LINE', 'FORWARD')
            # Multiple Edges: Prüfe ob alle in einer geraden Linie liegen
            vertices = []
            for edge in edges:
                verts = list(edge.vertices()) if hasattr(edge, 'vertices') else []
                vertices.extend([v.center() if hasattr(v, 'center') else v for v in verts])
            if len(vertices) < 3:
                return False
            # Prüfe ob alle Punkte kolinear sind
            v0 = vertices[0]
            v1 = vertices[-1]
            direction = v1 - v0
            dir_length = (direction.X**2 + direction.Y**2 + direction.Z**2)**0.5
            if dir_length < 1e-6:
                return False
            for vi in vertices[1:-1]:
                # Kreuzprodukt sollte Null sein für kolineare Punkte
                vi_v0 = vi - v0
                cross_x = direction.Y * vi_v0.Z - direction.Z * vi_v0.Y
                cross_y = direction.Z * vi_v0.X - direction.X * vi_v0.Z
                cross_z = direction.X * vi_v0.Y - direction.Y * vi_v0.X
                cross_mag = (cross_x**2 + cross_y**2 + cross_z**2)**0.5
                if cross_mag > 0.1:  # > 0.1mm Abweichung = gekrümmt
                    return True
            return False
        except Exception as e:
            logger.debug(f"_is_curved_path Analyse fehlgeschlagen: {e}, assume curved")
            return True  # Conservative: Bei Fehler MakePipeShell verwenden

    def _compute_shell(self, feature: 'ShellFeature', current_solid):
        """
        OCP-First Shell mit direktem OpenCASCADE BRepOffsetAPI_MakeThickSolid.

        Unterstützt:
        - Shell mit Öffnungen (faces_to_remove)
        - Geschlossener Hohlkörper (leere faces_to_remove)
        """
        if current_solid is None:
            raise ValueError("Shell benötigt einen existierenden Körper")

        # Öffnungs-Faces auflösen (TNP v4.0)
        opening_faces = self._resolve_faces_for_shell(current_solid, feature.opening_face_selectors, feature)
        has_opening_refs = bool(
            feature.face_shape_ids
            or feature.face_indices
            or feature.opening_face_selectors
        )
        if has_opening_refs and not opening_faces:
            raise ValueError(
                "Shell: Öffnungs-Faces konnten via TNP v4.0 nicht aufgelöst werden "
                "(ShapeID/face_indices). Kein Geometric-Fallback."
            )

        logger.debug(f"Shell mit Dicke={feature.thickness}mm, {len(opening_faces)} Öffnungen")

        # OCP-First Shell
        from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
        from OCP.TopTools import TopTools_ListOfShape
        from config.tolerances import Tolerances
        from build123d import Solid

        shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid

        # Liste der zu entfernenden Faces
        faces_to_remove = TopTools_ListOfShape()
        for face in opening_faces:
            face_shape = face.wrapped if hasattr(face, 'wrapped') else face
            faces_to_remove.Append(face_shape)

        # Shell erstellen (MakeThickSolidByJoin)
        shell_op = BRepOffsetAPI_MakeThickSolid()
        shell_op.MakeThickSolidByJoin(
            shape,
            faces_to_remove,  # Leer = geschlossener Hohlkörper
            -feature.thickness,  # Negativ für nach innen
            Tolerances.SHELL_TOLERANCE
        )
        shell_op.Build()

        if not shell_op.IsDone():
            raise ValueError(f"Shell OCP-Operation fehlgeschlagen: IsDone()=False")

        result_shape = shell_op.Shape()
        result_shape = self._fix_shape_ocp(result_shape)

        # Zu Build123d Solid wrappen
        result = Solid(result_shape)

        if not result.is_valid():
            raise ValueError("Shell erzeugte keinen gültigen Solid")

        # TNP-Registration wenn naming_service verfügbar
        if self._document and hasattr(self._document, '_shape_naming_service'):
            try:
                naming_service = self._document._shape_naming_service
                feature_id = getattr(feature, 'id', None) or str(id(feature))

                # Alle Faces registrieren
                from modeling.tnp_system import ShapeType
                from OCP.TopExp import TopExp_Explorer
                from OCP.TopAbs import TopAbs_FACE

                explorer = TopExp_Explorer(result_shape, TopAbs_FACE)
                face_idx = 0
                while explorer.More():
                    face_shape = explorer.Current()
                    naming_service.register_shape(
                        ocp_shape=face_shape,
                        shape_type=ShapeType.FACE,
                        feature_id=feature_id,
                        local_index=face_idx
                    )
                    face_idx += 1
                    explorer.Next()

                # Alle Edges registrieren
                naming_service.register_solid_edges(result, feature_id)

                if is_enabled("tnp_debug_logging"):
                    logger.success(f"Shell TNP: {face_idx} Faces registriert")

            except Exception as e:
                logger.error(f"Shell TNP Registration fehlgeschlagen: {e}")

        logger.debug(f"OCP Shell erfolgreich ({len(opening_faces)} Öffnungen)")
        return result

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

        all_edges = current_solid.edges() if hasattr(current_solid, 'edges') else []
        if not all_edges:
            raise ValueError("Solid hat keine Kanten")
        if not feature.edge_shape_ids and not feature.edge_indices and not feature.geometric_selectors:
            raise ValueError("N-Sided Patch benötigt mindestens 3 Kanten-Referenzen")

        resolved_edges = []

        def _is_same_edge(edge_a, edge_b) -> bool:
            try:
                wa = edge_a.wrapped if hasattr(edge_a, 'wrapped') else edge_a
                wb = edge_b.wrapped if hasattr(edge_b, 'wrapped') else edge_b
                return wa.IsSame(wb)
            except Exception:
                return edge_a is edge_b

        def _append_unique(edge_obj) -> None:
            if edge_obj is None:
                return
            for existing in resolved_edges:
                if _is_same_edge(existing, edge_obj):
                    return
            resolved_edges.append(edge_obj)

        # TNP v4.0: Zentraler Resolver (ShapeID / edge_indices / strict Selector-Policy)
        tnp_edges = self._resolve_edges_tnp(current_solid, feature)
        for edge in tnp_edges:
            _append_unique(edge)
        if is_enabled("tnp_debug_logging"):
            logger.debug(
                f"N-Sided Patch: {len(tnp_edges)} Edges via zentralem TNP-Resolver aufgelöst"
            )

        # Für zukünftige Rebuilds ShapeIDs + GeometricSelectors + Edge-Indizes persistieren
        if resolved_edges:
            try:
                resolved_indices = []
                for edge in resolved_edges:
                    for edge_idx, candidate in enumerate(all_edges):
                        if _is_same_edge(candidate, edge):
                            resolved_indices.append(edge_idx)
                            break
                if resolved_indices:
                    feature.edge_indices = resolved_indices
            except Exception as e:
                logger.debug(f"N-Sided Patch: Persistieren von Edge-Indizes fehlgeschlagen: {e}")

        if resolved_edges and self._document and hasattr(self._document, '_shape_naming_service'):
            try:
                from modeling.geometric_selector import GeometricEdgeSelector
                service = self._document._shape_naming_service

                new_shape_ids = []
                new_geo_selectors = []
                for idx, edge in enumerate(resolved_edges):
                    new_geo_selectors.append(GeometricEdgeSelector.from_edge(edge).to_dict())
                    shape_id = service.find_shape_id_by_edge(edge)
                    if shape_id is None and hasattr(edge, 'wrapped'):
                        ec = edge.center()
                        edge_len = edge.length if hasattr(edge, 'length') else 0.0
                        shape_id = service.register_shape(
                            ocp_shape=edge.wrapped,
                            shape_type=ShapeType.EDGE,
                            feature_id=feature.id,
                            local_index=idx,
                            geometry_data=(ec.X, ec.Y, ec.Z, edge_len)
                        )
                    if shape_id is not None:
                        new_shape_ids.append(shape_id)

                if new_shape_ids:
                    feature.edge_shape_ids = new_shape_ids
                if new_geo_selectors:
                    feature.geometric_selectors = new_geo_selectors
            except Exception as e:
                logger.debug(f"N-Sided Patch: Persistieren von ShapeIDs fehlgeschlagen: {e}")

        if len(resolved_edges) < 3:
            expected = (
                len(feature.edge_shape_ids or [])
                or len(feature.edge_indices or [])
                or len(feature.geometric_selectors or [])
            )
            logger.warning(f"Nur {len(resolved_edges)} von {expected} Kanten aufgelöst")
            raise ValueError(f"Nur {len(resolved_edges)} von {expected} Kanten aufgelöst")

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

        # TNP v4.0: Face-Referenzen vor der Shell-Ausführung aktualisieren
        self._update_face_selectors_for_feature(feature, current_solid)

        # Step 1: Create closed shell (reuse shell logic)
        # TNP v4.0: Leite opening_face_shape_ids und selectors durch
        shell_feat = ShellFeature(
            thickness=feature.wall_thickness,
            opening_face_selectors=feature.opening_face_selectors if feature.opening_face_selectors else []
        )
        # Übertrage Opening-ShapeIDs auf ShellFeature.face_shape_ids (TNP v4.0)
        if feature.opening_face_shape_ids:
            shell_feat.face_shape_ids = list(feature.opening_face_shape_ids)
        if feature.opening_face_indices:
            shell_feat.face_indices = list(feature.opening_face_indices)

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
        from build123d import Cylinder, Vector, Align
        import math

        if current_solid is None:
            raise ValueError("Hole: Kein gültiges Eingabe-Solid vorhanden")
        if feature.diameter <= 0:
            raise ValueError(f"Hole: Ungültiger Durchmesser {feature.diameter}mm (muss > 0 sein)")
        if feature.depth < 0:
            raise ValueError(f"Hole: Ungültige Tiefe {feature.depth}mm (muss >= 0 sein)")
        if feature.hole_type not in {"simple", "counterbore", "countersink"}:
            raise ValueError(f"Hole: Unbekannter hole_type '{feature.hole_type}'")
        if feature.hole_type == "counterbore":
            if feature.counterbore_diameter <= feature.diameter:
                raise ValueError(
                    f"Hole: Counterbore-Durchmesser {feature.counterbore_diameter}mm "
                    f"muss größer als Bohrungsdurchmesser {feature.diameter}mm sein"
                )
            if feature.counterbore_depth <= 0:
                raise ValueError(f"Hole: Counterbore-Tiefe {feature.counterbore_depth}mm muss > 0 sein")
        if feature.hole_type == "countersink":
            if feature.countersink_angle <= 0 or feature.countersink_angle >= 179:
                raise ValueError(
                    f"Hole: Countersink-Winkel {feature.countersink_angle}° ist ungültig "
                    "(erwartet: 0 < Winkel < 179)"
                )

        # TNP v4.0: Face-Referenzen auflösen/aktualisieren
        target_faces = self._resolve_feature_faces(feature, current_solid)
        has_face_refs = bool(feature.face_shape_ids or feature.face_indices or feature.face_selectors)
        if has_face_refs and not target_faces:
            raise ValueError(
                "Hole: Ziel-Face konnte via TNP v4.0 nicht aufgelöst werden "
                f"(ShapeIDs={len(feature.face_shape_ids or [])}, "
                f"Indices={len(feature.face_indices or [])}, "
                f"Selectors={len(feature.face_selectors or [])})"
            )

        pos = Vector(*feature.position)
        d = Vector(*feature.direction)
        if target_faces:
            # Falls Richtung ungültig ist, aus Face-Normale ableiten
            try:
                face_center = target_faces[0].center()
                face_normal = target_faces[0].normal_at(face_center)
                if d.length < 1e-9:
                    d = Vector(-face_normal.X, -face_normal.Y, -face_normal.Z)
                if pos.length < 1e-9:
                    pos = Vector(face_center.X, face_center.Y, face_center.Z)
            except Exception:
                pass

        if d.length < 1e-9:
            raise ValueError("Hole: Ungültige Bohrungsrichtung (Nullvektor)")

        d = d.normalized()
        radius = feature.diameter / 2.0

        # Tiefe: 0 = through all (verwende grosse Tiefe)
        depth = feature.depth if feature.depth > 0 else 1000.0

        logger.debug(f"Hole: type={feature.hole_type}, D={feature.diameter}mm, depth={depth}mm at {pos}")

        # === METHODE 1: BRepFeat_MakeCylindricalHole (nur für simple holes) ===
        brepfeat_reason = ""
        if feature.hole_type == "simple":
            try:
                from modeling.brepfeat_operations import brepfeat_cylindrical_hole

                result = brepfeat_cylindrical_hole(
                    base_solid=current_solid,
                    position=(pos.X, pos.Y, pos.Z),
                    direction=(d.X, d.Y, d.Z),
                    diameter=feature.diameter,
                    depth=feature.depth  # 0 = through all
                )

                if result is not None:
                    logger.debug(f"Hole via BRepFeat: D={feature.diameter}mm")
                    return result
                else:
                    brepfeat_reason = "BRepFeat_MakeCylindricalHole lieferte kein Resultat"
                    logger.debug("BRepFeat_MakeCylindricalHole fehlgeschlagen, Fallback auf Boolean")
            except Exception as e:
                brepfeat_reason = f"BRepFeat Fehler: {e}"
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
            if cb_shape is None:
                raise ValueError("Hole: Counterbore-Geometrie konnte nicht positioniert werden")
            hole_shape = hole_shape.fuse(cb_shape)

        # Countersink: Kegel oben
        elif feature.hole_type == "countersink":
            cs_angle_rad = math.radians(feature.countersink_angle / 2.0)
            cs_depth = radius / math.tan(cs_angle_rad) if cs_angle_rad > 0 else 2.0
            from build123d import Cone
            cs_cone = Cone(feature.diameter, 0.01, cs_depth,
                           align=(Align.CENTER, Align.CENTER, Align.MIN))
            cs_shape = self._position_cylinder(cs_cone, pos, d, cs_depth)
            if cs_shape is None:
                raise ValueError("Hole: Countersink-Geometrie konnte nicht positioniert werden")
            hole_shape = hole_shape.fuse(cs_shape)

        # Boolean Cut: Bohrung vom Koerper abziehen
        result = current_solid.cut(hole_shape)
        if result and hasattr(result, 'is_valid') and result.is_valid():
            logger.debug(f"Hole {feature.hole_type} D={feature.diameter}mm erfolgreich")
            return result

        detail = brepfeat_reason if brepfeat_reason else "Boolean-Cut war ungültig oder leer"
        raise ValueError(f"Hole Boolean Cut fehlgeschlagen ({detail})")

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
        TNP v4.0: Face-Selektion erfolgt über face_shape_ids (ShapeNamingService).
        """
        import math
        from OCP.BRepOffsetAPI import BRepOffsetAPI_DraftAngle
        from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS

        shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid

        if current_solid is None:
            raise ValueError("Draft: Kein gültiges Eingabe-Solid vorhanden")
        if abs(feature.draft_angle) >= 89.9:
            raise ValueError(
                f"Draft: Ungültiger Winkel {feature.draft_angle}°. "
                "Erwartet |Winkel| < 89.9°"
            )
        if len(feature.pull_direction) < 3:
            raise ValueError("Draft: Pull-Richtung ist unvollständig")
        px, py, pz = feature.pull_direction[0], feature.pull_direction[1], feature.pull_direction[2]
        if (px * px + py * py + pz * pz) <= 1e-12:
            raise ValueError("Draft: Ungültige Pull-Richtung (Nullvektor)")

        pull_dir = gp_Dir(px, py, pz)
        angle_rad = math.radians(feature.draft_angle)

        # Neutrale Ebene (Basis der Entformung)
        neutral_plane = gp_Pln(gp_Pnt(0, 0, 0), pull_dir)

        target_faces = self._resolve_feature_faces(feature, current_solid)
        has_face_refs = bool(feature.face_shape_ids or feature.face_indices or feature.face_selectors)

        if has_face_refs and not target_faces:
            raise ValueError("Draft: Ziel-Faces konnten via TNP v4.0 nicht aufgelöst werden")

        draft_op = BRepOffsetAPI_DraftAngle(shape)
        face_count = 0
        add_errors = []

        if target_faces:
            for face_idx, target_face in enumerate(target_faces):
                try:
                    topo_face = target_face.wrapped if hasattr(target_face, 'wrapped') else target_face
                    draft_op.Add(TopoDS.Face_s(topo_face), pull_dir, angle_rad, neutral_plane)
                    face_count += 1
                except Exception as e:
                    add_errors.append(f"Face[{face_idx}] konnte nicht hinzugefügt werden: {e}")
        else:
            # Kein explizites Face-Target -> alle Faces draften (Legacy-Verhalten)
            explorer = TopExp_Explorer(shape, TopAbs_FACE)
            all_face_idx = 0
            while explorer.More():
                face = TopoDS.Face_s(explorer.Current())
                try:
                    draft_op.Add(face, pull_dir, angle_rad, neutral_plane)
                    face_count += 1
                except Exception as e:
                    add_errors.append(f"Face[{all_face_idx}] konnte nicht hinzugefügt werden: {e}")
                explorer.Next()
                all_face_idx += 1

        if face_count == 0:
            detail = add_errors[0] if add_errors else "kein kompatibles Ziel-Face gefunden"
            raise ValueError(f"Draft: Keine Flächen konnten gedraftet werden ({detail})")

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
        import numpy as np

        shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid

        # TNP v4.0: Face-Referenz auflösen (ShapeID -> Index -> Selector).
        target_faces = self._resolve_feature_faces(feature, current_solid)
        has_face_refs = bool(
            getattr(feature, "face_shape_id", None) is not None
            or getattr(feature, "face_index", None) is not None
            or getattr(feature, "face_selector", None)
        )
        if has_face_refs and not target_faces:
            raise ValueError("Thread: Ziel-Face konnte via TNP v4.0 nicht aufgelöst werden")

        pos = np.array(feature.position, dtype=float)
        direction = np.array(feature.direction, dtype=float)

        if target_faces:
            target_face = target_faces[0]
            try:
                from OCP.BRepAdaptor import BRepAdaptor_Surface
                from OCP.GeomAbs import GeomAbs_Cylinder

                topo_face = target_face.wrapped if hasattr(target_face, "wrapped") else target_face
                adaptor = BRepAdaptor_Surface(topo_face)
                if adaptor.GetType() != GeomAbs_Cylinder:
                    raise ValueError("ausgewähltes Face ist nicht zylindrisch")

                cyl = adaptor.Cylinder()
                axis = cyl.Axis()
                axis_loc = axis.Location()
                axis_dir = axis.Direction()

                resolved_axis = np.array([axis_dir.X(), axis_dir.Y(), axis_dir.Z()], dtype=float)
                resolved_axis = resolved_axis / (np.linalg.norm(resolved_axis) + 1e-12)
                if np.linalg.norm(direction) > 1e-9 and np.dot(resolved_axis, direction) < 0:
                    resolved_axis = -resolved_axis

                resolved_origin = np.array([axis_loc.X(), axis_loc.Y(), axis_loc.Z()], dtype=float)
                if np.linalg.norm(pos) > 1e-9:
                    pos = resolved_origin + np.dot(pos - resolved_origin, resolved_axis) * resolved_axis
                else:
                    pos = resolved_origin
                direction = resolved_axis
            except Exception as e:
                logger.warning(f"Thread: Face-Referenz nicht als Zylinder nutzbar ({e}); verwende Feature-Parameter")

        if np.linalg.norm(direction) < 1e-9:
            raise ValueError("Thread: Ungültige Gewinderichtung (Nullvektor)")
        direction = direction / (np.linalg.norm(direction) + 1e-12)

        r = max(feature.diameter / 2.0, 1e-6)
        pitch = feature.pitch
        depth = feature.depth
        if pitch <= 1e-9:
            raise ValueError("Thread: Pitch muss > 0 sein")
        if depth <= 0:
            raise ValueError("Thread: Depth muss > 0 sein")
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
        """Echtes Gewinde via Helix + Sweep mit korrekter Profil-Orientierung.

        Das Profil wird senkrecht zum Helix-Tangenten am Startpunkt platziert
        (nicht auf Plane.XZ!). Dadurch entsteht saubere Geometrie mit wenigen
        Faces/Edges → schnelle Tessellation ohne Lag.
        """
        import numpy as np
        from build123d import (Helix, Solid, Polyline, BuildSketch, BuildLine,
                               Plane, make_face, sweep, Vector)
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse

        logger.debug(f"[THREAD] Helix sweep: r={r:.2f}, pitch={pitch}, depth={depth}, "
                     f"type={thread_type}, groove={groove_depth:.3f}")

        # Helix-Radius: Mitte der Gewinderille
        if thread_type == "external":
            helix_r = r - groove_depth / 2
        else:
            helix_r = r + groove_depth / 2

        # 1. Helix-Pfad via build123d
        helix = Helix(
            pitch=pitch,
            height=depth,
            radius=helix_r,
            center=tuple(pos),
            direction=tuple(direction)
        )

        # 2. ISO 60° Dreiecksprofil senkrecht zum Helix-Tangenten am Startpunkt
        half_w = pitch * 0.3

        # Profil-Plane senkrecht zur Helix-Tangente am Startpunkt
        start_pt = helix.position_at(0)
        tangent = helix.tangent_at(0)
        profile_plane = Plane(origin=start_pt, z_dir=tangent)

        with BuildSketch(profile_plane) as profile_sk:
            with BuildLine():
                Polyline(
                    (-groove_depth / 2, -half_w),
                    (groove_depth / 2, 0),
                    (-groove_depth / 2, half_w),
                    close=True
                )
            make_face()

        # 3. Sweep Profil entlang Helix
        thread_solid = sweep(profile_sk.sketch, path=helix)
        thread_ocp = thread_solid.wrapped if hasattr(thread_solid, 'wrapped') else thread_solid

        # 4. Boolean Operation
        if thread_type == "external":
            op = BRepAlgoAPI_Cut(shape, thread_ocp)
        else:
            op = BRepAlgoAPI_Fuse(shape, thread_ocp)

        op.Build()
        if not op.IsDone():
            raise RuntimeError("Thread boolean failed")

        result_shape = self._fix_shape_ocp(op.Shape())
        logger.debug(f"[THREAD] Helix sweep completed successfully")
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

    def _resolve_path(self, path_data: dict, current_solid, feature: Optional['SweepFeature'] = None):
        """
        Löst Pfad-Daten zu Build123d Wire auf.

        Args:
            path_data: Dict mit edge_indices, sketch_id, etc.
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
                from build123d import Wire, Edge

                source_solid = current_solid
                source_body_id = path_data.get("body_id")
                if source_body_id and self._document and hasattr(self._document, "find_body_by_id"):
                    ref_body = self._document.find_body_by_id(source_body_id)
                    if ref_body is not None and getattr(ref_body, "_build123d_solid", None) is not None:
                        source_solid = ref_body._build123d_solid

                all_edges = list(source_solid.edges()) if source_solid and hasattr(source_solid, 'edges') else []
                edge_indices = list(path_data.get("edge_indices") or [])
                has_topological_path_refs = bool(edge_indices)
                if feature and getattr(feature, "path_shape_id", None) is not None:
                    has_topological_path_refs = True
                shape_service = None
                if self._document and hasattr(self._document, '_shape_naming_service'):
                    shape_service = self._document._shape_naming_service

                def _persist_path_shape_id(edge_obj) -> None:
                    if not feature or not shape_service or feature.path_shape_id is not None:
                        return
                    try:
                        shape_id = shape_service.find_shape_id_by_edge(edge_obj)
                        if shape_id is None and hasattr(edge_obj, 'wrapped'):
                            ec = edge_obj.center()
                            edge_len = edge_obj.length if hasattr(edge_obj, 'length') else 0.0
                            shape_id = shape_service.register_shape(
                                ocp_shape=edge_obj.wrapped,
                                shape_type=ShapeType.EDGE,
                                feature_id=feature.id,
                                local_index=0,
                                geometry_data=(ec.X, ec.Y, ec.Z, edge_len)
                            )
                        if shape_id is not None:
                            feature.path_shape_id = shape_id
                    except Exception as e:
                        logger.debug(f"Sweep: Konnte Path-ShapeID nicht persistieren: {e}")

                resolved_index_edges = []
                if edge_indices and all_edges:
                    try:
                        from modeling.topology_indexing import edge_from_index
                        for edge_idx in edge_indices:
                            resolved = edge_from_index(source_solid, int(edge_idx))
                            if resolved is not None:
                                resolved_index_edges.append(resolved)
                    except Exception as e:
                        logger.debug(f"Sweep: Topology-Index-Pfadauflösung fehlgeschlagen: {e}")

                resolved_shape_edge = None
                if feature and feature.path_shape_id and shape_service:
                    try:
                        resolved_ocp, method = shape_service.resolve_shape_with_method(
                            feature.path_shape_id, source_solid
                        )
                        if resolved_ocp is not None:
                            if all_edges:
                                resolved_shape_edge = self._find_matching_edge_in_solid(
                                    resolved_ocp, all_edges, tolerance=0.1
                                )
                            if resolved_shape_edge is None:
                                resolved_shape_edge = Edge(resolved_ocp)
                            if is_enabled("tnp_debug_logging"):
                                logger.debug(f"Sweep: Path via ShapeID aufgelöst (method={method})")
                    except Exception as e:
                        logger.debug(f"Sweep: Path-ShapeID Auflösung fehlgeschlagen: {e}")

                strict_path_mismatch = False
                if edge_indices and feature and getattr(feature, "path_shape_id", None) is not None:
                    if not resolved_index_edges or resolved_shape_edge is None:
                        strict_path_mismatch = True
                    else:
                        strict_path_mismatch = not any(
                            self._is_same_edge(idx_edge, resolved_shape_edge)
                            for idx_edge in resolved_index_edges
                        )

                if strict_path_mismatch:
                    logger.warning(
                        "Sweep: TNP-Pfadreferenz ist inkonsistent "
                        "(path_shape_id != path_data.edge_indices). Kein Geometric-Fallback."
                    )
                    return None

                if resolved_index_edges:
                    _persist_path_shape_id(resolved_index_edges[0])
                    return Wire(resolved_index_edges)

                if resolved_shape_edge is not None:
                    return Wire([resolved_shape_edge])

                # Wenn explizite TNP-Referenzen vorhanden sind, kein stilles Recovery über Legacy/Session-Pfade.
                if has_topological_path_refs:
                    logger.warning(
                        "Sweep: TNP-Pfadreferenz konnte nicht aufgelöst werden "
                        "(ShapeID/edge_indices). Kein Geometric-Fallback."
                    )
                    return None

                # TNP v4.0 Fallback: GeometricEdgeSelector (Feature-Feld oder path_data)
                path_geo_selector = getattr(feature, 'path_geometric_selector', None) if feature else None
                if path_geo_selector is None:
                    path_geo_selector = path_data.get('path_geometric_selector')
                if path_geo_selector and all_edges:
                    try:
                        from modeling.geometric_selector import GeometricEdgeSelector
                        if isinstance(path_geo_selector, dict):
                            geo_sel = GeometricEdgeSelector.from_dict(path_geo_selector)
                        else:
                            geo_sel = path_geo_selector

                        best_edge = geo_sel.find_best_match(all_edges)
                        if best_edge is not None:
                            _persist_path_shape_id(best_edge)
                            return Wire([best_edge])
                    except Exception as e:
                        logger.debug(f"Sweep: GeometricEdgeSelector Fallback fehlgeschlagen: {e}")

                # Sekundär: Direkte Build123d Edges (Session-basiert)
                build123d_edges = path_data.get('build123d_edges', [])
                if build123d_edges:
                    _persist_path_shape_id(build123d_edges[0])
                    logger.debug(f"Sweep: Verwende {len(build123d_edges)} direkte Build123d Edge(s)")
                    return Wire(build123d_edges)

                # Sekundär: Direkte Einzel-Edge (Session-basiert)
                direct_edge = path_data.get('edge')
                if direct_edge is not None:
                    _persist_path_shape_id(direct_edge)
                    return Wire([direct_edge])

                if path_data.get("edge_selector") is not None:
                    logger.warning(
                        "Sweep: Legacy path_data.edge_selector wird nicht mehr aufgelöst. "
                        "Bitte Pfad neu auswählen (TNP v4: edge_indices/ShapeID)."
                    )

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

    def _resolve_feature_faces(self, feature, solid):
        """
        TNP v4.0: Löst Face-Referenzen eines Features auf und migriert Legacy-Daten.

        Reihenfolge:
        1. ShapeIDs via ShapeNamingService
        2. Topologie-Indizes via topology_indexing.face_from_index
        3. GeometricFaceSelector-Fallback nur ohne Topologie-Referenzen.
        """
        if solid is None or not hasattr(solid, 'faces'):
            return []

        all_faces = list(solid.faces())
        if not all_faces:
            return []

        from modeling.geometric_selector import GeometricFaceSelector

        # Feature-spezifische Felder bestimmen
        single_shape_attr = None
        single_index_attr = None
        single_selector_attr = None
        if isinstance(feature, HollowFeature):
            shape_attr = "opening_face_shape_ids"
            index_attr = "opening_face_indices"
            selector_attr = "opening_face_selectors"
        elif isinstance(feature, ShellFeature):
            shape_attr = "face_shape_ids"
            index_attr = "face_indices"
            selector_attr = "opening_face_selectors"
        elif isinstance(feature, (ThreadFeature, ExtrudeFeature)):
            # Thread/Push-Pull nutzen singuläre Face-Referenzen.
            shape_attr = None
            index_attr = None
            selector_attr = None
            single_shape_attr = "face_shape_id"
            single_index_attr = "face_index"
            single_selector_attr = "face_selector"
        else:
            shape_attr = "face_shape_ids"
            index_attr = "face_indices"
            selector_attr = "face_selectors"

        if single_shape_attr:
            single_shape = getattr(feature, single_shape_attr, None)
            single_index = getattr(feature, single_index_attr, None)
            single_selector = getattr(feature, single_selector_attr, None)

            shape_ids = [single_shape] if single_shape is not None else []
            face_indices = [single_index] if single_index is not None else []
            selectors = [single_selector] if single_selector else []
        else:
            shape_ids = list(getattr(feature, shape_attr, []) or [])
            face_indices = list(getattr(feature, index_attr, []) or [])
            selectors = list(getattr(feature, selector_attr, []) or [])
        if not shape_ids and not face_indices and not selectors:
            return []

        service = None
        if self._document and hasattr(self._document, '_shape_naming_service'):
            service = self._document._shape_naming_service

        resolved_faces = []
        resolved_shape_ids = []
        resolved_selector_indices = set()
        resolved_face_indices = []
        resolved_faces_from_shape = []
        resolved_faces_from_index = []

        strict_face_feature = isinstance(
            feature,
            (
                ExtrudeFeature,
                ThreadFeature,
                HoleFeature,
                DraftFeature,
                ShellFeature,
                HollowFeature,
            ),
        )

        def _same_face(face_a, face_b) -> bool:
            try:
                wa = face_a.wrapped if hasattr(face_a, 'wrapped') else face_a
                wb = face_b.wrapped if hasattr(face_b, 'wrapped') else face_b
                return wa.IsSame(wb)
            except Exception:
                return face_a is face_b

        def _face_index(face_obj):
            for face_idx, candidate in enumerate(all_faces):
                if _same_face(candidate, face_obj):
                    return face_idx
            return None

        def _append_source_face(collection, face_obj) -> None:
            for existing in collection:
                if _same_face(existing, face_obj):
                    return
            collection.append(face_obj)

        def _append_face(face_obj, shape_id=None, selector_index=None, topo_index=None, source=None) -> None:
            if face_obj is None:
                return
            for existing in resolved_faces:
                if _same_face(existing, face_obj):
                    if source == "shape":
                        _append_source_face(resolved_faces_from_shape, existing)
                    elif source == "index":
                        _append_source_face(resolved_faces_from_index, existing)
                    return
            resolved_faces.append(face_obj)
            if source == "shape":
                _append_source_face(resolved_faces_from_shape, face_obj)
            elif source == "index":
                _append_source_face(resolved_faces_from_index, face_obj)
            if shape_id is not None:
                resolved_shape_ids.append(shape_id)
            if selector_index is not None:
                resolved_selector_indices.add(selector_index)
            if topo_index is None:
                topo_index = _face_index(face_obj)
            if topo_index is not None:
                try:
                    topo_index = int(topo_index)
                    if topo_index >= 0 and topo_index not in resolved_face_indices:
                        resolved_face_indices.append(topo_index)
                except Exception:
                    pass

        valid_face_indices = []
        for raw_idx in face_indices:
            try:
                face_idx = int(raw_idx)
            except Exception:
                continue
            if face_idx >= 0 and face_idx not in valid_face_indices:
                valid_face_indices.append(face_idx)

        def _resolve_by_indices() -> None:
            if not valid_face_indices:
                return
            try:
                from modeling.topology_indexing import face_from_index

                for face_idx in valid_face_indices:
                    resolved_face = face_from_index(solid, face_idx)
                    _append_face(resolved_face, topo_index=face_idx, source="index")
            except Exception as e:
                logger.debug(f"{feature.name}: Face-Index Auflösung fehlgeschlagen: {e}")

        def _resolve_by_shape_ids() -> None:
            if not service:
                return
            for idx, shape_id in enumerate(shape_ids):
                if not hasattr(shape_id, 'uuid'):
                    continue
                try:
                    resolved_ocp, method = service.resolve_shape_with_method(
                        shape_id,
                        solid,
                        log_unresolved=False,
                    )
                    if resolved_ocp is None:
                        continue
                    from build123d import Face
                    resolved_face = Face(resolved_ocp)
                    _append_face(
                        resolved_face,
                        shape_id=shape_id,
                        selector_index=idx,
                        source="shape",
                    )
                    if is_enabled("tnp_debug_logging"):
                        logger.debug(
                            f"{feature.name}: Face via ShapeID aufgelöst "
                            f"(method={method})"
                        )
                except Exception as e:
                    logger.debug(f"{feature.name}: Face-ShapeID Auflösung fehlgeschlagen: {e}")

        expected_shape_refs = sum(1 for sid in shape_ids if hasattr(sid, "uuid"))
        single_ref_pair = bool(
            single_shape_attr
            and expected_shape_refs == 1
            and len(valid_face_indices) == 1
        )
        shape_ids_index_aligned = True
        if expected_shape_refs > 0 and valid_face_indices and not single_ref_pair:
            for sid in shape_ids:
                if not hasattr(sid, "uuid"):
                    continue
                local_idx = getattr(sid, "local_index", None)
                if not isinstance(local_idx, int) or not (0 <= int(local_idx) < len(valid_face_indices)):
                    shape_ids_index_aligned = False
                    break
        strict_dual_face_refs = (
            strict_face_feature
            and expected_shape_refs > 0
            and bool(valid_face_indices)
            and len(valid_face_indices) == expected_shape_refs
            and (shape_ids_index_aligned or single_ref_pair)
        )
        prefer_shape_first = bool(
            single_shape_attr
            and expected_shape_refs > 0
            and (not valid_face_indices or shape_ids_index_aligned or single_ref_pair)
        )

        # TNP v4.0:
        # - Extrude/Thread (single-face): shape-first für semantische Stabilität.
        # - Alle anderen: index-first, um Topologie-Indizes als Primärreferenz zu nutzen.
        if prefer_shape_first:
            _resolve_by_shape_ids()
            if strict_dual_face_refs or (len(resolved_shape_ids) < expected_shape_refs and valid_face_indices):
                _resolve_by_indices()
        elif valid_face_indices:
            _resolve_by_indices()
            indices_complete = len(resolved_face_indices) >= len(valid_face_indices)
            if strict_dual_face_refs or not indices_complete:
                _resolve_by_shape_ids()
        else:
            _resolve_by_shape_ids()
            _resolve_by_indices()

        strict_topology_mismatch = False
        if strict_dual_face_refs:
            if (
                len(resolved_faces_from_index) < len(valid_face_indices)
                or len(resolved_faces_from_shape) < expected_shape_refs
            ):
                strict_topology_mismatch = True
            else:
                for idx_face in resolved_faces_from_index:
                    if not any(_same_face(idx_face, shape_face) for shape_face in resolved_faces_from_shape):
                        strict_topology_mismatch = True
                        break
                if not strict_topology_mismatch:
                    for shape_face in resolved_faces_from_shape:
                        if not any(_same_face(shape_face, idx_face) for idx_face in resolved_faces_from_index):
                            strict_topology_mismatch = True
                            break

        has_topological_refs = bool(valid_face_indices or expected_shape_refs > 0)
        unresolved_topology_refs = (
            (valid_face_indices and len(resolved_face_indices) < len(valid_face_indices))
            or (
                expected_shape_refs > 0
                and not valid_face_indices
                and len(resolved_shape_ids) < expected_shape_refs
            )
        )
        if strict_dual_face_refs and strict_topology_mismatch:
            unresolved_topology_refs = True
        # Strict für single-face Referenzen: wenn ShapeID vorhanden aber nicht
        # auflösbar, nicht still auf potentiell falschen Index degradieren.
        if prefer_shape_first and expected_shape_refs > 0 and len(resolved_shape_ids) < expected_shape_refs:
            unresolved_topology_refs = True

        if has_topological_refs and unresolved_topology_refs:
            mismatch_hint = " (ShapeID/Index-Mismatch)" if strict_topology_mismatch else ""
            logger.warning(
                f"{feature.name}: Face-Referenz ist ungültig (ShapeID/face_indices). "
                f"Kein Geometric-Fallback.{mismatch_hint}"
            )
            return []

        need_selector_recovery = (not has_topological_refs) and (not resolved_faces)

        # 3) Geometric selector fallback (nur Recovery)
        if need_selector_recovery:
            for idx, selector_data in enumerate(selectors):
                if idx in resolved_selector_indices:
                    continue

                try:
                    if isinstance(selector_data, dict):
                        geo_sel = GeometricFaceSelector.from_dict(selector_data)
                    elif hasattr(selector_data, 'find_best_match'):
                        geo_sel = selector_data
                    else:
                        continue
                except Exception:
                    continue

                best_face = geo_sel.find_best_match(all_faces)
                if best_face is None:
                    continue

                shape_id = None
                if service:
                    try:
                        shape_id = service.find_shape_id_by_face(best_face)
                        if shape_id is None and hasattr(best_face, 'wrapped'):
                            fc = best_face.center()
                            area = best_face.area if hasattr(best_face, 'area') else 0.0
                            shape_id = service.register_shape(
                                ocp_shape=best_face.wrapped,
                                shape_type=ShapeType.FACE,
                                feature_id=feature.id,
                                local_index=idx,
                                geometry_data=(fc.X, fc.Y, fc.Z, area)
                            )
                    except Exception as e:
                        logger.debug(f"{feature.name}: Face-ShapeID Registrierung fehlgeschlagen: {e}")

                _append_face(best_face, shape_id=shape_id, selector_index=idx)

        if not resolved_faces:
            return []

        # Persistiere aktualisierte Referenzen zurück ins Feature
        try:
            updated_selectors = [
                GeometricFaceSelector.from_face(face).to_dict()
                for face in resolved_faces
            ]
            # Nicht-topologische Zusatzdaten (z. B. cell_ids fürs Overlay) beibehalten.
            for idx, updated in enumerate(updated_selectors):
                if idx >= len(selectors):
                    continue
                original = selectors[idx]
                if not isinstance(original, dict):
                    continue
                for key, value in original.items():
                    if key not in updated:
                        updated[key] = value
            if single_selector_attr:
                setattr(feature, single_selector_attr, updated_selectors[0] if updated_selectors else None)
            else:
                setattr(feature, selector_attr, updated_selectors)
        except Exception as e:
            logger.debug(f"{feature.name}: Selector-Update fehlgeschlagen: {e}")

        if single_shape_attr:
            if resolved_shape_ids:
                setattr(feature, single_shape_attr, resolved_shape_ids[0])
        elif resolved_shape_ids:
            setattr(feature, shape_attr, resolved_shape_ids)

        if single_index_attr:
            if resolved_face_indices:
                setattr(feature, single_index_attr, resolved_face_indices[0])
        elif resolved_face_indices:
            setattr(feature, index_attr, resolved_face_indices)

        return resolved_faces

    def _resolve_faces_for_shell(self, solid, face_selectors: List[dict],
                                feature: 'ShellFeature' = None):
        """
        Löst Face-Selektoren für Shell-Öffnungen auf.
        TNP v4.0: ShapeID-first, GeometricSelector als Fallback.
        """
        if solid is None:
            return []

        if feature is None:
            temp_feature = ShellFeature(opening_face_selectors=face_selectors or [])
            return self._resolve_feature_faces(temp_feature, solid)

        if face_selectors and not getattr(feature, "opening_face_selectors", None):
            feature.opening_face_selectors = list(face_selectors)

        return self._resolve_feature_faces(feature, solid)

    def _update_edge_selectors_after_operation(self, solid, current_feature_index: int = -1):
        """
        Aktualisiert Edge-Selektoren in Fillet/Chamfer Features nach Geometrie-Operation.

        Nach Push/Pull oder Boolean ändern sich Edge-Positionen. Diese Methode
        findet die neuen Edges und aktualisiert die gespeicherten GeometricEdgeSelectors.

        Bei großen Parameter-Änderungen (z.B. Extrude 200→100mm) wird automatisch
        adaptive Toleranz verwendet wenn Standard-Matching (10mm) fehlschlägt.

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

        adaptive_tolerance = None  # Lazy-computed bei Bedarf

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

            edge_shape_ids = getattr(feature, 'edge_shape_ids', [])

            new_selectors = []
            for idx, selector in enumerate(geometric_selectors):
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

                    # Rebuild-Fallback: Adaptive Toleranz bei Parameter-Änderungen
                    if best_edge is None:
                        if adaptive_tolerance is None:
                            adaptive_tolerance = self._compute_adaptive_edge_tolerance(solid)

                        if adaptive_tolerance > geo_sel.tolerance:
                            adaptive_sel = GeometricEdgeSelector(
                                center=geo_sel.center,
                                direction=geo_sel.direction,
                                length=geo_sel.length,
                                curve_type=geo_sel.curve_type,
                                tolerance=adaptive_tolerance
                            )
                            best_edge = adaptive_sel.find_best_match(all_edges)
                            if best_edge is not None:
                                logger.debug(f"Edge via adaptive Toleranz ({adaptive_tolerance:.1f}mm) gefunden")

                    if best_edge is not None:
                        # Erstelle neuen Selector mit aktualisierten Werten
                        new_selector = GeometricEdgeSelector.from_edge(best_edge)
                        new_selectors.append(new_selector)
                        updated_count += 1

                        # TNP v4.0: ShapeNamingService Record aktualisieren
                        if idx < len(edge_shape_ids):
                            self._update_shape_naming_record(edge_shape_ids[idx], best_edge)

                        # TNP v4.0: Topology-Index aktualisieren
                        try:
                            edge_indices = getattr(feature, "edge_indices", None)
                            if edge_indices is not None and idx < len(edge_indices):
                                for edge_idx, candidate in enumerate(all_edges):
                                    if self._is_same_edge(candidate, best_edge):
                                        edge_indices[idx] = edge_idx
                                        break
                        except Exception:
                            pass
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

        if updated_count > 0:
            logger.info(f"Aktualisiert {updated_count} Edge-Selektoren nach Geometrie-Operation")

    def _update_edge_selectors_for_feature(self, feature, solid):
        """
        Aktualisiert Edge-Selektoren eines SPEZIFISCHEN Features vor Ausführung.

        TNP-CRITICAL: Diese Methode muss BEVOR Fillet/Chamfer ausgeführt werden,
        weil das Solid sich durch vorherige Features verändert haben kann.

        Bei Parameter-Änderungen (z.B. Extrude 200→100mm) können Edge-Center um
        mehr als die Standard-Toleranz (10mm) wandern. In diesem Fall wird ein
        adaptiver Fallback verwendet, der die Toleranz an die Solid-Größe anpasst.

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

        edge_shape_ids = getattr(feature, 'edge_shape_ids', [])
        adaptive_tolerance = None  # Lazy-computed bei Bedarf

        updated_count = 0
        new_selectors = []

        for idx, selector in enumerate(geometric_selectors):
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

                # Rebuild-Fallback: Adaptive Toleranz bei Parameter-Änderungen
                # Wenn Standard-Matching (10mm) fehlschlägt, Toleranz an Solid-Größe anpassen
                if best_edge is None:
                    if adaptive_tolerance is None:
                        adaptive_tolerance = self._compute_adaptive_edge_tolerance(solid)

                    if adaptive_tolerance > geo_sel.tolerance:
                        adaptive_sel = GeometricEdgeSelector(
                            center=geo_sel.center,
                            direction=geo_sel.direction,
                            length=geo_sel.length,
                            curve_type=geo_sel.curve_type,
                            tolerance=adaptive_tolerance
                        )
                        best_edge = adaptive_sel.find_best_match(all_edges)
                        if best_edge is not None:
                            logger.debug(f"Edge via adaptive Toleranz ({adaptive_tolerance:.1f}mm) gefunden")

                if best_edge is not None:
                    # Erstelle neuen Selector mit aktualisierten Werten
                    new_selector = GeometricEdgeSelector.from_edge(best_edge)
                    new_selectors.append(new_selector)
                    updated_count += 1

                    # TNP v4.0: ShapeNamingService Record aktualisieren
                    if idx < len(edge_shape_ids):
                        self._update_shape_naming_record(edge_shape_ids[idx], best_edge)

                    # TNP v4.0: Topology-Index aktualisieren
                    try:
                        edge_indices = getattr(feature, "edge_indices", None)
                        if edge_indices is not None and idx < len(edge_indices):
                            for edge_idx, candidate in enumerate(all_edges):
                                if self._is_same_edge(candidate, best_edge):
                                    edge_indices[idx] = edge_idx
                                    break
                    except Exception:
                        pass
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

    def _compute_adaptive_edge_tolerance(self, solid) -> float:
        """
        Berechnet adaptive Toleranz für Edge-Matching basierend auf Solid-Größe.

        BESSER LÖSUNG: Statt das adaptive Toleranz-Ansatz zu verwenden, verlassen wir uns
        auf verbessertes TNP-Tracking (face_id-basierte Gruppierung, .wrapped Fix, etc.).

        Die adaptive Toleranz wird nur als letzten Fallback verwendet und ist STRENG begrenzt
        um falsche Edge-Matches zu vermeiden.

        Max: 15mm (statt 50mm) - verhindert dass völlig falsche Edges gematcht werden.
        """
        try:
            bbox = solid.bounding_box()
            max_dim = max(
                bbox.max.X - bbox.min.X,
                bbox.max.Y - bbox.min.Y,
                bbox.max.Z - bbox.min.Z
            )
            # Adaptive Toleranz = 5% der größten Dimension, min 5mm, max 15mm
            # (früher: 10% max 50mm - zu groß für präzise Fillets!)
            tolerance = max_dim / 20.0
            return max(5.0, min(tolerance, 15.0))
        except Exception:
            return 10.0

    def _update_shape_naming_record(self, shape_id, edge) -> None:
        """
        Aktualisiert einen ShapeNamingService Record mit neuer Edge-Geometrie.

        Wird aufgerufen wenn ein Edge-Selector nach Parameter-Änderung eine neue
        passende Edge gefunden hat. Aktualisiert ocp_shape, geometric_signature
        und spatial_index, damit _resolve_edges_tnp die Edge ebenfalls findet.
        """
        if not self._document or not hasattr(self._document, '_shape_naming_service'):
            return

        try:
            service = self._document._shape_naming_service

            if not hasattr(shape_id, 'uuid') or shape_id.uuid not in service._shapes:
                return

            record = service._shapes[shape_id.uuid]

            # OCP Shape aktualisieren
            record.ocp_shape = edge.wrapped
            record.is_valid = True

            # Geometric Signature neu berechnen
            old_sig = record.geometric_signature.copy() if record.geometric_signature else {}
            record.geometric_signature = record.compute_signature()

            # Spatial Index aktualisieren
            shape_type = record.shape_id.shape_type
            if 'center' in record.geometric_signature:
                import numpy as np
                new_center = np.array(record.geometric_signature['center'])

                # Alten Eintrag entfernen
                service._spatial_index[shape_type] = [
                    (pos, sid) for pos, sid in service._spatial_index[shape_type]
                    if sid.uuid != shape_id.uuid
                ]
                # Neuen Eintrag hinzufügen
                service._spatial_index[shape_type].append((new_center, record.shape_id))

            if is_enabled("tnp_debug_logging"):
                logger.debug(f"TNP Record {shape_id.uuid[:8]} aktualisiert nach Parameter-Änderung")

        except Exception as e:
            logger.debug(f"Shape Naming Record Update fehlgeschlagen: {e}")

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

    def _register_base_feature_edges(self, feature, solid) -> None:
        """
        TNP v4.0: Registriert alle Edges eines neu erzeugten Solids fuer Basis-Features
        (Loft, Revolve, Sweep, Primitive, Import). Nur einmal pro Feature-ID.
        """
        if not self._document or not hasattr(self._document, '_shape_naming_service'):
            return
        if not solid or not hasattr(solid, 'edges'):
            return

        try:
            service = self._document._shape_naming_service
            if service.get_shapes_by_feature(feature.id):
                return
            service.register_solid_edges(solid, feature.id)
        except Exception as e:
            if is_enabled("tnp_debug_logging"):
                logger.debug(f"TNP v4.0: Base-Feature Registrierung fehlgeschlagen: {e}")

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

    def _update_face_selectors_for_feature(self, feature, solid):
        """
        TNP v4.0: Aktualisiert Face-Referenzen eines Features vor Ausführung.

        Primary: ShapeIDs via ShapeNamingService
        Secondary: Face-Indizes via topology_indexing.face_from_index
        Fallback: GeometricFaceSelector (nur Legacy-Recovery)
        """
        if not solid:
            return

        if not isinstance(
            feature,
            (
                ShellFeature,
                HoleFeature,
                DraftFeature,
                HollowFeature,
                ThreadFeature,
                SurfaceTextureFeature,
                ExtrudeFeature,
            ),
        ):
            return

        resolved_faces = self._resolve_feature_faces(feature, solid)
        if is_enabled("tnp_debug_logging"):
            logger.debug(f"{feature.name}: {len(resolved_faces)} Face-Referenzen aufgelöst (TNP v4.0)")

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

    def _rebuild(self, rebuild_up_to=None, changed_feature_id: str = None, progress_callback=None):
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
        strict_self_heal = is_enabled("self_heal_strict")

        def _solid_metrics(solid_obj) -> dict:
            if solid_obj is None:
                return {
                    "volume": None,
                    "faces": 0,
                    "edges": 0,
                    "bbox_lengths": None,
                    "bbox_center": None,
                    "bbox_diag": None,
                }
            try:
                volume = float(getattr(solid_obj, "volume", 0.0))
            except Exception:
                volume = None
            try:
                faces = len(list(solid_obj.faces()))
            except Exception:
                faces = 0
            try:
                edges = len(list(solid_obj.edges()))
            except Exception:
                edges = 0
            bbox_lengths = None
            bbox_center = None
            bbox_diag = None
            try:
                bb = solid_obj.bounding_box()
                min_x = float(bb.min.X)
                min_y = float(bb.min.Y)
                min_z = float(bb.min.Z)
                max_x = float(bb.max.X)
                max_y = float(bb.max.Y)
                max_z = float(bb.max.Z)
                lx = max_x - min_x
                ly = max_y - min_y
                lz = max_z - min_z
                bbox_lengths = (lx, ly, lz)
                bbox_center = (
                    0.5 * (min_x + max_x),
                    0.5 * (min_y + max_y),
                    0.5 * (min_z + max_z),
                )
                bbox_diag = float((lx * lx + ly * ly + lz * lz) ** 0.5)
            except Exception:
                pass
            return {
                "volume": volume,
                "faces": faces,
                "edges": edges,
                "bbox_lengths": bbox_lengths,
                "bbox_center": bbox_center,
                "bbox_diag": bbox_diag,
            }

        def _format_metrics(metrics: dict) -> str:
            volume = metrics.get("volume")
            if volume is None:
                vol_text = "n/a"
            else:
                vol_text = f"{volume:.3f}"
            diag = metrics.get("bbox_diag")
            diag_text = "n/a" if diag is None else f"{float(diag):.3f}"
            return (
                f"vol={vol_text}mm³, "
                f"faces={metrics.get('faces', 0)}, "
                f"edges={metrics.get('edges', 0)}, "
                f"diag={diag_text}mm"
            )

        def _is_local_modifier_feature(feat) -> bool:
            return isinstance(feat, (ChamferFeature, FilletFeature))

        def _local_modifier_drift_details(feat, before_metrics: dict, after_metrics: dict) -> Optional[dict]:
            if before_metrics is None or after_metrics is None:
                return None

            before_lengths = before_metrics.get("bbox_lengths")
            after_lengths = after_metrics.get("bbox_lengths")
            before_center = before_metrics.get("bbox_center")
            after_center = after_metrics.get("bbox_center")
            before_diag = before_metrics.get("bbox_diag")
            after_diag = after_metrics.get("bbox_diag")
            if (
                before_lengths is None or after_lengths is None
                or before_center is None or after_center is None
                or before_diag is None or after_diag is None
            ):
                return None

            if isinstance(feat, ChamferFeature):
                magnitude = abs(float(getattr(feat, "distance", 0.0) or 0.0))
                op_label = "Chamfer"
            else:
                magnitude = abs(float(getattr(feat, "radius", 0.0) or 0.0))
                op_label = "Fillet"

            max_axis_grow = max(0.25, 0.60 * magnitude)
            max_axis_shrink = max(1.60, 6.50 * magnitude)
            max_diag_grow = max(0.35, 0.95 * magnitude)
            max_diag_shrink = max(2.20, 8.00 * magnitude)
            max_center_shift = max(1.50, 6.00 * magnitude)

            drift_reasons = []
            max_axis_grow_seen = 0.0
            max_axis_shrink_seen = 0.0
            for axis_idx, (before_len, after_len) in enumerate(zip(before_lengths, after_lengths)):
                grow = float(after_len - before_len)
                shrink = float(before_len - after_len)
                max_axis_grow_seen = max(max_axis_grow_seen, grow)
                max_axis_shrink_seen = max(max_axis_shrink_seen, shrink)
                if grow > max_axis_grow:
                    drift_reasons.append(f"axis{axis_idx}_grow={grow:.3f}mm")
                if shrink > max_axis_shrink:
                    drift_reasons.append(f"axis{axis_idx}_shrink={shrink:.3f}mm")

            diag_grow = float(after_diag - before_diag)
            diag_shrink = float(before_diag - after_diag)
            if diag_grow > max_diag_grow:
                drift_reasons.append(f"diag_grow={diag_grow:.3f}mm")
            if diag_shrink > max_diag_shrink:
                drift_reasons.append(f"diag_shrink={diag_shrink:.3f}mm")

            center_shift = float(
                (
                    (after_center[0] - before_center[0]) ** 2
                    + (after_center[1] - before_center[1]) ** 2
                    + (after_center[2] - before_center[2]) ** 2
                ) ** 0.5
            )
            if center_shift > max_center_shift:
                drift_reasons.append(f"center_shift={center_shift:.3f}mm")

            if not drift_reasons:
                return None

            return {
                "feature": op_label,
                "magnitude": magnitude,
                "before": before_metrics,
                "after": after_metrics,
                "limits": {
                    "max_axis_grow": max_axis_grow,
                    "max_axis_shrink": max_axis_shrink,
                    "max_diag_grow": max_diag_grow,
                    "max_diag_shrink": max_diag_shrink,
                    "max_center_shift": max_center_shift,
                },
                "observed": {
                    "max_axis_grow": max_axis_grow_seen,
                    "max_axis_shrink": max_axis_shrink_seen,
                    "diag_grow": diag_grow,
                    "diag_shrink": diag_shrink,
                    "center_shift": center_shift,
                },
                "reasons": drift_reasons,
            }

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

        last_valid_solid = current_solid
        last_valid_feature_index = start_index - 1 if current_solid is not None else -1

        logger.info(f"Rebuilding Body '{self.name}' (Features {start_index}-{max_index-1}/{len(self.features)})...")

        # Reset Cache (Phase 2: Lazy-Loading)
        self.invalidate_mesh()
        self._mesh_vertices.clear()
        self._mesh_triangles.clear()

        # Setze Status für Features VOR start_index (bereits computed)
        for i in range(start_index):
            if i < len(self.features) and not self.features[i].suppressed:
                self.features[i].status = "OK"  # Aus Checkpoint
                self.features[i].status_message = ""
                self.features[i].status_details = {}

        blocked_by_feature_error = False
        blocked_by_feature_name = ""
        blocked_by_feature_index = -1

        for i, feature in enumerate(self.features):
            solid_before_feature = current_solid
            if progress_callback:
                try:
                    progress_callback(i, len(self.features), feature.name)
                except Exception:
                    pass
            if i >= max_index:
                feature.status = "ROLLED_BACK"
                feature.status_message = ""
                feature.status_details = {}
                continue
            if feature.suppressed:
                feature.status = "SUPPRESSED"
                feature.status_message = ""
                feature.status_details = {}
                continue

            # === PHASE 7: Überspringe Features vor start_index (aus Checkpoint) ===
            if use_incremental and i < start_index:
                continue  # Status bereits gesetzt

            if blocked_by_feature_error:
                blocked_msg = (
                    f"Nicht ausgeführt: vorheriges Feature "
                    f"'{blocked_by_feature_name}' (Index {blocked_by_feature_index}) fehlgeschlagen."
                )
                feature.status = "ERROR"
                feature.status_message = blocked_msg
                feature.status_details = self._build_operation_error_details(
                    op_name=f"Blocked_{i}",
                    code="blocked_by_upstream_error",
                    message=blocked_msg,
                    feature=feature,
                )
                continue

            new_solid = None
            status = "OK"
            self._last_operation_error = ""
            self._last_operation_error_details = {}

            # ================= PRIMITIVE (Base Feature) =================
            if isinstance(feature, PrimitiveFeature):
                base_solid = feature.create_solid()
                if base_solid is not None:
                    new_solid = base_solid
                    logger.info(f"PrimitiveFeature: {feature.primitive_type} erstellt")
                    if current_solid is None:
                        self._register_base_feature_edges(feature, new_solid)
                else:
                    status = "ERROR"
                    logger.error(f"PrimitiveFeature: Erstellung fehlgeschlagen")

            # ================= IMPORT (Base Feature) =================
            elif isinstance(feature, ImportFeature):
                # ImportFeature enthält die Basis-Geometrie (z.B. konvertiertes Mesh)
                base_solid = feature.get_solid()
                if base_solid is not None:
                    new_solid = base_solid
                    logger.info(f"ImportFeature: Basis-Geometrie geladen ({base_solid.volume:.2f}mm³)")
                    if current_solid is None:
                        self._register_base_feature_edges(feature, new_solid)
                else:
                    status = "ERROR"
                    logger.error(f"ImportFeature: Konnte BREP nicht laden")

            # ================= EXTRUDE =================
            elif isinstance(feature, ExtrudeFeature):
                # Push/Pull auf Body-Face: BRepFeat für Join/Cut verwenden.
                has_polys = hasattr(feature, 'precalculated_polys') and feature.precalculated_polys

                if has_polys and current_solid is not None and feature.operation in ("Join", "Cut"):
                    # === PUSH/PULL auf Body-Face: Verwende BRepFeat für TNP-Robustheit ===
                    
                    def op_brepfeat():
                        return self._compute_extrude_part_brepfeat(feature, current_solid)
                    
                    brepfeat_result, status = self._safe_operation(
                        f"Extrude_BRepFeat_{i}",
                        op_brepfeat,
                        feature=feature,
                    )
                    
                    if brepfeat_result and status == "SUCCESS":
                        new_solid = brepfeat_result
                        if is_enabled("tnp_debug_logging"):
                            logger.debug(f"TNP BRepFeat: Push/Pull erfolgreich via BRepFeat_MakePrism")
                        
                        if is_enabled("extrude_debug"):
                            logger.debug(f"TNP DEBUG: Starte _update_edge_selectors_after_operation")
                        self._update_edge_selectors_after_operation(new_solid, current_feature_index=i)
                    else:
                        # TNP v4 strict: Bei vorhandenen Primärreferenzen (ShapeID/Index)
                        # KEIN Fallback auf polygon-basiertes Extrude+Boolean, da das
                        # semantisch eine andere Operation ergeben kann.
                        has_primary_face_ref = (
                            getattr(feature, "face_shape_id", None) is not None
                            or getattr(feature, "face_index", None) is not None
                        )
                        if has_primary_face_ref:
                            status = "ERROR"
                            new_solid = current_solid
                            logger.error(
                                "Push/Pull: BRepFeat fehlgeschlagen bei vorhandenen "
                                "TNP-Primärreferenzen (face_shape_id/face_index). "
                                "Kein Boolean-Fallback."
                            )
                        else:
                            # Legacy-Fallback nur ohne TNP-Primärreferenz.
                            has_polys = False
                
                if not has_polys or current_solid is None:
                    # === Normales Extrude (mit Sketch) oder New Body ===
                    def op_extrude():
                        return self._compute_extrude_part(feature)
                    
                    part_geometry, status = self._safe_operation(
                        f"Extrude_{i}",
                        op_extrude,
                        feature=feature,
                    )

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

                                # Nach Boolean-Operation: Edge-Selektoren für nachfolgende Features aktualisieren
                                if new_solid is not None:
                                    if is_enabled("extrude_debug"):
                                        logger.debug(f"TNP DEBUG: Starte _update_edge_selectors_after_operation")
                                    self._update_edge_selectors_after_operation(new_solid, current_feature_index=i)
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

                    # Feature-ID sicherstellen
                    if not hasattr(feature, 'id') or feature.id is None:
                        import uuid
                        feature.id = str(uuid.uuid4())[:8]
                        logger.debug(f"[FILLET] Generated ID for FilletFeature: {feature.id}")

                    def op_fillet(rad=feature.radius):
                        # OCP-First Fillet mit TNP Integration (Phase B)
                        edges_to_fillet = self._resolve_edges_tnp(current_solid, feature)
                        if not edges_to_fillet:
                            raise ValueError("Fillet: Keine Kanten selektiert (TNP resolution failed)")

                        naming_service = None
                        if self._document and hasattr(self._document, '_shape_naming_service'):
                            naming_service = self._document._shape_naming_service

                        if naming_service is None:
                            raise ValueError(
                                "Fillet: TNP ShapeNamingService nicht verfügbar. "
                                "Bitte Document mit TNP Service verwenden."
                            )

                        # EINZIGER PFAD - OCPFilletHelper (kein Fallback!)
                        result = OCPFilletHelper.fillet(
                            solid=current_solid,
                            edges=[e.wrapped if hasattr(e, 'wrapped') else e for e in edges_to_fillet],
                            radius=rad,
                            naming_service=naming_service,
                            feature_id=feature.id
                        )
                        return result

                    # Fail-Fast: Kein Fallback mit reduziertem Radius
                    new_solid, status = self._safe_operation(
                        f"Fillet_{i}",
                        op_fillet,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"
                        logger.error(f"Fillet R={feature.radius}mm fehlgeschlagen. Radius evtl. zu gross fuer die gewaehlten Kanten.")
                    # TNP History wird automatisch vom OCPFilletHelper registriert

            # ================= CHAMFER =================
            elif isinstance(feature, ChamferFeature):
                if current_solid:
                    # TNP-CRITICAL: Aktualisiere Edge-Selektoren BEVOR Chamfer ausgeführt wird
                    # Weil vorherige Features (Extrude, Boolean) das Solid verändert haben
                    self._update_edge_selectors_for_feature(feature, current_solid)

                    # Feature-ID sicherstellen
                    if not hasattr(feature, 'id') or feature.id is None:
                        import uuid
                        feature.id = str(uuid.uuid4())[:8]
                        logger.debug(f"[CHAMFER] Generated ID for ChamferFeature: {feature.id}")

                    def op_chamfer(dist=feature.distance):
                        # OCP-First Chamfer mit TNP Integration (Phase B)
                        edges = self._resolve_edges_tnp(current_solid, feature)
                        if not edges:
                            raise ValueError("Chamfer: Keine Kanten selektiert (TNP resolution failed)")

                        naming_service = None
                        if self._document and hasattr(self._document, '_shape_naming_service'):
                            naming_service = self._document._shape_naming_service

                        if naming_service is None:
                            raise ValueError(
                                "Chamfer: TNP ShapeNamingService nicht verfügbar. "
                                "Bitte Document mit TNP Service verwenden."
                            )

                        # EINZIGER PFAD - OCPChamferHelper (kein Fallback!)
                        result = OCPChamferHelper.chamfer(
                            solid=current_solid,
                            edges=[e.wrapped if hasattr(e, 'wrapped') else e for e in edges],
                            distance=dist,
                            naming_service=naming_service,
                            feature_id=feature.id
                        )
                        return result

                    # Fail-Fast: Kein Fallback mit reduzierter Distance
                    new_solid, status = self._safe_operation(
                        f"Chamfer_{i}",
                        op_chamfer,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"
                        logger.error(f"Chamfer D={feature.distance}mm fehlgeschlagen. Distance evtl. zu gross fuer die gewaehlten Kanten.")
                    # TNP History wird automatisch vom OCPChamferHelper registriert

            # ================= TRANSFORM =================
            elif isinstance(feature, TransformFeature):
                if current_solid:
                    def op_transform():
                        return self._apply_transform_feature(current_solid, feature)

                    new_solid, status = self._safe_operation(
                        f"Transform_{i}",
                        op_transform,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= REVOLVE =================
            elif isinstance(feature, RevolveFeature):
                def op_revolve():
                    return self._compute_revolve(feature)

                part_geometry, status = self._safe_operation(
                    f"Revolve_{i}",
                    op_revolve,
                    feature=feature,
                )

                if part_geometry:
                    if current_solid is None or feature.operation == "New Body":
                        new_solid = part_geometry
                        if current_solid is None:
                            self._register_base_feature_edges(feature, new_solid)
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

                part_geometry, status = self._safe_operation(
                    f"Loft_{i}",
                    op_loft,
                    feature=feature,
                )

                if part_geometry:
                    if current_solid is None or feature.operation == "New Body":
                        new_solid = part_geometry
                        if current_solid is None:
                            self._register_base_feature_edges(feature, new_solid)
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

                part_geometry, status = self._safe_operation(
                    f"Sweep_{i}",
                    op_sweep,
                    feature=feature,
                )

                if part_geometry:
                    if current_solid is None or feature.operation == "New Body":
                        new_solid = part_geometry
                        if current_solid is None:
                            self._register_base_feature_edges(feature, new_solid)
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

                    new_solid, status = self._safe_operation(
                        f"Shell_{i}",
                        op_shell,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= HOLLOW (3D-Druck) =================
            elif isinstance(feature, HollowFeature):
                if current_solid:
                    # TNP v4.0: Opening-Faces vor Hollow aktualisieren
                    self._update_face_selectors_for_feature(feature, current_solid)

                    def op_hollow():
                        return self._compute_hollow(feature, current_solid)

                    new_solid, status = self._safe_operation(
                        f"Hollow_{i}",
                        op_hollow,
                        feature=feature,
                    )
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

                    new_solid, status = self._safe_operation(
                        f"Lattice_{i}",
                        op_lattice,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= N-SIDED PATCH =================
            elif isinstance(feature, NSidedPatchFeature):
                if current_solid:
                    def op_nsided():
                        return self._compute_nsided_patch(feature, current_solid)

                    new_solid, status = self._safe_operation(
                        f"NSidedPatch_{i}",
                        op_nsided,
                        feature=feature,
                    )
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

                    new_solid, status = self._safe_operation(
                        f"Hole_{i}",
                        op_hole,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"
                        if not self._last_operation_error:
                            self._last_operation_error = "Hole-Operation lieferte kein Ergebnis-Solid"
                            self._last_operation_error_details = self._build_operation_error_details(
                                op_name=f"Hole_{i}",
                                code="no_result_solid",
                                message=self._last_operation_error,
                                feature=feature,
                            )

            # ================= DRAFT =================
            elif isinstance(feature, DraftFeature):
                if current_solid:
                    # TNP-CRITICAL: Aktualisiere Face-Selektoren BEVOR Draft ausgeführt wird
                    self._update_face_selectors_for_feature(feature, current_solid)
                    
                    def op_draft():
                        return self._compute_draft(feature, current_solid)

                    new_solid, status = self._safe_operation(
                        f"Draft_{i}",
                        op_draft,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"
                        if not self._last_operation_error:
                            self._last_operation_error = "Draft-Operation lieferte kein Ergebnis-Solid"
                            self._last_operation_error_details = self._build_operation_error_details(
                                op_name=f"Draft_{i}",
                                code="no_result_solid",
                                message=self._last_operation_error,
                                feature=feature,
                            )

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

                    new_solid, status = self._safe_operation(
                        f"Split_{i}",
                        op_split,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= THREAD =================
            elif isinstance(feature, ThreadFeature):
                if current_solid:
                    self._update_face_selectors_for_feature(feature, current_solid)
                if feature.cosmetic and is_enabled("cosmetic_threads"):
                    # Kosmetisch: kein BREP-Update, nur Helix-Linien im Viewport
                    status = "COSMETIC"
                    logger.debug(f"Thread '{feature.name}' — cosmetic, kein BREP-Update")
                elif current_solid:
                    def op_thread():
                        return self._compute_thread(feature, current_solid)

                    new_solid, status = self._safe_operation(
                        f"Thread_{i}",
                        op_thread,
                        feature=feature,
                    )
                    if new_solid is None:
                        new_solid = current_solid
                        status = "ERROR"

            # ================= SURFACE TEXTURE =================
            elif isinstance(feature, SurfaceTextureFeature):
                if current_solid:
                    self._update_face_selectors_for_feature(feature, current_solid)
                # Texturen modifizieren NICHT das BREP — nur Metadaten-Layer.
                # Displacement wird erst beim STL-Export angewendet.
                status = "OK"
                logger.debug(f"SurfaceTexture '{feature.name}' — Metadaten-only, kein BREP-Update")

            if strict_self_heal and status == "WARNING" and self._feature_has_topological_references(feature):
                rollback_from = _solid_metrics(new_solid) if new_solid is not None else _solid_metrics(current_solid)
                rollback_to = _solid_metrics(solid_before_feature)
                status = "ERROR"
                new_solid = solid_before_feature
                self._last_operation_error = (
                    f"Strict Self-Heal: Warning/Fallback bei Topologie-Referenzen blockiert "
                    f"(Feature '{feature.name}')."
                )
                self._last_operation_error_details = self._build_operation_error_details(
                    op_name=f"StrictSelfHeal_{i}",
                    code="self_heal_blocked_topology_warning",
                    message=self._last_operation_error,
                    feature=feature,
                    hint="Feature-Referenzen neu auswählen oder Parameter reduzieren.",
                )
                self._last_operation_error_details["rollback"] = {
                    "from": rollback_from,
                    "to": rollback_to,
                }
                logger.error(self._last_operation_error)
                logger.error(
                    f"Strict Self-Heal Rollback ({feature.name}): "
                    f"{_format_metrics(rollback_from)} -> {_format_metrics(rollback_to)}"
                )

            if strict_self_heal and new_solid is not None and status != "ERROR":
                step_validation = GeometryValidator.validate_solid(new_solid, ValidationLevel.NORMAL)
                if step_validation.is_error:
                    rollback_from = _solid_metrics(new_solid)
                    rollback_to = _solid_metrics(solid_before_feature)
                    status = "ERROR"
                    new_solid = solid_before_feature
                    self._last_operation_error = (
                        f"Strict Self-Heal: Feature '{feature.name}' erzeugte ungültige Geometrie "
                        f"({step_validation.message}) – Rollback auf letzten validen Stand."
                    )
                    self._last_operation_error_details = self._build_operation_error_details(
                        op_name=f"StrictSelfHeal_{i}",
                        code="self_heal_rollback_invalid_result",
                        message=self._last_operation_error,
                        feature=feature,
                        hint=step_validation.message,
                    )
                    self._last_operation_error_details["rollback"] = {
                        "from": rollback_from,
                        "to": rollback_to,
                    }
                    logger.error(self._last_operation_error)
                    logger.error(
                        f"Strict Self-Heal Rollback ({feature.name}): "
                        f"{_format_metrics(rollback_from)} -> {_format_metrics(rollback_to)}"
                    )

            if (
                strict_self_heal
                and new_solid is not None
                and status != "ERROR"
                and solid_before_feature is not None
                and _is_local_modifier_feature(feature)
            ):
                before_metrics = _solid_metrics(solid_before_feature)
                after_metrics = _solid_metrics(new_solid)
                drift_details = _local_modifier_drift_details(feature, before_metrics, after_metrics)
                if drift_details is not None:
                    status = "ERROR"
                    new_solid = solid_before_feature
                    self._last_operation_error = (
                        f"Strict Self-Heal: Feature '{feature.name}' verworfen "
                        f"(unerwartete globale Geometrie-Drift bei lokalem Modifier)."
                    )
                    self._last_operation_error_details = self._build_operation_error_details(
                        op_name=f"StrictSelfHeal_{i}",
                        code="self_heal_rollback_geometry_drift",
                        message=self._last_operation_error,
                        feature=feature,
                        hint="Chamfer/Fillet hat den Body global verändert. Auswahl/Parameter prüfen.",
                    )
                    self._last_operation_error_details["rollback"] = {
                        "from": after_metrics,
                        "to": before_metrics,
                    }
                    self._last_operation_error_details["geometry_drift"] = drift_details
                    logger.error(self._last_operation_error)
                    logger.error(
                        f"Strict Self-Heal Rollback ({feature.name}, drift): "
                        f"{_format_metrics(after_metrics)} -> {_format_metrics(before_metrics)} | "
                        f"reasons={', '.join(drift_details.get('reasons', []))}"
                    )

            feature.status = status
            if status in ("ERROR", "WARNING"):
                feature.status_message = self._last_operation_error or feature.status_message
                feature.status_details = dict(self._last_operation_error_details or {})
            else:
                feature.status_message = ""
                feature.status_details = {}

            # === Geometry Delta (Transparenz für Endanwender) ===
            # Berechnet den Geometrie-Unterschied vor/nach jeder Feature-Anwendung.
            # Transient (_geometry_delta wird NICHT gespeichert, nur zur Laufzeit).
            effective_solid = new_solid if (new_solid is not None and status != "ERROR") else current_solid
            before_m = _solid_metrics(solid_before_feature) if solid_before_feature is not None else None
            after_m = _solid_metrics(effective_solid) if effective_solid is not None else None
            if before_m is not None and after_m is not None and before_m["volume"] is not None and after_m["volume"] is not None:
                pre_vol = before_m["volume"]
                post_vol = after_m["volume"]
                vol_pct = ((post_vol - pre_vol) / pre_vol * 100.0) if pre_vol > 1e-12 else 0.0
                feature._geometry_delta = {
                    "volume_before": round(pre_vol, 2),
                    "volume_after": round(post_vol, 2),
                    "volume_pct": round(vol_pct, 1),
                    "faces_before": before_m["faces"],
                    "faces_after": after_m["faces"],
                    "faces_delta": after_m["faces"] - before_m["faces"],
                    "edges_before": before_m["edges"],
                    "edges_after": after_m["edges"],
                    "edges_delta": after_m["edges"] - before_m["edges"],
                }
            elif after_m is not None and after_m["volume"] is not None:
                # Erstes Feature (kein solid_before_feature)
                feature._geometry_delta = {
                    "volume_before": 0.0,
                    "volume_after": round(after_m["volume"], 2),
                    "volume_pct": 0.0,
                    "faces_before": 0,
                    "faces_after": after_m["faces"],
                    "faces_delta": after_m["faces"],
                    "edges_before": 0,
                    "edges_after": after_m["edges"],
                    "edges_delta": after_m["edges"],
                }
            else:
                feature._geometry_delta = None

            if status == "ERROR":
                blocked_by_feature_error = True
                blocked_by_feature_name = feature.name
                blocked_by_feature_index = i

            if new_solid is not None and status != "ERROR":
                current_solid = new_solid
                last_valid_solid = current_solid
                last_valid_feature_index = i

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
                before_heal_metrics = _solid_metrics(current_solid)
                healed, heal_result = GeometryHealer.heal_solid(current_solid)
                heal_applied = False

                if heal_result.success and healed is not None:
                    healed_validation = GeometryValidator.validate_solid(healed, ValidationLevel.NORMAL)
                    healed_metrics = _solid_metrics(healed)
                    topology_changed = (
                        before_heal_metrics["faces"] != healed_metrics["faces"]
                        or before_heal_metrics["edges"] != healed_metrics["edges"]
                    )
                    active_topology_refs = self._has_active_topological_references(max_index=max_index)

                    if strict_self_heal and active_topology_refs and topology_changed:
                        logger.error(
                            "Strict Self-Heal: Healing-Ergebnis verworfen "
                            "(Topologie geändert bei aktiven TNP-Referenzen)."
                        )
                    elif healed_validation.is_error:
                        logger.warning(
                            f"⚠️ Auto-Healing Ergebnis weiterhin ungültig: {healed_validation.message}"
                        )
                    else:
                        current_solid = healed
                        validation = healed_validation
                        heal_applied = True
                        if heal_result.changes_made:
                            logger.info(f"🔧 Auto-Healing: {', '.join(heal_result.changes_made)}")
                        logger.info(
                            f"Self-Heal Delta: {_format_metrics(before_heal_metrics)} -> "
                            f"{_format_metrics(healed_metrics)}"
                        )
                elif not heal_result.success:
                    logger.warning(f"⚠️ Auto-Healing fehlgeschlagen: {heal_result.message}")

                if strict_self_heal and not heal_applied and last_valid_solid is not None and last_valid_feature_index >= 0:
                    rollback_from = _solid_metrics(current_solid)
                    rollback_to = _solid_metrics(last_valid_solid)
                    logger.error(
                        f"Strict Self-Heal: Rollback auf letzten validen Checkpoint "
                        f"(Feature Index {last_valid_feature_index})."
                    )
                    logger.error(
                        f"Strict Self-Heal Rollback (final): "
                        f"{_format_metrics(rollback_from)} -> {_format_metrics(rollback_to)}"
                    )
                    current_solid = last_valid_solid
                    validation = GeometryValidator.validate_solid(current_solid, ValidationLevel.NORMAL)

            # Phase 9:
            # Globales UnifySameDomain nur ohne aktive TNP-Referenzen.
            # Sonst kann ein "post-history" Topologie-Merge ShapeIDs/Indices
            # nachträglich ungültig machen.
            if self._has_active_topological_references(max_index=max_index):
                if is_enabled("tnp_debug_logging"):
                    logger.debug("UnifySameDomain (Rebuild) übersprungen: aktive TNP-Referenzen vorhanden")
            else:
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
        Kompatibilitäts-Hook nach Rebuild.

        Das alte TNP-v3 Registry-System wurde entfernt; TNP v4 wird über den
        ShapeNamingService im Document gepflegt.
        """
        return

    def _feature_has_topological_references(self, feature) -> bool:
        """Prüft, ob ein Feature aktive Topologie-Referenzen trägt."""
        if feature is None:
            return False

        list_ref_attrs = (
            "edge_indices",
            "edge_shape_ids",
            "face_indices",
            "face_shape_ids",
            "opening_face_indices",
            "opening_face_shape_ids",
        )
        single_ref_attrs = (
            "face_index",
            "face_shape_id",
            "profile_face_index",
            "profile_shape_id",
            "path_shape_id",
        )

        for attr in list_ref_attrs:
            values = getattr(feature, attr, None)
            if values:
                return True

        for attr in single_ref_attrs:
            value = getattr(feature, attr, None)
            if value is not None:
                return True

        path_data = getattr(feature, "path_data", None)
        if isinstance(path_data, dict) and path_data.get("edge_indices"):
            return True

        return False

    def _has_active_topological_references(self, max_index: Optional[int] = None) -> bool:
        """True wenn mindestens ein aktives Feature bis max_index Topo-Refs besitzt."""
        limit = len(self.features) if max_index is None else max(0, int(max_index))
        for idx, feature in enumerate(self.features):
            if idx >= limit:
                break
            if getattr(feature, "suppressed", False):
                continue
            if self._feature_has_topological_references(feature):
                return True
        return False

    def update_feature_references(self, feature_id: str, old_solid, new_solid):
        """
        Kompatibilitäts-Hook bei Feature-Änderungen.

        Args:
            feature_id: ID des modifizierten Features
            old_solid: Solid VOR der Änderung
            new_solid: Solid NACH der Änderung
        """
        if is_enabled("tnp_debug_logging"):
            logger.debug(f"TNP v4.0: Feature {feature_id} wurde modifiziert")

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

    def _resolve_edges_tnp(self, solid, feature) -> List:
        """
        TNP v4.1 Edge-Auflösung mit History-First Strategie.

        Reihenfolge (STRICT):
        1. OperationRecord-Mappings (History-basiert)
        2. edge_shape_ids mit direkter Auflösung
        3. edge_indices (Topology-Index)
        4. geometric_selectors (NUR LETZTE OPTION)

        WICHTIG: Wenn History-First versagt und keine andere Methode funktioniert,
        soll das Feature fehlschlagen statt auf Geometric-Fallback zurückzufallen.
        """
        all_edges = list(solid.edges()) if hasattr(solid, 'edges') else []
        if not all_edges:
            if is_enabled("tnp_debug_logging"):
                logger.warning("TNP v4.0: Keine Edges im Solid gefunden")
            return []

        feature_name = getattr(feature, 'name', 'Unknown')
        edge_shape_ids = list(getattr(feature, 'edge_shape_ids', []) or [])
        edge_indices_raw = list(getattr(feature, 'edge_indices', []) or [])
        geometric_selectors = list(getattr(feature, 'geometric_selectors', []) or [])

        valid_edge_indices = []
        for raw_idx in edge_indices_raw:
            try:
                idx = int(raw_idx)
            except Exception:
                continue
            if idx >= 0 and idx not in valid_edge_indices:
                valid_edge_indices.append(idx)

        if is_enabled("tnp_debug_logging"):
            logger.info(
                f"TNP v4.0: Resolving edges for {feature_name} "
                f"(shape_ids={len(edge_shape_ids)}, indices={len(valid_edge_indices)}, "
                f"selectors={len(geometric_selectors)}, solid_edges={len(all_edges)})"
            )

        service = None
        if self._document and hasattr(self._document, '_shape_naming_service'):
            service = self._document._shape_naming_service

        resolved_edges = []
        unresolved_shape_ids = []  # Für Debug-Visualisierung
        resolved_shape_ids = []
        resolved_edge_indices = []
        resolved_edges_from_shape = []
        resolved_edges_from_index = []

        strict_edge_feature = isinstance(feature, (FilletFeature, ChamferFeature))

        def _edge_index_of(edge_obj):
            for edge_idx, candidate in enumerate(all_edges):
                if self._is_same_edge(candidate, edge_obj):
                    return edge_idx
            return None

        def _append_source_edge(collection, edge_obj) -> None:
            for existing in collection:
                if self._is_same_edge(existing, edge_obj):
                    return
            collection.append(edge_obj)

        def _append_unique(edge_obj, shape_id=None, topo_index=None, source=None) -> None:
            if edge_obj is None:
                return
            for existing in resolved_edges:
                if self._is_same_edge(existing, edge_obj):
                    if source == "shape":
                        _append_source_edge(resolved_edges_from_shape, existing)
                    elif source == "index":
                        _append_source_edge(resolved_edges_from_index, existing)
                    return
            resolved_edges.append(edge_obj)
            if source == "shape":
                _append_source_edge(resolved_edges_from_shape, edge_obj)
            elif source == "index":
                _append_source_edge(resolved_edges_from_index, edge_obj)
            if shape_id is not None:
                resolved_shape_ids.append(shape_id)
            if topo_index is None:
                topo_index = _edge_index_of(edge_obj)
            if topo_index is not None:
                try:
                    topo_index = int(topo_index)
                    if topo_index >= 0 and topo_index not in resolved_edge_indices:
                        resolved_edge_indices.append(topo_index)
                except Exception:
                    pass

        def _resolve_by_operation_records() -> int:
            """TNP v4.1: Zuerst OperationRecords nach Mappings durchsuchen."""
            if not service or not edge_shape_ids:
                return 0

            resolved_count = 0
            for op in service._operations:
                if op.manual_mappings and op.feature_id == getattr(feature, 'id', ''):
                    # Prüfe ob ShapeIDs in den Mappings vorhanden sind
                    for input_uuid, output_uuids in op.manual_mappings.items():
                        # Input-ShapeID finden
                        for shape_id in edge_shape_ids:
                            if hasattr(shape_id, 'uuid') and shape_id.uuid == input_uuid:
                                # Output-ShapeIDs finden
                                for output_uuid in output_uuids:
                                    if output_uuid in service._shapes:
                                        output_record = service._shapes[output_uuid]
                                        if output_record.ocp_shape:
                                            matching_edge = self._find_matching_edge_in_solid(
                                                output_record.ocp_shape, all_edges
                                            )
                                            if matching_edge is not None:
                                                _append_unique(matching_edge, shape_id=shape_id, source="shape")
                                                resolved_count += 1
                                                if is_enabled("tnp_debug_logging"):
                                                    logger.debug(
                                                        f"TNP v4.1: Edge via OperationRecord-Mapping aufgelöst: "
                                                        f"{input_uuid[:8]} → {output_uuid[:8]}"
                                                    )
            return resolved_count

        def _resolve_by_shape_ids() -> None:
            if not edge_shape_ids or service is None:
                return
            for i, shape_id in enumerate(edge_shape_ids):
                if not hasattr(shape_id, "uuid"):
                    continue
                try:
                    resolved_ocp, method = service.resolve_shape_with_method(
                        shape_id,
                        solid,
                        log_unresolved=False,
                    )
                    if resolved_ocp is None:
                        unresolved_shape_ids.append(shape_id)
                        if is_enabled("tnp_debug_logging"):
                            logger.warning(f"TNP v4.0: Edge {i} konnte via ShapeID nicht aufgelöst werden")
                        continue

                    matching_edge = self._find_matching_edge_in_solid(resolved_ocp, all_edges)
                    if matching_edge is not None:
                        _append_unique(matching_edge, shape_id=shape_id, source="shape")
                        if is_enabled("tnp_debug_logging"):
                            logger.debug(f"TNP v4.0: Edge {i} via ShapeID aufgelöst (method={method})")
                    else:
                        unresolved_shape_ids.append(shape_id)
                        if is_enabled("tnp_debug_logging"):
                            logger.warning(f"TNP v4.0: Keine passende Solid-Edge für ShapeID-Edge {i}")
                except Exception as e:
                    unresolved_shape_ids.append(shape_id)
                    if is_enabled("tnp_debug_logging"):
                        logger.warning(f"TNP v4.0: Edge {i} ShapeID-Auflösung fehlgeschlagen: {e}")

        def _resolve_by_indices() -> None:
            if not valid_edge_indices:
                return
            try:
                from modeling.topology_indexing import edge_from_index

                for edge_idx in valid_edge_indices:
                    resolved = edge_from_index(solid, int(edge_idx))
                    _append_unique(resolved, topo_index=edge_idx, source="index")
            except Exception as e:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP v4.0: Index-Auflösung fehlgeschlagen: {e}")

        expected_shape_refs = sum(1 for sid in edge_shape_ids if hasattr(sid, "uuid"))
        single_ref_pair = bool(expected_shape_refs == 1 and len(valid_edge_indices) == 1)
        shape_ids_index_aligned = True
        if expected_shape_refs > 0 and valid_edge_indices and not single_ref_pair:
            for sid in edge_shape_ids:
                if not hasattr(sid, "uuid"):
                    continue
                local_idx = getattr(sid, "local_index", None)
                if not isinstance(local_idx, int) or not (0 <= int(local_idx) < len(valid_edge_indices)):
                    shape_ids_index_aligned = False
                    break
        strict_dual_edge_refs = (
            strict_edge_feature
            and expected_shape_refs > 0
            and bool(valid_edge_indices)
            and len(valid_edge_indices) == expected_shape_refs
            and (shape_ids_index_aligned or single_ref_pair)
        )

        # TNP v4.1: History-First Strategie
        # 1. Zuerst OperationRecords (History-basiert)
        op_resolved = _resolve_by_operation_records()
        if op_resolved > 0 and is_enabled("tnp_debug_logging"):
            logger.debug(f"TNP v4.1: {op_resolved} Edges via OperationRecords aufgelöst")

        # 2. Dann ShapeIDs mit direkter Auflösung
        if op_resolved < len(edge_shape_ids):
            _resolve_by_shape_ids()

        # 3. Dann Index-basierte Auflösung
        if len(resolved_edges) < len(edge_shape_ids) or valid_edge_indices:
            _resolve_by_indices()

        strict_topology_mismatch = False
        if strict_dual_edge_refs:
            if (
                len(resolved_edges_from_index) < len(valid_edge_indices)
                or len(resolved_edges_from_shape) < expected_shape_refs
            ):
                strict_topology_mismatch = True
            else:
                for idx_edge in resolved_edges_from_index:
                    if not any(self._is_same_edge(idx_edge, shape_edge) for shape_edge in resolved_edges_from_shape):
                        strict_topology_mismatch = True
                        break
                if not strict_topology_mismatch:
                    for shape_edge in resolved_edges_from_shape:
                        if not any(self._is_same_edge(shape_edge, idx_edge) for idx_edge in resolved_edges_from_index):
                            strict_topology_mismatch = True
                            break

        # Single-Edge UX-Fall: Bei genau einer Index+ShapeID-Referenz kann eine
        # stale ShapeID (nach Undo/Redo) auf eine andere Edge zeigen, obwohl der
        # index-konsistente Edge-Pfad korrekt ist. Dann index deterministisch
        # bevorzugen und ShapeID später auf den tatsächlich verwendeten Edge heilen.
        if strict_topology_mismatch and single_ref_pair and resolved_edges_from_index:
            if is_enabled("tnp_debug_logging"):
                logger.warning(
                    f"{feature_name}: Single-Edge ShapeID/Index-Mismatch erkannt; "
                    "verwende edge_index als autoritative Referenz."
                )
            resolved_edges = list(resolved_edges_from_index)
            resolved_edges_from_shape = []
            resolved_shape_ids = []
            strict_topology_mismatch = False

        has_topological_refs = bool(valid_edge_indices or expected_shape_refs > 0)
        unresolved_topology_refs = (
            (valid_edge_indices and len(resolved_edge_indices) < len(valid_edge_indices))
            or (
                expected_shape_refs > 0
                and not valid_edge_indices
                and len(resolved_shape_ids) < expected_shape_refs
            )
        )
        if strict_dual_edge_refs and strict_topology_mismatch:
            unresolved_topology_refs = True

        # TNP v4.1: Bei Topology-Mismatch zuerst Geometric-Fallback probieren
        # (statt sofort aufzugeben wie in v4.0)
        if has_topological_refs and unresolved_topology_refs:
            mismatch_hint = " (ShapeID/Index-Mismatch)" if strict_topology_mismatch else ""
            logger.warning(
                f"{feature_name}: Topologie-Referenzen ungültig{mismatch_hint}. "
                f"Versuche Geometric-Fallback ({len(geometric_selectors)} Selektoren)..."
            )
            # Don't return here - try geometric recovery first!

        # TNP v4.1: Geometric-Fallback wenn:
        # 1. Keine Topologie-Referenzen vorhanden (original)
        # 2. ODER Topologie-Referenzen sind aufgelöst/inkonsistent (unresolved_topology_refs)
        need_selector_recovery = (
            ((not has_topological_refs) and (not resolved_edges))
            or (unresolved_topology_refs and geometric_selectors)
        )

        # GeometricSelector-Auflösung ohne Topologie-Referenzen oder bei Mismatch (Recovery)
        if need_selector_recovery and geometric_selectors:
            edges_before_geo = len(resolved_edges)
            try:
                from modeling.geometric_selector import GeometricEdgeSelector

                for selector_data in geometric_selectors:
                    if isinstance(selector_data, dict):
                        geo_sel = GeometricEdgeSelector.from_dict(selector_data)
                    elif hasattr(selector_data, 'find_best_match'):
                        geo_sel = selector_data
                    else:
                        continue
                    _append_unique(geo_sel.find_best_match(all_edges))
            except Exception as e:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"TNP v4.0: GeometricEdgeSelector-Auflösung fehlgeschlagen: {e}")

            edges_after_geo = len(resolved_edges)
            if edges_after_geo > edges_before_geo:
                recovered = edges_after_geo - edges_before_geo
                logger.success(f"  Geometric-Fallback: {recovered}/{len(geometric_selectors)} Edges wiederhergestellt")

        # 4) Referenzen konsolidieren (indices + optional ShapeIDs)
        resolved_indices = []
        for edge in resolved_edges:
            for edge_idx, candidate in enumerate(all_edges):
                if self._is_same_edge(candidate, edge):
                    resolved_indices.append(edge_idx)
                    break
        if resolved_indices:
            feature.edge_indices = resolved_indices

        if service is not None and resolved_edges:
            new_shape_ids = []
            for idx, edge in enumerate(resolved_edges):
                try:
                    shape_id = service.find_shape_id_by_edge(edge)
                    if shape_id is None and hasattr(edge, 'wrapped'):
                        ec = edge.center()
                        edge_len = edge.length if hasattr(edge, 'length') else 0.0
                        shape_id = service.register_shape(
                            ocp_shape=edge.wrapped,
                            shape_type=ShapeType.EDGE,
                            feature_id=feature.id,
                            local_index=idx,
                            geometry_data=(ec.X, ec.Y, ec.Z, edge_len),
                        )
                    if shape_id is not None:
                        new_shape_ids.append(shape_id)
                except Exception:
                    continue
            if new_shape_ids:
                feature.edge_shape_ids = new_shape_ids

        total_refs = max(len(edge_shape_ids), len(valid_edge_indices), len(geometric_selectors))
        found = len(resolved_edges)
        if is_enabled("tnp_debug_logging"):
            if total_refs == 0:
                logger.warning("TNP v4.0: Feature hat keine Edge-Referenzen")
            elif found >= total_refs:
                logger.debug(f"TNP v4.0: {found}/{total_refs} Edges aufgelöst")
            else:
                logger.warning(f"TNP v4.0: Nur {found}/{total_refs} Edges aufgelöst")
        
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

    @staticmethod
    def _is_same_edge(edge_a, edge_b) -> bool:
        """
        Robuster Edge-Vergleich für TNP-Pfade.

        Bevorzugt OCP IsSame (Topologie-identisch), fällt auf eine leichte
        Geometrie-Prüfung und zuletzt Objektidentität zurück.
        """
        if edge_a is None or edge_b is None:
            return False
        try:
            wrapped_a = edge_a.wrapped if hasattr(edge_a, "wrapped") else edge_a
            wrapped_b = edge_b.wrapped if hasattr(edge_b, "wrapped") else edge_b
            if hasattr(wrapped_a, "IsSame") and wrapped_a.IsSame(wrapped_b):
                return True
        except Exception:
            pass
        try:
            center_a = edge_a.center()
            center_b = edge_b.center()
            dx = float(center_a.X) - float(center_b.X)
            dy = float(center_a.Y) - float(center_b.Y)
            dz = float(center_a.Z) - float(center_b.Z)
            if (dx * dx + dy * dy + dz * dz) <= 1e-12:
                len_a = float(getattr(edge_a, "length", 0.0) or 0.0)
                len_b = float(getattr(edge_b, "length", 0.0) or 0.0)
                if abs(len_a - len_b) <= 1e-9:
                    return True
        except Exception:
            pass
        return edge_a is edge_b
    
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
        Phase 2-3: OCP-First ExtrudeFeature Implementation mit Feature-Flag-Steuerung.

        Architektur:
        - ocp_first_extrude=True: Nutzt OCPExtrudeHelper mit TNP Integration
        - ocp_first_extrude=False: Legacy Pfad (bestehende Implementation)

        TNP v4.0 Integration:
        1. Mit Sketch: Profile aus sketch.closed_profiles (immer aktuell)
        2. Ohne Sketch (Push/Pull): BRepFeat_MakePrism (MANDATORY OCP-First)
        3. Ohne Sketch (Face aus BREP): OCP MakePrism direkte Extrusion

        FALLBACK: Wenn OCP-First None zurückgibt, wird automatisch Legacy versucht.
        """
        if is_enabled("ocp_first_extrude"):
            result = self._compute_extrude_part_ocp_first(feature)
            # Fallback: Wenn OCP-First fehlschlägt, versuche Legacy
            if result is None:
                logger.warning("[OCP-FIRST] Fehlgeschlagen, versuche Legacy-Fallback...")
                return self._compute_extrude_part_legacy(feature)
            return result
        else:
            return self._compute_extrude_part_legacy(feature)

    def _compute_extrude_part_ocp_first(self, feature: ExtrudeFeature):
        """
        OCP-First Pfad: Nutzt OCPExtrudeHelper mit TNP Integration.

        Dieser Pfad verwendet den OCPExtrudeHelper der:
        - OCP-PRIMARY ist (kein Build123d Fallback)
        - Verbindliche TNP Integration durchführt
        - Alle Faces/Edges im ShapeNamingService registriert
        """
        # Phase 2: Prüfe Geometrie-Quelle
        has_sketch = feature.sketch is not None
        has_polys = hasattr(feature, 'precalculated_polys') and feature.precalculated_polys
        has_face_brep = hasattr(feature, 'face_brep') and feature.face_brep
        has_face_refs = (hasattr(feature, 'face_shape_id') and feature.face_shape_id is not None)

        if is_enabled("extrude_debug"):
            logger.debug(f"[OCP-FIRST] has_sketch={has_sketch}, has_polys={has_polys}, "
                       f"has_face_brep={has_face_brep}, has_face_refs={has_face_refs}")

        # Phase 2: KEINE Geometry-Quelle ohne Sketch = ERROR
        if not has_sketch and not has_polys and not has_face_brep:
            raise ValueError("ExtrudeFeature: Keine Geometrie-Quelle "
                           "(Sketch oder precalculated_polys oder face_brep erforderlich)")

        # Feature-ID sicherstellen
        if not hasattr(feature, 'id') or feature.id is None:
            import uuid
            feature.id = str(uuid.uuid4())[:8]
            logger.debug(f"[OCP-FIRST] Generated ID for ExtrudeFeature: {feature.id}")

        # TNP Service holen
        naming_service = None
        if self._document and hasattr(self._document, '_shape_naming_service'):
            naming_service = self._document._shape_naming_service

        if naming_service is None:
            raise ValueError(
                "TNP ShapeNamingService nicht verfügbar für OCP-First Extrude. "
                "Bitte Document mit TNP Service verwenden."
            )

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

            # === OCP-FIRST: Nutze OCPExtrudeHelper mit TNP Integration ===
            # Profile-Bestimmung (gleich wie Legacy)
            polys_to_extrude = []

            if has_sketch:
                # KERNEL FIRST: Profile aus Sketch ableiten (nicht aus Cache!)
                sketch_profiles = getattr(sketch, 'closed_profiles', [])
                profile_selector = getattr(feature, 'profile_selector', [])

                if sketch_profiles and profile_selector:
                    # Selektor-Match (CAD KERNEL FIRST - KEINE FALLBACKS!)
                    # KONVERTIERUNG: closed_profiles sind List[List[Line2D]], Shapely braucht Polygons
                    shapely_profiles = self._convert_line_profiles_to_polygons(sketch_profiles)
                    polys_to_extrude = self._filter_profiles_by_selector(
                        shapely_profiles, profile_selector
                    )
                    if polys_to_extrude:
                        logger.info(f"[OCP-FIRST] {len(polys_to_extrude)}/{len(sketch_profiles)} Profile via Selektor")
                    else:
                        # OCP-First: Selektor hat nicht gematcht → ERROR, kein Fallback!
                        logger.error(f"[OCP-FIRST] Selektor-Match fehlgeschlagen! Selector: {profile_selector}")
                        logger.error(f"[OCP-FIRST] Verfügbare Profile: {[(p.centroid.x, p.centroid.y) for p in shapely_profiles]}")
                        raise ValueError("Profile-Selektor hat kein Match - keine Extrusion möglich")
                elif sketch_profiles:
                    # Kein Selektor → alle Profile verwenden (Legacy/Import)
                    # KONVERTIERUNG: closed_profiles sind List[List[Line2D]], Shapely braucht Polygons
                    polys_to_extrude = self._convert_line_profiles_to_polygons(sketch_profiles)
                    logger.info(f"[OCP-FIRST] Alle {len(polys_to_extrude)} Profile (kein Selektor)")
                else:
                    # Sketch hat keine closed_profiles
                    logger.warning(f"[OCP-FIRST] Sketch hat keine closed_profiles!")
            else:
                # Phase 2: Ohne Sketch (Push/Pull): precalculated_polys oder face_brep
                if has_polys:
                    polys_to_extrude = list(feature.precalculated_polys)
                    logger.info(f"[OCP-FIRST] {len(polys_to_extrude)} Profile (Push/Pull Mode)")
                elif has_face_brep:
                    # Phase 2: Face aus BREP deserialisieren und direkt extrudieren
                    logger.info(f"[OCP-FIRST] Face aus BREP (Push/Pull auf {feature.face_type})")
                    return self._extrude_from_face_brep(feature)

            # === TNP v4.1: Native Circle Path (VOR Polygon-Verarbeitung) ===
            # Prüfe ob der Sketch Kreise mit native_ocp_data hat
            # Wenn ja, erstelle direkt native OCP Circle Faces (3 Faces statt 14+)
            faces_to_extrude = []
            if has_sketch and hasattr(sketch, 'circles') and sketch.circles:
                native_circle_faces = self._create_faces_from_native_circles(sketch, plane, profile_selector)
                if native_circle_faces:
                    logger.info(f"[TNP v4.1] {len(native_circle_faces)} native Circle Faces erstellt (3 Faces statt 14+)")
                    faces_to_extrude.extend(native_circle_faces)

            # === TNP v4.1: Native Arc Path (wenige Faces statt Polygon) ===
            # Prüfe ob der Sketch Arcs mit native_ocp_data hat
            if has_sketch and hasattr(sketch, 'arcs') and sketch.arcs:
                native_arc_faces = self._create_faces_from_native_arcs(sketch, plane, profile_selector)
                if native_arc_faces:
                    logger.info(f"[TNP v4.1] {len(native_arc_faces)} native Arc Faces erstellt (wenige Faces statt vielen)")
                    faces_to_extrude.extend(native_arc_faces)

            # Wenn native Faces erstellt wurden, diese direkt extrudieren
            if faces_to_extrude:
                polys_to_extrude = []  # Polygon-Path überspringen
                logger.info(f"[TNP v4.1] {len(faces_to_extrude)} native Faces direkt extrudieren")

            # === Faces erstellen und mit OCPExtrudeHelper extrudieren ===
            if polys_to_extrude:
                if is_enabled("extrude_debug"):
                    logger.info(f"[OCP-FIRST] Verarbeite {len(polys_to_extrude)} Profile.")

                for idx, poly in enumerate(polys_to_extrude):
                    try:
                        # VALIDIERUNG: Degenerierte Polygone überspringen
                        poly_area = poly.area if hasattr(poly, 'area') else 0
                        if poly_area < 1e-6:
                            logger.warning(f"  ⚠️ Polygon {idx} hat Area≈0 - überspringe (degeneriert)")
                            continue

                        # Außenkontur extrahieren
                        outer_coords = list(poly.exterior.coords)[:-1]
                        outer_pts = [plane.from_local_coords((p[0], p[1])) for p in outer_coords]
                        face = make_face(Wire.make_polygon(outer_pts))

                        # Löcher abziehen
                        for interior in poly.interiors:
                            inner_coords = list(interior.coords)[:-1]
                            inner_pts = [plane.from_local_coords((p[0], p[1])) for p in inner_coords]
                            face -= make_face(Wire.make_polygon(inner_pts))

                        faces_to_extrude.append(face)
                    except Exception as e:
                        logger.warning(f"Fehler bei Face-Konvertierung: {e}")
                        import traceback
                        traceback.print_exc()

            # === TNP v4.1: Alle Faces extrudieren (Native Circles UND Polygone) ===
            if faces_to_extrude:
                # Mit OCPExtrudeHelper extrudieren
                amount = feature.distance * feature.direction
                direction_vec = plane.z_dir * amount

                for f in faces_to_extrude:
                    try:
                        # OCP-First: Nutze OCPExtrudeHelper mit TNP Integration
                        result = OCPExtrudeHelper.extrude(
                            face=f,
                            direction=plane.z_dir,
                            distance=amount,
                            naming_service=naming_service,
                            feature_id=feature.id
                        )
                        if result is not None:
                            solids.append(result)
                            logger.debug(f"[OCP-FIRST] Extrudiert: {feature.id}")
                    except Exception as e:
                        logger.warning(f"[OCP-FIRST] OCPExtrudeHelper fehlgeschlagen: {e}")
                        # Fallback zu _ocp_extrude_face
                        s = self._ocp_extrude_face(f, amount, plane.z_dir)
                        if s is not None:
                            solids.append(s)

            # OCP-First: KEIN Legacy-Fallback
            if not solids:
                logger.error("[OCP-FIRST] Keine gültigen Profile/Faces gefunden - kein Legacy-Fallback!")
                return None

            if not solids: return None
            return solids[0] if len(solids) == 1 else Compound(children=solids)

        except Exception as e:
            logger.error(f"[OCP-FIRST] Extrude Fehler: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _compute_extrude_part_legacy(self, feature: ExtrudeFeature):
        """
        Legacy Pfad: Bestehende Extrude-Implementierung (getestet und stabil).

        Dieser Pfad verwendet die bewährte Implementierung mit:
        - Build123d PRIMARY für Extrusion
        - OCP als Fallback
        - Volle Geometrie-Unterstützung (Kreise, Splines, etc.)
        """
        # Phase 2: Prüfe Geometrie-Quelle
        has_sketch = feature.sketch is not None
        has_polys = hasattr(feature, 'precalculated_polys') and feature.precalculated_polys
        has_face_brep = hasattr(feature, 'face_brep') and feature.face_brep

        if is_enabled("extrude_debug"):
            logger.debug(f"[LEGACY] has_sketch={has_sketch}, has_polys={has_polys}, has_face_brep={has_face_brep}")

        # Phase 2: KEINE Geometry-Quelle ohne Sketch = ERROR
        if not has_sketch and not has_polys and not has_face_brep:
            raise ValueError("ExtrudeFeature: Keine Geometrie-Quelle "
                           "(Sketch oder precalculated_polys oder face_brep erforderlich)")

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

            # === LEGACY: CAD KERNEL FIRST: Profile-Bestimmung ===
            polys_to_extrude = []

            if has_sketch:
                # KERNEL FIRST: Profile aus Sketch ableiten (nicht aus Cache!)
                sketch_profiles = getattr(sketch, 'closed_profiles', [])
                profile_selector = getattr(feature, 'profile_selector', [])

                if sketch_profiles and profile_selector:
                    # Selektor-Match (CAD KERNEL FIRST - KEINE FALLBACKS!)
                    # KONVERTIERUNG: closed_profiles sind List[List[Line2D]], Shapely braucht Polygons
                    shapely_profiles = self._convert_line_profiles_to_polygons(sketch_profiles)
                    polys_to_extrude = self._filter_profiles_by_selector(
                        shapely_profiles, profile_selector
                    )
                    if polys_to_extrude:
                        logger.info(f"[LEGACY] {len(polys_to_extrude)}/{len(sketch_profiles)} Profile via Selektor")
                    else:
                        # Phase 2: Selektor hat nicht gematcht → ERROR, kein Fallback!
                        logger.error(f"[LEGACY] Selektor-Match fehlgeschlagen! Selector: {profile_selector}")
                        logger.error(f"[LEGACY] Verfügbare Profile: {[(p.centroid.x, p.centroid.y) for p in shapely_profiles]}")
                        raise ValueError("Profile-Selektor hat kein Match - keine Extrusion möglich")
                elif sketch_profiles:
                    # Kein Selektor → alle Profile verwenden (Legacy/Import)
                    # KONVERTIERUNG: closed_profiles sind List[List[Line2D]], Legacy braucht Shapely-Polygons
                    polys_to_extrude = self._convert_line_profiles_to_polygons(sketch_profiles)
                    logger.info(f"[LEGACY] Alle {len(polys_to_extrude)} Profile (kein Selektor)")
                else:
                    # Sketch hat keine closed_profiles
                    logger.warning(f"[LEGACY] Sketch hat keine closed_profiles!")
            else:
                # Phase 2: Ohne Sketch (Push/Pull): precalculated_polys oder face_brep
                if has_polys:
                    polys_to_extrude = list(feature.precalculated_polys)
                    logger.info(f"[LEGACY] {len(polys_to_extrude)} Profile (Push/Pull Mode)")
                elif has_face_brep:
                    # Phase 2: Face aus BREP deserialisieren und direkt extrudieren
                    logger.info(f"[LEGACY] Face aus BREP (Push/Pull auf {feature.face_type})")
                    return self._extrude_from_face_brep(feature)

            # === LEGACY: Extrude-Logik mit voller Geometrie-Unterstützung ===
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
                            native_spline = self._detect_matching_native_spline(outer_coords, feature.sketch)

                            if native_spline is not None:
                                logger.info(f"  → Außenkontur als NATIVE SPLINE: {len(native_spline.control_points)} ctrl pts")
                                spline_wire = self._create_wire_from_native_spline(native_spline, plane)

                                if spline_wire is not None:
                                    face = make_face(spline_wire)
                                else:
                                    logger.warning("  → Spline Wire Fallback: Verwende Polygon")
                                    outer_pts = [plane.from_local_coords((p[0], p[1])) for p in outer_coords]
                                    face = make_face(Wire.make_polygon(outer_pts))
                            else:
                                outer_circle_info = self._detect_circle_from_points(outer_coords)

                                if outer_circle_info:
                                    cx, cy, radius = outer_circle_info
                                    logger.info(f"  → Außenkontur als ECHTER KREIS (mit Löchern): r={radius:.2f} at ({cx:.2f}, {cy:.2f})")

                                    center_3d = plane.from_local_coords((cx, cy))
                                    from build123d import Plane as B3DPlane
                                    circle_plane = B3DPlane(origin=center_3d, z_dir=plane.z_dir)
                                    circle_wire = Wire.make_circle(radius, circle_plane)
                                    face = make_face(circle_wire)
                                else:
                                    outer_pts = [plane.from_local_coords((p[0], p[1])) for p in outer_coords]
                                    face = make_face(Wire.make_polygon(outer_pts))

                        # 2. Löcher abziehen (Shapely Interiors)
                        for int_idx, interior in enumerate(poly.interiors):
                            inner_coords = list(interior.coords)[:-1]
                            logger.debug(f"  Interior {int_idx}: {len(inner_coords)} Punkte")

                            circle_info = self._detect_circle_from_points(inner_coords)

                            if circle_info:
                                cx, cy, radius = circle_info
                                logger.info(f"  → Loch als ECHTER KREIS: r={radius:.2f} at ({cx:.2f}, {cy:.2f})")

                                center_3d = plane.from_local_coords((cx, cy))
                                from build123d import Plane as B3DPlane
                                circle_plane = B3DPlane(origin=center_3d, z_dir=plane.z_dir)
                                circle_wire = Wire.make_circle(radius, circle_plane)
                                circle_face = make_face(circle_wire)
                                face -= circle_face
                            else:
                                logger.warning(f"  → Loch als POLYGON ({len(inner_coords)} Punkte) - kein Kreis erkannt!")
                                inner_pts = [plane.from_local_coords((p[0], p[1])) for p in inner_coords]
                                face -= make_face(Wire.make_polygon(inner_pts))

                        faces_to_extrude.append(face)
                    except Exception as e:
                        logger.warning(f"Fehler bei Face-Konvertierung: {e}")
                        import traceback
                        traceback.print_exc()

                # Extrudieren mit OCP für bessere Robustheit (Build123d PRIMARY, OCP FALLBACK)
                amount = feature.distance * feature.direction

                # FIX: Für Cut-Operationen Extrusion verlängern um Through-Cuts zu ermöglichen
                cut_extension = 0.0
                if feature.operation == "Cut" and abs(amount) > 0.1:
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

            # LEGACY: Keine gültigen Profile/Faces
            if not solids:
                logger.error("[LEGACY] Keine gültigen Profile/Faces gefunden!")
                return None

            if not solids: return None
            return solids[0] if len(solids) == 1 else Compound(children=solids)

        except Exception as e:
            logger.error(f"[LEGACY] Extrude Fehler: {e}")
            return None

    def _convert_line_profiles_to_polygons(self, line_profiles: list) -> list:
        """
        Konvertiert Profile zu Shapely Polygons für Legacy-Code.

        Unterstützt zwei Formate:
        1. List[List[Line2D]] - vom Sketch _find_closed_profiles()
        2. List[ShapelyPolygon] - bereits vom UI vorkonvertiert

        Args:
            line_profiles: Liste von Profilen (List[Line2D] oder ShapelyPolygon)

        Returns:
            Liste von Shapely Polygon Objekten
        """
        from shapely.geometry import Polygon as ShapelyPoly

        polygons = []
        for profile in line_profiles:
            if not profile:
                continue

            # Fall 1: Bereits ein Shapely Polygon (vom UI)
            if hasattr(profile, 'exterior') and hasattr(profile, 'area'):
                if profile.is_valid and profile.area > 0:
                    polygons.append(profile)
                continue

            # Fall 2: List[Line2D] - vom Sketch _find_closed_profiles()
            coords = []
            try:
                for line in profile:
                    if hasattr(line, 'start') and hasattr(line.start, 'x'):
                        coords.append((line.start.x, line.start.y))
                    elif isinstance(line, tuple) and len(line) == 2:
                        coords.append(line)
            except Exception:
                continue

            # Shapely Polygon erstellen
            if len(coords) >= 3:
                try:
                    poly = ShapelyPoly(coords)
                    if poly.is_valid and poly.area > 0:
                        polygons.append(poly)
                    else:
                        logger.warning(f"[PROFILE] Ungültiges/degeneriertes Polygon mit {len(coords)} Punkten")
                except Exception as e:
                    logger.warning(f"[PROFILE] Polygon-Erstellung fehlgeschlagen: {e}")

        return polygons

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
        TNP v4.0: BRepFeat-basierter Push/Pull für Body-Face-Operationen.

        Face-Referenzauflösung:
        1. face_index (topology_indexing)
        2. face_shape_id (ShapeNamingService)
        3. face_selector (Legacy-Recovery)
        """
        if current_solid is None:
            raise ValueError("BRepFeat Push/Pull benötigt einen existierenden Körper")

        operation = getattr(feature, "operation", "")
        if operation not in ("Join", "Cut"):
            raise ValueError(f"BRepFeat Push/Pull unterstützt nur Join/Cut (erhalten: {operation})")

        import numpy as np
        from modeling.topology_indexing import face_from_index, face_index_of

        service = None
        if self._document and hasattr(self._document, "_shape_naming_service"):
            service = self._document._shape_naming_service

        selector_data = getattr(feature, "face_selector", None)
        selector_normal_hint = None
        if isinstance(selector_data, dict):
            raw_normal = selector_data.get("normal")
            if isinstance(raw_normal, (list, tuple)) and len(raw_normal) == 3:
                try:
                    selector_normal_hint = np.array(raw_normal, dtype=float)
                except Exception:
                    selector_normal_hint = None

        def _same_face(face_a, face_b) -> bool:
            try:
                wa = face_a.wrapped if hasattr(face_a, "wrapped") else face_a
                wb = face_b.wrapped if hasattr(face_b, "wrapped") else face_b
                return wa.IsSame(wb)
            except Exception:
                return face_a is face_b

        def _face_normal_np(face_obj):
            try:
                center = face_obj.center()
                n = face_obj.normal_at(center)
                n_vec = np.array([n.X, n.Y, n.Z], dtype=float)
                try:
                    from OCP.TopAbs import TopAbs_REVERSED
                    if face_obj.wrapped.Orientation() == TopAbs_REVERSED:
                        n_vec = -n_vec
                except Exception:
                    pass
                n_len = np.linalg.norm(n_vec)
                if n_len < 1e-9:
                    return None
                return n_vec / n_len
            except Exception:
                return None

        def _normal_alignment(face_obj, normal_hint):
            if face_obj is None or normal_hint is None:
                return -1.0
            try:
                hint = np.array(normal_hint, dtype=float)
                hint_len = np.linalg.norm(hint)
                if hint_len < 1e-9:
                    return -1.0
                hint = hint / hint_len
                face_n = _face_normal_np(face_obj)
                if face_n is None:
                    return -1.0
                return abs(float(np.dot(face_n, hint)))
            except Exception:
                return -1.0

        def _sync_feature_face_refs(face_obj) -> None:
            if face_obj is None:
                return
            try:
                resolved_idx = face_index_of(current_solid, face_obj)
                if resolved_idx is not None:
                    feature.face_index = int(resolved_idx)
            except Exception:
                pass

            try:
                from modeling.geometric_selector import GeometricFaceSelector
                feature.face_selector = GeometricFaceSelector.from_face(face_obj).to_dict()
            except Exception:
                pass

            if service and hasattr(face_obj, "wrapped"):
                try:
                    exact_sid = service.find_shape_id_by_face(face_obj, require_exact=True)
                except Exception:
                    exact_sid = None

                if exact_sid is None:
                    try:
                        fc = face_obj.center()
                        area = float(face_obj.area) if hasattr(face_obj, "area") else 0.0
                        exact_sid = service.register_shape(
                            ocp_shape=face_obj.wrapped,
                            shape_type=ShapeType.FACE,
                            feature_id=feature.id,
                            # Single-face reference slot (face_shape_id) is always 0.
                            local_index=0,
                            geometry_data=(fc.X, fc.Y, fc.Z, area),
                        )
                    except Exception as sid_err:
                        if is_enabled("tnp_debug_logging"):
                            logger.debug(f"BRepFeat Push/Pull: Face-ShapeID Sync fehlgeschlagen: {sid_err}")

                if exact_sid is not None:
                    feature.face_shape_id = exact_sid

        index_face = None
        raw_face_index = getattr(feature, "face_index", None)
        if raw_face_index is not None:
            try:
                idx = int(raw_face_index)
                if idx >= 0:
                    index_face = face_from_index(current_solid, idx)
            except Exception:
                index_face = None

        shape_face = None
        shape_method = ""
        shape_method_l = ""
        if (
            service
            and hasattr(getattr(feature, "face_shape_id", None), "uuid")
        ):
            try:
                resolved_ocp, shape_method = service.resolve_shape_with_method(
                    feature.face_shape_id,
                    current_solid,
                    log_unresolved=False,
                )
                if resolved_ocp is not None:
                    from build123d import Face
                    shape_face = Face(resolved_ocp)
            except Exception as resolve_err:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"BRepFeat Push/Pull: ShapeID-Auflösung fehlgeschlagen: {resolve_err}")
        shape_method_l = str(shape_method or "").lower()

        face_candidates = []
        has_topological_refs = bool(
            getattr(feature, "face_shape_id", None) is not None
            or getattr(feature, "face_index", None) is not None
        )

        def _selector_object():
            if not selector_data:
                return None
            try:
                from modeling.geometric_selector import GeometricFaceSelector
                if isinstance(selector_data, dict):
                    return GeometricFaceSelector.from_dict(selector_data)
                if hasattr(selector_data, "find_best_match"):
                    return selector_data
            except Exception:
                return None
            return None

        selector_obj = _selector_object()

        def _selector_match_score(face_obj) -> float:
            if face_obj is None or selector_obj is None:
                return -1.0
            try:
                if hasattr(selector_obj, "_match_score"):
                    return float(selector_obj._match_score(face_obj))
                best = selector_obj.find_best_match([face_obj])
                return 1.0 if best is not None else 0.0
            except Exception:
                return -1.0

        def _append_candidate(face_obj, source_label: str, method_label: str = "") -> None:
            if face_obj is None:
                return
            for existing in face_candidates:
                if _same_face(existing["face"], face_obj):
                    return
            selector_score = _selector_match_score(face_obj)
            alignment = _normal_alignment(face_obj, selector_normal_hint)
            reliability = 0.5
            if source_label.startswith("shape:"):
                if method_label in {"direct", "history", "brepfeat"}:
                    reliability = 3.0
                elif method_label == "geometric":
                    reliability = 1.6
                else:
                    reliability = 1.2
            elif source_label == "index":
                reliability = 1.1
            elif source_label == "selector":
                reliability = 1.0

            score = reliability
            if alignment >= 0.0:
                score += alignment
            if selector_score >= 0.0:
                score += (2.0 * selector_score)

            face_candidates.append(
                {
                    "face": face_obj,
                    "source": source_label,
                    "method": method_label,
                    "score": score,
                }
            )

        if (
            shape_face is not None
            and index_face is not None
            and not _same_face(shape_face, index_face)
        ):
            # Geometric Shape-Matching ist als Recovery gedacht und kann bei vielen
            # historischen Records eine falsche Face liefern. Wenn ein valider
            # face_index existiert, hat dieser dann Vorrang.
            if shape_method_l == "geometric":
                logger.warning(
                    "BRepFeat Push/Pull: face_shape_id wurde nur geometrisch aufgelöst und "
                    "widerspricht face_index; verwende face_index als Quelle."
                )
                shape_face = None
            else:
                logger.warning(
                    "BRepFeat Push/Pull: face_shape_id und face_index zeigen auf unterschiedliche Faces; "
                    "verwende ShapeID-Referenz und ignoriere face_index."
                )
                index_face = None

        if shape_face is not None:
            _append_candidate(shape_face, f"shape:{shape_method_l or 'resolved'}", shape_method_l)
        if index_face is not None:
            _append_candidate(index_face, "index", "")

        # Self-healing fallback: auch bei vorhandenen topo-Referenzen als letzter Rettungspfad zulassen.
        if selector_obj is not None and hasattr(current_solid, "faces"):
            try:
                selector_face = selector_obj.find_best_match(list(current_solid.faces()))
                _append_candidate(selector_face, "selector", "")
            except Exception as selector_err:
                if is_enabled("tnp_debug_logging"):
                    logger.debug(f"BRepFeat Push/Pull: Selector-Recovery fehlgeschlagen: {selector_err}")

        if not face_candidates:
            raise ValueError("BRepFeat Push/Pull: Zielfläche nicht gefunden (face_shape_id/face_index prüfen)")

        # Stabilität vor Geschwindigkeit: beste Kandidaten zuerst, bei Fehlschlag nächster.
        face_candidates.sort(key=lambda c: c["score"], reverse=True)

        def _normal_for_face(face_obj):
            center_local = face_obj.center()
            face_normal_local = face_obj.normal_at(center_local)
            face_n = np.array([face_normal_local.X, face_normal_local.Y, face_normal_local.Z], dtype=float)
            try:
                from OCP.TopAbs import TopAbs_REVERSED
                if face_obj.wrapped.Orientation() == TopAbs_REVERSED:
                    face_n = -face_n
            except Exception:
                pass
            face_len = np.linalg.norm(face_n)
            if face_len < 1e-9:
                raise ValueError("BRepFeat Push/Pull: Face-Normale ist Null")
            face_n = face_n / face_len

            # Verwende Selector-Normale nur wenn sie zu dieser Face plausibel passt.
            if selector_normal_hint is not None:
                hint = np.array(selector_normal_hint, dtype=float)
                hint_len = np.linalg.norm(hint)
                if hint_len > 1e-9:
                    hint = hint / hint_len
                    if abs(float(np.dot(face_n, hint))) >= 0.6:
                        return hint
            return face_n

        signed_distance = float(getattr(feature, "distance", 0.0) or 0.0) * float(getattr(feature, "direction", 1) or 1)
        abs_dist = abs(signed_distance) if abs(signed_distance) > 1e-9 else abs(float(getattr(feature, "distance", 0.0) or 0.0))
        if abs_dist <= 1e-9:
            raise ValueError("BRepFeat Push/Pull benötigt eine Distanz > 0")

        fuse_mode = 0 if operation == "Cut" else 1

        from OCP.BRepFeat import BRepFeat_MakePrism
        from OCP.gp import gp_Dir
        from build123d import Solid

        shape = current_solid.wrapped if hasattr(current_solid, 'wrapped') else current_solid
        attempt_errors = []

        for candidate in face_candidates:
            candidate_face = candidate["face"]
            face_resolution_source = candidate["source"]
            candidate_method = candidate["method"]
            try:
                normal = _normal_for_face(candidate_face)
                if operation == "Cut":
                    normal = -normal
                elif signed_distance < 0:
                    normal = -normal

                normal_attempts = [("primary", normal)]
                flipped = -normal
                if np.linalg.norm(flipped - normal) > 1e-9:
                    normal_attempts.append(("flipped", flipped))

                candidate_failures = []
                for normal_mode, trial_normal in normal_attempts:
                    try:
                        if is_enabled("tnp_debug_logging"):
                            logger.debug(
                                f"BRepFeat Push/Pull: Face via TNP-v4 aufgelöst "
                                f"(face_index={getattr(feature, 'face_index', None)}, "
                                f"has_shape_id={getattr(feature, 'face_shape_id', None) is not None}, "
                                f"source={face_resolution_source}, shape_method={candidate_method or '-'}, "
                                f"rank={candidate['score']:.3f}, normal_mode={normal_mode})"
                            )

                        face_shape = candidate_face.wrapped if hasattr(candidate_face, 'wrapped') else candidate_face
                        direction = gp_Dir(float(trial_normal[0]), float(trial_normal[1]), float(trial_normal[2]))

                        prism = BRepFeat_MakePrism()
                        prism.Init(shape, face_shape, face_shape, direction, fuse_mode, False)
                        prism.Perform(abs_dist)

                        if not prism.IsDone():
                            raise ValueError("BRepFeat Operation fehlgeschlagen")

                        result_shape = prism.Shape()
                        result_shape = self._unify_same_domain(result_shape, "BRepFeat_MakePrism")
                        result = Solid(result_shape)

                        is_valid = True
                        if hasattr(result, 'is_valid'):
                            try:
                                is_valid = result.is_valid()
                            except Exception as e:
                                logger.debug(f"[__init__.py] Fehler: {e}")
                                is_valid = True

                        has_volume_attr = hasattr(result, 'volume')
                        volume = result.volume if has_volume_attr else 0.0
                        if is_enabled("extrude_debug"):
                            logger.debug(
                                f"[TNP DEBUG BRepFeat] Validation: is_valid={is_valid}, "
                                f"has_volume={has_volume_attr}, volume={volume:.4f}"
                            )

                        if not (is_valid and has_volume_attr and result.volume > 0.001):
                            raise ValueError(
                                f"BRepFeat produzierte ungültiges Ergebnis "
                                f"(valid={is_valid}, vol={getattr(result, 'volume', 0):.4f})"
                            )

                        vol_before = float(getattr(current_solid, "volume", 0.0) or 0.0)
                        vol_after = float(getattr(result, "volume", 0.0) or 0.0)
                        faces_before = len(list(current_solid.faces())) if hasattr(current_solid, "faces") else 0
                        faces_after = len(list(result.faces())) if hasattr(result, "faces") else 0
                        vol_delta = abs(vol_after - vol_before)
                        if vol_delta <= 1e-6 and faces_before == faces_after:
                            raise ValueError(
                                "BRepFeat Push/Pull erzeugte keine Geometrieänderung "
                                "(möglicherweise stale Face-Referenz)"
                            )

                        logger.debug(f"BRepFeat Push/Pull erfolgreich: volume={result.volume:.2f}mm³")

                        _sync_feature_face_refs(candidate_face)

                        # === TNP v4.0: BRepFeat-Operation tracken ===
                        try:
                            if self._document and hasattr(self._document, '_shape_naming_service'):
                                service = self._document._shape_naming_service
                                brepfeat_history = None
                                try:
                                    brepfeat_history = self._build_history_from_make_shape(prism, shape)
                                except Exception as hist_err:
                                    if is_enabled("tnp_debug_logging"):
                                        logger.debug(f"TNP v4.0 BRepFeat History-Extraction fehlgeschlagen: {hist_err}")
                                service.track_brepfeat_operation(
                                    feature_id=feature.id,
                                    source_solid=current_solid,
                                    result_solid=result,
                                    modified_face=candidate_face,
                                    direction=(float(trial_normal[0]), float(trial_normal[1]), float(trial_normal[2])),
                                    distance=abs_dist,
                                    occt_history=brepfeat_history,
                                )
                        except Exception as tnp_e:
                            if is_enabled("tnp_debug_logging"):
                                logger.debug(f"TNP v4.0 BRepFeat Tracking fehlgeschlagen: {tnp_e}")

                        return result
                    except Exception as normal_err:
                        candidate_failures.append(f"{normal_mode}:{normal_err}")
                        continue

                raise ValueError("; ".join(candidate_failures) or "BRepFeat Operation fehlgeschlagen")
            except Exception as candidate_err:
                attempt_errors.append((face_resolution_source, str(candidate_err)))
                if is_enabled("tnp_debug_logging"):
                    logger.debug(
                        f"BRepFeat Push/Pull: Kandidat fehlgeschlagen "
                        f"(source={face_resolution_source}, reason={candidate_err})"
                    )
                continue

        if attempt_errors:
            source_info = "; ".join(f"{src}:{msg}" for src, msg in attempt_errors)
            logger.error(f"BRepFeat Push/Pull fehlgeschlagen nach {len(attempt_errors)} Kandidaten: {source_info}")
            raise ValueError(f"BRepFeat Push/Pull fehlgeschlagen: {source_info}")
        raise ValueError("BRepFeat Push/Pull fehlgeschlagen: keine auswertbaren Kandidaten")

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

    def _create_faces_from_native_circles(self, sketch, plane, profile_selector=None):
        """
        TNP v4.1: Erstellt native OCP Circle Faces aus Sketch-Kreisen.

        Wenn Kreise native_ocp_data haben, werden direkt native OCP Circle Faces
        erstellt (3 Faces statt 14+ durch Polygon-Approximation).

        Args:
            sketch: Sketch-Objekt mit circles Liste
            plane: Build123d Plane für 3D-Konvertierung
            profile_selector: Optional selector for filtering circles

        Returns:
            Liste von build123d Faces aus nativen OCP Circles
        """
        from build123d import Plane as B3DPlane, Wire, make_face, Vector

        faces = []
        circles_with_native_data = [
            c for c in sketch.circles
            if hasattr(c, 'native_ocp_data') and c.native_ocp_data
        ]

        if not circles_with_native_data:
            return []

        logger.info(f"[TNP v4.1] {len(circles_with_native_data)} Kreise mit native_ocp_data gefunden")

        for circle in circles_with_native_data:
            if circle.construction:
                continue  # Konstruktions-Kreise nicht extrudieren

            ocp_data = circle.native_ocp_data
            cx, cy = ocp_data['center']
            radius = ocp_data['radius']

            # Profiler-Selektor Matching (für selektive Extrusion)
            if profile_selector:
                # Selektor enthält Centroids der gewählten Profile
                circle_centroid = (cx, cy)
                if not any(
                    abs(circle_centroid[0] - sel[0]) < 0.1 and
                    abs(circle_centroid[1] - sel[1]) < 0.1
                    for sel in profile_selector
                ):
                    continue  # Circle nicht selektiert

            # WICHTIG: AKTUELLE Plane-Orientation vom Sketch verwenden!
            # Die native_ocp_data['plane'] kann veraltet sein (GUI rotiert die Plane nach dem Hinzufügen)
            origin = Vector(*sketch.plane_origin)
            z_dir = Vector(*sketch.plane_normal)
            x_dir = Vector(*sketch.plane_x_dir)
            y_dir = Vector(*sketch.plane_y_dir)

            # FIX: Wenn y_dir Nullvektor ist (Bug), aus z_dir und x_dir berechnen
            if y_dir.X == 0 and y_dir.Y == 0 and y_dir.Z == 0:
                y_dir = z_dir.cross(x_dir)
                logger.debug(f"[TNP v4.1] y_dir aus z_dir × x_dir berechnet: ({y_dir.X:.1f}, {y_dir.Y:.1f}, {y_dir.Z:.1f})")

            # DEBUG: Plane-Werte loggen
            logger.debug(f"[TNP v4.1] Circle plane: origin=({origin.X:.1f}, {origin.Y:.1f}, {origin.Z:.1f}), "
                        f"x_dir=({x_dir.X:.1f}, {x_dir.Y:.1f}, {x_dir.Z:.1f}), "
                        f"y_dir=({y_dir.X:.1f}, {y_dir.Y:.1f}, {y_dir.Z:.1f})")
            logger.debug(f"[TNP v4.1] Circle 2D center: ({cx:.2f}, {cy:.2f})")

            # Circle-Center in 3D: Origin + (cx, cy) Offset in der Plane
            center_3d = origin + x_dir * cx + y_dir * cy
            logger.debug(f"[TNP v4.1] Circle 3D center: ({center_3d.X:.2f}, {center_3d.Y:.2f}, {center_3d.Z:.2f})")

            # Native OCP Circle erstellen
            # Wire.make_circle() erstellt Circle MIT Center am Plane-Origin
            circle_plane = B3DPlane(origin=center_3d, x_dir=x_dir, z_dir=z_dir)
            circle_wire = Wire.make_circle(radius, circle_plane)
            face = make_face(circle_wire)

            faces.append(face)
            logger.debug(f"[TNP v4.1] Native Circle Face erstellt: r={radius:.2f} at ({cx:.2f}, {cy:.2f})")

        return faces

    def _create_faces_from_native_arcs(self, sketch, plane, profile_selector=None):
        """
        TNP v4.1: Erstellt native OCP Arc Faces aus Sketch-Arcs.

        Arcs benötigen eine besondere Behandlung: Da ein Arc kein geschlossener
        Wire ist, erstellen wir eine planare Face aus Arc + Sehne (chord).
        Bei Extrusion entsteht so ein korrekter Zylinder-Abschnitt.

        Args:
            sketch: Sketch-Objekt mit arcs Liste
            plane: Build123d Plane für 3D-Konvertierung
            profile_selector: Optional selector for filtering arcs

        Returns:
            Liste von build123d Faces aus nativen OCP Arcs
        """
        from build123d import Wire, make_face, Face, Vector
        from OCP.GC import GC_MakeArcOfCircle
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace
        from OCP.gp import gp_Pnt
        from OCP.TopoDS import TopoDS_Edge, TopoDS_Wire, TopoDS_Face

        faces = []
        arcs_with_native_data = [
            a for a in sketch.arcs
            if hasattr(a, 'native_ocp_data') and a.native_ocp_data
        ]

        if not arcs_with_native_data:
            return []

        logger.info(f"[TNP v4.1] {len(arcs_with_native_data)} Arcs mit native_ocp_data gefunden")

        for arc in arcs_with_native_data:
            if arc.construction:
                continue  # Konstruktions-Arcs nicht extrudieren

            ocp_data = arc.native_ocp_data
            cx, cy = ocp_data['center']
            radius = ocp_data['radius']
            start_angle = ocp_data['start_angle']
            end_angle = ocp_data['end_angle']
            plane_data = ocp_data.get('plane', {})

            # Profiler-Selektor Matching
            if profile_selector:
                arc_centroid = (cx, cy)
                if not any(
                    abs(arc_centroid[0] - sel[0]) < 0.1 and
                    abs(arc_centroid[1] - sel[1]) < 0.1
                    for sel in profile_selector
                ):
                    continue

            # WICHTIG: AKTUELLE Plane-Orientation vom Sketch verwenden!
            # Die native_ocp_data['plane'] kann veraltet sein (GUI rotiert die Plane nach dem Hinzufügen)
            origin = Vector(*sketch.plane_origin)
            z_dir = Vector(*sketch.plane_normal)
            x_dir = Vector(*sketch.plane_x_dir)
            y_dir = Vector(*sketch.plane_y_dir)

            # FIX: Wenn y_dir Nullvektor ist (Bug), aus z_dir und x_dir berechnen
            if y_dir.X == 0 and y_dir.Y == 0 and y_dir.Z == 0:
                y_dir = z_dir.cross(x_dir)
                logger.debug(f"[TNP v4.1] Arc y_dir aus z_dir × x_dir berechnet: ({y_dir.X:.1f}, {y_dir.Y:.1f}, {y_dir.Z:.1f})")

            # Arc-Center in 3D
            center_3d = origin + x_dir * cx + y_dir * cy

            # Arc-Parameter in 3D konvertieren
            start_rad = math.radians(start_angle)
            end_rad = math.radians(end_angle)

            # Start- und Endpunkte des Arcs in 3D
            start_3d = center_3d + x_dir * (radius * math.cos(start_rad)) + y_dir * (radius * math.sin(start_rad))
            end_3d = center_3d + x_dir * (radius * math.cos(end_rad)) + y_dir * (radius * math.sin(end_rad))

            # Mittelpunkt für den Arc
            mid_rad = (start_rad + end_rad) / 2
            mid_3d = center_3d + x_dir * (radius * math.cos(mid_rad)) + y_dir * (radius * math.sin(mid_rad))

            # Native OCP Arc Edge erstellen mit GC_MakeArcOfCircle (3 Punkte)
            gp_start = gp_Pnt(start_3d.X, start_3d.Y, start_3d.Z)
            gp_mid = gp_Pnt(mid_3d.X, mid_3d.Y, mid_3d.Z)
            gp_end = gp_Pnt(end_3d.X, end_3d.Y, end_3d.Z)

            arc_maker = GC_MakeArcOfCircle(gp_start, gp_mid, gp_end)
            if arc_maker.IsDone():
                # GC_MakeArcOfCircle.Value() gibt Geom_TrimmedCurve zurück
                # Wir müssen es in TopoDS_Edge wrappen
                arc_geom = arc_maker.Value()
                arc_edge_maker = BRepBuilderAPI_MakeEdge(arc_geom)
                if not arc_edge_maker.IsDone():
                    logger.warning("[TNP v4.1] Arc Edge Maker fehlgeschlagen")
                    continue
                arc_edge = arc_edge_maker.Edge()

                # Sehne (chord) mit OCP direkt erstellen
                chord_maker = BRepBuilderAPI_MakeEdge(gp_start, gp_end)
                if chord_maker.IsDone():
                    chord_edge = chord_maker.Edge()

                    # Wire aus Arc + Sehne mit OCP erstellen
                    wire_maker = BRepBuilderAPI_MakeWire()
                    wire_maker.Add(arc_edge)
                    wire_maker.Add(chord_edge)
                    wire_maker.Build()

                    if wire_maker.IsDone():
                        ocp_wire = wire_maker.Wire()

                        # Face aus Wire erstellen
                        face_maker = BRepBuilderAPI_MakeFace(ocp_wire)
                        if face_maker.IsDone():
                            ocp_face = face_maker.Face()

                            # Zu build123d Face konvertieren (direkt aus TopoDS_Face)
                            face = Face(ocp_face)
                            faces.append(face)
                            logger.debug(f"[TNP v4.1] Native Arc Face erstellt: r={radius:.2f}, {start_angle:.1f}°-{end_angle:.1f}°")
                        else:
                            logger.warning("[TNP v4.1] Face Maker fehlgeschlagen")
                    else:
                        logger.warning("[TNP v4.1] Wire Maker fehlgeschlagen")
                else:
                    logger.warning("[TNP v4.1] Chord Edge Maker fehlgeschlagen")
            else:
                logger.warning(f"[TNP v4.1] Arc Maker fehlgeschlagen für {arc}")

        return faces

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
                "status_message": getattr(feat, "status_message", ""),
                "status_details": getattr(feat, "status_details", {}),
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
                    # TNP v4.0: Push/Pull Face-Referenz
                    "face_index": getattr(feat, "face_index", None),
                    "face_selector": getattr(feat, "face_selector", None),
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
                if getattr(feat, "face_shape_id", None):
                    sid = feat.face_shape_id
                    if hasattr(sid, "uuid"):
                        feat_dict["face_shape_id"] = {
                            "uuid": sid.uuid,
                            "shape_type": sid.shape_type.name,
                            "feature_id": sid.feature_id,
                            "local_index": sid.local_index,
                            "geometry_hash": sid.geometry_hash,
                            "timestamp": sid.timestamp,
                        }
                    elif hasattr(sid, "feature_id") and hasattr(sid, "local_id"):
                        feat_dict["face_shape_id"] = {
                            "feature_id": sid.feature_id,
                            "local_id": sid.local_id,
                            "shape_type": "FACE",
                        }

            elif isinstance(feat, FilletFeature):
                feat_dict.update({
                    "feature_class": "FilletFeature",
                    "radius": feat.radius,
                    "radius_formula": feat.radius_formula,
                    "depends_on_feature_id": feat.depends_on_feature_id,
                })
                if feat.edge_indices:
                    feat_dict["edge_indices"] = list(feat.edge_indices)
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
                    "depends_on_feature_id": feat.depends_on_feature_id,
                })
                if feat.edge_indices:
                    feat_dict["edge_indices"] = list(feat.edge_indices)
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
                    # TNP v4.0: Face-Referenz für Revolve-Push/Pull
                    "face_index": feat.face_index,
                    "face_selector": feat.face_selector,
                })
                # TNP v4.0: ShapeID serialisieren (singular)
                if feat.face_shape_id:
                    if hasattr(feat.face_shape_id, "uuid"):
                        feat_dict["face_shape_id"] = {
                            "uuid": feat.face_shape_id.uuid,
                            "shape_type": feat.face_shape_id.shape_type.name,
                            "feature_id": feat.face_shape_id.feature_id,
                            "local_index": feat.face_shape_id.local_index,
                            "geometry_hash": feat.face_shape_id.geometry_hash,
                            "timestamp": feat.face_shape_id.timestamp
                        }
                    elif hasattr(feat.face_shape_id, "feature_id"):
                        # Legacy-Compatibility
                        feat_dict["face_shape_id"] = {
                            "feature_id": feat.face_shape_id.feature_id,
                            "local_id": getattr(feat.face_shape_id, "local_id", None),
                            "shape_type": feat.face_shape_id.shape_type.name
                        }

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

                # Session-/Legacy-only Pfadfelder nicht persistieren.
                path_data_copy = feat.path_data.copy() if feat.path_data else {}
                for transient_key in ("edge", "build123d_edges", "edge_selector", "path_geometric_selector"):
                    path_data_copy.pop(transient_key, None)
                path_edge_indices = list(path_data_copy.get("edge_indices") or [])
                has_topological_path_refs = bool(feat.path_shape_id or path_edge_indices)
                feat_dict.update({
                    "feature_class": "SweepFeature",
                    "is_frenet": feat.is_frenet,
                    "operation": feat.operation,
                    "twist_angle": feat.twist_angle,
                    "scale_start": feat.scale_start,
                    "scale_end": feat.scale_end,
                    "profile_data": pd_copy,
                    "path_data": path_data_copy,
                    "contact_mode": feat.contact_mode,
                    "profile_face_index": feat.profile_face_index,
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
                if feat.path_geometric_selector and not has_topological_path_refs:
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
                if feat.face_indices:
                    feat_dict["face_indices"] = list(feat.face_indices)
                # TNP v4.0: ShapeIDs vollstaendig serialisieren (inkl. Legacy-Fallback)
                if feat.face_shape_ids:
                    serialized_face_ids = []
                    for sid in feat.face_shape_ids:
                        if hasattr(sid, "uuid"):
                            serialized_face_ids.append({
                                "uuid": sid.uuid,
                                "shape_type": sid.shape_type.name,
                                "feature_id": sid.feature_id,
                                "local_index": sid.local_index,
                                "geometry_hash": sid.geometry_hash,
                                "timestamp": sid.timestamp
                            })
                        elif hasattr(sid, "feature_id") and hasattr(sid, "local_id"):
                            serialized_face_ids.append({
                                "feature_id": sid.feature_id,
                                "local_id": sid.local_id,
                                "shape_type": sid.shape_type.name
                            })
                    if serialized_face_ids:
                        feat_dict["face_shape_ids"] = serialized_face_ids

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
                if feat.face_indices:
                    feat_dict["face_indices"] = list(feat.face_indices)
                # TNP v4.0: ShapeIDs vollstaendig serialisieren
                if feat.face_shape_ids:
                    serialized_face_ids = []
                    for sid in feat.face_shape_ids:
                        if hasattr(sid, "uuid"):
                            serialized_face_ids.append({
                                "uuid": sid.uuid,
                                "shape_type": sid.shape_type.name,
                                "feature_id": sid.feature_id,
                                "local_index": sid.local_index,
                                "geometry_hash": sid.geometry_hash,
                                "timestamp": sid.timestamp
                            })
                        elif hasattr(sid, "feature_id") and hasattr(sid, "local_id"):
                            # Legacy-Compatibility: altes Format beibehalten
                            serialized_face_ids.append({
                                "feature_id": sid.feature_id,
                                "local_id": sid.local_id,
                                "shape_type": sid.shape_type.name
                            })
                    if serialized_face_ids:
                        feat_dict["face_shape_ids"] = serialized_face_ids

            elif isinstance(feat, HollowFeature):
                feat_dict.update({
                    "feature_class": "HollowFeature",
                    "wall_thickness": feat.wall_thickness,
                    "drain_hole": feat.drain_hole,
                    "drain_diameter": feat.drain_diameter,
                    "drain_position": list(feat.drain_position),
                    "drain_direction": list(feat.drain_direction),
                })
                if feat.opening_face_indices:
                    feat_dict["opening_face_indices"] = list(feat.opening_face_indices)

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
                    "cosmetic": feat.cosmetic,
                    "face_index": feat.face_index,
                    "face_selector": feat.face_selector,
                })
                # TNP v4.0: ShapeID serialisieren (inkl. Legacy-Fallback)
                if feat.face_shape_id:
                    sid = feat.face_shape_id
                    if hasattr(sid, "uuid"):
                        feat_dict["face_shape_id"] = {
                            "uuid": sid.uuid,
                            "shape_type": sid.shape_type.name,
                            "feature_id": sid.feature_id,
                            "local_index": sid.local_index,
                            "geometry_hash": sid.geometry_hash,
                            "timestamp": sid.timestamp
                        }
                    elif hasattr(sid, "feature_id") and hasattr(sid, "local_id"):
                        feat_dict["face_shape_id"] = {
                            "feature_id": sid.feature_id,
                            "local_id": sid.local_id,
                            "shape_type": sid.shape_type.name
                        }

            elif isinstance(feat, DraftFeature):
                feat_dict.update({
                    "feature_class": "DraftFeature",
                    "draft_angle": feat.draft_angle,
                    "pull_direction": list(feat.pull_direction),
                    "face_selectors": feat.face_selectors,
                })
                if feat.face_indices:
                    feat_dict["face_indices"] = list(feat.face_indices)
                # TNP v4.0: ShapeIDs vollstaendig serialisieren
                if feat.face_shape_ids:
                    serialized_face_ids = []
                    for sid in feat.face_shape_ids:
                        if hasattr(sid, "uuid"):
                            serialized_face_ids.append({
                                "uuid": sid.uuid,
                                "shape_type": sid.shape_type.name,
                                "feature_id": sid.feature_id,
                                "local_index": sid.local_index,
                                "geometry_hash": sid.geometry_hash,
                                "timestamp": sid.timestamp
                            })
                        elif hasattr(sid, "feature_id") and hasattr(sid, "local_id"):
                            serialized_face_ids.append({
                                "feature_id": sid.feature_id,
                                "local_id": sid.local_id,
                                "shape_type": sid.shape_type.name
                            })
                    if serialized_face_ids:
                        feat_dict["face_shape_ids"] = serialized_face_ids

            elif isinstance(feat, SplitFeature):
                feat_dict.update({
                    "feature_class": "SplitFeature",
                    "plane_origin": list(feat.plane_origin),
                    "plane_normal": list(feat.plane_normal),
                    "keep_side": feat.keep_side,
                })

            elif isinstance(feat, NSidedPatchFeature):
                feat_dict.update({
                    "feature_class": "NSidedPatchFeature",
                    "degree": feat.degree,
                    "tangent": feat.tangent,
                })
                if feat.edge_indices:
                    feat_dict["edge_indices"] = list(feat.edge_indices)
                # TNP v4.0: ShapeIDs und GeometricSelectors serialisieren
                if feat.edge_shape_ids:
                    serialized_edge_ids = []
                    for sid in feat.edge_shape_ids:
                        if hasattr(sid, "uuid"):
                            serialized_edge_ids.append({
                                "uuid": sid.uuid,
                                "shape_type": sid.shape_type.name,
                                "feature_id": sid.feature_id,
                                "local_index": sid.local_index,
                                "geometry_hash": sid.geometry_hash,
                                "timestamp": sid.timestamp
                            })
                        elif hasattr(sid, "feature_id") and hasattr(sid, "local_id"):
                            serialized_edge_ids.append({
                                "feature_id": sid.feature_id,
                                "local_id": sid.local_id,
                                "shape_type": sid.shape_type.name
                            })
                    if serialized_edge_ids:
                        feat_dict["edge_shape_ids"] = serialized_edge_ids
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
                if feat.face_indices:
                    feat_dict["face_indices"] = list(feat.face_indices)
                # TNP v4.0: ShapeIDs serialisieren (inkl. Legacy-Fallback)
                if feat.face_shape_ids:
                    serialized_face_ids = []
                    for sid in feat.face_shape_ids:
                        if hasattr(sid, "uuid"):
                            serialized_face_ids.append({
                                "uuid": sid.uuid,
                                "shape_type": sid.shape_type.name,
                                "feature_id": sid.feature_id,
                                "local_index": sid.local_index,
                                "geometry_hash": sid.geometry_hash,
                                "timestamp": sid.timestamp
                            })
                        elif hasattr(sid, "feature_id") and hasattr(sid, "local_id"):
                            serialized_face_ids.append({
                                "feature_id": sid.feature_id,
                                "local_id": sid.local_id,
                                "shape_type": sid.shape_type.name
                            })
                    if serialized_face_ids:
                        feat_dict["face_shape_ids"] = serialized_face_ids

            elif isinstance(feat, TransformFeature):
                feat_dict.update({
                    "feature_class": "TransformFeature",
                    "mode": feat.mode,
                    "data": feat.data,
                })

            elif isinstance(feat, BooleanFeature):
                feat_dict.update({
                    "feature_class": "BooleanFeature",
                    "operation": feat.operation,
                    "tool_body_id": feat.tool_body_id,
                    "tool_solid_data": feat.tool_solid_data,
                    "fuzzy_tolerance": feat.fuzzy_tolerance,
                    "expected_volume_change": feat.expected_volume_change,
                })
                # TNP v4.0: ShapeIDs serialisieren
                if feat.modified_shape_ids:
                    feat_dict["modified_shape_ids"] = [
                        {
                            "uuid": sid.uuid,
                            "shape_type": sid.shape_type.name,
                            "feature_id": sid.feature_id,
                            "local_index": sid.local_index,
                            "geometry_hash": sid.geometry_hash,
                            "timestamp": sid.timestamp
                        }
                        for sid in feat.modified_shape_ids
                    ]

            elif isinstance(feat, PushPullFeature):
                feat_dict.update({
                    "feature_class": "PushPullFeature",
                    "distance": feat.distance,
                    "distance_formula": feat.distance_formula,
                    "direction": feat.direction,
                    "operation": feat.operation,
                    "face_index": feat.face_index,
                    "face_selector": feat.face_selector,
                    "plane_origin": list(feat.plane_origin) if feat.plane_origin else None,
                    "plane_normal": list(feat.plane_normal) if feat.plane_normal else None,
                    "plane_x_dir": list(feat.plane_x_dir) if feat.plane_x_dir else None,
                    "plane_y_dir": list(feat.plane_y_dir) if feat.plane_y_dir else None,
                })
                # Face-BREP für nicht-planare Faces
                if feat.face_brep:
                    feat_dict["face_brep"] = feat.face_brep
                    feat_dict["face_type"] = feat.face_type
                # Precalculated Polygons (Fallback)
                if feat.precalculated_polys:
                    try:
                        feat_dict["precalculated_polys_wkt"] = [
                            p.wkt if hasattr(p, 'wkt') else str(p)
                            for p in feat.precalculated_polys
                        ]
                    except Exception:
                        pass
                # TNP v4.0: ShapeID serialisieren
                if feat.face_shape_id and hasattr(feat.face_shape_id, "uuid"):
                    sid = feat.face_shape_id
                    feat_dict["face_shape_id"] = {
                        "uuid": sid.uuid,
                        "shape_type": sid.shape_type.name,
                        "feature_id": sid.feature_id,
                        "local_index": sid.local_index,
                        "geometry_hash": sid.geometry_hash,
                        "timestamp": sid.timestamp
                    }

            elif isinstance(feat, PatternFeature):
                feat_dict.update({
                    "feature_class": "PatternFeature",
                    "pattern_type": feat.pattern_type,
                    "feature_id": feat.feature_id,
                    "count": feat.count,
                    "spacing": feat.spacing,
                    "direction_1": list(feat.direction_1),
                    "direction_2": list(feat.direction_2) if feat.direction_2 else None,
                    "count_2": feat.count_2,
                    "axis_origin": list(feat.axis_origin),
                    "axis_direction": list(feat.axis_direction),
                    "angle": feat.angle,
                    "mirror_plane": feat.mirror_plane,
                    "mirror_origin": list(feat.mirror_origin),
                    "mirror_normal": list(feat.mirror_normal),
                })

            elif isinstance(feat, PrimitiveFeature):
                feat_dict.update({
                    "feature_class": "PrimitiveFeature",
                    "primitive_type": feat.primitive_type,
                    "length": feat.length,
                    "width": feat.width,
                    "height": feat.height,
                    "radius": feat.radius,
                    "bottom_radius": feat.bottom_radius,
                    "top_radius": feat.top_radius,
                })

            elif isinstance(feat, ImportFeature):
                feat_dict.update({
                    "feature_class": "ImportFeature",
                    "brep_string": feat.brep_string,
                    "source_file": feat.source_file,
                    "source_type": feat.source_type,
                })

            features_data.append(feat_dict)

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
            "brep": brep_string,
            "version": "9.1",
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
                "status_message": feat_dict.get("status_message", ""),
                "status_details": feat_dict.get("status_details", {}),
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
                    face_index=feat_dict.get("face_index"),
                    face_selector=feat_dict.get("face_selector"),
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
                if "face_shape_id" in feat_dict:
                    from modeling.tnp_system import ShapeID, ShapeType

                    sid_data = feat_dict["face_shape_id"]
                    if isinstance(sid_data, dict):
                        shape_type = ShapeType[sid_data.get("shape_type", "FACE")]
                        local_index = int(sid_data.get("local_index", sid_data.get("local_id", 0)))
                        if sid_data.get("uuid"):
                            feat.face_shape_id = ShapeID(
                                uuid=sid_data.get("uuid", ""),
                                shape_type=shape_type,
                                feature_id=sid_data.get("feature_id", ""),
                                local_index=local_index,
                                geometry_hash=sid_data.get("geometry_hash", f"legacy_extrude_face_{local_index}"),
                                timestamp=sid_data.get("timestamp", 0.0),
                            )
                        else:
                            feat.face_shape_id = ShapeID.create(
                                shape_type=shape_type,
                                feature_id=sid_data.get("feature_id", feat_dict.get("id", feat.id)),
                                local_index=local_index,
                                geometry_data=("legacy_extrude_face", feat_dict.get("id", feat.id), local_index),
                            )

            elif feat_class == "FilletFeature":
                legacy_edge_selectors = feat_dict.get("edge_selectors")
                feat = FilletFeature(
                    radius=feat_dict.get("radius", 2.0),
                    edge_indices=feat_dict.get("edge_indices", []),
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
                if not feat.geometric_selectors and legacy_edge_selectors:
                    feat.geometric_selectors = cls._convert_legacy_edge_selectors(legacy_edge_selectors)

            elif feat_class == "ChamferFeature":
                legacy_edge_selectors = feat_dict.get("edge_selectors")
                feat = ChamferFeature(
                    distance=feat_dict.get("distance", 2.0),
                    edge_indices=feat_dict.get("edge_indices", []),
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
                if not feat.geometric_selectors and legacy_edge_selectors:
                    feat.geometric_selectors = cls._convert_legacy_edge_selectors(legacy_edge_selectors)

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
                # TNP v4.0: Face-Referenz laden
                feat.face_index = feat_dict.get("face_index")
                feat.face_selector = feat_dict.get("face_selector")
                if "face_shape_id" in feat_dict and feat_dict["face_shape_id"]:
                    sid_data = feat_dict["face_shape_id"]
                    # ShapeID aus dict rekonstruieren
                    from modeling.tnp_system import ShapeID, ShapeType
                    if "uuid" in sid_data:
                        feat.face_shape_id = ShapeID(
                            uuid=sid_data["uuid"],
                            shape_type=ShapeType[sid_data["shape_type"]],
                            feature_id=sid_data["feature_id"],
                            local_index=sid_data["local_index"],
                            geometry_hash=sid_data.get("geometry_hash"),
                            timestamp=sid_data.get("timestamp")
                        )
                    else:
                        # Legacy-Format
                        feat.face_shape_id = ShapeID(
                            shape_type=ShapeType[sid_data["shape_type"]],
                            feature_id=sid_data["feature_id"],
                            local_index=sid_data.get("local_id", sid_data.get("local_index", 0)),
                            geometry_data=None
                        )

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
                    profile_face_index=feat_dict.get("profile_face_index"),
                    contact_mode=feat_dict.get("contact_mode", "keep"),
                    **base_kwargs
                )
                if feat.profile_face_index is None and isinstance(profile_data, dict):
                    raw_profile_idx = profile_data.get("face_index")
                    if raw_profile_idx is None:
                        raw_profile_idx = profile_data.get("ocp_face_id")
                    try:
                        profile_idx = int(raw_profile_idx)
                        if profile_idx >= 0:
                            feat.profile_face_index = profile_idx
                    except Exception:
                        pass
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
                # Legacy/Session-Fallback: Selector evtl. noch in path_data gespeichert.
                if feat.path_geometric_selector is None and isinstance(feat.path_data, dict):
                    sel_data = feat.path_data.get("path_geometric_selector")
                    if isinstance(sel_data, dict):
                        feat.path_geometric_selector = GeometricEdgeSelector(**sel_data)
                # Gemischte Strategien vermeiden: alte edge_selector-Felder nur als Legacy-Lesehilfe.
                if isinstance(feat.path_data, dict):
                    feat.path_data.pop("path_geometric_selector", None)
                    feat.path_data.pop("edge_selector", None)
                has_topological_profile_refs = bool(
                    feat.profile_shape_id is not None
                    or feat.profile_face_index is not None
                )
                if has_topological_profile_refs:
                    feat.profile_geometric_selector = None
                has_topological_path_refs = bool(feat.path_shape_id)
                if isinstance(feat.path_data, dict) and feat.path_data.get("edge_indices"):
                    has_topological_path_refs = True
                if has_topological_path_refs:
                    feat.path_geometric_selector = None

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
                    face_indices=feat_dict.get("face_indices", []),
                    **base_kwargs
                )
                feat.thickness_formula = feat_dict.get("thickness_formula")
                # TNP v4.0: ShapeIDs deserialisieren (inkl. Legacy-Fallback)
                if "face_shape_ids" in feat_dict:
                    from modeling.tnp_system import ShapeID, ShapeType
                    feat.face_shape_ids = []
                    for idx, sid_data in enumerate(feat_dict["face_shape_ids"]):
                        if isinstance(sid_data, dict):
                            shape_type = ShapeType[sid_data.get("shape_type", "FACE")]
                            local_index = int(sid_data.get("local_index", sid_data.get("local_id", idx)))
                            if sid_data.get("uuid"):
                                feat.face_shape_ids.append(ShapeID(
                                    uuid=sid_data.get("uuid", ""),
                                    shape_type=shape_type,
                                    feature_id=sid_data.get("feature_id", ""),
                                    local_index=local_index,
                                    geometry_hash=sid_data.get("geometry_hash", f"legacy_shell_face_{local_index}"),
                                    timestamp=sid_data.get("timestamp", 0.0)
                                ))
                            else:
                                feat.face_shape_ids.append(ShapeID.create(
                                    shape_type=shape_type,
                                    feature_id=sid_data.get("feature_id", feat_dict.get("id", feat.id)),
                                    local_index=local_index,
                                    geometry_data=("legacy_shell_face", feat_dict.get("id", feat.id), local_index)
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
                    face_indices=feat_dict.get("face_indices", []),
                    position=tuple(feat_dict.get("position", (0, 0, 0))),
                    direction=tuple(feat_dict.get("direction", (0, 0, -1))),
                    counterbore_diameter=feat_dict.get("counterbore_diameter", 12.0),
                    counterbore_depth=feat_dict.get("counterbore_depth", 3.0),
                    countersink_angle=feat_dict.get("countersink_angle", 82.0),
                    **base_kwargs
                )
                feat.diameter_formula = feat_dict.get("diameter_formula")
                feat.depth_formula = feat_dict.get("depth_formula")
                # TNP v4.0: ShapeIDs deserialisieren (inkl. Legacy-Fallback)
                if "face_shape_ids" in feat_dict:
                    from modeling.tnp_system import ShapeID, ShapeType
                    feat.face_shape_ids = []
                    for idx, sid_data in enumerate(feat_dict["face_shape_ids"]):
                        if isinstance(sid_data, dict):
                            shape_type = ShapeType[sid_data.get("shape_type", "FACE")]
                            local_index = int(sid_data.get("local_index", sid_data.get("local_id", idx)))
                            if sid_data.get("uuid"):
                                feat.face_shape_ids.append(ShapeID(
                                    uuid=sid_data.get("uuid", ""),
                                    shape_type=shape_type,
                                    feature_id=sid_data.get("feature_id", ""),
                                    local_index=local_index,
                                    geometry_hash=sid_data.get("geometry_hash", f"legacy_face_{local_index}"),
                                    timestamp=sid_data.get("timestamp", 0.0)
                                ))
                            else:
                                # Legacy-Datei ohne uuid/local_index
                                feat.face_shape_ids.append(ShapeID.create(
                                    shape_type=shape_type,
                                    feature_id=sid_data.get("feature_id", feat_dict.get("id", feat.id)),
                                    local_index=local_index,
                                    geometry_data=("legacy_face", feat_dict.get("id", feat.id), local_index)
                                ))

            elif feat_class == "HollowFeature":
                feat = HollowFeature(
                    wall_thickness=feat_dict.get("wall_thickness", 2.0),
                    drain_hole=feat_dict.get("drain_hole", False),
                    drain_diameter=feat_dict.get("drain_diameter", 3.0),
                    drain_position=tuple(feat_dict.get("drain_position", [0, 0, 0])),
                    drain_direction=tuple(feat_dict.get("drain_direction", [0, 0, -1])),
                    opening_face_indices=feat_dict.get("opening_face_indices", []),
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
                feat = PushPullFeature(
                    distance=feat_dict.get("distance", 10.0),
                    distance_formula=feat_dict.get("distance_formula"),
                    direction=feat_dict.get("direction", 1),
                    operation=feat_dict.get("operation", "Join"),
                    face_index=feat_dict.get("face_index"),
                    face_selector=feat_dict.get("face_selector"),
                    plane_origin=tuple(feat_dict.get("plane_origin", (0, 0, 0))) if feat_dict.get("plane_origin") else (0, 0, 0),
                    plane_normal=tuple(feat_dict.get("plane_normal", (0, 0, 1))) if feat_dict.get("plane_normal") else (0, 0, 1),
                    plane_x_dir=tuple(feat_dict["plane_x_dir"]) if feat_dict.get("plane_x_dir") else None,
                    plane_y_dir=tuple(feat_dict["plane_y_dir"]) if feat_dict.get("plane_y_dir") else None,
                    **base_kwargs
                )
                # Face-BREP für nicht-planare Faces
                if "face_brep" in feat_dict:
                    feat.face_brep = feat_dict["face_brep"]
                    feat.face_type = feat_dict.get("face_type")
                # Precalculated Polygons (Fallback)
                if "precalculated_polys_wkt" in feat_dict:
                    try:
                        from shapely import wkt
                        feat.precalculated_polys = [
                            wkt.loads(w) for w in feat_dict["precalculated_polys_wkt"]
                        ]
                    except Exception:
                        pass
                # TNP v4.0: ShapeID deserialisieren
                if "face_shape_id" in feat_dict:
                    from modeling.tnp_system import ShapeID, ShapeType
                    sid_data = feat_dict["face_shape_id"]
                    if isinstance(sid_data, dict):
                        shape_type = ShapeType[sid_data.get("shape_type", "FACE")]
                        local_index = int(sid_data.get("local_index", sid_data.get("local_id", 0)))
                        if sid_data.get("uuid"):
                            feat.face_shape_id = ShapeID(
                                uuid=sid_data.get("uuid", ""),
                                shape_type=shape_type,
                                feature_id=sid_data.get("feature_id", ""),
                                local_index=local_index,
                                geometry_hash=sid_data.get("geometry_hash", f"legacy_pushpull_face_{local_index}"),
                                timestamp=sid_data.get("timestamp", 0.0),
                            )
                        else:
                            feat.face_shape_id = ShapeID.create(
                                shape_type=shape_type,
                                feature_id=sid_data.get("feature_id", feat_dict.get("id", feat.id)),
                                local_index=local_index,
                                geometry_data=("legacy_pushpull_face", feat_dict.get("id", feat.id), local_index),
                            )

            elif feat_class == "PatternFeature":
                feat = PatternFeature(
                    pattern_type=feat_dict.get("pattern_type", "Linear"),
                    feature_id=feat_dict.get("feature_id"),
                    count=feat_dict.get("count", 2),
                    spacing=feat_dict.get("spacing", 10.0),
                    direction_1=tuple(feat_dict.get("direction_1", (1, 0, 0))),
                    direction_2=tuple(feat_dict["direction_2"]) if feat_dict.get("direction_2") else None,
                    count_2=feat_dict.get("count_2"),
                    axis_origin=tuple(feat_dict.get("axis_origin", (0, 0, 0))),
                    axis_direction=tuple(feat_dict.get("axis_direction", (0, 0, 1))),
                    angle=feat_dict.get("angle", 360.0),
                    mirror_plane=feat_dict.get("mirror_plane"),
                    mirror_origin=tuple(feat_dict.get("mirror_origin", (0, 0, 0))),
                    mirror_normal=tuple(feat_dict.get("mirror_normal", (0, 0, 1))),
                    **base_kwargs
                )

            elif feat_class == "NSidedPatchFeature":
                legacy_edge_selectors = feat_dict.get("edge_selectors", [])
                feat = NSidedPatchFeature(
                    edge_indices=feat_dict.get("edge_indices", []),
                    degree=feat_dict.get("degree", 3),
                    tangent=feat_dict.get("tangent", True),
                    **base_kwargs
                )
                # TNP v4.0: ShapeIDs und GeometricSelectors deserialisieren
                if "edge_shape_ids" in feat_dict:
                    from modeling.tnp_system import ShapeID, ShapeType
                    feat.edge_shape_ids = []
                    for idx, sid_data in enumerate(feat_dict["edge_shape_ids"]):
                        if isinstance(sid_data, dict):
                            shape_type = ShapeType[sid_data.get("shape_type", "EDGE")]
                            local_index = int(sid_data.get("local_index", sid_data.get("local_id", idx)))
                            if sid_data.get("uuid"):
                                feat.edge_shape_ids.append(ShapeID(
                                    uuid=sid_data.get("uuid", ""),
                                    shape_type=shape_type,
                                    feature_id=sid_data.get("feature_id", ""),
                                    local_index=local_index,
                                    geometry_hash=sid_data.get("geometry_hash", f"legacy_edge_{local_index}"),
                                    timestamp=sid_data.get("timestamp", 0.0)
                                ))
                            else:
                                feat.edge_shape_ids.append(ShapeID.create(
                                    shape_type=shape_type,
                                    feature_id=sid_data.get("feature_id", feat_dict.get("id", feat.id)),
                                    local_index=local_index,
                                    geometry_data=("legacy_edge", feat_dict.get("id", feat.id), local_index)
                                ))
                if "geometric_selectors" in feat_dict:
                    from modeling.geometric_selector import GeometricEdgeSelector
                    feat.geometric_selectors = [
                        GeometricEdgeSelector.from_dict(gs) if isinstance(gs, dict) else gs
                        for gs in feat_dict["geometric_selectors"]
                    ]
                elif legacy_edge_selectors:
                    feat.geometric_selectors = cls._convert_legacy_nsided_edge_selectors(legacy_edge_selectors)

            elif feat_class == "SurfaceTextureFeature":
                feat = SurfaceTextureFeature(
                    texture_type=feat_dict.get("texture_type", "ripple"),
                    face_indices=feat_dict.get("face_indices", []),
                    face_selectors=feat_dict.get("face_selectors", []),
                    scale=feat_dict.get("scale", 1.0),
                    depth=feat_dict.get("depth", 0.5),
                    rotation=feat_dict.get("rotation", 0.0),
                    invert=feat_dict.get("invert", False),
                    type_params=feat_dict.get("type_params", {}),
                    export_subdivisions=feat_dict.get("export_subdivisions", 2),
                    **base_kwargs
                )
                # TNP v4.0: ShapeIDs deserialisieren (inkl. Legacy-Fallback)
                if "face_shape_ids" in feat_dict:
                    from modeling.tnp_system import ShapeID, ShapeType
                    feat.face_shape_ids = []
                    for idx, sid_data in enumerate(feat_dict["face_shape_ids"]):
                        if isinstance(sid_data, dict):
                            shape_type = ShapeType[sid_data.get("shape_type", "FACE")]
                            local_index = int(sid_data.get("local_index", sid_data.get("local_id", idx)))
                            if sid_data.get("uuid"):
                                feat.face_shape_ids.append(ShapeID(
                                    uuid=sid_data.get("uuid", ""),
                                    shape_type=shape_type,
                                    feature_id=sid_data.get("feature_id", ""),
                                    local_index=local_index,
                                    geometry_hash=sid_data.get("geometry_hash", f"legacy_texture_face_{local_index}"),
                                    timestamp=sid_data.get("timestamp", 0.0)
                                ))
                            else:
                                feat.face_shape_ids.append(ShapeID.create(
                                    shape_type=shape_type,
                                    feature_id=sid_data.get("feature_id", feat_dict.get("id", feat.id)),
                                    local_index=local_index,
                                    geometry_data=("legacy_texture_face", feat_dict.get("id", feat.id), local_index)
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
                    cosmetic=feat_dict.get("cosmetic", True),
                    face_index=feat_dict.get("face_index"),
                    face_selector=feat_dict.get("face_selector"),
                    **base_kwargs
                )
                # TNP v4.0: ShapeID deserialisieren (inkl. Legacy-Fallback)
                if "face_shape_id" in feat_dict:
                    from modeling.tnp_system import ShapeID, ShapeType
                    sid_data = feat_dict["face_shape_id"]
                    if isinstance(sid_data, dict):
                        shape_type = ShapeType[sid_data.get("shape_type", "FACE")]
                        local_index = int(sid_data.get("local_index", sid_data.get("local_id", 0)))
                        if sid_data.get("uuid"):
                            feat.face_shape_id = ShapeID(
                                uuid=sid_data.get("uuid", ""),
                                shape_type=shape_type,
                                feature_id=sid_data.get("feature_id", ""),
                                local_index=local_index,
                                geometry_hash=sid_data.get("geometry_hash", f"legacy_thread_face_{local_index}"),
                                timestamp=sid_data.get("timestamp", 0.0)
                            )
                        else:
                            feat.face_shape_id = ShapeID.create(
                                shape_type=shape_type,
                                feature_id=sid_data.get("feature_id", feat_dict.get("id", feat.id)),
                                local_index=local_index,
                                geometry_data=("legacy_thread_face", feat_dict.get("id", feat.id), local_index)
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
                    face_indices=feat_dict.get("face_indices", []),
                    **base_kwargs
                )
                # TNP v4.0: ShapeIDs deserialisieren (inkl. Legacy-Fallback)
                if "face_shape_ids" in feat_dict:
                    from modeling.tnp_system import ShapeID, ShapeType
                    feat.face_shape_ids = []
                    for idx, sid_data in enumerate(feat_dict["face_shape_ids"]):
                        if isinstance(sid_data, dict):
                            shape_type = ShapeType[sid_data.get("shape_type", "FACE")]
                            local_index = int(sid_data.get("local_index", sid_data.get("local_id", idx)))
                            if sid_data.get("uuid"):
                                feat.face_shape_ids.append(ShapeID(
                                    uuid=sid_data.get("uuid", ""),
                                    shape_type=shape_type,
                                    feature_id=sid_data.get("feature_id", ""),
                                    local_index=local_index,
                                    geometry_hash=sid_data.get("geometry_hash", f"legacy_face_{local_index}"),
                                    timestamp=sid_data.get("timestamp", 0.0)
                                ))
                            else:
                                feat.face_shape_ids.append(ShapeID.create(
                                    shape_type=shape_type,
                                    feature_id=sid_data.get("feature_id", feat_dict.get("id", feat.id)),
                                    local_index=local_index,
                                    geometry_data=("legacy_face", feat_dict.get("id", feat.id), local_index)
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

            elif feat_class == "BooleanFeature":
                feat = BooleanFeature(
                    operation=feat_dict.get("operation", "Cut"),
                    tool_body_id=feat_dict.get("tool_body_id"),
                    tool_solid_data=feat_dict.get("tool_solid_data"),
                    fuzzy_tolerance=feat_dict.get("fuzzy_tolerance"),
                    expected_volume_change=feat_dict.get("expected_volume_change"),
                    **base_kwargs
                )
                # TNP v4.0: ShapeIDs deserialisieren
                if "modified_shape_ids" in feat_dict:
                    from modeling.tnp_system import ShapeID, ShapeType
                    feat.modified_shape_ids = []
                    for sid_data in feat_dict["modified_shape_ids"]:
                        if isinstance(sid_data, dict):
                            shape_type = ShapeType[sid_data.get("shape_type", "FACE")]
                            feat.modified_shape_ids.append(ShapeID(
                                uuid=sid_data.get("uuid", ""),
                                shape_type=shape_type,
                                feature_id=sid_data.get("feature_id", ""),
                                local_index=sid_data.get("local_index", 0),
                                geometry_hash=sid_data.get("geometry_hash", ""),
                                timestamp=sid_data.get("timestamp", 0.0)
                            ))

            elif feat_class == "PrimitiveFeature":
                feat = PrimitiveFeature(
                    primitive_type=feat_dict.get("primitive_type", "box"),
                    length=feat_dict.get("length", 10.0),
                    width=feat_dict.get("width", 10.0),
                    height=feat_dict.get("height", 10.0),
                    radius=feat_dict.get("radius", 5.0),
                    bottom_radius=feat_dict.get("bottom_radius", 5.0),
                    top_radius=feat_dict.get("top_radius", 0.0),
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
        self.add_body(b, set_active=True)
        return b

    def add_body(self, body: Body, component: Component = None, set_active: bool = False):
        """Fügt einen Body dem Dokument hinzu und setzt die Document-Referenz."""
        if body is None:
            return None

        body._document = self

        if self._assembly_enabled:
            target = component or self._active_component or self.root_component
            if target and body not in target.bodies:
                target.bodies.append(body)
        else:
            if body not in self._bodies:
                self._bodies.append(body)

        if set_active:
            self.active_body = body

        return body

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
        self.add_body(body_above, set_active=False)
        self.add_body(body_below, set_active=False)

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
            body = Body(name=f"Imported_{i+1}", document=self)
            body._build123d_solid = solid
            body._update_mesh_from_solid(solid)

            self.add_body(body, set_active=False)
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

        Persistiert immer im Component-basierten Format (v9+).

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

        root_component_data = self._build_root_component_payload()
        active_component_id = self._active_component.id if self._active_component else root_component_data.get("id")

        return {
            "version": "9.1",
            "name": self.name,
            "parameters": params_data,
            "assembly_enabled": True,
            "root_component": root_component_data,
            "active_component_id": active_component_id,
            "active_body_id": self.active_body.id if self.active_body else None,
            "active_sketch_id": self.active_sketch.id if self.active_sketch else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Document':
        """
        Deserialisiert Dokument aus Dictionary.

        Lädt primär Component-Format (v9+). Flat-Format-Daten werden
        on-the-fly in eine Root-Component migriert.

        Args:
            data: Dictionary mit Dokument-Daten

        Returns:
            Neues Document-Objekt
        """
        doc = cls(name=data.get("name", "Imported"))
        version = data.get("version", "unknown")

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

        payload = dict(data)
        if "root_component" not in payload:
            payload["root_component"] = cls._migrate_flat_document_payload(data)
            payload["assembly_enabled"] = True
            payload.setdefault("active_component_id", payload["root_component"].get("id"))
            logger.info(f"[MIGRATION] Flat-Format v{version} zu Root-Component migriert")

        stripped_legacy, converted_legacy = cls._migrate_legacy_nsided_payload(payload)
        if stripped_legacy > 0:
            logger.info(
                f"[MIGRATION] NSided legacy edge_selectors entfernt: {stripped_legacy} "
                f"(zu geometric_selectors konvertiert: {converted_legacy})"
            )

        logger.info(f"[ASSEMBLY] Lade Component-Format v{version}")
        doc._load_assembly_format(payload)

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
        else:
            self.root_component = Component(name="Root")

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

        # Bodies an Document anbinden (TNP v4.0)
        self._attach_document_to_bodies()

    def _build_root_component_payload(self) -> dict:
        """
        Liefert serialisierbare Root-Component-Daten.

        Wenn Assembly aktiv ist, wird die bestehende Root-Component genutzt.
        Andernfalls werden die flachen Dokumentlisten in eine Root-Component
        gemappt (ohne Legacy-Format zu schreiben).
        """
        if self._assembly_enabled and self.root_component:
            return self.root_component.to_dict()

        return {
            "id": "root",
            "name": "Root",
            "position": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
            "visible": True,
            "is_active": True,
            "expanded": True,
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
            "sub_components": [],
        }

    @staticmethod
    def _migrate_flat_document_payload(data: dict) -> dict:
        """
        Migriert altes Flat-Dokumentformat in eine Root-Component-Struktur.
        """
        return {
            "id": "root",
            "name": "Root",
            "position": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
            "visible": True,
            "is_active": True,
            "expanded": True,
            "bodies": data.get("bodies", []),
            "sketches": data.get("sketches", []),
            "planes": data.get("planes", []),
            "sub_components": [],
        }

    @staticmethod
    def _iter_component_payloads(component_data: dict):
        """Iteriert rekursiv über Component-Dicts eines Payloads."""
        if not isinstance(component_data, dict):
            return
        yield component_data
        for sub in component_data.get("sub_components", []) or []:
            yield from Document._iter_component_payloads(sub)

    @staticmethod
    def _migrate_legacy_nsided_payload(payload: dict) -> Tuple[int, int]:
        """
        Entfernt legacy NSided edge_selectors aus dem Payload und konvertiert sie.

        Returns:
            (stripped_count, converted_count)
        """
        root = payload.get("root_component")
        if not isinstance(root, dict):
            return 0, 0

        stripped_count = 0
        converted_count = 0

        for comp in Document._iter_component_payloads(root):
            for body_data in comp.get("bodies", []) or []:
                for feat_data in body_data.get("features", []) or []:
                    if feat_data.get("feature_class") != "NSidedPatchFeature":
                        continue

                    legacy = feat_data.pop("edge_selectors", None)
                    if legacy is None:
                        continue
                    stripped_count += 1

                    has_modern_refs = bool(
                        feat_data.get("edge_indices")
                        or feat_data.get("edge_shape_ids")
                        or feat_data.get("geometric_selectors")
                    )
                    if has_modern_refs:
                        continue

                    migrated_geo = Body._convert_legacy_nsided_edge_selectors(legacy)
                    if migrated_geo:
                        feat_data["geometric_selectors"] = migrated_geo
                        converted_count += 1

        return stripped_count, converted_count

    def _attach_document_to_bodies(self):
        """Stellt sicher, dass alle Bodies eine Document-Referenz haben."""
        for body in self.get_all_bodies():
            body._document = self

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

    def _migrate_loaded_nsided_features_to_indices(self) -> int:
        """
        Einmalige Laufzeitmigration: NSided-Features auf edge_indices/ShapeIDs heben.

        Nutzt vorhandene geometric_selectors und das aktuelle Body-Solid, um
        stabile Kanten-Indizes + ShapeIDs zu persistieren.
        """
        migrated_features = 0

        def _is_same_edge(edge_a, edge_b) -> bool:
            try:
                wa = edge_a.wrapped if hasattr(edge_a, "wrapped") else edge_a
                wb = edge_b.wrapped if hasattr(edge_b, "wrapped") else edge_b
                return wa.IsSame(wb)
            except Exception:
                return edge_a is edge_b

        try:
            from modeling.geometric_selector import GeometricEdgeSelector
            from modeling.tnp_system import ShapeType
        except Exception:
            return 0

        shape_service = getattr(self, "_shape_naming_service", None)

        for body in self.get_all_bodies():
            solid = getattr(body, "_build123d_solid", None)
            if solid is None or not hasattr(solid, "edges"):
                continue

            all_edges = list(solid.edges())
            if not all_edges:
                continue

            for feature in body.features:
                if not isinstance(feature, NSidedPatchFeature):
                    continue

                if feature.edge_indices and feature.edge_shape_ids:
                    continue

                selectors = feature.geometric_selectors or []
                if not selectors:
                    continue

                resolved_edges = []
                for sel_data in selectors:
                    try:
                        geo_sel = (
                            GeometricEdgeSelector.from_dict(sel_data)
                            if isinstance(sel_data, dict)
                            else sel_data
                        )
                        if not hasattr(geo_sel, "find_best_match"):
                            continue
                        edge = geo_sel.find_best_match(all_edges)
                        if edge is None:
                            continue
                        if any(_is_same_edge(edge, existing) for existing in resolved_edges):
                            continue
                        resolved_edges.append(edge)
                    except Exception:
                        continue

                if len(resolved_edges) < 3:
                    continue

                resolved_indices = []
                for edge in resolved_edges:
                    match_idx = None
                    for i, candidate in enumerate(all_edges):
                        if _is_same_edge(candidate, edge):
                            match_idx = i
                            break
                    if match_idx is not None and match_idx not in resolved_indices:
                        resolved_indices.append(match_idx)

                if len(resolved_indices) < 3:
                    continue

                changed = False
                if feature.edge_indices != resolved_indices:
                    feature.edge_indices = resolved_indices
                    changed = True

                try:
                    canonical_selectors = [
                        GeometricEdgeSelector.from_edge(edge).to_dict()
                        for edge in resolved_edges
                    ]
                    if canonical_selectors:
                        feature.geometric_selectors = canonical_selectors
                        changed = True
                except Exception:
                    pass

                if shape_service:
                    migrated_shape_ids = []
                    for local_idx, edge in enumerate(resolved_edges):
                        try:
                            shape_id = shape_service.find_shape_id_by_edge(edge)
                            if shape_id is None and hasattr(edge, "wrapped"):
                                ec = edge.center()
                                edge_len = edge.length if hasattr(edge, "length") else 0.0
                                shape_id = shape_service.register_shape(
                                    ocp_shape=edge.wrapped,
                                    shape_type=ShapeType.EDGE,
                                    feature_id=feature.id,
                                    local_index=local_idx,
                                    geometry_data=(ec.X, ec.Y, ec.Z, edge_len),
                                )
                            if shape_id is not None:
                                migrated_shape_ids.append(shape_id)
                        except Exception:
                            continue

                    if migrated_shape_ids and (
                        not feature.edge_shape_ids or len(feature.edge_shape_ids) != len(migrated_shape_ids)
                    ):
                        feature.edge_shape_ids = migrated_shape_ids
                        changed = True

                if changed:
                    migrated_features += 1
                    body.invalidate_mesh()

        if migrated_features > 0:
            logger.info(
                f"[MIGRATION] NSided Features auf edge_indices/ShapeIDs migriert: {migrated_features}"
            )
        return migrated_features

    def _migrate_loaded_face_refs_to_indices(self) -> int:
        """
        Runtime migration after load:
        fills missing face/path indices from geometric selectors.

        Ziel:
        - Keine shape-id-only Referenzen ohne Index zuruecklassen
        - stabile Index-Referenzen fuer Face/Edge-basierte Features erzeugen
        """
        migrated_features = 0

        try:
            from modeling.geometric_selector import GeometricFaceSelector, GeometricEdgeSelector
            from modeling.topology_indexing import face_index_of, edge_index_of
        except Exception:
            return 0

        def _as_indices(raw_values) -> List[int]:
            valid: List[int] = []
            for raw_idx in list(raw_values or []):
                try:
                    idx = int(raw_idx)
                except Exception:
                    continue
                if idx < 0:
                    continue
                if idx not in valid:
                    valid.append(idx)
            return valid

        def _selector_to_face_index(selector_data: Any, all_faces: List[Any], solid: Any) -> Optional[int]:
            if not selector_data:
                return None
            try:
                if isinstance(selector_data, dict):
                    selector = GeometricFaceSelector.from_dict(selector_data)
                elif hasattr(selector_data, "find_best_match"):
                    selector = selector_data
                else:
                    return None
            except Exception:
                return None

            try:
                face = selector.find_best_match(all_faces)
                if face is None:
                    return None
                idx = face_index_of(solid, face)
                if idx is None:
                    return None
                idx = int(idx)
                if idx < 0:
                    return None
                return idx
            except Exception:
                return None

        def _selector_to_edge_index(selector_data: Any, all_edges: List[Any], solid: Any) -> Optional[int]:
            if not selector_data:
                return None
            try:
                if isinstance(selector_data, dict):
                    selector = GeometricEdgeSelector.from_dict(selector_data)
                elif hasattr(selector_data, "find_best_match"):
                    selector = selector_data
                else:
                    return None
            except Exception:
                return None

            try:
                edge = selector.find_best_match(all_edges)
                if edge is None:
                    return None
                idx = edge_index_of(solid, edge)
                if idx is None:
                    return None
                idx = int(idx)
                if idx < 0:
                    return None
                return idx
            except Exception:
                return None

        for body in self.get_all_bodies():
            solid = getattr(body, "_build123d_solid", None)
            if solid is None:
                continue

            all_faces = list(solid.faces()) if hasattr(solid, "faces") else []
            all_edges = list(solid.edges()) if hasattr(solid, "edges") else []
            face_count = len(all_faces)
            edge_count = len(all_edges)

            if face_count == 0 and edge_count == 0:
                continue

            for feature in body.features:
                changed = False

                def _ensure_face_indices(index_attr: str, selector_attr: str) -> bool:
                    if face_count == 0:
                        return False

                    raw_indices = getattr(feature, index_attr, None)
                    valid_indices = _as_indices(raw_indices)
                    if valid_indices:
                        return False

                    selectors = list(getattr(feature, selector_attr, []) or [])
                    resolved: List[int] = []
                    for sel in selectors:
                        idx = _selector_to_face_index(sel, all_faces, solid)
                        if idx is not None and idx not in resolved:
                            resolved.append(idx)

                    if resolved:
                        setattr(feature, index_attr, resolved)
                        return True
                    return False

                def _ensure_single_face_index(index_attr: str, selector_attr: str) -> bool:
                    if face_count == 0:
                        return False

                    raw_idx = getattr(feature, index_attr, None)
                    if raw_idx is not None:
                        return False

                    selector_data = getattr(feature, selector_attr, None)
                    resolved_idx = _selector_to_face_index(selector_data, all_faces, solid)
                    if resolved_idx is not None:
                        setattr(feature, index_attr, resolved_idx)
                        return True
                    return False

                if isinstance(feature, (HoleFeature, DraftFeature, SurfaceTextureFeature)):
                    changed |= _ensure_face_indices("face_indices", "face_selectors")
                elif isinstance(feature, ShellFeature):
                    changed |= _ensure_face_indices("face_indices", "opening_face_selectors")
                elif isinstance(feature, HollowFeature):
                    changed |= _ensure_face_indices("opening_face_indices", "opening_face_selectors")
                elif isinstance(feature, (ThreadFeature, ExtrudeFeature)):
                    changed |= _ensure_single_face_index("face_index", "face_selector")
                elif isinstance(feature, SweepFeature):
                    # Profile-Face (body-face sweep profile)
                    if face_count > 0:
                        if feature.profile_face_index is None:
                            resolved_profile_idx = _selector_to_face_index(
                                getattr(feature, "profile_geometric_selector", None),
                                all_faces,
                                solid,
                            )
                            if resolved_profile_idx is not None:
                                feature.profile_face_index = resolved_profile_idx
                                changed = True

                    # Path-Edges
                    path_data = feature.path_data if isinstance(feature.path_data, dict) else {}
                    raw_edge_indices = path_data.get("edge_indices", [])
                    valid_edge_indices = _as_indices(raw_edge_indices)

                    if not valid_edge_indices and edge_count > 0:
                        resolved_path_idx = _selector_to_edge_index(
                            getattr(feature, "path_geometric_selector", None),
                            all_edges,
                            solid,
                        )
                        if resolved_path_idx is not None:
                            path_data["edge_indices"] = [resolved_path_idx]
                            feature.path_data = path_data
                            changed = True

                if changed:
                    migrated_features += 1
                    body.invalidate_mesh()

        if migrated_features > 0:
            logger.info(
                f"[MIGRATION] Face/Path Referenzen auf Indizes migriert: {migrated_features}"
            )
        return migrated_features

    def _migrate_loaded_edge_refs_to_shape_ids(self) -> int:
        """
        Runtime migration after load:
        synchronizes edge_shape_ids from stable edge_indices for strict edge features.

        Hintergrund:
        Nach Save/Load können gespeicherte edge_shape_ids stale sein, obwohl edge_indices
        weiterhin korrekt auflösbar sind. Für Fillet/Chamfer sollen shape_ids danach
        auf die aktuell indexaufgelösten Kanten zeigen.
        """
        service = getattr(self, "_shape_naming_service", None)
        if service is None:
            return 0

        try:
            from modeling.topology_indexing import edge_from_index
            from modeling.tnp_system import ShapeType
        except Exception:
            return 0

        migrated_features = 0

        def _as_indices(raw_values) -> List[int]:
            valid: List[int] = []
            for raw_idx in list(raw_values or []):
                try:
                    idx = int(raw_idx)
                except Exception:
                    continue
                if idx < 0:
                    continue
                if idx not in valid:
                    valid.append(idx)
            return valid

        for body in self.get_all_bodies():
            solid = getattr(body, "_build123d_solid", None)
            if solid is None:
                continue

            for feature in body.features:
                if not isinstance(feature, (FilletFeature, ChamferFeature)):
                    continue

                edge_indices = _as_indices(getattr(feature, "edge_indices", []))
                if not edge_indices:
                    continue

                new_shape_ids = []
                for local_idx, edge_idx in enumerate(edge_indices):
                    try:
                        edge = edge_from_index(solid, int(edge_idx))
                    except Exception:
                        edge = None
                    if edge is None:
                        continue

                    try:
                        shape_id = service.find_shape_id_by_edge(edge)
                        if shape_id is None and hasattr(edge, "wrapped"):
                            ec = edge.center()
                            edge_len = edge.length if hasattr(edge, "length") else 0.0
                            shape_id = service.register_shape(
                                ocp_shape=edge.wrapped,
                                shape_type=ShapeType.EDGE,
                                feature_id=feature.id,
                                local_index=local_idx,
                                geometry_data=(ec.X, ec.Y, ec.Z, edge_len),
                            )
                        if shape_id is not None:
                            new_shape_ids.append(shape_id)
                    except Exception:
                        continue

                if len(new_shape_ids) != len(edge_indices):
                    continue

                old_ids = list(getattr(feature, "edge_shape_ids", []) or [])
                old_tokens = [sid.uuid for sid in old_ids if hasattr(sid, "uuid")]
                new_tokens = [sid.uuid for sid in new_shape_ids if hasattr(sid, "uuid")]
                if old_tokens != new_tokens:
                    feature.edge_shape_ids = new_shape_ids
                    migrated_features += 1
                    body.invalidate_mesh()

        if migrated_features > 0:
            logger.info(
                f"[MIGRATION] Edge ShapeIDs aus edge_indices synchronisiert: {migrated_features}"
            )
        return migrated_features

    def _migrate_loaded_face_refs_to_shape_ids(self) -> int:
        """
        Runtime migration after load:
        synchronizes face ShapeIDs from stable face indices for metadata-only features.

        Hintergrund:
        Fuer verbrauchende Features (z. B. Hole/Draft/Push-Pull) zeigen face_indices
        auf den VOR-Feature-Zustand. Diese koennen aus dem final geladenen BREP
        nicht sicher rekonstruiert werden. Daher wird hier nur fuer nicht-
        destruktive SurfaceTexture-Referenzen migriert.
        """
        service = getattr(self, "_shape_naming_service", None)
        if service is None:
            return 0

        try:
            from modeling.topology_indexing import face_from_index
            from modeling.tnp_system import ShapeType
        except Exception:
            return 0

        migrated_features = 0

        def _as_indices(raw_values) -> List[int]:
            valid: List[int] = []
            for raw_idx in list(raw_values or []):
                try:
                    idx = int(raw_idx)
                except Exception:
                    continue
                if idx < 0:
                    continue
                if idx not in valid:
                    valid.append(idx)
            return valid

        def _resolve_face_shape_id(feature, solid, face_idx: int, local_idx: int):
            try:
                face = face_from_index(solid, int(face_idx))
            except Exception:
                face = None
            if face is None:
                return None

            try:
                shape_id = service.find_shape_id_by_face(face, require_exact=True)
            except Exception:
                shape_id = None

            local_index = getattr(shape_id, "local_index", None) if shape_id is not None else None
            shape_slot_matches = (
                shape_id is not None
                and getattr(shape_id, "feature_id", None) == feature.id
                and isinstance(local_index, int)
                and local_index == int(local_idx)
            )
            if not shape_slot_matches:
                shape_id = None

            if shape_id is None and hasattr(face, "wrapped"):
                try:
                    fc = face.center()
                    area = float(face.area) if hasattr(face, "area") else 0.0
                    shape_id = service.register_shape(
                        ocp_shape=face.wrapped,
                        shape_type=ShapeType.FACE,
                        feature_id=feature.id,
                        local_index=int(local_idx),
                        geometry_data=(fc.X, fc.Y, fc.Z, area),
                    )
                except Exception:
                    return None
            return shape_id

        def _shape_tokens(shape_values: List[Any]) -> List[str]:
            return [sid.uuid for sid in shape_values if hasattr(sid, "uuid")]

        def _sync_face_list_refs(feature, solid, index_attr: str, shape_attr: str) -> bool:
            index_values = _as_indices(getattr(feature, index_attr, []))
            if not index_values:
                return False

            new_shape_ids = []
            for local_idx, face_idx in enumerate(index_values):
                shape_id = _resolve_face_shape_id(feature, solid, face_idx, local_idx)
                if shape_id is None:
                    return False
                new_shape_ids.append(shape_id)

            changed = False
            old_indices = list(getattr(feature, index_attr, []) or [])
            if old_indices != index_values:
                setattr(feature, index_attr, index_values)
                changed = True

            old_shape_ids = list(getattr(feature, shape_attr, []) or [])
            if _shape_tokens(old_shape_ids) != _shape_tokens(new_shape_ids):
                setattr(feature, shape_attr, new_shape_ids)
                changed = True

            return changed

        for body in self.get_all_bodies():
            solid = getattr(body, "_build123d_solid", None)
            if solid is None:
                continue

            for feature in body.features:
                changed = False
                if isinstance(feature, SurfaceTextureFeature):
                    changed |= _sync_face_list_refs(feature, solid, "face_indices", "face_shape_ids")

                if changed:
                    migrated_features += 1
                    body.invalidate_mesh()

        if migrated_features > 0:
            logger.info(
                f"[MIGRATION] Face ShapeIDs aus face_indices synchronisiert: {migrated_features}"
            )
        return migrated_features

    def _rehydrate_shape_naming_service_from_loaded_bodies(self) -> int:
        """
        Seed ShapeNamingService after load from already vorhandenen topology indices.

        Dadurch koennen bestehende ShapeIDs wieder direkt auf aktuelle Faces/Edges
        zeigen, auch wenn kein kompletter Feature-Rebuild stattgefunden hat.
        """
        service = getattr(self, "_shape_naming_service", None)
        if service is None:
            return 0

        try:
            from modeling.topology_indexing import face_from_index, edge_from_index
        except Exception:
            return 0

        seeded = 0

        def _pick_index(shape_id: Any, position: int, index_values: List[Any]) -> Optional[int]:
            candidates: List[Any] = []
            if position < len(index_values):
                candidates.append(index_values[position])
            local_index = getattr(shape_id, "local_index", None)
            if isinstance(local_index, int) and 0 <= local_index < len(index_values):
                candidates.append(index_values[local_index])
            if len(index_values) == 1:
                candidates.append(index_values[0])

            for raw_idx in candidates:
                try:
                    idx = int(raw_idx)
                except Exception:
                    continue
                if idx >= 0:
                    return idx
            return None

        def _seed_pairs(
            solid: Any,
            shape_ids: List[Any],
            index_values: List[Any],
            resolver,
        ) -> int:
            local_seeded = 0
            for i, shape_id in enumerate(shape_ids):
                if not hasattr(shape_id, "uuid"):
                    continue
                idx = _pick_index(shape_id, i, index_values)
                if idx is None:
                    continue
                try:
                    topo_entity = resolver(solid, idx)
                except Exception:
                    topo_entity = None
                if topo_entity is None or not hasattr(topo_entity, "wrapped"):
                    continue
                try:
                    service.seed_shape(shape_id, topo_entity.wrapped)
                    local_seeded += 1
                except Exception:
                    continue
            return local_seeded

        for body in self.get_all_bodies():
            solid = getattr(body, "_build123d_solid", None)
            if solid is None:
                continue

            for feature in body.features:
                seeded += _seed_pairs(
                    solid,
                    list(getattr(feature, "face_shape_ids", []) or []),
                    list(getattr(feature, "face_indices", []) or []),
                    face_from_index,
                )
                seeded += _seed_pairs(
                    solid,
                    list(getattr(feature, "opening_face_shape_ids", []) or []),
                    list(getattr(feature, "opening_face_indices", []) or []),
                    face_from_index,
                )
                seeded += _seed_pairs(
                    solid,
                    list(getattr(feature, "edge_shape_ids", []) or []),
                    list(getattr(feature, "edge_indices", []) or []),
                    edge_from_index,
                )

                single_face_shape = getattr(feature, "face_shape_id", None)
                single_face_index = getattr(feature, "face_index", None)
                if single_face_shape is not None and single_face_index is not None:
                    seeded += _seed_pairs(
                        solid,
                        [single_face_shape],
                        [single_face_index],
                        face_from_index,
                    )

                if isinstance(feature, SweepFeature):
                    if getattr(feature, "profile_shape_id", None) is not None:
                        seeded += _seed_pairs(
                            solid,
                            [feature.profile_shape_id],
                            [feature.profile_face_index],
                            face_from_index,
                        )

                    if getattr(feature, "path_shape_id", None) is not None:
                        path_data = feature.path_data if isinstance(feature.path_data, dict) else {}
                        path_indices = list(path_data.get("edge_indices", []) or [])
                        seeded += _seed_pairs(
                            solid,
                            [feature.path_shape_id],
                            path_indices,
                            edge_from_index,
                        )

        if seeded > 0:
            logger.info(f"[MIGRATION] ShapeNamingService aus geladenen Indizes rehydriert: {seeded}")
        return seeded

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
            for body in doc.get_all_bodies():
                if body._build123d_solid is not None:
                    logger.debug(f"Body '{body.name}': BREP direkt geladen (kein Rebuild nötig)")
                elif body.features:
                    try:
                        body._rebuild()
                        logger.debug(f"Body '{body.name}': Rebuild aus Feature-Tree")
                    except Exception as e:
                        logger.warning(f"Body '{body.name}' rebuild fehlgeschlagen: {e}")

            # Einmalige Legacy-Migration für NSided edge_selectors -> edge_indices/ShapeIDs.
            migrated_nsided = doc._migrate_loaded_nsided_features_to_indices()
            migrated_face_refs = doc._migrate_loaded_face_refs_to_indices()
            seeded_shape_refs = doc._rehydrate_shape_naming_service_from_loaded_bodies()
            migrated_face_shape_refs = doc._migrate_loaded_face_refs_to_shape_ids()
            migrated_edge_shape_refs = doc._migrate_loaded_edge_refs_to_shape_ids()
            if seeded_shape_refs > 0 and is_enabled("tnp_debug_logging"):
                logger.debug(
                    f"[MIGRATION] ShapeNamingService Rehydration: {seeded_shape_refs} mappings"
                )

            migrated_total = (
                migrated_nsided
                + migrated_face_refs
                + migrated_face_shape_refs
                + migrated_edge_shape_refs
            )
            if migrated_total > 0:
                import shutil

                backup_path = path.with_suffix(path.suffix + ".pre_nsided_migration.bak")
                try:
                    if not backup_path.exists():
                        shutil.copy2(path, backup_path)
                        logger.info(f"[MIGRATION] Backup vor Referenz-Migration erstellt: {backup_path}")
                except Exception as e:
                    logger.warning(f"[MIGRATION] Backup fuer Referenz-Migration fehlgeschlagen: {e}")

                if doc.save_project(str(path)):
                    logger.info(
                        "[MIGRATION] Projektdatei nach Referenz-Migration aktualisiert: "
                        f"{path} (nsided={migrated_nsided}, face_refs={migrated_face_refs}, "
                        f"face_shape_refs={migrated_face_shape_refs}, "
                        f"edge_shape_refs={migrated_edge_shape_refs})"
                    )
                else:
                    logger.warning(
                        "[MIGRATION] Projektdatei konnte nach Referenz-Migration nicht gespeichert werden"
                    )

            return doc

        except json.JSONDecodeError as e:
            logger.error(f"Ungültiges JSON in Projektdatei: {e}")
            return None
        except Exception as e:
            logger.error(f"Projekt konnte nicht geladen werden: {e}")
            return None

