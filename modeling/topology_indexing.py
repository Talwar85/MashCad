
"""
Utilities for stable face index mapping.

This module centralizes "index -> face object" resolution so all call sites use
the same contract. Primary strategy is build123d's `shape.faces()[index]`.
"""

from typing import Dict, Iterator, List, Optional, Tuple

from loguru import logger

try:
    from build123d import Edge, Face
except ImportError:  # pragma: no cover
    Edge = None  # type: ignore
    Face = None  # type: ignore

HAS_OCP = False
try:  # pragma: no cover - import guard
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from OCP.TopoDS import TopoDS
    HAS_OCP = True
except Exception:  # pragma: no cover
    HAS_OCP = False


def _shape_faces(shape_like) -> List:
    """Resolve all faces from a build123d/OCP shape with stable ordering."""
    if shape_like is None:
        return []

    # Preferred path: build123d's canonical face ordering.
    canonical = []
    if hasattr(shape_like, "faces"):
        try:
            canonical = list(shape_like.faces())
        except Exception:
            pass

    # Optional direct API hooks if a topology helper object is provided.
    if not canonical and hasattr(shape_like, "map_index_to_face"):
        try:
            mapped_faces = []
            idx = 0
            while True:
                face = shape_like.map_index_to_face(idx)
                if face is None:
                    break
                mapped_faces.append(face)
                idx += 1
            if mapped_faces:
                canonical = mapped_faces
        except Exception:
            pass

    if not HAS_OCP or Face is None:
        return canonical

    # If no canonical strategy, fallback to IndexMap via MapShapes (normalized)
    if not canonical:
        ocp_shape = shape_like.wrapped if hasattr(shape_like, "wrapped") else shape_like
        try:
            face_map = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(ocp_shape, TopAbs_FACE, face_map)
            for one_based_idx in range(1, face_map.Extent() + 1):
                canonical.append(Face(TopoDS.Face_s(face_map.FindKey(one_based_idx))))
        except Exception as exc:
            logger.debug(f"topology_indexing: face extraction failed: {exc}")
            return []

    # FIX: Restore correct orientation from Topology logic!
    # build123d/.faces() or MapShapes normalizes orientation to Forward.
    # We must match them back to the actual oriented faces in the solid for history to work.
    try:
        ocp_shape = shape_like.wrapped if hasattr(shape_like, "wrapped") else shape_like
        oriented_faces = []
        expl = TopExp_Explorer(ocp_shape, TopAbs_FACE)
        while expl.More():
            oriented_faces.append(expl.Current())
            expl.Next()
        
        # Match canonical (sorted) list to oriented instances
        result = []
        for face_obj in canonical:
            mapped = face_obj
            c_shape = face_obj.wrapped if hasattr(face_obj, "wrapped") else face_obj
            for o_shape in oriented_faces:
                if c_shape.IsSame(o_shape):
                    # Found the oriented version of this face
                    mapped = Face(TopoDS.Face_s(o_shape))
                    break
            result.append(mapped)
        return result

    except Exception as e:
        logger.warning(f"topology_indexing: orientation fix failed: {e}")
        return canonical


def _shape_edges(shape_like) -> List:
    """Resolve all edges from a build123d/OCP shape with stable ordering."""
    if shape_like is None:
        return []

    # Preferred path: build123d's canonical edge ordering.
    canonical = []
    if hasattr(shape_like, "edges"):
        try:
            canonical = list(shape_like.edges())
        except Exception:
            pass

    # Optional direct API hooks if a topology helper object is provided.
    if not canonical and hasattr(shape_like, "map_index_to_edge"):
        try:
            mapped_edges = []
            idx = 0
            while True:
                edge = shape_like.map_index_to_edge(idx)
                if edge is None:
                    break
                mapped_edges.append(edge)
                idx += 1
            if mapped_edges:
                canonical = mapped_edges
        except Exception:
            pass

    if not HAS_OCP or Edge is None:
        return canonical

    if not canonical:
        ocp_shape = shape_like.wrapped if hasattr(shape_like, "wrapped") else shape_like
        try:
            edge_map = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(ocp_shape, TopAbs_EDGE, edge_map)
            for one_based_idx in range(1, edge_map.Extent() + 1):
                canonical.append(Edge(TopoDS.Edge_s(edge_map.FindKey(one_based_idx))))
        except Exception:
            return []

    # FIX: Restore correct orientation
    try:
        ocp_shape = shape_like.wrapped if hasattr(shape_like, "wrapped") else shape_like
        oriented_edges = []
        expl = TopExp_Explorer(ocp_shape, TopAbs_EDGE)
        while expl.More():
            oriented_edges.append(expl.Current())
            expl.Next()
            
        result = []
        for edge_obj in canonical:
            mapped = edge_obj
            c_shape = edge_obj.wrapped if hasattr(edge_obj, "wrapped") else edge_obj
            for o_shape in oriented_edges:
                if c_shape.IsSame(o_shape):
                    mapped = Edge(TopoDS.Edge_s(o_shape))
                    break
            result.append(mapped)
        return result

    except Exception as e:
        return canonical


def iter_faces_with_indices(shape_like) -> Iterator[Tuple[int, object]]:
    """Iterate `(index, face)` with a consistent face ordering."""
    for idx, face in enumerate(_shape_faces(shape_like)):
        yield idx, face


def iter_edges_with_indices(shape_like) -> Iterator[Tuple[int, object]]:
    """Iterate `(index, edge)` with a consistent edge ordering."""
    for idx, edge in enumerate(_shape_edges(shape_like)):
        yield idx, edge


def face_from_index(shape_like, index: int):
    """Resolve a single face by zero-based index."""
    if index is None or index < 0:
        return None

    # Optional direct API if available.
    if hasattr(shape_like, "face_from_index"):
        try:
            return shape_like.face_from_index(index)
        except Exception:
            pass

    faces = _shape_faces(shape_like)
    if 0 <= index < len(faces):
        return faces[index]
    return None


def edge_from_index(shape_like, index: int):
    """Resolve a single edge by zero-based index."""
    if index is None or index < 0:
        return None

    if hasattr(shape_like, "edge_from_index"):
        try:
            return shape_like.edge_from_index(index)
        except Exception:
            pass

    edges = _shape_edges(shape_like)
    if 0 <= index < len(edges):
        return edges[index]
    return None


def _is_same_topo_entity(entity_a, entity_b) -> bool:
    if entity_a is None or entity_b is None:
        return False
    try:
        wa = entity_a.wrapped if hasattr(entity_a, "wrapped") else entity_a
        wb = entity_b.wrapped if hasattr(entity_b, "wrapped") else entity_b
        return wa.IsSame(wb)
    except Exception:
        return entity_a is entity_b


def face_index_of(shape_like, face_obj) -> Optional[int]:
    """Resolve the zero-based index of a face object in the current topology."""
    if face_obj is None:
        return None
    for idx, candidate in iter_faces_with_indices(shape_like):
        if _is_same_topo_entity(candidate, face_obj):
            return idx
    return None


def edge_index_of(shape_like, edge_obj) -> Optional[int]:
    """Resolve the zero-based index of an edge object in the current topology."""
    if edge_obj is None:
        return None
    for idx, candidate in iter_edges_with_indices(shape_like):
        if _is_same_topo_entity(candidate, edge_obj):
            return idx
    return None


def map_index_to_face(shape_like, index: int):
    """Alias kept for readability in call sites mirroring other CAD APIs."""
    return face_from_index(shape_like, index)


def map_index_to_edge(shape_like, index: int):
    """Alias kept for readability in call sites mirroring other CAD APIs."""
    return edge_from_index(shape_like, index)


def dump_topology_faces(shape_like) -> List[Dict]:
    """
    Return debug info for all internal face index mappings.

    The result is suitable for logging/tests and serves as a local equivalent of
    a `dump_TopoShape()` style utility.
    """
    dump: List[Dict] = []
    for idx, face in iter_faces_with_indices(shape_like):
        entry = {"index": idx}
        try:
            center = face.center()
            entry["center"] = (float(center.X), float(center.Y), float(center.Z))
        except Exception:
            entry["center"] = None
        try:
            entry["area"] = float(face.area) if hasattr(face, "area") else None
        except Exception:
            entry["area"] = None
        dump.append(entry)
    return dump


def dump_topology_edges(shape_like) -> List[Dict]:
    """
    Return debug info for all internal edge index mappings.

    The result is suitable for logging/tests and serves as a local equivalent of
    a `dump_TopoShape()` style utility.
    """
    dump: List[Dict] = []
    for idx, edge in iter_edges_with_indices(shape_like):
        entry = {"index": idx}
        try:
            center = edge.center()
            entry["center"] = (float(center.X), float(center.Y), float(center.Z))
        except Exception:
            entry["center"] = None
        try:
            entry["length"] = float(edge.length) if hasattr(edge, "length") else None
        except Exception:
            entry["length"] = None
        dump.append(entry)
    return dump
