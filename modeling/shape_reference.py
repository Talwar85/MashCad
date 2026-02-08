"""
MashCad - Shape Reference System
=================================

Stable references to B-Rep shapes (faces, edges) that survive topology changes.

Phase 7: TNP (Topological Naming Problem) solution.

Usage:
    from modeling.shape_reference import ShapeReference

    # Create reference from a face
    ref = ShapeReference.from_face(ocp_face)

    # Serialize for persistence
    data = ref.to_dict()

    # Restore and resolve
    ref = ShapeReference.from_dict(data)
    resolved_face = ref.resolve(solid)
"""

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict, Any, List
from loguru import logger

from modeling.face_hash import (
    compute_face_hash, get_face_center, get_face_normal,
    get_face_area, get_surface_type_name, faces_match_by_hash,
    HAS_OCP
)

if HAS_OCP:
    from OCP.TopoDS import TopoDS_Face, TopoDS_Shape, TopoDS
    from OCP.TopExp import TopExp
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps


@dataclass
class ShapeReference:
    """
    Stable reference to a B-Rep face that can survive topology changes.

    Resolution Strategy (cascade):
    1. Hash match (exact) - fastest, most reliable
    2. Geometric matching (fallback) - uses center, normal, area, type

    Attributes:
        geometry_hash: Stable geometric hash of the face
        center: Center of mass (x, y, z)
        normal: Surface normal for planar faces (nx, ny, nz) or None
        area: Surface area
        surface_type: Type name (plane, cylinder, etc.)
        session_id: Temporary sequential ID (only valid in current session)
    """

    # Primary: Geometric hash (most stable)
    geometry_hash: str

    # Secondary: Geometric properties (for fallback matching)
    center: Tuple[float, float, float]
    normal: Optional[Tuple[float, float, float]] = None
    area: Optional[float] = None
    surface_type: str = "unknown"

    # Tertiary: Sequential ID (only valid in current session, not persisted)
    session_id: Optional[int] = None

    def resolve(self, solid: 'TopoDS_Shape') -> Optional['TopoDS_Face']:
        """
        Resolves this reference to a face in the given solid.

        Uses cascade strategy:
        1. Try hash match (exact)
        2. Try geometric matching (fallback)

        Args:
            solid: The solid to search in

        Returns:
            Resolved TopoDS_Face or None if not found
        """
        if not HAS_OCP:
            return None

        try:
            explorer = TopExp_Explorer(solid, TopAbs_FACE)
            candidates = []

            while explorer.More():
                face = TopoDS.Face_s(explorer.Current())
                face_hash = compute_face_hash(face)

                # Exact hash match - best case
                if faces_match_by_hash(face_hash, self.geometry_hash):
                    logger.debug(f"[ShapeRef] Hash match: {self.geometry_hash[:8]}")
                    return face

                # Collect for fallback matching
                score = self._match_score(face)
                candidates.append((score, face, face_hash))
                explorer.Next()

            # Fallback: Best geometric match
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                best_score, best_face, best_hash = candidates[0]

                if best_score > 0.7:  # 70% threshold
                    logger.debug(f"[ShapeRef] Fallback match: score={best_score:.2f} "
                                f"hash={best_hash[:8]} (wanted {self.geometry_hash[:8]})")
                    return best_face
                else:
                    logger.warning(f"[ShapeRef] No good match: best_score={best_score:.2f} "
                                  f"(threshold=0.7)")

            return None

        except Exception as e:
            logger.error(f"[ShapeRef] resolve failed: {e}")
            return None

    def _match_score(self, face: 'TopoDS_Face') -> float:
        """
        Computes geometric match score between this reference and a face.

        Scoring breakdown:
        - Center distance: 40%
        - Normal match: 30%
        - Area match: 20%
        - Type match: 10%

        Args:
            face: Face to compare against

        Returns:
            Score from 0.0 to 1.0
        """
        score = 0.0

        try:
            # Center distance (40%)
            fc = get_face_center(face)
            dist = math.sqrt(
                (fc[0] - self.center[0])**2 +
                (fc[1] - self.center[1])**2 +
                (fc[2] - self.center[2])**2
            )
            # Score decreases with distance, 0 at 10mm distance
            score += max(0, 1.0 - dist / 10.0) * 0.4

            # Normal match (30%)
            if self.normal:
                fn = get_face_normal(face)
                if fn:
                    dot = abs(
                        fn[0] * self.normal[0] +
                        fn[1] * self.normal[1] +
                        fn[2] * self.normal[2]
                    )
                    score += dot * 0.3

            # Area match (20%)
            if self.area and self.area > 0:
                face_area = get_face_area(face)
                if face_area > 0:
                    ratio = min(face_area, self.area) / max(face_area, self.area)
                    score += ratio * 0.2

            # Type match (10%)
            adaptor = BRepAdaptor_Surface(face)
            face_type = get_surface_type_name(adaptor.GetType())
            if face_type == self.surface_type:
                score += 0.1

        except Exception as e:
            logger.trace(f"[ShapeRef] _match_score failed: {e}")

        return score

    def to_dict(self) -> Dict[str, Any]:
        """
        Serializes this reference for persistence.

        Returns:
            Dict suitable for JSON serialization
        """
        return {
            "geometry_hash": self.geometry_hash,
            "center": list(self.center),
            "normal": list(self.normal) if self.normal else None,
            "area": self.area,
            "surface_type": self.surface_type,
            # Note: session_id is NOT persisted - only valid in current session
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ShapeReference':
        """
        Restores a reference from persisted data.

        Args:
            data: Dict from to_dict()

        Returns:
            ShapeReference instance
        """
        return cls(
            geometry_hash=data.get("geometry_hash", "0" * 16),
            center=tuple(data.get("center", (0, 0, 0))),
            normal=tuple(data["normal"]) if data.get("normal") else None,
            area=data.get("area"),
            surface_type=data.get("surface_type", "unknown"),
            session_id=None,  # Not persisted
        )

    @classmethod
    def from_face(cls, face: 'TopoDS_Face', face_id: int = None) -> 'ShapeReference':
        """
        Creates a ShapeReference from a B-Rep face.

        Args:
            face: OCP TopoDS_Face
            face_id: Optional sequential ID for current session

        Returns:
            ShapeReference instance
        """
        if not HAS_OCP:
            return cls(
                geometry_hash="0" * 16,
                center=(0, 0, 0),
                session_id=face_id,
            )

        try:
            adaptor = BRepAdaptor_Surface(face)

            return cls(
                geometry_hash=compute_face_hash(face),
                center=get_face_center(face),
                normal=get_face_normal(face),
                area=get_face_area(face),
                surface_type=get_surface_type_name(adaptor.GetType()),
                session_id=face_id,
            )
        except Exception as e:
            logger.error(f"[ShapeRef] from_face failed: {e}")
            return cls(
                geometry_hash="0" * 16,
                center=(0, 0, 0),
                session_id=face_id,
            )

    def __repr__(self) -> str:
        return (f"ShapeReference(hash={self.geometry_hash[:8]}..., "
                f"type={self.surface_type}, id={self.session_id})")


def find_face_by_hash(solid: 'TopoDS_Shape', target_hash: str) -> Optional['TopoDS_Face']:
    """
    Finds a face in a solid by its hash.

    Args:
        solid: Solid to search
        target_hash: Target face hash

    Returns:
        Matching face or None
    """
    if not HAS_OCP:
        return None

    try:
        explorer = TopExp_Explorer(solid, TopAbs_FACE)
        while explorer.More():
            face = TopoDS.Face_s(explorer.Current())
            if compute_face_hash(face) == target_hash:
                return face
            explorer.Next()
        return None
    except Exception as e:
        logger.error(f"[ShapeRef] find_face_by_hash failed: {e}")
        return None


def find_face_by_id(solid: 'TopoDS_Shape', target_id: int) -> Optional['TopoDS_Face']:
    """
    Finds a face in a solid by its sequential ID.

    Note: This is only reliable within a single session. IDs can change
    after topology-modifying operations.

    Args:
        solid: Solid to search
        target_id: Target face ID (0-indexed)

    Returns:
        Matching face or None
    """
    if not HAS_OCP:
        return None

    try:
        if target_id < 0:
            return None

        face_map = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(solid, TopAbs_FACE, face_map)
        one_based = target_id + 1
        if one_based > face_map.Extent():
            return None
        return TopoDS.Face_s(face_map.FindKey(one_based))
        return None
    except Exception as e:
        logger.error(f"[ShapeRef] find_face_by_id failed: {e}")
        return None


def create_reference_map(solid: 'TopoDS_Shape') -> Dict[int, ShapeReference]:
    """
    Creates a map of face IDs to ShapeReferences for a solid.

    Useful for building the initial reference map when a body is created.

    Args:
        solid: Solid to map

    Returns:
        Dict mapping face_id -> ShapeReference
    """
    result = {}

    if not HAS_OCP:
        return result

    try:
        face_map = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(solid, TopAbs_FACE, face_map)
        for one_based in range(1, face_map.Extent() + 1):
            face_id = one_based - 1
            face = TopoDS.Face_s(face_map.FindKey(one_based))
            result[face_id] = ShapeReference.from_face(face, face_id)
    except Exception as e:
        logger.error(f"[ShapeRef] create_reference_map failed: {e}")

    return result
