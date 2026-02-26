"""
TNP v5.0 - Feature Integration Helpers

Integration utilities for connecting TNP v5.0 with CAD features.
"""

from typing import Optional, List, Dict, Any, Tuple
from loguru import logger

from .types import (
    ShapeID,
    ShapeType,
    SelectionContext,
)
from .service import TNPService


def get_tnp_v5_service(document: Any) -> Optional[TNPService]:
    """
    Get or create TNP v5.0 service from document.

    Args:
        document: Document instance

    Returns:
        TNPService or None if not available
    """
    # Try to get existing service
    service = getattr(document, '_tnp_v5_service', None)
    if service is not None:
        return service

    # Check if TNP v5.0 is enabled
    from config.feature_flags import is_enabled
    if not is_enabled("tnp_v5_enabled"):
        return None

    # Create new service
    try:
        doc_id = getattr(document, 'name', 'unknown')
        service = TNPService(document_id=doc_id)
        document._tnp_v5_service = service
        logger.debug(f"[TNP v5.0] Created service for document '{doc_id}'")
        return service
    except Exception as e:
        logger.warning(f"[TNP v5.0] Failed to create service: {e}")
        return None


def capture_sketch_selection_context(
    sketch: Any,
    profile_index: int,
    viewport: Any = None
) -> Optional[SelectionContext]:
    """
    Capture selection context when a sketch profile is selected.

    Args:
        sketch: The Sketch object
        profile_index: Index of the selected profile in the sketch
        viewport: Optional viewport for view direction

    Returns:
        SelectionContext with sketch information
    """
    try:
        # Get profile geometry for centroid
        profiles = getattr(sketch, 'closed_profiles', [])
        if profile_index >= len(profiles):
            return None

        profile = profiles[profile_index]

        # Calculate selection point (profile centroid)
        selection_point = _get_profile_centroid(profile, sketch)

        # Get view direction from viewport or default
        view_direction = (0, 0, 1)  # Default: looking from top
        if viewport is not None:
            view_direction = _get_view_direction_from_viewport(viewport)

        # Get adjacent profiles (for complex sketches)
        adjacent_shapes = _get_adjacent_profile_indices(profile_index, profiles)

        # Feature context is the sketch name/id
        feature_context = getattr(sketch, 'name', f'sketch_{id(sketch)}')

        context = SelectionContext(
            shape_id="",
            selection_point=selection_point,
            view_direction=view_direction,
            adjacent_shapes=adjacent_shapes,
            feature_context=feature_context
        )

        logger.debug(f"[TNP v5.0] Captured selection context for profile {profile_index}")
        return context

    except Exception as e:
        logger.debug(f"[TNP v5.0] Failed to capture selection context: {e}")
        return None


def register_extrude_output_faces(
    tnp_service: TNPService,
    solid: Any,
    feature_id: str,
    selection_contexts: Optional[List[SelectionContext]] = None
) -> List[ShapeID]:
    """
    Register extrude output faces with TNP v5.0.

    Args:
        tnp_service: TNP v5.0 service instance
        solid: The extruded build123d Solid
        feature_id: ID of the extrude feature
        selection_contexts: Optional list of selection contexts

    Returns:
        List of registered ShapeIDs
    """
    registered_ids = []

    try:
        if solid is None:
            return registered_ids

        # Get faces from solid
        faces = list(solid.faces())
        if not faces:
            logger.debug(f"[TNP v5.0] No faces to register for feature '{feature_id}'")
            return registered_ids

        # Register each face
        for idx, face in enumerate(faces):
            ocp_shape = face.wrapped if hasattr(face, 'wrapped') else face

            # Get selection context if available
            context = None
            if selection_contexts and idx < len(selection_contexts):
                context = selection_contexts[idx]

            shape_id = tnp_service.register_shape(
                ocp_shape=ocp_shape,
                shape_type=ShapeType.FACE,
                feature_id=feature_id,
                local_index=idx,
                context=context
            )

            registered_ids.append(shape_id)

        logger.info(f"[TNP v5.0] Registered {len(registered_ids)} faces for feature '{feature_id}'")
        return registered_ids

    except Exception as e:
        logger.warning(f"[TNP v5.0] Failed to register extrude faces: {e}")
        return registered_ids


def register_extrude_output_edges(
    tnp_service: TNPService,
    solid: Any,
    feature_id: str
) -> List[ShapeID]:
    """
    Register extrude output edges with TNP v5.0.

    Args:
        tnp_service: TNP v5.0 service instance
        solid: The extruded build123d Solid
        feature_id: ID of the extrude feature

    Returns:
        List of registered ShapeIDs
    """
    registered_ids = []

    try:
        if solid is None:
            return registered_ids

        # Get edges from solid
        edges = list(solid.edges())
        if not edges:
            logger.debug(f"[TNP v5.0] No edges to register for feature '{feature_id}'")
            return registered_ids

        # Register each edge
        for idx, edge in enumerate(edges):
            ocp_shape = edge.wrapped if hasattr(edge, 'wrapped') else edge

            shape_id = tnp_service.register_shape(
                ocp_shape=ocp_shape,
                shape_type=ShapeType.EDGE,
                feature_id=feature_id,
                local_index=idx,
                context=None
            )

            registered_ids.append(shape_id)

        logger.debug(f"[TNP v5.0] Registered {len(registered_ids)} edges for feature '{feature_id}'")
        return registered_ids

    except Exception as e:
        logger.warning(f"[TNP v5.0] Failed to register extrude edges: {e}")
        return registered_ids


# ==========================================================================
# Internal Helpers
# ==========================================================================

def _get_profile_centroid(profile: Any, sketch: Any) -> Tuple[float, float, float]:
    """Get 3D centroid of a sketch profile."""
    try:
        # Try shapely centroid first
        if hasattr(profile, 'centroid'):
            cx, cy = profile.centroid.x, profile.centroid.y
        else:
            cx, cy = 0, 0

        # Convert to 3D using sketch plane
        if hasattr(sketch, 'plane'):
            point_3d = sketch.plane.to_local_coords((cx, cy))
            if hasattr(point_3d, 'X'):
                return (point_3d.X, point_3d.Y, point_3d.Z)
            else:
                return tuple(point_3d) if hasattr(point_3d, '__iter__') else (cx, cy, 0)

        return (cx, cy, 0)
    except Exception:
        return (0, 0, 0)


def _get_view_direction_from_viewport(viewport: Any) -> Tuple[float, float, float]:
    """Get camera view direction from viewport."""
    try:
        # Try common viewport properties
        if hasattr(viewport, 'camera'):
            cam = viewport.camera
            if hasattr(cam, 'direction'):
                return tuple(cam.direction)
            elif hasattr(cam, 'view_direction'):
                return tuple(cam.view_direction)

        # Default: looking from negative Z
        return (0, 0, -1)
    except Exception:
        return (0, 0, -1)


def _get_adjacent_profile_indices(
    current_index: int,
    profiles: List[Any]
) -> List[str]:
    """Get indices of profiles adjacent to current profile."""
    adjacent = []
    for i, profile in enumerate(profiles):
        if i != current_index:
            # Check if profiles share edges (simplified check)
            adjacent.append(f"profile_{i}")
    return adjacent


# ==========================================================================
# Feature Data Storage
# ==========================================================================

def store_tnp_v5_data_in_feature(
    feature: Any,
    face_shape_ids: List[ShapeID],
    edge_shape_ids: Optional[List[ShapeID]] = None
) -> None:
    """
    Store TNP v5.0 shape IDs in feature data.

    Args:
        feature: The feature instance (e.g., ExtrudeFeature)
        face_shape_ids: List of face ShapeIDs from extrusion
        edge_shape_ids: Optional list of edge ShapeIDs
    """
    try:
        # Store face UUIDs
        if hasattr(feature, 'tnp_v5_face_ids'):
            feature.tnp_v5_face_ids = [sid.uuid for sid in face_shape_ids]
        else:
            # Add field if not present
            setattr(feature, 'tnp_v5_face_ids', [sid.uuid for sid in face_shape_ids])

        # Store edge UUIDs
        if edge_shape_ids:
            if hasattr(feature, 'tnp_v5_edge_ids'):
                feature.tnp_v5_edge_ids = [sid.uuid for sid in edge_shape_ids]
            else:
                setattr(feature, 'tnp_v5_edge_ids', [sid.uuid for sid in edge_shape_ids])

        logger.debug(f"[TNP v5.0] Stored {len(face_shape_ids)} face IDs in feature")

    except Exception as e:
        logger.warning(f"[TNP v5.0] Failed to store data in feature: {e}")


def get_tnp_v5_face_ids_from_feature(
    feature: Any
) -> List[str]:
    """
    Get stored TNP v5.0 face IDs from feature.

    Args:
        feature: The feature instance

    Returns:
        List of face UUIDs
    """
    return getattr(feature, 'tnp_v5_face_ids', [])


def resolve_extrude_face_after_boolean(
    tnp_service: TNPService,
    feature: Any,
    current_solid: Any,
    face_index: int = 0
) -> Optional[Any]:
    """
    Resolve an extrude face after boolean operations.

    This is the key post-operation resolution that uses TNP v5.0
    to find the correct face even after the solid has been modified.

    Args:
        tnp_service: TNP v5.0 service instance
        feature: The ExtrudeFeature
        current_solid: Current state of the solid
        face_index: Index of the face to resolve

    Returns:
        Resolved OCP shape or None
    """
    from .types import ResolutionOptions

    face_ids = get_tnp_v5_face_ids_from_feature(feature)
    if not face_ids or face_index >= len(face_ids):
        return None

    # Get the stored shape ID
    face_uuid = face_ids[face_index]

    # Try to get the ShapeID object
    record = tnp_service.get_shape_record(face_uuid)
    if record is None:
        return None

    # Resolve using semantic matching
    options = ResolutionOptions(use_semantic_matching=True)
    result = tnp_service.resolve(record.shape_id, current_solid, options)

    if result.success:
        return result.resolved_shape

    return None


# ==========================================================================
# Fillet/Chamfer Integration
# ==========================================================================

def register_fillet_input_edges(
    tnp_service: TNPService,
    edges: List[Any],
    feature_id: str,
    selection_contexts: Optional[List[SelectionContext]] = None
) -> List[ShapeID]:
    """
    Register fillet input edges with TNP v5.0.

    Args:
        tnp_service: TNP v5.0 service instance
        edges: List of build123d Edge objects selected for filleting
        feature_id: ID of the fillet feature
        selection_contexts: Optional list of selection contexts for each edge

    Returns:
        List of registered ShapeIDs
    """
    registered_ids = []

    try:
        for idx, edge in enumerate(edges):
            ocp_shape = edge.wrapped if hasattr(edge, 'wrapped') else edge

            # Get selection context if available
            context = None
            if selection_contexts and idx < len(selection_contexts):
                context = selection_contexts[idx]

            shape_id = tnp_service.register_shape(
                ocp_shape=ocp_shape,
                shape_type=ShapeType.EDGE,
                feature_id=feature_id,
                local_index=idx,
                context=context
            )

            registered_ids.append(shape_id)

        logger.debug(f"[TNP v5.0] Registered {len(registered_ids)} input edges for fillet '{feature_id}'")
        return registered_ids

    except Exception as e:
        logger.warning(f"[TNP v5.0] Failed to register fillet input edges: {e}")
        return registered_ids


def register_fillet_output_edges(
    tnp_service: TNPService,
    solid: Any,
    feature_id: str
) -> List[ShapeID]:
    """
    Register fillet output edges (the fillet blend edges) with TNP v5.0.

    Args:
        tnp_service: TNP v5.0 service instance
        solid: The solid after fillet operation
        feature_id: ID of the fillet feature

    Returns:
        List of registered ShapeIDs
    """
    registered_ids = []

    try:
        if solid is None:
            return registered_ids

        # Get edges from solid
        edges = list(solid.edges())
        if not edges:
            logger.debug(f"[TNP v5.0] No edges to register for fillet '{feature_id}'")
            return registered_ids

        # Register each edge
        for idx, edge in enumerate(edges):
            ocp_shape = edge.wrapped if hasattr(edge, 'wrapped') else edge

            shape_id = tnp_service.register_shape(
                ocp_shape=ocp_shape,
                shape_type=ShapeType.EDGE,
                feature_id=feature_id,
                local_index=idx,
                context=None
            )

            registered_ids.append(shape_id)

        logger.debug(f"[TNP v5.0] Registered {len(registered_ids)} output edges for fillet '{feature_id}'")
        return registered_ids

    except Exception as e:
        logger.warning(f"[TNP v5.0] Failed to register fillet output edges: {e}")
        return registered_ids


def register_fillet_output_faces(
    tnp_service: TNPService,
    solid: Any,
    feature_id: str
) -> List[ShapeID]:
    """
    Register fillet output faces with TNP v5.0.

    Args:
        tnp_service: TNP v5.0 service instance
        solid: The solid after fillet operation
        feature_id: ID of the fillet feature

    Returns:
        List of registered ShapeIDs
    """
    registered_ids = []

    try:
        if solid is None:
            return registered_ids

        # Get faces from solid
        faces = list(solid.faces())
        if not faces:
            logger.debug(f"[TNP v5.0] No faces to register for fillet '{feature_id}'")
            return registered_ids

        # Register each face
        for idx, face in enumerate(faces):
            ocp_shape = face.wrapped if hasattr(face, 'wrapped') else face

            shape_id = tnp_service.register_shape(
                ocp_shape=ocp_shape,
                shape_type=ShapeType.FACE,
                feature_id=feature_id,
                local_index=idx,
                context=None
            )

            registered_ids.append(shape_id)

        logger.debug(f"[TNP v5.0] Registered {len(registered_ids)} faces for fillet '{feature_id}'")
        return registered_ids

    except Exception as e:
        logger.warning(f"[TNP v5.0] Failed to register fillet faces: {e}")
        return registered_ids


def store_fillet_data_in_feature(
    feature: Any,
    input_edge_ids: List[ShapeID],
    output_edge_ids: Optional[List[ShapeID]] = None,
    output_face_ids: Optional[List[ShapeID]] = None
) -> None:
    """
    Store TNP v5.0 shape IDs in fillet/chamfer feature.

    Args:
        feature: FilletFeature or ChamferFeature instance
        input_edge_ids: List of input edge ShapeIDs
        output_edge_ids: Optional list of output edge ShapeIDs
        output_face_ids: Optional list of output face ShapeIDs
    """
    try:
        # Store input edge UUIDs
        if hasattr(feature, 'tnp_v5_input_edge_ids'):
            feature.tnp_v5_input_edge_ids = [sid.uuid for sid in input_edge_ids]
        else:
            setattr(feature, 'tnp_v5_input_edge_ids', [sid.uuid for sid in input_edge_ids])

        # Store output edge UUIDs
        if output_edge_ids:
            if hasattr(feature, 'tnp_v5_output_edge_ids'):
                feature.tnp_v5_output_edge_ids = [sid.uuid for sid in output_edge_ids]
            else:
                setattr(feature, 'tnp_v5_output_edge_ids', [sid.uuid for sid in output_edge_ids])

        # Store output face UUIDs
        if output_face_ids:
            if hasattr(feature, 'tnp_v5_output_face_ids'):
                feature.tnp_v5_output_face_ids = [sid.uuid for sid in output_face_ids]
            else:
                setattr(feature, 'tnp_v5_output_face_ids', [sid.uuid for sid in output_face_ids])

        logger.debug(f"[TNP v5.0] Stored fillet data in feature: {len(input_edge_ids)} input edges")

    except Exception as e:
        logger.warning(f"[TNP v5.0] Failed to store fillet data: {e}")


def get_tnp_v5_input_edge_ids(
    feature: Any
) -> List[str]:
    """
    Get stored TNP v5.0 input edge IDs from feature.

    Args:
        feature: FilletFeature or ChamferFeature instance

    Returns:
        List of edge UUIDs
    """
    return getattr(feature, 'tnp_v5_input_edge_ids', [])


def resolve_fillet_edge_after_boolean(
    tnp_service: TNPService,
    feature: Any,
    current_solid: Any,
    edge_index: int = 0
) -> Optional[Any]:
    """
    Resolve a fillet input edge after boolean operations.

    This is used to find the original edge that was filleted even after
    the solid has been modified by subsequent operations.

    Args:
        tnp_service: TNP v5.0 service instance
        feature: FilletFeature or ChamferFeature
        current_solid: Current state of the solid
        edge_index: Index of the input edge to resolve

    Returns:
        Resolved OCP shape or None
    """
    from .types import ResolutionOptions

    edge_ids = get_tnp_v5_input_edge_ids(feature)
    if not edge_ids or edge_index >= len(edge_ids):
        return None

    # Get the stored shape ID
    edge_uuid = edge_ids[edge_index]

    # Try to get the ShapeID object
    record = tnp_service.get_shape_record(edge_uuid)
    if record is None:
        return None

    # Resolve using semantic matching
    options = ResolutionOptions(use_semantic_matching=True)
    result = tnp_service.resolve(record.shape_id, current_solid, options)

    if result.success:
        return result.resolved_shape

    return None


def capture_edge_selection_context(
    edge: Any,
    viewport: Any = None,
    adjacent_faces: Optional[List[Any]] = None
) -> Optional[SelectionContext]:
    """
    Capture selection context when an edge is selected for filleting.

    Args:
        edge: The build123d Edge object
        viewport: Optional viewport for view direction
        adjacent_faces: List of faces adjacent to this edge

    Returns:
        SelectionContext with edge information
    """
    try:
        # Get edge center as selection point
        from build123d import Vector
        center = edge.center()
        if hasattr(center, 'X'):
            selection_point = (center.X, center.Y, center.Z)
        else:
            selection_point = tuple(center) if hasattr(center, '__iter__') else (0, 0, 0)

        # Get view direction
        view_direction = (0, 0, -1)  # Default
        if viewport is not None:
            view_direction = _get_view_direction_from_viewport(viewport)

        # Get adjacent faces info
        adjacent_shapes = []
        if adjacent_faces:
            for i, face in enumerate(adjacent_faces):
                adjacent_shapes.append(f"face_{i}")

        context = SelectionContext(
            shape_id="",
            selection_point=selection_point,
            view_direction=view_direction,
            adjacent_shapes=adjacent_shapes,
            feature_context="edge_selection"
        )

        logger.debug(f"[TNP v5.0] Captured selection context for edge")
        return context

    except Exception as e:
        logger.debug(f"[TNP v5.0] Failed to capture edge selection context: {e}")
        return None


# ==========================================================================
# Boolean Operation Integration
# ==========================================================================

def register_boolean_input_shapes(
    tnp_service: TNPService,
    target_solid: Any,
    tool_solid: Any,
    feature_id: str
) -> Tuple[List[ShapeID], List[ShapeID]]:
    """
    Register boolean input shapes (faces and edges) before operation.

    Args:
        tnp_service: TNP v5.0 service instance
        target_solid: The target solid (will be cut/joined)
        tool_solid: The tool solid (cutter/added part)
        feature_id: ID of the boolean feature

    Returns:
        Tuple of (face_ids, edge_ids) registered
    """
    face_ids = []
    edge_ids = []
    face_index = 0
    edge_index = 0

    try:
        def _register_solid(solid: Any, role: str) -> None:
            nonlocal face_index, edge_index
            if solid is None:
                return

            faces = list(solid.faces())
            for face in faces:
                ocp_shape = face.wrapped if hasattr(face, 'wrapped') else face
                shape_id = tnp_service.register_shape(
                    ocp_shape=ocp_shape,
                    shape_type=ShapeType.FACE,
                    feature_id=feature_id,
                    local_index=face_index,
                    context=None
                )
                face_ids.append(shape_id)
                face_index += 1

            edges = list(solid.edges())
            for edge in edges:
                ocp_shape = edge.wrapped if hasattr(edge, 'wrapped') else edge
                shape_id = tnp_service.register_shape(
                    ocp_shape=ocp_shape,
                    shape_type=ShapeType.EDGE,
                    feature_id=feature_id,
                    local_index=edge_index,
                    context=None
                )
                edge_ids.append(shape_id)
                edge_index += 1

            logger.debug(
                f"[TNP v5.0] Registered boolean input {role}: "
                f"{len(faces)} faces, {len(edges)} edges"
            )

        # Register target + tool input shapes.
        # Local indices are monotonic across both solids to avoid ShapeID reuse collisions.
        _register_solid(target_solid, "target")
        _register_solid(tool_solid, "tool")

        logger.debug(f"[TNP v5.0] Registered {len(face_ids)} faces, {len(edge_ids)} edges "
                    f"for boolean '{feature_id}' input")

        return face_ids, edge_ids

    except Exception as e:
        logger.warning(f"[TNP v5.0] Failed to register boolean input shapes: {e}")
        return face_ids, edge_ids


def register_boolean_output_shapes(
    tnp_service: TNPService,
    result_solid: Any,
    feature_id: str,
    input_face_ids: Optional[List[ShapeID]] = None,
    input_edge_ids: Optional[List[ShapeID]] = None
) -> Tuple[List[ShapeID], List[ShapeID], Dict[str, List[str]]]:
    """
    Register boolean output shapes and track transformations.

    Args:
        tnp_service: TNP v5.0 service instance
        result_solid: The solid after boolean operation
        feature_id: ID of the boolean feature
        input_face_ids: Optional list of input face ShapeIDs for transformation tracking
        input_edge_ids: Optional list of input edge ShapeIDs for transformation tracking

    Returns:
        Tuple of (output_face_ids, output_edge_ids, transformation_map)
        transformation_map maps input UUID -> list of output UUIDs
    """
    output_face_ids = []
    output_edge_ids = []
    transformation_map: Dict[str, List[str]] = {}

    try:
        if result_solid is None:
            return output_face_ids, output_edge_ids, transformation_map

        # Register output faces
        faces = list(result_solid.faces())
        for idx, face in enumerate(faces):
            ocp_shape = face.wrapped if hasattr(face, 'wrapped') else face
            shape_id = tnp_service.register_shape(
                ocp_shape=ocp_shape,
                shape_type=ShapeType.FACE,
                feature_id=feature_id,
                local_index=idx,
                context=None
            )
            output_face_ids.append(shape_id)

        # Register output edges
        edges = list(result_solid.edges())
        for idx, edge in enumerate(edges):
            ocp_shape = edge.wrapped if hasattr(edge, 'wrapped') else edge
            shape_id = tnp_service.register_shape(
                ocp_shape=ocp_shape,
                shape_type=ShapeType.EDGE,
                feature_id=feature_id,
                local_index=idx,
                context=None
            )
            output_edge_ids.append(shape_id)

        # Build transformation map (input -> output)
        # This is a simplified mapping - in production, OCCT history would be used
        if input_face_ids:
            for inp_id in input_face_ids:
                transformation_map[inp_id.uuid] = [out_id.uuid for out_id in output_face_ids]

        if input_edge_ids:
            for inp_id in input_edge_ids:
                transformation_map[inp_id.uuid] = [out_id.uuid for out_id in output_edge_ids]

        logger.debug(f"[TNP v5.0] Registered {len(output_face_ids)} output faces, "
                    f"{len(output_edge_ids)} output edges for boolean '{feature_id}'")

        return output_face_ids, output_edge_ids, transformation_map

    except Exception as e:
        logger.warning(f"[TNP v5.0] Failed to register boolean output shapes: {e}")
        return output_face_ids, output_edge_ids, transformation_map


def store_boolean_data_in_feature(
    feature: Any,
    input_face_ids: List[ShapeID],
    input_edge_ids: List[ShapeID],
    output_face_ids: List[ShapeID],
    output_edge_ids: List[ShapeID],
    transformation_map: Dict[str, List[str]]
) -> None:
    """
    Store TNP v5.0 boolean data in feature.

    Args:
        feature: BooleanFeature instance
        input_face_ids: Input face ShapeIDs
        input_edge_ids: Input edge ShapeIDs
        output_face_ids: Output face ShapeIDs
        output_edge_ids: Output edge ShapeIDs
        transformation_map: Input UUID -> list of output UUIDs mapping
    """
    try:
        # Store input UUIDs
        if hasattr(feature, 'tnp_v5_input_face_ids'):
            feature.tnp_v5_input_face_ids = [sid.uuid for sid in input_face_ids]
        else:
            setattr(feature, 'tnp_v5_input_face_ids', [sid.uuid for sid in input_face_ids])

        if hasattr(feature, 'tnp_v5_input_edge_ids'):
            feature.tnp_v5_input_edge_ids = [sid.uuid for sid in input_edge_ids]
        else:
            setattr(feature, 'tnp_v5_input_edge_ids', [sid.uuid for sid in input_edge_ids])

        # Store output UUIDs
        if hasattr(feature, 'tnp_v5_output_face_ids'):
            feature.tnp_v5_output_face_ids = [sid.uuid for sid in output_face_ids]
        else:
            setattr(feature, 'tnp_v5_output_face_ids', [sid.uuid for sid in output_face_ids])

        if hasattr(feature, 'tnp_v5_output_edge_ids'):
            feature.tnp_v5_output_edge_ids = [sid.uuid for sid in output_edge_ids]
        else:
            setattr(feature, 'tnp_v5_output_edge_ids', [sid.uuid for sid in output_edge_ids])

        # Store transformation map
        if hasattr(feature, 'tnp_v5_transformation_map'):
            feature.tnp_v5_transformation_map = transformation_map
        else:
            setattr(feature, 'tnp_v5_transformation_map', transformation_map)

        logger.debug(f"[TNP v5.0] Stored boolean data in feature: "
                    f"{len(input_face_ids)} input faces -> {len(output_face_ids)} output faces")

    except Exception as e:
        logger.warning(f"[TNP v5.0] Failed to store boolean data: {e}")


def resolve_boolean_shape_after_operation(
    tnp_service: TNPService,
    feature: Any,
    current_solid: Any,
    input_shape_uuid: str,
    shape_type: ShapeType = ShapeType.FACE
) -> Optional[Any]:
    """
    Resolve a shape after boolean operations using transformation map.

    Args:
        tnp_service: TNP v5.0 service instance
        feature: BooleanFeature
        current_solid: Current state of the solid
        input_shape_uuid: UUID of the original shape
        shape_type: Type of shape to resolve

    Returns:
        Resolved OCP shape or None
    """
    from .types import ResolutionOptions

    # Check transformation map first (input_uuid -> list of output_uuids)
    transformation_map = getattr(feature, 'tnp_v5_transformation_map', {})
    if input_shape_uuid in transformation_map:
        # Try each output candidate
        output_uuids = transformation_map[input_shape_uuid]
        if isinstance(output_uuids, list):
            for output_uuid in output_uuids:
                record = tnp_service.get_shape_record(output_uuid)
                if record is not None:
                    result = tnp_service.resolve(
                        record.shape_id, current_solid,
                        ResolutionOptions(use_semantic_matching=False)
                    )
                    if result.success:
                        return result.resolved_shape

    # Fallback: Try semantic resolution with original shape ID
    record = tnp_service.get_shape_record(input_shape_uuid)
    if record is not None:
        result = tnp_service.resolve(
            record.shape_id, current_solid,
            ResolutionOptions(use_semantic_matching=True)
        )
        if result.success:
            return result.resolved_shape

    return None


def get_occt_history_data(
    boolean_result: Any
) -> Optional[dict]:
    """
    Extract OCCT history data from boolean result.

    Args:
        boolean_result: Result from BooleanEngineV4

    Returns:
        Dict with serialized history data or None
    """
    try:
        # Check if result has OCCT history
        if hasattr(boolean_result, 'history') and boolean_result.history is not None:
            # Serialize history (simplified - would need proper OCCT serialization)
            return {
                'has_history': True,
                'is_generated': boolean_result.history.IsGenerated() if hasattr(boolean_result.history, 'IsGenerated') else False,
            }

        return None

    except Exception as e:
        logger.debug(f"[TNP v5.0] Failed to extract OCCT history: {e}")
        return None


def get_boolean_input_face_ids(
    feature: Any
) -> List[str]:
    """
    Get stored input face IDs from boolean feature.

    Args:
        feature: BooleanFeature instance

    Returns:
        List of face UUIDs
    """
    return getattr(feature, 'tnp_v5_input_face_ids', [])


def get_boolean_output_face_ids(
    feature: Any
) -> List[str]:
    """
    Get stored output face IDs from boolean feature.

    Args:
        feature: BooleanFeature instance

    Returns:
        List of face UUIDs
    """
    return getattr(feature, 'tnp_v5_output_face_ids', [])


def get_transformation_map(
    feature: Any
) -> Dict[str, List[str]]:
    """
    Get transformation map from boolean feature.

    Args:
        feature: BooleanFeature instance

    Returns:
        Dict mapping input UUIDs to lists of output UUIDs
    """
    return getattr(feature, 'tnp_v5_transformation_map', {})
