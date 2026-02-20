"""
AR-003 Phase 2: Body State Module

Extracted from modeling/__init__.py for maintainability.
Contains body state management, serialization helpers, and comparison utilities.

This module provides:
- Body state serialization (to_dict helpers)
- Body state deserialization (from_dict helpers)
- Feature serialization utilities
- Body comparison utilities
"""

from dataclasses import asdict
from typing import List, Optional, Any, Dict, Tuple
from loguru import logger
import uuid

from modeling.feature_operations import normalize_status_details_for_load


# ==============================================================================
# SHAPE ID SERIALIZATION HELPERS
# ==============================================================================

def serialize_shape_id(sid) -> Optional[dict]:
    """
    Serializes a ShapeID object to a dictionary.
    
    Args:
        sid: ShapeID object with uuid, shape_type, feature_id, local_index, etc.
    
    Returns:
        Serialized dict or None if sid is None
    """
    if sid is None:
        return None
    
    if hasattr(sid, "uuid"):
        return {
            "uuid": sid.uuid,
            "shape_type": sid.shape_type.name,
            "feature_id": sid.feature_id,
            "local_index": sid.local_index,
            "geometry_hash": sid.geometry_hash,
            "timestamp": sid.timestamp,
        }
    elif hasattr(sid, "feature_id") and hasattr(sid, "local_id"):
        # Legacy-Compatibility
        return {
            "feature_id": sid.feature_id,
            "local_id": sid.local_id,
            "shape_type": sid.shape_type.name
        }
    return None


def deserialize_shape_id(sid_data: dict, default_shape_type: str = "FACE"):
    """
    Deserializes a ShapeID from a dictionary.
    
    Args:
        sid_data: Dictionary with ShapeID data
        default_shape_type: Default shape type if not specified
    
    Returns:
        ShapeID object or None
    """
    if not isinstance(sid_data, dict):
        return None
    
    from modeling.tnp_system import ShapeID, ShapeType
    
    shape_type = ShapeType[sid_data.get("shape_type", default_shape_type)]
    local_index = int(sid_data.get("local_index", sid_data.get("local_id", 0)))
    
    if sid_data.get("uuid"):
        return ShapeID(
            uuid=sid_data.get("uuid", ""),
            shape_type=shape_type,
            feature_id=sid_data.get("feature_id", ""),
            local_index=local_index,
            geometry_hash=sid_data.get("geometry_hash", ""),
            timestamp=sid_data.get("timestamp", 0.0),
        )
    else:
        # Legacy format - create new ShapeID
        return ShapeID.create(
            shape_type=shape_type,
            feature_id=sid_data.get("feature_id", ""),
            local_index=local_index,
            geometry_data=None
        )


def serialize_shape_ids(sid_list: List) -> List[dict]:
    """
    Serializes a list of ShapeID objects.
    
    Args:
        sid_list: List of ShapeID objects
    
    Returns:
        List of serialized dicts
    """
    result = []
    for sid in sid_list:
        serialized = serialize_shape_id(sid)
        if serialized:
            result.append(serialized)
    return result


def deserialize_shape_ids(sid_data_list: List[dict], default_shape_type: str = "EDGE") -> List:
    """
    Deserializes a list of ShapeID dictionaries.
    
    Args:
        sid_data_list: List of ShapeID dictionaries
        default_shape_type: Default shape type if not specified
    
    Returns:
        List of ShapeID objects
    """
    result = []
    for sid_data in sid_data_list:
        if isinstance(sid_data, dict):
            sid = deserialize_shape_id(sid_data, default_shape_type)
            if sid:
                result.append(sid)
    return result


# ==============================================================================
# FEATURE SERIALIZATION HELPERS
# ==============================================================================

def serialize_feature_base(feat) -> dict:
    """
    Serializes base feature properties common to all features.
    
    Args:
        feat: Feature object
    
    Returns:
        Dict with base feature properties
    """
    return {
        "type": feat.type.name if feat.type else "UNKNOWN",
        "name": feat.name,
        "id": feat.id,
        "visible": feat.visible,
        "suppressed": feat.suppressed,
        "status": feat.status,
        "status_message": getattr(feat, "status_message", ""),
        "status_details": getattr(feat, "status_details", {}),
    }


def serialize_extrude_feature(feat, feat_dict: dict) -> dict:
    """Serialize ExtrudeFeature-specific properties."""
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
        "sketch_id": feat.sketch.id if feat.sketch else None,
        "profile_selector": feat.profile_selector if feat.profile_selector else None,
        "face_index": getattr(feat, "face_index", None),
        "face_selector": getattr(feat, "face_selector", None),
    })
    
    # WKT serialization for precalculated_polys
    if feat.precalculated_polys:
        try:
            feat_dict["precalculated_polys_wkt"] = [
                p.wkt if hasattr(p, 'wkt') else str(p)
                for p in feat.precalculated_polys
            ]
        except Exception:
            pass
    
    # Face-BREP for non-planar faces
    if hasattr(feat, 'face_brep') and feat.face_brep:
        feat_dict["face_brep"] = feat.face_brep
        feat_dict["face_type"] = getattr(feat, 'face_type', None)
    
    # ShapeID serialization
    if getattr(feat, "face_shape_id", None):
        feat_dict["face_shape_id"] = serialize_shape_id(feat.face_shape_id)
    
    return feat_dict


def serialize_fillet_feature(feat, feat_dict: dict) -> dict:
    """Serialize FilletFeature-specific properties."""
    feat_dict.update({
        "feature_class": "FilletFeature",
        "radius": feat.radius,
        "radius_formula": feat.radius_formula,
        "depends_on_feature_id": feat.depends_on_feature_id,
    })
    
    if feat.edge_indices:
        feat_dict["edge_indices"] = list(feat.edge_indices)
    
    # GeometricSelectors
    if feat.geometric_selectors:
        feat_dict["geometric_selectors"] = [
            gs.to_dict() if hasattr(gs, 'to_dict') else str(gs)
            for gs in feat.geometric_selectors
        ]
    
    # ShapeIDs
    if feat.edge_shape_ids:
        feat_dict["edge_shape_ids"] = serialize_shape_ids(feat.edge_shape_ids)
    
    return feat_dict


def serialize_chamfer_feature(feat, feat_dict: dict) -> dict:
    """Serialize ChamferFeature-specific properties."""
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
    
    if feat.edge_shape_ids:
        feat_dict["edge_shape_ids"] = serialize_shape_ids(feat.edge_shape_ids)
    
    return feat_dict


def serialize_revolve_feature(feat, feat_dict: dict) -> dict:
    """Serialize RevolveFeature-specific properties."""
    feat_dict.update({
        "feature_class": "RevolveFeature",
        "angle": feat.angle,
        "angle_formula": feat.angle_formula,
        "axis": list(feat.axis),
        "axis_origin": list(feat.axis_origin),
        "operation": feat.operation,
        "sketch_id": feat.sketch.id if feat.sketch else None,
        "profile_selector": feat.profile_selector if feat.profile_selector else None,
        "face_index": feat.face_index,
        "face_selector": feat.face_selector,
    })
    
    if feat.face_shape_id:
        feat_dict["face_shape_id"] = serialize_shape_id(feat.face_shape_id)
    
    return feat_dict


def serialize_loft_feature(feat, feat_dict: dict) -> dict:
    """Serialize LoftFeature-specific properties."""
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
            pd_copy['shapely_poly'] = None
        serialized_profiles.append(pd_copy)
    
    feat_dict.update({
        "feature_class": "LoftFeature",
        "ruled": feat.ruled,
        "operation": feat.operation,
        "start_continuity": feat.start_continuity if feat.start_continuity else "G0",
        "end_continuity": feat.end_continuity if feat.end_continuity else "G0",
        "profile_data": serialized_profiles,
    })
    
    if feat.profile_shape_ids:
        feat_dict["profile_shape_ids"] = serialize_shape_ids(feat.profile_shape_ids)
    
    if feat.profile_geometric_selectors:
        feat_dict["profile_geometric_selectors"] = [
            asdict(sel) if hasattr(sel, '__dataclass_fields__') else sel
            for sel in feat.profile_geometric_selectors
        ]
    
    return feat_dict


def serialize_sweep_feature(feat, feat_dict: dict) -> dict:
    """Serialize SweepFeature-specific properties."""
    # Serialize profile_data
    pd_copy = feat.profile_data.copy() if feat.profile_data else {}
    if 'shapely_poly' in pd_copy and pd_copy['shapely_poly'] is not None:
        poly = pd_copy['shapely_poly']
        if hasattr(poly, 'exterior'):
            pd_copy['shapely_poly_coords'] = {
                'exterior': list(poly.exterior.coords),
                'holes': [list(interior.coords) for interior in poly.interiors]
            }
        pd_copy['shapely_poly'] = None
    
    # Remove transient path fields
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
    
    if feat.profile_shape_id:
        feat_dict["profile_shape_id"] = serialize_shape_id(feat.profile_shape_id)
    
    if feat.path_shape_id:
        feat_dict["path_shape_id"] = serialize_shape_id(feat.path_shape_id)
    
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
    
    return feat_dict


def serialize_shell_feature(feat, feat_dict: dict) -> dict:
    """Serialize ShellFeature-specific properties."""
    feat_dict.update({
        "feature_class": "ShellFeature",
        "thickness": feat.thickness,
        "thickness_formula": feat.thickness_formula,
        "opening_face_selectors": feat.opening_face_selectors,
    })
    
    if feat.face_indices:
        feat_dict["face_indices"] = list(feat.face_indices)
    
    if feat.face_shape_ids:
        feat_dict["face_shape_ids"] = serialize_shape_ids(feat.face_shape_ids)
    
    return feat_dict


def serialize_hole_feature(feat, feat_dict: dict) -> dict:
    """Serialize HoleFeature-specific properties."""
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
    
    if feat.face_shape_ids:
        feat_dict["face_shape_ids"] = serialize_shape_ids(feat.face_shape_ids)
    
    return feat_dict


def serialize_hollow_feature(feat, feat_dict: dict) -> dict:
    """Serialize HollowFeature-specific properties."""
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
    
    if feat.opening_face_shape_ids:
        feat_dict["opening_face_shape_ids"] = serialize_shape_ids(feat.opening_face_shape_ids)
    
    if feat.opening_face_selectors:
        feat_dict["opening_face_selectors"] = [
            asdict(sel) if hasattr(sel, '__dataclass_fields__') else sel
            for sel in feat.opening_face_selectors
        ]
    
    return feat_dict


def serialize_thread_feature(feat, feat_dict: dict) -> dict:
    """Serialize ThreadFeature-specific properties."""
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
    
    if feat.face_shape_id:
        feat_dict["face_shape_id"] = serialize_shape_id(feat.face_shape_id)
    
    return feat_dict


def serialize_draft_feature(feat, feat_dict: dict) -> dict:
    """Serialize DraftFeature-specific properties."""
    feat_dict.update({
        "feature_class": "DraftFeature",
        "draft_angle": feat.draft_angle,
        "pull_direction": list(feat.pull_direction),
        "face_selectors": feat.face_selectors,
    })
    
    if feat.face_indices:
        feat_dict["face_indices"] = list(feat.face_indices)
    
    if feat.face_shape_ids:
        feat_dict["face_shape_ids"] = serialize_shape_ids(feat.face_shape_ids)
    
    return feat_dict


def serialize_split_feature(feat, feat_dict: dict) -> dict:
    """Serialize SplitFeature-specific properties."""
    feat_dict.update({
        "feature_class": "SplitFeature",
        "plane_origin": list(feat.plane_origin),
        "plane_normal": list(feat.plane_normal),
        "keep_side": feat.keep_side,
    })
    return feat_dict


def serialize_nsided_patch_feature(feat, feat_dict: dict) -> dict:
    """Serialize NSidedPatchFeature-specific properties."""
    feat_dict.update({
        "feature_class": "NSidedPatchFeature",
        "degree": feat.degree,
        "tangent": feat.tangent,
    })
    
    if feat.edge_indices:
        feat_dict["edge_indices"] = list(feat.edge_indices)
    
    if feat.edge_shape_ids:
        feat_dict["edge_shape_ids"] = serialize_shape_ids(feat.edge_shape_ids)
    
    if feat.geometric_selectors:
        feat_dict["geometric_selectors"] = [
            gs.to_dict() if hasattr(gs, 'to_dict') else gs
            for gs in feat.geometric_selectors
        ]
    
    return feat_dict


def serialize_surface_texture_feature(feat, feat_dict: dict) -> dict:
    """Serialize SurfaceTextureFeature-specific properties."""
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
    
    if feat.face_shape_ids:
        feat_dict["face_shape_ids"] = serialize_shape_ids(feat.face_shape_ids)
    
    return feat_dict


def serialize_transform_feature(feat, feat_dict: dict) -> dict:
    """Serialize TransformFeature-specific properties."""
    feat_dict.update({
        "feature_class": "TransformFeature",
        "mode": feat.mode,
        "data": feat.data,
    })
    return feat_dict


def serialize_boolean_feature(feat, feat_dict: dict) -> dict:
    """Serialize BooleanFeature-specific properties."""
    feat_dict.update({
        "feature_class": "BooleanFeature",
        "operation": feat.operation,
        "tool_body_id": feat.tool_body_id,
        "tool_solid_data": feat.tool_solid_data,
        "fuzzy_tolerance": feat.fuzzy_tolerance,
        "expected_volume_change": feat.expected_volume_change,
    })
    
    if feat.modified_shape_ids:
        feat_dict["modified_shape_ids"] = serialize_shape_ids(feat.modified_shape_ids)
    
    return feat_dict


def serialize_pushpull_feature(feat, feat_dict: dict) -> dict:
    """Serialize PushPullFeature-specific properties."""
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
    
    if feat.face_brep:
        feat_dict["face_brep"] = feat.face_brep
        feat_dict["face_type"] = feat.face_type
    
    if feat.precalculated_polys:
        try:
            feat_dict["precalculated_polys_wkt"] = [
                p.wkt if hasattr(p, 'wkt') else str(p)
                for p in feat.precalculated_polys
            ]
        except Exception:
            pass
    
    if feat.face_shape_id and hasattr(feat.face_shape_id, "uuid"):
        feat_dict["face_shape_id"] = serialize_shape_id(feat.face_shape_id)
    
    return feat_dict


def serialize_pattern_feature(feat, feat_dict: dict) -> dict:
    """Serialize PatternFeature-specific properties."""
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
    return feat_dict


def serialize_primitive_feature(feat, feat_dict: dict) -> dict:
    """Serialize PrimitiveFeature-specific properties."""
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
    return feat_dict


def serialize_lattice_feature(feat, feat_dict: dict) -> dict:
    """Serialize LatticeFeature-specific properties."""
    feat_dict.update({
        "feature_class": "LatticeFeature",
        "cell_type": feat.cell_type,
        "cell_size": feat.cell_size,
        "beam_radius": feat.beam_radius,
        "shell_thickness": feat.shell_thickness,
    })
    return feat_dict


def serialize_import_feature(feat, feat_dict: dict) -> dict:
    """Serialize ImportFeature-specific properties."""
    feat_dict.update({
        "feature_class": "ImportFeature",
        "brep_string": feat.brep_string,
        "source_file": feat.source_file,
        "source_type": feat.source_type,
    })
    return feat_dict


# ==============================================================================
# FEATURE SERIALIZATION DISPATCHER
# ==============================================================================

def serialize_feature(feat) -> dict:
    """
    Serializes a feature to a dictionary based on its type.
    
    Args:
        feat: Feature object to serialize
    
    Returns:
        Dictionary with serialized feature data
    """
    from modeling.features.extrude import ExtrudeFeature, PushPullFeature
    from modeling.features.fillet_chamfer import FilletFeature, ChamferFeature
    from modeling.features.revolve import RevolveFeature
    from modeling.features.advanced import (
        LoftFeature, SweepFeature, ShellFeature, HoleFeature,
        DraftFeature, SplitFeature, ThreadFeature, HollowFeature,
        NSidedPatchFeature, SurfaceTextureFeature, PrimitiveFeature,
        LatticeFeature
    )
    from modeling.features.transform import TransformFeature
    from modeling.features.boolean import BooleanFeature
    from modeling.features.pattern import PatternFeature
    from modeling.features.import_feature import ImportFeature
    
    feat_dict = serialize_feature_base(feat)
    
    if isinstance(feat, ExtrudeFeature):
        return serialize_extrude_feature(feat, feat_dict)
    elif isinstance(feat, FilletFeature):
        return serialize_fillet_feature(feat, feat_dict)
    elif isinstance(feat, ChamferFeature):
        return serialize_chamfer_feature(feat, feat_dict)
    elif isinstance(feat, RevolveFeature):
        return serialize_revolve_feature(feat, feat_dict)
    elif isinstance(feat, LoftFeature):
        return serialize_loft_feature(feat, feat_dict)
    elif isinstance(feat, SweepFeature):
        return serialize_sweep_feature(feat, feat_dict)
    elif isinstance(feat, ShellFeature):
        return serialize_shell_feature(feat, feat_dict)
    elif isinstance(feat, HoleFeature):
        return serialize_hole_feature(feat, feat_dict)
    elif isinstance(feat, HollowFeature):
        return serialize_hollow_feature(feat, feat_dict)
    elif isinstance(feat, ThreadFeature):
        return serialize_thread_feature(feat, feat_dict)
    elif isinstance(feat, DraftFeature):
        return serialize_draft_feature(feat, feat_dict)
    elif isinstance(feat, SplitFeature):
        return serialize_split_feature(feat, feat_dict)
    elif isinstance(feat, NSidedPatchFeature):
        return serialize_nsided_patch_feature(feat, feat_dict)
    elif isinstance(feat, SurfaceTextureFeature):
        return serialize_surface_texture_feature(feat, feat_dict)
    elif isinstance(feat, TransformFeature):
        return serialize_transform_feature(feat, feat_dict)
    elif isinstance(feat, BooleanFeature):
        return serialize_boolean_feature(feat, feat_dict)
    elif isinstance(feat, PushPullFeature):
        return serialize_pushpull_feature(feat, feat_dict)
    elif isinstance(feat, PatternFeature):
        return serialize_pattern_feature(feat, feat_dict)
    elif isinstance(feat, PrimitiveFeature):
        return serialize_primitive_feature(feat, feat_dict)
    elif isinstance(feat, LatticeFeature):
        return serialize_lattice_feature(feat, feat_dict)
    elif isinstance(feat, ImportFeature):
        return serialize_import_feature(feat, feat_dict)
    else:
        # Unknown feature type - just return base serialization
        return feat_dict


# ==============================================================================
# BODY STATE COMPARISON UTILITIES
# ==============================================================================

def compare_body_states(body1_state: dict, body2_state: dict) -> Dict[str, Any]:
    """
    Compares two body states and returns differences.
    
    Args:
        body1_state: First body state dict (from to_dict)
        body2_state: Second body state dict
    
    Returns:
        Dict with comparison results
    """
    differences = {
        "name_changed": body1_state.get("name") != body2_state.get("name"),
        "id_changed": body1_state.get("id") != body2_state.get("id"),
        "feature_count_changed": len(body1_state.get("features", [])) != len(body2_state.get("features", [])),
        "features_added": [],
        "features_removed": [],
        "features_modified": [],
    }
    
    # Compare features
    features1 = {f.get("id"): f for f in body1_state.get("features", [])}
    features2 = {f.get("id"): f for f in body2_state.get("features", [])}
    
    ids1 = set(features1.keys())
    ids2 = set(features2.keys())
    
    differences["features_added"] = list(ids2 - ids1)
    differences["features_removed"] = list(ids1 - ids2)
    
    # Check for modified features
    for fid in ids1 & ids2:
        if features1[fid] != features2[fid]:
            differences["features_modified"].append(fid)
    
    # Check split tracking
    differences["split_tracking_changed"] = (
        body1_state.get("source_body_id") != body2_state.get("source_body_id") or
        body1_state.get("split_index") != body2_state.get("split_index") or
        body1_state.get("split_side") != body2_state.get("split_side")
    )
    
    return differences


def body_state_summary(body_state: dict) -> str:
    """
    Creates a human-readable summary of a body state.
    
    Args:
        body_state: Body state dict (from to_dict)
    
    Returns:
        Summary string
    """
    name = body_state.get("name", "Unknown")
    n_features = len(body_state.get("features", []))
    has_brep = bool(body_state.get("brep"))
    version = body_state.get("version", "unknown")
    
    feature_types = {}
    for feat in body_state.get("features", []):
        feat_class = feat.get("feature_class", feat.get("type", "Unknown"))
        feature_types[feat_class] = feature_types.get(feat_class, 0) + 1
    
    type_summary = ", ".join(f"{t}: {c}" for t, c in sorted(feature_types.items()))
    
    return f"Body '{name}' (v{version}): {n_features} features [{type_summary}], BREP: {has_brep}"


# ==============================================================================
# BREP SERIALIZATION UTILITIES
# ==============================================================================

def serialize_brep(solid) -> Optional[str]:
    """
    Serializes a build123d Solid to a BREP string.
    
    Args:
        solid: Build123d Solid object
    
    Returns:
        BREP string or None on failure
    """
    if solid is None:
        return None
    
    try:
        from OCP.BRepTools import BRepTools
        import tempfile
        import os
        
        shape = solid.wrapped if hasattr(solid, 'wrapped') else solid
        with tempfile.NamedTemporaryFile(mode='w', suffix='.brep', delete=False) as tmp:
            tmp_path = tmp.name
        BRepTools.Write_s(shape, tmp_path)
        with open(tmp_path, 'r') as f:
            brep_string = f.read()
        os.unlink(tmp_path)
        return brep_string
    except Exception as e:
        logger.warning(f"BREP serialization failed: {e}")
        return None


def deserialize_brep(brep_string: str):
    """
    Deserializes a BREP string to a build123d Solid.
    
    Args:
        brep_string: BREP string
    
    Returns:
        Build123d Solid or None on failure
    """
    if not brep_string:
        return None
    
    try:
        from OCP.BRepTools import BRepTools
        from OCP.TopoDS import TopoDS_Shape
        from build123d import Solid
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.brep', delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(brep_string)
        
        shape = TopoDS_Shape()
        BRepTools.Read_s(shape, tmp_path)
        os.unlink(tmp_path)
        
        if shape and not shape.IsNull():
            return Solid(shape)
        return None
    except Exception as e:
        logger.warning(f"BREP deserialization failed: {e}")
        return None


# ==============================================================================
# LEGACY ALIASES FOR BACKWARD COMPATIBILITY
# ==============================================================================

_serialize_shape_id = serialize_shape_id
_deserialize_shape_id = deserialize_shape_id
_serialize_shape_ids = serialize_shape_ids
_deserialize_shape_ids = deserialize_shape_ids
_serialize_feature = serialize_feature
_serialize_feature_base = serialize_feature_base
_compare_body_states = compare_body_states
_body_state_summary = body_state_summary
_serialize_brep = serialize_brep
_deserialize_brep = deserialize_brep
