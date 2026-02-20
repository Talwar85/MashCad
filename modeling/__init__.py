"""
MashCad - 3D Modeling
Robust B-Rep Implementation with Build123d & Smart Failure Recovery

This module provides the core modeling functionality:
- Body: 3D-Körper mit RobustPartBuilder Logik
- Document: Dokument mit optionalem Assembly-System
- Component: Container für Bodies, Sketches, Planes
- Feature classes: Extrude, Fillet, Chamfer, etc.

All classes are now in dedicated modules for maintainability.
This file serves as a facade for backward compatibility.
"""

# =============================================================================
# CORE CLASSES - Import from dedicated modules
# =============================================================================

# Body class (from modeling/body.py)
from modeling.body import Body, HAS_OCP, HAS_BUILD123D

# Document class (from modeling/document.py)
from modeling.document import Document, SplitResult

# Component class (from modeling/component.py)
from modeling.component import Component

# =============================================================================
# FEATURE CLASSES - Import from modeling/features/
# =============================================================================

from modeling.features.base import Feature, FeatureType
from modeling.features.extrude import ExtrudeFeature, PushPullFeature
from modeling.features.revolve import RevolveFeature
from modeling.features.fillet_chamfer import FilletFeature, ChamferFeature
from modeling.features.pattern import PatternFeature
from modeling.features.boolean import BooleanFeature
from modeling.features.transform import TransformFeature
from modeling.features.advanced import (
    LoftFeature, SweepFeature, ShellFeature, HoleFeature,
    DraftFeature, SplitFeature, ThreadFeature, HollowFeature,
    NSidedPatchFeature, SurfaceTextureFeature, PrimitiveFeature,
    LatticeFeature
)
from modeling.features.import_feature import ImportFeature

# =============================================================================
# CONSTRUCTION ELEMENTS
# =============================================================================

from modeling.construction import ConstructionPlane

# =============================================================================
# HELPER MODULES - Re-export for backward compatibility
# =============================================================================

# Geometry utilities (from modeling/geometry_utils.py)
from modeling.geometry_utils import (
    solid_metrics,
    canonicalize_indices,
    get_face_center,
    get_face_area,
    validate_plane_normal,
    format_index_refs_for_error,
    format_shape_refs_for_error,
    collect_feature_reference_diagnostics,
    collect_feature_reference_payload,
    # Legacy aliases
    _solid_metrics,
    _canonicalize_indices,
    _get_face_center,
    _get_face_area,
    _format_index_refs_for_error,
    _format_shape_refs_for_error,
    _collect_feature_reference_diagnostics,
    _collect_feature_reference_payload,
)

# Shape builders (from modeling/shape_builders.py)
from modeling.shape_builders import (
    convert_legacy_nsided_edge_selectors,
    convert_legacy_edge_selectors,
    convert_line_profiles_to_polygons,
    filter_profiles_by_selector,
    get_plane_from_sketch,
    lookup_geometry_for_polygon,
    make_wire_from_mixed_geometry,
    # Legacy aliases
    _convert_legacy_nsided_edge_selectors,
    _convert_legacy_edge_selectors,
    _convert_line_profiles_to_polygons,
    _filter_profiles_by_selector,
    _get_plane_from_sketch,
    _lookup_geometry_for_polygon,
    _make_wire_from_mixed_geometry,
)

# Feature operations (from modeling/feature_operations.py)
from modeling.feature_operations import (
    record_tnp_failure,
    consume_tnp_failure,
    classify_error_code,
    default_next_action_for_code,
    build_operation_error_details,
    normalize_status_details_for_load,
    safe_operation,
    # Legacy aliases
    _record_tnp_failure,
    _consume_tnp_failure,
    _classify_error_code,
    _default_next_action_for_code,
    _build_operation_error_details,
    _normalize_status_details_for_load,
    _safe_operation,
)

# Body state utilities (from modeling/body_state.py)
from modeling.body_state import (
    serialize_shape_id,
    deserialize_shape_id,
    serialize_shape_ids,
    deserialize_shape_ids,
    serialize_feature,
    serialize_feature_base,
    compare_body_states,
    body_state_summary,
    serialize_brep,
    deserialize_brep,
    # Legacy aliases
    _serialize_shape_id,
    _deserialize_shape_id,
    _serialize_shape_ids,
    _deserialize_shape_ids,
    _serialize_feature,
    _serialize_feature_base,
    _compare_body_states,
    _body_state_summary,
    _serialize_brep,
    _deserialize_brep,
)

# =============================================================================
# ADDITIONAL IMPORTS - For backward compatibility
# =============================================================================

# OCP Helpers
from modeling.ocp_helpers import (
    OCPExtrudeHelper,
    OCPFilletHelper,
    OCPChamferHelper
)

# Boolean Engine
from modeling.boolean_engine_v4 import BooleanEngineV4

# TNP System
from modeling.tnp_system import (
    ShapeNamingService, ShapeID, ShapeType,
    OperationRecord
)

# Feature Dependency
from modeling.feature_dependency import FeatureDependencyGraph, get_dependency_graph

# Result Types
from modeling.result_types import OperationResult, BooleanResult, ResultStatus

# Geometry Validation/Healing
from modeling.geometry_validator import GeometryValidator, ValidationResult, ValidationLevel
from modeling.geometry_healer import GeometryHealer, HealingResult, HealingStrategy

# NURBS
from modeling.nurbs import NURBSCurve, NURBSSurface, ContinuityMode, CurveType

# STEP I/O
from modeling.step_io import STEPWriter, STEPReader, STEPSchema, export_step as step_export

# BREP Cache
import modeling.brep_cache as brep_cache

# CAD Tessellator
from modeling.cad_tessellator import CADTessellator

# Mesh Converter
from modeling.mesh_converter import MeshToBREPConverter

# =============================================================================
# __ALL__ EXPORTS
# =============================================================================

__all__ = [
    # Core classes
    'Body',
    'Document',
    'Component',
    'SplitResult',
    
    # Feature classes
    'Feature',
    'FeatureType',
    'ExtrudeFeature',
    'PushPullFeature',
    'RevolveFeature',
    'FilletFeature',
    'ChamferFeature',
    'PatternFeature',
    'BooleanFeature',
    'TransformFeature',
    'LoftFeature',
    'SweepFeature',
    'ShellFeature',
    'HoleFeature',
    'DraftFeature',
    'SplitFeature',
    'ThreadFeature',
    'HollowFeature',
    'NSidedPatchFeature',
    'SurfaceTextureFeature',
    'PrimitiveFeature',
    'LatticeFeature',
    'ImportFeature',
    
    # Construction
    'ConstructionPlane',
    
    # Geometry utils
    'solid_metrics',
    'canonicalize_indices',
    'get_face_center',
    'get_face_area',
    'validate_plane_normal',
    'format_index_refs_for_error',
    'format_shape_refs_for_error',
    'collect_feature_reference_diagnostics',
    'collect_feature_reference_payload',
    
    # Shape builders
    'convert_legacy_nsided_edge_selectors',
    'convert_legacy_edge_selectors',
    'convert_line_profiles_to_polygons',
    'filter_profiles_by_selector',
    'get_plane_from_sketch',
    'lookup_geometry_for_polygon',
    'make_wire_from_mixed_geometry',
    
    # Feature operations
    'record_tnp_failure',
    'consume_tnp_failure',
    'classify_error_code',
    'default_next_action_for_code',
    'build_operation_error_details',
    'normalize_status_details_for_load',
    'safe_operation',
    
    # Body state
    'serialize_shape_id',
    'deserialize_shape_id',
    'serialize_shape_ids',
    'deserialize_shape_ids',
    'serialize_feature',
    'serialize_feature_base',
    'compare_body_states',
    'body_state_summary',
    'serialize_brep',
    'deserialize_brep',
    
    # OCP Helpers
    'OCPExtrudeHelper',
    'OCPFilletHelper',
    'OCPChamferHelper',
    
    # Boolean Engine
    'BooleanEngineV4',
    
    # TNP System
    'ShapeNamingService',
    'ShapeID',
    'ShapeType',
    'OperationRecord',
    
    # Feature Dependency
    'FeatureDependencyGraph',
    'get_dependency_graph',
    
    # Result Types
    'OperationResult',
    'BooleanResult',
    'ResultStatus',
    
    # Geometry Validation/Healing
    'GeometryValidator',
    'ValidationResult',
    'ValidationLevel',
    'GeometryHealer',
    'HealingResult',
    'HealingStrategy',
    
    # NURBS
    'NURBSCurve',
    'NURBSSurface',
    'ContinuityMode',
    'CurveType',
    
    # STEP I/O
    'STEPWriter',
    'STEPReader',
    'STEPSchema',
    'step_export',
    
    # BREP Cache
    'brep_cache',
    
    # CAD Tessellator
    'CADTessellator',
    
    # Mesh Converter
    'MeshToBREPConverter',
    
    # Flags
    'HAS_OCP',
    'HAS_BUILD123D',
]
