"""
TNP v5.0 - Topological Naming Protocol

Enhanced topological naming system with:
- Semantic selection context for user intent capture
- Deterministic resolution strategies
- User-guided ambiguity resolution
- 99.9% resolution success rate target

Author: Development Team
Version: 5.0
Date: 2026-02-25
Replaces: TNP v4.0
"""

from .types import (
    ShapeID,
    ShapeRecord,
    ShapeType,
    SelectionContext,
    ResolutionResult,
    ResolutionMethod,
    ResolutionOptions,
)

from .service import TNPService

# Phase 2 exports
from .spatial import (
    SpatialIndex,
    Bounds,
    compute_bounds_from_signature
)

from .semantic_matcher import (
    SemanticMatcher,
    MatchCandidate,
    MatchResult,
    compute_match_score
)

from .adjacency import (
    AdjacencyTracker,
    AdjacencyGraph,
    compute_adjacency_similarity
)

# Phase 3 exports
from .ambiguity import (
    AmbiguityDetector,
    AmbiguityType,
    AmbiguityReport,
    CandidateInfo,
    detect_ambiguity,
)

# Feature integration exports
from .feature_integration import (
    get_tnp_v5_service,
    capture_sketch_selection_context,
    register_extrude_output_faces,
    register_extrude_output_edges,
    store_tnp_v5_data_in_feature,
    get_tnp_v5_face_ids_from_feature,
    resolve_extrude_face_after_boolean,
    # Fillet/Chamfer
    register_fillet_input_edges,
    register_fillet_output_edges,
    register_fillet_output_faces,
    store_fillet_data_in_feature,
    get_tnp_v5_input_edge_ids,
    resolve_fillet_edge_after_boolean,
    capture_edge_selection_context,
    # Boolean
    register_boolean_input_shapes,
    register_boolean_output_shapes,
    store_boolean_data_in_feature,
    resolve_boolean_shape_after_operation,
    get_occt_history_data,
    get_boolean_input_face_ids,
    get_boolean_output_face_ids,
    get_transformation_map,
)

# Migration exports
from .migration import (
    TNPMigration,
    MigrationResult,
    MigrationRollback,
    AutoMigration,
)

__all__ = [
    "ShapeID",
    "ShapeRecord",
    "ShapeType",
    "SelectionContext",
    "ResolutionResult",
    "ResolutionMethod",
    "ResolutionOptions",
    "TNPService",
    # Phase 2
    "SpatialIndex",
    "Bounds",
    "compute_bounds_from_signature",
    "SemanticMatcher",
    "MatchCandidate",
    "MatchResult",
    "compute_match_score",
    "AdjacencyTracker",
    "AdjacencyGraph",
    "compute_adjacency_similarity",
    # Phase 3
    "AmbiguityDetector",
    "AmbiguityType",
    "AmbiguityReport",
    "CandidateInfo",
    "detect_ambiguity",
    # Feature Integration
    "get_tnp_v5_service",
    "capture_sketch_selection_context",
    "register_extrude_output_faces",
    "register_extrude_output_edges",
    "store_tnp_v5_data_in_feature",
    "get_tnp_v5_face_ids_from_feature",
    "resolve_extrude_face_after_boolean",
    # Migration
    "TNPMigration",
    "MigrationResult",
    "MigrationRollback",
    "AutoMigration",
]
