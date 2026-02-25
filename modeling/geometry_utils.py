"""
MashCAD Geometry Utilities

Pure geometry helper functions extracted from modeling/__init__.py.
These functions are stateless and can be used independently.

AR-002: Phase 1 Split - Extracted for maintainability.
"""

import math
from typing import List, Optional, Tuple, Any, Union
from loguru import logger


def _vec_len(v: Tuple[float, float, float]) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _vec_dot(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _vec_cross(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _vec_sub(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vec_mul(v: Tuple[float, float, float], s: float) -> Tuple[float, float, float]:
    return (v[0] * s, v[1] * s, v[2] * s)


def _vec_normalize(v: Tuple[float, float, float], eps: float = 1e-9) -> Optional[Tuple[float, float, float]]:
    length = _vec_len(v)
    if length <= eps:
        return None
    return (v[0] / length, v[1] / length, v[2] / length)


def _as_vec3(value: Any) -> Optional[Tuple[float, float, float]]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except Exception:
        return None


def solid_metrics(solid) -> Optional[dict]:
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


def canonicalize_indices(indices) -> List[int]:
    """
    Normalisiert Topologie-Indizes fuer Determinismus.

    EPIC X2: Stellt sicher dass edge_indices, face_indices etc.
    immer sortiert und entdupliziert sind. Dies ist kritisch fuer:
    - Rebuild-Idempotenz
    - Save/Load Konsistenz
    - TNP Reference Stability

    Args:
        indices: Liste von Indizes (int, float, oder andere)

    Returns:
        Sorted list of unique non-negative integers
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


def get_face_center(face) -> Any:
    """
    Helper for TNP registration - gets face center of mass.

    Args:
        face: OCP TopoDS_Face or Build123d Face

    Returns:
        gp_Pnt center point
    """
    try:
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp
        props = GProp_GProps()
        BRepGProp.LinearProperties_s(face, props)
        p = props.CentreOfMass()
        return p
    except Exception:
        from OCP.gp import gp_Pnt
        return gp_Pnt(0, 0, 0)


def get_face_area(face) -> float:
    """
    Helper for TNP registration - gets face surface area.

    Args:
        face: OCP TopoDS_Face or Build123d Face

    Returns:
        float surface area
    """
    try:
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        return props.Mass()
    except Exception:
        return 0.0


def validate_plane_normal(plane_normal: Tuple[float, float, float], 
                          fallback: Tuple[float, float, float] = (0, 0, 1)) -> Tuple[float, float, float]:
    """
    Validates and normalizes a plane normal vector.

    Args:
        plane_normal: The normal vector to validate
        fallback: Fallback vector if normal is invalid

    Returns:
        Normalized normal vector or fallback
    """
    norm_len = math.sqrt(sum(c * c for c in plane_normal))
    if norm_len < 1e-9:
        logger.warning(f"Plane normal {plane_normal} ist Null-Vektor, Fallback auf {fallback}")
        return fallback
    
    # Normalize
    return tuple(c / norm_len for c in plane_normal)


def normalize_plane_axes(
    plane_normal: Tuple[float, float, float],
    plane_x_dir: Optional[Tuple[float, float, float]] = None,
    plane_y_dir: Optional[Tuple[float, float, float]] = None,
    eps: float = 1e-9,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
    """
    Normalisiert eine Ebenen-Basis zu einem stabilen orthonormalen Frame.

    Liefert immer ein konsistentes (normal, x_dir, y_dir)-Tripel, auch wenn
    Eingangsdaten unvollstaendig, parallel oder degeneriert sind.
    """
    n = validate_plane_normal(_as_vec3(plane_normal) or (0.0, 0.0, 1.0))
    x_in = _as_vec3(plane_x_dir)
    y_in = _as_vec3(plane_y_dir)

    x = None

    # 1) Primär aus x_dir (orthogonal auf Ebene projizieren)
    if x_in is not None:
        x_proj = _vec_sub(x_in, _vec_mul(n, _vec_dot(x_in, n)))
        x = _vec_normalize(x_proj, eps=eps)

    # 2) Sekundär aus y_dir ableiten
    if x is None and y_in is not None:
        y_proj = _vec_sub(y_in, _vec_mul(n, _vec_dot(y_in, n)))
        y_base = _vec_normalize(y_proj, eps=eps)
        if y_base is not None:
            x = _vec_normalize(_vec_cross(y_base, n), eps=eps)

    # 3) Robuster Fallback
    if x is None:
        if abs(n[2]) < 0.9:
            x = _vec_normalize(_vec_cross((0.0, 0.0, 1.0), n), eps=eps)
        else:
            x = (1.0, 0.0, 0.0)
        if x is None:
            x = (1.0, 0.0, 0.0)

    y = _vec_normalize(_vec_cross(n, x), eps=eps)
    if y is None:
        # Letzte Absicherung (sollte praktisch nie auftreten)
        x = (1.0, 0.0, 0.0) if abs(n[2]) > 0.9 else (0.0, 1.0, 0.0)
        y = _vec_normalize(_vec_cross(n, x), eps=eps) or (0.0, 1.0, 0.0)
        x = _vec_normalize(_vec_cross(y, n), eps=eps) or (1.0, 0.0, 0.0)

    # Orientierung moeglichst an supplied y_dir anlehnen
    if y_in is not None:
        y_hint = _vec_normalize(_vec_sub(y_in, _vec_mul(n, _vec_dot(y_in, n))), eps=eps)
        if y_hint is not None and _vec_dot(y, y_hint) < 0.0:
            x = (-x[0], -x[1], -x[2])
            y = (-y[0], -y[1], -y[2])

    return (
        (float(n[0]), float(n[1]), float(n[2])),
        (float(x[0]), float(x[1]), float(x[2])),
        (float(y[0]), float(y[1]), float(y[2])),
    )


def format_index_refs_for_error(label: str, refs, max_items: int = 3) -> str:
    """
    Formatiert Index-Referenzen kompakt fuer Fehlermeldungen.

    Args:
        label: Label prefix (e.g., "face_indices")
        refs: Reference value(s) - single or list
        max_items: Maximum items to show before truncating

    Returns:
        Formatted string for error messages
    """
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


def format_shape_refs_for_error(label: str, refs, max_items: int = 3) -> str:
    """
    Formatiert ShapeID-Referenzen kompakt fuer Fehlermeldungen.

    Args:
        label: Label prefix (e.g., "face_shape_ids")
        refs: Reference value(s) - single or list of ShapeID objects or dicts
        max_items: Maximum items to show before truncating

    Returns:
        Formatted string for error messages
    """
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


def collect_feature_reference_diagnostics(feature, max_parts: int = 6) -> str:
    """
    Baut eine kompakte Referenz-Zusammenfassung fuer Statusmeldungen.

    Wird an Fehlermeldungen angehaengt, damit GUI/Tooltip direkt zeigen kann,
    welche Topologie-Referenzen betroffen waren.

    Args:
        feature: Feature object to extract references from
        max_parts: Maximum number of reference parts to show

    Returns:
        Compact string with reference diagnostics
    """
    if feature is None:
        return ""

    parts = []

    def _add(part: str) -> None:
        if part:
            parts.append(part)

    # Face-Referenzen
    _add(format_index_refs_for_error("face_indices", getattr(feature, "face_indices", None)))
    _add(format_index_refs_for_error("opening_face_indices", getattr(feature, "opening_face_indices", None)))
    _add(format_index_refs_for_error("face_index", getattr(feature, "face_index", None)))
    _add(format_index_refs_for_error("profile_face_index", getattr(feature, "profile_face_index", None)))

    # Edge-Referenzen
    _add(format_index_refs_for_error("edge_indices", getattr(feature, "edge_indices", None)))
    path_data = getattr(feature, "path_data", None)
    if isinstance(path_data, dict):
        _add(format_index_refs_for_error("path.edge_indices", path_data.get("edge_indices", None)))

    # ShapeID-Referenzen
    _add(format_shape_refs_for_error("face_shape_ids", getattr(feature, "face_shape_ids", None)))
    _add(format_shape_refs_for_error("opening_face_shape_ids", getattr(feature, "opening_face_shape_ids", None)))
    _add(format_shape_refs_for_error("edge_shape_ids", getattr(feature, "edge_shape_ids", None)))
    _add(format_shape_refs_for_error("face_shape_id", getattr(feature, "face_shape_id", None)))
    _add(format_shape_refs_for_error("profile_shape_id", getattr(feature, "profile_shape_id", None)))
    _add(format_shape_refs_for_error("path_shape_id", getattr(feature, "path_shape_id", None)))

    if not parts:
        return ""

    if len(parts) > max_parts:
        hidden = len(parts) - max_parts
        parts = parts[:max_parts]
        parts.append(f"+{hidden} weitere")
    return "; ".join(parts)


def collect_feature_reference_payload(feature) -> dict:
    """
    Liefert maschinenlesbare Referenzdaten fuer Status-Details.

    Args:
        feature: Feature object to extract references from

    Returns:
        Dictionary with reference data
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


# =============================================================================
# Legacy Aliases for Backward Compatibility
# =============================================================================

# These aliases maintain backward compatibility with existing code
# that imports these functions from modeling.__init__

_solid_metrics = solid_metrics
_canonicalize_indices = canonicalize_indices
_get_face_center = get_face_center
_get_face_area = get_face_area
_normalize_plane_axes = normalize_plane_axes
_format_index_refs_for_error = format_index_refs_for_error
_format_shape_refs_for_error = format_shape_refs_for_error
_collect_feature_reference_diagnostics = collect_feature_reference_diagnostics
_collect_feature_reference_payload = collect_feature_reference_payload
