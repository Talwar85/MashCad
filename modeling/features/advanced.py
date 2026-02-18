from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Any
from enum import Enum
from loguru import logger
from .base import Feature, FeatureType
from modeling.nurbs import ContinuityMode
from modeling.tnp_system import ShapeID


def _canonicalize_indices(indices):
    """
    Normalisiert Topologie-Indizes fuer Determinismus (EPIC X2).

    Stellt sicher dass edge_indices, face_indices etc. immer
    sortiert und entdupliziert sind. Dies ist kritisch fuer:
    - Rebuild-Idempotenz
    - Save/Load Konsistenz
    - TNP Reference Stability
    """
    if not indices:
        return []

    canonical = set()
    for idx in indices:
        try:
            i = int(idx)
            if i >= 0:
                canonical.add(i)
        except (ValueError, TypeError):
            continue

    return sorted(canonical)


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
        # EPIC X2: Canonicalize face_indices for determinism
        if self.face_indices is None:
            self.face_indices = []
        else:
            self.face_indices = _canonicalize_indices(self.face_indices)


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
            self.name = f"Hole: {self.hole_type}"
        if self.face_shape_ids is None:
            self.face_shape_ids = []
        # EPIC X2: Canonicalize face_indices for determinism
        if self.face_indices is None:
            self.face_indices = []
        else:
            self.face_indices = _canonicalize_indices(self.face_indices)
        if self.face_selectors is None:
            self.face_selectors = []


@dataclass
class DraftFeature(Feature):
    """
    Draft (Entformungsschräge) für ausgewählte Flächen relativ zu einer Ebene.
    """
    draft_angle: float = 2.0  # Winkel in Grad (primaerer Feldname)
    # Legacy-Compat: aeltere Callsites nutzen "angle".
    angle: Optional[float] = None

    # TNP v4.0: Persistent ShapeIDs für Faces
    face_shape_ids: List = None
    face_indices: List = None

    face_selectors: List[dict] = field(default_factory=list)
    pull_direction: Tuple[float, float, float] = (0, 0, 1)  # Vektor der Entformung
    neutral_plane_normal: Tuple[float, float, float] = (0, 0, 1) # Normale der neutralen Ebene

    def __post_init__(self):
        self.type = FeatureType.DRAFT
        if not self.name or self.name == "Feature":
            self.name = "Draft"
        # Normalisiere Legacy-"angle" auf draft_angle.
        if self.angle is not None:
            try:
                self.draft_angle = float(self.angle)
            except Exception as e:
                logger.warning(
                    f"DraftFeature: ungueltiger Legacy-Wert fuer angle={self.angle!r}; "
                    f"verwende draft_angle={self.draft_angle!r}. Fehler: {e}"
                )
        # Halte beide Attribute synchron, da Kernel-Code und Serialization
        # gemischt "draft_angle" und "angle" verwenden.
        self.angle = self.draft_angle
        if self.face_shape_ids is None:
            self.face_shape_ids = []
        # EPIC X2: Canonicalize face_indices for determinism
        if self.face_indices is None:
            self.face_indices = []
        else:
            self.face_indices = _canonicalize_indices(self.face_indices)


@dataclass
class SplitFeature(Feature):
    """
    Split Body - Teilt den Körper an Ebene oder Fläche.
    """
    split_tool: str = "Plane"  # "Plane", "Face"
    
    # Plane Split
    plane_origin: Tuple[float, float, float] = (0, 0, 0)
    plane_normal: Tuple[float, float, float] = (0, 0, 1)
    
    # Face Split (TNP)
    tool_face_shape_id: Any = None
    tool_face_index: Optional[int] = None
    
    keep_both: bool = True  # Wenn False, wird die "obere" Hälfte behalten

    def __post_init__(self):
        self.type = FeatureType.SPLIT
        if not self.name or self.name == "Feature":
            self.name = "Split Body"


@dataclass
class ThreadFeature(Feature):
    """
    Gewinde (Thread) Feature.
    Unterstützt geometrische (echte) und kosmetische Gewinde (Textur/Annotation).
    """
    thread_type: str = "ISO Metric"
    # Legacy-Compat Felder fuer Serialisierung/UI
    standard: str = "M"
    diameter: float = 10.0
    pitch: float = 1.5
    depth: float = 20.0
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    direction: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    tolerance_class: str = "6g"
    tolerance_offset: float = 0.0
    cosmetic: bool = True

    # Neue/alte UI-Parameter parallel weiterfuehren
    size: str = "M10"
    mode: str = "Geometric"  # "Geometric", "Cosmetic"
    
    # Face Selection (Zylinderfläche auswählen)
    face_shape_id: Any = None
    face_index: Optional[int] = None
    face_selector: dict = None

    def __post_init__(self):
        self.type = FeatureType.THREAD
        if not self.name or self.name == "Feature":
            self.name = f"Thread: {self.size}"
        # Sync size <-> standard/diameter fuer Legacy- und neue Pfade.
        if self.size and self.size.startswith("M"):
            self.standard = "M"
            try:
                self.diameter = float(self.size[1:])
            except Exception as e:
                logger.warning(
                    f"ThreadFeature: ungueltiges size-Format {self.size!r}; "
                    f"behalte diameter={self.diameter!r}. Fehler: {e}"
                )
        else:
            self.size = f"{self.standard}{self.diameter:g}"


@dataclass
class HollowFeature(Feature):
    """
    Hollow - Volles Aushöhlen des Solids (Shell nach innen).
    """
    wall_thickness: float = 2.0

    # Legacy-Compat: Wird in UI/Serialization verwendet.
    drain_hole: bool = False
    drain_diameter: float = 2.0
    drain_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    drain_direction: Tuple[float, float, float] = (0.0, 0.0, -1.0)
    
    # Optional: Öffnung nach außen (Drain Hole)
    opening_face_shape_ids: List = None
    opening_face_indices: List = None
    opening_face_selectors: List[dict] = field(default_factory=list)

    def __post_init__(self):
        self.type = FeatureType.HOLLOW
        if not self.name or self.name == "Feature":
            self.name = "Hollow"
        if self.opening_face_shape_ids is None:
            self.opening_face_shape_ids = []
        # EPIC X2: Canonicalize opening_face_indices for determinism
        if self.opening_face_indices is None:
            self.opening_face_indices = []
        else:
            self.opening_face_indices = _canonicalize_indices(self.opening_face_indices)
        if self.opening_face_selectors is None:
            self.opening_face_selectors = []


@dataclass
class NSidedPatchFeature(Feature):
    """
    N-Sided Patch - Füllt eine Lücke zwischen N Kanten.
    Wichtig für Surface Modeling und Reparatur.
    """
    # TNP v4.0: Kanten-Referenzen
    edge_shape_ids: List = None
    edge_indices: List = None

    # Legacy: Geometrische Selektoren
    geometric_selectors: List[dict] = field(default_factory=list)

    # Legacy-Compat fuer Serialisierung
    degree: int = 3
    tangent: bool = True
    continuity: str = "G0"  # "G0" (Position), "G1" (Tangent)

    def __post_init__(self):
        self.type = FeatureType.NSIDED_PATCH
        if not self.name or self.name == "Feature":
            self.name = "N-Sided Patch"
        if self.edge_shape_ids is None:
            self.edge_shape_ids = []
        # EPIC X2: Canonicalize edge_indices for determinism
        if self.edge_indices is None:
            self.edge_indices = []
        else:
            self.edge_indices = _canonicalize_indices(self.edge_indices)
        if self.geometric_selectors is None:
            self.geometric_selectors = []

@dataclass
class SurfaceTextureFeature(Feature):
    """
    Surface Texture Feature - Phase 7.
    """
    texture_type: str = "Fuzzy"
    scale: float = 1.0
    depth: float = 0.5
    # Legacy-Compat: UI/Export serialisiert Rotationswinkel explizit.
    rotation: float = 0.0
    invert: bool = False
    type_params: dict = field(default_factory=dict)
    export_subdivisions: int = 2
    face_shape_ids: List = None
    face_indices: List = None
    face_selectors: List[dict] = field(default_factory=list)

    def __post_init__(self):
        self.type = FeatureType.SURFACE_TEXTURE
        if not self.name or self.name == "Feature":
            self.name = "Surface Texture"
        if self.face_shape_ids is None:
            self.face_shape_ids = []
        # EPIC X2: Canonicalize face_indices for determinism
        if self.face_indices is None:
            self.face_indices = []
        else:
            self.face_indices = _canonicalize_indices(self.face_indices)

@dataclass
class PrimitiveFeature(Feature):
    """
    Primitive Feature - Box, Cylinder, Sphere, Cone, Torus.
    """
    primitive_type: str = "Box"
    parameters: dict = field(default_factory=dict)
    # Legacy-compatible direct parameters (used across tests/serialization).
    length: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    radius: Optional[float] = None
    bottom_radius: Optional[float] = None
    top_radius: Optional[float] = None

    def __post_init__(self):
        self.type = FeatureType.PRIMITIVE
        if not self.name or self.name == "Feature":
            self.name = f"Primitive: {self.primitive_type}"
        if self.parameters is None:
            self.parameters = {}

        p = dict(self.parameters)

        # Merge legacy explicit ctor params into dict-style parameters.
        legacy_keys = (
            "length",
            "width",
            "height",
            "radius",
            "bottom_radius",
            "top_radius",
        )
        for key in legacy_keys:
            val = getattr(self, key, None)
            if val is not None and key not in p:
                p[key] = float(val)

        primitive = (self.primitive_type or "").lower()
        # Normalize defaults so downstream code can rely on stable keys.
        if primitive == "box":
            p.setdefault("length", 10.0)
            p.setdefault("width", 10.0)
            p.setdefault("height", 10.0)
        elif primitive == "cylinder":
            p.setdefault("radius", 5.0)
            p.setdefault("height", 10.0)
        elif primitive == "sphere":
            p.setdefault("radius", 5.0)
        elif primitive == "cone":
            p.setdefault("bottom_radius", 5.0)
            p.setdefault("top_radius", 0.0)
            p.setdefault("height", 10.0)

        self.parameters = p

        # Mirror normalized values back for serialization/UI compatibility.
        self.length = float(p["length"]) if "length" in p else None
        self.width = float(p["width"]) if "width" in p else None
        self.height = float(p["height"]) if "height" in p else None
        self.radius = float(p["radius"]) if "radius" in p else None
        self.bottom_radius = float(p["bottom_radius"]) if "bottom_radius" in p else None
        self.top_radius = float(p["top_radius"]) if "top_radius" in p else None

    def create_solid(self):
        """Erstellt den Primitiv-Solid via direktes OCP (OpenCASCADE)."""
        from OCP.BRepPrimAPI import (
            BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder,
            BRepPrimAPI_MakeSphere, BRepPrimAPI_MakeCone
        )
        from OCP.gp import gp_Pnt
        from build123d import Solid

        p = self.parameters
        t = self.primitive_type.lower()
        try:
            if t == "box":
                builder = BRepPrimAPI_MakeBox(
                    p.get("length", 10), p.get("width", 10), p.get("height", 10)
                )
            elif t == "cylinder":
                builder = BRepPrimAPI_MakeCylinder(
                    p.get("radius", 5), p.get("height", 10)
                )
            elif t == "sphere":
                builder = BRepPrimAPI_MakeSphere(p.get("radius", 5))
            elif t == "cone":
                builder = BRepPrimAPI_MakeCone(
                    p.get("bottom_radius", 5), p.get("top_radius", 0), p.get("height", 10)
                )
            else:
                return None

            builder.Build()
            if not builder.IsDone():
                return None
            return Solid(builder.Shape())
        except Exception as e:
            from loguru import logger
            logger.error(f"PrimitiveFeature.create_solid({t}) OCP failed: {e}")
            return None

@dataclass
class LatticeFeature(Feature):
    """
    Lattice Feature - Gitterstrukturen.
    """
    cell_type: str = "Gyroid"
    cell_size: float = 10.0
    thickness: float = 1.0

    def __post_init__(self):
        self.type = FeatureType.LATTICE
        if not self.name or self.name == "Feature":
            self.name = "Lattice"
