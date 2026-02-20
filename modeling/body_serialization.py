"""
Body Serialization - Extracted from body.py

Contains to_dict and from_dict methods for Body class serialization.
This module provides standalone functions that can be called from Body class.
"""

from dataclasses import asdict
from typing import Any, Optional, List
import uuid
import tempfile
import os

from loguru import logger

# Import feature classes
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

# OCP/build123d availability flags (set by body.py)
HAS_OCP = False
HAS_BUILD123D = False

try:
    from OCP.BRepTools import BRepTools
    from OCP.TopoDS import TopoDS_Shape
    from OCP.BRep import BRep_Builder
    from OCP.TopAbs import TopAbs_SOLID, TopAbs_COMPOUND, TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    HAS_OCP = True
except ImportError:
    pass

try:
    from build123d import Solid, Compound
    HAS_BUILD123D = True
except ImportError:
    pass


def body_to_dict(body) -> dict:
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
    for feat in body.features:
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
            _serialize_extrude_feature(feat, feat_dict)
        elif isinstance(feat, FilletFeature):
            _serialize_fillet_feature(feat, feat_dict)
        elif isinstance(feat, ChamferFeature):
            _serialize_chamfer_feature(feat, feat_dict)
        elif isinstance(feat, RevolveFeature):
            _serialize_revolve_feature(feat, feat_dict)
        elif isinstance(feat, LoftFeature):
            _serialize_loft_feature(feat, feat_dict)
        elif isinstance(feat, SweepFeature):
            _serialize_sweep_feature(feat, feat_dict)
        elif isinstance(feat, ShellFeature):
            _serialize_shell_feature(feat, feat_dict)
        elif isinstance(feat, HoleFeature):
            _serialize_hole_feature(feat, feat_dict)
        elif isinstance(feat, HollowFeature):
            _serialize_hollow_feature(feat, feat_dict)
        elif isinstance(feat, LatticeFeature):
            _serialize_lattice_feature(feat, feat_dict)
        elif isinstance(feat, ThreadFeature):
            _serialize_thread_feature(feat, feat_dict)
        elif isinstance(feat, DraftFeature):
            _serialize_draft_feature(feat, feat_dict)
        elif isinstance(feat, SplitFeature):
            _serialize_split_feature(feat, feat_dict)
        elif isinstance(feat, NSidedPatchFeature):
            _serialize_nsided_patch_feature(feat, feat_dict)
        elif isinstance(feat, SurfaceTextureFeature):
            _serialize_surface_texture_feature(feat, feat_dict)
        elif isinstance(feat, TransformFeature):
            _serialize_transform_feature(feat, feat_dict)
        elif isinstance(feat, BooleanFeature):
            _serialize_boolean_feature(feat, feat_dict)
        elif isinstance(feat, PushPullFeature):
            _serialize_pushpull_feature(feat, feat_dict)
        elif isinstance(feat, PatternFeature):
            _serialize_pattern_feature(feat, feat_dict)
        elif isinstance(feat, PrimitiveFeature):
            _serialize_primitive_feature(feat, feat_dict)
        elif isinstance(feat, ImportFeature):
            _serialize_import_feature(feat, feat_dict)

        features_data.append(feat_dict)

    # B-Rep Snapshot: exakte Geometrie speichern
    brep_string = None
    if body._build123d_solid is not None:
        try:
            from io import StringIO
            shape = body._build123d_solid.wrapped if hasattr(body._build123d_solid, 'wrapped') else body._build123d_solid
            with tempfile.NamedTemporaryFile(mode='w', suffix='.brep', delete=False) as tmp:
                tmp_path = tmp.name
            BRepTools.Write_s(shape, tmp_path)
            with open(tmp_path, 'r') as f:
                brep_string = f.read()
            os.unlink(tmp_path)
            logger.debug(f"BREP serialisiert für '{body.name}': {len(brep_string)} Zeichen")
        except Exception as e:
            logger.warning(f"BREP-Serialisierung fehlgeschlagen für '{body.name}': {e}")

    return {
        "name": body.name,
        "id": body.id,
        "features": features_data,
        "brep": brep_string,
        "version": "9.1",
        # Multi-Body Split-Tracking
        "source_body_id": body.source_body_id,
        "split_index": body.split_index,
        "split_side": body.split_side,
    }


def _serialize_extrude_feature(feat, feat_dict: dict):
    """Serialize ExtrudeFeature specific data."""
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
    # Serialisiere precalculated_polys (Shapely zu WKT) - Legacy Fallback
    if feat.precalculated_polys:
        try:
            feat_dict["precalculated_polys_wkt"] = [
                p.wkt if hasattr(p, 'wkt') else str(p)
                for p in feat.precalculated_polys
            ]
        except Exception as e:
            logger.debug(f"[body_serialization] Fehler: {e}")
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


def _serialize_fillet_feature(feat, feat_dict: dict):
    """Serialize FilletFeature specific data."""
    feat_dict.update({
        "feature_class": "FilletFeature",
        "radius": feat.radius,
        "radius_formula": feat.radius_formula,
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


def _serialize_chamfer_feature(feat, feat_dict: dict):
    """Serialize ChamferFeature specific data."""
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


def _serialize_revolve_feature(feat, feat_dict: dict):
    """Serialize RevolveFeature specific data."""
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
            feat_dict["face_shape_id"] = {
                "feature_id": feat.face_shape_id.feature_id,
                "local_id": getattr(feat.face_shape_id, "local_id", None),
                "shape_type": feat.face_shape_id.shape_type.name
            }


def _serialize_loft_feature(feat, feat_dict: dict):
    """Serialize LoftFeature specific data."""
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
    if feat.profile_geometric_selectors:
        feat_dict["profile_geometric_selectors"] = [
            asdict(sel) if hasattr(sel, '__dataclass_fields__') else sel
            for sel in feat.profile_geometric_selectors
        ]


def _serialize_sweep_feature(feat, feat_dict: dict):
    """Serialize SweepFeature specific data."""
    pd_copy = feat.profile_data.copy() if feat.profile_data else {}
    if 'shapely_poly' in pd_copy and pd_copy['shapely_poly'] is not None:
        poly = pd_copy['shapely_poly']
        if hasattr(poly, 'exterior'):
            pd_copy['shapely_poly_coords'] = {
                'exterior': list(poly.exterior.coords),
                'holes': [list(interior.coords) for interior in poly.interiors]
            }
        pd_copy['shapely_poly'] = None

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


def _serialize_shell_feature(feat, feat_dict: dict):
    """Serialize ShellFeature specific data."""
    feat_dict.update({
        "feature_class": "ShellFeature",
        "thickness": feat.thickness,
        "thickness_formula": feat.thickness_formula,
        "opening_face_selectors": feat.opening_face_selectors,
    })
    if feat.face_indices:
        feat_dict["face_indices"] = list(feat.face_indices)
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


def _serialize_hole_feature(feat, feat_dict: dict):
    """Serialize HoleFeature specific data."""
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


def _serialize_hollow_feature(feat, feat_dict: dict):
    """Serialize HollowFeature specific data."""
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
    if feat.opening_face_selectors:
        feat_dict["opening_face_selectors"] = [
            asdict(sel) if hasattr(sel, '__dataclass_fields__') else sel
            for sel in feat.opening_face_selectors
        ]


def _serialize_lattice_feature(feat, feat_dict: dict):
    """Serialize LatticeFeature specific data."""
    feat_dict.update({
        "feature_class": "LatticeFeature",
        "cell_type": feat.cell_type,
        "cell_size": feat.cell_size,
        "beam_radius": feat.beam_radius,
        "shell_thickness": feat.shell_thickness,
    })


def _serialize_thread_feature(feat, feat_dict: dict):
    """Serialize ThreadFeature specific data."""
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


def _serialize_draft_feature(feat, feat_dict: dict):
    """Serialize DraftFeature specific data."""
    feat_dict.update({
        "feature_class": "DraftFeature",
        "draft_angle": feat.draft_angle,
        "pull_direction": list(feat.pull_direction),
        "face_selectors": feat.face_selectors,
    })
    if feat.face_indices:
        feat_dict["face_indices"] = list(feat.face_indices)
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


def _serialize_split_feature(feat, feat_dict: dict):
    """Serialize SplitFeature specific data."""
    feat_dict.update({
        "feature_class": "SplitFeature",
        "plane_origin": list(feat.plane_origin),
        "plane_normal": list(feat.plane_normal),
        "keep_side": feat.keep_side,
    })


def _serialize_nsided_patch_feature(feat, feat_dict: dict):
    """Serialize NSidedPatchFeature specific data."""
    feat_dict.update({
        "feature_class": "NSidedPatchFeature",
        "degree": feat.degree,
        "tangent": feat.tangent,
    })
    if feat.edge_indices:
        feat_dict["edge_indices"] = list(feat.edge_indices)
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


def _serialize_surface_texture_feature(feat, feat_dict: dict):
    """Serialize SurfaceTextureFeature specific data."""
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


def _serialize_transform_feature(feat, feat_dict: dict):
    """Serialize TransformFeature specific data."""
    feat_dict.update({
        "feature_class": "TransformFeature",
        "mode": feat.mode,
        "data": feat.data,
    })


def _serialize_boolean_feature(feat, feat_dict: dict):
    """Serialize BooleanFeature specific data."""
    feat_dict.update({
        "feature_class": "BooleanFeature",
        "operation": feat.operation,
        "tool_body_id": feat.tool_body_id,
        "tool_solid_data": feat.tool_solid_data,
        "fuzzy_tolerance": feat.fuzzy_tolerance,
        "expected_volume_change": feat.expected_volume_change,
    })
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


def _serialize_pushpull_feature(feat, feat_dict: dict):
    """Serialize PushPullFeature specific data."""
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
        sid = feat.face_shape_id
        feat_dict["face_shape_id"] = {
            "uuid": sid.uuid,
            "shape_type": sid.shape_type.name,
            "feature_id": sid.feature_id,
            "local_index": sid.local_index,
            "geometry_hash": sid.geometry_hash,
            "timestamp": sid.timestamp
        }


def _serialize_pattern_feature(feat, feat_dict: dict):
    """Serialize PatternFeature specific data."""
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


def _serialize_primitive_feature(feat, feat_dict: dict):
    """Serialize PrimitiveFeature specific data."""
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


def _serialize_import_feature(feat, feat_dict: dict):
    """Serialize ImportFeature specific data."""
    feat_dict.update({
        "feature_class": "ImportFeature",
        "brep_string": feat.brep_string,
        "source_file": feat.source_file,
        "source_type": feat.source_type,
    })


def body_from_dict(cls, data: dict, body_class):
    """
    Deserialisiert Body aus Dictionary.

    Args:
        cls: The Body class (for classmethod access)
        data: Dictionary mit Body-Daten (von to_dict())
        body_class: The Body class to instantiate

    Returns:
        Neues Body-Objekt
    """
    body = body_class(name=data.get("name", "Body"))
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
            "status_details": _normalize_status_details_for_load(
                feat_dict.get("status_details", {})
            ),
        }

        feat = None

        if feat_class == "ExtrudeFeature":
            feat = _deserialize_extrude_feature(feat_dict, base_kwargs, cls)
        elif feat_class == "FilletFeature":
            feat = _deserialize_fillet_feature(feat_dict, base_kwargs, cls)
        elif feat_class == "ChamferFeature":
            feat = _deserialize_chamfer_feature(feat_dict, base_kwargs, cls)
        elif feat_class == "RevolveFeature":
            feat = _deserialize_revolve_feature(feat_dict, base_kwargs, cls)
        elif feat_class == "LoftFeature":
            feat = _deserialize_loft_feature(feat_dict, base_kwargs)
        elif feat_class == "SweepFeature":
            feat = _deserialize_sweep_feature(feat_dict, base_kwargs, cls)
        elif feat_class == "ShellFeature":
            feat = _deserialize_shell_feature(feat_dict, base_kwargs)
        elif feat_class == "HoleFeature":
            feat = _deserialize_hole_feature(feat_dict, base_kwargs)
        elif feat_class == "HollowFeature":
            feat = _deserialize_hollow_feature(feat_dict, base_kwargs)
        elif feat_class == "LatticeFeature":
            feat = _deserialize_lattice_feature(feat_dict, base_kwargs)
        elif feat_class == "PushPullFeature":
            feat = _deserialize_pushpull_feature(feat_dict, base_kwargs, cls)
        elif feat_class == "PatternFeature":
            feat = _deserialize_pattern_feature(feat_dict, base_kwargs)
        elif feat_class == "NSidedPatchFeature":
            feat = _deserialize_nsided_patch_feature(feat_dict, base_kwargs, cls)
        elif feat_class == "SurfaceTextureFeature":
            feat = _deserialize_surface_texture_feature(feat_dict, base_kwargs)
        elif feat_class == "ThreadFeature":
            feat = _deserialize_thread_feature(feat_dict, base_kwargs)
        elif feat_class == "DraftFeature":
            feat = _deserialize_draft_feature(feat_dict, base_kwargs)
        elif feat_class == "SplitFeature":
            feat = _deserialize_split_feature(feat_dict, base_kwargs)
        elif feat_class == "TransformFeature":
            feat = _deserialize_transform_feature(feat_dict, base_kwargs)
        elif feat_class == "BooleanFeature":
            feat = _deserialize_boolean_feature(feat_dict, base_kwargs)
        elif feat_class == "PrimitiveFeature":
            feat = _deserialize_primitive_feature(feat_dict, base_kwargs)
        elif feat_class == "ImportFeature":
            feat = _deserialize_import_feature(feat_dict, base_kwargs)
        else:
            # Generic Feature
            feat = Feature(**base_kwargs)
            try:
                feat.type = FeatureType[feat_dict.get("type", "SKETCH")]
            except Exception as e:
                logger.debug(f"[body_serialization] Fehler: {e}")
                pass

        if feat:
            feat.id = feat_dict.get("id", str(uuid.uuid4())[:8])
            body.features.append(feat)

    # B-Rep Snapshot laden
    brep_string = data.get("brep")
    if brep_string and HAS_OCP:
        _load_brep_snapshot(body, brep_string)

    # Multi-Body Split-Tracking
    body.source_body_id = data.get("source_body_id")
    body.split_index = data.get("split_index")
    body.split_side = data.get("split_side")

    return body


def _normalize_status_details_for_load(status_details: Any) -> dict:
    """Normalize status_details for loading from dict."""
    if isinstance(status_details, dict):
        return status_details
    return {}


def _deserialize_extrude_feature(feat_dict: dict, base_kwargs: dict, cls) -> 'ExtrudeFeature':
    """Deserialize ExtrudeFeature from dict."""
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
    feat._sketch_id = feat_dict.get("sketch_id")
    if "profile_selector" in feat_dict and feat_dict["profile_selector"]:
        feat.profile_selector = [tuple(p) for p in feat_dict["profile_selector"]]
    if "precalculated_polys_wkt" in feat_dict:
        try:
            from shapely import wkt
            feat.precalculated_polys = [
                wkt.loads(w) for w in feat_dict["precalculated_polys_wkt"]
            ]
        except Exception as e:
            logger.debug(f"[body_serialization] Fehler: {e}")
            pass
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
    return feat


def _deserialize_fillet_feature(feat_dict: dict, base_kwargs: dict, cls) -> 'FilletFeature':
    """Deserialize FilletFeature from dict."""
    legacy_edge_selectors = feat_dict.get("edge_selectors")
    feat = FilletFeature(
        radius=feat_dict.get("radius", 2.0),
        edge_indices=feat_dict.get("edge_indices", []),
        depends_on_feature_id=feat_dict.get("depends_on_feature_id"),
        **base_kwargs
    )
    feat.radius_formula = feat_dict.get("radius_formula")
    if "geometric_selectors" in feat_dict:
        from modeling.geometric_selector import GeometricEdgeSelector
        feat.geometric_selectors = [
            GeometricEdgeSelector.from_dict(gs) if isinstance(gs, dict) else gs
            for gs in feat_dict["geometric_selectors"]
        ]
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
    return feat


def _deserialize_chamfer_feature(feat_dict: dict, base_kwargs: dict, cls) -> 'ChamferFeature':
    """Deserialize ChamferFeature from dict."""
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
    return feat


def _deserialize_revolve_feature(feat_dict: dict, base_kwargs: dict, cls) -> 'RevolveFeature':
    """Deserialize RevolveFeature from dict."""
    feat = RevolveFeature(
        sketch=None,
        angle=feat_dict.get("angle", 360.0),
        axis=tuple(feat_dict.get("axis", (0, 1, 0))),
        axis_origin=tuple(feat_dict.get("axis_origin", (0, 0, 0))),
        operation=feat_dict.get("operation", "New Body"),
        **base_kwargs
    )
    feat.angle_formula = feat_dict.get("angle_formula")
    feat._sketch_id = feat_dict.get("sketch_id")
    if "profile_selector" in feat_dict and feat_dict["profile_selector"]:
        feat.profile_selector = [tuple(p) for p in feat_dict["profile_selector"]]
    feat.face_index = feat_dict.get("face_index")
    feat.face_selector = feat_dict.get("face_selector")
    if "face_shape_id" in feat_dict and feat_dict["face_shape_id"]:
        sid_data = feat_dict["face_shape_id"]
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
            feat.face_shape_id = ShapeID(
                shape_type=ShapeType[sid_data["shape_type"]],
                feature_id=sid_data["feature_id"],
                local_index=sid_data.get("local_id", sid_data.get("local_index", 0)),
                geometry_data=None
            )
    return feat


def _deserialize_loft_feature(feat_dict: dict, base_kwargs: dict) -> 'LoftFeature':
    """Deserialize LoftFeature from dict."""
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
    if "profile_geometric_selectors" in feat_dict:
        from modeling.geometric_selector import GeometricFaceSelector
        feat.profile_geometric_selectors = []
        for sel_data in feat_dict["profile_geometric_selectors"]:
            if isinstance(sel_data, dict):
                feat.profile_geometric_selectors.append(
                    GeometricFaceSelector(**sel_data)
                )
    return feat


def _deserialize_sweep_feature(feat_dict: dict, base_kwargs: dict, cls) -> 'SweepFeature':
    """Deserialize SweepFeature from dict."""
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
    from modeling.geometric_selector import GeometricFaceSelector, GeometricEdgeSelector
    if "profile_geometric_selector" in feat_dict:
        sel_data = feat_dict["profile_geometric_selector"]
        if isinstance(sel_data, dict):
            feat.profile_geometric_selector = GeometricFaceSelector(**sel_data)
    if "path_geometric_selector" in feat_dict:
        sel_data = feat_dict["path_geometric_selector"]
        if isinstance(sel_data, dict):
            feat.path_geometric_selector = GeometricEdgeSelector(**sel_data)
    if feat.path_geometric_selector is None and isinstance(feat.path_data, dict):
        sel_data = feat.path_data.get("path_geometric_selector")
        if isinstance(sel_data, dict):
            feat.path_geometric_selector = GeometricEdgeSelector(**sel_data)
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
    return feat


def _deserialize_shell_feature(feat_dict: dict, base_kwargs: dict) -> 'ShellFeature':
    """Deserialize ShellFeature from dict."""
    selectors = feat_dict.get("opening_face_selectors", [])
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
    
    feat = ShellFeature(
        thickness=feat_dict.get("thickness", 2.0),
        opening_face_selectors=converted_selectors,
        face_indices=feat_dict.get("face_indices", []),
        **base_kwargs
    )
    feat.thickness_formula = feat_dict.get("thickness_formula")
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
    return feat


def _deserialize_hole_feature(feat_dict: dict, base_kwargs: dict) -> 'HoleFeature':
    """Deserialize HoleFeature from dict."""
    selectors = feat_dict.get("face_selectors", [])
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
    return feat


def _deserialize_hollow_feature(feat_dict: dict, base_kwargs: dict) -> 'HollowFeature':
    """Deserialize HollowFeature from dict."""
    feat = HollowFeature(
        wall_thickness=feat_dict.get("wall_thickness", 2.0),
        drain_hole=feat_dict.get("drain_hole", False),
        drain_diameter=feat_dict.get("drain_diameter", 3.0),
        drain_position=tuple(feat_dict.get("drain_position", [0, 0, 0])),
        drain_direction=tuple(feat_dict.get("drain_direction", [0, 0, -1])),
        opening_face_indices=feat_dict.get("opening_face_indices", []),
        **base_kwargs
    )
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
    if "opening_face_selectors" in feat_dict:
        from modeling.geometric_selector import GeometricFaceSelector
        feat.opening_face_selectors = []
        for sel_data in feat_dict["opening_face_selectors"]:
            if isinstance(sel_data, dict):
                feat.opening_face_selectors.append(
                    GeometricFaceSelector(**sel_data)
                )
    return feat


def _deserialize_lattice_feature(feat_dict: dict, base_kwargs: dict) -> 'LatticeFeature':
    """Deserialize LatticeFeature from dict."""
    return LatticeFeature(
        cell_type=feat_dict.get("cell_type", "BCC"),
        cell_size=feat_dict.get("cell_size", 5.0),
        beam_radius=feat_dict.get("beam_radius", 0.5),
        shell_thickness=feat_dict.get("shell_thickness", 0.0),
        **base_kwargs
    )


def _deserialize_pushpull_feature(feat_dict: dict, base_kwargs: dict, cls) -> 'PushPullFeature':
    """Deserialize PushPullFeature from dict."""
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
    if "face_brep" in feat_dict:
        feat.face_brep = feat_dict["face_brep"]
        feat.face_type = feat_dict.get("face_type")
    if "precalculated_polys_wkt" in feat_dict:
        try:
            from shapely import wkt
            feat.precalculated_polys = [
                wkt.loads(w) for w in feat_dict["precalculated_polys_wkt"]
            ]
        except Exception:
            pass
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
    return feat


def _deserialize_pattern_feature(feat_dict: dict, base_kwargs: dict) -> 'PatternFeature':
    """Deserialize PatternFeature from dict."""
    return PatternFeature(
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


def _deserialize_nsided_patch_feature(feat_dict: dict, base_kwargs: dict, cls) -> 'NSidedPatchFeature':
    """Deserialize NSidedPatchFeature from dict."""
    legacy_edge_selectors = feat_dict.get("edge_selectors", [])
    feat = NSidedPatchFeature(
        edge_indices=feat_dict.get("edge_indices", []),
        degree=feat_dict.get("degree", 3),
        tangent=feat_dict.get("tangent", True),
        **base_kwargs
    )
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
    return feat


def _deserialize_surface_texture_feature(feat_dict: dict, base_kwargs: dict) -> 'SurfaceTextureFeature':
    """Deserialize SurfaceTextureFeature from dict."""
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
    return feat


def _deserialize_thread_feature(feat_dict: dict, base_kwargs: dict) -> 'ThreadFeature':
    """Deserialize ThreadFeature from dict."""
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
    return feat


def _deserialize_draft_feature(feat_dict: dict, base_kwargs: dict) -> 'DraftFeature':
    """Deserialize DraftFeature from dict."""
    selectors = feat_dict.get("face_selectors", [])
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
    return feat


def _deserialize_split_feature(feat_dict: dict, base_kwargs: dict) -> 'SplitFeature':
    """Deserialize SplitFeature from dict."""
    return SplitFeature(
        plane_origin=tuple(feat_dict.get("plane_origin", (0, 0, 0))),
        plane_normal=tuple(feat_dict.get("plane_normal", (0, 0, 1))),
        keep_side=feat_dict.get("keep_side", "above"),
        **base_kwargs
    )


def _deserialize_transform_feature(feat_dict: dict, base_kwargs: dict) -> 'TransformFeature':
    """Deserialize TransformFeature from dict."""
    return TransformFeature(
        mode=feat_dict.get("mode", "move"),
        data=feat_dict.get("data", {}),
        **base_kwargs
    )


def _deserialize_boolean_feature(feat_dict: dict, base_kwargs: dict) -> 'BooleanFeature':
    """Deserialize BooleanFeature from dict."""
    feat = BooleanFeature(
        operation=feat_dict.get("operation", "Cut"),
        tool_body_id=feat_dict.get("tool_body_id"),
        tool_solid_data=feat_dict.get("tool_solid_data"),
        fuzzy_tolerance=feat_dict.get("fuzzy_tolerance"),
        expected_volume_change=feat_dict.get("expected_volume_change"),
        **base_kwargs
    )
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
    return feat


def _deserialize_primitive_feature(feat_dict: dict, base_kwargs: dict) -> 'PrimitiveFeature':
    """Deserialize PrimitiveFeature from dict."""
    return PrimitiveFeature(
        primitive_type=feat_dict.get("primitive_type", "box"),
        length=feat_dict.get("length", 10.0),
        width=feat_dict.get("width", 10.0),
        height=feat_dict.get("height", 10.0),
        radius=feat_dict.get("radius", 5.0),
        bottom_radius=feat_dict.get("bottom_radius", 5.0),
        top_radius=feat_dict.get("top_radius", 0.0),
        **base_kwargs
    )


def _deserialize_import_feature(feat_dict: dict, base_kwargs: dict) -> 'ImportFeature':
    """Deserialize ImportFeature from dict."""
    return ImportFeature(
        brep_string=feat_dict.get("brep_string", ""),
        source_file=feat_dict.get("source_file", ""),
        source_type=feat_dict.get("source_type", ""),
        **base_kwargs
    )


def _load_brep_snapshot(body, brep_string: str):
    """Load B-Rep snapshot into body."""
    if not HAS_OCP:
        return
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.brep', delete=False, encoding='utf-8') as tmp:
            tmp.write(brep_string)
            tmp_path = tmp.name

        shape = TopoDS_Shape()
        builder = BRep_Builder()
        BRepTools.Read_s(shape, tmp_path, builder)
        os.unlink(tmp_path)

        if not shape.IsNull():
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


__all__ = [
    'body_to_dict',
    'body_from_dict',
    '_normalize_status_details_for_load',
    'HAS_OCP',
    'HAS_BUILD123D',
]