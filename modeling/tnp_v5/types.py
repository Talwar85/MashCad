"""
TNP v5.0 - Core Data Types

Defines the fundamental data structures for topological naming.
"""

from dataclasses import dataclass, field, replace
from typing import Optional, Tuple, Dict, Any, Set, List
from enum import Enum, auto
from uuid import uuid4
import hashlib
import time


class ShapeType(Enum):
    """Type of geometric entity"""
    EDGE = auto()
    FACE = auto()
    VERTEX = auto()
    SOLID = auto()

    @classmethod
    def from_ocp(cls, ocp_shape: Any) -> Optional['ShapeType']:
        """
        Determine shape type from OCP/TopoDS_Shape.

        Args:
            ocp_shape: OCP TopoDS_Shape (wrapped or unwrapped)

        Returns:
            ShapeType or None if type cannot be determined
        """
        try:
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX, TopAbs_SOLID

            # Get wrapped shape if needed
            shape = ocp_shape
            if hasattr(ocp_shape, 'wrapped'):
                shape = ocp_shape.wrapped

            if not hasattr(shape, 'ShapeType'):
                return None

            stype = shape.ShapeType()

            if stype == TopAbs_EDGE:
                return cls.EDGE
            elif stype == TopAbs_FACE:
                return cls.FACE
            elif stype == TopAbs_VERTEX:
                return cls.VERTEX
            elif stype == TopAbs_SOLID:
                return cls.SOLID
        except Exception:
            pass

        return None


@dataclass(frozen=True)
class ShapeID:
    """
    Immutable identifier for a geometric entity (v5.0).

    Enhanced from v4.0 with semantic information for better resolution.

    Attributes:
        uuid: Globally unique identifier
        shape_type: Type of shape (EDGE, FACE, VERTEX, SOLID)
        feature_id: ID of the feature that created this shape
        local_index: Index within the feature's output
        geometry_hash: Hash of the geometry for identification
        semantic_hash: Hash of selection context (v5.0 addition)
        parent_uuid: Parent shape ID for derived shapes (v5.0)
        creation_generation: Document generation when created (v5.0)
        tags: User or system tags for categorization (v5.0)
    """
    # Core identity (v4.0 compatible)
    uuid: str
    shape_type: ShapeType
    feature_id: str
    local_index: int
    geometry_hash: str

    # v5.0 additions
    semantic_hash: str = ""
    parent_uuid: Optional[str] = None
    creation_generation: int = 0
    tags: Tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        shape_type: ShapeType,
        feature_id: str,
        local_index: int,
        geometry_data: Tuple
    ) -> 'ShapeID':
        """
        Create a new ShapeID with unique UUID.

        Args:
            shape_type: Type of shape
            feature_id: ID of the creating feature
            local_index: Index within feature
            geometry_data: Tuple of data for geometry hashing

        Returns:
            New ShapeID with unique UUID
        """
        geometry_hash = cls._compute_geometry_hash(geometry_data)
        return cls(
            uuid=str(uuid4()),
            shape_type=shape_type,
            feature_id=feature_id,
            local_index=local_index,
            geometry_hash=geometry_hash,
            semantic_hash="",
            parent_uuid=None,
            creation_generation=0,
            tags=()
        )

    @staticmethod
    def _compute_geometry_hash(data: Tuple) -> str:
        """Compute deterministic hash from geometry data."""
        try:
            return hashlib.sha256(str(data).encode()).hexdigest()[:16]
        except Exception:
            return ""

    def with_context(self, context: 'SelectionContext') -> 'ShapeID':
        """
        Create a new ShapeID with semantic context information.

        This preserves the original UUID while adding semantic hash
        from the selection context for later semantic matching.

        Args:
            context: SelectionContext from user interaction

        Returns:
            New ShapeID with semantic_hash populated
        """
        if context is None:
            return self
        return replace(self, semantic_hash=self._compute_semantic_hash(context))

    def _compute_semantic_hash(self, context: 'SelectionContext') -> str:
        """Compute hash from selection context for semantic matching."""
        try:
            data = (
                getattr(context, 'selection_point', ()),
                tuple(sorted(getattr(context, 'adjacent_shapes', []))),
                getattr(context, 'feature_context', '')
            )
            return self._compute_geometry_hash(data)
        except Exception:
            return ""

    def with_parent(self, parent_uuid: str) -> 'ShapeID':
        """
        Create a derived ShapeID (e.g., edge from face).

        Args:
            parent_uuid: UUID of the parent shape

        Returns:
            New ShapeID with parent set
        """
        return replace(self, parent_uuid=parent_uuid)

    def with_tag(self, tag: str) -> 'ShapeID':
        """
        Add a tag to this ShapeID.

        Args:
            tag: Tag string to add

        Returns:
            New ShapeID with tag added
        """
        return replace(self, tags=self.tags + (tag,))

    # v4.0 compatibility methods
    def to_v4_format(self) -> Dict[str, Any]:
        """
        Convert to v4.0 compatible dictionary format.

        Returns:
            Dictionary with v4.0 fields
        """
        return {
            'uuid': self.uuid,
            'shape_type': self.shape_type,
            'feature_id': self.feature_id,
            'local_index': self.local_index,
            'geometry_hash': self.geometry_hash,
        }

    @classmethod
    def from_v4_format(cls, data: Dict[str, Any]) -> 'ShapeID':
        """
        Create ShapeID from v4.0 format dictionary.

        Args:
            data: Dictionary from v4.0 system

        Returns:
            New ShapeID converted from v4.0 data
        """
        return cls(
            uuid=data['uuid'],
            shape_type=data['shape_type'],
            feature_id=data['feature_id'],
            local_index=data['local_index'],
            geometry_hash=data['geometry_hash'],
            semantic_hash="",
            parent_uuid=None,
            creation_generation=0,
            tags=()
        )


@dataclass
class SelectionContext:
    """
    Context information captured when user selects a shape.

    This context enables semantic matching by capturing user intent,
    selection location, and surrounding geometry.

    Attributes:
        shape_id: The ShapeID being selected
        selection_point: 3D world coordinates of selection
        view_direction: Camera direction at selection time
        adjacent_shapes: List of ShapeIDs for connected shapes
        feature_context: Which feature created this shape
        timestamp: When the selection occurred
        semantic_tags: Additional tags for the selection
        screen_position: 2D screen coordinates (optional)
        zoom_level: Zoom level at selection (optional)
        viewport_id: Which viewport was used (optional)
    """
    shape_id: str
    selection_point: Tuple[float, float, float]
    view_direction: Tuple[float, float, float]
    adjacent_shapes: List[str]
    feature_context: str
    timestamp: float = field(default_factory=time.time)
    semantic_tags: Set[str] = field(default_factory=set)
    screen_position: Optional[Tuple[float, float]] = None
    zoom_level: Optional[float] = None
    viewport_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for persistence."""
        return {
            'shape_id': self.shape_id,
            'selection_point': self.selection_point,
            'view_direction': self.view_direction,
            'adjacent_shapes': self.adjacent_shapes,
            'feature_context': self.feature_context,
            'timestamp': self.timestamp,
            'semantic_tags': list(self.semantic_tags),
            'screen_position': self.screen_position,
            'zoom_level': self.zoom_level,
            'viewport_id': self.viewport_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SelectionContext':
        """Deserialize from dictionary."""
        return cls(
            shape_id=data['shape_id'],
            selection_point=tuple(data['selection_point']),
            view_direction=tuple(data['view_direction']),
            adjacent_shapes=data.get('adjacent_shapes', []),
            feature_context=data['feature_context'],
            timestamp=data.get('timestamp', time.time()),
            semantic_tags=set(data.get('semantic_tags', [])),
            screen_position=data.get('screen_position'),
            zoom_level=data.get('zoom_level'),
            viewport_id=data.get('viewport_id'),
        )


class ResolutionMethod(Enum):
    """Method used to resolve a ShapeID."""
    EXACT = "exact"           # IsSame() match - 100% reliable
    SEMANTIC = "semantic"     # Context-based matching - uses selection context
    HISTORY = "history"       # OCCT history tracing - when available
    USER_GUIDED = "user"      # User selected manually - 100% reliable
    FAILED = "failed"         # Could not resolve


@dataclass
class ResolutionResult:
    """
    Result of a shape resolution attempt.

    Attributes:
        shape_id: The ShapeID that was resolved
        resolved_shape: The OCP TopoDS_Shape (or None if failed)
        method: Which resolution method succeeded
        confidence: 0.0-1.0 confidence in the result
        duration_ms: How long the resolution took
        alternative_candidates: Other valid candidates (if ambiguous)
        disambiguation_used: How ambiguity was resolved (if any)
    """
    shape_id: str
    resolved_shape: Optional[Any]  # TopoDS_Shape
    method: ResolutionMethod
    confidence: float  # 0.0 - 1.0
    duration_ms: float
    alternative_candidates: List[Any] = field(default_factory=list)
    disambiguation_used: Optional[str] = None

    @property
    def success(self) -> bool:
        """Whether resolution was successful."""
        return self.resolved_shape is not None

    @property
    def is_ambiguous(self) -> bool:
        """Whether there were multiple valid candidates."""
        return len(self.alternative_candidates) > 0


@dataclass
class ResolutionOptions:
    """
    Options for shape resolution behavior.

    Attributes:
        use_semantic_matching: Enable context-based matching
        use_history_tracing: Enable OCCT history tracing
        require_user_confirmation: Prompt user on ANY ambiguity
        position_tolerance: Distance tolerance in mm
        angle_tolerance: Angle tolerance in radians
        enable_spatial_index: Use R-tree spatial index
        max_candidates: Maximum candidates to consider
        on_failure: What to do when resolution fails ("error", "skip", "prompt")
    """
    # Strategy selection
    use_semantic_matching: bool = True
    use_history_tracing: bool = True
    require_user_confirmation: bool = False

    # Tolerance settings
    position_tolerance: float = 0.01  # 1mm
    angle_tolerance: float = 0.1     # ~5.7 degrees

    # Performance
    enable_spatial_index: bool = True
    max_candidates: int = 10

    # Fallback behavior
    on_failure: str = "prompt"  # "error", "skip", "prompt"


@dataclass
class ShapeRecord:
    """
    Registry entry for a tracked shape.

    Attributes:
        shape_id: The ShapeID for this record
        ocp_shape: The OCP TopoDS_Shape (may be None)
        geometric_signature: Computed geometric fingerprint
        is_valid: Whether the shape is still valid
        selection_context: Original selection context (v5.0)
        adjacency: Map of neighbor shape_id -> relationship type (v5.0)
        validation_history: History of validation checks (v5.0)
        resolution_history: History of resolution attempts (v5.0)
    """
    shape_id: ShapeID
    ocp_shape: Optional[Any] = None  # TopoDS_Shape
    geometric_signature: Dict[str, Any] = field(default_factory=dict)
    is_valid: bool = True

    # v5.0 additions
    selection_context: Optional[SelectionContext] = None
    adjacency: Dict[str, str] = field(default_factory=dict)  # neighbor_id -> relationship
    validation_history: List['ValidationRecord'] = field(default_factory=list)
    resolution_history: List['ResolutionRecord'] = field(default_factory=list)

    def compute_signature(self) -> Dict[str, Any]:
        """
        Compute geometric fingerprint for this shape.

        Returns:
            Dictionary with geometric properties (center, length, area, etc.)
        """
        if self.ocp_shape is None:
            return {}

        sig = {}

        try:
            shape_type = self.shape_id.shape_type

            if shape_type == ShapeType.EDGE:
                sig.update(self._compute_edge_signature(self.ocp_shape))
            elif shape_type == ShapeType.FACE:
                sig.update(self._compute_face_signature(self.ocp_shape))
            elif shape_type == ShapeType.VERTEX:
                sig.update(self._compute_vertex_signature(self.ocp_shape))
        except Exception as e:
            from loguru import logger
            logger.debug(f"Failed to compute signature: {e}")

        return sig

    def _compute_edge_signature(self, edge) -> Dict[str, Any]:
        """Compute signature for an edge."""
        # Initialize signature dict to avoid silent errors
        sig = {}

        try:
            from OCP.BRepAdaptor import BRepAdaptor_Curve
            from OCP.GProp import GProp_GProps
            from OCP.BRepGProp import BRepGProp
            from OCP.TopoDS import TopoDS
            from OCP.TopAbs import TopAbs_EDGE

            if hasattr(edge, 'wrapped'):
                edge = edge.wrapped

            adaptor = BRepAdaptor_Curve(edge)

            # Midpoint
            try:
                u_mid = (adaptor.FirstParameter() + adaptor.LastParameter()) / 2
                pnt = adaptor.Value(u_mid)
                sig['center'] = (pnt.X(), pnt.Y(), pnt.Z())
            except:
                sig['center'] = (0, 0, 0)

            # Length
            try:
                props = GProp_GProps()
                BRepGProp.LinearProperties_s(edge, props)
                sig['length'] = props.Mass()
            except:
                sig['length'] = 0.0

            # Curve type
            try:
                sig['curve_type'] = str(adaptor.GetType())
            except:
                sig['curve_type'] = ""

        except Exception:
            pass

        return sig

    def _compute_face_signature(self, face) -> Dict[str, Any]:
        """Compute signature for a face."""
        try:
            from OCP.GProp import GProp_GProps
            from OCP.BRepGProp import BRepGProp

            if hasattr(face, 'wrapped'):
                face = face.wrapped

            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, props)

            center = props.CentreOfMass()
            return {
                'center': (center.X(), center.Y(), center.Z()),
                'area': props.Mass()
            }
        except Exception:
            return {}

    def _compute_vertex_signature(self, vertex) -> Dict[str, Any]:
        """Compute signature for a vertex."""
        try:
            if hasattr(vertex, 'wrapped'):
                vertex = vertex.wrapped

            from OCP.BRepBuilderAPI import BRepBuilderAPI_Vertex
            v_maker = BRepBuilderAPI_Vertex(vertex)
            pnt = v_maker.Pnt()
            return {'center': (pnt.X(), pnt.Y(), pnt.Z())}
        except Exception:
            return {}


# Type aliases for validation and resolution records
ValidationRecord = Dict[str, Any]  # TODO: Define properly
ResolutionRecord = Dict[str, Any]   # TODO: Define properly
