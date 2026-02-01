"""
MashCad - Face Hash System
===========================

Stable geometric hashing for B-Rep faces.
Enables face identification that survives topology changes.

Phase 7: TNP (Topological Naming Problem) solution.

Usage:
    from modeling.face_hash import compute_face_hash, get_face_info

    # Compute hash for a face
    face_hash = compute_face_hash(ocp_face)

    # Get full face info (hash, center, normal, etc.)
    info = get_face_info(ocp_face)
"""

import hashlib
import math
from typing import Optional, Tuple, Dict, Any
from loguru import logger

# OCP imports
try:
    from OCP.TopoDS import TopoDS_Face, TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.GeomAbs import (
        GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone,
        GeomAbs_Sphere, GeomAbs_Torus, GeomAbs_BSplineSurface,
        GeomAbs_BezierSurface, GeomAbs_SurfaceOfRevolution,
        GeomAbs_SurfaceOfExtrusion, GeomAbs_OffsetSurface,
        GeomAbs_OtherSurface
    )
    HAS_OCP = True
except ImportError:
    HAS_OCP = False
    logger.warning("[FaceHash] OCP not available - face hashing disabled")


# Surface type name mapping
SURFACE_TYPE_NAMES = {
    GeomAbs_Plane: "plane",
    GeomAbs_Cylinder: "cylinder",
    GeomAbs_Cone: "cone",
    GeomAbs_Sphere: "sphere",
    GeomAbs_Torus: "torus",
    GeomAbs_BSplineSurface: "bspline",
    GeomAbs_BezierSurface: "bezier",
    GeomAbs_SurfaceOfRevolution: "revolution",
    GeomAbs_SurfaceOfExtrusion: "extrusion",
    GeomAbs_OffsetSurface: "offset",
    GeomAbs_OtherSurface: "other",
} if HAS_OCP else {}


def get_surface_type_name(surface_type) -> str:
    """
    Converts OCP surface type enum to human-readable string.

    Args:
        surface_type: GeomAbs surface type enum

    Returns:
        String name like "plane", "cylinder", etc.
    """
    return SURFACE_TYPE_NAMES.get(surface_type, "unknown")


def get_face_center(face: 'TopoDS_Face') -> Tuple[float, float, float]:
    """
    Computes the center of mass of a face.

    Args:
        face: OCP TopoDS_Face

    Returns:
        Tuple (x, y, z) center coordinates
    """
    if not HAS_OCP:
        return (0.0, 0.0, 0.0)

    try:
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        center = props.CentreOfMass()
        return (center.X(), center.Y(), center.Z())
    except Exception as e:
        logger.trace(f"[FaceHash] get_face_center failed: {e}")
        return (0.0, 0.0, 0.0)


def get_face_area(face: 'TopoDS_Face') -> float:
    """
    Computes the surface area of a face.

    Args:
        face: OCP TopoDS_Face

    Returns:
        Surface area in square units
    """
    if not HAS_OCP:
        return 0.0

    try:
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        return props.Mass()
    except Exception as e:
        logger.trace(f"[FaceHash] get_face_area failed: {e}")
        return 0.0


def get_face_normal(face: 'TopoDS_Face') -> Optional[Tuple[float, float, float]]:
    """
    Gets the surface normal at the center of a planar face.

    Args:
        face: OCP TopoDS_Face

    Returns:
        Tuple (nx, ny, nz) normal vector, or None for non-planar faces
    """
    if not HAS_OCP:
        return None

    try:
        adaptor = BRepAdaptor_Surface(face)
        surface_type = adaptor.GetType()

        if surface_type == GeomAbs_Plane:
            plane = adaptor.Plane()
            direction = plane.Axis().Direction()
            return (direction.X(), direction.Y(), direction.Z())
        elif surface_type == GeomAbs_Cylinder:
            # For cylinders, return axis direction
            cyl = adaptor.Cylinder()
            direction = cyl.Axis().Direction()
            return (direction.X(), direction.Y(), direction.Z())

        return None
    except Exception as e:
        logger.trace(f"[FaceHash] get_face_normal failed: {e}")
        return None


def get_face_bounding_box(face: 'TopoDS_Face') -> Tuple[float, float, float, float, float, float]:
    """
    Gets the bounding box of a face.

    Args:
        face: OCP TopoDS_Face

    Returns:
        Tuple (xmin, ymin, zmin, xmax, ymax, zmax)
    """
    if not HAS_OCP:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    try:
        bbox = Bnd_Box()
        BRepBndLib.Add_s(face, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        return (xmin, ymin, zmin, xmax, ymax, zmax)
    except Exception as e:
        logger.trace(f"[FaceHash] get_face_bounding_box failed: {e}")
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def compute_face_hash(face: 'TopoDS_Face', precision: int = 3) -> str:
    """
    Computes a stable geometric hash for a B-Rep face.

    The hash is based on:
    - Surface type (plane, cylinder, cone, sphere, etc.)
    - Surface area (with tolerance)
    - Center of mass
    - Bounding box corners (for uniqueness of symmetric faces)
    - Type-specific parameters (normal for planes, radius for cylinders)

    Args:
        face: OCP TopoDS_Face
        precision: Decimal places for rounding (default 3 = 0.001 tolerance)

    Returns:
        16-character hex hash string
    """
    if not HAS_OCP:
        return "0" * 16

    try:
        adaptor = BRepAdaptor_Surface(face)
        surface_type = adaptor.GetType()
        surface_type_name = get_surface_type_name(surface_type)

        # Get geometric properties
        area = get_face_area(face)
        center = get_face_center(face)
        bbox = get_face_bounding_box(face)

        # Build hash components
        components = [
            f"type:{surface_type_name}",
            f"area:{round(area, precision)}",
            f"cx:{round(center[0], precision)}",
            f"cy:{round(center[1], precision)}",
            f"cz:{round(center[2], precision)}",
        ]

        # Add bounding box for uniqueness (prevents collision for symmetric faces)
        components.extend([
            f"bx:{round(bbox[0], precision)}_{round(bbox[3], precision)}",
            f"by:{round(bbox[1], precision)}_{round(bbox[4], precision)}",
            f"bz:{round(bbox[2], precision)}_{round(bbox[5], precision)}",
        ])

        # Add type-specific parameters
        if surface_type == GeomAbs_Plane:
            plane = adaptor.Plane()
            normal = plane.Axis().Direction()
            components.extend([
                f"nx:{round(normal.X(), precision)}",
                f"ny:{round(normal.Y(), precision)}",
                f"nz:{round(normal.Z(), precision)}",
            ])
        elif surface_type == GeomAbs_Cylinder:
            cyl = adaptor.Cylinder()
            components.append(f"radius:{round(cyl.Radius(), precision)}")
            axis = cyl.Axis().Direction()
            components.extend([
                f"ax:{round(axis.X(), precision)}",
                f"ay:{round(axis.Y(), precision)}",
                f"az:{round(axis.Z(), precision)}",
            ])
        elif surface_type == GeomAbs_Cone:
            cone = adaptor.Cone()
            components.append(f"angle:{round(cone.SemiAngle(), precision)}")
        elif surface_type == GeomAbs_Sphere:
            sphere = adaptor.Sphere()
            components.append(f"radius:{round(sphere.Radius(), precision)}")
        elif surface_type == GeomAbs_Torus:
            torus = adaptor.Torus()
            components.extend([
                f"major:{round(torus.MajorRadius(), precision)}",
                f"minor:{round(torus.MinorRadius(), precision)}",
            ])

        # Compute hash
        hash_input = "|".join(components)
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    except Exception as e:
        logger.warning(f"[FaceHash] compute_face_hash failed: {e}")
        return "0" * 16


def get_face_info(face: 'TopoDS_Face') -> Dict[str, Any]:
    """
    Gets complete face information including hash.

    Args:
        face: OCP TopoDS_Face

    Returns:
        Dict with keys: hash, center, normal, area, surface_type, bbox
    """
    if not HAS_OCP:
        return {
            "hash": "0" * 16,
            "center": (0.0, 0.0, 0.0),
            "normal": None,
            "area": 0.0,
            "surface_type": "unknown",
            "bbox": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        }

    try:
        adaptor = BRepAdaptor_Surface(face)
        surface_type = adaptor.GetType()

        return {
            "hash": compute_face_hash(face),
            "center": get_face_center(face),
            "normal": get_face_normal(face),
            "area": get_face_area(face),
            "surface_type": get_surface_type_name(surface_type),
            "bbox": get_face_bounding_box(face),
        }
    except Exception as e:
        logger.warning(f"[FaceHash] get_face_info failed: {e}")
        return {
            "hash": "0" * 16,
            "center": (0.0, 0.0, 0.0),
            "normal": None,
            "area": 0.0,
            "surface_type": "unknown",
            "bbox": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        }


def faces_match_by_hash(hash1: str, hash2: str) -> bool:
    """
    Checks if two face hashes match.

    Args:
        hash1: First face hash
        hash2: Second face hash

    Returns:
        True if hashes match exactly
    """
    return hash1 == hash2 and hash1 != "0" * 16
