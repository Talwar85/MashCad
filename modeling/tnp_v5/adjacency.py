"""
TNP v5.0 - Adjacency Tracker

Tracks topological relationships between shapes for resolution.
"""

from dataclasses import dataclass, field
from typing import Dict, Set, List, Optional, Tuple, Any
from collections import defaultdict
from loguru import logger


@dataclass
class AdjacencyGraph:
    """
    Directed graph of shape adjacencies.

    Stores undirected relationships (if A adjacent to B, then B adjacent to A).
    """
    # shape_uuid -> Set of adjacent shape_uuids
    _adjacency: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))

    # edge_uuid -> Set of face_uuids that share this edge
    _edge_to_faces: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))

    # face_uuid -> Set of edge_uuids that bound this face
    _face_to_edges: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))

    # vertex_uuid -> Set of edge_uuids that meet at this vertex
    _vertex_to_edges: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))

    def add_adjacency(self, shape_id_a: str, shape_id_b: str) -> None:
        """
        Record that two shapes are adjacent (undirected).

        Args:
            shape_id_a: First shape UUID
            shape_id_b: Second shape UUID
        """
        if shape_id_a and shape_id_b and shape_id_a != shape_id_b:
            self._adjacency[shape_id_a].add(shape_id_b)
            self._adjacency[shape_id_b].add(shape_id_a)

    def remove_adjacency(self, shape_id_a: str, shape_id_b: str) -> None:
        """
        Remove adjacency between two shapes.

        Args:
            shape_id_a: First shape UUID
            shape_id_b: Second shape UUID
        """
        if shape_id_a in self._adjacency:
            self._adjacency[shape_id_a].discard(shape_id_b)
        if shape_id_b in self._adjacency:
            self._adjacency[shape_id_b].discard(shape_id_a)

    def get_adjacent(self, shape_id: str) -> Set[str]:
        """
        Get all shapes adjacent to the given shape.

        Args:
            shape_id: Shape UUID to query

        Returns:
            Set of adjacent shape UUIDs
        """
        return self._adjacency.get(shape_id, set()).copy()

    def are_adjacent(self, shape_id_a: str, shape_id_b: str) -> bool:
        """
        Check if two shapes are adjacent.

        Args:
            shape_id_a: First shape UUID
            shape_id_b: Second shape UUID

        Returns:
            True if shapes are adjacent
        """
        return shape_id_b in self._adjacency.get(shape_id_a, set())

    def clear(self) -> None:
        """Clear all adjacency data."""
        self._adjacency.clear()
        self._edge_to_faces.clear()
        self._face_to_edges.clear()
        self._vertex_to_edges.clear()

    @property
    def size(self) -> int:
        """Return number of shapes with adjacencies."""
        return len(self._adjacency)


class AdjacencyTracker:
    """
    Tracks topological relationships between shapes.

    Maintains an undirected graph of shape adjacencies specialized for
    CAD topology (faces, edges, vertices).

    Usage:
        tracker = AdjacencyTracker()

        # Build from a solid
        tracker.build_from_solid(solid, shape_records)

        # Query adjacencies
        adjacent_faces = tracker.get_adjacent_faces(edge_uuid)
        adjacent_edges = tracker.get_adjacent_edges(face_uuid)

        # Find paths
        path = tracker.find_shortest_path(start_uuid, end_uuid)
    """

    def __init__(self):
        """Initialize the adjacency tracker."""
        self._graph = AdjacencyGraph()

        # Statistics
        self._build_count = 0
        self._last_build_size = 0

    # ==========================================================================
    # Graph Building
    # ==========================================================================

    def build_from_solid(
        self,
        solid: Any,
        shape_records: Dict[str, Any]
    ) -> int:
        """
        Build adjacency graph from a solid.

        Analyzes faces and edges to determine connectivity using OCP tools.

        Args:
            solid: build123d Solid or OCP TopoDS_Solid
            shape_records: Dict mapping UUID -> ShapeRecord (with ocp_shape)

        Returns:
            Number of adjacencies recorded
        """
        try:
            from OCP.TopExp import TopExp
            from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
            from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
            from OCP.TopoDS import TopoDS
        except ImportError:
            logger.warning("[AdjacencyTracker] OCP not available, cannot build from solid")
            return 0

        # Get OCP shape
        ocp_solid = solid.wrapped if hasattr(solid, 'wrapped') else solid

        # Build OCP shape -> UUID mapping
        ocp_to_uuid = self._build_ocp_map(shape_records)

        if not ocp_to_uuid:
            logger.debug("[AdjacencyTracker] No OCP shapes mapped, skipping build")
            return 0

        try:
            # Use OCP's edge->face map for efficient adjacency
            edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
            TopExp.MapShapesAndAncestors_s(ocp_solid, TopAbs_EDGE, TopAbs_FACE, edge_face_map)
        except Exception as e:
            logger.debug(f"[AdjacencyTracker] Could not build edge-face map: {e}")
            return 0

        adjacencies_added = 0

        # Process each edge in the map
        for edge_idx in range(1, edge_face_map.Extent() + 1):
            edge = edge_face_map.FindKey(edge_idx)
            edge_uuid = ocp_to_uuid.get(id(edge))

            if not edge_uuid:
                continue

            # Get faces adjacent to this edge
            adjacent_faces = edge_face_map.FindFromIndex(edge_idx)
            for face_idx in range(1, adjacent_faces.Size() + 1):
                face = adjacent_faces.Value(face_idx)
                face_uuid = ocp_to_uuid.get(id(face))

                if face_uuid:
                    # Record edge-face adjacency
                    self._graph.add_adjacency(edge_uuid, face_uuid)
                    self._graph._edge_to_faces[edge_uuid].add(face_uuid)
                    self._graph._face_to_edges[face_uuid].add(edge_uuid)
                    adjacencies_added += 1

        # Build face-face adjacencies (faces sharing an edge)
        for edge_uuid, face_uuids in self._graph._edge_to_faces.items():
            face_list = list(face_uuids)
            # Each pair of faces sharing this edge are adjacent
            for i in range(len(face_list)):
                for j in range(i + 1, len(face_list)):
                    self._graph.add_adjacency(face_list[i], face_list[j])

        # Build vertex-edge adjacencies
        self._build_vertex_adjacencies(ocp_solid, ocp_to_uuid)

        self._build_count += 1
        self._last_build_size = adjacencies_added

        logger.debug(f"[AdjacencyTracker] Built graph: {adjacencies_added} adjacencies, "
                    f"{self._graph.size} shapes")

        return adjacencies_added

    def _build_ocp_map(self, shape_records: Dict[str, Any]) -> Dict[int, str]:
        """
        Build OCP object id -> UUID mapping.

        Args:
            shape_records: Dict mapping UUID -> ShapeRecord

        Returns:
            Dict mapping OCP object id -> UUID
        """
        ocp_to_uuid = {}
        for uuid, record in shape_records.items():
            ocp_shape = None
            if hasattr(record, 'ocp_shape'):
                ocp_shape = record.ocp_shape
            elif hasattr(record, 'shape_id'):
                # Try to get from shape_id if it has ocp_shape
                shape_id = record.shape_id
                if hasattr(shape_id, 'ocp_shape'):
                    ocp_shape = shape_id.ocp_shape

            if ocp_shape is not None:
                wrapped = ocp_shape.wrapped if hasattr(ocp_shape, 'wrapped') else ocp_shape
                ocp_to_uuid[id(wrapped)] = uuid

        return ocp_to_uuid

    def _build_vertex_adjacencies(
        self,
        ocp_solid: Any,
        ocp_to_uuid: Dict[int, str]
    ) -> None:
        """
        Build vertex->edge adjacencies.

        Args:
            ocp_solid: OCP TopoDS_Solid
            ocp_to_uuid: OCP object id -> UUID mapping
        """
        try:
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_VERTEX, TopAbs_EDGE
            from OCP.TopoDS import TopoDS

            explorer = TopExp_Explorer(ocp_solid, TopAbs_EDGE)
            while explorer.More():
                edge = explorer.Current()
                edge_uuid = ocp_to_uuid.get(id(edge))

                if edge_uuid:
                    # Get vertices of this edge
                    from OCP.TopExp import TopExp as TopExpQuery
                    vertex_start = TopExpQuery.FirstVertex_s(edge)
                    vertex_end = TopExpQuery.LastVertex_s(edge)

                    for vertex in [vertex_start, vertex_end]:
                        vertex_uuid = ocp_to_uuid.get(id(vertex))
                        if vertex_uuid:
                            self._graph.add_adjacency(vertex_uuid, edge_uuid)
                            self._graph._vertex_to_edges[vertex_uuid].add(edge_uuid)

                explorer.Next()

        except Exception as e:
            logger.debug(f"[AdjacencyTracker] Vertex adjacency build failed: {e}")

    # ==========================================================================
    # Adjacency Queries
    # ==========================================================================

    def add_adjacency(self, shape_id_a: str, shape_id_b: str) -> None:
        """
        Manually record that two shapes are adjacent.

        Args:
            shape_id_a: First shape UUID
            shape_id_b: Second shape UUID
        """
        self._graph.add_adjacency(shape_id_a, shape_id_b)

    def get_adjacent(self, shape_id: str) -> Set[str]:
        """
        Get all shapes adjacent to the given shape.

        Args:
            shape_id: Shape UUID to query

        Returns:
            Set of adjacent shape UUIDs
        """
        return self._graph.get_adjacent(shape_id)

    def are_adjacent(self, shape_id_a: str, shape_id_b: str) -> bool:
        """
        Check if two shapes are directly adjacent.

        Args:
            shape_id_a: First shape UUID
            shape_id_b: Second shape UUID

        Returns:
            True if shapes are adjacent
        """
        return self._graph.are_adjacent(shape_id_a, shape_id_b)

    def get_adjacent_faces(self, edge_uuid: str) -> Set[str]:
        """
        Get all faces that share this edge.

        Args:
            edge_uuid: Edge UUID

        Returns:
            Set of face UUIDs adjacent to this edge
        """
        return self._graph._edge_to_faces.get(edge_uuid, set()).copy()

    def get_adjacent_edges(self, face_uuid: str) -> Set[str]:
        """
        Get all edges that bound this face.

        Args:
            face_uuid: Face UUID

        Returns:
            Set of edge UUIDs bounding this face
        """
        return self._graph._face_to_edges.get(face_uuid, set()).copy()

    def get_adjacent_edges_for_vertex(self, vertex_uuid: str) -> Set[str]:
        """
        Get all edges that meet at this vertex.

        Args:
            vertex_uuid: Vertex UUID

        Returns:
            Set of edge UUIDs meeting at this vertex
        """
        return self._graph._vertex_to_edges.get(vertex_uuid, set()).copy()

    def get_shared_faces(self, edge_a: str, edge_b: str) -> Set[str]:
        """
        Get faces shared by two edges (if any).

        Args:
            edge_a: First edge UUID
            edge_b: Second edge UUID

        Returns:
            Set of face UUIDs shared by both edges
        """
        faces_a = self._graph._edge_to_faces.get(edge_a, set())
        faces_b = self._graph._edge_to_faces.get(edge_b, set())
        return faces_a & faces_b

    # ==========================================================================
    # Path Finding
    # ==========================================================================

    def find_shortest_path(
        self,
        start_uuid: str,
        end_uuid: str,
        max_hops: int = 5
    ) -> Optional[List[str]]:
        """
        Find shortest path between two shapes using BFS.

        Args:
            start_uuid: Starting shape UUID
            end_uuid: Target shape UUID
            max_hops: Maximum path length to search

        Returns:
            List of shape UUIDs forming path, or None if no path found
        """
        if start_uuid == end_uuid:
            return [start_uuid]

        if start_uuid not in self._graph._adjacency:
            return None

        # BFS
        from collections import deque
        queue = deque([(start_uuid, [start_uuid])])
        visited = {start_uuid}

        while queue:
            current, path = queue.popleft()

            if len(path) > max_hops + 1:
                continue

            for neighbor in self._graph.get_adjacent(current):
                if neighbor == end_uuid:
                    return path + [neighbor]

                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return None

    def find_path_via_shape_type(
        self,
        start_uuid: str,
        end_uuid: str,
        shape_records: Dict[str, Any],
        intermediate_type: Any
    ) -> Optional[List[str]]:
        """
        Find path that goes through a specific shape type.

        Useful for finding face -> edge -> face paths.

        Args:
            start_uuid: Starting shape UUID
            end_uuid: Target shape UUID
            shape_records: Dict mapping UUID -> ShapeRecord
            intermediate_type: ShapeType enum for intermediate shapes

        Returns:
            List of shape UUIDs forming path, or None
        """
        path = self.find_shortest_path(start_uuid, end_uuid, max_hops=3)

        if not path or len(path) < 3:
            return path

        # Check if intermediate matches requested type
        intermediate_uuid = path[1] if len(path) > 1 else None
        if intermediate_uuid and intermediate_uuid in shape_records:
            record = shape_records[intermediate_uuid]
            shape_type = None
            if hasattr(record, 'shape_id'):
                shape_type = record.shape_id.shape_type
            elif hasattr(record, 'shape_type'):
                shape_type = record.shape_type

            if shape_type == intermediate_type:
                return path

        return None

    # ==========================================================================
    # Statistics & Utilities
    # ==========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the adjacency graph.

        Returns:
            Dict with statistics
        """
        # Calculate degree distribution
        degrees = [len(adj) for adj in self._graph._adjacency.values()]
        avg_degree = sum(degrees) / len(degrees) if degrees else 0
        max_degree = max(degrees) if degrees else 0

        return {
            'num_shapes': self._graph.size,
            'num_edge_face_links': len(self._graph._edge_to_faces),
            'num_face_edge_links': len(self._graph._face_to_edges),
            'num_vertex_edge_links': len(self._graph._vertex_to_edges),
            'avg_degree': round(avg_degree, 2),
            'max_degree': max_degree,
            'build_count': self._build_count,
            'last_build_size': self._last_build_size
        }

    def clear(self) -> None:
        """Clear all adjacency data."""
        self._graph.clear()
        logger.debug("[AdjacencyTracker] Cleared")

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize adjacency graph to dict.

        Returns:
            Dict representation of the graph
        """
        return {
            'adjacency': {k: list(v) for k, v in self._graph._adjacency.items()},
            'edge_to_faces': {k: list(v) for k, v in self._graph._edge_to_faces.items()},
            'face_to_edges': {k: list(v) for k, v in self._graph._face_to_edges.items()},
            'vertex_to_edges': {k: list(v) for k, v in self._graph._vertex_to_edges.items()},
            'stats': self.get_stats()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AdjacencyTracker':
        """
        Deserialize adjacency graph from dict.

        Args:
            data: Dict representation from to_dict()

        Returns:
            AdjacencyTracker instance
        """
        tracker = cls()

        # Restore adjacencies
        for shape_id, adjacents in data.get('adjacency', {}).items():
            for adj in adjacents:
                tracker._graph._adjacency[shape_id].add(adj)

        # Restore edge->face
        for edge_id, faces in data.get('edge_to_faces', {}).items():
            tracker._graph._edge_to_faces[edge_id] = set(faces)

        # Restore face->edge
        for face_id, edges in data.get('face_to_edges', {}).items():
            tracker._graph._face_to_edges[face_id] = set(edges)

        # Restore vertex->edge
        for vertex_id, edges in data.get('vertex_to_edges', {}).items():
            tracker._graph._vertex_to_edges[vertex_id] = set(edges)

        return tracker


# Convenience functions

def compute_adjacency_similarity(
    tracker: AdjacencyTracker,
    shape_id_a: str,
    shape_id_b: str
) -> float:
    """
    Compute Jaccard similarity of adjacency sets for two shapes.

    Useful for semantic matching when comparing candidates.

    Args:
        tracker: AdjacencyTracker instance
        shape_id_a: First shape UUID
        shape_id_b: Second shape UUID

    Returns:
        Jaccard similarity (0.0 to 1.0)
    """
    adj_a = tracker.get_adjacent(shape_id_a)
    adj_b = tracker.get_adjacent(shape_id_b)

    if not adj_a and not adj_b:
        return 1.0  # Both have no adjacents

    intersection = len(adj_a & adj_b)
    union = len(adj_a | adj_b)

    return intersection / union if union > 0 else 0.0
